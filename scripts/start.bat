@echo off
REM SlopTotal - One-command local server launcher
REM Usage: scripts\start.bat
REM
REM The server auto-detects your hardware (CPU cores, RAM, GPU)
REM and configures itself for optimal performance.
REM
REM Override any setting with environment variables:
REM   set SLOPTOTAL_PROFILE=lite ^& scripts\start.bat       Force lite mode (low RAM)
REM   set SLOPTOTAL_DEVICE=cpu ^& scripts\start.bat         Force CPU even if GPU available
REM   set SLOPTOTAL_TORCH_THREADS=4 ^& scripts\start.bat    Override thread count

setlocal
pushd "%~dp0.."

set "PORT=%SLOPTOTAL_PORT%"
if not defined PORT set "PORT=8000"
set "HOST=%SLOPTOTAL_HOST%"
if not defined HOST set "HOST=0.0.0.0"

echo.
echo   Starting SlopTotal...
echo   Models will be downloaded on first run (~9 GB, see docs/MODELS.md).
echo.

REM Detect if running inside venv; if not, try to activate one
if not defined VIRTUAL_ENV (
    if exist "venv\Scripts\activate.bat" (
        call "venv\Scripts\activate.bat"
    ) else if exist ".venv\Scripts\activate.bat" (
        call ".venv\Scripts\activate.bat"
    )
)

REM Check Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Install Python 3.10+ and try again.
    popd
    exit /b 1
)

REM Install dependencies if needed
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo   Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        popd
        exit /b 1
    )
)

python -m uvicorn app.main:app --host "%HOST%" --port "%PORT%"
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
