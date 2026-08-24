@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM ── Cap quyen lai cho seat Steven (double-click de chay OAuth thu cong) ──

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\hermes-home\hermes-agent\.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [X] Khong tim thay Python venv cua Hermes:
    echo     %PY%
    pause
    exit /b 1
)

echo Mo trinh duyet de dang nhap Steven va cap quyen as-user...
"%PY%" "%~dp0authorize.py"
pause
