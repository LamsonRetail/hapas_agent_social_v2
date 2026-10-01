"""Bộ thử không bao giờ xin lease thật từ platform.

`brain._resolve_agent` mặc định xin tài khoản AI từ console (tai_khoan_ai). Trong bộ
thử, mặc định tắt cờ đó để mọi bài cũ chạy đúng đường cũ, không chạm mạng. Bài nào cần
đường console tự bật lại bằng monkeypatch và giả lease.
"""
import pytest


@pytest.fixture(autouse=True)
def _tat_lease_that(monkeypatch):
    monkeypatch.setenv("MARK_THEO_TAI_KHOAN_CONSOLE", "0")
    try:
        import tai_khoan_ai
        tai_khoan_ai.xoa_cache()
    except BaseException:
        pass
    yield
