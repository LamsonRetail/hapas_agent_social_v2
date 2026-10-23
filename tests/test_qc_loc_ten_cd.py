"""Lọc TÊN CHIẾN DỊCH cấp trang ở trang Quảng cáo (23/10/2026, MKT: "lọc tên campaign" ở Bộ lọc đầu
trang — tên kiểu "HAPAS OFFICIAL_CÂN NHẮC_DA 20/10_TEASER SALE").

Soi: `quang_cao.loc_ten_cd` (tách cụm bằng , ; = HOẶC, bỏ dấu, cụm không còn chữ Latin bị bỏ, có chữ mà
không còn cụm nào = không khớp gì); `kho_qc` đổi sang số cấp chiến dịch (qc_campaign_ngay, campaign_id
= ANY) khi có `cds`; KPI / biểu đồ / TikTok và Meta / hai bảng / kênh đăng chỉ tính chiến dịch khớp;
kỳ trước tính lại danh sách khớp của KỲ TRƯỚC; thẻ + trạng thái rỗng + ghi chú Khán giả; mọi liên kết
/ biểu mẫu giữ `ten_cd`; Lark Sheet (nút trang, tool Mark, bộ nghe) mang và áp `ten_cd` vào mọi tab.

Không mạng, không Postgres: kho giả (`test_tiktok_ads`, `test_kenh_dang`, `test_sheet_qc`).
"""
from __future__ import annotations

import contextlib
import datetime
import html
import re
import unittest.mock
from urllib.parse import urlencode

import pytest
from test_kenh_dang import GiaKhoKenh
from test_sheet_qc import YC, GiaKhoSheet, _chay, _form
from test_sheet_qc_mark import _hoi
from test_tiktok_ads import QL, _co_so, _tao_app, dang_nhap

import sheet_qc_tool as ST
import xuat_sheet_qc as X
from dashboard import kho_qc as KQ
from dashboard import kho_sheet_qc as KS
from dashboard import nhap_lieu as NL
from dashboard import quang_cao as QC

Q = "tu=2026-10-12&den=2026-10-18"
TU, DEN = datetime.date(2026, 10, 12), datetime.date(2026, 10, 18)
TEN_A = "HAPAS OFFICIAL_CÂN NHẮC_DA 20/10_TEASER SALE"     # chiến dịch của HAPAS - KOC
TEN_B = "MM_Teaser Sale tháng 10"                          # chiến dịch của MATEMADE MKT
CD_A, CD_B, CD_C = "ca04010000", "ca53290001", "ca04160000"


# ───────────────────────────── 1. tách cụm (thuần) ─────────────────────────────
def test_loc_ten_cd_tach_cum_bo_dau_va_khong_latin():
    assert QC.loc_ten_cd({}) == {"chu": "", "maus": []}
    assert QC.loc_ten_cd({"ten_cd": "   "}) == {"chu": "", "maus": []}
    d = QC.loc_ten_cd({"ten_cd": "  TEASER SALE,  CÂN NHẮC_DA 20/10 "})
    assert d == {"chu": "TEASER SALE, CÂN NHẮC_DA 20/10", "maus": ["teasersale", "cannhacda2010"]}
    # ; cũng tách; trùng bỏ; cụm rỗng bỏ.
    assert QC.loc_ten_cd({"ten_cd": "teaser;Teaser;; ,sale"})["maus"] == ["teaser", "sale"]
    # Không còn chữ/số Latin: cụm đó bỏ; mọi cụm bị bỏ → maus rỗng (= không khớp gì, nơi gọi xử lý).
    assert QC.loc_ten_cd({"ten_cd": "…"}) == {"chu": "…", "maus": []}
    assert QC.loc_ten_cd({"ten_cd": "ภาษาไทย, -"})["maus"] == []
    assert QC.loc_ten_cd({"ten_cd": "ภาษาไทย, teaser"})["maus"] == ["teaser"]
    assert len(QC.loc_ten_cd({"ten_cd": "a" * 500})["chu"]) == QC.TIM_TOI_DA
    # Khớp tên mẫu của MKT dù gõ không dấu / khác hoa thường / khác ký hiệu.
    for go in ("teaser sale", "can nhac_da 20/10", "Cân Nhắc DA 2010", "hapas official"):
        assert all(m in QC.chu_tim(TEN_A) for m in QC.loc_ten_cd({"ten_cd": go})["maus"]), go


# ───────────────────────────── 2. SQL (kết nối giả) ─────────────────────────────
def _bat(tra=lambda sql, ts: []):
    goi = []

    class C:
        def execute(self, sql, ts=()):
            goi.append((sql, list(ts)))
            self._r = tra(sql, list(ts))
            return self

        def fetchall(self):
            return self._r

        def fetchone(self):
            return self._r[0] if self._r else None

    @contextlib.contextmanager
    def kn(*a, **k):
        yield C()
    return goi, kn


def test_sql_qc_tong_va_theo_ngay_doi_sang_cap_chien_dich():
    goi, kn = _bat(lambda sql, ts: [{"hien_thi": 1}])
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        KQ.qc_tong(["1"], TU, DEN)
        KQ.qc_tong(["1", "2"], TU, DEN, cds=["c1", "c2"])
        KQ.qc_theo_ngay(["1"], TU, DEN, cds=["c1"])
        KQ.qc_theo_ngay(["1"], TU, DEN)
        # [] = không chiến dịch nào khớp → rỗng, KHÔNG truy vấn.
        assert KQ.qc_tong(["1"], TU, DEN, cds=[]) == {}
        assert KQ.qc_theo_ngay(["1"], TU, DEN, cds=[]) == []
    assert len(goi) == 4
    for sql, ts in goi:
        assert sql.count("%s") == len(ts), sql
    (s0, t0), (s1, t1), (s2, t2), (s3, _t3) = goi
    assert "FROM qc_tk_ngay" in s0 and "campaign_id" not in s0 and t0 == [["1"], TU, DEN]
    assert "FROM qc_campaign_ngay" in s1 and "campaign_id = ANY(%s)" in s1
    assert t1 == [["1", "2"], ["c1", "c2"], TU, DEN] and "so_ngay" in s1
    # Biểu đồ: vẫn cộng JSON chi_so (xem trang SP) — qc_campaign_ngay cũng có cột chi_so.
    assert "FROM qc_campaign_ngay" in s2 and "chi_so->" in s2 and "GROUP BY ngay" in s2
    assert "FROM qc_tk_ngay" in s3 and "chi_so->" in s3


def test_sql_ma_cd_theo_ten_khop_o_python_hoac():
    def tra(sql, ts):
        return [{"campaign_id": k, "ten": t} for k, t in
                (("c1", TEN_A), ("c2", TEN_B), ("c3", "Chiến dịch khác"), ("c4", None))]
    goi, kn = _bat(tra)
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        assert KQ.ma_cd_theo_ten(["1"], TU, DEN, ["teasersale"]) == ["c1", "c2"]
        assert KQ.ma_cd_theo_ten(["1"], TU, DEN, ["cannhac", "khac"]) == ["c1", "c3"]
        assert KQ.ma_cd_theo_ten(["1"], TU, DEN, []) == []
        assert KQ.ma_cd_theo_ten([], TU, DEN, ["x"]) == []
    assert len(goi) == 2                                 # maus / ids rỗng: không truy vấn
    sql, ts = goi[0]
    assert sql == KQ.sql_ten_bang("campaign", cd=False) and ts == [["1"], TU, DEN]
    assert "DISTINCT ON (campaign_id)" in sql and "ORDER BY campaign_id, ngay DESC" in sql


def test_sql_qc_bang_va_kenh_loc_cds_moi_to_hop():
    def tra(sql, ts):
        if sql.startswith("WITH"):
            return [{"campaign_id": "c1", "ad_id": "a1", "advertiser_id": "1", "hien_thi": 5,
                     "tong_khop": 1, "tong": 1, "biet": True}]
        return [{"campaign_id": "c1", "ad_id": "a1", "ten": "TEASER", "ten_ad": "x",
                 "ten_campaign": "TEASER", "biet": True}]
    for cap in ("campaign", "ad"):
        for mau in ("", "teaser"):
            for cd in ("", "c1"):
                goi, kn = _bat(tra)
                with unittest.mock.patch.object(KQ, "ket_noi", kn):
                    KQ.qc_bang(cap, ["1"], TU, DEN, sap="chi", mau=mau, cd=cd, cds=["c1", "c9"])
                for sql, ts in goi:
                    assert sql.count("%s") == len(ts), (cap, mau, cd, sql)
                tong = next(g for g in goi if g[0].startswith("WITH"))
                assert "campaign_id = ANY(%s)" in tong[0] and ["c1", "c9"] in tong[1]
                if mau:                                  # tên khớp đọc TRONG các chiến dịch cds
                    assert "campaign_id = ANY(%s)" in goi[0][0]
    goi, kn = _bat(tra)
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        assert KQ.qc_bang("ad", ["1"], TU, DEN, sap="chi", cds=[]) == {"rows": [], "tong": 0,
                                                                         "bo_qua": 0}
        assert KQ.qc_kenh_dang(["1"], TU, DEN, cds=[])["rows"] == []
        KQ.qc_kenh_dang(["1"], TU, DEN, cds=["c1"])
        KQ.qc_kenh_dang(["1"], TU, DEN)
    assert len(goi) == 4                                 # cds=[]: không truy vấn
    (k1, tk1), (p1, tp1), (k2, _), (p2, _) = goi
    for sql, ts in goi:
        assert sql.count("%s") == len(ts), sql
    assert "q.campaign_id = ANY(%s)" in k1 and "q.campaign_id = ANY(%s)" in p1
    assert tk1[:4] == [["1"], TU, DEN, ["c1"]] and tp1 == [["1"], TU, DEN, ["c1"]]
    assert "campaign_id" not in k2 and "campaign_id" not in p2


def test_sql_sheet_doc_cap_chien_dich_khi_co_cds(monkeypatch):
    goi, kn = _bat(lambda sql, ts: [])
    monkeypatch.setattr(KS, "ket_noi", kn)
    KS.doc_theo_ngay(["1"], TU, DEN, cds=["c1"])
    KS.doc_tong_tien_te(["1"], TU, DEN, cds=["c1"])
    KS.doc_tong("quang_cao", ["1"], TU, DEN, cds=["c1"])
    assert KS.doc_theo_ngay(["1"], TU, DEN, cds=[]) == {"rows": [], "tong": 0}
    assert KS.doc_tong_tien_te(["1"], TU, DEN, cds=[]) == {}
    assert KS.doc_tong("chien_dich", ["1"], TU, DEN, cds=[]) == {"rows": [], "tong": 0}
    cau = [g for g in goi if not g[0].startswith("SET LOCAL")]
    assert len(cau) == 3
    for sql, ts in cau:
        assert sql.count("%s") == len(ts), sql
        assert "campaign_id = ANY(%s)" in sql and ["c1"] in ts
    assert "FROM qc_campaign_ngay" in cau[0][0] and "GROUP BY advertiser_id, ngay" in cau[0][0]
    assert "FROM qc_campaign_ngay q JOIN tk_quang_cao" in cau[1][0]
    assert cau[2][0] == KQ.sql_bang("ad", "chi", False, loc_ma=False, cd=False, them=KS._SO_NGAY,
                                    bo_qua=False, cds=True)


# ───────────────────────────── 3. API / trang (kho giả) ─────────────────────────────
def _dat_ten(kq):
    """Hai chiến dịch "teaser sale" (hai tài khoản), một quảng cáo đổi về chiến dịch A; kỳ trước
    (05–11/10) chỉ chiến dịch C mang tên teaser — kỳ trước phải TÍNH LẠI danh sách khớp."""
    bang = kq.bang["qc_campaign_ngay"]
    for (cid, _ng), r in bang.items():
        if cid == CD_A:
            r["ten"] = TEN_A
        elif cid == CD_B:
            r["ten"] = TEN_B
    for r in kq.bang["qc_ad_ngay"].values():
        if r["ad_id"] in ("ad04010000", "ad04010001"):
            r["campaign_id"], r["ten_campaign"] = CD_A, TEN_A
    mau = next(r for (cid, _), r in bang.items() if cid == CD_C)
    for i in range(7):
        d = datetime.date(2026, 10, 5) + datetime.timedelta(days=i)
        bang[(CD_C, d)] = {**mau, "ngay": d, "ten": "Teaser sale cũ", "hien_thi": 777, "chi": 70.0}


def _ve(kho_qc=None):
    app, c, kho, kq, tt, dv = _co_so(_tao_app(kho_qc=kho_qc))
    _dat_ten(kq)
    dang_nhap(c, QL)
    return app, c, kq


def _tong_cd(kq, cds, tu=TU, den=DEN, cot="hien_thi"):
    return sum(r[cot] or 0 for (cid, ng), r in kq.bang["qc_campaign_ngay"].items()
               if cid in cds and tu <= ng <= den)


def test_api_kpi_bieu_do_bang_chi_tinh_chien_dich_khop():
    _app, c, kq = _ve()
    tat = c.get(f"/api/qc?{Q}").json()
    assert tat["ten_cd"] is None
    d = c.get(_u("/api/qc", {"ten_cd": "teaser sale"})).json()
    assert d["ten_cd"] == {"chu": "teaser sale", "so_chien_dich": 2, "so_chien_dich_truoc": 1}
    # KPI + biểu đồ + khối nền tảng: chỉ cộng 2 chiến dịch khớp (cấp chiến dịch), khác số cả tài khoản.
    hien = _tong_cd(kq, {CD_A, CD_B})
    assert d["kpi"]["hien_thi"] == hien != tat["kpi"]["hien_thi"]
    assert d["kpi"]["chi"] == _tong_cd(kq, {CD_A, CD_B}, cot="chi")
    assert sum(x["hien_thi"] for x in d["theo_ngay"]) == hien
    assert sum(n["kpi"]["hien_thi"] or 0 for n in d["theo_nen_tang"]) == hien
    assert sum(x["hien_thi"] for x in d["theo_ngay_nen_tang"]) == hien
    # Bảng chiến dịch: đúng 2; bảng quảng cáo: chỉ quảng cáo của 2 chiến dịch đó.
    assert {r["campaign_id"] for r in d["campaign"]} == {CD_A, CD_B}
    assert d["bang"]["tong_campaign"] == 2
    cua_ab = {r["ad_id"] for r in kq.bang["qc_ad_ngay"].values() if r["campaign_id"] in (CD_A, CD_B)}
    assert {"ad04010000", "ad04010001"} <= cua_ab < {r["ad_id"] for r in tat["ad"]}
    assert {r["ad_id"] for r in d["ad"]} == cua_ab and d["bang"]["tong_ad"] == len(cua_ab)
    # Ghép với tìm theo tên / lọc chiến dịch của bảng.
    x = c.get(_u("/api/qc", {"ten_cd": "teaser sale", "tim": "hapas official"})).json()
    assert [r["campaign_id"] for r in x["campaign"]] == [CD_A] and x["kpi"] == d["kpi"]
    x = c.get(_u("/api/qc", {"ten_cd": "teaser sale", "cd": CD_B})).json()
    assert [r["campaign_id"] for r in x["campaign"]] == [CD_B]
    assert x["ad"] and all(r["campaign_id"] == CD_B for r in x["ad"])
    # HOẶC giữa các cụm; không dấu vẫn khớp.
    x = c.get(_u("/api/qc", {"ten_cd": "can nhac_da 20/10; MM_TEASER"})).json()
    assert x["ten_cd"]["so_chien_dich"] == 2
    x = c.get(_u("/api/qc", {"ten_cd": "Cân nhắc"})).json()
    assert x["ten_cd"]["so_chien_dich"] == 1 and x["kpi"]["hien_thi"] == _tong_cd(kq, {CD_A})


def test_api_ky_truoc_tinh_lai_danh_sach_khop():
    _app, c, kq = _ve()
    goi = []
    goc = kq.ma_cd_theo_ten

    def ghi(ids, tu, den, maus):
        goi.append((tu, den, tuple(maus)))
        return goc(ids, tu, den, maus)
    kq.ma_cd_theo_ten = ghi
    d = c.get(_u("/api/qc", {"ten_cd": "teaser sale"})).json()
    t0, t1 = QC.khoang_truoc(TU, DEN)
    assert goi == [(TU, DEN, ("teasersale",)), (t0, t1, ("teasersale",))]
    # Kỳ trước = chiến dịch "teaser" CỦA KỲ TRƯỚC (C), không phải A/B của kỳ này.
    assert d["kpi_truoc"]["hien_thi"] == 777 * 7
    assert d["doi"]["hien_thi"] == QC.doi_pt(d["kpi"]["hien_thi"], 777 * 7)
    # Không lọc: kỳ trước đọc qc_tk_ngay (không có số ngày 05–11/10).
    assert c.get(f"/api/qc?{Q}").json()["kpi_truoc"]["hien_thi"] is None


def test_api_chu_khong_latin_khong_khop_gi():
    _app, c, kq = _ve()
    for chu in ("…", "ภาษาไทย", "-, ;"):
        d = c.get(_u("/api/qc", {"ten_cd": chu})).json()
        assert d["ten_cd"]["so_chien_dich"] == 0, chu
        assert d["kpi"]["hien_thi"] is None and d["campaign"] == [] and d["ad"] == []
        assert sum(x["hien_thi"] for x in d["theo_ngay"]) == 0
        assert d["bang"]["tong_ad"] == 0 and d["theo_ngay_nen_tang"] == []
    # Cụm Latin còn lại vẫn dùng (cụm không Latin bị bỏ, không làm hỏng cả bộ lọc).
    d = c.get(_u("/api/qc", {"ten_cd": "ภาษาไทย, teaser sale"})).json()
    assert d["ten_cd"]["so_chien_dich"] == 2


def test_api_khong_xem_tien_van_loc_tien_khi_co_ten_cd():
    """Chốt chặn tiền không đổi: khối ten_cd không mang khoá tiền; loc_tien vẫn chạy cuối."""
    d = QC.loc_tien({"ten_cd": {"chu": "x", "so_chien_dich": 2, "so_chien_dich_truoc": 0},
                     "kpi": {"chi": 1, "hien_thi": 2}}, False)
    assert d == {"ten_cd": {"chu": "x", "so_chien_dich": 2, "so_chien_dich_truoc": 0},
                 "kpi": {"hien_thi": 2}}


def test_kenh_dang_nhan_cds():
    _app, c, kq = _ve(GiaKhoKenh())
    c.get(f"/api/qc?{Q}").json()
    assert kq.cds_kenh is None                              # không lọc: không truyền
    d = c.get(_u("/api/qc", {"ten_cd": "teaser sale"})).json()
    assert sorted(kq.cds_kenh) == [CD_A, CD_B] and d["kenh"] is not None
    c.get(_u("/api/qc", {"ten_cd": "…"})).json()
    assert kq.cds_kenh == []


def _u(duong: str, kw: dict) -> str:
    """URL có Q + tham số (params= của httpx THAY chuỗi truy vấn sẵn có, nên ghép tay)."""
    return f"{duong}?{Q}&{urlencode(kw)}"


def _href(t: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(r'href="([^"]+)"', t)]


def test_trang_the_lien_ket_bieu_mau_giu_ten_cd():
    _app, c, kq = _ve(GiaKhoKenh())
    t = c.get(_u("/quang-cao", {"ten_cd": "teaser sale"})).text
    # Ô trong Bộ lọc đầu trang (có nút i) + thẻ ngay trên KPI.
    loc = t.split('id="qc-loc"')[1].split("</form>")[0]
    assert 'name="ten_cd" value="teaser sale"' in loc and "VD: TEASER SALE, CÂN NHẮC_DA 20/10" in loc
    assert "KHÔNG áp vào Khán giả" in loc
    the = t.split('data-o="the-ten-cd"')[1].split("</p>")[0]
    assert "Chiến dịch có tên chứa: <b>teaser sale</b> · 2 chiến dịch" in the
    assert "(kỳ trước 1)" in the
    bo = _href(the)[0]
    assert "ten_cd" not in bo and "tu=2026-10-12" in bo
    assert t.index('data-o="the-ten-cd"') < t.index('id="qc-kpi"')
    # Khoảng nhanh, xếp cột, lọc chiến dịch, kênh: mọi liên kết giữ ten_cd.
    nhanh = _href(t.split('aria-label="Khoảng nhanh"')[1].split("</nav>")[0])
    assert nhanh and all("ten_cd=teaser+sale" in h for h in nhanh)
    sap = [html.unescape(h) for h in re.findall(r'class="qc-sap[^"]*" href="([^"]+)"', t)]
    assert sap and all("ten_cd=teaser+sale" in h for h in sap)
    loc_cd = [html.unescape(h) for h in re.findall(r'class="qc-bang__loc" href="([^"]+)"', t)]
    assert loc_cd and all("ten_cd=teaser+sale" in h for h in loc_cd)
    # Biểu mẫu bảng, kênh, Xuất Sheet: ẩn ten_cd.
    for dau in ('data-o="loc-bang"', 'class="qc-bang-loc qc-kenh-loc"', 'data-o="tao-sheet"'):
        khoi = t.split(dau)[1].split("</form>")[0]
        assert '<input type="hidden" name="ten_cd" value="teaser sale">' in khoi, dau
    assert "Tên chiến dịch chứa “teaser sale”" in t.split('id="sheet"')[1]
    # Khán giả theo tài khoản: nói rõ không theo lọc.
    assert 'data-o="kg-khong-loc-cd"' in t
    # Tab nền tảng dùng url_cho (giữ loc, gồm ten_cd).
    src = open(QC.__file__.replace("quang_cao.py", "templates/quang_cao.html"),
               encoding="utf-8").read()
    assert "url_cho(nen_tang=n.ma, tk='', cd='')" in src
    # Không lọc: không thẻ, không ghi chú, ô trống.
    t = c.get(f"/quang-cao?{Q}").text
    assert 'data-o="the-ten-cd"' not in t and 'data-o="kg-khong-loc-cd"' not in t
    assert 'name="ten_cd" value=""' in t and "ten_cd=" not in "".join(_href(t))


def test_trang_rong_khi_khong_chien_dich_nao_khop():
    _app, c, kq = _ve()
    t = c.get(_u("/quang-cao", {"ten_cd": "khongcochiendichnay"})).text
    assert "Không có chiến dịch nào có tên chứa “khongcochiendichnay”" in t
    assert 'data-o="ten-cd-trong"' in t and 'id="qc-kpi"' not in t
    assert "0 chiến dịch" in t.split('data-o="the-ten-cd"')[1].split("</p>")[0]
    t = c.get(_u("/quang-cao", {"ten_cd": "…"})).text
    assert "Không có chiến dịch nào có tên chứa “…”" in t


# ───────────────────────────── 4. Lark Sheet ─────────────────────────────
def test_nut_sheet_ghi_ten_cd():
    app, c, _kho, kq, tt, dv = _co_so(_tao_app())
    app.state.kho_sheet = ks = GiaKhoSheet()
    csrf = dang_nhap(c, QL)
    r = c.post("/quang-cao/tao-sheet", data=_form(csrf, ten_cd="  TEASER SALE,  CÂN NHẮC "))
    assert r.status_code == 303 and "ten_cd=TEASER+SALE" in r.headers["location"]
    assert ks.rows[0]["ten_cd"] == "TEASER SALE, CÂN NHẮC"
    t = c.get(f"/quang-cao?{Q}").text
    assert "tên chiến dịch “TEASER SALE, CÂN NHẮC”" in t.split('id="sheet"')[1]
    ks.rows.clear()
    c.post("/quang-cao/tao-sheet", data=_form(csrf))
    assert ks.rows[0]["ten_cd"] is None


def test_bo_nghe_ap_ten_cd_moi_tab(monkeypatch):
    kq, k, lk = _chay(monkeypatch, {**YC, "ten_cd": "TEASER SALE, cân nhắc"})
    assert kq["trang_thai"] == "xong"
    assert ("ma", ("teasersale", "cannhac")) in k.cds_doc
    assert ("ngay", ["17001"]) in k.cds_doc and ("tong", ["17001"]) in k.cds_doc
    assert [x[1].get("cds") for x in k.loc] == [["17001"], ["17001"]]      # chiến dịch + quảng cáo
    assert "chiến dịch “TEASER SALE, cân nhắc”" in lk.gia.dau.title
    tq = " ".join(str(o) for r in lk.gia.o("Tổng quan") for o in r)
    assert "Lọc tên chiến dịch" in tq and "1 chiến dịch khớp" in tq
    assert "tổng các chiến dịch khớp lọc tên chiến dịch" in tq
    # Không còn chữ Latin: không hỏi kho tên, mọi tab rỗng (cds = []).
    kq, k, lk = _chay(monkeypatch, {**YC, "ten_cd": "…"})
    assert not [x for x in k.cds_doc if x[0] == "ma"]
    assert ("ngay", []) in k.cds_doc and [x[1].get("cds") for x in k.loc] == [[], []]
    # Dòng cũ / không lọc: không truyền cds (như trước).
    kq, k, lk = _chay(monkeypatch, dict(YC))
    assert ("ngay", None) in k.cds_doc and all("cds" not in x[1] for x in k.loc)
    assert "chiến dịch “" not in lk.gia.dau.title


def test_tool_mark_mang_ten_cd(monkeypatch):
    assert "ten_cd" in ST.SCHEMA["parameters"]["properties"]
    ra, kho = _hoi(monkeypatch, QL, {"nen_tang": "tiktok", "ben": "hapas",
                                     "ten_cd": "  Teaser   sale "})
    (r,) = kho.rows
    assert r["ten_cd"] == "Teaser sale" and ra["pham_vi"]["ten_chien_dich"] == "Teaser sale"
    ra, kho = _hoi(monkeypatch, QL, {"nen_tang": "tiktok", "ben": "hapas"})
    assert kho.rows[0]["ten_cd"] is None and ra["pham_vi"]["ten_chien_dich"] is None
    with pytest.raises(NL.LoiNhap, match="ten_cd"):
        _hoi(monkeypatch, QL, {"ben": "hapas", "ten_cd": "x" * (QC.TIM_TOI_DA + 1)})
    assert X.loc_ten_cd({"ten_cd": None}) == {"chu": "", "maus": []}
