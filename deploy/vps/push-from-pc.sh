#!/usr/bin/env bash
# Đẩy Mark từ PC lên VPS. Chạy trên PC bằng Git Bash. Chỉ đăng nhập bằng KHOÁ SSH.
#
#   push-from-pc.sh kit            bộ triển khai (deploy/vps) → /opt/mark/kit
#   push-from-pc.sh code           code Mark đang chạy trên PC → /opt/mark/app
#   push-from-pc.sh env            .env của Mark, đổi đường dẫn Windows sang Linux
#   push-from-pc.sh hermes-config  config.yaml của Hermes (KHÔNG chép auth.json)
#   push-from-pc.sh prep           = kit + code + env + hermes-config
#   push-from-pc.sh state          .tokens/ .audit/ ~/.lsr/token — CHỈ khi Mark trên PC đã tắt
#   push-from-pc.sh ssh [lệnh]     mở phiên SSH / chạy một lệnh trên VPS
#
# Biến: VPS_ENV (mặc định "D:/test vps/.env"), MARK_SRC (mặc định D:/hapas_agent_social),
#       HERMES_HOME_PC (mặc định $LOCALAPPDATA/hermes).
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_ENV="${VPS_ENV:-D:/test vps/.env}"
MARK_SRC="${MARK_SRC:-D:/hapas_agent_social}"
HERMES_HOME_PC="${HERMES_HOME_PC:-${LOCALAPPDATA:-C:/Users/PC/AppData/Local}/hermes}"

# Đọc ĐÚNG bốn khoá cần cho SSH — không `source` cả file (có mật khẩu root trong đó).
lay() { grep -E "^$1=" "$VPS_ENV" | tail -1 | cut -d= -f2- | tr -d '"'"'" | tr -d '[:cntrl:]' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'; }
HOST="$(lay VPS_HOST)"; PORT="$(lay VPS_PORT)"; USER_="$(lay VPS_USER)"; KEY="$(lay SSH_KEY_PATH)"
PORT="${PORT:-22}"; USER_="${USER_:-root}"
KEY="${KEY:-.ssh/vps_test_key}"; case "$KEY" in /*|[A-Za-z]:*) ;; *) KEY="$(dirname "$VPS_ENV")/$KEY";; esac
[ -n "$HOST" ] || { echo "Không đọc được VPS_HOST trong $VPS_ENV"; exit 1; }
[ -f "$KEY" ] || { echo "Không thấy khoá SSH: $KEY"; exit 1; }

SSH=(ssh -i "$KEY" -p "$PORT" -o BatchMode=yes -o PasswordAuthentication=no
     -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$USER_@$HOST")
tren_vps() { "${SSH[@]}" "$@"; }

kiem_ket_noi() {
  tren_vps true 2>/dev/null || { cat <<MSG
❌ Không đăng nhập được VPS bằng khoá $KEY.
   Cài khoá public vào VPS trước (xem deploy/vps/README.md, mục "Cài khoá SSH").
MSG
  exit 1; }
}

day_kit() {
  # Repo bật autocrlf: trên Windows script có thể thành CRLF, mà bash trên Linux gặp CR là chết.
  # Chép ra thư mục tạm, bỏ CR (chr 13) ở mọi file trừ .ps1/.cmd, rồi mới đóng gói.
  local tmp; tmp="$(mktemp -d)"
  PYTHONUTF8=1 python - "$KIT" "$tmp" <<'PY'
import os, sys
src, dst = sys.argv[1], sys.argv[2]
for ten in os.listdir(src):
    p = os.path.join(src, ten)
    if not os.path.isfile(p):
        continue
    b = open(p, "rb").read()
    if not ten.endswith((".ps1", ".cmd")):
        b = b.replace(bytes([13]), b"")
    open(os.path.join(dst, ten), "wb").write(b)
PY
  tar -C "$tmp" -czf - . | tren_vps 'mkdir -p /opt/mark/kit && tar -xzf - -C /opt/mark/kit && chmod +x /opt/mark/kit/*.sh /opt/mark/kit/mark'
  rm -rf "$tmp"
  echo "✅ kit → /opt/mark/kit"
}

day_code() {
  # Đẩy ĐÚNG cây code đang chạy trên PC (kể cả thay đổi chưa commit). Không đè .env, state,
  # venv Scrapling hay cấu hình lark-cli trên VPS.
  tar -C "$MARK_SRC" -czf - \
    --exclude=.git --exclude='.venv*' --exclude=__pycache__ --exclude=.pytest_cache \
    --exclude=.artifacts --exclude=.probe --exclude=.tokens --exclude=.audit \
    --exclude=.lark-cli-bot --exclude=.dinh_kem --exclude=exports --exclude='*.log' \
    --exclude=.env --exclude='.env.*' . \
  | tren_vps 'mkdir -p /opt/mark/app && tar -xzf - -C /opt/mark/app && (id mark >/dev/null 2>&1 && chown -R mark:mark /opt/mark/app || true)'
  echo "✅ code ($MARK_SRC, nhánh $(git -C "$MARK_SRC" rev-parse --abbrev-ref HEAD 2>/dev/null) @ $(git -C "$MARK_SRC" rev-parse --short HEAD 2>/dev/null)) → /opt/mark/app"
}

day_env() {
  local tmp; tmp="$(mktemp)"
  PYTHONUTF8=1 python - "$MARK_SRC/.env" "$tmp" <<'PY'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
DAT = {"HERMES_HOME": "/opt/mark/hermes-home", "HERMES_AGENT_DIR": "/opt/mark/hermes-agent"}
out, doi, bo = [], [], []
for line in open(src, encoding="utf-8").read().splitlines():
    m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
    if not m or line.lstrip().startswith("#"):
        out.append(line); continue
    k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
    if k in DAT:
        out.append(f"{k}={DAT[k]}"); doi.append(k)
    elif len(v) > 2 and v[0].isalpha() and v[1] == ":" and v[2] in ("/", chr(92)):  # đường dẫn Windows
        out.append(f"# bỏ khi lên VPS (đường dẫn Windows): {k}"); bo.append(k)
    else:
        out.append(line)
for k, v in DAT.items():
    if k not in doi:
        out.append(f"{k}={v}"); doi.append(k)
open(dst, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("  đổi:", ", ".join(doi)); print("  bỏ (đường dẫn Windows):", ", ".join(bo) or "—")
PY
  tren_vps 'mkdir -p /opt/mark/app && cat > /opt/mark/app/.env && chmod 600 /opt/mark/app/.env && (id mark >/dev/null 2>&1 && chown mark:mark /opt/mark/app/.env || true)' < "$tmp"
  rm -f "$tmp"
  echo "✅ .env → /opt/mark/app/.env (600)"
}

day_hermes_config() {
  [ -f "$HERMES_HOME_PC/config.yaml" ] || { echo "Không thấy $HERMES_HOME_PC/config.yaml"; exit 1; }
  tren_vps 'mkdir -p /opt/mark/hermes-home && cat > /opt/mark/hermes-home/config.yaml && (id mark >/dev/null 2>&1 && chown -R mark:mark /opt/mark/hermes-home || true)' \
    < "$HERMES_HOME_PC/config.yaml"
  echo "✅ config.yaml → /opt/mark/hermes-home (auth.json KHÔNG chép: dùng chung với agent họp trên PC"
  echo "   thì hai nơi gia hạn cùng một token sẽ khoá chéo nhau)"
}

mark_pc_dang_chay() {
  powershell.exe -NoProfile -Command \
    "@(Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'hapas_agent_social.+run\.py' }).Count" \
    2>/dev/null | tr -d '\r'
}

day_state() {
  local n; n="$(mark_pc_dang_chay || echo '?')"
  if [ "$n" != "0" ] && [ "${1:-}" != "--force" ]; then
    echo "❌ Mark trên PC còn chạy ($n tiến trình run.py). Tắt trước:"
    echo "   PowerShell (admin): Stop-ScheduledTask LSR-Mark-Tran-Bot; Disable-ScheduledTask LSR-Mark-Tran-Bot"
    exit 1
  fi
  tar -C "$MARK_SRC" -czf - .tokens .audit 2>/dev/null \
    | tren_vps 'mkdir -p /opt/mark/app && tar -xzf - -C /opt/mark/app && (id mark >/dev/null 2>&1 && chown -R mark:mark /opt/mark/app/.tokens /opt/mark/app/.audit || true)'
  if [ -f "$HOME/.lsr/token" ]; then
    tren_vps 'mkdir -p /opt/mark/.lsr && cat > /opt/mark/.lsr/token && chmod 600 /opt/mark/.lsr/token && (id mark >/dev/null 2>&1 && chown -R mark:mark /opt/mark/.lsr || true)' < "$HOME/.lsr/token"
  fi
  echo "✅ .tokens/ .audit/ (+ ~/.lsr/token) → VPS"
}

case "${1:-}" in
  kit)            kiem_ket_noi; day_kit ;;
  code)           kiem_ket_noi; day_code ;;
  env)            kiem_ket_noi; day_env ;;
  hermes-config)  kiem_ket_noi; day_hermes_config ;;
  prep)           kiem_ket_noi; day_kit; day_code; day_env; day_hermes_config ;;
  state)          kiem_ket_noi; day_state "${2:-}" ;;
  ssh)            shift; if [ $# -gt 0 ]; then tren_vps "$@"; else "${SSH[@]/BatchMode=yes/BatchMode=no}"; fi ;;
  *)              sed -n '2,14p' "$0"; exit 2 ;;
esac
