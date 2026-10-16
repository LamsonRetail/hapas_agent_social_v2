"""Rà soát độc lập c812fff (16/10/2026) — mỗi phát hiện một nhóm bài: H1 lỗi một trang/một URL
không làm vỡ lượt (và không làm mất bài mạng xã hội đã trả tiền), M1 sổ "đã đọc dự phòng" +
khoá canonical, M2 web mặc định tắt, M3 từ loại trừ / từ khoá chỉ xét tiêu đề + đoạn nhắc, M4
hạn đồng hồ khi đọc trang, M5 hệ số an toàn + sổ nguyên trần, L2 robots sau chuyển hướng, L3 từ
loại trừ có dấu câu, L4 hết ngân sách không dời mốc, L6 canonical trang chủ. Mẫu tự viết; mạng
bị chặn (conftest)."""
from __future__ import annotations

import contextvars
import datetime
import time

import pytest
import test_nguon_web as TN
import test_theo_doi as TT
import test_theo_doi_web as TW
from test_theo_doi import GiaKhoTk, GiaViec, _chay_tk

import apify_tool as A
import nguon_web as W
import theo_doi as T
from dashboard import chi_phi as CP

_VN = datetime.timezone(datetime.timedelta(hours=7))
mo = TT.mo
_serp, _chay, _bai, _Gia = TN._serp, TN._chay, TN._bai, TN._Gia
DU_AN, BAY_GIO = TN.DU_AN, TN.BAY_GIO


# ───────────────────────────── H1 ─────────────────────────────
def test_h1_url_hong_khong_vo_luot():
    for u in ("http://[x", "https://a.vn:99999/x", "http://[::1", "https://"):
        assert W.url_an_toan(u, lambda h: ["93.184.216.34"]) is False
    assert W.mien("http://[x") == "" and W.url_chuan("http://[x") == ""
    assert W._ly_do_bo_url("http://[x/a", []) == "url_hong"
    assert W.kieu_trang("http://[x") == "khac"
    items = _serp(("http://[x/bai", "HAPAS", "hapas", "1 ngày trước"),
                  ("https://bao.vd.vn/ok.htm", "HAPAS", "hapas mới", "1 ngày trước"))
    items[0]["results"].append({"link": "https://b.vd.vn/x", "date": object()})   # dòng lạ
    hits, tk, _ = _chay(items, {})
    assert "https://bao.vd.vn/ok.htm" in [d["link"] for d, _ in hits]
    assert tk["pheu"]["url_hong"] == 1 and tk["trang_thai"] == "xong"


def test_h1_json_ld_long_qua_sau_va_trang_nem_loi():
    sau = "[" * 50_000 + "]" * 50_000
    t = W.boc_trang(f'<script type="application/ld+json">{sau}</script><p>hapas</p>',
                    "https://x.vn/a")
    assert "hapas" in t["noi_dung"]
    items = _serp(("https://hong.vd.vn/a", "HAPAS", "hapas", "1 ngày trước"),
                  ("https://bao.vd.vn/ok.htm", "HAPAS", "hapas mới", "1 ngày trước"))
    g = _Gia({"https://bao.vd.vn/ok.htm": _bai("HAPAS", "<p>" + "Nội dung. " * 30 + "HAPAS.</p>")})

    def tai(u):
        if "hong.vd.vn/a" in u:
            raise RuntimeError("bất ngờ")
        return g.tai(u)
    hits, tk = W.thu_thap(DU_AN, tu=datetime.date(2026, 10, 1), den=datetime.date(2026, 10, 16),
                          chay_actor=lambda *a: (items, {"run_id": "r"}), tai=tai, ngu=g.ngu_,
                          bay_gio=BAY_GIO, tu_dong_ho=g.dong_ho, han=1e9)
    assert tk["pheu"]["trang_hong"] == 1 and len(hits) == 2       # trang hỏng: còn đoạn trích


def test_h1_so_nhan_tien_ngay_ca_khi_nem(monkeypatch):
    so: dict = {}
    items = _serp(("https://bao.vd.vn/ok.htm", "HAPAS", "hapas", "1 ngày trước"))

    def no(*a, **k):
        raise MemoryError("giả")
    monkeypatch.setattr(W, "doc_serp", no)
    with pytest.raises(MemoryError):
        W.thu_thap(DU_AN, chay_actor=lambda *a: (items, {"run_id": "r9"}), bay_gio=BAY_GIO, so=so)
    assert so["run_ids"] == ["r9"] and so["usd_tim"] == W.GIA_TRANG


def _da_web_tiktok():
    return dict(TW._du_an(), cau_hinh={"tu_khoa": {p: {"bat": p in ("web", "tiktok")}
                                                   for p in T.TK_NEN_TANG}})


def test_h1_web_loi_bat_ngo_khong_mat_bai_mxh(mo):
    kho = GiaKhoTk(mo)

    def tim(p):
        def f(q, limit, country, d_from, d_to, **k):
            if p != "tiktok":
                return []
            A._KHI_CO_RUN.get()({"id": "run-tt"}, {"actor": T.TT_ACTOR})
            return [TT._tt_tim("kol.b", "2", "review túi HAPAS xinh")]
        return f
    mo.setattr(A, "_FETCH", {p: tim(p) for p in T.TK_NEN_TANG})

    def no(du_an, **kw):
        kw["so"].update(usd_tim=0.0005, run_ids=["run-w"])
        raise RecursionError("giả")
    mo.setattr(W, "thu_thap", no)
    v = GiaViec({}, [])
    tk = _chay_tk(_da_web_tiktok(), v)
    assert any(r["nen_tang"] == "tiktok" for _, cac in kho.bai for r in cac)   # MXH vẫn ghi
    assert "tiktok" in T.doc_moc_tk("hapas") and "web" not in T.doc_moc_tk("hapas")
    moc = next(p for p in v.d["nen_tang"]["tu_khoa"]["phan"] if p.get("id") == "tk-web")
    assert moc["trang_thai"] == "loi" and moc["usd_so"] == 0.0005
    assert any("lỗi bất ngờ RecursionError" in x for x in tk["ghi_chu"])


# ───────────────────────────── M1 ─────────────────────────────
def test_m1_da_boc_khong_doc_lai_va_ghi_khoa_moi():
    items = _serp(("https://chan.vd.vn/a", "HAPAS", "hapas", "1 ngày trước"),
                  ("https://chan.vd.vn/b", "HAPAS", "hapas", "1 ngày trước"))
    goi = []

    def boc(urls, han, tran):
        goi.append(list(urls))
        return [], {"run_id": "rb"}
    hits, tk, _ = _chay(items, {}, boc=boc, boc_toi_da=5, con_usd=1.0,
                        da_boc={W.khoa_web("https://chan.vd.vn/a")})
    assert goi == [["https://chan.vd.vn/b"]] and tk["pheu"]["da_boc_truoc"] == 1
    assert tk["da_boc_moi"] == [W.khoa_web("https://chan.vd.vn/b")]
    assert len(hits) == 2 and all(d["_web"]["chi_trich"] for d, _ in hits)


def test_m1_canonical_hoi_so_da_biet_va_bi_loai_ca_hai_khoa():
    can = "https://bao.vd.vn/goc.htm"
    h = _bai("Túi đẹp", "<p>" + "Không nhắc gì. " * 30 + "</p>").replace(
        "<head>", f'<head><link rel="canonical" href="{can}">')
    u = "https://bao.vd.vn/goc.htm?utm_x=1&p=2"
    items = _serp((u, "x", "", "1 ngày trước"))
    _, tk, _ = _chay(items, {u: h})
    assert {k for k, _, _ in tk["bi_loai"]} == {W.khoa_web(can), W.khoa_web(u)}
    hits, tk, _ = _chay(items, {u: h},
                        da_biet=lambda ks: {k: "da_co" for k in ks if k == W.khoa_web(can)})
    assert tk["pheu"]["da_co"] == 1 and hits == []


def test_m1_so_da_boc_14_ngay():
    bay = datetime.datetime(2026, 10, 16, 9, 0, tzinfo=_VN)
    T.ghi_da_boc("hapas", ["web:a"], bay - datetime.timedelta(days=20))
    T.ghi_da_boc("hapas", ["web:b"], bay - datetime.timedelta(days=3))
    T.ghi_da_boc("khac", ["web:c"], bay)
    assert T.doc_da_boc("hapas", bay) == {"web:b"}
    assert T.doc_da_boc("khac", bay) == {"web:c"}


def test_m1_luot_web_gui_da_boc_va_ghi_lai(mo):
    GiaKhoTk(mo)
    b = W.khoa_web("https://chan.vd.vn/b.htm")
    T.ghi_da_boc("hapas", [b], datetime.datetime.now(_VN))
    web = TW._GiaWeb(mo, [("https://chan.vd.vn/b.htm", "HAPAS", "hapas"),
                          ("https://chan.vd.vn/c.htm", "HAPAS", "hapas")], {})
    _chay_tk(TW._du_an())
    assert web.goi[0]["da_boc"] == {b}
    assert [u for u, _ in web.boc_goi] == [["https://chan.vd.vn/c.htm"]]
    assert W.khoa_web("https://chan.vd.vn/c.htm") in T.doc_da_boc("hapas",
                                                                  datetime.datetime.now(_VN))


# ───────────────────────────── M2 ─────────────────────────────
def test_m2_web_mac_dinh_tat_ca_hai_phia():
    assert "web" in T.MAC_DINH_TAT and CP.MAC_DINH_TAT == T.MAC_DINH_TAT
    da = {"tk_bat": True, "tk_so_bai": 15, "cau_hinh": {}}
    assert not T.cau_hinh(da, "tu_khoa", "web")["bat"]
    assert not CP.cau_hinh(da, "tu_khoa", "web")["bat"]
    from pathlib import Path
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" /
           "du-lieu-hapas-web-2026-10-16.sql").read_text(encoding="utf-8")
    assert "'{tu_khoa}'" in sql and '{"bat": true}' in sql and "WHERE ma = 'hapas'" in sql


# ───────────────────────────── M3 ─────────────────────────────
def test_m3_loai_tru_va_tu_khoa_chi_xet_tieu_de_va_doan_nhac():
    than = ("<p>Túi HAPAS ra mắt bộ sưu tập mới.</p><p>" + "Đoạn dài không liên quan. " * 40
            + "</p><p>Cuối bài: một cây guitar cũ.</p>")
    items = _serp(("https://bao.vd.vn/a.htm", "x", "", "1 ngày trước"))
    hits, tk, _ = _chay(items, {"https://bao.vd.vn/a.htm": _bai("Tin tức", than)})
    assert len(hits) == 1 and tk["pheu"]["loai_tru"] == 0          # "guitar" xa chỗ nhắc
    than2 = "<p>Túi da bò.</p><p>" + "Chữ đệm. " * 60 + "</p><p>Hapas bán chạy, mẫu xinh.</p>"
    g = _Gia({"https://bao.vd.vn/b.htm": _bai("Tin", than2)})
    hits, tk = W.thu_thap(dict(DU_AN, tu_khoa=["túi hapas xinh"]), tu=datetime.date(2026, 10, 1),
                          den=datetime.date(2026, 10, 16),
                          chay_actor=lambda *a: (_serp(("https://bao.vd.vn/b.htm", "x", "",
                                                         "1 ngày trước")), {}),
                          tai=g.tai, ngu=g.ngu_, bay_gio=BAY_GIO, tu_dong_ho=g.dong_ho, han=1e9)
    assert hits == [] and tk["pheu"]["khong_nhac"] == 1            # chữ rải rác: không tính


# ───────────────────────────── M4, M5 ─────────────────────────────
def test_m4_tai_http_dung_theo_dong_ho(monkeypatch):
    import requests
    gio = [0.0]

    class R:
        status_code = 200

        def __init__(self):
            self.headers = {"content-type": "text/html; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_content(self, n):
            while True:
                gio[0] += 10.0                      # mỗi khối 10 giây "nhỏ giọt"
                yield b"<p>x</p>"
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(W.time, "monotonic", lambda: gio[0])
    ma, h, _ = W.tai_http("https://93.184.216.34/a")
    assert ma == 0 and h == "" and gio[0] <= W.GIAY_TRANG_TOI_DA + 10
    gio[0] = 0.0
    assert W.tai_http("https://93.184.216.34/a", han=5.0)[0] == 0 and gio[0] <= 20


def test_m5_giay_boc_he_so_an_toan_va_so_nguyen_tran():
    assert W.giay_boc(0.1) == pytest.approx(0.1 / (W.BOC_USD_MOI_GIAY * 1.5))
    items = _serp(("https://chan.vd.vn/a", "HAPAS", "hapas", "1 ngày trước"))
    _, tk, _ = _chay(items, {}, boc=lambda u, h, t: ([], {"run_id": "rb", "giay": 1}),
                     boc_toi_da=3, con_usd=1.0)
    assert tk["usd_boc"] == 0.1


# ───────────────────────────── L2, L6 ─────────────────────────────
def test_l2_chuyen_huong_sang_mien_cam_bot_va_l6_canonical_trang_chu():
    items = _serp(("https://bao.vd.vn/a.htm", "HAPAS", "hapas", "1 ngày trước"))
    g = _Gia({})

    def tai(u):
        if u.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /\n", u) if "cam.vd.vn" in u else (404, "", u)
        return 200, _bai("HAPAS", "<p>hapas</p>"), "https://cam.vd.vn/a.htm"
    hits, tk = W.thu_thap(DU_AN, tu=datetime.date(2026, 10, 1), den=datetime.date(2026, 10, 16),
                          chay_actor=lambda *a: (items, {}), tai=tai, ngu=g.ngu_,
                          bay_gio=BAY_GIO, tu_dong_ho=g.dong_ho, han=1e9)
    assert tk["pheu"]["robots_chan"] == 1 and hits[0][0]["_web"]["chi_trich"]
    h = '<link rel="canonical" href="https://x.vn/"><p>a</p>'
    assert W.boc_trang(h, "https://x.vn/bai-1")["canonical"] == ""


# ───────────────────────────── L3, L4 ─────────────────────────────
def test_l3_tu_loai_tru_co_dau_cau_van_khop_chuoi_con():
    assert A._tu_loai_tru_khop({"text": "deal hôm nay #adtest nhé"}, ["#ad"]) == "#ad"
    assert A._tu_loai_tru_khop({"text": "theo dõi @abcshop"}, ["@abc"]) == "@abc"
    assert A._tu_loai_tru_khop({"text": "Túi HAPAS"}, ["hapa"]) == ""


def test_l4_thu_thap_bo_qua_khong_doi_moc(mo):
    GiaKhoTk(mo)
    mo.setattr(W, "thu_thap", lambda du_an, **kw: ([], {**kw["so"], "trang_thai":
                                                       "bo_qua: hết ngân sách tháng",
                                                       "pheu": W._pheu_moi()}))
    v = GiaViec({}, [])
    _chay_tk(TW._du_an(), v)
    assert "web" not in T.doc_moc_tk("hapas")
    ph = next(p for p in v.d["nen_tang"]["tu_khoa"]["phan"] if p.get("id") == "tk-web")
    assert ph["trang_thai"] == "loi" and ph["ma"] == "NGAN_SACH"


def test_l4_het_ngan_sach_that_khong_doi_moc(mo):
    GiaKhoTk(mo)
    TW._GiaWeb(mo, [], {})
    contextvars.copy_context().run(T._tim_tu_khoa, GiaViec({}, []), TW._du_an(), 3, 0.05,
                                   time.monotonic() + 600)
    assert "web" not in T.doc_moc_tk("hapas")
