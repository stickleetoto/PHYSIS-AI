"""Frontend lesson presets must stay aligned with the real physics registry."""
import json
from pathlib import Path

from physis.physics import SPECS


PRESETS_PATH = Path(__file__).parents[2] / "frontend" / "src" / "learning-presets.json"


def test_every_registered_model_has_a_valid_learning_preset():
    rows = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    assert len(rows) == len(SPECS) == 23
    assert len({row["model"] for row in rows}) == len(rows)
    assert {row["model"] for row in rows} == set(SPECS)

    for row in rows:
        spec = SPECS[row["model"]]
        assert row["title"].strip()
        assert row["objective"].strip()
        assert row["expectedRelation"].strip()
        assert row["observationQuestion"].strip()
        assert row["observations"]
        assert set(row["observations"]) <= set(spec.measurements)
        assert spec.assumptions

        # The UI builds its initialValues directly from these live catalog defaults.
        defaults = {variable.key: variable.default for variable in spec.variables}
        assert set(defaults) == {variable.key for variable in spec.variables}
        for variable in spec.variables:
            assert variable.min <= defaults[variable.key] <= variable.max

