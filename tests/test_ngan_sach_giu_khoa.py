"""Bấm Lưu trang Ngân sách GIỮ mọi khoá con biểu mẫu không quản (soát 18/10/2026).

Lỗi cũ: `POST /ngan-sach/{ma}/cau-hinh` dựng lại cả nhóm `tu_khoa` / `binh_luan` / `do_phu` từ ô của
biểu mẫu, nên khối `gian` (giãn nhịp) của mọi nền tảng — và khoá con nào biểu mẫu không có ô — mất
mỗi lần lưu. Nay mỗi khối bắt đầu từ bản đang lưu; nhóm ngoài biểu mẫu (`seeding`,
`hashtag_can_nhac_brand`, `web`, `theo_doi`…) giữ như `kho.dat_cau_hinh`. Kho giả."""
from __future__ import annotations

import copy
import html
import re
from pathlib import Path

import theo_doi as T


def _form_trang(t: str) -> dict:
    """Mọi ô của biểu mẫu Ngân sách như trình duyệt gửi khi bấm Lưu không sửa gì."""
    vung = re.search(r'<form method="post" action="/ngan-sach/hapas/cau-hinh" id="ns-form">'
                     r'(.*?)</form>', t, re.DOTALL).group(1)
    form = {}
    for the in re.findall(r"<input\b[^>]*>", vung):
        ten = re.search(r'name="([^"]+)"', the)
        if not ten:
            continue
        kieu = (re.search(r'type="([^"]+)"', the) or [None, "text"])[1]
        gt = re.search(r'value="([^"]*)"', the)
        if kieu == "checkbox" and " checked" not in the:
            continue
        form[ten.group(1)] = html.unescape(gt.group(1)) if gt else ""
    return form


def _giu_het(a: dict, b: dict, duong: str = "") -> None:
    for k, v in a.items():
        assert k in b, duong + k
        if isinstance(v, dict):
            _giu_het(v, b[k], f"{duong}{k}.")
        else:
            assert b[k] == v, duong + k


def test_luu_ngan_sach_giu_moi_khoa_con_bieu_mau_khong_quan():
    """Lưu nguyên biểu mẫu không sửa gì thì cấu hình giữ nguyên từng khoá; ô đã sửa vẫn đổi, ô xoá
    trống vẫn bỏ khoá (theo mặc định chung)."""
    from test_dashboard_app import QL, dang_nhap, tao, thong_bao
    from test_dashboard_app import GiaKho as KhoDash
    goc = {"tu_khoa": {
        "instagram": {"bat": True, "so_bai": 30, "so_tu": 6, "gian": {"bat": False, "gio": 72},
                      "bo_tu": ["#quatang2010"]},
        "facebook": {"bat": True, "gian": {"luot": 4},
                     "duong2": {"bat": True, "so_bai_moi_tu": 12, "gio": 30}},
        "threads": {"bat": True, "so_bai": 20, "gian": {"ty_le": 0.1},
                    "duong2": {"bat": False, "so_bai": 50}},
        "tiktok": {"bat": True, "so_tu": 3, "hashtag": {"bat": True, "so_yeu_cau": 5, "gio": 12}},
        "khac": {"bat": True}},
        "binh_luan": {"tiktok": {"bat": True, "so_bai": 10, "uu_tien": "moi"}},
        "do_phu": {"bat": True, "tran_usd": 0.2, "ghi_chu": "x"},
        "seeding": {"bat": False, "bai_mot_ngay": 7},
        "hashtag_can_nhac_brand": {"bat": True, "ten": ["Mate Made"]},
        "web": {"mien_nha": ["hapas.vn"]}, "theo_doi": {"co_gian": False}}
    kho = KhoDash()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15, tu_khoa=["hapas", "quatang2010"],
                              cau_hinh=copy.deepcopy(goc))
    _, c, _ = tao(kho)
    dang_nhap(c, QL)
    form = _form_trang(c.get("/ngan-sach").text)
    assert form["tk_instagram_so_tu"] == "6" and "tk_instagram_bat" in form
    r = c.post("/ngan-sach/hapas/cau-hinh", data=form)
    assert "Đã lưu cấu hình thu thập" in thong_bao(c, r)
    ch = kho.du_an["hapas"]["cau_hinh"]
    for p in ("instagram", "facebook", "threads"):
        assert ch["tu_khoa"][p]["gian"] == goc["tu_khoa"][p]["gian"], p
    assert ch["tu_khoa"]["facebook"]["duong2"] == goc["tu_khoa"]["facebook"]["duong2"]
    assert ch["tu_khoa"]["threads"]["duong2"] == goc["tu_khoa"]["threads"]["duong2"]
    assert ch["tu_khoa"]["tiktok"]["hashtag"] == goc["tu_khoa"]["tiktok"]["hashtag"]
    assert ch["tu_khoa"]["tiktok"]["so_tu"] == 3 and ch["tu_khoa"]["khac"] == {"bat": True}
    assert ch["tu_khoa"]["instagram"]["bo_tu"] == ["#quatang2010"]
    assert ch["binh_luan"]["tiktok"]["uu_tien"] == "moi" and ch["do_phu"]["ghi_chu"] == "x"
    for k in ("seeding", "hashtag_can_nhac_brand", "web", "theo_doi"):
        assert ch[k] == goc[k], k
    _giu_het(goc, ch)          # lưu biểu mẫu không sửa gì: mọi khoá đang lưu giữ nguyên giá trị
    # Sửa ô: chỉ khoá đó đổi; ô số bài xoá trống → bỏ khoá (theo mặc định chung), `gian` vẫn còn.
    c.post("/ngan-sach/hapas/cau-hinh", data={**form, "tk_instagram_so_bai": "",
                                              "dp_tran": "0,35"})
    ch = kho.du_an["hapas"]["cau_hinh"]
    assert "so_bai" not in ch["tu_khoa"]["instagram"] and ch["tu_khoa"]["instagram"]["gian"] == {
        "bat": False, "gio": 72}
    assert ch["do_phu"] == {"bat": True, "tran_usd": 0.35, "ghi_chu": "x"}


def test_mo_ta_schema_noi_khoi_gian_dung_mac_dinh():
    """COMMENT `du_an.cau_hinh` (quy chuẩn BI: mô tả đúng dữ liệu) nói khối `gian` đúng mặc định."""
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    m = re.search(r"COMMENT ON COLUMN du_an\.cau_hinh IS '([^']*)';", sql).group(1)
    assert '"gian"' in m
    for k, v in (("luot", T.TK_GIAN_LUOT), ("gio", T.TK_GIAN_GIO)):
        assert re.search(rf'"{k}" \((mặc định )?{v}\b', m), k
