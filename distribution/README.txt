PHYSIS AI 0.4.1 | Windows x64
Copyright 2026 DevSeat

한국어

1. ZIP의 모든 파일을 쓰기 가능한 폴더에 압축 해제하세요.
2. 처음 한 번 Setup-Runtime.cmd를 실행하세요. 인터넷 연결이 필요합니다.
   앱 폴더 안에 공식 Python과 과학 계산 패키지를 준비합니다.
3. Start-PHYSIS.cmd를 실행하세요. 오프라인 전용으로 사용하려면
   명령 프롬프트에서 Start-PHYSIS.cmd --offline 을 실행하세요.
4. 브라우저가 열리면 수학 실험실 또는 물리 실험실을 선택하세요.
   종료하려면 서버 콘솔에서 Ctrl+C를 누르세요.

English

1. Extract the entire ZIP to a folder you can write to.
2. Run Setup-Runtime.cmd once with an internet connection. Setup retrieves
   the pinned Python runtime and scientific packages into this folder.
3. Run Start-PHYSIS.cmd. For offline-only use, run Start-PHYSIS.cmd --offline
   from a command prompt. The default tutor uses Mock.
4. Open the mathematics or physics laboratory in the browser. Press Ctrl+C
   in the server console to stop. The default address is http://127.0.0.1:8765.

For a port conflict, choose another loopback port with
Start-PHYSIS.cmd --offline --port 8766

If the launcher reports a missing Microsoft Visual C++ x64 runtime, follow
Microsoft's official instructions, then run the launcher again:
https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist/

See WINDOWS_DISTRIBUTION.md, LICENSE, NOTICE and THIRD_PARTY_NOTICES.md.
