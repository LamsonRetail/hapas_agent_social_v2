"""tiktok_top_ads → lớp trình bày chung (trinh_bay_sheet), Lark GIẢ (tests/sheet_gia).

Danh sách ads đối thủ: Tổng quan = cỡ mẫu + phân bố theo cột có sẵn (Ngành/Mục tiêu/Brand)
+ top theo Likes + ghi chú/cảnh báo; tab Dữ liệu; tab Dữ liệu gốc (actor trả nhiều trường
hơn tool chọn). CTR của actor là ĐIỂM tương đối → giữ dạng chữ, không thành %.
"""
from __future__ import annotations

import json

import apify_tool as A
import tiktok_ads_tool as T
from test_tiktok_top_ads import AZZ, AZZ_THAT, MSG_GOI_FREE, chay, gia  # noqa: F401


def _fmt(lark, tab, cot, dong):
    st = [s for s in lark.kieu_o(tab, cot, dong) if "formatter" in s]
    return st[-1]["formatter"] if st else None


def test_tab_va_kieu_cot(gia):
    kq = chay(nganh="túi xách")
    lark = gia["lark"]
    assert lark.tab_ten() == ["Tổng quan", "Dữ liệu", "Dữ liệu gốc"]
    o = lark.o("Dữ liệu")
    assert o[1][5] == "top 10% (điểm 0.12)", "CTR là điểm tương đối — giữ chữ, không thành %"
    assert _fmt(lark, "Dữ liệu", 6, 2) is None, "cột CTR không có định dạng %"
    assert o[1][6] == 48200 and _fmt(lark, "Dữ liệu", 7, 2) == "#,##0"
    assert _fmt(lark, "Dữ liệu", 1, 2) == "#,##0"
    assert lark.tab("Dữ liệu")["frozen"] == 1
    sid = lark.tab("Dữ liệu")["sheet_id"]
    assert [b["range"] for p, b in lark.loc() if f"/{sid}/" in p] == [f"{sid}!A1:M4"]
    assert any(s.get("backColor") == "#1F3864" for s in lark.kieu_o("Dữ liệu", 1, 1))
    assert kq["day_du"] is True and "Đã ghi đủ" in kq["kiem_ghi"]


def test_tong_quan_mau_phan_bo_top(gia):
    kq = chay(nganh="túi xách")
    o = gia["lark"].o("Tổng quan")
    assert o[0][0] == kq["title"]
    assert "TikTok Creative Center" in o[1][0] and "30 ngày" in o[1][0]
    so = {r[0]: r[1] for r in o if len(r) > 1 and isinstance(r[0], str)}
    assert so["Số ads trong mẫu"] == kq["tom_tat"]["so_ads"] == 3
    assert so["Ads không rõ brand"] == kq["tom_tat"]["khong_ro_brand"] == 1
    chu = " ".join(str(c) for r in o for c in r)
    assert "THEO NGÀNH" in chu and "THEO MỤC TIÊU" in chu and "THEO BRAND" in chu
    assert "TOP 5 THEO LIKES" in chu
    assert "không phải mọi ad brand đang chạy" in chu and "ĐIỂM xếp hạng tương đối" in chu
    assert so["Bags"] == 3


def test_du_lieu_goc_moi_truong_actor_khong_lot_ra_model(gia):
    kq = chay(nganh="túi xách")
    goc = gia["lark"].o("Dữ liệu gốc")
    assert "adId" in goc[0] and "ctrTier" in goc[0] and "isSparkAd" in goc[0]
    j = goc[0].index("adId")
    assert goc[1][j] == "7644097429029437458", "mã ad dài giữ dạng chữ"
    assert _fmt(gia["lark"], "Dữ liệu gốc", j + 1, 2) == "@"
    assert len(goc) == 1 + 3
    assert "_goc" not in json.dumps(kq, ensure_ascii=False)
    assert "ctrTier" not in json.dumps(kq, ensure_ascii=False)


def test_thieu_ads_noi_ro_o_tong_quan(gia):
    gia["ket"]["chinh"], gia["ket"]["msg"] = AZZ_THAT, MSG_GOI_FREE
    chay(nganh="thời trang", so_ads=10)
    chu = " ".join(str(c) for r in gia["lark"].o("Tổng quan") for c in r)
    assert "Sheet có 3/10 ads đã xin — thiếu 7 ads" in chu and "gói Free" in chu


def test_cap_quyen_sau_cung_va_trang_tri_hong_van_du(gia, monkeypatch):
    lark = gia["lark"]
    cap = []
    monkeypatch.setattr(T.memory_store, "get_current_sender", lambda: "ou_x")
    monkeypatch.setattr(A, "_grant", lambda tok, ou: cap.append((len(lark.goi), ou)) or True)
    lark.hong = {"styles_batch_update"}
    kq = chay(nganh="túi xách")
    assert kq["granted"] is True and kq["sheet_url"] and kq["day_du"] is True
    writes = [i for i, g in enumerate(lark.goi) if g[1].endswith("/values_batch_update")]
    assert cap and cap[0][0] >= writes[-1] + 1 and cap[0][1] == "ou_x"
    assert len(lark.o("Dữ liệu")) == 4


def test_tao_sheet_hong_thi_loi_sheet(gia, monkeypatch):
    def hong(t):
        raise RuntimeError("lark 500 token=abc123")
    monkeypatch.setattr(A, "_create_sheet", hong)
    kq = chay(nganh="túi xách")
    assert kq["sheet_url"] is None and kq["loi"]["sheet"] and "abc123" not in kq["loi"]["sheet"]
    assert kq["success"] is False
