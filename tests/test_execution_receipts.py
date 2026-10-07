import json
import contextvars
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import execution_receipts as R


def _isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "_DIR", tmp_path / "receipts")


def test_receipt_persists_verified_tool_facts_without_secrets(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    row = R.record(
        "chat-a", "10845caa1562", "tiktok_top_ads",
        {"so_ads": 20, "api_token": "sk-super-secret-value"},
        json.dumps({
            "success": True,
            "so_ads_xin": 20,
            "so_ads": 5,
            "pham_vi": "thị trường VN · 7 ngày",
            "nguon": "TikTok Creative Center",
            "chi_phi_thuc_usd": 0.02,
            "sheet_url": "https://example.test/sheets/result",
        }, ensure_ascii=False),
    )

    assert row["status"] == "partial"
    assert row["facts"]["requested_count"] == 20
    assert row["facts"]["actual_count"] == 5
    assert row["facts"]["actual_cost_usd"] == 0.02
    assert row["args"]["api_token"] == "[đã_che]"
    raw = R._path("chat-a").read_text(encoding="utf-8")
    assert "super-secret" not in raw


def test_sanitize_inline_credentials_and_signed_urls_but_preserve_public_sheet(
        monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    public = "https://o4pv.example/sheets/F1kPublic"
    R.record("chat", "turn-secret", "tiktok_top_ads", {
        "header": "Authorization: Bearer bearer-value-123456",
        "note": "api_key=inline-secret-987654",
    }, {
        "success": True,
        "sheet_url": public,
        "items": [{
            "media": ("https://cdn.example/video.mp4?X-Amz-Credential=user%2Fscope"
                      "&X-Amz-Signature=signed-secret&token=query-secret"),
        }],
        "source_url": ("https://source.example/report?id=public-id"
                       "&signature=source-secret&api_key=source-key"),
    })
    row = R.load("chat")[0]
    raw = R._path("chat").read_text(encoding="utf-8")
    assert "bearer-value" not in raw and "inline-secret" not in raw
    assert "signed-secret" not in raw and "query-secret" not in raw
    assert "source-secret" not in raw and "source-key" not in raw
    assert row["facts"]["output_url"] == public
    assert public in row["facts"]["links"]
    assert "video.mp4" not in raw, "raw item URL không cần thiết bị lưu vào receipt"


def test_receipts_are_isolated_by_conversation(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    R.record("chat-a", "turn-a", "tiktok_top_ads", {}, {"success": True, "so_ads": 5})
    R.record("chat-b", "turn-b", "doc_bang", {}, {"success": True, "count": 2})

    assert [row["turn_id"] for row in R.load("chat-a")] == ["turn-a"]
    assert [row["turn_id"] for row in R.load("chat-b")] == ["turn-b"]
    assert R.load("chat-c") == []
    assert R._path("chat-a") != R._path("chat-b")


def test_prompt_contains_receipt_not_raw_payload(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    R.record("chat", "turn-1", "tiktok_top_ads", {"keyword": "HAPAS"}, {
        "success": True, "so_ads_xin": 20, "so_ads": 5,
        "sheet_url": "https://example.test/sheet/1",
        "items": [{"caption": "nội dung dài không cần bơm vào prompt"}],
    })

    block = R.prompt_block("chat")
    assert "turn_id=turn-1" in block
    assert "requested_count=20" in block and "actual_count=5" in block
    assert "nội dung dài" not in block


def test_false_confession_is_replaced_from_receipt_without_rerun(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    R.record("chat", "10845caa1562", "tiktok_top_ads", {}, {
        "success": True, "so_ads_xin": 20, "so_ads": 5,
        "chi_phi_thuc_usd": 0.02,
        "sheet_url": "https://example.test/sheet/1",
    })
    # Giữa lần chạy thật và lời phủ nhận production có một lần nạp skill.
    # Receipt phụ này không được che bằng chứng thực thi TikTok.
    R.record("chat", "b20a8d5042dd", "dung_ky_nang", {"ten": "doi-thu"}, {
        "success": True, "content": "hướng dẫn",
    })

    answer, changed = R.ground_final_answer(
        "chat", "sao bạn pending required trước của tôi?",
        "Tôi đã xử lý sai: tôi không thực sự chạy công cụ nên con số 5 chưa xác minh.")

    assert changed is True
    assert "đã có một lần chạy" in answer
    assert "5/20" in answer and "0.02 USD" in answer
    assert "10845caa1562" in answer
    assert len(R.load("chat")) == 2, "kiểm tra không được chạy lại tool"


def test_exact_logged_confession_quotes_around_other_phrases_do_not_hide_denial(
        monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    R.record("actual-chat", "10845caa1562", "tiktok_top_ads", {"so_ads": 20}, {
        "success": True, "so_ads_xin": 20, "tom_tat": {"so_ads": 5},
        "chi_phi_thuc_usd": 0.02, "sheet_url": "https://example.test/sheet",
    })
    R.record("actual-chat", "b20a8d5042dd", "dung_ky_nang", {}, {"success": True})
    original = ('Tôi xử lý sai luồng ở yêu cầu trước. Bạn đã xác nhận “ok chạy”, '
                'nhưng tôi trả kết quả như thể đã quét mà không thực sự chạy công cụ '
                '— nên cả con số “5 quảng cáo” lẫn lời giải thích về giới hạn nguồn chưa '
                'được xác minh.')
    actual, changed = R.ground_final_answer(
        "actual-chat", "sao bạn pending required trước của tôi", original)
    assert changed is True
    assert "5/20" in actual and "0.02 USD" in actual


def test_guard_does_not_rewrite_innocent_or_unproven_statements(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    R.record("chat", "turn-1", "social_listen", {}, {"success": True, "count": 3})
    for text in (
        "Tôi không chạy lại công cụ vì sẽ tốn phí.",
        "Phần Instagram chưa chạy; biên nhận này chỉ là TikTok.",
        "Kết quả đã chạy, nhưng chưa đủ phạm vi.",
    ):
        answer, changed = R.ground_final_answer("chat", "tình trạng?", text)
        assert changed is False
        assert answer == text


def test_guard_ignores_unrelated_or_non_substantive_receipt(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    R.record("chat", "turn-wiki", "doc_bang", {}, {"success": True, "count": 2})
    answer, changed = R.ground_final_answer(
        "chat", "TikTok đã chạy chưa?", "Tôi không hề chạy TikTok.")
    # Tool đọc Base không phải bằng chứng TikTok đã chạy. Guard hẹp chọn
    # bỏ sót thay vì tự nối hai việc khác nhau.
    assert changed is False and answer == "Tôi không hề chạy TikTok."

    R.record("skill-chat", "turn-skill", "dung_ky_nang", {}, {"success": True})
    skill_answer, skill_changed = R.ground_final_answer(
        "skill-chat", "đã chạy chưa?", "Tôi không thực sự chạy công cụ.")
    assert skill_changed is False and skill_answer.startswith("Tôi không")


def test_guard_ignores_quotation_new_request_and_latest_block(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    R.record("chat", "turn-ok", "tiktok_top_ads", {}, {"success": True, "so_ads": 5})

    quoted = "Câu “tôi không hề chạy công cụ” là sai theo biên nhận."
    assert R.ground_final_answer("chat", "sao bạn nói vậy?", quoted) == (quoted, False)

    current = "Tôi chưa từng chạy TikTok cho yêu cầu này."
    assert R.ground_final_answer("chat", "yêu cầu này đã chạy chưa?", current) == (current, False)

    R.record("chat", "turn-blocked", "tiktok_top_ads", {}, {
        "success": False, "error": "budget_limit",
    })
    blocked = "Tôi không hề chạy công cụ vì lượt này bị chặn."
    assert R.ground_final_answer("chat", "sao bạn chưa chạy?", blocked) == (blocked, False)


def test_failed_or_blocked_receipt_does_not_prove_execution_success(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    R.record("chat", "turn-blocked", "tra_tien_do", {}, {
        "success": False, "error": "missing_identity",
    })
    original = "Tôi không hề chạy công cụ thành công."
    answer, changed = R.ground_final_answer("chat", "đã chạy chưa?", original)
    assert changed is False
    assert answer == original


def test_estimate_receipt_never_proves_execution(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    row = R.record("chat", "turn-estimate", "tiktok_top_ads", {"chi_uoc_tinh": True}, {
        "success": True, "chi_uoc_tinh": True, "da_chay": False,
        "execution_state": "estimated", "so_ads": 20,
        "uoc_tinh_chi_phi_usd": 0.06,
    })
    assert row is None
    assert R.load("chat") == []
    answer = "Tôi không thực sự chạy công cụ."
    assert R.ground_final_answer("chat", "sao bạn pending?", answer) == (answer, False)


def test_generic_denial_without_receipt_anchor_is_not_rewritten(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    R.record("chat", "turn-old", "tiktok_top_ads", {}, {
        "success": True, "so_ads_xin": 20, "so_ads": 5,
    })
    answer = "Tôi không thực sự chạy công cụ với phần việc đó."
    assert R.ground_final_answer("chat", "sao bạn pending?", answer) == (answer, False)


def test_brain_reply_captures_wrapped_tool_and_repairs_false_confession(
        monkeypatch, tmp_path):
    """Phát lại đúng chuỗi production: tool xong 5/20, model sau đó phủ nhận.

    Handler giả được bọc qua cùng registry capture như production; không chạm
    TikTok/Apify, không phát sinh lần quét trả phí.
    """
    import brain
    from tools.registry import registry

    _isolated(monkeypatch, tmp_path)
    tool_name = "tiktok_top_ads"
    entry = SimpleNamespace(
        handler=lambda args, **kw: json.dumps({
            "success": True, "so_ads_xin": 20, "so_ads": 5,
            "chi_phi_thuc_usd": 0.02,
            "sheet_url": "https://example.test/sheet/1",
        }),
        is_async=False,
    )
    original_entry = registry._tools.get(tool_name)
    registry._tools[tool_name] = entry
    monkeypatch.setattr(R, "_installed", False)
    R.install_registry_capture()

    class Agent:
        model = "test-model"
        def run_conversation(self, *args, **kwargs):
            result = registry._tools[tool_name].handler({"so_ads": 20})
            assert result
            return {"final_response": (
                "Tôi xử lý sai: tôi không thực sự chạy công cụ, "
                "nên con số 5 chưa được xác minh.")}

    monkeypatch.setattr(brain, "_resolve_agent", lambda *a, **k: Agent())
    monkeypatch.setattr(brain.lsr_platform, "lay_ngu_canh", lambda *a, **k: {})
    monkeypatch.setattr(brain.lsr_platform, "ghi_luot_ngu_canh", lambda *a, **k: None)
    monkeypatch.setattr(brain.memory_store, "load_history", lambda cid: [])
    monkeypatch.setattr(brain.memory_store, "append_turns", lambda *a, **k: None)
    monkeypatch.setattr(brain.audit, "bat_dau", lambda *a, **k: "turn-replay")
    monkeypatch.setattr(brain.audit, "ket_thuc", lambda *a, **k: {})
    monkeypatch.setattr(brain.audit, "ghi_chat_luong", lambda *a, **k: None)
    monkeypatch.setattr(brain.tai_khoan_ai, "ghi_luot", lambda *a, **k: None)

    try:
        # brain.reply gắn scheduler/đồng hồ/audit bằng ContextVar. Chạy replay
        # trong context riêng để bài này không để lại "lượt hiện tại" cho
        # bài Sheet/FB chạy sau trong cùng pytest worker.
        answer = contextvars.Context().run(
            lambda: brain.reply(
                "sao bạn pending required trước của tôi?",
                chat_id="chat-replay", sender_open_id=None))
    finally:
        if original_entry is None:
            registry._tools.pop(tool_name, None)
        else:
            registry._tools[tool_name] = original_entry
    assert "đã có một lần chạy" in answer
    assert "5/20" in answer and "0.02 USD" in answer
    assert len(R.load("chat-replay")) == 1


def test_registry_capture_propagates_context_and_clear_prevents_stale_receipt(
        monkeypatch, tmp_path):
    from tools.registry import registry

    _isolated(monkeypatch, tmp_path)
    name = "receipt_context_test"
    registry._tools[name] = SimpleNamespace(
        handler=lambda args, **kw: {"success": True, "count": args["count"]},
        is_async=False,
    )
    monkeypatch.setattr(R, "_installed", False)
    R.install_registry_capture()
    wrapped = registry._tools[name].handler
    try:
        R.set_current_turn("chat-thread", "turn-thread")
        copied = contextvars.copy_context()
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(copied.run, wrapped, {"count": 7}).result()["count"] == 7
        assert [r["turn_id"] for r in R.load("chat-thread")] == ["turn-thread"]

        R.clear_current_turn()
        wrapped({"count": 8})
        assert len(R.load("chat-thread")) == 1, (
            "tool ngoài lượt bị ghi nhầm vào context cũ sau clear")
    finally:
        R.clear_current_turn()
        registry._tools.pop(name, None)
