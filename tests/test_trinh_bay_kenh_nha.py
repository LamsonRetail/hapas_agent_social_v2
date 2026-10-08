"""binh_luan_kenh_nha → lớp trình bày chung (trinh_bay_sheet) với Lark GIẢ (tests/sheet_gia).

Soi: 3 bảng → "Tổng quan", "1. Bình luận", "2. Thống kê", "3. Bài đã đọc", "Dữ liệu gốc";
mục lục đúng số dòng; Tổng quan chép đúng `thong_ke`; ô Likes trống (Threads) KHÔNG thành 0;
bản ghi gốc của Meta vào sheet nhưng KHÔNG mang token (`paging.next` có access_token) và không
lọt ra tool_result; cấp quyền sau cùng; `day_du`/`kiem_ghi`.
"""
from __future__ import annotations

import json

import apify_tool as A
import kenh_nha_tool as K
import trinh_bay_sheet as T
from test_binh_luan_kenh_nha import (TOK_IG, TOK_TH_DAI, M, _instagram, _so_dai_han,  # noqa: F401
                                     _threads, env, mang, sheet)


def _muc_luc(gia) -> dict:
    return {r[0]["text"]: r[1] for r in gia.o("Tổng quan") if r and isinstance(r[0], dict)}


def test_threads_ba_bang_tong_quan_va_o_trong(env, mang, sheet):  # noqa: F811
    env(THREADS_ACCESS_TOKEN=TOK_TH_DAI)
    _so_dai_han("threads", TOK_TH_DAI, TOK_TH_DAI, 50 * M.NGAY, 2 * M.NGAY)
    _threads(mang)
    raw = K._handle({"kenh": ["threads"], "title": "Kênh nhà Threads"})
    kq = json.loads(raw)
    gia = sheet
    assert gia.tab_ten() == ["Tổng quan", "1. Bình luận", "2. Thống kê", "3. Bài đã đọc",
                             T.TAB_GOC]
    muc = _muc_luc(gia)
    assert muc["1. Bình luận"] == kq["tong_comment"] == 4 and muc["3. Bài đã đọc"] == 1
    assert muc[T.TAB_GOC] == 4
    tq = gia.o("Tổng quan")
    so = {r[0]: r[1] for r in tq if r and isinstance(r[0], str) and len(r) > 1}
    tk = kq["thong_ke"]
    assert so["Bình luận tính thống kê"] == tk["tong"] == 3
    assert so["Phản hồi của chính thương hiệu"] == tk["cua_thuong_hieu"] == 1
    assert so["Tích cực"] == tk["sac_thai"]["Tích cực"]["so"]
    ghi = " ".join(str(r[0]) for r in tq)
    assert kq["dong_thong_ke"] in ghi and "TRỐNG = không có số, KHÔNG phải 0" in ghi
    # Likes Threads: ô trống giữ trống (không bịa 0), cột vẫn định dạng số nguyên.
    bl = gia.o("1. Bình luận")
    assert all(r[5] == "" for r in bl[1:])
    assert "#,##0" in [s.get("formatter") for s in gia.kieu_o("1. Bình luận", 6, 2)]
    assert "@" in [s.get("formatter") for s in gia.kieu_o("1. Bình luận", 12, 2)]
    assert kq["thong_ke_ghi_o"] == "tab '2. Thống kê'"
    assert kq["day_du"] is True and kq["kiem_ghi"] in kq["note"]
    assert "__goc" not in raw and "root_post" not in raw


def test_du_lieu_goc_instagram_khong_mang_token(env, mang, sheet, monkeypatch):  # noqa: F811
    env(IG_ACCESS_TOKEN=TOK_IG)
    _so_dai_han("instagram", TOK_IG, TOK_IG, 50 * M.NGAY, 2 * M.NGAY)
    _instagram(mang)
    luc = []
    monkeypatch.setattr(K.memory_store, "get_current_sender", lambda: "ou_x")
    monkeypatch.setattr(A, "_grant", lambda tok, oid: luc.append(len(sheet.goi)) or True)
    raw = K._handle({"kenh": ["instagram"]})
    kq = json.loads(raw)
    goc = sheet.o(T.TAB_GOC)
    assert goc and "id" in goc[0] and "username" in goc[0]
    o = json.dumps(goc, ensure_ascii=False)
    assert TOK_IG not in o and "paging" not in o, "URL next của Meta mang token: bỏ"
    assert TOK_IG not in raw
    assert kq["granted"] is True
    ghi = [i for i, g in enumerate(sheet.goi) if g[1].endswith("values_batch_update")]
    assert luc and luc[0] > max(ghi), "cấp quyền SAU khi ghi xong"
