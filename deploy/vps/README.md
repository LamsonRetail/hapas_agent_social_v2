# Chạy Mark trên VPS

Bộ này đưa Mark (`AG-SOCIAL-LISTENING`) từ PC Windows lên VPS Ubuntu 24.04, chạy dưới
**systemd**: luôn đúng **một** bản, tự chạy lại khi chết, có log, restart bằng một lệnh.

Mark không cần cổng vào nào: nó tự kéo việc từ platform (`/v1/self/jobs`). Chỉ cần đi ra HTTPS.

## Restart hằng ngày

| Ở đâu | Làm gì |
| --- | --- |
| PC | bấm đúp `deploy/vps/restart-mark-vps.cmd` (xem trạng thái: `status-mark-vps.cmd`) |
| PC (dòng lệnh) | `powershell -File deploy/vps/mark-vps.ps1 restart` — hoặc `status`, `logs`, `stop`, `start` |
| VPS | `mark restart` · `mark status` · `mark logs -f` · `mark stop` · `mark start` |

`mark restart` không chỉ khởi động lại: nó **đợi tới khi Mark lấy được token Lark** rồi báo ✅,
còn không lên sau 45 giây thì in log lỗi. Bot chết giữa chừng thì systemd tự chạy lại sau 10
giây; chết liên tục 10 lần trong 10 phút thì dừng hẳn (khỏi đốt quota) — xem `mark logs`.

Cập nhật code: trên PC `bash deploy/vps/push-from-pc.sh code`, rồi `mark restart`.
`.env` chỉ được đọc lúc khởi động — đổi `.env` thì `push-from-pc.sh env` rồi `mark restart`.

## Lần đầu

Đọc địa chỉ VPS + khoá từ `D:\test vps\.env` (chỉ các khoá `VPS_HOST`, `VPS_PORT`, `VPS_USER`,
`SSH_KEY_PATH` — **không bao giờ dùng mật khẩu**).

0. **Cài khoá SSH** (một lần, qua Console của nhà cung cấp VPS, đăng nhập root): dán dòng sau,
   thay `<khoá>` bằng nội dung file `D:\test vps\.ssh\vps_test_key.pub`:

   ```bash
   mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '<khoá>' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
   ```

1. **Dựng môi trường** — trên PC: `bash deploy/vps/push-from-pc.sh kit`, rồi trên VPS:
   `bash /opt/mark/kit/setup.sh` (vá bảo mật, swap 4 GB, tường lửa chỉ mở SSH, fail2ban, user
   `mark`, Node 22 + lark-cli, Python 3.11/3.12, Hermes đúng commit PC đang chạy, Chromium,
   Scrapling). Sau đó `bash /opt/mark/kit/harden-ssh.sh` (tắt đăng nhập bằng mật khẩu — tự từ
   chối nếu chưa có khoá) và **đổi mật khẩu root** (`passwd`).
2. **Đẩy code + cấu hình** — trên PC: `bash deploy/vps/push-from-pc.sh prep`
   (code đang chạy trên PC, `.env` đã đổi đường dẫn Windows → Linux, `config.yaml` của Hermes).
3. **Kiểm khi CHƯA bật bot** — trên VPS: `mark check` (đọc `.env`, lark-cli, Scrapling, nạp
   Hermes, token Lark, lease tài khoản AI, test không chạm mạng).
4. **Chuyển giao** (vài phút):
   - PC, PowerShell admin: `Stop-ScheduledTask LSR-Mark-Tran-Bot; Disable-ScheduledTask LSR-Mark-Tran-Bot`
   - PC: `bash deploy/vps/push-from-pc.sh state` (lịch sử chat, trí nhớ, sổ việc nền — tự từ
     chối nếu Mark trên PC còn chạy)
   - VPS: `mark go-live` → nhắn thử Mark trên Lark → `mark logs -f`

## Quay về PC

VPS: `mark off` (tắt và không tự bật lại). PC: `Enable-ScheduledTask LSR-Mark-Tran-Bot;
Start-ScheduledTask LSR-Mark-Tran-Bot`. Nếu đã chạy trên VPS một thời gian, chép `.tokens/` và
`.audit/` từ VPS về trước khi bật lại trên PC.

## Không được làm

- **Chạy hai Mark cùng lúc** (PC + VPS): hai bên giành job của nhau, trả lời hai lần, quét trùng.
  Systemd chặn hai bản trên VPS; còn PC thì phải tắt task trước — `mark go-live` hỏi lại cho chắc,
  và bot từ chối khởi động khi chưa go-live (`mark guard`).
- **Chép `auth.json` của Hermes từ PC lên VPS**: agent họp trên PC đang dùng nó; hai nơi gia hạn
  cùng một token là khoá chéo nhau, cả hai bot chết. Mark trên VPS chạy bằng tài khoản gắn trên
  console (lease); muốn có dự phòng thì đăng nhập Codex **riêng**: `mark login-codex`.

## Bố cục trên VPS

| Đường dẫn | Là gì |
| --- | --- |
| `/opt/mark/app` | code Mark + `.env` (600) + `.tokens/` `.audit/` + `.venv-scrapling/` |
| `/opt/mark/hermes-agent` | Hermes `d1afa16` + `venv/` (Python 3.11, gói chốt ở `requirements-hermes.txt`) |
| `/opt/mark/hermes-home` | `HERMES_HOME` riêng của Mark (`config.yaml`; `auth.json` chỉ có khi `mark login-codex`) |
| `/opt/mark/ms-playwright` | Chromium cho agent-browser và Scrapling |
| `/etc/systemd/system/mark.service` | dịch vụ; log: `journalctl -u mark` (= `mark logs`) |
