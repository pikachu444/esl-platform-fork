"""v0.21.0 BEAD_SHAPE 시험 보조(계약 esl_bead_shape_v021.md §10): 해석된 shape_rules 블록 · 합성 포켓 단면 메시.

``rules()`` = DEFAULTS(``bead_doe.shape_rules`` — impl-backend 가 4곳 거울로 둠)를 §7 해석 꼴로: range_guard 에서 enabled 를
빼고 flip_deg = select.quality.flip_deg, rank_quality.tria_pct null → compare.quality.tria_pct.fail. DEFAULTS 에 절이 아직 없으면
(병렬 구현 중) 계약 §6 표 값을 쓴다 — 값은 같은 이름·같은 수."""
from __future__ import annotations

import copy

import numpy as np

from esl.doe import DEFAULTS

# 계약 §6 의 기본 블록(DEFAULTS 에 shape_rules 가 없을 때만 — 병렬 브랜치 통합 전)
_CONTRACT_SHAPE_RULES = {
    "enabled": True, "w_partial": True,
    "range_guard": {"enabled": True, "jac_min": 0.3, "tria_angle_min_deg": 10.0, "area_ratio_min": 0.2,
                    "max_new_fail_ratio": None, "steps": 5, "min_keep_frac": 0.25,
                    "combo": {"enabled": True, "full_max_vars": 4, "samples": 16, "max_group": 8},
                    "budget": {"prep_timeout_s": 180, "matrix_timeout_s": 60, "max_evals": 4000, "max_vars": 120}},
    "mesh_route": {"relaxed_direct": {"enabled": True, "min_faces": 1500, "min_step_mb": None},
                   "rank_quality": {"fail_ratio": 0.10, "tria_pct": None}},
}


def _merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def defaults() -> dict:
    return copy.deepcopy(DEFAULTS.get("shape_rules") or _CONTRACT_SHAPE_RULES)


def rules(over: dict | None = None, *, cfg: dict | None = None) -> dict:
    """해석된 스냅샷 블록 {schema 1, w_partial, range_guard{…, flip_deg} | None, mesh_route{…}} (+ over 깊은 합치기)."""
    base = _merge(defaults(), over or {})
    sel = (cfg or DEFAULTS).get("select") or DEFAULTS["select"]
    cq = (cfg or DEFAULTS).get("compare", {}).get("quality") or DEFAULTS["compare"]["quality"]
    rg = base.get("range_guard")
    if rg is not None and rg.get("enabled") is not False:
        rg = dict(rg)
        rg.pop("enabled", None)
        rg.setdefault("flip_deg", float(sel["quality"]["flip_deg"]))
    else:
        rg = None
    mr = copy.deepcopy(base["mesh_route"])
    if mr["rank_quality"].get("tria_pct") is None:
        mr["rank_quality"]["tria_pct"] = float(cq["tria_pct"]["fail"])
    return {"schema": 1, "w_partial": bool(base["w_partial"]), "range_guard": rg, "mesh_route": mr}


def pocket(W: float = 20.0, D: float = 7.0, flank: float = 0.0, n_floor: int = 6, n_wall: int = 3, n_side: int = 3,
           side_w: float = 10.0, ny: int = 3, Ly: float = 30.0):
    """포켓 단면(x–z) 을 y 로 밀어낸 quad 메시 + D·W 기저(바닥 폭 = W − 2D − 2·flank — 깊고 좁으면 바닥이 뒤집힘).
    반환 (x0 (n,3), conn (m,4), elem_type (m,), basis {"D": vec (n,3), "W": vec (n,3)}, nominal {"D", "W"})."""
    xs, dD, dW, zs = [], [], [], []
    # 왼쪽 판 → 왼쪽 벽 → 바닥 → 오른쪽 벽 → 오른쪽 판 (단면 점 목록)
    xl_top, xr_top = -W / 2.0, W / 2.0
    xl_bot, xr_bot = -W / 2.0 + D + flank, W / 2.0 - D - flank
    for i in range(n_side):
        t = i / n_side
        xs.append(xl_top - side_w * (1 - t))
        zs.append(0.0)
        dD.append(0.0)
        dW.append(0.0)
    for i in range(n_wall):                 # 위 모서리(t=0) → 아래 모서리 앞
        t = i / n_wall
        xs.append(xl_top + t * (xl_bot - xl_top))
        zs.append(-t * D)
        dD.append(t * 1.0)                  # 아래 모서리 = +1 (D 커지면 안쪽으로)
        dW.append(-0.5)                     # 벽 전체가 W/2 만큼 바깥으로
    for i in range(n_floor + 1):
        t = i / n_floor
        xs.append(xl_bot + t * (xr_bot - xl_bot))
        zs.append(-D)
        dD.append((1 - t) * 1.0 + t * -1.0)
        dW.append((1 - t) * -0.5 + t * 0.5)
    for i in range(1, n_wall + 1):
        t = 1 - i / n_wall
        xs.append(xr_top + t * (xr_bot - xr_top))
        zs.append(-t * D)
        dD.append(-t * 1.0)
        dW.append(0.5)
    for i in range(1, n_side + 1):
        t = i / n_side
        xs.append(xr_top + side_w * t)
        zs.append(0.0)
        dD.append(0.0)
        dW.append(0.0)
    ns = len(xs)
    floor_z = np.array(zs)
    X, BD, BW = [], [], []
    for j in range(ny + 1):
        y = Ly * j / ny
        for i in range(ns):
            X.append([xs[i], y, zs[i]])
            dz = -1.0 if floor_z[i] == -D else (-(zs[i] / -D) if D else 0.0)
            BD.append([dD[i], 0.0, dz if zs[i] != 0.0 else 0.0])
            BW.append([dW[i], 0.0, 0.0])
    C = []
    for j in range(ny):
        for i in range(ns - 1):
            a = j * ns + i
            C.append([a, a + 1, a + 1 + ns, a + ns])
    C = np.asarray(C, np.int64)
    return (np.asarray(X, float), C, np.full(C.shape[0], 4, np.int8),
            {"D": np.asarray(BD, float), "W": np.asarray(BW, float)}, {"D": float(D), "W": float(W)})
