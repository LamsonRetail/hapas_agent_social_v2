"""Gán lại nhãn BÀI trong kho `lang_nghe` bằng prompt bài mới — script MỘT LẦN (17/10/2026).

Vì sao: tập đánh giá 17/10 (60 bài thật, nhãn chuẩn do người chấm) — bài Báo & Web chấm theo 400
ký tự đầu nên bài báo về quảng cáo GÂY TRANH CÃI ra "Trung lập" (0/2 tiêu cực), bài khen brand ra
"Trung lập". Prompt mới (`phan_loai.phan_loai_bai`: đọc mọi đoạn nhắc brand, sắc thái hướng về
brand, cờ rủi ro) chỉ tự áp cho bài MỚI; bài cũ cần chạy script này. Bình luận cũ gán lại bằng
`scripts/lang_nghe_gan_lai.py <dự án> --buoc b --tat-ca` (đã dùng prompt bình luận mới).

Chọn bài: mặc định mọi bài web (`nen_tang = 'web'`); `--tat-ca`: mọi bài KHÔNG thuộc kênh nhà
(bài kênh nhà không vào sắc thái/chủ đề của dashboard).

An toàn (cùng cách `lang_nghe_gan_lai.py`):
  • Mặc định CHẠY THỬ: một giao dịch READ ONLY, không gọi model, không ghi; in số bài và ước tính
    số lượt gọi model (lô `phan_loai._LO_BAI`). `--thu N` gọi model cho tối đa N bài để xem trước.
  • `--ap-dung --sao-luu <tệp>`: ghi tệp hoàn tác TRƯỚC, rồi mỗi lô UPDATE trong một giao dịch, chỉ
    sửa bài mà nhãn hiện tại còn y như lúc đọc. `cap_nhat_cuoi` dời để đồng bộ BigQuery lấy lại
    (`lang_nghe_db.DOI_MOC_BAI_SQL`: trừ bài YouTube ≤ 14 ngày chưa làm mới số hôm nay).
  • `--hoan-tac <tệp>`: trả nhãn cũ cho bài CÒN mang đúng nhãn script đã ghi.
  • Gọi model TUẦN TỰ từng lô (quota dùng chung với bot chính).

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_gan_nhan_bai.py hapas                 # chạy thử
    sudo -u mark $PY scripts/lang_nghe_gan_nhan_bai.py hapas --thu 14        # xem trước
    sudo -u mark $PY scripts/lang_nghe_gan_nhan_bai.py hapas --ap-dung --sao-luu .audit/nhan-bai-1710.jsonl
    sudo -u mark $PY scripts/lang_nghe_gan_nhan_bai.py hapas --hoan-tac .audit/nhan-bai-1710.jsonl
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import pathlib
import sys

GOC = pathlib.Path(__file__).resolve().parent.parent
for p in (str(GOC), str(GOC / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from lang_nghe_gan_lai import _chuan_bi_model

import lang_nghe_db as K
import phan_loai as P

# timezone.utc, không phải datetime.UTC: chạy được cả Python 3.10.
UTC = datetime.timezone.utc  # noqa: UP017
LO = P._LO_BAI
HAN_LO_GIAY = 180.0
COT = ("sac_thai", "chu_de")

SQL_CHI_DOC = "SET TRANSACTION READ ONLY"
SQL_DU_AN = "/* nb:du_an */ SELECT ma, ten, tu_khoa FROM du_an WHERE ma = %s"
SQL_BAI = (
    "/* nb:bai */ SELECT b.khoa, b.nen_tang, b.tai_khoan, b.tac_gia, b.noi_dung, b.hashtag, "
    "b.kieu_trang, b.sac_thai, b.chu_de, (n.loai = 'kenh_nha') AS kenh_nha FROM bai b "
    "LEFT JOIN nguon n ON n.id = b.nguon_id WHERE b.du_an = %s "
    "AND btrim(b.noi_dung || ' ' || COALESCE(b.hashtag, '')) <> '' ORDER BY b.khoa")
SQL_SUA = (
    f"/* nb:sua */ UPDATE bai SET sac_thai = %s, chu_de = %s, cap_nhat_cuoi = {K.DOI_MOC_BAI_SQL} "
    "WHERE du_an = %s AND khoa = %s AND sac_thai IS NOT DISTINCT FROM %s "
    "AND chu_de IS NOT DISTINCT FROM %s")


def doc_tep_hoan_tac(tep: str) -> tuple[dict, list[dict]]:
    dau, dong = {}, []
    with open(tep, encoding="utf-8") as f:
        for i, x in enumerate(f):
            if not x.strip():
                continue
            r = json.loads(x)
            if i == 0 and r.get("loai_dong") == "dau":
                dau = r
            elif all(k in r for k in ("khoa", "cu", "moi")):
                dong.append(r)
    return dau, dong


def doc_kho(ma: str) -> tuple[dict | None, list[dict]]:
    with K.ket_noi() as c:
        c.execute(SQL_CHI_DOC)
        du_an = c.execute(SQL_DU_AN, (ma,)).fetchone()
        if not du_an:
            return None, []
        return du_an, list(c.execute(SQL_BAI, (ma,)).fetchall())


def chon(rows: list[dict], tat_ca: bool = False) -> list[dict]:
    return [r for r in rows if not r.get("kenh_nha")
            and (tat_ca or r.get("nen_tang") == "web")]


def uoc_luot_model(rows: list[dict]) -> int:
    return math.ceil(len(rows) / LO)


def gan_nhan(du_an: dict, lo: list[dict]) -> tuple[list[dict], dict]:
    """-> (bài có nhãn mới KHÁC nhãn cũ, thống kê). Bài chưa gán được giữ nhãn cũ."""
    tt: dict = {}
    brand = ", ".join(dict.fromkeys(str(x) for x in P.thuong_hieu_du_an(du_an) if str(x).strip()))
    nhan = P.phan_loai_bai(lo, brand, HAN_LO_GIAY, tt, song_song=1)
    doi, dem = [], {"chua_gan": 0, "khong_doi": 0, "rui_ro": 0}
    for r, x in zip(lo, nhan):
        if not x:
            dem["chua_gan"] += 1
            continue
        dem["rui_ro"] += int(x[2])
        cu = {k: r.get(k) for k in COT}
        moi = {"sac_thai": x[0], "chu_de": x[1]}
        if moi == cu:
            dem["khong_doi"] += 1
            continue
        doi.append({"khoa": r["khoa"], "nen_tang": r.get("nen_tang"),
                    "noi_dung": r.get("noi_dung") or "", "cu": cu, "moi": moi,
                    "rui_ro": bool(x[2])})
    return doi, {**dem, "trang_thai": tt.get("trang_thai") or ""}


def ghi_lo(ma: str, lo: list[dict], so_luu, nguoc: bool = False) -> tuple[int, int]:
    """Một lô trong MỘT giao dịch; `so_luu` nhận dòng TRƯỚC khi UPDATE. -> (đã sửa, bỏ qua)."""
    if not lo:
        return 0, 0
    if so_luu is not None:
        for d in lo:
            so_luu.write(json.dumps({"du_an": ma, "khoa": d["khoa"], "cu": d["cu"],
                                     "moi": d["moi"]}, ensure_ascii=False) + "\n")
        so_luu.flush()
        os.fsync(so_luu.fileno())
    sua = 0
    with K.ket_noi() as c:
        for d in lo:
            dat, kiem = (d["cu"], d["moi"]) if nguoc else (d["moi"], d["cu"])
            sua += int(c.execute(SQL_SUA, (dat["sac_thai"], dat["chu_de"], ma, d["khoa"],
                                           kiem["sac_thai"], kiem["chu_de"])).rowcount or 0)
    return sua, len(lo) - sua


def _mau(d: dict) -> str:
    t = " ".join(str(d.get("noi_dung") or "").split())
    t = t if len(t) <= 90 else t[:89] + "…"
    s = f"  [{d.get('nen_tang')}] \"{t}\" ({d['cu'].get('sac_thai') or '—'} / " \
        f"{d['cu'].get('chu_de') or '—'}"
    if d.get("moi"):
        s += f" → {d['moi']['sac_thai']} / {d['moi']['chu_de']}" + (" · RỦI RO" if d.get("rui_ro")
                                                                   else "")
    return s + ")"


def chay(ns, in_ra=print) -> int:
    ma = ns.du_an.strip().lower()
    if ns.hoan_tac:
        dau, dong = doc_tep_hoan_tac(ns.hoan_tac)
        dong = [d for d in reversed(dong) if d.get("du_an", ma) == ma]
        if dau.get("du_an") and dau["du_an"] != ma:
            in_ra(f"Tệp hoàn tác của dự án '{dau['du_an']}', không phải '{ma}' — dừng.")
            return 2
        sua = bo = 0
        for i in range(0, len(dong), LO):
            a, b = ghi_lo(ma, dong[i:i + LO], None, nguoc=True)
            sua, bo = sua + a, bo + b
        in_ra(f"Hoàn tác {ma}: trả lại {sua}/{len(dong)} bài; {bo} bài bỏ qua (đã đổi sau lần "
              "gán lại — không đè).")
        return 0
    if ns.ap_dung and not ns.sao_luu:
        in_ra("--ap-dung cần --sao-luu <tệp> (tệp hoàn tác ghi TRƯỚC khi sửa kho).")
        return 2
    if ns.ap_dung and os.path.exists(ns.sao_luu):
        in_ra(f"Tệp {ns.sao_luu} đã có — chọn tên khác (không ghi đè tệp hoàn tác cũ).")
        return 2
    du_an, rows = doc_kho(ma)
    if not du_an:
        in_ra(f"Không có dự án '{ma}' trong kho.")
        return 2
    ds = chon(rows, ns.tat_ca)
    in_ra(f"Dự án {ma} — {'ÁP DỤNG' if ns.ap_dung else 'CHẠY THỬ (giao dịch chỉ đọc, không ghi gì)'}.")
    in_ra(f"Gán lại nhãn {len(ds)} bài ({'mọi bài ngoài kênh nhà' if ns.tat_ca else 'bài web'}); "
          f"ước tính {uoc_luot_model(ds)} lượt gọi model (lô {LO}, tuần tự).")
    if not ns.ap_dung:
        thu = ds[:min(max(0, ns.thu), LO)]
        if thu:
            _chuan_bi_model()
            doi, dem = gan_nhan(du_an, thu)
            in_ra(f"Xem trước {len(thu)} bài (KHÔNG ghi): {len(doi)} đổi nhãn, {dem['khong_doi']} "
                  f"giữ nguyên, {dem['chua_gan']} chưa gán được, {dem['rui_ro']} có cờ rủi ro "
                  f"({dem['trang_thai'] or '—'}).")
            for d in doi[:ns.mau]:
                in_ra(_mau(d))
        in_ra("Không ghi gì. Ghi thật: thêm --ap-dung --sao-luu <tệp hoàn tác>.")
        return 0
    with open(ns.sao_luu, "x", encoding="utf-8") as so_luu:
        so_luu.write(json.dumps({
            "loai_dong": "dau", "du_an": ma, "phien_ban": 1, "bang": "bai",
            "luc": datetime.datetime.now(UTC).isoformat(timespec="seconds"),
            "tat_ca": bool(ns.tat_ca)}, ensure_ascii=False) + "\n")
        so_luu.flush()
        _chuan_bi_model()
        sua = bo = chua = giu = 0
        cac_lo = [ds[i:i + LO] for i in range(0, len(ds), LO)]
        for j, lo in enumerate(cac_lo, 1):
            doi, dem = gan_nhan(du_an, lo)
            x, y = ghi_lo(ma, doi, so_luu)
            sua, bo, chua, giu = sua + x, bo + y, chua + dem["chua_gan"], giu + dem["khong_doi"]
            in_ra(f"    lô {j}/{len(cac_lo)}: {len(lo)} bài, đổi {x}, giữ {dem['khong_doi']}, "
                  f"chưa gán {dem['chua_gan']}, bỏ qua {y} ({dem['trang_thai'] or '—'})")
        in_ra(f"Đã sửa {sua} bài; giữ nguyên {giu}; chưa gán được {chua} (giữ nhãn cũ); bỏ qua "
              f"{bo}. Tệp hoàn tác: {ns.sao_luu}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gán lại nhãn bài trong kho lang_nghe bằng prompt "
                                             "bài mới (mặc định chạy thử, không ghi).")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("--dry-run", action="store_true", help="chạy thử (mặc định)")
    ap.add_argument("--ap-dung", action="store_true", help="ghi thật (cần --sao-luu)")
    ap.add_argument("--sao-luu", metavar="TEP", help="tệp hoàn tác JSONL (tạo mới)")
    ap.add_argument("--hoan-tac", metavar="TEP", help="trả lại nhãn cũ từ tệp hoàn tác")
    ap.add_argument("--tat-ca", action="store_true", help="mọi bài ngoài kênh nhà, không chỉ web")
    ap.add_argument("--thu", type=int, default=0, metavar="N",
                    help=f"chạy thử: gọi model cho tối đa N bài (≤ {LO}) để xem trước")
    ap.add_argument("--mau", type=int, default=8, help="số bài mẫu in ra")
    ns = ap.parse_args(argv)
    if ns.dry_run and (ns.ap_dung or ns.hoan_tac):
        ap.error("--dry-run không đi cùng --ap-dung / --hoan-tac")
    if ns.ap_dung and ns.hoan_tac:
        ap.error("--ap-dung và --hoan-tac là hai việc riêng")
    return chay(ns)


if __name__ == "__main__":
    sys.exit(main())
