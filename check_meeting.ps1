# Kiem tra suc khoe MEETING AGENT (hermes gateway) - chay truoc/sau khi bat Mark.
#   .\check_meeting.ps1
#
# Meeting agent dung CHUNG hermes-home voi social agent, nen moi lan dong vao
# social phai xac nhan meeting con nguyen. Script chi DOC, khong ghi gi.
# Luu y: file nay chi dung ky tu ASCII (PowerShell 5.1 doc .ps1 theo ANSI).

$ErrorActionPreference = "Continue"
$H = Join-Path $env:LOCALAPPDATA "hermes"
$Today = Get-Date -Format "yyyy-MM-dd"
$Fail = 0

Write-Host ""
Write-Host "=== MEETING AGENT HEALTH CHECK ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) ===" -ForegroundColor Cyan

# 1) Gateway process con song khong
$statePath = Join-Path $H "gateway_state.json"
if (-not (Test-Path $statePath)) {
    Write-Host "[FAIL] Khong thay gateway_state.json" -ForegroundColor Red
    $Fail = $Fail + 1
} else {
    $st = Get-Content $statePath -Raw | ConvertFrom-Json
    $proc = Get-Process -Id $st.pid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "[ OK ] Gateway PID $($st.pid) dang chay (state=$($st.gateway_state), active_agents=$($st.active_agents))" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Gateway PID $($st.pid) KHONG con chay" -ForegroundColor Red
        $Fail = $Fail + 1
    }
    # 2) Trang thai tung platform
    foreach ($p in $st.platforms.PSObject.Properties) {
        $s = $p.Value.state
        if ($s -eq "connected") {
            Write-Host "[ OK ] platform '$($p.Name)' = $s" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] platform '$($p.Name)' = $s ($($p.Value.error_message))" -ForegroundColor Red
            $Fail = $Fail + 1
        }
    }
}

# 3) Loi auth/quota trong NGAY HOM NAY
$errLog = Join-Path $H "logs\errors.log"
if (Test-Path $errLog) {
    $todayLines = @(Select-String -Path $errLog -Pattern "^$Today" -ErrorAction SilentlyContinue)
    Write-Host "[info] Tong dong loi hom nay: $($todayLines.Count)"
    # Dau hieu NGHIEM TRONG: token bi xoay mat, het quota, mat quyen
    foreach ($pat in @("invalid_grant", "refresh_token_reused", "relogin_required", "quota")) {
        $hits = @($todayLines | Where-Object { $_.Line -imatch $pat })
        if ($hits.Count -gt 0) {
            Write-Host "[FAIL] '$pat' xuat hien $($hits.Count) lan hom nay - token/quota co van de" -ForegroundColor Red
            $hits | Select-Object -Last 2 | ForEach-Object {
                $t = $_.Line
                if ($t.Length -gt 150) { $t = $t.Substring(0, 150) }
                Write-Host "        $t" -ForegroundColor DarkGray
            }
            $Fail = $Fail + 1
        } else {
            Write-Host "[ OK ] khong co '$pat' hom nay" -ForegroundColor Green
        }
    }
    # 429/401 chi la canh bao (co the do nguyen nhan khac)
    foreach ($pat in @("429", "401")) {
        $n = @($todayLines | Where-Object { $_.Line -imatch $pat }).Count
        Write-Host "[info] '$pat' hom nay: $n (theo doi xu huong; tang dot bien = dang tranh quota)"
    }
} else {
    Write-Host "[warn] Khong thay logs\errors.log" -ForegroundColor Yellow
}

# 4) auth.json - moc thoi gian de phat hien token bi xoay
$authPath = Join-Path $H "auth.json"
if (Test-Path $authPath) {
    Write-Host "[info] auth.json sua lan cuoi: $((Get-Item $authPath).LastWriteTime)"
}

# 5) Agent con phuc vu request khong
$agentLog = Join-Path $H "logs\agent.log"
if (Test-Path $agentLog) {
    $last = Get-Content $agentLog -Tail 1
    if ($last -and $last.Length -gt 120) { $last = $last.Substring(0, 120) }
    Write-Host "[info] agent.log dong cuoi: $last"
}

Write-Host ""
if ($Fail -eq 0) {
    Write-Host ">>> MEETING AGENT: BINH THUONG" -ForegroundColor Green
    exit 0
} else {
    Write-Host ">>> MEETING AGENT: CO $Fail VAN DE - DUNG MARK LAI VA XU LY TRUOC" -ForegroundColor Red
    exit 1
}
