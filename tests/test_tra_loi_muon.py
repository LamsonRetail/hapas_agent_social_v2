"""Lượt quá hạn của vòng job: gửi BÙ câu trả lời khi lượt chạy xong.

Sự cố 01/10/2026: lượt "khảo sát độ phủ HAPAS" chạy 617 giây, quá trần 480 giây. Người
dùng nhận câu xin lỗi; lượt vẫn chạy nốt, ra 31 bài + Sheet — rồi bị bỏ. Người dùng hỏi
lại, cào lần hai, trả tiền hai lần.
"""
from __future__ import annotations

import pathlib
import sys
import threading
import time

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

LARK = "lark:cli_app:oc_nhom1"


@pytest.fixture
def LP(monkeypatch):
    m = pytest.importorskip("lsr_platform")
    V = pytest.importorskip("viec_nen")
    monkeypatch.setattr(m, "_HAN_TRA_LOI", 0.2)
    monkeypatch.setattr(m, "_ngu", lambda s: None)
    gui: list = []
    xong = threading.Event()

    def day(k, van, kid):
        gui.append((dict(k), van, kid))
        xong.set()
        return True
    monkeypatch.setattr(V, "day_theo_kenh", day)
    m._gui_test, m._xong_test = gui, xong
    return m


def _cham(giay=0.6, dap="31 bài, Sheet: https://x/sheets/abc"):
    def f(h, chat_id=None, sender_open_id=None, **_):
        time.sleep(giay)
        return dap
    return f


def test_qua_han_tren_lark_hua_gui_bu_roi_gui_dung_mot_lan(LP):
    dap, ok, treo = LP._chay_co_han(_cham(), "khảo sát độ phủ hapas", LARK, "ou_1",
                                    {"chat_type": "group"}, job_id=7)
    assert treo and not ok
    assert "không cần hỏi lại" in dap, "đã hứa gửi bù thì đừng bảo người dùng hỏi lại"
    assert LP._xong_test.wait(3), "lượt xong muộn phải được gửi bù"
    time.sleep(0.1)
    assert len(LP._gui_test) == 1
    k, van, kid = LP._gui_test[0]
    assert k["loai"] == "lark_gateway" and k["oc"] == "oc_nhom1" and k["app_id"] == "cli_app"
    assert van.startswith("Trả lời muộn cho câu “khảo sát độ phủ hapas”")
    assert "https://x/sheets/abc" in van
    assert kid == "j7-muon", "mã khử trùng cố định theo job — gửi lại không ra hai tin"


def test_qua_han_tren_web_gui_vao_job_goc(LP):
    LP._chay_co_han(_cham(), "hỏi", "e2e-abc", None, job_id=55)
    assert LP._xong_test.wait(3)
    k, _, _ = LP._gui_test[0]
    assert k["loai"] == "web" and k["job_id"] == 55


def test_phien_khong_day_duoc_giu_cau_cu_va_khong_gui(LP):
    dap, _, treo = LP._chay_co_han(_cham(0.4), "hỏi", "hoiquy-1", None, job_id=9)
    assert treo and ("thử hỏi lại" in dap or "thu hẹp" in dap)
    time.sleep(0.6)
    assert LP._gui_test == [], "hồi quy/bộ thử không có kênh đẩy — không gửi gì"


def test_luot_nhanh_khong_gui_bu(LP):
    dap, ok, treo = LP._chay_co_han(_cham(0.0, "nhanh"), "hỏi", LARK, None, job_id=1)
    assert (dap, ok, treo) == ("nhanh", True, False)
    time.sleep(0.2)
    assert LP._gui_test == []


def test_luot_muon_loi_thi_bao_loi_chu_khong_im(LP):
    def no(h, chat_id=None, sender_open_id=None, **_):
        time.sleep(0.5)
        raise RuntimeError("model hỏng")
    LP._chay_co_han(no, "hỏi gì đó", LARK, None, job_id=3)
    assert LP._xong_test.wait(3)
    _, van, _ = LP._gui_test[0]
    assert "gặp lỗi" in van and "hỏi lại" in van
    assert "model hỏng" not in van, "không lộ lỗi nội bộ cho người dùng"


def test_gui_bu_loi_mang_thi_thu_lai(LP, monkeypatch):
    V = sys.modules["viec_nen"]
    lan = []

    def hong_hai_lan(k, van, kid):
        lan.append(kid)
        if len(lan) < 3:
            raise OSError("mạng chập")
        LP._xong_test.set()
        return True
    monkeypatch.setattr(V, "day_theo_kenh", hong_hai_lan)
    LP._chay_co_han(_cham(0.4), "hỏi", LARK, None, job_id=4)
    assert LP._xong_test.wait(3)
    assert lan == ["j4-muon"] * 3, "thử lại cùng mã khử trùng"


def test_cau_hoi_dai_bi_cat_gon(LP):
    LP._chay_co_han(_cham(), "a " * 200, LARK, None, job_id=5)
    assert LP._xong_test.wait(3)
    _, van, _ = LP._gui_test[0]
    assert len(van.split("\n", 1)[0]) < 120


def test_kenh_tu_chat_khop_kenh_hien_tai():
    V = pytest.importorskip("viec_nen")
    assert V.kenh_tu_chat(LARK)["loai"] == "lark_gateway"
    assert V.kenh_tu_chat("oc_abc")["loai"] == "lark_truc_tiep"
    assert V.kenh_tu_chat("hoiquy-1", 5)["loai"] == "khac"
    assert V.kenh_tu_chat("web-xyz", 5)["loai"] == "web"
    assert V.kenh_tu_chat("web-xyz", None)["loai"] == "khac"
    assert not V.co_the_day(V.kenh_tu_chat(""))
