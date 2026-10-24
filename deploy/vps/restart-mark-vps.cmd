@echo off
REM Bấm đúp để khởi động lại Mark trên VPS (kiểm luôn là đã lên đúng một bản).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mark-vps.ps1" restart
pause
