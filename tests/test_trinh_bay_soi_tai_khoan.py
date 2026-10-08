"""Sheet của `soi_tai_khoan` dựng bằng lớp trình bày chung (trinh_bay_sheet, 08/10/2026).

Nhiều bảng: "Hồ sơ" (một dòng mỗi tài khoản, chỉ số `_tong_hop` đã tính), "Bài đăng"
(bài trong khoảng), "Bài nổi bật" (top tool đã chọn — ít dòng thì gấp vào Tổng quan), rồi
"Dữ liệu gốc". Lark giả: tests/sheet_gia.py.
"""
from __future__ import annotations

import json

import account_tool as T
import apify_tool as A
import test_soi_tai_khoan_va_san as TS
from test_soi_tai_khoan_va_san import gia  # noqa: F401 — fixture dùng chung
from sheet_gia import meta  # noqa: E402


def _chay(**args) -> tuple[dict, str]:
    raw = T._handle(args)
    return json.loads(raw), raw


def _fmt(lark, tab, cot, dong=2):
    return [s["formatter"] for s in lark.kieu_o(tab, cot, dong) if "formatter" in s]


def test_tab_nhieu_bang_va_bang_nho_gap_vao_tong_quan(gia):
    _, lark = gia
    kq, _ = _chay(tai_khoan=["@thybui.__"])
    assert lark.tab_ten() == ["Tổng quan", "1. Hồ sơ", "2. Bài đăng", "Dữ liệu gốc"]
    tq = [r[0] for r in lark.o("Tổng quan")]
    assert "BÀI NỔI BẬT" in tq, "2 dòng × 6 cột: gấp vào Tổng quan"
    assert "BÀI TRONG KHOẢNG THEO TÀI KHOẢN" in tq and "MỤC LỤC" in tq
    chu = " ".join(map(str, tq))
    assert "2/3 bài đã đọc; 1 bài ngoài khoảng" in chu
    assert "soi_tai_khoan" in meta(lark.o("Tổng quan")) and kq["day_du"] is True


def test_ho_so_la_so_tool_da_tinh_va_ti_le_la_phan_so(gia):
    _, lark = gia
    kq, _ = _chay(tai_khoan=["@thybui.__"])
    tk = kq["tai_khoan"][0]
    o = lark.o("1. Hồ sơ")
    cot = {ten: i for i, ten in enumerate(o[0])}
    r = o[1]
    assert r[cot["Followers"]] == tk["ho_so"]["followers"] == 1000
    assert r[cot["View trung vị"]] == tk["view_trung_vi"] == 400
    assert r[cot["Bài/tuần"]] == tk["bai_moi_tuan"]
    assert r[cot["Tương tác / view"]] == tk["ti_le_tuong_tac_tren_view"] == 0.0875
    assert r[cot["View trung vị / follower"]] == 0.4
    # Phân số → định dạng 0.00% (0,0875 hiện 8,75%), không nhân 100 lần nữa.
    assert "0.00%" in _fmt(lark, "1. Hồ sơ", cot["Tương tác / view"] + 1)
    assert "@" in _fmt(lark, "1. Hồ sơ", cot["Tài khoản"] + 1)
    assert r[cot["Nền tảng"]] == "TikTok"


def test_bai_dang_ngay_that_va_tieu_de_co_dinh(gia):
    _, lark = gia
    _chay(tai_khoan=["@thybui.__"])
    o = lark.o("2. Bài đăng")
    assert o[0][:3] == ["Nền tảng", "Tài khoản", "Ngày đăng"] and len(o) == 3
    assert isinstance(o[1][2], float)
    assert "yyyy/MM/dd HH:mm:ss" in _fmt(lark, "2. Bài đăng", 3)
    assert "#,##0" in _fmt(lark, "2. Bài đăng", 5)
    assert lark.tab("2. Bài đăng")["frozen"] == 1
    sid = lark.tab("2. Bài đăng")["sheet_id"]
    assert [b["range"] for p, b in lark.loc() if f"/{sid}/" in p] == [f"{sid}!A1:L3"]


def test_ten_tai_khoan_toan_so_ghi_dang_chu(gia, monkeypatch):
    _, lark = gia
    bai = [dict(TS.TIKTOK[0], authorMeta={"name": "1234567", "fans": 10})]
    monkeypatch.setattr(A, "_call", lambda *a, **k: bai)
    _chay(tai_khoan=["@1234567"])
    assert lark.o("2. Bài đăng")[1][1] == "1234567"


def test_du_lieu_goc_gom_bai_va_ho_so_instagram_khong_lot_ra_ngoai(gia):
    _, lark = gia
    _, raw = _chay(tai_khoan=["@thybui.__", "https://www.instagram.com/edoris.vn/"])
    g = lark.o("Dữ liệu gốc")
    assert g[0][0] == "Loại bản ghi"
    loai = [r[0] for r in g[1:]]
    assert loai[:5] == [f"bài (dòng {i} tab Bài đăng)" for i in range(1, 6)]
    assert loai[-1] == "hồ sơ Instagram" and "followersCount" in g[0]
    assert "latestPosts" not in g[0], "bài IG đã có từng dòng riêng"
    assert '"_goc"' not in raw and "_goc_ho_so" not in raw


def test_khong_bai_trong_khoang_thi_khong_tao_sheet(gia, monkeypatch):
    _, lark = gia
    monkeypatch.setattr(A, "_call", lambda *a, **k: [TS.TIKTOK[2]])
    kq, _ = _chay(tai_khoan=["@thybui.__"])
    assert kq["sheet_url"] is None and not lark.bt and kq["day_du"] is None


def test_trang_tri_hong_van_co_link_va_du_lieu(gia):
    _, lark = gia
    lark.hong = {"styles_batch_update"}
    kq, _ = _chay(tai_khoan=["@thybui.__"])
    assert kq["sheet_url"] and kq["loi"] is None and kq["day_du"] is True
    assert len(lark.o("2. Bài đăng")) == 3


def test_cap_quyen_sua_cho_nguoi_hoi_sau_cung(gia, monkeypatch):
    _, lark = gia
    monkeypatch.setattr(T.memory_store, "get_current_sender", lambda: "ou_x")
    kq, _ = _chay(tai_khoan=["@thybui.__"])
    quyen = [i for i, g in enumerate(lark.goi) if "/permissions/" in g[1]]
    ghi = [i for i, g in enumerate(lark.goi) if g[1].endswith("/values_batch_update")]
    assert kq["granted"] is True and quyen and quyen[0] > max(ghi)
    assert lark.goi[quyen[0]][3]["perm"] == "edit"


def test_ghi_hong_thi_loi_sheet_nhu_cu(gia):
    _, lark = gia
    lark.hong = {"values_batch_update"}
    kq, _ = _chay(tai_khoan=["@thybui.__"])
    assert kq["sheet_url"] is None and "sheet" in kq["loi"] and kq["success"] is False
