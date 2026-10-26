-- Khán giả theo chiến dịch (26/10/2026, chủ dự án chốt) — CHỈ phần thay đổi của schema.sql ngày này:
-- bảng qc_khan_gia_cd + chỉ mục + cột mốc hoàn tất tk_quang_cao.khan_gia_cd_den + mô tả 11 nhãn +
-- quyền. schema.sql đã có đúng các lệnh này (chạy cả file vẫn được); file này để áp riêng phần mới,
-- KHÔNG có lệnh đổi DB — DB đích chọn bằng -d (thử trên DB tạm: đổi -d, file không tự nhảy sang
-- lang_nghe).
--
--   sudo -u postgres env PGOPTIONS='-c lock_timeout=5s' psql -v ON_ERROR_STOP=1 -d lang_nghe \
--     < deploy/lang-nghe/2026-10-26-khan-gia-cd.sql
--
-- Cần role postgres (superuser): SET ROLE lang_nghe_chu (chủ bảng, NOLOGIN — ALTER tk_quang_cao,
-- CREATE) + GRANT. Chạy TRƯỚC khi bật mã mới (mã mới đọc cột tk_quang_cao.khan_gia_cd_den — thiếu
-- cột thì trang Quảng cáo và đồng bộ quảng cáo lỗi). Một giao dịch; chạy lại không sao (IF NOT
-- EXISTS; COMMENT / GRANT ghi đè như cũ).
-- Khoá (soát L5): REFERENCES tk_quang_cao xin SHARE ROW EXCLUSIVE trên tk_quang_cao (chặn ghi bảng
-- đó tới hết giao dịch), ADD COLUMN xin ACCESS EXCLUSIVE (chặn cả đọc — chỉ đổi danh mục, cột NULL
-- không DEFAULT nên tức thì). Giao dịch ngắn; Mark / dashboard / bộ đồng bộ đang giữ khoá thì
-- lock_timeout 5 giây → lỗi, KHÔNG treo, không đổi gì — chạy lại sau (tránh 06:25–07:30 giờ VN).

\set ON_ERROR_STOP on

-- Chặn chạy nhầm DB (quên -d → DB postgres): DB đích phải có bảng quảng cáo của kho lắng nghe.
DO $kg$
BEGIN
  IF to_regclass('public.tk_quang_cao') IS NULL OR to_regclass('public.qc_khan_gia') IS NULL THEN
    RAISE EXCEPTION 'DB % không có tk_quang_cao / qc_khan_gia — chạy với -d lang_nghe',
      current_database();
  END IF;
END $kg$;

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL ROLE lang_nghe_chu;

CREATE TABLE IF NOT EXISTS qc_khan_gia_cd (
  advertiser_id   TEXT NOT NULL REFERENCES tk_quang_cao(advertiser_id),
  campaign_id     TEXT NOT NULL,
  tu              DATE NOT NULL,
  den             DATE NOT NULL CHECK (den >= tu),
  chieu           TEXT NOT NULL CHECK (chieu IN ('age', 'gender', 'province_id', 'region',
                                                 'platform', 'publisher_platform',
                                                 'platform_position')),
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
  PRIMARY KEY (advertiser_id, campaign_id, tu, den, chieu, gia_tri)
);
CREATE INDEX IF NOT EXISTS qc_khan_gia_cd_moi ON qc_khan_gia_cd (advertiser_id, den DESC, tu DESC);
CREATE INDEX IF NOT EXISTS qc_khan_gia_cd_cap_nhat ON qc_khan_gia_cd (cap_nhat_luc);
ALTER TABLE tk_quang_cao ADD COLUMN IF NOT EXISTS khan_gia_cd_den DATE;

COMMENT ON TABLE qc_khan_gia_cd IS $$[Lớp] Raw
[Mục đích] Khán giả quảng cáo TikTok / Meta của TỪNG chiến dịch (tuổi, giới tính, tỉnh/thành, nền tảng) trong cửa sổ 30 ngày — khối Khán giả của trang Quảng cáo khi lọc tên chiến dịch hoặc chọn một chiến dịch.
[Grain] 1 dòng = 1 chiến dịch × 1 cửa sổ (tu..den) × 1 chiều × 1 giá trị của chiều
[Khoá] PK: advertiser_id + campaign_id + tu + den + chieu + gia_tri | Join: advertiser_id → tk_quang_cao.advertiser_id; (advertiser_id, campaign_id) → qc_campaign_ngay (tên, số theo ngày)
[Nguồn] TikTok for Business MCP report_integrated_get (AUDIENCE, AUCTION_CAMPAIGN, chiều campaign_id + một chiều khán giả, lọc campaign_ids ≤ 100 mã), bộ hẹn giờ tiktok-ads-dong-bo; Meta: Graph API GET act_<id>/insights (level=campaign, breakdowns, lọc campaign.id ≤ 50 mã), bộ hẹn giờ meta-ads-dong-bo; lệnh khan-gia đọc lại ngay
[Phạm vi] Chiến dịch CÓ hiển thị trong cửa sổ (theo qc_campaign_ngay, ≤ 5.000 chiến dịch mỗi tài khoản, nhiều hiển thị trước) của tài khoản đang đồng bộ | Kênh TikTok Ads + Meta Ads | Từ 26/10/2026
[Đã xử lý] Cùng 13 chỉ số và cùng luật đổi số với qc_khan_gia (TikTok "-" → NULL; Meta mã trùng sau khi đổi — vd Unknown/unknown — cộng lại theo từng chiến dịch, reach NULL khi gộp); cột không có trong báo cáo khán giả (reach TikTok, engaged_view…) NULL
[Refresh] Mỗi 7 ngày mỗi tài khoản, SAU số hằng ngày của mọi tài khoản trong lượt 06:30 TikTok / 06:45 Meta giờ VN (≤ 20 phút mỗi nền tảng, còn lại lượt sau; lỗi thì đọc lại hôm sau), cửa sổ 30 ngày tới hết hôm qua; upsert, đọc ĐỦ mới dời mốc tk_quang_cao.khan_gia_cd_den và bỏ dòng cũ (một giao dịch); chỉ giữ cửa sổ hoàn tất mới nhất (BigQuery giữ đủ lịch sử)
[Dùng khi] Khán giả của một hoặc vài chiến dịch — chỉ dòng den = tk_quang_cao.khan_gia_cd_den của từng tài khoản, lọc campaign_id
[Không dùng khi] Khán giả cả tài khoản → dùng qc_khan_gia (reach không đếm trùng giữa chiến dịch); số theo ngày của chiến dịch → dùng qc_campaign_ngay
[Lưu ý] Dòng den > mốc là cửa sổ đang đọc / bị bỏ dở — KHÔNG dùng. Cộng nhiều chiến dịch: hiển thị, chi, bấm cộng được; reach thì đếm trùng người. province_id là mã vùng TikTok (GeoNames; tên ở dashboard/vung_tiktok.py), -1 = không rõ.$$;
COMMENT ON COLUMN qc_khan_gia_cd.advertiser_id IS 'Tài khoản quảng cáo của chiến dịch. Một phần PK. FK → tk_quang_cao.advertiser_id.';
COMMENT ON COLUMN qc_khan_gia_cd.campaign_id IS 'Mã chiến dịch (TikTok campaign_id; Meta campaign id, chuỗi số). Một phần PK. Join: → qc_campaign_ngay.campaign_id (cùng advertiser_id).';
COMMENT ON COLUMN qc_khan_gia_cd.tu IS 'Ngày đầu cửa sổ 30 ngày (múi giờ tài khoản). Một phần PK.';
COMMENT ON COLUMN qc_khan_gia_cd.den IS 'Ngày cuối cửa sổ (múi giờ tài khoản, = hôm qua lúc đọc). Một phần PK.';
COMMENT ON COLUMN qc_khan_gia_cd.chieu IS 'Chiều khán giả. Một phần PK. Giá trị như qc_khan_gia.chieu: age, gender (TikTok + Meta), province_id, platform (TikTok), region, publisher_platform, platform_position (Meta).';
COMMENT ON COLUMN qc_khan_gia_cd.gia_tri IS 'Giá trị của chiều, cùng mã với qc_khan_gia.gia_tri (TikTok age AGE_13_17…AGE_55_100, NONE; gender FEMALE, MALE, NONE; province_id mã vùng số GeoNames, -1 không rõ; platform ANDROID, IPHONE, IPAD, WAP, UNKNOWN; Meta region tên vùng Meta, publisher_platform, platform_position "<nền tảng>/<vị trí>"). Một phần PK.';
COMMENT ON COLUMN qc_khan_gia_cd.chi IS 'Chi tiêu quảng cáo (spend) của chiến dịch cho giá trị này, theo tiền tệ của tài khoản (tk_quang_cao.tien_te), nền tảng báo, chưa VAT. NULL khi nền tảng không trả. CHỈ SỐ TIỀN: chỉ quản trị viên + quản lý của bên thấy.';
COMMENT ON COLUMN qc_khan_gia_cd.hien_thi IS 'Lượt hiển thị (impressions), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.reach IS 'Người tiếp cận (reach) của chiến dịch trong cửa sổ cho giá trị này, người (TikTok không trả → NULL). Cộng nhiều dòng / nhiều chiến dịch thì đếm trùng người. NULL khi nền tảng không trả hoặc khi gộp mã trùng.';
COMMENT ON COLUMN qc_khan_gia_cd.click IS 'Lượt bấm (clicks, đích đến), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.ket_qua IS 'Kết quả theo mục tiêu tối ưu, đơn vị tuỳ mục tiêu: TikTok NULL (báo cáo khán giả không xin result); Meta luôn NULL. Giữ cột để cùng dạng với qc_khan_gia.';
COMMENT ON COLUMN qc_khan_gia_cd.chuyen_doi IS 'Chuyển đổi, lượt: TikTok conversion; Meta action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase — tên đầu tiên có). NULL khi nền tảng không trả hoặc Meta ẩn (quyền riêng tư).';
COMMENT ON COLUMN qc_khan_gia_cd.view_video IS 'Lượt xem video, lượt: TikTok video_play_actions; Meta action video_view (xem ≥ 3 giây). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.view_hai_giay IS 'Lượt xem ≥ 2 giây, lượt (TikTok video_watched_2s — báo cáo khán giả không xin chỉ số này nên NULL; Meta NULL).';
COMMENT ON COLUMN qc_khan_gia_cd.view_sau_giay IS 'Lượt xem ≥ 6 giây (TikTok video_watched_6s; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.view_het IS 'Lượt xem hết video, lượt: TikTok NULL (báo cáo khán giả không xin video_views_p100); Meta video_p100_watched_actions. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.engaged_view IS 'Lượt xem tương tác, lượt: TikTok NULL (báo cáo khán giả không xin); Meta ThruPlay (video_thruplay_watched_actions). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.thich IS 'Lượt thích / cảm xúc trên quảng cáo (TikTok likes; Meta action post_reaction), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.binh_luan IS 'Bình luận trên quảng cáo (TikTok comments; Meta action comment), bình luận. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.chia_se IS 'Lượt chia sẻ (TikTok shares; Meta action post), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.follow IS 'Lượt theo dõi từ quảng cáo, lượt: TikTok follows; Meta action like (thích Trang). NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.vao_ho_so IS 'Lượt vào trang hồ sơ kênh từ quảng cáo (TikTok profile_visits; Meta NULL), lượt. NULL khi nền tảng không trả.';
COMMENT ON COLUMN qc_khan_gia_cd.mua_shop IS 'Lượt mua TikTok Shop gán cho quảng cáo, lượt mua: TikTok NULL (báo cáo khán giả không xin onsite_shopping); Meta NULL (lượt mua Meta ở chuyen_doi).';
COMMENT ON COLUMN qc_khan_gia_cd.gia_tri_mua_shop IS 'Doanh thu gán cho quảng cáo theo tiền tệ tài khoản, chưa VAT: TikTok NULL (báo cáo khán giả không xin); Meta giá trị mua (action_values mua, cùng luật bí danh với chuyen_doi), NULL khi Meta ẩn. CHỈ SỐ TIỀN.';
COMMENT ON COLUMN qc_khan_gia_cd.chi_so IS 'MỌI chỉ số nền tảng trả cho dòng (JSON {tên chỉ số: số}; "-" của TikTok → null; không gồm campaign_id và mã chiều). TikTok: 13 chỉ số khán giả; Meta: trường Insights đã xin, action thành <trường>__<action_type>; ctr, cpm, reach KHÔNG cộng được qua dòng. Khoá tiền: spend, cpm, *_value, action_values__*.';
COMMENT ON COLUMN qc_khan_gia_cd.cap_nhat_luc IS 'Lần đồng bộ ghi/sửa dòng gần nhất (UTC). Mốc đồng bộ BigQuery.';
COMMENT ON COLUMN tk_quang_cao.khan_gia_cd_den IS 'Ngày cuối (den) của cửa sổ khán giả CẤP CHIẾN DỊCH đã đọc ĐỦ gần nhất (múi giờ tài khoản; đọc lại mỗi 7 ngày, từ 26/10/2026) — trang / BigQuery chỉ dùng dòng qc_khan_gia_cd có den = mốc này. NULL khi chưa có cửa sổ nào hoàn tất.';

RESET ROLE;

-- Quyền (như schema.sql): bộ hẹn giờ + dashboard (lang_nghe_web) đọc / thêm / sửa / XOÁ — xoá CHỈ bảng
-- này (lúc hoàn tất một cửa sổ: bỏ dòng cũ / cửa sổ bỏ dở); Mark chỉ đọc. SELECT cho lang_nghe_web
-- ghi rõ ở đây vì GRANT SELECT ON ALL TABLES của schema.sql chỉ áp bảng có lúc chạy. Cột
-- tk_quang_cao.khan_gia_cd_den: quyền cả bảng có sẵn (web SELECT/UPDATE, Mark SELECT) như khan_gia_luc.
GRANT SELECT, INSERT, UPDATE, DELETE ON qc_khan_gia_cd TO lang_nghe_web;
GRANT SELECT ON qc_khan_gia_cd TO mark;
COMMIT;

-- Kiểm sau khi chạy:
--   sudo -u postgres psql -d lang_nghe -c '\dp qc_khan_gia_cd'
--   sudo -u postgres psql -d lang_nghe -c '\d tk_quang_cao' | grep khan_gia_cd_den
