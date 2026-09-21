# 6 · Lên prod — version, cổng hồi quy, publish

## Hai môi trường, một nửa sự thật

Console cho publish một version lên `dev` hoặc `prod`. Runtime của agent **chỉ đọc
`prod`** — trừ agent có ID kết thúc `-TEST` thì đọc `dev`.

Nên `dev` là chỗ **xem trước an toàn**: console đã hiện đúng nội dung mới, bot ngoài Lark
chưa đổi gì. Mọi thay đổi persona nên đi qua dev trước.

## Persona: một nguồn, đẩy lên, đừng gõ hai lần

Trang agent trên console lấy Tiểu sử / Tính cách / Mô tả từ `persona` của version đang
sống. Hành vi bot thì lấy từ `persona.md` trên máy đội. Hai nơi, một sự thật — nên
`persona.md` là gốc và có script đẩy lên:

```bash
python scripts/dong_bo_tieu_su.py          # tạo draft + publish dev
python scripts/dong_bo_tieu_su.py --prod   # publish prod (bot thật đổi theo)
```

`instruction_block` mà platform biên dịch từ persona + kỹ năng được **ghép thẳng** vào
prompt sống của bot. Đây không phải trường trang trí trên console.

### HTTP 200 không có nghĩa là đã publish

`POST /publish` trả 200 kèm `publication: "pending_approval"` khi người gọi không đủ
quyền. Script bản đầu chỉ kiểm mã HTTP nên **báo thành công trong khi version nằm chờ
duyệt** — console vẫn hiện nội dung cũ và không ai hiểu tại sao.

Giờ nó đọc trường `publication`, và thoát mã 2 nếu không phải `published`.

Nguyên tắc rộng hơn: **kiểm cái mà API nói nó đã làm, đừng kiểm cái mà nó nhận được yêu
cầu.**

## Cổng hồi quy trước prod

`_eval_gate` đòi một bản hồi quy **PASS gắn đúng version** trước khi cho publish prod.

Chỗ hụt: `POST /v1/regression/run` **chỉ chấm điểm câu trả lời nộp lên** — nó không tự
gọi agent. Phải có một bộ ở giữa:

```
lấy golden case  →  đưa qua ingress THẬT  →  gom câu trả lời  →  nộp chấm
```

`scripts/chay_hoi_quy.py` làm việc đó. Hai quyết định trong nó đáng mang sang agent khác:

**Đi qua đúng ingress thật** (`/v1/chat/{id}/messages`), không gọi model trực tiếp. Hồi
quy phải đo thứ người dùng thật sự gặp — gồm cả policy, công tắc năng lực và prompt. Gọi
thẳng model là đo một hệ thống khác.

**Lọc case theo skill.** Golden set dùng chung cho nhiều agent. Trong 10 case active có 5
case của agent pháp chế. Chấm Mark bằng những câu đó là chấm sai người: Mark trả lời
**đúng** bằng cách nói "ngoài phạm vi", nhưng điểm vẫn 0 vì không chứa chuỗi mong đợi.

### Cổng này đang chập chờn — biết trước thì đỡ hoang mang

Cùng một đầu vào, hai lượt liền: **4/5 rồi 5/5**. Không phải agent đổi.

Nguyên nhân: một số golden case chấm bằng `contains` trên **một cách diễn đạt**. Model
trả lời đúng ý nhưng chọn chữ khác là trượt. Case `g_2ca99dedacfb` là ví dụ.

Đừng chữa bằng `force=true`. Chạy lại là đường đúng; và chuyện assertion phụ thuộc cách
diễn đạt cần báo lên người giữ golden set, không phải vá ở phía agent.

## Trình tự một lần lên prod

```
1. sửa persona.md / kỹ năng
2. dong_bo_tieu_su.py            → draft + publish dev
3. xem console, đối chiếu
4. chay_hoi_quy.py               → chạy qua ingress thật, nộp chấm
5. đạt → --publish-prod
6. kiểm lại trên Lark bằng một câu thật
```

Bước 6 không bỏ được. Bốn bước trên chứng minh platform đã ghi đúng; chỉ bước 6 chứng
minh **bot đang chạy** đọc được nó.

## Ghi chú vận hành

- Console dưới PowerShell 5.1 chạy cp1252. Script in tiếng Việt phải
  `reconfigure(encoding="utf-8")` ở đầu — không thì `print` ném **giữa chừng**, để lại
  một draft đã tạo mà không ai publish.
- Version đã publish thì không sửa được, chỉ tạo version mới. Đừng coi publish là "lưu".
