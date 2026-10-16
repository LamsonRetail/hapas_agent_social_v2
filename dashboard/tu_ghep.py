"""Từ ghép tiếng Việt cho mây từ khoá (`chi_so._tach_cum`) — tự soạn 16/10/2026, không chép từ
điển của bên thứ ba.

Vì sao cần: tiếng Việt viết cách từng ÂM TIẾT, một từ thường là hai âm tiết. Ghép hai âm tiết liền
nhau một cách máy móc thì cắt ngang ranh giới từ: "túi xách nữ aura" ra "xách nữ", "nữ aura";
"cười chảy nước mắt" ra "chảy nước"; "vui lòng kiểm tra tin nhắn" ra "lòng kiểm", "tra tin". Rà ảnh
chụp kho 16/10: mây "Tất cả" có 7/50 cụm cắt ngang kiểu này ("lòng kiểm", "tra tin", "nhắn tư", "gửi
tin", "nữ tuyệt", "điều tốt", "ơn mẹ"), mây External channel có "xách nữ", "nữ aura", "túi màu",
"hề diễn", "chảy nước". Tách từ bằng danh sách từ ghép + so khớp dài nhất (`chi_so._tach_don_vi`)
thì các cặp đó không còn, và "túi xách", "nước mắt" hiện đúng một từ.

Đã cân nhắc và KHÔNG dùng (đo trên ảnh chụp kho 16/10, 2.289 dòng, Python 3.12):
  * pyvi 0.1.1 (MIT): kéo numpy + scipy + scikit-learn (219 MB), nạp 2 giây, không bảo trì từ 2021;
    tách sai trên chữ MXH ("tin nhắn", "màu đen", "chính hãng", "giao hang nhanh" không dấu).
  * underthesea 9.5 (Apache-2.0, 46 MB): 0,36 ms/dòng (5.000 dòng ≈ 1,8 giây, quá ngân sách 300 ms
    của mây), tách sai nặng trên chữ thường MXH ("nước | hoa thơm", "nhắn shop", "nữ aura").
  * Danh sách Viet74K / Viet39K (kèm underthesea, repo duyet/vietnamese-wordlist): giấy phép
    GPL-2.0 — không gói vào dashboard được.
Danh sách dưới đây ngắn (~600 từ ghép hay gặp trên MXH mua sắm, quà tặng, thời trang, làm đẹp +
~330 hư từ ghép), nên thiếu từ là chuyện thường: thiếu một từ ghép thì cặp chữ đó vẫn được đếm như
trước (ghép hai âm tiết), chỉ là mảnh cắt ngang quanh nó chưa bị chặn. Thêm từ: viết CÓ dấu vào
đúng nhóm, cách nhau bằng dấu phẩy; viết cả hai kiểu đặt dấu nếu hay gặp cả hai (khoẻ/khỏe). So khớp
CÓ dấu, chữ gõ không dấu ("mau den") khớp mọi dạng; "mầu" là cách viết khác của "màu"
(`chi_so._BIEN_THE`).

Hai nhóm:
  TU_HU    hư từ / từ đệm / đại từ / lời lịch sự / câu trả lời mẫu của shop ("cảm ơn", "vui lòng",
           "thật sự", "bây giờ", "tin nhắn", "hỗ trợ"…): là MỘT đơn vị khi tách (chặn mảnh cắt
           ngang) nhưng KHÔNG bao giờ lên mây.
  TU_GHEP  từ ghép có nghĩa ("túi xách", "nước hoa", "tinh tế", "màu đen"…): một đơn vị, lên mây
           được như một cụm.
"""
from __future__ import annotations

from dashboard import chuan_chu as CC

TU_HU = """
cảm ơn, cám ơn, xin lỗi, vui lòng, làm ơn, xin chào, xin phép, tham gia,
không hề, chẳng hề, chả hề, thật sự, thực sự, thật ra, thực ra, quả thật, quả thực, quả là,
đúng là, đúng rồi, chính là, chỉ là, cũng là, cũng được, hơi bị, khá là, rất là, quá là,
có thể, có lẽ, có khi, có vẻ, hình như, dường như, chắc là, chắc hẳn, hẳn là, đã từng,
bây giờ, giờ đây, hiện giờ, lúc này, lúc nãy, ban nãy, hôm nay, hôm qua, hôm kia, hôm nào,
hôm trước, hôm sau, bữa nay, bữa trước, bữa nào, ngày mai, ngày kia, sáng nay, trưa nay,
chiều nay, tối nay, đêm nay, đêm qua, tối qua, năm nay, năm ngoái, năm sau, tháng này,
tháng sau, tháng trước, tuần này, tuần sau, tuần trước, sắp tới, gần đây, dạo này, mới đây,
vừa rồi, hồi nãy, hồi trước, ngày xưa, ngày trước, sau này, mai mốt, lâu nay, xưa nay,
mỗi ngày, hằng ngày, hàng ngày, ngày nào, lần đầu, lần sau, lần này, lần trước, đầu tiên,
cuối cùng, tiếp theo, tiếp tục, liên tục, bắt đầu, kết thúc, nhất định, luôn luôn, thường xuyên,
thường thường, đôi khi, thỉnh thoảng, lâu lâu, mãi mãi, suốt đời, cả đời, một chút,
chút xíu, một ít, một số, một vài, tất cả, toàn bộ, hầu hết, phần lớn, đa số, mọi người,
mọi thứ, mọi lúc, mọi nơi, người ta, ai cũng, ai nấy,
tại sao, vì sao, làm sao, thế nào, như thế, như vậy, như này, như nào, ra sao, bao giờ,
bao lâu, khi nào, lúc nào, chỗ nào, nơi nào, ở đâu, đâu đó, cái gì, gì đó, ai đó, nào đó,
cái này, cái kia, cái đó, cái ấy, điều này, điều đó, việc này, việc đó, chuyện này,
chuyện đó, thứ này, đồ này, làm gì, đi đâu,
nhưng mà, tuy nhiên, tuy là, tuy vậy, mặc dù, dù sao, dù vậy, dù cho, vì vậy, vì thế,
cho nên, thế nên, nên là, do đó, bởi vì, bởi thế, tại vì, nếu như, nếu mà, giả sử, hay là,
hoặc là, với lại, còn nữa, ngoài ra, hơn nữa, thêm nữa, bên cạnh, trong khi, sau đó,
trước đó, khi đó, lúc đó, từ đó, đến nỗi, đến mức, cho đến, cho tới, kể cả, kể từ, thay vì,
trong đó, ngoài kia, trên đời, thế thì, vậy thì, thế là, vậy là, thế mà, vậy mà, được rồi,
xong rồi, hết rồi, lâu rồi, được không, phải không, đúng không, hay không,
nói chung, nhất là, kiểu như, giống như, chẳng hạn, ví dụ, cụ thể, nghĩa là, tức là,
tóm lại, nói thật, thật lòng, công nhận, không biết, chả biết, chẳng biết, biết đâu,
vô cùng, cực kỳ, cực kì, hết sức, quá trời, quá chừng, trời ơi, ôi trời, dã man, quá xá,
ghê gớm, vãi chưởng,
chúng tôi, chúng ta, chúng mình, chúng em, chúng con, chúng nó, bọn mình, bọn em, bọn tớ,
bọn nó, tụi mình, tụi em, tụi tớ, tụi nó, các bạn, các chị, các anh, các em, các bác,
ông ấy, bà ấy, anh ấy, chị ấy, em ấy, cô ấy, chú ấy, bạn ấy, cậu ấy, bản thân, riêng mình,
liên hệ, nhắn tin, tin nhắn, kiểm tra, phản hồi, trả lời, hỗ trợ, tư vấn, giải đáp,
thông tin, chi tiết, xem thêm, xem ngay, mua ngay, đặt ngay, báo giá, hỏi giá, chốt đơn,
lên đơn, ra đơn, để lại, ghé thăm, ghé qua, truy cập, đường link, đăng ký, đăng kí,
đăng lại, đăng bài, đăng tải, theo dõi, bình luận, chia sẻ, tham khảo, tự nhiên, duy nhất,
nhân dịp, mong rằng, hiểu rằng, biết rằng, nghĩ rằng, gửi lời, dành riêng, cùng với, trở thành,
có mặt, áp dụng, sẵn sàng, chính thức, tích điểm, nâng hạng
"""

TU_GHEP = """
túi xách, túi đeo chéo, túi đeo vai, túi đeo hông, túi cầm tay, ví cầm tay, đeo chéo, đeo vai,
cầm tay, xách tay, ba lô, cặp sách, va li, dây đeo, quai đeo, quai xách, khoá kéo, khóa kéo,
dây kéo, phụ kiện, trang sức, vòng tay, vòng cổ, dây chuyền, bông tai, khuyên tai, nhẫn cưới,
đồng hồ, kính mắt, kính râm, mắt kính, khăn quàng, thắt lưng, dây lưng,
nước hoa, mùi hương, hương thơm, nốt hương, lưu hương, toả hương, tỏa hương, mỹ phẩm,
mĩ phẩm, son môi, son dưỡng, kem dưỡng, kem chống nắng, sữa rửa mặt, dưỡng da, làm đẹp,
trang điểm, chăm sóc, chăm sóc da, xịt thơm,
quần áo, áo khoác, áo dài, áo sơ mi, áo thun, giày dép, giày cao gót, giày thể thao,
trang phục, thời trang, phong cách, xu hướng, trào lưu, phối đồ, lên đồ,
mẫu mã, kiểu dáng, thiết kế, kích thước, kích cỡ, màu sắc, chất liệu, chất lượng, độ bền,
đường may, đường chỉ, hoạ tiết, họa tiết, hoa văn, da thật, da bò, da cừu, giả da, da lộn,
da tổng hợp, vải bố, vải dù, sức chứa, trọng lượng, hình dáng, đường nét, tông màu,
phối màu, bề mặt, lớp lót,
màu đen, màu trắng, màu đỏ, màu hồng, màu xanh, màu vàng, màu nâu, màu be, màu kem,
màu tím, màu xám, màu ghi, màu bạc, màu cam, màu nude, màu xanh dương, màu xanh lá,
màu xanh ngọc, màu hồng phấn, xanh dương, xanh lá, xanh lam, xanh lục, xanh ngọc, xanh rêu,
xanh than, đỏ đô, đỏ tươi, hồng phấn, hồng đất, hồng nhạt, nâu đất, vàng chanh, tím than,
đen trắng,
sản phẩm, hàng hoá, hàng hóa, mặt hàng, chính hãng, hàng thật, hàng giả, hàng nhái,
nguồn gốc, xuất xứ, thương hiệu, nhãn hiệu, cửa hàng, chi nhánh, đại lý, nhân viên,
khách hàng, người bán, người mua, dịch vụ, giao hàng, vận chuyển, đơn hàng, đặt hàng,
mua hàng, nhận hàng, đổi trả, đổi hàng, trả hàng, hoàn tiền, hoàn hàng, bảo hành,
thanh toán, khuyến mãi, khuyến mại, giảm giá, ưu đãi, miễn phí, tặng kèm, quà tặng, món quà,
phần quà, hộp quà, gói quà, bao bì, đóng gói, hộp đựng, túi đựng, túi giấy, giá cả,
giá trị, đáng giá, đáng tiền, xứng đáng, đắt đỏ, rẻ tiền, đắt tiền, phải chăng, hợp lý,
uy tín, tin tưởng, đánh giá, trải nghiệm, sử dụng, dùng thử, mua sắm, trực tuyến,
chăm sóc khách hàng, tổng đài, nhiệt tình, chu đáo, tận tâm, tận tình, thân thiện,
nhanh chóng, chậm trễ, cẩu thả, sơ sài, kỹ càng, kĩ càng, cẩn thận,
xinh đẹp, xinh xắn, xinh xẻo, dễ thương, đáng yêu, tuyệt vời, tuyệt đẹp, tuyệt hảo,
hoàn hảo, sang trọng, sang chảnh, tinh tế, thanh lịch, lịch sự, quý phái, cao cấp, hiện đại,
trẻ trung, năng động, cá tính, nữ tính, nam tính, dịu dàng, nhẹ nhàng, tối giản, đơn giản,
giản dị, tinh xảo, chỉn chu, chắc chắn, bền bỉ, cứng cáp, mềm mại, êm ái, tiện lợi,
tiện dụng, gọn gàng, nhỏ gọn, nhỏ xinh, rộng rãi, vừa vặn, nổi bật, bắt mắt, ấn tượng,
độc đáo, đặc biệt, ý nghĩa, ưng ý, hài lòng, thất vọng, tệ hại, sắc nét, bóng bẩy, sành điệu,
thời thượng, nhã nhặn, tươi tắn, rực rỡ, quyến rũ, ngọt ngào, thơm tho, dễ chịu, lung linh,
long lanh, xịn xò, xịn sò, đỉnh cao, ổn áp, tạm ổn, bình thường, cũ kỹ, lỗi thời, kinh khủng,
khủng khiếp, dễ dàng, khó khăn, phù hợp, thích hợp, cần thiết, quan trọng,
hạnh phúc, vui vẻ, vui mừng, vui tươi, yêu thương, yêu quý, thương yêu, yêu thích, ưa thích,
thích thú, buồn cười, hài hước, thú vị, cảm động, xúc động, cảm xúc, cảm nhận, cảm giác,
ấm áp, ấm lòng, tự hào, tự tin, may mắn, bất ngờ, ngạc nhiên, tò mò, phấn khích, khó chịu,
bực mình, tức giận, lo lắng, an tâm, yên tâm, rạng rỡ, mạnh khỏe, mạnh khoẻ, khỏe mạnh,
khoẻ mạnh, sức khỏe, sức khoẻ, bình an, bình yên, an lành, an khang, thịnh vượng, thành công,
hy sinh, hi sinh, tốt đẹp, trọn vẹn, viên mãn, tràn đầy, ngập tràn, biết ơn, mong muốn,
hy vọng, hi vọng, mong chờ, chờ đợi, cố gắng, nỗ lực, chăm chỉ, vất vả, nhớ nhung,
nụ cười, niềm vui, nước mắt, tình yêu, tình cảm, tình thương, kỷ niệm, kỉ niệm, khoảnh khắc,
cuộc sống, tuổi trẻ, thanh xuân, ước mơ, mong ước, lời chúc, chúc mừng, điểm tựa,
gia đình, bố mẹ, ba mẹ, cha mẹ, con gái, con trai, bạn gái, bạn trai, người yêu, vợ chồng,
ông bà, anh chị, chị em, anh em, bạn bè, bạn thân, đồng nghiệp, phụ nữ, đàn ông, đàn bà,
con người, người thân, người lớn, trẻ em, em bé, học sinh, sinh viên, cô gái, chàng trai,
quảng cáo, chiến dịch, nội dung, diễn viên, người mẫu, ca sĩ, nghệ sĩ, người nổi tiếng,
thần tượng, kịch bản, âm nhạc, bài hát, hình ảnh, ý tưởng, sáng tạo, thông điệp, câu chuyện,
mạng xã hội, sự kiện, chương trình, trúng thưởng, giải thưởng, quay số, đập hộp, mở hộp,
sinh nhật, ngày lễ, việt nam, hà nội, sài gòn, thành phố, đà nẵng, hải phòng, cần thơ,
miền bắc, miền nam, miền trung, nước ngoài, long biên, cầu giấy, hoàn kiếm, đống đa, ba đình,
tây hồ, hà đông, gò vấp, bình thạnh, thủ đức, tân bình, phú nhuận, sân bay, trung tâm thương mại,
đi làm, đi chơi, đi tiệc, đi học, du lịch,
công sở, văn phòng, dạo phố, hẹn hò, dự tiệc,
lựa chọn, sở hữu, sưu tầm, giới thiệu, gợi ý, ủng hộ, ra mắt,
công việc, công ty, thời gian, thời điểm, không gian, vấn đề, kết quả, nguyên nhân,
mục đích, ý kiến, quan điểm, suy nghĩ, kinh nghiệm, kiến thức, thông minh, xã hội, tiền bạc,
điện thoại, máy tính, trường học, bệnh viện, nhà hàng, siêu thị, thế giới, quốc tế,
đất nước, quê hương, cơ thể, khuôn mặt, làn da, mái tóc, vóc dáng, ngoại hình, nhan sắc,
thần thái, khí chất, phong thái, nhãn hàng,
đặc quyền, độc quyền, hội viên, thành viên, thân thiết, tri ân, trọn bộ, trọn gói, phiên bản,
hệ thống, trung tâm, cá nhân, tài liệu, giấy tờ, kim loại, vật dụng, hoả tốc, hỏa tốc,
đồng bộ, sơ mi, phom dáng, form dáng, khung hình, hoa hồng, đoá hoa, đóa hoa, trái tim,
lời nhắn, tiếng cười, trò chơi, buổi tối, phút giây, khán giả, giai điệu, nghệ thuật,
trình diễn, hành trình, cơ hội, điểm nhấn, năng lượng, tích cực, tiêu cực, tinh thần,
tâm lý, tâm lí, cuộc đời, thủ lĩnh, trân trọng, hấp dẫn, kết hợp, lo toan, chân thành,
đồng hành, nâng niu, mỉm cười, lưu giữ, chiều chuộng, yêu chiều, tận hưởng, quan tâm,
thuận lợi, tinh khôi, nhận quà, thơm phức, gửi gắm, bảo vệ, phát triển, lớn lao, diễn đạt,
ngại ngùng, lãng mạn, bận rộn, đón nhận, chào đón, hiện thực, tiềm năng, biểu cảm,
truyền tải, thanh tao, xuất hiện, thoải mái, thể hiện, trưởng thành, lâu bền, tiêu thụ,
hoạt động, lan toả, lan tỏa, toả sáng, tỏa sáng, khám phá, tuyệt đối, sắp xếp, mềm mịn,
cầu kỳ, cầu kì, thực tế, linh hoạt, trang trọng, kiêu sa, tận tay, lấp lánh, tìm kiếm,
khẳng định, thầm lặng, mạnh mẽ, mở bán, ghi điểm
"""


def _tach_ds(s: str) -> list[str]:
    return [" ".join(CC.thuong(x).split()) for x in s.replace("\n", ",").split(",") if x.strip()]


def _khoa(cum: str) -> str:
    return " ".join(CC.bo_dau(w) for w in cum.split())


#: {khoá bỏ dấu: [(các chữ CÓ dấu, là từ ghép có nghĩa?)]} — hư từ đứng trước. Bỏ dấu thì nhiều từ
#: trùng khoá ("có thể" hư từ / "cơ thể" từ ghép; "vậy mà" / "váy mà"; "ông bà" / "ổng bả") nên
#: tách từ so CÓ dấu; chữ gõ không dấu khớp mọi dạng (hư từ trước — gặp nhiều hơn hẳn).
DANG: dict[str, list[tuple[tuple[str, ...], bool]]] = {}
#: {khoá bỏ dấu: mặt chữ có dấu} của từ ghép có nghĩa; tập khoá hư từ ghép.
GHEP: dict[str, str] = {}
HU: set[str] = set()
for _ds, _la_ghep in ((TU_HU, False), (TU_GHEP, True)):
    for _c in _tach_ds(_ds):
        _k = _khoa(_c)
        DANG.setdefault(_k, []).append((tuple(_c.split()), _la_ghep))
        if _la_ghep:
            GHEP.setdefault(_k, _c)
        else:
            HU.add(_k)
#: Độ dài (số âm tiết) dài nhất trong danh sách — so khớp dài nhất thử từ đây xuống 2.
DAI_NHAT: int = max(len(k.split()) for k in DANG)
#: Âm tiết (bỏ dấu) đứng đầu một từ trong danh sách — chữ không ở đây thì khỏi tra (nhanh).
DAU: frozenset[str] = frozenset(k.split()[0] for k in DANG)
#: Hashtag viết liền đúng một từ ghép ("#tuixach", "#nuochoa") → khoá từ ghép: đếm chung với chữ
#: thường "túi xách", không thành hai mục trùng nghĩa trên mây. Hashtag không dấu nên khoá trùng
#: hư từ thì coi là hư từ (như chữ gõ không dấu).
LIEN: dict[str, str] = {}
for _k in sorted(DANG):
    LIEN.setdefault(_k.replace(" ", ""), _k)
