# Lập kế hoạch truy vấn social

Một lần quét cần đủ ba thứ: **từ khoá hoặc brand**, **nền tảng**, **khoảng thời gian**.
Còn lại lấy mặc định: Việt Nam, giờ VN, ngôn ngữ theo thị trường.

- **Đủ ba thứ** — người dùng nói rõ, hoặc vừa chốt ở lượt trước → CHẠY LUÔN. Mở đầu câu
  trả lời bằng một dòng phạm vi đã hiểu. Đừng hỏi lại để xác nhận điều người dùng vừa
  nói: mỗi câu "ok / có / chốt" là một lượt người dùng phải chờ mà không được gì thêm
- **Thiếu một trong ba**, hoặc câu hỏi mơ hồ tới mức hai cách hiểu cho kết quả khác hẳn →
  hỏi lại MỘT lần, gộp mọi câu hỏi vào đó
- Nền tảng không nói gì thì quét cả năm nền tảng, và nói rõ là đã quét cả năm

Khoảng thời gian tính tới HÔM NAY, không bao giờ gồm ngày chưa tới:

- "tuần này" = từ Thứ 2 tuần này tới hôm nay
- "tuần qua / tuần trước / 7 ngày" = 7 ngày gần nhất tính tới hôm nay
- "tháng này" = từ ngày 1 tới hôm nay

Báo kết quả theo đúng khoảng đã quét, không theo khoảng người dùng gọi tên.

Nêu giới hạn số kết quả mỗi lần quét. Không tự mở rộng sang dữ liệu riêng tư hoặc nguồn cần
đăng nhập.
