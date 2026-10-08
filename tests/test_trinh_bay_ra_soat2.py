"""Rà soát lần 2 (09/10/2026) lớp trình bày — Lark GIẢ, không mạng.

1. Cứu bảng tí hon (Tổng quan + thêm tab đều hỏng → ghi dưới tab dữ liệu đầu) KHÔNG được
   bỏ cột của tab dữ liệu đã có (trước đây xoá mất cột C..H của bảng 8 cột).
2. Ghi nối (fb_ads cùng lượt): đọc lại dòng CUỐI vừa nối, không phải dòng cuối cũ.
3. Ghi lại Tổng quan: ghi bản mới trước, xoá bản cũ sau; ghi hỏng thì bản cũ còn nguyên và
   `day_du` không còn True, có cảnh báo.
4. Ngân sách chờ 429 của một lần xuất: hết thì dừng, lỗi rõ ràng, kèm link đã tạo.
"""
from __future__ import annotations

import contextvars
import json

import pytest

import apify_tool as A
import trinh_bay_sheet as T
from sheet_gia import LarkGia


@pytest.fixture
def gia(monkeypatch):
    g = LarkGia()
    monkeypatch.setattr(A.lark, "call", g.call)
    return g


# ───────────────────────── 1) cứu bảng tí hon không xoá cột ─────────────────────────
def test_cuu_bang_gap_duoi_tab_du_lieu_khong_xoa_cot_du_lieu(gia):
    goc = gia.call

    def call(method, path, query=None, body=None):
        if path.endswith("/sheets_batch_update") and any("addSheet" in r
                                                         for r in body["requests"]):
            raise RuntimeError("Lark POST sheets_batch_update failed: HTTP 500")
        return goc(method, path, query, body)
    A.lark.call = call
    lon = T.Bang("Bình luận", [T.Cot(f"C{i}") for i in range(8)],
                 [[f"v{i}" for i in range(8)]] * 9)
    nho = T.Bang("Bài đăng", [T.Cot("Link"), T.Cot("TT")], [["u1", "OK"]])
    kq = T.xuat("Soi", [lon, nho], T.TongQuan("Soi"))
    sid0 = gia.dau.tabs[0]["sheet_id"]
    xoa = [b["dimension"] for m, p, q, b in gia.goi if m == "DELETE"
           and b["dimension"]["sheetId"] == sid0 and b["dimension"]["majorDimension"] == "COLUMNS"
           and b["dimension"]["startIndex"] <= 8]
    assert xoa == [], f"không xoá cột dữ liệu: {xoa}"
    o = gia.o(gia.tab_ten()[0])
    assert o[1] == [f"v{i}" for i in range(8)], "8 cột dữ liệu còn nguyên"
    assert any(r[:2] == ["u1", "OK"] for r in o), "bảng tí hon ghi nối bên dưới"
    assert kq.day_du is False, "Tổng quan hỏng thì không nhận đủ"


# ───────────────────────── 2) ghi nối: đọc lại dòng cuối mới ─────────────────────────
@pytest.fixture
def F(monkeypatch, gia):
    fb = pytest.importorskip("fb_ads_tool")
    import lsr_policy
    import memory_store
    snap = ('Library ID: 111\n Started running on 1 Oct 2026\n button "HAPAS túi mới"\n'
            'Library ID: 222\n Started running on 3 Oct 2026\n button "Quà 20/10"\n')
    monkeypatch.setattr(fb, "_BROWSER_OK", True)
    monkeypatch.setattr(fb, "browser_navigate",
                        lambda **k: json.dumps({"success": True, "title": "Ad Library"}),
                        raising=False)
    monkeypatch.setattr(fb, "_full_snapshot", lambda: snap)
    monkeypatch.setattr(fb, "browser_scroll", lambda **k: "{}", raising=False)
    monkeypatch.setattr(fb, "browser_get_images", lambda **k: json.dumps({"images": []}),
                        raising=False)
    monkeypatch.setattr(fb.time, "sleep", lambda s: None)
    monkeypatch.setattr(A, "_grant", lambda tok, ou: True)
    monkeypatch.setattr(memory_store, "get_current_sender", lambda: "ou_nguoi_hoi")
    monkeypatch.setattr(lsr_policy, "quyen_phat", lambda: {"reply", "write_data"})
    monkeypatch.setattr(fb, "_SHEET_LUOT", {})
    return fb


def _hai_luot(F):
    import dong_ho_luot
    import scheduler

    def luot():
        scheduler.set_current_chat("lark:cli_x:oc_1")
        dong_ho_luot.bat_dau()
        a = json.loads(F._handle_fb_ads_library({"query": "HAPAS"}))
        b = json.loads(F._handle_fb_ads_library({"query": "PEDRO"}))
        return a, b
    return contextvars.copy_context().run(luot)


def test_ghi_noi_doc_lai_dong_cuoi_moi(F, gia):
    a, b = _hai_luot(F)
    sid = gia.tab("Dữ liệu")["sheet_id"]
    doc = [q["ranges"] for m, p, q, bd in gia.goi if "values_batch_get" in p]
    assert any(f"{sid}!A5:" in r for r in doc), f"đọc lại dòng 5 (dòng cuối mới): {doc}"
    assert b["day_du"] is True and "Đã ghi đủ 4/4" in b["kiem_ghi"]


def test_ghi_noi_mat_dong_thi_bao_thieu(F, gia):
    goc = gia.call
    dem = {"n": 0}

    def call(method, path, query=None, body=None):
        if path.endswith("/values_batch_update") and any(
                "PEDRO" in json.dumps(vr["values"], ensure_ascii=False)
                and vr["range"].split("!")[0] == gia.tab("Dữ liệu")["sheet_id"]
                for vr in body["valueRanges"]):
            dem["n"] += 1
            return {"data": {}}                  # Lark "nhận" mà không ghi dòng nối
        return goc(method, path, query, body)
    A.lark.call = call
    a, b = _hai_luot(F)
    assert dem["n"] >= 1 and b["day_du"] is False and "THIẾU" in b["kiem_ghi"]


# ───────────────────────── 3) ghi lại Tổng quan an toàn ─────────────────────────
def test_ghi_lai_tong_quan_hong_giu_ban_cu_va_bao(F, gia):
    import dong_ho_luot
    import scheduler
    goc = gia.call
    hong = {"bat": False}

    def call(method, path, query=None, body=None):
        tq = gia.bt and next((t for t in gia.dau.tabs if t["title"] == "Tổng quan"), None)
        if hong["bat"] and path.endswith("/values_batch_update") and tq and any(
                vr["range"].startswith(tq["sheet_id"] + "!") for vr in body["valueRanges"]):
            raise RuntimeError("Lark 500")             # ghi LẠI Tổng quan hỏng
        return goc(method, path, query, body)
    A.lark.call = call

    def luot():
        scheduler.set_current_chat("lark:cli_x:oc_1")
        dong_ho_luot.bat_dau()
        a = json.loads(F._handle_fb_ads_library({"query": "HAPAS"}))
        hong["bat"] = True
        return a, json.loads(F._handle_fb_ads_library({"query": "PEDRO"}))
    a, b = contextvars.copy_context().run(luot)
    tq = gia.o("Tổng quan")
    chu = " ".join(str(c) for r in tq for c in r)
    assert "HAPAS (VN" in chu, "bản Tổng quan cũ còn nguyên (không xoá trước khi ghi)"
    assert b["day_du"] is not True and "Tổng quan" in b["kiem_ghi"]
    assert "Ghi lại tab Tổng quan" in b["canh_bao_trinh_bay"]


def test_ghi_lai_tong_quan_ghi_moi_truoc_xoa_cu_sau(gia):
    kq = T.xuat("x", [T.Bang("Bài", [T.Cot("a")], [["1"]] * 8)],
                T.TongQuan("x", ghi_chu=[f"ghi chú {i}" for i in range(20)]))
    cu = len(gia.o("Tổng quan"))
    n_goi = len(gia.goi)
    ket = T.ghi_lai_tong_quan(kq.token, kq.tong_quan_sid, kq.url,
                              T.TongQuan("x", ghi_chu=["mới"]), kq.tabs, so_dong_cu=cu)
    moi = gia.goi[n_goi:]
    i_ghi = next(i for i, g in enumerate(moi) if g[1].endswith("/values_batch_update"))
    i_xoa = next(i for i, g in enumerate(moi) if g[0] == "DELETE"
                 and g[3]["dimension"]["majorDimension"] == "ROWS")
    assert i_ghi < i_xoa, "ghi bản mới TRƯỚC, xoá bản cũ SAU"
    assert moi[i_xoa][3]["dimension"]["startIndex"] == 1 and \
        moi[i_xoa][3]["dimension"]["endIndex"] == cu
    o = gia.o("Tổng quan")
    assert ket["ok"] and len(o) == ket["so_dong"] and o[0][0] == "x"
    assert "ghi chú 19" not in str(o) and "• mới" in str(o)


def test_sheet_lon_tong_quan_hong_thi_day_du_khong_true(gia, monkeypatch):
    import sheet_lon
    from test_viec_nen import _VGia
    monkeypatch.setattr(sheet_lon, "_ngu", lambda s: None)
    monkeypatch.setattr(A, "_grant", lambda *a: True)
    s = sheet_lon.SoSheet(_VGia())
    s.dam_bao("Quét nền", "Tổng quan", "")
    s.ghi_tab("TikTok", [["a"], ["1"]], cot=[T.Cot("a")])
    kiem = s.kiem_ghi(bo_qua={"Tổng quan"})
    assert kiem["day_du"] is True
    sid_tq = s.s["tabs"]["Tổng quan"]["sheet_id"]
    goc = gia.call

    def call(method, path, query=None, body=None):
        if path.endswith("/values_batch_update") and any(
                vr["range"].startswith(sid_tq + "!") for vr in body["valueRanges"]):
            raise RuntimeError("Lark 500")
        return goc(method, path, query, body)
    A.lark.call = call
    gop = s.ghi_tong_quan("Tổng quan", T.TongQuan("Quét nền"), kiem)
    assert gop["day_du"] is False and s.s["kiem"]["day_du"] is False
    assert "Tổng quan" in s.s["kiem"]["cau"] and s.s["kiem"]["canh_bao"]


# ───────────────────────── 4) ngân sách chờ 429 ─────────────────────────
def test_het_ngan_sach_cho_thi_dung_va_bao_kem_link(gia, monkeypatch):
    monkeypatch.setattr(T, "NGAN_SACH_CHO", 10.0)
    goc = gia.call

    def call(method, path, query=None, body=None):
        if path.endswith("/values_batch_update"):
            raise RuntimeError("Lark POST values_batch_update failed: HTTP 429: frequency")
        return goc(method, path, query, body)
    A.lark.call = call
    with pytest.raises(T.HetNganSachCho) as loi:
        T.xuat("x", [T.Bang("Bài", [T.Cot("a")], [["1"]] * 5)])
    assert "CHƯA đủ dữ liệu" in str(loi.value)
    assert getattr(loi.value, "trinh_bay_url", "").endswith("/sht1"), "kèm link đã tạo"
