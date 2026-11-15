"""V-SH-9·10 — 그래프 변수 range guard(계약 esl_bead_shape_v021.md §4, SH-10~18).

V-SH-9  guard ⊇ w_clamp: H6 자동 seed 에서 기준을 뒤집힘만(jac·tri·area 끔)으로 두면 W 항목 usable = ``w_clamp_table`` usable
        (1e-4 반올림 포함) — 일반화 증명.
V-SH-10 기본 기준(Q-SH-1 A): H6 seed 표 → derive 적용 → 새 기본 범위의 모든 단일 끝 안이 accept 통과(독립 계산), 새 기본 범위
        LHS 30 안 미리보기 판정에서 SELECT_MORPH_INVERTED 0·RG_OUTSIDE_GUARD 0; 합성 포켓 D·W 조합(깊고 좁은 모서리 뒤집힘) →
        scale < 1 → 4 꼭짓점 통과; 표 불일치(hold 0·exclude·toggle) → unchecked → ``guard_selection`` 이 같은 값."""
import copy
import json
import os
import tempfile

import numpy as np
import pytest
import synth_guard as sg
from _bg_util import CFG, bgr, bs, prepared

from esl.doe import mesh_quality as mq
from esl.morph import range_guard as rgm

pytestmark = pytest.mark.slow

RU = sg.rules()
CRIT = bgr._crit(RU["range_guard"], CFG)


@pytest.fixture(scope="module")
def H6():
    return prepared("h6")


@pytest.fixture(scope="module")
def TABLE(H6):
    mesh, g, lab, fx, _d = H6
    return bgr.range_guard_table(mesh, g, lab, fx, CFG, RU)


@pytest.fixture(scope="module")
def AUTO(H6):
    mesh, g, lab, fx, _d = H6
    sel, _sym, _w = bgr.auto_seed(g, lab, CFG)
    return bgr.normalize_v2(sel, g, CFG, labels=lab, mesh=mesh, shape_rules=RU)


def test_guard_generalizes_w_clamp_v_sh_9(H6):
    mesh, g, lab, fx, _d = H6
    steps = int(bgr.select_cfg(CFG)["range"]["check_steps"])
    r_inv = sg.rules({"range_guard": {"jac_min": None, "tria_angle_min_deg": None, "area_ratio_min": None,
                                      "steps": steps, "combo": {"enabled": False}}})
    doc = bgr.range_guard_table(mesh, g, lab, fx, CFG, r_inv)
    wc = bgr.w_clamp_table(mesh, g, lab, fx, CFG)
    assert wc["entries"]
    rg = {json.dumps(e["key"]["segs"]): e for e in doc["entries"] if e["key"]["kind"] == "W"}
    for e in wc["entries"]:
        r = rg[json.dumps(e["segs"])]
        assert r["from"] == e["from"]
        assert r["usable"] == e["usable"], (e, r)                          # 같은 수치(1e-4 반올림 포함)
        assert [not x["ok"] for x in r["ends"]] == [bool(k) for k in e["inverted"]]
        assert all(x["reason"] == "inverted" for x in r["ends"] if not x["ok"])
    for k, r in rg.items():                                                # 표에 없는 W = 뒤집힘 없음
        if not any(json.dumps(e["segs"]) == k for e in wc["entries"]):
            assert r["state"] == "ok" and r["usable"] == r["from"]


def _probe_ok(mesh, B, values):
    x0 = np.asarray(mesh["x0"], float)
    x = bs.morph(x0, B, values)
    am = bs.affected_elems(mesh, x0, x)
    p = mq.guard_probe(x0, x, mesh["conn"], mesh["elem_type"], np.flatnonzero(am), flip_deg=CRIT["flip_deg"],
                       jac_min=CRIT["jac_min"], tria_angle_min_deg=CRIT["tria_angle_min_deg"])
    return rgm.accept(p, CRIT)


def test_guard_table_applied_v_sh_10(H6, TABLE, AUTO):
    mesh, g, lab, fx, _d = H6
    norm, _sha = AUTO
    doc = TABLE
    assert doc["schema"] == bgr.RANGE_GUARD_SCHEMA and doc["scope"] == "prep" and doc["budget"]["stopped"] is None
    assert any(e["state"] == "limited" for e in doc["entries"])
    assert doc["combos"] and all(c["scale"] < 1 for c in doc["combos"])
    d = tempfile.mkdtemp(prefix="rg_")
    sha1 = bgr.write_range_guard(os.path.join(d, bgr.RANGE_GUARD_JSON), doc)
    again = bgr.range_guard_table(mesh, g, lab, fx, CFG, RU)               # 멈추지 않은 표 = 같은 입력 바이트 같음
    assert bgr.write_range_guard(os.path.join(d, "b.json"), again) == sha1
    assert bgr.load_range_guard(d) == json.loads(json.dumps(doc))
    D = bgr.derive_obj_v2(mesh, norm, CFG, g, lab, fixed_node_ids=fx, range_guard=doc, shape_rules=RU)
    rows = bgr.params_rows_v2(D, CFG)
    assert rows and all(r["guard"]["state"] != "unchecked" for r in rows)
    assert not any(w["code"] == "RG_UNCHECKED" for b in D.beads for w in b.warnings)
    codes = {w["code"] for b in D.beads for w in b.warnings}
    assert {"RG_RANGE_LIMITED", "RG_COMBO_LIMITED"} <= codes
    # API derive(derive_v2) = BD_MATRIX derive(derive_obj_v2) — 같은 표 적용
    api = bgr.derive_v2(mesh, norm, CFG, g, lab, fixed_scan=fx, range_guard=doc, shape_rules=RU)
    assert json.dumps(api["params"], sort_keys=True) == json.dumps(rows, sort_keys=True)
    B = bs.basis(mesh, D, CFG)
    for r in rows:                                                         # 새 기본 범위 단일 끝 = accept 통과
        g_ = r["guard"]
        if g_["state"] == "blocked" or (g_["state"] == "limited" and r["default_range"] == g_["from"]):
            continue
        for end in r["default_range"]:
            ok, why, val = _probe_ok(mesh, B, {r["name"]: float(end)})
            assert ok, (r["name"], end, why, val)
    # LHS 30 안(새 기본 범위, use_default 변수): 뒤집힘 0 · RG_OUTSIDE_GUARD 0
    use = [r for r in rows if r["use_default"]]
    rng = np.random.default_rng(0)
    n = 30
    P = (np.argsort(rng.random((len(use), n)), axis=1) + rng.random((len(use), n))) / n
    x0 = np.asarray(mesh["x0"], float)
    for j in range(n):
        vals = {r["name"]: float(r["default_range"][0] + P[i, j] * (r["default_range"][1] - r["default_range"][0]))
                for i, r in enumerate(use)}
        st = bs.design_state(mesh, x0, bs.morph(x0, B, vals), D.fixed_mask, CFG)
        assert st["code"] != "SELECT_MORPH_INVERTED", (j, st["quality"])
        assert bgr.outside_guard(rows, vals) is None
    bad = dict(vals)
    r0 = next(r for r in rows if r["guard"]["state"] == "limited")
    bad[r0["name"]] = r0["guard"]["from"][1] + 1.0
    w = bgr.outside_guard(rows, bad)
    assert w["code"] == "RG_OUTSIDE_GUARD" and [v["name"] for v in w["vars"]] == [r0["name"]]


def test_pocket_combo_v_sh_10():
    """합성 포켓: D 깊게·W 좁게 = 바닥 폭 W − 2D 소멸 → 뒤집힘. 단일 끝은 통과, 조합 scale < 1, 줄인 4 꼭짓점 통과."""
    X0, C, T, Bv, nom = sg.pocket(W=20.0, D=7.0)
    idx = np.arange(C.shape[0])
    rg = RU["range_guard"]
    crit = dict(CRIT, jac_min=None, tria_angle_min_deg=None, area_ratio_min=None)

    def ok(vals):
        x = X0 + (vals.get("B1_D", nom["D"]) - nom["D"]) * Bv["D"] + (vals.get("B1_W", nom["W"]) - nom["W"]) * Bv["W"]
        p = mq.guard_probe(X0, x, C, T, idx, flip_deg=crit["flip_deg"], jac_min=None, tria_angle_min_deg=None)
        return rgm.accept(p, crit)
    rd = bgr.select_cfg(CFG)["range"]
    dr = [nom["D"] * (1 - rd["depth_rel"]), nom["D"] * (1 + rd["depth_rel"])]
    wr = [nom["W"] * (1 - rd["width_rel"]), nom["W"] * (1 + rd["width_rel"])]
    for name, r in (("B1_D", dr), ("B1_W", wr)):
        for end in r:
            assert ok({name: end})[0]                                      # 단일 끝은 통과
    b = rgm.Budget(rg["budget"]["max_evals"], None)
    cc = rg["combo"]
    res = rgm.combo([("B1_D", nom["D"], *dr), ("B1_W", nom["W"], *wr)], ok, full_max=cc["full_max_vars"],
                    samples=cc["samples"], steps=rg["steps"], budget=b, max_group=cc["max_group"])
    assert res is not None and res["scale"] < 1 and res["corners"] == 4 and res["reason"] == "inverted"
    u = res["usable"]
    for d in u["B1_D"]:
        for w in u["B1_W"]:
            assert ok({"B1_D": d, "B1_W": w})[0]                          # 줄인 4 꼭짓점 통과


def _sel_vals(doc, var_key):
    e = next(e for e in doc["entries"] if json.dumps(e["key"], sort_keys=True) == json.dumps(var_key, sort_keys=True))
    return e["usable"], e["state"]


@pytest.mark.parametrize("kind", ["hold0", "exclude", "toggle"])
def test_table_mismatch_unchecked_v_sh_10(H6, TABLE, AUTO, kind):
    mesh, g, lab, fx, _d = H6
    norm, _sha = AUTO
    sel = copy.deepcopy(norm)
    sel["beads"] = [b for b in sel["beads"] if b["id"] != "b9"]           # 판(plateau) — 섬 편집·제외가 기저 누출을 냄(기존 동작)
    target = "b10"                                                         # 포켓(폭 75) — 고정 노드 없음
    if kind == "hold0":
        next(b for b in sel["beads"] if b["id"] == target)["hold_fixed"] = 0
    elif kind == "exclude":
        sel["exclude"] = bs._norm_set({"t": [[139, 139]]}, "exclude", 10_000_000)   # 비드와 노드를 나누지 않는 기준 판 요소
    else:
        sel["graph"]["edits"] = {"toggle": [{"anchor": int(g["islands"][0]["anchor"]), "as": "bead"}]}
    norm2, _ = bgr.normalize_v2(sel, g, CFG, labels=lab, mesh=mesh, shape_rules=RU)
    D = bgr.derive_obj_v2(mesh, norm2, CFG, g, lab, fixed_node_ids=fx, range_guard=TABLE, shape_rules=RU)
    b = next(x for x in D.beads if x.id == target)
    assert b.guard["D"]["state"] == "unchecked" and b.guard["W"]["state"] == "unchecked"
    assert any(w["code"] == "RG_UNCHECKED" and w["var"] == "B10_W" for w in b.warnings)
    if kind == "hold0":                                                    # 다른 변수는 표 그대로
        assert next(x for x in D.beads if x.id == "b11").guard["W"]["state"] != "unchecked"
    B = bs.basis(mesh, D, CFG)
    doc = bgr.guard_selection(mesh, D, B, CFG, only=["B10_D", "B10_W"])
    assert doc["scope"] == "selection" and doc["selection_sha256"] == D.sha256
    assert [e["var"] for e in doc["entries"]] == ["B10_D", "B10_W"]
    seed_b = next(x for x in bgr.derive_obj_v2(mesh, norm, CFG, g, lab, fixed_node_ids=fx, shape_rules=RU).beads
                  if x.id == target)
    for typ in ("D", "W"):
        key = bgr._var_key(g, seed_b, typ)
        u_tab, st_tab = _sel_vals(TABLE, key)
        e = next(e for e in doc["entries"] if e["var"] == f"B10_{typ}")
        assert e["usable"] == u_tab and e["state"] == st_tab              # guard_selection = 표와 같은 값
        assert b.guard[typ]["state"] == st_tab
        assert not any(w["code"] == "RG_UNCHECKED" and w["var"] == f"B10_{typ}" for w in b.warnings)


def test_guard_selection_supplements_whole(H6, AUTO):
    """표 없음(전부 unchecked) → guard_selection 이 모든 그래프 변수 점검 + 조합 → 행에 guard·축소 반영(BD_MATRIX 보충)."""
    mesh, g, lab, fx, _d = H6
    norm, _sha = AUTO
    sub = copy.deepcopy(norm)
    sub["beads"] = [b for b in sub["beads"] if b["id"] in ("b6", "b10", "b11")]
    D = bgr.derive_obj_v2(mesh, sub, CFG, g, lab, fixed_node_ids=fx, range_guard=None, shape_rules=RU)
    assert all(v["state"] == "unchecked" for b in D.beads for v in b.guard.values())
    B = bs.basis(mesh, D, CFG)
    doc = bgr.guard_selection(mesh, D, B, CFG)
    assert sorted(e["var"] for e in doc["entries"]) == sorted(v["name"] for v in B.vars)
    rows = bgr.params_rows_v2(D, CFG)
    assert all(r["guard"]["state"] != "unchecked" for r in rows)
    assert any(c["vars"] == ["B6_D", "B6_W"] for c in doc["combos"])
    r6 = {r["name"]: r for r in rows}
    assert r6["B6_D"]["guard"]["combo_scale"] is not None and r6["B6_D"]["guard"]["combo_scale"] < 1
    info = bgr.guard_result(doc, 1.23)
    assert info["entries"] == len(doc["entries"]) and info["seconds"] == 1.23 and info["stopped"] is None
    # 예산 0 에 가까우면 남은 변수 unchecked + RG_BUDGET
    tiny = sg.rules({"range_guard": {"budget": {"max_evals": 3}}})
    D2 = bgr.derive_obj_v2(mesh, sub, CFG, g, lab, fixed_node_ids=fx, range_guard=None, shape_rules=tiny)
    d2 = bgr.guard_selection(mesh, D2, bs.basis(mesh, D2, CFG), CFG)
    assert d2["budget"]["stopped"] == "evals" and d2["skipped"]
    assert any(w["code"] == "RG_BUDGET" for w in D2.warnings)
    assert any(r["guard"]["state"] == "unchecked" for r in bgr.params_rows_v2(D2, CFG))
