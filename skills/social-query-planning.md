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

Khoảng thời gian tính tới HÔM NAY, không bao giờ gồm ngày chưa tới:

- "tuần này" = từ Thứ 2 tuần này tới hôm nay
- "tuần qua / tuần trước / 7 ngày" = 7 ngày gần nhất tính tới hôm nay
- "tháng này" = từ ngày 1 tới hôm nay

Báo kết quả theo đúng khoảng đã quét, không theo khoảng người dùng gọi tên.

Không tự mở rộng sang dữ liệu riêng tư hoặc nguồn cần đăng nhập.
