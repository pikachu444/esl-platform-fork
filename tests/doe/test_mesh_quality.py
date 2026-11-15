"""V-BS-7: 모핑 안 품질 판정(``mesh_quality.affected_quality`` — v0.15.0 추가, 계약 esl_bead_select.md §6).

정상 범위 안 새 Fail 0 → READY, W −40 %(사면 겹침) → SELECT_MORPH_INVERTED, 블렌딩 R 아주 작게 → 새 Fail 비율 > 0.01 →
SELECT_QUALITY_FAIL, 공칭에서 이미 Fail 인 요소는 세지 않음, ``bead_doe.compare.quality`` 값 변경이 그대로 반영(복제 없음),
v0.14.0 ``summarize`` 결과 불변."""
import copy

import numpy as np
import pytest

import synth_bead as sb
import synth_doe as sd
from esl.doe import DEFAULTS
from esl.doe import bead_select as bs
from esl.doe import mesh_quality as mq
from esl.doe import settings

def _cfg(h: float, policy: str = "skip") -> dict:
    """합성 메시 h mm(이슈 #53 기준은 3 mm 메시) → 길이 기준만 h/3 배로 맞춘 시험 설정(나머지 기준 = 기본값).
    v0.16.1: 기본 정책은 warn — 이 파일의 v0.15.0 기대값(V-BS-7)은 quality.fail_policy skip 으로(V-SR-9 skip 경로)."""
    q = copy.deepcopy(DEFAULTS["compare"]["quality"])
    for k in ("min_length", "max_length"):
        q[k] = {kk: vv * h / 3.0 for kk, vv in q[k].items()}
    return settings({"bead_doe": {"enabled": True, "compare": {"quality": q},
                                  "select": {"fixed_policy": policy, "quality": {"fail_policy": policy}}}})


CFG = _cfg(5.0)


def _make(h: float, cfg: dict):
    g = sb.generate(h)
    D = bs.derive_obj(g["mesh"], bs.normalize_input(sb.selection(g), cfg), cfg, fixed_node_ids=g["fixed_ids"])
    return g, D, bs.basis(g["mesh"], D, cfg)


@pytest.fixture(scope="module")
def G():
    return _make(5.0, CFG)


def test_normal_range_ready(G):
    g, D, B = G
    X0 = g["mesh"]["x0"]
    nom = B.nominal()
    for v in ({"B1_D1": 24.0, "B1_D2": 13.0}, {"B1_W": nom["B1_W"] + 5.0}, {"B2_D1": 7.0, "B2_W": 42.0}):
        x = bs.morph(X0, B, v)
        st = bs.design_state(g["mesh"], X0, x, D.fixed_mask, CFG)
        assert st["state"] == "READY", st
        assert st["quality"]["new_fail"] == 0 and st["quality"]["inverted"] == 0
        assert st["quality"]["n_affected"] > 0


def test_inverted_and_quality_fail(G):
    g, D, B = G
    X0 = g["mesh"]["x0"]
    m = g["mesh"]
    W = B.nominal()["B1_W"]
    x = bs.morph(X0, B, {"B1_W": 0.6 * W})                   # 사면·바닥 겹침
    st = bs.design_state(m, X0, x, D.fixed_mask, CFG)
    assert st["state"] == "FAILED_MESH" and st["code"] == "SELECT_MORPH_INVERTED", st["quality"]
    # 블렌딩 R 아주 작게 → 상판 첫 줄이 늘어남(max_length Fail)
    sel = sb.selection(g)
    sel["beads"][0]["blend_mm"] = 1.0
    Ds = bs.derive_obj(m, bs.normalize_input(sel, CFG), CFG)
    Bs = bs.basis(m, Ds, CFG)
    x = bs.morph(X0, Bs, {"B1_W": Bs.nominal()["B1_W"] - 6.0})
    st = bs.design_state(m, X0, x, Ds.fixed_mask, CFG)
    assert st["state"] == "FAILED_MESH" and st["code"] == "SELECT_QUALITY_FAIL", st["quality"]
    assert st["quality"]["new_fail_ratio"] > CFG["select"]["quality"]["max_fail_ratio"]
    assert st["quality"]["fail_by"]["max_length"] > 0
    # compare.quality 기준값 변경이 그대로 반영(한 곳)
    cfg2 = settings({"bead_doe": {"enabled": True, "select": {"quality": {"fail_policy": "skip"}}, "compare": {"quality": {
        "max_length": {"warn": 50.0, "fail": 60.0}, "aspect": {"warn": 50.0, "fail": 60.0},
        "skew": {"warn": 80.0, "fail": 89.0}, "quad_max_angle": {"warn": 170.0, "fail": 179.0},
        "quad_min_angle": {"warn": 2.0, "fail": 1.0}, "jacobian": {"warn": 0.1, "fail": 0.05},
        "warpage": {"warn": 80.0, "fail": 89.0}}}}})
    st2 = bs.design_state(m, X0, x, Ds.fixed_mask, cfg2)
    assert st2["state"] == "READY", st2["quality"]
    # select.quality.max_fail_ratio 상한도 반영
    cfg3 = settings({"bead_doe": {"enabled": True, "select": {"quality": {"max_fail_ratio": 0.99, "fail_policy": "skip"}}}})
    assert bs.design_state(m, X0, x, Ds.fixed_mask, cfg3)["state"] == "READY"
    # V-SR-9 warn 정책(기본): 같은 안 = READY + SELECT_QUALITY_WARN, 뒤집힘 안은 여전히 FAILED_MESH
    W = _cfg(5.0, "warn")
    st = bs.design_state(m, X0, x, Ds.fixed_mask, W)
    assert st["state"] == "READY" and st["code"] is None
    qw = [w for w in st["warnings"] if w["code"] == "SELECT_QUALITY_WARN"]
    assert qw and qw[0]["new_fail"] == st["quality"]["new_fail"] > 0
    xi = bs.morph(X0, B, {"B1_W": 0.6 * B.nominal()["B1_W"]})
    assert bs.design_state(m, X0, xi, D.fixed_mask, W)["code"] == "SELECT_MORPH_INVERTED"


def test_nominal_fail_not_counted(G):
    g, D, B = G
    m = g["mesh"]
    X0 = m["x0"]
    q = copy.deepcopy(DEFAULTS["compare"]["quality"])
    q["aspect"] = {"warn": 1.05, "fail": 1.1}                 # 공칭에서도 대부분 Fail
    x = bs.morph(X0, B, {"B1_D1": 22.01})
    am = bs.affected_elems(m, X0, x)
    r = mq.affected_quality(m, x, am, q, flip_deg=60.0)
    nominal_fail = mq.affected_quality(m, X0 + 0.0, am, q, flip_deg=60.0)
    assert r["n_affected"] == int(am.sum()) > 0
    assert r["new_fail"] == 0 and nominal_fail["new_fail"] == 0
    m0 = mq.element_metrics(X0, m["conn"][am], m["elem_type"][am])
    assert int(np.sum(m0["aspect"] > 1.1)) > 0                # 공칭 Fail 이 있는데도 세지 않음
    assert mq.affected_quality(m, x, np.zeros(len(am), bool), q, flip_deg=60.0)["n_affected"] == 0


@pytest.mark.parametrize("h", [5.0, 2.5])
def test_degradation_failed_by_mesh_size(h):
    """품질 열화(V-BS-7)는 메시 크기와 무관: h 5·2.5 mm 모두 b1 깊이 3.5 배·블렌딩 R = 1 mm(폭 −6) → FAILED_MESH.
    (h 2.5 는 원형 비드 b2 중심 노드가 격자점 — synth_bead 중심 노드 z = −D 수정 회귀도 겸함)"""
    cfg = _cfg(h)
    g, D, B = _make(h, cfg)
    m = g["mesh"]
    X0 = m["x0"]
    ctr = int(np.argmin(np.hypot(X0[:, 0] - 560.0, X0[:, 1] - 345.0)))
    if np.hypot(X0[ctr, 0] - 560.0, X0[ctr, 1] - 345.0) < 1e-9:
        assert X0[ctr, 2] == pytest.approx(-g["truth"]["b2"]["D"][1])
    nom = B.nominal()
    st = bs.design_state(m, X0, bs.morph(X0, B, {"B1_D1": 3.5 * nom["B1_D1"], "B1_D2": 3.5 * nom["B1_D2"]}),
                         D.fixed_mask, cfg)
    assert st["state"] == "FAILED_MESH", st["quality"]
    assert st["quality"]["new_fail_ratio"] > cfg["select"]["quality"]["max_fail_ratio"] or st["quality"]["inverted"] > 0
    sel = sb.selection(g)
    sel["beads"][0]["blend_mm"] = 1.0
    Ds = bs.derive_obj(m, bs.normalize_input(sel, cfg), cfg)
    Bs = bs.basis(m, Ds, cfg)
    st = bs.design_state(m, X0, bs.morph(X0, Bs, {"B1_W": Bs.nominal()["B1_W"] - 6.0}), Ds.fixed_mask, cfg)
    assert st["state"] == "FAILED_MESH", st["quality"]
    assert st["code"] in ("SELECT_QUALITY_FAIL", "SELECT_MORPH_INVERTED")


def test_summarize_unchanged():
    """v0.14.0 summarize: 정사각 4각·직각 3각 판 = Fail 0, 같은 키(함수 불변)."""
    mesh = sd.plate(nx=10, ny=10, Lx=30.0, Lz=30.0, n_tria_cols=2)
    s = mq.summarize(mesh, DEFAULTS["compare"]["quality"])
    assert set(s) == {"n_elems", "fail_elems", "fail_ratio", "warn_elems", "warn_ratio", "tria_pct", "tria_level",
                      "fail_by", "warn_by", "worst", "max_fail_ratio", "over_limit"}
    assert s["n_elems"] == 120 and s["fail_by"]["min_length"] == 0 and s["worst"]["quad_min_angle"] == pytest.approx(90.0)
    assert s["tria_pct"] == pytest.approx(100.0 * 40 / 120)


# ---------------------------------------------------------------- v0.21.0 V-SH-4 guard_probe(esl_bead_shape_v021.md §4.1)
def _patch(nx=6, ny=4, h=5.0):
    """quad 격자 nx×ny + 위쪽 tria 띠(각 칸 2개) — 평면 z=0."""
    xs = np.arange(nx + 1) * h
    X = [[x, y * h, 0.0] for y in range(ny + 2) for x in xs]
    n1 = nx + 1
    C, T = [], []
    for j in range(ny):
        for i in range(nx):
            a = j * n1 + i
            C.append([a, a + 1, a + 1 + n1, a + n1])
            T.append(4)
    j = ny
    for i in range(nx):
        a = j * n1 + i
        C += [[a, a + 1, a + 1 + n1, -1], [a, a + 1 + n1, a + n1, -1]]
        T += [3, 3]
    return np.asarray(X, float), np.asarray(C, np.int64), np.asarray(T, np.int8)


def test_guard_probe_v_sh_4():
    from esl.morph import core as mc
    X0, C, T = _patch()
    X0b = X0.copy()
    X0b[8, 0] += 4.9                                   # 공칭부터 나쁜 quad 2개(jac ≈ 0.29 — 노드 8 = 1행 1열)
    m_nom = mq.element_metrics(X0b, C, T)
    flip, jlim, tlim = 60.0, 0.3, 10.0
    X1 = X0b.copy()
    X1[17, :2] += 2.5                                  # 노드 17 찌그러뜨림(새 jac < 0.3) + tria 꼭짓점(새 최소각 < 10°)
    X1[40, 0] += 4.0
    am = np.ones(C.shape[0], bool)
    idx = np.flatnonzero(am)
    p = mq.guard_probe(X0b, X1, C, T, idx, flip_deg=flip, jac_min=jlim, tria_angle_min_deg=tlim)
    m1 = mq.element_metrics(X1, C, T)
    q = T == 4
    assert p["n_affected"] == C.shape[0]
    assert p["jac_bad_new"] == int(np.sum(q & (m_nom["jacobian"] >= jlim) & (m1["jacobian"] < jlim)))
    assert p["jac_bad_new"] >= 1
    assert p["jac_min"] == float(m1["jacobian"][q].min())
    bad0 = q & (m_nom["jacobian"] < jlim)
    assert bad0.any() and p["jac_bad_new"] < int(np.sum(q & (m1["jacobian"] < jlim)))   # 공칭부터 나쁜 요소는 안 셈
    t = ~q
    assert p["tri_bad_new"] == int(np.sum(t & (m_nom["min_angle"] >= tlim) & (m1["min_angle"] < tlim)))
    assert p["tri_angle_min"] == float(m1["min_angle"][t].min()) and p["tri_bad_new"] >= 1
    assert p["inverted"] == mq.inverted_count(X0b, X1, C, T, idx, flip_deg=flip)
    mesh = {"x0": X0b, "conn": C, "elem_type": T}
    e = mc.extremes(mesh, X0b, X1, am, {"max_flip_deg": 0.0}, {"area_ratio_min": 10.0, "rot_warn_deg": 0.0})
    assert e["area_ratio_min"] == mc._r(p["area_ratio_min"])
    a0 = mq._area(X0b, C, T.astype(np.int64))
    a1 = mq._area(X1, C, T.astype(np.int64))
    assert p["area_ratio_min"] == float(np.min(a1 / np.maximum(a0, 1e-300)))
    assert p["new_fail_ratio"] is None
    off = mq.guard_probe(X0b, X1, C, T, idx, flip_deg=flip, jac_min=None, tria_angle_min_deg=None)
    assert off["jac_bad_new"] == 0 and off["tri_bad_new"] == 0


def test_guard_probe_inverted_matches_design_state():
    """뒤집힘 = inverted_count = design_state 의 뒤집힘(affected_quality) — 같은 영향 요소에서 같은 수."""
    X0, C, T = _patch()
    X1 = X0.copy()
    X1[8, 0] += 9.0                                    # quad 접힘
    X1[37, 2] += 30.0
    am = np.ones(C.shape[0], bool)
    idx = np.flatnonzero(am)
    p = mq.guard_probe(X0, X1, C, T, idx, flip_deg=60.0, jac_min=0.3, tria_angle_min_deg=10.0,
                       qcfg=DEFAULTS["compare"]["quality"])
    aq = mq.affected_quality({"x0": X0, "conn": C, "elem_type": T}, X1, am, DEFAULTS["compare"]["quality"],
                             flip_deg=60.0)
    assert p["inverted"] == aq["inverted"] == mq.inverted_count(X0, X1, C, T, idx, flip_deg=60.0) >= 2
    assert p["new_fail_ratio"] == aq["new_fail_ratio"]
    b = mq.guard_base(X0, C, T, idx, DEFAULTS["compare"]["quality"])
    p2 = mq.guard_probe(X0, X1, C, T, idx, flip_deg=60.0, jac_min=0.3, tria_angle_min_deg=10.0,
                        qcfg=DEFAULTS["compare"]["quality"], base=b)
    assert p2 == p                                     # 공칭 재사용 = 같은 값
    z = mq.guard_probe(X0, X0, C, T, np.zeros(0, np.int64), flip_deg=60.0, jac_min=0.3, tria_angle_min_deg=10.0)
    assert z["n_affected"] == 0 and z["inverted"] == 0 and z["area_ratio_min"] is None
