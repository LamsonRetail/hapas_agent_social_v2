# 8 · Danh sách kiểm

## Bộ kiểm toán chạy lại được

```bash
python scripts/kiem_toan.py              # 130 mục, không gửi tin
python scripts/kiem_toan.py --nhanh      # bỏ mọi thứ gọi mạng
python scripts/kiem_toan.py --dau-cuoi   # gửi tin thật qua ingress
```

Chín khối:

| | Khối | Kiểm gì |
| :-- | :--- | :--- |
| A | Môi trường và cấu hình | khoá có mặt, `.env` thắng, không lẫn tài khoản |
| B | Hợp đồng | manifest ↔ stamp ↔ registry có khớp nhau không |
| C | Policy | quyết định theo hợp đồng, ghim quyền, không mạng |
| D | Công tắc năng lực | lớp thu hẹp, cả ba trạng thái |
| E | Prompt | **cái model thật sự đọc** |
| F | Trạng thái trên platform | version, publication, kiến thức, kênh |
| G | Vận hành | tiến trình, tác vụ lịch, log |
| H | Đối chiếu chéo | hai nơi có nói cùng một chuyện không |
| I | Đầu cuối | gửi tin thật qua ingress, chờ trả lời |

Bốn nguyên tắc trong bộ này đáng bê nguyên sang agent khác:

- **Mọi thay đổi trạng thái đều khôi phục trong `finally`**, kể cả khi nửa chừng lỗi.
  Một bộ kiểm để lại agent ở trạng thái lạ thì tệ hơn không kiểm.
- **Không in giá trị bí mật** — chỉ độ dài và 7 ký tự đầu của sha256.
- **Không tiêu tiền.** Không chạy scrape thật. Phần đầu-cuối chỉ đi đường **từ chối**,
  vốn không gọi tool nào.
- **Mỗi khẳng định nói rõ hỏng thì hậu quả là gì**, không chỉ `assert False`.

Khối E và H là hai khối bắt được loại lỗi mà không khối nào khác thấy: prompt nói sai, và
hai nguồn sự thật đã lệch nhau. Đó cũng là hai loại lỗi đắt nhất trong [mục 7](07-cho-de-sai.md).

## Checklist gắn một agent mới

### Trước khi gõ dòng nào

- [ ] Đọc [mục 7](07-cho-de-sai.md)
- [ ] Chốt `type` theo **việc agent thật sự làm**, không theo tên nhóm ([mục 2](02-nhan-vai.md))
- [ ] Liệt kê mọi **đường ra ngoài** của runtime, không chỉ đường đi qua dispatch

### Nhận vai

- [ ] `manifest/validate` trả 200, ghi lại `type` và `manifest_hash`
- [ ] Bài đánh giá **suy phạm vi từ manifest** và chạy trên registry thật
- [ ] Bài đánh giá nhận `out` **thật**, không phải `[]`
- [ ] Báo cáo ghim `manifest_hash`
- [ ] `enroll` → token ghi thẳng vào `.env`, **không in ra**
- [ ] `.env` có trong `.gitignore`

### Quyền hạn

- [ ] `decide()` hỏi stamp, có nhớ tạm, có đường lùi, fail-closed khi chưa từng gọi được
- [ ] Chốt đặt ở **điểm hội tụ**, cài sau khi import tool và trước khi dựng agent
- [ ] Đường vòng (`lark_client.call`…) đã bọc riêng
- [ ] Khai báo danh mục tool có công tắc
- [ ] Công tắc **chỉ thu hẹp**, không nới
- [ ] Lời dặn trong prompt **sinh ra từ** `decide()`, không gõ tay
- [ ] Thử tắt một năng lực rồi hỏi ngay: agent nói đúng là đang tắt, và tool **không**
      chạy

### Nhận việc

- [ ] Vòng job có **trần thời gian**
- [ ] In log **ngay khi nhận** job, không đợi xong
- [ ] Quá hạn: trả câu tử tế, đánh dấu thất bại, **không** đụng sổ token, đi tiếp
- [ ] Mọi nhịp nền nuốt lỗi **và in ra**
- [ ] Nhịp nào gọi mạng mỗi vòng đã **đo giá một vòng**
- [ ] `listener.py` nhận ra thông báo "bus đã có người" và giải thích thay vì đổ log

### Kiến thức

- [ ] Danh mục nguồn có mục `excluded` **chặn ở mã**, không phải bằng lời dặn
- [ ] Không transcript, không HR/payroll, không credential, không raw PII
- [ ] Kiến thức đã nạp có `status='approved'` — nếu không thì RAG không thấy
- [ ] Nguồn Wiki quét bằng **danh tính sẽ nhập**
- [ ] Đổi link **kích hoạt quét lại**, không đợi hết nhịp
- [ ] Người dùng thấy **tiến trình** khi đang nhập, và có trần thời gian chờ
- [ ] Thứ tự dùng nguồn đã viết vào prompt

### Lên prod

- [ ] Persona có **một nguồn**, và có script đẩy lên
- [ ] Publish đọc trường `publication`, không chỉ mã HTTP
- [ ] Hồi quy đi qua **ingress thật**
- [ ] Hồi quy **lọc case theo skill**
- [ ] Đạt cổng rồi mới prod — không `force`
- [ ] Kiểm lại bằng một câu thật trên Lark

### Bàn giao

- [ ] `kiem_toan.py` xanh toàn bộ
- [ ] Test đơn vị xanh hai phía
- [ ] `REGISTRY.md` và trang tài liệu agent khớp với `type` thật
- [ ] `danh-gia.json` khớp với lần chạy gần nhất
- [ ] Danh sách việc còn treo, viết rõ, không giấu

## Thứ đang treo của Mark

- **Xoay app secret Lark.** Secret cũ đã từng lộ trong một lần trao đổi. Chủ agent quyết
  định dùng tiếp cho tới khi xong việc rồi thay — quyết định đó vẫn đang nợ.
- **Nguồn Wiki đang TẮT**, chờ sign-off ADR `WIKI`. Đường ống đã dựng và kiểm xong; bật
  sớm là kéo cả bảng nhân sự vào kho kiến thức. Mục `G11` trong bộ kiểm toán canh đúng
  chuyện này.
- **Không có endpoint duyệt `agent_changes`** trên platform. Cần báo người giữ platform.
- **`POST /change` bỏ qua thẩm quyền admin**, khác với `/v1/a2a/grant`. Cần báo.
- **Golden case `g_2ca99dedacfb`** dùng assertion `contains` phụ thuộc cách diễn đạt,
  khiến cổng go-live chập chờn. Cần báo người giữ golden set.

## Nếu chỉ nhớ được ba điều

1. **Một nguồn sự thật cho mỗi câu hỏi.** Prompt, policy và manifest nói ba thứ khác nhau
   thì không ai sai rõ ràng — chỉ có agent hành xử khó hiểu.
2. **Hỏng thì phải kêu.** Lỗi đắt nhất ở đây không crash.
3. **Đo, đừng đoán.** Mỗi lần tôi rút ngắn một nhịp hay nới một giới hạn mà không đo
   trước, tôi đều phải quay lại sửa.
