"""Canh trần quét chủ agent đặt trên console (Năng lực → Quét mạng xã hội).

Trần số bài và trần chi phí trước đây nằm cứng trong code/.env (500 bài, 1 USD) — muốn
nâng phải nhờ người sửa máy chạy bot. Giờ chủ agent tự chỉnh trên console; console lưu
vào CÙNG mục `social_listen` trong `agents.capabilities` (khoá `cau_hinh`), Mark đọc
cùng lượt với công tắc bật/tắt.

Console KHÔNG phải ranh giới an toàn: runtime luôn kẹp lại trong khoảng cứng của nó.
"""
from __future__ import annotations

import io
import json
import time

import pytest

import apify_tool as A
import lsr_policy


@pytest.fixture
def cau_hinh(monkeypatch):
    def dat(c):
        monkeypatch.setattr(lsr_policy, "cau_hinh_tool",
                            lambda tool: dict(c) if tool == "social_listen" else {})
    return dat


def test_chua_dat_thi_dung_mac_dinh(cau_hinh):
    cau_hinh({})
    assert A._tran() == (A._MAX_LIMIT, round(A._MAX_CHARGE, 2))


def test_dat_trong_khoang_thi_dung_dung_so(cau_hinh):
    cau_hinh({"tran_bai": 800, "tran_usd": 2.5})
    assert A._tran() == (800, 2.5)


@pytest.mark.parametrize("c, mong", [
    ({"tran_bai": 100000, "tran_usd": 1000}, (1000, 5.0)),      # gõ nhầm vượt trần cứng
    ({"tran_bai": 0, "tran_usd": 0}, (10, 0.1)),               # 0 không được làm câm tool
    ({"tran_bai": -5, "tran_usd": -1}, (10, 0.1)),
])
def test_luon_kep_trong_khoang_an_toan(cau_hinh, c, mong):
    cau_hinh(c)
    assert A._tran() == mong


@pytest.mark.parametrize("rac", ["abc", None, float("nan"), [], {}])
def test_gia_tri_rac_thi_ve_mac_dinh(cau_hinh, rac):
    cau_hinh({"tran_bai": rac, "tran_usd": rac})
    assert A._tran() == (A._MAX_LIMIT, round(A._MAX_CHARGE, 2))


def test_doc_cau_hinh_hong_khong_chan_quet(monkeypatch):
    def hong(tool):
        raise RuntimeError("mất mạng")
    monkeypatch.setattr(lsr_policy, "cau_hinh_tool", hong)
    assert A._tran() == (A._MAX_LIMIT, round(A._MAX_CHARGE, 2))


def test_tran_usd_di_vao_lenh_goi_apify(cau_hinh, monkeypatch):
    cau_hinh({"tran_usd": 2.5})
    url = []

    class R:
        status_code = 200

        def json(self):
            return []

    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A.requests, "post", lambda u, **k: url.append(u) or R())
    A._call("apidojo~tiktok-scraper", {}, 10)
    assert "maxTotalChargeUsd=2.5" in url[0]


def test_limit_bi_kep_theo_tran_va_bao_cho_nguoi_dung(cau_hinh, monkeypatch):
    cau_hinh({"tran_bai": 200})
    nhan = []
    monkeypatch.setitem(A._FETCH, "tiktok",
                        lambda q, lim, *a: nhan.append(lim) or [])
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A.chi_phi_tool, "ghi", lambda **k: {})
    kq = json.loads(A._handle({"queries": ["hapas"], "platforms": ["tiktok"],
                               "date_from": "2026-09-19", "date_to": "2026-09-25",
                               "limit": 900}))
    assert nhan == [200], "fetcher phải nhận limit ĐÃ kẹp theo trần console"
    assert kq["tran_bai"] == 200
    assert "900" in kq["limit_bi_cat"] and "console" in kq["limit_bi_cat"]


# ───────────────────── lsr_policy đọc `cau_hinh` từ danh bạ ─────────────────────

@pytest.fixture
def danh_ba(monkeypatch):
    cu = dict(lsr_policy._nho_nl)

    def dat(caps):
        body = json.dumps({"caller": "AG-SOCIAL-LISTENING", "agents": [
            {"agent_id": "AG-SOCIAL-LISTENING", "capabilities": caps}]}).encode()

        class X(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda r, timeout=5: X(body))
        lsr_policy._nho_nl.update(bat=None, luc=0.0)

    monkeypatch.setenv("LSR_TELEMETRY_API_KEY", "k")
    monkeypatch.setenv("LSR_PLATFORM_URL", "https://platform.test")
    yield dat
    lsr_policy._nho_nl.clear()
    lsr_policy._nho_nl.update(cu)


def test_doc_cau_hinh_cung_muc_cong_tac(danh_ba):
    danh_ba([{"tool": "social_listen", "name": "Quét", "description": "",
              "cau_hinh": {"tran_bai": 800, "tran_usd": 2}},
             {"tool": "web_scrape", "name": "Đọc", "description": ""}])
    assert lsr_policy.cau_hinh_tool("social_listen") == {"tran_bai": 800, "tran_usd": 2}
    assert lsr_policy.cau_hinh_tool("web_scrape") == {}
    assert lsr_policy.nang_luc_bat() == {"social_listen", "web_scrape"}, (
        "thêm `cau_hinh` không được làm lệch công tắc")


def test_go_cau_hinh_tren_console_thi_ve_mac_dinh(danh_ba):
    danh_ba([{"tool": "social_listen", "cau_hinh": {"tran_bai": 800}}])
    assert lsr_policy.cau_hinh_tool("social_listen") == {"tran_bai": 800}
    danh_ba([{"tool": "social_listen"}])
    assert lsr_policy.cau_hinh_tool("social_listen") == {}


def test_chua_khai_capabilities_thi_khong_con_cau_hinh_cu(danh_ba):
    danh_ba([{"tool": "social_listen", "cau_hinh": {"tran_bai": 800}}])
    lsr_policy.cau_hinh_tool("social_listen")
    danh_ba(None)
    assert lsr_policy.cau_hinh_tool("social_listen") == {}
    assert time.time() - lsr_policy._nho_nl["luc"] < 5


def test_khop_khoang_va_mac_dinh_ben_console():
    """Console chặn gõ nhầm bằng min/max của nó; lệch với runtime là console cho lưu
    một số rồi runtime lặng lẽ kẹp thành số khác, hoặc báo "đang dùng mặc định" sai."""
    import pathlib
    import re
    ts = pathlib.Path(r"D:\Platform\apps\platform-web\lib\agentToolCapabilities.ts")
    if not ts.is_file():
        pytest.skip("không thấy repo Platform trên máy này")
    s = ts.read_text(encoding="utf-8")

    def truong(khoa):
        m = re.search(rf'khoa:\s*"{khoa}"[^}}]*', s)
        assert m, f"console không có ô {khoa}"
        return {k: float(re.search(rf"\b{k}:\s*([\d.]+)", m.group(0)).group(1))
                for k in ("min", "max", "mac_dinh")}

    bai, usd = truong("tran_bai"), truong("tran_usd")
    assert (bai["min"], bai["max"], bai["mac_dinh"]) == (*A._TRAN_BAI_KHOANG, A._MAX_LIMIT)
    assert (usd["min"], usd["max"], usd["mac_dinh"]) == (*A._TRAN_USD_KHOANG, A._MAX_CHARGE)
