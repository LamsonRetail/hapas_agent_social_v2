"""Tin Lark rơi vào listener của Mark (không qua gateway) phải dùng ĐÚNG phiên gateway.

Sự cố 05/10/2026 13:58: Lark chia sự kiện giữa kết nối gateway platform và listener của
Mark. "tìm ad tiktok viral 2/10–5/10" đi gateway (phiên `lark:<app>:oc_…`), Mark đề xuất
Top Ads 7 ngày; "ok chốt" rơi vào listener (phiên `oc_…`) — Mark không thấy đề xuất vừa
đưa, đọc lịch sử cũ của phiên `oc_…` rồi chạy Meta Ad Library + social 30 ngày về HAPAS.
"""
from __future__ import annotations

import pathlib
import sys
import types

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

OC = "oc_4a3e0000000000000000000000000000"


@pytest.fixture
def R(monkeypatch):
    run = pytest.importorskip("run")
    import lsr_platform as LP
    monkeypatch.setattr(run.config, "app_id", "cli_app_mark", raising=False)
    gui, goi = [], []
    monkeypatch.setattr(run.lark, "send_text", lambda *a, **k: gui.append(a))
    monkeypatch.setattr(run.lark, "add_reaction", lambda *a, **k: None)
    monkeypatch.setattr(run.lark, "remove_reaction", lambda *a, **k: None)
    monkeypatch.setattr(LP, "bao_luot", lambda *a, **k: None)

    def tra_loi(text, chat_id=None, sender_open_id=None, kenh=None):
        goi.append({"text": text, "chat_id": chat_id, "kenh": kenh})
        return "đáp"
    monkeypatch.setitem(sys.modules, "brain", types.SimpleNamespace(reply=tra_loi))
    run._gui_test, run._goi_test = gui, goi
    return run


def _gateway(monkeypatch, bat: bool):
    import lsr_platform as LP
    monkeypatch.setattr(LP, "_cau_hinh", lambda: {"agent_id": "AG-X"} if bat else None)
    monkeypatch.setattr(LP, "_job_poll_duoc_phep", lambda c: bat)


def test_co_gateway_dung_phien_gateway_va_kieu_chat(R, monkeypatch):
    _gateway(monkeypatch, True)
    R._do_reply({"chat_id": OC, "message_id": "om_1", "sender_id": "ou_1",
                 "text": "ok chốt", "message_type": "text", "chat_type": "p2p"})
    assert R._goi_test == [{"text": "ok chốt", "chat_id": f"lark:cli_app_mark:{OC}",
                            "kenh": {"chat_type": "p2p"}}]
    assert R._gui_test and R._gui_test[0][1] == OC, "vẫn trả lời thẳng vào chat Lark"


def test_nhom_cung_ra_group(R, monkeypatch):
    _gateway(monkeypatch, True)
    R._do_reply({"chat_id": OC, "message_id": "om_2", "text": "hi",
                 "message_type": "text", "chat_type": "group"})
    assert R._goi_test[0]["kenh"] == {"chat_type": "group"}


def test_khong_platform_giu_nguyen_duong_cu(R, monkeypatch):
    _gateway(monkeypatch, False)
    R._do_reply({"chat_id": OC, "message_id": "om_3", "text": "hi",
                 "message_type": "text", "chat_type": "p2p"})
    assert R._goi_test[0]["chat_id"] == OC and R._goi_test[0]["kenh"] is None


def test_phien_lark_chi_doi_chat_oc(R, monkeypatch):
    _gateway(monkeypatch, True)
    assert R._phien_lark(OC) == f"lark:cli_app_mark:{OC}"
    assert R._phien_lark("ou_abc") == "ou_abc"
    assert R._phien_lark("") == ""


def test_qua_han_khong_danh_dau_loi_va_khong_lay_so_luot_dang_chay(R, monkeypatch):
    """Quá hạn = Mark vẫn làm tiếp và sẽ gửi bù — không gắn CrossMark, không cướp sổ."""
    import lsr_platform as LP
    _gateway(monkeypatch, True)
    monkeypatch.setattr(LP, "_chay_co_han",
                        lambda *a, **k: ("Mark vẫn đang làm tiếp", False, True))
    phan_ung, lay = [], []
    monkeypatch.setattr(R.lark, "add_reaction", lambda mid, e: phan_ung.append(e) or "r1")
    monkeypatch.setattr(LP, "lay_model_vua_chay", lambda c: lay.append(c) or "m")
    monkeypatch.setenv("AGENT_TYPING_BADGE", "1")
    R._do_reply({"chat_id": OC, "message_id": "om_4", "text": "quét lớn",
                 "message_type": "text", "chat_type": "p2p"})
    assert "CrossMark" not in phan_ung
    assert lay == []
    assert R._gui_test[0][2] == "Mark vẫn đang làm tiếp"


# ───────────────────── một lượt mỗi phiên (gateway ↔ listener) ─────────────────────
import threading  # noqa: E402
import time  # noqa: E402


@pytest.fixture
def LPk(monkeypatch):
    import lsr_platform as LP
    monkeypatch.setattr(LP, "_HAN_TRA_LOI", 2.0)
    monkeypatch.setattr(LP, "_KHOA_PHIEN", {})
    return LP


def _do_chong(LP, phien_a, phien_b):
    dang, max_dong = [0], [0]
    kh = threading.Lock()

    def tra_loi(h, chat_id=None, sender_open_id=None, **_):
        with kh:
            dang[0] += 1
            max_dong[0] = max(max_dong[0], dang[0])
        time.sleep(0.3)
        with kh:
            dang[0] -= 1
        return "ok"
    ts = [threading.Thread(target=LP._chay_co_han, args=(tra_loi, "h", p, None))
          for p in (phien_a, phien_b)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(5)
    return max_dong[0]


def test_cung_phien_khong_chay_song_song(LPk):
    assert _do_chong(LPk, "lark:a:oc_1", "lark:a:oc_1") == 1, (
        "hai lượt cùng cuộc chat (một qua gateway, một qua listener) không được chen nhau"
    )


def test_khac_phien_van_song_song(LPk):
    assert _do_chong(LPk, "lark:a:oc_1", "lark:a:oc_2") == 2


def test_luot_truoc_treo_thi_cho_nua_tran_roi_chay(LPk):
    LPk._khoa_phien("lark:a:oc_9").acquire()       # lượt trước treo, giữ khoá mãi
    t0 = time.time()
    dap, ok, treo = LPk._chay_co_han(lambda h, **_: "vẫn trả lời", "h", "lark:a:oc_9", None)
    assert (dap, ok, treo) == ("vẫn trả lời", True, False)
    assert 0.9 <= time.time() - t0 < 2.0, "chờ ~nửa trần rồi chạy, không khoá chết"


def test_canh_bao_app_lech_mot_lan(monkeypatch, capsys):
    import lsr_platform as LP
    monkeypatch.setenv("LARK_APP_ID", "cli_mark")
    monkeypatch.setattr(LP, "_APP_DA_CANH_BAO", set())
    LP._canh_bao_app_lech("lark:cli_mark:oc_1")
    assert "CẢNH BÁO" not in capsys.readouterr().out
    LP._canh_bao_app_lech("lark:cli_khac:oc_1")
    LP._canh_bao_app_lech("lark:cli_khac:oc_2")
    assert capsys.readouterr().out.count("CẢNH BÁO") == 1
    LP._canh_bao_app_lech("web-123")


def test_bang_khoa_co_chan_tren_va_khong_bo_khoa_dang_giu(LPk):
    giu = LPk._khoa_phien("dang-giu")
    giu.acquire()
    for i in range(600):
        LPk._khoa_phien(f"p{i}")
    assert len(LPk._KHOA_PHIEN) <= 501
    assert LPk._KHOA_PHIEN.get("dang-giu") is giu, "khoá đang giữ không được bỏ"
    giu.release()
