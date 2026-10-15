-- Kho dữ liệu lắng nghe MXH (đợt 2, chủ dự án chốt 14/10/2026): DB `lang_nghe` trên Postgres 16
-- của VPS Mark. Chạy lại nhiều lần không hỏng (IF NOT EXISTS / DO $$ … $$).
--
--   sudo -u postgres psql -v ON_ERROR_STOP=1 -f deploy/lang-nghe/schema.sql
--
-- Vì sao DB riêng trên VPS mà không để trên platform: quyết định 0008 của platform (platform chỉ
-- giữ control + audit; dữ liệu xử lý nằm ở làn của agent) — chủ dự án chốt "mark vẫn phải theo
-- luật của platform như trước không đổi". Kỹ năng, công tắc, trần mỗi lượt, lịch của Mark VẪN ở
-- console platform; DB này chỉ giữ dự án, nguồn theo dõi, ngân sách tháng, bài đã quét.
--
-- Ba role, đăng nhập bằng Unix socket + peer (không mật khẩu, không mở cổng):
--   lang_nghe_chu  — sở hữu bảng (NOLOGIN), chỉ dùng để chạy file này.
--   mark           — user hệ điều hành của bot: ĐỌC dự án/nguồn, GHI bài/lượt quét/đề xuất.
--   lang_nghe_web  — user hệ điều hành của dashboard: quản lý dự án/nguồn/người xem, đọc mọi thứ.

\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lang_nghe_chu') THEN
    CREATE ROLE lang_nghe_chu NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mark') THEN
    CREATE ROLE mark LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lang_nghe_web') THEN
    CREATE ROLE lang_nghe_web LOGIN;
  END IF;
END $$;

SELECT 'CREATE DATABASE lang_nghe OWNER lang_nghe_chu ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'lang_nghe') \gexec

\connect lang_nghe

REVOKE ALL ON DATABASE lang_nghe FROM PUBLIC;
GRANT CONNECT ON DATABASE lang_nghe TO mark, lang_nghe_web;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO mark, lang_nghe_web;
GRANT CREATE ON SCHEMA public TO lang_nghe_chu;

SET ROLE lang_nghe_chu;

-- 1 dòng = 1 dự án/brand. `ma` là chữ gõ sau /theodoi (vd "hapas").
CREATE TABLE IF NOT EXISTS du_an (
  ma              TEXT PRIMARY KEY CHECK (ma ~ '^[a-z0-9][a-z0-9_-]{1,39}$'),
  ten             TEXT NOT NULL,
  tu_khoa         TEXT[] NOT NULL DEFAULT '{}',   -- bài phải nhắc ít nhất một (trừ kênh nhà)
  tu_loai_tru     TEXT[] NOT NULL DEFAULT '{}',   -- có thì loại cứng, không qua AI
  boi_canh        TEXT NOT NULL DEFAULT '',       -- mô tả brand cho bước AI phân xử
  thi_truong      TEXT NOT NULL DEFAULT 'VN' CHECK (thi_truong ~ '^[A-Z]{2}$'),
  tran_usd_thang  NUMERIC(8,2) NOT NULL DEFAULT 5 CHECK (tran_usd_thang >= 0),
  dang_bat        BOOLEAN NOT NULL DEFAULT TRUE,
  tao_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
  sua_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
  sua_boi         TEXT,
  bl_bat          BOOLEAN NOT NULL DEFAULT TRUE,
  bl_so_bai       INT NOT NULL DEFAULT 10 CHECK (bl_so_bai >= 0),
  bl_moi_bai      INT NOT NULL DEFAULT 0 CHECK (bl_moi_bai = 0 OR bl_moi_bai >= 5),
  tk_bat          BOOLEAN NOT NULL DEFAULT TRUE,
  tk_so_bai       INT NOT NULL DEFAULT 15 CHECK (tk_so_bai >= 0),
  cau_hinh        JSONB NOT NULL DEFAULT '{}'::jsonb
);
-- Đợt 2b (15/10/2026): cào bình luận — DB đã tạo trước đó thì thêm cột ở đây.
ALTER TABLE du_an ADD COLUMN IF NOT EXISTS bl_bat BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE du_an ADD COLUMN IF NOT EXISTS bl_so_bai INT NOT NULL DEFAULT 10
  CHECK (bl_so_bai >= 0);
ALTER TABLE du_an ADD COLUMN IF NOT EXISTS bl_moi_bai INT NOT NULL DEFAULT 0;
-- Đợt 2d (15/10/2026): 0 = cào HẾT bình luận của bài (chủ dự án). Đổi ràng buộc cũ (5–200).
ALTER TABLE du_an DROP CONSTRAINT IF EXISTS du_an_bl_moi_bai_check;
ALTER TABLE du_an ADD CONSTRAINT du_an_bl_moi_bai_check
  CHECK (bl_moi_bai = 0 OR bl_moi_bai >= 5);
ALTER TABLE du_an ALTER COLUMN bl_moi_bai SET DEFAULT 0;
-- Đợt 2c (15/10/2026): tìm theo từ khoá trong mỗi lượt /theodoi.
ALTER TABLE du_an ADD COLUMN IF NOT EXISTS tk_bat BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE du_an ADD COLUMN IF NOT EXISTS tk_so_bai INT NOT NULL DEFAULT 15
  CHECK (tk_so_bai >= 0);
-- Đợt 2e (15/10/2026): cấu hình thu thập theo TỪNG nền tảng, sửa trên dashboard.
ALTER TABLE du_an ADD COLUMN IF NOT EXISTS cau_hinh JSONB NOT NULL DEFAULT '{}'::jsonb;
-- Chủ dự án 15/10: "không có giới hạn" — bỏ trần trên của số bài / trần tháng; tiền vẫn chặn
-- bằng trần tháng của dự án + trần mỗi lượt trên console.
ALTER TABLE du_an DROP CONSTRAINT IF EXISTS du_an_bl_moi_bai_check;
ALTER TABLE du_an ADD CONSTRAINT du_an_bl_moi_bai_check CHECK (bl_moi_bai = 0 OR bl_moi_bai >= 5);
ALTER TABLE du_an DROP CONSTRAINT IF EXISTS du_an_bl_so_bai_check;
ALTER TABLE du_an ADD CONSTRAINT du_an_bl_so_bai_check CHECK (bl_so_bai >= 0);
ALTER TABLE du_an DROP CONSTRAINT IF EXISTS du_an_tk_so_bai_check;
ALTER TABLE du_an ADD CONSTRAINT du_an_tk_so_bai_check CHECK (tk_so_bai >= 0);
ALTER TABLE du_an DROP CONSTRAINT IF EXISTS du_an_tran_usd_thang_check;
ALTER TABLE du_an ADD CONSTRAINT du_an_tran_usd_thang_check CHECK (tran_usd_thang >= 0);

-- 1 dòng = 1 nguồn theo dõi. `dinh_danh`: username TikTok/Instagram, kênh YouTube (UC… hoặc
-- @handle), URL trang Facebook — đã chuẩn hoá chữ thường (trừ id kênh YouTube UC…).
CREATE TABLE IF NOT EXISTS nguon (
  id              BIGSERIAL PRIMARY KEY,
  du_an           TEXT NOT NULL REFERENCES du_an(ma) ON UPDATE CASCADE,
  nen_tang        TEXT NOT NULL CHECK (nen_tang IN ('tiktok', 'instagram', 'youtube', 'facebook')),
  dinh_danh       TEXT NOT NULL CHECK (length(dinh_danh) BETWEEN 2 AND 200),
  ten             TEXT NOT NULL DEFAULT '',
  link            TEXT NOT NULL DEFAULT '',
  loai            TEXT NOT NULL DEFAULT 'khac'
                  CHECK (loai IN ('kol', 'page', 'group', 'bao', 'kenh_nha', 'khac')),
  nhan            TEXT[] NOT NULL DEFAULT '{}',
  trang_thai      TEXT NOT NULL DEFAULT 'dang_theo_doi' CHECK (trang_thai IN ('dang_theo_doi', 'tam_dung')),
  chu_ky_ngay     INT NOT NULL DEFAULT 1 CHECK (chu_ky_ngay BETWEEN 1 AND 30),
  so_bai_moi_lan  INT NOT NULL DEFAULT 5 CHECK (so_bai_moi_lan >= 1),
  them_qua        TEXT NOT NULL DEFAULT 'dashboard' CHECK (them_qua IN ('dashboard', 'de_xuat', 'nhap_file')),
  them_boi        TEXT,
  them_luc        TIMESTAMPTZ NOT NULL DEFAULT now(),
  quet_cuoi       TIMESTAMPTZ,
  loi_cuoi        TEXT,
  loi_luc         TIMESTAMPTZ,
  UNIQUE (du_an, nen_tang, dinh_danh)
);

-- 1 dòng = 1 nguồn Mark thấy nổi khi quét mà chưa nằm trong danh sách. Người duyệt trên
-- dashboard; Mark KHÔNG tự thêm nguồn.
CREATE TABLE IF NOT EXISTS de_xuat (
  id              BIGSERIAL PRIMARY KEY,
  du_an           TEXT NOT NULL REFERENCES du_an(ma) ON UPDATE CASCADE,
  nen_tang        TEXT NOT NULL,
  dinh_danh       TEXT NOT NULL,
  ten             TEXT NOT NULL DEFAULT '',
  link            TEXT NOT NULL DEFAULT '',
  ly_do           TEXT NOT NULL DEFAULT '',
  so_bai          INT NOT NULL DEFAULT 0,
  thao_luan       BIGINT NOT NULL DEFAULT 0,
  trang_thai      TEXT NOT NULL DEFAULT 'cho' CHECK (trang_thai IN ('cho', 'da_duyet', 'tu_choi')),
  de_xuat_luc     TIMESTAMPTZ NOT NULL DEFAULT now(),
  xu_ly_boi       TEXT,
  xu_ly_luc       TIMESTAMPTZ,
  UNIQUE (du_an, nen_tang, dinh_danh)
);

-- 1 dòng = 1 lượt quét. Tiền thật (`chi_phi_usd`) cộng dồn theo tháng giờ VN là "đã tiêu"
-- của ngân sách theo dõi; chỉ lượt kieu = 'theo_doi' tính vào trần tháng của dự án.
CREATE TABLE IF NOT EXISTS luot_quet (
  id              BIGSERIAL PRIMARY KEY,
  du_an           TEXT NOT NULL REFERENCES du_an(ma) ON UPDATE CASCADE,
  kieu            TEXT NOT NULL CHECK (kieu IN ('theo_doi', 'tu_khoa')),
  ma_viec         TEXT,
  job_id          TEXT,
  bat_dau         TIMESTAMPTZ NOT NULL DEFAULT now(),
  ket_thuc        TIMESTAMPTZ,
  so_nguon        INT NOT NULL DEFAULT 0,
  so_nguon_loi    INT NOT NULL DEFAULT 0,
  bai_moi         INT NOT NULL DEFAULT 0,
  bai_cap_nhat    INT NOT NULL DEFAULT 0,
  chi_phi_usd     NUMERIC(10,4) NOT NULL DEFAULT 0,
  trang_thai      TEXT NOT NULL DEFAULT 'dang_chay'
                  CHECK (trang_thai IN ('dang_chay', 'xong', 'mot_phan', 'loi', 'da_huy')),
  loi             TEXT,
  ghi_chu         TEXT
);
CREATE INDEX IF NOT EXISTS luot_quet_du_an_bat_dau ON luot_quet (du_an, bat_dau);

-- 1 dòng = 1 bài ĐÃ GIỮ × 1 dự án. Khoá bài "<nền tảng>:<id bài>"; cùng một bài có thể liên
-- quan tới hai dự án (brand và đối thủ) nên khoá chính gồm cả dự án. Số liệu là lần đọc mới
-- nhất; lịch sử theo ngày ở `chi_so_ngay`.
CREATE TABLE IF NOT EXISTS bai (
  du_an           TEXT NOT NULL REFERENCES du_an(ma) ON UPDATE CASCADE,
  khoa            TEXT NOT NULL,
  nen_tang        TEXT NOT NULL,
  nguon_id        BIGINT REFERENCES nguon(id) ON DELETE SET NULL,
  kieu_quet       TEXT NOT NULL CHECK (kieu_quet IN ('theo_doi', 'tu_khoa')),
  link            TEXT NOT NULL,
  tac_gia         TEXT NOT NULL DEFAULT '',
  tai_khoan       TEXT NOT NULL DEFAULT '',
  followers       BIGINT,
  dang_luc        TIMESTAMPTZ,
  noi_dung        TEXT NOT NULL DEFAULT '',
  hashtag         TEXT NOT NULL DEFAULT '',
  khop_tu_khoa    BOOLEAN NOT NULL DEFAULT FALSE,
  sac_thai        TEXT,
  chu_de          TEXT,
  ly_do_giu       TEXT,
  xem             BIGINT,
  thich           BIGINT,
  binh_luan       BIGINT,
  chia_se         BIGINT,
  thay_lan_dau    TIMESTAMPTZ NOT NULL DEFAULT now(),
  cap_nhat_cuoi   TIMESTAMPTZ NOT NULL DEFAULT now(),
  luot_dau        BIGINT REFERENCES luot_quet(id) ON DELETE SET NULL,
  luot_cuoi       BIGINT REFERENCES luot_quet(id) ON DELETE SET NULL,
  bl_lay_luc      TIMESTAMPTZ,
  bl_da_lay       INT,
  bl_lay_khi_co   BIGINT,
  ma_noi_dung     TEXT,
  bl_lan_thieu    INT NOT NULL DEFAULT 0,
  PRIMARY KEY (du_an, khoa)
);
CREATE INDEX IF NOT EXISTS bai_du_an_dang_luc ON bai (du_an, dang_luc);
CREATE INDEX IF NOT EXISTS bai_nguon ON bai (nguon_id);
ALTER TABLE bai ADD COLUMN IF NOT EXISTS bl_lay_luc TIMESTAMPTZ;
ALTER TABLE bai ADD COLUMN IF NOT EXISTS bl_da_lay INT;
ALTER TABLE bai ADD COLUMN IF NOT EXISTS bl_lay_khi_co BIGINT;
ALTER TABLE bai ADD COLUMN IF NOT EXISTS ma_noi_dung TEXT;
ALTER TABLE bai ADD COLUMN IF NOT EXISTS bl_lan_thieu INT NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS bai_ma_noi_dung ON bai (du_an, ma_noi_dung);

-- 1 dòng = 1 bình luận (hoặc trả lời) Mark đã cào của một bài đã giữ. Đợt 2b (15/10/2026):
-- Kompa đếm "thảo luận" chủ yếu từ bình luận dưới bài của các trang — đọc được nội dung mới
-- gán sắc thái/chủ đề được tiếng khách. Bình luận của chính thương hiệu giữ lại nhưng không
-- gán nhãn, không tính vào sắc thái.
CREATE TABLE IF NOT EXISTS binh_luan (
  du_an           TEXT NOT NULL,
  khoa_bai        TEXT NOT NULL,
  ma              TEXT NOT NULL,
  nen_tang        TEXT NOT NULL,
  tac_gia         TEXT NOT NULL DEFAULT '',
  noi_dung        TEXT NOT NULL DEFAULT '',
  thich           BIGINT,
  tra_loi         BIGINT,
  la_tra_loi      BOOLEAN NOT NULL DEFAULT FALSE,
  cua_thuong_hieu BOOLEAN NOT NULL DEFAULT FALSE,
  dang_luc        TIMESTAMPTZ,
  sac_thai        TEXT,
  chu_de          TEXT,
  luot_id         BIGINT REFERENCES luot_quet(id) ON DELETE SET NULL,
  thay_lan_dau    TIMESTAMPTZ NOT NULL DEFAULT now(),
  cap_nhat_cuoi   TIMESTAMPTZ NOT NULL DEFAULT now(),
  loai            TEXT NOT NULL DEFAULT 'hop_le'
                  CHECK (loai IN ('hop_le', 'it_noi_dung', 'spam', 'trung', 'seeding', 'thuong_hieu')),
  ly_do_loc       TEXT,
  ma_noi_dung     TEXT,
  link            TEXT,
  ma_cha          TEXT,
  PRIMARY KEY (du_an, khoa_bai, ma),
  FOREIGN KEY (du_an, khoa_bai) REFERENCES bai (du_an, khoa) ON UPDATE CASCADE ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS binh_luan_du_an_dang_luc ON binh_luan (du_an, dang_luc);
CREATE INDEX IF NOT EXISTS binh_luan_cap_nhat ON binh_luan (cap_nhat_cuoi);
-- Đợt 2d (15/10/2026): nhãn lọc spam/rác/trùng (loc_rac.py) — DB đã tạo trước thì thêm cột.
ALTER TABLE binh_luan ADD COLUMN IF NOT EXISTS loai TEXT NOT NULL DEFAULT 'hop_le'
  CHECK (loai IN ('hop_le', 'it_noi_dung', 'spam', 'trung', 'seeding', 'thuong_hieu'));
ALTER TABLE binh_luan ADD COLUMN IF NOT EXISTS ly_do_loc TEXT;
ALTER TABLE binh_luan ADD COLUMN IF NOT EXISTS ma_noi_dung TEXT;
CREATE INDEX IF NOT EXISTS binh_luan_ma_noi_dung ON binh_luan (du_an, ma_noi_dung);
-- Đợt 2e (15/10/2026): link tới bình luận + mã bình luận cha (hiện chuỗi trả lời như thật).
ALTER TABLE binh_luan ADD COLUMN IF NOT EXISTS link TEXT;
ALTER TABLE binh_luan ADD COLUMN IF NOT EXISTS ma_cha TEXT;
-- Số bài mỗi lần của nguồn: bỏ trần trên (chủ dự án 15/10: "không có giới hạn").
ALTER TABLE nguon DROP CONSTRAINT IF EXISTS nguon_so_bai_moi_lan_check;
ALTER TABLE nguon ADD CONSTRAINT nguon_so_bai_moi_lan_check CHECK (so_bai_moi_lan >= 1);

-- 1 dòng = 1 bài × 1 dự án × 1 ngày (giờ VN): số đọc được lần cuối trong ngày đó.
CREATE TABLE IF NOT EXISTS chi_so_ngay (
  du_an           TEXT NOT NULL,
  khoa            TEXT NOT NULL,
  ngay            DATE NOT NULL,
  xem             BIGINT,
  thich           BIGINT,
  binh_luan       BIGINT,
  chia_se         BIGINT,
  PRIMARY KEY (du_an, khoa, ngay),
  FOREIGN KEY (du_an, khoa) REFERENCES bai (du_an, khoa) ON UPDATE CASCADE ON DELETE CASCADE
);

-- Ai được vào dashboard. `quan_ly` sửa được dự án/nguồn/ngân sách/người xem; `xem` chỉ xem.
CREATE TABLE IF NOT EXISTS nguoi_xem (
  email           TEXT PRIMARY KEY CHECK (email = lower(email) AND email LIKE '%@%'),
  vai_tro         TEXT NOT NULL CHECK (vai_tro IN ('xem', 'quan_ly')),
  them_boi        TEXT,
  them_luc        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Nhật ký mọi thay đổi làm trên dashboard (ai, lúc nào, sửa gì). Không đẩy lên BigQuery.
CREATE TABLE IF NOT EXISTS nhat_ky (
  id              BIGSERIAL PRIMARY KEY,
  luc             TIMESTAMPTZ NOT NULL DEFAULT now(),
  ai              TEXT NOT NULL,
  hanh_dong       TEXT NOT NULL,
  doi_tuong       TEXT NOT NULL,
  chi_tiet        JSONB
);

-- Mốc đồng bộ BigQuery của dashboard, mỗi bảng một dòng.
CREATE TABLE IF NOT EXISTS dong_bo_bq (
  bang            TEXT PRIMARY KEY,
  moc             TIMESTAMPTZ,
  lan_cuoi        TIMESTAMPTZ,
  so_dong         BIGINT,
  loi             TEXT
);

-- ───────────── Mô tả bảng + cột theo quy chuẩn BI (task t280613, skill lsr-bq-description-standard) ─────────────
-- Chủ dự án 14/10/2026: DB mới cũng theo rule mô tả của BI (11 nhãn bảng, mô tả mọi cột). Ghi
-- ngay trong file build (COMMENT ON chạy lại không mất), có bài canh tests/test_theo_doi.py.

COMMENT ON TABLE du_an IS $$[Lớp] Raw
[Mục đích] Danh mục dự án/brand đang được lắng nghe và cấu hình lọc (từ khoá, từ loại trừ, trần chi phí theo dõi mỗi tháng).
[Grain] 1 dòng = 1 dự án
[Khoá] PK: ma | Join: ma → nguon.du_an, bai.du_an, chi_so_ngay.du_an, luot_quet.du_an, de_xuat.du_an
[Nguồn] Người quản lý nhập trên dashboard social.hapas.vn (role lang_nghe_web); Mark chỉ đọc
[Phạm vi] Mọi dự án lắng nghe | Kênh: Không có | Dữ liệu từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Mã dự án chữ thường; thị trường 2 chữ in hoa; trần tháng ≥ 0 USD (ràng buộc CHECK)
[Refresh] Ghi tức thời khi người quản lý sửa trên dashboard (mỗi lần sửa ghi nhat_ky)
[Dùng khi] Biết dự án nào đang bật, từ khoá lọc, trần chi phí tháng
[Không dùng khi] Chi phí đã tiêu → dùng luot_quet; bài và tương tác → dùng bai; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.du_an
[Lưu ý] Cấu hình hiện hành, không giữ lịch sử (lịch sử sửa ở nhat_ky). Tắt dự án thì /theodoi từ chối.$$;
COMMENT ON COLUMN du_an.ma IS 'Mã dự án, chữ gõ sau /theodoi (vd hapas). PK. Chữ thường, số, -, _; 2–40 ký tự. Join: → nguon.du_an, bai.du_an, luot_quet.du_an.';
COMMENT ON COLUMN du_an.ten IS 'Tên hiển thị của dự án (vd HAPAS). Không NULL.';
COMMENT ON COLUMN du_an.tu_khoa IS 'Từ khoá dự án; bài từ nguồn không phải kênh nhà phải nhắc ít nhất một từ (so khớp bỏ dấu, không phân biệt hoa thường). Mảng rỗng: Mark dùng tên dự án.';
COMMENT ON COLUMN du_an.tu_loai_tru IS 'Từ loại trừ: bài chứa một từ này bị bỏ cứng trước bước AI. Mảng rỗng khi không đặt.';
COMMENT ON COLUMN du_an.boi_canh IS 'Mô tả brand cho bước AI phân xử giữ/loại và gán sắc thái, chủ đề. Chuỗi rỗng khi chưa viết.';
COMMENT ON COLUMN du_an.thi_truong IS 'Mã nước 2 chữ (ISO 3166-1) của thị trường chính, mặc định VN.';
COMMENT ON COLUMN du_an.tran_usd_thang IS 'Trần chi phí theo dõi mỗi tháng (giờ VN), USD tiền Apify, không VAT, ≥ 0 (không trần trên). Chỉ lượt kieu = theo_doi tính vào trần; trần mỗi lượt trên console platform vẫn áp dụng riêng.';
COMMENT ON COLUMN du_an.dang_bat IS 'TRUE: dự án bật, /theodoi được quét. FALSE: tắt, /theodoi từ chối.';
COMMENT ON COLUMN du_an.tao_luc IS 'Thời điểm tạo dự án (TIMESTAMPTZ, hiển thị theo múi giờ phiên; lưu UTC).';
COMMENT ON COLUMN du_an.sua_luc IS 'Thời điểm sửa dự án gần nhất (TIMESTAMPTZ, lưu UTC).';
COMMENT ON COLUMN du_an.bl_bat IS 'Công tắc TỔNG cào bình luận. TRUE: mỗi lượt /theodoi cào bình luận theo cấu hình từng nền tảng (cau_hinh.binh_luan; tính vào trần tháng). FALSE: không nền tảng nào cào, dù cau_hinh bật. Lưu cấu hình trên dashboard đặt = có ít nhất một nền tảng bật.';
COMMENT ON COLUMN du_an.bl_so_bai IS 'Số bài mặc định được cào bình luận mỗi lượt cho TỪNG nền tảng (khi cau_hinh không ghi đè), bài, ≥ 0 (không trần trên). 0 = không cào. Ưu tiên bài chưa cào, rồi bài có số bình luận tăng ≥ 20%.';
COMMENT ON COLUMN du_an.bl_moi_bai IS 'Số bình luận tối đa cào mỗi bài mỗi lượt, bình luận. 0 (mặc định) = cào HẾT bình luận + trả lời của bài (Facebook lần sau chỉ lấy bình luận mới; bài quá to cho trần mỗi lượt thì cào tiếp ở lượt sau); ≥ 5 = giới hạn. Actor tính tiền theo bình luận (TikTok 0,00125, Facebook 0,0025, Instagram 0,0026 USD; YouTube miễn phí).';
COMMENT ON COLUMN du_an.tk_bat IS 'Công tắc TỔNG tìm theo từ khoá. TRUE: mỗi lượt /theodoi còn TÌM theo từ khoá dự án trên các nền tảng bật trong cau_hinh.tu_khoa để bắt bài của mọi tài khoản (tính vào trần tháng). FALSE: chỉ quét nguồn đã theo dõi, dù cau_hinh bật.';
COMMENT ON COLUMN du_an.tk_so_bai IS 'Số bài mặc định lấy mỗi nền tảng mỗi lượt khi tìm theo từ khoá (khi cau_hinh không ghi đè), bài, ≥ 0 (không trần trên; Facebook gói Free thực tế tối đa 20 bài, 1 lượt/24h). 0 = không tìm.';
COMMENT ON COLUMN du_an.cau_hinh IS 'Cấu hình thu thập theo từng nền tảng (JSON), sửa ở trang Ngân sách: {"tu_khoa": {"<nền tảng>": {"bat", "so_bai" ≥ 0, "so_tu" ≥ 1}}, "binh_luan": {"<nền tảng>": {"bat", "so_bai" ≥ 0, "moi_bai" 0 = hết hoặc ≥ 5}}} — không trần trên nghiệp vụ (chỉ chặn số rác > 1.000.000). Khoá thiếu/giá trị rác thì dùng cột chung tk_* / bl_*; chỉ bat = true là bật; cột tk_bat / bl_bat là công tắc tổng. {} = theo cột chung.';
COMMENT ON COLUMN du_an.sua_boi IS 'Email người sửa gần nhất trên dashboard. NULL khi tạo bằng lệnh cài đặt. Email nội bộ — không đẩy lên BigQuery.';

COMMENT ON TABLE nguon IS $$[Lớp] Raw
[Mục đích] Danh sách nguồn mạng xã hội đang theo dõi của từng dự án, kèm chu kỳ quét và tình trạng quét gần nhất.
[Grain] 1 dòng = 1 nguồn (1 tài khoản/kênh/trang trên 1 nền tảng) của 1 dự án
[Khoá] PK: id | UNIQUE: du_an + nen_tang + dinh_danh | Join: du_an → du_an.ma; id → bai.nguon_id
[Nguồn] Người quản lý thêm/sửa trên dashboard (hoặc duyệt từ de_xuat); Mark chỉ ghi quet_cuoi, loi_cuoi, loi_luc
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Định danh chuẩn hoá (chữ thường, bỏ @ và tham số URL; id kênh YouTube UC… giữ nguyên)
[Refresh] Ghi tức thời khi người quản lý sửa; Mark cập nhật cột quét sau mỗi lượt /theodoi
[Dùng khi] Nguồn nào đang theo dõi, tới hạn quét, lỗi gần nhất
[Không dùng khi] Bài của nguồn → dùng bai; nguồn chờ duyệt → dùng de_xuat; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.nguon
[Lưu ý] Xoá nguồn thì bài cũ giữ lại với nguon_id NULL; nên tạm dừng thay vì xoá.$$;
COMMENT ON COLUMN nguon.id IS 'Mã nguồn tự tăng. PK. Join: → bai.nguon_id.';
COMMENT ON COLUMN nguon.du_an IS 'Dự án của nguồn. FK → du_an.ma.';
COMMENT ON COLUMN nguon.nen_tang IS 'Nền tảng. Giá trị: tiktok, instagram, youtube, facebook.';
COMMENT ON COLUMN nguon.dinh_danh IS 'Định danh nguồn đã chuẩn hoá: username TikTok/Instagram, id kênh YouTube (UC…) hoặc @handle, URL trang Facebook. Duy nhất trong (du_an, nen_tang).';
COMMENT ON COLUMN nguon.ten IS 'Tên hiển thị của nguồn. Chuỗi rỗng khi chưa nhập.';
COMMENT ON COLUMN nguon.link IS 'Link hồ sơ/kênh/trang. Chuỗi rỗng khi chưa nhập.';
COMMENT ON COLUMN nguon.loai IS 'Loại nguồn. Giá trị: kol, page, group, bao, kenh_nha (kênh của chính brand — giữ mọi bài), khac.';
COMMENT ON COLUMN nguon.nhan IS 'Nhãn tự do để lọc (vd đối thủ, top Kompa). Mảng rỗng khi không gắn.';
COMMENT ON COLUMN nguon.trang_thai IS 'Giá trị: dang_theo_doi (được quét khi tới hạn), tam_dung (bỏ qua).';
COMMENT ON COLUMN nguon.chu_ky_ngay IS 'Chu kỳ quét, ngày (1–30). Tới hạn khi lần quét cuối cách ≥ chu kỳ trừ 3 giờ.';
COMMENT ON COLUMN nguon.so_bai_moi_lan IS 'Số bài mới nhất lấy mỗi lần quét, bài (≥ 1, không trần trên). Instagram: actor hồ sơ chỉ trả 12 bài mới nhất.';
COMMENT ON COLUMN nguon.them_qua IS 'Giá trị: dashboard (người quản lý thêm), de_xuat (duyệt từ đề xuất của Mark), nhap_file.';
COMMENT ON COLUMN nguon.them_boi IS 'Email người thêm nguồn. NULL khi thêm bằng lệnh cài đặt. Email nội bộ — không đẩy lên BigQuery.';
COMMENT ON COLUMN nguon.them_luc IS 'Thời điểm thêm nguồn (TIMESTAMPTZ, lưu UTC).';
COMMENT ON COLUMN nguon.quet_cuoi IS 'Thời điểm quét thành công gần nhất (UTC). NULL khi chưa quét thành công.';
COMMENT ON COLUMN nguon.loi_cuoi IS 'Lỗi lần quét hỏng gần nhất. NULL khi lần gần nhất thành công hoặc chưa quét.';
COMMENT ON COLUMN nguon.loi_luc IS 'Thời điểm ghi loi_cuoi (UTC). NULL khi loi_cuoi NULL.';

COMMENT ON TABLE de_xuat IS $$[Lớp] Raw
[Mục đích] Hàng chờ nguồn Mark đề xuất theo dõi (tài khoản nổi trong lượt tìm theo từ khoá mà chưa có trong danh sách), chờ người quản lý duyệt.
[Grain] 1 dòng = 1 tài khoản đề xuất của 1 dự án
[Khoá] PK: id | UNIQUE: du_an + nen_tang + dinh_danh | Join: du_an → du_an.ma
[Nguồn] Mark ghi sau mỗi lượt social_listen khớp từ khoá dự án; người quản lý duyệt/từ chối trên dashboard
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Chỉ tài khoản ≥ 2 bài hoặc ≥ 50 thảo luận trong lượt; tối đa 10 mỗi lượt; bỏ nguồn đã có
[Refresh] Mark upsert sau mỗi lượt tìm theo từ khoá (số liệu ghi đè lần mới nhất)
[Dùng khi] Danh sách nguồn chờ duyệt và lý do đề xuất
[Không dùng khi] Nguồn đang theo dõi → dùng nguon
[Lưu ý] Mark không tự thêm nguồn; duyệt thì dashboard thêm dòng nguon với them_qua = de_xuat. Không đẩy lên BigQuery.$$;
COMMENT ON COLUMN de_xuat.id IS 'Mã đề xuất tự tăng. PK.';
COMMENT ON COLUMN de_xuat.du_an IS 'Dự án nhận đề xuất. FK → du_an.ma.';
COMMENT ON COLUMN de_xuat.nen_tang IS 'Nền tảng của tài khoản. Giá trị: tiktok, instagram, youtube.';
COMMENT ON COLUMN de_xuat.dinh_danh IS 'Định danh tài khoản (username hoặc id kênh YouTube UC…), cùng dạng nguon.dinh_danh.';
COMMENT ON COLUMN de_xuat.ten IS 'Tên hiển thị tài khoản lúc đề xuất.';
COMMENT ON COLUMN de_xuat.link IS 'Link hồ sơ/kênh.';
COMMENT ON COLUMN de_xuat.ly_do IS 'Lý do đề xuất: số bài, số thảo luận, từ khoá và ngày tìm.';
COMMENT ON COLUMN de_xuat.so_bai IS 'Số bài của tài khoản trong lượt tìm gần nhất, bài.';
COMMENT ON COLUMN de_xuat.thao_luan IS 'Thảo luận trong lượt tìm gần nhất = số bài + tổng bình luận nền tảng báo, thảo luận.';
COMMENT ON COLUMN de_xuat.trang_thai IS 'Giá trị: cho (chờ duyệt), da_duyet (đã thêm vào nguon), tu_choi.';
COMMENT ON COLUMN de_xuat.de_xuat_luc IS 'Thời điểm đề xuất lần đầu (UTC).';
COMMENT ON COLUMN de_xuat.xu_ly_boi IS 'Email người duyệt/từ chối. NULL khi chưa xử lý.';
COMMENT ON COLUMN de_xuat.xu_ly_luc IS 'Thời điểm duyệt/từ chối (UTC). NULL khi chưa xử lý.';

COMMENT ON TABLE luot_quet IS $$[Lớp] Raw
[Mục đích] Lịch sử các lượt quét: bao nhiêu nguồn, bao nhiêu bài, tốn bao nhiêu tiền thật, lỗi gì.
[Grain] 1 dòng = 1 lượt quét
[Khoá] PK: id | Join: du_an → du_an.ma; id → bai.luot_dau, bai.luot_cuoi
[Nguồn] Mark mở lượt khi bắt đầu, đóng khi xong (cả khi lỗi); chi phí = tổng usageTotalUsd đúng các run Apify của lượt
[Phạm vi] Mọi dự án | Kênh: Không có | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Không xử lý
[Refresh] Ghi tức thời khi Mark mở/đóng lượt
[Dùng khi] Chi phí theo dõi theo tháng (SUM chi_phi_usd WHERE kieu = 'theo_doi', tháng giờ VN); tỉ lệ nguồn lỗi
[Không dùng khi] Bài và tương tác → dùng bai; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.luot_quet
[Lưu ý] Lượt kẹt dang_chay quá 3 giờ được đóng thành loi ở lượt sau.$$;
COMMENT ON COLUMN luot_quet.id IS 'Mã lượt tự tăng. PK.';
COMMENT ON COLUMN luot_quet.du_an IS 'Dự án của lượt. FK → du_an.ma.';
COMMENT ON COLUMN luot_quet.kieu IS 'Giá trị: theo_doi (lượt /theodoi, tính vào trần tháng), tu_khoa (lượt tìm theo từ khoá ghi vào kho).';
COMMENT ON COLUMN luot_quet.ma_viec IS 'Mã việc nền của Mark (đối chiếu /viec). NULL với lượt tu_khoa.';
COMMENT ON COLUMN luot_quet.job_id IS 'Mã job platform đã giao lượt. NULL khi không có.';
COMMENT ON COLUMN luot_quet.bat_dau IS 'Thời điểm bắt đầu lượt (UTC).';
COMMENT ON COLUMN luot_quet.ket_thuc IS 'Thời điểm kết thúc lượt (UTC). NULL khi đang chạy.';
COMMENT ON COLUMN luot_quet.so_nguon IS 'Số nguồn lượt xét, nguồn.';
COMMENT ON COLUMN luot_quet.so_nguon_loi IS 'Số nguồn không lấy được bài, nguồn.';
COMMENT ON COLUMN luot_quet.bai_moi IS 'Số bài lần đầu vào kho trong lượt, bài.';
COMMENT ON COLUMN luot_quet.bai_cap_nhat IS 'Số bài đã có được cập nhật trong lượt, bài.';
COMMENT ON COLUMN luot_quet.chi_phi_usd IS 'Chi phí Apify THẬT của lượt, USD, không VAT. 0 với lượt chỉ dùng YouTube Data API và lượt tu_khoa (chi phí đó ở sổ chi phí quét). Không âm.';
COMMENT ON COLUMN luot_quet.trang_thai IS 'Giá trị: dang_chay, xong, mot_phan (một số nguồn lỗi), loi, da_huy.';
COMMENT ON COLUMN luot_quet.loi IS 'Tóm tắt lỗi, tối đa 500 ký tự. NULL khi không lỗi.';
COMMENT ON COLUMN luot_quet.ghi_chu IS 'Ghi chú vận hành (vd hết ngân sách tháng, bot khởi động lại giữa lượt). NULL khi không có.';

COMMENT ON TABLE bai IS $$[Lớp] Raw
[Mục đích] Bài mạng xã hội liên quan tới dự án mà Mark đã giữ, kèm nhãn AI và tương tác mới nhất.
[Grain] 1 dòng = 1 bài × 1 dự án
[Khoá] PK: du_an + khoa | Join: du_an → du_an.ma; nguon_id → nguon.id; (du_an, khoa) → chi_so_ngay, binh_luan; luot_dau, luot_cuoi → luot_quet.id
[Nguồn] Mark ghi sau mỗi lượt /theodoi (Apify theo tài khoản, YouTube Data API) và lượt tìm theo từ khoá (social_listen)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook (Threads từ tìm theo từ khoá) | Bài đăng trong 35 ngày trước lượt theo dõi, từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Chỉ bài liên quan (nhắc từ khoá trừ kênh nhà, không chứa từ loại trừ, không bị AI loại); khử trùng theo khoa; nội dung cắt 1.000 ký tự
[Refresh] Upsert tức thời sau mỗi lượt quét; video YouTube được đọc lại số mỗi ngày trong 14 ngày đầu
[Dùng khi] Đếm bài, thảo luận (1 + binh_luan), nguồn nổi bật, sắc thái, chủ đề
[Không dùng khi] Tăng trưởng theo ngày → dùng chi_so_ngay; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.bai
[Lưu ý] Số là lần đọc gần nhất, không phải cuối kỳ. Mẫu theo nguồn đã chọn + lượt tìm, không phải toàn bộ thảo luận trên mạng.$$;
COMMENT ON COLUMN bai.du_an IS 'Dự án. Một phần PK. FK → du_an.ma.';
COMMENT ON COLUMN bai.khoa IS 'Khoá bài "<nền tảng>:<id bài>" (không bóc được id thì "h" + 16 ký tự băm SHA-1 của link). Một phần PK.';
COMMENT ON COLUMN bai.nen_tang IS 'Nền tảng: tiktok, instagram, youtube, facebook; tìm theo từ khoá có thể thêm threads.';
COMMENT ON COLUMN bai.nguon_id IS 'Nguồn theo dõi cho ra bài. FK → nguon.id. NULL khi bài từ tìm theo từ khoá (tài khoản chưa theo dõi) hoặc nguồn đã bị xoá.';
COMMENT ON COLUMN bai.kieu_quet IS 'Giá trị: theo_doi, tu_khoa. Bài từng là theo_doi thì giữ theo_doi.';
COMMENT ON COLUMN bai.link IS 'Link bài gốc. Không NULL.';
COMMENT ON COLUMN bai.tac_gia IS 'Tên hiển thị kênh/tài khoản đăng. Chuỗi rỗng khi không có.';
COMMENT ON COLUMN bai.tai_khoan IS 'Username tài khoản đăng (TikTok, Instagram). Chuỗi rỗng với YouTube.';
COMMENT ON COLUMN bai.followers IS 'Người theo dõi tài khoản đăng lúc đọc gần nhất, người. NULL khi nền tảng không trả.';
COMMENT ON COLUMN bai.dang_luc IS 'Thời điểm đăng bài (UTC; giờ VN = dang_luc AT TIME ZONE ''Asia/Ho_Chi_Minh'').';
COMMENT ON COLUMN bai.noi_dung IS 'Nội dung/caption (YouTube: tiêu đề — mô tả), tối đa 1.000 ký tự.';
COMMENT ON COLUMN bai.hashtag IS 'Hashtag không có #, phân cách ", ", tối đa 500 ký tự.';
COMMENT ON COLUMN bai.khop_tu_khoa IS 'TRUE: nhắc ít nhất một từ khoá dự án. FALSE: không nhắc (chỉ giữ khi nguồn là kenh_nha).';
COMMENT ON COLUMN bai.sac_thai IS 'Sắc thái do AI gán. Giá trị: Tích cực, Tiêu cực, Trung lập. NULL khi AI chưa gán.';
COMMENT ON COLUMN bai.chu_de IS 'Chủ đề do AI gán theo 13 chủ đề của Mark. NULL khi AI chưa gán.';
COMMENT ON COLUMN bai.ly_do_giu IS 'Vì sao giữ: mã AI (brand, ad, product, ugc, other_market) hoặc kenh_nha / khop_tu_khoa.';
COMMENT ON COLUMN bai.xem IS 'Lượt xem lần đọc gần nhất, lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN bai.thich IS 'Lượt thích lần đọc gần nhất, lượt. NULL khi không đọc được.';
COMMENT ON COLUMN bai.binh_luan IS 'Số bình luận nền tảng báo lần đọc gần nhất, bình luận (không phải số đã cào). NULL khi không đọc được.';
COMMENT ON COLUMN bai.chia_se IS 'Lượt chia sẻ lần đọc gần nhất, lượt. NULL với YouTube, Instagram.';
COMMENT ON COLUMN bai.thay_lan_dau IS 'Thời điểm ghi bài lần đầu (UTC).';
COMMENT ON COLUMN bai.cap_nhat_cuoi IS 'Thời điểm cập nhật gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON COLUMN bai.luot_dau IS 'Lượt ghi bài lần đầu. FK → luot_quet.id.';
COMMENT ON COLUMN bai.luot_cuoi IS 'Lượt cập nhật bài gần nhất. FK → luot_quet.id.';
COMMENT ON COLUMN bai.bl_lay_luc IS 'Lần cào bình luận gần nhất (UTC). NULL khi chưa cào bình luận của bài.';
COMMENT ON COLUMN bai.bl_da_lay IS 'Số bình luận lấy được ở lần cào gần nhất, bình luận. NULL khi chưa cào.';
COMMENT ON COLUMN bai.bl_lan_thieu IS 'Số lần cào bình luận liên tiếp vẫn chưa đủ 80% số nền tảng báo (Instagram chưa đăng nhập, bài bị ẩn, chạm trần). Từ 2 lần thì thôi cào bù, chỉ cào lại khi bình luận tăng. 0 khi đã đủ.';
COMMENT ON COLUMN bai.ma_noi_dung IS 'Băm 16 ký tự của nội dung đã chuẩn hoá (bỏ dấu, link, emoji, số → 0) khi nội dung ≥ 30 ký tự — các bài cùng mã là cùng nội dung (đăng lại trên nhiều trang, seeding). NULL khi nội dung quá ngắn.';
COMMENT ON COLUMN bai.bl_lay_khi_co IS 'Số bình luận nền tảng báo lúc cào gần nhất, bình luận — để biết bài có thêm bình luận đáng cào lại không. NULL khi chưa cào.';

COMMENT ON TABLE binh_luan IS $$[Lớp] Raw
[Mục đích] Bình luận (và trả lời) dưới các bài đã giữ của dự án, kèm sắc thái và chủ đề AI gán — tiếng khách hàng.
[Grain] 1 dòng = 1 bình luận × 1 bài × 1 dự án
[Khoá] PK: du_an + khoa_bai + ma | Join: (du_an, khoa_bai) → bai.(du_an, khoa); luot_id → luot_quet.id
[Nguồn] Mark cào sau mỗi lượt /theodoi: Apify (TikTok, Facebook, Instagram comments scraper), YouTube Data API
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook | Bài đăng trong 35 ngày; tối đa bl_so_bai bài mỗi lượt, mỗi bài cào hết (bl_moi_bai = 0) hoặc tới bl_moi_bai bình luận; từ 15/10/2026
[Đã xử lý] Khử trùng theo ma; nội dung cắt 1.000 ký tự; mỗi dòng gắn nhãn lọc loai (hop_le/it_noi_dung/spam/trung/seeding/thuong_hieu) — chỉ hop_le được gán sắc thái/chủ đề
[Refresh] Upsert tức thời sau mỗi lượt quét (bài được cào lại khi số bình luận tăng ≥ 20%)
[Dùng khi] Đọc từng bình luận; thảo luận sạch (loai = 'hop_le'); sắc thái/chủ đề bình luận; tỷ lệ spam/seeding
[Không dùng khi] Tổng bình luận nền tảng báo → dùng bai.binh_luan; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.binh_luan
[Lưu ý] Đếm thảo luận sạch phải lọc loai = 'hop_le'; Instagram chưa đăng nhập chỉ trả một phần, Facebook/TikTok bài rất lớn có thể thiếu (so bai.bl_da_lay với bai.binh_luan để biết độ phủ).$$;
COMMENT ON COLUMN binh_luan.du_an IS 'Dự án. Một phần PK. FK (cùng khoa_bai) → bai.';
COMMENT ON COLUMN binh_luan.khoa_bai IS 'Khoá bài chứa bình luận. Một phần PK. FK (cùng du_an) → bai.khoa.';
COMMENT ON COLUMN binh_luan.ma IS 'Mã bình luận trên nền tảng; không có thì "h" + 16 ký tự băm SHA-1 (tác giả, nội dung, thời điểm). Một phần PK.';
COMMENT ON COLUMN binh_luan.nen_tang IS 'Nền tảng. Giá trị: tiktok, instagram, youtube, facebook.';
COMMENT ON COLUMN binh_luan.tac_gia IS 'Tên/username người bình luận (công khai trên nền tảng). Chuỗi rỗng khi không có.';
COMMENT ON COLUMN binh_luan.noi_dung IS 'Nội dung bình luận, tối đa 1.000 ký tự.';
COMMENT ON COLUMN binh_luan.thich IS 'Lượt thích bình luận lúc cào, lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN binh_luan.tra_loi IS 'Số trả lời của bình luận lúc cào, bình luận. NULL khi nền tảng không trả.';
COMMENT ON COLUMN binh_luan.la_tra_loi IS 'TRUE: dòng là trả lời của một bình luận khác. FALSE: bình luận gốc.';
COMMENT ON COLUMN binh_luan.cua_thuong_hieu IS 'TRUE: do tài khoản của chính thương hiệu viết (không gán nhãn, không tính sắc thái). FALSE: khách.';
COMMENT ON COLUMN binh_luan.dang_luc IS 'Thời điểm đăng bình luận (UTC). NULL khi nền tảng chỉ trả thời gian tương đối.';
COMMENT ON COLUMN binh_luan.sac_thai IS 'Sắc thái AI/luật gán. Giá trị: Tích cực, Tiêu cực, Trung lập. NULL khi chưa gán hoặc bình luận của thương hiệu.';
COMMENT ON COLUMN binh_luan.chu_de IS 'Chủ đề bình luận theo 7 nhóm của Mark (Sản phẩm/chất lượng, Giá/mua ở đâu/ý định mua, KOL/nội dung, Giao hàng/dịch vụ, Đối thủ, Tag bạn bè, Khác). NULL khi chưa gán.';
COMMENT ON COLUMN binh_luan.luot_id IS 'Lượt quét cào bình luận gần nhất. FK → luot_quet.id.';
COMMENT ON COLUMN binh_luan.thay_lan_dau IS 'Thời điểm ghi bình luận lần đầu (UTC).';
COMMENT ON COLUMN binh_luan.cap_nhat_cuoi IS 'Thời điểm cập nhật gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON COLUMN binh_luan.loai IS 'Nhãn lọc (loc_rac.py). Giá trị: hop_le (tính vào thảo luận sạch, có sắc thái), it_noi_dung (chỉ dấu chấm/emoji/tag/"chấm" — tương tác nhưng không có ý), spam (quảng cáo/lừa đảo/kéo khách), trung (cùng người cùng nội dung cùng bài, giữ bản đầu), seeding (cùng nội dung ≥ 40 ký tự từ ≥ 3 tài khoản trên ≥ 2 bài trong 7 ngày), thuong_hieu (chính thương hiệu viết).';
COMMENT ON COLUMN binh_luan.link IS 'Link mở thẳng tới bình luận khi nền tảng có (Facebook/Instagram commentUrl, YouTube &lc=); NULL thì mở bài (bai.link).';
COMMENT ON COLUMN binh_luan.ma_cha IS 'Mã bình luận cha khi dòng là trả lời (cùng khoa_bai). NULL với bình luận gốc hoặc nền tảng không trả.';
COMMENT ON COLUMN binh_luan.ly_do_loc IS 'Lý do lọc khi loai không phải hop_le (vd lien_ket_quang_cao, keo_khach, vay_tien, co_bac, viec_lam_mmo, ban_hang_khac, so_dien_thoai_quang_cao, cung_nguoi_cung_noi_dung, cung_noi_dung_nhieu_tai_khoan). NULL khi hợp lệ.';
COMMENT ON COLUMN binh_luan.ma_noi_dung IS 'Băm 16 ký tự nội dung đã chuẩn hoá khi nội dung ≥ 40 ký tự — để phát hiện seeding (cùng mã, ≥ 3 tài khoản, ≥ 2 bài, 7 ngày). NULL khi quá ngắn.';

COMMENT ON TABLE chi_so_ngay IS $$[Lớp] Raw
[Mục đích] Tương tác lũy kế của từng bài theo ngày đọc, để vẽ tăng trưởng và tính phần tăng trong kỳ.
[Grain] 1 dòng = 1 bài × 1 dự án × 1 ngày đọc (giờ VN)
[Khoá] PK: du_an + khoa + ngay | Join: (du_an, khoa) → bai.(du_an, khoa)
[Nguồn] Mark ghi mỗi lần đọc số của bài (ghi đè trong cùng ngày)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Không xử lý
[Refresh] Upsert tức thời mỗi lần Mark đọc số
[Dùng khi] Tăng trưởng theo ngày; phần tăng trong kỳ = ngày cuối − ngày đầu
[Không dùng khi] Số mới nhất, nội dung, nhãn → dùng bai; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.chi_so_ngay
[Lưu ý] Số LŨY KẾ, không phải phát sinh trong ngày; ngày không đọc thì thiếu dòng.$$;
COMMENT ON COLUMN chi_so_ngay.du_an IS 'Dự án. Một phần PK. FK (cùng khoa) → bai.';
COMMENT ON COLUMN chi_so_ngay.khoa IS 'Khoá bài. Một phần PK. FK (cùng du_an) → bai.';
COMMENT ON COLUMN chi_so_ngay.ngay IS 'Ngày đọc số theo giờ VN (GMT+7). Một phần PK.';
COMMENT ON COLUMN chi_so_ngay.xem IS 'Lượt xem lũy kế lần đọc cuối trong ngày, lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN chi_so_ngay.thich IS 'Lượt thích lũy kế, lượt. NULL khi không đọc được.';
COMMENT ON COLUMN chi_so_ngay.binh_luan IS 'Bình luận nền tảng báo, lũy kế, bình luận. NULL khi không đọc được.';
COMMENT ON COLUMN chi_so_ngay.chia_se IS 'Lượt chia sẻ lũy kế, lượt. NULL với YouTube, Instagram.';

COMMENT ON TABLE nguoi_xem IS $$[Lớp] Raw
[Mục đích] Ai được vào dashboard social.hapas.vn và với vai trò gì.
[Grain] 1 dòng = 1 email
[Khoá] PK: email | Join: Không có
[Nguồn] Người quản lý thêm/xoá trên dashboard; người quản lý đầu tiên thêm bằng lệnh quan_tri
[Phạm vi] Nhân viên HAPAS (tài khoản Lark của tổ chức) | Kênh: Không có | Từ khi cài dashboard
[Đã xử lý] Email chữ thường
[Refresh] Ghi tức thời khi người quản lý sửa
[Dùng khi] Kiểm quyền đăng nhập dashboard
[Không dùng khi] Lịch sử thêm/xoá → dùng nhat_ky
[Lưu ý] Email nội bộ — không đẩy lên BigQuery. Luôn phải còn ít nhất một quan_ly.$$;
COMMENT ON COLUMN nguoi_xem.email IS 'Email công ty (enterprise_email Lark), chữ thường. PK.';
COMMENT ON COLUMN nguoi_xem.vai_tro IS 'Giá trị: xem (chỉ xem), quan_ly (sửa dự án, nguồn, ngân sách, người xem).';
COMMENT ON COLUMN nguoi_xem.them_boi IS 'Email người thêm. NULL khi thêm bằng lệnh cài đặt.';
COMMENT ON COLUMN nguoi_xem.them_luc IS 'Thời điểm thêm (UTC).';

COMMENT ON TABLE nhat_ky IS $$[Lớp] Raw
[Mục đích] Nhật ký mọi thay đổi làm trên dashboard: ai, lúc nào, sửa gì.
[Grain] 1 dòng = 1 thao tác sửa
[Khoá] PK: id | Join: ai → nguoi_xem.email (khi còn)
[Nguồn] Dashboard ghi cùng giao dịch với mỗi thao tác sửa
[Phạm vi] Mọi thao tác trên dashboard | Kênh: Không có | Từ khi cài dashboard
[Đã xử lý] Không xử lý
[Refresh] Append tức thời
[Dùng khi] Kiểm toán thay đổi nguồn, ngân sách, người xem
[Không dùng khi] Trạng thái hiện hành → dùng du_an, nguon, nguoi_xem
[Lưu ý] Có email nội bộ — không đẩy lên BigQuery; chỉ người quản lý xem.$$;
COMMENT ON COLUMN nhat_ky.id IS 'Mã dòng tự tăng. PK.';
COMMENT ON COLUMN nhat_ky.luc IS 'Thời điểm thao tác (UTC).';
COMMENT ON COLUMN nhat_ky.ai IS 'Email người thao tác.';
COMMENT ON COLUMN nhat_ky.hanh_dong IS 'Tên thao tác (vd them_nguon, sua_ngan_sach, duyet_de_xuat, dang_nhap_lan_dau).';
COMMENT ON COLUMN nhat_ky.doi_tuong IS 'Đối tượng bị sửa (vd nguon:12, du_an:hapas).';
COMMENT ON COLUMN nhat_ky.chi_tiet IS 'Chi tiết JSON (giá trị trước/sau). NULL khi không có.';

COMMENT ON TABLE dong_bo_bq IS $$[Lớp] Raw
[Mục đích] Mốc đồng bộ kho lên BigQuery ganesha-381907.SOCIAL_LISTENING, mỗi bảng một dòng.
[Grain] 1 dòng = 1 bảng được đồng bộ
[Khoá] PK: bang | Join: Không có
[Nguồn] Dashboard (dashboard/dong_bo_bq.py) ghi sau mỗi lượt đồng bộ
[Phạm vi] 6 bảng: du_an, nguon, luot_quet, bai, chi_so_ngay, binh_luan | Kênh: Không có | Từ khi bật đồng bộ
[Đã xử lý] Không xử lý
[Refresh] Ghi sau mỗi lượt đồng bộ (sau mỗi lượt quét và 6 giờ một lần)
[Dùng khi] Kiểm độ trễ và lỗi đồng bộ BigQuery
[Không dùng khi] Dữ liệu nghiệp vụ → dùng các bảng còn lại
[Lưu ý] moc chỉ dời khi cả bảng đẩy xong; lỗi thì giữ mốc cũ.$$;
COMMENT ON COLUMN dong_bo_bq.bang IS 'Tên bảng được đồng bộ. PK.';
COMMENT ON COLUMN dong_bo_bq.moc IS 'Mốc đã đẩy xong (giá trị lớn nhất của cột mốc của bảng; với chi_so_ngay là ngày). NULL khi chưa đẩy lần nào hoặc bảng nạp lại toàn bộ.';
COMMENT ON COLUMN dong_bo_bq.lan_cuoi IS 'Thời điểm lượt đồng bộ gần nhất (UTC).';
COMMENT ON COLUMN dong_bo_bq.so_dong IS 'Số dòng đã đẩy ở lượt gần nhất, dòng.';
COMMENT ON COLUMN dong_bo_bq.loi IS 'Lỗi lượt gần nhất (đã bỏ URL, tối đa 200 ký tự). NULL khi thành công.';

RESET ROLE;

-- Quyền của bot: đọc cấu hình, ghi kết quả. Không sửa dự án, không thêm/xoá nguồn.
GRANT SELECT ON du_an, nguon TO mark;
GRANT UPDATE (quet_cuoi, loi_cuoi, loi_luc) ON nguon TO mark;
GRANT SELECT, INSERT, UPDATE ON bai, chi_so_ngay, luot_quet, binh_luan TO mark;
GRANT SELECT, INSERT ON de_xuat TO mark;
GRANT UPDATE (ten, link, ly_do, so_bai, thao_luan) ON de_xuat TO mark;
GRANT USAGE ON SEQUENCE luot_quet_id_seq, de_xuat_id_seq TO mark;

-- Quyền của dashboard: quản lý cấu hình + người xem, đọc mọi thứ, ghi nhật ký và mốc đồng bộ.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lang_nghe_web;
GRANT INSERT, UPDATE, DELETE ON du_an, nguon, nguoi_xem TO lang_nghe_web;
GRANT UPDATE (trang_thai, xu_ly_boi, xu_ly_luc) ON de_xuat TO lang_nghe_web;
GRANT INSERT ON nhat_ky TO lang_nghe_web;
GRANT INSERT, UPDATE ON dong_bo_bq TO lang_nghe_web;
GRANT USAGE ON SEQUENCE nguon_id_seq, nhat_ky_id_seq TO lang_nghe_web;
