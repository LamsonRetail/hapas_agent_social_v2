# 1 · Kiến trúc — ai sở hữu gì

## Ranh giới

```
PLATFORM (VM)                          AGENT (máy của đội)
─────────────────────────────          ─────────────────────────────
danh tính agent, tên, squad            mã nguồn, mô hình, tool
hợp đồng quyền hạn (out_allowed)       persona / tính cách
hàng đợi việc (jobs)                   cách trả lời
kho kiến thức + RAG                    quyết định gọi tool nào
telemetry, quota, audit                chốt chặn quyền tại chỗ
kill-switch                            nhịp nền (Wiki, nhắc lịch)
ingress Lark (gateway động)
```

Nguyên tắc chia: **platform giữ thứ cần kiểm soát tập trung, agent giữ thứ cần chạy
nhanh và riêng.** Platform không bao giờ chạy mã của đội; đội không bao giờ tự cấp quyền
cho mình.

## Ba danh tính, đừng lẫn

Đây là chỗ nhầm nhiều nhất trong hai tuần đầu.

| Danh tính | Là gì | Dùng để |
| :--- | :--- | :--- |
| **Agent token** | `lsr_tel_…` trong `.env` của agent | agent gọi `/v1/self/*` |
| **Token người dùng** | `~/.lsr/token`, phiên console | người/script gọi API quản trị |
| **Bot Lark** | `cli_…` + app secret | đọc Wiki, gửi tin, tra Base |

Ba cái này **quyền khác nhau và không thay thế được cho nhau**:

- Agent token đọc được `/v1/self/directory` nhưng **không** đọc được `/v1/roles/catalog`
  (401) — nó chỉ biết về chính nó.
- Token người dùng đọc được `/spec`, `/profile`, `/manifest`… nhưng **không** đọc được
  `/v1/agents/{id}/persona` hay `/skills` (403) — Caddy chặn ở biên.
- Bot Lark có thể đọc một node Wiki mà **không** liệt kê được space chứa nó. Danh sách
  space rỗng **không** chứng minh bot thiếu quyền. Chi tiết ở [mục 7](07-cho-de-sai.md).

Khi một lời gọi trả 401/403, câu hỏi đầu tiên luôn là *"đang dùng danh tính nào"*, không
phải *"thiếu quyền gì"*.

## Caddy chặn gì ở biên

Platform đứng sau Caddy. Từ ngoài chỉ qua được một danh sách trắng hẹp:

```
@selfserve   enroll · /bootstrap/* · /v1/self* · /v1/lark/* · /v1/chat/*
             /v1/roles/catalog · /v1/agents/manifest/validate · /v1/hosts
@selfagent   /v1/agents/{id}/(golive-checklist|spec|profile|lark-identities
                              |manifest|changes|change|agent-card)
```

Không có trong danh sách thì **403 từ biên**, kể cả khi bạn là admin. Ví dụ đã vấp:
`/v1/agents/{id}/knowledge`, `/v1/golden-cases`, `/v1/regression/run`, `/v1/audit`.

Đường vòng hợp lệ: **route của console** (`https://app.…/api/…`) chạy bên trong nên tới
được, và vẫn đi qua đúng kiểm quyền của `platform_api`.

Có một proxy admin ở `POST /api/admin` với danh sách trắng riêng. **Nó LUÔN POST**, bỏ
qua mọi ý định đọc — đừng dùng nó để "xem thử" một endpoint mà POST có tác dụng phụ.

## Hai cửa nhận việc

```
Lark  →  gateway động của platform  →  hàng đợi job  →  agent poll  →  trả lời
console web  ──────────────────────────┘
```

Cả hai cửa **đổ vào cùng một hàng đợi** và cùng một `brain.reply`. Không có bộ não thứ
hai, không có nhánh xử lý riêng — đó là chủ ý: thứ kiểm trên console chính là thứ chạy
trên Lark.

Platform có **gateway Lark động**: nó tự mở kết nối dài cho mọi app `approved`. Lark chỉ
cho **một bus toàn cục** mỗi app, nên `listener.py` chạy trên máy đội **không nối được
nữa** — và đó là trạng thái đúng, không phải sự cố. Xem [mục 4](04-nhan-viec.md).

## Luồng một lượt trả lời

```
1. job vào hàng đợi                    platform
2. agent poll /v1/self/jobs            long-poll 25s
3. agent hỏi /v1/self/context          instruction + RAG + lịch sử
4. agent hỏi /v1/self/stamp            quyền phát hiện hành (nhớ tạm 5′)
5. dựng prompt                          persona.md + luật quyền + ngữ cảnh platform
6. gọi model, gọi tool                  mỗi tool qua lsr_policy.decide()
7. POST /jobs/{id}/reply + /complete    kèm token đã dùng
```

Bước 4 và 6 là chỗ platform thật sự cầm quyền. Bước 5 là chỗ dễ nói dối nhất — xem
[mục 3](03-quyen-han.md).

## Vì sao agent đọc Wiki chứ không phải platform

ACL Wiki cấp **theo từng space cho từng bot**. Node nào bot không đọc được thì cũng
không nhập được. Để platform đọc bằng danh tính khác sẽ cho ra một bản đồ nội dung
**khác** với thứ agent thật sự lấy được — và người dùng sẽ tin vào bản đồ sai đó.

Nguyên tắc chung: **chỗ khảo sát phải đúng là chỗ sẽ thực thi.**
