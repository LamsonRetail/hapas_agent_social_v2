@echo off
REM Bấm đúp để xem Mark trên VPS đang chạy không + vài dòng log cuối.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mark-vps.ps1" status
pause
