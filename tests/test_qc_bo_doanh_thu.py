"""Doanh thu Shop / ROAS tạm gỡ (22/10/2026, chủ dự án: "đo khác cách công ty tự tính").

Soi: trang Quảng cáo + /api/qc (kể cả quản trị viên), Lark Sheet, tool Mark (`hoi_dashboard`,
`lay_so_tuc_thi`) không còn khoá / nhãn doanh thu hay ROAS; URL cũ `sap=roas` về sắp mặc định;
dữ liệu vẫn lưu (cột tiền `gia_tri_mua_shop` giữ luật `la_tien`); bật lại bằng một cờ.
"""
from __future__ import annotations

import re

from test_meta_ads_dashboard import ARGS, _app_hai_nen_tang
from test_meta_ads_dashboard import _hoi as _hoi_hd
from test_dashboard_app import XEM
from test_tiktok_ads import Q, QL, _co_so, _tao_app, dang_nhap
from test_tuc_thi import _bo_nghe, h  # noqa: F401  (fixture `h`)
from test_tuc_thi import _hoi as _hoi_tt

import hoi_dashboard_tool as HD
import tuc_thi_tool as TT
from dashboard import quang_cao as QC

#: Nhãn người đọc không được thấy (trang, Sheet).
_NHAN = re.compile(r"ROAS|Doanh thu", re.I)


def _khoa(x) -> set[str]:
    """Mọi khoá (đệ quy) của một JSON."""
    if isinstance(x, dict):
        return set(x) | {k for v in x.values() for k in _khoa(v)}
    if isinstance(x, list):
        return {k for v in x for k in _khoa(v)}
    return set()


def _khong_doanh_thu(x, noi: str):
    lo = sorted(k for k in _khoa(x) if QC.la_doanh_thu(k))
    assert not lo, (noi, lo)


def test_co_tat_va_luat_khoa():
    assert QC.HIEN_DOANH_THU is False
    for k in ("gia_tri_mua_shop", "roas_shop", "roas", "total_onsite_shopping_value",
              "onsite_shopping_roas", "complete_payment_roas", "total_purchase_value",
              "value_per_complete_payment", "action_values__omni_purchase",
              "purchase_roas__omni_purchase"):
        assert QC.la_doanh_thu(k), k
    for k in ("chi", "hien_thi", "cpm", "ctr", "mua_shop", "view_video", "tuong_tac", "gia_tri",
              "actions__omni_purchase", "chi_moi_follow", "spend"):
        assert not QC.la_doanh_thu(k), k
    # Dữ liệu vẫn lưu: cột tiền giữ nguyên, luật tiền không đổi.
    assert "gia_tri_mua_shop" in QC.TEN_COT_SO and "gia_tri_mua_shop" in QC.COT_TIEN
    assert QC.la_tien("gia_tri_mua_shop") and QC.la_tien("roas_shop")
    x = {"chi": 1, "gia_tri_mua_shop": 2, "ds": [{"roas_shop": 1, "hien_thi": 3}]}
    assert QC.loc_doanh_thu(x) == {"chi": 1, "ds": [{"hien_thi": 3}]}
    assert x["gia_tri_mua_shop"] == 2                       # không sửa bản gốc


def test_kpi_va_sap_khong_con_roas():
    for co_tien in (True, False):
        chinh, phu = QC.chon_kpi(co_tien)
        assert not {"gia_tri_mua_shop", "roas_shop"} & set(chinh + phu)
    assert "roas" not in QC.SAP_BANG
    # URL cũ `sap=roas`: về sắp mặc định, không lỗi.
    assert QC.loc_bang({"sap": "roas"}, True)["sap"] == "chi"
    assert QC.loc_bang({"sap": "roas"}, False)["sap"] == "hien_thi"


def test_bat_lai_bang_mot_co(monkeypatch):
    monkeypatch.setattr(QC, "HIEN_DOANH_THU", True)
    x = {"gia_tri_mua_shop": 2, "roas_shop": 1}
    assert QC.loc_doanh_thu(x) is x
    assert "roas_shop" in QC.chon_kpi(True)[1]


def test_api_va_trang_khong_doanh_thu_roas():
    _app, c, _kho, _kho_qc, _tt, _dv = _co_so(_tao_app())
    dang_nhap(c, QL)                                         # quản trị viên: có xem tiền
    for ben in ("", "&ben=hapas", "&ben=chua_gan"):
        d = c.get(f"/api/qc?{Q}{ben}").json()
        assert d["xem_tien"] is True and "chi" in d["kpi"]
        _khong_doanh_thu(d, ben)
    r = c.get(f"/api/qc?{Q}&sap=roas")
    assert r.status_code == 200 and r.json()["sap"] == "chi"
    for url in (f"/quang-cao?{Q}", f"/quang-cao?{Q}&sap=roas",
                f"/quang-cao?{Q}&sap=roas&chieu=tang"):
        r = c.get(url)
        assert r.status_code == 200, url
        assert not _NHAN.search(r.text), (url, _NHAN.search(r.text))
        assert "sap=roas" not in r.text and 'value="roas"' not in r.text
        assert "roas_shop" not in r.text and "gia_tri_mua_shop" not in r.text


def test_sheet_khong_cot_doanh_thu_roas(monkeypatch):
    from test_sheet_qc import _chay

    import xuat_sheet_qc as X
    kq, _k, lk = _chay(monkeypatch)
    assert kq["trang_thai"] == "xong"
    assert not any(QC.la_doanh_thu(m) for m, _t, _k2 in X._COT_SO)
    gia = lk.gia
    for tab in gia.tab_ten():
        for dong in gia.o(tab):
            for o in dong:
                assert not _NHAN.search(str(o)), (tab, o)


def test_mark_hoi_dashboard_khong_doanh_thu_roas(monkeypatch):
    a = _app_hai_nen_tang()
    for ai in (QL, XEM):                       # quản trị viên + Chỉ xem (đều xem tiền bên mình)
        qc = _hoi_hd(monkeypatch, ai, ARGS, a.kho, a.kho_qc)["phan"]["quang_cao"]
        assert qc["co"] is True
        _khong_doanh_thu(qc, ai)
        assert QC.CAU_KHONG_DOANH_THU in qc["ghi_chu"]
        b = qc["ben"][0]
        assert b["xem_tien"] is True and b["kpi"]["chi"] > 0
        assert b["theo_tai_khoan"] and b["theo_nen_tang"] and b["chi_phi"]["cpm"] is not None
    # Tra một đối tượng: cả chỉ số thô (action_values__…, purchase_roas__…) cũng bỏ.
    r = _hoi_hd(monkeypatch, XEM, {"tim": "nuoc hoa thang 10", "cap": "chien_dich",
                                   "theo_ngay": True, **ARGS}, a.kho, a.kho_qc)["phan"]["quang_cao"]
    assert r["tim_thay"] == 1
    _khong_doanh_thu(r, "tra_cuu")
    assert "actions__purchase" in r["doi_tuong"][0]["chi_so_tho_cong_duoc"]
    assert "ROAS" not in r["ghi_chu"].replace(QC.CAU_KHONG_DOANH_THU, "")
    # Mô tả tool: nói rõ là không báo + gợi ý báo cáo công ty; không còn hứa doanh thu / ROAS.
    assert QC.CAU_KHONG_DOANH_THU in HD.SCHEMA["description"]
    assert "ROAS" not in HD.PHAN["quang_cao"].replace("doanh thu Shop / ROAS tạm không báo", "")
    assert QC.CAU_KHONG_DOANH_THU in TT.QUY_TAC
    assert QC.CAU_KHONG_DOANH_THU in TT.SCHEMA["description"]


def test_mark_lay_so_tuc_thi_khong_doanh_thu_roas(monkeypatch, h):
    r = _hoi_tt(monkeypatch, h, XEM, {"loai": "quang_cao", "so_ngay": 3}, _bo_nghe(h))
    assert r["quang_cao"]["co"] is True and r["quang_cao"]["ben"][0]["kpi"]["chi"] is not None
    _khong_doanh_thu(r, "tuc_thi")
    assert QC.CAU_KHONG_DOANH_THU in r["ghi_chu"]
