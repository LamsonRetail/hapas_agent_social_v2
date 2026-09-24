"""Canh phần hội thoại: biết ai đang nói, nhóm hay chat riêng, ảnh, và lỗi model.

Mọi mục ở đây là một lỗi THẬT đọc ra từ sổ audit ngày 25/09:

  • 54/70 lượt Lark có `nguoi` trống — Mark không biết ai đang nói với mình
  • Tên Lark kèm chức danh ("A - CMO") làm cả chủ agent lẫn sếp bị xếp "ngoài team"
  • Người gửi ảnh nhận "chưa đọc được ảnh từ hệ thống" — thật ra tool bị chặn quyền
  • Người dùng nhận nguyên văn "API call failed … HTTP 429" làm câu trả lời
"""
from __future__ import annotations

import json

import pytest

import brain
import lsr_platform as P
import lsr_policy


# ─────────────────────────────── ai đang nói ───────────────────────────────

def test_job_lark_lay_duoc_nguoi_gui_tu_sender_open_id():
    """Job Lark mang người gửi ở `sender_open_id`; chỉ job console mới có `user_ref`."""
    assert P._lark_sender_ref({"text": "hi", "sender_open_id": "ou_abc"}) == "ou_abc"


def test_job_console_van_nhu_cu():
    assert P._lark_sender_ref({"user_ref": "ou_xyz"}) == "ou_xyz"
    assert P._lark_sender_ref({"user_ref": "a@hapas.vn"}) is None, (
        "email vào sender_open_id làm brain gọi Contact API sai và sinh lỗi 400")


@pytest.fixture
def ten_gia(monkeypatch):
    bang = {"ou_1": "Nguyễn Tiến Thẩm - AI Automation Intern",
            "ou_2": "Lê Quý Thiện - Technical & AI Automation Leader",
            "ou_3": "Đinh Công Tài - CMO",
            "ou_4": "Trần Văn Nam - Booking KOL"}
    monkeypatch.setattr(brain.lark, "resolve_user_name", lambda oid: bang.get(oid))
    brain._TEN_DA_TRA.clear()
    return bang


def test_chuc_danh_khong_lam_nguoi_trong_team_thanh_nguoi_ngoai(ten_gia):
    assert "Thành viên team" in brain._classify_sender("ou_1")[1]
    assert "SẾP TRỰC TIẾP" in brain._classify_sender("ou_2")[1]


def test_lanh_dao_nhan_ra_tu_chuc_danh(ten_gia):
    assert "Lãnh đạo" in brain._classify_sender("ou_3")[1]


def test_nguoi_ngoai_team_KHONG_bi_dan_giau_thong_tin(ten_gia):
    """Họ là người dùng chính của Mark (booking KOL/KOC, marketing). Bản cũ dặn 'KHÔNG
    tiết lộ thông tin nội bộ' — tức giấu nghiên cứu thị trường với đúng người cần nó."""
    vai = brain._classify_sender("ou_4")[1]
    assert "KHÔNG tiết lộ thông tin nội bộ" not in vai
    assert "người dùng chính" in vai


# ─────────────────────────────── nhóm hay chat riêng ────────────────────────

def test_kenh_doc_tu_reply_to():
    assert P._kenh_cua_job({"reply_to": {"chat_type": "group"}}) == {"chat_type": "group"}
    assert P._kenh_cua_job({"reply_to": {"chat_type": "p2p"}}) == {"chat_type": "p2p"}
    assert P._kenh_cua_job({"reply_to": {}}) is None
    assert P._kenh_cua_job({}) is None


def test_khong_co_kenh_thi_tra_loi_goi_y_nhu_cu():
    """`tra_loi` giả của các bộ thử không nhận `kenh` — không có kênh thì không truyền."""
    def tra_loi(text, chat_id=None, sender_open_id=None):
        return "ok"
    dap, ok, treo = P._chay_co_han(tra_loi, "hi", "s", None)
    assert (dap, ok, treo) == ("ok", True, False)


def test_co_kenh_thi_truyen_xuong():
    bat = {}

    def tra_loi(text, chat_id=None, sender_open_id=None, kenh=None):
        bat["kenh"] = kenh
        return "ok"
    P._chay_co_han(tra_loi, "hi", "s", "ou_1", {"chat_type": "group"})
    assert bat["kenh"] == {"chat_type": "group"}


def test_trong_nhom_tag_nguoi_hoi_bang_ma():
    """Tag bằng mã: platform tag THẲNG. Tag bằng tên phải khớp gần đúng và có thể trượt."""
    k = brain._khoi_kenh({"chat_type": "group"}, "ou_1", "Thẩm")
    assert "{{@ou_1}}" in k
    assert "GỌN" in k
    assert "Ghi chú dài hạn" in k, "không dặn giữ kín ghi chú riêng trước cả nhóm"


def test_trong_nhom_khong_biet_nguoi_hoi_thi_khong_bia_the_tag():
    assert "{{@" not in brain._khoi_kenh({"chat_type": "group"}, None, "(chưa rõ tên)")


def test_chat_rieng_va_console():
    assert "CHAT RIÊNG" in brain._khoi_kenh({"chat_type": "p2p"}, "ou_1", "Thẩm")
    assert brain._khoi_kenh(None, "ou_1", "Thẩm") == ""


def test_lich_su_nhom_gan_ten_nguoi_noi(ten_gia):
    hist = [{"role": "user", "text": "quét HAPAS", "sender": "ou_1"},
            {"role": "assistant", "text": "xong"},
            {"role": "user", "text": "còn Vascara?", "sender": "ou_3"}]
    nhom = brain._lich_su(hist, True)
    assert nhom[0]["content"] == "[Nguyễn Tiến Thẩm] quét HAPAS"
    assert nhom[2]["content"] == "[Đinh Công Tài] còn Vascara?"
    assert nhom[1]["content"] == "xong", "không gắn tên cho lượt của chính Mark"
    rieng = brain._lich_su(hist, False)
    assert rieng[0]["content"] == "quét HAPAS", "chat riêng không cần gắn tên"


# ─────────────────────────────── ảnh ───────────────────────────────────────

def test_tin_chi_co_anh_khong_dua_json_tho_cho_model():
    j = {"payload": {"message_type": "image", "image_key": "img_v3_x", "message_id": "om_1"}}
    hoi = P._cau_hoi_kem_anh('{"image_key":"img_v3_x"}', j, ["D:/x/.dinh_kem/om_1.jpg"])
    assert "image_key" not in hoi
    assert "[Ảnh đính kèm: D:/x/.dinh_kem/om_1.jpg]" in hoi


def test_co_anh_ma_khong_tai_duoc_thi_noi_that():
    j = {"payload": {"message_type": "image", "image_key": "img_v3_x"}}
    assert "không tải được" in P._cau_hoi_kem_anh("", j, [])


def test_tai_anh_ghi_vao_thu_muc_dinh_kem(tmp_path, monkeypatch):
    monkeypatch.setattr(lsr_policy, "THU_MUC_DINH_KEM", tmp_path)

    class R:
        headers = {"Content-Type": "image/png"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1): return b"\x89PNG" + b"0" * 10

    monkeypatch.setattr(P.urllib.request, "urlopen", lambda req, timeout=0: R())
    c = {"platform": "https://p", "key": "k", "url": "u", "agent_id": "A"}
    ra = P._tai_anh(c, {"payload": {"message_id": "om/../1", "image_key": "img_v3_x"},
                        "reply_to": {"app_id": "cli_1"}})
    assert len(ra) == 1 and ra[0].endswith(".png")
    assert ".." not in ra[0].split("\\")[-1].split("/")[-1], "tên file lấy nguyên từ dữ liệu ngoài"
    assert lsr_policy.decide("vision_analyze", {"image_url": ra[0]}).allowed


def test_vision_chi_doc_anh_dinh_kem_hoac_web():
    goc = lsr_policy.THU_MUC_DINH_KEM
    assert lsr_policy.decide("vision_analyze", {"image_url": str(goc / "a.jpg")}).allowed
    assert lsr_policy.decide("vision_analyze", {"image_url": "https://x/a.png"}).allowed
    assert not lsr_policy.decide("vision_analyze", {"image_url": "C:/Users/PC/a.png"}).allowed
    assert not lsr_policy.decide("vision_analyze",
                                 {"image_url": str(goc / ".." / ".env")}).allowed, \
        "thoát khỏi thư mục đính kèm bằng '..'"


# ─────────────────────────────── prompt không quảng cáo tool bị chặn ─────────

def test_prompt_khong_quang_cao_tool_bi_chan():
    """Prompt từng ghi 'đọc/ghi/sửa/tìm FILE, chạy CODE Python, giao việc cho subagent'
    trong khi lsr_policy chặn cả ba. Model tin prompt, gọi, rồi ăn từ chối giữa lượt."""
    for chan in ("execute_code", "read_file", "delegate_task"):
        assert not lsr_policy.decide(chan, {}).allowed, f"{chan} không còn bị chặn — xem lại"
    assert "chạy CODE Python, giao việc cho subagent" not in brain._TOOLING_NOTE
    assert "KHÔNG có quyền đọc/ghi file" in brain._TOOLING_NOTE


def test_model_khong_thay_tool_bi_chan():
    try:
        a = brain._resolve_agent(None, None)
    except Exception as e:                      # không có tài khoản model ở máy này
        pytest.skip(f"không dựng được agent: {type(e).__name__}")
    ts = getattr(a, "tools", None) or []
    ten = {(t.get("function") or t).get("name") for t in ts if isinstance(t, dict)}
    assert ten, "không đọc được danh sách tool của agent"
    assert not ten & {"execute_code", "read_file", "write_file", "delegate_task"}
    assert "vision_analyze" in ten


# ─────────────────────────────── lỗi model ─────────────────────────────────

def test_nhan_ra_loi_het_han_muc():
    t = "API call failed after 3 retries: HTTP 429: The usage limit has been reached"
    cau = brain._loi_mo_hinh(t, {"failed": True})
    assert cau and "HTTP 429" not in cau and "chưa được thực hiện" in cau


def test_luot_binh_thuong_khong_bi_coi_la_loi():
    assert brain._loi_mo_hinh("Đã quét xong 24 bài.", {}) is None


def test_luot_model_hong_KHONG_ghi_vao_lich_su(monkeypatch):
    """Bài quan trọng nhất của mục này. Câu lỗi lọt vào lịch sử thì lượt sau model đọc
    thấy chính mình 'đã nói' câu lỗi, và ngữ cảnh bẩn dần theo mỗi lần hỏng."""
    ghi = []

    class AgentGia:
        def run_conversation(self, *a, **k):
            return {"final_response": "API call failed after 3 retries: HTTP 429: The "
                                      "usage limit has been reached", "failed": True}

    monkeypatch.setattr(brain, "_resolve_agent", lambda *a, **k: AgentGia())
    monkeypatch.setattr(brain.lsr_platform, "lay_ngu_canh", lambda *a, **k: {})
    monkeypatch.setattr(brain.lsr_platform, "ghi_luot_ngu_canh",
                        lambda *a, **k: ghi.append("platform"))
    monkeypatch.setattr(brain.memory_store, "load_history", lambda cid: [])
    monkeypatch.setattr(brain.memory_store, "append_turns", lambda *a, **k: ghi.append("local"))
    monkeypatch.setattr(brain.audit, "bat_dau", lambda *a, **k: "t")
    monkeypatch.setattr(brain.audit, "ket_thuc", lambda *a, **k: {})
    dap = brain.reply("quét HAPAS tuần này", chat_id="lark:a:oc_1", sender_open_id=None)
    assert "HTTP 429" not in dap, "gửi nguyên văn lỗi cho người dùng"
    assert ghi == [], f"lượt hỏng vẫn bị ghi vào lịch sử: {ghi}"
