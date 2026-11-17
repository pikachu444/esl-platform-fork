# 비드 형상 변경을 위한 ESL 후보 방법과 조사 근거

사용자 로컬 PC에서도 이 문서, 연결된 계약, 구현, 실제 결과를 함께 읽을 수 있도록 저장소에 포함했다.
출발점은 [wgcha/esl-platform](https://github.com/wgcha/esl-platform)의 고정 ESL 형상 평가다.
실행 코드와 자료는 사용자 포크 [pikachu444/esl-platform-fork](https://github.com/pikachu444/esl-platform-fork)의
`codex/corner-drop-benchmark` 브랜치에 둔다. 세션 내부 파일을 읽는 작업은 필요하지 않다.

## 문제 정의

기준 형상의 충돌에서 전체 강체 이동과 회전을 제거한 변형장 u0를 구하고, 기준 선형 쉘 강성 K0로
이를 재현하는 정적 하중 f0를 만든다. 비드를 모핑한 뒤 같은 절점 ID·요소 연결과 f0를 유지하고 K1을
풀었더니 정적 변위가 매우 커지는 문제다. 기준 변위 재현은 이 하중이 변경 형상의 실제 충돌 변형까지
예측한다는 검증이 아니다.

노드 위치 변화로 전체 모멘트 평형과 3-2-1 지지 반력이 바뀔 수 있다. 동시에 분포 하중이 새 형상의
탄성 굽힘 모드에 투영되는 방식도 달라진다. 합력·합모멘트를 0으로 맞추는 것은 후자를 제거하지 않는다.
기하/소성/접촉 경로를 초기 선형 탄성 강성으로 대체하는 오차도 따로 확인해야 한다.

## 실제 구현한 후보

| 코드 | 정의 | 문헌과의 관계 | 구현 위치 |
|---|---|---|---|
| D0 | 기준 K0와 순수 변형 u0로 구한 f0를 변경 K1에 그대로 적용 | 기존 방식 대조군 | `esl/mech/drop_surrogates.py` |
| D1 | 후보 좌표·실제 절점 질량으로 D0의 합력·합모멘트 관성완화 후 정적 풀이 | 전체 평형 영향 분리용 진단 | 같은 파일 |
| P0 | 측정 접촉력 + 중력 - 실제 전체 가속도의 관성력, 후보별 평형 보정 | 이번 실험의 힘 기반 자유 판 근사 | 같은 파일 |
| P1 | 측정 접촉력 + 중력의 관성완화 후 정적 풀이 | NOCS를 자유 낙하 판에 확장한 실험 | 같은 파일 |
| I0 | 기준 시간 경로의 변형 형상에서 증분 K·Δu를 만들고, 후보별 고정 증분 모델의 해를 누적 | DiESL의 비드 법선 오프셋 확장. 검증된 동일 방법 아님 | 같은 파일 |
| R0 | 같은 기준 변형장의 응축 에너지비로 변위 크기를 추정 | 1-벡터 근사의 음성 대조군 | 같은 파일 |

정확한 식·좌표계·강체 게이지·시점·제약·평가 기준은
[실험 계약](../contracts/esl_corner_drop_benchmark.md)을 따른다. I0는 초기 응력 강성, 소성 접선강성,
후보 자체의 실제 찌그러진 경로를 알지 못한다. P0의 가속도는 강체 가속도를 먼저 제거한 가속도가 아니다.

## 1차 문헌

| 출처 | 확인한 내용 | 이번 문제에 적용할 때의 경계 |
|---|---|---|
| Kosaka (2010), *Improvement of Energy Absorption for the Side Member Using Topography Optimization* | LS-DYNA와 정적 topography를 외부 반복으로 연결한 실제 비드 설계 사례 | 정적 목적값을 충돌 에너지와 동일시하지 않고 변경안의 실제 충돌을 갱신해야 함 |
| Clemens & Schumacher (2023), *Nested loop approach ... using contact forces for the inner loops*, DOI 10.1016/j.istruc.2023.06.015 | 변위 역산 ESL 대신 충돌 접촉력을 선형 정적 내부 반복에 쓰는 NOCS | 고정단 박판 예제를 자유 낙하 판의 관성완화 검증으로 바꿔 말할 수 없음 |
| Clemens 후속 학위논문, §5·§7.2 | 변형 전 절점 위치의 접촉 하중 전달, 시점별 독립 하중, 강성/충돌 성능 관계와 외부 반복 한계 | 직접 쉘 절점 형상 최적화까지 동일 구현으로 검증한 자료는 아님 |
| Triller et al. (2021), DiESL, DOI 10.1007/s00158-020-02830-x | 변형 형상 기준의 증분 등가하중과 누적 응답 | 두께 최적화 검증이 비드 형상 매핑을 자동 정당화하지 않음 |
| Genest et al. (2015), WCSMO11 paper 1167 | 초기 형상의 민감도와 형상 변수, 실제 비선형 평가를 이용한 설계 갱신 | 동일 고정 ESL을 큰 형상 변경에 재사용하는 근거로 볼 수 없음 |
| Bai et al. (2019), DOI 10.1007/s00158-018-2054-8 | 에너지 수준을 맞추는 ESL 스케일링 | 초록 수준 확인. 모든 후보에 동일 상수를 곱하면 선형 변위 비율과 순위 문제는 그대로임 |
| Ren et al. (2020), DOI 10.1177/0954407020940138 | 변위 기반 스케일링 | 초록 수준 확인. 본 벤치마크에 별도 구현하거나 검증한 방법으로 표시하지 않음 |

원문 링크:

- https://lsdyna.ansys.com/wp-content/uploads/attachments/CrashSafety-4.pdf
- https://doi.org/10.1016/j.istruc.2023.06.015
- https://oms.uni-wuppertal.de/en/publications/dissertation/dr-ing-philipp-clemens/
- https://doi.org/10.1007/s00158-020-02830-x
- https://web.aeromech.usyd.edu.au/WCSMO2015/papers/1167_paper.pdf
- https://doi.org/10.1007/s00158-018-2054-8
- https://doi.org/10.1177/0954407020940138

문헌 조사가 전 세계 모든 연구의 전수조사라는 뜻은 아니다. 초록만 확인한 자료를 본문까지 확인했다고
표시하지 않는다. 외부 논문 원문 전체를 이 저장소에 복제하지 않고 출처와 이번 분석을 보존한다.

## 실제 검증과 접근 방법

- 실행 안내: [docs/benchmarks/corner_drop.md](../benchmarks/corner_drop.md)
- 비교 명세: [docs/contracts/esl_corner_drop_benchmark.md](../contracts/esl_corner_drop_benchmark.md)
- 로컬 Codex 작업 지시: [docs/development/codex_corner_drop_task.md](../development/codex_corner_drop_task.md)
- 수치 코드: `esl/mech/drop_surrogates.py`
- 실제 충돌 입력/실행/탐색: `esl/benchmarks/`
- 실제 실행 결과: `docs/benchmarks/corner_drop_20261117/`

비교 화면은 공개 판재 벤치마크 전용이다. 사용자 TV 조립체의 기존 하중을 위 여섯 가지로 자동 변환하는
범용 기능까지 완성했다고 표시하지 않는다. 최종 보고서의 명목 개선과 자세 변화의 소성 악화를 함께 읽는다.
