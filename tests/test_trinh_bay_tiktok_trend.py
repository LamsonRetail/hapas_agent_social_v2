"""Sheet trend TikTok dựng bằng lớp trình bày chung (trinh_bay_sheet, 08/10/2026).

Trước: năm loại (hashtag, top video, nhạc đang lên, âm thanh, hiệu ứng) dồn chung một bảng
với cột "Loại". Nay mỗi loại một bảng → tab đánh số; bảng rỗng không thành tab; Tổng quan =
cỡ mẫu tool đã đếm + đếm theo nhóm + ghi chú (nguồn chính thức vs suy từ mẫu, cắt trần,
nhạy cảm). Không có cột phần trăm: Creative Center chỉ trả hướng (chữ) và đổi hạng.
"""
from __future__ import annotations

import json

import test_tiktok_trend as TT
import tiktok_trend as T
from test_tiktok_trend import gia  # noqa: F401 — fixture dùng chung
from sheet_gia import meta  # noqa: E402


def _chay(**args) -> tuple[dict, str]:
    raw = T.chay(args)
    return json.loads(raw), raw


def _fmt(lark, tab, cot, dong=2):
    return [s["formatter"] for s in lark.kieu_o(tab, cot, dong) if "formatter" in s]


def test_tong_quan_co_mau_cua_tool_va_ghi_chu(gia):
    _, lark = gia
    kq, _ = _chay()
    tq = lark.o("Tổng quan")
    so = {r[0]: r[1] for r in tq if r and isinstance(r[0], str)}
    m = kq["mau_am_thanh"]
    assert so["Video mẫu đã cào"] == m["da_cao"] == 13
    assert so["Giữ lại (trong kỳ, đúng ngôn ngữ, không QC)"] == \
        m["giu_lai_trong_ky_dung_ngon_ngu"] == 7
    chu = " ".join(str(r[0]) for r in tq)
    assert kq["ghi_chu_nhac"] in chu and "SUY từ mẫu" in chu
    assert "HASHTAG THEO HƯỚNG" in chu and "Mẫu giữ được 7/100" in chu
    assert "Vùng VN" in meta(tq)


def test_dinh_dang_cot_va_tieu_de(gia):
    _, lark = gia
    _chay()
    o = lark.o("1. Hashtag đang nổi")
    assert o[0] == ["Hạng", "Hashtag", "Hướng", "Số bài", "Lượt xem", "Ngành", "Cảnh báo",
                    "Link"]
    assert o[1][:5] == [1, "#samdealruocden", "lên", 21209, 13703711]
    assert "#,##0" in _fmt(lark, "1. Hashtag đang nổi", 5)
    assert lark.tab("1. Hashtag đang nổi")["frozen"] == 1
    v = lark.o("2. Top video")
    assert v[1][3:6] == [0, 20223601, 338825], "followers, lượt xem, lượt xem tự nhiên"
    assert not any("%" in f for c in range(1, 9) for f in _fmt(lark, "2. Top video", c))


def test_du_lieu_goc_va_khong_lot_ban_ghi_tho(gia):
    _, lark = gia
    kq, raw = _chay()
    g = lark.o("Dữ liệu gốc")
    assert g[0][:2] == ["Bảng", "Dòng"] and "Metrics" in g[0]
    bang = [r[0] for r in g[1:]]
    assert bang.count("Hashtag đang nổi") == 3 and bang.count("Top video") == 1
    assert bang.count("Nhạc đang lên") == 10
    assert '"_goc"' not in raw
    assert all("_goc" not in t for t in kq["hashtag"] + kq["video"] + kq["nhac"])


def test_vung_khong_co_video_nhac_thi_khong_co_tab_rong(gia):
    _, lark = gia
    _chay(country="AR")
    assert "2. Top video" not in lark.tab_ten()
    assert not any("Nhạc đang lên" in t for t in lark.tab_ten())
    chu = " ".join(str(r[0]) for r in lark.o("Tổng quan"))
    assert "không có bảng nhạc cho AR" in chu


def test_hashtag_lay_them_de_lay_mau_thi_noi_ro(gia, monkeypatch):
    _, lark = gia
    monkeypatch.setattr(T, "_bang_hashtag", lambda vung, ky, n, *a: [
        dict(TT._tag(f"t{i}"), hang=i + 1, _goc={"Rank": i + 1}) for i in range(n)])
    kq, _ = _chay(so_hashtag=5)
    assert len(kq["hashtag"]) == 5
    assert len(lark.o("1. Hashtag đang nổi")) == 6
    chu = " ".join(str(r[0]) for r in lark.o("Tổng quan"))
    assert "Bảng hashtag ghi 5 dòng đầu" in chu and "lấy thêm chỉ để chọn chỗ lấy mẫu" in chu


def test_trang_tri_hong_van_co_link_va_du_lieu(gia):
    _, lark = gia
    lark.hong = {"styles_batch_update"}
    kq, _ = _chay()
    assert kq["sheet_url"] and kq["loi"] is None and kq["day_du"] is True
    assert len(lark.o("3. Nhạc đang lên")) == 11


def test_ghi_hong_thi_loi_sheet(gia):
    _, lark = gia
    lark.hong = {"values_batch_update"}
    kq, _ = _chay()
    assert kq["sheet_url"] is None and "sheet" in kq["loi"] and kq["hashtag"]
