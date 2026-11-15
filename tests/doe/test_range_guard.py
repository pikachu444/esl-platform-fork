"""V-SH-1·2·3·6 — 모드 무관 range guard 모듈 ``esl.morph.range_guard``(계약 esl_bead_shape_v021.md §2.3·§4.2·§4.5·§4.6).

배열·함수만(모드·파일·설정 없음): 해석적 ok_fn 으로 단일 축소 해상도·시험 수·inward, 상호작용 묶음·꼭짓점·조합 이분, 예산(가짜 시계·
max_evals)·막힘·문서 스키마, 그리고 모듈 독립성(AST — esl.doe·beadgraph·esl.mesh·open·DEFAULTS·전역 난수 없음)."""
import ast
import json
import os

import numpy as np
import pytest

from esl.morph import range_guard as rgm

STEPS = 5
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "esl", "morph",
                   "range_guard.py")


def big_budget():
    return rgm.Budget(10 ** 6, None)


def thr(t_lo, t_hi):
    """v ∈ [t_lo, t_hi] 통과(해석적 경계), 밖 = 위반(reason jac, value v)."""
    calls = []

    def ok(v):
        calls.append(v)
        good = t_lo <= v <= t_hi
        return (True, None, None) if good else (False, "jac", float(v), 1)
    return ok, calls


# ---------------------------------------------------------------- V-SH-1 single
@pytest.mark.parametrize("nom,lo,hi,t_lo,t_hi", [(10.0, 7.0, 13.0, 8.2, 11.37), (36.74, 29.392, 44.088, 30.0, 41.3),
                                                 (6.0, 4.2, 7.8, 0.0, 6.9)])
def test_single_resolution(nom, lo, hi, t_lo, t_hi):
    ok, calls = thr(t_lo, t_hi)
    r = rgm.single("B3_W", nom, lo, hi, ok, steps=STEPS, budget=big_budget())
    assert r["from"] == [lo, hi] and r["nominal"] == nom
    n_calls = len(calls)
    assert n_calls <= 2 * (1 + STEPS)
    assert sum(e["evals"] for e in r["ends"]) == n_calls
    for side, end, t in (("lo", lo, t_lo), ("hi", hi, t_hi)):
        u = r["usable"][0 if side == "lo" else 1]
        if (side == "lo" and end >= t) or (side == "hi" and end <= t):
            assert u == end                                     # 통과 끝은 그대로
            continue
        res = abs(end - nom) / 2 ** STEPS
        assert abs(u - t) <= res + 1e-4                         # 경계에서 해상도(+ 1e-4 반올림) 안
        assert (t <= u <= nom) if side == "lo" else (nom <= u <= t)   # 공칭 쪽 — 위반 쪽에 없음
        assert ok(u)[0]
        assert round(u * 1e4) == pytest.approx(u * 1e4, abs=1e-6)   # 1e-4 격자
    assert r["state"] == ("ok" if lo >= t_lo and hi <= t_hi else "limited")
    ok2, _ = thr(t_lo, t_hi)
    assert json.dumps(rgm.single("B3_W", nom, lo, hi, ok2, steps=STEPS, budget=big_budget()), sort_keys=True) == \
        json.dumps(r, sort_keys=True)                         # 같은 입력 비트 동일


def test_single_ends_record():
    ok, _ = thr(0.0, 41.3)
    r = rgm.single("B3_W", 37.28, 29.824, 44.736, ok, steps=STEPS, budget=big_budget())
    lo, hi = r["ends"]
    assert lo == {"side": "lo", "end": 29.824, "ok": True, "reason": None, "value": None, "evals": 1}
    assert hi["side"] == "hi" and not hi["ok"] and hi["reason"] == "jac" and hi["value"] == 44.736 and hi["n"] == 1
    assert hi["evals"] == 1 + STEPS


def test_inward_rounding():
    assert rgm.inward(41.31257, 37.0) == 41.3125
    assert rgm.inward(29.82341, 37.0) == 29.8235
    assert rgm.inward(5.0, 6.0) == 5.0 and rgm.inward(7.0, 6.0) == 7.0
    from esl.doe import bead_graph as bgr                  # bead_graph._inward 와 같은 식(이곳이 원본)
    for v, n in ((41.31257, 37.0), (29.82341, 37.0), (6.123456789, 6.5), (6.98765, 6.5)):
        assert rgm.inward(v, n) == bgr._inward(v, n)


# ---------------------------------------------------------------- V-SH-2 interacting / corners / combo
def test_interacting_union_find():
    sup = {"B2_D": np.array([1, 2, 3]), "B1_W": np.array([3, 4]), "B1_D": np.array([4, 5]), "B5_D": np.array([9]),
           "B4_D": np.array([20, 21]), "B4_W": np.array([21, 22])}
    g = rgm.interacting(sup)
    assert g == [["B1_D", "B1_W", "B2_D"], ["B4_D", "B4_W"]]           # 크기 1 제외·이름 정렬
    rev = dict(reversed(list(sup.items())))
    assert rgm.interacting(rev) == g                                    # 입력 순서 무관


def test_corners():
    c = rgm.corners(3, full_max=4, samples=16)
    assert c.dtype == np.int8 and c.shape == (8, 3)
    assert {tuple(r) for r in c.tolist()} == {(a, b, d) for a in (0, 1) for b in (0, 1) for d in (0, 1)}
    s = rgm.corners(6, full_max=4, samples=16)
    assert s.shape == (16, 6) and s.dtype == np.int8
    assert np.array_equal(s, np.random.default_rng(0).integers(0, 2, size=(16, 6), dtype=np.int8))
    assert np.array_equal(s, rgm.corners(6, full_max=4, samples=16))


def _sum_ok(limit):
    """합 제약: (D − 6) + (24 − W)/2 ≤ limit 통과(깊고 좁은 모서리 근사)."""
    def ok(vals):
        s = (vals["B1_D"] - 6.0) + (24.0 - vals["B1_W"]) / 2.0
        return (True, None, None) if s <= limit else (False, "inverted", 1.0)
    return ok


def test_combo_scale_exact():
    grp = [("B1_W", 24.0, 19.2, 28.8), ("B1_D", 6.0, 4.2, 7.8)]
    # 꼭짓점 (D 7.8, W 19.2): s·1.8 + s·2.4 ≤ limit → 경계 s* = limit / 4.2
    limit = 2.0
    r = rgm.combo(grp, _sum_ok(limit), full_max=4, samples=16, steps=STEPS, budget=big_budget())
    assert r["vars"] == ["B1_D", "B1_W"] and r["corners"] == 4 and r["bad_n"] == 1 and r["reason"] == "inverted"
    s_star = limit / 4.2
    assert s_star - 1 / 2 ** STEPS <= r["scale"] <= s_star
    assert r["scale"] * 2 ** STEPS == int(r["scale"] * 2 ** STEPS)      # 이분 격자
    u = r["usable"]
    assert u["B1_D"] == [rgm.inward(6.0 + r["scale"] * (4.2 - 6.0), 6.0), rgm.inward(6.0 + r["scale"] * 1.8, 6.0)]
    ok = _sum_ok(limit)
    for d in u["B1_D"]:
        for w in u["B1_W"]:
            assert ok({"B1_D": d, "B1_W": w})[0]                      # 4 꼭짓점 통과
    r2 = rgm.combo(list(reversed(grp)), _sum_ok(limit), full_max=4, samples=16, steps=STEPS, budget=big_budget())
    assert r2 == r                                                      # 입력 순서 무관


def test_combo_none_and_skips():
    grp = [("B1_D", 6.0, 4.2, 7.8), ("B1_W", 24.0, 19.2, 28.8)]
    assert rgm.combo(grp, _sum_ok(100.0), full_max=4, samples=16, steps=STEPS, budget=big_budget()) is None
    big = [(f"B{i}_D", 6.0, 4.2, 7.8) for i in range(1, 10)]
    r = rgm.combo(big, lambda v: (True, None, None), full_max=4, samples=16, steps=STEPS, budget=big_budget(),
                  max_group=8)
    assert r == {"vars": sorted(t[0] for t in big), "skipped": "max_group", "n": 9}
    calls = []

    def ok(v):
        calls.append(1)
        return True, None, None
    rgm.combo(big[:6], ok, full_max=4, samples=16, steps=STEPS, budget=big_budget(), max_group=8)
    assert len(calls) == 16                                              # 표본 16(시드 0)


# ---------------------------------------------------------------- V-SH-3 budget / blocked / doc
class FakeClock:
    def __init__(self, dt):
        self.t, self.dt = 0.0, dt

    def __call__(self):
        self.t += self.dt
        return self.t


def test_budget_evals_stops_whole_var():
    b = rgm.Budget(3, None)
    ok, _ = thr(0.0, 11.0)
    r = rgm.single("B1_D", 10.0, 7.0, 13.0, ok, steps=STEPS, budget=b)
    assert r == {"var": "B1_D", "skipped": "budget"}                     # 반쯤 줄인 값 없음
    assert b.stopped == "evals" and b.evals == 3 and not b.take()


def test_budget_time():
    clk = FakeClock(1.0)
    b = rgm.Budget(None, 4.5, clock=clk)
    n = 0
    while b.take():
        n += 1
    assert b.stopped == "time" and n == 4
    b2 = rgm.Budget(10, None)
    b2.stop("vars")
    assert b2.take() and b2.stopped == "vars"                           # 후보 수 상한은 기록만


def test_blocked_boundary():
    assert rgm.blocked(10.0, [6.0, 14.0], [9.0, 11.0], 0.25) == (False, False)      # keep = 0.25 = 경계 → 막힘 아님
    assert rgm.blocked(10.0, [6.0, 14.0], [9.01, 10.99], 0.25) == (True, True)
    assert rgm.blocked(10.0, [10.0, 14.0], [10.0, 10.5], 0.25) == (False, True)     # 원래 폭 0 = 막힘 아님
    ok, _ = thr(9.5, 10.5)
    r = rgm.single("B1_D", 10.0, 6.0, 14.0, ok, steps=STEPS, budget=big_budget(), min_keep_frac=0.25)
    assert r["state"] == "blocked"
    ok, _ = thr(9.5, 20.0)
    r = rgm.single("B1_D", 10.0, 6.0, 14.0, ok, steps=STEPS, budget=big_budget(), min_keep_frac=0.25)
    assert r["state"] == "limited"


def test_doc_schema_and_order():
    b = rgm.Budget(4000, 180)
    b.take()
    crit = {"flip_deg": 60, "jac_min": 0.3, "tria_angle_min_deg": 10, "area_ratio_min": 0.2,
            "max_new_fail_ratio": None}
    d = rgm.doc("prep", [], [], [], b, crit, {"graph_sha256": "g", "cfg_sha256": "c", "fixed_sha256": "f",
                                             "exclude_sha256": "e", "steps": 5, "min_keep_frac": 0.25, "max_vars": 120})
    assert list(d) == ["schema", "scope", "graph_sha256", "cfg_sha256", "fixed_sha256", "exclude_sha256",
                       "selection_sha256", "crit", "steps", "min_keep_frac", "budget", "entries", "combos", "skipped"]
    assert d["schema"] == rgm.SCHEMA == "esl/range_guard/1" and d["selection_sha256"] is None
    assert d["crit"] == {"flip_deg": 60.0, "jac_min": 0.3, "tria_angle_min_deg": 10.0, "area_ratio_min": 0.2,
                         "max_new_fail_ratio": None}
    assert d["budget"] == {"max_evals": 4000, "timeout_s": 180, "max_vars": 120, "evals": 1, "stopped": None}
    assert "seconds" not in json.dumps(d)


def test_accept_order():
    crit = {"flip_deg": 60.0, "jac_min": 0.3, "tria_angle_min_deg": 10.0, "area_ratio_min": 0.2,
            "max_new_fail_ratio": 0.05}
    p = {"inverted": 2, "jac_min": 0.1, "jac_bad_new": 3, "tri_angle_min": 5.0, "tri_bad_new": 1,
         "area_ratio_min": 0.1, "new_fail_ratio": 0.5}
    seq = []
    for k, z in (("inverted", 0), ("jac_bad_new", 0), ("tri_bad_new", 0), ("area_ratio_min", 0.5),
                 ("new_fail_ratio", 0.0)):
        seq.append(rgm.accept(p, crit)[1])
        p[k] = z
    assert seq == list(rgm.CRITERIA)
    assert rgm.accept(p, crit) == (True, None, None)
    off = dict(crit, jac_min=None, tria_angle_min_deg=None, area_ratio_min=None, max_new_fail_ratio=None)
    q = {"inverted": 0, "jac_min": 0.1, "jac_bad_new": 3, "tri_bad_new": 2, "area_ratio_min": 0.01,
         "new_fail_ratio": 0.9}
    assert rgm.accept(q, off) == (True, None, None)                      # 뒤집힘만(V-SH-9 기준)


# ---------------------------------------------------------------- V-SH-6 independence (range_guard part)
def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(n.module or "")
    return tree, mods


def test_range_guard_independent():
    tree, mods = _imports(SRC)
    assert mods <= {"__future__", "math", "time", "numpy"}, mods
    assert not any(m.startswith(("esl.doe", "beadgraph", "esl.mesh", "os", "json")) for m in mods)
    src = open(SRC, encoding="utf-8").read()
    assert "open(" not in src and "DEFAULTS" not in src
    for n in ast.walk(tree):                                             # 전역 난수 없음(시드 0 default_rng 만)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute) and n.value.attr == "random":
            assert n.attr == "default_rng", n.attr
    assert "default_rng(0)" in src
