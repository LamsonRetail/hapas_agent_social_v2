# 5 · Kiến thức — nạp, nguồn Wiki, RAG

## RAG không phải là tool

Đây là hiểu nhầm đầu tiên cần dẹp: agent **không gọi** một tool tên là "tra tài liệu".
Platform tự cắm 4 mẩu liên quan nhất vào `/v1/self/context` **mỗi lượt**, trước khi model
nhìn thấy câu hỏi.

Hệ quả thực tế:

- Không có công tắc nào tắt được RAG, và tắt hết năng lực thì agent **vẫn** tra được kho.
- Model không biết mình vừa "tra cứu" — nó chỉ thấy ngữ cảnh có sẵn. Nên nếu muốn nó nói
  rõ nguồn, phải **dặn trong prompt**, không có chỗ nào khác chen vào được.
- Mẩu nào lọt vào 4 chỗ đó là do truy vấn của platform quyết, không phải agent.

Điều kiện lọc phía platform:

```sql
WHERE b.status = 'approved' AND (b.scope = 'shared' OR b.agent_id = %s)
```

Nạp xong mà `status` chưa `approved` thì **không mẩu nào tới tay agent** — kho trên
console đầy, agent vẫn trả lời như chưa có gì.

## Ba đường nạp

| Đường | Dùng khi | Ghi chú |
| :--- | :--- | :--- |
| Console, kéo thả `.md` | vài tài liệu, nạp một lần | không theo dõi thay đổi |
| `scripts/nap_kien_thuc.py` | tài liệu nằm trong repo agent | so băm, chỉ đẩy file đã đổi |
| Nguồn Wiki | tài liệu sống, đội sửa thường xuyên | quét định kỳ, nhập khi người bấm |

Đường 2 và 3 khác nhau ở **ai giữ bản gốc**: repo hay Wiki. Đừng để cả hai cùng giữ một
nội dung — hai nguồn sự thật cho một câu hỏi là thứ mục [README](README.md) đã cảnh báo.

### Chặn cứng những thứ không được nạp

`nap_kien_thuc.py` đọc `knowledge/catalog.json` và **chỉ** nạp mục `approved_for_dev`;
mục `excluded` bị chặn ở mã, không phải bằng lời dặn. Bốn mục trong danh mục của Mark là
chat transcript, mà đặc tả vai cấm *"ingest chat transcript, export hội thoại,
HR/payroll, credential hoặc raw social PII"*.

Lý do chặn ở mã: **không có nút hoàn tác cho việc đã trả lời.** Nạp nhầm một transcript
là RAG có thể trích nó ra cho bất kỳ câu hỏi nào của bất kỳ ai, và bạn không biết nó đã
trích lần nào.

## Nguồn Wiki

> **Trạng thái hôm nay:** đường ống đã dựng và kiểm xong, nhưng nguồn Wiki của Mark
> **đang tắt** — chờ sign-off ADR `WIKI`. Bật sớm là kéo cả bảng nhân sự vào kho kiến
> thức. Phần dưới mô tả cơ chế, không phải trạng thái đang chạy.

```
console          chủ agent dán link node gốc     →  agents.wiki_source
agent (30′)      quét cây bằng token BOT của mình →  đếm mục, so vân tay, báo lên console
người            nhìn số, bấm nút
agent (20s)      thấy lệnh → nhập → báo kết quả
```

**Agent quét, không phải platform.** ACL Wiki cấp theo từng space cho từng bot; để
platform quét bằng danh tính khác sẽ ra một bản đồ nội dung khác với thứ agent thật sự
lấy được. Chỗ khảo sát phải đúng là chỗ sẽ thực thi.

**Quét thì không nhập.** Wiki là nơi người ta lưu nửa chừng. Phát hiện đổi thì **báo**,
nút cuối cùng vẫn là người. Nguyên tắc lấy từ `watch_wiki.py` của agent HR.

### Hai nhịp, hai con số khác nhau — cố ý

```
NHIP_QUET  1800s   không ai ngồi xem; mỗi lượt là hàng chục lời gọi Lark
NHIP_NHAP    20s   người vừa bấm nút và đang đứng chờ
```

Nhịp nhập từng là 60 giây; rút xuống 20 sau khi **đo**, không đoán. Cho phép rút vì
`khai_bao()` đã đổi cửa: `/v1/self` (0,5 KB) thay cho `/v1/self/directory` (28 KB, join
81 agent). Sau khi đổi, nhịp 20s vẫn **nhẹ hơn nhịp 60s cũ khoảng 20 lần**.

Dưới 10 giây thì vô nghĩa: lúc đó chặng chờ đã nhỏ hơn chính việc quét (~15 giây).

### Phát hiện thay đổi bằng vân tay

Mỗi node có `obj_edit_time`. Gom cả cây thành một map rồi băm — băm đổi nghĩa là Wiki
đổi. Rẻ hơn tải nội dung, và không nhầm "đọc lại cùng nội dung" thành "có thay đổi".

Nhưng nhớ: **đổi link cũng phải kích hoạt quét lại.** Bản đầu chỉ hẹn giờ theo nhịp, nên
dán link mới xong console vẫn hiện số của link cũ tới 30 phút — người dùng đọc số đó và
tưởng link mới rỗng.

### Bóc tới mục H1, và trả link sâu

Một node Wiki dài được cắt theo tiêu đề H1, mỗi mục thành một mẩu riêng kèm
`source_url` trỏ đúng tới mục đó. Người đọc câu trả lời bấm được vào thẳng đoạn gốc thay
vì tự dò trong tài liệu dài.

Trong ngữ cảnh gửi cho model, mỗi mẩu kèm `· cập nhật YYYY-MM-DD`. Có ngày thì model
mới nói được *"theo tài liệu ngày 12/09"* thay vì trình bày số liệu cũ như tình hình hôm
nay.

## Thứ tự dùng nguồn: kho trước, web là đường lùi

Quyết định của chủ agent, và lý do đứng vững: **wiki do đội tự soạn và cập nhật thường
xuyên thì nó có thẩm quyền.** Ra web hỏi thứ đội đã tự chốt là đổi một câu trả lời đúng
lấy một câu trả lời chung chung.

Bản trước làm ngược — bắt ra web cho mọi thứ đổi theo thời gian, kể cả khi kho có. Sai ở
giả định: nó coi kho là ảnh chụp tĩnh, trong khi kho ở đây là wiki sống.

Bảy điểm trong `_LUAT_NGUON` (`brain.py`), rút gọn:

1. Kho trước; với việc nội bộ, kho có thẩm quyền cao hơn mọi nguồn web
2. Trả lời được bằng kho thì dừng ở đó
3. Kho không có mới ra web — và nói rõ đây là thông tin ngoài
4. Hỏi nghiệp vụ (quy trình, phân công, số đã chốt) thì **luôn** theo kho
5. Câu hỏi về tình hình **hiện tại** mà chỉ dựa vào kho: phải nói là chưa đối chiếu web
6. Luôn nói rõ con số nào lấy từ đâu
7. Dùng `cập nhật <ngày>` để biết mẩu còn mới không

Điểm 5 là chốt an toàn duy nhất giữ lại, và nó không cãi luật trên: wiki dù cập nhật tốt
tới đâu cũng không biết đối thủ vừa đổi giá sáng nay.

## Xoá kiến thức

Xoá theo lô, một giao dịch. Bản đầu gửi mỗi tài liệu một lời gọi từ trình duyệt — 83 tài
liệu là 83 lời gọi, và nó **dừng ở 61** vì trình duyệt cắt. Người dùng nhìn thấy 22 tài
liệu còn lại và tưởng platform giữ lại có chủ đích.

Giới hạn 500 mục một lần, `= ANY(%s)` trong một transaction. Hoặc xong hết, hoặc không
gì cả.
