"""Dashboard lắng nghe (đợt 2, 14/10/2026): chỉ số kiểu Kompa (`dashboard/chi_so.py`).

Mọi kỳ vọng tính tay. "Thảo luận" = số bài + số bình luận nền tảng báo; ngày theo GIỜ VN của
`dang_luc`; bài kênh nhà tính vào số bài/thảo luận/nguồn nhưng không vào sắc thái/chủ đề/từ khoá.
"""
from __future__ import annotations

import datetime

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
                ht="hapasvn, tuixach"),
            bai("2026-10-10T10:00+07:00", nd="túi xách hapas quá xinh", ht="tuixach, fyp"),
            bai("2026-10-10T11:00+07:00", nd="Nước hoa thơm lâu", ht=""),
            bai("2026-10-10T12:00+07:00", nd="túi xách nước hoa", nid=9, loai="kenh_nha")]
    tk = CS.tu_khoa(rows, ["Hapas"])
    # '#hapasvn', 'xách hapas', 'hapas mới' chứa từ khoá dự án -> bỏ; 'mới về', 'quá xinh' có
    # hư từ -> bỏ; '#fyp' là hashtag đẩy đề xuất; 'nước hoa' chỉ 1 bài khách (bài kênh nhà không
    # tính) -> dưới ngưỡng 2 bài.
    assert [(g["tu"], g["so_bai"]) for g in tk] == [("#tuixach", 2), ("túi xách", 2)]
    assert CS.tu_khoa(rows, [])[0]["tu"] == "#tuixach"
    assert any(g["tu"] == "xách hapas" for g in CS.tu_khoa(rows, []))


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


def test_top_bai_theo_thao_luan_roi_luot_xem():
    rows = [bai("2026-10-10T09:00+07:00", bl=5, xem=1, link="https://a/1", nd="  một\n hai "),
            bai("2026-10-10T09:00+07:00", bl=5, xem=9, link="https://a/2"),
            bai("2026-10-10T09:00+07:00", bl=7, xem=0, link="https://a/3")]
    top = CS.top_bai(rows)
    assert [b["link"] for b in top] == ["https://a/3", "https://a/2", "https://a/1"]
    assert top[2]["noi_dung"] == "một hai" and top[0]["thao_luan"] == 8
    assert top[0]["dang_luc"] == "2026-10-10T09:00+07:00"
