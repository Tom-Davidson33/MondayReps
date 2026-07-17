@echo off
setlocal
REM ============================================================
REM  Tom's Monday Report - FULL SEQUENCE
REM    1) GPG_NM    - NM gas burn model  (Pelican forecast)
REM    2) Godfather - DWGM forecast
REM    3) Report    - render + Outlook draft  (run_report.py)
REM
REM  Usage:  run_all.bat              full run, drafts the email
REM          run_all.bat --no-send    models + render only, no Outlook
REM
REM  Note: run_report.py's freshness gate would trigger the models
REM  itself if they were stale; running them here first just means
REM  the gate finds them fresh and moves straight to the render.
REM ============================================================

set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%.venv"

REM --- model repo locations: edit these if the repos move ---
set "GPG_NM_DIR=C:\Users\MS6653\OneDrive - ENGIE\Desktop\Operation Arb\3. GPG_NM"
set "GODFATHER_DIR=C:\Users\MS6653\OneDrive - ENGIE\Desktop\Operation Arb\4. Godfather"
set "GPG_NM_ENTRY=main.py"
set "GODFATHER_ENTRY=main.py"

cd /d "%PROJECT_DIR%" || goto :fail_cd

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set "STAMP=%%i"
set "LOGDIR=%PROJECT_DIR%logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\run_all_%STAMP%.log"
echo Logging to %LOG%
echo [%time%] ===== FULL SEQUENCE START ===== > "%LOG%"

if not exist "%PROJECT_DIR%.env" goto :fail_env

REM --- report venv: create + install deps on first run ---
if exist "%VENV_DIR%\Scripts\python.exe" goto :venv_ok
echo [1st run] Creating venv and installing dependencies...
python -m venv "%VENV_DIR%" >> "%LOG%" 2>&1 || goto :fail_venv
"%VENV_DIR%\Scripts\python.exe" -m pip install -q -r "%PROJECT_DIR%requirements.txt" >> "%LOG%" 2>&1 || goto :fail_venv
:venv_ok
set "REPORT_PY=%VENV_DIR%\Scripts\python.exe"

REM ---------- STEP 1: GPG_NM ----------
echo [1/3] GPG_NM model...
call :run_model "GPG_NM" "%GPG_NM_DIR%" "%GPG_NM_ENTRY%" || goto :fail

REM ---------- STEP 2: Godfather (DWGM forecast) ----------
echo [2/3] DWGM forecast...
call :run_model "Godfather" "%GODFATHER_DIR%" "%GODFATHER_ENTRY%" || goto :fail

REM ---------- STEP 3: Report ----------
echo [3/3] Report...
echo [%time%] [report] run_report.py %* >> "%LOG%"
"%REPORT_PY%" "%PROJECT_DIR%run_report.py" %* >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :fail_report

echo [%time%] ===== FULL SEQUENCE OK ===== >> "%LOG%"
echo [OK] Full sequence complete. Log: %LOG%
call :maybe_pause
endlocal
exit /b 0

REM ---------------- subroutines ----------------
:run_model
REM %1 name  %2 repo dir  %3 entry script
set "MNAME=%~1"
set "MDIR=%~2"
set "MENTRY=%~3"
if not exist "%MDIR%\%MENTRY%" (
    echo [ERROR] %MNAME%: script not found: "%MDIR%\%MENTRY%" - fix the *_DIR / *_ENTRY vars at the top.
    exit /b 1
)
REM prefer the model repo's own venv if it has one, else the report venv
set "MPY=%REPORT_PY%"
if exist "%MDIR%\.venv\Scripts\python.exe" set "MPY=%MDIR%\.venv\Scripts\python.exe"
echo [%time%] [%MNAME%] "%MPY%" %MENTRY% >> "%LOG%"
pushd "%MDIR%"
"%MPY%" "%MENTRY%" >> "%LOG%" 2>&1
set "MRC=%ERRORLEVEL%"
popd
if not "%MRC%"=="0" (
    echo [ERROR] %MNAME% failed with exit code %MRC%. See %LOG%
    exit /b 1
)
echo [%time%] [%MNAME%] OK >> "%LOG%"
exit /b 0

:maybe_pause
REM keep the window open when double-clicked from Explorer
echo %cmdcmdline% | find /i "%~f0" >nul && pause
exit /b 0

REM ---------------- failure exits ----------------
:fail_cd
echo [ERROR] Cannot cd to project dir
goto :fail
:fail_env
echo [ERROR] .env not found at %PROJECT_DIR%.env
goto :fail
:fail_venv
echo [ERROR] venv creation / pip install failed. See %LOG%
goto :fail
:fail_report
echo [ERROR] Report failed with exit code %RC%. See %LOG%
goto :fail
:fail
echo [%time%] ===== FAILED ===== >> "%LOG%" 2>nul
call :maybe_pause
endlocal
exit /b 1
