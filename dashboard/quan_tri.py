"""Lệnh quản trị chạy trên VPS (user hệ điều hành `lang_nghe_web`, peer auth):

    python -m dashboard.quan_tri quan-tri <email> [--bo]          # cấp / bỏ quản trị viên
    python -m dashboard.quan_tri them-quyen <email> <bên> <xem|quan_ly>
    python -m dashboard.quan_tri bo-quyen <email> <bên>
    python -m dashboard.quan_tri them-ben <mã> <tên>
    python -m dashboard.quan_tri ds-nguoi
    python -m dashboard.quan_tri them-nguoi <email> <xem|quan_ly>  # lệnh CŨ: = them-quyen … hapas

Vì sao cần: dashboard chỉ cho người có quyền vào, nên quản trị viên ĐẦU TIÊN phải đặt từ máy chủ
(schema.sql 19/10/2026 đã đặt sẵn thamnt + thienlq khi chưa có ai). Sau đó sửa trên trang
"Quản trị". Lệnh qua mọi luật của quản lý bên (người chạy đã có quyền trên máy chủ) TRỪ luật
"còn ít nhất một quản trị viên"; ghi `nhat_ky` như mọi thay đổi khác, người thực hiện =
"cli:<user hệ điều hành>".
"""
from __future__ import annotations

import argparse
import getpass
import sys

from dashboard import kho
from dashboard import nhap_lieu as NL
from dashboard import phan_quyen as PQ


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m dashboard.quan_tri",
                                description="Quản trị dashboard Social Listening")
    sub = p.add_subparsers(dest="lenh", required=True)
    t = sub.add_parser("quan-tri", help="cấp (hoặc --bo: bỏ) quyền quản trị viên")
    t.add_argument("email")
    t.add_argument("--bo", action="store_true")
    t = sub.add_parser("them-quyen", help="thêm người vào bên hoặc đổi vai trò ở bên")
    t.add_argument("email")
    t.add_argument("don_vi")
    t.add_argument("vai_tro", choices=sorted(NL.VAI_TRO))
    t = sub.add_parser("bo-quyen", help="bỏ quyền của người ở một bên")
    t.add_argument("email")
    t.add_argument("don_vi")
    t = sub.add_parser("them-ben", help="tạo bên mới")
    t.add_argument("ma")
    t.add_argument("ten")
    t = sub.add_parser("them-nguoi", help="(cũ) = them-quyen <email> hapas <vai trò>")
    t.add_argument("email")
    t.add_argument("vai_tro", choices=sorted(NL.VAI_TRO))
    sub.add_parser("ds-nguoi", help="liệt kê người xem + quyền theo bên")
    a = p.parse_args(argv)
    ai = f"cli:{getpass.getuser()}"
    try:
        if a.lenh == "quan-tri":
            email = NL.email(a.email)
            kho.dat_quan_tri(ai, email, not a.bo, he_thong=True)
            print(f"Đã {'bỏ' if a.bo else 'cấp'} quyền quản trị viên: {email}.")
        elif a.lenh in ("them-quyen", "them-nguoi"):
            email = NL.email(a.email)
            ben = NL.ma_don_vi(getattr(a, "don_vi", "hapas"))
            kho.luu_quyen(ai, email, ben, NL.vai_tro(a.vai_tro), he_thong=True)
            print(f"Đã lưu {email} ({ben}: {NL.VAI_TRO[a.vai_tro]}).")
        elif a.lenh == "bo-quyen":
            email = NL.email(a.email)
            het = kho.xoa_quyen(ai, email, NL.ma_don_vi(a.don_vi), he_thong=True)
            print(f"Đã bỏ quyền của {email} ở bên {a.don_vi}"
                  + (" — không còn quyền nào nên đã xoá khỏi danh sách." if het else "."))
        elif a.lenh == "them-ben":
            ten = NL.sach(a.ten, 200)
            if not ten:
                raise NL.LoiNhap("Chưa nhập tên bên.")
            kho.them_don_vi(ai, NL.ma_don_vi(a.ma), ten, he_thong=True)
            print(f"Đã tạo bên {ten} ({a.ma}).")
        else:
            for x in kho.cac_nguoi_xem():
                q = {"la_quan_tri": x.get("la_quan_tri"), "ben": x.get("quyen") or {}}
                print(f"{x['email']}\t{PQ.nhan_vai(q)}")
    except (NL.LoiNhap, kho.LoiDuLieu, kho.LoiKho) as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
