"""Model theo console (chủ agent chốt 02/10/2026): chủ agent chọn MỘT model cho mỗi
provider trên console, áp cho mọi việc của Mark — lượt chat, AI phân xử, gán nhãn bình
luận, quét nền. Mọi thứ đều giả: không mạng, không token thật, không Apify.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re

import pytest

import apify_tool as A
import brain
import hermes_cli.runtime_provider as hrp
import lsr_platform
import tai_khoan_ai as T
from config import config

TOKEN_GIA = "sk-ant-oat01-GIA-KHONG-PHAI-THAT"
ACCESS_GIA = "eyJ-GIA-ACCESS"


def _lease_anthropic(**k):
    return {"mode": "subscription", "provider": "anthropic", "credential_id": "c-claude",
            "secret": TOKEN_GIA, **k}


def _lease_openai(**k):
    blob = {"tokens": {"access_token": ACCESS_GIA}, "auth_mode": "chatgpt"}
    return {"mode": "subscription", "provider": "openai", "credential_id": "c-gpt",
            "secret": json.dumps(blob), **k}


@pytest.fixture
def console(monkeypatch, tmp_path):
    monkeypatch.setenv("MARK_THEO_TAI_KHOAN_CONSOLE", "1")
    monkeypatch.delenv("MARK_LEASE_TTL", raising=False)
    monkeypatch.delenv("MARK_MODEL_ANTHROPIC", raising=False)
    monkeypatch.setattr(T, "_SO_DIR", tmp_path / "so")
    monkeypatch.setattr(T, "_GAN_NHAT", {})
    monkeypatch.setattr(lsr_platform, "_MODEL_VUA_CHAY", {})
    T.xoa_cache()
    may = []

    def may_gia(requested=None, **k):
        may.append(requested)
        return {"provider": "openai-codex", "api_mode": "codex_responses",
                "base_url": "https://chatgpt.com/backend-api/codex", "api_key": "MAY"}
    monkeypatch.setattr(hrp, "resolve_runtime_provider", may_gia)
    yield may
    T.xoa_cache()


def _cho_lease(monkeypatch, lease):
    dem = []
    monkeypatch.setattr(T.lsr_platform, "_xin_lease",
                        lambda: dem.append(1) or ((lease, "ok") if lease else (None, "giả")))
    return dem


# ─────────────────────────────── chọn model ───────────────────────────────

@pytest.mark.parametrize("lease,mong", [
    (_lease_anthropic(model="claude-opus-5-5"), "claude-opus-5-5"),
    (_lease_anthropic(model="  claude-haiku-4-5 "), "claude-haiku-4-5"),
    (_lease_openai(model="gpt-5.5"), "gpt-5.5"),
    (_lease_openai(model="gpt-6.1-sol"), "gpt-6.1-sol"),
])
def test_lease_co_model_hop_le_thi_dung_model_do(monkeypatch, console, lease, mong):
    _cho_lease(monkeypatch, lease)
    rt, model, nguon = T.chon_runtime()
    assert model == mong
    assert nguon["tu"] == "console" and nguon["model_tu"] == "console"
    assert nguon["ly_do_model"] == "" and console == []


@pytest.mark.parametrize("lease,mac_dinh", [
    (_lease_anthropic(model="claude-sonnet-9"), "claude-sonnet-4-6"),
    (_lease_anthropic(model="gpt-5.5"), "claude-sonnet-4-6"),        # chéo provider
    (_lease_openai(model="claude-opus-5-5"), config.agent_model),     # chéo provider
    (_lease_openai(model="gpt-4o"), config.agent_model),
    # Hermes liệt kê nhưng Codex backend trả 400 với tài khoản ChatGPT (thử thật 02/10).
    (_lease_openai(model="gpt-5.6-sol-pro"), config.agent_model),
    (_lease_openai(model="gpt-5.3-codex-spark"), config.agent_model),
    (_lease_openai(model=""), config.agent_model),
    (_lease_openai(model="   "), config.agent_model),
    (_lease_anthropic(model=123), "claude-sonnet-4-6"),
    (_lease_anthropic(model=["claude-opus-5-5"]), "claude-sonnet-4-6"),
], ids=["la", "cheo-anthropic", "cheo-openai", "ngoai-ds", "pro", "spark", "rong", "trang",
        "so", "list"])
def test_model_sai_hoac_cheo_provider_thi_ve_mac_dinh_va_ghi_ly_do(monkeypatch, console,
                                                                    lease, mac_dinh, capsys):
    _cho_lease(monkeypatch, lease)
    rt, model, nguon = T.chon_runtime()
    assert model == mac_dinh
    assert nguon["tu"] == "console", "model sai không được làm rơi tài khoản console"
    assert nguon["model_tu"] == "mac_dinh" and nguon["ly_do_model"]
    assert "dùng mặc định" in capsys.readouterr().out


@pytest.mark.parametrize("lease", [_lease_anthropic(model=None), _lease_anthropic(),
                                   _lease_openai(model=None)], ids=["null", "thieu", "oa"])
def test_model_null_hoac_thieu_thi_mac_dinh_khong_ly_do(monkeypatch, console, lease):
    _cho_lease(monkeypatch, lease)
    rt, model, nguon = T.chon_runtime()
    assert model == T._model_mac_dinh(lease["provider"])
    assert nguon["model_tu"] == "mac_dinh" and nguon["ly_do_model"] == ""


def test_model_mac_dinh_anthropic_van_doi_duoc_qua_env(monkeypatch, console):
    monkeypatch.setenv("MARK_MODEL_ANTHROPIC", "claude-opus-4-6")
    _cho_lease(monkeypatch, _lease_anthropic(model=None))
    assert T.chon_runtime()[1] == "claude-opus-4-6"


@pytest.mark.parametrize("lease", [
    _lease_anthropic(model="claude-opus-5-5", secret=""),
    _lease_openai(model="gpt-5.5", secret=None),
    _lease_anthropic(model="claude-opus-5-5", mode="api"),
    _lease_anthropic(model="claude-opus-5-5", provider="gemini"),
], ids=["khong-secret", "openai-khong-secret", "api", "provider-la"])
def test_duong_may_bo_model_console(monkeypatch, console, lease):
    """Credential kiểu file trên VM: lease không mang secret → chạy bằng máy. Model console
    của provider mà máy không đăng nhập thì không chạy được — giữ model của máy."""
    _cho_lease(monkeypatch, lease)
    rt, model, nguon = T.chon_runtime()
    assert rt["api_key"] == "MAY" and model == config.agent_model
    assert nguon["tu"] == "may" and nguon["model_tu"] == "mac_dinh"
    assert "bỏ model console" in nguon["ly_do_model"]


def test_mo_ta_runtime_hien_nguon_model(monkeypatch, console):
    _cho_lease(monkeypatch, _lease_anthropic(model="claude-opus-5-5"))
    mo_ta = T.mo_ta_runtime(*T.chon_runtime())
    assert mo_ta["model"] == "claude-opus-5-5" and mo_ta["model_tu"] == "console"
    assert TOKEN_GIA not in json.dumps(mo_ta)


# ─────────────────────── danh sách khớp platform + Hermes ───────────────────────

def test_ds_openai_dung_danh_sach_da_thu_that_tren_codex():
    """Không còn chép Hermes: đúng 7 model đã gọi thật được qua Codex backend (02/10)."""
    assert T.MODEL_CHO_PHEP["openai"] == (
        "gpt-6.1-sol", "gpt-6-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra",
        "gpt-5.6-luna", "gpt-5.5")


def _goc_platform() -> pathlib.Path:
    return pathlib.Path(os.environ.get("PLATFORM_REPO") or r"D:\Platform")


def test_ds_model_khop_hang_so_platform():
    """Platform (PR #88) giữ danh sách gốc ở `core/agent_model.py` (thuần: không DB,
    không HTTP). So TỪNG phần tử, đúng thứ tự, cả hai provider. Chưa có checkout / chưa
    có hằng số thì bỏ qua, như test_tran_nen_tang."""
    import importlib.util
    f = (_goc_platform() / "infra" / "lsr-platform" / "platform_api" / "core"
         / "agent_model.py")
    if not f.is_file():
        pytest.skip(f"không thấy {f} — đặt PLATFORM_REPO trỏ tới repo Platform có PR #88")
    spec = importlib.util.spec_from_file_location("_agent_model_platform", f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ds = getattr(mod, "MODEL_ALLOWLIST", None)
    assert isinstance(ds, dict), f"{f} không còn MODEL_ALLOWLIST"
    assert {p: tuple(v) for p, v in ds.items()} == T.MODEL_CHO_PHEP


# ─────────────────────── nhà cung cấp từ chối model ───────────────────────

class _Loi(Exception):
    def __init__(self, msg, status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class NotFoundError(Exception):
    pass


def _agent_hook(*su_kien):
    """Agent giả mà hook lỗi API của Hermes được gọi y như thật."""
    class Ag:
        def __init__(self):
            self.lan = 0

        def _invoke_api_request_error_hook(self, **k):
            pass

        def run_conversation(self, *a, **k):
            self.lan += 1
            for sk in su_kien:
                self._invoke_api_request_error_hook(error_type="BadRequestError", **sk)
            return {"final_response": "lỗi", "failed": True, "messages": []}
    a = Ag()
    T.gan_vao_agent(a, {"tu": "console", "credential_id": "c", "provider": "anthropic"})
    return a


@pytest.mark.parametrize("su_kien,mong", [
    # Đúng cách Hermes đưa ra (agent/error_classifier.py):
    ({"status_code": 404, "reason": "unknown",
      "error_message": "Error code: 404 - {'type': 'not_found_error', 'message': "
                       "'model: claude-opus-5-5'}"}, True),
    ({"status_code": 400, "reason": "format_error",
      "error_message": "The 'gpt-5.6-sol-pro' model is not supported when using Codex "
                       "with a ChatGPT account."}, True),
    ({"status_code": None, "reason": "model_not_found", "error_message": ""}, True),
    ({"status_code": 403, "reason": "auth",
      "error_message": "This model is not available on your subscription"}, True),
    ({"status_code": 429, "reason": "rate_limit", "error_message": "model overloaded"}, False),
    ({"status_code": 400, "reason": "format_error",
      "error_message": "messages must have non-empty content"}, False),
    ({"status_code": 500, "reason": "server_error", "error_message": "model not found"}, False),
], ids=["anthropic-404", "codex-400", "reason", "403-goi", "429", "400-khac", "500"])
def test_nhan_ra_tu_choi_model_tu_hook_hermes(console, su_kien, mong):
    a = _agent_hook(su_kien)
    out = a.run_conversation()
    assert T.model_bi_tu_choi(a, out, None) is mong
    assert "error_message" not in json.dumps(a._tai_khoan_loi_api), "không giữ thông điệp"


@pytest.mark.parametrize("m", ["gpt-5.6-sol-pro", "gpt-5.6-terra-pro", "gpt-5.6-luna-pro",
                               "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex",
                               "gpt-5.3-codex-spark"])
def test_hoi_quy_codex_400_that_la_tu_choi_model(console, m):
    """Đúng lỗi Codex backend trả khi thử thật 02/10/2026: Hermes xếp vào format_error,
    status 400 — vẫn phải nhận ra là model bị từ chối để chạy lại bằng mặc định."""
    a = _agent_hook({"status_code": 400, "reason": "format_error",
                     "error_message": f"The '{m}' model is not supported when using "
                                      f"Codex with a ChatGPT account."})
    out = a.run_conversation()
    assert a._tai_khoan_model_tu_choi is True
    assert T.model_bi_tu_choi(a, out, None) is True
    assert m not in T.MODEL_CHO_PHEP["openai"]


def test_tu_choi_model_chi_khi_luot_that_su_hong(console):
    """Như phan_loai_that_bai: không bao giờ đọc chữ model viết."""
    a = _agent_hook()
    assert not T.model_bi_tu_choi(a, {"final_response": "model not found 404"}, None)
    assert not T.model_bi_tu_choi(a, {"final_response": "x", "failure_reason":
                                      "model_not_found"}, None)
    assert T.model_bi_tu_choi(a, {"failed": True, "failure_reason": "model_not_found"}, None)
    assert T.model_bi_tu_choi(None, None, NotFoundError("x"))
    assert T.model_bi_tu_choi(None, None, _Loi("model: claude-x not_found_error", 404))
    assert not T.model_bi_tu_choi(None, None, _Loi("x", 401))
    assert not T.model_bi_tu_choi(None, None, RuntimeError("model not found"))


class _AgentGia:
    def __init__(self, nguon, model, *ket_qua):
        self._tai_khoan_nguon = nguon
        self.model = model
        self.ket_qua = list(ket_qua)
        self.lan = 0

    def run_conversation(self, *a, **k):
        self.lan += 1
        r = self.ket_qua.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r


OK = {"final_response": "Xin chào", "messages": []}
HONG_MODEL = {"final_response": "x", "failed": True, "failure_reason": "model_not_found",
              "messages": []}


def _nguon(model_tu="console"):
    return {"tu": "console", "credential_id": "c1", "provider": "anthropic",
            "mode": "subscription", "model_tu": model_tu, "ly_do_model": ""}


def test_brain_tu_choi_model_chay_lai_mot_lan_cung_tai_khoan_model_mac_dinh(monkeypatch,
                                                                            console):
    bao = []
    monkeypatch.setattr(T, "_bao_platform", lambda *a: bao.append(a) or True)
    monkeypatch.setattr(T, "chon_runtime", lambda: pytest.fail("không được xin lease lại"))
    rt = {"provider": "anthropic", "api_key": "k"}
    a1 = _AgentGia(_nguon(), "claude-opus-5-5", HONG_MODEL)
    a1._tai_khoan_chon = (rt, "claude-opus-5-5", _nguon())
    dung = []

    def dung_lai(chon):
        dung.append(chon)
        return _AgentGia(chon[2], chon[1], OK)
    agent, out, exc, so_lan = brain._chay_co_doi_tai_khoan(a1, "hi", [], dung_lai)
    assert out == OK and so_lan == 2 and agent.model == "claude-sonnet-4-6"
    (rt2, m2, n2), = dung
    assert rt2 is rt, "phải là CÙNG tài khoản"
    assert n2["credential_id"] == "c1" and n2["model_tu"] == "mac_dinh"
    assert "claude-opus-5-5" in n2["ly_do_model"]
    assert bao == [], "model bị từ chối không phải lỗi tài khoản — không báo platform"


def test_brain_403_tu_choi_model_khong_xuong_may(monkeypatch, console):
    may = []
    monkeypatch.setattr(T, "chon_runtime_may", lambda *a, **k: may.append(1))
    a1 = _AgentGia(_nguon(), "claude-opus-5-5",
                   _Loi("model claude-opus-5-5 is not allowed for this plan", 403))
    a1._tai_khoan_chon = ({}, "claude-opus-5-5", _nguon())
    agent, out, exc, so_lan = brain._chay_co_doi_tai_khoan(
        a1, "hi", [], lambda chon: _AgentGia(chon[2], chon[1], OK))
    assert out == OK and exc is None and may == []


@pytest.mark.parametrize("ca", ["mac-dinh", "da-chay-tool", "khong-chon"])
def test_brain_khong_chay_lai_model(monkeypatch, console, ca):
    hong = dict(HONG_MODEL)
    nguon = _nguon("mac_dinh" if ca == "mac-dinh" else "console")
    if ca == "da-chay-tool":
        hong["messages"] = [{"role": "tool", "content": "{}"}]
    a1 = _AgentGia(nguon, "m", hong)
    if ca != "khong-chon":
        a1._tai_khoan_chon = ({}, "m", nguon)
    agent, out, exc, so_lan = brain._chay_co_doi_tai_khoan(
        a1, "hi", [], lambda chon: pytest.fail("không được chạy lại"))
    assert so_lan == 1 and out == hong


def test_chay_mot_luot_tu_choi_model_chay_lai_mot_lan(console):
    dung = []

    def dung_agent(rt, model, nguon):
        dung.append(model)
        return _AgentGia(nguon, model, HONG_MODEL)
    chon = ({"provider": "anthropic"}, "claude-opus-5-5", _nguon())
    ag, out, exc, chon2 = T.chay_mot_luot(dung_agent, "nhắc", chon)
    assert dung == ["claude-opus-5-5", "claude-sonnet-4-6"], "đúng MỘT lần chạy lại"
    assert out == HONG_MODEL and chon2[2]["model_tu"] == "mac_dinh"
    dung.clear()
    T.chay_mot_luot(dung_agent, "nhắc", ({}, "claude-sonnet-4-6", _nguon("mac_dinh")))
    assert dung == ["claude-sonnet-4-6"], "model mặc định bị từ chối thì không có gì để thử"


# ─────────────────────── AI phân xử + quét nền ───────────────────────

class _AIAgentGia:
    tao: list = []

    def __init__(self, **kw):
        _AIAgentGia.tao.append(kw)
        self.model = kw["model"]

    def run_conversation(self, nhac):
        return {"final_response": json.dumps({i: ["k", "brand"] for i in
                                              re.findall(r'<p i="(\d+)">', nhac)})}


def _hang(n):
    now = datetime.datetime.now(A._VN_TZ)
    return [({"kenh": f"k{i}", "views": n - i, "text": f"bài {i}", "hashtags": "",
              "link": f"https://x/{i}"}, now) for i in range(n)]


def test_phan_xu_ai_dung_tai_khoan_va_model_console_mot_lease(monkeypatch, console):
    import run_agent
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "1")
    _AIAgentGia.tao = []
    monkeypatch.setattr(run_agent, "AIAgent", _AIAgentGia)
    dem = _cho_lease(monkeypatch, _lease_anthropic(model="claude-opus-5-5"))
    monkeypatch.setattr(T, "_ttl", lambda: 0.0)   # không có cache: đếm đúng số lần xin
    import time
    ket, tt = A._phan_xu_ai(_hang(3 * A._AI_LO), ["hapas"], "túi xách", "VN",
                            time.monotonic() + 30)
    assert tt["trang_thai"] == "đã chạy" and tt["so_lo"] == 3
    assert len(_AIAgentGia.tao) == 3
    assert {kw["model"] for kw in _AIAgentGia.tao} == {"claude-opus-5-5"}
    assert {kw["api_key"] for kw in _AIAgentGia.tao} == {TOKEN_GIA}, "phải là tài khoản console"
    assert {kw["provider"] for kw in _AIAgentGia.tao} == {"anthropic"}
    assert all(kw["max_iterations"] == 1 and kw["enabled_toolsets"] == []
               for kw in _AIAgentGia.tao)
    assert len(dem) == 1, "ba lô của một bước chỉ xin lease MỘT lần"
    assert console == [], "không được dựng runtime máy"


def test_phan_xu_ai_lease_hong_thi_van_chay_bang_may(monkeypatch, console):
    import run_agent
    import time
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "1")
    _AIAgentGia.tao = []
    monkeypatch.setattr(run_agent, "AIAgent", _AIAgentGia)
    _cho_lease(monkeypatch, None)
    ket, tt = A._phan_xu_ai(_hang(5), ["hapas"], "túi", "VN", time.monotonic() + 30)
    assert tt["trang_thai"] == "đã chạy"
    assert _AIAgentGia.tao[0]["api_key"] == "MAY"
    assert _AIAgentGia.tao[0]["model"] == config.agent_model


def test_phan_xu_ai_model_bi_tu_choi_lo_sau_di_thang_mac_dinh(monkeypatch, console):
    import run_agent
    import time
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "1")

    class Ag(_AIAgentGia):
        def run_conversation(self, nhac):
            if self.model == "claude-opus-5-5":
                return {"failed": True, "failure_reason": "model_not_found"}
            return super().run_conversation(nhac)
    _AIAgentGia.tao = []
    monkeypatch.setattr(run_agent, "AIAgent", Ag)
    _cho_lease(monkeypatch, _lease_anthropic(model="claude-opus-5-5"))
    ket, tt = A._phan_xu_ai(_hang(2 * A._AI_LO), ["hapas"], "túi", "VN",
                            time.monotonic() + 30, song_song=1)
    assert tt["trang_thai"] == "đã chạy"
    assert [kw["model"] for kw in _AIAgentGia.tao] == [
        "claude-opus-5-5", "claude-sonnet-4-6", "claude-sonnet-4-6"]


def test_phan_xu_ai_het_han_muc_bao_platform_mot_lan_roi_ve_luat(monkeypatch, console):
    import run_agent
    import time
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "1")

    class Ag(_AIAgentGia):
        def run_conversation(self, nhac):
            return {"failed": True, "failure_reason": "rate_limit", "final_response": "429"}
    _AIAgentGia.tao = []
    monkeypatch.setattr(run_agent, "AIAgent", Ag)
    _cho_lease(monkeypatch, _lease_anthropic())
    bao = []
    monkeypatch.setattr(T, "_bao_platform", lambda cid, ly_do: bao.append((cid, ly_do)) or True)
    ket, tt = A._phan_xu_ai(_hang(3 * A._AI_LO), ["hapas"], "túi", "VN",
                            time.monotonic() + 30)
    assert ket == {} and tt["lo_loi"] == 3, "lô hỏng vẫn rơi về luật như cũ"
    assert bao == [("c-claude", "limit")]


def test_gan_nhan_binh_luan_dung_model_console(monkeypatch, console):
    import phan_loai as P
    _AIAgentGia.tao = []
    monkeypatch.setattr(P, "_lop_agent", lambda: _AIAgentGia)
    _cho_lease(monkeypatch, _lease_openai(model="gpt-5.5"))
    P._goi_model("nhắc")
    assert _AIAgentGia.tao[0]["model"] == "gpt-5.5"
    assert _AIAgentGia.tao[0]["api_key"] == ACCESS_GIA


# ─────────────────────── usage + sổ ghi đúng model đã chạy ───────────────────────

def test_so_tai_khoan_ghi_model_da_chay(monkeypatch, console):
    nguon = dict(_nguon(), ly_do_model="")
    T.ghi_luot(nguon, "claude-opus-5-5", "chat-1", "ok", 1)
    dong = [json.loads(x) for f in T._SO_DIR.glob("*.jsonl")
            for x in f.read_text(encoding="utf-8").splitlines()]
    assert dong[0]["model"] == "claude-opus-5-5" and dong[0]["model_tu"] == "console"
    assert dong[0]["ly_do_model"] == ""


def test_bao_luot_gui_model_da_chay(monkeypatch, console):
    monkeypatch.setenv("LSR_COLLECTOR", "https://collector.example.test")
    monkeypatch.setenv("LSR_AGENT_ID", "AG-SOCIAL-LISTENING-TEST")
    monkeypatch.setenv("LSR_TELEMETRY_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MODEL", "gpt-5.6-terra")
    vet = []
    monkeypatch.setattr(lsr_platform, "_queue_trace", lambda t: vet.append(t) and None)
    T.ghi_luot(_nguon(), "claude-opus-5-5", "oc_1", "ok", 1)
    lsr_platform.bao_luot("m1", "hỏi", "đáp",
                          model=lsr_platform.lay_model_vua_chay("oc_1"))
    assert vet[0]["llm_calls"][0]["model"] == "claude-opus-5-5"
    assert lsr_platform.lay_model_vua_chay("oc_1") == "gpt-5.6-terra", (
        "lấy-và-xoá; chưa có lượt nào thì về env như cũ")
    lsr_platform.bao_luot("m2", "hỏi", "đáp")
    assert vet[1]["llm_calls"][0]["model"] == "gpt-5.6-terra"


def test_job_complete_bao_model_da_chay(monkeypatch, console):
    monkeypatch.setenv("AGENT_MODEL", "gpt-5.6-terra")
    goi = []

    def _goi(c, duong, than=None, timeout=None):
        if duong.startswith("/v1/self/jobs?"):
            return [{"id": 7, "session_id": "web:s1", "payload": {"text": "chào"}}]
        goi.append((duong, than))
        return {}
    monkeypatch.setattr(lsr_platform, "_goi", _goi)
    monkeypatch.setattr(lsr_platform, "_tai_anh", lambda c, j: [])

    def tra_loi(hoi, chat_id, sender_open_id=None, **k):
        T.ghi_luot(_nguon(), "claude-opus-5-5", chat_id, "ok", 1)
        return "đáp"
    assert lsr_platform._mot_vong({"url": "u", "key": "k"}, tra_loi) == 1
    xong = dict(goi)["/v1/self/jobs/7/complete"]
    assert xong["usage"]["model"] == "claude-opus-5-5"


def test_reply_noi_tron_model_console_vao_so_va_usage(monkeypatch, console):
    """reply → model console → sổ + usage cùng một model."""
    _cho_lease(monkeypatch, _lease_anthropic(model="claude-opus-5-5"))
    tao = []

    class Ag:
        def __init__(self, model):
            self.model = model
            tao.append(model)

        def run_conversation(self, *a, **k):
            return {"final_response": "Xin chào", "messages": []}
    monkeypatch.setattr(brain, "_dung_agent", lambda rt, model, *a: Ag(model))
    monkeypatch.setattr(brain.lsr_platform, "lay_ngu_canh", lambda *a, **k: {})
    monkeypatch.setattr(brain.lsr_platform, "ghi_luot_ngu_canh", lambda *a, **k: None)
    monkeypatch.setattr(brain.memory_store, "load_history", lambda cid: [])
    monkeypatch.setattr(brain.memory_store, "append_turns", lambda *a, **k: None)
    monkeypatch.setattr(brain.audit, "bat_dau", lambda *a, **k: "t")
    monkeypatch.setattr(brain.audit, "ket_thuc", lambda *a, **k: {})
    assert brain.reply("chào", chat_id="oc_x", sender_open_id=None) == "Xin chào"
    assert tao == ["claude-opus-5-5"]
    dong = [json.loads(x) for f in T._SO_DIR.glob("*.jsonl")
            for x in f.read_text(encoding="utf-8").splitlines()]
    assert dong[0]["model"] == "claude-opus-5-5" and dong[0]["model_tu"] == "console"
    assert lsr_platform.lay_model_vua_chay("oc_x") == "claude-opus-5-5"
