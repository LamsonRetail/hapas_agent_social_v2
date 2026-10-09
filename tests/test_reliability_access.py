"""Các ca hồi quy từ kiểm toán độ tin cậy 07/10, không gọi Lark thật."""

from __future__ import annotations

import json

import bang_tool
import lark_bang
import lsr_platform
from lsr_policy import decide


def test_docs_fetch_is_refused_with_redirect_to_doc_tai_lieu():
    """09/10: `docs +fetch` đọc bằng quyền BOT, không kiểm người hỏi — nay bị chặn và lý do
    chỉ đường sang `doc_tai_lieu` (kiểm quyền người hỏi như doc_bang)."""
    verdict = decide("lark_cli", {
        "args": ["docs", "+fetch", "--doc-token", "doc_123", "--doc-format", "markdown"],
    })
    assert not verdict.allowed
    assert "doc_tai_lieu" in verdict.reason


def test_option_values_cannot_turn_ambiguous_command_into_read():
    verdict = decide("lark_cli", {
        "args": ["docs", "+mystery", "--title", "please fetch this"],
    })
    assert not verdict.allowed
    assert "doc_tai_lieu" in verdict.reason


def test_option_values_do_not_make_read_command_look_mutating():
    """Giá trị option ('Copy update plan') không biến lệnh đọc thành lệnh ghi: lý do từ
    chối vẫn là đường đọc tài liệu, không phải 'động từ ghi/gửi'."""
    verdict = decide("lark_cli", {
        "args": ["docs", "+fetch", "--title", "Copy update plan"],
    })
    assert not verdict.allowed
    assert "doc_tai_lieu" in verdict.reason and "động từ ghi" not in verdict.reason


def test_raw_api_cannot_read_doc_content_either():
    for path in ("/open-apis/docx/v1/documents/doxAbc/raw_content",
                 "/open-apis/docx/v1/documents/doxAbc/blocks",
                 "open-apis/doc/v2/docAbc/raw_content"):
        verdict = decide("lark_cli", {"args": ["api", "GET", path]})
        assert not verdict.allowed, path
        assert "doc_tai_lieu" in verdict.reason


def test_doc_discovery_and_wiki_metadata_still_allowed():
    for args in (["docs", "--help"], ["docs", "+fetch", "--help"],
                 ["schema", "docx.document.raw_content"],
                 ["wiki", "+node-get", "--token", "wikTok"],
                 ["api", "GET", "/open-apis/wiki/v2/spaces/get_node"]):
        verdict = decide("lark_cli", {"args": args})
        assert verdict.allowed, (args, verdict.reason)


def test_lark_cli_write_commands_stay_blocked():
    for args in (
        ["docs", "+update"],
        ["base", "+record-create"],
        ["task", "+delete"],
        ["base", "records", "+delete", "--record-id", "rec_1"],
        ["api", "POST", "/open-apis/docx/v1/documents"],
    ):
        verdict = decide("lark_cli", {"args": args})
        assert not verdict.allowed, (args, verdict.reason)


def test_missing_identity_message_does_not_prescribe_sharing(monkeypatch):
    monkeypatch.delenv("AGENT_BOSS_OPEN_ID", raising=False)
    monkeypatch.delenv("STEVEN_BOSS_OPEN_ID", raising=False)
    monkeypatch.setattr(bang_tool, "_nguoi_hoi", lambda: "")
    monkeypatch.setattr(bang_tool, "base_noi_bo", lambda: set())
    monkeypatch.setattr(bang_tool, "_trong_cay_wiki", lambda *args: False)
    monkeypatch.setattr(lark_bang, "nhan_dien", lambda _nguon: ("bitable", "base_x", "tbl_x"))
    monkeypatch.setattr(lark_bang.lark, "call", lambda *args, **kwargs: {"data": {}})

    result = json.loads(bang_tool._handle({"nguon": "https://example.larksuite.com/base/base_x"}))

    assert "Console chưa chuyển danh tính Lark đã xác thực" in result["error"]
    assert "Chia sẻ thêm tài liệu không tự khắc phục" in result["error"]
    assert "Nhờ chủ Base chia sẻ" not in result["error"]


def test_web_job_never_trusts_raw_user_ref_open_id():
    forged = {"user_ref": "ou_victim", "sender_open_id": "ou_forged"}
    assert lsr_platform._lark_sender_ref(forged, "web") is None


def test_web_job_accepts_only_platform_verified_sender():
    verified = {"user_ref": "owner@lsr.vn", "sender_open_id": "ou_owner_agent_app",
                "sender_identity_verified": True}
    assert lsr_platform._lark_sender_ref(verified, "web") == "ou_owner_agent_app"


def test_old_web_job_fails_closed_but_lark_legacy_still_works():
    old = {"user_ref": "ou_old"}
    assert lsr_platform._lark_sender_ref(old, "web") is None
    assert lsr_platform._lark_sender_ref(old, "lark") == "ou_old"
    assert lsr_platform._lark_sender_ref({"sender_open_id": "ou_lark"}, "lark") == "ou_lark"
