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
  (c) TRẢ TIỀN, ĐƯỜNG CHÍNH (21/10/2026, chủ dự án: chỉ hai nhóm KOC affiliate / branding, duyệt
      tối đa 10 USD) — `--doc-ho-so --toi-da-usd X --ghi --sao-luu F`: bài còn NULL gom theo nhà
      sáng tạo, đọc HỒ SƠ (userPosts = `aweme` đầy đủ, `tiktok_api.DAY_DU`: không anchor shop =
      không giỏ) bằng `theo_doi_api.doc_ho_so_gio` — tài khoản nhiều video chưa rõ trước, lật tới
      khi thấy đủ video cần tìm / video cũ hơn video cũ nhất cần tìm / `--so-trang` trang (mặc định
      3); video khác của tài khoản đã có trong kho cũng được điền cờ (miễn phí). Mỗi tài khoản tối
      đa 1 + `--so-trang` yêu cầu × `tiktok_api.GIA_YEU_CAU`. Trần, lượt riêng ("gio-ho-so-…"),
      sổ chi phí như (b). Video không thấy trong số trang đã đọc giữ NULL, đếm "chưa đọc lại
      được". Chạy thử in trần hiệu lực, danh sách tài khoản, số video cần tìm, số yêu cầu + USD.
      An toàn khi chạy dài (soát 21/10/2026): cứ 20 tài khoản ghi kho + sao lưu + cập nhật chi phí
      đang tiêu của lượt (`lang_nghe_db.nhip_luot` — lượt khác thấy tiền đang tiêu); dừng sạch ở
      `--het-gio` (mặc định 06:50 nếu bắt đầu trước đó — trước lượt quét 07:00) hoặc sau
      `--toi-da-phut` (150, dưới 3 giờ "bỏ dở" của lượt); chết / Ctrl-C thì lượt đóng 'loi' với
      đúng tiền đã tiêu. Nên chạy từng phần ~2 USD.

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
    # 25/10/2026: phần còn gồm ngân sách tháng của bên — cùng luật `theo_doi.con_thang`.
    import theo_doi
    con = theo_doi.con_thang(ma, du_an, K.da_tieu_thang(ma))["con"]
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


# ───────────────────────────── hồ sơ nhà sáng tạo (trả tiền) ─────────────────────────────
def ke_hoach_ho_so(bai: list[dict], toi_da_usd: float | None, so_trang: int) -> dict:
    """Bài còn NULL → {"nhom": [(tài khoản, bài)], "yeu_cau", "usd", "vua_tran": số tài khoản
    đọc được trong `toi_da_usd` (None = mọi tài khoản)}. Thuần, không gọi mạng."""
    import theo_doi_api as TDA
    import tiktok_api as TT
    nhom = TDA.nhom_ho_so(bai)
    moi = 1 + max(1, int(so_trang))
    vua = len(nhom) if toi_da_usd is None else min(
        len(nhom), int(math.floor(toi_da_usd / (moi * TT.GIA_YEU_CAU) + 1e-9)))
    yc = TDA.uoc_ho_so(len(nhom), so_trang)
    return {"nhom": nhom, "yeu_cau": yc, "usd": round(yc * TT.GIA_YEU_CAU, 4), "vua_tran": vua}


#: Mặc định dừng TRƯỚC lượt quét hằng ngày 07:00 (giờ VN) và trước khi lượt bị coi là bỏ dở
#: (`lang_nghe_db.GIO_BO_DO` = 3 giờ tính từ `bat_dau`): chạy dài hơn thì chia lần.
HET_GIO_MAC_DINH = datetime.time(6, 50)
TOI_DA_PHUT = 150
LO_TAI_KHOAN = 20


def tran_hieu_luc(ma: str, toi_da_usd: float) -> tuple[float, str]:
    """(trần thật, câu giải thích) = min(X, còn tháng dự án, ngân sách Apify việc nền). Chỉ đọc."""
    import lang_nghe_db as K
    import quet_lon
    du_an = K.doc_du_an(ma) or {}
    # 25/10/2026: phần còn gồm ngân sách tháng của bên — cùng luật `theo_doi.con_thang`.
    import theo_doi
    con = theo_doi.con_thang(ma, du_an, K.da_tieu_thang(ma))["con"]
    ns_apify, _, ghi = quet_lon.ngan_sach(quet_lon.tran_usd_nen())
    tran = min(float(toi_da_usd), con, ns_apify)
    return tran, (f"trần {tran:.4f} USD = min(--toi-da-usd {toi_da_usd}, còn tháng dự án "
                  f"{con:.2f}, ngân sách Apify việc nền {ns_apify:.2f}). {ghi}")


def han_dung(bay_gio: datetime.datetime, het_gio: datetime.time | None,
             toi_da_phut: int) -> datetime.datetime:
    """Mốc phải dừng: sớm hơn của `het_gio` (hôm nay, hoặc ngày mai nếu đã qua) và bay_gio +
    `toi_da_phut`. `het_gio` None = mặc định 06:50 nếu bắt đầu trước 06:50, không thì chỉ trần phút."""
    moc = bay_gio + datetime.timedelta(minutes=max(1, int(toi_da_phut)))
    if het_gio is None:
        het_gio = HET_GIO_MAC_DINH if bay_gio.timetz().replace(tzinfo=None) < HET_GIO_MAC_DINH \
            else None
    if het_gio is not None:
        h = bay_gio.replace(hour=het_gio.hour, minute=het_gio.minute, second=0, microsecond=0)
        if h <= bay_gio:
            h += datetime.timedelta(days=1)
        moc = min(moc, h)
    return moc


def doc_ho_so(ma: str, bai: list[dict], toi_da_usd: float, so_trang: int, in_ra,
              bay_gio, *, sao_luu: str | None = None, cu: dict | None = None,
              het_gio: datetime.time | None = None, toi_da_phut: int = TOI_DA_PHUT,
              bo_qua: set[str] | frozenset = frozenset(), dong_ho=None) -> tuple[list[dict], dict]:
    """Đọc hồ sơ (`theo_doi_api.doc_ho_so_gio`) trong MỘT lượt `theo_doi` riêng, trần = min(X,
    phần còn tháng dự án, ngân sách Apify việc nền). Soát 21/10/2026: cứ `LO_TAI_KHOAN` tài khoản
    thì ghi kho + sao lưu + nhịp lượt (chi phí đã tiêu, tiến độ — `lang_nghe_db.nhip_luot`); dừng
    sạch ở `han_dung`; chết giữa chừng (kể cả Ctrl-C) thì lượt đóng 'loi' với ĐÚNG tiền đã tiêu
    (đếm theo run đã gửi). -> (dòng đã ghi, thống kê + "luot", "loi")."""
    import lang_nghe_db as K
    import theo_doi_api as TDA
    import tiktok_api as TT
    tran, cau = tran_hieu_luc(ma, toi_da_usd)
    in_ra(f"Hồ sơ TikTok: {cau}")
    tk = {"luot": None, "usd": 0.0, "loi": None, "tai_khoan": 0, "yeu_cau": 0, "thay": 0,
          "khong_doc_duoc": 0, "cap_nhat": 0}
    if tran < 2 * TT.GIA_YEU_CAU:
        tk["loi"] = "trần dưới 2 yêu cầu"
        return [], tk
    if not os.environ.get("APIFY_TOKEN", "").strip():
        tk["loi"] = "thiếu APIFY_TOKEN"
        return [], tk
    dang = K.luot_dang_chay(ma)
    if dang:
        tk["loi"] = f"dự án đang có lượt {dang.get('ma_viec') or dang.get('id')}"
        return [], tk
    dong_ho = dong_ho or (lambda: datetime.datetime.now(_VN))
    han = han_dung(bay_gio, het_gio, toi_da_phut)
    in_ra(f"Hồ sơ TikTok: dừng muộn nhất {han:%d/%m %H:%M} (giờ VN).")
    luot = K.mo_luot(ma, "theo_doi", ma_viec=f"gio-ho-so-{bay_gio:%Y%m%d%H%M}")
    tk["luot"] = luot
    so: list = []
    rows: list[dict] = []
    cu = cu or {}

    def tien() -> float:
        return round(sum(TT.GIA_YEU_CAU for m in so if isinstance(m, dict) and m.get("run_id")), 4)

    def cau_tk() -> str:
        return (f"cờ giỏ TikTok qua hồ sơ (script, 21/10/2026): {tk['tai_khoan']} tài khoản, "
                f"{tk['yeu_cau']} yêu cầu, thấy {tk['thay']} video cần tìm, chưa đọc lại được "
                f"{tk['khong_doc_duoc']}, cập nhật {tk['cap_nhat']} bài")

    def ghi_lo(lo: list[dict], x: dict) -> None:
        tk.update({k: x[k] for k in ("tai_khoan", "yeu_cau", "thay", "khong_doc_duoc")})
        tk["cap_nhat"] += K.cap_nhat_so_lieu(ma, luot, lo)
        rows.extend(lo)
        if sao_luu:
            _ghi_sao_luu(sao_luu, ma, [{**r, "_cu": cu[r["khoa"]]} for r in lo
                                       if r["khoa"] in cu and any(c in r for c in _CO)], "ho_so")
        K.nhip_luot(luot, tien(), cau_tk() + " (đang chạy)")
        in_ra(f"  … {tk['tai_khoan']} tài khoản, {tien():.4f} USD")
    trang_thai, loi = "loi", None
    try:
        _, x = TDA.doc_ho_so_gio(bai, tran, so_trang, so_run=so, ghi_lo=ghi_lo,
                                 lo=LO_TAI_KHOAN, dung=lambda: dong_ho() >= han, bo_qua=bo_qua)
        tk.update({k: x[k] for k in ("tai_khoan", "yeu_cau", "thay", "khong_doc_duoc")})
        loi = x.get("loi") or None
        trang_thai = "loi" if loi and loi != "het_gio" else "xong"
        TDA.ghi_nho_ho_so(ma, x.get("thieu") or {}, bay_gio)
    except BaseException as e:      # kể cả Ctrl-C: đóng lượt 'loi' với tiền đã tiêu rồi ném tiếp
        loi = f"{type(e).__name__}: {e}"[:300]
        raise
    finally:
        tk["usd"], tk["loi"] = tien(), loi
        K.dong_luot(luot, trang_thai=trang_thai, so_nguon=0, bai_moi=0,
                    bai_cap_nhat=tk["cap_nhat"], chi_phi_usd=tk["usd"],
                    loi=(loi or None) and str(loi)[:500],
                    ghi_chu=cau_tk() + (" — dừng vì hết giờ, chạy lại để làm tiếp"
                                        if loi == "het_gio" else ""))
    in_ra(f"Hồ sơ TikTok: {tk['tai_khoan']} tài khoản, {tk['yeu_cau']} yêu cầu, thấy "
          f"{tk['thay']} video cần tìm, chưa đọc lại được {tk['khong_doc_duoc']} (chưa thử, hoặc "
          f"hồ sơ không còn thấy video), cập nhật {tk['cap_nhat']} bài trong kho; chi phí "
          f"{tk['usd']:.4f} USD (lượt {luot}, tính vào trần tháng của dự án)"
          + (" — dừng vì hết giờ, chạy lại để làm tiếp." if loi == "het_gio" else "."))
    if loi == "het_gio":
        tk["loi"] = None
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
    ho_so = getattr(ns, "doc_ho_so", False)
    so_trang = getattr(ns, "so_trang", None) or 3
    tran = getattr(ns, "toi_da_usd", None) if ho_so else None
    if ho_so:
        try:
            tran, cau = tran_hieu_luc(ma, tran)     # chỉ đọc (soát 21/10/2026, L2)
            in_ra(f"Hồ sơ TikTok (chạy thử): {cau}")
        except Exception as e:  # noqa: BLE001 — chạy thử vẫn in kế hoạch theo --toi-da-usd
            in_ra(f"Hồ sơ TikTok: không tính được trần hiệu lực ({type(e).__name__}) — dùng "
                  f"--toi-da-usd {tran}.")
    bo_qua = (TDA_tai_khoan_moi_thu(ma, bay_gio) if getattr(ns, "theo_so_nho", False)
              else frozenset())
    hs = ke_hoach_ho_so([b for b in kh["con_null"] if _tk_bai(b) not in bo_qua], tran,
                        so_trang)
    in_ra(f"Đọc HỒ SƠ nhà sáng tạo cho bài còn NULL: {len(hs['nhom'])} tài khoản, "
          f"{sum(len(d) for _, d in hs['nhom'])} video cần tìm, tối đa {hs['yeu_cau']} yêu cầu ≈ "
          f"{hs['usd']:.4f} USD ({so_trang} trang/tài khoản)"
          + (f"; trần --toi-da-usd đủ cho {hs['vua_tran']} tài khoản đầu" if ho_so else "")
          + " — chỉ gọi API khi có --doc-ho-so --toi-da-usd X --ghi.")
    for ten, ds in hs["nhom"][:20]:
        in_ra(f"  @{ten}: {len(ds)} video")
    if not ns.ghi:
        in_ra("Thêm --ghi --sao-luu <tệp> để ghi.")
        return 0
    if kh["doi"]:
        _ghi_sao_luu(ns.sao_luu, ma, kh["doi"], "raw")
        n = K.ghi_co_tiktok_lo(ma, [{k: v for k, v in r.items() if k != "_cu"}
                                    for r in kh["doi"]])
        in_ra(f"Đã ghi cờ cho {n} bài (sao lưu giá trị cũ: {ns.sao_luu}).")
    if ho_so and kh["con_null"]:
        cu = {b["khoa"]: {c: b.get(c) for c in _CO} for b in bai}
        rows, tk = doc_ho_so(ma, kh["con_null"], ns.toi_da_usd, so_trang, in_ra, bay_gio,
                             sao_luu=ns.sao_luu, cu=cu, het_gio=getattr(ns, "het_gio", None),
                             toi_da_phut=getattr(ns, "toi_da_phut", None) or TOI_DA_PHUT,
                             bo_qua=bo_qua)
        if tk["loi"]:
            in_ra(f"Hồ sơ TikTok: {tk['loi']}")
            return 1
    if ns.goi_api and kh["con_null"]:
        cu = {b["khoa"]: {c: b.get(c) for c in _CO} for b in kh["con_null"]}
        rows, tk = goi_api(ma, kh["con_null"], ns.toi_da_usd, in_ra, bay_gio)
        _ghi_sao_luu(ns.sao_luu, ma, [{**r, "_cu": cu[r["khoa"]]} for r in rows
                                      if any(c in r for c in _CO)], "tiktok_api")
        if tk["loi"]:
            in_ra(f"TikTok API: {tk['loi']}")
            return 1
    return 0


def _tk_bai(b: dict) -> str:
    import theo_doi_api as TDA
    return TDA._tai_khoan_tt(b)


def TDA_tai_khoan_moi_thu(ma: str, bay_gio) -> set[str]:  # noqa: N802
    import theo_doi_api as TDA
    return TDA.tai_khoan_moi_thu(ma, bay_gio)


def _gio(s: str) -> datetime.time:
    try:
        return datetime.datetime.strptime(s.strip(), "%H:%M").time()
    except ValueError:
        raise argparse.ArgumentTypeError("--het-gio dạng HH:MM") from None


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
    ap.add_argument("--doc-ho-so", action="store_true",
                    help="đọc HỒ SƠ nhà sáng tạo của bài còn NULL (TRẢ TIỀN, cần --toi-da-usd)")
    ap.add_argument("--so-trang", type=int, default=3,
                    help="trang hồ sơ tối đa mỗi tài khoản (10 video/trang, mặc định 3)")
    ap.add_argument("--toi-da-usd", type=float, default=None,
                    help="trần USD của --goi-api / --doc-ho-so")
    ap.add_argument("--het-gio", type=_gio, default=None,
                    help="HH:MM giờ VN dừng sạch (mặc định 06:50 nếu bắt đầu trước 06:50)")
    ap.add_argument("--toi-da-phut", type=int, default=TOI_DA_PHUT,
                    help=f"phút chạy tối đa (mặc định {TOI_DA_PHUT}, dưới 3 giờ bỏ dở của lượt)")
    ap.add_argument("--theo-so-nho", action="store_true",
                    help="bỏ tài khoản đã thử hồ sơ trong 7 ngày (sổ nhớ của lượt quét)")
    ns = ap.parse_args(argv)
    if ns.ghi and not ns.sao_luu:
        ap.error("--ghi cần --sao-luu <tệp>")
    if ns.goi_api and (ns.toi_da_usd is None or not math.isfinite(ns.toi_da_usd)
                       or ns.toi_da_usd <= 0 or not ns.ghi):
        ap.error("--goi-api cần --toi-da-usd X (> 0) và --ghi")
    if ns.doc_ho_so and (ns.toi_da_usd is None or not math.isfinite(ns.toi_da_usd)
                         or ns.toi_da_usd <= 0):
        ap.error("--doc-ho-so cần --toi-da-usd X (> 0); không --ghi = chạy thử")
    if ns.doc_ho_so and ns.goi_api:
        ap.error("chọn một trong --doc-ho-so / --goi-api")
    if not 1 <= ns.so_trang <= 10:
        ap.error("--so-trang 1–10")
    if not ns.duong and not (ns.goi_api or ns.doc_ho_so):
        ap.error("cần ít nhất một đường dẫn raw (hoặc --goi-api / --doc-ho-so)")
    _chuan_bi()
    return chay(ns)


if __name__ == "__main__":
    sys.exit(main())
