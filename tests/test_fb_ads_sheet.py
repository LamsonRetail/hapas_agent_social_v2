"""`fb_ads_library` ra Lark Sheet theo dõi như Top Ads TikTok (chủ agent, 05/10/2026).

Tra ads vẫn là việc ĐỌC: agent không có `write_data` vẫn tra được, chỉ không có sheet.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

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
    ghi = {"tao": [], "rows": [], "cap": []}
    monkeypatch.setattr(A, "_create_sheet",
                        lambda t: ghi["tao"].append(t) or ("tok1", "https://x/sheets/tok1"))
    monkeypatch.setattr(A, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(A, "_write_values",
                        lambda tok, sid, v, dong_dau=1: ghi["rows"].append((dong_dau, v)))
    monkeypatch.setattr(A, "_grant", lambda tok, ou: ghi["cap"].append(ou) or True)
    monkeypatch.setattr(memory_store, "get_current_sender", lambda: "ou_nguoi_hoi")
    monkeypatch.setattr(lsr_policy, "quyen_phat", lambda: {"reply", "write_data"})
    fb._ghi_test = ghi
    return fb


def _chay(F, **args):
    return json.loads(F._handle_fb_ads_library({"query": "HAPAS", "limit": 5, **args}))


def test_co_quyen_ghi_thi_ra_sheet_moi_ad_mot_dong(F):
    kq = _chay(F)
    assert kq["success"] and kq["ads_returned"] == 2
    assert kq["sheet_url"] == "https://x/sheets/tok1" and kq["granted"] is True
    assert len(F._ghi_test["rows"]) == 1 and F._ghi_test["rows"][0][0] == 1
    rows = F._ghi_test["rows"][0][1]
    assert rows[0] == F._HEADER_SHEET and len(rows) == 3
    assert rows[1][1] == "111" and rows[1][2] == "1 Oct 2026"
    assert rows[1][4] == "https://www.facebook.com/ads/library/?id=111"
    assert rows[1][5] == "HAPAS" and rows[1][8] == "đang chạy"
    assert F._ghi_test["cap"] == ["ou_nguoi_hoi"], "người hỏi phải mở được sheet"
    assert "HAPAS" in kq["title"]


def test_khong_co_write_data_van_tra_duoc_nhung_khong_ghi(F, monkeypatch):
    import lsr_policy
    monkeypatch.setattr(lsr_policy, "quyen_phat", lambda: {"reply"})
    kq = _chay(F)
    assert kq["success"] and kq["ads_returned"] == 2
    assert kq["sheet_url"] is None and F._ghi_test["tao"] == []


def test_ghi_sheet_hong_khong_lam_hong_ket_qua(F, monkeypatch):
    import apify_tool as A

    def hong(t):
        raise RuntimeError("lark 500 token=abc123")
    monkeypatch.setattr(A, "_create_sheet", hong)
    kq = _chay(F)
    assert kq["success"] and kq["ads_returned"] == 2
    assert kq["sheet_url"] is None and kq["loi_sheet"]
    assert "abc123" not in kq["loi_sheet"], "không lộ token trong lỗi"


def test_page_id_va_ten_tu_dat(F):
    kq = json.loads(F._handle_fb_ads_library({"page_id": "1234", "title": "Theo dõi HAPAS"}))
    assert kq["title"] == "Theo dõi HAPAS"
    assert F._ghi_test["rows"][0][1][1][5] == "page_id 1234"


def test_khong_co_ad_thi_khong_tao_sheet(F, monkeypatch):
    monkeypatch.setattr(F, "_full_snapshot", lambda: "No ads match your search")
    kq = _chay(F)
    assert kq["ads_returned"] == 0 and F._ghi_test["tao"] == []


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
    assert F._ghi_test["tao"] == [a["title"]], "chỉ tạo MỘT sheet cho cả lượt"
    assert a["sheet_url"] == b["sheet_url"] and b["sheet_ghi_noi"] is True
    (d1, r1), (d2, r2) = F._ghi_test["rows"]
    assert d1 == 1 and len(r1) == 3            # tiêu đề + 2 ad
    assert d2 == 4 and r2[0][0] == 3 and r2[0][5] == "PEDRO", "nối dưới, STT chạy tiếp"

    # Lượt sau (mốc mới) thì sheet mới.
    ctx2 = contextvars.copy_context()
    ctx2.run(luot)
    assert len(F._ghi_test["tao"]) == 2


def test_ngoai_luot_luon_tao_sheet_moi(F, monkeypatch):
    import contextvars
    monkeypatch.setattr(F, "_SHEET_LUOT", {})
    contextvars.Context().run(_chay, F)
    contextvars.Context().run(_chay, F)
    assert len(F._ghi_test["tao"]) == 2


def test_noi_hong_van_tra_link_sheet_cua_luot(F, monkeypatch):
    """Brand thứ hai không nối được thì sheet của lượt VẪN CÒN — không được báo 'không có'."""
    import contextvars
    import apify_tool as A
    import dong_ho_luot
    import scheduler
    monkeypatch.setattr(F, "_SHEET_LUOT", {})
    lan = []

    def ghi(tok, sid, v, dong_dau=1):
        lan.append(dong_dau)
        if len(lan) == 2:
            raise RuntimeError("lark 503 token=xyz")
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
    assert lan == [1, 4, 4], "lần nối hỏng không làm lệch dòng của lần sau"


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
    assert b["sheet_url"] == a["sheet_url"] and len(F._ghi_test["tao"]) == 1


def test_ten_tu_dat_khong_qua_90_ky_tu(F):
    kq = _chay(F, query="x" * 200)
    assert len(kq["title"]) <= 90
