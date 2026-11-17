# 사용자 로컬 PC의 Codex에 전달할 작업 지시

대상 저장소는 **사용자의 Windows PC/WSL에 내려받은 저장소**다. 대화 세션의 임시 폴더·솔버·가상환경에
접근할 수 있다고 가정하지 않는다. 사용자 포크의 원격 브랜치가 입력 자료의 출처다.

로컬 터미널에서 처음 받는 경우:

```bash
git clone --branch codex/corner-drop-benchmark https://github.com/pikachu444/esl-platform-fork.git esl-platform-local
cd esl-platform-local
```

아래를 로컬 Codex 채팅에 전달한다. 이미 작업 중인 저장소라면 변경사항을 보호하고 같은 원격 브랜치를
별도 워크트리로 가져온다. 기존 작업을 초기화하거나 덮어쓰지 않는다.

```text
이 작업은 내 로컬 Windows PC에서 수행한다. 현재 열린 로컬 저장소를 먼저 확인해라.
ChatGPT 세션의 /workspace 경로나 세션에 설치된 솔버·Python 환경은 사용할 수 없다.

자료 저장소:
https://github.com/pikachu444/esl-platform-fork
기준 브랜치: codex/corner-drop-benchmark
작업 브랜치: codex/local-corner-drop (별도 워크트리 권장)
PR 생성이나 main 병합은 하지 마라.

먼저 원격 브랜치를 가져오고 다음 파일을 로컬 저장소에서 실제로 읽어라.
1. AGENTS.md
2. docs/research/esl_methods.md
3. docs/contracts/esl_corner_drop_benchmark.md
4. docs/benchmarks/corner_drop.md
5. docs/benchmarks/corner_drop_20261117/report.md
6. config/corner_drop_benchmark.json

목표는 코너로 낙하하는 넓은 판재에서 여섯 정적 대체방법을 재현하고,
정적 탐색이 고른 비드와 실제 재낙하의 성능을 비교하는 것이다.

수행할 일:
- 내 PC의 Windows/WSL/Python/Git/Node 및 설치된 솔버를 확인해라.
  검증된 실행 경로는 Linux/WSL이다. Windows 네이티브 지원을 확인 없이 선언하지 마라.
- 로컬 저장소 기준으로 가상환경과 의존성을 준비해라.
- 포함된 install_solver 명령으로 OpenCourant를 내 PC에 받고 고정 SHA256을 검증해라.
- 먼저 축소 실행으로 솔버·필드 변환·정적 계산·재낙하·보고서 연결을 확인해라.
- 그다음 40 ms 전체 설정으로 재현하고 기존 실제 결과와 비교해라.
- 기존 DOE를 유지하면서 코너 낙하 방법 비교 화면의 여섯 실행 버튼을 로컬 API에 연결해라.
  진행/실패/취소/보고서/CSV/JSON/원자료 받기까지 실제로 확인해라.
- 기준 형상 변위 재현만으로 설계 변경 예측이 성공했다고 판단하지 마라.
  평형, 절점 대응, 단위, 반력, 운동량, 에너지, 질량, 소성 적분점을 확인해라.
- 대체방법의 선택안과 독립 검증 집합에서 관측한 개선안을 구분해라.
  명목 변위가 줄어도 자세 변경에서 소성이 악화되면 강건한 개선이라고 쓰지 마라.
- 1회 외부 반복이 구현되어 있다. 다회 갱신 수렴과 실제 TV 조립체 적용을 이미 구현된
  기능이라고 가정하지 마라. 후속 개발은 기존 결과와 미해결 원인을 확인한 뒤 명세부터 갱신해라.
- 내 PC에서 수행한 명령·설치 위치·솔버 해시·실제 결과·미수행 검증을 기록해라.
- 중간마다 자신의 작업 브랜치를 커밋하고 내 포크에 푸시해라. 강제 푸시는 하지 마라.

세션의 임시 파일을 요구하거나 존재하지 않는 원격 자료를 읽었다고 주장하지 마라.
필요한 정의·근거·코드·예시 결과는 모두 위 원격 브랜치에서 내려받아 사용해라.
```

## 구현/검증 범위

실제 Linux 솔버 실행, 공통 탐색, 방법별 정적 풀이, 선택안/독립 후보의 실제 재낙하,
자세 변화/세분화, 보고서와 방법별 버튼이 구현되어 있다. 실제 실행 수치와 실패는 날짜별 결과 폴더를
따른다. 소스 빌드/기능 시험과 DB/GUI 시험의 범위를 혼동하지 않는다. 결과 폴더의 VALIDATION.md가
수행 여부를 명시한다.
