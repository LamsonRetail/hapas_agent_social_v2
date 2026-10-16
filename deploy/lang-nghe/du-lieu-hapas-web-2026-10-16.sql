-- Dữ liệu (không phải schema) cho dự án HAPAS khi bật Báo & Web — chủ dự án chốt 16/10/2026.
-- Từ loại trừ nhiễu là của RIÊNG brand HAPAS (Google trả "Hapa's Brewing", "Hapa Sushi", tàu
-- "KOTA HAPAS", đàn Hapas) nên ghi vào du_an.tu_loai_tru của HAPAS, không cứng trong code cho mọi
-- dự án. "hapa" an toàn vì từ loại trừ một chữ ≤ 4 ký tự chỉ khớp NGUYÊN từ (apify_tool.
-- _tu_loai_tru_khop) — không loại "hapas". Miền nhà hapas.co (trang quốc tế) bỏ qua như hapas.vn.
--
-- Chạy SAU schema.sql, một lần (chạy lại không nhân đôi):
--   sudo -u postgres psql -v ON_ERROR_STOP=1 -d lang_nghe -f deploy/lang-nghe/du-lieu-hapas-web-2026-10-16.sql
-- Bật Báo & Web cho HAPAS (cau_hinh.tu_khoa.web.bat = true — mặc định web TẮT mọi dự án).
-- Hoàn tác: tắt Báo & Web trên trang Ngân sách, bỏ 5 từ khỏi tu_loai_tru và khoá cau_hinh.web, hoặc
--   UPDATE du_an SET tu_loai_tru = array(SELECT x FROM unnest(tu_loai_tru) x WHERE x <> ALL
--     (ARRAY['kota hapas','hapa','guitar','sushi','brewing'])),
--     cau_hinh = (cau_hinh - 'web') #- '{tu_khoa,web}'
--   WHERE ma = 'hapas';

\set ON_ERROR_STOP on
BEGIN;
UPDATE du_an SET
  tu_loai_tru = array(SELECT DISTINCT x FROM unnest(tu_loai_tru ||
                  ARRAY['kota hapas', 'hapa', 'guitar', 'sushi', 'brewing']) AS x ORDER BY x),
  -- Báo & Web mặc định TẮT với mọi dự án (theo_doi.MAC_DINH_TAT); chủ dự án chỉ duyệt HAPAS
  -- -> bật rõ ở cau_hinh.tu_khoa.web.bat (giữ các khoá khác của web nếu đã có).
  cau_hinh = jsonb_set(jsonb_set(cau_hinh, '{tu_khoa}',
                         COALESCE(cau_hinh->'tu_khoa', '{}'::jsonb) || jsonb_build_object('web',
                           COALESCE(cau_hinh->'tu_khoa'->'web', '{}'::jsonb)
                           || '{"bat": true}'::jsonb)),
                       '{web}',
                       COALESCE(cau_hinh->'web', '{}'::jsonb) || jsonb_build_object('mien_nha',
                         (SELECT jsonb_agg(DISTINCT m) FROM jsonb_array_elements_text(
                            COALESCE(cau_hinh->'web'->'mien_nha', '[]'::jsonb)
                            || '["hapas.co"]'::jsonb) AS m))),
  sua_luc = now(), sua_boi = 'mark-web-2026-10-16'
WHERE ma = 'hapas';
INSERT INTO nhat_ky (ai, hanh_dong, doi_tuong, chi_tiet)
SELECT 'mark-web-2026-10-16', 'sua_du_an', 'hapas',
       '{"tu_loai_tru_them": ["kota hapas", "hapa", "guitar", "sushi", "brewing"],
         "cau_hinh.tu_khoa.web.bat": true,
         "cau_hinh.web.mien_nha_them": ["hapas.co"], "ly_do": "bật Báo & Web (chủ dự án 16/10)"}'::jsonb
WHERE EXISTS (SELECT 1 FROM du_an WHERE ma = 'hapas');
COMMIT;
