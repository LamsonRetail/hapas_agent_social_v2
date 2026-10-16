"""Dashboard lắng nghe (đợt 2, 14/10/2026): chỉ số kiểu Kompa (`dashboard/chi_so.py`).

Mọi kỳ vọng tính tay. "Thảo luận" = số bài + số bình luận nền tảng báo; ngày theo GIỜ VN của
`dang_luc`; bài kênh nhà tính vào số bài/thảo luận/nguồn nhưng không vào sắc thái/chủ đề/từ khoá.
"""
from __future__ import annotations

import datetime

import pytest

from dashboard import chi_so as CS

D = datetime.date
UTC = datetime.timezone.utc


def bai(luc: str, *, p="tiktok", nid: int | None = 1, loai="kol", bl=0, xem=0, thich=0, cs=0,
        sac=None, cd=None, tk="kol_a", tg="KOL A", nd="", ht="", link=None, ten=None):
    """`luc` ISO có múi giờ (vd '2026-10-14T09:00+07:00' hoặc '…Z')."""
    dt = datetime.datetime.fromisoformat(luc.replace("Z", "+00:00"))
    return {"khoa": f"{p}:{luc}:{tk}", "nen_tang": p, "nguon_id": nid,
            "kieu_quet": "theo_doi" if nid else "tu_khoa", "link": link or f"https://x.vn/{p}/{luc}",
            "tac_gia": tg, "tai_khoan": tk, "followers": None, "dang_luc": dt, "noi_dung": nd,
            "hashtag": ht, "sac_thai": sac, "chu_de": cd, "xem": xem, "thich": thich,
            "binh_luan": bl, "chia_se": cs, "nguon_loai": loai if nid else None,
            "nguon_ten": ten or (tg if nid else None), "nguon_dinh_danh": tk if nid else None,
            "nguon_link": f"https://www.tiktok.com/@{tk}" if nid else None}


def test_ranh_gioi_ngay_theo_gio_vn():
    rows = [bai("2026-10-13T16:59:00Z"),     # 23:59 ngày 13/10 giờ VN
            bai("2026-10-13T17:00:00Z"),     # 00:00 ngày 14/10 giờ VN
            bai("2026-10-14T16:59:59Z"),     # 23:59:59 ngày 14/10 giờ VN
            bai("2026-10-14T17:00:00Z")]     # 00:00 ngày 15/10 giờ VN — ngoài khoảng
    th = CS.tong_hop(rows, D(2026, 10, 13), D(2026, 10, 14), hom_nay=D(2026, 10, 20))
    assert th["xu_huong"]["moc"] == ["2026-10-13", "2026-10-14"]
    assert th["xu_huong"]["bai"] == [1, 2]
    assert th["kpi"]["bai"] == 3
    # datetime không múi giờ coi là UTC (psycopg luôn trả có múi giờ; đây là nhánh phòng hờ)
    assert CS.ngay_vn(datetime.datetime(2026, 10, 13, 17, 0)) == D(2026, 10, 14)  # noqa: DTZ001


def test_kpi_thao_luan_sac_thai_va_kenh_nha():
    rows = [bai("2026-10-10T09:00+07:00", bl=3, xem=100, thich=5, cs=1, sac="Tích cực", tk="a"),
            bai("2026-10-10T10:00+07:00", bl=0, xem=50, sac=None, tk="b", nid=2),
            bai("2026-10-11T10:00+07:00", bl=10, sac="Tiêu cực", tk="hapas", nid=3,
                loai="kenh_nha"),                                       # kênh nhà: không vào sắc thái
            bai("2026-10-11T11:00+07:00", bl=2, sac="Tiêu cực", tk="c", nid=None),
            bai("2026-10-12T11:00+07:00", bl=1, sac="lạ", tk="c", nid=None)]
    k = CS.tong_hop(rows, D(2026, 10, 8), D(2026, 10, 14), hom_nay=D(2026, 10, 14))["kpi"]
    assert (k["bai"], k["binh_luan"], k["thao_luan"]) == (5, 16, 21)
    assert k["xem"] == 150 and k["tuong_tac"] == 5 + 3 + 1 + 10 + 2 + 1
    assert k["nguon_co_bai"] == 4              # nguồn 1, 2, 3 + tài khoản "c" (tìm theo từ khoá)
    assert k["bai_kenh_nha"] == 1
    # 4 bài khách: 1 tích cực, 1 tiêu cực, 2 chưa phân loại ("lạ" không phải nhãn hợp lệ)
    assert (k["tich_cuc"], k["tieu_cuc"], k["trung_lap"], k["da_phan_loai"], k["chua_phan_loai"]) \
        == (1, 1, 0, 2, 2)
    assert (k["tich_cuc_pt"], k["tieu_cuc_pt"], k["trung_lap_pt"]) == (50.0, 50.0, 0.0)
    assert CS.kpi([])["tich_cuc_pt"] is None   # không bài nào phân loại thì không bịa %


def test_so_voi_ky_truoc_cung_do_dai():
    assert CS.khoang_truoc(D(2026, 10, 8), D(2026, 10, 14)) == (D(2026, 10, 1), D(2026, 10, 7))
    assert CS.khoang_truoc(D(2026, 9, 1), D(2026, 9, 30)) == (D(2026, 8, 2), D(2026, 8, 31))
    rows = [bai("2026-10-08T00:00+07:00", bl=1),
            bai("2026-10-14T23:59+07:00", bl=3),
            bai("2026-10-07T23:59+07:00", bl=1),        # kỳ trước (ngày cuối)
            bai("2026-10-01T00:00+07:00", bl=0),        # kỳ trước (ngày đầu)
            bai("2026-09-30T23:59+07:00", bl=50)]       # ngoài cả hai kỳ
    th = CS.tong_hop(rows, D(2026, 10, 8), D(2026, 10, 14), hom_nay=D(2026, 10, 14))
    ss = th["so_sanh"]
    assert ss["bai"] == {"nay": 2, "truoc": 2, "doi_pt": 0.0}
    assert ss["thao_luan"] == {"nay": 6, "truoc": 3, "doi_pt": 100.0}
    assert ss["binh_luan"] == {"nay": 4, "truoc": 1, "doi_pt": 300.0}
    assert th["khoang"]["ky_truoc"] == {"tu": "2026-10-01", "den": "2026-10-07"}
    trong = CS.tong_hop(rows[:2], D(2026, 10, 8), D(2026, 10, 14), hom_nay=D(2026, 10, 14))
    assert trong["so_sanh"]["bai"]["doi_pt"] is None          # kỳ trước 0 bài: không có %


def test_xu_huong_theo_ngay_du_ngay_trong_va_dinh():
    rows = [bai("2026-10-02T08:00+07:00", bl=4), bai("2026-10-02T09:00+07:00", bl=0),
            bai("2026-10-04T08:00+07:00", bl=1, sac="Tích cực", nid=7, loai="kenh_nha"),
            bai("2026-10-04T09:00+07:00", bl=0, sac="Trung lập")]
    x = CS.tong_hop(rows, D(2026, 10, 1), D(2026, 10, 4), hom_nay=D(2026, 10, 20))["xu_huong"]
    assert x["don_vi"] == "ngày"
    assert x["moc"] == ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    assert x["bai"] == [0, 2, 0, 2]
    assert x["thao_luan"] == [0, 6, 0, 3]
    assert x["kenh_nha"] == [0, 0, 0, 1] and x["trung_lap"] == [0, 0, 0, 1]
    assert x["chua_phan_loai"] == [0, 2, 0, 0]
    assert x["dinh"] == {"moc": "2026-10-02", "thao_luan": 6, "bai": 2}


def test_xu_huong_kep_ve_hom_nay():
    x = CS.xu_huong([], D(2026, 10, 1), D(2026, 10, 31), D(2026, 10, 14))
    assert x["moc"][-1] == "2026-10-14" and len(x["moc"]) == 14
    assert x["dinh"] is None


def test_gom_theo_tuan_khi_dai_hon_92_ngay():
    assert D(2026, 6, 3).weekday() == 2 and D(2026, 6, 8).weekday() == 0   # thứ Tư, thứ Hai
    tu = D(2026, 6, 3)
    # đúng 92 ngày: vẫn theo ngày
    x92 = CS.xu_huong([], tu, tu + datetime.timedelta(days=91), D(2026, 12, 31))
    assert x92["don_vi"] == "ngày" and len(x92["moc"]) == 92
    # 93 ngày: theo tuần, mốc đầu kẹp vào ngày bắt đầu (thứ Tư), sau đó là các thứ Hai
    rows = [bai("2026-06-07T23:00+07:00", bl=2),        # Chủ nhật -> tuần bắt đầu 03/06
            bai("2026-06-08T00:30+07:00"),              # thứ Hai -> tuần 08/06
            bai("2026-06-14T23:59+07:00")]              # Chủ nhật -> tuần 08/06
    x = CS.xu_huong(rows, tu, tu + datetime.timedelta(days=92), D(2026, 12, 31))
    assert x["don_vi"] == "tuần"
    assert x["moc"][:3] == ["2026-06-03", "2026-06-08", "2026-06-15"]
    assert x["bai"][:3] == [1, 2, 0]
    assert x["thao_luan"][:3] == [3, 2, 0]
    assert all(D.fromisoformat(m).weekday() == 0 for m in x["moc"][1:])


def test_top_nguon_theo_thao_luan_moi_nen_tang():
    rows = [bai("2026-10-10T09:00+07:00", nid=1, tk="a", tg="A", bl=5),
            bai("2026-10-10T10:00+07:00", nid=1, tk="a", tg="A", bl=0, xem=10),
            bai("2026-10-10T11:00+07:00", nid=2, tk="b", tg="B", bl=9),
            bai("2026-10-10T12:00+07:00", nid=None, tk="@KhachC", tg="Khách C", bl=1),
            bai("2026-10-10T13:00+07:00", nid=None, tk="khachc", tg="Khách C", bl=1),
            bai("2026-10-10T14:00+07:00", p="youtube", nid=9, tk="", tg="Kênh Y", bl=100,
                xem=5000)]
    top = CS.top_nguon(rows)
    assert [g["nen_tang"] for g in top] == ["youtube", "tiktok"]     # tổng thảo luận 101 > 21
    tk = top[1]
    assert tk["so_nguon"] == 3
    assert [(n["ten"], n["bai"], n["thao_luan"]) for n in tk["nguon"]] == [
        ("B", 1, 10), ("A", 2, 7), ("Khách C", 2, 4)]    # @KhachC ≡ khachc: gộp một tác giả
    assert tk["nguon"][2]["ten_loai"] == "Tìm theo từ khoá"
    assert tk["nguon"][0]["link"] == "https://www.tiktok.com/@b"


def test_sac_thai_theo_chu_de():
    rows = [bai("2026-10-10T09:00+07:00", sac="Tích cực", cd="Giá cả & khuyến mãi"),
            bai("2026-10-10T09:00+07:00", sac="Tiêu cực", cd="Giá cả & khuyến mãi"),
            bai("2026-10-10T09:00+07:00", sac="Tích cực", cd="Chất lượng sản phẩm"),
            bai("2026-10-10T09:00+07:00", sac="Trung lập", cd=None),
            bai("2026-10-10T09:00+07:00", sac=None, cd=""),
            bai("2026-10-10T09:00+07:00", sac="Tích cực", cd="Giá cả & khuyến mãi", nid=5,
                loai="kenh_nha")]                         # kênh nhà: bỏ
    ds = CS.sac_thai_chu_de(rows)
    assert [(g["chu_de"], g["so"]) for g in ds] == [
        ("Giá cả & khuyến mãi", 2), ("Chất lượng sản phẩm", 1), ("chưa phân loại", 2)]
    assert (ds[0]["Tích cực"], ds[0]["Tiêu cực"], ds[0]["Trung lập"]) == (1, 1, 0)
    assert (ds[2]["Trung lập"], ds[2]["chưa phân loại"]) == (1, 1)
    assert CS.sac_thai(rows) == [{"sac_thai": "Tích cực", "so": 2}, {"sac_thai": "Tiêu cực", "so": 1},
                                 {"sac_thai": "Trung lập", "so": 1},
                                 {"sac_thai": "chưa phân loại", "so": 1}]


def test_tu_khoa_bo_chinh_tu_khoa_du_an():
    rows = [bai("2026-10-10T09:00+07:00", nd="Túi xách HAPAS mới về #tuixach",
                ht="hapasvn, tuixach", tk="kol_a", nid=1),
            bai("2026-10-10T10:00+07:00", nd="túi xách hapas quá xinh", ht="hapasvn, fyp",
                tk="kol_b", nid=2),
            bai("2026-10-10T11:00+07:00", nd="Nước hoa thơm lâu", ht="", tk="kol_c", nid=3),
            bai("2026-10-10T12:00+07:00", nd="túi xách nước hoa", nid=9, loai="kenh_nha")]
    tk = CS.tu_khoa(rows, ["Hapas"])
    # '#hapasvn' chứa từ khoá dự án -> bỏ; 'mới về', 'quá xinh' có hư từ -> bỏ; '#fyp' là hashtag
    # đẩy đề xuất; '#tuixach' viết liền đúng từ ghép -> đếm chung với "túi xách" (không thành hai
    # mục); 'nước hoa' chỉ 1 bài khách (bài kênh nhà không tính) -> dưới ngưỡng 2 bài.
    assert [(g["tu"], g["so_bai"]) for g in tk] == [("túi xách", 2)]
    assert [(g["tu"], g["so_bai"]) for g in CS.tu_khoa(rows, [])] == [("#hapasvn", 2),
                                                                      ("túi xách", 2)]


def test_loc_nen_tang_loai_nguon_va_phan_bo():
    rows = [bai("2026-10-10T09:00+07:00", p="tiktok", nid=1, loai="kol", bl=1),
            bai("2026-10-10T09:00+07:00", p="facebook", nid=2, loai="page", bl=5),
            bai("2026-10-10T09:00+07:00", p="facebook", nid=None, bl=0)]
    a, b = D(2026, 10, 10), D(2026, 10, 10)
    assert CS.tong_hop(rows, a, b, nen_tang="facebook", hom_nay=a)["kpi"]["bai"] == 2
    assert CS.tong_hop(rows, a, b, loai_nguon="tu_khoa", hom_nay=a)["kpi"]["bai"] == 1
    th = CS.tong_hop(rows, a, b, hom_nay=a)
    assert [(x["nen_tang"], x["bai"], x["thao_luan"]) for x in th["nen_tang"]] == [
        ("facebook", 2, 7), ("tiktok", 1, 2)]
    assert [(x["loai"], x["thao_luan"]) for x in th["loai_nguon"]] == [
        ("page", 6), ("kol", 2), ("tu_khoa", 1)]


def bl(luc: str, ma: str, *, p="tiktok", nid: int | None = 1, loai_nguon="kol", lb="hop_le",
       sac="Tích cực", cd="Giá", thich=0, nd="ok", tg="Khách", ten=None, bai_tg="KOL A",
       ma_cha=None):
    dt = datetime.datetime.fromisoformat(luc.replace("Z", "+00:00"))
    return {"khoa_bai": f"{p}:1", "ma": ma, "nen_tang": p, "tac_gia": tg, "noi_dung": nd,
            "thich": thich, "tra_loi": 0, "la_tra_loi": bool(ma_cha), "ma_cha": ma_cha,
            "cua_thuong_hieu": lb == "thuong_hieu", "dang_luc": dt, "luc": dt, "sac_thai": sac,
            "chu_de": cd, "loai": lb, "ly_do_loc": None, "link": f"https://x.vn/c/{ma}",
            "nguon_loai": loai_nguon if nid else None, "nguon_id": nid,
            "nguon_ten": ten if nid else None, "bai_link": "https://x.vn/b/1",
            "bai_tac_gia": bai_tg, "bai_noi_dung": "Bài  gốc\n dài", "bai_dang_luc": dt}


def test_the_bl_co_link_bai_nguon_va_cha():
    c = CS.the_bl(bl("2026-10-10T09:00+07:00", "c2", ma_cha="c1", ten="Kênh A"))
    assert c["link"] == "https://x.vn/c/c2" and c["ma_cha"] == "c1" and c["la_tra_loi"]
    assert c["bai"] == {"link": "https://x.vn/b/1", "tac_gia": "KOL A", "noi_dung": "Bài gốc dài",
                        "dang_luc": "2026-10-10T09:00+07:00"}
    assert c["nguon"] == {"khoa": "n:1", "ten": "Kênh A", "loai": "KOL/KOC"}
    # Bài tìm theo từ khoá (không nguồn theo dõi): nguồn = tác giả bài, khoá không phân biệt hoa.
    k = CS.the_bl(bl("2026-10-10T09:00+07:00", "c3", nid=None, bai_tg="Bé Na"))["nguon"]
    assert k["khoa"] == "t:bé na" and k["ten"] == "Bé Na"
    assert CS.khoa_nguon_bl({"bai_tac_gia": " "}) == ("t:?", "Không rõ nguồn")


def test_chi_tiet_bl_loc_theo_truong_va_facets():
    rows = [bl("2026-10-10T09:00+07:00", "a", thich=5, nd="Giá bao nhiêu"),
            bl("2026-10-10T10:00+07:00", "b", sac="Tiêu cực", cd="Giao hàng", thich=1,
               nd="Ship lâu"),
            bl("2026-10-11T09:00+07:00", "c", p="facebook", nid=2, ten="Page B", thich=9),
            bl("2026-10-11T10:00+07:00", "d", lb="spam", thich=50, nd="link bit.ly"),
            bl("2026-10-20T10:00+07:00", "e")]                       # ngoài kỳ
    a, b = D(2026, 10, 10), D(2026, 10, 12)
    x = CS.chi_tiet_bl(rows, a, b)
    assert x["tong"] == 4 and [c["ma"] for c in x["binh_luan"]] == ["d", "c", "a", "b"]
    f = {k: {g["gia_tri"]: g["so"] for g in v} for k, v in x["facets"].items()}
    assert f["nen_tang"] == {"tiktok": 3, "facebook": 1} and f["loai"] == {"hop_le": 3, "spam": 1}
    assert f["sac_thai"] == {"Tích cực": 2, "Tiêu cực": 1}          # spam không có sắc thái
    assert {g["gia_tri"]: g["ten"] for g in x["facets"]["nguon"]} == {"n:1": "KOL A",
                                                                      "n:2": "Page B"}
    # Lọc một trường: facet của CHÍNH trường đó vẫn đếm đủ để chọn sang giá trị khác.
    y = CS.chi_tiet_bl(rows, a, b, nen_tang="tiktok", loai="hop_le", sap_xep="moi")
    assert [c["ma"] for c in y["binh_luan"]] == ["b", "a"]
    fy = {k: {g["gia_tri"]: g["so"] for g in v} for k, v in y["facets"].items()}
    assert fy["nen_tang"] == {"tiktok": 2, "facebook": 1} and fy["loai"] == {"hop_le": 2, "spam": 1}
    assert [c["ma"] for c in CS.chi_tiet_bl(rows, a, b, q="gia BAO", sap_xep="cu")["binh_luan"]] \
        == ["a"]                                                      # tìm bỏ dấu, không hoa
    assert CS.chi_tiet_bl(rows, a, b, nguon="n:2")["tong"] == 1
    assert CS.chi_tiet_bl(rows, a, b, chu_de="Giao hàng")["binh_luan"][0]["ma"] == "b"
    z = CS.chi_tiet_bl(rows, a, b, moi_trang=3, trang=9)
    assert (z["trang"], z["so_trang"], len(z["binh_luan"])) == (2, 2, 1)


def test_xep_theo_luong_tra_loi_ngay_duoi_cha():
    rows = [bl("2026-10-10T09:00+07:00", "g1", thich=5),
            bl("2026-10-10T09:05+07:00", "g2", thich=9),
            bl("2026-10-10T10:00+07:00", "r1b", ma_cha="g1"),
            bl("2026-10-10T09:30+07:00", "r1a", ma_cha="g1"),
            bl("2026-10-10T11:00+07:00", "r1a1", ma_cha="r1a"),
            bl("2026-10-10T12:00+07:00", "mo_coi", ma_cha="khong_co", thich=1),
            bl("2026-10-10T12:00+07:00", "vong_a", ma_cha="vong_b"),
            bl("2026-10-10T12:00+07:00", "vong_b", ma_cha="vong_a")]
    ra = [c["ma"] for c in CS.xep_theo_luong(rows)]
    assert ra[:6] == ["g2", "g1", "r1a", "r1a1", "r1b", "mo_coi"]
    assert sorted(ra) == sorted(c["ma"] for c in rows)           # vòng cha-con lỗi: không mất


def test_gan_ngu_canh_bai_chi_cho_dong_da_chon():
    c = bl("2026-10-10T09:00+07:00", "a")
    for k in ("bai_link", "bai_noi_dung", "bai_dang_luc"):
        c.pop(k)
    ds = [CS.the_bl(c)]
    assert ds[0]["bai"]["link"] == ""
    dt = datetime.datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
    CS.gan_ngu_canh_bai(ds, {"tiktok:1": {"bai_link": "https://x.vn/b/9",
                                          "bai_noi_dung": " Bài\n mới ", "bai_dang_luc": dt}})
    assert ds[0]["bai"] == {"link": "https://x.vn/b/9", "tac_gia": "KOL A", "noi_dung": "Bài mới",
                            "dang_luc": "2026-10-09T15:00+07:00"}


def test_tu_khoa_thao_luan_gom_bai_va_bl_hop_le():
    a = D(2026, 10, 10)
    b_ = [bai("2026-10-10T09:00+07:00", nd="nước hoa thơm"),
          bai("2026-10-10T09:00+07:00", nd="nước hoa", nid=9, loai="kenh_nha")]
    c = [bl("2026-10-10T10:00+07:00", "a", nd="nước hoa đẹp"),
         bl("2026-10-10T10:00+07:00", "b", nd="nước hoa rẻ", lb="spam")]
    r = CS.tu_khoa_thao_luan(b_, c, a, a)
    assert r["tong"] == 2                       # 1 bài khách + 1 bình luận hợp lệ
    assert [(g["tu"], g["so_bai"]) for g in r["tu_khoa"]] == [("nước hoa", 2)]


def test_top_bai_theo_thao_luan_roi_luot_xem():
    rows = [bai("2026-10-10T09:00+07:00", bl=5, xem=1, link="https://a/1", nd="  một\n hai "),
            bai("2026-10-10T09:00+07:00", bl=5, xem=9, link="https://a/2"),
            bai("2026-10-10T09:00+07:00", bl=7, xem=0, link="https://a/3")]
    top = CS.top_bai(rows)
    assert [b["link"] for b in top] == ["https://a/3", "https://a/2", "https://a/1"]
    assert top[2]["noi_dung"] == "một hai" and top[0]["thao_luan"] == 8
    assert top[0]["dang_luc"] == "2026-10-10T09:00+07:00"


# ───────────────────────── bộ lọc chung (đợt 2f) ─────────────────────────
def test_doc_bo_loc_chuan_hoa_va_tu_choi():
    rong = CS.doc_bo_loc({})
    assert rong == {"pham_vi": "tat_ca", "nen_tang": (), "loai": (), "nguon": (), "sac_thai": (),
                    "chu_de": (), "anh_huong": (), "tuong_tac": 0, "q": "", "kieu_quet": "",
                    "y_dinh": "", "gom_mg": ""}
    b = CS.doc_bo_loc({"nen_tang": "tiktok,facebook,tiktok", "sac_thai": "tieu_cuc,Tích cực",
                       "tuong_tac": "1.000", "q": "  túi   xách ",
                       "nguon": "n:1,tiktok:khach, a,n:2", "loai": "kol"})
    assert b["nen_tang"] == ("facebook", "tiktok") and b["loai"] == ("kol",)
    assert b["sac_thai"] == ("Tiêu cực", "Tích cực")          # mã URL hay nhãn đều về nhãn kho
    assert b["tuong_tac"] == 1000 and b["q"] == "túi xách"
    assert b["nguon"] == ("n:1", "n:2", "tiktok:khach, a")     # tên có dấu phẩy không bị cắt
    for sai in ({"pham_vi": "nha"}, {"nen_tang": "threads"}, {"loai": "vip"},
                {"sac_thai": "vui"}, {"tuong_tac": "50"}, {"kieu_quet": "x"}, {"q": "x" * 101},
                {"anh_huong": "khong_lo"}, {"nguon": ",".join(f"n:{i}" for i in range(51))},
                {"chu_de": "x" * 101}, {"y_dinh": "2"}, {"gom_mg": "co"}):
        with pytest.raises(CS.LoiBoLoc):
            CS.doc_bo_loc(sai)
    # JSON cho trình duyệt -> tham số URL -> đọc lại: không đổi.
    j = CS.bo_loc_json(b)
    assert j["sac_thai"] == ["tieu_cuc", "tich_cuc"] and j["tuong_tac"] == "1000"
    assert CS.bo_loc_json(rong)["tuong_tac"] == ""
    url = {k: ",".join(v) if isinstance(v, list) else v for k, v in j.items()}
    assert CS.doc_bo_loc(url) == b
    assert CS.khoa_bo_loc(b) != CS.khoa_bo_loc(rong)
    # Bộ lọc nhanh là DỮ LIỆU: mục nào cũng đọc được, mã không trùng.
    assert len({p["ma"] for p in CS.BO_LOC_NHANH}) == len(CS.BO_LOC_NHANH) >= 6
    for p in CS.BO_LOC_NHANH:
        assert CS.doc_bo_loc(p["loc"]) != rong, p["ma"]
    # "Khách hỏi mua" (16/10/2026) = đúng định nghĩa ô Ý định mua, không chỉ theo chủ đề AI.
    hoi_mua = next(p for p in CS.BO_LOC_NHANH if p["ma"] == "hoi_mua")
    assert hoi_mua["loc"] == {"y_dinh": "1"} and CS.CHU_DE_MUA in CS.CHU_DE_BL


def test_loc_nhanh_ngoai_theo_doi_bo_bai_cua_nguon_da_xoa():
    """Bài của nguồn đã xoá: nguon_id NULL nhưng kieu_quet vẫn theo_doi — không phải "nguồn mới"."""
    moi = bai("2026-10-10T09:00+07:00", nid=None, tk="moi")              # tìm theo từ khoá
    da_xoa = bai("2026-10-10T09:00+07:00", nid=None, tk="cu")
    da_xoa["kieu_quet"] = "theo_doi"
    theo_doi = bai("2026-10-10T09:00+07:00", nid=1, tk="kol")
    p = next(x for x in CS.BO_LOC_NHANH if x["ma"] == "ngoai_theo_doi")
    assert [r["tai_khoan"] for r in CS.loc_bai([moi, da_xoa, theo_doi],
                                               CS.doc_bo_loc(p["loc"]))] == ["moi"]


def test_khoa_nguon_link_dai_van_loc_duoc():
    """Bài không tác giả/tài khoản: khoá nguồn = "link:" + link (kho cắt 500) — 505 ký tự."""
    r = bai("2026-10-10T09:00+07:00", nid=None, tk="", tg="", link="https://x.vn/" + "a" * 487)
    k = CS.khoa_nguon_chu(r)
    assert len(k) == 505 and len(k) <= CS.NGUON_TOI_DA_KY_TU
    assert CS.loc_bai([r, bai("2026-10-10T09:00+07:00")], CS.doc_bo_loc({"nguon": k})) == [r]
    with pytest.raises(CS.LoiBoLoc):
        CS.doc_bo_loc({"nguon": "link:" + "a" * CS.NGUON_TOI_DA_KY_TU})


def test_loc_theo_tuong_tac_khong_so_phan_tram_ky_truoc():
    """Tương tác cộng dồn trọn đời bài: lọc "từ N tương tác" ưu ái bài cũ — không hiện % lệch."""
    rows = [bai("2026-10-10T09:00+07:00", thich=200, tk="nay"),
            bai("2026-10-02T09:00+07:00", thich=900, tk="truoc1"),
            bai("2026-10-03T09:00+07:00", thich=150, tk="truoc2")]
    a, b = D(2026, 10, 8), D(2026, 10, 14)
    th = CS.tong_hop(rows, a, b, hom_nay=b, bo_loc=CS.doc_bo_loc({"tuong_tac": "100"}))
    assert th["so_sanh_lech"] == "tuong_tac"
    assert th["so_sanh"]["bai"] == {"nay": 1, "truoc": 2, "doi_pt": None}
    assert all(v["doi_pt"] is None for v in th["so_sanh"].values())
    th = CS.tong_hop(rows, a, b, hom_nay=b)
    assert th["so_sanh_lech"] is None and th["so_sanh"]["bai"]["doi_pt"] == -50.0


def test_nhan_chu_de_khop_mark():
    import phan_loai
    assert CS.CHU_DE_BAI == tuple(phan_loai.CHU_DE_BAI.values())
    # Chủ đề MG ("Minigame/bài dự thi", 16/10/2026) có ở cả Mark lẫn dashboard: khớp đúng từng chữ
    # và đúng thứ tự — dashboard ẩn minigame khỏi mây theo đúng nhãn này.
    assert CS.CHU_DE_BL == tuple(phan_loai.CHU_DE.values())
    assert phan_loai.CHU_DE["MG"] == CS.CHU_DE_MINIGAME and CS.nhom_chu_de(CS.CHU_DE_MINIGAME) == "bl"
    assert CS.nhom_chu_de("Giá/mua ở đâu/ý định mua") == "bl"
    assert CS.nhom_chu_de("Giá cả & khuyến mãi") == "bai"
    assert CS.nhom_chu_de("Khác") == CS.nhom_chu_de(CS.CHUA) == "chung"
    assert CS.nhom_chu_de("Nhãn cũ lạ") == "bai"


def _bon_bai():
    a = bai("2026-10-10T09:00+07:00", nid=1, bl=30, thich=50, cs=30, sac="Tích cực",
            cd="Giá cả & khuyến mãi", tk="kol_a", nd="Túi xách HAPAS đẹp")     # tương tác 110
    a["followers"] = 5_000                                                         # nano
    b = bai("2026-10-10T10:00+07:00", p="facebook", nid=2, loai="kenh_nha", thich=20_000,
            sac="Tiêu cực", cd="Khác", tk="hapas")                                 # 20.000
    b["followers"] = 2_000_000                                                     # mega
    c = bai("2026-10-10T11:00+07:00", nid=None, bl=2, thich=3, sac="Tiêu cực", cd="Khác",
            tk="khach_c", nd="giá hơi cao", ht="tuixach")                          # 5, không rõ
    d = bai("2026-10-10T12:00+07:00", p="youtube", nid=3, loai="page", bl=500, thich=1000,
            tk="kenh_d")                                                           # 1.500
    d.update(followers=150_000, kieu_quet="tu_khoa")       # tài khoản theo dõi, tìm qua từ khoá
    return [a, b, c, d]


def test_bo_loc_moi_chieu_tren_bai():
    rows = _bon_bai()

    def L(**q):
        return [r["tai_khoan"] for r in CS.loc_bai(rows, CS.doc_bo_loc(q))]
    assert L() == ["kol_a", "hapas", "khach_c", "kenh_d"]
    assert L(pham_vi="kenh_nha") == ["hapas"]
    assert L(pham_vi="ben_ngoai") == ["kol_a", "khach_c", "kenh_d"]   # gồm bài tìm theo từ khoá
    assert L(nen_tang="tiktok,youtube") == ["kol_a", "khach_c", "kenh_d"]
    assert L(nen_tang="facebook") == ["hapas"]                          # kiểu cũ một giá trị
    assert L(loai="tu_khoa,kenh_nha") == ["hapas", "khach_c"]
    assert L(nguon="n:1,tiktok:khach_c") == ["kol_a", "khach_c"]
    # Sắc thái: bài kênh nhà không mang tiếng khách — "Tiêu cực" của nó không khớp.
    assert L(sac_thai="tieu_cuc") == L(sac_thai="Tiêu cực") == ["khach_c"]
    assert L(sac_thai="chua_phan_loai") == ["kenh_d"]
    # Chủ đề: nhãn bài lọc bài; nhãn chỉ của bình luận để phần bài nguyên.
    assert L(chu_de="Giá cả & khuyến mãi") == ["kol_a"]
    assert L(chu_de="Khác") == ["khach_c"]
    assert L(chu_de="chưa phân loại") == ["kenh_d"]
    assert L(chu_de="Giá/mua ở đâu/ý định mua") == L()
    assert L(anh_huong="nano,khong_ro") == ["kol_a", "khach_c"]
    assert (L(anh_huong="mega"), L(anh_huong="macro")) == (["hapas"], ["kenh_d"])
    assert L(tuong_tac="100") == ["kol_a", "hapas", "kenh_d"]
    assert L(tuong_tac="1000") == ["hapas", "kenh_d"] and L(tuong_tac="10000") == ["hapas"]
    assert L(kieu_quet="tu_khoa") == ["khach_c", "kenh_d"]
    assert L(kieu_quet="theo_doi") == ["kol_a", "hapas"]
    assert L(q="tuixach") == ["khach_c"]                                # hashtag
    assert L(q="TUI XACH") == ["kol_a"] and L(q="gia hoi") == ["khach_c"]   # bỏ dấu, không hoa
    assert L(pham_vi="ben_ngoai", nen_tang="tiktok", sac_thai="tieu_cuc") == ["khach_c"]  # AND
    for f, muc in ((None, "khong_ro"), (0, "khong_ro"), (9_999, "nano"), (10_000, "micro"),
                   (999_999, "macro"), (1_000_000, "mega")):
        assert CS.muc_anh_huong({"followers": f}) == muc, f


def _ba_bai_nam_bl():
    p1 = bai("2026-10-09T09:00+07:00", nid=1, thich=1500, bl=400, tk="kol_a", nd="Review túi mới")
    p1["followers"] = 50_000                                     # micro, tương tác 1.900
    p2 = bai("2026-10-09T10:00+07:00", p="facebook", nid=2, loai="kenh_nha", thich=40, bl=10,
             tk="hapas", nd="Ra mắt bộ sưu tập")                 # không rõ follower, 50
    p3 = bai("2026-10-09T11:00+07:00", nid=None, thich=5, bl=5, tk="khach", nd="đẹp ghê")  # 10

    def c(ma, p, **kw):
        x = bl("2026-10-10T09:00+07:00", ma, p=p["nen_tang"], nid=p["nguon_id"],
               loai_nguon=p["nguon_loai"] or "kol", **kw)
        x["khoa_bai"] = p["khoa"]
        return x
    cs = [c("c1", p1, sac="Tiêu cực", cd="Giao hàng/dịch vụ", nd="ship chậm"),
          c("c2", p1, sac="Tích cực", cd="Giá/mua ở đâu/ý định mua", nd="giá bao nhiêu"),
          c("c3", p2, sac="Tiêu cực", cd="Sản phẩm/chất lượng", nd="hàng lỗi"),
          c("c4", p2, lb="spam", sac="Tiêu cực", nd="link rẻ"),
          c("c5", p3, sac="Trung lập", cd="Khác", nd="xinh")]
    return [p1, p2, p3], cs


def test_bo_loc_tren_binh_luan_theo_bai_va_theo_chinh_no():
    bai_ds, cs = _ba_bai_nam_bl()
    idx = CS.chi_muc_bai(bai_ds)

    def M(_idx=idx, **q):
        return [x["ma"] for x in CS.loc_bl(cs, CS.doc_bo_loc(q), _idx)]
    assert M(pham_vi="kenh_nha") == ["c3", "c4"]                  # theo phạm vi của BÀI
    assert M(pham_vi="ben_ngoai") == ["c1", "c2", "c5"]
    assert M(nen_tang="facebook") == ["c3", "c4"] and M(loai="tu_khoa") == ["c5"]
    assert M(sac_thai="tieu_cuc") == ["c1", "c3"]                 # sắc thái CỦA bình luận; spam loại
    assert M(chu_de="Giá/mua ở đâu/ý định mua") == ["c2"]
    assert M(chu_de="Giá cả & khuyến mãi") == ["c1", "c2", "c3", "c4", "c5"]   # nhãn bài: không lọc
    assert M(chu_de="Khác") == ["c5"]
    assert M(anh_huong="micro") == ["c1", "c2"] and M(anh_huong="khong_ro") == ["c3", "c4", "c5"]
    assert M(tuong_tac="1000") == M(tuong_tac="100") == ["c1", "c2"]
    assert M(kieu_quet="tu_khoa") == ["c5"]
    assert M(nguon="tiktok:khach") == ["c5"]
    assert M(nguon="n:2") == M(None, nguon="n:2") == ["c3", "c4"]   # nguồn theo dõi: không cần bài
    # Chữ tìm: bình luận khớp khi chính nó HOẶC bài của nó chứa chữ.
    assert M(q="review") == ["c1", "c2"] and M(q="hang loi") == ["c3"]
    assert M(q="ra mat") == ["c3", "c4"]
    assert M(None, anh_huong="micro") == []                       # thiếu bài gốc: không đoán
    assert CS.can_tra_bai(CS.doc_bo_loc({"anh_huong": "micro"}))
    assert CS.can_tra_bai(CS.doc_bo_loc({"nguon": "tiktok:khach"}))
    assert CS.can_tra_bai(CS.doc_bo_loc({"q": "x"}))
    assert not CS.can_tra_bai(CS.doc_bo_loc({"pham_vi": "kenh_nha", "sac_thai": "tieu_cuc",
                                             "nguon": "n:1"}))
    assert CS.khoa_bai_thieu(cs, CS.chi_muc_bai(bai_ds[:1])) == [bai_ds[1]["khoa"],
                                                                bai_ds[2]["khoa"]]


def test_bo_loc_ap_ca_ky_truoc_va_khung_chi_tiet():
    rows = [bai("2026-10-10T09:00+07:00", nid=7, loai="kenh_nha", bl=4, tk="nha1"),
            bai("2026-10-11T09:00+07:00", nid=1, bl=1, tk="ngoai1"),
            bai("2026-10-02T09:00+07:00", nid=7, loai="kenh_nha", tk="nha2"),      # kỳ trước
            bai("2026-10-03T09:00+07:00", nid=7, loai="kenh_nha", tk="nha3")]      # kỳ trước
    a, b = D(2026, 10, 8), D(2026, 10, 14)
    th = CS.tong_hop(rows, a, b, hom_nay=b, bo_loc=CS.doc_bo_loc({"pham_vi": "kenh_nha"}))
    assert th["kpi"]["bai"] == 1 and th["kpi"]["thao_luan"] == 5
    assert th["so_sanh"]["bai"] == {"nay": 1, "truoc": 2, "doi_pt": -50.0}
    assert [n["khoa_nguon"] for g in th["top_nguon"] for n in g["nguon"]] == ["n:7"]
    ngoai = CS.tong_hop(rows, a, b, hom_nay=b, bo_loc=CS.doc_bo_loc({"pham_vi": "ben_ngoai"}))
    assert ngoai["so_sanh"]["bai"] == {"nay": 1, "truoc": 0, "doi_pt": None}
    # Khung chi tiết: bộ lọc chung AND điều kiện của điểm vừa bấm.
    bon = _bon_bai()
    d = D(2026, 10, 10)
    x = CS.chi_tiet_bai(bon, d, d, bo_loc=CS.doc_bo_loc({"pham_vi": "ben_ngoai"}),
                        sac_thai="Tiêu cực")
    assert x["tong"] == 1 and x["bai"][0]["khoa"] == bon[2]["khoa"]
    bai_ds, cs = _ba_bai_nam_bl()
    y = CS.chi_tiet_bl(cs, d, d, bo_loc=CS.doc_bo_loc({"pham_vi": "kenh_nha"}),
                       bai_theo_khoa=CS.chi_muc_bai(bai_ds))
    assert y["tong"] == 2
    assert {g["gia_tri"]: g["so"] for g in y["facets"]["loai"]} == {"hop_le": 1, "spam": 1}
    assert CS.chi_tiet_bl(cs, d, d, loai="hop_le",
                          bo_loc=CS.doc_bo_loc({"pham_vi": "kenh_nha"}))["tong"] == 1
    # Mây từ khoá + khối bình luận cùng bộ lọc.
    tk = CS.tu_khoa_thao_luan(bai_ds, cs, D(2026, 10, 9), d,
                              bo_loc=CS.doc_bo_loc({"pham_vi": "ben_ngoai"}))
    assert tk["tong"] == 2 + 3                       # p1, p3 + c1, c2, c5 (hợp lệ, bên ngoài)
    k = CS.tong_hop_bl(cs, d, d, hom_nay=d, bo_loc=CS.doc_bo_loc({"sac_thai": "tieu_cuc"}))["kpi"]
    assert (k["so"], k["tieu_cuc"], k["tich_cuc"]) == (2, 2, 0)


def test_dem_o_loc_bo_qua_chinh_chieu_va_kenh_nha_vs_ben_ngoai():
    a = bai("2026-10-10T09:00+07:00", nid=1, bl=2, sac="Tích cực", tk="a")              # 3 TL
    c = bai("2026-10-10T09:00+07:00", nid=None, sac="Tiêu cực", tk="c")                 # 1
    d = bai("2026-10-10T09:00+07:00", p="facebook", nid=4, bl=1, sac="Trung lập", tk="d")
    e = bai("2026-10-10T09:00+07:00", nid=7, loai="kenh_nha", bl=5, tk="e")             # 6
    b = bai("2026-10-10T09:00+07:00", p="facebook", nid=2, loai="kenh_nha", tk="b")

    def cmt(ma, p, **kw):
        x = bl("2026-10-10T10:00+07:00", ma, p=p["nen_tang"], nid=p["nguon_id"],
               loai_nguon=p["nguon_loai"] or "kol", **kw)
        x["khoa_bai"] = p["khoa"]
        return x
    cs = [cmt("k1", e, sac="Tiêu cực"), cmt("k2", e, sac="Tích cực"), cmt("k3", a),
          cmt("k4", d, lb="spam")]
    dd = D(2026, 10, 10)
    kq = CS.tong_quan_loc([a, c, d, e, b], cs, dd, dd,
                          CS.doc_bo_loc({"nen_tang": "tiktok", "pham_vi": "ben_ngoai"}))
    dem = kq["bo_loc_dem"]
    # Ô nền tảng bỏ qua CHÍNH nó (vẫn thấy Facebook để chọn thêm) nhưng giữ phạm vi bên ngoài.
    assert dem["nen_tang"] == {"tiktok": 2, "facebook": 1}
    assert dem["pham_vi"] == {"ben_ngoai": 2, "kenh_nha": 1}         # b trượt 2 chiều: không đếm
    assert dem["loai"] == {"kol": 1, "tu_khoa": 1}
    assert dem["kieu_quet"] == {"theo_doi": 1, "tu_khoa": 1}
    assert dem["sac_thai"]["tich_cuc"] == {"bai": 1, "bl": 1}
    assert dem["sac_thai"]["tieu_cuc"] == {"bai": 1, "bl": 0}        # k1 ở kênh nhà: trượt phạm vi
    assert sorted((x["gia_tri"], x["so"]) for x in dem["nguon"]) == [("n:1", 1), ("tiktok:c", 1)]
    nha, ngoai = kq["nha_ngoai"]["kenh_nha"], kq["nha_ngoai"]["ben_ngoai"]
    assert (nha["bai"], nha["thao_luan"], nha["bl"], nha["bl_hop_le"]) == (1, 6, 2, 2)
    assert (nha["sac_bl"]["tieu_cuc"], nha["sac_bl"]["tich_cuc"]) == (1, 1)
    assert nha["sac_bai"] == dict.fromkeys(CS.MA_SAC, 0)               # bài thương hiệu: không tính
    assert (ngoai["bai"], ngoai["thao_luan"], ngoai["bl"]) == (2, 4, 1)
    assert (ngoai["sac_bai"]["tich_cuc"], ngoai["sac_bai"]["tieu_cuc"]) == (1, 1)
    assert ngoai["sac_bl"]["tich_cuc"] == 1


# ───────────────────────── làm sạch số liệu (16/10/2026) ─────────────────────────
def test_tu_khoa_chu_kieu_cach_khong_bi_cat_dau():
    """Rà 15/10: "max cuo", "pii la", "ra ma" trên mây — dấu rời của chữ kiểu cách cắt chữ."""
    nd = "𝐃𝐚́𝐧 𝐦𝐚𝐱 𝐜𝐮𝐨̂́𝐢 𝐯𝐚̀𝐨 𝐬𝐨̣̂𝐩-𝐩𝐢𝐢 𝐥𝐚̀ 𝐫𝐚 𝐦𝐚̂̃𝐮"
    cum = CS._cum({"noi_dung": nd})
    assert "max cuối" in cum and not {"max cuo", "pii la", "ra ma"} & cum


def test_tu_khoa_gop_bien_the_teen_code_va_bo_cau_hoi_gia():
    a = D(2026, 10, 10)
    nd = ["Mk xin giá ak, giá sét túi trắng", "xin gia set tui trang", "giá bn shop, set túi trắng",
          "xin giá shop ơi", "Xin giá set túi trắng", "giá shop ạ"]
    c = [bl("2026-10-10T10:00+07:00", f"c{i}", nd=t, tg=f"Khách {i}") for i, t in enumerate(nd)]
    tk = {g["tu"]: g["so_bai"] for g in CS.tu_khoa_thao_luan([], c, a, a)["tu_khoa"]}
    # Mảnh câu hỏi giá (đã đếm ở Ý định mua) không lên mây; "mk xin" = "mình xin" là hư từ. Chủ dự
    # án 16/10: "giá set", "set giá" cũng là mảnh câu hỏi giá — "giá" chỉ ghép với lời đánh giá.
    assert not {"xin giá", "xin gia", "giá ak", "giá ạ", "giá bn", "giá shop", "mk xin",
                "mình xin", "giá bao", "giá set", "giá sét", "gia set"} & set(tk)
    # Biến thể có/không dấu + "sét"/"set" gộp một nhóm, hiện bằng mặt chữ gặp nhiều nhất.
    assert tk["set túi"] == 3 and tk["túi trắng"] == 3      # "tui" gõ không dấu là đại từ "tui"
    assert CS._cum({"noi_dung": "set giá bao nhiêu, giá rẻ mà giá tốt"}) == {"giá rẻ", "giá tốt"}
    m = [bl("2026-10-10T10:00+07:00", f"m{i}", nd=t, tg=f"Khách {i}")
         for i, t in enumerate(("màu đen đẹp", "mau den sang", "Màu đen nha"))]
    tk = {g["tu"]: g["so_bai"] for g in CS.tu_khoa_thao_luan([], m, a, a)["tu_khoa"]}
    assert tk == {"màu đen": 3}                    # "mau den" (không dấu) vào cùng nhóm
    # Khách gõ không dấu: "shop oi" là hư từ như "shop ơi".
    assert CS._cum({"noi_dung": "dep qua shop oi"}) == set()
    assert CS._cum({"noi_dung": "túi da mềm"}) == {"túi da", "da mềm"}   # "da" không phải hư từ
    # Review 16/10: "giá" so trên mặt chữ — "giả" (hàng giả) không bị bỏ như "giá".
    assert CS._cum({"noi_dung": "sp giả, shop giả"}) == {"sp giả", "shop giả"}
    assert CS._cum({"noi_dung": "báo giá, giá shop, gia sp"}) == set()
    g = [bl("2026-10-10T10:00+07:00", f"g{i}", nd="sp giả nhiều quá", tg=f"Khách {i}")
         for i in range(2)]
    assert {x["tu"] for x in CS.tu_khoa_thao_luan([], g, a, a)["tu_khoa"]} >= {"sp giả"}


def test_ngan_tu_khoa_dem_binh_luan_nhu_may_tu():
    """Ngăn từ khoá (cum) khớp đúng như mây đếm: theo cụm, KHÔNG theo tên tác giả, gộp có/không dấu.
    Trước đây ngăn tìm chữ (q_bl) trên cả tên tác giả: "xin gia" 6 trên mây, 190 trong ngăn."""
    a = D(2026, 10, 10)
    c = [bl("2026-10-10T10:00+07:00", "c1", nd="set túi trắng đẹp", tg="Lan"),
         bl("2026-10-10T10:00+07:00", "c2", nd="SET TÚI trang", tg="Hoa"),
         bl("2026-10-10T10:00+07:00", "c3", nd="túi trắng", tg="Set Túi Store"),   # chỉ tên
         bl("2026-10-10T10:00+07:00", "c4", nd="set túi", lb="spam")]
    tk = {g["tu"]: g["so_bai"] for g in CS.tu_khoa_thao_luan([], c, a, a)["tu_khoa"]}
    assert tk["set túi"] == 2
    x = CS.chi_tiet_bl(c, a, a, cum="set túi", loai="hop_le")
    assert x["tong"] == 2 and {b["ma"] for b in x["binh_luan"]} == {"c1", "c2"}
    assert CS.chi_tiet_bl(c, a, a, cum="set tui", loai="hop_le")["tong"] == 2
    # Ô tìm của luồng vẫn tìm cả tác giả, giờ thêm teen code.
    assert CS.chi_tiet_bl(c, a, a, q="set túi")["tong"] == 4
    c.append(bl("2026-10-10T10:00+07:00", "c5", nd="mk xin giá"))
    assert [b["ma"] for b in CS.chi_tiet_bl(c, a, a, q="mình xin")["binh_luan"]] == ["c5"]
    # Chữ tìm chung (q) của bộ lọc chung cũng qua teen code.
    assert [b["ma"] for b in CS.loc_bl(c, CS.doc_bo_loc({"q": "minh xin"}))] == ["c5"]


def test_la_y_dinh_mua():
    def c(nd, cd=None, lb="hop_le"):
        return {"noi_dung": nd, "chu_de": cd, "loai": lb}
    for nd in ("Xin giá ạ", "giá bn", "Bn ạ", "Ib", "ib mình nhé", "Màu đen còn không shop?",
               "Có ship COD về Đà Nẵng không ạ", "Giá?", "mua ở đâu vậy", "cho mình xin link",
               "size m còn không", "mk xin giá sét túi trắng", "shop ơi còn hàng không"):
        assert CS.la_y_dinh_mua(c(nd)), nd
    for nd in ("Túi đẹp quá", "Ship lâu quá, đặt 5 ngày chưa nhận", "giá rẻ quá",
               "con không thích màu này", "bao nhiêu tuổi rồi", "đặt hàng 5 ngày chưa nhận"):
        assert not CS.la_y_dinh_mua(c(nd)), nd
    assert CS.la_y_dinh_mua(c("Giá hơi cao so với chất liệu", cd=CS.CHU_DE_MUA))   # theo chủ đề AI
    assert not CS.la_y_dinh_mua(c("Xin giá", lb="spam"))                             # chỉ hợp lệ
    assert not CS.la_y_dinh_mua(c("ib", lb="thuong_hieu"))


def test_y_dinh_mua_kpi_ky_truoc_top_bai_va_bo_loc():
    a, b = D(2026, 10, 8), D(2026, 10, 14)

    def x(luc, ma, nd, khoa="tiktok:1", p="tiktok", **kw):
        r = bl(luc, ma, nd=nd, p=p, cd="Khác", **kw)
        r["khoa_bai"] = khoa
        return r
    nay = [x("2026-10-10T09:00+07:00", "a", "xin giá"),
           x("2026-10-10T10:00+07:00", "b", "giá bn"),
           x("2026-10-11T10:00+07:00", "c", "túi đẹp"),
           x("2026-10-12T10:00+07:00", "d", "ib", khoa="facebook:2", p="facebook", nid=2),
           x("2026-10-12T11:00+07:00", "e", "xin giá", lb="spam")]                # spam: không tính
    truoc = [x("2026-10-03T10:00+07:00", "t", "mua ở đâu")]
    y = CS.y_dinh_mua(nay, a, b, rows_truoc=truoc, hom_nay=b)
    assert (y["so"], y["sach"], y["pt"], y["truoc"], y["doi_pt"]) == (3, 4, 75.0, 1, 200.0)
    assert (y["theo_chu_de"], y["theo_cau"]) == (0, 3)
    assert y["xu_huong"]["moc"][2] == "2026-10-10" and y["xu_huong"]["so"][2:5] == [2, 0, 1]
    assert y["xu_huong"]["sach"][2:5] == [2, 1, 1]
    assert [(t["khoa_bai"], t["so"], t["sach"]) for t in y["top_bai"]] == [
        ("tiktok:1", 2, 3), ("facebook:2", 1, 1)]
    # Kỳ trước 0 → không bịa %; kỳ trước bị cắt dòng / lọc tương tác → không so.
    assert CS.y_dinh_mua(nay, a, b, rows_truoc=[], hom_nay=b)["doi_pt"] is None
    assert CS.y_dinh_mua(nay, a, b, rows_truoc=truoc, truoc_bi_cat=True, hom_nay=b)["doi_pt"] is None
    assert CS.y_dinh_mua(nay, a, b, rows_truoc=truoc, nay_bi_cat=True, hom_nay=b)["doi_pt"] is None
    # Review 16/10: đang lọc y_dinh=1 thì mẫu số vẫn là MỌI bình luận sạch (không luôn 100%).
    yy = CS.y_dinh_mua(nay, a, b, rows_truoc=truoc, hom_nay=b,
                       bo_loc=CS.doc_bo_loc({"y_dinh": "1"}))
    assert (yy["so"], yy["sach"], yy["pt"]) == (3, 4, 75.0) and yy["pt"] < 100
    assert yy["top_bai"][0]["sach"] == 3 and yy["xu_huong"]["sach"][2:5] == [2, 1, 1]
    f_yd = CS.bien_dich(CS.doc_bo_loc({"y_dinh": "1"}))
    assert not f_yd.rong and f_yd.bo_y_dinh().rong and f_yd.yd                # bản sao, gốc giữ
    # Theo bộ lọc chung (cả kỳ trước): chỉ Facebook.
    f = CS.doc_bo_loc({"nen_tang": "facebook"})
    yf = CS.y_dinh_mua(nay, a, b, rows_truoc=truoc, hom_nay=b, bo_loc=f)
    assert (yf["so"], yf["sach"], yf["truoc"]) == (1, 1, 0)
    # Chiều lọc y_dinh: chỉ bình luận ý định mua (bài không đổi) — bộ lọc nhanh "Khách hỏi mua".
    hm = CS.doc_bo_loc(next(p for p in CS.BO_LOC_NHANH if p["ma"] == "hoi_mua")["loc"])
    assert sorted(c["ma"] for c in CS.loc_bl(nay, hm)) == ["a", "b", "d"]
    assert CS.loc_bai([bai("2026-10-10T09:00+07:00")], hm) != []
    assert CS.chi_tiet_bl(nay, a, b, y_dinh=True, khoa_bai="tiktok:1")["tong"] == 2
    CS.gan_ngu_canh_y_dinh(y["top_bai"], {"tiktok:1": {
        "bai_link": "https://x.vn/b/1", "bai_noi_dung": " Bài\n gốc ",
        "bai_dang_luc": datetime.datetime(2026, 10, 9, 8, 0, tzinfo=UTC)}})
    assert y["top_bai"][0]["link"] == "https://x.vn/b/1" and y["top_bai"][0]["noi_dung"] == "Bài gốc"


def test_nhan_hien_thi_internal_external_channel():
    """Chủ dự án 16/10/2026: nhãn hiển thị tiếng Anh; giá trị lưu + tham số URL không đổi."""
    assert CS.PHAM_VI == {"tat_ca": "Tất cả", "kenh_nha": "Internal channel",
                          "ben_ngoai": "External channel"}
    assert CS.TEN_LOAI["kenh_nha"] == "Internal channel"
    ten = {p["ma"]: p["ten"] for p in CS.BO_LOC_NHANH}
    assert ten["kenh_nha"] == "Internal channel" and ten["ben_ngoai"] == "External channel"
    assert not any("kênh nhà" in (p["ten"] + p["mo_ta"]).lower() or
                   "bên ngoài" in (p["ten"] + p["mo_ta"]).lower() for p in CS.BO_LOC_NHANH)
    assert CS.doc_bo_loc({"pham_vi": "kenh_nha"})["pham_vi"] == "kenh_nha"


# ───────────────── mây từ: minigame, màu theo ngưỡng, tập trung (chẩn đoán 16/10/2026) ─────────────────
def _bl_mg(ma, nd, khoa="tiktok:mg", cd=None, sac="Trung lập"):
    r = bl("2026-10-10T10:00+07:00", ma, nd=nd, cd=cd or CS.CHU_DE_MINIGAME, sac=sac,
           tg=f"Khách {ma}")                       # mỗi bình luận một người (mây cần ≥ 2 người)
    r["khoa_bai"] = khoa
    return r


def test_may_tu_an_minigame_mac_dinh_va_ngan_dem_cung_cach():
    """D1: 29/50 cụm là lời chúc dự thi dưới MỘT bài minigame — mặc định không vào mây; bật
    `gom_mg=1` thì gồm. Ngăn từ khoá (cum) đếm đúng như mây ở cả hai chế độ."""
    a = D(2026, 10, 10)
    c = [_bl_mg(f"m{i}", "271 chúc mẹ luôn hạnh phúc, vui vẻ") for i in range(3)] + \
        [_bl_mg("k1", "túi này hạnh phúc ghê", khoa="tiktok:k", cd="Sản phẩm/chất lượng",
                sac="Tích cực"),
         _bl_mg("k2", "mua xong thấy hạnh phúc", khoa="tiktok:k2", cd="Khác", sac="Tích cực")]
    mac = CS.tu_khoa_thao_luan([], c, a, a)
    tk = {g["tu"]: g for g in mac["tu_khoa"]}
    assert mac["an_minigame"] == 3 and mac["tong"] == 2
    assert "chúc mẹ" not in tk and "vui vẻ" not in tk
    gom = CS.tu_khoa_thao_luan([], c, a, a, bo_loc=CS.doc_bo_loc({"gom_mg": "1"}))
    tg = {g["tu"]: g for g in gom["tu_khoa"]}
    assert gom["an_minigame"] == 0 and tg["chúc mẹ"]["so_bai"] == 3
    # Ngăn: cùng cụm, cùng số với mây theo từng chế độ.
    assert CS.chi_tiet_bl(c, a, a, cum="chúc mẹ", loai="hop_le")["tong"] == 0
    assert CS.chi_tiet_bl(c, a, a, cum="chúc mẹ", loai="hop_le",
                          bo_loc=CS.doc_bo_loc({"gom_mg": "1"}))["tong"] == 3
    # Chỉ là tuỳ chọn của mây: không lọc khối nào khác (bộ lọc vẫn "rỗng").
    assert CS.bien_dich(CS.doc_bo_loc({"gom_mg": "1"})).rong
    assert len(CS.loc_bl(c, CS.doc_bo_loc({"gom_mg": ""}))) == 5
    # Khối chủ đề bình luận hiện đúng chủ đề mới (gom theo chữ đã lưu).
    cd = {g["chu_de"]: g["so"] for g in CS.tong_hop_bl(c, a, a, hom_nay=a)["chu_de"]}
    assert cd[CS.CHU_DE_MINIGAME] == 3
    assert CS.tong_quan_loc([], c, a, a)["bo_loc_dem"]["chu_de"][0]["nhom"] == "bl"


def test_mau_may_tu_theo_nguong_va_canh_bao_tap_trung():
    """D2: tô theo ngưỡng (TC ≥ 25% số đã phân loại và ≥ 2 × TI), không theo nhãn lớn nhất. D4:
    một bài góp ≥ 60% số thảo luận của cụm → `mot_bai_pt`."""
    def g(tc, ti, tl):
        return {CS.TC: tc, CS.TI: ti, CS.TL: tl}
    assert CS.sac_noi_troi(g(11, 0, 30)) == "tc"          # 27% TC, chẳng ai chê → xanh
    assert CS.sac_noi_troi(g(4, 0, 46)) == "tl"           # 8% TC → xám
    assert CS.sac_noi_troi(g(10, 6, 20)) == "tl"          # TC < 2 × TI → xám
    assert CS.sac_noi_troi(g(2, 10, 20)) == "ti" and CS.sac_noi_troi(g(0, 0, 0)) == "tl"
    assert CS.sac_noi_troi(g(5, 5, 0)) == "tl"            # hoà → xám
    a = D(2026, 10, 10)
    c = [_bl_mg(f"v{i}", "video viral quá", khoa="tiktok:v", cd="KOL/nội dung", sac="Tích cực")
         for i in range(3)] + \
        [_bl_mg("w", "video viral ghê", khoa="tiktok:w", cd="KOL/nội dung", sac="Tích cực"),
         _bl_mg("x1", "túi đẹp", khoa="tiktok:x1", cd="Khác"),
         _bl_mg("x2", "túi đẹp", khoa="tiktok:x2", cd="Khác")]
    tk = {x["tu"]: x for x in CS.tu_khoa_thao_luan([], c, a, a)["tu_khoa"]}
    assert tk["video viral"]["mau"] == "tc" and tk["video viral"]["mot_bai_pt"] == 75
    assert tk["túi đẹp"]["mau"] == "tl" and "mot_bai_pt" not in tk["túi đẹp"]


# ───────────── mây từ: tách từ, rác quảng cáo, người viết (chủ dự án 16/10/2026) ─────────────
# "Phần từ khoá nổi bật đang lấy các bình luận spam và lấy key word đang lỗi". Mẫu tự đặt (không
# chép bình luận thật), dựng theo các lỗi đã rà trên ảnh chụp kho.
def test_tach_tu_khong_cat_ngang_tu_ghep():
    """Cặp âm tiết cắt ngang một từ ghép ("xách nữ", "nữ tuyệt", "hề diễn", "túi màu") không còn
    là cụm; từ ghép là MỘT cụm; hư từ ghép ("vui lòng", "kiểm tra", "cảm ơn") không lên mây."""
    def k(nd):
        return set(CS._tach_cum({"noi_dung": nd}))
    assert k("Túi xách nữ Luna màu đen") == {"tui xach", "mau den"}
    assert k("Phụ nữ tuyệt vời") == {"phu nu", "tuyet voi"}
    assert k("vai này diễn viên không hề diễn, đúng chất") == {"dien vien"}
    assert k("shop ơi túi mầu đen còn không") == {"mau den"}          # "mầu" viết khác của "màu"
    assert k("Vui lòng kiểm tra tin nhắn để được tư vấn, cảm ơn chị") == set()
    assert k("mua tặng mẹ, túi đẹp và ý nghĩa") == {"mua tang", "tang me", "tui dep", "y nghia"}
    # Tách từ so CÓ dấu: bỏ dấu thì "có thể"/"cơ thể", "vậy mà"/"váy mà", "ông bà"/"ổng bả" trùng.
    assert k("mai em có thể ghé") == set() and k("cơ thể khỏe") == {"co the"}
    assert k("hôm qua mặc váy mà vui") == {"mac vay"}
    assert k("hai ông bà dễ thương") == {"ong ba", "de thuong"} and k("ổng bả tới rồi") == set()
    # Gõ không dấu vẫn tách được; mặt chữ trên mây là bản gặp nhiều nhất.
    assert k("nuoc hoa thom lau") == {"nuoc hoa", "thom lau"}


def test_tach_cum_bo_ma_so_nhan_dan_tag_va_chu_keo_dai():
    def k(nd, ht=""):
        return set(CS._tach_cum({"noi_dung": nd, "hashtag": ht}))
    # Mảnh mã giới thiệu ("fpg" của CKZ-VD88S-FPG) không ghép với chữ bên cạnh.
    assert "fpg xoa" not in k("CKZ-VD88S-FPG xóa 88 rồi")
    assert k("túi a88ah đẹp, sale 20/10 giá 299k") == set()
    # Nhãn dán TikTok "[…]" không phải lời khách viết.
    assert k("mua tặng mẹ [cười chảy nước mắt][ấm lòng]") == {"mua tang", "tang me"}
    # Tên người được tag (viết hoa sau "@") không thành cụm.
    assert k("@Trần Mai Anh vào xem túi đẹp nè") == {"tui dep"}
    assert k("đẹppppp quá, túi xinhhhh") == {"tui xinh"}
    # Hashtag: thẻ có số (mùa vụ/ngày/mã) bỏ; thẻ viết liền đúng một từ ghép đếm chung với từ đó.
    assert k("Quà 20/10 #quatang2010 #tuixach", ht="quatang20_10, fyp, quatangme, nuochoa") == \
        {"tui xach", "nuoc hoa", "#quatangme"}


def test_rac_quang_cao_khong_vao_may_tong_va_ngan():
    """Spam affiliate còn nhãn hợp lệ (luật Mark sót / chưa lọc lại) không đưa chữ lên mây, không
    vào `tong`; ngăn từ khoá trả đúng các bình luận đã đếm."""
    a = D(2026, 10, 10)
    nd = ["𝐃𝐚́𝐧 𝐦𝐚𝐱 𝐜𝐮𝐨̂́𝐢 𝐯𝐚̀𝐨 𝐬𝐨̣̂𝐩-𝐩𝐢𝐢 𝐥𝐚̀ 𝐫𝐚 𝐦𝐚̂̃𝐮 túi xinh AHS-WCM-DQN",
          "dán sàn cam là có nha bạn, túi xinh. CAP-RSJ-JCG", "zán cam ah túi xinh",
          "KQX-77A-PLM túi xinh", "túi xinh quá", "túi xinh ghê", "Túi xinh xỉu"]
    c = [bl("2026-10-10T10:00+07:00", f"c{i}", nd=t, tg=f"Khách {i}") for i, t in enumerate(nd)]
    r = CS.tu_khoa_thao_luan([], c, a, a)
    tk = {g["tu"]: g["so_bai"] for g in r["tu_khoa"]}
    assert r["tong"] == 3 and tk == {"túi xinh": 3}
    x = CS.chi_tiet_bl(c, a, a, cum="túi xinh", loai="hop_le")
    assert x["tong"] == 3 and {b["ma"] for b in x["binh_luan"]} == {"c4", "c5", "c6"}
    assert not CS.la_rac_quang_cao("Có ship về 0912-345-678 không, đơn ORD-2410-0001 ngày 2026-10-15")
    assert not CS.la_rac_quang_cao("size XXL-3XL-4XL còn không") and not CS.la_rac_quang_cao("")
    # Ở mây, mã sản phẩm ≥ 2 khúc chữ cũng bỏ dòng (cái giá nhỏ để không lọt mã giới thiệu).
    assert CS.la_rac_quang_cao("Mẫu AURA-01-BLK còn không")


def test_rac_quang_cao_bat_moi_dong_affiliate_cua_loc_rac():
    """Mây phòng hờ: mọi bình luận `loc_rac.la_affiliate` gắn spam thì `la_rac_quang_cao` cũng bỏ."""
    import loc_rac
    mau = ["𝐃𝐚́𝐧 𝐦𝐚𝐱 𝐜𝐮𝐨̂́𝐢 𝐯𝐚̀𝐨 𝐬𝐨̣̂𝐩-𝐩𝐢𝐢 𝐥𝐚̀ 𝐫𝐚 𝐦𝐚̂̃𝐮 𝐯𝐚̀ 𝐠𝐢𝐚́ AHS-WCM-DQN",
           "CJW-UJK-A88AH xóa 88 rồi zán cam ah", "KQX-77A-PLM dán vào shopee nhé",
           "AHS-WCM-DQN sộp-pii", "𝐳𝐚́𝐧 𝐜𝐚𝐦 𝐧𝐡𝐞́", "Túi đẹp quá", "có bán trên shopee không"]
    for s in mau:
        if loc_rac.la_affiliate(s):
            assert CS.la_rac_quang_cao(s), s
    assert sum(loc_rac.la_affiliate(s) for s in mau) == 5
    assert not CS.la_rac_quang_cao("Túi đẹp quá") and not CS.la_rac_quang_cao(mau[-1])


def test_may_tu_mot_nguoi_viet_lap_khong_phai_xu_huong():
    """Cụm cần ≥ 2 người viết và người viết nhiều nhất góp ≤ 2/3: tài khoản bán hàng trả lời cùng
    câu 5 lần, một người dán một câu 3 lần — không lên mây; không rõ tác giả thì mỗi dòng một người."""
    a = D(2026, 10, 10)
    c = [bl("2026-10-10T10:00+07:00", f"s{i}", nd="Mẫu ví này có sẵn màu kem nha",
            tg="Shop Bán Hàng") for i in range(5)]
    c += [bl("2026-10-10T10:00+07:00", "o1", nd="màu kem đẹp", tg="Lan")]       # 5 + 1: không
    c += [bl("2026-10-10T10:00+07:00", f"v{i}", nd="ví xinh ghê", tg="Hoa") for i in range(2)]
    c += [bl("2026-10-10T10:00+07:00", "v9", nd="ví xinh thật", tg="Mai")]          # 2 + 1: được
    c += [bl("2026-10-10T10:00+07:00", f"d{i}", nd="dây đeo chắc", tg="Huệ") for i in range(3)]
    c += [bl("2026-10-10T10:00+07:00", "d9", nd="dây đeo chắc", tg="Cúc")]          # 3 + 1: không
    tk = {g["tu"]: g["so_bai"] for g in CS.tu_khoa_thao_luan([], c, a, a)["tu_khoa"]}
    assert tk == {"ví xinh": 3}
    vo_danh = [dict(bl("2026-10-10T10:00+07:00", f"x{i}", nd="túi trắng"), tac_gia=None)
               for i in range(2)]
    assert {g["tu"] for g in CS.tu_khoa_thao_luan([], vo_danh, a, a)["tu_khoa"]} == {"túi trắng"}
    # Bài: người viết = nguồn / tài khoản đăng — một KOC đăng 3 bài cùng chú thích không lên mây.
    b = [bai(f"2026-10-10T0{i}:00+07:00", nd="Túi xách nữ Luna xách tay", tk="koc_a", nid=None)
         for i in range(3)]
    assert CS.tu_khoa(b) == []
    them = [bai(f"2026-10-10T0{5 + i}:00+07:00", nd="túi xách tay", tk=f"koc_{i}", nid=None)
            for i in range(2)]
    assert CS.tu_khoa(b + them[:1]) == []                                     # 3 + 1: không
    assert [(g["tu"], g["so_bai"]) for g in CS.tu_khoa(b + them)] == [("túi xách", 5)]


def test_ngan_tu_khoa_bai_cong_binh_luan_bang_so_tren_may():
    """Thẻ "bài" (`chi_tiet_bai` cum) + thẻ "bình luận" (`chi_tiet_bl` cum, hop_le) của MỌI cụm
    đang hiện cộng lại đúng `so_bai` trên mây — kể cả hashtag gộp vào từ ghép, rác quảng cáo, bình
    luận minigame, bài kênh nhà, chữ không dấu."""
    a = D(2026, 10, 10)
    bs = [bai("2026-10-10T09:00+07:00", nd="Túi xách da thật, màu đen sang", ht="tuixach",
              tk="koc_a", nid=None),
          bai("2026-10-10T09:30+07:00", nd="quà tặng mẹ #tuixach", tk="koc_b", nid=None),
          bai("2026-10-10T10:00+07:00", nd="túi xách nước hoa", nid=9, loai="kenh_nha", tk="nha")]
    nd = [("tui xach dep qua", "Lan"), ("Túi xách màu đen còn không", "Hoa"),
          ("màu đen sang ghê", "Mai"), ("dán mã túi xách KQX-77A-PLM", "Spam"),
          ("chúc mẹ túi xách đẹp", "MG"), ("quà tặng mẹ ý nghĩa", "Cúc"),
          ("tặng mẹ luôn", "Đào")]
    cs = []
    for i, (t, tg) in enumerate(nd):
        x = bl("2026-10-10T11:00+07:00", f"c{i}", nd=t, tg=tg,
               cd=CS.CHU_DE_MINIGAME if tg == "MG" else "Khác")
        x["khoa_bai"] = bs[i % 2]["khoa"]
        cs.append(x)
    for gom in ("", "1"):
        f = CS.doc_bo_loc({"gom_mg": gom} if gom else {})
        may = CS.tu_khoa_thao_luan(bs, cs, a, a, bo_loc=f)["tu_khoa"]
        assert {"túi xách", "màu đen", "quà tặng"} <= {g["tu"] for g in may}
        for g in may:
            n_bai = CS.chi_tiet_bai(bs, a, a, cum=g["tu"], bo_loc=f)["tong"]
            n_bl = CS.chi_tiet_bl(cs, a, a, cum=g["tu"], loai="hop_le", bo_loc=f)["tong"]
            assert n_bai + n_bl == g["so_bai"], (gom, g["tu"])
    tk = {g["tu"]: g["so_bai"] for g in may}
    assert tk["túi xách"] == 2 + 3                     # 2 bài khách + c0, c1, c4 (MG khi gom_mg)


def test_tu_ghep_danh_sach_hop_le():
    """Danh sách từ ghép: mỗi mục 2–4 âm tiết, không mục nào nằm ở cả hai nhóm; khoá bỏ dấu trùng
    giữa hai nhóm chỉ là các cặp khác dấu đã biết (tách từ so có dấu)."""
    from dashboard import tu_ghep as TG
    dang = [f for v in TG.DANG.values() for f in v]
    assert all(2 <= len(f) <= 4 for f, _ in dang) and TG.DAI_NHAT <= 4
    assert len({f for f, _ in dang}) == len(dang)
    assert TG.HU & set(TG.GHEP) <= {"ban than", "co the", "do do"}
    assert TG.LIEN["tuixach"] == "tui xach" and TG.GHEP["tui xach"] == "túi xách"
