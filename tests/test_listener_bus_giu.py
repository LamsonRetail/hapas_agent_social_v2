"""Listener im lặng khi gateway platform giữ bus Lark — sự cố 04/10/2026.

Mỗi 10 phút lark-cli in ~12 dòng stderr (142 lần) dù đây là trạng thái đúng. Phải chặn:
  • bus bị giữ -> không dòng stderr nào ra log, `_consume_once` báo True;
  • supervisor chỉ in MỘT dòng cho cả chuỗi lần bị giữ;
  • sẵn sàng hoặc thoát vì lỗi khác -> stderr vẫn in đủ (không nuốt lỗi thật).
"""
from __future__ import annotations

import io
import threading

import pytest

import listener as L

# Đúng bản dump thật trên VPS (journal 04/10), thêm dòng "message" mà bản cũ nuốt.
DUMP_BI_GIU = """[event] consuming as cli_app (cli_app)
[event] local bus not found; checking remote connections...
[event] remote connection check: online_instance_cnt=1
{
  "ok": false,
  "identity": "bot",
  "error": {
    "type": "validation",
    "subtype": "failed_precondition",
    "message": "another event bus is already connected",
    "hint": "remote event connection detected; stop the owner host/process"
  }
}
"""


class ProcGia:
    def __init__(self, stderr: str, stdout: str = ""):
        self.stderr = io.StringIO(stderr)
        self.stdout = io.StringIO(stdout)
        self.stdin = io.StringIO()

    def poll(self):
        return 0

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


def _xa(stderr: str, bi_giu=True):
    ready, giu = threading.Event(), threading.Event()
    L._drain_stderr(ProcGia(stderr), ready, giu if bi_giu else None)
    return ready, giu


def test_bus_bi_giu_khong_in_dong_nao(capsys):
    _, giu = _xa(DUMP_BI_GIU)
    assert giu.is_set()
    assert capsys.readouterr().out == ""


def test_ban_cli_chi_co_hint_remote_cung_nhan_ra(capsys):
    dump = "\n".join(d for d in DUMP_BI_GIU.splitlines() if '"message"' not in d)
    _, giu = _xa(dump)
    assert giu.is_set()
    assert capsys.readouterr().out == ""


def test_san_sang_thi_in_ca_dong_truoc_do(capsys):
    ready, giu = _xa("[event] consuming as cli_app\n[event] ready\n[event] khác\n")
    assert ready.is_set() and not giu.is_set()
    out = capsys.readouterr().out
    assert out.count("[event/stderr]") == 3


def test_thoat_vi_loi_khac_van_in_du(capsys):
    _, giu = _xa('{\n  "ok": false,\n  "error": {"message": "token expired"}\n}\n')
    assert not giu.is_set()
    assert "token expired" in capsys.readouterr().out


def test_khong_co_co_bi_giu_van_bat_ready(capsys):
    ready, _ = _xa("[event] ready\n", bi_giu=False)
    assert ready.is_set()


def test_consume_once_bao_bi_giu_va_im(monkeypatch, capsys):
    monkeypatch.setattr(L.subprocess, "Popen", lambda *a, **k: ProcGia(DUMP_BI_GIU))
    monkeypatch.setattr(L, "_cli_env", lambda: {})
    assert L._consume_once("lark-cli", lambda m: None) is True
    assert capsys.readouterr().out == ""


def test_supervisor_bao_mot_dong_cho_nhieu_lan_bi_giu(monkeypatch, capsys):
    lan = []

    class Dung(Exception):
        pass

    def consume(cli, handler):
        lan.append(1)
        if len(lan) > 5:
            raise Dung
        return True

    def ngu(s):
        if len(lan) > 5:
            raise Dung
    monkeypatch.setattr(L, "_resolve_cli", lambda: "lark-cli")
    monkeypatch.setattr(L, "ensure_config", lambda: None)
    monkeypatch.setattr(L, "_consume_once", consume)
    monkeypatch.setattr(L.time, "sleep", ngu)
    with pytest.raises(Dung):
        L.start_listener(lambda m: None)
    out = capsys.readouterr().out
    assert out.count("[event]") == 2, out   # một dòng "bị giữ" + dòng crash giả để dừng
    assert out.count("MỘT BUS KHÁC") == 1
