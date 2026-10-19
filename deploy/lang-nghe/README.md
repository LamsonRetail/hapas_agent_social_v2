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
sudo -u postgres psql -d lang_nghe -c '\dt'        # 15 bảng (lich_quet 15/10, kiem_do_phu 17/10, han_muc_apify 18/10, don_vi + quyen 19/10/2026)
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

- **Đọc:** `du_an`, `nguon`, `don_vi`; `lich_quet` chỉ các cột Mark dùng (không đọc email người tạo/sửa); `nguoi_xem (email, vai_tro, la_quan_tri)` + `quyen (email, don_vi, vai_tro)` cho hỏi đáp số liệu (chỉ trả số dự án của bên người hỏi, từ 19/10/2026).
- **Ghi:** `bai`, `chi_so_ngay`, `luot_quet`, `de_xuat`; `kiem_do_phu` chỉ thêm dòng (kiểm độ phủ 2 lần/tuần, từ 17/10/2026); `han_muc_apify` chỉ thêm dòng (ảnh chụp hạn mức gói Apify cho trang Ngân sách sau mỗi lượt và mỗi 3 giờ, từ 18/10/2026 — dashboard không giữ token Apify).
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
