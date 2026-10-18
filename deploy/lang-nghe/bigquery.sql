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
  dong_bo_luc     TIMESTAMP OPTIONS(description='Thời điểm dòng được dashboard ghi vào BigQuery lần gần nhất, UTC.')
)
CLUSTER BY du_an, nen_tang
OPTIONS(description='''[Lớp] Raw
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
  kieu            STRING    OPTIONS(description='Giá trị: theo_doi (lượt /theodoi quét nguồn, tính vào trần tháng), tu_khoa (lượt tìm theo từ khoá ghi vào kho).'),
  ma_viec         STRING    OPTIONS(description='Mã việc nền của Mark (vd t10140830-ab12c), đối chiếu với /viec. NULL khi lượt không chạy qua việc nền.'),
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

-- Kiểm sau khi tạo: không còn mô tả rỗng.
-- SELECT table_name, option_value FROM `ganesha-381907.SOCIAL_LISTENING.INFORMATION_SCHEMA.TABLE_OPTIONS`
--   WHERE option_name = 'description';
-- SELECT table_name, column_name, description FROM `ganesha-381907.SOCIAL_LISTENING.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
--   WHERE description IS NULL OR TRIM(description) = '';
