# Kho lắng nghe `lang_nghe` + lệnh `/theodoi` (đợt 2)

Chủ dự án chốt 14/10/2026:

- **Dữ liệu ở VPS của Mark.** Danh sách nguồn theo dõi, ngân sách theo dõi hằng tháng và các bài đã quét nằm trong một DB Postgres riêng trên VPS này, không nằm trên platform.
  - Lý do: quyết định 0008 của platform. Platform chỉ giữ phần điều khiển và kiểm tra; dữ liệu xử lý nằm ở phía agent.
- **Mark vẫn theo luật platform như trước.** Kỹ năng, công tắc Năng lực và trần mỗi lượt vẫn ở console platform.
  - Lượt theo dõi đến từ hai đường lịch, cộng với lệnh gõ tay:
    - lịch `run` (Giao việc) đặt trên console, đi qua hàng đợi job của platform;
    - từ 15/10/2026, **lịch quét tự động** đặt trên dashboard (mục 5b): Mark tự chạy bằng một nhịp riêng trên VPS (`quet_tu_dong.py`) và báo mỗi lượt lên platform bằng trace.
- **Quản lý qua dashboard `social.hapas.vn`.** Dự án, nguồn, ngân sách và người xem được sửa ở đây (xem `dashboard/README.md`).

**Mọi bước dưới đây cần người duyệt trước khi chạy trên VPS.**

## 0. Điều kiện trước khi tạo DB: platform quản trị được kho

Chủ dự án chốt ngày 14/10/2026: platform phải quản trị được kho ở mức tổng quan TRƯỚC khi kho được tạo.

- Thiết kế nằm ở bản nháp quyết định `KDLA` trong repo platform (`docs/decisions/drafts/KDLA-kho-du-lieu-rieng-cua-agent.md`), kèm các ca kiểm ở TESTCASES §61. Theo thiết kế:
  - kho được đăng ký trên console và admin duyệt;
  - Mark gửi ảnh chụp tổng quan lên platform;
  - platform giữ công tắc cho phép ghi.
- Điều kiện ban đầu là thint duyệt bản nháp `KDLA`, phần platform chạy và kho ở trạng thái `hoat_dong` rồi mới tạo DB.
  - **Ngày 14/10/2026 chủ dự án bỏ điều kiện này** (đã hỏi ý kiến trực tiếp): DB được tạo trên VPS lúc 21:45 khi KDLA còn là bản nháp. Khi KDLA chạy, đăng ký kho này trên console như mọi kho khác.

Mô tả bảng và cột theo quy chuẩn BI (task Lark t280613, skill `lsr-bq-description-standard`) đã nằm sẵn trong `schema.sql` dưới dạng `COMMENT ON`. Test `tests/test_theo_doi.py::test_kho_theo_quy_chuan_mo_ta_bi` kiểm việc này.

## 1. Tạo DB, role, bảng

```bash
sudo -u postgres env PGOPTIONS='-c lock_timeout=5s' psql -v ON_ERROR_STOP=1 -f deploy/lang-nghe/schema.sql
sudo -u postgres psql -d lang_nghe -c '\dt'        # 22 bảng (lich_quet 15/10, kiem_do_phu 17/10, han_muc_apify 18/10, don_vi + quyen 19/10/2026, yeu_cau_tuc_thi 20/10/2026,
# TikTok Ads 19/10/2026: ket_noi_ngoai, tk_quang_cao, qc_tk_ngay, qc_campaign_ngay, qc_ad_ngay, qc_khan_gia)
```

`lock_timeout=5s` cần khi DB đang chạy. Lệnh `ALTER TABLE` (ví dụ thêm `luot_quet.lich_id`) xin khoá độc quyền trên bảng.

- Mark hoặc dashboard đang giữ khoá đó thì lệnh tự dừng sau 5 giây và báo lỗi. Chạy lại là được.
- Không đặt `lock_timeout` thì lệnh đứng chờ khoá, và mọi truy vấn đến sau trên bảng đó xếp hàng phía sau nó, nên Mark và dashboard treo theo.

Lệnh trên tạo:

- DB `lang_nghe`.
- 3 role, đều đăng nhập qua Unix socket với xác thực `peer`, không có mật khẩu và không mở cổng:
  - `lang_nghe_chu`: chủ sở hữu bảng, không đăng nhập.
  - `mark`: trùng tên user hệ điều hành của bot.
  - `lang_nghe_web`: trùng tên user hệ điều hành của dashboard.

Chạy lại file này nhiều lần không hỏng gì.

Quyền của Mark:

- **Đọc:** `du_an`, `nguon`, `don_vi`; TikTok Ads (19/10/2026): `tk_quang_cao`, `qc_*` và ĐÚNG 6 cột không bí mật của `ket_noi_ngoai` (nha_cung_cap, loai, trang_thai, refresh_het_luc, goi_ok_luc, loi_cuoi — không bao giờ cột token); `lich_quet` chỉ các cột Mark dùng (không đọc email người tạo/sửa); `nguoi_xem (email, vai_tro, la_quan_tri)` + `quyen (email, don_vi, vai_tro)` cho hỏi đáp số liệu (chỉ trả số dự án của bên người hỏi, từ 19/10/2026).
- **Ghi:** `bai`, `chi_so_ngay`, `luot_quet`, `de_xuat`; `kiem_do_phu` chỉ thêm dòng (kiểm độ phủ 2 lần/tuần, từ 17/10/2026); `han_muc_apify` chỉ thêm dòng (ảnh chụp hạn mức gói Apify cho trang Ngân sách sau mỗi lượt và mỗi 3 giờ, từ 18/10/2026 — dashboard không giữ token Apify). `yeu_cau_tuc_thi` thêm (chỉ cột yêu cầu) + đọc + sửa cột kết quả dòng bài/kênh/quét (RLS) — số tức thì, từ 20/10/2026, mục 9; không quyền nào trên `nhat_ky`.
- **Chỉ sửa:** cột lần quét và lỗi của `nguon`; cột trạng thái chạy của `lich_quet` (`lan_chay_ke`, `lan_chay_cuoi`, `ket_qua_cuoi`, `so_lan_chay`).
- **Không được:** thêm hay xoá nguồn, sửa dự án, sửa ngân sách, tạo/sửa/xoá lịch.

## 2. Thư viện cho Mark

```bash
# venv Hermes do uv quản (không có pip); DEPS_CMD của agent-deploy chỉ `uv pip install` nên không gỡ psycopg
sudo -u mark env HOME=/opt/mark /usr/local/bin/uv pip install --python /opt/mark/hermes-agent/venv/bin/python 'psycopg[binary]>=3.2,<3.3'
sudo -u mark /opt/mark/hermes-agent/venv/bin/python -c "import psycopg; print(psycopg.__version__)"
sudo -u mark psql -d lang_nghe -c 'select count(*) from du_an'   # kiểm peer auth
```

Thiếu thư viện hoặc chưa có DB thì `/theodoi` báo "Kho lắng nghe chưa dùng được: …". Các tính năng khác của Mark không bị ảnh hưởng.

## 3. Biến môi trường của Mark (`/opt/mark/app/.env`)

```
# tuỳ chọn — mặc định "dbname=lang_nghe" (Unix socket, peer)
LANG_NGHE_DSN=dbname=lang_nghe
# báo dashboard có dữ liệu mới (cùng VPS); khoá = LANG_NGHE_BAO_KHOA bên dashboard
LANG_NGHE_BAO_URL=http://127.0.0.1:8090/noi-bo/co-du-lieu
LANG_NGHE_BAO_KHOA=<openssl rand -hex 32>
```

Không dán khoá vào chat, log hay commit. Sửa xong thì chạy `mark restart`.

## 4. Dự án đầu tiên

Cách chính là tạo dự án trên dashboard. Muốn thử trước khi có dashboard thì chạy lệnh dưới đây; nhớ sửa từ khoá, từ loại trừ và mô tả brand cho đúng trước khi chạy:

```bash
sudo -u lang_nghe_web psql -d lang_nghe <<'SQL'
INSERT INTO du_an (ma, ten, tu_khoa, tu_loai_tru, boi_canh, thi_truong, tran_usd_thang, sua_boi, don_vi)
VALUES ('hapas', 'HAPAS', '{hapas}', '{hapasguitars,"hapas ashen"}',
        'HAPAS — thương hiệu thời trang, túi xách, trang sức Việt Nam', 'VN', 5, 'cai-dat', 'hapas')
ON CONFLICT (ma) DO NOTHING;
SQL
```

## 5. Lịch chạy (trên console platform, không trên VPS)

Mở console, vào agent Mark, tab **Lịch chạy**, rồi tạo lịch mới:

- **Kiểu:** Giao việc (`run`)
- **Lặp:** hằng ngày, giờ tuỳ chọn
- **Nội dung:** `/theodoi hapas`
- **Nhận kết quả:** một nhóm Lark hoặc chat riêng có bot

Cũng có thể nhờ Mark đặt bằng tool `schedule_reminder`. Lịch kiểu `send` hoặc sai mã dự án sẽ bị từ chối ngay lúc đặt.

Lệnh chạy được với các điều kiện sau:

- Phải đang bật công tắc **Soi tài khoản**.
- Mỗi nền tảng phải đang bật trong **Năng lực → Quét mạng xã hội**. Nền tảng nào tắt thì nguồn của nền tảng đó được bỏ qua và Mark có nói rõ.
- Mỗi lượt bị giới hạn bởi trần USD trên console, cộng thêm trần tháng của dự án (mặc định 5 USD).

### 5b. Lịch quét tự động (dashboard, từ 15/10/2026)

Chủ dự án chốt "Dashboard + Mark tự chạy". Ngoài lịch console ở trên, người quản lý đặt lịch linh hoạt ở tab **Lịch quét** trên dashboard: mỗi N giờ trong khung giờ, hằng ngày, hằng tuần, hoặc chiến dịch (từ lúc → tới lúc, mỗi ≥ 30 phút).

- Mark chạy nhịp 30 giây (`quet_tu_dong.py`, khởi động trong `run.py` sau việc nền). Tới mốc thì tạo đúng việc `/theodoi` như lệnh gõ tay, cùng các điều kiện ở trên. Kết quả chỉ hiện trên dashboard, không nhắn Lark.
- Bỏ qua và ghi lý do vào lịch khi: lượt trước còn chạy, hết trần tháng của dự án, công tắc tắt, hoặc lỡ mốc quá 30 phút (Mark tắt). Mốc lỡ dưới 30 phút thì chạy bù một lần.
- Chiến dịch đang diễn ra thì lịch thường của cùng dự án nhường. Hết khung thì chiến dịch tự dừng.
- Mark chưa chạy lịch nào cho tới khi đọc được danh bạ platform (công tắc Năng lực) ít nhất một lần từ lúc khởi động. Máy thiếu cấu hình `LSR_*` thì lịch không chạy.
- Lịch sai giới hạn (ví dụ ghi thẳng bằng psql với khoảng dưới 30 phút) thì ngủ, ghi lỗi, chờ sửa trên dashboard. DB còn chặn thêm bằng ràng buộc `lich_quet_chien_dich_check`.
- Mỗi lượt báo platform một trace qua collector (`lsr_platform.bao_luot`), cả lượt bỏ qua, gồm `lich_id`, `du_an`, mốc, kết quả. Khi việc chạy xong có thêm một trace với chi phí thật. Lượt theo lịch dashboard không qua hàng đợi job của platform, nên đây là dấu vết duy nhất platform thấy.
- Tuỳ chọn trong `.env` của Mark:
  - `MARK_LICH_QUET_BAO_LOI=oc_…` (hoặc `ou_…`): nhận một tin cảnh báo cho mỗi lịch, mỗi loại (lỗi / hết ngân sách), mỗi ngày.
  - `MARK_LICH_QUET=0`: tắt hẳn nhịp.
- Kiểm: `sudo -u mark psql -d lang_nghe -c "select id, du_an, kieu, bat, lan_chay_ke, lan_chay_cuoi, ket_qua_cuoi->>'trang_thai' from lich_quet order by id"`.

## 6. Kiểm sau khi bật

```bash
sudo -u mark psql -d lang_nghe -c "select id, trang_thai, so_nguon, bai_moi, chi_phi_usd, loi from luot_quet order by id desc limit 5"
```

Gõ `/theodoi hapas` trong chat riêng với Mark. Mark trả về mã việc ngay; quét xong Mark nhắn kết quả, có chi phí thật kèm theo.

Thứ tự quét: YouTube trước vì miễn phí, rồi Instagram, TikTok, Facebook.

## 7. TikTok Ads (19/10/2026, chủ dự án chốt)

Dashboard đọc số quảng cáo TikTok qua TikTok for Business MCP (OAuth của một quản trị viên, chỉ công cụ ĐỌC — `dashboard/tiktok_ads.py`; xem `dashboard/README.md` mục "TikTok Ads"). Thứ tự triển khai: **khoá → schema → mã → bộ hẹn giờ → BigQuery → kết nối**.

```bash
# a. Khoá mã hoá token (32 byte base64) — một lần; không dán vào chat/log/commit
echo "TIKTOK_KHOA_MA_HOA=$(openssl rand -base64 32)" | sudo tee -a /opt/lang-nghe/.env >/dev/null
sudo stat -c '%a %U' /opt/lang-nghe/.env          # vẫn 600 root

# b. Schema (6 bảng mới + quyền; chạy lại không hỏng) TRƯỚC mã mới
sudo -u postgres env PGOPTIONS='-c lock_timeout=5s' psql -v ON_ERROR_STOP=1 -f deploy/lang-nghe/schema.sql

# c. Mã dashboard (rsync như dashboard/README.md bước 2) rồi
sudo systemctl restart lang-nghe-dashboard

# d. HAI bộ hẹn giờ (user lang_nghe_web, cùng venv + .env với dashboard):
#    tiktok-ads-dong-bo  — mỗi ngày 06:30 giờ VN
#    tiktok-ads-yeu-cau  — mỗi 2 phút (từ 20/10/2026), chỉ chạy khi có người bấm "Đồng bộ ngay" / vừa kết nối
#    (dashboard KHÔNG chạy đồng bộ trong tiến trình web, chỉ ghi cờ yêu cầu)
sudo install -o root -g root -m 0644 deploy/lang-nghe/tiktok-ads-dong-bo.service   deploy/lang-nghe/tiktok-ads-dong-bo.timer deploy/lang-nghe/tiktok-ads-yeu-cau.service   deploy/lang-nghe/tiktok-ads-yeu-cau.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tiktok-ads-dong-bo.timer tiktok-ads-yeu-cau.timer
systemctl list-timers 'tiktok-ads-*'
/opt/lang-nghe/venv/bin/python -c "import cryptography; print(cryptography.__version__)"   # ≥ 48
# in trạng thái (không in token) — chạy đúng user + .env của dịch vụ
sudo systemd-run --quiet --wait --pipe -p User=lang_nghe_web -p EnvironmentFile=/opt/lang-nghe/.env   -p WorkingDirectory=/opt/lang-nghe/app /opt/lang-nghe/venv/bin/python -m dashboard.tiktok_ads trang-thai
# chạy một lượt ngay (thay vì đợi 06:30): sudo systemctl start tiktok-ads-dong-bo.service
```

e. **BigQuery** (khi đã bật `BQ_DATASET`): chạy khối "TikTok Ads" ở cuối `deploy/lang-nghe/bigquery.sql` (5 bảng `tk_quang_cao`, `qc_tk_ngay`, `qc_campaign_ngay`, `qc_ad_ngay`, `qc_khan_gia` — mô tả 11 nhãn) TRƯỚC khi bật mã mới; chủ dự án duyệt trước khi chạy. Bộ hẹn giờ đẩy BigQuery ngay sau mỗi lượt đồng bộ có dòng mới.

f. **Kết nối**: quản trị viên mở `https://social.hapas.vn/quan-tri#tiktok` → "Đăng nhập TikTok để kết nối" → đăng nhập TikTok for Business bằng tài khoản thấy đủ các tài khoản quảng cáo → Authorize. Dashboard tự đăng ký client OAuth (không cần app developer, không cần khai redirect URL), lưu token mã hoá, đọc tài khoản (gán bên MATEMADE/HAPAS tự động), rồi ghi yêu cầu đồng bộ: trong ≤ 2 phút bộ hẹn giờ `tiktok-ads-yeu-cau` bắt đầu nạp 90 ngày (tài khoản lớn mất vài chục phút tới vài giờ; bị ngắt thì lượt sau đọc tiếp). Kiểm bảng "Tài khoản quảng cáo → bên".

- **Gia hạn**: mỗi lần đăng nhập dùng được đúng **30 ngày** (TikTok không gia hạn khi làm mới). Thẻ đếm ngược (vàng < 7 ngày, đỏ < 2 ngày); Mark nhắn trước 7/3/1 ngày tới `MARK_TIKTOK_NHAC` (`oc_…`/`ou_…` trong `/opt/mark/app/.env`, trống thì `MARK_LICH_QUET_BAO_LOI`). Gia hạn = bấm "Đăng nhập lại để gia hạn 30 ngày".
- **Chuyển sang token API không hết hạn**: tạo app trên TikTok for Business Developer (chỉ quyền đọc báo cáo/tài khoản), lấy "API access token", dán vào ô "Dùng token API không hết hạn" trên thẻ. Dashboard thử đọc trước khi lưu; `loai` đổi thành `api_token`, thẻ hiện "Không hết hạn", Mark thôi nhắc. Muốn quay lại OAuth: bấm Đăng nhập lại.
- **Ngắt**: nút "Ngắt kết nối" thu hồi token phía TikTok và xoá khỏi DB (số đã đồng bộ giữ nguyên).
- **Kiểm**: `journalctl -u tiktok-ads-dong-bo -u tiktok-ads-yeu-cau -n 50` (mỗi lượt in một dòng JSON tóm tắt, không token); `sudo -u lang_nghe_web psql -d lang_nghe -c "select trang_thai, refresh_het_luc, dong_bo_ok_luc, dong_bo_so_dong, dong_bo_loi from ket_noi_ngoai"`.
- **Đồng bộ lại một khoảng**: lệnh `systemd-run` như trên với `dong-bo --tu 2026-09-01 --den 2026-09-30` (hoặc `dong-bo --bu 30`); không chạy chồng với bộ hẹn giờ (khoá advisory — lượt sau tự bỏ qua).
- **Đổi bộ hẹn giờ yêu cầu sang 2 phút (20/10/2026)**: cài lại `tiktok-ads-yeu-cau.timer` (`OnUnitActiveSec=2min`), `sudo systemctl daemon-reload && sudo systemctl restart tiktok-ads-yeu-cau.timer`.

## 8. Meta Ads (20/10/2026, chủ dự án chốt)

Facebook / Instagram Ads đi CHUNG đường ống TikTok (`dashboard/meta_ads.py`; chi tiết `dashboard/README.md` mục "Meta Ads"): cùng bảng (`tk_quang_cao.nen_tang = 'meta'`, `qc_*`), cùng luật quyền / tiền, trang Quảng cáo (chỉ quản trị viên, lọc TikTok / Meta / Tất cả), Mark hỏi đáp bằng chữ. Token = token người dùng hệ thống **CHỈ ĐỌC** đang có trong `/opt/mark/app/.env` (`MARK_META_ADS_TOKEN`, quyền `ads_read` + `read_insights` + `public_profile`, `me` = mark_ads_reader). Không dùng MCP chính thức của Meta (xin `ads_management`). Thứ tự: **schema → mã → nhập token → bộ hẹn giờ → BigQuery**.

```bash
# a. Schema (thêm cột/ràng buộc, chạy lại không hỏng) TRƯỚC mã mới — cùng lệnh mục 7b
sudo -u postgres env PGOPTIONS='-c lock_timeout=5s' psql -v ON_ERROR_STOP=1 -f deploy/lang-nghe/schema.sql

# b. Mã dashboard (rsync như dashboard/README.md bước 2) rồi
sudo systemctl restart lang-nghe-dashboard

# c. Nhập token từ .env của Mark — KHÔNG in token: chỉ hai dòng MARK_META_* đi qua ống, lệnh đọc
#    STDIN, kiểm GET me + me/permissions (từ chối nếu có quyền ghi) + me/adaccounts, mã hoá bằng
#    TIKTOK_KHOA_MA_HOA (khoá chung), lưu danh sách DUYỆT = MARK_META_AD_ACCOUNT_IDS, gán bên, ghi
#    yêu cầu đồng bộ; in tóm tắt không bí mật (tên token, quyền, số tài khoản).
sudo grep -E '^MARK_META_(ADS_TOKEN|AD_ACCOUNT_IDS)=' /opt/mark/app/.env \
  | sudo systemd-run --quiet --wait --pipe -p User=lang_nghe_web -p EnvironmentFile=/opt/lang-nghe/.env \
      -p WorkingDirectory=/opt/lang-nghe/app /opt/lang-nghe/venv/bin/python -m dashboard.meta_ads \
      nhap-token --dang-env --ai deploy-20-10

# d. HAI bộ hẹn giờ: meta-ads-dong-bo (06:45 giờ VN hằng ngày) + meta-ads-yeu-cau (2 phút, chỉ chạy khi có cờ)
sudo install -o root -g root -m 0644 deploy/lang-nghe/meta-ads-dong-bo.service deploy/lang-nghe/meta-ads-dong-bo.timer \
  deploy/lang-nghe/meta-ads-yeu-cau.service deploy/lang-nghe/meta-ads-yeu-cau.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meta-ads-dong-bo.timer meta-ads-yeu-cau.timer
systemctl list-timers 'meta-ads-*'
sudo systemd-run --quiet --wait --pipe -p User=lang_nghe_web -p EnvironmentFile=/opt/lang-nghe/.env \
  -p WorkingDirectory=/opt/lang-nghe/app /opt/lang-nghe/venv/bin/python -m dashboard.meta_ads trang-thai
```

e. **BigQuery** (`BQ_QC_XUAT_TIEN=1` ở prod — tiền Meta đẩy như TikTok): chạy khối "Meta Ads (20/10/2026) — NÂNG CẤP BẢNG ĐÃ TẠO" ở CUỐI `deploy/lang-nghe/bigquery.sql` (thêm `tk_quang_cao.nen_tang`, `duyet` + cập nhật mô tả bảng/cột cho Meta) — chủ dự án duyệt trước khi chạy. Chưa chạy thì `dong_bo_bq` bỏ hai cột mới khỏi lượt + cảnh báo trên trang BigQuery, không hỏng bảng.

- **Chỉ đọc**: client chỉ GET `https://graph.facebook.com/<phiên bản>/` + đường trong danh sách (me, me/adaccounts, me/permissions, act_<số>, act_<số>/insights|campaigns|ads); tham số đổi phương thức (`method`, `_method`, `batch`) bị chặn; trang sau phải cùng đường; không theo chuyển hướng; có bài thử canh "0 byte ra mạng" khi sai. Token có `ads_management`, `business_management`, `*_manage*`… bị từ chối, không lưu.
- **Duyệt tài khoản**: chỉ tài khoản `duyet` mới được đọc số (danh sách nhập kèm token, thay `MARK_META_AD_ACCOUNT_IDS`). Tài khoản mới mà token thấy → "Chưa duyệt", quản trị viên tích "Duyệt" ở bảng "Tài khoản quảng cáo → bên" (trang Quản trị).
- **Gán bên tự động**: tên có MATEMADE / MATE MADE / MADEMATE → matemade; tên có chữ THAI → chưa gán (chỉ quản trị viên thấy; chưa làm HAPAS Thái đợt này); còn lại → hapas. Quản trị viên sửa thì giữ.
- **Đổi token**: dán token mới trên thẻ "Kết nối Meta Ads" (giữ danh sách duyệt) hoặc chạy lại bước c (đặt lại danh sách duyệt theo .env). Thu hồi token cũ trong Meta Business Settings → Người dùng hệ thống (dashboard không thu hồi được bằng quyền đọc; "Ngắt" chỉ xoá bản trên máy chủ).
- **Kiểm**: `journalctl -u meta-ads-dong-bo -u meta-ads-yeu-cau -n 50`; `sudo -u lang_nghe_web psql -d lang_nghe -c "select nha_cung_cap, trang_thai, chu_token, quyen_token, dong_bo_ok_luc, dong_bo_loi from ket_noi_ngoai"`.

### Đồng bộ bấm tay cho mọi người có quyền (20/10/2026)

Dải "Số quảng cáo" (trang Chỉ số cho mọi người có quyền ở ít nhất một bên; trang Quảng cáo cho quản trị viên) hiện mỗi nền tảng: số đến ngày nào, đồng bộ lúc nào, trạng thái (ổn / có lỗi / đang chạy / đã yêu cầu) — không tiền, không số liệu — và nút **Đồng bộ ngay** (`POST /quang-cao/dong-bo`, CSRF). Nút chỉ ghi cờ yêu cầu loại **nhanh**: hôm nay + 2 ngày trước, chỉ tài khoản có hiển thị trong 30 ngày (xong trong vài phút); bộ hẹn giờ `*-yeu-cau` (2 phút) chạy. Đang chạy / đang có yêu cầu → không tạo mới, trả lời "Đang có yêu cầu lúc HH:MM (ai)" / "đang chạy từ HH:MM"; sau một lượt nhanh phải chờ 15 phút. Yêu cầu đầy đủ của quản trị viên đang chờ không bị hạ thành nhanh. Bộ hẹn giờ hằng ngày giữ đọc lại 7 ngày. Nạp lùi, kết nối, ngắt, gán bên: vẫn chỉ quản trị viên. Nhật ký: `dong_bo_qc` kiểu `bam_tay`.

## 9. Số tức thì của Mark (20/10/2026, chủ dự án chốt) — cần người duyệt trước khi chạy trên VPS

Mark (tool `lay_so_tuc_thi`, `tuc_thi_tool.py`) lấy số MỚI khi người hỏi cần: đọc lại số TikTok /
Meta Ads của bên họ (≤ 7 ngày gồm hôm nay), chỉ số hiện tại của ≤ 5 link bài / ≤ 2 kênh (Apify),
mở một lượt quét lắng nghe dự án. Mark KHÔNG cầm token quảng cáo: nó chỉ thêm dòng
`yeu_cau_tuc_thi`; trigger gọi `pg_notify('qc_tuc_thi', …)`; bộ nghe `tiktok-ads-nghe` /
`meta-ads-nghe` (user lang_nghe_web, `dashboard/nghe_qc.py`) chạy lượt đọc chỉ các tài khoản đó
rồi đánh dấu xong; Mark chờ ≤ 330 giây (kẹp dưới mốc chặn của đồng hồ lượt) rồi trả số từ kho kèm giờ cập nhật TỪNG nền tảng (đủ / một
phần / chưa đọc lại được).

```bash
cd /opt/lang-nghe/app   # sau khi rsync mã mới (dashboard/README.md bước 2) — Mark tự lên qua agent-deploy
# a. Schema (bảng yeu_cau_tuc_thi + 2 trigger + RLS + quyền; chạy lại không hỏng) TRƯỚC mã mới — như mục 7b
sudo -u postgres env PGOPTIONS='-c lock_timeout=5s' psql -v ON_ERROR_STOP=1 -f deploy/lang-nghe/schema.sql
sudo -u postgres psql -d lang_nghe -c '\dp yeu_cau_tuc_thi' -c "select policyname, roles, cmd from pg_policies where tablename='yeu_cau_tuc_thi'"
# b. Lượt hằng ngày nay tự CHỜ khoá (--cho-khoa-phut 120); KHÔNG chạy lại bằng systemd (systemd 255
#    từ chối RestartForceExitStatus với Type=oneshot — thử trên VPS 20/10); hỏng → OnFailure=qc-dong-bo-loi@<ncc>
sudo install -o root -g root -m 0644 deploy/lang-nghe/tiktok-ads-dong-bo.service \
  deploy/lang-nghe/meta-ads-dong-bo.service deploy/lang-nghe/qc-dong-bo-loi@.service /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/tiktok-ads-dong-bo.service \
  /etc/systemd/system/meta-ads-dong-bo.service
# c. Hai bộ nghe (chạy lâu dài, Restart=always; cùng hardening với *-ads-yeu-cau)
sudo install -o root -g root -m 0644 deploy/lang-nghe/tiktok-ads-nghe.service \
  deploy/lang-nghe/meta-ads-nghe.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tiktok-ads-nghe.service meta-ads-nghe.service
journalctl -u tiktok-ads-nghe -u meta-ads-nghe -n 20      # "đang nghe kênh qc_tuc_thi"
# d. Thử (không cần Mark): xử lý hàng chờ một lần
sudo systemd-run --quiet --wait --pipe -p User=lang_nghe_web -p EnvironmentFile=/opt/lang-nghe/.env \
  -p WorkingDirectory=/opt/lang-nghe/app /opt/lang-nghe/venv/bin/python -m dashboard.nghe_qc tiktok_ads --mot-lan
```

- **Lượt hằng ngày không bao giờ lặng lẽ mất** (soát H2): `dong-bo` hằng ngày gặp lượt nhỏ đang giữ
  khoá thì CHỜ trong tiến trình (thử lại mỗi 30 giây, tối đa `--cho-khoa-phut`: đơn vị đặt 120, mặc
  định CLI 30), vẫn không có khoá → thoát 3. systemd KHÔNG chạy lại (thử trên VPS 20/10/2026: systemd
  255 từ chối `RestartForceExitStatus` với `Type=oneshot` — đơn vị không nạp được). Mọi lỗi, kể cả bị
  giết vì quá `TimeoutStartSec=6h`: KHÔNG chạy lại (không vòng lặp giữ khoá cả ngày) — nạp lùi 90
  ngày dở dang, lượt hằng ngày hôm sau đọc tiếp nhờ mốc `tk_quang_cao.nap_lui_tu` ghi sau mỗi cửa sổ
  30 ngày. Hỏng hẳn → `OnFailure=qc-dong-bo-loi@<ncc>.service` đặt thẻ kết nối "lỗi" + lý do (quản
  trị viên thấy trên trang Quảng cáo); xử lý xong: `systemctl reset-failed tiktok-ads-dong-bo
  meta-ads-dong-bo`. Khung 06:25–07:30 giờ VN: bộ nghe, bộ hẹn giờ 2 phút và Mark KHÔNG mở lượt đọc
  tức thì / lượt bấm tay nào — kể cả cờ đầy đủ của quản trị viên (yêu cầu chờ → bo_qua, Mark trả số
  đã có và nói đồng bộ hằng ngày đang chạy; cờ "Đồng bộ ngay" giữ tới sau 07:30).
- **Bộ nghe** (soát H1, L4): chỉ mở lượt NHANH của dashboard (câu UPDATE bắt đầu lượt chỉ khớp cờ
  nhanh), lượt đầy đủ để bộ hẹn giờ; không chạy được (khoá bận, chưa kết nối, thiếu khoá) → chờ
  thông báo / 60 giây, không quay vòng.
- **Dự phòng**: bộ hẹn giờ `*-ads-yeu-cau` (2 phút) cũng xử lý hàng chờ — bộ nghe dừng thì yêu cầu
  vẫn chạy (chậm ≤ 2 phút; quá thời gian chờ Mark trả số cũ kèm giờ cập nhật). Nút "Đồng bộ ngay" loại
  nhanh của dashboard cũng NOTIFY → bộ nghe chạy ngay.
- **Độ mới trung thực** (soát M1, N1): lượt gộp nhiều yêu cầu chia lại cho TỪNG dòng — `so_tk_ok` =
  tài khoản CỦA dòng đó đọc được, `chi_tiet.tk_doc` / `tk_hong` (lý do từng tài khoản); 0 tài khoản →
  loi / bo_qua (không bao giờ xong); thiếu → xong + "một phần". Mark nói từng nền tảng theo ĐÚNG tài
  khoản của người hỏi (kể cả dòng dùng lại của người khác); tài khoản múi giờ sau giờ VN mà "hôm nay"
  ở đó chưa bắt đầu → nói rõ lý do. Sau lượt của bộ nghe có ghi dòng → đẩy BigQuery, giãn 10 phút.
- **Trần** (chống nền tảng chặn + chi phí; đếm NGUYÊN TỬ bằng khoá advisory trong CSDL): phía Mark
  (`/opt/mark/app/.env`, tuỳ chọn) — `MARK_TUC_THI_QC_NGUOI_GIO` 6 yêu cầu đọc quảng cáo/người/giờ
  (một yêu cầu cả TikTok + Meta tính 1), `MARK_TUC_THI_QC_GIO` 12/nhà cung cấp/giờ, cùng phạm vi
  trong 5 phút dùng lại lượt trước; `MARK_TUC_THI_BAI_LUOT` 5 link/lần, `MARK_TUC_THI_BAI_NGAY` 30
  link/người/ngày, `MARK_TUC_THI_KENH_LUOT` 2, `MARK_TUC_THI_KENH_NGAY` 10 kênh/người/ngày,
  `MARK_TUC_THI_QUET_NGAY` 2 lượt quét theo yêu cầu/bên/ngày (dự án chưa có bên: theo chính dự án).
  Phía dịch vụ (`/opt/lang-nghe/.env`) — `QC_TUC_THI_TRAN_GIO` 12 lượt/nhà cung cấp/giờ (chốt thứ
  hai); chờ quá 15 phút → bo_qua, chạy quá 60 phút → loi (cả dòng bài/kênh/quét kẹt).
- **Tiền**: quảng cáo = API nền tảng (miễn phí, chỉ đọc). Bài / kênh / quét = Apify: kiểm gói Apify
  trước (không hỏi được gói → KHÔNG chạy), chi phí thật ghi sổ `chi_phi_tool` +
  `yeu_cau_tuc_thi.chi_phi_usd`; lượt quét đi đúng đường `/theodoi` (trần tháng dự án, ngân sách
  việc nền). Phần tốn tiền phải xác nhận (soát M2, M3): ước tính → "Chạy nhé?" → mã xác nhận CHỈ
  dùng được ở đúng tin nhắn KẾ TIẾP của người đó trong cùng chat (qua thêm một tin → hết hạn), cùng
  phạm vi, 15 phút, một lần. Số USD của lượt quét = ĐÚNG mức `tao_luot` giữ chỗ (nguồn + từ khoá +
  bình luận + kiểm độ phủ, `theo_doi.uoc_giu_cho`) và bị buộc vào mã: lúc chạy cần giữ nhiều hơn →
  không tạo, hỏi lại.
- **Quyết định của chủ dự án (M4)**: người có vai trò Chỉ xem ở bên cũng mở được lượt quét theo
  yêu cầu — tức là tiêu ngân sách tháng của dự án. Câu xác nhận nói rõ số USD và ngân sách dự án bị
  trừ. Muốn chỉ Quản lý được mở quét thì đổi ở `tuc_thi_tool.quet` (dùng `PQ.sua_duoc`).
- **Quyền** (soát M5): như `hoi_dashboard` — chat riêng / web đã xác thực, có vai trò ở ≥ 1 bên;
  chỉ tài khoản / dự án bên mình; tài khoản chưa gán bên chỉ quản trị viên. Role `mark`: SELECT
  `yeu_cau_tuc_thi`, INSERT CHỈ các cột yêu cầu (trạng thái, mốc giờ, kết quả do trigger
  `chuan_yeu_cau_tuc_thi` đặt), UPDATE cột kết quả và CHỈ dòng bài/kênh/quét (RLS). KHÔNG quyền nào
  trên `nhat_ky` (dòng "mark_real_time" do trigger SECURITY DEFINER ghi), `ket_noi_ngoai`, `qc_*`.
- **Kiểm**: `sudo -u lang_nghe_web psql -d lang_nghe -c "select id, loai, nha_cung_cap, trang_thai,
  so_muc, so_tk_ok, so_dong, loi, tao_luc, xong_luc from yeu_cau_tuc_thi order by id desc limit 20"`;
  nhật ký: `select * from nhat_ky where hanh_dong = 'mark_real_time' order by id desc limit 20`.
- **Gỡ**: `systemctl disable --now tiktok-ads-nghe meta-ads-nghe` (bộ hẹn giờ vẫn xử lý hàng chờ).
  Tắt hẳn phía Mark: `MARK_TUC_THI=0` trong `/opt/mark/app/.env` rồi `mark restart` (tool trả lời
  "đang tắt"; chưa có công tắc console riêng cho `lay_so_tuc_thi`).

## 10. Tạo Lark Sheet từ trang Quảng cáo (20/10/2026, chủ dự án chốt) — cần người duyệt trước khi chạy trên VPS

Trang Quảng cáo (chỉ quản trị viên) có mục **Tạo Lark Sheet**: xuất số theo ĐÚNG bộ lọc đang xem (bên,
nền tảng, tài khoản, từ–đến) thành MỘT Lark Sheet riêng tư — Tổng quan + ba tab: *Theo ngày × tài
khoản*, *Theo chiến dịch*, *Theo quảng cáo* (tổng cả kỳ; tối đa 20.000 / 5.000 / 10.000 dòng, cắt thì
Tổng quan nói rõ). Có chi tiêu và chỉ số suy ra như trang (CPM, CPC, CTR, chi / 1.000 view, chi /
follow, chi / kết quả). Cột Doanh thu Shop + ROAS Shop tạm gỡ từ 22/10/2026 (chủ dự án: nền tảng
đo khác cách công ty tự tính; dữ liệu vẫn lưu, bật lại bằng `quang_cao.HIEN_DOANH_THU = True`).
TikTok và Meta cùng đường (cùng bảng `qc_*`); tên file ghi nền
tảng ("TikTok Ads · HAPAS · 01/10–19/10/2026").

Đường đi: dashboard (lang_nghe_web) KHÔNG có app Lark tạo Sheet — chỉ thêm dòng `yeu_cau_sheet_qc`
(RLS: chỉ dòng của chính người đăng nhập; trigger đặt trạng thái + kiểm trần). Trigger gọi
`pg_notify('qc_sheet', id)`; bộ nghe **`qc-sheet-nghe`** (user **mark**, `xuat_sheet_qc.py`, venv + `.env`
của Mark) kiểm lại người bấm còn là quản trị viên, tính lại phạm vi, đọc số bằng role `mark`, tạo Sheet
bằng app Lark của Mark (khoá chia sẻ link TRƯỚC khi ghi số — đúng đường `chi_so_ads`), chia sẻ quyền
**xem** cho email người bấm, nhắn link trên Lark, ghi trạng thái + link. Trang hỏi lại 5 giây một lần
khi còn yêu cầu đang tạo.

**22/10/2026 (chủ dự án) — một chỗ, đúng bộ lọc**: mục riêng "Tạo Lark Sheet" bỏ; nút **"Xuất Lark Sheet
theo bộ lọc này"** + danh sách Sheet gần đây nằm cuối mục *Chiến dịch và quảng cáo*. Yêu cầu mang thêm
nhiều tài khoản (`tk_ds`, ≤ 200 mã; chọn đủ = NULL = mọi tài khoản) và bộ lọc bảng (`tim`, `cd`, `sap`,
`chieu`). Tab chiến dịch / quảng cáo lọc + xếp bằng CHÍNH SQL của bảng trang (`kho_qc.sql_bang` qua
`kho_sheet_qc.doc_tong`), MỌI dòng khớp (không chỉ trang đang xem) tới trần; tab theo ngày chỉ theo tài
khoản + ngày; Tổng quan ghi bộ lọc đã dùng. Dòng cũ (cột mới NULL) dựng như trước. Lên mã: chạy
`schema.sql` (thêm 5 cột NULL — tức thì, không viết lại bảng; trigger kiểm giá trị) TRƯỚC khi khởi động
lại dashboard / Mark — mã mới đọc + ghi các cột này.

**22/10/2026 (chủ dự án) — hỏi Mark vẫn xuất Sheet được**: tool **`xuat_sheet_qc`** của Mark
(`sheet_qc_tool.py`) thêm dòng `yeu_cau_sheet_qc` với `nguon = 'mark'`, `nguoi_hoi` = email người hỏi đã
xác thực (chat riêng Lark / web console, cùng cửa `hoi_dashboard`), chỉ tài khoản trong các bên người đó
đọc được; bộ nghe dựng CÙNG Sheet và nhắn link cho chính người hỏi. Mark chỉ gọi khi người hỏi đòi Sheet /
file / xuất / tải về (lời dặn: mô tả tool, `skills/hoi-dashboard-lang-nghe.md`, `brain.py`); còn lại
vẫn trả lời bằng chữ. **Luật cứng ở bộ nghe** (không tin dòng, kể cả của Mark): dòng `web` vẫn chỉ quản
trị viên; dòng `mark` cần người còn quyền ở bên — phạm vi tài khoản tính lại từ quyền CSDL của
`nguoi_hoi` lúc dựng (mã ngoài phạm vi bị bỏ, Tổng quan + tin nhắn nói số đã bỏ; "Tất cả bên" / "Chưa
gán bên" chỉ quản trị viên), và **không xem tiền (`quang_cao.xem_tien`) của mọi tài khoản trong Sheet →
Sheet không có cột / giá trị tiền nào** (chi, CPM, CPC, chi / …, doanh thu; dòng TỔNG gộp mọi tiền tệ;
không xếp theo tiền). Không đọc được quyền → không Sheet. Đổi quyền giữa lượt → không chia sẻ. Trần
(trigger) đếm CHUNG hai nguồn. Thứ tự lên: **schema (cột `nguon` + quyền INSERT của mark + RLS
`sheet_qc_them_mark`) → mã Mark** (bộ nghe đọc `nguon`; tool ghi `nguon`) — mã mới trên schema cũ thì
bộ nghe lỗi "column nguon does not exist" tới khi chạy schema. Dashboard không đổi mã.

```bash
cd /opt/lang-nghe/app   # sau khi rsync mã mới (dashboard/README.md bước 2) — Mark tự lên qua agent-deploy
# a. Schema TRƯỚC mã mới (bảng yeu_cau_sheet_qc + 2 trigger + RLS + quyền theo cột; chạy lại không hỏng)
sudo -u postgres env PGOPTIONS='-c lock_timeout=5s' psql -v ON_ERROR_STOP=1 -f deploy/lang-nghe/schema.sql
sudo -u postgres psql -d lang_nghe -c '\dp yeu_cau_sheet_qc'   -c "select policyname, roles, cmd from pg_policies where tablename='yeu_cau_sheet_qc'"
# b. Dashboard mới (mục Tạo Lark Sheet; bỏ "Đồng bộ ngay" ở thẻ Quản trị + dải trên trang Chỉ số)
sudo systemctl restart lang-nghe-dashboard
# c. Bộ nghe phía Mark (mã đã có ở /opt/mark/app qua agent-deploy; kiểm trước khi cài)
test -f /opt/mark/app/xuat_sheet_qc.py && sudo -u mark /opt/mark/hermes-agent/venv/bin/python -c   "import psycopg, sys; assert tuple(map(int, psycopg.__version__.split('.')[:2])) >= (3, 2), psycopg.__version__; sys.path.insert(0, '/opt/mark/app'); import xuat_sheet_qc; print('ok', psycopg.__version__)"
sudo install -o root -g root -m 0644 deploy/lang-nghe/qc-sheet-nghe.service /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/qc-sheet-nghe.service
sudo systemctl daemon-reload
sudo systemctl enable --now qc-sheet-nghe.service
journalctl -u qc-sheet-nghe -n 20                          # "đang nghe kênh qc_sheet"
# d. Thử: bấm Tạo Sheet trên trang Quảng cáo (khoảng 7 ngày), xem journalctl; hoặc xử lý hàng chờ một lần:
sudo systemd-run --quiet --wait --pipe -p User=mark -p WorkingDirectory=/opt/mark/app   /opt/mark/hermes-agent/venv/bin/python -m xuat_sheet_qc --mot-lan
```

- **Theo Mark khi tự lên mã**: agent-deploy chỉ khởi động lại unit `mark` (`agentctl restart mark`).
  Unit có `PartOf=mark.service` + `After=mark.service` nên khởi động lại (và dừng) cùng Mark — không
  chạy mã cũ sau mỗi lần Mark tự cập nhật; `WantedBy=multi-user.target` giữ nó bật lúc khởi động máy.
  Kiểm: `systemctl show -p PartOf qc-sheet-nghe` → `PartOf=mark.service`.
- **Biến môi trường**: không thêm biến nào. Bộ nghe dùng `LARK_APP_ID` / `LARK_APP_SECRET` /
  `LANG_NGHE_DSN` sẵn có trong `/opt/mark/app/.env` (config.py tự nạp). Dashboard không thêm gì
  (`DASH_LARK_APP_*` vẫn chỉ để đăng nhập).
- **Quyền app Lark của Mark** (đã có cho `chi_so_ads` / `social_listen`): tạo Sheet, sửa quyền Drive
  (thêm cộng tác viên theo email, đóng chia sẻ link), gửi tin `im:message`. Tra email → open_id
  (`contact:user.id:readonly`) chỉ là đường lùi khi thêm quyền theo email bị từ chối.
- **Trần**: 1 yêu cầu đang chờ / đang tạo mỗi người, 4 yêu cầu mỗi người mỗi giờ, 30 mỗi giờ toàn hệ
  thống (trigger `chuan_yeu_cau_sheet_qc`, khoá advisory); khoảng ≤ 400 ngày. Trigger kiểm bộ lọc
  (22/10/2026): `tim` ≤ 100 ký tự, `cd` ~ `^[0-9A-Za-z_-]{0,64}$`, `sap` trong danh sách cột xếp,
  `chieu` ∈ (giam, tang), `tk_ds` ≤ 200 mã dạng advertiser_id — sai thì `invalid_parameter_value`. Chờ / đang tạo quá 30
  phút → `loi` (bộ nghe dọn; trang hiện "Quá hạn" và cho bấm lại).
- **Quyền DB**: lang_nghe_web INSERT chỉ (nguoi_hoi, ben, nen_tang, tk, tk_ds, tu, den, tim, cd, sap,
  chieu), SELECT mọi cột trừ
  `loi_noi_bo`, không UPDATE / DELETE; RLS theo `lang_nghe.nguoi` (app đặt bằng `set_config` trong
  cùng giao dịch). mark: SELECT, UPDATE chỉ cột kết quả, không DELETE; từ 22/10/2026 INSERT chỉ
  (nguoi_hoi, ben, nen_tang, tk, tk_ds, tu, den, tim, cd, sap, chieu, nguon) + USAGE sequence, RLS
  `sheet_qc_them_mark` WITH CHECK (nguon = 'mark') — web không được cấp cột `nguon` (luôn 'web').
  Trigger BEFORE INSERT chạy cho mọi role (trần + kiểm bộ lọc áp cho dòng Mark); khoá advisory
  `sheet_qc|<email>` rồi `sheet_qc|*` là khoá cả CSDL nên web và Mark cùng người xếp hàng nhau, cùng
  thứ tự khoá (người → toàn hệ thống) nên không khoá chéo.
- **Kiểm**: `sudo -u mark psql -d lang_nghe -c "select id, nguoi_hoi, nen_tang, ben, tu, den,
  tk_ds, tim, cd, sap, chieu, nguon, trang_thai, so_dong, loi, loi_noi_bo, da_nhan_tin, tao_luc, xong_luc
  from yeu_cau_sheet_qc order by
  id desc limit 20"`; nhật ký: `select * from nhat_ky where hanh_dong = 'tao_sheet_qc' order by id desc`.
- **Gỡ**: `systemctl disable --now qc-sheet-nghe` (yêu cầu mới chờ 30 phút rồi thành "Quá hạn"; trang
  vẫn chạy).

## 11. KOC affiliate (gắn giỏ) vs KOC branding (20–21/10/2026, task Lark t284905, PA1)

Cờ giỏ TikTok Shop theo từng video vào `bai.gio_hang` (+ `bai.la_quang_cao` = is_ads). TRUE = KOC
affiliate, FALSE = KOC branding — dashboard chỉ HAI nhóm (chủ dự án 20/10 tối); NULL (video không
đọc lại được giỏ: chưa thử, hoặc hồ sơ không còn thấy video) là một dòng mờ dưới khối. Cờ theo loại phản hồi (`tiktok_api.DAY_DU` /
`FEED` / `CHI_TIET`): tìm kiếm / hồ sơ không có anchor shop = FALSE; feed hashtag chỉ tin TRUE
(không bao giờ trả anchor shop); `post` thiếu anchors = NULL. Ghi kho: TRUE dính, FALSE chỉ điền
chỗ NULL, NULL không đè.

**Thứ tự — BigQuery TRƯỚC** (đồng bộ `bai` đi theo mốc `cap_nhat_cuoi`; dòng đẩy lên lúc BigQuery
chưa có cột thì lần sau không đẩy lại, nên không để dòng có cờ đồng bộ trước khi BigQuery có cột):

1. Sao lưu DB (mục Vận hành).
2. BigQuery: chạy khối cuối `bigquery.sql` (`ALTER TABLE … SOCIAL_LISTENING.bai ADD COLUMN IF NOT
   EXISTS gio_hang, la_quang_cao`). Postgres chưa có cột thì `dong_bo_bq` tự bỏ hai cột (cảnh báo).
3. Postgres: `schema.sql` (mục 1) — thêm hai cột NULL được, chỉ đổi danh mục.
4. Lên code (merge `main`, agent-deploy) → `mark restart`, khởi động lại dashboard. Bản code lên
   trước schema vẫn chạy (hỏi `information_schema`, nhớ "chưa có cột" 5 phút).
5. Bù bài cũ từ raw đã trả tiền (0 USD), chạy thử rồi ghi:
   ```bash
   sudo -u mark $PY scripts/lang_nghe_nap_gio_hang.py hapas /opt/mark/raw-kompa-1810
   sudo -u mark $PY scripts/lang_nghe_nap_gio_hang.py hapas /opt/mark/raw-kompa-1810 --ghi        --sao-luu /opt/mark/gio-hang-$(date +%F).jsonl
   ```
   Raw kompa + vòng 2–3 (172 tệp, đo 21/10/2026): 3.660 video — giỏ 1.575, không giỏ 966, chưa rõ
   1.119 (1.118 chỉ thấy ở feed hashtag).
6. TRẢ TIỀN (chủ dự án duyệt ≤ 10 USD, chạy với trần 9 USD): bài còn NULL đọc qua HỒ SƠ nhà
   sáng tạo (userPosts, `aweme` đầy đủ). Chạy thử trước (in tài khoản, video cần tìm, yêu cầu, USD
   và số tài khoản trần đủ), rồi chạy thật:
   ```bash
   sudo -u mark $PY scripts/lang_nghe_nap_gio_hang.py hapas --doc-ho-so --toi-da-usd 9
   sudo -u mark $PY scripts/lang_nghe_nap_gio_hang.py hapas --doc-ho-so --toi-da-usd 9 --ghi        --sao-luu /opt/mark/gio-ho-so-$(date +%F).jsonl
   ```
   Mỗi tài khoản tối đa 1 hồ sơ + 3 trang (`--so-trang`) × 0,002 USD; tài khoản nhiều video chưa rõ
   trước; trần = min(9, còn tháng dự án, ngân sách Apify việc nền), một lượt `theo_doi` riêng
   ("gio-ho-so-…") nên tiền vào trần tháng. Video không thấy giữ NULL ("chưa đọc lại được").
   Chạy từng phần ~2 USD (`--toi-da-usd 2`, lặp lại tới khi hết 9 USD hoặc hết video): cứ 20 tài
   khoản ghi kho + sao lưu + cập nhật chi phí đang tiêu của lượt (lượt khác thấy ngay); dừng sạch ở
   `--het-gio HH:MM` (mặc định 06:50 nếu bắt đầu trước — trước lượt quét 07:00) hoặc sau
   `--toi-da-phut` (150, dưới 3 giờ "bỏ dở"); chết / Ctrl-C thì lượt đóng `loi` với đúng tiền đã
   tiêu, chạy lại là làm tiếp (bài đã có cờ không còn NULL).
   (Đường cũ `--goi-api`: đọc từng video qua `post`, phản hồi có thể thiếu anchors — không dùng.)
7. Về sau, mỗi lượt tìm TikTok tự đọc hồ sơ cho video lượt đó còn NULL (chỉ thấy ở feed hashtag),
   trần `LANG_NGHE_GIO_HO_SO_USD` trong `/opt/mark/app/.env` (mặc định 0,05 USD/lượt, 0 = tắt),
   tính vào chi phí lượt (phần `tiktok_gio_ho_so`; ghi chú lượt "cờ giỏ qua hồ sơ TikTok: …"); trần
   tính sau khi trừ tiền tìm + làm mới của lượt; lỗi bước này không làm hỏng lượt. Tài khoản đã thử
   mà chưa thấy video thì 7 ngày không thử lại (`.audit/viec-nen/.gio-ho-so.json`; script dùng sổ
   này khi có `--theo-so-nho`).
8. Kiểm: `select gio_hang, count(*) from bai where du_an = 'hapas' and nen_tang = 'tiktok' group
   by 1`; dashboard trang Chỉ số → khối "KOC affiliate vs KOC branding", ô lọc "Loại KOC".

## 12. Kênh đăng của quảng cáo (22/10/2026, chủ dự án chốt) — cần người duyệt trước khi chạy trên VPS

Trang Quảng cáo tách mỗi tài khoản theo kênh đăng (TikTok: tài khoản chính chủ / KOC Spark Ads;
Meta: Trang + Instagram) — `dashboard/README.md` mục "Kênh đăng của quảng cáo". Hai bảng mới
`qc_ad_kenh`, `qc_kenh`; bộ đồng bộ TikTok / Meta hằng ngày tự điền (chỉ đọc; lỗi không làm hỏng lượt).

1. Postgres: `schema.sql` (mục 7b — CREATE bảng mới + GRANT; chạy lại không hỏng).
2. BigQuery: khối "Kênh đăng của quảng cáo" trong `bigquery.sql` (hai CREATE TABLE IF NOT EXISTS,
   người duyệt rồi mới chạy). Chưa chạy thì trang "Kết nối BigQuery" báo lỗi riêng hai bảng này.
3. Lên code, khởi động lại dashboard. Lượt 06:30 / 06:45 sáng hôm sau đọc kênh lần đầu (≈ 175 lượt
   TikTok + ≈ 35 lượt Meta, ad chi nhiều trước); muốn sớm hơn: `sudo systemctl start
   tiktok-ads-dong-bo.service` / `meta-ads-dong-bo.service`.
4. **Chủ dự án — tên Trang Facebook / Instagram**: tạo lại token người dùng hệ thống `mark_ads_reader`
   trong Meta Business Settings, tick thêm **`pages_read_engagement`** (chỉ đọc) bên cạnh
   `ads_read` + `read_insights`, giao quyền xem các Trang đứng tên quảng cáo cho người dùng hệ thống,
   rồi dán ở thẻ "Kết nối Meta Ads" (hoặc `nhap-token` như mục 8c). Dashboard chỉ nhận đúng các quyền
   `ads_read`, `read_insights`, `public_profile`, `pages_read_engagement` — tick thêm quyền khác (nhất
   là ads_management, business_management, *_manage*) là bị từ chối. Chưa làm bước này: bảng hiện
   "Page <id>" / "IG <id>", số vẫn đủ.
5. Kiểm: `select nen_tang, loai, count(*) from qc_ad_kenh group by 1, 2;` và
   `select count(*) filter (where ten is not null), count(*) from qc_kenh;` — trang Quảng cáo, khối
   "Theo kênh đăng" (dòng phụ "x% chi tiêu đã biết kênh").

## Vận hành

- **Sao lưu:**
  ```bash
  sudo -u postgres pg_dump -Fc lang_nghe > /opt/lang-nghe/backup/lang_nghe-$(date +%F).dump
  ```
- **Lượt bị bỏ dở:** lượt kẹt ở `dang_chay` quá 3 giờ (bot tắt giữa chừng) sẽ tự đóng thành `loi` ở lượt sau.
- **Lọc lại bình luận cũ theo luật spam mới** (16/10/2026, spam affiliate "dán mã vào Shopee"): không gọi AI, chỉ hạ `hop_le`/`trung` → `spam`. Xem trước rồi mới ghi:
  ```bash
  cd /opt/mark/app
  PY=/opt/mark/hermes-agent/venv/bin/python
  sudo -u mark $PY scripts/lang_nghe_loc_lai.py --mau 10                  # xem trước, chỉ đọc, tác giả đã che
  sudo -u mark $PY scripts/lang_nghe_loc_lai.py --ap-dung --sao-luu /opt/mark/loc_lai-$(date +%F).json
  sudo -u mark $PY scripts/lang_nghe_loc_lai.py --hoan-tac /opt/mark/loc_lai-<ngày>.json   # nếu cần trả lại
  ```
  Đọc tay nhóm "CẦN ĐỌC TAY" (hàng loạt không có mã) trước khi ghi. `--ap-dung` ghi nhãn cũ vào tệp `--sao-luu` (không ghi đè tệp có sẵn) rồi mới sửa; `--hoan-tac` chỉ trả dòng còn đúng nhãn script đặt. Từ lượt quét sau, luật mới tự chạy (từng bình luận + cấp bài: ≥ 5 tài khoản / 48 giờ theo giờ đăng).
- **Gộp bài Facebook trùng** (17/10/2026: pfbid đổi mỗi lượt cào, 161 bài FB của hapas có 24 nhóm trùng, thừa 36 dòng). Chạy SAU khi code mới + `schema.sql` (cột `bai.ma_so_fb`) đã lên VPS; mark không có DELETE trên `bai` nên cấp tạm rồi thu lại:
  ```bash
  cd /opt/mark/app
  PY=/opt/mark/hermes-agent/venv/bin/python
  sudo -u mark $PY scripts/lang_nghe_gop_bai_fb.py hapas                      # xem trước, chỉ đọc
  sudo -u postgres psql -d lang_nghe -c 'GRANT DELETE ON bai TO mark'
  sudo -u mark $PY scripts/lang_nghe_gop_bai_fb.py hapas --ap-dung --sao-luu /opt/mark/gop-bai-fb-$(date +%F).jsonl
  sudo -u postgres psql -d lang_nghe -c 'REVOKE DELETE ON bai FROM mark'
  sudo -u mark $PY scripts/lang_nghe_gop_bai_fb.py hapas --hoan-tac /opt/mark/gop-bai-fb-<ngày>.jsonl   # nếu cần trả lại
  ```
  Không chạy khi có lượt `/theodoi` đang chạy (script tự dừng). Quy tắc gộp và chọn số ghi ở đầu script.
- **Chi phí lượt và phí Apify ghi trễ** (đo 17/10/2026: đọc ngay khi run xong 0,1948 → sau vài chục giây 0,2397 USD): `luot_quet.chi_phi_usd` chốt khi run cuối đã xong ≥ 45 giây (chờ tối đa 75 giây); khoảng 90 giây sau run cuối Mark đọc lại ở luồng riêng, Apify tính thêm thì ghi dòng "điều chỉnh" vào sổ chi phí và NÂNG số của lượt (ghi chú lượt có câu "chi phí chốt lại …"). Bot khởi động lại trước bước này thì làm bù lúc khởi động.
- **Bot khởi động lại giữa lượt actor:** phần nền tảng đó không gửi lại, tránh trả tiền hai lần. Tiền vẫn tính theo run id, và nguồn của phần đó chờ lượt sau.
