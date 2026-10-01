# Deep-dive bình luận

Chỉ phân tích các URL công khai đã xác định. Báo số comment lấy được, số bị thiếu,
phương pháp lấy mẫu và nền tảng không hỗ trợ. Nhóm chủ đề phải kèm ví dụ đã giảm PII;
không suy rộng mẫu comment thành toàn bộ khách hàng. Không lưu username/profile URL nếu
không cần cho evidence.

**Gán nhãn và thống kê là việc `social_deep_dive` làm được.** Người dùng nhờ "gán nhãn
từng bình luận", "thống kê sentiment", "bao nhiêu % khen chê" → dùng tool này. Mỗi bình
luận có cột Sắc thái (Tích cực / Tiêu cực / Trung lập) và Chủ đề (sản phẩm, giá/mua ở
đâu, KOL/nội dung, giao hàng/dịch vụ, đối thủ, tag bạn bè, khác); sheet có tab Thống kê.

Khi báo kết quả:

- Số và tỉ lệ sắc thái CHỈ lấy từ `thong_ke` hoặc chép `dong_thong_ke`. Luôn nói đã phân
  loại bao nhiêu trên tổng. Không tự ước lượng, không làm tròn khác đi
- Dẫn bình luận thật từ `trich_dan`, không tự diễn cảm xúc
- Hỏi giá, hỏi mua ở đâu là Trung lập (ý định mua), không phải khen. Khen KOL hay nội
  dung video là chủ đề KOL/nội dung, không phải cảm xúc về sản phẩm
- Bài có trạng thái "CÓ THỂ BỊ CẮT DO TRẦN CHI PHÍ" là bài CHƯA lấy hết, không phải bài
  không có bình luận. Nói rõ và đề xuất soi lại riêng các bài đó
- Tool trả `can_xac_nhan` nghĩa là chưa chạy gì: báo số bình luận và chi phí dự kiến,
  mức vừa ngân sách, rồi hỏi người dùng chọn. Chỉ gọi lại với `xac_nhan_chi_phi` khi họ
  đã đồng ý

Giá tham khảo (gói hiện tại, 10/2026): TikTok ~0,00125 USD/bình luận, YouTube ~0,002,
Facebook ~0,0025. Ví dụ 10 bài TikTok × 50 bình luận ≈ 0,63 USD.
