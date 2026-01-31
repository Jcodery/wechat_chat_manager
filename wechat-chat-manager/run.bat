@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ========================================
echo   WeChat Chat Manager
echo ========================================
echo.
echo Starting server...
echo Open in browser: http://127.0.0.1:8000
echo.
echo Press Ctrl+C to stop
echo ========================================
echo.

REM Try venv in parent directory (project root)
if exist "..\.venv\Scripts\python.exe" (
    "..\.venv\Scripts\python.exe" -m uvicorn wechat_manager.api.main:app --host 127.0.0.1 --port 8000
    goto :end
)

REM Try venv in current directory
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m uvicorn wechat_manager.api.main:app --host 127.0.0.1 --port 8000
    goto :end
)

REM Fallback to system python
echo Warning: No virtual environment found, using system Python
python -m uvicorn wechat_manager.api.main:app --host 127.0.0.1 --port 8000

:end
pause
