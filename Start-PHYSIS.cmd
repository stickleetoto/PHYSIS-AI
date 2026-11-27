@echo off
setlocal EnableExtensions
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
    echo PHYSIS AI could not open its application folder.
    exit /b 2
)

set "LAB_PORTABLE=0"
set "LAB_PY="
set "LAB_PY_ARGS="

rem The root lock file marks an extracted distribution. Portable mode never
rem falls back to a Python installed elsewhere on the computer.
if exist "runtime-lock.json" (
    set "LAB_PORTABLE=1"
    if not exist "Setup-Runtime.cmd" goto package_incomplete
    if not exist "runtime\python.exe" goto portable_runtime_missing
    if not exist "runtime\vcruntime140.dll" if not exist "%SystemRoot%\System32\vcruntime140.dll" goto portable_vc_runtime_missing
    if not exist "runtime\vcruntime140_1.dll" if not exist "%SystemRoot%\System32\vcruntime140_1.dll" goto portable_vc_runtime_missing
    set "LAB_PY=runtime\python.exe"
) else (
    if exist "Setup-Runtime.cmd" goto package_incomplete
    if exist "Setup-Runtime.ps1" goto package_incomplete
    if exist ".venv\Scripts\python.exe" set "LAB_PY=.venv\Scripts\python.exe"
    if not defined LAB_PY if exist "runtime\python.exe" set "LAB_PY=runtime\python.exe"
    if not defined LAB_PY (
        where.exe python.exe >nul 2>&1
        if not errorlevel 1 set "LAB_PY=python.exe"
    )
    if not defined LAB_PY (
        where.exe py.exe >nul 2>&1
        if not errorlevel 1 (
            set "LAB_PY=py.exe"
            set "LAB_PY_ARGS=-3.13"
        )
    )
    if not defined LAB_PY goto source_runtime_missing
)

if "%LAB_PORTABLE%"=="1" call :probe_portable_interpreter
if errorlevel 1 if "%LAB_PORTABLE%"=="1" goto portable_interpreter_failed

if not defined PHYSIS_AI_PROVIDER set "PHYSIS_AI_PROVIDER=mock"
if not defined PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT set "PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT=0"

"%LAB_PY%" %LAB_PY_ARGS% scripts\serve.py %*
set "LAB_EXIT=%ERRORLEVEL%"
if not "%LAB_EXIT%"=="0" if not defined PHYSIS_NO_PAUSE if "%~1"=="" pause
popd
exit /b %LAB_EXIT%

:portable_runtime_missing
echo PHYSIS AI's portable Python runtime is not prepared.
echo Run Setup-Runtime.cmd once from this folder, then run Start-PHYSIS.cmd again.
echo Setup is an explicit user action. This launcher does not install software or request administrator access.
set "LAB_EXIT=2"
goto failed

:package_incomplete
echo This PHYSIS AI distribution is missing a required Setup-Runtime entry or runtime-lock.json.
echo Download or extract the complete distribution ZIP again.
set "LAB_EXIT=2"
goto failed

:portable_vc_runtime_missing
echo The package's x64 Visual C++ runtime files are missing.
echo Required Microsoft Visual C++ v14 runtime: minimum 14.51.36247.0, x64.
echo Official download: https://aka.ms/vc14/vc_redist.x64.exe
echo Official details: https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
echo No installer was started. Install it manually, then run Start-PHYSIS.cmd again.
set "LAB_EXIT=2"
goto failed

:portable_interpreter_failed
echo The embedded x64 Python interpreter could not start (Windows status %LAB_INTERPRETER_EXIT%).
echo If Windows reports a missing or incompatible VC runtime, the required minimum is 14.51.36247.0.
echo Official Microsoft x64 download: https://aka.ms/vc14/vc_redist.x64.exe
echo PHYSIS AI does not install software or request administrator access.
set "LAB_EXIT=2"
goto failed

:source_runtime_missing
echo Python 3.13 was not found for source mode.
echo Run Setup-Windows.cmd from this folder, then run Start-PHYSIS.cmd again.
set "LAB_EXIT=2"
goto failed

:probe_portable_interpreter
"%LAB_PY%" -I -c "import sys; print(sys.version.split()[0])" >nul 2>&1
set "LAB_INTERPRETER_EXIT=%ERRORLEVEL%"
exit /b %LAB_INTERPRETER_EXIT%

:failed
if not defined PHYSIS_NO_PAUSE if "%~1"=="" pause
popd
exit /b %LAB_EXIT%
