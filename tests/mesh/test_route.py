"""V-SH-5·6 — 메싱 경로 선택·메시 품질 순위 경고 ``esl.mesh.route``(계약 esl_bead_shape_v021.md §5.1·§5.4).

면 경계값(1499/1500), n_faces None, min_step_mb, relaxed 꺼짐·enabled false → cad, Fail·tria 경계값·tria null 해석값,
그리고 독립성(AST — esl.doe·gmsh import 없음, open·DEFAULTS·전역 난수 없음). 기준값은 시험 설정(DEFAULTS 해석)에서."""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "doe"))

import synth_guard as sg  # noqa: E402
from esl.doe import DEFAULTS  # noqa: E402
from esl.mesh import route  # noqa: E402

SRC = os.path.join(HERE, "..", "..", "esl", "mesh", "route.py")
RU = sg.rules()
RD = RU["mesh_route"]["relaxed_direct"]
RQ = RU["mesh_route"]["rank_quality"]
MF = int(RD["min_faces"])


def test_defaults_resolved():
    assert MF == 1500 and RD["min_step_mb"] is None and RD["enabled"] is True        # Q-SH-2
    assert RQ["fail_ratio"] == 0.10
    assert RQ["tria_pct"] == float(DEFAULTS["compare"]["quality"]["tria_pct"]["fail"])  # null → compare 기준 해석


def test_faces_boundary():
    a = route.choose(MF - 1, None, RD, relaxed_enabled=True)
    b = route.choose(MF, None, RD, relaxed_enabled=True)
    assert a["path"] == "cad" and a["reason"] == []
    assert b == {"path": "cad_relaxed", "reason": ["faces"], "n_faces": MF, "step_mb": None, "min_faces": MF,
                 "min_step_mb": None}


def test_faces_none_and_step_mb():
    assert route.choose(None, 500.0, RD, relaxed_enabled=True)["path"] == "cad"       # BREP 등 — 면 기준 건너뜀
    r2 = dict(RD, min_step_mb=20.0)
    assert route.choose(None, 19.99, r2, relaxed_enabled=True)["path"] == "cad"
    c = route.choose(None, 20.0, r2, relaxed_enabled=True)
    assert c["path"] == "cad_relaxed" and c["reason"] == ["step_mb"] and c["min_step_mb"] == 20.0
    d = route.choose(MF + 10, 25.0, r2, relaxed_enabled=True)
    assert d["reason"] == ["faces", "step_mb"]


def test_switches_off():
    assert route.choose(5000, 99.0, RD, relaxed_enabled=False)["path"] == "cad"       # compare cad_relaxed 꺼짐
    assert route.choose(5000, 99.0, dict(RD, enabled=False), relaxed_enabled=True)["path"] == "cad"
    assert route.choose(5000, None, dict(RD, min_faces=None), relaxed_enabled=True)["path"] == "cad"


def test_rank_flag_boundaries():
    fr, tp = float(RQ["fail_ratio"]), float(RQ["tria_pct"])
    assert route.rank_flag({"fail_ratio": fr, "tria_pct": tp}, RQ) is None              # 경계값 = 통과(> 만 위반)
    assert route.rank_flag({"fail_ratio": fr + 1e-9, "tria_pct": 0.0}, RQ) == \
        {"fail_ratio": fr + 1e-9, "tria_pct": 0.0, "over": ["fail"]}
    assert route.rank_flag({"fail_ratio": 0.0, "tria_pct": tp + 0.1}, RQ)["over"] == ["tria"]
    r = route.rank_flag({"fail_ratio": 0.555, "tria_pct": 21.9}, RQ)                    # 서버 실측(§0 근거)
    assert r["over"] == ["fail", "tria"]
    assert route.rank_flag(None, RQ) is None and route.rank_flag({}, RQ) is None


def test_route_independent():
    tree = ast.parse(open(SRC, encoding="utf-8").read())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(n.module or "")
    assert mods <= {"__future__", "math"}, mods
    src = open(SRC, encoding="utf-8").read()
    assert "open(" not in src and "DEFAULTS" not in src and "random" not in src and "gmsh" not in src.replace(
        "gmsh 를", "")
