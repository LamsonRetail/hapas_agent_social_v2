# 3 · Quyền hạn — ba tầng, và chỗ nói dối

## Ba tầng, xếp đúng thứ tự

```
1  HỢP ĐỒNG        connections.out trong manifest → platform tính ra out_allowed
                   ranh giới an toàn. Không nới được từ phía agent.
        ↓
2  CÔNG TẮC        chủ agent bật/tắt từng tool ở khối Năng lực trên console
                   chỉ THU HẸP thêm, không bao giờ nới.
        ↓
3  LỜI DẶN         prompt kể cho model biết nó được làm gì
                   phải SINH RA từ hai tầng trên, đừng gõ tay.
```

Thứ tự này quan trọng. Đảo tầng 1 và 2 thì một công tắc bật lên có thể nới quá hợp đồng
— và mọi thứ vẫn "chạy được", không ai thấy gì sai.

## Tầng 1 — hợp đồng, đọc từ stamp

`GET /v1/self/stamp` trả policy bundle: `type`, `out_allowed`, `users`, `forbidden`,
`approval_required_tools`, `budgets`. TTL 10′, ân hạn 60′.

Phía agent (`lsr_policy.quyen_phat()`) đọc theo **ba tầng tin cậy**:

```
1. stamp của platform     mới nhất
2. bản nhớ cuối           mất mạng một nhịp thì đừng câm giữa câu trả lời
3. manifest cục bộ        khi chưa bao giờ gọi được
4. rỗng                   không khai gì thì không phát gì — fail-closed
```

`out_allowed: false` ở mức trên cùng là **kill-switch**: trả rỗng ngay, bất kể hợp đồng
khai gì.

Nhớ tạm 300 giây. Hệ quả cần biết: **đổi hợp đồng trên platform là runtime đổi theo
trong vòng 5 phút**, không phải sửa file trên máy đội.

### Chốt chặn đặt ở đâu

Ở **điểm hội tụ** — nơi mọi tool đi qua. Với Hermes là `ToolRegistry.dispatch`:

```python
lsr_policy.install_registry_guard(audit.ghi_tool)   # bọc dispatch một lần
```

Phải gọi **sau** khi mọi tool đã import và **trước** khi agent đầu tiên được dựng — agent
chụp lại registry lúc khởi tạo.

Cẩn thận đường vòng: `lark_client.call` **không** đi qua `dispatch`. Phải bọc riêng.
Tìm hết các đường ra ngoài trước khi tin là đã chặn đủ.

## Tầng 2 — công tắc Năng lực

Chủ agent bật/tắt từng tool trên console. Lưu vào `agents.capabilities` — **cùng trường**
A2A Agent Card và `/v1/self/directory` đang đọc, nên tắt một năng lực là danh bạ đổi
theo. Agent tự đọc trạng thái của chính mình qua danh bạ.

Ba quyết định về cách hỏng, đều có lý do:

**Chưa khai `capabilities` → không thu hẹp gì.** Mọi agent khác trên platform đang ở
trạng thái này; coi "trống = tắt hết" là làm chết sạch.

**Đọc hỏng → dùng bản nhớ cuối.** Fail-closed ở tầng này không đổi lại an toàn nào —
hợp đồng vẫn đang giữ — mà chỉ khiến một nhịp mất mạng làm agent câm.

**Phải có danh mục tool có công tắc.** `capabilities` chỉ chứa tool **đang bật**; thiếu
danh mục thì runtime hiểu nhầm "không có trong danh sách" thành "bị tắt", và tắt lây cả
`schedule_reminder`, `remember_about_user`, `list_reminders`.

TTL công tắc **60 giây**, cố ý ngắn hơn hợp đồng (300s): hợp đồng đổi hiếm và đi qua quy
trình, còn công tắc là cái nút người ta bấm rồi thử ngay. Đo thật ở bản 300s: tắt xong
hỏi liền thì agent vẫn hứa *"tôi sẽ quét…"* và tool **vẫn chạy** — suốt cửa sổ đó cái
nút không có tác dụng gì.

## Tầng 3 — lời dặn trong prompt

**Đây là tầng nói dối dễ nhất, và đã nói dối thật.**

`brain.py` từng ghim cứng một khối: *"LUẬT VAI PLANNER — Mark KHÔNG có quyền ghi/sửa
Base, Sheet"*. Khi Mark đổi sang `executive` và `lsr_policy` đã cho phép `social_listen`,
prompt vẫn dặn là bị cấm — nên **model từ chối trước khi thử**. Người dùng thấy *"không
có quyền trả sheet"* trong khi quyền đã có từ hôm trước.

Đau ở chỗ **không có gì hỏng**: tool chạy được, policy đúng, chỉ prompt nói sai. Không
log nào báo, không test nào đỏ.

Chữa tận gốc không phải sửa lại chữ cho đúng hôm nay — mai đổi quyền lại lệch tiếp — mà
là **không giữ chữ nào cả**:

```python
for ten, (mo_ta, args) in _TOOL_CAN_XET.items():
    cho = lsr_policy.decide(ten, args).allowed      # hỏi đúng hàm sẽ chặn thật
    (duoc if cho else cam).append(mo_ta)
```

Hai bên không thể lệch vì chỉ còn một bên biết luật.

Kể cả tool **chỉ đọc** cũng phải liệt kê, nếu chúng tắt được bằng công tắc — thiếu thì
tắt xong agent vẫn tưởng mình dùng được, rồi gọi và ăn từ chối giữa câu trả lời.

Lưu ý nhỏ: tool nào cần tham số để `decide()` trả lời đúng thì phải truyền tham số thật.
`lark_cli` với args rỗng luôn bị từ chối vì *"thiếu danh sách args hợp lệ"* — hoá ra lúc
nào cũng báo là bị cấm.

## Runtime được phép hẹp hơn hợp đồng

`lsr_policy` chặn **mọi** `lark_cli --yes`, kể cả khi hợp đồng cho `write_data`. Lý do:
việc ghi mà agent thật sự cần nằm **trong** `social_listen` (xuất Sheet kết quả), không
đi qua `lark_cli`.

Nhưng phải nói rõ trong tài liệu: **chỗ chặn đó là code trên máy đội, không phải hợp
đồng trên platform.** Ai nới dòng đó là mở luôn, không qua duyệt nào.

Và ghi nhớ một hệ quả: `LARK_WRITE_OPS` gắn `base +record-create` với `write_data`. Khai
`write_data` để xuất Sheet là **mở luôn ghi bản ghi Base tuỳ ý** ở mức hợp đồng —
manifest không có mức chi tiết để nói "chỉ được ghi Sheet kết quả".

## Kiểm cả ba tầng

Bộ kiểm toán có 38 mục cho tầng 1, 10 mục cho tầng 2, 22 mục cho tầng 3 — trong đó tầng
3 chạy với **cả ba trạng thái quyền** (`executive` bật hết · `planner` · `executive`
nhưng tắt hết) và đối chiếu từng tool với `decide()`.

Đó là chỗ duy nhất bắt được kiểu lỗi "prompt nói sai": nó không crash, không đỏ ở đâu
khác.
