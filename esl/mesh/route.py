"""메싱 경로 선택 · 메시 품질 순위 경고 — 모드 무관 판정(계약 esl_bead_shape_v021.md §5, SH-19·22).

새 ③(기준 STEP 1개)·④(형상 STEP 마다)가 같이 쓴다. STEP 면 수·크기(MB)·``mesh_quality.summarize`` 결과와 해석된 규칙
(스냅샷 ``doe.shape_rules.mesh_route``)을 인수로 받을 뿐, 설정 해석·파일 IO·gmsh 를 하지 않는다(D-0.20.0-CODE).

STABLE INTERFACE
  choose(n_faces, step_mb, rule, *, relaxed_enabled) -> {"path": "cad"|"cad_relaxed", "reason": ["faces"|"step_mb"…],
         "n_faces", "step_mb", "min_faces", "min_step_mb"}
      rule = mesh_route.relaxed_direct {enabled, min_faces, min_step_mb}; relaxed_enabled = compare.mesh.cad_relaxed.enabled
  rank_flag(q, rule) -> {"fail_ratio", "tria_pct", "over": ["fail"|"tria"…]} | None
      q = summarize 결과 {fail_ratio, tria_pct, …}; rule = 해석된 rank_quality {fail_ratio, tria_pct(숫자)}
"""
from __future__ import annotations

import math


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def choose(n_faces: int | None, step_mb: float | None, rule: dict, *, relaxed_enabled: bool) -> dict:
    """path = cad_relaxed ⇔ rule.enabled ∧ relaxed_enabled ∧ (n_faces ≥ min_faces ∨ (min_step_mb 숫자 ∧ step_mb ≥ min_step_mb)).
    n_faces None(BREP 등) = 면 기준 건너뜀, min_faces None = 면 기준 끔. reason = 맞은 기준 목록(faces 먼저)."""
    rule = rule or {}
    nf = None if n_faces is None else int(n_faces)
    mb = _num(step_mb)
    min_f = rule.get("min_faces")
    min_f = None if min_f is None else int(min_f)
    min_mb = _num(rule.get("min_step_mb"))
    reason = []
    if bool(rule.get("enabled")) and bool(relaxed_enabled):
        if nf is not None and min_f is not None and nf >= min_f:
            reason.append("faces")
        if min_mb is not None and mb is not None and mb >= min_mb:
            reason.append("step_mb")
    return {"path": "cad_relaxed" if reason else "cad", "reason": reason, "n_faces": nf, "step_mb": mb,
            "min_faces": min_f, "min_step_mb": min_mb}


def rank_flag(q: dict, rule: dict) -> dict | None:
    """품질 미달(q.fail_ratio > rule.fail_ratio ∨ q.tria_pct > rule.tria_pct) → {fail_ratio, tria_pct, over[fail|tria]}, 아니면 None.
    q 가 없거나 값이 없으면 None(순위 경고 없음)."""
    if not q:
        return None
    fr, tp = _num(q.get("fail_ratio")), _num(q.get("tria_pct"))
    lim_f, lim_t = _num((rule or {}).get("fail_ratio")), _num((rule or {}).get("tria_pct"))
    over = []
    if fr is not None and lim_f is not None and fr > lim_f:
        over.append("fail")
    if tp is not None and lim_t is not None and tp > lim_t:
        over.append("tria")
    if not over:
        return None
    return {"fail_ratio": fr, "tria_pct": tp, "over": over}
