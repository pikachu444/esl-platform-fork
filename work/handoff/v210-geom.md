# v210-geom 이어받기 (impl-geom, 계약 docs/contracts/esl_bead_shape_v021.md)

- 브랜치 v210-geom (기준 ffe2559, worktree scratchpad/wt-210-geom)
- 확정: Q-SH-1 A(뒤집힘 0·새 jac<0.3 없음·새 tria 최소각<10° 없음·넓이 비≥0.2) · Q-SH-2 면≥1500 · Q-SH-3 경고만

## 상태
- [x] esl/morph/range_guard.py (SCHEMA·CRITERIA·Budget·accept·single·interacting·corners·combo·blocked·inward·doc)
- [x] esl/mesh/route.py (choose·rank_flag)
- [x] mesh_quality.guard_probe (+ guard_base, _area, _jac_angle — 추가만)
- [x] bead_graph: w_segs·_possible_vars(w_partial)·_bead_nominals·_check_ties·normalize_v2/derive_v2/derive_obj_v2(shape_rules, range_guard)
      ·GraphBead.w_seg_ids/w_cover·BG_W_PARTIAL·params_rows_v2(guard, w_segs, w_cover)·basis_v2 W segs=S_W·graph_section W 대표
      ·w_clamp_table(shape_rules)·range_guard_table·apply_range_guard·guard_selection·guard_info·guard_result·outside_guard
      ·write/load_range_guard·RANGE_GUARD_JSON/SCHEMA
- [x] bead_select.range_check(only=)
- [x] 시험 V-SH-1~10·17 (test_range_guard, tests/mesh/test_route, test_mesh_quality 추가, test_bead_graph_wpartial,
      test_bead_graph_guard, test_bead_graph_perf 추가, synth_guard)
- [x] 회귀 regress(none·cad·auto)·sel_regress·selreg = ffe2559(=72e9e8d 코드) 바이트 동일 (scratchpad/reg210)
- [x] packages/beadgraph diff 0, 패키지 시험 54 passed

## impl-backend 가 쓸 호출(stages·API)
- BD_LOADS: `doc = bgr.range_guard_table(mesh, graph, labels, fids, cfg, rules, seed=<③ seed 정규화 선택 | None>, exclude_segs=…)`
  → `bgr.write_range_guard(prep/select/RANGE_GUARD_JSON, doc, guard)`; 정보 = `bgr.guard_info(doc)`, 결과 = `bgr.guard_result(doc, sec)`.
  예외 → RG_FAILED(표 없음). range_guard 꺼짐 + w_partial → `w_clamp_table(…, shape_rules=rules)`.
- derive(API·BD_MATRIX): `derive_v2/derive_obj_v2(…, range_guard=bgr.load_range_guard(prep), shape_rules=rules)`.
- BD_MATRIX: `bgr.guard_selection(mesh, D, B, cfg)` (D 제자리 수정 → params_rows_v2 에 반영, D.warnings RG_BUDGET·RG_COMBO_SKIPPED)
  → `write_range_guard(select/<sha12>/range_guard.json)`; elems 변수만 `bs.range_check(…, only=[elems 변수])`.
- 셀: `bgr.outside_guard(rows, values)` → RG_OUTSIDE_GUARD | None.
- 경로: `route.choose(n_faces, step_mb, rules.mesh_route.relaxed_direct, relaxed_enabled=compare.mesh.cad_relaxed.enabled)`,
  `route.rank_flag(summarize 결과, rules.mesh_route.rank_quality)`.

## 계약과 다르게/보탠 점
- limited 인데 usable 이 공칭을 엄격히 품지 못하면(한쪽이 공칭에 붙음) 적용 때 blocked 로 처리(use_default false, RG_VAR_BLOCKED).
  계약 §4.4 는 "엄격히 품을 때만 적용"이라 범위가 그대로 남아 LHS 에서 RG_OUTSIDE_GUARD 가 나므로 V-SH-10 을 만족시키려고.
- single(min_keep_frac=)·combo(max_group=)·guard_probe(base=) 선택 키워드 추가(안정 시그니처 호환). ok_fn 은 4번째 값 n(위반 요소 수) 허용.
- 기저 지지가 비면 skipped short, BG_SEGMENT_SHORT 라도 기저가 있으면 점검(basis_v2·w_clamp 와 같은 꼴 — V-SH-9 일치).

## 측정
- H6 BD_LOADS 표 ≈ 13~21 s(34 항목), 270k(93 세그먼트) ≈ 146 s(≤ 180), guard_selection 20 비드 ≈ 2 s.
