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

REM --- model repo locations / commands ---
REM Prefer matching keys in the shell, then .env, then defaults:
REM   GPG_NM_REPO_DIR=...
REM   GODFATHER_REPO_DIR=...
REM   GPG_NM_COMMAND=python main.py
REM   GODFATHER_COMMAND=python main.py

cd /d "%PROJECT_DIR%" || goto :fail_cd

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set "STAMP=%%i"
set "LOGDIR=%PROJECT_DIR%logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\run_all_%STAMP%.log"
echo Logging to %LOG%
echo [%time%] ===== FULL SEQUENCE START ===== > "%LOG%"

if not exist "%PROJECT_DIR%.env" goto :fail_env
call :load_env_value GPG_NM_REPO_DIR
call :load_env_value GODFATHER_REPO_DIR
call :load_env_value GPG_NM_COMMAND
call :load_env_value GODFATHER_COMMAND
if not defined GPG_NM_REPO_DIR set "GPG_NM_REPO_DIR=C:\Users\MS6653\OneDrive - ENGIE\Desktop\Operation Arb\3. GPG_NM"
if not defined GODFATHER_REPO_DIR set "GODFATHER_REPO_DIR=C:\Users\MS6653\OneDrive - ENGIE\Desktop\Operation Arb\4. Godfather"
if not defined GPG_NM_COMMAND set "GPG_NM_COMMAND=python main.py"
if not defined GODFATHER_COMMAND set "GODFATHER_COMMAND=python main.py"

REM --- report venv: create + install deps on first run ---
if exist "%VENV_DIR%\Scripts\python.exe" goto :venv_ok
echo [1st run] Creating venv and installing dependencies...
python -m venv "%VENV_DIR%" >> "%LOG%" 2>&1 || goto :fail_venv
"%VENV_DIR%\Scripts\python.exe" -m pip install -q -r "%PROJECT_DIR%requirements.txt" >> "%LOG%" 2>&1 || goto :fail_venv
:venv_ok
set "REPORT_PY=%VENV_DIR%\Scripts\python.exe"

REM ---------- STEP 1: GPG_NM ----------
echo [1/3] GPG_NM model...
call :run_model "GPG_NM" "%GPG_NM_REPO_DIR%" "%GPG_NM_COMMAND%" || goto :fail

REM ---------- STEP 2: Godfather (DWGM forecast) ----------
echo [2/3] DWGM forecast...
call :run_model "Godfather" "%GODFATHER_REPO_DIR%" "%GODFATHER_COMMAND%" || goto :fail

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
REM %1 name  %2 repo dir  %3 command
set "MNAME=%~1"
set "MDIR=%~2"
set "MCMD=%~3"
if not exist "%MDIR%\" (
    echo [ERROR] %MNAME%: repo directory not found: "%MDIR%" - set %MNAME% repo dir in .env or at the top of run_all.bat.
    exit /b 1
)
if /i "%MCMD%"=="python main.py" if not exist "%MDIR%\main.py" call :detect_model_command "%MDIR%" MCMD || exit /b 1
REM prefer the model repo's own venv if it has one, else the report venv
set "MPY=%REPORT_PY%"
if exist "%MDIR%\.venv\Scripts\python.exe" set "MPY=%MDIR%\.venv\Scripts\python.exe"
echo [%time%] [%MNAME%] %MCMD% >> "%LOG%"
pushd "%MDIR%"
set "VIRTUAL_ENV="
for %%P in ("%MPY%") do (
    set "PATH=%%~dpP;%PATH%"
    set "VIRTUAL_ENV=%%~dpP.."
)
%MCMD% >> "%LOG%" 2>&1
set "MRC=%ERRORLEVEL%"
popd
if not "%MRC%"=="0" (
    echo [ERROR] %MNAME% failed with exit code %MRC%. See %LOG%
    exit /b 1
)
echo [%time%] [%MNAME%] OK >> "%LOG%"
exit /b 0

:detect_model_command
REM %1 repo dir, %2 variable name to receive command. Used when the default
REM "python main.py" is wrong for a model repo.
set "DDIR=%~1"
set "DVAR=%~2"
for %%F in (run.py forecast.py dwgm_forecast.py run_forecast.py godfather.py) do (
    if exist "%DDIR%\%%F" (
        set "%DVAR%=python %%F"
        exit /b 0
    )
)
echo [ERROR] No main.py found in "%DDIR%". Set GPG_NM_COMMAND or GODFATHER_COMMAND in .env to the actual model command.
exit /b 1

:load_env_value
REM Read simple KEY=value lines from .env without echoing secrets. Existing shell
REM values take precedence over .env values.
set "ENV_KEY=%~1"
for /f "usebackq tokens=1,* delims==" %%A in ("%PROJECT_DIR%.env") do (
    if /i "%%A"=="%ENV_KEY%" if not defined %ENV_KEY% set "%ENV_KEY%=%%~B"
)
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
