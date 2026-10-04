# Phân tích quảng cáo đối thủ

Chọn nguồn theo nền tảng quảng cáo:

- **Facebook, Instagram, Messenger, Threads** → Meta Ad Library (`fb_ads_library`, miễn
  phí). Xác nhận brand hoặc page ID, quốc gia, trạng thái active/all và khoảng quan sát.
  Báo library ID, ngày bắt đầu, creative/copy quan sát được và thời điểm tra cứu
- **TikTok** → Top Ads của TikTok Creative Center (`tiktok_top_ads`, TỐN TIỀN, khoảng
  0,003 USD mỗi ad). Tìm theo từ khoá (brand, sản phẩm, chữ trong ad) và/hoặc ngành
  (thời trang, túi xách, trang sức, nước hoa…), kỳ 7/30/180 ngày, xếp theo CTR hoặc likes

Không suy ra spend, targeting hoặc hiệu quả nếu nguồn không cung cấp.

**TikTok Top Ads — trước khi chạy:** gọi với `chi_uoc_tinh`=true (miễn phí), nêu phạm vi
(từ khoá hoặc ngành · kỳ · xếp theo · số ads) và chi phí ước tính rồi hỏi "Chạy nhé?".
Chỉ chạy khi người dùng đồng ý.

**TikTok Top Ads — khi báo kết quả, luôn nói ba điều:**

- Đây là tập quảng cáo TikTok xếp hạng hiệu quả cao nhất của thị trường, KHÔNG phải mọi
  quảng cáo một đối thủ đang chạy. Brand không có trong kết quả không có nghĩa là brand
  không chạy ads TikTok
- CTR và mức chi phí là mức TƯƠNG ĐỐI do TikTok xếp, không phải CTR thật hay số tiền đã
  chi. Không quy ra ngân sách của đối thủ
- Link video MP4 hết hạn sau 24–48 giờ; trang ad trên Creative Center thì còn. Cần giữ
  video thì tải ngay

Nguồn chính hỏng thì tool tự chuyển sang nguồn dự phòng: nói rõ, và nói nếu lọc ngành đã
bị nới ra ngành cha (vd "túi xách" thành "thời trang và phụ kiện").
