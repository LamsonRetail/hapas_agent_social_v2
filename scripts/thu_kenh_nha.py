"""Thử THẬT, chỉ đọc, từng kênh nhà đã nối token (Threads / Instagram / Facebook).

Mỗi kênh: 3 bài mới nhất, tối đa 50 bình luận/bài. KHÔNG tạo sheet, KHÔNG gán nhãn,
KHÔNG in token — chỉ in số bài, số bình luận, tình trạng token.

    python scripts/thu_kenh_nha.py            # mọi kênh có token trong .env
    python scripts/thu_kenh_nha.py instagram  # một kênh

Chạy ở thư mục gốc repo (cạnh .env). Lần đầu chạy sẽ đổi token ngắn hạn sang dài hạn và
lưu vào .tokens/meta_kenh_nha.json.
"""
from __future__ import annotations

import pathlib
import sys
import time

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

import config  # noqa: E402,F401  (nạp .env)
import kenh_nha_meta as M  # noqa: E402


def main() -> int:
    import kenh_nha_tool as K
    xin = [a.lower() for a in sys.argv[1:]] or list(M.KENH)
    bo = {"kenh": xin, "tu": None, "den": None, "bai": {}, "so_bai": 3, "max_bl": 50}
    loi = 0
    for k in xin:
        if M.thieu_cau_hinh(k):
            print(f"{M.TEN[k]}: chưa nối (.env thiếu {M.thieu_cau_hinh(k)})")
            continue
        kq = K._doc_kenh(k, bo, time.monotonic() + 90)
        if kq["loi"]:
            loi += 1
            print(f"{M.TEN[k]}: LỖI — {kq['loi']}")
            continue
        cua_kenh = sum(1 for r in kq["rows"] if r["cua_kenh"])
        tra_loi = sum(1 for r in kq["rows"] if r.get("cap", 1) > 1)
        print(f"{M.TEN[k]} (@{kq.get('tai_khoan')}): {len(kq['bai'])} bài, "
              f"{len(kq['rows'])} bình luận ({tra_loi} trả lời lồng nhau, {cua_kenh} của "
              f"kênh nhà)")
        for b in kq["bai"]:
            print(f"  - {b['ngay']} · {b.get('bl', 0)} bình luận"
                  + (f" / nền tảng báo {b['bao']}" if b.get("bao") is not None else "")
                  + f" · {b.get('trang_thai', '')}")
    for k, v in M.tinh_trang().items():
        print(f"token {M.TEN[k]}: {v['trang_thai']}")
    return 1 if loi else 0


if __name__ == "__main__":
    sys.exit(main())
