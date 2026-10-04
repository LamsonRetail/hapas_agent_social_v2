"""Canh tool `tiktok_top_ads` (tiktok_ads_tool.py): Top Ads TikTok Creative Center.

Dữ liệu giả giữ đúng hình "Sample output" trong README của hai actor (04/10/2026):
azzouzana (chính) trả `adTitle`/`brandName`/`ctr`/`costScore`/`videoUrl720p`/
`landingPageUrl`/`detailUrl`; lexis (dự phòng) trả `title`/`cost`/`videoUrls`/
`landingPage`/`industryKey`, không có `detailUrl`.
"""
from __future__ import annotations

import json

import pytest

import apify_tool as A
import lsr_policy
import tiktok_ads_tool as T

AZZ = [
    {"adId": "7644097429029437458", "adTitle": "=HYPERLINK(\"http://x\") Túi da mới",
     "brandName": "Brand A", "ctr": 0.12, "likes": 48200, "costScore": 2,
     "industryName": "Bags", "objectiveKey": "3", "isSparkAd": True,
     "videoUrl720p": "https://v/720.mp4", "periodDays": 30, "rank": 1,
     "detailUrl": "https://ads.tiktok.com/business/creativecenter/topads/7644097429029437458/pc/en",
     "landingPageUrl": "https://brand-a.vn/tui", "ctrTier": "top_10%"},
    {"adId": "2", "adTitle": "Ví nhỏ xinh", "brandName": "Brand A", "ctr": 0.08,
     "likes": 900, "costScore": 1, "industryName": "Bags",
     "objectiveKey": "campaign_objective_product_sales", "videoUrl540p": "https://v/540.mp4",
     "periodDays": 30, "rank": 2},
    {"adId": "3", "adTitle": "Balo đi học", "brandName": "", "ctr": 0.05, "likes": 10,
     "industryName": "Bags", "periodDays": 30, "rank": 3},
]
LEXIS = [
    {"id": "7638635028650033160", "title": "Áo khoác mùa đông", "brandName": "Brand B",
     "countryCodes": ["VN"], "landingPage": "https://b.vn", "industryKey": "label_22104000000",
     "objectiveKey": "campaign_objective_conversion", "ctr": 0.5, "cost": 1, "likes": 360,
     "videoUrls": {"720p": "https://v/lexis.mp4"}},
]


@pytest.fixture
def gia(monkeypatch):
    """Giả `_call` (ghi lại actor, payload, limit, nen_tang) + sheet + sổ chi phí."""
    goi: list = []
    ket = {"chinh": AZZ, "du_phong": LEXIS}
    so_ghi: list = []
    dong: list = []

    def call(actor, payload, limit, mem=None, min_charge=0, tran_usd=None, *, nen_tang=None):
        goi.append({"actor": actor, "payload": payload, "limit": limit,
                    "nen_tang": nen_tang, "tran_usd": tran_usd,
                    "han": A._HAN_CHOT.get(), "so": A._SO_RUN.get()})
        r = ket["chinh"] if actor == T.ACTOR_CHINH else ket["du_phong"]
        if isinstance(r, Exception):
            raise r
        so = A._SO_RUN.get()
        if so is not None:
            so.append({"status": "SUCCEEDED", "statusMessage": ket.get("msg", "")})
        return list(r)[:limit]

    monkeypatch.setattr(A, "_call", call)
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (500, 1.0, True))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda actors, tu, est: {
        "usd": 0.06, "so_run": len(actors), "cham_tran": 0, "dang_chay": 0, "_actors": actors})
    monkeypatch.setattr(T.chi_phi_tool, "ghi", lambda **k: so_ghi.append(k) or {})
    monkeypatch.setattr(A, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(A, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(A.lark, "call", lambda *a, **k: dong.append(k.get("body")) or {})
    monkeypatch.setattr(T.memory_store, "get_current_sender", lambda: None)
    monkeypatch.setattr(A, "_han_muc_thang", lambda: {"con_lai": 3.2})
    return {"goi": goi, "ket": ket, "so_ghi": so_ghi, "dong": dong}


def chay(**args) -> dict:
    return json.loads(T._handle(args))


def _o(gia) -> list[list]:
    return gia["dong"][0]["valueRanges"][0]["values"]


# ───────────────────────────── đầu vào ─────────────────────────────
def test_payload_actor_chinh_theo_tu_khoa_nganh_ky_sap_xep(gia):
    chay(tu_khoa="  túi   da ", nganh="túi xách", ky_ngay="7", sap_xep="like",
         muc_tieu="chuyen_doi", ngon_ngu="vi", so_ads=15)
    g = gia["goi"][0]
    assert g["actor"] == T.ACTOR_CHINH
    assert g["payload"] == {"countryCode": "VN", "period": "7", "orderBy": "like",
                            "maxItems": 15, "extractDetails": True, "keyword": "túi da",
                            "industry": "Bags", "objective": "campaign_objective_conversion",
                            "adLanguage": "vi"}
    assert g["limit"] == 15


def test_mac_dinh_30_ngay_xep_ctr_20_ads_khong_loc(gia):
    chay()
    p = gia["goi"][0]["payload"]
    assert p == {"countryCode": "VN", "period": "30", "orderBy": "ctr", "maxItems": 20,
                 "extractDetails": True}


def test_gia_tri_la_bi_bo_khong_gui_bua_cho_actor(gia):
    chay(ky_ngay="90", sap_xep="??", muc_tieu="x", ngon_ngu="klingon", chi_tiet="false")
    p = gia["goi"][0]["payload"]
    assert p["period"] == "30" and p["orderBy"] == "ctr" and p["extractDetails"] is False
    assert "objective" not in p and "adLanguage" not in p


def test_nganh_khong_nhan_ra_thi_bao_khong_chay(gia):
    kq = chay(nganh="vũ trụ học")
    assert "error" in kq and "Chưa nhận ra ngành" in kq["error"]
    assert not gia["goi"]


def test_vung_khong_ho_tro(gia):
    assert "error" in chay(country="ZZ") and not gia["goi"]


# ───────────────────────────── trần + sổ chi phí ─────────────────────────────
def test_moi_luot_di_qua_call_voi_tran_tiktok_va_han_chot(gia):
    chay(nganh="thời trang")
    g = gia["goi"][0]
    assert g["nen_tang"] == "tiktok", "phải chịu trần riêng TikTok trên console"
    assert g["tran_usd"] is None, "không tự đặt trần riêng, để console quyết"
    assert g["han"] is not None and g["so"] is not None, "thiếu hạn chót / sổ run"


def test_so_ads_bi_kep_theo_tran_bai_va_tran_usd(gia, monkeypatch):
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (500, 0.1, True))
    kq = chay(so_ads=200)
    # 0,9 × 0,1 USD / 0,003 USD mỗi ad = 30 ads.
    assert gia["goi"][0]["limit"] == 30 and kq["so_ads_xin"] == 30
    assert any("trần TikTok" in c for c in kq["canh_bao"])
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (12, 5.0, True))
    chay(so_ads=200)
    assert gia["goi"][-1]["limit"] == 12


def test_tiktok_bi_tat_tren_console_thi_khong_chay(gia, monkeypatch):
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (500, 1.0, False))
    kq = chay(nganh="túi")
    assert "error" in kq and "tắt" in kq["error"] and not gia["goi"]


def test_ghi_so_chi_phi_dung_actor_va_nen_tang(gia):
    kq = chay(nganh="túi xách")
    s = gia["so_ghi"][0]
    assert s["platforms"] == ["tiktok"] and s["date_range"] == "30 ngày gần nhất"
    assert s["thuc"]["_actors"] == [T.ACTOR_CHINH]
    assert s["est"] == pytest.approx(20 * 0.003)
    assert kq["chi_phi_thuc_usd"] == 0.06 and "0,06 USD" in kq["chi_phi"]


def test_chi_uoc_tinh_khong_chay_khong_ghi_so(gia):
    kq = chay(nganh="túi xách", so_ads=20, chi_uoc_tinh=True)
    assert kq["da_chay"] is False and not gia["goi"] and not gia["so_ghi"]
    assert kq["uoc_tinh_chi_phi_usd"] == pytest.approx(0.06)
    assert kq["uoc_tinh_toi_da_usd"] == pytest.approx(0.06 + 0.0025 + 20 * 0.004, abs=1e-3)
    assert "Chạy nhé?" in kq["note"] and kq["vuot_ngan_sach"] is False
    assert "ngành Túi xách" in kq["pham_vi"]


def test_chi_uoc_tinh_bao_thieu_ngan_sach_thang(gia, monkeypatch):
    monkeypatch.setattr(A, "_han_muc_thang", lambda: {"con_lai": 0.01})
    kq = chay(chi_uoc_tinh=True)
    assert kq["vuot_ngan_sach"] is True


def test_dung_call_that_thi_tran_usd_tiktok_len_toi_apify(monkeypatch):
    """Không giả `_call`: URL gửi Apify phải mang trần USD RIÊNG của TikTok."""
    monkeypatch.setattr(lsr_policy, "cau_hinh_tool", lambda tool: {
        "tran_usd": 2.0, "tran_usd_tiktok": 0.4} if tool == "social_listen" else {})
    monkeypatch.setattr(A, "_han_muc_thang", lambda: None)
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    url: list = []

    class _Post:
        status_code = 200

        def json(self):
            return AZZ

    monkeypatch.setattr(A.requests, "post", lambda u, **k: url.append(u) or _Post())
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(T.chi_phi_tool, "ghi", lambda **k: {})
    monkeypatch.setattr(A, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(A, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(A, "_write_values", lambda *a, **k: None)
    monkeypatch.setattr(T.memory_store, "get_current_sender", lambda: None)
    kq = json.loads(T._handle({"nganh": "túi"}))
    assert kq["tom_tat"]["so_ads"] == 3
    assert len(url) == 1 and "azzouzana~tiktok-creative-center-top-ads-scraper" in url[0]
    assert "maxTotalChargeUsd=0.4" in url[0], url[0]


# ───────────────────────────── sheet + tóm tắt ─────────────────────────────
def test_dong_sheet_du_cot_va_chan_cong_thuc(gia):
    kq = chay(nganh="túi xách")
    o = _o(gia)
    assert o[0] == T._HEADER
    d = o[1]
    assert d[:9] == [1, "'=HYPERLINK(\"http://x\") Túi da mới", "Brand A", "Bags", "Chuyển đổi",
                     "top 10% (điểm 0.12)", 48200, "mức 2", "30 ngày"]
    assert d[9:] == ["https://v/720.mp4", "https://brand-a.vn/tui", AZZ[0]["detailUrl"],
                     "azzouzana"]
    assert o[2][4] == "Bán sản phẩm" and o[2][9] == "https://v/540.mp4"
    assert o[2][5] == "điểm 0.08", "không có hạng thì ghi điểm"
    assert kq["sheet_url"] == "https://sheet"


def test_tom_tat_dem_cho_model(gia):
    kq = chay(nganh="túi xách")
    t = kq["tom_tat"]
    assert t["so_ads"] == 3 and t["so_brand"] == 1 and t["khong_ro_brand"] == 1
    assert t["brand_nhieu_ads_nhat"] == [{"brand": "Brand A", "so_ads": 2}]
    assert t["theo_nganh"] == {"Bags": 3}
    assert t["so_spark_ads"] == 1 and t["so_co_landing_page"] == 1
    assert t["so_co_link_video"] == 2
    assert len(kq["top"]) == 3 and kq["top"][0]["brand"] == "Brand A"
    assert "không phải mọi ad" in kq["note"] and "24–48 giờ" in kq["note"]


def test_khong_co_ad_nao_thi_khong_tao_sheet(gia):
    gia["ket"]["chinh"] = []
    kq = chay(tu_khoa="xyz")
    assert kq["tom_tat"]["so_ads"] == 0 and kq["sheet_url"] is None
    assert len(gia["goi"]) == 1, "rỗng bình thường thì KHÔNG chạy dự phòng"
    assert "Không có ad nào" in kq["note"]


# ───────────────────────────── dự phòng ─────────────────────────────
def test_nguon_chinh_hong_thi_chay_lexis(gia):
    gia["ket"]["chinh"] = A.LoiApify("LOI", "Run kết thúc FAILED.")
    kq = chay(nganh="túi xách", so_ads=10)
    assert [g["actor"] for g in gia["goi"]] == [T.ACTOR_CHINH, T.ACTOR_DU_PHONG]
    p = gia["goi"][1]["payload"]
    assert p["country"] == ["VN"] and p["industry"] == ["22"] and p["maxItems"] == 10
    assert "keyword" not in p and "region=VN" in p["startUrls"][0]["url"]
    assert gia["goi"][1]["nen_tang"] == "tiktok"
    assert "DỰ PHÒNG" in kq["nguon"] and "LOI" in kq["loi"]["nguon_chinh"]
    assert kq["success"] is True
    d = _o(gia)[1]
    assert d[3] == "Apparel & Accessories", "lexis chỉ có industryKey → tên ngành cha"
    assert d[9] == "https://v/lexis.mp4" and d[10] == "https://b.vn"
    assert d[11].startswith("https://ads.tiktok.com/business/creativecenter/topads/76386")
    assert d[12] == "lexis-solutions"
    assert gia["so_ghi"][0]["thuc"]["_actors"] == [T.ACTOR_CHINH, T.ACTOR_DU_PHONG]
    assert any("ngành cha" in c for c in kq["canh_bao"])


def test_du_phong_dung_tu_khoa_va_ma_muc_tieu(gia):
    gia["ket"]["chinh"] = RuntimeError("boom")
    chay(tu_khoa="charles", muc_tieu="tiep_can", ngon_ngu="vi")
    p = gia["goi"][1]["payload"]
    assert p["keyword"] == "charles" and "startUrls" not in p
    assert p["objective"] == ["5"] and p["adLanguage"] == ["vi"]


def test_rong_kem_bao_gioi_han_goi_thi_chay_du_phong(gia):
    gia["ket"]["chinh"], gia["ket"]["msg"] = [], "Free tier: daily run limit reached"
    kq = chay()
    assert len(gia["goi"]) == 2 and kq["tom_tat"]["so_ads"] == 1


@pytest.mark.parametrize("ma", ["HET_TIEN_THANG", "NGHEN_DONG_THOI", "DA_HUY"])
def test_loi_dung_chung_thi_khong_chay_du_phong(gia, ma):
    gia["ket"]["chinh"] = A.LoiApify(ma, "x")
    kq = chay()
    assert len(gia["goi"]) == 1 and "error" in kq and ma in kq["error"]


def test_ca_hai_nguon_hong_thi_bao_loi_ro(gia):
    gia["ket"]["chinh"] = A.LoiApify("LOI", "chính hỏng")
    gia["ket"]["du_phong"] = A.LoiApify("QUA_GIO", "dự phòng chậm")
    kq = chay()
    assert "error" in kq and "nguon_chinh" in kq["error"] and "du_phong" in kq["error"]


def test_loi_khong_lo_token(gia, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "apify_api_BIMATxyz123")
    gia["ket"]["chinh"] = RuntimeError("bad url ?token=apify_api_BIMATxyz123")
    gia["ket"]["du_phong"] = RuntimeError("again apify_api_BIMATxyz123")
    kq = chay()
    assert "BIMATxyz123" not in json.dumps(kq, ensure_ascii=False)


# ───────────────────────────── quản trị ─────────────────────────────
def test_policy_can_write_data_va_theo_cong_tac_quet_mang_xa_hoi():
    assert lsr_policy._MUTATING_EXACT["tiktok_top_ads"] == "write_data"
    assert "tiktok_top_ads" not in lsr_policy._SAFE_EXACT, "tool tốn tiền, ghi sheet"
    q, nl = dict(lsr_policy._nho), dict(lsr_policy._nho_nl)
    try:
        import time
        gio = time.time()
        lsr_policy._nho.update(quyen={"reply", "write_data"}, luc=gio)
        lsr_policy._nho_nl.update(bat={"social_listen"}, luc=gio)
        assert lsr_policy.decide("tiktok_top_ads", {}).allowed
        lsr_policy._nho_nl.update(bat={"soi_san"}, luc=gio)
        d = lsr_policy.decide("tiktok_top_ads", {})
        assert not d.allowed and "social_listen" in d.reason
        lsr_policy._nho.update(quyen={"reply"}, luc=gio)
        lsr_policy._nho_nl.update(bat={"social_listen"}, luc=gio)
        assert not lsr_policy.decide("tiktok_top_ads", {}).allowed, "công tắc không nới hợp đồng"
    finally:
        lsr_policy._nho.clear(); lsr_policy._nho.update(q)
        lsr_policy._nho_nl.clear(); lsr_policy._nho_nl.update(nl)


def test_prompt_ke_tool_va_luat_hoi_truoc():
    import brain
    assert "tiktok_top_ads" in brain._TOOL_CAN_XET
    assert "`tiktok_top_ads`" in brain._TOOLING_NOTE.split("TOOL TỐN TIỀN")[1][:200]
    assert "Chạy nhé?" in T.SCHEMA["description"] and "chi_uoc_tinh" in T.SCHEMA["description"]
