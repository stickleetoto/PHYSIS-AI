@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-Runtime.ps1" %*
set "setup_exit_code=%errorlevel%"
if not "%setup_exit_code%"=="0" if not defined PHYSIS_NO_PAUSE if "%~1"=="" pause
exit /b %setup_exit_code%
