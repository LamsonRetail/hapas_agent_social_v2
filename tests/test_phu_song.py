"""Độ phủ của tìm theo từ khoá (17/10/2026): Threads bật mà lượt không có dấu vết + lượt "nổi"
TikTok (sắp nhiều thích) bắt video viral mà Kompa đếm.

Chủ dự án 16/10: "sao threads vẫn chưa có bài nào ? Và không cào được các bài rất viral như trong
kompa". Dữ liệu giả LÀM SẠCH, không tên/chữ thật; không bài nào gọi Apify/Postgres/model thật.
"""
from __future__ import annotations

import contextvars
import datetime
import time

import pytest
from test_theo_doi import DU_AN, GiaKhoTk, GiaViec, _chay_tk, _tt_tim, mo  # noqa: F401
from test_tiktok_api import GiaApi, _aweme

import apify_tool as A
import theo_doi as T
import theo_doi_api as TDA
import tiktok_api as TT

_VN = datetime.timezone(datetime.timedelta(hours=7))
BAT_TH = {"tu_khoa": {"threads": {"bat": True}}}
G = TT.GIA_YEU_CAU             # 0,003 USD/yêu cầu (giá thật đo 17/10)
TU = ["hapas", "túi hapas", "ví hapas", "yêu từ điều nhỏ nhất"]


class GiaApiCoActor(GiaApi):
    """Như `GiaApi` nhưng báo run kèm tên actor như `_run_actor` thật (meta["actor"]) — sổ
    tiền TikTok (`_tien_tim_tiktok`) đếm yêu cầu API theo tên actor."""

    def _run(self, actor, payload, limit, *a, **k):
        fn = A._KHI_CO_RUN.get()
        if fn:
            A._KHI_CO_RUN.set(lambda run, meta, fn=fn: fn(run, {**(meta or {}), "actor": actor}))
        try:
            return super()._run(actor, payload, limit, *a, **k)
        finally:
            if fn:
                A._KHI_CO_RUN.set(fn)


def _fetch_ghi(goi: dict, tra=None):
    def tao(p):
        def f(q, limit, country, d_from, d_to, **k):
            goi[p] = (list(q), limit)
            return list((tra or {}).get(p, []))
        return f
    return {p: tao(p) for p in T.TK_NEN_TANG}


# ───────────────────────────── Threads không còn bị bỏ qua im lặng ─────────────────────────────
def test_threads_tat_tren_console_de_lai_ly_do_trong_pheu_va_ghi_chu(mo):  # noqa: F811
    """Lượt 8 (16/10 22:53): Threads bật cho HAPAS mà không có phễu, không có câu nào — nhánh
    công tắc console tắt `continue` không để lại gì."""
    GiaKhoTk(mo)
    goi: dict = {}
    mo.setattr(A, "_FETCH", _fetch_ghi(goi))
    mo.setattr(A, "_tran_nen_tang",
               lambda p, nen=None, c=None: (1000, 5.0, p != "threads"))
    v = GiaViec({}, [])
    tk = _chay_tk(dict(DU_AN, tu_khoa=TU, tk_bat=True, tk_so_bai=15, cau_hinh=BAT_TH), v)
    assert "threads" not in goi and "tiktok" in goi
    assert "console" in tk["pheu"]["threads"]["bo_qua"]
    assert any(x.startswith("tìm Threads: bỏ qua (chủ agent đã tắt Threads") for x in tk["ghi_chu"])
    ph = next(x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x["id"] == "tk-threads")
    assert (ph["ma"], ph["trang_thai"], ph["usd_so"]) == ("TAT_CONSOLE", "loi", 0.0)
    # Dòng phễu rỗng của nền tảng bỏ qua không in (câu ghi chú đã nói lý do).
    assert not any(c.startswith("phễu tìm Threads") for c in T._cau_tk(tk))


def test_threads_thieu_tien_co_so_tu_thay_vi_bo_ca_nen_tang(mo):  # noqa: F811
    """Threads thừa hưởng số bài chung (vd 300 → 20 từ × ≥10 bài ≈ 1,08 USD) vượt phần còn
    của việc → trước đây bỏ cả nền tảng. Nay co về số từ ĐẦU vừa phần còn lại."""
    GiaKhoTk(mo)
    goi: dict = {}
    mo.setattr(A, "_FETCH", _fetch_ghi(goi))
    v = GiaViec({}, [])
    v.d["ngan_sach_usd"] = 0.15          # đủ 1 từ × 10 bài: (10 × 0,0025 + 0,08) × 1,3 = 0,1365
    da = dict(DU_AN, tu_khoa=TU, tk_bat=True, tk_so_bai=300,
              cau_hinh={"tu_khoa": {p: {"bat": p == "threads"} for p in T.TK_NEN_TANG}})
    tk = contextvars.copy_context().run(T._tim_tu_khoa, v, da, 3, 5.0, time.monotonic() + 600)
    assert goi["threads"] == (["hapas"], 10)
    assert any("co còn 1/4 từ khoá đầu" in x for x in tk["ghi_chu"])
    assert tk["usd"] == pytest.approx(0.08), "0 bài vẫn tính phí khởi động"
    assert "threads" in tk["pheu"] and not tk["pheu"]["threads"].get("bo_qua")
    # 1 từ cũng không vừa → bỏ qua CÓ lý do (ước tính / còn lại).
    assert T._co_threads(TU, 300, 0.1) is None
    assert T._co_threads(TU, 300, 0.2) == (TU[:2], 20, T.uoc_tu_khoa_nen_tang("threads", 20, TU))
    assert T._co_threads(TU, 300, 0.3)[:2] == (TU, 40), "4 từ × 10 bài = 0,234 USD vừa 0,3"


def test_ghi_chu_bo_qua_dung_truoc_dong_pheu_de_khong_bi_cat(mo):  # noqa: F811
    """`luot_quet.ghi_chu` cắt ở 2.000 ký tự: câu bỏ qua phải nằm trước các dòng phễu dài."""
    tk = {"tu": TU, "pheu": {p: T._pheu_moi(30, "chưa có mốc") for p in ("youtube", "tiktok",
                                                                         "facebook", "web")},
          "ghi_chu": ["tìm Threads: bỏ qua (hết ngân sách) — ước tính 1,08 USD, còn 0,50 USD"]}
    cau = T._cau_tk(tk)
    assert cau[1].startswith("tìm Threads: bỏ qua") and cau[2].startswith("phễu tìm")
    assert "tìm Threads: bỏ qua" in "; ".join(cau)[:2000]


# ───────────────────────────── lượt nổi TikTok ─────────────────────────────
def test_tim_sap_nhieu_thich_va_tran_trang_moi_tu():
    """`tiktok_api.tim(sap=…, trang_toi_da=…)` gửi đúng sortType và không lật quá trần trang."""
    goi = []

    def goi_gia(payload, ngan):
        goi.append(dict(payload))
        ngan.xin()
        off = payload["searchPosts_offset"]
        return {"search_item_list": [{"aweme_info": _aweme(1000 + off + i, ngay=10)}
                                     for i in range(30)], "has_more": 1, "cursor": off + 30}
    import pytest as _p
    with _p.MonkeyPatch.context() as m:
        m.setattr(TT, "_goi", goi_gia)
        bay = datetime.datetime.now(_VN)
        ra = TT.tim(["hapas"], 600, bay - datetime.timedelta(days=30), bay,
                    sap=TT.SAP_NHIEU_THICH, trang_toi_da=2)
    assert len(goi) == 2 and len(ra) == 60
    assert {g["searchPosts_sortType"] for g in goi} == {1}
    assert {g["searchPosts_publishTime"] for g in goi} == {30}


def test_tran_noi_nam_trong_uoc_tinh_tiktok():
    # 3 trang/từ + 1 trang "mới nhất" + 10 làm mới
    uoc = T.uoc_tu_khoa_nen_tang("tiktok", 300, ["k"] * 21)
    # Lượt thường + mới nhất dùng 2 trang/từ (42 yêu cầu) → còn đủ 2 trang/từ cho lượt nổi.
    assert TDA.tran_noi(21, uoc, 42 * G, 5.0) == pytest.approx(21 * 2 * G)
    # Lượt thường lật hết trần → lượt nổi chỉ còn phần chưa dùng (chừa làm mới).
    assert TDA.tran_noi(21, uoc, 84 * G, 5.0) == pytest.approx(
        round(uoc - 84 * G - 10 * G, 4))
    assert TDA.tran_noi(21, uoc, 0.0, 0.01) == pytest.approx(0.01)
    assert TDA.tran_noi(21, 0.0, 0.0, 5.0) == 0.0


@pytest.mark.tiktok_api
def test_luot_noi_bat_video_viral_cu_cap_nhat_bai_da_co_va_theo_nhip(mo):  # noqa: F811
    """Video seeding viral 16 ngày trước (ngoài cửa sổ tăng dần 3 ngày của lượt thường) chỉ
    lọt lượt "nhiều thích 30 ngày"; bài đã có thì cập nhật số bình luận (thảo luận như Kompa).
    Run id vào cùng sổ tiền TikTok; lượt sau trong 20 giờ không chạy lại."""
    kho = GiaKhoTk(mo)
    kho.da_co = {"tiktok:7000000002"}
    api = GiaApiCoActor(mo)
    moi = _aweme(7000000001, user="kol.moi", ngay=1)
    moi["desc"] = "review túi hapas"
    viral = _aweme(7000000003, user="kol.viral", ngay=16, xem=5_000_000)
    viral["desc"] = "20/10 kiểu này #HAPAS #LAMMOIDIEUVIYEU"
    viral["statistics"]["comment_count"] = 5158
    cu = _aweme(7000000002, user="kol.cu", ngay=12)
    cu["desc"] = "hapas"
    cu["statistics"]["comment_count"] = 999
    api.tim[("hapas", 0)] = ([moi], 0)

    def tra(p):
        if "searchPosts_keyword" in p and p["searchPosts_sortType"] == TT.SAP_NHIEU_THICH:
            assert p["searchPosts_publishTime"] == 30
            return {"status_code": 0, "has_more": 0, "cursor": 30,
                    "search_item_list": [{"aweme_info": a} for a in (viral, cu, moi)]}
        return goc(p)
    goc = api._tra
    api._tra = tra
    bay = datetime.datetime.now(_VN)
    T.ghi_moc_tk("hapas", {"tiktok": {"luc": (bay - datetime.timedelta(days=1)).isoformat(),
                                      "dau": T.dau_tk(["hapas"], 15), "luot": 2,
                                      "xin": 15, "ve": 1}})
    da = dict(DU_AN, tk_bat=True, tk_so_bai=15,
              # Feed hashtag TikTok (17/10/2026) có bài thử riêng (test_duong_moi.py): tắt.
              cau_hinh={"tu_khoa": {p: {"bat": p == "tiktok", "hashtag": {"bat": False}}
                                    for p in T.TK_NEN_TANG}})
    v = GiaViec({}, [])
    tk = _chay_tk(da, v)
    sap = [g.get("searchPosts_sortType") for g in api.goi if "searchPosts_keyword" in g]
    assert sap == [0, 3, 1], "lượt thường (liên quan), trang mới nhất, rồi lượt nổi (nhiều thích)"
    f = tk["pheu"]["tiktok"]
    assert f["noi"]["ve"] == 3 and f["noi"]["moi"] == 2 and f["noi"]["usd"] == pytest.approx(G)
    # Bộ giả trả lại bài lượt thường cho trang mới nhất: về 1, không thêm bài, 1 yêu cầu.
    assert (f["moi_nhat"]["ve"], f["moi_nhat"]["moi"]) == (1, 0)
    assert f["moi_nhat"]["usd"] == pytest.approx(G) and f["moi_nhat"]["tu"] == 1
    assert f["ve"] == 3 and f["cap_nhat"] == 1
    assert kho.cap_nhat[0]["khoa"] == "tiktok:7000000002" and kho.cap_nhat[0]["binh_luan"] == 999
    giu = {r["khoa"]: r for _, rows in kho.bai for r in rows}
    assert giu["tiktok:7000000003"]["binh_luan"] == 5158
    assert "lượt nổi (nhiều thích 30 ngày" in next(c for c in T._cau_tk(tk)
                                                    if c.startswith("phễu tìm TikTok"))
    moc = T.doc_moc_tk("hapas")
    assert moc["tiktok"]["ve"] == 1, "mốc lượt thường không đếm bài lượt nổi (so_xin)"
    assert moc[TDA.KHOA_MOC_NOI]["ve"] == 3
    # Tiền: 3 yêu cầu API (thường + mới nhất + nổi) — cùng sổ `_tien_tim_tiktok` theo run id.
    tien = next(x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x["id"] == "tk-tiktok")
    assert tien["usd_so"] == pytest.approx(3 * G)
    # Trong 20 giờ: không chạy lượt nổi (và trang mới nhất) nữa.
    api.goi.clear()
    tk2 = _chay_tk(da, GiaViec({}, []))
    assert [g.get("searchPosts_sortType") for g in api.goi if "searchPosts_keyword" in g] == [0]
    assert "noi" not in tk2["pheu"]["tiktok"]


def test_den_luot_noi_theo_nhip():
    bay = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=_VN)
    assert TDA.den_luot_noi(None, bay)[0]
    assert not TDA.den_luot_noi({"luc": "2026-10-17T01:00:00+07:00"}, bay)[0]
    assert TDA.den_luot_noi({"luc": "2026-10-16T12:00:00+07:00"}, bay)[0]
    assert TDA.den_luot_noi({"luc": "rác"}, bay)[0]


def test_luot_noi_khong_chay_khi_tiktok_di_duong_du_phong(mo):  # noqa: F811
    """TikTok API tắt (bộ thử mặc định = đường dự phòng tính tiền theo video): không lượt nổi."""
    GiaKhoTk(mo)
    goi: dict = {}
    mo.setattr(A, "_FETCH", _fetch_ghi(goi, {"tiktok": [_tt_tim("kol.a", "1", "túi hapas")]}))
    tk = _chay_tk(dict(DU_AN, tk_bat=True, tk_so_bai=15))
    assert "noi" not in tk["pheu"]["tiktok"]
    assert TDA.KHOA_MOC_NOI not in T.doc_moc_tk("hapas")


# ───────────────────────────── review 17/10 (M1, M3, LOW) ─────────────────────────────
def _kich_ban_api(mo, kho_da_co=()):  # noqa: F811
    """Lượt thường qua TikTok API trả 1 bài mới (run có tên actor như thật)."""
    kho = GiaKhoTk(mo)
    kho.da_co = set(kho_da_co)
    api = GiaApiCoActor(mo)
    moi = _aweme(7000000001, user="kol.moi", ngay=1)
    moi["desc"] = "review túi hapas"
    api.tim[("hapas", 0)] = ([moi], 0)
    da = dict(DU_AN, tk_bat=True, tk_so_bai=15,
              # Feed hashtag TikTok (17/10/2026) có bài thử riêng (test_duong_moi.py): tắt.
              cau_hinh={"tu_khoa": {p: {"bat": p == "tiktok", "hashtag": {"bat": False}}
                                    for p in T.TK_NEN_TANG}})
    return kho, api, da


def _noi_gia(mo, so_run: int, loi: Exception | None = None, bai=()):  # noqa: F811
    """Thay `tim_noi_tiktok`: báo `so_run` run TikTok API (đã trả tiền) rồi trả bài / ném lỗi."""
    goi = []

    def f(q, bay_gio, tran, trang=2):
        goi.append(tran)
        for i in range(so_run):
            A._KHI_CO_RUN.get()({"id": f"noi{i}"}, {"actor": TT.ACTOR})
        if loi is not None:
            raise loi
        return list(bai)
    mo.setattr(TDA, "tim_noi_tiktok", f)
    return goi


@pytest.mark.tiktok_api
@pytest.mark.parametrize("loi", [A.LoiApify("HET_TIEN_THANG", "hết hạn mức tháng"),
                                 RuntimeError("shape lạ")])
def test_luot_noi_loi_khong_lam_mat_bai_luot_thuong(mo, loi):  # noqa: F811
    """M1: lượt nổi ném lỗi (kể cả HET_TIEN_THANG) → bài lượt thường (đã trả tiền) vẫn vào phễu
    + kho, phần TikTok "xong", lỗi nằm ở `noi.ly_do`, tiền gồm cả run của lượt nổi."""
    kho, _api, da = _kich_ban_api(mo)
    _noi_gia(mo, 1, loi)
    v = GiaViec({}, [])
    tk = _chay_tk(da, v)
    f = tk["pheu"]["tiktok"]
    assert f["ve"] == 1 and f["moi"] == 1 and kho.bai
    assert "lỗi" in f["noi"]["ly_do"] and f["noi"]["usd"] == pytest.approx(G)
    ph = next(x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x["id"] == "tk-tiktok")
    # thường + trang mới nhất (bộ giả trả lại bài lượt thường) + run của lượt nổi
    assert ph["trang_thai"] == "xong" and ph["usd_so"] == pytest.approx(3 * G)
    assert not any(x.startswith("tìm TikTok:") for x in tk["ghi_chu"])
    # M3: đã trả tiền (dù lỗi) → ghi mốc nhịp ngay, lượt sau không chạy lại.
    assert T.doc_moc_tk("hapas")[TDA.KHOA_MOC_NOI]["usd"] == pytest.approx(G)


@pytest.mark.tiktok_api
def test_luot_noi_tra_0_bai_van_ghi_moc_nhip(mo):  # noqa: F811
    """M3: lượt nổi trả tiền mà 0 bài → vẫn ghi mốc; lượt sau trong 20 giờ không trả tiền lại."""
    _kho, _api, da = _kich_ban_api(mo)
    goi = _noi_gia(mo, 2)
    _chay_tk(da, GiaViec({}, []))
    assert len(goi) == 1 and T.doc_moc_tk("hapas")[TDA.KHOA_MOC_NOI]["ve"] == 0
    _chay_tk(da, GiaViec({}, []))
    assert len(goi) == 1, "trong NOI_GIO_GIAN không chạy lại"


@pytest.mark.tiktok_api
def test_luot_noi_khong_ton_tien_thi_khong_ghi_moc(mo):  # noqa: F811
    _kho, _api, da = _kich_ban_api(mo)
    goi = _noi_gia(mo, 0)
    _chay_tk(da, GiaViec({}, []))
    _chay_tk(da, GiaViec({}, []))
    assert len(goi) == 2 and TDA.KHOA_MOC_NOI not in T.doc_moc_tk("hapas")


@pytest.mark.tiktok_api
def test_luot_noi_chi_chay_khi_luot_thuong_qua_api_va_con_gio(mo):  # noqa: F811
    """LOW: lượt thường xuống dự phòng (run actor khác) hoặc gần hết giờ → không lượt nổi."""
    _kho, _api, _da = _kich_ban_api(mo)
    goi = _noi_gia(mo, 1)
    phan_du_phong = [{"run_id": "a", "actor": TT.ACTOR},
                     {"run_id": "b", "actor": "apidojo~tiktok-scraper"}]
    v = GiaViec({}, [])
    bay = datetime.datetime.now(_VN)
    assert T._them_luot_noi(v, "hapas", 1, ["hapas"], [], {}, bay, 1.0, 5.0,
                            phan_du_phong) == ([], {})
    assert T._them_luot_noi(v, "hapas", 1, ["hapas"], [], {}, bay, 1.0, 5.0, []) == ([], {})
    v_het = GiaViec({}, [], con=T._CHUA_GIAY_CUOI + 100)
    _, noi = T._them_luot_noi(v_het, "hapas", 1, ["hapas"], [], {}, bay, 1.0, 5.0,
                              [{"run_id": "a", "actor": TT.ACTOR}])
    assert "hết giờ" in noi["ly_do"] and not goi


def test_threads_mot_cau_ghi_chu_sau_khi_co(mo):  # noqa: F811
    """LOW: Threads co theo ngân sách → chỉ câu "co còn …", không kèm câu "x/y từ khoá đầu"
    tính trên số bài TRƯỚC khi co."""
    GiaKhoTk(mo)
    mo.setattr(A, "_FETCH", _fetch_ghi({}))
    v = GiaViec({}, [])
    v.d["ngan_sach_usd"] = 0.15
    da = dict(DU_AN, tu_khoa=TU, tk_bat=True, tk_so_bai=20,
              cau_hinh={"tu_khoa": {p: {"bat": p == "threads"} for p in T.TK_NEN_TANG}})
    tk = contextvars.copy_context().run(T._tim_tu_khoa, v, da, 3, 5.0, time.monotonic() + 600)
    cau = [x for x in tk["ghi_chu"] if x.startswith("tìm Threads")]
    assert len(cau) == 1 and "co còn 1/4" in cau[0]
    # Đủ tiền mà số bài < 10 × số từ: vẫn một câu "x/y từ khoá đầu".
    tk = _chay_tk(dict(da, tk_so_bai=20))
    cau = [x for x in tk["ghi_chu"] if x.startswith("tìm Threads")]
    assert len(cau) == 1 and "2/4 từ khoá đầu" in cau[0]


def test_youtube_thieu_key_khong_ghi_cau_moi_luot(mo):  # noqa: F811
    """LOW: YouTube thiếu key (chuyện của máy chạy) → phễu + phần THIEU_KEY, không câu ghi chú."""
    GiaKhoTk(mo)
    mo.setattr(A, "_FETCH", _fetch_ghi({}))
    mo.setattr(A, "_youtube_co_key", lambda: False)
    v = GiaViec({}, [])
    tk = _chay_tk(dict(DU_AN, tk_bat=True, tk_so_bai=15), v)
    assert tk["pheu"]["youtube"]["bo_qua"] and not any("YouTube" in x for x in tk["ghi_chu"])
    ph = next(x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x["id"] == "tk-youtube")
    assert ph["ma"] == "THIEU_KEY"
