"""Canh trần thời gian của vòng job.

Trước 18/09 vòng job gọi `tra_loi` đồng bộ, KHÔNG trần. Một lượt gọi model treo là
đứng cả cửa console lẫn cửa Lark — không log, không lỗi, không cách nào biết ngoài
việc nhắn thử rồi ngồi đợi. Đã xảy ra thật: job #1985 nằm im 5 phút; khởi động lại
thì job kế tiếp xong trong 8 giây.

Kiểu hỏng này không để lại dấu vết, nên bài test là chỗ duy nhất nó đỏ lên.
"""

from __future__ import annotations

import pathlib
import sys
import threading
import time

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))


@pytest.fixture
def LP():
    m = pytest.importorskip("lsr_platform")
    cu = m._HAN_TRA_LOI
    m._HAN_TRA_LOI = 1.0          # ghim ngắn để bài test chạy nhanh
    yield m
    m._HAN_TRA_LOI = cu


def _nhanh(h, chat_id=None, sender_open_id=None):
    return "trả lời ngay"


def _cham(h, chat_id=None, sender_open_id=None):
    time.sleep(30)
    return "quá muộn"


def _no(h, chat_id=None, sender_open_id=None):
    raise RuntimeError("model hỏng")


def test_luot_nhanh_khong_bi_anh_huong(LP):
    dap, ok, treo = LP._chay_co_han(_nhanh, "hỏi", "p", None)
    assert (dap, ok, treo) == ("trả lời ngay", True, False)


def test_luot_treo_bi_cat_dung_han(LP):
    t0 = time.time()
    dap, ok, treo = LP._chay_co_han(_cham, "hỏi", "p", None)
    mat = time.time() - t0
    assert treo and not ok, "lượt treo phải bị cắt"
    assert mat < LP._HAN_TRA_LOI + 2, (
        f"cắt muộn {mat:.1f}s — vòng job vẫn bị chặn, tức watchdog không ăn"
    )


def test_treo_van_tra_loi_tu_te_cho_nguoi_dung(LP):
    dap, _, treo = LP._chay_co_han(_cham, "hỏi", "p", None)
    assert treo
    assert dap.strip(), "im lặng là thứ tệ nhất — phải nói gì đó"
    assert "thử hỏi lại" in dap or "thu hẹp" in dap, (
        "câu trả lời phải bảo người dùng làm gì tiếp, không chỉ báo lỗi"
    )


def test_luot_nem_loi_khong_bi_nham_la_treo(LP):
    dap, ok, treo = LP._chay_co_han(_no, "hỏi", "p", None)
    assert not ok and not treo, "lỗi và quá hạn là hai chuyện khác nhau"
    assert "Xin lỗi" in dap


def test_luong_qua_han_la_daemon(LP):
    """Luồng treo không giết được, nhưng KHÔNG được chặn lúc thoát tiến trình."""
    LP._chay_co_han(_cham, "hỏi", "p-daemon", None)
    con = [t for t in threading.enumerate() if t.name.startswith("tra-loi-p-daemon")]
    assert con, "luồng phải còn chạy nền (không bị giết giữa chừng)"
    assert all(t.daemon for t in con), (
        "luồng treo phải là daemon — không thì tắt bot sẽ treo theo nó"
    )


def test_han_doc_duoc_tu_bien_moi_truong():
    import importlib
    import os
    cu = os.environ.get("LSR_HAN_TRA_LOI_SECONDS")
    os.environ["LSR_HAN_TRA_LOI_SECONDS"] = "7"
    try:
        import lsr_platform
        importlib.reload(lsr_platform)
        assert lsr_platform._HAN_TRA_LOI == 7.0, (
            "chỉnh được trần mà không phải sửa mã — cần khi một tác vụ hợp lệ chạy lâu"
        )
    finally:
        if cu is None:
            os.environ.pop("LSR_HAN_TRA_LOI_SECONDS", None)
        else:
            os.environ["LSR_HAN_TRA_LOI_SECONDS"] = cu
        import lsr_platform
        importlib.reload(lsr_platform)


def test_tran_mac_dinh_du_rong_cho_viec_that():
    """Cắt sớm là giết việc hợp lệ: `social_listen` cào 5 nền tảng mất vài phút."""
    import importlib
    import os
    os.environ.pop("LSR_HAN_TRA_LOI_SECONDS", None)
    import lsr_platform
    importlib.reload(lsr_platform)
    assert lsr_platform._HAN_TRA_LOI >= 300, (
        f"trần {lsr_platform._HAN_TRA_LOI}s quá ngắn — một lượt quét social thật sẽ bị "
        "cắt oan, và người dùng sẽ tưởng bot hỏng"
    )
