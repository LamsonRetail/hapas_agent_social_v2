"""Canh `/web` và `/kho` — ép nguồn bằng CẤU TRÚC prompt, không bằng lời dặn.

Hồi quy cho một thất bại thật: gõ `/web Lark Base là gì?` thì Mark vẫn trả lời bằng
wiki và dẫn link wiki. Bộ lệnh chạy đúng, chỉ thị tới được prompt — nhưng nội dung kho
vẫn nằm nguyên trong prompt, kèm luật thường trực "trả lời được bằng kho thì DỪNG Ở
ĐÓ". Hai mệnh lệnh ngược nhau trong cùng một prompt, và cái nằm sát nội dung thắng.

Model không bướng. Lỗi ở chỗ ship hai luật chỏi nhau.

Nên bài test ở đây KHÔNG kiểm "prompt có câu dặn không" — câu dặn đã có sẵn từ đầu mà
vẫn hỏng. Nó kiểm thứ quyết định thật: EVIDENCE CÒN NẰM TRONG PROMPT HAY KHÔNG.
"""
from __future__ import annotations

import pytest

import brain

_CTX = {
    "knowledge": [
        {"title": "LarkSuite for beginner · 6. Lark Base",
         "source_url": "https://o4pvcegwn6b.sg.larksuite.com/wiki/abc#def",
         "content": "Lark Base là công cụ quản lý dữ liệu chung trong Lark.",
         "updated_at": "2026-09-22T00:00:00Z"},
        {"title": "02 Kiến trúc v4 7 tầng",
         "source_url": "https://o4pvcegwn6b.sg.larksuite.com/wiki/xyz#uvw",
         "content": "Kiến trúc v4 gồm bảy tầng.",
         "updated_at": "2026-09-20T00:00:00Z"},
    ],
}


def test_khong_go_lenh_thi_evidence_van_con():
    """Lượt bình thường phải đi y như trước — đây là đường mọi câu hỏi thật chạy qua."""
    p = brain._platform_context_block(_CTX)
    assert "Lark Base là công cụ" in p
    assert "Evidence từ kho kiến thức" in p


def test_web_GO_HAN_evidence_khoi_prompt():
    """Ràng buộc quan trọng nhất của tệp này.

    Không có evidence trong prompt thì không còn gì để lấy — đó mới là ép. Dặn model
    đừng dùng thứ đang nằm ngay trước mắt nó là chuyện đã thử và đã hỏng.
    """
    p = brain._platform_context_block(_CTX, "/web")
    assert "Lark Base là công cụ" not in p, "nội dung kho vẫn còn trong prompt"
    assert "Kiến trúc v4 gồm bảy tầng" not in p
    assert "Evidence từ kho kiến thức" not in p
    assert "wiki/abc#def" not in p, "link wiki còn sót — model sẽ dẫn lại link đó"


def test_web_noi_ro_kho_bi_GO_chu_khong_phai_kho_rong():
    """Bỏ evidence mà không giải thích thì model tưởng kho rỗng và nói sai với người
    dùng rằng 'không có tài liệu nào'."""
    p = brain._platform_context_block(_CTX, "/web")
    assert "GỠ" in p or "gỡ" in p
    assert "không phải kho rỗng" in p


def test_web_KHONG_kem_luat_thuong_truc():
    """Luật thường trực nói 'kho trước, dừng ở đó' — kèm nó vào lượt /web là lại ship
    đúng hai mệnh lệnh chỏi nhau đã làm hỏng lần trước."""
    p = brain._platform_context_block(_CTX, "/web")
    assert "DỪNG Ở ĐÓ" not in p
    assert "KHO TÀI LIỆU TRƯỚC" not in p


def test_kho_GIU_evidence_va_cam_ra_web():
    p = brain._platform_context_block(_CTX, "/kho")
    assert "Lark Base là công cụ" in p, "/kho mà mất evidence thì không còn gì để trả lời"
    assert "Không ra web trong lượt này" in p


def test_kho_cung_KHONG_kem_luat_thuong_truc():
    """Luật thường trực có điều 3: 'kho KHÔNG có mới ra web'. Gõ /kho rồi mà vẫn kèm
    câu đó là để hở đúng cái cửa người dùng vừa đóng."""
    p = brain._platform_context_block(_CTX, "/kho")
    assert "Kho KHÔNG có mới ra web" not in p
    assert "kho không có" in p.lower(), "/kho phải dặn nói thẳng khi kho thiếu"


def test_lenh_nguon_di_duoc_toi_prompt_that():
    """Nối tham số qua ba tầng hàm — đứt một tầng thì mọi test trên vẫn xanh mà thực
    tế không đổi gì. Đây là bài canh chính cái mối nối đó."""
    import inspect
    for ham in (brain._build_system_prompt, brain._resolve_agent):
        assert "nguon" in inspect.signature(ham).parameters, f"{ham.__name__} thiếu `nguon`"


@pytest.mark.parametrize("lenh", ["/kho", "/web"])
def test_lenh_nguon_khop_bang_cua_lenh_cung(lenh):
    import lenh_cung
    assert lenh in lenh_cung.LENH_NGUON, (
        f"{lenh} rơi khỏi LENH_NGUON thì `reply` không truyền `nguon` nữa, "
        "và prompt lặng lẽ quay về hành vi cũ"
    )
