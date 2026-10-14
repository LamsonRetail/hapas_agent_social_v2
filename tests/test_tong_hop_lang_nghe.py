"""Tổng hợp kiểu dashboard của social_listen (13/10/2026, `tong_hop_lang_nghe`).

Chủ agent so Mark với dashboard Kompa của HAPAS: thiếu xu hướng theo ngày, nguồn nổi bật
theo thảo luận, chủ đề × sắc thái, từ khoá nổi bật, bình luận YouTube kèm sắc thái. Mọi
số ở đây do CODE đếm — các bài dưới đây tính tay từng con số để canh. Không gọi model,
Apify, YouTube hay Lark thật.
"""
from __future__ import annotations

import datetime
import json
import re
import time

import pytest

import apify_tool as A
import phan_loai
import quet_lon as Q
import sheet_lon
import tong_hop_lang_nghe as TH
from test_phan_xu_ai import NOW, _phan_xu_gia, quet  # noqa: F401
from test_viec_nen import _hang, _TS_AI  # noqa: F401

VN = A._VN_TZ
TC, TI, TL = (phan_loai.SAC_THAI[k] for k in "+-=")
CHUA = phan_loai.CHUA
CD = phan_loai.CHU_DE_BAI


def _d(y, m, d, h=10, mi=0, tz=VN):
    return datetime.datetime(y, m, d, h, mi, tzinfo=tz)


def _b(platform="tiktok", kenh="k", comments=0, sac=None, chu_de=None, nha=False, **kw):
    d = {"platform": platform, "kenh": kenh, "username": kw.pop("username", ""),
         "followers": 0, "views": 0, "likes": 0, "comments": comments, "shares": 0,
         "hashtags": "", "text": "", "link": f"https://x/{kenh}/{comments}"}
    d.update(kw)
    if sac:
        d["_sac_thai"] = sac
    if chu_de:
        d["_chu_de"] = chu_de
    d["_cua_thuong_hieu"] = nha
    return d


# ───────────────────────── xu hướng ─────────────────────────
def _bai_xu_huong():
    utc = datetime.timezone.utc
    return [
        (_b(comments=5, sac=TC), _d(2026, 9, 20, 10)),
        (_b(comments=0, sac=TI), _d(2026, 9, 20, 22)),
        (_b(comments=10, sac=TC, nha=True), _d(2026, 9, 27, 9)),
        (_b(comments=20), _d(2026, 10, 3, 23)),
        # 18:30 UTC ngày 02/10 = 01:30 giờ VN ngày 03/10 — phải rơi vào ngày 03/10.
        (_b(comments=1, sac=TL), datetime.datetime(2026, 10, 2, 18, 30, tzinfo=utc)),
        (_b(comments=0, sac=TL), _d(2026, 10, 1)),
    ]


def test_xu_huong_du_moi_ngay_dem_dung_va_doi_gio_vn():
    xh = TH.xu_huong(_bai_xu_huong(), _d(2026, 9, 20, 0), _d(2026, 10, 3, 23, 59))
    assert xh["don_vi"] == "ngày" and len(xh["dong"]) == 14, "đủ 14 ngày kể cả ngày 0 bài"
    g = {r["moc"]: r for r in xh["dong"]}
    n20, n27, n03 = (datetime.date(2026, 9, 20), datetime.date(2026, 9, 27),
                     datetime.date(2026, 10, 3))
    assert (g[n20]["bai"], g[n20]["binh_luan"], g[n20]["thao_luan"]) == (2, 5, 7)
    assert (g[n20][TC], g[n20][TI]) == (1, 1)
    assert (g[n27]["bai"], g[n27]["bai_thuong_hieu"], g[n27]["thao_luan"]) == (1, 1, 11)
    assert g[n27][TC] == 0, "bài của thương hiệu không vào sắc thái"
    assert (g[n03]["bai"], g[n03]["binh_luan"], g[n03]["thao_luan"]) == (2, 21, 23)
    assert (g[n03][TL], g[n03][CHUA]) == (1, 1)
    assert g[datetime.date(2026, 9, 21)]["bai"] == 0
    assert xh["dinh"]["moc"] == n03 and xh["dinh"]["thao_luan"] == 23
    ss = xh["so_sanh"]
    assert (ss["ky_nay"]["tu"], ss["ky_nay"]["den"]) == (n27, n03)
    assert (ss["ky_nay"]["bai"], ss["ky_nay"]["thao_luan"]) == (4, 35)
    assert (ss["ky_truoc"]["bai"], ss["ky_truoc"]["thao_luan"]) == (2, 7)
    assert ss["doi_thao_luan"] == 400.0 and ss["doi_bai"] == 100.0


def test_xu_huong_khoang_ngan_khong_so_sanh_ky_truoc_rong_khong_chia_0():
    xh = TH.xu_huong([(_b(), _d(2026, 10, 5))], _d(2026, 10, 1, 0), _d(2026, 10, 10, 23))
    assert xh["so_sanh"] is None, "dưới 14 ngày thì không so 7 ngày với 7 ngày"
    xh = TH.xu_huong([(_b(), _d(2026, 10, 10))], _d(2026, 9, 27, 0), _d(2026, 10, 10, 23))
    assert xh["so_sanh"]["doi_thao_luan"] is None, "kỳ trước 0 thì không ra % (không chia 0)"
    xh = TH.xu_huong([], _d(2026, 10, 1, 0), _d(2026, 10, 3, 23))
    assert xh["dinh"] is None and all(r["bai"] == 0 for r in xh["dong"])


def test_xu_huong_khoang_dai_gom_theo_tuan_moc_dau_kep_vao_khoang():
    bai = [(_b(), _d(2026, 1, 3)), (_b(comments=4), _d(2026, 1, 6)), (_b(), _d(2026, 6, 30))]
    xh = TH.xu_huong(bai, _d(2026, 1, 1, 0), _d(2026, 6, 30, 23))
    assert xh["don_vi"] == "tuần" and xh["so_sanh"] is None
    moc = [r["moc"] for r in xh["dong"]]
    assert moc[0] == datetime.date(2026, 1, 1), "tuần đầu bắt đầu đúng ngày đầu khoảng (thứ Năm)"
    assert moc[1] == datetime.date(2026, 1, 5) and all(m.weekday() == 0 for m in moc[1:])
    g = {r["moc"]: r for r in xh["dong"]}
    assert g[datetime.date(2026, 1, 1)]["bai"] == 1
    assert g[datetime.date(2026, 1, 5)]["thao_luan"] == 5
    assert g[datetime.date(2026, 6, 29)]["bai"] == 1
    assert sum(r["bai"] for r in xh["dong"]) == 3


# ───────────────────────── nguồn nổi bật ─────────────────────────
def test_nguon_noi_bat_gom_kenh_xep_theo_thao_luan():
    bai = [
        (_b("tiktok", "Me4con", 100, username="me4con.102", views=1000, link="a1",
            followers=10, sac=TC), None),
        (_b("tiktok", "me4con", 50, username="@ME4CON.102", views=5000, link="a2",
            followers=30, sac=TI), None),
        (_b("tiktok", "Quỳnh phá kén", 300, username="quynhphaken", views=10, link="b1"),
         None),
        (_b("tiktok", "HAPAS", 0, username="hapas.official", nha=True, sac=TC), None),
        (_b("facebook", "Bừng Sáng", 1000, link="f1"), None),
    ]
    ng = TH.nguon_noi_bat(bai, toi_da=2)
    assert list(ng["theo_nen_tang"]) == ["facebook", "tiktok"], "nền tảng nhiều thảo luận trước"
    tt = ng["theo_nen_tang"]["tiktok"]
    assert [g["kenh"] for g in tt] == ["Quỳnh phá kén", "Me4con"] and ng["so_kenh"]["tiktok"] == 3
    me = tt[1]
    assert (me["bai"], me["binh_luan"], me["thao_luan"], me["views"]) == (2, 150, 152, 6000)
    assert me["followers"] == 30 and me["link_noi_bat"] == "a2"
    assert (me[TC], me[TI]) == (1, 1) and me["thuong_hieu"] is False
    full = TH.nguon_noi_bat(bai)["theo_nen_tang"]["tiktok"]
    assert full[-1]["kenh"] == "HAPAS" and full[-1]["thuong_hieu"] is True
    assert full[-1][TC] == 0, "bài của thương hiệu không vào sắc thái của nguồn"


# ───────────────────────── chủ đề ─────────────────────────
def test_chu_de_x_sac_thai_ti_le_tren_bai_da_gan():
    gia = CD["gia_ca"]
    bai = [(_b(sac=TC, chu_de=gia), None), (_b(sac=TI, chu_de=gia), None),
           (_b(sac=TI, chu_de=gia), None), (_b(sac=TC, chu_de=CD["chien_dich"]), None),
           (_b(sac=TL), None), (_b(sac=TC, chu_de=gia, nha=True), None)]
    cd = TH.chu_de(bai)
    assert (cd["tong"], cd["da_gan"], cd["chua_gan"]) == (5, 4, 1)
    dong = cd["dong"]
    assert [g["chu_de"] for g in dong] == [gia, CD["chien_dich"], CHUA]
    assert (dong[0]["so"], dong[0]["ti_le"], dong[0][TC], dong[0][TI]) == (3, 75.0, 1, 2)
    assert dong[1]["ti_le"] == 25.0
    assert dong[2]["ti_le"] is None and dong[2][TL] == 1, "chưa phân loại không có %"


def test_chu_de_nhan_la_khong_tinh():
    cd = TH.chu_de([(_b(chu_de="Thời tiết"), None)])
    assert cd["da_gan"] == 0 and cd["dong"][0]["chu_de"] == CHUA


# ───────────────────────── từ khoá ─────────────────────────
def test_tu_khoa_cum_hai_chu_hashtag_bo_hu_tu_va_tu_khoa_dang_quet():
    bai = [
        (_b(text="Túi xách đẹp quá, túi xách này giá rẻ! #hapas #TuiXach #fyp "
                 "https://x.com/a?b=1 @ban.than", sac=TC), None),
        (_b(text="mua túi xách ở hapas store", hashtags="tuixach, hapas", sac=TI), None),
        (_b(text="Nước hoa thơm lâu. Nước hoa đỉnh", sac=TC), None),
        (_b(text="nước hoa của hapas thơm"), None),
        (_b(text="túi xách túi xách", nha=True), None),
    ]
    tk = TH.tu_khoa(bai, ["hapas"])
    assert tk["so_bai"] == 4
    assert [(g["tu"], g["so_bai"]) for g in tk["dong"]] == [
        ("#tuixach", 2), ("nước hoa", 2), ("túi xách", 2)], \
        "cụm 1 bài bị bỏ; #fyp, #hapas, 'hapas store', bài brand, link, @tag không vào"
    g = {x["tu"]: x for x in tk["dong"]}
    assert (g["túi xách"][TC], g["túi xách"][TI]) == (1, 1)
    assert g["nước hoa"][CHUA] == 1


def test_tu_khoa_truy_van_nhieu_chu_khong_xoa_chu_chung():
    bai = [(_b(text="túi xách mới, túi hapas đẹp"), None),
           (_b(text="túi xách xinh, túi hapas xịn"), None)]
    tu = [g["tu"] for g in TH.tu_khoa(bai, ["túi hapas"])["dong"]]
    assert "túi xách" in tu and "túi hapas" not in tu


def test_the_youtube_nhieu_chu_khong_thanh_hashtag_gia():
    """snippet.tags YouTube nhiều chữ ("túi xách nữ") nối ", " vào `hashtags` — trước đây
    tách theo khoảng trắng ra '#túi', '#xách', '#nữ' (rà 13/10/2026)."""
    bai = [(_b("youtube", text="review", hashtags="túi xách nữ, balo thời trang, hapasvn2, "
                                                  "quatang2010"), None) for _ in range(3)]
    tu = [g["tu"] for g in TH.tu_khoa(bai, ["hapas"])["dong"]]
    assert tu == ["#quatang2010"], tu


def test_ten_kenh_va_cum_tu_nguoi_la_duoc_lam_sach_truoc_khi_vao_cau():
    bai = [(_b(kenh="<b>Kênh</b>\nX", comments=5,
               text="<script> mua ngay <script> mua ngay"), _d(2026, 10, 1)),
           (_b(kenh="<b>Kênh</b>\nX", text="<script> mua ngay"), _d(2026, 10, 1))]
    th = TH.tong_hop(bai, _d(2026, 10, 1, 0), _d(2026, 10, 1, 23), ["hapas"], hom_nay=HOM_NAY)
    cau = TH.cau_tong_hop(th)
    s = json.dumps(TH.tom_tat(th), ensure_ascii=False)
    assert "<" not in cau and ">" not in cau and "<" not in s and "‹b›Kênh‹/b› X" in cau


def test_kenh_ten_chu_khong_latin_khong_bi_don_chung():
    bai = [(_b("youtube", "ช่องหนึ่ง", 1), None), (_b("youtube", "채널둘", 2), None),
           (_b("youtube", "🌸🌸", 3), None), (_b("youtube", "ช่องหนึ่ง", 4), None)]
    ds = TH.nguon_noi_bat(bai)["theo_nen_tang"]["youtube"]
    assert sorted((g["kenh"], g["bai"]) for g in ds) == [
        ("ช่องหนึ่ง", 2), ("채널둘", 1), ("🌸🌸", 1)]


def test_tu_khoa_mot_bai_nhac_nhieu_lan_chi_tinh_mot():
    bai = [(_b(text="nước hoa nước hoa nước hoa"), None), (_b(text="nước hoa"), None)]
    assert TH.tu_khoa(bai, ["hapas"])["dong"][0]["so_bai"] == 2


# ───────────────────────── câu tổng hợp + bảng ─────────────────────────
HOM_NAY = datetime.date(2026, 12, 31)      # cố định "hôm nay" cho các khoảng ngày cũ


def test_cau_tong_hop_so_vn_va_so_sanh_khi_khong_phai_mau():
    th = TH.tong_hop(_bai_xu_huong(), _d(2026, 9, 20, 0), _d(2026, 10, 3, 23, 59),
                     ["hapas"], hom_nay=HOM_NAY)
    assert th["thao_luan"] == {"bai": 6, "binh_luan": 36, "tong": 42} and th["mau"] == []
    cau = TH.cau_tong_hop(th)
    assert cau.startswith("Thảo luận 42 = 6 bài + 36 bình luận nền tảng hiển thị")
    assert "không phải toàn bộ mạng xã hội" in cau and "tính vào ngày đăng bài" in cau
    assert "Ngày nhiều thảo luận nhất: 03/10 (23 thảo luận, 2 bài)" in cau
    assert "(+400,0%)" in cau and "so với 7 ngày liền trước" in cau
    assert "MẪU" not in cau
    assert "Chủ đề: chưa có bài nào được gán chủ đề (0/5)" in cau


def test_mau_thi_khong_so_sanh_va_canh_bao():
    """Rà 13/10/2026: nguồn chạm trần (YouTube 50 video mới nhất…) thì phần đầu khoảng
    trống — '7 ngày cuối +525%' là ảo. Có mẫu: không so, nói rõ là MẪU."""
    th = TH.tong_hop(_bai_xu_huong(), _d(2026, 9, 20, 0), _d(2026, 10, 3, 23, 59),
                     ["hapas"], mau=["YouTube chạm trần 50 bài", "", None], hom_nay=HOM_NAY)
    assert th["mau"] == ["YouTube chạm trần 50 bài"]
    assert th["xu_huong"]["so_sanh"] is None
    cau = TH.cau_tong_hop(th)
    assert "LƯU Ý — đây là MẪU, không phải toàn bộ: YouTube chạm trần 50 bài" in cau
    assert "Không so 7 ngày cuối với 7 ngày trước: có nguồn chạm trần" in cau
    assert "so với 7 ngày liền trước" not in cau, "không đưa ra % so sánh ảo"
    assert TH.tom_tat(th)["la_mau"] == ["YouTube chạm trần 50 bài"]
    assert TH.tom_tat(th)["xu_huong"]["khong_so_sanh_vi"].startswith("có nguồn chạm trần")
    so = [s.nhan for s in TH.so_lieu(th)]
    assert "Đây là MẪU" in so and not any("7 ngày" in s for s in so)


def test_khoang_ngay_qua_hom_nay_bi_kep_va_hom_nay_khong_vao_so_sanh():
    """'Tháng 10' hỏi ngày 13: không có 18 ngày 0 giả; hôm nay chưa trọn ngày nên 7 ngày
    cuối là 06–12/10 chứ không phải 07–13/10."""
    bai = [(_b(comments=9), _d(2026, 10, d)) for d in range(1, 14)]
    th = TH.tong_hop(bai, _d(2026, 10, 1, 0), _d(2026, 10, 31, 23), ["hapas"],
                     hom_nay=datetime.date(2026, 10, 13))
    xh = th["xu_huong"]
    assert len(xh["dong"]) == 13 and xh["cat_tuong_lai"] is True
    assert xh["so_sanh"] is None and "14 ngày trọn" in xh["ly_do_khong_so_sanh"]
    assert "Khoảng ngày kéo quá hôm nay — chỉ tính tới 13/10." in TH.cau_tong_hop(th)
    bai = [(_b(comments=9), _d(2026, 9, 28) + datetime.timedelta(days=i)) for i in range(16)]
    xh = TH.xu_huong(bai, _d(2026, 9, 28, 0), _d(2026, 10, 13, 23),
                     hom_nay=datetime.date(2026, 10, 13))
    ss = xh["so_sanh"]
    assert (ss["ky_nay"]["tu"], ss["ky_nay"]["den"]) == (datetime.date(2026, 10, 6),
                                                         datetime.date(2026, 10, 12))
    assert ss["doi_thao_luan"] == 0.0, "đều 10 thảo luận/ngày -> 0%, không bị hôm nay kéo lệch"


def test_tuan_va_khac_nam_ghi_ro():
    bai = [(_b(comments=1), _d(2025, 12, 30)), (_b(), _d(2026, 3, 3))]
    th = TH.tong_hop(bai, _d(2025, 11, 1, 0), _d(2026, 3, 31, 23), ["x"], hom_nay=HOM_NAY)
    cau = TH.cau_tong_hop(th)
    assert "Tuần nhiều thảo luận nhất: tuần từ 29/12/2025" in cau
    assert "Tuần nhiều thảo luận nhất (từ ngày)" in [s.nhan for s in TH.so_lieu(th)]


def test_cau_tong_hop_hang_nghin_dung_dau_cham():
    th = TH.tong_hop([(_b(comments=12345), _d(2026, 10, 1))], _d(2026, 10, 1, 0),
                     _d(2026, 10, 1, 23), ["hapas"])
    assert TH.cau_tong_hop(th).startswith("Thảo luận 12.346 = 1 bài + 12.345 bình luận")


def test_cac_bang_cung_so_cot_va_nguong_5_bai():
    bai = _bai_xu_huong()
    th = TH.tong_hop(bai, _d(2026, 9, 20, 0), _d(2026, 10, 3, 23), ["hapas"])
    ds = TH.cac_bang(th)
    assert [b.ten for b in ds] == [TH.TAB_XU_HUONG, TH.TAB_NGUON], \
        "không có chủ đề đã gán và không có cụm ≥2 bài thì không có tab Chủ đề / Từ khoá"
    for b in ds:
        assert {len(r) for r in b.dong + b.dong_tong} == {len(b.cot)}
    xh = ds[0]
    # bài, bình luận, thảo luận, bài brand, TC (bài brand TC không tính), TI, TL, chưa
    assert xh.dong_tong == [["TỔNG", 6, 36, 42, 1, 1, 1, 2, 1]]
    it = TH.tong_hop(bai[:4], _d(2026, 9, 20, 0), _d(2026, 10, 3, 23), ["hapas"])
    assert TH.cac_bang(it) == [], "dưới 5 bài: không dựng tab tổng hợp"
    assert TH.cau_tong_hop(it).startswith("Thảo luận"), "câu tổng hợp vẫn có"


def test_tom_tat_json_duoc():
    th = TH.tong_hop(_bai_xu_huong(), _d(2026, 9, 20, 0), _d(2026, 10, 3, 23), ["hapas"])
    s = json.dumps(TH.tom_tat(th), ensure_ascii=False)
    assert '"moc": "2026-10-03"' in s and '"doi_thao_luan_pt": 400.0' in s


# ───────────────────────── chủ đề trong JSON phán xử ─────────────────────────
def test_doc_phan_xu_lay_chu_de_moi_thu_tu_khong_nham_ma_nuoc():
    ra = A._doc_phan_xu(json.dumps({
        "0": ["k", "brand", "tich_cuc", "mau_ma"],
        "1": ["l", "trung_ten", "trung_lap", "khac", "ban nhạc metal"],
        "2": ["k", "other_market", "trung_lap", "chien_dich", "TH"],
        "3": ["k", "ugc", "gia_ca", "tieu_cuc"],                 # đảo thứ tự
        "4": ["k", "brand", "tich_cuc", "thoi_tiet"],            # mã lạ -> ghi chú
        "5": ["k", "brand", "tich_cuc"],                         # dạng trước 13/10
    }, ensure_ascii=False), 6)
    assert ra[0] == (True, "brand", "", TC, CD["mau_ma"])
    assert ra[1] == (False, "trung_ten", "ban nhạc metal", TL, CD["khac"])
    assert ra[2] == (True, "other_market", "TH", TL, CD["chien_dich"])
    assert ra[3][3:] == (TI, CD["gia_ca"])
    assert ra[4] == (True, "brand", "thoi_tiet", TC, None), "mã lạ thành ghi chú, không đoán"
    assert ra[5][4] is None


def test_nhac_phan_xu_co_du_13_ma_chu_de_va_format_duoc():
    p = A._NHAC_PHAN_XU
    assert all(f"  {ma} " in p for ma in CD), "mỗi mã chủ đề có dòng giải thích"
    assert "Phần tử thứ tư BẮT BUỘC" in p and "Phần tử thứ ba BẮT BUỘC" in p
    assert A._NHAC_PHAN_XU.format(queries="q", boi_canh="b", thi_truong="VN")
    assert len(CD) == 13 and len(set(CD.values())) == 13


def test_phan_xu_ai_tra_chu_de_bo_bai_khong_chac(monkeypatch):
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "1")

    def model(nhac, ns):
        so = re.findall(r'<p i="(\d+)">', nhac)
        return json.dumps({so[0]: ["k", "brand", "tich_cuc", "gia_ca"],
                           so[1]: ["k", "khong_ro", "tich_cuc", "gia_ca"]})
    monkeypatch.setattr(A, "_hoi_model", model)
    rows = [({"platform": "threads", "kenh": f"k{i}", "text": f"hapas {i}", "views": 10 - i,
              "_khop": True}, None) for i in range(2)]
    ket, tt = A._phan_xu_ai(rows, ["hapas"], "HAPAS: túi", "VN", time.monotonic() + 30)
    assert tt["_chu_de"] == {0: CD["gia_ca"]}, "bài AI không chắc không có chủ đề"
    assert all(len(v) == 3 for v in ket.values())


# ───────────────────────── quét NỀN: cache phán có chủ đề ─────────────────────────
def test_phan_xu_tang_luu_va_doc_lai_chu_de_cache_cu_van_doc_duoc(monkeypatch):
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "1")
    monkeypatch.setattr(A, "_hoi_model", lambda nhac, han: json.dumps(
        {str(i): ["k", "brand", "tich_cuc", "chat_luong"]
         for i in range(nhac.count('<p i="'))}))
    rows = _hang(30, khop=False)
    cache: dict = {}
    ket, tt = Q._phan_xu_tang(rows, _TS_AI, time.monotonic() + 600, [], cache=cache, ma="v")
    assert tt["_chu_de"] and set(tt["_chu_de"].values()) == {CD["chat_luong"]}
    assert all(len(v) == 5 and v[4] == CD["chat_luong"] for v in tt["_moi"].values())
    monkeypatch.setattr(A, "_hoi_model", lambda *a: pytest.fail("không được hỏi lại"))
    _, tt2 = Q._phan_xu_tang(rows, _TS_AI, time.monotonic() + 600, [], cache=dict(cache),
                             ma="v")
    assert tt2["_chu_de"] == tt["_chu_de"], "khởi động lại: chủ đề đọc từ cache"
    cu = {k: v[:4] for k, v in cache.items()}          # cache trước 13/10: 4 phần tử
    _, tt3 = Q._phan_xu_tang(rows, _TS_AI, time.monotonic() + 600, [], cache=cu, ma="v")
    assert tt3["_chu_de"] == {} and tt3["_sac_thai"], "cache cũ vẫn đọc được, chỉ thiếu chủ đề"


# ───────────────────────── bình luận YouTube ─────────────────────────
def test_chon_video_youtube_uu_tien_nhac_tu_khoa_roi_nhieu_binh_luan():
    bai = [(_b("youtube", "a", 5, link="https://youtube.com/watch?v=aaaaaa1", _khop=False),
            None),
           (_b("youtube", "b", 2, link="https://youtube.com/watch?v=bbbbbb1", _khop=True), None),
           (_b("youtube", "c", 0, link="https://youtube.com/watch?v=cccccc1", _khop=True), None),
           (_b("tiktok", "d", 99, _khop=True), None)]
    assert [d["kenh"] for d in TH.chon_video_youtube(bai, 5)] == ["b", "a"]


def test_chon_video_youtube_uu_tien_dung_thi_truong():
    """Trùng tên 'Hapas' ở Rajasthan: tin Hindi nhiều bình luận nhất nhưng khác thị trường
    — không được chiếm suất video lấy bình luận (rà 13/10/2026)."""
    bai = [(_b("youtube", "hindi", 5000, link="https://youtube.com/watch?v=hhhhhh1",
               _khop=True, _thi_truong="IN"), None),
           (_b("youtube", "vn", 3, link="https://youtube.com/watch?v=vvvvvv1", _khop=True,
               _thi_truong="VN"), None),
           (_b("youtube", "?", 2, link="https://youtube.com/watch?v=kkkkkk1", _khop=True,
               _thi_truong="không rõ"), None)]
    assert [d["kenh"] for d in TH.chon_video_youtube(bai, 2, "VN")] == ["vn", "?"]
    assert TH.chon_video_youtube(bai, 1)[0]["kenh"] == "hindi", "không truyền nước: như cũ"


def test_bat_mac_dinh_null_khong_tat():
    assert A._bat_mac_dinh(None) and A._bat_mac_dinh("") and A._bat_mac_dinh(True)
    assert A._bat_mac_dinh("true") and A._bat_mac_dinh(1)
    assert not A._bat_mac_dinh(False) and not A._bat_mac_dinh("false")
    assert not A._bat_mac_dinh("không") and not A._bat_mac_dinh(0)


def test_cau_mau_tu_per_platform():
    per = {"tiktok": {"scraped": 100, "limit": 100, "status": "OK"},
           "youtube": {"scraped": 40, "limit": 50, "status": "OK"},
           "threads": {"scraped": 10, "limit": 30, "status": "OK_MOT_PHAN"},
           "facebook": {"status": "HET_LUOT_24H"}}
    assert A._cau_mau(per, ["tiktok", "youtube", "threads", "facebook"]) == [
        "TikTok chạm trần 100 bài", "Threads chỉ lấy được một phần"]


def test_keo_binh_luan_youtube_khong_key_thi_bo_qua(monkeypatch):
    import deep_dive_tool as DD
    monkeypatch.setattr(DD, "_yt_api_san_sang", lambda: False)
    monkeypatch.setattr(DD, "_yt_api_lo", lambda *a: pytest.fail("không được gọi API"))
    kq = TH.keo_binh_luan_youtube([{"link": "https://youtube.com/watch?v=x123456"}], 30,
                                  time.monotonic() + 30)
    assert kq["trang_thai"].startswith("bỏ qua: không có YouTube Data API key")
    assert TH.keo_binh_luan_youtube([], 30, time.monotonic() + 30)["trang_thai"].startswith(
        "bỏ qua: không có video")


def _bl(vid, kenh, text, likes=0, cua_chu=False):
    return {"kenh": kenh, "text": text, "likes": likes, "replies": 0,
            "thoi_gian": "2026-10-10 10:00", "cua_chu": cua_chu,
            "link": f"https://www.youtube.com/watch?v={vid}", "cha": ""}


def test_phan_tich_binh_luan_youtube_gan_nhan_bo_chu_kenh_va_video_bi_loai(monkeypatch):
    monkeypatch.setattr(phan_loai, "_mot_lo", lambda texts: {
        i: ((TC, phan_loai.CHU_DE["SP"]) if "đẹp" in t else (TI, phan_loai.CHU_DE["DV"]))
        for i, t in enumerate(texts)})
    video = [{"platform": "youtube", "link": "https://www.youtube.com/watch?v=vid0001",
              "text": "Review túi HAPAS", "kenh": "Kênh A", "_cua_thuong_hieu": False}]
    kq = {"binh_luan": [_bl("vid0001", "u1", "túi đẹp quá"),
                        _bl("vid0001", "u2", "ship chậm ghê"),
                        _bl("vid0001", "Kênh A", "cảm ơn bạn", cua_chu=True),
                        _bl("vid0001", "hapas.official", "shop cảm ơn ạ"),
                        _bl("vidKHAC1", "u3", "đẹp")]}            # video bị loại -> bỏ
    r = TH.phan_tich_binh_luan_youtube(kq, video, ["hapas"], 60)
    tom = TH.tom_tat(TH.tong_hop([], _d(2026, 10, 1, 0), _d(2026, 10, 1, 23), ["x"]), r)
    yt = tom["binh_luan_youtube"]
    assert (yt["so_binh_luan"], yt["tinh_thong_ke"], yt["khong_tinh_chu_kenh_thuong_hieu"],
            yt["da_phan_loai"]) == (4, 2, 2, 2), "đủ số để không nói '2/4 đã phân loại'"
    assert len(r["dong"]) == 4
    nguon = {x["kenh"]: x["nguon"] for x in r["dong"]}
    assert nguon == {"u1": "khách", "u2": "khách", "Kênh A": "chủ kênh",
                     "hapas.official": phan_loai.NGUON_NHA}
    tk = r["thong_ke"]
    assert tk["tong"] == 2 and tk["sac_thai"][TC]["so"] == 1 and tk["sac_thai"][TI]["so"] == 1
    assert "2 trả lời của chủ kênh/thương hiệu (không tính)" in r["dong_thong_ke"]
    assert "phản hồi của chính thương hiệu" not in r["dong_thong_ke"]
    assert r["dong"][0]["video"] == "Review túi HAPAS"
    b = TH.bang_bl_yt(r)
    assert {len(x) for x in b.dong} == {len(b.cot)} == {len(TH.COT_BL_YT)}


def test_phan_tich_binh_luan_het_gio_thi_chua_phan_loai(monkeypatch):
    monkeypatch.setattr(phan_loai, "_mot_lo", lambda texts: pytest.fail("hết giờ: không gọi"))
    video = [{"link": "https://www.youtube.com/watch?v=vid0001", "text": "v", "kenh": "A"}]
    r = TH.phan_tich_binh_luan_youtube({"binh_luan": [_bl("vid0001", "u1", "túi đẹp quá")]},
                                       video, ["hapas"], 3)
    assert r["dong"][0]["sac_thai"] == CHUA and r["thong_ke"]["da_phan_loai"] == 0


# ───────────────────────── social_listen tại chỗ (đầu-cuối, Lark giả) ─────────────────────
def _gia_co_chu_de(nhac: str) -> str:
    d = json.loads(_phan_xu_gia(nhac))
    for i, t in re.findall(r'<p i="(\d+)">(.*?)</p>', nhac):
        sac = "tich_cuc" if "xinh" in t else "tieu_cuc" if "quảng cáo" in t else "trung_lap"
        cd = "chien_dich" if "quảng cáo" in t else "mau_ma"
        d[i] = d[i][:2] + [sac, cd] + d[i][2:]
    return json.dumps(d, ensure_ascii=False)


def test_social_listen_cot_chu_de_tab_tong_hop_va_cau(quet, monkeypatch):  # noqa: F811
    chay, ghi, hoi, tra = quet
    tra["fn"] = _gia_co_chu_de
    monkeypatch.setattr(TH, "TOI_THIEU_BAI_TAB", 2)    # sheet chính của fixture có 2 bài VN
    kq = chay()
    assert len(hoi) == 1, "chủ đề đi cùng ĐÚNG một lượt phân xử, không gọi thêm model"
    chinh = ghi[0][1]
    assert chinh[0][-1] == A._COT_CHU_DE
    theo = {r[2]: r[-1] for r in chinh[1:]}
    assert theo == {"Linh Đan": CD["chien_dich"], "Ngọc Trâm": CD["mau_ma"]}
    ten = chay.gia.tab_ten()
    for t in (TH.TAB_XU_HUONG, TH.TAB_NGUON, TH.TAB_CHU_DE):
        assert any(x.endswith(t) for x in ten), t
    assert ten.index(next(x for x in ten if x.endswith(TH.TAB_XU_HUONG))) < ten.index(
        next(x for x in ten if x.endswith("Bị loại"))), "tab tổng hợp đứng trước Bị loại"
    th = kq["tong_hop"]
    assert th["thao_luan"]["bai"] == 2 and kq["so_bai_sheet_chinh"] == 2
    assert {g["chu_de"]: g["so"] for g in th["chu_de"]["dong"]} == {
        CD["chien_dich"]: 1, CD["mau_ma"]: 1}
    assert kq["cau_tong_hop"] and kq["cau_tong_hop"] in kq["note"]
    assert set(kq["tong_hop_ghi_o"]) >= {TH.TAB_XU_HUONG, TH.TAB_NGUON, TH.TAB_CHU_DE}
    xh = chay.gia.du_lieu(next(x for x in ten if x.endswith(TH.TAB_XU_HUONG)))
    assert xh[0][:4] == ["Ngày", "Số bài", "Bình luận trên bài", "Thảo luận"]
    assert sum(int(r[1]) for r in xh[1:] if str(r[0]) != "TỔNG" and r[1] != "") == 2


def test_social_listen_it_bai_khong_tab_tong_hop_van_co_cau(quet):  # noqa: F811
    chay, ghi, _, _ = quet
    kq = chay()
    ten = chay.gia.tab_ten()
    assert not any(x.endswith((TH.TAB_XU_HUONG, TH.TAB_NGUON)) for x in ten)
    assert kq["tong_hop_ghi_o"] is None and kq["cau_tong_hop"].startswith("Thảo luận 2 = 2 bài")


_VID = {"text": "Review túi Hapas mới", "kenh": "Kênh Review", "views": 900, "comments": 3,
        "likes": 0, "followers": 0, "shares": 0, "hashtags": "",
        "link": "https://www.youtube.com/watch?v=REVIEW01"}


def test_social_listen_keo_va_gan_nhan_binh_luan_youtube(quet, monkeypatch):  # noqa: F811
    chay, ghi, hoi, tra = quet
    tra["fn"] = lambda nhac: json.dumps(
        {i: ["k", "brand", "trung_lap", "mau_ma"]
         for i in re.findall(r'<p i="(\d+)">', nhac)})
    monkeypatch.setitem(A._FETCH, "youtube", lambda *a: [(dict(_VID), NOW)])
    import deep_dive_tool as DD
    monkeypatch.setattr(DD, "_yt_api_san_sang", lambda: True)
    goi = []

    def api(links, per, han):
        goi.append((links, per))
        return {"binh_luan": [_bl("REVIEW01", "u1", "túi đẹp quá"),
                              _bl("REVIEW01", "u2", "giao chậm")],
                "dv": 1, "loi_bai": {}, "con_lai": [], "loi": "", "mot_phan": [],
                "chua_chay": []}
    monkeypatch.setattr(DD, "_yt_api_lo", api)
    monkeypatch.setattr(phan_loai, "_mot_lo", lambda texts: {
        i: ((TC, phan_loai.CHU_DE["SP"]) if "đẹp" in t else (TI, phan_loai.CHU_DE["DV"]))
        for i, t in enumerate(texts)})
    kq = chay(platforms=["youtube"])
    assert goi == [(["https://www.youtube.com/watch?v=REVIEW01"], TH.YT_MOI_VIDEO_TAI_CHO)]
    yt = kq["tong_hop"]["binh_luan_youtube"]
    assert yt["trang_thai"] == "đã chạy" and yt["so_binh_luan"] == 2 and yt["da_phan_loai"] == 2
    assert yt["sac_thai"] == {TC: 1, TI: 1, TL: 0}
    ten = chay.gia.tab_ten()
    tab = next(x for x in ten if x.endswith(TH.TAB_BL_YT))
    bang = chay.gia.du_lieu(tab)
    assert bang[0] == TH.COT_BL_YT and len(bang) == 3
    assert "Bình luận YouTube: Đã phân loại 2/2 bình luận" in kq["cau_tong_hop"]


def test_social_listen_tat_binh_luan_youtube_thi_khong_goi(quet, monkeypatch):  # noqa: F811
    chay, _, _, _ = quet
    monkeypatch.setitem(A._FETCH, "youtube", lambda *a: [(dict(_VID), NOW)])
    import deep_dive_tool as DD
    monkeypatch.setattr(DD, "_yt_api_san_sang", lambda: True)
    monkeypatch.setattr(DD, "_yt_api_lo", lambda *a: pytest.fail("đã tắt mà vẫn gọi"))
    kq = chay(platforms=["youtube"], binh_luan_youtube=False)
    assert "binh_luan_youtube" not in kq["tong_hop"]


def test_ke_hoach_tran_tab_rieng_giu_11_tab_trong_mot_bang_tinh():
    import trinh_bay_sheet as T
    bang = [T.Bang(f"B{i}", ["a", "b", "c", "d", "e", "f", "g"], [[i] * 7] * 8,
                   gap_duoc=False) for i in range(10)]
    goc = T.Bang("Dữ liệu gốc", ["x"], [[1]] * 3)
    assert len(T.ke_hoach(bang, None, goc).bang_tinh) == 2, "mặc định vẫn 10 tab / bảng tính"
    kh = T.ke_hoach(bang, None, goc, A._TRAN_TAB_SOCIAL)
    assert len(kh.bang_tinh) == 1 and kh.bang_tinh[0][-1].ten == T.TAB_GOC


def test_social_listen_nhieu_tab_nhat_van_mot_link(quet, monkeypatch):  # noqa: F811
    """Lượt sống 13/10/2026 (hapas/YouTube) ra 11 tab dữ liệu và bị đẩy "Dữ liệu gốc" sang
    bảng tính thứ hai. Nay social_listen nới trần tab riêng — mọi tab trong MỘT link."""
    chay, ghi, hoi, tra = quet
    tra["fn"] = _gia_co_chu_de
    monkeypatch.setattr(TH, "TOI_THIEU_BAI_TAB", 2)
    monkeypatch.setattr(TH, "TU_KHOA_TOI_THIEU_BAI", 1)
    # Có bản ghi gốc của nguồn thì sheet có thêm tab "Dữ liệu gốc" (luôn cuối).
    monkeypatch.setitem(A._FETCH, "youtube", lambda *a: [
        (dict(_VID, __goc={"id": "REVIEW01", "title": "Review"}), NOW)])
    import deep_dive_tool as DD
    monkeypatch.setattr(DD, "_yt_api_san_sang", lambda: True)
    monkeypatch.setattr(DD, "_yt_api_lo", lambda links, per, han: {
        "binh_luan": [_bl("REVIEW01", "u1", "túi đẹp quá")], "dv": 1, "loi_bai": {},
        "con_lai": [], "loi": "", "mot_phan": [], "chua_chay": []})
    monkeypatch.setattr(phan_loai, "_mot_lo", lambda texts: {
        i: (TC, phan_loai.CHU_DE["SP"]) for i in range(len(texts))})
    # Trích dẫn đủ dài để không bị gấp vào Tổng quan: nhiều bài tích cực.
    monkeypatch.setattr(A, "_TRICH_DAN_MOI_NHAN", 3)
    kq = chay()
    ten = chay.gia.tab_ten()
    du_lieu = [t for t in ten if t != "Tổng quan"]
    assert kq["bang_tinh_tiep"] is None, "không có bảng tính thứ hai"
    assert du_lieu[-1] == "Dữ liệu gốc" and len(du_lieu) >= 9
    for t in (TH.TAB_XU_HUONG, TH.TAB_NGUON, TH.TAB_CHU_DE, TH.TAB_TU_KHOA, TH.TAB_BL_YT,
              "Thị trường khác", "Bị loại", "Thống kê"):
        assert any(x.endswith(t) for x in du_lieu), t


def test_sat_gio_thi_bo_tab_tong_hop_va_khong_gan_nhan_binh_luan(quet, monkeypatch):  # noqa: F811
    """Đo sống 13/10/2026: thêm tab tổng hợp + gán nhãn bình luận đẩy lượt lên 99–168s (trần
    cứng 180s cho CẢ lượt). Hai phần thêm chỉ làm khi còn dư giờ — giả 'luôn sát giờ'."""
    chay, ghi, hoi, tra = quet
    tra["fn"] = _gia_co_chu_de
    monkeypatch.setattr(TH, "TOI_THIEU_BAI_TAB", 1)
    monkeypatch.setattr(A, "_CHUA_GIAY_TONG_HOP", 10_000.0)
    monkeypatch.setitem(A._FETCH, "youtube", lambda *a: [(dict(_VID), NOW)])
    import deep_dive_tool as DD
    monkeypatch.setattr(DD, "_yt_api_san_sang", lambda: True)
    monkeypatch.setattr(DD, "_yt_api_lo", lambda links, per, han: {
        "binh_luan": [_bl("REVIEW01", "u1", "túi đẹp quá")], "dv": 1, "loi_bai": {},
        "con_lai": [], "loi": "", "mot_phan": [], "chua_chay": []})
    monkeypatch.setattr(phan_loai, "_mot_lo", lambda texts: pytest.fail("sát giờ: không gọi"))
    kq = chay()
    assert kq["success"] is True and kq["tong_hop_bo_tab_vi_gio"] is True
    assert kq["tong_hop_ghi_o"] is None
    ten = chay.gia.tab_ten()
    assert not any(x.endswith((TH.TAB_XU_HUONG, TH.TAB_BL_YT)) for x in ten)
    assert "gần hết giờ nên sheet không có các tab tổng hợp" in kq["cau_tong_hop"]
    assert "chay_nen" not in kq["cau_tong_hop"], "lời dặn model không lọt vào câu ghi sheet"
    assert "đề xuất quét lại với `chay_nen`=true" in kq["note"]
    yt = kq["tong_hop"]["binh_luan_youtube"]
    # Hạn kéo = hạn gán nhãn + 3s: sát giờ thì khỏi gọi API luôn (bình luận chưa nhãn mà
    # tab tổng hợp cũng bị bỏ thì vô ích).
    assert yt["trang_thai"] == "bỏ qua: hết thời gian" and yt["so_binh_luan"] == 0


def _yt_gia(monkeypatch):
    import deep_dive_tool as DD
    monkeypatch.setattr(DD, "_yt_api_san_sang", lambda: True)
    monkeypatch.setattr(DD, "_yt_api_lo", lambda links, per, han: {
        "binh_luan": [_bl("REVIEW01", "u1", "túi đẹp quá")], "dv": 1, "loi_bai": {},
        "con_lai": [], "loi": "", "mot_phan": [], "chua_chay": []})


def test_gan_nhan_binh_luan_chay_song_song_voi_ai_khi_con_cho(quet, monkeypatch):  # noqa: F811
    """AI phân xử 1 lô + gán nhãn 1 lô = 2 lượt model cùng lúc (≤3): gán nhãn KHÔNG chờ AI
    xong. Model AI giả đứng chờ tới khi lô gán nhãn đã chạy — nối tiếp thì sẽ không bao giờ
    thấy tín hiệu."""
    import threading
    chay, _, _, tra = quet
    da_gan = threading.Event()
    thay = []

    def ai(nhac):
        thay.append(da_gan.wait(10))
        return _gia_co_chu_de(nhac)
    tra["fn"] = ai
    monkeypatch.setitem(A._FETCH, "youtube", lambda *a: [(dict(_VID), NOW)])
    _yt_gia(monkeypatch)
    monkeypatch.setattr(phan_loai, "_mot_lo", lambda texts: (
        da_gan.set(), {i: (TC, phan_loai.CHU_DE["SP"]) for i in range(len(texts))})[1])
    kq = chay()
    assert thay == [True], "gán nhãn bình luận chạy trong lúc AI đang phân xử"
    assert kq["tong_hop"]["binh_luan_youtube"]["da_phan_loai"] == 1


def test_ai_nhieu_lo_thi_gan_nhan_sau_ai_khong_qua_3_luot(quet, monkeypatch):  # noqa: F811
    """AI phân xử ≥3 lô (đã chiếm hết 3 chỗ) thì gán nhãn đợi AI xong."""
    import threading
    chay, _, hoi, tra = quet
    monkeypatch.setattr(A, "_AI_LO", 1)            # 1 bài/lô -> 6 bài = 6 lô AI
    khoa = threading.Lock()
    dang = {"ai": 0, "nhan": 0, "dinh": 0}

    def ai(nhac):
        with khoa:
            dang["ai"] += 1
            dang["dinh"] = max(dang["dinh"], dang["ai"] + dang["nhan"])
        time.sleep(0.05)
        with khoa:
            dang["ai"] -= 1
        return _gia_co_chu_de(nhac)
    tra["fn"] = ai

    def nhan(texts):
        with khoa:
            dang["nhan"] += 1
            dang["dinh"] = max(dang["dinh"], dang["ai"] + dang["nhan"])
            assert dang["ai"] == 0, "gán nhãn chạy khi AI còn đang chạy"
        with khoa:
            dang["nhan"] -= 1
        return {i: (TC, phan_loai.CHU_DE["SP"]) for i in range(len(texts))}
    monkeypatch.setitem(A._FETCH, "youtube", lambda *a: [(dict(_VID), NOW)])
    _yt_gia(monkeypatch)
    monkeypatch.setattr(phan_loai, "_mot_lo", nhan)
    kq = chay()
    assert len(hoi) == 6 and dang["dinh"] <= A._AI_SONG_SONG
    assert kq["tong_hop"]["binh_luan_youtube"]["da_phan_loai"] == 1


def test_con_du_gio_thi_khong_co_co_bo_tab(quet, monkeypatch):  # noqa: F811
    chay, _, _, tra = quet
    monkeypatch.setattr(TH, "TOI_THIEU_BAI_TAB", 1)
    kq = chay()
    assert kq.get("tong_hop_bo_tab_vi_gio") is None and kq["tong_hop_ghi_o"]


def test_schema_day_model_chep_cau_tong_hop():
    mo_ta = A.SCHEMA["description"]
    assert "cau_tong_hop" in mo_ta and "tong_hop_ghi_o" in mo_ta
    assert "đừng gọi là toàn bộ thảo luận về brand" in mo_ta
    assert "binh_luan_youtube" in A.SCHEMA["parameters"]["properties"]


# ───────────────────────── quét NỀN: tab + tin nhắn ─────────────────────────
class _SoGia:
    tabs: dict = {}

    def __init__(self, v=None):
        self.s = {"url": "https://sheet", "tabs": {}}

    def dam_bao(self, *a, **k):
        pass

    def bat_dau_giai_doan(self, *a):
        pass

    def ghi_tab(self, ten, bang, tu_dau=False, cot=None, mo_ta=""):
        _SoGia.tabs[ten] = bang
        self.s["tabs"][ten] = {}
        return len(bang)

    def kiem_ghi(self, bo_qua=()):
        return {"day_du": None, "cau": "chưa kiểm (giả)", "tabs": []}

    def ghi_tong_quan(self, ten, tq, kiem=None, bo_qua=()):
        import trinh_bay_sheet as T
        _SoGia.tabs[ten] = T.dung_tong_quan(tq, [], [], kiem)[0]


class _V:
    ma = "Q7"
    d = {"nen_tang": {"tiktok": {}}, "nguoi_yeu_cau": "", "ngan_sach_usd": 1.0}


def _ket_nen(chu_de):
    hits = [({**_b("tiktok", f"k{i}", 10, sac=TC, chu_de=chu_de, text="nước hoa thơm"),
              "_thi_truong": "VN", "_nhan_dinh": "brand", "_phan_xu": "AI"},
             _d(2026, 10, 1 + i)) for i in range(5)]
    ket = {"hits": hits, "bi_loai": [],
           "per": {"tiktok": {"scraped": 5, "trung_lap": 0, "trong_khoang": 5, "giu": 5,
                              "loai": 0}}, "phan_xu": {}}
    ket["tong_hop"] = TH.tong_hop(hits, _d(2026, 10, 1, 0), _d(2026, 10, 7, 23), ["hapas"])
    ket["cau_tong_hop"] = TH.cau_tong_hop(ket["tong_hop"])
    return ket


_TS = {"queries": ["hapas"], "date_from": "2026-10-01", "date_to": "2026-10-07",
       "country": "VN"}


def test_quet_nen_ghi_tab_tong_hop_va_tin_nhan(monkeypatch):
    _SoGia.tabs = {}
    monkeypatch.setattr(sheet_lon, "SoSheet", _SoGia)
    ket = _ket_nen(CD["gia_ca"])
    Q._ghi_cuoi(_V(), _TS, ket, {"usd": 0.1, "so_run": 1}, "xong")
    tabs = _SoGia.tabs
    assert tabs["TikTok"][0][-1] == A._COT_CHU_DE
    assert [r[-1] for r in tabs["TikTok"][1:]] == [CD["gia_ca"]] * 5
    for t in (TH.TAB_XU_HUONG, TH.TAB_NGUON, TH.TAB_CHU_DE, TH.TAB_TU_KHOA):
        assert t in tabs and {len(r) for r in tabs[t]} == {len(tabs[t][0])}, t
    assert len(tabs[TH.TAB_XU_HUONG]) == 1 + 7, "7 ngày, không ghi dòng TỔNG vào tab nền"
    assert ["Tổng hợp", ket["cau_tong_hop"]] in [r[:2] for r in tabs[Q._TAB_TONG]]
    tin = Q._tin_nhan(_V(), _TS, ket, {"usd": 0.1, "so_run": 1}, "https://sheet", "xong", [])
    assert ket["cau_tong_hop"] in tin and "Bình luận YouTube" not in tin


def test_quet_nen_tab_cu_khong_con_du_lieu_thi_ghi_de(monkeypatch):
    """Việc tiếp tục mà lượt sau không còn dữ liệu cho tab Chủ đề: tab cũ ghi lại, không để
    số của lượt trước nằm lại."""
    _SoGia.tabs = {}
    so = _SoGia()
    so.s["tabs"] = {TH.TAB_CHU_DE: {}}
    monkeypatch.setattr(sheet_lon, "SoSheet", lambda v: so)
    Q._ghi_cuoi(_V(), _TS, _ket_nen(None), {"usd": 0.1, "so_run": 1}, "xong")
    assert _SoGia.tabs[TH.TAB_CHU_DE] == [["(không có dòng nào ở lượt này)"]]


def test_quet_nen_khong_tong_hop_van_ghi_de_tab_cu(monkeypatch):
    """Lượt này lỗi tổng hợp (tong_hop None) mà tab Xu hướng còn từ lượt trước: ghi đè."""
    _SoGia.tabs = {}
    so = _SoGia()
    so.s["tabs"] = {TH.TAB_XU_HUONG: {}}
    monkeypatch.setattr(sheet_lon, "SoSheet", lambda v: so)
    ket = _ket_nen(CD["gia_ca"])
    ket.pop("tong_hop")
    ket.pop("cau_tong_hop")
    Q._ghi_cuoi(_V(), _TS, ket, {"usd": 0.1, "so_run": 1}, "xong")
    assert _SoGia.tabs[TH.TAB_XU_HUONG] == [["(không có dòng nào ở lượt này)"]]
    assert TH.TAB_NGUON not in _SoGia.tabs


def test_tin_nhan_nen_chi_neu_tab_co_that():
    ket = _ket_nen(None)                    # không chủ đề -> không có tab Chủ đề
    tin = Q._tin_nhan(_V(), _TS, ket, {"usd": 0, "so_run": 0}, "https://s", "xong", [])
    dong = next(x for x in tin.split("\n") if x.startswith("Tổng hợp"))
    assert "Xu hướng" in dong and "Chủ đề" not in dong.split("):")[0]


def test_mau_nen_tu_so_viec():
    class V:
        d = {"nen_tang": {"tiktok": {"chua_phu": ["x"]},
                          "youtube": {"phan": [{"trang_thai": "mot_phan"}]},
                          "threads": {"phan": [{"trang_thai": "xong"}]},
                          "facebook": {}}}
    ket = {"per": {"threads": {"scraped": 30}, "facebook": {"scraped": 5}}}
    ts = {"limit": {"threads": 30, "facebook": 20}}
    assert Q._mau_nen(V(), ts, ket) == ["TikTok còn đoạn chưa phủ",
                                       "YouTube chỉ lấy được một phần",
                                       "Threads chạm trần 30 bài"]


def test_binh_luan_youtube_nen_kiem_lai_huy_va_han_chot(monkeypatch):
    class V:
        d = {"nen_tang": {"youtube": {}}}

        def __init__(self, huy, con):
            self._huy, self._con = huy, con

        def da_huy(self):
            return self._huy

        def con_giay(self):
            return self._con
    hits = [(_b("youtube", "a", 5, link="https://youtube.com/watch?v=aaaaaa1"), None)]
    monkeypatch.setattr(TH, "keo_binh_luan_youtube", lambda *a: pytest.fail("không được kéo"))
    for v in (V(True, 900), V(False, 30)):
        r = Q._binh_luan_youtube_nen(v, {"queries": ["x"]}, hits, cho_ai=True)
        assert r["trang_thai"] == "bỏ qua: việc đã huỷ hoặc sát hạn chót"
    goi = {}

    def keo(video, per, han):
        goi["keo"] = han - time.monotonic()
        return {"trang_thai": "đã chạy", "binh_luan": []}

    def phan_tich(kq, video, q, han_giay, song_song=None):
        goi["nhan"], goi["ss"] = han_giay, song_song
        return {"dong": [], "thong_ke": None, "dong_thong_ke": ""}
    monkeypatch.setattr(TH, "keo_binh_luan_youtube", keo)
    monkeypatch.setattr(TH, "phan_tich_binh_luan_youtube", phan_tich)
    Q._binh_luan_youtube_nen(V(False, 150), {"queries": ["x"]}, hits, cho_ai=True)
    assert goi["keo"] <= 50 and goi["nhan"] <= 50, "chia phần giờ còn lại"
    assert goi["ss"] == TH.YT_SONG_SONG_NEN == 2


def test_binh_luan_youtube_nen_khong_chay_khi_huy_hoac_tat():
    class V:
        d = {"nen_tang": {"youtube": {}}}
    assert Q._binh_luan_youtube_nen(V(), {"queries": ["x"]}, [], cho_ai=False) is None
    assert Q._binh_luan_youtube_nen(V(), {"queries": ["x"], "binh_luan_youtube": False},
                                    [], cho_ai=True) is None

    class V2:
        d = {"nen_tang": {"tiktok": {}}}
    assert Q._binh_luan_youtube_nen(V2(), {"queries": ["x"]}, [], cho_ai=True) is None
    r = Q._binh_luan_youtube_nen(V(), {"queries": ["x"]}, [], cho_ai=True)
    assert r["trang_thai"].startswith("bỏ qua: không có video")
