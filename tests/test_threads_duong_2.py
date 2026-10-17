"""Threads ĐƯỜNG 2 + ước tính theo sản lượng thật + nguồn qua actor hồ sơ (17/10/2026).

Chủ dự án 17/10: "threads cũng rất quan trọng" — duyệt mở đường thứ hai (scrapersdelight tìm theo
từ khoá) chạy cùng futurizerush, và theo dõi tài khoản Threads qua actor hồ sơ rẻ. Mẫu
`mau_threads_duong2.json` rút từ raw THẬT vòng 2 (17/10/2026), đã làm sạch tên/mã/nội dung; hai
bài đầu của `tim_kiem_2` là bài cả hai actor cùng bắt (cùng mã, link y hệt như đo thật). Không bài
nào gọi Apify, Postgres hay model thật.
"""
from __future__ import annotations

import contextvars
import copy
import datetime
import json
import time
from pathlib import Path

import pytest
from test_theo_doi import DU_AN, GiaKhoTk, GiaViec, _chay_tk, mo  # noqa: F401

import apify_tool as A
import theo_doi as T
from dashboard import chi_phi as CP

MAU = json.loads((Path(__file__).parent / "mau_threads_duong2.json").read_text(encoding="utf-8"))
_VN = datetime.timezone(datetime.timedelta(hours=7))
TU = ["hapas", "túi hapas", "quà tặng hapas"]
BAT_TH = {"tu_khoa": {"threads": {"bat": True}}}


def _gan_ngay(items, truong, ngay=1, epoch=None):
    """Bản sao mẫu với ngày đăng `ngay` ngày trước BÂY GIỜ (cửa sổ tìm tính theo giờ thật)."""
    ra = copy.deepcopy(items)
    t0 = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=ngay)
    for i, x in enumerate(ra):
        t = t0 - datetime.timedelta(minutes=i)
        x[truong] = t.isoformat().replace("+00:00", "Z") if epoch is None else t.isoformat()
        if epoch:
            x[epoch] = int(t.timestamp())
    return ra


def _d1(ngay=1):
    return A._chuan_threads(_gan_ngay(MAU["tim_kiem_1"], "created_at", ngay, "created_at_timestamp"))


def _d2(ngay=1):
    return A._chuan_threads_2(_gan_ngay(MAU["tim_kiem_2"], "postedAt", ngay))


def _fetch(goi: list, tra: dict, loi: dict | None = None):
    """`A._FETCH` giả: ghi (nền tảng, từ khoá, limit, kwargs) theo THỨ TỰ gọi."""
    def tao(p):
        def f(q, limit, country, d_from, d_to, **k):
            goi.append((p, list(q), limit, (d_to - d_from).days, k))
            fn = A._KHI_CO_RUN.get()
            if fn:
                fn({"id": f"run-{p}"}, {"actor": A._ACTORS.get(p, p)})
            if (loi or {}).get(p):
                raise (loi or {})[p]
            return list(tra.get(p, []))
        return f
    return {p: tao(p) for p in (*T.TK_NEN_TANG, T.TH2_KHOA)}


def _da(**cau_hinh):
    return dict(DU_AN, tu_khoa=TU, tk_bat=True, tk_so_bai=30,
                cau_hinh={"tu_khoa": {p: {"bat": p == "threads", **(cau_hinh if p == "threads"
                                                                   else {})}
                                      for p in T.TK_NEN_TANG}})


# ───────────────────────────── chuẩn hoá + khoá bài ─────────────────────────────
def test_chuan_threads_2_cung_khoa_kho_voi_duong_1_tren_mau_that():
    d1 = {d["link"]: d for d, _ in _d1()}
    d2 = _d2()
    assert len(d2) == 6 and all(dt.tzinfo for _, dt in d2)
    chung = [d for d, _ in d2 if d["link"] in d1]
    assert len(chung) == 2, "2 bài cả hai actor cùng bắt"
    for d in chung:
        # Khoá kho (băm link) của cùng một bài trùng nhau → không thành hai dòng.
        assert T._khoa_bai("threads", d["link"]) == T._khoa_bai("threads", d1[d["link"]]["link"])
        assert A.ma_bai_threads(d["link"]) == d1[d["link"]]["__goc"]["post_code"]
    a = d2[0][0]
    assert (a["followers"], a["views"]) == (None, None), "actor không có follower/lượt xem"
    assert (a["likes"], a["comments"], a["shares"]) == (138, 33, 6)
    assert a["username"] == "nguoi_mau_01" and a["kenh"] == "Người mẫu 01"
    assert a["hashtags"] == "hapas" and a["link"].startswith("https://www.threads.com/@")


def test_link_threads_dung_lai_dung_dang_duong_1():
    assert A._link_threads("Kenh.A", "X1y", "https://www.threads.net/@kenh.a/post/X1y/?x=1") \
        == "https://www.threads.com/@kenh.a/post/X1y"
    assert A._link_threads("", "", "https://www.threads.net/@a/post/Q") \
        == "https://www.threads.com/@a/post/Q"
    u = "https://www.threads.com/@a_b.c/post/DeZ-c_9"
    assert A._link_threads("khac", "khac", u) == u, "link đúng dạng thì giữ nguyên từng ký tự"
    assert A.ma_bai_threads(u) == "DeZ-c_9" and A.ma_bai_threads("") == ""
    assert A._chuan_threads_2([{"text": "x"}, "rác"]) == [], "không có link: bỏ"


def test_fetch_threads_2_gui_dung_input_schema(monkeypatch):
    nhan = {}

    def call(actor, payload, limit, mem=None, min_charge=0, tran_usd=None, *, nen_tang=None):
        nhan.update(actor=actor, payload=payload, limit=limit, tran_usd=tran_usd, nen_tang=nen_tang,
                    mem=mem)
        return copy.deepcopy(MAU["tim_kiem_2"])
    monkeypatch.setattr(A, "_call", call)
    den = datetime.datetime(2026, 10, 17, 9, 30, tzinfo=_VN)
    tu = den - datetime.timedelta(days=3, hours=9, minutes=30)          # 0 giờ ngày 14/10
    ra = A._FETCH["threads_2"](["hapas", "HAPAS", "túi hapas"], 60, "VN", tu, den, moi_tu=20,
                               so_luot=9, tran_usd=0.09)
    assert nhan["actor"] == "scrapersdelight~threads-keyword-search-scraper" and nhan["mem"] is None
    assert nhan["payload"] == {"keywords": ["hapas", "túi hapas"], "searchType": "both",
                               "passesPerSurface": 5, "maxPostsPerKeyword": 20, "maxItems": 60,
                               "postedWithinDays": 4}
    assert (nhan["limit"], nhan["tran_usd"], nhan["nen_tang"]) == (60, 0.09, "threads")
    assert len(ra) == 6
    assert A._fetch_threads_2([], 60, "VN", tu, den) == [] and A._fetch_threads_2(
        ["a"], 0, "VN", tu, den) == []


def test_truong_doc_nen_co_du_cho_hai_actor_scrapersdelight():
    """Việc nền đọc dataset có `fields=`: trường bộ đọc dùng mà thiếu là mất dữ liệu IM LẶNG."""
    for k in ("postCode", "postUrl", "text", "postedAt", "likeCount", "replyCount", "repostCount",
              "authorUsername", "authorFullName", "searchKeyword", "hashtags"):
        assert k in A._TRUONG_ACTOR[A._ACTORS["threads_2"]], k
    for k in ("username", "full_name", "follower_count", "profile_url", "recent_posts"):
        assert k in A._TRUONG_ACTOR[A._ACTORS["threads_ho_so"]], k
    for k in ("search_keyword", "record_type", "requested_username", "profile_url", "post_url"):
        assert k in A._TRUONG_ACTOR[A._ACTORS["threads"]], k


# ───────────────────────────── cấu hình ─────────────────────────────
def test_cau_hinh_duong_2_mac_dinh_bat_duoi_cong_tac_threads():
    da = _da()
    c = T.cau_hinh_th2(da)
    assert c == {"bat": True, "bat_rieng": True, "so_bai": 100, "so_bai_moi_tu": 20, "so_luot": 2}
    assert not T.cau_hinh_th2(dict(da, cau_hinh={}))["bat"], "Threads tắt thì đường 2 tắt"
    assert T.cau_hinh_th2(dict(da, cau_hinh={}))["bat_rieng"]
    assert not T.cau_hinh_th2(dict(da, tk_bat=False))["bat"], "công tắc tổng thắng"
    for x, bat in (({"bat": False}, False), ({"bat": "false"}, False), ({"so_bai": 0}, False),
                   ({"so_bai": "rác"}, True), ({}, True)):
        assert T.cau_hinh_th2(_da(duong2=x))["bat"] is bat, x
    c = T.cau_hinh_th2(_da(duong2={"so_bai": 40, "so_bai_moi_tu": -3, "so_luot": 9}))
    assert (c["so_bai"], c["so_bai_moi_tu"], c["so_luot"]) == (40, 20, 5)
    for x in ({}, {"bat": False}, {"so_bai": 7, "so_bai_moi_tu": 3, "so_luot": 0}, "rác"):
        d = _da(duong2=x)
        assert CP.cau_hinh_th2(d) == T.cau_hinh_th2(d), x
        assert CP.uoc_th2(CP.cau_hinh_th2(d), TU) == T.uoc_th2(T.cau_hinh_th2(d), TU), x
    # Ước tính tối đa: min(trần bài, bài/từ × MỌI từ khoá) × 0,001 × 1,3.
    assert T.uoc_th2(T.cau_hinh_th2(da), TU) == round(60 * 0.001 * 1.3, 4)
    assert T.uoc_th2(T.cau_hinh_th2(da), TU * 20) == round(100 * 0.001 * 1.3, 4)
    assert T.uoc_tu_khoa_du_an(da) == round(T.uoc_tu_khoa_nen_tang("threads", 30, TU)
                                            + T.uoc_th2(T.cau_hinh_th2(da), TU), 4)


# ───────────────────────────── lượt tìm: hai đường ─────────────────────────────
def test_hai_duong_gop_bo_trung_theo_ma_bai_phieu_va_moc_rieng(mo):  # noqa: F811
    kho = GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    v = GiaViec({}, [])
    tk = _chay_tk(_da(), v)
    # Đường 2 chạy TRƯỚC đường 1, MỌI từ khoá; trần bài = min(100, 20 × 3 từ).
    assert [g[0] for g in goi] == [T.TH2_KHOA, "threads"]
    _, q2, lim2, _, k2 = goi[0]
    assert q2 == TU and lim2 == 60
    assert k2 == {"moi_tu": 20, "so_luot": 2, "tran_usd": round(max(0.1, 60 * 0.001 * 1.5), 2)}
    # Đường 1: trần USD = phần còn lại sau đường 2 (5 − 0,006), làm tròn XUỐNG, ≤ trần console.
    assert goi[1][4] == {"tran_usd": 4.99}
    rows = {r["link"]: r for _, cac in kho.bai for r in cac}
    assert len(rows) == 6, "2 bài chung chỉ một dòng + 4 bài riêng đường 2"
    chung = rows["https://www.threads.com/@nguoi_mau_01/post/MAU2000001X"]
    assert (chung["followers"], chung["xem"]) == (104, 20235), "giữ bản đường 1 (có follower/view)"
    rieng = rows["https://www.threads.com/@nguoi_mau_03/post/MAU2000003X"]
    assert (rieng["followers"], rieng["xem"], rieng["binh_luan"]) == (None, None, 109)
    assert len({r["khoa"] for r in rows.values()}) == 6
    f2 = tk["pheu"][T.TH2_KHOA]
    assert (f2["ve"], f2["pham_vi"], f2["trung_duong_1"], f2["giu"], f2["moi"]) == (6, 6, 2, 4, 4)
    assert f2["actor"] == "scrapersdelight~threads-keyword-search-scraper"
    assert tk["pheu"]["threads"]["ve"] == 2 and tk["pheu"]["threads"]["giu"] == 6
    cau = T._cau_tk(tk)
    i = next(n for n, c in enumerate(cau) if c.startswith("phễu tìm Threads ("))
    assert cau[i + 1].startswith("phễu tìm Threads đường 2 (scrapersdelight")
    assert "trùng đường 1 2 → riêng 4" in cau[i + 1] and "giữ 4 mới" in cau[i + 1]
    # Tiền: đường 1 (2 bài + phí khởi động) + đường 2 (6 bài × 0,001), phần + sổ mốc riêng.
    assert tk["usd"] == pytest.approx(2 * 0.0025 + 0.08 + 6 * 0.001)
    ph = {x["id"]: x for x in v.d["nen_tang"]["tu_khoa"]["phan"]}
    assert ph["tk-threads_2"]["usd_so"] == pytest.approx(0.006) and ph["tk-threads_2"]["so_item"] == 6
    assert ph["tk-threads_2-run-threads_2"]["trang_thai"] == "xong"
    moc = T.doc_moc_tk("hapas")
    assert set(moc) == {"threads", T.TH2_KHOA}
    # Sản lượng từng từ khoá (từ gửi mà 0 bài ghi 0) — ước tính lượt sau theo số thật.
    assert moc[T.TH2_KHOA]["ve"] == 6
    assert moc[T.TH2_KHOA]["ve_tu"] == {"hapas": 6, "tui hapas": 0, "qua tang hapas": 0}
    assert moc["threads"]["ve_tu"] == {"hapas": 1, "tui hapas": 1, "qua tang hapas": 0}
    assert moc[T.TH2_KHOA]["rong_lien"] == 0 and moc[T.TH2_KHOA]["huu_ich"] == 4
    assert v.d["pheu_tu_khoa"][T.TH2_KHOA]["trung_duong_1"] == 2


def test_duong_2_loi_khong_hong_duong_1(mo):  # noqa: F811
    kho = GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1()},
                                   {T.TH2_KHOA: A.LoiApify("LOI", "Run kết thúc FAILED.")}))
    tk = _chay_tk(_da())
    assert {r["link"] for _, cac in kho.bai for r in cac} == {d["link"] for d, _ in _d1()}
    assert any(x.startswith("tìm Threads đường 2: LOI") for x in tk["ghi_chu"])
    assert tk["pheu"][T.TH2_KHOA]["loi"] and tk["pheu"]["threads"]["ve"] == 2
    assert not any(c.startswith("phễu tìm Threads đường 2") for c in T._cau_tk(tk))
    assert tk["usd"] == pytest.approx(2 * 0.0025 + 0.08)
    m2 = T.doc_moc_tk("hapas")[T.TH2_KHOA]
    assert m2["rong_lien"] == 1 and "luc" not in m2, "lỗi actor: không dời mốc, chỉ đếm chuỗi"


def test_duong_1_loi_van_giu_bai_duong_2(mo):  # noqa: F811
    kho = GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {T.TH2_KHOA: _d2()},
                                   {"threads": A.LoiApify("QUA_GIO", "Quá giờ sau 230s.")}))
    tk = _chay_tk(_da())
    assert len({r["link"] for _, cac in kho.bai for r in cac}) == 6
    assert tk["pheu"]["threads"]["loi"] and tk["pheu"][T.TH2_KHOA]["trung_duong_1"] == 0
    cau = T._cau_tk(tk)
    assert any(c.startswith("phễu tìm Threads đường 2") for c in cau)
    assert not any(c.startswith("phễu tìm Threads (") for c in cau)
    assert set(T.doc_moc_tk("hapas")) == {T.TH2_KHOA}, "đường 1 lỗi: không dời mốc đường 1"


def test_canh_bao_duong_2_ve_0_bai_hai_luot_lien(mo):  # noqa: F811
    GiaKhoTk(mo)
    for lan, (tra2, loi2) in enumerate((([], None), ([], A.LoiApify("HET_TIEN_THANG", "hết")),
                                        ([], None), (_d2(), None)), 1):
        goi: list = []
        mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: tra2},
                                       {T.TH2_KHOA: loi2} if loi2 else None))
        tk = _chay_tk(_da(), luot=lan)
        f2 = tk["pheu"][T.TH2_KHOA]
        if lan in (1, 2):
            # Lượt 2: tài khoản hết tiền KHÔNG phải lỗi của actor — chuỗi giữ nguyên 1.
            assert f2["rong_lien"] == 1 and "canh_bao" not in f2, lan
            assert not any("CẢNH BÁO" in x for x in tk["ghi_chu"]), lan
        elif lan == 3:
            assert f2["rong_lien"] == 2 and "tắt: du_an.cau_hinh.tu_khoa.threads.duong2.bat" \
                in f2["canh_bao"]
            assert any(x.startswith("tìm Threads: CẢNH BÁO đường 2") for x in tk["ghi_chu"])
            assert "2 lượt liền về 0 bài" in next(c for c in T._cau_tk(tk)
                                                  if c.startswith("phễu tìm Threads đường 2"))
        else:
            assert f2["rong_lien"] == 0 and T.doc_moc_tk("hapas")[T.TH2_KHOA]["rong_lien"] == 0


def test_duong_2_tat_thi_khong_goi(mo):  # noqa: F811
    GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    tk = _chay_tk(_da(duong2={"bat": False}))
    assert [g[0] for g in goi] == ["threads"] and T.TH2_KHOA not in tk["pheu"]


def test_khoi_dong_lai_giua_duong_2_khong_gui_lai(mo):  # noqa: F811
    GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    v = GiaViec({"tu_khoa": {"phan": [{"id": "tk-threads_2-r9", "nen_tang": T.TH2_KHOA,
                                        "run_id": "r9", "trang_thai": "dang_chay"}]}}, [])
    tk = _chay_tk(_da(), v)
    assert [g[0] for g in goi] == ["threads"]
    assert any("đường 2: bot khởi động lại" in x for x in tk["ghi_chu"])


def test_ngan_sach_chat_duong_re_giu_duong_dat_bo(mo):  # noqa: F811
    """Phần còn 0,05 USD: đường 1 (≥ 0,08 khởi động) không vừa → bỏ CÓ lý do; đường 2 vẫn chạy
    với trần bài co theo ngân sách (38 bài × 0,001 × 1,3 ≤ 0,05)."""
    GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    v = GiaViec({}, [])
    v.d["ngan_sach_usd"] = 0.05
    tk = contextvars.copy_context().run(T._tim_tu_khoa, v, _da(), 3, 5.0, time.monotonic() + 600)
    assert [g[0] for g in goi] == [T.TH2_KHOA] and goi[0][2] == 38
    assert "co còn 38/60 bài" in tk["pheu"][T.TH2_KHOA]["xin_ly_do"]
    assert tk["pheu"]["threads"]["bo_qua"].startswith("hết ngân sách")
    v2 = GiaViec({}, [])
    v2.d["ngan_sach_usd"] = 0.005               # chưa đủ 10 bài → bỏ cả đường 2, có lý do
    goi.clear()
    tk = contextvars.copy_context().run(T._tim_tu_khoa, v2, _da(), 3, 5.0, time.monotonic() + 600)
    assert goi == [] and tk["pheu"][T.TH2_KHOA]["bo_qua"].startswith("hết ngân sách")
    assert any(x.startswith("tìm Threads đường 2: bỏ qua (hết ngân sách)") for x in tk["ghi_chu"])


# ───────────────────────────── ước tính theo sản lượng thật (mục 2) ─────────────────────────────
TU21 = ["hapas", "túi hapas", "ví hapas", "túi xách hapas", "quà tặng hapas", "nước hoa hapas",
        "hapas perfume", "hộp quà hapas", "yêu từ điều nhỏ nhất", "yeutudieunhonhat",
        "hahahahahapas", "hapas.vn", "hapassuperbrandday", "quatanghapas", "tuixachhapas",
        "nuochoahapas", "vihapas", "trangsuchapas", "hapasvn", "lammoidieuviyeu", "hapasxthom"]
# Đo thật 17/10 (run 21 từ khoá, không đăng nhập): "hapas" 3 bài, "túi hapas" 12, 19 cụm 0.
VE_TU21 = {**{A._norm(t): 0 for t in TU21}, "hapas": 3, "tui hapas": 12}


def test_san_luong_du_kien_theo_luot_truoc():
    q = TU21[:20]
    assert T.san_luong_du_kien(q, 10, None, 200)[0] == 200, "chưa có sổ: tính trần như cũ"
    n, ly = T.san_luong_du_kien(q, 10, {"ve_tu": VE_TU21}, 200)
    # 3 + min(10, 12) = 13 bài → × 1,5 = 20 (≥ 10, ≤ trần 200)
    assert n == 20 and "13 bài → dự kiến 20/200" in ly
    assert T.san_luong_du_kien(q, 10, {"ve": 15}, 200)[0] == 23, "sổ cũ chỉ có tổng"
    # 19 từ chưa đo tính đủ trần mỗi từ: 0 + 19 × 10 = 190 → × 1,5 → kẹp trần 200.
    assert T.san_luong_du_kien(q, 10, {"ve_tu": {"hapas": 0}}, 200)[0] == 200
    assert T.san_luong_du_kien(["hapas"], 10, {"ve_tu": {"hapas": 0}}, 10)[0] == 10, "sàn 10"
    assert T.san_luong_du_kien(q, 10, {"ve_tu": {"hapas": "rác"}, "ve": True}, 200)[0] == 200
    assert T._dem_ve_tu(["a", "B c"], [({"__goc": {"k": "b  C"}}, None)], "k") == {"a": 0, "b c": 1}
    assert T._dem_ve_tu(["a"], [({"__goc": {}}, None)], "k") is None, "không gắn được từ: bỏ"


def test_luot_11_threads_khong_con_bi_co_oan(mo):  # noqa: F811
    """Phễu lượt 11 thật: 21 từ khoá × 10 bài ước 0,79 USD → "co còn 15/21 từ khoá × 10 bài (ước
    0,59 USD)". Nay sổ mốc có sản lượng thật → ước tính 0,17 USD, tìm đủ 20 từ (trần actor)."""
    GiaKhoTk(mo)
    da = dict(_da(duong2={"bat": False}), tu_khoa=TU21, tk_so_bai=210)
    cu = T.uoc_tu_khoa_nen_tang("threads", 210, TU21)
    assert cu == pytest.approx((210 * 0.0025 + 0.08) * 1.3, abs=1e-4)          # 0,79
    assert T._co_threads(TU21, 210, 0.6)[:2] == (TU21[:15], 150), "đúng câu phễu lượt 11"
    T.ghi_moc_tk("hapas", {"threads": {"luc": "2026-10-16T07:00:00+07:00", "dau": "khac",
                                       "xin": 210, "ve": 15, "ve_tu": VE_TU21}})
    moi = T.uoc_tu_khoa_nen_tang("threads", 210, TU21, moc=T.doc_moc_tk("hapas")["threads"])
    assert moi == pytest.approx((20 * 0.0025 + 0.08) * 1.3, abs=1e-4)            # 0,169
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1()}))
    v = GiaViec({}, [])
    v.d["ngan_sach_usd"] = 0.6
    tk = contextvars.copy_context().run(T._tim_tu_khoa, v, da, 11, 5.0, time.monotonic() + 600)
    assert not any("co còn" in x for x in tk["ghi_chu"])
    (p, q, lim, _, k), = goi
    assert p == "threads" and q == TU21[:20] and lim == 210 and k == {"tran_usd": 0.6}
    assert "dự kiến 20/210" in tk["pheu"]["threads"]["xin_ly_do"]
    # Ngân sách thật sự chật: co theo ước tính SẢN LƯỢNG (từ đầu ra bài nhiều nhất) — 1 từ vừa.
    assert T._co_threads(TU21, 210, 0.15, {"ve_tu": VE_TU21})[:2] == (TU21[:1], 10)
    # Lượt vừa chạy ghi sản lượng mới của từng từ (2 bài mẫu: "hapas" 1, "túi hapas" 1, còn 0).
    ve = T.doc_moc_tk("hapas")["threads"]["ve_tu"]
    assert (ve["hapas"], ve["tui hapas"], sum(ve.values()), len(ve)) == (1, 1, 2, 20)


def test_giu_cho_luot_va_duong_2_theo_san_luong():
    da = dict(_da(), tu_khoa=TU21, tk_so_bai=210)
    toi_da = T.uoc_tu_khoa_du_an(da)
    moc = {"threads": {"ve_tu": VE_TU21}, T.TH2_KHOA: {"ve_tu": VE_TU21}}
    thuc = T.uoc_tu_khoa_du_an(da, moc=moc)
    # Đường 1: 20 bài thay vì 210; đường 2: 20 bài (3 + min(20, 12) = 15 → ×1,5 = 23) thay vì 100.
    assert toi_da == round((210 * 0.0025 + 0.08) * 1.3 + 100 * 0.001 * 1.3, 4)
    assert thuc == round((20 * 0.0025 + 0.08) * 1.3 + 23 * 0.001 * 1.3, 4)
    assert T.uoc_th2(T.cau_hinh_th2(da), TU21, {"ve_tu": VE_TU21}) == round(23 * 0.0013, 4)


# ───────────────────────────── nguồn Threads qua actor hồ sơ (mục 3) ─────────────────────────────
def _ho_so(ngay=1):
    hs = copy.deepcopy(MAU["ho_so"])
    for x in hs:
        x["recent_posts"] = _gan_ngay(x["recent_posts"], "posted_at", ngay)
    return hs


def test_doc_ho_so_threads_cung_dang_kho():
    kq = T._doc_ket_qua("threads", _ho_so(), 10)
    assert set(kq) == {"kenh_mau.vn"}
    tk = kq["kenh_mau.vn"]
    assert tk["ho_so"] == {"ten": "KÊNH MẪU", "tai_khoan": "kenh_mau.vn", "followers": 8434,
                           "link": "https://www.threads.com/@kenh_mau.vn"} and not tk["ghi_chu"]
    assert len(tk["bai"]) == 4
    b = tk["bai"][0]
    assert b["link"] == "https://www.threads.com/@kenh_mau.vn/post/MAUHS00000"
    assert (b["view"], b["like"], b["binh_luan"], b["share"]) == (None, 694, 6, 46)
    assert b["hashtag"] == ["quatang"] and b["ngay"].tzinfo
    # Cùng bài mà đường tìm theo từ khoá (futurizerush) ghi → cùng khoá kho (băm link).
    assert T._khoa_bai("threads", b["link"]) == T._khoa_bai(
        "threads", A._link_threads("kenh_mau.vn", "MAUHS00000", ""))
    rieng = [dict(MAU["ho_so"][0], username="kin.dao", is_private=True, recent_posts=[])]
    assert T._doc_ket_qua("threads", rieng, 10)["kin.dao"]["ghi_chu"] == "tài khoản Threads riêng tư"


def test_chay_viec_nguon_threads_qua_actor_ho_so(mo):  # noqa: F811
    from test_theo_doi import GiaApify, GiaKho, _nguon
    kho = GiaKho(nguon=[_nguon(1, "threads", "kenh_mau.vn", loai="kenh_nha"),
                        _nguon(2, "threads", "khong.co.threads")]).cai(mo)
    ap = GiaApify(mo, items=_ho_so(), usd=0.002)
    v = GiaViec({p: {"phan": c} for p, c in T.chia_phan(kho.nguon).items()}, [1, 2])
    st, cau = contextvars.copy_context().run(T.chay_viec, v)
    (g,) = ap.gui                                   # một tài khoản thiếu: KHÔNG chạy dự phòng
    assert g["actor"] == A._ACTORS["threads_ho_so"] and g["nen_tang"] == "threads"
    assert g["payload"] == {"profiles": ["kenh_mau.vn", "khong.co.threads"], "includePosts": True}
    assert g["limit"] == 2 and g["tran_usd"] == 0.1          # trần tối thiểu (ước 0,0052 × 1,5)
    (_, _, kieu, rows), = kho.bai
    assert kieu == "theo_doi" and len(rows) == 4 and {r["ly_do_giu"] for r in rows} == {"kenh_nha"}
    assert {r["xem"] for r in rows} == {None} and {r["followers"] for r in rows} == {8434}
    ok, loi = kho.danh_dau[0]
    assert ok == [1] and "không lấy được bài" in loi[2]
    ph = v.d["nen_tang"]["threads"]["phan"]
    assert len(ph) == 1 and ph[0]["usd_so"] == pytest.approx(0.002)
    assert st == "xong_mot_phan", cau


def test_nhap_nguon_threads_hapas_vn_qua_dashboard():
    """Người vận hành thêm `@hapas.vn` (Internal channel) trên trang Nguồn — định danh khớp Mark."""
    from dashboard import nhap_lieu as NL
    for vao in ("hapas.vn", "@hapas.vn", "https://www.threads.com/@hapas.vn",
                "threads.net/@HAPAS.vn/"):
        assert NL.chuan_dinh_danh("threads", vao) == ("hapas.vn", "https://www.threads.com/@hapas.vn")
    assert T._chuan_dinh_danh("threads", "hapas.vn") == "hapas.vn" and "kenh_nha" in NL.LOAI_NGUON
    ph = T.chia_phan([dict(DU_AN, id=7, nen_tang="threads", dinh_danh="hapas.vn", loai="kenh_nha",
                           so_bai_moi_lan=5)])["threads"][0]
    assert ph["payload"] == {"profiles": ["hapas.vn"], "includePosts": True}
    assert ph["uoc_usd"] == round(0.002 * 1.3, 4) == CP.uoc_mot_luot("threads", 1, 5)


# ───────────────────────────── dashboard ─────────────────────────────
def test_trang_ngan_sach_cong_duong_2_va_luu_khong_mat_cau_hinh():
    from test_dashboard_app import QL, dang_nhap, tao, thong_bao
    _, c, kho = tao()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15, cau_hinh={"tu_khoa": {"threads": {
        "bat": True, "duong2": {"bat": False, "so_bai": 50}}}})
    csrf = dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert 'data-o="ghi-th2"' in t and "Đường 2 tắt" in t and '"th2": {' in t
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "tk_threads_bat": "1",
                                                   "tk_threads_so_bai": "40"})
    assert "Đã lưu cấu hình thu thập" in thong_bao(c, r)
    th = kho.du_an["hapas"]["cau_hinh"]["tu_khoa"]["threads"]
    assert th == {"bat": True, "so_bai": 40, "duong2": {"bat": False, "so_bai": 50}}, \
        "lưu Ngân sách không được bật lại đường 2 người vận hành đã tắt"
    b = CP.bang_cau_hinh(kho.du_an["hapas"])
    assert b["tu_khoa"]["threads"]["duong2"]["uoc"] == 0.0
    assert b["tu_khoa"]["threads"]["duong2"]["uoc_khi_bat"] == 0.0
