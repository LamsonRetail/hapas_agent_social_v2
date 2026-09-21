# Gắn một external agent vào LSR Agent Platform

Bộ tài liệu này rút ra từ việc gắn **Mark Trần** (`AG-SOCIAL-LISTENING`) — agent chuyên
biệt đầu tiên chạy trên máy của đội nhưng chịu quản trị của platform. Viết để đội sau
không phải dò lại.

**External agent** = runtime chạy trên máy/hạ tầng của đội, không phải trên VM platform.
Platform giữ danh tính, hợp đồng quyền hạn, hàng đợi việc, kiến thức, telemetry và audit.
Đội giữ mã, mô hình, và công cụ riêng.

## Đọc theo thứ tự này

| | | |
| :-- | :--- | :--- |
| 1 | [Kiến trúc](01-kien-truc.md) | ai sở hữu gì · ba danh tính · hai cửa nhận việc |
| 2 | [Nhận vai](02-nhan-vai.md) | manifest → đánh giá → enroll → token |
| 3 | [Quyền hạn](03-quyen-han.md) | hợp đồng · stamp · chặn ở runtime · công tắc năng lực |
| 4 | [Nhận việc](04-nhan-viec.md) | ingress · vòng job · watchdog |
| 5 | [Kiến thức](05-kien-thuc.md) | nạp `.md` · nguồn Wiki · RAG |
| 6 | [Lên prod](06-len-prod.md) | version · eval gate · hồi quy |
| 7 | [**Chỗ dễ sai**](07-cho-de-sai.md) | **đọc trước khi gõ dòng nào** |
| 8 | [Danh sách kiểm](08-danh-sach-kiem.md) | bộ kiểm toán · checklist bàn giao |

Vội thì đọc **mục 7 trước**. Phần lớn thời gian của dự án này không mất vào việc viết mã,
mà vào việc tìm ra vì sao một thứ *trông như đã chạy* thật ra chưa chạy.

## Nguyên tắc xuyên suốt

Ba điều lặp đi lặp lại trong mọi mục dưới đây. Chúng không phải khẩu hiệu — mỗi điều đều
đổi bằng một sự cố thật.

**Một nguồn sự thật cho mỗi câu hỏi.** Câu "agent này được làm gì" phải có đúng một nơi
trả lời. Khi manifest nói một đằng, `lsr_policy` nói một nẻo, và prompt nói thứ thứ ba,
thì không ai sai rõ ràng — chỉ có agent hành xử khó hiểu. Đã xảy ra: prompt bảo Mark
không có quyền ghi Sheet suốt một ngày sau khi quyền đã được cấp.

**Hỏng thì phải kêu.** Loại lỗi nguy hiểm nhất ở đây không crash: bot vẫn trả lời trơn
tru nhưng dùng sai tài khoản, hoặc hàng đợi đứng im mà không dòng log nào báo. Mọi chốt
trong bộ này đều kèm câu hỏi *"nếu cái này hỏng, ai biết?"*

**Đo, đừng đoán.** Mỗi con số trong tài liệu này là số đo được, không phải ước lượng.
Chỗ nào chưa đo thì ghi rõ là chưa đo.

## Trạng thái Mark Trần khi viết tài liệu này

Số liệu dưới đây lấy từ lần chạy `scripts/kiem_toan.py` ngày 21/09/2026, không phải ước
lượng.

```
type            executive · out = reply · call_agent · write_data   (cố ý KHÔNG có send_message)
ingress         Lark qua gateway platform + web chat console
kiến thức       6 tài liệu nghiên cứu · 52 mẩu · 0 tài liệu Wiki (nguồn Wiki chờ sign-off ADR)
năng lực        6 công tắc, chặn thật ở runtime
version         v4 trên cả dev và prod, qua cổng hồi quy
kiểm toán       129/130 · test đơn vị 51 (agent) + 310 (platform)
```

Mục trượt duy nhất là `G5 · audit được ghi gần đây` — nó đo **hoạt động**, không đo lỗi:
chưa ai nhắn cho Mark trong 24 giờ qua. Để nguyên trong danh sách vì một sổ audit đứng
im quá lâu cũng là thứ đáng nhìn.

Còn treo: xoay app secret Lark · bốn việc ở [mục 8](08-danh-sach-kiem.md).

## Mã nguồn tham chiếu

Các đường dẫn trong bộ này trỏ tới hai repo:

- `hapas_agent_social` — phía agent (máy của đội)
- `lsr-agent-platform` — phía platform (VM)

Tệp đáng đọc nhất khi bắt tay vào việc:

| Tệp | Vai trò |
| :--- | :--- |
| [`lsr_policy.py`](../lsr_policy.py) | chốt chặn quyền tại điểm hội tụ tool |
| [`lsr_platform.py`](../lsr_platform.py) | vòng job · ngữ cảnh · telemetry |
| [`wiki_tu_dong.py`](../wiki_tu_dong.py) | nhịp nền theo dõi nguồn Wiki |
| [`scripts/kiem_toan.py`](../scripts/kiem_toan.py) | 130 mục kiểm, chạy lại được |
| [`manifest.json`](../manifest.json) | hợp đồng khai với platform |
