-- Lưu lượng truy cập + sở thích TikTok (28/10/2026, chủ dự án chốt) — CHỈ phần thay đổi của schema.sql
-- ngày này: bảng tên sở thích qc_so_thich + hai cột phiên bản bộ chiều tk_quang_cao.khan_gia_bo_chieu /
-- khan_gia_cd_bo_chieu + CHECK chiều khán giả (qc_khan_gia, qc_khan_gia_cd) nhận interest_category +
-- trigger yêu cầu Sheet nhận cột xếp cpc / lpv + mô tả 11 nhãn + quyền. schema.sql đã có đúng các lệnh
-- này (chạy cả file vẫn được); file này để áp riêng phần mới, KHÔNG có lệnh đổi DB — DB đích chọn bằng
-- -d (thử trên DB tạm: đổi -d, file không tự nhảy sang lang_nghe).
--
--   sudo -u postgres env PGOPTIONS='-c lock_timeout=5s' psql -v ON_ERROR_STOP=1 -d lang_nghe \
--     < deploy/lang-nghe/2026-10-28-qc-luu-luong.sql
--
-- Cần role postgres (superuser): SET ROLE lang_nghe_chu (chủ bảng, NOLOGIN — ALTER, CREATE, thay hàm
-- trigger) + GRANT. Chạy TRƯỚC khi bật mã mới (mã mới đọc hai cột mới của tk_quang_cao và ghi chiều
-- interest_category — thiếu thì trang Quảng cáo và đồng bộ quảng cáo lỗi). Chạy lại không sao.
-- HAI giao dịch (soát khoá):
--   (1) mọi thay đổi danh mục — MỘT giao dịch: CREATE TABLE qc_so_thich (bảng mới, không FK — không khoá
--       bảng nào khác); ADD COLUMN tk_quang_cao CHỈ khi cột chưa có (information_schema) — xin ACCESS
--       EXCLUSIVE (cột NULL không DEFAULT — chỉ đổi danh mục, tức thì); DROP CONSTRAINT + ADD CONSTRAINT
--       … NOT VALID trên qc_khan_gia, qc_khan_gia_cd CHỈ khi CHECK tên chuẩn <bảng>_chieu_check chưa có
--       interest_category — xin ACCESS EXCLUSIVE (chặn cả đọc) nhưng KHÔNG quét bảng (NOT VALID chỉ kiểm
--       dòng mới), nhả khi COMMIT, chừng mili giây. Bảng có CHECK chieu tên lạ → RAISE, không xoá gì.
--       CREATE OR REPLACE FUNCTION không khoá bảng. Mark / dashboard / bộ đồng bộ đang giữ khoá thì
--       lock_timeout 5 giây → lỗi, KHÔNG treo, rollback cả giao dịch (CHECK cũ còn nguyên) — chạy lại
--       sau (tránh 06:25–07:30 giờ VN). Trong lúc chờ khoá (≤ 5 giây) truy vấn mới vào ba bảng này xếp
--       hàng sau nó.
--       Chạy LẠI (đã áp): không câu nào xin ACCESS EXCLUSIVE — cột và CHECK đã đúng thì bỏ qua; còn
--       COMMENT (SHARE UPDATE EXCLUSIVE), CREATE INDEX IF NOT EXISTS (SHARE trên qc_so_thich), GRANT,
--       CREATE OR REPLACE FUNCTION — không chặn đọc / ghi các bảng đang dùng.
--   (2) VALIDATE CONSTRAINT (riêng giao dịch, SAU COMMIT của (1)): quét hai bảng khán giả, khoá
--       SHARE UPDATE EXCLUSIVE — đọc / ghi vẫn chạy song song; dòng cũ luôn đạt (CHECK mới rộng hơn
--       CHECK cũ). Gộp vào (1) thì ACCESS EXCLUSIVE bị giữ suốt lúc quét — vì vậy tách.
--       Lỗi / bị ngắt ở bước này: CHECK vẫn chặn dòng mới (chỉ chưa đánh dấu đã kiểm) — chạy lại file.

\set ON_ERROR_STOP on

-- Chặn chạy nhầm DB (quên -d → DB postgres): DB đích phải có bảng quảng cáo của kho lắng nghe.
DO $ll$
BEGIN
  IF to_regclass('public.tk_quang_cao') IS NULL OR to_regclass('public.qc_khan_gia') IS NULL
     OR to_regclass('public.qc_khan_gia_cd') IS NULL OR to_regclass('public.yeu_cau_sheet_qc') IS NULL THEN
    RAISE EXCEPTION 'DB % không có tk_quang_cao / qc_khan_gia / qc_khan_gia_cd / yeu_cau_sheet_qc — chạy với -d lang_nghe (sau delta 2026-10-26)',
      current_database();
  END IF;
END $ll$;

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL ROLE lang_nghe_chu;

CREATE TABLE IF NOT EXISTS qc_so_thich (
  phien_ban       SMALLINT NOT NULL CHECK (phien_ban IN (1, 2)),
  id              TEXT NOT NULL CHECK (id ~ '^[0-9]{1,30}$'),
  ten             TEXT NOT NULL,
  cap             SMALLINT,
  cha             TEXT,
  cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (phien_ban, id)
);
CREATE INDEX IF NOT EXISTS qc_so_thich_cap_nhat ON qc_so_thich (cap_nhat_luc);
-- Cột chỉ thêm khi CHƯA có (information_schema): chạy lại không xin ACCESS EXCLUSIVE trên tk_quang_cao
-- (ADD COLUMN IF NOT EXISTS vẫn xin khoá trước khi biết cột đã có).
DO $cot$
DECLARE
  c TEXT;
BEGIN
  FOREACH c IN ARRAY ARRAY['khan_gia_bo_chieu', 'khan_gia_cd_bo_chieu'] LOOP
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
                   AND table_name = 'tk_quang_cao' AND column_name = c) THEN
      EXECUTE format('ALTER TABLE public.tk_quang_cao ADD COLUMN %I SMALLINT', c);
    END IF;
  END LOOP;
END $cot$;
DO $sth$
DECLARE
  ds CONSTANT TEXT := $c$'age', 'gender', 'province_id', 'region', 'platform', 'publisher_platform', 'platform_position', 'interest_category'$c$;
  b TEXT;
  ten TEXT;
  la TEXT;
BEGIN
  FOREACH b IN ARRAY ARRAY['qc_khan_gia', 'qc_khan_gia_cd'] LOOP
    ten := b || '_chieu_check';
    -- Đã đúng (CHECK tên chuẩn có interest_category): bỏ qua — chạy lại không xin khoá.
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = format('public.%I', b)::regclass
               AND contype = 'c' AND conname = ten
               AND pg_get_constraintdef(oid) LIKE '%interest_category%') THEN
      CONTINUE;
    END IF;
    -- CHECK của cột chieu PHẢI mang tên chuẩn <bảng>_chieu_check (qc_khan_gia: đặt ở khối Meta;
    -- qc_khan_gia_cd: tên Postgres tự sinh cho CHECK cột). CHECK nào khác nhắc tới chieu → DỪNG, báo rõ,
    -- không xoá thứ không lường trước (giao dịch huỷ, CHECK cũ còn nguyên).
    SELECT string_agg(conname, ', ') INTO la FROM pg_constraint
      WHERE conrelid = format('public.%I', b)::regclass AND contype = 'c' AND conname <> ten
        AND pg_get_constraintdef(oid) LIKE '%chieu%';
    IF la IS NOT NULL THEN
      RAISE EXCEPTION 'Bảng % có CHECK chieu tên lạ (%) — không đổi gì; soát tay rồi chạy lại', b, la;
    END IF;
    EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I', b, ten);
    EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (chieu IN (%s)) NOT VALID', b,
                   ten, ds);
  END LOOP;
END $sth$;

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
  NEW.ten_cd := NULLIF(btrim(NEW.ten_cd), '');
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
  -- 23/10/2026: lọc tên chiến dịch cấp trang. Bản 2 (MKT): chuỗi JSON ba danh sách — trần
  -- quang_cao.TEN_CD_CHUOI_TOI_DA (app cắt trước; đây là chốt thứ hai).
  IF NEW.ten_cd IS NOT NULL AND length(NEW.ten_cd) > 600 THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: ten_cd quá 600 ký tự' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF NEW.cd IS NOT NULL AND NEW.cd !~ '^[0-9A-Za-z_-]{0,64}$' THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: cd sai' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  -- 28/10/2026: + cpc, lpv (bảng chiến dịch / quảng cáo thêm CPC, Landing page view).
  IF NEW.sap IS NOT NULL AND NEW.sap NOT IN ('chi', 'hien_thi', 'cpm', 'click', 'ctr', 'cpc', 'lpv',
                                             'view', 'tuong_tac', 'follow', 'roas') THEN
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
  -- Trần toàn hệ thống TÁCH theo nguồn (soát 22/10/2026): dòng Mark (người hỏi Mark, có thể bị
  -- lừa qua lời nhắn) ≤ 15/giờ đếm riêng dòng mark; dòng web (quản trị viên) ≤ 30/giờ đếm riêng
  -- dòng web — Mark không bao giờ chiếm hết trần của nút trên trang. nguon đã có giá trị mặc định
  -- ('web') trước khi trigger chạy; web không ghi được cột, mark bị RLS buộc 'mark'.
  IF NEW.nguon = 'mark' THEN
    IF (SELECT count(*) FROM public.yeu_cau_sheet_qc WHERE nguon = 'mark'
        AND tao_luc > now() - interval '1 hour') >= 15 THEN
      RAISE EXCEPTION 'yeu_cau_sheet_qc: quá trần Mark mỗi giờ' USING ERRCODE = 'check_violation';
    END IF;
  ELSIF (SELECT count(*) FROM public.yeu_cau_sheet_qc WHERE nguon <> 'mark'
         AND tao_luc > now() - interval '1 hour') >= 30 THEN
    RAISE EXCEPTION 'yeu_cau_sheet_qc: quá trần chung mỗi giờ' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION chuan_yeu_cau_sheet_qc() FROM PUBLIC;

COMMENT ON TABLE qc_so_thich IS $$[Lớp] Dim
[Mục đích] Tên tiếng Việt của nhóm sở thích TikTok (interest category) — đặt tên cho giá trị chiều sở thích của khán giả quảng cáo (qc_khan_gia, qc_khan_gia_cd).
[Grain] 1 dòng = 1 nhóm sở thích × 1 phiên bản danh mục TikTok (1 hoặc 2)
[Khoá] PK: phien_ban + id | Join: qc_khan_gia.gia_tri / qc_khan_gia_cd.gia_tri dạng 'v<phien_ban>:<id>' (chieu = interest_category) → (phien_ban, id); cha → qc_so_thich.id (cùng phien_ban)
[Nguồn] TikTok for Business MCP tool_execute → tool_interest_category_get (version 1 | 2, language vi), bộ hẹn giờ tiktok-ads-dong-bo
[Phạm vi] Toàn bộ danh mục sở thích TikTok trả cho một tài khoản quảng cáo đang đồng bộ | Kênh TikTok Ads | Từ 28/10/2026
[Đã xử lý] Chỉ nhóm có mã số và có tên; cha suy ra từ sub_category_ids của nhóm cấp trên; cap = level TikTok trả
[Refresh] Upsert theo khoá trong lượt đồng bộ TikTok 06:30 giờ VN khi kho đã có dòng sở thích và tên của phiên bản đó trống hoặc cũ hơn 7 ngày (một lượt gọi mỗi phiên bản); không xoá nhóm TikTok bỏ
[Dùng khi] Hiện tên nhóm sở thích của khán giả quảng cáo TikTok; dựng cây nhóm (cha → con)
[Không dùng khi] Số hiển thị / chi theo sở thích → dùng qc_khan_gia (cả tài khoản) hoặc qc_khan_gia_cd (theo chiến dịch)
[Lưu ý] Mã v1 (101…) và v2 (10…) là hai danh mục khác nhau — luôn join kèm phien_ban. Trang Quảng cáo hiện "Sở thích <mã>" khi chưa có tên.$$;
COMMENT ON COLUMN qc_so_thich.phien_ban IS 'Phiên bản danh mục sở thích TikTok. Giá trị: 1 (danh mục cũ — mã của chiều interest_category trong báo cáo khán giả), 2 (danh mục mới — interest_category_v2, giữ trong chi_so của dòng khán giả). Một phần PK.';
COMMENT ON COLUMN qc_so_thich.id IS 'Mã nhóm sở thích TikTok (interest_category_id, chuỗi số; v1 từ 101, v2 cấp 1 từ 10). Một phần PK. Join: qc_khan_gia.gia_tri = ''v'' || phien_ban || '':'' || id.';
COMMENT ON COLUMN qc_so_thich.ten IS 'Tên nhóm sở thích tiếng Việt TikTok trả (interest_category_name, language vi), vd "Giáo dục".';
COMMENT ON COLUMN qc_so_thich.cap IS 'Cấp của nhóm trong danh mục (level TikTok: 1 = nhóm lớn nhất). NULL khi nhóm không có level.';
COMMENT ON COLUMN qc_so_thich.cha IS 'Mã nhóm cha (cùng phien_ban) — nhóm có mã này trong sub_category_ids. NULL với nhóm cấp 1 hoặc khi không suy ra được.';
COMMENT ON COLUMN qc_so_thich.cap_nhat_luc IS 'Lần bộ đồng bộ ghi / sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON COLUMN tk_quang_cao.khan_gia_bo_chieu IS 'Phiên bản bộ chiều của lần đọc khán giả CẤP TÀI KHOẢN gần nhất (TikTok; 1 = tuổi, giới tính, tỉnh/thành, thiết bị + sở thích interest_category, từ 28/10/2026). NULL = đọc bằng bộ cũ trước 28/10/2026 hoặc tài khoản Meta — TikTok NULL thì lượt kế tiếp đọc lại một lần.';
COMMENT ON COLUMN tk_quang_cao.khan_gia_cd_bo_chieu IS 'Phiên bản bộ chiều của cửa sổ khán giả CẤP CHIẾN DỊCH hoàn tất (khan_gia_cd_den; TikTok, ghi cùng giao dịch; 1 = có sở thích, từ 28/10/2026). NULL = cửa sổ đọc bằng bộ cũ hoặc tài khoản Meta — TikTok NULL thì lượt kế tiếp đọc lại một lần (cửa sổ cũ vẫn dùng tới khi cửa sổ mới hoàn tất).';
COMMENT ON COLUMN qc_khan_gia.chieu IS 'Chiều khán giả. Một phần PK. Giá trị: age, gender (TikTok + Meta), province_id, platform (TikTok: tỉnh, thiết bị), region, publisher_platform, platform_position (Meta, từ 20/10/2026), interest_category (TikTok: nhóm sở thích, từ 28/10/2026 — các nhóm chồng nhau).';
COMMENT ON COLUMN qc_khan_gia.gia_tri IS 'Giá trị của chiều (mã TikTok): age AGE_13_17…AGE_55_100, NONE; gender FEMALE, MALE, NONE; province_id mã vùng số (-1 không rõ); platform ANDROID, IPHONE, IPAD, WAP, UNKNOWN; interest_category ''v1:<mã>'' (mã sở thích v1 — khoá nhóm của báo cáo; mã v2 ở chi_so.interest_category_v2; ''v2:<mã>'' khi TikTok chỉ trả v2; tên ở qc_so_thich). Meta: age cùng mã TikTok tới 45–54, rồi 55-64, 65+; gender FEMALE, MALE, NONE; region tên vùng Meta (vd Ho Chi Minh City); publisher_platform facebook, instagram, messenger, audience_network, threads; platform_position "<nền tảng>/<vị trí>" (vd instagram/reels). Một phần PK.';
COMMENT ON COLUMN qc_khan_gia_cd.chieu IS 'Chiều khán giả. Một phần PK. Giá trị như qc_khan_gia.chieu: age, gender (TikTok + Meta), province_id, platform (TikTok), region, publisher_platform, platform_position (Meta), interest_category (TikTok, từ 28/10/2026 — các nhóm chồng nhau).';
COMMENT ON COLUMN qc_khan_gia_cd.gia_tri IS 'Giá trị của chiều, cùng mã với qc_khan_gia.gia_tri (TikTok age AGE_13_17…AGE_55_100, NONE; gender FEMALE, MALE, NONE; province_id mã vùng số GeoNames, -1 không rõ; platform ANDROID, IPHONE, IPAD, WAP, UNKNOWN; interest_category ''v1:<mã>'' — tên ở qc_so_thich; Meta region tên vùng Meta, publisher_platform, platform_position "<nền tảng>/<vị trí>"). Một phần PK.';
COMMENT ON COLUMN yeu_cau_sheet_qc.sap IS 'Cột xếp tab chiến dịch / quảng cáo: chi, hien_thi, cpm, click, ctr, cpc, lpv, view, tuong_tac, follow, roas (cpc, lpv từ 28/10/2026; click / ctr / cpc theo lượt bấm liên kết); NULL (dòng cũ) = chi. Từ 22/10/2026.';
COMMENT ON TABLE qc_khan_gia IS $$[Lớp] Raw
[Mục đích] Khán giả quảng cáo TikTok / Meta của tài khoản (tuổi, giới tính, tỉnh/thành, nền tảng; TikTok thêm nhóm sở thích từ 28/10/2026) trong cửa sổ 30 ngày — ai đang xem quảng cáo.
[Grain] 1 dòng = 1 tài khoản × 1 cửa sổ (tu..den) × 1 chiều × 1 giá trị của chiều
[Khoá] PK: advertiser_id + tu + den + chieu + gia_tri | Join: advertiser_id → tk_quang_cao.advertiser_id
[Nguồn] TikTok for Business MCP report_integrated_get (AUDIENCE, AUCTION_ADVERTISER, chiều advertiser_id + một chiều khán giả), bộ hẹn giờ tiktok-ads-dong-bo; Meta: Graph API GET act_<id>/insights (time_increment=1; khán giả: breakdowns, không theo ngày), bộ hẹn giờ meta-ads-dong-bo
[Phạm vi] Tài khoản đang đồng bộ có hiển thị trong 30 ngày | Kênh TikTok Ads + Meta Ads (Facebook/Instagram, từ 20/10/2026) | Từ lần kết nối đầu (19/10/2026)
[Đã xử lý] Sở thích: gia_tri 'v1:<mã>' (mã v2 ở chi_so.interest_category_v2); 13 chỉ số (chi, hiển thị, bấm, ctr, cpm, chuyển đổi, xem, xem 6 giây, thích, bình luận, chia sẻ, follow, vào hồ sơ); "-" → NULL; cột không có trong báo cáo khán giả (reach, engaged_view…) NULL
[Refresh] Mỗi 7 ngày mỗi tài khoản (trong lượt đồng bộ 06:30 TikTok / 06:45 Meta giờ VN), cửa sổ 30 ngày tới hết hôm qua; cửa sổ cũ giữ lại (lịch sử)
[Dùng khi] Phân bố hiển thị/xem theo tuổi, giới tính, tỉnh, nền tảng, sở thích — lấy cửa sổ den mới nhất của từng tài khoản
[Không dùng khi] Số theo ngày → dùng qc_tk_ngay; theo chiến dịch → dùng qc_campaign_ngay
[Lưu ý] Các cửa sổ chồng nhau — KHÔNG cộng nhiều cửa sổ. province_id là mã vùng TikTok (GeoNames), -1 = không rõ. Sở thích (interest_category) CHỒNG NHAU — % một nhóm = hiển thị của nhóm ÷ tổng hiển thị theo tuổi cùng tài khoản + cửa sổ, KHÔNG ÷ tổng các nhóm; tên nhóm ở qc_so_thich; chỉ có ở cửa sổ đọc từ 28/10/2026 (tk_quang_cao.khan_gia_bo_chieu ≥ 1).$$;
COMMENT ON TABLE qc_khan_gia_cd IS $$[Lớp] Raw
[Mục đích] Khán giả quảng cáo TikTok / Meta của TỪNG chiến dịch (tuổi, giới tính, tỉnh/thành, nền tảng; TikTok thêm nhóm sở thích từ 28/10/2026) trong cửa sổ 30 ngày — khối Khán giả của trang Quảng cáo khi lọc tên chiến dịch hoặc chọn một chiến dịch.
[Grain] 1 dòng = 1 chiến dịch × 1 cửa sổ (tu..den) × 1 chiều × 1 giá trị của chiều
[Khoá] PK: advertiser_id + campaign_id + tu + den + chieu + gia_tri | Join: advertiser_id → tk_quang_cao.advertiser_id; (advertiser_id, campaign_id) → qc_campaign_ngay (tên, số theo ngày)
[Nguồn] TikTok for Business MCP report_integrated_get (AUDIENCE, AUCTION_CAMPAIGN, chiều campaign_id + một chiều khán giả, lọc campaign_ids ≤ 100 mã), bộ hẹn giờ tiktok-ads-dong-bo; Meta: Graph API GET act_<id>/insights (level=campaign, breakdowns, lọc campaign.id ≤ 50 mã), bộ hẹn giờ meta-ads-dong-bo; lệnh khan-gia đọc lại ngay
[Phạm vi] Chiến dịch CÓ hiển thị trong cửa sổ (theo qc_campaign_ngay, ≤ 5.000 chiến dịch mỗi tài khoản, nhiều hiển thị trước) của tài khoản đang đồng bộ | Kênh TikTok Ads + Meta Ads | Từ 26/10/2026
[Đã xử lý] Sở thích: gia_tri 'v1:<mã>' như qc_khan_gia; cùng 13 chỉ số và cùng luật đổi số với qc_khan_gia (TikTok "-" → NULL; Meta mã trùng sau khi đổi — vd Unknown/unknown — cộng lại theo từng chiến dịch, reach NULL khi gộp); cột không có trong báo cáo khán giả (reach TikTok, engaged_view…) NULL
[Refresh] Mỗi 7 ngày mỗi tài khoản, SAU số hằng ngày của mọi tài khoản trong lượt 06:30 TikTok / 06:45 Meta giờ VN (≤ 20 phút mỗi nền tảng, còn lại lượt sau; lỗi thì đọc lại hôm sau), cửa sổ 30 ngày tới hết hôm qua; upsert, đọc ĐỦ mới dời mốc tk_quang_cao.khan_gia_cd_den và bỏ dòng cũ (một giao dịch); chỉ giữ cửa sổ hoàn tất mới nhất (BigQuery giữ đủ lịch sử)
[Dùng khi] Khán giả của một hoặc vài chiến dịch — chỉ dòng den = tk_quang_cao.khan_gia_cd_den của từng tài khoản, lọc campaign_id
[Không dùng khi] Khán giả cả tài khoản → dùng qc_khan_gia (reach không đếm trùng giữa chiến dịch); số theo ngày của chiến dịch → dùng qc_campaign_ngay
[Lưu ý] Dòng den > mốc là cửa sổ đang đọc / bị bỏ dở — KHÔNG dùng. Cộng nhiều chiến dịch: hiển thị, chi, bấm cộng được; reach thì đếm trùng người. province_id là mã vùng TikTok (GeoNames; tên ở dashboard/vung_tiktok.py), -1 = không rõ. Sở thích (interest_category) chồng nhau — % = hiển thị của nhóm ÷ tổng hiển thị theo tuổi của cùng các chiến dịch + cửa sổ; tên nhóm ở qc_so_thich; chỉ có khi tk_quang_cao.khan_gia_cd_bo_chieu ≥ 1.$$;

RESET ROLE;

-- Quyền (như schema.sql): bộ hẹn giờ + dashboard (lang_nghe_web) đọc / thêm / sửa tên sở thích — KHÔNG
-- xoá; Mark chỉ đọc. SELECT cho lang_nghe_web ghi rõ ở đây vì GRANT SELECT ON ALL TABLES của schema.sql
-- chỉ áp bảng có lúc chạy. Cột tk_quang_cao mới: quyền cả bảng có sẵn (web SELECT/UPDATE, Mark SELECT).
GRANT SELECT, INSERT, UPDATE ON qc_so_thich TO lang_nghe_web;
GRANT SELECT ON qc_so_thich TO mark;
COMMIT;

-- (2) Đánh dấu CHECK mới đã kiểm mọi dòng cũ — SHARE UPDATE EXCLUSIVE, không chặn đọc / ghi.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL ROLE lang_nghe_chu;
ALTER TABLE qc_khan_gia VALIDATE CONSTRAINT qc_khan_gia_chieu_check;
ALTER TABLE qc_khan_gia_cd VALIDATE CONSTRAINT qc_khan_gia_cd_chieu_check;
RESET ROLE;
COMMIT;

-- Kiểm sau khi chạy:
--   sudo -u postgres psql -d lang_nghe -c '\dp qc_so_thich'
--   sudo -u postgres psql -d lang_nghe -c '\d tk_quang_cao' | grep bo_chieu
--   sudo -u postgres psql -d lang_nghe -c "select conrelid::regclass, conname, convalidated, pg_get_constraintdef(oid) from pg_constraint where conname like 'qc_khan_gia%chieu_check'"
