@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM ── Launcher 1-nut cho Social Agent (double-click tu Explorer hoac chay trong cmd) ──
REM  Chay con bot Lark: listener (nhan event) + Hermes brain (tra loi as bot).
REM  Khong con buoc OAuth as-user; danh tinh la BOT (tenant token tu app_id/secret).

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\Hermes Agent\hermes-home\hermes-agent\.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [X] Khong tim thay Python venv cua Hermes:
    echo     %PY%
    echo     Sua duong dan trong start.bat neu hermes-home o noi khac.
    pause
    exit /b 1
)

echo.
echo Chay bot Lark ^(listener + brain^)... Nhan Ctrl+C de dung.
echo.
"%PY%" "%~dp0run.py"
pause
