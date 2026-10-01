"""Bộ thử không bao giờ xin lease thật từ platform.

`brain._resolve_agent` mặc định xin tài khoản AI từ console (tai_khoan_ai). Trong bộ
thử, mặc định tắt cờ đó để mọi bài cũ chạy đúng đường cũ, không chạm mạng. Bài nào cần
đường console tự bật lại bằng monkeypatch và giả lease.
"""
import pytest


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
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "0")
    try:
        import tai_khoan_ai
        tai_khoan_ai.xoa_cache()
    except BaseException:
        pass
    yield
