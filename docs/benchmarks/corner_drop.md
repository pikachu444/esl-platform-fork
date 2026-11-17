# 코너 낙하 방법 비교 실행

기존 ESL/DOE를 유지하면서 독립 판재 벤치마크를 추가했다. 라이브러리의 **코너 낙하 방법 비교** 버튼으로
진입한다. 등록된 TV 조립체의 ESL을 자동 변환하는 기능은 아니다. 방법 정의는
[계약](../contracts/esl_corner_drop_benchmark.md)에 있다. 고정 ESL, 평형 보정 ESL, 접촉·가속도,
접촉·관성완화, 증분 형상, Ritz의 여섯 방법을 같은 실제 동해석 기준으로 비교한다.

## Linux / Windows WSL 재현

저장소 루트, Python 3.11 이상에서 실행한다. Windows 네이티브 실행은 검증하지 않았다.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e packages/beadgraph -e '.[benchmark]'
python -m esl.benchmarks.install_solver --destination /path/to/solver-runtime
python -m esl.benchmarks.corner_drop all \
  --solver /path/to/solver-runtime/OpenCourant \
  --out /path/to/corner-results
python -m esl.benchmarks.report /path/to/corner-results
```

기준 OpenCourant ZIP을 내려받고 SHA256을 확인한다. 솔버 라이선스는 배포본의 licenses에 있다.
솔버 실행 파일은 Git에 추가하지 않는다. 기본 전체 실행에는 수 분에서 수십 분이 걸릴 수 있다.
방법 하나만 실행하려면 `--method contact_inertia_relief`처럼 지정한다. 단계는 `baseline`, `search`,
`validate`, `all`이다. `validate`는 같은 출력 폴더의 `search.json`을 사용한다. 설정/솔버 해시가
같은 성공 해석은 재사용한다. 같은 출력 폴더의 동시 실행은 차단한다.

실행 연결만 확인할 때는 다음 설정을 사용한다. 6 ms 결과를 낙하 성능 판정에 사용하지 않는다.

```bash
python -m esl.benchmarks.corner_drop all \
  --config config/corner_drop_smoke.json \
  --solver /path/to/solver-runtime/OpenCourant --out /path/to/smoke-results
```

## 실제 버튼 연결

플랫폼의 기존 설정 파일에 다음을 지정하고 기존 방법대로 API를 실행한다.
기존 `bead_doe.enabled`와 독립적인 실험 실행 설정이다.

```yaml
bead_doe:
  corner_drop:
    enabled: true
    solver_root: /path/to/solver-runtime/OpenCourant
    max_runtime_s: 10800
    max_listed_runs: 50
    download_max_mb: 4096
```

프런트는 `npm ci && npm run build`로 빌드한다. 기존 배포/DB/로그인 설정은 저장소 설치 안내를 따른다.
프로젝트 라이브러리 → 코너 낙하 방법 비교에서 전체/방법별 실행, 전체/축소 프리셋, 진행 상태,
취소, 표와 보고서/CSV/JSON/영상/원자료 ZIP 받기를 제공한다.

- API: `/projects/{project_id}/corner-drop/settings`, `/runs`, `/runs/{id}`, `/runs/{id}/cancel`,
  `/runs/{id}/files/{name}`. 기존 `/esl/api` 접두를 사용한다.
- 기존 프로젝트 역할·CSRF 의존성을 사용한다. 실행·취소는 power/admin, 조회·다운로드는 멤버다.
- 브라우저에서 명령·솔버 경로·임의 설정 파일을 받지 않는다. 두 개의 고정 프리셋만 허용한다.
- 실험은 `<esl_root>/_corner_drop/<project hash>/<run id>`에 저장한다. 전용 Linux 프로세스에서
  실행하고 상속된 flock으로 서버 전체 실험 1건을 제한한다. API 재시작 시 살아 있는 워커는 계속 실행하며,
  종료된 워커의 미완료 상태는 중단으로 표시한다. 실행 시간 상한과 프로세스 그룹 취소가 있다.
- 실험 워커는 기존 PostgreSQL `jobs` 대기열에 등록하지 않는다. 이 화면의 실행 기록으로 조회한다.
  기존 워커 슬롯·스케줄러까지 통합한 기능이라고 표현하지 않는다.
- 원자료 ZIP에는 NPZ/입력/로그/보고서를 넣는다. 재생 가능한 원본 ANIM과 재시작 파일은 서버에 남는다.
  기본 4 GB 다운로드 제한을 넘으면 관리자 경로에서 직접 회수하거나 제한을 조정해야 한다.

## 결과 판독

`result.json`과 `comparison.csv`의 accepted는 명목 자세·거친 메시의 개선/소성/질량/해석품질 판정이다.
자세 변화와 세분화까지 통과한 강건한 설계라는 뜻이 아니다. `report.html`, `report.md`,
`observed_control.json`이 이 차이와 모든 실패를 설명한다.

`history.npz`는 실제 솔버 출력에서 추출한 절점 좌표·유한 Kabsch 변위·속도·가속도·접촉 반력·내부력과
두께 5개 적분점 소성변형률, 상하면 응력/변형률을 포함한다. `candidates.json`은 고정 시점별 정적
합력·합모멘트·개별 지지 반력·실제 해 잔차를 보존한다. `sensitivity.png`는 같은 절점/요소를 유지하고
비드 하나만 1 mm 바꾼 정적 예측과 실제 재낙하를 비교한다.

물리/방법의 미해결 한계와 품질 기준 변경 이력은 계약과 실행 보고서에서 확인한다.
연구용 확장 I0/P0/P1을 문헌의 동일 모델 검증이라고 표현하지 않는다.
