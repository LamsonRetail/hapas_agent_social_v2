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
