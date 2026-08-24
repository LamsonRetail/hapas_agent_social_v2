@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM ── Seed 1 kenh chat 1-1 de agent NHAN duoc tin nhan 1-1 ──
REM  Vi Lark khong cho user-token liet ke chat 1-1, ta phai "moi" truoc:
REM  gui 1 loi chao tu Steven -> nho chat_id -> tu gio nguoi do nhan 1-1 se duoc tra loi.

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\hermes-home\hermes-agent\.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [X] Khong tim thay Python venv cua Hermes:
    echo     %PY%
    pause
    exit /b 1
)

if not exist "%~dp0.tokens\steven.json" (
    echo [X] Chua co token Steven. Chay authorize.bat truoc da.
    pause
    exit /b 1
)

set "WHO=%*"
if "%WHO%"=="" (
    echo Nhap ten / email / open_id cua nguoi se nhan tin 1-1 voi Steven.
    set /p WHO=^>
)

echo.
echo Dang seed kenh 1-1 voi: %WHO%
echo.
"%PY%" "%~dp0seed_p2p.py" %WHO%
pause
