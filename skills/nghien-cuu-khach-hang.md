# Nghiên cứu khách hàng và hành vi mua

Soạn công cụ nghiên cứu (bảng hỏi, hướng dẫn phỏng vấn, phiếu quan sát) và tổng hợp kết
quả khảo sát cửa hàng, ghi chép phỏng vấn, phản hồi khách thành báo cáo nhu cầu, rào cản,
động lực mua và tiêu chí lựa chọn có dẫn chứng. Không dùng để bóc bình luận mạng xã hội
(dùng kỹ năng Deep-dive bình luận), đo sentiment (Phân tích crisis, sentiment và share of
voice) hay lên kế hoạch chiến dịch (Lập kế hoạch chiến dịch quảng cáo).

## Cần hỏi trước, gộp một lần

1. Vấn đề cần trả lời: khách chưa hiểu sản phẩm, chưa vào cửa hàng, hay vào rồi mà chưa mua
2. Nguồn dữ liệu: link Lark Sheet/Base, hay nội dung dán vào chat
3. Nhóm cần so: đã mua / chưa mua, cửa hàng / mall tỉnh, tỉnh, kênh mua, dịp mua

## Soạn bảng hỏi

Khung team đã dùng: A sàng lọc, B trigger và hành vi tại điểm bán, C pain point và quyết
định mua, D nhân khẩu học.

Luật sàng lọc và rẽ nhánh (áp dụng cả khi người dùng chỉ nói "khách mua túi"):

- Câu sàng lọc ở A chỉ lọc ĐỐI TƯỢNG: giới, tự chọn hoặc mua cho bản thân hay để tặng, đã
  vào cửa hàng. KHÔNG lọc theo đã mua hay chưa mua
- Giới tính: người phỏng vấn tự quan sát và ghi ("Giới (người phỏng vấn ghi): ( ) Nữ ( )
  Nam"), KHÔNG hỏi thẳng khách kiểu "Chị có phải là nữ không?"
- Phần C luôn có câu "Hôm nay chị có mua không?" rẽ nhánh: Có → lý do mua, động lực mua;
  Chưa → lý do chưa mua, rào cản. Người chưa mua vẫn đi tiếp đến hết phần D
- Câu rẽ nhánh ghi bước nhảy cho CẢ HAI nhánh, kể cả điểm nhập lại. Vd: "Có → câu 13; Chưa
  → câu 14", và ở cuối câu 13 ghi "xong câu 13 → sang câu 15" để người mua không bị hỏi
  câu của người chưa mua
- Cấm ghi "Không → kết thúc phỏng vấn" ở câu mua hay không. Chỉ được kết thúc sớm khi khách
  trượt câu sàng lọc đối tượng
- Câu sàng lọc chỉ để lọc, không dùng làm biến phân tích

Bảng hỏi trả đủ 4 phần, đúng thứ tự, thiếu phần nào là chưa xong:

1) Đầu phiếu: các ô điền "Mã khách: ____", "Cửa hàng/mall: ____", "Ngày: ____", "Giờ:
   ____", "Người phỏng vấn: ____". Phải là ô trên phiếu, không viết thành lời dặn "nên
   ghi". Mã khách theo dạng cửa hàng + ngày + số thứ tự, không dùng tên khách
2) Bảng hỏi A đến D, đánh số liên tục. Câu xếp hạng có ô ghi hạng cạnh từng ý (vd "Thiết
   kế: hạng __"). Ý "khác" có chỗ tự gõ, ghi ở cột riêng khi nhập Sheet
3) Hướng dẫn phỏng vấn: lời mở (giới thiệu, mục đích, thời lượng), xin phép trước khi ghi
   âm, đọc câu hỏi nguyên văn và không gợi ý đáp án, hỏi thêm "vì sao" với câu trả lời
   ngắn, cách đặt mã khách theo mã cửa hàng + ngày + số thứ tự trong ngày (vd CH01-0610-03)
   và ghi cùng mã đó lên đầu phiếu hỏi lẫn phiếu quan sát cho khớp nhau
4) PHIẾU QUAN SÁT riêng, cùng mã khách, có các ô: mẫu khách xem hoặc cầm lên, mẫu cầm lên
   rồi đặt xuống, câu khách hỏi nhân viên, thời gian ở cửa hàng (vào lúc, ra lúc), có mua
   không (Có / Chưa, mẫu đã mua)

Bắt buộc thêm:

- Thang thu nhập một bộ mã, không chồng lấn (vd dưới 8 triệu / 8 đến dưới 15 / 15 đến dưới
  25 / từ 25 triệu / không trả lời)
- Không hỏi tên, SĐT, email
- Trình bày phiếu bằng văn bản thuần: đánh số câu, lựa chọn xuống dòng bằng "- " hoặc
  "( )". KHÔNG bảng markdown, không tiêu đề #

## Bộ mã

- Nhu cầu: khách cần gì (quà tặng, đi làm, đựng laptop)
- Rào cản: thứ cản mua (giá vượt ngân sách, phân vân mẫu, chưa rõ chất liệu, sợ người nhận
  không thích)
- Động lực mua: thứ đẩy mua ngay (mẫu đẹp, ưu đãi, nhân viên tư vấn, dịp lễ)
- Tiêu chí lựa chọn: thứ dùng để so (thiết kế, giá, thương hiệu, đóng gói quà)
- Khác / không rõ: không khớp nhóm nào thì để đây và liệt kê nguyên văn

## Đọc dữ liệu bằng `doc_bang`

Mẫu của team: Sheet "TỔNG HỢP KẾT QUẢ KHẢO SÁT KH TẠI CH HAPAS/MALL TỈNH"
https://o4pvcegwn6b.sg.larksuite.com/sheets/ALdIsJOzGhij5htSKULlrcv8gBe, 2 tab: Khách
store HAPAS (?sheet=vc76ip) và Khách mall tỉnh (?sheet=AQ9ihe). Thêm ?sheet=<id> để chỉ
đọc một tab. Chỉ nêu tên và link, không chép dữ liệu khách ra ngoài.

Thấy link Sheet khảo sát kèm việc tổng hợp thì làm theo kỹ năng này từ đầu, rồi mới gọi
`doc_bang`.

- `doc_bang` báo không đọc được vì quyền (người hỏi chưa có quyền xem, bot chưa được chia
  sẻ): báo đúng lý do công cụ trả về, xin người dùng dán nội dung vào chat hoặc chia sẻ quyền
  xem Sheet rồi hỏi lại. KHÔNG suy đoán kết quả, không đưa số hay insight nào khi chưa đọc
  được dữ liệu

- Dòng tiêu đề `doc_bang` trả về phần lớn trống hoặc là tên PHẦN thì câu hỏi thật nằm ở
  dòng kế tiếp. Khi đó "N dòng" `doc_bang` báo đã gồm dòng câu hỏi: n = N − 1
- Ô nhiều lựa chọn: `doc_bang` nối các dòng trong ô bằng ' / ' (có dấu cách hai bên). Tách
  ĐÚNG theo ' / '. Không tách theo dấu phẩy hay '/' liền chữ ("Vợ/người yêu" là MỘT đáp án)
- `doc_bang` ĐÃ trim đầu cuối mỗi ô, không cần trim lại. Ký tự "\|" trong ô là "|" gốc
- Gộp biến thể: "HN" = "Hà Nội", "8 - 15 triệu" = "8-15 triệu", đáp án bị rút gọn về đáp
  án đầy đủ. Ghi rõ đã gộp gì
- Đáp án "khác" tự gõ đưa về nhóm Khác, liệt kê nguyên văn
- Bảng không có cột cửa hàng thì tab chính là nguồn (store hay mall tỉnh)
- Tiêu đề `doc_bang` có "(đọc X)" nghĩa là mới đọc một phần bảng: nói rõ chỉ tổng hợp X
  dòng, không suy ra cho cả bảng
- Ghi chép phỏng vấn dán vào chat: chuyển thành mỗi khách một mục, mỗi câu hỏi một ý, gắn
  mã rồi mới đếm. Gom các phản hồi cùng ý thành một
- Người dùng nói sẽ dán ghi chép nhưng chưa dán: xin dán, và NGAY trong câu trả lời đó nói
  trước cách làm: mỗi khách một mục, gắn mã nhu cầu / rào cản / động lực mua / tiêu chí lựa
  chọn, đếm trên n người, trích dẫn ẩn danh. n dưới 10 (vd "8 khách") thì báo luôn kết quả
  chỉ để tham khảo, không kết luận. Gộp một lần các câu ở mục "Cần hỏi trước" (vấn đề cần
  trả lời, nhóm cần so) vào cùng câu trả lời
- Docx/wiki tài liệu `doc_bang` không đọc được; file xlsx/csv gửi kèm cũng không. Nhờ
  người dùng đưa lên Lark Sheet hoặc dán nội dung

## Đếm và so nhóm

- LUẬT CỨNG, BẢNG DÀI (trên 20 dòng phản hồi, vd tab khảo sát 52 dòng): Mark KHÔNG có công
  cụ đếm, đếm tay bảng dài đã sai nhiều lần. Vì vậy KHÔNG đưa số đếm tần suất, %, "không
  thấy dòng trùng" hay so nhóm bằng số tự đếm. Thay vào đó trả:
  1) n từng tab lấy từ số dòng doc_bang báo (vd "Khách store: 52 dòng; Khách mall tỉnh:
     16 dòng") và tab nào đã đọc;
  2) với MỖI câu chọn cần trả lời: tên cột và công thức để team đếm đúng trên Sheet, vd
     =COUNTIF(<cột B5>;"*Thiết kế*") cho câu nhiều lựa chọn, =COUNTIF(<cột C2>;"Có") rồi
     chia cho n; so nhóm thì =COUNTIFS(<cột C2>;"Chưa";<cột C4>;"*<đáp án>*");
  3) soát trùng: hướng dẫn =COUNTIFS trên các cột trả lời hoặc Dữ liệu → Xoá trùng lặp ở
     chế độ chỉ xem; không tự kết luận có hay không có dòng trùng;
  4) nhận xét định tính khi đọc lướt (đáp án nào hay gặp, rào cản nào lặp lại), mỗi câu
     ghi rõ "đọc lướt, chưa đếm"; không dùng số;
  5) nhóm mẫu còn thiếu và cột còn thiếu (cửa hàng, ngày, người phỏng vấn)
- Bảng ngắn (≤20 dòng) hoặc ghi chép dán vào: đếm và ghi số/n kèm %, đếm hai lần
- Mẫu số = người được hỏi câu đó; câu rẽ nhánh thì mẫu số là nhóm đủ điều kiện (lý do chưa
  mua chia cho số người chưa mua). Ô trống trong nhóm đủ điều kiện báo riêng
- Câu nhiều lựa chọn: tổng % có thể quá 100, nói rõ
- CHỈ cho bảng ngắn hoặc ghi chép dán vào: ghi phép đếm (vd 6/18), đếm hai lần trước khi
  báo; số đếm tay có thể lệch 1-2, luôn nhắc kiểm lại bằng bộ lọc trên Sheet. KHÔNG áp dụng
  cho bảng dài (xem LUẬT CỨNG ở trên)
- So nhóm đã mua / chưa mua, store / mall tỉnh, theo tỉnh. Nhóm dưới 10 người ghi "chỉ tham
  khảo", không kết luận

## Chân dung khách

- Bảng ngắn hoặc ghi chép dán vào — đối chiếu chéo trước khi gửi: số chưa mua ở câu sàng lọc phải bằng số người trả lời câu
  lý do chưa mua; lệch thì đếm lại
- Bảng ngắn: mỗi gạch thuộc tính có số/n. Bảng dài: thuộc tính ghi "đọc lướt, chưa đếm" kèm
  công thức COUNTIF để team ra số; không đưa số tự đếm
- Câu sàng lọc (vd tuổi, mục đích mua) KHÔNG thành gạch thuộc tính; chỉ đưa vào dòng "Nhóm
  mẫu còn thiếu"
- Sheet có nhiều tab (vd store 52 + mall tỉnh 16): nêu cỡ mẫu TỪNG tab và nói tab nào đã
  dùng. Mỗi thuộc tính trong chân dung kèm số/n
- Luôn có dòng "Nhóm mẫu còn thiếu": nêu điều kiện sàng lọc của phiếu (vd phiếu chỉ hỏi nam
  mua quà cho nữ thì thiếu khách nữ tự mua, khách online, ngoài 22–40). Thuộc tính do cách
  chọn mẫu mà ra thì KHÔNG đưa vào chân dung như đặc điểm khách

## Báo chất lượng dữ liệu

Dòng trùng toàn bộ (nêu STT, KHÔNG tự xoá, có thể là hai khách giống nhau), thiếu cột cửa
hàng/ngày/người phỏng vấn, câu có 100% một giá trị, thang không chuẩn, câu bị đánh "bỏ" mà
vẫn có dữ liệu, câu xếp hạng không có hạng.

## Mẫu trả lời (văn bản thuần)

Trả lời bằng chữ thường, gạch đầu dòng "- " hoặc "1) 2)". KHÔNG bảng markdown, không tiêu
đề #, không **đậm**.

Bảng dài: DÒNG ĐẦU TIÊN là "Bảng dài nên Mark không tự đếm (Mark không có công cụ tính, đếm tay dễ sai); dưới đây là nhận xét đọc lướt và công thức để team ra số chính xác." Bảng ngắn có số tự đếm: DÒNG ĐẦU TIÊN, nguyên văn: "Số dưới đây Mark tự đếm/cộng tay từ bảng (Mark không có công cụ tính), có thể lệch hoặc sót: kiểm lại trên Sheet trước khi dùng." Kèm cách
soát: lọc cột trên Sheet, hoặc COUNTIF(<cột>;"*<đáp án>*") với câu nhiều lựa chọn.

1) Nguồn và mẫu: tên Sheet, tab, n; nêu cỡ mẫu TỪNG tab (vd Khách store n=52, Khách mall
   tỉnh n=16) và tab nào đã dùng, tab nào chưa; nhóm đủ điều kiện từng câu
2) Chất lượng dữ liệu, LUÔN đủ 3 dòng cố định: "Dòng trùng: STT … (hoặc: không thấy)";
   "Thiếu cột: …"; "Nhóm dưới 10 người: … chỉ tham khảo"
3) Kết quả từng câu: bảng ngắn ghi đáp án, số/n, %; bảng dài ghi nhận xét đọc lướt + công
   thức COUNTIF cho câu đó
4) So nhóm: bảng ngắn ghi chênh lệch kèm cảnh báo nhóm nhỏ; bảng dài đưa công thức COUNTIFS
5) Insight: sự thật quan sát, con số, trích dẫn ẩn danh, hàm ý cho nội dung hoặc cửa hàng,
   mức chắc chắn theo n
6) Nhóm mẫu còn thiếu và giả thuyết cần khảo sát thêm
7) Nhắc: số đếm tay, kiểm lại trên Sheet

## Bảng kiểm trước khi gửi

- Bảng ngắn: mỗi câu chọn đã có số/n, đã soát dòng trùng. Bảng dài: KHÔNG có số tự đếm, mỗi
  câu có công thức, không kết luận có/không dòng trùng. Cả hai: đã báo thiếu
  cột cửa hàng/ngày/người phỏng vấn; chân dung có dòng "Nhóm mẫu còn thiếu"
- Bảng hỏi: đủ đầu phiếu có ô (mã khách, cửa hàng/mall, ngày, giờ, người phỏng vấn) + câu
  mua hay không rẽ nhánh Có/Chưa mua, ghi bước nhảy cả hai nhánh, không kết thúc khi chưa
  mua + giới do người phỏng vấn ghi + hướng dẫn phỏng vấn có cách đặt mã khách +
  phiếu quan sát + câu xếp hạng có ô hạng + thang thu nhập không chồng lấn + không hỏi tên,
  SĐT, email
- Mỗi nhu cầu / rào cản có con số hoặc trích dẫn từ dữ liệu
- Có đề xuất ứng dụng cho nội dung hoặc cửa hàng, gắn với insight
- Không có chân dung khách do AI tưởng tượng: chỉ dùng thuộc tính CÓ cột trong tab đang
  phân tích; tab không có cột nghề nghiệp thì không nói nghề nghiệp. Luôn nêu cỡ mẫu
- Mẫu số đúng với câu rẽ nhánh; nhóm nhỏ đã cảnh báo
- Trích dẫn đã bỏ tên, SĐT; câu trả lời mở có tên KOL/KOC hay người cụ thể thì không nêu tên

## Không làm

- Không bịa số: thiếu dữ liệu thì nói thiếu, không đoán thay
- Không ghi/sửa Sheet hay Base của team, không xoá dòng trùng, không tạo task
- Không tự gửi tin nhắn hay nhắc vào nhóm
- Không chạy công cụ tốn tiền (`social_listen`, `social_deep_dive`, `soi_tai_khoan`,
  `soi_san`, `tiktok_top_ads`, `web_crawl`) khi chưa báo chi phí, hỏi người dùng và được
  đồng ý. Việc này chỉ cần `doc_bang` hoặc nội dung người dùng dán
