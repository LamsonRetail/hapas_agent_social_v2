"""Canh chi phí quét: Mark phải báo số tiền Apify THỰC tính, không phải ước tính.

Lỗi thật đọc ra từ lịch sử run Apify:

  • 23/09 Mark báo "khoảng 0,30 USD" — thực tế 0,83 USD (chỉ có ước tính trước khi chạy)
  • 25/09 hỏi lại chi phí thì Mark không trả lời được: số không nằm trong câu trả lời,
    mà kết quả tool thì không được giữ trong lịch sử
  • 25/09 actor dự phòng TikTok lấy 100 bài CHO MỖI hashtag (5 × 100), cào 333 bài thì
    chạm trần 1 USD và bị cắt ngang
"""
from __future__ import annotations

import datetime

import pytest

import apify_tool as A

TU = datetime.datetime(2026, 9, 25, 9, 27, tzinfo=A._VN_TZ)


class _Resp:
    def __init__(self, items):
        self._items = items

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": {"items": self._items}}


@pytest.fixture
def lich_su(monkeypatch):
    """Giả lịch sử run: một run cũ (phải bỏ qua) và các run của lượt quét này."""
    bang = {
        "apidojo~tiktok-scraper": [
            {"startedAt": "2026-09-25T02:27:01Z", "usageTotalUsd": 0.003, "status": "SUCCEEDED"},
            {"startedAt": "2026-09-23T08:18:40Z", "usageTotalUsd": 0.003, "status": "SUCCEEDED"},
        ],
        "clockworks~tiktok-hashtag-scraper": [
            {"startedAt": "2026-09-25T02:27:39Z", "usageTotalUsd": 0.999, "status": "SUCCEEDED"},
        ],
    }
    goi = []

    def get(url, **kw):
        goi.append(kw)
        return _Resp(bang.get(url.split("/acts/")[1].split("/")[0], []))

    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A.requests, "get", get)
    return goi


def test_cong_dung_run_cua_luot_nay_va_bao_cham_tran(lich_su):
    thuc = A._chi_phi_thuc(
        ["apidojo~tiktok-scraper", "clockworks~tiktok-hashtag-scraper"], TU)
    assert thuc == {"usd": 1.002, "so_run": 2, "cham_tran": 1, "dang_chay": 0}, (
        "run 23/09 bắt đầu trước lượt quét này nên không được cộng")
    dong = A._dong_chi_phi(thuc, 0.3)
    assert "1,00 USD" in dong and "số thực" in dong and "chạm trần" in dong


def test_token_di_qua_header_khong_nam_tren_url(lich_su):
    A._chi_phi_thuc(["apidojo~tiktok-scraper"], TU)
    assert lich_su and all("token" not in (kw.get("params") or {}) for kw in lich_su)
    assert all(kw["headers"]["Authorization"] == "Bearer tok" for kw in lich_su)


def test_khong_hoi_duoc_thi_noi_ro_la_uoc_tinh(monkeypatch):
    def hong(*a, **k):
        raise A.requests.ConnectionError("https://api.apify.com/?token=bi-mat")

    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A.requests, "get", hong)
    assert A._chi_phi_thuc(["apidojo~tiktok-scraper"], TU) is None
    dong = A._dong_chi_phi(None, 0.3)
    assert "chưa lấy được số thực" in dong and "0,30" in dong


def test_khong_tim_thay_run_nao_thi_khong_bao_0_usd():
    """Không thấy run (lệch giờ, API chậm cập nhật) không có nghĩa là miễn phí."""
    dong = A._dong_chi_phi({"usd": 0.0, "so_run": 0, "cham_tran": 0, "dang_chay": 0}, 0.3)
    assert "chưa lấy được số thực" in dong


def test_chi_youtube_thi_mien_phi():
    dong = A._dong_chi_phi({"usd": 0.0, "so_run": 0, "cham_tran": 0, "dang_chay": 0}, 0.0)
    assert "0 USD" in dong


def test_du_phong_tiktok_chia_limit_theo_hashtag(monkeypatch):
    goi = []
    monkeypatch.setattr(A, "_call", lambda actor, payload, limit, mem=None:
                        goi.append((payload, limit)) or [])
    A._fetch_tiktok_fallback(["xuhuong", "trend", "viral", "fyp", "tiktokvn"], 100)
    payload, _ = goi[0]
    assert payload["resultsPerPage"] == 20, (
        "resultsPerPage tính cho TỪNG hashtag: để 100 thì 5 hashtag đòi 500 video")


def test_mo_ta_tool_bat_buoc_dong_chi_phi():
    assert "chép NGUYÊN VĂN `chi_phi`" in A.SCHEMA["description"]
