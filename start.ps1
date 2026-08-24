# Launcher cho Social Agent — dùng venv của Hermes (đã có requests) và bật UTF-8.
#   .\start.ps1            # chạy bot (listener + brain)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
# venv Hermes thật nằm ở "D:\Project\Hermes Agent\hermes-home" — có thể override
# bằng HERMES_AGENT_DIR trong .env (ở đây chỉ cần để chạy Python có sẵn requests).
$Py = Join-Path $Here "..\Hermes Agent\hermes-home\hermes-agent\.venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "❌ Khong tim thay venv Hermes: $Py" -ForegroundColor Red
    Write-Host "   Sua duong dan trong start.ps1 neu hermes-home o noi khac." -ForegroundColor Yellow
    exit 1
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "▶ $Py run.py" -ForegroundColor Cyan
& $Py (Join-Path $Here "run.py")
