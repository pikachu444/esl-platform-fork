# Windows PC의 WSL2에서 탄성 코너 낙하 ESL 검증 재현

자료와 코드는 [사용자 포크의 작업 브랜치](https://github.com/pikachu444/esl-platform-fork/tree/codex/esl-shape-method-selection)에 있습니다. WSL2 Ubuntu 터미널에서 실행합니다. 처음 설치하면 WSL의 홈 아래에 저장소를 복제합니다.

```bash
git clone --branch codex/esl-shape-method-selection https://github.com/pikachu444/esl-platform-fork.git
cd esl-platform-fork
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-platform.txt matplotlib pillow
python -m esl.benchmarks.install_solver --config config/shape_method_validation.json --destination out/solver

export OPENBLAS_NUM_THREADS=1
python -m esl.benchmarks.shape_methods baseline --solver out/solver/OpenCourant --out out/elastic-corner
python -m esl.benchmarks.shape_methods all --solver out/solver/OpenCourant --out out/elastic-corner
python -m esl.benchmarks.shape_report out/elastic-corner
python -m esl.benchmarks.shape_sensitivity --solver out/solver/OpenCourant --out out/sensitivity --jobs 4
python -m esl.benchmarks.shape_sensitivity --solver out/solver/OpenCourant --out out/sensitivity --jobs 4 --inclination
python -m esl.benchmarks.first_order_esl_example
```

방금 실행할 방법만 고르려면 `all` 명령에 `--method snapshot_esl` 또는 `--method incremental_balanced`를 붙입니다. 별도 출력 폴더를 쓰면 결과를 나란히 확인할 수 있습니다. GUI는 저장소의 [실행 설정](benchmarks/corner_drop.md)에 따라 솔버 경로를 등록하고 프로젝트의 **코너 낙하 방법 비교**에서 **탄성 방법론 검증 · 수직 대각선 코너 낙하**를 선택합니다.

## 로컬 Codex에 전달할 지시문

> 이 작업은 내 Windows PC의 WSL2 Ubuntu에서 수행한다. `pikachu444/esl-platform-fork`의 `codex/esl-shape-method-selection`을 기준으로 삼고, 기존 로컬 변경사항을 보호한다. `AGENTS.md`, `docs/contracts/esl_shape_method_selection.md`, `docs/local_codex_shape_methods.md`를 먼저 읽는다. `LAW1` 탄성 코너 낙하 기준부터 재현하고, 코드에 고정된 독립 비드 깊이 변경으로만 ESL 방법을 비교한다. 공통 시각의 변위장, 피크 RMS, 변화 방향, 구속 의존성과 비드 5 민감도의 시간증분·메시 의존성을 실제 솔버 결과로 확인한다. 보고서와 JSON의 수치를 근거로 통과 여부와 검증 범위를 기록한다. PC에서 받아 쓰는 파일과 솔버 경로를 기록하고 중간 결과를 별도 작업 브랜치에 커밋·푸시한다. PR 생성과 `main` 병합은 하지 않는다.
