#!/usr/bin/env bash
# Tắt đăng nhập SSH bằng mật khẩu (máy đang bị dò mật khẩu root liên tục). Chạy bằng root,
# SAU KHI đã đăng nhập được bằng khoá. Script tự kiểm và từ chối nếu chưa có khoá nào —
# không bao giờ tự khoá mình ra ngoài.
#
#   bash /opt/mark/kit/harden-ssh.sh
#
# Giữ nguyên phiên SSH đang mở, mở thêm một phiên mới bằng khoá để thử trước khi thoát.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Chạy bằng root."; exit 1; }

AK=/root/.ssh/authorized_keys
n=$(grep -cE '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-[a-z0-9-]+) ' "$AK" 2>/dev/null || true)
[ "${n:-0}" -ge 1 ] || { echo "❌ $AK chưa có khoá nào — cài khoá trước, KHÔNG tắt mật khẩu."; exit 1; }
echo "Có $n khoá trong $AK."

cat > /etc/ssh/sshd_config.d/10-mark-harden.conf <<'CONF'
# Mark VPS: chỉ đăng nhập bằng khoá.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
MaxAuthTries 3
CONF
sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd
echo "✅ Đã tắt đăng nhập bằng mật khẩu. Thử mở phiên SSH MỚI bằng khoá trước khi đóng phiên này."
echo "   Nhớ đổi mật khẩu root (passwd) — mật khẩu cũ đang nằm trong file .env trên PC."
