"""chi_so_ads: lọc tên chiến dịch nhiều chữ (audit 09/10/2026).

Ngân hỏi "có cả 20/10 và product trong tên"; Mark gửi loc="20/10 AND product" thành MỘT bộ lọc
CONTAIN nên Meta trả 0 dòng, trong khi tên thật viết HOA ("20/10_Reach_PRODUCT_…"). Meta giả ở
đây mặc định lọc CONTAIN PHÂN BIỆT hoa thường và so từng byte (không chuẩn hoá Unicode) —
trường hợp xấu nhất: bộ lọc phía Meta không bao giờ được làm rơi tên khớp.
"""
from __future__ import annotations

import json
import unicodedata

import pytest

import apify_tool as A
import meta_ads_tool as T
import trinh_bay_sheet as TB
from test_trinh_bay_meta_ads import _gia, context  # noqa: F401 — fixture tự dùng

ACC = [{"id": "act_10", "name": "HAPAS 10 - INSTAGRAM", "currency": "VND",
        "timezone_name": "Asia/Ho_Chi_Minh"}]
TEN = ["20/10_Reach_PRODUCT_Mass", "20/10_Reach_CELEB_M", "20/10_Conv_PRODUCT_Retarget",
       "Always_on_PRODUCT", "1/6_Reach_KOL"]


def _dong(ten=TEN):
    return [{"account_id": "10", "account_name": ACC[0]["name"], "campaign_id": f"1202{i:04d}",
             "campaign_name": t, "date_start": "2026-10-08", "date_stop": "2026-10-08",
             "spend": str(100000 * (i + 1)), "impressions": str(1000 * (i + 1)), "clicks": str(i + 1)}
            for i, t in enumerate(ten)]


def _meta(monkeypatch, ten=TEN, hoa_thuong=True, bo_qua_loc=False):
    """Meta giả: CONTAIN phân biệt hoa thường + so byte (`hoa_thuong`) hoặc không; mọi bộ lọc AND.
    Trả tối đa `limit` dòng, cờ cắt khi còn dòng."""
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: [dict(a) for a in ACC])
    goi = []

    def pages(self, tail, params, limit):
        if tail.endswith("/campaigns"):
            return [{"id": r["campaign_id"], "name": r["campaign_name"]} for r in _dong(ten)], False
        # Các kiểm tra CONTAIN bên dưới chỉ theo dõi truy vấn Insights.
        goi.append(dict(params))
        rows = _dong(ten)
        if "filtering" in params and not bo_qua_loc:
            for f in json.loads(params["filtering"]):
                assert f["field"] == "campaign.name" and f["operator"] == "CONTAIN"
                if hoa_thuong:
                    rows = [r for r in rows if f["value"] in r["campaign_name"]]
                else:
                    rows = [r for r in rows if f["value"].lower() in r["campaign_name"].lower()]
        return rows[:limit], len(rows) > limit
    monkeypatch.setattr(T.MetaClient, "pages", pages)
    return goi


def run(**args):
    return json.loads(T._handle({"tai_khoan": "HAPAS 10 - INSTAGRAM", "tu_ngay": "2026-10-08",
                                 "den_ngay": "2026-10-08", "cap": "chien_dich", "chi_so": ["spend"],
                                 **args}))


def _ten_chi_tiet(gia):
    o = gia.o("Chi tiết")
    i = o[0].index("Tên đối tượng")
    return [r[i] for r in o[1:] if len(r) > i and r[i] and not str(r[0]).startswith("TỔNG")]


def _gui_meta(goi):
    return [[f["value"] for f in json.loads(p["filtering"])] if "filtering" in p else None for p in goi]


# ───────────── chữ lọc ─────────────
def test_loc_tat_ca_khop_du_moi_chu():
    loc = T._loc_tu_khoa({"loc_tat_ca": ["20/10", "product"]})
    assert loc == ["20/10", "product"]
    assert T._khop_ten("20/10_Reach_PRODUCT_Mass", loc)
    assert not T._khop_ten("20/10_Reach_CELEB_M", loc)
    assert not T._khop_ten("Always_on_PRODUCT", loc)


@pytest.mark.parametrize("chuoi", ["20/10 AND product", "20/10  AND  product"])
def test_loc_chuoi_cu_chi_tach_o_and_viet_hoa(chuoi):
    assert T._loc_tu_khoa({"loc": chuoi}) == ["20/10", "product"]


@pytest.mark.parametrize("chuoi", ["Reach PRODUCT", "Mẹ và Bé", "Black & White", "Mua 1 + 1",
                                   "20/10 and product", "Mẹ&Bé", "Android TV"])
def test_loc_chuoi_cu_giu_nguyen_cum_that(chuoi):
    assert T._loc_tu_khoa({"loc": chuoi}) == [chuoi]


def test_loc_mang_va_gop_loc_tat_ca_bo_trung():
    assert T._loc_tu_khoa({"loc": ["20/10"], "loc_tat_ca": ["PRODUCT", "product", " 20/10 "]}) == \
        ["20/10", "PRODUCT"]
    assert T._loc_tu_khoa({}) == [] and T._loc_tu_khoa({"loc": "", "loc_tat_ca": []}) == []


@pytest.mark.parametrize("args, loi", [
    ({"loc_tat_ca": "20/10"}, "loc_tat_ca cần danh sách"),
    ({"loc_tat_ca": [str(i) for i in range(11)]}, "tối đa 10 chữ"),
    ({"loc_tat_ca": ["x" * 101]}, "tối đa 100 ký tự"),
    ({"loc_tat_ca": [1]}, "phải là chuỗi"),
    ({"loc": "x" * 201}, "tối đa 200 ký tự"),
    ({"loc": 5}, "loc cần chuỗi hoặc danh sách"),
])
def test_loc_sai_bao_loi_truoc_meta(monkeypatch, args, loi):
    goi = _meta(monkeypatch)
    kq = run(**args)
    assert loi in kq["error"] and not goi


def test_hoa_thuong_va_nfc():
    nfd = unicodedata.normalize("NFD", "20/10_Sản_Phẩm_Mới")
    assert nfd != unicodedata.normalize("NFC", nfd)
    assert T._khop_ten(nfd, T._loc_tu_khoa({"loc_tat_ca": ["SẢN_PHẨM"]}))
    assert T._khop_ten("20/10_SẢN_PHẨM", T._loc_tu_khoa({"loc_tat_ca": [unicodedata.normalize("NFD", "sản")]}))
    assert T._loc_tu_khoa({"loc": unicodedata.normalize("NFD", "20/10 AND sản phẩm")}) == ["20/10", "sản phẩm"]
    assert not T._khop_ten("San pham", ["sản phẩm"]), "khớp thật không bỏ dấu"


@pytest.mark.parametrize("chu, bat_bien", [
    ("20/10", True), ("2024", True), ("1+1", True), ("_", False), ("%", False), ("20_10", False), ("50%", False),
    ("product", False), ("PRODUCT", False), ("Sản", False), ("ß", False), ("năm", False)])
def test_chi_chu_bat_bien_moi_gui_meta(chu, bat_bien):
    assert T._bat_bien(chu) is bat_bien


# ───────────── gọi Meta: bộ lọc Meta chỉ thu hẹp, code quyết ─────────────
def test_khop_mot_phan_phia_meta_khong_lam_roi_ten(monkeypatch):
    """Review 10f4a90: CONTAIN phân biệt hoa thường + Meta lọc cả "product" thì chỉ giữ 1/3."""
    gia = _gia(monkeypatch)
    ten = ["20/10_product_test", "20/10_Reach_PRODUCT_Mass", "20/10_Conv_PRODUCT_R", "20/10_CELEB"]
    goi = _meta(monkeypatch, ten=ten, hoa_thuong=True)
    kq = run(loc_tat_ca=["20/10", "product"])
    assert "error" not in kq, kq
    assert _gui_meta(goi) == [["20/10"]], "chỉ chữ bất biến được gửi Meta; một lần đọc"
    assert kq["so_dong"] == 3 and kq["loc_may_chu"] == ["20/10"]
    assert sorted(_ten_chi_tiet(gia)) == sorted(ten[:3])
    assert "3 chiến dịch khớp" in kq["cau_loc"]
    assert "Chi tiêu 600000" in kq["cau_tong"] and "chứa đủ cả “20/10” và “product”" in kq["cau_tong"]


def test_hai_chu_bat_bien_thanh_hai_bo_loc(monkeypatch):
    _gia(monkeypatch)
    goi = _meta(monkeypatch)
    kq = run(loc_tat_ca=["20/10", "product", "/"])
    assert json.loads(goi[0]["filtering"]) == [
        {"field": "campaign.name", "operator": "CONTAIN", "value": "20/10"},
        {"field": "campaign.name", "operator": "CONTAIN", "value": "/"}]
    assert kq["so_dong"] == 2


def test_tu_khoa_nfd_ten_nfc(monkeypatch):
    gia = _gia(monkeypatch)
    ten = ["20/10_Sản_Phẩm_A", "20/10_San_Pham_B", "1/6_Sản_Phẩm_C"]
    goi = _meta(monkeypatch, ten=ten, hoa_thuong=True)
    kq = run(loc_tat_ca=["20/10", unicodedata.normalize("NFD", "SẢN_PHẨM")])
    assert _gui_meta(goi) == [["20/10"]], "chữ có dấu/hoa thường không gửi Meta"
    assert kq["so_dong"] == 1 and _ten_chi_tiet(gia) == ["20/10_Sản_Phẩm_A"]


def test_khong_chu_bat_bien_thi_doc_khong_loc_ten(monkeypatch):
    gia = _gia(monkeypatch)
    goi = _meta(monkeypatch)
    kq = run(loc_tat_ca=["product"])
    assert _gui_meta(goi) == [None], "không gửi bộ lọc tên; một lần đọc"
    assert kq["so_dong"] == 3 and kq["loc_may_chu"] == []
    assert sorted(_ten_chi_tiet(gia)) == ["20/10_Conv_PRODUCT_Retarget", "20/10_Reach_PRODUCT_Mass",
                                          "Always_on_PRODUCT"]


def test_chuoi_cu_and_duoc_tach(monkeypatch):
    _gia(monkeypatch)
    goi = _meta(monkeypatch)
    kq = run(loc="20/10 AND product")
    assert _gui_meta(goi) == [["20/10"]] and kq["so_dong"] == 2


def test_meta_bo_qua_loc_thi_code_van_loc(monkeypatch):
    gia = _gia(monkeypatch)
    _meta(monkeypatch, bo_qua_loc=True)
    kq = run(loc_tat_ca=["20/10", "product"])
    assert kq["so_dong"] == 2
    assert "20/10_Reach_CELEB_M" not in _ten_chi_tiet(gia)


def test_doc_khong_loc_cham_tran_thi_noi_ro(monkeypatch):
    gia = _gia(monkeypatch)
    monkeypatch.setattr(T, "MAX_ROWS", 3)
    goi = _meta(monkeypatch)
    kq = run(loc_tat_ca=["product"])
    assert goi and "filtering" not in goi[0]
    assert kq["bi_cat"] is True and kq["so_dong"] == 2
    assert "chạm trần 3 dòng" in kq["cau_loc"] and "có thể còn chiến dịch khớp" in kq["cau_loc"]
    tq = " ".join(" ".join(str(x) for x in r) for r in gia.o("Tổng quan"))
    assert "trần tính trên dòng Meta trả TRƯỚC khi tự lọc" in tq


def test_khong_khop_vi_cham_tran_van_noi_ro(monkeypatch):
    _gia(monkeypatch)
    monkeypatch.setattr(T, "MAX_ROWS", 3)
    _meta(monkeypatch)
    kq = run(loc_tat_ca=["always"])
    assert kq["so_dong"] == 0 and kq["bi_cat"] is True
    assert "chạm trần 3 dòng" in kq["cau_loc"] and kq["so_chien_dich_da_doc"] == 3
    assert kq["so_chien_dich_khop_ten"] == 1 and "chưa thấy trong phần đã đọc" in kq["cau_loc"]
    assert "Tài khoản có" not in kq["cau_loc"]


def test_khong_khop_cham_tran_co_loc_meta_noi_phan_da_doc(monkeypatch):
    monkeypatch.setattr(T, "MAX_ROWS", 2)
    _meta(monkeypatch)
    kq = run(loc_tat_ca=["20/10", "tet"])
    assert kq["bi_cat"] is True and kq["so_chien_dich_da_doc"] == 2
    assert "Trong phần đã đọc có 2 chiến dịch có số mà tên chứa “20/10”" in kq["cau_loc"]


# ───────────── không khớp: không trả "0 dòng" trần ─────────────
def test_khong_khop_noi_ro_khong_tra_0_tran(monkeypatch):
    goi = _meta(monkeypatch, hoa_thuong=True)

    def cam(*a, **k):
        raise AssertionError("không khớp thì không tạo Sheet")
    monkeypatch.setattr(TB, "xuat", cam)
    monkeypatch.setattr(T.lark, "call", cam)
    monkeypatch.setattr(A.lark, "call", cam)
    kq = run(loc_tat_ca=["20/10", "tet"])
    assert "error" not in kq, kq
    assert _gui_meta(goi) == [["20/10"]], "không đọc thêm lần nào chỉ để lấy tên"
    assert kq["so_dong"] == 0 and "link" not in kq
    assert kq["loc_ap_dung"] == "Tên chiến dịch chứa tất cả: 20/10, tet (không phân biệt hoa thường)"
    assert kq["loc_may_chu"] == ["20/10"] and kq["so_chien_dich_da_doc"] == 3
    assert kq["ten_gan_dung"] == ["20/10_Conv_PRODUCT_Retarget", "20/10_Reach_CELEB_M",
                                  "20/10_Reach_PRODUCT_Mass"]
    c = kq["cau_loc"]
    assert c == kq["cau_tong"]
    assert "Không có dòng báo cáo của chiến dịch có tên chứa đủ cả “20/10” và “tet”" in c
    assert "HAPAS 10 - INSTAGRAM" in c and "ngày 2026-10-08" in c
    assert "Trong khoảng đó có 3 chiến dịch có số mà tên chứa “20/10” nhưng không chứa “tet”" in c
    assert "20/10_Reach_CELEB_M" in c and "Meta không lọc ra" not in c
    s = json.dumps(kq, ensure_ascii=False)
    assert "100000" not in s and "Chi tiêu" not in s, "không trả số chỉ số cho chiến dịch không khớp"


def test_khong_khop_khong_loc_meta_dem_moi_chien_dich(monkeypatch):
    goi = _meta(monkeypatch)
    kq = run(loc_tat_ca=["product", "tet"])
    assert _gui_meta(goi) == [None]
    assert kq["so_chien_dich_da_doc"] == 5
    assert "Tài khoản có 5 chiến dịch có số trong khoảng đó; gần nhất:" in kq["cau_loc"]


def test_khong_khop_khong_ten_nao_gan_thi_van_dua_vai_ten(monkeypatch):
    _meta(monkeypatch)
    kq = run(loc_tat_ca=["black friday"])
    assert kq["so_dong"] == 0 and len(kq["ten_gan_dung"]) == 5
    assert "không tên nào chứa chữ đã hỏi" in kq["cau_loc"]


def test_khong_khop_tai_khoan_khong_chay_gi(monkeypatch):
    _meta(monkeypatch, ten=[])
    kq = run(loc_tat_ca=["20/10"])
    assert kq["so_chien_dich_da_doc"] == 0 and kq["ten_gan_dung"] == []
    assert "Meta không trả chiến dịch nào có số (Meta lọc sơ theo “20/10”)." in kq["cau_loc"]


def test_khong_khop_van_kiem_lai_quyen(monkeypatch):
    _meta(monkeypatch)
    lan = []

    def allowed(actor):
        lan.append(actor)
        return len(lan) == 1
    monkeypatch.setattr(T, "_allowed", allowed)
    kq = run(loc_tat_ca=["không có"])
    assert "error" in kq and "ten_gan_dung" not in kq


def test_ten_gan_dung_xep_theo_so_chu_khop():
    ten, co = T._ten_gan_dung(["A_x", "20-10_product_B", "20/10_PRODUCT", "z"], ["20/10", "product"])
    assert co and ten == ["20/10_PRODUCT", "20-10_product_B"]


# ───────────── Sheet ─────────────
def test_tong_quan_ghi_bo_loc(monkeypatch):
    gia = _gia(monkeypatch)
    _meta(monkeypatch)
    kq = run(loc_tat_ca=["20/10", "product"])
    assert kq["link"]
    tq = " ".join(" ".join(str(x) for x in r) for r in gia.o("Tổng quan"))
    assert "Tên chiến dịch chứa tất cả: 20/10, product (không phân biệt hoa thường)" in tq
    assert "Meta chỉ lọc sơ theo “20/10”" in tq and "tool tự kiểm đủ mọi chữ" in tq
    assert "Meta không lọc ra" not in tq and "đọc lại không lọc" not in tq


def test_tong_quan_khong_loc_meta(monkeypatch):
    gia = _gia(monkeypatch)
    _meta(monkeypatch)
    run(loc_tat_ca=["product"])
    tq = " ".join(" ".join(str(x) for x in r) for r in gia.o("Tổng quan"))
    assert "Tool đọc mọi chiến dịch có số trong khoảng ngày rồi tự lọc tên." in tq


def test_rieng_tu_khong_doi_khi_co_loc(monkeypatch):
    gia = _gia(monkeypatch)
    _meta(monkeypatch)
    kq = run(loc_tat_ca=["20/10", "product"])
    assert "link" in kq
    i_patch = next(i for i, g in enumerate(gia.goi) if g[0] == "PATCH" and "/drive/v2/permissions/" in g[1])
    i_get = next(i for i, g in enumerate(gia.goi) if g[0] == "GET" and "/drive/v2/permissions/" in g[1])
    writes = [i for i, g in enumerate(gia.goi) if g[1].endswith("/values_batch_update")]
    grants = [(i, g) for i, g in enumerate(gia.goi) if g[1].endswith("/members")]
    assert i_patch < i_get < writes[0]
    assert len(grants) == 1 and grants[0][0] > writes[-1]
    assert grants[0][1][3] == {"member_type": "openid", "member_id": "ou_asker", "perm": "view"}


def test_cap_quang_cao_loc_theo_ten_chien_dich(monkeypatch):
    _gia(monkeypatch)
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: [dict(a) for a in ACC])
    rows = [dict(r, ad_id=r["campaign_id"] + "1", ad_name="Ad product " + r["campaign_name"]) for r in _dong()]
    monkeypatch.setattr(T.MetaClient, "pages", lambda self, tail, params, limit:
        ([{"id": r["campaign_id"], "name": r["campaign_name"]} for r in rows] if tail.endswith("/campaigns")
         else [dict(r) for r in rows], False))
    kq = run(cap="quang_cao", loc_tat_ca=["20/10", "product"])
    assert kq["so_dong"] == 2, "tên QUẢNG CÁO có 'product' không đủ: lọc theo tên chiến dịch"


def test_cap_tai_khoan_co_loc_lay_cap_chien_dich(monkeypatch):
    _gia(monkeypatch)
    goi = _meta(monkeypatch)
    kq = run(cap="tai_khoan", loc_tat_ca=["20/10", "product"])
    assert goi[0]["level"] == "campaign" and kq["so_dong"] == 2 and "cap_thuc_te" in kq


# ───────────── xem_truoc ─────────────
def test_xem_truoc_ton_trong_loc(monkeypatch):
    _meta(monkeypatch)
    monkeypatch.setattr(T, "_private_sheet", lambda *a, **k: pytest.fail("không tạo Sheet"))
    kq = run(loc_tat_ca=["20/10", "product"], xem_truoc=True)
    assert kq["xem_truoc"] is True and kq["so_dong"] == 2
    assert kq["kich_thuoc"] == {"tai_khoan": 1, "chien_dich": 2}
    assert kq["loc_may_chu"] == ["20/10"] and "2 chiến dịch khớp" in kq["cau_loc"]
    assert "Chi tiêu" not in json.dumps(kq, ensure_ascii=False)


def test_xem_truoc_khong_khop_van_noi_ro(monkeypatch):
    _meta(monkeypatch)
    kq = run(loc_tat_ca=["20/10", "tet"], xem_truoc=True)
    assert kq["xem_truoc"] is True and kq["so_dong"] == 0 and kq["ten_gan_dung"]


def test_xuat_mau_cung_loc(monkeypatch):
    gia = _gia(monkeypatch)
    kq = T.xuat_mau(_dong(), {"cap": "chien_dich", "chi_so": ["spend"], "tu_ngay": "2026-10-08",
                              "den_ngay": "2026-10-08", "loc_tat_ca": ["20/10", "product"]},
                    cap_quyen=lambda token: None, tai_khoan=ACC)
    assert kq.url
    assert sorted(_ten_chi_tiet(gia)) == ["20/10_Conv_PRODUCT_Retarget", "20/10_Reach_PRODUCT_Mass"]


# ───────────── review a1821c1 ─────────────
def test_meta_bo_qua_loc_chi_mot_chu_khong_vo(monkeypatch):
    """`con` rỗng (mọi chữ đều gửi Meta) + Meta trả tên không khớp: không IndexError."""
    _meta(monkeypatch, ten=["Always_on_PRODUCT"], bo_qua_loc=True)
    kq = run(loc_tat_ca=["20/10"])
    assert "error" not in kq, kq
    c = kq["cau_loc"]
    assert kq["so_dong"] == 0 and kq["so_chien_dich_da_doc"] == 1
    assert "Đã đọc 1 chiến dịch có số trong khoảng đó (Meta lọc sơ theo “20/10”)" in c
    assert "mà tên chứa" not in c, "không khẳng định tên chứa chữ khi code chưa kiểm"


def test_meta_bo_qua_loc_chi_dem_ten_code_da_kiem(monkeypatch):
    _meta(monkeypatch, bo_qua_loc=True)
    kq = run(loc_tat_ca=["20/10", "tet"])
    assert kq["so_chien_dich_da_doc"] == 5
    assert "có 3 chiến dịch có số mà tên chứa “20/10” nhưng không chứa “tet”" in kq["cau_loc"]


def test_ky_tu_dai_dien_chi_loc_phia_code(monkeypatch):
    gia = _gia(monkeypatch)
    goi = _meta(monkeypatch, ten=["Sale_50%_20/10", "Sale 50 20/10", "20_10_x"])
    kq = run(loc_tat_ca=["50%", "20/10"])
    assert _gui_meta(goi) == [["20/10"]], "chữ có % / _ không gửi Meta"
    assert kq["so_dong"] == 1 and _ten_chi_tiet(gia) == ["Sale_50%_20/10"]
    goi.clear()
    kq = run(loc_tat_ca=["20_10"])
    assert _gui_meta(goi) == [None] and kq["so_dong"] == 1
