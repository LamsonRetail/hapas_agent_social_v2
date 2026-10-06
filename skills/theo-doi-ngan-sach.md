# Theo dõi ngân sách chiến dịch

Lập mẫu, rà và đối chiếu ngân sách một chiến dịch: dự toán duyệt so với báo giá, đã cam
kết, đã thanh toán và dự kiến cuối kỳ, không chỉ nhìn tiền đã chi. Mark ĐỌC, TÍNH và ĐỀ
XUẤT. Không sửa bảng của team.

Đọc kỹ năng này cả khi người dùng gõ /bang hoặc dán link Sheet ngân sách: lệnh cứng chỉ ép
gọi công cụ, không thay quy trình dưới đây. `doc_bang` bị từ chối vì chưa có quyền thì
KHÔNG dừng ở câu xin quyền: xin người dùng dán số tab BẢNG TỔNG và nêu trước các điểm sẽ
soát (xem mục "Đọc bảng của team").

Không dùng cho: hiệu quả quảng cáo, tăng/giảm/tắt camp, tab check-in chỉ số ads → kỹ năng
"Audit hiệu quả quảng cáo". Lên kế hoạch chiến dịch mới (ngân sách tổng theo kênh) → "Lập
kế hoạch chiến dịch quảng cáo".

## Hỏi trước (gộp một lần)

1. Chiến dịch nào, kỳ nào, tổng ngân sách được duyệt
2. Nguồn số: link Sheet/Base, số dán vào chat, hay ảnh chụp báo giá
3. Muốn gì: lập mẫu mới, rà bảng đang có, hay đối chiếu báo giá với kế hoạch
4. Ngưỡng cảnh báo team đã chốt chưa (chưa thì dùng đề xuất bên dưới và nói rõ)

## Mẫu cột theo dõi

Liệt kê ĐỦ 16 cột theo đúng thứ tự, đánh số 1–16, không bỏ cột nào, nhất là cột %:

1) Nhóm 2) Hạng mục 3) Chi tiết/số lượng 4) Đơn giá 5) Dự toán duyệt 6) Báo giá 7) Đã cam
kết 8) Đã thanh toán 9) Dự kiến phát sinh 10) Dự kiến cuối kỳ 11) Chênh lệch 12) % 13) Mục
tiêu KQ 14) Thực tế KQ 15) Chi phí/KQ 16) Chứng từ

Công thức, mỗi công thức một gạch riêng:

- Dự kiến cuối kỳ = Đã cam kết + Dự kiến phát sinh (khoản chưa cam kết thì lấy Báo giá
  hoặc Dự toán)
- Chênh lệch = Dự toán duyệt − Dự kiến cuối kỳ (âm là vượt)
- % = Chênh lệch / Dự toán duyệt, dùng để gắn mức đỏ/vàng (xem "Cảnh báo cần soát")
- Chi phí/KQ = Dự kiến cuối kỳ / Thực tế KQ (view, post, lượt ghé)

5 nhóm chuẩn và ánh xạ tên nhóm trong bảng team: Sản xuất (PRODUCTION, SẢN XUẤT CONTENT,
sản xuất áo/quà) · Quảng cáo (ADS) · Booking (BOOKING: KOL, KOC, PR/báo chí) · Cửa hàng
(OFFLINE: EVENT, VM, ACTIVATION, OOH) · Khác (COLLAB và phần còn lại). Tên lạ thì hỏi,
không tự gán.

Khoản dễ sót (lập mẫu hay rà đều phải soát): VAT và thuế TNCN của KOL/KOC, vận chuyển,
phát sinh ngày quay và overtime, in lại, quà/merch, phí nền tảng, thuê/setup/dọn địa
điểm, phí agency, dự phòng 10–15%. Dự phòng luôn ghi bằng VND (vd 200 triệu → 20–30
triệu ₫), không chỉ ghi phần trăm.

## Đọc bảng của team

Bảng mẫu: QUẢN LÝ NGÂN SÁCH & MỤC TIÊU HAPAS 20.10, tab BẢNG TỔNG.

- Đọc riêng một tab bằng `doc_bang` với
  https://o4pvcegwn6b.sg.larksuite.com/sheets/OsbvsgC1chru5mtG7RFli2vFg1b?sheet=f99011
  hoặc mã sheet:OsbvsgC1chru5mtG7RFli2vFg1b_f99011. Link Wiki của bảng bỏ qua ?sheet= nên
  đọc cả 6 tab, rất dài
- Header 2 tầng, `doc_bang` lấy dòng 1 làm tiêu đề. Cột: Nhóm lớn, Hoạt động, Chi tiết,
  NGÂN SÁCH (dự toán), các cột "CHI PHÍ THỰC TẾ (dd.m)", mục tiêu/thực tế view, số post
- Qua `doc_bang` số là số thô (vd 1070000000, có thể lẻ thập phân). Số người dùng dán có
  thể dạng "1,070,000,000 ₫": bỏ dấu phẩy và ₫ rồi mới tính. "-" là không áp dụng
- Không thấy công thức. Cấp cha/con suy từ tên dòng (nhóm cha viết hoa), kiểm bằng tự cộng
- Tổng dự toán, tổng thực tế đọc thẳng dòng TỔNG (Sheet đã tính), ghi "theo dòng TỔNG"
- Mỗi khoản vượt ghi rõ số lấy ở cột nào. Ô cột mới nhất trống hoặc "-" thì lấy cột trước
  và ghi "(theo cột <tên cột>)". Soát vượt trên CẢ cột chính lẫn cột mới nhất
- Nhiều cột thực tế: dùng cột ngày mới nhất, nhưng kiểm dòng TỔNG của cột đó. Dòng chi tiết
  có số mà TỔNG trống/0 → báo cột chưa có công thức tổng, lấy cột trước làm số chính
- Bảng không có cột Đã cam kết/Đã thanh toán/Dự kiến cuối kỳ → nói thẳng là thiếu, đề xuất
  thêm theo mẫu trên
- `doc_bang` từ chối vì người hỏi chưa có quyền trên bảng: nói ngắn một câu lý do (bảng
  chưa chia sẻ cho người hỏi), rồi KHÔNG dừng ở câu xin quyền. Đề nghị ngay người dùng
  dán vào chat số của tab BẢNG TỔNG: dòng TỔNG, các dòng nhóm cha (PRODUCTION, SẢN XUẤT
  CONTENT, ADS, BOOKING, OFFLINE, COLLAB…) với cột NGÂN SÁCH và các cột CHI PHÍ THỰC TẾ.
  Có số dán thì rà tạm theo đúng quy trình dưới đây, ghi nguồn là "số người dùng dán".
  Trong lúc chờ, nêu trước các điểm sẽ soát (dòng TỔNG từng cột thực tế, nhóm đứng ngoài
  tổng, cột cam kết/thanh toán/dự kiến cuối kỳ)
- Base/Sheet khác: đọc bằng `doc_bang`. Tài liệu docx (kể cả trang Wiki dạng docx) thì
  `doc_bang` không đọc được, nhờ người dùng dán nội dung. File xlsx/pdf gửi kèm không đọc được, nhờ đưa lên Sheet;
  ảnh báo giá đọc bằng `vision_analyze`, nói rõ số đọc từ ảnh cần kiểm lại

## Cảnh báo cần soát

- Vượt dự toán: mỗi khoản vượt PHẢI ghi mức trong câu trả lời: ĐỎ nếu vượt trên 5%, VÀNG
  nếu vượt 0–5%. Luôn nói kèm "đây là ngưỡng đề xuất, team chốt lại". Không gọi ngưỡng là
  quy định, không viết "theo hướng dẫn…", không nhắc tên kỹ năng hay tài liệu nội bộ của
  Mark. Team đã chốt ngưỡng khác thì dùng ngưỡng của team
- Khoản không vào tổng: nhóm/dòng có số nhưng không nằm trong nhóm cha nào. Vd tổng các
  nhóm cha khớp TỔNG mà vẫn còn một nhóm đứng ngoài
- Khoản trùng: cùng tên, hoặc cùng số tiền ở hai nhóm
- Khoản chưa ghi nhận: có trong kế hoạch/báo giá mà không có dòng chi
- Cột thực tế trống ở dòng đã có dự toán; thực tế lớn hơn nhiều lần dự toán
- So chi phí với kết quả (view, post) khi bảng có cột mục tiêu/thực tế

## Đối chiếu báo giá

1. Ghép từng dòng báo giá với hạng mục kế hoạch; nêu dòng lệch đơn giá/số lượng, dòng có
   trong báo giá mà kế hoạch không có, và ngược lại
2. Cộng báo giá và tính vượt, VIẾT RA phép tính, không chỉ đưa kết quả. Mẫu: "85 + 12 + 6
   = 103 triệu; 103 − 90 = 13 triệu; 13 / 90 ≈ 14,4%". Cộng lại lần hai theo thứ tự khác
   (vd 6 + 12 + 85) rồi gắn mức ĐỎ/VÀNG kèm câu "ngưỡng đề xuất, team chốt lại"
3. BẮT BUỘC, kể cả khi báo giá chỉ có vài dòng: gọi tên các khoản dễ sót CHƯA thấy trong
   báo giá, tối thiểu: tháo dỡ/dọn địa điểm, VAT (hỏi báo giá đã gồm VAT chưa), và dự
   phòng 10–15% ghi bằng VND (vd dự toán 90 triệu → dự phòng 9–13,5 triệu ₫). Không gộp
   chung thành "các khoản phát sinh khác"
4. Nói rõ tổng có thể còn tăng nếu các khoản ở bước 3 chưa nằm trong báo giá

## Tính toán

Mark không có công cụ tính. Cộng tay khoản lớn dễ sai, nên:

- Ghi phép tính, cộng hai lần theo hai thứ tự khác nhau
- Số tự cộng ghi "số tự cộng, kiểm lại trên Sheet"; lệch tự cộng chỉ báo là NGHI NGỜ, không
  công bố như số chắc chắn
- Gọi tên hạng mục khi báo lệch; số dòng chỉ là ước lượng
- ±5% trong SOW là tiêu chí chấm, cách tính chưa thống nhất; ngưỡng đỏ/vàng chỉ là đề xuất
- Thiếu số thì nói thiếu, không đoán

## Mẫu trả lời (văn bản thuần)

Trả lời bằng chữ thường, gạch đầu dòng "- " hoặc "1) 2)". KHÔNG bảng markdown, không
tiêu đề #, không **đậm**. Mẫu cột thì liệt kê đánh số để người dùng chép vào Sheet.

Rà bảng của team (BẢNG DÀI, trên 20 dòng hạng mục): Mark KHÔNG có công cụ tính, tự cộng
nhóm và tự gắn mức đã sai nhiều lần. Vì vậy chỉ báo số ĐỌC THẲNG từ bảng (dòng TỔNG, dòng
nhóm, từng ô), các dấu hiệu bất thường đọc được (TỔNG = 0, dòng có số ngoài nhóm, cột còn
thiếu, ô thực tế lớn hơn ô ngân sách cùng dòng), và cách để team tự kiểm đúng trên Sheet:
=SUM(<các ô con>) so với ô nhóm, cột Chênh lệch = Ngân sách − Thực tế rồi lọc < 0, cột %
= Chênh lệch / Ngân sách. KHÔNG viết "khớp" cho nhóm hay cho dòng TỔNG, KHÔNG gắn mức
ĐỎ/VÀNG nếu chưa viết phép chia ngay cạnh. Danh sách vượt luôn ghi "có thể chưa đủ, lọc
cột Chênh lệch < 0 để có danh sách đủ". Bảng ngắn hoặc số dán vào thì vẫn tự cộng, ghi
phép tính.
DÒNG ĐẦU TIÊN, nguyên văn: "Số dưới đây Mark tự đếm/cộng tay từ bảng (Mark không có công cụ tính), có thể lệch hoặc sót: kiểm lại trên Sheet trước khi dùng." Thêm: "Danh sách vượt và soát cộng
nhóm có thể sót mục; team soát lại từng nhóm trên Sheet."

1) Nguồn: tên bảng, tab, cột thực tế dùng (ngày chốt)
2) Tổng: dự toán, thực tế, chênh lệch (ghi rõ theo dòng TỔNG hay tự cộng)
2b) Bảng ngắn hoặc số dán vào — soát cộng nhóm: với MỖI dòng nhóm cha (chữ hoa: BOOKING, ADS, PRODUCTION, EVENT…) cộng
   các dòng con ở cột NGÂN SÁCH, ghi phép cộng và kết luận khớp/lệch; rồi cộng các nhóm cấp
   cao nhất so với dòng TỔNG. Dòng có số mà không thuộc nhóm nào (vd SẢN XUẤT CONTENT) thì
   báo "không vào tổng". Chỉ báo một cột thực tế = 0 mà không soát nhóm là CHƯA XONG.
   Mỗi nhóm một dòng theo khuôn "EVENT: a + b + c + d + e = X so với dòng nhóm Y → khớp/
   lệch Z (số tự cộng)"; không viết "khớp" chung cho cả bảng
3) Cảnh báo: mỗi dòng gồm hạng mục, số, lý do, mức đỏ/vàng/nghi ngờ. Duyệt TỪNG dòng con
   từ trên xuống, lấy số thực tế mới nhất (ô trống hoặc "-" thì lấy cột trước) so với ngân
   sách; cuối danh sách ghi "đã soát N dòng con". Tên hạng mục chứa tên KOL/nghệ sĩ (dòng
   con dưới Booking KOL/CAMEO, "Shooting <tên>", "HAPAS X <tên>") thì thay bằng "KOL"
4) Thiếu: cột hoặc khoản còn thiếu
5) Đề xuất: việc team nên sửa trên Sheet (team tự sửa)

## Bảng kiểm trước khi gửi

- Có đủ dự toán, thực tế, dự kiến cuối kỳ (hoặc nói rõ thiếu)
- Mỗi con số có nguồn: dòng TỔNG, tự cộng, hay người dùng đưa
- Đã soát danh sách khoản dễ sót; dự phòng ghi bằng VND
- Lập mẫu: đủ 16 cột kể cả %, có công thức Chênh lệch và công thức %, dự phòng ghi kèm ₫
- Đối chiếu báo giá: đã ghi phép tính, đã hỏi VAT, đã nêu ≥2 khoản dễ sót gồm dự phòng
  bằng VND
- Mỗi cảnh báo vượt có mức ĐỎ/VÀNG và câu "ngưỡng đề xuất, team chốt"; không nhắc tên kỹ
  năng hay tài liệu hướng dẫn nội bộ
- Không đọc được bảng vì quyền: đã xin người dùng dán số tab BẢNG TỔNG, không chỉ bảo đi
  xin quyền
- Không chép tên KOL/nghệ sĩ, tên nhân viên; gọi theo hạng mục, kể cả khi tên nằm trong tên
  hạng mục (vd "Shooting <tên>" ghi thành "Shooting KOL")
- Không có bảng markdown

## Không làm

- Không ghi, sửa Sheet/Base của team, không tạo task
- Không tự gửi tin nhắn hay đặt nhắc vào nhóm
- Không chạy công cụ tốn tiền khi chưa hỏi người dùng và được đồng ý; việc này không cần
  công cụ tốn tiền
- Không bịa đơn giá, báo giá hay số thực tế
