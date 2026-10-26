# Dashboard Social Listening — `social.hapas.vn`

Trang web nội bộ cho team marketing HAPAS (đợt 2, chủ dự án chốt 14/10/2026). Đọc kho Postgres `lang_nghe` trên VPS của Mark (Mark ghi bài sau mỗi lượt `/theodoi <mã dự án>`), hiển thị chỉ số kiểu Kompa và cho người quản lý sửa danh sách nguồn + ngân sách.

## Phạm vi

Dashboard **chỉ gồm**:

1. **Chỉ số** (`/`): bài, thảo luận (= bài + bình luận nền tảng báo, như Kompa), nguồn có bài, lượt xem, tương tác, % tích cực/tiêu cực/trung lập, so với kỳ liền trước cùng độ dài; xu hướng theo ngày (theo tuần khi khoảng > 92 ngày, giờ VN); sắc thái × chủ đề; theo nền tảng; theo loại nguồn; nguồn nổi bật; từ khoá nổi bật; bài nổi bật. Lọc theo dự án, khoảng ngày (mặc định 30 ngày trọn tới hết hôm qua — so ngày trọn với ngày trọn), nền tảng, loại nguồn. Tự cập nhật khi Mark quét xong (không tải lại trang).
2. **Nguồn** (`/nguon`): thêm/sửa dự án; thêm/sửa/tạm dừng/xoá nguồn theo dõi (dán nguyên link trang cá nhân cũng được), mỗi nguồn kèm ước tính USD/tháng (tính lại ngay khi đổi số bài/chu kỳ); duyệt/từ chối nguồn Mark đề xuất.
3. **Ngân sách** (`/ngan-sach`) — quản trị chi phí (chủ dự án 15/10/2026). Hai tầng trần: platform đặt trần tháng cấp cửa hàng (KDLA, chưa có — trang hiện "chưa có (chờ KDLA)"; `kho.tran_platform()` trả None tới khi Mark ghi trần đó vào kho), dashboard đặt trần tháng từng dự án (0–100 USD); Mark áp trần THẤP HƠN. Trang hiện: đã tiêu tháng này (giờ VN), **dự báo cả tháng** = đã tiêu + phần còn lại của tháng theo cấu hình nguồn hiện tại (nguồn tạm dừng không tính, YouTube 0), dự báo theo nền tảng, cảnh báo đỏ khi dự báo > trần hiệu lực kèm 3 nguồn tốn nhất và cách giảm (tăng chu kỳ / giảm số bài / tạm dừng); lịch sử lượt quét. Công thức ở `chi_phi.py`, chép từ `theo_doi._uoc_phan` (giá, hệ số 1,3, phí khởi động actor) — bài thử đối chiếu với Mark.
4. **Quản trị** (`/quan-tri`, trước 19/10/2026 tên "Người xem" ở `/nguoi-xem` — đường cũ chuyển hướng 308; quản trị viên + quản lý của bên): ai được vào, quyền theo từng bên, nhật ký thay đổi; tên, chức danh, phòng ban, trạng thái tài khoản Lark (đang hoạt động / chưa kích hoạt / tạm khoá / đã nghỉ việc / không có trong danh bạ — đọc danh bạ Lark, đệm trong `nguoi_xem`, làm mới nền ≤ 12 giờ/lần) và lần đăng nhập gần nhất. Thêm email: kiểm với danh bạ và cảnh báo (không chặn) nếu không có / không hoạt động. Từ 21/10/2026 (chủ dự án: "phân quyền đơn giản hơn"): ô tìm người theo tên/email lọc danh sách tại chỗ; "Thêm người" gợi ý theo TÊN từ danh bạ Lark (`danh_ba.cac_nguoi`, cùng scope với bước dò danh bạ; nhớ 30 phút) hoặc nhập email; mỗi người một ngăn "Sửa quyền" — ô chọn theo bên (Không có quyền / Chỉ xem / Quản lý) + công tắc Quản trị viên (mọi bên) — chỉ áp khi bấm **Lưu** (`POST /nguoi-xem/quyen`: kho kiểm TỪNG thay đổi bằng đúng luật cũ trong MỘT giao dịch, một thay đổi sai thì không áp gì; nhật ký một dòng mỗi thay đổi). "Xoá khỏi danh sách" (chỉ quản trị viên) giữ nguyên.
5. **Chi tiết + bình luận** (đợt 2b, 15/10/2026): bấm vào điểm/cột/dòng bất kỳ trên trang Chỉ số mở khung các bài làm nên con số đó (`/api/bai`), mỗi bài mở được bình luận Mark đã cào (`/api/binh-luan`). Khối "Bình luận đã đọc" đếm sắc thái/chủ đề bình luận của khách (bình luận của thương hiệu không tính). Số bài × số bình luận mỗi lượt đặt ở trang Ngân sách.
   - **Ý định mua** (16/10/2026): ô KPI + khối riêng (cột theo ngày/tuần/tháng, bài có nhiều câu hỏi mua nhất; bấm là ra đúng bình luận). Ý định mua = bình luận hợp lệ có chủ đề AI "Giá/mua ở đâu/ý định mua" HOẶC câu hỏi giá/mua (xin giá, giá bn, ib, mua ở đâu, còn hàng, size, ship, đặt hàng…) — `chi_so.la_y_dinh_mua`. Theo bộ lọc chung; so kỳ trước không có % khi kỳ trước 0. Bộ lọc nhanh "Khách hỏi mua" = cùng định nghĩa (`y_dinh=1`).
   - **Từ khoá nổi bật**: chữ chuẩn hoá chung với ô tìm (`chuan_chu.py`: NFKC cho chữ kiểu cách 𝐃𝐚́𝐧, teen code mk/bn/ko…, bỏ dấu khi so); bản có dấu/không dấu gộp một nhóm; mảnh câu hỏi giá ("xin giá", "giá set", "set giá") không vào mây — đã đếm ở Ý định mua. Từ 16/10/2026 (chủ dự án: "lấy bình luận spam, key word đang lỗi"): tách TỪ trước khi ghép cụm (`tu_ghep.py`, danh sách từ ghép tự soạn + so khớp dài nhất, so có dấu) — cụm là một từ ghép ("túi xách", "nước hoa") hoặc hai từ đơn liền nhau ("túi đẹp"), không còn mảnh cắt ngang như "xách nữ", "nữ tuyệt", "lòng kiểm"; bỏ mã/chữ dính số, nhãn dán TikTok "[…]", tên người được tag, hashtag có số (#quatang2010); "#tuixach" đếm chung với "túi xách"; bình luận có mã giới thiệu / lời dặn dán mã không vào mây dù nhãn còn hợp lệ (`chi_so.la_rac_quang_cao`); cụm cần ≥ 2 người viết và người viết nhiều nhất ≤ 2/3 số thảo luận của cụm. Không dùng pyvi/underthesea (nặng, chậm, tách sai chữ MXH — xem đầu `tu_ghep.py`). Ngăn từ khoá đếm bình luận đúng như mây (`cum_bl`, không xét tên tác giả). Mặc định không gồm bình luận chủ đề "Minigame/bài dự thi" (công tắc "Gồm cả bình luận minigame", `gom_mg=1` trên URL). Màu theo ngưỡng: xanh khi ≥ 25% tích cực và gấp đôi tiêu cực, đỏ đối xứng, còn lại xám; hộp rê chuột cảnh báo "x% từ 1 bài" khi một bài góp ≥ 60%.
   - Nhãn hiển thị (16/10/2026): **Internal channel** (nguồn loại `kenh_nha`) / **External channel** (`ben_ngoai`). Giá trị lưu và tham số URL không đổi.
6. **BigQuery** (`/bigquery`, chỉ quản trị viên từ 19/10/2026): trạng thái đồng bộ kho lên BigQuery; bấm "Đồng bộ ngay".
7. **Lịch quét** (`/lich-quet`, chủ dự án chốt 15/10/2026 "Dashboard + Mark tự chạy"): lịch quét tự động mỗi dự án — mỗi N giờ trong khung giờ, hằng ngày (giờ cụ thể), hằng tuần (ngày + giờ), chiến dịch (từ lúc → tới lúc, mỗi 30 phút – 7 ngày, dài ≤ 92 ngày, bắt đầu trong 365 ngày tới, mặc định quét mọi nguồn; đang diễn ra thì lịch thường nhường, hết khung tự dừng). Biểu mẫu có xem trước 10 lần chạy tới (giờ VN) và chi phí tối đa so với trần tháng, tính ở máy chủ trong threadpool (`/api/lich-quet/xem-truoc`, đúng hàm Mark dùng — `lich_quet.py`; kỳ của lịch đang gõ chỉ đếm mốc của chính nó). Mark (`quet_tu_dong.py`, nhịp 30 giây trên VPS, không qua hàng đợi job platform) tự chạy `/theodoi` đúng mốc, báo mỗi lượt lên platform bằng trace; kết quả hiện ở đây, không nhắn Lark. Trang Ngân sách nhân theo số lượt của lịch đang bật (không còn giả định 1 lượt/ngày).
8. **Quảng cáo** (`/quang-cao`, TikTok 19/10/2026 + Meta 20/10/2026) — số TikTok Ads + Meta Ads (Facebook/Instagram) theo bên, lọc nền tảng; kết nối + gán bên + duyệt tài khoản ở trang Quản trị (chỉ quản trị viên). Xem mục "TikTok Ads" và "Meta Ads" dưới đây.

### Phân quyền theo bên (chủ dự án chốt 19/10/2026)

Mỗi dự án thuộc đúng một **bên** (`du_an.don_vi` → bảng `don_vi`: `hapas`, `matemade`, quản trị viên tạo thêm). Luật ở `phan_quyen.py` (thuần), dùng chung cho app, kho (kiểm lại TRONG giao dịch sau khi khoá `nguoi_xem` + `quyen`) và kho giả của bộ thử.

| Vai trò | Ở đâu | Được làm |
|---|---|---|
| **Quản trị viên** | `nguoi_xem.la_quan_tri` | Mọi bên, mọi dự án; tạo bên; tạo dự án ở bất kỳ bên nào, chuyển dự án sang bên khác (ô "Bên sở hữu" khi sửa dự án); thêm/xoá/đổi bất kỳ ai, kể cả quản trị viên khác; trang BigQuery. Luôn còn ≥ 1 quản trị viên. |
| **Quản lý** của một bên | `quyen (email, don_vi, 'quan_ly')` | Sửa dự án / nguồn / từ khoá / ngân sách từng dự án / lịch quét / duyệt đề xuất — CHỈ dự án của bên đó; tạo dự án ở bên đó; thêm/bỏ người **Chỉ xem** của bên đó (không cấp Quản lý, không đụng quản trị viên, không tự đổi quyền mình; bỏ người khỏi bên X chỉ xoá quyền ở X). |
| **Chỉ xem** của một bên | `quyen (…, 'xem')` | Xem số liệu dự án của bên đó. |

- Một người có thể có quyền ở nhiều bên. Không cờ quản trị và không dòng `quyen` nào = không đăng nhập được; dashboard xoá luôn dòng `nguoi_xem` khi người đó hết bên.
- Dự án của bên khác: như không có (API 404 "Không có dự án này", không có trong ô chọn); xem được mà không sửa được: POST 403. Nguồn / đề xuất / lịch: dự án đọc lại từ kho, không tin biểu mẫu. `/su-kien` chỉ đẩy `cap-nhat` của dự án người đó đọc được.
- Trang Ngân sách của người không phải quản trị viên: số đã dùng / trần / ngày đặt lại của **gói Apify** là của cả tài khoản dùng chung (chi phí token chung, chỉ đọc — chấp nhận cho mọi người xem thấy); trần nội bộ + dự báo tới lúc đặt lại chỉ cộng dự án của bên họ. Dashboard không có ô sửa hạn mức Apify (Mark ghi `han_muc_apify`).
- Nhật ký trên trang Quản trị: quản trị viên thấy mọi dòng; quản lý của bên chỉ thấy dòng về dự án / quyền của bên mình.
- Cột cũ `nguoi_xem.vai_tro` chỉ còn để tương thích (Mark bản cũ đọc): dashboard giữ nó = vai trò gộp, không dùng để quyết định quyền.
- Mark (`hoi_dashboard_tool`) đọc quyền bằng `kho.quyen_cua` và chỉ trả số dự án của bên người hỏi.

### TikTok Ads (chủ dự án chốt 19/10/2026)

Số quảng cáo TikTok của các tài khoản quảng cáo HAPAS / MATEMADE, đọc qua **TikTok for Business MCP server** (lớp `tt-ads-mcp-layer`, không cần app developer). Mã: `tiktok_ads.py` (OAuth, MCP, đồng bộ — không LLM), `kho_qc.py` (SQL của các bảng quảng cáo), `quang_cao.py` (luật thuần: chỉ số, tiền, phạm vi theo bên, tổng hợp — dùng chung cho trang, `/api/qc` và Mark).

- **Trang "Quảng cáo TikTok"** (`/quang-cao`, mục menu hiện cho người có quyền ở ít nhất một bên đã có tài khoản quảng cáo; quản trị viên luôn thấy): lọc bên (chỉ bên đọc được; quản trị viên thêm "Tất cả bên", "Chưa gán bên"), tài khoản (22/10/2026: **chọn nhiều** — danh sách đánh dấu có ô tìm, Chọn tất cả / Bỏ chọn, nhóm TikTok / Meta; URL `tk=` lặp lại, một `tk=` cũ vẫn chạy; mọi mã kiểm theo phạm vi ở máy chủ — trang bỏ lặng mã lạ, `/api/qc` 404; không chọn = tất cả; KPI, kỳ trước, biểu đồ, hai bảng và Sheet cùng theo tập đã chọn; `/api/qc` trả thêm `tk_ds`), khoảng ngày (mặc định 30 ngày tới hết hôm qua; nút 7/30/90 ngày); KPI hai tầng như trang Chỉ số (hàng chính Chi tiêu*, Hiển thị, View video; hàng phụ Reach, Engaged view, Tương tác = thích + bình luận + chia sẻ, Follow, Vào hồ sơ; Doanh thu Shop*, ROAS Shop* **tạm gỡ 22/10/2026** — xem dưới) kèm % so kỳ trước; biểu đồ theo ngày (ECharts, chọn chỉ số); bảng chiến dịch + bảng quảng cáo (22/10/2026, MKT): ô **Tìm theo tên** (không dấu; quảng cáo khớp cả tên chiến dịch chứa nó — so ở Python bằng `chu_tim`, nhanh hơn translate() của Postgres), bấm tên chiến dịch = **lọc quảng cáo của chiến dịch đó** (`cd`), **xếp theo mọi cột** (Chi*, Hiển thị, CPM*, Click, CTR, View video, Tương tác, Follow; cột + sắp ROAS* tạm gỡ 22/10/2026, URL cũ `sap=roas` về sắp mặc định; bấm tiêu đề cột, bấm lại đổi chiều; CPM/CTR chỉ xếp hạng dòng ≥ 1.000 hiển thị), **20 dòng một trang** (22/10/2026, chủ dự án — thay "Số dòng"; thanh trang ‹ 1 2 3 … 150 ›, điện thoại ‹ 3/150 ›; trang bảng chiến dịch `tc`, quảng cáo `ta`; sai → 1, quá cuối → trang cuối; đổi lọc / xếp về trang 1; `so` cũ bị lờ), kèm số dòng khớp — máy chủ lọc + xếp + LIMIT/OFFSET (`quang_cao.loc_bang`, `kho_qc.qc_bang`; URL `tim`, `cd`, `sap`, `chieu=tang`, `tc`, `ta`; `/api/qc` trả thêm `bang` có `trang_*`, `so_trang_*`). Bộ lọc bảng không đổi KPI / biểu đồ; **"Xuất Lark Sheet theo bộ lọc này"** (22/10/2026: một chỗ, cuối mục bảng, kèm Sheet gần đây) xuất đúng bộ lọc đầu trang + bộ lọc bảng, mọi dòng khớp tới trần; khán giả (tuổi, giới tính, tỉnh/thành, nền tảng — cửa sổ 30 ngày mới nhất; tỉnh/thành hiện "Mã vùng N" — **TODO**: thêm bảng mã vùng TikTok/GeoNames → tên tỉnh để hiện tên); dòng "Số đến hết ngày …, đồng bộ lúc …". `*` = chỉ số tiền.
- **`/api/qc`** (`ben`, `tk`, `tu`, `den`, `sap`): cùng hàm với trang. Bên / tài khoản ngoài phạm vi → 404 như không có.
- **Lọc tên chiến dịch cấp trang** (23/10/2026, MKT): ô **Tên chiến dịch** ở Bộ lọc đầu trang (URL `ten_cd`, ≤ 100 ký tự; dấu phẩy / chấm phẩy = HOẶC; so khớp bỏ dấu với tên mới nhất trong kỳ — `quang_cao.loc_ten_cd`, `kho_qc.ma_cd_theo_ten`). Khi bật: KPI, biểu đồ, TikTok và Meta, hai bảng, kênh đăng và Lark Sheet chỉ tính chiến dịch khớp (số cấp chiến dịch, `qc_campaign_ngay`); kỳ trước tính lại danh sách khớp của kỳ trước; cụm không còn chữ Latin bị bỏ, có chữ mà không còn cụm nào = không khớp gì. Khán giả: xem mục "Khán giả theo chiến dịch" ngay dưới (26/10/2026 — khối Khán giả theo lọc tên). Thẻ "Chiến dịch có tên chứa …" trên KPI (✕ bỏ lọc); mọi liên kết / biểu mẫu giữ `ten_cd`; `/api/qc` trả `ten_cd` = {chu, so_chien_dich, so_chien_dich_truoc} hoặc null. Sheet: cột `yeu_cau_sheet_qc.ten_cd` (schema.sql).
  - **Bản 2** (23/10/2026, MKT — như Meta Ads Manager): ô gọn **Tên chiến dịch ▾** mở bảng ba dòng — *chứa tất cả* (`cd_co`), *chứa một trong* (`cd_mot`), *không chứa* (`cd_khong`), AND; tham số lặp lại hoặc dấu phẩy; `ten_cd` cũ = `cd_mot`. Trần 10 từ khoá / dòng, 60 ký tự / từ, 600 ký tự chuỗi (cắt lặng, nút i ghi rõ). Ô thẻ (Enter / dấu phẩy, Backspace) + gợi ý tên thật `GET /api/qc/ten-cd?q=` (cùng cửa + phạm vi `/api/qc`, ≤ 10 tên, mới nhất trước). Thẻ từng điều kiện trên KPI (✕ bỏ riêng điều kiện đó, "Bỏ lọc tên"); 0 khớp → ≤ 5 tên gần nhất bấm được. `quang_cao.loc_ten_cd` / `khop_ten_cd`; Sheet lưu JSON `{"co","mot","khong"}` ở cột `ten_cd` (trigger ≤ 600), dòng cũ chữ thường = "một trong"; tool Mark `ten_cd_co` / `ten_cd_mot` / `ten_cd_khong`.
- **Khán giả theo chiến dịch** (26/10/2026, chủ dự án): khối Khán giả theo Bộ lọc đầu trang (bên, tài khoản, nền tảng, **tên chiến dịch**) + ô **Chiến dịch** trong khối (URL `kg_cd`, biểu mẫu GET mang lại mọi tham số khác; qc.js: đổi là đi). Không lọc tên, không chọn → số cấp tài khoản (`qc_khan_gia`, như cũ — reach không đếm trùng giữa chiến dịch); lọc tên → cộng các chiến dịch khớp; chọn → đúng chiến dịch đó — đọc `qc_khan_gia_cd` (cửa sổ cấp chiến dịch mới nhất của từng tài khoản; `kho_qc.ds_cd_khan_gia`, `qc_khan_gia_cd`). Cộng > 1 chiến dịch thì `reach` = null. Ô chọn: chiến dịch có số khán giả trong cửa sổ, khớp lọc tên, chi nhiều trước (không xem tiền: hiển thị), ≤ 500 dòng. Câu "Số của …" nói rõ phạm vi + tài khoản chưa có số cấp chiến dịch. `/api/qc` trả `khan_gia_cd` = {che_do, chon, chon_ten, so_cd, tong_ds, ds, tk_thieu}. Đồng bộ: mỗi tuần mỗi tài khoản (TikTok AUDIENCE `AUCTION_CAMPAIGN`, Meta insights `level=campaign`, chỉ chiến dịch có hiển thị trong cửa sổ theo `qc_campaign_ngay`, ≤ 5.000 mỗi tài khoản), chạy SAU số hằng ngày của mọi tài khoản, tối đa 20 phút mỗi nền tảng mỗi lượt (`TRAN_GIAY_KHAN_GIA_CD`; còn lại lượt sau, mốc cũ nhất trước). Mốc hoàn tất `tk_quang_cao.khan_gia_cd_den`: upsert từng lô, đọc ĐỦ mới một giao dịch bỏ dòng cũ + dời mốc; trang, `/api/qc`, BigQuery chỉ dùng cửa sổ = mốc — lượt lỗi / bị giết giữa chừng không bao giờ lộ cửa sổ thiếu, cửa sổ hoàn tất trước vẫn hiện, hôm sau đọc lại. Postgres chỉ giữ cửa sổ hoàn tất mới nhất, BigQuery giữ đủ. Đọc lại ngay (bỏ qua mốc tuần, KHÔNG trần thời gian, giữ khoá đồng bộ suốt lúc chạy — tránh 06:25–07:30): `python -m dashboard.tiktok_ads khan-gia` / `python -m dashboard.meta_ads khan-gia` (`--tk` lặp lại được) — `deploy/lang-nghe/README.md` mục 13. Tỉnh TikTok: tên từ mã GeoNames (`dashboard/vung_tiktok.py`, 34 tỉnh mới + mã 63 tỉnh cũ + 6 vùng ngoài Việt Nam đã gặp, vd "Bangkok (Thái Lan)"); mã lạ vẫn "Mã vùng …" — soát bằng `python -m dashboard.tiktok_ads vung-chua-ten`.
- **Mark xuất Lark Sheet quảng cáo (22/10/2026, chủ dự án: "khi hỏi Mark thì Mark vẫn xuất Sheet được")**: nút xuất chỉ ở trang Quảng cáo (quản trị viên), nhưng người có quyền ở bên hỏi Mark đòi Sheet / file / xuất / tải về thì tool `xuat_sheet_qc` (`sheet_qc_tool.py`) thêm dòng `yeu_cau_sheet_qc` `nguon = 'mark'` cho CHÍNH người hỏi (`kho_sheet_qc.tao(..., nguon="mark")`, cùng trigger + trần + khoá advisory với nút trang), chỉ tài khoản trong bên người đó đọc được; bộ nghe `xuat_sheet_qc.py` dựng cùng Sheet, nhắn link. Bộ nghe tính lại phạm vi + quyền tiền từ quyền CSDL lúc dựng: tài khoản ngoài phạm vi bị bỏ; không xem tiền → Sheet KHÔNG có cột / giá trị tiền. Hỏi số bình thường Mark vẫn trả lời bằng chữ. Cài: `deploy/lang-nghe/README.md` mục 10.
- **Doanh thu Shop / ROAS tạm gỡ (22/10/2026, chủ dự án)**: `gia_tri_mua_shop` (TikTok `total_onsite_shopping_value`, Meta giá trị mua purchase) và ROAS suy ra từ nó đo khác cách công ty tự tính → gỡ khỏi trang, `/api/qc` (lọc ở MÁY CHỦ: `quang_cao.loc_doanh_thu`, mọi người kể cả quản trị viên), Lark Sheet và câu trả lời của Mark (`hoi_dashboard`, `lay_so_tuc_thi` — Mark nói rõ là không báo, gợi ý báo cáo của công ty). Dữ liệu vẫn lưu + đồng bộ như cũ (`gia_tri_mua_shop` vẫn là cột tiền; BigQuery không đổi). Bật lại: `quang_cao.HIEN_DOANH_THU = True`.
- **Quyền**: mỗi tài khoản quảng cáo thuộc một bên (`tk_quang_cao.don_vi`). Người xem chỉ thấy tài khoản của bên mình; tài khoản chưa gán bên chỉ quản trị viên thấy. **Chỉ số tiền** (spend, cpm, cpc, `cost_per_*`, `*_value`, `*_roas`, ngân sách, billed/cash/voucher, cột `chi`, `gia_tri_mua_shop`, ROAS) — từ 20/10/2026 (chủ dự án): **mọi người có quyền ở bên đó** (Quản lý hoặc Chỉ xem) được biết, nhưng **chỉ qua hỏi Mark, trả lời bằng chữ** (không biểu đồ). Trang **Quảng cáo TikTok** và `/api/qc` chỉ **Quản trị viên** (`quang_cao.thay_trang_qc`). Lọc tiền vẫn ở MÁY CHỦ (`quang_cao.loc_tien`) cho tài khoản chưa gán bên / ngoài bên.
- **Thẻ "Kết nối TikTok Ads"** (trang Quản trị, CHỈ quản trị viên): trạng thái, đếm ngược tới hạn 30 ngày (vàng < 7 ngày, đỏ < 2 ngày; "Không hết hạn" với token API), người/lúc cấp quyền, số tài khoản thấy so với lần trước (cảnh báo khi ít hơn), lần làm mới token, lần gọi TikTok thành công, lần đồng bộ thành công + số đến hết ngày, lỗi gần nhất. Nút: **Đăng nhập lại để gia hạn 30 ngày** (OAuth), **Đồng bộ ngay** (CHỈ ghi cờ yêu cầu `yeu_cau_dong_bo_luc` — thẻ hiện "Đã yêu cầu đồng bộ lúc …, sẽ chạy trong ≤ 2 phút", rồi "đang chạy từ …" và kết quả lượt cuối), **Ngắt kết nối** (thu hồi phía TikTok + xoá token, hỏi xác nhận), ô **Dùng token API không hết hạn**. Dưới thẻ: bảng **tài khoản quảng cáo → bên** (sửa bên, bật/tắt đồng bộ).
- **Gán bên tự động** khi thấy tài khoản lần đầu: tên có MATEMADE / MATE MADE (không phân biệt hoa thường, khoảng trắng, dấu) → `matemade`, còn lại → `hapas`. Quản trị viên sửa thì `gan_tay` = true — lần thấy sau không đè.

Đường dẫn: `POST /tiktok/ket-noi` (bắt đầu OAuth — nút trên thẻ, có CSRF; `GET` chỉ chuyển về thẻ, không tác dụng phụ; trang Quản trị của quản trị viên thêm đúng gốc `https://business-api.tiktok.com` vào CSP `form-action` để form chuyển hướng được), `GET /tiktok/xong` (TikTok trả về), `POST /tiktok/ngat`, `POST /tiktok/token`, `POST /tiktok/gan-ben` — tất cả CHỈ quản trị viên; POST qua đúng chốt CSRF + Origin như mọi POST.

**Kết nối (đo thật 19/10/2026):** đăng ký client động (DCR, client công khai, không secret) một lần cho mỗi `redirect_uri` = `DASH_BASE_URL + /tiktok/xong` (đã thử thật: đăng ký `https://social.hapas.vn/tiktok/xong` trả HTTP 201) → OAuth PKCE S256, scope `mcp:tt4b`, `resource` = máy chủ MCP. State ký HMAC, sống 10 phút, buộc vào phiên quản trị viên (dấu CSRF của phiên) + nonce trong cookie `ln_tiktok` (HttpOnly, Secure, SameSite=Lax, chỉ đường `/tiktok`) + đúng email; PKCE verifier nằm trong cookie đó ở dạng ĐÃ MÃ HOÁ. Access token sống ~24 giờ, refresh token **30 ngày và không được gia hạn khi làm mới** (TikTok trả lại cùng token, hạn đếm lùi) — dashboard không bao giờ kéo dài `refresh_het_luc`; hết 30 ngày thì `trang_thai = het_han`, quản trị viên đăng nhập lại để có 30 ngày mới. Mark nhắc trước 7, 3, 1 ngày (`nhac_tiktok_ads.py`).

**Token API (không hết hạn, sau này):** khi chủ dự án có app TikTok for Business Developer (quyền đọc báo cáo), dán "API access token" vào ô trên thẻ: dashboard thử MỘT lượt đọc danh sách tài khoản rồi mới lưu (`loai = api_token`, mã hoá, không làm mới, thẻ hiện "Không hết hạn"). Đổi qua lại hai loại chỉ là thao tác trên thẻ — không đổi mã.

**Bảo mật:**
- Danh sách công cụ MCP **chỉ đọc** cứng trong mã (`tiktok_ads.CONG_CU_DOC`: auth_advertiser_get, advertiser_info_get, report_integrated_get, identity_get, tool_execute — đúng các công cụ mã dùng). Tên khác — mọi công cụ tạo/sửa/ngân sách mà máy chủ MCP có phơi ra — bị chặn TRƯỚC khi gửi (bài thử canh). Từ 22/10/2026 (chủ dự án duyệt): `identity_get` chỉ nhận `advertiser_id`, `page`, `page_size` ≤ 100; `tool_execute` (cửa gọi ~380 công cụ khác, có cả công cụ GHI tên đuôi `_get` như `split_test_end_get`) chỉ qua ĐÚNG một dạng `{"tool_name": "ad_get", "params": {advertiser_id, fields = TRUONG_AD_GET cố định, filtering = {ad_ids: 1–100 mã số}, page_size ≤ 1000, page?}}` (`tiktok_ads.kiem_ad_get`) — thừa / thiếu / lạ một khoá là chặn (`tests/test_kenh_dang.py`).
- Token **mã hoá trong DB** (`ket_noi_ngoai.*_token_enc`) bằng khoá `TIKTOK_KHOA_MA_HOA` (32 byte base64, chỉ trong `/opt/lang-nghe/.env`). Thuật toán **AES-256-GCM** (`cryptography`, `AESGCM`; `requirements.txt`: `cryptography>=48,<51` — venv VPS đã có 50.0.2): base64(1 byte phiên bản | nonce ngẫu nhiên 12 byte | bản mã ‖ thẻ 16 byte), AAD = nhà cung cấp + tên cột — bản mã cột access không giải được ở cột refresh, sửa một byte là từ chối. Khoá thiếu / không phải base64 / không đúng 32 byte: không lưu cũng không đọc token, thẻ báo rõ lý do, lượt đồng bộ ghi `trang_thai = loi` — dashboard không sập.
- Không trang / API / log / nhật ký nào có token (bài thử canh cả chuỗi mã hoá); lỗi TikTok qua `tiktok_ads.gon_loi` (bỏ đúng các token tiến trình đang dùng, URL và chuỗi giống token) trước khi lưu/hiện.
- Làm mới token: access còn < 6 giờ thì làm mới trước lượt; TikTok từ chối giữa lượt thì làm mới cưỡng bức MỘT lần rồi chạy tiếp (`McpTuLamMoi`). Ghi token / trạng thái CÓ ĐIỀU KIỆN (đúng token + `cap_luc` đã đọc), lượt dừng khi phát hiện kết nối bị ngắt / đăng nhập lại giữa chừng — không bao giờ khôi phục kết nối quản trị viên vừa ngắt.
- Ngắt kết nối loại token API: dashboard chỉ xoá được bản trên máy chủ — thông báo nhắc thu hồi token trong TikTok for Business Developer (token không tự hết hạn).
- `/quang-cao` + `/api/qc` chung ngân sách tính với `/api/chi-so` (tối đa 2 lượt cùng lúc, quá thì 503), khoảng ≤ 400 ngày; bảng top tổng + LIMIT trước rồi mới đọc tên của ≤ 10 đối tượng.
- Role `mark` chỉ đọc `tk_quang_cao`, `qc_*` và **đúng 6 cột không bí mật** của `ket_noi_ngoai` (nha_cung_cap, loai, trang_thai, refresh_het_luc, goi_ok_luc, loi_cuoi) — không cột token, client_id hay email người cấp.
- BigQuery chỉ nhận `tk_quang_cao` + 4 bảng `qc_*` — không bao giờ `ket_noi_ngoai`.

**Đồng bộ** (`python -m dashboard.tiktok_ads dong-bo`, bộ hẹn giờ systemd 06:30 giờ VN — `deploy/lang-nghe/README.md` mục 7): làm mới token → đọc lại danh sách tài khoản (gán bên) → mỗi tài khoản đang đồng bộ: lần đầu nạp lùi **90 ngày** (3 cửa sổ 30 ngày, mới trước; lượt bị ngắt thì lượt sau đọc tiếp từ mốc `nap_lui_tu`), sau đó mỗi ngày đọc lại **7 ngày** gần nhất (chuyển đổi TikTok ghi trễ). Cấp tài khoản theo ngày (đủ 101 chỉ số hợp lệ — 3 lượt × ≤ 45); cấp campaign và ad CHỈ đối tượng có hiển thị (TikTok trả mọi đối tượng chưa xoá — một tài khoản 20.000 ad, 7.599 chạy trong 30 ngày): lấy ID xếp impressions giảm dần, dừng ở dòng 0 đầu tiên; rồi đọc theo lô ≤ 100 ID, ≤ 45 chỉ số mỗi lượt, trang ≤ 200 dòng. Cấp ad chỉ 38 chỉ số chính (một lượt mỗi trang; 7 thuộc tính + 38 = đúng 45 — thêm tên nào là gấp đôi lượt gọi cấp ad). Khán giả mỗi 7 ngày. Lỗi mạng thử lại 3 lần; tuần tự, nghỉ 0,3 giây giữa các lượt gọi. Upsert theo khoá chính (chạy lại không nhân đôi). Không token dùng được → ghi trạng thái, thoát 0. **Dashboard không bao giờ chạy đồng bộ trong tiến trình web** (MemoryMax 512M, khởi động lại giữa chừng): nút "Đồng bộ ngay" và lần kết nối đầu chỉ ghi cờ yêu cầu; bộ hẹn giờ thứ hai `tiktok-ads-yeu-cau.timer` (2 phút/lần) chạy `dong-bo --chi-khi-yeu-cau` — không có yêu cầu thì thoát ngay (< 1 giây, một câu SELECT). Hai bộ hẹn giờ + lệnh tay không chạy chồng (khoá advisory Postgres). Xong thì đẩy BigQuery ngay (khi đã bật `BQ_DATASET`), ngoài nhịp 6 giờ của dashboard.

Bảng (schema.sql, mô tả 11 nhãn): `ket_noi_ngoai` (một dòng mỗi nhà cung cấp — trạng thái, token mã hoá, lượt đồng bộ gần nhất), `tk_quang_cao`, `qc_tk_ngay`, `qc_campaign_ngay`, `qc_ad_ngay`, `qc_khan_gia` (cột số kiểu riêng + `chi_so` JSONB đủ mọi chỉ số TikTok trả), `qc_ad_kenh` + `qc_kenh` (kênh đăng, 22/10/2026 — mục dưới).

### Kênh đăng của quảng cáo (chủ dự án chốt 22/10/2026)

Trang Quảng cáo có khối **"Theo kênh đăng"** (ngay sau biểu đồ theo ngày; `templates/_kenh_dang.html`, `kenh_dang.py`, `static/kenh.css`): số của các tài khoản đang lọc tách theo danh tính quảng cáo chạy dưới tên — chi tiêu (chỉ khi xem tiền), hiển thị, click, view video, tương tác, follow; xếp theo chi (không xem tiền: theo hiển thị); 20 kênh, "xem thêm" 100 rồi 500 (`kenh_so`). Nhãn: **Spark Ads** (TikTok AUTH_CODE — bài KOC uỷ quyền; BC_AUTH_TT không trùng tên tài khoản), **Chính chủ** (TT_USER, CUSTOMIZED_USER, BC_AUTH_TT trùng tên tài khoản quảng cáo — vd "MATE MADE" ↔ "MATEMADE MKT"), **Page** (Meta — gộp theo Trang, Instagram đi kèm ở dòng phụ), **Instagram** (ad Meta chỉ có Instagram). Ad chưa đọc kênh / nền tảng không trả gộp dòng **"Chưa xác định"**; nút "i" + dòng phụ ghi độ phủ (% chi tiêu — hoặc % hiển thị khi không xem tiền — đã biết kênh). Một kênh chạy ở nhiều tài khoản được cộng chung. `/api/qc` có thêm khoá `kenh` (đã qua `QC.loc_tien`).

- **Đo thật 22/10/2026** (MATEMADE MKT, chỉ đọc): `ad_get` qua tool_execute trả `identity_id`, `identity_type`, `identity_authorized_bc_id`, `tiktok_item_id`, `campaign_id` cho 20/20 ad chạy 7 ngày và 100/100 ad chi nhiều nhất 30 ngày (100% chi tiêu; BC_AUTH_TT 56, AUTH_CODE 44; 29 kênh); `identity_get` một lượt trả 1.952 danh tính (page_info toàn 0), nối được 100%. Meta: `act_<id>/ads?fields=id,creative{actor_id,instagram_user_id,object_story_spec{page_id,instagram_user_id},effective_instagram_media_id}` lọc `ad.id IN` + mọi `effective_status` — 50/50 ad có Trang + Instagram; tên Trang / IG với token hiện tại (thiếu `pages_read_engagement`) bị từ chối (mã 100) → trang hiện "Page <id>" / "IG <id>".
- **Đồng bộ** (trong lượt đầy đủ hằng ngày, SAU phần số; lượt nhanh / tức thì không đọc kênh): chỉ ad CÓ phân phối chưa có dòng `qc_ad_kenh` (kênh của ad không đổi), chi nhiều trước. TikTok ≤ 100 ad mỗi lượt `ad_get`, ≤ 300 lượt mỗi lần (`TRAN_KENH_LUOT`), `identity_get` một lượt mỗi tài khoản khi có kênh chưa có tên (danh tính identity_get không trả → nhớ âm 7 ngày). Lỗi một tài khoản ghi nhật ký rồi sang tài khoản sau; chỉ token bị từ chối mới ném tiếp như phần số. Meta ≤ 200 ad mỗi lượt, ≤ 100 lượt mỗi lần; tên Trang (`/<id>?fields=name`) / username IG (`fields=username`) chỉ khi token có `pages_read_engagement`, ≤ 50 lượt mỗi lần, lỗi thì ghi dòng không tên và hỏi lại sau 1 ngày. Ad nền tảng không trả → dòng `loai = khong_thay` (hỏi lại sau 7 ngày). Lỗi phần kênh (cả kho chưa có bảng) chỉ ghi nhật ký — không làm hỏng lượt, thẻ kết nối không đổi (trừ token bị từ chối). Lần đầu ≈ 175 lượt TikTok + ≈ 35 lượt Meta.
- **Meta: quyền `pages_read_engagement` + `pages_show_list`** (chỉ đọc, Meta thường cấp cùng nhau) được phép từ 22/10/2026 (`meta_ads.QUYEN_CHO_PHEP`); không bắt buộc. Không xin `instagram_basic`: username IG thường bị từ chối — lỗi IG đầu tiên của lượt thì thôi hỏi IG (hiện "IG <id>"). Chốt `kiem_url` thêm đúng một dạng: GET `<id số>` trần với DUY NHẤT `fields=name` hoặc `fields=username`, không trang sau. ads_management / business_management / *_manage* / publish vẫn bị từ chối.
- Bảng: `qc_ad_kenh` (PK advertiser_id + ad_id; kenh_id, loai, kenh_phu_id = Instagram của ad Meta, bai_id) và `qc_kenh` (PK nen_tang + kenh_id; ten, username). Đẩy BigQuery (`dong_bo_bq`, không cột tiền); Mark đọc được (chưa dùng trong hỏi đáp).

### Meta Ads (chủ dự án chốt 20/10/2026)

Số Facebook / Instagram Ads của các tài khoản HAPAS / MATEMADE, đọc bằng **Graph API, chỉ GET**, token **người dùng hệ thống chỉ đọc** (`ads_read`, `read_insights`, `public_profile`; từ 22/10/2026 được phép thêm `pages_read_engagement` — tên Trang của kênh đăng; đo 20/10/2026: `me` = mark_ads_reader, 20 tài khoản VND, Asia/Ho_Chi_Minh). Mã: `meta_ads.py` (client Graph, nhập token, đồng bộ — không LLM, không phụ thuộc mã runtime của Mark); dùng chung `kho_qc.py`, `quang_cao.py`, trang và Mark với TikTok. `meta_ads_tool.py` (tool cũ của Mark) giữ nguyên.

- **Chỉ đọc, kiểm TRƯỚC khi gửi** (`meta_ads.kiem_url`): chỉ GET; chỉ `https://graph.facebook.com/<phiên bản>/` + `me`, `me/adaccounts`, `me/permissions`, `act_<số>`, `act_<số>/insights|campaigns|ads`; trang sau (`paging.next`) phải cùng đường (riêng `me/…` Meta đổi thành `<id số>/…`); tham số theo DANH SÁCH CHO PHÉP (`fields`, `limit`, `after`, `before`, `level`, `time_range`, `time_increment`, `breakdowns`; `access_token` chỉ được có trong `paging.next` và luôn bị bỏ khỏi URL — token đi header), khoá khác (`method`, `_method`, `batch`, khoá lạ trong trang sau) bị chặn trước khi gửi; không theo chuyển hướng. Không job async (POST) — Meta báo "quá nhiều dữ liệu" (mã 1) thì chia đôi cửa sổ tới 1 ngày.
- **Token**: thẻ "Kết nối Meta Ads" → "Dán token mới", hoặc lệnh `python -m dashboard.meta_ads nhap-token` (STDIN JSON `{token, tai_khoan_duyet, ai}` hoặc `--dang-env` đọc 2 dòng `MARK_META_*`) — GET `me` + `me/permissions` + `me/adaccounts` rồi mới lưu; **từ chối** token có quyền ngoài `ads_read`/`read_insights`/`public_profile` (ads_management, business_management, *_manage*…) hoặc thiếu `ads_read`/`read_insights`. Mã hoá AES-256-GCM bằng **cùng khoá** `TIKTOK_KHOA_MA_HOA`, AAD riêng `meta_ads` (bản mã không tráo được với TikTok). Lệnh không bao giờ in token. "Ngắt" chỉ xoá token trên máy chủ — thu hồi trong Meta Business Settings. Mã 190 / 102 → `trang_thai = loi` (mã con 463 → `het_han`); thẻ báo dán token mới.
- **Duyệt tài khoản** (`tk_quang_cao.duyet`, thay `MARK_META_AD_ACCOUNT_IDS`): chỉ tài khoản đã duyệt mới được đọc số; trang + Mark bỏ qua tài khoản chưa duyệt. Danh sách nhập kèm token đặt đúng tập duyệt; tài khoản mới token thấy về sau "Chưa duyệt" tới khi quản trị viên tích.
- **Gán bên tự động** (chung TikTok + Meta, `quang_cao.ben_tu_dong`): chữ THAI đứng riêng trong tên → chưa gán (NULL, chỉ quản trị viên — chưa làm HAPAS Thái đợt này; xét trước); MATEMADE / MATE MADE / MADEMATE → matemade; còn lại → hapas. Không đè `gan_tay`.
- **Đồng bộ** (`python -m dashboard.meta_ads dong-bo`, bộ hẹn giờ 06:45 giờ VN + `meta-ads-yeu-cau` 2 phút): Insights `level=account|campaign|ad`, `time_increment=1`, trang 500 dòng, ghi từng trang (không giữ cả cửa sổ trong bộ nhớ); lần đầu nạp lùi 90 ngày (cửa sổ 30 ngày, mới trước), sau đó mỗi ngày đọc lại 7 ngày; khán giả mỗi tuần (30 ngày) theo `age`, `gender`, `region`, `publisher_platform`, `publisher_platform+platform_position`. Giới hạn tần suất (mã 4, 17, 32, 613, 80000–80014, HTTP 429): nghỉ 30/60/120/240 giây rồi thử lại; header tải ≥ 85% thì nghỉ trước lượt sau. Khoá advisory riêng (720 191 002) — chạy song song TikTok được. Xong thì đẩy BigQuery.
- **Ánh xạ chỉ số** (cột kiểu riêng; mọi trường + action thô vào `chi_so`, action thành `<trường>__<action_type>`):

| Cột | TikTok | Meta |
|---|---|---|
| `chi` | spend | spend |
| `hien_thi` | impressions | impressions |
| `reach` | reach | reach (theo dòng, không cộng qua ngày) |
| `click` | clicks | clicks (mọi lượt bấm) |
| `chuyen_doi` | conversion | action mua: purchase > omni_purchase > offsite_conversion.fb_pixel_purchase (tên đầu tiên có, không cộng) |
| `view_video` | video_play_actions | action `video_view` (≥ 3 giây) |
| `view_het` | video_views_p100 | video_p100_watched_actions |
| `engaged_view` | engaged_view | video_thruplay_watched_actions (ThruPlay) |
| `thich` / `binh_luan` / `chia_se` | likes / comments / shares | action post_reaction / comment / post |
| `follow` | follows | action `like` (thích Trang) |
| `gia_tri_mua_shop` | total_onsite_shopping_value | action_values mua (cùng luật bí danh) |
| `ket_qua`, `view_hai_giay`, `view_sau_giay`, `vao_ho_so`, `mua_shop` | có | NULL |

  Meta bỏ action bằng 0: dòng có phân phối mà vắng action → 0; dòng khán giả chuyển đổi/giá trị vắng → NULL (có thể bị ẩn vì quyền riêng tư). `follow` = thích Trang là lựa chọn tạm (Instagram follow chưa có action rõ — kiểm lại khi có số thật).
- **Trang Quảng cáo** (chỉ quản trị viên): lọc Nền tảng (Tất cả / TikTok / Meta), nền tảng hiện ở từng tài khoản và dòng top. `/api/qc` nhận `nen_tang` (sai → 400); payload có `nen_tang`, `cac_nen_tang`, `theo_nen_tang` (KPI mỗi nền tảng), `theo_ngay_nen_tang`, và `nen_tang` trên mỗi dòng `tai_khoan` / `campaign` / `ad`. Trang nhúng nguyên payload ở `<script id="qc-api">` (qc.js dựng biểu đồ từ đó). Giao diện tối giản — chờ lượt thiết kế.
- **Xem trang sản phẩm (22/10/2026, chủ dự án: "cái gì gây hiểu nhầm thì phải làm cho rõ ràng")**: biểu đồ "Theo ngày" thêm hai chuỗi, MỖI chuỗi MỘT nền tảng — không gộp, không cộng chồng (xem "Tất cả" vẫn là đường một màu của nền tảng đó), nút chỉ hiện khi phạm vi có nền tảng đó với số ≠ 0; định nghĩa ở nút ⓘ cạnh tiêu đề, dòng chú giải dưới tiêu đề và tooltip:
  - **Xem trang SP TikTok Shop** (`xem_sp_shop` ← TikTok `onsite_on_web_detail`): lượt xem trang chi tiết sản phẩm trong TikTok Shop do quảng cáo mang lại — đếm lượt, không phải số người; không gồm trang chủ shop. Đo thật 22/10/2026 ở cấp tài khoản và campaign. `onsite_on_web_detail_rate` (= xem ÷ click, > 100%) không xin, không hiện. Tên TikTok TỪ CHỐI (một tên sai hỏng cả lượt gọi): `quang_cao.TEN_TU_CHOI` (shop_page_view, product_page_view, total_product_detail_page_view, onsite_shopping_page_view, product_clicks, onsite_product_view, live_product_clicks_rate, shop_visits…). Cấp ad KHÔNG xin.
  - **Xem SP website (Meta)** (`xem_sp_web` ← `chi_so.actions__view_content`, Meta Pixel ViewContent): lượt xem trang sản phẩm trên WEBSITE sau quảng cáo — không phải Shop (Meta không có số Shop).
  - Cộng từ JSON `chi_so` của `qc_tk_ngay` (`kho_qc.qc_theo_ngay`, SQL cố định, chỉ giá trị kiểu số). `/api/qc`: mỗi dòng `theo_ngay` / `theo_ngay_nen_tang` có `xem_sp_shop`, `xem_sp_web`; `chuoi_xem_sp` = chuỗi có số trong phạm vi (mã, nền tảng, nhãn, định nghĩa, tổng). Không phải chỉ số tiền.
  - **Sau khi triển khai cần đọc lại TikTok MỘT lần từ 2026-07-22** (số cũ chưa có `onsite_on_web_detail`; người vận hành chạy, xem `deploy/lang-nghe/README.md` mục 7 "Đồng bộ lại một khoảng"): `dong-bo --tu 2026-07-22` (đọc lại cả cấp campaign + ad như nạp lùi 90 ngày — vài giờ với tài khoản lớn; chạy sau 07:30, khoá advisory chặn chạy chồng). Chưa đọc lại thì chuỗi TikTok chỉ có số từ 7 ngày gần nhất (lượt hằng ngày). Meta không cần đọc lại (`actions__view_content` đã có trong `chi_so`).
- **Giới hạn đã biết (soát 20/10/2026, chưa sửa — ghi để chủ dự án biết)**:
  - Tra tên của Mark bỏ dấu theo bảng chữ tiếng Việt (`kho_qc.DICH_TU`); tên có dấu ngoài tiếng Việt chỉ khớp khi gõ đúng dấu hoặc tra bằng mã.
  - Luật "chữ THAI đứng riêng → chưa gán bên" rộng: tên có "Thái" (vd Thái Bình, tên người) cũng thành chưa gán — chỉ quản trị viên thấy; quản trị viên gán tay ở bảng tài khoản (lần thấy sau giữ nguyên).
  - Tài khoản Meta có số rồi bị bỏ duyệt: trang + Mark bỏ qua, nhưng số cũ VẪN ở `qc_*` và BigQuery (lọc bằng `tk_quang_cao.duyet`; không tự xoá số).
- **Lượt đồng bộ luôn kết thúc**: khoá / bản mã hỏng giữa lượt → `trang_thai = loi`; lỗi lạ → `dong_bo_loi` = "lượt dừng bất thường" (không bao giờ kẹt "đang chạy" / "ổn"). Loại lượt (nhanh / đầy đủ) quyết định NGUYÊN TỬ khi bắt đầu (`kho_qc.bat_dau_dong_bo`, một câu UPDATE … RETURNING). Giãn 15 phút tính cả từ lúc lượt nhanh BẮT ĐẦU (lượt bị giết giữa chừng vẫn bị tính). Câu "đang có yêu cầu" chỉ hiện email người yêu cầu cho quản trị viên.
- **Đồng bộ bấm tay cho mọi người có quyền**: dải "Số quảng cáo" trên trang Chỉ số (và trang Quảng cáo) — `deploy/lang-nghe/README.md` mục 8.
- **Mark** (`hoi_dashboard`, phần `quang_cao`): cả hai nền tảng, `theo_nen_tang`, `theo_tai_khoan` / top có nền tảng, chi phí suy ra tính lại từ tổng; tham số `nen_tang`; tra MỘT chiến dịch / quảng cáo / tài khoản bằng `tim` + `cap` (+ `theo_ngay`) — khớp tên không dấu / hoa thường / khoảng trắng hoặc mã, ≤ 10 đối tượng (nhiều hơn → `mo_ho`), không khớp → `goi_y` 5 tên gần nhất. Reach tổng nhiều ngày để trống. Luật "câu hỏi của người dùng là gốc" nằm ở mô tả tool + `ghi_chu`.
- **Số tức thì của Mark** (20/10/2026, `lay_so_tuc_thi`): Mark xin đọc lại số quảng cáo bằng một dòng `yeu_cau_tuc_thi` (`kho_tuc_thi.py`); bộ nghe `nghe_qc.py` (`tiktok-ads-nghe` / `meta-ads-nghe`, LISTEN `qc_tuc_thi`) chạy `DichVu.dong_bo_tai_khoan` — chỉ tài khoản trong phạm vi, ≤ 7 ngày gồm hôm nay, chỉ đọc, cùng khoá advisory, không đụng cờ / mốc của thẻ kết nối. Bộ hẹn giờ `*-yeu-cau` vẫn quét hàng chờ (dự phòng). Nút "Đồng bộ ngay" cũng NOTIFY. Mark không bao giờ cầm token. Lượt hằng ngày chờ khoá (≤ 30 phút, rồi thoát 3 → systemd chạy lại); khung 06:25–07:30 không lượt nhỏ nào (`quang_cao.trong_gio_dong_bo`); bộ nghe chỉ mở lượt nhanh. Cài + trần: `deploy/lang-nghe/README.md` mục 9.

Dashboard **không** chứa kỹ năng, persona, công tắc năng lực, trần mỗi lượt hay lịch "Giao việc" của Mark — những thứ đó vẫn ở console platform (chủ dự án: "mark vẫn phải theo luật của platform như trước không đổi … dashboard chỉ gồm những chỉ số và quản lý nguồn cũng như ngân sách"). Lịch console (tab Lịch chạy, kiểu Giao việc, nội dung `/theodoi <mã dự án>` — `deploy/lang-nghe/README.md` mục 5) vẫn chạy song song với lịch quét tự động.

## Cấu trúc

| Tệp | Việc |
|---|---|
| `app.py` | FastAPI `tao_app(kho=…, cau_hinh=…, lark=…, dong_bo=…)`; mọi trang, API, SSE, báo nội bộ |
| `kho.py` | module DUY NHẤT có SQL (psycopg 3, role `lang_nghe_web`); mỗi thao tác sửa ghi `nhat_ky` cùng giao dịch |
| `chi_so.py` | phép đếm chỉ số, thuần Python |
| `chuan_chu.py` | chuẩn hoá chữ MXH (NFKC, teen code, bỏ dấu) — thuần, Mark import chung (`loc_rac`) |
| `chi_phi.py` | dự báo chi phí theo dõi tháng (thuần Python; hằng số chép từ Mark, có bài đối chiếu) |
| `lich_quet.py` | lịch quét tự động: kiểm cấu hình, tính mốc (giờ VN), quyết định nhịp — thuần, Mark import chung |
| `trang_lich.py` | dựng danh sách lịch + bản xem trước (mốc + chi phí) cho trang Lịch quét |
| `phan_quyen.py` | luật phân quyền theo bên (thuần): phạm vi đọc/sửa, luật sửa người xem |
| `nhap_lieu.py` | kiểm biểu mẫu, chuẩn hoá định danh nguồn đúng dạng Mark dùng khi quét |
| `dang_nhap.py` | đăng nhập Lark (OAuth), phiên cookie ký HMAC, CSRF |
| `danh_ba.py` | danh bạ Lark (token tổ chức): email -> tên, chức danh, phòng ban, trạng thái tài khoản |
| `dong_bo_bq.py` | đồng bộ kho → BigQuery (gắn vào hook `app.state.sau_cap_nhat`) |
| `quan_tri.py` | lệnh máy chủ: cấp/bỏ quản trị viên, quyền theo bên, tạo bên, liệt kê |
| `tiktok_ads.py` | TikTok Ads: OAuth (DCR + PKCE), mã hoá token, MCP chỉ đọc, đồng bộ; dòng lệnh `python -m dashboard.tiktok_ads dong-bo` |
| `meta_ads.py` | Meta Ads: client Graph CHỈ GET, nhập token chỉ đọc, đồng bộ; `python -m dashboard.meta_ads dong-bo|nhap-token|trang-thai` |
| `kho_qc.py` | SQL của `ket_noi_ngoai`, `tk_quang_cao`, `qc_*` (dùng chung `kho.ket_noi`; TikTok + Meta) + hàm đọc tra cứu của Mark |
| `quang_cao.py` | luật thuần quảng cáo (TikTok + Meta): chỉ số, chỉ số tiền, phạm vi theo bên, gán bên, trạng thái đồng bộ — Mark import chung |
| `templates/`, `static/` | giao diện (Jinja2, ECharts 5.5.1 phục vụ tại chỗ `static/echarts.min.js`, sáng/tối theo hệ điều hành) |

Đường dẫn: `/`, `/api/chi-so`, `/quang-cao`, `/api/qc`, `/tiktok/ket-noi`, `/tiktok/xong`, `/nguon`, `/ngan-sach`, `/quan-tri` (`/nguoi-xem` → 308), `/api/danh-ba/tim` (gợi ý người theo tên, quản trị viên + quản lý bên), `/bigquery` (chỉ quản trị viên), `/su-kien` (SSE), `/dang-nhap`, `/dang-nhap/lark`, `/dang-nhap/xong`, `/dang-xuat`, `/suc-khoe` (không cần đăng nhập), `/noi-bo/co-du-lieu` (chỉ Mark trên cùng máy), và các POST sửa dữ liệu (`/du-an/…`, `/nguon/…`, `/de-xuat/…`, `/ngan-sach/<mã>`, `/nguoi-xem/quyen|xoa`, `/don-vi/them`, `/bigquery/dong-bo`, `/tiktok/ngat|token|gan-ben`, `/meta/ngat|token`, `/qc/gan-ben`, `/quang-cao/tao-sheet` + `/api/qc/sheet` (xuất Lark Sheet, 20/10/2026) — chỉ quản trị viên; `/quang-cao/dong-bo` — mọi người có quyền; "Đồng bộ ngay" chỉ còn ở dải trên trang Quảng cáo).

## Bảo vệ

- Đăng nhập bằng Lark: tài khoản phải thuộc tổ chức Lark của HAPAS (`tenant_key` = `DASH_LARK_TENANT_KEY`), email lấy `enterprise_email` (chỉ khi trống mới lấy `email`), và email phải có quyền (quản trị viên hoặc ít nhất một bên — xem "Phân quyền theo bên"). Lần đầu mỗi email đăng nhập, open_id Lark được ghi vào nhật ký. Quyền đọc lại MỖI lượt — xoá người xem / bỏ quyền ở bên có hiệu lực ngay.
- Phiên 8 giờ. "Đăng xuất" chỉ xoá cookie ở trình duyệt đó (cookie ký không thu hồi được từ máy chủ); muốn chặn ai ngay thì xoá khỏi trang Quản trị, muốn đăng xuất TẤT CẢ thì đổi `DASH_SESSION_KEY` rồi restart.
- Mọi POST: phiên + mã CSRF + quyền sửa ĐÚNG dự án / bên đó, kiểm phía máy chủ. Không còn ít nhất một quản trị viên thì không xoá/bỏ quyền được (khoá bảng `nguoi_xem` + `quyen` trong giao dịch).
- Cookie HttpOnly, Secure, SameSite=Lax. Chỉ chuyển hướng tới đường dẫn tương đối. CSP `script-src 'self'` (không CDN), mọi chữ từ kho đều được thoát.
- Người chỉ xem không thấy email người sửa/thêm và chữ lỗi thô (chỉ thấy "có lỗi").
- `/api/chi-so`: tối đa 2 lượt tính cùng lúc (quá thì 503 "đang bận", trang tự thử lại), kết quả nhớ 60 giây theo mốc lượt quét mới nhất, đọc tối đa 20.000 bài MỚI NHẤT (vượt thì trang cảnh báo).
- `/su-kien`: tối đa 200 kết nối, 5 mỗi người; đọc lại vai trò mỗi 5 phút, bị xoá thì đóng.
- `/noi-bo/co-du-lieu`: chỉ nhận từ 127.0.0.1/::1, không qua proxy, đúng `LANG_NGHE_BAO_KHOA` (để trống = từ chối hết; trùng khoá phiên = không khởi động). Caddy chặn thêm đường này từ ngoài.
- Thời gian thực: Mark báo qua `/noi-bo/co-du-lieu`; dự phòng vòng kiểm 30 giây lượt quét vừa xong. Mỗi lần có dữ liệu mới, trình duyệt nhận `cap-nhat` rồi tải lại số; sau đó hook `sau_cap_nhat` chạy nền (đồng bộ BigQuery).
- ECharts 5.5.1 phục vụ từ chính dashboard: `static/echarts.min.js`, lấy từ `https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js`, 1.030.855 byte, sha256 `e84270bd0cd5bdf60fefc26d00c2a391cb2e81f4d26a7a9ee16185a54773a3cf` (thẻ script có `integrity`, bộ thử canh hash). Đổi bản thì sửa `ECHARTS_SRI` trong `app.py`.

## Cài trên VPS — **cần người duyệt trước khi chạy trên VPS**

Điều kiện: đã chạy `deploy/lang-nghe/schema.sql` (DB `lang_nghe`, role `lang_nghe_web`).

```bash
# 1. user hệ điều hành trùng tên role (peer auth) + thư mục
sudo useradd --system --home /opt/lang-nghe --shell /usr/sbin/nologin lang_nghe_web
sudo install -d -o root -g lang_nghe_web -m 0750 /opt/lang-nghe /opt/lang-nghe/app

# 2. mã + venv riêng (KHÔNG dùng venv Hermes)
sudo rsync -a --delete --chown=root:lang_nghe_web --chmod=D750,F640 dashboard/ /opt/lang-nghe/app/dashboard/
sudo python3.12 -m venv /opt/lang-nghe/venv
sudo /opt/lang-nghe/venv/bin/pip install -r /opt/lang-nghe/app/dashboard/requirements.txt
sudo /opt/lang-nghe/venv/bin/pip check

# 3. cấu hình: chép env.example, điền khoá (xem mục "Ứng dụng Lark").
#    HAI khoá khác nhau, mỗi khoá một lần openssl riêng (trùng nhau thì dashboard không khởi động:
#    khoá báo nằm cả trong .env của Mark — ai đọc được nó không được phép ký phiên quản lý).
sudo install -o root -g root -m 0600 dashboard/env.example /opt/lang-nghe/.env
sudo sed -i "s/__KHOA_PHIEN_openssl_rand_hex_32__/$(openssl rand -hex 32)/" /opt/lang-nghe/.env   # DASH_SESSION_KEY
KHOA_BAO=$(openssl rand -hex 32)                                                                  # LANG_NGHE_BAO_KHOA
sudo sed -i "s/__KHOA_BAO_openssl_rand_hex_32__/$KHOA_BAO/" /opt/lang-nghe/.env
#    cùng khoá báo đặt vào .env của Mark (LANG_NGHE_BAO_KHOA=…), rồi xoá biến khỏi shell
sudoedit /opt/mark/app/.env; unset KHOA_BAO
sudoedit /opt/lang-nghe/.env        # DASH_LARK_APP_ID/SECRET, DASH_LARK_TENANT_KEY

# 4. kiểm peer auth, rồi (nếu schema.sql chưa đặt) thêm quản trị viên ĐẦU TIÊN
sudo -u lang_nghe_web psql -d lang_nghe -c 'select count(*) from nguoi_xem where la_quan_tri'
cd /opt/lang-nghe/app && sudo -u lang_nghe_web /opt/lang-nghe/venv/bin/python -m dashboard.quan_tri quan-tri <email-lark>@hapas.vn
#    quyền theo bên: … quan_tri them-quyen <email> <bên> <xem|quan_ly>; bo-quyen <email> <bên>; them-ben <mã> <tên>; ds-nguoi

# 5. dịch vụ (chỉ nghe 127.0.0.1:8090, 1 worker)
sudo install -o root -g root -m 0644 dashboard/lang-nghe-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now lang-nghe-dashboard
curl -s http://127.0.0.1:8090/suc-khoe        # {"ok":true,"db":true}
journalctl -u lang-nghe-dashboard -n 50
```

Dashboard KHÔNG khởi động (xem `journalctl`) khi: thiếu biến bắt buộc, `DASH_SESSION_KEY` không phải ≥ 32 ký tự hex, `LANG_NGHE_BAO_KHOA` có nhưng ngắn hơn 32 ký tự hex hoặc TRÙNG khoá phiên.

Cập nhật mã: **chạy `deploy/lang-nghe/schema.sql` TRƯỚC** khi mã mới cần cột/bảng mới (19/10/2026: `don_vi`, `quyen`, `nguoi_xem.la_quan_tri`, `du_an.don_vi` — thiếu thì dashboard mới không đọc được quyền, mọi trang 503), rồi `rsync` lại bước 2, `pip install -r` nếu `requirements.txt` đổi, `sudo systemctl restart lang-nghe-dashboard`.

Unit systemd đã đặt `InaccessiblePaths=-/opt/mark` (dashboard không đọc được thư mục/.env của Mark), `ProtectProc=invisible`, `CapabilityBoundingSet=` rỗng, `SystemCallFilter=@system-service`. **Việc sau (chủ dự án duyệt):** thêm `InaccessiblePaths=-/opt/lang-nghe` vào unit của Mark để chiều ngược lại cũng kín (Mark chỉ cần socket Postgres).

### Caddy (`/etc/caddy/Caddyfile`)

```caddy
social.hapas.vn {
    encode zstd gzip
    # biểu mẫu dashboard rất nhỏ — chặn thân yêu cầu lớn ngay ở cửa
    request_body {
        max_size 256KB
    }
    # chỉ dành cho máy chủ: Mark báo thẳng 127.0.0.1:8090/noi-bo/…, người vận hành kiểm
    # 127.0.0.1:8090/suc-khoe — từ ngoài trả 404
    @noi_bo path /noi-bo/* /suc-khoe
    respond @noi_bo 404
    reverse_proxy 127.0.0.1:8090 {
        flush_interval -1      # đẩy ngay sự kiện SSE (/su-kien)
    }
}
```

GIỮ nguyên `X-Forwarded-For` Caddy tự gửi — **không bao giờ** thêm `header_up -X-Forwarded-For`: uvicorn dựa vào nó để biết IP người xem thật, và `/noi-bo/co-du-lieu` dựa vào nó để biết yêu cầu đi qua proxy (thiếu nó thì mọi yêu cầu qua Caddy trông như từ 127.0.0.1).

Cần thêm (chủ dự án duyệt): bản ghi DNS `social.hapas.vn` → IP VPS; mở `80/tcp` và `443/tcp` trên ufw (hiện chỉ mở 22) và firewall nhà cung cấp. Caddy tự lấy chứng chỉ HTTPS.

### Ứng dụng Lark (Lark Developer, bản quốc tế)

1. Tạo **ứng dụng tự xây** riêng cho dashboard (không dùng app của bot Mark). Lấy App ID / App Secret → `DASH_LARK_APP_ID` / `DASH_LARK_APP_SECRET`.
2. **Security Settings → Redirect URLs**: thêm đúng `https://social.hapas.vn/dang-nhap/xong`.
3. **Permissions & Scopes** (quyền người dùng): `contact:user.email:readonly`. Nên thêm `contact:user.employee:readonly` (email doanh nghiệp `enterprise_email`, do tổ chức cấp — được ưu tiên hơn `email` người dùng tự khai) và đặt `DASH_LARK_SCOPE="contact:user.email:readonly contact:user.employee:readonly"`.
4. **Danh bạ cho trang Người xem** (quyền ỨNG DỤNG, token tổ chức): `contact:user.id:readonly` (email -> open_id), `contact:user.base:readonly` (tên, trạng thái), `contact:user.employee:readonly` (chức danh `job_title`), `contact:user.department:readonly` + `contact:department.base:readonly` (phòng ban). **Phạm vi dữ liệu danh bạ** của app = toàn công ty (người ngoài phạm vi hiện như "Không có trong danh bạ"). Thiếu quyền thì trang vẫn chạy, cột Trạng thái hiện "Chưa đọc được danh bạ" kèm ⓘ, tự thử lại mỗi giờ.
5. Phát hành phiên bản; phạm vi sử dụng: những người cần xem dashboard.
6. `DASH_LARK_TENANT_KEY` = `tenant_key` của tổ chức Lark HAPAS. Cách lấy: API "lấy thông tin tổ chức" (`GET /open-apis/tenant/v2/tenant/query`, token tenant — kiểm đường dẫn lúc cài), hoặc đăng nhập thử một lần: dashboard từ chối và ghi `tenant_key` thật vào `journalctl -u lang-nghe-dashboard` (không phải bí mật).

Endpoint Lark (đối chiếu tài liệu open.larksuite.com ngày 14/10/2026, nằm ở đầu `dang_nhap.py`): uỷ quyền `https://accounts.larksuite.com/open-apis/authen/v1/authorize` (tham số `client_id`), đổi mã `POST https://open.larksuite.com/open-apis/authen/v2/oauth/token`, người dùng `GET …/authen/v1/user_info` (trả `tenant_key`, `open_id`, `enterprise_email`, `email`). **Kiểm bằng một lần đăng nhập thật sau khi cài.**

### Phía Mark

Trong `/opt/mark/app/.env` (xem `deploy/lang-nghe/README.md` mục 3): `LANG_NGHE_BAO_URL=http://127.0.0.1:8090/noi-bo/co-du-lieu` và `LANG_NGHE_BAO_KHOA=<trùng khoá dashboard>`, rồi `mark restart`. Không đặt cũng được — dashboard tự kiểm 30 giây một lần.

### BigQuery (tuỳ chọn — để trống `BQ_DATASET` là tắt)

1. **Trước tiên** tạo dataset + bảng (có mô tả 11 nhãn) từ `deploy/lang-nghe/bigquery.sql` — chủ dự án duyệt trước khi chạy.
2. Tài khoản dịch vụ riêng, chỉ có: **BigQuery Data Editor** trên dataset `ganesha-381907.SOCIAL_LISTENING` + **BigQuery Job User** trên project `ganesha-381907`.
3. Khoá JSON đặt ở `/opt/lang-nghe/bq-sa.json`: `sudo chown root:lang_nghe_web /opt/lang-nghe/bq-sa.json && sudo chmod 0640 /opt/lang-nghe/bq-sa.json` (dịch vụ chỉ đọc được, không sửa/xoá được).
4. Trong `/opt/lang-nghe/.env`: `BQ_DATASET=ganesha-381907.SOCIAL_LISTENING`, `BQ_LOCATION=asia-southeast1`, `GOOGLE_APPLICATION_CREDENTIALS=/opt/lang-nghe/bq-sa.json`; `systemctl restart lang-nghe-dashboard`.

Đồng bộ chạy sau mỗi lượt quét và 6 giờ một lần. Không đẩy `nguoi_xem`, `nhat_ky`, `de_xuat`, cột email, `ket_noi_ngoai` (token TikTok). **Số tiền quảng cáo** (`chi`, `gia_tri_mua_shop`, khoá tiền trong `chi_so`) chỉ đẩy khi `BQ_QC_XUAT_TIEN=1` (mặc định `0`: cột tiền NULL, khoá tiền bị bỏ — chờ chủ dự án quyết; quyền SELECT cả bảng `qc_*` của role mark cũng đang chờ quyết định này). TikTok Ads (19/10/2026): thêm `tk_quang_cao` + 4 bảng `qc_*` — chạy khối "TikTok Ads" cuối `deploy/lang-nghe/bigquery.sql` TRƯỚC khi bật bản mới (thiếu bảng thì trang BigQuery báo lỗi bảng đó tới khi tạo).

### TikTok Ads — cài lần đầu (cần người duyệt trước khi chạy trên VPS)

Thứ tự: **khoá → schema.sql → mã → bộ hẹn giờ → kết nối**. Chi tiết lệnh ở `deploy/lang-nghe/README.md` mục 7.

1. Khoá mã hoá (một lần, KHÔNG dán vào chat/log/commit): `echo "TIKTOK_KHOA_MA_HOA=$(openssl rand -base64 32)" | sudo tee -a /opt/lang-nghe/.env >/dev/null` (tệp vẫn 600 root). Mất/đổi khoá = token cũ không giải mã được → đăng nhập TikTok lại (số đã đồng bộ không mất).
2. `deploy/lang-nghe/schema.sql` (6 bảng mới + quyền), rồi `rsync` mã + `systemctl restart lang-nghe-dashboard`.
3. Hai bộ hẹn giờ: `tiktok-ads-dong-bo.timer` (06:30 hằng ngày) và `tiktok-ads-yeu-cau.timer` (2 phút/lần, chỉ chạy khi có yêu cầu "Đồng bộ ngay") — deploy/lang-nghe/README.md mục 7. `pip install -r requirements.txt` (thêm `cryptography`, venv thường đã có).
4. Quản trị viên mở **Quản trị → Kết nối TikTok Ads → Đăng nhập TikTok để kết nối**, đăng nhập TikTok for Business bằng tài khoản thấy đủ 16 tài khoản quảng cáo, bấm Authorize. Dashboard tự đăng ký client (không cần khai redirect URL ở đâu), lưu token, đọc danh sách tài khoản, gán bên và ghi yêu cầu đồng bộ — bộ hẹn giờ 2 phút bắt đầu nạp 90 ngày. Kiểm bảng "Tài khoản quảng cáo → bên".
5. Mark nhắc gia hạn: đặt `MARK_TIKTOK_NHAC=oc_<nhóm quản trị>` (hoặc `ou_…`) trong `/opt/mark/app/.env`, `mark restart` (trống thì dùng `MARK_LICH_QUET_BAO_LOI`; cả hai trống = không nhắc, thẻ vẫn đếm ngược).

## Chạy bộ thử (máy dev, không cần Postgres/mạng)

```powershell
cd D:\hapas_w49; $env:LARK_APP_ID='cli_test'; $env:LARK_APP_SECRET='test'
python -X utf8 -m pytest -q -p no:cacheprovider --basetemp=.pt/tmpd tests/test_dashboard_*.py tests/test_dong_bo_bq.py tests/test_tiktok_ads.py
```
