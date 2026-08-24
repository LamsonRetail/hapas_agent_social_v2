"""One-time OAuth cho seat Steven — DEVICE CODE (QR / link).

Giống cơ chế của lark-cli: xin device_code + verification_url, hiện QR + link,
bạn quét/đăng nhập BẰNG tài khoản Steven và bấm Đồng ý, rồi tự lấy token
(có refresh_token) và lưu vào .tokens/steven.json. KHÔNG cần redirect URI.

    python authorize.py
"""

from __future__ import annotations

import webbrowser

import lark_client as lark
from config import config


def _print_qr(url: str) -> None:
    try:
        import qrcode  # có sẵn trong venv của Hermes

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception:
        pass  # không có qrcode thì thôi, vẫn có link


def main() -> None:
    print("=" * 54)
    print("   STEVEN-HERMES — XÁC THỰC USER (device-code / QR)")
    print("=" * 54)
    print(f"App: {config.app_id}")
    print("Đang khởi tạo kết nối...\n")

    dev = lark.start_device_authorization()
    url = dev["verification_url"]
    if not url:
        raise SystemExit(f"Không lấy được verification_url. Response: {dev}")

    _print_qr(url)
    print("\n" + "=" * 54)
    print("📲 CÁCH 1: Mở app Lark trên điện thoại → quét QR ở trên.")
    print("🌐 CÁCH 2: Mở link sau trong trình duyệt (ĐĂNG NHẬP BẰNG STEVEN):")
    print(f"   {url}")
    if dev.get("user_code"):
        print(f"   Mã xác nhận (nếu hỏi): {dev['user_code']}")
    print("=" * 54 + "\n")
    print("⏳ Đang chờ bạn bấm Đồng ý trên Lark...")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    t = lark.poll_device_token(dev["device_code"], dev["interval"], dev["expires_in"])
    print("\n✅ XÁC THỰC THÀNH CÔNG!")
    print(f"   name:    {t.get('name') or '(unknown)'}")
    print(f"   open_id: {t.get('open_id') or '(unknown)'}")
    print(f"   scope:   {(t.get('scope') or '(not returned)')}")
    print(f"   Token đã lưu: {config.token_file}")
    print("\n→ Giờ chạy: python run.py  (hoặc double-click start.bat)")


if __name__ == "__main__":
    main()
