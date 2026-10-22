"""Bảng chiến dịch / quảng cáo trang Quảng cáo: lọc theo tên + chiến dịch, sắp theo mọi chỉ số
(22/10/2026, MKT — task t284905: "thêm các filter lọc theo tên, campaign và sort theo các chỉ số cho
dashboard Ads (gồm meta ads và tiktok ads)")."""
from __future__ import annotations

import contextlib
import datetime
import re
import unittest.mock

from test_tiktok_ads import Q, QL, _co_so, _tao_app, dang_nhap

from dashboard import kho_qc as KQ
from dashboard import quang_cao as QC


def test_loc_bang_kiem_tham_so():
    d = QC.loc_bang({}, True)
    assert d == {"tim": "", "mau": "", "cd": "", "sap": "chi", "chieu": "giam", "so": 10}
    assert QC.loc_bang({}, False)["sap"] == "hien_thi"
    # Người không xem tiền: không xếp theo chỉ số tiền (thứ hạng chi cũng là thông tin tiền).
    for sap in QC.SAP_BANG_TIEN:
        assert QC.loc_bang({"sap": sap}, False)["sap"] == "hien_thi", sap
        assert QC.loc_bang({"sap": sap}, True)["sap"] == sap
    assert QC.loc_bang({"sap": "chi; DROP TABLE x"}, True)["sap"] == "chi"
    assert QC.loc_bang({"chieu": "tang"}, True)["chieu"] == "tang"
    assert QC.loc_bang({"chieu": "ASC"}, True)["chieu"] == "giam"
    assert QC.loc_bang({"so": "25"}, True)["so"] == 25
    for so in ("7", "500", "x", "-1"):
        assert QC.loc_bang({"so": so}, True)["so"] == 10, so
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
                        assert ts[-1] == KQ.TOP_TOI_DA
                        assert KQ.SAP_BANG_SQL[sap] in sql
                        assert (" ASC NULLS LAST" in sql) is tang
                        assert ("campaign_id = %s" in sql) is bool(cd)
                        if mau:
                            assert ts[-2] == ["c1"]                   # chỉ "Chiến dịch TẾT" khớp
                            assert ("campaign_id = %s" in goi[0][0]) is bool(cd)
                        assert r["tong"] == 7 and "tong_khop" not in r["rows"][0]
                        assert r["rows"][0]["ten"] == "Tên"
    goi, kn = _bat_sql()
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        KQ.qc_bang("ad", ["1"], tu, den, sap="khong-co'; --")
        assert KQ.qc_bang("ad", ["1"], tu, den, sap="chi", mau="khongco") == {"rows": [], "tong": 0}
    assert "khong-co" not in goi[0][0] and "ORDER BY t.hien_thi DESC" in goi[0][0]
    assert len(goi) == 3                       # tìm không khớp tên nào: không chạy truy vấn tổng
    assert KQ.qc_bang("ad", [], tu, den, sap="chi") == {"rows": [], "tong": 0}


def test_api_qc_loc_ten_chien_dich_va_sap_xep():
    _app, c, _kho, _kho_qc, _tt, _dv = _co_so(_tao_app())
    dang_nhap(c, QL)
    d = c.get(f"/api/qc?{Q}").json()
    assert d["sap"] == "chi" and d["bang"]["chieu"] == "giam" and d["bang"]["so"] == 10
    assert len(d["campaign"]) == min(10, d["bang"]["tong_campaign"])
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
    for nhan in ("CPM", "CTR", "ROAS", "Click", "Tương tác"):
        assert f'>{nhan}<span class="qc-sap__mui"' in t, nhan
    # Tên chiến dịch là link lọc quảng cáo của nó.
    assert re.search(r'class="qc-bang__loc" href="[^"]*cd=[^"]+#top"', t)

    t = c.get(f"/quang-cao?{Q}&sap=ctr&chieu=tang&so=25").text
    assert 'aria-sort="ascending"' in t and 'option value="25" selected' in t
    assert 'option value="ctr" selected' in t and "Bỏ lọc" in t
    # Bộ lọc đầu trang giữ lựa chọn của bảng khi đổi ngày / tài khoản.
    assert '<input type="hidden" name="chieu" value="tang">' in t
    assert '<input type="hidden" name="so" value="25">' in t

    d = c.get(f"/api/qc?{Q}").json()
    cd, ten = d["campaign"][0]["campaign_id"], d["campaign"][0]["ten"]
    t = c.get(f"/quang-cao?{Q}&cd={cd}").text
    assert f"Chiến dịch: <b>{ten}</b>" in t and "Bỏ lọc chiến dịch" in t and "khớp" in t
    assert f'<input type="hidden" name="cd" value="{cd}">' in t
    assert t.count(f'name="cd" value="{cd}"') == 1       # chỉ ở form bảng, không ở Bộ lọc đầu trang
    t = c.get(f"/quang-cao?{Q}&tim=khongcoteninaynay").text
    assert "Không có chiến dịch nào khớp bộ lọc" in t
