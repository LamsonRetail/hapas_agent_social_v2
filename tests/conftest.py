"""Bộ thử không bao giờ xin lease thật từ platform.

`brain._resolve_agent` mặc định xin tài khoản AI từ console (tai_khoan_ai). Trong bộ
thử, mặc định tắt cờ đó để mọi bài cũ chạy đúng đường cũ, không chạm mạng. Bài nào cần
đường console tự bật lại bằng monkeypatch và giả lease.

Cấu hình console (Năng lực → trần quét, công tắc) cũng KHÔNG đọc thật. Ngày 02/10/2026
chủ agent đặt trần TikTok 50 bài và tắt Facebook trên console: 34 bài đỏ vì bộ chạy nạp
`.env` gốc (có khoá platform) nên `lsr_policy.cau_hinh_tool` đọc số sống — bài đặt trần
chung vẫn bị trần riêng từng nền tảng đè. Nay mặc định là cấu hình rỗng cố định, và mọi
kết nối mạng ra ngoài máy bị chặn. Bài nào cần cấu hình riêng thì tự monkeypatch
`cau_hinh_tool` / giả `urlopen` như trước; cần mạng thật thì đặt MARK_TEST_CHO_MANG=1.
"""
import math
import os
import socket

import pytest

# Bí mật Meta Ads không bao giờ vào bộ thử: chặn `config` nạp chúng từ `.env` thật (biến
# này phải đặt TRƯỚC khi module nào import config) và gỡ bản đang có trong môi trường
# shell, trước khi `meta_ads_tool` kịp giữ token vào bộ nhớ module.
os.environ["MARK_DOTENV_BO_QUA"] = "MARK_META_"
for _k in [k for k in os.environ if k.startswith("MARK_META_")]:
    os.environ.pop(_k, None)

#: Biến khiến runtime gọi platform (lease, stamp, danh bạ Năng lực, trace, job).
_BIEN_PLATFORM = ("LSR_TELEMETRY_API_KEY", "LSR_COLLECTOR", "LSR_PLATFORM_URL",
                  "LSR_PLATFORM_TOKEN", "LSR_PLATFORM_ADMIN_TOKEN",
                  # Phoenix: không bài nào tự xuất trace (phoenix_trace đọc lại env mỗi lượt).
                  "PHOENIX_COLLECTOR_ENDPOINT", "PHOENIX_API_KEY", "MARK_PHOENIX_SALT",
                  "MARK_PHOENIX_CONTENT", "MARK_PHOENIX_LLM_INPUT")
_DIA_CHI_MAY = {"localhost", "127.0.0.1", "::1", None}
_goc_getaddrinfo = socket.getaddrinfo


def _getaddrinfo_chan(host, *a, **k):
    h = host.decode() if isinstance(host, bytes) else host
    if h not in _DIA_CHI_MAY:
        # gaierror: thư viện nào cũng hiểu là "mất mạng" và đi đường lỗi của nó.
        raise socket.gaierror(socket.EAI_NONAME,
                              f"bộ thử chặn mạng ra ngoài ({h}) — MARK_TEST_CHO_MANG=1 để mở")
    return _goc_getaddrinfo(host, *a, **k)


@pytest.fixture(autouse=True)
def _khong_cham_console_that(monkeypatch):
    """Không bài nào đọc console/platform sống, trừ khi tự chọn."""
    for ten in _BIEN_PLATFORM:
        monkeypatch.delenv(ten, raising=False)
    for ten in [k for k in os.environ if k.startswith("MARK_META_")]:
        monkeypatch.delenv(ten, raising=False)
    try:
        import lsr_policy
        # Bản nhớ MỚI cho mỗi bài: không mang trần/công tắc của bài trước hay của console.
        # `luc=inf` = luôn còn hạn → không bao giờ tự đi hỏi; bài nào ép làm mới
        # (`_nho_nl.update(bat=None, luc=0.0)`) thì đọc qua `urlopen` nó tự giả.
        monkeypatch.setattr(lsr_policy, "_nho_nl", {
            "bat": lsr_policy.KHONG_THU_HEP, "luc": math.inf, "nguon": "bộ thử",
            "cau_hinh": {}})
        monkeypatch.setattr(lsr_policy, "_nho", {"quyen": None, "luc": 0.0,
                                                 "nguon": "chưa hỏi"})
    except BaseException:
        pass
    if os.environ.get("MARK_TEST_CHO_MANG", "").strip() != "1":
        monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo_chan)
    yield


@pytest.fixture(autouse=True)
def _tat_lease_that(monkeypatch, tmp_path):
    monkeypatch.setenv("MARK_THEO_TAI_KHOAN_CONSOLE", "0")
    # Việc nền (viec_nen.py): sổ việc + bộ đếm YouTube vào thư mục tạm, không bao giờ tự
    # dựng luồng điều phối — bài nào cần thì gọi thẳng `viec_nen.chay_ngay`.
    monkeypatch.setenv("SOCIAL_NEN_THU_MUC", str(tmp_path / "viec-nen"))
    monkeypatch.setenv("SOCIAL_NEN_TU_CHAY", "0")
    # Bài cũ của social_listen/deep_dive canh đường TẠI CHỖ: mặc định tắt chạy nền (lượt
    # ≤600 bài/nền tảng không đổi gì). Bài của việc nền tự bật lại SOCIAL_QUET_NEN=1.
    monkeypatch.setenv("SOCIAL_QUET_NEN", "0")
    # social_listen: không hỏi hạn mức Apify thật (GET /users/me…) và không gọi model
    # thật để phân xử bài — bài cần thì tự bật lại và giả `requests.get` / `_hoi_model`.
    monkeypatch.setenv("APIFY_KIEM_TRUOC", "0")
    # social_deep_dive: YouTube đi YouTube Data API khi có key (bộ chạy nạp `.env` gốc có
    # key thật). Bài cũ canh đường actor Apify → mặc định KHÔNG có key; bài API tự đặt key
    # giả và giả `requests.get`.
    monkeypatch.delenv("YOUTUBE_DATA_API_KEY", raising=False)
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "0")
    try:
        import tai_khoan_ai
        tai_khoan_ai.xoa_cache()
    except BaseException:
        pass
    # Audit + sổ chi phí: KHÔNG BAO GIỜ ghi vào .audit/ thật hay đẩy lên Base production.
    # Lần quét chạy ngoài lượt bot từng để lại dòng trống Turn ID trong "Chi phí quét"
    # (25–28/09/2026). Bài nào cần thử đường Base thì tự monkeypatch `lark.call`.
    try:
        import audit
        import chi_phi_tool
        monkeypatch.setattr(audit, "_THU_MUC", tmp_path / ".audit")
        monkeypatch.setattr(audit, "_DAY_LEN_BASE", False)
        monkeypatch.setattr(audit, "_CAU_HINH", tmp_path / "audit_base.json")
        monkeypatch.setattr(chi_phi_tool, "_CAU_HINH", tmp_path / "chi_phi_quet_base.json")
        monkeypatch.setattr(chi_phi_tool, "_SO", tmp_path / ".audit" / "chi-phi" / "so.jsonl")
    except BaseException:
        pass
    yield
