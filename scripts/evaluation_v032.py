"""Budgeted, resumable, explicit-start PHYSIS comparison runner.

This module never performs work just by being imported. The default `run`
command prints a dry-run plan; model/provider work requires `--execute` and
four explicit hard limits.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

LIVE_ARMS = ("A", "C", "D", "E", "F")
VALID_PROVIDERS = {"mock", "ollama", "openai", "anthropic", "compatible"}
TRUST_LABEL = "UNTRUSTED_MODEL_OUTPUT_REQUIRES_REVIEW"
MAX_REQUESTS_HARD_CAP = 500
MAX_SECONDS_HARD_CAP = 3600
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
RESULT_ORIGINS = {"replay", "mock", "actual_provider", "archived_baseline", "no_provider_call"}


class EvaluationError(RuntimeError):
    pass


class RunIdentityMismatch(EvaluationError):
    pass


class BudgetExceeded(EvaluationError):
    pass


def _now() -> float:
    return time.time()


def _utc(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else _now(), timezone.utc).isoformat()


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def product_id() -> str:
    """Identify the exact current product tree, not only a release label."""
    from fingerprint_product import inventory

    return inventory()["sha256"]


def _screen(question: str, level: str) -> None:
    from physis.cognitive import excluded_reply

    if excluded_reply(question, level):
        raise EvaluationError("A case is outside the approved classroom physics scope.")


def load_cases(path: Path, default_model: str | None = None) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".jsonl":
        items = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        decoded = json.loads(raw)
        if isinstance(decoded, dict):
            items = decoded.get("items", decoded.get("cases", []))
        elif isinstance(decoded, list):
            items = decoded
        else:
            raise EvaluationError("Case input must be JSON or JSONL.")
    if not items:
        raise EvaluationError("Case input is empty.")
    seen = set()
    cases = []
    for item in items:
        if not isinstance(item, dict):
            raise EvaluationError("Each case must be an object.")
        case_id = item.get("id", item.get("case_id"))
        question = item.get("question")
        level = item.get("level", "school")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise EvaluationError("Case IDs must be non-empty and unique.")
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise EvaluationError(f"Case {case_id} has an invalid question.")
        if level not in {"intro", "school", "university", "research"}:
            raise EvaluationError(f"Case {case_id} has an unsupported level.")
        _screen(question, level)
        model = item.get("model", default_model)
        if model is not None and not isinstance(model, str):
            raise EvaluationError(f"Case {case_id} has an invalid model.")
        seen.add(case_id)
        # Only this allowlist is ever sent to an arm. Answer keys, grades, and
        # references stay local to the case file and are never included.
        cases.append({
            "id": case_id,
            "question": question.strip(),
            "level": level,
            "model": model,
            "patch": item.get("patch", {}),
            "prior": item.get("prior") if isinstance(item.get("prior"), str) else None,
        })
    return cases


def load_config(path: Path | None) -> dict:
    if path is None:
        return {"provider_configs": {"mock": {"provider": "mock", "model": "local-rules"}},
                "default_experiment_model": "uniform"}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise EvaluationError("Provider config must be a JSON object.")
    profiles = data.get("provider_configs")
    if not isinstance(profiles, dict) or not profiles:
        raise EvaluationError("Config must define provider_configs by name.")
    for profile_name, profile in profiles.items():
        if not isinstance(profile_name, str) or not profile_name or not isinstance(profile, dict):
            raise EvaluationError("Each named provider config must be an object.")
        if profile.get("provider") not in VALID_PROVIDERS:
            raise EvaluationError(f"Unknown provider in profile {profile_name}.")
        if not isinstance(profile.get("model"), str) or not profile["model"]:
            raise EvaluationError(f"Profile {profile_name} needs a model ID.")
        for key in ("endpoint_env", "api_key_env"):
            value = profile.get(key)
            if value is not None and (not isinstance(value, str) or not value.isidentifier()):
                raise EvaluationError(f"Profile {profile_name} has an invalid {key}.")
    default_model = data.get("default_experiment_model", "uniform")
    if not isinstance(default_model, str) or not default_model:
        raise EvaluationError("default_experiment_model must be a model ID.")
    data["default_experiment_model"] = default_model
    return data


def select_profiles(config: dict, names: list[str] | None) -> dict[str, dict]:
    profiles = config["provider_configs"]
    selected = names or list(profiles)
    if len(set(selected)) != len(selected) or any(name not in profiles for name in selected):
        raise EvaluationError("Requested provider profile is missing or repeated.")
    return {name: profiles[name] for name in selected}


def selected_arms(config: dict, value: str | None) -> tuple[str, ...]:
    arms = tuple(value.split(",")) if value else tuple(config.get("arms", LIVE_ARMS))
    if not arms or len(set(arms)) != len(arms) or any(arm not in LIVE_ARMS for arm in arms):
        raise EvaluationError("Live arms must be unique entries from A,C,D,E,F. Import archived B separately.")
    return arms


def _runtime_binding(profiles: dict[str, dict], replay_file: Path | None) -> dict:
    binding = {}
    for name, profile in profiles.items():
        endpoint_env = profile.get("endpoint_env")
        endpoint = os.environ.get(endpoint_env, "") if endpoint_env else ""
        key_env = profile.get("api_key_env")
        binding[name] = {
            "endpoint_sha256": _sha_bytes(endpoint.encode("utf-8")) if endpoint else None,
            "key_env_name": key_env,
            "key_present": bool(os.environ.get(key_env)) if key_env else None,
            "adapter_key_present": bool(os.environ.get({"openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY", "compatible": "PHYSIS_COMPATIBLE_API_KEY"}.get(
                    profile["provider"], ""))) if profile["provider"] != "mock" else None,
        }
    binding["replay_sha256"] = _sha_file(replay_file) if replay_file else None
    binding["runner_sha256"] = _sha_file(Path(__file__))
    return binding


def _config_id(profiles: dict[str, dict], arms: tuple[str, ...], config: dict,
               runtime_binding: dict | None = None) -> str:
    canonical = {
        "provider_configs": profiles,
        "arms": list(arms),
        "default_experiment_model": config.get("default_experiment_model"),
        "knowledge_db_env": config.get("knowledge_db_env"),
        "api_data_dir": config.get("api_data_dir"),
        "runtime_binding": runtime_binding or {},
    }
    return _sha_bytes(_canonical(canonical))


def build_plan(cases: list[dict], profiles: dict[str, dict], arms: tuple[str, ...]) -> list[dict]:
    plan = []
    for profile_name, profile in profiles.items():
        for arm in arms:
            for case in cases:
                plan.append({"provider_config": profile_name, "provider": profile["provider"],
                             "model": profile["model"], "arm": arm, "case_id": case["id"]})
    return plan


class ProgressStore:
    """SQLite progress ledger; reservations are committed before each model call."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY, input_id TEXT NOT NULL, config_id TEXT NOT NULL,
          product_id TEXT NOT NULL, max_requests INTEGER NOT NULL,
          max_seconds REAL NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS invocations (
          invocation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
          max_requests INTEGER NOT NULL, max_seconds REAL NOT NULL, started_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS request_reservations (
          reservation_id INTEGER PRIMARY KEY AUTOINCREMENT,
          invocation_id TEXT NOT NULL REFERENCES invocations(invocation_id),
          provider_config TEXT NOT NULL, arm TEXT NOT NULL, case_id TEXT NOT NULL,
          operation TEXT NOT NULL, units INTEGER NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS case_results (
          run_id TEXT NOT NULL REFERENCES runs(run_id), provider_config TEXT NOT NULL,
          arm TEXT NOT NULL, case_id TEXT NOT NULL, attempt INTEGER NOT NULL,
          question_hash TEXT NOT NULL, status TEXT NOT NULL, started_at REAL NOT NULL,
          finished_at REAL, request_count INTEGER NOT NULL DEFAULT 0,
          output_json TEXT, error TEXT, origin TEXT NOT NULL DEFAULT 'no_provider_call',
          PRIMARY KEY(run_id, provider_config, arm, case_id, attempt)
        );
        CREATE INDEX IF NOT EXISTS case_results_lookup
          ON case_results(run_id, provider_config, arm, case_id, attempt);
        """)

    def close(self) -> None:
        self.db.close()

    def create_run(self, run_id: str, input_id: str, config_id: str, product_id_value: str,
                   max_requests_total: int, max_seconds_total: float) -> None:
        if not _RUN_ID.fullmatch(run_id):
            raise EvaluationError("run_id must use letters, digits, dot, dash, or underscore (max 80).")
        row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row:
            if (row["input_id"], row["config_id"], row["product_id"]) != (input_id, config_id, product_id_value):
                raise RunIdentityMismatch("Input, provider config, or product changed; use a new run ID.")
            if max_requests_total > row["max_requests"] or max_seconds_total > row["max_seconds"]:
                raise RunIdentityMismatch("A resumed run cannot raise its original cumulative budget.")
            self.db.execute("UPDATE runs SET max_requests=?,max_seconds=? WHERE run_id=?",
                            (max_requests_total, max_seconds_total, run_id))
            return
        self.db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
                        (run_id, input_id, config_id, product_id_value,
                         max_requests_total, max_seconds_total, _now()))

    def begin_invocation(self, invocation_id: str, max_requests: int, max_seconds: float,
                         run_id: str | None = None) -> str:
        if run_id is None:
            row = self.db.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
        else:
            row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise EvaluationError("Create a run before starting an invocation.")
        if max_requests > row["max_requests"] or max_seconds > row["max_seconds"]:
            raise BudgetExceeded("Invocation limits cannot exceed the cumulative run limits.")
        if _now() - row["created_at"] >= row["max_seconds"]:
            raise BudgetExceeded("The cumulative wall-time budget has expired.")
        spent = self.request_usage(row["run_id"])
        if spent >= row["max_requests"]:
            raise BudgetExceeded("The cumulative request budget is exhausted.")
        self.db.execute("INSERT INTO invocations VALUES (?,?,?,?,?)",
                        (invocation_id, row["run_id"], max_requests, max_seconds, _now()))
        return invocation_id

    def _check_budget(self, invocation_id: str, additional: int = 0) -> tuple[str, float]:
        inv = self.db.execute("SELECT * FROM invocations WHERE invocation_id=?", (invocation_id,)).fetchone()
        if not inv:
            raise EvaluationError("Invocation is unknown.")
        run = self.db.execute("SELECT * FROM runs WHERE run_id=?", (inv["run_id"],)).fetchone()
        now = _now()
        inv_used = self.db.execute(
            "SELECT COALESCE(SUM(units),0) FROM request_reservations WHERE invocation_id=?",
            (invocation_id,)).fetchone()[0]
        total_used = self.request_usage(inv["run_id"])
        if inv_used + additional > inv["max_requests"]:
            raise BudgetExceeded("Per-invocation request budget exhausted before provider call.")
        if total_used + additional > run["max_requests"]:
            raise BudgetExceeded("Cumulative request budget exhausted before provider call.")
        inv_remaining = inv["max_seconds"] - (now - inv["started_at"])
        run_remaining = run["max_seconds"] - (now - run["created_at"])
        remaining = min(inv_remaining, run_remaining)
        if remaining <= 0:
            raise BudgetExceeded("Wall-time budget exhausted before provider call.")
        return inv["run_id"], remaining

    def reserve_requests(self, invocation_id: str, operation: str, units: int = 1,
                         provider_config: str = "", arm: str = "", case_id: str = "") -> int:
        if type(units) is not int or units < 1:
            raise EvaluationError("Request reservations must be positive integers.")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._check_budget(invocation_id, units)
            cur = self.db.execute(
                "INSERT INTO request_reservations(invocation_id,provider_config,arm,case_id,operation,units,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (invocation_id, provider_config, arm, case_id, operation[:80], units, _now()))
            self.db.execute("COMMIT")
            return int(cur.lastrowid)
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def request_usage(self, run_id: str | None = None) -> int:
        if run_id is None:
            row = self.db.execute("SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
            if not row:
                return 0
            run_id = row["run_id"]
        return int(self.db.execute(
            "SELECT COALESCE(SUM(q.units),0) FROM request_reservations q "
            "JOIN invocations i USING(invocation_id) WHERE i.run_id=?", (run_id,)).fetchone()[0])

    def remaining_seconds(self, invocation_id: str) -> float:
        _, remaining = self._check_budget(invocation_id)
        return max(0.001, remaining)

    def recover_interrupted(self, run_id: str) -> int:
        cur = self.db.execute(
            "UPDATE case_results SET status='interrupted',finished_at=?,error='interrupted_by_restart' "
            "WHERE run_id=? AND status='inflight'", (_now(), run_id))
        return cur.rowcount

    def latest_case(self, run_id: str, provider_config: str, arm: str, case_id: str):
        return self.db.execute(
            "SELECT * FROM case_results WHERE run_id=? AND provider_config=? AND arm=? AND case_id=? "
            "ORDER BY attempt DESC LIMIT 1", (run_id, provider_config, arm, case_id)).fetchone()

    def begin_case(self, run_id: str, provider_config: str, arm: str, case_id: str,
                   question_hash: str) -> int:
        latest = self.latest_case(run_id, provider_config, arm, case_id)
        attempt = (latest["attempt"] + 1) if latest else 1
        self.db.execute(
            "INSERT INTO case_results(run_id,provider_config,arm,case_id,attempt,question_hash,status,started_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (run_id, provider_config, arm, case_id, attempt, question_hash, "inflight", _now()))
        return attempt

    def finish_case(self, run_id: str, provider_config: str, arm: str, case_id: str,
                    status: str, output: dict | None = None, error: str | None = None,
                    origin: str = "no_provider_call") -> None:
        latest = self.latest_case(run_id, provider_config, arm, case_id)
        if not latest or latest["status"] != "inflight":
            raise EvaluationError("Cannot finish a case without an in-flight attempt.")
        output_json = json.dumps(output, ensure_ascii=False, separators=(",", ":")) if output is not None else None
        request_count = self.db.execute(
            "SELECT COALESCE(SUM(q.units),0) FROM request_reservations q "
            "JOIN invocations i USING(invocation_id) WHERE i.run_id=? AND q.provider_config=? "
            "AND q.arm=? AND q.case_id=? AND q.created_at>=?",
            (run_id, provider_config, arm, case_id, latest["started_at"])).fetchone()[0]
        self.db.execute(
            "UPDATE case_results SET status=?,finished_at=?,request_count=?,output_json=?,error=?,origin=? "
            "WHERE run_id=? AND provider_config=? AND arm=? AND case_id=? AND attempt=?",
            (status, _now(), request_count, output_json, error, origin,
             run_id, provider_config, arm, case_id, latest["attempt"]))

    def current_case_request_count(self, run_id: str, provider_config: str,
                                   arm: str, case_id: str) -> int:
        latest = self.latest_case(run_id, provider_config, arm, case_id)
        if not latest:
            return 0
        return int(self.db.execute(
            "SELECT COALESCE(SUM(q.units),0) FROM request_reservations q "
            "JOIN invocations i USING(invocation_id) WHERE i.run_id=? AND q.provider_config=? "
            "AND q.arm=? AND q.case_id=? AND q.created_at>=?",
            (run_id, provider_config, arm, case_id, latest["started_at"])).fetchone()[0])

    def rows(self, run_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM case_results"
        params = ()
        if run_id:
            query += " WHERE run_id=?"
            params = (run_id,)
        query += " ORDER BY provider_config,arm,case_id,attempt"
        return [dict(row) for row in self.db.execute(query, params)]

    def run_row(self, run_id: str | None = None) -> dict:
        if run_id is None:
            row = self.db.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
        else:
            row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else {}


class ProgressLock:
    """Single-writer OS lock; prevents concurrent resumes from duplicating calls."""

    def __init__(self, progress_path: Path):
        self.path = Path(str(progress_path) + ".lock")
        self.file = None
        self._locked = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0, os.SEEK_END)
                if self.file.tell() == 0:
                    self.file.write(b"\0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._locked = True
            return self
        except OSError as exc:
            self.file.close()
            self.file = None
            raise EvaluationError("This progress database is already active in another process.") from exc

    def __exit__(self, exc_type, exc, tb):
        if self.file is None:
            return
        if self._locked:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        self.file.close()
        self.file = None
        self._locked = False


@contextmanager
def provider_environment(profile: dict):
    """Map secret-free env-var references to the provider adapter's known names."""
    provider = profile["provider"]
    changes: dict[str, str] = {}
    endpoint_env = profile.get("endpoint_env")
    key_env = profile.get("api_key_env")
    endpoint_key = {"ollama": "OLLAMA_BASE_URL", "compatible": "PHYSIS_COMPATIBLE_BASE_URL"}.get(provider)
    key_key = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
               "compatible": "PHYSIS_COMPATIBLE_API_KEY"}.get(provider)
    if endpoint_key:
        if not endpoint_env or not os.environ.get(endpoint_env):
            raise EvaluationError(f"Profile requires configured endpoint env var {endpoint_env or endpoint_key}.")
        changes[endpoint_key] = os.environ[endpoint_env]
    if key_key and provider != "compatible":
        source = key_env or key_key
        if not os.environ.get(source):
            raise EvaluationError(f"Profile requires its API key in environment variable {source}.")
        if source != key_key:
            changes[key_key] = os.environ[source]
    elif provider == "compatible":
        if key_env:
            if not os.environ.get(key_env):
                raise EvaluationError(f"Profile requires its API key in environment variable {key_env}.")
            changes[key_key] = os.environ[key_env]
        else:
            # Keyless compatible endpoints must not inherit a global credential.
            changes[key_key] = ""
    old = {key: os.environ.get(key) for key in changes}
    try:
        os.environ.update(changes)
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _case_hash(case: dict) -> str:
    return _sha_bytes(_canonical({"id": case["id"], "question": case["question"],
                                  "level": case["level"], "model": case["model"],
                                  "patch": case["patch"], "prior": case["prior"]}))


def output_origin(output: dict | None, provider: str, request_count: int,
                  replay_used: bool = False) -> str:
    """Label the source of an attempt without inferring performance or model use."""
    if replay_used:
        return "replay"
    pending = [output] if isinstance(output, dict) else []
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if value.get("origin") == "replay":
                return "replay"
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    if provider == "mock":
        return "mock"
    if request_count > 0:
        return "actual_provider"
    return "no_provider_call"


def annotate_output_origin(output: dict, origin: str) -> None:
    """Persist provenance without presenting Mock/replay time as model latency."""
    output["origin"] = origin

    def visit(value):
        if isinstance(value, dict):
            if {"provider", "model", "requests"}.issubset(value):
                if origin == "replay":
                    value["provider"] = "replay"
                    value["model"] = None
                    value["latency_ms"] = None
                    for request in value.get("requests", []):
                        if isinstance(request, dict):
                            request["latency_ms"] = None
                elif origin == "mock":
                    value["provider"] = "mock"
                    value["latency_ms"] = None
                elif origin == "no_provider_call":
                    value["provider"] = None
                    value["model"] = None
                    value["latency_ms"] = None
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(output)


def _stored_origin(row, payload: dict) -> str:
    origin = row["origin"]
    if origin in RESULT_ORIGINS:
        return origin
    # Older runner databases used `live` as a default. Reclassify from persisted
    # request receipts so exports never imply a real model request for replay or
    # deterministic Mock output.
    if row["arm"] == "B (ARCHIVED)":
        return "archived_baseline"
    if output_origin(payload, "mock" if row["provider_config"] == "mock" else "unknown",
                     int(row["request_count"])) == "replay":
        return "replay"
    if int(row["request_count"]) > 0:
        return "actual_provider"
    if row["provider_config"] == "mock":
        return "mock"
    return "no_provider_call"


def _snapshot_for(case: dict):
    from physis.api import snapshot
    from physis.physics import SPECS
    from physis.schema import Patch
    from physis.state import build

    model = case.get("model") or "uniform"
    if model not in SPECS:
        raise EvaluationError(f"Case {case['id']} uses an unknown experiment model.")
    experiment = build(SPECS[model], uuid.uuid4(), Patch.model_validate(case.get("patch") or {}))
    return snapshot(experiment, 1, case["level"]).model_dump(mode="json")


async def _run_arm(arm: str, case: dict, profile_name: str, profile: dict, app,
                   store: ProgressStore, invocation_id: str, run_id: str,
                   transport=None) -> dict:
    from physis.evaluation_guard import generation_guard
    from physis.provider_config import ProviderSelection, provider_context

    provider = profile["provider"]
    selection = ProviderSelection(provider=provider, model=profile["model"])
    reserve = lambda operation: store.reserve_requests(
        invocation_id, operation, 1, profile_name, arm, case["id"])
    history_mode = "previous_question_only" if case.get("prior") else "none"

    async def invoke():
        from physis.providers import replay_context

        replay_scope = replay_context(transport) if transport is not None else None
        if replay_scope is None:
            from contextlib import nullcontext
            replay_scope = nullcontext()
        with provider_context(selection) as metrics, generation_guard(reserve), replay_scope:
            if arm == "A":
                from physis.providers import request_explanation

                # Raw answer arm: same question and level, without router, RAG, or engine context.
                answer = await request_explanation(
                    provider, {"question": case["question"], "level": case["level"]},
                    transport=transport)
                result = {"text": answer.text, "source_ids": answer.source_ids,
                          "assumptions": answer.assumptions, "uncertainty": answer.uncertainty}
            elif arm in {"C", "D", "E"}:
                from physis.cognitive import ablation_turn

                snapshot = _snapshot_for(case)
                history = ([{"question": case["prior"]}] if case.get("prior") else ())
                result = await ablation_turn(arm, case["question"], snapshot, app.state.knowledge,
                                             level=case["level"], history=history,
                                             provider=provider, transport=transport)
            elif arm == "F":
                # Call the real tutor route through ASGI in this process. This
                # preserves provider guard context and does not open a network socket.
                import httpx

                asgi = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=asgi, base_url="http://testserver") as client:
                    created = await client.post("/api/experiments", json={
                        "model": case.get("model") or "uniform", "level": case["level"],
                        "patch": case.get("patch") or {},
                    })
                    if not created.is_success:
                        raise EvaluationError(f"F setup failed with HTTP {created.status_code}.")
                    initial = created.json()
                    body = {"experiment_id": initial["experiment"]["id"],
                            "revision": initial["revision"], "message": case["question"],
                            "mode": "explain", "level": case["level"],
                            "selection": selection.model_dump(mode="json")}
                    if case.get("prior"):
                        body["previous_question"] = case["prior"]
                    response = await client.post("/api/tutor/stream", json=body)
                    if not response.is_success:
                        raise EvaluationError(f"F tutor route returned HTTP {response.status_code}.")
                    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
                    final = next((event for event in reversed(events)
                                  if event.get("event") in {"result", "error"}), None)
                    if final is None:
                        raise EvaluationError("F tutor stream did not return a result event.")
                    after = await client.get(f"/api/experiments/{initial['experiment']['id']}")
                    after_json = after.json() if after.is_success else None
                    result = {"events": events, "final_event": final,
                              "experiment_before": initial, "experiment_after": after_json,
                              "state_change": bool(after_json and
                                  (after_json.get("revision") != initial.get("revision") or
                                   after_json.get("experiment") != initial.get("experiment"))),
                              "history_mode": history_mode,
                              "followup_comparable": not bool(case.get("prior")),
                              "provider_requests": final.get("metrics", {}).get("requests", [])}
            else:
                raise EvaluationError(f"Unsupported arm {arm}.")
        result.setdefault("provider_metrics", metrics.as_dict())
        result["trust_label"] = TRUST_LABEL
        return result

    remaining = store.remaining_seconds(invocation_id)
    async with asyncio.timeout(remaining):
        result = await invoke()
    result.setdefault("history_mode", history_mode)
    return result


async def _execute(profiles: dict[str, dict], arms: tuple[str, ...], cases: list[dict],
                   config: dict, store: ProgressStore, run_id: str, invocation_id: str,
                   retries: int, retry_interrupted: bool, replay_provider=None) -> int:
    from physis.api import create_app

    app_dir = store.path.parent / f"{run_id}.appdata"
    app_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PHYSIS_DATA_DIR"] = str(app_dir)
    os.environ["PHYSIS_AI_PROVIDER"] = "mock"
    app = create_app(app_dir / "experiments.sqlite3")
    store.recover_interrupted(run_id)
    attempted = 0
    async with app.router.lifespan_context(app):
        for profile_name, profile in profiles.items():
            with provider_environment(profile):
                for arm in arms:
                    for case in cases:
                        latest = store.latest_case(run_id, profile_name, arm, case["id"])
                        if latest and latest["status"] == "ok":
                            continue
                        if latest and latest["status"] == "interrupted" and not retry_interrupted:
                            continue
                        attempts_so_far = int(latest["attempt"]) if latest else 0
                        attempts_allowed = 1 + retries
                        if latest and latest["status"] != "ok" and attempts_so_far >= attempts_allowed:
                            continue
                        while attempts_so_far < attempts_allowed:
                            if store.remaining_seconds(invocation_id) <= 0:
                                raise BudgetExceeded("Wall-time budget expired.")
                            store.begin_case(run_id, profile_name, arm, case["id"], _case_hash(case))
                            transport = None
                            try:
                                transport = replay_provider(profile_name, arm, case) if replay_provider else None
                                output = await _run_arm(arm, case, profile_name, profile, app,
                                                         store, invocation_id, run_id, transport)
                                origin = output_origin(
                                    output, profile["provider"],
                                    store.current_case_request_count(run_id, profile_name, arm, case["id"]),
                                    replay_used=transport is not None and transport.consumed)
                                annotate_output_origin(output, origin)
                                result_event = output.get("final_event") if arm == "F" else None
                                status = "error" if result_event and result_event.get("event") == "error" else "ok"
                                store.finish_case(run_id, profile_name, arm, case["id"], status, output,
                                                  origin=origin)
                            except (TimeoutError, asyncio.CancelledError):
                                origin = output_origin(
                                    None, profile["provider"],
                                    store.current_case_request_count(run_id, profile_name, arm, case["id"]),
                                    replay_used=transport is not None and transport.consumed)
                                store.finish_case(run_id, profile_name, arm, case["id"], "error", None,
                                                  "wall_time_budget_exceeded", origin=origin)
                                if isinstance(sys.exc_info()[1], asyncio.CancelledError):
                                    raise
                            except Exception as exc:
                                origin = output_origin(
                                    None, profile["provider"],
                                    store.current_case_request_count(run_id, profile_name, arm, case["id"]),
                                    replay_used=transport is not None and transport.consumed)
                                store.finish_case(run_id, profile_name, arm, case["id"],
                                                  "budget_exhausted" if isinstance(exc, BudgetExceeded) else "error",
                                                  None, f"{type(exc).__name__}: {exc}"[:600], origin=origin)
                                if isinstance(exc, BudgetExceeded):
                                    raise
                            attempted += 1
                            attempts_so_far += 1
                            latest = store.latest_case(run_id, profile_name, arm, case["id"])
                            if latest["status"] == "ok":
                                break
    return attempted


def _provider_context_for_mock_replay(profiles: dict[str, dict], replay_file: Path | None):
    if replay_file is None:
        return None
    if any(profile["provider"] != "mock" for profile in profiles.values()):
        raise EvaluationError("Replay requires exclusively Mock profiles.")
    from physis.providers import ReplayTransport

    fixtures = {}
    for line in replay_file.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            fixtures[(row["provider_config"], row["arm"], row["case_id"])] = row["content"]

    def factory(profile_name, arm, case):
        if profiles[profile_name]["provider"] != "mock":
            return None
        key = (profile_name, arm, case["id"])
        if key not in fixtures:
            raise EvaluationError(f"Replay fixture missing for {key}.")
        return ReplayTransport(content=fixtures[key])
    return factory


def execute_run(args) -> int:
    if args.max_requests_per_invocation is None or args.max_requests_total is None \
            or args.max_seconds_per_invocation is None or args.max_seconds_total is None:
        raise EvaluationError("--execute requires per-invocation and cumulative request and wall-time budgets.")
    if not (1 <= args.max_requests_per_invocation <= MAX_REQUESTS_HARD_CAP
            and 1 <= args.max_requests_total <= MAX_REQUESTS_HARD_CAP
            and 1 <= args.max_seconds_per_invocation <= MAX_SECONDS_HARD_CAP
            and 1 <= args.max_seconds_total <= MAX_SECONDS_HARD_CAP):
        raise EvaluationError("Budgets must be positive and within the runner hard caps.")
    config = load_config(args.config)
    profiles = select_profiles(config, args.profiles.split(",") if args.profiles else None)
    arms = selected_arms(config, args.arms)
    cases = load_cases(args.cases, config.get("default_experiment_model"))
    input_id = _sha_file(args.cases)
    cfg_id = _config_id(profiles, arms, config, _runtime_binding(profiles, args.replay))
    prod_id = product_id()
    run_id = args.run_id or f"{input_id[:8]}-{cfg_id[:8]}-{prod_id[:8]}"
    with ProgressLock(args.progress):
        store = ProgressStore(args.progress)
        try:
            store.create_run(run_id, input_id, cfg_id, prod_id,
                             args.max_requests_total, args.max_seconds_total)
            invocation_id = f"{run_id[:48]}-{uuid.uuid4().hex[:12]}"
            store.begin_invocation(invocation_id, args.max_requests_per_invocation,
                                   args.max_seconds_per_invocation, run_id)
            replay_factory = _provider_context_for_mock_replay(profiles, args.replay)
            count = asyncio.run(_execute(profiles, arms, cases, config, store, run_id,
                                         invocation_id, args.retries, args.retry_interrupted,
                                         replay_factory))
            print(json.dumps({"run_id": run_id, "attempted_cases": count,
                              "request_count": store.request_usage(run_id),
                              "progress": str(args.progress), "product_id": prod_id}, ensure_ascii=False))
            return 0
        finally:
            store.close()


def import_archived_b(progress: Path, archive: Path) -> int:
    data = json.loads(archive.read_text(encoding="utf-8-sig"))
    rows = data.get("arms", {}).get("B", {}).get("rows")
    if not isinstance(rows, list):
        raise EvaluationError("Archive does not contain arms.B.rows; only saved B results can be imported.")
    archive_hash = _sha_file(archive)
    run_id = f"archived-b-{archive_hash[:12]}"
    with ProgressLock(progress):
      store = ProgressStore(progress)
      try:
        store.create_run(run_id, archive_hash, archive_hash, str(data.get("model_digest", "v0.3.1")), 0, 1)
        for row in rows:
            case_id = row.get("case_id")
            if not case_id:
                continue
            events = row.get("events", [])
            result = next((event.get("result") for event in reversed(events)
                           if event.get("event") == "result"), None)
            error = row.get("error") or next((event.get("detail") for event in reversed(events)
                                               if event.get("event") == "error"), None)
            payload = {"archive_label": "ARCHIVED B (v0.3.1); saved output, not a live run",
                       "question": row.get("question"), "result": result,
                       "event": row.get("event"), "error": error,
                       "origin": "archived_baseline",
                       "trust_label": TRUST_LABEL}
            store.db.execute(
                "INSERT OR REPLACE INTO case_results(run_id,provider_config,arm,case_id,attempt,question_hash,"
                "status,started_at,finished_at,request_count,output_json,error,origin) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, "archived-v0.3.1", "B (ARCHIVED)", case_id, 1,
                 _sha_bytes((row.get("question") or "").encode()),
                 "ok" if result else "error", _now(), _now(), 0,
                 json.dumps(payload, ensure_ascii=False), error, "archived_baseline"))
        print(f"Imported {len(rows)} saved B rows as archived-v0.3.1 into {progress}.")
        return 0
      finally:
        store.close()


def compare_results(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        if not path.is_file():
            raise EvaluationError(f"Progress database does not exist: {path}")
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            data = db.execute("SELECT * FROM case_results ORDER BY provider_config,arm,case_id,attempt").fetchall()
        except sqlite3.Error as exc:
            raise EvaluationError(f"Not a runner progress database: {path}") from exc
        finally:
            db.close()
        latest = {}
        for row in data:
            key = (row["run_id"], row["provider_config"], row["arm"], row["case_id"])
            if key not in latest or row["attempt"] > latest[key]["attempt"]:
                latest[key] = row
        for row in latest.values():
            payload = json.loads(row["output_json"]) if row["output_json"] else {}
            if row["arm"] == "B (ARCHIVED)":
                text = ((payload.get("result") or {}).get("message")
                        if isinstance(payload.get("result"), dict) else None)
                if not text:
                    text = payload.get("error") or ""
            else:
                final = payload.get("final_event") or {}
                result = final.get("result") or {}
                text = payload.get("text") or result.get("message") or ""
            rows.append({"run_id": row["run_id"], "provider_config": row["provider_config"],
                         "arm": row["arm"], "case_id": row["case_id"], "status": row["status"],
                         "request_count": row["request_count"], "text": text,
                         "origin": _stored_origin(row, payload), "trust_label": TRUST_LABEL})
    return sorted(rows, key=lambda r: (r["provider_config"], r["arm"], r["case_id"], r["run_id"]))


def _write_compare(rows: list[dict], output: Path | None, fmt: str) -> None:
    if fmt == "json":
        text = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    else:
        from io import StringIO
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=("run_id", "provider_config", "arm", "case_id",
                                                   "status", "request_count", "origin", "text", "trust_label"))
        writer.writeheader()
        writer.writerows(rows)
        text = buffer.getvalue()
    if output:
        output.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Plan by default; execute only with explicit flags and budgets.")
    run.add_argument("--cases", type=Path, required=True)
    run.add_argument("--config", type=Path)
    run.add_argument("--progress", type=Path, required=True)
    run.add_argument("--profiles", help="Comma-separated named provider configs; default is all.")
    run.add_argument("--arms", help="Comma-separated live arms (A,C,D,E,F); default from config.")
    run.add_argument("--run-id")
    run.add_argument("--execute", action="store_true", help="Required to make provider requests.")
    run.add_argument("--max-requests-per-invocation", type=int)
    run.add_argument("--max-seconds-per-invocation", type=float)
    run.add_argument("--max-requests-total", type=int)
    run.add_argument("--max-seconds-total", type=float)
    run.add_argument("--retries", type=int, default=0)
    run.add_argument("--retry-interrupted", action="store_true")
    run.add_argument("--replay", type=Path, help="Offline ReplayTransport JSONL fixture for a Mock profile.")
    compare = sub.add_parser("compare", help="Compare saved progress databases; performs no provider calls.")
    compare.add_argument("--progress", type=Path, nargs="+", required=True)
    compare.add_argument("--format", choices=("csv", "json"), default="csv")
    compare.add_argument("--output", type=Path)
    archive = sub.add_parser("import-b", help="Import saved v0.3.1 B rows; does not run the archive.")
    archive.add_argument("--archive", type=Path, required=True)
    archive.add_argument("--progress", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            if args.retries < 0 or args.retries > 1:
                raise EvaluationError("--retries must be 0 or 1.")
            config = load_config(args.config)
            profiles = select_profiles(config, args.profiles.split(",") if args.profiles else None)
            arms = selected_arms(config, args.arms)
            cases = load_cases(args.cases, config.get("default_experiment_model"))
            plan = build_plan(cases, profiles, arms)
            if not args.execute:
                print("DRY RUN — no provider requests or progress writes.")
                print(json.dumps({"cases": len(cases), "provider_configs": list(profiles),
                                  "arms": arms, "planned_rows": len(plan),
                                  "progress_path": str(args.progress),
                                  "note": "B is imported from a saved file only; outputs remain untrusted."},
                                 ensure_ascii=False))
                return 0
            return execute_run(args)
        if args.command == "compare":
            rows = compare_results(args.progress)
            _write_compare(rows, args.output, args.format)
            return 0
        if args.command == "import-b":
            return import_archived_b(args.progress, args.archive)
    except EvaluationError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
