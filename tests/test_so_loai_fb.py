"""Sổ "bài đã loại" với Facebook (18/10/2026, chủ dự án: "rà các chỗ đang trả tiền cho dữ liệu bị
bỏ").

Sổ đã loại (`theo_doi_api.ghi_loai`, review 16/10) chạy đúng với TikTok (id video), Instagram
(shortcode), YouTube, Threads (băm link chuẩn), web (sổ riêng) — phễu lượt 9–10 "đã loại trước
56/30". Facebook thì KHÔNG: khoá bài theo link mang pfbid, mà pfbid đổi mỗi lượt cào (đo vòng 1
17/10), nên bài Facebook đã bị AI loại (lạc đề 5–10 bài/lượt ở lượt 7–11) không bao giờ khớp lại sổ
và bị gửi AI xét lại mỗi lượt. Nay sổ ghi thêm khoá ổn định: id số và chủ bài + phút + nội dung."""
from __future__ import annotations

import datetime
import time

from test_theo_doi import DU_AN, GiaKhoTk, mo  # noqa: F401

import apify_tool as A
import theo_doi as T

VN = datetime.timezone(datetime.timedelta(hours=7))
LUC = datetime.datetime(2026, 10, 17, 9, 5, 30, tzinfo=VN)


def _hit(pfbid: str, phut: int = 5, chu: str = "Pass lại túi hapas giá rẻ, ib mình") -> tuple:
    return ({"platform": "facebook", "link": f"https://www.facebook.com/shopx/posts/{pfbid}",
             "username": "shopx", "kenh": "Shop X", "text": chu, "hashtags": ""},
            LUC.replace(minute=phut))


def _tk() -> dict:
    return {"pheu": {}, "pham_vi": {"tu": "2026-09-18T00:00:00+07:00"}, "moi": 0, "cu": 0,
            "de_xuat": 0, "ai": ""}


def test_bai_facebook_bi_loai_khop_lai_du_pfbid_doi(mo):  # noqa: F811
    GiaKhoTk(mo)
    goi_ai: list[int] = []

    def ai(cho, tu, boi_canh, thi_truong, han):
        goi_ai.append(len(cho))
        return ({i: (False, "lac_de") for i in range(len(cho))},
                {"trang_thai": "đã chạy", "_sac_thai": {}, "_chu_de": {}})
    mo.setattr(A, "_phan_xu_ai", ai)
    da = dict(DU_AN, tu_khoa=["hapas"])
    T._tach_va_giu(da, 9, [_hit("pfbid0AAA")], ["hapas"], time.monotonic() + 60, _tk())
    assert goi_ai == [1]
    # Lượt sau: CÙNG bài, pfbid khác (actor trả mỗi lượt một pfbid) → khớp sổ, không gửi AI lại.
    tk = _tk()
    T._tach_va_giu(da, 10, [_hit("pfbid0BBB")], ["hapas"], time.monotonic() + 60, tk)
    assert goi_ai == [1] and tk["pheu"]["facebook"]["da_loai_truoc"] == 1
    # Bài KHÁC của cùng trang (phút khác hoặc chữ khác) vẫn được xét.
    tk = _tk()
    T._tach_va_giu(da, 11, [_hit("pfbid0CCC", phut=40), _hit("pfbid0DDD", chu="Túi hapas mới")],
                   ["hapas"], time.monotonic() + 60, tk)
    assert goi_ai == [1, 2] and not tk["pheu"]["facebook"].get("da_loai_truoc")


def test_khoa_on_dinh_chi_cho_facebook():
    d, dt = _hit("pfbid0AAA")
    k = T._khoa_loai_on_dinh(d, dt)
    assert len(k) == 1 and k[0].startswith("facebook:nd:shopx|2026-10-17T02:05:00+00:00|")
    so = dict(d, link="https://www.facebook.com/123456789/posts/987654321012")
    assert T._khoa_loai_on_dinh(so, dt)[0] == "facebook:id:987654321012"
    assert T._khoa_loai_on_dinh(dict(d, platform="tiktok"), dt) == []
    assert T._khoa_loai_on_dinh(dict(d, text="🙂"), dt) == []          # ảnh không chữ: không gộp
