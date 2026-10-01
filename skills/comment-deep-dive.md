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
- Chủ agent đặt trần CỨNG cho MỖI lần bóc: trần bình luận (mặc định 300, 50–3000) và trần
  chi phí (mặc định 0,5 USD, 0,1–5). Tổng tiền có thể bị tính của cả lần bóc không bao
  giờ vượt trần chi phí; mỗi lượt chạy YouTube/Facebook phải giữ tối thiểu 0,5 USD trong
  trần đó, nên trần 0,5 USD chỉ đủ MỘT lượt (~225 bình luận YouTube). Trong trần, người
  dùng xin bao nhiêu bình luận/bài cũng được, tối đa 1000/bài
- Tool trả `vuot_tran` nghĩa là chưa chạy gì: nói yêu cầu vượt trần, chép câu `goi_y`
  ("trong trần này bóc được tối đa N bình luận/bài cho M bài"), đề xuất giảm bớt hoặc
  nhờ chủ agent nâng "Trần bình luận" / "Trần chi phí bóc bình luận" ở Console → Năng
  lực. Không có cách chạy vượt trần

Giá tham khảo (gói hiện tại, 10/2026): TikTok ~0,00125 USD/bình luận, YouTube ~0,002,
Facebook ~0,0025. Ví dụ 10 bài TikTok × 50 bình luận ≈ 0,63 USD.
