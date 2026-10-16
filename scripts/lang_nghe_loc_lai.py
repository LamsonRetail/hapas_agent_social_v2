"""Lọc LẠI bình luận ĐÃ có trong kho lắng nghe theo luật spam mới (16/10/2026) — không gọi AI.

Rà kho 15/10/2026: 119 bình luận spam affiliate ("𝐃𝐚́𝐧 𝐦𝐚𝐱 … 𝐬𝐨̣̂𝐩-𝐩𝐢𝐢 … AHS-WCM-DQN", "CJW-UJK-A88AH
xóa 88 rồi zán cam ah") lọt bộ lọc, 34 nằm trong thảo luận sạch. Luật mới trong `loc_rac` chỉ áp
cho bình luận cào từ nay; script này áp cho bình luận đã có:
  1. luật từng bình luận (`loc_rac.ly_do_spam`, gồm `affiliate_dan_ma`) cho dòng hop_le / trung;
  2. luật cấp bài (`loc_rac.affiliate_hang_loat`): ≥ 5 tài khoản có mã giới thiệu (hoặc chữ kiểu
     cách + lời dặn/tên sàn) dưới cùng một bài trong 48 giờ theo giờ đăng; mã có trong bài/bình
     luận của thương hiệu không tính.
Chỉ HẠ nhãn hop_le / trung → spam và xoá sắc thái + chủ đề của dòng đó (như seeding); không bao
giờ nâng nhãn, không gán lại nhãn AI. `cap_nhat_cuoi` = now() để BigQuery đẩy lại dòng đã đổi.

    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_loc_lai.py                        # xem trước (chỉ đọc)
    sudo -u mark $PY scripts/lang_nghe_loc_lai.py --du-an hapas --mau 10
    sudo -u mark $PY scripts/lang_nghe_loc_lai.py --ap-dung --sao-luu /opt/mark/loc_lai-1610.json
    sudo -u mark $PY scripts/lang_nghe_loc_lai.py --hoan-tac /opt/mark/loc_lai-1610.json

`--ap-dung` BẮT BUỘC `--sao-luu <tệp>`: trước khi sửa, ghi nhãn CŨ (loai, ly_do_loc, sac_thai,
chu_de) của mọi dòng sắp đổi vào tệp JSON (không ghi đè tệp có sẵn; không chứa nội dung hay tên
người bình luận). `--hoan-tac <tệp>` trả lại đúng nhãn cũ trong MỘT giao dịch, chỉ ở dòng còn mang
nhãn script đã đặt (người/luật khác đã sửa sau đó thì để nguyên). Xem trước chạy trong giao dịch
READ ONLY.

Chạy ở thư mục gốc repo của Mark (/opt/mark/app). Kết nối như Mark (`lang_nghe_db.ket_noi`: Unix
socket + peer, `LANG_NGHE_DSN` — lấy từ môi trường, không có thì từ `.env` cạnh repo, mặc định
`dbname=lang_nghe`). Mẫu in ra đã CHE tác giả (mã băm ngắn). Dashboard thấy số mới sau ≤ 1 phút.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
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


def ke_hoach(rows: list[dict], thuong_hieu: list[str] | tuple = (),
             noi_dung_bai: dict | None = None) -> list[dict]:
    """THUẦN (kiểm bằng bài thử). `rows` = bình luận của MỘT dự án (khoa_bai, ma, tac_gia,
    noi_dung, luc = giờ đăng, loai, ly_do_loc, cua_thuong_hieu, sac_thai, chu_de), kể cả bình luận
    của thương hiệu (chỉ để biết mã nào là của brand); `noi_dung_bai` = {khoá bài: nội dung bài}.
    -> các dòng cần đổi: [{khoa_bai, ma, cu, ly_do_cu, sac_thai_cu, chu_de, ly_do, tac_gia,
    noi_dung}], chỉ hop_le / trung → spam."""
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
    for kb, m in loc_rac.affiliate_hang_loat(tam, ha_duoc=HA_DUOC, thuong_hieu=thuong_hieu,
                                             noi_dung_bai=noi_dung_bai):
        doi[(kb, m)] = {**_tom(theo[(kb, m)]), "ly_do": "affiliate_hang_loat"}
    return list(doi.values())


def _tom(r: dict) -> dict:
    return {"khoa_bai": r["khoa_bai"], "ma": r["ma"], "cu": r.get("loai"),
            "ly_do_cu": r.get("ly_do_loc"), "sac_thai_cu": r.get("sac_thai"),
            "chu_de": r.get("chu_de"), "tac_gia": r.get("tac_gia") or "",
            "noi_dung": r.get("noi_dung") or ""}


def che_tac_gia(ten: str) -> str:
    """Tên người bình luận → mã băm ngắn (phân biệt được tài khoản, không lộ tên)."""
    ten = loc_rac.khoa_tac_gia(ten)
    return "tg-" + hashlib.sha1(ten.encode("utf-8")).hexdigest()[:6] if ten else "tg-?"


def _dong_mau(x: dict) -> str:
    nd = " ".join(x["noi_dung"].split())
    return (f"    [{x['ly_do']}] {che_tac_gia(x['tac_gia'])} · {x['khoa_bai'][:40]} · "
            f"\"{nd[:90]}{'…' if len(nd) > 90 else ''}\"")


def bao_cao(ma: str, so_xet: int, doi: list[dict], mau: int) -> list[str]:
    dem = collections.Counter((x["cu"], x["ly_do"]) for x in doi)
    ra = [(f"Dự án {ma}: xét {so_xet} bình luận (hop_le / trung + spam affiliate đã có + của "
           "thương hiệu)")]
    if not doi:
        return ra + ["  Không có dòng nào cần đổi."]
    for (cu, ly_do), n in sorted(dem.items(), key=lambda x: (-x[1], x[0])):
        ra.append(f"  {cu} → spam ({ly_do}): {n}")
    mua = sum(1 for x in doi if x["cu"] == "hop_le" and x["chu_de"] == CHU_DE_MUA)
    ra.append(f"  Tổng: {len(doi)} dòng, {len({che_tac_gia(x['tac_gia']) for x in doi})} tài "
              f"khoản, {len({x['khoa_bai'] for x in doi})} bài; {mua} dòng hop_le đang đếm là "
              f"\"{CHU_DE_MUA}\"")
    if not mau:
        return ra
    # Hàng loạt mà KHÔNG có mã in hoa nối gạch (chỉ chữ kiểu cách) là phần dễ nhầm nhất: in riêng
    # để người duyệt đọc tay trước khi --ap-dung.
    khong_ma = [x for x in doi if x["ly_do"] == "affiliate_hang_loat"
                and not loc_rac.ma_gioi_thieu(x["noi_dung"])]
    con = [x for x in doi if x not in khong_ma]
    if con:
        ra.append(f"  Mẫu ({min(mau, len(con))}/{len(con)}, tác giả đã che):")
        ra += [_dong_mau(x) for x in con[:mau]]
    if khong_ma:
        ra.append(f"  CẦN ĐỌC TAY — hàng loạt không có mã nối gạch "
                  f"({min(mau, len(khong_ma))}/{len(khong_ma)}):")
        ra += [_dong_mau(x) for x in khong_ma[:mau]]
    return ra


_SQL_DOC = (
    "SELECT khoa_bai, ma, tac_gia, noi_dung, dang_luc AS luc, loai, ly_do_loc, cua_thuong_hieu, "
    "sac_thai, chu_de FROM binh_luan WHERE du_an = %s AND (loai = ANY(%s) OR ly_do_loc = ANY(%s) "
    "OR loai = 'thuong_hieu' OR cua_thuong_hieu) ORDER BY khoa_bai, ma")
_SQL_BAI = "SELECT khoa, noi_dung FROM bai WHERE du_an = %s"
_SQL_GHI = (
    "UPDATE binh_luan SET loai = 'spam', ly_do_loc = %s, sac_thai = NULL, chu_de = NULL, "
    "cap_nhat_cuoi = now() WHERE du_an = %s AND khoa_bai = %s AND ma = %s AND loai = %s")
_SQL_HOAN = (
    "UPDATE binh_luan SET loai = %s, ly_do_loc = %s, sac_thai = %s, chu_de = %s, "
    "cap_nhat_cuoi = now() WHERE du_an = %s AND khoa_bai = %s AND ma = %s AND loai = 'spam' "
    "AND ly_do_loc = %s")


def _ghi_sao_luu(tep: pathlib.Path, dong: list[dict]) -> None:
    """Tệp hoàn tác: tạo MỚI (không ghi đè), quyền 600, ghi xong + fsync rồi mới sửa kho."""
    noi_dung = json.dumps({"tao_luc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           "script": "scripts/lang_nghe_loc_lai.py", "so_dong": len(dong),
                           "dong": dong}, ensure_ascii=False, indent=1)
    fd = os.open(tep, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(noi_dung)
        f.flush()
        os.fsync(f.fileno())


def chay(du_an: str | None, ap_dung: bool, mau: int, sao_luu: str | None = None) -> int:
    _dsn_tu_env_file()
    if ap_dung and pathlib.Path(sao_luu or "").exists():
        print(f"Tệp sao lưu {sao_luu} đã có — chọn tên khác (không ghi đè bản hoàn tác cũ).",
              file=sys.stderr)
        return 2
    with K.ket_noi() as c:                    # MỘT giao dịch: lỗi giữa chừng thì không ghi gì
        if not ap_dung:
            c.execute("SET TRANSACTION READ ONLY")
        q = "SELECT ma, ten, tu_khoa FROM du_an" + (" WHERE ma = %s" if du_an else "")
        cac = c.execute(q + " ORDER BY ma", (du_an,) if du_an else ()).fetchall()
        if not cac:
            print(f"Không có dự án {du_an!r} trong kho." if du_an else "Kho chưa có dự án nào.")
            return 1
        ke: list[tuple[str, dict]] = []
        for d in cac:
            rows = c.execute(_SQL_DOC, (d["ma"], list(HA_DUOC), list(_LY_DO_AFF))).fetchall()
            bai = {r["khoa"]: r["noi_dung"] for r in c.execute(_SQL_BAI, (d["ma"],)).fetchall()}
            doi = ke_hoach(rows, [d["ten"], *(d.get("tu_khoa") or [])], bai)
            print("\n".join(bao_cao(d["ma"], len(rows), doi, mau)))
            ke += [(d["ma"], x) for x in doi]
        if not ap_dung:
            print(f"XEM TRƯỚC (chỉ đọc) — chưa ghi gì ({len(ke)} dòng sẽ đổi). Thêm --ap-dung "
                  "--sao-luu <tệp> để ghi.")
            return 0
        _ghi_sao_luu(pathlib.Path(sao_luu), [
            {"du_an": ma, "khoa_bai": x["khoa_bai"], "ma": x["ma"], "loai": x["cu"],
             "ly_do_loc": x["ly_do_cu"], "sac_thai": x["sac_thai_cu"], "chu_de": x["chu_de"],
             "ly_do_moi": x["ly_do"]} for ma, x in ke])
        tong = sum(c.execute(_SQL_GHI, (x["ly_do"], ma, x["khoa_bai"], x["ma"], x["cu"])).rowcount
                   or 0 for ma, x in ke)
    print(f"Đã ghi {tong} dòng (một giao dịch). Hoàn tác: --hoan-tac {sao_luu}")
    return 0


def hoan_tac(tep: str) -> int:
    """Trả nhãn cũ từ tệp sao lưu, MỘT giao dịch, chỉ dòng còn đúng nhãn script đã đặt."""
    _dsn_tu_env_file()
    dong = json.loads(pathlib.Path(tep).read_text(encoding="utf-8"))["dong"]
    with K.ket_noi() as c:
        tra = sum(c.execute(_SQL_HOAN, (x["loai"], x["ly_do_loc"], x["sac_thai"], x["chu_de"],
                                        x["du_an"], x["khoa_bai"], x["ma"], x["ly_do_moi"])).rowcount
                  or 0 for x in dong)
    print(f"Đã trả nhãn cũ cho {tra}/{len(dong)} dòng (một giao dịch); {len(dong) - tra} dòng đã "
          "bị sửa sau đó nên để nguyên.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Lọc lại bình luận đã có theo luật spam mới "
                                            "(spam affiliate) — không gọi AI.")
    p.add_argument("--du-an", help="chỉ một dự án (mã); mặc định mọi dự án")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="chỉ xem trước, chỉ đọc (mặc định)")
    g.add_argument("--ap-dung", action="store_true", help="ghi vào kho, một giao dịch")
    g.add_argument("--hoan-tac", metavar="TỆP", help="trả nhãn cũ từ tệp --sao-luu")
    p.add_argument("--sao-luu", metavar="TỆP", help="tệp JSON hoàn tác (bắt buộc với --ap-dung)")
    p.add_argument("--mau", type=int, default=5, help="số dòng mẫu in mỗi nhóm (mặc định 5)")
    a = p.parse_args(argv)
    if a.ap_dung and not a.sao_luu:
        p.error("--ap-dung cần --sao-luu <tệp> (để hoàn tác được)")
    try:
        if a.hoan_tac:
            return hoan_tac(a.hoan_tac)
        return chay(a.du_an, a.ap_dung, max(0, a.mau), a.sao_luu)
    except K.LoiKho as e:
        print(f"Lỗi kho: {e}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as e:     # tệp sao lưu / hoàn tác: kho không bị sửa
        print(f"Lỗi tệp ({type(e).__name__}): {e} — kho KHÔNG bị sửa.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
