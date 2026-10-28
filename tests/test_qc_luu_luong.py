"""Lưu lượng truy cập + sở thích TikTok (28/10/2026, chủ dự án chốt).

"về khách hàng mục tiêu: interest_category. Về lưu lượng truy cập: clicks, ctr, cpc,
total_landing_page_view (shop view, product view)" — trang /quang-cao:
  • Click / CTR / CPC = BẤM LIÊN KẾT ở mọi chỗ (TikTok clicks; Meta inline_link_clicks) — cột click
    của kho không đổi;
  • mục "Lưu lượng truy cập" (7 ô, ô tiền chỉ người xem tiền, ô một nền tảng chỉ khi có nền tảng đó);
  • bảng chiến dịch / quảng cáo thêm CPC + Landing page view (xếp được); biểu đồ thêm Click + LPV;
  • khối Khán giả thêm "Sở thích (TikTok)" (cả cấp tài khoản và chiến dịch), % trên tổng hiển thị
    TikTok cùng phạm vi; tên từ tool_interest_category_get (công cụ chỉ đọc thứ hai của tool_execute);
  • tới hạn: cửa sổ đọc bằng bộ chiều cũ tới hạn lại MỘT lần (tk_quang_cao.*_bo_chieu);
  • delta Postgres 2026-10-28-qc-luu-luong.sql = schema.sql; BigQuery qc_so_thich + mô tả 11 nhãn.

Không mạng: máy chủ TikTok / Meta giả + kho giả của test_tiktok_ads / test_meta_ads_dashboard."""
from __future__ import annotations

import copy
import datetime
import json
import math
import re
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_dashboard_app import QL, dang_nhap
from test_meta_ads_dashboard import _app_hai_nen_tang
from test_tiktok_ads import (
    BAY,
    HAPAS_KOC,
    LE,
    MM_2,
    MM_MKT,
    GiaKhoQC,
    GiaTikTok,
    Q,
    _co_so,
    _dv,
    _GhiSQL,
    _ket_noi_san,
    _khoa_lap,
    _tao_app,
)

from dashboard import app as A
from dashboard import dong_bo_bq as DBQ
from dashboard import kenh_dang as KD
from dashboard import kho_qc as KQ
from dashboard import kho_sheet_qc as KS
from dashboard import quang_cao as QC
from dashboard import tiktok_ads as TA

GOC = Path(__file__).resolve().parents[1]
CHAY = (HAPAS_KOC, MM_MKT, MM_2)
#: Ba nhóm sở thích giả: (mã v1, mã v2) — như đo thật, mỗi dòng có cả hai.
ST = [("116", "25"), ("101", "10"), ("130", "25")]
TEN = {1: [{"interest_category_id": "116", "interest_category_name": "Làm đẹp", "level": 1,
            "sub_category_ids": ["11601"]},
           {"interest_category_id": "101", "interest_category_name": "Giáo dục", "level": 1,
            "sub_category_ids": []},
           {"interest_category_id": "11601", "interest_category_name": "Trang điểm", "level": 2},
           {"interest_category_id": "x9", "interest_category_name": "Mã lạ"},
           {"interest_category_id": "200", "interest_category_name": ""}],
       2: [{"interest_category_id": "25", "interest_category_name": "Làm đẹp & chăm sóc", "level": 1,
            "sub_category_ids": ["2501"]}]}


def _tt_so_thich(**kw) -> GiaTikTok:
    tt = GiaTikTok(**kw)
    tt.so_thich = list(ST)
    tt.ten_so_thich = copy.deepcopy(TEN)
    return tt


def _audience(tt, cap=None, chieu=None):
    return [a for t, a in tt.cong_cu if t == "report_integrated_get"
            and a["report_type"] == "AUDIENCE" and (cap is None or a["data_level"] == cap)
            and (chieu is None or a["dimensions"][-1] == chieu)]


def _ten_goi(tt):
    return [a for t, a in tt.cong_cu if t == "tool_execute"
            and a.get("tool_name") == TA.TOOL_SO_THICH]


# ───────────────────────────── 1. chốt chỉ đọc tool_execute ─────────────────────────────
def _st(**p):
    return {"tool_name": TA.TOOL_SO_THICH,
            "params": {"advertiser_id": "7418067186868240401", "version": 1, "language": "vi", **p}}


def test_tool_execute_nhan_dung_dang_so_thich():
    for pb in (1, 2):
        TA.kiem_cong_cu("tool_execute", _st(version=pb))
    # ad_get dạng cũ vẫn qua (22/10/2026).
    TA.kiem_cong_cu("tool_execute", {"tool_name": "ad_get", "params": {
        "advertiser_id": "1", "fields": list(TA.TRUONG_AD_GET), "filtering": {"ad_ids": ["2"]},
        "page_size": 100}})
    assert TA.CONG_CU_DOC == {"auth_advertiser_get", "advertiser_info_get", "report_integrated_get",
                              "identity_get", "tool_execute"}


@pytest.mark.parametrize("args", [
    _st(version=3), _st(version=0), _st(version="1"), _st(version=True), _st(version=1.0),
    _st(language="en"), _st(language="VI"), _st(language=None), _st(advertiser_id=7418067),
    _st(advertiser_id="74x"), _st(advertiser_id=""), _st(advertiser_id="1" * 31),
    _st(page=1), _st(fields=["name"]),
    {"tool_name": TA.TOOL_SO_THICH, "params": {"advertiser_id": "1", "version": 1}},
    {"tool_name": TA.TOOL_SO_THICH, "params": {"advertiser_id": "1", "language": "vi"}},
    {"tool_name": TA.TOOL_SO_THICH, "params": {"version": 1, "language": "vi"}},
    {"tool_name": TA.TOOL_SO_THICH},
    {**_st(), "them": 1},
    {"tool_name": TA.TOOL_SO_THICH, "params": "advertiser_id=1"},
    {"tool_name": "tool_interest_keyword_get", "params": _st()["params"]},
    {"tool_name": "interest_category_get", "params": _st()["params"]},
    {"tool_name": "TOOL_INTEREST_CATEGORY_GET", "params": _st()["params"]},
    {"tool_name": "campaign_create", "params": _st()["params"]},
    None, [], "tool_interest_category_get",
])
def test_tool_execute_chan_moi_bien_the_truoc_khi_gui(args):
    tt = GiaTikTok()
    mcp = TA.Mcp(tt.access, TA.Http(transport=tt.transport(), ngu=lambda s: None))
    with pytest.raises(TA.LoiChan):
        mcp.goi("tool_execute", args)
    assert tt.goi == []                       # không một byte nào tới TikTok


def test_ghi_chu_cho_phep_co_ngay_va_chu_du_an():
    src = (GOC / "dashboard" / "tiktok_ads.py").read_text(encoding="utf-8")
    i = src.index("CONG_CU_DOC = frozenset")
    truoc = src[max(0, i - 1500):i]
    assert "28/10/2026" in truoc and "chủ dự án duyệt" in truoc
    assert "tool_interest_category_get" in truoc


# ───────────────────────────── 2. đọc sở thích + tên ─────────────────────────────
def test_doc_so_thich_cap_tai_khoan_va_chien_dich_va_ten():
    tt = _tt_so_thich()
    dv, kho_qc, tt = _dv(tt=tt)
    _ket_noi_san(dv, tt)
    kq = dv.dong_bo()
    assert not kq["loi"], kq
    # Cấp tài khoản: một lượt mỗi tài khoản chạy, chiều [advertiser_id, interest_category].
    tk = _audience(tt, "AUCTION_ADVERTISER", QC.CHIEU_SO_THICH)
    assert sorted(a["advertiser_id"] for a in tk) == sorted(CHAY)
    assert all(a["dimensions"] == ["advertiser_id", "interest_category"]
               and a["metrics"] == list(QC.CHI_SO_KHAN_GIA) for a in tk)
    kg = [r for r in kho_qc.bang["qc_khan_gia"].values() if r["chieu"] == QC.CHIEU_SO_THICH]
    assert {r["gia_tri"] for r in kg} == {"v1:116", "v1:101", "v1:130"}
    # Hai mã v1 cùng một mã v2 ("25") vẫn là HAI dòng (khoá nhóm = v1, không ghi đè / cộng).
    assert len(kg) == 3 * len(CHAY)
    r = next(x for x in kg if x["gia_tri"] == "v1:116")
    assert r["chi_so"]["interest_category_v2"] == "25"          # mã giữ dạng chuỗi
    assert "interest_category" not in r["chi_so"]
    # Cấp chiến dịch: cùng đường AUCTION_CAMPAIGN (lọc campaign_ids), đủ 3 chiến dịch × 3 nhóm.
    cd = [r for r in kho_qc.bang["qc_khan_gia_cd"].values() if r["chieu"] == QC.CHIEU_SO_THICH]
    assert len(cd) == 3 * 3 * 3 and {r["gia_tri"] for r in cd} == {"v1:116", "v1:101", "v1:130"}
    assert _audience(tt, "AUCTION_CAMPAIGN", QC.CHIEU_SO_THICH)
    # Phiên bản bộ chiều ghi cùng mốc.
    for a in CHAY:
        assert kho_qc.tk[a]["khan_gia_bo_chieu"] == TA.BO_CHIEU == 1
        assert kho_qc.tk[a]["khan_gia_cd_bo_chieu"] == TA.BO_CHIEU
    # Tên: MỘT lượt mỗi phiên bản, tài khoản đã đọc được; mã lạ / không tên bị bỏ; cha suy ra.
    goi = _ten_goi(tt)
    assert sorted(a["params"]["version"] for a in goi) == [1, 2]
    assert all(a["params"]["language"] == "vi" and a["params"]["advertiser_id"] in (*CHAY, LE)
               for a in goi)
    ds = kho_qc.so_thich
    assert set(ds) == {(1, "116"), (1, "101"), (1, "11601"), (2, "25")}
    assert ds[(1, "11601")]["cha"] == "116" and ds[(1, "11601")]["cap"] == 2
    assert ds[(1, "116")]["cha"] is None and ds[(1, "116")]["ten"] == "Làm đẹp"
    # Lần 2 cùng ngày: không đọc lại khán giả, không gọi lại tên (mốc tuần).
    tt.cong_cu.clear()
    dv.dong_bo()
    assert not _audience(tt) and not _ten_goi(tt)


def test_ten_doc_lai_sau_bay_ngay_va_khong_goi_khi_chua_co_so_thich():
    dv, _kho_qc, tt = _dv()                   # TikTok giả không trả dòng sở thích nào
    _ket_noi_san(dv, tt)
    dv.dong_bo()
    assert not _ten_goi(tt)                   # chưa có dòng sở thích → không tốn lượt gọi
    tt2 = _tt_so_thich()
    dv2, kho_qc2, tt2 = _dv(tt=tt2)
    _ket_noi_san(dv2, tt2, het_rt=BAY + datetime.timedelta(days=60))
    dv2.dong_bo()
    assert len(_ten_goi(tt2)) == 2
    kho_qc2.bay = BAY + datetime.timedelta(days=8)
    tt2.cong_cu.clear()
    dv3, _, _ = _dv(kho_qc2, tt2, bay=BAY + datetime.timedelta(days=8))
    dv3.dong_bo()
    assert len(_ten_goi(tt2)) == 2


def test_ten_loi_khong_lam_hong_luot():
    tt = _tt_so_thich()
    tt.ten_so_thich = {}                      # TikTok trả lỗi cho cả hai phiên bản
    nk: list[str] = []
    dv, kho_qc, tt = _dv(tt=tt)
    dv.log = nk.append
    _ket_noi_san(dv, tt)
    kq = dv.dong_bo()
    assert not kq["loi"] and not getattr(kho_qc, "so_thich", {})
    assert sum("tên sở thích" in x for x in nk) == 2
    assert any(r["chieu"] == QC.CHIEU_SO_THICH for r in kho_qc.bang["qc_khan_gia"].values())


def test_doc_so_thich_ham_thuan():
    class Mcp:
        def __init__(self):
            self.da_goi = []

        def goi(self, ten, a):
            TA.kiem_cong_cu(ten, a)                # đúng dạng chốt chỉ đọc nhận
            self.da_goi.append((ten, a))
            return {"interest_categories": TEN[1]}
    m = Mcp()
    rows = TA.doc_so_thich(m, "123", 1)
    assert m.da_goi == [("tool_execute", {"tool_name": TA.TOOL_SO_THICH, "params": {
        "advertiser_id": "123", "version": 1, "language": "vi"}})]
    assert {r["id"] for r in rows} == {"116", "101", "11601"}
    assert all(set(r) == {"phien_ban", "id", "ten", "cap", "cha"} for r in rows)


def test_nhan_so_thich_ten_va_du_phong():
    assert QC.ma_so_thich("116", "25") == "v1:116"
    assert QC.ma_so_thich(None, "25") == "v2:25" and QC.ma_so_thich("", None) == ""
    assert QC.ma_so_thich("x", "y") == ""
    assert QC.tach_so_thich("v1:116") == (1, "116") and QC.tach_so_thich("v3:1") is None
    assert QC.tach_so_thich("116") is None
    ten = {"v1:116": "Làm đẹp"}
    assert QC.nhan_gia_tri(QC.CHIEU_SO_THICH, "v1:116", ten) == "Làm đẹp"
    assert QC.nhan_gia_tri(QC.CHIEU_SO_THICH, "v1:101", ten) == "Sở thích 101"
    assert QC.nhan_gia_tri(QC.CHIEU_SO_THICH, "v2:25") == "Sở thích 25"
    assert QC.nhan_gia_tri(QC.CHIEU_SO_THICH, "") == "Không rõ"
    # Chiều khác không đổi.
    assert QC.nhan_gia_tri("gender", "FEMALE", ten) == "Nữ"
    assert QC.TEN_CHIEU[QC.CHIEU_SO_THICH] == "Sở thích (TikTok)"
    assert QC.CHIEU_TAT_CA[-1] == QC.CHIEU_SO_THICH and QC.CHIEU_SO_THICH not in QC.CHIEU_KHAN_GIA


# ───────────────────────────── 3. lỗi chiều sở thích không làm hỏng chiều khác ─────────────────
class _TikTokTuChoiSoThich(GiaTikTok):
    """TikTok từ chối chiều interest_category ở cấp `cap` (chưa đo thật ở cấp chiến dịch)."""

    cap = "AUCTION_CAMPAIGN"

    def _bao_cao(self, a):
        if (a["report_type"] == "AUDIENCE" and a["data_level"] == self.cap
                and a["dimensions"][-1] == QC.CHIEU_SO_THICH):
            return {"code": 40002, "message": "Invalid dimension: interest_category"}
        return super()._bao_cao(a)


def test_cap_chien_dich_tu_choi_so_thich_van_hoan_tat_cua_so():
    tt = _TikTokTuChoiSoThich()
    tt.so_thich = list(ST)
    nk: list[str] = []
    dv, kho_qc, tt = _dv(tt=tt)
    dv.log = nk.append
    _ket_noi_san(dv, tt)
    kq = dv.dong_bo()
    # Lỗi ghi vào `loi` của phần cấp chiến dịch (mỗi tài khoản), lượt số không lỗi.
    assert not kq["loi"] and kq["khan_gia_cd"]["loi"] == len(CHAY)
    assert sum("chiều interest_category" in x and "40002" in x for x in nk) == len(CHAY)
    # Bốn chiều kia hoàn tất: mốc dời, phiên bản ghi (không đọc lại mỗi ngày), không dòng sở thích dở.
    cd = kho_qc.bang["qc_khan_gia_cd"].values()
    assert {r["chieu"] for r in cd} == set(QC.CHIEU_KHAN_GIA)
    assert all(kho_qc.tk[a]["khan_gia_cd_den"] == datetime.date(2026, 10, 18)
               and kho_qc.tk[a]["khan_gia_cd_bo_chieu"] == TA.BO_CHIEU for a in CHAY)
    # Hôm sau: không tới hạn lại (đợi mốc tuần).
    tt.cong_cu.clear()
    dv2, _, _ = _dv(kho_qc, tt, bay=BAY + datetime.timedelta(days=1))
    dv2.dong_bo()
    assert not _audience(tt, "AUCTION_CAMPAIGN")
    # Lệnh khan-gia báo lỗi trong kết quả.
    assert "interest_category" in (dv2.doc_khan_gia([HAPAS_KOC])["loi"] or "")


class _LoSau(GiaTikTok):
    """Chiều sở thích cấp chiến dịch: lô có 1 chiến dịch (lô thứ hai khi LO_ID = 2) trả `ma`."""

    ma: int | None = None

    def _bao_cao(self, a):
        if (self.ma and a["report_type"] == "AUDIENCE" and a["data_level"] == "AUCTION_CAMPAIGN"
                and a["dimensions"][-1] == QC.CHIEU_SO_THICH
                and len(json.loads(a["filtering"][0]["filter_value"])) == 1):
            return {"code": self.ma, "message": "hỏng"}
        return super()._bao_cao(a)


def _lo_sau(monkeypatch):
    tt = _LoSau()
    tt.so_thich = list(ST)
    dv, kho_qc, tt = _dv(tt=tt)
    _ket_noi_san(dv, tt, het_rt=BAY + datetime.timedelta(days=60))
    dv.dong_bo()
    monkeypatch.setattr(TA, "LO_ID", 2)
    # Hôm sau, cửa sổ cấp chiến dịch của HAPAS_KOC còn bộ chiều cũ → tới hạn lại (cửa sổ mới 19/10).
    kho_qc.tk[HAPAS_KOC]["khan_gia_cd_bo_chieu"] = None
    dv2, _, _ = _dv(kho_qc, tt, bay=BAY + datetime.timedelta(days=1))
    return dv2, kho_qc, tt


def _cd(dv):
    """Chỉ phần khán giả cấp chiến dịch của lượt hằng ngày (LO_ID nhỏ chỉ dùng cho phần này)."""
    return dv.khan_gia_cd(dv.mcp(), [HAPAS_KOC], dv._bay_gio())


def _st_cd(kho_qc, den=None):
    return [r for r in kho_qc.bang["qc_khan_gia_cd"].values() if r["chieu"] == QC.CHIEU_SO_THICH
            and r["advertiser_id"] == HAPAS_KOC and (den is None or r["den"] == den)]


def test_cd_loi_tam_so_thich_khong_doi_moc_va_doc_lai(monkeypatch):
    """Lỗi TẠM (mã không phải từ chối chiều) ở lô thứ hai: như lỗi chiều chính — cửa sổ mới KHÔNG
    hoàn tất, mốc + phiên bản bộ chiều không dời (lượt sau đọc lại), lô đầu đã ghi theo từng lô nhưng
    vô hình; cửa sổ cũ vẫn là cửa sổ hiện."""
    dv2, kho_qc, tt = _lo_sau(monkeypatch)
    cu, moi = datetime.date(2026, 10, 18), datetime.date(2026, 10, 19)
    tt.ma = 50000
    kq = _cd(dv2)
    assert len(kq["loi"]) == 1 and kq["xong"] == 0
    t = kho_qc.tk[HAPAS_KOC]
    assert t["khan_gia_cd_den"] == cu and t["khan_gia_cd_bo_chieu"] is None
    assert _st_cd(kho_qc, moi)                         # lô đầu đã ghi (từng lô) …
    hien = kho_qc.ds_cd_khan_gia([HAPAS_KOC])["ds"]
    assert {x["den"] for x in hien} == {cu}            # … nhưng vô hình: cửa sổ cũ vẫn hiện
    assert TA.khan_gia_cd_den_han(t, moi, bo_chieu=TA.BO_CHIEU)
    # Lượt sau, TikTok ổn: hoàn tất cửa sổ mới, đủ sở thích, phiên bản ghi.
    tt.ma = None
    assert _cd(dv2)["xong"] == 1
    assert t["khan_gia_cd_den"] == moi and t["khan_gia_cd_bo_chieu"] == TA.BO_CHIEU
    assert len(_st_cd(kho_qc)) == 3 * 3 and {r["den"] for r in _st_cd(kho_qc)} == {moi}


def test_cd_tu_choi_giua_chung_bo_lo_da_ghi_va_lui_mot_tuan(monkeypatch):
    """TikTok TỪ CHỐI chiều (40002) ở lô thứ hai: lô đầu đã ghi bị bỏ khi hoàn tất (không nửa
    chiều), cửa sổ hoàn tất với bốn chiều kia, phiên bản bộ chiều dời (lùi một tuần)."""
    dv2, kho_qc, tt = _lo_sau(monkeypatch)
    tt.ma = 40002
    kq = _cd(dv2)
    assert len(kq["loi"]) == 1 and kq["xong"] == 1 and "từ chối" in kq["loi"][0]
    t = kho_qc.tk[HAPAS_KOC]
    moi = datetime.date(2026, 10, 19)
    assert t["khan_gia_cd_den"] == moi and t["khan_gia_cd_bo_chieu"] == TA.BO_CHIEU
    assert _st_cd(kho_qc) == []
    assert {r["chieu"] for r in kho_qc.bang["qc_khan_gia_cd"].values()
            if r["advertiser_id"] == HAPAS_KOC} == set(QC.CHIEU_KHAN_GIA)


def test_phan_loai_tu_choi_chieu():
    assert TA.la_tu_choi_chieu(TA.LoiTikTok("x", 40002))
    for e in (TA.LoiTikTok("x", 50000), TA.LoiTikTok("x"), TA.LoiTikTok("x", 40100),
              TA.LoiXacThuc("x", 40002), KQ.LoiKho("bảng chưa có"), ValueError("x")):
        assert not TA.la_tu_choi_chieu(e), e


def test_cap_tai_khoan_loi_tam_khong_ghi_bo_chieu():
    class _TkTam(GiaTikTok):
        ma = 50000

        def _bao_cao(self, a):
            if (self.ma and a["report_type"] == "AUDIENCE"
                    and a["data_level"] == "AUCTION_ADVERTISER"
                    and a["dimensions"][-1] == QC.CHIEU_SO_THICH):
                return {"code": self.ma, "message": "tạm"}
            return super()._bao_cao(a)
    tt = _TkTam()
    tt.so_thich = list(ST)
    dv, kho_qc, tt = _dv(tt=tt)
    _ket_noi_san(dv, tt, het_rt=BAY + datetime.timedelta(days=60))
    dv.dong_bo()
    for a in CHAY:
        t = kho_qc.tk[a]
        assert t["khan_gia_luc"] == BAY and t.get("khan_gia_bo_chieu") is None
    # Hôm sau tới hạn lại (dù mốc tuần còn mới); TikTok ổn → ghi phiên bản.
    tt.ma = None
    tt.cong_cu.clear()
    dv2, _, _ = _dv(kho_qc, tt, bay=BAY + datetime.timedelta(days=1))
    dv2.dong_bo()
    assert _audience(tt, "AUCTION_ADVERTISER", QC.CHIEU_SO_THICH)
    assert all(kho_qc.tk[a]["khan_gia_bo_chieu"] == TA.BO_CHIEU for a in CHAY)


def test_dong_chi_co_ma_v2_thanh_v2_va_ten_tu_danh_muc_v2():
    """Đo thật 28/10/2026: 5/20 dòng cấp tài khoản có interest_category = null, chỉ có
    interest_category_v2 (vd "18") → giá trị "v2:18", tên từ danh mục v2."""
    tt = _tt_so_thich()
    tt.so_thich = [*ST, (None, "18")]
    tt.ten_so_thich[2].append({"interest_category_id": "18", "interest_category_name": "Thời trang",
                               "level": 1, "sub_category_ids": ["1801"]})
    _app, c, _kho, kq, tt, _dv_tt = _co_so(_tao_app(tt=tt))
    dang_nhap(c, QL)
    kg = [r for r in kq.bang["qc_khan_gia"].values() if r["chieu"] == QC.CHIEU_SO_THICH]
    v2 = [r for r in kg if r["gia_tri"] == "v2:18"]
    assert len(v2) == len(CHAY) and all(r["chi_so"]["interest_category_v2"] == "18" for r in v2)
    assert kq.so_thich[(2, "18")]["ten"] == "Thời trang"
    st = {x["gia_tri"]: x for x in _api(c)["khan_gia"][QC.CHIEU_SO_THICH]}
    assert st["v2:18"]["nhan"] == "Thời trang" and st["v1:116"]["nhan"] == "Làm đẹp"
    assert any(r["gia_tri"] == "v2:18" for r in kq.bang["qc_khan_gia_cd"].values())


def test_cap_tai_khoan_tu_choi_so_thich_van_ghi_bon_chieu():
    tt = _TikTokTuChoiSoThich()
    tt.cap = "AUCTION_ADVERTISER"
    tt.so_thich = list(ST)
    nk: list[str] = []
    dv, kho_qc, tt = _dv(tt=tt)
    dv.log = nk.append
    _ket_noi_san(dv, tt)
    kq = dv.dong_bo()
    assert not kq["loi"]
    kg = kho_qc.bang["qc_khan_gia"].values()
    assert {r["chieu"] for r in kg} == set(QC.CHIEU_KHAN_GIA) and len(kg) == 4 * 2 * 3
    assert all(kho_qc.tk[a]["khan_gia_bo_chieu"] == TA.BO_CHIEU for a in CHAY)
    assert sum("interest_category" in x for x in nk) == len(CHAY)


# ───────────────────────────── 4. tới hạn theo bộ chiều ─────────────────────────────
def test_den_han_ham_thuan():
    bay = BAY
    hq = datetime.date(2026, 10, 18)
    moi = {"khan_gia_luc": bay - datetime.timedelta(days=1), "khan_gia_cd_den": hq}
    # Meta (không truyền bo_chieu): như cũ.
    assert not TA.khan_gia_den_han(moi, bay) and not TA.khan_gia_cd_den_han(moi, hq)
    # TikTok, cửa sổ đọc bằng bộ cũ (NULL) → tới hạn ngay.
    assert TA.khan_gia_den_han(moi, bay, bo_chieu=1)
    assert TA.khan_gia_cd_den_han(moi, hq, bo_chieu=1)
    xong = {**moi, "khan_gia_bo_chieu": 1, "khan_gia_cd_bo_chieu": 1}
    assert not TA.khan_gia_den_han(xong, bay, bo_chieu=1)
    assert not TA.khan_gia_cd_den_han(xong, hq, bo_chieu=1)
    # Bộ chiều sau (2) → tới hạn lại; giá trị lạ coi như cũ.
    assert TA.khan_gia_den_han(xong, bay, bo_chieu=2)
    assert TA.khan_gia_cd_den_han({**xong, "khan_gia_cd_bo_chieu": True}, hq, bo_chieu=1)


def _bo_cu(kho_qc):
    """Giả trạng thái TRƯỚC 28/10/2026: cửa sổ mới (trong tuần) nhưng đọc bằng bộ chiều cũ."""
    for a in CHAY:
        kho_qc.tk[a].pop("khan_gia_bo_chieu", None)
        kho_qc.tk[a].pop("khan_gia_cd_bo_chieu", None)
    for b in ("qc_khan_gia", "qc_khan_gia_cd"):
        for k in [k for k, r in kho_qc.bang[b].items() if r["chieu"] == QC.CHIEU_SO_THICH]:
            del kho_qc.bang[b][k]


def test_bo_chieu_cu_den_han_mot_lan_va_cua_so_cu_van_hien():
    tt = _tt_so_thich()
    dv, kho_qc, tt = _dv(tt=tt)
    _ket_noi_san(dv, tt, het_rt=BAY + datetime.timedelta(days=60))
    dv.dong_bo()
    _bo_cu(kho_qc)
    cu = {k: dict(r) for k, r in kho_qc.bang["qc_khan_gia_cd"].items()}
    # Lượt kế tiếp (hôm sau) bị giết giữa phần cấp chiến dịch: cửa sổ cũ (bộ cũ) vẫn là cửa sổ hiện.
    sau = BAY + datetime.timedelta(days=1)

    class _Giet(GiaTikTok):
        def _bao_cao(self, a):
            if a["report_type"] == "AUDIENCE" and a["data_level"] == "AUCTION_CAMPAIGN":
                raise SystemExit(143)
            return super()._bao_cao(a)
    tg = _Giet()
    tg.so_thich, tg.token_hop_le, tg.access, tg.refresh = ST, tt.token_hop_le, tt.access, tt.refresh
    dvg, _, _ = _dv(kho_qc, tg, bay=sau)
    with pytest.raises(SystemExit):
        dvg.dong_bo()
    ids = list(CHAY)
    hien = kho_qc.ds_cd_khan_gia(ids)["ds"]
    assert len(hien) == 9 and all(kho_qc.tk[a]["khan_gia_cd_den"] == datetime.date(2026, 10, 18)
                                  for a in CHAY)
    assert {k for k, r in kho_qc.bang["qc_khan_gia_cd"].items()
            if r["den"] == datetime.date(2026, 10, 18)} == set(cu)
    # Cấp tài khoản đã đọc lại (bộ mới, cửa sổ mới) trước khi bị giết.
    assert all(kho_qc.tk[a]["khan_gia_bo_chieu"] == TA.BO_CHIEU for a in CHAY)
    # Lượt sau hoàn tất: cửa sổ mới có sở thích; phiên bản ghi; lượt kế tiếp KHÔNG đọc lại.
    tt.cong_cu.clear()
    dv2, _, _ = _dv(kho_qc, tt, bay=sau)
    dv2.dong_bo()
    moi = datetime.date(2026, 10, 19)
    assert {r["den"] for r in kho_qc.bang["qc_khan_gia_cd"].values()} == {moi}
    assert any(r["chieu"] == QC.CHIEU_SO_THICH for r in kho_qc.bang["qc_khan_gia_cd"].values())
    assert all(kho_qc.tk[a]["khan_gia_cd_bo_chieu"] == TA.BO_CHIEU for a in CHAY)
    tt.cong_cu.clear()
    dv3, _, _ = _dv(kho_qc, tt, bay=sau + datetime.timedelta(days=1))
    dv3.dong_bo()
    assert not _audience(tt)


def test_tai_khoan_khong_co_dong_so_thich_khong_doc_lai_moi_ngay():
    dv, kho_qc, tt = _dv()                    # TikTok không trả dòng sở thích nào
    _ket_noi_san(dv, tt, het_rt=BAY + datetime.timedelta(days=60))
    dv.dong_bo()
    assert all(kho_qc.tk[a]["khan_gia_bo_chieu"] == TA.BO_CHIEU
               and kho_qc.tk[a]["khan_gia_cd_bo_chieu"] == TA.BO_CHIEU for a in CHAY)
    for n in (1, 2, 3):
        tt.cong_cu.clear()
        dvn, _, _ = _dv(kho_qc, tt, bay=BAY + datetime.timedelta(days=n))
        dvn.dong_bo()
        assert not _audience(tt), n


def test_meta_khong_doi_cach_toi_han():
    """Meta dùng chung luot_khan_gia_cd / khan_gia_den_han nhưng không truyền bo_chieu: cột phiên
    bản NULL không làm tài khoản Meta tới hạn."""
    t = {"khan_gia_luc": BAY, "khan_gia_cd_den": datetime.date(2026, 10, 18)}
    assert not TA.khan_gia_den_han(t, BAY) and not TA.khan_gia_cd_den_han(
        t, datetime.date(2026, 10, 18))
    src = (GOC / "dashboard" / "meta_ads.py").read_text(encoding="utf-8")
    assert "bo_chieu" not in src and "CHIEU_SO_THICH" not in src


# ───────────────────────────── 5. trang: khối Khán giả ─────────────────────────────
def _app_so_thich(ten=True):
    tt = _tt_so_thich()
    if not ten:
        tt.ten_so_thich = {}
    app, c, _kho, kq, tt, _dv_tt = _co_so(_tao_app(tt=tt))
    dang_nhap(c, QL)
    return app, c, kq, tt


def _api(c, **kw):
    return c.get(f"/api/qc?{Q}&{urlencode(kw, doseq=True)}").json()


def _khoi(t: str) -> str:
    return t.split('id="qc-kg-tieu-de"')[1].split("</section>")[0]


def test_khoi_khan_gia_so_thich_mau_so_la_tong_tiktok_cung_pham_vi():
    _app, c, kq, _tt = _app_so_thich()
    d = _api(c)
    st = d["khan_gia"][QC.CHIEU_SO_THICH]
    assert [x["nhan"] for x in st][:2] and {x["nhan"] for x in st} == {
        "Làm đẹp", "Giáo dục", "Sở thích 130"}
    # Mẫu số: tổng hiển thị theo TUỔI của các tài khoản có dòng sở thích (không phải tổng nhóm).
    kg = [r for r in kq.bang["qc_khan_gia"].values() if r["advertiser_id"] in CHAY]
    mau = sum(r["hien_thi"] for r in kg if r["chieu"] == "age")
    for x in st:
        assert x["pt"] == round(100.0 * x["hien_thi"] / mau, 1)
    tong_nhom = sum(x["hien_thi"] for x in st)
    assert tong_nhom != mau and sum(x["pt"] for x in st) != 100.0
    # Trang: cột "Sở thích (TikTok)" cùng kiểu thanh; (i) giải thích mẫu số, không chữ nhỏ mới.
    k = _khoi(c.get(f"/quang-cao?{Q}").text)
    assert '<h3 class="qc-h3">Sở thích (TikTok)</h3>' in k and "Làm đẹp" in k
    assert "Sở thích 130" in k
    i = k.split('class="goi-y" data-goi-y="')[1].split('">i</button>')[0]
    assert "tổng lượt hiển thị TikTok cùng phạm vi" in i and "vượt 100%" in i


def test_so_thich_theo_chien_dich_kg_cd_va_loc_ten():
    _app, c, kq, _tt = _app_so_thich()
    ma = f"ca{MM_MKT[-4:]}0001"
    d = _api(c, kg_cd=ma)
    st = d["khan_gia"][QC.CHIEU_SO_THICH]
    rows = [r for r in kq.bang["qc_khan_gia_cd"].values() if r["campaign_id"] == ma]
    mau = sum(r["hien_thi"] for r in rows if r["chieu"] == "age")
    assert st and {x["gia_tri"] for x in st} == {"v1:116", "v1:101", "v1:130"}
    assert all(x["pt"] == round(100.0 * x["hien_thi"] / mau, 1) for x in st)
    # Hai chiến dịch: cộng hiển thị, mẫu số là tổng tuổi của đúng hai chiến dịch.
    mb = f"ca{HAPAS_KOC[-4:]}0000"
    d2 = _api(c, kg_cd=[ma, mb])
    st2 = {x["gia_tri"]: x for x in d2["khan_gia"][QC.CHIEU_SO_THICH]}
    rows2 = [r for r in kq.bang["qc_khan_gia_cd"].values() if r["campaign_id"] in (ma, mb)]
    mau2 = sum(r["hien_thi"] for r in rows2 if r["chieu"] == "age")
    h = sum(r["hien_thi"] for r in rows2 if r["gia_tri"] == "v1:116")
    assert st2["v1:116"]["hien_thi"] == h and st2["v1:116"]["pt"] == round(100.0 * h / mau2, 1)


def test_so_thich_thieu_ten_va_meta_khong_co_cot():
    _app, c, _kq, _tt = _app_so_thich(ten=False)
    st = _api(c)["khan_gia"][QC.CHIEU_SO_THICH]
    assert {x["nhan"] for x in st} == {"Sở thích 116", "Sở thích 101", "Sở thích 130"}
    # Chỉ Meta: không có cột sở thích.
    h = _app_hai_nen_tang()
    dang_nhap(h.c, QL)
    d = h.c.get(f"/api/qc?{Q}&nen_tang=meta").json()
    assert d["khan_gia"][QC.CHIEU_SO_THICH] == []
    assert '<h3 class="qc-h3">Sở thích (TikTok)</h3>' not in _khoi(
        h.c.get(f"/quang-cao?{Q}&nen_tang=meta").text)


def test_khan_gia_ham_thuan_mau_so_va_khong_gop_theo_ten():
    rows = [{"chieu": "age", "gia_tri": "AGE_18_24", "hien_thi": 600},
            {"chieu": "age", "gia_tri": "AGE_25_34", "hien_thi": 400},
            {"chieu": QC.CHIEU_SO_THICH, "gia_tri": "v1:116", "hien_thi": 700},
            {"chieu": QC.CHIEU_SO_THICH, "gia_tri": "v1:130", "hien_thi": 500}]
    ten = {"v1:116": "Làm đẹp", "v1:130": "Làm đẹp"}       # hai mã trùng tên → vẫn hai dòng
    kg = QC.khan_gia(rows, ten, 1000)
    assert [(x["nhan"], x["hien_thi"], x["pt"]) for x in kg[QC.CHIEU_SO_THICH]] == [
        ("Làm đẹp", 700, 70.0), ("Làm đẹp", 500, 50.0)]
    assert [x["pt"] for x in kg["age"]] == [60.0, 40.0]
    assert all(x["pt"] is None for x in QC.khan_gia(rows, ten, None)[QC.CHIEU_SO_THICH])
    assert all(x["pt"] is None for x in QC.khan_gia(rows, ten, 0)[QC.CHIEU_SO_THICH])


def test_sql_mau_so_thich_va_ten(monkeypatch):
    g = _GhiSQL({"GROUP BY k.chieu, k.gia_tri": [
        {"chieu": QC.CHIEU_SO_THICH, "gia_tri": "v1:116", "tu": 1, "den": 2}],
        "AS mau": [{"mau": 99}], "VALUES (1), (2)": [{"phien_ban": 2}], "FROM qc_so_thich": [
            {"phien_ban": 1, "id": "116", "ten": "Làm đẹp"}, {"phien_ban": 2, "id": "25", "ten": ""}]})
    monkeypatch.setattr(KQ, "ket_noi", g)
    assert KQ.qc_khan_gia([HAPAS_KOC])["mau_so_thich"] == 99
    assert KQ.qc_khan_gia_cd([HAPAS_KOC], ["7"])["mau_so_thich"] == 99
    assert KQ.ten_so_thich(["v1:116", "v2:25", "x", "116"]) == {"v1:116": "Làm đẹp"}
    assert KQ.so_thich_can_lam_moi(7) == [2]
    for sql, ts in g.cau:
        assert sql.count("%s") == len(ts or ()), sql
    mau = [s for s, _ in g.cau if "AS mau" in s]
    assert len(mau) == 2
    for s in mau:
        assert "k.chieu = 'age'" in s and "i.chieu = 'interest_category'" in s and "EXISTS" in s
    assert "i.campaign_id = k.campaign_id" in mau[1] and "k.campaign_id = ANY(%s)" in mau[1]
    assert mau[0].startswith(KQ._MOI_TK) and mau[1].startswith(KQ._MOI_CD)
    ten = next((s, t) for s, t in g.cau if "FROM qc_so_thich" in s)
    assert ten[1] == (["116"], ["25"])
    # Không dòng sở thích → không truy vấn mẫu số; không mã hợp lệ → không truy vấn tên.
    g2 = _GhiSQL({"GROUP BY": [{"chieu": "age", "gia_tri": "A", "tu": 1, "den": 2}]})
    monkeypatch.setattr(KQ, "ket_noi", g2)
    assert KQ.qc_khan_gia([HAPAS_KOC])["mau_so_thich"] is None and len(g2.cau) == 1
    assert KQ.ten_so_thich(["x"]) == {} and len(g2.cau) == 1
    s = (KQ.sql_upsert("qc_khan_gia"))
    assert "ON CONFLICT (advertiser_id, tu, den, chieu, gia_tri)" in s


def test_sql_moc_bo_chieu(monkeypatch):
    g = _GhiSQL()
    g.rowcount = 0
    monkeypatch.setattr(KQ, "ket_noi", g)
    luc = datetime.datetime(2026, 10, 28, tzinfo=datetime.UTC)
    KQ.dat_khan_gia("1", bo_chieu=1)
    KQ.dat_khan_gia("act_2")
    KQ.xong_khan_gia_cd("1", datetime.date(2026, 10, 27), luc, bo_chieu=1)
    cau = [c for c in g.cau if c[0].startswith("UPDATE tk_quang_cao")]
    assert cau[0] == (("UPDATE tk_quang_cao SET khan_gia_luc = now(), khan_gia_bo_chieu = %s "
                       "WHERE advertiser_id = %s"), (1, "1"))
    assert cau[1] == ("UPDATE tk_quang_cao SET khan_gia_luc = now() WHERE advertiser_id = %s",
                      ("act_2",))
    assert cau[2] == (("UPDATE tk_quang_cao SET khan_gia_cd_den = %s, khan_gia_cd_bo_chieu = %s "
                       "WHERE advertiser_id = %s"), (datetime.date(2026, 10, 27), 1, "1"))
    assert "khan_gia_bo_chieu" in KQ._COT_TK and "khan_gia_cd_bo_chieu" in KQ._COT_TK


# ───────────────────────────── 6. click bấm liên kết ─────────────────────────────
def test_sql_click_lien_ket_va_lpv():
    s = KQ.click_lk_sql()
    assert "left(advertiser_id, 4) = 'act_'" in s and "chi_so->'inline_link_clicks'" in s
    assert "ELSE click END" in s and "%" not in s
    assert "q.chi_so" in KQ.click_lk_sql("q.") and "left(q.advertiser_id, 4)" in KQ.click_lk_sql("q.")
    lpv = KQ.lpv_sql()
    assert "total_landing_page_view" in lpv and "actions__landing_page_view" in lpv
    assert "AS click_lk" in KQ._TONG_LL and "AS lpv" in KQ._TONG_LL and "%" not in KQ._TONG_LL
    for x in ("x'; drop", "q", "qq."):
        with pytest.raises(ValueError):
            KQ.click_lk_sql(x)
    # Bảng: Click / CTR / CPC xếp theo click_lk; CPC + LPV xếp được; CPC dưới ngưỡng xuống cuối.
    assert KQ.SAP_BANG_SQL["click"] == "t.click_lk" and "t.click_lk" in KQ.SAP_BANG_SQL["ctr"]
    assert "t.chi / t.click_lk" in KQ.SAP_BANG_SQL["cpc"] and KQ.SAP_BANG_SQL["lpv"] == "t.lpv"
    assert str(QC.NGUONG_TI_LE) in KQ.SAP_BANG_SQL["cpc"]
    assert set(KQ.SAP_BANG_SQL) >= set(QC.SAP_BANG)
    sql = KQ.sql_bang("ad", "cpc", False, loc_ma=False, cd=False)
    assert KQ._TONG_LL in sql and sql.count("%s") == 5
    # Khối kênh đăng: click_lk theo quảng cáo, gộp theo kênh + phần chưa rõ.
    kenh, phu = KQ.sql_kenh_dang("hien_thi")
    assert "AS click_lk" in kenh and "sum(a.click_lk)" in kenh and "AS click_lk" in phu
    assert "left(q.advertiser_id, 4)" in kenh and "left(q.advertiser_id, 4)" in phu


def test_click_meta_la_inline_link_clicks_tiktok_la_clicks():
    h = _app_hai_nen_tang()
    c, kq = h.c, h.kho_qc
    dang_nhap(c, QL)
    d = c.get(f"/api/qc?{Q}").json()
    ids = {t["advertiser_id"] for t in d["tai_khoan"]}
    ky = [r for r in kq.bang["qc_tk_ngay"].values() if r["advertiser_id"] in ids
          and datetime.date(2026, 10, 12) <= r["ngay"] <= datetime.date(2026, 10, 18)]
    tt = [r for r in ky if not r["advertiser_id"].startswith("act_")]
    mt = [r for r in ky if r["advertiser_id"].startswith("act_")]
    assert tt and mt
    lk_meta = sum(r["chi_so"]["inline_link_clicks"] for r in mt)
    assert lk_meta < sum(r["click"] for r in mt)            # Meta: bấm liên kết < mọi lượt bấm
    nen = {n["nen_tang"]: n["kpi"] for n in d["theo_nen_tang"]}
    assert nen["meta"]["click_lk"] == lk_meta
    assert nen["tiktok"]["click_lk"] == sum(r["click"] for r in tt)
    assert d["kpi"]["click_lk"] == lk_meta + nen["tiktok"]["click_lk"]
    k = d["kpi"]
    assert k["ctr"] == round(k["click_lk"] / k["hien_thi"] * 100, 4)
    assert k["cpc"] == round(k["chi"] / k["click_lk"], 2)
    # Cột click của kho KHÔNG đổi (BigQuery / Mark).
    assert k["click"] == sum(r["click"] for r in mt) + nen["tiktok"]["click_lk"]
    # Ô CTR có sẵn ở hàng KPI + khối TikTok và Meta dùng click_lk.
    t = c.get(f"/quang-cao?{Q}").text
    ctr = f"{k['click_lk'] / k['hien_thi'] * 100:.2f}".replace(".", ",")
    kpi = t.split('id="qc-kpi"')[1].split("</section>")[0]
    assert 'data-kpi="ctr"' not in kpi and 'data-kpi="cpm"' in kpi    # CTR không hiện hai lần
    ll = t.split('data-o="luu-luong"')[1].split("</section>")[0]
    assert f">{ctr}%<" in ll
    m = nen["meta"]
    chia = t.split('aria-labelledby="qc-chia-tieu-de"')[1].split("</section>")[0]
    assert f"{m['click_lk'] / m['hien_thi'] * 100:.2f}".replace(".", ",") + "%" in chia
    # Dòng Meta vắng inline_link_clicks (Meta bỏ số 0) → 0, không lùi về mọi lượt bấm.
    from test_tiktok_ads import click_lk
    assert click_lk({"advertiser_id": "act_1", "click": 9, "chi_so": {}}) == 0
    assert click_lk({"advertiser_id": "act_1", "click": None, "chi_so": {}}) is None
    assert click_lk({"advertiser_id": "123", "click": 9, "chi_so": {"inline_link_clicks": 1}}) == 9


def test_kpi_luu_luong_ham_thuan():
    k = QC.kpi({"chi": 1000.0, "hien_thi": 10_000, "click": 300, "click_lk": 200, "lpv": 50,
                "xem_sp_shop": 7, "xem_sp_web": 0})
    assert (k["ctr"], k["cpc"], k["chi_tren_lpv"]) == (2.0, 5.0, 20.0)
    assert k["click_lk"] == 200 and k["xem_sp_shop"] == 7
    rong = QC.kpi({})
    assert rong["ctr"] is None and rong["cpc"] is None and rong["chi_tren_lpv"] is None
    assert QC.la_tien("cpc") and QC.la_tien("chi_tren_lpv")
    for m in ("click_lk", "ctr", "lpv", "xem_sp_shop", "xem_sp_web"):
        assert not QC.la_tien(m), m
    # Sheet dùng chung hieu_qua: Click / CTR / CPC theo click_lk khi có; dòng cũ lùi về click.
    h = QC.hieu_qua({"chi": 100.0, "hien_thi": 1000, "click": 50, "click_lk": 20})
    assert (h["click_lk"], h["ctr"], h["cpc"]) == (20, 2.0, 5.0)
    assert QC.hieu_qua({"chi": 100.0, "hien_thi": 1000, "click": 50})["click_lk"] == 50


# ───────────────────────────── 7. mục Lưu lượng truy cập ─────────────────────────────
def _o_ll(t: str) -> dict[str, str]:
    k = t.split('data-o="luu-luong"')[1].split("</section>")[0]
    return {m.group(1): m.group(2) for m in re.finditer(
        r'data-kpi="(\w+)">.*?class="kpi__so" title="[^"]*">([^<]*)<', k, re.DOTALL)}


def test_muc_luu_luong_tat_ca_nen_tang_va_loc_nen_tang():
    h = _app_hai_nen_tang()
    c = h.c
    dang_nhap(c, QL)
    t = c.get(f"/quang-cao?{Q}").text
    o = _o_ll(t)
    assert list(o) == ["click_lk", "ctr", "cpc", "lpv", "chi_tren_lpv", "xem_sp_shop", "xem_sp_web"]
    assert ">Lưu lượng truy cập</h2>" in t
    # Số đầy đủ chấm nghìn, không viết tắt; tiền có ₫.
    d = c.get(f"/api/qc?{Q}").json()
    assert o["click_lk"] == f"{d['kpi']['click_lk']:,}".replace(",", ".")
    assert o["cpc"].endswith(" ₫") and not re.search(r"\d\s?(tr|tỷ|N|K)\b", " ".join(o.values()))
    # Giải thích chỉ ở nút (i) của từng ô — không dòng chữ nhỏ.
    k = t.split('data-o="luu-luong"')[1].split("</section>")[0]
    assert k.count('class="goi-y"') == 7 and "mo nho" not in k and "<p" not in k
    assert "inline_link_clicks" in k and "total_landing_page_view" in k
    # ▲▼ so với kỳ trước như ô KPI (kỳ trước của dữ liệu giả trống); ss=khong → không ▲▼.
    assert "so với kỳ trước" in k or "kỳ trước chưa có số" in k
    k2 = c.get(f"/quang-cao?{Q}&ss=khong").text.split('data-o="luu-luong"')[1].split("</section>")[0]
    assert "so với kỳ trước" not in k2 and "kỳ trước chưa có số" not in k2
    # Lọc TikTok: không ô Xem SP website; lọc Meta: không ô Xem trang SP TikTok Shop.
    assert "xem_sp_web" not in _o_ll(c.get(f"/quang-cao?{Q}&nen_tang=tiktok").text)
    om = _o_ll(c.get(f"/quang-cao?{Q}&nen_tang=meta").text)
    assert "xem_sp_shop" not in om and "xem_sp_web" in om


def test_muc_luu_luong_an_o_tien_khi_khong_xem_tien(monkeypatch):
    _app, c, _kq, _tt = _app_so_thich()
    monkeypatch.setattr(QC, "xem_tien", lambda q, ben: False)
    t = c.get(f"/quang-cao?{Q}").text
    o = _o_ll(t)
    assert list(o) == ["click_lk", "ctr", "lpv", "xem_sp_shop"]
    d = c.get(f"/api/qc?{Q}").json()
    khoa = set(_khoa_lap(d))
    assert not {"cpc", "chi_tren_lpv", "chi"} & khoa
    # Bảng: không cột / không xếp CPC (sap=cpc → mặc định hiển thị).
    assert "Xếp theo CPC" not in t and "Xếp theo Landing page view" in t
    assert c.get(f"/api/qc?{Q}&sap=cpc").json()["sap"] == "hien_thi"


def test_chon_luu_luong_ham_thuan():
    assert QC.chon_luu_luong(True, ["tiktok", "meta"]) == tuple(QC.KPI_LUU_LUONG)
    assert QC.chon_luu_luong(False, ["tiktok"]) == ("click_lk", "ctr", "lpv", "xem_sp_shop")
    assert QC.chon_luu_luong(True, []) == ("click_lk", "ctr", "cpc", "lpv", "chi_tren_lpv")
    # Mark không đổi: ô mới không nằm trong KPI_QC (hoi_dashboard lọc theo KPI_QC).
    assert not set(QC.KPI_LUU_LUONG) & set(QC.KPI_QC)


# ───────────────────────────── 8. bảng + biểu đồ ─────────────────────────────
def test_bang_cot_cpc_lpv_va_xep():
    _app, c, _kq, _tt = _app_so_thich()
    t = c.get(f"/quang-cao?{Q}").text
    bang = t.split('id="qc-top-tieu-de"')[1]
    for nhan in ("Click", "CTR", "CPC", "Landing page view"):
        assert f"Xếp theo {nhan}," in bang, nhan
    assert 'data-nhan="CPC"' in bang and 'data-nhan="Landing page view"' in bang
    assert ("cpc", "CPC") in [(m, x) for m, x in QC.SAP_BANG.items()] and "cpc" in QC.SAP_BANG_TIEN
    assert "lpv" not in QC.SAP_BANG_TIEN
    # Xếp theo LPV: giảm dần, mọi dòng có lpv (ad TikTok có total_landing_page_view ở CHI_SO_AD).
    assert "total_landing_page_view" in QC.CHI_SO_AD
    for cap in ("campaign", "ad"):
        d = c.get(f"/api/qc?{Q}&sap=lpv").json()[cap]
        v = [r["lpv"] for r in d]
        assert v and v == sorted(v, reverse=True) and all(x > 0 for x in v), cap
    d = c.get(f"/api/qc?{Q}&sap=cpc&chieu=tang").json()
    assert d["sap"] == "cpc"
    cpc = [r["chi"] / r["click_lk"] for r in d["campaign"] if r["click_lk"] and r["hien_thi"] >= 1000]
    assert cpc == sorted(cpc)
    # Trang bảng: CPC = chi ÷ click_lk (làm tròn đồng, chấm nghìn).
    r0 = c.get(f"/api/qc?{Q}&sap=chi").json()["campaign"][0]
    assert f'data-nhan="CPC">{A.so_vn(math.floor(r0["chi"] / r0["click_lk"] + 0.5))}<' in c.get(
        f"/quang-cao?{Q}&sap=chi").text


def test_bieu_do_chuoi_click_va_lpv():
    _app, c, _kq, _tt = _app_so_thich()
    d = c.get(f"/api/qc?{Q}").json()
    assert all("click_lk" in r and "lpv" in r for r in d["theo_ngay"])
    assert all("click_lk" in r and "lpv" in r for r in d["theo_ngay_nen_tang"])
    assert sum(r["lpv"] for r in d["theo_ngay"]) > 0
    tuan = d["theo_ky"].get("tuan")
    if tuan:
        assert sum(r["lpv"] for r in tuan["chung"]) == sum(r["lpv"] for r in d["theo_ngay"])
    js = (GOC / "dashboard" / "static" / "qc.js").read_text(encoding="utf-8")
    m = re.search(r"var CHUOI = \[(.*?)\];", js, re.DOTALL).group(1)
    assert '["click_lk", "Click"]' in m and '["lpv", "Landing page view"]' in m
    assert '"click"' not in m
    assert ("click_lk", "Click") in A._CHUOI_QC and ("lpv", "Landing page view") in A._CHUOI_QC
    # (i) của biểu đồ luôn có, định nghĩa Click / LPV.
    t = c.get(f"/quang-cao?{Q}").text
    xh = t.split('id="qc-xh-tieu-de"')[1][:2500]
    assert "Giải thích chỉ số trên biểu đồ" in xh and "inline_link_clicks" in xh


def test_kenh_dang_click_lien_ket():
    r = {"nen_tang": "meta", "kenh_id": "1", "ten": "Page", "chi": 1, "hien_thi": 2, "click": 10,
         "click_lk": 4, "view_video": 0, "follow": 0, "tk_ids": []}
    assert KD.dong(r, {})["click"] == 4
    assert KD.dong({k: v for k, v in r.items() if k != "click_lk"}, {})["click"] == 10


# ───────────────────────────── 9. Lark Sheet ─────────────────────────────
def test_sheet_cung_click_lien_ket_va_trigger_nhan_sap_moi():
    import xuat_sheet_qc as X
    assert ("click_lk", "Click", "so_nguyen") in X._COT_SO
    assert X._so({"click": 50, "click_lk": 20, "hien_thi": 1000, "chi": 100.0}, False)[
        [m for m, _, _ in X._cot(False)].index("click_lk")] == 20
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    ds = re.search(r"NEW\.sap NOT IN \((.*?)\) THEN", sql, re.DOTALL).group(1)
    assert set(re.findall(r"'(\w+)'", ds)) == set(QC.SAP_BANG) | {"roas"}
    assert QC.loc_bang({"sap": "cpc"}, True)["sap"] == "cpc"
    assert QC.loc_bang({"sap": "cpc"}, False)["sap"] == "hien_thi"
    assert QC.loc_bang({"sap": "lpv"}, False)["sap"] == "lpv"


def test_sheet_sql_click_lk(monkeypatch):
    g = _GhiSQL()
    monkeypatch.setattr(KS, "ket_noi", g)
    a, b = datetime.date(2026, 10, 1), datetime.date(2026, 10, 2)
    KS.doc_theo_ngay(["1"], a, b)
    KS.doc_theo_ngay(["1"], a, b, cds=["c"])
    KS.doc_tong_tien_te(["1"], a, b)
    cau = [s for s, _ in g.cau if "statement_timeout" not in s]
    assert all("AS click_lk" in s for s in cau), cau
    assert "left(q.advertiser_id, 4)" in cau[2]
    for s, ts in g.cau:
        assert s.count("%s") == len(ts or ()), s


# ───────────────────────────── 10. schema + delta + BigQuery ─────────────────────────────
def _schema():
    return (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")


def _delta():
    return (GOC / "deploy" / "lang-nghe" / "2026-10-28-qc-luu-luong.sql").read_text(encoding="utf-8")


def _khoi_moi(sql: str) -> str:
    return re.search(r"CREATE TABLE IF NOT EXISTS qc_so_thich \(.*?END \$sth\$;\n", sql,
                     re.DOTALL).group(0)


def test_schema_va_delta_cung_khoi():
    sql, dl = _schema(), _delta()
    assert sql.count("\\connect") == 1 and "\\connect" not in dl and "\\c " not in dl
    k = _khoi_moi(sql)
    assert k == _khoi_moi(dl)
    # CHECK mới: đúng QC.CHIEU_TAT_CA, NOT VALID, tìm CHECK cũ theo định nghĩa (tên tự sinh).
    ds = re.search(r"\$c\$(.*?)\$c\$", k).group(1)
    assert tuple(re.findall(r"'(\w+)'", ds)) == QC.CHIEU_TAT_CA
    assert "NOT VALID" in k and "ten := b || '_chieu_check';" in k
    assert "LIKE '%interest_category%'" in k and "DROP CONSTRAINT IF EXISTS %I', b, ten" in k
    # Tên lạ: chỉ để phát hiện → RAISE (không xoá); không DROP nào theo LIKE.
    lien = k[k.index("conname <> ten"):k.index("END IF;", k.index("conname <> ten"))]
    assert "RAISE EXCEPTION" in lien and "DROP" not in lien
    assert k.count("DROP CONSTRAINT") == 1
    # ADD COLUMN chỉ khi information_schema chưa có cột (chạy lại không xin ACCESS EXCLUSIVE).
    assert "ADD COLUMN IF NOT EXISTS khan_gia_bo_chieu" not in k
    assert "FROM information_schema.columns WHERE table_schema = 'public'" in k
    assert "ADD COLUMN %I SMALLINT" in k
    for b in ("qc_khan_gia", "qc_khan_gia_cd"):
        v = f"ALTER TABLE {b} VALIDATE CONSTRAINT {b}_chieu_check;"
        assert v in sql and v in dl
    # tk_quang_cao: hai cột (CREATE cho DB mới + ALTER cho DB đang chạy).
    tk = re.search(r"CREATE TABLE IF NOT EXISTS tk_quang_cao \((.*?)\n\);", sql, re.DOTALL).group(1)
    for c in ("khan_gia_bo_chieu", "khan_gia_cd_bo_chieu"):
        assert re.search(rf"^\s{{2}}{c}\s+SMALLINT,$", tk, re.MULTILINE), c
        assert f"'{c}'" in k
        assert re.search(rf"COMMENT ON COLUMN tk_quang_cao\.{c} IS '.{{40,}}';", sql)
    # Bảng tên: tạo khi đang là chủ bảng, trước GRANT SELECT ON ALL TABLES; web thêm/sửa (không
    # xoá), Mark chỉ đọc.
    assert sql.index("SET ROLE lang_nghe_chu;") < sql.index(k) < sql.index("RESET ROLE;")
    assert sql.index(k) < sql.index("GRANT SELECT ON ALL TABLES IN SCHEMA public TO lang_nghe_web")
    assert "GRANT INSERT, UPDATE ON qc_so_thich TO lang_nghe_web;" in sql
    assert "GRANT SELECT ON qc_so_thich TO mark;" in sql
    assert not re.search(r"GRANT[^;]*DELETE[^;]*qc_so_thich", sql + dl)
    assert not re.search(r"GRANT[^;]*(INSERT|UPDATE)[^;]*qc_so_thich[^;]*TO mark", sql + dl)
    # Hàm trigger Sheet trong delta = bản của schema.sql.
    ham = re.search(r"CREATE OR REPLACE FUNCTION chuan_yeu_cau_sheet_qc\(\).*?END \$fn\$;\n", sql,
                    re.DOTALL).group(0)
    assert ham in dl and "'cpc', 'lpv'" in ham
    # Mô tả 11 nhãn của bảng mới + mô tả mới của chiều sở thích có ở cả hai file.
    mo = re.search(r"COMMENT ON TABLE qc_so_thich IS \$\$(.*?)\$\$;", sql, re.DOTALL).group(1)
    assert [x.split("]", 1)[0] + "]" for x in mo.split("\n")] == [
        "[Lớp]", "[Mục đích]", "[Grain]", "[Khoá]", "[Nguồn]", "[Phạm vi]", "[Đã xử lý]",
        "[Refresh]", "[Dùng khi]", "[Không dùng khi]", "[Lưu ý]"]
    for c in ("phien_ban", "id", "ten", "cap", "cha", "cap_nhat_luc"):
        x = re.search(rf"COMMENT ON COLUMN qc_so_thich\.{c} IS '(?:[^']|'')+';\n", sql).group(0)
        assert x in dl, c
    for b in ("qc_khan_gia", "qc_khan_gia_cd"):
        for c in ("chieu", "gia_tri"):
            moi = [m.group(0) for m in re.finditer(
                rf"COMMENT ON COLUMN {b}\.{c} IS '(?:[^']|'')+';\n", sql)]
            assert "interest_category" in moi[-1] and moi[-1] in dl, (b, c)
        bang = [m.group(0) for m in re.finditer(rf"COMMENT ON TABLE {b} IS \$\$.*?\$\$;\n", sql,
                                                 re.DOTALL)]
        assert "sở thích" in bang[-1] and bang[-1] in dl, b


def test_delta_hai_giao_dich_va_khoa():
    dl = _delta()
    assert "to_regclass('public.tk_quang_cao') IS NULL" in dl and "RAISE EXCEPTION" in dl
    assert dl.index("RAISE EXCEPTION") < dl.index("BEGIN;")
    assert dl.count("BEGIN;") == 2 and dl.count("COMMIT;") == 2
    assert dl.count("SET LOCAL lock_timeout = '5s';") == 2
    assert dl.count("SET LOCAL ROLE lang_nghe_chu;") == 2 and dl.count("RESET ROLE;") == 2
    i = [dl.index(x) for x in ("BEGIN;", "SET LOCAL ROLE lang_nghe_chu;", _khoi_moi(dl),
                               "CREATE OR REPLACE FUNCTION chuan_yeu_cau_sheet_qc",
                               "COMMENT ON TABLE qc_so_thich", "RESET ROLE;",
                               "GRANT SELECT, INSERT, UPDATE ON qc_so_thich TO lang_nghe_web;",
                               "GRANT SELECT ON qc_so_thich TO mark;", "COMMIT;")]
    assert i == sorted(i)
    hai = dl[dl.index("COMMIT;") + 7:]
    assert "VALIDATE CONSTRAINT" in hai
    assert "VALIDATE CONSTRAINT" not in dl[dl.index("BEGIN;"):dl.index("COMMIT;")]
    for x in ("ACCESS EXCLUSIVE", "SHARE UPDATE EXCLUSIVE", "NOT VALID", "lock_timeout"):
        assert x in dl.split("\\set ON_ERROR_STOP on")[0], x
    assert "-d lang_nghe" in dl and "sudo -u postgres" in dl


def test_bigquery_bang_ten_va_cot_bo_chieu():
    b = DBQ.BANG["qc_so_thich"]
    assert b["khoa"] == ["phien_ban", "id"] and b["kieu"] == "tang_dan"
    assert DBQ.THU_TU[-1] == "qc_so_thich"
    cot = dict(DBQ.BANG["tk_quang_cao"]["cot"])
    assert cot["khan_gia_bo_chieu"] == cot["khan_gia_cd_bo_chieu"] == "INT64"
    assert {"khan_gia_bo_chieu", "khan_gia_cd_bo_chieu"} <= set(DBQ.BANG["tk_quang_cao"]["tuy_chon"])
    sql = (GOC / "deploy" / "lang-nghe" / "bigquery.sql").read_text(encoding="utf-8")
    for c in ("khan_gia_bo_chieu", "khan_gia_cd_bo_chieu"):
        assert re.search(rf"ALTER TABLE `[^`]+\.tk_quang_cao`\s+ADD COLUMN IF NOT EXISTS {c} INT64 "
                         r"OPTIONS\(description='.{40,}'\);", sql), c
    m = re.search(r"CREATE TABLE IF NOT EXISTS `[^`]+\.qc_so_thich`\s*\((.*?)\n\)\n(.*?)'''\);",
                  sql, re.DOTALL)
    dong = m.group(2).split("description='''", 1)[1].split("\n")
    assert [d.split("]", 1)[0] + "]" for d in dong] == [
        "[Lớp]", "[Mục đích]", "[Grain]", "[Khoá]", "[Nguồn]", "[Phạm vi]", "[Đã xử lý]",
        "[Refresh]", "[Dùng khi]", "[Không dùng khi]", "[Lưu ý]"]
    assert "dùng SOCIAL_LISTENING.qc_khan_gia" in dong[9]
    meta = sql.index("-- ───────────── Meta Ads (20/10/2026)")
    assert sql.index("qc_so_thich`") < meta
    # Cuối file: mô tả bảng + chieu + gia_tri của hai bảng khán giả có interest_category (11 nhãn).
    cuoi = sql[sql.rindex("-- Lưu lượng truy cập + sở thích TikTok (28/10/2026"):]
    for bang in ("qc_khan_gia", "qc_khan_gia_cd"):
        mt = re.search(rf"ALTER TABLE `[^`]+\.{bang}`\n  SET OPTIONS\(description='''(.*?)'''\);",
                       cuoi, re.DOTALL).group(1)
        assert len(mt.split("\n")) == 11 and "sở thích" in mt, bang
        for c in ("chieu", "gia_tri"):
            assert re.search(rf"ALTER TABLE `[^`]+\.{bang}`\n  ALTER COLUMN {c} SET OPTIONS\("
                             rf"description='[^\n]*interest_category[^\n]*'\);", cuoi), (bang, c)
    # Không tiền trong bảng tên.
    r = DBQ._bo_tien("qc_so_thich", {"phien_ban": 1, "id": "1", "ten": "A"})
    assert r == {"phien_ban": 1, "id": "1", "ten": "A"}


def test_kho_gia_khop_kho_that():
    """Kho giả có đủ hàm mới của kho_qc (tên giống nhau)."""
    for ten in ("so_thich_can_lam_moi", "ghi_so_thich", "ten_so_thich", "dat_khan_gia",
                "xong_khan_gia_cd", "qc_khan_gia", "qc_khan_gia_cd"):
        assert hasattr(KQ, ten) and hasattr(GiaKhoQC, ten), ten
    assert MM_2 in CHAY


# ───────────────────────────── 11. đợt soát 28/10/2026 ─────────────────────────────
def test_mark_cpc_ctr_theo_click_lien_ket(monkeypatch):
    import hoi_dashboard_tool as H
    k = {"chi": 100.0, "hien_thi": 1000, "click": 50, "click_lk": 20}
    cp = H._chi_phi_day_du(k)
    assert (cp["ctr"], cp["cpc"]) == (2.0, 5.0)
    assert H._chi_phi_day_du({"chi": 100.0, "hien_thi": 1000, "click": 50})["cpc"] == 2.0
    assert H._click_lien_ket(k) == {"chi": 100.0, "hien_thi": 1000, "click": 20}
    assert "click vào link" in H.GHI_CHU_QC and "inline_link_clicks" in H.GHI_CHU_QC
    # Kho: top / tra đối tượng / theo ngày của Mark có click_lk.
    tong, _ = KQ.sql_top("campaign", "chi")
    assert KQ._TONG_LL in tong and tong.count("%s") == 4
    g = _GhiSQL()
    monkeypatch.setattr(KQ, "ket_noi", g)
    a, b = datetime.date(2026, 10, 1), datetime.date(2026, 10, 2)
    KQ.qc_doi_tuong("chien_dich", ["1"], a, b, ["2"])
    KQ.qc_doi_tuong_ngay("chien_dich", ["1"], a, b, ["2"])
    assert all(KQ._TONG_LL in s for s, _ in g.cau)
    for s_, ts in g.cau:
        assert s_.count("%s") == len(ts or ()), s_


def test_mark_tong_quan_dung_click_lk():
    """Đường tổng quan của Mark (hoi_dashboard quang_cao): chi_phi.ctr / cpc theo click_lk."""
    import hoi_dashboard_tool as H
    h = _app_hai_nen_tang()
    kq = h.kho_qc
    ids = [a for a, t in kq.tk.items() if t.get("duyet", True)]
    a, b = datetime.date(2026, 10, 12), datetime.date(2026, 10, 18)
    k = QC.kpi(kq.qc_tong(ids, a, b))
    cp = H._chi_phi_day_du(k)
    assert cp["ctr"] == round(k["click_lk"] * 100 / k["hien_thi"], 2)
    assert k["click_lk"] < k["click"]


def test_cac_tk_khoan_dung_khi_chua_co_cot_moi(monkeypatch):
    g = _GhiSQL({"FROM tk_quang_cao": [{"advertiser_id": "1"}]})
    monkeypatch.setattr(KQ, "ket_noi", g)
    KQ.cac_tk()
    sql = g.cau[0][0]
    assert "FROM tk_quang_cao t " in sql
    for c in ("khan_gia_bo_chieu", "khan_gia_cd_bo_chieu"):
        assert f"(to_jsonb(t)->>'{c}')::smallint AS {c}" in sql
        assert f", {c}," not in sql


def test_cpc_tien_te_khac_vnd_hai_so_le():
    h = _app_hai_nen_tang()
    c, kq = h.c, h.kho_qc
    dang_nhap(c, QL)
    for t in kq.tk.values():
        t["tien_te"] = "USD"
    d = c.get(f"/api/qc?{Q}").json()
    assert d["tien_te"] == ["USD"]
    o = _o_ll(c.get(f"/quang-cao?{Q}").text)
    cpc = d["kpi"]["cpc"]
    assert o["cpc"] == A.so_thap(cpc, 2) + " USD" and "," in o["cpc"]
    t = c.get(f"/quang-cao?{Q}&sap=chi").text
    r0 = c.get(f"/api/qc?{Q}&sap=chi").json()["campaign"][0]
    assert f'data-nhan="CPC">{A.so_thap(round(r0["chi"] / r0["click_lk"], 2))}<' in t
    # VND: làm tròn đồng.
    for t_ in kq.tk.values():
        t_["tien_te"] = "VND"
    assert "," not in _o_ll(c.get(f"/quang-cao?{Q}").text)["cpc"]


def test_sheet_cot_lpv_moi_tab(monkeypatch):
    import xuat_sheet_qc as X
    ma = [m for m, _, _ in X._COT_SO]
    assert ma.index("lpv") == ma.index("cpc") + 1
    assert ("lpv", "Landing page view", "so_nguyen") in X._COT_SO
    assert "lpv" in [m for m, _, _ in X._cot(False, False)]          # không phải cột tiền
    g = _GhiSQL()
    monkeypatch.setattr(KS, "ket_noi", g)
    a, b = datetime.date(2026, 10, 1), datetime.date(2026, 10, 2)
    KS.doc_theo_ngay(["1"], a, b)
    KS.doc_theo_ngay(["1"], a, b, cds=["c"])
    KS.doc_tong_tien_te(["1"], a, b)
    cau = [s_ for s_, _ in g.cau if "statement_timeout" not in s_]
    assert all("AS lpv" in s_ for s_ in cau)
    assert "AS lpv" in KQ.sql_bang("campaign", "lpv", False, loc_ma=False, cd=False, bo_qua=False)


def test_luoi_o_kpi_hang_day():
    _app, c, _kq, _tt = _app_so_thich()
    t = c.get(f"/quang-cao?{Q}").text
    kpi = t.split('id="qc-kpi"')[1].split("</section>")[0]
    n = kpi.count('class="kpi kpi-o"')
    m = re.search(r'--so-kpi: (\d+); --kpi-cot: (\d+); --kpi-cot-hep: (\d+)', kpi)
    assert int(m.group(1)) == n and int(m.group(2)) == n == 6 and int(m.group(3)) == 3
    ll = t.split('data-o="luu-luong"')[1]
    m = re.search(r'--so-kpi: (\d+); --kpi-cot: (\d+); --kpi-cot-hep: (\d+)', ll)
    assert m.groups() == ("6", "6", "3")              # chỉ TikTok: không ô website Meta
    css = (GOC / "dashboard" / "static" / "qc.css").read_text(encoding="utf-8")
    assert "var(--kpi-cot," in css and "var(--kpi-cot-hep," in css
