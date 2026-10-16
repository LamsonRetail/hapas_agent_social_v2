# Lắng nghe WEB (báo, diễn đàn, blog) — thiết kế + kế hoạch tích hợp

Ngày 16/10/2026. Bản mẫu: `nguon_web.py` + `tests/test_nguon_web.py` (chưa nối vào `/theodoi`,
chưa đụng dashboard — hai nhánh w57 Threads và w58 chi phí/cửa sổ tìm đang sửa các file đó).

## 1. Kết luận ngắn

**Tìm Google có lọc ngày → đọc trang bằng HTTP thường → chỉ giữ bài thật sự nhắc brand → bước AI
sẵn có của Mark.** Không cào rộng báo, không đọc RSS/sitemap, không dùng "news API".

- Chi phí đo thật: 0,0005 USD/trang kết quả (10 link). Một lượt HAPAS = 1 câu tìm × 2 trang ≈
  **0,0013 USD** (ước tính đã nhân 1,3). Chạy mỗi ngày ≈ **0,04 USD/tháng**.
- Đọc bài: HTTP thường, **0 USD**, 8/9 trang đọc được, ngày đăng có trong JSON-LD/meta.
- Lượt thử "hapas" trong 30 ngày: 22 link, khoảng 11 link đúng HAPAS. Trong đó có bài
  **cafebiz "Từ quảng cáo gây tranh cãi của một nhãn hiệu túi xách Việt…"** (13/10, về TVC
  20/10). Đây là tín hiệu khủng hoảng mà kênh mạng xã hội hiện tại không bắt được.

## 2. Bằng chứng (lượt thử trả tiền 16/10/2026, token mới, mỗi lượt trần ≤ 0,10 USD)

| Lượt | Actor | Cấu hình | Kết quả | Tiền thật |
|---|---|---|---|---|
| 1 | `apidojo~google-search-scraper` | 4 URL Google có `tbs=qdr:m`, `gl=vn` | Bỏ qua bộ lọc ngày + vùng: ra trang Mỹ (Hapa's Brewing, bài 2019), 3/4 câu rỗng | 0,010 |
| 2 | `scraperlink~google-search-results-serp-scraper` | 3 câu (chung / site báo / site diễn đàn), 1 năm, VN/vi | 60 link, có ngày; đúng brand: daibieunhandan, brandsvietnam ×3, cafef ×3, kenh14, thanhnien, tinhte, voz, threads, lemon8, metric | 0,003 (6 trang) |
| 3 | cùng actor | `hapas` + `"yêu từ điều nhỏ nhất"`, 30 ngày, loại MXH/sàn | 22 link; khoảng 11 đúng brand (cafebiz TVC, adsoftheworld, campaignbriefasia, marketech-apac, vincom, cafef, rootagency, linkedin…); nhiễu: tàu KOTA HAPAS, Hapa Sushi, fishbase, semrush | 0,0015 (3 trang) |
| 4 | `cheapapi~google-serp-scraper` | Google **News** (tbm=nws), 30 ngày | Chỉ 3 bài (cafebiz TVC, cafef + cafebiz Vietcombank–LSR). Tab tin tức hẹp hơn tìm web | 0,0055 |
| 5 | `apify~website-content-crawler` | 2 trang (gồm daibieunhandan bị 403 khi gọi HTTP) | Đọc được cả 2 | 0,0174 |

Tổng tiền lượt thử của nhánh này: **0,0374 USD**. Hạn mức tài khoản: 1,2136 → 1,2533 USD. Phần
chênh 0,0397 có 0,002 USD là lượt `scraptik` của agent khác dùng chung tài khoản.

Đọc trang bằng HTTP thường (miễn phí, UA tự xưng `HapasListeningBot`, nghỉ giữa hai lần tải):
brandsvietnam, cafef ×3, kenh14, tinhte, voz, thanhnien → 200 + có ngày đăng. daibieunhandan →
403. Ba điều thấy khi đọc thân bài, cũng là lý do phải đọc trang chứ không dừng ở đoạn trích:

- cafef "nữ du khách trộm tài sản 500 triệu": đoạn trích Google **rỗng**, nhưng thân bài kể
  "túi xách Hapas" cạnh Rolex, LV, Bulgari. Đây là tín hiệu định vị thương hiệu.
- thanhnien "túi baguette…": chữ HAPAS chỉ nằm ở ghi chú ảnh "ẢNH: HAPAS". Đây là bài PR đặt,
  module gắn cờ `la_pr`.
- kenh14 "7 món hàng sale 7/7": HAPAS là món số 6, tức nhắc lướt (`muc_nhac = thoang`).

Thử chạy cả quy trình trên chính dữ liệu lượt 2 + 3 (`thu_thap`, đọc trang thật): 72 link → giữ
16 (trùng 4, MXH 1, robots cấm 24 — chủ yếu reddit, quá cũ 41, không nhắc 4, từ loại trừ 3).
Trong 16 bài giữ, khoảng 4 bài là nhiễu (tàu, fishbase, semrush, tin tuyển dụng). Bước AI phân
xử có sẵn sẽ loại các bài này với mã `trung_ten` / `lac_de`.

## 3. Bản đồ nguồn web cho brand thời trang/quà tặng VN

| Nhóm | Ví dụ | Giá trị | Cách tìm | Cách đọc | robots / pháp lý |
|---|---|---|---|---|---|
| Báo lớn | VnExpress, Tuổi Trẻ, Thanh Niên, Dân trí, Znews, Vietnamnet | Thấp về số lượng, cao về ảnh hưởng (khủng hoảng, PR) | Google (`tbs` ngày) | HTTP + JSON-LD | Bài: cho phép `*`. Tìm nội bộ: **cấm** (`/tim-kiem` ở tuoitre/thanhnien/znews). VnExpress chặn bot AI có tên, không chặn `*` |
| Báo kinh tế/lifestyle | CafeF, CafeBiz, Kenh14, Afamily, Eva, Soha | **Cao** với HAPAS (LSR, TVC, sale, "top túi") | Google | HTTP | cho phép |
| Báo nghề marketing | Brandsvietnam, Advertising Vietnam, Campaign Brief Asia, Marketech APAC, Ads of the World | **Cao** quanh chiến dịch (đánh giá chuyên môn, có cả tiếng Anh) | Google, **không** đặt `lr=lang_vi` | HTTP | cho phép |
| Diễn đàn | Voz, Tinhte, Otofun; Webtretho **đã chết** (DNS không phân giải được) | Tiếng khách thật (pass túi, hỏi chất lượng), số lượng ít | Google | HTTP (XenForo có JSON-LD, số trả lời) | Voz chặn bot AI, cho phép `*` |
| Reddit | r/hapas (người lai), đàn Hapas | Gần như toàn nhiễu với HAPAS | — | robots **cấm** → chỉ giữ đoạn trích | — |
| Blog/agency | rootagency, lacamie, metric.vn, ai-hay | Trung bình (phân tích, so sánh) | Google | HTTP | cho phép |
| MXH khác | LinkedIn, X, Lemon8 | Có (bài nhân sự, PR) | Google | thường bị chặn → đoạn trích | chỉ đoạn trích |
| Đánh giá sàn | Shopee/Lazada/TikTok Shop | **Nhiều nhất** về tiếng khách, nhưng là dữ liệu của chính shop | **API người bán** (xem §6) | — | Không cào shop của chính mình |

### Phương án bị loại (có số đo)
- **RSS/sitemap báo**: sitemap tin cafef/kenh14/cafebiz chỉ có 50 bài mới nhất, brandsvietnam
  có 385. Không bài nào có "hapas". Muốn bắt brand nằm sâu trong thân bài thì phải tải toàn bộ
  bài mỗi giờ của hàng chục báo, tức hàng nghìn lần tải mỗi ngày để gặp 0–1 bài nhắc brand.
- **Google News RSS**: ToS chỉ cho dùng cá nhân/phi thương mại, đo trước chỉ ra 1–2 bài trong
  30 ngày. Tab News qua actor (lượt 4) cũng chỉ ra 3 bài, nên tìm web phủ rộng hơn hẳn.
- **Tìm nội bộ của báo**: robots.txt cấm.
- **apidojo**: bỏ qua bộ lọc ngày và vùng (lượt 1).
- **`apify~google-search-scraper` (chính chủ)**: tốt nhất về độ bền nhưng đòi
  `minimalMaxTotalChargeUsd = 0,5` mỗi lượt, giá 0,0045/trang, tức gấp 9 lần. Không thử được với
  trần 0,10. Giữ làm **dự phòng**: nếu bật thì trần console của nền tảng web phải ≥ 0,5 USD.
  Tiền thật vẫn nhỏ (`apify_tool._run_actor` có sẵn tham số `min_charge`).
- **API chính thức**: Google Custom Search JSON API đã đóng với khách mới, Bing Search API đã
  ngừng (8/2025). *Theo hiểu biết đến giữa 2026, cần kiểm lại trước khi chốt.* Brave Search API
  còn, nhưng chỉ mục tiếng Việt yếu và chưa đo.
- **website-content-crawler cho mọi trang**: 0,009 USD/trang so với 0 USD của HTTP. Chỉ đáng
  dùng làm dự phòng cho miền chặn (403), để TẮT mặc định.

## 4. Thiết kế module (`nguon_web.py`)

```
cau_truy_van(du_an)      từ khoá -> rút gọn ("hapas" phủ "túi hapas", "hapas.vn") -> gộp OR
                         trong trần 32 từ; -site: MXH (đã có actor riêng), sàn, miền nhà;
                         -"từ loại trừ" khi còn chỗ
payload_tim(...)         tbs=cdr:1,cd_min..cd_max (đúng CỬA SỔ lượt), gl=VN, hl=vi, KHÔNG lr
thu_thap(du_an, ...)     actor (trần USD) -> doc_serp -> URL chuẩn + chống trùng -> bỏ MXH/
                         sàn/miền nhà/tệp -> robots.txt -> tải HTTP (an toàn SSRF, ≤3 MB, theo ≤4
                         chuyển hướng, nghỉ 1,5 s/miền, dừng khi gần hạn) -> boc_trang ->
                         ngày (trang > Google; diễn đàn lấy max(đăng, sửa)) trong cửa sổ và
                         35 ngày -> nhắc từ khoá ở TIÊU ĐỀ/THÂN (cùng `_khop_tu_khoa`) ->
                         từ loại trừ -> spam -> hit (d, dt)
```

- **Khoá**: `web:<sha1-16 của URL chuẩn>`. `m.cafef.vn/x?utm_source=…` và `cafef.vn/x/` là một
  bài; có `rel=canonical` cùng miền thì dùng canonical. `theo_doi._khoa_bai("web", link,
  {"id": …})` ra đúng khoá này (có bài thử).
- **Thân bài**: lấy khối nằm trong vùng chính (article/main/lớp `*content*`, `*detail*`,
  `bbWrapper`); bỏ nav/header/footer/aside và lớp `related|sidebar|tin-lien-quan|tags…`. Như
  vậy chữ brand ở cột "tin liên quan" không bị đếm (có bài thử). Chỉ dùng thư viện chuẩn, venv
  Hermes không cần cài thêm gói.
- **Không lưu toàn văn**: `noi_dung` = tiêu đề + tối đa 3 đoạn quanh chỗ nhắc, ≤1000 ký tự.
  Tiêu đề và đoạn nhắc đầu tiên nằm trong 200 ký tự đầu, vì `_boc_bai` của bước AI chỉ đọc
  200 ký tự.
- **Trang không đọc được** (403, robots cấm, hết giờ): giữ tiêu đề + đoạn trích Google nếu có
  nhắc brand, gắn cờ `chi_trich`.
- **Trường thêm** (`d["_web"]`, chưa có cột): `kieu_trang` (bao/dien_dan/blog/mxh_khac/khac),
  `muc_nhac` (tieu_de/chinh/thoang), `so_lan_nhac`, `la_pr` (thân bài dẫn link về miền nhà hoặc
  có "Ảnh/Nguồn: HAPAS"), `chi_trich`, `tac_gia_bai`.
- **Lỗi + bí mật**: module không đọc token (actor chạy qua `apify_tool._run_actor`). Lỗi actor
  được ghi vào `tk["loi"]` sau khi đã che chuỗi giống token (có bài thử), không làm hỏng lượt lớn.
- **Chi phí**: `uoc_luot(so_truy_van, so_trang, so_boc)` = (trang × 0,0005 + phí khởi động 0 +
  trang dự phòng × 0,009) × 1,3, cùng dạng `theo_doi._uoc_phan`. `tran_luot` = ước × 1,5, kẹp
  ≥ 0,1 và ≤ phần tháng còn lại; tháng còn < 0,1 thì không chạy.

## 5. Kế hoạch tích hợp (sau khi w57/w58 merge)

**Schema** (`deploy/lang-nghe/schema.sql`, chạy lại được):
```sql
-- bai.nen_tang không có CHECK: 'web' ghi được ngay, không cần sửa.
ALTER TABLE bai ADD COLUMN IF NOT EXISTS kieu_trang TEXT
  CHECK (kieu_trang IS NULL OR kieu_trang IN ('bao','dien_dan','blog','mxh_khac','khac'));
ALTER TABLE bai ADD COLUMN IF NOT EXISTS muc_nhac TEXT;   -- tieu_de | chinh | thoang
ALTER TABLE bai ADD COLUMN IF NOT EXISTS la_pr BOOLEAN;
-- + COMMENT ON COLUMN theo quy chuẩn BI (skill lsr-bq-description-standard) + đồng bộ BQ.
```
Thêm `kieu_trang, muc_nhac, la_pr` vào `lang_nghe_db._COT_BAI`. Cột thêm NULL được nên bài
MXH không bị ảnh hưởng.

**Vì sao `nen_tang = 'web'` mà không dùng lại `nguon.loai = 'bao'`**: `loai` là thuộc tính
của một **nguồn theo dõi** (bảng `nguon`, CHECK `nen_tang` chỉ có 4 MXH). Bài web tìm theo từ
khoá có `nguon_id = NULL`, nên dashboard sẽ xếp vào "Tìm theo từ khoá" và không bao giờ hiện
là "Báo". Một giá trị nền tảng duy nhất cho một không gian khoá; chi tiết Báo/Diễn đàn để ở
`kieu_trang`. Không tách thành nhiều nền tảng 'bao'/'dien_dan', vì đổi danh sách miền sau này
sẽ làm cùng một URL đổi khoá (thành trùng bài) và nhân số chỗ phải sửa (giá, bình luận, bộ lọc).
**Giai đoạn 2**: mở `nguon.nen_tang` thêm 'web' (`dinh_danh` = tên miền, `loai` = 'bao') thành
"danh sách báo theo dõi". Mỗi miền thành câu `site:` riêng, lúc đó loại 'Báo/tin tức' có ý nghĩa.

**Mark** (`theo_doi.py`):
1. Trong `_tim_tu_khoa`, thêm phần `tk-web` (cùng kiểu phần/mốc/run id như các nền tảng tìm theo
   từ khoá). Cửa sổ `tu..den` lấy từ mốc của w58 (`cua_so_tk`); actor gửi qua
   `A._run_actor(..., nen_tang="web")`; ghi run id ngay để khởi động lại không trả tiền hai lần.
2. Gọi `nguon_web.thu_thap(du_an, tu=…, den=…, con_usd=…, han=…, chay_actor=<hàm bọc run id>)`
   rồi đưa `hits` vào **`_giu_tu_khoa`** có sẵn (trùng / loại trừ / spam / AI / ghi kho / phễu).
   Trong `_giu_tu_khoa`, thêm `kieu_trang/muc_nhac/la_pr` từ `d["_web"]` vào dòng ghi.
3. Phễu: gộp `tk["pheu"]` của web vào `luot_quet.ghi_chu` (`_cau_pheu`), thêm dòng "Web".
4. Bình luận: **không** cào bình luận báo (phần lớn báo VN không có, hoặc là widget FB).
   Bỏ `web` khỏi `_lay_binh_luan`.
5. `_dinh_danh_tai_khoan` trả None cho web, nên không sinh "đề xuất nguồn" (đúng ý: đề xuất
   miền báo là việc của giai đoạn 2).
6. AI: nên nâng 200 → 400 ký tự **riêng cho web** trong `apify_tool._boc_bai` (bài dài cần
   ngữ cảnh). Prompt thêm một câu: "bài web có thể nhắc lướt; tin tuyển dụng / tàu / quán
   cùng tên = trung_ten".

**Dashboard**:
- `chi_so.TEN_NEN_TANG["web"] = "Báo & Web"`, `nhap_lieu`/bộ lọc thêm 'web'.
  `_TOI_DA_GIA_TRI["nen_tang"]` 4 → 6 (cùng lúc với Threads). Thêm lọc phụ `kieu_trang`.
- **Chỉ số**: không có xem/thích/chia sẻ (NULL, đừng hiện 0). "Thảo luận" = 1 + số trả lời
  (diễn đàn có, báo thường không). Với báo nên hiện **số bài**, **số miền**, **% bài PR**
  (`la_pr`), **% nhắc ở tiêu đề** (`muc_nhac`), không dùng tương tác. "Ảnh hưởng" của web
  không lấy từ followers. Giai đoạn 2 có thể gán hạng miền (báo lớn / ngách) bằng danh sách tĩnh.
- **Sắc thái**: bài báo dài, nhắc lướt thì sắc thái của **cả bài** không phải sắc thái về
  brand. AI được đưa đoạn quanh chỗ nhắc và chấm sắc thái **đối với brand**. Bài `thoang` mặc
  định nằm trong tổng nhưng có thể tách khỏi tỷ lệ tích cực/tiêu cực khi lọc.
- **Đám mây từ khoá**: chỉ dùng `noi_dung` (đã là đoạn quanh chỗ nhắc), **không** dùng toàn
  văn, để bài 2.000 chữ không lấn hết bình luận ngắn. Có thể cho trọng số 1 bài web = 1 bình
  luận.
- **Trang Ngân sách**: thêm dòng "Báo & Web: N câu tìm × 2 trang × lượt/tháng". Chép
  `GIA_TRANG`, `KHOI_DONG`, `GIA_BOC` vào `dashboard/chi_phi.py` + bài đối chiếu như các nền
  tảng khác (`uoc_luot` ↔ bản sao).

**Lịch**: báo lên Google chậm 1–24 giờ, nên **1 lượt/ngày** là đủ (≈0,04 USD/tháng). Cửa sổ
chồng lùi 2 ngày để bắt bài Google đánh chỉ mục muộn (trùng bị upsert, không tốn thêm).
**Chiến dịch** (vd 20/10, ra mắt TVC): lịch `chien_dich` mỗi 6 giờ, thêm slogan/hashtag chiến
dịch làm từ khoá (vd "do anything for love", "yêu từ điều nhỏ nhất"). Chạy liền 2 tuần ≈ 0,07
USD. Bật cảnh báo khi có bài web `tieu_cuc` ở miền `bao`, vì đó là dạng khủng hoảng cafebiz đã
thấy.

## 6. Đánh giá sàn TMĐT — đề xuất đi đường khác
Đánh giá Shopee/Lazada/TikTok Shop là nguồn tiếng khách lớn nhất. Cào qua Apify tốn 0,002–0,004
USD/đánh giá (zen-studio, vistics…), tức 10.000 đánh giá ≈ 20–40 USD. Ghi chú trong
`shopee_tool.py` cho biết actor Shopee hay rỗng âm thầm ở gói FREE. HAPAS là **chủ shop**, nên
cách đúng là API người bán: Shopee Open Platform (`product.get_comment`), Lazada Open Platform,
TikTok Shop Partner API. Cách này đủ dữ liệu, miễn phí, hợp lệ. Chỉ cào đánh giá shop **đối
thủ** khi thật sự cần. Lưu vào bảng riêng (hoặc `binh_luan` gắn với bài "sản phẩm"), không trộn
với bài web.

## 7. Pháp lý / rủi ro
- Tìm Google qua actor bên thứ ba là tự động hoá trái ToS của Google. Rủi ro nằm ở nhà cung cấp
  actor, mình không dùng tài khoản Google nào. Mọi đơn vị social listening ở VN đều làm vậy.
  Actor bên thứ ba có thể đổi/hỏng (đã thấy apidojo làm sai bộ lọc), nên giữ actor chính chủ
  làm dự phòng.
- Đọc trang: tôn trọng robots.txt (cấm thì chỉ giữ đoạn trích Google), UA tự xưng, 1 lượt/ngày,
  nghỉ giữa hai lần tải cùng miền, chỉ lưu tiêu đề + đoạn ngắn + link. Đây là trích dẫn để theo
  dõi/bình luận, không đăng lại nội dung.
- Không vượt tường chặn (403 thì thôi), trừ khi chủ dự án bật actor dự phòng.

## 8. Chủ dự án cần quyết
1. **Bật web cho HAPAS** với lịch 1 lượt/ngày (≈0,04 USD/tháng) + lịch chiến dịch 6 giờ quanh
   các dịp lớn?
2. **Danh sách từ loại trừ** cho nhiễu đã thấy: "kota hapas", "brewing", "sushi", "guitar",
   "hapa"… (nhập trên dashboard) và miền nhà thêm `hapas.co`.
3. **Mức chấp nhận pháp lý**: (a) chỉ HTTP + robots (mặc định), hay (b) cho phép actor dự phòng
   đọc trang bị chặn (~0,009 USD/trang)?
4. **Actor tìm**: dùng `scraperlink` (rẻ, đã đo) và để actor chính chủ làm dự phòng (cần trần
   console web ≥ 0,5 USD/lượt, tiền thật vẫn nhỏ)?
5. **Đánh giá sàn**: đồng ý đi API người bán (cần quyền app Shopee/Lazada/TikTok Shop của LSR)
   thay vì cào?
6. Giai đoạn 2 (danh sách báo theo dõi, hạng miền) làm ngay hay chờ 2–4 tuần dữ liệu?

## Quyết định của chủ dự án (16/10/2026)

1. **BẬT lắng nghe web cho HAPAS:**
   - quét hằng ngày, cửa sổ lùi 2 ngày;
   - trong chiến dịch, quét 6 giờ/lần và thêm khẩu hiệu chiến dịch làm từ khoá phụ.
2. **Thêm từ loại trừ** cho các bài nhiễu đã gặp:
   - từ loại trừ: "kota hapas", "hapa", guitar, sushi, brewing;
   - tên miền nhà: thêm `hapas.co`.
3. **Trang chặn đọc thường** (403, hoặc chỉ có đoạn trích) được đọc bằng website-content-crawler, giá ≈ 0,009 USD/trang:
   - có trần mỗi lượt;
   - vẫn tôn trọng robots.txt.
4. **Đánh giá Shopee / Lazada / TikTok Shop: để sau** (xem "Kế hoạch").

## Kế hoạch (chưa làm)

- **Đánh giá sàn (Shopee, Lazada, TikTok Shop):**
  - lấy qua API người bán (LSR sở hữu shop): miễn phí, đầy đủ, hợp lệ;
  - cần LSR cấp quyền ứng dụng;
  - đánh giá đi vào luồng giống bình luận (sắc thái, chủ đề, ý định mua).
- **Pha 2 web:**
  - danh sách báo theo dõi (`nguon.nen_tang='web'` theo tên miền);
  - xếp hạng mức ảnh hưởng của trang.
  - Làm sau 2–4 tuần có dữ liệu.

## Đã tích hợp (16/10/2026, nhánh feat/web-lang-nghe)

**Chạy SQL TRƯỚC khi merge/deploy** (VPS, theo thứ tự; chạy lại được):
1. `deploy/lang-nghe/schema.sql`: thêm `bai.kieu_trang`, `bai.muc_nhac`, `bai.la_pr`, hai CHECK
   `NOT VALID` và COMMENT. Cột NULL được, không ghi lại bảng.
2. `deploy/lang-nghe/du-lieu-hapas-web-2026-10-16.sql`: dữ liệu riêng của HAPAS.
   - Thêm từ loại trừ "kota hapas", "hapa", "guitar", "sushi", "brewing".
   - Thêm miền nhà `hapas.co` vào `du_an.cau_hinh.web.mien_nha`.
   - Ghi nhật ký; trong file có sẵn câu hoàn tác.
3. BigQuery, khối "Báo & Web" trong `deploy/lang-nghe/bigquery.sql`: ADD COLUMN + mô tả theo quy
   chuẩn BI. Chạy trước khi bật đồng bộ bản mới.

Bài mạng xã hội vẫn ghi đúng câu lệnh cũ: `lang_nghe_db.ghi_bai` chỉ đưa 3 cột web vào câu ghi
khi dòng có giá trị. DB chưa chạy bước 1 thì chỉ bài web lỗi, bài mạng xã hội không ảnh hưởng.

**Mark** (`theo_doi.py`):
- **Vị trí trong lượt:** `web` là nền tảng thứ 6 của `TK_NEN_TANG`. Phần `tk-web` chạy sau
  mạng xã hội trong cùng lượt tìm theo từ khoá, cùng công tắc tổng `tk_bat`, công tắc console
  `bat_web`, trần console, trần tháng dự án, mốc và phễu.
- **Bật mặc định:** web không nằm trong `MAC_DINH_TAT` vì chủ dự án đã bật.
- **Nhịp quét:**
  - Ngoài chiến dịch: tối đa 1 lượt mỗi 20 giờ (`WEB_GIO_GIAN`). Các lượt khác trong ngày ghi
    "CHUA_TOI_LUOT" và không tốn tiền.
  - Trong chiến dịch (`lich_quet` kiểu chien_dich đang chạy): lượt nào cũng tìm web.
  - Cửa sổ ngày gửi Google tính từ lượt web thành công trước, lùi 2 ngày (`WEB_NGAY_CHONG`).
  - Bài được giữ trong cả phạm vi theo dõi (`theo_doi_api.pham_vi`).
- **Khẩu hiệu chiến dịch:** ghi ở `lich_quet.cau_hinh.tu_khoa_them` của lịch chiến dịch (ô "Từ
  khoá chiến dịch" trên trang Lịch). Lý do chọn chỗ này:
  - khẩu hiệu sống đúng bằng khung chiến dịch, hết chiến dịch thì tự thôi, không phải nhớ gỡ
    khỏi từ khoá dự án;
  - chỉ web dùng khẩu hiệu (0,0005 USD/trang), lượt tìm mạng xã hội không đắt thêm.
- **Sổ "đã loại" riêng cho web** (`<mã>:web`):
  - từ khoá web có thể kèm khẩu hiệu nên có dấu riêng, không đè sổ của mạng xã hội;
  - bài web đã có trong kho hoặc đã bị loại thì không tải lại, không đọc dự phòng lại.
- **AI:** đọc 400 ký tự với bài web (`apify_tool._CHU_AI`), các nền tảng khác giữ 200.
- **Từ loại trừ một chữ dài ≤ 4 ký tự** chỉ khớp NGUYÊN từ: "hapa" loại "Hapa's Brewing" nhưng
  không loại "túi hapas". Từ loại trừ ngắn hoặc nằm trong từ khoá không đưa lên câu tìm Google.

**Tiền** (theo các quy tắc an toàn tiền đã review cho Apify):
- **Actor tìm Google:**
  - mỗi lượt có `maxTotalChargeUsd` (ước tính × 1,5, ≥ 0,1, ≤ phần tháng còn lại);
  - sổ trong lượt = số trang về × 0,0005 USD (giá thật).
- **Actor đọc dự phòng** (`apify~website-content-crawler`, chủ dự án BẬT):
  - chỉ đọc trang robots.txt cho phép mà HTTP thường bị chặn hoặc lỗi;
  - tối đa `boc` trang mỗi lượt (mặc định 10, sửa trên Ngân sách, 0 = tắt), trang Google thấy
    nhắc brand đi trước;
  - trần = min(số trang × 0,0135; phần còn lại), không thấp hơn 0,1, nếu không đủ thì không chạy;
  - actor này tính tiền theo tài nguyên nên `maxTotalChargeUsd` không chặn được. Trần thật là
    THỜI GIAN chạy = trần ÷ 0,00026 USD/giây (đo được ở 4 GB);
  - sổ = max(số trang về × 0,009; số giây × 0,00026); actor lỗi thì tính nguyên trần.
- Mọi run được ghi phần có run id ngay khi tạo, nên `Viec.chot_chi_phi` chốt đúng tiền thật.

**Chi phí dự kiến hằng tháng (HAPAS: 2 từ khoá sau rút gọn → 1 câu tìm, 15 kết quả → 2 trang):**
- **Tìm Google:** 30 lượt × 2 trang × 0,0005 ≈ **0,03 USD/tháng**.
- **Đọc dự phòng:** chỉ chạy khi có trang MỚI bị chặn (lượt thử: 1–2 trang trên 72 link). Mỗi lần
  khoảng 0,01–0,02 USD (khởi động trình duyệt). Thường **0–0,4 USD/tháng**.
- **Chiến dịch 6 giờ/lượt trong 2 tuần:** thêm khoảng 56 lượt × 0,001–0,0015 ≈ 0,08 USD, cộng
  phần đọc dự phòng nếu có.
- **Trần lý thuyết:** 30 lượt × (0,0013 + 0,135) ≈ 4,1 USD/tháng nếu ngày nào cũng có 10 trang
  mới bị chặn. Trần tháng của dự án vẫn chặn trên cùng; muốn chắc hơn thì hạ `boc` xuống 2–3.

**Dashboard:**
- **Hiển thị:**
  - "Báo & Web" là nền tảng `web`, đi qua bảng `NEN_TANG` của chi_so.js và token màu `--nt-web`.
  - Thêm bộ lọc "Loại trang" (Báo, Diễn đàn, Blog, MXH khác, Web khác); ô này chỉ hiện khi kỳ có
    bài web.
  - Thẻ KPI "Báo & Web": số bài là số chính; số miền, % bài PR, % nhắc ở tiêu đề nằm trong ⓘ.
  - Thẻ bài web có chip loại trang, PR, mức nhắc.
  - Xem / thích / chia sẻ NULL hiện trống, không hiện 0.
- **Ngân sách:**
  - Dòng "Báo & Web": bật/tắt, số kết quả mỗi câu tìm, "từ khoá → câu", ≈ USD, trần trang đọc
    dự phòng.
  - `chi_phi.uoc_web` và `ngan_sach.js` chép đúng `theo_doi.uoc_web`; có bài thử đối chiếu, gồm
    cả bài chạy bằng node.
  - Số lượt web tính riêng: ngoài chiến dịch ≤ 1 lượt/ngày, trong chiến dịch mọi lượt.
- **Lịch:** lịch chiến dịch có ô "Từ khoá chiến dịch" (`tu_khoa_them`).
- **Sửa lỗi:**
  - Lưu trang Ngân sách giờ giữ các khoá khác của `du_an.cau_hinh` (vd `web.mien_nha`), không ghi
    đè cả khối.
  - `/api/bai` nhận nền tảng `web`.
- **BigQuery:** dong_bo_bq đồng bộ thêm 3 cột mới.
