# 4 · Nhận việc — ingress, vòng job, watchdog

## Hai cửa, một hàng đợi

```
Lark    →  gateway động của platform  ─┐
console web  ─────────────────────────┴→  jobs  →  agent poll  →  brain.reply
```

Cùng một `brain.reply`, không có nhánh riêng. Thứ kiểm trên console chính là thứ chạy
trên Lark — đó là lý do console chat đáng tin làm công cụ kiểm thử.

## Gateway Lark động — và vì sao listener cục bộ không nối được

Platform chạy `event_gateway_dynamic`: cứ 20 giây nó đọc `/v1/runtime/lark-apps`, lấy
app nào `status='approved'` và có `app_secret`, rồi **mở kết nối dài**.

Lark chỉ cho **một bus toàn cục mỗi app**. Nên khi gateway đã cầm, `listener.py` trên máy
đội báo:

```
another event bus is already connected to this app
(1 remote event connection(s) detected via API)
```

**Đây là trạng thái đúng, không phải sự cố.** Tin Lark vẫn tới qua gateway rồi thành
job, agent vẫn trả lời bình thường.

Tôi đã mất nửa tiếng đi tìm "kết nối ma" vì nhìn `bus.log` không thấy dòng
`Consumer connected` rồi kết luận kênh Lark đã chết — trong khi audit cho thấy agent vẫn
trả lời đều. Nên `listener.py` giờ nhận ra chuỗi đó, **in một câu giải thích rồi lùi 10
phút** thay vì thử lại mỗi 30 giây và đổ log.

Câu giải thích nói luôn *"tin Lark vẫn tới qua job, agent vẫn trả lời bình thường"* — để
người đọc log sau không hiểu nhầm như tôi.

> **Cảnh báo cho bản sao thử nghiệm.** Nếu bạn nhân bản thư mục agent để thử, **đổi app
> Lark và agent id** trong `.env` của bản sao. Bản `mark_tran_test` từng khai đúng app
> và đúng agent id của production — chạy lên là giành bus với bot thật.

## Vòng job

```python
jobs = _goi(c, f"/v1/self/jobs?wait=25&max=1")     # long-poll
```

`/v1/self/jobs` **claim job** chứ không chỉ đọc. Gọi nó để "xem có gì" là đã nhận việc —
đừng dùng nó để thăm dò.

Xong thì phải gọi đủ hai đường, không chỉ một:

```
POST /v1/self/jobs/{id}/reply      {text}
POST /v1/self/jobs/{id}/complete   {ok, usage}
```

`usage` nên kèm token thật của lượt đó. Lấy từ sổ audit theo `chat_id` — và nhớ rằng
`lay_luot_vua_xong` là **lấy-và-xoá**, nên chỉ gọi khi lượt đã kết thúc. Gọi lúc lượt
còn dở là cướp số của lượt đang chạy rồi ghi nhầm cho job khác.

## Watchdog — chốt quan trọng nhất của mục này

Vòng job chạy **tuần tự** và gọi `brain.reply` **đồng bộ**. Không có trần thời gian thì
một lượt gọi model treo là **đứng cả cửa console lẫn cửa Lark** — không log, không lỗi,
không cách nào biết ngoài việc nhắn thử rồi ngồi đợi.

Đã xảy ra: một job nằm im 5 phút; khởi động lại thì job kế tiếp xong trong 8 giây.

```python
_HAN_TRA_LOI = 480     # LSR_HAN_TRA_LOI_SECONDS
```

Rộng tay vì tool cào 5 nền tảng có thể chạy vài phút thật — cắt sớm là giết việc hợp lệ.
Nhưng phải có trần.

Quá hạn thì: trả một câu tử tế cho người dùng, đánh dấu job thất bại, **và đi tiếp**.

Luồng quá hạn **không bị giết**: Python không có cách dừng một luồng an toàn, ép dừng
giữa lúc nó giữ khoá hay ghi file thì hỏng nặng hơn. Để nó là daemon, chạy nốt rồi tự
tắt, và không chặn lúc thoát tiến trình.

Quá hạn thì **không đụng vào sổ token** — lượt chưa kết thúc, lấy số lúc này là ghi nhầm
cho job đã bỏ. Thà thiếu số còn hơn số sai.

## In ngay khi nhận, đừng đợi xong mới in

```
[job] #1993 nhận · 'quét social cho anh'
[job] #1993 QUÁ HẠN 480s — bỏ lượt, đi tiếp.
[job] #1993 LỖI · … → 'Xin lỗi, câu này xử lý lâu quá mức cho phép…'
```

Trước đây chỉ có một dòng lúc hoàn tất, nên **job treo trông y hệt "không có job nào"**.
Không phân biệt được bằng log. Đó mới là thứ làm mất thời gian, hơn cả bản thân lỗi treo.

## Nhịp nền khác

Agent có thể có nhiều nhịp chạy song song. Của Mark:

| Nhịp | Chu kỳ | Việc |
| :--- | :--- | :--- |
| `lsr-job` | long-poll 25s | nhận và trả lời job |
| `lsr-wiki` | 20s / 30′ | kiểm lệnh nhập · quét Wiki định kỳ |
| nhắc lịch | 20s | bắn nhắc đã đặt |
| `lsr-wal-flush` | — | đẩy bù telemetry |

Mọi nhịp nền đều phải **nuốt lỗi**: nhịp hỏng không được làm bot chết hay chậm câu trả
lời. Nhưng nuốt thì phải **in ra**, không thì lỗi biến mất luôn.

Và nhịp nào gọi mạng mỗi vòng thì **chọn cửa rẻ**. Nhịp Wiki từng gọi
`/v1/self/directory` (28 KB, join 81 agent) mỗi vòng; đổi sang `/v1/self` (0.5 KB) thì
rút nhịp từ 60s xuống 20s mà vẫn **nhẹ hơn 20 lần**.

## Khởi động lại cho đúng

Dưới Windows Task Scheduler:

```powershell
Stop-ScheduledTask  -TaskName "…"    # PHẢI dừng task trước
Stop-Process -Id <pid> -Force        # rồi mới giết tiến trình
Start-ScheduledTask -TaskName "…"
```

Bỏ bước dừng task thì `Start-ScheduledTask` **trả về thành công nhưng không bật gì** —
task còn kẹt ở trạng thái `Running` từ lần trước và từ chối lượt mới với mã `0x800710E0`.
Bot tắt mà tưởng đã bật.

Và **luôn đếm lại tiến trình sau mỗi bước**, đừng gộp dừng với bật vào một khối: khối lỗi
giữa chừng thì phần bật không chạy, và bot nằm im.
