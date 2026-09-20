"""Canh lời dặn quyền hạn trong prompt lệch khỏi bộ thực thi `lsr_policy`.

Đã xảy ra thật, và tốn của owner một buổi: prompt ghim cứng "LUẬT VAI PLANNER — Mark
KHÔNG có quyền ghi/sửa Base, Sheet". Khi Mark đổi sang `executive` và `lsr_policy` đã
cho phép `social_listen`, prompt vẫn dặn là bị cấm — model TỪ CHỐI trước khi thử.
Người dùng thấy "không có quyền trả sheet" trong khi quyền đã có.

Cái đau là không có gì hỏng: tool chạy được, policy đúng, chỉ có PROMPT nói sai. Không
log nào báo, không test nào đỏ. Bài test này là chỗ đó đỏ lên.

Không mạng: ép `lsr_policy` dùng bản nhớ tạm với từng bộ quyền giả định.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))


@pytest.fixture
def bo_doi():
    """Trả (brain, lsr_policy) và dọn bản nhớ quyền sau mỗi bài."""
    brain = pytest.importorskip("brain")
    import lsr_policy
    cu = dict(lsr_policy._nho)
    yield brain, lsr_policy
    lsr_policy._nho.clear()
    lsr_policy._nho.update(cu)


def _dat_quyen(lsr_policy, quyen: set[str]) -> None:
    """Ghim quyền phát vào bản nhớ, TTL còn hạn nên không gọi mạng."""
    import time
    lsr_policy._nho.update(quyen=set(quyen), luc=time.time(), nguon="test")


def _phan_duoc(note: str) -> str:
    return note.split("KHÔNG được:")[0]


def test_moi_tool_nam_dung_ben(bo_doi):
    """Mỗi tool phải nằm đúng bên ĐƯỢC PHÉP / KHÔNG được theo `decide()`."""
    brain, lsr_policy = bo_doi
    for quyen in ({"reply", "call_agent"},                       # planner
                  {"reply", "call_agent", "write_data"},         # executive như hiện nay
                  set()):                                        # fail-closed
        _dat_quyen(lsr_policy, quyen)
        note = brain._luat_vai_note()
        duoc = _phan_duoc(note)
        lech = [
            f"quyền={sorted(quyen) or 'rỗng'} · {ten}: "
            f"policy {'cho' if cho else 'chặn'} nhưng lời dặn nói {'được' if trong else 'cấm'}"
            for ten, (mo_ta, args) in brain._TOOL_CAN_XET.items()
            for cho in [lsr_policy.decide(ten, args).allowed]
            for trong in [mo_ta in duoc]
            if cho != trong
        ]
        assert not lech, "lời dặn trong prompt nói sai về quyền:\n  " + "\n  ".join(lech)


def test_co_write_data_thi_khong_duoc_dan_la_cam_ghi_sheet(bo_doi):
    """Bài test tái hiện đúng lỗi đã xảy ra."""
    brain, lsr_policy = bo_doi
    _dat_quyen(lsr_policy, {"reply", "call_agent", "write_data"})
    note = brain._luat_vai_note()
    assert "Lark Sheet" in _phan_duoc(note), (
        "có quyền write_data mà lời dặn không cho Mark xuất Lark Sheet — "
        "model sẽ từ chối trước khi thử, đúng lỗi đã xảy ra 18/09"
    )
    assert "TUYỆT ĐỐI không nói 'tôi không có quyền'" in note


def test_khong_co_write_data_thi_phai_thu_ve_chi_doc(bo_doi):
    brain, lsr_policy = bo_doi
    _dat_quyen(lsr_policy, {"reply", "call_agent"})
    duoc = _phan_duoc(brain._luat_vai_note())
    assert "Lark Sheet" not in duoc, "không có write_data mà vẫn hứa xuất Sheet"


def test_gui_tin_luon_bi_cam_du_hop_dong_cho(bo_doi):
    """Runtime hẹp hơn hợp đồng ở chỗ này — lời dặn phải kể đúng runtime."""
    brain, lsr_policy = bo_doi
    _dat_quyen(lsr_policy, {"reply", "call_agent", "write_data", "send_message"})
    note = brain._luat_vai_note()
    assert "gửi tin, đăng bài" in note.split("KHÔNG được:")[-1], (
        "lsr_policy chặn mọi `lark_cli --yes` kể cả khi hợp đồng cho send_message; "
        "lời dặn phải theo runtime chứ không theo hợp đồng"
    )


def test_khong_con_chu_cung_trong_prompt(bo_doi):
    """Khối `_PLANNER_POLICY_NOTE` đã xoá — còn sót là lại có hai nguồn sự thật."""
    brain, _ = bo_doi
    assert not hasattr(brain, "_PLANNER_POLICY_NOTE"), (
        "khối chữ cứng còn sống — xoá hẳn, đừng để ai dùng lại"
    )
    assert "LUẬT VAI PLANNER" not in brain._build_system_prompt(None, None)


# ───────────────────── luật chọn nguồn: kho tài liệu hay web ──────────────────
#
# Kho tài liệu KHÔNG phải một tool: RAG tự chạy mỗi lượt rồi dán mẩu thẳng vào prompt,
# còn web search thì model phải chủ động gọi. Mất cân bằng đó khiến model gần như luôn
# chọn tài liệu — không phải vì tài liệu đúng hơn, mà vì nó đã nằm sẵn trước mắt.
#
# Với agent social listening thì đó là thiên vị SAI CHIỀU: xu hướng và động thái đối
# thủ mà trả lời bằng ảnh chụp lúc nạp thì sai một cách rất khó phát hiện, vì câu trả
# lời nghe vẫn có căn cứ.

_CO_EVIDENCE = {"version": 1,
                "knowledge": [{"title": "x.md", "content": "abc", "source_url": "u"}]}


def test_co_evidence_thi_co_luat_chon_nguon(bo_doi):
    brain, _ = bo_doi
    sp = brain._build_system_prompt(None, _CO_EVIDENCE)
    assert "### Chọn nguồn: kho tài liệu hay web" in sp


def test_khong_co_evidence_thi_khong_dan_luat(bo_doi):
    """Không có mẩu nào thì luật vô nghĩa — đừng làm phình prompt."""
    brain, _ = bo_doi
    sp = brain._build_system_prompt(None, {"version": 1, "instruction_block": "x"})
    assert "Chọn nguồn" not in sp


def test_noi_ro_kho_tai_lieu_la_anh_chup(bo_doi):
    brain, _ = bo_doi
    sp = brain._build_system_prompt(None, _CO_EVIDENCE)
    assert "ẢNH CHỤP tại lúc nạp" in sp, (
        "không nói thì model coi tài liệu ngang với hiện tại, và trả lời câu về xu "
        "hướng bằng dữ liệu cũ mà vẫn nghe có căn cứ"
    )


def test_viec_doi_theo_thoi_gian_phai_ra_web(bo_doi):
    brain, _ = bo_doi
    sp = brain._build_system_prompt(None, _CO_EVIDENCE)
    assert "phải ra web, KỂ CẢ khi" in sp, (
        "phải nói RÕ là kể cả khi kho có nói tới — không thì model thấy kho có rồi là "
        "dừng, đúng cái thiên vị đang cần chữa"
    )


def test_lech_nhau_thi_phai_noi_ca_hai(bo_doi):
    """Phần giá trị nhất: tự chọn một bên rồi im là giấu mất mâu thuẫn."""
    brain, _ = bo_doi
    sp = brain._build_system_prompt(None, _CO_EVIDENCE)
    assert "NÓI CẢ HAI kèm ngày" in sp
