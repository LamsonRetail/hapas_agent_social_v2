"""social_deep_dive → lớp trình bày chung (trinh_bay_sheet) với Lark GIẢ (tests/sheet_gia).

Soi: thứ tự tab ("Tổng quan", "1. Bình luận", "2. Thống kê", "3. Bài đăng", "Dữ liệu gốc"),
mục lục đúng số dòng, bảng tí hon (Bài đăng ≤5 dòng) gấp vào Tổng quan, Tổng quan chép
đúng số `thong_ke` + câu `dong_thong_ke`, kiểu cột (Likes số nguyên, thời gian ngày giờ thật,
người bình luận dạng chữ, tỉ lệ ĐÃ nhân 100), tiêu đề navy + cố định dòng 1 + bộ lọc, cấp
quyền SAU CÙNG, trang trí hỏng vẫn đủ dữ liệu + link, `day_du`/`kiem_ghi`, bản ghi gốc chỉ
nằm trong sheet. Việc nền (sheet_lon): Tổng quan + mục lục + kiểm ghi.
"""
from __future__ import annotations

import json
import re

import deep_dive_tool as D
import phan_loai as P
import trinh_bay_sheet as T
from sheet_gia import LarkGia
from test_binh_luan_phan_tich import TT, _bl, moi_truong  # noqa: F401
from test_viec_nen import nen  # noqa: F401
from sheet_gia import meta  # noqa: E402


def _lark(mt) -> LarkGia:
    return mt[2].gia_lark


def _du_lieu(n_bai: int = 1):
    """Bình luận giả cho `n_bai` video TikTok: mỗi bài 2 bình luận khách."""
    def tra(payload, limit):
        ra = []
        for u in payload["postURLs"]:
            ra += [dict(_bl(u, "túi đẹp quá", 9), cid=f"a{u[-3:]}", uniqueId="12345",
                        createTimeISO="2026-10-01T03:00:00Z", avatarThumbnail="https://a/x.jpg"),
                   dict(_bl(u, "giao chậm", 2), cid=f"b{u[-3:]}", uniqueId="khach_b")]
        return ra
    return tra


def _chay(mt, n_bai=1, **kw):
    mt[0].tra = _du_lieu(n_bai)
    urls = [TT.format(7000001 + i) for i in range(n_bai)]
    raw = D._handle({"post_urls": urls, **kw})
    return json.loads(raw), raw


def _tq(gia, nhan):
    return next(r for r in gia.o("Tổng quan") if r and r[0] == nhan)


def _fmt(gia, tab, cot, dong=2):
    return [s["formatter"] for s in gia.kieu_o(tab, cot, dong) if "formatter" in s]


# ───────────────────────── tab, mục lục, gấp bảng ─────────────────────────
def test_ba_bang_tro_len_thi_tab_danh_so_va_muc_luc_dung_so_dong(moi_truong):  # noqa: F811
    kq, _ = _chay(moi_truong, n_bai=6)
    gia = _lark(moi_truong)
    assert kq["success"] is True and kq["tong_comment"] == 12
    assert gia.tab_ten() == ["Tổng quan", "1. Bình luận", "2. Thống kê", "3. Bài đăng",
                             T.TAB_GOC]
    tq = gia.o("Tổng quan")
    muc = {(r[0]["text"] if isinstance(r[0], dict) else r[0]): r[1] for r in tq
           if r and r[0] and len(r) > 1 and isinstance(r[1], int)
           and (isinstance(r[0], dict) or str(r[0]).startswith(("1.", "2.", "3.", "Dữ")))}
    assert muc["1. Bình luận"] == 12 and muc["3. Bài đăng"] == 6 and muc[T.TAB_GOC] == 12
    assert muc["2. Thống kê"] == len(D._dong_thong_ke(kq["thong_ke"])) - 1
    assert len(gia.o("1. Bình luận")) == 13 and len(gia.o("3. Bài đăng")) == 7
    assert kq["thong_ke_ghi_o"] == "tab '2. Thống kê'"
    assert "bình luận ở tab '1. Bình luận'" in kq["note"]


def test_bai_dang_it_thi_gap_vao_tong_quan(moi_truong):  # noqa: F811
    kq, _ = _chay(moi_truong, n_bai=2)
    gia = _lark(moi_truong)
    assert gia.tab_ten() == ["Tổng quan", "1. Bình luận", "2. Thống kê", T.TAB_GOC]
    tq = gia.o("Tổng quan")
    i = next(k for k, r in enumerate(tq) if r and r[0] == "BÀI ĐĂNG")
    assert tq[i + 1][:4] == ["Link bài", "Nền tảng", "Trạng thái", "Số bình luận"]
    assert {tq[i + 2][0], tq[i + 3][0]} == {TT.format(7000001), TT.format(7000002)}
    assert tq[i + 2][2] == "OK" and tq[i + 2][3] == 2


def test_ten_tab_sach_va_noi_ghi_theo_ten_that(moi_truong):  # noqa: F811
    """Tên bảng có ký tự cấm (/ : [ ] ? *) → tab hợp lệ ≤30 ký tự; `noi_ghi` tìm cả tab
    đánh số và tab tách phần."""
    gia = _lark(moi_truong)
    tk = P.dem([{"platform": "tiktok", "bai": "u", "sac_thai": "Tích cực", "chu_de": "Khác",
                 "likes": 1}])
    bl = T.Bang("Bình luận", D.cot_binh_luan(D._HEADER), [["tiktok", "a", "x"] + [""] * 9],
                gap_duoc=False)
    kq = T.xuat("Soi", [bl, D.bang_thong_ke(tk, "Thống kê: bài/kênh [x]*?")])
    ten = gia.tab_ten()
    assert ten[:2] == ["Tổng quan", "1. Bình luận"]
    assert ten[2] == "2. Thống kê bài kênh x" and len(ten[2]) <= 30
    assert not any(re.search(r"[/\\?*\[\]:]", t) for t in ten)
    assert D.noi_ghi(kq, "Bình luận") == "tab '1. Bình luận'"
    gia_tach = type("K", (), {"tabs": [T.TabDaGhi("2. Bình luận (1/2)", "s", [], 1, 1)]})()
    assert D.noi_ghi(gia_tach, "Bình luận") == "tab '2. Bình luận (1/2)'"
    assert D.noi_ghi(gia_tach, "Thống kê").startswith("tab 'Tổng quan'")


# ───────────────────────── Tổng quan = số của tool ─────────────────────────
def test_tong_quan_chep_dung_thong_ke_va_cau_dong_thong_ke(moi_truong):  # noqa: F811
    kq, _ = _chay(moi_truong, n_bai=1, title="Soi bình luận HAPAS")
    gia = _lark(moi_truong)
    tq = gia.o("Tổng quan")
    tk = kq["thong_ke"]
    assert tq[0][0] == "Soi bình luận HAPAS"
    assert "Nguồn: social_deep_dive" in meta(tq) and "Phạm vi: 1 bài" in meta(tq)
    assert _tq(gia, "Bình luận đã ghi sheet")[1] == kq["tong_comment"] == 2
    assert _tq(gia, "Đã phân loại")[1] == tk["da_phan_loai"]
    for lab in ("Tích cực", "Tiêu cực", "Trung lập"):
        r = _tq(gia, lab)
        assert r[1] == tk["sac_thai"][lab]["so"]
        assert P._pt(tk["sac_thai"][lab]["ti_le"]) in r[3], "tỉ lệ đúng dạng dong_thong_ke"
    ghi = [r[0] for r in tq if r and str(r[0]).startswith("• ")]
    assert f"• {kq['dong_thong_ke']}" in ghi
    assert any("tối đa 50 bình luận" in g for g in ghi), "nói rõ trần max_comments"
    assert any(str(r[0]).startswith("Đã ghi đủ") for r in tq), "dòng KIỂM GHI"
    assert kq["day_du"] is True and kq["kiem_ghi"].startswith("Đã ghi đủ")
    assert kq["kiem_ghi"] in kq["note"] and kq["bang_tinh_tiep"] is None


# ───────────────────────── kiểu cột, trang trí ─────────────────────────
def test_dinh_dang_cot_tieu_de_co_dinh_va_loc(moi_truong):  # noqa: F811
    kq, _ = _chay(moi_truong, n_bai=1)
    gia = _lark(moi_truong)
    bl, tk = "1. Bình luận", "2. Thống kê"
    o = gia.o(bl)
    assert o[0] == D._HEADER
    dong = next(r for r in o[1:] if r[2] == "túi đẹp quá")
    assert dong[1] == "12345" and isinstance(dong[1], str), "người bình luận số-trơn vẫn là chữ"
    assert "@" in _fmt(gia, bl, 2)
    assert dong[5] == 9 and "#,##0" in _fmt(gia, bl, 6)
    ngay = round((__import__("datetime").datetime(2026, 10, 1, 10, 0)
                  - __import__("datetime").datetime(1899, 12, 30)).total_seconds() / 86400, 6)
    assert dong[7] == ngay and "yyyy/MM/dd HH:mm:ss" in _fmt(gia, bl, 8), "giờ VN, ngày thật"
    # Thống kê: tỉ lệ của phan_loai ĐÃ nhân 100 → 75.0 hiển thị 75.00%, không nhân nữa.
    t = gia.o(tk)
    tong = next(r for r in t if r[0] == "Tổng" and r[1] == "Tích cực")
    assert tong[2:] == [1, 50.0, 81.8]
    assert "#,##0.00" in _fmt(gia, tk, 4) and "#,##0.00" in _fmt(gia, tk, 5)
    for ten in (bl, tk):
        tab = gia.tab(ten)
        assert tab["frozen"] == 1
        st = gia.kieu_o(ten, 1, 1)
        assert any(s.get("backColor") == T.NAVY and s.get("font", {}).get("bold") for s in st)
    sid = gia.tab(bl)["sheet_id"]
    vung = [b["range"] for p, b in gia.loc() if f"/{sid}/" in p]
    assert vung == [f"{sid}!A1:L3"], "bộ lọc phủ tiêu đề + đủ dòng dữ liệu"
    assert gia.kieu_o(bl, 1, 4) == [], "không có dòng tổng (tool không tính tổng)"


def test_trang_tri_hong_van_du_du_lieu_va_link(moi_truong, monkeypatch):  # noqa: F811
    _lark(moi_truong).hong = {"styles_batch_update", "/filter", "merge_cells"}
    kq, _ = _chay(moi_truong, n_bai=1)
    gia = _lark(moi_truong)
    assert kq["success"] is True and kq["sheet_url"].startswith("https://x.larksuite.com/")
    assert len(gia.o("1. Bình luận")) == 3 and kq["day_du"] is True


def test_doc_lai_khong_duoc_thi_chua_kiem_khong_tu_nhan_du(moi_truong):  # noqa: F811
    _lark(moi_truong).doc_lai = False
    kq, _ = _chay(moi_truong, n_bai=1)
    assert kq["success"] is True and kq["day_du"] is None
    assert "chưa đọc lại" in kq["kiem_ghi"] and "Đã ghi ĐỦ" not in kq["note"]


def test_ghi_thieu_thi_canh_bao_trong_note(moi_truong, monkeypatch):  # noqa: F811
    goc = T.kiem_ghi
    def thieu(tok, tabs):
        k = goc(tok, tabs)
        for t in k["tabs"]:
            if t["tab"] == "1. Bình luận":
                t.update(ket="thieu", cau="THIẾU")
        return dict(k, day_du=False, cau="CẢNH BÁO GHI THIẾU: 1. Bình luận: THIẾU")
    monkeypatch.setattr(T, "kiem_ghi", thieu)
    kq, _ = _chay(moi_truong, n_bai=1)
    assert kq["day_du"] is False and "CẢNH BÁO GHI THIẾU" in kq["note"]


# ───────────────────────── quyền, dữ liệu gốc ─────────────────────────
def test_cap_quyen_sau_cung_va_khong_nguoi_hoi_thi_khong_cap(moi_truong, monkeypatch):  # noqa: F811
    gia = _lark(moi_truong)
    luc = []
    monkeypatch.setattr(D, "_grant", lambda tok, oid: luc.append((tok, oid, len(gia.goi))) or True)
    kq, _ = _chay(moi_truong, n_bai=1)
    assert kq["granted"] is True and luc[0][:2] == ("sht1", "ou_test")
    ghi = [i for i, g in enumerate(gia.goi) if g[1].endswith("values_batch_update")]
    assert luc[0][2] > max(ghi), "cấp quyền SAU khi ghi xong mọi tab (kể cả Tổng quan)"
    monkeypatch.setattr(D.memory_store, "get_current_sender", lambda: None)
    luc.clear()
    kq, _ = _chay(moi_truong, n_bai=1)
    assert kq["granted"] is False and luc == []


def test_du_lieu_goc_moi_truong_chi_trong_sheet(moi_truong):  # noqa: F811
    kq, raw = _chay(moi_truong, n_bai=1)
    gia = _lark(moi_truong)
    goc = gia.o(T.TAB_GOC)
    assert "avatarThumbnail" in goc[0] and "cid" in goc[0] and len(goc) == 3
    i = goc[0].index("cid")
    assert [r[i] for r in goc[1:]] == ["a001", "b001"], "cùng thứ tự dòng bảng Bình luận"
    assert "avatarThumbnail" not in raw and "__goc" not in raw
    assert "1.000 ký tự" in "".join(str(r[0]) for r in gia.o("Tổng quan"))


# ───────────────────────── việc nền (sheet_lon) ─────────────────────────
def test_viec_nen_co_tong_quan_muc_luc_kiem_ghi(nen, monkeypatch):  # noqa: F811
    """Việc nền ghi bằng sheet_lon: tab Tổng quan (mục lục + kiểm ghi + số thong_ke), tab
    Bình luận/Thống kê/Bài đăng có kiểu cột; `ket_qua` của việc giữ `kiem_ghi`."""
    import lark_client
    import viec_nen as V
    gia, lk = LarkGia(), nen.lark

    def call(method, path, query=None, body=None):
        la_sheet = "/sheets/" in path or path.endswith("/spreadsheets")
        return (gia.call if la_sheet else lk.call)(method, path, query=query, body=body)
    monkeypatch.setattr(lark_client, "call", call)
    monkeypatch.setattr(D, "_cau_hinh", lambda nen=None: (30000, 50.0 if nen else 5.0))
    monkeypatch.setattr(P, "phan_loai_binh_luan",
                        lambda rows, han, tt=None: [("Tích cực", "Khác")] * len(rows))
    urls = [f"https://www.tiktok.com/@a/video/{1000000 + i}" for i in range(40)]
    kq = json.loads(D._handle({"post_urls": urls, "max_comments": 100}))
    assert kq["dang_chay_nen"]
    nen.so_item = lambda actor, p: 3
    d = V.chay_ngay(kq["ma_viec"])
    kqv = d["ket_qua"]
    ten = gia.tab_ten()
    # sheet_lon.ghi_tong_quan xếp tab: Tổng quan đầu, các tab dữ liệu theo thứ tự thêm.
    assert ten[0] == "Tổng quan" and {"Bình luận", "Thống kê", "Bài đăng"} <= set(ten), ten
    assert kqv["day_du"] is True and kqv["kiem_ghi"].startswith("Đã ghi đủ")
    assert "Kiểm ghi: Đã ghi đủ" in d["thong_bao"]["ket_qua"]
    tq = gia.o("Tổng quan")
    so = {r[0]: r[1] for r in tq if r and isinstance(r[0], str) and len(r) > 1}
    assert so["Bình luận đã ghi sheet"] == kqv["tong_comment"] > 0
    muc = {(r[0]["text"] if isinstance(r[0], dict) else r[0]): r[1] for r in tq
           if r and isinstance(r[0], dict)}
    assert muc["Bình luận"] == kqv["tong_comment"] and muc["Bài đăng"] == 40
    assert any("không có tab 'Dữ liệu gốc'" in str(r[0]) for r in tq), "nói rõ thiếu bản gốc"
    assert gia.tab("Bình luận")["frozen"] == 1
    assert any(s.get("backColor") == T.NAVY for s in gia.kieu_o("Bình luận", 1, 1))
    # Chế độ LỚN đặt định dạng an toàn sau khi ghi: tỉ lệ ĐÃ ×100 → số 2 lẻ, không bao giờ
    # "0.00%" (sẽ nhân 100 lần nữa).
    fmt = _fmt(gia, "Thống kê", 4)
    assert fmt and set(fmt) <= {"#,##0.00", "#,##0.00"} and "0.00%" not in fmt
