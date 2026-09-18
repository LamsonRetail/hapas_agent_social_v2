import json

from lsr_policy import decide


def test_lark_raw_get_is_allowed():
    assert decide("lark_cli", {"args": ["api", "GET", "/open-apis/wiki/v2/spaces"]}).allowed


def test_lark_raw_post_is_denied():
    verdict = decide("lark_cli", {"args": ["api", "POST", "/open-apis/im/v1/messages"]})
    assert not verdict.allowed


def test_lark_high_risk_yes_is_denied():
    assert not decide("lark_cli", {"args": ["task", "+create", "--yes"]}).allowed


def test_sheet_producing_social_tools_follow_the_contract():
    """Ba tool xuất Lark Sheet đi theo `write_data`, không theo một bảng cứng.

    Tên cũ là `..._denied_until_scope_is_decided` và khẳng định chúng LUÔN bị chặn —
    đúng hồi Mark còn là `planner`. Ngày 17/09 Mark thành `executive` và được
    `write_data`, nên bài test đó thành sai; nó đỏ đúng một ngày mới bị phát hiện vì
    lúc đổi type tôi chỉ chạy các bài mới viết, không chạy lại bộ cũ.

    Bản này ghim quyền tường minh nên không phụ thuộc hợp đồng đang khai gì ngoài
    thực tế, và kiểm CẢ HAI chiều — đó mới là bất biến thật.
    """
    import time

    import lsr_policy

    cu = dict(lsr_policy._nho)
    try:
        for quyen, mong in (({"reply", "call_agent"}, False),           # planner
                            ({"reply", "call_agent", "write_data"}, True)):
            lsr_policy._nho.update(quyen=set(quyen), luc=time.time(), nguon="test")
            for name in ("social_listen", "social_deep_dive", "web_crawl"):
                assert decide(name, {}).allowed is mong, (
                    f"{name} với quyền {sorted(quyen)}: chờ "
                    f"{'cho' if mong else 'chặn'}"
                )
    finally:
        lsr_policy._nho.clear()
        lsr_policy._nho.update(cu)


def test_read_only_research_tools_are_allowed():
    for name in ("fb_ads_library", "web_scrape", "browser_snapshot"):
        assert decide(name, {}).allowed


def test_unknown_tool_fails_closed():
    verdict = decide("future_super_tool", {"action": "maybe"})
    assert json.loads(json.dumps(verdict.__dict__))["allowed"] is False
