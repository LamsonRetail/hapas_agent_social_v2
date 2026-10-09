"""chi_so_ads: lọc tên chiến dịch nhiều chữ (audit 09/10/2026).

Ngân hỏi "có cả 20/10 và product trong tên"; Mark gửi loc="20/10 AND product" thành MỘT bộ lọc
CONTAIN nên Meta trả 0 dòng, trong khi tên thật viết HOA ("20/10_Reach_PRODUCT_…"). Meta giả ở
đây lọc CONTAIN PHÂN BIỆT hoa thường (trường hợp xấu nhất) để buộc đường đọc lại không lọc.
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
    """Meta giả: CONTAIN phân biệt hoa thường (`hoa_thuong`) hoặc không; mọi bộ lọc AND."""
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: [dict(a) for a in ACC])
    goi = []

    def pages(self, tail, params, limit):
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


# ───────────── chữ lọc ─────────────
def test_loc_tat_ca_khop_du_moi_chu():
    loc = T._loc_tu_khoa({"loc_tat_ca": ["20/10", "product"]})
    assert loc == ["20/10", "product"]
    assert T._khop_ten("20/10_Reach_PRODUCT_Mass", loc)
    assert not T._khop_ten("20/10_Reach_CELEB_M", loc)
    assert not T._khop_ten("Always_on_PRODUCT", loc)


@pytest.mark.parametrize("chuoi", ["20/10 AND product", "20/10 and product", "20/10 & product",
                                   "20/10 + product", "20/10 và product", "20/10  And  product"])
def test_loc_chuoi_cu_tach_o_dau_noi(chuoi):
    assert T._loc_tu_khoa({"loc": chuoi}) == ["20/10", "product"]


@pytest.mark.parametrize("chuoi", ["Reach PRODUCT", "Mẹ&Bé", "C+", "Android TV"])
def test_loc_chuoi_khong_tach_o_dau_cach(chuoi):
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
    assert T._khop_ten(nfd, T._loc_tu_khoa({"loc_tat_ca": ["SẢN PHẨM".replace(" ", "_")]}))
    assert T._khop_ten("20/10_SẢN_PHẨM", T._loc_tu_khoa({"loc_tat_ca": [unicodedata.normalize("NFD", "sản")]}))
    # Chuỗi cũ viết tách bằng "và" dạng tổ hợp vẫn tách đúng.
    assert T._loc_tu_khoa({"loc": unicodedata.normalize("NFD", "20/10 và sản phẩm")}) == ["20/10", "sản phẩm"]
    assert not T._khop_ten("San pham", ["sản phẩm"]), "khớp thật không bỏ dấu"


# ───────────── gọi Meta ─────────────
def test_moi_chu_mot_bo_loc_graph(monkeypatch):
    _gia(monkeypatch)
    goi = _meta(monkeypatch, hoa_thuong=False)
    kq = run(loc_tat_ca=["20/10", "product"])
    assert "error" not in kq, kq
    assert json.loads(goi[0]["filtering"]) == [
        {"field": "campaign.name", "operator": "CONTAIN", "value": "20/10"},
        {"field": "campaign.name", "operator": "CONTAIN", "value": "product"}]
    assert len(goi) == 1 and kq["loc_du_phong"] is False, "Meta đã lọc ra dòng: không đọc lại"
    assert "2 chiến dịch khớp" in kq["cau_loc"]


def test_chuoi_cu_and_duoc_tach_thanh_hai_bo_loc(monkeypatch):
    _gia(monkeypatch)
    goi = _meta(monkeypatch, hoa_thuong=False)
    kq = run(loc="20/10 AND product")
    assert [f["value"] for f in json.loads(goi[0]["filtering"])] == ["20/10", "product"]
    assert kq["so_dong"] == 2


def test_meta_tra_0_thi_doc_lai_khong_loc_va_tu_loc(monkeypatch):
    gia = _gia(monkeypatch)
    goi = _meta(monkeypatch, hoa_thuong=True)      # "product" ≠ "PRODUCT" phía Meta
    kq = run(loc_tat_ca=["20/10", "product"])
    assert "error" not in kq, kq
    assert len(goi) == 2 and "filtering" in goi[0] and "filtering" not in goi[1]
    assert goi[0]["time_range"] == goi[1]["time_range"]
    assert kq["loc_du_phong"] is True and kq["so_dong"] == 2
    assert sorted(_ten_chi_tiet(gia)) == ["20/10_Conv_PRODUCT_Retarget", "20/10_Reach_PRODUCT_Mass"]
    assert "đọc lại không lọc" in kq["cau_loc"]
    # Tổng chỉ của chiến dịch khớp: 100.000 + 300.000.
    assert "Chi tiêu 400000" in kq["cau_tong"] and "chứa đủ cả “20/10” và “product”" in kq["cau_tong"]


def test_meta_bo_qua_loc_thi_code_van_loc(monkeypatch):
    gia = _gia(monkeypatch)
    _meta(monkeypatch, bo_qua_loc=True)
    kq = run(loc_tat_ca=["20/10", "product"])
    assert kq["so_dong"] == 2 and kq["loc_du_phong"] is False
    assert "20/10_Reach_CELEB_M" not in _ten_chi_tiet(gia)


def test_khong_khop_noi_ro_khong_tra_0_tran(monkeypatch):
    goi = _meta(monkeypatch, hoa_thuong=True)

    def cam(*a, **k):
        raise AssertionError("không khớp thì không tạo Sheet")
    monkeypatch.setattr(TB, "xuat", cam)
    monkeypatch.setattr(T.lark, "call", cam)
    monkeypatch.setattr(A.lark, "call", cam)
    kq = run(loc_tat_ca=["20/10", "tet"])
    assert "error" not in kq, kq
    assert len(goi) == 2 and kq["so_dong"] == 0 and "link" not in kq
    assert kq["loc_ap_dung"] == "Tên chiến dịch chứa tất cả: 20/10, tet (không phân biệt hoa thường)"
    assert kq["loc_du_phong"] is True and kq["so_chien_dich_khong_loc"] == 5
    assert kq["ten_gan_dung"] == ["20/10_Conv_PRODUCT_Retarget", "20/10_Reach_CELEB_M",
                                  "20/10_Reach_PRODUCT_Mass"]
    c = kq["cau_loc"]
    assert c == kq["cau_tong"]
    assert "Không có chiến dịch nào có tên chứa đủ cả “20/10” và “tet”" in c
    assert "HAPAS 10 - INSTAGRAM" in c and "ngày 2026-10-08" in c and "có 5 chiến dịch có số" in c
    assert "20/10_Reach_CELEB_M" in c
    s = json.dumps(kq, ensure_ascii=False)
    assert "100000" not in s and "Chi tiêu" not in s, "không trả số chỉ số cho chiến dịch không khớp"


def test_khong_khop_khong_ten_nao_gan_thi_van_dua_vai_ten(monkeypatch):
    _meta(monkeypatch)
    kq = run(loc_tat_ca=["black friday"])
    assert kq["so_dong"] == 0 and len(kq["ten_gan_dung"]) == 5
    assert "không tên nào chứa chữ đã hỏi" in kq["cau_loc"]


def test_khong_khop_tai_khoan_khong_chay_gi(monkeypatch):
    _meta(monkeypatch, ten=[])
    kq = run(loc_tat_ca=["20/10"])
    assert kq["so_chien_dich_khong_loc"] == 0 and kq["ten_gan_dung"] == []
    assert "không có chiến dịch nào có số" in kq["cau_loc"]


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
    assert "đọc lại không lọc rồi tự lọc tên" in tq


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
    monkeypatch.setattr(T.MetaClient, "pages", lambda self, tail, params, limit: ([dict(r) for r in rows], False))
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
    assert kq["loc_du_phong"] is True and "2 chiến dịch khớp" in kq["cau_loc"]
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
