"""Lọc seeding affiliate cấp BÀI (18/10/2026, `loc_rac.tai_khoan_seeding`, `theo_doi._loc_seeding`).

Mẫu `mau_seeding_tiktok.json` cắt từ raw scraptik đã trả tiền của đợt điều tra Kompa (tài khoản, tên,
id video đã thay): một tài khoản affiliate đăng 8 video chỉ có hashtag trong ngày 15/10 (thật: 177
video), một người bán hàng livestream 6 bài/ngày nhưng 13–62 nghìn lượt xem, một tài khoản nhiều bình
luận thật, một nhà sáng tạo review 1 bài/ngày. Bài đi qua ĐÚNG bộ chuẩn hoá TikTok của Mark
(`tiktok_api.video` → `_chuan_clockworks` → `_chuan_tiktok`). Kho giả, không Postgres, không AI thật."""
from __future__ import annotations

import copy
import datetime
import json
from pathlib import Path

import pytest

import apify_tool as A
import kiem_do_phu as KDP
import lang_nghe_db as K
import loc_rac as L
import theo_doi as T
import theo_doi_api as TDA
import tiktok_api as TT

_VN = datetime.timezone(datetime.timedelta(hours=7))
MAU = json.loads((Path(__file__).parent / "mau_seeding_tiktok.json").read_text(encoding="utf-8"))
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"], "tu_loai_tru": ["guitar"],
         "boi_canh": "HAPAS — thương hiệu túi xách Việt Nam", "thi_truong": "VN", "cau_hinh": {}}


def _lech() -> int:
    """Dời giờ đăng của mẫu để video mới nhất là HÔM QUA: bài thử không phụ thuộc ngày chạy (sổ
    seeding chỉ giữ 92 ngày, phạm vi tính từ hôm nay)."""
    cuoi = max(int(a["create_time"]) for k, xs in MAU.items() if not k.startswith("_") for a in xs)
    dich = int((datetime.datetime.now(_VN) - datetime.timedelta(days=1)).timestamp()) - cuoi
    return dich // 86400 * 86400              # trọn ngày: bài cùng ngày (giờ VN) vẫn cùng ngày


def _hits(nhom: str, *, dich_ngay: int = 0, cung_ngay: bool = False, so_lan: int = 1) -> list:
    """Bài của một nhóm mẫu qua bộ chuẩn hoá TikTok thật -> [(d, dt)]. `cung_ngay`: dồn mọi bài vào
    ngày của bài đầu (giữ giờ); `so_lan`: nhân bản (id mới) để đủ nhịp."""
    lech = _lech() + dich_ngay * 86400
    goc = MAU[nhom]
    items = []
    for lan in range(so_lan):
        for i, a in enumerate(goc):
            a = copy.deepcopy(a)
            t = int(a["create_time"]) + lech
            if cung_ngay:
                d0 = datetime.datetime.fromtimestamp(int(goc[0]["create_time"]) + lech, _VN)
                d1 = datetime.datetime.fromtimestamp(t, _VN)
                t = int(d1.replace(year=d0.year, month=d0.month, day=d0.day).timestamp())
            a["create_time"] = t + lan * 60
            a["aweme_id"] = str(int(a["aweme_id"]) + 1000 * lan)
            items.append(TT.video(a))
    ra = A._chuan_tiktok(A._chuan_clockworks(items))
    for d, _ in ra:
        d["platform"] = "tiktok"
    return ra


def _dong(hits: list) -> list[dict]:
    return [{"tk": L.khoa_tai_khoan("tiktok", d["username"]), "khoa": d["link"], "dang_luc": dt,
             "bl": d["comments"], "xem": d["views"]} for d, dt in hits]


CFG = L.cau_hinh_seeding(DU_AN)


# ───────────────────────────── luật thuần ─────────────────────────────
def test_bat_tai_khoan_affiliate_khong_bat_nha_sang_tao_that():
    """8 video chỉ hashtag trong một ngày, 0 bình luận, vài trăm lượt xem → seeding. Livestream 6
    bài/ngày nhưng trung vị ~26 nghìn xem, tài khoản 5 bài/ngày trung vị 37 bình luận, review 1
    bài/ngày → KHÔNG bắt (creator thật hay có tương tác thật)."""
    rows = (_dong(_hits("seeding")) + _dong(_hits("livestream"))
            + _dong(_hits("tuong_tac_that", cung_ngay=True) + _hits("tuong_tac_that",
                                                                     cung_ngay=True)[:1])
            + _dong(_hits("review")))
    rows[-5]["khoa"] += "-ban-sao"                 # bản nhân của tài khoản tương tác: khoá khác
    seed = L.tai_khoan_seeding(rows, CFG, set(), ["HAPAS", "hapas"])
    assert set(seed) == {("tiktok", "aff_mau")}
    x = seed[("tiktok", "aff_mau")]
    assert (x["so_bai"], x["max_ngay"], x["tv_bl"]) == (8, 8, 0) and x["tv_xem"] < 1000
    # Bỏ điều kiện lượt xem thì người livestream bị bắt nhầm — điều kiện này là cần.
    seed0 = L.tai_khoan_seeding(rows, {**CFG, "trung_vi_xem": 0}, set(), ["HAPAS"])
    assert ("tiktok", "live_mau") in seed0
    assert "aff_mau: 8 bài, cao nhất 8 bài ngày" in L.cau_seeding(("tiktok", "aff_mau"), x)


def test_nhip_7_ngay_va_nguong_mot_ngay():
    """Không ngày nào ≥ 5 bài nhưng 3 bài/ngày suốt 7 ngày, 0 bình luận → 21 ≥ 20 → seeding; 2 bài/
    ngày (14/7 ngày) hay 4 bài trong một ngày → không."""
    goc = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=_VN)

    def tk(ten, moi_ngay, so_ngay):
        return [{"tk": ("tiktok", ten), "khoa": f"{ten}:{n}:{i}", "bl": 0, "xem": 500,
                 "dang_luc": goc + datetime.timedelta(days=n, minutes=i)}
                for n in range(so_ngay) for i in range(moi_ngay)]
    seed = L.tai_khoan_seeding(tk("ba", 3, 7) + tk("hai", 2, 7) + tk("bon", 4, 1), CFG)
    assert set(seed) == {("tiktok", "ba")} and seed[("tiktok", "ba")]["max_7"] == 21


def test_kenh_nha_va_tai_khoan_mang_ten_brand_khong_bao_gio_la_seeding():
    hits = _hits("seeding")
    rows = _dong(hits)
    assert L.tai_khoan_seeding(rows, CFG, {("tiktok", "aff_mau")}, ["HAPAS"]) == {}
    brand = [{**r, "tk": ("tiktok", "hapas.aeon_mau")} for r in rows]
    assert L.tai_khoan_seeding(brand, CFG, set(), ["HAPAS", "hapas"]) == {}
    assert L.tai_khoan_seeding(brand, {**CFG, "mien_ten_brand": False}, set(), ["HAPAS"])
    # Trang Facebook của cửa hàng có định danh là id số, tên hiển thị mang tên brand (raw mina 17/10:
    # "HAPAS SÀI GÒN" 7 bài/ngày, 0 bình luận) — chỉ cần MỘT dòng có tên là miễn.
    # (Facebook phải bật ở `nen_tang` — mặc định luật chỉ áp TikTok, soát M4.)
    cfg_fb = {**CFG, "nen_tang": ["tiktok", "facebook"]}
    so = [{**r, "tk": ("facebook", "61594301968444")} for r in rows]
    so[0]["ten"] = "HAPAS SÀI GÒN"
    assert L.tai_khoan_seeding(so, cfg_fb, set(), ["HAPAS", "hapas"]) == {}
    assert L.tai_khoan_seeding([{**r, "ten": "Phạm Mai Khanh"} for r in so[1:]], cfg_fb, set(),
                               ["HAPAS"]), "affiliate Shopee tên người: vẫn bắt"
    # Facebook kênh nhà: định danh URL trang, bài lượt tìm mang slug trang.
    nha = T._kenh_nha([{"nen_tang": "facebook", "loai": "kenh_nha",
                        "dinh_danh": "https://www.facebook.com/HapasGlobal"},
                       {"nen_tang": "tiktok", "loai": "kol", "dinh_danh": "aff_mau"}])
    assert nha == {("facebook", "facebook.com/hapasglobal"), ("facebook", "hapasglobal")}


def test_chi_tiktok_mac_dinh_xem_0_facebook_la_thieu_va_dung_tuong_tac():
    """Soát 18/10/2026 (M4): luật chỉ áp TikTok trừ khi bật thêm; Facebook / Instagram trả 0 khi
    THIẾU lượt xem — 0 đó không phải "≤ 15.000 xem"; không có số xem thì dùng thích + chia sẻ."""
    goc = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=_VN)

    def fb(ten, tt, p="facebook", xem=0):
        return [{"tk": (p, ten), "khoa": f"{p}:{ten}:{i}", "bl": 0, "xem": xem, "tt": tt,
                 "dang_luc": goc + datetime.timedelta(minutes=i)} for i in range(8)]
    rows = fb("shop_dong", 5000) + fb("aff_fb", 3) + fb("ig_dong", 4000, "instagram")
    assert L.tai_khoan_seeding(rows, CFG) == {}, "mặc định chỉ TikTok"
    bat = {**CFG, "nen_tang": ["tiktok", "facebook", "instagram"]}
    seed = L.tai_khoan_seeding(rows, bat)
    assert set(seed) == {("facebook", "aff_fb")}, "xem 0 = thiếu; 5.000 thích + chia sẻ: không bắt"
    assert seed[("facebook", "aff_fb")]["tv_xem"] is None and seed[("facebook", "aff_fb")]["tv_tt"] == 3
    assert "không có lượt xem, trung vị 3 thích + chia sẻ" in L.cau_seeding(
        ("facebook", "aff_fb"), seed[("facebook", "aff_fb")])
    assert L.tai_khoan_seeding([{**r, "tt": None} for r in fb("aff_fb", 3)], bat) == {}, \
        "không có cả số xem lẫn tương tác: không kết luận"
    # Cấu hình: nen_tang lạ bỏ, rỗng = không nền tảng nào.
    assert L.cau_hinh_seeding({"cau_hinh": {"seeding": {"nen_tang": ["Facebook", "x"]}}})[
        "nen_tang"] == ["facebook"]
    assert L.cau_hinh_seeding({"cau_hinh": {"seeding": {"nen_tang": []}}})["nen_tang"] == []


def test_facebook_hai_lan_doc_khac_pfbid_dem_mot_bai():
    """Khoá phụ ổn định ("phu" — id số / chữ ký nội dung): hai lần đọc cùng một bài Facebook (pfbid
    khác) là MỘT bài của nhịp đăng (soát M4: lịch sử `them` của script nạp raw)."""
    goc = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=_VN)
    bat = {**CFG, "nen_tang": ["facebook"], "trung_vi_tuong_tac": 0}
    lan1 = [{"tk": ("facebook", "a"), "khoa": f"facebook:pfbidA{i}", "phu": [f"facebook:id:{i}"],
             "bl": 0, "xem": None, "dang_luc": goc + datetime.timedelta(minutes=i)} for i in range(3)]
    lan2 = [{**r, "khoa": r["khoa"].replace("pfbidA", "pfbidB")} for r in lan1]
    assert L.tai_khoan_seeding(lan1 + lan2, bat) == {}, "3 bài, không phải 6"
    d = {"platform": "facebook", "username": "a", "kenh": "A", "comments": 0, "likes": 2,
         "shares": 1, "link": "https://www.facebook.com/a/posts/pfbid0xyz",
         "text": "Túi HAPAS pass lại giá tốt", "__goc": {"post_id": "123456789012"}}
    x = T._dong_seeding(d, goc)
    assert x["khoa"] == "facebook:id:123456789012" and x["tt"] == 3 and x["phu"][0].startswith(
        "facebook:")
    k = T._dong_kho_seeding({"khoa": "facebook:pfbidcu", "nen_tang": "facebook", "tai_khoan": "a",
                             "tac_gia": "A", "link": d["link"], "noi_dung": d["text"],
                             "ma_so_fb": "123456789012", "dang_luc": goc, "binh_luan": 0,
                             "xem": None, "thich": 2, "chia_se": 1})
    assert "facebook:id:123456789012" in k["phu"] and k["tt"] == 3


def test_giu_bai_co_thao_luan_that_va_khong_ket_luan_khi_thieu_so():
    assert L.giu_bai_seeding(10, CFG) and not L.giu_bai_seeding(9, CFG)
    assert not L.giu_bai_seeding(None, CFG) and not L.giu_bai_seeding(50, {**CFG, "giu_bl_tu": 0})
    rows = [{**r, "bl": None} for r in _dong(_hits("seeding"))]
    assert L.tai_khoan_seeding(rows, CFG) == {}, "không có số bình luận nào: không kết luận"


def test_cau_hinh_mac_dinh_bat_va_so_rac_ve_mac_dinh():
    assert L.cau_hinh_seeding({}) == L.SEEDING_BAI and L.SEEDING_BAI["bat"] is True
    assert L.cau_hinh_seeding({"cau_hinh": {"seeding": {"bat": False}}})["bat"] is False
    assert L.cau_hinh_seeding({"cau_hinh": {"seeding": {"bat": "false"}}})["bat"] is True
    c = L.cau_hinh_seeding({"cau_hinh": {"seeding": {"bai_mot_ngay": "abc", "bai_bay_ngay": True,
                                                     "trung_vi_xem": 0, "giu_bl_tu": -3,
                                                     "ngay": 500, "trung_vi_bl": 4}}})
    assert (c["bai_mot_ngay"], c["bai_bay_ngay"], c["trung_vi_xem"], c["giu_bl_tu"], c["ngay"],
            c["trung_vi_bl"]) == (5, 20, 0, 10, 35, 4)
    assert L.tai_khoan_seeding(_dong(_hits("seeding")), {**CFG, "bat": False}) == {}


# ───────────────────────────── tích hợp pipeline lượt tìm ─────────────────────────────
class KhoGia:
    def __init__(self, nguon=()):
        self.bai: dict[str, dict] = {}
        self.nguon = list(nguon)
        self.ghi: list[list[dict]] = []

    def cai(self, mp):
        for ten in ("khoa_da_co", "cap_nhat_so_lieu", "nguon_cua_du_an", "lich_su_tai_khoan",
                    "ghi_bai", "ghi_de_xuat", "khoa_fb_trung"):
            mp.setattr(K, ten, getattr(self, ten))
        return self

    def khoa_da_co(self, ma, khoa):
        return {k for k in khoa if k in self.bai}

    def cap_nhat_so_lieu(self, ma, luot, rows):
        return len(rows)

    def nguon_cua_du_an(self, ma):
        return list(self.nguon)

    def lich_su_tai_khoan(self, ma, tai_khoan, tu):
        return [{"khoa": r["khoa"], "nen_tang": r["nen_tang"], "tai_khoan": r["tai_khoan"].lower(),
                 "dang_luc": r["dang_luc"], "binh_luan": r["binh_luan"], "xem": r["xem"]}
                for r in self.bai.values() if r["tai_khoan"].lower() in tai_khoan
                and r["dang_luc"] >= tu]

    def ghi_bai(self, ma, luot, kieu, rows):
        self.ghi.append([dict(r) for r in rows])
        for r in rows:
            self.bai[r["khoa"]] = dict(r)
        return len(rows), 0

    def ghi_de_xuat(self, ma, cac):
        return 0

    def khoa_fb_trung(self, ma, rows):
        return {}


@pytest.fixture
def ai(monkeypatch):
    """AI giả: ghi lại tài khoản của MỌI bài được gửi, không phán gì (bài giữ theo từ khoá)."""
    goi: list[list[str]] = []

    def phan_xu(rows, *a, **k):
        goi.append([d["username"] for d, _ in rows])
        return {}, {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"}
    monkeypatch.setattr(A, "_phan_xu_ai", phan_xu)
    return goi


def _tk() -> dict:
    tu = datetime.datetime.now(_VN) - datetime.timedelta(days=60)
    return {"pheu": {}, "moi": 0, "cu": 0, "giu": 0, "de_xuat": 0, "cap_nhat": 0,
            "pham_vi": {"tu": tu.isoformat(timespec="minutes")}}


def test_luot_tim_bo_seeding_truoc_ai_ghi_so_va_luot_sau_van_nho(monkeypatch, ai):
    kho = KhoGia().cai(monkeypatch)
    hits = _hits("seeding") + _hits("review") + _hits("livestream")
    tk = _tk()
    T._tach_va_giu(DU_AN, 7, hits, ["hapas"], 1e12, tk)
    f = tk["pheu"]["tiktok"]
    assert f["seeding"] == 8 and tk["seeding"] == 8
    assert sorted(set(ai[0])) == ["live_mau", "review_mau"], "bài seeding không tới AI"
    assert {r["tai_khoan"] for r in kho.ghi[0]} == {"live_mau", "review_mau"}
    dau = TDA.dau_loai(DU_AN, ["hapas"])
    so = TDA.doc_loai("hapas", dau, datetime.datetime.now(_VN) - datetime.timedelta(days=60))
    seed_k = {T._khoa_bai("tiktok", d["link"], {"id": d["__goc"]["id"]}) for d, _ in hits[:8]}
    assert {k for k, v in so.items() if v[0] == L.LY_DO_SEEDING_BAI} == seed_k
    assert len(TDA.doc_seeding("hapas")) == 8
    assert "seeding affiliate 8" in T._cau_pheu("tiktok", f)
    assert "bỏ 8 bài seeding affiliate của 1 tài khoản (@aff_mau 8 bài ngày" in T._cau_seeding_tk(tk)
    # Gặp lại bài đã loại (cùng dấu luật, soát 18/10/2026 H1): sổ KHÔNG chặn vĩnh viễn lý do
    # seeding — luật hiện hành xét lại (vẫn seeding: bỏ lại), không tới AI, không ghi kho; bài vẫn
    # là bài đã biết (không đếm "chưa thấy" của nhịp giãn).
    tk2 = _tk()
    T._tach_va_giu(DU_AN, 8, _hits("seeding"), ["hapas"], 1e12, tk2)
    f2 = tk2["pheu"]["tiktok"]
    assert (f2["da_loai_truoc"], f2["xet_lai"], f2["seeding"]) == (0, 8, 8)
    assert len(ai) == 1 and len(kho.ghi) == 1
    assert "xét lại theo luật 8 bài đã loại" in T._cau_pheu("tiktok", f2)
    # Lượt sau, ĐỔI từ khoá (dấu luật khác → phần "bai" của sổ làm lại từ đầu): MỘT video mới của
    # cùng tài khoản (ngày khác) + 8 bài cũ. Kho không có bài nào của tài khoản, nhưng sổ seeding nhớ
    # nhịp 8 bài/ngày → vẫn bỏ cả 9, không bài nào tới AI.
    moi = _hits("seeding", dich_ngay=1)[:1]
    moi[0][0]["link"] = moi[0][0]["link"].replace(moi[0][0]["__goc"]["id"], "7690000000000999999")
    moi[0][0]["__goc"]["id"] = "7690000000000999999"
    tk3 = _tk()
    T._tach_va_giu({**DU_AN, "tu_khoa": ["hapas", "túi hapas"]}, 9, moi + _hits("seeding"),
                   ["hapas", "túi hapas"], 1e12, tk3)
    assert tk3["pheu"]["tiktok"]["seeding"] == 9 and len(ai) == 1 and len(kho.ghi) == 1
    assert len(TDA.doc_seeding("hapas")) == 9


def _hits_bl(n: int) -> list:
    """8 bài của tài khoản seeding mẫu, mỗi bài `n` bình luận (lần đọc sau)."""
    hits = _hits("seeding")
    for d, _ in hits:
        d["comments"] = n
    return hits


def test_bai_seeding_len_binh_luan_hom_sau_duoc_xet_lai_va_giu(monkeypatch, ai):
    """Soát 18/10/2026 (H1): lượt 07:00 thấy 8 video gần 0 bình luận → loại cả 8. Hôm sau mỗi video
    40 bình luận: sổ không chặn, luật xét lại trên SỐ MỚI (trung vị 40 > 2, mỗi bài ≥ 10) → cả 8 tới
    AI và vào kho; sổ seeding nhận số mới."""
    kho = KhoGia().cai(monkeypatch)
    T._tach_va_giu(DU_AN, 7, _hits("seeding"), ["hapas"], 1e12, _tk())
    assert ai == [] and {x["bl"] for x in TDA.doc_seeding("hapas")} == {0}
    tk = _tk()
    T._tach_va_giu(DU_AN, 8, _hits_bl(40), ["hapas"], 1e12, tk)
    f = tk["pheu"]["tiktok"]
    assert (f["xet_lai"], f["seeding"], f["da_loai_truoc"]) == (8, 0, 0)
    assert len(ai) == 1 and len(ai[0]) == 8 and [r["binh_luan"] for r in kho.ghi[0]] == [40] * 8
    # Bài đã vào kho: khoá gỡ khỏi sổ seeding + sổ "đã loại" (soát 18/10/2026) — nhịp đăng của
    # tài khoản đọc từ kho; kiểm độ phủ không còn thấy bài vừa "đã có" vừa "đã loại".
    assert TDA.doc_seeding("hapas") == []
    assert TDA.doc_loai("hapas", TDA.dau_loai(DU_AN, ["hapas"]),
                        datetime.datetime.now(_VN) - datetime.timedelta(days=60)) == {}
    # Số luỹ kế: một lần đọc cũ hơn (ít bình luận hơn) không hạ số trong sổ.
    TDA.ghi_seeding("hapas", [T._dong_so_seeding(d, dt) for d, dt in _hits_bl(40)])
    TDA.ghi_seeding("hapas", [T._dong_so_seeding(d, dt) for d, dt in _hits_bl(3)])
    assert {x["bl"] for x in TDA.doc_seeding("hapas")} == {40}


def test_bai_ai_loai_sau_xet_lai_van_o_so_seeding_voi_so_moi(monkeypatch):
    """Bài seeding được xét lại (đủ bình luận) nhưng AI loại: KHÔNG vào kho, nên vẫn ở sổ seeding
    với số mới (nhịp đăng của tài khoản cho lượt sau) và sổ "đã loại" ghi lý do AI."""
    KhoGia().cai(monkeypatch)
    monkeypatch.setattr(A, "_phan_xu_ai", lambda rows, *a, **k: (
        {i: (False, "lac_de", "") for i in range(len(rows))},
        {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"}))
    T._tach_va_giu(DU_AN, 7, _hits("seeding"), ["hapas"], 1e12, _tk())
    T._tach_va_giu(DU_AN, 8, _hits_bl(40), ["hapas"], 1e12, _tk())
    so_seed = TDA.doc_seeding("hapas")
    assert {x["bl"] for x in so_seed} == {40} and len(so_seed) == 8
    so = TDA.doc_loai("hapas", TDA.dau_loai(DU_AN, ["hapas"]),
                      datetime.datetime.now(_VN) - datetime.timedelta(days=60))
    assert {v[0] for v in so.values()} == {"ai:lac_de"}


def test_tat_luat_doi_nguong_hay_thanh_kenh_nha_thi_bai_da_loai_duoc_xet_lai(monkeypatch, ai):
    """Bài đã loại vì seeding: tắt luật, nâng ngưỡng hay duyệt tài khoản thành kênh nhà thì lượt sau
    bài đi tiếp (dấu luật `dau_loai` không tính `cau_hinh`, nên sổ không được chặn)."""
    kho = KhoGia().cai(monkeypatch)
    nha = [{"id": 1, "nen_tang": "tiktok", "dinh_danh": "aff_mau", "loai": "kenh_nha"}]
    for i, (da, nguon) in enumerate((
            ({**DU_AN, "cau_hinh": {"seeding": {"bat": False}}}, []),
            ({**DU_AN, "cau_hinh": {"seeding": {"bai_mot_ngay": 9, "bai_bay_ngay": 50}}}, []),
            (DU_AN, nha))):
        kho.bai.clear()                       # bài lần trước giữ ra khỏi kho: lần này là bài mới
        kho.nguon = []
        T._tach_va_giu(DU_AN, 7, _hits("seeding"), ["hapas"], 1e12, _tk())      # loại → sổ
        assert len(ai) == i
        kho.nguon = nguon
        tk = _tk()
        T._tach_va_giu(da, 8 + i, _hits("seeding"), ["hapas"], 1e12, tk)
        assert len(ai) == i + 1 and len(ai[-1]) == 8 and not tk["pheu"]["tiktok"]["seeding"]
        assert tk["pheu"]["tiktok"]["xet_lai"] == 8
        assert TDA.doc_seeding("hapas") == [], "bài đã giữ: khoá gỡ khỏi sổ seeding"


def test_mien_ten_brand_dung_cung_danh_sach_ten_voi_cong_brand(monkeypatch, ai):
    """Soát 18/10/2026 (LOW): tài khoản mang tên thương hiệu con khai ở cấu hình cổng brand
    ("ten": ["Mate Made"]) được miễn luật seeding như tên dự án."""
    KhoGia().cai(monkeypatch)
    monkeypatch.setattr(T, "khau_hieu_chien_dich", lambda ma, bay_gio: (None, []))
    hits = _hits("seeding")
    for d, _ in hits:
        d["username"] = "matemade.store"
    T._tach_va_giu(DU_AN, 7, hits, ["hapas"], 1e12, tk := _tk())
    assert tk["pheu"]["tiktok"]["seeding"] == 8 and ai == []
    da = {**DU_AN, "cau_hinh": {"hashtag_can_nhac_brand": {"ten": ["Mate Made"]}}}
    TDA.bo_khoi_so("hapas", [x["khoa"] for x in TDA.doc_seeding("hapas")])
    T._tach_va_giu(da, 8, hits, ["hapas"], 1e12, tk2 := _tk())
    assert not tk2["pheu"]["tiktok"]["seeding"] and len(ai) == 1 and len(ai[0]) == 8


def test_mien_seeding_khong_dung_tag_tu_hoc_va_so_nguyen_cum(monkeypatch, ai):
    """Soát 18/10/2026 (MEDIUM): miễn seeding so CHUỖI CON trên định danh / tên hiển thị, nên chỉ
    dùng tên NGƯỜI đặt (`ten_mien_seeding`: tên, mã, "ten" cấu hình, `du_an.hashtag`) — (b) tag kiểm
    độ phủ tự học (#quatangxinh) không miễn shop affiliate "quatangxinh.shop", kể cả ở script dọn;
    (c) "Mate Made" so nguyên cụm "matemade", không tách ra "made" để miễn mọi "handmade…"."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import lang_nghe_loc_seeding as S
    KhoGia().cai(monkeypatch)
    monkeypatch.setattr(T, "khau_hieu_chien_dich", lambda ma, bay_gio: (None, ["Quà tặng xinh"]))
    T.ghi_moc_tk("hapas", {KDP.KHOA_NOI_CFG: {"tag": ["quatangxinh", "hapassale"]}})
    da = {**DU_AN, "hashtag": ["hapas", "quatang2010", "yeutudieunhonhat"],
          "cau_hinh": {"hashtag_can_nhac_brand": {"ten": ["Mate Made"]}}}
    assert T.ten_mien_seeding(da) == ["HAPAS", "hapas", "Mate Made", "yeutudieunhonhat"]
    assert "quatangxinh" in T.ten_brand(da), "cổng brand vẫn tính khẩu hiệu chiến dịch"
    # (b) lượt quét: tài khoản mang tag học / khẩu hiệu không được miễn.
    hits = _hits("seeding")
    for d, _ in hits:
        d["username"] = "quatangxinh.shop"
    T._tach_va_giu(da, 7, hits, ["hapas"], 1e12, tk := _tk())
    assert tk["pheu"]["tiktok"]["seeding"] == 8 and ai == []
    # (b) script dọn: cùng danh sách (mặc định của `ke_hoach`).
    bai = [{"khoa": f"tiktok:9{i}", "nen_tang": "tiktok", "link": d["link"],
            "tai_khoan": "quatangxinh.shop", "tac_gia": "Quà Tặng Xinh", "dang_luc": dt,
            "binh_luan": 0, "xem": 300, "thich": 1, "chia_se": 0}
           for i, (d, dt) in enumerate(hits)]
    assert set(S.ke_hoach(da, [], bai, [])["tai_khoan"]) == {("tiktok", "quatangxinh.shop")}
    cd = [{**r, "tai_khoan": "yeutudieunhonhat.official"} for r in bai]
    assert S.ke_hoach(da, [], cd, [])["tai_khoan"] == {}, "hashtag của dự án (người đặt): miễn"
    # (c) so nguyên cụm.
    rows = _dong(_hits("seeding"))
    ten = T.ten_mien_seeding(da)
    hand = [{**r, "tk": ("tiktok", "handmade.xinh")} for r in rows]
    assert L.tai_khoan_seeding(hand, CFG, set(), ten), "'made' không phải tên brand"
    assert not L.ten_brand_trong("handmade.xinh", ten) and not L.ten_brand_trong("Made in VN", ten)
    assert L.ten_brand_trong("matemade.store", ten) and L.ten_brand_trong("Mate Made Official", ten)
    assert L.tai_khoan_seeding([{**r, "tk": ("tiktok", "mate_made.hn")} for r in rows], CFG,
                               set(), ten) == {}


def test_tat_luat_seeding_thi_bai_di_tiep_toi_ai(monkeypatch, ai):
    KhoGia().cai(monkeypatch)
    tk = _tk()
    T._tach_va_giu({**DU_AN, "cau_hinh": {"seeding": {"bat": False}}}, 7, _hits("seeding"),
                   ["hapas"], 1e12, tk)
    assert not tk["pheu"]["tiktok"]["seeding"] and len(ai[0]) == 8


def test_bai_seeding_co_thao_luan_that_van_giu(monkeypatch, ai):
    kho = KhoGia().cai(monkeypatch)
    hits = _hits("seeding")
    hits[0][0]["comments"] = 69                       # như video 26/09: 69 bình luận, 1,5 triệu xem
    tk = _tk()
    T._tach_va_giu(DU_AN, 7, hits, ["hapas"], 1e12, tk)
    assert tk["pheu"]["tiktok"]["seeding"] == 7 and [r["binh_luan"] for r in kho.ghi[0]] == [69]


def test_nguon_theo_doi_khong_phai_kenh_nha_cung_qua_luat(monkeypatch, ai):
    """Tài khoản seeding lỡ được duyệt thành nguồn (kol): bài vẫn bị bỏ; nguồn kênh nhà cùng nhịp đăng
    thì giữ hết."""
    KhoGia().cai(monkeypatch)
    nguon = {1: {"id": 1, "nen_tang": "tiktok", "dinh_danh": "aff_mau", "loai": "kol"},
             2: {"id": 2, "nen_tang": "tiktok", "dinh_danh": "nha_mau", "loai": "kenh_nha"}}
    nha = []
    for d, dt in _hits("seeding"):
        d2 = dict(d, username="nha_mau", link=d["link"].replace("aff_mau", "nha_mau")
                  .replace("/video/769", "/video/869"))
        nha.append((d2, dt))
    rows, tk = T.chon_bai(DU_AN, {1: _hits("seeding"), 2: nha}, nguon, 1e12)
    assert tk["seeding"] == 8 and {r["tai_khoan"] for r in rows} == {"nha_mau"} and len(rows) == 8
    assert len(TDA.doc_seeding("hapas")) == 8


_LUC_TT = datetime.datetime.now(_VN) - datetime.timedelta(days=2)


def _bai_tt(i, user, kenh, text, p="tiktok", **them):
    return ({"platform": p, "username": user, "kenh": kenh, "text": text, "hashtags": "hapas",
             "link": (f"https://www.tiktok.com/@{user}/video/55{i}" if p == "tiktok"
                      else f"https://www.youtube.com/watch?v=yt{i:09d}"),
             "comments": 3, "views": 900, "likes": 1, "shares": 0, **them}, _LUC_TT)


def test_cong_thi_truong_vn_chi_bo_chu_ngoai_trong_noi_dung_con_lai_de_ai(monkeypatch):
    """Soát 18/10/2026 (M2): cổng VN trước AI chỉ bỏ bài có NỘI DUNG chữ ngoài VN rõ (chữ Thái) hoặc
    kênh YouTube khai nước khác mà không có dấu hiệu Việt. Tài khoản "HAPAS THAILAND" viết Latin là
    ca mơ hồ → AI; AI giữ với mã other_market thì dự án VN loại (ai:other_market)."""
    kho = KhoGia().cai(monkeypatch)
    gui: list[list[str]] = []

    def phan_xu(rows, *a, **k):
        gui.append([d["username"] for d, _ in rows])
        return ({i: (True, "other_market", "TH") for i, (d, _) in enumerate(rows)
                 if d["username"] == "hapasthailand"},
                {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"})
    monkeypatch.setattr(A, "_phan_xu_ai", phan_xu)
    hits = [_bai_tt(1, "hapasthailand", "HAPAS THAILAND", "New tote collection #hapas"),
            _bai_tt(2, "shop_th", "ร้านกระเป๋า", "กระเป๋าใหม่ hapas สวยมาก ราคาพิเศษ วันนี้"),
            _bai_tt(3, "khach_vn", "Khách", "túi hapas xinh quá trời"),
            _bai_tt(4, "kenh_us", "Hapas Review", "Hapas tote bag honest review and unboxing",
                    p="youtube", _quoc_gia="US"),
            _bai_tt(5, "kenh_us_vn", "Hapas Review", "Review túi Hapas mới nhất", p="youtube",
                    _quoc_gia="US")]
    tk = _tk()
    T._tach_va_giu(DU_AN, 7, hits, ["hapas"], 1e12, tk)
    f, fy = tk["pheu"]["tiktok"], tk["pheu"]["youtube"]
    assert (f["thi_truong"], fy["thi_truong"]) == (1, 1)
    assert sorted(u for g in gui for u in g) == ["hapasthailand", "kenh_us_vn", "khach_vn"]
    assert sorted(r["tai_khoan"] for g in kho.ghi for r in g) == ["kenh_us_vn", "khach_vn"]
    assert f["ai_loai"] == {"other_market": 1}
    so = TDA.doc_loai("hapas", TDA.dau_loai(DU_AN, ["hapas"]), _LUC_TT - datetime.timedelta(days=1))
    assert sorted(v[0] for v in so.values()) == ["ai:other_market", "he_chu", "thi_truong"]
    assert "ngoài thị trường VN 1" in T._cau_pheu("tiktok", f)
    assert "brand ở thị trường khác 1" in T._cau_pheu("tiktok", f)
    # Dự án thị trường khác (TH): không áp cổng VN, AI other_market giữ như social_listen.
    tk2 = _tk()
    T._tach_va_giu({**DU_AN, "ma": "hapas_th", "thi_truong": "TH"}, 7, hits[:2], ["hapas"],
                   1e12, tk2)
    assert not tk2["pheu"]["tiktok"].get("thi_truong") and not tk2["pheu"]["tiktok"]["ai_loai"]


def test_ai_khong_phan_ma_thi_truong_khac_vn_thi_khong_giu_theo_tu_khoa(monkeypatch, ai):
    """Soát 18/10/2026 (LOW): lượt bot, AI không phán (hết giờ / lỗi) → bài nhắc từ khoá được giữ
    theo luật — trừ bài mà tín hiệu thị trường (`_thi_truong`) là nước khác và không có dấu hiệu
    Việt ("HAPAS THAILAND" viết Latin, kênh khai ngôn ngữ Thái): không ghi, không vào sổ (lượt sau
    AI xét lại). Review tiếng Việt trên kênh YouTube khai US vẫn giữ (dấu hiệu Việt thắng)."""
    kho = KhoGia().cai(monkeypatch)
    hits = [_bai_tt(1, "hapasthailand", "HAPAS THAILAND", "New tote collection #hapas"),
            _bai_tt(2, "kenh_th", "Hapas TH", "Hapas new bag", _ngon_ngu="th"),
            _bai_tt(3, "khach_vn", "Khách", "túi hapas xinh quá trời"),
            _bai_tt(4, "kenh_us_vn", "Hapas Review", "Review túi Hapas mới nhất", p="youtube",
                    _quoc_gia="US")]
    tk = _tk()
    T._tach_va_giu(DU_AN, 7, hits, ["hapas"], 1e12, tk)
    assert len(ai) == 1 and len(ai[0]) == 4, "cổng VN để AI quyết ca mơ hồ"
    assert sorted(r["tai_khoan"] for g in kho.ghi for r in g) == ["kenh_us_vn", "khach_vn"]
    f = tk["pheu"]["tiktok"]
    assert f["chua_ai_ngoai_vn"] == 2 and not f["khong_nhac"]
    assert "AI chưa phán mà thị trường khác VN 2 (chưa ghi" in T._cau_pheu("tiktok", f)
    assert TDA.doc_loai("hapas", TDA.dau_loai(DU_AN, ["hapas"]),
                        _LUC_TT - datetime.timedelta(days=1)) == {}, "không vào sổ: lượt sau xét"
    # Dự án thị trường khác (TH): luật không áp — AI không phán thì giữ theo từ khoá như cũ.
    tk2 = _tk()
    T._tach_va_giu({**DU_AN, "ma": "hapas_th", "thi_truong": "TH"}, 8, hits[:1], ["hapas"],
                   1e12, tk2)
    assert not tk2["pheu"]["tiktok"].get("chua_ai_ngoai_vn") and tk2["pheu"]["tiktok"]["giu"] == 1
    # Lượt sau AI phán được: bài được xét lại (AI giữ thì ghi).
    monkeypatch.setattr(A, "_phan_xu_ai", lambda rows, *a, **k: (
        {i: (True, "ugc", "VN") for i in range(len(rows))},
        {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"}))
    kho.bai.clear()
    T._tach_va_giu(DU_AN, 9, hits[:2], ["hapas"], 1e12, tk3 := _tk())
    assert tk3["pheu"]["tiktok"]["giu"] == 2 and not tk3["pheu"]["tiktok"].get("chua_ai_ngoai_vn")


def test_cong_vn_khong_loai_chu_toan_hoc_ten_hien_thi_la_va_caption_khong_dau(monkeypatch, ai):
    """Raw Kompa 18/10/2026: trang "HAPAS - Thương Hiệu Túi Xách Nữ" viết caption bằng chữ toán học
    ("𝗦𝗘𝗧 𝗤𝗨𝗔̀ 𝗕𝗔́𝗡 𝗖𝗛𝗔̣𝗬…") bị cổng cũ đếm là chữ ngoài VN; tài khoản Việt tên hiển thị "𓇼˖°"
    caption trống bị loại vì TÊN; caption không dấu không trúng 40 từ Việt bị YouTube luật "≥ 5 từ
    Latin" loại. Nay cả ba tới AI; bài đã bị loại vì lý do VN được xét lại (NFKC)."""
    KhoGia().cai(monkeypatch)
    hits = [_bai_tt(1, "hapas_page", "HAPAS - Thương Hiệu Túi Xách Nữ",
                    "𝗦𝗘𝗧 𝗤𝗨𝗔̀ 𝗕𝗔́𝗡 𝗖𝗛𝗔̣𝗬 𝗡𝗛𝗔̂́𝗧 𝟮𝟬/𝟭𝟬 𝗡𝗛𝗔̀ 𝗛𝗔𝗣𝗔𝗦 🎁"),
            _bai_tt(2, "botrmnguynth198", "𓇼˖°ꕤ𓇼", ""),
            _bai_tt(3, "kenh_yt", "Linh", "Mo hop tui Hapas size lon gia re cho chi em", p="youtube")]
    hits[1][0]["hashtags"] = ""
    dau = TDA.dau_loai(DU_AN, ["hapas"])
    TDA.ghi_loai("hapas", dau, [(T._khoa_bai("tiktok", hits[0][0]["link"]), "he_chu", _LUC_TT)],
                 _LUC_TT - datetime.timedelta(days=5))
    tk = _tk()
    T._tach_va_giu(DU_AN, 7, hits, ["hapas"], 1e12, tk)
    assert not tk["pheu"]["tiktok"]["thi_truong"] and not tk["pheu"]["youtube"]["thi_truong"]
    assert tk["pheu"]["tiktok"]["xet_lai"] == 1, "bài loại nhầm vì chữ toán học được xét lại"
    assert sorted(u for g in ai for u in g) == ["botrmnguynth198", "hapas_page", "kenh_yt"]
    assert T._ngoai_vn(DU_AN, _bai_tt(9, "x", "ร้าน", "กระเป๋า hapas สวยมาก")[0], ["hapas"]) == \
        "he_chu"
    assert T._ngoai_vn(DU_AN, _bai_tt(9, "x", "김민지", "túi hapas xinh")[0], ["hapas"]) == ""


# ───────────────────────────── sổ ─────────────────────────────
def test_so_loai_giu_so_seeding_khi_doi_dau_luat_va_go_khi_hoan_tac():
    luc = datetime.datetime.now(_VN) - datetime.timedelta(days=3)
    tu = luc - datetime.timedelta(days=10)
    TDA.ghi_seeding("hapas", [{"khoa": "tiktok:1", "nen_tang": "tiktok", "tai_khoan": "aff_mau",
                               "dang_luc": luc, "bl": 0, "xem": 300}])
    TDA.ghi_loai("hapas", "dau1", [("tiktok:1", L.LY_DO_SEEDING_BAI, luc)], tu)
    TDA.ghi_loai("hapas", "dau2", [("tiktok:2", "spam", luc)], tu)       # đổi dấu: "bai" làm lại
    assert set(TDA.doc_loai("hapas", "dau2", tu)) == {"tiktok:2"}
    x = TDA.doc_seeding("hapas", tu)
    assert [(r["khoa"], r["tai_khoan"], r["bl"], r["xem"]) for r in x] == [
        ("tiktok:1", "aff_mau", 0, 300)]
    assert x[0]["dang_luc"] == luc.replace(second=0, microsecond=0)
    assert TDA.bo_khoi_so("hapas", ["tiktok:1", "tiktok:2", "khong_co"]) == 2
    assert TDA.doc_seeding("hapas") == [] and TDA.doc_loai("hapas", "dau2", tu) == {}
    # Bài quá 92 ngày không vào sổ seeding.
    TDA.ghi_seeding("hapas", [{"khoa": "tiktok:3", "nen_tang": "tiktok", "tai_khoan": "a",
                               "dang_luc": luc - datetime.timedelta(days=100), "bl": 0, "xem": 1}])
    assert TDA.doc_seeding("hapas") == []


def test_mo_ta_cau_hinh_seeding_trong_schema_khop_mac_dinh():
    """COMMENT `du_an.cau_hinh` (quy chuẩn BI: mô tả đúng dữ liệu) nói đủ khoá + mặc định của luật."""
    import re
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    m = re.search(r"COMMENT ON COLUMN du_an\.cau_hinh IS '([^']*)';", sql).group(1)
    for k, v in L.SEEDING_BAI.items():
        assert f'"{k}"' in m, k
        if isinstance(v, list):
            assert f'"{k}" (mặc định {json.dumps(v)}' in m, k
        elif not isinstance(v, bool):
            assert re.search(rf'"{k}" \((mặc định )?{v}\b', m), k


def test_kho_loi_khi_doc_lich_su_thi_tinh_tren_so_va_lo(monkeypatch, ai):
    kho = KhoGia().cai(monkeypatch)

    def hong(*a, **k):
        raise K.LoiKho("không nối được kho lắng nghe (OperationalError)")
    monkeypatch.setattr(K, "lich_su_tai_khoan", hong)
    tk = _tk()
    T._tach_va_giu(DU_AN, 7, _hits("seeding"), ["hapas"], 1e12, tk)
    assert tk["pheu"]["tiktok"]["seeding"] == 8 and not kho.ghi
