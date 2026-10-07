# 개발

Windows 어댑터는 Python 3.10, Docker 중계와 TUI는 Python 3.12로 실행합니다.

```powershell
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```

Linux에서도 중계·TUI·알림 상태 로직 테스트를 실행할 수 있습니다. Windows 전용 테스트는 해당 환경에서만 실행됩니다. `test_clipboard.py`는 실제 로컬 클립보드를 잠깐 바꾸고 복원하므로 데스크톱에서 실행합니다. CI에서는 이 테스트를 제외합니다.

## 코드

- `bridge/broker.py`: 요청 대기열, 에이전트 lease, 결과 중복 방지
- `bridge/agent.py`: 호스트 폴링과 GUI 작업 시간 제한
- `bridge/windows.py`: 카카오톡 창·입력 컨트롤 확인과 조작
- `bridge/clipboard_backup.py`: 클립보드 형식 백업·복원
- `bridge/notifications.py`, `bridge/chatlist.py`: 알림·배지 감지
- `bridge/styled_tui.py`, `bridge/themes.py`: 터미널 화면과 테마

실제 카카오톡 시험은 테스트용 방에서 직접 실행합니다. pytest는 실제 카카오톡에 메시지를 보내지 않습니다. 모의 에이전트는 실행 중인 에이전트를 멈춘 다음 `scripts/start-agent.ps1 -Mock`으로 시작합니다. 시험이 끝나면 실제 에이전트를 다시 시작합니다.

송신 실패를 자동 재시도로 처리하지 마세요. 대상 창과 초안 검증을 유지하고, 새 이벤트를 추가할 때는 느린 GUI 작업 중 조회가 중첩되지 않는지 확인합니다.

## 릴리스

`main`에 코드를 올리면 CI가 Windows/Linux 테스트와 Docker 빌드를 실행합니다. `v0.1.0` 형태의 태그를 올리면 테스트 성공 후 ZIP과 SHA-256 파일을 첨부한 draft Release를 만듭니다. GitHub Releases에서 내용을 확인하고 공개합니다.

```powershell
python scripts/package-release.py --version v0.1.0
```

패키징은 명시된 소스·문서만 포함합니다. 가상 환경·접속 키·토큰·로그·작업 기록은 포함하지 않습니다. 워크플로 실행 상태는 GitHub Actions에서 확인합니다.
