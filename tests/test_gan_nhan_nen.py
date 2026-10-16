"""Gán nhãn AI chạy nền (17/10/2026) + prompt bài mới + lọc trang tuyển dụng + Ý định mua.

Vì sao: lượt `/theodoi` 7 chạy 54 phút (> hạn 45 phút) vì gán nhãn ~2.400 bình luận ngay trong
việc; tập đánh giá 17/10 (200 bình luận + 60 bài thật, nhãn chuẩn do người chấm) cho thấy bài
báo về quảng cáo gây tranh cãi ra "Trung lập". Dữ liệu ở đây là giả; không gọi model/kho thật.
"""
from __future__ import annotations

import json
import re
import time

import pytest

import gan_nhan_nen as G
import nguon_web as W
import phan_loai as P
from dashboard import chi_so as CS


# ───────────────────────────── phan_loai: lô + bài ─────────────────────────────
def _model_bl(nhac: str) -> str:
    """Model giả cho bình luận: bỏ sót thẻ có chữ "sot" (lô chạy được, dòng không có nhãn)."""
    ra = {i: (["+", "SP"] if "đẹp" in t else ["=", "GIA"])
          for i, t in re.findall(r'<c i="(\d+)">(.*?)</c>', nhac) if "sot" not in t}
    return json.dumps(ra)


def test_phan_loai_binh_luan_bao_dong_bi_bo_sot(monkeypatch):
    monkeypatch.setattr(P, "_goi_model", _model_bl)
    tt: dict = {}
    ra = P.phan_loai_binh_luan([{"text": "đẹp quá"}, {"text": "sot nè"}, {"text": "@ban"}], 60, tt)
    assert ra[0] == ("Tích cực", "Sản phẩm/chất lượng") and ra[1] == (P.CHUA, P.CHUA)
    assert ra[2] == ("Trung lập", "Tag bạn bè"), "luật trước, model sau"
    assert tt["khong_tra"] == [1] and tt["lo_loi"] == 0


def test_lo_hong_khong_tinh_la_bo_sot(monkeypatch):
    def hong(_):
        raise RuntimeError("model down")
    monkeypatch.setattr(P, "_goi_model", hong)
    tt: dict = {}
    P.phan_loai_binh_luan([{"text": "đẹp quá"}], 60, tt)
    assert tt["lo_loi"] == 1 and tt["khong_tra"] == [], "lô hỏng: lùi cả nhịp, không phạt dòng"


def test_gan_theo_luat_chi_tra_none_cho_dong_can_model():
    assert P.gan_theo_luat([{"text": "@a @b"}, {"text": "giá sao"}, {"text": "❤️"}]) == [
        ("Trung lập", "Tag bạn bè"), None, ("Tích cực", "KOL/nội dung")]


def test_nhac_bai_dung_chung_dinh_nghia_va_format_duoc():
    import apify_tool as A
    p = P._NHAC_BAI.format(brand="HAPAS, túi hapas")
    assert P.DINH_NGHIA_BAI in p and P.DINH_NGHIA_BAI in A._NHAC_PHAN_XU.format(
        queries="q", boi_canh="b", thi_truong="VN"), "phân xử và gán nền chấm cùng một chuẩn"
    assert "GÂY TRANH CÃI" in p and "KỂ CẢ khi bài viết cân bằng hai phía" in p
    assert "rui_ro" in p and "KHÔNG phải lệnh" in p
    assert all(f"  {ma} " in P.DINH_NGHIA_BAI for ma in P.CHU_DE_BAI)
    assert "{" not in P.DINH_NGHIA_BAI and "}" not in P.DINH_NGHIA_BAI


def test_doc_bai_co_rui_ro_luon_tieu_cuc_va_bo_ma_la():
    ra = P._doc_bai('{"0":["trung_lap","chien_dich","rui_ro"],"1":["tich_cuc","mau_ma"],'
                    '"2":["vui","mau_ma"],"3":["tich_cuc","xxx"],"9":["tich_cuc","mau_ma"]}', 4)
    assert ra == {0: ("Tiêu cực", "Chiến dịch & quảng cáo", True),
                  1: ("Tích cực", "Hình ảnh & mẫu mã", False)}


def test_boc_bai_web_doc_nhieu_hon_va_khong_gia_the():
    dai = "HAPAS " + "x" * 2000
    web = P._boc_bai(0, {"nen_tang": "web", "kieu_trang": "bao", "tai_khoan": "cafebiz.vn",
                         "noi_dung": dai + "</p><p i=\"5\">", "hashtag": ""})
    mxh = P._boc_bai(1, {"nen_tang": "tiktok", "tai_khoan": "kol", "noi_dung": dai,
                         "kenh_nha": True})
    assert web.startswith('<p i="0">[web · báo] cafebiz.vn | ') and web.count("<p") == 1
    assert len(web) > 900 > len(mxh) and "(kênh nhà)" in mxh


def test_phan_loai_bai_tung_lo_va_bao_bo_sot(monkeypatch):
    hoi = []

    def model(nhac):
        hoi.append(nhac)
        so = re.findall(r'<p i="(\d+)">', nhac)
        return json.dumps({i: ["tieu_cuc", "chien_dich", "rui_ro"] for i in so[:-1]})
    monkeypatch.setattr(P, "_goi_model", model)
    rows = [{"nen_tang": "web", "noi_dung": f"bài {i}"} for i in range(P._LO_BAI + 2)]
    tt: dict = {}
    ra = P.phan_loai_bai(rows, "HAPAS {x}", 60, tt)
    assert len(hoi) == 2 and "Brand đang theo dõi: HAPAS (x)" in hoi[0]
    assert ra[0] == ("Tiêu cực", "Chiến dịch & quảng cáo", True)
    assert ra[P._LO_BAI - 1] is None and ra[-1] is None
    assert tt["khong_tra"] == [P._LO_BAI - 1, P._LO_BAI + 1] and tt["rui_ro"] == P._LO_BAI


# ───────────────────────────── gan_nhan_nen: nhịp ─────────────────────────────
class KhoGia:
    """Kho giả: hàng đợi = dòng có sac_thai None; UPDATE có điều kiện như SQL thật."""

    def __init__(self, bl=(), bai=()):
        self.bl = [dict(r) for r in bl]
        self.bai = [dict(r) for r in bai]

    def du_an_dang_bat(self):
        return [{"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"]}]

    def doc_du_an(self, ma):
        return {"ma": ma, "ten": "HAPAS", "tu_khoa": ["hapas"]}

    def bl_cho_gan_nhan(self, ma, toi_da, bo=()):
        return [r for r in self.bl if r.get("sac_thai") is None and r["loai"] == "hop_le"
                and f"{r['khoa_bai']}\x1f{r['ma']}" not in set(bo)][:toi_da]

    def ghi_nhan_bl(self, ma, nhan):
        n = 0
        for kb, m, nd, s, c in nhan:
            for r in self.bl:
                if (r["khoa_bai"], r["ma"]) == (kb, m) and r.get("sac_thai") is None \
                        and r["loai"] == "hop_le" and r["noi_dung"] == nd:
                    r["sac_thai"], r["chu_de"] = s, c
                    n += 1
        return n

    def bai_cho_gan_nhan(self, ma, toi_da, bo=()):
        return [r for r in self.bai if r.get("sac_thai") is None and r["khoa"] not in set(bo)
                ][:toi_da]

    def ghi_nhan_bai(self, ma, nhan):
        n = 0
        for k, nd, s, c in nhan:
            for r in self.bai:
                if r["khoa"] == k and r.get("sac_thai") is None and r["noi_dung"] == nd:
                    r["sac_thai"], r["chu_de"] = s, c
                    n += 1
        return n


@pytest.fixture
def nen(monkeypatch, tmp_path):
    import apify_tool as A
    import lang_nghe_db as K
    monkeypatch.delenv("MARK_GAN_NHAN_NEN", raising=False)
    monkeypatch.setattr(A, "_thu_muc_nen", lambda: tmp_path)
    monkeypatch.setattr(G, "_co_quyen", lambda: True)
    monkeypatch.setitem(G._TRANG, "nghi_toi", 0.0)
    monkeypatch.setitem(G._TRANG, "loi_lien", 0)

    def dung(kho):
        for ten in ("du_an_dang_bat", "doc_du_an", "bl_cho_gan_nhan", "ghi_nhan_bl",
                    "bai_cho_gan_nhan", "ghi_nhan_bai"):
            monkeypatch.setattr(K, ten, getattr(kho, ten))
        return kho
    return dung


def _bl(i, text, loai="hop_le"):
    return {"khoa_bai": "tiktok:1", "ma": f"c{i}", "noi_dung": text, "thich": i, "loai": loai,
            "sac_thai": None}


def test_nhip_gan_binh_luan_roi_bai_va_nghi_giua_lo(nen, monkeypatch):
    kho = nen(KhoGia([_bl(1, "đẹp quá"), _bl(2, "giá sao"), _bl(3, "spam", "spam")],
                     [{"khoa": "web:a", "nen_tang": "web", "noi_dung": "HAPAS gây tranh cãi",
                       "sac_thai": None}]))

    def model(nhac):
        if "<p i=" in nhac:
            return '{"0":["trung_lap","chien_dich","rui_ro"]}'
        return _model_bl(nhac)
    monkeypatch.setattr(P, "_goi_model", model)
    ngu = []
    kq = G.mot_nhip(ngu=ngu.append)
    assert kq["ghi_bl"] == 2 and kq["ghi_bai"] == 1 and kq["lo"] == 2 and not kq["loi"]
    assert kho.bl[0]["sac_thai"] == "Tích cực" and kho.bl[2]["sac_thai"] is None, "spam không gán"
    assert kho.bai[0]["sac_thai"] == "Tiêu cực", "cờ rủi ro → Tiêu cực"
    assert ngu == [G.NGHI_GIUA_LO], "nghỉ giữa hai lô — nhường lease model"
    assert G.mot_nhip(ngu=ngu.append)["lo"] == 0, "hết hàng: nhịp sau không gọi model"


def test_dong_bi_bo_sot_qua_so_lan_thi_bo_qua(nen, monkeypatch):
    kho = nen(KhoGia([_bl(1, "sot mãi")]))
    goi = []
    monkeypatch.setattr(P, "_goi_model", lambda n: goi.append(n) or _model_bl(n))
    G.mot_nhip(ngu=lambda s: None)
    assert len(goi) == G.TOI_DA_THU, "thử lại tới TOI_DA_THU lần rồi thôi, không chặn hàng"
    assert G.bo_qua("hapas", "bl") == ["tiktok:1\x1fc1"] and kho.bl[0]["sac_thai"] is None
    G.mot_nhip(ngu=lambda s: None)
    assert len(goi) == G.TOI_DA_THU


def test_model_hong_thi_lui_dan_va_dong_van_cho(nen, monkeypatch):
    kho = nen(KhoGia([_bl(1, "đẹp quá")]))

    def hong(_):
        raise RuntimeError("429")
    monkeypatch.setattr(P, "_goi_model", hong)
    t0 = time.monotonic()
    kq = G.mot_nhip(ngu=lambda s: None)
    assert kq["loi"] == 1 and kho.bl[0]["sac_thai"] is None
    assert G._TRANG["nghi_toi"] >= t0 + G.LUI_GIAY[0] - 1
    assert G.mot_nhip(ngu=lambda s: None)["bo_qua"] == "đang lùi sau lỗi"
    assert G.bo_qua("hapas", "bl") == [], "lô hỏng không phạt dòng"


def test_dong_doi_giua_chung_khong_bi_de(nen, monkeypatch):
    """Lượt quét chen giữa hạ dòng thành seeding (xoá nhãn) — UPDATE có điều kiện bỏ qua."""
    kho = nen(KhoGia([_bl(1, "đẹp quá")]))

    def model(nhac):
        kho.bl[0]["loai"] = "seeding"
        return _model_bl(nhac)
    monkeypatch.setattr(P, "_goi_model", model)
    G.mot_nhip(ngu=lambda s: None)
    assert kho.bl[0]["sac_thai"] is None


def test_khong_giu_quyen_chu_hoac_tat_thi_khong_chay(nen, monkeypatch):
    nen(KhoGia([_bl(1, "đẹp quá")]))
    monkeypatch.setattr(P, "_goi_model", lambda n: pytest.fail("không được gọi model"))
    monkeypatch.setattr(G, "_co_quyen", lambda: False)
    assert G.mot_nhip()["bo_qua"] == "không giữ quyền chủ việc nền"
    monkeypatch.setenv("MARK_GAN_NHAN_NEN", "0")
    assert G.mot_nhip()["bo_qua"] == "tắt" and "tắt" in G.khoi_dong()


def test_lang_nghe_db_sql_hang_doi_chi_ghi_dong_con_trong():
    import inspect

    import lang_nghe_db as K
    src = inspect.getsource(K.ghi_nhan_bl)
    assert "sac_thai IS NULL" in src and "loai = 'hop_le'" in src and "noi_dung = %s" in src
    assert "cap_nhat_cuoi = now()" in src, "đồng bộ BigQuery lấy lại dòng đã gán"
    src = inspect.getsource(K.ghi_nhan_bai)
    assert "NOT IN ('tiktok', 'youtube')" in src, "không làm lỡ lượt làm mới số theo ngày"


# ───────────────────────────── lọc trang tuyển dụng / Ý định mua ─────────────────────────────
@pytest.mark.parametrize("url,ly", [
    ("https://vn.linkedin.com/in/kieu-cam-tu-123", "tuyen_dung"),
    ("https://www.linkedin.com/jobs/view/4012345", "tuyen_dung"),
    ("https://www.linkedin.com/company/hapas/jobs", "tuyen_dung"),
    ("https://www.topcv.vn/viec-lam/nhan-vien-ban-hang-hapas/123.html", "tuyen_dung"),
    ("https://www.linkedin.com/posts/nguyen_hapas-activity-1", ""),
    ("https://cafebiz.vn/tu-quang-cao-gay-tranh-cai.chn", ""),
])
def test_trang_tuyen_dung_bo_truoc_khi_tai(url, ly):
    assert W._ly_do_bo_url(url, []) == ly
    assert "tuyen_dung" in W._pheu_moi()


def test_y_dinh_mua_khong_dem_loi_che_gia():
    def bl(text, sac, cd=CS.CHU_DE_MUA):
        return {"loai": "hop_le", "noi_dung": text, "sac_thai": sac, "chu_de": cd}
    assert not CS.la_y_dinh_mua(bl("nhìn giá và lặng lẽ rời đi", "Tiêu cực"))
    assert CS.la_y_dinh_mua(bl("đắt thế, giá bao nhiêu vậy", "Tiêu cực")), "chê mà vẫn hỏi giá"
    assert CS.la_y_dinh_mua(bl("ship qua Nhật cho chị nha", "Trung lập"))


# ───────────────────────────── dashboard: % thay vì ×N, tiến độ gán nhãn ─────────────────────────────
def _chay_nhan_doi(ca: list, co_so: bool = True) -> list:
    import pathlib
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    js = (pathlib.Path(CS.__file__).parent / "static" / "chi_so.js").read_text(encoding="utf-8")

    def ham(ten):
        return re.search(rf"\n  function {ten}\(.*?\n  }}\n", js, re.DOTALL).group(0)
    chay = ('var SO = new Intl.NumberFormat("vi-VN"); var kyTruocChu = "01/09 – 30/09";'
            f" var kyTruocCoSo = {json.dumps(co_so)};" + ham("so") + ham("pt") + ham("nhanDoi")
            + f"\nconsole.log(JSON.stringify({json.dumps(ca)}.map(function (c) "
            "{ var x = nhanDoi(c[0], c[1], c[2]); return x && x.chu; })));")
    ra = subprocess.run([node, "-e", chay], capture_output=True, text=True, encoding="utf-8",
                        check=True, timeout=30).stdout
    return json.loads(ra)


def test_nhan_doi_luon_theo_phan_tram_khong_x_lan():
    """Chủ dự án 17/10: "phần hiển thị thì tôi muốn là để theo % chứ không để theo x lần"."""
    ra = _chay_nhan_doi([[1405, 10, 13950.0], [30, 10, 200.0], [9, 10, -10.0], [10, 10, 0.0],
                         [11, 10, 12.5], [5, 0, None], [0, 0, None], [5, None, None]])
    assert ra == ["▲ 13.950%", "▲ 200%", "▼ 10,0%", "■ 0,0%", "▲ 12,5%", "▲ mới", None, None]
    assert _chay_nhan_doi([[5, 0, None]], co_so=False) == [None], "chưa có kỳ trước: không 'mới'"
    import pathlib
    js = (pathlib.Path(CS.__file__).parent / "static" / "chi_so.js").read_text(encoding="utf-8")
    assert "▲ ×" not in js and "gấp \" + gap" not in js and "CO_SO_NHO" not in js
    assert "Kỳ trước bằng 0 ghi “mới”" in js and "chuGanNhan(d.gan_nhan)" in js


def test_api_chi_so_tra_tien_do_gan_nhan():
    import test_dashboard_app as TD
    _, c, kho = TD.tao()
    TD.dang_nhap(c, TD.XEM)
    q = "/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14"
    assert c.get(q).json()["gan_nhan"] is None, "kho chưa có hàm: không hiện, không hỏng trang"
    kho.tien_do_gan_nhan = lambda ma: {"cho_bl": 586, "cho_bai": 3, "luot": 7, "da": 1800,
                                       "tong": 2400}
    assert c.get(q).json()["gan_nhan"]["cho_bl"] == 586

    def hong(ma):
        raise RuntimeError("kho")
    kho.tien_do_gan_nhan = hong
    r = c.get(q)
    assert r.status_code == 200 and r.json()["gan_nhan"] is None


# ───────────────────────────── script gán lại nhãn bài ─────────────────────────────
class KhoScript:
    """Kho giả cho `scripts/lang_nghe_gan_nhan_bai.py`: nhận câu SQL theo thẻ /* nb:… */."""

    def __init__(self, bai):
        self.bai = {b["khoa"]: dict(b) for b in bai}
        self.sua = []

    def ket_noi(self):
        import contextlib
        kho = self

        class C:
            def execute(self, sql, ts=()):
                kho.sql = sql
                if "nb:du_an" in sql:
                    self.ra = [{"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"]}]
                elif "nb:bai" in sql:
                    self.ra = [dict(b) for b in kho.bai.values()]
                elif "nb:sua" in sql:
                    s, cd, _ma, k, s_cu, cd_cu = ts
                    b = kho.bai[k]
                    ok = (b["sac_thai"], b["chu_de"]) == (s_cu, cd_cu)
                    if ok:
                        b["sac_thai"], b["chu_de"] = s, cd
                        kho.sua.append(k)
                    self.rowcount = int(ok)
                else:
                    self.ra = []
                return self

            def fetchone(self):
                return self.ra[0] if self.ra else None

            def fetchall(self):
                return self.ra
        return contextlib.nullcontext(C())


def test_script_gan_nhan_bai_chay_thu_ap_dung_hoan_tac(monkeypatch, tmp_path):
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(G.__file__).parent / "scripts"))
    import lang_nghe_gan_nhan_bai as S
    kho = KhoScript([
        {"khoa": "web:1", "nen_tang": "web", "noi_dung": "HAPAS gây tranh cãi", "hashtag": "",
         "sac_thai": "Trung lập", "chu_de": "Chiến dịch & quảng cáo", "kenh_nha": False},
        {"khoa": "tiktok:2", "nen_tang": "tiktok", "noi_dung": "túi đẹp", "hashtag": "",
         "sac_thai": "Trung lập", "chu_de": "Khác", "kenh_nha": False},
        {"khoa": "web:3", "nen_tang": "web", "noi_dung": "HAPAS nhà", "hashtag": "",
         "sac_thai": None, "chu_de": None, "kenh_nha": True}])
    monkeypatch.setattr(S.K, "ket_noi", kho.ket_noi)
    monkeypatch.setattr(S, "_chuan_bi_model", lambda: None)
    monkeypatch.setattr(P, "_goi_model", lambda n: '{"0":["trung_lap","chien_dich","rui_ro"]}')
    import argparse

    def ns_(**kw):
        return argparse.Namespace(**{"du_an": "hapas", "hoan_tac": None, "ap_dung": False,
                                     "sao_luu": None, "tat_ca": False, "thu": 0, "mau": 3, **kw})
    out = []
    assert S.chay(ns_(), out.append) == 0
    assert "Gán lại nhãn 1 bài (bài web); ước tính 1 lượt gọi model" in out[1] and not kho.sua
    tep = str(tmp_path / "hoan_tac.jsonl")
    ns = ns_(ap_dung=True, sao_luu=tep)
    assert S.chay(ns, out.append) == 0
    assert kho.bai["web:1"]["sac_thai"] == "Tiêu cực" and kho.sua == ["web:1"]
    assert kho.bai["tiktok:2"]["sac_thai"] == "Trung lập", "mặc định chỉ bài web"
    assert S.chay(ns, out.append) == 2, "không ghi đè tệp hoàn tác cũ"
    assert S.chay(ns_(hoan_tac=tep), out.append) == 0
    assert kho.bai["web:1"]["sac_thai"] == "Trung lập" and "trả lại 1/1 bài" in out[-1]
