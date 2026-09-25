"""Chế độ `trend` của `social_listen`: trend TikTok đang nổi theo QUỐC GIA, không cần từ khoá.

Vì sao có chế độ riêng — đo thật 25/09/2026, "quét trend TikTok, đủ 800 bài":
cào hashtag chung chung (#trend, #viral, #xuhuong…) cho ra một MẪU NGẪU NHIÊN, không phải
trend. Trong 800 video chỉ 255 video đăng trong 7 ngày, 292 video tiếng Anh, 95 video vừa
mới vừa tiếng Việt, và KHÔNG âm thanh nào được dùng quá một lần. Video top đầu là của một
kênh nước ngoài. Lọc lại cũng không cứu được: cách lấy mẫu đã sai từ gốc.

Cách làm ở đây:

  1. Bảng xếp hạng CHÍNH THỨC của TikTok Creative Center (actor `data_xplorer~tiktok-trends`):
     hashtag đang nổi theo quốc gia + hướng lên/xuống, và top video của quốc gia. Đúng
     vùng, đúng kỳ, ~0,0015 USD/dòng, 6–8 giây.
  2. Âm thanh + hiệu ứng: KHÔNG nguồn nào có bảng xếp hạng đáng tin cho VN (đo 25/09:
     `burbn~tiktok-trending-sounds` trả rỗng cho VN kể cả toàn cầu; `automation-lab` tự
     ghi `isFormalRanking=false`). Nên SUY RA: lấy video mới dưới các hashtag ĐANG LÊN,
     chỉ giữ video trong kỳ và đúng ngôn ngữ, rồi đếm âm thanh/hiệu ứng được NHIỀU KÊNH
     KHÁC NHAU dùng lại. Kết quả phải nói rõ là suy từ mẫu, kèm cỡ mẫu.

Mọi lượt chạy đi qua `apify_tool._call` nên tự chịu trần chi phí trên console, và chi phí
thật được ghi vào sổ audit như lần quét thường.
"""
from __future__ import annotations

import collections
import datetime
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import apify_tool as A
import chi_phi_tool
import memory_store

from tools.registry import tool_error, tool_result  # type: ignore

ACTOR_TREND = "data_xplorer~tiktok-trends"
# Creative Center chỉ mở top video cho 5 vùng này; hashtag thì nhiều vùng hơn.
_VUNG_VIDEO = {"US", "JP", "VN", "TH", "ID"}
_VUNG_HASHTAG = {"US", "FR", "DE", "IT", "ES", "GB", "AR", "AU", "BR", "CA", "CO", "EG",
                 "ID", "IL", "JP", "KR", "MY", "MX", "PH", "SA", "SG", "ZA", "TW", "TH",
                 "TR", "AE", "VN"}
# Ngôn ngữ caption coi là "của vùng". `un` = TikTok không nhận ra (caption chỉ có
# emoji/hashtag) — giữ lại, vì bỏ đi là mất cả loạt video trend không lời.
_NGON_NGU = {"VN": {"vi", "un"}, "TH": {"th", "un"}, "ID": {"id", "un"},
             "JP": {"ja", "un"}, "KR": {"ko", "un"}}
_GIA_DONG = 0.0015          # USD/dòng của ACTOR_TREND (gói FREE)
_GIA_KHOI_DONG = 0.025
_GIA_VIDEO_MAU = 0.003      # clockworks, như lần quét thường
# TikTok chỉ trả khoảng 30–70 video mỗi hashtag dù xin nhiều hơn. Đo thật 25/09/2026: xin
# 160 video/hashtag cho 5 hashtag, được 33–71 mỗi cái, một hashtag trả 0, tổng 209/800.
# Nên mẫu N video phải soi khoảng N/40 hashtag, không phải dồn vào 5 cái.
_VIDEO_MOI_HASHTAG = 40
_SO_HASHTAG_SOI_IT_NHAT = 5
_SO_HASHTAG_SOI_TOI_DA = 25
# Hashtag chiến dịch trả tiền của brand (vd #larocheposaysuperbrandday,
# #hợptáccùnglarocheposay): lên bảng vì brand mua, không phải trend tự nhiên. Không đem
# đi lấy mẫu, kẻo âm thanh/hiệu ứng của chiến dịch bị đếm thành trend (đo thật 25/09: hai
# hiệu ứng "12 kênh dùng" đều từ #larocheposaysuperbrandday).
_CHIEN_DICH = re.compile(unicodedata.normalize(
    "NFC", r"hoptac|hợptác|brandday|superbrand|collab|taitro|tàitrợ"))


def _chon_hashtag_soi(tags: list[dict], so_mau: int) -> list[str]:
    """Hashtag đem đi lấy mẫu: đủ nhiều cho `so_mau`, đang LÊN trước, bỏ chiến dịch brand."""
    k = max(_SO_HASHTAG_SOI_IT_NHAT,
            min(_SO_HASHTAG_SOI_TOI_DA, -(-so_mau // _VIDEO_MOI_HASHTAG)))
    tu_nhien = [t for t in tags
                if not _CHIEN_DICH.search(unicodedata.normalize("NFC", t["hashtag"]).lower())]
    len_ = [t["hashtag"] for t in tu_nhien if t["huong"] == "lên"]
    con = [t["hashtag"] for t in tu_nhien if t["huong"] != "lên"]
    return (len_ + con)[:k]


def _so(v, mac_dinh: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return mac_dinh


def _metric(ds, ten: str) -> int:
    for m in ds or []:
        if isinstance(m, dict) and m.get("metric") == ten:
            try:
                return int(m.get("value") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _bang_hashtag(vung: str, ky: int, n: int) -> list[dict]:
    raw = A._call(ACTOR_TREND, {"trendType": "hashtags", "countryCode": vung,
                                "hashtagPeriod": str(ky), "maxItems": n}, n)
    return [{
        "hang": x.get("Rank"), "hashtag": str(x.get("Hashtag") or "").lstrip("#"),
        "huong": {"up": "lên", "down": "xuống"}.get(str(x.get("Trend Direction")),
                                                     str(x.get("Trend Direction") or "")),
        "so_bai": x.get("Posts") or 0, "luot_xem": x.get("Video Views") or 0,
        "nganh": ", ".join(x.get("Industries") or []),
        "link": x.get("TikTok URL") or "",
    } for x in raw if x.get("Hashtag")]


def _bang_video(vung: str, ky: int, n: int, tu_nhien: bool) -> list[dict]:
    raw = A._call(ACTOR_TREND, {"trendType": "videos", "videoCountry": vung,
                                "videoPeriod": str(ky), "maxItems": n,
                                "videoOrganicOnly": tu_nhien}, n)
    return [{
        "hang": x.get("Video Rank"), "luot_xem": x.get("Views") or 0,
        "luot_xem_tu_nhien": _metric(x.get("Metrics"), "Organic Views"),
        "kenh": x.get("Author Handle") or x.get("Author") or "",
        "followers": x.get("Followers") or 0,
        "tieu_de": str(x.get("Title") or "")[:200],
        "chu_de": ", ".join(x.get("Content Tags") or []),
        "link": x.get("Video TikTok URL") or "",
    } for x in raw]


def _mau_am_thanh(tags: list[str], n: int, vung: str, ky: int) -> dict:
    """Lấy mẫu video dưới `tags` rồi đếm âm thanh/hiệu ứng nhiều kênh dùng lại."""
    per = max(1, n // max(1, len(tags)))
    raw = A._call(A._ACTORS["tiktok_fallback"], {"hashtags": tags, "resultsPerPage": per}, n)
    moc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=ky)
    ngon_ngu = _NGON_NGU.get(vung)
    giu = []
    for it in raw:
        dt = A._to_vn(it.get("createTimeISO"))
        if not dt or dt < moc or it.get("isAd"):
            continue
        if ngon_ngu and str(it.get("textLanguage") or "un") not in ngon_ngu:
            continue
        giu.append(it)

    am = collections.defaultdict(lambda: {"kenh": set(), "video": 0, "view": 0, "tag": set()})
    hu = collections.defaultdict(lambda: {"kenh": set(), "video": 0, "tag": set()})
    ten_am: dict[str, tuple[str, str]] = {}
    for it in giu:
        kenh = (it.get("authorMeta") or {}).get("name") or ""
        m = it.get("musicMeta") or {}
        if m.get("musicId"):
            k = str(m["musicId"])
            a = am[k]
            a["kenh"].add(kenh); a["video"] += 1; a["view"] += int(it.get("playCount") or 0)
            a["tag"].add(str(it.get("input") or ""))
            ten_am[k] = (str(m.get("musicName") or ""), str(m.get("musicAuthor") or ""))
        for e in it.get("effectStickers") or []:
            if isinstance(e, dict) and e.get("name"):
                h = hu[str(e["name"])]
                h["kenh"].add(kenh); h["video"] += 1; h["tag"].add(str(it.get("input") or ""))

    # Chỉ tính là tín hiệu khi >= 2 KÊNH KHÁC NHAU dùng: một kênh đăng 5 video bằng âm
    # gốc của chính mình không phải trend.
    am_thanh = sorted(({
        "ten": ten_am[k][0], "tac_gia": ten_am[k][1], "so_kenh": len(v["kenh"]),
        "so_video": v["video"], "tong_view": v["view"],
        "di_kem_hashtag": ", ".join(sorted(t for t in v["tag"] if t)),
        "link": f"https://www.tiktok.com/music/x-{k}",
    } for k, v in am.items() if len(v["kenh"]) >= 2),
        key=lambda x: (-x["so_kenh"], -x["tong_view"]))[:15]
    # `di_kem_hashtag` để phân biệt trend tự nhiên với chiến dịch brand: đo thật 25/09,
    # hai hiệu ứng được 12 kênh dùng đều nằm dưới #larocheposaysuperbrandday.
    hieu_ung = sorted(({"ten": k, "so_kenh": len(v["kenh"]), "so_video": v["video"],
                        "di_kem_hashtag": ", ".join(sorted(t for t in v["tag"] if t))}
                       for k, v in hu.items() if len(v["kenh"]) >= 2),
                      key=lambda x: -x["so_kenh"])[:10]
    return {"cao": len(raw), "giu": len(giu), "am_thanh": am_thanh, "hieu_ung": hieu_ung,
            "cao_du": len(raw) >= n}


def chay(args: dict) -> str:
    vung = (str(args.get("country") or "VN").strip() or "VN").upper()
    if vung not in _VUNG_HASHTAG:
        return tool_error(f"Creative Center chưa có trend cho vùng {vung}. Có: "
                          f"{', '.join(sorted(_VUNG_HASHTAG))}.")
    ky = 30 if str(args.get("ky_ngay") or "7").strip() == "30" else 7
    so_tag = _so(args.get("so_hashtag"), 20, 5, 100)
    so_vid = _so(args.get("so_video"), 20, 5, 100) if vung in _VUNG_VIDEO else 0
    tu_nhien = args.get("chi_tu_nhien") is not False
    tran_bai, _ = A._tran()
    so_mau = _so(args.get("so_video_mau"), 100, 20, tran_bai) \
        if args.get("soi_am_thanh") is not False else 0

    # Lấy bảng hashtag DÀI hơn số cần báo khi mẫu lớn: cần đủ hashtag để soi (xem
    # `_chon_hashtag_soi`), mà mỗi dòng chỉ 0,0015 USD.
    k = -(-so_mau // _VIDEO_MOI_HASHTAG) if so_mau else 0
    n_tag = max(so_tag, min(100, 2 * k + 10)) if so_mau else so_tag
    est = (_GIA_KHOI_DONG * (1 + bool(so_vid)) + _GIA_DONG * (n_tag + so_vid)
           + _GIA_VIDEO_MAU * so_mau)
    bat_dau = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=5)
    t0 = time.monotonic()
    loi: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_tag = ex.submit(_bang_hashtag, vung, ky, n_tag)
        f_vid = ex.submit(_bang_video, vung, ky, so_vid, tu_nhien) if so_vid else None
        try:
            tat_ca_tag = f_tag.result(timeout=A._TOOL_DEADLINE)
        except Exception as e:  # noqa: BLE001
            tat_ca_tag, loi["hashtag"] = [], f"{type(e).__name__}: {e}"[:250]
        tags = tat_ca_tag[:so_tag]
        try:
            vids = f_vid.result(timeout=A._TOOL_DEADLINE) if f_vid else []
        except Exception as e:  # noqa: BLE001
            vids, loi["video"] = [], f"{type(e).__name__}: {e}"[:250]

    mau = {"cao": 0, "giu": 0, "am_thanh": [], "hieu_ung": [], "cao_du": True}
    dang_len = _chon_hashtag_soi(tat_ca_tag, so_mau) if so_mau else []
    if so_mau and dang_len:
        try:
            mau = _mau_am_thanh(dang_len, so_mau, vung, ky)
        except Exception as e:  # noqa: BLE001
            loi["am_thanh"] = f"{type(e).__name__}: {e}"[:250]

    actors = [ACTOR_TREND] + ([A._ACTORS["tiktok_fallback"]] if so_mau else [])
    thuc = A._chi_phi_thuc(actors, bat_dau, est)
    du = len(tat_ca_tag) >= n_tag and len(vids) >= so_vid and mau["cao_du"]
    if thuc and thuc.get("cham_tran") and du:
        thuc = {**thuc, "cham_tran": 0}
    chi_phi_tool.ghi(queries=[f"trend {vung}"], platforms=["tiktok"],
                     date_range=f"{ky} ngày gần nhất", thuc=thuc, est=est)

    if not tags and not vids:
        return tool_error("Không lấy được bảng trend: " + "; ".join(
            f"{k}: {v}" for k, v in loi.items()))

    url, granted = None, False
    title = (args.get("title") or "").strip() or \
        f"Trend TikTok {vung} · {ky} ngày · {datetime.datetime.now(A._VN_TZ):%d-%m-%Y}"
    rows = [["Loại", "Hạng", "Tên", "Hướng / Kênh", "Số bài / Số kênh dùng",
             "Lượt xem", "Ghi chú", "Link"]]
    rows += [["Hashtag", t["hang"], "#" + t["hashtag"], t["huong"], t["so_bai"],
              t["luot_xem"], t["nganh"], t["link"]] for t in tags]
    rows += [["Video", v["hang"], v["tieu_de"], v["kenh"], "", v["luot_xem"],
              f"tự nhiên {v['luot_xem_tu_nhien']} · {v['chu_de']}", v["link"]] for v in vids]
    rows += [["Âm thanh (suy từ mẫu)", i + 1, a["ten"], a["tac_gia"], a["so_kenh"],
              a["tong_view"], f"{a['so_video']} video · #{a['di_kem_hashtag']}", a["link"]]
             for i, a in enumerate(mau["am_thanh"])]
    rows += [["Hiệu ứng (suy từ mẫu)", i + 1, h["ten"], "", h["so_kenh"], "",
              f"{h['so_video']} video · #{h['di_kem_hashtag']}", ""]
             for i, h in enumerate(mau["hieu_ung"])]
    try:
        tok, url = A._create_sheet(title)
        A._write_values(tok, A._first_sheet_id(tok), rows)
        sender = memory_store.get_current_sender()
        granted = A._grant(tok, sender) if sender else False
    except Exception as e:  # noqa: BLE001
        loi["sheet"] = f"{type(e).__name__}: {e}"[:250]

    return tool_result(
        success=not loi, che_do="trend", vung=vung, ky_ngay=ky,
        nguon=("Bảng xếp hạng chính thức TikTok Creative Center (hashtag + video). "
               "Âm thanh/hiệu ứng SUY từ mẫu video dưới các hashtag đang lên."),
        hashtag=tags, video=vids, chi_video_tu_nhien=tu_nhien,
        am_thanh=mau["am_thanh"], hieu_ung=mau["hieu_ung"],
        mau_am_thanh={"hashtag_da_soi": dang_len if so_mau else [], "da_cao": mau["cao"],
                      "giu_lai_trong_ky_dung_ngon_ngu": mau["giu"]},
        loi=loi or None, sheet_url=url, granted=granted, title=title,
        uoc_tinh_chi_phi_usd=round(est, 3),
        chi_phi_thuc_usd=thuc["usd"] if thuc and thuc.get("so_run") else None,
        cham_tran_chi_phi=bool(thuc and thuc.get("cham_tran")),
        chi_phi=A._dong_chi_phi(thuc, est),
        giay=round(time.monotonic() - t0, 1),
    )
