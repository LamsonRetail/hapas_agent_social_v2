"""Nhắc việc (scheduler) — sự cố 04/10/2026.

Nhắc đặt từ chat Lark qua gateway mang chat key `lark:<app>:<oc>`; bản cũ đưa nguyên
chuỗi cho Lark -> 230001 "invalid receive_id", thử lại mỗi 20 giây mãi mãi (4.271 lần).
Phải chặn:
  • chat gateway gửi qua `lsr_platform.gui_lark` với oc + app_id, chat `oc_` gửi thẳng;
  • lỗi vĩnh viễn -> đánh dấu thất bại, không thử nữa;
  • lỗi tạm -> lùi dần, tối đa 10 lần;
  • log chỉ khi trạng thái đổi;
  • nhắc trễ < 7 ngày gửi một lần kèm ghi chú trễ; trễ hơn thì thất bại.
Không chạm mạng: Lark và platform đều giả.
"""
from __future__ import annotations

import io
import urllib.error

import pytest

import lark_client
import lsr_platform
import scheduler as S

GIO = 1_790_000_000.0


@pytest.fixture
def so(monkeypatch, tmp_path):
    f = tmp_path / "reminders.json"
    monkeypatch.setattr(S, "_FILE", f)
    gui = {"gateway": [], "truc_tiep": []}
    monkeypatch.setattr(lsr_platform, "gui_lark",
                        lambda oc, text, app_id="", uuid=None:
                        gui["gateway"].append((oc, app_id, text, uuid)) or {})
    monkeypatch.setattr(lark_client, "send_text",
                        lambda kieu, rid, text, uuid=None:
                        gui["truc_tiep"].append((kieu, rid, text, uuid)) or {})
    return gui


def _dat(chat: str, due: float, **them) -> dict:
    r = {"id": "abc1234567", "chat_id": chat, "message": "Họp lúc 14h",
         "due_ts": due, "recurrence": "none", "created_by": None,
         "created_at": due - 60, "done": False, **them}
    S._save([r])
    return r


def _mot():
    return S._load()[0]


def test_chat_gateway_gui_qua_platform_voi_oc_va_app_id(so):
    _dat("lark:cli_app1:oc_nhom9", GIO - 5)
    assert S._fire_due(GIO) == 1
    assert so["truc_tiep"] == []
    oc, app, text, uid = so["gateway"][0]
    assert (oc, app, text) == ("oc_nhom9", "cli_app1", "Họp lúc 14h")
    assert uid and len(uid) <= 50
    r = _mot()
    assert r["done"] and r["trang_thai"] == "da_gui"


def test_chat_oc_gui_thang_lark(so):
    _dat("oc_rieng", GIO - 5)
    assert S._fire_due(GIO) == 1
    assert so["truc_tiep"][0][:3] == ("chat_id", "oc_rieng", "Họp lúc 14h")
    assert so["gateway"] == []


def test_loi_vinh_vien_230001_dung_han(monkeypatch, so, capsys):
    """Đúng lỗi thật trên VPS: không thử lại, chỉ in một dòng."""
    def hong(*a, **k):
        raise RuntimeError('Lark POST /open-apis/im/v1/messages failed: HTTP 400: '
                           '{"code":230001,"msg":"... ext=invalid receive_id"}')
    monkeypatch.setattr(lark_client, "send_text", hong)
    _dat("oc_khong_con", GIO - 5)
    assert S._fire_due(GIO) == 0
    r = _mot()
    assert r["done"] and r["trang_thai"] == "that_bai"
    for i in range(5):                      # các nhịp sau: không gửi, không in
        S._fire_due(GIO + 20 * (i + 1))
    out = capsys.readouterr().out
    assert out.count("[reminder]") == 1


def test_gateway_502_lark_tu_choi_bot_khong_trong_chat_la_vinh_vien(monkeypatch, so):
    def hong(*a, **k):
        raise urllib.error.HTTPError(
            "https://p/v1/lark/send", 502, "Bad Gateway", {},
            io.BytesIO('{"detail":"Lark từ chối: Bot is not in the chat"}'.encode()))
    monkeypatch.setattr(lsr_platform, "gui_lark", hong)
    _dat("lark:cli_a:oc_b", GIO - 5)
    S._fire_due(GIO)
    assert _mot()["trang_thai"] == "that_bai"


def test_chat_khong_phai_lark_that_bai_ngay(so):
    _dat("web:phien1", GIO - 5)
    S._fire_due(GIO)
    assert _mot()["trang_thai"] == "that_bai"
    assert so["gateway"] == so["truc_tiep"] == []


def test_loi_tam_lui_dan_va_co_tran(monkeypatch, so, capsys):
    lan = []

    def hong(*a, **k):
        lan.append(1)
        raise urllib.error.URLError("connection reset")
    monkeypatch.setattr(lsr_platform, "gui_lark", hong)
    _dat("lark:cli_a:oc_b", GIO - 5)
    t = GIO
    S._fire_due(t)
    r = _mot()
    assert not r["done"] and r["so_lan_thu"] == 1 and r["thu_lai_ts"] == t + 30
    S._fire_due(t + 20)                     # chưa tới giờ thử lại -> không gọi
    assert len(lan) == 1
    for _ in range(30):                     # đi theo đúng giờ thử lại
        r = _mot()
        if r["done"]:
            break
        t = r["thu_lai_ts"]
        S._fire_due(t)
    r = _mot()
    assert r["done"] and r["trang_thai"] == "that_bai"
    assert len(lan) == S._THU_TOI_DA == 10
    out = capsys.readouterr().out
    assert out.count("[reminder]") == 2, "một dòng khi bắt đầu thử lại, một khi bỏ"


def test_loi_tam_roi_gui_duoc(monkeypatch, so):
    lan = []

    def luc_duoc_luc_khong(oc, text, app_id="", uuid=None):
        lan.append(uuid)
        if len(lan) == 1:
            raise urllib.error.HTTPError("u", 503, "x", {}, io.BytesIO(b""))
        return {}
    monkeypatch.setattr(lsr_platform, "gui_lark", luc_duoc_luc_khong)
    _dat("lark:cli_a:oc_b", GIO - 5)
    S._fire_due(GIO)
    assert S._fire_due(GIO + 30) == 1
    assert lan[0] == lan[1], "cùng uuid để khử trùng"
    assert _mot()["trang_thai"] == "da_gui"


def test_nhac_tre_2_ngay_gui_mot_lan_kem_ghi_chu(so):
    """Ca 6cbd4598d1: bản ghi cũ (không có so_lan_thu), trễ ~2 ngày."""
    _dat("lark:cli_a:oc_b", GIO - 2 * 86400)
    assert S._fire_due(GIO) == 1
    assert S._fire_due(GIO + 20) == 0
    assert len(so["gateway"]) == 1
    text = so["gateway"][0][2]
    assert text.startswith("(nhắc trễ do lỗi gửi") and text.endswith("Họp lúc 14h")


def test_nhac_dung_gio_khong_ghi_chu_tre(so):
    _dat("lark:cli_a:oc_b", GIO - 30)
    S._fire_due(GIO)
    assert so["gateway"][0][2] == "Họp lúc 14h"


def test_nhac_tre_qua_7_ngay_that_bai_khong_gui(so):
    _dat("lark:cli_a:oc_b", GIO - 8 * 86400)
    assert S._fire_due(GIO) == 0
    assert so["gateway"] == []
    assert _mot()["trang_thai"] == "that_bai"


def test_hang_ngay_tre_gui_mot_lan_roi_hen_ngay_ke(so):
    _dat("oc_x", GIO - 3 * 86400 - 100, recurrence="daily")
    assert S._fire_due(GIO) == 1
    r = _mot()
    assert not r["done"] and GIO < r["due_ts"] <= GIO + 86400
    assert S._fire_due(GIO + 20) == 0


def test_huy_trong_luc_gui_khong_bi_ghi_de(monkeypatch, so):
    def gui_va_huy(*a, **k):
        S.cancel_reminder("abc1234567")
        return {}
    monkeypatch.setattr(lsr_platform, "gui_lark", gui_va_huy)
    _dat("lark:cli_a:oc_b", GIO - 5)
    S._fire_due(GIO)
    r = _mot()
    assert r["done"] and "trang_thai" not in r
