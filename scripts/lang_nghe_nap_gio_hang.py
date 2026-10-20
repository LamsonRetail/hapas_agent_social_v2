"""Bù cờ giỏ hàng TikTok (`bai.gio_hang`, `bai.la_quang_cao`) cho bài ĐÃ CÓ trong kho (20/10/2026).

Vì sao: marketing (task Lark t284905) — "đang bị lẫn KOC branding và KOC aff → tiêu chí: KOC
branding không gắn giỏ hàng >< KOC aff có gắn giỏ". Cờ giỏ TikTok Shop có sẵn lúc cào
(`tiktok_api._gio_hang`: anchor có "shop"; `hasTikTokShopProduct` của clockworks) nhưng trước
20/10/2026 không được ghi vào `bai`, nên cả kho cũ là NULL ("chưa rõ") trên dashboard.

Hai đường:
  (a) MIỄN PHÍ — đọc lại raw ĐÃ TRẢ TIỀN, đúng cách `scripts/lang_nghe_nap_raw.py` tìm tệp (mỗi
      đường dẫn là tệp hoặc thư mục, đệ quy `raw_*.json` / `raw_*.jsonl`): `.jsonl` scraptik qua
      `lang_nghe_nap_raw._tiktok` (→ `tiktok_api.video` → `apify_tool._chuan_tiktok`), `.json` của
      clockworks / apidojo qua `_chuan_clockworks` / `_chuan_tiktok`. Actor TikTok khác (epctex,
      powerai…) không có bộ chuẩn hoá của Mark — bỏ qua, in tên. Khớp bài theo khoá
      (`theo_doi._khoa_bai`: "tiktok:<id video>"). Nhiều bản đọc của một video gộp như kho
      (`lang_nghe_db._GOP_CO`): có bản báo giỏ là TRUE, FALSE chỉ khi không bản nào báo TRUE,
      NULL khi không bản nào báo. Cờ theo loại phản hồi (`tiktok_api.DAY_DU` / `FEED` /
      `CHI_TIET`, soát 21/10/2026): tìm kiếm / hồ sơ không có anchor shop = FALSE (kể cả anchors
      trống); feed hashtag (scraptik challengePosts, clockworks hashtag) chỉ tin TRUE — feed không
      bao giờ trả anchor shop, 21/53 "không giỏ" của feed trái với tìm kiếm / hồ sơ.
  (b) TRẢ TIỀN — bài còn NULL sau (a): in số bài + ước tính (`tiktok_api.so_lieu_bai`, 1 yêu cầu
      / video = `tiktok_api.GIA_YEU_CAU` USD; API không nhận nhiều id một yêu cầu). CHỈ gọi khi
      có `--goi-api --toi-da-usd X`: trần = min(X, phần còn của tháng dự án, ngân sách Apify việc
      nền `quet_lon.ngan_sach`), mở MỘT lượt `theo_doi` riêng (`ma_viec` "gio-hang-…") và đóng với
      chi phí theo số run (như `theo_doi_api.lam_moi_tiktok`) — tiền vào trần tháng của dự án; số
      liệu mới đọc được cập nhật luôn (`lang_nghe_db.cap_nhat_so_lieu`, ảnh chụp hôm nay).
      Lưu ý: raw 18/10 có 1/1 phản hồi `post` (aweme_detail) THIẾU `anchors` — thử nhỏ trước
      (`--toi-da-usd 0.01` = 5 video) xem có ra cờ không rồi mới chạy lớn.

An toàn:
  • Mặc định CHẠY THỬ: chỉ đọc kho, in số bài khớp, số sẽ đặt TRUE / FALSE, số còn NULL.
  • Thứ tự triển khai: ALTER BigQuery (cuối `deploy/lang-nghe/bigquery.sql`) TRƯỚC schema.sql
    và TRƯỚC script này — đồng bộ BigQuery đi theo mốc `cap_nhat_cuoi`: dòng đã đồng bộ khi
    BigQuery chưa có cột sẽ không được đẩy lại (README §11).
  • `--ghi --sao-luu <tệp>`: ghi (một giao dịch) và lưu giá trị cũ từng bài vào tệp JSONL (hoàn
    tác: `UPDATE bai SET gio_hang = <cũ>, la_quang_cao = <cũ> …` theo tệp). Cờ chỉ được điền /
    nâng (`_GOP_CO`), không bao giờ hạ TRUE, không ghi đè bằng NULL; `cap_nhat_cuoi = now()` chỉ
    với bài có cờ đổi (BigQuery đồng bộ lại đúng các bài đó).
  • Phạm vi sao lưu của đường trả tiền (`--goi-api`): tệp chỉ giữ giá trị CŨ của hai cờ cho bài
    nhận được cờ; số liệu (xem / thích / bình luận / chia sẻ) đọc lại được cập nhật theo luật
    thường của kho (`cap_nhat_so_lieu`, ảnh chụp `chi_so_ngay` hôm nay) và KHÔNG có trong tệp —
    đó là số đọc thật mới hơn, không cần hoàn tác.

VPS (user mark, cwd /opt/mark/app; chạy ALTER bigquery.sql rồi schema.sql trước — README §11):

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_nap_gio_hang.py hapas /opt/mark/raw-kompa-1810    # chạy thử
    sudo -u mark $PY scripts/lang_nghe_nap_gio_hang.py hapas /opt/mark/raw-kompa-1810 --ghi \\
        --sao-luu /opt/mark/gio-hang-$(date +%F).jsonl
    sudo -u mark $PY scripts/lang_nghe_nap_gio_hang.py hapas --goi-api --toi-da-usd 0.01 \\
        --ghi --sao-luu /opt/mark/gio-hang-api-$(date +%F).jsonl                     # thử nhỏ
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
for _p in (GOC, GOC / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_VN = datetime.timezone(datetime.timedelta(hours=7))
_CO = ("gio_hang", "la_quang_cao")
#: Actor TikTok có bộ chuẩn hoá của Mark (tệp `.json` có `actor` + `items`).
_TIKTOK_JSON = {"clockworks~tiktok-hashtag-scraper": "clockworks",
                "clockworks~tiktok-scraper": "clockworks",
                "clockworks~tiktok-profile-scraper": "clockworks",
                "apidojo~tiktok-scraper": "apidojo"}


def gop(cu, moi):
    """Bản Python của `lang_nghe_db._GOP_CO`: TRUE dính, FALSE điền chỗ NULL, NULL không đè."""
    if cu is True or moi is True:
        return True
    return cu if cu is not None else moi


# ───────────────────────────── đọc raw (miễn phí) ─────────────────────────────
def doc_co_raw(duong: list[str]) -> dict:
    """Mọi tệp raw → {"co": {khoá bài: {"gio_hang", "la_quang_cao"}}, "ban_doc": số bản đọc
    TikTok, "tep": [(tên, loại, số bản đọc)], "bo_qua": [(tên, lý do)]}. Không gọi mạng."""
    import apify_tool as A
    import lang_nghe_nap_raw as N
    import theo_doi as T
    ra = {"co": {}, "ban_doc": 0, "tep": [], "bo_qua": []}

    def them(rows):
        for d, _ in rows:
            goc = d.get("__goc") if isinstance(d.get("__goc"), dict) else {}
            k = T._khoa_bai("tiktok", d.get("link") or "", {"id": goc.get("id")})
            x = ra["co"].setdefault(k, dict.fromkeys(_CO))
            for c in _CO:
                v = d.get(c)
                x[c] = gop(x[c], v if isinstance(v, bool) else None)
            ra["ban_doc"] += 1
    for f in N.cac_tep(duong):
        try:
            if f.suffix == ".jsonl":
                tim, ho_so = N._tiktok(f)
                them(tim + ho_so)
                ra["tep"].append((f.name, "scraptik TikTok", len(tim) + len(ho_so)))
                continue
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            ra["bo_qua"].append((f.name, f"đọc lỗi {type(e).__name__}"))
            continue
        actor = str((r or {}).get("actor") or "").replace("/", "~") if isinstance(r, dict) else ""
        kieu = _TIKTOK_JSON.get(actor)
        if not kieu:
            if "tiktok" in actor or f.name.startswith("raw_tt"):
                ra["bo_qua"].append((f.name,
                                     f"actor {actor or '?'} không có bộ chuẩn hoá của Mark"))
            continue
        items = [it for it in r.get("items") or [] if isinstance(it, dict) and not A._la_demo(it)]
        if actor == A._ACTORS["tiktok_fallback"]:
            items = A.chi_tin_gio_true(items)       # feed hashtag: chỉ tin TRUE
        rows = A._chuan_tiktok(A._chuan_clockworks(items) if kieu == "clockworks" else items)
        them(rows)
        ra["tep"].append((f.name, actor, len(rows)))
    return ra


def ke_hoach(bai: list[dict], co: dict[str, dict]) -> dict:
    """Bài trong kho × cờ đọc từ raw → {"khop", "doi": [{khoa, cờ mới…, "_cu": {cờ cũ}}],
    "dat": {cờ: {True: n, False: n}}, "con_null": [bài còn gio_hang NULL sau khi ghi]}. Thuần."""
    ra = {"khop": 0, "doi": [], "dat": {c: {True: 0, False: 0} for c in _CO}, "con_null": []}
    for b in bai:
        x = co.get(b["khoa"])
        if x is not None:
            ra["khop"] += 1
        moi = {c: gop(b.get(c), (x or {}).get(c)) for c in _CO}
        doi = {c: moi[c] for c in _CO if moi[c] is not None and moi[c] != b.get(c)}
        if doi:
            for c, v in doi.items():
                ra["dat"][c][v] += 1
            ra["doi"].append({"khoa": b["khoa"], **doi, "_cu": {c: b.get(c) for c in _CO}})
        if moi["gio_hang"] is None:
            ra["con_null"].append(b)
    return ra


def _ghi_sao_luu(tep: str, ma: str, doi: list[dict], nhan: str) -> None:
    with open(tep, "a", encoding="utf-8") as fh:
        for r in doi:
            fh.write(json.dumps({"du_an": ma, "duong": nhan, "khoa": r["khoa"], "cu": r["_cu"],
                                 "moi": {c: r[c] for c in _CO if c in r}},
                                ensure_ascii=False) + "\n")


# ───────────────────────────── TikTok API (trả tiền) ─────────────────────────────
def uoc_api(so_bai: int) -> float:
    """USD đọc lại `so_bai` video (1 yêu cầu/video — scraptik `post_awemeId` một id mỗi yêu cầu)."""
    import tiktok_api as TT
    return round(so_bai * TT.GIA_YEU_CAU, 4)


def goi_api(ma: str, bai: list[dict], toi_da_usd: float, in_ra, bay_gio) -> tuple[list[dict], dict]:
    """Đọc lại cờ (+ số liệu) của tối đa ⌊trần / giá⌋ bài qua `tiktok_api.so_lieu_bai`, trong MỘT
    lượt `theo_doi` riêng. -> (dòng {khoa, xem…, cờ}, {"luot", "usd", "goi", "loi"})."""
    import apify_tool as A
    import lang_nghe_db as K
    import quet_lon
    import tiktok_api as TT
    du_an = K.doc_du_an(ma) or {}
    con = max(0.0, float(du_an.get("tran_usd_thang") or 0) - K.da_tieu_thang(ma))
    ns_apify, _, ghi = quet_lon.ngan_sach(quet_lon.tran_usd_nen())
    tran = min(float(toi_da_usd), con, ns_apify)
    n = min(len(bai), int(math.floor(tran / TT.GIA_YEU_CAU + 1e-9)))
    in_ra(f"TikTok API: trần {tran:.4f} USD = min(--toi-da-usd {toi_da_usd}, còn tháng dự án "
          f"{con:.2f}, ngân sách Apify việc nền {ns_apify:.2f}) → đọc {n}/{len(bai)} bài. {ghi}")
    tk = {"luot": None, "usd": 0.0, "goi": n, "loi": None}
    if n <= 0:
        return [], tk
    if not os.environ.get("APIFY_TOKEN", "").strip():
        tk["loi"] = "thiếu APIFY_TOKEN"
        return [], tk
    dang = K.luot_dang_chay(ma)
    if dang:
        tk["loi"] = f"dự án đang có lượt {dang.get('ma_viec') or dang.get('id')}"
        return [], tk
    chon = bai[:n]
    theo_link = {b["link"]: b["khoa"] for b in chon if b.get("link")}
    luot = K.mo_luot(ma, "theo_doi", ma_viec=f"gio-hang-{bay_gio:%Y%m%d%H%M}")
    tk["luot"] = luot
    so: list = []
    moc = [(bien, bien.set(gt)) for bien, gt in ((A._NEN_TANG, "tiktok"), (A._SO_RUN, so))]
    items: list = []
    rows: list[dict] = []
    try:
        try:
            items = TT.so_lieu_bai(list(theo_link), tran_usd=n * TT.GIA_YEU_CAU)
        except A.LoiApify as e:
            tk["loi"] = f"{e.ma}: {A._che_token(str(e))[:200]}"
        finally:
            for bien, t in reversed(moc):
                bien.reset(t)
        tk["usd"] = round(sum(TT.GIA_YEU_CAU for m in so if isinstance(m, dict)
                              and m.get("run_id")), 4)
        vid = {TT.id_video(u): k for u, k in theo_link.items()}
        for it in items:
            if it.get("id") not in vid:
                continue
            r = {"khoa": vid[it["id"]], "xem": it.get("playCount"), "thich": it.get("diggCount"),
                 "binh_luan": it.get("commentCount"), "chia_se": it.get("shareCount"),
                 "gio_hang": A._gio_hang_tiktok(it), "la_quang_cao": A._quang_cao_tiktok(it)}
            rows.append({k: v for k, v in r.items() if v is not None or k not in _CO})
        cap = K.cap_nhat_so_lieu(ma, luot, rows) if rows else 0
    finally:
        co = sum(1 for r in rows if "gio_hang" in r)
        K.dong_luot(luot, trang_thai="loi" if tk["loi"] and not rows else "xong", so_nguon=0,
                    bai_moi=0, bai_cap_nhat=len(rows), chi_phi_usd=tk["usd"],
                    loi=(tk["loi"] or None) and str(tk["loi"])[:500],
                    ghi_chu=(f"bù cờ giỏ hàng TikTok (script một lần, 20/10/2026): "
                             f"{len(theo_link)} bài gửi, {len(items)} về, {co} có cờ giỏ"))
    in_ra(f"TikTok API: {len(items)} video về, {co} có cờ giỏ, cập nhật {cap} bài; chi phí "
          f"{tk['usd']:.4f} USD (lượt {luot}, tính vào trần tháng của dự án).")
    return rows, tk


# ───────────────────────────── chạy ─────────────────────────────
def chay(ns, in_ra=print, bay_gio: datetime.datetime | None = None) -> int:
    import lang_nghe_db as K
    import tiktok_api as TT
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    ma = ns.du_an.strip().lower()
    che_do = "GHI" if ns.ghi else "CHẠY THỬ (chỉ đọc kho, không ghi)"
    in_ra(f"Dự án {ma} — {che_do}.")
    raw = doc_co_raw(ns.duong) if ns.duong else {"co": {}, "ban_doc": 0, "tep": [], "bo_qua": []}
    for ten, loai, n in raw["tep"]:
        in_ra(f"  {ten}: {loai}, {n} bản đọc")
    for ten, ly in raw["bo_qua"]:
        in_ra(f"  bỏ qua {ten}: {ly}")
    dem = {c: {v: sum(1 for x in raw["co"].values() if x[c] is v) for v in (True, False, None)}
           for c in _CO}
    in_ra(f"Raw: {raw['ban_doc']} bản đọc TikTok, {len(raw['co'])} video — giỏ hàng có "
          f"{dem['gio_hang'][True]}, không {dem['gio_hang'][False]}, nguồn không báo "
          f"{dem['gio_hang'][None]}; quảng cáo có {dem['la_quang_cao'][True]}, không "
          f"{dem['la_quang_cao'][False]}, không báo {dem['la_quang_cao'][None]}.")
    try:
        bai = K.bai_tiktok_co(ma)
    except K.LoiKho as e:
        in_ra(f"Dừng: {e}")
        return 2
    kh = ke_hoach(bai, raw["co"])
    in_ra(f"Kho: {len(bai)} bài TikTok, {kh['khop']} khớp raw; sẽ đặt giỏ hàng TRUE "
          f"{kh['dat']['gio_hang'][True]}, FALSE {kh['dat']['gio_hang'][False]}; quảng cáo TRUE "
          f"{kh['dat']['la_quang_cao'][True]}, FALSE {kh['dat']['la_quang_cao'][False]} "
          f"({len(kh['doi'])} bài đổi); còn NULL giỏ hàng sau bước này: {len(kh['con_null'])}.")
    in_ra(f"Đọc lại {len(kh['con_null'])} bài còn NULL qua TikTok API: ước tính "
          f"{uoc_api(len(kh['con_null'])):.4f} USD ({TT.GIA_YEU_CAU} USD/video, 1 yêu cầu/video)"
          " — chỉ chạy khi có --goi-api --toi-da-usd X (và --ghi).")
    if not ns.ghi:
        in_ra("Thêm --ghi --sao-luu <tệp> để ghi.")
        return 0
    if kh["doi"]:
        _ghi_sao_luu(ns.sao_luu, ma, kh["doi"], "raw")
        n = K.ghi_co_tiktok_lo(ma, [{k: v for k, v in r.items() if k != "_cu"}
                                    for r in kh["doi"]])
        in_ra(f"Đã ghi cờ cho {n} bài (sao lưu giá trị cũ: {ns.sao_luu}).")
    if ns.goi_api and kh["con_null"]:
        cu = {b["khoa"]: {c: b.get(c) for c in _CO} for b in kh["con_null"]}
        rows, tk = goi_api(ma, kh["con_null"], ns.toi_da_usd, in_ra, bay_gio)
        _ghi_sao_luu(ns.sao_luu, ma, [{**r, "_cu": cu[r["khoa"]]} for r in rows
                                      if any(c in r for c in _CO)], "tiktok_api")
        if tk["loi"]:
            in_ra(f"TikTok API: {tk['loi']}")
            return 1
    return 0


def _chuan_bi() -> None:
    """Nạp `.env` của Mark (`APIFY_TOKEN`, `LANG_NGHE_DSN`) như các script kho khác."""
    import config  # noqa: F401 — nạp .env


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bù cờ giỏ hàng TikTok cho bài đã có trong kho")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("duong", nargs="*", help="tệp / thư mục raw (như lang_nghe_nap_raw.py)")
    ap.add_argument("--ghi", action="store_true", help="ghi vào kho (mặc định chạy thử)")
    ap.add_argument("--sao-luu", help="tệp JSONL lưu giá trị cũ (bắt buộc với --ghi)")
    ap.add_argument("--goi-api", action="store_true",
                    help="đọc lại bài còn NULL qua TikTok API (TRẢ TIỀN, cần --toi-da-usd)")
    ap.add_argument("--toi-da-usd", type=float, default=None, help="trần USD của --goi-api")
    ns = ap.parse_args(argv)
    if ns.ghi and not ns.sao_luu:
        ap.error("--ghi cần --sao-luu <tệp>")
    if ns.goi_api and (ns.toi_da_usd is None or not math.isfinite(ns.toi_da_usd)
                       or ns.toi_da_usd <= 0 or not ns.ghi):
        ap.error("--goi-api cần --toi-da-usd X (> 0) và --ghi")
    if not ns.duong and not ns.goi_api:
        ap.error("cần ít nhất một đường dẫn raw (hoặc --goi-api)")
    _chuan_bi()
    return chay(ns)


if __name__ == "__main__":
    sys.exit(main())
