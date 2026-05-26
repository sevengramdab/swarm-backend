@echo off
setlocal

set "PROJECT_ROOT=D:\vs code project files\outputs\simplepod_swarm"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "SIMPLEPOD_NODE_ID=shadow_pc"

cd /d "%PROJECT_ROOT%"

echo ===========================================
echo   SimplePod Shadow PC (RTX 3080)
echo ===========================================
echo.
echo Setting NODE_IDENTITY=shadow_pc
echo.

"%PYTHON%" -m uvicorn interfaces.web_ui.backend.main:app --host 0.0.0.0 --port 8000
