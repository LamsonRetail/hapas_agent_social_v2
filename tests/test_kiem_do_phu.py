"""Kiểm độ phủ hai lần mỗi tuần (17/10/2026, `kiem_do_phu` + `theo_doi._kiem_do_phu`).

Chủ dự án: "trước đó làm social quét sao ko quét thấy những bài đó" → "độ phủ cho hẳn 0,1 đô đi";
đổi phạm vi cùng ngày: hai lần/tuần, 0,20 USD/lần, và Mark tự sửa đường thu thập theo lý do sót.
Dữ liệu giả làm sạch (tên tài khoản/chữ không phải thật), không Apify, không Postgres."""
from __future__ import annotations

import contextvars
import datetime
import math
import re
import time
from pathlib import Path

import pytest
from test_theo_doi import DU_AN, GiaKhoTk, GiaViec, mo  # noqa: F401

import apify_tool as A
import kiem_do_phu as KDP
import lang_nghe_db as K
import theo_doi as T
import tiktok_api as TT

_VN = datetime.timezone(datetime.timedelta(hours=7))
#: Hàm thật — fixture `mo` thay bằng hàm rỗng cho các bài thử lượt /theodoi khác.
_KIEM_THAT = T._kiem_do_phu
BAY = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=_VN)


# ───────────────────────────── cấu hình, nhịp, chọn mẫu ─────────────────────────────
@pytest.mark.parametrize("ch, ky_vong", [
    ({}, {"bat": True, "tran_usd": 0.20}),
    ({"do_phu": {"bat": False}}, {"bat": False, "tran_usd": 0.20}),
    ({"do_phu": {"tran_usd": 0}}, {"bat": False, "tran_usd": 0.0}),
    ({"do_phu": {"tran_usd": "rác"}}, {"bat": True, "tran_usd": 0.20}),
    ({"do_phu": {"tran_usd": -1}}, {"bat": True, "tran_usd": 0.20}),
    ({"do_phu": {"tran_usd": 0.25}}, {"bat": True, "tran_usd": 0.25}),
    ({"do_phu": {"tran_usd": 9}}, {"bat": True, "tran_usd": KDP.TRAN_TOI_DA}),
    ({"do_phu": "hỏng"}, {"bat": True, "tran_usd": 0.20})])
def test_cau_hinh_mac_dinh_bat_020_co_cong_tac(ch, ky_vong):
    assert KDP.cau_hinh({"cau_hinh": ch}) == ky_vong


def test_den_han_hai_lan_moi_tuan():
    assert KDP.den_han(None, BAY)[0] is True
    assert KDP.den_han({"luc": "hỏng"}, BAY)[0] is True
    co, ly = KDP.den_han({"luc": "2026-10-14T09:00:00+07:00"}, BAY)        # 72 giờ < 84
    assert not co and "14/10" in ly
    assert KDP.den_han({"luc": "2026-10-13T20:59:00+07:00"}, BAY)[0] is True   # 84 giờ 1 phút


def test_chon_tag_tu_khoa_roi_tag_chien_dich_bo_tag_chung():
    """Video seeding chỉ có hashtag (#HAPAS #LAMMOIDIEUVIYEU #QUATANG2010): tag chiến dịch đi cùng
    bài đã giữ được chọn; #fyp / #xuhuong không phải tag brand."""
    bai = ["fyp, HAPAS, LAMMOIDIEUVIYEU, QUATANG2010", "LAMMOIDIEUVIYEU, xuhuong, fyp",
           "hapasxthom, LAMMOIDIEUVIYEU", "hapasxthom, fyp, QUATANG2010", "mot_lan_thoi, fyp"]
    assert KDP.chon_tag(["túi hapas", "hapas", "Hapas"], bai) == [
        "hapas", "tuihapas", "hapasxthom", "lammoidieuviyeu"]
    assert KDP.chon_tag(["hapas"], []) == ["hapas"]
    assert len(KDP.chon_tag(["hapas", "a b c d"], bai * 3)) <= KDP.TAG_TOI_DA


def test_chon_tac_gia_bo_nguon_dang_theo_doi_va_trung():
    noi = [{"tai_khoan": "hapas.official"}, {"tai_khoan": "KOL.A"}, {"tai_khoan": ""},
           {"tai_khoan": "kol.b"}]
    dx = [{"dinh_danh": "@kol.a"}, {"dinh_danh": "kol.c"}]
    assert KDP.chon_tac_gia(noi, dx, {"hapas.official"}) == ["kol.a", "kol.b", "kol.c"]
    assert KDP.chon_tac_gia(noi, dx, set(), toi_da=2) == ["hapas.official", "kol.a"]


@pytest.mark.parametrize("cid, uid", [({}, {}), ({"t1": "1", "t2": "2", "t3": "3", "t4": "4"},
                                                {f"u{i}": str(i) for i in range(6)})])
def test_chia_yeu_cau_khong_vuot_tran_va_2_3_cho_hashtag(cid, uid):
    tag, tg = ["t1", "t2", "t3", "t4"], [f"u{i}" for i in range(6)]
    n = int(KDP.TRAN_MAC_DINH / TT.GIA_YEU_CAU + 1e-9)
    assert n == 66
    ttag, ttg = KDP.chia_yeu_cau(n, tag, tg, cid, uid)
    dung = (sum(ttag.values()) + sum(0 if cid.get(t) else 1 for t in ttag)
            + sum(ttg.values()) + sum(0 if uid.get(u) else 1 for u in ttg))
    assert dung <= n
    assert set(ttag) == set(tag) and all(1 <= x <= KDP.TAG_TRANG_TOI_DA for x in ttag.values())
    so_tag = sum(ttag.values()) + sum(0 if cid.get(t) else 1 for t in ttag)
    assert so_tag <= math.ceil(n * KDP.PHAN_TAG)
    assert ttg and all(1 <= x <= KDP.TAC_GIA_TRANG for x in ttg.values())
    # Không có hashtag: mọi yêu cầu cho nhà sáng tạo; không có ai: mọi yêu cầu cho hashtag.
    assert KDP.chia_yeu_cau(10, [], tg, {}, {})[0] == {}
    assert KDP.chia_yeu_cau(10, ["t1"], [], {}, {}) == ({"t1": KDP.TAG_TRANG_TOI_DA}, {})


def test_do_phu_dem_va_theo_thao_luan():
    def x(nhac, co, tl, loai=False):
        return {"nhac": nhac, "da_co": co, "da_loai": loai, "tl": tl}
    so = KDP.tinh_do_phu([x(True, True, 1), x(True, True, 9), x(True, False, 90),
                          x(True, False, 1, loai=True), x(False, False, 500)])
    assert (so["so_mau"], so["so_nhac"], so["so_da_co"], so["so_sot"], so["so_da_loai"]) == \
        (5, 3, 2, 1, 1)
    assert so["do_phu"] == pytest.approx(66.67) and so["do_phu_tl"] == pytest.approx(10.0)
    assert KDP.tinh_do_phu([])["do_phu"] is None and KDP.tinh_do_phu([])["do_phu_tl"] is None


def test_ly_do_sot():
    d = {"text": "Cố lên #HAPAS #LAMMOIDIEUVIYEU", "username": "kol.moi", "kenh": "KOL", "likes": 5}
    ly = KDP.ly_do_sot(d, BAY - datetime.timedelta(days=15), ["hapas"], set(), BAY)
    assert ly[0].startswith("chỉ nhắc brand qua hashtag") and "15 ngày" in ly[1] and len(ly) == 2
    d2 = {"text": "túi hapas đẹp", "username": "kol.cu", "likes": 9000}
    assert KDP.ly_do_sot(d2, BAY, ["hapas"], {"kol.cu"}, BAY) == [
        "tìm theo từ khoá không trả về bài này"]


# ───────────────────────────── tiktok_api: hashtag + tài khoản ─────────────────────────────
class GiaApi:
    """Giả `apify_tool._call` cho scraptik: mỗi lời gọi một run (ghi `_SO_RUN`, báo
    `_KHI_CO_RUN` như thật), trả theo `tra(payload)`."""

    def __init__(self, mp, tra):
        self.goi: list[dict] = []
        self.tra = tra
        mp.setattr(A, "_call", self.call)

    def call(self, actor, payload, limit, mem=None, *, tran_usd=None, **kw):
        assert actor == TT.ACTOR and tran_usd == TT._TRAN_LUOT, "mỗi run mang maxTotalChargeUsd"
        rid = f"dp{len(self.goi)}"
        self.goi.append(dict(payload))
        so = A._SO_RUN.get()
        if so is not None:
            so.append({"run_id": rid})
        fn = A._KHI_CO_RUN.get()
        if fn:
            fn({"id": rid}, {"actor": TT.ACTOR})
        x = self.tra(payload)
        if isinstance(x, Exception):
            raise x
        return [x]


def _aw(vid, user, desc, ngay, bl=3, thich=50, tags=()):
    return {"aweme_id": str(vid), "desc": desc, "create_time": int(ngay.timestamp()),
            "author": {"uid": f"u-{user}", "unique_id": user, "nickname": user.upper()},
            "statistics": {"comment_count": bl, "digg_count": thich, "play_count": 1000},
            "text_extra": [{"hashtag_name": t} for t in tags]}


def test_tim_cid_trung_ten_nhieu_nguoi_nhat_va_lat_trang_hashtag(monkeypatch):
    def tra(p):
        if "searchHashtags_keyword" in p:
            return {"status_code": 0, "challenge_list": [
                {"challenge_info": {"cid": "9", "cha_name": "hapas🥰", "user_count": 3}},
                {"challenge_info": {"cid": "1", "cha_name": "HAPAS", "user_count": 900}},
                {"challenge_info": {"cid": "7", "cha_name": "hapasofficial", "user_count": 5000}}]}
        cur = p["challengePosts_cursor"]
        return {"status_code": 0, "cursor": cur + 20, "has_more": 1 if cur < 20 else 0,
                "aweme_list": [_aw(100 + cur + i, "kol", "#hapas", BAY) for i in range(2)]}
    api = GiaApi(monkeypatch, tra)
    ngan = TT.Ngan(0.1)
    assert TT.tim_cid("#Hapas", ngan) == "1"
    items = TT.bai_hashtag("1", 5, ngan)
    assert [x["id"] for x in items] == ["100", "101", "120", "121"]
    assert [p.get("challengePosts_cursor") for p in api.goi[1:]] == [0, 20]
    assert api.goi[1]["challengePosts_count"] == TT.TAG_MOI_TRANG and ngan.da == 3


def test_bai_tai_khoan_nho_uid_va_dung_khi_gap_bai_cu(monkeypatch):
    cu = BAY - datetime.timedelta(days=40)

    def tra(p):
        if "profile_username" in p:
            return {"status_code": 0, "user": {"uid": "u9", "unique_id": "kol"}}
        if p["userPosts_maxCursor"] == "0":
            return {"status_code": 0, "has_more": 1, "max_cursor": "c1",
                    "aweme_list": [_aw(1, "kol", "a", BAY), dict(_aw(2, "kol", "ghim", cu),
                                                                is_top=1)]}
        return {"status_code": 0, "has_more": 1, "max_cursor": "c2",
                "aweme_list": [_aw(3, "kol", "b", cu)]}
    api = GiaApi(monkeypatch, tra)
    items, uid = TT.bai_tai_khoan("@kol", 5, TT.Ngan(1), d_from=BAY - datetime.timedelta(days=30))
    assert uid == "u9" and [x["id"] for x in items] == ["1", "3"]     # bỏ ghim, dừng ở bài cũ
    assert len(api.goi) == 3
    api.goi.clear()
    items, _ = TT.bai_tai_khoan("kol", 1, TT.Ngan(1), uid="u9")
    assert [list(p)[0] for p in api.goi] == ["userPosts_userId"], "uid đã nhớ: bỏ yêu cầu hồ sơ"


def test_trang_sau_loi_giu_trang_truoc_trang_dau_loi_thi_nem(monkeypatch):
    def tra(p):
        if p["challengePosts_cursor"]:
            return A.LoiApify("HET_TIEN_THANG", "hết tiền")
        return {"status_code": 0, "cursor": 20, "has_more": 1,
                "aweme_list": [_aw(5, "kol", "#hapas", BAY)]}
    GiaApi(monkeypatch, tra)
    assert [x["id"] for x in TT.bai_hashtag("1", 3, TT.Ngan(1))] == ["5"]
    GiaApi(monkeypatch, lambda p: A.LoiApify("LOI", "hỏng"))
    with pytest.raises(A.LoiApify):
        TT.bai_hashtag("1", 3, TT.Ngan(1))


def test_lay_mau_loi_mot_tag_khong_mat_phan_khac_het_tien_thi_khoa(monkeypatch):
    def tra(p):
        if p.get("challengePosts_cid") == "2":
            return A.LoiApify("LOI", "tag hỏng")
        if p.get("userPosts_userId") == "u-b":
            return A.LoiApify("HET_TIEN_THANG", "hết tiền tháng")
        if "challengePosts_cid" in p:
            return {"status_code": 0, "has_more": 0, "aweme_list": [_aw(7, "kol", "#hapas", BAY)]}
        return {"status_code": 0, "has_more": 0, "aweme_list": [_aw(8, "kol.a", "hapas", BAY)]}
    api = GiaApi(monkeypatch, tra)
    ngan = TT.Ngan(0.1)
    ra, tk = contextvars.copy_context().run(
        KDP.lay_mau, {"t1": 1, "t2": 1}, {"kol.a": 1, "kol.b": 1}, {"t1": "1", "t2": "2"},
        {"kol.a": "u-a", "kol.b": "u-b"}, ngan, BAY - datetime.timedelta(days=30))
    assert "#t1" in {d for _, d in ra}, "tag lỗi không làm mất bài đã trả tiền của tag khác"
    assert "tag hỏng" in tk["tag"]["t2"]["loi"] and tk["dung"] == "HET_TIEN_THANG"
    assert ngan.toi_da == 0 and len(api.goi) <= 4


def test_tran_yeu_cau_chan_tong_so_run(monkeypatch):
    """0,20 USD ⇒ ≤ 66 yêu cầu dù kế hoạch xin nhiều hơn (trần cứng ở bộ đếm)."""
    api = GiaApi(monkeypatch, lambda p: {"status_code": 0, "has_more": 1, "cursor": 999999,
                                         "max_cursor": "x", "aweme_list": [
                                             _aw(time.time_ns(), "kol", "#hapas", BAY)]})
    ngan = TT.Ngan(0.20)
    contextvars.copy_context().run(
        KDP.lay_mau, {f"t{i}": 50 for i in range(4)}, {f"u{i}": 50 for i in range(6)},
        {f"t{i}": str(i) for i in range(4)}, {f"u{i}": str(i) for i in range(6)}, ngan,
        BAY - datetime.timedelta(days=3650))
    assert len(api.goi) == ngan.da == 66


# ───────────────────────────── trong lượt /theodoi ─────────────────────────────
class KhoDp(GiaKhoTk):
    def __init__(self, mp):
        super().__init__(mp)
        self.dong: list[dict] = []
        mp.setattr(K, "hashtag_gan_day", lambda ma, p, tu, toi_da=3000: [
            "HAPAS, LAMMOIDIEUVIYEU", "LAMMOIDIEUVIYEU, fyp"])
        mp.setattr(K, "tac_gia_noi_bat", lambda ma, p, tu, toi_da=20: [
            {"tai_khoan": "hapas.official", "thao_luan": 900, "so_bai": 9},
            {"tai_khoan": "kol.cu", "thao_luan": 300, "so_bai": 2}])
        mp.setattr(K, "de_xuat_dang_xet", lambda ma, p: [{"dinh_danh": "kol.dx", "thao_luan": 60}])
        mp.setattr(K, "nguon_dang_theo_doi", lambda ma: [
            {"id": 7, "nen_tang": "tiktok", "dinh_danh": "@hapas.official"}])
        mp.setattr(K, "ghi_kiem_do_phu", lambda r: (self.dong.append(r), 1)[1])


def _tra_mau(ngay_seed):
    """#hapas: bài seeding chỉ-hashtag (sót, 768 bình luận), bài đã có, bài 'hapas guitar' (từ
    loại trừ), bài 45 ngày (ngoài mẫu). Nhà sáng tạo: một bài brand đã có + một bài không nhắc."""
    def tra(p):
        if "searchHashtags_keyword" in p:
            k = p["searchHashtags_keyword"]
            return {"status_code": 0, "challenge_list": [
                {"challenge_info": {"cid": f"c-{k}", "cha_name": k, "user_count": 10}}]}
        if p.get("challengePosts_cid") == "c-hapas":
            return {"status_code": 0, "has_more": 0, "aweme_list": [
                _aw(70000001, "kol.moi", "Cố lên #HAPAS #LAMMOIDIEUVIYEU", ngay_seed, bl=768,
                    thich=40, tags=("HAPAS", "LAMMOIDIEUVIYEU")),
                _aw(70000002, "kol.cu", "túi hapas mới", BAY - datetime.timedelta(days=2), bl=9),
                _aw(70000003, "ban.nhac", "hapas guitar cover", BAY, bl=5),
                _aw(70000004, "kol.xa", "hapas xưa", BAY - datetime.timedelta(days=45))]}
        if "challengePosts_cid" in p:
            return {"status_code": 0, "has_more": 0, "aweme_list": [
                _aw(70000001, "kol.moi", "Cố lên #HAPAS", ngay_seed, bl=768, thich=40)]}
        if "profile_username" in p:
            return {"status_code": 0, "user": {"uid": f"u-{p['profile_username']}"}}
        return {"status_code": 0, "has_more": 0, "aweme_list": [
            _aw(70000002, "kol.cu", "túi hapas mới", BAY - datetime.timedelta(days=2), bl=9),
            _aw(70000005, "kol.cu", "ăn sáng", BAY - datetime.timedelta(days=1))]}
    return tra


def _chay_dp(v, du_an=None, con=5.0):
    return contextvars.copy_context().run(T._kiem_do_phu, v, du_an or dict(DU_AN), 12, con,
                                          time.monotonic() + 900)


def test_kiem_do_phu_do_sot_lap_lo_ghi_bang_va_tien(mo):  # noqa: F811
    mo.setattr(T, "_kiem_do_phu", _KIEM_THAT)
    mo.setattr(TT, "dung_api", lambda viec: True)
    kho = KhoDp(mo)
    kho.da_co = {"tiktok:70000002"}
    mo.setattr(K, "khoa_da_co", lambda ma, khoa: {k for k in khoa if k in kho.da_co | {
        r["khoa"] for _, rows in kho.bai for r in rows}})
    api = GiaApi(mo, _tra_mau(datetime.datetime.now(_VN) - datetime.timedelta(days=15)))
    v = GiaViec({}, [])
    kq = _chay_dp(v)
    so = kq["so"]
    # Mẫu: seeding (sót), bài đã có; 'hapas guitar' bị từ loại trừ (không nhắc brand), bài 45 ngày
    # ngoài mẫu, bài 'ăn sáng' không nhắc brand.
    assert (so["so_nhac"], so["so_da_co"], so["so_sot"]) == (2, 1, 1)
    assert so["do_phu"] == 50.0 and so["do_phu_tl"] == pytest.approx(100 * 10 / (10 + 769), 0.01)
    (dong,) = kho.dong
    assert dong["du_an"] == "hapas" and dong["luot_id"] == 12 and dong["nen_tang"] == "tiktok"
    (sot,) = dong["bai_sot"]
    assert sot["khoa"] == "tiktok:70000001" and sot["thao_luan"] == 769
    assert sot["tai_khoan"] == "kol.moi" and sot["link"].endswith("/video/70000001")
    assert sot["ly_do"][0].startswith("chỉ nhắc brand qua hashtag")
    assert sorted(sot["duong"]) == ["#hapas", "#lammoidieuviyeu"]
    # Lấp lỗ: bài sót đi qua phễu (AI không phán → giữ theo từ khoá) → ghi kho, đánh dấu bổ sung.
    assert kq["bo_sung"] == 1 and sot["bo_sung"] is True
    assert [r["khoa"] for _, rows in kho.bai for r in rows] == ["tiktok:70000001"]
    assert any(r["khoa"] == "tiktok:70000002" for r in kho.cap_nhat), "bài đã có: cập nhật số"
    # Tiền: mỗi yêu cầu một run, id vào sổ việc nhóm do_phu; tag + nhà sáng tạo (bỏ nguồn đang theo
    # dõi hapas.official).
    ids = [ph["run_id"] for ph in v.d["nen_tang"]["do_phu"]["phan"] if ph.get("run_id")]
    assert len(ids) == len(api.goi) == kq["so_yeu_cau"] <= 66
    assert kq["usd"] == pytest.approx(len(api.goi) * TT.GIA_YEU_CAU) == dong["chi_phi_usd"]
    assert {t["ten"] for t in dong["mau"]["tag"]} == {"#hapas", "#lammoidieuviyeu"}
    assert {t["ten"] for t in dong["mau"]["tac_gia"]} == {"@kol.cu", "@kol.dx"}
    assert not any(p.get("profile_username") == "hapas.official" for p in api.goi)
    moc = T.doc_moc_tk("hapas")[KDP.KHOA_MOC]
    assert moc["cid"] == {"hapas": "c-hapas", "lammoidieuviyeu": "c-lammoidieuviyeu"}
    assert moc["uid"] == {"kol.cu": "u-kol.cu", "kol.dx": "u-kol.dx"} and moc["usd"] == kq["usd"]
    cau = KDP.cau_ghi_chu(kq)[0]
    assert cau.startswith("kiểm độ phủ (TikTok: 2 hashtag + 2 nhà sáng tạo")
    assert "1/2 bài nhắc brand đã có (50%)" in cau and "bổ sung 1" in cau
    # Tự sửa đường thu thập (đổi phạm vi 17/10): KOL chưa theo dõi → đề xuất ưu tiên (769 thảo luận
    # ≥ 500); tag chiến dịch của bài sót → lượt nổi; sót do tụt hạng → lượt nổi thêm 1 trang.
    hd = dong["hanh_dong"]
    assert hd["de_xuat"] == [{"dinh_danh": "kol.moi", "so_bai": 1, "thao_luan": 769,
                              "uu_tien": True}]
    assert kho.dx[-1][0]["dinh_danh"] == "kol.moi" and kho.dx[-1][0]["ly_do"].startswith(
        "ƯU TIÊN theo dõi — kiểm độ phủ")
    assert hd["tag_them"] == ["lammoidieuviyeu"] and hd["noi"]["trang"] == [2, 3]
    noi = T.doc_moc_tk("hapas")[KDP.KHOA_NOI_CFG]
    assert (noi["trang"], noi["gio"], noi["tag"]) == (3, 20, ["lammoidieuviyeu"])
    assert sot["hanh_dong"] == ["đã ghi vào kho", "đề xuất theo dõi @kol.moi (ưu tiên)",
                                "tìm #lammoidieuviyeu trong lượt nổi",
                                "nới lượt nổi lên 3 trang/từ khoá"]
    assert "Mark đã làm: đề xuất theo dõi 1 nhà sáng tạo (1 ưu tiên); thêm #lammoidieuviyeu" in cau
    # Khởi động lại trong CÙNG việc: không gọi lại, trả kết quả đã có.
    n = len(api.goi)
    assert _chay_dp(v)["so"] == so and len(api.goi) == n
    # Việc mới trong 3,5 ngày: không kiểm; mốc dùng lại cid/uid lần sau.
    assert _chay_dp(GiaViec({}, [])) == {} and len(api.goi) == n


def test_kiem_do_phu_tat_het_tien_khoi_dong_lai(mo):  # noqa: F811
    mo.setattr(T, "_kiem_do_phu", _KIEM_THAT)
    mo.setattr(TT, "dung_api", lambda viec: True)
    KhoDp(mo)
    api = GiaApi(mo, _tra_mau(BAY))
    assert _chay_dp(GiaViec({}, []), dict(DU_AN, cau_hinh={"do_phu": {"bat": False}})) == {}
    kq = _chay_dp(GiaViec({}, []), con=0.01)
    assert "ngân sách còn 0,01 USD" in kq["bo_qua"] and not api.goi
    assert KDP.cau_ghi_chu(kq) == [f"kiểm độ phủ: bỏ qua ({kq['bo_qua']})"]
    v = GiaViec({}, [], con=200)
    assert "hết giờ" in _chay_dp(v)["bo_qua"] and not api.goi
    v = GiaViec({"do_phu": {"phan": [{"id": "dp-r1", "run_id": "r1", "nen_tang": "do_phu"}]}}, [])
    kq = _chay_dp(v)
    assert "khởi động lại" in kq["ghi_chu"][0] and not api.goi
    assert v.d["nen_tang"]["do_phu"]["phan"][-1]["ma"] == "KHONG_KIEM_DUOC"
    # Trần riêng 0,03 USD ⇒ ≤ 10 yêu cầu.
    kq = _chay_dp(GiaViec({}, []), dict(DU_AN, cau_hinh={"do_phu": {"tran_usd": 0.03}}))
    assert 0 < len(api.goi) <= 10 and kq["usd"] <= 0.03 + 1e-9


def test_kiem_do_phu_khong_tieu_dong_nao_thi_tra_moc_cu(mo):  # noqa: F811
    mo.setattr(T, "_kiem_do_phu", _KIEM_THAT)
    mo.setattr(TT, "dung_api", lambda viec: True)
    KhoDp(mo)
    mo.setattr(KDP, "lay_mau", lambda *a, **k: ([], {"tag": {}, "tac_gia": {}}))
    kq = _chay_dp(GiaViec({}, []))
    assert kq["so_yeu_cau"] == 0 and KDP.KHOA_MOC in T.doc_moc_tk("hapas")
    assert KDP.den_han(T.doc_moc_tk("hapas")[KDP.KHOA_MOC], datetime.datetime.now(_VN))[0]


def test_chay_viec_cau_do_phu_dung_truoc_phieu_va_tien_khong_vao_nen_tang(mo):  # noqa: F811
    """Câu độ phủ nằm TRƯỚC các dòng phễu (ghi_chu cắt 2.000 ký tự); bài bổ sung cộng vào bài
    mới của lượt; nhóm do_phu không vào danh sách nền tảng của sổ chi phí."""
    from test_theo_doi import GiaKho
    kho = GiaKho().cai(mo)
    mo.setattr(T, "_tim_tu_khoa", lambda *a, **k: {
        "tu": ["hapas"], "moi": 2, "pheu": {"tiktok": T._pheu_moi(3, "x")}, "ghi_chu": []})
    mo.setattr(T, "_lay_binh_luan", lambda *a, **k: {})
    mo.setattr(T, "_kiem_do_phu", lambda *a, **k: {
        "usd": 0.03, "so_yeu_cau": 10, "bo_sung": 3, "cu": 1,
        "so": {"so_mau": 40, "so_nhac": 20, "so_da_co": 15, "so_sot": 5, "do_phu": 75.0,
               "do_phu_tl": 62.5}, "mau": {"tag": [1, 2], "tac_gia": [1]}})
    v = GiaViec({"do_phu": {"phan": [{"id": "dp-r9", "run_id": "r9", "nen_tang": "do_phu"}]}}, [])
    T.chay_viec(v)
    (luot,) = kho.luot.values()
    gc = luot["ghi_chu"]
    assert gc.index("kiểm độ phủ (TikTok") < gc.index("phễu tìm TikTok")
    assert "15/20 bài nhắc brand đã có (75%), theo thảo luận 62%" in gc  # 62,5 làm tròn chẵn
    assert luot["bai_moi"] == 2 + 3
    assert "do_phu" not in v.chot[0][1]


# ───────────────────────────── schema + quyền ─────────────────────────────
def test_schema_bang_kiem_do_phu_quyen_va_cot_ghi():
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    khoi = re.search(r"CREATE TABLE IF NOT EXISTS kiem_do_phu \((.*?)\n\);", sql, re.DOTALL)
    assert khoi, "bảng kiem_do_phu có trong schema.sql"
    cot = set(re.findall(r"^\s{2}([a-z_]+)\s", khoi.group(1), re.MULTILINE))
    assert set(K._COT_DO_PHU) <= cot
    assert "GRANT SELECT, INSERT ON kiem_do_phu TO mark;" in sql
    assert "GRANT USAGE ON SEQUENCE kiem_do_phu_id_seq TO mark;" in sql
    assert not re.search(r"GRANT[^;]*(UPDATE|DELETE)[^;]*ON kiem_do_phu[^;]*TO mark", sql)
    assert "CREATE INDEX IF NOT EXISTS kiem_do_phu_du_an_luc" in sql


# ───────────────────────────── tự sửa đường thu thập ─────────────────────────────
def _sot(u, tl, ma=("khac",), tag=()):
    return {"tai_khoan": u, "ten": u.upper(), "thao_luan": tl, "ma_ly_do": list(ma),
            "tag": list(tag), "hanh_dong": []}


def test_hanh_dong_de_xuat_gop_theo_nguoi_bo_nguon_dang_theo_doi():
    sot = [_sot("kol.a", 300), _sot("kol.a", 250), _sot("kol.b", 40), _sot("hapas.official", 900)]
    hd = KDP.hanh_dong(sot, ["hapas"], {"hapas.official"}, None, 70.0, BAY)
    assert [(g["dinh_danh"], g["so_bai"], g["thao_luan"]) for g in hd["de_xuat"]] == [
        ("kol.a", 2, 550), ("kol.b", 1, 40)]
    assert hd["tom"]["de_xuat"][0]["uu_tien"] and not hd["tom"]["de_xuat"][1]["uu_tien"]
    assert "uu_tien" not in hd["de_xuat"][0] and hd["de_xuat"][1]["ly_do"].startswith("kiểm độ phủ")
    assert sot[3]["hanh_dong"] == ["@hapas.official đã là nguồn theo dõi"]
    assert hd["tom"]["noi"]["ly_do"] == "", "sót không do tụt hạng: không nới lượt nổi"


def test_hanh_dong_tag_luot_noi_chi_tag_chien_dich_va_tran_4():
    sot = [_sot("a", 10, tag=("hapas", "fyp", "lammoidieuviyeu")),
           _sot("b", 10, tag=("lammoidieuviyeu", "motlan")),
           _sot("c", 600, tag=("quatang2010",)), _sot("d", 1, tag=("hapasxthom",))]
    hd = KDP.hanh_dong(sot, ["hapas"], set(), {"tag": ["cu1", "cu2", "cu3"]}, 70.0, BAY)
    # quatang2010 (thảo luận ≥ 500), lammoidieuviyeu (2 bài), hapasxthom (chứa tên brand); #fyp,
    # #hapas (đã là từ khoá), #motlan (1 bài, ít) không. Tối đa 4 tag, tag mới đi trước.
    assert hd["noi_cfg"]["tag"] == ["quatang2010", "lammoidieuviyeu", "hapasxthom", "cu1"]
    assert hd["tom"]["tag_them"] == ["quatang2010", "lammoidieuviyeu", "hapasxthom"]


def test_hanh_dong_noi_trang_roi_nhip_roi_lui_khi_tot():
    tut = [_sot("a", 5, ("ngoai_cua_so",)), _sot("b", 5, ("it_thich",))]
    hd = KDP.hanh_dong(tut, ["hapas"], set(), None, 50.0, BAY)
    assert (hd["noi_cfg"]["trang"], hd["noi_cfg"]["gio"]) == (3, 20)
    hd = KDP.hanh_dong(tut, ["hapas"], set(), {"trang": 4, "gio": 20}, 50.0, BAY)
    assert (hd["noi_cfg"]["trang"], hd["noi_cfg"]["gio"]) == (4, 10)
    hd = KDP.hanh_dong(tut, ["hapas"], set(), {"trang": 4, "gio": 10}, 50.0, BAY)
    assert (hd["noi_cfg"]["trang"], hd["noi_cfg"]["gio"]) == (4, 10), "đã tối đa"
    # Một bài tụt hạng nhỏ (< 25% thảo luận sót) không đủ để nới.
    hd = KDP.hanh_dong([_sot("a", 1, ("it_thich",)), _sot("b", 99)], ["hapas"], set(), None,
                       50.0, BAY)
    assert hd["noi_cfg"]["trang"] == 2
    # Độ phủ tốt, không còn tụt hạng: lùi một nấc (nhịp trước, rồi trang).
    hd = KDP.hanh_dong([], ["hapas"], set(), {"trang": 4, "gio": 10}, 95.0, BAY)
    assert (hd["noi_cfg"]["trang"], hd["noi_cfg"]["gio"]) == (4, 20)
    hd = KDP.hanh_dong([], ["hapas"], set(), {"trang": 4, "gio": 20}, 95.0, BAY)
    assert (hd["noi_cfg"]["trang"], hd["noi_cfg"]["gio"]) == (3, 20)
    assert KDP.cau_hinh_noi({"trang": 99, "gio": 1, "tag": "rác"}) == {"trang": 4, "gio": 10,
                                                                       "tag": []}


def test_luot_noi_dung_tag_va_trang_tu_kiem_do_phu_trong_tran(mo):  # noqa: F811
    """Lượt nổi đọc cấu hình kiểm độ phủ: thêm hashtag chiến dịch vào câu tìm, số trang mỗi từ,
    nhịp — trần vẫn là `tran_noi` (phần ước tính TikTok chưa dùng, phần còn của tháng)."""
    mo.setattr(TT, "dung_api", lambda viec: True)
    goi = {}

    def tim(q, bay_gio, tran, trang=2, tag=None, cid=None):
        goi.update(q=list(q), tran=tran, trang=trang, tag=list(tag or []))
        cid["lammoidieuviyeu"] = "c9"           # cid mới tìm được → nhớ vào mốc kiểm độ phủ
        return []
    mo.setattr(T.TDA, "tim_noi_tiktok", tim)
    T.ghi_moc_tk("hapas", {KDP.KHOA_NOI_CFG: {"trang": 3, "gio": 10,
                                              "tag": ["lammoidieuviyeu", "hapas"]},
                           T.TDA.KHOA_MOC_NOI: {"luc": (datetime.datetime.now(_VN)
                                                         - datetime.timedelta(hours=11)).isoformat()}})
    v = GiaViec({}, [])
    phan = [{"run_id": "r1", "actor": T.TT_ACTOR}]
    uoc = 5.0
    _got, noi = T._them_luot_noi(v, "hapas", 3, ["hapas"], [], T.doc_moc_tk("hapas"),
                                 datetime.datetime.now(_VN), uoc, 0.05, phan)
    # Hashtag đọc qua FEED (đo 17/10: tìm như từ khoá chỉ trùng 17/94 bài của feed), không thêm
    # vào câu tìm; "hapas" đã là từ khoá nên không đọc feed lần nữa.
    assert goi["q"] == ["hapas"] and goi["tag"] == ["lammoidieuviyeu"] and goi["trang"] == 3
    assert T.doc_moc_tk("hapas")[KDP.KHOA_MOC]["cid"] == {"lammoidieuviyeu": "c9"}
    assert goi["tran"] <= 0.05 - TT.GIA_YEU_CAU + 1e-9, "trần: phần còn của tháng"
    assert "theo kiểm độ phủ: 3 trang/từ, mỗi 10 giờ, #lammoidieuviyeu, #hapas" in noi["ly_do"]


# ───────────────────────────── dashboard: thẻ Độ phủ + trang Ngân sách ─────────────────────────────
@pytest.mark.parametrize("ch", [{}, {"do_phu": {"bat": False}}, {"do_phu": {"tran_usd": 0}},
                                {"do_phu": {"tran_usd": "x"}}, {"do_phu": {"tran_usd": 0.35}},
                                {"do_phu": {"tran_usd": 7}}, {"do_phu": {"tran_usd": True}},
                                {"do_phu": "hỏng"}, {"do_phu": {"bat": True, "tran_usd": -2}}])
def test_chi_phi_do_phu_khop_mark(ch):
    from dashboard import chi_phi as CP
    assert CP.cau_hinh_do_phu({"cau_hinh": ch}) == KDP.cau_hinh({"cau_hinh": ch})
    assert (CP.DP_TRAN_MAC_DINH, CP.DP_TRAN_TOI_DA, CP.DP_GIO_GIAN) == (
        KDP.TRAN_MAC_DINH, KDP.TRAN_TOI_DA, KDP.GIO_GIAN)


def test_du_bao_do_phu_hai_lan_moi_tuan():
    from dashboard import chi_phi as CP
    bay = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=_VN)
    db = CP.du_bao_do_phu({}, None, bay)
    # 17/10 09:00, 20/10 21:00, 24/10 09:00, 27/10 21:00, 31/10 09:00 → 5 lần × 0,20.
    assert (db["luot_con_lai"], db["con_lai"], db["bat"]) == (5, 1.0, True)
    assert db["luot_30"] == 9 and db["usd_30"] == pytest.approx(1.8)
    db = CP.du_bao_do_phu({}, bay - datetime.timedelta(hours=10), bay)
    assert db["luot_con_lai"] == 4 and db["lan_toi"] == "2026-10-20T11:00+07:00"
    db = CP.du_bao_do_phu({"cau_hinh": {"do_phu": {"bat": False}}}, None, bay)
    assert db["con_lai"] == 0 and db["lan_toi"] is None


def test_ngan_sach_js_do_phu_khop_python(tmp_path):
    import json
    import shutil
    import subprocess
    from dashboard import chi_phi as CP
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    js = (Path(__file__).resolve().parents[1] / "dashboard" / "static" / "ngan_sach.js").read_text(
        encoding="utf-8")
    khoi = re.search(r"// <do_phu>.*?// </do_phu>", js, re.DOTALL).group(0)
    ca = [(True, ""), (False, "0.5"), (True, "0"), (True, "0,35"), (True, "7"), (True, "-1"),
          (True, "rác"), (True, "0.05")]
    hs = CP.hang_so_cho_trinh_duyet()
    chay = (f"var hs = {json.dumps({'do_phu': hs['do_phu']})};\n" + khoi +
            f"\nvar ca = {json.dumps(ca)};\nconsole.log(JSON.stringify(ca.map(function (c) {{"
            " return dpUsd({bat: function () { return c[0]; }, gt: function () { return c[1]; }});"
            " })));\n")
    f = tmp_path / "dp.js"
    f.write_text(chay, encoding="utf-8")
    ra = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True,
                                   encoding="utf-8", check=True, timeout=30).stdout)

    def py(bat, o):
        t = o.replace(",", ".")
        try:
            v = float(t) if t else None
        except ValueError:
            v = "rác"
        ch = {"bat": bat, **({} if v is None else {"tran_usd": v})}
        x = CP.cau_hinh_do_phu({"cau_hinh": {"do_phu": ch}})
        return x["tran_usd"] if x["bat"] else 0
    assert ra == [py(b, o) for b, o in ca]


def _dong_dp(tl, luc, **kw):
    return {"id": 1, "luot_id": 9, "luc": luc, "nen_tang": "tiktok", "so_mau": 120,
            "so_nhac": 40, "so_da_co": 30, "so_da_loai": 2, "so_sot": 10, "thao_luan_nhac": 900,
            "thao_luan_da_co": 600, "do_phu": 75.0, "do_phu_tl": tl, "bo_sung": 4,
            "so_yeu_cau": 60, "chi_phi_usd": 0.18,
            "mau": {"tag": [{"ten": "#hapas"}], "tac_gia": [{"ten": "@kol.a"}], "ngay": 30,
                    "tran_usd": 0.2},
            "bai_sot": [{"khoa": "tiktok:1", "link": "javascript:alert(1)", "tai_khoan": "kol.moi",
                         "thao_luan": 769, "ma_ly_do": ["chi_hashtag", "ngoai_cua_so"],
                         "ly_do": ["chỉ nhắc brand qua hashtag"], "duong": ["#hapas"],
                         "hanh_dong": ["đã ghi vào kho", "đề xuất theo dõi @kol.moi (ưu tiên)"],
                         "bo_sung": True},
                        {"khoa": "tiktok:2", "link": "https://www.tiktok.com/@b/video/2",
                         "ma_ly_do": ["chi_hashtag"], "thao_luan": 5}],
            "hanh_dong": {"de_xuat": [{"dinh_danh": "kol.moi", "so_bai": 1, "thao_luan": 769,
                                       "uu_tien": True}], "tag_noi": ["lammoidieuviyeu"],
                          "tag_them": ["lammoidieuviyeu"],
                          "noi": {"trang": [2, 3], "gio": [20, 20],
                                  "ly_do": "nới lượt nổi lên 3 trang/từ khoá"}}, **kw}


def test_do_phu_json_doi_diem_canh_bao_link_an_toan():
    from dashboard import chi_so as CS
    bay = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=_VN)
    assert CS.do_phu_json([], bay) is None
    x = CS.do_phu_json([_dong_dp(66.67, bay - datetime.timedelta(hours=2)),
                        _dong_dp(70.0, bay - datetime.timedelta(days=4))], bay)
    assert x["do_phu_tl"] == 66.67 and x["doi_diem"] == -3.3 and x["canh_bao"] and not x["cu"]
    assert x["bai_sot"][0]["link"] == "" and x["bai_sot"][1]["link"].startswith("https://")
    assert x["ly_do"][0] == {"ma": "chi_hashtag", "ten": "chỉ có hashtag", "so": 2}
    assert x["hanh_dong"]["tag_them"] == ["lammoidieuviyeu"] and x["tran_usd"] == 0.2
    assert x["bai_sot"][0]["hanh_dong"][1] == "đề xuất theo dõi @kol.moi (ưu tiên)"
    x = CS.do_phu_json([_dong_dp(85.0, bay - datetime.timedelta(days=8))], bay)
    assert not x["canh_bao"] and x["cu"] and x["doi_diem"] is None and x["truoc"] is None
    assert CS.noi_tu_hanh_dong(_dong_dp(1, bay)["hanh_dong"]) == {
        "tag": ["lammoidieuviyeu"], "trang": 3, "gio": 20}


def test_api_chi_so_co_the_do_phu_va_bang_chua_tao_thi_bo_the():
    from test_dashboard_app import XEM, dang_nhap, tao
    from dashboard.kho import LoiKho
    _, c, kho = tao()
    dang_nhap(c, XEM)
    url = "/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14"
    assert c.get(url).json()["do_phu"] is None
    luc = datetime.datetime.now(_VN) - datetime.timedelta(hours=1)
    kho.do_phu = [_dong_dp(66.67, luc), _dong_dp(70.0, luc - datetime.timedelta(days=4))]
    d = c.get(url).json()["do_phu"]
    assert d["do_phu_tl"] == 66.67 and d["canh_bao"] and d["so_sot"] == 10

    def hong(*a, **k):
        raise LoiKho("kho lắng nghe báo lỗi (UndefinedTable: 42P01)")
    kho.do_phu_gan_nhat = hong
    r = c.get(url)
    assert r.status_code == 200 and r.json()["do_phu"] is None


def test_trang_ngan_sach_kiem_do_phu_luu_cong_tac_va_tran():
    from test_dashboard_app import QL, XEM, dang_nhap, tao, thong_bao
    _, c, kho = tao()
    kho.do_phu = [_dong_dp(66.67, datetime.datetime.now(_VN) - datetime.timedelta(hours=1))]
    csrf = dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert "Kiểm độ phủ (TikTok, 2 lần/tuần)" in t and 'name="dp_tran"' in t
    assert re.search(r'name="dp_bat" value="1"[^>]*checked', t)
    assert "lượt nổi: #lammoidieuviyeu" in t and "3 trang/từ khoá, mỗi 20 giờ" in t
    assert "kiểm độ phủ" in t and "tối đa <b>0,20</b> USD/lần" in t
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "dp_tran": "0,35"})
    assert "Đã lưu cấu hình thu thập" in thong_bao(c, r)
    assert kho.du_an["hapas"]["cau_hinh"]["do_phu"] == {"bat": False, "tran_usd": 0.35}
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "dp_bat": "1", "dp_tran": ""})
    assert kho.du_an["hapas"]["cau_hinh"]["do_phu"] == {"bat": True}
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "dp_bat": "1", "dp_tran": "5"})
    assert "Kiểm độ phủ: trần tối đa" in thong_bao(c, r)
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf})
    assert "do_phu" not in kho.du_an["hapas"]["cau_hinh"], "biểu mẫu cũ không có ô: không đụng"
    dang_nhap(c, XEM)
    t = c.get("/ngan-sach").text
    assert 'name="dp_tran"' not in t and "Kiểm độ phủ (TikTok, 2 lần/tuần)" in t
