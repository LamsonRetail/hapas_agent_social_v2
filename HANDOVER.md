# Social Agent (Mark Trần) — Tài liệu bàn giao kỹ thuật

Cập nhật: 30/08/2026 · Trạng thái: **đang chạy production**

Bot Lark trả lời bằng Hermes brain, phục vụ mảng Branding Ads & Booking KOL/KOC
của Lamson Retail. Tài liệu này dành cho người tiếp quản vận hành/phát triển.

> **Đọc mục [Cảnh báo sống còn](#cảnh-báo-sống-còn) trước tiên.** Phần lớn sự cố
> trong dự án này **không crash, không báo lỗi** — bot vẫn trả lời trơn tru
> nhưng số liệu sai. Đó là kiểu hỏng nguy hiểm nhất ở đây.

---

## 1. Kiến trúc

```
Lark  ──push (long-connection)──>  lark-cli event consume
                                            │ NDJSON
                                            ▼
                                   listener.py  (lọc: bỏ bot/echo,
                                            │    group phải @mention)
                                            ▼
                                   run.py  (de-dupe, thread pool, timeout 180s)
                                            │
                                            ▼
                                   brain.py  ──> Hermes AIAgent (gpt-5.6-terra)
                                                      │
                              ┌───────────────────────┼───────────────────────┐
                              ▼                       ▼                       ▼
                        8 tool nghiệp vụ        persona.md            memory_store
                        (mục 3)                 (tính cách)           (per-chat/user)
```

**Danh tính:** BOT (`tenant_access_token` từ app_id/secret). Không có OAuth
as-user. Bot **không** thấy tài nguyên cá nhân của người khác.

**Điểm cực kỳ quan trọng:** Mark **dùng chung `hermes-home` với meeting agent**
(`C:\Users\PC\AppData\Local\hermes`). Xem mục [Ràng buộc với meeting agent](#6-ràng-buộc-với-meeting-agent).

---

## 2. Bản đồ file

### Đang dùng

| File | Vai trò |
|---|---|
| `run.py` | Main. De-dupe theo `message_id`, thread pool, per-chat lock, timeout 180s, reaction "Typing" |
| `listener.py` | Supervisor `lark-cli event consume`, respawn mỗi 90 phút, backoff khi crash |
| `brain.py` | Dựng system prompt (persona + trí nhớ + hướng dẫn tool), gọi `AIAgent.run_conversation` |
| `config.py` | Loader `.env` tự viết + mọi biến cấu hình |
| `lark_client.py` | REST client: tenant token, gửi/reply, reaction, resolve tên, tải file |
| `cli_support.py` | Tìm `lark-cli`, tạo `config.json` file-based, env sạch |
| `memory_store.py` | History per-chat + memory per-user + tool `remember_about_user` |
| `scheduler.py` | Reminder store + ticker 20s + 3 tool nhắc hẹn |
| `persona.md` | **Tính cách bot — sửa file này, không sửa code** |

### Tool nghiệp vụ

| File | Đăng ký tool |
|---|---|
| `lark_cli_tool.py` | `lark_cli` |
| `fb_ads_tool.py` | `fb_ads_library` |
| `apify_tool.py` | `social_listen` |
| `deep_dive_tool.py` | `social_deep_dive` |
| `web_tool.py` | `web_scrape` |
| `crawl_tool.py` + `crawl_runner.py` | `web_crawl` |
| `scrapling_runner.py` | (runner của `web_scrape`) |

### Vận hành

| File | Dùng khi |
|---|---|
| `start.ps1` / `start.bat` | Khởi động bot (tự kiểm tra bản vá `browser_tool`) |
| `check_meeting.ps1` | Kiểm tra sức khoẻ meeting agent — **chạy trước/sau mọi thay đổi** |
| `patch_browser_tool.py` | Vá lỗi cắt URL của Hermes — **chạy lại sau mỗi `hermes update`** |

### Code as-user cũ — đã xoá 28/08/2026

Đã xoá `poller.py`, `authorize.py`, `authorize.bat`, `lark_tool.py`,
`seed_p2p.py`, `seed_p2p.bat` và bản nháp `extractors.py` sau khi xác minh không
còn importer. Docstring/config/call signature liên quan OAuth-as-user cũng đã
được dọn; `lark_client.py` chỉ còn tenant token.

---

## 3. Tám tool của Mark

| Tool | Làm gì | Chi phí |
|---|---|---|
| `lark_cli` | Mọi domain Lark (im, base, wiki, docs, drive, task, sheets, calendar…) | miễn phí |
| `fb_ads_library` | Quảng cáo đối thủ trên Meta Ad Library (bao cả FB/IG/Threads/Messenger) | miễn phí (browser) |
| `social_listen` | Cào post theo keyword/hashtag + khoảng ngày trên 5 nền tảng → Lark Sheet | Apify cho 4 nguồn; YouTube API miễn phí |
| `social_deep_dive` | Kéo **bình luận** của bài cụ thể → Lark Sheet | Apify |
| `web_scrape` | Đọc chữ một trang web công khai | miễn phí |
| `web_crawl` | Cào **toàn bộ sản phẩm** web bán hàng → Lark Sheet | miễn phí |
| `schedule_reminder` / `list` / `cancel` | Nhắc hẹn | miễn phí |
| `remember_about_user` | Ghi nhớ dài hạn về người đang nói chuyện | miễn phí |

Cộng thêm toolset sẵn có của Hermes: `browser`, `vision`, `file`,
`code_execution`, `delegation`.

### `social_listen` — nền tảng và chất lượng **không ngang nhau**

| Nền tảng | Actor | Followers | Lọc ngày | Ghi chú |
|---|---|---|---|---|
| TikTok | apidojo (4.65★) + clockworks (dự phòng) | ✅ | enum thô | Tốt nhất, rẻ nhất |
| YouTube | Data API v3 chính thức | ✅ | ✅ server-side | Miễn phí; quota 100 search/ngày |
| Threads | futurizerush (4.18★) | ✅ | ✅ server-side | Phải ghim RAM 1GB |
| Instagram | apidojo (4.02★) | ❌ | ❌ | Không lọc quốc gia → nhiễu quốc tế |
| Facebook | scrapeforge (3.63★) | ❌ | ✅ server-side | Yếu nhất; free 20 kết quả + **1 lần chạy/24h** |

- Không nói nền tảng → cào **cả 5**, chế độ *rộng-nông* (YouTube 50, Threads 30 post).
- Gọi đích danh → *đào sâu*, dùng nguyên `limit`.
- Hiểu viết tắt: `fb`/`face`/`phây`, `ig`/`insta`, `tt`, `yt`/`ytb`, `thread`.

#### Actor TikTok chạm TRẦN 10 kết quả — vá 08/09/2026

Người dùng báo "brand đang chạy chiến dịch rầm rộ mà chỉ cào được ~5 bài
TikTok". Kiểm chứng: **đúng**.

Đo với `hapas`+`matemade`, 01/08→08/09, `limit=100`:

| Đường đi | Bài trả về | Trong khoảng |
|---|---|---|
| apidojo (actor chính) | **10** | 7 |
| apidojo, chỉ 1 từ khoá | 10 | — |
| apidojo, bỏ `location` | 10 | — |
| apidojo, `sortType=RELEVANCE` | **0** | — |
| `startUrls` = tag/hapas hoặc search?q=hapas | **0** | — |
| **clockworks (dự phòng)** | **120** | **60** |

Đúng **10** ở mọi biến thể tham số ⇒ đó là **trần cứng của actor** cho
tìm-theo-keyword, không phải "thị trường chỉ có bấy nhiêu". `maxItems` (mặc định
1000 theo input schema) không đổi được điều đó.

**Lỗi thiết kế đã sửa:** luật cũ chỉ gọi actor dự phòng khi actor chính trả
**RỖNG**. Nó trả 10 chứ không rỗng ⇒ dự phòng **không bao giờ chạy**. Người dùng
nhận 7 bài và tin đó là tất cả. Nay leo thang khi sản lượng **thấp bất thường**
(`< _TIKTOK_NGUONG_LEO_THANG = 20`), rồi gộp và khử trùng theo `postPage`.

Sau khi vá, cùng truy vấn: **200 bài, 55 trong khoảng** (trước: 7). Và mới thấy
được nội dung của **MATE MADE** — trước đó thiếu sạch.

**Đánh đổi chi phí:** clockworks đắt hơn ~10 lần ($0,003 vs $0,0003 mỗi video).
Vì thế `_UNIT_COST["tiktok"]` nay để **giá dự phòng** — ước tính cao hơn thực tế
thì người dùng chỉ ngạc nhiên dễ chịu, ước tính thấp hơn thì vỡ kế hoạch chi
phí. Số bài đến từ dự phòng được báo ở `tu_actor_du_phong` + `ghi_chu_nguon`.

> ⚠ Bài học chung: **"actor trả ít" và "thị trường ít bài" là hai chuyện khác
> nhau.** Ngưỡng leo thang phải đặt theo SẢN LƯỢNG BẤT THƯỜNG, đừng đợi tới lúc
> rỗng hẳn — actor chạm trần thì không bao giờ rỗng.

#### Nhiễu ĐỒNG ÂM — vá 08/09/2026

Quét brand `hapas` trên YouTube trả về đầy tin **chính trị/tôn giáo tiếng Hindi**.
Không phải lỗi code: **Hapas còn là tên một địa danh ở Rajasthan (Ấn Độ)** đang
có vụ việc nóng (Sania–Salim), cộng thêm hashtag thương hiệu Thái, hãng đàn
HapasGuitars, và lưới nuôi cá "hapa". `_relevant()` giữ **23/25** video vì chúng
**thật sự chứa chữ "hapas"** — lọc đúng như thiết kế, nhưng thiết kế chưa đủ.

`regionCode=VN` KHÔNG cứu được: YouTube chỉ dùng nó để xếp hạng, không lọc địa
lý. Đã thêm ba lớp:

1. `relevanceLanguage` theo nước (VN→vi) — kéo kết quả đúng ngôn ngữ lên, nhưng
   vẫn không phải bộ lọc cứng.
2. `_ngoai_thi_truong()` — loại bài mà **hệ chữ** khác hẳn thị trường đang quét.
   Luật chung theo Unicode, không phải luật riêng cho tiếng Hindi. Chỉ áp dụng ở
   nước dùng chữ Latin (`_THI_TRUONG_LATIN`) — ở TH/IN/JP thì chính nội dung cần
   tìm mới là phi-Latin. Đo **chỉ trên tiêu đề + tên kênh**, không đo mô tả: mô
   tả lẫn link/hashtag Latin làm loãng tỉ lệ và tin Devanagari lọt lưới.
3. `exclude` — tham số mới cho người dùng tự loại từ khoá. Cần vì nhiễu đồng âm
   **có thể viết bằng đúng chữ Latin** ("Salim Hapas and Sania in Dubai") — không
   luật tự động nào đoán nổi, nhưng người dùng thì biết.

Đo trên đúng truy vấn đã gây lỗi (50 video, `hapas|matemade`, 01/08→08/09):

| | Giữ lại | Loại |
|---|---|---|
| Trước khi vá | 37 (đầy tin Hindi + Thái) | 0 |
| Sau, không `exclude` | 15 | 22 |
| Sau, `exclude=[sania, salim, guitars, shekhawati, cement]` | **10** (8 là HAPAS thật) | 27 |

**Loại là phải BÁO.** `per_platform` nay trả `bi_loai_vi_khac_he_chu`,
`vi_du_bi_loai` và `ghi_chu_nhieu` để Mark nói ra và gợi ý dùng `exclude`. Loại
âm thầm thì người dùng tưởng brand mình không ai nhắc, mà thật ra ta vừa vứt đi.

`_relevant()` **cố ý vẫn khớp chuỗi con**, không theo ranh giới từ: người Việt
hay gõ liền một mạch nhiều hashtag (`...tiktokdichHAPASNUOCHOAHAPASLEAVEANOTE`),
khớp theo ranh giới từ sẽ loại đúng bài của chính brand.

#### Lọc bằng AI theo BỐI CẢNH NGÀNH HÀNG — 08/09/2026

Ba lớp trên đều là luật chuỗi, và luật chuỗi thua ở đúng chỗ khó: nhiễu đồng âm
viết bằng chữ Latin ("Salim Hapas and Sania in Dubai"), hoặc ngược lại — bài
ĐÚNG ngành hàng nhưng viết bằng chữ khác. Nên thêm lớp thứ tư: nhờ **chính model
của Mark** đọc bối cảnh ngành hàng rồi tự loại bài lạc đề.

Tham số mới `boi_canh` (vd `"HAPAS: túi xách, trang sức, nước hoa"`). Mô tả tool
bắt Mark **tự suy từ ngữ cảnh trò chuyện mà điền**, người dùng không phải nghĩ
ra từ khoá loại trừ.

Đo trên đúng 37 bài đã gây lỗi:

| | Loại | Giữ |
|---|---|---|
| Lọc hệ chữ (luật chuỗi) | 22 | 15 |
| **Lọc bằng AI** | **22** | **15** |

Cùng con số nhưng **khác hẳn về chất**:

- AI loại được thứ luật chuỗi bó tay: tin Hindi **phiên âm Latin**, cửa hàng xi
  măng `Mumra HAPAS Store`, hãng đàn `HapasGuitars`, remix Indonesia.
- AI **giữ lại** thứ luật chuỗi vứt oan: mấy bài tiếng Thái `#HAPAS #กระเป๋า`
  (kra-pao = túi xách) — ĐÚNG ngành hàng, chỉ khác ngôn ngữ.

Vì vậy **có `boi_canh` thì TẮT lọc hệ chữ**, để AI phân xử (nó thông minh hơn).
`exclude` thì vẫn giữ: đó là luật cứng người dùng cố ý đặt.

**Bốn chốt an toàn, đừng bỏ khi sửa** (đã kiểm chứng từng cái):

1. **MỘT lượt gọi model cho CẢ lượt quét**, đặt sau khi gộp kết quả mọi nền
   tảng — không phải mỗi nền tảng một lượt. Quota Codex **dùng chung với meeting
   agent**, bot production ưu tiên hơn.
2. **FAIL-OPEN.** Model lỗi / hết giờ / trả rác ⇒ **giữ nguyên mọi bài** và ghi
   lý do vào `ai_ghi_chu`. Bộ lọc hỏng mà im lặng vứt dữ liệu là kiểu hỏng tệ
   nhất ở đây. Đã kiểm bằng cách chạy khi thiếu import: log ra
   `KHONG chay duoc (NameError) -> giu nguyen tat ca`, đúng như thiết kế.
3. **KHÔNG CHẮC THÌ GIỮ** (viết thẳng trong prompt). Theo dõi brand mà bỏ sót
   một bài nhắc thật thì tai hại hơn để lọt một bài lạc đề — bài thừa nhìn sheet
   là thấy, bài thiếu thì không bao giờ biết.
4. **Ngân sách thời gian.** `_TOOL_DEADLINE` là 135s và đã chừa 45s cho model
   viết trả lời; cộng thêm 50s gọi model ở đây là vượt trần 180s của `run.py`
   và bị cắt **cả lượt trả lời** — mất trắng cả lượt quét vừa tốn tiền Apify.
   Nên `_loc_bang_ai` nhận `con_lai` và tự bỏ qua khi còn dưới 15s.
   Đo thật: 37 bài hết **24,4s**.

Trần `_AI_TOI_DA = 150` bài mỗi lượt; đông hơn thì bỏ lọc (và ghi log) chứ không
cắt bớt im lặng.

##### Hai lỗi của chính bộ lọc AI — vá 08/09/2026 (đọc kỹ)

**1. Trần 150 bài làm bộ lọc TẮT NGÚM đúng lúc cần nhất.**

Bản đầu: quá 150 bài thì bỏ lọc. Người dùng báo "vẫn nhiều nhiễu Ấn Độ"; đọc
sheet của họ ra **đúng 154 bài** — vượt trần 4 bài — nên bộ lọc **không chạy
dòng nào**. Quét càng rộng thì nhiễu càng nhiều, mà trần lại càng dễ chạm: cơ
chế tự vô hiệu hoá đúng vào lúc nó có giá trị nhất.

Nay **chia lô** `_AI_LO = 120` bài mỗi lượt gọi, chạy tiếp tới khi hết ngân sách
thời gian. Hết giờ giữa chừng thì **giữ nguyên phần chưa xét** và ghi rõ
`moi xet N/M bai`. Trần tuyệt đối nâng lên 600.

Đo lại trên đúng 154 bài đó: **loại 66, giữ 88, nhiễu Ấn Độ còn sót 0**, hết
**18 giây** (2 lô).

**2. Thiếu `boi_canh` thì bộ lọc không chạy.**

Nếu Mark quên điền tham số, bộ lọc tắt hoàn toàn và người dùng lại nhận sheet
đầy nhiễu — lúc được lúc không, không hiểu vì sao. Nay **luôn chạy**: thiếu
`boi_canh` thì đổi sang chế độ *"tự nhìn ra chủ đề chiếm đa số rồi loại bài lạc
hẳn"*. Đo trên cùng 154 bài: loại 67, giữ 87, nhiễu Ấn Độ còn sót **0** — gần
như y hệt chế độ có bối cảnh.

> Bài học: một cơ chế an toàn (trần, guard, cờ tắt) mà **im lặng vô hiệu hoá
> tính năng** thì tệ hơn không có. Guard phải làm việc NHẸ ĐI (chia lô, giảm
> phạm vi) chứ đừng TẮT HẲN, và luôn ghi lại là mình đã làm gì.

Kết quả trả về có `loc_bang_ai`, `bi_loai_boi_ai`, `vi_du_ai_da_loai`,
`ai_ghi_chu` — **phải báo ra**, loại âm thầm thì người dùng tưởng brand mình ít
được nhắc.


### `web_crawl` — thang chiến lược, không hardcode site

1. **catalog_json** — Haravan `/collections/all/products.json`, Shopify `/products.json`
2. **html_data** — JSON-LD / Next.js / Nuxt / JSON hydration trong mọi inline script
3. **html_gia** — đi ngược từ giá tới thẻ `<a>` gần nhất trong HTML thô
4. **sitemap_sp** — sitemap → từng **trang sản phẩm** → JSON-LD/og có cấu trúc
5. **sitemap_dm** — sitemap → nhiều **trang danh mục** → chạy lại bộ bóc tầng 2/3
6. **bu_anh** — mở lại trang sản phẩm để lấy **album ảnh** cho sp mới có 1 ảnh
7. **browser** — render JS rồi chạy lại bộ bóc dữ liệu/giá

Tầng 1–3 chỉ đọc **đúng một trang**. Tầng 4–6 (thêm 06/09/2026) chỉ chạy khi ba
tầng đầu ra **ít hơn số người dùng xin** — vì trang chủ chỉ bày hàng nổi bật, kết
quả *trông như* đã xong mà thật ra thiếu gần hết.

Đo lại 06/09/2026 (xin 120 sp mỗi site):

| Site | Tầng | Sản phẩm | Ảnh | Trước đây |
|---|---|---|---|---|
| hapas.vn | catalog_json | 112 | **1.410** | 112 sp / 112 ảnh |
| yody.vn | html_data+sitemap_dm+bu_anh | **120** | **404** | 90 sp / 90 ảnh |
| juno.vn | html_gia+sitemap_sp+bu_anh | **120** | **1.075** | 40 sp / 40 ảnh |
| vascara.com | html_gia+sitemap_sp+bu_anh | **120** | **709** | 19 sp / 12 ảnh |
| charleskeith.vn | — | 0 | — | sitemap của họ trỏ toàn URL 404 |
| dior.com | — | 0 | — | Akamai chặn mọi tầng |

Vì sao đi qua sitemap chứ không tự đoán `?page=N`: sitemap là đường chủ site
**chủ động khai trong robots.txt**, còn vascara **cấm** `*?page=*` trong robots.

`html_gia`, `sitemap_dm`, `browser` đều là tầng ĐOÁN THEO MẪU GIÁ →
`crawl_tool.py` bắt Mark cảnh báo người dùng đối chiếu ở **cả ba**; đừng sửa
thành chỉ cảnh báo `browser`. `catalog_json`, `html_data`, `sitemap_sp` là dữ
liệu có cấu trúc, tin được.

Mẹo thuật toán (nếu cần sửa): giá **không nằm trong** thẻ `<a>` mà là thẻ anh em
kề bên. Quét `<a>` rồi tìm giá bên trong → 0 kết quả. Phải **đi ngược từ giá, lùi
lại tìm `<a>` gần nhất**. Không phụ thuộc class/id nên site đổi giao diện vẫn chạy.
Ảnh thì ngược lại: phải lấy thẻ `<img>` **gần giá nhất** (thẻ cuối cửa sổ) —
thẻ đầu cửa sổ là ảnh của sản phẩm **liền trước**.

#### Tầng `html_data_attr` + leo thang browser — vá 08/09/2026

**charleskeith.vn: 0 → 24 sản phẩm.** Hai lỗi độc lập chồng lên nhau:

**1. Leo thang browser chờ tới lúc RỖNG nên không bao giờ chạy.** Tầng
`html_gia` bắt được đúng một thứ — cái banner *"Nhận ngay túi tote canvas độc
quyền* 1.799.000đ"*. `sp` không rỗng ⇒ luật cũ (`if not sp: qua_browser()`) bỏ
qua tầng browser, trong khi browser render ra **992.225 ký tự** đầy sản phẩm.
Nay leo thang khi **kết quả đáng ngờ** (≤2 sp và không có tầng cấu trúc nào), và
chỉ nhận kết quả browser nếu nó NHIỀU HƠN — không để tầng đắt làm nghèo dữ liệu.

Đây là **cùng một họ lỗi với actor TikTok cùng ngày**: cơ chế leo thang đặt
ngưỡng "rỗng" thì không bao giờ chạy, vì hỏng-một-phần không bao giờ rỗng.

**2. HTML của họ không có một chữ giá nào.** Đã đo đủ mọi định dạng tiền
(`1.799.000₫`, `₫1.799.000`, `… VND`, `… đ`): **0 khớp**. Nên mọi bộ bóc theo
regex giá đều ra 0. Giá nằm trong THUỘC TÍNH:

```html
<div class="product-tile" data-pid="CK2-90151648-1_STO.GR_M-VN"
     data-price="2650000.0" data-currency="VND" data-availability="in_stock">
```

Thêm tầng `_boc_theo_data_attr()`: đọc `data-price` + `data-pid`, tên lấy từ
`alt` của ảnh (thẻ `<a>` bọc ảnh nên không có chữ), cắt đuôi kỹ thuật
`", hi-res"`. Đây là khuôn **Salesforce Commerce Cloud (SFRA)** — dùng ở rất
nhiều web doanh nghiệp, nên là luật CHUNG theo cấu trúc, không phải luật riêng
cho charleskeith. Và nó **đáng tin hơn `html_gia`**: giá đọc từ thuộc tính khai
báo sẵn chứ không đoán theo khoảng cách văn bản — vì thế `html_data_attr` được
tính vào nhóm "có cấu trúc" và thử TRƯỚC `html_gia`.

**Cuộn trang.** `qua_browser` nay chạy `page_action=_cuon_trang` (cuộn 6 lần,
nghỉ 700ms) để kích lazy-load/infinite-scroll. Trên charleskeith nó không đổi số
thẻ (24 thẻ render sẵn phía server), nhưng là luật chung cần cho SPA khác.

##### Hai site vẫn KHÔNG cào được, và vì sao

| Site | Nguyên nhân THẬT | Ghi chú |
|---|---|---|
| pedro.com | Tường chặn bot: title trả về đúng chữ **"Checking your browser..."** | Cuộn/render không cứu được. Không có actor Apify. |
| dior.com | Akamai chặn cả `/robots.txt` | Xem mục 12 — đã quyết bỏ, giá trị kinh doanh gần bằng 0 |

> ⚠ **Bẫy URL:** `charleskeith.vn` (domain trần) hành xử khác
> `charleskeith.com/vn` → redirect sang `charleskeith.vn/vn`. Tôi đo domain trần
> suốt và kết luận sai là "không cào được". Khi một site ra 0, **thử URL có
> vùng/ngôn ngữ trước khi kết luận**.

Hồi quy sau khi vá (xin 60 sp):

| Site | sp | ảnh | tầng |
|---|---|---|---|
| hapas.vn | 60 | 509 | catalog_json |
| yody.vn | 60 | 60 | html_data |
| juno.vn | 60 | 548 | html_gia+sitemap_sp+bu_anh |
| vascara.com | 60 | 437 | html_gia+sitemap_sp+bu_anh |
| **charleskeith.vn/vn** | **24** | **24** | **browser** |

#### Tầng 7 — ADAPTER "site → Apify actor" (thêm 08/09/2026)

`crawl_adapters.py` là **bảng NGOẠI LỆ tường minh**, tách riêng khỏi thang 6
tầng. Lý do tách: một luật riêng lẫn giữa các luật chung sẽ bị người sau tưởng là
luật chung rồi sửa nhầm. Mỗi mục ở đây đọc là biết ngay "ngoại lệ cho site X".

**Chỉ chạy khi 6 tầng miễn phí ra 0** (hoặc ra rác bị cờ `nghi_ngo` chặn). Nó
tốn tiền Apify nên tuyệt đối không được chạy trước tầng miễn phí — đã kiểm hồi
quy: vascara.com vẫn đi `html_gia+sitemap_sp+bu_anh`, `qua_adapter=None`, $0.

##### Mục đầu tiên: Uniqlo

`web_crawl` ra **0 sp** trên `uniqlo.com/vn/vi` và `/vn/en`: SPA, storefront trả
**403 cho mọi fetcher** kể cả browser stealth; sitemap có 22.157 URL nhưng không
nhóm nào bóc được. Dữ liệu nằm ở API commerce riêng
(`/vn/api/commerce/v5/vi/products`) — API đó trả **200 cho client thường** (khác
dior.com, chặn sạch tới cả `robots.txt`) nhưng đòi header client-id mà Uniqlo
không công bố. `robots.txt` của Uniqlo **không chặn `/api`**.

Cố ý **KHÔNG** hardcode endpoint + client-id vào runner: vừa phá luật "không
hardcode site", vừa vỡ ngay khi họ đổi client-id. Dùng actor đã có người bảo trì.

| | Actor | Giá | Đã kiểm chứng |
|---|---|---|---|
| chính | `rl1987~uniqlo-api-scraper` | **$0,50/1.000 sp** | 20 sp/20s; field name, basePrice, promoPrice, mainImage, url, productId |
| dự phòng | `abotapi~uniqlo-com-scraper` | $2,00/1.000 sp + $0,08 start | 12 sp/16s; `mode` chỉ nhận `search`/`url`, KHÔNG có `category` |

Kiểm chứng **cả hai** là cố ý — dự án vừa học đúng bài "cơ chế dự phòng chưa
từng chạy thì coi như không có" (xem lỗi actor TikTok cùng ngày).

Nghiệm thu end-to-end: **40 sp, 40 ảnh, $0,02**, `tang=apify_adapter`,
`actor_da_dung=['rl1987~uniqlo-api-scraper']`.

##### Ba điều đã cài, đừng bỏ khi sửa

1. **FAIL-OPEN.** Adapter lỗi thì giữ nguyên kết luận thất bại trung thực của
   thang miễn phí. Không được biến lỗi adapter thành "site không có sản phẩm" —
   đó là kết luận SAI VỀ THỊ TRƯỜNG.
2. **Leo thang theo SẢN LƯỢNG THẤP** (`< _NGUONG_LEO_THANG = 5`), không đợi
   actor lỗi hẳn. Actor chạm trần/hỏng một phần thì không bao giờ rỗng.
3. **Báo chi phí.** `qua_adapter`, `actor_da_dung`, `chi_phi_apify_usd` được trả
   ra và mô tả tool bắt Mark nói cho người dùng biết. Tầng tính tiền mà im lặng
   là cách êm nhất để hoá đơn phình lên.

##### ⚠ Bẫy đã suýt sập: đừng gộp theo TÊN

Kết quả Uniqlo trông như lặp — 10 dòng đầu có 3 dòng cùng tên *"UT MAGIC FOR ALL
ICONS Áo Thun"*. Tôi tưởng đó là biến thể màu và đã viết bước gộp. Kiểm lại thì
chúng có **SKU và link khác nhau hoàn toàn** (E489147, E489146, E484258): là các
mẫu áo **khác nhau thật**, chỉ trùng tên vì Uniqlo đặt cùng một tên cho cả bộ
sưu tập UT. **Gộp theo tên là xoá mất sản phẩm thật.**

Nên bước gộp chỉ dùng mã MẪU (`l1Id`/`styleCode`), và trên dữ liệu thật nó gộp
**0 dòng** — đúng như phải thế. Adapter mang thêm trường `ghi_chu` để Mark giải
thích cho người dùng khỏi tưởng dữ liệu bị trùng.

##### Site vẫn chưa cào được

`charleskeith.vn` (sitemap 11.894 URL nhưng trỏ 404) và `pedro.com` (vỏ SPA
12KB) — đã tra Apify Store, **không có actor nào**. Vẫn 0 sp.

#### Bốn lỗi ÂM THẦM đã sửa 06/09/2026

Không lỗi nào từng crash hay báo lỗi — bot vẫn trả lời trơn tru, chỉ sai số liệu.

| Lỗi | Biểu hiện | Cách sửa |
|---|---|---|
| Ảnh **gán nhầm** sản phẩm liền trước | vascara: "Kính mát Cassie" mang ảnh giày sandals | lấy thẻ `<img>` cuối cửa sổ, đọc cả `data-src`/`srcset` |
| Link sản phẩm **404 hàng loạt** | yody: hydration khai slug không kèm `/product/`, code ghép `base+slug` → 90/90 link chết trong sheet | `_sua_link()` đối chiếu slug với sitemap, không tốn request |
| `_so("1,290,000")` = **1 đồng** | cắt chuỗi ở dấu phẩy đầu tiên | tách phần xu theo hậu tố `[.,]\d{1,2}$` |
| **Dương tính giả** | vnexpress.net báo "1 sản phẩm" (tiêu đề bài báo); charleskeith.vn báo 1 banner khuyến mãi | `nghi_ngo`: ≤2 kết quả mà không tầng cấu trúc nào chống lưng ⇒ `success=false`, **không ghi sheet** |

Kiểm chứng 06/09/2026: **18/18** sản phẩm mẫu có **mọi** URL ảnh nằm đúng trong
trang sản phẩm của chính nó (0 ảnh gán nhầm); **24/24** link mẫu trả HTTP 200.

#### Ngân sách thời gian — đừng bỏ

`crawl_tool._NGAN_SACH = 110s` và runner **tự dừng** khi hết giờ, trả kết quả một
phần kèm cờ `het_ngan_sach`. Bản cũ để `_TIMEOUT=280s` trong khi
`AGENT_REPLY_TIMEOUT=180s` — lượt cào lâu bị `run.py` cắt trước, người dùng chỉ
thấy bot **im lặng**. Sửa `_NGAN_SACH` thì phải xem lại `AGENT_REPLY_TIMEOUT`.

Site chặn tốc độ (yody trả 429 hàng loạt) thì runner **tự hạ từ 8 xuống 3 luồng**
và đếm vào `bi_chan_toc_do` để Mark nói rõ: thiếu ảnh vì **bị chặn**, không phải
vì sản phẩm không có ảnh.

---

## 4. Cấu hình `.env`

| Biến | Giá trị hiện tại | Ghi chú |
|---|---|---|
| `LARK_APP_ID` / `LARK_APP_SECRET` | `cli_aa04dc…` | App bot |
| `HERMES_HOME` | `%LOCALAPPDATA%\hermes` | **Dùng chung với meeting** |
| `HERMES_AGENT_DIR` | `…\hermes\hermes-agent` | |
| `AGENT_MODEL` | `gpt-5.6-terra` | Xem [bẫy model](#42-model-có-thể-bị-chặn-đột-ngột) |
| `AGENT_MAX_ITERATIONS` | `14` | Nâng từ 6 — 6 không đủ cho việc nhiều bước |
| `AGENT_MAX_WORKERS` | `2` | Hạ từ 4 để giảm tranh quota với meeting |
| `AGENT_TYPING_BADGE` | `1` | Badge "đang xử lý" dưới tin người dùng. Xem [mục 7.1](#71-badge-đang-xử-lý) |
| `LARK_CLI_PATH` | `…\hermes\node\lark-cli.cmd` | Ghim tay: Windows chỉ có `.cmd`, không có `.exe` |
| `APIFY_TOKEN` | *(bí mật)* | console.apify.com/settings/integrations |
| `APIFY_MAX_CHARGE_USD` | `1.0` | Trần chi phí mỗi nền tảng mỗi lần chạy |
| `YOUTUBE_DATA_API_KEY` | *(bí mật)* | Google Cloud, bật YouTube Data API v3 |

### 4.1 Ba bẫy `.env` / PowerShell

1. **`.env` KHÔNG được có comment cuối dòng.** Loader ở `config.py:24` chỉ
   `split("=", 1)`, không cắt `#`. Viết `AGENT_MAX_WORKERS=2  # ghi chú` sẽ khiến
   `int()` trong `run.py` ném `ValueError` ngay lúc import.
2. **File `.ps1` phải thuần ASCII.** PowerShell 5.1 đọc `.ps1` theo ANSI; comment
   tiếng Việt có dấu vỡ thành mojibake và làm hỏng cú pháp, báo lỗi vô nghĩa kiểu
   *"The string is missing the terminator"*.
3. **PowerShell cần `&` trước đường dẫn có nháy.** `"C:\...\python.exe" script.py`
   là biểu thức chuỗi, không phải lệnh. Phải viết `& "C:\...\python.exe" script.py`.

### 4.2 Model có thể bị chặn đột ngột

26/08/2026 lúc 16:42, OpenAI chặn `gpt-5.6-sol` (meeting) **và** `gpt-5.4` (Mark)
với tài khoản ChatGPT qua Codex — HTTP 400 non-retryable, **cả hai bot chết**.

Model đã kiểm chứng còn chạy: `gpt-5.6-terra` (Codex CLI trên máy dùng cái này),
`gpt-5.6-luna`, `gpt-5.5`. Bị chặn: `gpt-5.6-sol`, `gpt-5.4`, `gpt-5.6`.

Gặp lại thì đổi `AGENT_MODEL` trong `.env` (Mark) và `model.default` trong
`config.yaml` của hermes-home (meeting).

---

## 5. Chi phí nguồn social

Apify có gói free **$10/tháng**. Giá mỗi 100 item:

| Nền tảng | Giá | So với TikTok |
|---|---|---|
| TikTok | $0.03 | 1× |
| Instagram | $0.056 | 2× |
| Facebook | $0.05 | 2× |
| **YouTube** | **$0 (Data API v3)** | — |
| **Threads** | **$0.27** | **9×** |

- Quét cả 5 nguồn (rộng-nông): YouTube không ăn credit Apify; 4 nguồn còn lại
  được ước tính từ `_UNIT_COST` + `_START_COST` và trả trong
  `uoc_tinh_chi_phi_usd` của mỗi lượt.
- Đào sâu TikTok 100 post: **$0.03**.
- `web_crawl` và `fb_ads_library`: **miễn phí**.

YouTube không mất tiền nhưng `search.list` có bucket mặc định 100 lượt/ngày,
mỗi trang tối đa 50 video. Mặc định quét 50 video; gọi đích danh với limit lớn
hơn sẽ dùng thêm một search call cho mỗi trang. Threads mặc định 30 vì đắt.

---

## 6. Ràng buộc với meeting agent

**Meeting agent là production, được ưu tiên hơn Mark.**

Hai bot dùng chung `hermes-home`, nên chia sẻ:

| Tài nguyên | Rủi ro | Trạng thái |
|---|---|---|
| **Quota Codex** | 🔴 cao nhất — không tách được nếu một tài khoản ChatGPT | Hạ `AGENT_MAX_WORKERS=2` |
| `state.db`, `auth.json` | 🟡 | SQLite WAL chịu được đa tiến trình |
| File log | 🟡 | Brain của Mark ghi vào `logs/errors.log` của meeting — **đừng đọc nhầm** |
| `skills/` | 🟢 đã vá | `skills.platform_disabled.feishu` (28 skill lark-*) |
| `config.yaml` | 🟢 | Mark chỉ đọc, không ghi (đã đo) |

Hai bot dùng **hai app Lark khác nhau** nên không tranh event bus.

**Quy trình bắt buộc:** chạy `check_meeting.ps1` **trước và sau** mọi thay đổi.
Mốc bình thường: gateway còn sống, `api_server` + `feishu` đều `connected`,
`invalid_grant`/`refresh_token_reused`/`relogin_required`/`quota` đều = 0.

> ⚠ Script hiện **chưa bắt** lỗi model (`not supported` / `BadRequestError`).
> 26/08 nó báo "BÌNH THƯỜNG" suốt 48 phút meeting đã chết. Nên bổ sung các mẫu này.

---

## 7. Vận hành

```powershell
# Khoi dong bot
.\start.ps1                 # hoac double-click start.bat
.\start.ps1 -StrictPatch    # dung han neu ban va browser_tool da mat

# Kiem tra meeting agent (chi doc, chay bao nhieu lan cung duoc)
.\check_meeting.ps1

# Va lai sau khi `hermes update`
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" .\patch_browser_tool.py
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" .\patch_browser_tool.py --check
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" .\patch_browser_tool.py --revert
```

Khởi động thành công sẽ in:

```
[ OK ] ban va browser_tool con nguyen
Bot creds:  ✅ tenant_access_token OK  (bot open_id=ou_…)
Reminders:  ticker chạy mỗi 20s ✅
Intake: ✅ event bus ready — consuming im.message.receive_v1 as bot
```

**Đổi app Lark thì phải xoá `.lark-cli-bot/`** — `ensure_config()` thoát sớm khi
`config.json` đã tồn tại, nên nó giữ app cũ trong khi REST đã dùng app mới. Tách
não: reply bằng bot mới nhưng event consumer nối app cũ.

---

### 7.1 Badge "đang xử lý"

Khi có người nhắn, bot **thả reaction `Typing`** lên chính tin nhắn đó; Lark
render thành một badge nhỏ ngay dưới tin nhắn, để người dùng biết bot đã nhận và
đang làm. Trả lời xong thì **gỡ badge**; nếu hỏng hoặc gửi tin thất bại thì đổi
sang `CrossMark` để người vận hành nhìn ra.

Đây đúng là cơ chế meeting agent dùng — không phải cách khác. Xem
`_FEISHU_REACTION_IN_PROGRESS = "Typing"` trong
`hermes-agent/plugins/platforms/feishu/adapter.py:288`. Meeting bật mặc định
(`FEISHU_REACTIONS`), Mark bật bằng `AGENT_TYPING_BADGE=1` trong `.env`.

**Mặc định trong code vẫn là TẮT, và đừng đổi thành bật.** Lý do còn nguyên giá
trị: nếu quyền gửi tin hỏng, người dùng chỉ thấy mỗi badge mà **không thấy trả
lời nào**, tưởng bot treo. Badge là lời hứa "sắp có trả lời" — chỉ được hứa khi
đã chắc mình giữ được lời. Trước khi bật ở một máy mới phải xác minh đủ hai điều
kiện:

1. App có scope `im:message.reactions:write_only` — thử `lark_client.add_reaction`
   rồi `remove_reaction` trên một tin nhắn có sẵn, cả hai phải thành công.
2. Bot **đã gửi tin thành công thật** trong chat đó (xem lịch sử tin nhắn hoặc
   dòng `[out] chat=…` trong log).

Bật ngày 07/09/2026 sau khi xác minh đủ cả hai. Banner khởi động in trạng thái:

```
  Badge:      ✅ reaction 'Typing' lên tin người dùng khi đang xử lý
```

Phải in ra vì badge bật/tắt bằng một biến `.env` — không in thì lúc badge biến
mất, không ai phân biệt được là do tắt cờ hay do bot chết.


## 8. Cảnh báo sống còn

Toàn bộ sự cố nặng trong dự án này đều **không crash, không báo lỗi** — bot vẫn
trả lời trơn tru nhưng số liệu sai. Danh sách đã gặp thật:

| Sự cố | Biểu hiện | Đã xử lý |
|---|---|---|
| **Shim `.cmd` nuốt dấu `&`** | `fb_ads_library` báo "0 ad" cho **mọi** brand. HAPAS thật ra có 380 ad | `patch_browser_tool.py` — vá lại sau mỗi `hermes update` |
| **Sentinel `noResults`** | Actor TikTok trả N item chỉ có key `noResults` → báo cáo "cào 10 → giữ 0", tưởng lọc ngày loại hết | Loại sentinel trước khi xử lý |
| **Chữ "7/100" mơ hồ** | Model đọc thành "sheet mới ghi 7 trong 100" → tưởng lỗi ghi, chạy lại 3 lần + xuất CSV vô ích | Tách trường `da_ghi_vao_sheet` / `bi_loai_vi_ngoai_khoang_ngay` |
| **Hết hạn mức giống "không có dữ liệu"** | Facebook free hết lượt vẫn trả `SUCCEEDED` với dataset rỗng | Mọi nguồn cào 0 item đều kèm cảnh báo mơ hồ |
| **Actor chết đột ngột** | apidojo chạy tốt cả buổi rồi trả rỗng cho **mọi** truy vấn | Tự fallback sang clockworks |
| **Phí Actor Start theo GB** | Threads để mặc định 4GB → mất $0.08 và bị huỷ trước khi trả item nào | Ghim `memory: 1024` |
| **`sortingOrder: relevance`** | Actor YouTube cũ trả video 2023–2024 cho cửa sổ 1 tuần → lọc còn 0 | Bỏ actor; Data API lọc ngày server-side + `order=date` |
| **Marker autoraise dùng chung** | Banner thông báo lọt vào chat production của meeting | `compression.threshold: 0.85` |
| **Timeout do gọi tuần tự** | Nhiều từ khoá × nhiều nền tảng → vượt trần 180s | Song song hoá 2 tầng + ngân sách 135s |
| **Chỉ cào MỘT trang rồi tưởng xong** | `web_crawl` vascara ra 19 sp (site có 3.521 URL), yody 90/2.853 — không lỗi, chỉ thiếu | Tầng `sitemap_sp`/`sitemap_dm` khi ra ít hơn số người dùng xin |
| **Ảnh gán nhầm sản phẩm kề bên** | "Kính mát Cassie" mang ảnh giày sandals; sheet vẫn đủ cột nên nhìn không ra | Lấy thẻ `<img>` GẦN GIÁ NHẤT, đọc cả `data-src`/`srcset` |
| **Link sản phẩm 404 hàng loạt** | yody: 90/90 link trong sheet đều chết, bấm mới biết | Đối chiếu slug với sitemap để chữa link |
| **Giá có dấu phẩy thành 1 đồng** | `_so("1,290,000")` → 1 | Tách phần xu theo hậu tố, không cắt ở dấu phẩy |
| **Dương tính giả** | vnexpress.net báo "cào được 1 sản phẩm" (là tiêu đề bài báo) | `nghi_ngo`: ≤2 kết quả không có tầng cấu trúc chống lưng ⇒ không ghi sheet |
| **Nhiễu đồng âm** | Quét brand `hapas` ra tin chính trị/tôn giáo tiếng Hindi — Hapas là địa danh ở Rajasthan; lọc cũ giữ hết vì chúng THẬT SỰ chứa chữ đó | Lọc theo hệ chữ + tham số `exclude` + BÁO số bị loại |
| **Actor chạm trần, không rỗng** | apidojo TikTok trả đúng 10 bài ở mọi tham số; luật cũ chỉ leo thang khi RỖNG nên dự phòng không bao giờ chạy — mất 55/62 bài | Leo thang theo SẢN LƯỢNG BẤT THƯỜNG (<20), không đợi rỗng |
| **Trùng tên ≠ trùng sản phẩm** | Uniqlo đặt cùng tên cho cả bộ UT; suýt gộp theo tên và xoá mất sản phẩm thật (SKU + link khác nhau hoàn toàn) | Chỉ gộp theo mã MẪU, và kiểm SKU/link trước khi kết luận trùng |
| **Leo thang chờ RỖNG** | charleskeith: html_gia ra 1 banner rác nên browser không bao giờ chạy, dù browser có 992KB đầy sản phẩm | Leo thang theo KẾT QUẢ ĐÁNG NGỜ (≤2 sp, không tầng cấu trúc), không đợi rỗng |

**Nguyên tắc rút ra, đã cài vào mọi tool:**

- Cào 0 item **không** đồng nghĩa "không có dữ liệu" — luôn nêu rõ sự mơ hồ
- Một nguồn hỏng thì **cấm** trình bày các nguồn còn lại như thể là toàn bộ
- `in_range` < `scraped` là **bình thường** (lọc ngày), không phải lỗi ghi
- Chạm trần `limit` trên khoảng ngày rộng ⇒ kết quả là **mẫu**, không phải toàn bộ
- Tầng `browser` là **đoán theo mẫu** — nhắc người dùng đối chiếu
- Hỏi nền tảng chưa hỗ trợ ⇒ **từ chối rõ**, không thay bằng nguồn khác

---

## 9. Giới hạn đã biết

- **Quota Codex dùng chung với meeting.** Không tách được nếu một tài khoản ChatGPT.
- **Bản vá `browser_tool` mất sau mỗi `hermes update`.** Launcher có cảnh báo nhưng vẫn phải chạy lại tay.
- **Facebook organic yếu**: khớp từ khoá lỏng (tra "hapas" ra "Happy Animals"), engagement hay trả 0, free 1 lần chạy/24h.
- **Instagram** không có followers, không lọc quốc gia → nhiễu quốc tế.
- **Site hạng sang (dior.com…)** dùng Akamai — cả 4 tầng Scrapling đều thua.
- **TikTok/Instagram không lọc được khoảng ngày server-side** → cào rộng rồi lọc lại, `limit` là số post *cào*, số trong khoảng luôn ít hơn.
- **YouTube cần `YOUTUBE_DATA_API_KEY`** và có quota mặc định 100 lượt
  `search.list` mỗi ngày (reset theo giờ Pacific).

---

## 10. Phụ thuộc ngoài

| Thứ | Vị trí | Ghi chú |
|---|---|---|
| Hermes | `%LOCALAPPDATA%\hermes` | Dùng chung với meeting |
| venv Hermes | `…\hermes-agent\venv` | Mark chạy bằng venv này |
| lark-cli | `…\hermes\node\lark-cli.cmd` | v1.0.89 |
| **venv Scrapling** | `.venv-scrapling` (repo) | **Riêng biệt** — cố ý không cài vào venv Hermes |
| Apify | cloud | Gói free $10/tháng |
| YouTube Data API v3 | Google Cloud | API key; 100 search/ngày mặc định |

Dựng lại venv Scrapling:

```powershell
py -3.12 -m venv .venv-scrapling
.venv-scrapling\Scripts\python.exe -m pip install "scrapling[fetchers]" requests
.venv-scrapling\Scripts\scrapling.exe install
```

---

## 11. Việc nên làm tiếp

1. **Bổ sung `check_meeting.ps1`** bắt `not supported` / `BadRequestError` / `Non-retryable` — lỗ hổng đã để meeting chết 48 phút mà script báo bình thường.

Đã hoàn thành 30/08/2026 (chạy `check_meeting.ps1` trước và sau — đều BÌNH THƯỜNG):

- **YouTube sang Data API v3.** Key đã cấp và **kiểm chứng chạy thật**: 12 video
  trong 7 ngày, có subscribers/views/likes, 0 video lọt ngoài khoảng ngày. Cắt
  nguồn đắt nhất ($0.40/100 item) về **0 đồng**.
- **Xoá code as-user chết** + khối OAuth mồ côi trong `lark_client.py`; đã dọn
  docstring/config/chữ ký hàm. Cả 8 tool nghiệp vụ vẫn đăng ký đủ sau khi xoá.
- **Dọn `.lark-cli-bot.old-20260826-104826`** (xác minh trỏ app cũ
  `cli_a9bcf789…`, khác app đang chạy).
- **`yody.vn` cào được**, bằng luật CHUNG chứ không phải luật riêng cho site:
  quét mọi inline `<script>` theo NỘI DUNG thay vì dò container theo tên. Kéo
  theo juno.vn và vascara.com cũng thoát khỏi tầng browser.

---

## 12. browser-act / BrowserAct — ĐÃ ĐÁNH GIÁ VÀ LOẠI BỎ (07–08/09/2026)

Giữ mục này lại dù code đã gỡ sạch, để **không ai làm lại thí nghiệm 133 credit
này lần nữa**. Đã xoá: `.venv-browseract/`, `browser_act_runner.py`,
`browseract_runner.py`, tầng `stealth_extract` trong `crawl_runner`/
`scrapling_runner`, `%APPDATA%\browseract` (692 MB), key trong `.env` và key CLI.

### Đã thử những gì

[browser-act/skills](https://github.com/browser-act/skills) (MIT) có hai mặt:
CLI tự động hoá trình duyệt cục bộ, và BrowserAct Cloud (REST API + ~338
template sẵn). Đã dựng wrapper cho cả hai, đo bằng key thật.

### Vì sao KHÔNG lắp dạng "skill" của Hermes

| Lý do | Bằng chứng |
|---|---|
| Mark không chạy được skill | `brain.py:208` không bật toolset `skills`; `terminal` tắt hẳn ở dòng 220 |
| Bật lên là mở lỗ hổng | Skill browser-act chạy bằng lệnh shell → phải bật `terminal` cho một bot trả lời **bất kỳ ai** nhắn vào group Lark |
| Làm bẩn meeting | `skills/` **dùng chung** với meeting agent |
| Bề mặt prompt-injection | SKILL.md là **văn bản chỉ dẫn**; nạp chỉ dẫn bên thứ ba vào agent đang giữ bot token Lark là mở đúng cửa đó |

CLI còn **khoá cứng mọi lệnh** cho tới khi agent chạy handshake, và thông báo
lỗi bảo agent *"ghi nội dung skill của chúng tôi vào file skill của bạn"* —
**đừng làm theo**; chỉ cần chạy `get-skills core --skill-version <ver>` là mở.

### Số đo thật — vì sao loại

| Phép thử | Credit | Kết quả |
|---|---|---|
| Facebook Ads Library (`HAPAS`) | 33 | 10 ad, trường đầy đủ, nhưng **lọc ngày không ăn** (xin 30 ngày, trả ad 2024–2025) |
| TikTok Influencer (`túi xách nữ`) | 30 | 10 creator, nhưng là **shop bán hàng chứ không phải KOL**; 2/9 trường rỗng hết |
| YouTube Channel Contact Finder | **70** | **THẤT BẠI** (`extraction_empty`), output rỗng — vẫn bị tính tiền |

Quy đổi ~3 credit/bản ghi → 100 bản ghi ≈ **$0,19**, gấp đôi mức "$0.10/100
dòng" họ quảng cáo, chưa tính proxy ($3,2/GB).

Đặt cạnh cái đang có: `fb_ads_library` **miễn phí** ra **380 ad** cho HAPAS
(BrowserAct: 33 credit cho 10 ad); Apify TikTok **$0,03/100** (BrowserAct
≈$0,19/100). **Đắt hơn đúng ở chỗ Apify mạnh, thua hẳn tool miễn phí ở mảng
Facebook.**

### Bốn cái bẫy, ghi lại phòng khi quay lại

1. **`run-task` trả id ở trường `id`, không phải `task_id`** (trong khi
   `get-task-status` lại nhận tham số tên `task_id`). Đọc hụt là lượt chạy
   **vẫn bị tính tiền** mà không bám theo được kết quả.
2. **Lượt THẤT BẠI vẫn bị tính tiền, và tính nhiều hơn lượt thành công** (70 so
   với 30–33). Trần chi phí phải đếm mọi lượt, và **cấm retry tự động**.
3. **Trạng thái `paused` không phải lỗi cũng không phải xong** — là lúc nó dừng
   chờ người thật đăng nhập/CAPTCHA. Tiến trình tự động sẽ đứng tới hết giờ rồi
   báo "timeout", khiến người ta đi tìm lỗi mạng.
4. **`stealth-extract` chạy Chromium CỤC BỘ**, không phải lệnh thuần cloud. Trên
   máy này kernel của nó khởi động rồi **GPU process bị ACCESS_DENIED
   (0xC0000022)** và Chromium tự thoát. Nó không kèm `--disable-gpu` và CLI
   không cho chèn cờ (chỉ có `BROWSERACT_API_KEY`, `BROWSERACT_DATA_DIR`,
   `BROWSERACT_SERVER_URL`). Đã thử cả trong lẫn ngoài sandbox — hỏng như nhau.

### Nếu sau này muốn thử lại

Điều kiện tối thiểu: họ sửa lỗi kernel GPU, **và** có trần chi phí đếm cả lượt
hỏng, **và** đo lại thấy rẻ hơn Apify ở nguồn cụ thể nào đó. Chưa đủ ba thứ đó
thì đừng lắp lại.

