"""Khán giả theo chiến dịch (26/10/2026, chủ dự án chốt): khối Khán giả của trang Quảng cáo theo Bộ
lọc đầu trang (cả tên chiến dịch) + ô chọn MỘT chiến dịch; bảng mới qc_khan_gia_cd (TikTok AUDIENCE
AUCTION_CAMPAIGN, Meta insights level=campaign), lệnh `khan-gia` đọc lại ngay, tên tỉnh TikTok
(GeoNames), schema + bản delta + BigQuery.

Không mạng: dùng lại máy chủ giả TikTok / Meta và kho giả của test_tiktok_ads /
test_meta_ads_dashboard (đã thêm nhánh khán giả cấp chiến dịch)."""
from __future__ import annotations

import datetime
import html
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from test_dashboard_app import QL, dang_nhap
from test_meta_ads_dashboard import CAMPAIGN, LA, MATE, NUOC_HOA, GiaMeta, _mdv, _nhap
from test_tiktok_ads import (
    BAY,
    HAPAS_KOC,
    LE,
    MM_2,
    MM_MKT,
    GiaTikTok,
    _co_so,
    _dv,
    _GhiSQL,
    _ket_noi_san,
    _tao_app,
)

from dashboard import dong_bo_bq as DBQ
from dashboard import kho_qc as KQ
from dashboard import meta_ads as MA
from dashboard import quang_cao as QC
from dashboard import tiktok_ads as TA
from dashboard import vung_tiktok as VT

GOC = Path(__file__).resolve().parents[1]
Q = "tu=2026-10-12&den=2026-10-18"
CUA_SO = (datetime.date(2026, 9, 19), datetime.date(2026, 10, 18))
CHAY = (HAPAS_KOC, MM_MKT, MM_2)                    # tài khoản TikTok giả có chạy (LE không)


def _ma_cd(adv: str, i: int) -> str:
    """Mã chiến dịch của máy chủ TikTok giả (chiến dịch i của tài khoản adv)."""
    return f"ca{adv[-4:]}{i:04d}"


def _audience(tt, cap: str | None = None) -> list[dict]:
    return [a for t, a in tt.cong_cu if t == "report_integrated_get"
            and a["report_type"] == "AUDIENCE" and (cap is None or a["data_level"] == cap)]


# ───────────────────────────── 1. đọc TikTok ─────────────────────────────
def test_tiktok_doc_khan_gia_cap_chien_dich_chi_chien_dich_co_chay():
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt)
    kq = dv.dong_bo()
    assert not kq["loi"], kq
    cd = kho_qc.bang["qc_khan_gia_cd"]
    # 3 tài khoản có chạy × 3 chiến dịch có hiển thị × 4 chiều × 2 giá trị; chiến dịch không chạy
    # (4 mã cuối của máy chủ giả) không bao giờ được xin.
    assert len(cd) == 3 * 3 * 4 * 2
    assert {(r["advertiser_id"], r["campaign_id"]) for r in cd.values()} == {
        (a, _ma_cd(a, i)) for a in CHAY for i in range(3)}
    assert {(r["tu"], r["den"]) for r in cd.values()} == {CUA_SO}
    for r in cd.values():
        assert r["chieu"] in QC.CHIEU_KHAN_GIA and r["gia_tri"]
        assert "campaign_id" not in r["chi_so"] and r["chieu"] not in r["chi_so"]
    # Lô ≤ 100 mã, đúng 4 chiều mỗi tài khoản, cùng cửa sổ 30 ngày với cấp tài khoản.
    cap_cd = _audience(tt, "AUCTION_CAMPAIGN")
    assert len(cap_cd) == 3 * 4
    assert all(a["dimensions"][0] == "campaign_id" and a["metrics"] == list(QC.CHI_SO_KHAN_GIA)
               and (a["start_date"], a["end_date"]) == ("2026-09-19", "2026-10-18")
               for a in cap_cd)
    assert sorted({x for _, _, ids in tt.kg_cd for x in ids}) == sorted(
        _ma_cd(a, i) for a in CHAY for i in range(3))
    # Cấp tài khoản vẫn ghi như cũ (Mark, Sheet, BigQuery đọc bảng này).
    assert len(kho_qc.bang["qc_khan_gia"]) == 4 * 2 * 3
    # Lần 2 cùng ngày: không đọc lại khán giả nào (mốc tuần của cả hai cấp).
    tt.cong_cu.clear()
    dv.dong_bo()
    assert not _audience(tt)


def test_tiktok_tuan_sau_doc_lai_chi_giu_cua_so_hoan_tat():
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt, het_rt=BAY + datetime.timedelta(days=60))
    dv.dong_bo()
    assert {kho_qc.tk[a]["khan_gia_cd_den"] for a in CHAY} == {CUA_SO[1]}
    assert kho_qc.tk[LE]["khan_gia_cd_den"] is None          # không chạy: không có cửa sổ
    dv2, _, _ = _dv(kho_qc, tt, bay=BAY + datetime.timedelta(days=7))
    tt.cong_cu.clear()
    dv2.dong_bo()
    assert _audience(tt, "AUCTION_CAMPAIGN") and _audience(tt, "AUCTION_ADVERTISER")
    moi = (datetime.date(2026, 9, 26), datetime.date(2026, 10, 25))
    # Hoàn tất cửa sổ mới → mốc dời, cửa sổ cũ bỏ (Postgres chỉ giữ cửa sổ hoàn tất mới nhất).
    assert {(r["tu"], r["den"]) for r in kho_qc.bang["qc_khan_gia_cd"].values()} == {moi}
    assert {kho_qc.tk[a]["khan_gia_cd_den"] for a in CHAY} == {moi[1]}


def test_tiktok_lo_100_ma_chia_lo(monkeypatch):
    dv, _kho, tt = _dv()
    _ket_noi_san(dv, tt)
    dv.dong_bo()
    tt.kg_cd.clear()
    monkeypatch.setattr(TA, "LO_ID", 2)
    kq = dv.doc_khan_gia([HAPAS_KOC])
    assert kq == {"so_dong": 4 * 2 + 3 * 4 * 2, "so_tk": 1, "loi": None}
    # 3 chiến dịch, lô 2 → [2, 1] cho mỗi chiều; hiển thị nhiều trước.
    assert [len(ids) for _, _, ids in tt.kg_cd] == [2, 1] * 4
    assert tt.kg_cd[0][2] == (_ma_cd(HAPAS_KOC, 0), _ma_cd(HAPAS_KOC, 1))


class _TikTokTinhLoi(GiaTikTok):
    """Báo cáo AUDIENCE cấp chiến dịch hỏng ở chiều tỉnh (sau khi tuổi, giới tính đã ghi): `loi`
    = "ma" → TikTok trả mã lỗi; "giet" → tiến trình bị giết (SIGTERM / OOM: không chạy được dọn
    dẹp nào); None → bình thường. `doi` (tuỳ chọn): đổi số của lần đọc sau."""

    loi: str | None = "ma"

    def _bao_cao(self, a):
        if (self.loi and a["report_type"] == "AUDIENCE" and a["data_level"] == "AUCTION_CAMPAIGN"
                and a["dimensions"][1] == "province_id"):
            if self.loi == "giet":
                raise SystemExit(143)
            return {"code": 40002, "message": "Invalid dimension combination"}
        return super()._bao_cao(a)


def _api_kg(kho_qc, ids):
    """Như trang đọc: cửa sổ cấp chiến dịch nhìn thấy được của các tài khoản."""
    return kho_qc.ds_cd_khan_gia(ids)


def test_m1_cua_so_do_dang_vo_hinh_va_doc_lai_hom_sau():
    tt = _TikTokTinhLoi()
    nk: list[str] = []
    dv, kho_qc, tt = _dv(tt=tt)
    dv.log = nk.append
    _ket_noi_san(dv, tt)
    kq = dv.dong_bo()
    # Phần phụ: lượt số không lỗi, cấp tài khoản đủ; dòng tuổi / giới tính đã ghi nhưng mốc KHÔNG
    # dời → trang không thấy (cửa sổ thiếu tỉnh, thiết bị không bao giờ lộ), tài khoản "chưa có".
    assert not kq["loi"] and len(kho_qc.bang["qc_khan_gia"]) == 4 * 2 * 3
    # LE không có chiến dịch chạy: xử lý xong (không cửa sổ); 3 tài khoản lỗi.
    assert kq["khan_gia_cd"] == {"xong": 1, "con": 0, "loi": 3}
    assert kho_qc.bang["qc_khan_gia_cd"]
    assert {r["chieu"] for r in kho_qc.bang["qc_khan_gia_cd"].values()} == {"age", "gender"}
    assert all(kho_qc.tk[a]["khan_gia_cd_den"] is None for a in CHAY)
    v = _api_kg(kho_qc, list(CHAY))
    assert v["ds"] == [] and v["tk_thieu"] == sorted(CHAY)
    # Mỗi lỗi một dòng nhật ký (không chỉ lỗi đầu).
    assert sum("khán giả theo chiến dịch" in x and "40002" in x for x in nk) == 3
    # Tới hạn lại ngay: hôm sau đọc lại cấp chiến dịch (cấp tài khoản đã có trong tuần).
    tt.loi = None
    tt.cong_cu.clear()
    dv2, _, _ = _dv(kho_qc, tt, bay=BAY + datetime.timedelta(days=1))
    dv2.dong_bo()
    assert _audience(tt, "AUCTION_CAMPAIGN") and not _audience(tt, "AUCTION_ADVERTISER")
    # Hoàn tất: chỉ còn cửa sổ mới, đủ 4 chiều; dòng dở dang hôm trước bị bỏ.
    moi = datetime.date(2026, 10, 19)
    assert {r["den"] for r in kho_qc.bang["qc_khan_gia_cd"].values()} == {moi}
    assert len(kho_qc.bang["qc_khan_gia_cd"]) == 3 * 3 * 4 * 2
    assert len(_api_kg(kho_qc, list(CHAY))["ds"]) == 9
    # Lệnh khan-gia báo lỗi cấp chiến dịch trong kết quả (không chỉ nhật ký).
    tt.loi = "ma"
    kq = dv2.doc_khan_gia([HAPAS_KOC])
    assert "khán giả theo chiến dịch" in kq["loi"] and kq["so_tk"] == 1


def test_m1_bi_giet_giua_chung_khong_lo_cua_so_thieu():
    tt = _TikTokTinhLoi()
    tt.loi = "giet"
    dv, kho_qc, tt = _dv(tt=tt)
    _ket_noi_san(dv, tt)
    with pytest.raises(SystemExit):
        dv.dong_bo()                            # SIGTERM / OOM: không chạy được dọn dẹp nào
    # Số hằng ngày của MỌI tài khoản đã ghi trước khi phần khán giả cấp chiến dịch bắt đầu.
    assert {r["advertiser_id"] for r in kho_qc.bang["qc_tk_ngay"].values()} == set(CHAY)
    # Dòng dở dang còn trong bảng nhưng vô hình (không mốc): trang, BigQuery, hạn đọc lại.
    assert kho_qc.bang["qc_khan_gia_cd"]
    assert _api_kg(kho_qc, list(CHAY))["ds"] == []
    t = kho_qc.tk[HAPAS_KOC]
    assert TA.khan_gia_cd_den_han(t, CUA_SO[1])
    tt.loi = None
    dv2, _, _ = _dv(kho_qc, tt, bay=BAY + datetime.timedelta(hours=2))
    dv2.dong_bo()
    assert len(_api_kg(kho_qc, list(CHAY))["ds"]) == 9
    assert {r["chieu"] for r in kho_qc.bang["qc_khan_gia_cd"].values()} == set(QC.CHIEU_KHAN_GIA)


def test_m2_doc_lai_cung_ngay_loi_giu_cua_so_cu():
    tt = _TikTokTinhLoi()
    tt.loi = None
    dv, kho_qc, tt = _dv(tt=tt)
    _ket_noi_san(dv, tt)
    dv.dong_bo()
    truoc = {k: dict(r) for k, r in kho_qc.bang["qc_khan_gia_cd"].items()
             if r["advertiser_id"] == HAPAS_KOC}
    assert len(truoc) == 3 * 4 * 2
    # Lệnh khan-gia cùng ngày (cùng cửa sổ) lỗi ở chiều tỉnh: cửa sổ cũ vẫn đủ, vẫn nhìn thấy.
    tt.loi = "ma"
    kq = dv.doc_khan_gia([HAPAS_KOC])
    assert "40002" in kq["loi"]
    sau = {k: r for k, r in kho_qc.bang["qc_khan_gia_cd"].items()
           if r["advertiser_id"] == HAPAS_KOC}
    assert set(sau) == set(truoc) and kho_qc.tk[HAPAS_KOC]["khan_gia_cd_den"] == CUA_SO[1]
    assert {r["chieu"] for r in sau.values()} == set(QC.CHIEU_KHAN_GIA)
    assert len([x for x in _api_kg(kho_qc, [HAPAS_KOC])["ds"]]) == 3
    # Đọc lại thành công: giá trị TikTok không còn trả bị bỏ, cap_nhat_luc mới hơn mọi lần ghi.
    tt.loi = None
    k_cu = next(iter(sau))
    kho_qc.bang["qc_khan_gia_cd"][k_cu[:-1] + ("GIA_TRI_CU",)] = {
        **sau[k_cu], "gia_tri": "GIA_TRI_CU", "cap_nhat_luc": 0}
    dv.doc_khan_gia([HAPAS_KOC])
    cua = [r for r in kho_qc.bang["qc_khan_gia_cd"].values() if r["advertiser_id"] == HAPAS_KOC]
    assert len(cua) == 3 * 4 * 2 and "GIA_TRI_CU" not in {r["gia_tri"] for r in cua}
    assert len({r["cap_nhat_luc"] for r in cua}) == 1


def test_m3_so_moi_tai_khoan_truoc_roi_moi_khan_gia_cap_chien_dich():
    dv, _kho, tt = _dv()
    _ket_noi_san(dv, tt)
    dv.dong_bo()
    bc = [(i, a) for i, (t, a) in enumerate(tt.cong_cu) if t == "report_integrated_get"]
    cuoi_so = max(i for i, a in bc if a["report_type"] == "BASIC")
    dau_cd = min(i for i, a in bc if a["data_level"] == "AUCTION_CAMPAIGN"
                 and a["report_type"] == "AUDIENCE")
    assert cuoi_so < dau_cd


def test_m3_tran_thoi_gian_dung_va_doc_tiep_luot_sau():
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt)
    # Đồng hồ giả: thời gian chỉ trôi khi kho ghi khán giả cấp chiến dịch (6 lần ghi mỗi tài khoản
    # có chiến dịch = 1.500 giây > trần 20 phút) — tài khoản đầu xong thì hết giờ.
    dv.dong_ho = lambda: getattr(kho_qc, "_tick", 0) * 250
    assert TA.TRAN_GIAY_KHAN_GIA_CD == 20 * 60
    thu_tu = sorted(CHAY)
    kq = dv.dong_bo()
    # LE (không chiến dịch, mốc trống, mã nhỏ nhất) + tài khoản đầu xong; hai tài khoản để lượt
    # sau — số hằng ngày vẫn đủ, lượt không lỗi.
    assert kq["khan_gia_cd"] == {"xong": 2, "con": 2, "loi": 0} and not kq["loi"]
    assert {a for a in CHAY if kho_qc.tk[a]["khan_gia_cd_den"]} == {thu_tu[0]}
    assert {r["advertiser_id"] for r in kho_qc.bang["qc_tk_ngay"].values()} == set(CHAY)
    # Lượt sau (cùng ngày): chỉ tài khoản còn tới hạn — đọc tiếp, không làm lại tài khoản đã xong.
    for n in (1, 2):
        tt.kg_cd.clear()
        kq = dv.dong_bo()
        assert kq["khan_gia_cd"] == {"xong": 2, "con": 2 - n, "loi": 0}
        assert {x[0] for x in tt.kg_cd} == {thu_tu[n]}
    assert all(kho_qc.tk[a]["khan_gia_cd_den"] == CUA_SO[1] for a in CHAY)
    # Lệnh khan-gia không giới hạn thời gian: mọi tài khoản trong một lần.
    tt.kg_cd.clear()
    assert dv.doc_khan_gia()["loi"] is None
    assert {x[0] for x in tt.kg_cd} == set(CHAY)


def test_tiktok_kho_loi_van_doc_cap_tai_khoan():
    nk: list[str] = []
    dv, kho_qc, tt = _dv()
    dv.log = nk.append

    def chua_co(*_a):
        raise KQ.LoiKho("relation qc_khan_gia_cd does not exist")
    kho_qc.cd_co_chay = chua_co
    _ket_noi_san(dv, tt)
    kq = dv.dong_bo()
    # Mỗi tài khoản (cả LE) lỗi riêng, mỗi lỗi một dòng nhật ký; lượt số không lỗi.
    assert not kq["loi"] and kq["khan_gia_cd"]["loi"] == 4
    assert len(kho_qc.bang["qc_khan_gia"]) == 4 * 2 * 3 and not _audience(tt, "AUCTION_CAMPAIGN")
    assert sum("LoiKho" in x for x in nk) == 4


class _BQ:
    def __init__(self):
        self.so = 0

    def da_bat(self):
        return True

    def chay(self):
        self.so += 1
        return {"bang": []}


def test_cli_khan_gia_tiktok_doc_lai_ngay(capsys):
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt)
    dv.dong_bo()
    capsys.readouterr()
    tt.cong_cu.clear()
    bq = _BQ()
    # Mốc tuần còn mới nhưng lệnh khan-gia bỏ qua mốc: cả hai cấp, mọi tài khoản đang đồng bộ.
    assert TA.main(["khan-gia"], dich_vu=dv, dong_bo_bq=bq) == 0
    out = capsys.readouterr().out
    kq = json.loads(out.split("[tiktok_ads] ", 1)[1].splitlines()[0])
    assert kq["so_tk"] == 4 and kq["loi"] is None and kq["so_dong"] == 3 * (8 + 24)
    assert {a["advertiser_id"] for a in _audience(tt, "AUCTION_CAMPAIGN")} == set(CHAY)
    assert bq.so == 1 and tt.access not in out
    # Không đụng cờ / mốc lượt của thẻ kết nối, không khám phá lại tài khoản.
    assert not any(t == "auth_advertiser_get" for t, _ in tt.cong_cu)
    # --tk: chỉ tài khoản đó; --khong-bq.
    tt.cong_cu.clear()
    assert TA.main(["khan-gia", "--tk", MM_2, "--khong-bq"], dich_vu=dv, dong_bo_bq=bq) == 0
    assert {a["advertiser_id"] for a in _audience(tt)} == {MM_2} and bq.so == 1
    # Lượt khác giữ khoá quá thời gian chờ → thoát 3.
    kho_qc.dang_khoa.add(KQ.KHOA_DONG_BO)
    assert TA.main(["khan-gia", "--cho-khoa-phut", "1"], dich_vu=dv, dong_bo_bq=bq) == 3
    kho_qc.dang_khoa.clear()


def test_cli_vung_chua_ten(capsys):
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt)
    dv.dong_bo()
    r = next(iter(kho_qc.bang["qc_khan_gia"].values()))
    kho_qc.bang["qc_khan_gia"][("x",)] = {**r, "chieu": "province_id", "gia_tri": "9999999",
                                          "hien_thi": 5}
    capsys.readouterr()
    assert TA.main(["vung-chua-ten"], dich_vu=dv) == 0
    kq = json.loads(capsys.readouterr().out)
    # 1581129 (Hà Nội) có tên, -1 = không rõ — chỉ mã lạ được liệt kê.
    assert kq["chua_ten"] == [{"gia_tri": "9999999", "hien_thi": 5}] and kq["so_chua_ten"] == 1


# ───────────────────────────── 2. đọc Meta ─────────────────────────────
def test_meta_doc_khan_gia_cap_chien_dich():
    dv, kho_qc, gm = _mdv()
    _nhap(dv)
    assert not dv.dong_bo()["loi"]
    cd = kho_qc.bang["qc_khan_gia_cd"]
    co = {(r["advertiser_id"], r["campaign_id"]) for r in cd.values()}
    assert co == {(a, cid) for a, ds in CAMPAIGN.items() if a != LA for cid, _ in ds
                  if a in dv.kho.tk and dv.kho.tk[a].get("duyet")}
    assert {r["chieu"] for r in cd.values()} == {c for c, _ in MA.CHIEU_META}
    r = next(r for r in cd.values() if r["campaign_id"] == "120201" and r["chieu"] == "age"
             and r["gia_tri"] == "AGE_18_24")
    assert r["advertiser_id"] == NUOC_HOA and r["reach"] is not None and r["hien_thi"] == 100
    assert "campaign_id" not in r["chi_so"]
    # Lọc campaign.id IN đúng các chiến dịch có hiển thị trong cửa sổ (từ kho), breakdowns như cấp
    # tài khoản; một lượt mỗi chiều mỗi tài khoản (≤ 50 mã).
    nh = [x for x in gm.kg_cd if x[0] == NUOC_HOA]
    assert sorted(x[1] for x in nh) == sorted(",".join(b) for _, b in MA.CHIEU_META)
    assert all(set(x[2]) == {"120201", "120202"} for x in nh)
    # Soát M3: số (insights không breakdowns) của MỌI tài khoản trước lượt khán giả cấp chiến dịch.
    q = [{k: v[0] for k, v in parse_qs(urlsplit(str(r.url)).query).items()} for r in gm.goi
         if "/insights" in str(r.url)]
    cuoi_so = max(i for i, x in enumerate(q) if not x.get("breakdowns"))
    dau_cd = min(i for i, x in enumerate(q) if x.get("breakdowns") and x["level"] == "campaign")
    assert cuoi_so < dau_cd
    assert {k: kho_qc.tk[k]["khan_gia_cd_den"] for k, _ in co} == {
        k: datetime.date(2026, 10, 18) for k, _ in co}
    # Lần 2: không đọc lại.
    gm.kg_cd.clear()
    dv.dong_bo()
    assert not gm.kg_cd


class _MetaNang(GiaMeta):
    """Khán giả cấp chiến dịch: lô > 1 chiến dịch → Meta "quá nhiều dữ liệu" (mã 1)."""

    def xu_ly(self, req):
        q = {k: v[0] for k, v in parse_qs(urlsplit(str(req.url)).query).items()}
        if (q.get("level") == "campaign" and q.get("breakdowns") and q.get("filtering")
                and len(json.loads(q["filtering"])[0]["value"]) > 1):
            self.goi.append(req)
            return httpx.Response(400, json={"error": {"code": 1, "message": "too much"}})
        return super().xu_ly(req)


def test_meta_qua_nang_chia_doi_lo_va_cli():
    dv, kho_qc, gm = _mdv(gm=_MetaNang())
    _nhap(dv)
    assert not dv.dong_bo()["loi"]
    # NUOC_HOA có 2 chiến dịch: lô 2 bị từ chối → đọc từng chiến dịch, đủ số.
    assert {x[2] for x in gm.kg_cd if x[0] == NUOC_HOA} == {("120201",), ("120202",)}
    assert {r["campaign_id"] for r in kho_qc.bang["qc_khan_gia_cd"].values()
            if r["advertiser_id"] == NUOC_HOA} == {"120201", "120202"}
    gm.kg_cd.clear()
    assert MA.main(["khan-gia", "--tk", NUOC_HOA, "--khong-bq"], dich_vu=dv) == 0
    assert {x[0] for x in gm.kg_cd} == {NUOC_HOA}


def test_meta_gop_ma_trung_theo_tung_chien_dich():
    a, b = datetime.date(2026, 9, 19), datetime.date(2026, 10, 18)
    rows = [MA.dong_khan_gia_cd({"campaign_id": c, "age": g, "spend": "10", "impressions": str(n),
                                 "reach": "5"}, NUOC_HOA, a, b, "age")
            for c in ("1", "2") for g, n in (("Unknown", 3), ("unknown", 4))]
    gop = {(x["campaign_id"], x["gia_tri"]): x for x in MA.gop_khan_gia_cd(rows)}
    assert set(gop) == {("1", "NONE"), ("2", "NONE")}
    assert gop[("1", "NONE")]["hien_thi"] == 7 and gop[("1", "NONE")]["reach"] is None


# ───────────────────────────── 3. trang + API ─────────────────────────────
def _app_co_so():
    app, c, _kho, kq, _tt, _dv_tt = _co_so(_tao_app())
    dang_nhap(c, QL)
    return app, c, kq


def _u(**kw) -> str:
    return f"/quang-cao?{Q}&{urlencode(kw, doseq=True)}" if kw else f"/quang-cao?{Q}"


def _api(c, **kw):
    return c.get(f"/api/qc?{Q}&{urlencode(kw, doseq=True)}").json()


def _khoi(t: str) -> str:
    return t.split('id="qc-kg-tieu-de"')[1].split("</section>")[0]


def _dat_ten(kq, ten: dict[str, str]):
    for (cid, _ng), r in kq.bang["qc_campaign_ngay"].items():
        if cid in ten:
            r["ten"] = ten[cid]


def _hien_thi(kq, cds, chieu="gender"):
    return sum(r["hien_thi"] for r in kq.bang["qc_khan_gia_cd"].values()
               if r["campaign_id"] in cds and r["chieu"] == chieu)


def test_trang_mac_dinh_theo_tai_khoan_co_o_chon_chien_dich():
    _app, c, kq = _app_co_so()
    t = c.get(_u()).text
    k = _khoi(t)
    assert "(số theo tài khoản)" in k and not getattr(kq, "goi_kg_cd", None)
    # Tên tỉnh thay vì mã vùng.
    assert "Hà Nội" in k and "Mã vùng" not in k
    f = k.split('data-o="chon-cd-kg"')[1].split("</form>")[0]
    assert 'action="/quang-cao#khan-gia"' in t.split('data-o="chon-cd-kg"')[0][-200:]
    ma = re.findall(r'<option value="([^"]*)"', f)
    assert ma[0] == "" and sorted(ma[1:]) == sorted(_ma_cd(a, i) for a in CHAY for i in range(3))
    assert ">Mọi chiến dịch (theo tài khoản)</option>" in f and " · TikTok</option>" in f
    an = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', f))
    assert an["tu"] == "2026-10-12" and an["den"] == "2026-10-18" and "kg_cd" not in an
    assert "data-kg-xem>Xem</button>" in f and 'id="khan-gia"' in t
    d = _api(c)
    assert d["khan_gia_cd"]["che_do"] == "tai_khoan" and d["khan_gia_cd"]["chon"] == ""
    assert len(d["khan_gia_cd"]["ds"]) == 9


def test_chon_mot_chien_dich_va_lien_ket_giu_lua_chon():
    _app, c, kq = _app_co_so()
    ma = _ma_cd(MM_MKT, 1)
    _dat_ten(kq, {ma: "MM Teaser 10.10"})
    d = _api(c, kg_cd=ma)
    kc = d["khan_gia_cd"]
    assert (kc["che_do"], kc["chon"], kc["so_cd"], kc["chon_ten"], kc["chon_nen_tang"]) == (
        "chien_dich", ma, 1, "MM Teaser 10.10", "tiktok")
    assert kq.goi_kg_cd[-1][1] == (ma,)
    tong = sum(x["hien_thi"] for x in d["khan_gia"]["gender"])
    assert tong == _hien_thi(kq, {ma}) > 0
    t = c.get(_u(kg_cd=ma)).text
    k = _khoi(t)
    assert "Số của chiến dịch <b>MM Teaser 10.10</b> (TikTok)." in k
    assert f'<option value="{ma}" selected>MM Teaser 10.10 · TikTok</option>' in k
    # Liên kết của trang (khoảng nhanh) giữ kg_cd; tab nền tảng bỏ (chiến dịch thuộc nền tảng).
    nhanh = [html.unescape(h) for h in re.findall(
        r'href="([^"]+)"', t.split('aria-label="Khoảng nhanh"')[1].split("</nav>")[0])]
    assert nhanh and all(parse_qs(urlsplit(h).query)["kg_cd"] == [ma] for h in nhanh)
    # Mã lạ / ngoài phạm vi → mặc định (theo tài khoản), không lỗi.
    for la in ("ca99990000", "x'; DROP", ""):
        assert _api(c, kg_cd=la)["khan_gia_cd"]["che_do"] == "tai_khoan", la


def test_loc_ten_chien_dich_chi_cong_chien_dich_khop():
    _app, c, kq = _app_co_so()
    a, b, x = _ma_cd(HAPAS_KOC, 0), _ma_cd(MM_MKT, 2), _ma_cd(MM_2, 1)
    _dat_ten(kq, {a: "Teaser Nước Hoa", b: "TEASER mm", x: "Sale 11.11"})
    d = _api(c, cd_mot="teaser")
    kc = d["khan_gia_cd"]
    assert kc["che_do"] == "chien_dich" and kc["so_cd"] == 2 and kc["chon"] == ""
    assert set(kq.goi_kg_cd[-1][1]) == {a, b}
    assert {y["campaign_id"] for y in kc["ds"]} == {a, b}
    assert sum(y["hien_thi"] for y in d["khan_gia"]["gender"]) == _hien_thi(kq, {a, b})
    t = c.get(_u(cd_mot="teaser")).text
    k = _khoi(t)
    assert "<b>2 chiến dịch</b> có tên khớp lọc (" in k
    assert ">Mọi chiến dịch khớp lọc tên (2)</option>" in k
    # Ô ẩn của biểu mẫu mang lại lọc tên.
    assert '<input type="hidden" name="cd_mot" value="teaser">' in k
    # Chọn chiến dịch KHÔNG khớp lọc → lờ, vẫn cộng 2 chiến dịch khớp.
    assert _api(c, cd_mot="teaser", kg_cd=x)["khan_gia_cd"]["so_cd"] == 2
    # Chọn một trong hai → đúng chiến dịch đó.
    assert _api(c, cd_mot="teaser", kg_cd=b)["khan_gia_cd"]["so_cd"] == 1
    # Không chiến dịch nào khớp → API rỗng (trang hiện khối "không khớp" chung của lọc tên).
    d = _api(c, cd_mot="khongcoten")
    assert d["khan_gia_cd"]["so_cd"] == 0 and not any(d["khan_gia"].values())
    # Chiến dịch khớp trong kỳ nhưng CHƯA có số khán giả cấp chiến dịch (chiến dịch mới, chưa tới
    # lượt đọc tuần) → khối Khán giả nói rõ, không lùi về số cả tài khoản.
    bang = kq.bang["qc_khan_gia_cd"]
    for k in [k for k, r in bang.items() if r["campaign_id"] in (a, b)]:
        del bang[k]
    t = c.get(_u(cd_mot="teaser")).text
    k = _khoi(t)
    assert "Không chiến dịch nào có tên khớp lọc có số khán giả" in k and "qc-thanh" not in k


def test_reach_khong_cong_qua_nhieu_chien_dich():
    _app, c, kq = _app_co_so()
    for r in kq.bang["qc_khan_gia_cd"].values():
        r["reach"] = 10
    a, b = _ma_cd(HAPAS_KOC, 0), _ma_cd(HAPAS_KOC, 1)
    _dat_ten(kq, {a: "Teaser A", b: "Teaser B"})
    hai = _api(c, cd_mot="teaser")["khan_gia"]["gender"]
    assert hai and all(y["reach"] is None for y in hai)
    mot = _api(c, cd_mot="teaser", kg_cd=a)["khan_gia"]["gender"]
    assert mot and all(y["reach"] == 10 for y in mot)


def test_tai_khoan_chua_co_so_theo_chien_dich_duoc_neu_ten():
    _app, c, kq = _app_co_so()
    kq.tk[MM_2]["khan_gia_cd_den"] = None              # chưa có cửa sổ hoàn tất
    a = _ma_cd(HAPAS_KOC, 0)
    _dat_ten(kq, {a: "Teaser A"})
    d = _api(c, cd_mot="teaser")
    assert d["khan_gia_cd"]["tk_thieu"] == ["mate made 2"]
    assert all(x["campaign_id"] != _ma_cd(MM_2, 0) for x in _api(c)["khan_gia_cd"]["ds"])
    assert "1 tài khoản chưa có số theo chiến dịch (đọc mỗi tuần): mate made 2" in _khoi(
        c.get(_u(cd_mot="teaser")).text)


def test_dong_den_moi_hon_moc_khong_len_trang():
    """Soát M1: dòng của cửa sổ đang đọc / bỏ dở (den > mốc) không bao giờ vào số của trang."""
    _app, c, kq = _app_co_so()
    ma = _ma_cd(HAPAS_KOC, 0)
    truoc = sum(x["hien_thi"] for x in _api(c, kg_cd=ma)["khan_gia"]["gender"])
    mau = next(r for r in kq.bang["qc_khan_gia_cd"].values() if r["campaign_id"] == ma
               and r["chieu"] == "gender")
    den = CUA_SO[1] + datetime.timedelta(days=1)
    kq.bang["qc_khan_gia_cd"][("x",)] = {**mau, "den": den, "hien_thi": 10 ** 9}
    assert sum(x["hien_thi"] for x in _api(c, kg_cd=ma)["khan_gia"]["gender"]) == truoc
    assert _api(c)["khan_gia_cd"]["ds"] and len(_api(c)["khan_gia_cd"]["ds"]) == 9


def test_o_chon_giu_chien_dich_dang_chon_ngoai_tran(monkeypatch):
    """Soát L2: chiến dịch đang chọn nằm ngoài KG_CD_O_CHON dòng đầu vẫn hiện, vẫn được chọn."""
    _app, c, _kq = _app_co_so()
    monkeypatch.setattr(QC, "KG_CD_O_CHON", 2)
    ds = _api(c)["khan_gia_cd"]
    assert len(ds["ds"]) == 2 and ds["tong_ds"] == 9
    ngoai = next(x for x in (_ma_cd(a, i) for a in CHAY for i in range(3))
                 if x not in {y["campaign_id"] for y in ds["ds"]})
    d = _api(c, kg_cd=ngoai)["khan_gia_cd"]
    assert d["chon"] == ngoai and [x["campaign_id"] for x in d["ds"]][-1] == ngoai
    assert len(d["ds"]) == 3
    k = _khoi(c.get(_u(kg_cd=ngoai)).text)
    assert f'<option value="{ngoai}" selected>' in k and "Ô chọn hiện 3 / 9 chiến dịch" in k


def test_an_tien_dau_cuoi_qua_api(monkeypatch):
    """Người không xem tiền (`xem_tien` False): /api/qc không có khoá tiền ở khối Khán giả (ô chọn,
    các dòng), ô chọn xếp theo hiển thị. Trang /quang-cao hiện chỉ quản trị viên (luôn xem tiền) —
    bài thử ép `xem_tien` False để canh đường tiền đầu-cuối."""
    _app, c, _kq = _app_co_so()
    monkeypatch.setattr(QC, "xem_tien", lambda q, ben: False)
    d = _api(c, cd_mot="chien")
    assert d["xem_tien"] is False
    kc = d["khan_gia_cd"]
    assert kc["ds"] and all("chi" not in x for x in kc["ds"])
    hien = [x["hien_thi"] for x in kc["ds"]]
    assert hien == sorted(hien, reverse=True)
    assert all(not ({"chi", "gia_tri_mua_shop"} & set(x)) for ds in d["khan_gia"].values()
               for x in ds)
    t = c.get(_u()).text
    assert "chi nhiều" not in _khoi(t)


def test_ds_kg_cd_xep_theo_chi_hoac_hien_thi_va_loc_tien():
    ds = [{"campaign_id": "1", "ten": "Teaser", "chi": 10.0, "hien_thi": 900},
          {"campaign_id": "2", "ten": "Teaser 2", "chi": 50.0, "hien_thi": 100},
          {"campaign_id": "3", "ten": "Sale", "chi": 99.0, "hien_thi": 50}]
    khong = {"co_loc": False}
    assert [x["campaign_id"] for x in QC.ds_kg_cd(ds, khong, True)] == ["3", "2", "1"]
    assert [x["campaign_id"] for x in QC.ds_kg_cd(ds, khong, False)] == ["1", "2", "3"]
    loc = QC.loc_ten_cd({"cd_mot": "teaser"})
    assert [x["campaign_id"] for x in QC.ds_kg_cd(ds, loc, True)] == ["2", "1"]
    # Người không xem tiền: chi bị bỏ khỏi ô chọn (khoá tiền, đệ quy).
    ra = QC.loc_tien({"khan_gia_cd": {"ds": ds}}, False)
    assert all("chi" not in x and "hien_thi" in x for x in ra["khan_gia_cd"]["ds"])
    assert QC.doc_kg_cd({"kg_cd": " 123 "}) == "123" and QC.doc_kg_cd({"kg_cd": "a b"}) == ""


def test_nhan_tinh_tiktok():
    assert VT.ten_tinh("1581129") == "Hà Nội" and VT.ten_tinh(1581129) == "Hà Nội"
    assert VT.ten_tinh("13494358") == VT.ten_tinh("1580578") == "TP. Hồ Chí Minh"
    assert VT.ten_tinh("13494353") == VT.ten_tinh("1581088") == "Gia Lai"
    assert VT.ten_tinh("999") is None and VT.ten_tinh(None) is None
    # 34 tỉnh/thành sau 01/07/2025 + 54 mã cũ (GeoNames ADM1H) = 88 mã Việt Nam, đủ 63 tỉnh cũ theo
    # tên; + 6 mã ngoài Việt Nam gặp thật trong kho (soát 26/10/2026, GeoNames ADM1).
    assert len(VT.TEN_TINH) == 94 and len(set(VT.TEN_TINH.values())) == 71
    assert VT.NGOAI_VN <= set(VT.TEN_TINH)
    assert all("(" in VT.TEN_TINH[k] for k in VT.NGOAI_VN)
    assert not any("(" in v for k, v in VT.TEN_TINH.items() if k not in VT.NGOAI_VN)
    for ma, ten in (("1609348", "Bangkok (Thái Lan)"), ("1641897", "Đông Kalimantan (Indonesia)"),
                    ("1822449", "Ratanakiri (Campuchia)"),
                    ("1841597", "Gyeongsangbuk-do (Hàn Quốc)"), ("1853904", "Osaka (Nhật Bản)"),
                    ("1862047", "Hyōgo (Nhật Bản)")):
        assert QC.nhan_gia_tri("province_id", ma) == ten
    assert all(re.fullmatch(r"[0-9]{6,9}", k) for k in VT.TEN_TINH)
    assert QC.nhan_gia_tri("province_id", "1581129") == "Hà Nội"
    assert QC.nhan_gia_tri("province_id", "42") == "Mã vùng 42"
    assert QC.nhan_gia_tri("province_id", "-1") == "Không rõ"
    # Mã cũ + mã mới cùng tên → một dòng trên trang (cộng hiển thị).
    kg = QC.khan_gia([{"chieu": "province_id", "gia_tri": "1580578", "hien_thi": 3},
                      {"chieu": "province_id", "gia_tri": "13494358", "hien_thi": 4}])
    assert [(x["nhan"], x["hien_thi"]) for x in kg["province_id"]] == [("TP. Hồ Chí Minh", 7)]


# ───────────────────────────── 4. SQL của kho_qc ─────────────────────────────
class _GhiSQLXoa(_GhiSQL):
    rowcount = 0


def test_sql_khan_gia_cd(monkeypatch):
    luc = datetime.datetime(2026, 10, 19, 1, 0, tzinfo=datetime.UTC)
    g = _GhiSQLXoa({"FROM qc_campaign_ngay WHERE advertiser_id": [{"campaign_id": 7}],
                    "SELECT now()": [{"luc": luc}]})
    monkeypatch.setattr(KQ, "ket_noi", g)
    a, b = CUA_SO
    assert KQ.cd_co_chay(HAPAS_KOC, a, b, 1000) == ["7"]
    assert KQ.gio_kho() == luc
    KQ.xong_khan_gia_cd(HAPAS_KOC, b, luc)
    xong = g.cau[-3:]
    KQ.ds_cd_khan_gia([HAPAS_KOC])
    KQ.qc_khan_gia_cd([HAPAS_KOC], ["7"])
    KQ.gia_tri_khan_gia("province_id")
    for sql, ts in g.cau:
        assert sql.count("%s") == len(ts or ()), sql
    # Hoàn tất: MỘT kết nối (một giao dịch) — bỏ dòng khác cửa sổ / cũ hơn lượt, đặt lại
    # cap_nhat_luc, dời mốc; không xoá cửa sổ vừa hoàn tất.
    assert xong[0] == (("DELETE FROM qc_khan_gia_cd WHERE advertiser_id = %s "
                        "AND (den <> %s OR cap_nhat_luc < %s)"), (HAPAS_KOC, b, luc))
    assert xong[1][0].startswith("UPDATE qc_khan_gia_cd SET cap_nhat_luc = now()")
    assert xong[2] == ("UPDATE tk_quang_cao SET khan_gia_cd_den = %s WHERE advertiser_id = %s",
                       (b, HAPAS_KOC))
    doc = [s for s, _ in g.cau if not s.startswith(("DELETE", "UPDATE"))]
    assert not any(re.search(r"\b(INSERT|UPDATE|DELETE)\b", s) for s in doc)
    # Người đọc chỉ dùng cửa sổ = mốc hoàn tất; danh sách KHÔNG có LIMIT (soát L1).
    moi = ("WITH moi AS (SELECT advertiser_id, khan_gia_cd_den AS den FROM tk_quang_cao "
           "WHERE advertiser_id = ANY(%s) AND khan_gia_cd_den IS NOT NULL)")
    ds = next(s for s in doc if "LEFT JOIN LATERAL" in s)
    assert ds.startswith(moi) and "JOIN moi USING (advertiser_id, den)" in ds
    assert "LIMIT" not in ds.split("LEFT JOIN LATERAL")[1]
    tong = next(s for s in doc if "GROUP BY k.chieu, k.gia_tri" in s)
    assert tong.startswith(moi) and "k.campaign_id = ANY(%s)" in tong
    thieu = next(s for s in doc if "SELECT DISTINCT k.advertiser_id" in s)
    assert "t.khan_gia_cd_den IS NULL" in thieu
    # Không gọi DB khi không có tài khoản / chiến dịch.
    n = len(g.cau)
    assert KQ.qc_khan_gia_cd([HAPAS_KOC], []) == {"rows": [], "tu": None, "den": None}
    assert KQ.ds_cd_khan_gia([]) == {"ds": [], "tk_thieu": []} and len(g.cau) == n
    # Upsert theo khoá có campaign_id + tài khoản (không cần chốt WHERE advertiser_id).
    s = KQ.sql_upsert("qc_khan_gia_cd")
    assert "ON CONFLICT (advertiser_id, campaign_id, tu, den, chieu, gia_tri)" in s
    assert "WHERE" not in s
    assert "khan_gia_cd_den" in KQ._COT_TK


# ───────────────────────────── 5. schema + bản delta + BigQuery ─────────────────────────────
def _khoi_tao(sql: str) -> str:
    return re.search(r"CREATE TABLE IF NOT EXISTS qc_khan_gia_cd \(.*?\n\);\n"
                     r"CREATE INDEX IF NOT EXISTS qc_khan_gia_cd_moi[^\n]*\n"
                     r"CREATE INDEX IF NOT EXISTS qc_khan_gia_cd_cap_nhat[^\n]*\n"
                     r"ALTER TABLE tk_quang_cao ADD COLUMN IF NOT EXISTS khan_gia_cd_den DATE;\n",
                     sql, re.DOTALL).group(0)


def test_schema_bang_moi_quyen_va_ban_delta():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    assert sql.count("\\connect") == 1                       # không thêm \connect nào
    tao = _khoi_tao(sql)
    assert "PRIMARY KEY (advertiser_id, campaign_id, tu, den, chieu, gia_tri)" in tao
    assert "REFERENCES tk_quang_cao(advertiser_id)" in tao
    ck = re.search(r"chieu\s+TEXT NOT NULL CHECK \(chieu IN \((.*?)\)\)", tao, re.DOTALL).group(1)
    assert tuple(re.findall(r"'(\w+)'", ck)) == QC.CHIEU_TAT_CA
    # Mốc hoàn tất: cột tk_quang_cao (CREATE cho DB mới + ALTER cho DB đang chạy) có mô tả.
    tk = re.search(r"CREATE TABLE IF NOT EXISTS tk_quang_cao \((.*?)\n\);", sql, re.DOTALL).group(1)
    assert re.search(r"^\s{2}khan_gia_cd_den\s+DATE$", tk, re.MULTILINE)
    mo_cot = re.search(r"COMMENT ON COLUMN tk_quang_cao\.khan_gia_cd_den IS '[^']{20,}';\n", sql)
    assert mo_cot
    # Bảng tạo khi đang là chủ bảng (SET ROLE lang_nghe_chu … RESET ROLE), trước GRANT SELECT ON
    # ALL TABLES của web; quyền như qc_khan_gia + DELETE chỉ bảng này; Mark chỉ đọc.
    assert sql.index("SET ROLE lang_nghe_chu;") < sql.index(tao) < sql.index("RESET ROLE;")
    assert sql.index(tao) < sql.index("GRANT SELECT ON ALL TABLES IN SCHEMA public TO lang_nghe_web")
    assert "GRANT INSERT, UPDATE, DELETE ON qc_khan_gia_cd TO lang_nghe_web;" in sql
    assert "GRANT SELECT ON qc_khan_gia_cd TO mark;" in sql
    assert not re.search(r"GRANT[^;]*DELETE[^;]*ON[^;]*qc_(?!khan_gia_cd)", sql)
    assert not re.search(r"GRANT[^;]*(INSERT|UPDATE|DELETE)[^;]*qc_khan_gia_cd[^;]*TO mark", sql)
    # Bản delta (áp được trên DB CHƯA có bản đầu): đúng khối tạo + mốc + mô tả của schema.sql, không
    # đổi DB, chặn nhầm DB, một giao dịch, chú thích khoá đúng (soát L5).
    dl = (GOC / "deploy" / "lang-nghe" / "2026-10-26-khan-gia-cd.sql").read_text(encoding="utf-8")
    assert "\\connect" not in dl and "\\c " not in dl and _khoi_tao(dl) == tao
    mo_ta = re.search(r"COMMENT ON TABLE qc_khan_gia_cd IS .*?cap_nhat_luc IS '[^']*';\n", sql,
                      re.DOTALL).group(0)
    assert mo_ta in dl and mo_ta.count("COMMENT ON COLUMN qc_khan_gia_cd.") == 26
    assert mo_cot.group(0) in dl
    assert "SHARE ROW EXCLUSIVE" in dl and "ACCESS EXCLUSIVE" in dl
    assert "không khoá bảng nào khác" not in dl
    assert "to_regclass('public.tk_quang_cao') IS NULL" in dl and "RAISE EXCEPTION" in dl
    i = [dl.index(x) for x in ("BEGIN;", "SET LOCAL ROLE lang_nghe_chu;", tao, "RESET ROLE;",
                               ("GRANT SELECT, INSERT, UPDATE, DELETE ON qc_khan_gia_cd TO "
                                "lang_nghe_web;"), "GRANT SELECT ON qc_khan_gia_cd TO mark;",
                               "COMMIT;")]
    assert i == sorted(i)
    assert "-d lang_nghe" in dl and "sudo -u postgres" in dl


def test_bigquery_bang_moi_va_mo_ta_11_nhan(monkeypatch):
    b = DBQ.BANG["qc_khan_gia_cd"]
    assert tuple(b["khoa"]) == KQ.BANG_QC["qc_khan_gia_cd"][1] and b["kieu"] == "tang_dan"
    assert DBQ.THU_TU.index("qc_khan_gia") < DBQ.THU_TU.index("qc_khan_gia_cd")
    s = DBQ.sql_merge("qc_khan_gia_cd")
    assert "T.campaign_id = S.campaign_id" in s and "DELETE" not in s
    # Soát L4: chỉ đẩy dòng của cửa sổ đã hoàn tất (mọi lô — cả lô đầu lẫn lô sau).
    for co_moc in (False, True):
        for co_sau in (False, True):
            q = DBQ.sql_lo("qc_khan_gia_cd", co_moc, co_sau)
            assert ("qc_khan_gia_cd.den <= t.khan_gia_cd_den" in q
                    and "t.advertiser_id = qc_khan_gia_cd.advertiser_id" in q), q
    assert "khan_gia_cd_den" not in DBQ.sql_lo("qc_khan_gia", True, True)
    assert ("khan_gia_cd_den", "DATE") in DBQ.BANG["tk_quang_cao"]["cot"]
    sql = (GOC / "deploy" / "lang-nghe" / "bigquery.sql").read_text(encoding="utf-8")
    assert re.search(r"ALTER TABLE `[^`]+\.tk_quang_cao`\s+ADD COLUMN IF NOT EXISTS "
                     r"khan_gia_cd_den DATE OPTIONS\(description='.{20,}'\);", sql)
    m = re.search(r"CREATE TABLE IF NOT EXISTS `[^`]+\.qc_khan_gia_cd`\s*\((.*?)\n\)\n(.*?)'''\);",
                  sql, re.DOTALL)
    dong = m.group(2).split("description='''", 1)[1].split("\n")
    assert [d.split("]", 1)[0] + "]" for d in dong] == [
        "[Lớp]", "[Mục đích]", "[Grain]", "[Khoá]", "[Nguồn]", "[Phạm vi]", "[Đã xử lý]",
        "[Refresh]", "[Dùng khi]", "[Không dùng khi]", "[Lưu ý]"]
    assert "dùng SOCIAL_LISTENING.qc_khan_gia" in dong[9] and "khan_gia_cd_den" in dong[7]
    cot = re.findall(r"^\s{2}(\w+)\s+\w+\s+OPTIONS\(description='(.{10,}?)'\)", m.group(1),
                     re.MULTILINE)
    assert [c for c, _ in cot] == [c for c, _ in b["cot"]] + ["dong_bo_luc"]
    # Khối tạo bảng nằm TRƯỚC phần nâng cấp Meta (phần đó không được có CREATE TABLE).
    assert sql.index("qc_khan_gia_cd`") < sql.index("-- ───────────── Meta Ads (20/10/2026)")
    # Tiền: như mọi bảng qc_* (BQ_QC_XUAT_TIEN khác 1 → bỏ).
    monkeypatch.delenv("BQ_QC_XUAT_TIEN", raising=False)
    r = DBQ._bo_tien("qc_khan_gia_cd", {"chi": 5, "hien_thi": 3, "chi_so": {"spend": 5}})
    assert r["chi"] is None and r["hien_thi"] == 3 and "spend" not in r["chi_so"]


def test_le_khong_chay_khong_doc_cap_chien_dich():
    dv, _kho, tt = _dv()
    _ket_noi_san(dv, tt)
    dv.dong_bo()
    assert not any(a["advertiser_id"] == LE for a in _audience(tt))
    _mdv()                                                    # máy chủ Meta giả dựng được
    assert MATE in CAMPAIGN
