"""v0.21.0 BEAD_SHAPE 모드별 단계 시험(esl_bead_shape_v021.md V-SH-12·13) — 새 스냅샷(doe.shape_rules) 의 ①②③ select 준비·행렬과
④ 형상 경로. 모드 차이는 계획 표 열(bs_*)로만(시나리오 이름 분기 없음). impl-geom 코어(range_guard_table·guard_selection·
route.choose·rank_flag)는 통합 전이라 시험에서 스텁으로 끼움(monkeypatch raising=False — 실제 코어가 있으면 그 위에 덮어씀)."""
import json
import os
import sys
import types

import pytest
from _bg_util import cf, esl_mesh

from esl.doe import bead_graph as bgr
from esl.doe import bead_select as bsel
from esl.doe import stages as stg
from esl.doe import transfer_plan as tp
from esl.errors import EslError

RG_JSON = "range_guard.json"


# ---------------------------------------------------------------- 코어 스텁(통합 전 impl-geom 접점)
class Spy:
    def __init__(self):
        self.calls: dict[str, list] = {}

    def rec(self, name, *a, **kw):
        self.calls.setdefault(name, []).append((a, kw))

    def n(self, name):
        return len(self.calls.get(name, []))


@pytest.fixture
def core(monkeypatch):
    """range_guard_table·write/load_range_guard·guard_selection 스텁 + derive/params_rows/range_check 감시자."""
    spy = Spy()
    monkeypatch.setattr(bgr, "RANGE_GUARD_JSON", RG_JSON, raising=False)

    def table(mesh, graph, labels, fids, cfg, *, shape_rules=None, scope="prep"):
        spy.rec("range_guard_table", shape_rules=shape_rules, scope=scope)
        names = sorted(g["name"] for g in (getattr(graph, "beads", None) or []) if isinstance(g, dict)) or ["B1_D"]
        return {"schema": "esl/range_guard/1", "scope": scope,
                "entries": [{"name": n, "state": "limited", "usable": [6.0, 8.0]} for n in names[:1]],
                "combos": [], "skipped": [], "budget": {"evals": 7, "stopped": None}}

    def write(path, doc, guard=None):
        spy.rec("write_range_guard", path=path)
        with open(guard(path) if guard else path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, sort_keys=True)

    def load(prep_dir):
        p = os.path.join(prep_dir, "select", RG_JSON)
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)

    def gsel(mesh, D, B, cfg, *, shape_rules=None, fixed_node_ids=None, only=None, table=None):
        spy.rec("guard_selection", only=list(only or []), table=table is not None, shape_rules=shape_rules)
        return {"schema": "esl/range_guard/1", "scope": "selection", "entries": [], "combos": [], "skipped": [],
                "budget": {"evals": 3, "stopped": None}}
    monkeypatch.setattr(bgr, "range_guard_table", table, raising=False)
    monkeypatch.setattr(bgr, "write_range_guard", write, raising=False)
    monkeypatch.setattr(bgr, "load_range_guard", load, raising=False)
    monkeypatch.setattr(bgr, "guard_selection", gsel, raising=False)

    real_derive, real_rows, real_rc = bgr.derive_obj_v2, bgr.params_rows_v2, bsel.range_check

    def derive(mesh, norm, cfg, graph, labels, *, fixed_node_ids=None, mesh_sha256=None, w_clamp=None, range_guard=None,
               shape_rules=None):
        spy.rec("derive", range_guard=range_guard, shape_rules=shape_rules, w_clamp=w_clamp)
        return real_derive(mesh, norm, cfg, graph, labels, fixed_node_ids=fixed_node_ids, mesh_sha256=mesh_sha256,
                           w_clamp=w_clamp)

    def rows(D, cfg=None):
        out = real_rows(D, cfg)
        for i, r in enumerate(out):                     # 코어 행 키 guard(통합 후엔 코어가 채움)
            r.setdefault("guard", {"state": "unchecked" if i == 0 else "ok"})
        return out

    def rcheck(mesh, D, B, cfg, only=None):
        spy.rec("range_check", only=only)
        return real_rc(mesh, D, B, cfg)
    monkeypatch.setattr(bgr, "derive_obj_v2", derive)
    monkeypatch.setattr(bgr, "params_rows_v2", rows)
    monkeypatch.setattr(bsel, "range_check", rcheck)
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


SPEC = {"method": "lhs", "n": 3, "seed": 1, "params": [{"name": "B1_D", "lo": 6.0, "hi": 10.0}]}


# ---------------------------------------------------------------- V-SH-12
def test_new_snapshot_loads_writes_range_guard_not_w_clamp(tmp_path, core):
    """BD_LOADS(① 열 bs_guard basis): 새 스냅샷 = range_guard.json(스키마 esl/range_guard/1, scope prep), w_clamp.json 안 씀,
    결과 range_guard 요약(시간 값은 seconds 만)."""
    _m, _d, out, run, _ = _prep(tmp_path, shape_rules={"schema": 1})
    r = run("bd_loads")
    sd_ = out / "prep" / "select"
    assert (sd_ / RG_JSON).is_file() and not (sd_ / "w_clamp.json").exists()
    assert json.loads((sd_ / RG_JSON).read_text(encoding="utf-8"))["scope"] == "prep"
    assert r["range_guard"]["entries"] == 1 and r["range_guard"]["limited"] == 1 and r["range_guard"]["evals"] == 7
    assert f"prep/select/{RG_JSON}" in r["files"]
    sr = core.calls["range_guard_table"][0][1]["shape_rules"]
    assert sr["range_guard"]["jac_min"] == 0.3 and sr["w_partial"] is True and core.calls["range_guard_table"][0][1]["scope"] == "prep"


def test_legacy_snapshot_unchanged(tmp_path, core):
    """키 없는 스냅샷 = v0.20.0: range_guard_table·guard_selection 안 부름, range_guard.json·결과 키 없음, basis.json 에 새 키 없음."""
    _m, doe, out, run, _ = _prep(tmp_path)
    r = run("bd_loads")
    assert core.n("range_guard_table") == 0 and "range_guard" not in r
    assert not (out / "prep" / "select" / RG_JSON).exists()
    auto = json.loads((out / "prep" / "select" / "auto_selection.json").read_text(encoding="utf-8"))
    sel = auto["selection"]
    doe["selection"] = {"rev": 1, "sha256": auto["sha256"], "input": sel}
    run("bd_matrix", rev=1, spec=SPEC, selection=doe["selection"])
    assert core.n("guard_selection") == 0
    d = out / "select" / auto["sha256"][:12]
    bj = json.loads((d / "basis.json").read_text(encoding="utf-8"))
    assert "shape_rules" not in bj and "range_guard_sha256" not in bj and not (d / RG_JSON).exists()
    assert all(c[1]["shape_rules"] is None and c[1]["range_guard"] is None for c in core.calls["derive"])


def test_matrix_uses_prep_table_and_supplements(tmp_path, core):
    """BD_MATRIX: derive 가 준비 표(range_guard)·shape_rules 를 받음, 표에 없는 unchecked 변수·조합은 guard_selection 으로 보충 →
    select/<sha12>/range_guard.json(scope selection), params.json 행에 guard, basis.json shape_rules·range_guard_sha256,
    elems 변수는 range_check(only=)로 경고만, 같은 sha 재사용(점검표가 같으면)."""
    _m, doe, out, run, msgs = _prep(tmp_path, shape_rules={"schema": 1})
    run("bd_loads")
    auto = json.loads((out / "prep" / "select" / "auto_selection.json").read_text(encoding="utf-8"))
    sha = auto["sha256"]
    doe["selection"] = {"rev": 1, "sha256": sha, "input": auto["selection"]}
    r = run("bd_matrix", rev=1, spec=SPEC, selection=doe["selection"])
    prep_doc = json.loads((out / "prep" / "select" / RG_JSON).read_text(encoding="utf-8"))
    kw = core.calls["derive"][-1][1]
    assert kw["range_guard"] == prep_doc and kw["shape_rules"]["schema"] == 1 and kw["w_clamp"] is None     # w_clamp.json 안 읽음
    d = out / "select" / sha[:12]
    assert json.loads((d / RG_JSON).read_text(encoding="utf-8"))["scope"] == "selection"
    gs = core.calls["guard_selection"][-1][1]
    assert gs["only"] == sorted(gs["only"]) and gs["table"] is True and r["range_guard"]["evals"] == 3
    bj = json.loads((d / "basis.json").read_text(encoding="utf-8"))
    import hashlib
    assert bj["shape_rules"] == 1 and bj["range_guard_sha256"] == hashlib.sha256(
        (out / "prep" / "select" / RG_JSON).read_bytes()).hexdigest()
    rows = json.loads((d / "params.json").read_text(encoding="utf-8"))["params"]
    assert rows and all("guard" in x for x in rows)
    assert core.calls["range_check"][-1][1]["only"] is not None            # elems 변수만(그래프 변수 제외)
    msgs.clear()
    run("bd_matrix", rev=2, spec=SPEC, selection=doe["selection"])
    assert any("재사용" in s for s in msgs)
    # 준비 점검표가 바뀌면(sha 불일치) 다시 계산
    (out / "prep" / "select" / RG_JSON).write_text(json.dumps({**prep_doc, "entries": []}, sort_keys=True), encoding="utf-8")
    msgs.clear()
    run("bd_matrix", rev=3, spec=SPEC, selection=doe["selection"])
    assert not any("재사용" in s for s in msgs)


def test_guard_core_failure_is_soft(tmp_path, core, monkeypatch):
    """코어 점검 실패(예외)·코어 없음 → 준비는 계속, 경고 RG_FAILED, range_guard.json 없음(derive 는 unchecked)."""
    def boom(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(bgr, "range_guard_table", boom, raising=False)
    _m, _d, out, run, _ = _prep(tmp_path, shape_rules={"schema": 1})
    r = run("bd_loads")
    assert not (out / "prep" / "select" / RG_JSON).exists()
    assert r["range_guard"]["failed"] == "ValueError" and "entries" not in r["range_guard"]
    assert any(str(w).startswith("RG_FAILED") and "ValueError" in str(w) for w in r["warnings"])
    monkeypatch.delattr(bgr, "range_guard_table")                   # 코어 없음 = AttributeError 대신 RG_UNAVAILABLE
    r2 = _runner(tmp_path, _d)[1]("bd_loads")
    assert any(str(w).startswith("RG_FAILED") for w in r2["warnings"])


def test_columns_drive_behavior(tmp_path, core, monkeypatch):
    """모드 차이 = 계획 표 열: 같은 스냅샷이라도 열 bs_guard 가 none 이면 점검 없음·w_clamp 경로(시나리오 이름 분기 없음). 열 bs_guard 가
    basis 인 행(case_once·bmesh_once·step_once)은 같은 코드 경로를 탄다."""
    for pid in ("case_once", "bmesh_once", "step_once"):
        assert tp.PLANS[pid]["bs_guard"] == "basis" and tp.PLANS[pid]["bs_wpart"] == "graph"
    saved = dict(tp.PLANS["case_once"])
    monkeypatch.setitem(tp.PLANS, "case_once", dict(saved, bs_guard="none"))
    _m, _d, out, run, _ = _prep(tmp_path, shape_rules={"schema": 1})
    run("bd_loads")
    assert core.n("range_guard_table") == 0 and not (out / "prep" / "select" / RG_JSON).exists()


def test_range_guard_off_uses_legacy_w_clamp(tmp_path, core):
    """shape_rules.range_guard.enabled false → 점검표 없음, W 기본 범위는 v0.20.0 w_clamp 표 경로(derive 가 w_clamp 를 받음)."""
    _m, doe, out, run, _ = _prep(tmp_path, shape_rules={"schema": 1, "range_guard": {"enabled": False}})
    run("bd_loads")
    assert core.n("range_guard_table") == 0 and not (out / "prep" / "select" / RG_JSON).exists()
    auto = json.loads((out / "prep" / "select" / "auto_selection.json").read_text(encoding="utf-8"))
    doe["selection"] = {"rev": 1, "sha256": auto["sha256"], "input": auto["selection"]}
    run("bd_matrix", rev=1, spec=SPEC, selection=doe["selection"])
    assert core.n("guard_selection") == 0 and core.calls["derive"][-1][1]["range_guard"] is None


def test_invalid_block_config_invalid(tmp_path, core):
    """잘못된 스냅샷 블록 → CONFIG_INVALID(준비 첫 단계에서)."""
    mesh = esl_mesh(cf.load_fixture("h5"))
    doe = _study(tmp_path, mesh, shape_rules={"range_guard": {"jac_min": 2}})
    _out, run, _ = _runner(tmp_path, doe)
    with pytest.raises(EslError) as ei:
        run("bd_input")
        run("bd_loads")
    assert ei.value.code == "CONFIG_INVALID"


def test_outside_guard_cell_warning():
    """셀 경고 RG_OUTSIDE_GUARD: 점검된 usable 밖 값만, 이름 정렬, 경계값(1e-9 허용)은 통과."""
    usable = {"B2_D": [6.0, 8.0], "B1_D": [1.0, 2.0]}
    assert stg._outside_guard({"B1_D": 1.5, "B2_D": 8.0}, usable) is None
    w = stg._outside_guard({"B2_D": 9.0, "B1_D": 0.5, "X": 3.0}, usable)
    assert w["code"] == "RG_OUTSIDE_GUARD" and [v["name"] for v in w["vars"]] == ["B1_D", "B2_D"]
    assert w["vars"][0] == {"name": "B1_D", "value": 0.5, "usable": [1.0, 2.0]}


# ---------------------------------------------------------------- V-SH-13 (④ 경로 — 순위·직행 계획)
class FakeRoute(types.ModuleType):
    """esl.mesh.route 스텁(계약 §4 시그니처). 실제 모듈이 있으면 시험에서 그걸 씀."""

    @staticmethod
    def choose(n_faces, step_mb, rule, *, relaxed_enabled):
        mf, ms = rule.get("min_faces"), rule.get("min_step_mb")
        hit = []
        if n_faces is not None and mf is not None and n_faces >= mf:
            hit.append("faces")
        if step_mb is not None and ms is not None and step_mb >= ms:
            hit.append("step_mb")
        ok = bool(rule.get("enabled")) and relaxed_enabled and bool(hit)
        return {"path": "cad_relaxed" if ok else "cad", "reason": "+".join(hit) if ok else None, "n_faces": n_faces,
                "step_mb": step_mb, "min_faces": mf, "min_step_mb": ms}

    @staticmethod
    def rank_flag(q, rule):
        if not q:
            return None
        fr, tp_ = q.get("fail_ratio"), q.get("tria_pct")
        over = []
        if fr is not None and rule.get("fail_ratio") is not None and fr > rule["fail_ratio"]:
            over.append("fail_ratio")
        if tp_ is not None and rule.get("tria_pct") is not None and tp_ > rule["tria_pct"]:
            over.append("tria_pct")
        return {"fail_ratio": fr, "tria_pct": tp_, "over": over} if over else None


@pytest.fixture
def route(monkeypatch):
    try:
        import esl.mesh.route as real
        return real
    except ImportError:
        pass
    fake = FakeRoute("esl.mesh.route")
    monkeypatch.setitem(sys.modules, "esl.mesh.route", fake)
    import esl.mesh as pkg
    monkeypatch.setattr(pkg, "route", fake, raising=False)
    return fake


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


def test_route_core_absent_is_legacy(tmp_path, monkeypatch):
    """코어 esl.mesh.route 가 없으면(통합 전) 직행·순위 경고 없음 = 지금 경로 그대로(ImportError 로 작업이 죽지 않는다)."""
    monkeypatch.setattr(stg, "_mroute", lambda: None)
    assert _route_case(tmp_path, monkeypatch, None, shape={"schema": 1}, faces=9999, mb=0.01) is None
    c = _C({"schema": 1})
    monkeypatch.setattr(stg, "_shape", lambda cc: tp.resolve_shape({"schema": 1}))
    monkeypatch.setattr(stg, "_bs", lambda cc, col: "shapes")
    res = {"d001": {"status": "READY", "quality": {"fail_ratio": 0.9, "tria_pct": 90.0}}}
    stg._cmp_mq_flags(c, [{"id": "d001"}], res)
    assert "mq" not in res["d001"]
    monkeypatch.setattr(stg, "_bs", lambda cc, col: "base")
    assert stg._sel_mq_base(c, {"mesh": {"quality": {"fail_ratio": 0.9}}}) is None


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
