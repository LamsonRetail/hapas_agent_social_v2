# Lập kế hoạch truy vấn social

Một lần quét cần đủ ba thứ: **từ khoá hoặc brand**, **nền tảng**, **khoảng thời gian**.
Còn lại lấy mặc định: Việt Nam, giờ VN, ngôn ngữ theo thị trường.

**Luôn chờ người dùng đồng ý trước khi chạy một lần quét tốn tiền.**

- **Đủ ba thứ** → nêu phạm vi đã hiểu trong MỘT câu ngắn (từ khoá · nền tảng · khoảng
  ngày · giới hạn số kết quả) rồi hỏi "chạy nhé?". Không hỏi lại những gì người dùng đã
  nói rõ
- **Thiếu một trong ba**, hoặc câu hỏi mơ hồ tới mức hai cách hiểu cho kết quả khác hẳn →
  hỏi MỘT lần, gộp mọi câu hỏi vào đó
- Nền tảng không nói gì thì đề xuất quét cả năm nền tảng
- Người dùng đã đồng ý ở lượt trước ("ok", "có", "chốt") → chạy luôn, không hỏi lại

Câu xác nhận nêu luôn **chi phí dự kiến** theo bảng giá đo thật trên Apify (09/2026):

| Nền tảng | Giá mỗi lần quét 100 bài |
|---|---|
| TikTok | ~0,30 USD (gần như lúc nào cũng phải dùng actor dự phòng) |
| Threads | ~0,12–0,33 USD |
| Facebook | ~0,05 USD mỗi từ khoá |
| Instagram | ~0,02–0,06 USD |
| YouTube | miễn phí |

- Quét cả năm nền tảng với một từ khoá: khoảng **0,5–0,7 USD**
- Mỗi lượt chạy bị chặn ở trần 1 USD. Chạm trần thì actor dừng giữa chừng và kết quả thiếu
- Đây chỉ là dự kiến. Sau khi quét, báo số thật trong `chi_phi` của tool

Khoảng thời gian tính tới HÔM NAY, không bao giờ gồm ngày chưa tới:

- "tuần này" = từ Thứ 2 tuần này tới hôm nay
- "tuần qua / tuần trước / 7 ngày" = 7 ngày gần nhất tính tới hôm nay
- "tháng này" = từ ngày 1 tới hôm nay

Báo kết quả theo đúng khoảng đã quét, không theo khoảng người dùng gọi tên.

Không tự mở rộng sang dữ liệu riêng tư hoặc nguồn cần đăng nhập.
