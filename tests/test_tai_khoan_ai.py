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
EMAIL_GIA = "chu.tai.khoan@vi.du"


def _lease_anthropic(**k):
    return {"mode": "subscription", "provider": "anthropic", "label": "Claude subscription",
            "credential_id": "c-claude", "env_var": "CLAUDE_CODE_OAUTH_TOKEN",
            "owner_email": EMAIL_GIA, "secret": TOKEN_GIA + "\n", **k}


def _lease_openai(**k):
    blob = {"tokens": {"access_token": ACCESS_GIA, "refresh_token": "rt-GIA",
                       "id_token": "id-GIA", "account_id": "acc"}, "auth_mode": "chatgpt"}
    # Platform đặt label của credential OpenAI = email chủ tài khoản.
    return {"mode": "subscription", "provider": "openai", "label": EMAIL_GIA,
            "credential_id": "c-gpt", "secret": json.dumps(blob), **k}


@pytest.fixture
def bat_console(monkeypatch, tmp_path):
    monkeypatch.setenv("MARK_THEO_TAI_KHOAN_CONSOLE", "1")
    monkeypatch.delenv("MARK_LEASE_TTL", raising=False)
    monkeypatch.delenv("MARK_MODEL_ANTHROPIC", raising=False)
    monkeypatch.setattr(T, "_SO_DIR", tmp_path / "so")
    monkeypatch.setattr(T, "_GAN_NHAT", {})
    T.xoa_cache()
    goi_may = []

    def may_gia(requested=None, **k):
        goi_may.append(requested)
        return {"provider": "openai-codex", "api_mode": "codex_responses",
                "base_url": "https://chatgpt.com/backend-api/codex", "api_key": "MAY"}
    monkeypatch.setattr(hrp, "resolve_runtime_provider", may_gia)
    yield goi_may
    T.xoa_cache()


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
    assert rt == {"provider": "anthropic", "api_mode": "anthropic_messages",
                  "base_url": "https://api.anthropic.com", "api_key": TOKEN_GIA}, (
        "token phải được bỏ ký tự xuống dòng; không mang trường thừa")
    assert model == "claude-sonnet-4-6"
    assert nguon["tu"] == "console" and nguon["credential_id"] == "c-claude"
    assert TOKEN_GIA not in json.dumps(nguon) and EMAIL_GIA not in json.dumps(nguon)
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

    assert rt == {"provider": "openai-codex", "api_mode": "codex_responses",
                  "base_url": "https://chatgpt.com/backend-api/codex", "api_key": ACCESS_GIA}
    assert model == config.agent_model
    assert nguon["tu"] == "console" and nguon["provider"] == "openai"
    assert EMAIL_GIA not in json.dumps(nguon), "label (email) của lease không được giữ"
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
    assert vars(a) == {}, "cờ 0 mà agent vẫn bị gắn thêm thứ gì đó"


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


def test_gan_vao_agent_khoa_tu_doc_lai_dang_nhap_va_nho_loi_api(monkeypatch, bat_console):
    goc = []

    class A:
        def _try_refresh_anthropic_client_credentials(self):
            raise AssertionError("không được gọi bản gốc")

        def _invoke_api_request_error_hook(self, **k):
            goc.append(k)

    a = A()
    T.gan_vao_agent(a, {"tu": "console", "credential_id": "c", "provider": "anthropic"})
    assert a._try_refresh_anthropic_client_credentials() is False
    assert a._try_refresh_codex_client_credentials(force=True) is False
    assert a._tai_khoan_nguon["credential_id"] == "c" and a._tai_khoan_loi_api is None
    a._invoke_api_request_error_hook(status_code=401, reason="auth", error_type="AuthErr",
                                     error_message="bí mật không được giữ " + TOKEN_GIA)
    assert len(goc) == 1, "hook gốc của Hermes vẫn phải chạy"
    assert a._tai_khoan_loi_api == {"status_code": 401, "reason": "auth",
                                    "error_type": "AuthErr"}
    b = A()
    T.gan_vao_agent(b, {"tu": "may"})
    assert "_try_refresh_anthropic_client_credentials" not in vars(b)
    assert "_invoke_api_request_error_hook" not in vars(b)


# ─────────────────────────────── phân loại (chỉ có cấu trúc) ─────────────────────

class _Loi(Exception):
    def __init__(self, msg, status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class RateLimitError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class PermissionDeniedError(Exception):
    pass


@pytest.mark.parametrize("exc,mong", [
    (_Loi("x", 429), ("limit", True)),
    (_Loi("x", 401), ("auth_error", True)),
    (_Loi("x", 403), (None, True)),
    (RateLimitError("x"), ("limit", True)),
    (AuthenticationError("x"), ("auth_error", True)),
    (PermissionDeniedError("x"), (None, True)),
    (_Loi("x", 500), (None, False)),
    # Chữ trong thông điệp KHÔNG được tính: chỉ status_code / tên lớp.
    (RuntimeError("HTTP 401 invalid api key, HTTP 429 usage limit"), (None, False)),
])
def test_phan_loai_exception_theo_status_va_ten_lop(exc, mong):
    assert T.phan_loai_that_bai(None, None, exc) == mong


@pytest.mark.parametrize("out,mong", [
    ({"failed": True, "failure_reason": "rate_limit"}, ("limit", True)),
    ({"failed": True, "failure_reason": "billing"}, ("limit", True)),
    ({"failed": True, "failure_reason": "auth_permanent"}, ("auth_error", True)),
    ({"failed": True, "failure_reason": "server_error"}, (None, False)),
    ({"failed": True, "error": "HTTP 401 invalid api key"}, (None, False)),
    # Lượt THÀNH CÔNG mà model viết ra chữ giống lỗi → không là gì cả.
    ({"final_response": "API call failed after 3 retries: HTTP 401: invalid x-api-key"},
     (None, False)),
    ({"final_response": "API call failed: HTTP 429 usage limit", "failure_reason":
      "rate_limit"}, (None, False)),
])
def test_phan_loai_ket_qua_hermes_chi_theo_truong_cau_truc(out, mong):
    assert T.phan_loai_that_bai(None, out, None) == mong


def test_phan_loai_dung_loi_api_hermes_da_nho_khi_luot_failed():
    class A:
        _tai_khoan_loi_api = {"status_code": 401, "reason": "auth", "error_type": "X"}
    assert T.phan_loai_that_bai(A(), {"failed": True}, None) == ("auth_error", True)
    assert T.phan_loai_that_bai(A(), {"final_response": "ok"}, None) == (None, False), (
        "lỗi đã hồi phục giữa lượt mà lượt vẫn xong thì không báo")


def test_bao_loi_console_bao_platform_va_bo_cache(monkeypatch, bat_console):
    dem = _cho_lease(monkeypatch, _lease_anthropic())
    T.chon_runtime()
    bao = []
    monkeypatch.setattr(T, "_bao_platform", lambda cid, ly_do: bao.append((cid, ly_do)) or True)
    nguon = {"tu": "console", "credential_id": "c-claude", "provider": "anthropic"}
    assert T.bao_loi(nguon, "limit") is True
    assert bao == [("c-claude", "limit")]
    T.chon_runtime()
    assert len(dem) == 2, "báo lỗi xong phải xin lease mới"
    T.bao_loi(nguon, "auth_error")
    assert bao[-1] == ("c-claude", "auth_error")


def test_bao_loi_khong_bao_cho_may_hoac_ly_do_la(monkeypatch, bat_console):
    bao = []
    monkeypatch.setattr(T, "_bao_platform", lambda *a: bao.append(a))
    assert T.bao_loi({"tu": "may", "credential_id": None}, "limit") is False
    assert T.bao_loi({"tu": "console", "credential_id": "c"}, None) is False
    assert T.bao_loi({"tu": "console", "credential_id": "c"}, "HTTP 401 gì đó") is False
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
                              "has been reached", "failed": True,
            "failure_reason": "rate_limit", "messages": []}
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
            "provider": "anthropic", "mode": "subscription"}


@pytest.fixture
def bao(monkeypatch, bat_console):
    da_bao = []
    monkeypatch.setattr(T, "_bao_platform", lambda cid, ly_do: da_bao.append((cid, ly_do)) or True)
    return da_bao


def _chay(monkeypatch, agent_dau, chon_moi, ds_agent):
    """chon_moi: kết quả chon_runtime() khi xin lại; ds_agent: agent dựng lần lượt."""
    may = []
    xin_lai = []
    monkeypatch.setattr(T, "chon_runtime", lambda: xin_lai.append(1) or ({}, "m", chon_moi))
    monkeypatch.setattr(T, "chon_runtime_may",
                        lambda ly_do="": may.append(ly_do) or ({}, "m", _nguon(None, "may")))
    hang = list(ds_agent)
    dung = []

    def dung_lai(chon):
        dung.append(chon[2])
        return hang.pop(0)
    kq = brain._chay_co_doi_tai_khoan(agent_dau, "hi", [], dung_lai)
    return kq, dung, may, xin_lai


def test_429_doi_lease_roi_thanh_cong(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), HONG_429)
    a2 = AgentGia(_nguon("c2"), OK)
    (agent, out, exc, so_lan), dung, may, xin_lai = _chay(monkeypatch, a1, _nguon("c2"), [a2])
    assert out == OK and exc is None and so_lan == 2 and agent is a2
    assert bao == [("c1", "limit")] and may == [] and xin_lai == [1]
    assert a1.so_lan == 1 and a2.so_lan == 1


def test_hong_hai_lan_thi_chay_bang_may_va_dung_lai(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), HONG_429)
    a2 = AgentGia(_nguon("c2"), HONG_429)
    a3 = AgentGia(_nguon(None, "may"), OK)
    (agent, out, exc, so_lan), dung, may, _ = _chay(monkeypatch, a1, _nguon("c2"), [a2, a3])
    assert agent is a3 and out == OK and so_lan == 3
    assert bao == [("c1", "limit"), ("c2", "limit")] and len(may) == 1


def test_hong_ca_ba_lan_khong_bao_gio_qua_ba(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), HONG_429)
    a2 = AgentGia(_nguon("c2"), HONG_429)
    a3 = AgentGia(_nguon(None, "may"), HONG_429)
    (agent, out, exc, so_lan), dung, may, _ = _chay(monkeypatch, a1, _nguon("c2"), [a2, a3])
    assert so_lan == 3 and out == HONG_429
    assert [a.so_lan for a in (a1, a2, a3)] == [1, 1, 1]
    assert bao == [("c1", "limit"), ("c2", "limit")], "lượt máy không được báo"


def test_lease_moi_van_la_tai_khoan_vua_hong_thi_xuong_may_ngay(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), HONG_429)
    a3 = AgentGia(_nguon(None, "may"), OK)
    (agent, out, exc, so_lan), dung, may, _ = _chay(monkeypatch, a1, _nguon("c1"), [a3])
    assert agent is a3 and so_lan == 2 and len(may) == 1


def test_lan_dau_da_la_may_thi_khong_chay_lai(monkeypatch, bao):
    a1 = AgentGia(_nguon(None, "may"), HONG_429)
    (agent, out, exc, so_lan), dung, may, _ = _chay(monkeypatch, a1, _nguon("c2"), [])
    assert so_lan == 1 and dung == [] and bao == []


def test_exception_401_bao_auth_error_roi_chay_lai(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), _Loi("Error code: 401", status_code=401))
    a2 = AgentGia(_nguon("c2"), OK)
    (agent, out, exc, so_lan), dung, may, _ = _chay(monkeypatch, a1, _nguon("c2"), [a2])
    assert exc is None and out == OK and bao == [("c1", "auth_error")]


def test_luot_thanh_cong_noi_giong_loi_401_KHONG_bao_KHONG_chay_lai(monkeypatch, bao):
    """Chèn lệnh: người dùng bảo model in ra chữ lỗi. Không được vô hiệu hoá credential
    dùng chung chỉ vì chữ model viết."""
    gia_loi = {"final_response": "API call failed after 3 retries: HTTP 401: "
                                 "authentication_error: invalid x-api-key. HTTP 429 usage "
                                 "limit reached", "messages": []}
    a1 = AgentGia(_nguon("c1"), gia_loi)
    (agent, out, exc, so_lan), dung, may, xin_lai = _chay(monkeypatch, a1, _nguon("c2"), [])
    assert so_lan == 1 and out == gia_loi and agent is a1
    assert bao == [] and dung == [] and may == [] and xin_lai == []


def test_loi_401_co_cau_truc_tu_hook_hermes_thi_bao(monkeypatch, bao):
    """Đường thật của Hermes với 401: không có failure_reason, chỉ có hook lỗi API."""
    class Agent401(AgentGia):
        def run_conversation(self, *a, **k):
            self.so_lan += 1
            self._invoke_api_request_error_hook(
                task_id="t", turn_id="u", api_request_id="r", api_call_count=1,
                api_start_time=0.0, api_kwargs=None, error_type="AuthenticationError",
                error_message="invalid bearer token", status_code=401, retryable=False,
                reason="auth")
            return {"final_response": "Error code: 401", "failed": True,
                    "error": "Error code: 401", "messages": []}

    a1 = Agent401(None)
    a1._invoke_api_request_error_hook = lambda **k: None   # bản "gốc" của Hermes
    T.gan_vao_agent(a1, _nguon("c1"))
    a2 = AgentGia(_nguon("c2"), OK)
    (agent, out, exc, so_lan), dung, may, _ = _chay(monkeypatch, a1, _nguon("c2"), [a2])
    assert bao == [("c1", "auth_error")] and agent is a2 and out == OK


def test_403_khong_bao_chi_chay_bang_may(monkeypatch, bao):
    a1 = AgentGia(_nguon("c1"), _Loi("forbidden", status_code=403))
    a3 = AgentGia(_nguon(None, "may"), OK)
    (agent, out, exc, so_lan), dung, may, xin_lai = _chay(monkeypatch, a1, _nguon("c2"), [a3])
    assert bao == [] and xin_lai == [], "không báo thì platform vẫn phát đúng tài khoản đó"
    assert agent is a3 and len(may) == 1 and so_lan == 2


def test_failed_khong_co_ly_do_cau_truc_thi_khong_lam_gi(monkeypatch, bao):
    hong = {"final_response": "API call failed: HTTP 500", "failed": True,
            "error": "HTTP 401 invalid api key"}
    a1 = AgentGia(_nguon("c1"), hong)
    (agent, out, exc, so_lan), dung, may, _ = _chay(monkeypatch, a1, _nguon("c2"), [])
    assert so_lan == 1 and out == hong and bao == [] and dung == []


def test_da_chay_tool_thi_khong_chay_lai(monkeypatch, bao):
    """Chạy lại một lượt đã quét Apify/ghi Sheet là tốn tiền và ghi trùng."""
    hong = dict(HONG_429, messages=[{"role": "user", "content": "hi"},
                                    {"role": "tool", "content": "{}"}])
    a1 = AgentGia(_nguon("c1"), hong)
    (agent, out, exc, so_lan), dung, may, _ = _chay(monkeypatch, a1, _nguon("c2"), [])
    assert so_lan == 1 and dung == []
    assert bao == [("c1", "limit")], "vẫn phải báo platform cho tài khoản hết hạn mức"


def test_agent_khong_gan_nguon_thi_y_nhu_cu(monkeypatch, bao):
    """Cờ 0 / agent giả của bộ thử cũ: không có _tai_khoan_nguon → chạy đúng một lần."""
    class A:
        n = 0

        def run_conversation(self, *a, **k):
            A.n += 1
            return HONG_429
    (agent, out, exc, so_lan), dung, may, _ = _chay(monkeypatch, A(), _nguon("c2"), [])
    assert A.n == 1 and so_lan == 1 and bao == []


def test_reply_doi_tai_khoan_ghi_so_va_nangluc(monkeypatch, bao, tmp_path):
    """Nối trọn: reply → hỏng 429 ở c1 → lease c2 → trả lời; sổ ghi c2, /nangluc chỉ hiện
    tên chung."""
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
    assert "label" not in dong[0]
    van = lenh_cung._van_nangluc()
    assert "Tài khoản AI lượt gần nhất: tài khoản trên console (Claude)" in van
    assert "c2" not in van.split("Tài khoản AI")[1], "/nangluc không được hiện credential_id"


def test_nangluc_chi_hien_ten_chung_khong_email(monkeypatch, bat_console):
    import lenh_cung
    T.ghi_luot({"tu": "console", "provider": "openai", "credential_id": "usr-openai-" +
                EMAIL_GIA, "label": EMAIL_GIA}, "gpt-x", "c", "ok", 1)
    van = lenh_cung._van_nangluc()
    assert "tài khoản trên console (ChatGPT)" in van and EMAIL_GIA not in van
    T.ghi_luot({"tu": "may", "provider": "openai-codex"}, "gpt-x", "c", "loi", 3)
    assert "tài khoản dự phòng trên máy" in lenh_cung._van_nangluc()


def test_ghi_luot_gan_lai_nguyen_object(monkeypatch, bat_console):
    """Luồng khác đang đọc bản cũ thì bản cũ không bị xoá/sửa giữa chừng."""
    T.ghi_luot(_nguon("c1"), "m", "a")
    cu = T._GAN_NHAT
    T.ghi_luot(_nguon("c2"), "m", "b")
    assert cu["credential_id"] == "c1" and T._GAN_NHAT["credential_id"] == "c2"


def test_nangluc_khong_them_dong_khi_co_tat(monkeypatch):
    import lenh_cung
    monkeypatch.setattr(T, "_GAN_NHAT", {"provider": "anthropic", "tu": "console"})
    assert "Tài khoản AI" not in lenh_cung._van_nangluc()


def test_che_loi_truoc_khi_vao_audit():
    s = brain._che(f"HTTP 401 with key {TOKEN_GIA} for {EMAIL_GIA}, Bearer abc.def")
    assert TOKEN_GIA not in s and EMAIL_GIA not in s and "abc.def" not in s
    assert "HTTP 401" in s


def test_mo_ta_runtime_khong_lo_api_key_hay_email(monkeypatch, bat_console):
    _cho_lease(monkeypatch, _lease_openai())
    mo_ta = json.dumps(T.mo_ta_runtime(*T.chon_runtime()), ensure_ascii=False)
    assert ACCESS_GIA not in mo_ta and EMAIL_GIA not in mo_ta
    assert "chatgpt.com" in mo_ta and "console (ChatGPT)" in mo_ta
