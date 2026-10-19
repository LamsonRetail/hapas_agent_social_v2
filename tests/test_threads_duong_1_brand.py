"""Threads ĐƯỜNG 1 (futurizerush) chỉ nhận từ khoá MỘT chữ có tên brand (18/10/2026).

Đo thật 18/10/2026: futurizerush~meta-threads-scraper tìm cụm nhiều chữ theo kiểu HOẶC từng chữ
("túi hapas" ra bài chỉ có chữ "túi") — một run chỉ 4/88 bài liên quan mà vẫn trả 0,0025 USD/bài
+ 0,08 phí khởi động. Chỉ "hapas" thì mỗi khung ngày chạm ~30–36 bài liên quan. Đường 2
(scrapersdelight, 0,001 USD/bài) khớp cụm đúng hơn: cụm nhiều chữ chỉ gửi đường 2. Không bài nào
gọi Apify, Postgres hay model thật."""
from __future__ import annotations

import contextvars
import copy
import datetime
import json
import time

import pytest
from test_apify_on_dinh import quet  # noqa: F401
from test_theo_doi import DU_AN, GiaKhoTk, GiaViec, _chay_tk, mo  # noqa: F401
from test_threads_duong_2 import MAU, TU, _d1, _d2, _da, _fetch
from test_viec_nen import nen  # noqa: F401

import apify_tool as A
import quet_lon as Q
import theo_doi as T
from dashboard import chi_phi as CP

#: Từ khoá của lượt đo 18/10 (4/88 bài liên quan ở đường 1) + dạng một chữ khác.
TU_DO = ["hapas", "túi hapas", "#HAPAS", "hapas.vn", "hapasvn", "quatanghapas", "yeutudieunhonhat",
         "quà tặng hapas", "túi"]


# ───────────────────────────── luật chọn từ ─────────────────────────────
def test_chi_tu_mot_chu_co_ten_brand_vao_duong_1():
    da = dict(DU_AN, tu_khoa=TU_DO)
    tu, ly = T.tu_threads_duong1(da, TU_DO)
    # "#HAPAS" trùng "hapas" theo cách actor nhận (bỏ '#') — không tốn một suất từ khoá.
    assert tu == ["hapas", "hapas.vn", "hapasvn", "quatanghapas"]
    assert ly == "từ một chữ có tên brand"
    assert T._mot_chu_co_brand("#HAPAS", ["HAPAS"])
    # Phễu: từ chỉ đường 2 nhận ("#HAPAS" là bản trùng của "hapas", không phải "chỉ đường 2").
    assert T._chi_duong_2(TU_DO, tu) == ["túi hapas", "yeutudieunhonhat", "quà tặng hapas", "túi"]
    # "túi" một chữ nhưng không có tên brand; khẩu hiệu viết liền không có chữ "hapas".
    assert not T._mot_chu_co_brand("túi", ["HAPAS"])
    assert not T._mot_chu_co_brand("yeutudieunhonhat", ["HAPAS", "hapas"])
    assert not T._mot_chu_co_brand("túi hapas", ["HAPAS"]), "cụm nhiều chữ chỉ đi đường 2"
    # Tên ngắn (≤ 3 ký tự) phải đứng đầu từ, như hashtag của `_khop_mot_tu`.
    assert T._mot_chu_co_brand("PNJ30Nam", ["PNJ"]) and not T._mot_chu_co_brand("xpnjy", ["PNJ"])
    # Brand = tên + mã + `hashtag_can_nhac_brand.ten` (cách repo xác định brand — cổng brand).
    mm = dict(da, ten="HAPAS", cau_hinh={"hashtag_can_nhac_brand": {"ten": ["Mate Made"]}})
    assert T.tu_threads_duong1(mm, ["hapas", "matemade", "mate made"])[0] == ["hapas", "matemade"]


def test_ghi_de_duong1_tu_va_rong_thi_tat_duong_1():
    th = {"bat": True, "duong1_tu": ["hapas", " túi   hapas ", "HAPAS", 7, "", "hapasvn"],
          "bo_tu": ["hapasvn"]}
    da = dict(DU_AN, tu_khoa=TU_DO, cau_hinh={"tu_khoa": {"threads": th}})
    # Ghi đè thay luật (kể cả cụm nhiều chữ chủ dự án tự đặt), vẫn bỏ `bo_tu` của Threads.
    assert T.duong1_tu(da) == ["hapas", "túi hapas", "hapasvn"]
    assert T.tu_threads_duong1(da, TU_DO) == (["hapas", "túi hapas"], "theo cấu hình duong1_tu")
    # Không phải danh sách: như thiếu → luật một chữ.
    rac = dict(da, cau_hinh={"tu_khoa": {"threads": {"duong1_tu": "hapas"}}})
    assert T.duong1_tu(rac) is None and T.tu_threads_duong1(rac, TU_DO)[0][0] == "hapas"
    # Soát PR #76 (19/10/2026): rỗng thì TẮT đường 1 — không rơi về tên brand / mã dự án.
    rong = dict(da, cau_hinh={"tu_khoa": {"threads": {"duong1_tu": ["hapasvn"],
                                                      "bo_tu": ["hapasvn"]}}})
    assert T.tu_threads_duong1(rong, TU_DO) == ([], "duong1_tu chỉ còn từ bị bo_tu — tắt đường 1")
    tat = dict(da, cau_hinh={"tu_khoa": {"threads": {"duong1_tu": []}}})
    assert T.tu_threads_duong1(tat, TU_DO) == ([], "duong1_tu rỗng — tắt đường 1"), \
        "`duong1_tu: []` có chủ ý = tắt đường 1"
    chi_cum = ["túi hapas", "quà tặng hapas"]
    assert T.tu_threads_duong1(dict(DU_AN, tu_khoa=chi_cum), chi_cum) == (
        [], "không có từ một chữ có tên brand — tắt đường 1")
    # `bo_tu` = ["hapas"] thì đường 1 KHÔNG tìm "HAPAS" (luật bo_tu thắng).
    bo = dict(DU_AN, tu_khoa=["hapas", "túi hapas"],
              cau_hinh={"tu_khoa": {"threads": {"bo_tu": ["hapas"]}}})
    assert T.tu_threads_duong1(bo, T.tu_nen_tang(bo, "threads", T.tu_tim(bo)))[0] == []
    # Tên brand nhiều chữ: không tìm theo mã dự án ("kdla") hay tên viết liền.
    kdla = {"ma": "kdla", "ten": "Khu Du Lịch A", "tu_khoa": ["khu du lịch a"]}
    assert T.tu_threads_duong1(kdla, ["khu du lịch a"])[0] == []
    assert T.tu_threads_duong1({"ten": "Mate Made"}, ["túi mate made"])[0] == []
    for d in (rong, tat, bo, kdla):
        tu = T.tu_nen_tang(d, "threads", T.tu_tim(d))
        assert CP.tu_threads_duong1(d, tu) == T.tu_threads_duong1(d, tu), d


def test_dashboard_cung_danh_sach_va_cung_uoc_tinh():
    ca = [dict(DU_AN, tu_khoa=TU_DO),
          dict(DU_AN, tu_khoa=["túi hapas", "quà tặng hapas"]),
          dict(DU_AN, tu_khoa=TU_DO, cau_hinh={"tu_khoa": {"threads": {
              "bat": True, "duong1_tu": ["hapas", "túi hapas"], "bo_tu": ["túi hapas"]}}}),
          dict(DU_AN, tu_khoa=TU_DO, cau_hinh={"hashtag_can_nhac_brand": {"ten": ["Túi"]}}),
          {"ma": "pnj", "ten": "PNJ", "tu_khoa": ["pnj30nam", "xpnjy", "trang sức pnj"]}]
    for da in ca:
        tu = T.tu_nen_tang(da, "threads", T.tu_tim(da))
        assert CP.tu_threads_duong1(da, tu) == T.tu_threads_duong1(da, tu), da
        assert CP.ten_brand(da) == T.cau_hinh_hashtag_brand(da)["ten"], da
        for kw in TU_DO + ["pnj30nam", "xpnjy"]:
            assert CP._mot_chu_co_brand(kw, CP.ten_brand(da)) == T._mot_chu_co_brand(
                kw, T.cau_hinh_hashtag_brand(da)["ten"]), (kw, da)
        bat = dict(da, tk_bat=True, tk_so_bai=40, cau_hinh={
            **(da.get("cau_hinh") or {}),
            "tu_khoa": {**((da.get("cau_hinh") or {}).get("tu_khoa") or {}),
                        "threads": {**(((da.get("cau_hinh") or {}).get("tu_khoa") or {})
                                       .get("threads") or {}), "bat": True}}})
        b = CP.bang_cau_hinh(bat)
        assert b["uoc_tk"] == pytest.approx(T.uoc_tu_khoa_du_an(bat, fb_toi_da=10 ** 6), abs=1e-4)
        assert b["tu_khoa"]["threads"]["tu_duong1"] == T.tu_threads_duong1(
            bat, T.tu_nen_tang(bat, "threads", T.tu_tim(bat)))[0]
    b = CP.bang_cau_hinh(dict(DU_AN, tu_khoa=TU_DO, tk_bat=True, tk_so_bai=40,
                              cau_hinh={"tu_khoa": {"threads": {"bat": True}}}))
    assert b["tu_khoa"]["threads"]["so_tu_gui"] == 4                 # 40 bài → 4 từ đầu


@pytest.mark.parametrize("th", [{"bo_tu": ["hapas"]}, {"duong1_tu": []}])
def test_dashboard_duong_1_tat_thi_0_usd(th):
    """Đường 1 tắt (19/10/2026): ước tính Threads chỉ còn đường 2, khớp lượt chạy + giữ chỗ."""
    da = dict(DU_AN, tu_khoa=["hapas", "túi hapas"], tk_bat=True, tk_so_bai=40,
              cau_hinh={"tu_khoa": {"threads": {"bat": True, **th}}})
    assert T.uoc_threads_1(da) == 0.0
    b = CP.bang_cau_hinh(da)
    t = b["tu_khoa"]["threads"]
    assert t["tu_duong1"] == [] and t["so_tu_gui"] == 0
    assert t["uoc"] == pytest.approx(t["duong2"]["uoc"], abs=1e-9) and t["uoc"] > 0
    assert b["uoc_tk"] == pytest.approx(T.uoc_tu_khoa_du_an(da, fb_toi_da=10 ** 6), abs=1e-4)
    assert T.giu_cho_tu_khoa(da) == pytest.approx(T.uoc_tu_khoa_du_an(da), abs=1e-4)
    # Trình duyệt tính lại theo danh sách gốc (trước `bo_tu`) máy chủ phát.
    assert t["duong1_goc"] == ([] if "duong1_tu" in th else ["hapas"])


def test_uoc_tinh_theo_san_luong_tinh_tren_tu_duong_1():
    """Ước tính đường 1 theo sản lượng lượt trước (`ve_tu`) lấy đúng từ khoá lượt chạy gửi đi."""
    da = dict(_da(), tu_khoa=["hapas", "túi hapas"], tk_so_bai=60)
    moc = {"threads": {"ve_tu": {"hapas": 30, "tui hapas": 4}}}
    # Đường 1 chỉ "hapas": mỗi từ 60 bài, về 30 → × 1,5 = 45 bài.
    assert T.uoc_threads_1(da, moc=moc) == round((45 * 0.0025 + 0.08) * 1.3, 4)
    # Bản cũ gửi cả "túi hapas": 2 từ × 30 bài, về 30 + 4 = 34 → 51 bài.
    assert T.uoc_tu_khoa_nen_tang("threads", 60, ["hapas", "túi hapas"], moc=moc["threads"]) == \
        round((51 * 0.0025 + 0.08) * 1.3, 4)
    assert T.uoc_tu_khoa_du_an(da, moc=moc) == pytest.approx(
        T.uoc_threads_1(da, moc=moc) + T.uoc_th2(T.cau_hinh_th2(da), ["hapas", "túi hapas"]),
        abs=1e-4)


# ───────────────────────────── lượt /theodoi ─────────────────────────────
def test_theodoi_cum_chi_gui_duong_2_va_pheu_noi_ro(mo):  # noqa: F811
    GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    tk = _chay_tk(_da())
    (p2, q2, *_), (p1, q1, *_) = goi
    assert (p2, q2) == (T.TH2_KHOA, TU), "đường 2 vẫn nhận MỌI từ khoá"
    assert (p1, q1) == ("threads", ["hapas"]), "đường 1 chỉ từ một chữ có tên brand"
    f = tk["pheu"]["threads"]["duong1"]
    assert f == {"tu": ["hapas"], "ly_do": "từ một chữ có tên brand",
                 "chi_duong2": ["túi hapas", "quà tặng hapas"]}
    dong = next(c for c in T._cau_tk(tk) if c.startswith("phễu tìm Threads ("))
    assert ("đường 1 futurizerush tìm 'hapas' (từ một chữ có tên brand; 2 từ khoá chỉ gửi đường 2: "
            "'túi hapas', 'quà tặng hapas')") in dong


def test_theodoi_duong_1_loi_phieu_van_ghi_tu(mo):  # noqa: F811
    GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {T.TH2_KHOA: _d2()},
                                   {"threads": A.LoiApify("QUA_GIO", "Quá giờ sau 230s.")}))
    tk = _chay_tk(_da())
    assert tk["pheu"]["threads"]["loi"] and tk["pheu"]["threads"]["duong1"]["tu"] == ["hapas"]


@pytest.mark.parametrize("th", [{"bo_tu": ["hapas"]}, {"duong1_tu": []}])
def test_theodoi_duong_1_tat_chi_chay_duong_2(mo, th):  # noqa: F811
    """Soát PR #76 (19/10/2026): không có từ một chữ có tên brand sau `bo_tu` / `duong1_tu: []`
    → KHÔNG gọi futurizerush (không 0,08 USD khởi động), đường 2 vẫn chạy, phễu ghi lý do."""
    GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    tk = _chay_tk(_da(**th))
    assert [g[0] for g in goi] == [T.TH2_KHOA], "chỉ đường 2"
    f = tk["pheu"]["threads"]
    assert "tắt đường 1" in f["bo_qua"] and f["duong1"]["tu"] == []
    assert "hapas" not in f["duong1"]["chi_duong2"] if th.get("bo_tu") else \
        f["duong1"]["chi_duong2"] == TU
    assert any(c.startswith("tìm Threads: bỏ qua (") and "tắt đường 1" in c
               for c in T._cau_tk(tk))
    assert tk["pheu"][T.TH2_KHOA]["ve"] == len(_d2()) and tk["usd"] < 0.08


def test_theodoi_ghi_de_duong1_tu(mo):  # noqa: F811
    GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    tk = _chay_tk(_da(duong1_tu=["hapasvn", "hapas"]))
    assert [g[1] for g in goi if g[0] == "threads"] == [["hapasvn", "hapas"]]
    assert tk["pheu"]["threads"]["duong1"]["ly_do"] == "theo cấu hình duong1_tu"


# ───────────────────────────── social_listen tại chỗ ─────────────────────────────
def test_social_listen_tach_hai_duong_bo_trung_giu_ban_duong_1(monkeypatch):
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (1000, 5.0, True))
    goi: list = []
    monkeypatch.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    bay = datetime.datetime.now(A._VN_TZ)
    tu = bay - datetime.timedelta(days=9)
    den = bay - datetime.timedelta(days=2)
    ra = A._tim_threads_tai_cho(["hapas", "túi hapas", "#hapas", "quà tặng hapas"], 100, "VN",
                                tu, den)
    (p2, q2, l2, ngay2, k2), (p1, q1, l1, _, k1) = goi
    # Trần bài chia theo số từ khoá: 1 từ một chữ / 2 cụm ("#hapas" trùng "hapas").
    assert (p2, q2, l2) == (T.TH2_KHOA, ["túi hapas", "quà tặng hapas"], 67)
    # Hai run CHIA trần console Threads 5 USD (19/10/2026): đường 1 lấy phần còn lại.
    assert (p1, q1, l1, k1) == ("threads", ["hapas"], 33, {"tran_usd": 4.9})
    # Đường 2 lọc "trong N ngày tới hôm nay": xin tới BÂY GIỜ để bao trọn khoảng ngày cũ; trần USD
    # = max(sàn 0,1; 67 × 0,001 × 1,5).
    assert ngay2 >= 9 and k2 == {"moi_tu": 34, "tran_usd": 0.1}
    # 2 bài cả hai đường cùng bắt chỉ một dòng, giữ bản đường 1 (có follower + lượt xem).
    assert len(ra) == len(_d1()) + len(_d2()) - 2
    links = [d["link"] for d, _ in ra]
    assert len(set(links)) == len(links)
    chung = next(d for d, _ in ra if d["link"].endswith("MAU2000001X"))
    assert (chung["followers"], chung["views"]) == (104, 20235)
    # Bài chỉ đường 2 có: số để 0 (sheet / xếp hạng social_listen cần số), không phải None.
    assert all(isinstance(d["views"], int) and isinstance(d["followers"], int) for d, _ in ra)
    # Chỉ từ một chữ: không gọi đường 2 (như trước 18/10).
    goi.clear()
    A._tim_threads_tai_cho(["hapas"], 30, "VN", tu, den)
    assert [(g[0], g[1], g[2]) for g in goi] == [("threads", ["hapas"], 30)]
    assert goi[0][4] == {}, "một đường: trần console nguyên vẹn (`_call` tự đọc)"
    goi.clear()
    A._tim_threads_tai_cho(["túi hapas"], 30, "VN", tu, den)
    assert [g[0] for g in goi] == [T.TH2_KHOA], "chỉ cụm: không trả 0,08 khởi động futurizerush"


def test_social_listen_mot_duong_loi_la_mot_phan_ca_hai_loi_thi_nem(monkeypatch):
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (1000, 5.0, True))
    bay = datetime.datetime.now(A._VN_TZ)
    so: list = []
    tok = A._SO_RUN.set(so)
    try:
        monkeypatch.setattr(A, "_FETCH", _fetch([], {"threads": _d1()},
                                                {T.TH2_KHOA: ValueError("rác")}))
        ra = A._tim_threads_tai_cho(["hapas", "túi hapas"], 40, "VN", bay, bay)
        assert len(ra) == len(_d1()) and so[-1]["ma"] == "LOI" and so[-1]["tu_khoa"] == "túi hapas"
        assert A._tong_hop_nguon(ra, so)["status"] == "OK_MOT_PHAN"
        monkeypatch.setattr(A, "_FETCH", _fetch([], {}, {
            "threads": A.LoiApify("QUA_GIO", "Quá giờ."), T.TH2_KHOA: ValueError("rác")}))
        with pytest.raises(ValueError):
            A._tim_threads_tai_cho(["hapas", "túi hapas"], 40, "VN", bay, bay)
    finally:
        A._SO_RUN.reset(tok)


def test_social_listen_uoc_tinh_va_handle(quet, monkeypatch):  # noqa: F811
    # Cụm đi đường 2: không phí khởi động 0,08, 0,001 USD/bài.
    assert A.uoc_threads_tai_cho(["hapas"], 100) == pytest.approx((0.08 + 0.25, 0.33))
    assert A.uoc_threads_tai_cho(["túi hapas"], 100) == pytest.approx((0.1, 0.1))
    assert A.uoc_threads_tai_cho(["hapas", "túi hapas"], 100) == pytest.approx(
        (0.08 + 50 * 0.0025 + 50 * 0.001, 0.08 + 50 * 0.0025))
    assert A.chia_limit_threads(1, 2, 100) == (33, 67) and A.chia_limit_threads(2, 0, 7) == (7, 0)
    chay, _ = quet
    goi: list = []
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (500, 1.0, True))
    for p, f in _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}).items():
        monkeypatch.setitem(A._FETCH, p, f)
    kq = chay(queries=["hapas", "túi hapas"])
    assert [(g[0], g[1]) for g in goi] == [(T.TH2_KHOA, ["túi hapas"]), ("threads", ["hapas"])]
    assert kq["per_platform"]["threads"]["status"] == "OK"
    assert kq["per_platform"]["threads"]["scraped"] == len(_d1()) + len(_d2()) - 2


# ───────────────────────────── social_listen nền (quet_lon) ─────────────────────────────
def test_quet_nen_cum_thanh_mot_luot_duong_2():
    # Khoảng tới HÔM NAY (khoảng cũ thì không có đường 2 — `test_khoang_cu_khong_chay_duong_2`).
    hom_nay = datetime.datetime.now(A._VN_TZ).date()
    ts = {"queries": ["hapas", "túi hapas"],
          "date_from": f"{hom_nay - datetime.timedelta(days=30):%Y-%m-%d}",
          "date_to": f"{hom_nay:%Y-%m-%d}", "country": "VN"}
    kh = Q.ke_hoach(["hapas", "túi hapas"], ["threads"], {"threads": 200}, ts, 45, {})
    x = kh["nen_tang"]["threads"]
    th1 = [ph for ph in x["phan"] if ph.get("kieu") != "duong2"]
    (th2,) = [ph for ph in x["phan"] if ph.get("kieu") == "duong2"]
    assert {ph["payload"]["keywords"][0] for ph in th1} == {"hapas"}
    assert all(ph["actor"] == A._ACTORS["threads"] for ph in th1)
    assert sum(ph["limit"] for ph in th1) >= 100 and th2["limit"] == 100
    assert th2["actor"] == A._ACTORS["threads_2"] and th2["payload"] == {
        "keywords": ["túi hapas"], "searchType": "both", "passesPerSurface": A.TH2_LUOT,
        "maxPostsPerKeyword": 100, "maxItems": 100, "postedWithinDays": th2["ngay"]}
    assert th2["ngay"] >= 30
    assert th2["uoc_usd"] == pytest.approx(100 * 0.001), "0,001/bài, không phí khởi động"
    assert any("chỉ tìm qua scrapersdelight" in c for c in x["ghi_chu"])
    # Dữ liệu về: đọc bằng bộ đọc đường 2; sổ tiền theo giá của phần.
    rows = Q._chuan_hoa("threads", th2, copy.deepcopy(MAU["tim_kiem_2"]))
    # Actor không trả lượt xem / follower: sheet và xếp hạng của social_listen cần số → 0.
    assert len(rows) == 6 and (rows[0][0]["views"], rows[0][0]["followers"]) == (0, 0)
    assert Q._so_tien("threads", th2, MAU["tim_kiem_2"], {}) == pytest.approx(6 * 0.001)
    # Payload dựng lại (cắt theo ngân sách) vẫn cùng số ngày đã chốt.
    assert Q.dung_payload("threads", dict(th2, limit=40), ts)["postedWithinDays"] == th2["ngay"]
    # Bỏ trùng link giữa hai lượt con: giữ bản có lượt xem (đường 1).
    d1 = {"link": "https://www.threads.com/@a/post/X", "views": 9, "followers": 3}
    d2 = {"link": "https://www.threads.com/@a/post/X", "views": 0, "followers": 0}
    giu, trung = Q._bo_trung_dong([(d2, 1), (d1, 2), ({"link": ""}, 3), ({"link": ""}, 4)])
    assert trung == 1 and giu[0] == (d1, 2) and len(giu) == 3
    assert json.dumps(th2["payload"], ensure_ascii=False)


def test_quet_nen_threads_hai_duong_tu_dau_den_cuoi(nen, monkeypatch):  # noqa: F811
    """Việc nền social_listen thật (Apify giả): cụm "túi hapas" thành MỘT run scrapersdelight,
    "hapas" vẫn đi futurizerush; bài đường 2 vào cùng tab Threads."""
    import test_viec_nen as VN

    import viec_nen as V
    goc = VN._item

    def item(actor, i, tag="hapas"):
        if actor == A._ACTORS["threads_2"]:
            return {"postCode": f"D2X{i}", "postUrl": f"https://www.threads.com/@d{i}/post/D2X{i}",
                    "text": f"túi hapas xinh {i}", "postedAt": VN.NOW.isoformat(),
                    "authorUsername": f"d{i}", "likeCount": 1, "replyCount": 0, "repostCount": 0}
        return goc(actor, i, tag)
    monkeypatch.setattr(VN, "_item", item)
    kq = VN._quet(platforms=["threads"], queries=["hapas", "túi hapas"], limit=700,
                  chay_nen=True)
    assert kq["dang_chay_nen"], kq
    d = V.chay_ngay(kq["ma_viec"])
    acts = [u.split("/acts/")[1].split("/runs")[0] for u in nen.post_urls]
    assert acts.count(A._ACTORS["threads_2"]) == 1 and A._ACTORS["threads"] in acts
    (vao,) = [nen.inputs[r["defaultKeyValueStoreId"]] for rid, r in nen.runs.items()
              if nen.actor_cua[rid] == A._ACTORS["threads_2"]]
    assert vao["keywords"] == ["túi hapas"] and vao["maxItems"] == 350
    assert all(nen.inputs[r["defaultKeyValueStoreId"]]["keywords"] == ["hapas"]
               for rid, r in nen.runs.items() if nen.actor_cua[rid] == A._ACTORS["threads"])
    per = d["ket_qua"]["per"]["threads"]
    assert per["scraped"] >= 350 + 350 and per["giu"] > 0


def test_chi_tu_mot_chu_quet_nen_nhu_cu():
    ts = {"queries": ["hapas", "matemade"], "date_from": "2026-09-01", "date_to": "2026-09-30",
          "country": "VN"}
    kh = Q.ke_hoach(["hapas", "matemade"], ["threads"], {"threads": 200}, ts, 45, {})
    assert all(ph.get("kieu") != "duong2" for ph in kh["nen_tang"]["threads"]["phan"])
    # Tại chỗ: cụm thêm MỘT run đường 2 nối đuôi (ước giây cho quyết định chạy nền).
    t1, t2 = Q.toc(A._ACTORS["threads"]), Q.toc(A._ACTORS["threads_2"])
    assert Q.giay_tai_cho(["threads"], {"threads": 100}, ["hapas"]) == round(15 + 100 / t1, 1)
    assert Q.giay_tai_cho(["threads"], {"threads": 100}, ["hapas", "túi hapas"]) == round(
        15 + 50 / t1 + 15 + 50 / t2, 1)
    assert Q.giay_tai_cho(["threads"], {"threads": 100}, ["túi hapas"]) == round(15 + 100 / t2, 1)


def test_uoc_khong_doi_cho_tu_mot_chu_va_khong_lam_cham(mo):  # noqa: F811
    """`_tim_tu_khoa` không đổi gì với dự án chỉ có từ một chữ có tên brand."""
    GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1()}))
    da = dict(_da(duong2={"bat": False}), tu_khoa=["hapas", "hapasvn"], tk_so_bai=20)
    v = GiaViec({}, [])
    contextvars.copy_context().run(T._tim_tu_khoa, v, da, 3, 5.0, time.monotonic() + 600)
    assert [(g[0], g[1]) for g in goi] == [("threads", ["hapas", "hapasvn"])]


# ───────────────────────────── khoảng ngày cũ (soát PR #76, 19/10/2026) ─────────────────────────────
def _khoang(lui_den: int, dai: int = 30):
    """(d_from, d_to) VN: kết thúc `lui_den` ngày trước hôm nay, dài `dai` ngày."""
    ngay = datetime.datetime.now(A._VN_TZ).date() - datetime.timedelta(days=lui_den)
    den = A._parse_date(f"{ngay:%Y-%m-%d}", end=True)
    return den - datetime.timedelta(days=dai), den


def test_ly_do_bo_duong_2_theo_ngay_ket_thuc():
    assert A.ly_do_bo_duong_2(_khoang(0)[1]) == "" and A.ly_do_bo_duong_2(_khoang(2)[1]) == ""
    ly = A.ly_do_bo_duong_2(_khoang(3)[1])
    assert "cũ hơn hôm nay 3 ngày" in ly and "scrapersdelight" in ly and "futurizerush" in ly
    # Khoảng cũ: mọi từ khoá (cả cụm) đi futurizerush như trước 18/10; không `d_to` thì như cũ.
    q = ["hapas", "túi hapas", "#HAPAS"]
    assert A.tach_tu_threads(q, _khoang(60)[1]) == (["hapas", "túi hapas"], [])
    assert A.tach_tu_threads(q, _khoang(1)[1]) == A.tach_tu_threads(q) == (["hapas"], ["túi hapas"])
    # `postedWithinDays` kẹp: schema chỉ có minimum 0 (0 = không lọc) → 1 ≤ N ≤ hằng.
    bay = datetime.datetime.now(A._VN_TZ)
    assert A.ngay_th2(bay - datetime.timedelta(days=900), bay) == A.TH2_NGAY_TOI_DA
    assert A.ngay_th2(bay, bay) == 1
    assert Q.dung_payload("threads", {"kieu": "duong2", "tu_khoa": ["túi hapas"], "limit": 10,
                                      "ngay": 9999}, {})["postedWithinDays"] == A.TH2_NGAY_TOI_DA


def test_khoang_cu_khong_chay_duong_2(monkeypatch):
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (1000, 5.0, True))
    goi: list = []
    monkeypatch.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    tu, den = _khoang(50)
    A._tim_threads_tai_cho(["hapas", "túi hapas"], 100, "VN", tu, den)
    assert [(g[0], g[1], g[2], g[4]) for g in goi] == [("threads", ["hapas", "túi hapas"], 100, {})]
    # Ước tính USD + giây cùng đường: không có run scrapersdelight.
    assert A.uoc_threads_tai_cho(["túi hapas"], 100, den) == pytest.approx((0.08 + 0.25, 0.33))
    t1 = Q.toc(A._ACTORS["threads"])
    assert Q.giay_tai_cho(["threads"], {"threads": 100}, ["hapas", "túi hapas"], den) == round(
        15 + 100 / t1, 1)
    # Việc nền: không lượt đường 2, cụm thành lượt futurizerush theo cửa sổ ngày, ghi chú nói rõ.
    ts = {"queries": ["hapas", "túi hapas"], "date_from": f"{tu:%Y-%m-%d}",
          "date_to": f"{den:%Y-%m-%d}", "country": "VN"}
    x = Q.ke_hoach(["hapas", "túi hapas"], ["threads"], {"threads": 200}, ts, 45, {})["nen_tang"][
        "threads"]
    assert all(ph.get("kieu") != "duong2" for ph in x["phan"])
    assert {ph["tu_khoa"] for ph in x["phan"]} == {"hapas", "túi hapas"}
    assert all(ph["actor"] == A._ACTORS["threads"] for ph in x["phan"])
    assert any("scrapersdelight chỉ lọc" in c for c in x["ghi_chu"])


def test_social_listen_khoang_cu_ghi_ly_do(quet, monkeypatch):  # noqa: F811
    chay, _ = quet
    goi: list = []
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (500, 1.0, True))
    tu, den = _khoang(45)
    d1 = A._chuan_threads(copy.deepcopy(MAU["tim_kiem_1"]))
    for p, f in _fetch(goi, {"threads": d1, T.TH2_KHOA: _d2()}).items():
        monkeypatch.setitem(A._FETCH, p, f)
    kq = chay(queries=["hapas", "túi hapas"], date_from=f"{tu:%Y-%m-%d}",
              date_to=f"{den:%Y-%m-%d}")
    assert [g[0] for g in goi] == ["threads"], "không trả tiền scrapersdelight cho bài ngoài khoảng"
    assert "scrapersdelight chỉ lọc" in kq["per_platform"]["threads"]["duong2_bo_qua"]
    # Khoảng tới hôm nay: không có câu này.
    goi.clear()
    kq = chay(queries=["hapas", "túi hapas"])
    assert "duong2_bo_qua" not in kq["per_platform"]["threads"]


# ───────────────────────────── LOW: chia bài / chia trần ─────────────────────────────
def test_chia_limit_khong_vuot_tran_va_chia_tran_console():
    for so1, so2, lim in [(1, 1, 1), (1, 1, 0), (1, 1, 2), (3, 1, 2), (1, 5, 3), (2, 2, 101)]:
        l1, l2 = A.chia_limit_threads(so1, so2, lim)
        assert l1 + l2 == lim and l1 >= 0 and l2 >= 0, (so1, so2, lim)
        if lim >= 2:
            assert l1 >= 1 and l2 >= 1
    assert A.chia_limit_threads(1, 1, 1) == (1, 0)
    # Hai run cùng lượt: tổng trần = trần console (≥ 0,2); một run thì để `_call` đọc trần console.
    assert A.chia_tran_threads(1.0, 67, True) == (0.9, 0.1)
    assert A.chia_tran_threads(0.3, 1000, True) == (0.1, 0.2)
    assert A.chia_tran_threads(5.0, 67, False) == (None, 0.1)
    for tran in (0.2, 0.25, 1.0, 3.3):
        t1, t2 = A.chia_tran_threads(tran, 5000, True)
        assert t1 + t2 == pytest.approx(tran) and min(t1, t2) >= A._TRAN_USD_KHOANG[0]
