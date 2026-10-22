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
--                    và cột trạng thái chạy của lịch; đọc email + quyền theo bên của người xem
--                    (hỏi đáp số liệu dashboard trong chat chỉ cho người xem, chỉ dự án bên họ).
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

-- Bên (đơn vị) sở hữu dự án (19/10/2026, chủ dự án: phân quyền theo bên — HAPAS, MATEMADE…). Mỗi dự
-- án thuộc một bên; người xem có quyền theo từng bên (bảng `quyen`). Tạo TRƯỚC du_an (khoá ngoại).
CREATE TABLE IF NOT EXISTS don_vi (
  ma              TEXT PRIMARY KEY CHECK (ma ~ '^[a-z0-9][a-z0-9_-]{1,39}$'),
  ten             TEXT NOT NULL CHECK (length(ten) BETWEEN 1 AND 200),
  tao_luc         TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO don_vi (ma, ten) VALUES ('hapas', 'HAPAS'), ('matemade', 'MATEMADE')
  ON CONFLICT (ma) DO NOTHING;

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
  hashtag         TEXT[] NOT NULL DEFAULT '{}',   -- hashtag riêng (IG + feed TikTok), 18/10/2026
  don_vi          TEXT NOT NULL REFERENCES don_vi(ma) ON UPDATE CASCADE   -- bên, 19/10/2026
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
-- 19/10/2026: bên của dự án. DB đã có dự án: thêm cột cho phép NULL, gán bên (mã có "matemade" →
-- matemade, còn lại → hapas; chỉ dòng còn NULL nên chạy lại không đè bên đã đổi trên dashboard),
-- rồi mới NOT NULL — chỉ ALTER khi cột còn cho NULL (chạy lại không xin khoá bảng vô ích).
ALTER TABLE du_an ADD COLUMN IF NOT EXISTS don_vi TEXT REFERENCES don_vi(ma) ON UPDATE CASCADE;
UPDATE du_an SET don_vi = CASE WHEN ma LIKE '%matemade%' THEN 'matemade' ELSE 'hapas' END
  WHERE don_vi IS NULL;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
             AND table_name = 'du_an' AND column_name = 'don_vi' AND is_nullable = 'YES') THEN
    ALTER TABLE du_an ALTER COLUMN don_vi SET NOT NULL;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS du_an_don_vi ON du_an (don_vi);

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
  gio_hang        BOOLEAN,
  la_quang_cao    BOOLEAN,
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
-- ── KOC gắn giỏ / KOC branding (20/10/2026, task Lark t284905, chủ dự án duyệt PA1) ──
-- Marketing: "đang bị lẫn KOC branding và KOC aff → tiêu chí: KOC branding không gắn giỏ hàng ><
-- KOC aff có gắn giỏ". Cờ giỏ TikTok Shop đã có lúc cào (`tiktok_api._gio_hang`: anchor có
-- "shop"; `hasTikTokShopProduct` của clockworks) nhưng trước đây mất khi ghi kho. Hai cột NULL
-- được (chỉ đổi danh mục, không ghi lại bảng). NULL = chưa rõ (chỉ thấy ở feed hashtag — feed không
-- bao giờ trả anchor shop — hoặc nguồn không báo); tìm kiếm / hồ sơ không có anchor shop = FALSE. Ghi: TRUE dính (bản đọc báo giỏ rồi thì bản đọc sau không hạ — feed hashtag hay thiếu
-- anchor, đo raw 18/10: 21 video feed báo không giỏ mà tìm kiếm / hồ sơ báo có giỏ), FALSE chỉ
-- điền chỗ NULL, NULL không đè gì (`lang_nghe_db._GOP_CO`). Quyền: GRANT cả bảng bai cho mark ở
-- cuối file đã đủ (không có GRANT theo cột). Bài cũ: scripts/lang_nghe_nap_gio_hang.py.
ALTER TABLE bai ADD COLUMN IF NOT EXISTS gio_hang BOOLEAN;
ALTER TABLE bai ADD COLUMN IF NOT EXISTS la_quang_cao BOOLEAN;

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

-- Ai được vào dashboard. Từ 19/10/2026 quyền theo BÊN: cờ `la_quan_tri` (toàn hệ thống) + bảng
-- `quyen` (vai trò từng bên). `vai_tro` là cột CŨ, chỉ còn để tương thích (Mark bản cũ đọc): dashboard
-- giữ nó = vai trò gộp (quan_ly khi là quản trị viên hoặc quản lý một bên, còn lại xem), không dùng
-- để quyết định quyền nữa.
CREATE TABLE IF NOT EXISTS nguoi_xem (
  email           TEXT PRIMARY KEY CHECK (email = lower(email) AND email LIKE '%@%'),
  vai_tro         TEXT NOT NULL CHECK (vai_tro IN ('xem', 'quan_ly')),
  them_boi        TEXT,
  them_luc        TIMESTAMPTZ NOT NULL DEFAULT now(),
  la_quan_tri     BOOLEAN NOT NULL DEFAULT FALSE
);
ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS la_quan_tri BOOLEAN NOT NULL DEFAULT FALSE;
-- Danh bạ Lark (17/10/2026, chủ dự án: "thêm title trong công ty… biết email có active thật
-- không"): bản đệm đọc từ Lark contact API bằng app của dashboard (dashboard/danh_ba.py), làm
-- mới ≤ 12 giờ/lần khi mở trang Quản trị và ngay khi thêm email. `dang_nhap_cuoi` ghi mỗi lượt
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

-- Quyền theo bên (19/10/2026): một người nhiều bên, mỗi bên một vai trò. Xoá người xem thì xoá luôn
-- quyền. Người không phải quản trị viên và không còn dòng nào ở đây thì không đăng nhập được
-- (dashboard xoá luôn dòng nguoi_xem của họ).
CREATE TABLE IF NOT EXISTS quyen (
  email           TEXT NOT NULL REFERENCES nguoi_xem(email) ON DELETE CASCADE ON UPDATE CASCADE,
  don_vi          TEXT NOT NULL REFERENCES don_vi(ma) ON UPDATE CASCADE,
  vai_tro         TEXT NOT NULL CHECK (vai_tro IN ('xem', 'quan_ly')),
  them_boi        TEXT,
  them_luc        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (email, don_vi)
);
CREATE INDEX IF NOT EXISTS quyen_don_vi ON quyen (don_vi);

-- Chuyển quyền cũ sang quyền theo bên (chủ dự án chốt 19/10/2026). Chạy lại không đè thay đổi
-- làm sau đó trên dashboard:
--   1. Quản trị viên đầu tiên: thamnt + thienlq — CHỈ khi chưa có quản trị viên nào (dashboard luôn
--      giữ ≥ 1 quản trị viên, nên từ lần thứ hai câu này không làm gì).
--   2. nganlt: Quản lý HAPAS; itsupport: Chỉ xem HAPAS — chỉ khi người đó còn tên và CHƯA có dòng
--      quyền nào (bị xoá rồi thì không thêm lại; đã đổi vai trò thì không đè).
--   3. Mọi người còn lại chưa có dòng quyền nào và không phải quản trị viên: chép vai_tro cũ thành
--      quyền ở bên HAPAS (người thêm bằng bản dashboard / lệnh cũ trước khi lên bản mới). Dashboard
--      không để lại người "có tên mà không quyền", nên câu này không cấp lại quyền đã bỏ.
INSERT INTO nguoi_xem (email, vai_tro, them_boi, la_quan_tri)
  SELECT e, 'quan_ly', 'chuyen_quyen_ben', TRUE
  FROM unnest(ARRAY['thamnt@hapas.vn', 'thienlq@hapas.vn']) AS t(e)
  WHERE NOT EXISTS (SELECT 1 FROM nguoi_xem WHERE la_quan_tri)
  ON CONFLICT (email) DO UPDATE SET la_quan_tri = TRUE, vai_tro = 'quan_ly';
INSERT INTO quyen (email, don_vi, vai_tro, them_boi)
  SELECT n.email, 'hapas', t.v, 'chuyen_quyen_ben'
  FROM (VALUES ('nganlt@hapas.vn', 'quan_ly'), ('itsupport@hapas.vn', 'xem')) AS t(e, v)
  JOIN nguoi_xem n ON n.email = t.e
  WHERE NOT EXISTS (SELECT 1 FROM quyen q WHERE q.email = n.email)
  ON CONFLICT (email, don_vi) DO NOTHING;
INSERT INTO quyen (email, don_vi, vai_tro, them_boi)
  SELECT n.email, 'hapas', n.vai_tro, 'chuyen_quyen_ben' FROM nguoi_xem n
  WHERE NOT n.la_quan_tri AND NOT EXISTS (SELECT 1 FROM quyen q WHERE q.email = n.email)
  ON CONFLICT (email, don_vi) DO NOTHING;
-- Cột cũ vai_tro = vai trò gộp (như dashboard `kho._vai_cu`) — Mark bản cũ đọc đúng.
UPDATE nguoi_xem n SET vai_tro = 'quan_ly' WHERE n.vai_tro <> 'quan_ly' AND (n.la_quan_tri OR
  EXISTS (SELECT 1 FROM quyen q WHERE q.email = n.email AND q.vai_tro = 'quan_ly'));
UPDATE nguoi_xem n SET vai_tro = 'xem' WHERE n.vai_tro <> 'xem' AND NOT n.la_quan_tri AND
  NOT EXISTS (SELECT 1 FROM quyen q WHERE q.email = n.email AND q.vai_tro = 'quan_ly');

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

-- ───────────── TikTok Ads (19/10/2026, chủ dự án chốt) ─────────────
-- Dashboard nối TikTok for Business (MCP server, OAuth của quản trị viên) và đồng bộ số quảng cáo
-- mỗi ngày 06:30 giờ VN (`dashboard/tiktok_ads.py`, bộ hẹn giờ systemd). Token nằm ở
-- `ket_noi_ngoai` dưới dạng MÃ HOÁ (khoá TIKTOK_KHOA_MA_HOA chỉ có trong /opt/lang-nghe/.env); role
-- mark chỉ đọc các cột không bí mật (cấp theo cột ở cuối file). Mỗi tài khoản quảng cáo thuộc một
-- bên (`tk_quang_cao.don_vi`), chỉ số tiền chỉ quản trị viên + quản lý của bên thấy (lọc ở app).
-- Một dòng mỗi nhà cung cấp kết nối ngoài ('tiktok_ads'; 'meta_ads' từ 20/10/2026).
CREATE TABLE IF NOT EXISTS ket_noi_ngoai (
  nha_cung_cap    TEXT PRIMARY KEY,
  loai            TEXT NOT NULL DEFAULT 'mcp_oauth' CHECK (loai IN ('mcp_oauth', 'api_token')),
  client_id       TEXT,
  redirect_uri    TEXT,
  access_token_enc TEXT,
  refresh_token_enc TEXT,
  access_het_luc  TIMESTAMPTZ,
  refresh_het_luc TIMESTAMPTZ,
  nguoi_cap       TEXT,
  cap_luc         TIMESTAMPTZ,
  lam_moi_luc     TIMESTAMPTZ,
  goi_ok_luc      TIMESTAMPTZ,
  so_tk_thay      INT CHECK (so_tk_thay >= 0),
  so_tk_truoc     INT CHECK (so_tk_truoc >= 0),
  loi_cuoi        TEXT,
  loi_luc         TIMESTAMPTZ,
  trang_thai      TEXT NOT NULL DEFAULT 'chua_ket_noi'
                  CHECK (trang_thai IN ('chua_ket_noi', 'hoat_dong', 'het_han', 'loi', 'da_ngat')),
  dong_bo_bat_dau TIMESTAMPTZ,
  dong_bo_xong    TIMESTAMPTZ,
  dong_bo_ok_luc  TIMESTAMPTZ,
  dong_bo_so_dong INT CHECK (dong_bo_so_dong >= 0),
  dong_bo_loi     TEXT,
  so_den_ngay     DATE,
  yeu_cau_dong_bo_luc TIMESTAMPTZ,
  yeu_cau_boi     TEXT,
  cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 1 dòng = 1 tài khoản quảng cáo (TikTok advertiser / Meta act_…) mà lần kết nối thấy.
CREATE TABLE IF NOT EXISTS tk_quang_cao (
  advertiser_id   TEXT PRIMARY KEY,
  ten             TEXT NOT NULL DEFAULT '',
  don_vi          TEXT REFERENCES don_vi(ma) ON UPDATE CASCADE,
  gan_tay         BOOLEAN NOT NULL DEFAULT FALSE,
  gan_luc         TIMESTAMPTZ,
  tien_te         TEXT NOT NULL DEFAULT 'VND',
  mui_gio         TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
  dang_dong_bo    BOOLEAN NOT NULL DEFAULT TRUE,
  con_quyen       BOOLEAN NOT NULL DEFAULT TRUE,
  thay_lan_dau    TIMESTAMPTZ NOT NULL DEFAULT now(),
  thay_cuoi       TIMESTAMPTZ NOT NULL DEFAULT now(),
  nap_lui_tu      DATE,
  nap_lui_xong_luc TIMESTAMPTZ,
  khan_gia_luc    TIMESTAMPTZ,
  cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
  nen_tang        TEXT NOT NULL DEFAULT 'tiktok',
  duyet           BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS tk_quang_cao_don_vi ON tk_quang_cao (don_vi);

-- Số theo NGÀY (múi giờ tài khoản) của cả tài khoản. Cột số kiểu riêng = chỉ số hay dùng; MỌI chỉ
-- số TikTok trả (100 tên hợp lệ) nằm trong chi_so (JSON).
CREATE TABLE IF NOT EXISTS qc_tk_ngay (
  advertiser_id   TEXT NOT NULL REFERENCES tk_quang_cao(advertiser_id),
  ngay            DATE NOT NULL,
  chi             NUMERIC(16,2),
  hien_thi        BIGINT,
  reach           BIGINT,
  click           BIGINT,
  ket_qua         BIGINT,
  chuyen_doi      BIGINT,
  view_video      BIGINT,
  view_hai_giay         BIGINT,
  view_sau_giay         BIGINT,
  view_het        BIGINT,
  engaged_view    BIGINT,
  thich           BIGINT,
  binh_luan       BIGINT,
  chia_se         BIGINT,
  follow          BIGINT,
  vao_ho_so       BIGINT,
  mua_shop        BIGINT,
  gia_tri_mua_shop NUMERIC(16,2),
  chi_so          JSONB NOT NULL DEFAULT '{}'::jsonb,
  cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (advertiser_id, ngay)
);
CREATE INDEX IF NOT EXISTS qc_tk_ngay_ngay ON qc_tk_ngay (ngay);
CREATE INDEX IF NOT EXISTS qc_tk_ngay_cap_nhat ON qc_tk_ngay (cap_nhat_luc);

-- Số theo ngày của từng campaign CÓ phân phối (impressions hoặc chi > 0 trong ngày).
CREATE TABLE IF NOT EXISTS qc_campaign_ngay (
  advertiser_id   TEXT NOT NULL REFERENCES tk_quang_cao(advertiser_id),
  campaign_id     TEXT NOT NULL,
  ngay            DATE NOT NULL,
  ten             TEXT NOT NULL DEFAULT '',
  muc_tieu        TEXT,
  chi             NUMERIC(16,2),
  hien_thi        BIGINT,
  reach           BIGINT,
  click           BIGINT,
  ket_qua         BIGINT,
  chuyen_doi      BIGINT,
  view_video      BIGINT,
  view_hai_giay         BIGINT,
  view_sau_giay         BIGINT,
  view_het        BIGINT,
  engaged_view    BIGINT,
  thich           BIGINT,
  binh_luan       BIGINT,
  chia_se         BIGINT,
  follow          BIGINT,
  vao_ho_so       BIGINT,
  mua_shop        BIGINT,
  gia_tri_mua_shop NUMERIC(16,2),
  chi_so          JSONB NOT NULL DEFAULT '{}'::jsonb,
  cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (campaign_id, ngay)
);
CREATE INDEX IF NOT EXISTS qc_campaign_ngay_tk ON qc_campaign_ngay (advertiser_id, ngay);
CREATE INDEX IF NOT EXISTS qc_campaign_ngay_cap_nhat ON qc_campaign_ngay (cap_nhat_luc);

-- Số theo ngày của từng quảng cáo (ad) CÓ phân phối — chỉ ad đang chạy, không đọc hàng chục nghìn
-- ad chưa xoá mà không chạy.
CREATE TABLE IF NOT EXISTS qc_ad_ngay (
  advertiser_id   TEXT NOT NULL REFERENCES tk_quang_cao(advertiser_id),
  campaign_id     TEXT,
  adgroup_id      TEXT,
  ad_id           TEXT NOT NULL,
  ngay            DATE NOT NULL,
  ten_ad          TEXT NOT NULL DEFAULT '',
  noi_dung        TEXT NOT NULL DEFAULT '',
  ten_campaign    TEXT NOT NULL DEFAULT '',
  ten_nhom        TEXT NOT NULL DEFAULT '',
  chi             NUMERIC(16,2),
  hien_thi        BIGINT,
  reach           BIGINT,
  click           BIGINT,
  ket_qua         BIGINT,
  chuyen_doi      BIGINT,
  view_video      BIGINT,
  view_hai_giay         BIGINT,
  view_sau_giay         BIGINT,
  view_het        BIGINT,
  engaged_view    BIGINT,
  thich           BIGINT,
  binh_luan       BIGINT,
  chia_se         BIGINT,
  follow          BIGINT,
  vao_ho_so       BIGINT,
  mua_shop        BIGINT,
  gia_tri_mua_shop NUMERIC(16,2),
  chi_so          JSONB NOT NULL DEFAULT '{}'::jsonb,
  cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ad_id, ngay)
);
CREATE INDEX IF NOT EXISTS qc_ad_ngay_tk ON qc_ad_ngay (advertiser_id, ngay);
CREATE INDEX IF NOT EXISTS qc_ad_ngay_cap_nhat ON qc_ad_ngay (cap_nhat_luc);

-- Khán giả (báo cáo AUDIENCE) của tài khoản trong một cửa sổ 30 ngày, đọc mỗi tuần một lần.
CREATE TABLE IF NOT EXISTS qc_khan_gia (
  advertiser_id   TEXT NOT NULL REFERENCES tk_quang_cao(advertiser_id),
  tu              DATE NOT NULL,
  den             DATE NOT NULL CHECK (den >= tu),
  chieu           TEXT NOT NULL,
  gia_tri         TEXT NOT NULL,
  chi             NUMERIC(16,2),
  hien_thi        BIGINT,
  reach           BIGINT,
  click           BIGINT,
  ket_qua         BIGINT,
  chuyen_doi      BIGINT,
  view_video      BIGINT,
  view_hai_giay         BIGINT,
  view_sau_giay         BIGINT,
  view_het        BIGINT,
  engaged_view    BIGINT,
  thich           BIGINT,
  binh_luan       BIGINT,
  chia_se         BIGINT,
  follow          BIGINT,
  vao_ho_so       BIGINT,
  mua_shop        BIGINT,
  gia_tri_mua_shop NUMERIC(16,2),
  chi_so          JSONB NOT NULL DEFAULT '{}'::jsonb,
  cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (advertiser_id, tu, den, chieu, gia_tri)
);
CREATE INDEX IF NOT EXISTS qc_khan_gia_moi ON qc_khan_gia (advertiser_id, den DESC);
CREATE INDEX IF NOT EXISTS qc_khan_gia_cap_nhat ON qc_khan_gia (cap_nhat_luc);

-- ───────────── Meta Ads (20/10/2026, chủ dự án chốt) ─────────────
-- Meta (Facebook / Instagram) Ads đi CHUNG đường ống TikTok (`dashboard/meta_ads.py`, bộ hẹn giờ
-- meta-ads-dong-bo 06:45 giờ VN): một dòng ket_noi_ngoai 'meta_ads' (token người dùng hệ thống CHỈ
-- ĐỌC, mã hoá cùng khoá TIKTOK_KHOA_MA_HOA, AAD riêng), tài khoản act_… trong tk_quang_cao
-- (nen_tang = 'meta', chỉ tài khoản `duyet` mới được đọc số), số trong cùng 4 bảng qc_*. Khoá chính
-- qc_* giữ nguyên (mã campaign/ad hai nền tảng khác dạng; upsert không bao giờ đè dòng của tài
-- khoản khác — kho_qc.sql_upsert). Chạy lại nhiều lần không sao; ALTER chỉ đổi danh mục (thêm cột
-- DEFAULT hằng) hoặc quét bảng nhỏ (CHECK) — dưới lock_timeout.
-- Đổi ràng buộc CHECK NGUYÊN TỬ (soát 20/10/2026): mỗi khối DO là MỘT giao dịch — DROP + ADD cùng
-- thành công hoặc cùng huỷ (lock_timeout giữa chừng không bao giờ để bảng mất CHECK); ràng buộc đã
-- đúng (pg_get_constraintdef) thì bỏ qua — chạy lại schema.sql là không làm gì, không xin khoá.
DO $mt$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'ket_noi_ngoai'::regclass
                 AND conname = 'ket_noi_ngoai_nha_cung_cap_check'
                 AND pg_get_constraintdef(oid) LIKE '%meta_ads%') THEN
    ALTER TABLE ket_noi_ngoai DROP CONSTRAINT IF EXISTS ket_noi_ngoai_nha_cung_cap_check;
    ALTER TABLE ket_noi_ngoai ADD CONSTRAINT ket_noi_ngoai_nha_cung_cap_check
      CHECK (nha_cung_cap IN ('tiktok_ads', 'meta_ads'));
  END IF;
END $mt$;
ALTER TABLE ket_noi_ngoai ADD COLUMN IF NOT EXISTS chu_token TEXT;
ALTER TABLE ket_noi_ngoai ADD COLUMN IF NOT EXISTS quyen_token TEXT[];
-- Đồng bộ bấm tay cho mọi người có quyền (20/10/2026): loại yêu cầu / lượt + mốc giãn 15 phút.
ALTER TABLE ket_noi_ngoai ADD COLUMN IF NOT EXISTS yeu_cau_kieu TEXT;
ALTER TABLE ket_noi_ngoai ADD COLUMN IF NOT EXISTS dong_bo_kieu TEXT;
ALTER TABLE ket_noi_ngoai ADD COLUMN IF NOT EXISTS nhanh_xong_luc TIMESTAMPTZ;
DO $mt$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'ket_noi_ngoai'::regclass
                 AND conname = 'ket_noi_ngoai_kieu_check'
                 AND pg_get_constraintdef(oid) LIKE '%dong_bo_kieu%') THEN
    ALTER TABLE ket_noi_ngoai DROP CONSTRAINT IF EXISTS ket_noi_ngoai_kieu_check;
    ALTER TABLE ket_noi_ngoai ADD CONSTRAINT ket_noi_ngoai_kieu_check
      CHECK ((yeu_cau_kieu IS NULL OR yeu_cau_kieu IN ('day_du', 'nhanh'))
             AND (dong_bo_kieu IS NULL OR dong_bo_kieu IN ('day_du', 'nhanh')));
  END IF;
END $mt$;
ALTER TABLE tk_quang_cao ADD COLUMN IF NOT EXISTS nen_tang TEXT NOT NULL DEFAULT 'tiktok';
ALTER TABLE tk_quang_cao ADD COLUMN IF NOT EXISTS duyet BOOLEAN NOT NULL DEFAULT TRUE;
DO $mt$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'tk_quang_cao'::regclass
                 AND conname = 'tk_quang_cao_ma_check'
                 AND pg_get_constraintdef(oid) LIKE '%act_%') THEN
    -- CHECK cũ (chỉ chuỗi số) bỏ CÙNG giao dịch với CHECK mới.
    ALTER TABLE tk_quang_cao DROP CONSTRAINT IF EXISTS tk_quang_cao_advertiser_id_check;
    ALTER TABLE tk_quang_cao DROP CONSTRAINT IF EXISTS tk_quang_cao_ma_check;
    ALTER TABLE tk_quang_cao ADD CONSTRAINT tk_quang_cao_ma_check CHECK (
      (nen_tang = 'tiktok' AND advertiser_id ~ '^[0-9]{1,30}$')
      OR (nen_tang = 'meta' AND advertiser_id ~ '^act_[0-9]{1,30}$'));
  END IF;
END $mt$;
CREATE INDEX IF NOT EXISTS tk_quang_cao_nen_tang ON tk_quang_cao (nen_tang);
DO $mt$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'qc_khan_gia'::regclass
                 AND conname = 'qc_khan_gia_chieu_check'
                 AND pg_get_constraintdef(oid) LIKE '%platform_position%') THEN
    ALTER TABLE qc_khan_gia DROP CONSTRAINT IF EXISTS qc_khan_gia_chieu_check;
    ALTER TABLE qc_khan_gia ADD CONSTRAINT qc_khan_gia_chieu_check CHECK (chieu IN ('age', 'gender',
      'province_id', 'region', 'platform', 'publisher_platform', 'platform_position'));
  END IF;
END $mt$;

-- ───────────── Kênh đăng của quảng cáo (22/10/2026, chủ dự án chốt) ─────────────
-- Trang Quảng cáo tách mỗi tài khoản theo "kênh đăng" — danh tính quảng cáo chạy dưới tên: TikTok
-- identity (tài khoản chính chủ, KOC / Spark Ads), Meta Trang Facebook (+ Instagram đi kèm). Bộ đồng bộ
-- (tiktok_ads.py ad_get qua tool_execute dạng cố định + identity_get; meta_ads.py GET act_<id>/ads)
-- đọc kênh MỘT lần cho mỗi ad có phân phối (kênh của ad không đổi). Bảng mới: CREATE nhanh, không khoá
-- bảng nào khác; chạy lại không sao.
CREATE TABLE IF NOT EXISTS qc_ad_kenh (
  advertiser_id   TEXT NOT NULL REFERENCES tk_quang_cao(advertiser_id),
  ad_id           TEXT NOT NULL,
  nen_tang        TEXT NOT NULL CHECK (nen_tang IN ('tiktok', 'meta')),
  kenh_id         TEXT,
  loai            TEXT NOT NULL,
  kenh_phu_id     TEXT,
  bai_id          TEXT,
  cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (advertiser_id, ad_id)
);
CREATE INDEX IF NOT EXISTS qc_ad_kenh_kenh ON qc_ad_kenh (nen_tang, kenh_id);
CREATE INDEX IF NOT EXISTS qc_ad_kenh_cap_nhat ON qc_ad_kenh (cap_nhat_luc);
CREATE TABLE IF NOT EXISTS qc_kenh (
  nen_tang        TEXT NOT NULL CHECK (nen_tang IN ('tiktok', 'meta')),
  kenh_id         TEXT NOT NULL,
  loai            TEXT,
  ten             TEXT,
  username        TEXT,
  cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (nen_tang, kenh_id)
);
CREATE INDEX IF NOT EXISTS qc_kenh_cap_nhat ON qc_kenh (cap_nhat_luc);

-- ───────────── Số tức thì của Mark (20/10/2026, chủ dự án chốt) ─────────────
-- "mark có quyền cao nhất có thể cào real time theo yêu cầu": một dòng = một yêu cầu Mark gửi khi
-- người hỏi cần số MỚI hơn số trong kho (dashboard/kho_tuc_thi.py). Quảng cáo: Mark CHỈ thêm dòng
-- chờ, bộ nghe tiktok-ads-nghe / meta-ads-nghe (user lang_nghe_web, có khoá giải mã) chạy lượt
-- đọc — Mark không bao giờ cầm token. Bài / kênh / quét: Mark tự chạy (Apify, trần nhỏ), dòng
-- dùng đếm trần mỗi người / mỗi bên mỗi ngày và giữ chi phí thật. Bảng mới: CREATE nhanh, không
-- khoá bảng nào khác.
CREATE TABLE IF NOT EXISTS yeu_cau_tuc_thi (
  id              BIGSERIAL PRIMARY KEY,
  loai            TEXT NOT NULL CHECK (loai IN ('quang_cao', 'bai', 'kenh', 'quet')),
  nguoi_hoi       TEXT NOT NULL,
  ben             TEXT,
  nha_cung_cap    TEXT CHECK (nha_cung_cap IS NULL OR nha_cung_cap IN ('tiktok_ads', 'meta_ads')),
  tai_khoan       TEXT[] NOT NULL DEFAULT '{}',
  tu              DATE,
  den             DATE,
  du_an           TEXT,
  so_muc          INT NOT NULL DEFAULT 0 CHECK (so_muc >= 0),
  chi_tiet        JSONB NOT NULL DEFAULT '{}'::jsonb,
  trang_thai      TEXT NOT NULL DEFAULT 'cho'
                  CHECK (trang_thai IN ('cho', 'dang_chay', 'xong', 'loi', 'bo_qua', 'tu_choi')),
  uoc_usd         NUMERIC(10,4),
  chi_phi_usd     NUMERIC(10,4),
  so_dong         INT,
  so_tk_ok        INT CHECK (so_tk_ok >= 0),
  loi             TEXT,
  tao_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
  bat_dau_luc     TIMESTAMPTZ,
  xong_luc        TIMESTAMPTZ,
  CHECK (den IS NULL OR tu IS NULL OR den >= tu)
);
CREATE INDEX IF NOT EXISTS yeu_cau_tuc_thi_loai_luc ON yeu_cau_tuc_thi (loai, tao_luc DESC);
CREATE INDEX IF NOT EXISTS yeu_cau_tuc_thi_cho ON yeu_cau_tuc_thi (nha_cung_cap, trang_thai)
  WHERE trang_thai IN ('cho', 'dang_chay');
-- Soát 20/10/2026 M5 (quyền tối thiểu của role mark):
--   • TRƯỚC khi thêm: trạng thái do CSDL quyết, Mark không chọn được — có `loi` (Mark từ chối vì
--     trần / quyền / ngân sách) → tu_choi; quảng cáo → cho (bộ nghe chạy); bài / kênh / quét →
--     dang_chay (Mark tự chạy rồi kết thúc). Cột kết quả (so_dong, so_tk_ok, chi_phi_usd, mốc giờ)
--     luôn do CSDL đặt.
--   • SAU khi thêm: một dòng nhat_ky "mark_real_time" (ai = email người hỏi) + pg_notify cho dòng
--     quảng cáo chờ. Hàm SECURITY DEFINER (chủ lang_nghe_chu, search_path cố định): role mark KHÔNG
--     có quyền ghi nhat_ky. Thông báo chỉ gửi khi giao dịch COMMIT.
-- CREATE OR REPLACE + khối DO kiểm pg_trigger: chạy lại không tạo trùng, không xin khoá khi đã có.
CREATE OR REPLACE FUNCTION chuan_yeu_cau_tuc_thi() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  NEW.trang_thai := CASE WHEN NEW.loi IS NOT NULL THEN 'tu_choi'
                         WHEN NEW.loai = 'quang_cao' THEN 'cho' ELSE 'dang_chay' END;
  NEW.tao_luc := now();
  NEW.bat_dau_luc := CASE WHEN NEW.trang_thai = 'dang_chay' THEN now() END;
  NEW.xong_luc := CASE WHEN NEW.trang_thai = 'tu_choi' THEN now() END;
  NEW.so_dong := NULL;
  NEW.so_tk_ok := NULL;
  NEW.chi_phi_usd := NULL;
  RETURN NEW;
END $fn$;
CREATE OR REPLACE FUNCTION bao_yeu_cau_tuc_thi() RETURNS trigger LANGUAGE plpgsql
  SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
  INSERT INTO public.nhat_ky (ai, hanh_dong, doi_tuong, chi_tiet)
  VALUES (NEW.nguoi_hoi, 'mark_real_time', 'tuc_thi:' || NEW.id,
          jsonb_build_object('loai', NEW.loai, 'ben', NEW.ben, 'nha_cung_cap', NEW.nha_cung_cap,
                             'so_tai_khoan', cardinality(NEW.tai_khoan), 'tu', NEW.tu,
                             'den', NEW.den, 'du_an', NEW.du_an, 'so_muc', NEW.so_muc,
                             'trang_thai', NEW.trang_thai, 'ly_do', left(NEW.loi, 300)));
  IF NEW.loai = 'quang_cao' AND NEW.trang_thai = 'cho' THEN
    PERFORM pg_notify('qc_tuc_thi', COALESCE(NEW.nha_cung_cap, ''));
  END IF;
  RETURN NULL;
END $fn$;
REVOKE ALL ON FUNCTION bao_yeu_cau_tuc_thi() FROM PUBLIC;
DO $mt$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'yeu_cau_tuc_thi_chuan'
                 AND tgrelid = 'yeu_cau_tuc_thi'::regclass) THEN
    CREATE TRIGGER yeu_cau_tuc_thi_chuan BEFORE INSERT ON yeu_cau_tuc_thi
      FOR EACH ROW EXECUTE FUNCTION chuan_yeu_cau_tuc_thi();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'yeu_cau_tuc_thi_bao'
                 AND tgrelid = 'yeu_cau_tuc_thi'::regclass) THEN
    CREATE TRIGGER yeu_cau_tuc_thi_bao AFTER INSERT ON yeu_cau_tuc_thi
      FOR EACH ROW EXECUTE FUNCTION bao_yeu_cau_tuc_thi();
  END IF;
END $mt$;
-- Bảo mật theo dòng (M5): role mark chỉ SỬA dòng bài / kênh / quét (dòng quảng cáo do bộ nghe kết
-- thúc); đọc + thêm mọi dòng; lang_nghe_web đọc + sửa mọi dòng. Chủ bảng (lang_nghe_chu, chạy file
-- này và hàm SECURITY DEFINER) bỏ qua RLS. Bật RLS / tạo chính sách chỉ khi chưa có.
DO $mt$
BEGIN
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'yeu_cau_tuc_thi'::regclass) THEN
    ALTER TABLE yeu_cau_tuc_thi ENABLE ROW LEVEL SECURITY;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'yeu_cau_tuc_thi'
                 AND policyname = 'tuc_thi_doc') THEN
    CREATE POLICY tuc_thi_doc ON yeu_cau_tuc_thi FOR SELECT TO mark, lang_nghe_web USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'yeu_cau_tuc_thi'
                 AND policyname = 'tuc_thi_them_mark') THEN
    CREATE POLICY tuc_thi_them_mark ON yeu_cau_tuc_thi FOR INSERT TO mark WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'yeu_cau_tuc_thi'
                 AND policyname = 'tuc_thi_sua_mark') THEN
    CREATE POLICY tuc_thi_sua_mark ON yeu_cau_tuc_thi FOR UPDATE TO mark
      USING (loai <> 'quang_cao') WITH CHECK (loai <> 'quang_cao');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'yeu_cau_tuc_thi'
                 AND policyname = 'tuc_thi_sua_web') THEN
    CREATE POLICY tuc_thi_sua_web ON yeu_cau_tuc_thi FOR UPDATE TO lang_nghe_web
      USING (true) WITH CHECK (true);
  END IF;
END $mt$;

-- ───────────── Xuất Lark Sheet quảng cáo (20/10/2026, chủ dự án chốt) ─────────────
-- Trang Quảng cáo (chỉ quản trị viên) có nút "Tạo Sheet": một dòng = một yêu cầu xuất số quảng cáo
-- theo ĐÚNG bộ lọc trang (bên, nền tảng, tài khoản, từ–đến) thành MỘT Lark Sheet ba tab (theo ngày ×
-- tài khoản, theo chiến dịch, theo quảng cáo). Dashboard (lang_nghe_web) KHÔNG giữ app Lark tạo
-- được Sheet nên chỉ THÊM dòng; bộ nghe qc-sheet-nghe (user mark, `xuat_sheet_qc.py`, .env của Mark)
-- nhận qua pg_notify('qc_sheet') + quét dòng chờ lúc khởi động / mỗi phút, dựng Sheet, chia sẻ quyền
-- XEM cho người yêu cầu, nhắn link trên Lark và ghi lại trạng thái + link.
-- Vì sao bảng RIÊNG (không thêm `loai` vào yeu_cau_tuc_thi): hai bên đổi vai — ở đây web thêm, Mark
-- sửa; yeu_cau_tuc_thi cho Mark THÊM mọi dòng và cho lang_nghe_web SỬA mọi dòng (RLS tuc_thi_*).
-- Dùng chung bảng thì web sửa được link / trạng thái Sheet, Mark thêm được yêu cầu Sheet giả. Bảng
-- riêng: quyền theo cột + RLS gọn, kênh NOTIFY riêng (bộ nghe quảng cáo không bị đánh thức).
-- Bảng mới: CREATE nhanh, không khoá bảng nào khác.
CREATE TABLE IF NOT EXISTS yeu_cau_sheet_qc (
  id              BIGSERIAL PRIMARY KEY,
  nguoi_hoi       TEXT NOT NULL CHECK (length(nguoi_hoi) BETWEEN 3 AND 254),
  ben             TEXT NOT NULL CHECK (ben ~ '^[a-z0-9][a-z0-9_-]{0,39}$'),
  nen_tang        TEXT NOT NULL CHECK (nen_tang IN ('tat_ca', 'tiktok', 'meta')),
  tk              TEXT CHECK (tk IS NULL OR tk ~ '^(act_)?[0-9]{1,30}$'),
  tu              DATE NOT NULL,
  den             DATE NOT NULL,
  trang_thai      TEXT NOT NULL DEFAULT 'cho'
                  CHECK (trang_thai IN ('cho', 'dang_tao', 'xong', 'loi')),
  tieu_de         TEXT,
  sheet_url       TEXT CHECK (sheet_url IS NULL
                  OR sheet_url ~ '^https://[a-z0-9.-]+\.(larksuite\.com|feishu\.cn)(/|$)'),
  so_dong         JSONB NOT NULL DEFAULT '{}'::jsonb,
  loi             TEXT,
  loi_noi_bo      TEXT,
  da_nhan_tin     BOOLEAN NOT NULL DEFAULT FALSE,
  tao_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
  bat_dau_luc     TIMESTAMPTZ,
  xong_luc        TIMESTAMPTZ,
  CHECK (den >= tu AND den - tu < 400)
);
-- 22/10/2026 (chủ dự án): Sheet theo ĐÚNG bộ lọc trang — nhiều tài khoản (tk_ds, ≤ 200 mã; cột tk cũ
-- vẫn đọc được cho dòng cũ) + bộ lọc bảng chiến dịch / quảng cáo (tim, cd, sap, chieu). Cột NULL được
-- thêm không mặc định: tức thì, không viết lại bảng. Trigger chuan_yeu_cau_sheet_qc kiểm giá trị.
ALTER TABLE yeu_cau_sheet_qc ADD COLUMN IF NOT EXISTS tk_ds TEXT[],
  ADD COLUMN IF NOT EXISTS tim TEXT, ADD COLUMN IF NOT EXISTS cd TEXT,
  ADD COLUMN IF NOT EXISTS sap TEXT, ADD COLUMN IF NOT EXISTS chieu TEXT;
-- 22/10/2026 (chủ dự án: "khi hỏi Mark thì Mark vẫn xuất Sheet được"): Mark (tool xuat_sheet_qc,
-- role mark) cũng THÊM dòng — cho chính người hỏi. `nguon` ghi dòng từ đâu: web không được cấp
-- cột này (luôn mặc định 'web'), Mark phải ghi 'mark' (RLS sheet_qc_them_mark). Bộ nghe đọc cột này:
-- dòng web chỉ quản trị viên; dòng mark thì người có quyền ở bên, phạm vi + cột tiền tính lại từ
-- quyền CSDL của nguoi_hoi lúc dựng. Mặc định hằng số: PG ≥ 11 thêm cột không viết lại bảng; CHECK
-- chỉ quét bảng (nhỏ) một lần. IF NOT EXISTS: chạy lại bỏ qua cả ràng buộc.
ALTER TABLE yeu_cau_sheet_qc ADD COLUMN IF NOT EXISTS nguon TEXT NOT NULL DEFAULT 'web'
  CHECK (nguon IN ('web', 'mark'));
CREATE INDEX IF NOT EXISTS yeu_cau_sheet_qc_nguoi ON yeu_cau_sheet_qc (nguoi_hoi, tao_luc DESC);
CREATE INDEX IF NOT EXISTS yeu_cau_sheet_qc_cho ON yeu_cau_sheet_qc (trang_thai, id)
  WHERE trang_thai IN ('cho', 'dang_tao');
-- TRƯỚC khi thêm (SECURITY DEFINER, chủ lang_nghe_chu bỏ qua RLS để đếm cả bảng): trạng thái + cột
-- kết quả do CSDL đặt (web không chọn được); trần NGUYÊN TỬ dưới khoá advisory — một yêu cầu đang
-- chờ / đang tạo (chưa quá 30 phút) mỗi người, ≤ 4 yêu cầu mỗi người mỗi giờ, ≤ 30 yêu cầu toàn hệ
-- thống mỗi giờ. App kiểm trước cùng số (`dashboard/kho_sheet_qc.py`) để báo câu rõ; đây là chốt
-- thứ hai.
-- 22/10/2026: trigger chạy cho MỌI dòng thêm, dù web hay Mark (role mark) thêm — cùng trần, cùng
-- kiểm bộ lọc; trần đếm CHUNG hai nguồn (một người: một yêu cầu đang chờ dù bấm trang hay hỏi Mark).
-- Khoá advisory là khoá của CẢ cơ sở dữ liệu (không theo role): phiên web và phiên Mark thêm cho
-- cùng người xếp hàng trên cùng khoá 'sheet_qc|<email>'. Thứ tự khoá luôn người → toàn hệ thống
-- (`kho_sheet_qc.tao` giữ khoá người TRƯỚC khi INSERT, trigger lấy lại — cùng phiên nên không tự
-- chặn — rồi khoá '*'), nên hai nguồn không thể khoá chéo nhau. Khoá _xact nhả khi giao dịch kết thúc.
-- nguon KHÔNG bị trigger đặt lại: RLS WITH CHECK chạy SAU trigger BEFORE và kiểm đúng giá trị này.
CREATE OR REPLACE FUNCTION chuan_yeu_cau_sheet_qc() RETURNS trigger LANGUAGE plpgsql
  SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
  NEW.nguoi_hoi := lower(btrim(NEW.nguoi_hoi));
  NEW.trang_thai := 'cho';
  NEW.tao_luc := now();
  NEW.bat_dau_luc := NULL;
  NEW.xong_luc := NULL;
  NEW.tieu_de := NULL;
  NEW.sheet_url := NULL;
  NEW.so_dong := '{}'::jsonb;
  NEW.loi := NULL;
  NEW.loi_noi_bo := NULL;
  NEW.da_nhan_tin := FALSE;
  -- 22/10/2026: bộ lọc (cùng luật quang_cao.loc_bang / tk_chon); rỗng → NULL. Sai → invalid_parameter_value
  -- (app báo "Bộ lọc không hợp lệ", không lẫn với trần check_violation).
  NEW.tim := NULLIF(btrim(NEW.tim), '');
  NEW.cd := NULLIF(btrim(NEW.cd), '');
  IF cardinality(NEW.tk_ds) = 0 THEN
    NEW.tk_ds := NULL;
  END IF;
  IF NEW.tk_ds IS NOT NULL AND (cardinality(NEW.tk_ds) > 200 OR array_ndims(NEW.tk_ds) <> 1
      OR EXISTS (SELECT 1 FROM unnest(NEW.tk_ds) x WHERE x IS NULL OR x !~ '^(act_)?[0-9]{1,30}$')) THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: tk_ds sai' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF NEW.tim IS NOT NULL AND length(NEW.tim) > 100 THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: tim quá 100 ký tự' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF NEW.cd IS NOT NULL AND NEW.cd !~ '^[0-9A-Za-z_-]{0,64}$' THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: cd sai' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF NEW.sap IS NOT NULL AND NEW.sap NOT IN ('chi', 'hien_thi', 'cpm', 'click', 'ctr', 'view',
                                             'tuong_tac', 'follow', 'roas') THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: sap sai' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF NEW.chieu IS NOT NULL AND NEW.chieu NOT IN ('giam', 'tang') THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: chieu sai' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('sheet_qc|' || NEW.nguoi_hoi));
  PERFORM pg_advisory_xact_lock(hashtext('sheet_qc|*'));
  IF EXISTS (SELECT 1 FROM public.yeu_cau_sheet_qc WHERE nguoi_hoi = NEW.nguoi_hoi
             AND ((trang_thai = 'cho' AND tao_luc > now() - interval '30 minutes')
                  OR (trang_thai = 'dang_tao' AND bat_dau_luc > now() - interval '30 minutes'))) THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: đang có yêu cầu chờ' USING ERRCODE = 'check_violation';
  END IF;
  IF (SELECT count(*) FROM public.yeu_cau_sheet_qc WHERE nguoi_hoi = NEW.nguoi_hoi
      AND tao_luc > now() - interval '1 hour') >= 4 THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: quá trần mỗi người mỗi giờ' USING ERRCODE = 'check_violation';
  END IF;
  IF (SELECT count(*) FROM public.yeu_cau_sheet_qc WHERE tao_luc > now() - interval '1 hour') >= 30 THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: quá trần chung mỗi giờ' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION chuan_yeu_cau_sheet_qc() FROM PUBLIC;
-- SAU khi thêm: đánh thức bộ nghe (thông báo chỉ gửi khi giao dịch COMMIT; không ai nghe thì bỏ —
-- bộ nghe vẫn quét dòng chờ mỗi phút).
CREATE OR REPLACE FUNCTION bao_yeu_cau_sheet_qc() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  PERFORM pg_notify('qc_sheet', NEW.id::text);
  RETURN NULL;
END $fn$;
DO $mt$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'yeu_cau_sheet_qc_chuan'
                 AND tgrelid = 'yeu_cau_sheet_qc'::regclass) THEN
    CREATE TRIGGER yeu_cau_sheet_qc_chuan BEFORE INSERT ON yeu_cau_sheet_qc
      FOR EACH ROW EXECUTE FUNCTION chuan_yeu_cau_sheet_qc();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'yeu_cau_sheet_qc_bao'
                 AND tgrelid = 'yeu_cau_sheet_qc'::regclass) THEN
    CREATE TRIGGER yeu_cau_sheet_qc_bao AFTER INSERT ON yeu_cau_sheet_qc
      FOR EACH ROW EXECUTE FUNCTION bao_yeu_cau_sheet_qc();
  END IF;
END $mt$;
-- Bảo mật theo dòng: lang_nghe_web chỉ THÊM + ĐỌC dòng của CHÍNH người đang đăng nhập — app đặt
-- `set_config('lang_nghe.nguoi', <email phiên>, true)` trong cùng giao dịch (`kho_sheet_qc._la`);
-- quên đặt = không thấy dòng nào, không thêm được (lớp chặn thứ hai sau kiểm quyền của app, không
-- phải ranh giới chống chính role web). Không chính sách UPDATE / DELETE nào cho web → web không bao
-- giờ sửa trạng thái / link. Role mark đọc + sửa mọi dòng (chỉ cột kết quả — cấp theo cột cuối
-- file), không xoá. 22/10/2026: role mark THÊM được dòng (tool xuat_sheet_qc — Sheet cho chính
-- người hỏi Mark), chỉ dòng nguon = 'mark' (sheet_qc_them_mark); app Mark tự đặt nguoi_hoi = email
-- người hỏi đã xác thực — CSDL không biết người hỏi Lark nên KHÔNG tin dòng: bộ nghe tính lại quyền,
-- phạm vi tài khoản và cột tiền từ quyền CSDL của nguoi_hoi lúc dựng Sheet. Bật RLS / tạo chính
-- sách chỉ khi chưa có.
DO $mt$
BEGIN
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'yeu_cau_sheet_qc'::regclass) THEN
    ALTER TABLE yeu_cau_sheet_qc ENABLE ROW LEVEL SECURITY;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'yeu_cau_sheet_qc'
                 AND policyname = 'sheet_qc_doc_web') THEN
    CREATE POLICY sheet_qc_doc_web ON yeu_cau_sheet_qc FOR SELECT TO lang_nghe_web
      USING (nguoi_hoi = current_setting('lang_nghe.nguoi', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'yeu_cau_sheet_qc'
                 AND policyname = 'sheet_qc_them_web') THEN
    CREATE POLICY sheet_qc_them_web ON yeu_cau_sheet_qc FOR INSERT TO lang_nghe_web
      WITH CHECK (nguoi_hoi = current_setting('lang_nghe.nguoi', true));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'yeu_cau_sheet_qc'
                 AND policyname = 'sheet_qc_doc_mark') THEN
    CREATE POLICY sheet_qc_doc_mark ON yeu_cau_sheet_qc FOR SELECT TO mark USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'yeu_cau_sheet_qc'
                 AND policyname = 'sheet_qc_sua_mark') THEN
    CREATE POLICY sheet_qc_sua_mark ON yeu_cau_sheet_qc FOR UPDATE TO mark
      USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'yeu_cau_sheet_qc'
                 AND policyname = 'sheet_qc_them_mark') THEN
    CREATE POLICY sheet_qc_them_mark ON yeu_cau_sheet_qc FOR INSERT TO mark
      WITH CHECK (nguon = 'mark');
  END IF;
END $mt$;

-- ───────────── Mô tả bảng + cột theo quy chuẩn BI (task t280613, skill lsr-bq-description-standard) ─────────────
-- Chủ dự án 14/10/2026: DB mới cũng theo rule mô tả của BI (11 nhãn bảng, mô tả mọi cột). Ghi
-- ngay trong file build (COMMENT ON chạy lại không mất), có bài canh tests/test_theo_doi.py.

COMMENT ON TABLE du_an IS $$[Lớp] Raw
[Mục đích] Danh mục dự án/brand đang được lắng nghe và cấu hình lọc + thu thập (từ khoá, từ loại trừ, hashtag riêng, trần chi phí theo dõi mỗi tháng).
[Grain] 1 dòng = 1 dự án
[Khoá] PK: ma | Join: ma → nguon.du_an, bai.du_an, chi_so_ngay.du_an, luot_quet.du_an, de_xuat.du_an, lich_quet.du_an; don_vi → don_vi.ma
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
COMMENT ON COLUMN du_an.cau_hinh IS 'Cấu hình thu thập theo từng nền tảng (JSON), sửa ở trang Ngân sách: {"tu_khoa": {"<nền tảng>": {"bat", "so_bai" ≥ 0, "so_tu" ≥ 1}}, "binh_luan": {"<nền tảng>": {"bat", "so_bai" ≥ 0, "moi_bai" 0 = hết hoặc ≥ 5}}} — không trần trên nghiệp vụ (chỉ chặn số rác > 1.000.000). Khoá thiếu/giá trị rác thì dùng cột chung tk_* / bl_*; chỉ bat = true là bật; thiếu bat thì bật theo cột chung, TRỪ threads (thiếu bat = tắt — chủ dự án bật trên trang Ngân sách, từ 16/10/2026); cột tk_bat / bl_bat là công tắc tổng. {} = theo cột chung (Threads tắt). Từ 17/10/2026 "tu_khoa"."threads" có thêm "duong2": {"bat", "so_bai" = trần bài cả lượt (0 = tắt, mặc định 100), "so_bai_moi_tu" (mặc định 20), "so_luot" 1–5 (mặc định 2)} cho đường 2 tìm Threads (scrapersdelight) — chỉ chạy khi Threads bật; thiếu bat = BẬT, false = tắt. Từ 18/10/2026 "tu_khoa"."threads" có "duong1_tu": danh sách từ khoá gửi đường 1 tìm Threads (futurizerush) — thiếu thì chỉ từ khoá MỘT chữ có tên brand (tên, mã dự án, hashtag_can_nhac_brand.ten; vd hapas, hapasvn), vì futurizerush khớp cụm nhiều chữ theo từng chữ; cụm nhiều chữ chỉ đi đường 2; vẫn bỏ bo_tu của Threads; rỗng sau khi lọc thì tìm tên brand; chưa có ô trên trang Ngân sách (sửa bằng jsonb_set, lưu trang giữ nguyên). Cũng từ 17/10/2026: "tu_khoa"."facebook" có "duong2": {"bat", "so_bai_moi_tu" (bài mới nhất mỗi cụm, mặc định 12, 0 = tắt), "gio" (giờ tối thiểu giữa hai lượt, mặc định 20), "gio_chien_dich" (giờ tối thiểu khi đang có lịch chiến dịch, mặc định = gio; hạ xuống thì quét dày hơn — 6 giờ ≈ 4 lượt/ngày, tới ~25 USD/tháng/dự án)} cho đường 2 tìm Facebook (mina, chỉ cụm nhiều chữ có tên brand) — thiếu bat thì theo Facebook (số bài > 0); "tu_khoa"."tiktok" có "hashtag": {"bat", "so_yeu_cau" (trần yêu cầu mỗi lượt, mặc định 5, 0 = tắt), "gio" (mặc định 20)} cho feed hashtag TikTok của từ khoá một chữ — thiếu bat thì theo TikTok; "so_tu" của instagram là số hashtag mỗi lượt (mặc định 12). Từ 18/10/2026 "tu_khoa"."<nền tảng>"."bo_tu": danh sách từ khoá KHÔNG đem đi tìm trên nền tảng đó (mọi đường tìm của nền tảng; so trọn cụm, bỏ dấu, không phân biệt hoa thường; Instagram / feed hashtag TikTok: mục một chữ bỏ hashtag cùng dạng viết liền) — bài vẫn lọc theo đủ tu_khoa; sửa ở khối Nâng cao trang Ngân sách ("Không tìm trên…"), thiếu/rỗng = tìm mọi từ khoá. Cũng từ 18/10/2026 "seeding": {"bat" (thiếu = BẬT, chỉ false là tắt), "bai_mot_ngay" (mặc định 5), "bai_bay_ngay" (20), "trung_vi_bl" (2), "trung_vi_xem" (15000, 0 = bỏ điều kiện xem), "trung_vi_tuong_tac" (300, trung vị thích + chia sẻ thay điều kiện xem khi tài khoản không có số xem nào — chưa hiệu chỉnh, 0 = bỏ), "giu_bl_tu" (10, 0 = không giữ bài nào), "ngay" (35, số ngày lịch sử), "mien_ten_brand" (thiếu = true), "nen_tang" (mặc định ["tiktok"] — nền tảng đã hiệu chỉnh; thêm youtube / facebook / instagram / threads để bật; lượt xem 0 của Facebook / Instagram / Threads là thiếu số)} cho luật seeding affiliate cấp bài: tài khoản đăng ≥ bai_mot_ngay bài liên quan trong một ngày hoặc ≥ bai_bay_ngay bài trong 7 ngày, VÀ trung vị bình luận ≤ trung_vi_bl, trung vị lượt xem ≤ trung_vi_xem thì bài của nó không vào bai (trừ bài ≥ giu_bl_tu bình luận); kênh nhà và tài khoản mang tên dự án, mã dự án, một tên trong hashtag_can_nhac_brand.ten hoặc một du_an.hashtag (so nguyên cụm viết liền, không gồm tag kiểm độ phủ tự học) ở định danh hoặc tên hiển thị không bao giờ bị bắt; số rác/ngoài khoảng → mặc định. "tu_khoa"."instagram" / "facebook" / "threads" có "gian": {"bat" (thiếu = BẬT), "luot" (mặc định 3, 1–6), "ty_le" (0,05), "gio" (44)} giãn nhịp đường tìm ít bài mới: luot lượt tìm liền có bài mới < ty_le × bài về thì chỉ tìm lại sau gio giờ (chiến dịch đang chạy thì không giãn); lưu trang Ngân sách giữ nguyên khối này và mọi khoá biểu mẫu không có ô. Cũng từ 18/10/2026 "hashtag_can_nhac_brand": true / false hoặc {"bat" (thiếu = BẬT, chỉ false là tắt), "ten" (danh sách tên brand thêm, vd thương hiệu con), "tag_rong" (hashtag rộng KHÔNG tính là tên brand, thiếu = ["quatang2010"])} cho cổng brand của bài CHỈ đến từ đường hashtag (feed hashtag TikTok, Instagram tìm theo hashtag, TikTok dự phòng theo hashtag, mẫu hashtag của kiểm độ phủ): bài chỉ vào bai khi nội dung, hashtag, tên hoặc định danh chủ bài (hoặc chính hashtag của feed) gọi tên dự án, mã dự án, một tên trong "ten" hoặc một tag chiến dịch của dự án (du_an.hashtag, tag kiểm độ phủ thêm vào lượt nổi khi tag chứa tên brand, khẩu hiệu lịch chiến dịch đang chạy — dạng viết liền, trừ tag_rong và tag chung chung; từ 18/10/2026) (bỏ dấu, không phân biệt hoa thường); kênh nhà miễn; bài bị bỏ trước AI, vào sổ đã loại với lý do hashtag_khong_nhac_brand (mỗi lượt xét lại theo danh sách tên hiện hành — thêm tên / tag là gỡ được; chưa có ô trên trang Ngân sách: sửa JSON bằng jsonb_set, lệnh mẫu ở theo_doi.py, lưu trang Ngân sách giữ nguyên khối).';
COMMENT ON COLUMN du_an.sua_boi IS 'Email người sửa gần nhất trên dashboard. NULL khi tạo bằng lệnh cài đặt. Email nội bộ — không đẩy lên BigQuery.';
COMMENT ON COLUMN du_an.don_vi IS 'Bên (đơn vị) sở hữu dự án, từ 19/10/2026. FK → don_vi.ma. Không NULL. Quyết định ai xem/sửa dự án trên dashboard và ai hỏi được Mark số của dự án (quyen.don_vi). Dự án có trước 19/10/2026: mã chứa "matemade" → matemade, còn lại → hapas. Chỉ quản trị viên chuyển được dự án sang bên khác. Chưa đẩy lên BigQuery.';

COMMENT ON TABLE don_vi IS $$[Lớp] Raw
[Mục đích] Danh mục bên (đơn vị: HAPAS, MATEMADE…) sở hữu dự án lắng nghe, làm gốc cho phân quyền theo bên trên dashboard.
[Grain] 1 dòng = 1 bên
[Khoá] PK: ma | Join: ma → du_an.don_vi, quyen.don_vi
[Nguồn] Quản trị viên tạo trên dashboard social.hapas.vn (trang Quản trị); hapas, matemade có sẵn từ schema.sql
[Phạm vi] Mọi bên dùng dashboard | Kênh: Không có | Từ 19/10/2026
[Đã xử lý] Mã chữ thường, số, -, _ (2–40 ký tự, ràng buộc CHECK); tên 1–200 ký tự
[Refresh] Ghi tức thời khi quản trị viên tạo bên (ghi nhat_ky)
[Dùng khi] Biết dự án thuộc bên nào, tên hiển thị của bên
[Không dùng khi] Ai có quyền ở bên nào → dùng quyen
[Lưu ý] Không xoá bên trên dashboard (dự án và quyền trỏ tới). Không đẩy lên BigQuery.$$;
COMMENT ON COLUMN don_vi.ma IS 'Mã bên (vd hapas, matemade). PK. Chữ thường, số, -, _; 2–40 ký tự. Join: → du_an.don_vi, quyen.don_vi.';
COMMENT ON COLUMN don_vi.ten IS 'Tên hiển thị của bên (vd HAPAS). Không NULL, 1–200 ký tự.';
COMMENT ON COLUMN don_vi.tao_luc IS 'Thời điểm tạo bên (UTC).';

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
[Đã xử lý] Chỉ bài liên quan (nhắc từ khoá trừ kênh nhà, không chứa từ loại trừ, không bị AI loại); từ 18/10/2026 không có bài seeding affiliate (mặc định chỉ TikTok — nền tảng khác bật ở du_an.cau_hinh.seeding.nen_tang; tài khoản không phải kênh nhà, không mang tên brand, đăng ≥ 5 bài/ngày hoặc ≥ 20 bài/7 ngày với trung vị ≤ 2 bình luận và ≤ 15.000 lượt xem — ngưỡng ở du_an.cau_hinh.seeding; bài tự có ≥ 10 bình luận vẫn giữ; bài cũ dọn bằng scripts/lang_nghe_loc_seeding.py), bài tìm theo từ khoá ngoài thị trường VN (nội dung chữ Thái/Hàn/Trung/Hindi… hoặc kênh YouTube khai nước khác, không có dấu hiệu Việt; ca mơ hồ như tài khoản brand nước khác viết Latin do AI phán mã other_market — từ 18/10/2026) và bài chỉ đến từ đường hashtag (feed hashtag TikTok, Instagram hashtag) mà không gọi tên brand ở nội dung, hashtag, tên hay định danh chủ bài (tên brand gồm tag chiến dịch của dự án: du_an.hashtag, tag kiểm độ phủ thêm vào lượt nổi khi tag chứa tên brand, khẩu hiệu lịch chiến dịch đang chạy — trừ tag rộng như #quatang2010; trừ kênh nhà; tắt ở du_an.cau_hinh.hashtag_can_nhac_brand); khử trùng theo khoa; bài Facebook khử trùng thêm theo id số ma_so_fb, không có id thì theo chủ bài + phút đăng + nội dung (pfbid trong link đổi mỗi lượt cào, từ 17/10/2026; bản trùng cũ gộp bằng scripts/lang_nghe_gop_bai_fb.py); nội dung cắt 1.000 ký tự
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
COMMENT ON COLUMN bai.gio_hang IS 'Chỉ TikTok: TRUE = video gắn giỏ TikTok Shop (KOC affiliate trên dashboard), FALSE = không gắn giỏ (KOC branding), theo từng video. Đọc từ tìm kiếm / hồ sơ TikTok (anchors không có shop, kể cả anchors trống = FALSE); feed hashtag chỉ báo được TRUE (không bao giờ trả anchor shop, đo 21/10/2026). NULL = chưa rõ: video chỉ thấy ở feed hashtag, nguồn không báo, hoặc nền tảng khác — không phải FALSE. TRUE không bị lần đọc sau hạ; bài trước 20/10/2026 điền bằng scripts/lang_nghe_nap_gio_hang.py.';
COMMENT ON COLUMN bai.la_quang_cao IS 'Chỉ TikTok: TRUE = TikTok đánh dấu video là quảng cáo (is_ads / isAd), FALSE = không. NULL = nguồn không báo hoặc nền tảng khác. Không dùng để tách KOC (tiêu chí là gio_hang).';

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
[Mục đích] Ai được vào dashboard social.hapas.vn: cờ quản trị viên toàn hệ thống và thông tin danh bạ Lark; vai trò theo từng bên ở bảng quyen.
[Grain] 1 dòng = 1 email
[Khoá] PK: email | Join: email → quyen.email
[Nguồn] Quản trị viên / quản lý của bên thêm, xoá trên dashboard; quản trị viên đầu tiên đặt bằng schema.sql hoặc lệnh quan_tri; tên, chức danh, phòng ban, trạng thái đọc từ danh bạ Lark (contact API)
[Phạm vi] Nhân viên HAPAS (tài khoản Lark của tổ chức) | Kênh: Không có | Từ khi cài dashboard; la_quan_tri từ 19/10/2026
[Đã xử lý] Email chữ thường; trạng thái Lark quy về 5 giá trị; vai_tro (cột cũ) = vai trò gộp từ la_quan_tri + quyen
[Refresh] Ghi tức thời khi sửa người xem; cột danh bạ làm mới ≤ 12 giờ/lần khi mở trang Quản trị và khi thêm email; dang_nhap_cuoi, lark_open_id, lark_union_id, lark_user_id ghi mỗi lượt đăng nhập
[Dùng khi] Kiểm quyền đăng nhập dashboard, biết ai là quản trị viên
[Không dùng khi] Vai trò ở từng bên → dùng quyen; lịch sử thêm/xoá → dùng nhat_ky
[Lưu ý] Email nội bộ — không đẩy lên BigQuery. Luôn phải còn ít nhất một quản trị viên. Người không phải quản trị viên mà không có dòng quyen nào thì không đăng nhập được (dashboard xoá luôn dòng).$$;
COMMENT ON COLUMN nguoi_xem.email IS 'Email công ty (enterprise_email Lark), chữ thường. PK. Join: → quyen.email.';
COMMENT ON COLUMN nguoi_xem.vai_tro IS 'CŨ (trước 19/10/2026), chỉ giữ để tương thích — KHÔNG dùng để quyết định quyền (dùng la_quan_tri + quyen). Dashboard giữ = vai trò gộp: quan_ly khi là quản trị viên hoặc Quản lý ít nhất một bên, còn lại xem. Giá trị: xem, quan_ly.';
COMMENT ON COLUMN nguoi_xem.la_quan_tri IS 'TRUE: quản trị viên toàn hệ thống (mọi bên, mọi dự án, tạo bên, thêm/xoá/đổi mọi người kể cả quản trị viên khác, trang BigQuery). FALSE (mặc định): quyền theo từng bên ở bảng quyen. Từ 19/10/2026; luôn còn ít nhất một TRUE.';
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

COMMENT ON TABLE quyen IS $$[Lớp] Raw
[Mục đích] Vai trò của từng người xem ở từng bên (Quản lý / Chỉ xem) — dashboard và Mark chỉ cho người này đọc / sửa dự án của các bên ở đây.
[Grain] 1 dòng = 1 người xem × 1 bên
[Khoá] PK: email + don_vi | Join: email → nguoi_xem.email; don_vi → don_vi.ma, du_an.don_vi
[Nguồn] Quản trị viên (mọi vai trò) hoặc quản lý của bên (chỉ người Chỉ xem của bên mình) thêm/xoá trên dashboard; lệnh quan_tri; dòng có trước 19/10/2026 chép từ nguoi_xem.vai_tro sang bên hapas
[Phạm vi] Mọi người xem không phải quản trị viên (quản trị viên có thể có hoặc không) | Kênh: Không có | Từ 19/10/2026
[Đã xử lý] Vai trò quy về 2 giá trị (ràng buộc CHECK)
[Refresh] Ghi tức thời khi sửa người xem (ghi nhat_ky trước/sau)
[Dùng khi] Kiểm ai xem / sửa được dự án của bên nào
[Không dùng khi] Quản trị viên toàn hệ thống → dùng nguoi_xem.la_quan_tri; lịch sử đổi quyền → dùng nhat_ky
[Lưu ý] Email nội bộ — không đẩy lên BigQuery. Xoá người xem thì quyền xoá theo (ON DELETE CASCADE); bỏ dòng cuối của người không phải quản trị viên thì dashboard xoá luôn người đó.$$;
COMMENT ON COLUMN quyen.email IS 'Email người xem. Một phần PK. FK → nguoi_xem.email (xoá người thì xoá quyền).';
COMMENT ON COLUMN quyen.don_vi IS 'Bên được cấp quyền. Một phần PK. FK → don_vi.ma.';
COMMENT ON COLUMN quyen.vai_tro IS 'Vai trò ở bên này. Giá trị: xem (chỉ đọc dự án của bên), quan_ly (sửa dự án, nguồn, từ khoá, ngân sách từng dự án, lịch quét, duyệt đề xuất của bên; thêm/xoá người Chỉ xem của bên).';
COMMENT ON COLUMN quyen.them_boi IS 'Email người cấp quyền; chuyen_quyen_ben khi chép từ vai trò cũ (schema.sql 19/10/2026); cli:<user> khi cấp bằng lệnh quan_tri. Email nội bộ.';
COMMENT ON COLUMN quyen.them_luc IS 'Thời điểm cấp quyền lần đầu ở bên này (UTC; đổi vai trò không đổi cột này).';

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
[Lưu ý] Có email nội bộ — không đẩy lên BigQuery; quản trị viên xem mọi dòng, quản lý của bên chỉ xem dòng về dự án / quyền của bên mình.$$;
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

COMMENT ON TABLE ket_noi_ngoai IS $$[Lớp] Raw
[Mục đích] Trạng thái kết nối tới dịch vụ ngoài của dashboard (TikTok Ads qua TikTok for Business MCP; Meta Ads qua Graph API, từ 20/10/2026) — loại token, hạn, người cấp, số tài khoản thấy, lượt đồng bộ gần nhất — cho thẻ "Kết nối TikTok Ads" / "Kết nối Meta Ads", dải trạng thái đồng bộ và lời nhắc gia hạn của Mark.
[Grain] 1 dòng = 1 nhà cung cấp kết nối (nha_cung_cap)
[Khoá] PK: nha_cung_cap | Join: Không có
[Nguồn] Dashboard social.hapas.vn (OAuth / dán token của quản trị viên trên trang Quản trị; lệnh python -m dashboard.meta_ads nhap-token; nút "Đồng bộ ngay" của mọi người có quyền) và bộ hẹn giờ tiktok-ads-* / meta-ads-* (dashboard/tiktok_ads.py, dashboard/meta_ads.py)
[Phạm vi] Nhà cung cấp tiktok_ads (từ 19/10/2026), meta_ads (từ 20/10/2026) | Kênh TikTok Ads, Meta Ads | Từ 19/10/2026
[Đã xử lý] Token MÃ HOÁ AES-256-GCM (AAD = nhà cung cấp + tên cột; một khoá TIKTOK_KHOA_MA_HOA chung, chỉ ở /opt/lang-nghe/.env); token Meta chỉ lưu khi quyền đã cấp nằm trọn trong ads_read, read_insights, public_profile; lỗi đã bỏ URL và chuỗi giống token
[Refresh] Ghi khi quản trị viên kết nối/ngắt/dán token, khi ai đó bấm Đồng bộ ngay (chỉ ghi cờ yêu cầu), khi làm mới access token TikTok (≈ mỗi 24 giờ khi đồng bộ) và mỗi lượt đồng bộ (06:30 TikTok / 06:45 Meta giờ VN hằng ngày + lượt theo yêu cầu, bộ hẹn giờ 2 phút)
[Dùng khi] Biết kết nối còn hạn bao lâu, ai cấp, lần đồng bộ / gọi thành công cuối, lỗi cuối
[Không dùng khi] Số quảng cáo → dùng qc_tk_ngay, qc_campaign_ngay, qc_ad_ngay; danh sách tài khoản → dùng tk_quang_cao
[Lưu ý] Refresh token TikTok KHÔNG được gia hạn khi làm mới: hạn cứng 30 ngày từ lần đăng nhập (refresh_het_luc); loai api_token không hết hạn. Role mark chỉ đọc nha_cung_cap, loai, trang_thai, refresh_het_luc, goi_ok_luc, loi_cuoi. Không đẩy lên BigQuery.$$;
COMMENT ON COLUMN ket_noi_ngoai.nha_cung_cap IS 'Mã nhà cung cấp. PK. Giá trị: tiktok_ads, meta_ads (từ 20/10/2026).';
COMMENT ON COLUMN ket_noi_ngoai.loai IS 'Loại token. Giá trị: mcp_oauth (OAuth của quản trị viên, access ~24 giờ + refresh 30 ngày không gia hạn), api_token (TikTok: token API của app developer; Meta: token người dùng hệ thống chỉ đọc — không hết hạn, không làm mới).';
COMMENT ON COLUMN ket_noi_ngoai.client_id IS 'Mã client OAuth TikTok cấp khi dashboard tự đăng ký (Dynamic Client Registration, client công khai — không có secret). NULL khi chưa đăng ký.';
COMMENT ON COLUMN ket_noi_ngoai.redirect_uri IS 'Địa chỉ trả về đã đăng ký cùng client_id (DASH_BASE_URL + /tiktok/xong). Đổi địa chỉ thì dashboard đăng ký client mới.';
COMMENT ON COLUMN ket_noi_ngoai.access_token_enc IS 'Access token ĐÃ MÃ HOÁ AES-256-GCM (base64 của phiên bản 1 byte + nonce 12 byte + bản mã và thẻ). BÍ MẬT — role mark không được đọc. NULL khi chưa kết nối / đã ngắt.';
COMMENT ON COLUMN ket_noi_ngoai.refresh_token_enc IS 'Refresh token ĐÃ MÃ HOÁ. BÍ MẬT — role mark không được đọc. NULL với loai api_token, chưa kết nối hoặc đã ngắt.';
COMMENT ON COLUMN ket_noi_ngoai.access_het_luc IS 'Thời điểm access token hết hạn (UTC). NULL với api_token (không hết hạn) hoặc khi chưa kết nối.';
COMMENT ON COLUMN ket_noi_ngoai.refresh_het_luc IS 'Thời điểm refresh token hết hạn = hạn cứng của lần đăng nhập (UTC; ~30 ngày từ cap_luc, làm mới không kéo dài). NULL với api_token hoặc khi chưa kết nối.';
COMMENT ON COLUMN ket_noi_ngoai.nguoi_cap IS 'Email Lark của quản trị viên đã cấp quyền lần gần nhất. NULL khi chưa kết nối.';
COMMENT ON COLUMN ket_noi_ngoai.cap_luc IS 'Thời điểm cấp quyền (OAuth xong / dán token) lần gần nhất (UTC).';
COMMENT ON COLUMN ket_noi_ngoai.lam_moi_luc IS 'Lần làm mới access token gần nhất (UTC). NULL khi chưa làm mới lần nào từ lần cấp quyền.';
COMMENT ON COLUMN ket_noi_ngoai.goi_ok_luc IS 'Lần gọi TikTok thành công gần nhất (đọc danh sách tài khoản), UTC.';
COMMENT ON COLUMN ket_noi_ngoai.so_tk_thay IS 'Số tài khoản quảng cáo lần đọc gần nhất thấy được, tài khoản. NULL khi chưa đọc.';
COMMENT ON COLUMN ket_noi_ngoai.so_tk_truoc IS 'Số tài khoản lần đọc liền trước, tài khoản — so với so_tk_thay để cảnh báo khi mất quyền một tài khoản. NULL khi mới đọc một lần.';
COMMENT ON COLUMN ket_noi_ngoai.loi_cuoi IS 'Lỗi gần nhất (đã bỏ URL/chuỗi giống token), ≤ 500 ký tự. NULL khi chưa lỗi lần nào.';
COMMENT ON COLUMN ket_noi_ngoai.loi_luc IS 'Thời điểm ghi loi_cuoi (UTC).';
COMMENT ON COLUMN ket_noi_ngoai.trang_thai IS 'Trạng thái kết nối. Giá trị: chua_ket_noi, hoat_dong, het_han (refresh token hết 30 ngày hoặc bị từ chối khi làm mới), loi (TikTok từ chối token / lỗi khác), da_ngat (quản trị viên ngắt).';
COMMENT ON COLUMN ket_noi_ngoai.dong_bo_bat_dau IS 'Lúc lượt đồng bộ gần nhất bắt đầu (UTC).';
COMMENT ON COLUMN ket_noi_ngoai.dong_bo_xong IS 'Lúc lượt đồng bộ gần nhất kết thúc (UTC). NULL khi đang chạy (hoặc bị ngắt giữa chừng).';
COMMENT ON COLUMN ket_noi_ngoai.dong_bo_ok_luc IS 'Lần đồng bộ gần nhất kết thúc KHÔNG lỗi (UTC).';
COMMENT ON COLUMN ket_noi_ngoai.dong_bo_so_dong IS 'Số dòng qc_* ghi/sửa trong lượt đồng bộ gần nhất, dòng.';
COMMENT ON COLUMN ket_noi_ngoai.dong_bo_loi IS 'Lỗi của lượt đồng bộ gần nhất (theo tài khoản, đã gọn). NULL khi lượt ổn.';
COMMENT ON COLUMN ket_noi_ngoai.so_den_ngay IS 'Số liệu đã đồng bộ tới hết ngày này (múi giờ tài khoản, thường là hôm qua). NULL khi chưa đồng bộ.';
COMMENT ON COLUMN ket_noi_ngoai.yeu_cau_dong_bo_luc IS 'Lúc có người bấm “Đồng bộ ngay” (hoặc quản trị viên vừa kết nối) mà lượt chưa chạy (UTC). Bộ hẹn giờ tiktok-ads-yeu-cau / meta-ads-yeu-cau (2 phút/lần) chạy khi cột này khác NULL; lượt bắt đầu thì đặt lại NULL. NULL = không có yêu cầu chờ.';
COMMENT ON COLUMN ket_noi_ngoai.yeu_cau_boi IS 'Email Lark của người gửi yêu cầu đồng bộ gần nhất. NULL khi chưa ai yêu cầu.';
COMMENT ON COLUMN ket_noi_ngoai.cap_nhat_luc IS 'Lần sửa dòng gần nhất (UTC).';
COMMENT ON COLUMN ket_noi_ngoai.chu_token IS 'Tên người dùng của token (Meta: me.name, vd mark_ads_reader) — không bí mật, hiện trên thẻ kết nối. NULL với TikTok hoặc khi chưa dán token.';
COMMENT ON COLUMN ket_noi_ngoai.quyen_token IS 'Quyền đã cấp của token (Meta: me/permissions trạng thái granted, vd {ads_read,read_insights,public_profile}) lúc lưu. NULL với TikTok hoặc khi chưa dán token.';
COMMENT ON COLUMN ket_noi_ngoai.yeu_cau_kieu IS 'Loại yêu cầu đồng bộ đang chờ. Giá trị: day_du (quản trị viên / vừa kết nối: lượt thường, nạp lùi nếu cần), nhanh (người có quyền bấm Đồng bộ ngay: hôm nay + 2 ngày trước, chỉ tài khoản có hiển thị). Yêu cầu day_du đang chờ không bị hạ thành nhanh. NULL khi không có yêu cầu.';
COMMENT ON COLUMN ket_noi_ngoai.dong_bo_kieu IS 'Loại lượt đồng bộ gần nhất / đang chạy. Giá trị: day_du, nhanh. NULL khi chưa có lượt nào từ 20/10/2026.';
COMMENT ON COLUMN ket_noi_ngoai.nhanh_xong_luc IS 'Lúc lượt nhanh (bấm tay) gần nhất kết thúc (UTC) — bấm lại được sau 15 phút. NULL khi chưa có lượt nhanh.';
COMMENT ON TABLE tk_quang_cao IS $$[Lớp] Dim
[Mục đích] Danh sách tài khoản quảng cáo TikTok + Meta dashboard đọc được, tài khoản thuộc bên nào và (Meta) đã được duyệt đọc số chưa — quyết định ai xem được số của tài khoản.
[Grain] 1 dòng = 1 tài khoản quảng cáo (advertiser_id: TikTok advertiser hoặc Meta act_…)
[Khoá] PK: advertiser_id | Join: don_vi → don_vi.ma; advertiser_id → qc_tk_ngay, qc_campaign_ngay, qc_ad_ngay, qc_khan_gia
[Nguồn] TikTok for Business MCP: auth_advertiser_get (tên) + advertiser_info_get (tiền tệ, múi giờ); Meta Graph API GET me/adaccounts (tên, currency, timezone_name) — mỗi lượt đồng bộ; bên + duyệt do gán tự động / lệnh nhập token hoặc quản trị viên sửa trên trang Quản trị
[Phạm vi] Mọi tài khoản quảng cáo người cấp quyền / token thấy được (19/10/2026: 16 tài khoản TikTok; 20/10/2026: 20 tài khoản Meta) | Kênh TikTok Ads + Meta Ads | Từ 19/10/2026 (Meta từ 20/10/2026)
[Đã xử lý] Gán bên tự động khi thấy: tên có chữ THAI đứng riêng → chưa gán (NULL); tên có MATEMADE / MATE MADE / MADEMATE (không phân biệt hoa thường, khoảng trắng, dấu) → matemade; còn lại → hapas; không bao giờ đè bên quản trị viên đã sửa (gan_tay). Meta: tài khoản mới chưa duyệt trừ khi có trong danh sách nhập kèm token
[Refresh] Upsert mỗi lượt đồng bộ (06:30 TikTok / 06:45 Meta giờ VN + bấm tay) và khi kết nối; sửa tay bên/đồng bộ/duyệt trên trang Quản trị
[Dùng khi] Lọc số quảng cáo theo bên; biết tài khoản nào đang đồng bộ, đã nạp lùi 90 ngày chưa
[Không dùng khi] Số chi/hiển thị → dùng qc_tk_ngay; trạng thái token → dùng ket_noi_ngoai
[Lưu ý] don_vi NULL = chưa gán bên, chỉ quản trị viên thấy. con_quyen false = lần đọc gần nhất không còn thấy tài khoản (mất quyền) — số cũ giữ nguyên. duyet false (chỉ Meta) = không đọc số, trang và Mark bỏ qua.$$;
COMMENT ON COLUMN tk_quang_cao.advertiser_id IS 'Mã tài khoản quảng cáo: TikTok chuỗi số; Meta act_<số> (từ 20/10/2026). PK. Join: → qc_*.advertiser_id.';
COMMENT ON COLUMN tk_quang_cao.ten IS 'Tên tài khoản trên nền tảng (TikTok advertiser_name; Meta name; đã bỏ khoảng trắng hai đầu), vd "MATEMADE MKT". Chuỗi rỗng khi nền tảng không trả (hoặc tài khoản Meta đã duyệt nhưng chưa thấy).';
COMMENT ON COLUMN tk_quang_cao.don_vi IS 'Bên sở hữu tài khoản. FK → don_vi.ma. NULL = chưa gán bên (chỉ quản trị viên thấy số).';
COMMENT ON COLUMN tk_quang_cao.gan_tay IS 'TRUE: quản trị viên đã sửa bên/đồng bộ trên trang Quản trị — gán tự động không đè. FALSE: bên do gán tự động.';
COMMENT ON COLUMN tk_quang_cao.gan_luc IS 'Lần quản trị viên sửa bên/đồng bộ gần nhất (UTC; người sửa ở nhat_ky). NULL khi chưa sửa tay.';
COMMENT ON COLUMN tk_quang_cao.tien_te IS 'Tiền tệ của tài khoản (currency, mã ISO, vd VND) — đơn vị mọi cột tiền của tài khoản.';
COMMENT ON COLUMN tk_quang_cao.mui_gio IS 'Múi giờ của tài khoản (TikTok display_timezone; Meta timezone_name; vd Asia/Ho_Chi_Minh) — ngày trong qc_* theo múi giờ này.';
COMMENT ON COLUMN tk_quang_cao.dang_dong_bo IS 'TRUE: lượt đồng bộ đọc số tài khoản này. FALSE: quản trị viên tắt (số cũ giữ).';
COMMENT ON COLUMN tk_quang_cao.con_quyen IS 'TRUE: lần đọc gần nhất còn thấy tài khoản. FALSE: không còn thấy (người cấp quyền mất quyền) — không đồng bộ, số cũ giữ.';
COMMENT ON COLUMN tk_quang_cao.thay_lan_dau IS 'Lần đầu dashboard thấy tài khoản (UTC).';
COMMENT ON COLUMN tk_quang_cao.thay_cuoi IS 'Lần gần nhất thấy tài khoản (UTC).';
COMMENT ON COLUMN tk_quang_cao.nap_lui_tu IS 'Nạp lùi đã đọc xong xuống tới ngày này (múi giờ tài khoản; cửa sổ 30 ngày mới trước). Lượt bị ngắt giữa chừng thì lượt sau chỉ đọc phần trước ngày này. NULL khi chưa nạp cửa sổ nào.';
COMMENT ON COLUMN tk_quang_cao.nap_lui_xong_luc IS 'Lúc nạp lùi 90 ngày lần đầu xong (UTC). NULL = chưa nạp lùi (lượt sau nạp).';
COMMENT ON COLUMN tk_quang_cao.khan_gia_luc IS 'Lần đọc khán giả gần nhất (UTC; đọc lại mỗi 7 ngày). NULL khi chưa đọc.';
COMMENT ON COLUMN tk_quang_cao.cap_nhat_luc IS 'Lần sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery (bảng nhỏ — nạp lại toàn bộ).';
COMMENT ON COLUMN tk_quang_cao.nen_tang IS 'Nền tảng quảng cáo. Giá trị: tiktok, meta (từ 20/10/2026). Dòng trước 20/10/2026 = tiktok.';
COMMENT ON COLUMN tk_quang_cao.duyet IS 'TRUE: được đọc số (TikTok luôn TRUE; Meta = có trong danh sách duyệt — thay MARK_META_AD_ACCOUNT_IDS, nhập kèm token hoặc quản trị viên tích trên trang Quản trị). FALSE: tài khoản Meta thấy được nhưng chưa duyệt — không đồng bộ, trang và Mark bỏ qua.';
COMMENT ON TABLE qc_tk_ngay IS $$[Lớp] Raw
[Mục đích] Số quảng cáo TikTok / Meta theo ngày của cả tài khoản (chi, hiển thị, xem video, tương tác, follow, doanh thu Shop…) cho trang "Quảng cáo" và Mark.
[Grain] 1 dòng = 1 tài khoản quảng cáo × 1 ngày (múi giờ tài khoản)
[Khoá] PK: advertiser_id + ngay | Join: advertiser_id → tk_quang_cao.advertiser_id
[Nguồn] TikTok for Business MCP report_integrated_get (BASIC, AUCTION_ADVERTISER, chiều advertiser_id + stat_time_day), bộ hẹn giờ tiktok-ads-dong-bo; Meta: Graph API GET act_<id>/insights (time_increment=1; khán giả: breakdowns, không theo ngày), bộ hẹn giờ meta-ads-dong-bo
[Phạm vi] Tài khoản tk_quang_cao đang đồng bộ | Kênh TikTok Ads + Meta Ads (Facebook/Instagram, từ 20/10/2026) | Từ 90 ngày trước lần kết nối đầu (nạp lùi)
[Đã xử lý] Chỉ ngày có hiển thị hoặc chi > 0; số đổi từ chữ ("-" → NULL); cột số kiểu riêng chép từ chi_so
[Refresh] Upsert hằng ngày 06:30 (TikTok) / 06:45 (Meta) giờ VN + lượt bấm tay "Đồng bộ ngay" (hôm nay + 2 ngày trước): đọc lại 7 ngày gần nhất tới hết hôm qua; lần đầu mỗi tài khoản 90 ngày (3 cửa sổ 30 ngày)
[Dùng khi] Tổng chi/hiển thị/xem/tương tác theo ngày, tài khoản, bên; xu hướng; ROAS Shop = gia_tri_mua_shop / chi
[Không dùng khi] Số từng chiến dịch → dùng qc_campaign_ngay; từng quảng cáo → dùng qc_ad_ngay; tuổi/giới tính/tỉnh → dùng qc_khan_gia
[Lưu ý] Chuyển đổi TikTok ghi trễ tới 7 ngày nên số 7 ngày gần nhất còn đổi; reach cộng nhiều ngày là đếm trùng người. Tiền theo tiền tệ tài khoản, chỉ quản trị viên + quản lý của bên thấy.$$;
COMMENT ON COLUMN qc_tk_ngay.advertiser_id IS 'Tài khoản quảng cáo. Một phần PK. FK → tk_quang_cao.advertiser_id.';
COMMENT ON COLUMN qc_tk_ngay.ngay IS 'Ngày số liệu theo múi giờ tài khoản (tk_quang_cao.mui_gio, thường GMT+7). Một phần PK.';
COMMENT ON COLUMN qc_tk_ngay.chi IS 'Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy.';
COMMENT ON COLUMN qc_tk_ngay.hien_thi IS 'Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.reach IS 'Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.click IS 'Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.ket_qua IS 'Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.chuyen_doi IS 'Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.view_video IS 'Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.view_hai_giay IS 'Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.view_sau_giay IS 'Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.view_het IS 'Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.engaged_view IS 'Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.thich IS 'Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.binh_luan IS 'Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.chia_se IS 'Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.follow IS 'Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.vao_ho_so IS 'Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.mua_shop IS 'Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_tk_ngay.gia_tri_mua_shop IS 'Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi, phân bổ mặc định của Meta). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN.';
COMMENT ON COLUMN qc_tk_ngay.chi_so IS 'MỌI chỉ số nền tảng trả cho dòng (JSON {tên chỉ số: số}; số đã đổi từ chữ, "-" của TikTok → null). TikTok: tài khoản/campaign đủ 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Meta (20/10/2026): mọi trường Insights đã xin, danh sách action thành <trường>__<action_type> (vd actions__purchase, action_values__purchase, video_p100_watched_actions__video_view); reach, frequency, ctr, cpc, cpm, cpp, *_avg_*, *roas* KHÔNG cộng được qua dòng. Khoá tiền: spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*.';
COMMENT ON COLUMN qc_tk_ngay.cap_nhat_luc IS 'Lần đồng bộ ghi/sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON TABLE qc_campaign_ngay IS $$[Lớp] Raw
[Mục đích] Số quảng cáo TikTok / Meta theo ngày của từng chiến dịch (campaign) có phân phối — xếp hạng chiến dịch theo chi/hiển thị/xem/follow.
[Grain] 1 dòng = 1 campaign × 1 ngày (múi giờ tài khoản)
[Khoá] PK: campaign_id + ngay | Join: advertiser_id → tk_quang_cao.advertiser_id; campaign_id → qc_ad_ngay.campaign_id
[Nguồn] TikTok for Business MCP report_integrated_get (BASIC, AUCTION_CAMPAIGN, chiều campaign_id + stat_time_day; tên + mục tiêu xin như chỉ số), bộ hẹn giờ tiktok-ads-dong-bo; Meta: Graph API GET act_<id>/insights (time_increment=1; khán giả: breakdowns, không theo ngày), bộ hẹn giờ meta-ads-dong-bo
[Phạm vi] Tài khoản tk_quang_cao đang đồng bộ, chỉ campaign có hiển thị trong cửa sổ đọc | Kênh TikTok Ads + Meta Ads (Facebook/Instagram, từ 20/10/2026) | Từ 90 ngày trước lần kết nối đầu
[Đã xử lý] Lấy ID campaign xếp impressions giảm dần, dừng ở dòng 0 đầu tiên; đọc số theo lô ≤ 100 ID; chỉ ngày có hiển thị hoặc chi > 0; "-" → NULL
[Refresh] Upsert hằng ngày 06:30 (TikTok) / 06:45 (Meta) giờ VN + lượt bấm tay "Đồng bộ ngay" (hôm nay + 2 ngày trước), đọc lại 7 ngày gần nhất; lần đầu 90 ngày
[Dùng khi] Top chiến dịch trong kỳ; chi/hiển thị/xem theo chiến dịch và ngày
[Không dùng khi] Tổng tài khoản → dùng qc_tk_ngay (đủ cả phần không gán chiến dịch); từng quảng cáo → dùng qc_ad_ngay
[Lưu ý] ten / muc_tieu là giá trị lúc đọc (đổi tên thì dòng cũ giữ tên cũ — lấy tên ngày mới nhất). Ngân sách chiến dịch (campaign_budget) chỉ nằm trong chi_so và là số tiền.$$;
COMMENT ON COLUMN qc_campaign_ngay.advertiser_id IS 'Tài khoản quảng cáo của campaign. FK → tk_quang_cao.advertiser_id.';
COMMENT ON COLUMN qc_campaign_ngay.campaign_id IS 'Mã campaign (TikTok campaign_id; Meta campaign_id). Một phần PK. Join: → qc_ad_ngay.campaign_id.';
COMMENT ON COLUMN qc_campaign_ngay.ngay IS 'Ngày số liệu theo múi giờ tài khoản (thường GMT+7). Một phần PK.';
COMMENT ON COLUMN qc_campaign_ngay.ten IS 'Tên campaign lúc đọc (campaign_name). Chuỗi rỗng khi TikTok không trả.';
COMMENT ON COLUMN qc_campaign_ngay.muc_tieu IS 'Mục tiêu campaign: TikTok objective_type (vd REACH, VIDEO_VIEWS, PRODUCT_SALES); Meta objective (vd OUTCOME_ENGAGEMENT, OUTCOME_SALES, LINK_CLICKS). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.chi IS 'Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy.';
COMMENT ON COLUMN qc_campaign_ngay.hien_thi IS 'Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.reach IS 'Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.click IS 'Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.ket_qua IS 'Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.chuyen_doi IS 'Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.view_video IS 'Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.view_hai_giay IS 'Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.view_sau_giay IS 'Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.view_het IS 'Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.engaged_view IS 'Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.thich IS 'Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.binh_luan IS 'Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.chia_se IS 'Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.follow IS 'Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.vao_ho_so IS 'Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.mua_shop IS 'Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_campaign_ngay.gia_tri_mua_shop IS 'Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi, phân bổ mặc định của Meta). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN.';
COMMENT ON COLUMN qc_campaign_ngay.chi_so IS 'MỌI chỉ số nền tảng trả cho dòng (JSON {tên chỉ số: số}; số đã đổi từ chữ, "-" của TikTok → null). TikTok: tài khoản/campaign đủ 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Meta (20/10/2026): mọi trường Insights đã xin, danh sách action thành <trường>__<action_type> (vd actions__purchase, action_values__purchase, video_p100_watched_actions__video_view); reach, frequency, ctr, cpc, cpm, cpp, *_avg_*, *roas* KHÔNG cộng được qua dòng. Khoá tiền: spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*.';
COMMENT ON COLUMN qc_campaign_ngay.cap_nhat_luc IS 'Lần đồng bộ ghi/sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON TABLE qc_ad_ngay IS $$[Lớp] Raw
[Mục đích] Số quảng cáo TikTok / Meta theo ngày của từng quảng cáo (ad) có phân phối — top quảng cáo/video theo chi/hiển thị/xem/follow.
[Grain] 1 dòng = 1 ad × 1 ngày (múi giờ tài khoản)
[Khoá] PK: ad_id + ngay | Join: advertiser_id → tk_quang_cao.advertiser_id; campaign_id → qc_campaign_ngay.campaign_id
[Nguồn] TikTok for Business MCP report_integrated_get (BASIC, AUCTION_AD, chiều ad_id + stat_time_day; tên, nội dung, campaign/nhóm xin như chỉ số), bộ hẹn giờ tiktok-ads-dong-bo; Meta: Graph API GET act_<id>/insights (time_increment=1; khán giả: breakdowns, không theo ngày), bộ hẹn giờ meta-ads-dong-bo
[Phạm vi] Tài khoản tk_quang_cao đang đồng bộ, CHỈ ad có hiển thị trong cửa sổ đọc (đo 19/10/2026: 7.599 / 20.000 ad của MATEMADE MKT chạy trong 30 ngày) | Kênh TikTok Ads + Meta Ads (Facebook/Instagram, từ 20/10/2026) | Từ 90 ngày trước lần kết nối đầu
[Đã xử lý] Lấy ID ad xếp impressions giảm dần, dừng ở dòng 0 đầu tiên; lô ≤ 100 ID, ≤ 45 chỉ số mỗi lượt gọi; chi_so chỉ gồm 38 chỉ số chính (không đủ 100 như tài khoản/campaign); chỉ ngày có hiển thị hoặc chi > 0
[Refresh] Upsert hằng ngày 06:30 (TikTok) / 06:45 (Meta) giờ VN + lượt bấm tay "Đồng bộ ngay" (hôm nay + 2 ngày trước), đọc lại 7 ngày gần nhất; lần đầu 90 ngày
[Dùng khi] Top quảng cáo trong kỳ; nội dung quảng cáo nào kéo xem/follow
[Không dùng khi] Tổng tài khoản → dùng qc_tk_ngay; chiến dịch → dùng qc_campaign_ngay; khán giả → dùng qc_khan_gia
[Lưu ý] Bảng lớn nhất (hàng nghìn dòng mỗi ngày với tài khoản lớn). Chỉ số ngoài 38 chỉ số chính của ad → xem cấp campaign/tài khoản.$$;
COMMENT ON COLUMN qc_ad_ngay.advertiser_id IS 'Tài khoản quảng cáo của ad. FK → tk_quang_cao.advertiser_id.';
COMMENT ON COLUMN qc_ad_ngay.campaign_id IS 'Campaign chứa ad. Join: → qc_campaign_ngay.campaign_id. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.adgroup_id IS 'Nhóm quảng cáo chứa ad (TikTok ad group; Meta ad set). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.ad_id IS 'Mã quảng cáo (TikTok ad_id; Meta ad_id). Một phần PK.';
COMMENT ON COLUMN qc_ad_ngay.ngay IS 'Ngày số liệu theo múi giờ tài khoản (thường GMT+7). Một phần PK.';
COMMENT ON COLUMN qc_ad_ngay.ten_ad IS 'Tên quảng cáo lúc đọc (ad_name). Chuỗi rỗng khi TikTok không trả.';
COMMENT ON COLUMN qc_ad_ngay.noi_dung IS 'Chữ quảng cáo (TikTok ad_text), ≤ 2.000 ký tự; quảng cáo Spark Ads thường là chú thích bài gốc. Chuỗi rỗng khi không có; Meta luôn rỗng (không đọc nội dung sáng tạo).';
COMMENT ON COLUMN qc_ad_ngay.ten_campaign IS 'Tên campaign chứa ad lúc đọc (campaign_name). Chuỗi rỗng khi TikTok không trả.';
COMMENT ON COLUMN qc_ad_ngay.ten_nhom IS 'Tên nhóm quảng cáo lúc đọc (adgroup_name). Chuỗi rỗng khi TikTok không trả.';
COMMENT ON COLUMN qc_ad_ngay.chi IS 'Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy.';
COMMENT ON COLUMN qc_ad_ngay.hien_thi IS 'Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.reach IS 'Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.click IS 'Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.ket_qua IS 'Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.chuyen_doi IS 'Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.view_video IS 'Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.view_hai_giay IS 'Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.view_sau_giay IS 'Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.view_het IS 'Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.engaged_view IS 'Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.thich IS 'Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.binh_luan IS 'Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.chia_se IS 'Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.follow IS 'Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.vao_ho_so IS 'Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.mua_shop IS 'Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_ngay.gia_tri_mua_shop IS 'Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi, phân bổ mặc định của Meta). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN.';
COMMENT ON COLUMN qc_ad_ngay.chi_so IS 'MỌI chỉ số nền tảng trả cho dòng (JSON {tên chỉ số: số}; số đã đổi từ chữ, "-" của TikTok → null). TikTok: tài khoản/campaign đủ 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Meta (20/10/2026): mọi trường Insights đã xin, danh sách action thành <trường>__<action_type> (vd actions__purchase, action_values__purchase, video_p100_watched_actions__video_view); reach, frequency, ctr, cpc, cpm, cpp, *_avg_*, *roas* KHÔNG cộng được qua dòng. Khoá tiền: spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*.';
COMMENT ON COLUMN qc_ad_ngay.cap_nhat_luc IS 'Lần đồng bộ ghi/sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON TABLE qc_khan_gia IS $$[Lớp] Raw
[Mục đích] Khán giả quảng cáo TikTok / Meta của tài khoản (tuổi, giới tính, tỉnh/thành, nền tảng) trong cửa sổ 30 ngày — ai đang xem quảng cáo.
[Grain] 1 dòng = 1 tài khoản × 1 cửa sổ (tu..den) × 1 chiều × 1 giá trị của chiều
[Khoá] PK: advertiser_id + tu + den + chieu + gia_tri | Join: advertiser_id → tk_quang_cao.advertiser_id
[Nguồn] TikTok for Business MCP report_integrated_get (AUDIENCE, AUCTION_ADVERTISER, chiều advertiser_id + một chiều khán giả), bộ hẹn giờ tiktok-ads-dong-bo; Meta: Graph API GET act_<id>/insights (time_increment=1; khán giả: breakdowns, không theo ngày), bộ hẹn giờ meta-ads-dong-bo
[Phạm vi] Tài khoản đang đồng bộ có hiển thị trong 30 ngày | Kênh TikTok Ads + Meta Ads (Facebook/Instagram, từ 20/10/2026) | Từ lần kết nối đầu (19/10/2026)
[Đã xử lý] 13 chỉ số (chi, hiển thị, bấm, ctr, cpm, chuyển đổi, xem, xem 6 giây, thích, bình luận, chia sẻ, follow, vào hồ sơ); "-" → NULL; cột không có trong báo cáo khán giả (reach, engaged_view…) NULL
[Refresh] Mỗi 7 ngày mỗi tài khoản (trong lượt đồng bộ 06:30 TikTok / 06:45 Meta giờ VN), cửa sổ 30 ngày tới hết hôm qua; cửa sổ cũ giữ lại (lịch sử)
[Dùng khi] Phân bố hiển thị/xem theo tuổi, giới tính, tỉnh, nền tảng — lấy cửa sổ den mới nhất của từng tài khoản
[Không dùng khi] Số theo ngày → dùng qc_tk_ngay; theo chiến dịch → dùng qc_campaign_ngay
[Lưu ý] Các cửa sổ chồng nhau — KHÔNG cộng nhiều cửa sổ. province_id là mã vùng TikTok (GeoNames), -1 = không rõ.$$;
COMMENT ON COLUMN qc_khan_gia.advertiser_id IS 'Tài khoản quảng cáo. Một phần PK. FK → tk_quang_cao.advertiser_id.';
COMMENT ON COLUMN qc_khan_gia.tu IS 'Ngày đầu cửa sổ 30 ngày (múi giờ tài khoản). Một phần PK.';
COMMENT ON COLUMN qc_khan_gia.den IS 'Ngày cuối cửa sổ (múi giờ tài khoản, = hôm qua lúc đọc). Một phần PK.';
COMMENT ON COLUMN qc_khan_gia.chieu IS 'Chiều khán giả. Một phần PK. Giá trị: age, gender (TikTok + Meta), province_id, platform (TikTok: tỉnh, thiết bị), region, publisher_platform, platform_position (Meta, từ 20/10/2026).';
COMMENT ON COLUMN qc_khan_gia.gia_tri IS 'Giá trị của chiều (mã TikTok): age AGE_13_17…AGE_55_100, NONE; gender FEMALE, MALE, NONE; province_id mã vùng số (-1 không rõ); platform ANDROID, IPHONE, IPAD, WAP, UNKNOWN. Meta: age cùng mã TikTok tới 45–54, rồi 55-64, 65+; gender FEMALE, MALE, NONE; region tên vùng Meta (vd Ho Chi Minh City); publisher_platform facebook, instagram, messenger, audience_network, threads; platform_position "<nền tảng>/<vị trí>" (vd instagram/reels). Một phần PK.';
COMMENT ON COLUMN qc_khan_gia.chi IS 'Chi tiêu quảng cáo (spend), theo tiền tệ của tài khoản (tk_quang_cao.tien_te; 16 tài khoản TikTok đo 19/10/2026 và 20 tài khoản Meta đo 20/10/2026 đều VND), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy.';
COMMENT ON COLUMN qc_khan_gia.hien_thi IS 'Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.reach IS 'Người tiếp cận (reach) trong ĐÚNG phạm vi dòng (ngày / cửa sổ), người. Cộng nhiều dòng thì đếm trùng người — không phải reach duy nhất. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.click IS 'Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.ket_qua IS 'Kết quả theo mục tiêu tối ưu của chiến dịch (TikTok result), đơn vị tuỳ mục tiêu (lượt xem, hiển thị, chuyển đổi…); Meta luôn NULL. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.chuyen_doi IS 'Chuyển đổi, lượt: TikTok conversion (sự kiện tối ưu); Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — lấy tên đầu tiên có, không cộng các tên trùng nghĩa). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.view_video IS 'Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.view_hai_giay IS 'Lượt xem ≥ 2 giây (TikTok video_watched_2s; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.view_sau_giay IS 'Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.view_het IS 'Lượt xem hết video (TikTok video_views_p100; Meta video_p100_watched_actions), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.engaged_view IS 'Lượt xem tương tác, lượt: TikTok engaged_view (xem ≥ 6 giây hoặc tương tác trong 1 ngày); Meta ThruPlay (video_thruplay_watched_actions: xem hết hoặc ≥ 15 giây). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.thich IS 'Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.binh_luan IS 'Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.chia_se IS 'Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.follow IS 'Lượt theo dõi từ quảng cáo, lượt: TikTok follows (theo dõi kênh); Meta action like (thích Trang). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.vao_ho_so IS 'Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.mua_shop IS 'Lượt mua trong TikTok Shop gán cho quảng cáo (TikTok onsite_shopping; Meta NULL — lượt mua Meta ở chuyen_doi), lượt mua. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia.gia_tri_mua_shop IS 'Doanh thu gán cho quảng cáo, theo tiền tệ tài khoản: TikTok Shop (total_onsite_shopping_value, giá khách trả); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi, phân bổ mặc định của Meta). 0 khi dòng có phân phối mà không có mua. CHỈ SỐ TIỀN.';
COMMENT ON COLUMN qc_khan_gia.chi_so IS 'MỌI chỉ số nền tảng trả cho dòng (JSON {tên chỉ số: số}; số đã đổi từ chữ, "-" của TikTok → null). TikTok: tài khoản/campaign đủ 100 tên hợp lệ; ad: 38 chỉ số + thuộc tính; khán giả: 13. Meta (20/10/2026): mọi trường Insights đã xin, danh sách action thành <trường>__<action_type> (vd actions__purchase, action_values__purchase, video_p100_watched_actions__video_view); reach, frequency, ctr, cpc, cpm, cpp, *_avg_*, *roas* KHÔNG cộng được qua dòng. Khoá tiền: spend, cpm, cpc, cpp, cost_per_*, *_value, action_values__*, *roas*, *budget*.';
COMMENT ON COLUMN qc_khan_gia.cap_nhat_luc IS 'Lần đồng bộ ghi/sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON TABLE qc_ad_kenh IS $$[Lớp] Raw
[Mục đích] Kênh đăng của từng quảng cáo (ad) — danh tính quảng cáo chạy dưới tên: TikTok identity (tài khoản chính chủ, KOC / Spark Ads), Meta Trang Facebook (+ Instagram đi kèm) — để tách số quảng cáo theo kênh.
[Grain] 1 dòng = 1 ad của 1 tài khoản quảng cáo
[Khoá] PK: advertiser_id + ad_id | Join: (advertiser_id, ad_id) → qc_ad_ngay; (nen_tang, kenh_id) → qc_kenh; (nen_tang, kenh_phu_id) → qc_kenh (Instagram)
[Nguồn] TikTok for Business MCP tool_execute ad_get (trường identity_id, identity_type, tiktok_item_id), bộ hẹn giờ tiktok-ads-dong-bo; Meta Graph API GET act_<id>/ads (creative.actor_id, object_story_spec.page_id, instagram_user_id), bộ hẹn giờ meta-ads-dong-bo
[Phạm vi] Ad có phân phối (có dòng qc_ad_ngay) của tài khoản đang đồng bộ | Kênh TikTok Ads + Meta Ads | Từ 22/10/2026 (đọc lùi mọi ad đã có số, chi nhiều trước)
[Đã xử lý] Một lần mỗi ad (kênh của ad không đổi); ≤ 300 lượt TikTok / 100 lượt Meta mỗi lần đồng bộ; ad nền tảng không trả → kenh_id NULL, loai khong_thay, hỏi lại sau 7 ngày. Meta: kênh = Trang (actor_id, rồi page_id), không Trang mà có Instagram → kênh là Instagram
[Refresh] Thêm dòng trong lượt đồng bộ hằng ngày 06:30 (TikTok) / 06:45 (Meta) giờ VN, sau phần số; lượt nhanh / tức thì không đọc kênh
[Dùng khi] Số quảng cáo theo kênh đăng (join qc_ad_ngay theo advertiser_id + ad_id); bao nhiêu chi tiêu chạy qua KOC / Spark Ads so với kênh chính chủ
[Không dùng khi] Tên kênh → dùng qc_kenh; số theo ngày của ad → dùng qc_ad_ngay
[Lưu ý] Ad chưa có dòng (chưa tới lượt đọc) và dòng kenh_id NULL gộp vào "Chưa xác định" trên trang. Một Trang Meta có thể đi với nhiều Instagram — kenh_phu_id là của từng ad.$$;
COMMENT ON COLUMN qc_ad_kenh.advertiser_id IS 'Tài khoản quảng cáo của ad (TikTok chuỗi số; Meta act_<số>). Một phần PK. FK → tk_quang_cao.advertiser_id.';
COMMENT ON COLUMN qc_ad_kenh.ad_id IS 'Mã quảng cáo (TikTok ad_id; Meta ad id). Một phần PK. Join: → qc_ad_ngay.ad_id.';
COMMENT ON COLUMN qc_ad_kenh.nen_tang IS 'Nền tảng: tiktok | meta. Không NULL.';
COMMENT ON COLUMN qc_ad_kenh.kenh_id IS 'Mã kênh đăng: TikTok identity_id (chuỗi số hoặc UUID); Meta id Trang Facebook (hoặc id Instagram khi ad không có Trang). Join: → qc_kenh.kenh_id. NULL khi nền tảng không trả ad hoặc ad không có danh tính (loai khong_thay).';
COMMENT ON COLUMN qc_ad_kenh.loai IS 'Loại kênh. TikTok identity_type: AUTH_CODE (bài KOC uỷ quyền bằng mã — Spark Ads), BC_AUTH_TT (tài khoản TikTok gắn Business Center — chính chủ hoặc KOC), TT_USER (tài khoản TikTok chính chủ), CUSTOMIZED_USER (danh tính tuỳ chỉnh, không phải tài khoản TikTok). Meta: page | instagram. khong_thay: nền tảng không trả ad. Không NULL.';
COMMENT ON COLUMN qc_ad_kenh.kenh_phu_id IS 'Kênh đi kèm: Meta id tài khoản Instagram (instagram_user_id) của ad chạy dưới Trang. NULL với TikTok và khi ad Meta không gắn Instagram.';
COMMENT ON COLUMN qc_ad_kenh.bai_id IS 'Mã bài gốc của quảng cáo: TikTok tiktok_item_id (video), Meta effective_instagram_media_id. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_ad_kenh.cap_nhat_luc IS 'Lần đồng bộ ghi/sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery; dòng khong_thay hỏi lại khi cũ hơn 7 ngày.';
COMMENT ON TABLE qc_kenh IS $$[Lớp] Dim
[Mục đích] Tên kênh đăng của quảng cáo (TikTok identity, Trang Facebook, tài khoản Instagram) để hiện trên trang Quảng cáo.
[Grain] 1 dòng = 1 kênh của 1 nền tảng
[Khoá] PK: nen_tang + kenh_id | Join: (nen_tang, kenh_id) ← qc_ad_kenh.kenh_id / qc_ad_kenh.kenh_phu_id
[Nguồn] TikTok for Business MCP identity_get (display_name, username), bộ hẹn giờ tiktok-ads-dong-bo; Meta Graph API GET /<id>?fields=name (Trang) | fields=username (Instagram) — cần quyền pages_read_engagement, bộ hẹn giờ meta-ads-dong-bo
[Phạm vi] TikTok: MỌI danh tính của tài khoản có kênh chưa có tên (đo 22/10/2026: 1.951 danh tính ở MATEMADE MKT) | Meta: Trang / Instagram gặp trong qc_ad_kenh | Từ 22/10/2026
[Đã xử lý] Bỏ trùng theo identity_id; tên trống không ghi đè tên đã biết; ≤ 200 ký tự
[Refresh] Upsert trong lượt đồng bộ hằng ngày khi có kênh chưa có tên (TikTok một lượt identity_get mỗi tài khoản; Meta ≤ 50 lượt mỗi lần, hỏi lại kênh chưa tên sau 1 ngày)
[Dùng khi] Hiện tên kênh cạnh số theo kênh (join từ qc_ad_kenh)
[Không dùng khi] Số theo kênh → dùng qc_ad_kenh join qc_ad_ngay; kênh lắng nghe mạng xã hội → dùng nguon
[Lưu ý] Meta: token thiếu pages_read_engagement thì không có dòng / ten NULL — trang hiện "Page <id>" / "IG <id>".$$;
COMMENT ON COLUMN qc_kenh.nen_tang IS 'Nền tảng: tiktok | meta. Một phần PK.';
COMMENT ON COLUMN qc_kenh.kenh_id IS 'Mã kênh: TikTok identity_id; Meta id Trang hoặc id tài khoản Instagram. Một phần PK. Join: ← qc_ad_kenh.kenh_id, qc_ad_kenh.kenh_phu_id.';
COMMENT ON COLUMN qc_kenh.loai IS 'Loại kênh: TikTok identity_type (AUTH_CODE, BC_AUTH_TT, TT_USER, CUSTOMIZED_USER); Meta page | instagram. NULL khi chưa biết.';
COMMENT ON COLUMN qc_kenh.ten IS 'Tên hiển thị: TikTok display_name; Meta tên Trang. NULL khi nền tảng không trả hoặc token Meta thiếu pages_read_engagement.';
COMMENT ON COLUMN qc_kenh.username IS 'Tên người dùng không @: TikTok username (thường NULL với AUTH_CODE); Meta username Instagram. NULL khi không có.';
COMMENT ON COLUMN qc_kenh.cap_nhat_luc IS 'Lần đồng bộ ghi/sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON TABLE yeu_cau_tuc_thi IS $$[Lớp] Raw
[Mục đích] Sổ yêu cầu số TỨC THÌ của Mark (đọc số quảng cáo mới, cào chỉ số bài / kênh, mở lượt quét lắng nghe theo yêu cầu) — hàng chờ cho bộ nghe quảng cáo, đếm trần, dấu vết ai xin gì.
[Grain] 1 dòng = 1 yêu cầu Mark gửi (kể cả bị từ chối vì trần)
[Khoá] PK: id | Join: ben → don_vi.ma; du_an → du_an.ma; tai_khoan[] → tk_quang_cao.advertiser_id
[Nguồn] Mark (tool lay_so_tuc_thi, role mark) thêm dòng; bộ nghe tiktok-ads-nghe / meta-ads-nghe và bộ hẹn giờ *-ads-yeu-cau (role lang_nghe_web) nhận + kết thúc dòng quảng cáo
[Phạm vi] Mọi người có vai trò ở ít nhất một bên, chỉ trong phạm vi bên của họ | Kênh TikTok Ads, Meta Ads, Apify (bài, kênh, quét) | Từ 20/10/2026
[Đã xử lý] Tài khoản đã lọc theo bên người hỏi trước khi ghi; khoảng ngày quảng cáo đã kẹp ≤ 7 ngày gồm hôm nay; dòng chờ quá 15 phút → bo_qua, chạy quá 60 phút → loi
[Refresh] Theo yêu cầu (thời gian thực); dòng không bao giờ xoá
[Dùng khi] Biết Mark đã xin đọc gì, lúc nào, cho ai; đếm trần mỗi người / mỗi bên / mỗi giờ; soát chi phí Apify của lượt cào tức thì
[Không dùng khi] Số quảng cáo → dùng qc_tk_ngay; lượt quét lắng nghe và chi phí tháng → dùng luot_quet; ai sửa gì trên dashboard → dùng nhat_ky
[Lưu ý] Có email người hỏi — KHÔNG đẩy lên BigQuery. Mọi yêu cầu có một dòng nhat_ky (hanh_dong mark_real_time) do trigger ghi; trạng thái lúc thêm do trigger đặt; RLS: role mark chỉ sửa dòng bài/kênh/quét.$$;
COMMENT ON COLUMN yeu_cau_tuc_thi.id IS 'Mã yêu cầu tự tăng. PK.';
COMMENT ON COLUMN yeu_cau_tuc_thi.loai IS 'Loại: quang_cao (đọc số TikTok/Meta Ads mới — bộ nghe chạy), bai (cào chỉ số link bài), kenh (cào hồ sơ + bài mới của kênh), quet (mở lượt quét lắng nghe /theodoi).';
COMMENT ON COLUMN yeu_cau_tuc_thi.nguoi_hoi IS 'Email công ty của người hỏi Mark (đã xác thực qua chat riêng Lark / web console). Dữ liệu cá nhân — không đẩy BigQuery.';
COMMENT ON COLUMN yeu_cau_tuc_thi.ben IS 'Bên (don_vi.ma) của phạm vi yêu cầu; NULL khi nhiều bên hoặc dữ liệu công khai không thuộc bên nào.';
COMMENT ON COLUMN yeu_cau_tuc_thi.nha_cung_cap IS 'Chỉ loai quang_cao: tiktok_ads hoặc meta_ads (mỗi nhà cung cấp một dòng). NULL với loại khác.';
COMMENT ON COLUMN yeu_cau_tuc_thi.tai_khoan IS 'Chỉ loai quang_cao: mã tài khoản quảng cáo (advertiser_id / act_…) trong phạm vi người hỏi cần đọc lại. Mảng rỗng với loại khác.';
COMMENT ON COLUMN yeu_cau_tuc_thi.tu IS 'Ngày đầu khoảng cần đọc lại (giờ VN; bộ nghe kẹp theo múi giờ tài khoản, tối đa 7 ngày gồm hôm nay). NULL với bài/kênh.';
COMMENT ON COLUMN yeu_cau_tuc_thi.den IS 'Ngày cuối khoảng cần đọc lại (≤ hôm nay). NULL với bài/kênh.';
COMMENT ON COLUMN yeu_cau_tuc_thi.du_an IS 'Chỉ loai quet: mã dự án được quét (du_an.ma). NULL với loại khác.';
COMMENT ON COLUMN yeu_cau_tuc_thi.so_muc IS 'Số mục của yêu cầu: link bài (bai), kênh (kenh), nguồn (quet), tài khoản (quang_cao). Dùng đếm trần mỗi người mỗi ngày.';
COMMENT ON COLUMN yeu_cau_tuc_thi.chi_tiet IS 'Chi tiết JSON: link / kênh đã xin, nền tảng, lý do từ chối, mã việc nền của lượt quét. Không chứa token.';
COMMENT ON COLUMN yeu_cau_tuc_thi.trang_thai IS 'cho (đợi bộ nghe), dang_chay, xong, loi, bo_qua (quá hạn / chạm trần phía dịch vụ / lượt khác), tu_choi (Mark chặn vì trần, quyền, ngân sách — không tốn gì, không tính trần).';
COMMENT ON COLUMN yeu_cau_tuc_thi.uoc_usd IS 'Chi phí ước tính lúc xin (USD, Apify), NULL với quảng cáo (API nền tảng miễn phí).';
COMMENT ON COLUMN yeu_cau_tuc_thi.chi_phi_usd IS 'Chi phí Apify thật của yêu cầu (USD, cộng usageTotalUsd các run), NULL khi chưa biết / không tốn tiền.';
COMMENT ON COLUMN yeu_cau_tuc_thi.so_dong IS 'Chỉ loai quang_cao: số dòng qc_* lượt đọc đã ghi/cập nhật. NULL khi chưa chạy.';
COMMENT ON COLUMN yeu_cau_tuc_thi.so_tk_ok IS 'Chỉ loai quang_cao: số tài khoản lượt đọc ĐỌC ĐƯỢC (so với so_muc = số tài khoản xin). Nhỏ hơn so_muc = cập nhật một phần; 0 → trạng thái loi/bo_qua, không bao giờ xong. NULL khi chưa chạy.';
COMMENT ON COLUMN yeu_cau_tuc_thi.loi IS 'Lý do lỗi / bỏ qua / từ chối (đã bỏ token và URL), ≤ 500 ký tự. NULL khi ổn.';
COMMENT ON COLUMN yeu_cau_tuc_thi.tao_luc IS 'Lúc Mark ghi yêu cầu (UTC).';
COMMENT ON COLUMN yeu_cau_tuc_thi.bat_dau_luc IS 'Lúc lượt đọc / cào bắt đầu (UTC). Các yêu cầu gộp vào cùng một lượt có cùng mốc.';
COMMENT ON COLUMN yeu_cau_tuc_thi.xong_luc IS 'Lúc kết thúc (UTC) — Mark nói "số cập nhật lúc HH:MM" theo mốc này.';
COMMENT ON TABLE yeu_cau_sheet_qc IS $$[Lớp] Raw
[Mục đích] Sổ yêu cầu xuất số quảng cáo TikTok / Meta Ads thành Lark Sheet từ trang Quảng cáo — hàng chờ cho bộ nghe qc-sheet-nghe (Mark) và dấu vết ai xuất phạm vi nào, link nào.
[Grain] 1 dòng = 1 lần quản trị viên bấm "Xuất Lark Sheet theo bộ lọc này" (trước 22/10/2026: "Tạo Sheet") hoặc 1 lần người có quyền nhờ Mark xuất Sheet (từ 22/10/2026, nguon = mark); đã qua trần
[Khoá] PK: id | Join: ben → don_vi.ma (trừ tat_ca, chua_gan); tk → tk_quang_cao.advertiser_id
[Nguồn] Dashboard social.hapas.vn (role lang_nghe_web) hoặc Mark (tool xuat_sheet_qc, role mark) thêm dòng; bộ nghe qc-sheet-nghe (role mark, xuat_sheet_qc.py) nhận, dựng Sheet và ghi kết quả
[Phạm vi] Dòng web: chỉ quản trị viên; dòng Mark: người có quyền ở bên (Sheet không cột tiền khi không xem tiền) | Kênh TikTok Ads, Meta Ads | Từ 20/10/2026
[Đã xử lý] Trạng thái + cột kết quả lúc thêm do trigger đặt; trần (1 yêu cầu đang chờ, 4/người/giờ, 30/giờ toàn hệ thống) do trigger kiểm; email chữ thường; chờ / đang tạo quá 30 phút → loi
[Refresh] Theo yêu cầu (thời gian thực); dòng không bao giờ xoá
[Dùng khi] Biết ai đã xuất Sheet quảng cáo nào, phạm vi nào, lúc nào, link nào; soát lỗi xuất Sheet
[Không dùng khi] Số quảng cáo → dùng qc_tk_ngay, qc_campaign_ngay, qc_ad_ngay; yêu cầu đọc số mới của Mark → dùng yeu_cau_tuc_thi
[Lưu ý] Có email người yêu cầu và link Sheet (Sheet riêng tư, chỉ người yêu cầu được xem) — KHÔNG đẩy lên BigQuery. RLS: web chỉ thấy / thêm dòng của chính người đăng nhập (lang_nghe.nguoi); mark chỉ thêm dòng nguon = mark, chỉ mark sửa kết quả.$$;
COMMENT ON COLUMN yeu_cau_sheet_qc.id IS 'Mã yêu cầu tự tăng. PK. Cũng là payload của pg_notify(qc_sheet).';
COMMENT ON COLUMN yeu_cau_sheet_qc.nguoi_hoi IS 'Email công ty (chữ thường) của quản trị viên bấm Tạo Sheet, hoặc của người hỏi Mark (nguon = mark) — Sheet chia sẻ quyền xem cho email này, Mark nhắn link tới email này. Dữ liệu cá nhân — không đẩy BigQuery.';
COMMENT ON COLUMN yeu_cau_sheet_qc.ben IS 'Bên của bộ lọc trang: mã don_vi, tat_ca (mọi bên) hoặc chua_gan (tài khoản chưa gán bên).';
COMMENT ON COLUMN yeu_cau_sheet_qc.nen_tang IS 'Nền tảng của bộ lọc trang: tat_ca, tiktok hoặc meta.';
COMMENT ON COLUMN yeu_cau_sheet_qc.tk IS 'Một tài khoản quảng cáo của bộ lọc (advertiser_id / act_…); NULL = mọi tài khoản của bên + nền tảng. Từ 22/10/2026 danh sách ở tk_ds (một mã thì ghi cả cột này); bộ nghe đọc tk_ds trước, rồi tk (dòng cũ).';
COMMENT ON COLUMN yeu_cau_sheet_qc.tk_ds IS 'Các tài khoản quảng cáo đã chọn (advertiser_id / act_…, tối đa 200, trigger kiểm); NULL = mọi tài khoản của bên + nền tảng. Từ 22/10/2026; dòng cũ NULL (xem tk).';
COMMENT ON COLUMN yeu_cau_sheet_qc.tim IS 'Chữ tìm theo tên của bảng chiến dịch / quảng cáo (≤ 100 ký tự, so khớp bỏ dấu); NULL = không lọc tên. Từ 22/10/2026.';
COMMENT ON COLUMN yeu_cau_sheet_qc.cd IS 'Mã chiến dịch của bộ lọc bảng (chỉ chiến dịch đó + quảng cáo của nó); NULL = mọi chiến dịch. Từ 22/10/2026.';
COMMENT ON COLUMN yeu_cau_sheet_qc.sap IS 'Cột xếp tab chiến dịch / quảng cáo: chi, hien_thi, cpm, click, ctr, view, tuong_tac, follow, roas; NULL (dòng cũ) = chi. Từ 22/10/2026.';
COMMENT ON COLUMN yeu_cau_sheet_qc.chieu IS 'Chiều xếp: giam (cao → thấp) hoặc tang; NULL (dòng cũ) = giam. Từ 22/10/2026.';
COMMENT ON COLUMN yeu_cau_sheet_qc.nguon IS 'Dòng từ đâu: web (nút trên trang Quảng cáo, chỉ quản trị viên — mặc định, web không ghi được cột này) hoặc mark (người hỏi Mark trên Lark nhờ xuất Sheet, tool xuat_sheet_qc). Từ 22/10/2026; dòng cũ = web.';
COMMENT ON COLUMN yeu_cau_sheet_qc.tu IS 'Ngày đầu khoảng xuất (ngày theo múi giờ tài khoản, như qc_tk_ngay.ngay).';
COMMENT ON COLUMN yeu_cau_sheet_qc.den IS 'Ngày cuối khoảng xuất; tối đa 400 ngày (CHECK).';
COMMENT ON COLUMN yeu_cau_sheet_qc.trang_thai IS 'cho (đợi bộ nghe), dang_tao, xong (có sheet_url), loi (xem loi).';
COMMENT ON COLUMN yeu_cau_sheet_qc.tieu_de IS 'Tên file Sheet bộ nghe đặt (vd "TikTok Ads · HAPAS · 01/10–19/10/2026"). NULL khi chưa tạo.';
COMMENT ON COLUMN yeu_cau_sheet_qc.sheet_url IS 'Link Lark Sheet (riêng tư: chia sẻ link đóng, chỉ người yêu cầu được xem). NULL khi chưa xong / lỗi.';
COMMENT ON COLUMN yeu_cau_sheet_qc.so_dong IS 'Số dòng từng tab JSON {ngay, chien_dich, quang_cao, tong_chien_dich, tong_quang_cao}: tong_* lớn hơn số dòng = tab bị cắt ở trần dòng.';
COMMENT ON COLUMN yeu_cau_sheet_qc.loi IS 'Lý do lỗi cho người yêu cầu (đã bỏ token / URL), ≤ 300 ký tự. NULL khi ổn.';
COMMENT ON COLUMN yeu_cau_sheet_qc.loi_noi_bo IS 'Chi tiết lỗi kỹ thuật cho vận hành (loại lỗi + chữ lỗi đã che token), ≤ 500 ký tự. Role lang_nghe_web không đọc được cột này.';
COMMENT ON COLUMN yeu_cau_sheet_qc.da_nhan_tin IS 'Mark đã nhắn link (hoặc lỗi) cho người yêu cầu trên Lark chưa.';
COMMENT ON COLUMN yeu_cau_sheet_qc.tao_luc IS 'Lúc bấm Tạo Sheet (UTC, trigger đặt).';
COMMENT ON COLUMN yeu_cau_sheet_qc.bat_dau_luc IS 'Lúc bộ nghe nhận yêu cầu (UTC).';
COMMENT ON COLUMN yeu_cau_sheet_qc.xong_luc IS 'Lúc xong / lỗi (UTC).';
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
-- Phân quyền theo bên (19/10/2026): tool chỉ trả số dự án của các bên người hỏi được xem
-- (`dashboard.kho.quyen_cua` — đọc nguoi_xem.la_quan_tri + quyen(email, don_vi, vai_tro));
-- cột du_an.don_vi: role mark đã được đọc cả bảng du_an (cấp ở trên).
GRANT SELECT (la_quan_tri) ON nguoi_xem TO mark;
-- Bộ nghe Lark Sheet quảng cáo (`xuat_sheet_qc`, 21/10/2026): chia quyền xem + nhắn link theo
-- union_id Lark của người bấm (`dashboard.kho.union_id_cua`) — email đăng nhập không trùng email Lark.
GRANT SELECT (lark_union_id) ON nguoi_xem TO mark;
GRANT SELECT (email, don_vi, vai_tro) ON quyen TO mark;
GRANT SELECT ON don_vi TO mark;

-- Quyền của dashboard: quản lý cấu hình + người xem, đọc mọi thứ, ghi nhật ký và mốc đồng bộ.
BEGIN;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lang_nghe_web;
-- Xuất Lark Sheet (20/10/2026): thu NGAY trong cùng giao dịch quyền đọc cả bảng vừa cấp ở trên — web
-- không bao giờ có lúc nào đọc được loi_noi_bo; quyền theo cột cấp lại ở khối cuối file.
REVOKE SELECT ON yeu_cau_sheet_qc FROM lang_nghe_web;
COMMIT;
GRANT INSERT, UPDATE, DELETE ON du_an, nguon, nguoi_xem TO lang_nghe_web;
-- 19/10/2026: quyền theo bên (thêm/đổi/bỏ) + tạo bên (không xoá bên).
GRANT INSERT, UPDATE, DELETE ON quyen TO lang_nghe_web;
GRANT INSERT, UPDATE ON don_vi TO lang_nghe_web;
GRANT UPDATE (trang_thai, xu_ly_boi, xu_ly_luc) ON de_xuat TO lang_nghe_web;
GRANT INSERT ON nhat_ky TO lang_nghe_web;
GRANT INSERT, UPDATE ON dong_bo_bq TO lang_nghe_web;
GRANT USAGE ON SEQUENCE nguon_id_seq, nhat_ky_id_seq TO lang_nghe_web;
GRANT INSERT, UPDATE, DELETE ON lich_quet TO lang_nghe_web;
GRANT USAGE ON SEQUENCE lich_quet_id_seq TO lang_nghe_web;

-- TikTok Ads (19/10/2026): Mark chỉ ĐỌC số quảng cáo (hỏi đáp `hoi_dashboard` phần quang_cao, chỉ
-- tài khoản của bên người hỏi) và CÁC CỘT KHÔNG BÍ MẬT của ket_noi_ngoai (nhắc quản trị viên gia
-- hạn 30 ngày) — KHÔNG BAO GIỜ cột token (access_token_enc, refresh_token_enc) hay client_id,
-- email người cấp. REVOKE trước: thu quyền cả bảng nếu bản nháp nào lỡ cấp, rồi cấp theo cột.
REVOKE ALL ON ket_noi_ngoai FROM mark;
GRANT SELECT (nha_cung_cap, loai, trang_thai, refresh_het_luc, goi_ok_luc, loi_cuoi)
  ON ket_noi_ngoai TO mark;
GRANT SELECT ON tk_quang_cao, qc_tk_ngay, qc_campaign_ngay, qc_ad_ngay, qc_khan_gia TO mark;
-- Dashboard + bộ hẹn giờ (cùng user lang_nghe_web): kết nối, tài khoản, số quảng cáo — đọc/ghi;
-- không xoá số (DELETE không cấp). Đọc đã có ở GRANT SELECT ON ALL TABLES phía trên.
GRANT INSERT, UPDATE ON ket_noi_ngoai, tk_quang_cao, qc_tk_ngay, qc_campaign_ngay, qc_ad_ngay,
  qc_khan_gia TO lang_nghe_web;
-- Kênh đăng (22/10/2026): như qc_* — bộ hẹn giờ (lang_nghe_web) thêm/sửa, không xoá; dashboard đọc qua
-- GRANT SELECT ON ALL TABLES phía trên; Mark chỉ đọc (không cột tiền, không bí mật).
GRANT INSERT, UPDATE ON qc_ad_kenh, qc_kenh TO lang_nghe_web;
GRANT SELECT ON qc_ad_kenh, qc_kenh TO mark;

-- Số tức thì (20/10/2026, dashboard/kho_tuc_thi.py): Mark thêm + đọc yêu cầu, chỉ sửa cột kết quả
-- (yêu cầu bài / kênh / quét của chính nó), KHÔNG xoá. Nhật ký: Mark chỉ THÊM dòng nhat_ky (không
-- đọc, không sửa) — mỗi yêu cầu một dòng "mark_real_time". Bộ nghe + bộ hẹn giờ (lang_nghe_web)
-- nhận / kết thúc dòng quảng cáo. Không bảng quảng cáo nào thêm quyền ghi cho mark.
-- Soát 20/10/2026 M5: INSERT chỉ các cột yêu cầu (trạng thái, mốc giờ, kết quả do trigger đặt);
-- UPDATE chỉ cột kết quả và CHỈ dòng bài/kênh/quét (RLS ở trên); KHÔNG quyền nào trên nhat_ky
-- (nhật ký do trigger SECURITY DEFINER ghi). REVOKE trước: thu quyền cả bảng / nhật ký của bản
-- nháp trước, rồi cấp lại theo cột.
-- Một giao dịch (soát L-d): chạy lại file này, Mark không bao giờ thấy khoảng trống quyền giữa
-- REVOKE và GRANT.
BEGIN;
REVOKE INSERT, UPDATE ON yeu_cau_tuc_thi FROM mark;
REVOKE INSERT ON nhat_ky FROM mark;
REVOKE USAGE ON SEQUENCE nhat_ky_id_seq FROM mark;
GRANT SELECT ON yeu_cau_tuc_thi TO mark;
GRANT INSERT (loai, nguoi_hoi, ben, nha_cung_cap, tai_khoan, tu, den, du_an, so_muc, chi_tiet,
              uoc_usd, loi) ON yeu_cau_tuc_thi TO mark;
GRANT UPDATE (trang_thai, chi_phi_usd, loi, chi_tiet, xong_luc) ON yeu_cau_tuc_thi TO mark;
GRANT USAGE ON SEQUENCE yeu_cau_tuc_thi_id_seq TO mark;
GRANT SELECT, UPDATE ON yeu_cau_tuc_thi TO lang_nghe_web;
COMMIT;

-- Xuất Lark Sheet quảng cáo (20/10/2026, dashboard/kho_sheet_qc.py + xuat_sheet_qc.py): web THÊM đúng
-- các cột phạm vi + ĐỌC các cột trạng thái (không loi_noi_bo), KHÔNG sửa / xoá; Mark ĐỌC + SỬA cột
-- kết quả, KHÔNG thêm / xoá. RLS ở trên giới hạn dòng (web: chỉ dòng của người đăng nhập). REVOKE
-- trước (thu quyền cả bảng — GRANT SELECT ON ALL TABLES phía trên vừa cấp cho web), rồi cấp theo
-- cột; một giao dịch: chạy lại file này không có khoảng trống quyền.
BEGIN;
REVOKE ALL ON yeu_cau_sheet_qc FROM mark, lang_nghe_web;
REVOKE ALL ON SEQUENCE yeu_cau_sheet_qc_id_seq FROM mark, lang_nghe_web;
GRANT SELECT (id, nguoi_hoi, ben, nen_tang, tk, tk_ds, tu, den, tim, cd, sap, chieu, trang_thai,
              tieu_de, sheet_url, so_dong, loi, da_nhan_tin, tao_luc, bat_dau_luc, xong_luc)
  ON yeu_cau_sheet_qc TO lang_nghe_web;
GRANT INSERT (nguoi_hoi, ben, nen_tang, tk, tk_ds, tu, den, tim, cd, sap, chieu)
  ON yeu_cau_sheet_qc TO lang_nghe_web;
GRANT USAGE ON SEQUENCE yeu_cau_sheet_qc_id_seq TO lang_nghe_web;
GRANT SELECT ON yeu_cau_sheet_qc TO mark;
GRANT UPDATE (trang_thai, tieu_de, sheet_url, so_dong, loi, loi_noi_bo, da_nhan_tin, bat_dau_luc,
              xong_luc) ON yeu_cau_sheet_qc TO mark;
-- 22/10/2026 (tool xuat_sheet_qc): Mark THÊM đúng các cột yêu cầu + nguon (RLS sheet_qc_them_mark buộc
-- nguon = 'mark'); trạng thái / kết quả / mốc giờ do trigger đặt như dòng web. Không DELETE.
GRANT INSERT (nguoi_hoi, ben, nen_tang, tk, tk_ds, tu, den, tim, cd, sap, chieu, nguon)
  ON yeu_cau_sheet_qc TO mark;
GRANT USAGE ON SEQUENCE yeu_cau_sheet_qc_id_seq TO mark;
COMMIT;
