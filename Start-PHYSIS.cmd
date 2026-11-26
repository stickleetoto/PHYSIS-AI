@echo off
setlocal
pushd "%~dp0"
set "LAB_PY=python"
if exist ".venv\Scripts\python.exe" set "LAB_PY=.venv\Scripts\python.exe"
if exist "runtime\python.exe" set "LAB_PY=runtime\python.exe"
"%LAB_PY%" scripts\serve.py %*
set "LAB_EXIT=%ERRORLEVEL%"
if not "%LAB_EXIT%"=="0" if "%~1"=="" pause
popd
exit /b %LAB_EXIT%
