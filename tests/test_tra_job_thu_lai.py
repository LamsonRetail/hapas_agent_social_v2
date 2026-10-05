"""Trả lời job platform phải sống qua lỗi tạm — sự cố 04/10/2026 21:46.

Job 5632: một 502 Bad Gateway ở `/reply` là mất câu trả lời. Phải chặn:
  • 5xx / lỗi mạng -> thử lại 3 lần, giãn 1s, 3s, 9s;
  • 4xx -> không thử lại;
  • thử lại không ra hai tin Lark (platform khử trùng theo sự kiện `message` của job).
Không chạm mạng: `_goi` giả mô phỏng đúng hành vi `self_job_reply` / `self_job_complete`.
"""
from __future__ import annotations

import io
import urllib.error

import pytest

import lsr_platform as P


def _http(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://p/x", code, "loi", {}, io.BytesIO(b""))


class NenGia:
    """Platform giả: `/reply` khử trùng theo job như app.py (đã có message -> không gửi)."""

    def __init__(self, loi_reply=(), loi_complete=()):
        self.loi_reply = list(loi_reply)        # mỗi phần tử: (lỗi, đã_xử_lý_xong?)
        self.loi_complete = list(loi_complete)
        self.lark = []                           # tin thật sự ra Lark
        self.su_kien = set()
        self.done = False
        self.goi = []

    def __call__(self, c, duong, than=None, timeout=None):
        if duong.startswith("/v1/self/jobs?"):
            return [{"id": 5632, "session_id": "lark:cli_a:oc_b",
                     "payload": {"text": "chào"}}]
        self.goi.append(duong)
        if duong.endswith("/reply"):
            loi, da_xu_ly = self.loi_reply.pop(0) if self.loi_reply else (None, True)
            if da_xu_ly and "message" not in self.su_kien:
                self.su_kien.add("message")
                self.lark.append(than["text"])
            if loi:
                raise loi
            return {"ok": True}
        if duong.endswith("/complete"):
            loi, da_xu_ly = self.loi_complete.pop(0) if self.loi_complete else (None, True)
            if da_xu_ly:
                if self.done:
                    raise _http(409)
                self.done = True
            if loi:
                raise loi
            return {"ok": True}
        return {}


@pytest.fixture
def ngu(monkeypatch):
    nghi = []
    monkeypatch.setattr(P, "_ngu", nghi.append)
    monkeypatch.setattr(P, "_tai_anh", lambda c, j: [])
    return nghi


def _chay(monkeypatch, nen):
    monkeypatch.setattr(P, "_goi", nen)
    return P._mot_vong({"platform": "u", "key": "k", "agent_id": "AG-X-TEST"},
                       lambda hoi, chat_id, sender_open_id=None, **k: "đáp")


def test_502_o_reply_thu_lai_va_den_noi(monkeypatch, ngu):
    nen = NenGia(loi_reply=[(_http(502), False)])
    assert _chay(monkeypatch, nen) == 1
    assert nen.goi.count("/v1/self/jobs/5632/reply") == 2
    assert nen.lark == ["đáp"]
    assert ngu == [1]
    assert nen.done


def test_502_sau_khi_platform_da_gui_khong_ra_hai_tin(monkeypatch, ngu):
    """Proxy trả 502 nhưng handler đã gửi Lark và commit: lần thử lại phải là bản trùng."""
    nen = NenGia(loi_reply=[(_http(502), True), (_http(503), True)])
    _chay(monkeypatch, nen)
    assert nen.goi.count("/v1/self/jobs/5632/reply") == 3
    assert nen.lark == ["đáp"], "chỉ đúng một tin ra Lark"


def test_loi_mang_thu_lai_gian_1_3_9(monkeypatch, ngu):
    nen = NenGia(loi_reply=[(urllib.error.URLError("reset"), False)] * 4)
    _chay(monkeypatch, nen)
    assert nen.goi.count("/v1/self/jobs/5632/reply") == 4, "1 lần + 3 lần thử lại"
    assert ngu == [1, 3, 9]
    assert nen.lark == []
    assert nen.done, "complete vẫn được gọi như trước"


def test_400_khong_thu_lai(monkeypatch, ngu):
    nen = NenGia(loi_reply=[(_http(400), False)])
    _chay(monkeypatch, nen)
    assert nen.goi.count("/v1/self/jobs/5632/reply") == 1
    assert ngu == []


def test_complete_502_da_xu_ly_thu_lai_gap_409_la_xong(monkeypatch, ngu, capsys):
    nen = NenGia(loi_complete=[(_http(502), True)])
    _chay(monkeypatch, nen)
    assert nen.goi.count("/v1/self/jobs/5632/complete") == 2
    out = capsys.readouterr().out
    assert "đã xong từ lần gửi trước" in out
    assert "/complete lỗi:" not in out


def test_complete_409_ngay_lan_dau_van_bao_loi(monkeypatch, ngu, capsys):
    nen = NenGia()
    nen.done = True                              # job đã bị đóng nơi khác
    _chay(monkeypatch, nen)
    assert nen.goi.count("/v1/self/jobs/5632/complete") == 1
    assert "/complete lỗi:" in capsys.readouterr().out
