"""Lịch quét tự động (15/10/2026) — phần THUẦN `dashboard/lich_quet.py`: kiểm cấu hình, tính mốc
chạy (giờ VN UTC+7, không giờ mùa hè), quyết định của nhịp quét. Dashboard và Mark dùng chung
module này nên mốc dashboard xem trước = mốc Mark chạy."""
from __future__ import annotations

import datetime as dt

import pytest

from dashboard import lich_quet as LQ

VN = dt.timezone(dt.timedelta(hours=7))
UTC = dt.timezone.utc


def vn(*a):
    return dt.datetime(*a, tzinfo=VN)


def moc(kieu, ch, sau, so=10):
    return [x.strftime("%Y-%m-%d %H:%M") for x in LQ.cac_moc(kieu, ch, sau, so)]


# 2026-10-15 là thứ Năm (T5); 16 T6, 17 T7, 18 CN, 19 T2.
NAM_HAI = {"moi_gio": 2, "tu": "07:00", "den": "23:00", "thu": []}


# ───────────────────────────── mỗi N giờ ─────────────────────────────
def test_moi_n_gio_trong_khung_va_sang_ngay_sau():
    assert moc("moi_n_gio", NAM_HAI, vn(2026, 10, 15, 8, 30), 9) == [
        "2026-10-15 09:00", "2026-10-15 11:00", "2026-10-15 13:00", "2026-10-15 15:00",
        "2026-10-15 17:00", "2026-10-15 19:00", "2026-10-15 21:00", "2026-10-15 23:00",
        "2026-10-16 07:00"]
    assert LQ.luot_moi_ngay("moi_n_gio", NAM_HAI) == 9


def test_moi_n_gio_moc_dung_bang_sau_thi_lay_moc_ke():
    """`moc_ke` lấy mốc SAU HẲN thời điểm đưa vào — mốc vừa chạy không bị lấy lại."""
    assert LQ.moc_ke("moi_n_gio", NAM_HAI, vn(2026, 10, 15, 9, 0)) == vn(2026, 10, 15, 11, 0)
    assert LQ.moc_ke("moi_n_gio", NAM_HAI, vn(2026, 10, 15, 23, 0)) == vn(2026, 10, 16, 7, 0)
    assert LQ.moc_ke("moi_n_gio", NAM_HAI, vn(2026, 10, 15, 6, 59, 59)) == vn(2026, 10, 15, 7, 0)


@pytest.mark.parametrize("n, ra", [(1, 14), (3, 5), (4, 4), (6, 3), (8, 2), (12, 2)])
def test_moi_n_gio_so_luot_moi_ngay(n, ra):
    ch = {"moi_gio": n, "tu": "08:00", "den": "21:00", "thu": []}
    assert LQ.luot_moi_ngay("moi_n_gio", ch) == ra


def test_moi_n_gio_chi_ngay_thuong():
    ch = {**NAM_HAI, "thu": [1, 2, 3, 4, 5]}
    # Thứ Sáu 23:30 -> bỏ T7, CN -> Thứ Hai 07:00
    assert LQ.moc_ke("moi_n_gio", ch, vn(2026, 10, 16, 23, 30)) == vn(2026, 10, 19, 7, 0)


def test_moi_gio_ca_ngay():
    ch = {"moi_gio": 1, "tu": "00:00", "den": "23:59", "thu": []}
    assert LQ.luot_moi_ngay("moi_n_gio", ch) == 24
    assert moc("moi_n_gio", ch, vn(2026, 10, 15, 22, 10), 3) == [
        "2026-10-15 23:00", "2026-10-16 00:00", "2026-10-16 01:00"]


# ───────────────────────────── hằng ngày / hằng tuần ─────────────────────────────
def test_hang_ngay_gio_cu_the():
    ch = {"gio": ["07:00", "12:00", "19:30"], "thu": []}
    assert moc("hang_ngay", ch, vn(2026, 10, 15, 19, 30), 4) == [
        "2026-10-16 07:00", "2026-10-16 12:00", "2026-10-16 19:30", "2026-10-17 07:00"]


def test_hang_ngay_chi_cuoi_tuan():
    ch = {"gio": ["09:00"], "thu": [6, 7]}
    assert moc("hang_ngay", ch, vn(2026, 10, 15, 8, 0), 3) == [
        "2026-10-17 09:00", "2026-10-18 09:00", "2026-10-24 09:00"]


def test_hang_tuan_ngay_va_gio():
    ch = {"gio": ["09:00", "15:00"], "thu": [1, 3, 5]}
    assert moc("hang_tuan", ch, vn(2026, 10, 15, 10, 0), 5) == [
        "2026-10-16 09:00", "2026-10-16 15:00", "2026-10-19 09:00", "2026-10-19 15:00",
        "2026-10-21 09:00"]


def test_hang_tuan_khong_ngay_nao_thi_khong_co_moc():
    assert LQ.moc_ke("hang_tuan", {"gio": ["09:00"], "thu": []}, vn(2026, 10, 15)) is None


# ───────────────────────────── chiến dịch ─────────────────────────────
CD = {"tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-22T22:00", "moi_phut": 60}


def test_chien_dich_bat_dau_buoc_va_tu_ket_thuc():
    assert LQ.moc_ke("chien_dich", CD, vn(2026, 10, 15)) == vn(2026, 10, 20, 8, 0)
    assert LQ.moc_ke("chien_dich", CD, vn(2026, 10, 20, 8, 0)) == vn(2026, 10, 20, 9, 0)
    assert LQ.moc_ke("chien_dich", CD, vn(2026, 10, 22, 21, 30)) == vn(2026, 10, 22, 22, 0)
    assert LQ.moc_ke("chien_dich", CD, vn(2026, 10, 22, 22, 0)) is None     # hết khung
    assert LQ.dem_moc("chien_dich", CD, vn(2026, 10, 1), vn(2026, 11, 1)) == 63  # 08:00→22:00 ×3 ngày


def test_chien_dich_buoc_le_phut():
    ch = {**CD, "moi_phut": 45}
    assert moc("chien_dich", ch, vn(2026, 10, 20, 8, 10), 3) == [
        "2026-10-20 08:45", "2026-10-20 09:30", "2026-10-20 10:15"]
    assert LQ.luot_moi_ngay("chien_dich", ch) == 32


def test_ranh_gioi_thang_nam_va_nam_nhuan():
    assert LQ.moc_ke("hang_ngay", {"gio": ["00:15"], "thu": []}, vn(2026, 12, 31, 23, 0)) == \
        vn(2027, 1, 1, 0, 15)
    assert LQ.moc_ke("moi_n_gio", NAM_HAI, vn(2026, 10, 31, 23, 30)) == vn(2026, 11, 1, 7, 0)
    ch = {"tu_luc": "2026-12-31T22:00", "den_luc": "2027-01-01T02:00", "moi_phut": 120}
    assert moc("chien_dich", ch, vn(2026, 12, 31, 21), 5) == [
        "2026-12-31 22:00", "2027-01-01 00:00", "2027-01-01 02:00"]
    # 2028 nhuận: thứ Ba 29/02/2028 có mặt
    assert LQ.moc_ke("hang_tuan", {"gio": ["09:00"], "thu": [2]}, vn(2028, 2, 28, 10)) == \
        vn(2028, 2, 29, 9, 0)


def test_gio_viet_nam_khong_phu_thuoc_mui_gio_dau_vao():
    """Kho trả TIMESTAMPTZ theo UTC: 01:00Z = 08:00 VN; kết quả luôn giờ VN (+07, không DST)."""
    x = LQ.moc_ke("moi_n_gio", NAM_HAI, dt.datetime(2026, 10, 15, 1, 0, tzinfo=UTC))
    assert x == vn(2026, 10, 15, 9, 0) and x.utcoffset() == dt.timedelta(hours=7)
    # giữa năm (mùa hè nơi khác) vẫn +07
    assert LQ.moc_ke("hang_ngay", {"gio": ["07:00"]}, vn(2026, 6, 30, 8)).utcoffset() == \
        dt.timedelta(hours=7)


def test_cau_hinh_hong_khong_lap_vo_han():
    assert LQ.moc_ke("hang_ngay", {"gio": ["07:00"], "thu": [9]}, vn(2026, 10, 15)) is None
    assert LQ.moc_ke("moi_n_gio", {"moi_gio": 5}, vn(2026, 10, 15)) is None
    assert LQ.moc_ke("chien_dich", {"tu_luc": "rác"}, vn(2026, 10, 15)) is None
    assert LQ.moc_ke("la", {}, vn(2026, 10, 15)) is None
    assert LQ.moc_ke("hang_ngay", "không phải dict", vn(2026, 10, 15)) is None


# ───────────────────────────── kiểm biểu mẫu ─────────────────────────────
BAY_GIO = vn(2026, 10, 15, 8, 30)


def test_chuan_hoa_moi_n_gio_va_ten_tu_dong():
    d = LQ.chuan_hoa({"kieu": "moi_n_gio", "moi_gio": "2", "tu": "7:00", "den": "23:00",
                      "thu_1": "1", "thu_5": "on", "bat": "1"}, BAY_GIO)
    assert d["cau_hinh"] == {"moi_gio": 2, "tu": "07:00", "den": "23:00", "thu": [1, 5]}
    assert d["ten"] == "Mỗi 2 giờ, 07:00–23:00, T2, T6" and d["bat"] and not d["quet_moi_nguon"]


def test_chuan_hoa_gio_sap_bo_trung():
    d = LQ.chuan_hoa({"kieu": "hang_ngay", "gio": "19:30, 07:00;07:00  12:00", "ten": " Sáng "},
                     BAY_GIO)
    assert d["cau_hinh"]["gio"] == ["07:00", "12:00", "19:30"] and d["ten"] == "Sáng"


def test_chuan_hoa_chien_dich_don_vi_gio():
    d = LQ.chuan_hoa({"kieu": "chien_dich", "tu_luc": "2026-10-20T08:00",
                      "den_luc": "2026-10-22 22:00", "moi": "2", "don_vi": "gio",
                      "quet_moi_nguon": "1"}, BAY_GIO)
    assert d["cau_hinh"] == {"tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-22T22:00",
                             "moi_phut": 120}
    assert d["quet_moi_nguon"] and d["ten"].startswith("Chiến dịch 20/10 08:00 → 22/10 22:00")


@pytest.mark.parametrize("form, loi", [
    ({"kieu": "moi_ngay"}, "Chọn kiểu lịch"),
    ({"kieu": "moi_n_gio", "moi_gio": "5"}, "N là 1, 2, 3"),
    ({"kieu": "moi_n_gio", "moi_gio": "0"}, "N là 1, 2, 3"),
    ({"kieu": "moi_n_gio", "moi_gio": "2", "tu": "22:00", "den": "07:00"}, "giờ kết thúc"),
    ({"kieu": "moi_n_gio", "moi_gio": "2", "tu": "25:00"}, "HH:MM"),
    ({"kieu": "hang_ngay", "gio": ""}, "Chưa nhập giờ"),
    ({"kieu": "hang_ngay", "gio": "7h"}, "HH:MM"),
    ({"kieu": "hang_ngay", "gio": ", ".join(f"{h:02d}:{m:02d}" for h in range(24)
                                              for m in (0, 10, 20, 30, 40))}, "Tối đa 96"),
    ({"kieu": "hang_tuan", "gio": "09:00"}, "ít nhất một ngày"),
    ({"kieu": "chien_dich", "tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-20T08:00",
      "moi": "60"}, "sau thời điểm bắt đầu"),
    ({"kieu": "chien_dich", "tu_luc": "2026-10-01T08:00", "den_luc": "2026-10-10T08:00",
      "moi": "60"}, "đã kết thúc"),
    ({"kieu": "chien_dich", "tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-21T08:00",
      "moi": "20", "don_vi": "phut"}, "tối thiểu 30 phút"),
    ({"kieu": "chien_dich", "tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-21T08:00",
      "moi": "0", "don_vi": "gio"}, "khoảng cách"),
    ({"kieu": "chien_dich", "tu_luc": "2026-10-20T08:00", "den_luc": "2027-03-01T08:00",
      "moi": "1", "don_vi": "gio"}, "tối đa 92 ngày"),
    ({"kieu": "chien_dich", "tu_luc": "2026-02-30T08:00", "den_luc": "2026-10-21T08:00",
      "moi": "1", "don_vi": "gio"}, "không phải ngày giờ có thật"),
    ({"kieu": "chien_dich", "tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-20T09:00",
      "moi": "2", "don_vi": "gio"}, None),    # mốc duy nhất 08:00 còn trong tương lai -> hợp lệ
])
def test_chuan_hoa_tu_choi_cau_hinh_sai(form, loi):
    if loi is None:
        assert LQ.chuan_hoa(form, BAY_GIO)["cau_hinh"]["moi_phut"] == 120
        return
    with pytest.raises(LQ.LoiLich) as e:
        LQ.chuan_hoa(form, BAY_GIO)
    assert loi in str(e.value)


def test_chuan_hoa_chien_dich_khong_con_moc():
    """Đang giữa chiến dịch mà bước dài hơn phần còn lại: không còn mốc nào -> báo rõ."""
    with pytest.raises(LQ.LoiLich, match="không còn mốc"):
        LQ.chuan_hoa({"kieu": "chien_dich", "tu_luc": "2026-10-15T08:00",
                      "den_luc": "2026-10-15T09:00", "moi": "2", "don_vi": "gio"}, BAY_GIO)


def test_form_qua_lai_giu_nguyen_cau_hinh():
    for kieu, ch in (("moi_n_gio", {"moi_gio": 3, "tu": "08:00", "den": "20:00", "thu": [6, 7]}),
                     ("hang_tuan", {"gio": ["09:00", "18:30"], "thu": [2, 4]}),
                     ("chien_dich", {"tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-22T22:00",
                                     "moi_phut": 90})):
        lich = {"kieu": kieu, "cau_hinh": ch, "ten": "x", "bat": True, "quet_moi_nguon": True}
        d = LQ.chuan_hoa(LQ.bieu_mau(LQ.tu_form(lich, BAY_GIO)), BAY_GIO)
        assert d["cau_hinh"] == ch and d["quet_moi_nguon"] and d["bat"], kieu
    mac = LQ.tu_form_mac_dinh(BAY_GIO)
    assert LQ.chuan_hoa(LQ.bieu_mau(mac), BAY_GIO)["kieu"] == "moi_n_gio"
    # biểu mẫu gửi lên bị từ chối: vẽ lại đúng chữ đã gõ
    g = LQ.gia_tri_tu_form({"kieu": "hang_ngay", "gio": "7h sáng", "thu_3": "1"}, BAY_GIO)
    assert g["gio"] == "7h sáng" and g["thu"] == [3] and not g["bat"]


# ───────────────────────────── nhịp quét ─────────────────────────────
GIO_1 = {"moi_gio": 1, "tu": "00:00", "den": "23:59", "thu": []}


def test_quyet_dinh_chua_toi_han_khong_doi_gi():
    ke = vn(2026, 10, 15, 10, 0)
    assert LQ.quyet_dinh("moi_n_gio", GIO_1, ke, vn(2026, 10, 15, 9, 59)) == (None, None, ke)
    assert LQ.quyet_dinh("moi_n_gio", GIO_1, None, vn(2026, 10, 15, 9, 59)) == (None, None, None)


def test_quyet_dinh_dung_gio_chay_va_doi_moc_ke():
    chay, lo, ke = LQ.quyet_dinh("moi_n_gio", GIO_1, vn(2026, 10, 15, 10),
                                 vn(2026, 10, 15, 10, 0, 20))
    assert (chay, lo, ke) == (vn(2026, 10, 15, 10), None, vn(2026, 10, 15, 11))
    # nhịp sau: mốc kế ở tương lai -> không chạy lần hai
    assert LQ.quyet_dinh("moi_n_gio", GIO_1, ke, vn(2026, 10, 15, 10, 0, 50))[0] is None


def test_quyet_dinh_mark_tat_lau_chi_chay_bu_mot_lan_moc_moi_nhat():
    """Mark tắt 10:00 → 12:10: lỡ 10:00, 11:00, 12:00 — chạy MỘT lần cho 12:00 (lỡ 10 phút)."""
    chay, lo, ke = LQ.quyet_dinh("moi_n_gio", GIO_1, vn(2026, 10, 15, 10),
                                 vn(2026, 10, 15, 12, 10))
    assert (chay, lo, ke) == (vn(2026, 10, 15, 12), None, vn(2026, 10, 15, 13))


def test_quyet_dinh_lo_qua_30_phut_thi_bo():
    chay, lo, ke = LQ.quyet_dinh("moi_n_gio", NAM_HAI, vn(2026, 10, 15, 9),
                                 vn(2026, 10, 15, 9, 45))
    assert chay is None and lo == vn(2026, 10, 15, 9) and ke == vn(2026, 10, 15, 11)
    # lỡ đúng 30 phút vẫn còn trong cửa sổ
    assert LQ.quyet_dinh("moi_n_gio", NAM_HAI, vn(2026, 10, 15, 9),
                         vn(2026, 10, 15, 9, 30))[0] == vn(2026, 10, 15, 9)
    # Mark tắt qua đêm: mốc 23:00 hôm trước lỡ, 07:00 sáng nay còn trong cửa sổ -> chạy 07:00
    assert LQ.quyet_dinh("moi_n_gio", NAM_HAI, vn(2026, 10, 14, 23),
                         vn(2026, 10, 15, 7, 5))[:2] == (vn(2026, 10, 15, 7), None)


def test_quyet_dinh_chien_dich_moc_cuoi_roi_het():
    chay, _lo, ke = LQ.quyet_dinh("chien_dich", CD, vn(2026, 10, 22, 22),
                                  vn(2026, 10, 22, 22, 0, 30))
    assert chay == vn(2026, 10, 22, 22) and ke is None


# ───────────────────────────── chiến dịch ưu tiên + trạng thái ─────────────────────────────
def _l(i, kieu, ch, bat=True):
    return {"id": i, "kieu": kieu, "cau_hinh": ch, "bat": bat}


def test_dem_luot_du_an_lich_thuong_nhuong_chien_dich():
    thuong = _l(1, "moi_n_gio", GIO_1)
    cd = _l(2, "chien_dich", {"tu_luc": "2026-10-16T00:00", "den_luc": "2026-10-16T23:59",
                              "moi_phut": 30})
    tu, den = vn(2026, 10, 15, 23, 59), vn(2026, 10, 17, 0, 0)
    assert LQ.dem_luot_du_an([thuong], tu, den) == {1: 25}           # 16/10 cả ngày + 17/10 00:00
    assert LQ.dem_luot_du_an([thuong, cd], tu, den) == {1: 1, 2: 48}
    assert LQ.dem_luot_du_an([thuong, {**cd, "bat": False}], tu, den) == {1: 25}


def test_trang_thai_va_chien_dich_dang_chay():
    thuong = _l(1, "moi_n_gio", GIO_1)
    cd = _l(2, "chien_dich", CD)
    ds = [thuong, cd]
    assert LQ.trang_thai(cd, ds, vn(2026, 10, 15))[0] == "cho_chien_dich"
    assert LQ.trang_thai(thuong, ds, vn(2026, 10, 15))[0] == "bat"
    assert LQ.trang_thai(cd, ds, vn(2026, 10, 21))[0] == "dang_chien_dich"
    assert LQ.trang_thai(thuong, ds, vn(2026, 10, 21)) == ("nhuong", "Nhường chiến dịch #2")
    assert LQ.trang_thai(cd, ds, vn(2026, 10, 23)) == ("ket_thuc", "Đã kết thúc")
    assert LQ.trang_thai({**thuong, "bat": False}, ds, vn(2026, 10, 21))[0] == "tat"
    assert LQ.chien_dich_dang_chay(ds, vn(2026, 10, 21))["id"] == 2
    assert LQ.chien_dich_dang_chay([thuong, {**cd, "bat": False}], vn(2026, 10, 21)) is None


# ───────────────────────────── chữ hiển thị ─────────────────────────────
@pytest.mark.parametrize("thu, chu", [([], "mọi ngày"), ([1, 2, 3, 4, 5], "T2–T6"),
                                      ([6, 7], "T7, CN"), ([1, 3, 5], "T2, T4, T6"),
                                      ([1, 2, 3, 5], "T2–T4, T6"), (list(range(1, 8)), "mọi ngày")])
def test_chu_thu(thu, chu):
    assert LQ.chu_thu(thu) == chu


def test_chu_moc_va_khoang():
    b = vn(2026, 10, 15, 8, 30)
    assert LQ.chu_moc(vn(2026, 10, 15, 16), b) == "Hôm nay 16:00"
    assert LQ.chu_moc(vn(2026, 10, 16, 7), b) == "Mai 07:00"
    assert LQ.chu_moc(vn(2026, 10, 19, 7), b) == "T2 19/10 07:00"
    assert LQ.chu_moc(vn(2027, 1, 4, 7), b) == "T2 04/01/2027 07:00"
    assert LQ.chu_con(vn(2026, 10, 15, 9, 15), b) == "còn 45 phút"
    assert LQ.chu_con(vn(2026, 10, 15, 10, 45), b) == "còn 2 giờ 15 phút"
    assert LQ.chu_con(vn(2026, 10, 18, 8, 30), b) == "còn 3 ngày"
    assert LQ.moc_gan_qua("hang_ngay", {"gio": ["07:00", "07:20"]})
    assert not LQ.moc_gan_qua("moi_n_gio", NAM_HAI)
