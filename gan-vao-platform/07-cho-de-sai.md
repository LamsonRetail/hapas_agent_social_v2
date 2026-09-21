# 7 · Chỗ dễ sai

Mỗi mục dưới đây là một sự cố thật, mỗi cái ngốn từ nửa tiếng tới một ngày. Xếp theo
**cách nó lừa bạn**, không theo thành phần — vì thứ làm mất thời gian không phải bản
thân lỗi, mà là việc nó trông như đang chạy.

______________________________________________________________________

## A · Trông như đã chạy, thật ra chưa

### A1 — Biến môi trường cấp User âm thầm che `.env`

**Hiện tượng.** Đổi `APIFY_TOKEN` trong `.env`, khởi động lại, bot vẫn báo hết hạn mức.
Chủ agent khẳng định tài khoản còn tiền — và đúng.

**Nguyên nhân.** Loader dùng `os.environ.setdefault`. Một biến `APIFY_TOKEN` cấp User còn
sót từ lần cài cũ, trỏ về tài khoản đã cạn, **thắng** giá trị trong `.env`. Không dòng
log nào báo.

**Chữa.** `.env` thắng, và **in ra khi đè** (chỉ tên khoá, không bao giờ in giá trị).

> `.env` nằm cạnh mã, đi theo repo, sửa là thấy. Biến cấp User thì vô hình. Nguồn sự
> thật phải là cái nhìn thấy được.

### A2 — `Start-ScheduledTask` thành công nhưng không bật gì

Task còn kẹt `Running` từ lần trước, từ chối lượt mới với `0x800710E0`. Lệnh vẫn trả về
êm ru. Bot tắt mà tưởng đã bật.

**Chữa.** `Stop-ScheduledTask` **trước**, rồi mới `Stop-Process`, rồi `Start`. Và đếm lại
tiến trình sau **từng** bước — đừng gộp vào một khối, vì khối lỗi giữa chừng thì phần bật
không chạy.

### A3 — HTTP 200 nghĩa là "đang chờ duyệt"

`POST /publish` trả 200 kèm `publication: "pending_approval"` khi người gọi không đủ
quyền. Script kiểm mã HTTP nên báo thành công; console hiện nội dung cũ.

**Chữa.** Kiểm **cái API nói nó đã làm**, đừng kiểm cái nó nhận được yêu cầu.

### A4 — Prompt nói agent bị cấm, trong khi quyền đã có

`brain.py` ghim cứng *"LUẬT VAI PLANNER — không có quyền ghi Sheet"*. Mark đã lên
`executive` từ hôm trước, policy đã cho, tool chạy được — nhưng model **từ chối trước khi
thử**. Không crash, không test đỏ, không log.

**Chữa.** Sinh lời dặn bằng cách **hỏi chính hàm sẽ chặn** (`lsr_policy.decide`). Xem
[mục 3](03-quyen-han.md).

### A5 — Vòng job treo, log im như không có việc

Một lượt gọi model treo; vòng job tuần tự nên đứng cả Lark lẫn console. Log chỉ in lúc
**hoàn tất**, nên "job treo" trông y hệt "không có job nào".

**Chữa.** In ngay khi **nhận** job, và đặt trần `_HAN_TRA_LOI = 480s`. Xem
[mục 4](04-nhan-viec.md).

### A6 — Checklist "28/28 complete" mà chưa kiểm gì

Agent do admin tạo thì tự `active`, checklist đầy màu xanh. Nó chỉ nghĩa là **đã khai đủ
trường**.

______________________________________________________________________

## B · Đúng cú pháp, sai danh tính

### B1 — Ba khoá, đừng lẫn

Khi gặp 401/403, câu hỏi **đầu tiên** là *"đang dùng danh tính nào"*, không phải *"thiếu
quyền gì"*.

| | đọc được | KHÔNG đọc được |
| :--- | :--- | :--- |
| agent token `lsr_tel_…` | `/v1/self/*` | `/v1/roles/catalog` → 401 |
| token người dùng | `/spec` `/profile` `/manifest` | `/persona` `/skills` → 403 (Caddy) |
| bot Lark `cli_…` | node Wiki được cấp | danh sách space → có thể rỗng |

### B2 — Danh sách space Wiki rỗng **không** chứng minh bot thiếu quyền

Bot đọc được một node cụ thể mà vẫn không liệt kê nổi space chứa nó. Tôi đã kết luận sai
theo hướng ngược lại và đi xin quyền không cần thiết.

**Chữa.** Thử **đúng node** cần đọc. Danh sách chỉ là gợi ý, không phải bằng chứng.

### B3 — Bản sao thử nghiệm giành bus Lark với bot thật

`mark_tran_test` khai đúng app id và agent id của production. Chạy lên là cướp kết nối.

**Chữa.** Nhân bản thư mục thì **đổi app Lark và agent id** trong `.env` của bản sao.

______________________________________________________________________

## C · Endpoint không như bạn tưởng

### C1 — `POST /profile` không có `GET`

Gọi `GET /v1/agents/{id}/profile` trả 405. Muốn đọc thì dùng `GET /spec`.

### C2 — Proxy admin của console **luôn POST**

`POST /api/admin` bỏ qua mọi trường `method` bạn gửi kèm. Đừng dùng nó để "xem thử" một
endpoint mà POST có tác dụng phụ.

### C3 — Caddy chặn ở biên, kể cả khi bạn là admin

Ngoài danh sách trắng thì 403 ngay tại biên, chưa tới `platform_api`. Đã vấp:
`/knowledge`, `/v1/golden-cases`, `/v1/regression/run`, `/v1/audit`. Đường vòng hợp lệ là
route của console.

### C4 — `/v1/self/jobs` **claim** job, không phải chỉ đọc

Gọi nó để "xem có gì" là đã nhận việc.

### C5 — `lark_client.call` nhận `query=`, không phải `params=`

Chữ ký là `call(method, api_path, *, query=None, body=None)` — tham số **chỉ truyền theo
tên**. Quen tay gõ `params=` như `requests` thì ném `TypeError` ngay. Đây là cái bẫy rẻ
nhất trong danh sách: nó kêu to. Nhắc ở đây vì nó làm mất thời gian nhiều hơn mức đáng.

### C6 — `lark_client.call` **không** đi qua `ToolRegistry.dispatch`

Bọc dispatch là chưa đủ. Tìm hết đường ra ngoài trước khi tin là đã chặn đủ.

### C7 — `POST /change` không có ai duyệt ở đầu kia

Mọi thay đổi chạm policy rơi vào `pending_review`. Bảng `agent_changes` có
`reviewed_by`/`reviewed_at` nhưng không nơi nào ghi vào. Đổi `type` hiện phải xoá rồi
dựng lại — xem [mục 2](02-nhan-vai.md).

______________________________________________________________________

## D · Ghi vào DB rồi mà không tới nơi

### D1 — Thêm cột vào `SELECT` mà agent vẫn nhận `None`

`_rag_search` **dựng dict bằng tay**. Thêm `b.updated_at` vào câu SQL là chưa đủ; phải
thêm cả vào chỗ dựng dict.

### D2 — Endpoint tự bóp gói tin của bạn

Ingest nhận `source_url` nhưng handler dựng lại `clean` chỉ gồm `{name, content}` — mọi
trường khác rơi im lặng.

**Chữa cho cả D1 và D2.** Khi thêm một trường, **lần theo nó tới tận nơi đọc**, đừng dừng
ở chỗ ghi.

### D3 — `coalesce` xoá mất phần của người khác

`wiki_source` có hai bên ghi: console (khai báo link) và agent (kết quả quét).
`coalesce(%s, wiki_source)` **thay nguyên cục**, nên mỗi bên ghi là xoá phần của bên kia.

**Chữa.** Trộn nông: `coalesce(wiki_source,'{}') || coalesce(%s,'{}')`.

Quy tắc: **cột jsonb có hơn một người ghi thì dùng `||`, không dùng gán.**

### D4 — Xoá 83 tài liệu, dừng ở 61

83 lời gọi tuần tự từ trình duyệt; trình duyệt cắt giữa chừng. Người dùng thấy 22 cái còn
lại và tưởng platform giữ có chủ đích.

**Chữa.** Một lời gọi, `= ANY(%s)`, một transaction, trần 500 mục.

### D5 — Kiến thức chưa `approved` thì RAG không thấy

`WHERE b.status='approved' AND (b.scope='shared' OR b.agent_id=%s)`. Kho trên console
đầy, agent trả lời như chưa có gì.

______________________________________________________________________

## E · Bài kiểm tự lừa mình

### E1 — Truyền `out=[]` vào bài đánh giá

Suốt một thời gian nó kiểm một agent không khai quyền gì. Xanh — nhưng xanh về agent
khác.

### E2 — Báo cáo đánh giá không ghim băm manifest

Manifest đổi là băm đổi. Báo cáo cũ gắn manifest mới là nói dối im lặng.

### E3 — Kiểm lại thứ mình **ngờ** sẽ mất, không kiểm thứ màn hình **hiện**

Dựng lại agent: tôi kiểm kiến thức, quên kiểm tiểu sử và danh sách kỹ năng đang bật —
đúng hai thứ đã mất.

### E4 — Assertion `contains` trên một cách diễn đạt

Cổng hồi quy cho 4/5 rồi 5/5 trên **cùng đầu vào**. Model trả lời đúng ý, chọn chữ khác.
Chạy lại là đường đúng; đừng `force=true`.

### E5 — Test của tôi đỏ mà mã thì đúng

Ba lần trong dự án này: một list comprehension có chữ `for` bị đọc thành vòng lặp xoá;
`setNguon({...nguon})` bị đọc thành thân request; một test dựa vào `exec` mong manh hơn
chính đoạn mã nó canh.

**Chữa.** Test canh **hành vi**, đừng canh hình dạng mã nguồn.

______________________________________________________________________

## F · Công cụ và môi trường

### F1 — PowerShell không hiểu `&&`

Windows PowerShell 5.1 báo lỗi cú pháp. Dùng `;` hoặc `if ($?) { }`.

### F2 — `print` tiếng Việt chết giữa chừng dưới cp1252

Để lại một draft version đã tạo mà không ai publish. `reconfigure(encoding="utf-8")` ở
đầu mọi script.

### F3 — Chuỗi escape bị nghiền qua nhiều lớp

Viết file bằng heredoc → Python → file: `\b` thành ký tự backspace thật, `\n` thành xuống
dòng thật. Ba lần. **Dùng công cụ ghi file trực tiếp**, đừng xếp tầng shell.

### F4 — `lay_luot_vua_xong` là lấy-và-xoá

Gọi khi lượt còn dở là cướp số token của lượt đang chạy rồi ghi nhầm cho job khác.

### F5 — Nhịp nền gọi cửa đắt

Nhịp Wiki gọi `/v1/self/directory` (28 KB, join 81 agent) mỗi vòng. Đổi sang `/v1/self`
(0,5 KB) thì rút nhịp 60s → 20s mà vẫn nhẹ hơn 20 lần.

**Nguyên tắc.** Muốn rút nhịp thì **đo giá một vòng trước**, đừng rút rồi mong không sao.

______________________________________________________________________

## G · Một câu tổng kết

Loại lỗi đắt nhất trong dự án này không crash. Nó để mọi thứ xanh và chỉ sai ở một chỗ
không ai nhìn: sai tài khoản, sai danh tính, sai phiên bản, sai người được chấm điểm.

Nên với mỗi chốt bạn dựng, hỏi thêm một câu: **nếu cái này hỏng, ai biết?**
