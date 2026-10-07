# Phoenix tự host cho Mark (VPS Ubuntu 24.04)

Trace mỗi lượt của Mark (span gốc `mark.turn` + span LLM + span tool) vào Arize Phoenix
chạy trên CHÍNH VPS của Mark, chỉ nghe `127.0.0.1`. Người xem vào bằng SSH tunnel.
Phía Mark: `phoenix_trace.py` — tắt hẳn khi không đặt `PHOENIX_COLLECTOR_ENDPOINT`.

Giấy phép Phoenix: Elastic License 2.0 — tự host dùng nội bộ được; không cung cấp lại
cho bên thứ ba như dịch vụ, không xoá thông báo bản quyền.

## 1. Cài server (venv riêng, KHÔNG dùng venv Hermes)

```bash
sudo useradd --system --home /var/lib/phoenix --shell /usr/sbin/nologin phoenix
sudo install -d -o phoenix -g phoenix -m 0750 /var/lib/phoenix
sudo install -d -o root -g root -m 0755 /opt/phoenix /etc/phoenix
sudo python3.12 -m venv /opt/phoenix/venv
sudo /opt/phoenix/venv/bin/pip install --upgrade pip
sudo /opt/phoenix/venv/bin/pip install "arize-phoenix==20.19.0"

# cấu hình: chép phoenix.env.example, thay PHOENIX_SECRET + mật khẩu admin
sudo install -o root -g root -m 0600 deploy/phoenix/phoenix.env.example /etc/phoenix/phoenix.env
sudo sed -i "s/__THAY_BANG_openssl_rand_hex_32__/$(openssl rand -hex 32)/" /etc/phoenix/phoenix.env
sudoedit /etc/phoenix/phoenix.env          # đặt PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD

sudo install -o root -g root -m 0644 deploy/phoenix/phoenix.service /etc/systemd/system/phoenix.service
sudo systemctl daemon-reload && sudo systemctl enable --now phoenix
ss -ltnp | grep -E '6006|4317'   # mong đợi: 127.0.0.1:6006 và *:4317 (xem mục 2)
```

Nâng cấp: ghim bản mới, `pip install`, `systemctl restart phoenix`. Phoenix chạy migration
lúc khởi động — **sao lưu `/var/lib/phoenix/phoenix.db` trước**.

## 2. Cổng gRPC 4317

Phoenix luôn bind gRPC ở `[::]:4317` (bỏ qua `PHOENIX_HOST`; chỉ tắt được khi chạy
read-only). VPS **đã có ufw bật, default deny incoming, chỉ mở 22/tcp (IPv4 + IPv6)** nên
4317 đã bị chặn từ ngoài — **không cần thêm luật iptables nào**. Mark gửi qua HTTP
`127.0.0.1:6006`, không dùng 4317; auth bật nên gRPC cũng đòi API key. Unit còn đặt
`IPAddressAllow=localhost` + `IPAddressDeny=any` (cgroup chỉ cho loopback) — lớp thứ hai.

Chỉ cần kiểm sau khi cài:

```bash
sudo ufw status verbose                      # Default: deny (incoming); chỉ 22/tcp ALLOW
# từ MÁY KHÁC (không phải VPS):
nc -vz -w 5 <ip-vps> 4317                    # phải thất bại / timeout
nc -vz -w 5 <ip-vps> 6006                    # phải thất bại / timeout
```

Nếu sau này ufw bị tắt hoặc mở rộng: thêm `sudo ufw deny 4317/tcp` (áp cho cả IPv6 khi
`IPV6=yes` trong `/etc/default/ufw`). Kiểm cả firewall của nhà cung cấp cloud.

## 3. Lần đăng nhập đầu + System API key cho Mark

Auth bật thì Phoenix **từ chối mọi trace cho tới khi có API key**.

1. Mở tunnel (mục 5), vào `http://localhost:6006`, đăng nhập `admin@localhost` bằng
   mật khẩu ban đầu, **đổi mật khẩu ngay**.
2. Settings → API Keys → **System Keys** → Create, tên `mark-collector`. Key chỉ hiện
   một lần. System key không mất khi xoá user admin.
3. (Tuỳ chọn) tạo tài khoản cho từng người trong team (Settings → Users), mỗi người dùng
   **user key** riêng khi chạy eval từ laptop — không dùng key của Mark.

## 4. Bật trace phía Mark

```bash
# gói OTel vào ĐÚNG venv Mark đang chạy (venv Hermes), ghim trùng extra `otlp` của Hermes
<HERMES_AGENT_DIR>/venv/bin/pip install -r requirements-phoenix.txt
<HERMES_AGENT_DIR>/venv/bin/pip check
```

Thêm vào `.env` của Mark (xem `.env.example`):

```
PHOENIX_COLLECTOR_ENDPOINT=http://127.0.0.1:6006
PHOENIX_API_KEY=<system key mark-collector>
PHOENIX_PROJECT_NAME=mark
MARK_PHOENIX_SALT=<openssl rand -hex 32>
```

`mark restart`, rồi xem dòng khởi động: `Phoenix:    BẬT → http://127.0.0.1:6006 · project
mark · nội dung đã che · hook ✅`. Thiếu gói → `TẮT (chưa cài gói opentelemetry)`, Mark vẫn
chạy. `MARK_PHOENIX_CONTENT=off` = chỉ gửi tên/thời gian/token/trạng thái, không gửi chữ.
`MARK_PHOENIX_LLM_INPUT=1` = gửi thêm tin nhắn đưa vào model (đã che, không system prompt).

Tắt trace: xoá `PHOENIX_COLLECTOR_ENDPOINT` rồi `mark restart`.

**Không bao giờ** đặt `PHOENIX_COLLECTOR_ENDPOINT` trên máy PC trỏ về VPS (không chạy hai Mark).

## 5. Xem trace (SSH tunnel)

```bash
ssh -N -L 6006:127.0.0.1:6006 <user>@<ip-vps>
# rồi mở http://localhost:6006 ; cổng 6006 ở máy đang bận thì -L 16006:127.0.0.1:6006
```

PowerShell trên Windows 10+ dùng nguyên lệnh trên (OpenSSH có sẵn).

## 6. Kiểm trên staging trước khi bật prod

- Một lượt dán token giả, email, SĐT, `ou_…` → tìm trong UI Phoenix không thấy;
  `sqlite3 /var/lib/phoenix/phoenix.db "select count(*) from spans where attributes like '%sk-%'"` = 0.
- Span tool cùng trace_id với `mark.turn`; lượt 429/đổi tài khoản nằm chung một trace.
- `systemctl stop phoenix` → Mark vẫn trả lời bình thường, log chỉ một dòng
  `[phoenix] không gửi được trace` mỗi 5 phút; `mark restart` không chậm thêm quá ~6 s.
- Theo dõi một tuần: `systemctl status phoenix` (MemoryMax 2G), `du -sh /var/lib/phoenix`.
- Bản Hermes trên VPS phải có các hook quan sát (bản đã thử: 0.19.1, commit `d1afa16`):
  `grep -n 'post_api_request\|_emit_post_tool_call_hook' <HERMES_AGENT_DIR>/agent/conversation_loop.py <HERMES_AGENT_DIR>/model_tools.py`
  và `grep -n 'class PluginContext\|def register_hook' <HERMES_AGENT_DIR>/hermes_cli/plugins.py`.
