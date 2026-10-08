"""Bình luận Threads và Instagram trong social_deep_dive (04/10/2026).

Mẫu dữ liệu lấy từ output THẬT của bốn actor (chạy không đăng nhập ngày 04/10), đã làm
sạch tên/ID/nội dung — `mau_binh_luan_threads_ig.json`. Không bài nào gọi Apify, Lark hay
model thật.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

import apify_tool as A
import deep_dive_tool as D
from sheet_gia import LarkGia
from test_binh_luan_phan_tich import TabGia
import quet_lon

MAU = json.loads((Path(__file__).parent / "mau_binh_luan_threads_ig.json")
                 .read_text(encoding="utf-8"))
TH = "https://www.threads.com/@hapas.vn/post/DeBjCyXDzaz"
TH_NET = "https://www.threads.net/@hapas.vn/post/DeBjCyXDzaz?xmt=abc"
IG = "https://www.instagram.com/p/DHn78JLv9-U/"


def _model_gia(nhac: str) -> str:
    ra = {}
    for i, t in re.findall(r'<c i="(\d+)">(.*?)</c>', nhac):
        ra[i] = (["+", "SP"] if "đẹp" in t else ["-", "DV"] if "chậm" in t
                 else ["=", "GIA"] if "Giá" in t else ["=", "KHAC"])
    return json.dumps(ra)


class _Apify:
    """`_call` giả: theo actor trả mẫu thật; `hong` = actor nào ném lỗi (kèm meta run)."""

    def __init__(self):
        self.goi = []
        self.hong: dict = {}
        self.tra = {D._ACTORS["threads"]: MAU["futurizerush_threads"],
                    D._ACTORS["instagram"]: MAU["apify_instagram"],
                    D._ACTORS_DU_PHONG["threads"]: MAU["fetch_cat_threads"],
                    D._ACTORS_DU_PHONG["instagram"]: MAU["apidojo_instagram"]}

    def __call__(self, actor, payload, limit, mem=None, min_charge=0, tran_usd=None):
        self.goi.append({"actor": actor, "payload": payload, "limit": limit, "mem": mem,
                         "tran_usd": tran_usd})
        if actor in self.hong:
            ma, usd = self.hong[actor]
            meta = {"actor": actor, "run_id": "r1" if usd is not None else None, "usd": usd}
            so = A._SO_RUN.get()
            if so is not None:
                so.append(meta)
            raise A.LoiApify(ma, f"{actor} hỏng", meta)
        return [dict(x) for x in self.tra.get(actor, [])]


@pytest.fixture
def mt(monkeypatch):
    ap = _Apify()
    cp = []
    monkeypatch.setattr(D, "_call", ap)
    monkeypatch.setattr(D, "_cau_hinh", lambda: (300, 0.5))
    monkeypatch.setattr(A, "_cau_hinh_quet", lambda: {})
    monkeypatch.setattr(A, "_tran", lambda nen=None: (500, 0.37))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda actors, *a, **k: cp.append(actors) or {
        "usd": 0.1, "so_run": len(ap.goi), "cham_tran": 0, "dang_chay": 0})
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {})
    monkeypatch.setattr(D.chi_phi_tool, "ghi", lambda **k: {})
    monkeypatch.setattr(D.phan_loai, "_goi_model", _model_gia)
    gia = LarkGia()                     # Lark giả: sheet đi qua trinh_bay_sheet thật
    monkeypatch.setattr(A.lark, "call", gia.call)
    sheet = TabGia(gia, "Bình luận")
    monkeypatch.setattr(D, "_grant", lambda tok, oid: True)
    monkeypatch.setattr(D.memory_store, "get_current_sender", lambda: "ou_test")
    return ap, sheet, cp


# ───────────────────────── nhận link, ID bài ─────────────────────────
def test_nhan_link_threads_net_com_va_instagram():
    assert D._platform_of(TH) == D._platform_of(TH_NET) == "threads"
    assert D._platform_of(IG) == "instagram"
    assert D._id_bai(TH) == D._id_bai(TH_NET) == "threads:DeBjCyXDzaz"
    assert D._id_bai("https://www.threads.net/t/DeBjCyXDzaz") == "threads:DeBjCyXDzaz"
    for u in (IG, "https://instagram.com/reel/DHn78JLv9-U/?igsh=x",
              "https://www.instagram.com/reels/DHn78JLv9-U", "https://www.instagram.com/hapas/p/DHn78JLv9-U/"):
        assert D._id_bai(u) == "instagram:DHn78JLv9-U", u
    # Link TRẢ LỜI mang mã của chính trả lời, không phải của bài.
    assert D._id_bai("https://www.threads.com/@nguoi_0/post/DeBjvdVmu9O") != D._id_bai(TH)


# ───────────────────────── map từ output thật ─────────────────────────
def test_map_threads_bo_dong_bai_goc_nhung_van_dem_tien():
    rows, n_raw = D._map_threads(MAU["futurizerush_threads"])
    assert n_raw == 5 and len(rows) == 4            # 4 trả lời + 1 original_post bị tính tiền
    assert all(r["text"] != "Bài gốc của brand" for r in rows)
    r = rows[1]
    assert r["kenh"] == "nguoi_1" and r["likes"] == 32 and r["replies"] == 2
    assert r["thoi_gian"] == "2026-10-03 14:48" and r["tac_gia_thich"] == ""
    assert r["link"] == TH
    assert D._quy_ve_bai(r["_nguon"] + [r["link"]], [TH_NET]) == TH_NET


def test_map_instagram_tu_output_that():
    rows, n_raw = D._map_instagram(MAU["apify_instagram"])
    assert n_raw == len(rows) == 4
    assert rows[0]["kenh"] == "ig_0" and rows[0]["link"] == IG
    assert rows[0]["thoi_gian"] == "2025-04-18 18:22" and rows[0]["replies"] == 0
    other = "https://www.instagram.com/p/DHn78JLv9-U/?img_index=1"
    assert all(D._quy_ve_bai(r["_nguon"] + [r["link"]], [other, TH]) == other for r in rows)


def test_map_du_phong_tu_output_that():
    th, n = D._map_threads_du_phong(MAU["fetch_cat_threads"])
    assert n == len(th) == 3 and th[0]["kenh"] == "fc_0" and th[0]["link"] == TH
    assert th[0]["thoi_gian"] == ""                 # fetch_cat không trả createdAt khi chưa login
    ig, n = D._map_instagram_du_phong(MAU["apidojo_instagram"])
    assert n == len(ig) == 3 and ig[0]["kenh"] == "ad_0" and ig[0]["link"] == IG


def test_shape_la_thi_bao_khong_ghi_bua():
    with pytest.raises(RuntimeError, match="shape KHÔNG khớp"):
        D._map_threads([{"foo": 1}])
    with pytest.raises(RuntimeError, match="shape KHÔNG khớp"):
        D._map_instagram([{"foo": 1}])
    assert D._map_instagram([{"error": "no_items"}]) == ([], 1)


# ───────────────────────── chia lô, ước tính ─────────────────────────
def test_threads_10_den_300_tra_loi_20_bai_moi_luot_va_tinh_dong_bai_goc():
    us = [f"https://www.threads.com/@b/post/C{i:04d}" for i in range(25)]
    per, lo = D._chia_lo("threads", us, 50, 5.0)
    assert per == 50 and max(len(x) for x in lo) <= 20 and sum(map(len, lo)) == 25
    assert D._chia_lo("threads", us[:1], 5, 0.5)[0] == 10
    assert D._chia_lo("threads", us[:1], 900, 5.0)[0] == 300
    assert D._uoc_lo("threads", us[:2], 30) == pytest.approx(0.02 + 2 * 31 * 0.0025)
    assert D._uoc_lo("instagram", [IG], 20) == pytest.approx(20 * 0.0026)
    assert D._limit("threads", us[:2], 30) == 62 and D._limit("instagram", [IG], 20) == 20
    # Mỗi lô vẫn dưới 90% trần.
    for p, u in (("threads", us), ("instagram", [IG] * 7)):
        pc, cac = D._chia_lo(p, u, 50, 0.5)
        assert all(D._uoc_lo(p, x, pc) <= D._BIEN * 0.5 + 1e-9 for x in cac), p


def test_payload_dung_input_schema_actor():
    assert D._payload("threads", [TH], 3) == {
        "post_urls": [{"url": TH}], "max_replies": 10, "include_nested_replies": False}
    assert D._payload("instagram", [IG], 20) == {"directUrls": [IG], "resultsLimit": 20}
    assert D._payload_du_phong("threads", [TH], 7) == {
        "postUrls": [{"url": TH}], "maxRepliesPerThread": 7, "maxDepth": 1}
    assert D._payload_du_phong("instagram", [IG, IG], 7) == {
        "startUrls": [IG, IG], "maxItems": 14, "fetchReplies": False}


# ───────────────────────── chạy cả lượt ─────────────────────────
def test_threads_va_ig_ra_sheet_co_sac_thai_va_thong_ke(mt):
    ap, sheet, cp = mt
    kq = json.loads(D._handle({"post_urls": [TH_NET, IG], "max_comments": 30}))
    assert kq["success"] is True
    g = {x["actor"]: x for x in ap.goi}
    th = g[D._ACTORS["threads"]]
    assert th["payload"]["post_urls"] == [{"url": TH_NET}] and th["payload"]["max_replies"] == 30
    assert th["mem"] == 1024 and th["limit"] == 31 and 0 < th["tran_usd"] <= 0.5
    assert kq["per_url"][TH_NET] == {"platform": "threads", "status": "OK", "comments": 4}
    assert kq["per_url"][IG] == {"platform": "instagram", "status": "OK", "comments": 4}
    assert set(kq["thong_ke"]["theo_nen_tang"]) == {"threads", "instagram"}
    assert kq["thong_ke"]["da_phan_loai"] == kq["thong_ke"]["tong"] == 8
    tc = kq["thong_ke"]["sac_thai"]["Tích cực"]
    assert tc["so"] == 2 and tc["ti_le"] == 25.0
    assert sheet[0][3] == "Sắc thái" and {r[0] for r in sheet[1:]} == {"threads", "instagram"}
    assert all(r[3] in ("Tích cực", "Tiêu cực", "Trung lập") for r in sheet[1:])
    assert set(kq["gioi_han_nen_tang"]) == {"threads", "instagram"}
    assert "lồng nhau" in kq["note"] and "MỘT PHẦN" in kq["note"]
    assert sorted(cp[0]) == sorted([D._ACTORS["threads"], D._ACTORS["instagram"]])
    assert kq["uoc_tinh_chi_phi_usd"] == pytest.approx(0.02 + 31 * 0.0025 + 30 * 0.0026)


def test_tat_tren_console_thi_khong_boc(mt, monkeypatch):
    ap = mt[0]
    monkeypatch.setattr(A, "_cau_hinh_quet", lambda: {"bat_threads": 0})
    kq = json.loads(D._handle({"post_urls": [TH, IG]}))
    assert [x["actor"] for x in ap.goi] == [D._ACTORS["instagram"]]
    assert kq["per_url"][TH]["status"] == "ĐÃ TẮT" and "ĐÃ TẮT" in kq["note"]
    ap.goi.clear()
    kq = json.loads(D._handle({"post_urls": [TH]}))
    assert ap.goi == [] and "chủ agent đã tắt Threads" in kq["error"]


def test_tran_usd_rieng_cua_console_ha_tran_moi_luot(mt, monkeypatch):
    ap = mt[0]
    monkeypatch.setattr(A, "_cau_hinh_quet", lambda: {"tran_usd_instagram": 0.1})
    json.loads(D._handle({"post_urls": [IG], "max_comments": 20}))
    assert ap.goi[0]["tran_usd"] <= 0.1
    # Trần tool 2 USD nhưng trần riêng Threads 0,1 USD/lượt: số trả lời/bài tự hạ cho vừa
    # (0,9 × 0,1 − 0,02 − 0,0025 dòng gốc) / 0,0025 = 27.
    monkeypatch.setattr(A, "_cau_hinh_quet", lambda: {"tran_usd_threads": 0.1})
    monkeypatch.setattr(D, "_cau_hinh", lambda: (3000, 2.0))
    ap.goi.clear()
    kq = json.loads(D._handle({"post_urls": [TH], "max_comments": 300}))
    assert ap.goi[0]["tran_usd"] <= 0.1 and ap.goi[0]["payload"]["max_replies"] == 27
    assert kq["max_comments_thuc"] == {"threads": 27}


def test_apify_ghi_tien_cham_thi_chi_phi_theo_so_dong_da_tinh(mt, monkeypatch):
    """Smoke 04/10: Threads xong, Apify vẫn báo 0,02 (chỉ phí khởi động); thật 0,07."""
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 0.02, "so_run": 1, "cham_tran": 0, "dang_chay": 0})
    kq = json.loads(D._handle({"post_urls": [TH], "max_comments": 30}))
    assert kq["chi_phi_thuc_usd"] == pytest.approx(0.02 + 5 * 0.0025, abs=1e-3)
    assert "tính theo số dòng" in kq["chi_phi"]


# ───────────────────────── dự phòng trong phần trần còn lại ─────────────────────────
def test_nguon_chinh_hong_thi_du_phong_trong_phan_con_lai(mt):
    ap, sheet, cp = mt
    ap.hong[D._ACTORS["threads"]] = ("LOI", 0.03)
    kq = json.loads(D._handle({"post_urls": [TH], "max_comments": 30}))
    chinh, dp = ap.goi
    assert dp["actor"] == D._ACTORS_DU_PHONG["threads"]
    assert dp["tran_usd"] + 0.03 <= chinh["tran_usd"] + 1e-9
    assert dp["payload"]["maxRepliesPerThread"] <= 30
    v = kq["per_url"][TH]
    assert v["status"] == "OK" and v["comments"] == 3 and "DỰ PHÒNG" in v["nguon"]
    assert kq["dung_nguon_du_phong"] == ["threads"] and "DỰ PHÒNG" in kq["note"]
    assert D._ACTORS_DU_PHONG["threads"] in cp[0]


def test_ig_hong_ca_hai_nguon_thi_bao_loi_ca_hai(mt):
    ap = mt[0]
    ap.hong[D._ACTORS["instagram"]] = ("LOI", None)
    ap.hong[D._ACTORS_DU_PHONG["instagram"]] = ("LOI", None)
    kq = json.loads(D._handle({"post_urls": [IG]}))
    assert len(ap.goi) == 2
    e = kq["per_url"][IG]
    assert e["status"] == "LỖI" and "dự phòng" in e["error"] and kq["platforms_failed"] == ["instagram"]


@pytest.mark.parametrize("ma", ["QUA_GIO", "HET_TIEN_THANG", "NGHEN_DONG_THOI"])
def test_loi_ma_du_phong_cung_gap_thi_khong_chay(mt, ma):
    ap = mt[0]
    ap.hong[D._ACTORS["threads"]] = (ma, None)
    D._handle({"post_urls": [TH]})
    assert [g["actor"] for g in ap.goi] == [D._ACTORS["threads"]]


def test_nguon_chinh_tieu_gan_het_tran_thi_khong_chay_du_phong(mt):
    ap = mt[0]
    ap.hong[D._ACTORS["threads"]] = ("LOI", 0.2)
    kq = json.loads(D._handle({"post_urls": [TH], "max_comments": 30}))
    cap = ap.goi[0]["tran_usd"]
    assert cap - 0.2 < 0.1
    assert len(ap.goi) == 1 and "không đủ" in kq["per_url"][TH]["error"]


@pytest.mark.parametrize("p", ["threads", "instagram"])
def test_tran_du_phong_cong_tien_chinh_khong_vuot_tran_lo(p):
    for cap in (0.1, 0.13, 0.5, 1.0, 4.99):
        for i in range(0, 101):
            da = cap * i / 100
            tran, per = D._tran_du_phong(p, cap, da, 3, 50)
            assert da + tran <= cap + 1e-9
            if per:
                assert tran >= A._TRAN_USD_KHOANG[0] and 1 <= per <= 50
                kd, bl, bai = D._GIA_DU_PHONG[p]
                assert kd + 3 * (bai + per * bl) <= D._BIEN * tran + 1e-9


# ───────────────────────── việc nền ─────────────────────────
def test_viec_nen_threads_ghim_ram_doc_dong_goc_va_chuan_hoa():
    nt = D._ke_hoach_nen({"threads": (30, [[TH]]), "instagram": (20, [[IG]])}, 5.0)
    ph = nt["threads"]["phan"][0]
    assert ph["mem"] == 1024 and ph["limit"] == 31 and ph["gia"] == 0.0025
    assert ph["payload"]["post_urls"] == [{"url": TH}]
    assert "mem" not in nt["instagram"]["phan"][0]
    rows = D._chuan_nen("threads", ph, MAU["futurizerush_threads"])
    assert len(rows) == 4 and all(c["bai"] == TH and c["platform"] == "threads"
                                  for c, _ in rows)
    for actor in (D._ACTORS["threads"], D._ACTORS["instagram"]):
        assert actor in quet_lon._TOC_HAT_GIONG


def test_loi_dan_khong_con_noi_chua_boc_duoc():
    d = D.SCHEMA["description"]
    assert "Threads" in d and "Instagram" in d and "CHƯA hỗ trợ Instagram" not in d
    assert "gioi_han_nen_tang" in d and "DỰ PHÒNG" in d
    assert not math.isnan(D._GIA["threads"])
