# Chạy bộ nghiệm thu SOW (Promptfoo) trên máy dev. Xem evals/sow/README.md.
#   powershell -File evals\sow\chay.ps1                # cả bộ
#   powershell -File evals\sow\chay.ps1 -Loc "SOW 6 "  # lọc theo description
#   powershell -File evals\sow\chay.ps1 -Lap 3         # hỏi mỗi ca 3 lần → pass^3 (độ ổn định)
param([string]$Loc = "", [int]$Lap = 1)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# Không gửi telemetry, không chia sẻ cloud, không tự kiểm tra cập nhật.
$env:PROMPTFOO_DISABLE_TELEMETRY = "1"
$env:PROMPTFOO_DISABLE_SHARING = "1"
$env:PROMPTFOO_DISABLE_UPDATE = "1"
$env:PYTHONIOENCODING = "utf-8"
if (-not $env:PROMPTFOO_PYTHON) { $env:PROMPTFOO_PYTHON = "python" }

$out = Join-Path $here "ket-qua"
New-Item -ItemType Directory -Force $out | Out-Null
$file = Join-Path $out ("ket-qua-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")

$args_ = @("-y", "promptfoo@0.124.0", "eval", "-c", (Join-Path $here "promptfooconfig.yaml"),
           "--no-cache", "-o", $file)
if ($Loc) { $args_ += @("--filter-pattern", $Loc) }
if ($Lap -gt 1) { $args_ += @("--repeat", "$Lap") }
& npx @args_
if (Test-Path $file) { & $env:PROMPTFOO_PYTHON (Join-Path $here "tong_hop.py") $file }
Write-Host "Kết quả: $file  ·  xem: npx promptfoo@0.124.0 view"
