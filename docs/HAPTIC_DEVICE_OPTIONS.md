# 촉각 장치와 웹 연결 후보

2026-10-14 공식 문서 확인. 아래는 설계 검토이며 구매·연결·출력 결과가 아니다.
소프트웨어 준비의 범위는 [PR-02 과제](tasks/HAPTIC_OUTPUT_AND_CALIBRATION.md)에 있다.

## 선택 제안

**기성품 첫 검토 후보는 bHaptics TactSuit Air**로 한다. 8개 논리 채널을
물리적으로 다른 위치에 배정할 수 있는지 확인하는 데 필요한 출력점 수와
공식 SDK가 있다는 점을 근거로 한 제안이다. 착용 적합성, 위치 구별 가능성,
출력 지연은 아직 모른다. 장치가 이미 있다면 해당 모델부터 같은 조건을 확인한다.

| 후보 | 공식 자료로 확인한 내용 | 이번 실험에 대한 판단 |
| --- | --- | --- |
| TactSuit Air | 16개 ERM 모터, BLE, 미국 스토어 표시가 $320. 오디오 유선 입력은 2채널 | 8개 위치를 선택하는 첫 검토 후보. 오디오 모드로 8채널 명령을 대체하지 않음 |
| TactSuit Pro | 32개 ERM 모터, 미국 스토어 표시가 $565 | 더 많은 위치가 필요할 때 대안. 현재 8개 부호만으로 추가 비용의 이점을 단정할 수 없음 |
| Hapticlabs Satellite | 독립 출력 2개, USB/UART, ESP32와 DRV2605 기반 | 단일 기기는 현행 8개 공간 채널과 맞지 않음. 여러 기기의 동기화는 미검증 |
| 직접 제작하는 8점 진동 밴드 | 이 저장소의 설계 대안이며 선정한 제품이 아님 | 위치 배치는 자유롭지만 기구·구동 회로·펌웨어·정지 기능까지 개발해야 함 |

가격은 확인일 미국 페이지 표시값이며 배송·세금·한국 판매 가격을 포함한 견적이 아니다.
Air/Pro의 모터 개수가 사람이 구별할 수 있는 감각 채널 수를 보장하지 않는다.

Air의 SDK 인덱스는 16개 연속 슬롯이 아니다. 공식 motor-index 문서는 Pro와
같은 격자를 사용하며 Air의 활성 슬롯을 앞 `0–3`, `12–15`, 뒤 `16–19`,
`28–31`로 설명한다. 따라서 연결 시 모델별 슬롯을 검사하고 하나씩 확인해야 한다.
현재 mock의 `0–7`을 실제 Air에 그대로 보내면 안 된다. 이 PR은 실물 프로파일을
하드코딩하지 않는다. 방향과 신체 위치의 대응은 교정 후 별도 프로파일로 고정한다.

## 웹 사용 경로

공식 `tact-js`는 브라우저용 SDK지만, bHaptics Player 설치·실행과 장치 연결을
전제로 한다. 공식 JavaScript 가이드는 Windows 10/11 x64 또는 Apple Silicon
macOS, 배포한 haptic app의 App ID/API key를 요구한다. Dot 모드는 각 모터의
명령 세기와 지속 시간을 지정할 수 있다. 이 경로를 **브라우저에서 장치로 직접
BLE 연결**이라고 설명하면 안 된다.

따라서 제안 경로는 웹 과제 → 브라우저 어댑터 → 사용자 PC의 Player → 장치다.
로컬 Codex는 필요하지 않지만 Player는 별도 프로그램이다. 실제 HTTPS 사이트와
Player 사이 연결, 브라우저 권한·연결 정책, 대상 장치만의 선택, 키 노출 범위,
SDK 라이선스와 버전 고정은 통합 전에 확인해야 한다. 현재 Sites 배포에서 이
경로를 시험하지 않았다. 클라우드 서버가 사용자의 BLE 장치를 직접 조작하지 않는다.

직접 제작 장치의 대안은 Web Bluetooth다. MDN 문서상 보안 컨텍스트, 사용자 동작에
따른 장치 선택, 권한 정책이 필요하고 Web Worker에서는 제공되지 않는다. Firefox와
Safari 지원을 전제로 하지 않는다. Chrome/Edge에서도 OS·장치·정책을 실제로 확인해야
한다. 이 대안을 택하면 Python 추정기를 실행하는 Worker에서 패킷만 보내고 창의
장치 어댑터가 연결을 담당한다. 임베디드 미리보기의 권한을 가정하지 말고 직접 연
HTTPS 사이트에서 검증한다. 이는 설계 대안이며 구현된 연결이 아니다.

## 구매 또는 연결을 결정하기 전 확인할 것

- 보유 모델·사용 PC·착용 위치·예산 범위.
- 공식 SDK로 서로 다른 8개 실제 출력점을 개별 선택할 수 있는지.
- 다른 앱의 haptic playback을 끈 상태에서 대상 장치만 선택하고 중단할 수 있는지.
- host 정지·연결 해제 중에도 장치의 제한된 펄스가 종료되는지.
- 웹에서 정상·지연·중단 조건을 기록할 수 있는지.

구매나 실물 출력을 실행한 것으로 기록하지 않는다. 여덟 위치 또는 네 세기가
구별되지 않으면 새 부호 버전을 설계하고 시각 비교 조건도 같은 정보량으로 바꾼다.
어려운 문항이나 사용자만 제외해 원래 코드가 성공했다고 보고하지 않는다.

## 공식 출처

- [TactSuit Air 제품·가격](https://www.bhaptics.com/shop/buy-tactsuit/tactsuit-air/)
- [TactSuit Pro 제품·가격](https://www.bhaptics.com/shop/buy-tactsuit/tactsuit-pro/)
- [bHaptics motor index](https://docs.bhaptics.com/sdk/further/motor)
- [bHaptics JavaScript guide](https://docs.bhaptics.com/ko/sdk/js/guide)
- [공식 tact-js 저장소](https://github.com/bhaptics/tact-js)
- [Hapticlabs Satellite 개요](https://docs.hapticlabs.io/satellite/overview/)
  — BLE 항목이 아직 “upcoming in Q2/2024”로 기재되어 있어 출시된 지원으로 해석하지 않음.
- [MDN Web Bluetooth](https://developer.mozilla.org/en-US/docs/Web/API/Web_Bluetooth_API)
- [MDN Bluetooth 호환성](https://developer.mozilla.org/en-US/docs/Web/API/Bluetooth#browser_compatibility)
