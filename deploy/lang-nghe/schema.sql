-- Kho dữ liệu lắng nghe MXH (đợt 2, chủ dự án chốt 14/10/2026): DB `lang_nghe` trên Postgres 16
-- của VPS Mark. Chạy lại nhiều lần không hỏng (IF NOT EXISTS / DO $$ … $$).
--
--   sudo -u postgres env PGOPTIONS='-c lock_timeout=5s' psql -v ON_ERROR_STOP=1 \
--     -f deploy/lang-nghe/schema.sql
--
-- lock_timeout: ALTER TABLE (vd thêm luot_quet.lich_id) xin khoá ACCESS EXCLUSIVE; Mark/dashboard
-- đang giữ khoá thì lệnh dừng sau 5 giây và báo lỗi (chạy lại sau), không treo mọi truy vấn khác.
--
-- Vì sao DB riêng trên VPS mà không để trên platform: quyết định 0008 của platform (platform chỉ
-- giữ control + audit; dữ liệu xử lý nằm ở làn của agent) — chủ dự án chốt "mark vẫn phải theo
-- luật của platform như trước không đổi". Kỹ năng, công tắc, trần mỗi lượt, lịch của Mark VẪN ở
-- console platform; DB này chỉ giữ dự án, nguồn theo dõi, ngân sách tháng, bài đã quét. Từ
-- 15/10/2026 thêm lịch quét TỰ ĐỘNG (bảng lich_quet, chủ dự án chốt "Dashboard + Mark tự chạy");
-- lịch Giao việc trên console vẫn chạy song song.
--
-- Ba role, đăng nhập bằng Unix socket + peer (không mật khẩu, không mở cổng):
--   lang_nghe_chu  — sở hữu bảng (NOLOGIN), chỉ dùng để chạy file này.
--   mark           — user hệ điều hành của bot: ĐỌC dự án/nguồn/lịch, GHI bài/lượt quét/đề xuất
--                    và cột trạng thái chạy của lịch; đọc email + vai trò người xem (hỏi đáp
--                    số liệu dashboard trong chat chỉ cho người xem).
--   lang_nghe_web  — user hệ điều hành của dashboard: quản lý dự án/nguồn/lịch/người xem, đọc mọi thứ.

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
-- lock_timeout dự phòng khi quên PGOPTIONS (lệnh chạy ở đầu file): 5 giây, chỉ khi phiên
-- chưa đặt — PGOPTIONS đặt tay vẫn giữ nguyên.
SELECT set_config('lock_timeout', '5s', false) WHERE current_setting('lock_timeout') = '0';

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
  cau_hinh        JSONB NOT NULL DEFAULT '{}'::jsonb,
  hashtag         TEXT[] NOT NULL DEFAULT '{}'    -- hashtag riêng (IG + feed TikTok), 18/10/2026
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
-- 18/10/2026 (chủ dự án: "bỏ phần thị trường, thay bằng phần hashtag"): hashtag riêng của dự án,
-- sửa ở trang Nguồn. Mark dùng cho tìm hashtag Instagram + feed hashtag TikTok; mảng rỗng thì suy
-- từ từ khoá như trước. Quyền: role mark đọc cả bảng (GRANT SELECT ON du_an), lang_nghe_web ghi
-- cả bảng (GRANT INSERT, UPDATE ON du_an) — không có GRANT theo cột nào cần thêm.
ALTER TABLE du_an ADD COLUMN IF NOT EXISTS hashtag TEXT[] NOT NULL DEFAULT '{}';

-- 1 dòng = 1 nguồn theo dõi. `dinh_danh`: username TikTok/Instagram/Threads, kênh YouTube (UC… hoặc
-- @handle), URL trang Facebook — đã chuẩn hoá chữ thường (trừ id kênh YouTube UC…).
CREATE TABLE IF NOT EXISTS nguon (
  id              BIGSERIAL PRIMARY KEY,
  du_an           TEXT NOT NULL REFERENCES du_an(ma) ON UPDATE CASCADE,
  nen_tang        TEXT NOT NULL CHECK (nen_tang IN ('tiktok', 'instagram', 'youtube', 'facebook', 'threads')),
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
  kieu_trang      TEXT,
  muc_nhac        TEXT,
  la_pr           BOOLEAN,
  ma_so_fb        TEXT,
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
-- Báo & Web (16/10/2026, nguon_web.py): bài web là dòng `bai` với nen_tang = 'web' (cột không có
-- CHECK nên không phải sửa). Ba cột riêng của bài web, NULL với bài mạng xã hội — thêm cột NULL
-- được là thao tác chỉ đổi danh mục (không ghi lại bảng), chạy nhanh dưới lock_timeout.
ALTER TABLE bai ADD COLUMN IF NOT EXISTS kieu_trang TEXT;
ALTER TABLE bai ADD COLUMN IF NOT EXISTS muc_nhac TEXT;
ALTER TABLE bai ADD COLUMN IF NOT EXISTS la_pr BOOLEAN;
ALTER TABLE bai DROP CONSTRAINT IF EXISTS bai_kieu_trang_check;
ALTER TABLE bai ADD CONSTRAINT bai_kieu_trang_check CHECK (kieu_trang IS NULL OR kieu_trang IN
  ('bao', 'dien_dan', 'blog', 'mxh_khac', 'khac')) NOT VALID;
ALTER TABLE bai DROP CONSTRAINT IF EXISTS bai_muc_nhac_check;
ALTER TABLE bai ADD CONSTRAINT bai_muc_nhac_check CHECK (muc_nhac IS NULL OR muc_nhac IN
  ('tieu_de', 'chinh', 'thoang')) NOT VALID;
-- Khử trùng bài Facebook (17/10/2026, khu_trung_fb.py): đo thật DB production — mỗi lượt cào actor
-- trả pfbid KHÁC cho cùng một bài, khoá theo pfbid nên 161 bài FB của hapas có 24 nhóm trùng (60
-- dòng, thừa 36). Khoá bài giữ nguyên; id số của bài (ổn định) để Mark nhận ra bản trùng lúc ghi.
-- Không UNIQUE: bản trùng cũ chưa gộp (scripts/lang_nghe_gop_bai_fb.py) vẫn mang cùng id, và một
-- lỗi trùng khoá ở giữa lô là rollback CẢ lô bài đã trả tiền. Index một phần: chỉ dòng có id.
ALTER TABLE bai ADD COLUMN IF NOT EXISTS ma_so_fb TEXT;
ALTER TABLE bai DROP CONSTRAINT IF EXISTS bai_ma_so_fb_check;
ALTER TABLE bai ADD CONSTRAINT bai_ma_so_fb_check CHECK (ma_so_fb IS NULL OR ma_so_fb ~ '^[0-9]{5,25}$')
  NOT VALID;
CREATE INDEX IF NOT EXISTS bai_ma_so_fb ON bai (du_an, ma_so_fb) WHERE ma_so_fb IS NOT NULL;

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
  san_pham        TEXT,
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
-- 17/10/2026: món khách hỏi mua (chủ dự án: "hỏi mua những cái khác nhưng đang bị đánh vào hỏi
-- mua túi"). Mã khớp phan_loai.SAN_PHAM / dashboard.chi_so.SAN_PHAM. NULL = không phải bình luận
-- hỏi mua / chưa gán. Gán lại dữ liệu cũ: scripts/lang_nghe_gan_san_pham.py (chạy thử trước).
ALTER TABLE binh_luan ADD COLUMN IF NOT EXISTS san_pham TEXT;
ALTER TABLE binh_luan DROP CONSTRAINT IF EXISTS binh_luan_san_pham_check;
ALTER TABLE binh_luan ADD CONSTRAINT binh_luan_san_pham_check CHECK (san_pham IS NULL OR san_pham IN
  ('tui', 'vi', 'nuoc_hoa', 'trang_suc', 'set_qua', 'khac', 'ngoai_brand', 'chua_ro'));
-- Số bài mỗi lần của nguồn: bỏ trần trên (chủ dự án 15/10: "không có giới hạn").
ALTER TABLE nguon DROP CONSTRAINT IF EXISTS nguon_so_bai_moi_lan_check;
ALTER TABLE nguon ADD CONSTRAINT nguon_so_bai_moi_lan_check CHECK (so_bai_moi_lan >= 1);
-- Threads (16/10/2026, chủ dự án: "thêm listening threads"): nguồn Threads theo dõi được. DB đã tạo
-- trước đó giữ ràng buộc 4 nền tảng (tên tự sinh nguon_nen_tang_check) — đổi ở đây, chạy lại được.
ALTER TABLE nguon DROP CONSTRAINT IF EXISTS nguon_nen_tang_check;
ALTER TABLE nguon ADD CONSTRAINT nguon_nen_tang_check
  CHECK (nen_tang IN ('tiktok', 'instagram', 'youtube', 'facebook', 'threads'));

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
-- Danh bạ Lark (17/10/2026, chủ dự án: "thêm title trong công ty… biết email có active thật
-- không"): bản đệm đọc từ Lark contact API bằng app của dashboard (dashboard/danh_ba.py), làm
-- mới ≤ 12 giờ/lần khi mở trang Người xem và ngay khi thêm email. `dang_nhap_cuoi` ghi mỗi lượt
-- đăng nhập thành công. Không ghi nhật ký (bản đệm, không phải thao tác của người quản lý).
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS ten_lark TEXT;
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS chuc_danh TEXT;
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS phong_ban TEXT;
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS trang_thai_lark TEXT
  CHECK (trang_thai_lark IN ('hoat_dong', 'chua_kich_hoat', 'tam_khoa', 'nghi_viec', 'khong_co'));
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS danh_ba_loi TEXT
  CHECK (danh_ba_loi IN ('thieu_quyen', 'loi'));
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS danh_ba_luc TIMESTAMPTZ;
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS dang_nhap_cuoi TIMESTAMPTZ;
-- Mã tài khoản Lark (17/10/2026): ghi lúc đăng nhập OAuth. Lark batch_get_id KHÔNG khớp
-- enterprise_email (email công ty) -> quản lý dùng email @hapas.vn bị báo nhầm "không có trong
-- danh bạ"; có open_id thì đọc danh bạ tra thẳng theo mã, không qua email.
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS lark_open_id TEXT;
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS lark_union_id TEXT;
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS lark_user_id TEXT;

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

-- Lịch quét TỰ ĐỘNG (chủ dự án chốt 15/10/2026: "Dashboard + Mark tự chạy"): đặt trên dashboard,
-- Mark (quet_tu_dong.py) tự chạy /theodoi đúng mốc. Cách tính mốc: dashboard/lich_quet.py.
CREATE TABLE IF NOT EXISTS lich_quet (
  id              BIGSERIAL PRIMARY KEY,
  du_an           TEXT NOT NULL REFERENCES du_an(ma) ON UPDATE CASCADE,
  ten             TEXT NOT NULL DEFAULT '' CHECK (length(ten) <= 200),
  kieu            TEXT NOT NULL CHECK (kieu IN ('moi_n_gio', 'hang_ngay', 'hang_tuan', 'chien_dich')),
  cau_hinh        JSONB NOT NULL DEFAULT '{}'::jsonb,
  bat             BOOLEAN NOT NULL DEFAULT TRUE,
  quet_moi_nguon  BOOLEAN NOT NULL DEFAULT FALSE,
  lan_chay_ke     TIMESTAMPTZ,
  lan_chay_cuoi   TIMESTAMPTZ,
  ket_qua_cuoi    JSONB,
  so_lan_chay     INT NOT NULL DEFAULT 0 CHECK (so_lan_chay >= 0),
  tao_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
  tao_boi         TEXT,
  sua_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
  sua_boi         TEXT
);
CREATE INDEX IF NOT EXISTS lich_quet_den_han ON lich_quet (lan_chay_ke) WHERE bat;
CREATE INDEX IF NOT EXISTS lich_quet_du_an ON lich_quet (du_an);
-- Chiến dịch: khoảng 30 phút – 7 ngày một lượt, kể cả dòng ghi ngoài dashboard (psql) — lớp chặn
-- thứ hai sau `dashboard/lich_quet.py` (Mark cũng tự cho lịch sai giới hạn ngủ). CASE giữ thứ tự
-- đánh giá: moi_phut không phải số thì không ép kiểu.
ALTER TABLE lich_quet DROP CONSTRAINT IF EXISTS lich_quet_chien_dich_check;
ALTER TABLE lich_quet ADD CONSTRAINT lich_quet_chien_dich_check CHECK (
  kieu <> 'chien_dich' OR CASE WHEN jsonb_typeof(cau_hinh->'moi_phut') = 'number'
    THEN (cau_hinh->>'moi_phut')::numeric BETWEEN 30 AND 10080 ELSE false END);
-- Lượt nào do lịch nào giao (NULL: lượt gõ tay / lịch console). Xoá lịch thì lượt giữ, cột NULL.
ALTER TABLE luot_quet ADD COLUMN IF NOT EXISTS lich_id BIGINT
  REFERENCES lich_quet(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS luot_quet_lich ON luot_quet (lich_id) WHERE lich_id IS NOT NULL;

-- Kiểm ĐỘ PHỦ (17/10/2026, chủ dự án duyệt hai lần/tuần, 0,20 USD/lần): mỗi lần Mark lấy một mẫu bài
-- TikTok bằng đường KHÁC thu thập hằng ngày (hashtag brand/chiến dịch + bài mới nhất của nhà sáng
-- tạo nổi), đo bao nhiêu bài nhắc brand đã có trong `bai` — lỗ hổng thu thập tự hiện trên
-- dashboard — rồi tự sửa đường thu thập (đề xuất nguồn, hashtag + nhịp lượt nổi; cột hanh_dong). Vì sao bảng mà không phải sổ JSON trên đĩa của Mark: dashboard (user khác, tiến
-- trình khác) cần LỊCH SỬ để so ▲/▼ với lần trước và danh sách bài sót; mốc nhịp tuần + bộ nhớ
-- cid/uid vẫn ở sổ mốc của Mark (`.moc-tu-khoa.json`) nên bảng chưa tạo thì Mark không kiểm lại
-- mỗi lượt (chỉ báo "không ghi được bảng" trong ghi chú lượt).
CREATE TABLE IF NOT EXISTS kiem_do_phu (
  id              BIGSERIAL PRIMARY KEY,
  du_an           TEXT NOT NULL REFERENCES du_an(ma) ON UPDATE CASCADE,
  luot_id         BIGINT REFERENCES luot_quet(id) ON DELETE SET NULL,
  luc             TIMESTAMPTZ NOT NULL DEFAULT now(),
  nen_tang        TEXT NOT NULL DEFAULT 'tiktok',
  so_mau          INT NOT NULL DEFAULT 0 CHECK (so_mau >= 0),
  so_nhac         INT NOT NULL DEFAULT 0 CHECK (so_nhac >= 0),
  so_da_co        INT NOT NULL DEFAULT 0 CHECK (so_da_co >= 0),
  so_da_loai      INT NOT NULL DEFAULT 0 CHECK (so_da_loai >= 0),
  so_sot          INT NOT NULL DEFAULT 0 CHECK (so_sot >= 0),
  thao_luan_nhac  BIGINT NOT NULL DEFAULT 0,
  thao_luan_da_co BIGINT NOT NULL DEFAULT 0,
  do_phu          NUMERIC(5,2) CHECK (do_phu BETWEEN 0 AND 100),
  do_phu_tl       NUMERIC(5,2) CHECK (do_phu_tl BETWEEN 0 AND 100),
  bo_sung         INT NOT NULL DEFAULT 0 CHECK (bo_sung >= 0),
  so_yeu_cau      INT NOT NULL DEFAULT 0 CHECK (so_yeu_cau >= 0),
  chi_phi_usd     NUMERIC(10,4) NOT NULL DEFAULT 0 CHECK (chi_phi_usd >= 0),
  mau             JSONB NOT NULL DEFAULT '{}'::jsonb,
  bai_sot         JSONB NOT NULL DEFAULT '[]'::jsonb,
  hanh_dong       JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS kiem_do_phu_du_an_luc ON kiem_do_phu (du_an, luc DESC);

-- Hạn mức GÓI Apify (18/10/2026, chủ dự án: "đo kĩ phần hiển thị chi phí để ko bị lố so với thực tế
-- gói"): ảnh chụp `GET /v2/users/me/limits` (miễn phí) của tài khoản Apify Mark đang dùng — Mark ghi
-- sau mỗi lượt /theodoi, sau bước chốt lại chi phí và mỗi 3 giờ ở nhịp lịch quét. Vì sao bảng mà
-- không cho dashboard tự gọi Apify: dashboard không giữ APIFY_TOKEN (chỉ /opt/mark/app/.env có) —
-- không đưa token sang tiến trình thứ hai chỉ để đọc vài con số. Gói FREE 10 USD/chu kỳ (16/10–15/11)
-- là trần THẬT; trần tháng dự án 30 USD lớn hơn thì không có tác dụng — trang Ngân sách cảnh báo.
CREATE TABLE IF NOT EXISTS han_muc_apify (
  id              BIGSERIAL PRIMARY KEY,
  luc             TIMESTAMPTZ NOT NULL DEFAULT now(),
  goi             TEXT NOT NULL DEFAULT '',
  da_dung_usd     NUMERIC(10,4) NOT NULL CHECK (da_dung_usd >= 0),
  tran_usd        NUMERIC(10,2) NOT NULL CHECK (tran_usd >= 0),
  chu_ky_tu       TIMESTAMPTZ,
  chu_ky_den      TIMESTAMPTZ,
  tran_luot_usd   NUMERIC(10,2) CHECK (tran_luot_usd >= 0),
  du_tru_usd      NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (du_tru_usd >= 0),
  luot_id         BIGINT REFERENCES luot_quet(id) ON DELETE SET NULL,
  nguon_ghi       TEXT NOT NULL DEFAULT 'luot' CHECK (nguon_ghi IN ('luot', 'chot_lai', 'nhip'))
);
CREATE INDEX IF NOT EXISTS han_muc_apify_luc ON han_muc_apify (luc DESC);

-- ───────────── Mô tả bảng + cột theo quy chuẩn BI (task t280613, skill lsr-bq-description-standard) ─────────────
-- Chủ dự án 14/10/2026: DB mới cũng theo rule mô tả của BI (11 nhãn bảng, mô tả mọi cột). Ghi
-- ngay trong file build (COMMENT ON chạy lại không mất), có bài canh tests/test_theo_doi.py.

COMMENT ON TABLE du_an IS $$[Lớp] Raw
[Mục đích] Danh mục dự án/brand đang được lắng nghe và cấu hình lọc + thu thập (từ khoá, từ loại trừ, hashtag riêng, trần chi phí theo dõi mỗi tháng).
[Grain] 1 dòng = 1 dự án
[Khoá] PK: ma | Join: ma → nguon.du_an, bai.du_an, chi_so_ngay.du_an, luot_quet.du_an, de_xuat.du_an, lich_quet.du_an
[Nguồn] Người quản lý nhập trên dashboard social.hapas.vn (role lang_nghe_web); Mark chỉ đọc
[Phạm vi] Mọi dự án lắng nghe | Kênh: Không có | Dữ liệu từ khi bật đợt 2 (sau 14/10/2026); cột hashtag từ 18/10/2026
[Đã xử lý] Mã dự án chữ thường; thị trường 2 chữ in hoa; hashtag bỏ #, bỏ dấu, chữ thường, chỉ a-z 0-9 _; trần tháng ≥ 0 USD (ràng buộc CHECK)
[Refresh] Ghi tức thời khi người quản lý sửa trên dashboard (mỗi lần sửa ghi nhat_ky)
[Dùng khi] Biết dự án nào đang bật, từ khoá lọc, trần chi phí tháng
[Không dùng khi] Chi phí đã tiêu → dùng luot_quet; bài và tương tác → dùng bai; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.du_an
[Lưu ý] Cấu hình hiện hành, không giữ lịch sử (lịch sử sửa ở nhat_ky). Tắt dự án thì /theodoi từ chối.$$;
COMMENT ON COLUMN du_an.ma IS 'Mã dự án, chữ gõ sau /theodoi (vd hapas). PK. Chữ thường, số, -, _; 2–40 ký tự. Join: → nguon.du_an, bai.du_an, luot_quet.du_an.';
COMMENT ON COLUMN du_an.ten IS 'Tên hiển thị của dự án (vd HAPAS). Không NULL.';
COMMENT ON COLUMN du_an.tu_khoa IS 'Từ khoá dự án; bài từ nguồn không phải kênh nhà phải nhắc ít nhất một từ (so khớp bỏ dấu, không phân biệt hoa thường). Mảng rỗng: Mark dùng tên dự án.';
COMMENT ON COLUMN du_an.tu_loai_tru IS 'Từ loại trừ: bài chứa một từ này bị bỏ cứng trước bước AI. Mảng rỗng khi không đặt.';
COMMENT ON COLUMN du_an.boi_canh IS 'Mô tả brand cho bước AI phân xử giữ/loại và gán sắc thái, chủ đề. Chuỗi rỗng khi chưa viết.';
COMMENT ON COLUMN du_an.thi_truong IS 'Mã nước 2 chữ (ISO 3166-1) của thị trường chính, mặc định VN. Từ 18/10/2026 dashboard không còn ô sửa: dự án mới luôn VN, dự án cũ giữ giá trị đã lưu; Mark vẫn dùng cho cổng thị trường và bước AI.';
COMMENT ON COLUMN du_an.hashtag IS 'Hashtag riêng của dự án, người quản lý nhập ở trang Nguồn (từ 18/10/2026): đã bỏ #, bỏ dấu (đ→d), chữ thường, chỉ a-z 0-9 _, bỏ trùng, giữ thứ tự gõ; tối đa 50 mục, mỗi mục ≤ 100 ký tự. Mark dùng cho lượt tìm hashtag Instagram (lấy cau_hinh.tu_khoa.instagram.so_tu hashtag đầu, mặc định 12) và feed hashtag TikTok (bỏ thêm dấu _, chỉ tag 3–40 ký tự). Mảng rỗng (mặc định; mọi dự án trước 18/10/2026): Mark suy hashtag từ tu_khoa như trước — Instagram: mọi từ khoá viết liền bỏ dấu, TikTok: từ khoá một chữ. Không dùng để lọc bài (bài vẫn lọc theo tu_khoa, tu_loai_tru).';
COMMENT ON COLUMN du_an.tran_usd_thang IS 'Trần chi phí theo dõi mỗi tháng (giờ VN), USD tiền Apify, không VAT, ≥ 0 (không trần trên). Chỉ lượt kieu = theo_doi tính vào trần; trần mỗi lượt trên console platform vẫn áp dụng riêng.';
COMMENT ON COLUMN du_an.dang_bat IS 'TRUE: dự án bật, /theodoi được quét. FALSE: tắt, /theodoi từ chối.';
COMMENT ON COLUMN du_an.tao_luc IS 'Thời điểm tạo dự án (TIMESTAMPTZ, hiển thị theo múi giờ phiên; lưu UTC).';
COMMENT ON COLUMN du_an.sua_luc IS 'Thời điểm sửa dự án gần nhất (TIMESTAMPTZ, lưu UTC).';
COMMENT ON COLUMN du_an.bl_bat IS 'Công tắc TỔNG cào bình luận. TRUE: mỗi lượt /theodoi cào bình luận theo cấu hình từng nền tảng (cau_hinh.binh_luan; tính vào trần tháng). FALSE: không nền tảng nào cào, dù cau_hinh bật. Lưu cấu hình trên dashboard đặt = có ít nhất một nền tảng bật.';
COMMENT ON COLUMN du_an.bl_so_bai IS 'Số bài mặc định được cào bình luận mỗi lượt cho TỪNG nền tảng (khi cau_hinh không ghi đè), bài, ≥ 0 (không trần trên). 0 = không cào. Ưu tiên bài chưa cào, rồi bài có số bình luận tăng ≥ 20%.';
COMMENT ON COLUMN du_an.bl_moi_bai IS 'Số bình luận tối đa cào mỗi bài mỗi lượt, bình luận. 0 (mặc định) = cào HẾT bình luận + trả lời của bài (Facebook lần sau chỉ lấy bình luận mới; bài quá to cho trần mỗi lượt thì cào tiếp ở lượt sau); ≥ 5 = giới hạn. Actor tính tiền theo bình luận (TikTok 0,00125, Facebook 0,0025, Instagram 0,0026, Threads 0,0025 USD + 0,02 khởi động; YouTube miễn phí). Threads chỉ nhận 10–300 trả lời mỗi bài.';
COMMENT ON COLUMN du_an.tk_bat IS 'Công tắc TỔNG tìm theo từ khoá. TRUE: mỗi lượt /theodoi còn TÌM theo từ khoá dự án trên các nền tảng bật trong cau_hinh.tu_khoa để bắt bài của mọi tài khoản (tính vào trần tháng). FALSE: chỉ quét nguồn đã theo dõi, dù cau_hinh bật.';
COMMENT ON COLUMN du_an.tk_so_bai IS 'Số bài mặc định lấy mỗi nền tảng mỗi lượt khi tìm theo từ khoá (khi cau_hinh không ghi đè), bài, ≥ 0 (không trần trên; Facebook gói Free thực tế tối đa 20 bài, 1 lượt/24h; Threads chỉ tìm số bài // 10 từ khoá đầu vì actor lấy ≥ 10 bài mỗi từ). 0 = không tìm.';
COMMENT ON COLUMN du_an.cau_hinh IS 'Cấu hình thu thập theo từng nền tảng (JSON), sửa ở trang Ngân sách: {"tu_khoa": {"<nền tảng>": {"bat", "so_bai" ≥ 0, "so_tu" ≥ 1}}, "binh_luan": {"<nền tảng>": {"bat", "so_bai" ≥ 0, "moi_bai" 0 = hết hoặc ≥ 5}}} — không trần trên nghiệp vụ (chỉ chặn số rác > 1.000.000). Khoá thiếu/giá trị rác thì dùng cột chung tk_* / bl_*; chỉ bat = true là bật; thiếu bat thì bật theo cột chung, TRỪ threads (thiếu bat = tắt — chủ dự án bật trên trang Ngân sách, từ 16/10/2026); cột tk_bat / bl_bat là công tắc tổng. {} = theo cột chung (Threads tắt). Từ 17/10/2026 "tu_khoa"."threads" có thêm "duong2": {"bat", "so_bai" = trần bài cả lượt (0 = tắt, mặc định 100), "so_bai_moi_tu" (mặc định 20), "so_luot" 1–5 (mặc định 2)} cho đường 2 tìm Threads (scrapersdelight) — chỉ chạy khi Threads bật; thiếu bat = BẬT, false = tắt. Cũng từ 17/10/2026: "tu_khoa"."facebook" có "duong2": {"bat", "so_bai_moi_tu" (bài mới nhất mỗi cụm, mặc định 12, 0 = tắt), "gio" (giờ tối thiểu giữa hai lượt, mặc định 20), "gio_chien_dich" (giờ tối thiểu khi đang có lịch chiến dịch, mặc định = gio; hạ xuống thì quét dày hơn — 6 giờ ≈ 4 lượt/ngày, tới ~25 USD/tháng/dự án)} cho đường 2 tìm Facebook (mina, chỉ cụm nhiều chữ có tên brand) — thiếu bat thì theo Facebook (số bài > 0); "tu_khoa"."tiktok" có "hashtag": {"bat", "so_yeu_cau" (trần yêu cầu mỗi lượt, mặc định 5, 0 = tắt), "gio" (mặc định 20)} cho feed hashtag TikTok của từ khoá một chữ — thiếu bat thì theo TikTok; "so_tu" của instagram là số hashtag mỗi lượt (mặc định 12). Từ 18/10/2026 "tu_khoa"."<nền tảng>"."bo_tu": danh sách từ khoá KHÔNG đem đi tìm trên nền tảng đó (mọi đường tìm của nền tảng; so trọn cụm, bỏ dấu, không phân biệt hoa thường; Instagram / feed hashtag TikTok: mục một chữ bỏ hashtag cùng dạng viết liền) — bài vẫn lọc theo đủ tu_khoa; sửa ở khối Nâng cao trang Ngân sách ("Không tìm trên…"), thiếu/rỗng = tìm mọi từ khoá. Cũng từ 18/10/2026 "seeding": {"bat" (thiếu = BẬT, chỉ false là tắt), "bai_mot_ngay" (mặc định 5), "bai_bay_ngay" (20), "trung_vi_bl" (2), "trung_vi_xem" (15000, 0 = bỏ điều kiện xem), "trung_vi_tuong_tac" (300, trung vị thích + chia sẻ thay điều kiện xem khi tài khoản không có số xem nào — chưa hiệu chỉnh, 0 = bỏ), "giu_bl_tu" (10, 0 = không giữ bài nào), "ngay" (35, số ngày lịch sử), "mien_ten_brand" (thiếu = true), "nen_tang" (mặc định ["tiktok"] — nền tảng đã hiệu chỉnh; thêm youtube / facebook / instagram / threads để bật; lượt xem 0 của Facebook / Instagram / Threads là thiếu số)} cho luật seeding affiliate cấp bài: tài khoản đăng ≥ bai_mot_ngay bài liên quan trong một ngày hoặc ≥ bai_bay_ngay bài trong 7 ngày, VÀ trung vị bình luận ≤ trung_vi_bl, trung vị lượt xem ≤ trung_vi_xem thì bài của nó không vào bai (trừ bài ≥ giu_bl_tu bình luận); kênh nhà và tài khoản mang tên dự án ở định danh hoặc tên hiển thị không bao giờ bị bắt; số rác/ngoài khoảng → mặc định. "tu_khoa"."instagram" / "facebook" / "threads" có "gian": {"bat" (thiếu = BẬT), "luot" (mặc định 3, 1–6), "ty_le" (0,05), "gio" (44)} giãn nhịp đường tìm ít bài mới: luot lượt tìm liền có bài mới < ty_le × bài về thì chỉ tìm lại sau gio giờ (chiến dịch đang chạy thì không giãn); lưu trang Ngân sách giữ nguyên khối này và mọi khoá biểu mẫu không có ô. Cũng từ 18/10/2026 "hashtag_can_nhac_brand": true / false hoặc {"bat" (thiếu = BẬT, chỉ false là tắt), "ten" (danh sách tên brand thêm, vd thương hiệu con), "tag_rong" (hashtag rộng KHÔNG tính là tên brand, thiếu = ["quatang2010"])} cho cổng brand của bài CHỈ đến từ đường hashtag (feed hashtag TikTok, Instagram tìm theo hashtag, TikTok dự phòng theo hashtag, mẫu hashtag của kiểm độ phủ): bài chỉ vào bai khi nội dung, hashtag, tên hoặc định danh chủ bài (hoặc chính hashtag của feed) gọi tên dự án, mã dự án, một tên trong "ten" hoặc một tag chiến dịch của dự án (du_an.hashtag, tag kiểm độ phủ thêm vào lượt nổi, khẩu hiệu lịch chiến dịch đang chạy — dạng viết liền, trừ tag_rong và tag chung chung; từ 18/10/2026) (bỏ dấu, không phân biệt hoa thường); kênh nhà miễn; bài bị bỏ trước AI, vào sổ đã loại với lý do hashtag_khong_nhac_brand (mỗi lượt xét lại theo danh sách tên hiện hành — thêm tên / tag là gỡ được; chưa có ô trên trang Ngân sách: sửa JSON bằng jsonb_set, lệnh mẫu ở theo_doi.py, lưu trang Ngân sách giữ nguyên khối).';
COMMENT ON COLUMN du_an.sua_boi IS 'Email người sửa gần nhất trên dashboard. NULL khi tạo bằng lệnh cài đặt. Email nội bộ — không đẩy lên BigQuery.';

COMMENT ON TABLE nguon IS $$[Lớp] Raw
[Mục đích] Danh sách nguồn mạng xã hội đang theo dõi của từng dự án, kèm chu kỳ quét và tình trạng quét gần nhất.
[Grain] 1 dòng = 1 nguồn (1 tài khoản/kênh/trang trên 1 nền tảng) của 1 dự án
[Khoá] PK: id | UNIQUE: du_an + nen_tang + dinh_danh | Join: du_an → du_an.ma; id → bai.nguon_id
[Nguồn] Người quản lý thêm/sửa trên dashboard (hoặc duyệt từ de_xuat); Mark chỉ ghi quet_cuoi, loi_cuoi, loi_luc
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (từ 16/10/2026) | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Định danh chuẩn hoá (chữ thường, bỏ @ và tham số URL; id kênh YouTube UC… giữ nguyên)
[Refresh] Ghi tức thời khi người quản lý sửa; Mark cập nhật cột quét sau mỗi lượt /theodoi
[Dùng khi] Nguồn nào đang theo dõi, tới hạn quét, lỗi gần nhất
[Không dùng khi] Bài của nguồn → dùng bai; nguồn chờ duyệt → dùng de_xuat; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.nguon
[Lưu ý] Xoá nguồn thì bài cũ giữ lại với nguon_id NULL; nên tạm dừng thay vì xoá.$$;
COMMENT ON COLUMN nguon.id IS 'Mã nguồn tự tăng. PK. Join: → bai.nguon_id.';
COMMENT ON COLUMN nguon.du_an IS 'Dự án của nguồn. FK → du_an.ma.';
COMMENT ON COLUMN nguon.nen_tang IS 'Nền tảng. Giá trị: tiktok, instagram, youtube, facebook, threads (từ 16/10/2026).';
COMMENT ON COLUMN nguon.dinh_danh IS 'Định danh nguồn đã chuẩn hoá: username TikTok/Instagram/Threads (chữ thường, không @), id kênh YouTube (UC…) hoặc @handle, URL trang Facebook. Duy nhất trong (du_an, nen_tang).';
COMMENT ON COLUMN nguon.ten IS 'Tên hiển thị của nguồn. Chuỗi rỗng khi chưa nhập.';
COMMENT ON COLUMN nguon.link IS 'Link hồ sơ/kênh/trang. Chuỗi rỗng khi chưa nhập.';
COMMENT ON COLUMN nguon.loai IS 'Loại nguồn. Giá trị: kol, page, group, bao, kenh_nha (kênh của chính brand — giữ mọi bài), khac.';
COMMENT ON COLUMN nguon.nhan IS 'Nhãn tự do để lọc (vd đối thủ, top Kompa). Mảng rỗng khi không gắn.';
COMMENT ON COLUMN nguon.trang_thai IS 'Giá trị: dang_theo_doi (được quét khi tới hạn), tam_dung (bỏ qua).';
COMMENT ON COLUMN nguon.chu_ky_ngay IS 'Chu kỳ quét, ngày (1–30). Tới hạn khi lần quét cuối cách ≥ chu kỳ trừ 3 giờ.';
COMMENT ON COLUMN nguon.so_bai_moi_lan IS 'Số bài mới nhất lấy mỗi lần quét, bài (≥ 1, không trần trên). Instagram: actor hồ sơ chỉ trả 12 bài mới nhất. Threads: actor lấy (và tính tiền) tối thiểu 10 bài mỗi tài khoản.';
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
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Threads (từ 16/10/2026) | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Chỉ tài khoản ≥ 2 bài hoặc ≥ 50 thảo luận trong lượt; tối đa 10 mỗi lượt; bỏ nguồn đã có
[Refresh] Mark upsert sau mỗi lượt tìm theo từ khoá (số liệu ghi đè lần mới nhất)
[Dùng khi] Danh sách nguồn chờ duyệt và lý do đề xuất
[Không dùng khi] Nguồn đang theo dõi → dùng nguon
[Lưu ý] Mark không tự thêm nguồn; duyệt thì dashboard thêm dòng nguon với them_qua = de_xuat. Không đẩy lên BigQuery.$$;
COMMENT ON COLUMN de_xuat.id IS 'Mã đề xuất tự tăng. PK.';
COMMENT ON COLUMN de_xuat.du_an IS 'Dự án nhận đề xuất. FK → du_an.ma.';
COMMENT ON COLUMN de_xuat.nen_tang IS 'Nền tảng của tài khoản. Giá trị: tiktok, instagram, youtube, threads.';
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
[Khoá] PK: id | Join: du_an → du_an.ma; id → bai.luot_dau, bai.luot_cuoi; lich_id → lich_quet.id
[Nguồn] Mark mở lượt khi bắt đầu, đóng khi xong (cả khi lỗi); chi phí = tổng usageTotalUsd đúng các run Apify của lượt
[Phạm vi] Mọi dự án | Kênh: Không có | Từ khi bật đợt 2 (sau 14/10/2026)
[Đã xử lý] Không xử lý
[Refresh] Ghi tức thời khi Mark mở/đóng lượt
[Dùng khi] Chi phí theo dõi theo tháng (SUM chi_phi_usd WHERE kieu = 'theo_doi', tháng giờ VN); tỉ lệ nguồn lỗi
[Không dùng khi] Bài và tương tác → dùng bai; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.luot_quet
[Lưu ý] Lượt kẹt dang_chay quá 3 giờ được đóng thành loi ở lượt sau.$$;
COMMENT ON COLUMN luot_quet.id IS 'Mã lượt tự tăng. PK.';
COMMENT ON COLUMN luot_quet.du_an IS 'Dự án của lượt. FK → du_an.ma.';
COMMENT ON COLUMN luot_quet.kieu IS 'Giá trị: theo_doi (lượt /theodoi, tính vào trần tháng), tu_khoa (lượt tìm theo từ khoá ghi vào kho; cả lượt nạp raw đã trả tiền bằng scripts/lang_nghe_nap_raw.py từ 18/10/2026, chi phí 0).';
COMMENT ON COLUMN luot_quet.ma_viec IS 'Mã việc nền của Mark (đối chiếu /viec). NULL với lượt tu_khoa của social_listen; nap-raw-<năm tháng ngày giờ phút> với lượt nạp raw (scripts/lang_nghe_nap_raw.py, từ 18/10/2026).';
COMMENT ON COLUMN luot_quet.job_id IS 'Mã job platform đã giao lượt. NULL khi không có.';
COMMENT ON COLUMN luot_quet.bat_dau IS 'Thời điểm bắt đầu lượt (UTC).';
COMMENT ON COLUMN luot_quet.ket_thuc IS 'Thời điểm kết thúc lượt (UTC). NULL khi đang chạy.';
COMMENT ON COLUMN luot_quet.so_nguon IS 'Số nguồn lượt xét, nguồn.';
COMMENT ON COLUMN luot_quet.so_nguon_loi IS 'Số nguồn không lấy được bài, nguồn.';
COMMENT ON COLUMN luot_quet.bai_moi IS 'Số bài lần đầu vào kho trong lượt, bài.';
COMMENT ON COLUMN luot_quet.bai_cap_nhat IS 'Số bài đã có được cập nhật trong lượt, bài.';
COMMENT ON COLUMN luot_quet.chi_phi_usd IS 'Chi phí Apify THẬT của lượt, USD, không VAT: tổng usageTotalUsd đúng các run của lượt, đọc khi run cuối đã xong ≥ 45 giây; Mark đọc lại ~90 giây sau run cuối và NÂNG số nếu Apify ghi thêm phí sự kiện (chỉ nâng, không hạ; từ 17/10/2026 — lượt cũ hơn có thể thiếu phí ghi trễ). 0 với lượt chỉ dùng YouTube Data API và lượt tu_khoa (chi phí đó ở sổ chi phí quét). Không âm.';
COMMENT ON COLUMN luot_quet.trang_thai IS 'Giá trị: dang_chay, xong, mot_phan (một số nguồn lỗi), loi, da_huy.';
COMMENT ON COLUMN luot_quet.loi IS 'Tóm tắt lỗi, tối đa 500 ký tự. NULL khi không lỗi.';
COMMENT ON COLUMN luot_quet.ghi_chu IS 'Ghi chú vận hành (vd hết ngân sách tháng, bot khởi động lại giữa lượt, nền tảng bỏ qua/lỗi kèm lý do) và phễu từng nền tảng của lượt tìm theo từ khoá, các câu nối bằng "; ". Tối đa 20.000 ký tự (từ 17/10/2026; trước đó 2.000 — lượt cũ có thể cụt), quá thì cắt và ghi dấu đã cắt ở cuối. NULL khi không có.';
COMMENT ON COLUMN luot_quet.lich_id IS 'Lịch quét tự động đã giao lượt này. FK → lich_quet.id. NULL khi lượt gõ tay /theodoi, lịch Giao việc trên console, lượt tu_khoa, hoặc lịch đã bị xoá.';

COMMENT ON TABLE bai IS $$[Lớp] Raw
[Mục đích] Bài mạng xã hội liên quan tới dự án mà Mark đã giữ, kèm nhãn AI và tương tác mới nhất.
[Grain] 1 dòng = 1 bài × 1 dự án
[Khoá] PK: du_an + khoa | Join: du_an → du_an.ma; nguon_id → nguon.id; (du_an, khoa) → chi_so_ngay, binh_luan; luot_dau, luot_cuoi → luot_quet.id
[Nguồn] Mark ghi sau mỗi lượt /theodoi (Apify theo tài khoản, YouTube Data API) và lượt tìm theo từ khoá (/theodoi, social_listen)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (nguồn theo dõi + tìm theo từ khoá từ 16/10/2026; trước đó chỉ từ social_listen), Báo & Web (nen_tang = web: báo, diễn đàn, blog tìm qua Google, từ 16/10/2026) | Bài đăng từ 17/09/2026: mỗi lượt quét giữ bài đăng trong 35 ngày trước lượt (từ khi bật đợt 2, 14/10/2026); bài đăng 17/09 → 14/10/2026 nạp từ raw đã trả tiền (scripts/lang_nghe_nap_raw.py, kieu_quet tu_khoa / theo_doi, từ 18/10/2026)
[Đã xử lý] Chỉ bài liên quan (nhắc từ khoá trừ kênh nhà, không chứa từ loại trừ, không bị AI loại); từ 18/10/2026 không có bài seeding affiliate (mặc định chỉ TikTok — nền tảng khác bật ở du_an.cau_hinh.seeding.nen_tang; tài khoản không phải kênh nhà, không mang tên brand, đăng ≥ 5 bài/ngày hoặc ≥ 20 bài/7 ngày với trung vị ≤ 2 bình luận và ≤ 15.000 lượt xem — ngưỡng ở du_an.cau_hinh.seeding; bài tự có ≥ 10 bình luận vẫn giữ; bài cũ dọn bằng scripts/lang_nghe_loc_seeding.py), bài tìm theo từ khoá ngoài thị trường VN (nội dung chữ Thái/Hàn/Trung/Hindi… hoặc kênh YouTube khai nước khác, không có dấu hiệu Việt; ca mơ hồ như tài khoản brand nước khác viết Latin do AI phán mã other_market — từ 18/10/2026) và bài chỉ đến từ đường hashtag (feed hashtag TikTok, Instagram hashtag) mà không gọi tên brand ở nội dung, hashtag, tên hay định danh chủ bài (tên brand gồm tag chiến dịch của dự án: du_an.hashtag, tag kiểm độ phủ thêm vào lượt nổi, khẩu hiệu lịch chiến dịch đang chạy — trừ tag rộng như #quatang2010; trừ kênh nhà; tắt ở du_an.cau_hinh.hashtag_can_nhac_brand); khử trùng theo khoa; bài Facebook khử trùng thêm theo id số ma_so_fb, không có id thì theo chủ bài + phút đăng + nội dung (pfbid trong link đổi mỗi lượt cào, từ 17/10/2026; bản trùng cũ gộp bằng scripts/lang_nghe_gop_bai_fb.py); nội dung cắt 1.000 ký tự
[Refresh] Upsert tức thời sau mỗi lượt quét; video YouTube được đọc lại số mỗi ngày trong 14 ngày đầu
[Dùng khi] Đếm bài, thảo luận (1 + binh_luan), nguồn nổi bật, sắc thái, chủ đề
[Không dùng khi] Tăng trưởng theo ngày → dùng chi_so_ngay; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.bai
[Lưu ý] Số là lần đọc gần nhất, không phải cuối kỳ. Mẫu theo nguồn đã chọn + lượt tìm, không phải toàn bộ thảo luận trên mạng.$$;
COMMENT ON COLUMN bai.du_an IS 'Dự án. Một phần PK. FK → du_an.ma.';
COMMENT ON COLUMN bai.khoa IS 'Khoá bài "<nền tảng>:<id bài>" (không bóc được id thì "h" + 16 ký tự băm SHA-1 của link). Một phần PK.';
COMMENT ON COLUMN bai.nen_tang IS 'Nền tảng. Giá trị: tiktok, instagram, youtube, facebook, threads, web (Báo & Web: báo, diễn đàn, blog tìm qua Google, từ 16/10/2026).';
COMMENT ON COLUMN bai.nguon_id IS 'Nguồn theo dõi cho ra bài. FK → nguon.id. NULL khi bài từ tìm theo từ khoá (tài khoản chưa theo dõi) hoặc nguồn đã bị xoá.';
COMMENT ON COLUMN bai.kieu_quet IS 'Giá trị: theo_doi, tu_khoa. Bài từng là theo_doi thì giữ theo_doi.';
COMMENT ON COLUMN bai.link IS 'Link bài gốc. Không NULL.';
COMMENT ON COLUMN bai.tac_gia IS 'Tên hiển thị kênh/tài khoản đăng. Chuỗi rỗng khi không có.';
COMMENT ON COLUMN bai.tai_khoan IS 'Username tài khoản đăng (TikTok, Instagram, Threads); tên miền trang với web (vd cafef.vn). Chuỗi rỗng với YouTube.';
COMMENT ON COLUMN bai.followers IS 'Người theo dõi tài khoản đăng lúc đọc gần nhất, người. NULL khi nền tảng không trả.';
COMMENT ON COLUMN bai.dang_luc IS 'Thời điểm đăng bài (UTC; giờ VN = dang_luc AT TIME ZONE ''Asia/Ho_Chi_Minh'').';
COMMENT ON COLUMN bai.noi_dung IS 'Nội dung/caption (YouTube: tiêu đề — mô tả; web: tiêu đề | tối đa 3 đoạn quanh chỗ nhắc brand, không lưu toàn văn), tối đa 1.000 ký tự.';
COMMENT ON COLUMN bai.hashtag IS 'Hashtag không có #, phân cách ", ", tối đa 500 ký tự.';
COMMENT ON COLUMN bai.khop_tu_khoa IS 'TRUE: nhắc ít nhất một từ khoá dự án. FALSE: không nhắc (chỉ giữ khi nguồn là kenh_nha).';
COMMENT ON COLUMN bai.sac_thai IS 'Sắc thái do AI gán. Giá trị: Tích cực, Tiêu cực, Trung lập. NULL khi AI chưa gán.';
COMMENT ON COLUMN bai.chu_de IS 'Chủ đề do AI gán theo 13 chủ đề của Mark. NULL khi AI chưa gán.';
COMMENT ON COLUMN bai.ly_do_giu IS 'Vì sao giữ: mã AI (brand, ad, product, ugc, other_market) hoặc kenh_nha / khop_tu_khoa.';
COMMENT ON COLUMN bai.xem IS 'Lượt xem lần đọc gần nhất, lượt. NULL khi nền tảng không trả (luôn NULL với web).';
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
COMMENT ON COLUMN bai.kieu_trang IS 'Loại trang của bài web. Giá trị: bao (báo/tạp chí), dien_dan (diễn đàn), blog, mxh_khac (LinkedIn, X, Lemon8…), khac (trang khác). NULL với bài mạng xã hội (nen_tang khác web).';
COMMENT ON COLUMN bai.muc_nhac IS 'Mức nhắc brand trong bài web. Giá trị: tieu_de (từ khoá ở tiêu đề), chinh (≥ 3 lần trong thân bài), thoang (nhắc lướt 1–2 lần, vd bài liệt kê nhiều brand). NULL với bài mạng xã hội.';
COMMENT ON COLUMN bai.la_pr IS 'TRUE: bài web có dấu hiệu bài đặt/PR (thân bài dẫn link về miền của brand hoặc ghi "Ảnh/Nguồn: <brand>"). FALSE: không thấy dấu hiệu. NULL với bài mạng xã hội.';
COMMENT ON COLUMN bai.ma_so_fb IS 'Id số ổn định của bài Facebook (5–25 chữ số): id bài actor trả (postId, post_id, post.id, feedbackId), không có thì bóc từ link (/posts/, /videos/, /reel/, /permalink/, story_fbid=). Dùng để nhận bản trùng: pfbid trong link và khoa đổi mỗi lượt cào (đo 17/10/2026). Không phải khoá (PK là du_an + khoa), không join bảng khác; không duy nhất (bản trùng cũ chưa gộp có thể cùng id). NULL với nền tảng khác, bài ghi trước 17/10/2026 chưa được quét lại (quét lại thì Mark điền), hoặc link pfbid mà actor không trả id.';

COMMENT ON TABLE binh_luan IS $$[Lớp] Raw
[Mục đích] Bình luận (và trả lời) dưới các bài đã giữ của dự án, kèm sắc thái và chủ đề AI gán — tiếng khách hàng.
[Grain] 1 dòng = 1 bình luận × 1 bài × 1 dự án
[Khoá] PK: du_an + khoa_bai + ma | Join: (du_an, khoa_bai) → bai.(du_an, khoa); luot_id → luot_quet.id
[Nguồn] Mark cào sau mỗi lượt /theodoi: Apify (TikTok, Facebook, Instagram comments scraper; Threads replies scraper), YouTube Data API
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads (từ 16/10/2026) | Bài đăng trong 35 ngày; tối đa bl_so_bai bài mỗi lượt, mỗi bài cào hết (bl_moi_bai = 0) hoặc tới bl_moi_bai bình luận; từ 15/10/2026
[Đã xử lý] Khử trùng theo ma; nội dung cắt 1.000 ký tự; mỗi dòng gắn nhãn lọc loai (hop_le/it_noi_dung/spam/trung/seeding/thuong_hieu; spam gồm spam affiliate, lọc lại dữ liệu cũ bằng scripts/lang_nghe_loc_lai.py) — chỉ hop_le được gán sắc thái/chủ đề
[Refresh] Upsert tức thời sau mỗi lượt quét (bài được cào lại khi số bình luận tăng ≥ 20%)
[Dùng khi] Đọc từng bình luận; thảo luận sạch (loai = 'hop_le'); sắc thái/chủ đề bình luận; tỷ lệ spam/seeding; món khách hỏi mua (san_pham)
[Không dùng khi] Tổng bình luận nền tảng báo → dùng bai.binh_luan; bản cho BI → dùng ganesha-381907.SOCIAL_LISTENING.binh_luan
[Lưu ý] Đếm thảo luận sạch phải lọc loai = 'hop_le'; Instagram chưa đăng nhập chỉ trả một phần, Threads chỉ trả lời cấp 1 (10–300 mỗi bài), Facebook/TikTok bài rất lớn có thể thiếu (so bai.bl_da_lay với bai.binh_luan để biết độ phủ).$$;
COMMENT ON COLUMN binh_luan.du_an IS 'Dự án. Một phần PK. FK (cùng khoa_bai) → bai.';
COMMENT ON COLUMN binh_luan.khoa_bai IS 'Khoá bài chứa bình luận. Một phần PK. FK (cùng du_an) → bai.khoa.';
COMMENT ON COLUMN binh_luan.ma IS 'Mã bình luận trên nền tảng; không có thì "h" + 16 ký tự băm SHA-1 (tác giả, nội dung, thời điểm). Một phần PK.';
COMMENT ON COLUMN binh_luan.nen_tang IS 'Nền tảng. Giá trị: tiktok, instagram, youtube, facebook, threads.';
COMMENT ON COLUMN binh_luan.tac_gia IS 'Tên/username người bình luận (công khai trên nền tảng). Chuỗi rỗng khi không có.';
COMMENT ON COLUMN binh_luan.noi_dung IS 'Nội dung bình luận, tối đa 1.000 ký tự.';
COMMENT ON COLUMN binh_luan.thich IS 'Lượt thích bình luận lúc cào, lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN binh_luan.tra_loi IS 'Số trả lời của bình luận lúc cào, bình luận. NULL khi nền tảng không trả.';
COMMENT ON COLUMN binh_luan.la_tra_loi IS 'TRUE: dòng là trả lời của một bình luận khác. FALSE: bình luận gốc.';
COMMENT ON COLUMN binh_luan.cua_thuong_hieu IS 'TRUE: do tài khoản của chính thương hiệu viết (không gán nhãn, không tính sắc thái). FALSE: khách.';
COMMENT ON COLUMN binh_luan.dang_luc IS 'Thời điểm đăng bình luận (UTC). NULL khi nền tảng chỉ trả thời gian tương đối.';
COMMENT ON COLUMN binh_luan.sac_thai IS 'Sắc thái AI/luật gán. Giá trị: Tích cực, Tiêu cực, Trung lập. NULL khi chưa gán hoặc bình luận của thương hiệu.';
COMMENT ON COLUMN binh_luan.chu_de IS 'Chủ đề bình luận theo 8 nhóm của Mark (Sản phẩm/chất lượng, Giá/mua ở đâu/ý định mua, KOL/nội dung, Giao hàng/dịch vụ, Đối thủ, Tag bạn bè, Minigame/bài dự thi, Khác). Minigame/bài dự thi = bài dự thi/lời chúc theo đề bài của brand, từ 16/10/2026; dashboard ẩn khỏi mây từ khoá. NULL khi chưa gán.';
COMMENT ON COLUMN binh_luan.luot_id IS 'Lượt quét cào bình luận gần nhất. FK → luot_quet.id.';
COMMENT ON COLUMN binh_luan.thay_lan_dau IS 'Thời điểm ghi bình luận lần đầu (UTC).';
COMMENT ON COLUMN binh_luan.cap_nhat_cuoi IS 'Thời điểm cập nhật gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON COLUMN binh_luan.loai IS 'Nhãn lọc (loc_rac.py). Giá trị: hop_le (tính vào thảo luận sạch, có sắc thái), it_noi_dung (chỉ dấu chấm/emoji/tag/"chấm" — tương tác nhưng không có ý), spam (quảng cáo/lừa đảo/kéo khách, gồm spam affiliate mời dán mã giới thiệu vào Shopee), trung (cùng người cùng nội dung cùng bài, giữ bản đầu), seeding (cùng nội dung ≥ 40 ký tự từ ≥ 3 tài khoản trên ≥ 2 bài trong 7 ngày), thuong_hieu (chính thương hiệu viết).';
COMMENT ON COLUMN binh_luan.link IS 'Link mở thẳng tới bình luận khi nền tảng có (Facebook/Instagram commentUrl, Threads reply_url, YouTube &lc=); NULL thì mở bài (bai.link).';
COMMENT ON COLUMN binh_luan.ma_cha IS 'Mã bình luận cha khi dòng là trả lời (cùng khoa_bai). NULL với bình luận gốc hoặc nền tảng không trả.';
COMMENT ON COLUMN binh_luan.san_pham IS 'Món khách hỏi mua, chỉ có ở bình luận hỏi mua (AI gán cùng sắc thái/chủ đề, đọc cả nội dung bài; từ 17/10/2026). Giá trị: tui (túi xách, balo), vi (ví), nuoc_hoa (nước hoa), trang_suc (trang sức), set_qua (set/combo/hộp quà nhiều món), khac (món khác của brand), ngoai_brand (đồ không phải hàng của brand, vd quần áo người trong video mặc — dashboard không tính là ý định mua), chua_ro (không đoán được món). NULL khi không phải bình luận hỏi mua, chưa gán nhãn, gán trước 17/10/2026 chưa gán lại, hoặc loai khác hop_le.';
COMMENT ON COLUMN binh_luan.ly_do_loc IS 'Lý do lọc khi loai không phải hop_le (vd lien_ket_quang_cao, keo_khach, vay_tien, co_bac, viec_lam_mmo, ban_hang_khac, so_dien_thoai_quang_cao, cung_nguoi_cung_noi_dung, cung_noi_dung_nhieu_tai_khoan; affiliate_dan_ma = một bình luận có mã giới thiệu nhiều khúc kèm lời dặn dán mã hoặc tên sàn, hoặc chữ kiểu cách kèm lời dặn; affiliate_hang_loat = ≥ 5 tài khoản có mã (hoặc chữ kiểu cách + lời dặn/tên sàn) dưới cùng một bài trong 48 giờ theo giờ đăng, trừ mã của chính thương hiệu). NULL khi hợp lệ.';
COMMENT ON COLUMN binh_luan.ma_noi_dung IS 'Băm 16 ký tự nội dung đã chuẩn hoá khi nội dung ≥ 40 ký tự — để phát hiện seeding (cùng mã, ≥ 3 tài khoản, ≥ 2 bài, 7 ngày). NULL khi quá ngắn.';

COMMENT ON TABLE chi_so_ngay IS $$[Lớp] Raw
[Mục đích] Tương tác lũy kế của từng bài theo ngày đọc, để vẽ tăng trưởng và tính phần tăng trong kỳ.
[Grain] 1 dòng = 1 bài × 1 dự án × 1 ngày đọc (giờ VN)
[Khoá] PK: du_an + khoa + ngay | Join: (du_an, khoa) → bai.(du_an, khoa)
[Nguồn] Mark ghi mỗi lần đọc số của bài (ghi đè trong cùng ngày)
[Phạm vi] Mọi dự án | Nền tảng TikTok, Instagram, YouTube, Facebook, Threads | Từ khi bật đợt 2 (sau 14/10/2026)
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
[Nguồn] Người quản lý thêm/xoá trên dashboard; người quản lý đầu tiên thêm bằng lệnh quan_tri; tên, chức danh, phòng ban, trạng thái đọc từ danh bạ Lark (contact API)
[Phạm vi] Nhân viên HAPAS (tài khoản Lark của tổ chức) | Kênh: Không có | Từ khi cài dashboard
[Đã xử lý] Email chữ thường; trạng thái Lark quy về 5 giá trị
[Refresh] Ghi tức thời khi người quản lý sửa; cột danh bạ làm mới ≤ 12 giờ/lần khi mở trang Người xem và khi thêm email; dang_nhap_cuoi, lark_open_id, lark_union_id, lark_user_id ghi mỗi lượt đăng nhập
[Dùng khi] Kiểm quyền đăng nhập dashboard
[Không dùng khi] Lịch sử thêm/xoá → dùng nhat_ky
[Lưu ý] Email nội bộ — không đẩy lên BigQuery. Luôn phải còn ít nhất một quan_ly.$$;
COMMENT ON COLUMN nguoi_xem.email IS 'Email công ty (enterprise_email Lark), chữ thường. PK.';
COMMENT ON COLUMN nguoi_xem.vai_tro IS 'Giá trị: xem (chỉ xem), quan_ly (sửa dự án, nguồn, ngân sách, người xem).';
COMMENT ON COLUMN nguoi_xem.them_boi IS 'Email người thêm. NULL khi thêm bằng lệnh cài đặt.';
COMMENT ON COLUMN nguoi_xem.them_luc IS 'Thời điểm thêm (UTC).';
COMMENT ON COLUMN nguoi_xem.ten_lark IS 'Tên trong danh bạ Lark. NULL khi chưa đọc được hoặc không có trong danh bạ.';
COMMENT ON COLUMN nguoi_xem.chuc_danh IS 'Chức danh (job_title) trong danh bạ Lark. NULL khi trống, chưa đọc được hoặc app thiếu quyền đọc trường này.';
COMMENT ON COLUMN nguoi_xem.phong_ban IS 'Tên phòng ban trong danh bạ Lark, nhiều phòng nối bằng " · ". NULL khi chưa đọc được.';
COMMENT ON COLUMN nguoi_xem.trang_thai_lark IS 'Giá trị: hoat_dong, chua_kich_hoat, tam_khoa, nghi_viec, khong_co (không tìm thấy email trong danh bạ). NULL khi chưa đọc được lần nào.';
COMMENT ON COLUMN nguoi_xem.danh_ba_loi IS 'Lỗi lần đọc danh bạ gần nhất. Giá trị: thieu_quyen (app Lark chưa được cấp scope), loi (lỗi khác). NULL khi lần gần nhất đọc được.';
COMMENT ON COLUMN nguoi_xem.danh_ba_luc IS 'Thời điểm đọc danh bạ Lark gần nhất, kể cả lần lỗi (UTC). NULL khi chưa đọc.';
COMMENT ON COLUMN nguoi_xem.dang_nhap_cuoi IS 'Lần đăng nhập dashboard thành công gần nhất (UTC). NULL khi chưa đăng nhập kể từ khi có cột (lần đầu xem nhat_ky dang_nhap_lan_dau).';
COMMENT ON COLUMN nguoi_xem.lark_open_id IS 'open_id Lark của tài khoản (riêng cho app dashboard DASH_LARK_APP_ID). Ghi lúc đăng nhập, hoặc khi đọc danh bạ tìm được. NULL khi chưa đăng nhập và danh bạ chưa tìm thấy.';
COMMENT ON COLUMN nguoi_xem.lark_union_id IS 'union_id Lark của tài khoản (chung mọi app của cùng nhà phát triển; dùng khi đổi app Lark). Ghi lúc đăng nhập. NULL khi chưa đăng nhập.';
COMMENT ON COLUMN nguoi_xem.lark_user_id IS 'user_id Lark (mã nhân viên trong tổ chức). Ghi lúc đăng nhập. NULL khi chưa đăng nhập hoặc app thiếu scope contact:user.employee_id:readonly.';

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
COMMENT ON COLUMN dong_bo_bq.loi IS 'Lỗi lượt gần nhất (đã bỏ URL, tối đa 200 ký tự). Bắt đầu bằng "cảnh báo: " là CẢNH BÁO, không phải lỗi: lượt vẫn xong, mốc vẫn dời (vd bỏ cột tuỳ chọn chưa có ở Postgres hoặc BigQuery, từ 18/10/2026). NULL khi thành công không cảnh báo.';

COMMENT ON TABLE lich_quet IS $$[Lớp] Raw
[Mục đích] Lịch quét tự động của từng dự án (mỗi N giờ, hằng ngày, hằng tuần, chiến dịch) để Mark tự chạy /theodoi đúng mốc, kèm trạng thái lần chạy gần nhất.
[Grain] 1 dòng = 1 lịch quét của 1 dự án
[Khoá] PK: id | Join: du_an → du_an.ma; id → luot_quet.lich_id
[Nguồn] Người quản lý đặt trên dashboard social.hapas.vn (tab Lịch quét); Mark chỉ ghi lan_chay_ke, lan_chay_cuoi, ket_qua_cuoi, so_lan_chay
[Phạm vi] Mọi dự án | Kênh: Không có | Từ khi bật lịch quét tự động (sau 15/10/2026)
[Đã xử lý] Cấu hình đã kiểm trên dashboard (giờ HH:MM, khoảng ≥ 30 phút, ≤ 96 lượt/ngày, kết thúc chiến dịch sau bắt đầu); giờ là giờ Việt Nam UTC+7
[Refresh] Ghi tức thời khi người quản lý sửa (mỗi lần sửa ghi nhat_ky); Mark cập nhật cột chạy mỗi nhịp 30 giây khi lịch tới hạn
[Dùng khi] Biết dự án nào đang quét tự động, mốc chạy kế, lần chạy gần nhất và lý do bỏ qua
[Không dùng khi] Kết quả + chi phí từng lượt → dùng luot_quet (lọc lich_id); lịch Giao việc trên console platform → xem console
[Lưu ý] Lịch console (Giao việc /theodoi) vẫn chạy song song và không nằm ở đây. Chiến dịch đang diễn ra thì lịch thường cùng dự án nhường. Không đẩy lên BigQuery.$$;
COMMENT ON COLUMN lich_quet.id IS 'Mã lịch tự tăng. PK. Join: → luot_quet.lich_id.';
COMMENT ON COLUMN lich_quet.du_an IS 'Dự án được quét theo lịch. FK → du_an.ma.';
COMMENT ON COLUMN lich_quet.ten IS 'Tên lịch hiển thị (≤ 200 ký tự); bỏ trống trên dashboard thì lấy mô tả tự sinh (vd "Mỗi 2 giờ, 07:00–23:00, mọi ngày").';
COMMENT ON COLUMN lich_quet.kieu IS 'Kiểu lịch. Giá trị: moi_n_gio (mỗi N giờ trong khung giờ), hang_ngay (giờ cụ thể mỗi ngày), hang_tuan (ngày trong tuần + giờ), chien_dich (từ lúc → tới lúc, mỗi N phút ≥ 30).';
COMMENT ON COLUMN lich_quet.cau_hinh IS 'Cấu hình mốc theo kiểu (JSON, giờ VN): moi_n_gio {"moi_gio": 1|2|3|4|6|8|12, "tu": "HH:MM", "den": "HH:MM", "thu": [1–7]}; hang_ngay/hang_tuan {"gio": ["HH:MM", …], "thu": [1–7]}; chien_dich {"tu_luc": "YYYY-MM-DDTHH:MM", "den_luc": …, "moi_phut": ≥ 30}. thu: 1 = Thứ 2 … 7 = Chủ nhật; [] = mọi ngày (hang_tuan bắt buộc có).';
COMMENT ON COLUMN lich_quet.bat IS 'TRUE: lịch đang bật, Mark chạy khi tới mốc. FALSE: tắt, Mark bỏ qua (lan_chay_ke NULL).';
COMMENT ON COLUMN lich_quet.quet_moi_nguon IS 'TRUE: mỗi lượt quét MỌI nguồn đang theo dõi, không xét chu kỳ của nguồn (mặc định của chiến dịch). FALSE: nguồn chỉ quét khi tới chu kỳ (nguon.chu_ky_ngay); tìm theo từ khoá và cào bình luận chạy mỗi lượt như /theodoi.';
COMMENT ON COLUMN lich_quet.lan_chay_ke IS 'Mốc chạy kế tiếp (UTC; giờ VN = lan_chay_ke AT TIME ZONE ''Asia/Ho_Chi_Minh''). Dashboard đặt khi lưu; Mark dời sang mốc sau TRƯỚC khi chạy. NULL khi lịch tắt hoặc chiến dịch đã kết thúc.';
COMMENT ON COLUMN lich_quet.lan_chay_cuoi IS 'Lần Mark xử lý lịch gần nhất (đã giao việc hoặc bỏ qua), UTC. NULL khi chưa tới mốc nào.';
COMMENT ON COLUMN lich_quet.ket_qua_cuoi IS 'Kết quả lần xử lý gần nhất (JSON): trang_thai (da_tao, bo_qua, loi, rồi xong/mot_phan/loi/da_huy khi việc chạy xong), ma_loi, ly_do, ma_viec, luot_id, moc, luc, canh_bao (ngày đã gửi cảnh báo theo loại). NULL khi chưa xử lý lần nào.';
COMMENT ON COLUMN lich_quet.so_lan_chay IS 'Số lượt Mark đã giao việc theo lịch này (không tính lượt bỏ qua), lượt, ≥ 0.';
COMMENT ON COLUMN lich_quet.tao_luc IS 'Thời điểm tạo lịch (UTC).';
COMMENT ON COLUMN lich_quet.tao_boi IS 'Email người tạo lịch trên dashboard. Email nội bộ — không đẩy lên BigQuery.';
COMMENT ON COLUMN lich_quet.sua_luc IS 'Thời điểm sửa cấu hình gần nhất (UTC).';
COMMENT ON COLUMN lich_quet.sua_boi IS 'Email người sửa gần nhất. Email nội bộ — không đẩy lên BigQuery.';

COMMENT ON TABLE kiem_do_phu IS $$[Lớp] Raw
[Mục đích] Lịch sử kiểm độ phủ: trong một mẫu bài TikTok lấy bằng đường khác thu thập hằng ngày, bao nhiêu bài nhắc brand đã có trong kho, các bài bị sót và việc Mark đã tự làm để lấp.
[Grain] 1 dòng = 1 lượt kiểm độ phủ của 1 dự án (tối đa 1 lượt mỗi 3,5 ngày)
[Khoá] PK: id | Join: du_an → du_an.ma; luot_id → luot_quet.id; bai_sot[].khoa → bai.khoa (cùng du_an)
[Nguồn] Mark (kiem_do_phu.py) trong lượt /theodoi: hashtag brand/chiến dịch + bài mới nhất của nhà sáng tạo nổi qua TikTok API (scraptik), đối chiếu bảng bai
[Phạm vi] Mọi dự án bật kiểm độ phủ | Kênh: TikTok | Bài đăng trong 30 ngày trước lúc kiểm, từ 17/10/2026
[Đã xử lý] Bài nhắc brand theo luật khớp từ khoá/hashtag của Mark, đã bỏ từ loại trừ và spam; bài đã loại trước (AI, hoặc luật seeding affiliate / thị trường / cổng brand — từ 18/10/2026 tính cả sổ seeding) không vào mẫu số; trùng bài giữa các đường gộp một
[Refresh] Ghi một lần khi lượt kiểm xong (hai lần mỗi tuần mỗi dự án), không sửa lại
[Dùng khi] Theo dõi độ phủ thu thập (do_phu_tl), so với lần trước, xem bài brand bị sót, lý do và Mark đã làm gì
[Không dùng khi] Bài đã thu thập → dùng bai; chi phí cả lượt → dùng luot_quet
[Lưu ý] Mẫu không phải toàn bộ TikTok: độ phủ là ước lượng trên mẫu (xem so_nhac). Bài sót đã được đưa qua phễu lọc + AI ngay trong lượt (bo_sung). Không đẩy lên BigQuery.$$;
COMMENT ON COLUMN kiem_do_phu.id IS 'Mã lượt kiểm tự tăng. PK.';
COMMENT ON COLUMN kiem_do_phu.du_an IS 'Dự án được kiểm. FK → du_an.ma.';
COMMENT ON COLUMN kiem_do_phu.luot_id IS 'Lượt /theodoi chứa lượt kiểm. FK → luot_quet.id. NULL khi lượt đã bị xoá.';
COMMENT ON COLUMN kiem_do_phu.luc IS 'Thời điểm ghi kết quả kiểm (UTC).';
COMMENT ON COLUMN kiem_do_phu.nen_tang IS 'Nền tảng của mẫu. Giá trị: tiktok.';
COMMENT ON COLUMN kiem_do_phu.so_mau IS 'Số bài mẫu đăng trong 30 ngày (sau khi gộp trùng), bài.';
COMMENT ON COLUMN kiem_do_phu.so_nhac IS 'Số bài mẫu nhắc brand, trừ bài đã loại trước (AI hoặc luật, gồm bài seeding affiliate) — mẫu số của độ phủ, bài.';
COMMENT ON COLUMN kiem_do_phu.so_da_co IS 'Số bài nhắc brand đã có trong bai lúc kiểm (trước khi bổ sung), bài.';
COMMENT ON COLUMN kiem_do_phu.so_da_loai IS 'Số bài nhắc brand mà Mark đã xét và loại trước đó — AI loại, hoặc luật seeding affiliate / thị trường / cổng brand (từ 18/10/2026 tính cả sổ seeding) — không tính là sót, bài.';
COMMENT ON COLUMN kiem_do_phu.so_sot IS 'Số bài nhắc brand chưa có trong bai = so_nhac − so_da_co, bài.';
COMMENT ON COLUMN kiem_do_phu.thao_luan_nhac IS 'Tổng thảo luận (1 + bình luận nền tảng báo) của các bài nhắc brand, thảo luận.';
COMMENT ON COLUMN kiem_do_phu.thao_luan_da_co IS 'Tổng thảo luận của các bài nhắc brand đã có trong bai, thảo luận.';
COMMENT ON COLUMN kiem_do_phu.do_phu IS 'Độ phủ theo số bài = 100 × so_da_co / so_nhac, %. NULL khi so_nhac = 0.';
COMMENT ON COLUMN kiem_do_phu.do_phu_tl IS 'Độ phủ theo thảo luận = 100 × thao_luan_da_co / thao_luan_nhac, % — số chính trên dashboard (dưới 80% hiện cảnh báo). NULL khi không có bài nhắc brand.';
COMMENT ON COLUMN kiem_do_phu.bo_sung IS 'Số bài sót đã qua lọc + AI và được ghi mới vào bai ngay trong lượt kiểm, bài.';
COMMENT ON COLUMN kiem_do_phu.so_yeu_cau IS 'Số yêu cầu TikTok API đã gửi (mỗi yêu cầu một run Apify), yêu cầu.';
COMMENT ON COLUMN kiem_do_phu.chi_phi_usd IS 'Chi phí theo sổ = so_yeu_cau × 0,002 USD (giá thật một yêu cầu TikTok API, đo từng run 18/10/2026; dòng trước 18/10/2026 ghi theo 0,0034), trần mặc định 0,20 USD/lần, không VAT; tiền thật đã cộng vào luot_quet.chi_phi_usd của lượt. Không âm.';
COMMENT ON COLUMN kiem_do_phu.mau IS 'Thành phần mẫu (JSON): tag [{ten, trang, bai, loi}], tac_gia [{ten, trang, bai, loi}], theo_duong {hashtag, tac_gia: số đo riêng từng đường}, ngay (30), tran_usd.';
COMMENT ON COLUMN kiem_do_phu.bai_sot IS 'Tối đa 10 bài sót nhiều thảo luận nhất (JSON): khoa, link, tai_khoan, ten, thao_luan, binh_luan, thich, xem, dang_luc, noi_dung (≤ 200 ký tự), duong, tag, ma_ly_do + ly_do (lý do có lẽ bị sót: chi_hashtag, ngoai_cua_so, it_thich, tac_gia_moi, khac), bo_sung (đã ghi vào bai chưa), hanh_dong (câu Mark đã làm cho bài này).';
COMMENT ON COLUMN kiem_do_phu.hanh_dong IS 'Việc Mark tự làm sau lượt kiểm (JSON): de_xuat [{dinh_danh, so_bai, thao_luan, uu_tien}] (đề xuất nguồn ghi vào de_xuat), tag_noi (hashtag lượt nổi đang dùng), tag_them (hashtag vừa thêm), noi {trang: [trước, sau], gio: [trước, sau], ly_do} (nới/lùi lượt nổi). {} khi không có bài sót.';
COMMENT ON TABLE han_muc_apify IS $$[Lớp] Raw
[Mục đích] Ảnh chụp hạn mức gói Apify của tài khoản Mark đang dùng (đã dùng, trần gói, chu kỳ, trần mỗi lượt nền trên console) để trang Ngân sách so dự báo với phần còn thật của gói.
[Grain] 1 dòng = 1 lần Mark đọc GET /v2/users/me/limits
[Khoá] PK: id | Join: luot_id → luot_quet.id
[Nguồn] Mark (theo_doi.ghi_han_muc_goi) đọc Apify /v2/users/me/limits (miễn phí) + trần việc nền trên console platform; dashboard chỉ đọc
[Phạm vi] Tài khoản Apify trong APIFY_TOKEN của Mark, cả tài khoản (mọi việc dùng chung token) | Kênh: Không có | Từ 18/10/2026
[Đã xử lý] USD không VAT; mốc giờ lưu UTC; chu kỳ theo Apify (không theo tháng lịch); đã dùng là số Apify báo lúc đọc
[Refresh] Sau mỗi lượt /theodoi, sau bước chốt lại chi phí (~90 giây sau run cuối) và mỗi 3 giờ ở nhịp lịch quét của Mark
[Dùng khi] Biết gói còn bao nhiêu tới ngày đặt lại, so dự báo với phần còn của gói, so trần nội bộ dự án với trần gói
[Không dùng khi] Tiền thật từng lượt → dùng luot_quet; trần tháng của dự án → dùng du_an
[Lưu ý] Đã dùng tính CẢ tài khoản, gồm việc khác và run thử dùng chung token; Apify ghi phí sự kiện trễ vài chục giây nên dòng ngay sau lượt có thể thiếu chút ít. Đổi token thì chu kỳ và số theo tài khoản mới. Không đẩy lên BigQuery.$$;
COMMENT ON COLUMN han_muc_apify.id IS 'Mã ảnh chụp tự tăng. PK.';
COMMENT ON COLUMN han_muc_apify.luc IS 'Thời điểm Mark đọc hạn mức (UTC).';
COMMENT ON COLUMN han_muc_apify.goi IS 'Mã gói Apify (FREE, STARTER…; APIFY_GOI trong .env của Mark thắng). Chuỗi rỗng khi token không đọc được /users/me.';
COMMENT ON COLUMN han_muc_apify.da_dung_usd IS 'Đã dùng trong chu kỳ hiện tại của CẢ tài khoản (current.monthlyUsageUsd), USD, không VAT, ≥ 0.';
COMMENT ON COLUMN han_muc_apify.tran_usd IS 'Trần chi của gói trong một chu kỳ (limits.maxMonthlyUsageUsd), USD, ≥ 0. Chạm trần thì Apify từ chối mọi run tới ngày đặt lại.';
COMMENT ON COLUMN han_muc_apify.chu_ky_tu IS 'Bắt đầu chu kỳ hạn mức (monthlyUsageCycle.startAt, UTC). NULL khi Apify không trả.';
COMMENT ON COLUMN han_muc_apify.chu_ky_den IS 'Thời điểm đặt lại hạn mức = endAt + 1 giây (UTC; giờ VN = chu_ky_den AT TIME ZONE ''Asia/Ho_Chi_Minh''). NULL khi Apify không trả.';
COMMENT ON COLUMN han_muc_apify.tran_luot_usd IS 'Trần USD mỗi việc nền trên console platform (Năng lực → Quét mạng xã hội) lúc đọc — một lượt /theodoi không tiêu quá số này. NULL khi không đọc được.';
COMMENT ON COLUMN han_muc_apify.du_tru_usd IS 'Phần Mark chừa lại không dùng cho việc nền (quet_lon._DU_TRU_THANG), USD; phần dùng được = tran_usd − da_dung_usd − du_tru_usd.';
COMMENT ON COLUMN han_muc_apify.luot_id IS 'Lượt /theodoi vừa xong khi ghi (nguon_ghi luot, chot_lai). FK → luot_quet.id. NULL khi ghi ở nhịp định kỳ.';
COMMENT ON COLUMN han_muc_apify.nguon_ghi IS 'Lúc ghi. Giá trị: luot (đóng lượt), chot_lai (chốt lại chi phí ~90 giây sau run cuối), nhip (nhịp lịch quét mỗi 3 giờ).';

RESET ROLE;

-- Quyền của bot: đọc cấu hình, ghi kết quả. Không sửa dự án, không thêm/xoá nguồn.
GRANT SELECT ON du_an, nguon TO mark;
GRANT UPDATE (quet_cuoi, loi_cuoi, loi_luc) ON nguon TO mark;
GRANT SELECT, INSERT, UPDATE ON bai, chi_so_ngay, luot_quet, binh_luan TO mark;
GRANT SELECT, INSERT ON de_xuat TO mark;
GRANT UPDATE (ten, link, ly_do, so_bai, thao_luan) ON de_xuat TO mark;
GRANT USAGE ON SEQUENCE luot_quet_id_seq, de_xuat_id_seq TO mark;
-- Kiểm độ phủ (17/10/2026): Mark chỉ thêm dòng + đọc lại; không sửa/xoá lịch sử.
GRANT SELECT, INSERT ON kiem_do_phu TO mark;
GRANT USAGE ON SEQUENCE kiem_do_phu_id_seq TO mark;
-- Hạn mức gói Apify (18/10/2026): Mark chỉ thêm ảnh chụp + đọc lại; không sửa/xoá.
GRANT SELECT, INSERT ON han_muc_apify TO mark;
GRANT USAGE ON SEQUENCE han_muc_apify_id_seq TO mark;
-- Lịch quét tự động (15/10/2026): Mark đọc ĐÚNG các cột nó dùng (`lang_nghe_db._COT_LICH`; không
-- đọc email tao_boi/sua_boi), chỉ ghi cột trạng thái chạy (FOR UPDATE cần quyền UPDATE trên ít
-- nhất một cột — đủ ở đây). Không tạo/xoá/sửa cấu hình lịch. REVOKE trước: bản nháp cũ cấp SELECT
-- cả bảng; thu quyền bảng là thu luôn quyền cột, rồi cấp lại theo cột.
REVOKE SELECT ON lich_quet FROM mark;
GRANT SELECT (id, du_an, ten, kieu, cau_hinh, bat, quet_moi_nguon, lan_chay_ke, lan_chay_cuoi,
              ket_qua_cuoi, so_lan_chay) ON lich_quet TO mark;
GRANT UPDATE (lan_chay_ke, lan_chay_cuoi, ket_qua_cuoi, so_lan_chay) ON lich_quet TO mark;
-- Hỏi đáp số liệu dashboard trong chat (17/10/2026, `hoi_dashboard_tool.py`): Mark chỉ trả số cho
-- người có tên trong `nguoi_xem`, nên đọc ĐÚNG hai cột email + vai_tro (không them_boi/them_luc).
-- Các bảng còn lại tool đọc (du_an, nguon, bai, binh_luan, luot_quet, lich_quet theo cột) đã có
-- quyền ở trên. Cột mới mà `dashboard.kho.vai_tro` đọc thêm thì cấp thêm ở đây (thiếu quyền thì
-- tool ĐÓNG — không trả số cho ai). Chạy lại nhiều lần không sao (GRANT trùng không lỗi).
GRANT SELECT (email, vai_tro) ON nguoi_xem TO mark;

-- Quyền của dashboard: quản lý cấu hình + người xem, đọc mọi thứ, ghi nhật ký và mốc đồng bộ.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lang_nghe_web;
GRANT INSERT, UPDATE, DELETE ON du_an, nguon, nguoi_xem TO lang_nghe_web;
GRANT UPDATE (trang_thai, xu_ly_boi, xu_ly_luc) ON de_xuat TO lang_nghe_web;
GRANT INSERT ON nhat_ky TO lang_nghe_web;
GRANT INSERT, UPDATE ON dong_bo_bq TO lang_nghe_web;
GRANT USAGE ON SEQUENCE nguon_id_seq, nhat_ky_id_seq TO lang_nghe_web;
GRANT INSERT, UPDATE, DELETE ON lich_quet TO lang_nghe_web;
GRANT USAGE ON SEQUENCE lich_quet_id_seq TO lang_nghe_web;
