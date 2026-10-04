"""Hồi quy cho 20 điểm rà soát 02/10/2026 (ba bản review độc lập của đợt 5 quét nền).

Mỗi bài mang số điểm (R1…R20) để đối chiếu với báo cáo. Không chạm mạng.
"""
from __future__ import annotations

import datetime
import json
import os
import threading
import time

import pytest

import apify_tool as A
import lsr_platform
import quet_lon as Q
import sheet_lon
import viec_nen as V
from test_apify_on_dinh import R
from test_viec_nen import (GiaLark, NOW, TU, DEN, _VGia, _item, _quet,  # noqa: F401
                           _viec_dang_chay, _viec_xong, nen)


def _rid_dang_chay(nen, n=40):
    actor = A._ACTORS["tiktok_fallback"]
    return nen.tao_run(actor, {}, [_item(actor, i) for i in range(n)], "RUNNING")


# ───────────────────────────── TIỀN ─────────────────────────────
def test_R1_huy_truoc_khi_dieu_phoi_van_huy_run_dang_song(nen):
    """Việc bị huỷ khi lượt con đang chạy (có run id): phải HUỶ run trên Apify, giữ item."""
    rid = _rid_dang_chay(nen)
    nen.trang_thai = "RUNNING"

    def sua(d, ph):
        ph.update(trang_thai="dang_chay", run_id=rid, tran_usd=4.5)
        d["huy"] = {"yeu_cau": True}
    ma = _viec_dang_chay(nen, sua)
    d = V.chay_ngay(ma)
    ph = d["nen_tang"]["tiktok"]["phan"][1]
    assert rid in nen.abort and nen.post_urls == []
    assert ph["so_item"] == 40 and d["trang_thai"] == "da_huy"


def test_R1_gan_han_chot_khong_chi_danh_dau_ma_huy_run(nen):
    rid = _rid_dang_chay(nen)
    nen.trang_thai = "RUNNING"

    def sua(d, ph):
        ph.update(trang_thai="dang_chay", run_id=rid, tran_usd=4.5)
        d["han_chot_ts"] = V._bay_gio() + 20          # < dự phòng + 30 giây
    ma = _viec_dang_chay(nen, sua)
    d = V.chay_ngay(ma)
    assert rid in nen.abort and nen.post_urls == []
    assert d["nen_tang"]["tiktok"]["phan"][1]["so_item"] == 40


def test_R1_dang_gui_khi_dong_thi_tim_run_truoc(nen):
    actor = A._ACTORS["tiktok_fallback"]
    hold = {}

    def sua(d, ph):
        hold["rid"] = nen.tao_run(actor, ph["payload"], [_item(actor, i) for i in range(7)],
                                  "RUNNING")
        ph.update(trang_thai="dang_gui", tran_usd=4.5,
                  moc_gui=(datetime.datetime.now(A._VN_TZ)
                           - datetime.timedelta(seconds=5)).isoformat())
        d["han_chot_ts"] = V._bay_gio() - 60          # khởi động lại SAU hạn
    nen.trang_thai = "RUNNING"
    ma = _viec_dang_chay(nen, sua)
    d = V.chay_ngay(ma)
    ph = d["nen_tang"]["tiktok"]["phan"][1]
    assert nen.post_urls == [] and hold["rid"] in nen.abort and ph["so_item"] == 7


class _DsRun:
    """Danh sách run của actor CÓ phân trang (desc, offset/limit)."""

    def __init__(self, runs, inputs, hong=False):
        self.runs, self.inputs, self.hong, self.hoi = runs, inputs, hong, []

    def get(self, url, params=None, **k):
        if url.endswith("/runs"):
            self.hoi.append(dict(params or {}))
            if self.hong:
                return R(500, {})
            o, n = int(params.get("offset") or 0), int(params.get("limit") or 1000)
            return R(200, {"data": {"items": self.runs[o:o + n]}})
        if "/records/INPUT" in url:
            kv = url.split("/key-value-stores/")[1].split("/")[0]
            return R(200, self.inputs[kv]) if kv in self.inputs else R(404, {})
        return R(404, {})


def _run(i, giay=1):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=giay)
    return {"id": f"r{i}", "startedAt": t.isoformat(), "defaultKeyValueStoreId": f"kv{i}"}


def test_R2_tim_run_vua_tao_xet_toi_50_run_co_phan_trang(monkeypatch):
    A._RUN_CUA_MINH.clear()
    runs = [_run(i) for i in range(40)]
    inputs = {f"kv{i}": {"khac": i} for i in range(40)}
    inputs["kv33"] = {"q": "cua_toi"}
    f = _DsRun(runs, inputs)
    monkeypatch.setattr(A.requests, "get", f.get)
    moc = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=10)
    run, kiem = A._tim_run_vua_tao_ex("a~b", {"q": "cua_toi"}, {}, moc, nghiem=True)
    assert run["id"] == "r33" and kiem and [h["offset"] for h in f.hoi] == [0, 25]
    A._RUN_CUA_MINH.clear()


def test_R2_hoi_hong_thi_viec_nen_khong_post_lai(nen, monkeypatch):
    actor = A._ACTORS["tiktok_fallback"]

    def sua(d, ph):
        ph.update(trang_thai="dang_gui", tran_usd=4.5,
                  moc_gui=(datetime.datetime.now(A._VN_TZ)
                           - datetime.timedelta(seconds=5)).isoformat())
    ma = _viec_dang_chay(nen, sua)
    goc = nen.get

    def get(url, params=None, **k):
        if url.endswith(f"/acts/{actor}/runs"):
            return R(503, {})
        return goc(url, params, **k)
    monkeypatch.setattr(A.requests, "get", get)
    d = V.chay_ngay(ma)
    ph = d["nen_tang"]["tiktok"]["phan"][1]
    assert nen.post_urls == [], "không kiểm được run cũ thì KHÔNG POST (trả tiền hai lần)"
    assert ph["ma"] == "KHONG_KIEM_DUOC" and "hai lần" in ph["ly_do"]


def test_R2_ung_vien_khong_doc_duoc_input_la_khong_kiem_duoc(monkeypatch):
    A._RUN_CUA_MINH.clear()
    f = _DsRun([_run(1)], {})                   # INPUT 404
    monkeypatch.setattr(A.requests, "get", f.get)
    moc = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=10)
    assert A._tim_run_vua_tao_ex("a~b", {"q": 1}, {}, moc, nghiem=True) == (None, False)
    assert A._tim_run_vua_tao_ex("a~b", {"q": 1}, {}, moc) == (None, True)
    f.hong = True
    assert A._tim_run_vua_tao_ex("a~b", {"q": 1}, {}, moc) == (None, False)


def test_R3_so_ngan_sach_dung_lai_tu_so_da_tinh(nen):
    kq = _quet(limit=1500)
    v = V.Viec(V.doc(kq["ma_viec"]))
    ph = v.d["nen_tang"]["tiktok"]["phan"]
    ph[0].update(trang_thai="xong", usd=None, usd_so=0.03)
    ph[1].update(trang_thai="mot_phan", usd=0.2, usd_so=4.1)
    ns = Q._so_ngan_sach(v)
    assert round(ns.da, 4) == 4.13


def test_R4_huy_trong_luc_cho_cho_thi_khong_post(nen, monkeypatch):
    ev = threading.Event()
    monkeypatch.setattr(A, "_han_muc_thang", lambda: ev.set() or None)  # huỷ chen vào
    tok = A._HUY.set(ev)
    try:
        with pytest.raises(A.LoiApify) as e:
            A._run_actor("a~b", {}, 5, deadline=A._dong_ho() + 200)
    finally:
        A._HUY.reset(tok)
    assert e.value.ma == "DA_HUY" and nen.post_urls == []


def test_R4_doc_tiep_run_khong_cho_cho_trong(nen):
    rid = nen.tao_run("a~b", {}, [{"i": 1}], "SUCCEEDED")
    giu = [A._CHO_APIFY.acquire(timeout=0) for _ in range(A._DONG_THOI_TOI_DA)]
    try:
        items, meta = A._doc_tiep_run(rid, 10, A._dong_ho() + 100, True, "a~b")
    finally:
        for x in giu:
            if x:
                A._CHO_APIFY.release()
    assert items == [{"i": 1}]


def test_R5_chot_chi_phi_huy_run_con_song_roi_tinh_lai_va_tinh_muon(nen):
    kq = _quet()
    v = V.Viec(V.doc(kq["ma_viec"]))
    rid = _rid_dang_chay(nen, 10)
    nen.trang_thai = "RUNNING"
    v.d["nen_tang"]["tiktok"]["phan"][1]["run_id"] = rid
    cp = v.chot_chi_phi(["hapas"], ["tiktok"], "")
    assert rid in nen.abort and cp["usd"] == 0.01 and cp["da_ghi_so"]
    # Run "báo tiền muộn": lần tính lại thấy nhiều hơn -> MỘT dòng điều chỉnh.
    nen.runs[rid]["usageTotalUsd"] = 0.05
    v.d["chi_phi"]["can_tinh_lai"] = True
    lech = v.tinh_lai_muon(cho_giay=0)
    assert lech == 0.04 and nen.so_chi_phi[-1]["thuc"]["usd"] == 0.04
    assert "điều chỉnh" in nen.so_chi_phi[-1]["queries"][0]
    assert v.tinh_lai_muon(cho_giay=0) == 0.0, "chỉ tính lại MỘT lần"


def test_R6_ngan_sach_thang_tru_phan_viec_khac_dang_giu(nen, monkeypatch):
    monkeypatch.setattr(A, "_han_muc_thang",
                        lambda: {"dung": 4.13, "tran": 5.0, "con_lai": 0.87, "reset": None})
    d = {"ma": "qkhac-00001", "agent_id": "AG-THU", "trang_thai": "dang_cao",
         "ngan_sach_usd": 0.40, "nen_tang": {"tiktok": {"phan": [
             {"trang_thai": "xong", "usd_so": 0.10}]}}, "tao_ts": 1}
    V.luu(d)
    ns, _, cau = Q.ngan_sach(5.0)
    assert ns == round(0.87 - 0.30 - 0.30, 2) and "đang giữ" in cau
    import scheduler
    scheduler.set_current_chat("oc_moi")
    r = V.tao_viec("social_listen", {"x": 1}, {}, {"usd": 0.5}, 0.5, con_lai_thang=0.87)
    assert r["tu_choi"] and r["vuot_ngan_sach"] and r["ngan_sach_con_usd"] == 0.27


def test_R7_giu_cho_trang_youtube_nguyen_tu():
    assert A._youtube_giu("v1", 60) == 60
    assert A._youtube_giu("v2", 60) == 20, "việc thứ hai chỉ còn phần chưa ai giữ (80−60)"
    assert A._youtube_con_trang(nen=True) == 0
    assert A._youtube_con_trang(nen=True, ma="v1") == 60
    tok = A._YT_MA.set("v1")
    try:
        A._youtube_dem(5)
    finally:
        A._YT_MA.reset(tok)
    assert A._youtube_doc()["giu"]["v1"] == 55 and A._youtube_da_dung() == 5
    assert A._youtube_tra("v1") == 55 and A._youtube_con_trang(nen=True) == 55


def test_R7_viec_nen_youtube_giu_cho_khi_tao(nen, monkeypatch):
    kq = _quet(platforms=["youtube"], limit=1500, chay_nen=True)
    assert A._youtube_doc()["giu"] == {kq["ma_viec"]: 30}
    monkeypatch.setattr(A, "_youtube_tim", lambda *a, toi_da_trang=None, **k: ([], toi_da_trang,
                                                                                False))
    V.chay_ngay(kq["ma_viec"])
    assert A._youtube_doc()["giu"] == {}, "việc kết thúc phải trả chỗ chưa dùng"


# ───────────────────────────── QUYỀN / KHỞI ĐỘNG LẠI ─────────────────────────────
def test_R8_mat_quyen_thi_dung_khong_luu_khong_post_khong_nhan(nen, monkeypatch):
    kq = _quet(limit=1500)
    assert V._lay_quyen()
    # Tiến trình khác giành quyền với số thế hệ lớn hơn ngay khi việc bắt đầu cào.
    goc = Q._chay_cac_phan

    def gianh(v, *a, **k):
        V._ghi_khoa_chu(V.the_cua_toi() + 7)
        return goc(v, *a, **k)
    monkeypatch.setattr(Q, "_chay_cac_phan", gianh)
    d = V.chay_ngay(kq["ma_viec"])
    assert nen.post_urls == [] and not nen.lark.tin()
    tren_dia = V.doc(kq["ma_viec"])
    assert tren_dia["trang_thai"] == "dang_cao" and not tren_dia["thong_bao"]["da_gui"]
    assert d["trang_thai"] == "dang_cao"


def test_R8_khoa_chu_theo_agent_va_so_the_he_tang(nen, monkeypatch):
    assert V._lay_quyen()
    t1 = V.the_cua_toi()
    assert "AG-THU" in V._khoa_chu().name
    V._QUYEN.clear()
    assert V._lay_quyen() and V.the_cua_toi() > t1
    # Agent khác dùng chung thư mục: khoá riêng, không chặn nhau.
    monkeypatch.setenv("LSR_AGENT_ID", "AG-KHAC")
    assert V._khoa_chu().name != f".chu-AG-THU.lock" and V._chu_khac() is None


def test_R9_huy_chen_giua_luc_doc_va_dang_ky_van_duoc_ton_trong(nen, monkeypatch):
    kq = _quet()
    goc = V.Viec.__init__

    def init(self, d):
        if not getattr(init, "da", False):
            init.da = True
            V.huy(kq["ma_viec"], chat="oc_nhom1", nguoi="")
        goc(self, d)
    monkeypatch.setattr(V.Viec, "__init__", init)
    d = V.chay_ngay(kq["ma_viec"])
    assert d["trang_thai"] == "da_huy" and nen.post_urls == []


def test_R10_luu_ban_chup_va_khong_mat_run_id(nen, monkeypatch):
    kq = _quet()
    v = V.Viec(V.doc(kq["ma_viec"]))
    thay = []
    goc = V.luu
    monkeypatch.setattr(V, "luu", lambda d: thay.append(d) or goc(d))
    v.luu()
    assert thay and thay[-1] is not v.d and thay[-1] == v.d
    # Ghi run id hỏng 3 lần -> run bị HUỶ ngay, không để chạy mồ côi.
    rid = nen.tao_run("a~b", {}, [], "RUNNING")
    tok = A._KHI_CO_RUN.set(lambda run, meta: (_ for _ in ()).throw(OSError("đĩa đầy")))
    try:
        with pytest.raises(A.LoiApify) as e:
            A._cho_run(dict(nen.runs[rid]), {}, "t", 5, {"actor": "a~b"}, 0,
                       lambda: 100, True)
    finally:
        A._KHI_CO_RUN.reset(tok)
    assert rid in nen.abort and e.value.meta["run_id_chua_luu"] == rid


def test_R11_lo_muon_sau_khi_viec_ket_thuc_khong_doi_trang_thai(nen):
    kq = _quet()
    v = V.Viec(V.doc(kq["ma_viec"]))
    v.d["trang_thai"] = "xong"
    ph = v.d["nen_tang"]["tiktok"]["phan"][1]
    truoc = dict(ph)
    muon = _rid_dang_chay(nen, 3)
    v.cap_nhat_phan(ph, trang_thai="dang_chay", run_id=muon)
    v.ghi_dong("tiktok", [({"link": "x"}, None)], "tiktok-1")
    assert ph == truoc and muon in v.d["run_muon"] and v.d["ghi_chu_muon"]
    assert muon in nen.abort and v.doc_dong("tiktok") == []
    assert muon in v.run_ids(), "run muộn vẫn được cộng tiền"


def test_R12_job_id_song_theo_luong_tra_loi_cham(monkeypatch):
    monkeypatch.setattr(lsr_platform, "_HAN_TRA_LOI", 0.05)
    thay, xong = [], threading.Event()

    def cham(hoi, chat_id=None, sender_open_id=None):
        time.sleep(0.2)
        thay.append(lsr_platform.job_cua_phien(chat_id))
        xong.set()
        return "ok"
    _, _, treo = lsr_platform._chay_co_han(cham, "hỏi", "web:p1", None, job_id=555)
    assert treo
    assert xong.wait(3) and thay == [555], "lượt chậm vẫn thấy đúng job id của nó"
    time.sleep(0.05)
    assert lsr_platform.job_cua_phien("web:p1") is None


# ───────────────────────────── DỮ LIỆU ─────────────────────────────
def test_R13_cache_phan_xu_luon_ap_ke_ca_khi_khong_goi_ai(nen):
    kq = _quet(limit=1500)
    v = V.Viec(V.doc(kq["ma_viec"]))
    rows = [({"kenh": f"k{i}", "text": f"hapas túi {i}", "views": 10,
              "link": f"https://www.tiktok.com/@a/video/{i}"}, NOW) for i in range(10)]
    v.ghi_dong("tiktok", rows, "tiktok-1")
    Q._cache_ghi(v, {Q._khoa_link(rows[0][0]): (False, "spam", "")})
    ket = Q._loc(v, dict(v.d["tham_so"]), A._parse_date(TU, end=False),
                 A._parse_date(DEN, end=True), False, [])
    assert ket["per"]["tiktok"]["giu"] == 9 and ket["phan_xu"]["dem"]["AI"]["loai"] == 1
    assert "đã lưu" in ket["phan_xu"]["trang_thai"]


def test_R13_R14_bang_doi_thi_ghi_lai_tu_dau_va_xoa_cot_thua(monkeypatch):
    lk = GiaLark()
    monkeypatch.setattr(A.lark, "call", lk.call)
    monkeypatch.setattr(sheet_lon, "_ngu", lambda s: None)
    monkeypatch.setattr(A, "_grant", lambda *a: True)
    v = _VGia()
    s = sheet_lon.SoSheet(v)
    s.dam_bao("T", "Tổng hợp", "")
    cu = [["a", "b", "c", "d"]] + [[i, i, i, "x"] for i in range(1500)]
    s.ghi_tab("TikTok", cu)
    s.s["tabs"]["TikTok"]["da_ghi"] = 1000            # giả như đang ghi dở
    lk.goi.clear()
    moi = [["a", "b", "c"]] + [[i, -i, i] for i in range(1200)]
    s.ghi_tab("TikTok", moi)
    ghi = lk.ghi()
    assert ghi[0][0].endswith("!A1:D1000"), "bảng khác -> ghi lại TỪ DÒNG 1, đủ 4 cột"
    vals = [b["valueRanges"][0]["values"] for m, p, b, q in lk.goi
            if p.endswith("values_batch_update")]
    assert all(len(r) == 4 for blk in vals for r in blk), "đệm tới cột rộng nhất từng ghi"
    assert sum(n for _, n in ghi) == 1501, "1201 dòng mới + 300 dòng thừa được xoá"


def test_R14_ban_so_bo_cung_so_cot_ban_cuoi():
    d = {"platform": "tiktok", "kenh": "k", "link": "l", "text": "t"}
    so_bo = Q._dong(d, NOW, "kw", 500) + ["chưa lọc", "sơ bộ", "chưa phân loại", "khách"]
    assert len(so_bo) == len(list(A._HEADER) + Q._COT_THEM)


def test_R15_phan_trang_dataset_khong_cat_cut_khong_trung(monkeypatch):
    du_lieu = [{"i": i} if i % 7 else {} for i in range(2500)]     # có item rỗng
    hoi = []

    def get(url, params=None, **k):
        hoi.append(dict(params))
        o, n = int(params.get("offset") or 0), int(params["limit"])
        return R(200, du_lieu[o:o + n])
    monkeypatch.setattr(A.requests, "get", get)
    out = A._lay_items({"defaultDatasetId": "d"}, 3000, {})
    assert [h.get("offset") for h in hoi] == [None, 1000, 2000]
    assert all("clean" not in h and h["skipHidden"] == 1 for h in hoi)
    assert len(out) == sum(1 for x in du_lieu if x) and len({x["i"] for x in out}) == len(out)


def test_R16_cau_phan_xu_cong_du_ca_loai_tru_va_chuyen_thi_truong():
    px = {"dem": {"AI": {"giu": 3, "loai": 2}, "AI (theo kênh)": {"giu": 1, "loai": 0},
                  "Luật": {"giu": 4, "loai": 1}}, "loai_tru": 5,
          "chuyen_thi_truong": {"TH": 2}, "trang_thai": "đã chạy"}
    c = Q._cau_phan_xu(px)
    assert "từ loại trừ 5" in c and "thị trường 2" in c


# ───────────────────────────── RIÊNG TƯ / BẢO MẬT ─────────────────────────────
def test_R17_nguoi_yeu_cau_chi_thay_viec_o_chat_rieng(nen):
    import scheduler
    kq = _quet()
    scheduler.set_current_chat("oc_nhom_khac")
    scheduler.set_current_chat_type("group")
    assert not V.tra()["tim_thay"]
    scheduler.set_current_chat("oc_rieng")
    scheduler.set_current_chat_type("p2p")
    assert V.tra()["viec"][0]["ma_viec"] == kq["ma_viec"]
    assert not V.huy()["ok"], "không mã: chỉ huỷ việc của chính chat này"
    assert V.huy(kq["ma_viec"])["ok"]
    scheduler.set_current_chat_type(None)


@pytest.mark.parametrize("vao, ra", [
    ("=HYPERLINK(\"http://x\",\"bấm\")", "'=HYPERLINK(\"http://x\",\"bấm\")"),
    ("+84 912 345 678", "'+84 912 345 678"),
    ("@SUM(A1)", "'@SUM(A1)"),
    ("  =1+1", "'  =1+1"),
    ("\t=cmd", "'\t=cmd"),
    ("\r=cmd", "'\r=cmd"),
    ("-2+3+cmd|' /C calc'!A0", "'-2+3+cmd|' /C calc'!A0"),
    ("-=1", "'-=1"),
    ("- gạch đầu dòng bình thường", "- gạch đầu dòng bình thường"),
    ("-15% hôm nay", "-15% hôm nay"),
    ("hapas = đẹp", "hapas = đẹp"),
    (123, 123),
])
def test_R18_chan_chen_cong_thuc(vao, ra):
    assert A._o_an_toan(vao) == ra


def test_R18_moi_bo_ghi_sheet_deu_qua_bo_loc(monkeypatch):
    lk = GiaLark()
    monkeypatch.setattr(A.lark, "call", lk.call)
    monkeypatch.setattr(sheet_lon, "_ngu", lambda s: None)
    monkeypatch.setattr(A, "_grant", lambda *a: True)
    A._write_values("t", "s", [["=1+1", "ok"]])
    import deep_dive_tool as D
    D._write("t", "s", [["@x"] + [""] * 9])
    s = sheet_lon.SoSheet(_VGia())
    s.dam_bao("T", "Tổng hợp", "")
    s.ghi_tab("TikTok", [["+cmd"]])
    vals = [b["valueRanges"][0]["values"][0][0] for m, p, b, q in lk.goi
            if p.endswith("values_batch_update")]
    assert vals == ["'=1+1", "'@x", "'+cmd"]
    import crawl_tool
    assert crawl_tool._bang_an_toan is A._bang_an_toan


def test_R19_don_dep_chi_xoa_viec_xong_cu(nen, monkeypatch):
    goc = V.thu_muc()
    now = V._bay_gio()

    def tao(ma, tt, tuoi_ngay, gui=True):
        V.luu({"ma": ma, "agent_id": "AG-THU", "trang_thai": tt, "tao_ts": now,
               "xong_ts": now - tuoi_ngay * 86400,
               "thong_bao": {"ket_qua": "x", "da_gui": gui}})
        (goc / ma).mkdir(parents=True, exist_ok=True)
        (goc / ma / "rows-tiktok.jsonl").write_text("x" * 2000, encoding="utf-8")
    tao("qcu00-00001", "xong", 30)
    tao("qmoi0-00002", "xong", 1)
    tao("qdang-00003", "dang_cao", 30)
    tao("qchua-00004", "xong", 30, gui=False)        # chưa nhắn được -> giữ
    kq = V.don_dep()
    assert kq["xoa"] == ["qcu00-00001"]
    assert not (goc / "qcu00-00001").exists() and V.doc("qcu00-00001") is None
    assert V.doc("qdang-00003") and V.doc("qchua-00004") and V.doc("qmoi0-00002")
    monkeypatch.setenv("SOCIAL_NEN_TOI_DA_MB", "10")
    monkeypatch.setattr(V, "_co_thu_muc", lambda f: 6 * 1024 * 1024)
    assert V.don_dep()["xoa"] == ["qmoi0-00002"], "vượt trần dung lượng: xoá việc xong cũ nhất"


def test_R20_gateway_va_web_mang_ma_khu_trung(monkeypatch):
    goi = []
    monkeypatch.setattr(lsr_platform, "_cau_hinh", lambda: {"platform": "p", "key": "k"})
    monkeypatch.setattr(lsr_platform, "_goi", lambda c, d, b=None, timeout=35:
                        goi.append((d, b)) or {})
    lsr_platform.gui_lark("oc_1", "kq", "cli", uuid="q1-kq")
    lsr_platform.bao_su_kien_job(9, "kq", ma_su_kien="q1-kq")
    assert goi[0][1]["uuid"] == "q1-kq" and goi[1][1]["data"]["id"] == "q1-kq"


@pytest.mark.parametrize("v", [" \t=1+1", "\xa0\t=1+1", "\u3000\t@SUM(1)", "  \t=1+1",
                               "\u200b=1+1", "\ufeff=1+1", "\u2060 +84 9", "\t hello"])
def test_R18b_khoang_trang_la_truoc_cong_thuc_van_bi_chan(v):
    """Review lần 2 (02/10/2026): khoảng trắng thường + tab, hoặc ký tự vô hình trước '='."""
    assert A._o_an_toan(v) == "'" + v


@pytest.mark.parametrize("v", ["- gạch đầu dòng", "-15% hôm nay", "  bình thường", "Tốt =))"])
def test_R18b_chu_thuong_giu_nguyen(v):
    assert A._o_an_toan(v) == v
