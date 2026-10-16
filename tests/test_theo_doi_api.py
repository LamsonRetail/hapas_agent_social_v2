"""`theo_doi_api` (16/10/2026): phần nhiều yêu cầu TikTok API + tìm theo từ khoá tách PHÁT HIỆN
khỏi CẬP NHẬT (chủ dự án: "những khoảng thời gian trong chiến dịch thì cào ra những bài đó phải
cập nhật chứ"). Dữ liệu giả làm sạch, không tên/chữ thật."""
from __future__ import annotations

import contextvars
import datetime
import time

import pytest
from test_theo_doi import DU_AN, GiaKhoTk, GiaViec, _chay_tk, _tt_tim, mo  # noqa: F401

import apify_tool as A
import lang_nghe_db as K
import theo_doi as T
import theo_doi_api as TDA
import tiktok_api as TT

_VN = datetime.timezone(datetime.timedelta(hours=7))
BAY = datetime.datetime(2026, 10, 16, 17, 0, tzinfo=_VN)


# ───────────────────────────── phạm vi theo dõi ─────────────────────────────
def _lich(i, tu, den, kieu="chien_dich", bat=False):
    return {"id": i, "kieu": kieu, "bat": bat,
            "cau_hinh": {"tu_luc": tu, "den_luc": den, "moi_phut": 60}}


def test_pham_vi_mac_dinh_30_ngay(monkeypatch):
    monkeypatch.setattr(K, "lich_chien_dich", lambda ma: [])
    tu, n, ly = TDA.pham_vi("hapas", BAY)
    assert tu == datetime.datetime(2026, 9, 16, tzinfo=_VN) and n == 30 and ly == "30 ngày"


def test_pham_vi_noi_theo_chien_dich_gan_day_kep_92_ngay(monkeypatch):
    lich = [_lich(1, "2026-08-20T08:00", "2026-10-22T22:00"),         # đang chạy, từ 20/08
            _lich(2, "2026-06-01T08:00", "2026-07-01T22:00")]         # kết thúc > 30 ngày: bỏ
    monkeypatch.setattr(K, "lich_chien_dich", lambda ma: lich)
    tu, n, ly = TDA.pham_vi("hapas", BAY)
    assert tu == datetime.datetime(2026, 8, 20, tzinfo=_VN) and "chiến dịch #1" in ly
    monkeypatch.setattr(K, "lich_chien_dich",
                        lambda ma: [_lich(3, "2026-06-20T08:00", "2026-09-20T08:00")])
    tu, n, ly = TDA.pham_vi("hapas", BAY)
    assert n == 92 and "kẹp 92 ngày" in ly


def test_pham_vi_doc_lich_hong_thi_mac_dinh(monkeypatch):
    def hong(ma):
        raise K.LoiKho("kho hỏng")
    monkeypatch.setattr(K, "lich_chien_dich", hong)
    assert TDA.pham_vi("hapas", BAY)[2] == "30 ngày"


@pytest.mark.parametrize("moc, cung, ky_vong", [
    (None, True, 300), ({"xin": 100, "ve": 95}, True, 200), ({"xin": 200, "ve": 200}, True, 300),
    ({"xin": 100, "ve": 20}, True, 30), ({"xin": 100, "ve": 2}, True, 10),
    ({"xin": 100, "ve": 20}, False, 300), ({"xin": "x", "ve": 1}, True, 300)])
def test_so_xin_co_gian_theo_luot_truoc(moc, cung, ky_vong):
    assert TDA.so_xin(300, moc, cung)[0] == ky_vong


def test_tach_da_biet(monkeypatch):
    monkeypatch.setattr(K, "khoa_da_co", lambda ma, khoa: {"tiktok:1"})
    hits = [(dict(_tt_tim("a", "1", "x")[0], platform="tiktok"), BAY),
            (dict(_tt_tim("a", "1", "x")[0], platform="tiktok"), BAY),
            (dict(_tt_tim("b", "2", "y")[0], platform="tiktok"), BAY)]
    cap, moi, trung = TDA.tach_da_biet("hapas", hits, lambda d: f"tiktok:{d['__goc']['id']}")
    assert [r["khoa"] for r in cap] == ["tiktok:1"] and cap[0]["xem"] == 100
    assert [d["__goc"]["id"] for d, _ in moi] == ["2"] and trung == {"tiktok": 1}


# ───────────────────────────── /theodoi: phát hiện + cập nhật ─────────────────────────────
def _fetch(bai_tiktok):
    return {p: (lambda *a, p=p, **k: [(dict(d), dt) for d, dt in bai_tiktok]
                if p == "tiktok" else [])
            for p in ("tiktok", "facebook", "instagram", "youtube")}


def test_bai_ngoai_cua_so_tang_dan_van_giu_va_bai_cu_duoc_cap_nhat(mo):  # noqa: F811
    """Chẩn đoán lượt 6: cửa sổ 3 ngày làm BỎ bài 8 ngày (cả bài đã có trong kho). Nay bài trong
    phạm vi 30 ngày: đã có → cập nhật số liệu (+ ảnh chụp ngày); mới → lọc như cũ."""
    kho = GiaKhoTk(mo)
    kho.da_co = {"tiktok:1"}
    ngay = datetime.datetime.now(_VN)
    bai = [_tt_tim("kol.a", "1", "túi hapas cũ đã biết", ngay - datetime.timedelta(days=8)),
           _tt_tim("kol.b", "2", "review túi hapas mới", ngay - datetime.timedelta(days=8)),
           _tt_tim("kol.c", "3", "hapas ngoài phạm vi", ngay - datetime.timedelta(days=45))]
    mo.setattr(A, "_FETCH", _fetch(bai))
    da = dict(DU_AN, tk_bat=True, tk_so_bai=15)
    T.ghi_moc_tk("hapas", {"tiktok": {"luc": ngay.isoformat(), "dau": T.dau_tk(["hapas"], 15),
                                      "luot": 2, "xin": 15, "ve": 3}})
    tk = _chay_tk(da)
    f = tk["pheu"]["tiktok"]
    assert f["ngay"] == 3 and f["cua_so"] == 0, "vẫn XIN cửa sổ 3 ngày (bộ lọc ngày phía server)"
    assert (f["ve"], f["pham_vi"], f["ngoai_pham_vi"], f["cap_nhat"], f["moi"]) == (3, 2, 1, 1, 1)
    assert [r["khoa"] for r in kho.cap_nhat] == ["tiktok:1"] and kho.cap_nhat[0]["xem"] == 100
    assert [r["khoa"] for _, rows in kho.bai for r in rows] == ["tiktok:2"]
    dong = next(c for c in T._cau_tk(tk) if c.startswith("phễu tìm TikTok"))
    assert "trong phạm vi 2 (ngoài phạm vi 1) → cập nhật 1 bài đã có" in dong
    assert "giữ 1 (1 mới)" in dong
    assert "cập nhật số liệu 1 bài đã có" in T._cau_tk(tk)[0]
    # Cỡ xin co lại theo lượt trước (về 3/15 → xin 10), mốc ghi số xin/về/hữu ích.
    assert f["xin"] == 10 and "về 3/15" in f["xin_ly_do"]
    moc = T.doc_moc_tk("hapas")["tiktok"]
    assert (moc["xin"], moc["ve"], moc["huu_ich"]) == (10, 3, 2)
    assert moc["dau"] == T.dau_tk(["hapas"], 15), "dấu theo cấu hình — cỡ xin đổi không lùi 30 ngày"


def test_lam_moi_so_lieu_bai_tiktok_noi(mo):  # noqa: F811
    """Bài quan trọng mà tìm không trả lại: làm mới số liệu theo link (TikTok API)."""
    kho = GiaKhoTk(mo)
    kho.lam_moi = [{"khoa": "tiktok:70000001", "link": "https://www.tiktok.com/@a/video/70000001"},
                   {"khoa": "tiktok:70000002", "link": "https://www.tiktok.com/@b/video/70000002"}]
    mo.setattr(A, "_FETCH", _fetch([]))
    mo.setattr(TT, "dung_api", lambda viec: True)
    goi = []

    def so_lieu(urls, tran_usd=None):
        goi.append((list(urls), tran_usd))
        for i, _ in enumerate(urls):
            A._SO_RUN.get().append({"run_id": f"lm{i}"})
            A._KHI_CO_RUN.get()({"id": f"lm{i}"}, {})
        return [{"id": "70000001", "playCount": 50, "diggCount": 4, "commentCount": 2,
                 "shareCount": 1}]
    mo.setattr(TT, "so_lieu_bai", so_lieu)
    v = GiaViec({}, [])
    tk = _chay_tk(dict(DU_AN, tk_bat=True, tk_so_bai=15), v)
    assert goi and goi[0][1] == pytest.approx(TDA.LAM_MOI_TOI_DA * TT.GIA_YEU_CAU)
    assert kho.cap_nhat == [{"khoa": "tiktok:70000001", "xem": 50, "thich": 4, "binh_luan": 2,
                             "chia_se": 1}]
    assert tk["lam_moi"]["bai"] == 2 and tk["lam_moi"]["usd"] == pytest.approx(0.004)
    ids = {ph.get("run_id") for ph in v.d["nen_tang"]["tu_khoa"]["phan"]}
    assert {"lm0", "lm1"} <= ids, "run id vào sổ việc để chốt tiền thật"
    # Khởi động lại: đã có mốc làm mới thì không làm lại.
    goi.clear()
    _chay_tk(dict(DU_AN, tk_bat=True, tk_so_bai=15), v)
    assert not goi


def test_phat_lai_luot_6_pheu_truoc_sau():
    """Phát lại lượt 6 thật (16/10 16:50): 252 video TikTok về; lượt 5 (cửa sổ 30 ngày) cho thấy
    ~155/252 nằm trong 30 ngày; 39 trong cửa sổ 3 ngày. Trước: chỉ 39 vào lọc, 213 bỏ (trả tiền
    rồi vứt). Sau: 155 trong phạm vi — 116 bài đã có trong kho được cập nhật số liệu, 39 vào lọc;
    chỉ 97 bài cũ hơn 30 ngày bị bỏ."""
    ngay = BAY
    ve = ([ngay - datetime.timedelta(days=1)] * 39 + [ngay - datetime.timedelta(days=10)] * 116
          + [ngay - datetime.timedelta(days=60)] * 97)
    d3 = ngay - datetime.timedelta(days=3)
    truoc = sum(1 for dt in ve if d3 <= dt)
    tu_pv = ngay - datetime.timedelta(days=30)
    sau = sum(1 for dt in ve if tu_pv <= dt)
    assert (len(ve), truoc, len(ve) - truoc) == (252, 39, 213)
    assert (sau, sau - truoc, len(ve) - sau) == (155, 116, 97)
    # Tiền mỗi bài DÙNG ĐƯỢC (mới + cập nhật), cùng 0,77 USD actor cũ: 0,0197 → 0,0050 USD.
    assert round(0.77 / truoc, 4) == 0.0197 and round(0.77 / sau, 4) == 0.005


# ───────────────────────────── phần nhiều yêu cầu ─────────────────────────────
class GiaRun:
    """Giả `apify_tool._run_actor`: scraptik qua `_call` (ghi `_SO_RUN`), actor cũ (dự phòng)
    gọi thẳng. Mỗi lời gọi một run id, báo `_KHI_CO_RUN` như thật."""

    def __init__(self, mp, tra):
        self.goi, self.tra = [], tra
        mp.setattr(A, "_run_actor", self.run)

    def run(self, actor, payload, limit, mem=None, deadline=None, min_charge=0, *,
            tran_usd=None, mot_phan=False, nen_tang=None):
        rid = f"r{len(self.goi)}"
        self.goi.append((actor, dict(payload), tran_usd))
        A._KHI_CO_RUN.get()({"id": rid}, {})
        items = self.tra(actor, payload)
        return items, {"actor": actor, "run_id": rid, "ma": "OK",
                       "usd": 0.002 if actor == TT.ACTOR else 0.003 * len(items)}


def _chay_phan(ph, cap=0.5):
    v = GiaViec({"tiktok": {"phan": [ph]}}, [1])
    kq = contextvars.copy_context().run(TDA.chay, v, "tiktok", ph, cap, time.monotonic() + 600)
    return v, kq


def test_phan_ho_so_qua_api_thieu_tai_khoan_thi_chay_clockworks(monkeypatch):
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    ph = T.chia_phan([{"id": 1, "nen_tang": "tiktok", "dinh_danh": "@kenh_a", "so_bai_moi_lan": 5},
                      {"id": 2, "nen_tang": "tiktok", "dinh_danh": "kenh_b",
                       "so_bai_moi_lan": 5}])["tiktok"][0]
    assert ph["bo_chuyen"] == "tiktok_ho_so" and ph["actor"] == TT.ACTOR
    assert ph["du_phong"]["actor"] == "clockworks~tiktok-profile-scraper"

    def tra(actor, p):
        if actor != TT.ACTOR:
            return [{"authorMeta": {"name": "kenh_b", "fans": 3}, "createTimeISO": "2026-10-15",
                     "webVideoUrl": "https://www.tiktok.com/@kenh_b/video/70000009"}]
        if p.get("profile_username") == "kenh_a":
            return [{"status_code": 0, "user": {"uid": "u1", "unique_id": "kenh_a"}}]
        if p.get("profile_username"):
            return [{"status_code": 0, "user": {}}]
        return [{"status_code": 0, "has_more": 0, "aweme_list": [
            {"aweme_id": "70000001", "author": {"unique_id": "kenh_a"}, "create_time": 1791000000}]}]
    r = GiaRun(monkeypatch, tra)
    _v, (items, meta, loi, khong) = _chay_phan(ph)
    assert loi is None and khong is None and meta["ma"] == "OK"
    assert {(x.get("authorMeta") or {}).get("name") for x in items} == {"kenh_a", "kenh_b"}
    assert [a for a, p, _ in r.goi if a != TT.ACTOR] == ["clockworks~tiktok-profile-scraper"]
    assert r.goi[-1][1]["profiles"] == ["kenh_b"], "dự phòng chỉ cho tài khoản thiếu"
    assert meta["usd"] == pytest.approx(3 * 0.002 + 0.003)
    assert len(ph["run_phu"]) == 4 and ph["trang_thai"] == "dang_chay"
    assert TDA.tien_phan("tiktok", ph, items, meta) == meta["usd"]
    rows = T._doc_ket_qua("tiktok", items, 5)
    assert set(rows) == {"kenh_a", "kenh_b"}


def test_phan_binh_luan_qua_api_va_viec_nen_cong_run_phu(monkeypatch, tmp_path):
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    u1 = "https://www.tiktok.com/@a/video/70000001"
    ph = {"id": "bl-tiktok-0", "nen_tang": "tiktok", "per": 20, "day_du": False,
          "bai": [{"khoa": "tiktok:70000001", "link": u1}], "actor": "clockworks~x"}
    TDA.gan_binh_luan(ph, [u1], 20)
    assert ph["bo_chuyen"] == "tiktok_binh_luan" and ph["tra_loi"] == 20

    def tra(actor, p):
        return [{"status_code": 0, "has_more": 0, "comments": [
            {"cid": "c1", "text": "đẹp", "reply_comment_total": 0, "reply_id": "0",
             "create_time": 1791000000, "user": {"unique_id": "khach"}}]}]
    GiaRun(monkeypatch, tra)
    _v, (items, _meta, loi, _) = _chay_phan(ph)
    assert loi is None and len(items) == 1 and items[0]["videoWebUrl"] == u1
    assert T._doc_bl("tiktok", items)[0]["text"] == "đẹp"
    import viec_nen
    monkeypatch.setenv("SOCIAL_NEN_THU_MUC", str(tmp_path / "vn"))
    vn = viec_nen.Viec.__new__(viec_nen.Viec)
    vn.d = {"nen_tang": {"binh_luan": {"phan": [ph, {"id": "x", "run_id": "r9"}]}}}
    import threading
    vn._khoa = threading.RLock()
    assert set(vn.run_ids()) == {"r9", *ph["run_phu"]}
