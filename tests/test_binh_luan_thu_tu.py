"""Bình luận: phần chạy theo thứ tự ưu tiên TOÀN CỤC giữa mọi nền tảng + sàn công bằng (18/10/2026).

Đo thật lượt 17 (18/10): ghi chú "bình luận: ưu tiên 102 bài chưa cào thiếu nhiều nhất (Threads 966,
Facebook 868, Threads 418)" nhưng các phần chạy THEO NỀN TẢNG — các lô Facebook chạy trước, tiêu
1,81 USD, mười phần Threads sau đó đều "bỏ qua (trần còn 0,02 USD … < mức actor đòi 0,10 USD)".
Threads chưa từng được cào bình luận trong lượt thường; phải chạy riêng một lượt chỉ bật Threads
(lượt 18) mới được 674 bình luận."""
from __future__ import annotations

import time

import pytest
from test_theo_doi import (  # noqa: F401
    DU_AN,
    GiaApify,
    GiaKhoBl,
    GiaViec,
    _lay_bl,
    mo,
    nhan_gia,
)

import apify_tool as A
import deep_dive_tool as D
import theo_doi as T

BAT = {"binh_luan": {"threads": {"bat": True}}}
DA = dict(DU_AN, bl_bat=True, bl_so_bai=10, bl_moi_bai=0, cau_hinh=BAT)


def _b(p, khoa, co, **kw):
    link = {"facebook": f"https://www.facebook.com/hapas/posts/{khoa}",
            "threads": f"https://www.threads.com/@hapas.vn/post/C{khoa}"}[p]
    return {"khoa": f"{p}:{khoa}", "nen_tang": p, "link": link, "tai_khoan": "hapas.vn",
            "tac_gia": "HAPAS", "binh_luan": co, "bl_lay_luc": None, "bl_da_lay": None,
            "bl_lay_khi_co": None, "nguon_loai": "kenh_nha", **kw}


class TieuHetTran(GiaApify):
    """Mỗi run tiêu ĐỦ trần USD gửi Apify — trường hợp xấu nhất của ngân sách."""

    def run_actor(self, actor, payload, limit, mem=None, deadline=None, min_charge=0, *,
                  tran_usd=None, mot_phan=False, nen_tang=None):
        items, meta = super().run_actor(actor, payload, limit, mem, deadline, min_charge,
                                        tran_usd=tran_usd, mot_phan=mot_phan, nen_tang=nen_tang)
        return items, {**meta, "usd": float(tran_usd or 0)}


def test_phan_xep_toan_cuc_threads_966_truoc_facebook_868(mo):  # noqa: F811
    """Đúng ca lượt 17: Threads 966, Facebook 868, Threads 418 — sổ xếp đúng thứ tự đó."""
    v = GiaViec({}, [])
    ds = [_b("facebook", "f868", 868), _b("threads", "t966", 966), _b("threads", "t418", 418)]
    T._tao_cac_phan_bl(v, ds, 0)
    cac = T._phan_bl(v)
    assert [(x["nen_tang"], x["thieu"]) for x in cac] == [
        ("threads", 966), ("facebook", 868), ("threads", 418)]
    # Bản cũ nối theo `BL_NEN_TANG`: [facebook 868, threads 966, threads 418].
    assert [x["id"] for x in cac] == ["bl-threads-0", "bl-facebook-1", "bl-threads-2"]
    assert all(x["chua_cao"] for x in cac)
    # Bài đã cào (dù thiếu nhiều) đứng sau mọi bài chưa cào — cùng khoá `_uu_tien_bl`.
    v2 = GiaViec({}, [])
    T._tao_cac_phan_bl(v2, [_b("threads", "cu", 3000, bl_lay_luc=1, bl_da_lay=10),
                            _b("facebook", "moi", 40)], 0)
    assert [x["nen_tang"] for x in T._phan_bl(v2)] == ["facebook", "threads"]


def test_lay_binh_luan_chay_threads_truoc_va_pheu_noi_dung_thu_tu(mo, nhan_gia):  # noqa: F811
    GiaKhoBl(mo, [_b("facebook", "f868", 868), _b("threads", "t966", 966),
                  _b("threads", "t418", 418)])
    ap = GiaApify(mo, items=[], usd=0.01)
    tk = _lay_bl(GiaViec({}, []), DA, 17, 5.0, time.monotonic() + 300)
    assert [g["actor"] for g in ap.gui] == [D._ACTORS["threads"], D._ACTORS["facebook"],
                                            D._ACTORS["threads"]]
    # Câu thứ tự đứng ngay sau câu ưu tiên — cùng thứ tự với câu ưu tiên.
    i = next(i for i, c in enumerate(tk["ghi_chu"]) if c.startswith("bình luận: ưu tiên"))
    assert tk["ghi_chu"][i] == ("bình luận: ưu tiên 3 bài chưa cào thiếu nhiều nhất (Threads 966, "
                                "Facebook 868, Threads 418)")
    assert tk["ghi_chu"][i + 1] == "bình luận: thứ tự chạy Threads 966 → Facebook 868 → Threads 418"


def test_ngan_sach_chat_moi_nen_tang_van_co_mot_lo(mo, nhan_gia):  # noqa: F811
    """Facebook có 3 lô ưu tiên cao hơn mọi bài Threads, tháng còn 0,5 USD, mỗi run tiêu đủ trần.

    Bản cũ (luật giữ 50% cho các lô sau): 0,25 → 0,12 → 0,10 cho ba lô Facebook, còn 0,03 USD —
    Threads "bỏ qua (trần còn 0,03 USD < 0,10)". Nay lô Facebook thứ 3 NHƯỜNG sàn: Threads chạy
    trước với 0,10, rồi lô Facebook thứ 3 xét lại với phần còn (0,03 → bỏ qua, có lý do)."""
    GiaKhoBl(mo, [_b("facebook", "a", 1200), _b("facebook", "b", 1100),
                  _b("facebook", "c", 1000), _b("threads", "t", 50)])
    ap = TieuHetTran(mo, items=[])
    v = GiaViec({}, [])
    tk = _lay_bl(v, DA, 17, 0.5, time.monotonic() + 300)
    assert [(g["actor"], g["tran_usd"]) for g in ap.gui] == [
        (D._ACTORS["facebook"], 0.25), (D._ACTORS["facebook"], 0.12), (D._ACTORS["threads"], 0.1)]
    cac = {x["bai"][0]["khoa"]: x for x in T._phan_bl(v)}
    assert cac["threads:t"]["trang_thai"] == "xong"
    assert cac["facebook:c"]["ma"] == "NGAN_SACH" and "0,03" in cac["facebook:c"]["ly_do"]
    assert ("bình luận: thứ tự chạy Facebook 1.200 → Facebook 1.100 → Threads 50 (kéo lên: sàn "
            "công bằng)") in tk["ghi_chu"]
    assert any(c.startswith("bình luận Facebook: bỏ qua") for c in tk["ghi_chu"])
    assert tk["usd"] == pytest.approx(0.47)


def test_du_tien_thi_khong_keo_len(mo, nhan_gia):  # noqa: F811
    """Ngân sách rộng: thứ tự đúng ưu tiên, không lô nào nhường."""
    GiaKhoBl(mo, [_b("facebook", "a", 1200), _b("facebook", "b", 1100), _b("threads", "t", 50)])
    ap = TieuHetTran(mo, items=[])
    tk = _lay_bl(GiaViec({}, []), DA, 17, 20.0, time.monotonic() + 300)
    assert [g["actor"] for g in ap.gui] == [D._ACTORS["facebook"], D._ACTORS["facebook"],
                                            D._ACTORS["threads"]]
    assert not any("kéo lên" in c for c in tk["ghi_chu"])


def test_chon_phan_san_uu_tien_nen_tang_ua_tien_cao_hon(monkeypatch):
    """Ba nền tảng, phần còn 0,15 USD < hai sàn 0,20: lô đã có lượt nhường cho nền tảng chưa có lượt
    có lô ĐẦU ưu tiên cao nhất; lô đầu của một nền tảng không bao giờ nhường (không lặp vô tận)."""
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 5.0, True))
    f1 = {"nen_tang": "facebook", "trang_thai": "xong", "gia": 0.0025}
    f2 = {"nen_tang": "facebook", "trang_thai": "cho", "gia": 0.0025}
    th = {"nen_tang": "threads", "trang_thai": "cho", "gia": 0.0025}
    tt = {"nen_tang": "tiktok", "trang_thai": "cho", "gia": 0.0004}
    yt = {"nen_tang": "youtube", "trang_thai": "cho", "gia": 0.0}
    cac = [f1, f2, yt, th, tt]
    cho = [f2, yt, th, tt]
    assert T._san_bl(cac, cho, "facebook") == {"threads": 0.1, "tiktok": 0.1}   # YouTube miễn phí
    assert T._chon_phan_bl(cac, cho, 0.15) == (th, "threads")
    assert T._chon_phan_bl(cac, cho, 0.30) == (f2, None)          # đủ sàn: không nhường
    # Lô đầu Threads không nhường, chỉ bị cắt trần xuống mức nó cần (0,10) để giữ sàn TikTok.
    assert T._chon_phan_bl(cac, [th, tt], 0.15) == (th, None)
    assert T._tran_lo_bl(5.0, 0.15, 1.0, 0.0, 1.0, 0.0, 0.1) == 0.1
    # Trần console Threads dưới mức một lô: không giữ sàn cho nó (không bao giờ chạy được).
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (
        1000, 0.05 if p == "threads" else 5.0, True))
    assert T._san_bl(cac, cho, "facebook") == {"tiktok": 0.1}
    # Phần đang dở (khởi động lại giữa run) luôn đọc tiếp trước.
    dang = dict(tt, trang_thai="dang_chay")
    assert T._chon_phan_bl(cac, [f2, th, dang], 0.0) == (dang, None)


def test_tran_lo_san_khong_cat_duoi_muc_lo_can():
    assert T._tran_lo_bl(5.0, 1.0, 9.0, 0.0, 4.0, 0.0, 0.3) == 0.7
    assert T._tran_lo_bl(5.0, 0.25, 9.0, 0.0, 4.0, 0.0, 0.2) == 0.1     # không dưới 0,10
    assert T._tran_lo_bl(5.0, 0.05, 9.0, 0.0, 4.0, 0.0, 0.2) == 0.05    # P < mức cần: bỏ qua
    assert T._tran_lo_bl(2.0, 5.0, 1.0, 0.8, 4.0) == T._tran_lo_bl(2.0, 5.0, 1.0, 0.8, 4.0, 0.0, 0.0)


def test_khoi_dong_lai_doc_tiep_dung_thu_tu_trong_so(mo, nhan_gia):  # noqa: F811
    """Phần đã lập nằm trong sổ: bot khởi động lại không chọn bài lại, phần đang dở đọc tiếp run cũ
    TRƯỚC, các phần còn lại chạy đúng thứ tự trong sổ."""
    kho = GiaKhoBl(mo, [_b("facebook", "f868", 868), _b("threads", "t966", 966),
                        _b("threads", "t418", 418)])
    v = GiaViec({}, [])
    T._tao_cac_phan_bl(v, [dict(b) for b in kho.bai], 0)
    cac = T._phan_bl(v)
    cac[0].update(trang_thai="xong", usd_so=0.3)                     # Threads 966 đã xong
    cac[2].update(trang_thai="dang_chay", run_id="r-cu", tran_usd=0.4)   # Threads 418 đang dở
    thu_tu = [x["id"] for x in cac]
    ap = GiaApify(mo, items=[], usd=0.01)
    tk = _lay_bl(v, DA, 17, 5.0, time.monotonic() + 300)
    assert kho.hoi == [] and ap.doc_tiep == ["r-cu"]
    assert [g["actor"] for g in ap.gui] == [D._ACTORS["facebook"]]
    assert [x["id"] for x in T._phan_bl(v)] == thu_tu
    assert "bình luận: thứ tự chạy Threads 418 → Facebook 868" in tk["ghi_chu"]


def test_phan_lap_truoc_18_10_khong_co_khoa_thieu():
    assert T._nhan_lo_bl({"nen_tang": "facebook", "bai": [{"binh_luan": 1234}, {}]}) == \
        "Facebook 1.234"
    assert T._cau_thu_tu_bl(["a"]) == ""
    assert T._cau_thu_tu_bl([str(i) for i in range(8)]) == \
        "bình luận: thứ tự chạy 0 → 1 → 2 → 3 → 4 → 5 → … (+2 lô)"
