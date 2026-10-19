"""Luật phân quyền theo bên (19/10/2026, `dashboard/phan_quyen.py`) — thuần, dùng chung cho kho thật
(kiểm trong giao dịch), app và kho giả của bộ thử."""
from __future__ import annotations

import pytest

from dashboard import phan_quyen as PQ

QT = {"la_quan_tri": True, "ben": {}}
QL_HP = {"la_quan_tri": False, "ben": {"hapas": "quan_ly", "matemade": "xem"}}
XEM_MM = {"la_quan_tri": False, "ben": {"matemade": "xem"}}
DS = [{"ma": "hapas", "don_vi": "hapas"}, {"ma": "mm", "don_vi": "matemade"},
      {"ma": "khac", "don_vi": "ben-moi"}]


def test_khong_co_co_quan_tri_va_khong_ben_thi_khong_vao_duoc():
    assert not PQ.co_quyen(None) and not PQ.co_quyen({"la_quan_tri": False, "ben": {}})
    assert PQ.vai_chung({"la_quan_tri": False, "ben": {}}) is None
    assert PQ.chuan({"la_quan_tri": None, "ben": {"hapas": "chu"}}) == {"la_quan_tri": False,
                                                                       "ben": {}}


def test_pham_vi_doc_sua_theo_ben():
    assert PQ.pham_vi(QT, DS) == {"doc": {"hapas", "mm", "khac"}, "sua": {"hapas", "mm", "khac"},
                                  "ben_doc": None, "ben_sua": None}
    assert PQ.pham_vi(QL_HP, DS) == {"doc": {"hapas", "mm"}, "sua": {"hapas"},
                                     "ben_doc": {"hapas", "matemade"}, "ben_sua": {"hapas"}}
    assert PQ.pham_vi(XEM_MM, DS)["doc"] == {"mm"} and PQ.pham_vi(XEM_MM, DS)["sua"] == set()
    assert not PQ.doc_duoc(XEM_MM, {"ma": "x"})                  # dự án thiếu bên: chỉ quản trị
    assert PQ.vai_chung(QL_HP) == "quan_ly" and PQ.vai_chung(XEM_MM) == "xem"
    assert PQ.nhan_vai(QL_HP, {"hapas": "HAPAS"}) == "HAPAS: Quản lý · MATEMADE: Chỉ xem"
    assert PQ.nhan_vai(QT) == "Quản trị viên"
    assert PQ.ben_quan_ly(QT, ["a", "b"]) == ["a", "b"] and PQ.ben_quan_ly(QL_HP) == ["hapas"]


@pytest.mark.parametrize("ham", [
    lambda: PQ.kiem_dat_quan_tri(QL_HP, None, True, 3),
    lambda: PQ.kiem_xoa_nguoi(QL_HP, XEM_MM, 3),
    lambda: PQ.kiem_tao_ben(QL_HP),
    lambda: PQ.kiem_luu_quyen(QL_HP, "a@x.vn", None, "b@x.vn", "hapas", "quan_ly"),
    lambda: PQ.kiem_luu_quyen(QL_HP, "a@x.vn", None, "b@x.vn", "matemade", "xem"),
    lambda: PQ.kiem_xoa_quyen(QL_HP, "a@x.vn", XEM_MM, "b@x.vn", "matemade"),
    lambda: PQ.kiem_dat_quan_tri(QT, QT, False, 0),               # quản trị viên cuối
    lambda: PQ.kiem_xoa_nguoi(PQ.HE_THONG, QT, 0),                # lệnh máy chủ cũng không xoá
])
def test_luat_chan(ham):
    with pytest.raises(PQ.LoiQuyen):
        ham()


def test_luat_cho_phep():
    PQ.kiem_luu_quyen(QL_HP, "a@x.vn", None, "b@x.vn", "hapas", "xem")
    PQ.kiem_xoa_quyen(QL_HP, "a@x.vn", {"la_quan_tri": False, "ben": {"hapas": "xem"}},
                      "b@x.vn", "hapas")
    PQ.kiem_luu_quyen(QT, "a@x.vn", QL_HP, "b@x.vn", "matemade", "quan_ly")
    PQ.kiem_dat_quan_tri(QT, QT, False, 1)
    PQ.kiem_luu_quyen(PQ.HE_THONG, "cli:x", None, "b@x.vn", "hapas", "quan_ly")
