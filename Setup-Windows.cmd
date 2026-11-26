@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.13 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
pushd frontend
call npm.cmd ci --no-audit --no-fund
if errorlevel 1 goto frontend_failed
call npm.cmd run build
if errorlevel 1 goto frontend_failed
popd
echo Ready. Run Start-PHYSIS.cmd.
popd
exit /b 0
:frontend_failed
popd
:failed
echo Setup failed. See the error above.
popd
pause
exit /b 1
