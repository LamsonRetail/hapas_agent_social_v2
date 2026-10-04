"""Ngành hàng của TikTok Creative Center: câu tiếng Việt → mã ngành của từng actor.

Dùng chung cho hai chỗ:
  • `tiktok_top_ads` (tiktok_ads_tool.py) — top quảng cáo theo ngành.
  • chế độ `trend` của `social_listen` (tiktok_trend.py) — bảng hashtag theo ngành.

Ba actor gọi cùng một ngành bằng ba kiểu khác nhau (đọc input schema 04/10/2026):
  • azzouzana~tiktok-creative-center-top-ads-scraper: NHÃN chữ, có cả ngành con
    ("Apparel & Accessories", "Bags", "Ordinary Jewellery"…; tên trùng thì kèm mã, vd
    "Beauty & Personal Care (14000000000)").
  • lexis-solutions~tiktok-top-ads-scraper (dự phòng): mã HAI SỐ của ngành cha ("22").
  • data_xplorer~tiktok-trends (`industryId`): mã 11 số của ngành cha ("22000000000");
    chỉ nhận 15 ngành cha, lọc phía actor nên không tốn thêm tiền.
Ngành con (túi, trang sức…) chỉ actor chính lọc được; hai actor kia lùi về ngành cha —
bên gọi phải nói rõ là đã lọc rộng hơn.

Khớp câu: chữ CÓ DẤU trước. Bỏ dấu chỉ dùng cho cụm dài (>= 6 chữ cái): "son" bỏ dấu
trùng "sơn", "váy" trùng "vay", "ví" trùng "vi", "túi" trùng "tui" (= "tôi" miền Nam).
"""
from __future__ import annotations

import re
import unicodedata

# Tên ngành cha theo mã hai số — enumTitles của lexis, khớp `industryKey`
# ("label_22104000000") mà cả hai actor top ads trả về.
TEN_NHOM = {
    "10": "Education", "11": "Vehicle & Transportation", "12": "Baby, Kids & Maternity",
    "13": "Financial Services", "14": "Beauty & Personal Care", "15": "Tech & Electronics",
    "16": "Appliances", "17": "Travel", "18": "Household Products", "19": "Pets",
    "20": "Apps", "21": "Home Improvement", "22": "Apparel & Accessories",
    "23": "News & Entertainment", "24": "Business Services", "25": "Games",
    "26": "Life Services", "27": "Food & Beverage", "28": "Sports & Outdoor",
    "29": "Health", "30": "E-Commerce (Non-app)",
}
# Ngành cha mà `industryId` của data_xplorer nhận (enum của actor, 04/10/2026).
NHOM_TREND = {"10", "11", "12", "14", "15", "17", "18", "19", "21", "22", "23", "25",
              "27", "28", "29"}

# (khoá, tên tiếng Việt, nhãn azzouzana, mã ngành cha, cụm người dùng hay gõ).
# THỨ TỰ CÓ NGHĨA: ngành con đứng trước ngành cha ("trang sức cao cấp" trước "trang
# sức", "phụ kiện trang sức" trước "phụ kiện", "giày nữ" trước "giày").
_BANG = (
    ("tui_xach", "Túi xách", "Bags", "22",
     ("túi xách", "túi", "balo", "ba lô", "ví", "bóp", "handbag", "bags", "bag",
      "backpack", "wallet")),
    ("trang_suc_cao_cap", "Trang sức cao cấp", "High-end Jewellery", "22",
     ("trang sức cao cấp", "vàng bạc đá quý", "kim cương", "fine jewelry",
      "high-end jewellery")),
    ("trang_suc", "Trang sức", "Ordinary Jewellery", "22",
     ("trang sức", "phụ kiện trang sức", "nhẫn", "vòng tay", "dây chuyền", "bông tai",
      "khuyên tai", "jewelry", "jewellery")),
    ("dong_ho", "Đồng hồ", "Watches", "22", ("đồng hồ", "watches", "watch")),
    ("thoi_trang_nu", "Thời trang nữ", "Women's Clothing", "22",
     ("thời trang nữ", "quần áo nữ", "đồ nữ", "váy", "đầm", "women's clothing")),
    ("thoi_trang_nam", "Thời trang nam", "Men's Clothing", "22",
     ("thời trang nam", "quần áo nam", "đồ nam", "men's clothing")),
    ("giay_nu", "Giày nữ", "Women's Shoes", "22",
     ("giày nữ", "giày dép nữ", "women's shoes")),
    ("giay_nam", "Giày nam", "Men's Shoes", "22", ("giày nam", "men's shoes")),
    ("phu_kien_thoi_trang", "Phụ kiện thời trang", "Clothing Accessories", "22",
     ("phụ kiện thời trang", "phụ kiện", "mũ", "nón", "khăn", "thắt lưng", "kính mát",
      "clothing accessories", "accessories")),
    ("thoi_trang", "Thời trang và phụ kiện", "Apparel & Accessories", "22",
     ("thời trang", "quần áo", "giày dép", "giày", "apparel & accessories", "apparel",
      "fashion")),
    ("nuoc_hoa", "Nước hoa", "Fragrances & Perfumes", "14",
     ("nước hoa", "perfume", "fragrances", "fragrance")),
    ("cham_soc_da", "Chăm sóc da", "Skincare", "14",
     ("chăm sóc da", "dưỡng da", "skincare", "skin care")),
    ("trang_diem", "Trang điểm", "Cosmetics", "14",
     ("trang điểm", "mỹ phẩm trang điểm", "son", "makeup", "cosmetics")),
    ("lam_dep", "Làm đẹp và chăm sóc cá nhân", "Beauty & Personal Care (14000000000)", "14",
     ("làm đẹp", "mỹ phẩm", "chăm sóc cá nhân", "beauty & personal care", "beauty")),
    ("me_be", "Mẹ và bé", "Baby, Kids & Maternity", "12",
     ("mẹ và bé", "mẹ & bé", "mẹ bé", "trẻ em", "em bé", "baby")),
    ("an_uong", "Đồ ăn và đồ uống", "Food & Beverage", "27",
     ("đồ ăn", "đồ uống", "ăn uống", "thực phẩm", "f&b", "food & beverage", "food")),
    ("gia_dung", "Đồ gia dụng", "Household Products", "18",
     ("đồ gia dụng", "gia dụng", "household products", "household")),
    ("noi_that", "Nhà cửa và nội thất", "Home Improvement", "21",
     ("nội thất", "nhà cửa", "trang trí nhà", "home improvement", "home decor")),
    ("cong_nghe", "Công nghệ và điện tử", "Tech & Electronics", "15",
     ("công nghệ", "điện tử", "điện thoại", "tech & electronics", "electronics", "tech")),
    ("the_thao", "Thể thao và dã ngoại", "Sports & Outdoor", "28",
     ("thể thao", "dã ngoại", "sports & outdoor", "sports", "outdoor")),
    ("du_lich", "Du lịch", "Travel (17000000000)", "17", ("du lịch", "travel")),
)
_BO_DAU_TOI_THIEU = 6


def _co_dau(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", str(s or "")).lower().split())


def _khong_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", _co_dau(s).replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _co_cum(cau: str, cum: str) -> bool:
    return re.search(r"(?<![\w])" + re.escape(cum) + r"(?![\w])", cau) is not None


def _ra(dong: tuple) -> dict:
    khoa, ten, nhan, nhom, _ = dong
    return {"khoa": khoa, "ten": ten, "nhan_actor": nhan, "nhom": nhom,
            "ten_nhom": TEN_NHOM[nhom],
            "id_trend": f"{nhom}000000000" if nhom in NHOM_TREND else "",
            "la_nganh_con": nhan.split(" (")[0] != TEN_NHOM[nhom]}


def tim(cau) -> dict | None:
    """Câu người dùng ("túi xách", "thời trang", "Apparel & Accessories", "22") → ngành.

    Trả {khoa, ten, nhan_actor, nhom, ten_nhom, id_trend, la_nganh_con}; None nếu không
    nhận ra (bên gọi phải báo, không được lặng lẽ bỏ lọc)."""
    s = _co_dau(cau)
    if not s:
        return None
    k = _khong_dau(s)
    so = re.sub(r"\D", "", s)
    for dong in _BANG:
        khoa, ten, nhan, nhom, cum = dong
        if s in (khoa, khoa.replace("_", " "), nhan.lower(), _co_dau(ten)) \
                or k == _khong_dau(ten):
            return _ra(dong)
    # Mã số: "22" hoặc "22000000000" → ngành cha.
    if so and s.replace(" ", "") == so and (so[:2] in TEN_NHOM) and len(so) in (2, 11):
        nhom = so[:2]
        cha = next((d for d in _BANG if d[3] == nhom and not _ra(d)["la_nganh_con"]), None)
        if cha:
            return _ra(cha)
    for dong in _BANG:
        for cum in dong[4]:
            c = _co_dau(cum)
            if _co_cum(s, c):
                return _ra(dong)
            ck = _khong_dau(c)
            if len(ck.replace(" ", "")) >= _BO_DAU_TOI_THIEU and _co_cum(k, ck):
                return _ra(dong)
    return None


def ten_nhom_tu_key(key) -> str:
    """`industryKey` của actor ("label_22104000000") → tên ngành cha ("Apparel & …")."""
    so = re.sub(r"\D", "", str(key or ""))
    return TEN_NHOM.get(so[:2], "") if len(so) >= 2 else ""


def danh_sach() -> str:
    """Các ngành nhận được, để báo khi không khớp."""
    return ", ".join(d[1] for d in _BANG)
