"""Dashboard lắng nghe — dự báo chi phí theo dõi (`dashboard/chi_phi.py`, chủ dự án 15/10/2026:
"dashboard phải quản trị được chi phí").

Hằng số và công thức một lượt được CHÉP từ Mark (dashboard không import module của Mark): bài
đối chiếu ở đây import `theo_doi` / `apify_tool` để lệch là đỏ ngay. Số dự báo tính tay."""
from __future__ import annotations

import datetime

import pytest

import apify_tool as A
import theo_doi as T
from dashboard import chi_phi as CP

VN = datetime.timezone(datetime.timedelta(hours=7))
UTC = datetime.timezone.utc
XAP_XI = {"abs": 1e-6}


def test_hang_so_khop_mark():
    assert CP.GIA == T._GIA
    assert CP.HE_SO_UOC == T._HE_SO_UOC
    assert CP.START_COST == A._START_COST


@pytest.mark.parametrize("p", ["tiktok", "instagram", "facebook", "youtube"])
@pytest.mark.parametrize("so_nguon", [0, 1, 3])
@pytest.mark.parametrize("so_bai", [1, 5, 30])
def test_mot_luot_khop_uoc_phan_cua_mark(p, so_nguon, so_bai):
    assert CP.uoc_mot_luot(p, so_nguon, so_bai) == T._uoc_phan(p, so_nguon, so_bai)


@pytest.mark.parametrize("p, so_bai", [("tiktok", 10), ("instagram", 7), ("facebook", 4)])
def test_mot_nguon_mot_ngay_bang_mot_luot_actor(p, so_bai):
    """Phần theo bài + phí khởi động một ngày = đúng ước tính một lượt actor của Mark."""
    n = {"nen_tang": p, "so_bai_moi_lan": so_bai, "chu_ky_ngay": 1}
    assert CP.chi_phi_luot_nguon(n) + CP.phi_khoi_dong_ngay(p) == pytest.approx(
        T._uoc_phan(p, 1, so_bai), abs=1e-4)


def _nguon(i, p, so_bai, chu_ky, tt="dang_theo_doi"):
    return {"id": i, "nen_tang": p, "dinh_danh": f"n{i}", "ten": f"Nguồn {i}",
            "so_bai_moi_lan": so_bai, "chu_ky_ngay": chu_ky, "trang_thai": tt}


NGUON = [_nguon(1, "tiktok", 10, 1),            # 10×0,003×1,3 = 0,039/lượt
         _nguon(2, "instagram", 30, 2),         # 1 tài khoản×0,0026×1,3 = 0,00338/lượt
         _nguon(3, "youtube", 5, 1),            # miễn phí
         _nguon(4, "facebook", 5, 3, "tam_dung"),   # tạm dừng: không tính
         _nguon(5, "facebook", 4, 3)]           # 4×0,005×1,3 = 0,026/lượt
GIUA_THANG = datetime.datetime(2026, 10, 15, 12, 0, tzinfo=VN)   # còn 16,5 ngày


def test_du_bao_tinh_tay():
    db = CP.du_bao(NGUON, da_tieu=1.2, tran_du_an=2.0, tran_platform=None, bay_gio=GIUA_THANG)
    assert db["ngay_con_lai"] == 16.5
    # còn lại: TikTok 16,5×0,039 = 0,6435; Instagram 8,25×0,00338 = 0,027885 + khởi động
    # 8,25×(0,016×1,3) = 0,1716; Facebook 5,5×0,026 = 0,143 + 5,5×(0,00005×1,3) = 0,0003575
    nt = {x["nen_tang"]: x for x in db["nen_tang"]}
    assert [x["nen_tang"] for x in db["nen_tang"]] == ["tiktok", "instagram", "facebook", "youtube"]
    assert nt["tiktok"]["con_lai"] == pytest.approx(0.6435, **XAP_XI)
    assert nt["instagram"]["nguon_con_lai"] == pytest.approx(0.027885, **XAP_XI)
    assert nt["instagram"]["khoi_dong_con_lai"] == pytest.approx(0.1716, **XAP_XI)
    assert nt["facebook"]["con_lai"] == pytest.approx(0.1433575, **XAP_XI)
    assert nt["facebook"]["so_nguon"] == 1                       # nguồn 4 tạm dừng
    assert nt["youtube"]["con_lai"] == 0 and nt["youtube"]["thang_cau_hinh"] == 0
    assert db["con_lai"] == pytest.approx(0.9863, abs=1e-4)
    assert db["du_bao_thang"] == pytest.approx(2.1863, abs=1e-4)
    # 30 ngày theo cấu hình: 1,17 + (0,0507 + 0,312) + (0,26 + 0,00065) = 1,79335
    assert db["thang_cau_hinh"] == pytest.approx(1.79335, abs=1e-4)
    assert db["tran"] == 2.0 and db["vuot"] is True
    assert db["vuot_usd"] == pytest.approx(0.1863, abs=1e-4)
    assert [(x["id"], x["thang_usd"]) for x in db["top_ton"]] == [
        (1, pytest.approx(1.17)), (5, pytest.approx(0.26)), (2, pytest.approx(0.0507))]
    assert 4 not in [x["id"] for x in db["nguon"]] and 3 not in [x["id"] for x in db["top_ton"]]


def test_tran_hieu_luc_lay_tran_thap_hon():
    db = CP.du_bao(NGUON, 1.2, tran_du_an=5.0, tran_platform=None, bay_gio=GIUA_THANG)
    assert db["tran"] == 5.0 and db["vuot"] is False and db["vuot_usd"] == 0
    db = CP.du_bao(NGUON, 1.2, tran_du_an=5.0, tran_platform=1.5, bay_gio=GIUA_THANG)
    assert (db["tran"], db["tran_platform"], db["vuot"]) == (1.5, 1.5, True)
    assert CP.tran_hieu_luc(1.0, 3.0) == 1.0 and CP.tran_hieu_luc(4.0, None) == 4.0


def test_chi_nguon_tam_dung_va_youtube_thi_khong_ton():
    db = CP.du_bao([_nguon(1, "youtube", 30, 1), _nguon(2, "tiktok", 30, 1, "tam_dung")],
                   0.0, 5.0, None, GIUA_THANG)
    assert db["con_lai"] == 0 and db["du_bao_thang"] == 0 and db["top_ton"] == []
    assert [x["nen_tang"] for x in db["nen_tang"]] == ["youtube"]
    trong = CP.du_bao([], 0.7, 5.0, None, GIUA_THANG)
    assert trong["du_bao_thang"] == 0.7 and trong["nen_tang"] == [] and not trong["vuot"]


def test_khoi_dong_theo_chu_ky_ngan_nhat_cua_nen_tang():
    """Hai nguồn Instagram chu kỳ 1 và 7: nền tảng có ngày quét MỖI ngày -> khởi động 30 lần."""
    db = CP.du_bao([_nguon(1, "instagram", 5, 1), _nguon(2, "instagram", 5, 7)], 0, 5, None,
                   GIUA_THANG)
    (ig,) = db["nen_tang"]
    assert ig["thang_cau_hinh"] == pytest.approx(30 * 0.00338 + 30 / 7 * 0.00338 + 30 * 0.0208)


@pytest.mark.parametrize("luc, con, so_ngay", [
    (datetime.datetime(2026, 10, 31, 23, 0, tzinfo=VN), 1 / 24, 31),
    (datetime.datetime(2026, 10, 31, 17, 30, tzinfo=UTC), 30 - 0.5 / 24, 30),   # 00:30 1/11 VN
    (datetime.datetime(2026, 10, 31, 16, 59, tzinfo=UTC), 1 / 1440, 31),        # 23:59 31/10 VN
    (datetime.datetime(2026, 12, 15, 0, 0, tzinfo=VN), 17.0, 31),               # sang năm mới
    (datetime.datetime(2028, 2, 1, 0, 0, tzinfo=VN), 29.0, 29),                 # năm nhuận
    (datetime.datetime(2026, 10, 1, 0, 0, tzinfo=VN), 31.0, 31),
])
def test_ngay_con_lai_theo_thang_gio_vn(luc, con, so_ngay):
    assert CP.ngay_con_lai(luc) == pytest.approx(con, abs=1e-9)
    assert CP.so_ngay_thang(luc) == so_ngay


def test_hang_so_cho_trinh_duyet():
    hs = CP.hang_so_cho_trinh_duyet()
    assert hs == {"gia": CP.GIA, "he_so": 1.3, "start": CP.START_COST, "ngay": 30}
