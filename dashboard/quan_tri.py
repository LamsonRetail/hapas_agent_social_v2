"""Lệnh quản trị chạy trên VPS (user hệ điều hành `lang_nghe_web`, peer auth):

    python -m dashboard.quan_tri them-nguoi <email> <xem|quan_ly>
    python -m dashboard.quan_tri ds-nguoi

Vì sao cần: dashboard chỉ cho người có tên trong `nguoi_xem` vào, nên người quản lý ĐẦU TIÊN
phải thêm từ máy chủ. Sau đó thêm/xoá người trên trang "Người xem". Lệnh ghi `nhat_ky` như mọi
thay đổi khác, người thực hiện = "cli:<user hệ điều hành>".
"""
from __future__ import annotations

import argparse
import getpass
import sys

from dashboard import kho
from dashboard import nhap_lieu as NL


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m dashboard.quan_tri",
                                description="Quản trị dashboard lắng nghe MXH")
    sub = p.add_subparsers(dest="lenh", required=True)
    t = sub.add_parser("them-nguoi", help="thêm người xem hoặc đổi vai trò")
    t.add_argument("email")
    t.add_argument("vai_tro", choices=sorted(NL.VAI_TRO))
    sub.add_parser("ds-nguoi", help="liệt kê người xem")
    a = p.parse_args(argv)
    try:
        if a.lenh == "them-nguoi":
            email = NL.email(a.email)
            kho.luu_nguoi_xem(f"cli:{getpass.getuser()}", email, NL.vai_tro(a.vai_tro))
            print(f"Đã lưu {email} ({NL.VAI_TRO[a.vai_tro]}).")
        else:
            for x in kho.cac_nguoi_xem():
                print(f"{x['email']}\t{x['vai_tro']}")
    except (NL.LoiNhap, kho.LoiDuLieu, kho.LoiKho) as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
