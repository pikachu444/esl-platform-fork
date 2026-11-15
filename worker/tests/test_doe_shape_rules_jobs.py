"""V-SH-13(워커 부분)·V-SH-14(워커 회귀) — v0.21.0 형상 규칙: 새 스냅샷 ① 준비 = range_guard.json(실제 코어), 옛 스냅샷(키 없음) = 새 키 없음,
작업 결과 range_guard 요약 통과, ④ 준비 등록 route·mq 키 통과(옛 행은 뺌), ③ 준비 mesh.route·quality 통과. 실제 PG·워커·코어(스텁 없음),
가짜 paicad, 합성 비드 메시."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from doe_worker_support import doe_worker_settings, set_control, write_fake_paicad
from esl_test_support import REPO
from test_doe_select_jobs import create_select, make_bead_case, run_job, study

sys.path.insert(0, str(REPO / "tests" / "doe"))

pytestmark = [pytest.mark.skipif(os.name == "nt", reason="가짜 paicad 는 POSIX 실행 스크립트"), pytest.mark.select_schema2]
RG = "range_guard.json"


@pytest.fixture()
def exe(tmp_path):
    return write_fake_paicad(tmp_path)


@pytest.fixture()
def settings_dict(tmp_path, exe, request):
    sr = getattr(request, "param", None)
    return doe_worker_settings(tmp_path, exe, **({"shape_rules": sr} if sr else {}))


@pytest.fixture()
def worker(worker_factory, exe):
    set_control(exe, rules=[])
    w = worker_factory()
    w.heartbeat_once()
    return w


def prep_dir(esl_root: Path, sid: str) -> Path:
    return esl_root / "_doe" / sid / "prep"


def _graph_ok(esl_root: Path, sid: str) -> bool:
    return (prep_dir(esl_root, sid) / "select" / "graph.json").is_file()


# ================================================================ ① 준비(새 스냅샷 / 옛 스냅샷)
def _rg_state(j: dict, g: dict, esl_root: Path, sid: str) -> str:
    """준비 결과: file(range_guard.json 있음) | failed(경고 RG_FAILED — 코어 점검 예외) | none."""
    sd = prep_dir(esl_root, sid) / "select"
    txt = json.dumps([j.get("warnings"), g["prep"].get("warnings")], ensure_ascii=False)
    if (sd / RG).is_file():
        return "file"
    return "failed" if "RG_FAILED" in txt else "none"


def test_new_snapshot_prep_writes_range_guard(client, engine, worker, esl_root, inputs_root):
    """새 스터디: 스냅샷·inputs 에 shape_rules 블록, 준비 READY, w_clamp.json 은 안 씀, 실제 코어 점검 → range_guard.json(RG_FAILED 없음)."""
    w = make_bead_case(engine, esl_root, inputs_root)
    s = create_select(client, w["entry_ids"])
    assert s["inputs"]["shape_rules"]["schema"] == 1 and s["inputs"]["shape_rules"]["mesh_route"]["relaxed_direct"]["min_faces"] == 1500
    j = run_job(client, worker, s["job"]["id"])
    g = study(client, s["id"])
    assert g["phase"] == "READY"
    assert _graph_ok(esl_root, s["id"])
    assert not (prep_dir(esl_root, s["id"]) / "select" / "w_clamp.json").exists()
    assert _rg_state(j, g, esl_root, s["id"]) == "file"
    doc = json.loads((prep_dir(esl_root, s["id"]) / "select" / RG).read_text(encoding="utf-8"))
    assert doc["schema"] == "esl/range_guard/1" and doc["scope"] == "prep"


@pytest.mark.parametrize("settings_dict", [{"enabled": False}], indirect=True, ids=["shape_rules_off"])
def test_old_snapshot_has_no_shape_keys(client, engine, worker, esl_root, inputs_root):
    """설정 shape_rules.enabled false(= 키 없는 옛 스냅샷): inputs 에 키 없음, range_guard.json·RG_FAILED 없음(v0.20.0 준비 그대로)."""
    w = make_bead_case(engine, esl_root, inputs_root)
    s = create_select(client, w["entry_ids"])
    assert "shape_rules" not in s["inputs"]
    j = run_job(client, worker, s["job"]["id"])
    g = study(client, s["id"])
    assert g["phase"] == "READY" and _rg_state(j, g, esl_root, s["id"]) == "none"
    assert "range_guard" not in json.dumps(g["prep"]) and "shape_rules" not in json.dumps(g["prep"])


# ================================================================ 결과 키·등록 단위
def test_summary_passes_range_guard_only_when_present():
    from esl_worker import doe_jobs as dj
    rg = {"entries": 3, "limited": 1, "blocked": 0, "combos": 0, "evals": 9, "seconds": 0.1, "stopped": None}
    assert dj._summary({"range_guard": rg, "n_designs": 3})["range_guard"] == rg
    assert "range_guard" not in dj._summary({"n_designs": 3})


def _write(p: Path, doc: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="utf-8")


def test_register_step_prep_passes_route_quality():
    from esl_worker import register as rg
    s = {"inputs": {"select_base": "step"}}
    fixed = {"source": "scan", "n": 3}
    mesh = {"n_nodes": 10, "n_elems": 8, "tri_frac": 0.1,
            "route": {"path": "cad_relaxed", "reason": ["faces"], "n_faces": 2800, "min_faces": 1500},
            "quality": {"fail_ratio": 0.12, "tria_pct": 4.0}}
    out = rg._select_step_prep(s, {"mesh": mesh, "step": {"file_name": "a.step"}}, fixed)
    assert out["mesh"]["route"]["path"] == "cad_relaxed" and out["mesh"]["quality"]["fail_ratio"] == 0.12
    out0 = rg._select_step_prep(s, {"mesh": {"n_nodes": 10, "n_elems": 8, "tri_frac": 0.1}, "step": {"file_name": "a.step"}}, fixed)
    assert "route" not in out0["mesh"] and "quality" not in out0["mesh"]            # 옛 준비 요약 키 불변


def test_compare_shape_keys_route_mq():
    from esl_worker import register as rg
    assert rg.COMPARE_SHAPE_KEYS[-2:] == ("route", "mq")
    assert rg.COMPARE_SHAPE_KEYS.count("route") == 1 and len(set(rg.COMPARE_SHAPE_KEYS)) == len(rg.COMPARE_SHAPE_KEYS)
