# Test cases — Mark Trần

> Mọi e2e chạy trên `AG-SOCIAL-LISTENING-TEST`; không dùng agent hoặc app Lark thật.

| ID      | Kịch bản                                               | Kỳ vọng                                                  | Trạng thái     |
| ------- | ------------------------------------------------------ | -------------------------------------------------------- | -------------- |
| MARK-01 | Khởi động thiếu cấu hình Platform                      | Bot vẫn chạy; bridge/context/telemetry là no-op          | local          |
| MARK-02 | Bật job poll với ID production nhưng không có override | Không khởi động poller                                   | local          |
| MARK-03 | Bật job poll với `AG-SOCIAL-LISTENING-TEST`            | Poller nhận job và gọi đúng `brain.reply`                | e2e            |
| MARK-04 | Platform mất kết nối khi gửi trace                     | Trace nằm trong WAL và được flush lại với cùng `run_id`  | local + e2e    |
| MARK-05 | Platform trả dev version và RAG                        | System prompt chứa instruction, evidence và source URL   | local + e2e    |
| MARK-06 | Yêu cầu gửi tin/tạo task/ghi Base                      | Tool bị policy guard chặn trước handler                  | local + e2e    |
| MARK-07 | `lark_cli api GET ...`                                 | Được phép ở chế độ read-only                             | local          |
| MARK-08 | `lark_cli api POST ...` hoặc `--yes`                   | Bị chặn fail-closed                                      | local          |
| MARK-09 | Knowledge catalog chứa transcript                      | Không được chọn để sync                                  | local          |
| MARK-10 | Trả lời dùng knowledge                                 | Có tên nguồn/URL; không bịa số ngoài evidence            | AG-EVAL        |
| MARK-11 | Câu hỏi chứa email/số điện thoại/token                 | Telemetry redact trước khi vào WAL                       | local          |
| MARK-12 | Deactivate hoặc stamp hết hạn                          | Không có tool/out mới sau TTL                            | chờ ADR `EXTC` |
| MARK-13 | Wiki có node mới                                       | Node mặc định tắt, chỉ ingest sau duyệt                  | chờ ADR `WIKI` |
| MARK-14 | So sánh Lark và web cùng câu hỏi                       | Cùng persona/version/policy; khác biệt chỉ ở format kênh | e2e sau bind   |

## Điều kiện đạt vòng đầu

- Unit test `MARK-01`, `02`, `04`–`09`, `11` xanh.
- Platform web chat hoàn tất một round-trip trên TEST ID.
- Không có write/send thật trong lúc kiểm thử.
- Version chỉ publish `dev`; production giữ nguyên.

## Kết quả 16/09/2026

- ✅ `22 passed` cho policy, bridge/WAL/redaction, evaluate, đăng ký TEST và safety gate của
  worker chỉ-TEST.
- ✅ Đánh giá hành vi thật qua model đạt `5/5`; báo cáo có manifest hash tại
  `.artifacts/AG-SOCIAL-LISTENING-TEST-evaluation.json`.
- ✅ Manifest parse được; 6 skills; catalog có 6 tài liệu `approved_for_dev` và 4 transcript
  `excluded`.
- ✅ Tạo `AG-SOCIAL-LISTENING-TEST` qua self-service owner, schema/token riêng; v3 chỉ publish
  `dev`, model `gpt-5.6-terra`, đúng 6 skill có hướng dẫn, gắn Codex owner, không gắn Lark.
- ✅ `MARK-03`: web chat đi đủ Chat API → job queue → worker local → `brain.reply` →
  reply/complete. Năm Golden job `1938`–`1942` và smoke v3 đều trả lời thành công; dashboard
  chuyển `health: ok`.
- ✅ `MARK-06` e2e: yêu cầu ghi Base và gửi Marketing bị từ chối; Mark chỉ soạn nội dung để
  người có quyền tự làm.
- ✅ Web `user_ref` dạng email không còn bị gửi nhầm vào Lark Contact API; smoke `job-1945`
  trả `READY FIX`, log không còn HTTP 400.
- ✅ 5 ca `mark_social_listening` đã active trên Golden của Platform và cả 5 đã được chính TEST
  worker trả lời đạt tiêu chí qua web queue. Chưa ghi nhận regression run vì console chỉ cho tạo
  case, còn `POST /v1/regression/run` cần cửa quản trị server.
- ✅ Tạo cold standby `AG-MARK-TRAN-BACKUP`: deactivated, dev v4, 6 skills, Codex; không Lark,
  không ingress, không prod.
- ◐ `MARK-05` mới đạt phần version/instruction; knowledge vẫn bằng 0. Upload 6 file nghiên cứu
  lên server bị chặn an toàn do nội dung HAPAS/MATE MADE nhạy cảm, chờ owner xác nhận rõ.
- ⏳ `MARK-04` e2e mất kết nối, `MARK-10` AG-EVAL server-side và `MARK-14` Lark/web chưa chạy.
