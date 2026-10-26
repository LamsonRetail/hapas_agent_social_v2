-- Bảng BigQuery nhận bản sao kho lắng nghe `lang_nghe` (VPS Mark) — đợt 2, 14/10/2026.
--
-- NGƯỜI DUYỆT RỒI MỚI CHẠY (quy chuẩn lsr-bq-description-standard: không tự CREATE trên BigQuery).
-- Dataset mặc định `ganesha-381907.SOCIAL_LISTENING` (vùng asia-southeast1, cùng vùng với
-- PLATFORM_SYNC) — đổi tên/project thì sửa cả biến BQ_DATASET của dashboard.
--
-- Ghi: dịch vụ dashboard (`dashboard/dong_bo_bq.py`) MERGE theo khoá sau mỗi lượt quét và 6 giờ
-- một lần, bằng tài khoản dịch vụ CHỈ có quyền trên dataset này. Không đẩy `nguoi_xem`, `nhat_ky`
-- (email nội bộ) và các cột người sửa (`sua_boi`, `them_boi`).
-- Tạo bảng một lần bằng CREATE TABLE IF NOT EXISTS có đủ mô tả; MERGE không đổi mô tả.

CREATE SCHEMA IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING`
OPTIONS(location = 'asia-southeast1',
        description = 'Bản sao kho lắng nghe MXH (DB lang_nghe trên VPS Mark): dự án, nguồn theo dõi, bài đã giữ, số liệu theo ngày, lượt quét. Ghi bởi dashboard social.hapas.vn.');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.du_an`
(
  ma              STRING    OPTIONS(description='Mã dự án/brand, chữ gõ sau /theodoi (vd hapas). PK. Chữ thường, số, -, _; 2–40 ký tự (ràng buộc ở DB nguồn). Join: → nguon.du_an, bai.du_an, chi_so_ngay.du_an, luot_quet.du_an. Không NULL.'),
  ten             STRING    OPTIONS(description='Tên hiển thị của dự án (vd HAPAS), người quản lý đặt trên dashboard. Không NULL.'),
  tu_khoa         ARRAY<STRING> OPTIONS(description='Từ khoá dự án: bài từ nguồn không phải kênh nhà phải nhắc ít nhất một từ (so khớp bỏ dấu, không phân biệt hoa thường) mới được giữ. Mảng rỗng khi chưa đặt (khi đó Mark dùng tên dự án).'),
  tu_loai_tru     ARRAY<STRING> OPTIONS(description='Từ loại trừ: bài chứa một từ này bị bỏ cứng trước bước AI (vd hapasguitars). Mảng rỗng khi không đặt.'),
  boi_canh        STRING    OPTIONS(description='Mô tả brand đưa cho bước AI phân xử giữ/loại và gán sắc thái, chủ đề. Chuỗi rỗng khi chưa viết.'),
  thi_truong      STRING    OPTIONS(description='Mã nước 2 chữ (ISO 3166-1) của thị trường chính, mặc định VN. Dùng cho bước AI nhận bài ngoài thị trường. Từ 18/10/2026 dashboard không còn ô sửa: dự án mới luôn VN, dự án cũ giữ giá trị đã lưu.'),
  tran_usd_thang  NUMERIC   OPTIONS(description='Trần chi phí theo dõi mỗi tháng, USD (tiền Apify, không VAT). ≥ 0, không trần trên (ràng buộc nguồn), mặc định 5. Chỉ lượt kieu = theo_doi tính vào trần; trần mỗi lượt trên console platform vẫn áp dụng riêng.'),
  dang_bat        BOOL      OPTIONS(description='TRUE: dự án đang bật, /theodoi được quét. FALSE: tắt trên dashboard, /theodoi từ chối.'),
  tao_luc         TIMESTAMP OPTIONS(description='Thời điểm tạo dự án ở DB nguồn, UTC; giờ VN = DATETIME(tao_luc, "Asia/Ho_Chi_Minh").'),
  sua_luc         TIMESTAMP OPTIONS(description='Thời điểm sửa dự án gần nhất ở DB nguồn, UTC.'),
  hashtag         ARRAY<STRING> OPTIONS(description='Hashtag riêng của dự án, người quản lý nhập trên dashboard (từ 18/10/2026): đã bỏ #, bỏ dấu, chữ thường, chỉ a-z 0-9 _, bỏ trùng, giữ thứ tự gõ; tối đa 50 mục. Mark dùng cho tìm hashtag Instagram và feed hashtag TikTok. Mảng rỗng (mặc định; mọi dự án trước 18/10/2026): Mark suy hashtag từ tu_khoa như trước. Không dùng để lọc bài.'),
  dong_bo_luc     TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC. Chỉ để kiểm độ trễ đồng bộ.')
)
OPTIONS(description='''[Lớp] Raw
[Mục đích] Danh mục dự án/brand đang được lắng nghe và cấu hình lọc + thu thập (từ khoá, từ loại trừ, hashtag riêng, trần chi phí tháng).
[Grain] 1 dòng = 1 dự án
[Khoá] PK: ma | Join: ma → nguon.du_an, bai.du_an, chi_so_ngay.du_an, luot_quet.du_an
[Nguồn] Postgres lang_nghe.public.du_an trên VPS Mark (người quản lý sửa trên dashboard social.hapas.vn)
[Phạm vi] Mọi dự án lắng nghe | Kênh: Không có | Dữ liệu từ khi bật đợt 2 (sau 14/10/2026); cột hashtag từ 18/10/2026
[Đã xử lý] Bỏ cột sua_boi (email người sửa); thêm dong_bo_luc; dự án xoá ở nguồn thì xoá ở đây khi đồng bộ
[Refresh] Nạp lại toàn bảng bằng MERGE (có xoá dòng không còn ở nguồn) sau mỗi lượt quét và 6 giờ một lần
[Dùng khi] Gắn tên dự án, xem cấu hình từ khoá, hashtag và trần chi phí tháng
[Không dùng khi] Số bài, thảo luận → dùng SOCIAL_LISTENING.bai; chi phí đã tiêu → dùng SOCIAL_LISTENING.luot_quet
[Lưu ý] Bảng chứa cấu hình hiện hành, không giữ lịch sử thay đổi (lịch sử sửa nằm ở nhật ký trên VPS, không đẩy lên).''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.nguon`
(
  id              INT64     OPTIONS(description='Mã nguồn tự tăng ở DB nguồn. PK. Join: → bai.nguon_id. Không NULL.'),
  du_an           STRING    OPTIONS(description='Dự án của nguồn. FK → du_an.ma. Không NULL.'),
  nen_tang        STRING    OPTIONS(description='Nền tảng của nguồn. Giá trị (ràng buộc nguồn): tiktok, instagram, youtube, facebook, threads (từ 16/10/2026).'),
  dinh_danh       STRING    OPTIONS(description='Định danh nguồn đã chuẩn hoá: username TikTok/Instagram/Threads (chữ thường, không @), id kênh YouTube (UC…, giữ hoa thường) hoặc @handle, URL trang Facebook. Duy nhất trong cặp (du_an, nen_tang).'),
  ten             STRING    OPTIONS(description='Tên hiển thị của nguồn do người quản lý nhập. Chuỗi rỗng khi chưa nhập.'),
  link            STRING    OPTIONS(description='Link hồ sơ/kênh/trang của nguồn. Chuỗi rỗng khi chưa nhập.'),
  loai            STRING    OPTIONS(description='Loại nguồn. Giá trị (ràng buộc nguồn): kol (người ảnh hưởng), page (trang/fanpage), group (nhóm), bao (báo/trang tin), kenh_nha (kênh của chính brand — giữ mọi bài), khac.'),
  nhan            ARRAY<STRING> OPTIONS(description='Nhãn tự do người quản lý gắn để lọc (vd đối thủ, top Kompa). Mảng rỗng khi không gắn.'),
  trang_thai      STRING    OPTIONS(description='Giá trị: dang_theo_doi (được quét khi tới hạn), tam_dung (bỏ qua).'),
  chu_ky_ngay     INT64     OPTIONS(description='Chu kỳ quét, số ngày (1–30, ràng buộc nguồn). Nguồn tới hạn khi lần quét cuối cách đây ít nhất chu kỳ trừ 3 giờ.'),
  so_bai_moi_lan  INT64     OPTIONS(description='Số bài mới nhất lấy mỗi lần quét, bài (≥ 1, không trần trên). Instagram luôn trả tối đa 12 bài mới nhất (giới hạn của actor hồ sơ). Threads: actor lấy (và tính tiền) tối thiểu 10 bài mỗi tài khoản.'),
  them_qua        STRING    OPTIONS(description='Nguồn vào danh sách bằng cách nào. Giá trị: dashboard (người quản lý thêm), de_xuat (duyệt từ đề xuất của Mark), nhap_file.'),
  them_luc        TIMESTAMP OPTIONS(description='Thời điểm thêm nguồn, UTC.'),
  quet_cuoi       TIMESTAMP OPTIONS(description='Thời điểm quét thành công gần nhất, UTC. NULL khi chưa quét thành công lần nào.'),
  loi_cuoi        STRING    OPTIONS(description='Lỗi của lần quét hỏng gần nhất (vd tài khoản riêng tư, sai định danh). NULL khi lần quét gần nhất thành công hoặc chưa quét.'),
  loi_luc         TIMESTAMP OPTIONS(description='Thời điểm ghi loi_cuoi, UTC. NULL khi loi_cuoi NULL.'),
  dong_bo_luc     TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
CLUSTER BY du_an, nen_tang
OPTIONS(description='''[Lớp] Raw
[Mục đích] Danh sách nguồn mạng xã hội đang theo dõi của từng dự án, kèm chu kỳ quét và tình trạng quét gần nhất.
[Grain] 1 dòng = 1 nguồn (1 tài khoản/kênh/trang trên 1 nền tảng) của 1 dự án
[Khoá] PK: id | Join: du_an → du_an.ma; id → bai.nguon_id
[Nguồn] Postgres lang_nghe.public.nguon trên VPS Mark (người quản lý sửa trên dashboard; Mark chỉ ghi quet_cuoi, loi_cuoi, loi_luc)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (từ 16/10/2026) | Dữ liệu từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Bỏ cột them_boi (email người thêm); thêm dong_bo_luc; nguồn xoá ở nguồn thì xoá ở đây khi đồng bộ
[Refresh] Nạp lại toàn bảng bằng MERGE (có xoá dòng không còn ở nguồn) sau mỗi lượt quét và 6 giờ một lần
[Dùng khi] Đếm nguồn theo dõi theo dự án/nền tảng/loại; tìm nguồn lỗi hoặc lâu chưa quét; gắn loại nguồn cho bài
[Không dùng khi] Bài và tương tác của nguồn → dùng SOCIAL_LISTENING.bai; nguồn Mark đề xuất chưa duyệt → không có trên BigQuery, xem dashboard
[Lưu ý] Bài tìm theo từ khoá (bai.kieu_quet = tu_khoa) có thể không có nguồn (bai.nguon_id NULL).''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.bai`
(
  du_an           STRING    OPTIONS(description='Dự án bài thuộc về. Một phần PK (cùng khoa). FK → du_an.ma. Không NULL.'),
  khoa            STRING    OPTIONS(description='Khoá bài "<nền tảng>:<id bài>" (id lấy từ link; không bóc được id thì "h" + 16 ký tự băm SHA-1 của link). Một phần PK. Join: → chi_so_ngay.khoa (cùng du_an).'),
  nen_tang        STRING    OPTIONS(description='Nền tảng của bài. Giá trị: tiktok, instagram, youtube, facebook, threads (Threads cả lượt theo dõi lẫn tìm theo từ khoá từ 16/10/2026), web (Báo & Web — báo, diễn đàn, blog tìm qua Google, từ 16/10/2026).'),
  nguon_id        INT64     OPTIONS(description='Nguồn theo dõi đã cho ra bài. FK → nguon.id. NULL khi bài đến từ tìm theo từ khoá hoặc nguồn đã bị xoá.'),
  kieu_quet       STRING    OPTIONS(description='Bài vào kho bằng đường nào. Giá trị: theo_doi (lượt /theodoi quét nguồn), tu_khoa (lượt tìm theo từ khoá). Bài đã từng là theo_doi thì giữ theo_doi.'),
  link            STRING    OPTIONS(description='Link bài gốc trên nền tảng. Không NULL.'),
  tac_gia         STRING    OPTIONS(description='Tên hiển thị kênh/tài khoản đăng bài. Chuỗi rỗng khi nền tảng không trả.'),
  tai_khoan       STRING    OPTIONS(description='Username của tài khoản đăng (TikTok, Instagram, Threads); tên miền trang với web (vd cafef.vn). Chuỗi rỗng với YouTube và khi không có.'),
  followers       INT64     OPTIONS(description='Số người theo dõi tài khoản đăng lúc quét gần nhất, người. NULL khi nền tảng không trả (trang Facebook).'),
  dang_luc        TIMESTAMP OPTIONS(description='Thời điểm bài được đăng, UTC; giờ VN = DATETIME(dang_luc, "Asia/Ho_Chi_Minh"). Lượt theo dõi chỉ ghi bài đăng trong 35 ngày trước lúc quét.'),
  noi_dung        STRING    OPTIONS(description='Nội dung/caption bài (YouTube: tiêu đề — mô tả), cắt tối đa 1.000 ký tự. Chuỗi rỗng khi bài không có chữ.'),
  hashtag         STRING    OPTIONS(description='Hashtag của bài, không có dấu #, phân cách bằng ", ", tối đa 500 ký tự. Chuỗi rỗng khi không có.'),
  khop_tu_khoa    BOOL      OPTIONS(description='TRUE: nội dung/hashtag/tên kênh nhắc ít nhất một từ khoá dự án. FALSE: không nhắc (chỉ giữ khi nguồn là kenh_nha).'),
  sac_thai        STRING    OPTIONS(description='Sắc thái bài do bước AI gán. Giá trị: Tích cực, Tiêu cực, Trung lập. NULL khi AI chưa gán (hỏng, hết giờ hoặc bài chỉ được cập nhật số).'),
  chu_de          STRING    OPTIONS(description='Chủ đề bài do bước AI gán, theo 13 chủ đề của Mark (vd Chiến dịch & quảng cáo, Giá cả, Chất lượng sản phẩm, Khác). NULL khi AI chưa gán.'),
  ly_do_giu       STRING    OPTIONS(description='Vì sao bài được giữ: mã AI (brand, ad, product, ugc, other_market) hoặc kenh_nha / khop_tu_khoa khi giữ theo luật. NULL khi bài chỉ được cập nhật số.'),
  xem             INT64     OPTIONS(description='Lượt xem lúc đọc gần nhất, lượt. NULL khi nền tảng không trả (bài ảnh Instagram, nhiều bài Facebook).'),
  thich           INT64     OPTIONS(description='Lượt thích lúc đọc gần nhất, lượt. NULL khi không đọc được.'),
  binh_luan       INT64     OPTIONS(description='Số bình luận nền tảng báo lúc đọc gần nhất, bình luận (không phải số bình luận đã cào). NULL khi không đọc được. Thảo luận kiểu Kompa = 1 bài + binh_luan.'),
  chia_se         INT64     OPTIONS(description='Lượt chia sẻ lúc đọc gần nhất, lượt. NULL với YouTube và Instagram (nền tảng không công khai).'),
  thay_lan_dau    TIMESTAMP OPTIONS(description='Thời điểm Mark ghi bài vào kho lần đầu, UTC.'),
  cap_nhat_cuoi   TIMESTAMP OPTIONS(description='Thời điểm Mark cập nhật bài gần nhất (số liệu hoặc nhãn), UTC. Mốc đồng bộ của bảng này.'),
  luot_dau        INT64     OPTIONS(description='Lượt quét ghi bài lần đầu. FK → luot_quet.id. NULL khi lượt đó đã bị xoá ở nguồn.'),
  luot_cuoi       INT64     OPTIONS(description='Lượt quét cập nhật bài gần nhất. FK → luot_quet.id.'),
  ma_noi_dung     STRING    OPTIONS(description='Băm 16 ký tự nội dung đã chuẩn hoá khi ≥ 30 ký tự — các bài cùng mã là cùng nội dung (đăng lại nhiều trang, seeding); đếm bài khử trùng = COUNT(DISTINCT COALESCE(ma_noi_dung, khoa)). NULL khi quá ngắn.'),
  kieu_trang      STRING    OPTIONS(description='Loại trang của bài web. Giá trị: bao (báo/tạp chí), dien_dan (diễn đàn), blog, mxh_khac (LinkedIn, X, Lemon8…), khac (trang khác). NULL với bài mạng xã hội (nen_tang khác web).'),
  muc_nhac        STRING    OPTIONS(description='Mức nhắc brand trong bài web. Giá trị: tieu_de (từ khoá ở tiêu đề), chinh (≥ 3 lần trong thân bài), thoang (nhắc lướt 1–2 lần, vd bài liệt kê nhiều brand). NULL với bài mạng xã hội.'),
  la_pr           BOOL      OPTIONS(description='TRUE: bài web có dấu hiệu bài đặt/PR (thân bài dẫn link về miền của brand hoặc ghi "Ảnh/Nguồn: <brand>"). FALSE: không thấy dấu hiệu. NULL với bài mạng xã hội.'),
  ma_so_fb        STRING    OPTIONS(description='Id số ổn định của bài Facebook (5–25 chữ số): id bài actor trả (postId, post_id, post.id, feedbackId), không có thì bóc từ link (/posts/, /videos/, /reel/, /permalink/, story_fbid=). Dùng để nhận bản trùng: pfbid trong link và khoa đổi mỗi lượt cào (đo 17/10/2026). Không phải khoá (PK là du_an + khoa), không join bảng khác; không duy nhất (bản trùng cũ chưa gộp có thể cùng id). NULL với nền tảng khác, bài ghi trước 17/10/2026 chưa được quét lại (quét lại thì Mark điền), hoặc link pfbid mà actor không trả id.'),
  gio_hang        BOOL      OPTIONS(description='Chỉ TikTok: TRUE = video gắn giỏ TikTok Shop (KOC affiliate trên dashboard), FALSE = không gắn giỏ (KOC branding), theo từng video. Đọc từ tìm kiếm / hồ sơ TikTok (anchors không có shop, kể cả anchors trống = FALSE); feed hashtag chỉ báo được TRUE (không bao giờ trả anchor shop, đo 21/10/2026). NULL = chưa rõ: video chỉ thấy ở feed hashtag, nguồn không báo, hoặc nền tảng khác — không phải FALSE. TRUE không bị lần đọc sau hạ; bài trước 20/10/2026 điền bằng scripts/lang_nghe_nap_gio_hang.py.'),
  la_quang_cao    BOOL      OPTIONS(description='Chỉ TikTok: TRUE = TikTok đánh dấu video là quảng cáo (is_ads / isAd), FALSE = không. NULL = nguồn không báo hoặc nền tảng khác. Không dùng để tách KOC (tiêu chí là gio_hang).'),
  dong_bo_luc     TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
CLUSTER BY du_an, nen_tang
OPTIONS(description='''[Lớp] Raw
[Mục đích] Bài mạng xã hội liên quan tới dự án mà Mark đã giữ, kèm nhãn AI và tương tác mới nhất, để đếm thảo luận, nguồn nổi bật, sắc thái, chủ đề.
[Grain] 1 dòng = 1 bài × 1 dự án
[Khoá] PK: du_an + khoa | Join: du_an → du_an.ma; nguon_id → nguon.id; (du_an, khoa) → chi_so_ngay; luot_dau, luot_cuoi → luot_quet.id
[Nguồn] Postgres lang_nghe.public.bai trên VPS Mark; Mark ghi sau mỗi lượt /theodoi (Apify theo tài khoản, YouTube Data API) và lượt tìm theo từ khoá
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (nguồn theo dõi + tìm theo từ khoá từ 16/10/2026; trước đó chỉ từ social_listen), Báo & Web (nen_tang = web: báo, diễn đàn, blog tìm qua Google, từ 16/10/2026) | Bài đăng từ 17/09/2026: mỗi lượt quét giữ bài đăng trong 35 ngày trước lượt (từ khi bật đợt 2, 14/10/2026); bài đăng 17/09 → 14/10/2026 nạp từ raw đã trả tiền (từ 18/10/2026)
[Đã xử lý] Chỉ bài liên quan: nhắc từ khoá dự án (trừ kênh nhà), không chứa từ loại trừ, không bị AI loại; từ 18/10/2026 không có bài seeding affiliate (mặc định chỉ TikTok; tài khoản không phải kênh nhà, không mang tên brand, đăng ≥ 5 bài/ngày hoặc ≥ 20 bài/7 ngày với trung vị ≤ 2 bình luận và ≤ 15.000 lượt xem; bài tự có ≥ 10 bình luận vẫn giữ), bài tìm theo từ khoá ngoài thị trường VN (nội dung chữ nước khác hoặc kênh YouTube khai nước khác, không có dấu hiệu Việt; ca mơ hồ do AI phán) và bài chỉ đến từ đường hashtag (feed hashtag TikTok, Instagram hashtag) mà không gọi tên brand ở nội dung, hashtag, tên hay định danh chủ bài (tên brand gồm tag chiến dịch của dự án, trừ tag rộng như #quatang2010; trừ kênh nhà); khử trùng theo khoa; bài Facebook khử trùng thêm theo id số ma_so_fb, không có id thì theo chủ bài + phút đăng + nội dung (từ 17/10/2026); nội dung cắt 1.000 ký tự
[Refresh] MERGE theo du_an + khoa các dòng có cap_nhat_cuoi mới hơn mốc, sau mỗi lượt quét và 6 giờ một lần (lượt /theodoi theo lịch Giao việc trên console và theo Lịch quét tự động trên dashboard — mỗi N giờ, hằng ngày, hằng tuần hoặc liên tục trong chiến dịch, từ 15/10/2026)
[Dùng khi] Đếm bài, thảo luận (1 + binh_luan), nguồn nổi bật, sắc thái, chủ đề, từ khoá theo ngày đăng/nền tảng/dự án
[Không dùng khi] Tương tác theo từng ngày để vẽ tăng trưởng → dùng SOCIAL_LISTENING.chi_so_ngay; chi phí quét → dùng SOCIAL_LISTENING.luot_quet
[Lưu ý] Số liệu là lần đọc gần nhất, không phải cuối kỳ; bài YouTube được đọc lại số mỗi ngày trong 14 ngày đầu, nền tảng khác chỉ khi bài còn nằm trong N bài mới nhất của nguồn. Đây là mẫu theo nguồn đã chọn, không phải toàn bộ thảo luận trên mạng. MERGE không xoá dòng: bài seeding đã dọn ở Postgres (scripts/lang_nghe_loc_seeding.py) còn ở đây nếu đồng bộ bật trước khi dọn.''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.chi_so_ngay`
(
  du_an           STRING    OPTIONS(description='Dự án. Một phần PK. FK (cùng khoa) → bai.du_an.'),
  khoa            STRING    OPTIONS(description='Khoá bài "<nền tảng>:<id bài>". Một phần PK. FK (cùng du_an) → bai.khoa.'),
  ngay            DATE      OPTIONS(description='Ngày đọc số liệu theo giờ VN (GMT+7). Một phần PK.'),
  xem             INT64     OPTIONS(description='Lượt xem lũy kế lần đọc cuối trong ngày, lượt. NULL khi nền tảng không trả.'),
  thich           INT64     OPTIONS(description='Lượt thích lũy kế lần đọc cuối trong ngày, lượt. NULL khi không đọc được.'),
  binh_luan       INT64     OPTIONS(description='Số bình luận nền tảng báo, lũy kế lần đọc cuối trong ngày, bình luận. NULL khi không đọc được.'),
  chia_se         INT64     OPTIONS(description='Lượt chia sẻ lũy kế lần đọc cuối trong ngày, lượt. NULL với YouTube, Instagram.'),
  dong_bo_luc     TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
PARTITION BY ngay
CLUSTER BY du_an
OPTIONS(description='''[Lớp] Raw
[Mục đích] Tương tác lũy kế của từng bài theo ngày đọc, để vẽ tăng trưởng và tính phần tăng trong kỳ.
[Grain] 1 dòng = 1 bài × 1 dự án × 1 ngày đọc (giờ VN)
[Khoá] PK: du_an + khoa + ngay | Join: (du_an, khoa) → bai.(du_an, khoa)
[Nguồn] Postgres lang_nghe.public.chi_so_ngay trên VPS Mark; Mark ghi mỗi lần đọc số của bài (ghi đè trong cùng ngày)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Không xử lý; bản sao các cột số liệu
[Refresh] MERGE theo du_an + khoa + ngay các dòng có ngày từ (mốc lần trước − 1 ngày), sau mỗi lượt quét và 6 giờ một lần
[Dùng khi] Tăng trưởng lượt xem/bình luận theo ngày; phần tăng trong kỳ = giá trị ngày cuối − ngày đầu của bài
[Không dùng khi] Số liệu mới nhất của bài, nội dung, nhãn → dùng SOCIAL_LISTENING.bai
[Lưu ý] Số là LŨY KẾ, không phải phát sinh trong ngày; bài không được đọc ngày nào thì thiếu dòng ngày đó (không có dòng 0).''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.luot_quet`
(
  id              INT64     OPTIONS(description='Mã lượt quét tự tăng ở DB nguồn. PK. Join: → bai.luot_dau, bai.luot_cuoi.'),
  du_an           STRING    OPTIONS(description='Dự án của lượt. FK → du_an.ma.'),
  kieu            STRING    OPTIONS(description='Giá trị: theo_doi (lượt /theodoi quét nguồn, tính vào trần tháng), tu_khoa (lượt tìm theo từ khoá ghi vào kho; cả lượt nạp raw đã trả tiền bằng scripts/lang_nghe_nap_raw.py từ 18/10/2026, chi phí 0).'),
  ma_viec         STRING    OPTIONS(description='Mã việc nền của Mark (vd t10140830-ab12c), đối chiếu với /viec. nap-raw-<năm tháng ngày giờ phút> với lượt nạp raw (từ 18/10/2026). NULL khi lượt không chạy qua việc nền.'),
  job_id          STRING    OPTIONS(description='Mã job platform đã giao lượt (lịch run trên console). NULL khi lượt do Lịch quét tự động trên dashboard giao (không qua job platform) hoặc không lấy được.'),
  bat_dau         TIMESTAMP OPTIONS(description='Thời điểm bắt đầu lượt, UTC.'),
  ket_thuc        TIMESTAMP OPTIONS(description='Thời điểm kết thúc lượt, UTC. NULL khi lượt đang chạy.'),
  so_nguon        INT64     OPTIONS(description='Số nguồn lượt này xét, nguồn.'),
  so_nguon_loi    INT64     OPTIONS(description='Số nguồn không lấy được bài trong lượt, nguồn.'),
  bai_moi         INT64     OPTIONS(description='Số bài lần đầu vào kho trong lượt, bài.'),
  bai_cap_nhat    INT64     OPTIONS(description='Số bài đã có được cập nhật số liệu/nhãn trong lượt, bài.'),
  chi_phi_usd     NUMERIC   OPTIONS(description='Chi phí Apify THẬT của lượt, USD, không VAT: tổng usageTotalUsd đúng các run của lượt, đọc khi run cuối đã xong ≥ 45 giây; Mark đọc lại ~90 giây sau run cuối và NÂNG số nếu Apify ghi thêm phí sự kiện (chỉ nâng, không hạ; từ 17/10/2026 — lượt cũ hơn có thể thiếu phí ghi trễ). 0 khi lượt chỉ dùng YouTube Data API (miễn phí). Không âm.'),
  trang_thai      STRING    OPTIONS(description='Giá trị: dang_chay, xong (mọi nguồn được), mot_phan (một số nguồn lỗi), loi (không nguồn nào được hoặc bot dừng giữa chừng), da_huy.'),
  loi             STRING    OPTIONS(description='Tóm tắt lỗi của các nguồn hỏng, tối đa 500 ký tự. NULL khi không có lỗi.'),
  ghi_chu         STRING    OPTIONS(description='Ghi chú vận hành (vd hết ngân sách tháng, bot khởi động lại giữa lượt, nền tảng bỏ qua/lỗi kèm lý do) và phễu từng nền tảng của lượt tìm theo từ khoá, các câu nối bằng "; ". Tối đa 20.000 ký tự (từ 17/10/2026; trước đó 2.000 — lượt cũ có thể cụt), quá thì cắt và ghi dấu đã cắt ở cuối. NULL khi không có.'),
  dong_bo_luc     TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
CLUSTER BY du_an
OPTIONS(description='''[Lớp] Raw
[Mục đích] Lịch sử các lượt quét của kho lắng nghe: bao nhiêu nguồn, bao nhiêu bài, tốn bao nhiêu tiền, lỗi gì.
[Grain] 1 dòng = 1 lượt quét
[Khoá] PK: id | Join: du_an → du_an.ma; id → bai.luot_dau, bai.luot_cuoi
[Nguồn] Postgres lang_nghe.public.luot_quet trên VPS Mark; Mark mở lượt khi bắt đầu và đóng khi xong
[Phạm vi] Mọi dự án | Kênh: Không có | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Không xử lý; bản sao 1-1
[Refresh] MERGE theo id các dòng có max(bat_dau, ket_thuc) mới hơn mốc, sau mỗi lượt quét và 6 giờ một lần
[Dùng khi] Chi phí theo dõi theo tháng (SUM chi_phi_usd WHERE kieu = 'theo_doi', tháng theo giờ VN); tỉ lệ nguồn lỗi; số bài mới mỗi lượt
[Không dùng khi] Nội dung và tương tác bài → dùng SOCIAL_LISTENING.bai; cấu hình trần tháng → dùng SOCIAL_LISTENING.du_an
[Lưu ý] Tháng của ngân sách tính theo giờ VN: DATE_TRUNC(DATE(bat_dau, "Asia/Ho_Chi_Minh"), MONTH). Lượt kẹt dang_chay quá 3 giờ được đóng thành loi ở lượt sau.''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.binh_luan`
(
  du_an           STRING    OPTIONS(description='Dự án. Một phần PK. FK (cùng khoa_bai) → bai.du_an.'),
  khoa_bai        STRING    OPTIONS(description='Khoá bài chứa bình luận "<nền tảng>:<id bài>". Một phần PK. FK (cùng du_an) → bai.khoa.'),
  ma              STRING    OPTIONS(description='Mã bình luận trên nền tảng; không có thì "h" + 16 ký tự băm SHA-1 (tác giả, nội dung, thời điểm). Một phần PK.'),
  nen_tang        STRING    OPTIONS(description='Nền tảng. Giá trị: tiktok, instagram, youtube, facebook, threads.'),
  tac_gia         STRING    OPTIONS(description='Tên/username công khai của người bình luận trên nền tảng. Chuỗi rỗng khi không có.'),
  noi_dung        STRING    OPTIONS(description='Nội dung bình luận, tối đa 1.000 ký tự.'),
  thich           INT64     OPTIONS(description='Lượt thích bình luận lúc cào, lượt. NULL khi nền tảng không trả.'),
  tra_loi         INT64     OPTIONS(description='Số trả lời của bình luận lúc cào, bình luận. NULL khi nền tảng không trả.'),
  la_tra_loi      BOOL      OPTIONS(description='TRUE: dòng là trả lời của bình luận khác. FALSE: bình luận gốc.'),
  cua_thuong_hieu BOOL      OPTIONS(description='TRUE: do tài khoản của chính thương hiệu viết — không gán nhãn, loại khỏi sắc thái. FALSE: khách.'),
  dang_luc        TIMESTAMP OPTIONS(description='Thời điểm đăng bình luận, UTC (giờ VN = +7). NULL khi nền tảng chỉ trả thời gian tương đối.'),
  sac_thai        STRING    OPTIONS(description='Sắc thái AI/luật gán. Giá trị: Tích cực, Tiêu cực, Trung lập. NULL khi chưa gán hoặc bình luận của thương hiệu.'),
  chu_de          STRING    OPTIONS(description='Chủ đề bình luận (8 nhóm: Sản phẩm/chất lượng, Giá/mua ở đâu/ý định mua, KOL/nội dung, Giao hàng/dịch vụ, Đối thủ, Tag bạn bè, Minigame/bài dự thi, Khác). Minigame/bài dự thi = bài dự thi/lời chúc theo đề bài của brand, từ 16/10/2026. NULL khi chưa gán.'),
  luot_id         INT64     OPTIONS(description='Lượt quét cào bình luận gần nhất. FK → luot_quet.id.'),
  thay_lan_dau    TIMESTAMP OPTIONS(description='Thời điểm Mark ghi bình luận lần đầu, UTC.'),
  cap_nhat_cuoi   TIMESTAMP OPTIONS(description='Thời điểm cập nhật gần nhất ở DB nguồn, UTC. Mốc đồng bộ.'),
  loai            STRING    OPTIONS(description='Nhãn lọc. Giá trị: hop_le (thảo luận sạch, có sắc thái), it_noi_dung (chỉ dấu chấm/emoji/tag), spam (quảng cáo/lừa đảo/kéo khách, gồm spam affiliate dán mã), trung (cùng người cùng nội dung cùng bài), seeding (cùng nội dung từ ≥ 3 tài khoản trong 7 ngày), thuong_hieu (thương hiệu viết). Đếm thảo luận sạch: loai = hop_le.'),
  ly_do_loc       STRING    OPTIONS(description='Lý do lọc khi loai không phải hop_le (vd lien_ket_quang_cao, keo_khach, vay_tien, co_bac, viec_lam_mmo, cung_nguoi_cung_noi_dung, cung_noi_dung_nhieu_tai_khoan; affiliate_dan_ma, affiliate_hang_loat = spam mời dán mã giới thiệu vào Shopee). NULL khi hợp lệ.'),
  ma_noi_dung     STRING    OPTIONS(description='Băm 16 ký tự nội dung đã chuẩn hoá khi ≥ 40 ký tự — cùng mã từ ≥ 3 tài khoản trên ≥ 2 bài là seeding. NULL khi quá ngắn.'),
  link            STRING    OPTIONS(description='Link mở thẳng tới bình luận khi nền tảng có (Facebook, Instagram, Threads, YouTube); NULL thì dùng bai.link.'),
  ma_cha          STRING    OPTIONS(description='Mã bình luận cha khi dòng là trả lời (cùng khoa_bai). NULL với bình luận gốc.'),
  san_pham        STRING    OPTIONS(description='Món khách hỏi mua, chỉ có ở bình luận hỏi mua (AI gán cùng sắc thái/chủ đề, đọc cả nội dung bài; từ 17/10/2026). Giá trị: tui (túi xách, balo), vi (ví), nuoc_hoa (nước hoa), trang_suc (trang sức), set_qua (set/combo/hộp quà nhiều món), khac (món khác của brand), ngoai_brand (đồ không phải hàng của brand, vd quần áo người trong video mặc — dashboard không tính là ý định mua), chua_ro (không đoán được món). NULL khi không phải bình luận hỏi mua, chưa gán nhãn, gán trước 17/10/2026 chưa gán lại, hoặc loai khác hop_le.'),
  dong_bo_luc     TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
CLUSTER BY du_an, nen_tang
OPTIONS(description='''[Lớp] Raw
[Mục đích] Bình luận (và trả lời) dưới các bài đã giữ của dự án, kèm sắc thái và chủ đề AI gán — tiếng khách hàng.
[Grain] 1 dòng = 1 bình luận × 1 bài × 1 dự án
[Khoá] PK: du_an + khoa_bai + ma | Join: (du_an, khoa_bai) → bai.(du_an, khoa); luot_id → luot_quet.id
[Nguồn] Postgres lang_nghe.public.binh_luan trên VPS Mark; Mark cào sau mỗi lượt /theodoi (Apify comments scraper TikTok/Facebook/Instagram, Threads replies scraper, YouTube Data API)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (từ 16/10/2026) | Bài đăng trong 35 ngày; số bài và số bình luận mỗi bài theo cấu hình từng nền tảng (du_an.cau_hinh trên Postgres, 0 = cào hết); từ 15/10/2026
[Đã xử lý] Khử trùng theo ma; nội dung cắt 1.000 ký tự; mỗi dòng có nhãn lọc loai (spam/rác/trùng/seeding/thương hiệu) — chỉ hop_le được gán sắc thái/chủ đề
[Refresh] MERGE theo du_an + khoa_bai + ma các dòng có cap_nhat_cuoi mới, sau mỗi lượt quét và 6 giờ một lần
[Dùng khi] Đọc từng bình luận; tỷ lệ sắc thái, chủ đề bình luận của khách theo ngày; món khách hỏi mua (san_pham)
[Không dùng khi] Tổng bình luận nền tảng báo của bài → dùng SOCIAL_LISTENING.bai.binh_luan
[Lưu ý] Thảo luận sạch / sắc thái: lọc loai = 'hop_le'; Instagram chưa đăng nhập chỉ trả một phần, Threads chỉ trả lời cấp 1 (10–300 mỗi bài), bài rất lớn có thể thiếu (so bai.binh_luan để biết độ phủ).''');

-- Nâng cấp bảng đã tạo TRƯỚC đợt 2e (15/10/2026): CREATE … IF NOT EXISTS không thêm cột vào bảng
-- có sẵn, mà dong_bo_bq MERGE cả link + ma_cha — chạy khối này trước khi bật đồng bộ bản mới.
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.binh_luan`
  ADD COLUMN IF NOT EXISTS link STRING OPTIONS(description='Link mở thẳng tới bình luận khi nền tảng có (Facebook, Instagram, Threads, YouTube); NULL thì dùng bai.link.'),
  ADD COLUMN IF NOT EXISTS ma_cha STRING OPTIONS(description='Mã bình luận cha khi dòng là trả lời (cùng khoa_bai). NULL với bình luận gốc.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.nguon`
  ALTER COLUMN so_bai_moi_lan SET OPTIONS(description='Số bài mới nhất lấy mỗi lần quét, bài (≥ 1, không trần trên). Instagram luôn trả tối đa 12 bài mới nhất (giới hạn của actor hồ sơ). Threads: actor lấy (và tính tiền) tối thiểu 10 bài mỗi tài khoản.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.du_an`
  ALTER COLUMN tran_usd_thang SET OPTIONS(description='Trần chi phí theo dõi mỗi tháng, USD (tiền Apify, không VAT). ≥ 0, không trần trên (ràng buộc nguồn), mặc định 5. Chỉ lượt kieu = theo_doi tính vào trần; trần mỗi lượt trên console platform vẫn áp dụng riêng.');

-- Threads (16/10/2026): bảng đã tạo trước thì CREATE … IF NOT EXISTS không đổi mô tả — cập nhật
-- mô tả bảng/cột có nhắc nền tảng (quy chuẩn BI: mô tả luôn đúng dữ liệu).
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.nguon`
  ALTER COLUMN nen_tang SET OPTIONS(description='Nền tảng của nguồn. Giá trị (ràng buộc nguồn): tiktok, instagram, youtube, facebook, threads (từ 16/10/2026).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.nguon`
  ALTER COLUMN dinh_danh SET OPTIONS(description='Định danh nguồn đã chuẩn hoá: username TikTok/Instagram/Threads (chữ thường, không @), id kênh YouTube (UC…, giữ hoa thường) hoặc @handle, URL trang Facebook. Duy nhất trong cặp (du_an, nen_tang).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.nguon`
  ALTER COLUMN so_bai_moi_lan SET OPTIONS(description='Số bài mới nhất lấy mỗi lần quét, bài (≥ 1, không trần trên). Instagram luôn trả tối đa 12 bài mới nhất (giới hạn của actor hồ sơ). Threads: actor lấy (và tính tiền) tối thiểu 10 bài mỗi tài khoản.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  ALTER COLUMN nen_tang SET OPTIONS(description='Nền tảng của bài. Giá trị: tiktok, instagram, youtube, facebook, threads (Threads cả lượt theo dõi lẫn tìm theo từ khoá từ 16/10/2026).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  ALTER COLUMN tai_khoan SET OPTIONS(description='Username của tài khoản đăng (TikTok, Instagram, Threads). Chuỗi rỗng với YouTube và khi không có.');
-- Báo & Web (16/10/2026): bảng đã tạo trước thì thêm 3 cột + cập nhật mô tả (dong_bo_bq MERGE
-- cả ba cột — chạy khối này TRƯỚC khi bật đồng bộ bản mới).
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  ADD COLUMN IF NOT EXISTS kieu_trang STRING OPTIONS(description='Loại trang của bài web. Giá trị: bao (báo/tạp chí), dien_dan (diễn đàn), blog, mxh_khac (LinkedIn, X, Lemon8…), khac (trang khác). NULL với bài mạng xã hội (nen_tang khác web).'),
  ADD COLUMN IF NOT EXISTS muc_nhac STRING OPTIONS(description='Mức nhắc brand trong bài web. Giá trị: tieu_de (từ khoá ở tiêu đề), chinh (≥ 3 lần trong thân bài), thoang (nhắc lướt 1–2 lần, vd bài liệt kê nhiều brand). NULL với bài mạng xã hội.'),
  ADD COLUMN IF NOT EXISTS la_pr BOOL OPTIONS(description='TRUE: bài web có dấu hiệu bài đặt/PR (thân bài dẫn link về miền của brand hoặc ghi "Ảnh/Nguồn: <brand>"). FALSE: không thấy dấu hiệu. NULL với bài mạng xã hội.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  ALTER COLUMN nen_tang SET OPTIONS(description='Nền tảng của bài. Giá trị: tiktok, instagram, youtube, facebook, threads (Threads cả lượt theo dõi lẫn tìm theo từ khoá từ 16/10/2026), web (Báo & Web — báo, diễn đàn, blog tìm qua Google, từ 16/10/2026).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  ALTER COLUMN tai_khoan SET OPTIONS(description='Username của tài khoản đăng (TikTok, Instagram, Threads); tên miền trang với web (vd cafef.vn). Chuỗi rỗng với YouTube và khi không có.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Bài mạng xã hội liên quan tới dự án mà Mark đã giữ, kèm nhãn AI và tương tác mới nhất, để đếm thảo luận, nguồn nổi bật, sắc thái, chủ đề.
[Grain] 1 dòng = 1 bài × 1 dự án
[Khoá] PK: du_an + khoa | Join: du_an → du_an.ma; nguon_id → nguon.id; (du_an, khoa) → chi_so_ngay; luot_dau, luot_cuoi → luot_quet.id
[Nguồn] Postgres lang_nghe.public.bai trên VPS Mark; Mark ghi sau mỗi lượt /theodoi (Apify theo tài khoản, YouTube Data API) và lượt tìm theo từ khoá
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (nguồn theo dõi + tìm theo từ khoá từ 16/10/2026; trước đó chỉ từ social_listen), Báo & Web (nen_tang = web: báo, diễn đàn, blog tìm qua Google, từ 16/10/2026) | Bài đăng trong 35 ngày trước mỗi lượt quét, từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Chỉ bài liên quan: nhắc từ khoá dự án (trừ kênh nhà), không chứa từ loại trừ, không bị AI loại; khử trùng theo khoa; nội dung cắt 1.000 ký tự
[Refresh] MERGE theo du_an + khoa các dòng có cap_nhat_cuoi mới hơn mốc, sau mỗi lượt quét và 6 giờ một lần (lượt /theodoi theo lịch Giao việc trên console và theo Lịch quét tự động trên dashboard — mỗi N giờ, hằng ngày, hằng tuần hoặc liên tục trong chiến dịch, từ 15/10/2026)
[Dùng khi] Đếm bài, thảo luận (1 + binh_luan), nguồn nổi bật, sắc thái, chủ đề, từ khoá theo ngày đăng/nền tảng/dự án
[Không dùng khi] Tương tác theo từng ngày để vẽ tăng trưởng → dùng SOCIAL_LISTENING.chi_so_ngay; chi phí quét → dùng SOCIAL_LISTENING.luot_quet
[Lưu ý] Số liệu là lần đọc gần nhất, không phải cuối kỳ; bài YouTube được đọc lại số mỗi ngày trong 14 ngày đầu, nền tảng khác chỉ khi bài còn nằm trong N bài mới nhất của nguồn. Đây là mẫu theo nguồn đã chọn, không phải toàn bộ thảo luận trên mạng.''');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.binh_luan`
  ALTER COLUMN nen_tang SET OPTIONS(description='Nền tảng. Giá trị: tiktok, instagram, youtube, facebook, threads.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.binh_luan`
  ALTER COLUMN link SET OPTIONS(description='Link mở thẳng tới bình luận khi nền tảng có (Facebook, Instagram, Threads, YouTube); NULL thì dùng bai.link.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.nguon`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Danh sách nguồn mạng xã hội đang theo dõi của từng dự án, kèm chu kỳ quét và tình trạng quét gần nhất.
[Grain] 1 dòng = 1 nguồn (1 tài khoản/kênh/trang trên 1 nền tảng) của 1 dự án
[Khoá] PK: id | Join: du_an → du_an.ma; id → bai.nguon_id
[Nguồn] Postgres lang_nghe.public.nguon trên VPS Mark (người quản lý sửa trên dashboard; Mark chỉ ghi quet_cuoi, loi_cuoi, loi_luc)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (từ 16/10/2026) | Dữ liệu từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Bỏ cột them_boi (email người thêm); thêm dong_bo_luc; nguồn xoá ở nguồn thì xoá ở đây khi đồng bộ
[Refresh] Nạp lại toàn bảng bằng MERGE (có xoá dòng không còn ở nguồn) sau mỗi lượt quét và 6 giờ một lần
[Dùng khi] Đếm nguồn theo dõi theo dự án/nền tảng/loại; tìm nguồn lỗi hoặc lâu chưa quét; gắn loại nguồn cho bài
[Không dùng khi] Bài và tương tác của nguồn → dùng SOCIAL_LISTENING.bai; nguồn Mark đề xuất chưa duyệt → không có trên BigQuery, xem dashboard
[Lưu ý] Bài tìm theo từ khoá (bai.kieu_quet = tu_khoa) có thể không có nguồn (bai.nguon_id NULL).''');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Bài mạng xã hội liên quan tới dự án mà Mark đã giữ, kèm nhãn AI và tương tác mới nhất, để đếm thảo luận, nguồn nổi bật, sắc thái, chủ đề.
[Grain] 1 dòng = 1 bài × 1 dự án
[Khoá] PK: du_an + khoa | Join: du_an → du_an.ma; nguon_id → nguon.id; (du_an, khoa) → chi_so_ngay; luot_dau, luot_cuoi → luot_quet.id
[Nguồn] Postgres lang_nghe.public.bai trên VPS Mark; Mark ghi sau mỗi lượt /theodoi (Apify theo tài khoản, YouTube Data API) và lượt tìm theo từ khoá
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (nguồn theo dõi + tìm theo từ khoá từ 16/10/2026; trước đó chỉ từ social_listen) | Bài đăng trong 35 ngày trước mỗi lượt quét, từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Chỉ bài liên quan: nhắc từ khoá dự án (trừ kênh nhà), không chứa từ loại trừ, không bị AI loại; khử trùng theo khoa; nội dung cắt 1.000 ký tự
[Refresh] MERGE theo du_an + khoa các dòng có cap_nhat_cuoi mới hơn mốc, sau mỗi lượt quét và 6 giờ một lần (lượt /theodoi theo lịch Giao việc trên console và theo Lịch quét tự động trên dashboard — mỗi N giờ, hằng ngày, hằng tuần hoặc liên tục trong chiến dịch, từ 15/10/2026)
[Dùng khi] Đếm bài, thảo luận (1 + binh_luan), nguồn nổi bật, sắc thái, chủ đề, từ khoá theo ngày đăng/nền tảng/dự án
[Không dùng khi] Tương tác theo từng ngày để vẽ tăng trưởng → dùng SOCIAL_LISTENING.chi_so_ngay; chi phí quét → dùng SOCIAL_LISTENING.luot_quet
[Lưu ý] Số liệu là lần đọc gần nhất, không phải cuối kỳ; bài YouTube được đọc lại số mỗi ngày trong 14 ngày đầu, nền tảng khác chỉ khi bài còn nằm trong N bài mới nhất của nguồn. Đây là mẫu theo nguồn đã chọn, không phải toàn bộ thảo luận trên mạng.''');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.chi_so_ngay`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Tương tác lũy kế của từng bài theo ngày đọc, để vẽ tăng trưởng và tính phần tăng trong kỳ.
[Grain] 1 dòng = 1 bài × 1 dự án × 1 ngày đọc (giờ VN)
[Khoá] PK: du_an + khoa + ngay | Join: (du_an, khoa) → bai.(du_an, khoa)
[Nguồn] Postgres lang_nghe.public.chi_so_ngay trên VPS Mark; Mark ghi mỗi lần đọc số của bài (ghi đè trong cùng ngày)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Không xử lý; bản sao các cột số liệu
[Refresh] MERGE theo du_an + khoa + ngay các dòng có ngày từ (mốc lần trước − 1 ngày), sau mỗi lượt quét và 6 giờ một lần
[Dùng khi] Tăng trưởng lượt xem/bình luận theo ngày; phần tăng trong kỳ = giá trị ngày cuối − ngày đầu của bài
[Không dùng khi] Số liệu mới nhất của bài, nội dung, nhãn → dùng SOCIAL_LISTENING.bai
[Lưu ý] Số là LŨY KẾ, không phải phát sinh trong ngày; bài không được đọc ngày nào thì thiếu dòng ngày đó (không có dòng 0).''');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.binh_luan`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Bình luận (và trả lời) dưới các bài đã giữ của dự án, kèm sắc thái và chủ đề AI gán — tiếng khách hàng.
[Grain] 1 dòng = 1 bình luận × 1 bài × 1 dự án
[Khoá] PK: du_an + khoa_bai + ma | Join: (du_an, khoa_bai) → bai.(du_an, khoa); luot_id → luot_quet.id
[Nguồn] Postgres lang_nghe.public.binh_luan trên VPS Mark; Mark cào sau mỗi lượt /theodoi (Apify comments scraper TikTok/Facebook/Instagram, Threads replies scraper, YouTube Data API)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (từ 16/10/2026) | Bài đăng trong 35 ngày; số bài và số bình luận mỗi bài theo cấu hình từng nền tảng (du_an.cau_hinh trên Postgres, 0 = cào hết); từ 15/10/2026
[Đã xử lý] Khử trùng theo ma; nội dung cắt 1.000 ký tự; mỗi dòng có nhãn lọc loai (spam/rác/trùng/seeding/thương hiệu) — chỉ hop_le được gán sắc thái/chủ đề
[Refresh] MERGE theo du_an + khoa_bai + ma các dòng có cap_nhat_cuoi mới, sau mỗi lượt quét và 6 giờ một lần
[Dùng khi] Đọc từng bình luận; tỷ lệ sắc thái, chủ đề bình luận của khách theo ngày; món khách hỏi mua (san_pham)
[Không dùng khi] Tổng bình luận nền tảng báo của bài → dùng SOCIAL_LISTENING.bai.binh_luan
[Lưu ý] Thảo luận sạch / sắc thái: lọc loai = 'hop_le'; Instagram chưa đăng nhập chỉ trả một phần, Threads chỉ trả lời cấp 1 (10–300 mỗi bài), bài rất lớn có thể thiếu (so bai.binh_luan để biết độ phủ).''');

-- Món khách hỏi mua (17/10/2026): bảng đã tạo trước thì thêm cột (dong_bo_bq MERGE cả san_pham —
-- chạy khối này TRƯỚC khi bật đồng bộ bản mới, cùng lúc chạy schema.sql trên Postgres).
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.binh_luan`
  ADD COLUMN IF NOT EXISTS san_pham STRING OPTIONS(description='Món khách hỏi mua, chỉ có ở bình luận hỏi mua (AI gán cùng sắc thái/chủ đề, đọc cả nội dung bài; từ 17/10/2026). Giá trị: tui (túi xách, balo), vi (ví), nuoc_hoa (nước hoa), trang_suc (trang sức), set_qua (set/combo/hộp quà nhiều món), khac (món khác của brand), ngoai_brand (đồ không phải hàng của brand, vd quần áo người trong video mặc — dashboard không tính là ý định mua), chua_ro (không đoán được món). NULL khi không phải bình luận hỏi mua, chưa gán nhãn, gán trước 17/10/2026 chưa gán lại, hoặc loai khác hop_le.');

-- Ghi chú lượt giữ tới 20.000 ký tự (17/10/2026, trước đó cắt ở 2.000): bảng đã tạo trước thì
-- CREATE … IF NOT EXISTS không đổi mô tả — cập nhật cho khớp COMMENT luot_quet.ghi_chu bên Postgres
-- (quy chuẩn BI: mô tả luôn đúng dữ liệu). Chỉ đổi mô tả, không đổi kiểu cột (STRING không trần).
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.luot_quet`
  ALTER COLUMN ghi_chu SET OPTIONS(description='Ghi chú vận hành (vd hết ngân sách tháng, bot khởi động lại giữa lượt, nền tảng bỏ qua/lỗi kèm lý do) và phễu từng nền tảng của lượt tìm theo từ khoá, các câu nối bằng "; ". Tối đa 20.000 ký tự (từ 17/10/2026; trước đó 2.000 — lượt cũ có thể cụt), quá thì cắt và ghi dấu đã cắt ở cuối. NULL khi không có.');

-- Khử trùng bài Facebook (17/10/2026, khu_trung_fb.py): bảng đã tạo trước thì thêm cột ma_so_fb
-- (dong_bo_bq MERGE cả cột này — chạy khối này TRƯỚC khi bật đồng bộ bản mới, cùng lúc chạy
-- schema.sql trên Postgres) và đặt lại mô tả bảng. Khối này đứng CUỐI nên mô tả bảng sau cùng là
-- bản đủ nhất (hai khối SET OPTIONS của bai phía trên chạy trước, khối 16/10 thiếu Báo & Web).
-- Lưu ý: MERGE của bai không xoá dòng — bản trùng script gộp đã xoá ở Postgres phải xoá tay ở đây
-- nếu đồng bộ đã bật trước khi gộp (17/10/2026: chưa bật, dong_bo_bq 0 dòng).
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  ADD COLUMN IF NOT EXISTS ma_so_fb STRING OPTIONS(description='Id số ổn định của bài Facebook (5–25 chữ số): id bài actor trả (postId, post_id, post.id, feedbackId), không có thì bóc từ link (/posts/, /videos/, /reel/, /permalink/, story_fbid=). Dùng để nhận bản trùng: pfbid trong link và khoa đổi mỗi lượt cào (đo 17/10/2026). Không phải khoá (PK là du_an + khoa), không join bảng khác; không duy nhất (bản trùng cũ chưa gộp có thể cùng id). NULL với nền tảng khác, bài ghi trước 17/10/2026 chưa được quét lại (quét lại thì Mark điền), hoặc link pfbid mà actor không trả id.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Bài mạng xã hội liên quan tới dự án mà Mark đã giữ, kèm nhãn AI và tương tác mới nhất, để đếm thảo luận, nguồn nổi bật, sắc thái, chủ đề.
[Grain] 1 dòng = 1 bài × 1 dự án
[Khoá] PK: du_an + khoa | Join: du_an → du_an.ma; nguon_id → nguon.id; (du_an, khoa) → chi_so_ngay; luot_dau, luot_cuoi → luot_quet.id
[Nguồn] Postgres lang_nghe.public.bai trên VPS Mark; Mark ghi sau mỗi lượt /theodoi (Apify theo tài khoản, YouTube Data API) và lượt tìm theo từ khoá
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (nguồn theo dõi + tìm theo từ khoá từ 16/10/2026; trước đó chỉ từ social_listen), Báo & Web (nen_tang = web: báo, diễn đàn, blog tìm qua Google, từ 16/10/2026) | Bài đăng trong 35 ngày trước mỗi lượt quét, từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Chỉ bài liên quan: nhắc từ khoá dự án (trừ kênh nhà), không chứa từ loại trừ, không bị AI loại; khử trùng theo khoa; bài Facebook khử trùng thêm theo id số ma_so_fb, không có id thì theo chủ bài + phút đăng + nội dung (từ 17/10/2026); nội dung cắt 1.000 ký tự
[Refresh] MERGE theo du_an + khoa các dòng có cap_nhat_cuoi mới hơn mốc, sau mỗi lượt quét và 6 giờ một lần (lượt /theodoi theo lịch Giao việc trên console và theo Lịch quét tự động trên dashboard — mỗi N giờ, hằng ngày, hằng tuần hoặc liên tục trong chiến dịch, từ 15/10/2026)
[Dùng khi] Đếm bài, thảo luận (1 + binh_luan), nguồn nổi bật, sắc thái, chủ đề, từ khoá theo ngày đăng/nền tảng/dự án
[Không dùng khi] Tương tác theo từng ngày để vẽ tăng trưởng → dùng SOCIAL_LISTENING.chi_so_ngay; chi phí quét → dùng SOCIAL_LISTENING.luot_quet
[Lưu ý] Số liệu là lần đọc gần nhất, không phải cuối kỳ; bài YouTube được đọc lại số mỗi ngày trong 14 ngày đầu, nền tảng khác chỉ khi bài còn nằm trong N bài mới nhất của nguồn. Đây là mẫu theo nguồn đã chọn, không phải toàn bộ thảo luận trên mạng.''');

-- Chốt chi phí khi phí sự kiện Apify ghi trễ (17/10/2026): bảng đã tạo trước thì đổi mô tả cột cho
-- khớp COMMENT luot_quet.chi_phi_usd bên Postgres. Chỉ đổi mô tả, không đổi kiểu cột.
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.luot_quet`
  ALTER COLUMN chi_phi_usd SET OPTIONS(description='Chi phí Apify THẬT của lượt, USD, không VAT: tổng usageTotalUsd đúng các run của lượt, đọc khi run cuối đã xong ≥ 45 giây; Mark đọc lại ~90 giây sau run cuối và NÂNG số nếu Apify ghi thêm phí sự kiện (chỉ nâng, không hạ; từ 17/10/2026 — lượt cũ hơn có thể thiếu phí ghi trễ). 0 khi lượt chỉ dùng YouTube Data API (miễn phí). Không âm.');

-- Hashtag riêng của dự án (18/10/2026, chủ dự án: "bỏ phần thị trường, thay bằng phần hashtag"):
-- bảng đã tạo trước thì thêm cột (dong_bo_bq MERGE cả hashtag — chạy khối này TRƯỚC khi bật bản
-- mới, cùng lúc chạy schema.sql trên Postgres), cập nhật mô tả thi_truong + mô tả bảng cho khớp.
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.du_an`
  ADD COLUMN IF NOT EXISTS hashtag ARRAY<STRING> OPTIONS(description='Hashtag riêng của dự án, người quản lý nhập trên dashboard (từ 18/10/2026): đã bỏ #, bỏ dấu, chữ thường, chỉ a-z 0-9 _, bỏ trùng, giữ thứ tự gõ; tối đa 50 mục. Mark dùng cho tìm hashtag Instagram và feed hashtag TikTok. Mảng rỗng (mặc định; mọi dự án trước 18/10/2026): Mark suy hashtag từ tu_khoa như trước. Không dùng để lọc bài.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.du_an`
  ALTER COLUMN thi_truong SET OPTIONS(description='Mã nước 2 chữ (ISO 3166-1) của thị trường chính, mặc định VN. Dùng cho bước AI nhận bài ngoài thị trường. Từ 18/10/2026 dashboard không còn ô sửa: dự án mới luôn VN, dự án cũ giữ giá trị đã lưu.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.du_an`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Danh mục dự án/brand đang được lắng nghe và cấu hình lọc + thu thập (từ khoá, từ loại trừ, hashtag riêng, trần chi phí tháng).
[Grain] 1 dòng = 1 dự án
[Khoá] PK: ma | Join: ma → nguon.du_an, bai.du_an, chi_so_ngay.du_an, luot_quet.du_an
[Nguồn] Postgres lang_nghe.public.du_an trên VPS Mark (người quản lý sửa trên dashboard social.hapas.vn)
[Phạm vi] Mọi dự án lắng nghe | Kênh: Không có | Dữ liệu từ khi bật đợt 2 (sau 14/10/2026); cột hashtag từ 18/10/2026
[Đã xử lý] Bỏ cột sua_boi (email người sửa); thêm dong_bo_luc; dự án xoá ở nguồn thì xoá ở đây khi đồng bộ
[Refresh] Nạp lại toàn bảng bằng MERGE (có xoá dòng không còn ở nguồn) sau mỗi lượt quét và 6 giờ một lần
[Dùng khi] Gắn tên dự án, xem cấu hình từ khoá, hashtag và trần chi phí tháng
[Không dùng khi] Số bài, thảo luận → dùng SOCIAL_LISTENING.bai; chi phí đã tiêu → dùng SOCIAL_LISTENING.luot_quet
[Lưu ý] Bảng chứa cấu hình hiện hành, không giữ lịch sử thay đổi (lịch sử sửa nằm ở nhật ký trên VPS, không đẩy lên).''');

-- Seeding affiliate + cổng thị trường VN + cổng brand đường hashtag (18/10/2026): Mark không ghi
-- bài seeding affiliate (tài khoản đăng dày, ít tương tác), bài tìm theo từ khoá ngoài thị trường VN
-- và bài chỉ đến từ đường hashtag mà không gọi tên brand; bài seeding cũ dọn ở
-- Postgres bằng scripts/lang_nghe_loc_seeding.py. Bảng đã tạo trước thì đặt lại mô tả bảng (khối
-- này đứng CUỐI nên là bản mới nhất). MERGE của bai không xoá dòng — nếu đồng bộ đã bật trước khi
-- dọn thì xoá tay các khoá trong tệp hoàn tác của script.
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Bài mạng xã hội liên quan tới dự án mà Mark đã giữ, kèm nhãn AI và tương tác mới nhất, để đếm thảo luận, nguồn nổi bật, sắc thái, chủ đề.
[Grain] 1 dòng = 1 bài × 1 dự án
[Khoá] PK: du_an + khoa | Join: du_an → du_an.ma; nguon_id → nguon.id; (du_an, khoa) → chi_so_ngay; luot_dau, luot_cuoi → luot_quet.id
[Nguồn] Postgres lang_nghe.public.bai trên VPS Mark; Mark ghi sau mỗi lượt /theodoi (Apify theo tài khoản, YouTube Data API) và lượt tìm theo từ khoá
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (nguồn theo dõi + tìm theo từ khoá từ 16/10/2026; trước đó chỉ từ social_listen), Báo & Web (nen_tang = web: báo, diễn đàn, blog tìm qua Google, từ 16/10/2026) | Bài đăng từ 17/09/2026: mỗi lượt quét giữ bài đăng trong 35 ngày trước lượt (từ khi bật đợt 2, 14/10/2026); bài đăng 17/09 → 14/10/2026 nạp từ raw đã trả tiền (từ 18/10/2026)
[Đã xử lý] Chỉ bài liên quan: nhắc từ khoá dự án (trừ kênh nhà), không chứa từ loại trừ, không bị AI loại; từ 18/10/2026 không có bài seeding affiliate (mặc định chỉ TikTok; tài khoản không phải kênh nhà, không mang tên brand, đăng ≥ 5 bài/ngày hoặc ≥ 20 bài/7 ngày với trung vị ≤ 2 bình luận và ≤ 15.000 lượt xem; bài tự có ≥ 10 bình luận vẫn giữ), bài tìm theo từ khoá ngoài thị trường VN (nội dung chữ nước khác hoặc kênh YouTube khai nước khác, không có dấu hiệu Việt; ca mơ hồ do AI phán) và bài chỉ đến từ đường hashtag (feed hashtag TikTok, Instagram hashtag) mà không gọi tên brand ở nội dung, hashtag, tên hay định danh chủ bài (tên brand gồm tag chiến dịch của dự án, trừ tag rộng như #quatang2010; trừ kênh nhà); khử trùng theo khoa; bài Facebook khử trùng thêm theo id số ma_so_fb, không có id thì theo chủ bài + phút đăng + nội dung (từ 17/10/2026); nội dung cắt 1.000 ký tự
[Refresh] MERGE theo du_an + khoa các dòng có cap_nhat_cuoi mới hơn mốc, sau mỗi lượt quét và 6 giờ một lần (lượt /theodoi theo lịch Giao việc trên console và theo Lịch quét tự động trên dashboard — mỗi N giờ, hằng ngày, hằng tuần hoặc liên tục trong chiến dịch, từ 15/10/2026)
[Dùng khi] Đếm bài, thảo luận (1 + binh_luan), nguồn nổi bật, sắc thái, chủ đề, từ khoá theo ngày đăng/nền tảng/dự án
[Không dùng khi] Tương tác theo từng ngày để vẽ tăng trưởng → dùng SOCIAL_LISTENING.chi_so_ngay; chi phí quét → dùng SOCIAL_LISTENING.luot_quet
[Lưu ý] Số liệu là lần đọc gần nhất, không phải cuối kỳ; bài YouTube được đọc lại số mỗi ngày trong 14 ngày đầu, nền tảng khác chỉ khi bài còn nằm trong N bài mới nhất của nguồn. Đây là mẫu theo nguồn đã chọn, không phải toàn bộ thảo luận trên mạng. MERGE không xoá dòng: bài seeding đã dọn ở Postgres (scripts/lang_nghe_loc_seeding.py) còn ở đây nếu đồng bộ bật trước khi dọn.''');

-- Lượt nạp raw đã trả tiền (18/10/2026, scripts/lang_nghe_nap_raw.py): kieu tu_khoa, ma_viec
-- nap-raw-<giờ>. Bảng đã tạo trước thì đổi mô tả cột cho khớp COMMENT bên Postgres.
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.luot_quet`
  ALTER COLUMN kieu SET OPTIONS(description='Giá trị: theo_doi (lượt /theodoi quét nguồn, tính vào trần tháng), tu_khoa (lượt tìm theo từ khoá ghi vào kho; cả lượt nạp raw đã trả tiền bằng scripts/lang_nghe_nap_raw.py từ 18/10/2026, chi phí 0).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.luot_quet`
  ALTER COLUMN ma_viec SET OPTIONS(description='Mã việc nền của Mark (vd t10140830-ab12c), đối chiếu với /viec. nap-raw-<năm tháng ngày giờ phút> với lượt nạp raw (từ 18/10/2026). NULL khi lượt không chạy qua việc nền.');

-- TikTok Ads (19/10/2026, dashboard/tiktok_ads.py): tài khoản quảng cáo + số quảng cáo theo ngày,
-- campaign, ad, khán giả. NGƯỜI DUYỆT RỒI MỚI CHẠY, và chạy TRƯỚC khi bật bản dashboard có TikTok Ads
-- (dong_bo_bq MERGE cả 5 bảng — thiếu bảng thì bảng đó báo lỗi trên trang BigQuery tới khi tạo).
-- Không có bảng ket_noi_ngoai (token mã hoá, email người cấp) — không bao giờ đẩy lên BigQuery.
-- Cột tiền (chi, gia_tri_mua_shop, khoá tiền trong chi_so) là dữ liệu nhạy cảm: dashboard chỉ cho
-- quản trị viên + quản lý của bên xem. Mặc định dashboard KHÔNG đẩy số tiền (BQ_QC_XUAT_TIEN=0:
-- cột tiền NULL, khoá tiền bỏ khỏi chi_so) cho tới khi chủ dự án quyết; đặt 1 thì đẩy đủ —
-- khi đó cấp quyền đọc dataset theo đúng nguyên tắc trên.

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.tk_quang_cao`
(
  advertiser_id     STRING    OPTIONS(description='Mã tài khoản quảng cáo: TikTok chuỗi số; Meta act_<số> (từ 20/10/2026). PK. Join: → qc_*.advertiser_id.'),
  ten               STRING    OPTIONS(description='Tên tài khoản trên nền tảng (TikTok advertiser_name; Meta name; đã bỏ khoảng trắng hai đầu), vd "MATEMADE MKT". Chuỗi rỗng khi nền tảng không trả.'),
  don_vi            STRING    OPTIONS(description='Bên sở hữu tài khoản. FK → don_vi.ma. NULL = chưa gán bên (chỉ quản trị viên thấy số).'),
  gan_tay           BOOL      OPTIONS(description='TRUE: quản trị viên đã sửa bên/đồng bộ trên trang Quản trị — gán tự động không đè. FALSE: bên do gán tự động.'),
  gan_luc           TIMESTAMP OPTIONS(description='Lần quản trị viên sửa bên/đồng bộ gần nhất (UTC; người sửa ở nhat_ky). NULL khi chưa sửa tay.'),
  tien_te           STRING    OPTIONS(description='Tiền tệ của tài khoản (currency, mã ISO, vd VND) — đơn vị mọi cột tiền của tài khoản.'),
  mui_gio           STRING    OPTIONS(description='Múi giờ của tài khoản (TikTok display_timezone; Meta timezone_name; vd Asia/Ho_Chi_Minh) — ngày trong qc_* theo múi giờ này.'),
  dang_dong_bo      BOOL      OPTIONS(description='TRUE: lượt đồng bộ đọc số tài khoản này. FALSE: quản trị viên tắt (số cũ giữ).'),
  con_quyen         BOOL      OPTIONS(description='TRUE: lần đọc gần nhất còn thấy tài khoản. FALSE: không còn thấy (người cấp quyền mất quyền) — không đồng bộ, số cũ giữ.'),
  thay_lan_dau      TIMESTAMP OPTIONS(description='Lần đầu dashboard thấy tài khoản (UTC).'),
  thay_cuoi         TIMESTAMP OPTIONS(description='Lần gần nhất thấy tài khoản (UTC).'),
  nap_lui_tu        DATE      OPTIONS(description='Nạp lùi đã đọc xong xuống tới ngày này (múi giờ tài khoản; cửa sổ 30 ngày mới trước). Lượt bị ngắt giữa chừng thì lượt sau chỉ đọc phần trước ngày này. NULL khi chưa nạp cửa sổ nào.'),
  nap_lui_xong_luc  TIMESTAMP OPTIONS(description='Lúc nạp lùi 90 ngày lần đầu xong (UTC). NULL = chưa nạp lùi (lượt sau nạp).'),
  khan_gia_luc      TIMESTAMP OPTIONS(description='Lần đọc khán giả gần nhất (UTC; đọc lại mỗi 7 ngày). NULL khi chưa đọc.'),
  cap_nhat_luc      TIMESTAMP OPTIONS(description='Lần sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery (bảng nhỏ — nạp lại toàn bộ).'),
  nen_tang          STRING    OPTIONS(description='Nền tảng quảng cáo. Giá trị: tiktok, meta (từ 20/10/2026). NULL ở dòng ghi trước khi dashboard đẩy cột này (lượt đồng bộ kế tiếp nạp lại toàn bảng).'),
  duyet             BOOL      OPTIONS(description='TRUE: được đọc số (TikTok luôn TRUE; Meta = quản trị viên đã duyệt tài khoản). FALSE: tài khoản Meta chưa duyệt — không có số trong qc_*. NULL ở dòng ghi trước khi dashboard đẩy cột này.'),
  dong_bo_luc       TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
OPTIONS(description='''[Lớp] Dim
[Mục đích] Danh sách tài khoản quảng cáo TikTok + Meta (Facebook/Instagram) dashboard đọc được và tài khoản thuộc bên nào (HAPAS, MATEMADE…).
[Grain] 1 dòng = 1 tài khoản quảng cáo (advertiser_id: TikTok advertiser hoặc Meta act_…)
[Khoá] PK: advertiser_id | Join: advertiser_id → qc_tk_ngay.advertiser_id, qc_campaign_ngay.advertiser_id, qc_ad_ngay.advertiser_id, qc_khan_gia.advertiser_id
[Nguồn] Postgres lang_nghe.public.tk_quang_cao trên VPS Mark; bộ đồng bộ TikTok Ads (TikTok for Business MCP: auth_advertiser_get + advertiser_info_get); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Mọi tài khoản quảng cáo người cấp quyền thấy được (19/10/2026: 16 tài khoản) | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 19/10/2026
[Đã xử lý] Gán bên tự động (tên có chữ THAI → chưa gán; MATEMADE / MATE MADE / MADEMATE → matemade; còn lại → hapas) trừ khi quản trị viên đã sửa tay (gan_tay); không đẩy email người sửa
[Refresh] MERGE nạp lại toàn bộ (xoá dòng không còn ở nguồn) sau mỗi lượt đồng bộ TikTok / Meta (06:30 / 06:45 giờ VN hằng ngày) và 6 giờ một lần
[Dùng khi] Gắn bên / tên / tiền tệ cho số quảng cáo; lọc tài khoản đang đồng bộ
[Không dùng khi] Số chi, hiển thị, xem → dùng SOCIAL_LISTENING.qc_tk_ngay; dự án lắng nghe → dùng SOCIAL_LISTENING.du_an
[Lưu ý] don_vi NULL = chưa gán bên. con_quyen false = token hiện tại không còn thấy tài khoản (số cũ vẫn giữ trong qc_*).''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
(
  advertiser_id     STRING    OPTIONS(description='Tài khoản quảng cáo. Một phần PK. FK → tk_quang_cao.advertiser_id.'),
  ngay              DATE      OPTIONS(description='Ngày số liệu theo múi giờ tài khoản (tk_quang_cao.mui_gio, thường GMT+7). Một phần PK.'),
  chi               NUMERIC   OPTIONS(description='Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy. NULL trên BigQuery khi dashboard đặt BQ_QC_XUAT_TIEN khác 1 (mặc định 0 — chưa đẩy tiền).'),
  hien_thi          INT64     OPTIONS(description='Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.'),
  reach             INT64     OPTIONS(description='Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.'),
  click             INT64     OPTIONS(description='Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.'),
  ket_qua           INT64     OPTIONS(description='Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.'),
  chuyen_doi        INT64     OPTIONS(description='Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.'),
  view_video        INT64     OPTIONS(description='Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.'),
  view_hai_giay     INT64     OPTIONS(description='Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  view_sau_giay     INT64     OPTIONS(description='Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  view_het          INT64     OPTIONS(description='Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.'),
  engaged_view      INT64     OPTIONS(description='Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.'),
  thich             INT64     OPTIONS(description='Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.'),
  binh_luan         INT64     OPTIONS(description='Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.'),
  chia_se           INT64     OPTIONS(description='Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.'),
  follow            INT64     OPTIONS(description='Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.'),
  vao_ho_so         INT64     OPTIONS(description='Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  mua_shop          INT64     OPTIONS(description='Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.'),
  gia_tri_mua_shop  NUMERIC   OPTIONS(description='Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN — NULL trên BigQuery khi BQ_QC_XUAT_TIEN khác 1 (mặc định).'),
  chi_so            STRING    OPTIONS(description='Chuỗi JSON của cột JSONB chi_so bên Postgres: MỌI chỉ số nền tảng trả cho dòng {tên chỉ số: số} ("-" của TikTok → null; Meta: danh sách action thành <trường>__<action_type>, vd actions__purchase, action_values__purchase — reach, frequency, ctr, cpc, cpm, cpp, *roas* không cộng được qua dòng). Đọc bằng JSON_VALUE(chi_so, \'$.cpm\') hoặc PARSE_JSON(chi_so). Tài khoản/campaign: 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Khoá tiền (spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*) chỉ có khi dashboard đặt BQ_QC_XUAT_TIEN=1 (mặc định 0: bỏ khỏi chuỗi).'),
  cap_nhat_luc      TIMESTAMP OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery (đẩy dòng có cap_nhat_luc mới hơn lần trước).'),
  dong_bo_luc       TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
PARTITION BY ngay
CLUSTER BY advertiser_id
OPTIONS(description='''[Lớp] Raw
[Mục đích] Số quảng cáo TikTok / Meta theo ngày của cả tài khoản: chi, hiển thị, xem video, tương tác, follow, doanh thu TikTok Shop.
[Grain] 1 dòng = 1 tài khoản quảng cáo × 1 ngày (múi giờ tài khoản, thường GMT+7)
[Khoá] PK: advertiser_id + ngay | Join: advertiser_id → tk_quang_cao.advertiser_id
[Nguồn] Postgres lang_nghe.public.qc_tk_ngay trên VPS Mark; TikTok for Business MCP report_integrated_get (BASIC, AUCTION_ADVERTISER, theo ngày); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Tài khoản tk_quang_cao đang đồng bộ | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 90 ngày trước lần kết nối đầu (nạp lùi)
[Đã xử lý] Chỉ ngày có hiển thị hoặc chi > 0; "-" của TikTok → NULL; tiền giữ tiền tệ gốc của tài khoản (tk_quang_cao.tien_te)
[Refresh] MERGE theo advertiser_id + ngay các dòng có cap_nhat_luc mới hơn mốc, ngay sau lượt đồng bộ TikTok 06:30 / Meta 06:45 giờ VN (đọc lại 7 ngày gần nhất) và 6 giờ một lần
[Dùng khi] Tổng chi/hiển thị/xem/tương tác theo ngày, tài khoản, bên (JOIN tk_quang_cao); ROAS Shop = SUM(gia_tri_mua_shop) / SUM(chi)
[Không dùng khi] Từng chiến dịch → dùng SOCIAL_LISTENING.qc_campaign_ngay; từng quảng cáo → dùng SOCIAL_LISTENING.qc_ad_ngay; tuổi/giới tính/tỉnh → dùng SOCIAL_LISTENING.qc_khan_gia
[Lưu ý] Chuyển đổi TikTok ghi trễ tới 7 ngày — số 7 ngày gần nhất còn đổi. reach cộng nhiều ngày là đếm trùng người. Cột tiền là dữ liệu nhạy cảm: chỉ chia cho quản trị viên + quản lý của bên.''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
(
  advertiser_id     STRING    OPTIONS(description='Tài khoản quảng cáo của campaign. FK → tk_quang_cao.advertiser_id.'),
  campaign_id       STRING    OPTIONS(description='Mã campaign (TikTok campaign_id; Meta campaign_id). Một phần PK. Join: → qc_ad_ngay.campaign_id.'),
  ngay              DATE      OPTIONS(description='Ngày số liệu theo múi giờ tài khoản (thường GMT+7). Một phần PK.'),
  ten               STRING    OPTIONS(description='Tên campaign lúc đọc (campaign_name). Chuỗi rỗng khi TikTok không trả.'),
  muc_tieu          STRING    OPTIONS(description='Mục tiêu campaign (objective_type), vd REACH, VIDEO_VIEWS, PRODUCT_SALES, ENGAGEMENT. NULL khi nền tảng không trả.'),
  chi               NUMERIC   OPTIONS(description='Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy. NULL trên BigQuery khi dashboard đặt BQ_QC_XUAT_TIEN khác 1 (mặc định 0 — chưa đẩy tiền).'),
  hien_thi          INT64     OPTIONS(description='Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.'),
  reach             INT64     OPTIONS(description='Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.'),
  click             INT64     OPTIONS(description='Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.'),
  ket_qua           INT64     OPTIONS(description='Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.'),
  chuyen_doi        INT64     OPTIONS(description='Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.'),
  view_video        INT64     OPTIONS(description='Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.'),
  view_hai_giay     INT64     OPTIONS(description='Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  view_sau_giay     INT64     OPTIONS(description='Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  view_het          INT64     OPTIONS(description='Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.'),
  engaged_view      INT64     OPTIONS(description='Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.'),
  thich             INT64     OPTIONS(description='Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.'),
  binh_luan         INT64     OPTIONS(description='Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.'),
  chia_se           INT64     OPTIONS(description='Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.'),
  follow            INT64     OPTIONS(description='Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.'),
  vao_ho_so         INT64     OPTIONS(description='Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  mua_shop          INT64     OPTIONS(description='Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.'),
  gia_tri_mua_shop  NUMERIC   OPTIONS(description='Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN — NULL trên BigQuery khi BQ_QC_XUAT_TIEN khác 1 (mặc định).'),
  chi_so            STRING    OPTIONS(description='Chuỗi JSON của cột JSONB chi_so bên Postgres: MỌI chỉ số nền tảng trả cho dòng {tên chỉ số: số} ("-" của TikTok → null; Meta: danh sách action thành <trường>__<action_type>, vd actions__purchase, action_values__purchase — reach, frequency, ctr, cpc, cpm, cpp, *roas* không cộng được qua dòng). Đọc bằng JSON_VALUE(chi_so, \'$.cpm\') hoặc PARSE_JSON(chi_so). Tài khoản/campaign: 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Khoá tiền (spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*) chỉ có khi dashboard đặt BQ_QC_XUAT_TIEN=1 (mặc định 0: bỏ khỏi chuỗi).'),
  cap_nhat_luc      TIMESTAMP OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery (đẩy dòng có cap_nhat_luc mới hơn lần trước).'),
  dong_bo_luc       TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
PARTITION BY ngay
CLUSTER BY advertiser_id, campaign_id
OPTIONS(description='''[Lớp] Raw
[Mục đích] Số quảng cáo TikTok / Meta theo ngày của từng chiến dịch có phân phối — xếp hạng chiến dịch.
[Grain] 1 dòng = 1 campaign × 1 ngày (múi giờ tài khoản)
[Khoá] PK: campaign_id + ngay | Join: advertiser_id → tk_quang_cao.advertiser_id; campaign_id → qc_ad_ngay.campaign_id
[Nguồn] Postgres lang_nghe.public.qc_campaign_ngay trên VPS Mark; TikTok for Business MCP report_integrated_get (BASIC, AUCTION_CAMPAIGN, theo ngày); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Tài khoản đang đồng bộ, chỉ campaign có hiển thị trong cửa sổ đọc | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 90 ngày trước lần kết nối đầu
[Đã xử lý] Chỉ campaign có impressions > 0 trong cửa sổ đọc, chỉ ngày có hiển thị hoặc chi > 0; "-" → NULL
[Refresh] MERGE theo campaign_id + ngay các dòng có cap_nhat_luc mới hơn mốc, sau lượt đồng bộ TikTok 06:30 / Meta 06:45 giờ VN và 6 giờ một lần
[Dùng khi] Top chiến dịch trong kỳ; chi/hiển thị/xem theo chiến dịch
[Không dùng khi] Tổng tài khoản → dùng SOCIAL_LISTENING.qc_tk_ngay; từng quảng cáo → dùng SOCIAL_LISTENING.qc_ad_ngay
[Lưu ý] ten / muc_tieu là giá trị lúc đọc từng ngày — lấy tên của ngày mới nhất. Ngân sách chiến dịch chỉ trong chi_so (campaign_budget, tiền).''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
(
  advertiser_id     STRING    OPTIONS(description='Tài khoản quảng cáo của ad. FK → tk_quang_cao.advertiser_id.'),
  campaign_id       STRING    OPTIONS(description='Campaign chứa ad. Join: → qc_campaign_ngay.campaign_id. NULL khi nền tảng không trả.'),
  adgroup_id        STRING    OPTIONS(description='Nhóm quảng cáo (ad group) chứa ad. NULL khi nền tảng không trả.'),
  ad_id             STRING    OPTIONS(description='Mã quảng cáo (TikTok ad_id; Meta ad_id). Một phần PK.'),
  ngay              DATE      OPTIONS(description='Ngày số liệu theo múi giờ tài khoản (thường GMT+7). Một phần PK.'),
  ten_ad            STRING    OPTIONS(description='Tên quảng cáo lúc đọc (ad_name). Chuỗi rỗng khi TikTok không trả.'),
  noi_dung          STRING    OPTIONS(description='Chữ quảng cáo (ad_text), ≤ 2.000 ký tự; quảng cáo Spark Ads thường là chú thích bài gốc. Chuỗi rỗng khi không có.'),
  ten_campaign      STRING    OPTIONS(description='Tên campaign chứa ad lúc đọc (campaign_name). Chuỗi rỗng khi TikTok không trả.'),
  ten_nhom          STRING    OPTIONS(description='Tên nhóm quảng cáo lúc đọc (adgroup_name). Chuỗi rỗng khi TikTok không trả.'),
  chi               NUMERIC   OPTIONS(description='Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy. NULL trên BigQuery khi dashboard đặt BQ_QC_XUAT_TIEN khác 1 (mặc định 0 — chưa đẩy tiền).'),
  hien_thi          INT64     OPTIONS(description='Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.'),
  reach             INT64     OPTIONS(description='Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.'),
  click             INT64     OPTIONS(description='Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.'),
  ket_qua           INT64     OPTIONS(description='Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.'),
  chuyen_doi        INT64     OPTIONS(description='Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.'),
  view_video        INT64     OPTIONS(description='Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.'),
  view_hai_giay     INT64     OPTIONS(description='Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  view_sau_giay     INT64     OPTIONS(description='Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  view_het          INT64     OPTIONS(description='Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.'),
  engaged_view      INT64     OPTIONS(description='Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.'),
  thich             INT64     OPTIONS(description='Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.'),
  binh_luan         INT64     OPTIONS(description='Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.'),
  chia_se           INT64     OPTIONS(description='Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.'),
  follow            INT64     OPTIONS(description='Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.'),
  vao_ho_so         INT64     OPTIONS(description='Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  mua_shop          INT64     OPTIONS(description='Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.'),
  gia_tri_mua_shop  NUMERIC   OPTIONS(description='Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN — NULL trên BigQuery khi BQ_QC_XUAT_TIEN khác 1 (mặc định).'),
  chi_so            STRING    OPTIONS(description='Chuỗi JSON của cột JSONB chi_so bên Postgres: MỌI chỉ số nền tảng trả cho dòng {tên chỉ số: số} ("-" của TikTok → null; Meta: danh sách action thành <trường>__<action_type>, vd actions__purchase, action_values__purchase — reach, frequency, ctr, cpc, cpm, cpp, *roas* không cộng được qua dòng). Đọc bằng JSON_VALUE(chi_so, \'$.cpm\') hoặc PARSE_JSON(chi_so). Tài khoản/campaign: 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Khoá tiền (spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*) chỉ có khi dashboard đặt BQ_QC_XUAT_TIEN=1 (mặc định 0: bỏ khỏi chuỗi).'),
  cap_nhat_luc      TIMESTAMP OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery (đẩy dòng có cap_nhat_luc mới hơn lần trước).'),
  dong_bo_luc       TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
PARTITION BY ngay
CLUSTER BY advertiser_id, campaign_id
OPTIONS(description='''[Lớp] Raw
[Mục đích] Số quảng cáo TikTok / Meta theo ngày của từng quảng cáo (ad) có phân phối — top quảng cáo/video.
[Grain] 1 dòng = 1 ad × 1 ngày (múi giờ tài khoản)
[Khoá] PK: ad_id + ngay | Join: advertiser_id → tk_quang_cao.advertiser_id; campaign_id → qc_campaign_ngay.campaign_id
[Nguồn] Postgres lang_nghe.public.qc_ad_ngay trên VPS Mark; TikTok for Business MCP report_integrated_get (BASIC, AUCTION_AD, theo ngày); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Tài khoản đang đồng bộ, CHỈ ad có hiển thị trong cửa sổ đọc | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 90 ngày trước lần kết nối đầu
[Đã xử lý] Chỉ ad có impressions > 0 trong cửa sổ đọc, chỉ ngày có hiển thị hoặc chi > 0; chi_so gồm 38 chỉ số chính (không đủ 100 như tài khoản/campaign); "-" → NULL
[Refresh] MERGE theo ad_id + ngay các dòng có cap_nhat_luc mới hơn mốc, sau lượt đồng bộ TikTok 06:30 / Meta 06:45 giờ VN và 6 giờ một lần
[Dùng khi] Top quảng cáo trong kỳ; nội dung nào kéo xem/follow
[Không dùng khi] Tổng tài khoản → dùng SOCIAL_LISTENING.qc_tk_ngay; chiến dịch → dùng SOCIAL_LISTENING.qc_campaign_ngay
[Lưu ý] Bảng lớn nhất (hàng nghìn dòng mỗi ngày với tài khoản lớn) — luôn lọc theo ngay (cột phân vùng).''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
(
  advertiser_id     STRING    OPTIONS(description='Tài khoản quảng cáo. Một phần PK. FK → tk_quang_cao.advertiser_id.'),
  tu                DATE      OPTIONS(description='Ngày đầu cửa sổ 30 ngày (múi giờ tài khoản). Một phần PK.'),
  den               DATE      OPTIONS(description='Ngày cuối cửa sổ (múi giờ tài khoản, = hôm qua lúc đọc). Một phần PK.'),
  chieu             STRING    OPTIONS(description='Chiều khán giả. Một phần PK. Giá trị: age, gender (TikTok + Meta), province_id, platform (TikTok: tỉnh, thiết bị), region, publisher_platform, platform_position (Meta, từ 20/10/2026).'),
  gia_tri           STRING    OPTIONS(description='Giá trị của chiều (mã TikTok): age AGE_13_17…AGE_55_100, NONE; gender FEMALE, MALE, NONE; province_id mã vùng số (-1 không rõ); platform ANDROID, IPHONE, IPAD, WAP, UNKNOWN. Meta: age cùng mã TikTok tới 45–54, rồi 55-64, 65+; gender FEMALE, MALE, NONE; region tên vùng Meta; publisher_platform facebook, instagram, messenger, audience_network, threads; platform_position <nền tảng>/<vị trí>. Một phần PK.'),
  chi               NUMERIC   OPTIONS(description='Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy. NULL trên BigQuery khi dashboard đặt BQ_QC_XUAT_TIEN khác 1 (mặc định 0 — chưa đẩy tiền).'),
  hien_thi          INT64     OPTIONS(description='Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.'),
  reach             INT64     OPTIONS(description='Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.'),
  click             INT64     OPTIONS(description='Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.'),
  ket_qua           INT64     OPTIONS(description='Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.'),
  chuyen_doi        INT64     OPTIONS(description='Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.'),
  view_video        INT64     OPTIONS(description='Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.'),
  view_hai_giay     INT64     OPTIONS(description='Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  view_sau_giay     INT64     OPTIONS(description='Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  view_het          INT64     OPTIONS(description='Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.'),
  engaged_view      INT64     OPTIONS(description='Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.'),
  thich             INT64     OPTIONS(description='Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.'),
  binh_luan         INT64     OPTIONS(description='Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.'),
  chia_se           INT64     OPTIONS(description='Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.'),
  follow            INT64     OPTIONS(description='Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.'),
  vao_ho_so         INT64     OPTIONS(description='Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  mua_shop          INT64     OPTIONS(description='Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.'),
  gia_tri_mua_shop  NUMERIC   OPTIONS(description='Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN — NULL trên BigQuery khi BQ_QC_XUAT_TIEN khác 1 (mặc định).'),
  chi_so            STRING    OPTIONS(description='Chuỗi JSON của cột JSONB chi_so bên Postgres: MỌI chỉ số nền tảng trả cho dòng {tên chỉ số: số} ("-" của TikTok → null; Meta: danh sách action thành <trường>__<action_type>, vd actions__purchase, action_values__purchase — reach, frequency, ctr, cpc, cpm, cpp, *roas* không cộng được qua dòng). Đọc bằng JSON_VALUE(chi_so, \'$.cpm\') hoặc PARSE_JSON(chi_so). Tài khoản/campaign: 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Khoá tiền (spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*) chỉ có khi dashboard đặt BQ_QC_XUAT_TIEN=1 (mặc định 0: bỏ khỏi chuỗi).'),
  cap_nhat_luc      TIMESTAMP OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery (đẩy dòng có cap_nhat_luc mới hơn lần trước).'),
  dong_bo_luc       TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
PARTITION BY den
CLUSTER BY advertiser_id, chieu
OPTIONS(description='''[Lớp] Raw
[Mục đích] Khán giả quảng cáo TikTok / Meta (tuổi, giới tính, tỉnh/thành, nền tảng) của tài khoản trong cửa sổ 30 ngày.
[Grain] 1 dòng = 1 tài khoản × 1 cửa sổ (tu..den) × 1 chiều × 1 giá trị
[Khoá] PK: advertiser_id + tu + den + chieu + gia_tri | Join: advertiser_id → tk_quang_cao.advertiser_id
[Nguồn] Postgres lang_nghe.public.qc_khan_gia trên VPS Mark; TikTok for Business MCP report_integrated_get (AUDIENCE, AUCTION_ADVERTISER); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Tài khoản đang đồng bộ có hiển thị trong 30 ngày | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 19/10/2026
[Đã xử lý] 13 chỉ số khán giả; cột không có trong báo cáo khán giả (reach, engaged_view…) NULL; "-" → NULL
[Refresh] MERGE theo khoá các dòng có cap_nhat_luc mới hơn mốc; nguồn đọc mỗi 7 ngày mỗi tài khoản (trong lượt 06:30 TikTok / 06:45 Meta giờ VN)
[Dùng khi] Phân bố hiển thị/xem theo tuổi, giới tính, tỉnh, nền tảng — chỉ lấy cửa sổ den mới nhất của từng tài khoản
[Không dùng khi] Số theo ngày → dùng SOCIAL_LISTENING.qc_tk_ngay; theo chiến dịch → dùng SOCIAL_LISTENING.qc_campaign_ngay
[Lưu ý] Các cửa sổ chồng nhau — KHÔNG cộng nhiều cửa sổ. province_id là mã vùng TikTok (GeoNames), -1 = không rõ.''');

-- Kiểm sau khi tạo: không còn mô tả rỗng.
-- SELECT table_name, option_value FROM `ganesha-381907.SOCIAL_LISTENING.INFORMATION_SCHEMA.TABLE_OPTIONS`
--   WHERE option_name = 'description';
-- SELECT table_name, column_name, description FROM `ganesha-381907.SOCIAL_LISTENING.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
--   WHERE description IS NULL OR TRIM(description) = '';

-- Kênh đăng của quảng cáo (22/10/2026, chủ dự án chốt): hai bảng mới, chạy cùng lúc với schema.sql
-- trên Postgres (dong_bo_bq đẩy qc_ad_kenh + qc_kenh sau qc_khan_gia; chưa chạy khối này thì hai bảng
-- báo lỗi trên trang Kết nối BigQuery, bảng khác vẫn đẩy). Không cột tiền.
CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.qc_ad_kenh`
(
  advertiser_id     STRING    OPTIONS(description='Tài khoản quảng cáo của ad (TikTok chuỗi số; Meta act_<số>). Một phần PK. FK → tk_quang_cao.advertiser_id.'),
  ad_id             STRING    OPTIONS(description='Mã quảng cáo (TikTok ad_id; Meta ad id). Một phần PK. Join: → qc_ad_ngay.ad_id (cùng advertiser_id).'),
  nen_tang          STRING    OPTIONS(description='Nền tảng: tiktok | meta. Không NULL.'),
  kenh_id           STRING    OPTIONS(description='Mã kênh đăng: TikTok identity_id (chuỗi số hoặc UUID); Meta id Trang Facebook (hoặc id Instagram khi ad không có Trang). Join: → qc_kenh.kenh_id (cùng nen_tang). NULL khi nền tảng không trả ad (loai khong_thay).'),
  loai              STRING    OPTIONS(description='Loại kênh. TikTok identity_type: AUTH_CODE (bài KOC uỷ quyền bằng mã — Spark Ads), BC_AUTH_TT (tài khoản TikTok gắn Business Center — chính chủ hoặc KOC), TT_USER (tài khoản TikTok chính chủ), CUSTOMIZED_USER (danh tính tuỳ chỉnh). Meta: page | instagram. khong_thay: nền tảng không trả ad. Không NULL.'),
  kenh_phu_id       STRING    OPTIONS(description='Kênh đi kèm: Meta id tài khoản Instagram (instagram_user_id) của ad chạy dưới Trang. Join: → qc_kenh.kenh_id. NULL với TikTok và khi ad Meta không gắn Instagram.'),
  bai_id            STRING    OPTIONS(description='Mã bài gốc của quảng cáo: TikTok tiktok_item_id (video), Meta effective_instagram_media_id. NULL khi nền tảng không trả.'),
  cap_nhat_luc      TIMESTAMP OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery.'),
  dong_bo_luc       TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
CLUSTER BY advertiser_id, kenh_id
OPTIONS(description='''[Lớp] Raw
[Mục đích] Kênh đăng của từng quảng cáo — danh tính quảng cáo chạy dưới tên: TikTok identity (chính chủ, KOC / Spark Ads), Meta Trang Facebook (+ Instagram đi kèm) — để tách số quảng cáo theo kênh.
[Grain] 1 dòng = 1 ad của 1 tài khoản quảng cáo
[Khoá] PK: advertiser_id + ad_id | Join: (advertiser_id, ad_id) → qc_ad_ngay; (nen_tang, kenh_id) → qc_kenh; (nen_tang, kenh_phu_id) → qc_kenh (Instagram)
[Nguồn] Postgres lang_nghe.public.qc_ad_kenh trên VPS Mark; TikTok for Business MCP tool_execute ad_get (identity_id, identity_type, tiktok_item_id); Meta Graph API GET act_<id>/ads (creative.actor_id, object_story_spec.page_id, instagram_user_id)
[Phạm vi] Ad có phân phối (có dòng qc_ad_ngay) của tài khoản đang đồng bộ | Kênh TikTok Ads + Meta Ads | Từ 22/10/2026 (đọc lùi mọi ad đã có số, chi nhiều trước)
[Đã xử lý] Một lần mỗi ad (kênh của ad không đổi); ad nền tảng không trả → kenh_id NULL, loai khong_thay (hỏi lại sau 7 ngày); Meta: kênh = Trang, không Trang mà có Instagram → kênh là Instagram
[Refresh] MERGE theo advertiser_id + ad_id các dòng có cap_nhat_luc mới hơn mốc, sau lượt đồng bộ TikTok 06:30 / Meta 06:45 giờ VN và 6 giờ một lần
[Dùng khi] Số quảng cáo theo kênh đăng (join qc_ad_ngay theo advertiser_id + ad_id); chi tiêu qua KOC / Spark Ads so với kênh chính chủ
[Không dùng khi] Tên kênh → dùng SOCIAL_LISTENING.qc_kenh; số theo ngày của ad → dùng SOCIAL_LISTENING.qc_ad_ngay
[Lưu ý] Ad chưa có dòng (chưa tới lượt đọc) hoặc kenh_id NULL = "Chưa xác định" trên dashboard — luôn LEFT JOIN từ qc_ad_ngay.''');

CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.qc_kenh`
(
  nen_tang          STRING    OPTIONS(description='Nền tảng: tiktok | meta. Một phần PK.'),
  kenh_id           STRING    OPTIONS(description='Mã kênh: TikTok identity_id; Meta id Trang hoặc id tài khoản Instagram. Một phần PK. Join: ← qc_ad_kenh.kenh_id, qc_ad_kenh.kenh_phu_id (cùng nen_tang).'),
  loai              STRING    OPTIONS(description='Loại kênh: TikTok identity_type (AUTH_CODE, BC_AUTH_TT, TT_USER, CUSTOMIZED_USER); Meta page | instagram. NULL khi chưa biết.'),
  ten               STRING    OPTIONS(description='Tên hiển thị: TikTok display_name; Meta tên Trang. NULL khi nền tảng không trả hoặc token Meta thiếu quyền pages_read_engagement.'),
  username          STRING    OPTIONS(description='Tên người dùng không @: TikTok username (thường NULL với AUTH_CODE); Meta username Instagram. NULL khi không có.'),
  cap_nhat_luc      TIMESTAMP OPTIONS(description='Lần bộ đồng bộ ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery.'),
  dong_bo_luc       TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
OPTIONS(description='''[Lớp] Dim
[Mục đích] Tên kênh đăng của quảng cáo (TikTok identity, Trang Facebook, tài khoản Instagram).
[Grain] 1 dòng = 1 kênh của 1 nền tảng
[Khoá] PK: nen_tang + kenh_id | Join: (nen_tang, kenh_id) ← qc_ad_kenh.kenh_id / qc_ad_kenh.kenh_phu_id
[Nguồn] Postgres lang_nghe.public.qc_kenh trên VPS Mark; TikTok for Business MCP identity_get (display_name, username); Meta Graph API GET /<id>?fields=name | username (cần pages_read_engagement)
[Phạm vi] TikTok: mọi danh tính của tài khoản có kênh chưa có tên (đo 22/10/2026: 1.951 danh tính ở MATEMADE MKT) | Meta: Trang / Instagram gặp trong qc_ad_kenh | Từ 22/10/2026
[Đã xử lý] Bỏ trùng theo identity_id; tên trống không ghi đè tên đã biết; ≤ 200 ký tự
[Refresh] MERGE theo nen_tang + kenh_id các dòng có cap_nhat_luc mới hơn mốc, sau lượt đồng bộ TikTok 06:30 / Meta 06:45 giờ VN và 6 giờ một lần
[Dùng khi] Gắn tên kênh vào số theo kênh (join từ qc_ad_kenh)
[Không dùng khi] Số theo kênh → dùng SOCIAL_LISTENING.qc_ad_kenh join SOCIAL_LISTENING.qc_ad_ngay; nguồn lắng nghe mạng xã hội → dùng SOCIAL_LISTENING.nguon
[Lưu ý] Meta: token thiếu pages_read_engagement thì không có dòng hoặc ten NULL (dashboard hiện "Page <id>" / "IG <id>").''');

-- Khán giả theo chiến dịch (26/10/2026, chủ dự án chốt): bảng mới, chạy cùng lúc với
-- deploy/lang-nghe/2026-10-26-khan-gia-cd.sql trên Postgres, TRƯỚC khi bật mã mới (dong_bo_bq đẩy
-- qc_khan_gia_cd sau qc_khan_gia; chưa chạy khối này thì bảng này báo lỗi trên trang Kết nối BigQuery,
-- bảng khác vẫn đẩy). Cột tiền theo BQ_QC_XUAT_TIEN như mọi bảng qc_*. Postgres chỉ giữ ~4 tuần cửa
-- sổ; BigQuery MERGE tăng dần, không xoá → giữ đủ lịch sử từ 26/10/2026.
CREATE TABLE IF NOT EXISTS `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia_cd`
(
  advertiser_id     STRING    OPTIONS(description='Tài khoản quảng cáo của chiến dịch (TikTok chuỗi số; Meta act_<số>). Một phần PK. FK → tk_quang_cao.advertiser_id.'),
  campaign_id       STRING    OPTIONS(description='Mã chiến dịch (TikTok campaign_id; Meta campaign id, chuỗi số). Một phần PK. Join: → qc_campaign_ngay.campaign_id (cùng advertiser_id).'),
  tu                DATE      OPTIONS(description='Ngày đầu cửa sổ 30 ngày (múi giờ tài khoản, thường GMT+7). Một phần PK.'),
  den               DATE      OPTIONS(description='Ngày cuối cửa sổ (múi giờ tài khoản, = hôm qua lúc đọc). Một phần PK. Cột phân vùng.'),
  chieu             STRING    OPTIONS(description='Chiều khán giả. Một phần PK. Giá trị: age, gender (TikTok + Meta), province_id, platform (TikTok: tỉnh, thiết bị), region, publisher_platform, platform_position (Meta).'),
  gia_tri           STRING    OPTIONS(description='Giá trị của chiều, cùng mã với qc_khan_gia.gia_tri: TikTok age AGE_13_17…AGE_55_100, NONE; gender FEMALE, MALE, NONE; province_id mã vùng số GeoNames (-1 không rõ; tên tỉnh ở dashboard/vung_tiktok.py); platform ANDROID, IPHONE, IPAD, WAP, UNKNOWN. Meta: age cùng mã TikTok tới 45–54, rồi 55-64, 65+; region tên vùng Meta; publisher_platform; platform_position <nền tảng>/<vị trí>. Một phần PK.'),
  chi               NUMERIC   OPTIONS(description='Chi tiêu quảng cáo (spend) của chiến dịch cho giá trị này, theo tiền tệ của tài khoản (tk_quang_cao.tien_te), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN — NULL trên BigQuery khi dashboard đặt BQ_QC_XUAT_TIEN khác 1.'),
  hien_thi          INT64     OPTIONS(description='Lượt hiển thị (impressions), lượt. Cộng được qua chiến dịch. NULL khi nền tảng không trả.'),
  reach             INT64     OPTIONS(description='Người tiếp cận (reach) của chiến dịch trong cửa sổ cho giá trị này, người. TikTok luôn NULL (báo cáo khán giả không trả). Cộng nhiều dòng / nhiều chiến dịch là đếm trùng người — muốn reach cả tài khoản dùng qc_khan_gia. NULL khi Meta gộp mã trùng.'),
  click             INT64     OPTIONS(description='Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.'),
  ket_qua           INT64     OPTIONS(description='Kết quả theo mục tiêu tối ưu: TikTok NULL (báo cáo khán giả không xin result); Meta luôn NULL. Giữ cột để cùng dạng với qc_khan_gia.'),
  chuyen_doi        INT64     OPTIONS(description='Chuyển đổi, lượt: TikTok conversion; Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — tên đầu tiên có). NULL khi nền tảng không trả hoặc Meta ẩn (quyền riêng tư).'),
  view_video        INT64     OPTIONS(description='Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.'),
  view_hai_giay     INT64     OPTIONS(description='Lượt xem ≥ 2 giây, lượt: TikTok NULL (báo cáo khán giả không xin video_watched_2s); Meta NULL.'),
  view_sau_giay     INT64     OPTIONS(description='Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  view_het          INT64     OPTIONS(description='Lượt xem hết video, lượt: TikTok NULL (báo cáo khán giả không xin video_views_p100); Meta video_p100_watched_actions. NULL khi nền tảng không trả.'),
  engaged_view      INT64     OPTIONS(description='Lượt xem tương tác, lượt: TikTok NULL (báo cáo khán giả không xin); Meta ThruPlay (video_thruplay_watched_actions). NULL khi nền tảng không trả.'),
  thich             INT64     OPTIONS(description='Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.'),
  binh_luan         INT64     OPTIONS(description='Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.'),
  chia_se           INT64     OPTIONS(description='Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.'),
  follow            INT64     OPTIONS(description='Lượt theo dõi từ quảng cáo, lượt: TikTok follows; Meta action like (thích Trang). NULL khi nền tảng không trả.'),
  vao_ho_so         INT64     OPTIONS(description='Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.'),
  mua_shop          INT64     OPTIONS(description='Lượt mua TikTok Shop gán cho quảng cáo, lượt mua: TikTok NULL (báo cáo khán giả không xin onsite_shopping); Meta NULL (lượt mua Meta ở chuyen_doi).'),
  gia_tri_mua_shop  NUMERIC   OPTIONS(description='Doanh thu gán cho quảng cáo theo tiền tệ tài khoản, chưa VAT: TikTok NULL (báo cáo khán giả không xin); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi), NULL khi Meta ẩn. CHỈ SỐ TIỀN — NULL trên BigQuery khi BQ_QC_XUAT_TIEN khác 1.'),
  chi_so            STRING    OPTIONS(description='Chuỗi JSON của cột JSONB chi_so bên Postgres: MỌI chỉ số nền tảng trả cho dòng {tên chỉ số: số} ("-" của TikTok → null; không gồm campaign_id và mã chiều). TikTok: 13 chỉ số khán giả; Meta: trường Insights đã xin, action thành <trường>__<action_type>. ctr, cpm, reach không cộng được qua dòng. Đọc bằng JSON_VALUE(chi_so, \'$.cpm\'). Khoá tiền (spend, cpm, *_value, action_values__*) chỉ có khi BQ_QC_XUAT_TIEN=1.'),
  cap_nhat_luc      TIMESTAMP OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery (đẩy dòng có cap_nhat_luc mới hơn lần trước).'),
  dong_bo_luc       TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
PARTITION BY den
CLUSTER BY advertiser_id, campaign_id, chieu
OPTIONS(description='''[Lớp] Raw
[Mục đích] Khán giả quảng cáo TikTok / Meta của TỪNG chiến dịch (tuổi, giới tính, tỉnh/thành, nền tảng) trong cửa sổ 30 ngày.
[Grain] 1 dòng = 1 chiến dịch × 1 cửa sổ (tu..den) × 1 chiều × 1 giá trị
[Khoá] PK: advertiser_id + campaign_id + tu + den + chieu + gia_tri | Join: advertiser_id → tk_quang_cao.advertiser_id; (advertiser_id, campaign_id) → qc_campaign_ngay
[Nguồn] Postgres lang_nghe.public.qc_khan_gia_cd trên VPS Mark; TikTok for Business MCP report_integrated_get (AUDIENCE, AUCTION_CAMPAIGN, chiều campaign_id + một chiều khán giả); Meta Ads: Graph API GET act_<id>/insights (level=campaign, breakdowns) — bộ đồng bộ dashboard/tiktok_ads.py, dashboard/meta_ads.py
[Phạm vi] Chiến dịch CÓ hiển thị trong cửa sổ (≤ 1.000 chiến dịch mỗi tài khoản, nhiều hiển thị trước) của tài khoản đang đồng bộ | Kênh TikTok Ads + Meta Ads | Từ 26/10/2026
[Đã xử lý] 13 chỉ số khán giả, cùng luật đổi số với qc_khan_gia; Meta mã trùng sau khi đổi (Unknown/unknown) cộng lại theo từng chiến dịch; cột không có trong báo cáo khán giả NULL; "-" → NULL
[Refresh] MERGE theo khoá các dòng có cap_nhat_luc mới hơn mốc, sau lượt đồng bộ TikTok 06:30 / Meta 06:45 giờ VN và 6 giờ một lần; nguồn đọc mỗi 7 ngày mỗi tài khoản; không xoá dòng khi Postgres dọn cửa sổ cũ
[Dùng khi] Khán giả của một hoặc vài chiến dịch — lấy cửa sổ den mới nhất của từng tài khoản rồi lọc campaign_id
[Không dùng khi] Khán giả cả tài khoản (reach không đếm trùng) → dùng SOCIAL_LISTENING.qc_khan_gia; số theo ngày của chiến dịch → dùng SOCIAL_LISTENING.qc_campaign_ngay
[Lưu ý] Các cửa sổ chồng nhau — KHÔNG cộng nhiều cửa sổ. Cộng nhiều chiến dịch: hiển thị / chi / bấm cộng được, reach thì đếm trùng người. Cửa sổ đọc lại cùng ngày (lệnh khan-gia) có thể còn dòng giá trị cũ mà lần đọc sau không còn.''');

-- ───────────── Meta Ads (20/10/2026) — NÂNG CẤP BẢNG ĐÃ TẠO (người duyệt rồi mới chạy) ─────────────
-- CREATE … IF NOT EXISTS ở trên không thêm cột / không đổi mô tả của bảng đã có: chạy các lệnh
-- dưới đây một lần TRƯỚC khi bật bản dashboard có Meta Ads (dong_bo_bq tự bỏ cột nen_tang / duyet
-- khỏi lượt + cảnh báo khi BigQuery chưa có — không hỏng cả bảng). Tiền đẩy theo BQ_QC_XUAT_TIEN (prod = 1).
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.tk_quang_cao`
  ADD COLUMN IF NOT EXISTS nen_tang STRING OPTIONS(description='Nền tảng quảng cáo. Giá trị: tiktok, meta (từ 20/10/2026). NULL ở dòng ghi trước khi dashboard đẩy cột này (lượt đồng bộ kế tiếp nạp lại toàn bảng).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.tk_quang_cao`
  ADD COLUMN IF NOT EXISTS duyet BOOL OPTIONS(description='TRUE: được đọc số (TikTok luôn TRUE; Meta = quản trị viên đã duyệt tài khoản). FALSE: tài khoản Meta chưa duyệt — không có số trong qc_*. NULL ở dòng ghi trước khi dashboard đẩy cột này.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.tk_quang_cao`
  SET OPTIONS(description='''[Lớp] Dim
[Mục đích] Danh sách tài khoản quảng cáo TikTok + Meta (Facebook/Instagram) dashboard đọc được và tài khoản thuộc bên nào (HAPAS, MATEMADE…).
[Grain] 1 dòng = 1 tài khoản quảng cáo (advertiser_id: TikTok advertiser hoặc Meta act_…)
[Khoá] PK: advertiser_id | Join: advertiser_id → qc_tk_ngay.advertiser_id, qc_campaign_ngay.advertiser_id, qc_ad_ngay.advertiser_id, qc_khan_gia.advertiser_id
[Nguồn] Postgres lang_nghe.public.tk_quang_cao trên VPS Mark; bộ đồng bộ TikTok Ads (TikTok for Business MCP: auth_advertiser_get + advertiser_info_get); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Mọi tài khoản quảng cáo người cấp quyền thấy được (19/10/2026: 16 tài khoản) | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 19/10/2026
[Đã xử lý] Gán bên tự động (tên có chữ THAI → chưa gán; MATEMADE / MATE MADE / MADEMATE → matemade; còn lại → hapas) trừ khi quản trị viên đã sửa tay (gan_tay); không đẩy email người sửa
[Refresh] MERGE nạp lại toàn bộ (xoá dòng không còn ở nguồn) sau mỗi lượt đồng bộ TikTok / Meta (06:30 / 06:45 giờ VN hằng ngày) và 6 giờ một lần
[Dùng khi] Gắn bên / tên / tiền tệ cho số quảng cáo; lọc tài khoản đang đồng bộ
[Không dùng khi] Số chi, hiển thị, xem → dùng SOCIAL_LISTENING.qc_tk_ngay; dự án lắng nghe → dùng SOCIAL_LISTENING.du_an
[Lưu ý] don_vi NULL = chưa gán bên. con_quyen false = token hiện tại không còn thấy tài khoản (số cũ vẫn giữ trong qc_*).''');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.tk_quang_cao`
  ALTER COLUMN advertiser_id SET OPTIONS(description='Mã tài khoản quảng cáo: TikTok chuỗi số; Meta act_<số> (từ 20/10/2026). PK. Join: → qc_*.advertiser_id.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.tk_quang_cao`
  ALTER COLUMN ten SET OPTIONS(description='Tên tài khoản trên nền tảng (TikTok advertiser_name; Meta name; đã bỏ khoảng trắng hai đầu), vd "MATEMADE MKT". Chuỗi rỗng khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.tk_quang_cao`
  ALTER COLUMN mui_gio SET OPTIONS(description='Múi giờ của tài khoản (TikTok display_timezone; Meta timezone_name; vd Asia/Ho_Chi_Minh) — ngày trong qc_* theo múi giờ này.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Số quảng cáo TikTok / Meta theo ngày của cả tài khoản: chi, hiển thị, xem video, tương tác, follow, doanh thu TikTok Shop.
[Grain] 1 dòng = 1 tài khoản quảng cáo × 1 ngày (múi giờ tài khoản, thường GMT+7)
[Khoá] PK: advertiser_id + ngay | Join: advertiser_id → tk_quang_cao.advertiser_id
[Nguồn] Postgres lang_nghe.public.qc_tk_ngay trên VPS Mark; TikTok for Business MCP report_integrated_get (BASIC, AUCTION_ADVERTISER, theo ngày); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Tài khoản tk_quang_cao đang đồng bộ | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 90 ngày trước lần kết nối đầu (nạp lùi)
[Đã xử lý] Chỉ ngày có hiển thị hoặc chi > 0; "-" của TikTok → NULL; tiền giữ tiền tệ gốc của tài khoản (tk_quang_cao.tien_te)
[Refresh] MERGE theo advertiser_id + ngay các dòng có cap_nhat_luc mới hơn mốc, ngay sau lượt đồng bộ TikTok 06:30 / Meta 06:45 giờ VN (đọc lại 7 ngày gần nhất) và 6 giờ một lần
[Dùng khi] Tổng chi/hiển thị/xem/tương tác theo ngày, tài khoản, bên (JOIN tk_quang_cao); ROAS Shop = SUM(gia_tri_mua_shop) / SUM(chi)
[Không dùng khi] Từng chiến dịch → dùng SOCIAL_LISTENING.qc_campaign_ngay; từng quảng cáo → dùng SOCIAL_LISTENING.qc_ad_ngay; tuổi/giới tính/tỉnh → dùng SOCIAL_LISTENING.qc_khan_gia
[Lưu ý] Chuyển đổi TikTok ghi trễ tới 7 ngày — số 7 ngày gần nhất còn đổi. reach cộng nhiều ngày là đếm trùng người. Cột tiền là dữ liệu nhạy cảm: chỉ chia cho quản trị viên + quản lý của bên.''');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN chi SET OPTIONS(description='Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy. NULL trên BigQuery khi dashboard đặt BQ_QC_XUAT_TIEN khác 1 (mặc định 0 — chưa đẩy tiền).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN hien_thi SET OPTIONS(description='Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN reach SET OPTIONS(description='Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN click SET OPTIONS(description='Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN ket_qua SET OPTIONS(description='Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN chuyen_doi SET OPTIONS(description='Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN view_video SET OPTIONS(description='Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN view_hai_giay SET OPTIONS(description='Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN view_sau_giay SET OPTIONS(description='Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN view_het SET OPTIONS(description='Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN engaged_view SET OPTIONS(description='Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN thich SET OPTIONS(description='Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN binh_luan SET OPTIONS(description='Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN chia_se SET OPTIONS(description='Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN follow SET OPTIONS(description='Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN vao_ho_so SET OPTIONS(description='Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN mua_shop SET OPTIONS(description='Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN gia_tri_mua_shop SET OPTIONS(description='Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN — NULL trên BigQuery khi BQ_QC_XUAT_TIEN khác 1 (mặc định).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN chi_so SET OPTIONS(description='Chuỗi JSON của cột JSONB chi_so bên Postgres: MỌI chỉ số nền tảng trả cho dòng {tên chỉ số: số} ("-" của TikTok → null; Meta: danh sách action thành <trường>__<action_type>, vd actions__purchase, action_values__purchase — reach, frequency, ctr, cpc, cpm, cpp, *roas* không cộng được qua dòng). Đọc bằng JSON_VALUE(chi_so, \'$.cpm\') hoặc PARSE_JSON(chi_so). Tài khoản/campaign: 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Khoá tiền (spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*) chỉ có khi dashboard đặt BQ_QC_XUAT_TIEN=1 (mặc định 0: bỏ khỏi chuỗi).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_tk_ngay`
  ALTER COLUMN cap_nhat_luc SET OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery (đẩy dòng có cap_nhat_luc mới hơn lần trước).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Số quảng cáo TikTok / Meta theo ngày của từng chiến dịch có phân phối — xếp hạng chiến dịch.
[Grain] 1 dòng = 1 campaign × 1 ngày (múi giờ tài khoản)
[Khoá] PK: campaign_id + ngay | Join: advertiser_id → tk_quang_cao.advertiser_id; campaign_id → qc_ad_ngay.campaign_id
[Nguồn] Postgres lang_nghe.public.qc_campaign_ngay trên VPS Mark; TikTok for Business MCP report_integrated_get (BASIC, AUCTION_CAMPAIGN, theo ngày); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Tài khoản đang đồng bộ, chỉ campaign có hiển thị trong cửa sổ đọc | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 90 ngày trước lần kết nối đầu
[Đã xử lý] Chỉ campaign có impressions > 0 trong cửa sổ đọc, chỉ ngày có hiển thị hoặc chi > 0; "-" → NULL
[Refresh] MERGE theo campaign_id + ngay các dòng có cap_nhat_luc mới hơn mốc, sau lượt đồng bộ TikTok 06:30 / Meta 06:45 giờ VN và 6 giờ một lần
[Dùng khi] Top chiến dịch trong kỳ; chi/hiển thị/xem theo chiến dịch
[Không dùng khi] Tổng tài khoản → dùng SOCIAL_LISTENING.qc_tk_ngay; từng quảng cáo → dùng SOCIAL_LISTENING.qc_ad_ngay
[Lưu ý] ten / muc_tieu là giá trị lúc đọc từng ngày — lấy tên của ngày mới nhất. Ngân sách chiến dịch chỉ trong chi_so (campaign_budget, tiền).''');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN campaign_id SET OPTIONS(description='Mã campaign (TikTok campaign_id; Meta campaign_id). Một phần PK. Join: → qc_ad_ngay.campaign_id.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN muc_tieu SET OPTIONS(description='Mục tiêu campaign (objective_type), vd REACH, VIDEO_VIEWS, PRODUCT_SALES, ENGAGEMENT. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN chi SET OPTIONS(description='Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy. NULL trên BigQuery khi dashboard đặt BQ_QC_XUAT_TIEN khác 1 (mặc định 0 — chưa đẩy tiền).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN hien_thi SET OPTIONS(description='Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN reach SET OPTIONS(description='Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN click SET OPTIONS(description='Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN ket_qua SET OPTIONS(description='Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN chuyen_doi SET OPTIONS(description='Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN view_video SET OPTIONS(description='Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN view_hai_giay SET OPTIONS(description='Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN view_sau_giay SET OPTIONS(description='Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN view_het SET OPTIONS(description='Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN engaged_view SET OPTIONS(description='Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN thich SET OPTIONS(description='Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN binh_luan SET OPTIONS(description='Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN chia_se SET OPTIONS(description='Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN follow SET OPTIONS(description='Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN vao_ho_so SET OPTIONS(description='Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN mua_shop SET OPTIONS(description='Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN gia_tri_mua_shop SET OPTIONS(description='Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN — NULL trên BigQuery khi BQ_QC_XUAT_TIEN khác 1 (mặc định).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN chi_so SET OPTIONS(description='Chuỗi JSON của cột JSONB chi_so bên Postgres: MỌI chỉ số nền tảng trả cho dòng {tên chỉ số: số} ("-" của TikTok → null; Meta: danh sách action thành <trường>__<action_type>, vd actions__purchase, action_values__purchase — reach, frequency, ctr, cpc, cpm, cpp, *roas* không cộng được qua dòng). Đọc bằng JSON_VALUE(chi_so, \'$.cpm\') hoặc PARSE_JSON(chi_so). Tài khoản/campaign: 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Khoá tiền (spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*) chỉ có khi dashboard đặt BQ_QC_XUAT_TIEN=1 (mặc định 0: bỏ khỏi chuỗi).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_campaign_ngay`
  ALTER COLUMN cap_nhat_luc SET OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery (đẩy dòng có cap_nhat_luc mới hơn lần trước).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Số quảng cáo TikTok / Meta theo ngày của từng quảng cáo (ad) có phân phối — top quảng cáo/video.
[Grain] 1 dòng = 1 ad × 1 ngày (múi giờ tài khoản)
[Khoá] PK: ad_id + ngay | Join: advertiser_id → tk_quang_cao.advertiser_id; campaign_id → qc_campaign_ngay.campaign_id
[Nguồn] Postgres lang_nghe.public.qc_ad_ngay trên VPS Mark; TikTok for Business MCP report_integrated_get (BASIC, AUCTION_AD, theo ngày); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Tài khoản đang đồng bộ, CHỈ ad có hiển thị trong cửa sổ đọc | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 90 ngày trước lần kết nối đầu
[Đã xử lý] Chỉ ad có impressions > 0 trong cửa sổ đọc, chỉ ngày có hiển thị hoặc chi > 0; chi_so gồm 38 chỉ số chính (không đủ 100 như tài khoản/campaign); "-" → NULL
[Refresh] MERGE theo ad_id + ngay các dòng có cap_nhat_luc mới hơn mốc, sau lượt đồng bộ TikTok 06:30 / Meta 06:45 giờ VN và 6 giờ một lần
[Dùng khi] Top quảng cáo trong kỳ; nội dung nào kéo xem/follow
[Không dùng khi] Tổng tài khoản → dùng SOCIAL_LISTENING.qc_tk_ngay; chiến dịch → dùng SOCIAL_LISTENING.qc_campaign_ngay
[Lưu ý] Bảng lớn nhất (hàng nghìn dòng mỗi ngày với tài khoản lớn) — luôn lọc theo ngay (cột phân vùng).''');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN campaign_id SET OPTIONS(description='Campaign chứa ad. Join: → qc_campaign_ngay.campaign_id. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN adgroup_id SET OPTIONS(description='Nhóm quảng cáo (ad group) chứa ad. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN ad_id SET OPTIONS(description='Mã quảng cáo (TikTok ad_id; Meta ad_id). Một phần PK.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN chi SET OPTIONS(description='Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy. NULL trên BigQuery khi dashboard đặt BQ_QC_XUAT_TIEN khác 1 (mặc định 0 — chưa đẩy tiền).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN hien_thi SET OPTIONS(description='Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN reach SET OPTIONS(description='Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN click SET OPTIONS(description='Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN ket_qua SET OPTIONS(description='Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN chuyen_doi SET OPTIONS(description='Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN view_video SET OPTIONS(description='Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN view_hai_giay SET OPTIONS(description='Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN view_sau_giay SET OPTIONS(description='Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN view_het SET OPTIONS(description='Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN engaged_view SET OPTIONS(description='Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN thich SET OPTIONS(description='Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN binh_luan SET OPTIONS(description='Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN chia_se SET OPTIONS(description='Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN follow SET OPTIONS(description='Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN vao_ho_so SET OPTIONS(description='Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN mua_shop SET OPTIONS(description='Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN gia_tri_mua_shop SET OPTIONS(description='Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN — NULL trên BigQuery khi BQ_QC_XUAT_TIEN khác 1 (mặc định).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN chi_so SET OPTIONS(description='Chuỗi JSON của cột JSONB chi_so bên Postgres: MỌI chỉ số nền tảng trả cho dòng {tên chỉ số: số} ("-" của TikTok → null; Meta: danh sách action thành <trường>__<action_type>, vd actions__purchase, action_values__purchase — reach, frequency, ctr, cpc, cpm, cpp, *roas* không cộng được qua dòng). Đọc bằng JSON_VALUE(chi_so, \'$.cpm\') hoặc PARSE_JSON(chi_so). Tài khoản/campaign: 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Khoá tiền (spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*) chỉ có khi dashboard đặt BQ_QC_XUAT_TIEN=1 (mặc định 0: bỏ khỏi chuỗi).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_ad_ngay`
  ALTER COLUMN cap_nhat_luc SET OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery (đẩy dòng có cap_nhat_luc mới hơn lần trước).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  SET OPTIONS(description='''[Lớp] Raw
[Mục đích] Khán giả quảng cáo TikTok / Meta (tuổi, giới tính, tỉnh/thành, nền tảng) của tài khoản trong cửa sổ 30 ngày.
[Grain] 1 dòng = 1 tài khoản × 1 cửa sổ (tu..den) × 1 chiều × 1 giá trị
[Khoá] PK: advertiser_id + tu + den + chieu + gia_tri | Join: advertiser_id → tk_quang_cao.advertiser_id
[Nguồn] Postgres lang_nghe.public.qc_khan_gia trên VPS Mark; TikTok for Business MCP report_integrated_get (AUDIENCE, AUCTION_ADVERTISER); Meta Ads: Graph API GET (me/adaccounts, act_<id>/insights) — bộ đồng bộ dashboard/meta_ads.py
[Phạm vi] Tài khoản đang đồng bộ có hiển thị trong 30 ngày | Kênh TikTok Ads + Meta Ads (từ 20/10/2026) | Từ 19/10/2026
[Đã xử lý] 13 chỉ số khán giả; cột không có trong báo cáo khán giả (reach, engaged_view…) NULL; "-" → NULL
[Refresh] MERGE theo khoá các dòng có cap_nhat_luc mới hơn mốc; nguồn đọc mỗi 7 ngày mỗi tài khoản (trong lượt 06:30 TikTok / 06:45 Meta giờ VN)
[Dùng khi] Phân bố hiển thị/xem theo tuổi, giới tính, tỉnh, nền tảng — chỉ lấy cửa sổ den mới nhất của từng tài khoản
[Không dùng khi] Số theo ngày → dùng SOCIAL_LISTENING.qc_tk_ngay; theo chiến dịch → dùng SOCIAL_LISTENING.qc_campaign_ngay
[Lưu ý] Các cửa sổ chồng nhau — KHÔNG cộng nhiều cửa sổ. province_id là mã vùng TikTok (GeoNames), -1 = không rõ.''');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN chieu SET OPTIONS(description='Chiều khán giả. Một phần PK. Giá trị: age, gender (TikTok + Meta), province_id, platform (TikTok: tỉnh, thiết bị), region, publisher_platform, platform_position (Meta, từ 20/10/2026).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN gia_tri SET OPTIONS(description='Giá trị của chiều (mã TikTok): age AGE_13_17…AGE_55_100, NONE; gender FEMALE, MALE, NONE; province_id mã vùng số (-1 không rõ); platform ANDROID, IPHONE, IPAD, WAP, UNKNOWN. Meta: age cùng mã TikTok tới 45–54, rồi 55-64, 65+; gender FEMALE, MALE, NONE; region tên vùng Meta; publisher_platform facebook, instagram, messenger, audience_network, threads; platform_position <nền tảng>/<vị trí>. Một phần PK.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN chi SET OPTIONS(description='Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy. NULL trên BigQuery khi dashboard đặt BQ_QC_XUAT_TIEN khác 1 (mặc định 0 — chưa đẩy tiền).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN hien_thi SET OPTIONS(description='Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN reach SET OPTIONS(description='Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN click SET OPTIONS(description='Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN ket_qua SET OPTIONS(description='Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN chuyen_doi SET OPTIONS(description='Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN view_video SET OPTIONS(description='Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN view_hai_giay SET OPTIONS(description='Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN view_sau_giay SET OPTIONS(description='Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN view_het SET OPTIONS(description='Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN engaged_view SET OPTIONS(description='Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN thich SET OPTIONS(description='Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN binh_luan SET OPTIONS(description='Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN chia_se SET OPTIONS(description='Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN follow SET OPTIONS(description='Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN vao_ho_so SET OPTIONS(description='Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN mua_shop SET OPTIONS(description='Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN gia_tri_mua_shop SET OPTIONS(description='Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN — NULL trên BigQuery khi BQ_QC_XUAT_TIEN khác 1 (mặc định).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN chi_so SET OPTIONS(description='Chuỗi JSON của cột JSONB chi_so bên Postgres: MỌI chỉ số nền tảng trả cho dòng {tên chỉ số: số} ("-" của TikTok → null; Meta: danh sách action thành <trường>__<action_type>, vd actions__purchase, action_values__purchase — reach, frequency, ctr, cpc, cpm, cpp, *roas* không cộng được qua dòng). Đọc bằng JSON_VALUE(chi_so, \'$.cpm\') hoặc PARSE_JSON(chi_so). Tài khoản/campaign: 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Khoá tiền (spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*) chỉ có khi dashboard đặt BQ_QC_XUAT_TIEN=1 (mặc định 0: bỏ khỏi chuỗi).');
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.qc_khan_gia`
  ALTER COLUMN cap_nhat_luc SET OPTIONS(description='Lần bộ đồng bộ TikTok / Meta ghi/sửa dòng ở Postgres (UTC) — mốc đẩy BigQuery (đẩy dòng có cap_nhat_luc mới hơn lần trước).');

-- KOC gắn giỏ / KOC branding (20/10/2026, task Lark t284905, PA1): bảng đã tạo trước thì thêm hai
-- cột cờ TikTok (dong_bo_bq MERGE cả hai khi cả Postgres lẫn BigQuery đã có cột — `tuy_chon`; chưa
-- chạy khối này thì đồng bộ bỏ hai cột, kèm cảnh báo). Chạy cùng lúc với schema.sql trên Postgres.
ALTER TABLE `ganesha-381907.SOCIAL_LISTENING.bai`
  ADD COLUMN IF NOT EXISTS gio_hang BOOL OPTIONS(description='Chỉ TikTok: TRUE = video gắn giỏ TikTok Shop (KOC affiliate trên dashboard), FALSE = không gắn giỏ (KOC branding), theo từng video. Đọc từ tìm kiếm / hồ sơ TikTok (anchors không có shop, kể cả anchors trống = FALSE); feed hashtag chỉ báo được TRUE (không bao giờ trả anchor shop, đo 21/10/2026). NULL = chưa rõ: video chỉ thấy ở feed hashtag, nguồn không báo, hoặc nền tảng khác — không phải FALSE. TRUE không bị lần đọc sau hạ; bài trước 20/10/2026 điền bằng scripts/lang_nghe_nap_gio_hang.py.'),
  ADD COLUMN IF NOT EXISTS la_quang_cao BOOL OPTIONS(description='Chỉ TikTok: TRUE = TikTok đánh dấu video là quảng cáo (is_ads / isAd), FALSE = không. NULL = nguồn không báo hoặc nền tảng khác. Không dùng để tách KOC (tiêu chí là gio_hang).');
