# 2 · Nhận vai — từ manifest tới token

## Bốn bước

```
manifest.json  →  đánh giá chạy thật  →  POST /v1/agents/enroll  →  token vào .env
```

Không có bước nào bỏ được, và bước hai là bước hay bị làm giả nhất.

## Manifest — hợp đồng với platform

Tối thiểu (SPEC §2.1):

```json
{
  "agent": {
    "id": "AG-VIET-HOA-CO-GACH",
    "name": "Tên hiển thị",
    "type": "planner | executive | quality_controller",
    "owner": "ai@hapas.vn",
    "backup_owner": "nguoi.khac@hapas.vn",
    "squad": "Tên nhóm có dấu",
    "description": "≥ 30 ký tự, nói agent làm gì"
  },
  "data_sources": [{"kind": "mcp", "ref": "web_search"}],
  "connections": [{"channel": "lark", "in": ["event"], "out": ["reply", "call_agent"]}],
  "kpis": [{"name": "…", "metric": "…", "target": "…"}],
  "permissions": {"data": {"forbidden": ["…"]}}
}
```

Kiểm trước khi gửi, đừng đoán:

```bash
curl -H "Authorization: Bearer $PAT" -H 'Content-Type: application/json' \
  -d '{"manifest": …}' https://platform.…/v1/agents/manifest/validate
```

Nó trả `type` và `manifest_hash` — cả hai đều cần ở bước sau.

### `type` quyết định trần quyền, không phải mong muốn

```
planner             reply · call_agent
executive           reply · send_message · create_task · call_agent · write_data
quality_controller  reply · call_agent
```

Chọn type theo **thứ agent thật sự làm**, không theo tên nhóm. Mark nằm nhóm "Chức năng
dùng chung" nhưng là `executive`, vì ba tool nghiên cứu của nó gộp kết quả vào Lark
Sheet rồi trả link — đó là ghi ra ngoài hệ thống.

**Khai hẹp hơn trần là tốt.** Mark là `executive` nhưng cố ý **không** khai
`send_message`: nó xuất Sheet được nhưng không tự đẩy tin cho ai. Muốn mở sau thì thêm
vào `connections.out` rồi đồng bộ — không cần dựng lại agent.

### Đổi `type` sau khi enroll: phải xoá rồi dựng lại

`POST /v1/agents/{id}/change` đẩy **mọi** thay đổi chạm policy vào `pending_review`, mà
platform **chưa có endpoint duyệt** `agent_changes` — bảng có `reviewed_by`/`reviewed_at`
nhưng không nơi nào ghi vào. Ba đường ghi được `type` còn lại: `register` và `nocode` bị
Caddy chặn từ ngoài, `enroll` trả 409 với agent đang sống.

Nên chọn `type` cho đúng ngay từ đầu. Nếu buộc phải đổi, xem phần "Dựng lại" bên dưới.

## Đánh giá — phải chạy thật

`enroll` đòi `{tests_total, tests_pass, manifest_hash, failures}`. Nó **chỉ kiểm
`tests_pass == tests_total`** — một báo cáo khai khống qua được hết.

Bài đánh giá tử tế phải **suy phạm vi từ chính manifest** rồi ép lên mã thật:

```
data_sources + connections.out  →  danh sách tool được phép
                                →  chạy qua điểm hội tụ dispatch THẬT
                                →  đếm ca bị chặn đúng / lọt sai
```

Vòng đầu của Mark ra **48/50** vì đúng kiểu lỗi này: `SocialPolicy` cho ghi và gửi
**chỉ cần có `--yes`** — rộng hơn hợp đồng. Nếu nhận vai lúc đó, console sẽ ghi *"agent
này chỉ trả lời"* trong khi runtime vẫn cho nó ghi Base và gửi tin.

Tham khảo: `nhan_vai/danh_gia.py` trong gói bàn giao — 51 ca, chạy trên `ToolRegistry`
thật của Hermes (98 tool), không mạng, không credential.

Hai cái bẫy trong chính bài đánh giá:

- **Truyền `out` thật vào**, đừng truyền rỗng. Bản đầu truyền `out=[]` nên suốt một thời
  gian nó kiểm một agent không khai quyền gì — xanh, nhưng xanh về agent khác.
- **Ghim băm manifest vào báo cáo.** Manifest đổi là băm đổi; báo cáo cũ gắn với manifest
  mới là nói dối một cách im lặng.

## Enroll

```python
POST /v1/agents/enroll
{
  "agent_id": "AG-…", "name": "…", "owner": "…", "squad": "…",
  "deployment": "external",
  "host_note": "máy của ai, chạy bằng gì",
  "manifest": {…}, "evaluation": {…}
}
```

Trả về `telemetry_key` (`lsr_tel_…`). **Ghi thẳng vào `.env`, đừng in ra màn hình** —
một lần in là nó nằm trong lịch sử terminal, trong log, và trong transcript.

Người tạo là admin platform thì agent **tự `active` luôn**, bỏ qua golive checklist. Tiện
lúc dựng, nhưng nhớ rằng checklist "28/28 complete" khi đó chỉ nghĩa là **đã khai đủ
trường**, không phải đã kiểm gì.

## Dựng lại khi buộc phải đổi type

Thứ **sống sót** qua `delete`:

```
brain_items        kiến thức + kỹ năng tự viết
agent_golive_checklist
agent_traces
agent_changes
```

Thứ **mất**:

```
lark_apps          phải gắn lại app
routing_binding    phải nối lại kênh
agent_versions     MẤT TIỂU SỬ và danh sách kỹ năng ĐANG BẬT
agent_publications
agent_runtime_tokens   token cũ chết, phải thay .env
connector_grants · a2a_grants · sessions · user_facts · quotas · schedules
```

Chỗ đau nhất là `agent_versions`: bản thân kỹ năng còn (trong `brain_items`) nhưng
**danh sách đang bật thì mất**, và tiểu sử trống trơn. Console trông như agent vừa bị
xoá não. Chuẩn bị sẵn script bật lại trước khi xoá.

Quy trình an toàn:

1. Chụp lại trạng thái: kiến thức (số tài liệu/mẩu), kỹ năng đang bật, app Lark, tiểu sử
2. Xoá
3. `enroll` lại với manifest mới
4. Ghi token mới vào `.env`
5. Gắn lại app Lark, `sync` để nó về `approved`
6. Dựng lại version (tiểu sử + kỹ năng)
7. Đối chiếu với bản chụp ở bước 1

Mark làm theo đúng trình tự này: **17/17** ở bước dựng lại, **13/13** ở bước đối chiếu.
Nhưng tôi vẫn sót — kiểm kiến thức mà quên kiểm tiểu sử và kỹ năng, vì chỉ kiểm thứ
mình đoán trước sẽ mất. **Kiểm đủ những gì màn hình hiển thị, không chỉ những gì mình
ngờ.**
