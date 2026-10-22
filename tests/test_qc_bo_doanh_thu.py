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
from test_meta_ads import context  # noqa: F401  (fixture `context`, không autouse ở đây)

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


# ───────────── Sheet số ads Meta của Mark (`chi_so_ads`, meta_ads_tool) ─────────────
def test_chi_so_ads_danh_muc_va_schema_khong_doanh_thu_roas(monkeypatch):
    import json

    import meta_ads_tool as MT
    assert MT.HIEN_DOANH_THU is QC.HIEN_DOANH_THU is False
    d = json.loads(MT._handle({"danh_muc": True}))
    ma = {m["ma"] for g in d["nhom"].values() for m in g}
    assert ma and not ma & set(MT.DOANH_THU) and "purchases" in ma
    assert not any(_NHAN.search(m["ten"] + m["y_nghia"]) or "Giá trị mua" in m["ten"]
                   for g in d["nhom"].values() for m in g)
    assert d["ghi_chu"] == QC.CAU_KHONG_DOANH_THU
    enum = MT.SCHEMA["parameters"]["properties"]["chi_so"]["items"]["enum"]
    assert not set(enum) & set(MT.DOANH_THU)
    assert QC.CAU_KHONG_DOANH_THU in MT.SCHEMA["description"]
    # Hỏi đích danh → lỗi nói rõ lý do; nhóm chuyen_doi bỏ các chỉ số đó.
    for k in MT.DOANH_THU:
        try:
            MT._metrics([k])
        except ValueError as e:
            assert QC.CAU_KHONG_DOANH_THU in str(e)
        else:
            raise AssertionError(k)
    assert MT._metrics(["chuyen_doi"]) == ["purchases", "cost_per_purchase"]
    assert not {"action_values", "purchase_roas"} & MT._truong(MT._metrics(["chuyen_doi"]),
                                                               "account")


def test_chi_so_ads_sheet_khong_cot_doanh_thu_roas(monkeypatch, context):
    import json

    import meta_ads_tool as MT
    from test_meta_ads import _kq
    monkeypatch.setenv("MARK_META_ADS_TOKEN", "fake")
    monkeypatch.setattr(MT, "_allowed", lambda actor: actor == "ou_asker")
    calls, sheets = [], []

    class Client:
        def __init__(self, *a):
            pass

        def accounts(self):
            return [{"id": "act_1", "name": "HAPAS", "currency": "VND"}]

        def pages(self, tail, params, limit):
            calls.append(params)
            return [{"spend": "100", "impressions": "10",
                     "actions": [{"action_type": "purchase", "value": "2"}],
                     "action_values": [{"action_type": "purchase", "value": "500"}],
                     "purchase_roas": [{"action_type": "purchase", "value": "5"}]}], False

    monkeypatch.setattr(MT, "MetaClient", Client)
    monkeypatch.setattr(MT, "_private_sheet", lambda title, bang, tq, actor, goc=None, gop=():
                        sheets.append((bang, tq, gop)) or _kq())
    r = json.loads(MT._handle({"tai_khoan": "tat_ca", "khoang_ngay": "7_ngay",
                               "chi_so": ["co_ban", "chuyen_doi"], "chia_theo": ["nen_tang"]}))
    assert "error" not in r, r
    assert not {"action_values", "purchase_roas"} & set(calls[0]["fields"].split(","))
    bang, tq, gop = sheets[0]
    chu = " ".join([c.ten for b in (bang, *gop) for c in b.cot] + list(tq.ghi_chu)
                   + [s.nhan for s in tq.so_lieu] + [str(r.get("cau_tong", ""))])
    assert not _NHAN.search(chu) and "Giá trị mua" not in chu and "giá trị mua" not in chu, chu
    assert "Mua hàng" in chu
    r = json.loads(MT._handle({"tai_khoan": "tat_ca", "khoang_ngay": "7_ngay", "chi_so": ["roas"]}))
    assert "error" in r and QC.CAU_KHONG_DOANH_THU in r["error"]
