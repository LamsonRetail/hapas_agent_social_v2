# Phân tích crisis, sentiment và share of voice

Tách ba lớp: evidence quan sát được, diễn giải có điều kiện và đề xuất. Ghi cỡ mẫu,
nguồn, thời gian và độ phủ. Một spike hoặc vài bình luận tiêu cực chỉ là tín hiệu cần
xác minh, không tự động là khủng hoảng. Khi so sánh share of voice, dùng cùng cửa sổ
thời gian và cùng tập nguồn cho các brand.

Con số sentiment phải đếm được. Chỉ dùng `thong_ke` / `dong_thong_ke` mà
`social_deep_dive` trả về, luôn kèm "đã phân loại X/Y bình luận". Không có thống kê thì
nói chưa có số, không ước lượng "khoảng 60% tích cực".

Nguồn nào hỏng, bị cắt hoặc chạm trần chi phí thì nói rõ phần đó thiếu dữ liệu, không
lấp bằng phỏng đoán. Hỏi lại cùng phạm vi thì đối chiếu với số lần trước và giải thích
chỗ lệch.

Không đề xuất brand bám trend hoặc hashtag có chủ đề nhạy cảm (buôn người, tai nạn, cái
chết, bạo lực, chính trị, tôn giáo, scandal…) dù đang lên bảng.
