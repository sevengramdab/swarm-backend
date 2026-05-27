@echo off
setlocal EnableDelayedExpansion

echo ===========================================
echo   SimplePod Shadow PC Deploy
echo ===========================================
echo.

:: Config — edit these if your setup differs
set "SHADOW_PC_IP=100.64.0.2"
set "REPO_URL=https://github.com/sevengramdab/swarm-backend.git"
set "INSTALL_DIR=%USERPROFILE%\simplepod-shadow"

:: Check Python
call python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.12+ from https://python.org
    pause
    exit /b 1
)

:: Clone or update repo
if exist "%INSTALL_DIR%\.git" (
    echo [1/4] Updating existing repo...
    cd /d "%INSTALL_DIR%"
    git pull
) else (
    echo [1/4] Cloning repo to %INSTALL_DIR%...
    git clone "%REPO_URL%" "%INSTALL_DIR%"
    cd /d "%INSTALL_DIR%"
)

:: Create venv
echo [2/4] Setting up Python environment...
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

:: Install deps
echo [3/4] Installing dependencies...
python -m pip install --upgrade pip
if exist requirements.txt (
    pip install -r requirements.txt
) else (
    pip install fastapi uvicorn pydantic pyyaml pyautogui pillow requests
)

:: Start shadow node
echo [4/4] Starting Shadow Node...
echo.
echo   Node ID:   shadow_pc
echo   IP:        %SHADOW_PC_IP%
echo   Port:      8000
echo.
echo   Your main PC should now see this node at:
echo   http://%SHADOW_PC_IP%:8000/health
echo.
echo   Press Ctrl+C to stop.
echo ===========================================

python shadow_node.py
