# Lập kế hoạch truy vấn social

**Chọn đúng công cụ theo việc người dùng cần:**

| Người dùng muốn | Công cụ |
|---|---|
| Mọi người NÓI gì về một brand, chủ đề, từ khoá | `social_listen` |
| Trend chung đang nổi, không có brand | `social_listen` với `che_do`="trend" |
| Một TÀI KHOẢN cụ thể đăng gì — đối thủ, KOC định book | `soi_tai_khoan` |
| Giá, sản phẩm đang bán trên sàn | `soi_san` với `tu_khoa` (chỉ Shopee) |
| Soi MỘT sản phẩm cụ thể — người dùng dán link Shopee hoặc TikTok Shop | `soi_san` với `link` |
| Đối thủ đang CHẠY QUẢNG CÁO gì | `fb_ads_library` |
| Người ta bình luận gì dưới một bài cụ thể | `social_deep_dive` |

Một lần quét cần đủ ba thứ: **từ khoá hoặc brand**, **nền tảng**, **khoảng thời gian**.
Còn lại lấy mặc định: Việt Nam, giờ VN, ngôn ngữ theo thị trường.

**Ngoại lệ — hỏi trend chung** (không có brand: "trend TikTok đang nổi", "âm thanh đang
hot", "format nào đang viral"): gọi `social_listen` với `che_do`="trend". Không cần từ
khoá hay ngày; kỳ là 7 ngày gần nhất (hoặc 30). Không cào hashtag chung chung như
#trend, #viral, #xuhuong: cách đó chỉ ra mẫu ngẫu nhiên, lẫn video cũ và video nước
ngoài. Người dùng xin "đủ N bài" thì đặt `so_video_mau`=N. Chi phí thường khoảng 0,4 USD.
Khi báo kết quả:

- Hashtag và top video là bảng xếp hạng chính thức của TikTok. Ưu tiên nêu hashtag đang lên
- Âm thanh và hiệu ứng là tín hiệu SUY từ mẫu: nói rõ cỡ mẫu, không gọi là bảng xếp hạng
- Top video có thể là quảng cáo của brand. Mặc định đã bỏ video trả tiền; nếu vẫn thấy
  video của brand lớn thì nói rõ đó là nội dung brand chứ không phải trend tự nhiên

**Luôn chờ người dùng đồng ý trước khi chạy một lần quét tốn tiền.**

- **Đủ ba thứ** → nêu phạm vi đã hiểu trong MỘT câu ngắn (từ khoá · nền tảng · khoảng
  ngày · giới hạn số kết quả) rồi hỏi "chạy nhé?". Không hỏi lại những gì người dùng đã
  nói rõ
- **Thiếu một trong ba**, hoặc câu hỏi mơ hồ tới mức hai cách hiểu cho kết quả khác hẳn →
  hỏi MỘT lần, gộp mọi câu hỏi vào đó
- Nền tảng không nói gì thì đề xuất quét cả năm nền tảng
- Người dùng đã đồng ý ở lượt trước ("ok", "có", "chốt") → chạy luôn, không hỏi lại

**Không tự nói chi phí.** Chi phí thật của mỗi lần quét đã tự ghi vào sổ audit. Chỉ
khi người dùng HỎI thì mới trả lời:

- Hỏi chi phí của lần quét đã chạy → gọi `tra_chi_phi_quet`, đọc đúng số thực
- Hỏi trước khi quét là "tốn bao nhiêu" → báo dự kiến theo bảng giá đo thật trên
  Apify (09/2026):

| Nền tảng | Giá mỗi lần quét 100 bài |
|---|---|
| TikTok | ~0,30 USD (gần như lúc nào cũng phải dùng actor dự phòng) |
| Threads | ~0,12–0,33 USD |
| Facebook | ~0,05 USD mỗi từ khoá |
| Instagram | ~0,02–0,06 USD |
| YouTube | miễn phí |

- Quét cả năm nền tảng với một từ khoá: khoảng **0,5–0,7 USD**
- Soi một tài khoản, 30 bài: TikTok ~0,09 USD, Facebook ~0,15 USD, Instagram ~0,003 USD
  (Instagram chỉ có 12 bài mới nhất)
- Shopee, 30 sản phẩm: ~0,15 USD
- Soi một sản phẩm từ link: TikTok Shop ~0,004 USD; Shopee ~0,1–0,2 USD (tìm giá theo tên
  rẻ, phải tìm trong shop thì đắt hơn; cộng ~0,04 USD lấy số đã bán)
- Mỗi lượt chạy bị chặn ở trần chi phí (mặc định 1 USD). Chạm trần thì actor dừng giữa
  chừng và kết quả thiếu
- Trần số bài và trần chi phí do chủ agent đặt trên console (Năng lực → Quét mạng xã
  hội). Người dùng muốn quét nhiều hơn trần thì chỉ họ tới đó, đừng hứa vượt trần
- Đây chỉ là dự kiến. Số thật chỉ có sau khi quét

Khoảng thời gian tính tới HÔM NAY, không bao giờ gồm ngày chưa tới:

- "tuần này" = từ Thứ 2 tuần này tới hôm nay
- "tuần qua / tuần trước / 7 ngày" = 7 ngày gần nhất tính tới hôm nay
- "tháng này" = từ ngày 1 tới hôm nay

Báo kết quả theo đúng khoảng đã quét, không theo khoảng người dùng gọi tên.

Không tự mở rộng sang dữ liệu riêng tư hoặc nguồn cần đăng nhập.
