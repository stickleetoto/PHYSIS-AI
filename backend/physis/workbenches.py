"""Independent experiment inputs in a bounded, local comparison workspace."""
from contextlib import closing
import json
from math import isclose
import sqlite3
from uuid import UUID

from fastapi import HTTPException

from .state import RevisionConflict
from .science_language import FACTS as SCIENCE_FACTS


class Workbenches:
    def __init__(self, store):
        self.store = store

    def initialize(self):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS bench_members(
                    member TEXT PRIMARY KEY, anchor TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    UNIQUE(anchor, ordinal));
                CREATE TABLE IF NOT EXISTS provider_usage(
                    id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    outcome TEXT NOT NULL, metrics TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS local_generation(epoch INTEGER NOT NULL);
                INSERT INTO local_generation SELECT 0 WHERE NOT EXISTS(SELECT 1 FROM local_generation);
            """)

    @staticmethod
    def _members(db, member):
        found = db.execute("SELECT anchor FROM bench_members WHERE member=?", (str(member),)).fetchone()
        if not found:
            return str(member), [str(member)]
        ids = db.execute("SELECT member FROM bench_members WHERE anchor=? ORDER BY ordinal", found).fetchall()
        return found[0], [row[0] for row in ids]

    def members(self, member):
        with closing(sqlite3.connect(self.store.path)) as db:
            anchor, ids = self._members(db, member)
        return UUID(anchor), list(map(UUID, ids))

    def attach(self, source, revision, exp, level):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            found = db.execute("SELECT revision FROM experiments WHERE id=?", (str(source),)).fetchone()
            if not found or found[0] != revision:
                raise RevisionConflict()
            anchor, ids = self._members(db, source)
            if len(ids) >= 4:
                raise HTTPException(409, "비교 실험은 최대 4개입니다. 비교에서 한 개를 빼고 다시 시도하세요.")
            db.execute("INSERT OR IGNORE INTO bench_members VALUES (?, ?, 0)", (anchor, anchor))
            slot = db.execute("SELECT MAX(ordinal)+1 FROM bench_members WHERE anchor=?", (anchor,)).fetchone()[0]
            self.store.write(db, exp, level, 0)
            db.execute("INSERT INTO bench_members VALUES (?, ?, ?)", (str(exp.id), anchor, slot))

    def detach(self, source, member):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            anchor, ids = self._members(db, source)
            if str(member) not in ids or str(member) == anchor:
                raise HTTPException(422, "기준 실험은 유지하며 비교에 추가한 실험만 제외할 수 있습니다.")
            db.execute("DELETE FROM bench_members WHERE member=? AND anchor=?", (str(member), anchor))

    def generation(self):
        with closing(sqlite3.connect(self.store.path)) as db:
            return db.execute("SELECT epoch FROM local_generation").fetchone()[0]

    def create_from(self, source, revision, exp, level):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT revision FROM experiments WHERE id=?", (str(source),)).fetchone()
            if prior != (revision,):
                raise RevisionConflict()
            self.store.write(db, exp, level, 0)

    def usage(self, metrics=None, outcome=None, generation=None):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            if metrics is not None:
                db.execute("INSERT INTO provider_usage (metrics,outcome) SELECT ?,? FROM local_generation WHERE epoch=?",
                           (json.dumps(metrics, ensure_ascii=False, allow_nan=False), outcome, generation))
                return
            rows = db.execute("SELECT created_at,outcome,metrics FROM provider_usage ORDER BY id DESC LIMIT 30").fetchall()
            return [dict(json.loads(data), created_at=stamp + "Z", outcome=status) for stamp, status, data in rows]

    def export_learning(self):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            experiments = [dict(row) for row in db.execute("SELECT * FROM experiments ORDER BY rowid")]
            for experiment in experiments:
                experiment["inputs"] = json.loads(experiment["inputs"])
            memberships = [dict(row) for row in db.execute("SELECT * FROM bench_members ORDER BY anchor,ordinal")]
            usage = [dict(json.loads(row["metrics"]), created_at=row["created_at"] + "Z", outcome=row["outcome"])
                     for row in db.execute("SELECT * FROM provider_usage ORDER BY id")]
            return {"experiments": experiments, "workbenches": memberships, "usage": usage}

    def erase_learning(self):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE local_generation SET epoch=epoch+1")
            for table in ("bench_members", "provider_usage", "experiments"):
                db.execute(f"DELETE FROM {table}")


FACTS = [
    ("arrival_time", "도착 시간", "s"), ("measured_period", "측정 주기", "s"),
    ("stop_distance", "정지 거리", "m"), ("energy_loss", "충돌 에너지 손실", "J"),
    ("final_position", "마지막 위치", "m"), ("gauge_pressure", "게이지압", "Pa"),
    ("buoyancy", "부력", "N"), ("outlet_speed", "출구 유속", "m/s"),
    *((key, label, unit) for key, (label, unit) in SCIENCE_FACTS.items()),
]

MEASUREMENTS = {
    "displacement":"원점 변위", "quarter_displacement":"¼ 파장 지점 변위", "temperature":"온도",
    "pressure":"압력", "speed":"속력", "angle":"각도", "y":"높이", "x":"수평 위치",
    "vx":"수평 속도", "vy":"수직 속도", "energy":"역학적 에너지", "flow":"유량",
    "fx":"수평 힘", "fy":"수직 힘", "error":"기준해 오차",
}


def difference_at_common_samples(first, second):
    """Compare recorded instants shared by both grids, including different end times."""
    a, b, exp = first.run, second.run, first.experiment
    by_time = {round(t, 10): i for i, t in enumerate(b.times)}
    pairs = [(i, by_time[key]) for i, t in enumerate(a.times) if (key := round(t, 10)) in by_time]
    if not pairs:
        return ""
    for q, label in MEASUREMENTS.items():
        for index, name in enumerate(exp.objects):
            k = f"{index}.{q}"
            if k not in a.series or k not in b.series:
                continue
            left, right = a.series[k], b.series[k]
            i, j = max(pairs, key=lambda p: abs(right[p[1]] - left[p[0]]))
            if not isclose(left[i], right[j], rel_tol=1e-10, abs_tol=1e-12):
                unit = exp.measurements[q]
                return (f"같은 시각의 표본 중 {name}의 {label} 차이가 가장 큰 시각은 {a.times[i]:.5g} s입니다. "
                        f"기준 {left[i]:.5g} {unit}, 비교 {right[j]:.5g} {unit}입니다.")
    return ""


def comparison_text(first, second):
    a, b = first.run, second.run
    if "FAILED" in {a.status, b.status}:
        return "두 실행 중 검증에 실패한 결과가 있습니다. 두 조건의 물리적 차이를 해석하기 전에 실패한 검사를 확인하세요."
    if first.experiment.model != second.experiment.model:
        return "서로 다른 모델입니다. 단위와 측정 정의가 일치하는 물리량을 선택해 공통 시간 구간을 살펴보세요."
    sample_difference = difference_at_common_samples(first, second)
    for key, label, unit in FACTS:
        if key in a.facts and key in b.facts:
            x, y = a.facts[key], b.facts[key]
            summary = f"기준 실험의 {label}은 {x:.5g} {unit}, 비교 실험은 {y:.5g} {unit}입니다. 차이(비교 − 기준)는 {y-x:.5g} {unit}입니다."
            return (summary + " " + sample_difference).strip()
    if sample_difference:
        return sample_difference
    exp = first.experiment
    quantity = next((key for key in exp.measurements if "0."+key in a.series and "0."+key in b.series), None)
    if quantity:
        x, y = a.series["0."+quantity][0], b.series["0."+quantity][0]
        return f"같은 시작 시각 0 s에서 {quantity} 측정값은 각각 {x:.5g}, {y:.5g} {exp.measurements[quantity]}입니다. 시간에 따른 차이는 비교 그래프에서 확인하세요."
    return "두 실험의 측정 표본을 비교 그래프에서 확인하세요."
