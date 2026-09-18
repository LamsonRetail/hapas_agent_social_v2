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

#: Repo Platform trên máy dev. Không có thì bỏ qua bài đối chiếu chéo.
_TS_PLATFORM = pathlib.Path(r"D:\Platform\apps\platform-web\lib\agentToolCapabilities.ts")

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
    assert ben_console == set(lsr_policy._TOOL_CO_CONG_TAC), (
        f"lệch danh mục công tắc — console {sorted(ben_console)} vs "
        f"runtime {sorted(lsr_policy._TOOL_CO_CONG_TAC)}"
    )
