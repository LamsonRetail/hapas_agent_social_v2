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
import json

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


def test_khong_tu_noi_chi_phi_chi_tra_loi_khi_hoi():
    """Chủ agent 25/09: chi phí ghi vào Base audit, ai hỏi mới trả lời."""
    mo_ta = A.SCHEMA["description"]
    assert "KHÔNG tự nói ra" in mo_ta and "tra_chi_phi_quet" in mo_ta
    assert "LUÔN kết thúc" not in mo_ta


# ─────────────────────────── sổ chi phí (chi_phi_tool) ───────────────────────────

@pytest.fixture
def so(monkeypatch, tmp_path):
    import audit
    import chi_phi_tool as C
    monkeypatch.setattr(C, "_SO", tmp_path / "chi-phi-quet.jsonl")
    monkeypatch.setattr(audit, "_DAY_LEN_BASE", False)
    monkeypatch.setattr(audit, "_BAT", True)

    def vao_luot(chat):
        tid = audit.bat_dau(chat, "ou_1", "quét hapas")
        return tid

    return C, audit, vao_luot


def test_ghi_so_gan_dung_chat_va_turn_cua_luot_dang_chay(so):
    C, audit, vao_luot = so
    tid = vao_luot("oc_nhom")
    rec = C.ghi(queries=["hapas"], platforms=["tiktok"], date_range="21→25",
                thuc={"usd": 1.002, "so_run": 2, "cham_tran": 1, "dang_chay": 0}, est=0.3)
    audit._dang_chay.pop(tid, None)
    assert rec["chat"] == "oc_nhom" and rec["turn_id"] == tid and rec["nguoi"] == "ou_1"
    assert rec["chi_phi_thuc_usd"] == 1.002 and rec["cham_tran"] is True
    f = C._fields({**rec, "nguoi": ""})
    assert f["Chi phí thực USD"] == 1.002 and f["Chạm trần"] == "có"
    assert f["Nguồn số"] == "Apify (thực)" and f["Turn ID"] == tid
    assert set(f) == {ten for ten, _ in C._COT}, "field lệch cột là mất nguyên dòng Base"


def test_khong_co_so_thuc_thi_ghi_la_uoc_tinh(so):
    C, _, _ = so
    rec = C.ghi(queries=["x"], platforms=["tiktok"], date_range="", thuc=None, est=0.3,
                chat="oc_a")
    assert rec["chi_phi_thuc_usd"] is None
    assert C._fields(rec)["Nguồn số"].startswith("ước tính")


def test_tra_chi_phi_chi_thay_chat_cua_minh(so):
    C, audit, vao_luot = so
    for chat, usd in (("oc_a", 0.3), ("oc_b", 0.9), ("oc_a", 1.0)):
        C.ghi(queries=["q"], platforms=["tiktok"], date_range="", est=0.3, chat=chat,
              thuc={"usd": usd, "so_run": 1, "cham_tran": 0, "dang_chay": 0})
    tid = vao_luot("oc_a")
    kq = json.loads(C._handle({"so_luot": 5}))
    audit._dang_chay.pop(tid, None)
    assert kq["so_lan_quet"] == 2
    assert [x["chi_phi_thuc_usd"] for x in kq["cac_lan_quet"]] == [1.0, 0.3], "mới nhất trước"
    assert kq["tong_chi_phi_thuc_usd"] == 1.3


def test_so_khong_nam_ngang_hang_so_audit():
    """Hồi quy/kiểm toán lấy `sorted(.audit/*.jsonl)[-1]` làm sổ audit."""
    import audit
    import chi_phi_tool as C
    assert C._SO.parent != audit._THU_MUC and C._SO.parent.parent == audit._THU_MUC


def test_tool_tra_cuu_duoc_policy_cho_phep():
    import lsr_policy
    assert "tra_chi_phi_quet" in lsr_policy._SAFE_EXACT
