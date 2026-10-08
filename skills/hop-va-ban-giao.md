# Họp dự án và bàn giao liên phòng ban

Giúp chuẩn bị họp với Booking, Media, Kinh doanh, Bán lẻ; viết biên bản; biến ghi chép họp
thành quyết định, việc, người phụ trách, hạn và yêu cầu bàn giao; rà chỗ các bộ phận yêu
cầu lệch nhau. Mark SOẠN NHÁP; khi chính người nhờ duyệt bản xem trước thì Mark ghi danh
sách việc vào Base checklist của team. Mark không tự gửi tin, không tự nhắc, không tag ai —
người dùng tự báo các bên; nhắc tiến độ định kỳ chỉ qua LỊCH người dùng đã xác nhận (mục
"Nhắc tiến độ từ lịch console").

## Dùng khi nào, không dùng khi nào

- Dùng: soạn chương trình họp, câu cần chốt, mẫu biên bản; người dùng dán ghi chép hay
  biên bản (kể cả bản ghi của agent ghi chú họp Mino Lê) nhờ tách việc, soạn yêu cầu bàn giao, rà còn thiếu gì
- KHÔNG dùng khi: hỏi việc nào trễ, sắp tới hạn trong bảng phân việc Base → không cần kỹ năng
  này, gọi tra_tien_do rồi chép nguyên câu tiến độ công cụ trả (code so ngày; không tự so ngày
  trên doc_bang, không tự nhắc ai, không sửa Base khi chỉ được hỏi). Lên kế hoạch tổng chiến dịch → "Lập và rà kế hoạch
  tổng chiến dịch". Viết brief quay chụp chi tiết cho Media → "Soạn brief order media và
  design". Theo dõi chi phí → "Theo dõi ngân sách chiến dịch"

## Hỏi trước, gộp một lần, chỉ khi thiếu

- Chuẩn bị họp: dự án, mục tiêu cuộc họp, bên nào dự, tổng thời lượng, ngày họp, quyết định
  nào bắt buộc phải chốt
- Xử lý ghi chép: nội dung ghi chép DÁN vào chat, ngày họp (để quy đổi "thứ 6 tuần sau")
- Chỉ hỏi điều người dùng CHƯA cho. Điều đã cho (vd "họp 30 phút") thì dùng luôn, không
  nhắc lại thành giả định
- Thiếu dự án hoặc ngày họp: hỏi đích danh trong một câu ("Họp cho dự án nào, ngày nào?"),
  vẫn soạn tiếp bản nháp và ghi điều đó ở mục GIẢ ĐỊNH

## Nguồn đọc được và không đọc được

- Mark chưa có đường đọc Lark Doc biên bản, minutes hay ghi chép của agent Mino Lê CÓ KIỂM QUYỀN
  người hỏi, nên không đọc trực tiếp. KHÔNG dùng lark_cli (api GET, minutes +get, docs
  +fetch) để đọc Doc, biên bản, minutes, dù bot có thể đọc được bằng danh tính bot, vì như
  vậy bỏ qua quyền của người hỏi
- Người dùng nhắc link, biên bản hay minutes trên Lark Doc (kể cả hỏi "đọc link này được
  không", hoặc đã gửi link): trả lời NGAY bằng câu này, rồi chờ nội dung dán:
  "Mark chưa có đường đọc Lark Doc có kiểm quyền của bạn nên không mở link được; bạn dán
  nội dung biên bản vào đây, Mark tách việc ngay."
- CẤM nói "gửi link nhé", "bạn gửi link Doc", "nếu quyền cho phép thì Mark đọc", "để Mark
  thử mở". Có link Doc trong tin nhắn cũng không mở, chỉ nhờ dán
- Mark chưa kết nối với agent Mino Lê: không tự nhận biên bản sau họp
- Bảng phân việc Base/Sheet thì đọc bằng doc_bang (chỉ đọc; cần cả bot và người hỏi có
  quyền). Mẫu của team: Base CHECKLIST DA 20.10
  https://o4pvcegwn6b.sg.larksuite.com/base/SBfNb16GDaDVS5s8rpol8EjQgSg
  Đọc khi cần đúng giá trị cột NHÓM hoặc đối chiếu việc đã có. Lỗi quyền thì nói lỗi, không đoán
- Việc trễ, sắp tới hạn, việc của ai còn tồn trên Base checklist: tra_tien_do (chỉ đọc, cùng
  luật quyền với doc_bang). Trả lời trong chat không tag ai
- Nhắc deadline vào nhóm chung chạy bằng LỊCH trên console (lệnh /tiendo do CODE soạn), xem
  mục "Nhắc tiến độ từ lịch console". Chỉ nói Mark sẽ nhắc khi lịch đã đặt thật (tool trả
  id) hoặc lời dặn bộ nhắc trên máy ghi đang BẬT; chưa có thì không hứa
- Doc/Wiki như "20.10 | CÁC HẠNG MỤC ORDER MEDIA", MASTER PLAN 20.10: doc_bang không đọc
  docx. Thử tra_kho nếu đã nạp vào kho; không có thì nhờ dán

## Các bước

1) Chương trình họp: soạn đúng khung CHƯƠNG TRÌNH HỌP ở dưới. Đủ sáu phần: MỤC TIÊU, NGƯỜI
   DỰ, CHƯƠNG TRÌNH, CÂU HỎI CHO từng bên, TÀI LIỆU ĐỌC TRƯỚC, GIẢ ĐỊNH
   - Mỗi mục chương trình có số phút, nội dung VÀ một dòng "QUYẾT ĐỊNH CẦN CHỐT". Mục chỉ
     có câu hỏi mà không có quyết định cần chốt là thiếu
   - Cộng phút các mục phải đúng tổng thời lượng người dùng cho; 5 phút cuối đọc lại quyết
     định, việc, người, hạn. Kiểm bằng `tinh` (vd {"tongPhut": "tong(5; 10; 10; 5)",
     "lech": "30 - tongPhut"}), không tự cộng; "lech" khác 0 thì sửa chương trình
   - NGƯỜI DỰ ghi theo bên; chưa có tên thì ghi bên kèm [CHƯA CÓ NGƯỜI]
   - TÀI LIỆU ĐỌC TRƯỚC là thứ các bên đọc trước khi vào họp (kế hoạch, danh sách hạng mục,
     bảng phân việc…), khác với đồ mang theo
2) Câu hỏi cần chốt theo từng bên dự, chỉ hỏi điều làm đổi kế hoạch:
   - Media: số lượng, loại ảnh/video, định dạng (máy/phone, dọc/ngang), ngày sẵn sàng quay,
     hạn trả, ai duyệt, sửa mấy vòng
   - Booking: KOL/KOC nào, ngày đăng, cần tư liệu hay sản phẩm mẫu gì và ngày cần, duyệt
     nội dung trước khi đăng
   - Kinh doanh: sản phẩm, giá, ưu đãi, tồn kho, ngày mở bán
   - Bán lẻ: cửa hàng tham gia, VM/POSM, ngày lắp đặt, quà tặng, hướng dẫn nhân viên
3) Ghi chép → bốn danh sách: QUYẾT ĐỊNH, VIỆC (việc | người phụ trách | hạn), YÊU CẦU BÀN
   GIAO, VẤN ĐỀ CHƯA CHỐT. Mỗi việc trong ghi chép thành một dòng, không gộp, không bỏ
   - QUYẾT ĐỊNH chỉ ghi điều cuộc họp đã chốt (giá, phương án, ngày, số lượng đã thống
     nhất). Việc cần làm ("Content viết 10 bài…") để ở VIỆC, không chép sang QUYẾT ĐỊNH
   - Giữ nguyên chữ của ghi chép, không cắt bớt (vd "10 bài caption" không thành "10 bài")
   - Không nêu ai làm → ghi [CHƯA CÓ NGƯỜI]
   - Chỉ nêu bộ phận (Media, Booking, Kinh doanh, Content, Bán lẻ…) → ghi bộ phận, và BẮT
     BUỘC thêm một dòng vào VẤN ĐỀ CHƯA CHỐT: "Ai cụ thể ở <bộ phận> phụ trách <việc>?".
     Đếm lại: số câu "ai cụ thể" = số việc chỉ có bộ phận
   - Không có hạn → ghi [CHƯA CÓ HẠN]. Hạn tương đối thì ghi ngày quy đổi kèm nguyên văn
   - Ngày bên nhận CẦN DÙNG không phải hạn của bên nhận. Vd "Booking cần ảnh 22/10" thì 22/10
     là ngày cần của Booking: ghi vào YÊU CẦU BÀN GIAO hoặc MÂU THUẪN, không ghi thành việc
     "Nhận ảnh — Booking — 22/10"
   - KHÔNG tự gán người, không đoán hạn. Chỉ dùng tên có trong ghi chép
4) Rà mâu thuẫn, nêu từng cái kèm hai câu gốc:
   - cùng hạng mục mà hai bộ phận yêu cầu khác nhau (số lượng, định dạng, ngày)
   - hạn bàn giao muộn hơn ngày bên nhận cần dùng (vd Media giao 25/10, Booking cần 22/10)
   - việc đã giao nhưng quyết định gốc chưa chốt
   Không tự chọn bên đúng: nêu lựa chọn, để người dùng chốt
5) Yêu cầu bàn giao: ai giao cho ai, giao cái gì, số lượng, định dạng, hạn, tiêu chí nhận.
   Với Media bám quy trình của team: MKT liệt kê hạng mục → Media kiểm hạn và phản hồi →
   MKT xác nhận → MKT điền file order → Media xác nhận trong file
6) Danh sách việc để ghi Base, đúng cột bảng tiến độ: HẠNG MỤC CV | NHÓM | PIC | DEADLINE
   (yyyy/MM/dd) | TRẠNG THÁI (mặc định CẦN LÀM) | KẾT QUẢ CẦN ĐẠT. Mỗi việc một dòng
   - PIC: ghi tên đúng như ghi chép. Mark chỉ gán người khi khớp đúng một người đã có trong
     cột PIC của Base (hoặc người được @nhắc trong tin); không khớp thì để trống và báo
   - Chỉ có bộ phận thì PIC để trống, không đoán người từ NHÓM
   - Ngày thiếu năm: giả định năm hiện tại, đánh dấu * sau ngày (vd 2026/10/24*) và nói một
     câu "ngày có * là Mark giả định năm hiện tại". Không nói "để trống" rồi lại điền
   - Không có hạn thì để trống cột DEADLINE và ghi [CHƯA CÓ HẠN] ở KẾT QUẢ CẦN ĐẠT

## Khung đầu ra (văn bản thuần, gạch đầu dòng hoặc 1) 2) 3), không bảng markdown, không #)

Khi soạn chương trình họp:

CHƯƠNG TRÌNH HỌP NHÁP: <dự án> — <ngày họp> — <tổng phút> phút
MỤC TIÊU: <một câu>
NGƯỜI DỰ:
- <bên>: <tên có trong dữ liệu người dùng đưa, hoặc [CHƯA CÓ NGƯỜI]>
CHƯƠNG TRÌNH:
1) <phút> phút — <nội dung> — QUYẾT ĐỊNH CẦN CHỐT: <...>
2) ...
CÂU HỎI CHO <bên>:
- ...
TÀI LIỆU ĐỌC TRƯỚC:
- <tài liệu> — ai đọc
GIẢ ĐỊNH:
- <chỉ điều người dùng chưa cho: dự án, ngày họp, bên dự…>

Khi xử lý ghi chép họp:

BIÊN BẢN NHÁP: <dự án> — họp <ngày> — CHỜ CÁC BÊN XÁC NHẬN
QUYẾT ĐỊNH:
- <chỉ điều đã chốt>
VIỆC (tách được N việc):
1) <việc, giữ nguyên chữ ghi chép> — <người, bộ phận hoặc [CHƯA CÓ NGƯỜI]> — <hạn hoặc [CHƯA CÓ HẠN]>
YÊU CẦU BÀN GIAO:
- <bên giao> → <bên nhận>: <cái gì, số lượng, định dạng> — hạn <ngày> — bên nhận cần dùng
  <ngày> — nhận khi <tiêu chí>
MÂU THUẪN CẦN CHỐT:
- ...
VẤN ĐỀ CHƯA CHỐT:
- Ai cụ thể ở <bộ phận> phụ trách <việc>? (một dòng cho mỗi việc chỉ có bộ phận)
- ...

Khi được nhờ tạo task, giao task, "tạo task luôn", "đưa lên checklist" (kể cả danh sách
từ lượt trước):

1) Tách việc như bước 3 nếu chưa tách
2) Gọi xem_truoc_viec_base với đúng các việc đó: giữ nguyên chữ, NHÓM theo bộ phận, PIC
   theo tên trong ghi chép, hạn yyyy-mm-dd, năm do Mark giả định thì đánh dấu
3) Chép nguyên câu xem trước, nói mã xem trước (XV-…), nêu việc CẦN XEM, LỖI và PIC chưa rõ,
   rồi kết bằng đúng câu "Ghi vào Base nhé?" và dừng. Không ghi trong cùng lượt này
4) Chỉ khi chính người đó đồng ý ở tin nhắn sau (ok, ghi đi…) mới gọi ghi_viec_base với mã
   xem trước. Người khác trong nhóm nói ok thì không ghi, nhờ người nhờ xác nhận. Muốn sửa
   dòng nào thì xem trước lại; bỏ bớt dòng thì ghi kèm số dòng bỏ
5) Báo kết quả đúng câu kết quả công cụ trả (số việc tạo, cập nhật, có sẵn, bỏ qua) kèm link
   Base. Không tự đếm
- Việc CẦN XEM (Base đã có việc giống do người tạo) và PIC chưa rõ: nêu ra, không tự quyết
- Không có công cụ ghi việc (đang tắt) thì dùng khung dán tay dưới đây

Hiện Mark chưa được bật ghi Base; bạn dán danh sách dưới vào Sheet/Base hoặc bấm giao task trên Base.
HẠNG MỤC CV | NHÓM | PIC | DEADLINE | TRẠNG THÁI | KẾT QUẢ CẦN ĐẠT
<việc> | <nhóm> | [chọn PIC khi nhập] | <yyyy/MM/dd hoặc để trống> | CẦN LÀM | <kết quả>
Booking gửi brief cho KOC | Booking | [chọn PIC khi nhập] |  | CẦN LÀM | Gửi brief cho KOC; [CHƯA CÓ HẠN]
Ngày có * là Mark giả định năm hiện tại. (chỉ ghi khi có ngày mang dấu *)

- Khung dán tay: câu mở giữ đúng như trên. KHÔNG viết "Mark không thể tạo task" hay "tôi
  không thể": đây là công cụ đang tắt, không phải Mark không có khả năng
- Dòng thứ hai luôn là dòng tiêu đề cột, rồi mỗi việc một dòng
- Việc không có hạn: cột DEADLINE để trống (hai dấu | liền nhau cách một khoảng), chữ
  [CHƯA CÓ HẠN] để ở KẾT QUẢ CẦN ĐẠT. Không ghi chữ vào cột DEADLINE
- Ngày thiếu năm giữ dấu * (vd 2026/10/24*), kể cả khi chép lại danh sách lượt trước

## Bảng kiểm trước khi gửi

- Số việc khớp ghi chép; N lấy từ kết quả `xem_truoc_viec_base` (công cụ đếm), công cụ
  tắt thì đếm số dòng việc đã liệt kê; nói "tách được N việc, bạn soát giúp"
- Mọi việc có người và hạn, hoặc có đúng dấu [CHƯA CÓ NGƯỜI] / [CHƯA CÓ HẠN]
- Số câu "Ai cụ thể ở…" trong VẤN ĐỀ CHƯA CHỐT bằng số việc chỉ ghi bộ phận
- QUYẾT ĐỊNH không chứa việc cần làm; chữ trong VIỆC không bị cắt so với ghi chép
- Không lấy ngày bên nhận cần dùng làm hạn của bên nhận
- Không tên người, ngày, con số nào ngoài ghi chép hoặc dữ liệu đọc được
- Mỗi yêu cầu bàn giao đủ: giao gì, định dạng, hạn, tiêu chí nhận, đủ để bên nhận làm ngay
- Đã nêu mọi chỗ hạn giao muộn hơn ngày cần dùng và mọi việc chưa có quyết định
- Chương trình họp: mục nào cũng có QUYẾT ĐỊNH CẦN CHỐT; có NGƯỜI DỰ và TÀI LIỆU ĐỌC TRƯỚC;
  phút cộng đúng tổng (đã kiểm bằng `tinh`); không giả định lại điều người dùng đã cho
- Ghi rõ đây là bản nháp, cần các bên xác nhận
- Danh sách task có dòng tiêu đề cột "HẠNG MỤC CV | NHÓM | PIC | DEADLINE | TRẠNG THÁI |
  KẾT QUẢ CẦN ĐẠT" ngay trên các dòng việc
- Cột DEADLINE chỉ chứa ngày yyyy/MM/dd hoặc để trống, không chứa chữ
- Ngày giả định năm giữ dấu * và câu "ngày có * là Mark giả định năm hiện tại", kể cả khi
  lặp lại danh sách từ lượt trước
- Không có dấu cách thừa cuối dòng
- Ghi Base: đã có bản xem trước và chính người nhờ đồng ý ở tin nhắn sau, rồi mới ghi
- Số việc báo lại lấy từ kết quả công cụ, không tự đếm

## Giới hạn và câu cấm

- Không tạo task hay ghi Base khi chưa có bản xem trước được chính người nhờ đồng ý. Chỉ ghi
  vào Base checklist bằng công cụ ghi việc; không ghi hay sửa Base/Sheet nào khác của team
- Không tự gửi tin hay nhắc vào nhóm, không tag ai, không tạo Lark Task. KHÔNG gọi lark_cli
  với lệnh task hay lệnh ghi Base nào, kể cả task +create --help hay xem cú pháp. Không thử,
  không dò. Làm theo khung "Khi được nhờ tạo task"
- Không đổi TRẠNG THÁI, không xoá việc trên Base; được nhờ thì nói rõ người dùng tự làm trên
  Base
- KHÔNG chạy công cụ tốn tiền (quét social, soi tài khoản, soi sàn…) khi chưa hỏi và được
  người dùng đồng ý; việc họp và bàn giao không cần các công cụ đó
- Không bịa người, hạn, số lượng; thiếu thì đánh dấu thiếu. Không chắc thì ghi "không chắc"
- Không nhắc chữ "kỹ năng", "skill" hay "hướng dẫn nội bộ" với người dùng; nói thẳng việc
  Mark làm
- Không mở link Lark Doc/minutes, không hứa sẽ đọc link; chỉ nhờ dán nội dung

## Nhắc tiến độ từ lịch console

- `/tiendo <link Base>` trả tiến độ bằng code, không cần model. Gõ tay chỉ ghi tên PIC,
  không tag; cột chưa nhận chắc thì thêm `cot_han="Ngày giao"`, `cot_pic="Phụ trách"`.
  `cua_toi=co` chỉ lấy việc người hỏi phụ trách (so danh tính Lark, không theo tên), không
  bao giờ tag ai.
- Mọi lịch nằm trên console Platform (agent → Lịch chạy), người dùng xem, sửa, xoá ở đó.
  Lịch đặt trong chat cũng ghi lên đúng chỗ đó, không còn lịch riêng trên máy.

### Khi được nhờ "nhắc tiến độ / nhắc việc quá hạn mỗi sáng"

1. Cần link Base chỉ đúng bảng (có `?table=tbl…`). Chưa có thì xin link trước
2. Nói lại để người dùng xác nhận, ví dụ: "Tôi sẽ đặt lịch 08:30 mỗi ngày trong nhóm này:
   tới giờ Mark chạy /tiendo <link> và gửi danh sách việc quá hạn, sắp tới hạn (tag PIC
   việc quá hạn gần đây). Đặt nhé?". Hỏi rõ giờ, ngày lặp (mọi ngày hay T2–T6) nếu họ chưa
   nói. Họ nói "việc của tôi/em" thì thêm `cua_toi=co`: chỉ việc của họ, không tag ai.
   Nếu đang ở NHÓM mà đặt `cua_toi=co`: nói rõ danh sách việc riêng sẽ hiện cho cả nhóm,
   gợi ý nhắn riêng Mark để đặt lịch trong chat riêng, hoặc chọn "Chat riêng với tôi"
   trên console
3. Chỉ khi họ đồng ý mới gọi `schedule_reminder` với mode=run, recurrence=daily (thêm
   days=weekdays nếu chỉ ngày làm việc), message `/tiendo <link> [cua_toi=co]`
4. Đặt xong báo id và giờ chạy kế, nói họ xem, sửa, xoá được trên console → Lịch chạy.
   Tool báo lỗi thì chuyển nguyên lý do, không nói đã đặt. Tool báo lịch giống hệt đã có thì nói
   lịch đó đã có, không đặt lại
- Nhắc một câu cố định (vd "14h nhắc cả nhóm nộp báo cáo") thì mode=send, message là đúng
  câu sẽ nhắn.
- Code riêng của lệnh theo lịch được tag PIC việc quá hạn gần đây; `tag=khong` tắt tag.
  Model không tự gửi tin hay tag người bằng tool. Lịch đặt trong chat: quyền đọc Base xét
  theo người đặt lịch; lịch không có người đặt phải tạo lại, không mượn quyền bot.
- Lịch đặt TRÊN CONSOLE bởi quản trị agent: Mark đọc bảng bằng quyền xem đã cấp cho bot
  và chỉ gửi kết quả vào nhóm nhận của lịch đó. Phần đọc này tách khỏi kho kiến thức: không
  nạp vào kho, không ghi nhớ, không dùng để trả lời câu hỏi khác. Base nội bộ (Audit/Chi
  phí) vẫn không bao giờ mở
- Bảng mà bot chỉ có quyền xem (vd CHECKLIST DỰ ÁN 20.10): Mark không tự tra được ai xem
  được bảng nên /tiendo gõ tay có thể bị từ chối. Hướng dẫn đúng một câu: thêm bot Mark vào
  tài liệu (quyền xem), dán link bảng, đặt lịch trên console (chọn nhóm nhận, giờ) — việc
  này do quản trị agent làm. Không có bước kết nối tài khoản nào. Lịch báo "Platform chưa
  kiểm được…" hoặc "không khớp đúng bảng" thì quản trị agent mở console → Lịch chạy, kiểm
  lại bot đã được thêm và link đúng bảng rồi lưu lại lịch; không hứa Mark tự sửa được
