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
        self.chua_toi_han: set[int] = set()     # nguồn đang theo dõi nhưng chưa tới chu kỳ

    def cai(self, mp):
        for ten in ("doc_du_an", "cac_du_an", "nguon_toi_han", "dem_nguon", "da_tieu_thang",
                    "luot_dang_chay", "mo_luot", "dong_luot", "danh_dau_nguon", "ghi_bai",
                    "bai_youtube_can_lam_moi", "cap_nhat_so_lieu", "du_an_dang_bat",
                    "nguon_cua_du_an", "ghi_de_xuat", "nguon_dang_theo_doi"):
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
        return [dict(n) for n in self.nguon if n["id"] not in self.chua_toi_han]

    def nguon_dang_theo_doi(self, ma):
        return [dict(n) for n in self.nguon]

    def dem_nguon(self, ma):
        return {"dang_theo_doi": 3, "tam_dung": 1}

    def da_tieu_thang(self, ma):
        return self.da_tieu

    def luot_dang_chay(self, ma):
        return self.dang_chay

    def mo_luot(self, ma, kieu, ma_viec=None, job_id=None, **kw):
        i = len(self.luot) + 1
        self.luot[i] = {"du_an": ma, "kieu": kieu, "ma_viec": ma_viec, "job_id": job_id, **kw}
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
        self.d["chi_phi"] = {"usd": 0.0123, "da_ghi_so": True}       # như Viec thật: ghi sổ việc
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
    # Kiểm độ phủ (17/10/2026, 2 lần/tuần) có bài thử riêng (`test_kiem_do_phu.py`); các bài thử
    # lượt /theodoi khác không lấy mẫu.
    monkeypatch.setattr(T, "_kiem_do_phu", lambda *a, **k: {})
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
    # Facebook (17/10/2026): thedoor, actor + payload cũ làm dự phòng.
    assert ph["facebook"][0]["actor"] == "thedoor~facebook-page-scraper"
    assert ph["facebook"][0]["payload"] == {"pageUrls": ["https://facebook.com/f"],
                                            "postsToScrape": 3}
    assert ph["facebook"][0]["du_phong"]["payload"]["resultsLimit"] == 3
    assert ph["facebook"][0]["uoc_usd"] == pytest.approx((3 * 0.0025 + 0.01) * 1.3, abs=1e-4)
    # conftest tắt TikTok API → phần đi actor cũ clockworks, tính theo VIDEO (0,003/video).
    assert tt["tiktok-5"]["uoc_usd"] == pytest.approx(10 * 0.003 * 1.3, abs=1e-4)
    assert tt["tiktok-5"]["gia"] == 0.003
    # Instagram: 0,0026/tài khoản, không phí khởi động (17/10/2026, `apify_tool._START_COST`).
    assert ph["instagram"][0]["uoc_usd"] == pytest.approx(0.0026 * 1.3, abs=1e-4)


def test_chia_phan_tiktok_api_tinh_theo_yeu_cau(monkeypatch):
    """18/10/2026: nguồn TikTok qua TikTok API tính theo YÊU CẦU 0,002 USD (giá thật từng run:
    14/14 run scraptik 0,0020, chỉ sự kiện "request"). @hapas.official 20 bài = 1 hồ sơ + 2 trang +
    1 trang bù bài ghim = 4 yêu cầu — ước tính cũ 20 × 0,0012 × 1,3 = 0,0312 USD/lượt lố 3–5 lần
    so với 3–4 yêu cầu thật (0,006–0,008)."""
    import tiktok_api as TT
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    assert TT.GIA_YEU_CAU == T._GIA["tiktok"] == T.TK_TT_YEU_CAU == 0.002
    assert [TT.so_yeu_cau_ho_so(n) for n in (1, 5, 10, 11, 20)] == [3, 3, 3, 4, 4]
    ph = T.chia_phan([_nguon(1, "tiktok", "hapas.official", so_bai=20),
                      _nguon(2, "tiktok", "khac", so_bai=20)])["tiktok"][0]
    assert ph["bo_chuyen"] == "tiktok_ho_so" and ph["gia"] == 0.002
    assert ph["uoc_usd"] == pytest.approx(2 * 4 * 0.002 * 1.3, abs=1e-6)
    assert T._uoc_phan("tiktok", 1, 20) == pytest.approx(0.0104, abs=1e-6)


def test_cat_theo_ngan_sach(monkeypatch):
    import tiktok_api as TT
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    ds = [_nguon(1, "tiktok", "a"), _nguon(2, "tiktok", "b"), _nguon(3, "youtube", "@c"),
          _nguon(4, "instagram", "d")]
    giu, bo = T._cat_theo_ngan_sach(ds, 0.008)
    # TikTok đầu (3 yêu cầu × 0,002 × 1,3 = 0,0078) vừa; thêm TikTok thứ hai thì phần 0,0156 vượt;
    # YouTube miễn phí luôn giữ; Instagram (0,0034) cộng vào thì vượt.
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


# ───────────────────────────── lịch quét tự động (15/10/2026) ─────────────────────────────
def test_ke_hoach_quet_moi_nguon_bo_qua_chu_ky(mo):
    """Lịch chiến dịch `quet_moi_nguon`: quét MỌI nguồn đang theo dõi, kể cả nguồn chưa tới chu kỳ."""
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "a"), _nguon(2, "youtube", "@b")]).cai(mo)
    kho.chua_toi_han = {2}
    assert [n["id"] for n in T.ke_hoach("hapas")["nguon"]] == [1]
    assert [n["id"] for n in T.ke_hoach("hapas", moi_nguon=True)["nguon"]] == [1, 2]


def test_ke_hoach_tra_ma_loi_cho_lich(mo):
    GiaKho(du_an={"hapas": dict(DU_AN, dang_bat=False)}).cai(mo)
    assert T.ke_hoach("hapas")["ma_loi"] == "du_an_tat"
    GiaKho(dang_chay={"id": 7, "ma_viec": "t1"}).cai(mo)
    assert T.ke_hoach("hapas")["ma_loi"] == "dang_chay"
    GiaKho(nguon=[]).cai(mo)
    assert T.ke_hoach("hapas")["ma_loi"] == "khong_co_gi"
    GiaKho(nguon=[_nguon(1, "tiktok", "a")], da_tieu=5.0).cai(mo)
    assert T.ke_hoach("hapas")["ma_loi"] == "het_ngan_sach"
    GiaKho(nguon=[_nguon(1, "tiktok", "a")]).cai(mo)
    mo.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 5.0, False))
    assert T.ke_hoach("hapas")["ma_loi"] == "khong_quet_duoc"
    assert T.ke_hoach("khongco")["ma_loi"] == "khong_co_du_an"


def _bat_tao_viec(mo, kq=None):
    import quet_lon
    import viec_nen
    mo.setattr(quet_lon, "tran_usd_nen", lambda: 20.0)
    mo.setattr(quet_lon, "ngan_sach", lambda tran: (8.0, {"con_lai": 9.0}, ""))
    goi: list[dict] = []

    def tao(loai, tham_so, nen_tang, uoc, ngan_sach, ghi_chu=None, **kw):
        goi.append({"loai": loai, "tham_so": tham_so, "ns": ngan_sach})
        return kq or {"dang_chay_nen": True, "ma_viec": "t10150900-abcde"}
    mo.setattr(viec_nen, "tao_viec", tao)
    return goi


def test_tao_luot_theo_lich_gan_moc_va_quet_moi_nguon(mo):
    """Mốc lịch nằm trong tham số việc: lượt mỗi giờ không bị khoá chống trùng 6 giờ coi là việc
    cũ, còn cùng một mốc nhận hai lần thì ra đúng việc cũ."""
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "a"), _nguon(2, "tiktok", "b")]).cai(mo)
    kho.chua_toi_han = {2}
    goi = _bat_tao_viec(mo)
    kq = T.tao_luot("hapas", moi_nguon=True, lich={"id": 7, "moc": "2026-10-15T09:00:00+07:00"})
    assert kq["ok"] and kq["ma_viec"] == "t10150900-abcde" and kq["so_nguon"] == 2
    ts = goi[0]["tham_so"]
    assert ts["lich_id"] == 7 and ts["moc"] == "2026-10-15T09:00:00+07:00"
    assert ts["moi_nguon"] is True and ts["nguon"] == [1, 2]
    # /theodoi gõ tay: tham số y như trước (không có khoá lịch).
    assert T.tao_luot("hapas")["ok"]
    assert set(goi[1]["tham_so"]) == {"du_an", "ngay", "nguon"} and goi[1]["tham_so"]["nguon"] == [1]


def test_tao_luot_theo_lich_het_thang_khong_tao_viec(mo):
    """Tháng của dự án đã hết: lịch KHÔNG tạo việc (chat vẫn chạy được phần miễn phí như cũ)."""
    GiaKho(du_an={"hapas": dict(DU_AN, tk_bat=True, tk_so_bai=10)}, nguon=[], da_tieu=5.0).cai(mo)
    goi = _bat_tao_viec(mo)
    kq = T.tao_luot("hapas", lich={"id": 3, "moc": "x"})
    assert not kq["ok"] and kq["ma_loi"] == "het_ngan_sach" and "5,00/5,00" in kq["cau"]
    assert goi == []
    assert T.tao_luot("hapas")["ok"] and len(goi) == 1


def test_tao_luot_ma_loi_viec_cu_va_so_tu_choi(mo):
    import viec_nen
    GiaKho(nguon=[_nguon(1, "tiktok", "a")]).cai(mo)
    _bat_tao_viec(mo, {"dang_chay_nen": False, "tu_choi": True, "note": "Hàng đợi đầy."})
    kq = T.tao_luot("hapas", lich={"id": 1, "moc": "x"})
    assert kq == {"ok": False, "ma_loi": "tu_choi", "ma_viec": None, "cau": "Hàng đợi đầy."}
    mo.setattr(viec_nen, "tat_ca", lambda: [{"ma": "t9", "loai": "theo_doi", "trang_thai": "dang_cao",
                                             "tham_so": {"du_an": "hapas"}}])
    kq = T.tao_luot("hapas", lich={"id": 1, "moc": "x"})
    assert kq["ma_loi"] == "dang_chay" and kq["ma_viec"] == "t9"
    _bat_tao_viec(mo, {"dang_chay_nen": False, "tu_choi": True})
    mo.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 5.0, True))
    import quet_lon
    mo.setattr(viec_nen, "tat_ca", list)
    mo.setattr(quet_lon, "ngan_sach", lambda tran: (0.0001, None, ""))
    assert T.tao_luot("hapas", lich={"id": 1, "moc": "x"})["ma_loi"] == "het_ngan_sach_apify"


def _dua_hai_luong(mo):
    """Hai luồng cùng gọi tao_luot cho CÙNG dự án đúng một lúc (lịch console qua luồng job + lịch
    dashboard qua luồng nhịp). `tao_viec` giả ghi sổ chậm 0,2 giây — cửa sổ đua."""
    import quet_lon
    import viec_nen
    GiaKho(nguon=[_nguon(1, "tiktok", "a")]).cai(mo)
    mo.setattr(quet_lon, "tran_usd_nen", lambda: 20.0)
    mo.setattr(quet_lon, "ngan_sach", lambda tran: (8.0, {"con_lai": 9.0}, ""))
    so: list[dict] = []

    def tao(loai, tham_so, *a, **k):
        time.sleep(0.2)
        so.append({"ma": f"t{len(so) + 1}", "loai": "theo_doi", "tham_so": tham_so,
                   "trang_thai": "xep_hang"})
        return {"dang_chay_nen": True, "ma_viec": so[-1]["ma"]}
    mo.setattr(viec_nen, "tao_viec", tao)
    mo.setattr(viec_nen, "tat_ca", lambda: list(so))
    cung_luc = threading.Barrier(2)
    ra: list[dict] = []

    def chay(lich):
        cung_luc.wait()
        ra.append(T.tao_luot("hapas", lich=lich))
    luong = [threading.Thread(target=chay, args=(x,)) for x in (None, {"id": 3, "moc": "m"})]
    for t in luong:
        t.start()
    for t in luong:
        t.join(10)
    return so, ra


def test_tao_luot_cung_du_an_dong_thoi_chi_tao_mot_viec(mo):
    """Review 15/10 (M1): kiểm việc dở → ghi sổ là MỘT bước dưới khoá theo dự án — chỉ một việc,
    bên kia nhận dang_chay (lịch ghi bỏ qua có lý do), không quét trùng, không trả tiền hai lần."""
    so, ra = _dua_hai_luong(mo)
    assert len(so) == 1
    assert sorted(x["ok"] for x in ra) == [False, True]
    assert next(x for x in ra if not x["ok"])["ma_loi"] == "dang_chay"


def test_bai_thu_dua_bat_duoc_loi_khi_khong_co_khoa(mo):
    """Chứng minh bài thử trên bắt được lỗi thật: bỏ khoá thì hai việc cùng được tạo."""
    import contextlib
    mo.setattr(T, "_khoa_tao", lambda ma: contextlib.nullcontext())
    so, _ = _dua_hai_luong(mo)
    assert len(so) == 2


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


def test_youtube_nguon_lat_trang_khi_hon_50_video(monkeypatch):
    """Chủ dự án 15/10 "không có giới hạn": 120 video/lần = 3 trang playlistItems (50+50+20)."""
    goi = []

    def get(res, params, timeout=None):
        goi.append((res, dict(params)))
        if res == "channels":
            return {"items": [{"id": "UCabcdefghijklmnopqrstuv", "snippet": {"title": "K"},
                               "statistics": {}, "contentDetails": {
                                   "relatedPlaylists": {"uploads": "UU9"}}}]}
        if res == "playlistItems":
            dau = int(params.get("pageToken") or 0)
            n = params["maxResults"]
            return {"items": [{"contentDetails": {"videoId": f"v{dau + i:010d}"}} for i in range(n)],
                    "nextPageToken": str(dau + n)}
        if res == "videos":
            return {"items": [{"id": i, "snippet": {"title": "t", "description": "",
                                                    "publishedAt": "2026-10-12T03:00:00Z"},
                               "statistics": {}} for i in params["id"].split(",")]}
        raise AssertionError(res)
    monkeypatch.setattr(A, "_youtube_get", get)
    ra, loi = T._lay_youtube([_nguon(1, "youtube", "UCabcdefghijklmnopqrstuv", so_bai=120)])
    assert not loi and len(ra[1]) == 120
    assert [p["maxResults"] for r, p in goi if r == "playlistItems"] == [50, 50, 20]


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


def test_chay_viec_theo_lich_quet_moi_nguon_ghi_lich_id_va_bao_lich(mo):
    """Việc do lịch quét tự động giao: lượt mang lich_id, nguồn chưa tới chu kỳ vẫn quét (quét
    mọi nguồn), sổ chi phí ghi "(lịch #id)", và kết quả cuối báo về lịch."""
    import quet_tu_dong
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "kola")]).cai(mo)
    kho.chua_toi_han = {1}
    ap = GiaApify(mo, [_tt("kola", 21, "túi hapas")])
    bao = []
    mo.setattr(quet_tu_dong, "ket_thuc_viec", lambda *a, **k: bao.append((a, k)))
    v = _viec(kho.nguon)
    v.d["tham_so"].update(lich_id=7, moc="2026-10-15T09:00:00+07:00", moi_nguon=True)
    trang_thai, _ = T.chay_viec(v)
    assert len(ap.gui) == 1 and trang_thai == "xong"
    luot = v.d["luot_id"]
    assert kho.luot[luot]["lich_id"] == 7
    assert v.chot[0][0] == ["theo dõi hapas (lịch #7)"]
    ((a, k),) = bao
    assert a[:4] == (7, v.ma, luot, "xong")
    # chi phí THẬT (đã chốt theo run id) + dự án + mốc đi kèm để báo platform
    assert k == {"chi_phi_usd": 0.0123, "du_an": "hapas", "moc": "2026-10-15T09:00:00+07:00"}
    # Việc gõ tay: không mở lượt kèm lich_id, không báo lịch.
    bao.clear()
    v2 = _viec([_nguon(2, "tiktok", "kolb")])
    kho.nguon.append(_nguon(2, "tiktok", "kolb"))
    T.chay_viec(v2)
    assert "lich_id" not in kho.luot[v2.d["luot_id"]] and bao == []


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
    # "le" dưới ngưỡng; Threads theo dõi được từ 16/10/2026 nên cũng thành đề xuất.
    assert [x["dinh_danh"] for x in dx] == ["quynhphaken", "th", "me4con"]
    assert dx[1]["nen_tang"] == "threads" and dx[1]["link"] == "https://www.threads.com/@th"
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


def test_dong_luot_giu_ghi_chu_dai_toi_tran(monkeypatch):
    """17/10/2026: lượt 9–11 dài đúng 2.000 ký tự (trần cũ) — mất phễu Báo & Web, bình luận. Kho
    giữ tới `GHI_CHU_TOI_DA`; quá trần thì cắt và ĐÁNH DẤU; COMMENT cột nói đúng trần."""
    import contextlib
    ghi: list[tuple] = []

    class C:
        def execute(self, sql, ts=()):
            assert sql.startswith("UPDATE luot_quet SET")
            ghi.append(ts)

    monkeypatch.setattr(K, "ket_noi", lambda: contextlib.nullcontext(C()))
    phieu = "; ".join(f"phễu tìm Instagram (dòng {i}): về 0 → trong phạm vi 0" for i in range(120))
    assert 2000 < len(phieu) < K.GHI_CHU_TOI_DA
    K.dong_luot(9, trang_thai="xong", ghi_chu=phieu)
    assert ghi[-1][-2] == phieu, "không cắt ở 2.000 nữa"
    K.dong_luot(9, trang_thai="xong", ghi_chu="x" * (K.GHI_CHU_TOI_DA + 500))
    assert len(ghi[-1][-2]) == K.GHI_CHU_TOI_DA and ghi[-1][-2].endswith(K._DUOI_CAT)
    K.dong_luot(9, trang_thai="xong", ghi_chu="")
    assert ghi[-1][-2] is None
    assert K.cat_ghi_chu("y" * K.GHI_CHU_TOI_DA) == "y" * K.GHI_CHU_TOI_DA
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    m = re.search(r"COMMENT ON COLUMN luot_quet\.ghi_chu IS '([^']*)';", sql)
    assert m and f"{K.GHI_CHU_TOI_DA:,}".replace(",", ".") in m.group(1)
    # Mô tả cột BigQuery (bảng mới lẫn khối ALTER cho bảng đã tạo) khớp COMMENT Postgres — soát
    # 17/10/2026 (L4): bản cũ vẫn tả ghi chú như trước khi có phễu từ khoá và trần mới.
    bq = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "bigquery.sql").read_text(
        encoding="utf-8")
    mo_ta = re.findall(r"\bghi_chu\s+(?:STRING\s+)?(?:SET\s+)?OPTIONS\(description='([^']*)'\)", bq)
    assert len(mo_ta) == 2 and set(mo_ta) == {m.group(1)}, mo_ta


_NHAN_BI = ("[Lớp]", "[Mục đích]", "[Grain]", "[Khoá]", "[Nguồn]", "[Phạm vi]", "[Đã xử lý]",
            "[Refresh]", "[Dùng khi]", "[Không dùng khi]", "[Lưu ý]")


def test_kho_theo_quy_chuan_mo_ta_bi():
    """Chủ dự án 14/10/2026: DB mới theo rule BI (task t280613) — mọi bảng có mô tả 11 nhãn
    đúng thứ tự, mỗi nhãn một dòng; mọi cột có mô tả; [Không dùng khi] chỉ bảng thay thế."""
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    bang = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", sql, re.DOTALL)
    # + lich_quet (15/10), kiem_do_phu (17/10/2026), han_muc_apify (18/10/2026),
    # don_vi + quyen (phân quyền theo bên, 19/10/2026), ket_noi_ngoai + tk_quang_cao + qc_tk_ngay +
    # qc_campaign_ngay + qc_ad_ngay + qc_khan_gia (TikTok Ads, 19/10/2026)
    assert len(bang) == 21
    # Cột thêm bằng ALTER (không nằm trong khối CREATE) cũng phải có mô tả.
    assert re.search(r"COMMENT ON COLUMN luot_quet\.lich_id IS '.{10,}';", sql)
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


def test_quyen_lich_quet_va_cot_mark_ghi():
    """Lịch quét tự động: dashboard tạo/sửa/xoá; Mark chỉ đọc + ghi đúng các cột trạng thái chạy
    mà `lang_nghe_db` ghi (lệch thì lỗi quyền chỉ lộ trên VPS). DDL chạy lại được."""
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    # Review 15/10 (L4): Mark đọc ĐÚNG các cột nó dùng (không email tao_boi/sua_boi) — quyền theo
    # cột, thu quyền cả bảng của bản nháp trước khi cấp.
    assert "GRANT SELECT ON lich_quet TO mark;" not in sql
    assert sql.index("REVOKE SELECT ON lich_quet FROM mark;") < sql.index(
        "GRANT SELECT (id,")
    m = re.search(r"GRANT SELECT \(([^)]*)\) ON lich_quet TO mark;", sql)
    doc = {re.sub(r"\s+", "", c) for c in m.group(1).split(",")}
    assert doc == {c.strip() for c in K._COT_LICH.split(",")}
    assert not doc & {"tao_boi", "sua_boi", "tao_luc", "sua_luc"}
    # M3: lớp chặn thứ hai ở DB cho khoảng chiến dịch; DDL chạy lại được.
    assert "DROP CONSTRAINT IF EXISTS lich_quet_chien_dich_check" in sql
    assert "BETWEEN 30 AND 10080" in sql and "PGOPTIONS='-c lock_timeout=5s'" in sql
    m = re.search(r"GRANT UPDATE \(([^)]*)\) ON lich_quet TO mark;", sql)
    cot_mark = {c.strip() for c in m.group(1).split(",")}
    assert cot_mark == {"lan_chay_ke", "lan_chay_cuoi", "ket_qua_cuoi", "so_lan_chay"}
    assert not re.search(r"GRANT[^;]*(INSERT|DELETE)[^;]*ON lich_quet[^;]*TO mark", sql)
    assert "GRANT INSERT, UPDATE, DELETE ON lich_quet TO lang_nghe_web;" in sql
    assert "GRANT USAGE ON SEQUENCE lich_quet_id_seq TO lang_nghe_web;" in sql
    assert "ALTER TABLE luot_quet ADD COLUMN IF NOT EXISTS lich_id" in sql
    # Mọi cột UPDATE trong lang_nghe_db.py trên lich_quet phải nằm trong quyền của Mark.
    src = (Path(__file__).resolve().parents[1] / "lang_nghe_db.py").read_text(encoding="utf-8")
    sua = set()
    for khoi in re.findall(r'UPDATE lich_quet SET (.*?)WHERE', src, re.DOTALL):
        sua |= set(re.findall(r"([a-z_]+) = ", khoi.replace('"', " ")))
    assert sua and sua <= cot_mark, sua - cot_mark


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
        self.da_nhan: set = set()
        mp.setattr(K, "da_gan_nhan", lambda ma, ks: set(self.da_nhan))

    def can(self, ma, nen_tang, toi_da, cao_het=False):
        self.hoi.append((ma, list(nen_tang), toi_da))
        return [b for b in self.bai if b["nen_tang"] in nen_tang][:toi_da]

    def ghi_bl(self, ma, luot, rows, da_lay, khong_tinh_thieu=None):
        self.ghi.append((ma, luot, [dict(r) for r in rows], dict(da_lay)))
        self.khong_tinh = set(khong_tinh_thieu or ())
        return len(rows), 0


@pytest.fixture
def nhan_gia(monkeypatch):
    """Đường gán nhãn NGAY trong lượt (MARK_GAN_NHAN_NEN=0); đường nền: bài thử riêng bên dưới."""
    import phan_loai
    monkeypatch.setenv("MARK_GAN_NHAN_NEN", "0")
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
    # đợt 2e: hỏi từng nền tảng theo cấu hình riêng
    assert kho.hoi == [("hapas", [p], 10) for p in ("youtube", "tiktok", "instagram", "facebook")]
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


def test_gan_nhan_nen_luot_chi_gan_luat_con_lai_de_trong(mo, monkeypatch):
    """17/10/2026: lượt 7 chạy 54 phút vì gán nhãn trong lượt. Mặc định (nền bật) lượt KHÔNG gọi
    model: chỉ gán phần luật (dòng chỉ @tag/emoji — thường đã bị `loc_rac` tách khỏi hop_le), dòng
    còn lại để trống cho `gan_nhan_nen`."""
    import gan_nhan_nen
    import phan_loai
    monkeypatch.delenv("MARK_GAN_NHAN_NEN", raising=False)
    monkeypatch.setattr(gan_nhan_nen, "dang_chay", gan_nhan_nen.bat)   # luồng nền đang sống
    monkeypatch.setattr(phan_loai, "phan_loai_binh_luan",
                        lambda *a, **k: pytest.fail("lượt quét không được gọi model gán nhãn"))
    kho = GiaKhoBl(mo, [_bai_bl("111", 30)])
    GiaApify(mo, items=[_bl_tt("c1", "111", "khach1", "túi đẹp quá"),
                        _bl_tt("c3", "111", "khach3", "giá sao shop")], usd=0.01)
    tk = _lay_bl(GiaViec({}, []), dict(DU_AN, bl_so_bai=10, bl_moi_bai=0), 1, 5.0,
                 time.monotonic() + 300)
    theo = {r["ma"]: r for r in kho.ghi[0][2]}
    assert theo["c1"].get("sac_thai") is None and theo["c3"].get("chu_de") is None
    assert tk["cho_nen"] == 2 and "2 bình luận chờ gán nhãn nền" in T._cau_bl(tk)[0]
    import phan_loai as P
    d = [{"text": "@lan @mai"}, {"text": "giá sao"}]
    T._gan_nhan_bl(d, time.monotonic() + 300, tk)
    assert d[0]["sac_thai"] == "Trung lập" and "sac_thai" not in d[1] and tk["cho_nen"] == 3
    assert P.CHUA not in (d[0]["sac_thai"], d[0]["chu_de"])


def test_bai_web_de_nen_cham_lai_bai_mxh_giu_nhan_phan_xu(monkeypatch):
    import gan_nhan_nen
    monkeypatch.delenv("MARK_GAN_NHAN_NEN", raising=False)
    monkeypatch.setattr(gan_nhan_nen, "dang_chay", gan_nhan_nen.bat)   # luồng nền đang sống
    assert T._nhan_bai_ngay({"platform": "web"}, "Trung lập", "Khác") == (None, None)
    assert T._nhan_bai_ngay({"platform": "tiktok"}, "Tích cực", "Khác") == ("Tích cực", "Khác")
    monkeypatch.setenv("MARK_GAN_NHAN_NEN", "0")
    assert T._nhan_bai_ngay({"platform": "web"}, "Trung lập", "Khác") == ("Trung lập", "Khác")


def test_binh_luan_facebook_tran_con_duoi_muc_actor_doi_thi_khong_chay(mo, nhan_gia):
    """Trần gửi Apify tối thiểu 0,1 USD (`_call`; Facebook chỉ đòi 0,0017 — API Apify 15/10):
    tháng còn ít hơn 0,1 thì bỏ, nói rõ."""
    GiaKhoBl(mo, [dict(_bai_bl("9", 40), nen_tang="facebook", khoa="facebook:9",
                       link="https://www.facebook.com/hapas/posts/9")])
    ap = GiaApify(mo)
    v = GiaViec({}, [])
    tk = _lay_bl(v, dict(DU_AN, bl_so_bai=5, bl_moi_bai=20), 1, 0.05,
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


# ───────────────────────────── tìm theo từ khoá (đợt 2c) ─────────────────────────────
def _tt_tim(user, vid, text, ngay=None):
    ngay = ngay or datetime.datetime.now(_VN) - datetime.timedelta(days=1)
    return ({"kenh": user, "username": user, "followers": 10, "views": 100, "likes": 5,
             "comments": 3, "shares": 0, "hashtags": "", "text": text,
             "link": f"https://www.tiktok.com/@{user}/video/{vid}", "__goc": {"id": vid}}, ngay)


class GiaKhoTk:
    def __init__(self, mp, co_bai=False):
        self.co_bai, self.bai, self.dx = co_bai, [], []
        mp.setattr(K, "co_bai_tu_khoa", lambda ma: self.co_bai)
        mp.setattr(K, "nguon_cua_du_an", lambda ma: [
            {"id": 7, "nen_tang": "tiktok", "dinh_danh": "hapas.official"}])
        mp.setattr(K, "ghi_bai", lambda ma, luot, kieu, rows: (
            self.bai.append((kieu, [dict(r) for r in rows])), (len(rows), 0))[1])
        mp.setattr(K, "ghi_de_xuat", lambda ma, cac: (self.dx.append(list(cac)), len(cac))[1])
        # Tách phát hiện / cập nhật (16/10/2026): khoá đã có trong kho, dòng cập nhật số liệu,
        # lịch chiến dịch (phạm vi), bài cần làm mới số liệu theo link.
        self.da_co: set[str] = set()
        self.cap_nhat: list[dict] = []
        self.lich: list[dict] = []
        self.lam_moi: list[dict] = []
        mp.setattr(K, "khoa_da_co", lambda ma, khoa: {k for k in khoa if k in self.da_co})
        mp.setattr(K, "cap_nhat_so_lieu", lambda ma, luot, rows: (
            self.cap_nhat.extend(dict(r) for r in rows), len(rows))[1])
        mp.setattr(K, "lich_chien_dich", lambda ma: list(self.lich))
        mp.setattr(K, "bai_can_lam_moi", lambda ma, p, tu, n: list(self.lam_moi)[:n])


def test_tim_tu_khoa_giu_bai_nhac_hapas_gan_nguon_va_ghi_tien(mo):
    kho = GiaKhoTk(mo)
    goi = {}

    def tim(p):
        def f(q, limit, country, d_from, d_to, **k):
            goi[p] = (list(q), limit, (d_to - d_from).days, k)
            fn = A._KHI_CO_RUN.get()
            if fn:
                fn({"id": f"run-{p}"}, {"actor": T.TT_ACTOR} if p == "tiktok" else {})
            if p == "tiktok":
                return [_tt_tim("hapas.official", "1", "túi hapas mới về"),
                        _tt_tim("kol.b", "2", "review túi HAPAS xinh"),
                        _tt_tim("kol.b", "3", "hôm nay ăn phở"),
                        _tt_tim("x", "4", "hapas guitar đỉnh"),
                        _tt_tim("kol.c", "5", "hapas cũ", datetime.datetime.now(_VN)
                                - datetime.timedelta(days=60))]
            return []
        return f
    mo.setattr(A, "_FETCH", {p: tim(p) for p in ("tiktok", "facebook", "instagram", "youtube")})
    du_an = dict(DU_AN, tu_khoa=["hapas", "túi hapas", "Hapas", "yeutudieunhonhat"],
                 tk_bat=True, tk_so_bai=15)
    v = GiaViec({}, [])
    import contextvars
    tk = contextvars.copy_context().run(T._tim_tu_khoa, v, du_an, 3, 5.0, time.monotonic() + 600)
    assert goi["tiktok"][0] == ["hapas", "túi hapas", "yeutudieunhonhat"]   # bỏ trùng hoa/thường
    # Instagram tìm theo hashtag (17/10/2026): mọi từ khoá viết liền, bỏ dấu, bỏ trùng.
    assert goi["instagram"][0] == ["hapas", "tuihapas", "yeutudieunhonhat"]
    assert goi["facebook"][1] == 15 and goi["tiktok"][2] >= 30           # lần đầu lùi 30 ngày
    assert goi["youtube"][3] == {"toi_da_trang": 1}                       # trần trang YT
    # Dự phòng TikTok (tính theo video) chỉ được tiêu phần còn lại: 5 USD − ước tính API.
    assert goi["tiktok"][3] == {"tran_du_phong": round(5.0 - T.uoc_tu_khoa_nen_tang(
        "tiktok", 15, ["hapas", "túi hapas", "yeutudieunhonhat"]), 2)}
    kieu, rows = kho.bai[0]
    assert kieu == "tu_khoa"
    theo = {r["khoa"]: r for r in rows}
    assert set(theo) == {"tiktok:1", "tiktok:2"}        # phở: không nhắc; guitar: loại trừ; cũ: ngoài khoảng
    assert theo["tiktok:1"]["nguon_id"] == 7 and theo["tiktok:2"]["nguon_id"] is None
    assert [ph["run_id"] for ph in v.d["nen_tang"]["tu_khoa"]["phan"] if ph.get("run_id")] \
        == ["run-youtube", "run-tiktok", "run-facebook", "run-instagram"]
    # TikTok API tính theo yêu cầu: 1 run (giả) × 0,003 USD > 5 bài × 0,0001 sổ tạm.
    assert tk["giu"] == 2 and tk["usd"] == pytest.approx(T.TK_TT_YEU_CAU, abs=1e-6)
    assert ("tìm theo 3 từ khoá: lấy 4 bài trong phạm vi 30 ngày, cập nhật số liệu 0 bài đã có, "
            "giữ 2") in T._cau_tk(tk)[0]


def test_tim_tu_khoa_khoi_dong_lai_khong_gui_lai_va_ngan_sach(mo):
    GiaKhoTk(mo, co_bai=True)
    goi = []
    mo.setattr(A, "_FETCH", {p: (lambda q, *a, p=p: goi.append(p) or [])
                             for p in ("tiktok", "facebook", "instagram", "youtube")})
    v = GiaViec({"tu_khoa": {"phan": [{"id": "tk-tiktok-r9", "nen_tang": "tiktok",
                                        "run_id": "r9", "trang_thai": "dang_chay"},
                                       {"id": "tk-youtube", "loai": "moc", "nen_tang": "youtube",
                                        "trang_thai": "xong"}]}}, [])
    v.d["ngan_sach_usd"] = 0.04
    du_an = dict(DU_AN, tu_khoa=["hapas"], tk_bat=True, tk_so_bai=15,
                 cau_hinh={"tu_khoa": {"instagram": {"so_bai": 4}}})
    import contextvars
    tk = contextvars.copy_context().run(T._tim_tu_khoa, v, du_an, 3, 5.0, time.monotonic() + 600)
    # TikTok có run dở: không gửi lại; YouTube đã xong; FB (≈0,051) vượt ngân sách việc 0,04;
    # Instagram 4 bài (2 tab × 2 bài × 0,0026 × 1,3 ≈ 0,0135) vừa.
    assert goi == ["instagram"]
    assert any("không gửi lại" in x for x in tk["ghi_chu"])
    assert any("Facebook: bỏ qua (hết ngân sách)" in x for x in tk["ghi_chu"])


def test_tim_tu_khoa_tat_thi_khong_goi(mo):
    mo.setattr(A, "_FETCH", {})
    tk = T._tim_tu_khoa(GiaViec({}, []), dict(DU_AN, tk_bat=False, tk_so_bai=15), 1, 5.0, 0)
    assert tk["lay"] == 0 and T._cau_tk(tk) == []


def test_gia_tim_tu_khoa_khop_dashboard():
    from dashboard import chi_phi as CP
    assert CP.TK_GIA == T._TK_GIA and CP.TK_KHOI == T._TK_KHOI
    tu = ["hapas", "túi hapas", "yeutudieunhonhat"]
    assert CP.uoc_tu_khoa_luot(15, tu) == T.uoc_tu_khoa(15, tu)


def test_ke_hoach_chua_nguon_toi_han_van_tim_tu_khoa(mo):
    kho = GiaKho(du_an={"hapas": dict(DU_AN, tk_bat=True, tk_so_bai=15)}).cai(mo)
    kho.nguon = []
    kh = T.ke_hoach("hapas")
    assert "loi" not in kh and kh["nguon"] == [] and kh["con_thang"] == 5.0
    GiaKho(du_an={"hapas": dict(DU_AN, tk_bat=False, tk_so_bai=15)}).cai(mo)
    assert "tới hạn" in T.ke_hoach("hapas")["loi"]


# ───────────────────────────── cào hết + lọc (đợt 2d) ─────────────────────────────
def _fb(khoa, so_bl, **kw):
    return {"khoa": f"facebook:{khoa}", "nen_tang": "facebook", "binh_luan": so_bl,
            "link": f"https://www.facebook.com/hapas/posts/{khoa}", "tai_khoan": "", "tac_gia": "HAPAS",
            "nguon_loai": "kenh_nha", "bl_lay_luc": None, "bl_da_lay": None, "bl_lay_khi_co": None,
            **kw}


def test_cao_het_xin_du_so_nen_tang_bao_va_chia_lo_theo_tran(mo):
    """bl_moi_bai = 0: mỗi bài xin số nền tảng báo +15% +10; lô vừa ~90% trần console (5 USD
    trong fixture → ≈1.384 bình luận Facebook); bài to hơn trần một mình một lô."""
    lo = T._chia_lo_bl("facebook", [_fb("a", 291), _fb("b", 1200), _fb("c", 30), _fb("d", 5000)], 0)
    can = [[T._can_bl(b, 0) for b in x] for x, _ in lo]
    assert T._can_bl(_fb("a", 291), 0) == int(291 * 1.15) + 10
    # Không trần mỗi bài (chủ dự án 15/10: "không có giới hạn"); bài to hơn trần lượt đi một mình.
    assert T._can_bl(_fb("d", 5000), 0) == int(5000 * 1.15) + 10
    assert all(sum(c) <= 1384 or len(c) == 1 for c in can)
    assert sorted(x for c in can for x in c) == sorted([344, 1390, 44, 5760])
    v = GiaViec({}, [])
    T._tao_cac_phan_bl(v, [_fb("a", 291)], 0)
    ph = v.d["nen_tang"]["binh_luan"]["phan"][0]
    assert ph["payload"]["includeNestedComments"] is True
    assert ph["payload"]["viewOption"] == "RANKED_UNFILTERED" and ph["payload"]["resultsLimit"] == 344
    assert ph["uoc_usd"] == pytest.approx((344 * 0.0025 + 0.001) * 1.3, abs=1e-4)


def test_facebook_da_cao_du_lan_sau_chi_lay_binh_luan_moi(mo):
    luc = datetime.datetime(2026, 10, 14, 23, 50, tzinfo=_VN)
    b = _fb("a", 330, bl_lay_luc=luc, bl_da_lay=280, bl_lay_khi_co=291)
    assert T._tang_dan(b) and T._can_bl(b, 0) == int(39 * 1.15) + 20
    v = GiaViec({}, [])
    T._tao_cac_phan_bl(v, [b], 0)
    pl = v.d["nen_tang"]["binh_luan"]["phan"][0]["payload"]
    assert pl["viewOption"] == "RECENT_ACTIVITY" and pl["onlyCommentsNewerThan"] == "2026-10-13"
    # Chưa cào đủ (actor dừng ở trần): cào lại cả bài, không lọc theo ngày.
    assert not T._tang_dan(_fb("b", 330, bl_lay_luc=luc, bl_da_lay=100, bl_lay_khi_co=291))


def test_tiktok_cao_het_lay_ca_tra_loi(mo):
    v = GiaViec({}, [])
    T._tao_cac_phan_bl(v, [_bai_bl("1", 122)], 0)
    pl = v.d["nen_tang"]["binh_luan"]["phan"][0]["payload"]
    assert pl["commentsPerPost"] == int(122 * 1.15) + 10 and pl["maxRepliesPerComment"] == 100


def test_loc_truoc_khi_gan_nhan_chi_hop_le_di_ai(mo, nhan_gia):
    kho = GiaKhoBl(mo, [_bai_bl("111", 30)])
    GiaApify(mo, items=[
        _bl_tt("c1", "111", "khach1", "Ib"),
        _bl_tt("c2", "111", "khach2", "."),
        _bl_tt("c3", "111", "shopx", "Việc nhẹ lương cao 500k/ngày inbox"),
        _bl_tt("c4", "111", "khach1", "Ib"),
        _bl_tt("c5", "111", "khach3", "túi đẹp quá")])
    tk = _lay_bl(GiaViec({}, []), dict(DU_AN, bl_so_bai=10, bl_moi_bai=0), 1, 5.0,
                 time.monotonic() + 300)
    theo = {r["ma"]: r for r in kho.ghi[0][2]}
    assert [theo[m]["loai"] for m in ("c1", "c2", "c3", "c4", "c5")] == \
        ["hop_le", "it_noi_dung", "spam", "trung", "hop_le"]
    assert theo["c3"]["ly_do_loc"] == "viec_lam_mmo"
    assert nhan_gia == [["Ib", "túi đẹp quá"]]                       # chỉ hợp lệ đi gán nhãn
    assert theo["c2"]["sac_thai"] is None and theo["c1"]["sac_thai"] == "Tích cực"
    assert tk["loc"] == {"hop_le": 2, "it_noi_dung": 1, "spam": 1, "trung": 1}
    assert "đã lọc: 1 it_noi_dung, 1 spam, 1 trung" in T._cau_bl(tk)[0]


def test_seeding_danh_dau_tren_kho():
    """Cùng nội dung từ ≥ 3 tài khoản trong 7 ngày → seeding (SQL chạy trong cùng giao dịch)."""
    class C:
        def __init__(self):
            self.sql = []
            self.rowcount = 2

        def execute(self, q, ts=()):
            self.sql.append((q, ts))
            return self
    c = C()
    assert K._danh_dau_seeding(c, "hapas", ["h1", None, "h1", "h2"]) == 2
    q, ts = c.sql[0]
    assert "HAVING count(DISTINCT lower(tac_gia)) >= %s" in q and "loai = 'seeding'" in q
    assert ts == ("hapas", ["h1", "h2"], 7, 3, "hapas")
    assert "count(DISTINCT khoa_bai) >= 2" in q
    assert K._danh_dau_seeding(c, "hapas", [None]) == 0 and len(c.sql) == 1


def test_cao_lai_khong_gui_lai_ai_binh_luan_da_co_nhan(mo, nhan_gia):
    kho = GiaKhoBl(mo, [_bai_bl("111", 30)])
    kho.da_nhan = {("tiktok:111", "c1")}
    GiaApify(mo, items=[_bl_tt("c1", "111", "khach1", "đẹp quá"), _bl_tt("c2", "111", "k2", "giá sao")])
    _lay_bl(GiaViec({}, []), dict(DU_AN, bl_so_bai=10, bl_moi_bai=0), 1, 5.0, time.monotonic() + 300)
    assert nhan_gia == [["giá sao"]]
    assert kho.hoi[0][2] == 10


def test_cau_hinh_theo_nen_tang_ghi_de_cot_chung():
    """Đợt 2e: mọi giới hạn tuỳ chỉnh từng nền tảng; khoá thiếu dùng cột chung; số rác bị kẹp."""
    da = dict(DU_AN, tk_bat=True, tk_so_bai=15, bl_bat=True, bl_so_bai=10, bl_moi_bai=0,
              cau_hinh={"tu_khoa": {"facebook": {"so_bai": 50}, "instagram": {"bat": False},
                                    "tiktok": {"so_bai": "rác"}},
                        "binh_luan": {"tiktok": {"so_bai": 40, "moi_bai": 3},
                                      "youtube": {"so_bai": 9999}}})
    assert T.cau_hinh(da, "tu_khoa", "facebook")["bat"] is True
    assert T.cau_hinh(da, "tu_khoa", "facebook")["so_bai"] == 50
    assert T.cau_hinh(da, "tu_khoa", "facebook")["so_tu"] == T.TK_IG_TOI_DA_TU
    assert T.cau_hinh(da, "tu_khoa", "instagram")["bat"] is False
    assert T.cau_hinh(da, "tu_khoa", "tiktok")["so_bai"] == 15            # rác → cột chung
    assert T.cau_hinh(da, "tu_khoa", "youtube") == {"bat": True, "so_bai": 15,
                                                     "so_tu": T.TK_IG_TOI_DA_TU}
    assert T.cau_hinh(da, "binh_luan", "tiktok") == {"bat": True, "so_bai": 40, "moi_bai": 5}
    assert T.cau_hinh(da, "binh_luan", "youtube")["so_bai"] == 9999       # không trần trên
    assert T.cau_hinh(da, "binh_luan", "facebook") == {"bat": True, "so_bai": 10, "moi_bai": 0}
    # Facebook không còn cứng 20 khi gói trả phí
    assert T.uoc_tu_khoa_nen_tang("facebook", 50, ["hapas"], fb_toi_da=10**6) > \
        T.uoc_tu_khoa_nen_tang("facebook", 50, ["hapas"])
    # Số mỗi bài âm / null trong JSONB KHÔNG thành 0 (= cào hết, đắt nhất): lấy cột chung.
    da2 = dict(da, bl_moi_bai=40, cau_hinh={"binh_luan": {"tiktok": {"moi_bai": -1},
                                                          "facebook": {"moi_bai": None}}})
    assert [T.cau_hinh(da2, "binh_luan", p)["moi_bai"] for p in ("tiktok", "facebook")] == [40, 40]
    # Chỉ True mới là bật; cột tk_bat / bl_bat là công tắc tổng.
    da3 = dict(da, cau_hinh={"tu_khoa": {"tiktok": {"bat": "false"}}})
    assert T.cau_hinh(da3, "tu_khoa", "tiktok")["bat"] is False
    tat = dict(da, tk_bat=False, bl_bat=False)
    assert not T.tk_co_bat(tat) and not T.cau_hinh(tat, "binh_luan", "tiktok")["bat"]
    assert T.tk_co_bat(dict(da, tk_so_bai=0))                             # Facebook 50 vẫn bật
    assert not T.tk_co_bat(dict(da, tk_so_bai=0, cau_hinh={}))


def test_tim_tu_khoa_theo_cau_hinh_tung_nen_tang(mo):
    GiaKhoTk(mo)
    goi = {}

    def tim(p):
        def f(q, limit, *a, **k):
            goi[p] = (list(q), limit)
            return []
        return f
    mo.setattr(A, "_FETCH", {p: tim(p) for p in ("tiktok", "facebook", "instagram", "youtube")})
    mo.setattr(A, "_goi_apify", lambda: "STARTER")
    da = dict(DU_AN, tu_khoa=["hapas", "yeutudieunhonhat", "hahahapas"], tk_bat=True, tk_so_bai=15,
              cau_hinh={"tu_khoa": {"facebook": {"so_bai": 60}, "tiktok": {"bat": False},
                                    "instagram": {"so_tu": 3}}})
    import contextvars
    contextvars.copy_context().run(T._tim_tu_khoa, GiaViec({}, []), da, 1, 50.0,
                                   time.monotonic() + 600)
    assert "tiktok" not in goi and goi["facebook"][1] == 60       # gói trả phí: không kẹp 20
    assert goi["instagram"][0] == ["hapas", "yeutudieunhonhat", "hahahapas"]
    assert goi["youtube"][1] == 15


# ───────────── cửa sổ tìm theo mốc + phễu + trần trang YouTube (chẩn đoán 16/10) ─────────────
def _chay_tk(du_an, v=None, luot=3):
    import contextvars
    return contextvars.copy_context().run(T._tim_tu_khoa, v or GiaViec({}, []), du_an, luot,
                                          5.0, time.monotonic() + 600)


def test_cua_so_tk_tu_moc_thanh_cong_gan_nhat():
    bay = datetime.datetime(2026, 10, 20, 9, 30, tzinfo=_VN)
    dau = T.dau_tk(["hapas", "túi hapas"], 300)
    tu, n, ly = T.cua_so_tk(None, dau, bay)
    assert (n, ly) == (30, "chưa có mốc") and tu == datetime.datetime(2026, 9, 20, tzinfo=_VN)
    moc = {"luc": "2026-10-16T09:20:00+07:00", "dau": dau}
    tu, n, ly = T.cua_so_tk(moc, dau, bay)       # cách 4 ngày 10 phút + 1 ngày chồng → 6
    assert n == 6 and tu == datetime.datetime(2026, 10, 14, tzinfo=_VN) and "16/10 09:20" in ly
    assert tu <= datetime.datetime(2026, 10, 15, 9, 20, tzinfo=_VN), "chồng mép ≥ 1 ngày"
    assert T.cua_so_tk(dict(moc, luc="2026-10-20T08:00:00+07:00"), dau, bay)[1] == 3
    assert T.cua_so_tk(dict(moc, luc="2026-08-01T08:00:00+07:00"), dau, bay)[1] == 30
    # Đổi từ khoá hoặc số bài của nền tảng → lùi tối đa; hoa/thường, dấu cách thừa không tính.
    assert T.cua_so_tk(moc, T.dau_tk(["hapas"], 300), bay)[1:] == (30, "đổi từ khoá/số bài")
    assert T.cua_so_tk(moc, T.dau_tk(["hapas", "túi hapas"], 150), bay)[1] == 30
    assert T.dau_tk(["Hapas", "Túi  HAPAS"], 300) == dau
    assert T.cua_so_tk(dict(moc, luc="rác"), dau, bay)[1:] == (30, "mốc hỏng")


def test_tim_tu_khoa_cua_so_theo_moc_tung_nen_tang(mo):
    GiaKhoTk(mo)
    goi: dict[str, list] = {}

    def tim(p):
        def f(q, limit, country, d_from, d_to, **k):
            goi.setdefault(p, []).append((d_to - d_from).days)
            if p == "tiktok":
                return [_tt_tim("kol.b", "21", "review túi hapas",
                                datetime.datetime.now(_VN) - datetime.timedelta(days=8))]
            return []
        return f
    mo.setattr(A, "_FETCH", {p: tim(p) for p in ("tiktok", "facebook", "instagram", "youtube")})
    da = dict(DU_AN, tu_khoa=["hapas"], tk_bat=True, tk_so_bai=15)
    tk = _chay_tk(da)
    assert goi["tiktok"][-1] >= 30 and tk["giu"] == 1      # chưa có mốc: 30 ngày
    moc = T.doc_moc_tk("hapas")
    # Lịch sử nhịp (`KHOA_NHIP_TIM`, 18/10/2026) ghi cả lượt về 0 bài — không phải mốc cửa sổ.
    assert set(moc) - {T.KHOA_NHIP_TIM} == {"tiktok"}, "nền tảng trả 0 item không dời mốc"
    assert moc[T.KHOA_NHIP_TIM]["instagram"]["lich_su"][-1][1:] == [0, 0]
    assert moc["tiktok"]["luot"] == 3 and moc["tiktok"]["dau"] == T.dau_tk(["hapas"], 15)
    # Ngay sau đó: TikTok đã tìm thành công → cửa sổ tối thiểu 3 ngày; YouTube vẫn 30.
    tk = _chay_tk(da)
    assert goi["tiktok"][-1] == 3 and goi["youtube"][-1] >= 30
    assert tk["pheu"]["tiktok"]["cua_so"] == 0, "video 8 ngày nằm ngoài cửa sổ 3 ngày"
    # Mốc cách 10 ngày (lượt cách quãng): cửa sổ 10 + 1 ngày chồng → bắt lại video 8 ngày.
    luc = datetime.datetime.now(_VN) - datetime.timedelta(days=10)
    T.ghi_moc_tk("hapas", {"tiktok": dict(moc["tiktok"], luc=luc.isoformat())})
    tk = _chay_tk(da)
    assert goi["tiktok"][-1] in (11, 12) and tk["pheu"]["tiktok"]["cua_so"] == 1
    # Đổi số bài TikTok trên dashboard → lùi 30 ngày lại.
    _chay_tk(dict(da, cau_hinh={"tu_khoa": {"tiktok": {"so_bai": 300}}}))
    assert goi["tiktok"][-1] >= 30


def test_tim_tu_khoa_ghi_kho_hong_thi_khong_doi_moc(mo):
    GiaKhoTk(mo)

    def hong(*a):
        raise K.LoiKho("kho lắng nghe báo lỗi (OperationalError: 08006)")
    mo.setattr(K, "ghi_bai", hong)
    mo.setattr(A, "_FETCH", {p: (lambda *a, p=p, **k: [_tt_tim("kol.b", "2", "review túi hapas")]
                                 if p == "tiktok" else [])
                             for p in ("tiktok", "facebook", "instagram", "youtube")})
    v = GiaViec({}, [])
    with pytest.raises(K.LoiKho):
        _chay_tk(dict(DU_AN, tk_bat=True, tk_so_bai=15), v)
    assert T.doc_moc_tk("hapas") == {}, "bài chưa vào kho thì lượt sau phải tìm lại khoảng đó"
    assert v.d["pheu_tu_khoa"]["tiktok"]["ve"] == 1, "phễu vẫn vào sổ việc"


def test_tim_tu_khoa_pheu_tung_buoc(mo):
    GiaKhoTk(mo)
    cu = datetime.datetime.now(_VN) - datetime.timedelta(days=60)
    bai = [_tt_tim("a", "1", "túi hapas đẹp"),                    # giữ
           _tt_tim("a", "1", "túi hapas đẹp"),                    # trùng
           _tt_tim("b", "2", "hapas guitar đỉnh"),                # từ loại trừ
           _tt_tim("c", "3", "hapas vay nhanh không thế chấp"),   # spam
           _tt_tim("d", "4", "hapas lạc đề"),                     # AI loại: lac_de
           _tt_tim("e", "5", "hapas trùng tên"),                  # AI loại: trung_ten
           _tt_tim("f", "6", "hôm nay ăn phở"),                   # AI không phán, không nhắc
           _tt_tim("g", "7", "hapas cũ", cu)]                     # ngoài cửa sổ

    def ai(cho, *a, **k):
        px = {}
        for i, (d, _) in enumerate(cho):
            if "lạc đề" in d["text"]:
                px[i] = (False, "lac_de")
            elif "trùng tên" in d["text"]:
                px[i] = (False, "trung_ten")
        return px, {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"}
    mo.setattr(A, "_phan_xu_ai", ai)
    mo.setattr(A, "_FETCH", {p: (lambda *a, p=p, **k: [(dict(d), dt) for d, dt in bai]
                                 if p == "tiktok" else [])
                             for p in ("tiktok", "facebook", "instagram", "youtube")})
    v = GiaViec({}, [])
    tk = _chay_tk(dict(DU_AN, tk_bat=True, tk_so_bai=15), v)
    f = tk["pheu"]["tiktok"]
    assert (f["ve"], f["cua_so"], f["trung"], f["loai_tru"], f["spam"], f["khong_nhac"],
            f["giu"], f["moi"]) == (8, 7, 1, 1, 1, 1, 1, 1)
    assert f["ai_loai"] == {"lac_de": 1, "trung_ten": 1}
    assert tk["pheu"]["youtube"]["ve"] == 0 and "facebook" in tk["pheu"]
    dong = next(c for c in T._cau_tk(tk) if c.startswith("phễu tìm TikTok"))
    assert ("(xin 30 ngày, chưa có mốc; theo cấu hình): về 8 → trong phạm vi 7 (ngoài phạm vi 1)"
            " → cập nhật 0 bài đã có; bài mới: trùng 1") in dong
    assert "AI loại 2 (lạc đề 1, trùng tên 1), không nhắc từ khoá 1 → giữ 1 (1 mới)" in dong
    assert v.d["pheu_tu_khoa"]["tiktok"] == f
    ph = next(x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x["id"] == "tk-tiktok")
    assert ph["cua_so"]["ngay"] == 30 and ph["so_item"] == 8


# ───── Instagram gói Free chỉ trả {"demo": true} (đo thật 17/10/2026): phễu phải nói lý do ─────
_NHAN_DEMO = "actor chỉ trả dữ liệu demo cho gói Free (0 bài thật)"


def _ig_tim(user, code, text):
    ngay = datetime.datetime.now(_VN) - datetime.timedelta(days=1)
    return ({"kenh": user, "username": user, "followers": 10, "views": 0, "likes": 5,
             "comments": 1, "shares": 0, "hashtags": "", "text": text,
             "link": f"https://www.instagram.com/p/{code}/", "__goc": {"id": code}}, ngay)


def _fetch_ig_demo(that: dict | None = None):
    """`_FETCH["instagram"]` thật đi qua `_fanout` (mỗi từ khoá một run): từ khoá không có trong
    `that` thì run đó chỉ ra item mẫu → LoiApify CHI_DEMO như `_cho_run`."""
    that = that or {}

    def f(q, limit, *a, **k):
        def mot(kw):
            if kw in that:
                return [that[kw]]
            raise A.LoiApify("CHI_DEMO", "Chỉ có dữ liệu DEMO: actor apidojo~instagram-hashtag-"
                                         "scraper trả 10 item mẫu", {"tu_khoa": kw})
        return A._fanout(mot, list(q))
    return f


@pytest.mark.parametrize("tu", [["hapas", "yeutudieunhonhat"], ["hapas"]],
                         ids=["nhieu_tu_fanout_nuot_loi", "mot_tu_nem_thang"])
def test_tim_tu_khoa_instagram_chi_demo_noi_ly_do_khong_ve_0(mo, tu):
    GiaKhoTk(mo)
    mo.setattr(A, "_FETCH", {**{p: (lambda *a, **k: []) for p in ("tiktok", "facebook",
                                                                    "youtube")},
                             "instagram": _fetch_ig_demo()})
    v = GiaViec({}, [])
    tk = _chay_tk(dict(DU_AN, tu_khoa=tu, tk_bat=True, tk_so_bai=15), v)
    cau = T._cau_tk(tk)
    assert f"tìm Instagram: {_NHAN_DEMO} — nâng gói Apify hoặc đổi actor" in cau
    assert not any(c.startswith("phễu tìm Instagram") for c in cau), "không còn dòng 'về 0'"
    f = tk["pheu"]["instagram"]
    assert f["ma_loi"] == "CHI_DEMO" and f["loi"].startswith(_NHAN_DEMO)
    assert v.d["pheu_tu_khoa"]["instagram"]["ma_loi"] == "CHI_DEMO", "sổ việc giữ lý do"
    ph = next(x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x["id"] == "tk-instagram")
    assert ph["trang_thai"] == "loi" and ph["ma"] == "CHI_DEMO" and ph["usd_so"] == 0
    assert "instagram" not in T.doc_moc_tk("hapas"), "lỗi nguồn không dời mốc"
    assert A._LOI_TU_KHOA.get() is None, "sổ lỗi từ khoá trả lại sau lượt"


def test_tim_tu_khoa_instagram_mot_tu_demo_van_giu_bai_va_noi_tu_loi(mo):
    GiaKhoTk(mo)
    mo.setattr(A, "_FETCH", {**{p: (lambda *a, **k: []) for p in ("tiktok", "facebook",
                                                                    "youtube")},
                             "instagram": _fetch_ig_demo(
                                 {"hapas": _ig_tim("kol.ig", "IG1", "túi hapas xinh")})})
    tk = _chay_tk(dict(DU_AN, tu_khoa=["hapas", "yeutudieunhonhat"], tk_bat=True, tk_so_bai=15))
    f = tk["pheu"]["instagram"]
    assert f["ve"] == 1 and f["giu"] == 1 and "loi" not in f
    dong = next(c for c in T._cau_tk(tk) if c.startswith("phễu tìm Instagram"))
    assert f"từ khoá lỗi: 'yeutudieunhonhat' {_NHAN_DEMO}" in dong
    assert "instagram" in T.doc_moc_tk("hapas")


def test_youtube_cau_tim_dat_cum_trong_ngoac_kep():
    """Dấu cách trong câu tìm YouTube là AND: cụm nhiều chữ phải trong ngoặc kép; cụm đã có từ
    đơn bao trọn thì bỏ (chẩn đoán 16/10/2026: YouTube 0 video ở cả 3 lượt)."""
    q = ["hapas", "túi hapas", "Hapas", "yêu từ điều nhỏ nhất", "hapas.vn", 'ví "x"|y', ""]
    assert A._cau_tim_youtube(q) == 'hapas|"yêu từ điều nhỏ nhất"|hapas.vn|"ví x y"'
    assert A._cau_tim_youtube(["túi hapas", "ví hapas"]) == '"túi hapas"|"ví hapas"'
    assert A._cau_tim_youtube(["#hapas", "túi hapas"]) == "#hapas"
    # "-" đầu từ khoá là toán tử LOẠI TRỪ của YouTube; từ khoá chỉ toàn ký tự bị bỏ → câu rỗng.
    assert A._cau_tim_youtube(["-hapas", "- túi xách"]) == 'hapas|"túi xách"'
    assert A._cau_tim_youtube(['"', "|", " "]) == ""


def test_youtube_tim_cau_rong_khong_goi_api(monkeypatch):
    """Câu tìm rỗng thì YouTube trả video bất kỳ và tốn quota — không gọi."""
    goi = []
    monkeypatch.setattr(A.requests, "get", lambda *a, **k: goi.append(a))
    assert A._youtube_tim(['"', "|"], 50, "VN", None, None) == ([], 0, False)
    assert goi == []


def test_youtube_tim_gui_cau_da_dat_ngoac(monkeypatch):
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "AIzaTHU")
    gui = []

    class Y:
        status_code = 200

        def json(self):
            return {"items": []}
    monkeypatch.setattr(A.requests, "get", lambda url, params=None, **k: gui.append(params) or Y())
    A._youtube_tim(["hapas", "túi hapas", "yêu từ điều nhỏ nhất"], 15, "VN",
                   BAY_GIO - datetime.timedelta(days=3), BAY_GIO, 1)
    assert gui[0]["q"] == 'hapas|"yêu từ điều nhỏ nhất"'


def test_tim_tu_khoa_youtube_tran_trang_theo_quota(mo):
    GiaKhoTk(mo)
    goi = {}
    mo.setattr(A, "_FETCH", {p: (lambda q, lim, *a, p=p, **k: goi.__setitem__(p, (lim, k)) or [])
                             for p in ("tiktok", "facebook", "instagram", "youtube")})
    da = dict(DU_AN, tk_bat=True, tk_so_bai=15,
              cau_hinh={"tu_khoa": {"youtube": {"so_bai": 500}}})
    mo.setenv("YOUTUBE_SEARCH_NEN", "2")
    _chay_tk(da)
    assert goi["youtube"] == (500, {"toi_da_trang": 2}), "10 trang cần, quota việc nền còn 2"
    mo.setenv("YOUTUBE_SEARCH_NEN", "0")
    goi.clear()
    tk = _chay_tk(da)
    assert "youtube" not in goi and "tiktok" in goi
    assert any("YouTube: bỏ qua (hết quota" in x for x in tk["ghi_chu"])


def test_binh_luan_link_va_ma_cha():
    b = {"khoa": "youtube:abcDEF12345", "nen_tang": "youtube", "tai_khoan": "", "tac_gia": ""}
    r = {"kenh": "A", "text": "hay", "link": "https://www.youtube.com/watch?v=abcDEF12345",
         "__goc": {"id": "Ugx1", "snippet": {"parentId": "Ugx0"}}}
    d = T._dong_bl(r, b, ["hapas"])
    assert d["link"].endswith("&lc=Ugx1") and d["ma_cha"] == "Ugx0"
    t = T._dong_bl({"kenh": "k", "text": "x", "__goc": {"cid": "c2", "repliesToId": "c1"}},
                   dict(b, nen_tang="tiktok", khoa="tiktok:1"), [])
    assert t["ma_cha"] == "c1" and t["link"] is None

