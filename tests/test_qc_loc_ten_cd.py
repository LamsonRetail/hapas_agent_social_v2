"""Lọc TÊN CHIẾN DỊCH cấp trang ở trang Quảng cáo (23/10/2026, MKT: "lọc tên campaign" ở Bộ lọc đầu
trang — tên kiểu "HAPAS OFFICIAL_CÂN NHẮC_DA 20/10_TEASER SALE"). Bản 2 cùng ngày (MKT, như Meta Ads
Manager): "chứa tất cả từ khoá · chứa một trong các từ khoá · không chứa bất kì từ khoá nào", AND.

Soi: `quang_cao.loc_ten_cd` (cd_co / cd_mot / cd_khong lặp lại hoặc dấu phẩy; `ten_cd` cũ = cd_mot; trần
10 từ khoá × 60 ký tự × 600 ký tự chuỗi; từ khoá không còn chữ Latin bị bỏ; co / mot bị bỏ hết = không
khớp gì) + `khop_ten_cd` (bảng chân trị); `kho_qc` đổi sang số cấp chiến dịch (qc_campaign_ngay,
campaign_id = ANY) khi có `cds`; KPI / biểu đồ / TikTok và Meta / hai bảng / kênh đăng chỉ tính chiến
dịch khớp; kỳ trước tính lại danh sách khớp của KỲ TRƯỚC; gợi ý tên /api/qc/ten-cd (phạm vi, bỏ dấu,
≤ 10, quyền); bảng chọn ba dòng + thẻ từng điều kiện + gợi ý tên gần nhất khi 0 khớp; mọi liên kết /
biểu mẫu giữ ba danh sách; Lark Sheet (nút trang, tool Mark, bộ nghe) lưu JSON / đọc chữ cũ và áp vào
mọi tab.

Không mạng, không Postgres: kho giả (`test_tiktok_ads`, `test_kenh_dang`, `test_sheet_qc`).
"""
from __future__ import annotations

import contextlib
import datetime
import html
import json
import pathlib
import re
import unittest.mock
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from test_kenh_dang import GiaKhoKenh
from test_sheet_qc import YC, GiaKhoSheet, _chay, _form
from test_sheet_qc_mark import _hoi
from test_tiktok_ads import HP_QL, QL, XEM, _co_so, _tao_app, dang_nhap

import sheet_qc_tool as ST
import xuat_sheet_qc as X
from dashboard import kho_qc as KQ
from dashboard import kho_sheet_qc as KS
from dashboard import nhap_lieu as NL
from dashboard import quang_cao as QC

GOC = pathlib.Path(__file__).resolve().parent.parent
Q = "tu=2026-10-12&den=2026-10-18"
TU, DEN = datetime.date(2026, 10, 12), datetime.date(2026, 10, 18)
TEN_A = "HAPAS OFFICIAL_CÂN NHẮC_DA 20/10_TEASER SALE"     # chiến dịch của HAPAS - KOC
TEN_B = "MM_Teaser Sale tháng 10"                          # chiến dịch của MATEMADE MKT
CD_A, CD_B, CD_C = "ca04010000", "ca53290001", "ca04160000"


# ───────────────────────────── 1. bộ đọc tham số (thuần) ─────────────────────────────
def test_loc_ten_cd_ba_danh_sach_lap_lai_va_dau_phay():
    d = QC.loc_ten_cd({})
    assert (d["co"], d["mot"], d["khong"], d["co_loc"], d["chu"]) == ([], [], [], False, "")
    assert QC.loc_ten_cd({"cd_co": "   ", "cd_mot": [" , ;"]})["co_loc"] is False
    d = QC.loc_ten_cd({"cd_co": ["LOYALTY", "  20/10 "], "cd_khong": "reach"})
    assert (d["co"], d["mot"], d["khong"]) == (["LOYALTY", "20/10"], [], ["reach"])
    assert d["maus"] == {"co": ["loyalty", "2010"], "mot": [], "khong": ["reach"]}
    assert d["chu"] == "chứa tất cả: LOYALTY, 20/10 · không chứa: reach"
    assert d["co_loc"] is True and d["khong_khop"] is False and d["cat"] is False
    # Một giá trị có dấu phẩy / chấm phẩy = nhiều từ khoá; trùng (sau bỏ dấu) bỏ, giữ chữ gõ đầu tiên.
    d = QC.loc_ten_cd({"cd_mot": ["teaser; Teaser,TEASER", "Cân nhắc", "can nhac"]})
    assert d["mot"] == ["teaser", "Cân nhắc"] and d["maus"]["mot"] == ["teaser", "cannhac"]


def test_loc_ten_cd_query_params_lap_lai():
    from starlette.datastructures import QueryParams
    d = QC.loc_ten_cd(QueryParams("cd_co=LOYALTY&cd_co=20%2F10&cd_mot=a,b&cd_khong=reach"))
    assert (d["co"], d["mot"], d["khong"]) == (["LOYALTY", "20/10"], ["a", "b"], ["reach"])


def test_loc_ten_cd_ten_cd_cu_la_mot_trong():
    """Link từ PR #101 (`ten_cd`, dấu phẩy = hoặc) vẫn chạy: gộp vào cd_mot."""
    d = QC.loc_ten_cd({"ten_cd": "  TEASER SALE,  CÂN NHẮC_DA 20/10 "})
    assert d["mot"] == ["TEASER SALE", "CÂN NHẮC_DA 20/10"] and d["co"] == d["khong"] == []
    assert d["maus"]["mot"] == ["teasersale", "cannhacda2010"]
    assert QC.loc_ten_cd({"ten_cd": "a", "cd_mot": "b"})["mot"] == ["b", "a"]
    # Khớp tên mẫu của MKT dù gõ không dấu / khác hoa thường / khác ký hiệu.
    for go in ("teaser sale", "can nhac_da 20/10", "Cân Nhắc DA 2010", "hapas official"):
        assert QC.khop_ten_cd(TEN_A, QC.loc_ten_cd({"ten_cd": go})), go


def test_loc_ten_cd_tran_cat_lang():
    d = QC.loc_ten_cd({"cd_co": [f"k{i}" for i in range(15)]})
    assert d["co"] == [f"k{i}" for i in range(QC.TU_KHOA_TOI_DA)] and d["cat"] is True
    d = QC.loc_ten_cd({"cd_mot": "x" * 200})
    assert d["mot"] == ["x" * QC.TU_KHOA_DAI_TOI_DA] and d["cat"] is True
    # Tổng chuỗi JSON ≤ 600: bớt từ "không chứa" trước, rồi "một trong", rồi "tất cả".
    dai = {k: [f"{k}{i:02d}" + "y" * 50 for i in range(10)] for k in ("cd_co", "cd_mot", "cd_khong")}
    d = QC.loc_ten_cd(dai)
    assert len(QC.chuoi_ten_cd(d)) <= QC.TEN_CD_CHUOI_TOI_DA and d["cat"] is True
    assert d["khong"] == [] and d["mot"] == [] and d["co"] == dai["cd_co"][:9]
    assert QC.loc_ten_cd({"cd_co": ["a", "b"]})["cat"] is False


def test_loc_ten_cd_khong_latin():
    # Từ khoá không còn chữ/số Latin: bỏ khi so khớp (vẫn hiện như người gõ).
    d = QC.loc_ten_cd({"cd_mot": "ภาษาไทย, teaser"})
    assert d["mot"] == ["ภาษาไทย", "teaser"] and d["maus"]["mot"] == ["teaser"]
    assert d["khong_khop"] is False
    # co / mot có từ khoá mà mọi từ bị bỏ → không khớp gì (cùng luật `tim`).
    for k in ("cd_co", "cd_mot", "ten_cd"):
        d = QC.loc_ten_cd({k: "…, ภาษาไทย"})
        assert d["co_loc"] is True and d["khong_khop"] is True, k
        assert not QC.khop_ten_cd(TEN_A, d)
    # khong bị bỏ hết: chỉ là không ràng buộc.
    d = QC.loc_ten_cd({"cd_khong": "…"})
    assert d["co_loc"] is True and d["khong_khop"] is False and QC.khop_ten_cd(TEN_A, d)


def test_khop_ten_cd_bang_chan_tri():
    def k(ten, **kw):
        return QC.khop_ten_cd(ten, QC.loc_ten_cd({f"cd_{a}": v for a, v in kw.items()}))
    ten = "HAPAS_LOYALTY 20/10_CONVERSION"
    assert k(ten, co=["loyalty", "2010"]) and not k(ten, co=["loyalty", "reach"])
    assert k(ten, mot=["reach", "loyalty"]) and not k(ten, mot=["reach", "teaser"])
    assert k(ten, khong=["reach"]) and not k(ten, khong=["reach", "conversion"])
    assert k(ten, co=["loyalty"], mot=["conversion", "reach"], khong=["teaser"])
    assert not k(ten, co=["loyalty"], mot=["reach"], khong=["teaser"])
    assert not k(ten, co=["loyalty"], mot=["conversion"], khong=["hapas"])
    assert not k(ten, co=["teaser"], mot=["conversion"])
    # Bỏ dấu, khoảng trắng, _ và / (gõ "20 10" vẫn khớp "20/10"); tên rỗng chỉ khớp "không chứa".
    assert k("CÂN NHẮC_DA 20/10", co=["can nhac da", "20 10"])
    assert k(None, khong=["x"]) and not k(None, co=["x"]) and not k("", mot=["x"])
    # Không điều kiện: mọi tên khớp.
    assert QC.khop_ten_cd("bất kỳ", QC.loc_ten_cd({}))


def test_chuoi_json_khu_hoi_va_chu_cu():
    d = QC.loc_ten_cd({"cd_co": ["LOYALTY", "20/10"], "cd_khong": "reach \"x\""})
    s = QC.chuoi_ten_cd(d)
    assert s == '{"co":["LOYALTY","20/10"],"mot":[],"khong":["reach \\"x\\""]}'
    d2 = QC.loc_ten_cd(QC.doc_ten_cd(s))
    assert (d2["co"], d2["mot"], d2["khong"]) == (d["co"], d["mot"], d["khong"])
    assert QC.chuoi_ten_cd(QC.loc_ten_cd({})) is None
    # Dòng cũ: chữ thường (dấu phẩy = hoặc) → "chứa một trong".
    assert QC.doc_ten_cd("TEASER SALE, cân nhắc") == {"ten_cd": "TEASER SALE, cân nhắc"}
    assert QC.loc_ten_cd(QC.doc_ten_cd("TEASER, sale"))["mot"] == ["TEASER", "sale"]
    assert QC.loc_ten_cd(QC.doc_ten_cd(None))["co_loc"] is False
    # JSON hỏng / lạ → coi như chữ cũ, không ném; khoá thiếu / sai kiểu bỏ qua.
    assert QC.doc_ten_cd("{hỏng") == {"ten_cd": "{hỏng"}
    la = QC.loc_ten_cd(QC.doc_ten_cd('{"co":"a","mot":[1,{"x":1}],"khong":null}'))
    assert (la["co"], la["mot"], la["khong"]) == (["a"], ["1"], [])


def test_goi_y_ten_va_ten_gan_nhat():
    ds = [{"ten": "MM_Teaser Sale tháng 10"}, {"ten": TEN_A}, {"ten": "MM_Teaser Sale tháng 10"},
          {"ten": "HAPAS_Reach_10/10"}, {"ten": None}]
    g = QC.goi_y_ten_cd(ds, "teaser")
    assert g["ten"] == ["MM_Teaser Sale tháng 10", TEN_A]               # mới nhất trước, không trùng
    assert "TEASER SALE" in g["tu_khoa"]                                  # đoạn tên tách theo _
    assert QC.goi_y_ten_cd(ds, "TÉASER")["ten"] == g["ten"]              # bỏ dấu
    assert QC.goi_y_ten_cd(ds, "…") == {"q": "…", "ten": [], "tu_khoa": []}
    nhieu = [{"ten": f"Teaser {i}"} for i in range(30)]
    assert len(QC.goi_y_ten_cd(nhieu, "teaser")["ten"]) == 10
    # Tên gần nhất: chứa nhiều từ khoá nhất, rồi nhiều chữ lẻ; bỏ tên chứa từ "không chứa".
    loc = QC.loc_ten_cd({"cd_co": ["teaser sale 21/10"], "cd_khong": "mm"})
    assert QC.ten_gan_nhat(ds, loc) == [TEN_A, "HAPAS_Reach_10/10"]
    loc = QC.loc_ten_cd({"cd_mot": ["hapas reach"]})
    assert QC.ten_gan_nhat(ds, loc)[0] == "HAPAS_Reach_10/10"
    assert QC.ten_gan_nhat(ds, QC.loc_ten_cd({"cd_co": "zzz"})) == []


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


def test_sql_ma_cd_theo_ten_khop_o_python_ba_dieu_kien():
    def tra(sql, ts):
        return [{"campaign_id": k, "ten": t} for k, t in
                (("c1", TEN_A), ("c2", TEN_B), ("c3", "Chiến dịch khác"), ("c4", None))]
    goi, kn = _bat(tra)
    L = QC.loc_ten_cd
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        assert KQ.ma_cd_theo_ten(["1"], TU, DEN, L({"cd_mot": "teasersale"})) == ["c1", "c2"]
        assert KQ.ma_cd_theo_ten(["1"], TU, DEN, L({"cd_mot": "cannhac, khac"})) == ["c1", "c3"]
        assert KQ.ma_cd_theo_ten(["1"], TU, DEN, L({"cd_co": "teaser",
                                                    "cd_khong": "hapas"})) == ["c2"]
        assert KQ.ma_cd_theo_ten(["1"], TU, DEN, L({"cd_khong": "teaser"})) == ["c3", "c4"]
        assert KQ.ma_cd_theo_ten(["1"], TU, DEN, L({})) == []
        assert KQ.ma_cd_theo_ten(["1"], TU, DEN, L({"cd_co": "…"})) == []
        assert KQ.ma_cd_theo_ten([], TU, DEN, L({"cd_mot": "x"})) == []
    assert len(goi) == 4                       # không điều kiện / không khớp chắc / ids rỗng: không hỏi
    sql, ts = goi[0]
    assert sql == KQ.sql_ten_bang("campaign", cd=False) and ts == [["1"], TU, DEN]
    assert "DISTINCT ON (campaign_id)" in sql and "ORDER BY campaign_id, ngay DESC" in sql


def test_sql_ten_cd_trong_ky_moi_nhat_truoc():
    d1, d2 = datetime.date(2026, 10, 13), datetime.date(2026, 10, 17)
    goi, kn = _bat(lambda sql, ts: [{"campaign_id": "c1", "ten": "A", "ngay": d1},
                                    {"campaign_id": "c2", "ten": "B", "ngay": d2},
                                    {"campaign_id": "c0", "ten": "C", "ngay": d2}])
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        assert [r["campaign_id"] for r in KQ.ten_cd_trong_ky(["1"], TU, DEN)] == ["c0", "c2", "c1"]
        assert KQ.ten_cd_trong_ky([], TU, DEN) == []
    assert goi == [(KQ.SQL_TEN_CD_KY, [["1"], TU, DEN])]
    assert KQ.SQL_TEN_CD_KY.count("%s") == 3 and "FROM qc_campaign_ngay" in KQ.SQL_TEN_CD_KY


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
    # Bộ nghe: đúng hàm khớp của trang; chắc chắn không khớp thì không hỏi.
    KS.ma_cd_theo_ten(["1"], TU, DEN, QC.loc_ten_cd({"cd_co": "x"}))
    assert KS.ma_cd_theo_ten(["1"], TU, DEN, QC.loc_ten_cd({"cd_co": "…"})) == []
    cau = [g for g in goi if not g[0].startswith("SET LOCAL")]
    assert len(cau) == 4
    for sql, ts in cau[:3]:
        assert sql.count("%s") == len(ts), sql
        assert "campaign_id = ANY(%s)" in sql and ["c1"] in ts
    assert "FROM qc_campaign_ngay" in cau[0][0] and "GROUP BY advertiser_id, ngay" in cau[0][0]
    assert "FROM qc_campaign_ngay q JOIN tk_quang_cao" in cau[1][0]
    assert cau[2][0] == KQ.sql_bang("ad", "chi", False, loc_ma=False, cd=False, them=KS._SO_NGAY,
                                    bo_qua=False, cds=True)
    assert cau[3][0] == KQ.sql_ten_bang("campaign", cd=False)


# ───────────────────────────── 3. API (kho giả) ─────────────────────────────
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


def _u(duong: str, kw) -> str:
    """URL có Q + tham số (params= của httpx THAY chuỗi truy vấn sẵn có, nên ghép tay)."""
    return f"{duong}?{Q}&{urlencode(kw, doseq=True)}"


def test_api_kpi_bieu_do_bang_chi_tinh_chien_dich_khop():
    _app, c, kq = _ve()
    tat = c.get(f"/api/qc?{Q}").json()
    assert tat["ten_cd"] is None
    d = c.get(_u("/api/qc", {"cd_mot": "teaser sale"})).json()
    assert d["ten_cd"]["so_chien_dich"] == 2 and d["ten_cd"]["so_chien_dich_truoc"] == 1
    assert d["ten_cd"]["mot"] == ["teaser sale"] and d["ten_cd"]["chu"] == "chứa một trong: teaser sale"
    assert d["ten_cd"]["goi_y"] == [] and d["ten_cd"]["so_dieu_kien"] == 1
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
    x = c.get(_u("/api/qc", {"cd_mot": "teaser sale", "tim": "hapas official"})).json()
    assert [r["campaign_id"] for r in x["campaign"]] == [CD_A] and x["kpi"] == d["kpi"]
    x = c.get(_u("/api/qc", {"cd_mot": "teaser sale", "cd": CD_B})).json()
    assert [r["campaign_id"] for r in x["campaign"]] == [CD_B]
    assert x["ad"] and all(r["campaign_id"] == CD_B for r in x["ad"])
    # Ba dòng AND: chứa tất cả + không chứa.
    x = c.get(_u("/api/qc", {"cd_co": ["teaser", "sale"], "cd_khong": "hapas"})).json()
    assert [r["campaign_id"] for r in x["campaign"]] == [CD_B]
    assert x["kpi"]["hien_thi"] == _tong_cd(kq, {CD_B}) and x["ten_cd"]["so_dieu_kien"] == 2
    x = c.get(_u("/api/qc", {"cd_khong": "chien dich"})).json()          # bỏ dấu: "Chiến dịch …"
    assert {r["campaign_id"] for r in x["campaign"]} == {CD_A, CD_B}
    # `ten_cd` cũ (PR #101) = chứa một trong; HOẶC giữa các cụm; không dấu vẫn khớp.
    x = c.get(_u("/api/qc", {"ten_cd": "can nhac_da 20/10; MM_TEASER"})).json()
    assert x["ten_cd"]["so_chien_dich"] == 2
    assert x["ten_cd"]["mot"] == ["can nhac_da 20/10", "MM_TEASER"]
    x = c.get(_u("/api/qc", {"ten_cd": "Cân nhắc"})).json()
    assert x["ten_cd"]["so_chien_dich"] == 1 and x["kpi"]["hien_thi"] == _tong_cd(kq, {CD_A})


def test_api_ky_truoc_tinh_lai_danh_sach_khop():
    _app, c, kq = _ve()
    goi = []
    goc = kq.ma_cd_theo_ten

    def ghi(ids, tu, den, loc):
        goi.append((tu, den, tuple(loc["maus"]["co"]), tuple(loc["maus"]["khong"])))
        return goc(ids, tu, den, loc)
    kq.ma_cd_theo_ten = ghi
    d = c.get(_u("/api/qc", {"cd_co": "teaser sale", "cd_khong": "mm"})).json()
    t0, t1 = QC.khoang_truoc(TU, DEN)
    assert goi == [(TU, DEN, ("teasersale",), ("mm",)), (t0, t1, ("teasersale",), ("mm",))]
    # Kỳ trước = chiến dịch "teaser" CỦA KỲ TRƯỚC (C), không phải A/B của kỳ này.
    assert d["kpi_truoc"]["hien_thi"] == 777 * 7
    assert d["doi"]["hien_thi"] == QC.doi_pt(d["kpi"]["hien_thi"], 777 * 7)
    # Không lọc: kỳ trước đọc qc_tk_ngay (không có số ngày 05–11/10).
    assert c.get(f"/api/qc?{Q}").json()["kpi_truoc"]["hien_thi"] is None


def test_api_chu_khong_latin_khong_khop_gi():
    _app, c, kq = _ve()
    for kw in ({"cd_mot": "…"}, {"ten_cd": "ภาษาไทย"}, {"cd_co": "-, ;"},
               {"cd_co": "…", "cd_mot": "teaser"}):
        d = c.get(_u("/api/qc", kw)).json()
        assert d["ten_cd"]["so_chien_dich"] == 0, kw
        assert d["kpi"]["hien_thi"] is None and d["campaign"] == [] and d["ad"] == []
        assert sum(x["hien_thi"] for x in d["theo_ngay"]) == 0
        assert d["bang"]["tong_ad"] == 0 and d["theo_ngay_nen_tang"] == []
    # Từ khoá Latin còn lại vẫn dùng; "không chứa" chỉ toàn chữ không Latin = không ràng buộc.
    d = c.get(_u("/api/qc", {"cd_mot": "ภาษาไทย, teaser sale"})).json()
    assert d["ten_cd"]["so_chien_dich"] == 2
    d = c.get(_u("/api/qc", {"cd_mot": "teaser sale", "cd_khong": "ภาษาไทย"})).json()
    assert d["ten_cd"]["so_chien_dich"] == 2


def test_api_khong_khop_goi_y_ten_gan_nhat():
    _app, c, kq = _ve()
    d = c.get(_u("/api/qc", {"cd_co": "TEASER SALE 21/10"})).json()
    assert d["ten_cd"]["so_chien_dich"] == 0
    assert d["ten_cd"]["goi_y"][:2] == [TEN_A, TEN_B] and len(d["ten_cd"]["goi_y"]) <= 5
    # Có chiến dịch khớp: không tính gợi ý.
    assert c.get(_u("/api/qc", {"cd_co": "teaser"})).json()["ten_cd"]["goi_y"] == []


def test_api_khong_xem_tien_van_loc_tien_khi_co_ten_cd():
    """Chốt chặn tiền không đổi: khối ten_cd không mang khoá tiền; loc_tien vẫn chạy cuối."""
    tcd = {"chu": "x", "co": ["x"], "mot": [], "khong": [], "so_chien_dich": 2,
           "so_chien_dich_truoc": 0, "goi_y": []}
    d = QC.loc_tien({"ten_cd": tcd, "kpi": {"chi": 1, "hien_thi": 2}}, False)
    assert d == {"ten_cd": tcd, "kpi": {"hien_thi": 2}}


def test_kenh_dang_nhan_cds():
    _app, c, kq = _ve(GiaKhoKenh())
    c.get(f"/api/qc?{Q}").json()
    assert kq.cds_kenh is None                              # không lọc: không truyền
    d = c.get(_u("/api/qc", {"cd_mot": "teaser sale"})).json()
    assert sorted(kq.cds_kenh) == [CD_A, CD_B] and d["kenh"] is not None
    c.get(_u("/api/qc", {"cd_co": "…"})).json()
    assert kq.cds_kenh == []


# ───────────────────────────── 4. gợi ý tên /api/qc/ten-cd ─────────────────────────────
def test_api_goi_y_ten_cd_pham_vi_bo_dau_tran():
    _app, c, kq = _ve()
    # A chạy tới 15/10, B tới 18/10 → B (mới hơn) trước.
    for d in (16, 17, 18):
        kq.bang["qc_campaign_ngay"].pop((CD_A, datetime.date(2026, 10, d)), None)
    r = c.get(_u("/api/qc/ten-cd", {"q": "TÉASER"}))
    assert r.status_code == 200
    p = r.json()
    assert p["ten"] == [TEN_B, TEN_A] and p["q"] == "TÉASER"
    assert p["tu_khoa"] and all("teaser" in QC.chu_tim(x) for x in p["tu_khoa"])
    # Cùng phạm vi trang: bên / tài khoản / kỳ.
    assert c.get(_u("/api/qc/ten-cd", {"q": "teaser", "ben": "hapas"})).json()["ten"] == [TEN_A]
    assert c.get(_u("/api/qc/ten-cd", {"q": "teaser", "ben": "matemade"})).json()["ten"] == [TEN_B]
    cu = c.get("/api/qc/ten-cd?tu=2026-10-05&den=2026-10-11&q=teaser").json()
    assert cu["ten"] == ["Teaser sale cũ"]
    assert c.get(_u("/api/qc/ten-cd", {"q": "teaser", "ben": "khongco"})).status_code == 404
    assert c.get(_u("/api/qc/ten-cd", {"q": "teaser", "tk": "999"})).status_code == 404
    assert c.get(_u("/api/qc/ten-cd", {"q": "x", "nen_tang": "zalo"})).status_code == 400
    # q rỗng / không Latin: không hỏi kho.
    kq.goi_ten_ky = []
    assert c.get(_u("/api/qc/ten-cd", {"q": "…"})).json() == {"q": "…", "ten": [], "tu_khoa": []}
    assert c.get(f"/api/qc/ten-cd?{Q}").json()["ten"] == [] and kq.goi_ten_ky == []
    # ≤ 10 tên.
    mau = next(iter(kq.bang["qc_campaign_ngay"].values()))
    for i in range(15):
        kq.bang["qc_campaign_ngay"][(f"cz{i:02d}", TU)] = {**mau, "campaign_id": f"cz{i:02d}",
                                                          "ngay": TU, "ten": f"Teaser {i}"}
    assert len(c.get(_u("/api/qc/ten-cd", {"q": "teaser"})).json()["ten"]) == 10


def test_api_goi_y_ten_cd_chi_quan_tri_vien():
    _app, c, kq = _ve()
    for ai in (XEM, HP_QL):
        dang_nhap(c, ai)
        assert c.get(_u("/api/qc/ten-cd", {"q": "teaser"})).status_code == 404, ai
    c.cookies.clear()
    r = c.get(_u("/api/qc/ten-cd", {"q": "teaser"}), follow_redirects=False)
    assert r.status_code in (302, 303, 401, 404)


def test_api_goi_y_ten_cd_ban_tra_503():
    app, c, kq = _ve()
    giu = 0
    while app.state.ban.acquire(blocking=False):
        giu += 1
    try:
        assert c.get(_u("/api/qc/ten-cd", {"q": "teaser"})).status_code == 503
    finally:
        for _ in range(giu):
            app.state.ban.release()
    assert c.get(_u("/api/qc/ten-cd", {"q": "teaser"})).status_code == 200


# ───────────────────────────── 5. trang ─────────────────────────────
def _href(t: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(r'href="([^"]+)"', t)]


def _tham(h: str) -> dict:
    return parse_qs(urlsplit(h).query)


def test_trang_bang_chon_ba_dong_va_tom_tat():
    _app, c, kq = _ve(GiaKhoKenh())
    t = c.get(_u("/quang-cao", {"cd_co": ["LOYALTY", "20/10"], "cd_khong": "reach"})).text
    loc = t.split('id="qc-loc"')[1].split("</form>")[0]
    o = loc.split('data-o="loc-ten-cd"')[1]
    # Ô gọn + tóm tắt "2 điều kiện"; ba dòng đúng nhãn; không JS: ô chữ dấu phẩy, đúng tên tham số.
    assert 'id="qc-tcd-gia-tri" data-trong="Mọi chiến dịch">2 điều kiện</span>' in o
    for nhan, ts, gt in (("Chứa tất cả từ khoá", "cd_co", "LOYALTY, 20/10"),
                         ("Chứa một trong các từ khoá", "cd_mot", ""),
                         ("Không chứa từ khoá nào", "cd_khong", "reach")):
        dong = o.split(f'data-tcd="{ts}"')[1].split("data-tcd=")[0]
        assert nhan in dong and f'name="{ts}" value="{gt}"' in dong, ts
        assert 'placeholder="Nhập tên hoặc từ khoá"' in dong
    assert ">Áp dụng</button>" in o and "data-tcd-xoa>Xoá điều kiện</a>" in o
    xoa = _tham(_href(o.split("data-tcd-xoa")[0])[-1])
    assert not {"cd_co", "cd_mot", "cd_khong", "ten_cd"} & set(xoa) and xoa["tu"] == ["2026-10-12"]
    # (i) giải thích: không cần dấu, bỏ khoảng trắng / _ / /, AND, trần.
    gy = html.unescape(re.search(r'data-goi-y="([^"]+)"', o).group(1))
    for chu in ("không cần gõ dấu", "khoảng trắng, dấu _ và /", "bằng VÀ", "Tối đa 10 từ khoá",
                "60 ký tự", "KHÔNG áp vào Khán giả"):
        assert chu in gy, chu
    tom = t.split('class="qc-loc-khung__gia-tri"')[1].split("</span>")[0]
    assert "· chứa tất cả: LOYALTY, 20/10 · không chứa: reach" in tom
    # Không lọc: "Mọi chiến dịch", ô trống, không thẻ, không ghi chú Khán giả.
    t = c.get(f"/quang-cao?{Q}").text
    assert 'data-trong="Mọi chiến dịch">Mọi chiến dịch</span>' in t
    assert 'name="cd_co" value=""' in t and 'data-o="the-ten-cd"' not in t
    assert 'data-o="kg-khong-loc-cd"' not in t


def test_trang_the_tung_dieu_kien_va_lien_ket_giu_loc():
    _app, c, kq = _ve(GiaKhoKenh())
    t = c.get(_u("/quang-cao", {"cd_co": ["teaser", "sale"], "cd_khong": "hapas"})).text
    the = t.split('data-o="the-ten-cd"')[1].split("</div>")[0]
    assert t.index('data-o="the-ten-cd"') < t.index('id="qc-kpi"')
    assert "Chứa tất cả: <b>teaser, sale</b>" in the and "Không chứa: <b>hapas</b>" in the
    assert 'data-tcd-the="mot"' not in the
    assert "1 chiến dịch" in the and "(kỳ trước 1)" in the
    # ✕ của MỖI điều kiện chỉ bỏ điều kiện đó (giữ mọi bộ lọc khác); "Bỏ lọc tên" bỏ cả ba.
    bo_co = _tham(_href(the.split('data-tcd-the="co"')[1])[0])
    assert "cd_co" not in bo_co and bo_co["cd_khong"] == ["hapas"] and bo_co["tu"] == ["2026-10-12"]
    bo_khong = _tham(_href(the.split('data-tcd-the="khong"')[1])[0])
    assert bo_khong["cd_co"] == ["teaser", "sale"] and "cd_khong" not in bo_khong
    het = _href(the.split("qc-tcd-the__bo-het")[1])[0]
    assert not {"cd_co", "cd_mot", "cd_khong", "ten_cd"} & set(_tham(het)) and "tu=2026-10-12" in het
    # Khoảng nhanh, xếp cột, lọc chiến dịch: mọi liên kết giữ ba danh sách (tham số lặp lại).
    ds = (_href(t.split('aria-label="Khoảng nhanh"')[1].split("</nav>")[0])
          + [html.unescape(h) for h in re.findall(r'class="qc-sap[^"]*" href="([^"]+)"', t)]
          + [html.unescape(h) for h in re.findall(r'class="qc-bang__loc" href="([^"]+)"', t)])
    assert len(ds) > 3
    for h in ds:
        q = _tham(h)
        assert q["cd_co"] == ["teaser", "sale"] and q["cd_khong"] == ["hapas"], h
        assert "ten_cd" not in q
    # Biểu mẫu bảng, kênh, Xuất Sheet: ô ẩn lặp lại.
    an = ('<input type="hidden" name="cd_co" value="teaser"><input type="hidden" name="cd_co" '
          'value="sale"><input type="hidden" name="cd_khong" value="hapas">')
    for dau in ('data-o="loc-bang"', 'class="qc-bang-loc qc-kenh-loc"', 'data-o="tao-sheet"'):
        assert an in t.split(dau)[1].split("</form>")[0], dau
    assert "Tên chiến dịch chứa tất cả: teaser, sale · không chứa: hapas" in t.split('id="sheet"')[1]
    assert 'data-o="kg-khong-loc-cd"' in t
    # Link cũ `ten_cd` → thẻ "chứa một trong", liên kết đổi sang cd_mot.
    t = c.get(_u("/quang-cao", {"ten_cd": "teaser sale"})).text
    assert "Chứa một trong: <b>teaser sale</b>" in t
    nhanh = _href(t.split('aria-label="Khoảng nhanh"')[1].split("</nav>")[0])
    assert all(_tham(h)["cd_mot"] == ["teaser sale"] and "ten_cd" not in _tham(h) for h in nhanh)


def test_trang_rong_khi_khong_chien_dich_nao_khop_goi_y_ten():
    _app, c, kq = _ve()
    t = c.get(_u("/quang-cao", {"cd_co": "teaser sale 21/10", "cd_khong": "mm"})).text
    rong = t.split('data-o="ten-cd-trong"')[1].split("</div>")[0]
    assert ("Không có chiến dịch nào có tên khớp (chứa tất cả: teaser sale 21/10 · không chứa: mm)"
            in rong)
    assert 'id="qc-kpi"' not in t and "0 chiến dịch" in t.split('data-o="the-ten-cd"')[1]
    ds = rong.split('data-o="ten-cd-goi-y"')[1]
    assert f">{TEN_A}</a>" in ds and "MM_Teaser" not in ds          # bỏ tên chứa "mm"
    assert ds.count("<li>") <= 5
    h = _tham(_href(ds)[0])
    assert h["cd_mot"] == [TEN_A] and not {"cd_co", "cd_khong", "ten_cd"} & set(h)
    # Không tên nào chung chữ: không có danh sách gợi ý; chữ không Latin: vẫn trạng thái rỗng.
    t = c.get(_u("/quang-cao", {"cd_co": "zzzz"})).text
    assert 'data-o="ten-cd-trong"' in t and 'data-o="ten-cd-goi-y"' not in t
    t = c.get(_u("/quang-cao", {"cd_mot": "…"})).text
    assert "Không có chiến dịch nào có tên khớp (chứa một trong: …)" in t


def test_trang_goi_y_ten_co_dau_phay_thanh_chua_tat_ca():
    _app, c, kq = _ve()
    for (cid, _ng), r in kq.bang["qc_campaign_ngay"].items():
        if cid == CD_A:
            r["ten"] = "HAPAS, TEASER; 21"
    t = c.get(_u("/quang-cao", {"cd_co": "hapas teaser 22"})).text
    h = _tham(_href(t.split('data-o="ten-cd-goi-y"')[1])[0])
    assert h["cd_co"] == ["HAPAS", " TEASER", " 21"] and "cd_mot" not in h


def test_js_css_o_the_va_dien_thoai():
    js = (GOC / "dashboard" / "static" / "qc.js").read_text(encoding="utf-8")
    css = (GOC / "dashboard" / "static" / "qc.css").read_text(encoding="utf-8")
    khoi = js.split('[data-o="loc-ten-cd"]')[1]
    for chu in ("/api/qc/ten-cd?", "setTimeout(hoi, 250)", '"Backspace"', "/[,;]/",
                'an.type = "hidden"', 'go.removeAttribute("name")', "textContent",
                "aria-activedescendant"):
        assert chu in khoi, chu
    assert "innerHTML" not in khoi
    dt = css.split("@media (max-width: 640px)")[1].split("\n}\n")[0]
    assert ".qc-tcd__bang { width: auto; }" in dt and "min-height: 44px" in dt


# ───────────────────────────── 6. Lark Sheet ─────────────────────────────
def test_nut_sheet_ghi_json_ba_danh_sach():
    app, c, _kho, kq, tt, dv = _co_so(_tao_app())
    app.state.kho_sheet = ks = GiaKhoSheet()
    csrf = dang_nhap(c, QL)
    body = urlencode([*_form(csrf).items(), ("cd_co", "LOYALTY"), ("cd_co", "20/10"),
                      ("cd_khong", " reach ")])
    r = c.post("/quang-cao/tao-sheet", content=body.encode(),
               headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 303
    assert _tham(r.headers["location"])["cd_co"] == ["LOYALTY", "20/10"]
    s = ks.rows[0]["ten_cd"]
    assert s == '{"co":["LOYALTY","20/10"],"mot":[],"khong":["reach"]}'
    assert len(s) <= QC.TEN_CD_CHUOI_TOI_DA
    t = c.get(f"/quang-cao?{Q}").text
    assert ("tên chiến dịch chứa tất cả: LOYALTY, 20/10 · không chứa: reach"
            in t.split('id="sheet"')[1])
    # Chữ cũ `ten_cd` (form cũ còn mở) vẫn ghi được — thành "một trong".
    ks.rows.clear()
    c.post("/quang-cao/tao-sheet", data=_form(csrf, ten_cd="  TEASER SALE,  CÂN NHẮC "))
    assert json.loads(ks.rows[0]["ten_cd"]) == {"co": [], "mot": ["TEASER SALE", "CÂN NHẮC"],
                                                "khong": []}
    ks.rows.clear()
    c.post("/quang-cao/tao-sheet", data=_form(csrf))
    assert ks.rows[0]["ten_cd"] is None
    # Dòng cũ lưu chữ thường: danh sách Sheet gần đây vẫn đọc được.
    ks.rows[0]["ten_cd"] = "TEASER SALE"
    t = c.get(f"/quang-cao?{Q}").text
    assert "tên chiến dịch chứa một trong: TEASER SALE" in t.split('id="sheet"')[1]


def test_schema_trigger_tran_600_va_comment():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    chuan = sql[sql.index("CREATE OR REPLACE FUNCTION chuan_yeu_cau_sheet_qc()"):]
    chuan = chuan[:chuan.index("END $fn$;")]
    assert f"length(NEW.ten_cd) > {QC.TEN_CD_CHUOI_TOI_DA}" in chuan
    assert "length(NEW.ten_cd) > 100" not in chuan and QC.TEN_CD_CHUOI_TOI_DA == 600
    # Cột vẫn TEXT (không ALTER TYPE), COMMENT nói JSON + dòng cũ.
    assert "ALTER TABLE yeu_cau_sheet_qc ADD COLUMN IF NOT EXISTS ten_cd TEXT;" in sql
    assert "ALTER COLUMN ten_cd" not in sql
    cm = re.search(r"COMMENT ON COLUMN yeu_cau_sheet_qc\.ten_cd IS '([^']*)';", sql).group(1)
    assert '{"co":[..],"mot":[..],"khong":[..]}' in cm and "≤ 600 ký tự" in cm and "Dòng cũ" in cm


def test_bo_nghe_ap_ba_dieu_kien_moi_tab(monkeypatch):
    s = QC.chuoi_ten_cd(QC.loc_ten_cd({"cd_co": ["TEASER", "sale"], "cd_mot": "cân nhắc, 20/10",
                                       "cd_khong": "reach"}))
    kq, k, lk = _chay(monkeypatch, {**YC, "ten_cd": s})
    assert kq["trang_thai"] == "xong"
    assert ("ma", (("teaser", "sale"), ("cannhac", "2010"), ("reach",))) in k.cds_doc
    assert ("ngay", ["17001"]) in k.cds_doc and ("tong", ["17001"]) in k.cds_doc
    assert [x[1].get("cds") for x in k.loc] == [["17001"], ["17001"]]      # chiến dịch + quảng cáo
    tieu = lk.gia.dau.title
    assert "chiến dịch chứa tất cả: TEASER, sale · chứa một trong: cân nhắc, 20/10" in tieu
    tq = " ".join(str(o) for r in lk.gia.o("Tổng quan") for o in r)
    assert "Lọc tên chiến dịch" in tq and "1 chiến dịch khớp" in tq
    assert "không chứa: reach" in tq and "kết hợp bằng VÀ" in tq
    assert "tổng các chiến dịch khớp lọc tên chiến dịch" in tq
    # Dòng cũ chữ thường (PR #101) = "chứa một trong".
    kq, k, lk = _chay(monkeypatch, {**YC, "ten_cd": "TEASER SALE, cân nhắc"})
    assert ("ma", ((), ("teasersale", "cannhac"), ())) in k.cds_doc
    assert "chứa một trong: TEASER SALE, cân nhắc" in lk.gia.dau.title
    # Không còn chữ Latin ở "tất cả": không hỏi kho tên, mọi tab rỗng (cds = []).
    kq, k, lk = _chay(monkeypatch, {**YC, "ten_cd": '{"co":["…"],"mot":[],"khong":[]}'})
    assert not [x for x in k.cds_doc if x[0] == "ma"]
    assert ("ngay", []) in k.cds_doc and [x[1].get("cds") for x in k.loc] == [[], []]
    # Dòng cũ / không lọc: không truyền cds (như trước).
    kq, k, lk = _chay(monkeypatch, dict(YC))
    assert ("ngay", None) in k.cds_doc and all("cds" not in x[1] for x in k.loc)
    assert "chiến dịch chứa" not in lk.gia.dau.title
    assert X.loc_ten_cd({"ten_cd": None})["co_loc"] is False


def test_tool_mark_ba_danh_sach_va_ten_cd_cu(monkeypatch):
    p = ST.SCHEMA["parameters"]["properties"]
    for k in ("ten_cd_co", "ten_cd_mot", "ten_cd_khong"):
        assert p[k]["type"] == "array" and p[k]["items"] == {"type": "string"}, k
    assert "ten_cd" in p and "ten_cd_mot" in p["ten_cd"]["description"]
    ra, kho = _hoi(monkeypatch, QL, {"nen_tang": "tiktok", "ben": "hapas",
                                     "ten_cd_co": ["LOYALTY", " 20/10 "], "ten_cd_khong": ["reach"]})
    (r,) = kho.rows
    assert json.loads(r["ten_cd"]) == {"co": ["LOYALTY", "20/10"], "mot": [], "khong": ["reach"]}
    assert ra["pham_vi"]["ten_chien_dich"] == "chứa tất cả: LOYALTY, 20/10 · không chứa: reach"
    assert ra["pham_vi"]["loc_ten_chien_dich"] == {"chua_tat_ca": ["LOYALTY", "20/10"],
                                                   "chua_mot_trong": [], "khong_chua": ["reach"]}
    # `ten_cd` cũ = một trong (gộp với ten_cd_mot).
    ra, kho = _hoi(monkeypatch, QL, {"nen_tang": "tiktok", "ben": "hapas",
                                     "ten_cd": "  Teaser   sale ", "ten_cd_mot": ["MM"]})
    assert json.loads(kho.rows[0]["ten_cd"])["mot"] == ["MM", "Teaser sale"]
    ra, kho = _hoi(monkeypatch, QL, {"nen_tang": "tiktok", "ben": "hapas"})
    assert kho.rows[0]["ten_cd"] is None and ra["pham_vi"]["ten_chien_dich"] is None
    assert ra["pham_vi"]["loc_ten_chien_dich"] is None
    # Vượt trần → báo lại (không âm thầm cắt điều kiện người hỏi nêu); sai kiểu → báo.
    with pytest.raises(NL.LoiNhap, match="ten_cd"):
        _hoi(monkeypatch, QL, {"ben": "hapas", "ten_cd": "x" * (QC.TIM_TOI_DA + 1)})
    with pytest.raises(NL.LoiNhap, match="tối đa 10 từ khoá"):
        _hoi(monkeypatch, QL, {"ben": "hapas", "ten_cd_co": [f"k{i}" for i in range(11)]})
    with pytest.raises(NL.LoiNhap, match="60 ký tự"):
        _hoi(monkeypatch, QL, {"ben": "hapas", "ten_cd_khong": ["y" * 61]})
    with pytest.raises(NL.LoiNhap, match="danh sách chữ"):
        _hoi(monkeypatch, QL, {"ben": "hapas", "ten_cd_mot": [{"a": 1}]})
    # Luật dùng khi nào nằm ở tầng lời dặn (skill), không ở mô tả tool.
    skill = (GOC / "skills" / "hoi-dashboard-lang-nghe.md").read_text(encoding="utf-8")
    assert "ten_cd_co" in skill and "ten_cd_khong" in skill
