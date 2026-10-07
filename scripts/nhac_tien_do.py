"""Thử tay bộ nhắc tiến độ (tien_do.py) — xem trước, hoặc gửi MỘT lần vào nhóm chỉ định.

    python scripts/nhac_tien_do.py --xem-truoc                    # in tin SẼ gửi hôm nay, không gửi
    python scripts/nhac_tien_do.py --xem-truoc --ngay 2026-10-10  # như trên, coi "hôm nay" là ngày khác
    python scripts/nhac_tien_do.py --gui-thu --chat oc_xxx        # gửi thật MỘT lần vào oc_xxx

Vì sao đường gửi đòi cả `--gui-thu` lẫn `--chat`: đây là tin có @nhắc người thật. Không lấy
nhóm từ MARK_NHAC_TIEN_DO_CHAT (có thể đang trỏ nhóm dự án thật) — người chạy phải gõ mã
nhóm thử bằng tay. Gửi thử KHÔNG ghi sổ `.tokens/nhac_tien_do.json`, nên không chặn nhắc
08:30 của bộ chạy chính. Chỉ đọc Base; không có việc quá hạn/sắp hạn thì không gửi gì.

Chạy ở thư mục gốc repo (cạnh .env).
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))


def _tham_so(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Xem trước / gửi thử tin nhắc tiến độ.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--xem-truoc", action="store_true", help="in tin sẽ gửi, KHÔNG gửi")
    g.add_argument("--gui-thu", action="store_true", help="gửi MỘT lần vào --chat")
    p.add_argument("--chat", default="", help="mã nhóm oc_… (bắt buộc với --gui-thu)")
    p.add_argument("--ngay", default="", help="yyyy-mm-dd, mặc định hôm nay giờ VN")
    a = p.parse_args(argv)
    if a.gui_thu and not re.fullmatch(r"oc_[A-Za-z0-9]+", a.chat or ""):
        p.error("--gui-thu cần --chat oc_… gõ tay (không lấy nhóm từ cấu hình)")
    if a.xem_truoc and a.chat:
        p.error("--xem-truoc không gửi gì — bỏ --chat")
    return a


def main(argv: list[str] | None = None) -> int:
    a = _tham_so(argv)
    import config  # noqa: F401  (nạp .env)
    import tien_do as T

    try:
        ngay = (datetime.date.fromisoformat(a.ngay) if a.ngay else T.hom_nay_vn())
    except ValueError:
        print(f"--ngay '{a.ngay}' không phải yyyy-mm-dd")
        return 2
    print(T.trang_thai_khoi_dong())
    try:
        tin, d = T.soan_tin_hom_nay(ngay)
    except Exception as e:  # noqa: BLE001
        print(f"Không đọc được Base — không gửi gì: {e}")
        return 1
    print(f"Base: {d['ten']} — {d['url']}  ·  ngày {ngay:%d/%m/%Y}")
    if not tin:
        print("Không có việc quá hạn / sắp tới hạn → bộ nhắc sẽ KHÔNG gửi tin nào.")
        return 0
    print("-" * 60)
    print(tin)
    print("-" * 60)
    if a.xem_truoc:
        print("(xem trước — chưa gửi)")
        return 0
    import scheduler
    try:
        # uuid theo ngày: lỡ chạy lại lệnh gửi thử trong vòng 1 giờ thì Lark không đăng tin thứ hai.
        scheduler._gui(a.chat, tin, f"tdthu-{a.chat}-{T.hom_nay_vn():%y%m%d}"[:50])
    except scheduler.LoiGui as e:
        print(f"Gửi hỏng: {e}")
        return 1
    print(f"Đã gửi thử vào {a.chat}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
