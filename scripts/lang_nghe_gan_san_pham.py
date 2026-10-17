"""Gán MÓN khách hỏi mua cho bình luận ý định mua ĐÃ có trong kho `lang_nghe` — script MỘT LẦN
(17/10/2026, cột `binh_luan.san_pham`).

Vì sao cần: chủ dự án "đôi khi người dùng hỏi mua những cái khác nhưng đang bị đánh vào hỏi mua
túi". Từ bản này việc nền `gan_nhan_nen` gán món cùng lượt gán sắc thái/chủ đề (đọc cả nội dung
bài), nhưng chỉ cho dòng CHƯA có nhãn — bình luận ý định mua đã gán trước đó có `san_pham` NULL,
dashboard lùi về tên món trong chính bình luận nên "xin giá" dưới bài hộp quà vẫn là "Chưa rõ món".

Chọn: bình luận `hop_le`, không của thương hiệu, `san_pham` NULL, và là ý định mua theo ĐÚNG luật
của dashboard (`dashboard.chi_so._hoi_mua`: chủ đề AI "Giá/mua…" không Tiêu cực, hoặc câu hỏi
giá/mua). Gọi ĐÚNG `phan_loai.phan_loai_binh_luan(kem_san_pham=True)` với nội dung bài + mô tả
brand như việc nền; CHỈ ghi `san_pham` — sắc thái/chủ đề giữ nguyên (không để lượt gán lại làm
lệch số cũ). Model không trả món cho dòng nào thì dòng đó giữ NULL.

An toàn (như scripts/lang_nghe_gan_lai.py):
  • Mặc định CHẠY THỬ: đọc trong MỘT giao dịch READ ONLY, không gọi model, không ghi; in số dòng,
    mẫu (tác giả đã băm) và ước tính số lượt gọi model. `--thu N` gọi model cho tối đa N dòng
    (một lô) để xem trước món — vẫn không ghi.
  • `--ap-dung --sao-luu <tệp>`: ghi tệp hoàn tác TRƯỚC, rồi UPDATE từng lô ≤ 100 dòng trong một
    giao dịch; chỉ sửa dòng còn `san_pham` NULL và CÙNG nội dung lúc đọc. `cap_nhat_cuoi = now()`
    để đồng bộ BigQuery lấy lại dòng.
  • `--hoan-tac <tệp>`: trả NULL cho các dòng CÒN mang đúng món script đã ghi.
  • Gọi model TUẦN TỰ từng lô 100 (quota dùng chung với bot chính).

Chạy trên VPS bằng user `mark`, SAU khi đã chạy deploy/lang-nghe/schema.sql (cột san_pham) và bản
code mới đã lên:

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_gan_san_pham.py hapas                 # chạy thử
    sudo -u mark $PY scripts/lang_nghe_gan_san_pham.py hapas --thu 50        # xem trước món
    sudo -u mark $PY scripts/lang_nghe_gan_san_pham.py hapas --ap-dung --sao-luu .audit/san-pham-1710.jsonl
    sudo -u mark $PY scripts/lang_nghe_gan_san_pham.py hapas --hoan-tac .audit/san-pham-1710.jsonl
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import math
import os
import pathlib
import sys

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

import gan_nhan_nen as G  # noqa: E402
import lang_nghe_db as K  # noqa: E402
import phan_loai as P  # noqa: E402
from dashboard import chi_so as CS  # noqa: E402

LO = P._LO                      # 100 bình luận mỗi lượt gọi model — như việc nền
HAN_LO_GIAY = 180.0

# Mọi câu SQL mang thẻ `/* sp:<tên> */` — bộ thử nhận diện câu theo thẻ (kho giả).
SQL_CHI_DOC = "SET TRANSACTION READ ONLY"
SQL_DU_AN = "/* sp:du_an */ SELECT ma, ten, tu_khoa, boi_canh FROM du_an WHERE ma = %s"
SQL_BL = (
    "/* sp:bl */ SELECT b.khoa_bai, b.ma, b.tac_gia, b.noi_dung, b.thich, b.loai, b.sac_thai, "
    "b.chu_de, b.cua_thuong_hieu, b.san_pham, b.la_tra_loi, "
    "left(p.noi_dung, 300) AS bai_noi_dung, "
    "left(p.hashtag, 120) AS bai_hashtag "
    "FROM binh_luan b JOIN bai p ON p.du_an = b.du_an AND p.khoa = b.khoa_bai "
    "WHERE b.du_an = %s AND b.loai = 'hop_le' AND NOT b.cua_thuong_hieu AND b.san_pham IS NULL "
    "AND btrim(b.noi_dung) <> '' "
    # Trả lời chỉ là ý định mua khi AI gán "Giá/mua…" (`dashboard.chi_so._hoi_mua`).
    "AND (NOT b.la_tra_loi OR b.chu_de = 'Giá/mua ở đâu/ý định mua') "
    "ORDER BY b.khoa_bai, b.ma")
SQL_SUA = (
    "/* sp:sua */ UPDATE binh_luan SET san_pham = %s, cap_nhat_cuoi = now() "
    "WHERE du_an = %s AND khoa_bai = %s AND ma = %s AND san_pham IS NULL AND loai = 'hop_le' "
    "AND NOT cua_thuong_hieu AND noi_dung = %s")
SQL_HOAN = (
    "/* sp:hoan */ UPDATE binh_luan SET san_pham = NULL, cap_nhat_cuoi = now() "
    "WHERE du_an = %s AND khoa_bai = %s AND ma = %s AND san_pham = %s")


def bam(tac_gia) -> str:
    """Tác giả trong bản in: băm, không in tên thật."""
    return "#" + hashlib.sha1(str(tac_gia or "").encode("utf-8")).hexdigest()[:8]


def doc_kho(ma: str) -> tuple[dict | None, list[dict]]:
    """(dự án, bình luận hop_le chưa có món) — MỘT giao dịch READ ONLY."""
    with K.ket_noi() as c:
        c.execute(SQL_CHI_DOC)
        du_an = c.execute(SQL_DU_AN, (ma,)).fetchone()
        if not du_an:
            return None, []
        return du_an, list(c.execute(SQL_BL, (ma,)).fetchall())


def chon(rows: list[dict]) -> list[dict]:
    """Bình luận ý định mua theo luật của dashboard (chưa xét món)."""
    return [r for r in rows if CS._hoi_mua(r)]


def uoc_luot_model(dong: list[dict]) -> tuple[int, int]:
    """-> (số dòng cần model, số lượt gọi model)."""
    n = sum(1 for d in dong if P._luat(d.get("noi_dung") or "") is None)
    return n, math.ceil(n / LO)


def gan_mon(lo: list[dict], brand: str) -> tuple[list[tuple[dict, str]], dict]:
    """Một lô qua đúng bộ gán nhãn của việc nền. -> ([(dòng, món)], thống kê)."""
    tt: dict = {}
    nhan = P.phan_loai_binh_luan(
        [{"text": d.get("noi_dung") or "", "likes": int(d.get("thich") or 0),
          "ngu_canh_bai": G.ngu_canh_bai(d)} for d in lo],
        HAN_LO_GIAY, tt, song_song=1, brand=brand, kem_san_pham=True)
    ra = [(d, sp) for d, (_, _, sp) in zip(lo, nhan) if sp in P.SAN_PHAM]
    return ra, {"khong_mon": len(lo) - len(ra), "trang_thai": tt.get("trang_thai") or ""}


def ghi_lo(ma: str, doi: list[tuple[dict, str]], so_luu) -> tuple[int, int]:
    """Ghi tệp hoàn tác rồi UPDATE trong MỘT giao dịch. -> (đã sửa, bỏ qua vì dòng đã đổi)."""
    if not doi:
        return 0, 0
    for d, sp in doi:
        so_luu.write(json.dumps({"du_an": ma, "khoa_bai": d["khoa_bai"], "ma": d["ma"],
                                 "cu": None, "moi": sp}, ensure_ascii=False) + "\n")
    so_luu.flush()
    os.fsync(so_luu.fileno())
    sua = 0
    with K.ket_noi() as c:
        for d, sp in doi:
            sua += int(c.execute(SQL_SUA, (sp, ma, d["khoa_bai"], d["ma"],
                                           d.get("noi_dung") or "")).rowcount or 0)
    return sua, len(doi) - sua


def hoan_tac(ma: str, tep: str) -> tuple[int, int, str]:
    dong, du_an_tep = [], ""
    with open(tep, encoding="utf-8") as f:
        for x in f:
            if not x.strip():
                continue
            r = json.loads(x)
            if r.get("loai_dong") == "dau":
                du_an_tep = r.get("du_an") or ""
            elif all(k in r for k in ("khoa_bai", "ma", "moi")) and r.get("du_an", ma) == ma:
                dong.append(r)
    if du_an_tep and du_an_tep != ma:
        return 0, 0, du_an_tep
    sua = 0
    for i in range(0, len(dong), LO):
        with K.ket_noi() as c:
            for r in dong[i:i + LO]:
                sua += int(c.execute(SQL_HOAN, (ma, r["khoa_bai"], r["ma"], r["moi"])).rowcount
                           or 0)
    return sua, len(dong) - sua, ""


def _mau(d: dict, sp: str | None = None) -> str:
    t = P._TAG_RE.sub("@…", " ".join(str(d.get("noi_dung") or "").split()))
    t = t if len(t) <= 80 else t[:79] + "…"
    b = " ".join(str(d.get("bai_noi_dung") or "").split())[:50]
    return (f"  [{bam(d.get('tac_gia'))}] \"{t}\" | bài: \"{b}\" | theo chữ: "
            f"{CS.san_pham_tu_chu(d.get('noi_dung')) or '—'}" + (f" → AI: {sp}" if sp else ""))


def _chuan_bi_model() -> None:
    """Nạp `.env` của Mark và chỉ đường tới Hermes như `brain.py` (như lang_nghe_gan_lai)."""
    from config import config
    os.environ.setdefault("HERMES_HOME", config.hermes_home)
    os.environ.setdefault("PYTHONUTF8", "1")
    if config.hermes_agent_dir not in sys.path:
        sys.path.insert(0, config.hermes_agent_dir)


def chay(ns, in_ra=print) -> int:
    ma = ns.du_an.strip().lower()
    if ns.hoan_tac:
        sua, bo, khac = hoan_tac(ma, ns.hoan_tac)
        if khac:
            in_ra(f"Tệp hoàn tác của dự án '{khac}', không phải '{ma}' — dừng.")
            return 2
        in_ra(f"Hoàn tác {ma}: trả NULL cho {sua} dòng; {bo} dòng bỏ qua (món đã đổi sau đó).")
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
    dong = chon(rows)
    can, luot = uoc_luot_model(dong)
    brand = G.brand_du_an(du_an)
    theo_chu = collections.Counter(CS.san_pham_tu_chu(d.get("noi_dung")) or "chua_ro"
                                   for d in dong)
    in_ra(f"Dự án {ma} — {'ÁP DỤNG' if ns.ap_dung else 'CHẠY THỬ (chỉ đọc, không ghi gì)'}.")
    in_ra(f"Bình luận ý định mua chưa có món: {len(dong)} (trên {len(rows)} hop_le chưa có món).")
    in_ra("  Món theo chữ trong bình luận (luật lùi của dashboard hiện nay): "
          + ", ".join(f"{k} {v}" for k, v in theo_chu.most_common()))
    in_ra(f"  Ước tính: {can} dòng → {luot} lượt gọi model (lô {LO}, tuần tự, kèm nội dung bài).")
    for d in dong[:ns.mau]:
        in_ra(_mau(d))
    if not ns.ap_dung:
        thu = [d for d in dong if P._luat(d.get("noi_dung") or "") is None][:min(max(0, ns.thu),
                                                                              LO)]
        if thu:
            _chuan_bi_model()
            doi, dem = gan_mon(thu, brand)
            in_ra(f"Xem trước {len(thu)} dòng (1 lượt model, KHÔNG ghi): "
                  + ", ".join(f"{k} {v}" for k, v in collections.Counter(
                      sp for _, sp in doi).most_common())
                  + f"; không trả món {dem['khong_mon']} ({dem['trang_thai'] or '—'}).")
            for d, sp in doi[:ns.mau]:
                in_ra(_mau(d, sp))
        in_ra("Không ghi gì. Ghi thật: thêm --ap-dung --sao-luu <tệp hoàn tác>.")
        return 0
    _chuan_bi_model()
    can_model = [d for d in dong if P._luat(d.get("noi_dung") or "") is None]
    cac_lo = [can_model[i:i + LO] for i in range(0, len(can_model), LO)]
    tong = collections.Counter()
    sua_tong = bo_tong = khong = 0
    with open(ns.sao_luu, "x", encoding="utf-8") as so_luu:
        so_luu.write(json.dumps({
            "loai_dong": "dau", "du_an": ma, "phien_ban": 1, "cot": "san_pham",
            "luc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
            ensure_ascii=False) + "\n")
        so_luu.flush()
        for j, lo in enumerate(cac_lo, 1):
            doi, dem = gan_mon(lo, brand)
            sua, bo = ghi_lo(ma, doi, so_luu)
            sua_tong, bo_tong, khong = sua_tong + sua, bo_tong + bo, khong + dem["khong_mon"]
            tong.update(sp for _, sp in doi)
            in_ra(f"    lô {j}/{len(cac_lo)}: {len(lo)} dòng, ghi {sua}, bỏ qua {bo}, không trả "
                  f"món {dem['khong_mon']} ({dem['trang_thai'] or '—'})")
    in_ra(f"Đã ghi món cho {sua_tong} dòng (" + ", ".join(
        f"{k} {v}" for k, v in tong.most_common()) + f"); bỏ qua {bo_tong} (dòng đã đổi); "
          f"{khong} dòng model không trả món (giữ NULL). Tệp hoàn tác: {ns.sao_luu}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gán món khách hỏi mua (binh_luan.san_pham) cho "
                                             "bình luận ý định mua cũ (mặc định chạy thử).")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("--dry-run", action="store_true",
                    help="chạy thử (mặc định khi không có --ap-dung / --hoan-tac)")
    ap.add_argument("--ap-dung", action="store_true", help="ghi thật (cần --sao-luu)")
    ap.add_argument("--sao-luu", metavar="TEP", help="tệp hoàn tác JSONL (tạo mới)")
    ap.add_argument("--hoan-tac", metavar="TEP", help="trả NULL cho các dòng script đã ghi")
    ap.add_argument("--thu", type=int, default=0, metavar="N",
                    help="chạy thử: gọi model cho tối đa N dòng (≤ 100) để xem trước, không ghi")
    ap.add_argument("--mau", type=int, default=8, help="số dòng mẫu in ra")
    ns = ap.parse_args(argv)
    if ns.dry_run and (ns.ap_dung or ns.hoan_tac):
        ap.error("--dry-run không đi cùng --ap-dung / --hoan-tac")
    if ns.ap_dung and ns.hoan_tac:
        ap.error("--ap-dung và --hoan-tac là hai việc riêng")
    return chay(ns)


if __name__ == "__main__":
    sys.exit(main())
