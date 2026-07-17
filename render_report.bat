@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  Tom's Monday Report - RENDER ONLY (no Outlook draft/send)
REM ============================================================

REM --- adjust these to your project ---
set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%.venv"
set "ENTRY=report.main"
set "RENDER_FLAG=--no-draft"
set "ENV_FILE=%PROJECT_DIR%.env"
REM ------------------------------------

cd /d "%PROJECT_DIR%" || (echo [ERROR] Cannot cd to project dir & exit /b 1)

for /f "tokens=1-4 delims=/:. " %%a in ("%date% %time%") do set "STAMP=%%d%%c%%b_%%a"
set "LOGDIR=%PROJECT_DIR%logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\render_%STAMP%.log"

echo [%time%] Starting RENDER-ONLY run > "%LOG%"
echo Logging to %LOG%

if not exist "%ENV_FILE%" (
    echo [ERROR] .env not found at %ENV_FILE%
    exit /b 1
)

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [ERROR] venv not found at %VENV_DIR%. Run the full runner once first.
    exit /b 1
)
call "%VENV_DIR%\Scripts\activate.bat"

echo [%time%] Running %ENTRY% %RENDER_FLAG% ... >> "%LOG%"
python -m %ENTRY% %RENDER_FLAG% >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo [%time%] Render FAILED (exit %RC%) >> "%LOG%"
    echo [ERROR] Render failed with exit code %RC%. See %LOG%
    endlocal & exit /b 1
)

echo [%time%] Render completed OK. HTML written, no email created. >> "%LOG%"
echo [OK] Report rendered (no draft/send). Log: %LOG%
endlocal
exit /b 0
