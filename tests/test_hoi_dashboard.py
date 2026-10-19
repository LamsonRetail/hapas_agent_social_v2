"""Tool `hoi_dashboard` (17/10/2026): Mark trả lời số liệu dashboard lắng nghe trong chat.

Ba điều phải canh:
  • SỐ KHỚP TRANG: `tinh_chi_so` ghép các khối y như `/api/chi-so` — so TỪNG KHỐI với chính
    endpoint của `dashboard/app.py` trên CÙNG kho giả (`test_dashboard_app.GiaKho`), nhiều bộ lọc.
  • CHỈ NGƯỜI XEM DASHBOARD: danh tính từ nguồn đã xác thực (chat riêng Lark / web đã xác thực),
    email phải có trong `nguoi_xem`; nhóm chat, A2A, lịch, không đọc được email/danh sách → ĐÓNG.
  • KHÔNG DỮ LIỆU CÁ NHÂN THÔ: không tên/nội dung người bình luận, chữ lỗi thô chỉ cho quản lý.
Không Postgres, không mạng (danh bạ Lark giả)."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from test_dashboard_app import QL, XEM, GiaKho, _bai, _bl, dang_nhap, tao

import hoi_dashboard_tool as HD
import lsr_policy
import memory_store
import meta_ads_tool
import scheduler
from dashboard import app as A
from dashboard import chi_so as CS

VN = datetime.timezone(datetime.timedelta(hours=7))
P2P = {"channel": "lark", "chat_type": "p2p", "nguoi_gui": "ou_hoi"}
NGUOI_BINH_LUAN = "Trần Thị Bình Luận"


@pytest.fixture(autouse=True)
def ngu_canh(monkeypatch):
    memory_store.set_current_sender("ou_hoi")
    scheduler.set_current_chat(None)
    scheduler.set_current_chat_type("p2p")
    meta_ads_tool.set_context(P2P)
    HD._nho.clear()
    HD._email_nho.clear()
    yield
    memory_store.set_current_sender(None)
    scheduler.set_current_chat_type(None)
    meta_ads_tool.set_context({})
    HD._nho.clear()


def _luc(ngay: int, gio: int = 9) -> datetime.datetime:
    return datetime.datetime(2026, 10, ngay, gio, 0, tzinfo=VN)


def _kho_mau() -> GiaKho:
    """Đủ thứ để mọi khối có số: hai kỳ, nhiều nền tảng/loại nguồn/sắc thái, kênh nhà, bài web,
    bài tìm theo từ khoá, bình luận hợp lệ/thương hiệu/hỏi mua (kỳ này và kỳ trước), bài gốc của
    bình luận nằm TRƯỚC khoảng (đường `bai_theo_khoa`)."""
    kho = GiaKho()
    kho.bai = [
        _bai(_luc(10), khoa="tiktok:1", binh_luan=40, thich=2000, xem=90000,
             noi_dung="túi xách hapas đẹp quá giá tốt", followers=250000),
        _bai(_luc(11), khoa="tiktok:2", sac_thai="Tiêu cực", binh_luan=900, thich=800,
             chia_se=50, noi_dung="túi xách bong da sau một tuần thất vọng", chu_de="Chất lượng sản phẩm"),
        _bai(_luc(12), khoa="facebook:3", nen_tang="facebook", nguon_id=None, kieu_quet="tu_khoa",
             nguon_loai=None, tai_khoan="page.x", tac_gia="Page X", sac_thai="Trung lập",
             noi_dung="review túi xách màu be", binh_luan=5),
        _bai(_luc(12, 20), khoa="instagram:4", nen_tang="instagram", nguon_loai="kenh_nha",
             nguon_id=2, sac_thai=None, noi_dung="bộ sưu tập mới", binh_luan=12),
        _bai(_luc(13), khoa="web:5", nen_tang="web", nguon_id=None, kieu_quet="tu_khoa",
             nguon_loai=None, tai_khoan="vnexpress.net", xem=None, thich=None, chia_se=None,
             binh_luan=None, kieu_trang="bao", muc_nhac="tieu_de", la_pr=False,
             noi_dung="HAPAS ra mắt túi xách mới"),
        _bai(_luc(14), khoa="tiktok:6", sac_thai="Tiêu cực", binh_luan=3, thich=1,
             noi_dung="túi xách giao chậm"),
        # kỳ trước
        _bai(_luc(3), khoa="tiktok:7", binh_luan=10, noi_dung="túi xách đẹp"),
        _bai(_luc(5), khoa="tiktok:8", sac_thai="Tiêu cực", binh_luan=1, noi_dung="túi xách xấu"),
        # đăng TRƯỚC cả kỳ trước: chỉ tới được qua bình luận mới (đường `bai_theo_khoa`)
        _bai(datetime.datetime(2026, 9, 20, 9, 0, tzinfo=VN), khoa="tiktok:9", followers=500000,
             binh_luan=70, thich=3000, noi_dung="túi xách hapas review"),
    ]
    bl = [
        _bl("tiktok:1", "a", _luc(10, 10)),
        _bl("tiktok:1", "b", _luc(10, 11), sac="Tiêu cực"),
        _bl("tiktok:1", "c", _luc(10, 12), nha=True),
        _bl("tiktok:2", "d", _luc(11, 10), sac="Trung lập", chu_de="Giá/mua ở đâu/ý định mua"),
        _bl("tiktok:2", "e", _luc(11, 11), sac="Trung lập", chu_de="Khác"),
        _bl("instagram:4", "f", _luc(12, 21), sac="Tích cực"),
        # bình luận mới dưới bài đăng TRƯỚC khoảng (bài kỳ trước)
        _bl("tiktok:7", "g", _luc(9, 8), sac="Trung lập", chu_de="Khác"),
        _bl("tiktok:9", "i", _luc(13, 8), sac="Tích cực", chu_de="Sản phẩm/chất lượng"),
        # kỳ trước
        _bl("tiktok:7", "h", _luc(3, 10), sac="Trung lập", chu_de="Giá/mua ở đâu/ý định mua"),
    ]
    for c in bl:
        c["tac_gia"] = NGUOI_BINH_LUAN
    bl[4]["noi_dung"] = "giá bao nhiêu vậy shop"
    bl[6]["noi_dung"] = "xin link mua với"
    bl[7]["noi_dung"] = "túi xách này còn size nhỏ không"
    bl[3]["san_pham"] = "set_qua"            # món hỏi mua AI gán (17/10/2026)
    bl[5].update(nguon_loai="kenh_nha", nguon_id=2, nen_tang="instagram")
    kho.bl = bl
    return kho


QUERY = (
    "",
    "&nen_tang=tiktok,facebook",
    "&pham_vi=ben_ngoai",
    "&pham_vi=kenh_nha",
    "&sac_thai=tieu_cuc",
    "&q=túi xách",                       # lọc chữ: bình luận cần bài gốc (bai_theo_khoa có chữ)
    "&anh_huong=macro",                  # chiều cấp bài: bai_theo_khoa không chữ
    "&y_dinh=1",
    "&y_dinh=set_qua",                   # lọc một món hỏi mua (AI gán)
    "&y_dinh=tui",                       # món theo chữ trong bình luận (luật lùi)
    "&tuong_tac=1000",                   # so sánh bị tắt (so_sanh_lech)
    "&loai=tu_khoa&kieu_quet=tu_khoa",
    "&chu_de=Giá/mua ở đâu/ý định mua",
    "&kieu_trang=bao",
    "&gom_mg=1",
)
#: Khoá của /api/chi-so mà tool không tính (thông tin phiên/lượt, không phải số của bộ lọc).
#: `do_phu` (kiểm độ phủ, 17/10/2026): lần kiểm gần nhất, không theo bộ lọc/khoảng ngày.
KHONG_TINH = {"gan_nhan", "du_an", "ngay_cuoi_chua_tron", "luot_gan_nhat", "cap_nhat_luc",
              "do_phu"}


def _json(x):
    return json.loads(json.dumps(x, ensure_ascii=False, default=str))


@pytest.mark.parametrize("them", QUERY)
@pytest.mark.parametrize("tu,den", [("2026-10-08", "2026-10-14"), ("2026-09-01", "2026-10-16")])
def test_khop_api_chi_so_tung_khoi(tu, den, them):
    """Cùng kho, cùng bộ lọc: MỌI khối số của tool == của /api/chi-so (sau JSON)."""
    _, c, kho = tao(_kho_mau())
    dang_nhap(c, XEM)
    r = c.get(f"/api/chi-so?du_an=hapas&tu={tu}&den={den}{them}")
    assert r.status_code == 200, r.text
    api = r.json()
    q = {k: v[-1] for k, v in parse_qs(them.lstrip("&")).items()}
    d = HD.tinh_chi_so(kho, kho.doc_du_an("hapas"), datetime.date.fromisoformat(tu),
                       datetime.date.fromisoformat(den), CS.doc_bo_loc(q), A._hom_nay())
    d = _json(d)
    thieu = set(api) - KHONG_TINH - set(d)
    assert not thieu, f"tool thiếu khối của dashboard: {thieu}"
    for k in set(api) - KHONG_TINH:
        assert d[k] == api[k], f"khối {k} lệch với dashboard ({them or 'không lọc'})"


def test_mau_du_lieu_phu_du_cac_khoi():
    """Canh chính bài thử khớp: mẫu phải làm mọi khối có số (khớp trên khối rỗng là khớp giả)."""
    kho = _kho_mau()
    d = HD.tinh_chi_so(kho, kho.doc_du_an("hapas"), datetime.date(2026, 10, 8),
                       datetime.date(2026, 10, 14), CS.doc_bo_loc({}), datetime.date(2026, 10, 17))
    assert d["kpi"]["bai"] == 6 and d["kpi_truoc"]["bai"] == 2
    assert d["kpi"]["web"]["bai"] == 1 and d["kpi"]["bai_kenh_nha"] == 1
    assert d["y_dinh_mua"]["so"] >= 2 and d["y_dinh_mua"]["truoc"] == 1
    assert d["tu_khoa"] and d["top_nguon"] and d["binh_luan_da_cao"]["kpi"]["thuong_hieu"] == 1
    assert d["_khung_hoang"]["kpi"]["bai"] == 1          # tiktok:2 tiêu cực, 1.750 tương tác
    q = HD.tinh_chi_so(kho, kho.doc_du_an("hapas"), datetime.date(2026, 10, 8),
                       datetime.date(2026, 10, 14), CS.doc_bo_loc({"q": "túi xách"}),
                       datetime.date(2026, 10, 17))
    assert kho.goi_bai_khoa and kho.goi_bai_khoa_chu[-1] is True   # đã đi đường bài gốc thiếu
    assert q["kpi"]["bai"] < d["kpi"]["bai"]


def test_khoang_mac_dinh_giong_dashboard():
    hn = A._hom_nay()
    assert HD.doc_khoang({}, hn) == A._doc_khoang({})
    assert HD.doc_khoang({"tu": "2026-10-01", "den": "2026-10-07"}, hn) == \
        A._doc_khoang({"tu": "2026-10-01", "den": "2026-10-07"})
    tu, den = HD.doc_khoang({"so_ngay": 7}, datetime.date(2026, 10, 17))
    assert (tu, den) == (datetime.date(2026, 10, 10), datetime.date(2026, 10, 16))
    for sai in ({"tu": "2026-10-09", "den": "2026-10-01"}, {"tu": "2025-01-01"},
                {"tu": "17/10/2026"}, {"so_ngay": 0}, {"so_ngay": "abc"}):
        with pytest.raises(A.NL.LoiNhap):
            HD.doc_khoang(sai, datetime.date(2026, 10, 17))


def test_chip_nhanh_va_bo_loc_cua_model():
    q = HD.tham_so_loc({"nen_tang": ["tiktok", "facebook"], "sac_thai": "tieu_cuc",
                        "tuong_tac": 1000, "la": "bo qua", "q": ""})
    assert q == {"nen_tang": "tiktok,facebook", "sac_thai": "tieu_cuc", "tuong_tac": "1000"}
    b = CS.doc_bo_loc(q)
    assert b["nen_tang"] == ("facebook", "tiktok") and b["sac_thai"] == (CS.TI,)
    nhanh = next(x for x in CS.BO_LOC_NHANH if x["ma"] == "can_xu_ly")
    assert CS.doc_bo_loc(HD.tham_so_loc({}, nhanh))["pham_vi"] == "kenh_nha"
    # chip có so_ngay, người hỏi không nói kỳ: N ngày tính tới HÔM NAY như nút trên trang
    assert HD.doc_khoang({}, datetime.date(2026, 10, 17), nhanh) == \
        (datetime.date(2026, 10, 11), datetime.date(2026, 10, 17))
    assert HD.doc_khoang({"so_ngay": 30}, datetime.date(2026, 10, 17), nhanh)[1] == \
        datetime.date(2026, 10, 16)
    with pytest.raises(CS.LoiBoLoc):
        CS.doc_bo_loc(HD.tham_so_loc({"nen_tang": "twitter"}))


def test_link_mo_dung_man_hinh():
    b = CS.doc_bo_loc({"sac_thai": "tieu_cuc", "nen_tang": "tiktok", "pham_vi": "ben_ngoai",
                       "q": "giá & ship"})
    u = HD.link_dashboard("hapas", datetime.date(2026, 10, 1), datetime.date(2026, 10, 7), b)
    p = urlsplit(u)
    assert (p.scheme, p.netloc, p.path) == ("https", "social.hapas.vn", "/")
    q = {k: v[-1] for k, v in parse_qs(p.query).items()}
    assert q["du_an"] == "hapas" and (q["tu"], q["den"]) == ("2026-10-01", "2026-10-07")
    assert CS.doc_bo_loc(q) == b                        # trang đọc lại ra ĐÚNG bộ lọc
    assert "gom_mg" not in q and "tuong_tac" not in q   # chiều trống không lên link
    rong = HD.link_dashboard("hapas", datetime.date(2026, 10, 1), datetime.date(2026, 10, 7), None)
    assert "pham_vi" not in rong


# ───────────────────────────── trả lời đầy đủ ─────────────────────────────
@pytest.fixture
def la_nguoi_xem(monkeypatch):
    monkeypatch.setattr(HD, "email_cua", lambda oid: XEM if oid == "ou_hoi" else QL)


BAY_GIO = datetime.datetime(2026, 10, 17, 10, 0, tzinfo=VN)


def test_tra_loi_khop_tong_quan_va_co_link(la_nguoi_xem):
    kho = _kho_mau()
    _, c, _ = tao(kho)
    dang_nhap(c, XEM)
    api = c.get("/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14&pham_vi=ben_ngoai").json()
    ra = HD.tra_loi({"du_an": "hapas", "tu": "2026-10-08", "den": "2026-10-14",
                     "bo_loc": {"pham_vi": "ben_ngoai"}, "phan": list(HD.PHAN)}, kho,
                    open_id="ou_hoi", bay_gio=BAY_GIO)
    ra = _json(ra)
    tq = ra["phan"]["tong_quan"]
    assert tq["kpi"]["thao_luan"] == api["kpi"]["thao_luan"]
    assert tq["so_voi_ky_truoc"] == api["so_sanh"]
    assert tq["y_dinh_mua"]["pt"] == api["y_dinh_mua"]["pt"]
    assert ra["khoang"]["ky_truoc"] == {"tu": "2026-10-01", "den": "2026-10-07"}
    assert ra["link"].startswith("https://social.hapas.vn/?du_an=hapas&tu=2026-10-08")
    assert "pham_vi=ben_ngoai" in ra["link"]
    assert ra["vai_tro_nguoi_hoi"] == "xem" and set(ra["phan"]) == set(HD.PHAN)
    assert ra["phan"]["nha_ngoai"][CS.TEN_BEN_NGOAI]["bai"] == \
        api["nha_ngoai"]["ben_ngoai"]["bai"]
    assert ra["link_ngan_sach"].endswith("/ngan-sach?du_an=hapas")
    assert ra["phan"]["do_phu"]["co"] is False
    # Không tên / nội dung người bình luận ở bất kỳ đâu.
    chu = json.dumps(ra, ensure_ascii=False)
    assert NGUOI_BINH_LUAN not in chu and "xin link mua với" not in chu


def test_mac_dinh_phan_va_cat_top(la_nguoi_xem):
    kho = _kho_mau()
    ra = HD.tra_loi({"tu": "2026-10-08", "den": "2026-10-14", "so_dong": 2}, kho,
                    open_id="ou_hoi", bay_gio=BAY_GIO)
    assert list(ra["phan"]) == list(HD.PHAN_MAC_DINH)
    assert ra["du_an"] == {"ma": "hapas", "ten": "HAPAS"}           # dự án mặc định như trang
    assert len(ra["phan"]["bai"]["top"]) == 2
    assert all(len(b["noi_dung"]) <= HD.CHU_TOI_DA for b in ra["phan"]["bai"]["top"])
    ra = HD.tra_loi({"so_dong": 999, "phan": ["bai"]}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)
    assert ra["khoang"]["mac_dinh"] is True and ra["khoang"]["so_ngay"] == 30


def test_khung_hoang_dung_chip_dashboard(la_nguoi_xem):
    kho = _kho_mau()
    ra = HD.tra_loi({"tu": "2026-10-08", "den": "2026-10-14", "phan": ["khung_hoang"]}, kho,
                    open_id="ou_hoi", bay_gio=BAY_GIO)
    kh = ra["phan"]["khung_hoang"]
    assert kh["so_bai"] == 1 and kh["top_bai"][0]["link"]
    q = {k: v[-1] for k, v in parse_qs(urlsplit(ra["link_khung_hoang"]).query).items()}
    assert (q["sac_thai"], q["tuong_tac"]) == ("tieu_cuc", "1000")
    # Đang lọc chỉ tích cực: không có gì để xét, không bịa số.
    ra = HD.tra_loi({"tu": "2026-10-08", "den": "2026-10-14", "phan": ["khung_hoang"],
                     "bo_loc": {"sac_thai": "tich_cuc"}}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)
    assert "so_bai" not in ra["phan"]["khung_hoang"]


def test_du_an_sai_va_bo_loc_sai(la_nguoi_xem):
    kho = _kho_mau()
    with pytest.raises(A.NL.LoiNhap, match="hapas"):
        HD.tra_loi({"du_an": "khong-co"}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)
    with pytest.raises(CS.LoiBoLoc):
        HD.tra_loi({"bo_loc": {"sac_thai": "vui"}}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)
    with pytest.raises(A.NL.LoiNhap):
        HD.tra_loi({"bo_loc_nhanh": "khong_co"}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)


def test_chi_phi_lich_an_loi_tho_voi_nguoi_chi_xem(monkeypatch):
    kho = _kho_mau()
    kho.luot = [{"id": 9, "du_an": "hapas", "kieu": "theo_doi", "ma_viec": "v9",
                 "bat_dau": _luc(16), "ket_thuc": _luc(16, 10), "so_nguon": 3, "so_nguon_loi": 1,
                 "bai_moi": 12, "bai_cap_nhat": 4, "chi_phi_usd": 0.0421, "trang_thai": "mot_phan",
                 "loi": "apify 402 /home/mark/.env", "ghi_chu": None, "lich_id": None}]
    for email, thay in ((XEM, False), (QL, True)):
        monkeypatch.setattr(HD, "email_cua", lambda oid, e=email: e)
        ra = HD.tra_loi({"phan": ["chi_phi", "lich"]}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)
        cp = ra["phan"]["chi_phi"]
        assert cp["da_tieu_usd"] == 1.25 and cp["tran_usd"] == 5.0
        assert cp["luot_gan_nhat"][0]["chi_phi_usd"] == 0.0421
        assert ("/home/mark" in json.dumps(ra)) is thay
        assert cp["luot_gan_nhat"][0]["loi"] == ("apify 402 /home/mark/.env" if thay
                                                 else HD.LOI_CHUNG)
        assert ra["phan"]["lich"]["lich"] == [] and "phan" in ra
        assert "tong_quan" not in ra["phan"]             # chỉ phần được hỏi
    assert kho.goi_bai == []                            # không đọc 20k bài khi chỉ hỏi chi phí


def test_chi_phi_noi_ca_goi_apify(monkeypatch):
    """18/10/2026: "ngân sách còn" phải nói cả gói Apify (trần THẬT của tài khoản) — như khối
    "Gói Apify" trang Ngân sách (`chi_phi.goi_apify`, ảnh chụp Mark ghi ở `han_muc_apify`)."""
    from test_goi_apify import LUC, _anh
    kho = _kho_mau()
    monkeypatch.setattr(HD, "email_cua", lambda oid: XEM)
    cp = HD.tra_loi({"phan": ["chi_phi"]}, kho, open_id="ou_hoi", bay_gio=LUC)["phan"]["chi_phi"]
    assert cp["goi_apify"] == {"co": False}                     # kho chưa có bảng / hàm
    kho.han_muc_apify = lambda: _anh()
    g = HD.tra_loi({"phan": ["chi_phi"]}, kho, open_id="ou_hoi",
                   bay_gio=LUC)["phan"]["chi_phi"]["goi_apify"]
    assert g["goi"] == "FREE" and g["tran_goi_usd"] == 10.0 and g["da_dung_usd"] == 4.5819
    assert g["con_lai_goi_usd"] == pytest.approx(5.4181)
    assert g["mark_dung_duoc_usd"] == pytest.approx(5.1181) and g["tran_moi_luot_usd"] == 2.0
    assert g["dat_lai"].startswith("2026-11-16T07:00") and g["tran_noi_bo_vo_hieu"] is False
    assert "han_muc_apify" in HD._HAM_KHO


def _kho_ngan_sach():
    """HAPAS 18/10 01:00 như `test_du_bao_thuc` (12 lượt thật, lịch 07:00, gói FREE, trần console
    2 USD/lượt) + một trang Facebook kênh nhà 10 bài đăng ≤ 1 bài/ngày (co còn 4) + một dự án
    thứ hai đang bật (gói dùng chung)."""
    from test_du_bao_thuc import DP_CUOI, DU_AN_HAPAS, LICH_07, LUOT_THAT
    from test_goi_apify import _anh
    kho = GiaKho()
    kho.du_an["hapas"].update({k: DU_AN_HAPAS[k] for k in (
        "tu_khoa", "bl_bat", "bl_so_bai", "bl_moi_bai", "tk_bat", "tk_so_bai", "cau_hinh",
        "tran_usd_thang")})
    kho.du_an["khac"] = {**kho.du_an["hapas"], "ma": "khac", "ten": "Khác",
                         "tran_usd_thang": 10.0, "cau_hinh": {}}
    for i, (ma, loai) in enumerate((("hapas", "kenh_nha"), ("hapas", "kol"),
                                    ("khac", "kenh_nha")), 1):
        kho.nguon[i] = {"id": i, "du_an": ma, "nen_tang": "facebook",
                        "dinh_danh": f"https://www.facebook.com/trang{i}", "ten": f"T{i}",
                        "link": "", "loai": loai, "nhan": [], "trang_thai": "dang_theo_doi",
                        "chu_ky_ngay": 1, "so_bai_moi_lan": 10, "them_qua": "dashboard",
                        "them_boi": None, "them_luc": None, "quet_cuoi": None,
                        "loi_cuoi": None, "loi_luc": None}
    kho.nhip_dang = lambda du_an, ngay=14: {1: 1, 2: 1, 3: 1}
    kho.luot = [dict(x) for x in LUOT_THAT] + [dict(x, du_an="khac", id=100 + x["id"])
                                               for x in LUOT_THAT[1:6]]
    kho._lich()[6] = dict(LICH_07)
    kho.da_tieu_thang = lambda: {"hapas": 15.44, "khac": 2.0}
    kho.do_phu = [{"luc": DP_CUOI, "hanh_dong": {}}]
    kho.han_muc_apify = lambda: _anh()
    return kho


def test_chi_phi_va_lich_khop_trang_tung_khoi(monkeypatch):
    """Soát 18/10/2026: Mark trả lời số chi phí KHÁC dashboard — không co số bài nguồn (trang co
    theo nhịp đăng), `tong_quan`/`dong_lich` không truyền `chi` (mức tối đa 8,6 USD/lượt chưa kẹp ở
    trần console 2 USD), trần nội bộ của gói chỉ của một dự án (trang: tổng dự án đang bật). Nay
    cùng hàm, cùng tham số: so TỪNG KHỐI tool với khối trang tính ra trên CÙNG kho giả."""
    from test_du_bao_thuc import BAY

    from dashboard import chi_phi as CP
    from dashboard import trang_lich as TL
    ghi: dict = {}

    def nghe(mod, ten):
        goc = getattr(mod, ten)

        def boc(*a, **kw):
            ra = goc(*a, **kw)
            ghi.setdefault(ten, []).append(_json(ra))
            return ra
        monkeypatch.setattr(mod, ten, boc)
    for mod, ten in ((CP, "khoi_ngan_sach"), (CP, "goi_ngan_sach"), (TL, "tong_quan"),
                     (TL, "dong_lich")):
        nghe(mod, ten)
    monkeypatch.setattr(A, "_bay_gio", lambda: BAY)
    _, c, kho = tao(_kho_ngan_sach())
    dang_nhap(c, QL)
    assert c.get("/ngan-sach?du_an=hapas").status_code == 200
    assert c.get("/lich-quet?du_an=hapas").status_code == 200
    trang = {k: list(v) for k, v in ghi.items()}
    ghi.clear()
    monkeypatch.setattr(HD, "email_cua", lambda oid: QL)
    ra = HD.tra_loi({"du_an": "hapas", "phan": ["chi_phi", "lich"]}, kho, open_id="ou_hoi",
                    bay_gio=BAY)["phan"]
    tool = ghi
    # Khối dự án: Ngân sách (hapas + khác cho gói) — cùng đầu vào thì cùng mọi số.
    k_trang = {x["du_bao"]["tran"]: x for x in trang["khoi_ngan_sach"]}
    assert tool["khoi_ngan_sach"][0] == trang["khoi_ngan_sach"][0]          # hapas
    assert sorted(_json(x)["du_bao"]["tran"] for x in tool["khoi_ngan_sach"]) == sorted(k_trang)
    assert tool["goi_ngan_sach"] == trang["goi_ngan_sach"]
    # Lịch: `tong_quan` (trang Lịch + `theo_lich` của chi phí) và `dong_lich`.
    assert all(x == trang["tong_quan"][0] for x in tool["tong_quan"])
    assert tool["dong_lich"] == trang["dong_lich"]
    # Số tool nói ra = số trang hiện.
    k, g, tq, dl = (trang["khoi_ngan_sach"][0], trang["goi_ngan_sach"][0],
                    trang["tong_quan"][0], trang["dong_lich"][0][0])
    cp = ra["chi_phi"]
    assert cp["con_lai_theo_nguon_usd"] == k["db"]["con_lai"]
    assert cp["du_bao_thuc"]["du_bao_thang_usd"] == k["du_bao"]["du_bao_thang"]
    assert cp["goi_apify"]["du_bao_toi_dat_lai_usd"] == g["du_bao_chu_ky"]
    assert cp["theo_lich"]["tong"] == tq["tong"] and cp["theo_lich"]["tong_thuc"] == tq["tong_thuc"]
    assert ra["lich"]["tong_quan_thang"]["tong"] == tq["tong"]
    assert ra["lich"]["lich"][0]["usd_30_ngay"] == dl["usd_30"]
    # Đúng các lỗi cũ: kênh nhà co còn 4 bài, KOL lấy đủ; mỗi lượt kẹp 2 USD; trần nội bộ 30 + 10.
    co = {n["id"]: n["so_bai_co_gian"] for n in k["nguon"]}
    assert co == {1: 4, 2: None}
    assert dl["moi_luot"] == 2.0 and ra["lich"]["lich"][0]["moi_luot_toi_da_usd"] == 2.0
    assert g["tran_noi_bo"] == 40.0 and cp["goi_apify"]["tran_noi_bo_vo_hieu"] is True


# ───────────────────────────── quyền ─────────────────────────────
def test_nguoi_khong_co_trong_nguoi_xem_bi_tu_choi(monkeypatch):
    kho = _kho_mau()
    monkeypatch.setattr(HD, "email_cua", lambda oid: "la@hapas.vn")
    with pytest.raises(HD.TuChoi, match="la@hapas.vn"):
        HD.tra_loi({}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)
    assert kho.goi_bai == [] and kho.goi_bl == []
    monkeypatch.setattr(HD, "email_cua", lambda oid: "")
    with pytest.raises(HD.TuChoi, match="email"):
        HD.tra_loi({}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)

    def hong(email):
        raise RuntimeError("mất kết nối")
    monkeypatch.setattr(HD, "email_cua", lambda oid: XEM)
    monkeypatch.setattr(kho, "quyen_cua", hong)
    with pytest.raises(HD.TuChoi, match="chưa đọc được danh sách"):
        HD.tra_loi({}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)


def test_xoa_khoi_nguoi_xem_mat_quyen_ngay(la_nguoi_xem):
    kho = _kho_mau()
    HD.tra_loi({"phan": ["tong_quan"]}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)
    del kho.nguoi[XEM]
    with pytest.raises(HD.TuChoi):
        HD.tra_loi({"phan": ["tong_quan"]}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)


@pytest.mark.parametrize("ctx,loai_chat,ai,khop", [
    (P2P, "p2p", "ou_hoi", None),
    ({**P2P, "chat_type": "group"}, "group", "ou_hoi", "nhóm"),
    (P2P, "group", "ou_hoi", "nhóm"),
    ({"channel": "a2a", "chat_type": "p2p", "nguoi_gui": "ou_hoi"}, "p2p", "ou_hoi", "A2A"),
    ({**P2P, "scheduled": True}, "p2p", "ou_hoi", "Lịch"),
    (P2P, "p2p", "ou_khac", "không khớp"),
    ({"channel": "lark", "nguoi_gui": "ou_hoi"}, None, "ou_hoi", "chat riêng"),
    ({"chat_type": "p2p"}, "p2p", "ou_hoi", "kênh"),
    ({"channel": "web", "nguoi_gui": "ou_hoi"}, None, "ou_hoi", "Web chưa xác thực"),
    ({"channel": "web", "nguoi_gui": "ou_hoi", "sender_identity_verified": True}, None,
     "ou_hoi", None),
    ({"channel": "lark", "chat_type": "p2p", "nguoi_gui": "bia"}, "p2p", "bia", "xác thực"),
])
def test_danh_tinh_nguoi_hoi(ctx, loai_chat, ai, khop):
    meta_ads_tool.set_context(ctx)
    scheduler.set_current_chat_type(loai_chat)
    memory_store.set_current_sender(ai)
    if khop is None:
        assert HD.nguoi_hoi() == ai
    else:
        with pytest.raises(HD.TuChoi, match=khop):
            HD.nguoi_hoi()


def test_email_tu_danh_ba_lark(monkeypatch):
    goi = []

    def call(method, path, query=None, body=None):
        goi.append((method, path, query))
        return {"code": 0, "data": {"user": {"email": "TU.KHAI@gmail.com",
                                             "enterprise_email": "Nguoi.Xem@hapas.vn"}}}
    monkeypatch.setattr(HD.lark, "call", call)
    assert HD.email_cua("ou_hoi") == "nguoi.xem@hapas.vn"      # email tổ chức cấp trước
    assert HD.email_cua("ou_hoi") == "nguoi.xem@hapas.vn" and len(goi) == 1   # nhớ
    assert goi[0] == ("GET", "/open-apis/contact/v3/users/ou_hoi", {"user_id_type": "open_id"})
    monkeypatch.setattr(HD.lark, "call", lambda *a, **k: {"data": {"user": {"email": "tu@x.vn"}}})
    assert HD.email_cua("ou_2") == "tu@x.vn"
    monkeypatch.setattr(HD.lark, "call", lambda *a, **k: {"code": 99991672, "data": {}})
    assert HD.email_cua("ou_3") == ""

    def loi(*a, **k):
        raise TimeoutError
    monkeypatch.setattr(HD.lark, "call", loi)
    assert HD.email_cua("ou_4") == ""


def test_handle_tu_choi_va_gan_co_han_che(monkeypatch, la_nguoi_xem):
    kho = _kho_mau()
    monkeypatch.setattr(HD, "_kho", kho)
    co = []
    monkeypatch.setattr(memory_store, "danh_dau_phien_han_che", lambda chat, tool: co.append(tool))
    d = json.loads(HD._handle({"tu": "2026-10-08", "den": "2026-10-14", "phan": ["tong_quan"]}))
    assert "error" not in d and co == ["hoi_dashboard"]
    scheduler.set_current_chat_type("group")
    d = json.loads(HD._handle({}))
    assert "nhóm" in d["error"] and co == ["hoi_dashboard"]       # từ chối: không gắn cờ, không số
    scheduler.set_current_chat_type("p2p")
    assert "Tham số" in json.loads(HD._handle({"tu": "hôm qua"}))["error"]


def test_handle_kho_loi_noi_ro_khong_doan(monkeypatch, la_nguoi_xem):
    from dashboard.kho import LoiKho

    class KhoHong(GiaKho):
        def cac_du_an(self):
            raise LoiKho("không nối được kho lắng nghe (OperationalError)")
    monkeypatch.setattr(HD, "_kho", KhoHong())
    e = json.loads(HD._handle({}))["error"]
    assert "Chưa đọc được kho" in e and "dbname" not in e


# ───────────────────────────── cửa kho của Mark ─────────────────────────────
def test_kho_mark_chi_ham_doc_va_dung_dsn_cua_mark(monkeypatch):
    from dashboard import kho as K
    monkeypatch.setenv("LANG_NGHE_DSN", "dbname=lang_nghe_mark")
    monkeypatch.setenv("LANG_NGHE_WEB_DSN", "dbname=lang_nghe_web")
    km = HD.KhoMark()
    for ten in ("them_du_an", "luu_quyen", "xoa_quyen", "dat_quan_tri", "xoa_nguon", "sua_lich", "ghi_nhat_ky",
                "ket_noi", "_dsn"):
        with pytest.raises(AttributeError):
            getattr(km, ten)
    monkeypatch.setattr(K, "quyen_cua", lambda email: K._dsn())
    assert km.quyen_cua("x@hapas.vn") == "dbname=lang_nghe_mark"
    assert K._dsn() == "dbname=lang_nghe_web"              # trả lại như cũ sau lần gọi


def test_lich_doc_dung_cot_mark_duoc_doc(monkeypatch):
    import contextlib

    import lang_nghe_db
    sql = []

    class C:
        def execute(self, s, p):
            sql.append(s)
            return self

        def fetchall(self):
            return []

    monkeypatch.setattr(lang_nghe_db, "ket_noi", lambda: contextlib.nullcontext(C()))
    assert HD.KhoMark.cac_lich("hapas") == []
    cot = set(re.findall(r"\bl\.(\w+)", sql[0]))
    duoc = set(re.search(r"GRANT SELECT \(([^)]*)\) ON lich_quet TO mark",
                         _schema(), re.DOTALL).group(1).replace("\n", " ").replace(" ", "").split(","))
    assert cot <= duoc, cot - duoc
    assert "tao_boi" not in sql[0] and "sua_boi" not in sql[0]


def _schema() -> str:
    return (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql"
            ).read_text(encoding="utf-8")


def test_schema_cap_quyen_doc_nguoi_xem_theo_cot():
    s = _schema()
    assert re.search(r"GRANT SELECT \(email, vai_tro\) ON nguoi_xem TO mark;", s)
    assert not re.search(r"GRANT SELECT ON [^;]*nguoi_xem[^;]* TO mark", s)   # không cả bảng


def test_policy_cho_doc_va_brain_biet_tool():
    assert lsr_policy.decide("hoi_dashboard", {}).allowed
    assert "hoi_dashboard" not in lsr_policy._MUTATING_EXACT
    import brain
    assert "hoi_dashboard" in brain._TOOLING_NOTE and "hoi_dashboard" in brain._TOOL_CAN_XET


def test_chi_tra_so_du_an_cua_ben_nguoi_hoi(monkeypatch):
    """19/10/2026: người xem MATEMADE hỏi Mark số của dự án HAPAS → như không có dự án (không đọc
    bài nào), `cac_du_an` chỉ gồm dự án bên họ; quản trị viên thấy mọi dự án; chi phí (gói Apify)
    chỉ cộng dự án trong phạm vi."""
    from test_dashboard_app import MM_XEM, _kho_hai_ben
    kho = _kho_hai_ben()
    monkeypatch.setattr(HD, "email_cua", lambda oid: MM_XEM)
    with pytest.raises(HD.NL.LoiNhap, match="Không có dự án") as e:
        HD.tra_loi({"du_an": "hapas", "phan": ["tong_quan"]}, kho, open_id="ou_hoi",
                   bay_gio=BAY_GIO)
    assert "hapas (" not in str(e.value) and "mm (" in str(e.value)
    assert kho.goi_bai == [] and kho.goi_bl == []
    ra = HD.tra_loi({"phan": ["tong_quan"]}, kho, open_id="ou_hoi", bay_gio=BAY_GIO)
    assert ra["du_an"]["ma"] == "mm" and [d["ma"] for d in ra["cac_du_an"]] == ["mm"]
    assert ra["vai_tro_nguoi_hoi"] == "xem"
    assert all(x[0] == "mm" for x in kho.goi_bai)
    monkeypatch.setattr(HD, "email_cua", lambda oid: QL)
    ra = HD.tra_loi({"du_an": "hapas", "phan": ["tong_quan"]}, kho, open_id="ou_hoi",
                    bay_gio=BAY_GIO)
    assert {d["ma"] for d in ra["cac_du_an"]} == {"hapas", "mm"}
    assert ra["vai_tro_nguoi_hoi"] == "quan_ly"
