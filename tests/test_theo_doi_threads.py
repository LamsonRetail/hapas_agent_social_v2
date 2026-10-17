"""Threads trong lượt `/theodoi` và dashboard (chủ dự án 16/10/2026: "thêm listening threads").

Mẫu `mau_threads_lang_nghe.json` rút từ 3 lượt chạy thử THẬT actor futurizerush~meta-threads-scraper
(16/10/2026), đã làm sạch tên/mã/nội dung. Bình luận dùng mẫu thật của actor trả lời
(`mau_binh_luan_threads_ig.json`, 04/10/2026). Không bài nào gọi Apify, Postgres hay model thật.
"""
from __future__ import annotations

import contextvars
import copy
import datetime
import json
import re
import time
from pathlib import Path

import pytest
import test_theo_doi as TT
from test_theo_doi import (
    DU_AN,
    GiaApify,
    GiaKho,
    GiaKhoBl,
    GiaKhoTk,
    GiaViec,
    _chay_tk,
    _lay_bl,
    _nguon,
)

import apify_tool as A
import deep_dive_tool as D
import theo_doi as T
from dashboard import chi_phi as CP
from dashboard import chi_so as CS
from dashboard import nhap_lieu as NL

# Fixture dùng chung với test_theo_doi (gán lại để pytest thấy trong module này).
mo = TT.mo
nhan_gia = TT.nhan_gia

GOC = Path(__file__).resolve().parents[1]
MAU = json.loads((Path(__file__).parent / "mau_threads_lang_nghe.json").read_text(encoding="utf-8"))
MAU_BL = json.loads((Path(__file__).parent / "mau_binh_luan_threads_ig.json")
                    .read_text(encoding="utf-8"))["futurizerush_threads"]
_VN = datetime.timezone(datetime.timedelta(hours=7))


def _moi(items, ngay=1):
    """Bản sao mẫu với ngày đăng `ngay` ngày trước BÂY GIỜ (cửa sổ tìm tính theo giờ thật)."""
    ra = copy.deepcopy(items)
    t = int((datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=ngay)).timestamp())
    for i, x in enumerate(ra):
        x["created_at_timestamp"] = t - 60 * i
        x["created_at"] = datetime.datetime.fromtimestamp(x["created_at_timestamp"],
                                                          datetime.timezone.utc).isoformat()
    return ra


BAT_TH = {"tu_khoa": {"threads": {"bat": True}}, "binh_luan": {"threads": {"bat": True}}}


# ───────────────────────────── mặc định tắt ─────────────────────────────
def test_threads_mac_dinh_tat_den_khi_bat_ro():
    da = dict(DU_AN, tk_bat=True, tk_so_bai=15, bl_bat=True, bl_so_bai=10, bl_moi_bai=0)
    for nhom in ("tu_khoa", "binh_luan"):
        assert not T.cau_hinh(da, nhom, "threads")["bat"]           # deploy không tự tiêu tiền
        assert T.cau_hinh(da, nhom, "tiktok")["bat"]                # nền tảng cũ: như trước
        assert T.cau_hinh(dict(da, cau_hinh=BAT_TH), nhom, "threads")["bat"]
        # công tắc tổng vẫn thắng; "true" dạng chuỗi không phải bật
        assert not T.cau_hinh(dict(da, tk_bat=False, bl_bat=False, cau_hinh=BAT_TH), nhom,
                              "threads")["bat"]
        rac = {nhom: {"threads": {"bat": "true"}}}
        assert not T.cau_hinh(dict(da, cau_hinh=rac), nhom, "threads")["bat"]
    assert T.uoc_tu_khoa_du_an(da) == T.uoc_tu_khoa_du_an(
        dict(da, cau_hinh={"tu_khoa": {"threads": {"bat": False}}}))


def test_dashboard_cau_hinh_hien_thi_dien_tat_cho_threads():
    goc = {"tu_khoa": {"tiktok": {"bat": True}, "threads": {"so_bai": 40}}}
    ra = CP.cau_hinh_hien_thi(goc)
    assert ra["tu_khoa"]["threads"] == {"so_bai": 40, "bat": False}
    assert ra["binh_luan"]["threads"] == {"bat": False} and ra["tu_khoa"]["tiktok"] == {"bat": True}
    assert "bat" not in goc["tu_khoa"]["threads"]                   # không sửa dict gốc
    assert CP.cau_hinh_hien_thi(BAT_TH)["tu_khoa"]["threads"] == {"bat": True}
    assert CP.cau_hinh_hien_thi(None)["tu_khoa"] == {"threads": {"bat": False},
                                                      "web": {"bat": False}}   # web: chỉ HAPAS


# ─────────────── nguồn Threads (actor hồ sơ từ 17/10/2026; chế độ "user" làm dự phòng) ───────────────
def test_chia_phan_threads_actor_ho_so_du_phong_che_do_user_toi_da_20_tai_khoan():
    ds = [_nguon(i, "threads", f"https://www.threads.net/@Kenh{i}/", so_bai=5) for i in range(1, 23)]
    ds.append(_nguon(99, "threads", "@kol.x", so_bai=30))
    ph = {x["id"]: x for x in T.chia_phan(ds)["threads"]}
    assert set(ph) == {"threads-10", "threads-10-2", "threads-30"}
    a = ph["threads-10"]
    ten = [f"kenh{i}" for i in range(1, 21)]
    assert a["actor"] == A._ACTORS["threads_ho_so"] and not a.get("mem")
    assert a["payload"] == {"profiles": ten, "includePosts": True}
    assert (a["limit"], a["gia"], a["khoi"]) == (20, 0.002, 0.0) and len(ph["threads-10-2"]["nguon"]) == 2
    assert a["uoc_usd"] == pytest.approx(20 * 0.002 * 1.3, abs=1e-4)      # 0,052 thay vì 0,754
    dp = a["du_phong"]
    assert dp["actor"] == A._ACTORS["threads"] and dp["mem"] == 1024
    assert dp["payload"] == {"mode": "user", "usernames": ten, "max_posts": 10}
    assert dp["limit"] == 200 and (dp["gia"], dp["khoi"]) == (0.0025, 0.08)
    assert dp["uoc_usd"] == pytest.approx((200 * 0.0025 + 0.08) * 1.3, abs=1e-4)
    assert ph["threads-30"]["payload"]["profiles"] == ["kol.x"]
    # Actor hồ sơ tính theo TÀI KHOẢN: số bài mỗi lần không đổi tiền.
    assert T._uoc_phan("threads", 1, 5) == T._uoc_phan("threads", 1, 30) == round(0.002 * 1.3, 4)


def test_doc_threads_ghep_nguon_va_chon_bai_kenh_nha(mo):
    items = _moi(MAU["nguoi_dung"])
    kq = T._doc_threads(items + [{"record_type": "profile", "username": "x"}])
    assert set(kq) == {"kenh_mau.vn"}
    tk = kq["kenh_mau.vn"]
    assert tk["ho_so"]["followers"] == 8423 and len(tk["bai"]) == 2
    n = _nguon(5, "threads", "https://www.threads.com/@Kenh_Mau.vn", loai="kenh_nha", so_bai=5)
    ra, loi = T.ghep_nguon("threads", kq, [n, _nguon(6, "threads", "khong_co")])
    assert len(ra[5]) == 2 and not ra[6] and "không lấy được bài" in loi[6]
    d, dt = ra[5][0]
    assert d["platform"] == "threads" and d["username"] == "kenh_mau.vn" and d["likes"] == 694
    assert d["link"].startswith("https://www.threads.com/@kenh_mau.vn/post/") and dt.tzinfo
    rows, thong_ke = T.chon_bai(DU_AN, {5: ra[5]}, {5: n}, time.monotonic() + 5)
    assert thong_ke["giu"] == 2 and {r["ly_do_giu"] for r in rows} == {"kenh_nha"}
    assert rows[0]["khoa"].startswith("threads:h") and rows[0]["nen_tang"] == "threads"
    assert rows[0]["hashtag"] == "BST MẪU 20/10" and rows[1]["hashtag"] == "quatang"


def test_chay_viec_du_phong_che_do_user_doc_dung_bai(mo):
    """Actor hồ sơ trả 0 hồ sơ cả lượt → phần dự phòng futurizerush "user" (cùng lượt) đọc bài như
    trước; nguồn KHÔNG bị đánh lỗi theo phần hồ sơ (17/10/2026)."""
    kho = GiaKho(nguon=[_nguon(1, "threads", "kenh_mau.vn", loai="kenh_nha")]).cai(mo)
    ap = GiaApify(mo, items=[], usd=0.0)
    mau = _moi(MAU["nguoi_dung"])
    goc = ap.run_actor

    def chay(actor, *a, **k):
        ap.items = mau if actor == A._ACTORS["threads"] else []
        return goc(actor, *a, **k)
    mo.setattr(A, "_run_actor", chay)
    phan = T.chia_phan(kho.nguon)
    v = GiaViec({p: {"phan": c} for p, c in phan.items()}, [1])
    st, cau = contextvars.copy_context().run(T.chay_viec, v)
    assert [g["actor"] for g in ap.gui] == [A._ACTORS["threads_ho_so"], A._ACTORS["threads"]]
    g = ap.gui[1]
    assert g["payload"]["mode"] == "user" and g["limit"] == 10 and g["nen_tang"] == "threads"
    # trần dự phòng = ước tính × 1,5 (ước tính gồm phí khởi động 0,08 của actor 4 GB)
    assert g["tran_usd"] == round((10 * 0.0025 + 0.08) * 1.3 * 1.5, 2)
    (_, _, kieu, rows), = kho.bai
    assert kieu == "theo_doi" and len(rows) == 2 and kho.danh_dau[0] == ([1], {})
    cac = v.d["nen_tang"]["threads"]["phan"]
    assert [x["id"] for x in cac] == ["threads-10", "threads-10-du-phong"]
    assert cac[0]["chuyen_du_phong"] == "threads-10-du-phong" and cac[1]["trang_thai"] == "xong"
    assert "chạy dự phòng futurizerush cho 1 tài khoản" in cau and st == "xong_mot_phan", cau


def test_tao_luot_giu_cho_ca_du_phong_threads(mo):
    """Soát 17/10/2026: phần hồ sơ Threads ước 0,0026 USD/tài khoản nhưng dự phòng futurizerush
    ~0,137 USD/lượt không nằm trong ước tính / giữ chỗ của việc. Nay giữ chỗ = trường hợp xấu
    nhất của phần (`giu_cho_phan`)."""
    import quet_lon
    import viec_nen
    kho = GiaKho(nguon=[_nguon(1, "threads", "kenh_mau.vn", loai="kenh_nha")]).cai(mo)
    mo.setattr(quet_lon, "tran_usd_nen", lambda: 20.0)
    mo.setattr(quet_lon, "ngan_sach", lambda tran: (8.0, {"con_lai": 9.0}, ""))
    mo.setattr(T, "uoc_do_phu", lambda *a, **k: 0.0)
    tao = []
    mo.setattr(viec_nen, "tao_viec", lambda *a, **k: tao.append(a) or {"ma_viec": "t1"})
    (ph,) = T.chia_phan(kho.nguon)["threads"]
    assert T.giu_cho_phan(ph) == ph["du_phong"]["uoc_usd"] == round((10 * 0.0025 + 0.08) * 1.3, 4)
    kq = T.tao_luot("hapas")
    _, _, _, uoc, ngan_sach, _ = tao[0]
    assert uoc["usd"] == 0.14 and ngan_sach == round(0.14 * 1.5, 2)
    assert "gồm tới 0,14 USD dự phòng nếu actor chính hỏng" in kq["cau"]
    # Phần không có dự phòng: giữ chỗ = ước tính như cũ.
    assert T.giu_cho_phan({"uoc_usd": 0.05}) == 0.05


def test_vong_phan_kep_ngan_sach_cua_viec_cho_du_phong_threads(mo):
    """Vòng phần kẹp theo ngân sách CỦA VIỆC (không chỉ phần còn của tháng): việc giữ 0,10 USD thì
    phần dự phòng futurizerush (ước 0,1365) bị bỏ CÓ lý do, nguồn không bị đánh lỗi; việc giữ
    0,30 thì dự phòng chạy với trần ≤ phần còn của việc."""
    kho = GiaKho(nguon=[_nguon(1, "threads", "kenh_mau.vn", loai="kenh_nha")]).cai(mo)
    ap = GiaApify(mo, items=[], usd=0.0)
    mau = _moi(MAU["nguoi_dung"])
    goc = ap.run_actor

    def chay(actor, *a, **k):
        ap.items = mau if actor == A._ACTORS["threads"] else []
        return goc(actor, *a, **k)
    mo.setattr(A, "_run_actor", chay)
    v = GiaViec({p: {"phan": c} for p, c in T.chia_phan(kho.nguon).items()}, [1])
    v.d["ngan_sach_usd"] = 0.1
    _, cau = contextvars.copy_context().run(T.chay_viec, v)
    assert [g["actor"] for g in ap.gui] == [A._ACTORS["threads_ho_so"]]
    assert ap.gui[0]["tran_usd"] == 0.1
    dp = v.d["nen_tang"]["threads"]["phan"][1]
    assert dp["id"] == "threads-10-du-phong" and dp["ma"] == "NGAN_SACH"
    assert dp["ly_do"].startswith("hết ngân sách của lượt (còn 0,10 USD") and "0,14 USD" in dp["ly_do"]
    assert "Threads: hết ngân sách của lượt" in cau and kho.danh_dau[0] == ([], {})
    kho = GiaKho(nguon=[_nguon(1, "threads", "kenh_mau.vn", loai="kenh_nha")]).cai(mo)
    ap.gui.clear()
    v = GiaViec({p: {"phan": c} for p, c in T.chia_phan(kho.nguon).items()}, [1])
    v.d["ngan_sach_usd"] = 0.3
    contextvars.copy_context().run(T.chay_viec, v)
    assert [g["actor"] for g in ap.gui] == [A._ACTORS["threads_ho_so"], A._ACTORS["threads"]]
    assert ap.gui[1]["tran_usd"] == round((10 * 0.0025 + 0.08) * 1.3 * 1.5, 2) <= 0.3
    assert kho.danh_dau[0] == ([1], {})


def test_chuan_dinh_danh_threads_tu_link():
    assert T._chuan_dinh_danh("threads", "https://www.threads.net/@Hapas.VN/?x=1") == "hapas.vn"
    assert T._chuan_dinh_danh("threads", "threads.com/@hapas.vn") == "hapas.vn"
    assert T._chuan_dinh_danh("threads", "@Hapas.vn") == "hapas.vn"


# ───────────────────────────── tìm theo từ khoá ─────────────────────────────
@pytest.mark.parametrize("so_bai, so_tu", [(15, 1), (5, 1), (40, 4), (1000, 4)])
def test_tu_khoa_threads_chi_tim_so_bai_chia_10(so_bai, so_tu):
    tu = ["hapas", "túi hapas", "yêu từ điều nhỏ nhất", "hahahapas"]
    q = T._tu_cho("threads", tu, 2, so_bai)
    assert q == tu[:so_tu] and q == CP.tu_gui("threads", tu, 2, so_bai)
    n = max(10, so_bai)
    assert T.uoc_tu_khoa_nen_tang("threads", so_bai, tu) == round((n * 0.0025 + 0.08) * 1.3, 4)
    # actor không dừng ở maxItems: tổng max_posts × số từ không vượt số bài ước tính
    assert len(q) * max(10, so_bai // len(q)) <= n


def test_tim_tu_khoa_threads_phieu_moc_de_xuat_va_tien(mo):
    kho = GiaKhoTk(mo)
    mo.setattr(T.K, "nguon_cua_du_an", lambda ma: [
        {"id": 9, "nen_tang": "threads", "dinh_danh": "nguoi_mau_b"}])
    goi = {}

    def tim(p):
        def f(q, limit, country, d_from, d_to, **k):
            goi[p] = (list(q), limit, (d_to - d_from).days)
            fn = A._KHI_CO_RUN.get()
            if fn:
                fn({"id": f"run-{p}"}, {})
            return A._chuan_threads(_moi(MAU["tim_kiem"])) if p == "threads" else []
        return f
    mo.setattr(A, "_FETCH", {p: tim(p) for p in T.TK_NEN_TANG})
    da = dict(DU_AN, tu_khoa=["hapas", "túi hapas", "yeutudieunhonhat"], tk_bat=True, tk_so_bai=15,
              cau_hinh={"tu_khoa": {"threads": {"bat": True}}})
    tk = _chay_tk(da)
    assert goi["threads"][0] == ["hapas"] and goi["threads"][1] == 15 and goi["threads"][2] >= 30
    assert any("tìm Threads: 1/3 từ khoá đầu" in x and "≥ 30" in x for x in tk["ghi_chu"])
    rows = {r["khoa"]: r for kieu, cac in kho.bai for r in cac}
    assert {r["tai_khoan"] for r in rows.values()} == {"nguoi_mau_a", "nguoi_mau_b"}   # c: không nhắc
    assert {r["tai_khoan"]: r["nguon_id"] for r in rows.values()} == {"nguoi_mau_a": None,
                                                                     "nguoi_mau_b": 9}
    f = tk["pheu"]["threads"]
    assert (f["ve"], f["cua_so"], f["khong_nhac"], f["giu"]) == (3, 3, 1, 2)
    assert any(c.startswith("phễu tìm Threads (xin 30 ngày") for c in T._cau_tk(tk))
    assert set(T.doc_moc_tk("hapas")) == {"threads"}
    # Run TikTok giả ở trên không mang tên actor TikTok API → sổ theo video về (0 bài = 0 USD).
    assert tk["usd"] == pytest.approx(3 * 0.0025 + 0.08)


def test_tim_tu_khoa_threads_0_bai_van_tru_phi_khoi_dong(mo):
    GiaKhoTk(mo)
    mo.setattr(A, "_FETCH", {p: (lambda *a, **k: []) for p in T.TK_NEN_TANG})
    tk = _chay_tk(dict(DU_AN, tk_bat=True, tk_so_bai=15, cau_hinh=BAT_TH))
    assert tk["usd"] == pytest.approx(0.08) and tk["pheu"]["threads"]["ve"] == 0
    assert T.doc_moc_tk("hapas") == {}, "0 bài không dời mốc"


# ───────────────────────────── bình luận Threads ─────────────────────────────
TH = "https://www.threads.com/@hapas.vn/post/DeBjCyXDzaz"


def _bai_th(so_bl=21, loai="kenh_nha"):
    return {"khoa": "threads:hmau", "nen_tang": "threads", "link": TH, "tai_khoan": "hapas.vn",
            "tac_gia": "HAPAS", "binh_luan": so_bl, "bl_lay_luc": None, "nguon_loai": loai}


def test_phan_binh_luan_threads_lo_20_bai_10_den_300_tra_loi():
    v = GiaViec({}, [])
    bai = [dict(_bai_th(), khoa=f"threads:h{i}", link=f"https://www.threads.com/@a/post/C{i}")
           for i in range(25)]
    T._tao_cac_phan_bl(v, bai, {"threads": 5})
    ph = v.d["nen_tang"]["binh_luan"]["phan"]
    assert [len(x["bai"]) for x in ph] == [20, 5]
    a = ph[0]
    assert a["actor"] == D._ACTORS["threads"] and a["mem"] == 1024 and a["khoi"] == 0.02
    assert a["payload"] == {"post_urls": [{"url": b["link"]} for b in bai[:20]],
                            "max_replies": 10, "include_nested_replies": False}
    assert a["limit"] == 20 * 10 + 20                    # + dòng bài gốc mỗi bài
    assert a["uoc_usd"] == pytest.approx((200 * 0.0025 + 0.02 + 20 * 0.0025) * 1.3, abs=1e-4)
    v2 = GiaViec({}, [])
    T._tao_cac_phan_bl(v2, [_bai_th(so_bl=900)], 0)     # cào hết: actor nhận tối đa 300
    assert v2.d["nen_tang"]["binh_luan"]["phan"][0]["payload"]["max_replies"] == 300


def test_lay_binh_luan_threads_ma_link_va_tra_loi_cua_thuong_hieu(mo, nhan_gia):
    nha = dict(MAU_BL[0], reply_id="MAUNHA1", author_username="hapas.vn",
               text_content="Cảm ơn bạn nha", reply_url="https://www.threads.com/@hapas.vn/post/MAUNHA1")
    kho = GiaKhoBl(mo, [_bai_th()])
    ap = GiaApify(mo, items=[*MAU_BL, nha], usd=0.03)
    da = dict(DU_AN, bl_bat=True, bl_so_bai=10, bl_moi_bai=0,
              cau_hinh={"binh_luan": {p: {"bat": p == "threads"}
                                      for p in ("youtube", "tiktok", "instagram", "facebook",
                                                "threads")}})
    tk = _lay_bl(GiaViec({}, []), da, 4, 5.0, time.monotonic() + 300)
    assert kho.hoi == [("hapas", ["threads"], 10)]
    assert ap.gui[0]["actor"] == D._ACTORS["threads"]
    _, _, rows, da_lay = kho.ghi[0]
    theo = {r["ma"]: r for r in rows}
    assert set(theo) == {"DeBjvdVmu9O", "DeBjxwuFF_5", "DeBjy_Nk3Bh", "DeBj4I4Ejdw", "MAUNHA1"}
    assert theo["DeBjvdVmu9O"]["link"] == "https://www.threads.com/@nguoi_0/post/DeBjvdVmu9O"
    assert theo["DeBjvdVmu9O"]["khoa_bai"] == "threads:hmau" and not theo["DeBjvdVmu9O"]["la_tra_loi"]
    assert theo["MAUNHA1"]["cua_thuong_hieu"] and theo["MAUNHA1"]["sac_thai"] is None
    assert da_lay == {"threads:hmau": (5, 21)} and tk["nha"] == 1


# ───────────────────────────── dashboard ─────────────────────────────
def test_dashboard_danh_sach_va_nhap_nguon_threads():
    assert "threads" in NL.NEN_TANG and NL.TEN_NEN_TANG["threads"] == "Threads"
    assert CS.TEN_NEN_TANG["threads"] == "Threads" and "threads" in CP.NEN_TANG
    for vao in ("https://www.threads.net/@Kenh.Mau/", "threads.com/@kenh.mau?igshid=x", "@Kenh.Mau",
                "kenh.mau"):
        assert NL.chuan_dinh_danh("threads", vao) == ("kenh.mau", "https://www.threads.com/@kenh.mau")
    for vao, chu in (("https://www.threads.com/@kenh.mau/post/ABC", "link bài"),
                     ("https://www.instagram.com/kenh.mau", "Instagram"),
                     ("tên có dấu cách", "Threads")):
        with pytest.raises(NL.LoiNhap, match=chu):
            NL.chuan_dinh_danh("threads", vao)
    # Mark đọc lại đúng định danh dashboard lưu
    assert T._chuan_dinh_danh("threads", NL.chuan_dinh_danh("threads", "@Kenh.Mau")[0]) == "kenh.mau"


def test_dashboard_bo_loc_nhan_threads():
    b = CS.doc_bo_loc({"nen_tang": "tiktok,threads,facebook,instagram,youtube",
                       "nguon": "threads:kenh.mau,tiktok:a, b,n:3"})
    assert b["nen_tang"] == ("facebook", "instagram", "threads", "tiktok", "youtube")
    assert b["nguon"] == ("n:3", "threads:kenh.mau", "tiktok:a, b")
    with pytest.raises(CS.LoiBoLoc):
        CS.doc_bo_loc({"nen_tang": "twitter"})


def test_dashboard_chi_phi_khop_mark_threads():
    assert CP.GIA == T._GIA and CP.START_COST == A._START_COST and A._START_COST["threads"] == 0.08
    assert CP.KHOI_NGUON == T._KHOI_NGUON and T._KHOI_NGUON["threads"] == 0.0
    assert CP.TK_GIA == T._TK_GIA and CP.TK_KHOI == T._TK_KHOI
    assert CP.BL_GIA == T._BL_GIA and CP.BL_KHOI_DONG == T._BL_KHOI_DONG
    assert T._TK_GIA["threads"] == A._UNIT_COST["threads"] == 0.0025
    assert T._GIA["threads"] == A.TH_HO_SO_GIA == 0.002          # nguồn: actor hồ sơ (17/10/2026)
    assert (CP.TH2_GIA, CP.TH2_SO_BAI, CP.TH2_MOI_TU, CP.TH2_LUOT) == (
        T.TH2_GIA, T.TH2_SO_BAI, T.TH2_MOI_TU, T.TH2_LUOT) and T.TH2_GIA == A.TH2_GIA
    assert T._TK_KHOI["threads"] == A._START_COST["threads"]
    assert T._BL_GIA["threads"] == D._GIA["threads"]
    assert T._BL_KHOI_DONG["threads"] == D._GIA_KHOI_DONG["threads"]
    assert (CP.TH_TOI_THIEU_BAI, CP.TH_TOI_DA_MOI_LUOT) == (T.TH_TOI_THIEU_BAI, T.TH_TOI_DA_MOI_LUOT)
    assert CP.MAC_DINH_TAT == T.MAC_DINH_TAT and set(CP.NEN_TANG) == set(T.TK_NEN_TANG)
    for so_nguon in (0, 1, 3, 25):
        for so_bai in (1, 5, 10, 30):
            assert CP.uoc_mot_luot("threads", so_nguon, so_bai) == T._uoc_phan("threads", so_nguon,
                                                                                so_bai)
    tu = ["hapas", "túi hapas", "yeutudieunhonhat"]
    for so_bai in (0, 5, 15, 30, 300):
        assert CP.uoc_tk_nen_tang("threads", so_bai, tu) == T.uoc_tu_khoa_nen_tang("threads",
                                                                                   so_bai, tu)
        assert CP.uoc_binh_luan_luot(so_bai, 20, "threads") == T.uoc_binh_luan(so_bai, 20,
                                                                                "threads")
    assert CP.uoc_tu_khoa_luot(15, tu) == T.uoc_tu_khoa(15, tu)
    nguon = [dict(_nguon(i, "threads", f"k{i}", so_bai=5 if i % 2 else 10), trang_thai="dang_theo_doi")
             for i in range(1, 26)] + [dict(_nguon(40, "tiktok", "t"), trang_thai="dang_theo_doi")]
    assert CP.nguon_moi_luot(nguon) == pytest.approx(sum(T.uoc_tinh(nguon).values()), abs=1e-4)
    for da in ({"tk_bat": True, "tk_so_bai": 15, "bl_bat": True, "bl_so_bai": 10, "cau_hinh": {}},
               {"tk_bat": True, "tk_so_bai": 15, "bl_bat": True, "bl_so_bai": 10, "cau_hinh": BAT_TH},
               {"tk_bat": False, "tk_so_bai": 15, "bl_bat": True, "bl_so_bai": 10,
                "cau_hinh": {"binh_luan": {"threads": {"bat": "x"}}}}):
        for nhom in ("tu_khoa", "binh_luan"):
            assert CP.cau_hinh(da, nhom, "threads") == T.cau_hinh(da, nhom, "threads")
    b = CP.bang_cau_hinh({"ten": "HAPAS", "tu_khoa": tu, "tk_bat": True, "tk_so_bai": 15,
                          "bl_bat": True, "bl_so_bai": 10, "cau_hinh": BAT_TH})
    assert b["tu_khoa"]["threads"]["so_tu_gui"] == 1 and b["tu_khoa"]["tiktok"]["so_tu_gui"] == 3
    # Đường 2 (17/10/2026) cộng vào ô Threads: 60 bài (20/từ × 3 từ) × 0,001 × 1,3.
    da_th = {"ten": "HAPAS", "tu_khoa": tu, "tk_bat": True, "tk_so_bai": 15, "cau_hinh": BAT_TH}
    assert b["tu_khoa"]["threads"]["uoc"] == round(
        T.uoc_tu_khoa_nen_tang("threads", 15, tu) + T.uoc_th2(T.cau_hinh_th2(da_th), tu), 4)
    assert T.uoc_th2(T.cau_hinh_th2(da_th), tu) == round(60 * 0.001 * 1.3, 4)
    hs = CP.hang_so_cho_trinh_duyet()
    # Báo & Web (16/10) xếp sau Threads; chỉ Threads mặc định tắt.
    assert list(hs["nen_tang"])[-2:] == ["threads", "web"] and hs["mac_dinh_tat"] == ("threads", "web")
    assert hs["th_toi_thieu_bai"] == 10


def test_du_bao_thang_threads_theo_tai_khoan_khong_phi_khoi_dong():
    ng = [{"id": i, "nen_tang": "threads", "dinh_danh": f"k{i}", "so_bai_moi_lan": 5,
           "chu_ky_ngay": 1} for i in range(21)]
    db = CP.du_bao(ng, 0, 50, None, datetime.datetime(2026, 10, 15, 12, tzinfo=_VN))
    (th,) = db["nen_tang"]
    # Actor hồ sơ (17/10/2026): 21 tài khoản × 0,002 × 1,3 mỗi ngày, không phí khởi động
    # (chế độ "user" cũ: 21 × 10 × 0,0025 × 1,3 + 2 lô × 0,08 × 1,3 ≈ 0,89 USD/ngày).
    assert th["thang_cau_hinh"] == pytest.approx(30 * 21 * 0.002 * 1.3)
    assert th["khoi_dong_con_lai"] == 0


# ───────────────────────────── schema ─────────────────────────────
def test_schema_cho_phep_threads_va_mo_ta_dung():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    khoi = re.search(r"CREATE TABLE IF NOT EXISTS nguon \((.*?)\n\);", sql, re.DOTALL).group(1)
    assert "'facebook', 'threads')" in khoi
    # DB đã tạo: đổi ràng buộc tên tự sinh, chạy lại được.
    i = sql.index("ALTER TABLE nguon DROP CONSTRAINT IF EXISTS nguon_nen_tang_check;")
    assert sql.index("ALTER TABLE nguon ADD CONSTRAINT nguon_nen_tang_check", i) > i
    for cot in ("nguon.nen_tang", "bai.nen_tang", "binh_luan.nen_tang", "de_xuat.nen_tang"):
        m = re.search(rf"COMMENT ON COLUMN {cot} IS '([^']*)';", sql)
        assert "threads" in m.group(1), cot
    dong = next(x for x in sql.splitlines() if x.startswith("COMMENT ON COLUMN du_an.cau_hinh IS"))
    assert "TRỪ threads" in dong
    bq = (GOC / "deploy" / "lang-nghe" / "bigquery.sql").read_text(encoding="utf-8")
    assert bq.count("ALTER COLUMN nen_tang SET OPTIONS") == 4      # + bai của Báo & Web
    assert "tiktok, instagram, youtube, facebook, threads (từ 16/10/2026).'" in bq


def test_trang_ngan_sach_co_dong_threads_tat_va_luu_duoc():
    """Dòng Threads trên trang Ngân sách: ô bật hiện TẮT khi chưa đặt (dù tk_bat của dự án bật),
    bật + lưu thì Mark thấy bật."""
    from test_dashboard_app import QL, dang_nhap, tao, thong_bao
    _, c, kho = tao()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15)
    csrf = dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert 'data-nt="threads"' in t and 'name="tk_threads_so_bai"' in t
    assert re.search(r'name="tk_threads_bat" value="1" aria-label="[^"]*">', t)      # không checked
    assert re.search(r'name="tk_tiktok_bat" value="1"[^>]*checked', t)
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "tk_threads_bat": "1",
                                                   "tk_threads_so_bai": "40"})
    assert "Đã lưu cấu hình thu thập" in thong_bao(c, r)
    ch = kho.du_an["hapas"]["cau_hinh"]
    assert ch["tu_khoa"]["threads"] == {"bat": True, "so_bai": 40}
    assert ch["binh_luan"]["threads"] == {"bat": False}
    assert T.cau_hinh(kho.du_an["hapas"], "tu_khoa", "threads")["bat"]
