"""Số tụt về 0 (19/10/2026): bài TikTok @quynhphaken 1.387 bình luận, lượt 07:00 ghi thành 0 dù
TikTok vẫn hiện 1.389 (bình luận bật, lượt xem vẫn tăng). Parser đổi trường thiếu thành 0
(`int(x or 0)`) → `lang_nghe_db` giữ số cũ khi bài đã có số > 0 mà lượt mới trả đúng 0, và ảnh
chụp `chi_so_ngay` ghi số ĐÃ GIỮ (số trả về từ `bai`), không phải số 0 thô.

Biểu thức SQL `_GIU_KHI_VE_0` đã chạy thật trên Postgres (VPS, 19/10/2026) với bảng giá trị
(mới, cũ) → kết quả: (0, 1387) → 1387, (1389, 1387) → 1389, (NULL, 1387) → 1387, (0, 0) → 0,
(0, NULL) → 0, (5, NULL) → 5, (NULL, NULL) → NULL, (3, 10) → 3. Ở đây kiểm phần Python: câu SQL
dùng đúng biểu thức và số ghi vào `chi_so_ngay` lấy từ RETURNING."""
from __future__ import annotations

import datetime

import pytest

import lang_nghe_db as K

_VN = datetime.timezone(datetime.timedelta(hours=7))


def _giu(moi, cu):
    """Bản Python của `_GIU_KHI_VE_0` (để kho giả trả đúng số Postgres trả)."""
    if moi == 0 and cu is not None and cu > 0:
        return cu
    return cu if moi is None else moi


class KhoGia:
    def __init__(self, bai):
        self.bai = {r["khoa"]: dict(r) for r in bai}
        self.anh: list[list] = []
        self.cau: list[str] = []
        self._kq: list = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, ts=()):
        self.cau.append(sql)
        ts = list(ts)
        if sql.startswith("INSERT INTO bai"):
            khoa = ts[4]
            dau = 4 + K._COT_BAI.index("xem")
            moi = dict(zip(K._SO, ts[dau:dau + 4]))
            cu = self.bai.get(khoa)
            if cu is None:
                self.bai[khoa] = {"khoa": khoa, **moi}
                self._kq = [{"moi": True, **moi}]
            else:
                for k in K._SO:
                    cu[k] = _giu(moi[k], cu.get(k))
                self._kq = [{"moi": False, **{k: cu[k] for k in K._SO}}]
        elif sql.startswith("UPDATE bai SET"):
            khoa = ts[-1]
            cu = self.bai.get(khoa)
            if cu is None:
                self._kq = []
            else:
                for k, v in zip(K._SO, ts[:4]):
                    cu[k] = _giu(v, cu.get(k))
                self._kq = [{"khoa": khoa, **{k: cu[k] for k in K._SO}}]
        elif sql.startswith("INSERT INTO chi_so_ngay"):
            self.anh.append(ts[3:7])
            self._kq = []
        else:
            raise AssertionError(f"câu SQL lạ: {sql[:80]}")
        return self

    def fetchone(self):
        return self._kq[0] if self._kq else None


@pytest.fixture
def kho(monkeypatch):
    def tao(bai=()):
        k = KhoGia(bai)
        monkeypatch.setattr(K, "ket_noi", lambda: k)
        return k
    return tao


KHOA = "tiktok:7692036197492739346"
CU = {"khoa": KHOA, "xem": 4652352, "thich": 307000, "binh_luan": 1387, "chia_se": 8400}


def _dong(**kw):
    r = {"khoa": KHOA, "nen_tang": "tiktok", "link": "https://www.tiktok.com/@quynhphaken/video/1",
         "tac_gia": "Quỳnh phá kén", "tai_khoan": "quynhphaken",
         "dang_luc": datetime.datetime(2026, 10, 2, 18, 49, tzinfo=_VN), "noi_dung": "20/10",
         "xem": 4672726, "thich": 307417, "binh_luan": 0, "chia_se": 8455}
    r.update(kw)
    return r


def test_cau_sql_dung_bieu_thuc_giu_so(kho):
    k = kho([CU])
    K.ghi_bai("hapas", 20, "tu_khoa", [_dong()])
    K.cap_nhat_so_lieu("hapas", 20, [{"khoa": KHOA, "xem": 1, "thich": 1, "binh_luan": 0,
                                      "chia_se": 1}])
    ghi, sua = k.cau[0], k.cau[2]
    for c in K._SO:
        assert (f"{c} = COALESCE(NULLIF(EXCLUDED.{c}, CASE WHEN bai.{c} > 0 THEN 0 END), "
                f"bai.{c})") in ghi
        assert f"{c} = COALESCE(NULLIF(%s::bigint, CASE WHEN {c} > 0 THEN 0 END), {c})" in sua
    assert "RETURNING (xmax = 0) AS moi, xem, thich, binh_luan, chia_se" in ghi
    assert "RETURNING khoa, xem, thich, binh_luan, chia_se" in sua


def test_ghi_bai_tut_ve_0_giu_so_cu_ca_anh_chup_ngay(kho):
    k = kho([CU])
    assert K.ghi_bai("hapas", 20, "tu_khoa", [_dong()]) == (0, 1)
    assert k.bai[KHOA]["binh_luan"] == 1387 and k.bai[KHOA]["xem"] == 4672726
    assert k.anh == [[4672726, 307417, 1387, 8455]], "ảnh chụp ngày ghi số đã giữ, không phải 0"


def test_cap_nhat_so_lieu_tut_ve_0_giu_so_cu(kho):
    k = kho([CU])
    assert K.cap_nhat_so_lieu("hapas", 20, [{"khoa": KHOA, "xem": 4672726, "thich": 0,
                                             "binh_luan": 0, "chia_se": None}]) == 1
    assert k.bai[KHOA]["binh_luan"] == 1387 and k.bai[KHOA]["thich"] == 307000
    # Cột lượt này không đọc (chia_se None) vẫn để NULL trong ảnh chụp như trước.
    assert k.anh == [[4672726, 307000, 1387, None]]


def test_so_that_van_ghi_de(kho):
    k = kho([CU])
    K.ghi_bai("hapas", 20, "tu_khoa", [_dong(binh_luan=1389)])
    assert k.bai[KHOA]["binh_luan"] == 1389 and k.anh[-1][2] == 1389
    # Bài mới mà nguồn trả 0 (chưa có số cũ) thì 0 là 0.
    k = kho()
    assert K.ghi_bai("hapas", 20, "tu_khoa", [_dong()]) == (1, 0)
    assert k.bai[KHOA]["binh_luan"] == 0 and k.anh == [[4672726, 307417, 0, 8455]]


def test_ket_qua_khong_phai_dict_thi_dung_so_luot_nay():
    """Kho giả cũ chỉ trả {"moi": ...}: không vỡ, dùng số của lượt như trước."""
    r = {"xem": 5, "thich": None, "binh_luan": 0, "chia_se": 2}
    assert K._so_da_giu({"moi": False}, r) == [5, None, 0, 2]
    assert K._so_da_giu(None, r) == [5, None, 0, 2]
    assert K._so_da_giu({"moi": False, "xem": 9, "thich": 3, "binh_luan": 7, "chia_se": 2}, r) \
        == [9, None, 7, 2]
