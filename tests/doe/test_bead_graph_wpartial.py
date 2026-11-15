"""V-SH-7·8 — 그래프 비드 W 를 폭 정보가 있는 구간(S_W)에만(계약 esl_bead_shape_v021.md §3, SH-4~9).

H6 픽스처: 바닥 링 두 조각(폭 없음 — 입구 선 한쪽) + 다리(폭 36 mm) 를 한 비드로 → vars [D, W], W 기저는 S_W(다리)에만 —
허용 구역(A_W(S_W)) 밖 0·S \\ S_W 노드 0·달성 W ±1e-3·D 기저는 옛 규칙과 비트 같음·BG_W_PARTIAL. legacy(shape_rules None 또는
w_partial false)는 v0.20.0 규칙(W 는 모든 세그먼트에 폭이 있을 때만)·바이트 그대로, 전부 W 인 비드는 두 규칙에서 정규화·기저 비트
같음, 네트워크 묶기 D 만, 타이(S_W 공칭), merge 한 W+비W 세그먼트 = D 만."""
import copy
import hashlib
import json

import numpy as np
import pytest
import synth_guard as sg
from _bg_util import CFG, bgr, bs, prepared

from esl.errors import EslError

pytestmark = pytest.mark.slow

RU = sg.rules()
RU_OFF = sg.rules({"w_partial": False, "range_guard": {"enabled": False}})   # 항목 1·2 끔
PART = [16597, 16483, 16589]          # 바닥 링(폭 없음) · 다리(폭 36) · 바닥 링(폭 없음) — 접합 구역 4 로 이어짐
ALLW = [90306, 87439]                 # 채널 + 플레어(둘 다 폭 있음)


@pytest.fixture(scope="module")
def H6():
    return prepared("h6")


def _sel(g, beads, ties=(), edits=None):
    return {"schema_version": 2, "graph": {"sha256": bgr.graph_sha_of(g), "rules": g["rules"], "edits": edits or {}},
            "beads": [{"id": f"b{i + 1}", "src": "graph", "segs": [{"anchor": a} for a in bd]}
                      for i, bd in enumerate(beads)], "ties": [list(t) for t in ties]}


def _derive(H, sel, rules):
    mesh, g, lab, fx, _d = H
    norm, sha = bgr.normalize_v2(sel, g, CFG, labels=lab, mesh=mesh, shape_rules=rules)
    D = bgr.derive_obj_v2(mesh, norm, CFG, g, lab, fixed_node_ids=fx, shape_rules=rules)
    return norm, sha, D


def _gb(D, name):
    return next(v for v in D.graph_basis if v["name"] == name)


def test_w_partial_basis_v_sh_7(H6):
    from beadgraph.checks import achieved, strict_allowed_nodes
    mesh, g, lab, fx, _d = H6
    norm, _sha, D = _derive(H6, _sel(g, [PART]), dict(RU, range_guard=None))
    assert "vars" not in norm["beads"][0]                               # 가능 집합 = [D, W] 전부 → 기록 안 함
    b = D.beads[0]
    sid = {s["anchor"]: s["id"] for s in g["segments"]}
    assert b.vars == ["D", "W"] and b.w_seg_ids == [sid[16483]]
    assert b.W_nom == pytest.approx(float(g["segments"][sid[16483]]["entry_width"]))
    w = next(x for x in b.warnings if x["code"] == "BG_W_PARTIAL")
    assert w == {"code": "BG_W_PARTIAL", "level": "info", "bead": "b1", "n_w": 1, "n_seg": 3, "cover": b.w_cover,
                 "no_w": [16589, 16597]}
    L = {a: float(g["segments"][sid[a]]["length"]) for a in PART}
    assert b.w_cover == round(L[16483] / sum(L.values()), 4)
    B = bs.basis(mesh, D, CFG)                                          # BG_BASIS_LEAK 이면 여기서 EslError
    gw = _gb(D, "B1_W")
    assert gw["segs"] == [sid[16483]] and gw["zones"] == []
    X = np.asarray(mesh["x0"], float)
    C = bgr._conn(mesh)
    allowed = strict_allowed_nodes(g, lab, X, C, [gw])["B1_W"]
    full = np.zeros((X.shape[0], 3))
    full[gw["idx"]] = gw["vec"]
    mag = np.linalg.norm(full, axis=1)
    assert float(mag[~allowed].max(initial=0.0)) <= 1e-6                 # 바깥 0(A_W(S_W))
    other = np.isin(lab["segment"], [sid[16597], sid[16589]])
    on_other = np.unique(C[other][C[other] >= 0])
    on_sw = np.unique(C[np.isin(lab["segment"], [sid[16483]])].ravel())
    only_other = np.setdiff1d(on_other, on_sw)
    assert float(mag[only_other].max(initial=0.0)) == 0.0               # S \ S_W 노드 W 기저 = 0
    nom_b = next(v for v in B.vars if v["name"] == "B1_W")["nominal"]
    for end in b.range_basis["W"]:
        x = bs.morph(X, B, {"B1_W": end})
        err = achieved(g, lab, X, x, [gw], {"B1_W": float(end) - nom_b + gw["nominal"]})["B1_W"]
        assert err is not None and err <= 1e-3                           # S_W 달성 W(BG-D-33)
    # D 기저 = 옛 규칙(W 없는 비드)과 비트 같음
    _n0, _s0, D0 = _derive(H6, _sel(g, [PART]), None)
    assert D0.beads[0].vars == ["D"]
    B0 = bs.basis(mesh, D0, CFG)
    v1 = next(v for v in B.vars if v["name"] == "B1_D")
    v0 = next(v for v in B0.vars if v["name"] == "B1_D")
    assert v1["idx"].tobytes() == v0["idx"].tobytes() and v1["vec"].tobytes() == v0["vec"].tobytes()
    # 행·요약 키(부분일 때만)
    rows = {r["name"]: r for r in bgr.params_rows_v2(D, CFG)}
    assert rows["B1_W"]["w_segs"] == [16483] and rows["B1_W"]["w_cover"] == b.w_cover
    assert "w_segs" not in rows["B1_D"]
    summ = D.summary(with_figures=False)["beads"][0]
    assert summ["w_segs"] == [16483] and summ["w_cover"] == b.w_cover
    doc = bgr.derive_v2(mesh, norm, CFG, g, lab, fixed_scan=fx, shape_rules=dict(RU, range_guard=None))
    assert doc["beads"][0]["section"] is not None and doc["beads"][0]["section"]["ds_dW"]


def _h(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def test_w_partial_legacy_v_sh_8(H6):
    mesh, g, lab, fx, _d = H6
    sel = _sel(g, [PART, ALLW, [16578]])
    out = {}
    for tag, rules in (("none", None), ("off", RU_OFF)):
        norm, sha, D = _derive(H6, sel, rules)
        B = bs.basis(mesh, D, CFG)
        out[tag] = (sha, _h(D.summary(with_figures=False)), _h(bgr.params_rows_v2(D, CFG)), bs.basis_bin(B),
                    _h(bgr.derive_v2(mesh, norm, CFG, g, lab, fixed_scan=fx, shape_rules=rules)))
        assert D.beads[0].vars == ["D"] and D.beads[0].W_nom is None    # v0.20.0: 하나라도 폭이 없으면 D 만
        assert not any(w["code"] == "BG_W_PARTIAL" for b in D.beads for w in b.warnings)
        assert "w_segs" not in json.dumps(D.summary(with_figures=False))
    assert out["none"] == out["off"]                                     # w_partial false = 키 없음과 같은 바이트
    with pytest.raises(EslError) as ei:                                  # legacy 는 부분 W 비드에 W 를 고를 수 없음
        bad = copy.deepcopy(sel)
        bad["beads"][0]["vars"] = ["D", "W"]
        bgr.normalize_v2(bad, g, CFG, labels=lab, mesh=mesh)
    assert ei.value.code == "BG_EDIT_INVALID"
    # 전부 W 인 비드: 두 규칙에서 정규화·기저 비트 같음
    s_all = _sel(g, [ALLW])
    n1, sha1, D1 = _derive(H6, s_all, None)
    n2, sha2, D2 = _derive(H6, s_all, dict(RU, range_guard=None))
    assert bs.canonical_json(n1) == bs.canonical_json(n2) and sha1 == sha2
    assert bs.basis_bin(bs.basis(mesh, D1, CFG)) == bs.basis_bin(bs.basis(mesh, D2, CFG))
    assert D2.beads[0].w_cover is None and D2.beads[0].w_seg_ids == D2.beads[0].seg_ids


def test_w_partial_network_ties_merge(H6):
    mesh, g, lab, fx, _d = H6
    sha = bgr.graph_sha_of(g)
    net = {"schema_version": 2, "graph": {"sha256": sha, "rules": g["rules"], "edits": {}},
           "beads": [{"id": "b1", "src": "graph", "segs": [{"network": 16483}]}], "ties": []}
    _n, _s, D = _derive(H6, net, dict(RU, range_guard=None))
    assert D.beads[0].vars == ["D"]                                       # 네트워크 묶기 = D 만(BG-D-18)
    # 타이: S_W 공칭이 같은 부분 비드 둘 = 허용(BG_W_PARTIAL 각자), S_W 공칭이 다르면 BG_TIE_NOMINAL
    ok = _sel(g, [[16597, 16483], [16578, 16481]], ties=[["b1", "b2"]])
    _n, _s, D = _derive(H6, ok, dict(RU, range_guard=None))
    assert [b.vars for b in D.beads] == [["D", "W"], ["D", "W"]]
    assert all(any(w["code"] == "BG_W_PARTIAL" for w in b.warnings) for b in D.beads)
    rows = {r["name"]: r for r in bgr.params_rows_v2(D, CFG)}
    assert rows["B1_W"]["group_members"] == ["B1_W", "B2_W"] and "B2_W" not in rows
    for bad_beads in ([[16597, 16483], [14472, 14577]],                  # S_W 공칭 36 vs 58.74
                      [[16597, 16483], [14977]]):                        # W 유무가 다름(부분 W vs 폭 없음)
        with pytest.raises(EslError) as ei:
            bgr.normalize_v2(_sel(g, bad_beads, ties=[["b1", "b2"]]), g, CFG, labels=lab, mesh=mesh, shape_rules=RU)
        assert ei.value.code == "BG_TIE_NOMINAL"
    bgr.normalize_v2(_sel(g, [[16597, 16483], [14977]], ties=[["b1", "b2"]]), g, CFG, labels=lab, mesh=mesh)
    # merge 한 W + 비W 세그먼트 = entry_width null → 그 구간 D 만
    m = _sel(g, [[16597, 16589]], edits={"merge": [[{"anchor": 16597}, {"anchor": 16483}]]})
    _n, _s, D = _derive(H6, m, dict(RU, range_guard=None))
    assert D.beads[0].vars == ["D"]
