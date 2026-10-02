#!/usr/bin/env bash
# Gia cố SSH mà vẫn giữ NHIỀU đường vào. Chạy bằng root, sau khi đã đăng nhập được bằng khoá.
#
#   bash /opt/mark/kit/harden-ssh.sh [tên-user-quản-trị]     (mặc định: tham)
#
# Sau khi chạy, có ba đường vào độc lập:
#   1. SSH bằng khoá (root hoặc user quản trị)            — đường hằng ngày
#   2. Console web của nhà cung cấp, root + mật khẩu       — không đi qua SSH, không bị ảnh hưởng
#   3. SSH bằng MẬT KHẨU với user quản trị (có sudo)       — đăng nhập từ máy không có khoá
# Chỉ tắt đúng một cửa: root đăng nhập SSH bằng mật khẩu (cửa bị dò mật khẩu liên tục).
# fail2ban vẫn chặn IP dò mật khẩu ở đường 3.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Chạy bằng root."; exit 1; }
ADMIN="${1:-tham}"

AK=/root/.ssh/authorized_keys
n=$(grep -cE '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-[a-z0-9-]+) ' "$AK" 2>/dev/null || true)
[ "${n:-0}" -ge 1 ] || { echo "❌ $AK chưa có khoá nào — cài khoá trước, KHÔNG đụng SSH."; exit 1; }

# User quản trị: dùng chung khoá của root (đường 1) + mật khẩu riêng do người dùng TỰ đặt (đường 3).
if ! id "$ADMIN" >/dev/null 2>&1; then
  useradd -m -s /bin/bash -G sudo "$ADMIN"
  echo "Đã tạo user $ADMIN (nhóm sudo)."
fi
install -d -m 700 -o "$ADMIN" -g "$ADMIN" "/home/$ADMIN/.ssh"
install -m 600 -o "$ADMIN" -g "$ADMIN" "$AK" "/home/$ADMIN/.ssh/authorized_keys"

# Tên file phải đứng TRƯỚC mọi file khác theo thứ tự chữ cái: sshd lấy giá trị gặp ĐẦU TIÊN, mà
# nhà cung cấp (Data Online) cài sẵn 00-dataonline.conf với PermitRootLogin yes. Không sửa file
# của họ — tính năng Reset Root Password trên trang quản lý có thể dựa vào nó.
CONF_FILE=/etc/ssh/sshd_config.d/00-0-mark-harden.conf
rm -f /etc/ssh/sshd_config.d/10-mark-harden.conf
cat > "$CONF_FILE" <<CONF
# Mark VPS: root chỉ vào bằng khoá; $ADMIN vào được bằng khoá HOẶC mật khẩu.
PermitRootLogin prohibit-password
PubkeyAuthentication yes
PasswordAuthentication yes
KbdInteractiveAuthentication no
MaxAuthTries 4
CONF
sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd
case "$(sshd -T | awk '$1=="permitrootlogin"{print $2}')" in prohibit-password|without-password) true;; *) false;; esac   || { echo "❌ sshd vẫn cho root đăng nhập bằng mật khẩu — có file cấu hình khác đọc trước"; exit 1; }
# sudo báo "unable to resolve host" khi /etc/hosts thiếu tên máy.
grep -qw "$(hostname)" /etc/hosts || echo "127.0.1.1 $(hostname)" >> /etc/hosts

if passwd -S "$ADMIN" 2>/dev/null | awk '{exit ($2=="P")?0:1}'; then
  echo "✅ $ADMIN đã có mật khẩu — đường 3 dùng được."
else
  echo "⚠ $ADMIN CHƯA có mật khẩu → đường 3 chưa dùng được. Tự đặt bằng:  passwd $ADMIN"
fi
echo "✅ Root: SSH chỉ bằng khoá. Console web (root + mật khẩu) vẫn dùng như cũ."
echo "   Mở thêm một phiên SSH MỚI để thử trước khi đóng phiên này."
