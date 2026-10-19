# Dashboard Social Listening — `social.hapas.vn`

Trang web nội bộ cho team marketing HAPAS (đợt 2, chủ dự án chốt 14/10/2026). Đọc kho Postgres `lang_nghe` trên VPS của Mark (Mark ghi bài sau mỗi lượt `/theodoi <mã dự án>`), hiển thị chỉ số kiểu Kompa và cho người quản lý sửa danh sách nguồn + ngân sách.

## Phạm vi

Dashboard **chỉ gồm**:

1. **Chỉ số** (`/`): bài, thảo luận (= bài + bình luận nền tảng báo, như Kompa), nguồn có bài, lượt xem, tương tác, % tích cực/tiêu cực/trung lập, so với kỳ liền trước cùng độ dài; xu hướng theo ngày (theo tuần khi khoảng > 92 ngày, giờ VN); sắc thái × chủ đề; theo nền tảng; theo loại nguồn; nguồn nổi bật; từ khoá nổi bật; bài nổi bật. Lọc theo dự án, khoảng ngày (mặc định 30 ngày trọn tới hết hôm qua — so ngày trọn với ngày trọn), nền tảng, loại nguồn. Tự cập nhật khi Mark quét xong (không tải lại trang).
2. **Nguồn** (`/nguon`): thêm/sửa dự án; thêm/sửa/tạm dừng/xoá nguồn theo dõi (dán nguyên link trang cá nhân cũng được), mỗi nguồn kèm ước tính USD/tháng (tính lại ngay khi đổi số bài/chu kỳ); duyệt/từ chối nguồn Mark đề xuất.
3. **Ngân sách** (`/ngan-sach`) — quản trị chi phí (chủ dự án 15/10/2026). Hai tầng trần: platform đặt trần tháng cấp cửa hàng (KDLA, chưa có — trang hiện "chưa có (chờ KDLA)"; `kho.tran_platform()` trả None tới khi Mark ghi trần đó vào kho), dashboard đặt trần tháng từng dự án (0–100 USD); Mark áp trần THẤP HƠN. Trang hiện: đã tiêu tháng này (giờ VN), **dự báo cả tháng** = đã tiêu + phần còn lại của tháng theo cấu hình nguồn hiện tại (nguồn tạm dừng không tính, YouTube 0), dự báo theo nền tảng, cảnh báo đỏ khi dự báo > trần hiệu lực kèm 3 nguồn tốn nhất và cách giảm (tăng chu kỳ / giảm số bài / tạm dừng); lịch sử lượt quét. Công thức ở `chi_phi.py`, chép từ `theo_doi._uoc_phan` (giá, hệ số 1,3, phí khởi động actor) — bài thử đối chiếu với Mark.
4. **Quản trị** (`/quan-tri`, trước 19/10/2026 tên "Người xem" ở `/nguoi-xem` — đường cũ chuyển hướng 308; quản trị viên + quản lý của bên): ai được vào, quyền theo từng bên, nhật ký thay đổi; tên, chức danh, phòng ban, trạng thái tài khoản Lark (đang hoạt động / chưa kích hoạt / tạm khoá / đã nghỉ việc / không có trong danh bạ — đọc danh bạ Lark, đệm trong `nguoi_xem`, làm mới nền ≤ 12 giờ/lần) và lần đăng nhập gần nhất. Thêm email: kiểm với danh bạ và cảnh báo (không chặn) nếu không có / không hoạt động.
5. **Chi tiết + bình luận** (đợt 2b, 15/10/2026): bấm vào điểm/cột/dòng bất kỳ trên trang Chỉ số mở khung các bài làm nên con số đó (`/api/bai`), mỗi bài mở được bình luận Mark đã cào (`/api/binh-luan`). Khối "Bình luận đã đọc" đếm sắc thái/chủ đề bình luận của khách (bình luận của thương hiệu không tính). Số bài × số bình luận mỗi lượt đặt ở trang Ngân sách.
   - **Ý định mua** (16/10/2026): ô KPI + khối riêng (cột theo ngày/tuần/tháng, bài có nhiều câu hỏi mua nhất; bấm là ra đúng bình luận). Ý định mua = bình luận hợp lệ có chủ đề AI "Giá/mua ở đâu/ý định mua" HOẶC câu hỏi giá/mua (xin giá, giá bn, ib, mua ở đâu, còn hàng, size, ship, đặt hàng…) — `chi_so.la_y_dinh_mua`. Theo bộ lọc chung; so kỳ trước không có % khi kỳ trước 0. Bộ lọc nhanh "Khách hỏi mua" = cùng định nghĩa (`y_dinh=1`).
   - **Từ khoá nổi bật**: chữ chuẩn hoá chung với ô tìm (`chuan_chu.py`: NFKC cho chữ kiểu cách 𝐃𝐚́𝐧, teen code mk/bn/ko…, bỏ dấu khi so); bản có dấu/không dấu gộp một nhóm; mảnh câu hỏi giá ("xin giá", "giá set", "set giá") không vào mây — đã đếm ở Ý định mua. Từ 16/10/2026 (chủ dự án: "lấy bình luận spam, key word đang lỗi"): tách TỪ trước khi ghép cụm (`tu_ghep.py`, danh sách từ ghép tự soạn + so khớp dài nhất, so có dấu) — cụm là một từ ghép ("túi xách", "nước hoa") hoặc hai từ đơn liền nhau ("túi đẹp"), không còn mảnh cắt ngang như "xách nữ", "nữ tuyệt", "lòng kiểm"; bỏ mã/chữ dính số, nhãn dán TikTok "[…]", tên người được tag, hashtag có số (#quatang2010); "#tuixach" đếm chung với "túi xách"; bình luận có mã giới thiệu / lời dặn dán mã không vào mây dù nhãn còn hợp lệ (`chi_so.la_rac_quang_cao`); cụm cần ≥ 2 người viết và người viết nhiều nhất ≤ 2/3 số thảo luận của cụm. Không dùng pyvi/underthesea (nặng, chậm, tách sai chữ MXH — xem đầu `tu_ghep.py`). Ngăn từ khoá đếm bình luận đúng như mây (`cum_bl`, không xét tên tác giả). Mặc định không gồm bình luận chủ đề "Minigame/bài dự thi" (công tắc "Gồm cả bình luận minigame", `gom_mg=1` trên URL). Màu theo ngưỡng: xanh khi ≥ 25% tích cực và gấp đôi tiêu cực, đỏ đối xứng, còn lại xám; hộp rê chuột cảnh báo "x% từ 1 bài" khi một bài góp ≥ 60%.
   - Nhãn hiển thị (16/10/2026): **Internal channel** (nguồn loại `kenh_nha`) / **External channel** (`ben_ngoai`). Giá trị lưu và tham số URL không đổi.
6. **BigQuery** (`/bigquery`, chỉ quản trị viên từ 19/10/2026): trạng thái đồng bộ kho lên BigQuery; bấm "Đồng bộ ngay".
7. **Lịch quét** (`/lich-quet`, chủ dự án chốt 15/10/2026 "Dashboard + Mark tự chạy"): lịch quét tự động mỗi dự án — mỗi N giờ trong khung giờ, hằng ngày (giờ cụ thể), hằng tuần (ngày + giờ), chiến dịch (từ lúc → tới lúc, mỗi 30 phút – 7 ngày, dài ≤ 92 ngày, bắt đầu trong 365 ngày tới, mặc định quét mọi nguồn; đang diễn ra thì lịch thường nhường, hết khung tự dừng). Biểu mẫu có xem trước 10 lần chạy tới (giờ VN) và chi phí tối đa so với trần tháng, tính ở máy chủ trong threadpool (`/api/lich-quet/xem-truoc`, đúng hàm Mark dùng — `lich_quet.py`; kỳ của lịch đang gõ chỉ đếm mốc của chính nó). Mark (`quet_tu_dong.py`, nhịp 30 giây trên VPS, không qua hàng đợi job platform) tự chạy `/theodoi` đúng mốc, báo mỗi lượt lên platform bằng trace; kết quả hiện ở đây, không nhắn Lark. Trang Ngân sách nhân theo số lượt của lịch đang bật (không còn giả định 1 lượt/ngày).

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
| `templates/`, `static/` | giao diện (Jinja2, ECharts 5.5.1 phục vụ tại chỗ `static/echarts.min.js`, sáng/tối theo hệ điều hành) |

Đường dẫn: `/`, `/api/chi-so`, `/nguon`, `/ngan-sach`, `/quan-tri` (`/nguoi-xem` → 308), `/bigquery` (chỉ quản trị viên), `/su-kien` (SSE), `/dang-nhap`, `/dang-nhap/lark`, `/dang-nhap/xong`, `/dang-xuat`, `/suc-khoe` (không cần đăng nhập), `/noi-bo/co-du-lieu` (chỉ Mark trên cùng máy), và các POST sửa dữ liệu (`/du-an/…`, `/nguon/…`, `/de-xuat/…`, `/ngan-sach/<mã>`, `/nguoi-xem/them|xoa|quan-tri`, `/don-vi/them`, `/bigquery/dong-bo`).

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

Đồng bộ chạy sau mỗi lượt quét và 6 giờ một lần. Không đẩy `nguoi_xem`, `nhat_ky`, `de_xuat`, cột email.

## Chạy bộ thử (máy dev, không cần Postgres/mạng)

```powershell
cd D:\hapas_w49; $env:LARK_APP_ID='cli_test'; $env:LARK_APP_SECRET='test'
python -X utf8 -m pytest -q -p no:cacheprovider --basetemp=.pt/tmpd tests/test_dashboard_*.py tests/test_dong_bo_bq.py
```
