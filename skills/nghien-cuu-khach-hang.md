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

## Đọc và đếm dữ liệu: `dem_bang` cho SỐ, `doc_bang` cho NỘI DUNG

Mọi con số (n, số người chọn, %, so nhóm, dòng trùng) lấy từ `dem_bang`: code đếm trên
MỌI dòng của tab, không giới hạn số dòng. `doc_bang` dùng để đọc nội dung (câu trả lời mở,
trích dẫn, rà từng dòng). Không tự đếm trên bảng `doc_bang` trả về.

Mẫu của team: Sheet "TỔNG HỢP KẾT QUẢ KHẢO SÁT KH TẠI CH HAPAS/MALL TỈNH"
https://o4pvcegwn6b.sg.larksuite.com/sheets/ALdIsJOzGhij5htSKULlrcv8gBe, 2 tab: Khách
store HAPAS (?sheet=vc76ip) và Khách mall tỉnh (?sheet=AQ9ihe). Thêm ?sheet=<id> để chỉ
đọc một tab. Chỉ nêu tên và link, không chép dữ liệu khách ra ngoài.

Thấy link Sheet khảo sát kèm việc tổng hợp thì làm theo kỹ năng này từ đầu, rồi mới gọi
công cụ.

- `dem_bang` hoặc `doc_bang` báo không đọc được vì quyền (người hỏi chưa có quyền xem, bot
  chưa được chia sẻ): báo đúng lý do công cụ trả về, xin người dùng dán nội dung vào chat
  hoặc chia sẻ quyền xem Sheet rồi hỏi lại. KHÔNG suy đoán kết quả, không đưa số hay
  insight nào khi chưa đọc được dữ liệu

Cách gọi `dem_bang` cho khảo sát:
- Một tab một lần gọi (link có ?sheet=<id>, hoặc `tab` = tên tab). Hỏi cả Sheet thì gọi
  từng tab, nêu n TỪNG tab
- `cot` = mã câu cần trả lời, vd ["B4", "B5", "C1", "C2", "C4"]; bỏ trống = mọi câu
- So nhóm đã mua/chưa mua: `nhom_theo` = "C2" (câu mua hay không); theo tỉnh: cột tỉnh
- Dòng tiêu đề: công cụ tự nhận (khảo sát team có dòng 1 là tên PHẦN, câu hỏi ở dòng 2)
  và báo lại `dong_tieu_de_da_dung`. Nhận sai thì gọi lại với `dong_tieu_de`
- Ô nhiều lựa chọn = nhiều DÒNG trong ô, công cụ đã tách. KHÔNG bật `tach_dau_phay` cho
  khảo sát của team: "Có, đã mua/sẽ mua ngay hôm nay" là MỘT đáp án
- Gộp biến thể ("HN" = "Hà Nội", "8 - 15 triệu" = "8-15 triệu", đáp án bị rút gọn về đáp
  án đầy đủ): gọi lại với `gop`, vd [["Cần thời gian suy nghĩ thêm", "Cần thời gian suy
  nghĩ thêm/tham khảo thêm nơi khác"]]. Công cụ tính mỗi người một lần. Không tự cộng hai
  số. Ghi rõ đã gộp gì
- Đáp án "khác" tự gõ (vd "Vợ thích") nằm trong danh sách đáp án với số của nó: gom vào
  nhóm Khác khi trình bày, liệt kê nguyên văn
- Bảng không có cột cửa hàng thì tab chính là nguồn (store hay mall tỉnh)
- `dem_bang` báo `bi_cat` hoặc `doc_bang` có "(đọc X)": mới đọc một phần bảng, nói rõ
  số chỉ tính trên phần đã đọc, không suy ra cho cả bảng
- Bảng khảo sát DÁN vào chat (chép từ Sheet/Excel, bảng markdown, CSV): gọi `dem_bang`
  với `du_lieu` = NGUYÊN VĂN phần dán (không sửa, không bỏ dòng), các tham số `cot`,
  `nhom_theo`, `gop` y như với Sheet. Chép NGUYÊN `cau_so` (công cụ ghi nguồn "dữ liệu dán
  trong chat"); ô nhiều lựa chọn xuống dòng trong ô hoặc tách bằng ";" công cụ tự tách
- Ghi chép phỏng vấn dán vào chat (văn xuôi, không phải bảng): ĐỌC và gắn mã là việc của
  Mark — chuyển thành mỗi khách MỘT dòng, các cột cách nhau bằng tab: mã khách, rồi mỗi câu
  hỏi một cột chứa mã đã gắn (nhiều mã trong một ô thì tách bằng ";"). Đưa bảng đó vào
  `dem_bang` (`du_lieu`) để công cụ ĐẾM, chép `cau_so`; không tự đếm, không "đếm hai lần".
  Nói rõ mã là Mark gắn khi đọc, số là công cụ đếm. Gom các phản hồi cùng ý thành một mã
- Người dùng nói sẽ dán ghi chép nhưng chưa dán: xin dán, và NGAY trong câu trả lời đó nói
  trước cách làm: mỗi khách một mục, gắn mã nhu cầu / rào cản / động lực mua / tiêu chí lựa
  chọn, công cụ đếm trên n người, trích dẫn ẩn danh. n dưới 10 (vd "8 khách") thì báo luôn kết quả
  chỉ để tham khảo, không kết luận. Gộp một lần các câu ở mục "Cần hỏi trước" (vấn đề cần
  trả lời, nhóm cần so) vào cùng câu trả lời
- Docx/wiki tài liệu `doc_bang` không đọc được; file xlsx/csv gửi kèm cũng không. Nhờ
  người dùng đưa lên Lark Sheet hoặc dán nội dung

## Đếm và so nhóm

- SỐ CHỈ LẤY TỪ `dem_bang`: chép NGUYÊN câu số trong `cau_so` (n, số người, %), không
  đếm lại, không làm tròn khác, không cộng % của câu chọn nhiều. Bảng dài hay ngắn đều
  vậy, kể cả tab 52 dòng
- Nêu n từng tab đúng như `dem_bang` báo (vd "Khách store HAPAS: n=52; Khách mall tỉnh:
  n=16") và tab nào đã dùng
- Mẫu số = người được hỏi câu đó: `cau_so` đã ghi "x/n người trả lời" và % tính trên số
  người trả lời. Câu rẽ nhánh (lý do chưa mua) thì mẫu số là nhóm đủ điều kiện: lấy ở
  dòng nhóm của `nhom_theo` (vd nhóm "Không, chưa mua" n=7). Ô trống trong nhóm đủ điều
  kiện báo riêng
- Câu nhiều lựa chọn: tổng % có thể quá 100, nói rõ (công cụ đã ghi sẵn)
- So nhóm đã mua / chưa mua, store / mall tỉnh, theo tỉnh: lấy số từng nhóm trong
  `cau_so`. Nhóm dưới 10 người ghi "chỉ tham khảo", không kết luận (công cụ đã đánh dấu)
- Dòng trùng: chép kết quả "Dòng trùng" của `dem_bang` (nêu STT, KHÔNG tự xoá, có thể là
  hai khách giống nhau). Không tự kết luận có/không dòng trùng khi chưa gọi công cụ
- Câu trả lời MỞ (công cụ báo "câu trả lời MỞ", không có số): đọc bằng `doc_bang`, mã hoá
  theo Bộ mã ở trên. Đây là NHẬN ĐỊNH CỦA MARK khi đọc, không phải số đếm: nói rõ "Mark
  đọc và gom ý", kèm 2–3 trích dẫn ẩn danh, không gắn % cho các ý tự gom
- `dem_bang` bị tắt hoặc báo lỗi không phải lỗi quyền: nói rõ chưa đếm được bằng công cụ,
  KHÔNG tự đếm bảng dài. Thay vào đó đưa n đọc được, công thức để team đếm đúng trên
  Sheet (=COUNTIF(<cột B5>;"*Thiết kế*") cho câu nhiều lựa chọn, =COUNTIF(<cột C2>;"Có")
  rồi chia cho n, so nhóm =COUNTIFS(<cột C2>;"Chưa";<cột C4>;"*<đáp án>*")) và nhận xét
  định tính ghi "đọc lướt, chưa đếm"

## Chân dung khách

- Đối chiếu chéo trước khi gửi: số chưa mua ở câu mua hay không phải bằng số người trả lời
  câu lý do chưa mua (cả hai đều có trong `cau_so`); lệch thì nêu lệch, không tự sửa số
- Mỗi gạch thuộc tính có số/n lấy từ `cau_so`
- Câu sàng lọc (vd tuổi, mục đích mua) KHÔNG thành gạch thuộc tính; chỉ đưa vào dòng "Nhóm
  mẫu còn thiếu"
- Sheet có nhiều tab (vd store 52 + mall tỉnh 16): nêu cỡ mẫu TỪNG tab (gọi `dem_bang`
  cho từng tab) và nói tab nào đã dùng; mỗi thuộc tính kèm số/n của đúng tab đó
- Luôn có dòng "Nhóm mẫu còn thiếu": nêu điều kiện sàng lọc của phiếu (vd phiếu chỉ hỏi nam
  mua quà cho nữ thì thiếu khách nữ tự mua, khách online, ngoài 22–40). Thuộc tính do cách
  chọn mẫu mà ra thì KHÔNG đưa vào chân dung như đặc điểm khách

## Báo chất lượng dữ liệu

Dòng trùng toàn bộ (lấy từ `dem_bang`, nêu STT, KHÔNG tự xoá, có thể là hai khách giống
nhau), thiếu cột cửa
hàng/ngày/người phỏng vấn, câu có 100% một giá trị, thang không chuẩn, câu bị đánh "bỏ" mà
vẫn có dữ liệu, câu xếp hạng không có hạng.

## Mẫu trả lời (văn bản thuần)

Trả lời bằng chữ thường, gạch đầu dòng "- " hoặc "1) 2)". KHÔNG bảng markdown, không tiêu
đề #, không **đậm**.

Số lấy từ `dem_bang` thì DÒNG ĐẦU TIÊN ghi nguồn số, vd "Số dưới đây do công cụ đếm trên
toàn bộ 52 dòng của tab Khách store HAPAS (tiêu đề ở dòng 2)." Phần mã hoá câu mở ghi rõ
là Mark đọc và gom ý. Chỉ khi `dem_bang` không chạy được mới mở đầu bằng "Mark chưa đếm
được bằng công cụ; dưới đây là nhận xét đọc lướt và công thức để team ra số."

1) Nguồn và mẫu: tên Sheet, tab, n; nêu cỡ mẫu TỪNG tab (vd Khách store n=52, Khách mall
   tỉnh n=16) và tab nào đã dùng, tab nào chưa; nhóm đủ điều kiện từng câu
2) Chất lượng dữ liệu, LUÔN đủ 3 dòng cố định: "Dòng trùng: STT … (hoặc: không có)";
   "Thiếu cột: …"; "Nhóm dưới 10 người: … chỉ tham khảo"
3) Kết quả từng câu: đáp án, số/n, % chép từ `cau_so`; câu mở: ý Mark gom được + trích dẫn
4) So nhóm: số từng nhóm từ `cau_so`, chênh lệch kèm cảnh báo nhóm nhỏ
5) Insight: sự thật quan sát, con số, trích dẫn ẩn danh, hàm ý cho nội dung hoặc cửa hàng,
   mức chắc chắn theo n
6) Nhóm mẫu còn thiếu và giả thuyết cần khảo sát thêm

## Bảng kiểm trước khi gửi

- Mỗi câu chọn có số/n chép NGUYÊN từ `cau_so` của `dem_bang` (không số nào tự đếm), có n
  từng tab, có kết quả dòng trùng; câu mở ghi rõ là Mark đọc. Đã báo thiếu cột cửa
  hàng/ngày/người phỏng vấn; chân dung có dòng "Nhóm mẫu còn thiếu"
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
  đồng ý. Việc này chỉ cần `dem_bang`, `doc_bang` hoặc nội dung người dùng dán
