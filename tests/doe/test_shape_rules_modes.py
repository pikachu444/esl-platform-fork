"""v0.21.0 BEAD_SHAPE 모드별 단계 시험(esl_bead_shape_v021.md V-SH-12·13) — 새 스냅샷(doe.shape_rules) 의 ①②③ select 준비·행렬과
④ 형상 경로. 모드 차이는 계획 표 열(bs_*)로만(시나리오 이름 분기 없음). 코어(range_guard_table·guard_selection·route)는 실제
모듈 — 감시자(spy)는 실제 함수를 그대로 부르며 인수만 기록한다(스텁 없음). 실패 주입은 soft-fail 시험에서만."""
import hashlib
import json

import pytest
from _bg_util import cf, esl_mesh

from esl.doe import bead_graph as bgr
from esl.doe import bead_select as bsel
from esl.doe import stages as stg
from esl.doe import transfer_plan as tp
from esl.errors import EslError
from esl.mesh import route as mroute

RG_JSON = bgr.RANGE_GUARD_JSON


# ---------------------------------------------------------------- 감시자(실제 코어 호출 + 인수 기록)
class Spy:
    def __init__(self):
        self.calls: dict[str, list] = {}

    def rec(self, name, *a, **kw):
        self.calls.setdefault(name, []).append((a, kw))

    def n(self, name):
        return len(self.calls.get(name, []))

    def last(self, name):
        return self.calls[name][-1]


@pytest.fixture
def core(monkeypatch):
    """bead_graph·bead_select 접점 함수를 실제 함수로 부르는 감시자로 감쌈(인수·반환 기록)."""
    spy = Spy()

    def wrap(mod, name):
        real = getattr(mod, name)

        def f(*a, **kw):
            r = real(*a, **kw)
            spy.rec(name, *a, **kw)
            spy.calls[name][-1] = (a, kw, r)
            return r
        monkeypatch.setattr(mod, name, f)
    for n in ("range_guard_table", "guard_selection", "derive_obj_v2", "w_clamp_table", "load_range_guard"):
        wrap(bgr, n)
    wrap(bsel, "range_check")
    return spy


def _study(tmp_path, mesh, **extra):
    import synth_doe as sd
    cd = tmp_path / "case" / "input"
    cd.mkdir(parents=True, exist_ok=True)
    rad = sd.write_mesh_rad(str(cd / "model.rad"), mesh)
    dirs = [sd.save_entry(str(tmp_path / "lib"), "E0", mesh, "bend", 1.0, seed=0)[0]]
    return {"id": "G1", "scenario": "select", "title": "t", "select_schema": 2, "bead_source": "auto",
            "cfg": {"bead_doe": {"enabled": True}, "opt_run": {"solver": {"backend": "superlu"}}},
            "entries": [{"id": "E0", "dir": dirs[0]}],
            "base": {"entry_id": "E0", "rad_path": rad, "part_title": sd.PART_TITLE, "case_dir": str(cd)}, **extra}


def _runner(tmp_path, doe):
    out = tmp_path / "_doe" / "G1"
    msgs: list[str] = []

    def run(stage, **kw):
        return stg.run_stage({"stage": stage, "out": str(out), "doe": {**doe, **kw}}, msgs.append)
    return out, run, msgs


def _prep(tmp_path, **extra):
    mesh = esl_mesh(cf.load_fixture("h5"))
    doe = _study(tmp_path, mesh, **extra)
    out, run, msgs = _runner(tmp_path, doe)
    run("bd_input")
    return mesh, doe, out, run, msgs


def _auto(out):
    return json.loads((out / "prep" / "select" / "auto_selection.json").read_text(encoding="utf-8"))


SPEC = {"method": "lhs", "n": 3, "seed": 1, "params": [{"name": "B1_D", "lo": 6.0, "hi": 10.0}]}
NEW = {"schema": 1}


# ---------------------------------------------------------------- V-SH-12
def test_new_snapshot_loads_writes_range_guard_not_w_clamp(tmp_path, core):
    """BD_LOADS(① 열 bs_guard basis): 새 스냅샷 = 실제 range_guard_table → range_guard.json(스키마 esl/range_guard/1, scope prep),
    w_clamp.json 안 씀, 결과 range_guard 요약 = 코어 guard_result, RG_FAILED 없음(접점 시그니처 정합)."""
    _m, _d, out, run, _ = _prep(tmp_path, shape_rules=NEW)
    r = run("bd_loads")
    sd_ = out / "prep" / "select"
    assert (sd_ / RG_JSON).is_file() and not (sd_ / "w_clamp.json").exists()
    doc = json.loads((sd_ / RG_JSON).read_text(encoding="utf-8"))
    assert doc["schema"] == bgr.RANGE_GUARD_SCHEMA and doc["scope"] == "prep" and doc["entries"]
    assert not any(str(w).startswith("RG_FAILED") for w in r["warnings"]), r["warnings"]
    assert "failed" not in r["range_guard"] and r["range_guard"] == {**bgr.guard_result(doc), "seconds": r["range_guard"]["seconds"]}
    assert f"prep/select/{RG_JSON}" in r["files"]
    a, kw, _ = core.last("range_guard_table")
    sr = a[5]                                               # 6번째 위치 인수 = 해석된 shape_rules
    assert sr["range_guard"]["jac_min"] == 0.3 and sr["w_partial"] is True and kw["seed"] is None   # ① = 코어 auto_seed
    inp = json.loads((out / "prep" / "input.json").read_text(encoding="utf-8"))
    assert inp["range_guard"]["entries"] == len(doc["entries"])


def test_legacy_snapshot_unchanged(tmp_path, core):
    """키 없는 스냅샷 = v0.20.0: range_guard_table·guard_selection 안 부름, range_guard.json·결과 키 없음, basis.json 에 새 키 없음,
    range_check 는 모든 변수(only=None)."""
    _m, doe, out, run, _ = _prep(tmp_path)
    r = run("bd_loads")
    assert core.n("range_guard_table") == 0 and "range_guard" not in r
    assert not (out / "prep" / "select" / RG_JSON).exists()
    assert core.last("w_clamp_table")[1]["shape_rules"] is None
    auto = _auto(out)
    doe["selection"] = {"rev": 1, "sha256": auto["sha256"], "input": auto["selection"]}
    run("bd_matrix", rev=1, spec=SPEC, selection=doe["selection"])
    assert core.n("guard_selection") == 0
    d = out / "select" / auto["sha256"][:12]
    bj = json.loads((d / "basis.json").read_text(encoding="utf-8"))
    assert "shape_rules" not in bj and "range_guard_sha256" not in bj and not (d / RG_JSON).exists()
    kw = core.last("derive_obj_v2")[1]                       # BD_MATRIX derive = v0.20.0 호출 그대로
    assert "shape_rules" not in kw and "range_guard" not in kw
    assert core.last("range_check")[1].get("only") is None
    rows = json.loads((d / "params.json").read_text(encoding="utf-8"))["params"]
    assert rows and not any("guard" in x for x in rows)


def test_matrix_uses_prep_table_and_supplements(tmp_path, core):
    """BD_MATRIX: derive 가 준비 표·shape_rules 를 받아 seed 변수에 적용(unchecked 아님 — 표 머리 graph·cfg·fixed·exclude sha 가
    derive 와 같음), API derive(derive_v2) 도 같은 표 적용, guard_selection 보충 → select/<sha12>/range_guard.json(scope selection),
    params.json 그래프 행 guard, basis.json shape_rules·range_guard_sha256, elems 변수만 range_check(only=), 같은 sha 재사용."""
    m, doe, out, run, msgs = _prep(tmp_path, shape_rules=NEW)
    run("bd_loads")
    auto = _auto(out)
    sha = auto["sha256"]
    doe["selection"] = {"rev": 1, "sha256": sha, "input": auto["selection"]}
    r = run("bd_matrix", rev=1, spec=SPEC, selection=doe["selection"])
    prep_doc = json.loads((out / "prep" / "select" / RG_JSON).read_text(encoding="utf-8"))
    a, kw, D = core.last("derive_obj_v2")
    assert kw["range_guard"] == prep_doc and kw["shape_rules"]["schema"] == 1 and kw["w_clamp"] is None
    rows0 = bgr.params_rows_v2(D)
    assert rows0 and all(x["guard"]["state"] != "unchecked" for x in rows0 if "guard" in x), \
        [(x["name"], x["guard"]) for x in rows0]                     # 준비 표가 seed 변수 전부에 맞음
    g, lab = bgr.load_graph(str(out / "prep"))
    cfg = a[2]                                               # derive_obj_v2 위치 인수 cfg
    norm, _ = bgr.normalize_v2(auto["selection"], g, cfg, labels=lab, mesh=m, shape_rules=kw["shape_rules"])
    api = bgr.derive_v2(a[0], norm, cfg, g, lab, fixed_scan=(), range_guard=bgr.load_range_guard(str(out / "prep")),
                        shape_rules=kw["shape_rules"])
    assert [x.get("guard") for x in api["params"]] == [x.get("guard") for x in rows0]   # API derive = BD_MATRIX derive
    d = out / "select" / sha[:12]
    sel_doc = json.loads((d / RG_JSON).read_text(encoding="utf-8"))
    assert sel_doc["scope"] == "selection" and sel_doc["selection_sha256"] == sha
    assert r["range_guard"] == bgr.guard_result(sel_doc, r["range_guard"]["seconds"])
    assert core.last("guard_selection")[1]["only"] == []                # 모두 표에 맞음 → 단일 보충 없음(조합만)
    bj = json.loads((d / "basis.json").read_text(encoding="utf-8"))
    assert bj["shape_rules"] == 1 and bj["range_guard_sha256"] == hashlib.sha256(
        (out / "prep" / "select" / RG_JSON).read_bytes()).hexdigest()
    rows = json.loads((d / "params.json").read_text(encoding="utf-8"))["params"]
    assert rows and all("guard" in x for x in rows)
    assert core.last("range_check")[1]["only"] == []                   # elems 변수만(그래프 변수 제외)
    msgs.clear()
    run("bd_matrix", rev=2, spec=SPEC, selection=doe["selection"])
    assert any("재사용" in s for s in msgs)
    (out / "prep" / "select" / RG_JSON).write_text(json.dumps({**prep_doc, "entries": []}, sort_keys=True), encoding="utf-8")
    msgs.clear()
    n0 = core.n("guard_selection")
    run("bd_matrix", rev=3, spec=SPEC, selection=doe["selection"])
    assert not any("재사용" in s for s in msgs)
    assert core.n("guard_selection") == n0 + 1 and core.last("guard_selection")[1]["only"]   # 표 비면 unchecked 보충


def test_select_grid_outside_guard(tmp_path, core):
    """BD_SELECT_GRID: 안 값이 변수 행 guard.usable 밖이면 셀 경고 RG_OUTSIDE_GUARD(경고만 — 상태 불변), 안이면 없음."""
    _m, doe, out, run, _ = _prep(tmp_path, shape_rules=NEW)
    run("bd_loads")
    auto = _auto(out)
    doe["selection"] = {"rev": 1, "sha256": auto["sha256"], "input": auto["selection"]}
    run("bd_matrix", rev=1, spec=SPEC, selection=doe["selection"])
    rows = json.loads((out / "select" / auto["sha256"][:12] / "params.json").read_text(encoding="utf-8"))["params"]
    r0 = next(x for x in rows if (x.get("guard") or {}).get("usable"))
    u = r0["guard"]["usable"]
    mx = json.loads((out / "doe" / "1" / "matrix.json").read_text(encoding="utf-8"))
    k = next(i for i, x in enumerate(mx["designs"]) if x["id"] != stg.BASELINE)
    mx["designs"][k]["values"] = {**mx["designs"][k]["values"], r0["name"]: float(u[1]) + 0.5}
    (out / "doe" / "1" / "matrix.json").write_text(json.dumps(mx), encoding="utf-8")
    run("bd_select_grid", rev=1)
    man = json.loads((out / "doe" / "1" / "grid" / "grid_manifest.json").read_text(encoding="utf-8"))
    c0 = next(x for x in man["cells"] if x["id"] == mx["designs"][k]["id"])
    og = [w for w in c0.get("warnings") or [] if isinstance(w, dict) and w.get("code") == "RG_OUTSIDE_GUARD"]
    assert og and og[0]["vars"][0]["name"] == r0["name"]
    assert bgr.outside_guard(rows, {r0["name"]: float(u[0])}) is None


def test_guard_core_failure_is_soft(tmp_path, monkeypatch):
    """코어 점검 중 실제 예외(주입) → 준비는 계속, 경고 RG_FAILED{code}, range_guard.json 없음(derive 는 unchecked)."""
    def boom(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(bgr, "range_guard_table", boom)
    _m, _d, out, run, _ = _prep(tmp_path, shape_rules=NEW)
    r = run("bd_loads")
    assert not (out / "prep" / "select" / RG_JSON).exists()
    assert r["range_guard"]["failed"] == "ValueError" and "entries" not in r["range_guard"]
    assert any(str(w).startswith("RG_FAILED") and "ValueError" in str(w) for w in r["warnings"])


def test_interface_signatures_bind():
    """접점 정합: 백엔드·단계가 부르는 형태가 코어 실제 시그니처에 묶임(조용히 빠지는 키워드 없음)."""
    import inspect
    bind = [(bgr.range_guard_table, (1, 2, 3, 4, 5, 6), {"seed": None, "exclude_segs": None}),
            (bgr.guard_selection, (1, 2, 3, 4), {"only": []}),
            (bgr.derive_obj_v2, (1, 2, 3, 4, 5), {"fixed_node_ids": (), "mesh_sha256": None, "shape_rules": None,
                                                  "range_guard": None, "w_clamp": None}),
            (bgr.derive_v2, (1, 2, 3, 4, 5), {"frame": None, "fixed_scan": (), "bead": None, "w_clamp": None,
                                              "range_guard": None, "shape_rules": None}),
            (bgr.normalize_v2, (1, 2, 3), {"labels": None, "mesh": None, "shape_rules": None}),
            (bgr.w_clamp_table, (1, 2, 3, 4, 5), {"shape_rules": None}),
            (bgr.write_range_guard, (1, 2), {"guard": None}), (bgr.load_range_guard, (1,), {}),
            (bgr.guard_result, (1, 2), {}), (bgr.guard_info, (1,), {}), (bgr.outside_guard, (1, 2), {}),
            (bsel.range_check, (1, 2, 3, 4), {"only": []}),
            (mroute.choose, (1, 2, 3), {"relaxed_enabled": True}), (mroute.rank_flag, (1, 2), {})]
    for fn, a, kw in bind:
        inspect.signature(fn).bind(*a, **kw)
    for name in ("_mroute", "_kwcall"):                     # 통합 전 대체 경로 제거됨
        assert not hasattr(stg, name)


def test_columns_drive_behavior(tmp_path, core, monkeypatch):
    """모드 차이 = 계획 표 열: 같은 스냅샷이라도 열 bs_guard 가 none 이면 점검 없음·w_clamp 경로(시나리오 이름 분기 없음). 열 bs_guard 가
    basis 인 행(case_once·bmesh_once·step_once)은 같은 코드 경로를 탄다."""
    for pid in ("case_once", "bmesh_once", "step_once"):
        assert tp.PLANS[pid]["bs_guard"] == "basis" and tp.PLANS[pid]["bs_wpart"] == "graph"
    saved = dict(tp.PLANS["case_once"])
    monkeypatch.setitem(tp.PLANS, "case_once", dict(saved, bs_guard="none"))
    _m, _d, out, run, _ = _prep(tmp_path, shape_rules=NEW)
    run("bd_loads")
    assert core.n("range_guard_table") == 0 and not (out / "prep" / "select" / RG_JSON).exists()


def test_range_guard_off_uses_legacy_w_clamp(tmp_path, core):
    """shape_rules.range_guard.enabled false → 점검표 없음, W 기본 범위는 w_clamp 표 경로(w_partial 이면 S_W 후보 — shape_rules 전달),
    derive 가 w_clamp 를 받음."""
    _m, doe, out, run, _ = _prep(tmp_path, shape_rules={"schema": 1, "range_guard": {"enabled": False}})
    run("bd_loads")
    assert core.n("range_guard_table") == 0 and not (out / "prep" / "select" / RG_JSON).exists()
    assert core.last("w_clamp_table")[1]["shape_rules"]["w_partial"] is True
    auto = _auto(out)
    doe["selection"] = {"rev": 1, "sha256": auto["sha256"], "input": auto["selection"]}
    run("bd_matrix", rev=1, spec=SPEC, selection=doe["selection"])
    kw = core.last("derive_obj_v2")[1]
    assert core.n("guard_selection") == 0 and kw["range_guard"] is None
    assert kw["w_clamp"] == bgr.load_w_clamp(str(out / "prep"))


def test_invalid_block_config_invalid(tmp_path):
    """잘못된 스냅샷 블록 → CONFIG_INVALID(준비 첫 단계에서)."""
    mesh = esl_mesh(cf.load_fixture("h5"))
    doe = _study(tmp_path, mesh, shape_rules={"range_guard": {"jac_min": 2}})
    _out, run, _ = _runner(tmp_path, doe)
    with pytest.raises(EslError) as ei:
        run("bd_input")
        run("bd_loads")
    assert ei.value.code == "CONFIG_INVALID"


# ---------------------------------------------------------------- V-SH-12 ③ 새(select_base step) — seed = _sel_auto_step
def _gm():
    from esl.doe import mesh_gmsh as mg
    return mg


needs_gmsh = pytest.mark.skipif(not _gm().available()[0], reason="gmsh 없음")


@needs_gmsh
def test_step_seed_table_matches_matrix(tmp_path, core):
    """③: BD_LOADS 점검 후보 seed = _sel_auto_step 파일(fixed_user 포함), 표 fixed_sha256 = BD_MATRIX derive 와 같아 seed 변수 전부
    적용(unchecked 없음), ③ 결과 mesh.quality·route 기록."""
    import synth_compare as scmp
    import synth_doe as sd
    import test_step_graph as tsg
    a = sd.plate(nx=20, ny=15, Lx=tsg.LX, Lz=tsg.LZ)
    (tmp_path / "up").mkdir()
    step = scmp.plate_step(str(tmp_path / "up" / "b.step"), 2, Lx=tsg.LX, Lz=tsg.LZ, depth=5.0)
    doe = tsg._study(tmp_path, step, a, shape_rules=NEW)
    out = tmp_path / "_doe" / "S1"
    run = tsg._runner(out, doe)
    run("bd_input")
    run("bd_mesh0")
    r = run("bd_loads")
    assert r["graph"]["ok"] and not any(str(w).startswith("RG_FAILED") for w in r["warnings"]), r["warnings"]
    a_, kw, _doc = core.last("range_guard_table")
    auto = json.loads((out / "prep" / "select" / "auto_selection.json").read_text(encoding="utf-8"))
    assert kw["seed"] == auto["selection"] and "fixed_user" in kw["seed"]
    assert len(a_[3]) == 0                                   # ③ derive 고정 = _sel_fixed_ids(빈) — 이전 고정은 seed fixed_user
    inp = json.loads((out / "prep" / "input.json").read_text(encoding="utf-8"))
    assert isinstance(inp["mesh"].get("quality"), dict) and inp["mesh"]["route"]["path"] == "cad"
    if not auto["selection"]["beads"]:
        pytest.skip("seed 비드 없음")
    doe["selection"] = {"rev": 1, "sha256": auto["sha256"], "input": auto["selection"]}
    run("bd_matrix", rev=1, spec={"method": "lhs", "n": 3, "seed": 1, "params": [{"name": "B1_D", "lo": 3.0, "hi": 7.0}]})
    D = core.last("derive_obj_v2")[2]
    rows = bgr.params_rows_v2(D)
    assert rows and all(x["guard"]["state"] != "unchecked" for x in rows if "guard" in x), [x.get("guard") for x in rows]


# ---------------------------------------------------------------- V-SH-13 (④ 경로 — 순위·직행 계획, 실제 esl.mesh.route)
@pytest.fixture
def route():
    return mroute


class _C:
    """_route_of 가 읽는 최소 Ctx(스냅샷 shape_rules + 계획 표)."""

    def __init__(self, shape, scn="compare", step=False):
        self.D = {"shape_rules": shape, "scenario": scn}
        self.cfg = __import__("esl.doe", fromlist=["DEFAULTS"]).DEFAULTS
        self.scn = scn
        self._rel = None


def _route_case(tmp_path, monkeypatch, route, *, shape, faces, mb, mode="auto", source="step", rx=True, plan_col="shapes"):
    p = tmp_path / "m.step"
    p.write_bytes(b"x" * int(mb * 1048576))
    c = _C(shape)
    c.p = lambda rel: str(p)
    monkeypatch.setattr(stg, "_shape", lambda cc: tp.resolve_shape(cc.D["shape_rules"]) if cc.D["shape_rules"] is not None else None)
    monkeypatch.setattr(stg, "_bs", lambda cc, col: plan_col if cc.D["shape_rules"] is not None else "none")
    monkeypatch.setattr(stg.mg, "step_scan", lambda src, kinds=(): {"n_faces": faces})
    return stg._route_of(c, {"rel": "m.step", "source": source}, {"mesh": {"cad_relaxed": {"enabled": rx}}}, mode)


def test_route_of_threshold_and_legacy(tmp_path, monkeypatch, route):
    """§4 경로 판정: 면 경계(1499/1500)·min_step_mb·relaxed 꺼짐·열 none·옛 스냅샷·mesh 형상·mode 가 auto/cad 아님 → 직행 아님·None."""
    sh = {"schema": 1}
    r = _route_case(tmp_path, monkeypatch, route, shape=sh, faces=1500, mb=0.01)
    assert r["path"] == "cad_relaxed" and r["n_faces"] == 1500 and r["min_faces"] == 1500
    assert _route_case(tmp_path, monkeypatch, route, shape=sh, faces=1499, mb=0.01)["path"] == "cad"
    assert _route_case(tmp_path, monkeypatch, route, shape=sh, faces=None, mb=0.01)["path"] == "cad"
    assert _route_case(tmp_path, monkeypatch, route, shape=sh, faces=10, mb=0.01)["path"] == "cad"
    assert _route_case(tmp_path, monkeypatch, route, shape={"mesh_route": {"relaxed_direct": {"min_step_mb": 0.005}}},
                       faces=10, mb=0.01)["path"] == "cad_relaxed"
    assert _route_case(tmp_path, monkeypatch, route, shape=sh, faces=9999, mb=0.01, rx=False)["path"] == "cad"
    assert _route_case(tmp_path, monkeypatch, route, shape={"mesh_route": {"relaxed_direct": {"enabled": False}}},
                       faces=9999, mb=0.01)["path"] == "cad"
    assert _route_case(tmp_path, monkeypatch, route, shape=sh, faces=9999, mb=0.01, plan_col="none") is None
    assert _route_case(tmp_path, monkeypatch, route, shape=None, faces=9999, mb=0.01) is None
    assert _route_case(tmp_path, monkeypatch, route, shape=sh, faces=9999, mb=0.01, source="mesh") is None
    assert _route_case(tmp_path, monkeypatch, route, shape=sh, faces=9999, mb=0.01, mode="remesh") is None
    assert _route_case(tmp_path, monkeypatch, route, shape=sh, faces=9999, mb=0.01, mode="cad")["path"] == "cad_relaxed"
    assert stg._route_row({"path": "cad", "reason": None, "n_faces": 3, "min_faces": 1500, "extra": 1}) == \
        {"path": "cad", "reason": None, "n_faces": 3, "min_faces": 1500}


def test_mq_rank_flags(monkeypatch, route):
    """③ 순위 경고(§5): 품질 Fail 비율·tria 가 기준을 넘는 형상만 mq(순위 순서 그대로), best_clean_mq = 경고 없는 최상위, 기준값 경계는
    통과, 열 none·옛 스냅샷 = 표시 없음."""
    sh = tp.resolve_shape({"schema": 1})
    c = _C({"schema": 1})
    monkeypatch.setattr(stg, "_shape", lambda cc: sh)
    monkeypatch.setattr(stg, "_bs", lambda cc, col: "shapes")
    rows = [{"id": "d001"}, {"id": "d002"}, {"id": "d003"}, {"id": "d004"}]
    res = {"d001": {"status": "READY", "quality": {"fail_ratio": 0.11, "tria_pct": 5.0}},
           "d002": {"status": "READY", "quality": {"fail_ratio": 0.10, "tria_pct": 5.0}},       # 경계 = 통과
           "d003": {"status": "READY", "quality": {"fail_ratio": 0.0, "tria_pct": 15.5}},
           "d004": {"status": "FAILED_MESH", "quality": {"fail_ratio": 0.9, "tria_pct": 90.0}}}
    stg._cmp_mq_flags(c, rows, res)
    assert "mq" in res["d001"] and "mq" not in res["d002"] and "mq" in res["d003"] and "mq" not in res["d004"]
    R = {"ranking": [{"id": "d001"}, {"id": "d003"}, {"id": "d002"}]}
    shapes = {"d000": {"name": "기준", "mq": {"fail_ratio": 0.2, "tria_pct": 1.0}},
              "d001": {"name": "a", "mq": {"fail_ratio": 0.11, "tria_pct": 5.0}},
              "d002": {"name": "b"}, "d003": {"name": "c", "mq": {"fail_ratio": 0.0, "tria_pct": 15.5}}}
    out = stg._cmp_mq_rank(c, R, shapes)
    assert [x["id"] for x in R["ranking"]] == ["d001", "d003", "d002"]                 # 순위 유지(Q-SH-3)
    assert out["best_clean_mq"] == "d002" and out["warning"]["scope"] == "shapes" and out["warning"]["n"] == 3
    assert [r["id"] for r in out["rows"]] == ["d000", "d001", "d003"] and "MESH_QUALITY_RANK" in R["ranking"][0]["warn"]
    monkeypatch.setattr(stg, "_bs", lambda cc, col: "none")
    res2 = {"d001": {"status": "READY", "quality": {"fail_ratio": 0.9, "tria_pct": 90.0}}}
    stg._cmp_mq_flags(c, rows, res2)
    assert "mq" not in res2["d001"] and stg._cmp_mq_rank(c, {"ranking": [{"id": "d001"}]}, shapes) is None
    assert route.rank_flag(None, sh["mesh_route"]["rank_quality"]) is None


# ---------------------------------------------------------------- V-SH-13 ④ 실제 gmsh(합성 STEP — min_faces 를 낮춰 대형 판정)
def _gm():
    from esl.doe import mesh_gmsh as mg
    return mg


needs_gmsh = pytest.mark.skipif(not _gm().available()[0], reason="gmsh 없음")


def _cmp_doe(tmp_path, sid, p1, *, shape=None, **kw):
    import test_mesh_relaxed_v0174 as t174
    doe = t174._doe(tmp_path, sid, p1, **kw)
    if shape is not None:
        doe["shape_rules"] = shape
    return doe


@needs_gmsh
def test_direct_relaxed_skips_cad_and_bytes_equal_legacy(tmp_path, route, monkeypatch):
    """대형 판정(min_faces 낮춤) → cad 세션 호출 0, attempts [cad SKIPPED relaxed_direct, cad_relaxed READY], route·MESH_ROUTE_RELAXED,
    직행 메시 = 지금 cad 실패 뒤 cad_relaxed 메시와 바이트 같음. 옛 스냅샷(키 없음)·작은 STEP = 형상 행에 route 없음/cad."""
    import synth_many as smany
    import test_step_compare as tsc

    from esl.library import _util as U
    p1 = smany.many_dimple_solid_step(tmp_path / "up" / "u1" / "s.step")
    n_faces = _gm().step_scan(p1, ())["n_faces"]
    # 옛 스냅샷: cad 첫 시도 → 자식 안 cad_relaxed
    out0 = tmp_path / "_doe" / "L0"
    tsc._run(out0, _cmp_doe(tmp_path / "a", "L0", p1), stages=("bd_input", "bd_mesh0"))
    s0 = tsc._shape(out0, "d001")
    assert s0["status"] == "READY" and s0["mesh_path"] == "cad_relaxed" and "route" not in s0
    # 새 스냅샷·낮춘 min_faces: 직행(cad 호출 0)
    called = []
    real_one = stg._cmp_mesh_one
    monkeypatch.setattr(stg, "_cmp_mesh_one", lambda *a, **k: called.append(a[3]["id"] if False else 1) or real_one(*a, **k))
    sh = {"schema": 1, "mesh_route": {"relaxed_direct": {"min_faces": max(2, n_faces // 2)}}}
    out1 = tmp_path / "_doe" / "N1"
    r, _ = tsc._run(out1, _cmp_doe(tmp_path / "b", "N1", p1, shape=sh), stages=("bd_input", "bd_mesh0"))
    s1 = tsc._shape(out1, "d001")
    d0 = tsc._shape(out1, "d000")
    assert s1["status"] == "READY" and s1["mesh_method"] == "cad" and s1["mesh_path"] == "cad_relaxed"
    assert s1["route"]["path"] == "cad_relaxed" and s1["route"]["n_faces"] == n_faces
    assert [(a["stage"], a["status"]) for a in s1["attempts"]] == [("cad", "SKIPPED"), ("cad_relaxed", "READY")]
    assert s1["attempts"][0]["reason"] == "relaxed_direct"
    assert called.count(1) == 1                                  # 기준(d000, 작은 평판)만 cad — 큰 모델 d001 은 cad 세션 0
    assert any(i.startswith("MESH_ROUTE_RELAXED") and "d001" in i for i in r["bd_mesh0"].get("info", []))
    assert d0["route"]["path"] == "cad"                          # 작은 STEP → cad, 옛 행 + route 키만
    assert {k: v for k, v in d0.items() if k != "route"}.keys() == tsc._shape(out0, "d000").keys()
    m0 = U.sha256_file(str(out0 / "prep" / "shapes" / "d001" / "mesh" / "mesh.npz"))
    m1 = U.sha256_file(str(out1 / "prep" / "shapes" / "d001" / "mesh" / "mesh.npz"))
    assert m0 == m1                                              # 같은 설정 → 같은 메시(바이트)


@needs_gmsh
@pytest.mark.parametrize("mode", ["auto", "cad"])
def test_direct_relaxed_failure_paths(tmp_path, route, monkeypatch, mode):
    """직행 실패(주입): auto → cad·refine_local·refine_global 을 SKIPPED(relaxed_direct) 로 두고 freeform→tria 로 계속, mode cad → 형상 실패 행."""
    import synth_many as smany
    import test_step_compare as tsc

    from esl.errors import EslError
    p1 = smany.many_dimple_solid_step(tmp_path / "up" / "u1" / "s.step")
    real = _gm().run_isolated
    n = {"direct": 0}

    def fake(path, td, h, cfg, props, **kw):
        if (cfg["mesh"].get("cad_relaxed") or {}).get("direct") and "d001" in str(td):
            n["direct"] += 1
            raise EslError("MESH_FAILED", "injected direct failure")
        return real(path, td, h, cfg, props, **kw)
    monkeypatch.setattr(_gm(), "run_isolated", fake)
    sh = {"schema": 1, "mesh_route": {"relaxed_direct": {"min_faces": 2}}}
    doe = _cmp_doe(tmp_path, "F1", p1, shape=sh, mesh_mode=mode, mesh_ladder=["cad", "refine_local", "refine_global", "freeform"],
                   mesh={"fallback": {"enabled": True}})
    out = tmp_path / "_doe" / "F1"
    try:
        tsc._run(out, doe, stages=("bd_input", "bd_mesh0"))
    except EslError:
        pass                                                      # 모든 형상 실패 = 단계 실패(mode cad)
    s = tsc._shape(out, "d001")
    assert n["direct"] == 1
    st = {a["stage"]: a for a in s["attempts"]}
    assert st["cad"]["status"] == "SKIPPED" and st["cad_relaxed"]["status"] == "FAILED_MESH"
    if mode == "cad":
        assert s["status"] == "FAILED_MESH" and len(s["attempts"]) == 2
    else:
        for x in ("refine_local", "refine_global"):
            assert st[x]["status"] == "SKIPPED" and st[x]["reason"] == "relaxed_direct"
        assert any(a["stage"] in ("freeform", "tria") for a in s["attempts"])
