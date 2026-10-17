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
  thể dạng "1,070,000,000 ₫": đưa nguyên văn vào `dem_bang` (`du_lieu`), công cụ tự đọc;
  đưa vào `tinh` thì viết số trơn (1070000000). "-" là không áp dụng
- Không thấy công thức. Cấp cha/con suy từ tên dòng (nhóm cha viết hoa), kiểm bằng
  `dem_bang` (mục "Tính toán")
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
- Base/Sheet khác: đọc bằng `doc_bang`. Tài liệu docx (kể cả trang Wiki dạng docx, vd
  master plan) đọc bằng `doc_tai_lieu`; số trong đó cần cộng thì đưa vào `dem_bang` với
  `du_lieu` hoặc `tinh`, không tự cộng. File xlsx/pdf gửi kèm không đọc được, nhờ đưa lên Sheet;
  ảnh báo giá đọc bằng `vision_analyze`, nói rõ số đọc từ ảnh cần kiểm lại

## Bài học chiến dịch cũ

- Lập mẫu hay rà ngân sách: có công cụ `nho_bai_hoc` thì tra bài học cũ của team về
  khoản hay vượt (booking, sản xuất, phát sinh). Dẫn lại là BÀI HỌC CŨ kèm người ghi,
  ngày đo, link nguồn; không dùng bài học thay báo giá, đơn giá, khuyến mãi hay quyền hạn
  hiện hành
- Chênh lệch đã chốt, có số và link Sheet thì có thể đề nghị lưu thành bài học: đọc lại,
  hỏi "Lưu bài học này nhé?" và chỉ gọi `ghi_bai_hoc` khi người dùng đồng ý ở tin nhắn
  sau (xem kỹ năng "Ghi và nhớ bài học chiến dịch")

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
2. Cộng báo giá và tính vượt bằng công cụ `tinh` (KHÔNG tự cộng/chia, kể cả 3 dòng), một
   lần gọi, vd `phep_tinh` = {"tong": "85000000 + 12000000 + 6000000", "vuot":
   "tong - 90000000", "tyle": "ty_le(vuot; 90000000)", "dp10":
   "90000000 * 10%", "dp15": "90000000 * 15%"}. Chép NGUYÊN `cau_tinh` để người đọc
   thấy phép tính, vd "85.000.000 + 12.000.000 + 6.000.000 = 103.000.000; 103.000.000 −
   90.000.000 = 13.000.000; 13.000.000 ÷ 90.000.000 × 100 ≈ 14,4%". Rồi gắn mức ĐỎ/VÀNG
   kèm câu "ngưỡng đề xuất, team chốt lại". Báo giá dán dạng bảng nhiều dòng thì cộng bằng
   `dem_bang` với `du_lieu` = nguyên văn phần dán, rồi lấy tổng đó vào `tinh`
3. BẮT BUỘC, kể cả khi báo giá chỉ có vài dòng: gọi tên các khoản dễ sót CHƯA thấy trong
   báo giá, tối thiểu: tháo dỡ/dọn địa điểm, VAT (hỏi báo giá đã gồm VAT chưa), và dự
   phòng 10–15% ghi bằng VND lấy từ `cau_tinh` (vd dự toán 90 triệu → dự phòng 9–13,5
   triệu ₫). Không gộp chung thành "các khoản phát sinh khác"
4. Nói rõ tổng có thể còn tăng nếu các khoản ở bước 3 chưa nằm trong báo giá

## Tính toán

Cộng trên Sheet/Base của team: dùng `dem_bang` với `cong` = cột cần cộng (code cộng, đọc
được "1,070,000,000 ₫", "1.100.000đ", "3 triệu"). Chép NGUYÊN tổng trong `cau_so`, không
tự cộng lại, và nói rõ số đó là "công cụ cộng" (khác số "theo dòng TỔNG").

- Bảng ngân sách nhiều tầng (dòng nhóm = tổng dòng con, có dòng TỔNG, dòng Chênh lệch):
  cộng CẢ cột là cộng trùng. Dùng `dong` = số dòng thật trên Sheet:
  1) soát một nhóm: `cong` cột NGÂN SÁCH, `dong` = các dòng con của nhóm (vd
     PRODUCTION ở dòng 22, con ở "23-25") rồi so với ô của dòng nhóm
  2) soát dòng TỔNG: `dong` = các dòng nhóm cấp cao nhất (vd "4, 17, 22, 28, 43") rồi so
     với dòng TỔNG; nhóm nào có số mà không nằm trong các dòng đó là "không vào tổng"
  3) cột thực tế mới nhất mà dòng TỔNG trống/0: cộng cả cột chỉ đúng khi các dòng nhóm
     của cột đó cũng trống/0 — kiểm khi đọc, rồi ghi "công cụ cộng các dòng chi tiết"
- `cau_so` có CẢNH BÁO dòng TỔNG trong vùng cộng thì gọi lại với `dong` để loại dòng đó.
  Ô không phải số ("-", chữ) công cụ đã báo riêng: nói ra, không coi là 0
- Tỷ lệ vượt (%), chênh lệch, dự phòng, "tổng đã cộng so với ô nhóm lệch bao nhiêu": gọi
  `tinh` (vd "ty_le(13000000; 90000000)", "chenh_lech(tong; nhom)") rồi chép
  NGUYÊN `cau_tinh` — phép tính hiện ngay cạnh, kết quả do công cụ tính
- Số người dùng dán vào chat (không có Sheet): bảng hay danh sách số → `dem_bang` với
  `du_lieu` = nguyên văn phần dán (`cong` = cột số; dòng "Hạng mục: số" công cụ tự cộng
  cột B); vài số rời → `tinh`. Ghi nguồn "số người dùng dán, công cụ cộng". Không cộng
  tay, không "cộng hai lần theo hai thứ tự"
- `dem_bang`/`tinh` bị tắt hoặc lỗi (không phải lỗi quyền): KHÔNG tự cộng bảng dài. Chỉ
  báo số đọc thẳng (dòng TỔNG, dòng nhóm, từng ô) và cách để team tự kiểm trên Sheet:
  =SUM(<các ô con>) so với ô nhóm, cột Chênh lệch = Ngân sách − Thực tế rồi lọc < 0. Phép
  ngắn bắt buộc phải có thì viết phép tính và ghi "số tự tính, chưa qua công cụ — kiểm lại"
- Gọi tên hạng mục khi báo lệch
- ±5% trong SOW là tiêu chí chấm, cách tính chưa thống nhất; ngưỡng đỏ/vàng chỉ là đề xuất
- Thiếu số thì nói thiếu, không đoán

## Mẫu trả lời (văn bản thuần)

Trả lời bằng chữ thường, gạch đầu dòng "- " hoặc "1) 2)". KHÔNG bảng markdown, không
tiêu đề #, không **đậm**. Mẫu cột thì liệt kê đánh số để người dùng chép vào Sheet.

Rà bảng của team: mọi tổng tự tính lấy từ `dem_bang` (mục "Tính toán"), số còn lại đọc
thẳng từ bảng (dòng TỔNG, dòng nhóm, từng ô). Nêu các dấu hiệu bất thường đọc được (TỔNG
= 0, dòng có số ngoài nhóm, cột còn thiếu, ô thực tế lớn hơn ô ngân sách cùng dòng). Chỉ
viết "khớp" cho một nhóm hay dòng TỔNG khi đã có tổng của `dem_bang` đặt cạnh ô đó. KHÔNG
gắn mức ĐỎ/VÀNG nếu chưa có phép chia của `tinh` (chép từ `cau_tinh`) ngay cạnh. Danh sách
vượt luôn ghi "có thể chưa đủ, lọc cột Chênh lệch < 0 để có danh sách đủ".
DÒNG ĐẦU TIÊN ghi nguồn số: "Tổng và tỷ lệ do công cụ tính, số còn lại đọc thẳng từ bảng;
kiểm lại trên Sheet trước khi dùng." Số người dùng dán thì ghi "số người dùng dán, công cụ
cộng". Chỉ khi công cụ không chạy mới có "số tự tính, chưa qua công cụ". Thêm: "Danh sách
vượt có thể sót mục; team soát lại từng nhóm trên Sheet."

1) Nguồn: tên bảng, tab, cột thực tế dùng (ngày chốt)
2) Tổng: dự toán, thực tế, chênh lệch (ghi rõ theo dòng TỔNG hay công cụ cộng)
2b) Soát cộng nhóm: với MỖI dòng nhóm cha (chữ hoa: BOOKING, ADS, PRODUCTION, EVENT…)
   cộng các dòng con ở cột NGÂN SÁCH bằng `dem_bang` (`dong` = dòng con), rồi cộng các
   nhóm cấp cao nhất so với dòng TỔNG. Dòng có số mà không thuộc nhóm nào (vd SẢN XUẤT
   CONTENT) thì báo "không vào tổng". Chỉ báo một cột thực tế = 0 mà không soát nhóm là
   CHƯA XONG. Mỗi nhóm một dòng theo khuôn "PRODUCTION (dòng 23–25): X so với dòng nhóm Y
   → khớp/lệch Z (công cụ cộng)", Z lấy từ `tinh`; số dán vào chat thì cộng bằng
   `dem_bang` với `du_lieu` (hoặc `tinh` với tong(a; b; c)) và chép phép cộng từ công cụ.
   Không viết "khớp" chung cho cả bảng
3) Cảnh báo: mỗi dòng gồm hạng mục, số, lý do, mức đỏ/vàng/nghi ngờ. Duyệt TỪNG dòng con
   từ trên xuống, lấy số thực tế mới nhất (ô trống hoặc "-" thì lấy cột trước) so với ngân
   sách; cuối danh sách ghi "đã soát N dòng con". Tên hạng mục chứa tên KOL/nghệ sĩ (dòng
   con dưới Booking KOL/CAMEO, "Shooting <tên>", "HAPAS X <tên>") thì thay bằng "KOL"
4) Thiếu: cột hoặc khoản còn thiếu
5) Đề xuất: việc team nên sửa trên Sheet (team tự sửa)

## Bảng kiểm trước khi gửi

- Có đủ dự toán, thực tế, dự kiến cuối kỳ (hoặc nói rõ thiếu)
- Mỗi con số có nguồn: dòng TỔNG, công cụ cộng (`dem_bang`), công cụ tính (`tinh`), hay
  người dùng đưa; không số nào tự tính tay khi công cụ đang chạy
- Đã soát danh sách khoản dễ sót; dự phòng ghi bằng VND
- Lập mẫu: đủ 16 cột kể cả %, có công thức Chênh lệch và công thức %, dự phòng ghi kèm ₫
- Đối chiếu báo giá: đã gọi `tinh` và chép phép tính trong `cau_tinh`, đã hỏi VAT, đã nêu
  ≥2 khoản dễ sót gồm dự phòng bằng VND
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
