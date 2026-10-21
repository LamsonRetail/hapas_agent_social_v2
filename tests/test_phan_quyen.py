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


def test_xoa_quyen_ben_khac_khong_lo_ai_thuoc_ben_do():
    """Soát 19/10/2026: quản lý HAPAS bỏ quyền ai đó ở MATEMADE — câu báo lỗi giống nhau dù người
    đó có hay không có quyền ở MATEMADE (không dò được danh sách bên khác)."""
    loi = []
    for dich in (None, {"la_quan_tri": False, "ben": {"hapas": "xem"}}, XEM_MM):
        with pytest.raises(PQ.LoiQuyen) as e:
            PQ.kiem_xoa_quyen(QL_HP, "a@x.vn", dich, "b@x.vn", "matemade")
        loi.append(str(e.value))
    assert len(set(loi)) == 1 and loi[0].startswith("Chỉ quản trị viên hoặc quản lý")
    # Quản trị viên vẫn nhận câu rõ ràng khi người đó không có quyền ở bên.
    with pytest.raises(PQ.LoiQuyen, match="không có quyền ở bên này"):
        PQ.kiem_xoa_quyen(QT, "a@x.vn", None, "b@x.vn", "matemade")



# ─────────────── một lần Lưu = trọn quyền một người (21/10/2026) ───────────────
def _doi(lam, dich, quan_tri=None, ben=None, so_qt_khac=1, email="b@x.vn"):
    return PQ.thay_doi_quyen(lam, "a@x.vn", dich, email, quan_tri, ben or {}, so_qt_khac)


def test_thay_doi_quyen_ap_tron_bo_cho_quan_tri_vien():
    doi, sau = _doi(QT, XEM_MM, True, {"hapas": "quan_ly"})
    assert doi == [("quan_tri", None, False, True)]           # sẽ là quản trị viên: bỏ qua bên
    assert sau == {"la_quan_tri": True, "ben": {"matemade": "xem"}}
    doi, sau = _doi(QT, XEM_MM, None, {"hapas": "quan_ly", "matemade": None})
    assert doi == [("ben", "hapas", None, "quan_ly"), ("ben", "matemade", "xem", None)]
    assert sau == {"la_quan_tri": False, "ben": {"hapas": "quan_ly"}}
    # bỏ cờ + đặt bên cùng lúc (còn quản trị viên khác)
    doi, sau = _doi(QT, QT, False, {"hapas": "xem"}, so_qt_khac=1)
    assert doi == [("quan_tri", None, True, False), ("ben", "hapas", None, "xem")]
    # bên không gửi giữ nguyên; giá trị không đổi không tính -> không có gì để lưu
    with pytest.raises(PQ.LoiQuyen, match="Chưa chọn quyền nào"):
        _doi(QT, QL_HP, None, {"hapas": "quan_ly", "khac": None})
    with pytest.raises(PQ.LoiQuyen, match="Chưa chọn quyền nào"):
        _doi(QT, None, None, {"hapas": None})                  # người mới: cùng một câu


@pytest.mark.parametrize("lam, dich, qt, ben, so_qt, khop", [
    (QT, QT, False, {}, 0, "quản trị viên cuối cùng"),
    (QT, QT, False, {"hapas": "xem"}, 0, "quản trị viên cuối cùng"),
    (QL_HP, None, True, {}, 3, "Chỉ quản trị viên"),
    (QL_HP, None, None, {"hapas": "quan_ly"}, 1, "chỉ thêm được người Chỉ xem"),
    (QL_HP, None, None, {"matemade": "xem"}, 1, "quản lý của bên này"),
    (QL_HP, QT, None, {"hapas": "xem"}, 1, None),               # quản trị viên: bên bỏ qua
    (QL_HP, {"la_quan_tri": False, "ben": {"hapas": "quan_ly"}}, None, {"hapas": "xem"}, 1,
     "chỉ quản trị viên đổi được"),
    (QL_HP, {"la_quan_tri": False, "ben": {"hapas": "quan_ly"}}, None, {"hapas": None}, 1,
     "chỉ quản trị viên bỏ được"),
    # một thay đổi hợp lệ + một sai: cả lần bị từ chối
    (QL_HP, {"la_quan_tri": False, "ben": {"hapas": "xem", "matemade": "xem"}}, None,
     {"hapas": None, "matemade": None}, 1, "quản lý của bên này"),
])
def test_thay_doi_quyen_giu_moi_luat_cu(lam, dich, qt, ben, so_qt, khop):
    with pytest.raises(PQ.LoiQuyen, match=khop or "Chưa chọn quyền nào"):
        _doi(lam, dich, qt, ben, so_qt)


def test_quan_ly_khong_tu_doi_quyen_minh():
    for ben in ({"hapas": "xem"}, {"hapas": None}):
        with pytest.raises(PQ.LoiQuyen, match="chính mình"):
            PQ.thay_doi_quyen(QL_HP, "a@x.vn", QL_HP, "a@x.vn", None, ben, 1)


def test_lua_chon_ben_khop_luat():
    xem = {"la_quan_tri": False, "ben": {"hapas": "xem"}}
    assert PQ.lua_chon_ben(QT, "a@x.vn", xem, "b@x.vn", "hapas") == (["", "xem", "quan_ly"], "")
    assert PQ.lua_chon_ben(QL_HP, "a@x.vn", xem, "b@x.vn", "hapas") == (["", "xem"], "")
    assert PQ.lua_chon_ben(QL_HP, "a@x.vn", None, "", "hapas") == (["", "xem"], "")
    duoc, ly_do = PQ.lua_chon_ben(QL_HP, "a@x.vn", QT, "b@x.vn", "hapas")
    assert duoc == [""] and "quản trị viên" in ly_do
    duoc, ly_do = PQ.lua_chon_ben(QL_HP, "a@x.vn", QL_HP, "a@x.vn", "hapas")
    assert duoc == ["quan_ly"] and "chính mình" in ly_do
    assert PQ.tom_tat(QL_HP, {"hapas": "HAPAS"}) == "HAPAS · Quản lý, MATEMADE · Chỉ xem"
    assert PQ.tom_tat(QL_HP, {"hapas": "HAPAS"}, ["hapas"]) == "HAPAS · Quản lý"
    assert PQ.tom_tat(QT, {}) == "Quản trị viên"
