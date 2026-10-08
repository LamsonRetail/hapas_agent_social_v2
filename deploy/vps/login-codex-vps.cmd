@echo off
REM Bấm đúp: đăng nhập Codex RIÊNG cho Mark trên VPS (dự phòng khi tài khoản trên console hỏng).
REM Làm theo hướng dẫn hiện ra: mở link trên trình duyệt, đăng nhập ChatGPT, nhập mã.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mark-vps.ps1" login-codex
pause
