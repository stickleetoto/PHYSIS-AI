# PHYSIS AI 0.4.1 for Windows x64

## 한국어

1. 릴리스의 **PHYSIS-AI-0.4.1-win-x64.zip**과 **SHA256SUMS.txt**를 같은 폴더에 내려받습니다. PowerShell에서 아래 명령으로 계산한 SHA-256을 체크섬 파일의 ZIP 항목과 대조합니다. [v0.4.1 릴리스](https://github.com/stickleetoto/PHYSIS-AI/releases/tag/v0.4.1)
2. 현재 사용자가 쓸 수 있는 폴더에 **모두 압축 해제**합니다. ZIP 안에서 바로 실행하면 설정 파일을 찾을 수 없습니다.
3. 처음 한 번 **Setup-Runtime.cmd**를 실행합니다. 인터넷 연결이 필요합니다. CPython과 휠 23개의 다운로드 용량은 약 70.1 MiB입니다. 이 도구는 Python.org와 PyPI에서 받은 파일의 고정 SHA-256을 확인해 앱 폴더의 `runtime`에 준비합니다. 기존 시스템 Python·Node.js를 설치하거나 변경할 필요가 없습니다.
4. **Start-PHYSIS.cmd**를 실행합니다. 수학 실험실에서 미분·적분을 선택하거나 물리 실험실에서 초기 조건을 바꾸어 실험을 시작하세요. 설정 후 외부 연결을 막고 사용하려면 명령 프롬프트에서 `Start-PHYSIS.cmd --offline`을 실행합니다.
5. 종료할 때는 서버 콘솔에서 **Ctrl+C**를 누릅니다. 다음 사용 때에는 시작 프로그램만 다시 실행합니다.

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\PHYSIS-AI-0.4.1-win-x64.zip'
Get-Content -LiteralPath '.\SHA256SUMS.txt'
```

기본 주소는 `http://127.0.0.1:8765`입니다. 포트 충돌 시 `Start-PHYSIS.cmd --offline --port 8766`으로 다른 포트를 사용할 수 있습니다. 브라우저를 직접 열고 싶으면 `--no-browser`를 추가하세요. 데이터는 기본적으로 `%LOCALAPPDATA%\PHYSIS-AI`에 저장합니다. 브라우저에 저장한 학습 기록은 같은 브라우저 프로필과 주소에서 여세요. 포트를 바꾸면 브라우저 저장소의 주소도 바뀝니다.

## English

Download the Windows x64 ZIP and its external SHA-256 checksum from the release page. Verify the digest using the commands above, then extract the entire archive into a writable local directory. [Release downloads](https://github.com/stickleetoto/PHYSIS-AI/releases/tag/v0.4.1)

Run **Setup-Runtime.cmd** once while connected to the internet. The official CPython archive and 23 wheels total about 70.1 MiB. The manifest pins each download by version and SHA-256. The provisioned Python interpreter and its packages live under `runtime` inside the extracted folder. The UI is prebuilt. To launch, double-click **Start-PHYSIS.cmd**. To work offline after setup, run the following in Command Prompt from the extracted folder.

```bat
Start-PHYSIS.cmd --offline
```

The default tutor is Mock. The server listens on the IPv4 loopback interface. The launcher opens the default browser when the service is ready. To choose a different local port, add `--port 8766`. To open the address yourself, add `--no-browser`. Stop the console server with Ctrl+C before restarting it. Experiments and the local corpus database use `%LOCALAPPDATA%\PHYSIS-AI` by default. Browser learning records use the same browser profile and origin.

## Runtime and troubleshooting

| Symptom | Action |
|---|---|
| Setup has not been completed or an archive hash differs | Use the matching setup files from the same release. Check connectivity to python.org and files.pythonhosted.org and retry setup. |
| Windows reports a missing Visual C++ runtime | Use Microsoft’s supported **x64 v14** runtime instructions. The installed version must support the build tools used by the native component. Use Microsoft’s installer yourself if needed, then try the launcher again. [Microsoft download and version guidance](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist/) |
| The server reports a port conflict | Use the suggested alternative port. Existing third-party services can keep using their port. |
| The browser stays closed | Open the loopback URL printed by the launcher. Read the console error if the service did not start. |
| Corporate policy blocks PowerShell, networking or writes | Use a permitted local folder and your organization’s approved software process. |

The release ZIP distributes PHYSIS, static UI assets, the educational corpus, setup files and notices. Microsoft Visual C++ DLLs, Python and wheels are obtained from their upstream distributors during the user-initiated setup. A fresh machine without network access needs the runtime provisioned before offline use. Distribution provenance and measured Windows coverage are recorded in the source repository. [Distribution audit](https://github.com/stickleetoto/PHYSIS-AI/blob/v0.4.1/DISTRIBUTION_AUDIT.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)
