"""Gắn lại `nguon_id` cho bài KÊNH NHÀ ghi như bài tìm theo từ khoá — script MỘT LẦN (18/10/2026).

Vì sao: lượt nạp raw 14 (18/10/2026 17:30–17:41, raw `hapasglobal` của Kompa) cho bài fanpage nhà
đi CẢ đường từ khoá lẫn đường nguồn (`scripts/lang_nghe_nap_raw.py` loại theo `id()` của dict tạo
lại — đã sửa). Đường từ khoá ghi trước (`kieu_quet = tu_khoa`, `nguon_id` NULL), đường nguồn thấy
"103 bài đã có, 19 mới" và chỉ nâng số: bài nhà thành "External channel", lọt sắc thái / chủ đề.
Lỗi cùng dạng có thể có từ TRƯỚC — đường từ khoá Facebook của `/theodoi` không gắn được nguồn
(`theo_doi._dinh_danh_tai_khoan` trả None với Facebook) — nên script xét MỌI bài khớp, không chỉ
lượt 14, và in theo `luot_dau`.

Chọn bài: bài của dự án có `nguon_id` NULL, nền tảng có nguồn kênh nhà (`nguon.loai = kenh_nha`),
mà chủ bài (`tai_khoan`) hoặc link khớp ĐÚNG MỘT nguồn kênh nhà theo luật của script nạp raw
(`lang_nghe_nap_raw.dau_chu_bai`, như `/theodoi`): tài khoản = định danh nguồn, tên trang trong
link, id trang (id trong định danh nguồn + id trang trong link bài ĐÃ gắn nguồn đó — link thedoor
`/<id trang>/posts/…`). Không dùng tên hiển thị. Khớp > 1 nguồn: để nguyên, in ra. Bài đã có
`nguon_id`: không đụng.

Sửa: `nguon_id` = nguồn đó, `kieu_quet = 'theo_doi'` (như lượt `/theodoi` ghi bài nguồn —
`lang_nghe_db.ghi_bai`), `cap_nhat_cuoi = now()` để BigQuery đồng bộ lại. Sắc thái / chủ đề giữ
nguyên: dashboard bỏ bài kênh nhà khỏi phần sắc thái theo `nguon.loai`.

An toàn: mặc định CHẠY THỬ trong giao dịch READ ONLY — in số bài theo nguồn và theo `luot_dau`,
kèm mẫu. `--ap-dung --sao-luu <tệp>`: ghi giá trị CŨ (khoá, `kieu_quet`, `nguon_id` = NULL) vào tệp
MỚI (không ghi đè, quyền 600, fsync) rồi UPDATE trong MỘT giao dịch, chỉ dòng còn `nguon_id` NULL.
`--hoan-tac <tệp>`: trả giá trị cũ, chỉ ở dòng còn mang đúng `nguon_id` script đã gắn.

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_sua_nguon_nha.py hapas                     # chạy thử
    sudo -u mark $PY scripts/lang_nghe_sua_nguon_nha.py hapas --ap-dung \\
        --sao-luu /opt/mark/sua-nguon-nha-$(date +%F).json
    sudo -u mark $PY scripts/lang_nghe_sua_nguon_nha.py hapas \\
        --hoan-tac /opt/mark/sua-nguon-nha-<ngày>.json
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import pathlib
import sys

GOC = pathlib.Path(__file__).resolve().parent.parent
for _p in (GOC, GOC / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lang_nghe_nap_raw as N

import lang_nghe_db as K

_VN = datetime.timezone(datetime.timedelta(hours=7))
_SQL_NGUON = ("/* sua_nha:nguon */ SELECT id, nen_tang, dinh_danh FROM nguon WHERE du_an = %s "
              "AND loai = 'kenh_nha' ORDER BY id")
_SQL_DA_GAN = ("/* sua_nha:da_gan */ SELECT nguon_id, link FROM bai WHERE du_an = %s "
               "AND nguon_id = ANY(%s)")
_SQL_BAI = ("/* sua_nha:bai */ SELECT khoa, nen_tang, tai_khoan, link, kieu_quet, luot_dau, "
            "dang_luc FROM bai WHERE du_an = %s AND nguon_id IS NULL AND nen_tang = ANY(%s) "
            "ORDER BY dang_luc NULLS LAST, khoa")
_SQL_GHI = ("/* sua_nha:ghi */ UPDATE bai SET nguon_id = %s, kieu_quet = 'theo_doi', "
            "cap_nhat_cuoi = now() WHERE du_an = %s AND khoa = %s AND nguon_id IS NULL")
_SQL_HOAN = ("/* sua_nha:hoan */ UPDATE bai SET nguon_id = NULL, kieu_quet = %s, "
             "cap_nhat_cuoi = now() WHERE du_an = %s AND khoa = %s AND nguon_id = %s")


def ke_hoach(nguon: list[dict], da_gan: list[dict], bai: list[dict]) -> tuple[list, list, dict]:
    """THUẦN. `nguon` = nguồn kênh nhà; `da_gan` = (nguon_id, link) của bài ĐÃ gắn các nguồn đó;
    `bai` = bài `nguon_id` NULL. -> (bài sẽ gắn — thêm "nguon_moi", bài mơ hồ — thêm "khop", bảng
    dấu {id nguồn: (nền tảng, dấu)})."""
    bang = N.bang_dau(nguon)
    for r in da_gan:          # id trang học từ link bài đã gắn (thedoor `/<id trang>/posts/…`)
        x = bang.get(int(r["nguon_id"]))
        if x and x[0] == "facebook":
            x[1].update(f"id:{a or b}" for a, b in N._RE_ID_TRANG.findall(str(r.get("link") or "")))
    gan, mo_ho = [], []
    for r in bai:
        p = str(r.get("nen_tang") or "")
        ids = N.nguon_khop(p, N.dau_chu_bai(p, str(r.get("tai_khoan") or ""),
                                            str(r.get("link") or "")), bang)
        if len(ids) == 1:
            gan.append({**r, "nguon_moi": ids[0]})
        elif ids:
            mo_ho.append({**r, "khop": ids})
    return gan, mo_ho, bang


def _luot(k) -> str:
    return f"lượt {k}" if k is not None else "không lượt"


def _theo_luot(rows: list[dict]) -> str:
    dem = collections.Counter(r.get("luot_dau") for r in rows)
    return ", ".join(f"{_luot(k)}: {v}" for k, v in sorted(
        dem.items(), key=lambda x: (x[0] is None, x[0] or 0)))


def _mau(r: dict) -> str:
    dt = r.get("dang_luc")
    ngay = dt.astimezone(_VN).strftime("%d/%m %H:%M") if isinstance(dt, datetime.datetime) else "?"
    return (f"    {r['khoa']} · {ngay} · {_luot(r.get('luot_dau'))} · {r.get('kieu_quet')} · "
            f"@{r.get('tai_khoan') or '?'} · {r.get('link') or ''}")


def bao_cao(ma: str, nguon: list[dict], bang: dict, gan: list, mo_ho: list, mau: int) -> list[str]:
    ten = {int(n["id"]): f"#{n['id']} {n['nen_tang']} {n['dinh_danh']}" for n in nguon}
    ra = [f"Nguồn kênh nhà của {ma}: " + "; ".join(
        f"{ten[nid]} (dấu {', '.join(sorted(d)) or '—'})" for nid, (_, d) in bang.items())]
    ra.append(f"Sẽ gắn {len(gan)} bài (nguon_id NULL → nguồn kênh nhà, kieu_quet → theo_doi)"
              + (f" — theo luot_dau: {_theo_luot(gan)}" if gan else "") + ".")
    for nid in bang:
        cua = [r for r in gan if r["nguon_moi"] == nid]
        if not cua:
            continue
        kq = collections.Counter(str(r.get("kieu_quet")) for r in cua)
        ra.append(f"  {ten[nid]}: {len(cua)} bài — {_theo_luot(cua)}; kieu_quet cũ "
                  + ", ".join(f"{k} {v}" for k, v in sorted(kq.items())))
        ra += [_mau(r) for r in cua[:mau]]
    if mo_ho:
        ra.append(f"Mơ hồ (khớp > 1 nguồn kênh nhà — để nguyên): {len(mo_ho)} bài — "
                  f"{_theo_luot(mo_ho)}")
        ra += [_mau(r) + f" · khớp {r['khop']}" for r in mo_ho[:mau]]
    return ra


def _ghi_sao_luu(tep: pathlib.Path, ma: str, dong: list[dict]) -> None:
    """Tệp hoàn tác: tạo MỚI (không ghi đè), quyền 600, ghi xong + fsync rồi mới sửa kho."""
    noi_dung = json.dumps({"tao_luc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           "script": "scripts/lang_nghe_sua_nguon_nha.py", "du_an": ma,
                           "so_dong": len(dong), "dong": dong}, ensure_ascii=False, indent=1)
    fd = os.open(tep, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(noi_dung)
        f.flush()
        os.fsync(f.fileno())


def chay(ns, in_ra=print) -> int:
    ma = ns.du_an.strip().lower()
    if ns.hoan_tac:
        return hoan_tac(ma, ns.hoan_tac, in_ra)
    if ns.ap_dung and not ns.sao_luu:
        in_ra("--ap-dung cần --sao-luu <tệp> (tệp hoàn tác).")
        return 2
    if ns.ap_dung and pathlib.Path(ns.sao_luu).exists():
        in_ra(f"Tệp {ns.sao_luu} đã có — chọn tên khác (không ghi đè tệp hoàn tác cũ).")
        return 2
    with K.ket_noi() as c:                    # MỘT giao dịch: lỗi giữa chừng thì không ghi gì
        if not ns.ap_dung:
            c.execute("SET TRANSACTION READ ONLY")
        nguon = c.execute(_SQL_NGUON, (ma,)).fetchall()
        if not nguon:
            in_ra(f"Dự án {ma} không có nguồn kênh nhà nào — không có gì để gắn.")
            return 0
        da_gan = c.execute(_SQL_DA_GAN, (ma, [int(n["id"]) for n in nguon])).fetchall()
        bai = c.execute(_SQL_BAI, (ma, sorted({str(n["nen_tang"]) for n in nguon}))).fetchall()
        gan, mo_ho, bang = ke_hoach(nguon, da_gan, bai)
        in_ra(f"Dự án {ma} — " + ("ÁP DỤNG" if ns.ap_dung else "CHẠY THỬ (giao dịch chỉ đọc)")
              + f": xét {len(bai)} bài nguon_id NULL trên nền tảng có nguồn kênh nhà.")
        for s in bao_cao(ma, nguon, bang, gan, mo_ho, max(0, ns.mau)):
            in_ra(s)
        if not ns.ap_dung:
            in_ra("Không ghi gì. Ghi thật: thêm --ap-dung --sao-luu <tệp hoàn tác>.")
            return 0
        if not gan:
            in_ra("Không có bài nào cần gắn — không tạo tệp hoàn tác.")
            return 0
        _ghi_sao_luu(pathlib.Path(ns.sao_luu), ma, [
            {"khoa": r["khoa"], "nguon_id": None, "kieu_quet": r["kieu_quet"],
             "luot_dau": r.get("luot_dau"), "nguon_moi": r["nguon_moi"]} for r in gan])
        so = sum(c.execute(_SQL_GHI, (r["nguon_moi"], ma, r["khoa"])).rowcount or 0 for r in gan)
    in_ra(f"Đã gắn {so}/{len(gan)} bài (một giao dịch; dashboard + BigQuery thấy sau lượt đồng bộ "
          f"kế). Hoàn tác: --hoan-tac {ns.sao_luu}")
    return 0


def hoan_tac(ma: str, tep: str, in_ra) -> int:
    """Trả `nguon_id` NULL + `kieu_quet` cũ, MỘT giao dịch, chỉ dòng còn mang nguồn script gắn."""
    x = json.loads(pathlib.Path(tep).read_text(encoding="utf-8"))
    if x.get("du_an") != ma:
        in_ra(f"Tệp hoàn tác không phải của dự án '{ma}' — dừng.")
        return 2
    dong = x["dong"]
    with K.ket_noi() as c:
        tra = sum(c.execute(_SQL_HOAN, (r["kieu_quet"], ma, r["khoa"], r["nguon_moi"])).rowcount
                  or 0 for r in dong)
    in_ra(f"Đã trả giá trị cũ cho {tra}/{len(dong)} bài (một giao dịch); {len(dong) - tra} bài đã "
          "đổi nguồn sau đó nên để nguyên.")
    return 0


def tao_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Gắn lại nguon_id cho bài kênh nhà ghi như bài tìm "
                                             "theo từ khoá (một lần; mặc định chạy thử).")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("--ap-dung", action="store_true", help="ghi thật (cần --sao-luu)")
    ap.add_argument("--sao-luu", metavar="TEP", help="tệp JSON hoàn tác (tạo mới)")
    ap.add_argument("--hoan-tac", metavar="TEP", help="trả giá trị cũ từ tệp --sao-luu")
    ap.add_argument("--mau", type=int, default=5, help="số bài mẫu in mỗi nguồn (mặc định 5)")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = tao_parser()
    ns = ap.parse_args(argv)
    if ns.ap_dung and ns.hoan_tac:
        ap.error("--ap-dung và --hoan-tac là hai việc riêng")
    N._dsn_tu_env_file()
    try:
        return chay(ns)
    except K.LoiKho as e:
        print(f"Lỗi kho: {e}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as e:     # tệp sao lưu / hoàn tác: kho không bị sửa
        print(f"Lỗi tệp ({type(e).__name__}): {e} — kho KHÔNG bị sửa.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
