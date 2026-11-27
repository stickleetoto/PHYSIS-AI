import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from physis import math_lab_api as lab


@pytest.mark.parametrize("change", [
    {"params": {"z": 1}}, {"point": float("nan")}, {"divisions": 65}, {"step": 0},
    {"hi": -10}, {"expression": "x" * 181}, {"lower": 1001}, {"unexpected": True},
])
def test_rejects_inputs_outside_experiment_contract(change):
    with pytest.raises(ValidationError):
        lab.LabRequest.model_validate({"mode": "function", "expression": "x", **change})


@pytest.mark.parametrize("cancel,ready,expected", [(False,True,"계산 시간 제한"),
                        (False,False,"시작 시간 제한"), (True,True,"취소")])
def test_timeout_and_disconnect_stop_and_reap_worker(monkeypatch, tmp_path, cancel, ready, expected):
    script = tmp_path / "waiting_worker.py"
    script.write_text("import time\n"+("print('READY', flush=True)\n" if ready else "")+"time.sleep(10)\n", encoding="utf8")
    monkeypatch.setattr(lab, "WORKER", script)
    monkeypatch.setattr(lab, "TIME_LIMIT", 0.12)
    monkeypatch.setattr(lab, "STARTUP_LIMIT", 2 if ready else 0.15)
    original = lab.subprocess.Popen
    children = []

    def record(*args, **kwargs):
        process = original(*args, **kwargs)
        children.append(process)
        return process

    class Connection:
        async def is_disconnected(self):
            return cancel

    monkeypatch.setattr(lab.subprocess, "Popen", record)
    result = asyncio.run(lab.calculate_lab(Connection(), lab.LabRequest(mode="function", expression="x")))
    assert expected in result["detail"]
    assert children and all(child.poll() is not None for child in children)
    assert lab._slots.acquire(blocking=False)
    lab._slots.release()
