"""Lệnh `/theodoi` và lượt theo dõi nguồn (đợt 2, 14/10/2026).

Kho `lang_nghe` và mọi nguồn ngoài (Apify, YouTube, model) đều GIẢ: test chạy không cần
Postgres, không ra mạng. Phần SQL được canh bằng đối chiếu cột với `schema.sql` và chạy thật
trên VPS (xem `deploy/lang-nghe/README.md`). Các ca tiền (trần, khởi động lại, lỗi sau khi đã
trả tiền) bám theo review 14/10."""
from __future__ import annotations

import datetime
import re
import threading
import time
from pathlib import Path

import pytest

import apify_tool as A
import lang_nghe_db as K
import theo_doi as T

_VN = datetime.timezone(datetime.timedelta(hours=7))
BAY_GIO = datetime.datetime(2026, 10, 14, 9, 0, tzinfo=_VN)
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"], "tu_loai_tru": ["guitar"],
         "boi_canh": "HAPAS — thương hiệu túi xách Việt Nam", "thi_truong": "VN",
         "tran_usd_thang": 5.0, "dang_bat": True}


def _nguon(i, p, dd, loai="kol", so_bai=5):
    return {"id": i, "nen_tang": p, "dinh_danh": dd, "ten": dd, "link": "", "loai": loai,
            "so_bai_moi_lan": so_bai, "chu_ky_ngay": 1, "quet_cuoi": None}


class GiaKho:
    """Thay `lang_nghe_db` bằng bộ nhớ: đủ để kiểm luồng, không cần Postgres."""

    def __init__(self, du_an=None, nguon=(), da_tieu=0.0, dang_chay=None):
        self.du_an = {DU_AN["ma"]: dict(DU_AN)} if du_an is None else du_an
        self.nguon = list(nguon)
        self.da_tieu = da_tieu
        self.dang_chay = dang_chay
        self.bai: list[tuple] = []
        self.so: list[tuple] = []
        self.luot: dict[int, dict] = {}
        self.danh_dau: list[tuple] = []
        self.lam_moi: list[dict] = []
        self.hong_ghi = False

    def cai(self, mp):
        for ten in ("doc_du_an", "cac_du_an", "nguon_toi_han", "dem_nguon", "da_tieu_thang",
                    "luot_dang_chay", "mo_luot", "dong_luot", "danh_dau_nguon", "ghi_bai",
                    "bai_youtube_can_lam_moi", "cap_nhat_so_lieu", "du_an_dang_bat",
                    "nguon_cua_du_an", "ghi_de_xuat"):
            mp.setattr(K, ten, getattr(self, ten))
        self.de_xuat: list[tuple] = []
        return self

    def du_an_dang_bat(self):
        return [{"ma": k, "ten": v["ten"], "tu_khoa": v["tu_khoa"]}
                for k, v in self.du_an.items() if v["dang_bat"]]

    def nguon_cua_du_an(self, ma):
        return [{"id": n["id"], "nen_tang": n["nen_tang"], "dinh_danh": n["dinh_danh"]}
                for n in self.nguon]

    def ghi_de_xuat(self, ma, cac):
        self.de_xuat.append((ma, [dict(x) for x in cac]))
        return len(cac)

    def doc_du_an(self, ma):
        return self.du_an.get(ma)

    def cac_du_an(self):
        return [{"ma": k, "ten": v["ten"], "dang_bat": v["dang_bat"]} for k, v in self.du_an.items()]

    def nguon_toi_han(self, ma):
        return [dict(n) for n in self.nguon]

    def dem_nguon(self, ma):
        return {"dang_theo_doi": 3, "tam_dung": 1}

    def da_tieu_thang(self, ma):
        return self.da_tieu

    def luot_dang_chay(self, ma):
        return self.dang_chay

    def mo_luot(self, ma, kieu, ma_viec=None, job_id=None):
        i = len(self.luot) + 1
        self.luot[i] = {"du_an": ma, "kieu": kieu, "ma_viec": ma_viec, "job_id": job_id}
        return i

    def dong_luot(self, luot_id, **kw):
        self.luot.setdefault(luot_id, {}).update(kw)

    def danh_dau_nguon(self, ok, loi):
        self.danh_dau.append((sorted(ok), dict(loi)))

    def ghi_bai(self, ma, luot_id, kieu, rows):
        if self.hong_ghi:
            raise K.LoiKho("kho lắng nghe báo lỗi (ForeignKeyViolation: 23503)")
        self.bai.append((ma, luot_id, kieu, [dict(r) for r in rows]))
        return len(rows), 0

    def bai_youtube_can_lam_moi(self, ma, ngay=14, toi_da=200):
        return list(self.lam_moi)

    def cap_nhat_so_lieu(self, ma, luot_id, rows):
        self.so.append((ma, luot_id, [dict(r) for r in rows]))
        return len(rows)


class GiaViec:
    """Đủ giao diện `viec_nen.Viec` mà runner dùng (kể cả sổ dòng trên đĩa)."""

    def __init__(self, nen_tang, nguon_ids, con=3000.0):
        self.d = {"ma": "t10140900-abcde", "tham_so": {"du_an": "hapas", "nguon": nguon_ids},
                  "nen_tang": nen_tang, "kenh": {"job_id": "job-1"}}
        self.ma = self.d["ma"]
        self._khoa = threading.RLock()
        self.co_dung = threading.Event()
        self._con, self.huy, self.chot, self.so_luu = con, False, [], 0
        self.dia: dict[str, list] = {}

    def da_huy(self):
        return self.huy

    def con_giay(self):
        return self._con

    def han_mono(self, chua=0.0):
        return time.monotonic() + self._con - chua

    def cap_nhat_phan(self, ph, **kw):
        ph.update(kw)

    def luu(self):
        self.so_luu += 1

    def cac_phan(self):
        for p, nt in self.d["nen_tang"].items():
            for ph in nt.get("phan") or []:
                yield p, ph

    def run_ids(self):
        return [ph["run_id"] for _, ph in self.cac_phan() if ph.get("run_id")]

    def ghi_dong(self, p, rows, phan_id):
        self.dia.setdefault(p, []).extend((dict(d), dt) for d, dt in rows)

    def doc_dong(self, p):
        return [(dict(d), dt) for d, dt in self.dia.get(p, [])]

    def chot_chi_phi(self, q, p, r):
        self.chot.append((list(q), list(p), r))
        return {"usd": 0.0123}


@pytest.fixture
def mo(monkeypatch):
    """Mọi nền tảng bật (trần console 5 USD/lượt), có key YouTube, AI không phán gì."""
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 5.0, True))
    monkeypatch.setattr(A, "_youtube_co_key", lambda: True)
    monkeypatch.setattr(A, "_phan_xu_ai", lambda *a, **k: ({}, {"_sac_thai": {}, "_chu_de": {},
                                                                 "trang_thai": "đã chạy"}))
    import viec_nen
    monkeypatch.setattr(viec_nen, "tat_ca", list)
    return monkeypatch


def _tt(user, vid, text, ngay=None):
    """Một item thô của actor clockworks~tiktok-profile-scraper."""
    ngay = ngay or datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    return {"authorMeta": {"name": user, "nickName": user.upper(), "fans": 100},
            "createTimeISO": ngay.isoformat().replace("+00:00", "Z"), "playCount": 10,
            "diggCount": 2, "commentCount": 3, "shareCount": 1, "text": text,
            "webVideoUrl": f"https://www.tiktok.com/@{user}/video/{vid}", "hashtags": [],
            "musicMeta": {}}


class GiaApify:
    """`_run_actor` / `_doc_tiep_run` / `_tim_run_vua_tao_ex` giả; ghi lại mọi lượt."""

    def __init__(self, mp, items=None, usd=0.03):
        self.items, self.usd = items or [], usd
        self.gui: list[dict] = []
        self.doc_tiep: list[str] = []
        self.tim = (None, True)
        mp.setattr(A, "_run_actor", self.run_actor)
        mp.setattr(A, "_doc_tiep_run", self.doc_tiep_run)
        mp.setattr(A, "_tim_run_vua_tao_ex", lambda *a, **k: self.tim)

    def run_actor(self, actor, payload, limit, mem=None, deadline=None, min_charge=0, *,
                  tran_usd=None, mot_phan=False, nen_tang=None):
        self.gui.append({"actor": actor, "payload": payload, "limit": limit,
                         "tran_usd": tran_usd, "nen_tang": nen_tang, "mot_phan": mot_phan})
        fn = A._KHI_CO_RUN.get()
        if fn:
            fn({"id": f"r{len(self.gui)}"}, {})
        return list(self.items), {"run_id": f"r{len(self.gui)}", "ma": "OK", "usd": self.usd}

    def doc_tiep_run(self, run_id, limit, deadline=None, mot_phan=True, actor=""):
        self.doc_tiep.append(run_id)
        return list(self.items), {"run_id": run_id, "ma": "OK", "usd": self.usd}


# ───────────────────────────── tiện ích + ước tính ─────────────────────────────
def test_chuan_dinh_danh_va_khoa_bai():
    assert T._chuan_dinh_danh("tiktok", "@Me4Con.102/") == "me4con.102"
    assert T._chuan_dinh_danh("youtube", "UCabcdefghijklmnopqrstuv") == "UCabcdefghijklmnopqrstuv"
    assert (T._chuan_dinh_danh("facebook", "https://m.facebook.com/HapasOfficial/?ref=x")
            == "facebook.com/hapasofficial")
    assert T._khoa_bai("tiktok", "https://www.tiktok.com/@a/video/7551234567") == "tiktok:7551234567"
    assert T._khoa_bai("youtube", "https://www.youtube.com/watch?v=abcDEF12345") == "youtube:abcDEF12345"
    assert T._khoa_bai("instagram", "https://www.instagram.com/reel/C0dE-1/") == "instagram:C0dE-1"
    k1 = T._khoa_bai("facebook", "https://facebook.com/x")
    assert k1.startswith("facebook:h") and k1 == T._khoa_bai("facebook", "https://facebook.com/x")


def test_chia_phan_moi_nguon_dung_so_bai_cua_no():
    """Review 14/10: gộp theo số bài LỚN NHẤT làm nguồn 5 bài bị lấy 30 bài ngoài ước tính."""
    ds = [_nguon(1, "tiktok", "@a"), _nguon(2, "tiktok", "b"), _nguon(3, "tiktok", "c", so_bai=30),
          _nguon(4, "instagram", "d"), _nguon(5, "youtube", "@e"),
          _nguon(6, "facebook", "https://facebook.com/f", so_bai=3)]
    ph = T.chia_phan(ds)
    tt = {x["id"]: x for x in ph["tiktok"]}
    assert set(tt) == {"tiktok-5", "tiktok-30"}
    assert tt["tiktok-5"]["payload"]["profiles"] == ["a", "b"] and tt["tiktok-5"]["limit"] == 10
    assert tt["tiktok-5"]["payload"]["resultsPerPage"] == 5
    assert tt["tiktok-30"]["nguon"] == [3] and tt["tiktok-30"]["limit"] == 30
    assert ph["instagram"][0]["payload"] == {"usernames": ["d"]}
    assert ph["youtube"][0]["actor"] == "youtube" and ph["youtube"][0]["uoc_usd"] == 0
    assert ph["facebook"][0]["payload"]["resultsLimit"] == 3
    assert tt["tiktok-5"]["uoc_usd"] == pytest.approx(10 * 0.003 * 1.3, abs=1e-4)
    assert ph["instagram"][0]["uoc_usd"] == pytest.approx((0.0026 + 0.016) * 1.3, abs=1e-4)


def test_cat_theo_ngan_sach():
    ds = [_nguon(1, "tiktok", "a"), _nguon(2, "tiktok", "b"), _nguon(3, "youtube", "@c"),
          _nguon(4, "instagram", "d")]
    giu, bo = T._cat_theo_ngan_sach(ds, 0.02)
    # TikTok đầu (0,0195) vừa; thêm TikTok thứ hai thì phần 0,039 vượt; YouTube miễn phí luôn
    # giữ; Instagram có phí khởi động nên vượt.
    assert [n["id"] for n in giu] == [1, 3] and [n["id"] for n in bo] == [2, 4]


# ───────────────────────────── kế hoạch ─────────────────────────────
def test_ke_hoach_khong_co_du_an_liet_ke_du_an_co_san(mo):
    GiaKho().cai(mo)
    kh = T.ke_hoach("khongco")
    assert "Không có dự án 'khongco'" in kh["loi"] and "hapas" in kh["loi"]


def test_ke_hoach_du_an_tat_va_luot_dang_chay(mo):
    GiaKho(du_an={"hapas": dict(DU_AN, dang_bat=False)}).cai(mo)
    assert "đang tắt" in T.ke_hoach("hapas")["loi"]
    GiaKho(dang_chay={"id": 7, "ma_viec": "t1"}).cai(mo)
    assert "còn đang chạy" in T.ke_hoach("hapas")["loi"]


def test_ke_hoach_khong_nguon_toi_han_noi_ro_so_nguon(mo):
    GiaKho(nguon=[]).cai(mo)
    loi = T.ke_hoach("hapas")["loi"]
    assert "đang theo dõi 3" in loi and "tạm dừng 1" in loi


def test_ke_hoach_ton_trong_cong_tac_nen_tang_tren_console(mo):
    GiaKho(nguon=[_nguon(1, "tiktok", "a"), _nguon(2, "youtube", "@b")]).cai(mo)
    mo.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 5.0, p != "tiktok"))
    kh = T.ke_hoach("hapas")
    assert [n["id"] for n in kh["nguon"]] == [2]
    assert kh["bo_qua"][0][0]["id"] == 1 and "đã tắt TikTok" in kh["bo_qua"][0][1]


def test_ke_hoach_het_ngan_sach_thang(mo):
    GiaKho(nguon=[_nguon(1, "tiktok", "a")], da_tieu=5.0).cai(mo)
    loi = T.ke_hoach("hapas")["loi"]
    assert "hết ngân sách tháng" in loi and "5,00/5,00" in loi


def test_ke_hoach_kho_loi_noi_that(mo):
    def hong(ma):
        raise K.LoiKho("không nối được kho lắng nghe (OperationalError)")
    mo.setattr(K, "doc_du_an", hong)
    assert "Kho lắng nghe chưa dùng được" in T.ke_hoach("hapas")["loi"]


# ───────────────────────────── lệnh ─────────────────────────────
def test_lenh_theodoi_tron_huong_dan(mo):
    GiaKho().cai(mo)
    s = T.lenh_theodoi("")
    assert "/theodoi <mã dự án>" in s and "hapas (HAPAS)" in s and "Lịch chạy" in s


def test_lenh_theodoi_tao_viec_nen_dung_cau_truc(mo):
    import quet_lon
    import viec_nen
    GiaKho(nguon=[_nguon(1, "tiktok", "a"), _nguon(2, "youtube", "@b")], da_tieu=1.0).cai(mo)
    mo.setattr(quet_lon, "tran_usd_nen", lambda: 20.0)
    mo.setattr(quet_lon, "ngan_sach", lambda tran: (8.0, {"con_lai": 9.0}, ""))
    goi = {}

    def tao(loai, tham_so, nen_tang, uoc, ngan_sach, ghi_chu=None, **kw):
        goi.update(loai=loai, tham_so=tham_so, nen_tang=nen_tang, uoc=uoc, ns=ngan_sach, kw=kw)
        return {"dang_chay_nen": True, "ma_viec": "t10140900-x"}
    mo.setattr(viec_nen, "tao_viec", tao)
    s = T.lenh_theodoi("HAPAS")
    assert goi["loai"] == "theo_doi" and goi["tham_so"]["du_an"] == "hapas"
    assert goi["tham_so"]["nguon"] == [1, 2] and re.fullmatch(r"\d{4}-\d\d-\d\d",
                                                                goi["tham_so"]["ngay"])
    ph = goi["nen_tang"]["tiktok"]["phan"][0]
    assert ph["nguon"] == [1] and ph["payload"]["profiles"] == ["a"] and ph["trang_thai"] == "cho"
    assert goi["nen_tang"]["youtube"]["phan"][0]["actor"] == "youtube"
    assert 0 < goi["ns"] <= 4.0                     # ≤ phần còn lại của tháng (5 − 1)
    assert goi["kw"]["con_lai_thang"] == 9.0
    assert "t10140900-x" in s and "2 nguồn" in s and "còn 4,00/5,00 USD" in s


def test_lenh_theodoi_khong_vuot_ngan_sach_apify(mo):
    import quet_lon
    GiaKho(nguon=[_nguon(1, "tiktok", "a", so_bai=30)]).cai(mo)
    mo.setattr(quet_lon, "tran_usd_nen", lambda: 20.0)
    mo.setattr(quet_lon, "ngan_sach", lambda tran: (0.01, None, ""))
    assert T.lenh_theodoi("hapas").startswith("Chưa chạy")


def test_lenh_theodoi_tu_choi_khi_con_viec_cung_du_an(mo):
    """Review 14/10: lịch + gõ tay cùng lúc thì việc thứ hai bị từ chối, không quét trùng."""
    import viec_nen
    GiaKho(nguon=[_nguon(1, "tiktok", "a")]).cai(mo)
    mo.setattr(viec_nen, "tat_ca", lambda: [{"ma": "t1", "loai": "theo_doi",
                                             "tham_so": {"du_an": "hapas"},
                                             "trang_thai": "xep_hang"}])
    s = T.lenh_theodoi("hapas")
    assert "chưa xong (mã t1)" in s


# ───────────────────────────── lọc + nhãn ─────────────────────────────
def _dong(link, text, ngay, kenh="KOL A", views=100, p="tiktok"):
    return ({"platform": p, "kenh": kenh, "username": "kola", "views": views,
             "likes": 5, "comments": 2, "shares": 1, "hashtags": "", "text": text,
             "link": link}, ngay)


def test_chon_bai_luat_giu_bo(mo):
    moi, cu = BAY_GIO - datetime.timedelta(days=2), BAY_GIO - datetime.timedelta(days=40)
    nguon = {1: _nguon(1, "tiktok", "kola"), 2: _nguon(2, "tiktok", "hapas", loai="kenh_nha")}
    theo_nguon = {
        1: [_dong("https://t.com/@a/video/1", "review túi Hapas đẹp", moi),
            _dong("https://t.com/@a/video/2", "đi chơi cuối tuần", moi),
            _dong("https://t.com/@a/video/3", "hapas cũ", cu),
            _dong("https://t.com/@a/video/4", "hapas guitar solo", moi),
            _dong("https://t.com/@a/video/1", "review túi Hapas đẹp", moi),   # trùng
            _dong("https://t.com/@a/video/5", "không ngày", None)],
        2: [_dong("https://t.com/@h/video/9", "BST thu đông", moi, kenh="Nhà")],
    }
    rows, tk = T.chon_bai(DU_AN, theo_nguon, nguon, time.monotonic() + 60, BAY_GIO)
    assert [r["khoa"] for r in rows] == ["tiktok:1", "tiktok:9"]
    assert tk == {"lay_duoc": 6, "qua_cu": 2, "khong_nhac": 1, "loai_tru": 1, "ai_loai": 0,
                  "giu": 2, "ai": "đã chạy"}
    assert rows[0]["khop_tu_khoa"] and not rows[1]["khop_tu_khoa"]
    assert rows[1]["ly_do_giu"] == "kenh_nha" and rows[0]["xem"] == 100


def test_chon_bai_ai_loai_kol_nhung_khong_loai_kenh_nha(mo):
    moi = BAY_GIO - datetime.timedelta(days=1)
    nguon = {1: _nguon(1, "tiktok", "kola"), 2: _nguon(2, "tiktok", "hapas", loai="kenh_nha")}
    theo_nguon = {1: [_dong("https://t.com/@a/video/1", "hapas ashen metal", moi)],
                  2: [_dong("https://t.com/@h/video/2", "hapas sale", moi)]}
    mo.setattr(A, "_phan_xu_ai", lambda rows, *a, **k: (
        {0: (False, "trung_ten", "ban nhạc"), 1: (False, "lac_de", "")},
        {"_sac_thai": {1: "Tích cực"}, "_chu_de": {1: "Chiến dịch & quảng cáo"},
         "trang_thai": "đã chạy"}))
    rows, tk = T.chon_bai(DU_AN, theo_nguon, nguon, time.monotonic() + 60, BAY_GIO)
    assert [r["khoa"] for r in rows] == ["tiktok:2"] and tk["ai_loai"] == 1
    assert rows[0]["ly_do_giu"] == "kenh_nha"               # không ghi mã loại vào bài giữ
    assert rows[0]["sac_thai"] == "Tích cực" and rows[0]["chu_de"] == "Chiến dịch & quảng cáo"


def test_chon_bai_ai_khong_chac_ve_luat(mo):
    """`khong_ro` = AI không chắc → giữ theo luật như social_listen, không tính là AI loại."""
    moi = BAY_GIO - datetime.timedelta(days=1)
    mo.setattr(A, "_phan_xu_ai", lambda rows, *a, **k: (
        {0: (False, "khong_ro", "")}, {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"}))
    rows, tk = T.chon_bai(DU_AN, {1: [_dong("https://t.com/@a/video/1", "hapas?", moi)]},
                          {1: _nguon(1, "tiktok", "kola")}, time.monotonic() + 60, BAY_GIO)
    assert len(rows) == 1 and rows[0]["ly_do_giu"] == "khop_tu_khoa" and tk["ai_loai"] == 0


# ───────────────────────────── ghép nguồn ─────────────────────────────
def test_ghep_nguon_theo_ten_cat_dung_so_bai_va_bao_loi():
    import account_tool
    raw = [_tt("me4con.102", i, "hapas") for i in range(9)]
    ket = account_tool._doc_tiktok(raw)
    ds = [_nguon(1, "tiktok", "@Me4Con.102", so_bai=7), _nguon(2, "tiktok", "khongco")]
    ra, loi = T.ghep_nguon("tiktok", ket, ds)
    assert len(ra[1]) == 7 and ra[1][0][0]["comments"] == 3 and ra[1][0][0]["_goc_id"] is None
    assert ra[2] == [] and 2 in loi and 1 not in loi


def test_ghep_nguon_facebook_theo_url_dau_vao():
    ngay = BAY_GIO - datetime.timedelta(days=1)
    ket = {"hapas official": {"ho_so": {"ten": "Hapas Official", "tai_khoan": "Hapas"},
                              "bai": [{"ngay": ngay, "noi_dung": "x", "hashtag": [],
                                       "link": "https://www.facebook.com/p/posts/1",
                                       "_goc": {"inputUrl": "https://www.facebook.com/HapasOfficial/"}}],
                              "ghi_chu": ""}}
    ds = [_nguon(1, "facebook", "https://facebook.com/hapasofficial"),
          _nguon(2, "facebook", "https://facebook.com/khac")]
    ra, loi = T.ghep_nguon("facebook", ket, ds)
    assert len(ra[1]) == 1 and ra[2] == [] and 2 in loi


def test_lay_youtube_theo_handle_va_id(monkeypatch):
    goi = []

    def get(res, params, timeout=None):
        goi.append((res, dict(params)))
        if res == "channels" and params.get("forHandle") == "@hapas":
            return {"items": [{"id": "UC_hapas_000000000000000", "snippet": {"title": "HAPAS",
                               "country": "VN"}, "statistics": {"subscriberCount": "1200"},
                               "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
        if res == "channels" and params.get("forHandle"):
            return {"items": []}
        if res == "channels":
            return {"items": [{"id": "UCabcdefghijklmnopqrstuv", "snippet": {"title": "VGbrands"},
                               "statistics": {}, "contentDetails": {
                                   "relatedPlaylists": {"uploads": "UU2"}}}]}
        if res == "playlistItems":
            vid = "aaaaaaaaaaa" if params["playlistId"] == "UU1" else "bbbbbbbbbbb"
            return {"items": [{"contentDetails": {"videoId": vid}}]}
        if res == "videos":
            return {"items": [{"id": i, "snippet": {"title": "HAPAS thu đông", "description": "",
                                                    "publishedAt": "2026-10-12T03:00:00Z"},
                               "statistics": {"viewCount": "50", "commentCount": "3"}}
                              for i in params["id"].split(",")]}
        raise AssertionError(res)
    monkeypatch.setattr(A, "_youtube_get", get)
    ds = [_nguon(1, "youtube", "@hapas"), _nguon(2, "youtube", "UCabcdefghijklmnopqrstuv"),
          _nguon(3, "youtube", "khongco")]
    ra, loi = T._lay_youtube(ds)
    assert ra[1][0][0]["link"].endswith("aaaaaaaaaaa") and ra[1][0][0]["followers"] == 1200
    assert ra[1][0][0]["_quoc_gia"] == "VN" and ra[1][0][1].tzinfo is not None
    assert ra[2][0][0]["kenh"] == "VGbrands" and ra[2][0][0]["comments"] == 3
    assert 3 in loi and "không tìm thấy kênh" in loi[3]
    assert not any(r == "search" for r, _ in goi)      # không đốt quota search (100 đơn vị)


# ───────────────────────────── chạy nền ─────────────────────────────
def _viec(nguon):
    phan = T.chia_phan(nguon)
    return GiaViec({p: {"phan": cac} for p, cac in phan.items()}, [n["id"] for n in nguon])


def test_chay_viec_ghi_kho_tran_usd_va_bao_ket_qua(mo):
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "kola"), _nguon(2, "youtube", "@hapas"),
                        _nguon(3, "tiktok", "matten")], da_tieu=4.85).cai(mo)
    ap = GiaApify(mo, [_tt("kola", 11, "túi hapas xinh"), _tt("kola", 12, "ăn sáng")])
    ngay = datetime.datetime.now(_VN) - datetime.timedelta(days=1)
    mo.setattr(T, "_lay_youtube", lambda ds: ({2: [_dong("https://www.youtube.com/watch?v=yyyyyyyyyyy",
                                                         "HAPAS review", ngay, p="youtube")]}, {}))
    v = _viec(kho.nguon)
    trang_thai, van_ban = T.chay_viec(v)
    (gui,) = ap.gui
    # Trần lượt actor = min(console 5, tháng còn 0,15, max(0,1; ước tính 0,039 × 1,5)) = 0,1 —
    # Apify dừng ở trần này nên lượt không thể tiêu quá phần tháng còn lại.
    con_thang = 5.0 - 4.85
    assert gui["tran_usd"] == 0.1 <= con_thang and gui["nen_tang"] == "tiktok" and gui["mot_phan"]
    assert gui["payload"]["profiles"] == ["kola", "matten"] and gui["limit"] == 10
    assert trang_thai == "xong_mot_phan"                  # nguồn 3 không có bài
    (_, luot, kieu, rows), = kho.bai
    assert kieu == "theo_doi" and sorted(r["khoa"] for r in rows) == ["tiktok:11",
                                                                    "youtube:yyyyyyyyyyy"]
    ok, loi = kho.danh_dau[0]
    assert ok == [1, 2] and set(loi) == {3}
    assert kho.luot[luot]["trang_thai"] == "mot_phan" and kho.luot[luot]["bai_moi"] == 2
    assert kho.luot[luot]["chi_phi_usd"] == pytest.approx(0.0123)
    assert v.d["luot_id"] == luot and v.chot[0][1] == ["tiktok"]
    assert v.d["nen_tang"]["tiktok"]["phan"][0]["run_id"] == "r1"
    assert "giữ 2 bài" in van_ban and "0,01 USD" in van_ban and "1 nguồn lỗi" in van_ban
    # Cờ Apify chỉ sống trong bản sao ngữ cảnh của runner.
    assert A._NEN.get() is False and A._NEN_TANG.get() is None


def test_chay_viec_het_ngan_sach_thang_khong_goi_actor(mo):
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "kola")], da_tieu=4.98).cai(mo)
    ap = GiaApify(mo, [_tt("kola", 1, "hapas")])
    v = _viec(kho.nguon)
    _, van_ban = T.chay_viec(v)
    assert ap.gui == [] and "hết ngân sách tháng" in van_ban
    assert v.d["nen_tang"]["tiktok"]["phan"][0]["ma"] == "NGAN_SACH" and v.chot == []


def test_khoi_dong_lai_phan_da_xong_doc_tu_dia_khong_quet_lai(mo):
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "kola")]).cai(mo)
    ap = GiaApify(mo, [])
    v = _viec(kho.nguon)
    ph = v.d["nen_tang"]["tiktok"]["phan"][0]
    ph.update(trang_thai="xong", run_id="r9")
    ngay = datetime.datetime.now(_VN) - datetime.timedelta(days=1)
    d, _ = _dong("https://www.tiktok.com/@kola/video/77", "hapas", ngay)
    v.dia["tiktok"] = [({**d, "_nguon_id": 1}, ngay)]
    v.d["luot_id"] = 42
    T.chay_viec(v)
    assert ap.gui == [] and ap.doc_tiep == []
    assert [r["khoa"] for r in kho.bai[0][3]] == ["tiktok:77"] and kho.danh_dau[0][0] == [1]
    assert kho.luot[42]["chi_phi_usd"] == pytest.approx(0.0123) and len(kho.luot) == 1


def test_khoi_dong_lai_co_run_id_thi_doc_tiep_khong_gui_lai(mo):
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "kola")]).cai(mo)
    ap = GiaApify(mo, [_tt("kola", 5, "hapas")])
    v = _viec(kho.nguon)
    v.d["nen_tang"]["tiktok"]["phan"][0].update(trang_thai="dang_chay", run_id="r7",
                                                tran_usd=0.1)
    T.chay_viec(v)
    assert ap.gui == [] and ap.doc_tiep == ["r7"]
    assert [r["khoa"] for r in kho.bai[0][3]] == ["tiktok:5"]


def test_khoi_dong_lai_dang_gui_khong_kiem_duoc_thi_khong_gui_lai(mo):
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "kola")]).cai(mo)
    ap = GiaApify(mo, [_tt("kola", 5, "hapas")])
    ap.tim = (None, False)
    v = _viec(kho.nguon)
    ph = v.d["nen_tang"]["tiktok"]["phan"][0]
    ph.update(trang_thai="dang_gui", tran_usd=0.1,
              moc_gui=datetime.datetime.now(_VN).isoformat())
    T.chay_viec(v)
    assert ap.gui == [] and ph["ma"] == "KHONG_KIEM_DUOC" and ph["usd_so"] == 0.1


def test_loi_kho_sau_khi_tra_tien_van_ghi_chi_phi_vao_luot(mo):
    """Review 14/10: nguồn bị xoá giữa lượt / kho hỏng lúc ghi — tiền đã tiêu vẫn vào lượt."""
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "kola")]).cai(mo)
    kho.hong_ghi = True
    GiaApify(mo, [_tt("kola", 5, "hapas")])
    v = _viec(kho.nguon)
    trang_thai, van_ban = T.chay_viec(v)
    luot = v.d["luot_id"]
    assert trang_thai == "loi" and "ForeignKeyViolation" in van_ban
    assert kho.luot[luot]["trang_thai"] == "loi"
    assert kho.luot[luot]["chi_phi_usd"] == pytest.approx(0.0123)


def test_lam_moi_youtube_chi_cap_nhat_so(mo):
    """Review 14/10: bản cũ đi qua upsert đầy đủ, INSERT thiếu cột NOT NULL, hỏng lặng lẽ."""
    kho = GiaKho(nguon=[]).cai(mo)
    kho.lam_moi = [{"khoa": "youtube:abcDEF12345", "link": "x"}]
    mo.setattr(A, "_youtube_get", lambda res, params, timeout=None: {"items": [{
        "id": "abcDEF12345", "snippet": {"title": "t", "publishedAt": "2026-10-10T00:00:00Z"},
        "statistics": {"viewCount": "900", "likeCount": "7", "commentCount": "12"}}]})
    assert T._lam_moi_youtube("hapas", 3) == 1
    (_, luot, rows), = kho.so
    assert luot == 3 and rows == [{"khoa": "youtube:abcDEF12345", "xem": 900, "thich": 7,
                                   "binh_luan": 12, "chia_se": None}]


# ───────────────────────────── tìm theo từ khoá → kho ─────────────────────────────
def _hit(p, user, i, binh_luan=0, sac="chưa phân loại", **kw):
    ngay = BAY_GIO - datetime.timedelta(days=1)
    d = {"platform": p, "kenh": user.upper(), "username": user, "followers": 10, "views": 5,
         "likes": 1, "comments": binh_luan, "shares": 0, "hashtags": "", "text": "hapas",
         "link": f"https://www.tiktok.com/@{user}/video/{i}", "_khop": True,
         "_sac_thai": sac, "_chu_de": "chưa phân loại", "__goc": {"id": str(i)}, **kw}
    return d, ngay


def test_du_an_khop_theo_tu_khoa_bo_dau():
    cac = [{"ma": "hapas", "tu_khoa": ["Hapas"]}, {"ma": "edoris", "tu_khoa": ["edoris"]}]
    assert [x["ma"] for x in T._du_an_khop(["túi HAPAS đẹp"], cac)] == ["hapas"]
    assert T._du_an_khop(["matemade"], cac) == []


def test_ban_sao_bo_nhan_chua_phan_loai_va_lay_id_kenh_youtube():
    yt = ({"platform": "youtube", "kenh": "VG", "username": "", "link": "https://www.youtube.com/watch?v=abcDEF12345",
           "_sac_thai": "Tích cực", "_chu_de": "chưa phân loại",
           "__goc": {"search": {"snippet": {"channelId": "UCabcdefghijklmnopqrstuv"}}}},
          BAY_GIO)
    ban = T._ban_sao_tu_khoa([yt, _hit("tiktok", "a", 1), ({"link": "x"}, None)])
    assert len(ban) == 2
    assert ban[0][0]["_kenh_id"] == "UCabcdefghijklmnopqrstuv" and ban[0][0]["_chu_de"] is None
    assert ban[0][0]["_sac_thai"] == "Tích cực" and ban[1][0]["_sac_thai"] is None
    assert "__goc" not in ban[1][0] and ban[1][0]["_goc_id"] == "1"


def test_de_xuat_nguong_bo_nguon_da_co_va_xep_theo_thao_luan():
    ban = T._ban_sao_tu_khoa([_hit("tiktok", "quynhphaken", 1, binh_luan=6642),
                              _hit("tiktok", "me4con", 2), _hit("tiktok", "me4con", 3),
                              _hit("tiktok", "le", 4, binh_luan=3),
                              _hit("tiktok", "dacodanh", 5), _hit("tiktok", "dacodanh", 6),
                              _hit("threads", "th", 7, binh_luan=900)])
    dx = T._de_xuat_tu(ban, {("tiktok", "dacodanh")}, ["hapas"])
    assert [x["dinh_danh"] for x in dx] == ["quynhphaken", "me4con"]   # "le" dưới ngưỡng
    assert dx[0]["thao_luan"] == 6643 and dx[0]["link"] == "https://www.tiktok.com/@quynhphaken"
    assert "1 bài, 6643 thảo luận" in dx[0]["ly_do"]


def test_luu_tu_khoa_ghi_bai_gan_nguon_da_co_va_de_xuat(mo):
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "@Me4Con")]).cai(mo)
    ban = T._ban_sao_tu_khoa([_hit("tiktok", "me4con", 2), _hit("tiktok", "moi", 3, binh_luan=80),
                              _hit("tiktok", "moi", 3, binh_luan=80)])     # trùng link
    kq = T.luu_tu_khoa(["hapas"], ban)
    (ma, luot, kieu, rows), = kho.bai
    assert ma == "hapas" and kq == {"hapas": (2, 0, 1)} and kieu == "tu_khoa" and kho.luot[luot]["kieu"] == "tu_khoa"
    assert {r["khoa"]: r["nguon_id"] for r in rows} == {"tiktok:2": 1, "tiktok:3": None}
    assert [x["dinh_danh"] for x in kho.de_xuat[0][1]] == ["moi"]
    assert kho.luot[luot]["trang_thai"] == "xong" and "không tính vào trần" in kho.luot[luot]["ghi_chu"]
    assert T.luu_tu_khoa(["edoris"], ban) == {}                    # không dự án nào khớp


def test_luu_tu_khoa_nen_tat_khi_chua_cai_kho_hoac_bi_tat(monkeypatch):
    import importlib.util
    chay = []
    monkeypatch.setattr(T, "luu_tu_khoa", lambda *a: chay.append(a))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    T.luu_tu_khoa_nen(["hapas"], [_hit("tiktok", "a", 1)])
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    monkeypatch.setenv("LANG_NGHE_GHI_TU_KHOA", "0")
    T.luu_tu_khoa_nen(["hapas"], [_hit("tiktok", "a", 1)])
    time.sleep(0.05)
    assert chay == []


# ───────────────────────────── nối vào Mark ─────────────────────────────
def test_lenh_cung_theodoi_theo_cong_tac_soi_tai_khoan(monkeypatch):
    import lenh_cung
    hoi = []
    monkeypatch.setattr(lenh_cung.lsr_policy, "decide", lambda t, a=None: hoi.append(t) or
                        lenh_cung.lsr_policy.PolicyDecision(False, "chủ agent đã tắt"))
    r = lenh_cung.xu_ly("/theodoi hapas")
    assert r.sai and "chủ agent đã tắt" in r.tra_loi_thang and hoi == ["soi_tai_khoan"]
    monkeypatch.setattr(lenh_cung.lsr_policy, "decide",
                        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(True, ""))
    monkeypatch.setattr(T, "lenh_theodoi", lambda s: f"đã nhận {s}")
    r = lenh_cung.xu_ly("/theodoi hapas")
    assert r.tra_loi_thang == "đã nhận hapas" and not r.sai
    assert "/theodoi" in lenh_cung.xu_ly("/help").tra_loi_thang


def test_viec_nen_ma_va_runner_theo_doi():
    import viec_nen
    assert viec_nen.ma_moi("theo_doi").startswith("t")
    assert viec_nen.ma_moi("social_listen").startswith("q")
    assert viec_nen.ma_moi("social_deep_dive").startswith("b")
    assert viec_nen._runner("theo_doi") is T.chay_viec


def test_lich_theodoi_kiem_cu_phap_khi_dat():
    import scheduler
    assert scheduler._kiem_lenh_tiendo("/theodoi hapas", "run") == ""
    assert "mode=run" in scheduler._kiem_lenh_tiendo("/theodoi hapas", "send")
    assert "mã dự án" in scheduler._kiem_lenh_tiendo("/theodoi", "run")
    assert "mã dự án" in scheduler._kiem_lenh_tiendo("/theodoi Hapas Official", "run")


# ───────────────────────────── kho ─────────────────────────────
def test_kho_loi_ket_noi_khong_lo_dsn(monkeypatch):
    """Lỗi kết nối THẬT của psycopg (sai DSN) — thông báo chỉ có tên loại lỗi, không có DSN."""
    pytest.importorskip("psycopg")
    monkeypatch.setenv("LANG_NGHE_DSN",
                       "host=127.0.0.1 port=1 dbname=x user=u password=bi-mat-khong-duoc-lo")
    with pytest.raises(K.LoiKho) as e:
        K.doc_du_an("hapas")
    assert "bi-mat" not in str(e.value) and "OperationalError" in str(e.value)


def test_kho_thieu_psycopg_bao_ro(monkeypatch):
    import builtins
    that = builtins.__import__

    def gia(name, *a, **k):
        if name.startswith("psycopg"):
            raise ImportError(name)
        return that(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", gia)
    with pytest.raises(K.LoiKho) as e:
        K.doc_du_an("hapas")
    assert "psycopg" in str(e.value)


_NHAN_BI = ("[Lớp]", "[Mục đích]", "[Grain]", "[Khoá]", "[Nguồn]", "[Phạm vi]", "[Đã xử lý]",
            "[Refresh]", "[Dùng khi]", "[Không dùng khi]", "[Lưu ý]")


def test_kho_theo_quy_chuan_mo_ta_bi():
    """Chủ dự án 14/10/2026: DB mới theo rule BI (task t280613) — mọi bảng có mô tả 11 nhãn
    đúng thứ tự, mỗi nhãn một dòng; mọi cột có mô tả; [Không dùng khi] chỉ bảng thay thế."""
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    bang = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", sql, re.DOTALL)
    assert len(bang) == 10
    for ten, khoi in bang:
        m = re.search(rf"COMMENT ON TABLE {ten} IS \$\$(.*?)\$\$;", sql, re.DOTALL)
        assert m, f"{ten}: thiếu mô tả bảng"
        dong = m.group(1).split("\n")
        assert [d.split("]", 1)[0] + "]" for d in dong] == list(_NHAN_BI), ten
        assert all(len(d.split("]", 1)[1].strip()) > 2 for d in dong), ten
        assert "dùng" in dong[9], ten
        cot = re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE)
        cot = [c for c in cot if c not in ("primary", "unique", "foreign")]
        thieu = [c for c in cot if not re.search(rf"COMMENT ON COLUMN {ten}\.{c} IS '.{{10,}}';",
                                                 sql)]
        assert not thieu, f"{ten}: cột thiếu mô tả {thieu}"


def test_cot_ghi_bai_khop_schema():
    """Cột `ghi_bai` ghi phải có trong bảng `bai` của schema.sql (lệch thì lỗi chỉ lộ trên VPS)."""
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    khoi = re.search(r"CREATE TABLE IF NOT EXISTS bai \((.*?)\n\);", sql, re.DOTALL).group(1)
    cot = set(re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE))
    assert set(K._COT_BAI) | {"du_an", "kieu_quet", "luot_dau", "luot_cuoi"} <= cot
    # Quyền: Mark không được sửa dự án hay thêm nguồn.
    assert re.search(r"GRANT SELECT ON du_an, nguon TO mark;", sql)
    assert not re.search(r"GRANT[^;]*(INSERT|DELETE)[^;]*ON du_an[^;]*TO mark", sql)


# ───────────────────────────── bình luận (đợt 2b, 15/10/2026) ─────────────────────────────
def _bai_bl(vid, so_bl=10, tk="hapas.official", p="tiktok"):
    return {"khoa": f"{p}:{vid}", "nen_tang": p, "link": f"https://www.tiktok.com/@{tk}/video/{vid}",
            "tai_khoan": tk, "tac_gia": tk.upper(), "binh_luan": so_bl, "bl_lay_luc": None}


def _bl_tt(cid, vid, user, text, likes=0, tra_loi_cho=None, tk="hapas.official"):
    x = {"cid": cid, "uniqueId": user, "text": text, "diggCount": likes,
         "createTimeISO": "2026-10-13T02:00:00.000Z", "replyCommentTotal": 0,
         "videoWebUrl": f"https://www.tiktok.com/@{tk}/video/{vid}"}
    if tra_loi_cho:
        x["repliesToId"] = tra_loi_cho
    return x


def _lay_bl(*a):
    """Chạy trong BẢN SAO ngữ cảnh như runner thật — cờ Apify (_NEN_TANG…) không rò sang test khác."""
    import contextvars
    return contextvars.copy_context().run(T._lay_binh_luan, *a)


class GiaKhoBl:
    def __init__(self, mp, bai):
        self.bai, self.hoi, self.ghi = bai, [], []
        mp.setattr(K, "bai_can_lay_binh_luan", self.can)
        mp.setattr(K, "ghi_binh_luan", self.ghi_bl)

    def can(self, ma, nen_tang, toi_da):
        self.hoi.append((ma, list(nen_tang), toi_da))
        return [b for b in self.bai if b["nen_tang"] in nen_tang][:toi_da]

    def ghi_bl(self, ma, luot, rows, da_lay):
        self.ghi.append((ma, luot, [dict(r) for r in rows], dict(da_lay)))
        return len(rows), 0


@pytest.fixture
def nhan_gia(monkeypatch):
    import phan_loai
    goi = []

    def gan(rows, han, tt=None, song_song=None):
        goi.append([r["text"] for r in rows])
        if tt is not None:
            tt["trang_thai"] = "đã chạy"
        return [("Tích cực", "Sản phẩm/chất lượng")] * len(rows)
    monkeypatch.setattr(phan_loai, "phan_loai_binh_luan", gan)
    return goi


def test_binh_luan_tiktok_ghi_kho_nhan_va_tach_thuong_hieu(mo, nhan_gia):
    kho = GiaKhoBl(mo, [_bai_bl("111", 30), _bai_bl("222", 5)])
    ap = GiaApify(mo, items=[
        _bl_tt("c1", "111", "khach1", "túi đẹp quá", likes=3),
        _bl_tt("c2", "111", "hapas.official", "cảm ơn bạn ạ", tra_loi_cho="c1"),
        _bl_tt("c3", "222", "khach2", "giá bao nhiêu shop"),
        _bl_tt("c3", "222", "khach2", "giá bao nhiêu shop")], usd=0.01)
    v = GiaViec({}, [])
    du_an = dict(DU_AN, bl_bat=True, bl_so_bai=10, bl_moi_bai=20)
    tk = _lay_bl(v, du_an, 7, 5.0, time.monotonic() + 300)
    assert kho.hoi == [("hapas", ["youtube", "tiktok", "instagram", "facebook"], 10)]
    g = ap.gui[0]
    assert g["actor"] == "clockworks~tiktok-comments-scraper" and g["nen_tang"] == "tiktok"
    assert g["payload"]["postURLs"] == [b["link"] for b in kho.bai]
    assert g["payload"]["commentsPerPost"] == 20 and g["limit"] == 40
    assert g["tran_usd"] == round(max(0.1, T.uoc_binh_luan(2, 20, "tiktok") * 1.5), 2)
    ma, luot, rows, da_lay = kho.ghi[0]
    assert ma == "hapas" and luot == 7
    theo = {r["ma"]: r for r in rows}
    assert set(theo) == {"c1", "c2", "c3"}                  # khử trùng theo mã bình luận
    assert theo["c1"]["khoa_bai"] == "tiktok:111" and theo["c3"]["khoa_bai"] == "tiktok:222"
    assert theo["c1"]["sac_thai"] == "Tích cực" and theo["c1"]["chu_de"] == "Sản phẩm/chất lượng"
    # trả lời của chính chủ video: giữ, đánh dấu thương hiệu, KHÔNG đưa đi gán nhãn
    assert theo["c2"]["cua_thuong_hieu"] and theo["c2"]["la_tra_loi"] and theo["c2"]["sac_thai"] is None
    assert nhan_gia == [["túi đẹp quá", "giá bao nhiêu shop"]]
    assert theo["c1"]["dang_luc"] == datetime.datetime(2026, 10, 13, 9, 0, tzinfo=_VN)
    assert da_lay == {"tiktok:111": (2, 30), "tiktok:222": (1, 5)}
    ph = v.d["nen_tang"]["binh_luan"]["phan"][0]
    assert ph["run_id"] == "r1" and ph["trang_thai"] == "xong"     # run id vào sổ → chốt chi phí
    assert tk["lay"] == 3 and tk["nha"] == 1 and tk["usd"] > 0
    assert "đọc 3 bình luận của 2 bài" in T._cau_bl(tk)[0]


def test_binh_luan_facebook_tran_con_duoi_muc_actor_doi_thi_khong_chay(mo, nhan_gia):
    """Actor bình luận Facebook đòi maxTotalChargeUsd ≥ 0,5: tháng còn ít hơn thì bỏ, nói rõ."""
    GiaKhoBl(mo, [dict(_bai_bl("9", 40), nen_tang="facebook", khoa="facebook:9",
                       link="https://www.facebook.com/hapas/posts/9")])
    ap = GiaApify(mo)
    v = GiaViec({}, [])
    tk = _lay_bl(v, dict(DU_AN, bl_so_bai=5, bl_moi_bai=20), 1, 0.3,
                          time.monotonic() + 300)
    assert ap.gui == []
    assert any("bỏ qua" in x and "Facebook" in x for x in tk["ghi_chu"])
    assert v.d["nen_tang"]["binh_luan"]["phan"][0]["ma"] == "NGAN_SACH"


def test_binh_luan_khoi_dong_lai_doc_tiep_run_khong_gui_lai(mo, nhan_gia):
    kho = GiaKhoBl(mo, [_bai_bl("111", 30)])
    ap = GiaApify(mo, items=[_bl_tt("c1", "111", "khach1", "đẹp")])
    v = GiaViec({}, [])
    ph = T._tao_phan_bl(v, "tiktok", kho.bai, 20)
    ph.update(trang_thai="dang_chay", run_id="r-cu", tran_usd=0.2)
    _lay_bl(v, dict(DU_AN, bl_so_bai=10, bl_moi_bai=20), 1, 5.0, time.monotonic() + 300)
    assert ap.gui == [] and ap.doc_tiep == ["r-cu"]
    assert kho.hoi == []                       # phần đã lập từ trước: không chọn bài lại
    assert [r["ma"] for r in kho.ghi[0][2]] == ["c1"]


def test_binh_luan_tat_hoac_0_bai_thi_khong_lam_gi(mo):
    kho = GiaKhoBl(mo, [_bai_bl("1")])
    for du_an in (dict(DU_AN, bl_bat=False, bl_so_bai=10), dict(DU_AN, bl_bat=True, bl_so_bai=0)):
        tk = _lay_bl(GiaViec({}, []), du_an, 1, 5.0, time.monotonic() + 300)
        assert tk["bai"] == 0
    assert kho.hoi == []


def test_gia_binh_luan_khop_dashboard():
    from dashboard import chi_phi as CP
    assert CP.BL_GIA == T._BL_GIA and CP.BL_KHOI_DONG == T._BL_KHOI_DONG
    assert CP.uoc_binh_luan_luot(10, 20) == T.uoc_binh_luan(10, 20)


def test_kho_binh_luan_quyen_va_cot():
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    assert "GRANT SELECT, INSERT, UPDATE ON bai, chi_so_ngay, luot_quet, binh_luan TO mark;" in sql
    for c in ("bl_bat", "bl_so_bai", "bl_moi_bai"):
        assert f"ALTER TABLE du_an ADD COLUMN IF NOT EXISTS {c} " in sql
    for c in ("bl_lay_luc", "bl_da_lay", "bl_lay_khi_co"):
        assert f"ALTER TABLE bai ADD COLUMN IF NOT EXISTS {c} " in sql
    khoi = re.search(r"CREATE TABLE IF NOT EXISTS binh_luan \((.*?)\n\);", sql, re.DOTALL).group(1)
    cot = set(re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE))
    assert set(K._COT_BL) | {"du_an", "khoa_bai", "luot_id"} <= cot


def test_binh_luan_khong_vuot_ngan_sach_cua_viec(mo, nhan_gia):
    """Review 15/10: bình luận kẹp theo ngân sách việc đã giữ chỗ (trừ phần đã tiêu)."""
    GiaKhoBl(mo, [_bai_bl("111", 30), _bai_bl("222", 30)])
    ap = GiaApify(mo, items=[_bl_tt("c1", "111", "khach1", "đẹp")])
    v = GiaViec({"tiktok": {"phan": [{"id": "tiktok-5", "trang_thai": "xong", "usd_so": 0.45}]}}, [])
    v.d["ngan_sach_usd"] = 0.6
    _lay_bl(v, dict(DU_AN, bl_so_bai=10, bl_moi_bai=100), 1, 5.0, time.monotonic() + 300)
    assert ap.gui[0]["tran_usd"] == 0.15                # 0,6 − 0,45; ước tính ×1,5 = 0,49
    v2 = GiaViec({"tiktok": {"phan": [{"id": "t", "trang_thai": "xong", "usd_so": 0.55}]}}, [])
    v2.d["ngan_sach_usd"] = 0.6
    ap.gui.clear()
    tk = _lay_bl(v2, dict(DU_AN, bl_so_bai=10, bl_moi_bai=20), 1, 5.0, time.monotonic() + 300)
    assert ap.gui == [] and any("bỏ qua" in x for x in tk["ghi_chu"])


def test_binh_luan_loi_khong_danh_dau_bai_khong_tra_ve(mo, nhan_gia):
    kho = GiaKhoBl(mo, [_bai_bl("111", 30), _bai_bl("222", 30)])
    ap = GiaApify(mo, items=[_bl_tt("c1", "111", "khach1", "đẹp")])
    ap.run_actor_goc = ap.run_actor

    def qua_gio(*a, **k):
        items, meta = ap.run_actor_goc(*a, **k)
        return items, {**meta, "ma": "QUA_GIO"}
    mo.setattr(A, "_run_actor", qua_gio)
    _lay_bl(GiaViec({}, []), dict(DU_AN, bl_so_bai=10, bl_moi_bai=20), 1, 5.0, time.monotonic() + 300)
    assert kho.ghi[0][3] == {"tiktok:111": (1, 30)}       # bài 222 không bị gạch khỏi lượt sau


def test_tra_loi_cua_chu_bai_khong_phai_kenh_nha_khong_tinh_la_thuong_hieu(mo, nhan_gia):
    kho = GiaKhoBl(mo, [_bai_bl("111", 30, tk="kol.a"), dict(_bai_bl("222", 30, tk="shop.x"), nguon_loai="kenh_nha")])
    GiaApify(mo, items=[_bl_tt("c1", "111", "kol.a", "cảm ơn", tk="kol.a"),
                        _bl_tt("c2", "222", "shop.x", "cảm ơn", tk="shop.x")])
    _lay_bl(GiaViec({}, []), dict(DU_AN, bl_so_bai=10, bl_moi_bai=20), 1, 5.0, time.monotonic() + 300)
    theo = {r["ma"]: r for r in kho.ghi[0][2]}
    assert not theo["c1"]["cua_thuong_hieu"] and theo["c2"]["cua_thuong_hieu"]

