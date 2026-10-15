"""Dashboard lắng nghe (đợt 2, 14/10/2026): chuẩn hoá định danh nguồn + kiểm biểu mẫu.

Định danh lưu kho phải đúng dạng Mark dùng khi quét (`theo_doi._chuan_dinh_danh`): người dùng
dán nguyên link trang cá nhân (kèm ?lang=, igsh=…) thì vẫn ra đúng username/URL trang."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from dashboard import nhap_lieu as NL

UC = "UCaBcDeFgHiJkLmNoPqRsTuV"     # 24 ký tự, hoa thường lẫn lộn — phải giữ nguyên


@pytest.mark.parametrize("p, vao, ra", [
    ("tiktok", "https://www.tiktok.com/@Hapas.Official?lang=vi", "hapas.official"),
    ("tiktok", "tiktok.com/@abc_1/video/7412345678901234567?is_from_webapp=1", "abc_1"),
    ("tiktok", "@Hapas_VN", "hapas_vn"),
    ("tiktok", "hapas.vn", "hapas.vn"),
    ("instagram", "https://www.instagram.com/Hapas.Official/?igsh=MWx0bG9rYw==", "hapas.official"),
    ("instagram", "instagram.com/stories/hapas.vn/3456789012345678901/", "hapas.vn"),
    ("instagram", "@Hapas.VN", "hapas.vn"),
    ("youtube", UC, UC),
    ("youtube", f"https://www.youtube.com/channel/{UC}/videos", UC),
    ("youtube", "https://m.youtube.com/@HapasVN/shorts", "@hapasvn"),
    ("youtube", "@HapasVN", "@hapasvn"),
    ("youtube", "HapasVN", "@hapasvn"),
    ("facebook", "https://web.facebook.com/HapasVN/?ref=page_internal", "https://www.facebook.com/hapasvn"),
    ("facebook", "fb.com/hapasvn", "https://www.facebook.com/hapasvn"),
    ("facebook", "m.facebook.com/HapasVN/", "https://www.facebook.com/hapasvn"),
    ("facebook", "https://www.facebook.com/profile.php?id=100012345678&sk=about",
     "https://www.facebook.com/100012345678"),
    ("facebook", "https://www.facebook.com/pages/Hapas-Store/123456789", "https://www.facebook.com/123456789"),
    ("facebook", "https://www.facebook.com/groups/TuiXachViet/", "https://www.facebook.com/groups/tuixachviet"),
    ("facebook", "HapasVN", "https://www.facebook.com/hapasvn"),
])
def test_chuan_dinh_danh_tu_link_dan(p, vao, ra):
    dd, link = NL.chuan_dinh_danh(p, vao)
    assert dd == ra
    assert link.startswith("https://")


@pytest.mark.parametrize("p, vao, chu", [
    ("tiktok", "https://vm.tiktok.com/ZSabc123/", "rút gọn"),
    ("tiktok", "https://www.tiktok.com/foryou", "Không thấy tên tài khoản"),
    ("tiktok", "https://www.instagram.com/hapas", "Instagram"),
    ("instagram", "https://www.instagram.com/p/Cxyz123/", "link bài"),
    ("instagram", "https://www.instagram.com/reel/Cxyz123/", "link bài"),
    ("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "link video"),
    ("youtube", "https://youtu.be/dQw4w9WgXcQ", "link video"),
    ("youtube", "https://www.youtube.com/c/HapasVN", "/c/"),
    ("facebook", "https://www.facebook.com/HapasVN/posts/pfbid0abc", "không phải link trang"),
    ("facebook", "https://www.facebook.com/watch/?v=123", "không phải link trang"),
    ("facebook", "https://www.facebook.com/profile.php", "thiếu id"),
    ("facebook", "https://www.tiktok.com/@hapas", "TikTok"),
    ("tiktok", "", "Chưa nhập"),
    ("threads", "hapas", "Nền tảng"),
    ("tiktok", "tên có dấu cách", "TikTok"),
])
def test_chuan_dinh_danh_bao_loi_de_hieu(p, vao, chu):
    with pytest.raises(NL.LoiNhap) as e:
        NL.chuan_dinh_danh(p, vao)
    assert chu in str(e.value)


def test_dinh_danh_la_diem_co_dinh_cua_cach_mark_so_khop():
    """Dạng lưu kho đi qua `theo_doi._chuan_dinh_danh` (Mark so nguồn ↔ kết quả actor) không đổi
    gì ngoài phần Mark tự bỏ ('@', scheme/www của Facebook) — lệch là nguồn quét không ra bài."""
    import theo_doi as T
    assert T._chuan_dinh_danh("tiktok", NL.chuan_dinh_danh("tiktok", "@Hapas.Official")[0]) \
        == "hapas.official"
    assert T._chuan_dinh_danh("instagram", NL.chuan_dinh_danh("instagram", "instagram.com/Ab_c/")[0]) \
        == "ab_c"
    assert T._chuan_dinh_danh("youtube", NL.chuan_dinh_danh("youtube", UC)[0]) == UC
    assert T._chuan_dinh_danh("youtube", NL.chuan_dinh_danh("youtube", "@HapasVN")[0]) == "hapasvn"
    fb = NL.chuan_dinh_danh("facebook", "https://web.facebook.com/HapasVN/?ref=x")[0]
    # actor Facebook trả inputUrl đúng URL đã gửi (có thể thêm '/'): hai bên phải ra cùng khoá
    assert T._chuan_dinh_danh("facebook", fb) == T._chuan_dinh_danh("facebook", fb + "/") \
        == "facebook.com/hapasvn"


@pytest.mark.parametrize("vao, ra", [("5", "5.00"), ("12,5", "12.50"), (" 0 ", "0.00"),
                                     ("100", "100.00"), ("99.999", "100.00"),
                                     ("100.01", "100.01"), ("2500", "2500.00")])
def test_tran_usd_hop_le(vao, ra):
    """Chủ dự án 15/10: trần tháng không còn trần trên 100 USD."""
    assert NL.tran_usd(vao) == Decimal(ra)


@pytest.mark.parametrize("vao", ["-1", "abc", "", "nan", "inf", "1e9"])   # 1e9: tràn cột
def test_tran_usd_am_rac_hoac_tran_cot(vao):
    with pytest.raises(NL.LoiNhap):
        NL.tran_usd(vao)


@pytest.mark.parametrize("vao, ra", [
    ("/nguon?du_an=hapas", "/nguon?du_an=hapas"), ("/", "/"), ("//evil.com", "/"),
    ("https://evil.com/x", "/"), ("/\\evil.com", "/"), ("nguon", "/"), ("/a\r\nb", "/"),
    ("/x?next=https://evil.com", "/"), (None, "/")])
def test_chi_chuyen_huong_duong_tuong_doi(vao, ra):
    assert NL.duong_an_toan(vao) == ra


def test_link_an_toan_chi_http():
    assert NL.link_an_toan("javascript:alert(1)") == ""
    assert NL.link_an_toan("https://a.vn/x") == "https://a.vn/x"


def test_email_vai_tro_ma_du_an():
    assert NL.email("  A.B@HAPAS.VN ") == "a.b@hapas.vn"
    for sai in ("abc", "a@b", "a b@c.vn", ""):
        with pytest.raises(NL.LoiNhap):
            NL.email(sai)
    assert NL.vai_tro("quan_ly") == "quan_ly"
    with pytest.raises(NL.LoiNhap):
        NL.vai_tro("admin")
    assert NL.ma_du_an(" Hapas ") == "hapas"
    for sai in ("h", "-hapas", "ha pas", "a" * 41):
        with pytest.raises(NL.LoiNhap):
            NL.ma_du_an(sai)


def test_bieu_mau_du_an_va_nguon():
    d = NL.du_an({"ma": "hapas", "ten": " HAPAS ", "tu_khoa": "hapas, Hapas,túi hapas\n",
                  "tu_loai_tru": "guitar", "thi_truong": "vn", "dang_bat": "1"}, moi=True)
    assert d == {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas"],
                 "tu_loai_tru": ["guitar"], "boi_canh": "", "thi_truong": "VN", "dang_bat": True}
    with pytest.raises(NL.LoiNhap):
        NL.du_an({"ten": "X", "tu_khoa": ""}, moi=False)          # thiếu từ khoá
    n = NL.nguon({"nen_tang": "tiktok", "dinh_danh": "https://www.tiktok.com/@KolA",
                  "loai": "kol", "chu_ky_ngay": "3", "so_bai_moi_lan": "10", "nhan": "kol, mỹ phẩm"})
    assert n == {"nen_tang": "tiktok", "dinh_danh": "kola", "link": "https://www.tiktok.com/@kola",
                 "ten": "kola", "loai": "kol", "nhan": ["kol", "mỹ phẩm"], "chu_ky_ngay": 3,
                 "so_bai_moi_lan": 10}
    for sai in ({"chu_ky_ngay": "0"}, {"chu_ky_ngay": "31"}, {"so_bai_moi_lan": "0"},
                {"so_bai_moi_lan": "-5"}, {"so_bai_moi_lan": str(NL.SO_TOI_DA + 1)},
                {"loai": "fanpage"}):
        with pytest.raises(NL.LoiNhap):
            NL.nguon({"nen_tang": "tiktok", "dinh_danh": "kola", **sai})
    # Không trần trên nghiệp vụ cho số bài mỗi lần (chủ dự án 15/10: "không có giới hạn").
    assert NL.nguon({"nen_tang": "tiktok", "dinh_danh": "kola",
                     "so_bai_moi_lan": "500"})["so_bai_moi_lan"] == 500


def test_ngay():
    md = datetime.date(2026, 10, 14)
    assert NL.ngay("", md) == md
    assert NL.ngay("2026-10-01", md) == datetime.date(2026, 10, 1)
    with pytest.raises(NL.LoiNhap):
        NL.ngay("01/10/2026", md)
    for cuc_tri in ("9999-12-31", "0001-01-01", "1999-12-31", "2101-01-01"):
        with pytest.raises(NL.LoiNhap, match="2000–2100"):
            NL.ngay(cuc_tri, md)
    assert NL.ngay("2000-01-01", md).year == 2000 and NL.ngay("2100-12-31", md).year == 2100
