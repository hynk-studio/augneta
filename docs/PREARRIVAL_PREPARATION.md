# TactSleeve 선행 개발: 출력 표현과 교정 리허설

2026-10-15. 장비 없이 검증 가능한 소프트웨어 기능이다. 실행 결과와 미검증 항목은
[검증 기록](VERIFICATION_PREARRIVAL.md)에 둔다.

## 지금 사용할 수 있는 것

- `tactile.py`: 방향/크기 의미를 나타내는 `CodeSpec`과 6모터 표현 `TactileProfile` 분리.
  기본 후보는 6방향·2강도이며 위치나 지각 능력을 측정한 결과가 아니다.
  명시적인 패턴을 공급하면 의미 범주 수와 모터 수를 다르게 구성할 수 있다.
- 한 의미 상태에서 시각 벡터와 좌/우 3개 명령값을 만들고 같은 pulse/gap을 전달한다.
  개인별 gain을 바꿔도 의미와 시각 벡터는 바뀌지 않는다. 같은 패턴으로 의미를
  조용히 합치는 설정은 거부한다. 이것이 모든 패턴의 지각적 구별을 보장하지는 않는다.
- `/calibration`: 화면의 모터 표시를 보고 응답하는 개발 리허설. 직접 선택,
  무자극, 구별 못함을 구분하고 교정 블록과 홀드아웃 블록을 따로 기록한다.
- 교정 블록 뒤 gain/timing을 수동 조정하고 프로필을 고정한다. 검증 중에는
  프로필/의미를 변경할 수 없다. 이 수동 리허설에 자동 개인화는 적용하지 않는다.
  별도의 [5.0-4 모의 비교](SELECTIVE_CALIBRATION.md)는 가상 응답으로만 gain 후보를 선택하며
  그 결과를 이 화면이나 실제 장치에 자동 설치하지 않는다.
- 후보 프로필과 세션 JSON 내보내기, 프로필 다시 불러오기, 중단 기록 보존.
  프로필을 불러온 뒤에는 새로운 교정 블록을 시작한다. 중단된 세션의 재개는 지원하지 않는다.

기본 6방향 × 2강도 + 무자극 2개로 블록당 14회, 총 28회다. 소프트웨어 기본값이며
인간 연구에 필요한 시행 수나 유효 감각 채널 수의 근거가 아니다. gain·명령 강도·
150 ms pulse/150 ms gap도 시험용 값이고, 착용자의 편안한 범위로 검증되지 않았다.

`CodeSpec.encode()`는 인과 추정기의 belief에서 방향/크기만 양자화한다. 목표·행동·
평가기 truth를 받지 않는다. 불확실성·센서 age/누락 표시는 기존 과제에 남아 있으며,
새 6슬롯 경로와 기존 추적 UI의 연결은 후속 통합이다. 기존 과제의 8방향 패킷과
`haptic-smoke`는 이전 기준선을 보존한다. 현재 결과를 6모터 촉각 조건의 추적 성능으로
보고하지 않는다.

## 화면 사용

1. 서버 실행 후 `http://127.0.0.1:8000/calibration`을 연다. 기존 과제 하단에도 링크가 있다.
2. 후보 gain/timing을 정하거나 JSON 프로필을 불러온 뒤 **Start fit block**을 누른다.
3. **Show next pattern** 뒤 방향/크기, **No pattern**, **Cannot identify** 중 하나로 응답한다.
   pulse와 gap이 끝나기 전 응답은 서버에서도 거부한다. 다음 정답·전체 일정은 API에 노출하지 않는다.
4. 교정 블록의 혼동표를 확인한다. 필요한 수동 조정 후 **Freeze profile & start validation**을 누른다.
5. 검증 블록 종료 후 보고서와 JSON을 내려받는다. 도중에 Stop을 눌러도 받은 응답은 남는다.
   화면을 떠나면 표시를 지우고 해당 세션 정지를 요청하며, 늦게 온 제시 응답이 다시 표시되지 않게 한다.

정답 label을 직접 보여주지는 않지만 화면에서 모터 출력을 읽는 리허설이므로 촉각
맹검 실험이 아니다. 자동 테스트의 합성 응답과 사람이 화면을 보고 입력한 개발 응답은
`response_provenance`로 구분한다. `human_evidence=false`는 인간 연구 결과를 주장하지
않는다는 뜻이며 실제 키보드 응답의 존재를 합성 자료로 바꾸는 표지가 아니다.

세션은 서버의 `--log-dir` 아래 `calibration/<session UUID>/session.json`에 매 응답마다
저장한다. 교정/검증 자료, 두 프로필, 명령, 중단·변경 사건을 분리한다. 서버 간격은
전송 시간을 포함하므로 지각 반응 시간으로 쓰지 않는다. 실제 자극 시각/장치 ACK는
측정하지 않으며 프로필은 항상 `unvalidated_hardware_candidate`다. Git에는 응답을 넣지 않는다.

## Site, 클라우드, 실제 PC의 역할

| 실행 장소 | 현재 역할 |
| --- | --- |
| 클라우드 개발 작업공간 | 코드·API·합성 검증·PR 작성. 사용자 BLE 장치를 원격으로 조작하지 않음 |
| 기존 [ChatGPT Site](https://augneta-lab.hynk1240.chatgpt.site) | 기존 숨은 흐름 데모. 확인한 배포는 v1이며 이번 교정 기능은 아직 배포하지 않음 |
| Windows PC | 새 Flask 화면을 실행하고, 장비 도착 후 Player와 함께 실물 연결을 검증할 우선 호스트 |
| Apple Silicon 맥 | 공식 Python SDK 지원 범위 내의 대안. 첫 장비 세션에서는 PC 한 대를 기준으로 고정 |

개발에 로컬 Codex는 필요 없다. 데모 Site의 사용과 로컬 브라우저에서 같은 저장소의
화면을 여는 것은 함께 가능하다. Site의 별도 배포본과 GitHub 브랜치가 자동으로
동기화된다고 가정하지 않는다. 원격 HTTPS Site→로컬 Player 연결은 아직 검증하지 않았다.

공식 [Python SDK 안내](https://docs.bhaptics.com/sdk/python/guide)는 Windows 10/11 x64,
Apple Silicon macOS, Python 3.8–3.12, Player와 haptic app 설정을 요구한다.
Augneta와 겹치는 Python 3.12를 로컬 실물 준비의 기준으로 삼는다. 이번 리허설에는
Player, bHaptics SDK, BLE, 계정/API key, GPU가 필요 없다. 실제 장치 어댑터를 붙일 때
SDK 버전을 고정하고 설치·출력을 별도로 확인한다.

## Windows에서 실행

Python 3.12와 Git이 설치된 PC의 PowerShell에서, 새 폴더를 사용할 경우:

```powershell
git clone --branch feat/haptic-output-preparation https://github.com/hynk-studio/augneta.git
cd augneta
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m augneta serve --port 8000
```

브라우저에서 `http://127.0.0.1:8000/calibration`을 연다. 기존 체크아웃이 있으면
먼저 변경 상태를 확인하고 해당 작업을 보존한다. 위 branch는 검토 중인 PR이며
main에 병합된 기능이라고 가정하지 않는다. 가상환경 활성화나 PowerShell 실행 정책
변경은 필요 없다. 서버는 터미널에서 Ctrl+C로 종료한다.

## macOS에서 실행

동일 브랜치를 새 폴더에 받은 뒤 Python 3.12를 사용한다:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pip check
.venv/bin/python -m augneta serve --port 8000
```

Windows/macOS 명령은 로컬 실행 안내이며 이번 Linux 작업공간에서 해당 OS의 설치를
검증했다는 뜻은 아니다. 장비가 오면 실제 호스트에서 설치와 연결을 확인한다.
