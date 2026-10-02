#!/usr/bin/env bash
# Dựng môi trường chạy Mark trên VPS Ubuntu 24.04. Chạy bằng root; chạy lại bao nhiêu lần
# cũng được (bước nào đã xong thì bỏ qua). KHÔNG bật bot — bật bằng `mark go-live` sau khi
# Mark trên PC đã tắt (hai bản cùng chạy là giành job của nhau, trả lời hai lần).
#
#   bash /opt/mark/kit/setup.sh
#
# Bố cục:
#   /opt/mark/app            code Mark (đẩy từ PC bằng push-from-pc.sh code)
#   /opt/mark/hermes-agent   Hermes đúng commit PC đang chạy + venv Python 3.11
#   /opt/mark/hermes-home    HERMES_HOME của RIÊNG Mark (không chép auth.json từ PC)
#   /opt/mark/ms-playwright  trình duyệt dùng chung cho agent-browser và Scrapling
set -euo pipefail

HERMES_REPO="https://github.com/NousResearch/hermes-agent.git"
HERMES_COMMIT="d1afa16053a3777849c2b5465d59a0147b2172f9"   # = bản trên PC (02/10/2026)
LARK_CLI_VERSION="1.0.89"
NODE_MAJOR=22
BASE=/opt/mark
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PYTHON_INSTALL_DIR="$BASE/python"        # python của uv nằm chỗ user mark đọc được
export PLAYWRIGHT_BROWSERS_PATH="$BASE/ms-playwright"
export DEBIAN_FRONTEND=noninteractive

buoc() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "Chạy bằng root."; exit 1; }

buoc "Gói hệ thống + bản vá bảo mật"
apt-get update -q
apt-get -y -q upgrade
apt-get -y -q install git curl ca-certificates build-essential ufw fail2ban \
  unattended-upgrades jq rsync tar
timedatectl set-timezone Asia/Ho_Chi_Minh || true

buoc "Swap 4 GB (máy không có swap; hai bộ Chromium có thể ngốn RAM)"
if ! swapon --show | grep -q .; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

buoc "Tường lửa: chỉ mở SSH (Mark không cần cổng vào nào — nó tự kéo việc từ platform)"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null
systemctl enable --now fail2ban >/dev/null

buoc "User mark"
id mark >/dev/null 2>&1 || useradd --system --home-dir "$BASE" --shell /bin/bash mark
mkdir -p "$BASE"/{app,hermes-home,ms-playwright,python,kit,.lsr}
chmod 700 "$BASE/.lsr"

buoc "Node $NODE_MAJOR + lark-cli $LARK_CLI_VERSION"
if ! node -v 2>/dev/null | grep -q "^v$NODE_MAJOR\."; then
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
  apt-get -y -q install nodejs
fi
npm ls -g @larksuite/cli 2>/dev/null | grep -q "@$LARK_CLI_VERSION" \
  || npm install -g --no-fund --no-audit "@larksuite/cli@$LARK_CLI_VERSION"
command -v lark-cli >/dev/null || { echo "Không thấy lark-cli sau khi cài."; exit 1; }

buoc "uv + Python 3.11 / 3.12"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh \
  | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh
uv python install 3.11 3.12

buoc "Hermes ${HERMES_COMMIT:0:7}"
[ -d "$BASE/hermes-agent/.git" ] || git clone -q "$HERMES_REPO" "$BASE/hermes-agent"
git -C "$BASE/hermes-agent" fetch -q origin
git -C "$BASE/hermes-agent" checkout -q "$HERMES_COMMIT"
[ -x "$BASE/hermes-agent/venv/bin/python" ] || uv venv -q --python 3.11 "$BASE/hermes-agent/venv"
uv pip install -q --python "$BASE/hermes-agent/venv/bin/python" -r "$KIT/requirements-hermes.txt"
uv pip install -q --python "$BASE/hermes-agent/venv/bin/python" --no-deps -e "$BASE/hermes-agent"

buoc "agent-browser (toolset browser của Hermes) + Chromium"
( cd "$BASE/hermes-agent" && npm install --no-fund --no-audit >/dev/null )
( cd "$BASE/hermes-agent" && npx --yes playwright install --with-deps chromium )

buoc "venv Scrapling (Python 3.12) cho web_read / social crawl"
[ -x "$BASE/app/.venv-scrapling/bin/python" ] || uv venv -q --python 3.12 "$BASE/app/.venv-scrapling"
uv pip install -q --python "$BASE/app/.venv-scrapling/bin/python" -r "$KIT/requirements-scrapling.txt"
"$BASE/app/.venv-scrapling/bin/scrapling" install || echo "⚠ scrapling install lỗi — chạy lại sau"
# Code Mark cũ gọi cứng `.venv-scrapling/Scripts/python.exe` (kiểu Windows) — trỏ về bin/python
# để bản code nào đẩy lên cũng chạy được Scrapling.
mkdir -p "$BASE/app/.venv-scrapling/Scripts"
ln -sfn ../bin/python "$BASE/app/.venv-scrapling/Scripts/python.exe"

buoc "Dịch vụ systemd + lệnh mark"
install -m 0755 "$KIT/mark" /usr/local/bin/mark
install -m 0644 "$KIT/mark.service" /etc/systemd/system/mark.service
systemctl daemon-reload
chown -R mark:mark "$BASE"
[ -f "$BASE/hermes-home/config.yaml" ] || echo "⚠ chưa có config.yaml — trên PC chạy: push-from-pc.sh hermes-config"

buoc "Xong"
cat <<'MSG'
Bước tiếp:
  1. Trên PC:  push-from-pc.sh code ; push-from-pc.sh env ; push-from-pc.sh hermes-config
  2. Trên VPS: mark check      (kiểm khi CHƯA bật bot)
  3. Tắt Mark trên PC, rồi trên PC: push-from-pc.sh state
  4. Trên VPS: mark go-live    (bật bot, tự chạy lại khi chết / khi khởi động máy)
MSG
