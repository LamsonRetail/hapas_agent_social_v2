# Social Agent — Lark BOT agent (Hermes brain + lark-cli)

Con **bot Lark** trả lời tin nhắn bằng **Hermes** (model `gpt-5.6-terra` qua
`openai-codex`) và thao tác trên Lark qua **lark-cli** — tất cả dưới **danh tính
BOT** (`tenant_access_token` mint từ `app_id`/`app_secret`). Không dùng seat
user / OAuth as-user nữa.

Cơ chế:

- **Nhận tin:** chạy `lark-cli event consume im.message.receive_v1 --as bot`
  (long-connection). Lark PUSH tin về stdout dạng NDJSON — không cần webhook.
  Group: chỉ trả lời khi bot được @mention; p2p: luôn trả lời.
- **Trả lời & thao tác:** gửi qua `lark_client` (REST) và tool `lark_cli` (đủ mọi
  domain: im, calendar, task, wiki, docs, drive, base, sheets, mail…) — đều dưới
  danh tính bot. Bot KHÔNG thấy tài nguyên cá nhân của người khác.

## Kiến trúc

| File | Vai trò |
|------|---------|
| `config.py` | Đọc `.env`; app/token/event/brain config; `brand`, `cli_config_dir`. |
| `lark_client.py` | `get_tenant_token()` (cache + auto-refresh), `get_bot_open_id()`, REST `call()`, `send_text/reply_text()`, reactions — tất cả dùng tenant token. |
| `listener.py` | Supervisor: (re)spawn `event consume … --as bot`, parse NDJSON, lọc (bot/echo, group không @mention), respawn trước khi token 2h hết hạn. |
| `lark_cli_tool.py` | Tool `lark_cli` cho brain — chạy lark-cli với tenant token inject qua env (`LARKSUITE_CLI_TENANT_ACCESS_TOKEN` + `DEFAULT_AS=bot`). |
| `brain.py` | Hermes brain: `resolve_runtime_provider("openai-codex")` → `AIAgent` → `run_conversation` → `final_response`. Nhớ ngữ cảnh theo từng chat + trí nhớ per-user. |
| `scheduler.py` | Ticker nền: bắn nhắc hẹn đã đặt, gửi AS bot. |
| `run.py` | Main: check token → in bot open_id → start scheduler → `start_listener`. Mỗi tin: ack reaction → brain (có timeout) → reply as bot. |
| `start.ps1` | Launcher dùng venv của Hermes (đã có `requests`) + UTF-8. |

## Cài đặt

1. Copy cấu hình và điền `LARK_APP_ID` / `LARK_APP_SECRET` của app bot:
   ```powershell
   copy .env.example .env
   ```
2. Trong **Lark Developer Console** của app:
   - **Subscribe event** `im.message.receive_v1` ở chế độ **long-connection**
     ("应用长连接" / long connection).
   - Cấp scope: `im:message.p2p_msg:readonly` (nhận) + `im:message` (gửi)
     (+ `im:message.reactions:write_only` cho badge "Typing").
   - **Add bot vào group** nào muốn nó trả lời (và @mention bot trong group).
3. Cài lark-cli nếu chưa có:
   ```powershell
   npx @larksuite/cli@latest install
   ```
   (hoặc đặt `LARK_CLI_PATH` trỏ tới `lark-cli.exe`).
4. Trỏ Hermes: đặt `HERMES_HOME` và `HERMES_AGENT_DIR` trong `.env` về
   `hermes-home` thật (mặc định resolve cạnh folder này, thường KHÔNG đúng).
5. Nếu dùng `social_listen` trên YouTube: bật **YouTube Data API v3** trong
   Google Cloud và điền `YOUTUBE_DATA_API_KEY`. YouTube dùng API chính thức,
   không fallback sang Apify trả phí.

## Chạy

```powershell
.\start.ps1
```

Sau đó nhắn cho bot (DM) hoặc @mention bot trong group → bot trả lời bằng tiếng
Việt theo persona trong `persona.md`.

## Ghi chú

- Brain resolve credentials **mỗi tin** nên luôn dùng JWT Codex mới nhất
  (auto-refresh trong `auth.json` của hermes-home).
- Listener respawn consumer mỗi `LARK_EVENT_RESPAWN_SECONDS` (mặc định 90 phút)
  để token 2h không bao giờ hết hạn giữa chừng; dừng bằng đóng stdin (không
  `kill -9` — tránh rò subscription trên server).
- Sửa tính cách bot ở `persona.md`, KHÔNG cần sửa code.
- Kiến trúc as-user cũ (`poller.py`, `authorize.py`, `lark_tool.py`,
  `seed_p2p.py`) đã bị **xoá hẳn** ngày 28/08/2026 — bot chỉ còn một danh tính
  duy nhất là tenant token. Cần tra cứu thì xem commit trước đó trong git.
