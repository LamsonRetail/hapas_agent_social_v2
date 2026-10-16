"""Báo & Web trong `/theodoi` (16/10/2026): phần `tk-web` của lượt tìm, nhịp một lượt/ngày + mọi
lượt trong chiến dịch (khẩu hiệu làm từ khoá), đọc dự phòng có trần, sổ tiền theo giá thật, sổ
"đã loại" riêng, cột web khi ghi kho, từ loại trừ ngắn khớp nguyên từ. Mọi HTML / kết quả tìm ở
đây là MẪU TỰ VIẾT; mạng bị chặn (conftest) — actor, tải trang đều giả."""
from __future__ import annotations

import datetime
import json

import pytest
import test_theo_doi as TT
from test_theo_doi import DU_AN, GiaKhoTk, GiaViec, _chay_tk

import apify_tool as A
import lang_nghe_db as K
import nguon_web as W
import theo_doi as T

_VN = datetime.timezone(datetime.timedelta(hours=7))
mo = TT.mo


def _bai(tieu_de, than, ngay):
    ld = {"@type": "NewsArticle", "headline": tieu_de, "datePublished": ngay}
    return (f'<html><head><script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}'
            f'</script><meta property="og:site_name" content="Báo Mẫu"></head><body><article>'
            f'<div class="detail-content"><p>{than}</p></div></article></body></html>')


def _hom_qua():
    return (datetime.datetime.now(_VN) - datetime.timedelta(days=1)).isoformat(timespec="seconds")


# ───────────────────────────── cấu hình + ước tính ─────────────────────────────
def test_web_mac_dinh_bat_duoi_cong_tac_tong_va_boc():
    c = T.cau_hinh(dict(DU_AN, tk_bat=True, tk_so_bai=15), "tu_khoa", "web")
    assert c["bat"] and c["so_bai"] == 15 and c["boc"] == T.WEB_BOC_MAC_DINH == 10
    assert not T.cau_hinh(dict(DU_AN, tk_bat=False, tk_so_bai=15), "tu_khoa", "web")["bat"]
    da = dict(DU_AN, tk_bat=True, tk_so_bai=15, cau_hinh={"tu_khoa": {"web": {"boc": 0}}})
    assert T.cau_hinh(da, "tu_khoa", "web")["boc"] == 0                    # 0 = tắt dự phòng
    da = dict(DU_AN, tk_bat=True, tk_so_bai=15, cau_hinh={"tu_khoa": {"web": {"boc": "x"}}})
    assert T.cau_hinh(da, "tu_khoa", "web")["boc"] == 10
    assert "web" not in T.MAC_DINH_TAT and "web" in T.TK_NEN_TANG


def test_uoc_web_dung_cong_thuc():
    tu = ["hapas", "túi hapas", "ví hapas", "quà tặng hapas", "yêu từ điều nhỏ nhất", "hapas.vn"]
    # 2 từ sau rút gọn -> 1 câu; 15 kết quả -> 2 trang; 10 trang dự phòng
    assert T.uoc_web(15, tu) == round((1 * 2 * 0.0005 + 10 * 0.009) * 1.3, 4)
    assert T.uoc_web(15, tu, 0) == round(0.001 * 1.3, 4)
    assert T.uoc_web(0, tu) == 0.0
    nhieu = [f"brand{i}" for i in range(20)]                                # 20 từ -> 4 câu (trần)
    assert T.uoc_web(30, nhieu, 0) == round(4 * 3 * 0.0005 * 1.3, 4)
    assert T.uoc_tu_khoa_nen_tang("web", 15, tu) == T.uoc_web(15, tu)
    da = dict(DU_AN, tu_khoa=tu, tk_bat=True, tk_so_bai=15,
              cau_hinh={"tu_khoa": {p: {"bat": p == "web", "boc": 2} for p in T.TK_NEN_TANG}})
    assert T.uoc_tu_khoa_du_an(da) == T.uoc_web(15, tu, 2)


def test_cua_so_web_lui_2_ngay():
    bay = datetime.datetime(2026, 10, 20, 9, 0, tzinfo=_VN)
    moc = {"luc": "2026-10-19T09:00:00+07:00", "dau": "d"}
    assert T.cua_so_tk(moc, "d", bay, chong=T.WEB_NGAY_CHONG)[1] == 3
    assert T.cua_so_tk(dict(moc, luc="2026-10-15T09:00:00+07:00"), "d", bay, chong=2)[1] == 7


# ───────────────────────────── từ loại trừ ─────────────────────────────
def test_tu_loai_tru_ngan_khop_nguyen_tu():
    lt = ["hapa", "kota hapas", "guitar", "sushi", "brewing"]
    assert A._tu_loai_tru_khop({"text": "Túi HAPAS mới về"}, lt) == ""
    assert A._tu_loai_tru_khop({"text": "Hapa's Brewing Company taproom"}, ["hapa"]) == "hapa"
    assert A._tu_loai_tru_khop({"text": "Hapa sushi Cherry Creek"}, lt) == "hapa"
    assert A._tu_loai_tru_khop({"text": "tàu KOTA HAPAS cập cảng"}, lt) == "kota hapas"
    assert A._tu_loai_tru_khop({"text": "x", "username": "hapasguitars.com"}, lt) == "guitar"
    q = W.cau_truy_van(dict(DU_AN, tu_loai_tru=lt))[0]
    assert '-"kota hapas"' in q and "-guitar" in q and "-hapa " not in q + " "


def test_ai_doc_400_ky_tu_voi_web():
    d = {"platform": "web", "text": "a" * 390 + "HAPAS" + "b" * 50, "kenh": "x"}
    assert "HAPAS" in A._boc_bai(0, d)
    assert "HAPAS" not in A._boc_bai(0, dict(d, platform="tiktok"))


# ───────────────────────────── ghi kho ─────────────────────────────
class _Ket:
    def __init__(self):
        self.lenh = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, gt=None):
        self.lenh.append((sql, gt))
        return self

    def fetchone(self):
        return {"moi": True}


def test_ghi_bai_chi_them_cot_web_khi_co(monkeypatch):
    k = _Ket()
    monkeypatch.setattr(K, "ket_noi", lambda: k)
    r = {"khoa": "tiktok:1", "nen_tang": "tiktok", "link": "l", "noi_dung": "x"}
    K.ghi_bai("hapas", 1, "tu_khoa", [r, dict(r, khoa="web:a", nen_tang="web", kieu_trang="bao",
                                             muc_nhac="tieu_de", la_pr=False)])
    ins = [s for s, _ in k.lenh if s.startswith("INSERT INTO bai ")]
    assert "kieu_trang" not in ins[0]
    assert "kieu_trang, muc_nhac, la_pr)" in ins[1]
    assert "la_pr = COALESCE(EXCLUDED.la_pr, bai.la_pr)" in ins[1]


# ───────────────────────────── một lượt /theodoi có web ─────────────────────────────
class _GiaWeb:
    """Bọc `nguon_web.thu_thap` thật, tiêm actor Google + actor dự phòng + tải trang giả."""

    def __init__(self, mp, serp, trang, boc_html=None):
        self.goi, self.tai, self.boc_goi = [], [], []
        self.serp, self.trang, self.boc_html = serp, trang, boc_html or {}
        goc = W.thu_thap

        def gia(du_an, **kw):
            self.goi.append(dict(kw, du_an=du_an))
            return goc(du_an, chay_actor=self.actor, tai=self.tai_trang, ngu=lambda s: None,
                       boc=self.boc, **kw)
        mp.setattr(W, "thu_thap", gia)

    def actor(self, payload, limit, han, tran):
        assert tran >= 0.1 and payload["tbs"].startswith("cdr:1")
        self.payload = payload
        A._KHI_CO_RUN.get()({"id": "run-tim"}, {"actor": W.ACTOR_TIM})
        return [{"search_term": "q", "results": [
            {"position": i, "link": u, "title": t, "snippet": s, "date": "1 ngày trước"}
            for i, (u, t, s) in enumerate(self.serp, 1)]}], {"run_id": "run-tim"}

    def tai_trang(self, u):
        self.tai.append(u)
        if u.endswith("/robots.txt"):
            return 404, "", u
        h = self.trang.get(u)
        return (200, h, u) if h else (403, "", u)

    def boc(self, urls, han, tran):
        self.boc_goi.append((list(urls), tran))
        A._KHI_CO_RUN.get()({"id": "run-boc"}, {"actor": W.ACTOR_BOC})
        return ([{"url": u, "crawl": {"httpStatusCode": 200}, "html": self.boc_html[u]}
                 for u in urls if u in self.boc_html], {"run_id": "run-boc", "giay": 40})


def _du_an(**kw):
    return dict(DU_AN, tu_khoa=["hapas", "túi hapas"], tk_bat=True, tk_so_bai=15,
                cau_hinh={"tu_khoa": {p: {"bat": p == "web"} for p in T.TK_NEN_TANG},
                          "web": {"mien_nha": ["hapas.co"]}}, **kw)


def test_luot_web_ghi_kho_tien_phan_moc_va_nhip_mot_ngay(mo):
    kho = GiaKhoTk(mo)
    kho.da_co = {W.khoa_web("https://bao.vd.vn/cu.htm")}
    serp = [("https://bao.vd.vn/a.htm", "Túi Việt", ""),
            ("https://chan.vd.vn/b.htm", "HAPAS bị chê", "TVC hapas gây tranh cãi"),
            ("https://bao.vd.vn/cu.htm", "Đã có", "hapas"),
            ("https://hapas.co/en", "nhà", "hapas"),
            ("https://www.tiktok.com/@a/video/1", "tt", "hapas")]
    than = "Bài viết dài về túi Việt. " * 10 + "Túi HAPAS bán chạy, xem tại hapas.co."
    web = _GiaWeb(mo, serp, {"https://bao.vd.vn/a.htm": _bai("Túi Việt lên ngôi", than, _hom_qua())},
                  {"https://chan.vd.vn/b.htm": _bai("Quảng cáo gây tranh cãi",
                                                    "TVC 20/10 của HAPAS bị chê. " * 3, _hom_qua())})
    v = GiaViec({}, [])
    tk = _chay_tk(_du_an(), v)
    assert len(web.goi) == 1 and web.goi[0]["boc_toi_da"] == 10
    assert web.boc_goi == [(["https://chan.vd.vn/b.htm"], 0.1)]
    assert "https://bao.vd.vn/cu.htm" not in web.tai                    # đã có: không tải lại
    assert not any("hapas.co" in u or "tiktok" in u for u in web.tai)
    rows = [r for _, cac in kho.bai for r in cac]
    assert {r["nen_tang"] for r in rows} == {"web"} and len(rows) == 2
    a = next(r for r in rows if "bao.vd.vn" in r["link"])
    assert (a["kieu_trang"], a["muc_nhac"], a["xem"], a["tai_khoan"]) == ("bao", "thoang", None,
                                                                          "bao.vd.vn")
    assert a["khoa"] == W.khoa_web("https://bao.vd.vn/a.htm") and a["nguon_id"] is None
    # Sổ tiền theo giá thật: 1 trang Google + trang dự phòng (max(1 × 0,009, 40 s × giá giây)).
    assert tk["usd"] == pytest.approx(0.0005 + max(0.009, 40 * W.BOC_USD_MOI_GIAY))
    phan = v.d["nen_tang"]["tu_khoa"]["phan"]
    assert {p.get("run_id") for p in phan if p.get("run_id")} == {"run-tim", "run-boc"}
    assert all(p["trang_thai"] == "xong" for p in phan if p.get("run_id"))
    f = tk["pheu"]["web"]
    assert (f["ve"], f["cap_nhat"], f["giu"]) == (5, 1, 2)
    assert f["web"]["boc_duoc"] == 1 and f["web"]["mxh"] == 1 and f["web"]["nha"] == 1
    assert any(c.startswith("phễu tìm Báo & Web") for c in T._cau_tk(tk))
    assert set(T.doc_moc_tk("hapas")) == {"web"}
    # Lượt thứ hai trong ngày, không chiến dịch: không tìm web.
    tk2 = _chay_tk(_du_an(), GiaViec({}, []))
    assert len(web.goi) == 1 and any("một lượt mỗi ngày" in x for x in tk2["ghi_chu"])


def test_chien_dich_moi_luot_co_web_va_khau_hieu(mo):
    kho = GiaKhoTk(mo)
    bay = datetime.datetime.now(_VN)
    kho.lich = [{"id": 5, "kieu": "chien_dich", "bat": True, "cau_hinh": {
        "tu_luc": (bay - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
        "den_luc": (bay + datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
        "moi_phut": 60, "tu_khoa_them": ["Do anything for love", " ", "hapas"]}}]
    web = _GiaWeb(mo, [("https://bao.vd.vn/c.htm", "Do anything for love", "")],
                  {"https://bao.vd.vn/c.htm": _bai("Chiến dịch Do anything for love",
                                                   "Phim quảng cáo mới. " * 15, _hom_qua())})
    tk = _chay_tk(_du_an())
    _chay_tk(_du_an())                                           # lượt 2 trong chiến dịch: vẫn tìm
    assert len(web.goi) == 2 and web.goi[0]["them_tu"] == ["Do anything for love", "hapas"]
    assert '"Do anything for love"' in web.payload["keyword"]
    # Bài chỉ nhắc khẩu hiệu (không có chữ hapas) vẫn giữ: khẩu hiệu là từ khoá của lượt web.
    rows = [r for _, cac in kho.bai for r in cac]
    assert rows and rows[0]["link"] == "https://bao.vd.vn/c.htm"
    assert any("chiến dịch #5 thêm khẩu hiệu" in x for x in tk["ghi_chu"])


def test_web_het_ngan_sach_khong_doc_du_phong(mo):
    GiaKhoTk(mo)
    web = _GiaWeb(mo, [("https://chan.vd.vn/b.htm", "HAPAS", "hapas")], {})
    import contextvars
    import time
    contextvars.copy_context().run(T._tim_tu_khoa, GiaViec({}, []), _du_an(), 3, 0.1003,
                                   time.monotonic() + 600)
    assert web.goi and web.boc_goi == []                         # còn 0,1 - 0,0005 < trần tối thiểu


def test_bai_web_bi_loai_vao_so_rieng_khong_de_so_mxh(mo):
    import theo_doi_api as TDA
    GiaKhoTk(mo)
    _GiaWeb(mo, [("https://bao.vd.vn/k.htm", "Túi đẹp", "")],
            {"https://bao.vd.vn/k.htm": _bai("Túi đẹp", "Không nhắc brand nào. " * 20, _hom_qua())})
    TDA.ghi_loai("hapas", "dau-mxh", [("tiktok:1", "spam", datetime.datetime.now(_VN))],
                 datetime.datetime.now(_VN) - datetime.timedelta(days=30))
    tk = _chay_tk(_du_an())
    tu_pv = datetime.datetime.fromisoformat(tk["pham_vi"]["tu"])
    da = _du_an()
    so_web = TDA.doc_loai("hapas:web", TDA.dau_loai(da, W.rut_gon_tu_khoa(T.tu_tim(da))), tu_pv)
    k = W.khoa_web("https://bao.vd.vn/k.htm")
    assert set(so_web) == {k} and so_web[k][0] == "khong_nhac"
    assert set(TDA.doc_loai("hapas", "dau-mxh", tu_pv)) == {"tiktok:1"}      # sổ MXH còn nguyên
