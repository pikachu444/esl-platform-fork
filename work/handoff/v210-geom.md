# v210-geom 이어받기 (impl-geom, 계약 docs/contracts/esl_bead_shape_v021.md)

- 브랜치 v210-geom (기준 ffe2559, worktree scratchpad/wt-210-geom)
- 확정: Q-SH-1 A(뒤집힘 0·새 jac<0.3 없음·새 tria 최소각<10° 없음·넓이 비≥0.2) · Q-SH-2 면≥1500 · Q-SH-3 경고만

## 상태
- [x] esl/morph/range_guard.py (SCHEMA·CRITERIA·Budget·accept·single·interacting·corners·combo·blocked·inward·doc)
- [x] esl/mesh/route.py (choose·rank_flag)
- [x] mesh_quality.guard_probe (+ guard_base, _area — 추가만)
- [x] bead_graph: w_segs·_possible_vars(w_partial)·_bead_nominals·_check_ties·normalize_v2/derive_v2/derive_obj_v2(shape_rules, range_guard)
      ·GraphBead.w_seg_ids/w_cover·BG_W_PARTIAL·params_rows_v2(guard, w_segs, w_cover)·basis_v2 W segs=S_W·graph_section W 대표
      ·w_clamp_table(shape_rules)·range_guard_table·apply_range_guard·guard_selection·guard_info·guard_result·outside_guard
      ·write/load_range_guard·RANGE_GUARD_JSON/SCHEMA
- [x] bead_select.range_check(only=)
- [ ] 시험 V-SH-1~10·17
- [ ] 회귀(regress none·cad·auto, sel_regress, selreg) vs 72e9e8d

## 메모
- H6 BD_LOADS 표 ≈ 13 s(기저 ≈ 12 s 중 절반). inverted-only 기준에서 W usable = w_clamp_table 과 같음(V-SH-9 확인).
