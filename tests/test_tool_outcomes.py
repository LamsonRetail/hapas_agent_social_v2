import contextvars
import json

import audit
import execution_receipts as receipts
import lsr_policy
import tiktok_ads_tool as top_ads
from tools.registry import tool_error


def _mot_luot(monkeypatch, ket_qua):
    monkeypatch.setattr(audit, "_BAT", True)
    monkeypatch.setattr(audit, "_DAY_LEN_BASE", False)
    monkeypatch.setattr(audit, "_ghi", lambda rec: None)

    def chay():
        tid = audit.bat_dau("console:test", "tester@example.com", "test")
        audit.ghi_tool("tool_test", {}, ket_qua, 0.1)
        return audit.ket_thuc(tid, "xong")

    return contextvars.Context().run(chay)


def test_audit_json_permission_denied_la_blocked(monkeypatch):
    rec = _mot_luot(monkeypatch, json.dumps({
        "error": "permission_denied",
        "message": "khong co quyen",
    }))
    tool = rec["tool"][0]
    assert tool["trang_thai"] == "blocked"
    assert tool["ma_loi"] == "permission_denied"
    assert tool["co_ket_qua"] is False
    assert rec["trang_thai_tool"] == "blocked"
    assert rec["trang_thai"] == "blocked"


def test_policy_denied_truoc_handler_tao_blocked_receipt_va_chan_success_cu(
        monkeypatch, tmp_path):
    """Dispatch chặn trước handler vẫn phải thành receipt mới nhất của chính tool."""
    from tools import registry as registry_module
    import dong_ho_luot

    class Registry:
        def dispatch(self, name, args, **kwargs):
            raise AssertionError("policy denied không được chạm handler")

    reg = Registry()
    monkeypatch.setattr(registry_module, "registry", reg)
    monkeypatch.setattr(receipts, "_DIR", tmp_path / "receipts")
    monkeypatch.setenv("LSR_POLICY_MODE", "enforce")
    monkeypatch.setattr(lsr_policy, "decide",
                        lambda name, args: lsr_policy.PolicyDecision(False, "thiếu quyền"))
    monkeypatch.setattr(dong_ho_luot, "xet", lambda: ("", 0.0))
    # Chứng minh hook nằm trước `_BAT`: tắt audit vẫn không được mất receipt denial.
    monkeypatch.setattr(audit, "_BAT", False)

    receipts.record("chat-policy", "turn-ok", "tiktok_top_ads", {}, {
        "success": True, "so_ads_xin": 20, "actual_count": 5,
    })
    receipts.set_current_turn("chat-policy", "turn-denied")
    try:
        assert lsr_policy.install_registry_guard(audit.ghi_tool)
        denied = json.loads(reg.dispatch("tiktok_top_ads", {"so_ads": 20}))
    finally:
        receipts.clear_current_turn()

    assert denied["error"] == "policy_denied"
    rows = receipts.load("chat-policy")
    assert [row["status"] for row in rows] == ["partial", "blocked"]
    original = "Tôi không hề chạy TikTok vì lượt này bị chặn."
    assert receipts.ground_final_answer(
        "chat-policy", "TikTok đã chạy chưa?", original) == (original, False)


def test_policy_observe_khong_tao_blocked_receipt_gia(monkeypatch):
    got = []
    monkeypatch.setenv("LSR_POLICY_MODE", "observe")
    monkeypatch.setattr(receipts, "record_current", lambda *a, **k: got.append((a, k)))
    monkeypatch.setattr(audit, "_BAT", False)
    audit.ghi_tool("tiktok_top_ads", {}, None, 0.0, loi="policy: quan sát")
    assert got == []


def test_deadline_chan_truoc_handler_van_ghi_receipt(monkeypatch):
    got = []
    monkeypatch.setattr(receipts, "record_current",
                        lambda *a, **k: got.append((a, k)) or {"status": "blocked"})
    monkeypatch.setattr(audit, "_BAT", False)
    audit.ghi_tool("social_listen", {"limit": 20}, None, 0.0,
                   loi="hết giờ lượt (180s)")
    assert len(got) == 1
    assert got[0][0][0] == "social_listen"
    assert got[0][1]["error"].startswith("hết giờ lượt")


def test_audit_hieu_dung_envelope_tool_error_thuc_te(monkeypatch):
    rec = _mot_luot(monkeypatch, tool_error("Không xác định được người hỏi trên Console."))
    tool = rec["tool"][0]
    assert tool["trang_thai"] == "blocked"
    assert tool["co_ket_qua"] is False
    assert "Không xác định" in tool["loi"]


def test_audit_success_5_tren_20_la_partial_va_dem_dung(monkeypatch):
    rec = _mot_luot(monkeypatch, {
        "success": True,
        "so_ads_xin": 20,
        "tom_tat": {"so_ads": 5},
        "top": [{"id": str(i)} for i in range(5)],
    })
    tool = rec["tool"][0]
    assert tool["trang_thai"] == "partial"
    assert tool["so_ket_qua"] == 5
    assert tool["co_ket_qua"] is True
    assert rec["trang_thai_tool"] == "partial"


def test_audit_success_du_so_luong_la_completed(monkeypatch):
    rec = _mot_luot(monkeypatch, {
        "success": True,
        "requested_count": 2,
        "actual_count": 2,
        "items": [{"id": "1"}, {"id": "2"}],
    })
    assert rec["tool"][0]["trang_thai"] == "completed"
    assert rec["trang_thai"] == "ok", "giữ tương thích trạng thái lượt thành công"


def test_audit_none_khong_duoc_coi_la_completed():
    outcome = audit.phan_loai_ket_qua_tool(None)
    assert outcome["trang_thai"] == "failed"
    assert outcome["ma_loi"] == "empty_result"
    assert outcome["co_ket_qua"] is False


def test_audit_fallback_thanh_con_giu_loi_nguon_nhung_luot_la_partial(monkeypatch):
    monkeypatch.setattr(audit, "_BAT", True)
    monkeypatch.setattr(audit, "_DAY_LEN_BASE", False)
    monkeypatch.setattr(audit, "_ghi", lambda rec: None)

    def chay():
        tid = audit.bat_dau("console:test", "tester@example.com", "test fallback")
        audit.ghi_tool("nguon_chinh", {}, {"error": "upstream_failed"}, 0.1)
        audit.ghi_tool("nguon_du_phong", {}, {"success": True, "items": [{"id": 1}]}, 0.1)
        return audit.ket_thuc(tid, "đã lấy từ nguồn dự phòng")

    rec = contextvars.Context().run(chay)
    assert rec["trang_thai_tool"] == "partial"
    assert rec["trang_thai_tool_te_nhat"] == "failed"
    assert rec["trang_thai"] == "partial"


def test_audit_ghi_model_provider_thuc_te_va_chat_luong(monkeypatch):
    monkeypatch.setattr(audit, "_BAT", True)
    monkeypatch.setattr(audit, "_DAY_LEN_BASE", False)
    monkeypatch.setattr(audit, "_ghi", lambda rec: None)

    class Agent:
        model = "gpt-runtime"
        provider_name = "provider-runtime"

    def chay():
        tid = audit.bat_dau("console:test", "tester@example.com", "đã chạy chưa")
        audit.ghi_chat_luong("corrected", "đối chiếu receipt", "turn-goc")
        return audit.ket_thuc(tid, "đã sửa theo bằng chứng", agent=Agent())

    rec = contextvars.Context().run(chay)
    assert rec["model_thuc_te"] == "gpt-runtime"
    assert rec["provider_thuc_te"] == "provider-runtime"
    assert rec["chat_luong"] == {
        "trang_thai": "corrected", "ly_do": "đối chiếu receipt",
        "evidence_turn_id": "turn-goc",
    }


def test_audit_model_provider_thieu_thi_ghi_unknown(monkeypatch):
    rec = _mot_luot(monkeypatch, {"success": True})
    assert rec["model_thuc_te"] == "unknown"
    assert rec["provider_thuc_te"] == "unknown"


def test_paid_quota_khong_bi_goi_la_free():
    ly_do = top_ads._phan_loai_gioi_han(
        "Quota exceeded for a paid account. Upgrade quota in billing.", 5, 20)
    assert ly_do["code"] == "quota_exceeded"
    assert ly_do["plan"] == "paid"
    assert "Free" not in top_ads._canh_bao_thieu(ly_do, 5, 20)


def test_short_result_khong_co_status_thi_khong_doan_nguyen_nhan():
    ly_do = top_ads._phan_loai_gioi_han("", 5, 20)
    assert ly_do == {
        "code": "unknown_short_result",
        "verified": False,
        "evidence": None,
    }
    canh_bao = top_ads._canh_bao_thieu(ly_do, 5, 20)
    assert "chưa xác định nguyên nhân" in canh_bao
    assert "Free" not in canh_bao


def test_free_chi_khi_status_noi_ro_free_account():
    ly_do = top_ads._phan_loai_gioi_han(
        "Free accounts have limited data extraction.", 5, 20)
    assert ly_do["code"] == "free_plan_data_limit"
    assert ly_do["plan"] == "free"
    assert ly_do["verified"] is True
    canh_bao = top_ads._canh_bao_thieu(ly_do, 5, 20)
    assert "actor báo tài khoản đang ở gói Free" in canh_bao
    assert "chạy lại cũng chỉ ra cùng" not in canh_bao


def test_fallback_nganh_con_duoc_danh_dau_pham_vi_rong_hon():
    bo, loi = top_ads._doc_tham_so({"nganh": "trang sức"})
    assert not loi and bo["nganh"]["la_nganh_con"]
    scope = top_ads._doi_chieu_pham_vi(bo, "dự phòng")
    assert scope["scope_match"] is False
    assert scope["partial_reason"] == "broader_industry"
    assert "trang sức" in scope["requested_scope"].lower()
    assert scope["actual_scope"] != scope["requested_scope"]


def test_nguon_chinh_giu_dung_pham_vi_yeu_cau():
    bo, loi = top_ads._doc_tham_so({"nganh": "trang sức"})
    assert not loi
    scope = top_ads._doi_chieu_pham_vi(bo, "chính")
    assert scope["scope_match"] is True
    assert scope["partial_reason"] is None
    assert scope["actual_scope"] == scope["requested_scope"]
