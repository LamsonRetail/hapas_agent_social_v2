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
  2. Âm thanh + hiệu ứng SUY RA: lấy video mới dưới các hashtag ĐANG LÊN, chỉ giữ video
     trong kỳ và đúng ngôn ngữ, rồi đếm âm thanh/hiệu ứng được NHIỀU KÊNH KHÁC NHAU dùng
     lại. Kết quả phải nói rõ là suy từ mẫu, kèm cỡ mẫu. Tách "nhạc (bài hát) dùng lại"
     với "âm thanh gốc" (`musicMeta.musicOriginal`): hai thứ khác hẳn về cách dùng cho
     brand — bài hát có bản quyền, âm thanh gốc là format/giọng nói của một kênh.
  3. Bảng "nhạc đang lên" của Creative Center (`burbn~tiktok-trending-sounds`), chạy song
     song. Đo 25/09: actor này trả RỖNG cho VN (cả toàn cầu) — nên khi rỗng phải nói thẳng
     là không có bảng cho VN, TUYỆT ĐỐI không lấy bảng nước khác thay vào.

Trần chi phí: cả lượt trend là MỘT lượt TikTok — mọi lượt actor con (bảng hashtag, top
video, lấy mẫu, bảng nhạc) cộng lại phải gọn trong trần TikTok trên console (`tran_usd_tiktok`,
`tran_bai_tiktok`, `bat_tiktok`; Năng lực → Quét mạng xã hội). E2E 04-05/10/2026: trend từng
đọc trần CHUNG (`A._tran()`) và gọi `_call` không kèm `nen_tang`, nên một lượt cào hashtag
5×30 = 150 video tiêu 0,45 USD trong khi trần TikTok là 0,17 USD. Nay `_ke_hoach` chia trần
cho từng lượt con theo thứ tự ưu tiên, cắt hoặc bỏ lượt kém ưu tiên khi không đủ (và nói ra),
mỗi lượt `_call` mang `nen_tang="tiktok"` và trần USD riêng = phần được chia. Chi phí thật
được ghi vào sổ audit như lần quét thường.
"""
from __future__ import annotations

import collections
import contextvars
import datetime
import math
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import apify_tool as A
import chi_phi_tool
import memory_store
import nganh_tiktok

from tools.registry import tool_error, tool_result  # type: ignore

ACTOR_TREND = "data_xplorer~tiktok-trends"
ACTOR_NHAC = "burbn~tiktok-trending-sounds"
# Creative Center chỉ mở top video cho 5 vùng này; hashtag thì nhiều vùng hơn.
_VUNG_VIDEO = {"US", "JP", "VN", "TH", "ID"}
_VUNG_HASHTAG = {"US", "FR", "DE", "IT", "ES", "GB", "AR", "AU", "BR", "CA", "CO", "EG",
                 "ID", "IL", "JP", "KR", "MY", "MX", "PH", "SA", "SG", "ZA", "TW", "TH",
                 "TR", "AE", "VN"}
# Vùng mà actor nhạc nhận (enum `country_code` trong README của actor, 01/10/2026).
_VUNG_NHAC = {"AU", "BR", "CA", "EG", "FR", "DE", "ID", "IL", "IT", "JP", "MY", "PH", "RU",
              "SA", "SG", "KR", "ES", "TW", "TH", "TR", "AE", "GB", "US", "VN"}
# Ngôn ngữ caption coi là "của vùng". `un` = TikTok không nhận ra (caption chỉ có
# emoji/hashtag) — giữ lại, vì bỏ đi là mất cả loạt video trend không lời.
_NGON_NGU = {"VN": {"vi", "un"}, "TH": {"th", "un"}, "ID": {"id", "un"},
             "JP": {"ja", "un"}, "KR": {"ko", "un"}}
_GIA_DONG = 0.0015          # USD/dòng của ACTOR_TREND (gói FREE)
_GIA_KHOI_DONG = 0.025
_GIA_VIDEO_MAU = 0.003      # clockworks, như lần quét thường
_GIA_NHAC_KHOI_DONG = 0.02  # burbn, gói FREE: 0,02/lượt (ghim 1 GB) + 0,02/bài
_GIA_NHAC = 0.02
_BIEN = 0.9                 # cả lượt trend chỉ xin tới 90% trần USD TikTok
# Bảng hashtag/top video ít hơn chừng này dòng thì không đáng một lượt khởi chạy.
_TOI_THIEU_BANG = 5
# TikTok chỉ trả khoảng 30–70 video mỗi hashtag dù xin nhiều hơn. Đo thật 25/09/2026: xin
# 160 video/hashtag cho 5 hashtag, được 33–71 mỗi cái, một hashtag trả 0, tổng 209/800.
# Nên mẫu N video phải soi khoảng N/40 hashtag, không phải dồn vào 5 cái.
_VIDEO_MOI_HASHTAG = 40
_SO_HASHTAG_SOI_IT_NHAT = 5
_SO_HASHTAG_SOI_TOI_DA = 25
# Đo 01/10/2026: xin mẫu 100 video → cào được 40, giữ được 21 (lọc kỳ + ngôn ngữ bỏ gần
# một nửa). Nên xin DƯ 2,5 lần số cần giữ, và còn thiếu thì cào thêm một lượt dưới các
# hashtag CHƯA soi (vẫn trong trần mỗi lượt).
_HE_SO_XIN = 2.5
_CON_GIAY_DE_CAO_THEM = 60
# Còn ít hơn chừng này giây thì bỏ hẳn lượt lấy mẫu âm thanh (nói rõ), khỏi chạy dở.
_TOI_THIEU_GIAY_MAU = 30


def _trong_han(han_run: float, fn, *a):
    """Chạy `fn` với hạn chót + sổ run của apify_tool: tới hạn thì run bị huỷ và `_call`
    trả phần đã lấy thay vì ném QUA_GIO. Gọi trong `contextvars.copy_context().run`."""
    A._SO_RUN.set([])
    A._HAN_CHOT.set(han_run)
    return fn(*a)
# Lượt cào thêm dùng PHẦN CÒN LẠI của trần mỗi lượt sau lượt đầu, không phải cả trần lần
# nữa (rà 01/10/2026: hai lượt mỗi lượt 90% trần = tiêu gần gấp đôi). Còn ít hơn chừng
# này video thì thôi, không đáng một lượt khởi chạy.
_MAU_THEM_TOI_THIEU = 20
# Hashtag chiến dịch trả tiền của brand (vd #larocheposaysuperbrandday,
# #hợptáccùnglarocheposay): lên bảng vì brand mua, không phải trend tự nhiên. Không đem
# đi lấy mẫu, kẻo âm thanh/hiệu ứng của chiến dịch bị đếm thành trend (đo thật 25/09: hai
# hiệu ứng "12 kênh dùng" đều từ #larocheposaysuperbrandday).
_CHIEN_DICH = re.compile(unicodedata.normalize(
    "NFC", r"hoptac|hợptác|brandday|superbrand|collab|taitro|tàitrợ"))
# Hashtag chủ đề NHẠY CẢM: brand không nên bám. 01/10/2026 Mark gợi ý móc nội dung vào
# #traibuonnguoi chỉ vì nó đang lên bảng.
# Hai cách so, vì bản đầu so GỐC NGẮN trên chữ bỏ dấu và báo nhầm (rà 01/10/2026):
# "crochet"/"crochetbag" chứa "chet" (túi móc len — trend ĐÚNG ngành của brand túi!),
# "tainan" là thành phố Đài Nam, "thientai" vừa là "thiên tai" vừa là "thiên tài".
#   1. Regex trên chữ đã BỎ DẤU, viết liền: chỉ cụm DÀI, đặc thù tiếng Việt, đã soát
#      không trùng tiếng Anh/địa danh. Gốc ngắn mơ hồ ("tainan", "chet", "giet") chỉ tính
#      khi đi kèm hậu tố tiếng Việt rõ nghĩa.
#   2. Chuỗi CÓ DẤU (chữ thường, NFC, viết liền): có dấu thì không còn trùng tiếng Anh.
#      Không có "chết"/"giết" trơn: "chếtcười", "đẹpchếtmất" là tiếng lóng khen,
#      "giếtthờigian" là giết thời gian.
_NHAY_CAM = (
    ("buôn người", r"buonnguoi|buonban(?:noitang|treem|phunu)", ("buônngười",)),
    ("lừa đảo / bắt cóc", r"luadao|batcoc|mattich", ("lừađảo", "bắtcóc", "mấttích")),
    ("tai nạn / thiên tai",
     r"(?:vu|gay|bi)tainan|tainan(?:giaothong|xe|lienhoan|thamkhoc|kinhhoang|nghiemtrong"
     r"|chetnguoi|laodong|maybay|hamtau)|lulut|ngaplut|satlodat|dongdat|chayno|hoahoan"
     # "thientai" trơn bỏ dấu trùng "thiên tài" nên chỉ tính khi kèm ngữ cảnh thảm hoạ;
     # hashtag cứu trợ/bão lũ thì brand cũng không nên bám (review 01/10/2026).
     r"|thientai(?:mientrung|cuutro|lulut|baolu|thamkhoc|ungho)|cuutro|baolu",
     ("tainạn", "thiêntai", "lũlụt", "độngđất", "cháynổ", "hỏahoạn", "hoảhoạn")),
    # Không có "quadoi": bỏ dấu thì "qua đời" trùng "quà đôi" — hashtag quà tặng của brand.
    ("chết chóc",
     r"tuvong|nguoichet|chetnguoi|chetchoc|xacchet|caichet|gietnguoi|giethai|satnhan"
     r"|vuanmang|anmang(?!a)",                       # "batmanmanga" chứa "anmang"
     ("tửvong", "quađời", "ánmạng", "giếtngười", "giếthại", "bịgiết", "xácchết",
      "cáichết", "chếtchóc")),
    ("bạo lực", r"baoluc|danhnhau|hiepdam|xamhai|khungbo|chientranh",
     ("bạolực", "đánhnhau", "hiếpdâm", "xâmhại", "khủngbố", "chiếntranh")),
    ("ma tuý", r"matuy", ("matúy", "matuý")),
    # "baucua" (bầu cua — trò chơi Tết) chứa "baucu".
    ("chính trị", r"chinhtri|bieutinh|baucu(?!a)", ("chínhtrị", "biểutình", "bầucử")),
    ("tôn giáo", r"tongiao|phatgiao|congiao|thienchua",
     ("tôngiáo", "phậtgiáo", "côngiáo", "thiênchúa")),
    ("scandal", r"scandal|bocphot", ("bócphốt",)),
)
_NHAY_CAM_RE = tuple((nhan, re.compile(rx), co_dau) for nhan, rx, co_dau in _NHAY_CAM)
_AM_GOC_RE = re.compile(r"^\s*(original sound|âm thanh gốc|nhạc nền|son original|"
                        r"sonido original|suara asli|som original)", re.I)


def _khong_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower().replace("đ", "d"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def _co_dau(s: str) -> str:
    """Chữ thường NFC, viết liền, GIỮ dấu."""
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFC", str(s or "").lower()))


def _nhay_cam(tag: str) -> str:
    """Chủ đề nhạy cảm của hashtag, "" nếu không."""
    k, d = _khong_dau(tag), _co_dau(tag)
    for nhan, rx, co_dau in _NHAY_CAM_RE:
        if rx.search(k) or any(g in d for g in co_dau):
            return nhan
    return ""


def _thu_tu_soi(tags: list[dict]) -> list[str]:
    """Mọi hashtag có thể đem lấy mẫu: đang LÊN trước, bỏ chiến dịch brand và chủ đề nhạy cảm."""
    tu_nhien = [t for t in tags
                if not _CHIEN_DICH.search(unicodedata.normalize("NFC", t["hashtag"]).lower())
                and not _nhay_cam(t["hashtag"])]
    len_ = [t["hashtag"] for t in tu_nhien if t["huong"] == "lên"]
    con = [t["hashtag"] for t in tu_nhien if t["huong"] != "lên"]
    return len_ + con


def _so_hashtag_soi(so_mau: int) -> int:
    return max(_SO_HASHTAG_SOI_IT_NHAT,
               min(_SO_HASHTAG_SOI_TOI_DA, -(-so_mau // _VIDEO_MOI_HASHTAG)))


def _chon_hashtag_soi(tags: list[dict], so_mau: int) -> list[str]:
    """Hashtag đem đi lấy mẫu: đủ nhiều cho `so_mau`, đang LÊN trước, bỏ chiến dịch brand."""
    return _thu_tu_soi(tags)[:_so_hashtag_soi(so_mau)]


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


def _first(d: dict, *names, default=""):
    for n in names:
        v = d.get(n)
        if v not in (None, ""):
            return v
    return default


def _bang_hashtag(vung: str, ky: int, n: int, nganh_id: str = "",
                  tran_usd: float | None = None) -> list[dict]:
    """`nganh_id`: `industryId` của actor (mã 11 số của ngành cha, xem nganh_tiktok) —
    actor lọc phía nó nên không tốn thêm tiền; rỗng = mọi ngành như trước. `tran_usd`:
    phần trần TikTok `_ke_hoach` chia cho lượt này."""
    payload = {"trendType": "hashtags", "countryCode": vung, "hashtagPeriod": str(ky),
               "maxItems": n}
    if nganh_id:
        payload["industryId"] = nganh_id
    raw = A._call(ACTOR_TREND, payload, n, tran_usd=tran_usd, nen_tang="tiktok")
    return [{
        "hang": x.get("Rank"), "hashtag": str(x.get("Hashtag") or "").lstrip("#"),
        "huong": {"up": "lên", "down": "xuống"}.get(str(x.get("Trend Direction")),
                                                     str(x.get("Trend Direction") or "")),
        "so_bai": x.get("Posts") or 0, "luot_xem": x.get("Video Views") or 0,
        "nganh": ", ".join(x.get("Industries") or []),
        "link": x.get("TikTok URL") or "",
    } for x in raw if x.get("Hashtag")]


def _bang_video(vung: str, ky: int, n: int, tu_nhien: bool,
               tran_usd: float | None = None) -> list[dict]:
    raw = A._call(ACTOR_TREND, {"trendType": "videos", "videoCountry": vung,
                                "videoPeriod": str(ky), "maxItems": n,
                                "videoOrganicOnly": tu_nhien}, n,
                  tran_usd=tran_usd, nen_tang="tiktok")
    return [{
        "hang": x.get("Video Rank"), "luot_xem": x.get("Views") or 0,
        "luot_xem_tu_nhien": _metric(x.get("Metrics"), "Organic Views"),
        "kenh": x.get("Author Handle") or x.get("Author") or "",
        "followers": x.get("Followers") or 0,
        "tieu_de": str(x.get("Title") or "")[:200],
        "chu_de": ", ".join(x.get("Content Tags") or []),
        "link": x.get("Video TikTok URL") or "",
    } for x in raw]


def _bang_nhac(vung: str, ky: int, n: int, tran_usd: float | None = None) -> list[dict]:
    """Bảng nhạc đang lên của Creative Center. Shape đầu ra actor không công bố (01/10/2026)
    nên map phòng thủ nhiều tên trường; dòng của nước KHÁC thì bỏ, không bao giờ trình bày
    như của `vung`."""
    raw = A._call(ACTOR_NHAC, {"country_code": vung, "period": str(ky),
                               "rank_type": "surging", "new_on_board": "false",
                               "commercial_music": "false", "maxResults": n,
                               "limit": min(20, n)}, n, mem=1024,
                 tran_usd=tran_usd, nen_tang="tiktok")
    out = []
    for x in raw:
        if not isinstance(x, dict) or x.get("error"):
            continue
        nuoc = str(_first(x, "country_code", "countryCode", "country")).upper()
        if nuoc and nuoc != vung:
            continue
        ten = _first(x, "title", "song_name", "songName", "name", "music_name")
        if not ten:
            continue
        out.append({
            "hang": _first(x, "rank", "ranking", "position", default=len(out) + 1),
            "ten": str(ten)[:150],
            "tac_gia": str(_first(x, "author", "artist", "creator", "singer"))[:100],
            "thay_doi_hang": _first(x, "rank_diff", "rankDiff", "rank_change"),
            "moi_vao_bang": bool(_first(x, "is_new", "new_on_board", "isNew", default=False)),
            "link": str(_first(x, "link", "url", "tiktok_url", "music_url", "sound_url")),
        })
    return out[:n]


def _suc(ngan_sach: float) -> int:
    """Số video mẫu mua được bằng `ngan_sach` USD."""
    return int(max(0.0, ngan_sach) / _GIA_VIDEO_MAU + 1e-9)


def _so_xin(so_mau: int, tran_bai: int, ngan_sach: float) -> int:
    """Số video xin ở lượt cào đầu: dư `_HE_SO_XIN` lần, nhưng gọn trong trần bài và ngân
    sách USD của phần lấy mẫu."""
    return max(1, min(tran_bai, _suc(ngan_sach), math.ceil(so_mau * _HE_SO_XIN)))


def _gia_bang(n: int) -> float:
    return _GIA_KHOI_DONG + _GIA_DONG * n if n else 0.0


def _gia_nhac(n: int) -> float:
    return _GIA_NHAC_KHOI_DONG + _GIA_NHAC * n if n else 0.0


def _dong_vua(con: float, khoi_dong: float, gia: float) -> int:
    """Số dòng mua được bằng `con` USD sau phí khởi động."""
    return max(0, int((con - khoi_dong) / gia + 1e-9))


def _ke_hoach(tran_usd: float, tran_bai: int, so_tag: int, so_vid: int, so_mau: int,
              so_nhac: int) -> dict:
    """Chia trần USD TikTok cho CẢ lượt trend (E2E 04-05/10/2026, xem docstring module).

    Ngân sách = `_BIEN` × trần. Thứ tự ưu tiên: bảng hashtag > top video > lượt lấy mẫu
    đầu (kèm dòng hashtag thêm để có chỗ soi) > bảng nhạc > lượt cào thêm mẫu. Lượt nào
    không đủ thì CẮT số dòng, dưới mức tối thiểu thì BỎ — ghi vào `cat` để nói ra.
    `tran` là trần USD gửi kèm từng lượt `_call`; tổng của chúng <= ngân sách <= trần.
    `tu_choi` = trần không đủ cả bảng hashtag tối thiểu."""
    ngan_sach = _BIEN * tran_usd
    con, cat = ngan_sach, []
    # 1. Bảng hashtag — lõi của trend, không đủ thì không chạy gì.
    n_tag = min(so_tag, _dong_vua(con, _GIA_KHOI_DONG, _GIA_DONG))
    if n_tag < min(so_tag, _TOI_THIEU_BANG):
        return {"tu_choi": True, "ngan_sach": ngan_sach, "cat": cat}
    if n_tag < so_tag:
        cat.append(f"bảng hashtag còn {n_tag}/{so_tag} dòng")
    con -= _gia_bang(n_tag)
    # 2. Top video.
    n_vid = 0
    if so_vid:
        n_vid = min(so_vid, _dong_vua(con, _GIA_KHOI_DONG, _GIA_DONG))
        if n_vid < min(so_vid, _TOI_THIEU_BANG):
            n_vid = 0
            cat.append("bỏ bảng top video")
        elif n_vid < so_vid:
            cat.append(f"top video còn {n_vid}/{so_vid}")
        con -= _gia_bang(n_vid)
    # 3. Lượt lấy mẫu đầu, kèm dòng hashtag thêm để có đủ hashtag mà soi (0,0015 USD/dòng).
    n1 = them_tag = muon = 0
    if so_mau:
        muon = _so_xin(so_mau, tran_bai, 10 ** 6)
        k = -(-so_mau // _VIDEO_MOI_HASHTAG)
        them_tag = max(0, min(100, 2 * k + 10) - n_tag)
        n1 = min(muon, _suc(con - _GIA_DONG * them_tag))
        if n1 < _MAU_THEM_TOI_THIEU:
            n1 = them_tag = 0
            cat.append("bỏ lấy mẫu âm thanh/hiệu ứng")
        elif n1 < muon:
            cat.append(f"lấy mẫu âm thanh còn {n1}/{muon} video")
        con -= _GIA_DONG * them_tag + _GIA_VIDEO_MAU * n1
    # 4. Bảng nhạc đang lên (0,02 USD/bài).
    n_nhac = 0
    if so_nhac:
        n_nhac = min(so_nhac, _dong_vua(con, _GIA_NHAC_KHOI_DONG, _GIA_NHAC))
        if not n_nhac:
            cat.append("bỏ bảng nhạc đang lên")
        elif n_nhac < so_nhac:
            cat.append(f"bảng nhạc còn {n_nhac}/{so_nhac} bài")
        con -= _gia_nhac(n_nhac)
    # 5. Lượt cào thêm mẫu: chỉ phần còn lại (tối đa 6 lần số cần + 1, như trước).
    them_mau = min(tran_bai, 6 * so_mau + 1, _suc(con)) if n1 else 0
    tran = {"hashtag": round(_gia_bang(n_tag + them_tag), 4),
            "video": round(_gia_bang(n_vid), 4),
            "mau": round(_GIA_VIDEO_MAU * (n1 + them_mau), 4),
            "nhac": round(_gia_nhac(n_nhac), 4)}
    k_du = -(-so_mau // _VIDEO_MOI_HASHTAG) if so_mau else 0
    est_xin = (_gia_bang(max(so_tag, min(100, 2 * k_du + 10) if so_mau else 0))
               + _gia_bang(so_vid) + _GIA_VIDEO_MAU * muon + _gia_nhac(so_nhac))
    return {"tu_choi": False, "ngan_sach": ngan_sach, "cat": cat, "tran": tran,
            "est": round(sum(tran.values()), 4), "est_xin": round(est_xin, 4),
            "n_tag": n_tag, "them_tag": them_tag, "n_vid": n_vid, "n1": n1,
            "them_mau": them_mau, "n_nhac": n_nhac}


def _cao_mau(tags: list[str], n: int, tran_usd: float | None = None) -> list[dict]:
    per = max(1, -(-n // max(1, len(tags))))
    return A._call(A._ACTORS["tiktok_fallback"], {"hashtags": tags, "resultsPerPage": per}, n,
                   tran_usd=tran_usd, nen_tang="tiktok")


def _khoa_video(it: dict) -> str:
    return str(it.get("id") or it.get("webVideoUrl") or
               (str((it.get("authorMeta") or {}).get("name")), it.get("createTimeISO"),
                str((it.get("musicMeta") or {}).get("musicId"))))


def _la_am_goc(m: dict) -> bool:
    goc = m.get("musicOriginal")
    if isinstance(goc, bool):
        return goc
    if isinstance(goc, str) and goc.strip().lower() in ("true", "false"):
        return goc.strip().lower() == "true"
    # Thiếu trường: tên kiểu "original sound - <kênh>" / "âm thanh gốc - …" là âm gốc.
    return bool(_AM_GOC_RE.search(str(m.get("musicName") or "")))


def _mau_am_thanh(thu_tu: list[str], so_mau: int, vung: str, ky: int,
                  tran_bai: int = 10 ** 6, ngan_sach: float = 9.0,
                  con_giay: float = 0.0, n1: int | None = None) -> dict:
    """Lấy mẫu video dưới các hashtag theo `thu_tu` rồi đếm âm thanh/hiệu ứng nhiều kênh dùng lại.

    `ngan_sach`: USD của CẢ phần lấy mẫu (hai lượt cộng lại), do `_ke_hoach` chia từ trần
    TikTok; `n1`: số video lượt đầu theo kế hoạch."""
    suc = max(1, _suc(ngan_sach))                               # video cả hai lượt
    n1 = max(1, min(n1, suc)) if n1 else _so_xin(so_mau, tran_bai, ngan_sach)
    k1 = _so_hashtag_soi(n1)
    t0 = time.monotonic()
    moc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=ky)
    ngon_ngu = _NGON_NGU.get(vung)

    def loc(raw: list[dict]) -> list[dict]:
        giu = []
        for it in raw:
            dt = A._to_vn(it.get("createTimeISO"))
            if not dt or dt < moc or it.get("isAd"):
                continue
            if ngon_ngu and str(it.get("textLanguage") or "un") not in ngon_ngu:
                continue
            giu.append(it)
        return giu

    da_soi = thu_tu[:k1]
    raw = _cao_mau(da_soi, n1, round(n1 * _GIA_VIDEO_MAU, 4))
    da_thay = {_khoa_video(it) for it in raw}
    giu = loc(raw)
    cao, da_xin, so_luot = len(raw), n1, 1
    con_lai = thu_tu[k1:]
    # Ngân sách lượt hai = ngân sách mẫu − tiền lượt đầu THẬT tiêu (actor tính theo video
    # trả về). Lượt đầu cào ít — đúng lúc cần lượt hai — thì còn nhiều; cào gần đủ thì
    # còn ít và lượt hai bị bỏ.
    suc2 = suc - len(raw)
    if (len(giu) < so_mau and con_lai and raw and suc2 >= _MAU_THEM_TOI_THIEU
            and con_giay - (time.monotonic() - t0) > _CON_GIAY_DE_CAO_THEM):
        # Tỉ lệ cào/giữ của lượt đầu cho biết phải xin thêm bao nhiêu (kẹp 1,5–6 lần).
        ti_le = min(6.0, max(1.5, len(raw) / max(1, len(giu))))
        n2 = max(1, min(tran_bai, suc2, int((so_mau - len(giu)) * ti_le) + 1))
        them = con_lai[:max(1, min(_SO_HASHTAG_SOI_TOI_DA, -(-n2 // _VIDEO_MOI_HASHTAG)))]
        # Trần USD của lượt hai cũng chỉ là phần còn lại — Apify tự chặn nếu giá lệch.
        tran2 = round(max(0.0, ngan_sach - len(raw) * _GIA_VIDEO_MAU), 4)
        try:
            moi = [it for it in _cao_mau(them, n2, tran2) if _khoa_video(it) not in da_thay]
            da_soi, cao, da_xin, so_luot = da_soi + them, cao + len(moi), da_xin + n2, 2
            giu += loc(moi)
        except Exception as e:  # noqa: BLE001 — lượt đầu vẫn dùng được
            print(f"[trend] cào thêm mẫu hỏng: {A._che_token(e)}"[:300])

    am = collections.defaultdict(lambda: {"kenh": set(), "video": 0, "view": 0, "tag": set()})
    hu = collections.defaultdict(lambda: {"kenh": set(), "video": 0, "tag": set()})
    ten_am: dict[str, tuple[str, str, bool]] = {}
    for it in giu:
        kenh = (it.get("authorMeta") or {}).get("name") or ""
        m = it.get("musicMeta") or {}
        if m.get("musicId"):
            k = str(m["musicId"])
            a = am[k]
            a["kenh"].add(kenh); a["video"] += 1; a["view"] += int(it.get("playCount") or 0)
            a["tag"].add(str(it.get("input") or ""))
            ten_am[k] = (str(m.get("musicName") or ""), str(m.get("musicAuthor") or ""),
                         _la_am_goc(m))
        for e in it.get("effectStickers") or []:
            if isinstance(e, dict) and e.get("name"):
                h = hu[str(e["name"])]
                h["kenh"].add(kenh); h["video"] += 1; h["tag"].add(str(it.get("input") or ""))

    # Chỉ tính là tín hiệu khi >= 2 KÊNH KHÁC NHAU dùng: một kênh đăng 5 video bằng âm
    # gốc của chính mình không phải trend.
    tat_ca = sorted(({
        "ten": ten_am[k][0], "tac_gia": ten_am[k][1],
        "loai": "Âm thanh gốc" if ten_am[k][2] else "Nhạc (bài hát) dùng lại",
        "so_kenh": len(v["kenh"]), "so_video": v["video"], "tong_view": v["view"],
        "di_kem_hashtag": ", ".join(sorted(t for t in v["tag"] if t)),
        "link": f"https://www.tiktok.com/music/x-{k}",
    } for k, v in am.items() if len(v["kenh"]) >= 2),
        key=lambda x: (-x["so_kenh"], -x["tong_view"]))
    # `di_kem_hashtag` để phân biệt trend tự nhiên với chiến dịch brand: đo thật 25/09,
    # hai hiệu ứng được 12 kênh dùng đều nằm dưới #larocheposaysuperbrandday.
    hieu_ung = sorted(({"ten": k, "so_kenh": len(v["kenh"]), "so_video": v["video"],
                        "di_kem_hashtag": ", ".join(sorted(t for t in v["tag"] if t))}
                       for k, v in hu.items() if len(v["kenh"]) >= 2),
                      key=lambda x: -x["so_kenh"])[:10]
    return {"cao": cao, "giu": len(giu), "am_thanh": tat_ca[:15], "hieu_ung": hieu_ung,
            "nhac_dung_lai": [a for a in tat_ca if a["loai"] != "Âm thanh gốc"][:10],
            "am_thanh_goc": [a for a in tat_ca if a["loai"] == "Âm thanh gốc"][:10],
            "cao_du": cao >= da_xin, "hashtag_da_soi": da_soi, "da_xin": da_xin,
            "so_luot": so_luot}


def chay(args: dict) -> str:
    vung = (str(args.get("country") or "VN").strip() or "VN").upper()
    if vung not in _VUNG_HASHTAG:
        return tool_error(f"Creative Center chưa có trend cho vùng {vung}. Có: "
                          f"{', '.join(sorted(_VUNG_HASHTAG))}.")
    ky = 30 if str(args.get("ky_ngay") or "7").strip() == "30" else 7
    # Ngành (chủ agent xin 04/10/2026: "trend ngành thời trang / túi / phụ kiện"). Chỉ bảng
    # hashtag lọc được; Creative Center không lọc top video theo ngành.
    nganh = None
    if str(args.get("nganh") or "").strip():
        nganh = nganh_tiktok.tim(args["nganh"])
        if not nganh or not nganh["id_trend"]:
            return tool_error(f"Chưa lọc trend được theo ngành '{args['nganh']}'. Ngành "
                              f"nhận được: {nganh_tiktok.danh_sach()}.")
    # Trần RIÊNG của TikTok (bài, USD, bật/tắt) — không phải trần chung (E2E 04-05/10).
    tran_bai, tran_usd, bat = A._tran_nen_tang("tiktok")
    if not bat:
        return tool_error(
            "KHÔNG CHẠY, chưa tốn tiền: " + A._ly_do_tat("tiktok")
            + " — trend TikTok cũng không chạy. Nói thẳng với người dùng như vậy; muốn chạy "
              "thì nhờ chủ agent bật lại TikTok trên console.")
    so_tag = _so(args.get("so_hashtag"), 20, 5, 100)
    so_vid = _so(args.get("so_video"), 20, 5, 100) if vung in _VUNG_VIDEO else 0
    tu_nhien = args.get("chi_tu_nhien") is not False
    so_mau = _so(args.get("so_video_mau"), 100, 20, tran_bai) \
        if args.get("soi_am_thanh") is not False else 0
    so_nhac = _so(args.get("so_nhac"), 10, 0, 50) if vung in _VUNG_NHAC else 0
    # Chia trần TikTok cho cả lượt (mọi bảng + lấy mẫu); thiếu thì cắt lượt kém ưu tiên.
    kh = _ke_hoach(tran_usd, tran_bai, so_tag, so_vid, so_mau, so_nhac)
    cau_tran = (f"trần TikTok trên console là {A._usd_vn(tran_usd)} USD/lượt — cả lượt "
                f"trend (mọi bảng + lấy mẫu) gộp lại phải gọn trong trần này")
    if kh["tu_choi"]:
        return tool_error(
            f"KHÔNG CHẠY, chưa tốn tiền: {cau_tran}, không đủ cho bảng hashtag tối thiểu "
            f"{_TOI_THIEU_BANG} dòng. Chủ agent nâng trần TikTok ở {A._NOI_CONSOLE}.")
    cat = kh["cat"]
    so_tag_bao, so_vid, n_nhac = kh["n_tag"], kh["n_vid"], kh["n_nhac"]
    # Bảng hashtag DÀI hơn số cần báo khi lấy mẫu: cần đủ hashtag để soi (xem
    # `_chon_hashtag_soi`, và lượt cào thêm), mà mỗi dòng chỉ 0,0015 USD.
    n_tag = so_tag_bao + kh["them_tag"]
    if not kh["n1"]:
        so_mau = 0
    # Ước tính = tổng trần đã chia (gồm cả lượt cào thêm TỆ NHẤT) — luôn <= trần TikTok.
    est = kh["est"]
    vuot = kh["est_xin"] > kh["ngan_sach"] + 1e-9
    cau_cat = (f"Yêu cầu đầy đủ ước {A._usd_vn(round(kh['est_xin'], 2))} USD, vượt trần — "
               f"sẽ cắt: {'; '.join(cat)}." if cat else "")
    cau_uoc = (f"Ước tính tối đa {A._usd_vn(round(est, 2))} USD; {cau_tran}."
               + (" " + cau_cat if cau_cat else ""))

    if args.get("chi_uoc_tinh") in (True, "true", "True", 1, "1"):
        hm = A._han_muc_thang()
        con = round(hm["con_lai"], 2) if hm else None
        thieu = bool(hm and con is not None and con < est)
        return tool_result(
            success=True, che_do="trend", chi_uoc_tinh=True, da_chay=False, vung=vung,
            ky_ngay=ky, nganh=({"ten": nganh["ten"], "loc_theo": nganh["ten_nhom"]}
                               if nganh else None),
            ke_hoach={"so_hashtag": so_tag_bao, "so_video": so_vid,
                      "so_video_mau_luot_dau": kh["n1"],
                      "so_video_mau_cao_them_toi_da": kh["them_mau"], "so_nhac": n_nhac},
            uoc_tinh_chi_phi_usd=round(est, 3), tran_usd_tiktok=tran_usd,
            uoc_tinh_neu_khong_cat_usd=round(kh["est_xin"], 3), vuot_tran=vuot,
            bi_cat_theo_tran=cat or None, ngan_sach_thang_con_usd=con,
            vuot_ngan_sach=thieu, cau_uoc_tinh=cau_uoc,
            note=("CHƯA chạy, không tốn tiền. Nêu phạm vi (vùng, kỳ, ngành nếu có) rồi chép "
                  "`cau_uoc_tinh` (số USD + trần TikTok"
                  + (", và phần sẽ bị cắt" if cat else "") + ") TRƯỚC khi kết bằng "
                  "\"Chạy nhé?\" và DỪNG. Đồng ý mới gọi lại bỏ `chi_uoc_tinh`."
                  + (" Ngân sách Apify tháng không đủ — nói rõ, chưa chạy được."
                     if thieu else "")),
        )
    bat_dau = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=5)
    t0 = time.monotonic()
    loi: dict[str, str] = {}

    # MỘT hạn chót cho cả lượt, truyền vào từng lời gọi actor qua contextvars của
    # apify_tool: tới hạn thì run bị HUỶ và trả phần đã có. Rà 01/10/2026: mỗi bảng chờ
    # nguyên `_TOOL_DEADLINE` riêng, lượt lấy mẫu đầu chạy không kiểm giờ — cộng dồn
    # 300–400s, đúng kiểu lỗi 340s/508s đã sửa ở social_listen.
    han = t0 + A._TOOL_DEADLINE
    han_run = han - A._DU_PHONG_HUY

    def con() -> float:
        return max(0.05, han - time.monotonic())

    ex = ThreadPoolExecutor(max_workers=3)
    try:
        def gui(fn, *a):
            return ex.submit(contextvars.copy_context().run, _trong_han, han_run, fn, *a)
        tr = kh["tran"]
        f_tag = gui(_bang_hashtag, vung, ky, n_tag, nganh["id_trend"] if nganh else "",
                    tr["hashtag"])
        f_vid = gui(_bang_video, vung, ky, so_vid, tu_nhien, tr["video"]) if so_vid else None
        f_nhac = gui(_bang_nhac, vung, ky, n_nhac, tr["nhac"]) if n_nhac else None
        try:
            tat_ca_tag = f_tag.result(timeout=con())
        except Exception as e:  # noqa: BLE001
            tat_ca_tag, loi["hashtag"] = [], A._che_token(f"{type(e).__name__}: {e}")[:250]
        tags = tat_ca_tag[:so_tag_bao]
        try:
            vids = f_vid.result(timeout=con()) if f_vid else []
        except Exception as e:  # noqa: BLE001
            vids, loi["video"] = [], A._che_token(f"{type(e).__name__}: {e}")[:250]

        mau = {"cao": 0, "giu": 0, "am_thanh": [], "hieu_ung": [], "cao_du": True}
        thu_tu = _thu_tu_soi(tat_ca_tag) if so_mau else []
        if so_mau and thu_tu and con() < _TOI_THIEU_GIAY_MAU:
            loi["am_thanh"] = "bỏ qua lấy mẫu âm thanh vì hết thời gian của lượt"
        elif so_mau and thu_tu:
            try:
                mau = contextvars.copy_context().run(
                    _trong_han, han_run, _mau_am_thanh, thu_tu, so_mau, vung, ky,
                    tran_bai, tr["mau"], con(), kh["n1"])
            except Exception as e:  # noqa: BLE001
                loi["am_thanh"] = A._che_token(f"{type(e).__name__}: {e}")[:250]
        try:
            nhac = f_nhac.result(timeout=con()) if f_nhac else []
        except Exception as e:  # noqa: BLE001
            nhac, loi["nhac"] = [], A._che_token(f"{type(e).__name__}: {e}")[:250]
    finally:
        # Không chờ lượt treo: trần trả lời 180s của run.py không đợi ai.
        ex.shutdown(wait=False)

    for t in tat_ca_tag:
        nc = _nhay_cam(t["hashtag"])
        if nc:
            t["nhay_cam"] = f"nhạy cảm ({nc}) — không nên bám trend"
    nhay_cam = [f"#{t['hashtag']} ({t['nhay_cam']})" for t in tags if t.get("nhay_cam")]

    nhac_trong_vn = bool(vung == "VN" and n_nhac and not nhac and "nhac" not in loi)
    if not so_nhac and vung not in _VUNG_NHAC:
        ghi_chu_nhac = f"Creative Center không có bảng nhạc cho {vung}."
    elif so_nhac and not n_nhac:
        ghi_chu_nhac = ("Trần chi phí TikTok của lượt không còn đủ cho bảng nhạc sau các bảng "
                        "ưu tiên hơn — đã bỏ qua.")
    elif not n_nhac:
        ghi_chu_nhac = "Không lấy bảng nhạc (so_nhac=0)."
    elif "nhac" in loi:
        ghi_chu_nhac = "Lấy bảng nhạc Creative Center LỖI — chỉ có âm thanh suy từ mẫu."
    elif not nhac:
        ghi_chu_nhac = (f"Creative Center không trả bảng nhạc cho {vung}; chỉ có âm thanh "
                        f"suy từ mẫu.")
    else:
        ghi_chu_nhac = (f"{len(nhac)} bài nhạc đang lên từ bảng Creative Center của {vung} "
                        f"(bảng chính thức, không phải suy từ mẫu).")

    actors = ([ACTOR_TREND] + ([A._ACTORS["tiktok_fallback"]] if so_mau else [])
              + ([ACTOR_NHAC] if n_nhac else []))
    thuc = A._chi_phi_thuc(actors, bat_dau, est)
    du = (len(tat_ca_tag) >= n_tag and len(vids) >= so_vid and mau["cao_du"]
          and len(nhac) >= n_nhac)
    if thuc and thuc.get("cham_tran") and du:
        thuc = {**thuc, "cham_tran": 0}
    chi_phi_tool.ghi(queries=[f"trend {vung}" + (f" · {nganh['ten']}" if nganh else "")],
                     platforms=["tiktok"],
                     date_range=f"{ky} ngày gần nhất", thuc=thuc, est=est)

    if not tags and not vids:
        return tool_error("Không lấy được bảng trend: " + "; ".join(
            f"{k}: {v}" for k, v in loi.items()))

    url, granted = None, False
    title = (args.get("title") or "").strip() or \
        (f"Trend TikTok {vung} · " + (f"{nganh['ten_nhom']} · " if nganh else "")
         + f"{ky} ngày · {datetime.datetime.now(A._VN_TZ):%d-%m-%Y}")
    rows = [["Loại", "Hạng", "Tên", "Hướng / Kênh", "Số bài / Số kênh dùng",
             "Lượt xem", "Ghi chú", "Link"]]
    rows += [["Hashtag", t["hang"], "#" + t["hashtag"], t["huong"], t["so_bai"],
              t["luot_xem"], (t["nhay_cam"].upper() + "; " if t.get("nhay_cam") else "")
              + t["nganh"], t["link"]] for t in tags]
    rows += [["Video", v["hang"], v["tieu_de"], v["kenh"], "", v["luot_xem"],
              f"tự nhiên {v['luot_xem_tu_nhien']} · {v['chu_de']}", v["link"]] for v in vids]
    rows += [["Nhạc đang lên (bảng Creative Center)", n["hang"], n["ten"], n["tac_gia"], "",
              "", (f"đổi hạng {n['thay_doi_hang']}" if n["thay_doi_hang"] != "" else "")
              + (" · mới vào bảng" if n["moi_vao_bang"] else ""), n["link"]] for n in nhac]
    rows += [[("Âm thanh gốc" if a.get("loai") == "Âm thanh gốc" else "Nhạc dùng lại")
              + " (suy từ mẫu)", i + 1, a["ten"], a["tac_gia"], a["so_kenh"],
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

    ghi_chu_nganh = ""
    if nganh:
        ghi_chu_nganh = (
            f" Bảng hashtag đã lọc theo ngành {nganh['ten_nhom']} của TikTok"
            + (f" (ngành cha của {nganh['ten']} — TikTok không lọc hashtag hẹp hơn)"
               if nganh["la_nganh_con"] else "")
            + "; top video KHÔNG lọc được theo ngành."
            + (f" Ngành này chỉ có {len(tat_ca_tag)} hashtag trên bảng."
               if len(tat_ca_tag) < n_tag and "hashtag" not in loi else ""))
    return tool_result(
        success=not loi, che_do="trend", vung=vung, ky_ngay=ky,
        nganh=({"ten": nganh["ten"], "loc_theo": nganh["ten_nhom"],
                "industry_id": nganh["id_trend"]} if nganh else None),
        nguon=("Bảng xếp hạng chính thức TikTok Creative Center (hashtag + video + nhạc đang "
               "lên). Âm thanh/hiệu ứng SUY từ mẫu video dưới các hashtag đang lên."),
        hashtag=tags, video=vids, chi_video_tu_nhien=tu_nhien,
        hashtag_nhay_cam=nhay_cam,
        nhac=nhac, nhac_trong_vn=nhac_trong_vn, ghi_chu_nhac=ghi_chu_nhac,
        am_thanh=mau["am_thanh"], hieu_ung=mau["hieu_ung"],
        nhac_dung_lai=mau.get("nhac_dung_lai", []), am_thanh_goc=mau.get("am_thanh_goc", []),
        mau_am_thanh={"hashtag_da_soi": mau.get("hashtag_da_soi", []) if so_mau else [],
                      "da_xin": mau.get("da_xin", 0), "da_cao": mau["cao"],
                      "giu_lai_trong_ky_dung_ngon_ngu": mau["giu"],
                      "so_video_mau_can": so_mau, "so_luot_cao": mau.get("so_luot", 0)},
        loi=loi or None, sheet_url=url, granted=granted, title=title,
        uoc_tinh_chi_phi_usd=round(est, 3), tran_usd_tiktok=tran_usd,
        bi_cat_theo_tran=cat or None,
        chi_phi_thuc_usd=thuc["usd"] if thuc and thuc.get("so_run") else None,
        cham_tran_chi_phi=bool(thuc and thuc.get("cham_tran")),
        chi_phi=A._dong_chi_phi(thuc, est),
        giay=round(time.monotonic() - t0, 1),
        note=((f"ĐÃ CẮT cho vừa trần TikTok ({A._usd_vn(tran_usd)} USD/lượt): "
               f"{'; '.join(cat)} — nói ra với người dùng. " if cat else "")
              + ghi_chu_nhac + ghi_chu_nganh
              + (" Mẫu giữ được ít hơn số cần — nói rõ cỡ mẫu thật."
                 if so_mau and mau["giu"] < so_mau else "")
              + (f" HASHTAG NHẠY CẢM: {'; '.join(nhay_cam)} — KHÔNG đề xuất brand bám các "
                 f"trend này." if nhay_cam else "")),
    )
