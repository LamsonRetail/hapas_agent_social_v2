"""`fb_ads_library` ra Lark Sheet theo dõi như Top Ads TikTok (chủ agent, 05/10/2026).

Tra ads vẫn là việc ĐỌC: agent không có `write_data` vẫn tra được, chỉ không có sheet.
Sheet dựng bằng lớp trình bày chung `trinh_bay_sheet` (08/10/2026): tab "Tổng quan" rồi tab
"Dữ liệu"; cùng lượt tra nhiều brand thì nối dòng vào tab Dữ liệu và ghi lại Tổng quan.
Lark là bản GIẢ (tests/sheet_gia) — không chạm mạng.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from sheet_gia import LarkGia  # noqa: E402

SNAP = (
    'Library ID: 111\n Started running on 1 Oct 2026\n button "=HAPAS túi mới, mua ngay '
    'hôm nay giảm 20%"\n'
    'Library ID: 222\n Started running on 3 Oct 2026\n button "Quà 20/10 cho nàng"\n'
)


@pytest.fixture
def F(monkeypatch):
    fb = pytest.importorskip("fb_ads_tool")
    import apify_tool as A
    import lsr_policy
    import memory_store
    monkeypatch.setattr(fb, "_BROWSER_OK", True)
    monkeypatch.setattr(fb, "browser_navigate",
                        lambda **k: json.dumps({"success": True, "title": "Ad Library"}),
                        raising=False)
    monkeypatch.setattr(fb, "_full_snapshot", lambda: SNAP)
    monkeypatch.setattr(fb, "browser_scroll", lambda **k: "{}", raising=False)
    monkeypatch.setattr(fb, "browser_get_images", lambda **k: json.dumps({"images": []}),
                        raising=False)
    monkeypatch.setattr(fb.time, "sleep", lambda s: None)
    gia = LarkGia()
    monkeypatch.setattr(A.lark, "call", gia.call)
    import collections
    import trinh_bay_sheet
    monkeypatch.setattr(trinh_bay_sheet, "_LOC_LUOT", collections.deque())  # trần lọc/phút
    cap: list = []
    monkeypatch.setattr(A, "_grant", lambda tok, ou: cap.append(ou) or True)
    monkeypatch.setattr(memory_store, "get_current_sender", lambda: "ou_nguoi_hoi")
    monkeypatch.setattr(lsr_policy, "quyen_phat", lambda: {"reply", "write_data"})
    fb._gia, fb._cap = gia, cap
    return fb


def _chay(F, **args):
    return json.loads(F._handle_fb_ads_library({"query": "HAPAS", "limit": 5, **args}))


def _fmt(gia, tab, cot, dong):
    st = [s for s in gia.kieu_o(tab, cot, dong) if "formatter" in s]
    return st[-1]["formatter"] if st else None


def _ngay_serial() -> int:
    hom_nay = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date()
    return (hom_nay - datetime.date(1899, 12, 30)).days


def test_co_quyen_ghi_thi_ra_sheet_moi_ad_mot_dong(F):
    kq = _chay(F)
    gia = F._gia
    assert kq["success"] and kq["ads_returned"] == 2
    assert kq["sheet_url"] == "https://x.larksuite.com/sheets/sht1" and kq["granted"] is True
    assert gia.tab_ten() == ["Tổng quan", "Dữ liệu"]
    rows = gia.o("Dữ liệu")
    assert rows[0] == F._HEADER_SHEET and len(rows) == 3
    assert rows[1][0] == 1 and rows[1][1] == "111" and rows[1][2] == "1 Oct 2026"
    assert rows[1][3].startswith("'=HAPAS"), "chặn chèn công thức vẫn còn"
    assert rows[1][4] == "https://www.facebook.com/ads/library/?id=111"
    assert rows[1][5] == "HAPAS" and rows[1][8] == "đang chạy"
    assert rows[1][9] == _ngay_serial(), "Ngày quét là ngày thật"
    assert F._cap == ["ou_nguoi_hoi"], "người hỏi phải mở được sheet"
    assert "HAPAS" in kq["title"]
    assert kq["day_du"] is True and "Đã ghi đủ 2/2" in kq["kiem_ghi"]


def test_kieu_cot_tieu_de_co_dinh_loc(F):
    _chay(F)
    gia = F._gia
    assert _fmt(gia, "Dữ liệu", 1, 2) == "#,##0"
    assert _fmt(gia, "Dữ liệu", 2, 2) == "@", "Library ID là chữ"
    assert _fmt(gia, "Dữ liệu", 10, 2) == "dd/MM/yyyy"
    assert any(s.get("backColor") == "#1F3864" for s in gia.kieu_o("Dữ liệu", 1, 1))
    assert gia.tab("Dữ liệu")["frozen"] == 1
    sid = gia.tab("Dữ liệu")["sheet_id"]
    assert [b["range"] for p, b in gia.loc() if f"/{sid}/" in p] == [f"{sid}!A1:J3"]


def test_tong_quan_mau_nhom_va_ghi_chu(F, monkeypatch):
    monkeypatch.setattr(F, "_full_snapshot", lambda: "~120 results\n" + SNAP)
    kq = _chay(F)
    assert kq["total_results"] == 120
    o = F._gia.o("Tổng quan")
    chu = " ".join(str(c) for r in o for c in r)
    assert o[0][0] == kq["title"]
    assert "Meta Ad Library" in o[1][0] and "Trang / từ khoá: HAPAS" in o[1][0]
    so = {r[0]: r[1] for r in o if len(r) > 1 and isinstance(r[0], str)}
    assert so["Số ad trong sheet (mẫu đã bóc)"] == 2 and so["Số trang / từ khoá đã tra"] == 1
    assert "THEO TRANG / TỪ KHOÁ" in chu and "THEO QUỐC GIA" in chu and "THEO NỀN TẢNG LỌC" in chu
    assert "Ad Library báo khoảng 120 kết quả; sheet có 2 ad — còn khoảng 118 ad chưa đưa vào" in chu
    assert "limit lớn hơn" in chu and "cắt ở 700 ký tự" in chu
    assert "ou_nguoi_hoi" not in chu


def test_khong_co_write_data_van_tra_duoc_nhung_khong_ghi(F, monkeypatch):
    import lsr_policy
    monkeypatch.setattr(lsr_policy, "quyen_phat", lambda: {"reply"})
    kq = _chay(F)
    assert kq["success"] and kq["ads_returned"] == 2
    assert kq["sheet_url"] is None and F._gia.bt == {}


def test_ghi_sheet_hong_khong_lam_hong_ket_qua(F, monkeypatch):
    import apify_tool as A

    def hong(t):
        raise RuntimeError("lark 500 token=abc123")
    monkeypatch.setattr(A, "_create_sheet", hong)
    kq = _chay(F)
    assert kq["success"] and kq["ads_returned"] == 2
    assert kq["sheet_url"] is None and kq["loi_sheet"]
    assert "abc123" not in kq["loi_sheet"], "không lộ token trong lỗi"


def test_trang_tri_hong_van_co_link_va_du_lieu(F):
    F._gia.hong = {"styles_batch_update"}
    kq = _chay(F)
    assert kq["sheet_url"] and not kq["loi_sheet"] and kq["granted"] is True
    rows = F._gia.o("Dữ liệu")
    assert len(rows) == 3 and rows[2][1] == "222"
    assert isinstance(rows[1][9], str) and rows[1][9].count("/") == 2, "ngày ghi dạng chữ"
    assert kq["day_du"] is True


def test_page_id_va_ten_tu_dat(F):
    kq = json.loads(F._handle_fb_ads_library({"page_id": "1234", "title": "Theo dõi HAPAS"}))
    assert kq["title"] == "Theo dõi HAPAS"
    assert F._gia.o("Dữ liệu")[1][5] == "page_id 1234"


def test_khong_co_ad_thi_khong_tao_sheet(F, monkeypatch):
    monkeypatch.setattr(F, "_full_snapshot", lambda: "No ads match your search")
    kq = _chay(F)
    assert kq["ads_returned"] == 0 and F._gia.bt == {}


def test_cung_luot_nhieu_brand_ghi_noi_mot_sheet(F, monkeypatch):
    """02/10/2026 một lượt tra 8 brand — phải ra MỘT sheet, không phải 8."""
    import contextvars
    import dong_ho_luot
    import scheduler
    monkeypatch.setattr(F, "_SHEET_LUOT", {})
    ctx = contextvars.copy_context()

    def luot():
        scheduler.set_current_chat("lark:cli_x:oc_1")
        dong_ho_luot.bat_dau()
        a = json.loads(F._handle_fb_ads_library({"query": "HAPAS"}))
        b = json.loads(F._handle_fb_ads_library({"query": "PEDRO"}))
        return a, b
    a, b = ctx.run(luot)
    gia = F._gia
    assert [bt.title for bt in gia.bt.values()] == [a["title"]], "chỉ tạo MỘT sheet cho cả lượt"
    assert a["sheet_url"] == b["sheet_url"] and b["sheet_ghi_noi"] is True
    rows = gia.o("Dữ liệu")
    assert len(rows) == 5                                  # tiêu đề + 2 + 2 ad
    assert rows[3][0] == 3 and rows[3][5] == "PEDRO", "nối dưới, STT chạy tiếp"
    assert rows[3][1] == "111" and rows[4][3] == "Quà 20/10 cho nàng"
    # Dòng nối: trang trí phủ dòng mới, lọc phủ tới dòng cuối, đọc lại kiểm đủ.
    sid = gia.tab("Dữ liệu")["sheet_id"]
    assert [b["range"] for p, b in gia.loc() if f"/{sid}/" in p][-1] == f"{sid}!A1:J5"
    assert _fmt(gia, "Dữ liệu", 2, 5) == "@"
    assert b["day_du"] is True and "Đã ghi đủ 4/4" in b["kiem_ghi"]
    # Tổng quan ghi lại theo toàn bộ dòng của lượt.
    o = gia.o("Tổng quan")
    so = {r[0]: r[1] for r in o if len(r) > 1 and isinstance(r[0], str)}
    assert so["Số ad trong sheet (mẫu đã bóc)"] == 4 and so["Số trang / từ khoá đã tra"] == 2
    chu = " ".join(str(c) for r in o for c in r)
    assert "PEDRO" in chu and "HAPAS (VN" in chu and "PEDRO (VN" in chu
    assert gia.tab_ten() == ["Tổng quan", "Dữ liệu"], "không thêm tab Tổng quan thứ hai"

    # Lượt sau (mốc mới) thì sheet mới.
    ctx2 = contextvars.copy_context()
    ctx2.run(luot)
    assert len(gia.bt) == 2


def test_ngoai_luot_luon_tao_sheet_moi(F, monkeypatch):
    import contextvars
    monkeypatch.setattr(F, "_SHEET_LUOT", {})
    contextvars.Context().run(_chay, F)
    contextvars.Context().run(_chay, F)
    assert len(F._gia.bt) == 2


def test_noi_hong_van_tra_link_sheet_cua_luot(F, monkeypatch):
    """Brand thứ hai không nối được thì sheet của lượt VẪN CÒN — không được báo 'không có'."""
    import contextvars
    import apify_tool as A
    import dong_ho_luot
    import scheduler
    monkeypatch.setattr(F, "_SHEET_LUOT", {})
    goc = A._write_values

    def ghi(tok, sid, v, dong_dau=1, cot_dau=1):
        if v and len(v[0]) > 5 and v[0][5] == "PEDRO":
            raise RuntimeError("lark 503 token=xyz")
        return goc(tok, sid, v, dong_dau=dong_dau, cot_dau=cot_dau)
    monkeypatch.setattr(A, "_write_values", ghi)

    def luot():
        scheduler.set_current_chat("lark:cli_x:oc_2")
        dong_ho_luot.bat_dau()
        a = json.loads(F._handle_fb_ads_library({"query": "HAPAS"}))
        b = json.loads(F._handle_fb_ads_library({"query": "PEDRO"}))
        c = json.loads(F._handle_fb_ads_library({"query": "VASCARA"}))
        return a, b, c
    a, b, c = contextvars.copy_context().run(luot)
    assert b["sheet_url"] == a["sheet_url"] and b["granted"] is True
    assert b["loi_sheet"] and "xyz" not in b["loi_sheet"]
    assert c["sheet_url"] == a["sheet_url"] and not c["loi_sheet"]
    rows = F._gia.o("Dữ liệu")
    assert len(rows) == 5 and rows[3][5] == "VASCARA" and rows[3][0] == 3, \
        "lần nối hỏng không làm lệch dòng của lần sau"
    chu = " ".join(str(x) for r in F._gia.o("Tổng quan") for x in r)
    assert "PEDRO" not in chu, "Tổng quan không kể brand chưa nối được"


def test_cap_quyen_hong_van_luu_sheet_cua_luot(F, monkeypatch):
    import contextvars
    import apify_tool as A
    import dong_ho_luot
    import scheduler
    monkeypatch.setattr(F, "_SHEET_LUOT", {})
    monkeypatch.setattr(A, "_grant", lambda tok, ou: False)

    def luot():
        scheduler.set_current_chat("lark:cli_x:oc_3")
        dong_ho_luot.bat_dau()
        return (json.loads(F._handle_fb_ads_library({"query": "HAPAS"})),
                json.loads(F._handle_fb_ads_library({"query": "PEDRO"})))
    a, b = contextvars.copy_context().run(luot)
    assert a["sheet_url"] and a["granted"] is False
    assert b["sheet_url"] == a["sheet_url"] and len(F._gia.bt) == 1


def test_ten_tu_dat_khong_qua_90_ky_tu(F):
    kq = _chay(F, query="x" * 200)
    assert len(kq["title"]) <= 90
