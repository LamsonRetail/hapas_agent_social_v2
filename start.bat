@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM =====================================================================
REM  Launcher 1-nut cho Social Agent (double-click tu Explorer, hoac cmd)
REM  Chay bot Lark: listener (nhan event) + Hermes brain (tra loi as bot).
REM  Danh tinh la BOT (tenant token tu app_id/secret) - khong co OAuth as-user.
REM
REM  Venv duoc resolve theo thu tu:
REM    1) HERMES_AGENT_DIR trong .env  (nguon su that - brain.py cung doc bien nay)
REM    2) Cac vi tri cai Hermes pho bien
REM  Hermes nam cho khac thi chi can sua HERMES_AGENT_DIR trong .env.
REM
REM  File nay chi dung ky tu ASCII cho chac (batch + codepage rat de vo dau).
REM =====================================================================

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
REM Khong buffer stdout: chay nen / ghi ra file thi log moi hien ngay.
set "PYTHONUNBUFFERED=1"

REM --- .env phai co truoc ------------------------------------------------
if not exist "%~dp0.env" (
    echo [X] Chua co .env
    echo     Copy .env.example -^> .env roi dien LARK_APP_ID / LARK_APP_SECRET.
    pause
    exit /b 1
)

REM --- doc HERMES_AGENT_DIR tu .env --------------------------------------
set "AGENTDIR="
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
    if /i "%%~A"=="HERMES_AGENT_DIR" set "AGENTDIR=%%~B"
)

REM --- tim python.exe cua venv Hermes -----------------------------------
set "PY="
if defined AGENTDIR (
    if exist "!AGENTDIR!\venv\Scripts\python.exe"  set "PY=!AGENTDIR!\venv\Scripts\python.exe"
    if not defined PY if exist "!AGENTDIR!\.venv\Scripts\python.exe" set "PY=!AGENTDIR!\.venv\Scripts\python.exe"
)
if not defined PY if exist "%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"  set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\hermes\hermes-agent\.venv\Scripts\python.exe" set "PY=%LOCALAPPDATA%\hermes\hermes-agent\.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\Hermes Agent\hermes-home\hermes-agent\.venv\Scripts\python.exe" set "PY=%~dp0..\Hermes Agent\hermes-home\hermes-agent\.venv\Scripts\python.exe"

if not defined PY (
    echo [X] Khong tim thay venv cua Hermes. Da thu:
    if defined AGENTDIR echo     - !AGENTDIR!\venv\Scripts\python.exe
    if defined AGENTDIR echo     - !AGENTDIR!\.venv\Scripts\python.exe
    echo     - %LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
    echo     - %LOCALAPPDATA%\hermes\hermes-agent\.venv\Scripts\python.exe
    echo.
    echo     Sua HERMES_AGENT_DIR trong .env cho dung hermes-agent.
    pause
    exit /b 1
)

REM --- tu kiem tra ban va browser_tool ----------------------------------
REM `hermes update` ghi de tools/browser_tool.py -^> mat ban va -^> shim .cmd lai
REM nuot dau '&' trong URL -^> fb_ads_library bao "0 ad" cho MOI brand ma khong he
REM bao loi. Day la kieu hong nguy hiem nhat: bot van tra loi tron tru nhung SO
REM LIEU SAI. Nen phai kiem tra moi lan khoi dong.
if exist "%~dp0patch_browser_tool.py" (
    "%PY%" "%~dp0patch_browser_tool.py" --verify
    if errorlevel 1 (
        echo.
        echo ==============================================================
        echo  CANH BAO: BAN VA browser_tool DA MAT
        echo  ^(rat co the vua chay 'hermes update'^)
        echo.
        echo  Hau qua: URL co dau '&' bi cmd.exe cat cut.
        echo  fb_ads_library se bao "0 ad" cho MOI brand ma KHONG bao loi,
        echo  tuc bot van tra loi tron tru nhung SO LIEU SAI.
        echo.
        echo  Sua:  "%PY%" patch_browser_tool.py
        echo ==============================================================
        echo.
        choice /C YN /N /M "Van chay tiep? [Y/N] "
        if errorlevel 2 exit /b 1
    ) else (
        echo [OK] ban va browser_tool con nguyen ^(URL co '&' se di tron ven^)
    )
)

echo.
echo Chay bot Lark ^(listener + brain^)... Nhan Ctrl+C de dung.
echo.
"%PY%" "%~dp0run.py"
pause
