# Launcher cho Social Agent - dung venv cua Hermes (da co requests) va bat UTF-8.
#   .\start.ps1            # chay bot (listener + brain)
#
# Venv duoc resolve theo thu tu:
#   1) HERMES_AGENT_DIR trong .env  (nguon su that - brain.py cung doc bien nay)
#   2) Cac vi tri cai Hermes pho bien
# Neu Hermes nam cho khac, chi can sua HERMES_AGENT_DIR trong .env.
#
# LUU Y: file nay chi dung ky tu ASCII. PowerShell 5.1 doc .ps1 theo ANSI, ky tu
# UTF-8 co dau se vo thanh mojibake va lam hong cu phap (loi "missing terminator").

#   .\start.ps1 -StrictPatch   # dung han neu ban va browser_tool da mat

param([switch]$StrictPatch)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-DotEnvValue([string]$Key) {
    $envFile = Join-Path $Here ".env"
    if (-not (Test-Path $envFile)) { return $null }
    foreach ($line in Get-Content $envFile) {
        $t = $line.Trim()
        if ($t.StartsWith("#") -or -not $t.Contains("=")) { continue }
        $parts = $t.Split("=", 2)
        if ($parts[0].Trim() -eq $Key) { return $parts[1].Trim().Trim('"').Trim("'") }
    }
    return $null
}

$Candidates = @()
$AgentDir = Get-DotEnvValue "HERMES_AGENT_DIR"
if ($AgentDir) {
    $Candidates += (Join-Path $AgentDir "venv\Scripts\python.exe")
    $Candidates += (Join-Path $AgentDir ".venv\Scripts\python.exe")
}
$Candidates += (Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\python.exe")
$Candidates += (Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\.venv\Scripts\python.exe")
$Candidates += (Join-Path $Here "..\Hermes Agent\hermes-home\hermes-agent\.venv\Scripts\python.exe")

$Py = $null
foreach ($c in $Candidates) {
    if ($c -and (Test-Path $c)) { $Py = $c; break }
}

if (-not $Py) {
    Write-Host "Khong tim thay venv cua Hermes. Da thu:" -ForegroundColor Red
    foreach ($c in $Candidates) { Write-Host "   - $c" -ForegroundColor DarkGray }
    Write-Host "   Sua HERMES_AGENT_DIR trong .env cho dung hermes-agent." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $Here ".env"))) {
    Write-Host "Chua co .env - copy .env.example -> .env roi dien LARK_APP_ID/LARK_APP_SECRET." -ForegroundColor Red
    exit 1
}

# --- Tu kiem tra ban va browser_tool -----------------------------------------
# `hermes update` ghi de tools/browser_tool.py -> mat ban va -> shim .cmd lai
# nuot dau '&' trong URL -> fb_ads_library bao "0 ad" cho MOI brand ma khong he
# bao loi. Day la kieu hong nguy hiem nhat: agent van tra loi tron tru nhung so
# lieu sai. Nen kiem tra moi lan khoi dong.
$PatchScript = Join-Path $Here "patch_browser_tool.py"
if (Test-Path $PatchScript) {
    & $Py $PatchScript --verify
    $PatchState = $LASTEXITCODE
    if ($PatchState -eq 0) {
        Write-Host "[ OK ] ban va browser_tool con nguyen (URL co '&' se di tron ven)" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "==============================================================" -ForegroundColor Red
        if ($PatchState -eq 2) {
            Write-Host " KHONG THAY tools/browser_tool.py cua Hermes" -ForegroundColor Red
        } else {
            Write-Host " CANH BAO: BAN VA browser_tool DA MAT" -ForegroundColor Red
            Write-Host " (rat co the vua chay 'hermes update')" -ForegroundColor Red
        }
        Write-Host ""
        Write-Host " Hau qua: URL co dau '&' bi cmd.exe cat cut." -ForegroundColor Yellow
        Write-Host " fb_ads_library se bao '0 ad' cho MOI brand ma KHONG bao loi," -ForegroundColor Yellow
        Write-Host " tuc bot van tra loi tron tru nhung SO LIEU SAI." -ForegroundColor Yellow
        Write-Host ""
        Write-Host " Sua:  python patch_browser_tool.py" -ForegroundColor Cyan
        Write-Host "==============================================================" -ForegroundColor Red
        Write-Host ""
        if ($StrictPatch) {
            Write-Host "Dung lai vi -StrictPatch. Va xong roi chay lai." -ForegroundColor Red
            exit 1
        }
    }
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
# Khong buffer stdout: khi chay nen (ghi ra file/pipe) Python block-buffer khien
# banner va log khong hien ra cho toi khi day buffer - rat kho theo doi.
$env:PYTHONUNBUFFERED = "1"

Write-Host "> $Py run.py" -ForegroundColor Cyan
& $Py (Join-Path $Here "run.py")
