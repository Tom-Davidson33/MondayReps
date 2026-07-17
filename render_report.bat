@echo off
setlocal
REM ============================================================
REM  Tom's Monday Report - RENDER ONLY (no Outlook draft/send)
REM  Runs run_report.py --no-send in the project venv, then you
REM  open out\tom_monday_report.html to preview.
REM  Does NOT run the models first - use run_all.bat for that.
REM ============================================================

set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%.venv"

cd /d "%PROJECT_DIR%" || goto :fail_cd

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set "STAMP=%%i"
set "LOGDIR=%PROJECT_DIR%logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\render_%STAMP%.log"
echo Logging to %LOG%

if not exist "%PROJECT_DIR%.env" goto :fail_env
if not exist "%VENV_DIR%\Scripts\python.exe" goto :fail_venv

echo [%time%] render-only: run_report.py --no-send > "%LOG%"
"%VENV_DIR%\Scripts\python.exe" "%PROJECT_DIR%run_report.py" --no-send >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :fail_run

echo [OK] Report rendered to out\tom_monday_report.html - no email created. Log: %LOG%
call :maybe_pause
endlocal
exit /b 0

:maybe_pause
REM keep the window open when double-clicked from Explorer
echo %cmdcmdline% | find /i "%~f0" >nul && pause
exit /b 0

:fail_cd
echo [ERROR] Cannot cd to project dir
goto :fail
:fail_env
echo [ERROR] .env not found at %PROJECT_DIR%.env
goto :fail
:fail_venv
echo [ERROR] venv not found at %VENV_DIR% - run run_all.bat once first to create it.
goto :fail
:fail_run
echo [ERROR] Render failed with exit code %RC%. See %LOG%
goto :fail
:fail
call :maybe_pause
endlocal
exit /b 1
