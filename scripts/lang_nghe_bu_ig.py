"""Bù lịch sử Instagram KÊNH NHÀ của một dự án `lang_nghe` — script MỘT LẦN (17/10/2026).

Vì sao cần: actor theo dõi tài khoản Instagram của `/theodoi` (`apify~instagram-profile-scraper`,
0,0026 USD/tài khoản) chỉ trả 12 bài MỚI NHẤT, nên bài đăng trước ngày bắt đầu theo dõi không bao
giờ vào kho. Đo thật vòng 2 (17/10/2026): `futurizerush~instagram-profile-posts-scraper` với
`hapas.vn`, 30 ngày → 19 bài (25/09 → 12/10), trong đó 7 bài kho CHƯA có (25/09–03/10, có reel
2.133 thích / 61 bình luận), 0,0385 USD (0,01 khởi động + 0,0015 USD/bài; `postsNewerThan` lọc
ngày phía actor). Actor này chỉ dùng MỘT lần để bù, không thay actor hằng ngày.

Cách làm:
  • Nguồn: mọi nguồn Instagram loại `kenh_nha` của dự án (hoặc `--tai-khoan` trong số đó).
  • Mặc định CHẠY THỬ: in nguồn, đầu vào actor, trần và ước tính — KHÔNG gọi actor, KHÔNG ghi kho.
  • `--ap-dung`: gọi actor với `maxTotalChargeUsd` ≤ 0,10 USD, rồi lưu bằng ĐÚNG đường ghi bài
    nguồn kênh nhà của `/theodoi`: `theo_doi._dong_tu_tai_khoan` → `theo_doi.chon_bai` (kênh nhà giữ
    MỌI bài trong `NGAY_GIU` ngày, AI chỉ gán sắc thái/chủ đề, gắn `nguon_id`) →
    `lang_nghe_db.ghi_bai(kieu="theo_doi")`. Khoá bài là shortcode (`theo_doi._khoa_bai`) như bài
    đã có — bài trùng chỉ cập nhật số. Bài có bình luận nên lượt `/theodoi` sau tự cào bình luận
    (`lang_nghe_db.bai_can_lay_binh_luan`).
  • Tiền: mở MỘT lượt `theo_doi` riêng (`ma_viec` "bu-ig-…") và đóng với chi phí THẬT đọc lại theo
    run id (`apify_tool._chi_phi_cac_run`) — tiền vào trần tháng của dự án như mọi lượt theo dõi.
    Không chạy khi dự án đang có lượt theo dõi khác hoặc phần còn của tháng thấp hơn trần.

Chạy trên VPS bằng user `mark` (kho nối qua Unix socket + peer; `APIFY_TOKEN`, model đọc `.env`
của Mark qua `config`):

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_bu_ig.py hapas                  # chạy thử (0 USD)
    sudo -u mark $PY scripts/lang_nghe_bu_ig.py hapas --ap-dung        # ≤ 0,10 USD
"""
from __future__ import annotations

import argparse
import datetime
import math
import os
import pathlib
import sys
import time

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

ACTOR = "futurizerush~instagram-profile-posts-scraper"
GIA_BAI = 0.0015            # USD/bài (sự kiện `apify-default-dataset-item`, đo 17/10/2026)
GIA_KHOI = 0.01             # USD/run (`apify-actor-start`, 1 GB)
TRAN_TOI_DA = 0.10          # trần cứng của script (chủ dự án duyệt ≤ 0,10 USD)
NGAY_MAC_DINH = 30
BAI_MAC_DINH = 40           # bài tối đa mỗi tài khoản (`maxPosts`); hapas.vn 30 ngày = 19 bài
_VN = datetime.timezone(datetime.timedelta(hours=7))


def _so(v) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def doc_futurizerush(items: list) -> dict[str, dict]:
    """Item futurizerush (trường theo run thật 17/10/2026: username, postUrl, shortcode, caption,
    hashtags, likes, comments, timestamp ISO, isVideo, videoViewCount, isPinned) -> {tài khoản:
    {"ho_so", "bai", "ghi_chu"}} cùng dạng `account_tool._doc_instagram` (để dùng nguyên
    `theo_doi._dong_tu_tai_khoan`). Link luôn `/p/<shortcode>/` khi thiếu `postUrl`."""
    import apify_tool as A
    ra: dict[str, dict] = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        u = str(it.get("username") or it.get("author") or "").strip().lower()
        sc = str(it.get("shortcode") or "").strip()
        link = str(it.get("postUrl") or "") or (f"https://www.instagram.com/p/{sc}/" if sc else "")
        if not u or not link:
            continue
        tk = ra.setdefault(u, {"ho_so": {"ten": u, "tai_khoan": u, "followers": None,
                                         "link": f"https://www.instagram.com/{u}/"},
                               "bai": [], "ghi_chu": ""})
        tk["bai"].append({
            "ngay": A._to_vn(it.get("timestamp")),
            "loai": "video" if it.get("isVideo") else "bài",
            "view": _so(it.get("videoViewCount")) or None, "like": _so(it.get("likes")),
            "binh_luan": _so(it.get("comments")), "share": None,
            "noi_dung": str(it.get("caption") or ""), "link": link,
            "hashtag": [str(h).lstrip("#") for h in it.get("hashtags") or [] if h],
            "_goc": {**it, "id": sc or None},
        })
    return ra


def ke_hoach(ma: str, tai_khoan: list[str] | None, ngay: int, so_bai: int, tran: float,
             bay_gio: datetime.datetime) -> dict:
    """Đọc kho, chọn nguồn, dựng đầu vào actor. Không gọi Apify. -> {"loi"} hoặc {du_an, nguon,
    payload, limit, tran, uoc, con_thang}."""
    import lang_nghe_db as K
    du_an = K.doc_du_an(ma)
    if not du_an:
        return {"loi": f"Không có dự án '{ma}' trong kho."}
    nguon = [n for n in K.nguon_dang_theo_doi(ma)
             if n.get("nen_tang") == "instagram" and n.get("loai") == "kenh_nha"]
    if tai_khoan:
        muon = {str(t).strip().lstrip("@").lower() for t in tai_khoan}
        nguon = [n for n in nguon if str(n["dinh_danh"]).strip().lstrip("@").lower() in muon]
    if not nguon:
        return {"loi": f"Dự án {ma} không có nguồn Instagram kênh nhà nào đang theo dõi"
                       + (f" khớp {', '.join(tai_khoan)}" if tai_khoan else "") + "."}
    ten = [str(n["dinh_danh"]).strip().lstrip("@") for n in nguon]
    tu = (bay_gio - datetime.timedelta(days=ngay)).astimezone(_VN).date()
    tran = round(min(TRAN_TOI_DA, max(0.0, tran)), 2)
    uoc = round(GIA_KHOI + GIA_BAI * so_bai * len(ten), 4)
    con = max(0.0, float(du_an.get("tran_usd_thang") or 0) - K.da_tieu_thang(ma))
    return {"du_an": du_an, "nguon": nguon,
            "payload": {"usernames": ten, "maxPosts": int(so_bai),
                        "postsNewerThan": tu.isoformat()},
            "limit": int(so_bai) * len(ten), "tran": tran, "uoc": uoc, "con_thang": con}


def _chi_phi_that(run_id: str | None, in_ra) -> float | None:
    """`usageTotalUsd` THẬT của run (Apify ghi tiền chậm vài chục giây — đọc tới khi hai lần liền
    khớp, tối đa ~60 giây). None khi không đọc được."""
    import apify_tool as A
    if not run_id:
        return None
    truoc = None
    for _ in range(7):
        kq = A._chi_phi_cac_run([run_id])
        if kq.get("so_run") and not kq.get("con_song"):
            if truoc is not None and abs(kq["usd"] - truoc) < 1e-9:
                return kq["usd"]
            truoc = kq["usd"]
        time.sleep(_NGHI_GIAY)
    in_ra("Chưa đọc được tiền ổn định từ Apify — lượt ghi số mới nhất đang có.")
    return truoc


_NGHI_GIAY = 10.0


def chay(ns, in_ra=print, bay_gio: datetime.datetime | None = None) -> int:
    import apify_tool as A
    import lang_nghe_db as K
    import theo_doi as T
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    ma = ns.du_an.strip().lower()
    kh = ke_hoach(ma, ns.tai_khoan, ns.ngay, ns.so_bai, ns.tran, bay_gio)
    if kh.get("loi"):
        in_ra(kh["loi"])
        return 2
    che_do = "ÁP DỤNG" if ns.ap_dung else "CHẠY THỬ (không gọi actor, không ghi kho)"
    in_ra(f"Dự án {ma} — {che_do}.")
    in_ra("Nguồn Instagram kênh nhà: " + ", ".join(
        f"@{n['dinh_danh']} (#{n['id']})" for n in kh["nguon"]))
    in_ra(f"Actor {ACTOR}, đầu vào {kh['payload']}, tối đa {kh['limit']} bài.")
    in_ra(f"Trần maxTotalChargeUsd {kh['tran']:.2f} USD; ước tính tối đa {kh['uoc']:.4f} USD "
          f"({GIA_KHOI} khởi động + {GIA_BAI}/bài); phần còn của tháng dự án "
          f"{kh['con_thang']:.2f} USD.")
    if kh["uoc"] > kh["tran"] + 1e-9:
        in_ra(f"Ước tính vượt trần {kh['tran']:.2f} USD — giảm --so-bai (actor dừng ở trần, "
              "phần sau không lấy).")
    if not ns.ap_dung:
        in_ra("Thêm --ap-dung để gọi actor và ghi kho.")
        return 0
    if kh["con_thang"] < kh["tran"] - 1e-9:
        in_ra(f"Dừng: phần còn của tháng ({kh['con_thang']:.2f} USD) thấp hơn trần "
              f"{kh['tran']:.2f} USD.")
        return 2
    dang = K.luot_dang_chay(ma)
    if dang:
        in_ra(f"Dừng: dự án đang có lượt theo dõi {dang.get('ma_viec') or dang.get('id')} — "
              "đợi lượt đó xong rồi chạy lại.")
        return 2
    if not os.environ.get("APIFY_TOKEN", "").strip():
        in_ra("Dừng: thiếu APIFY_TOKEN trong .env của Mark.")
        return 2
    du_an, nguon = kh["du_an"], kh["nguon"]
    luot = K.mo_luot(ma, "theo_doi", ma_viec=f"bu-ig-{bay_gio:%Y%m%d%H%M}")
    items, meta, loi = [], {}, None
    moi = cu = 0
    rows: list = []
    usd = None
    try:
        try:
            items, meta = A._run_actor(ACTOR, kh["payload"], kh["limit"], None,
                                       time.monotonic() + 300, 0, tran_usd=kh["tran"],
                                       mot_phan=True, nen_tang="instagram")
        except A.LoiApify as e:
            loi, meta = e, e.meta
        in_ra(f"Actor: {meta.get('status') or meta.get('ma')}, {len(items)} bài, run "
              f"{meta.get('run_id')}" + (f" — lỗi {loi.ma}: {loi}" if loi else ""))
        ket = doc_futurizerush(items)
        theo_khoa = {str(n["dinh_danh"]).strip().lstrip("@").lower(): n for n in nguon}
        theo_nguon = {int(n["id"]): [] for n in nguon}
        for u, tk in ket.items():
            n = theo_khoa.get(u)
            if n is not None:
                theo_nguon[int(n["id"])] += T._dong_tu_tai_khoan("instagram", tk)
        han_ai = time.monotonic() + 150
        rows, tk = T.chon_bai(du_an, theo_nguon, {int(n["id"]): n for n in nguon}, han_ai,
                              bay_gio)
        if rows:
            moi, cu = K.ghi_bai(ma, luot, "theo_doi", rows)
        in_ra(f"Lọc như /theodoi: lấy {tk['lay_duoc']}, quá cũ {tk['qua_cu']}, loại trừ "
              f"{tk['loai_tru']}, giữ {tk['giu']} → {moi} bài MỚI, {cu} bài đã có (cập nhật số). "
              f"AI: {tk.get('ai') or '—'}.")
        for r in sorted(rows, key=lambda r: r["dang_luc"] or bay_gio):
            in_ra(f"  {r['khoa']}  {r['dang_luc']:%d/%m %H:%M}  {r['binh_luan'] or 0} bình luận  "
                  f"{r['link']}")
    finally:
        usd = _chi_phi_that(meta.get("run_id"), in_ra)
        if usd is None:
            usd = float(meta.get("usd") or 0) or (kh["uoc"] if meta.get("run_id") else 0.0)
        K.dong_luot(luot, trang_thai="loi" if loi is not None and not rows else "xong",
                    so_nguon=len(nguon), bai_moi=moi, bai_cap_nhat=cu, chi_phi_usd=usd,
                    loi=(f"{loi.ma}: {loi}"[:500] if loi is not None else None),
                    ghi_chu=(f"bù lịch sử Instagram kênh nhà {ns.ngay} ngày bằng {ACTOR} "
                             f"(script một lần, 17/10/2026): {len(items)} bài về, {moi} mới, "
                             f"{cu} đã có; lượt /theodoi sau cào bình luận"))
    in_ra(f"Chi phí thật: {usd:.4f} USD (lượt {luot}, tính vào trần tháng của dự án).")
    return 0 if loi is None or rows else 1


def _chuan_bi() -> None:
    """Nạp `.env` của Mark (`APIFY_TOKEN`, `LANG_NGHE_DSN`) và chỉ đường tới Hermes như `brain.py`
    — `theo_doi.chon_bai` gọi model gán nhãn qua `tai_khoan_ai` đúng như lượt `/theodoi`."""
    from config import config
    os.environ.setdefault("HERMES_HOME", config.hermes_home)
    os.environ.setdefault("PYTHONUTF8", "1")
    if config.hermes_agent_dir not in sys.path:
        sys.path.insert(0, config.hermes_agent_dir)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bù lịch sử Instagram kênh nhà (một lần)")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("--tai-khoan", nargs="*", default=None,
                    help="chỉ các tài khoản này (trong số nguồn IG kênh nhà)")
    ap.add_argument("--ngay", type=int, default=NGAY_MAC_DINH,
                    help=f"lùi bao nhiêu ngày (mặc định {NGAY_MAC_DINH})")
    ap.add_argument("--so-bai", type=int, default=BAI_MAC_DINH,
                    help=f"bài tối đa mỗi tài khoản (mặc định {BAI_MAC_DINH})")
    ap.add_argument("--tran", type=float, default=TRAN_TOI_DA,
                    help=f"maxTotalChargeUsd, tối đa {TRAN_TOI_DA}")
    ap.add_argument("--ap-dung", action="store_true", help="gọi actor và ghi kho")
    ns = ap.parse_args(argv)
    if ns.ngay < 1 or ns.so_bai < 1 or not math.isfinite(ns.tran):
        ap.error("--ngay, --so-bai phải ≥ 1; --tran là số")
    _chuan_bi()
    return chay(ns)


if __name__ == "__main__":
    sys.exit(main())
