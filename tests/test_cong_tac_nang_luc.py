"""Canh lớp công tắc Năng lực trong `lsr_policy`.

Công tắc là lớp THU HẸP trên hợp đồng, không phải ranh giới an toàn. Ba tính chất phải
giữ, và cả ba đều hỏng theo kiểu khó thấy nếu ai đó sửa ẩu:

1. Công tắc BẬT không bao giờ nới quá hợp đồng. Đảo thứ tự hai lớp là mất tính chất
   này mà mọi thứ vẫn "chạy được".
2. Chưa khai `capabilities` thì KHÔNG thu hẹp gì. Coi "trống = tắt hết" là làm chết
   mọi agent khác trên platform.
3. Tool ngoài hệ thống công tắc (`schedule_reminder`, `remember_about_user`,
   `list_reminders`…) không bao giờ bị tắt lây. Đây là cái bẫy thật: `capabilities`
   chỉ chứa tool ĐANG BẬT, nên nếu runtime không biết danh mục thì nó sẽ hiểu nhầm
   "không có trong danh sách" thành "bị tắt".

Không mạng: ghim thẳng vào hai bản nhớ của `lsr_policy`.
"""

from __future__ import annotations

import pathlib
import re
import sys
import time

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

#: Repo Platform trên máy dev (PLATFORM_REPO trỏ được sang bản checkout mới hơn). Không có
#: thì bỏ qua bài đối chiếu chéo.
_TS_PLATFORM = (pathlib.Path(__import__("os").environ.get("PLATFORM_REPO") or r"D:\Platform")
                / "apps" / "platform-web" / "lib" / "agentToolCapabilities.ts")

HOP_DONG_DU = {"reply", "call_agent", "write_data"}


@pytest.fixture
def P():
    p = pytest.importorskip("lsr_policy")
    q_cu, nl_cu = dict(p._nho), dict(p._nho_nl)
    yield p
    p._nho.clear(); p._nho.update(q_cu)
    p._nho_nl.clear(); p._nho_nl.update(nl_cu)


def _dat(p, quyen: set[str], bat) -> None:
    gio = time.time()
    p._nho.update(quyen=set(quyen), luc=gio, nguon="test")
    p._nho_nl.update(bat=bat, luc=gio, nguon="test")


def test_bat_het_thi_khong_doi_hanh_vi(P):
    _dat(P, HOP_DONG_DU, set(P._TOOL_CO_CONG_TAC))
    for t in P._TOOL_CO_CONG_TAC - {"lark_cli"}:
        assert P.decide(t, {}).allowed, f"{t} bị chặn dù công tắc bật"
    assert P.decide("lark_cli", {"args": ["wiki", "+search", "x"]}).allowed


def test_tat_mot_cai_chi_chan_dung_cai_do(P):
    _dat(P, HOP_DONG_DU, set(P._TOOL_CO_CONG_TAC) - {"social_listen"})
    d = P.decide("social_listen", {})
    assert not d.allowed
    assert "đang TẮT" in d.reason, (
        "lý do phải nói rõ là do CHỦ AGENT TẮT, không phải thiếu quyền — "
        f"đang trả: {d.reason}"
    )
    assert P.decide("social_deep_dive", {}).allowed, "tắt nhầm sang tool khác"


@pytest.mark.parametrize("tool", ["schedule_reminder", "cancel_reminder",
                                  "remember_about_user", "list_reminders",
                                  "browser_get_text"])
def test_tool_ngoai_he_thong_cong_tac_khong_bi_tat_lay(P, tool):
    """Tắt sạch 6 công tắc vẫn không được đụng tới tool không có công tắc."""
    _dat(P, HOP_DONG_DU, set())
    assert tool not in P._TOOL_CO_CONG_TAC
    assert P.decide(tool, {}).allowed, (
        f"{tool} bị tắt lây — `capabilities` chỉ chứa tool ĐANG BẬT, nên thiếu danh "
        "mục `_TOOL_CO_CONG_TAC` là runtime hiểu nhầm 'không có trong danh sách' "
        "thành 'bị tắt'"
    )


def test_chua_khai_capabilities_thi_khong_thu_hep(P):
    """Trạng thái của mọi agent khác trên platform."""
    _dat(P, HOP_DONG_DU, P.KHONG_THU_HEP)
    for t in P._TOOL_CO_CONG_TAC - {"lark_cli"}:
        assert P.decide(t, {}).allowed, f"{t} bị chặn dù agent chưa khai capabilities"


def test_cong_tac_khong_bao_gio_noi_qua_hop_dong(P):
    """Tính chất quan trọng nhất: công tắc chỉ thu hẹp, không nới."""
    _dat(P, {"reply", "call_agent"}, set(P._TOOL_CO_CONG_TAC))   # planner, bật hết
    d = P.decide("social_listen", {})
    assert not d.allowed, "công tắc BẬT đã nới quá hợp đồng — thứ tự hai lớp bị đảo"
    assert "write_data" in d.reason, f"lý do phải là thiếu quyền hợp đồng: {d.reason}"


def test_doc_hong_thi_giu_ban_nho_cuoi(P):
    _dat(P, HOP_DONG_DU, {"social_deep_dive"})
    P._nho_nl["luc"] = 0                       # ép hết hạn
    P._nho["luc"] = time.time()
    goc = P._nang_luc_tu_danh_ba
    P._nang_luc_tu_danh_ba = lambda: None       # giả lập mất mạng
    try:
        assert not P.decide("social_listen", {}).allowed, "mất mạng đã làm nới quyền"
        assert P.decide("social_deep_dive", {}).allowed, "mất mạng đã làm câm tool đang bật"
    finally:
        P._nang_luc_tu_danh_ba = goc


def test_khop_danh_muc_ben_console():
    """`_TOOL_CO_CONG_TAC` phải khớp danh mục console, nếu không sẽ có tool không tắt được.

    Hai repo khác nhau nên CI không chạy được bài này — chỉ chạy trên máy dev có cả
    hai. Vẫn đáng giữ: lệch ở đây nghĩa là owner bấm tắt trên console mà runtime không
    biết, tức công tắc im lặng không ăn.
    """
    if not _TS_PLATFORM.is_file():
        pytest.skip(f"không có {_TS_PLATFORM}")
    import lsr_policy
    s = _TS_PLATFORM.read_text(encoding="utf-8")
    khoi = re.search(r'"AG-SOCIAL-LISTENING":\s*\[(.*?)\n  \]', s, re.S)
    assert khoi, "không đọc được mục AG-SOCIAL-LISTENING trong agentToolCapabilities.ts"
    ben_console = set(re.findall(r'tool:\s*"([^"]+)"', khoi.group(1)))
    assert ben_console, "đọc ra danh mục rỗng — regex hỏng, khẳng định sau vô nghĩa"
    runtime = set(lsr_policy._TOOL_CO_CONG_TAC)
    # Tool có công tắc lùi được phép CHỜ console: console chưa có dòng của nó thì runtime
    # lùi về công tắc cha — đúng hành vi cũ, nên thứ tự merge hai repo không quan trọng.
    cho = set(lsr_policy._CONG_TAC_LUI)
    assert ben_console in (runtime, runtime - cho), (
        f"lệch danh mục công tắc — console {sorted(ben_console)} vs "
        f"runtime {sorted(runtime)} (được chờ: {sorted(cho)})"
    )
    # Console đã có tool lùi thì nó phải khai đúng công tắc cha (`theo:`).
    for tool, cha in lsr_policy._CONG_TAC_LUI.items():
        if tool in ben_console:
            dong = re.search(r'\{[^{}]*tool:\s*"%s"[^{}]*\}' % re.escape(tool),
                             khoi.group(1), re.S)
            assert dong and re.search(r'theo:\s*"%s"' % re.escape(cha), dong.group(0)), (
                f"console có '{tool}' nhưng không khai theo: \"{cha}\" — console và "
                "runtime hiểu khác nhau khi chưa ai đặt công tắc này")


# ─────────── công tắc lùi: `tiktok_top_ads` có công tắc riêng, chưa đặt thì theo cha ───────────

def test_cong_tac_lui_tro_vao_tool_co_cong_tac(P):
    for tool, cha in P._CONG_TAC_LUI.items():
        assert tool in P._TOOL_CO_CONG_TAC and cha in P._TOOL_CO_CONG_TAC
        assert cha not in P._CONG_TAC_LUI, "không xích hai tầng — console chỉ lùi một tầng"


def test_top_ads_chua_dat_rieng_thi_theo_quet_mxh(P):
    """Console cũ (chưa có công tắc Top Ads), hoặc chưa ai bấm: y như trước."""
    _dat(P, HOP_DONG_DU, {"social_listen"})
    assert P.decide("tiktok_top_ads", {}).allowed
    _dat(P, HOP_DONG_DU, {"soi_san"})
    d = P.decide("tiktok_top_ads", {})
    assert not d.allowed and "theo công tắc 'social_listen'" in d.reason, d.reason


def test_top_ads_bat_rieng_khi_quet_mxh_tat(P):
    _dat(P, HOP_DONG_DU, {"soi_san", "tiktok_top_ads"})
    assert P.decide("tiktok_top_ads", {}).allowed, "công tắc riêng bật mà vẫn theo cha"
    assert not P.decide("social_listen", {}).allowed, "bật Top Ads không được bật lây cha"


def test_top_ads_tat_ro_khi_quet_mxh_bat(P):
    _dat(P, HOP_DONG_DU, {"social_listen"})
    P._nho_nl["tat_ro"] = {"tiktok_top_ads"}
    d = P.decide("tiktok_top_ads", {})
    assert not d.allowed and "đang TẮT" in d.reason
    assert "theo công tắc" not in d.reason, "tắt bằng công tắc RIÊNG, không phải của cha"
    assert P.decide("social_listen", {}).allowed, "tắt Top Ads không được tắt lây cha"


def test_top_ads_khong_noi_qua_hop_dong(P):
    _dat(P, {"reply", "call_agent"}, {"tiktok_top_ads", "social_listen"})
    d = P.decide("tiktok_top_ads", {})
    assert not d.allowed and "write_data" in d.reason


def test_top_ads_chua_khai_capabilities_thi_khong_thu_hep(P):
    _dat(P, HOP_DONG_DU, P.KHONG_THU_HEP)
    assert P.decide("tiktok_top_ads", {}).allowed


# ── đọc thật từ danh bạ (giả `urlopen`): dấu tắt rõ `{tool, bat: false}` của console ──

@pytest.fixture
def danh_ba(P, monkeypatch):
    import io
    import json

    def dat(caps):
        body = json.dumps({"caller": "AG-SOCIAL-LISTENING", "agents": [
            {"agent_id": "AG-SOCIAL-LISTENING", "capabilities": caps}]}).encode()

        class X(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda r, timeout=5: X(body))
        P._nho_nl.update(bat=None, luc=0.0)
        P._nho.update(quyen=set(HOP_DONG_DU), luc=time.time(), nguon="test")

    monkeypatch.setenv("LSR_TELEMETRY_API_KEY", "k")
    monkeypatch.setenv("LSR_PLATFORM_URL", "https://platform.test")
    return dat


def _muc(tool, **k):
    return {"tool": tool, "name": tool, "description": "", **k}


def test_danh_ba_console_cu_thi_lui_ve_quet_mxh(P, danh_ba):
    danh_ba([_muc("social_listen", cau_hinh={"tran_bai_tiktok": 50})])
    assert P.nang_luc_bat() == {"social_listen"}
    assert P.decide("tiktok_top_ads", {}).allowed
    danh_ba([_muc("soi_san")])
    assert not P.decide("tiktok_top_ads", {}).allowed


def test_danh_ba_dau_tat_ro(P, danh_ba):
    danh_ba([_muc("social_listen"), {"tool": "tiktok_top_ads", "bat": False}])
    assert P.nang_luc_bat() == {"social_listen"}, "dấu tắt không được tính là bật"
    assert not P.decide("tiktok_top_ads", {}).allowed
    assert P.decide("social_listen", {}).allowed
    assert P.cau_hinh_tool("tiktok_top_ads") == {}


def test_danh_ba_bat_rieng(P, danh_ba):
    danh_ba([_muc("soi_san"), _muc("tiktok_top_ads")])
    assert P.decide("tiktok_top_ads", {}).allowed
    assert not P.decide("social_listen", {}).allowed


def test_danh_ba_chi_con_dau_tat_la_tat_het(P, danh_ba):
    """Console tắt hết thì chỉ còn dấu tắt — vẫn là bảng công tắc, KHÔNG phải "chưa
    khai". Hiểu thành chưa khai là bật lại mọi thứ chủ agent vừa tắt."""
    danh_ba([{"tool": "tiktok_top_ads", "bat": False}])
    assert P.nang_luc_bat() == set()
    for t in P._TOOL_CO_CONG_TAC - {"lark_cli"}:
        assert not P.decide(t, {}).allowed, f"{t} vẫn chạy dù console tắt hết"


def test_danh_ba_doc_lai_khong_giu_dau_tat_cu(P, danh_ba):
    danh_ba([_muc("social_listen"), {"tool": "tiktok_top_ads", "bat": False}])
    assert not P.decide("tiktok_top_ads", {}).allowed
    danh_ba([_muc("social_listen")])
    assert P.decide("tiktok_top_ads", {}).allowed, "dấu tắt của lần đọc trước còn dính"
    danh_ba(None)
    assert P.nang_luc_bat() is P.KHONG_THU_HEP
    assert P.decide("tiktok_top_ads", {}).allowed


# ─────────── `binh_luan_kenh_nha`: công tắc riêng, chưa đặt thì theo Quét MXH (như Top Ads) ───────────

def test_kenh_nha_cong_tac_lui_ve_quet_mxh(P):
    assert P._CONG_TAC_LUI["binh_luan_kenh_nha"] == "social_listen"
    assert "binh_luan_kenh_nha" in P._TOOL_CO_CONG_TAC


def test_danh_ba_kenh_nha_bat_rieng_khi_quet_mxh_tat(P, danh_ba):
    danh_ba([_muc("soi_san"), _muc("binh_luan_kenh_nha")])
    assert P.decide("binh_luan_kenh_nha", {}).allowed, "công tắc riêng bật mà vẫn theo cha"
    assert not P.decide("social_listen", {}).allowed
    assert not P.decide("tiktok_top_ads", {}).allowed, "bật kênh nhà không được bật lây Top Ads"


def test_danh_ba_kenh_nha_tat_ro_khi_quet_mxh_bat(P, danh_ba):
    danh_ba([_muc("social_listen"), {"tool": "binh_luan_kenh_nha", "bat": False}])
    d = P.decide("binh_luan_kenh_nha", {})
    assert not d.allowed and "đang TẮT" in d.reason and "theo công tắc" not in d.reason
    assert P.decide("social_listen", {}).allowed, "tắt kênh nhà không được tắt lây cha"
    assert P.decide("tiktok_top_ads", {}).allowed, "dấu tắt của kênh nhà không đụng Top Ads"


def test_danh_ba_kenh_nha_console_cu_thi_theo_quet_mxh(P, danh_ba):
    danh_ba([_muc("social_listen")])
    assert P.decide("binh_luan_kenh_nha", {}).allowed
    danh_ba([_muc("soi_san")])
    d = P.decide("binh_luan_kenh_nha", {})
    assert not d.allowed and "theo công tắc 'social_listen'" in d.reason
