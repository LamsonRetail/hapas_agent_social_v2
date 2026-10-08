"""soi_san theo LINK (san_link.py) → lớp trình bày chung (trinh_bay_sheet), Lark GIẢ.

Soi: 4 bảng → "Tổng quan", "1. Sản phẩm", "2. Phân loại", "3. Mô tả", "4. Bình luận",
"Dữ liệu gốc"; mục lục đúng số dòng; giá VND định dạng tiền ₫, điểm 2 lẻ, ngày bình luận là
ngày thật; Tổng quan đếm theo sàn/sao + ghi chú giới hạn nguồn (TikTok Shop chỉ vài bình
luận); bản ghi gốc của actor vào sheet nhưng không lọt ra tool_result; `cap_quyen` sau cùng;
trang trí hỏng vẫn có link + dữ liệu; `tabs.ket_qua.cho_tool()` cho shopee_tool.
"""
from __future__ import annotations

import json

import san_link as L
import shopee_tool as S
import trinh_bay_sheet as T
from test_san_link import SP_URL, TT_URL, gia  # noqa: F401


def _fmt(lk, tab, cot, dong=2):
    return [s["formatter"] for s in lk.kieu_o(tab, cot, dong) if "formatter" in s]


def test_bon_bang_tab_danh_so_muc_luc_va_dinh_dang(gia):  # noqa: F811
    _, dong = gia
    lk = dong.lk
    raw = S._handle({"link": [SP_URL, TT_URL]})
    kq = json.loads(raw)
    assert kq["sheet_url"].startswith("https://x.larksuite.com/sheets/")
    assert lk.tab_ten() == ["Tổng quan", "1. Sản phẩm", "2. Phân loại", "3. Mô tả",
                            "4. Bình luận", T.TAB_GOC]
    muc = {r[0]["text"]: r[1] for r in lk.o("Tổng quan") if r and isinstance(r[0], dict)}
    assert muc["1. Sản phẩm"] == 2 and muc["3. Mô tả"] == 2
    assert muc["4. Bình luận"] == len(lk.o("4. Bình luận")) - 1 == 4
    sp = lk.o("1. Sản phẩm")
    i = sp[0].index("Giá từ")
    assert sp[1][i] == 19900 and '#,##0 "₫"' in _fmt(lk, "1. Sản phẩm", i + 1)
    j = sp[0].index("Điểm")
    assert "#,##0.00" in _fmt(lk, "1. Sản phẩm", j + 1)
    bl = lk.o("4. Bình luận")
    assert isinstance(bl[1][2], int) and "dd/MM/yyyy" in _fmt(lk, "4. Bình luận", 3)
    assert lk.tab("4. Bình luận")["frozen"] == 1
    assert "__goc" not in raw and "reviewId" not in raw


def test_tong_quan_dem_theo_san_sao_va_ghi_chu_nguon(gia):  # noqa: F811
    _, dong = gia
    lk = dong.lk
    S._handle({"link": [SP_URL, TT_URL]})
    tq = lk.o("Tổng quan")
    i = next(k for k, r in enumerate(tq) if r and r[0] == "SẢN PHẨM THEO SÀN")
    nhom = {tq[i + 2][0]: tq[i + 2][1], tq[i + 3][0]: tq[i + 3][1]}
    assert nhom == {"Shopee": 1, "TikTok Shop": 1}
    assert any(r and r[0] == "BÌNH LUẬN THEO SỐ SAO" for r in tq)
    ghi = " ".join(str(r[0]) for r in tq)
    assert "Phạm vi: 1 link Shopee, 1 link TikTok Shop" in ghi
    assert "KHÔNG phải mẫu đại diện" in ghi and "Chỉ đọc được 2/7 bình luận" in ghi
    assert "Ô trống = nguồn không trả số đó, KHÔNG phải 0" in ghi


def test_du_lieu_goc_moi_nguon_kem_actor(gia):  # noqa: F811
    _, dong = gia
    lk = dong.lk
    S._handle({"link": [SP_URL, TT_URL]})
    goc = lk.o(T.TAB_GOC)
    h = goc[0]
    assert h[:2] == ["Nguồn (actor)", "Sản phẩm (của tool)"]
    nguon = [r[0] for r in goc[1:]]
    assert L.ACTOR_TIM_SHOPEE in nguon and L.ACTOR_CT_SHOPEE in nguon and L.ACTOR_TTS in nguon
    assert nguon.count(L.ACTOR_DG_SHOPEE) == 2, "mọi đánh giá đọc được, kể cả trước khi lọc"
    assert "likedCount" in h and "reviewId" in h


def test_ghi_nhieu_tab_cap_quyen_sau_cung_va_ket_qua_cho_tool(gia):  # noqa: F811
    _, dong = gia
    lk = dong.lk
    kq = L.soi([SP_URL], 10)
    luc = []
    tok, url = L.ghi_nhieu_tab("Soi", kq["tabs"], cap_quyen=lambda t: luc.append(len(lk.goi)))
    ghi = [i for i, g in enumerate(lk.goi) if g[1].endswith("values_batch_update")]
    assert url and luc and luc[0] > max(ghi)
    ct = kq["tabs"].ket_qua.cho_tool()
    assert ct["day_du"] is True and ct["kiem_ghi"].startswith("Đã ghi đủ")
    assert kq["tabs"][0][0] == L.TEN_TAB_SAN_PHAM and len(kq["tabs"][0][1]) > 1


def test_trang_tri_hong_van_co_link_va_du_lieu(gia):  # noqa: F811
    _, dong = gia
    lk = dong.lk
    lk.hong = {"styles_batch_update", "/filter"}
    kq = json.loads(S._handle({"link": [TT_URL]}))
    assert kq["sheet_url"] and not (kq.get("loi") or {}).get("sheet")
    assert len(lk.o("4. Bình luận")) == 3
