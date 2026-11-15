# release v0.21.0 통합 (lead)

worktree scratchpad/wt-210, 브랜치 release/v0.21.0, 계약 docs/contracts/esl_bead_shape_v021.md
확정 Q-SH-1 A / Q-SH-2 면 ≥ 1500 / Q-SH-3 경고만

## 상태
- [x] 1 merge geom 7ee02eb · be e76a00d · fe 0ee30cd (충돌 없음 — 파일 겹침 0)
- [x] 2 접점 정합 — stages _kwcall·_mroute 제거, range_guard_table 위치 rules·seed(③ auto 파일)·fids(=derive 고정), guard_selection·range_check·derive 직접 호출, guard_info·guard_result·outside_guard 코어 사용, w_clamp_table shape_rules, auto seed normalize shape_rules; 시험 스텁 → 실제 코어
- [x] 3 register.py·opt_core.py 계약 §12 소유 절
- [x] 4 계약 §14 SH-28~32·R-SH-9·상태 확정
- [x] 5 fe DoeSettingsShapeRules(check:api 통과)
- [x] 6 시험 — 전체 통과(rel210/sum.log), vitest 단독 618 통과·기준 604 통과(fe 타임아웃 = 부하 환경)
- [ ] 7 회귀
- [~] 8 문서 — VERSION·버전 단언·openapi 0.21.0, CHANGELOG, decisions, FAQ 3건 완료, v210-* 인계 삭제(release 인계는 최종 커밋에서)
- [ ] 9 최종 커밋·push

## 진행 메모
- 전체 시험: bash scratchpad/rel210_all.sh (요약 scratchpad/rel210/sum.log, 파일별 .done 건너뜀). 단건: bash scratchpad/rel210_pt.sh <args>
- vitest·regress 는 전체 시험 뒤 단독 실행 예정
