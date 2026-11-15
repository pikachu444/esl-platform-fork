# 계약: 비드 형상 변화 개선 — 구간별 W · 품질 기반 변수 범위 제한 · 큰 모델 cad 완화 직행 (BEAD_SHAPE, v0.21.0)

- 상태: **초안(계약만 — 구현 금지 단계)**. 사용자 결정 Q-SH-1~3(§13)은 **권고안을 기본값으로** 적었다. 답이 다르면 §6 기본값만 바꾸고 구조는 그대로.
- 버전: **v0.21.0** (`release/v0.21.0`, 기준 main 72e9e8d = v0.20.0). migration **불필요**(새 값 = `bead_does.inputs`·작업 `params.doe` JSONB, 작업 폴더 파일).
- 관계(새 스냅샷에서만 이 문서 우선, 옛 스냅샷은 기존 계약 그대로):
  - `esl_beadgraph.md` BG-D-17 "W = 구성 세그먼트가 모두 W 를 가질 때만"·BG-X-3(D-0.17.0-WBOTH 의 비드 단위 부분) → §3 으로 대체. **세그먼트 단위 WBOTH(입구 선 양쪽 ≥ 3 노드일 때만 `entry_width`)는 그대로**.
  - `esl_beadgraph.md` BG-X-1·BG-X-11(W 뒤집힘 범위 줄임, `w_clamp.json`) → §4 range guard 로 일반화(D·W, 뒤집힘 + 요소 품질, 조합).
  - `esl_select_relax.md` SR-D-33·39(`range_check` 경고, D-0.16.1-RCHECK "자동 축소 안 함")는 **elems 비드 변수에 그대로**(R_auto 순환 근거 유지). 그래프 변수는 기저 램프를 원래 범위에 고정(`range_basis`, BG-D-24)하므로 축소해도 순환이 없다(BG-X-1 과 같은 근거).
  - `esl_compare_mesh_options.md` C2-D-32·33·45(cad → 시간 초과·면 실패 → cad_relaxed) 앞에 직행 경로 추가(§5). `esl_step_graph.md` SG-D-4(③ 기준 메시 = ④ 사다리)를 따라 ③ 에도 같이 적용.
  - 코드 구조 원칙 D-0.20.0-CODE(`AGENTS.md`): 두 모드 이상이 쓰는 계산 = 모드 무관 독립 모듈, 모드 차이 = `transfer_plan.PLANS` 열, 진단 스키마 1개, 값은 DEFAULTS·pydantic·yaml 2개.
- ID: 결정 `D-0.21.0-SH-n`(이하 SH-n), 시험 `V-SH-n`, 리스크 `R-SH-n`, 질문 `Q-SH-n`.
- 범위 밖: 위치(U/V) 변수(v0.22 — D-0.15-Q3 보류 유지), 강성 지표·하중 전달(v0.20.0 확정 그대로).
- 근거(서버 실측, 사용자 제공 2026-11-15): 큰 모델(실 STEP 약 2800 면, D-0.17.4-RELAXED) ③/④ 메싱 = cad **516 s 시간 초과** → cad_relaxed **272~280 s 성공**, 품질 **Fail 55.5 %·tria 21.9 %**.

## 0. 현황 (72e9e8d, 근거 파일:행)

| 항목 | 위치 | 현재 |
|---|---|---|
| 비드 W 가능 판정 | `esl/doe/bead_graph.py:462` `_possible_vars` | 비드의 **모든** 세그먼트에 `entry_width` 가 있어야 `["D","W"]`, 하나라도 없으면 `["D"]` |
| 비드 W 공칭 | `bead_graph.py:626` `_bead_nominals`, `:954`~`:983` `derive_obj_v2` | 길이 가중 평균(전 세그먼트), 하나라도 없으면 None → W 변수 없음 |
| 패키지 W 기저 | `packages/beadgraph/src/beadgraph/morph.py:220-224` | 넘긴 `segs` 중 하나라도 `entry_width` None 이면 `ValueError`("W needs entry lines on both sides for every segment") |
| 세그먼트 entry_width | `beadgraph/absorb.py:293-305` | 골격 양쪽 입구 노드 각 ≥ 3 일 때만(WBOTH, 세그먼트 단위) |
| W 범위 줄임 | `bead_graph.py:265` `w_clamp_table`(BD_LOADS `stages.py:3938`) → `:344` `_apply_w_clamp`(derive) · `:1154` `clamp_w_ranges`(BD_MATRIX `stages.py:4259-4261`) | **W 만, 뒤집힘만**, 후보 = W 세그먼트 각각 + 자동 seed W 묶음, `fixed_user`·`exclude`·toggle 있으면 미적용 |
| 범위 끝 점검 | `bead_select.py:1641` `range_check`, `:1696` → `esl/morph/core.py:221` `range_combo` | 모든 변수 끝 뒤집힘 → 경고 `SELECT_RANGE_INVERTS`·`SELECT_RANGE_COMBO` 만(범위 불변) |
| 품질 지표 | `esl/doe/mesh_quality.py:36` `element_metrics`(jacobian·내각…), `:148` `inverted_count`, `:200` `affected_quality`; `esl/morph/core.py:370` `extremes`(넓이 비) | 안 판정(`design_state`)은 뒤집힘만 FAILED_MESH, 품질은 경고(D-0.16-P2) |
| 큰 모델 메싱 | `stages.py:1422` `_cmp_mesh_shape` → `:1442` `large_model`(STEP 면 > 1000 또는 Sphere) → cad 몫 = `large.cad_share` 0.15 × 3600 = 540 s − 자식 여유 30 s = **510 s** → 실패 → `:1813` `_cmp_relaxed_parent`(isolate, ≤ 900 s) | cad 를 반드시 먼저 시도 — 큰 모델은 510 s 를 버림 |
| 메시 품질 기록 | `stages.py:1261` `_cmp_ready`(`mesh_quality.summarize`), `:2263` `SHAPE_QUALITY_FAIL`(Fail > 1 %, 준비 경고만) · `step_graph.py:801` ③ `mrec`(품질 없음, `tria_check` 만) | 순위·결과에는 품질 표시 없음 |
| 계획 표 | `esl/doe/transfer_plan.py:31` `PLANS`(5행 × 11열), `:49` `PLAN_COLS`, `:51` `PLAN_OF` | 하중 전달·강성 지표 열만 |
| 스냅샷 | `backend/esl_platform/api/services/doe.py:1262-1264` | `doe.load_transfer`·`doe.rank` 만 새 키(키 없음 = legacy) |

## 1. 범위 / 비범위

| 범위 (v0.21.0) | 비범위 |
|---|---|
| 1. 그래프 비드 W 를 **W 가능 구간(S_W)에만** — 나머지 구간은 D 만 | 위치 U/V 변수, 세그먼트 단위 WBOTH 완화(한쪽 입구 폭), 네트워크 묶기 W, elems 비드 |
| 2. 그래프 변수(D·W) 기본 범위를 **시험 모핑 + 요소 품질**로 자동 축소(준비 단계 표 + 행렬 단계 보충), 조합 꼭짓점 점검 | elems 비드(schema 1 본문) 범위 축소, 안 판정 규칙(`design_state`·graph_rules) 변경, 패키지 beadgraph 변경 |
| 3. STEP 크기 기준 **cad_relaxed 직행**(③ 새·④), 메시 품질 미달 **순위 경고** | cad_relaxed 파라미터 변경(C2-D-43 유지), 품질 미달 형상 자동 제외, ② 사용자 B 메시 품질 경고, 옛 ③(paicad) |

## 2. 공통 결정 — 스냅샷 게이트 · 계획 표 · 공용 모듈

### 2.1 스냅샷 게이트 (SH-1)
- 새 스터디 생성 시 설정 절 `bead_doe.shape_rules`(§6)를 해석해 **작업 스냅샷 `params.doe.shape_rules` 와 `bead_does.inputs.shape_rules` 에 같은 블록**으로 고정한다(§7). 워커는 `doe.shape_rules`, API(derive)는 `inputs.shape_rules` 를 읽는다.
- **키 없음 = v0.20.0 동작 그대로**(세 항목 모두): W 전부 필요, `w_clamp.json`·`clamp_w_ranges`·`range_check`, cad 먼저. `shape_rules.enabled: false` 설정이면 새 스터디도 키를 쓰지 않는다.
- 복제 = 원 스터디 블록 그대로(옛 스터디는 키를 주입하지 않음 — LT-11 과 같은 규칙). 재시도 = 스냅샷 값.
- 항목별 끔: 블록 안 `w_partial: false` / `range_guard.enabled: false` / `mesh_route.relaxed_direct.enabled: false` 면 그 항목만 v0.20.0 동작(단 `range_guard` 가 꺼지고 `w_partial` 이 켜지면 `w_clamp` 후보는 §3.1 의 S_W 규칙).

### 2.2 모드별 계획 표 (SH-2) — `transfer_plan.PLANS` 에 열 4개 추가(같은 표 한 곳)

| plan id (모드) | `bs_wpart` | `bs_guard` | `bs_route` | `bs_mq` |
|---|---|---|---|---|
| `case_once` ① same·select(case) | `graph` | `basis` | `none` | `none` |
| `bmesh_once` ② mesh·select(mesh) | `graph` | `basis` | `none` | `none` |
| `step_once` 새 ③ select(step) | `graph` | `basis` | `base` | `base` |
| `step_per_design` 옛 ③ step(paicad) | `none` | `none` | `none` | `none` |
| `compare_per_shape` ④ compare | `none` | `none` | `shapes` | `shapes` |

열 의미(값이 `none` 이면 그 모드에서 항목 없음):

| 열 | 값 | ① | ② | 새 ③ | ④ |
|---|---|---|---|---|---|
| `bs_wpart` | `graph` = 그래프 비드(`src: graph`)의 W 를 S_W 에만 | Case 메시 그래프 | B 메시 그래프 | STEP→사다리 메시 그래프 | 변수 없음 |
| `bs_guard` | `basis` = 그 모드의 기준 메시(d000) 위 그래프 기저로 시험 모핑 | Case 메시 | B 메시 | 사다리 메시(평가 영역과 무관 — 영향 요소만) | 변수 없음 |
| `bs_route` | `base` = BD_MESH0 기준 STEP 1개, `shapes` = 형상 STEP 마다 | 메싱 없음 | 사용자 메시 | 기준 STEP | 형상마다(기준 d000 포함, case·mesh 형상 제외) |
| `bs_mq` | `base` = 기준 메시 품질 → 결과 1건, `shapes` = 형상마다 → 순위 행 | – | – | 결과 경고 1건(모든 안 같은 메시) | 행 ⚠ + 결과 경고 |

- `same`·`mesh`(paicad) 시나리오는 ①·② 행을 공유하지만 그래프 비드가 없어 `bs_wpart`·`bs_guard` 경로에 도달하지 않는다(값 `graph`·`basis` 는 "그래프 비드가 있으면" 의미).
- 호출 쪽(`stages.py`·`step_graph.py`)은 **열 값만** 읽는다(시나리오 이름 분기 금지). 새 계획 행은 이 네 열도 채움(빈 칸 = `CONFIG_INVALID` — 기존 `plan_for` 검사). `PLAN_VERSION` 은 **1 그대로**(하중 전달 해시 `hash_view` 에 들어가므로 올리면 v0.20.0 새 스냅샷 해시가 바뀜) — 형상 규칙 판은 `shape_rules.schema` 가 맡는다.

### 2.3 공용 모듈과 독립성 (SH-3)

| 모듈 | 계산(모드 무관) | 쓰는 모드 | import 허용 | import 금지 |
|---|---|---|---|---|
| **신규 `esl/morph/range_guard.py`** | 단일 변수 끝 점검·이분 축소, 상호작용 묶음, 꼭짓점 생성, 조합 공통 비율 이분, 예산, 막힘 판정, 진단 문서 조립 | ①②③ | `math`, `time`(시계는 인수 주입, 기본 `time.monotonic`), `numpy` | `esl.doe.*`, `beadgraph`, `esl.mesh.*`, 파일·네트워크 IO(`open`·`os`·`json` 파일 쓰기), 설정 해석(`DEFAULTS`), 전역 난수(시드 0 `default_rng` 만) |
| **신규 `esl/mesh/route.py`** | 메싱 경로 선택(cad / cad_relaxed), 메시 품질 순위 경고 판정 | 새 ③·④ | `math` | `esl.doe.*`, `gmsh`, 파일 IO(STEP 세기 결과는 인수), 설정 해석 |
| `esl/doe/mesh_quality.py` += `guard_probe`(추가만) | 영향 요소 품질 탐침(기존 `element_metrics`·`inverted_count`·`_elem_normals` 재사용) | ①②③ | 지금 그대로(numpy) | 새 import 없음 |
| `esl/doe/bead_graph.py`(기존, 모드를 모름) | S_W 규칙, 후보 기저, 표 적용 | ①②③ | 지금 그대로 | 시나리오·`select_base` 이름 읽기 금지(필요한 값은 인수) |

```python
# esl/morph/range_guard.py — 안정 시그니처(impl-geom 작성, impl-backend 는 bead_graph 경유로만 사용)
SCHEMA = "esl/range_guard/1"
CRITERIA = ("inverted", "jac", "tri_angle", "area_ratio", "new_fail")      # accept 의 판정·보고 순서
class Budget:                      # Budget(max_evals, timeout_s, clock=time.monotonic); take() -> bool(남았으면 1 차감); stopped -> None|"evals"|"time"|"vars"
def accept(probe: dict, crit: dict) -> tuple[bool, str | None, float | None]   # (통과, 첫 위반 기준, 그 값)
def single(name, nominal, lo, hi, ok_fn, *, steps, budget) -> dict             # §4.2 — ok_fn(v) -> (bool, reason, value)
def interacting(supports: dict[str, np.ndarray]) -> list[list[str]]          # 변수 → 영향 요소 index, 공유 요소 union-find, 크기 ≥ 2 묶음만, 이름 정렬
def corners(n: int, *, full_max: int, samples: int) -> np.ndarray             # int8 (m, n): n ≤ full_max → 2^n 전부, 아니면 default_rng(0) samples 개
def combo(group: list[tuple[str, float, float, float]], ok_multi, *, full_max, samples, steps, budget) -> dict | None
def blocked(nominal, frm, usable, min_keep_frac) -> tuple[bool, bool]          # (lo 쪽 막힘, hi 쪽 막힘)
def inward(v, nominal) -> float                                               # 1e-4 공칭 쪽 반올림(bead_graph._inward 와 같은 식 — 이곳이 원본)
def doc(scope, entries, combos, skipped, budget, crit, meta) -> dict          # §4.6 스키마(결정적 키 순서)

# esl/mesh/route.py
def choose(n_faces: int | None, step_mb: float | None, rule: dict, *, relaxed_enabled: bool) -> dict
    # -> {"path": "cad"|"cad_relaxed", "reason": ["faces"|"step_mb"], "n_faces", "step_mb", "min_faces", "min_step_mb"}
def rank_flag(q: dict, rule: dict) -> dict | None
    # q = mesh_quality.summarize 결과, rule = 해석된 rank_quality{fail_ratio, tria_pct(숫자)} -> {"fail_ratio", "tria_pct", "over": [...]} | None

# esl/doe/mesh_quality.py (추가만)
def guard_probe(x0, x, conn, elem_type, idx, *, flip_deg, jac_min, tria_angle_min_deg, qcfg=None) -> dict
    # -> {n_affected, inverted, jac_min, jac_bad_new, tri_angle_min, tri_bad_new, area_ratio_min, new_fail_ratio|None}
```

## 3. 항목 1 — W 구간별 허용 (SH-4 ~ SH-9)

### 3.1 규칙
| ID | 결정 | 근거 |
|---|---|---|
| SH-4 | **S_W = 비드 세그먼트 중 `entry_width` 가 있는 것**(정렬, `bead_graph.w_segs(graph, seg_ids)`). 새 스냅샷(`w_partial` ∧ 계획 `bs_wpart = graph`)에서 `_possible_vars = ["D","W"]` ⇔ \|S_W\| ≥ 1(네트워크 묶기 `{network}` 는 BG-D-18 대로 D 만). `area`·`plateau` 는 구성상 `entry_width` 가 null 이라 자동으로 S_W 밖 | 사용자 요구 "폭 정보가 있는 구간만 W" |
| SH-5 | **W 변수 1개 = S_W 에만 적용**: 이름 그대로 `B<n>_W`(타이 = 대표 id). 공칭 `W_nom` = S_W 길이 가중 평균 entry_width. D 변수 `B<n>_D` 는 지금처럼 S 전체 | 이름 체계·행렬·결과 열 불변 |
| SH-6 | **기저 = 패키지 그대로, esl 이 넘기는 segs 만 S_W**: `basis_v2` 의 W 항목 `{"name": B<n>_W, "kind": "W", "segs": S_W, "zones": [], "hold"}`. 구역은 `bead_zones(S_W)` 가 정함 → S_W 와 S \ S_W 사이 접합 구역 = 바깥 = 램프 원점 J(BG-D-24 — W 는 그 접합에서 0 으로 줄어듦), S \ S_W 벽·바닥 = "다른 요소"(블렌딩 띠 자름, `SELECT_BLEND_CLIPPED`). 바깥 0 점검(BG-X-9 `allowed_elements(S_W, W)`)·달성 W(BG-D-33)·`chk_o*` 도 같은 S_W | 패키지 무변경(§9.3) — `ValueError` 는 S_W 에서 생길 수 없음 |
| SH-7 | **범위·feasible**: W 기본 = `W_nom(S_W)·(1 ± width_rel)`, W feasible 하한 = 2·D_nom + W_floor_min(BG-D-22 식, D_nom = 비드 전체), D feasible 상한의 `(W_entry − W_floor_min)/2` 항 = `W_nom(S_W)` 로(S \ S_W 구간은 폭 제약 없음). 램프·코너 가드 고정 범위 = 이 기본 범위(`range_basis`) | BG-D-22 식 그대로, 입력만 S_W |
| SH-8 | **타이(BG-D-21)**: 조건 "같은 W 유무" 와 \|W_nom 차\| ≤ 2·`sym_tol_mm` 는 S_W 공칭으로. S_W 구성 수가 달라도 허용(정보 `BG_W_PARTIAL` 각자) | 거울 비드는 보통 같은 S_W |
| SH-9 | **편집**: `merge` 로 W·비W 세그먼트를 합치면 합친 세그먼트는 `entry_width` null(패키지 `edits.py:234` 그대로) → 그 구간은 D 만. `split` 은 각 조각이 분류 규칙대로 | 패키지 무변경 |

### 3.2 변수 행 · 요약 · 스냅샷 (새 스냅샷만 — 키가 없으면 출력에 없음)
- `SelectionDerived.beads[]`(그래프 비드) += `w_segs: [앵커…]`·`w_cover: 0..1`(S_W 길이 / S 길이, 4자리) — **부분일 때만**(\|S_W\| < \|S\|). 정보 `BG_W_PARTIAL{bead, n_w, n_seg, cover, no_w: [앵커…]}`.
- 변수 행(`params_rows_v2`·`DoeParamsOut.params[]`) W 행 += `w_segs`·`w_cover`(부분일 때만).
- 정규화 선택(BG-D-36): `vars` 는 지금처럼 "가능한 것 전부와 다를 때만" 기록. 가능 집합이 스냅샷에 따라 다르므로 **선택 sha 는 스터디 안에서만 의미**(스냅샷은 스터디마다 고정 — 충돌 없음). 전부 W 인 비드·D 만 비드는 옛 규칙과 정규화 바이트 같음.
- `basis.json` += `shape_rules: 1`(새 스냅샷만). `GRAPH_ALGO`·`GRAPH_RULES`·`MORPH_RULES` 그대로.

### 3.3 화면 (2560×1440 기준, 1920×1080 잘림·가로 스크롤 없음, 새 화면 없음)
- 비드 목록(`BeadList`·`SegmentTree`): 비드 변수 칩 `D · W(부분 2/3)` — 툴팁 "폭 정보 없는 구간(입구 선 한쪽): #a12 · #a40 — 그 구간은 깊이만 바뀝니다". 세그먼트 줄은 W 없는 구간을 `W —`(툴팁 같은 문구).
- 변수 표(`DoeParamTable`): `B3_W` 이름 옆 작은 꼬리표 "부분" + 툴팁(구간 앵커·길이 비율 %).
- 단면 그림(BG-D-46): W 미분 `ds_dW` 는 S_W 의 대표 세그먼트(길이 최대)에서. 3D·평면도 층 변경 없음.

## 4. 항목 2 — 품질 기반 변수 범위 제한, range guard (SH-10 ~ SH-18)

### 4.1 판정 기준 (SH-10) — 안 1개(변수 값 묶음)의 "통과"
영향 요소 = 노드 변위 > `U_EPS`(1e-9 mm)인 노드를 가진 요소(`affected_elems` 와 같은 규칙). `guard_probe` 값으로 `range_guard.accept` 가 아래 순서로 첫 위반을 고른다.

| 기준 | 위반 조건 | 재사용 |
|---|---|---|
| `inverted` | 뒤집힘 수 > 0 (quad 야코비안 ≤ 0 ∨ 법선 회전 > `flip_deg` = `select.quality.flip_deg` 60) | `mesh_quality.inverted_count` — `design_state` 와 비트 같은 판정 |
| `jac` | quad 중 **공칭 ≥ `jac_min` 인데 안에서 < `jac_min`** 인 요소 ≥ 1 | `element_metrics.jacobian`(2×2 가우스 점 최소/최대) |
| `tri_angle` | tria 중 **공칭 최소 내각 ≥ `tria_angle_min_deg` 인데 안에서 <** 인 요소 ≥ 1 | `element_metrics.min_angle` |
| `area_ratio` | 영향 요소 넓이 비(안/공칭) 최소 < `area_ratio_min` | `core.extremes` 와 같은 넓이 식 |
| `new_fail` | (`max_new_fail_ratio` 가 숫자일 때만) 새 Fail 비율 > 그 값 | `affected_quality` 와 같은 Fail 규칙(`compare.quality`) |

- **"새로 나빠진 요소"만 센다**(공칭에서 이미 기준 밖인 요소는 무시) — 거친 기준 메시(사다리 tria)에서 범위가 0 으로 무너지지 않게. 공칭 자체는 늘 통과.
- 판정 규칙 D-0.16-P2(안 판정 = 뒤집힘만 제외, 품질은 경고)는 **그대로** — guard 는 **기본 범위만** 줄이고 안을 제외하지 않는다(§4.4).

### 4.2 축소 알고리즘 (SH-11·12)
**단일 변수**(`range_guard.single`): 변수마다 원래 기본 범위 `from = [lo, hi]`, 공칭 v₀.
```
for side, end in ((lo 쪽, lo), (hi 쪽, hi)):
    if not budget.take(): stopped → 이 변수 전체를 skipped(reason budget) — 반쯤 줄인 값은 쓰지 않음
    ok = ok_fn(end)                               # 시험 모핑 x = x0 + (end − v₀)·B_v → guard_probe → accept
    if ok: usable_side = end
    else:  a, b = v₀, end                          # a = 통과(공칭), b = 위반
           repeat steps: m = (a+b)/2; ok_fn(m) ? a = m : b = m    (매 회 budget.take)
           usable_side = inward(a, v₀)             # 1e-4 공칭 쪽 반올림 — 반올림된 끝이 위반 쪽에 떨어지지 않음
state = ok | limited | blocked(blocked: 양쪽 다 keep < min_keep_frac, keep = |usable−v₀| / |from−v₀|)
```
- 해상도 = \|끝 − v₀\| / 2^`steps`(기본 5 → 3.1 %). 시험 수 ≤ 2·(1 + steps) = 12/변수.
- 단조 가정: 품질은 \|Δ\| 에 단조로 나빠진다고 보고 경계 1개를 찾는다(어긋남 = R-SH-2, 안 판정이 받침).

**조합**(`range_guard.combo`, "필요 시"): 단일 축소 뒤 **상호작용 묶음**만 — 영향 요소를 공유하는 변수들(`interacting`, union-find). 같은 비드의 D·W 는 항상 한 묶음(깊고 좁은 모서리 = 바닥 폭 W − 2D 소멸이 대표 위험). 묶음 크기 ≤ `combo.max_group`(8) 만, 넘으면 `RG_COMBO_SKIPPED{vars, n}`.
```
꼭짓점 = corners(k, full_max = combo.full_max_vars(4), samples = combo.samples(16))  # k ≤ 4 → 2^k 전부, 아니면 시드 0 표본 16
값(s) = {v_i: v₀_i + s·(usable_i(꼭짓점 비트) − v₀_i)}
s = 1 에서 모든 꼭짓점 통과 → None
아니면 s ∈ [0, 1] 이분 steps 회(첫 위반에서 조기 종료) → scale = a → 묶음 변수 기본 범위 = v₀ + scale·(usable − v₀)(inward)
```
- `esl.morph.core.range_combo`(SR-D-39)와 같은 꼭짓점·이분 규칙을 일반 판정 함수로 — 새 모듈이 원본, 옛 함수는 그대로 둠(legacy 바이트).

### 4.3 실행 위치 · 흐름 (SH-13·14)
"준비 단계에서 미리" 가 원칙이다 — API 가 행렬을 만들 때(`DoeParamsOut.default_range`) 이미 줄어 있어야 위험 안이 표본에 들어가지 않는다(BG-X-11 과 같은 이유: 행렬은 API 가 만들고 워커는 sha 만 맞춤).

| 단계 | 하는 일 | 산출물 |
|---|---|---|
| **BD_LOADS**(준비, `bs_guard = basis`, 그래프 성공 시) | 후보 변수 기저(`basis_v2` 경로, 램프 = 원래 기본 범위) → 단일 점검 → 조합 점검. 후보 순서(결정적) = ① 자동 seed 선택의 변수(③ 은 `_sel_auto_step` seed, ①② auto 는 그래프 seed, manual 도 seed 를 계산해 후보로) → ② 그 밖의 단일 세그먼트 D·W((tier, 앵커) 순). 조합 = seed 선택의 상호작용 묶음 | `prep/select/range_guard.json`(scope `prep`) — 새 스냅샷은 `w_clamp.json` 을 쓰지 않음 |
| **derive**(API·BD_MATRIX 같은 코드 `derive_obj_v2(range_guard=, shape_rules=)`) | 표 항목이 맞는 변수에 §4.4 적용. 맞지 않으면 `guard.state = "unchecked"` + 정보 `RG_UNCHECKED{var}` | 변수 행 `guard{…}` |
| **BD_MATRIX**(`_sel_prepare`) | unchecked 변수만 같은 함수로 점검(`guard_selection(only=…)`) + 선택 전체 조합 점검 → `params.json` 기본 범위 반영(BG-X-1 과 같은 경로 — 다음 행렬부터 보임). 이번 행렬은 sha 고정이라 바꾸지 않음. 그래프 변수는 `range_check`·`clamp_w_ranges` 를 부르지 않고, elems 변수만 `range_check(only=elems 변수)`(SR-D-33 경고 그대로) | `select/<sha12>/range_guard.json`(scope `selection`) |
| **BD_SELECT_GRID**(미리보기 셀) | 안 값이 그 변수의 `guard.usable` 밖이면 셀 경고 `RG_OUTSIDE_GUARD{vars:[{name, value, usable}]}`(**경고만** — 상태·판정 규칙 불변) | 셀 `warnings` |

**표 일치 규칙**(derive): 표 머리 `graph_sha256`·`cfg_sha256`(select 설정 키 + shape_rules 해시)·`fixed_sha256`(후보 계산에 쓴 고정 노드 집합 sha)·`exclude_sha256` 이 현재 선택과 같고, toggle 편집이 없고, 항목 `key{kind, segs[[앵커, 요소 수]…], w_segs, hold}` 와 `from` 이 그 변수와 같을 때만 적용. merge·split 은 키가 달라진 변수만 불일치. (BG-X-11 의 "fixed_user·exclude 없을 때만" 을 "같은 집합일 때" 로 넓힘 — ③ seed 는 fixed_user 를 가짐.)

### 4.4 적용 규칙 (SH-15·16)
- `state limited` → `default_range` = usable(공칭을 엄격히 품을 때만), `feasible` 의 **위반 쪽** = min/max(feasible, usable)(BG-X-11 과 같음 — 사용자가 넓히면 기존 `RANGE_OUTSIDE_FEASIBLE` 경고, 막지 않음). 정보 `RG_RANGE_LIMITED{bead, var, from, to, side, reason, value}`.
- `state blocked`(양쪽 keep < `min_keep_frac`) → `default_range` = usable, `use_default: false`, 경고 `RG_VAR_BLOCKED{bead, var, usable, reason}`.
- 조합 scale < 1 → 묶음 변수 `default_range` 만 scale 적용(feasible 불변), 정보 `RG_COMBO_LIMITED{vars, corners, bad_n, scale, reason}`. 묶음 구성원이 **모두** 표에 맞을 때만(아니면 BD_MATRIX 가 다시).
- 타이 대표 변수 = 구성원 공통 Δ(BG-X-11 규칙), 시험 모핑은 `basis_v2` 의 대표 기저 그대로(구성원 합).
- 기저·램프 L(`range_basis`)·`BG_RAMP_SHORT`·`use_default` 의 `BG_SEGMENT_SHORT` 규칙 불변.
- 변수 행 `guard = {state: ok|limited|blocked|unchecked, from:[lo,hi], usable:[lo,hi]|null, reason|null, value|null, combo_scale|null}`(새 스냅샷의 그래프 변수만).

### 4.5 비용 상한 (SH-17)
| 상한 | 기본 | 넘으면 |
|---|---|---|
| `budget.prep_timeout_s` | 180 s(기저 계산 포함, BD_LOADS guard 전체) | 남은 후보 `skipped{reason: budget}` + 정보 `RG_BUDGET{done, total, evals, stopped}` — 준비는 READY, 그 변수는 BD_MATRIX 가 점검 |
| `budget.matrix_timeout_s` | 60 s(BD_MATRIX unchecked + 조합) | 남은 변수 unchecked 유지 + `RG_BUDGET` |
| `budget.max_evals` | 4000 시험 모핑(단계마다) | 위와 같음(stopped `evals`) |
| `budget.max_vars` | 120 후보 변수(BD_LOADS) | seed 변수 먼저 → 단일 세그먼트는 남는 만큼(stopped `vars`) |
- 시험 1회 = `morph`(기저 지지 노드만 더함) + 영향 요소 품질(수천 요소) — ms 단위. 비용 대부분은 후보 기저(H6 104k 요소 `bg.basis` 3.9 s 실측, BG-D-46). guard 실패(예외) = 경고 `RG_FAILED{code}` + 표 없음(derive 는 전부 unchecked) — 준비·행렬은 계속.
- 시간으로 멈춘 표는 결정적이지 않음(`budget.stopped: "time"` 기록). 멈추지 않은 표는 같은 입력에서 바이트 같음(시간 값은 파일에 넣지 않고 작업 결과·로그에만).

### 4.6 진단 스키마 `esl/range_guard/1` (SH-18 — 준비 표·선택 문서 공통 1개)
```json
{
  "schema": "esl/range_guard/1", "scope": "prep|selection",
  "graph_sha256": "…", "cfg_sha256": "…", "fixed_sha256": "…", "exclude_sha256": "…", "selection_sha256": null,
  "crit": {"flip_deg": 60.0, "jac_min": 0.3, "tria_angle_min_deg": 10.0, "area_ratio_min": 0.2, "max_new_fail_ratio": null},
  "steps": 5, "min_keep_frac": 0.25,
  "budget": {"max_evals": 4000, "timeout_s": 180, "max_vars": 120, "evals": 812, "stopped": null},
  "entries": [{
    "key": {"kind": "D|W", "segs": [[1043, 812]], "w_segs": [[1043, 812]], "hold": 1},
    "var": "B3_W", "src": "seed|segment|selection", "nominal": 37.28, "from": [29.824, 44.736],
    "usable": [29.824, 41.3125], "state": "limited",
    "ends": [{"side": "lo", "end": 29.824, "ok": true, "reason": null, "value": null, "evals": 1},
             {"side": "hi", "end": 44.736, "ok": false, "reason": "jac", "value": 0.214, "n": 3, "evals": 6}]}],
  "combos": [{"members": [{"kind": "D", "segs": [[1043, 812]]}, {"kind": "W", "segs": [[1043, 812]]}],
              "vars": ["B3_D", "B3_W"], "corners": 4, "bad_n": 1, "scale": 0.6875, "reason": "inverted",
              "usable": {"B3_D": [7.1, 11.4], "B3_W": [32.1, 40.0]}}],
  "skipped": [{"key": {"kind": "D", "segs": [[2210, 95]], "hold": 1}, "reason": "budget|basis_error|short", "detail": null}]
}
```
- 키 정렬·compact·ASCII(`graph_bytes` 와 같은 직렬화). `var` = scope selection 에서만 값(prep 은 null 가능). 작업 결과 `range_guard{entries, limited, blocked, combos, evals, seconds, stopped}`·`prep/input.json.range_guard`(새 스냅샷만).

## 5. 항목 3 — 큰 모델 cad 완화 직행 · 메시 품질 순위 경고 (SH-19 ~ SH-24)

### 5.1 경로 선택 (SH-19)
- 이미 아는 크기 지표: **STEP 면 수**(`mesh_gmsh.step_scan` — `large_model` 이 지금도 셈, 결정적·gmsh 없음)와 STEP 파일 크기(MB). 요소 수는 메싱 전에 알 수 없음(면 넓이도 OCC 가져오기 뒤) — 그래서 면 수가 1차 기준.
- `route.choose`: `path = cad_relaxed` ⇔ `relaxed_direct.enabled` ∧ `compare.mesh.cad_relaxed.enabled` ∧ (`n_faces ≥ min_faces`(기본 **1500**, Q-SH-2) ∨ (`min_step_mb` 숫자 ∧ `step_mb ≥ min_step_mb`)). n_faces None(BREP 등) = 면 기준 건너뜀. 주기 면(Sphere) 단독은 기준 아님(작은 모델은 cad 가 빨리 끝나거나 면 폴백으로 해결 — 지금 경로가 낭비 없음).
- 적용: 계획 `bs_route ∈ {base, shapes}` 이고 메시 모드 auto·cad 인 STEP 행만(mesh 형상·case 기준·mode freeform·remesh 는 지금 그대로).

### 5.2 실행 (SH-20)
- 직행 = cad 세션을 **띄우지 않고** `_cmp_relaxed_parent` 와 같은 부모 하위 프로세스 1회(isolate, 같은 `cad_relaxed` 설정·채택 조건: 품질 오류 없음 ∧ 충실도 ≤ `remesh.fidelity.fail_mm`). 제한 시간 = min(`cad_relaxed.timeout_s` 900, `stage_cap`(누적 0 기준)).
- 성공 → 행 `mesh_method: cad`, `mesh_path: cad_relaxed`, `cad_relaxed{…, direct: true}`, `route{path, reason, n_faces, min_faces}`, `attempts = [{stage: cad, status: SKIPPED, reason: relaxed_direct}, {stage: cad_relaxed, status: READY, seconds}]` → `stage_times`.
- 실패: mode auto → 사다리를 **cad·refine_local·refine_global 을 뺀 나머지**(기본 freeform → defeature → tria)로 계속(세분화는 cad 실패 면 기록이 필요 — 직행에는 없음, 건너뜀 사유 `relaxed_direct`), 시간 예산 `refine.total_timeout_s` 는 직행 시도부터 누적. mode cad → 실패 행(지금 `_cmp_relaxed_only` 실패와 같은 꼴).
- 기대 효과(서버 실측 기준): 큰 모델 1개 첫 메시까지 ≈ 516 + 280 = 796 s → ≈ 280 s(cad 몫 510 s 절감). 메시는 지금 cad_relaxed 성공본과 같은 설정 → 같은 메시(V-SH-14 비트 비교).

### 5.3 기록 (SH-21)
- ④ `prep/compare.json` 형상 행 += `route`(새 스냅샷만), 준비 정보 `MESH_ROUTE_RELAXED{id, name, n_faces, min_faces}`(경고 아님). 기존 `_cmp_path_warn` 경로 문구에 "직행" 표기.
- 새 ③ `prep/input.json.mesh` += `route`·`quality{fail_ratio, tria_pct, fail_elems, n_elems}`(새 스냅샷만), `base.json` 불변.

### 5.4 메시 품질 순위 경고 (SH-22·23·24)
- 판정 `route.rank_flag(q, rule)`: `q.fail_ratio > rank_quality.fail_ratio`(기본 **0.10**) ∨ `q.tria_pct > rank_quality.tria_pct`(null → 해석 때 `compare.quality.tria_pct.fail` 15 로 고정) → `{fail_ratio, tria_pct, over: ["fail"|"tria"]}`. q = `_cmp_ready` 의 `mesh_quality.summarize`(지금 계산되는 값 — 새 계산 없음).
- ④(`bs_mq = shapes`): 순위 행 += `mq{fail_ratio, tria_pct}`(걸린 형상만) + 행 `warn` 에 `MESH_QUALITY_RANK`(D-0.16.1-Q1 과 같은 ⚠ — **순위는 그대로**), 결과 `warnings += MESH_QUALITY_RANK{scope: "shapes", n, shapes:[{id, name, fail_ratio, tria_pct}]}`, `summary.best_clean_mq` = 품질 경고 없는 최상위 형상 id(최상위가 깨끗하면 그 id, 없으면 null). `ranking.csv` 끝 열 `mq_fail_ratio, mq_tria_pct`(새 스냅샷만).
- 새 ③(`bs_mq = base`): 준비 경고 1건 + 결과 `warnings += MESH_QUALITY_RANK{scope: "base", fail_ratio, tria_pct}` 1건(모든 안이 같은 메시 — 행 표시 없음), `summary.mesh_quality{fail_ratio, tria_pct, warn}`.
- 보고서(`report_doe.py`) 한계 절에 1줄: "메시 품질 미달(Fail x % · tria y %) — 순위 신뢰도 낮음, 품질 통과 최상위 = …". 기존 `SHAPE_QUALITY_FAIL`(Fail > 1 %, 준비 경고)은 그대로.

## 6. 설정 키 — `bead_doe.shape_rules` (DEFAULTS `esl/doe/__init__.py` = pydantic `BeadDoeShapeRulesCfg` = `config/esl_platform.example.yaml`·`config/esl_platform.prod.example.yaml`, 하드코딩 금지)

최상위 새 절 한 곳(기존 해시 대상 절 — `select`·`compare.quality`·`compare.mesh` 프로필 키 — 을 건드리지 않음 → 옛 해시 불변, §9.2). 새 스터디 생성 때 이 절을 해석해 스냅샷으로 고정(§7).

```yaml
bead_doe:
  shape_rules:                     # v0.21.0 BEAD_SHAPE — 새 스터디 스냅샷 doe.shape_rules 원본(옛 스터디 = 키 없음 = v0.20.0 동작)
    enabled: true                  # false = 새 스터디도 스냅샷을 쓰지 않음
    w_partial: true                # 항목 1 — 그래프 비드 W 를 폭 정보 있는 구간(S_W)에만
    range_guard:                   # 항목 2
      enabled: true
      jac_min: 0.3                 # quad 새 나쁜 야코비안 기준(공칭 ≥ 이 값 → 안 < 이 값 = 위반)
      tria_angle_min_deg: 10.0     # tria 새 나쁜 최소 내각
      area_ratio_min: 0.2          # 영향 요소 넓이 비 최소
      max_new_fail_ratio: null     # compare.quality 기준 새 Fail 비율 상한(null = 안 봄)
      steps: 5                     # 끝마다 이분 횟수
      min_keep_frac: 0.25          # 한쪽 남은 폭 비 < 이 값 = 그쪽 막힘(양쪽 → RG_VAR_BLOCKED)
      combo: {enabled: true, full_max_vars: 4, samples: 16, max_group: 8}
      budget: {prep_timeout_s: 180, matrix_timeout_s: 60, max_evals: 4000, max_vars: 120}
    mesh_route:                    # 항목 3
      relaxed_direct: {enabled: true, min_faces: 1500, min_step_mb: null}
      rank_quality: {fail_ratio: 0.10, tria_pct: null}   # tria_pct null = compare.quality.tria_pct.fail
```

| 키 | 기본 | 의미 | pydantic 검사 |
|---|---|---|---|
| `enabled` | true | 새 스터디 스냅샷 생성 여부 | bool |
| `w_partial` | true | §3 S_W 규칙 | bool |
| `range_guard.enabled` | true | §4 guard(끄면 새 스냅샷에서도 w_clamp 경로) | bool |
| `range_guard.jac_min` | 0.3 | quad 새 나쁜 야코비안 | (0, 1) |
| `range_guard.tria_angle_min_deg` | 10.0 | tria 새 나쁜 최소 내각 | (0, 60) |
| `range_guard.area_ratio_min` | 0.2 | 넓이 비 최소 | (0, 1) |
| `range_guard.max_new_fail_ratio` | null | 새 Fail 비율 상한 | null \| (0, 1] |
| `range_guard.steps` | 5 | 이분 횟수 | 1..20 |
| `range_guard.min_keep_frac` | 0.25 | 막힘 판정 | [0, 1) |
| `range_guard.combo.enabled` | true | 조합 점검 | bool |
| `range_guard.combo.full_max_vars` | 4 | 이하면 2^k 전부 | 1..8 |
| `range_guard.combo.samples` | 16 | 넘으면 시드 0 표본 수 | 1..256 |
| `range_guard.combo.max_group` | 8 | 묶음 상한(넘으면 건너뜀) | 2..32 |
| `range_guard.budget.prep_timeout_s` | 180 | BD_LOADS guard 시간 | (0, 3600] |
| `range_guard.budget.matrix_timeout_s` | 60 | BD_MATRIX 보충 시간 | (0, 3600] |
| `range_guard.budget.max_evals` | 4000 | 단계별 시험 모핑 수 | 1..1e6 |
| `range_guard.budget.max_vars` | 120 | 준비 후보 변수 수 | 1..2000 |
| `mesh_route.relaxed_direct.enabled` | true | §5 직행 | bool |
| `mesh_route.relaxed_direct.min_faces` | 1500 | STEP 면 기준 | null \| ≥ 1 |
| `mesh_route.relaxed_direct.min_step_mb` | null | STEP 크기 기준 | null \| > 0 |
| `mesh_route.rank_quality.fail_ratio` | 0.10 | 순위 경고 Fail 비율 | (0, 1] |
| `mesh_route.rank_quality.tria_pct` | null | 순위 경고 tria % | null \| (0, 100] |

- 뒤집힘 각은 새 키를 만들지 않고 `select.quality.flip_deg`(60)를 해석 때 `range_guard.flip_deg` 로 복사(같은 값 한 곳).
- `GET /doe/settings` += `shape_rules{enabled, w_partial, range_guard{enabled}, mesh_route{relaxed_direct{enabled, min_faces}}}`(표시용).

## 7. API · 스냅샷 키

| 위치 | 키 | 새 스냅샷 | 옛 스냅샷 |
|---|---|---|---|
| 작업 `params.doe.shape_rules` · `bead_does.inputs.shape_rules`(같은 블록) | `{schema: 1, w_partial, range_guard{…, flip_deg} \| null(꺼짐), mesh_route{relaxed_direct{…}, rank_quality{fail_ratio, tria_pct(숫자)}}}` | 생성 때 해석·고정, 복제 = 그대로 | 키 없음 |
| `DoeStudyOut.inputs.shape_rules` | 위 블록 | 있음 | null |
| select derive 응답(`SelectionDerived`) 그래프 비드 | `w_segs`, `w_cover`(부분일 때) | 있음 | 없음 |
| 변수 행(`DoeParamsOut.params[]`) | `guard{state, from, usable, reason, value, combo_scale}`, W 행 `w_segs`·`w_cover` | 있음 | 없음 |
| 미리보기 셀 `warnings` | `RG_OUTSIDE_GUARD` | 있음 | 없음 |
| ④ 준비 형상 행(`compare.json`·API) | `route{path, reason, n_faces, min_faces}` | 있음 | 없음 |
| ③ 준비 `inputs`/prep `mesh` | `route`, `quality{fail_ratio, tria_pct, fail_elems, n_elems}` | 있음 | 없음 |
| 결과(`post/result.json`·API) | 순위 행 `mq`, `summary.best_clean_mq`(④), `summary.mesh_quality`(③), `warnings` `MESH_QUALITY_RANK` | 있음 | 없음 |
| `GET /doe/settings` | `shape_rules{…}`(§6) | – | – |

- 백엔드 → 코어 전달: `normalize_v2(…, shape_rules=)`, `derive_v2(…, w_clamp=, range_guard=, shape_rules=)`(`_graph_call` 이 시그니처에 있는 키만 넘김 — 옛 코어와도 호환). `load_graph` 가 `prep/select/range_guard.json`(schema 확인)을 함께 읽고 캐시 키·derive 캐시 키에 그 sha 를 넣는다.
- 워커 → 코어: `c.D.get("shape_rules")` → `transfer_plan.resolve_shape(snap)`(None = legacy) — 해석·검사 한 곳(잘못된 블록 = `CONFIG_INVALID`).
- `docs/contracts/openapi_p1b.json` 갱신(위 필드).

## 8. 경고 · 진단 코드 (문구 원본 `resources/doe_messages.json`, 화면 `frontend/src/api/doe.ts` 문구 맵)

| 코드 | 수준 | 필드 | 뜻 |
|---|---|---|---|
| `BG_W_PARTIAL` | info | bead, n_w, n_seg, cover, no_w | 비드 W 가 일부 구간에만(그 밖은 D 만) |
| `RG_RANGE_LIMITED` | info | bead, var, from, to, side, reason, value | 품질 점검으로 기본 범위 축소 |
| `RG_VAR_BLOCKED` | warning | bead, var, usable, reason | 양쪽 다 거의 못 움직임 — 기본 체크 해제 |
| `RG_COMBO_LIMITED` | info | vars, corners, bad_n, scale, reason | 함께 바꿀 때 위험 → 공통 비율로 축소 |
| `RG_COMBO_SKIPPED` | info | vars, n | 묶음이 커 조합 점검 생략 |
| `RG_UNCHECKED` | info | var | 준비 표에 없음 — 미리보기 준비(BD_MATRIX)에서 점검 |
| `RG_BUDGET` | info | done, total, evals, stopped | 비용 상한으로 일부만 점검 |
| `RG_FAILED` | warning | code | guard 계산 실패(범위 축소 없음, 진행) |
| `RG_OUTSIDE_GUARD` | warning(셀) | vars[{name, value, usable}] | 이 안은 점검된 안전 범위 밖 값 |
| `MESH_ROUTE_RELAXED` | info | id, name, n_faces, min_faces | 큰 모델이라 cad 없이 완화 메싱으로 시작 |
| `MESH_QUALITY_RANK` | warning | scope, n?, shapes?, fail_ratio?, tria_pct? | 메시 품질 미달 — 순위 신뢰도 낮음(순위는 유지) |

- 진단 스키마는 §4.6 하나(`esl/range_guard/1`). 메시 경로·품질은 기존 형상 행·준비 문서에 키 추가(새 파일 없음).

## 9. 레거시 호환 · 해시 · beadgraph 판

### 9.1 레거시 규칙 (SH-25)
- **`shape_rules` 키 없는 스냅샷 = v0.20.0 동작·바이트 그대로**: ①②③ `sel_regress`·`selreg`, ④ `scripts/regress.py`(작업 폴더, V-C2-30 방식) 준비·`loads.npz`·`compare.json`·`params.json`·`derived.json`·`basis.json`·`w_clamp.json`·`result.json`·`ranking.csv`·보고서·view3d **바이트 동일**.
- 새 코드는 모두 `_shape(c)`(워커) / `inputs.shape_rules`(API) 가 None 이 아닐 때만 실행. 새 키는 새 스냅샷 산출물에만 들어감.

### 9.2 해시 (SH-26)
- 새 설정 절 `shape_rules` 는 **기존 해시 함수 어디에도 들어가지 않는다**(`_cfg_hash` 의 keep = solver·mesh·solve·grid·mapping·paicad options·select·compare.quality, `_cmp_sha`·`_profile_sha`·`base.json profile` = 지정 키만) → 옛 스터디 해시 불변(시험 V-SH-13).
- 새 스냅샷만: `_sel_cfg_sha` += `transfer_plan.shape_hash_view(rules)`(schema·w_partial·range_guard 의 crit·steps·min_keep_frac·combo — budget 제외). 안 해시(`design_sha`)는 기저 sha 를 통해 W 기저 변화를 이미 포함, ④ `_cmp_sha` 는 형상 메시 sha 로 경로 변화를 이미 포함 → 추가 없음.

### 9.3 beadgraph 판 · 기존 스터디 영향 (SH-27)
- **패키지 변경 없음 → 판 1.1.0·`RULES` 1·`MORPH_RULES` 2 그대로**. 항목 1 은 esl 이 W 변수에 S_W 만 넘겨 해결(SH-6), 항목 2 는 esl 쪽 모듈. 이유: `graph.json` 머리에 `version` 이 들어가(`classify.py:485`) 판을 올리면 재준비 때 graph sha 가 바뀌어 저장된 선택이 `BG_GRAPH_STALE`(409)이 되고 sel 회귀 바이트가 깨짐.
- 기존 schema 2 스터디: `BG_GRAPH_STALE` 없음, 기저 재계산 없음(`GRAPH_ALGO` 1·`MORPH_RULES` 2 그대로), `w_clamp.json` 경로 그대로. schema 1 스터디: 변경 없음.
- physicsai 공유: guard 를 패키지(`beadgraph.guard`, 1.2.0)로 옮기는 것은 후속(그때 graph.json 머리 `version` 변경 → 재준비 1회 `BG_GRAPH_STALE` 재확인 — 계약에 미리 적어 둠).

## 10. 시험 (V-SH-n) — 모듈 단위(모드 무관 합성)와 모드별 계획 시험 분리

**A. 모듈 단위 합성 시험(모드·파일·설정 없이 배열·함수만)**

| ID | 시험 | 위치 |
|---|---|---|
| V-SH-1 | `single`: 해석적 ok_fn(v ≤ t 통과) — usable 이 t 에서 해상도 \|끝−v₀\|/2^steps 안·공칭 쪽, 통과 끝은 그대로, 시험 수 ≤ 2(1+steps), `inward` 반올림 끝이 위반 쪽에 없음, 같은 입력 비트 동일 | `tests/doe/test_range_guard.py` |
| V-SH-2 | `interacting`·`corners`·`combo`: 공유 요소 union-find(크기 1 제외·이름 정렬), k ≤ 4 → 2^k, 크기 초과 → 시드 0 표본(입력 dict 순서와 무관), 합 제약 ok_multi 에서 scale 이분 정확(1/2^steps), 모든 꼭짓점 통과 → None, `max_group` 초과 → 건너뜀 | 같은 파일 |
| V-SH-3 | 예산: 가짜 시계·`max_evals` 로 멈춤 → 멈춘 변수는 skipped(반쯤 줄인 값 없음)·`stopped` 사유, `blocked` 판정(keep 경계값), `doc` 키 순서·스키마 | 같은 파일 |
| V-SH-4 | `guard_probe`: 합성 quad·tria 패치 — 전단으로 야코비안 저하 수 = 직접 계산, 공칭부터 나쁜 요소는 안 셈, tria 최소각, 넓이 비 = `core.extremes` 와 비트 같음, `inverted` = `mesh_quality.inverted_count` 와 비트 같음(= `design_state` 의 뒤집힘) | `tests/doe/test_mesh_quality.py`(추가) |
| V-SH-5 | `route.choose`·`rank_flag`: 면 경계값(1499/1500), n_faces None, `min_step_mb`, relaxed 꺼짐 → cad, enabled false → cad, Fail·tria 경계값·tria null 해석값 | `tests/mesh/test_route.py` |
| V-SH-6 | 독립성: AST — `range_guard.py` 는 `esl.doe`·`beadgraph`·`esl.mesh` import 없음, `route.py` 는 `esl.doe`·`gmsh` import 없음, 둘 다 `open(`·`DEFAULTS`·전역 난수 없음 | `tests/doe/test_range_guard.py`·`tests/mesh/test_route.py` |

**B. 그래프·모핑 시험(패키지 픽스처 H5·H6·stepboss + 합성)**

| ID | 시험 | 위치 |
|---|---|---|
| V-SH-7 | **W 부분**: 픽스처에서 W·비W 세그먼트 묶음 비드 → vars [D, W], W 기저 지지 ⊆ A_W(S_W) — `BG_BASIS_LEAK` 없음·바깥 max ≤ 1e-6, S \ S_W 노드 W 기저 = 0, S_W 달성 W ±1e-3(BG-D-33), D 기저 = 옛 규칙과 비트 같음, `BG_W_PARTIAL` 정보 | `tests/doe/test_bead_graph_wpartial.py` |
| V-SH-8 | **W 부분 legacy**: `shape_rules=None`(또는 `w_partial false`) → `_possible_vars`·derive 문서·params·basis 바이트 = v0.20.0, 전부 W 비드는 두 규칙에서 정규화·기저 비트 같음, 네트워크 묶기 D 만, 타이(SH-8), merge 한 W+비W 세그먼트 = D 만 | 같은 파일 |
| V-SH-9 | **guard ⊇ w_clamp**: H6 자동 seed 에서 기준을 뒤집힘만(jac·tri·area 끔)으로 두면 W 항목 usable = `w_clamp_table` usable 과 같은 수치(1e-4 반올림 포함) — 일반화 증명 | `tests/doe/test_bead_graph_guard.py` |
| V-SH-10 | **guard 기본 기준**: H6 seed 표 → derive 적용 → 새 기본 범위의 모든 단일 끝 안이 `accept` 통과, 새 기본 범위 LHS 30 안 미리보기 판정에서 `SELECT_MORPH_INVERTED` 0·`RG_OUTSIDE_GUARD` 0; 합성 포켓 D·W 조합(깊고 좁은 모서리 뒤집힘) → scale < 1 → 4 꼭짓점 통과; 표 불일치(hold 0·exclude·toggle) → unchecked → `guard_selection` 이 같은 값 | 같은 파일 |

**C. 모드별 계획 시험**

| ID | 시험 | 위치 |
|---|---|---|
| V-SH-11 | 계획 표: 5행의 `bs_wpart`·`bs_guard`·`bs_route`·`bs_mq` = §2.2 표, 빈 칸 → `CONFIG_INVALID`, `PLAN_VERSION` 1 그대로·`hash_view` 불변, `resolve_shape(None)` = None, 잘못된 블록 → `CONFIG_INVALID`, `shape_hash_view` 에 budget 없음 | `tests/doe/test_transfer_plan.py` |
| V-SH-12 | **①②③ select 새 스냅샷**(합성 `synth_bead`·`synth_step_graph`): BD_LOADS 가 `range_guard.json` 을 쓰고 `w_clamp.json` 은 안 씀, API derive = BD_MATRIX derive(같은 표 적용), 사용자 묶음 → BD_MATRIX 보충·`params.json` 축소·`select/<sha12>/range_guard.json`, elems 변수는 `range_check` 경고만, W 부분 변수가 행렬·미리보기·실행까지; stages 는 계획 열만 읽음(① case·② mesh 같은 코드 경로) | `tests/doe/test_shape_rules_modes.py` |
| V-SH-13 | **③ 새·④ 경로**: 합성 STEP(시험에서 `min_faces` 를 낮춰 대형 판정) → cad 세션 호출 0(스파이)·`attempts` [cad SKIPPED relaxed_direct, cad_relaxed READY]·`route`·`MESH_ROUTE_RELAXED`, 직행 메시 = 지금 cad 실패 뒤 cad_relaxed 메시와 바이트 같음; 직행 실패(주입) → auto 는 freeform→tria(세분화 건너뜀 사유 relaxed_direct), mode cad 는 실패 행; 작은 STEP → cad(형상 행 = 옛 행 + `route` 키만); 품질 기준을 낮춰 `MESH_QUALITY_RANK`(④ 행 ⚠·`best_clean_mq`·CSV 끝 열, ③ 결과 1건); 옛 ③·`same`·`mesh` = 변화 없음 | 같은 파일 + `worker/tests/test_doe_shape_rules_jobs.py` |
| V-SH-14 | **회귀(바이트 동일)**: 옛 스냅샷(키 없음) ①②③ `sel_regress`·`selreg`, ④ `scripts/regress.py`(mode 없음·cad·auto × h5·h3 × step·case) main(72e9e8d)과 바이트 동일; 새 DEFAULTS 로도 `_cfg_hash`·`_sel_cfg_sha`·`_cmp_sha`·`select_hash_view`·`_profile_sha`·`base.json` 불변; `packages/beadgraph` diff 0·graph.json 바이트 동일(BG_GRAPH_STALE 없음); `evaluate.py`·`rank.py`·`load_transfer.py`·`stiffness_metric.py` diff 0 | 기존 + 작업 폴더 |
| V-SH-15 | **API·설정**: 4곳 거울(DEFAULTS·pydantic·yaml 2) 값·검사 범위, 새 스터디 `doe.shape_rules`·`inputs.shape_rules` 같은 블록, 옛 스터디 복제 = 키 없음, 새 스터디 복제 = 그대로, derive 에 `shape_rules`·`range_guard` 전달·캐시 키, 행 `guard`·`w_segs`, settings 노출, openapi | `backend/tests/test_doe_shape_rules_api.py` |
| V-SH-16 | **UI**(목): 변수 표 guard 꼬리표(limited·blocked·unchecked 툴팁), W 부분 칩·세그먼트 `W —`, ④ 형상 행 "완화 직행" 칩, 순위 ⚠ + "품질 통과 최상위" 1줄, ③ 결과 띠 1줄; 옛 결과·선택 화면 그대로; 2560×1440·1920×1080 잘림 없음 | `frontend/src/__tests__/doe_shape_rules.test.tsx` |
| V-SH-17 | **성능**: H6(104k) BD_LOADS guard ≤ 30 s, 실크기 합성(≈ 270k 요소·≈ 110 세그먼트 — `synth_step_graph`/perf 픽스처) ≤ `prep_timeout_s` 또는 `RG_BUDGET` 로 멈춤(준비 READY), BD_MATRIX 20 비드 보충 ≤ 60 s | `tests/doe/test_bead_graph_perf.py`(추가) |
| V-SH-R1 | (수동, 이슈 #63) 실 STEP ≈ 2800 면 ③·④: 첫 메시 ≈ 280 s(cad 0 s), 품질 Fail·tria 기록, `MESH_QUALITY_RANK` 표시; ① 20안 새 스터디: 기본 범위 안 `SELECT_MORPH_INVERTED` 0, 줄어든 변수 목록·사유 확인 | 현장 |

## 11. 리스크

| ID | 리스크 | 대응 |
|---|---|---|
| R-SH-1 | guard 가 범위를 너무 줄여(거친 tria 기준 메시, 엄격한 jac) DOE 탐색 폭이 좁아짐 | "새로 나빠진 요소"만 셈, `min_keep_frac`·blocked 표시, feasible 은 위반 쪽만·사용자 확장 허용(경고), 기준 강도 = Q-SH-1 |
| R-SH-2 | 품질이 \|Δ\| 에 단조가 아니면 이분이 경계 하나만 찾아 범위 안에 위반 섬이 남음 | 안 판정(`design_state` 뒤집힘 FAILED_MESH·품질 경고)이 그대로 받침, `RG_OUTSIDE_GUARD` 는 범위 밖만 |
| R-SH-3 | 준비 시간 증가(후보 기저 계산) | 예산(180 s)·seed 우선·`RG_BUDGET`·BD_MATRIX 보충, V-SH-17 측정 |
| R-SH-4 | W 부분: S_W 가 짧으면 접합 램프로 W 효과가 작거나 달성 노드 없음 | 기존 `BG_SEGMENT_SHORT` → `use_default: false`, `w_cover` 표시 |
| R-SH-5 | 1500 면 이상이지만 cad 가 성공했을 모델이 직행으로 품질 나쁜 메시를 받음 | `MESH_QUALITY_RANK`, 기준값 설정·Q-SH-2, `relaxed_direct.enabled` 로 끔 |
| R-SH-6 | 면 수는 크기의 대리 지표(면 수 적고 곡면 큰 모델은 못 잡음) | `min_step_mb` 보조 키, 후속: 같은 STEP sha 의 이전 cad 시간 초과 기록으로 직행(비범위) |
| R-SH-7 | 표에 없는 선택(사용자 묶음·편집)은 첫 행렬에 위험 안이 들어갈 수 있음(지금과 같음) | `RG_UNCHECKED` 표시, BD_MATRIX 보충 후 다음 행렬부터 축소, 셀 `RG_OUTSIDE_GUARD` |
| R-SH-8 | guard 가 esl 안에만 있어 physicsai 가 아직 못 씀 | §9.3 후속(패키지 1.2.0 이관 계획 명시) |

## 12. 파일 소유권 (겹침 0) · 순서

| 에이전트 | 소유 파일 | 금지 | 시험 |
|---|---|---|---|
| **impl-geom**(비드 그래프·모핑 코어) | 신규 `esl/morph/range_guard.py`, 신규 `esl/mesh/route.py`, `esl/doe/mesh_quality.py`(`guard_probe` 추가만), `esl/doe/bead_graph.py`(`w_segs`·`_possible_vars(w_partial=)`·`_bead_nominals`·`_check_ties`·`derive_obj_v2`/`derive_v2`/`normalize_v2` 의 `shape_rules`·`range_guard` 인자·`GraphBead.w_seg_ids/w_cover`·`params_rows_v2` 행 키·`basis_v2` W segs = S_W·`range_guard_table`·`guard_selection`·`write_range_guard`·`load_range_guard`·`RANGE_GUARD_JSON/SCHEMA`·`_graph_figures` W 대표), `esl/doe/bead_select.py`(`range_check(…, only=None)` 키워드 추가만); 신규 시험 `tests/doe/test_range_guard.py`·`tests/mesh/test_route.py`·`tests/doe/test_bead_graph_wpartial.py`·`tests/doe/test_bead_graph_guard.py`·`tests/doe/synth_guard.py`, `tests/doe/test_mesh_quality.py`·`test_bead_graph_perf.py` 추가분 | `packages/beadgraph/**`(전원 금지), `stages.py`·`step_graph.py`·`transfer_plan.py`·`__init__.py`·`report_doe.py`·`resources/**`·`backend/**`·`worker/**`·`frontend/**` | V-SH-1~10·17 |
| **impl-backend**(설정·계획·워커 단계·API) | `esl/doe/__init__.py`(DEFAULTS `shape_rules`), `esl/doe/transfer_plan.py`(열 4개·`resolve_shape`·`shape_hash_view`), `esl/doe/stages.py`(`_shape`·BD_LOADS `_sel_range_guard`/legacy `_sel_w_clamp` 분기·`_sel_prepare` 보충·`_sel_cfg_sha`·셀 `RG_OUTSIDE_GUARD`·`_cmp_mesh_shape` 직행·`_cmp_relaxed_direct`·`_cmp_mesh0` route 행·`_cmp_post`/`bd_post` mq·CSV 열), `esl/doe/step_graph.py`(mesh0 `route`·`quality`·mq 경고), `esl/doe/report_doe.py`(한계 절 1줄), `resources/doe_messages.json`(§8 코드), `backend/esl_platform/core/config.py`(`BeadDoeShapeRulesCfg`·하위 Cfg), `config/esl_platform.example.yaml`·`config/esl_platform.prod.example.yaml`, `backend/esl_platform/api/services/doe.py`(스냅샷·inputs·복제·settings), `backend/esl_platform/api/services/doe_select.py`(`range_guard.json` 읽기·캐시 키·`shape_rules` 전달·`GRAPH_ROW_KEYS`), `backend/esl_platform/api/schemas.py`, `docs/contracts/openapi_p1b.json`, `worker/esl_worker/doe_jobs.py`(결과 키 통과); 시험 `tests/doe/test_transfer_plan.py`(추가)·신규 `tests/doe/test_shape_rules_modes.py`·`backend/tests/test_doe_shape_rules_api.py`·`worker/tests/test_doe_shape_rules_jobs.py` | `packages/beadgraph/**`, impl-geom 소유 파일, `frontend/**`, `evaluate.py`·`rank.py`·`load_transfer.py`·`stiffness_metric.py`·`mesh_gmsh.py`·`mesh_refine.py`(변경 금지 — 직행은 기존 `run_isolated`·`stage_cap` 호출만) | V-SH-11~15 |
| **impl-frontend**(화면) | `frontend/src/api/types.ts`·`frontend/src/api/doe.ts`(필드·§8 문구 맵·정보 집합), `frontend/src/components/DoeParamTable.tsx`·`SegmentTree.tsx`·`BeadList.tsx`·`DoeRanking.tsx`·`DoeInputs.tsx`, `frontend/src/pages/doe/DoeStudy.tsx`, 목 `frontend/src/mock/graphmock.ts`·`doedata.ts`·`server.ts`, 신규 `frontend/src/__tests__/doe_shape_rules.test.tsx` | 프런트 밖 전부 | V-SH-16 |
| 통합(lead) | 이 문서, `docs/decisions.md`(SH 결정 등록), `CHANGELOG.md`, `VERSION`, `docs/manual/*`(형상 규칙 안내), 기존 계약 상호참조 줄 | – | V-SH-14 실행·V-SH-R1 안내 |

- 순서: impl-geom ∥ impl-backend(설정·계획 열·API·스냅샷 먼저) ∥ impl-frontend(목) → impl-backend 단계 배선(§2.3·§3·§4 시그니처 사용) → 통합 E2E(V-SH-12·13) → 회귀(V-SH-14) → 현장(V-SH-R1).
- 공동 수정 금지: `bead_graph.py`·`bead_select.py`·`mesh_quality.py`·신규 두 모듈 = impl-geom 단독, `stages.py`·`step_graph.py`·`transfer_plan.py`·`__init__.py`·`doe_messages.json`·`backend/**`·`worker/**`·yaml = impl-backend 단독, `frontend/**` = impl-frontend 단독.

## 13. 사용자에게 물을 결정 (권고안으로 진행 — 답에 따라 §6 기본값만 바뀜)

| Q | 질문 | 선택지 | 권고 |
|---|---|---|---|
| Q-SH-1 | 범위 자동 축소의 품질 기준 강도 | (A) **표준** = 뒤집힘 0 + 새 야코비안 < 0.3 없음 + 새 tria 최소각 < 10° 없음 + 넓이 비 ≥ 0.2 / (B) 엄격 = A + `compare.quality` 기준 새 Fail 0(`max_new_fail_ratio` 0 근처) / (C) 뒤집힘만(지금 W 줄임을 D 까지 넓힘) | **A** — 뒤집힘 직전의 찌그러짐까지 미리 거르되, HyperMesh Fail 기준(jac 0.6 등)으로 막으면 거친 기준 메시에서 범위가 크게 줄어 DOE 가 무의미해짐. 안 판정(품질 = 경고만, D-0.16-P2)과도 어긋나지 않음 |
| Q-SH-2 | cad 를 건너뛰고 완화 메싱으로 바로 갈 STEP 크기 | (A) **면 ≥ 1500** / (B) 면 ≥ 1000(지금 '대형 모델' 기준과 같음) / (C) 면 ≥ 2500 | **A** — 서버 실측 2800 면·합성 1915 면(cad 438 s 실패)을 모두 포함하고, 1000~1500 면 모델의 cad 성공 가능성(품질이 더 좋음)은 남김. 숫자는 설정이라 현장 측정 뒤 바꾸기 쉬움 |
| Q-SH-3 | 메시 품질 미달(Fail > 10 % 또는 tria > 15 %) 형상·기준 메시의 순위 처리 | (A) **경고만** — 순위 유지 + 행 ⚠ + "품질 통과 최상위" 1줄 / (B) 품질 미달 형상을 순위에서 빼고 따로 표시 | **A** — 지금까지 품질은 막지 않는 원칙(SC-D-13·D-0.16-P2·D-0.16.1-Q1)과 같고, 큰 모델은 완화 메싱이 유일한 성공 경로라 빼면 비교 자체가 사라짐 |
