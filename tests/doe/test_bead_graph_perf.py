"""V-BG-13 performance (perf, slow): 220k-element synthetic (H6 tiled 2x, 208 876 elements + a strip of the third tile)
-> classify <= 60 s and tracemalloc <= 300 MB, derive (schema 2) <= 3 s, basis 20 variables <= 60 s; 250 001 elements
-> GRAPH_FAILED{TOO_LARGE}."""
import time
import tracemalloc

import numpy as np
import pytest
from _bg_util import CFG, bgr, bs, cf, esl_mesh

pytestmark = [pytest.mark.perf, pytest.mark.slow]


def tiled(n_target=220_000):
    fx = cf.load_fixture("h6")
    X, C, F = fx["x0"], fx["conn"].astype(np.int64), fx["fixed"].astype(np.int64)
    xs, cs, fs = [], [], []
    off = 0
    k = 0
    while sum(c.shape[0] for c in cs) < n_target:
        Xk = X + np.array([1300.0 * k, 0.0, 0.0])
        xs.append(Xk)
        cs.append(np.where(C >= 0, C + off, -1))
        fs.append(F + off)
        off += X.shape[0]
        k += 1
    Xa, Ca, Fa = np.vstack(xs), np.vstack(cs), np.concatenate(fs)
    m = n_target
    keep = Ca[:m]
    used = np.unique(keep[keep >= 0])
    remap = -np.ones(Xa.shape[0], np.int64)
    remap[used] = np.arange(used.size)
    return {"x0": Xa[used], "conn": np.where(keep >= 0, remap[np.maximum(keep, 0)], -1).astype(np.int32),
            "fixed": remap[Fa][remap[Fa] >= 0].astype(np.int32)}


def test_perf_220k():
    fx = tiled()
    mesh = esl_mesh(fx)
    assert mesh["elem_id"].size == 220_000
    import tempfile
    d = tempfile.mkdtemp(prefix="bg_perf_")
    tracemalloc.start()
    t0 = time.perf_counter()
    st = bgr.prep_graph(mesh, fx["fixed"] + 1, CFG, d)
    dt = time.perf_counter() - t0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"classify 220k: {dt:.1f} s, peak {peak / 2 ** 20:.0f} MB, segments {st['n_segments']}")
    assert st["ok"], st
    assert dt <= 60.0 and peak <= 300 * 2 ** 20
    g, lab = bgr.load_graph(d)
    sel, _sym, _w = bgr.auto_seed(g, lab, CFG)
    t0 = time.perf_counter()
    norm, _ = bs.normalize(sel, CFG, mesh=mesh, graph=g, labels=lab)
    D = bgr.derive_obj_v2(mesh, norm, CFG, g, lab, fixed_node_ids=fx["fixed"] + 1)
    dd = time.perf_counter() - t0
    print(f"derive {dd:.2f} s, beads {len(D.beads)}")
    assert dd <= 3.0
    t0 = time.perf_counter()
    B = bs.basis(mesh, D, CFG)
    db = time.perf_counter() - t0
    print(f"basis {len(B.vars)} variables {db:.1f} s")
    assert len(B.vars) >= 20 and db <= 60.0 * len(B.vars) / 20.0


def test_too_large():
    fx = cf.load_fixture("h5")
    mesh = esl_mesh(fx)
    n = int(CFG["select"]["graph"]["limits"]["max_elems"]) + 1   # v0.17.4 기본 600,000(이슈 #63 — 현장 267,470 요소)
    reps = n // mesh["elem_id"].size + 1
    big = {k: (np.tile(v, reps)[:n] if np.ndim(v) == 1 and v.size == mesh["elem_id"].size else v) for k, v in mesh.items()}
    big["conn"] = np.tile(mesh["conn"], (reps, 1))[:n]
    big["elem_type"] = np.tile(mesh["elem_type"], reps)[:n]
    st = bgr.prep_graph(big, (), CFG, "/nonexistent-never-written")
    assert st["ok"] is False and st["code"] == "TOO_LARGE"


# ---------------------------------------------------------------- v0.21.0 V-SH-17 range guard 성능(esl_bead_shape_v021.md §4.5)
def _rules():
    import synth_guard as sg
    return sg.rules()


def test_guard_perf_h6():
    """H6(104k) BD_LOADS guard(후보 기저 포함) ≤ 30 s, 예산 안에서 끝(멈춤 없음)."""
    from _bg_util import prepared
    mesh, g, lab, fx, _d = prepared("h6")
    t0 = time.perf_counter()
    doc = bgr.range_guard_table(mesh, g, lab, fx, CFG, _rules())
    dt = time.perf_counter() - t0
    print(f"guard h6: {dt:.1f} s, entries {len(doc['entries'])}, evals {doc['budget']['evals']}")
    assert doc["budget"]["stopped"] is None and doc["entries"]
    assert dt <= 30.0


def test_guard_perf_real_size():
    """실크기 합성(H6 타일 ≈ 270k 요소): BD_LOADS guard ≤ prep_timeout_s 또는 RG_BUDGET 으로 멈춤(표는 늘 반환 — 준비 READY),
    BD_MATRIX 20 비드 보충(guard_selection, 표 없음 = 전부 unchecked) ≤ matrix_timeout_s(넘으면 RG_BUDGET)."""
    import tempfile
    ru = _rules()
    bc = ru["range_guard"]["budget"]
    fx = tiled(270_000)
    mesh = esl_mesh(fx)
    d = tempfile.mkdtemp(prefix="rg_perf_")
    st = bgr.prep_graph(mesh, fx["fixed"] + 1, CFG, d)
    assert st["ok"], st
    g, lab = bgr.load_graph(d)
    fids = fx["fixed"] + 1
    t0 = time.perf_counter()
    doc = bgr.range_guard_table(mesh, g, lab, fids, CFG, ru)
    dt = time.perf_counter() - t0
    info = bgr.guard_info(doc)
    print(f"guard 270k: {dt:.1f} s, segments {st['n_segments']}, entries {len(doc['entries'])}, "
          f"evals {doc['budget']['evals']}, stopped {doc['budget']['stopped']}")
    assert doc["entries"]
    assert dt <= float(bc["prep_timeout_s"]) or any(w["code"] == "RG_BUDGET" for w in info)
    sel, _sym, _w = bgr.auto_seed(g, lab, CFG)
    sel["beads"] = sel["beads"][:20]
    norm, _ = bgr.normalize_v2(sel, g, CFG, labels=lab, mesh=mesh, shape_rules=ru)
    D = bgr.derive_obj_v2(mesh, norm, CFG, g, lab, fixed_node_ids=fids, range_guard=None, shape_rules=ru)
    B = bs.basis(mesh, D, CFG)
    t0 = time.perf_counter()
    sd = bgr.guard_selection(mesh, D, B, CFG)
    dm = time.perf_counter() - t0
    print(f"guard_selection {len(D.beads)} beads / {len(B.vars)} vars: {dm:.1f} s, stopped {sd['budget']['stopped']}")
    assert dm <= float(bc["matrix_timeout_s"]) * 1.05
    assert sd["budget"]["stopped"] is None or any(w["code"] == "RG_BUDGET" for w in D.warnings)
    # 아주 짧은 준비 시간 → 시간으로 멈춤, 표 반환(남은 후보 skipped budget)
    import synth_guard as sg
    tiny = sg.rules({"range_guard": {"budget": {"prep_timeout_s": 0.001}}})
    d2 = bgr.range_guard_table(mesh, g, lab, fids, CFG, tiny)
    assert d2["budget"]["stopped"] == "time" and any(s["reason"] == "budget" for s in d2["skipped"])
    assert any(w["code"] == "RG_BUDGET" for w in bgr.guard_info(d2))
