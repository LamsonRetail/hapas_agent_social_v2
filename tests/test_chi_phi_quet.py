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
from test_binh_luan_phan_tich import moi_truong  # noqa: F401

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
    # Ghim trần 1 USD: không ghim thì test đọc trần THẬT trên console qua mạng.
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    monkeypatch.setattr(A.time, "sleep", lambda s: None)   # lần đọc xác nhận, khỏi chờ thật
    return goi


def test_cong_dung_run_cua_luot_nay_va_bao_cham_tran(lich_su):
    thuc = A._chi_phi_thuc(
        ["apidojo~tiktok-scraper", "clockworks~tiktok-hashtag-scraper"], TU)
    assert thuc == {"usd": 1.002, "so_run": 2, "cham_tran": 1, "dang_chay": 0,
                    "on_dinh": True}, (
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
    monkeypatch.setattr(A.time, "sleep", lambda s: None)   # hỏi lại 2 lần, khỏi chờ thật
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


def _quet_gia(monkeypatch, so_bai: int, limit: int):
    """Chạy `_handle` với nguồn TikTok giả trả `so_bai` bài và lịch sử run chạm trần."""
    import apify_tool
    now = datetime.datetime.now(A._VN_TZ)
    bai = [({"kenh": "k", "followers": 0, "views": 0, "likes": 0, "comments": 0,
             "shares": 0, "hashtags": "", "text": "", "link": f"https://t/{i}"},
            now - datetime.timedelta(days=30)) for i in range(so_bai)]
    monkeypatch.setitem(apify_tool._FETCH, "tiktok", lambda *a: bai)
    monkeypatch.setattr(apify_tool, "_tran", lambda: (1000, 2.4))
    monkeypatch.setattr(apify_tool, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 2.403, "so_run": 2, "cham_tran": 1, "dang_chay": 0})
    ghi = []
    monkeypatch.setattr(apify_tool.chi_phi_tool, "ghi", lambda **k: ghi.append(k) or {})
    kq = json.loads(apify_tool._handle({
        "queries": ["trend"], "platforms": ["tiktok"], "limit": limit,
        "date_from": f"{now:%Y-%m-%d}", "date_to": f"{now:%Y-%m-%d}"}))
    return kq, ghi[0]["thuc"]


def test_lay_du_limit_thi_khong_bao_cham_tran(monkeypatch):
    """Trần 2,4 USD cho 800 bài: lấy đủ 800 cũng tiêu đúng 2,4 USD, không bị cắt gì."""
    kq, thuc = _quet_gia(monkeypatch, 800, 800)
    assert kq["cham_tran_chi_phi"] is False and thuc["cham_tran"] == 0


def test_thieu_bai_va_tieu_sat_tran_thi_van_bao(monkeypatch):
    kq, thuc = _quet_gia(monkeypatch, 333, 800)
    assert kq["cham_tran_chi_phi"] is True and thuc["cham_tran"] == 1


def test_hoi_chi_phi_loi_thoang_qua_thi_hoi_lai(monkeypatch):
    """Đo 25/09: một lần gọi Apify lỗi là sổ ghi 'chưa lấy được số thực' dù run đã xong."""
    lan = []

    def get(url, **kw):
        lan.append(1)
        if len(lan) == 1:
            raise A.requests.ConnectionError("lỗi thoáng qua")
        return _Resp([{"startedAt": "2026-09-25T02:27:39Z", "usageTotalUsd": 0.0035,
                       "status": "SUCCEEDED"}])

    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A, "_tran", lambda: (100, 0.3))
    monkeypatch.setattr(A.time, "sleep", lambda s: None)
    monkeypatch.setattr(A.requests, "get", get)
    thuc = A._chi_phi_thuc(["pro100chok~tiktok-shop-scraper-usage"], TU, 0.0035)
    assert thuc and thuc["usd"] == 0.004 and thuc["so_run"] == 1


# ───────── B7 (E2E 04-05/10/2026): sổ ghi 0,143 USD, Apify tính thật 0,193 ─────────
def _apify_theo_lan(monkeypatch, cac_lan):
    """`requests.get` giả: lần đọc thứ i trả (trạng thái, usd) = cac_lan[min(i, cuối)]."""
    lan, ngu = [], []

    def get(url, **kw):
        st, usd = cac_lan[min(len(lan), len(cac_lan) - 1)]
        lan.append(1)
        return _Resp([{"startedAt": "2026-09-25T02:27:39Z", "usageTotalUsd": usd,
                       "status": st}])

    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    monkeypatch.setattr(A.time, "sleep", lambda s: ngu.append(s))
    monkeypatch.setattr(A.requests, "get", get)
    return lan, ngu


def test_hoi_lai_toi_khi_so_on_dinh_khong_dung_o_nua_uoc_tinh(monkeypatch):
    """Bản cũ: số đầu 0,143 ≥ 50% ước tính 0,2 là thôi hỏi -> sổ ghi thiếu 0,05 USD."""
    lan, _ = _apify_theo_lan(monkeypatch, [("SUCCEEDED", 0.143), ("SUCCEEDED", 0.193)])
    thuc = A._chi_phi_thuc(["apify~facebook-comments-scraper"], TU, 0.2)
    assert thuc["usd"] == 0.193 and thuc["on_dinh"] is True
    assert len(lan) == 3, "đọc tới khi hai lần liền nhau khớp nhau"


def test_run_con_chay_thi_cho_co_gioi_han_va_bao_chua_on_dinh(monkeypatch):
    lan, ngu = _apify_theo_lan(monkeypatch, [("RUNNING", 0.05)])
    thuc = A._chi_phi_thuc(["x~y"], TU)
    assert len(lan) == 1 + A._CP_LAN_TOI_DA and sum(ngu) <= 20, "chờ có trần"
    assert thuc["dang_chay"] == 1 and thuc["on_dinh"] is False
    assert "vẫn đang chạy" in A._dong_chi_phi(thuc, 0.1)


def test_khong_cho_qua_han_chot_cua_ben_goi(monkeypatch):
    lan, ngu = _apify_theo_lan(monkeypatch, [("SUCCEEDED", 0.1), ("SUCCEEDED", 0.2)])
    thuc = A._chi_phi_thuc(["x~y"], TU, 0.1, han=A.time.monotonic() + 1.0)
    assert ngu == [] and len(lan) == 1, "không bắt đầu lần chờ nào vượt hạn"
    assert thuc["usd"] == 0.1 and thuc["on_dinh"] is False


def test_so_thap_hon_nua_uoc_tinh_thi_hoi_them_du_da_khop(monkeypatch):
    """Apify có thể đứng ở phí khởi động vài giây rồi mới cộng tiền theo dòng."""
    lan, _ = _apify_theo_lan(monkeypatch, [("SUCCEEDED", 0.02), ("SUCCEEDED", 0.02),
                                           ("SUCCEEDED", 0.07)])
    thuc = A._chi_phi_thuc(["x~y"], TU, 0.08)
    assert thuc["usd"] == 0.07 and thuc["on_dinh"] is True


def test_deep_dive_dua_han_chot_cho_viec_hoi_tien(moi_truong, monkeypatch):  # noqa: F811
    """Chờ số ổn định không được vượt `f_cp.result(timeout=…)`, kẻo mất luôn số đã đọc."""
    import json
    import deep_dive_tool as D
    from test_binh_luan_phan_tich import TT, _bl
    ap = moi_truong[0]
    ap.tra = lambda payload, limit: [_bl(TT.format(7000001), "đẹp")]
    han = []
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda actors, tu, est=0.0, h=None, **k: (
        han.append(h) or {"usd": 0.2, "so_run": 1, "cham_tran": 0, "dang_chay": 0}))
    t = A.time.monotonic()
    kq = json.loads(D._handle({"post_urls": [TT.format(7000001)]}))
    assert kq["chi_phi_thuc_usd"] == 0.2
    assert han and t < han[0] <= t + A._TOOL_DEADLINE - 9
