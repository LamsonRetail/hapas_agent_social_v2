"""Ô "Khoảng ngày" + so sánh + thanh lọc + gộp tuần / tháng của trang Quảng cáo (25/10/2026, chủ
dự án): khoảng nhanh hết ở ngày cuối có số, kỳ so sánh (kỳ liền trước / cùng kỳ tháng trước /
không), `ss=khong` không chạy truy vấn kỳ trước, biểu đồ gộp theo tuần / tháng ở máy chủ, nhãn
khoảng từng mục, "Số tới hết", khán giả có cửa sổ riêng, mọi liên kết / biểu mẫu giữ đủ tham số."""
from __future__ import annotations

import datetime
import html
import pathlib
import re
from urllib.parse import parse_qs, urlencode, urlsplit

from test_kenh_dang import GiaKhoKenh
from test_meta_ads_dashboard import _app_hai_nen_tang
from test_sheet_qc import GiaKhoSheet, _form
from test_tiktok_ads import MM_2, QL, _co_so, _tao_app, dang_nhap

from dashboard import quang_cao as QC

GOC = pathlib.Path(__file__).resolve().parent.parent
D = datetime.date
Q = "tu=2026-10-12&den=2026-10-18"
NGAY_CUOI = "2026-10-18"                 # ngày cuối có số của kho giả (_co_so đồng bộ 12–18/10)


def _ve(kho_qc=None):
    app, c, kho, kq, tt, dv = _co_so(_tao_app(kho_qc=kho_qc))
    dang_nhap(c, QL)
    return app, c, kq


def _href(t: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(r'href="([^"]+)"', t)]


def _tham(h: str) -> dict:
    return parse_qs(urlsplit(h).query)


def _khoi(t: str, dau: str, cuoi: str = "</form>") -> str:
    return t.split(dau)[1].split(cuoi)[0]


# ───────────────────────────── 1. khoảng nhanh (hàm thuần) ─────────────────────────────
def _nhanh(moc, hom_qua):
    return {x["ma"]: (x["nhan"], x["tu"], x["den"]) for x in QC.khoang_nhanh(moc, hom_qua)}


def test_khoang_nhanh_het_o_moc():
    hq = D(2026, 10, 24)
    k = _nhanh(hq, hq)
    assert list(k) == ["1", "7", "14", "30", "thang_nay", "thang_truoc", "90"]
    assert k["1"] == ("Hôm qua", "2026-10-24", "2026-10-24")
    assert k["7"] == ("7 ngày", "2026-10-18", "2026-10-24")
    assert k["14"][1:] == ("2026-10-11", "2026-10-24")
    assert k["30"] == ("30 ngày", "2026-09-25", "2026-10-24")
    assert k["90"][1:] == ("2026-07-27", "2026-10-24")
    assert k["thang_nay"] == ("Tháng này", "2026-10-01", "2026-10-24")
    assert k["thang_truoc"] == ("Tháng trước", "2026-09-01", "2026-09-30")       # trọn tháng


def test_khoang_nhanh_dong_bo_tre_va_mep_thang():
    # Số mới tới 22/10 (hôm qua là 24/10): mọi khoảng hết ở 22/10, "Hôm qua" đổi tên.
    k = _nhanh(D(2026, 10, 22), D(2026, 10, 24))
    assert k["1"] == ("Ngày 22/10", "2026-10-22", "2026-10-22")
    assert k["30"][1:] == ("2026-09-23", "2026-10-22")
    assert all(v[2] == "2026-10-22" for m, v in k.items() if m != "thang_truoc")
    # Mốc là ngày 1: "Tháng này" một ngày; tháng trước là tháng 2 (năm nhuận 29 ngày).
    k = _nhanh(D(2024, 3, 1), D(2024, 3, 1))
    assert k["thang_nay"][1:] == ("2024-03-01", "2024-03-01")
    assert k["thang_truoc"][1:] == ("2024-02-01", "2024-02-29")
    # Qua năm.
    k = _nhanh(D(2026, 1, 3), D(2026, 1, 3))
    assert k["thang_truoc"][1:] == ("2025-12-01", "2025-12-31")
    assert k["7"][1:] == ("2025-12-28", "2026-01-03")


def test_ngay_moc_kep_hom_qua():
    hq = D(2026, 10, 24)
    assert QC.ngay_moc(None, hq) == hq                                       # chưa có số
    assert QC.ngay_moc(D(2026, 10, 22), hq) == D(2026, 10, 22)
    assert QC.ngay_moc(D(2026, 10, 25), hq) == hq                            # có số hôm nay
    assert QC.ngay_moc(datetime.datetime(2026, 10, 20, 6, 30), hq) == D(2026, 10, 20)
    assert QC.ngay_moc("2026-10-19", hq) == D(2026, 10, 19)
    assert QC.ngay_moc("rác", hq) == hq


# ───────────────────────────── 2. kỳ so sánh ─────────────────────────────
def test_ky_so_sanh_ba_kieu_va_kep_ngay():
    tu, den = D(2026, 10, 12), D(2026, 10, 18)
    assert QC.ky_so_sanh(tu, den) == QC.khoang_truoc(tu, den) == (D(2026, 10, 5), D(2026, 10, 11))
    assert QC.ky_so_sanh(tu, den, "truoc") == (D(2026, 10, 5), D(2026, 10, 11))
    assert QC.ky_so_sanh(tu, den, "khong") is None
    assert QC.ky_so_sanh(tu, den, "thang_truoc") == (D(2026, 9, 12), D(2026, 9, 18))
    # Kẹp ngày cuối tháng: 29–31/03 → 28/02 (năm thường), 29/02 (năm nhuận).
    assert QC.ky_so_sanh(D(2026, 3, 29), D(2026, 3, 31), "thang_truoc") == (D(2026, 2, 28),
                                                                           D(2026, 2, 28))
    assert QC.ky_so_sanh(D(2024, 3, 30), D(2024, 3, 31), "thang_truoc") == (D(2024, 2, 29),
                                                                           D(2024, 2, 29))
    # Trọn tháng → trọn tháng trước (không cụt 28/01, không lố sang tháng 3).
    assert QC.ky_so_sanh(D(2026, 2, 1), D(2026, 2, 28), "thang_truoc") == (D(2026, 1, 1),
                                                                          D(2026, 1, 31))
    assert QC.ky_so_sanh(D(2026, 3, 1), D(2026, 3, 31), "thang_truoc") == (D(2026, 2, 1),
                                                                          D(2026, 2, 28))
    assert QC.ky_so_sanh(D(2026, 5, 1), D(2026, 5, 31), "thang_truoc") == (D(2026, 4, 1),
                                                                          D(2026, 4, 30))
    # Qua năm.
    assert QC.ky_so_sanh(D(2026, 1, 10), D(2026, 1, 20), "thang_truoc") == (D(2025, 12, 10),
                                                                           D(2025, 12, 20))
    assert QC.lui_thang(D(2026, 5, 31)) == D(2026, 4, 30)
    assert QC.lui_thang(D(2026, 1, 31), 13) == D(2024, 12, 31)


def test_doc_so_sanh():
    assert QC.doc_so_sanh({}) == "truoc"
    assert QC.doc_so_sanh({"ss": "khong"}) == "khong"
    assert QC.doc_so_sanh({"ss": "thang_truoc"}) == "thang_truoc"
    assert QC.doc_so_sanh({"ss": "'; DROP"}) == "truoc"
    assert QC.doc_so_sanh(None) == "truoc"


def _theo_doi(kq):
    """Ghi mọi (tu, den) của qc_tong / ma_cd_theo_ten."""
    goi = []
    goc_tong, goc_cd = kq.qc_tong, kq.ma_cd_theo_ten

    def tong(ids, tu, den, cds=None):
        goi.append(("tong", tu, den))
        return goc_tong(ids, tu, den, cds=cds)

    def ma_cd(ids, tu, den, loc):
        goi.append(("cd", tu, den))
        return goc_cd(ids, tu, den, loc)
    kq.qc_tong, kq.ma_cd_theo_ten = tong, ma_cd
    return goi


def test_ss_khong_bo_truy_van_ky_truoc():
    _app, c, kq = _ve()
    goi = _theo_doi(kq)
    d = c.get(f"/api/qc?{Q}&ss=khong&cd_mot=a").json()
    assert d["so_sanh"] == "khong" and d["ky_truoc"] is None
    assert all(v is None for v in d["doi"].values())
    assert goi and all(tu >= D(2026, 10, 12) for _, tu, _den in goi)          # không kỳ trước nào
    assert d["ten_cd"]["so_chien_dich_truoc"] == 0
    # Mặc định: có truy vấn kỳ trước 05–11/10.
    goi.clear()
    d = c.get(f"/api/qc?{Q}").json()
    assert d["so_sanh"] == "truoc" and d["ky_truoc"] == {"tu": "2026-10-05", "den": "2026-10-11"}
    assert ("tong", D(2026, 10, 5), D(2026, 10, 11)) in goi
    # Cùng kỳ tháng trước.
    goi.clear()
    d = c.get(f"/api/qc?{Q}&ss=thang_truoc").json()
    assert d["ky_truoc"] == {"tu": "2026-09-12", "den": "2026-09-18"}
    assert ("tong", D(2026, 9, 12), D(2026, 9, 18)) in goi


def test_trang_ss_khong_an_tang_giam():
    _app, c, _kq = _ve()
    t = c.get(f"/quang-cao?{Q}&ss=khong").text
    assert "không so sánh</span>" in _khoi(t, 'id="qc-moi"', "</p>")
    kpi = _khoi(t, 'id="qc-kpi"', "</section>")
    assert "so với kỳ trước" not in kpi and "kỳ trước chưa có số" not in kpi and "▲▼" not in kpi
    assert 'value="khong" selected' in t
    t = c.get(f"/quang-cao?{Q}&ss=thang_truoc").text
    assert "so với cùng kỳ tháng trước, 12/09 – 18/09" in _khoi(t, 'id="qc-moi"', "</p>")
    t = c.get(f"/quang-cao?{Q}").text
    assert "so với 05/10 – 11/10" in _khoi(t, 'id="qc-moi"', "</p>")
    assert "▲▼ so với 05/10 – 11/10" in _khoi(t, 'id="qc-kpi"', "</section>")


# ───────────────────────────── 3. gộp tuần / tháng ─────────────────────────────
def test_don_vi_mac_dinh_va_co():
    assert [QC.don_vi_mac_dinh(n) for n in (1, 31, 32, 120, 121, 400)] == [
        "ngay", "ngay", "tuan", "tuan", "thang", "thang"]
    assert QC.don_vi_co(D(2026, 10, 12), D(2026, 10, 18)) == ["ngay"]
    assert QC.don_vi_co(D(2026, 10, 1), D(2026, 10, 20)) == ["ngay", "tuan"]
    assert QC.don_vi_co(D(2026, 9, 25), D(2026, 10, 24)) == ["ngay", "tuan", "thang"]
    assert QC.don_vi_co(D(2025, 9, 1), D(2026, 9, 30)) == ["ngay", "tuan", "thang"]


def _ngay(tu, den, **them):
    ra, d = [], tu
    while d <= den:
        ra.append({"ngay": d.isoformat(), "chi": 10, "hien_thi": d.day, "reach": 5, **them})
        d += datetime.timedelta(days=1)
    return ra


def test_gop_tuan_iso_cat_theo_khoang():
    tu, den = D(2026, 10, 1), D(2026, 10, 20)          # thứ Năm 01/10 → thứ Ba 20/10
    w = QC.gop_ky(_ngay(tu, den), "tuan", tu, den)
    assert [(x["ngay"], x["den"], x["so_ngay"], x["nhan"]) for x in w] == [
        ("2026-10-01", "2026-10-04", 4, "Tuần 01/10"),        # tuần đầu thiếu (thứ Năm → CN)
        ("2026-10-05", "2026-10-11", 7, "Tuần 05/10"),
        ("2026-10-12", "2026-10-18", 7, "Tuần 12/10"),
        ("2026-10-19", "2026-10-20", 2, "Tuần 19/10")]
    assert [x["chi"] for x in w] == [40, 70, 70, 20]
    assert w[1]["hien_thi"] == sum(range(5, 12))
    assert all(x["reach"] is None for x in w)                  # không cộng người duy nhất
    assert sum(x["chi"] for x in w) == 200


def test_gop_thang_va_theo_nen_tang():
    tu, den = D(2026, 8, 20), D(2026, 10, 3)
    rows = _ngay(tu, den, nen_tang="tiktok") + _ngay(tu, den, nen_tang="meta")[:5]
    m = QC.gop_ky(rows, "thang", tu, den)
    assert [(x["ngay"], x["nen_tang"], x["so_ngay"], x["nhan"]) for x in m] == [
        ("2026-08-20", "meta", 12, "Tháng 08/2026"), ("2026-08-20", "tiktok", 12, "Tháng 08/2026"),
        ("2026-09-01", "tiktok", 30, "Tháng 09/2026"), ("2026-10-01", "tiktok", 3, "Tháng 10/2026")]
    assert m[0]["chi"] == 50 and m[1]["chi"] == 120 and m[2]["chi"] == 300
    # Dòng ngoài khoảng bị bỏ; đơn vị "ngay" giữ nguyên.
    assert QC.gop_ky(rows, "thang", D(2026, 9, 1), D(2026, 9, 30))[0]["chi"] == 300
    assert QC.gop_ky(rows[:2], "ngay", tu, den) == rows[:2]


def test_api_theo_ky_khop_tong():
    _app, c, kq = _ve()
    d = c.get("/api/qc?tu=2026-08-01&den=2026-10-18").json()                # 79 ngày → tuần
    ky = d["theo_ky"]
    assert ky["mac_dinh"] == "tuan" and ky["co"] == ["ngay", "tuan", "thang"]
    for dv in ("tuan", "thang"):
        assert sum(x["hien_thi"] for x in ky[dv]["chung"]) == d["kpi"]["hien_thi"], dv
        assert sum(x["hien_thi"] for x in ky[dv]["nen_tang"]) == d["kpi"]["hien_thi"], dv
    assert ky["tuan"]["chung"][-1]["nhan"] == "Tuần 12/10"
    assert c.get(f"/api/qc?{Q}").json()["theo_ky"] == {"mac_dinh": "ngay", "co": ["ngay"]}


# ───────────────────────────── 4. trang: ô khoảng ngày, nhãn, độ mới ─────────────────────────────
def test_mac_dinh_het_o_ngay_cuoi_co_so():
    _app, c, _kq = _ve()
    d = c.get("/api/qc").json()
    assert d["den"] == NGAY_CUOI and d["tu"] == "2026-09-19" and d["khoang"]["so_ngay"] == 30
    assert d["khoang"]["moc"] == NGAY_CUOI and d["khoang"]["chua_du"] is False
    t = c.get("/quang-cao").text
    assert 'data-tu="2026-09-19" data-den="2026-10-18" data-max="2026-10-18"' in t


def test_trang_o_khoang_ngay_khoang_nhanh_va_nhan():
    _app, c, _kq = _ve(GiaKhoKenh())
    t = c.get(f"/quang-cao?{Q}").text
    loc = _khoi(t, 'id="qc-loc"')
    o = _khoi(loc, 'data-o="khoang-ngay"', 'data-o="loc-ten-cd"')
    # Ô gọn có biểu tượng lịch (SVG, không emoji) + chữ khoảng; hai ô ngày chỉ còn trong bảng nổi.
    assert '<svg class="bt qc-kn__bt"' in o and ">12/10 – 18/10/2026 · 7 ngày</span>" in o
    assert "📅" not in t and loc.count('type="date"') == 2 and o.count('type="date"') == 2
    nhanh = _khoi(o, 'aria-label="Khoảng nhanh"', "</nav>")
    nhan = re.findall(r'data-kn-nhanh="[^"]+"[^>]*>([^<]+)</a>', nhanh)
    assert nhan == ["Ngày 18/10", "7 ngày", "14 ngày", "30 ngày", "Tháng này", "Tháng trước",
                    "90 ngày"]
    assert "data-kn-tuy-chon" in nhanh and ">Tuỳ chọn</button>" in nhanh
    h = {_tham(x)["tu"][0] + "/" + _tham(x)["den"][0] for x in _href(nhanh)}
    assert "2026-10-12/2026-10-18" in h and "2026-09-01/2026-09-30" in h      # 7 ngày, tháng trước
    assert re.search(r'data-kn-nhanh="7" aria-current="true"', nhanh)
    for ma, ten in QC.SO_SANH.items():
        assert f'<option value="{ma}"' in o and ten in o
    assert "data-kn-lich" in o and "data-kn-ap-dung" in o and 'data-toi-da="400"' in o
    # Độ mới: "Số tới hết 18/10"; khoảng trong số → không "!".
    assert 'data-o="so-toi-het">Số tới hết 18/10</span>' in o
    assert 'data-o="khoang-chua-du"' not in t
    # Nhãn khoảng ở KPI, Theo ngày, Chiến dịch và quảng cáo, Theo kênh đăng.
    assert t.count('data-o="nhan-khoang">12/10 – 18/10</span>') == 4
    for dau in ('id="qc-kpi"', 'id="qc-xh-tieu-de"', 'id="qc-top-tieu-de"', 'id="qc-kenh-tieu-de"'):
        assert 'data-o="nhan-khoang"' in t.split(dau)[1][:900], dau
    # Khán giả: cửa sổ riêng — 26/10/2026 bỏ dòng chữ nhỏ; cửa sổ nằm trong nút (i) của tiêu đề.
    kg = _khoi(t, 'id="qc-kg-tieu-de"', "</section>")
    assert 'data-o="kg-cua-so"' not in kg and "cửa sổ mới nhất" not in kg
    assert re.search(r'data-goi-y="Phân bố lượt hiển thị trong cửa sổ 30 ngày gần nhất \(\d\d/\d\d – '
                     r'\d\d/\d\d/\d{4}\), đọc lại mỗi tuần — không theo khoảng ngày đang lọc', kg)
    # Nút gộp + tiêu đề "Theo ngày".
    assert 'id="qc-don-vi"' in t and 'Theo <span id="qc-xh-don-vi">ngày</span>' in t
    # Tóm tắt điện thoại.
    assert _khoi(t, 'class="qc-loc-khung__gia-tri">', "</span>") == (
        "Tất cả bên · Tất cả tài khoản (4) · 7 ngày")


def test_trang_canh_bao_khi_khoang_qua_ngay_cuoi():
    _app, c, _kq = _ve()
    t = c.get("/quang-cao?tu=2026-10-12&den=2026-10-21").text
    canh = re.search(r'<button type="button" class="goi-y goi-y--canh" data-o="khoang-chua-du" '
                     r'data-goi-y="([^"]+)">!</button>', t)
    assert canh and "tới hết 18/10" in html.unescape(canh.group(1))
    assert "(hôm nay chưa hết ngày)" not in html.unescape(canh.group(1))


def test_thanh_loc_mot_hang():
    h = _app_hai_nen_tang()
    c = h.c
    dang_nhap(c, QL)
    t = c.get(f"/quang-cao?{Q}&ss=khong").text
    loc = _khoi(t, 'id="qc-loc"')
    # Bên, Tài khoản, Nền tảng, Khoảng ngày, Tên chiến dịch theo thứ tự, trong CÙNG biểu mẫu.
    vi_tri = [loc.index(x) for x in ('name="ben"', 'data-o="chon-tk"', 'data-o="loc-nen-tang"',
                                     'data-o="khoang-ngay"', 'data-o="loc-ten-cd"')]
    assert vi_tri == sorted(vi_tri)
    assert 'data-o="thanh-loc"' in loc and 'select name="ben" data-tu-gui' in loc
    assert 'data-loc-xem>Xem</button>' in loc                        # không JS vẫn còn nút Xem
    # Nền tảng không còn ở góc đầu trang.
    assert t.index('data-o="loc-nen-tang"') > t.index('id="qc-loc"')
    tk = _khoi(loc, 'data-o="chon-tk"', 'data-o="loc-nen-tang"')
    assert ">Áp dụng</button>" in tk and "Bấm Xem" not in tk
    # Nút nền tảng: giữ ss, bỏ chọn tài khoản.
    nen = _href(_khoi(loc, 'data-o="loc-nen-tang"', "</nav>"))
    assert len(nen) == 3 and all(_tham(x)["ss"] == ["khong"] and "tk" not in _tham(x) for x in nen)


# ───────────────────────────── 5. giữ tham số ─────────────────────────────
def test_lien_ket_va_bieu_mau_giu_ss_va_moi_loc():
    _app, c, _kq = _ve(GiaKhoKenh())
    # (cd_co / cd_mot / cd_khong: test_qc_loc_ten_cd — cùng `loc` với ss nên đi cùng nhau.)
    q = f"{Q}&" + urlencode({"ss": "khong", "tk": [MM_2], "kt": "abc",
                             "tim": "x", "sap": "hien_thi"}, doseq=True)
    t = c.get(f"/quang-cao?{q}").text
    loc = _khoi(t, 'id="qc-loc"')
    # Khoảng nhanh: giữ ss, tài khoản / tên chiến dịch / tìm / kênh.
    nhanh = _href(_khoi(loc, 'aria-label="Khoảng nhanh"', "</nav>"))
    assert len(nhanh) == 7
    for h in nhanh:
        p = _tham(h)
        assert p["ss"] == ["khong"] and p["tk"] == [MM_2], h
        assert p["kt"] == ["abc"] and p["tim"] == ["x"] and p["sap"] == ["hien_thi"], h
    # Thanh lọc giữ kênh (kt) + tìm; select ss mang giá trị đang dùng.
    assert '<input type="hidden" name="kt" value="abc">' in loc
    assert '<input type="hidden" name="tim" value="x">' in loc
    # Biểu mẫu bảng, kênh, Xuất Sheet: ss ẩn.
    an = '<input type="hidden" name="ss" value="khong">'
    for dau in ('data-o="loc-bang"', 'class="qc-bang-loc qc-kenh-loc"', 'data-o="tao-sheet"'):
        assert an in _khoi(t, dau), dau
    # Xếp cột / trang / kênh giữ ss.
    ds = [html.unescape(h) for h in re.findall(r'class="qc-sap[^"]*" href="([^"]+)"', t)]
    assert ds and all(_tham(h)["ss"] == ["khong"] for h in ds)
    # Mặc định (kỳ liền trước): không ghi ss vào liên kết / ô ẩn — URL gọn.
    t = c.get(f"/quang-cao?{Q}").text
    assert 'name="ss" value="truoc"' not in t and "ss=truoc" not in t
    assert all("ss" not in _tham(h) for h in _href(_khoi(t, 'aria-label="Khoảng nhanh"', "</nav>")))


def test_xuat_sheet_quay_lai_giu_ss():
    app, c, _kho, _kq, *_ = _co_so(_tao_app())
    app.state.kho_sheet = GiaKhoSheet()
    csrf = dang_nhap(c, QL)
    r = c.post("/quang-cao/tao-sheet", data=_form(csrf, ss="thang_truoc", tk=None))
    assert r.status_code in (302, 303) and _tham(r.headers["location"])["ss"] == ["thang_truoc"]


def test_js_css_thanh_phan_dung_chung():
    js = (GOC / "dashboard" / "static" / "khoang_ngay.js").read_text(encoding="utf-8")
    css = (GOC / "dashboard" / "static" / "khoang_ngay.css").read_text(encoding="utf-8")
    qc = (GOC / "dashboard" / "static" / "qc.js").read_text(encoding="utf-8")
    qcc = (GOC / "dashboard" / "static" / "qc.css").read_text(encoding="utf-8")
    tpl = (GOC / "dashboard" / "templates" / "quang_cao.html").read_text(encoding="utf-8")
    # Lịch: lưới ARIA, phím, khoá ngày sau mốc, không chèn HTML.
    for chu in ('"role", "grid"', '"gridcell"', '"aria-selected"', '"aria-disabled"', '"PageUp"',
                '"PageDown"', '"Home"', '"End"', '"ArrowLeft"', "mouseover", "data-kn-tuy-chon",
                "textContent", "data-toi-da"):
        assert chu in js, chu
    assert "innerHTML" not in js and "eval(" not in js
    assert ".kn-o:focus-visible" in css and "@media (max-width: 640px)" in css
    assert "khoang_ngay.js" in tpl and "khoang_ngay.css" in tpl and "<script>" not in tpl
    # Thanh lọc: ẩn nút Xem khi có JS, đổi Bên là gửi; dính đầu trang ở máy tính.
    assert "data-loc-xem" in qc and "xem.hidden = true" in qc and "theo_ky" in qc
    assert "position: sticky" in qcc.split("@media (min-width: 761px)")[1].split("}\n}")[0]
    dt = qcc.split("@media (max-width: 640px)")[1].split("\n}\n")[0]
    assert ".qc-loc-khung__tom {" in dt
