"""Bảng chiến dịch / quảng cáo trang Quảng cáo: lọc theo tên + chiến dịch, sắp theo mọi chỉ số
(22/10/2026, MKT — task t284905: "thêm các filter lọc theo tên, campaign và sort theo các chỉ số cho
dashboard Ads (gồm meta ads và tiktok ads)"). Cùng ngày (chủ dự án): phân trang 20 dòng thay "Số
dòng", chọn nhiều tài khoản."""
from __future__ import annotations

import contextlib
import datetime
import html
import re
import unittest.mock
from pathlib import Path

from test_tiktok_ads import (HAPAS_KOC, LE, MM_2, MM_MKT, Q, QL, GiaTikTok, _co_so, _tao_app,
                             dang_nhap)

from dashboard import kho_qc as KQ
from dashboard import quang_cao as QC


def test_loc_bang_kiem_tham_so():
    d = QC.loc_bang({}, True)
    assert d == {"tim": "", "mau": "", "cd": "", "sap": "chi", "chieu": "giam", "tc": 1, "ta": 1}
    assert QC.loc_bang({}, False)["sap"] == "hien_thi"
    # Người không xem tiền: không xếp theo chỉ số tiền (thứ hạng chi cũng là thông tin tiền).
    for sap in QC.SAP_BANG_TIEN:
        assert QC.loc_bang({"sap": sap}, False)["sap"] == "hien_thi", sap
        if sap in QC.SAP_BANG:          # 22/10/2026: roas tạm ẩn (QC.HIEN_DOANH_THU)
            assert QC.loc_bang({"sap": sap}, True)["sap"] == sap
    assert QC.loc_bang({"sap": "chi; DROP TABLE x"}, True)["sap"] == "chi"
    assert QC.loc_bang({"chieu": "tang"}, True)["chieu"] == "tang"
    assert QC.loc_bang({"chieu": "ASC"}, True)["chieu"] == "giam"
    assert "so" not in QC.loc_bang({"so": "25"}, True)          # "Số dòng" cũ: lờ đi (22/10/2026)
    assert QC.loc_bang({"tc": "3", "ta": "12"}, True) | {} == {**QC.loc_bang({}, True), "tc": 3,
                                                                "ta": 12}
    d = QC.loc_bang({"tim": "  Chiến   dịch  Tết ", "cd": "1793_ab-C"}, True)
    assert d["tim"] == "Chiến dịch Tết" and d["mau"] == "chiendichtet" and d["cd"] == "1793_ab-C"
    assert len(QC.loc_bang({"tim": "a" * 500}, True)["tim"]) == QC.TIM_TOI_DA
    for cd in ("1' OR '1'='1", "a b", "x" * 65):
        assert QC.loc_bang({"cd": cd}, True)["cd"] == "", cd


def _bat_sql():
    goi = []

    class C:
        def execute(self, sql, ts):
            goi.append((sql, list(ts)))
            if sql.startswith("WITH"):
                self._r = [{"campaign_id": "c1", "ad_id": "c1", "advertiser_id": "1",
                            "hien_thi": 5, "tong_khop": 7}]
            elif "advertiser_id = ANY" in sql:            # tên mới nhất để lọc ở Python
                self._r = [{"campaign_id": k, "ad_id": k, "ten": t, "ten_ad": t, "ten_campaign": None}
                           for k, t in (("c1", "Chiến dịch TẾT"), ("c2", "Sale 11.11"))]
            else:
                self._r = [{"campaign_id": "c1", "ad_id": "c1", "ten": "Tên"}]
            return self

        def fetchall(self):
            return self._r

    @contextlib.contextmanager
    def kn(trung="x"):
        yield C()
    return goi, kn


def test_qc_bang_sql_tham_so_khop_moi_to_hop():
    """Số %s trong SQL = số tham số ở MỌI tổ hợp (cấp × tìm × chiến dịch × cột xếp × chiều); biểu thức
    xếp chỉ lấy từ bảng cố định; tìm tên so khớp bỏ dấu ở Python rồi lọc theo MÃ; kết quả bỏ
    `tong_khop`, trả tổng riêng."""
    tu, den = datetime.date(2026, 10, 1), datetime.date(2026, 10, 7)
    for cap in ("campaign", "ad"):
        for mau in ("", "tet"):
            for cd in ("", "c1"):
                for sap in QC.SAP_BANG:
                    for tang in (False, True):
                        goi, kn = _bat_sql()
                        with unittest.mock.patch.object(KQ, "ket_noi", kn):
                            r = KQ.qc_bang(cap, ["1", "2"], tu, den, sap=sap, tang=tang, mau=mau,
                                           cd=cd, n=999)
                        for sql, ts in goi:
                            assert sql.count("%s") == len(ts), (cap, mau, cd, sap, sql)
                        sql, ts = goi[1 if mau else 0]
                        assert ts[-2:] == [KQ.TOP_TOI_DA, 0] and sql.endswith("LIMIT %s OFFSET %s")
                        assert KQ.SAP_BANG_SQL[sap] in sql
                        assert (" ASC NULLS LAST" in sql) is tang
                        assert ("campaign_id = %s" in sql) is bool(cd)
                        if mau:
                            assert ts[-3] == ["c1"]                   # chỉ "Chiến dịch TẾT" khớp
                            assert ("campaign_id = %s" in goi[0][0]) is bool(cd)
                        assert r["tong"] == 7 and "tong_khop" not in r["rows"][0] and r["bo_qua"] == 0
                        assert r["rows"][0]["ten"] == "Tên"
    goi, kn = _bat_sql()
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        KQ.qc_bang("ad", ["1"], tu, den, sap="khong-co'; --")
        assert KQ.qc_bang("ad", ["1"], tu, den, sap="chi", mau="khongco") == {
            "rows": [], "tong": 0, "bo_qua": 0}
    assert "khong-co" not in goi[0][0] and "ORDER BY t.hien_thi DESC" in goi[0][0]
    assert len(goi) == 3                       # tìm không khớp tên nào: không chạy truy vấn tổng
    assert KQ.qc_bang("ad", [], tu, den, sap="chi") == {"rows": [], "tong": 0, "bo_qua": 0}


def test_api_qc_loc_ten_chien_dich_va_sap_xep():
    _app, c, _kho, _kho_qc, _tt, _dv = _co_so(_tao_app())
    dang_nhap(c, QL)
    d = c.get(f"/api/qc?{Q}").json()
    assert d["sap"] == "chi" and d["bang"]["chieu"] == "giam" and d["bang"]["moi_trang"] == 20
    assert len(d["campaign"]) == min(20, d["bang"]["tong_campaign"])
    chi = [r["chi"] for r in d["campaign"]]
    assert chi == sorted(chi, reverse=True)

    # Xếp mọi cột, hai chiều — dòng có số trước, đúng thứ tự.
    for sap, khoa in (("hien_thi", "hien_thi"), ("follow", "follow"), ("tuong_tac", "tuong_tac"),
                      ("click", "click"), ("view", "view_video")):
        for chieu in ("giam", "tang"):
            x = c.get(f"/api/qc?{Q}&sap={sap}&chieu={chieu}&so=50").json()
            assert x["sap"] == sap and x["bang"]["chieu"] == chieu
            v = [r[khoa] or 0 for r in x["ad"]]
            assert v == sorted(v, reverse=chieu == "giam"), (sap, chieu)
    x = c.get(f"/api/qc?{Q}&sap=cpm&chieu=tang&so=50").json()
    du = [r for r in x["campaign"] if (r["hien_thi"] or 0) >= QC.NGUONG_TI_LE]
    cpm = [r["chi"] / r["hien_thi"] for r in du]
    assert cpm == sorted(cpm) and x["campaign"][:len(du)] == du    # dưới ngưỡng xuống cuối

    # Tìm theo tên: không dấu vẫn khớp; số khớp đúng; quảng cáo khớp theo tên chiến dịch chứa nó.
    ten = d["campaign"][0]["ten"]
    x = c.get(f"/api/qc?{Q}&tim={QC.chu_tim(ten)}").json()
    assert x["bang"]["tim"] == QC.chu_tim(ten)
    assert x["campaign"] and all(QC.chu_tim(ten) in QC.chu_tim(r["ten"]) for r in x["campaign"])
    assert x["bang"]["tong_campaign"] < d["bang"]["tong_campaign"]
    assert x["ad"] and all(QC.chu_tim(ten) in QC.chu_tim(r["ten_campaign"]) for r in x["ad"])
    x = c.get(f"/api/qc?{Q}&tim=khongcoteninaynay").json()
    assert x["campaign"] == [] and x["ad"] == [] and x["bang"]["tong_ad"] == 0
    for tim in ("…", "-", "ภาษาไทย"):                  # không còn chữ/số Latin: không khớp, không lờ đi
        x = c.get(f"/api/qc?{Q}", params={"tim": tim}).json()
        assert x["campaign"] == [] and x["ad"] == [] and x["bang"]["tim"] == tim

    # Lọc chiến dịch: bảng chiến dịch chỉ nó, bảng quảng cáo chỉ quảng cáo của nó. KPI không đổi.
    cd = d["campaign"][0]["campaign_id"]
    x = c.get(f"/api/qc?{Q}&cd={cd}&so=50").json()
    assert [r["campaign_id"] for r in x["campaign"]] == [cd] and x["kpi"] == d["kpi"]
    cd = d["ad"][0]["campaign_id"]                 # (dữ liệu giả: mã chiến dịch của ad sinh riêng)
    x = c.get(f"/api/qc?{Q}&cd={cd}&so=50").json()
    assert x["ad"] and all(r["campaign_id"] == cd for r in x["ad"])
    assert x["bang"]["tong_ad"] < d["bang"]["tong_ad"]


def test_trang_quang_cao_thanh_loc_va_tieu_de_cot_bam_duoc():
    _app, c, _kho, _kho_qc, _tt, _dv = _co_so(_tao_app())
    dang_nhap(c, QL)
    t = c.get(f"/quang-cao?{Q}").text
    assert 'data-o="loc-bang"' in t and 'name="tim"' in t and "Chiến dịch và quảng cáo" in t
    # Cột đang xếp (Chi, cao → thấp) có aria-sort; bấm lại → thấp → cao.
    th = re.search(r'<th class="so" aria-sort="descending"><a class="qc-sap qc-sap--dang" '
                   r'href="([^"]+)"', t)
    assert th and "sap=chi" in th.group(1) and "chieu=tang" in th.group(1)
    for nhan in ("CPM", "CTR", "Click", "Tương tác"):
        assert f'>{nhan}<span class="qc-sap__mui"' in t, nhan
    # Tên chiến dịch là link lọc quảng cáo của nó.
    assert re.search(r'class="qc-bang__loc" href="[^"]*cd=[^"]+#top"', t)

    t = c.get(f"/quang-cao?{Q}&sap=ctr&chieu=tang&so=25").text
    assert 'aria-sort="ascending"' in t and 'name="so"' not in t and "Số dòng" not in t
    assert 'option value="ctr" selected' in t and "Bỏ lọc" in t
    # Bộ lọc đầu trang giữ lựa chọn của bảng khi đổi ngày / tài khoản.
    assert '<input type="hidden" name="chieu" value="tang">' in t

    d = c.get(f"/api/qc?{Q}").json()
    cd, ten = d["campaign"][0]["campaign_id"], d["campaign"][0]["ten"]
    t = c.get(f"/quang-cao?{Q}&cd={cd}").text
    assert f"Chiến dịch: <b>{ten}</b>" in t and "Bỏ lọc chiến dịch" in t and "khớp" in t
    assert f'<input type="hidden" name="cd" value="{cd}">' in t
    # Ở form bảng + form Xuất Lark Sheet (Sheet theo đúng bộ lọc bảng), không ở Bộ lọc đầu trang.
    assert t.count(f'name="cd" value="{cd}"') == 2
    assert 'name="cd"' not in t.split('id="qc-loc"')[1].split("</form>")[0]
    t = c.get(f"/quang-cao?{Q}&tim=khongcoteninaynay").text
    assert "Không có chiến dịch nào khớp bộ lọc" in t


# ───────────────────────────── phân trang (22/10/2026, chủ dự án) ─────────────────────────────
TU, DEN = datetime.date(2026, 10, 12), datetime.date(2026, 10, 18)
_NAV = r'<nav class="phan-trang" aria-label="([^"]+)">(.*?)</nav>'
_SO = r'<span class="dai-qc__an">Trang </span>([\d.]+)</a>'


def _nhieu():
    """3 tài khoản có số × 25 chiến dịch, × 60 quảng cáo → nhiều trang."""
    return _co_so(_tao_app(tt=GiaTikTok(so_campaign=25, so_ad=60)))


def _href(t: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(r'href="([^"]+)"', t)]


def test_so_trang_va_o_trang():
    for x in (None, "", "0", "-3", "abc", "2.5", "1e3", "99999999", " "):
        assert QC.so_trang(x) == 1, x
    assert QC.so_trang("7") == 7 and QC.so_trang(" 12 ") == 12
    assert QC.so_trang("9999999") == QC.TRANG_TOI_DA
    assert QC.o_trang(1, 1) == [1] and QC.o_trang(5, 8) == list(range(1, 9))
    assert QC.o_trang(1, 150) == [1, 2, 3, 4, 5, 6, None, 150]
    assert QC.o_trang(4, 150) == [1, 2, 3, 4, 5, 6, None, 150]
    assert QC.o_trang(5, 150) == [1, None, 4, 5, 6, None, 150]
    assert QC.o_trang(8, 150) == [1, None, 7, 8, 9, None, 150]
    assert QC.o_trang(147, 150) == [1, None, 145, 146, 147, 148, 149, 150]
    assert QC.o_trang(150, 150) == QC.o_trang(999, 150) == [1, None, *range(145, 151)]
    assert QC.o_trang(0, 0) == [1]


def test_qc_bang_qua_trang_cuoi_ve_trang_cuoi():
    """Trang quá cuối: đếm (LIMIT 1 OFFSET 0) rồi đọc lại đúng trang cuối — cùng câu SQL."""
    goi = []

    class C:
        def execute(self, sql, ts):
            goi.append((sql, list(ts)))
            if sql.startswith("WITH"):
                bo_qua = ts[-1]
                self._r = ([] if bo_qua >= 45 else
                           [{"campaign_id": f"c{i}", "advertiser_id": "1", "tong_khop": 45}
                            for i in range(bo_qua, min(45, bo_qua + ts[-2]))])
            else:
                self._r = []
            return self

        def fetchall(self):
            return self._r

    @contextlib.contextmanager
    def kn(trung="x"):
        yield C()
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        r = KQ.qc_bang("campaign", ["1"], TU, DEN, sap="chi", n=20, bo_qua=980)
    assert r["bo_qua"] == 40 and r["tong"] == 45 and len(r["rows"]) == 5
    assert [g[1][-2:] for g in goi if g[0].startswith("WITH")] == [[20, 980], [1, 0], [20, 40]]
    assert len({g[0] for g in goi if g[0].startswith("WITH")}) == 1
    goi.clear()
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        r = KQ.qc_bang("campaign", ["1"], TU, DEN, sap="chi", n=999, bo_qua=-5)
    assert goi[0][1][-2:] == [KQ.TOP_TOI_DA, 0] and r["bo_qua"] == 0


def test_api_phan_trang_may_chu():
    _app, c, *_ = _nhieu()
    dang_nhap(c, QL)
    d = c.get(f"/api/qc?{Q}&so=50").json()            # "so" cũ: lờ đi
    b = d["bang"]
    n = b["so_trang_ad"]
    assert b["tong_ad"] == 180 and n == 9 and b["trang_ad"] == 1 and len(d["ad"]) == 20
    assert b["tong_campaign"] == 75 and b["so_trang_campaign"] == 4 and "so" not in b
    p2 = c.get(f"/api/qc?{Q}&ta=2").json()
    assert p2["bang"]["trang_ad"] == 2 and p2["bang"]["trang_campaign"] == 1
    assert p2["campaign"] == d["campaign"]                # trang bảng kia không đổi
    assert not {r["ad_id"] for r in d["ad"]} & {r["ad_id"] for r in p2["ad"]}
    assert d["ad"][-1]["chi"] >= p2["ad"][0]["chi"]
    cuoi = c.get(f"/api/qc?{Q}&ta=99999&tc=4").json()
    assert cuoi["bang"]["trang_ad"] == n and len(cuoi["ad"]) == 180 - (n - 1) * 20
    assert cuoi["bang"]["trang_campaign"] == 4 and len(cuoi["campaign"]) == 75 - 3 * 20
    for x in ("0", "-3", "abc", "2.5", ""):
        assert c.get(f"/api/qc?{Q}&ta={x}").json()["bang"]["trang_ad"] == 1, x
    # Ghép mọi trang = đủ mọi dòng, không trùng, đúng thứ tự (xếp ở máy chủ trước khi cắt trang).
    tat = []
    for i in range(1, n + 1):
        tat += c.get(f"/api/qc?{Q}&ta={i}&sap=hien_thi&chieu=tang").json()["ad"]
    assert len({r["ad_id"] for r in tat}) == len(tat) == 180
    v = [r["hien_thi"] or 0 for r in tat]
    assert v == sorted(v)
    # Lọc hẹp lại khi đang ở trang xa → về trang cuối của kết quả mới (không bảng rỗng).
    ten = d["campaign"][0]["ten"]
    x = c.get(f"/api/qc?{Q}&tc=4&tim={QC.chu_tim(ten)}").json()
    assert x["campaign"] and x["bang"]["trang_campaign"] == x["bang"]["so_trang_campaign"]


def test_thanh_trang_hien_dung_va_giu_bo_loc():
    _app, c, *_ = _nhieu()
    dang_nhap(c, QL)
    t = c.get(f"/quang-cao?{Q}").text
    nav = re.findall(_NAV, t, re.S)
    assert [a for a, _ in nav] == ["Trang của bảng chiến dịch", "Trang của bảng quảng cáo"]
    cd, ad = nav[0][1], nav[1][1]
    assert "…" not in cd and re.findall(_SO, cd) == ["1", "2", "3", "4"]
    # 9 trang, đang ở 1: ‹ 1 2 3 4 5 6 … 9 ›; trước mờ, sau là link; trang hiện tại aria-current.
    assert re.findall(_SO, ad) == ["1", "2", "3", "4", "5", "6", "9"] and ad.count("…") == 1
    assert ad.count('aria-current="page"') == 1
    assert re.search(r'aria-current="page"><span class="dai-qc__an">Trang </span>1<', ad)
    assert re.search(r'<span class="phan-trang__o phan-trang__ben" aria-disabled="true"><span '
                     r'class="dai-qc__an">Trang trước', ad)
    assert [h for h in _href(ad) if "ta=2" in h] and all(h.endswith("#top") for h in _href(ad))
    assert "Trang 1/9 · 180 khớp" in ad and 'aria-hidden="true">1/9<' in ad

    # Giữa: ‹ 1 … 4 5 6 … 9 › ; liên kết giữ mọi bộ lọc + trang bảng kia; đổi xếp → về trang 1.
    t = c.get(f"/quang-cao?{Q}&ta=5&tc=2&sap=hien_thi&chieu=tang&tk={HAPAS_KOC}&tk={MM_MKT}"
              f"&tk={MM_2}").text
    nav = dict(re.findall(_NAV, t, re.S))
    ad = nav["Trang của bảng quảng cáo"]
    assert re.findall(_SO, ad) == ["1", "4", "5", "6", "9"] and ad.count("…") == 2
    for h in _href(ad):
        assert "tc=2" in h and "sap=hien_thi" in h and "chieu=tang" in h and h.endswith("#top")
        assert h.count("tk=") == 3 and "tu=2026-10-12" in h
    assert "ta=4" in _href(ad)[0]                                        # ‹ = trang 4
    assert all("ta=5" in h for h in _href(nav["Trang của bảng chiến dịch"]))
    loc_cot = [html.unescape(h) for h in re.findall(r'class="qc-sap[^"]*" href="([^"]+)"', t)]
    assert loc_cot and not any("tc=" in h or "ta=" in h for h in loc_cot)
    assert all(h.count("tk=") == 3 for h in loc_cot)
    # Trang cuối: › mờ.
    t = c.get(f"/quang-cao?{Q}&ta=9").text
    ad = dict(re.findall(_NAV, t, re.S))["Trang của bảng quảng cáo"]
    assert re.search(r'aria-disabled="true"><span class="dai-qc__an">Trang sau', ad)
    # Một trang: không có thanh trang.
    _a, c2, *_ = _co_so(_tao_app())
    dang_nhap(c2, QL)
    assert '<nav class="phan-trang"' not in c2.get(f"/quang-cao?{Q}").text


# ───────────────────────────── chọn nhiều tài khoản (22/10/2026, chủ dự án) ─────────────────────────────
def test_tk_chon_thuan():
    tk = [{"advertiser_id": "1"}, {"advertiser_id": "act_2"}, {"advertiser_id": "3"}]
    assert QC.tk_chon(["3", "1", "3", ""], tk) == (["1", "3"], [])         # theo thứ tự danh sách
    assert QC.tk_chon("act_2", tk) == (["act_2"], [])                       # một tk= cũ
    assert QC.tk_chon(None, tk) == ([], []) and QC.tk_chon([], tk) == ([], [])
    assert QC.tk_chon(["1", "9", "x'--"], tk) == (["1"], ["9", "x'--"])
    assert QC.tk_chon(["1", "act_2", "3"], tk) == ([], [])                  # chọn đủ = tất cả
    nhieu = [{"advertiser_id": str(i)} for i in range(300)]
    chon, ngoai = QC.tk_chon([str(i) for i in range(250)], nhieu)
    assert len(chon) == QC.TK_TOI_DA == 200 and len(ngoai) == 50


def test_api_va_trang_nhieu_tai_khoan_trong_pham_vi():
    _app, c, _kho, kho_qc, *_ = _co_so(_tao_app())
    dang_nhap(c, QL)
    tat = c.get(f"/api/qc?{Q}").json()
    d = c.get(f"/api/qc?{Q}&tk={MM_2}&tk={HAPAS_KOC}").json()
    hai = [t["advertiser_id"] for t in tat["tai_khoan"] if t["advertiser_id"] in (MM_2, HAPAS_KOC)]
    assert d["tk_ds"] == hai and d["tk"] == ""
    tong = kho_qc.qc_tong([MM_2, HAPAS_KOC], TU, DEN)
    assert d["kpi"]["hien_thi"] == tong["hien_thi"] != tat["kpi"]["hien_thi"]
    assert d["kpi"]["chi"] == tong["chi"]
    assert sum(x["hien_thi"] for x in d["theo_ngay"]) == tong["hien_thi"]           # biểu đồ
    t0, t1 = QC.khoang_truoc(TU, DEN)                                               # kỳ trước
    truoc = QC.loc_doanh_thu(QC.kpi(kho_qc.qc_tong([MM_2, HAPAS_KOC], t0, t1)))
    assert d["kpi_truoc"] == json_kpi(truoc)
    assert {r["advertiser_id"] for r in d["campaign"] + d["ad"]} == {MM_2, HAPAS_KOC}
    assert d["bang"]["tong_ad"] < tat["bang"]["tong_ad"]
    # Một tk= cũ vẫn chạy; chọn đủ mọi tài khoản = tất cả.
    d1 = c.get(f"/api/qc?{Q}&tk={MM_2}").json()
    assert d1["tk"] == MM_2 and d1["tk_ds"] == [MM_2]
    du = "&".join(f"tk={t['advertiser_id']}" for t in tat["tai_khoan"])
    assert c.get(f"/api/qc?{Q}&{du}").json()["tk_ds"] == [] and tat["tk_ds"] == []
    # Ngoài phạm vi: API 404 (như trước, kể cả lẫn với mã đúng); trang bỏ lặng mã lạ.
    assert c.get(f"/api/qc?{Q}&ben=matemade&tk={HAPAS_KOC}").status_code == 404
    assert c.get(f"/api/qc?{Q}&tk={MM_2}&tk=999").status_code == 404
    assert c.get(f"/api/qc?{Q}&nen_tang=meta&tk={MM_2}").status_code == 404
    r = c.get(f"/quang-cao?{Q}&ben=matemade&tk={HAPAS_KOC}&tk={MM_2}&tk=x%27--")
    assert r.status_code == 200
    t = r.text
    assert f'name="tk" value="{MM_2}" checked>' in t and HAPAS_KOC not in t
    assert re.search(r'id="qc-tk-gia-tri" data-tat-ca="Tất cả tài khoản \(2\)">mate made 2<', t)

    t = c.get(f"/quang-cao?{Q}&tk={MM_2}&tk={HAPAS_KOC}").text
    assert re.search(r'id="qc-tk-gia-tri" data-tat-ca="Tất cả tài khoản \(4\)">2 tài khoản<', t)
    for x in (MM_2, HAPAS_KOC):
        assert f'name="tk" value="{x}" checked>' in t
    assert f'name="tk" value="{MM_MKT}">' in t                                      # chưa chọn
    assert re.search(r'<legend class="qc-tk__nhom-ten"><span class="qc-cham qc-cham--tiktok"', t)
    # Form bảng + form Xuất Sheet giữ đúng các tài khoản; khoảng nhanh giữ; nền tảng bỏ chọn.
    bang = t.split('data-o="loc-bang"')[1].split("</form>")[0]
    sheet = t.split('data-o="tao-sheet"')[1].split("</form>")[0]
    for khoi in (bang, sheet):
        assert re.findall(r'<input type="hidden" name="tk" value="([^"]+)">', khoi) == hai
    nhanh = _href(t.split('aria-label="Khoảng nhanh"')[1].split("</nav>")[0])
    assert nhanh and all(h.count("tk=") == 2 for h in nhanh)
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "templates" / "quang_cao.html"
           ).read_text(encoding="utf-8")
    assert "url_cho(nen_tang=n.ma, tk='', cd='')" in src           # đổi nền tảng: bỏ chọn tài khoản
    # Không chọn: tóm tắt "Tất cả tài khoản (N)", không ô nào đánh dấu.
    t = c.get(f"/quang-cao?{Q}").text
    assert re.search(r'id="qc-tk-gia-tri" data-tat-ca="Tất cả tài khoản \(4\)">Tất cả tài khoản '
                     r'\(4\)<', t) and f'name="tk" value="{LE}">' in t and '" checked>' not in t


def json_kpi(k: dict) -> dict:
    import json
    return json.loads(json.dumps(k, default=str))
