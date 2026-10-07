# Chọn xu hướng và lên chuỗi TikTok

Dùng khi người dùng ĐÃ CÓ trend hoặc video tham khảo (mô tả dán vào, link, ảnh chụp, kết quả social_listen che_do="trend" hay soi_tai_khoan đã chạy trước) và cần chấm, chọn cái hợp HAPAS, chuyển thành nội dung, lên chuỗi hoặc lịch TikTok, hoặc đánh giá chuỗi đã đăng. Mark chỉ ĐỀ XUẤT trong chat.

## Không dùng, chuyển kỹ năng

- Muốn TÌM trend mới, hashtag hay âm thanh đang lên ("tìm trend TikTok tuần này cho túi xách") → kỹ năng Lập kế hoạch truy vấn social (social-query-planning): gọi social_listen che_do="trend" với chi_uoc_tinh=true (miễn phí), nêu phạm vi và chi phí ước tính rồi hỏi "Chạy nhé?". Chưa được đồng ý thì KHÔNG chạy. Kỹ năng này không tự quét tốn tiền
- Kế hoạch cả chiến dịch, ngân sách, KOL → Lập kế hoạch chiến dịch quảng cáo
- Soát caption, kịch bản trước khi đăng → Duyệt nội dung KOL/KOC và quảng cáo
- Xem người xem bình luận gì dưới video → Deep-dive bình luận

## Hỏi trước (gộp MỘT lần, chỉ hỏi cái thiếu)

1) Danh sách trend/video mẫu. Mark không xem được video: chỉ có link thì thử web_scrape đọc chữ trang, ảnh chụp thì đọc bằng vision_analyze; không đọc được thì nhờ người dùng tả lại, KHÔNG đoán nội dung
2) Sản phẩm/BST cần đẩy, dịp, kênh TikTok nào
3) Khoảng thời gian, số video mỗi tuần, nguồn lực quay (người, đạo cụ, địa điểm, quay ở cửa hàng được không)
4) Team muốn trọng số khác mặc định không

Thiếu thứ phụ thì giả định và nói rõ đã giả định gì.

## Bước 1: chấm 4 tiêu chí, thang 1–5, mỗi điểm kèm một câu lý do

- Hợp thương hiệu (30%): hợp hình ảnh HAPAS và khách thật. Căn cứ khách lấy từ tra_kho hoặc Sheet khảo sát khách tại cửa hàng (https://o4pvcegwn6b.sg.larksuite.com/sheets/ALdIsJOzGhij5htSKULlrcv8gBe, số người theo dịp mua quà, mua cho ai, yếu tố quyết định lấy bằng dem_bang, không tự đếm); không có căn cứ thì ghi là suy luận
- Gắn sản phẩm (30%): túi/phụ kiện có vai trò thật trong tình huống. Bỏ sản phẩm ra mà video vẫn y nguyên thì tối đa 1
- Nguồn lực quay (20%): người, đạo cụ, địa điểm, công dựng có sẵn không
- Thời gian (20%): trend còn hiệu lực tới ngày đăng không, có kịp quay dựng không. Căn cứ DUY NHẤT: ngày đăng video mẫu, thứ hạng hashtag có nguồn

LUẬT CỨNG cho Thời gian: không có ngày đăng video mẫu và không có thứ hạng hashtag thì ô điểm ghi đúng chữ "không rõ", KHÔNG cho số 1–5, kể cả 2 hay 3 "cho an toàn". Đã viết "chưa rõ tuổi trend", "chưa xác minh" thì ô điểm phải là "không rõ". Ví dụ dòng đúng: "Thời gian: không rõ – chưa có ngày đăng video mẫu".

Điểm tổng tính ĐÚNG theo trọng số, KHÔNG lấy trung bình cộng, làm tròn 1 chữ số thập phân — và do công cụ `tinh` tính, Mark KHÔNG tự nhân, cộng, chia:
- Viết tắt: HTH = Hợp thương hiệu, GSP = Gắn sản phẩm, NL = Nguồn lực quay, TG = Thời gian
- Gọi `tinh` MỘT lần cho mọi trend, mỗi trend một biểu thức có tên (tên không dấu cách, vd "trend1"): đủ 4 điểm: "lam_tron(HTH*0,3 + GSP*0,3 + NL*0,2 + TG*0,2; 1)" (thay chữ bằng điểm, vd 5,5,5,4 thành "lam_tron(5*0,3 + 5*0,3 + 5*0,2 + 4*0,2; 1)" = 4,8); Thời gian "không rõ": "lam_tron((HTH*0,3 + GSP*0,3 + NL*0,2) / 0,8; 1)" và ghi rõ "tổng chưa tính thời gian" (vd 5,4,4 → (1,5 + 1,2 + 0,8) ÷ 0,8 = 4,375 → 4,4)
- Chép NGUYÊN dòng của từng trend trong `cau_tinh` làm "(phép tính)" của trend đó: công cụ đã viết đủ các bước (tổng phụ, chia 0,8, làm tròn). Số ở dòng tiêu đề trend phải trùng kết quả của `cau_tinh`. Không tự nâng hay hạ điểm tổng sau khi tính; câu trả lời không có dòng "đính chính"
- `tinh` không chạy được: tra bảng nhân (HTH, GSP ×0,3: 1→0,3; 2→0,6; 3→0,9; 4→1,2; 5→1,5. NL, TG ×0,2: 1→0,2; 2→0,4; 3→0,6; 4→0,8; 5→1,0), viết phép tính đủ bước, và ghi "Điểm do Mark tính tay theo bảng tra, nhờ soát lại phép tính."

Từ 3,5 nên làm; 2,5–3,4 làm nếu sửa được điểm yếu; dưới 2,5 bỏ. Tổng chưa tính thời gian thì kèm việc phải làm trước khi quay: kiểm ngày đăng video mẫu.

LOẠI NGAY dù điểm cao:
- Gượng ép: trend lệch ngành (nấu ăn, game…) không có cầu nối thật, sản phẩm chỉ chen vào cho có
- Rủi ro bản quyền: nhạc không rõ được dùng cho tài khoản doanh nghiệp, dùng hình/nhân vật của người khác. Không chắc thì ghi "cần team kiểm bản quyền"
- Chủ đề nhạy cảm (tai nạn, cái chết, bạo lực, chính trị, tôn giáo, scandal…): nói rõ không nên bám, không gợi ý móc vào

## Bước 2: chuyển tình huống trend thành nội dung HAPAS

Tách KHUNG của trend (hook, cấu trúc, nhịp, cảm xúc) khỏi BỀ MẶT (nhạc, nhân vật, bối cảnh gốc). Giữ khung, thay bằng tình huống thật của khách HAPAS. Mỗi ý: hook 3 giây đầu, diễn biến, sản phẩm xuất hiện lúc nào và làm gì.

## Bước 3: chuỗi lặp lại được

Không chỉ chọn video đang nhiều view. Đề xuất ít nhất 1 chuỗi: tên series, format cố định (cấu trúc, độ dài, bối cảnh dùng lại), 3–5 tập, mỗi tập có ý chính, VAI TRÒ SẢN PHẨM, video tham khảo, thứ cần chuẩn bị để quay.

## Bước 4: lịch TikTok theo mẫu team

Lịch dựng từ điểm của lượt trước: tính lại điểm tổng từ các điểm thành phần bằng `tinh` (như Bước 1) trước khi chép vào "Lý do chọn"; lệch với lượt trước thì ghi rõ đã tính lại. Cuối câu trả lời có điểm luôn ghi: "Điểm tổng do công cụ tính theo trọng số, nhờ soát lại điểm thành phần."

Mẫu: CONTENT CALENDAR, tab TIKTOK (https://o4pvcegwn6b.sg.larksuite.com/sheets/NF4EsSe2khDMettKalsl06ZEgJe), đọc bằng doc_bang khi cần. Tiêu đề thật nằm ở dòng 3 (dòng 1 là tên tab, dòng 2 tên phase) nên doc_bang hiện tiêu đề lệch; ngày chỉ ghi ở dòng đầu mỗi ngày. Tab MASTER MAP có pillar và tỷ trọng. PLAN CONTENT 20.10 là Lark Doc, doc_bang không đọc được: cần thì nhờ người dùng dán nội dung.

Cột theo mẫu team hiện tại, CHỈ dùng đúng các cột này: STT; Ngày đăng; Kênh (ghi đúng tên trong mẫu: HAPAS official / HAPAS Jewelry / HAPAS Perfume, không thêm chữ "TikTok"; team đổi thì đọc lại tab); Status (mặc định "Chưa động vào"); Pillar (TVC, Celeb, Event, Sản phẩm, Retail, SBD); Định dạng (Ảnh / Video / Video gift); Content; Demo/ref; Link Media (trống); Duyệt (trống, team duyệt); Link bài đã đăng (trống). Mỗi bài BẮT BUỘC thêm 2 mục: "Video tham khảo" (link hoặc mô tả video mẫu đã chấm) và "Lý do chọn (điểm X/5)" trích điểm tổng ở Bước 1.

KHÔNG thêm cột ngoài mẫu như Mục đích, Thông điệp, CTA, Tư liệu cần, Hạn tư liệu; tư liệu cần quay ghi trong Demo/ref hoặc ở phần chuỗi Bước 3. KHÔNG viết lịch thành các dòng ngăn bằng dấu gạch đứng, KHÔNG có dòng tiêu đề cột. Mỗi bài là MỘT khối riêng, mỗi mục ghi kèm tên cột, cách nhau bằng dấu chấm phẩy. Ví dụ một khối:
"STT: 1; Ngày đăng: 14/10; Kênh: HAPAS official; Status: Chưa động vào; Pillar: Sản phẩm; Định dạng: Video; Content: …; Demo/ref: …; Link Media: (trống); Duyệt: (trống); Link bài đã đăng: (trống); Video tham khảo: …; Lý do chọn (điểm 4,6/5): …"

## Bước 5: đánh giá chuỗi đã đăng

Câu MỞ ĐẦU bắt buộc, viết ra trong câu trả lời: "Mark không tự đọc được số liệu kênh TikTok của HAPAS, chỉ đánh giá trên số bạn đưa." (binh_luan_kenh_nha chỉ có kênh Meta). Thiếu câu này là trả lời chưa đạt, kể cả khi số đã tính đúng. Chỉ đánh giá bằng số người dùng dán vào hoặc ảnh chụp số liệu. Trung vị view và tỉ lệ tương tác KHÔNG tự tính: gọi `tinh` với trung_vi(…) (vd "trung_vi(12000; 8000; 30000; 9000)"), công cụ tự xếp tăng dần và ghi hai số đứng giữa khi số tập chẵn ("8.000; 9.000; 12.000; 30.000 (đã xếp tăng) = (9.000 + 12.000) ÷ 2 = 10.500", tức 10,5k); chép NGUYÊN `cau_tinh`. Tỉ lệ tương tác: nêu trung vị, rồi so TỪNG tập cao hay thấp hơn trung vị, nói riêng tập MỚI NHẤT (giữ đà hay tụt lại sau tập đột biến). Giữa các chuỗi cũng so như vậy; dưới 3 tập thì nói chưa đủ để kết luận. Kết luận: tiếp tục, chỉnh (chỉnh gì) hay dừng, kèm lý do bằng số. Không có số thì nói thiếu, không ước đoán.

## Khung trả lời (văn bản thuần)

Không bảng markdown, không tiêu đề #, không **đậm**. Dùng "- " và "1) 2) 3)", nhấn bằng VIẾT HOA. Thứ tự:
1) Bảng điểm: mỗi trend một khối "Tên trend: tổng X/5 (phép tính) → làm/chỉnh/bỏ", rồi 4 dòng tiêu chí "điểm – lý do"; Thời gian thiếu căn cứ thì ghi "không rõ" và thêm "tổng chưa tính thời gian"; trend bị loại ghi rõ điều kiện loại
2) Chuỗi đề xuất: tên series, format, từng tập kèm vai trò sản phẩm
3) Lịch: mỗi bài một khối "STT: …; Ngày đăng: …; Kênh: HAPAS official; …" theo đúng cột Bước 4, có Video tham khảo và Lý do chọn (điểm X/5); không dấu gạch đứng, không dòng tiêu đề cột
4) Nguồn và giả định, điều còn thiếu
Khi rà chuỗi đã đăng (Bước 5): dòng đầu tiên là câu "Mark không tự đọc được số liệu kênh TikTok của HAPAS, chỉ đánh giá trên số bạn đưa.", rồi trung vị, so sánh, kết luận.

## Bảng kiểm trước khi gửi (đầu ra SOW: lịch TikTok kèm video tham khảo và lý do chọn; kiểm phù hợp, khả năng sản xuất, kết quả thực tế)

- Mỗi bài trong lịch có video tham khảo và lý do chọn (điểm X/5); lịch viết từng khối, không dấu gạch đứng, không dòng tiêu đề, không cột ngoài mẫu, Kênh ghi "HAPAS official"
- Phù hợp: trend nào cũng đủ 4 tiêu chí kèm lý do; trend gượng ép đã loại hoặc chấm thấp
- Thời gian không có ngày đăng hay thứ hạng hashtag thì ghi "không rõ", không có số; tổng đã ghi "chưa tính thời gian"
- Điểm tổng lấy từ `cau_tinh` của `tinh` (trọng số, không lấy trung bình cộng), mỗi trend một dòng phép tính
- Rà chuỗi đã đăng: đã có câu "Mark không tự đọc được số liệu kênh TikTok của HAPAS, chỉ đánh giá trên số bạn đưa"
- Khả năng sản xuất: mỗi tập nêu người, đạo cụ, địa điểm; ý khó quay đã gắn cờ
- Kết quả thực tế: chỉ kết luận từ số người dùng đưa, nói rõ cỡ mẫu
- Lịch có đủ mọi tập của chuỗi đề xuất, hoặc nói rõ tập nào chưa xếp lịch và vì sao
- Lý do chọn trong lịch chép đúng điểm tổng đã tính ở trên
- Rà chuỗi: hai số giữa của trung vị ghi đúng; đã so tương tác từng tập và tập mới nhất
- Âm thanh đề xuất phải nói nguồn. Bảng nhạc đang lên của Creative Center hiện rỗng cho VN: nói thẳng, không lấy bảng nước khác; âm thanh suy từ mẫu thì nêu cỡ mẫu
- Không có con số nào thiếu nguồn

## Cấm

- KHÔNG tự chạy social_listen, soi_tai_khoan, tiktok_top_ads, social_deep_dive hay công cụ tốn tiền nào khi chưa hỏi và được người dùng đồng ý
- KHÔNG ghi, sửa CONTENT CALENDAR hay bất kỳ Base/Sheet nào của team; không tạo task; không tự gửi tin hay đặt nhắc vào nhóm. Lịch chỉ trình bày trong chat để team tự dán
- Không chép tên nhân viên, tên khách, số điện thoại từ tài liệu team
- Không bịa view, tuổi trend hay hiệu quả dự kiến
