"""Tên tỉnh/thành cho mã vùng TikTok (`province_id` của báo cáo AUDIENCE) — 26/10/2026, chủ dự án:
khối Khán giả hiện "Hà Nội" thay vì "Mã vùng 1581129".

Mã vùng TikTok là mã GeoNames (geonameid; quốc gia Việt Nam = 1562822). Bảng dưới dựng từ bản dump
GeoNames tải ngày 26/10/2026 (https://download.geonames.org/export/dump/VN.zip, cột feature_code):
  • ADM1  — 34 tỉnh/thành SAU sáp nhập 01/07/2025 (mã mới 13494xxx + 11 tỉnh giữ nguyên mã cũ);
  • ADM1H — 52 tỉnh/thành TRƯỚC sáp nhập đã thôi dùng mã (cùng 11 tỉnh giữ mã ở ADM1 là đủ 63 tỉnh
    cũ; thêm Hà Tây, Sa Đéc cũ hơn) — 88 mã, đối chiếu đủ với dump (bài thử ghim số mã).
Báo cáo TikTok có thể trả mã cũ hoặc mã mới tuỳ thời điểm — giữ cả hai. Tên viết theo tên tiếng Việt
thông dụng (có dấu); mã cũ và mã mới cùng tên (vd Lào Cai cũ / Lào Cai mới) thì khối Khán giả cộng
chung một dòng (`quang_cao.khan_gia` gộp theo nhãn).

Ngoài Việt Nam: soát 26/10/2026 trên VPS thấy 6 mã không thuộc Việt Nam (khán giả ở Thái Lan, Nhật,
Hàn…); tra admin1CodesASCII.txt của GeoNames — cả 6 là ADM1 → "<tên> (<nước>)". Không gọi API: mã
lạ khác (vùng chưa gặp, mã TikTok đổi) → trang hiện "Mã vùng <mã>". Soát mã chưa có tên trong kho:
`python -m dashboard.tiktok_ads vung-chua-ten` (chỉ đọc DB) rồi tra GeoNames, bổ sung bảng này.
"""
from __future__ import annotations

#: geonameid → tên tỉnh/thành (tiếng Việt). Không sửa tay mã — đối chiếu lại dump GeoNames khi thêm.
TEN_TINH: dict[str, str] = {
    # ── ADM1: 34 tỉnh/thành từ 01/07/2025 ──
    "1581129": "Hà Nội",
    "13494358": "TP. Hồ Chí Minh",
    "13494346": "Hải Phòng",
    "13494351": "Đà Nẵng",
    "13494363": "Cần Thơ",
    "1565033": "Huế",
    "1586182": "Cao Bằng",
    "1905099": "Điện Biên",
    "1577954": "Lai Châu",
    "1576632": "Lạng Sơn",
    "1559969": "Nghệ An",
    "1568758": "Quảng Ninh",
    "1567643": "Sơn La",
    "1566165": "Thanh Hóa",
    "1580700": "Hà Tĩnh",
    "13494365": "Tuyên Quang",
    "13494334": "Lào Cai",
    "13494335": "Thái Nguyên",
    "13494345": "Phú Thọ",
    "13494344": "Bắc Ninh",
    "13494347": "Hưng Yên",
    "13494348": "Ninh Bình",
    "13494350": "Quảng Trị",
    "13494352": "Quảng Ngãi",
    "13494353": "Gia Lai",
    "13494354": "Khánh Hòa",
    "13494356": "Lâm Đồng",
    "13494355": "Đắk Lắk",
    "13494357": "Đồng Nai",
    "13494359": "Tây Ninh",
    "13494361": "Vĩnh Long",
    "13494360": "Đồng Tháp",
    "13494364": "Cà Mau",
    "13494362": "An Giang",
    # ── ADM1H: tỉnh/thành trước 01/07/2025 (mã cũ) ──
    "1580578": "TP. Hồ Chí Minh",
    "1581297": "Hải Phòng",
    "1905468": "Đà Nẵng",
    "1581188": "Cần Thơ",
    "1594446": "An Giang",
    "1584534": "Bà Rịa - Vũng Tàu",
    "1905419": "Bắc Giang",
    "1905669": "Bắc Kạn",
    "1905675": "Bạc Liêu",
    "1905412": "Bắc Ninh",
    "1587974": "Bến Tre",
    "1587871": "Bình Định",
    "1905475": "Bình Dương",
    "1905480": "Bình Phước",
    "1581882": "Bình Thuận",
    "1905678": "Cà Mau",
    "1584169": "Đắk Lắk",
    "1904987": "Đắk Nông",
    "1582720": "Đồng Nai",
    "1582562": "Đồng Tháp",
    "1581088": "Gia Lai",
    "1581030": "Hà Giang",
    "1905637": "Hà Nam",
    "1905686": "Hải Dương",
    "7506719": "Hậu Giang",
    "1572594": "Hòa Bình",
    "1905699": "Hưng Yên",
    "1579634": "Khánh Hòa",
    "1579008": "Kiên Giang",
    "1565088": "Kon Tum",
    "1577882": "Lâm Đồng",
    "1562412": "Lào Cai",
    "1575788": "Long An",
    "1905626": "Nam Định",
    "1559970": "Ninh Bình",
    "1559971": "Ninh Thuận",
    "1905577": "Phú Thọ",
    "1569805": "Phú Yên",
    "1568839": "Quảng Bình",
    "1905516": "Quảng Nam",
    "1568769": "Quảng Ngãi",
    "1568733": "Quảng Trị",
    "1559972": "Sóc Trăng",
    "1566557": "Tây Ninh",
    "1566338": "Thái Bình",
    "1905497": "Thái Nguyên",
    "1564676": "Tiền Giang",
    "1559975": "Trà Vinh",
    "1559976": "Tuyên Quang",
    "1559977": "Vĩnh Long",
    "1905856": "Vĩnh Phúc",
    "1559978": "Yên Bái",
    "1581019": "Hà Tây",
    "12166267": "Sa Đéc",
    # ── Ngoài Việt Nam (soát 26/10/2026: mã TikTok thật trong kho, tra admin1CodesASCII.txt của
    #    GeoNames — đều là ADM1; tên GeoNames + nước bằng tiếng Việt) ──
    "1609348": "Bangkok (Thái Lan)",
    "1641897": "Đông Kalimantan (Indonesia)",
    "1822449": "Ratanakiri (Campuchia)",
    "1841597": "Gyeongsangbuk-do (Hàn Quốc)",
    "1853904": "Osaka (Nhật Bản)",
    "1862047": "Hyōgo (Nhật Bản)",
}
#: Mã ngoài Việt Nam trong TEN_TINH (đếm / soát riêng).
NGOAI_VN = frozenset({"1609348", "1641897", "1822449", "1841597", "1853904", "1862047"})


def ten_tinh(ma) -> str | None:
    """Mã vùng TikTok → tên tỉnh/thành; None khi chưa có trong bảng."""
    return TEN_TINH.get(str(ma or "").strip())
