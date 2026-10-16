"""Lọc LẠI bình luận ĐÃ có trong kho lắng nghe theo luật spam mới (16/10/2026) — không gọi AI.

Rà kho 15/10/2026: 119 bình luận spam affiliate ("𝐃𝐚́𝐧 𝐦𝐚𝐱 … 𝐬𝐨̣̂𝐩-𝐩𝐢𝐢 … AHS-WCM-DQN", "CJW-UJK-A88AH
xóa 88 rồi zán cam ah") lọt bộ lọc, 34 nằm trong thảo luận sạch. Luật mới trong `loc_rac` chỉ áp
cho bình luận cào từ nay; script này áp cho bình luận đã có:
  1. luật từng bình luận (`loc_rac.ly_do_spam`, gồm `affiliate_dan_ma`) cho dòng hop_le / trung;
  2. luật cấp bài (`loc_rac.affiliate_hang_loat`): ≥ 5 tài khoản có mã giới thiệu / chữ kiểu cách
     dưới cùng một bài trong 48 giờ.
Chỉ HẠ nhãn hop_le / trung → spam và xoá sắc thái + chủ đề của dòng đó (như seeding); không bao
giờ nâng nhãn, không gán lại nhãn AI. `cap_nhat_cuoi` = now() để BigQuery đẩy lại dòng đã đổi.

    sudo -u mark /opt/mark/hermes-agent/venv/bin/python scripts/lang_nghe_loc_lai.py   # xem trước
    … scripts/lang_nghe_loc_lai.py --du-an hapas --mau 10
    … scripts/lang_nghe_loc_lai.py --ap-dung        # ghi, MỘT giao dịch cho mọi dự án

Chạy ở thư mục gốc repo của Mark (/opt/mark/app). Kết nối như Mark (`lang_nghe_db.ket_noi`: Unix
socket + peer, `LANG_NGHE_DSN` — lấy từ môi trường, không có thì từ `.env` cạnh repo, mặc định
`dbname=lang_nghe`). Mẫu in ra đã CHE tác giả (mã băm ngắn, không in tên người bình luận). Dashboard
thấy số mới sau ≤ 1 phút (bộ nhớ đệm).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import os
import pathlib
import sys

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

import lang_nghe_db as K
import loc_rac

#: Nhãn được phép hạ thành spam. Không đụng it_noi_dung / seeding / thuong_hieu / spam sẵn có.
HA_DUOC = ("hop_le", "trung")
#: Spam affiliate đã có vẫn đọc: luật cấp bài đếm chúng vào cùng một đợt.
_LY_DO_AFF = ("affiliate_dan_ma", "affiliate_hang_loat")
CHU_DE_MUA = "Giá/mua ở đâu/ý định mua"


def _dsn_tu_env_file() -> None:
    """Mark đặt `LANG_NGHE_DSN` trong `.env` (deploy/lang-nghe/README.md §3): chỉ đọc ĐÚNG khoá đó,
    không nạp các bí mật khác vào tiến trình."""
    if os.environ.get("LANG_NGHE_DSN"):
        return
    tep = GOC / ".env"
    if not tep.exists():
        return
    for dong in tep.read_text(encoding="utf-8", errors="replace").splitlines():
        k, _, v = dong.partition("=")
        if k.strip() == "LANG_NGHE_DSN" and v.strip():
            os.environ["LANG_NGHE_DSN"] = v.strip()
            return


def ke_hoach(rows: list[dict], thuong_hieu: list[str] | tuple = ()) -> list[dict]:
    """THUẦN (kiểm bằng bài thử). `rows` = bình luận của MỘT dự án (khoa_bai, ma, tac_gia,
    noi_dung, luc, loai, ly_do_loc, cua_thuong_hieu, chu_de). -> các dòng cần đổi:
    [{khoa_bai, ma, cu, ly_do, tac_gia, noi_dung, chu_de}], chỉ hop_le / trung → spam."""
    doi: dict[tuple, dict] = {}
    for r in rows:
        if r.get("loai") not in HA_DUOC or r.get("cua_thuong_hieu"):
            continue
        ly_do = loc_rac.ly_do_spam(r.get("noi_dung") or "", thuong_hieu)
        if ly_do:
            doi[(r["khoa_bai"], r["ma"])] = {**_tom(r), "ly_do": ly_do}
    # Luật cấp bài đếm cả dòng vừa hạ ở bước 1 (cùng một đợt) — dòng đó mang nhãn spam nên không
    # bị trả lại lần nữa.
    tam = [dict(r, loai="spam") if (r["khoa_bai"], r["ma"]) in doi else r for r in rows]
    theo = {(r["khoa_bai"], r["ma"]): r for r in rows}
    for kb, m in loc_rac.affiliate_hang_loat(tam, ha_duoc=HA_DUOC):
        doi[(kb, m)] = {**_tom(theo[(kb, m)]), "ly_do": "affiliate_hang_loat"}
    return list(doi.values())


def _tom(r: dict) -> dict:
    return {"khoa_bai": r["khoa_bai"], "ma": r["ma"], "cu": r.get("loai"),
            "tac_gia": r.get("tac_gia") or "", "noi_dung": r.get("noi_dung") or "",
            "chu_de": r.get("chu_de")}


def che_tac_gia(ten: str) -> str:
    """Tên người bình luận → mã băm ngắn (phân biệt được tài khoản, không lộ tên)."""
    ten = loc_rac.khoa_tac_gia(ten)
    return "tg-" + hashlib.sha1(ten.encode("utf-8")).hexdigest()[:6] if ten else "tg-?"


def bao_cao(ma: str, so_xet: int, doi: list[dict], mau: int) -> list[str]:
    dem = collections.Counter((x["cu"], x["ly_do"]) for x in doi)
    ra = [f"Dự án {ma}: xét {so_xet} bình luận (hop_le / trung + spam affiliate đã có)"]
    if not doi:
        return ra + ["  Không có dòng nào cần đổi."]
    for (cu, ly_do), n in sorted(dem.items(), key=lambda x: (-x[1], x[0])):
        ra.append(f"  {cu} → spam ({ly_do}): {n}")
    mua = sum(1 for x in doi if x["cu"] == "hop_le" and x["chu_de"] == CHU_DE_MUA)
    ra.append(f"  Tổng: {len(doi)} dòng, {len({che_tac_gia(x['tac_gia']) for x in doi})} tài "
              f"khoản, {len({x['khoa_bai'] for x in doi})} bài; {mua} dòng hop_le đang đếm là "
              f"\"{CHU_DE_MUA}\"")
    if mau:
        ra.append("  Mẫu (tác giả đã che):")
        for x in doi[:mau]:
            nd = " ".join(x["noi_dung"].split())
            ra.append(f"    [{x['ly_do']}] {che_tac_gia(x['tac_gia'])} · {x['khoa_bai'][:40]} · "
                      f"\"{nd[:90]}{'…' if len(nd) > 90 else ''}\"")
    return ra


_SQL_DOC = (
    "SELECT khoa_bai, ma, tac_gia, noi_dung, COALESCE(dang_luc, thay_lan_dau) AS luc, loai, "
    "ly_do_loc, cua_thuong_hieu, chu_de FROM binh_luan WHERE du_an = %s AND "
    "(loai = ANY(%s) OR ly_do_loc = ANY(%s)) ORDER BY khoa_bai, ma")
_SQL_GHI = (
    "UPDATE binh_luan SET loai = 'spam', ly_do_loc = %s, sac_thai = NULL, chu_de = NULL, "
    "cap_nhat_cuoi = now() WHERE du_an = %s AND khoa_bai = %s AND ma = %s AND loai = %s")


def chay(du_an: str | None, ap_dung: bool, mau: int) -> int:
    _dsn_tu_env_file()
    with K.ket_noi() as c:                    # MỘT giao dịch: lỗi giữa chừng thì không ghi gì
        q = "SELECT ma, ten, tu_khoa FROM du_an" + (" WHERE ma = %s" if du_an else "")
        cac = c.execute(q + " ORDER BY ma", (du_an,) if du_an else ()).fetchall()
        if not cac:
            print(f"Không có dự án {du_an!r} trong kho." if du_an else "Kho chưa có dự án nào.")
            return 1
        tong = 0
        for d in cac:
            rows = c.execute(_SQL_DOC, (d["ma"], list(HA_DUOC), list(_LY_DO_AFF))).fetchall()
            doi = ke_hoach(rows, [d["ten"], *(d.get("tu_khoa") or [])])
            print("\n".join(bao_cao(d["ma"], len(rows), doi, mau)))
            if ap_dung:
                for x in doi:
                    tong += c.execute(_SQL_GHI, (x["ly_do"], d["ma"], x["khoa_bai"], x["ma"],
                                                 x["cu"])).rowcount or 0
            else:
                tong += len(doi)
    print(f"Đã ghi {tong} dòng (một giao dịch)." if ap_dung else
          f"XEM TRƯỚC — chưa ghi gì ({tong} dòng sẽ đổi). Thêm --ap-dung để ghi.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Lọc lại bình luận đã có theo luật spam mới "
                                            "(spam affiliate) — không gọi AI.")
    p.add_argument("--du-an", help="chỉ một dự án (mã); mặc định mọi dự án")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="chỉ xem trước (mặc định)")
    g.add_argument("--ap-dung", action="store_true", help="ghi vào kho, một giao dịch")
    p.add_argument("--mau", type=int, default=5, help="số dòng mẫu in mỗi dự án (mặc định 5)")
    a = p.parse_args(argv)
    try:
        return chay(a.du_an, a.ap_dung, max(0, a.mau))
    except K.LoiKho as e:
        print(f"Lỗi kho: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
