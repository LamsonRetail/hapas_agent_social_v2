"""Mark chạy bằng tài khoản AI gán trên console — mọi thứ đều giả, không mạng, không
token thật."""
from __future__ import annotations

import json

import pytest

import brain
import hermes_cli.runtime_provider as hrp
import tai_khoan_ai as T
from config import config

TOKEN_GIA = "sk-ant-oat01-GIA-KHONG-PHAI-THAT"
ACCESS_GIA = "eyJ-GIA-ACCESS"


def _lease_anthropic(**k):
    return {"mode": "subscription", "provider": "anthropic", "label": "Claude subscription",
            "credential_id": "c-claude", "env_var": "CLAUDE_CODE_OAUTH_TOKEN",
            "owner_email": "ai@vi.du", "secret": TOKEN_GIA + "\n", **k}


def _lease_openai(**k):
    blob = {"tokens": {"access_token": ACCESS_GIA, "refresh_token": "rt-GIA",
                       "id_token": "id-GIA", "account_id": "acc"}, "auth_mode": "chatgpt"}
    return {"mode": "subscription", "provider": "openai", "label": "ChatGPT Pro",
            "credential_id": "c-gpt", "secret": json.dumps(blob), **k}


@pytest.fixture
def bat_console(monkeypatch, tmp_path):
    monkeypatch.setenv("MARK_THEO_TAI_KHOAN_CONSOLE", "1")
    monkeypatch.delenv("MARK_LEASE_TTL", raising=False)
    monkeypatch.delenv("MARK_MODEL_ANTHROPIC", raising=False)
    monkeypatch.setattr(T, "_SO_DIR", tmp_path / "so")
    T.xoa_cache()
    T._GAN_NHAT.clear()
    goi_may = []

    def may_gia(requested=None, **k):
        goi_may.append(requested)
        return {"provider": "openai-codex", "api_mode": "codex_responses",
                "base_url": "https://chatgpt.com/backend-api/codex", "api_key": "MAY"}
    monkeypatch.setattr(hrp, "resolve_runtime_provider", may_gia)
    yield goi_may
    T.xoa_cache()
    T._GAN_NHAT.clear()


def _cho_lease(monkeypatch, *leases):
    """Giả _xin_lease, trả lần lượt từng lease; đếm số lần gọi."""
    dem = []
    hang = list(leases)

    def xin():
        dem.append(1)
        l = hang.pop(0) if len(hang) > 1 else hang[0]
        return (l, "ok") if l else (None, "URLError: giả")
    monkeypatch.setattr(T.lsr_platform, "_xin_lease", xin)
    return dem


# ─────────────────────────────── chọn runtime ───────────────────────────────

def test_lease_anthropic_ra_runtime_anthropic_va_model_claude(monkeypatch, bat_console):
    _cho_lease(monkeypatch, _lease_anthropic())
    rt, model, nguon = T.chon_runtime()
    assert rt["provider"] == "anthropic" and rt["api_mode"] == "anthropic_messages"
    assert rt["base_url"] == "https://api.anthropic.com"
    assert rt["api_key"] == TOKEN_GIA, "token phải được bỏ ký tự xuống dòng"
    assert model == "claude-sonnet-4-6"
    assert nguon["tu"] == "console" and nguon["credential_id"] == "c-claude"
    assert nguon["label"] == "Claude subscription"
    assert TOKEN_GIA not in json.dumps(nguon) and "ai@vi.du" not in json.dumps(nguon)
    assert bat_console == [], "đường máy không được chạm"


def test_model_anthropic_doi_duoc_qua_env(monkeypatch, bat_console):
    monkeypatch.setenv("MARK_MODEL_ANTHROPIC", "claude-opus-4-6")
    _cho_lease(monkeypatch, _lease_anthropic())
    assert T.chon_runtime()[1] == "claude-opus-4-6"


def test_lease_openai_ra_runtime_codex_KHONG_ghi_auth_json(monkeypatch, bat_console, tmp_path):
    home = tmp_path / "hermes"
    home.mkdir()
    auth = home / "auth.json"
    auth.write_text('{"providers": {}}', encoding="utf-8")
    truoc = (auth.read_bytes(), auth.stat().st_mtime_ns, sorted(p.name for p in home.iterdir()))
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_CODEX_BASE_URL", raising=False)
    _cho_lease(monkeypatch, _lease_openai())

    rt, model, nguon = T.chon_runtime()

    assert rt["provider"] == "openai-codex" and rt["api_mode"] == "codex_responses"
    assert rt["base_url"] == "https://chatgpt.com/backend-api/codex"
    assert rt["api_key"] == ACCESS_GIA
    assert model == config.agent_model
    assert nguon["tu"] == "console" and nguon["provider"] == "openai"
    sau = (auth.read_bytes(), auth.stat().st_mtime_ns, sorted(p.name for p in home.iterdir()))
    assert sau == truoc, "auth.json của máy bị đụng"
    assert bat_console == []


@pytest.mark.parametrize("lease", [
    {"mode": "api", "credential_id": "c-api", "base_url": "http://litellm", "model": "x"},
    _lease_anthropic(provider="gemini"),
    _lease_anthropic(secret=""),
    _lease_anthropic(secret="   \n"),
    _lease_openai(secret="khong-phai-json"),
    _lease_openai(secret=json.dumps({"tokens": {}})),
    None,
], ids=["api", "provider-la", "khong-secret", "secret-rong", "openai-hong", "openai-thieu",
        "loi-lease"])
def test_khong_ho_tro_hoac_loi_thi_ve_duong_may(monkeypatch, bat_console, lease):
    _cho_lease(monkeypatch, lease)
    rt, model, nguon = T.chon_runtime()
    assert bat_console == [config.agent_provider]
    assert rt["api_key"] == "MAY" and model == config.agent_model
    assert nguon["tu"] == "may" and nguon["credential_id"] is None and nguon["ly_do"]
    assert "khong-phai-json" not in nguon["ly_do"]


def test_co_0_la_duong_cu_khong_xin_lease(monkeypatch, bat_console):
    monkeypatch.setenv("MARK_THEO_TAI_KHOAN_CONSOLE", "0")
    dem = _cho_lease(monkeypatch, _lease_anthropic())
    rt, model, nguon = T.chon_runtime()
    assert dem == [], "cờ 0 mà vẫn xin lease"
    assert bat_console == [config.agent_provider] and model == config.agent_model
    assert nguon["tu"] == "may"


def test_co_0_resolve_agent_y_nhu_cu(monkeypatch, bat_console):
    """Cờ 0: _resolve_agent dựng agent bằng đúng runtime + model cũ, không gắn gì thêm."""
    monkeypatch.setenv("MARK_THEO_TAI_KHOAN_CONSOLE", "0")
    dem = _cho_lease(monkeypatch, _lease_anthropic())
    bat = {}

    class A:
        pass

    def dung(rt, model, *a):
        bat.update(rt=rt, model=model)
        return A()
    monkeypatch.setattr(brain, "_dung_agent", dung)
    a = brain._resolve_agent(None, None)
    assert dem == [] and bat["rt"]["api_key"] == "MAY" and bat["model"] == config.agent_model
    assert not hasattr(a, "_tai_khoan_nguon")
    assert "_try_refresh_anthropic_client_credentials" not in vars(a)


def test_cache_lease_theo_ttl(monkeypatch, bat_console):
    dem = _cho_lease(monkeypatch, _lease_anthropic())
    gio = [1000.0]
    monkeypatch.setattr(T.time, "monotonic", lambda: gio[0])
    T.chon_runtime()
    T.chon_runtime()
    assert len(dem) == 1, "trong TTL phải dùng lại lease"
    gio[0] += 61
    T.chon_runtime()
    assert len(dem) == 2, "quá 60s phải xin lại"
    monkeypatch.setenv("MARK_LEASE_TTL", "0")
    T.chon_runtime()
    assert len(dem) == 3


def test_loi_lease_cung_duoc_nho_trong_ttl(monkeypatch, bat_console):
    """Platform sập thì không bắt mỗi lượt chờ timeout."""
    dem = _cho_lease(monkeypatch, None)
    T.chon_runtime()
    T.chon_runtime()
    assert len(dem) == 1


def test_gan_vao_agent_khoa_tu_doc_lai_dang_nhap(monkeypatch, bat_console):
    class A:
        def _try_refresh_anthropic_client_credentials(self):
            raise AssertionError("không được gọi bản gốc")

    a = A()
    T.gan_vao_agent(a, {"tu": "console", "label": "x", "credential_id": "c"})
    assert a._try_refresh_anthropic_client_credentials() is False
    assert a._try_refresh_codex_client_credentials(force=True) is False
    assert a._tai_khoan_nguon["credential_id"] == "c"
    b = A()
    T.gan_vao_agent(b, {"tu": "may"})
    assert "_try_refresh_anthropic_client_credentials" not in vars(b)


# ─────────────────────────────── phân loại + báo lỗi ───────────────────────────

@pytest.mark.parametrize("loi,mong", [
    ("API call failed after 3 retries: HTTP 429: The usage limit has been reached", "limit"),
    ("rate_limit_error: Number of request tokens has exceeded your rate limit", "limit"),
    ("insufficient_quota", "limit"),
    ("HTTP 401: authentication_error: invalid x-api-key", "auth_error"),
    ("OAuth token has expired", "auth_error"),
    ("Unauthorized", "auth_error"),
    ("invalid bearer token", "auth_error"),
    ("HTTP 500: Internal server error", None),
    ("Request payload too large: max compression attempts (3) reached.", None),
    ("", None),
])
def test_phan_loai_loi(loi, mong):
    assert T.phan_loai_loi(loi) == mong


def test_phan_loai_nhan_exception():
    assert T.phan_loai_loi(RuntimeError("Error code: 429 - rate limited")) == "limit"


def test_bao_loi_console_bao_platform_va_bo_cache(monkeypatch, bat_console):
    dem = _cho_lease(monkeypatch, _lease_anthropic())
    T.chon_runtime()
    bao = []
    monkeypatch.setattr(T, "_bao_platform", lambda cid, ly_do: bao.append((cid, ly_do)) or True)
    nguon = {"tu": "console", "credential_id": "c-claude", "label": "Claude"}
    assert T.bao_loi(nguon, "HTTP 429 usage limit") == "limit"
    assert bao == [("c-claude", "limit")]
    T.chon_runtime()
    assert len(dem) == 2, "báo lỗi xong phải xin lease mới"
    assert T.bao_loi(nguon, RuntimeError("HTTP 401 Unauthorized")) == "auth_error"
    assert bao[-1] == ("c-claude", "auth_error")


def test_bao_loi_khong_bao_cho_luot_chay_bang_may(monkeypatch, bat_console):
    bao = []
    monkeypatch.setattr(T, "_bao_platform", lambda *a: bao.append(a))
    assert T.bao_loi({"tu": "may", "credential_id": None}, "HTTP 429") == "limit"
    assert T.bao_loi({"tu": "console", "credential_id": "c"}, "HTTP 500 lỗi lạ") is None
    assert bao == []


def test_bao_platform_goi_dung_endpoint(monkeypatch):
    monkeypatch.setenv("LSR_COLLECTOR", "https://collector.vi-du.test")
    monkeypatch.setenv("LSR_AGENT_ID", "AG-THU")
    monkeypatch.setenv("LSR_TELEMETRY_API_KEY", "khoa-gia")
    bat = {}

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def urlopen(req, timeout=None):
        bat.update(url=req.full_url, body=json.loads(req.data), method=req.get_method())
        return R()
    monkeypatch.setattr(T.urllib.request, "urlopen", urlopen)
    assert T._bao_platform("c-claude", "limit") is True
    assert bat["url"] == "https://platform.vi-du.test/v1/self/model-auth/report"
    assert bat["body"] == {"credential_id": "c-claude", "reason": "limit"}
    assert bat["method"] == "POST"


# ─────────────────────────────── brain: chạy lại một lần ───────────────────────

HONG_429 = {"final_response": "API call failed after 3 retries: HTTP 429: The usage limit "
                              "has been reached", "failed": True, "messages": []}
OK = {"final_response": "Xin chào", "messages": []}


class AgentGia:
    def __init__(self, nguon, *ket_qua):
        self._tai_khoan_nguon = nguon
        self.ket_qua = list(ket_qua)
        self.so_lan = 0
        self.model = "m-" + str(nguon.get("credential_id") if nguon else "?")

    def run_conversation(self, *a, **k):
        self.so_lan += 1
        r = self.ket_qua.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r


def _nguon(cid, tu="console"):
    return {"tu": tu, "credential_id": cid if tu == "console" else None,
            "label": cid or "máy", "provider": "anthropic", "mode": "subscription"}


@pytest.fixture
def bao(monkeypatch, bat_console):
    da_bao = []
    monkeypatch.setattr(T, "_bao_platform", lambda cid, ly_do: da_bao.append((cid, ly_do)) or True)
    return da_bao


def _chay(monkeypatch, agent_dau, chon_moi, ds_agent):
    """chon_moi: kết quả chon_runtime() khi xin lại; ds_agent: agent dựng lần lượt."""
    may = []
    monkeypatch.setattr(T, "chon_runtime", lambda: ({}, "m", chon_moi))
    monkeypatch.setattr(T, "chon_runtime_may",
                        lambda ly_do="": may.append(ly_do) or ({}, "m", _nguon(None, "may")))
    hang = list(ds_agent)
    dung = []

    def dung_lai(chon):
        dung.append(chon[2])
        return hang.pop(0)
    kq = brain._chay_co_doi_tai_khoan(agent_dau, "hi", [], dung_lai)
    return kq, dung, may


def test_429_doi_lease_roi_thanh_cong(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), HONG_429)
    a2 = AgentGia(_nguon("c2"), OK)
    (agent, out, exc, so_lan), dung, may = _chay(monkeypatch, a1, _nguon("c2"), [a2])
    assert out == OK and exc is None and so_lan == 2 and agent is a2
    assert bao == [("c1", "limit")] and may == []
    assert a1.so_lan == 1 and a2.so_lan == 1


def test_hong_hai_lan_thi_chay_bang_may_va_dung_lai(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), HONG_429)
    a2 = AgentGia(_nguon("c2"), HONG_429)
    a3 = AgentGia(_nguon(None, "may"), OK)
    (agent, out, exc, so_lan), dung, may = _chay(monkeypatch, a1, _nguon("c2"), [a2, a3])
    assert agent is a3 and out == OK and so_lan == 3
    assert bao == [("c1", "limit"), ("c2", "limit")] and len(may) == 1


def test_hong_ca_ba_lan_khong_bao_gio_qua_ba(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), HONG_429)
    a2 = AgentGia(_nguon("c2"), HONG_429)
    a3 = AgentGia(_nguon(None, "may"), HONG_429)
    (agent, out, exc, so_lan), dung, may = _chay(monkeypatch, a1, _nguon("c2"), [a2, a3])
    assert so_lan == 3 and out == HONG_429
    assert [a.so_lan for a in (a1, a2, a3)] == [1, 1, 1]
    assert bao == [("c1", "limit"), ("c2", "limit")], "lượt máy không được báo"


def test_lease_moi_van_la_tai_khoan_vua_hong_thi_xuong_may_ngay(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), HONG_429)
    a3 = AgentGia(_nguon(None, "may"), OK)
    (agent, out, exc, so_lan), dung, may = _chay(monkeypatch, a1, _nguon("c1"), [a3])
    assert agent is a3 and so_lan == 2 and len(may) == 1


def test_lan_dau_da_la_may_thi_khong_chay_lai(monkeypatch, bao):
    a1 = AgentGia(_nguon(None, "may"), HONG_429)
    (agent, out, exc, so_lan), dung, may = _chay(monkeypatch, a1, _nguon("c2"), [])
    assert so_lan == 1 and dung == [] and bao == []


def test_401_nem_exception_bao_auth_error_roi_chay_lai(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), RuntimeError("Error code: 401 - authentication_error"))
    a2 = AgentGia(_nguon("c2"), OK)
    (agent, out, exc, so_lan), dung, may = _chay(monkeypatch, a1, _nguon("c2"), [a2])
    assert exc is None and out == OK and bao == [("c1", "auth_error")]


def test_loi_khong_phan_loai_duoc_thi_khong_chay_lai(monkeypatch, bao):
    hong = {"final_response": "API call failed: HTTP 500", "failed": True}
    a1 = AgentGia(_nguon("c1"), hong)
    (agent, out, exc, so_lan), dung, may = _chay(monkeypatch, a1, _nguon("c2"), [])
    assert so_lan == 1 and out == hong and bao == []


def test_da_chay_tool_thi_khong_chay_lai(monkeypatch, bao):
    """Chạy lại một lượt đã quét Apify/ghi Sheet là tốn tiền và ghi trùng."""
    hong = dict(HONG_429, messages=[{"role": "user", "content": "hi"},
                                    {"role": "tool", "content": "{}"}])
    a1 = AgentGia(_nguon("c1"), hong)
    (agent, out, exc, so_lan), dung, may = _chay(monkeypatch, a1, _nguon("c2"), [])
    assert so_lan == 1 and dung == []
    assert bao == [("c1", "limit")], "vẫn phải báo platform cho tài khoản hết hạn mức"


def test_agent_khong_gan_nguon_thi_y_nhu_cu(monkeypatch, bao):
    """Cờ 0 / agent giả của bộ thử cũ: không có _tai_khoan_nguon → chạy đúng một lần."""
    class A:
        n = 0

        def run_conversation(self, *a, **k):
            A.n += 1
            return HONG_429
    (agent, out, exc, so_lan), dung, may = _chay(monkeypatch, A(), _nguon("c2"), [])
    assert A.n == 1 and so_lan == 1 and bao == []


def test_reply_doi_tai_khoan_ghi_so_va_nangluc(monkeypatch, bao, tmp_path):
    """Nối trọn: reply → hỏng 429 ở c1 → lease c2 → trả lời; sổ và /nangluc ghi c2."""
    import lenh_cung
    chon = [({}, "claude-sonnet-4-6", _nguon("c1")), ({}, "claude-sonnet-4-6", _nguon("c2"))]
    monkeypatch.setattr(T, "chon_runtime", lambda: chon.pop(0))
    ket_qua = [HONG_429, OK]

    class A:
        def __init__(self, model):
            self.model = model

        def run_conversation(self, *a, **k):
            return ket_qua.pop(0)
    monkeypatch.setattr(brain, "_dung_agent", lambda rt, model, *a: A(model))
    monkeypatch.setattr(brain.lsr_platform, "lay_ngu_canh", lambda *a, **k: {})
    monkeypatch.setattr(brain.lsr_platform, "ghi_luot_ngu_canh", lambda *a, **k: None)
    monkeypatch.setattr(brain.memory_store, "load_history", lambda cid: [])
    monkeypatch.setattr(brain.memory_store, "append_turns", lambda *a, **k: None)
    monkeypatch.setattr(brain.audit, "bat_dau", lambda *a, **k: "t")
    monkeypatch.setattr(brain.audit, "ket_thuc", lambda *a, **k: {})

    dap = brain.reply("chào", chat_id="thu-tai-khoan", sender_open_id=None)

    assert dap == "Xin chào"
    assert bao == [("c1", "limit")]
    dong = [json.loads(x) for f in (T._SO_DIR).glob("*.jsonl")
            for x in f.read_text(encoding="utf-8").splitlines()]
    assert len(dong) == 1 and dong[0]["credential_id"] == "c2" and dong[0]["so_lan"] == 2
    assert dong[0]["ket_qua"] == "ok" and dong[0]["chat"] == "thu-tai-khoan"
    assert "Tài khoản AI lượt gần nhất: c2 (anthropic, console)" in lenh_cung._van_nangluc()


def test_nangluc_khong_them_dong_khi_co_tat(monkeypatch):
    import lenh_cung
    T._GAN_NHAT.update({"label": "X"})
    try:
        assert "Tài khoản AI" not in lenh_cung._van_nangluc()
    finally:
        T._GAN_NHAT.clear()


def test_mo_ta_runtime_khong_lo_api_key(monkeypatch, bat_console):
    _cho_lease(monkeypatch, _lease_anthropic())
    mo_ta = T.mo_ta_runtime(*T.chon_runtime())
    assert TOKEN_GIA not in json.dumps(mo_ta, ensure_ascii=False)
    assert mo_ta["base_url_host"] == "api.anthropic.com" and mo_ta["tu"] == "console"
