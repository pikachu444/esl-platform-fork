"""V-SH-15 (esl_bead_shape_v021.md): shape_rules 설정 4곳 거울(DEFAULTS·pydantic·yaml 2개)·스냅샷/inputs 블록·settings 노출·openapi."""

from __future__ import annotations

import json

import pytest
import yaml
from esl_test_support import REPO


def _flat(d, p=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, f"{p}{k}."))
        else:
            out[f"{p}{k}"] = v
    return out


def test_shape_rules_four_way_mirror():
    from esl.doe import DEFAULTS
    from esl_platform.core.config import BeadDoeCfg

    core = DEFAULTS["shape_rules"]
    assert BeadDoeCfg().model_dump()["shape_rules"] == core
    for p in ("esl_platform.example.yaml", "esl_platform.prod.example.yaml"):
        y = yaml.safe_load((REPO / "config" / p).read_text(encoding="utf-8"))
        got = BeadDoeCfg.model_validate(y["bead_doe"]).model_dump()["shape_rules"]
        assert _flat(got) == _flat(core), p
        assert _flat(y["bead_doe"]["shape_rules"]).keys() <= _flat(core).keys(), p


def test_shape_snapshot_and_settings():
    from esl.doe import DEFAULTS
    from esl_platform.api.services import doe as svc
    from esl_platform.core.config import BeadDoeCfg

    c = BeadDoeCfg().model_dump()
    snap = svc.shape_snapshot(c)
    assert snap["schema"] == 1 and "budget" in snap["range_guard"]
    assert snap["range_guard"]["flip_deg"] == DEFAULTS["select"]["quality"]["flip_deg"]
    ss = svc._shape_settings(c)
    assert ss["range_guard"] == {"enabled": True} and ss["mesh_route"]["relaxed_direct"]["min_faces"] == 1500
    off = BeadDoeCfg.model_validate({"shape_rules": {"enabled": False}}).model_dump()
    assert svc.shape_snapshot(off) is None
    bad = BeadDoeCfg().model_dump()
    bad["shape_rules"]["range_guard"]["jac_min"] = 2.0
    with pytest.raises(Exception) as ei:
        svc.shape_snapshot(bad)
    assert ei.type.__name__ == "DomainError" and "CONFIG_INVALID" in str(ei.value)


def test_openapi_has_shape_rules():
    doc = json.loads((REPO / "docs" / "contracts" / "openapi_p1b.json").read_text(encoding="utf-8"))
    assert "shape_rules" in doc["components"]["schemas"]["DoeSettingsOut"]["properties"]
