"""Cờ `restricted` gửi kèm /reply khi lượt trả số hạn chế (review 08/10/2026, mục 2).

Platform ẩn nội dung câu trả lời có cờ khỏi người dưới moderator ở bản ghi hội thoại,
nên cờ phải do CHÍNH tool đặt trong lượt (không đoán theo chữ), đi đúng job, không dính
sang lượt sau, và không bao giờ đặt cho job A2A/kênh lạ (job đó bị tool từ chối).
"""
from __future__ import annotations

import pytest

import lsr_platform as P


@pytest.fixture
def nen(monkeypatch):
    goi = []
    monkeypatch.setattr(P, "_tai_anh", lambda c, j: [])
    monkeypatch.setattr(P, "_goi_job", lambda c, duong, than: goi.append((duong, than)) or {"ok": 1})
    with P._HAN_CHE_KHOA:
        P._HAN_CHE_JOB.clear()
    return goi


def _job(monkeypatch, job):
    monkeypatch.setattr(P, "_goi", lambda *a, **k: [job])


def _reply_body(goi):
    return next(than for duong, than in goi if duong.endswith("/reply"))


def test_flagged_turn_sends_restricted(monkeypatch, nen):
    _job(monkeypatch, {"id": 71, "channel": "lark", "session_id": "lark:cli:oc_1",
                       "reply_to": {"chat_type": "p2p"}, "payload": {"text": "/soads", "sender_open_id": "ou_a"}})
    seen = {}

    def tra_loi(hoi, chat_id, sender_open_id=None, kenh=None):
        seen.update(kenh=kenh, sender=sender_open_id)
        assert P.danh_dau_han_che("chi_so_ads")
        return "Tổng chi tiêu 1.000.000"
    assert P._mot_vong({}, tra_loi) == 1
    assert _reply_body(nen) == {"text": "Tổng chi tiêu 1.000.000", "restricted": "chi_so_ads"}
    assert seen["kenh"] == {"chat_type": "p2p", "channel": "lark", "nguoi_gui": "ou_a"}
    assert not P._HAN_CHE_JOB


def test_unflagged_turn_in_clean_session(monkeypatch, nen):
    assert not P.danh_dau_han_che("chi_so_ads")          # ngoài lượt: không có hộp, không dính
    _job(monkeypatch, {"id": 72, "channel": "web", "session_id": "web:s1",
                       "payload": {"text": "chào", "sender_open_id": "ou_a"}})
    assert P._mot_vong({}, lambda hoi, chat_id, sender_open_id=None, **k: "chào bạn") == 1
    assert _reply_body(nen) == {"text": "chào bạn"}


def test_later_turns_in_ads_session_stay_flagged(monkeypatch, nen):
    """Lượt sau nhắc lại số từ lịch sử (không gọi tool) vẫn mang cờ — cờ bám phiên, lưu đĩa."""
    import memory_store
    memory_store.danh_dau_phien_han_che("lark:cli:oc_9", "chi_so_ads")
    _job(monkeypatch, {"id": 74, "channel": "lark", "session_id": "lark:cli:oc_9",
                       "reply_to": {"chat_type": "p2p"}, "payload": {"text": "tổng lúc nãy?",
                                                                     "sender_open_id": "ou_a"}})
    assert P._mot_vong({}, lambda hoi, chat_id, sender_open_id=None, **k: "Chi tiêu 1.000.000") == 1
    assert _reply_body(nen) == {"text": "Chi tiêu 1.000.000", "restricted": "chi_so_ads"}


def test_overlapping_turns_do_not_steal_or_clear_flag(monkeypatch):
    """Lượt B chạy chồng lượt A cùng phiên (quá nửa trần chờ khoá): cờ của A ở lại với A."""
    import threading
    import time
    monkeypatch.setattr(P, "_HAN_TRA_LOI", 1.0)
    monkeypatch.setattr(P, "_KHOA_PHIEN", {})
    with P._HAN_CHE_KHOA:
        P._HAN_CHE_JOB.clear()
    a_flagged = threading.Event()

    def turn_a(hoi, chat_id, sender_open_id=None, **k):
        P.danh_dau_han_che("chi_so_ads")
        a_flagged.set()
        time.sleep(0.8)                  # B bắt đầu (sau 0,5 s chờ khoá) và xong trước A
        return "số"

    def turn_b(hoi, chat_id, sender_open_id=None, **k):
        assert a_flagged.is_set()
        return "chào"
    ta = threading.Thread(target=P._chay_co_han, args=(turn_a, "a", "lark:x:oc_1", None), kwargs={"job_id": 1})
    ta.start()
    assert a_flagged.wait(2)
    assert P._chay_co_han(turn_b, "b", "lark:x:oc_1", None, job_id=2)[1]
    ta.join(3)
    assert P._lay_han_che_job(2) == ""
    assert P._lay_han_che_job(1) == "chi_so_ads"


def test_a2a_kenh_never_carries_user_ref_identity(monkeypatch, nen):
    _job(monkeypatch, {"id": 73, "channel": "a2a", "session_id": "a2a_x",
                       "reply_to": {"channel": "a2a"},
                       "payload": {"text": "/soads", "user_ref": "ou_victim", "from_agent": "AG-X"}})
    seen = {}
    assert P._mot_vong({}, lambda hoi, chat_id, sender_open_id=None, kenh=None:
                       seen.update(kenh=kenh) or "từ chối") == 1
    assert seen["kenh"] == {"channel": "a2a"}


@pytest.mark.parametrize("payload,expected", [
    ({"sender_open_id": "ou_a", "sender_identity_verified": True},
     {"channel": "web", "sender_identity_verified": True, "nguoi_gui": "ou_a"}),
    ({"sender_open_id": "ou_a", "sender_identity_verified": "true"}, {"channel": "web"}),
    ({"user_ref": "ou_a"}, {"channel": "web"})])
def test_web_kenh_only_verified_identity(payload, expected):
    assert P._kenh_job_day_du({"payload": payload}, "web") == expected


def test_late_web_reply_carries_flag(monkeypatch):
    import viec_nen
    sent = []
    monkeypatch.setattr(P, "bao_su_kien_job",
                        lambda job_id, text, ma_su_kien=None, han_che="": sent.append(han_che) or {})
    viec_nen.day_theo_kenh({"loai": "web", "job_id": 5}, "số", "k1", han_che="chi_so_ads")
    viec_nen.day_theo_kenh({"loai": "web", "job_id": 5}, "chào", "k2")
    assert sent == ["chi_so_ads", ""]


def test_event_body_flag(monkeypatch):
    bodies = []
    monkeypatch.setattr(P, "_cau_hinh", lambda: {"platform": "u", "key": "k"})
    monkeypatch.setattr(P, "_goi", lambda c, duong, than=None, timeout=None: bodies.append(than) or {})
    P.bao_su_kien_job(5, "số", "k1", han_che="chi_so_ads")
    P.bao_su_kien_job(5, "chào", "k2")
    assert bodies[0]["data"] == {"text": "số", "id": "k1", "restricted": "chi_so_ads"}
    assert "restricted" not in bodies[1]["data"]
