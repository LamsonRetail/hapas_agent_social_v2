"""Lịch nhắc / giao việc đặt trong chat → Platform (chủ agent chốt 08/10/2026).

Ranh giới phải giữ:
  • schedule/list/cancel gọi `POST /v1/self/tools/call` với session_id = phiên Lark của
    cuộc chat hiện tại và actor = người đang nói — lấy từ LƯỢT, không từ đối số model;
  • Platform hỏng/từ chối → tool_error nói lý do, KHÔNG BAO GIỜ ghi file nhắc trên máy;
  • lượt chạy theo lịch không đặt/huỷ lịch; mode=run cần danh tính người đặt;
  • `/tiendo` trong lịch: phải mode=run, cú pháp đúng, link có ?table=;
  • gọi lại cùng nội dung + cùng giờ chạy kế không đẻ lịch thứ hai;
  • nhắc CŨ trên máy chỉ còn xem/huỷ (trong đúng chat) và gửi nốt.
Không chạm mạng: `lsr_platform._goi` là giả.
"""
from __future__ import annotations

import datetime
import io
import json
import urllib.error

import pytest

import lsr_platform
import lsr_policy
import memory_store
import scheduler as S

LINK = "https://test.larksuite.com/base/baseTokenTest123?table=tblTest"
PHIEN = "lark:cli_app:oc_nhom1"


@pytest.fixture
def pf(monkeypatch, tmp_path):
    """Platform giả: ghi mọi lời gọi; trả lời theo `pf['tra'][tool]` (dict hoặc Exception)."""
    monkeypatch.setattr(S, "_FILE", tmp_path / "reminders.json")
    monkeypatch.setattr(lsr_platform, "_cau_hinh",
                        lambda: {"url": "u", "platform": "https://p.test", "agent_id": "A",
                                 "key": "k"})
    st = {"goi": [], "tra": {
        "list_reminders": {"ok": True, "data": {"reminders": []}},
        "schedule_reminder": {"ok": True, "data": {
            "id": 41, "message": "m", "recurrence": "daily", "mode": "run",
            "days": "mọi ngày", "due_at_vn": "09/10/2026 08:30 (hằng ngày, mọi ngày)",
            "note": "Đã đặt LỊCH"}},
        "cancel_reminder": {"ok": True, "data": {"cancelled": 41}},
    }}

    def goi(c, duong, body=None, timeout=35):
        st["goi"].append((duong, body, timeout))
        kq = st["tra"][body["tool"]]
        if isinstance(kq, Exception):
            raise kq
        return kq
    monkeypatch.setattr(lsr_platform, "_goi", goi)
    S.set_current_chat(PHIEN)
    S.set_current_scheduled(False)
    memory_store.set_current_sender("ou_nguoi1")
    yield st
    S.set_current_chat(None)
    S.set_current_scheduled(False)
    memory_store.set_current_sender(None)


def _j(s: str) -> dict:
    return json.loads(s)


def _goi_tool(st, tool):
    return [b for d, b, _t in st["goi"] if b["tool"] == tool]


# ───────────────────────────── đặt lịch ─────────────────────────────
def test_dat_lich_tiendo_run_goi_platform_dung_hop_dong(pf):
    kq = _j(S._handle_schedule({"message": f"/tiendo {LINK} cua_toi=co", "when": "08:30",
                                "recurrence": "daily", "mode": "run", "days": "weekdays"}))
    assert kq["success"] is True and kq["id"] == 41 and "Lịch chạy" in kq["xem_sua_xoa"]
    tao = _goi_tool(pf, "schedule_reminder")
    assert len(tao) == 1
    b = tao[0]
    assert pf["goi"][-1][0] == "/v1/self/tools/call"
    assert b["tool"] == b["name"] == "schedule_reminder"
    assert b["session_id"] == PHIEN and b["actor"] == "ou_nguoi1"
    assert b["args"] == {"message": f"/tiendo {LINK} cua_toi=co", "when": "08:30",
                         "mode": "run", "recurrence": "daily", "days": "weekdays"}
    assert not S._FILE.exists(), "không được tạo nhắc trên máy nữa"


def test_doi_so_model_khong_doi_duoc_nguoi_dat_hay_nhom(pf):
    S._handle_schedule({"message": "Nộp báo cáo", "when": "14:00", "actor": "ou_nannhan",
                        "session_id": "lark:cli_app:oc_khac", "chat_id": "oc_khac"})
    b = _goi_tool(pf, "schedule_reminder")[0]
    assert b["actor"] == "ou_nguoi1" and b["session_id"] == PHIEN
    assert set(b["args"]) == {"message", "when", "mode"} and b["args"]["mode"] == "send"


@pytest.mark.parametrize("loi, chu", [
    ({"ok": False, "error": "không hiểu thời điểm 'mai'"}, "không hiểu thời điểm"),
    (urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b"bad token")), "HTTP 401"),
    (urllib.error.URLError("timed out"), "Không gọi được Platform"),
    (TimeoutError("slow"), "Không gọi được Platform"),
    ({"weird": 1}, "Platform từ chối"),
])
def test_platform_loi_bao_ly_do_khong_lui_ve_may(pf, loi, chu):
    pf["tra"]["schedule_reminder"] = loi
    kq = _j(S._handle_schedule({"message": "Họp 14h", "when": "13:50"}))
    assert "error" in kq and chu in kq["error"] and "CHƯA" in kq["error"]
    assert not S._FILE.exists() and S._load() == []


def test_chua_cau_hinh_platform_tu_choi_khong_ghi_may(pf, monkeypatch):
    monkeypatch.setattr(lsr_platform, "_cau_hinh", lambda: None)
    kq = _j(S._handle_schedule({"message": "Họp", "when": "+30m"}))
    assert "chưa nối Platform" in kq["error"] and pf["goi"] == [] and not S._FILE.exists()


def test_chat_lark_truc_tiep_dung_app_cua_mark(pf, monkeypatch):
    monkeypatch.setattr(S.config, "app_id", "cli_mark", raising=False)
    S.set_current_chat("oc_rieng9")
    S._handle_schedule({"message": "Uống nước", "when": "+2h"})
    assert _goi_tool(pf, "schedule_reminder")[0]["session_id"] == "lark:cli_mark:oc_rieng9"


@pytest.mark.parametrize("chat", ["job:55", "", "web:abc", "lark:cli_app:", "lark:a b:oc_x"])
def test_khong_phai_chat_lark_khong_goi(pf, chat):
    S.set_current_chat(chat)
    kq = _j(S._handle_schedule({"message": "Họp", "when": "10:00"}))
    assert "cuộc trò chuyện Lark" in kq["error"] and pf["goi"] == []


def test_run_thieu_danh_tinh_tu_choi(pf):
    memory_store.set_current_sender(None)
    kq = _j(S._handle_schedule({"message": f"/tiendo {LINK}", "when": "08:30", "mode": "run"}))
    assert "danh tính" in kq["error"] and _goi_tool(pf, "schedule_reminder") == []
    # send không cần danh tính: vẫn đặt được, actor rỗng
    S._handle_schedule({"message": "Họp", "when": "10:00"})
    assert _goi_tool(pf, "schedule_reminder")[0]["actor"] == ""


@pytest.mark.parametrize("args, chu", [
    ({"message": f"/tiendo {LINK}", "when": "08:30"}, "mode=run"),
    ({"message": f"/tiendo {LINK} cua_toi=ai", "when": "08:30", "mode": "run"}, "cua_toi"),
    ({"message": f"/tiendo {LINK} so_ngay=99", "when": "08:30", "mode": "run"}, "so_ngay"),
    ({"message": "/tiendo https://x.larksuite.com/base/abc", "when": "08:30", "mode": "run"},
     "?table="),
    ({"message": "Họp", "when": "08:30", "mode": "chay"}, "`mode`"),
    ({"message": "", "when": "08:30"}, "message"),
    ({"message": "Họp", "when": ""}, "when"),
])
def test_kiem_truoc_khi_dat(pf, args, chu):
    kq = _j(S._handle_schedule(args))
    assert chu in kq["error"] and _goi_tool(pf, "schedule_reminder") == []


def test_luot_theo_lich_khong_dat_khong_huy(pf):
    S.set_current_scheduled(True)
    assert "THEO LỊCH" in _j(S._handle_schedule({"message": "Họp", "when": "10:00"}))["error"]
    assert "THEO LỊCH" in _j(S._handle_cancel({"id": "41"}))["error"]
    assert pf["goi"] == []


def test_goi_lai_cung_noi_dung_cung_gio_khong_tao_them(pf):
    moc = datetime.datetime.fromtimestamp(S._parse_when("08:30"), S.VN_TZ)
    pf["tra"]["list_reminders"] = {"ok": True, "data": {"reminders": [
        {"id": 7, "message": f"/tiendo  {LINK}", "recurrence": "daily",
         "due_at_vn": moc.strftime("%d/%m/%Y %H:%M")}]}}
    kq = _j(S._handle_schedule({"message": f"/tiendo {LINK}", "when": "08:30",
                                "recurrence": "daily", "mode": "run"}))
    assert kq["da_co_san"] is True and kq["id"] == 7
    assert _goi_tool(pf, "schedule_reminder") == []
    # khác giờ thì là lịch khác — vẫn tạo
    S._handle_schedule({"message": f"/tiendo {LINK}", "when": "17:00", "mode": "run"})
    assert len(_goi_tool(pf, "schedule_reminder")) == 1


def test_xem_danh_sach_hong_van_de_lenh_tao_tu_bao(pf):
    pf["tra"]["list_reminders"] = urllib.error.URLError("down")
    pf["tra"]["schedule_reminder"] = urllib.error.URLError("down")
    kq = _j(S._handle_schedule({"message": "Họp", "when": "10:00"}))
    assert "CHƯA" in kq["error"] and "list_reminders" in kq["error"]


# ───────────────────────────── xem / huỷ ─────────────────────────────
def _nhac_cu(chat, rid="abc1234567"):
    items = S._load()
    items.append({"id": rid, "chat_id": chat, "message": "Họp cũ", "due_ts": 1_900_000_000.0,
                  "recurrence": "none", "created_by": None, "created_at": 1.0, "done": False})
    S._save(items)


def test_xem_lich_tu_platform_kem_nhac_cu_cua_dung_chat(pf):
    pf["tra"]["list_reminders"] = {"ok": True, "data": {"reminders": [
        {"id": 41, "message": "Họp", "recurrence": "none", "due_at_vn": "09/10/2026 10:00"}]}}
    _nhac_cu(PHIEN)
    _nhac_cu("lark:cli_app:oc_khac", rid="def1234567")
    kq = _j(S._handle_list({}))
    assert kq["count"] == 1 and kq["reminders"][0]["id"] == 41
    assert [r["id"] for r in kq["nhac_cu_tren_may"]] == ["abc1234567"]
    b = _goi_tool(pf, "list_reminders")[0]
    assert b["session_id"] == PHIEN and b["args"] == {}


def test_xem_lich_platform_hong_bao_loi(pf):
    pf["tra"]["list_reminders"] = {"ok": False, "error": "agent bị khoá"}
    assert "agent bị khoá" in _j(S._handle_list({}))["error"]


def test_huy_lich_platform_gui_id_so(pf):
    kq = _j(S._handle_cancel({"id": "41"}))
    assert kq["success"] is True and kq["cancelled"] == 41
    assert _goi_tool(pf, "cancel_reminder")[0]["args"] == {"id": 41}
    kq = _j(S._handle_cancel({"id": 41}))
    assert kq["cancelled"] == 41


def test_huy_lich_platform_tu_choi(pf):
    pf["tra"]["cancel_reminder"] = {"ok": False, "error": "không thấy lịch nhắc #9 trong cuộc này"}
    kq = _j(S._handle_cancel({"id": "9"}))
    assert "không thấy lịch" in kq["error"] and "CHƯA" in kq["error"]


def test_huy_nhac_cu_chi_trong_dung_chat(pf):
    _nhac_cu("lark:cli_app:oc_khac")
    kq = _j(S._handle_cancel({"id": "abc1234567"}))
    assert "Không thấy" in kq["error"] and not S._load()[0]["done"]
    S.set_current_chat("lark:cli_app:oc_khac")
    kq = _j(S._handle_cancel({"id": "abc1234567"}))
    assert kq["success"] and S._load()[0]["done"] and pf["goi"] == []


def test_khong_con_ham_tao_nhac_tren_may():
    assert not hasattr(S, "add_reminder")


# ───────────────────────────── nối dây ─────────────────────────────
def test_policy_dat_huy_la_ghi_xem_la_doc():
    assert lsr_policy._MUTATING_EXACT["schedule_reminder"] == "write_data"
    assert lsr_policy._MUTATING_EXACT["cancel_reminder"] == "write_data"
    assert "list_reminders" in lsr_policy._SAFE_EXACT


def test_brain_dat_co_luot_theo_lich_va_loi_dan(pf, monkeypatch):
    import brain
    seen = {}
    monkeypatch.setattr(brain.lenh_cung, "xu_ly",
                        lambda *a, **k: (seen.setdefault("lich", S._current_scheduled.get()),
                                         brain.lenh_cung.KetQua(van_ban="", tra_loi_thang="x"))[1])
    monkeypatch.setattr(brain.memory_store, "append_turns", lambda *a, **k: None)
    monkeypatch.setattr(brain.audit, "bat_dau", lambda *a, **k: "t")
    monkeypatch.setattr(brain.audit, "ket_thuc", lambda *a, **k: None)
    brain.reply("hi", chat_id=PHIEN, sender_open_id="ou_a",
                kenh={"chat_type": "group", "scheduled": True, "scheduled_by": "ou_a"})
    assert seen["lich"] is True
    brain.reply("hi", chat_id=PHIEN, sender_open_id="ou_a", kenh={"chat_type": "group"})
    assert S._current_scheduled.get() is False
    note = brain._TOOLING_NOTE
    assert "mode=run" in note and "/tiendo" in note and "Lịch chạy" in note
    assert "cua_toi=co" in note
