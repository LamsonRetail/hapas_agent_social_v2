# Điều khiển Mark trên VPS từ PC — chỉ đăng nhập bằng KHOÁ SSH.
#   powershell -File mark-vps.ps1 restart      (status | restart | start | stop | logs | check)
# Đọc VPS_HOST / VPS_PORT / VPS_USER / SSH_KEY_PATH từ "D:\test vps\.env" (đổi bằng $env:VPS_ENV).
param([string]$Lenh = "status", [Parameter(ValueFromRemainingArguments = $true)] $Them)

$ErrorActionPreference = "Stop"
$envFile = if ($env:VPS_ENV) { $env:VPS_ENV } else { "D:\test vps\.env" }
if (-not (Test-Path $envFile)) { Write-Host "Không thấy $envFile"; exit 1 }

# Chỉ lấy đúng bốn khoá — không đọc mật khẩu.
$cfg = @{}
foreach ($l in Get-Content $envFile -Encoding UTF8) {
  if ($l -match '^(VPS_HOST|VPS_PORT|VPS_USER|SSH_KEY_PATH)=(.*)$') { $cfg[$Matches[1]] = $Matches[2].Trim('"', "'", ' ') }
}
$hostVps = $cfg["VPS_HOST"]; if (-not $hostVps) { Write-Host "Thiếu VPS_HOST trong $envFile"; exit 1 }
$port = if ($cfg["VPS_PORT"]) { $cfg["VPS_PORT"] } else { "22" }
$user = if ($cfg["VPS_USER"]) { $cfg["VPS_USER"] } else { "root" }
$key = if ($cfg["SSH_KEY_PATH"]) { $cfg["SSH_KEY_PATH"] } else { ".ssh\vps_test_key" }
if (-not [IO.Path]::IsPathRooted($key)) { $key = Join-Path (Split-Path $envFile) $key }

# ssh của Git Bash không bắt bẻ quyền file khoá như ssh.exe của Windows.
$ssh = "C:\Program Files\Git\usr\bin\ssh.exe"
if (-not (Test-Path $ssh)) { $ssh = (Get-Command ssh.exe -ErrorAction SilentlyContinue).Source }
if (-not $ssh) { Write-Host "Không tìm thấy ssh"; exit 1 }

$remote = "mark $Lenh $($Them -join ' ')".Trim()
& $ssh -t -i $key -p $port -o BatchMode=yes -o PasswordAuthentication=no `
  -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$user@$hostVps" $remote
exit $LASTEXITCODE
