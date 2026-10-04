"""B3 (E2E 04-05/10/2026): thống kê sắc thái KHÔNG đếm tiếng của chính thương hiệu.

`social_deep_dive` đếm cả trả lời của hapas.official vào sắc thái (Mark phải đếm tay lại:
73,3% so với 71,4%); social_listen đếm cả 3 bài của chính HAPAS. Dòng của brand vẫn nằm
trong sheet (cột "Nguồn" = "thương hiệu") nhưng không vào số đếm/%, báo riêng một câu.
Không gọi Apify, Lark hay model thật.
"""
from __future__ import annotations

import json

import apify_tool as A
import deep_dive_tool as D
import phan_loai as P
from test_binh_luan_phan_tich import moi_truong  # noqa: F401

TC, TI, TL = (P.SAC_THAI[k] for k in "+-=")
VID = "https://www.tiktok.com/@hapas.official/video/7000123"


# ───────────────────────── nhận ra tài khoản của brand ─────────────────────────
def test_nhan_ra_tai_khoan_nha(monkeypatch):
    monkeypatch.delenv("SOCIAL_TAI_KHOAN_NHA", raising=False)
    assert P.la_tai_khoan_nha("hapas.official") and P.la_tai_khoan_nha("@Hapas.VN")
    assert P.la_tai_khoan_nha("hapas_official"), "khác dấu chấm/gạch vẫn là một handle"
    assert not P.la_tai_khoan_nha("hapas_fan_club") and not P.la_tai_khoan_nha("")
    # Brand của lượt quét: handle chính chủ, không phải shop bán lại hay fan.
    assert P.la_tai_khoan_nha("HAPAS Official", ["hapas"])
    assert P.la_tai_khoan_nha("HAPAS", "hapas")
    assert not P.la_tai_khoan_nha("hapasshop", ["hapas"])
    assert not P.la_tai_khoan_nha("HAPAS THAILAND", ["hapas"])
    # Chủ bài/video trả lời bình luận trên bài của chính mình.
    assert P.la_tai_khoan_nha("koc.linh", chu_bai="@Koc.Linh")
    assert not P.la_tai_khoan_nha("nguoi.xem", chu_bai="koc.linh")


def test_danh_sach_handle_doi_duoc_bang_env(monkeypatch):
    monkeypatch.setenv("SOCIAL_TAI_KHOAN_NHA", "brand.x, brand.y")
    assert P.la_tai_khoan_nha("brand.y")
    assert not P.la_tai_khoan_nha("hapas.official"), "env THAY danh sách mặc định"


# ───────────────────────── đếm ─────────────────────────
def _dong(text, sac, nha=False, likes=0):
    return {"platform": "tiktok", "bai": VID, "text": text, "likes": likes,
            "sac_thai": sac, "chu_de": P.CHU_DE["SP"], "cua_thuong_hieu": nha}


def test_dem_bo_dong_cua_thuong_hieu_va_bao_rieng():
    rows = ([_dong("đẹp", TC)] * 5 + [_dong("chán", TI)] * 2
            + [_dong("cảm ơn bạn", P.NHAN_NHA, True, likes=99)] * 2)
    tk = P.dem(rows)
    assert tk["tong"] == 7 and tk["da_phan_loai"] == 7 and tk["chua_phan_loai"] == 0
    assert tk["cua_thuong_hieu"] == 2
    assert tk["sac_thai"][TC] == {"so": 5, "ti_le": 71.4, "ti_le_theo_like": None}
    assert tk["theo_bai"][VID]["tong"] == 7 and tk["theo_nen_tang"]["tiktok"]["tong"] == 7
    dong = P.dong_thong_ke(tk)
    assert dong.startswith("Đã phân loại 7/7 bình luận: Tích cực 5 (71,4%)")
    assert dong.endswith(" 2 phản hồi của chính thương hiệu (không tính).")
    assert all(x["text"] != "cảm ơn bạn" for ds in P.trich_dan(rows).values() for x in ds)


def test_khong_co_dong_thuong_hieu_thi_cau_giu_nguyen():
    tk = P.dem([_dong("đẹp", TC)])
    assert tk["cua_thuong_hieu"] == 0 and "thương hiệu" not in P.dong_thong_ke(tk)


# ───────────────────────── social_deep_dive ─────────────────────────
def test_dau_hieu_chu_kenh_youtube_va_tiktok():
    yt = D._yt_dong({"authorDisplayName": "@HapasChannel", "channelId": "UC1",
                     "authorChannelId": {"value": "UC1"}, "textOriginal": "cảm ơn"}, "v1")
    khach = D._yt_dong({"authorDisplayName": "A", "channelId": "UC1",
                        "authorChannelId": {"value": "UC9"}, "textOriginal": "x"}, "v1")
    assert yt["cua_chu"] is True and khach["cua_chu"] is False
    ac = D._map_youtube([{"author": "@x", "comment": "hi", "authorIsChannelOwner": True}])[0]
    assert ac[0]["cua_chu"] is True
    rows = [{"kenh": "hapas.official", "bai": VID, "link": VID},    # chủ video TikTok
            {"kenh": "khach", "bai": VID, "link": VID},
            {"kenh": "koc.a", "bai": "https://www.threads.net/@koc.a/post/Abc", "link": ""},
            dict(yt, bai="https://www.youtube.com/watch?v=v1"),
            {"kenh": "HAPAS Official", "bai": "https://www.facebook.com/p/1", "link": ""}]
    assert D._danh_dau_thuong_hieu(rows, ["hapas"]) == 4
    assert [r["cua_thuong_hieu"] for r in rows] == [True, False, True, True, True]


def test_deep_dive_tra_loi_cua_brand_o_sheet_nhung_khong_tinh(moi_truong):  # noqa: F811
    ap, _, sheet, ghi_tab = moi_truong
    ap.tra = lambda payload, limit: [
        {"cid": "1", "uniqueId": "a", "text": "túi đẹp quá", "videoWebUrl": VID},
        {"cid": "2", "uniqueId": "b", "text": "giao chậm", "videoWebUrl": VID},
        {"cid": "3", "uniqueId": "hapas.official", "text": "túi đẹp, cảm ơn bạn",
         "videoWebUrl": VID, "repliesToId": "1"}]
    kq = json.loads(D._handle({"post_urls": [VID]}))
    hd = sheet[0]
    i_nguon, i_sac = hd.index("Nguồn"), hd.index("Sắc thái")
    nguon = {r[1]: r[i_nguon] for r in sheet[1:]}
    assert nguon == {"a": "khách", "b": "khách", "hapas.official": "thương hiệu"}
    assert {r[1]: r[i_sac] for r in sheet[1:]}["hapas.official"] == P.NHAN_NHA
    tk = kq["thong_ke"]
    assert tk["tong"] == 2 and tk["cua_thuong_hieu"] == 1
    assert tk["sac_thai"][TC]["so"] == 1 and tk["sac_thai"][TC]["ti_le"] == 50.0
    assert "1 phản hồi của chính thương hiệu (không tính)" in kq["dong_thong_ke"]
    assert "KHÔNG tính vào số/%" in kq["note"]
    bang = next(rows for x in ghi_tab if isinstance(x, tuple) for rows in [x[1]])
    assert ["1 phản hồi của chính thương hiệu (không tính)", "", "", "", ""] in bang


# ───────────────────────── social_listen ─────────────────────────
def test_bai_cua_brand_khong_vao_thong_ke_bai():
    bai = [{"platform": "threads", "username": u, "kenh": u, "likes": 1, "views": 1,
            "text": t, "link": f"l{n}", "_sac_thai": s}
           for n, (u, t, s) in enumerate([("hapas.official", "BST mới", TC),
                                          ("hapas_vn", "sale", TC),
                                          ("khach1", "xinh", TC),
                                          ("khach2", "dở", TI)])]
    assert A.danh_dau_bai_nha(bai, ["hapas"]) == 2
    assert [A._nguon_bai(d) for d in bai] == ["thương hiệu"] * 2 + ["khách"] * 2
    st = A.thong_ke_sac_thai(bai)
    tk = st["thong_ke"]
    assert tk["tong"] == 2 and tk["cua_thuong_hieu"] == 2
    assert tk["sac_thai"][TC]["ti_le"] == 50.0
    assert st["dong_thong_ke"].endswith(" 2 bài của chính thương hiệu (không tính).")
    assert [x["link"] for x in st["trich_dan"][TC]] == ["l2"]
    bang = A._bang_thong_ke(st)
    assert ["2 bài của chính thương hiệu (không tính)", "", "", "", ""] in bang
    assert all(len(r) == 5 for r in bang)
