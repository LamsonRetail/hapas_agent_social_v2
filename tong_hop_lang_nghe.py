"""Tổng hợp kiểu dashboard cho `social_listen` (13/10/2026): xu hướng theo ngày, nguồn
nổi bật, chủ đề × sắc thái, từ khoá nổi bật, bình luận YouTube kèm sắc thái.

Vì sao có: chủ agent so Mark với dashboard Kompa của HAPAS (13/09–13/10/2026) — Kompa có
đường xu hướng thảo luận, top nguồn theo từng kênh, sắc thái theo chủ đề, mây từ khoá;
Mark chỉ trả danh sách bài + đếm sắc thái, muốn biết "ngày nào nổ", "ai nói nhiều nhất",
"khen chê về chuyện gì" thì Mark phải tự đếm tay trên sheet (và đếm sai). Module này đếm
bằng CODE từ đúng các dòng sẽ ghi vào sheet; model chỉ chép `cau_tong_hop`.

Nguyên tắc, đừng bỏ khi sửa:
  1. CHỈ ĐẾM, KHÔNG ƯỚC LƯỢNG. "Thảo luận" = số bài + số bình luận NỀN TẢNG BÁO trên các
     bài đó (trường comments của nguồn) — gọi đúng tên như vậy, không gọi là toàn bộ thảo
     luận về brand (bình luận ở bài không nhắc brand thì không có ở đây).
  2. Bài của CHÍNH brand vẫn tính vào số bài / thảo luận / nguồn (dashboard cũng tính),
     nhưng KHÔNG vào sắc thái, chủ đề, từ khoá: tiếng của brand không phải tiếng khách
     (cùng luật `phan_loai.dem`).
  3. Không có số kỳ trước thì không bịa "% so với kỳ trước": chỉ so 7 ngày cuối với 7
     ngày liền trước BÊN TRONG khoảng đã quét, và gọi đúng tên như vậy.
  4. Nguồn chạm trần (`chua_phu_het`) thì đường xu hướng là của MẪU — phải nói ra, phần
     đầu khoảng có thể thấp vì chưa quét tới chứ không phải vì ít người nói.
"""
from __future__ import annotations

import collections
import datetime
import re
import time
import unicodedata

import phan_loai
import trinh_bay_sheet as T

VN = datetime.timezone(datetime.timedelta(hours=7))

TAB_XU_HUONG = "Xu hướng"
TAB_NGUON = "Nguồn nổi bật"
TAB_CHU_DE = "Chủ đề"
TAB_TU_KHOA = "Từ khoá"
TAB_BL_YT = "Bình luận YouTube"

NGAY_TOI_DA_THEO_NGAY = 92      # khoảng dài hơn thì gom theo tuần (sheet khỏi vài trăm dòng)
NGUON_MOI_NEN_TANG = 20
TU_KHOA_TOI_DA = 50
TU_KHOA_TOI_THIEU_BAI = 2       # cụm chỉ một bài nhắc thì là nhiễu, không phải "nổi bật"
SO_SANH_NGAY = 7
TOI_THIEU_BAI_TAB = 5           # ít bài hơn thì không dựng tab tổng hợp (xem `cac_bang`)

_TEN_NEN = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram",
            "youtube": "YouTube", "threads": "Threads"}
TC, TI, TL = (phan_loai.SAC_THAI[k] for k in "+-=")
CHUA = phan_loai.CHUA


def _ten_nen(p) -> str:
    return _TEN_NEN.get(str(p or ""), str(p or "?"))


def _so(v) -> int:
    try:
        return max(0, int(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def _so_vn(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def _pt_vn(x: float | None, dau: bool = False) -> str:
    if x is None:
        return "—"
    s = f"{x:+.1f}" if dau else f"{x:.1f}"
    return s.replace(".", ",") + "%"


def _ngay(dt) -> datetime.date:
    if isinstance(dt, datetime.datetime):
        return (dt.astimezone(VN) if dt.tzinfo else dt).date()
    return dt


def _nha(d: dict) -> bool:
    return bool(d.get("_cua_thuong_hieu"))


def _sac(d: dict) -> str:
    s = d.get("_sac_thai")
    return s if s in (TC, TI, TL) else CHUA


def _chu_de(d: dict) -> str:
    c = d.get("_chu_de")
    return c if c in phan_loai.CHU_DE_BAI.values() else CHUA


def _thao_luan(d: dict) -> int:
    return 1 + _so(d.get("comments"))


def _sach(s, n: int = 60) -> str:
    """Chữ người lạ viết (tên kênh, cụm từ) trước khi vào câu model phải chép NGUYÊN VĂN:
    gộp khoảng trắng, NFKC, đổi '<' '>' — cùng cách `apify_tool._khong_the` cho trích dẫn."""
    s = unicodedata.normalize("NFKC", " ".join(str(s or "").split()))
    return s.replace("<", "‹").replace(">", "›")[:n]


# ───────────────────────── xu hướng ─────────────────────────
def _dau_tuan(n: datetime.date) -> datetime.date:
    return n - datetime.timedelta(days=n.weekday())


def xu_huong(bai: list, d_from, d_to, *, hom_nay: datetime.date | None = None,
             mau: bool = False) -> dict:
    """Đếm theo NGÀY đăng (giờ VN), đủ mọi ngày trong khoảng kể cả ngày 0 bài; khoảng dài
    hơn `NGAY_TOI_DA_THEO_NGAY` thì theo TUẦN (thứ Hai đầu tuần, kẹp vào khoảng). Ngày
    cuối kẹp về HÔM NAY (khoảng "tháng 10" hỏi ngày 13 không có 18 ngày 0 giả).

    So 7 ngày cuối với 7 ngày liền trước chỉ khi: theo ngày, đủ 14 ngày TRỌN (hôm nay chưa
    hết nên không tính), và `mau`=False — nguồn chạm trần/thiếu thì phần đầu khoảng thấp vì
    chưa quét tới, % so sánh sẽ là ảo (rà 13/10/2026). Không so thì `ly_do_khong_so_sanh`.

    -> {don_vi, dong: [{moc, bai, bai_thuong_hieu, binh_luan, thao_luan, TC, TI, TL,
    chua}], dinh, so_sanh, ly_do_khong_so_sanh, cat_tuong_lai, nhieu_nam}. Sắc thái chỉ
    đếm bài KHÔNG phải của brand."""
    hom_nay = hom_nay or datetime.datetime.now(VN).date()
    n0, n1 = _ngay(d_from), _ngay(d_to)
    cat_tuong_lai = n1 > hom_nay
    n1 = max(n0, min(n1, hom_nay))
    so_ngay = (n1 - n0).days + 1
    theo_tuan = so_ngay > NGAY_TOI_DA_THEO_NGAY
    moc = (lambda n: max(n0, _dau_tuan(n))) if theo_tuan else (lambda n: n)
    cac_moc, n = [], n0
    while n <= n1:
        m = moc(n)
        if not cac_moc or cac_moc[-1] != m:
            cac_moc.append(m)
        n += datetime.timedelta(days=1)
    dem = {m: {"moc": m, "bai": 0, "bai_thuong_hieu": 0, "binh_luan": 0, "thao_luan": 0,
               TC: 0, TI: 0, TL: 0, CHUA: 0} for m in cac_moc}
    for d, dt in bai:
        if dt is None:
            continue
        g = dem.get(moc(_ngay(dt)))
        if g is None:
            continue
        g["bai"] += 1
        g["binh_luan"] += _so(d.get("comments"))
        g["thao_luan"] += _thao_luan(d)
        if _nha(d):
            g["bai_thuong_hieu"] += 1
        else:
            g[_sac(d)] += 1
    dong = [dem[m] for m in cac_moc]
    dinh = max(dong, key=lambda g: (g["thao_luan"], -g["moc"].toordinal()), default=None)
    if dinh is not None and not dinh["thao_luan"]:
        dinh = None
    so_sanh, ly_do = None, None
    cuoi = n1 - datetime.timedelta(days=1) if n1 >= hom_nay else n1   # ngày TRỌN cuối cùng
    if theo_tuan:
        ly_do = "khoảng dài, đếm theo tuần"
    elif (cuoi - n0).days + 1 < 2 * SO_SANH_NGAY:
        ly_do = f"khoảng quét chưa đủ {2 * SO_SANH_NGAY} ngày trọn"
    elif mau:
        ly_do = ("có nguồn chạm trần hoặc chỉ lấy được một phần nên đây là MẪU — so hai kỳ "
                 "sẽ ra % ảo")
    else:
        def gom(a: datetime.date, b: datetime.date) -> dict:
            x = [dem[m] for m in cac_moc if a <= m <= b]
            return {"tu": a, "den": b, "bai": sum(g["bai"] for g in x),
                    "thao_luan": sum(g["thao_luan"] for g in x)}
        nay = gom(cuoi - datetime.timedelta(days=SO_SANH_NGAY - 1), cuoi)
        truoc = gom(cuoi - datetime.timedelta(days=2 * SO_SANH_NGAY - 1),
                    cuoi - datetime.timedelta(days=SO_SANH_NGAY))

        def doi(k: str) -> float | None:
            return (round(100.0 * (nay[k] - truoc[k]) / truoc[k], 1) if truoc[k] else None)
        so_sanh = {"ky_nay": nay, "ky_truoc": truoc, "doi_bai": doi("bai"),
                   "doi_thao_luan": doi("thao_luan")}
    return {"don_vi": "tuần" if theo_tuan else "ngày", "dong": dong, "dinh": dinh,
            "so_sanh": so_sanh, "ly_do_khong_so_sanh": ly_do,
            "cat_tuong_lai": cat_tuong_lai, "den": n1, "nhieu_nam": n0.year != n1.year}


# ───────────────────────── nguồn nổi bật ─────────────────────────
def _khoa_kenh(d: dict) -> str:
    """Khoá gom kênh: handle/tên đã bỏ dấu + ký tự lạ ("@ME4CON.102" ≡ "me4con.102"). Tên
    toàn chữ Thái/Hàn/emoji thì `_gon` rỗng -> dùng tên chuẩn hoá (giữ chữ gốc), kẻo mọi
    kênh như vậy dồn chung một dòng "?" (rà 13/10/2026). YouTube không có username."""
    for x in (d.get("username"), d.get("kenh")):
        k = phan_loai._gon(x)
        if k:
            return k
    for x in (d.get("username"), d.get("kenh")):
        k = re.sub(r"\s+", " ", phan_loai._ten(x))
        if k:
            return "~" + k
    return "?" + str(d.get("link") or "")


def nguon_noi_bat(bai: list, toi_da: int = NGUON_MOI_NEN_TANG) -> dict:
    """Gom bài theo (nền tảng, kênh) -> top `toi_da` kênh mỗi nền tảng theo THẢO LUẬN (bài
    + bình luận nền tảng báo), hoà thì số bài rồi views. -> {theo_nen_tang: {p: [kênh]},
    so_kenh: {p: n}} — nền tảng xếp theo tổng thảo luận giảm dần."""
    gom: dict = {}
    for d, _ in bai:
        p = str(d.get("platform") or "?")
        k = (p, _khoa_kenh(d))
        g = gom.get(k)
        if g is None:
            g = gom[k] = {"nen_tang": p, "ten": collections.Counter(), "bai": 0,
                          "binh_luan": 0, "thao_luan": 0, "views": 0, "likes": 0,
                          "followers": 0, "thuong_hieu": False, TC: 0, TI: 0, TL: 0,
                          CHUA: 0, "_top": None}
        g["ten"][str(d.get("kenh") or d.get("username") or "?")] += 1
        g["bai"] += 1
        g["binh_luan"] += _so(d.get("comments"))
        g["thao_luan"] += _thao_luan(d)
        g["views"] += _so(d.get("views"))
        g["likes"] += _so(d.get("likes"))
        g["followers"] = max(g["followers"], _so(d.get("followers")))
        g["thuong_hieu"] = g["thuong_hieu"] or _nha(d)
        if not _nha(d):
            g[_sac(d)] += 1
        khoa_top = (_so(d.get("views")), _so(d.get("comments")), _so(d.get("likes")))
        if g["_top"] is None or khoa_top > g["_top"][0]:
            g["_top"] = (khoa_top, str(d.get("link") or ""))
    theo: dict = collections.defaultdict(list)
    for g in gom.values():
        g["kenh"] = sorted(g["ten"].items(), key=lambda x: (-x[1], x[0]))[0][0]
        g["link_noi_bat"] = g["_top"][1] if g["_top"] else ""
        del g["ten"], g["_top"]
        theo[g["nen_tang"]].append(g)
    tong = {p: sum(g["thao_luan"] for g in ds) for p, ds in theo.items()}
    ra = {}
    for p in sorted(theo, key=lambda p: (-tong[p], p)):
        ds = sorted(theo[p], key=lambda g: (-g["thao_luan"], -g["bai"], -g["views"], g["kenh"]))
        ra[p] = ds[:toi_da]
    return {"theo_nen_tang": ra, "so_kenh": {p: len(theo[p]) for p in ra}}


# ───────────────────────── chủ đề × sắc thái ─────────────────────────
def chu_de(bai: list) -> dict:
    """Bài KHÔNG của brand theo chủ đề (nhãn `phan_loai.CHU_DE_BAI`, AI gán cùng lượt phân
    xử) × sắc thái. Tỉ lệ tính trên số bài ĐÃ có chủ đề. -> {tong, da_gan, chua_gan,
    dong: [{chu_de, so, ti_le, TC, TI, TL, chua}]} — nhiều bài trước, "chưa phân loại" cuối."""
    khach = [d for d, _ in bai if not _nha(d)]
    dem: dict = {}
    for d in khach:
        c = _chu_de(d)
        g = dem.setdefault(c, {"chu_de": c, "so": 0, TC: 0, TI: 0, TL: 0, CHUA: 0})
        g["so"] += 1
        g[_sac(d)] += 1
    da = sum(g["so"] for c, g in dem.items() if c != CHUA)
    for c, g in dem.items():
        g["ti_le"] = round(100.0 * g["so"] / da, 1) if (da and c != CHUA) else None
    dong = sorted(dem.values(), key=lambda g: (g["chu_de"] == CHUA, -g["so"], g["chu_de"]))
    return {"tong": len(khach), "da_gan": da, "chua_gan": len(khach) - da, "dong": dong}


# ───────────────────────── từ khoá nổi bật ─────────────────────────
# Hư từ / đại từ / từ đệm hay gặp trên mạng xã hội VN + tiếng Anh. Cụm hai chữ có một
# chữ ở đây thì bỏ ("của hàng", "rất đẹp"): mây từ khoá phải là cụm có nghĩa ("túi xách",
# "nước hoa"). Danh sách cố ý ngắn gọn; thiếu vài từ chỉ làm lọt cụm vô nghĩa ở cuối bảng.
_STOP = set("""
và của là có cho với các những một này đó thì mà được đã đang sẽ không chưa cũng rất quá
lắm nhé nha ạ à ơi nhỉ vậy thế như để khi từ trong ngoài trên dưới ra vào lên xuống đi
đến tới về theo bị vì nên nếu hay hoặc còn nữa rồi mình bạn tôi tui tớ em anh chị ai gì
nào đâu sao bao nhiêu thôi luôn ngay lại đây kia ấy nhiều ít hơn nhất mỗi mọi cả tất chỉ
vẫn đều chứ nhưng tại bởi do qua giữa sau trước cùng hết ở nó họ chúng ta mấy cái con
người thấy làm biết muốn cần phải đều vừa mới xong đúng đó đấy nè nhá hả ha hihi haha
hehe kk ok oke uh ừ vâng dạ ko k hok hông khum dc đc dk j r vs ib inbox link bio rep cmt
check xem nhé nhaa luôn thì là lúc giờ hôm nay mai qua năm tháng ngày tuần
the a an and or of to in on for with is are was were be been my your our their i you
he she it we they this that these those at by from as so if not no yes me us them its
just very really all any can will would should do does did have has had get got more
""".split())
# Hashtag "đẩy đề xuất" ai cũng gắn, không nói gì về brand.
_HASHTAG_CHUNG = {"fyp", "foryou", "foryoupage", "xuhuong", "xuhướng", "viral", "trending",
                  "trend", "tiktok", "reels", "reel", "capcut", "fypシ", "fy", "explore",
                  "viralvideo", "tiktokvietnam", "vairal", "thinhhanh", "learnontiktok"}
_RE_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_RE_TAG_NGUOI = re.compile(r"@[\w.\-]+")
_RE_HASHTAG = re.compile(r"#(\w+)")
_RE_DOAN = re.compile(r"[^\w\s]+|\d+|_+")


def _chuan_chu(s) -> str:
    return unicodedata.normalize("NFC", str(s or "")).lower()


def _bo_dau(s: str) -> str:
    return phan_loai._bo_dau(s)


def _cum(d: dict) -> set[str]:
    """Các cụm của MỘT bài: cụm hai chữ liền nhau (không vượt dấu câu/số/emoji) không chứa
    hư từ, cộng hashtag dạng '#tên'. Mỗi cụm tính một lần mỗi bài."""
    text = _RE_TAG_NGUOI.sub(" ", _RE_URL.sub(" ", _chuan_chu(d.get("text"))))
    tags = {t for t in _RE_HASHTAG.findall(text)}
    # Trường `hashtags` nối bằng ", ". Thẻ YouTube (snippet.tags) có thể NHIỀU CHỮ ("túi
    # xách nữ") — tách theo khoảng trắng thì ra hashtag giả "#túi", "#xách" (rà 13/10/2026):
    # chỉ tách theo dấu phẩy/chấm phẩy/#, bỏ thẻ có khoảng trắng (không phải hashtag).
    tags |= {t.strip() for t in re.split(r"[,;#]+", _chuan_chu(d.get("hashtags")))
             if t.strip() and not re.search(r"\s", t.strip())}
    text = _RE_HASHTAG.sub(" ", text)
    ra = set()
    for t in tags:
        t = t.strip()
        if len(t) >= 3 and not t.isdigit() and t not in _HASHTAG_CHUNG:
            ra.add("#" + t)
    for doan in _RE_DOAN.split(text):
        chu = doan.split()
        for a, b in zip(chu, chu[1:], strict=False):          # cặp chữ liền nhau
            if (a != b and len(a) >= 2 and len(b) >= 2 and a.isalpha() and b.isalpha()
                    and a not in _STOP and b not in _STOP):
                ra.add(f"{a} {b}")
    return ra


def tu_khoa(bai: list, queries: list[str], toi_da: int = TU_KHOA_TOI_DA) -> dict:
    """Top cụm từ / hashtag theo SỐ BÀI nhắc (bài không của brand), bỏ cụm chứa chính từ
    khoá đang quét (quét "hapas" thì "túi hapas" không phải phát hiện gì). Cụm phải có ít
    nhất `TU_KHOA_TOI_THIEU_BAI` bài. -> {so_bai, dong: [{tu, so_bai, TC, TI, TL}]}."""
    khach = [d for d, _ in bai if not _nha(d)]
    # So trên dạng bỏ dấu + bỏ khoảng trắng: quét "hapas" thì bỏ "túi hapas", "#hapasvn",
    # "hapas store". Truy vấn nhiều chữ ("túi hapas") chỉ bỏ cụm chứa NGUYÊN cụm — bỏ theo
    # từng chữ thì "túi" làm mất luôn "túi xách". Truy vấn < 3 ký tự thì không bỏ gì.
    bo = {x for x in (re.sub(r"[\s#]+", "", _bo_dau(_chuan_chu(q))) for q in queries)
          if len(x) >= 3}
    dem: dict = {}
    for d in khach:
        for c in _cum(d):
            gon = re.sub(r"[\s#]+", "", _bo_dau(c))
            if any(b in gon for b in bo):
                continue
            g = dem.setdefault(c, {"tu": c, "so_bai": 0, TC: 0, TI: 0, TL: 0, CHUA: 0})
            g["so_bai"] += 1
            g[_sac(d)] += 1
    dong = [g for g in dem.values() if g["so_bai"] >= TU_KHOA_TOI_THIEU_BAI]
    dong.sort(key=lambda g: (-g["so_bai"], g["tu"]))
    return {"so_bai": len(khach), "dong": dong[:toi_da]}


# ───────────────────────── bình luận YouTube (API miễn phí) ─────────────────────────
# Lượt tại chỗ: ≤100 bình luận = ĐÚNG một lô gán nhãn (`phan_loai._LO`) để chạy song song
# với AI phân xử mà tổng lượt model cùng lúc vẫn ≤3 (apify_tool._AI_SONG_SONG). Việc nền
# có thời gian nên lấy rộng hơn.
YT_VIDEO_TAI_CHO, YT_MOI_VIDEO_TAI_CHO = 5, 20
# Việc nền: ≤500 bình luận = ≤5 lượt model, 2 lượt song song — cùng mức `quet_lon._phan_xu_tang`
# tự giới hạn cho AI phân xử nền (quota model dùng chung với bot chính).
YT_VIDEO_NEN, YT_MOI_VIDEO_NEN, YT_SONG_SONG_NEN = 25, 20, 2


def chon_video_youtube(bai: list, toi_da: int, country: str | None = None) -> list[dict]:
    """Video YouTube có bình luận, tối đa `toi_da`. Thứ tự: đúng thị trường đang quét trước
    (`_thi_truong` ∈ {country, "không rõ"}; trùng tên "Hapas" ở Rajasthan là tin tiếng Hindi
    hàng nghìn bình luận — chiếm hết suất rồi bị AI loại, rà 13/10/2026), rồi CÓ nhắc từ
    khoá (`_khop`), rồi nhiều bình luận, rồi views."""
    ds = [d for d, _ in bai if d.get("platform") == "youtube" and _so(d.get("comments"))
          and str(d.get("link") or "").strip()]
    ds.sort(key=lambda d: (bool(country) and d.get("_thi_truong", "không rõ")
                           not in (country, "không rõ"),
                           not d.get("_khop", True), -_so(d.get("comments")),
                           -_so(d.get("views")), str(d.get("link"))))
    return ds[:toi_da]


def keo_binh_luan_youtube(videos: list[dict], moi_video: int, han: float) -> dict:
    """Kéo bình luận bằng YouTube Data API (miễn phí, cùng đường `social_deep_dive`).
    KHÔNG chạy actor dự phòng (tốn tiền, ngoài phạm vi lượt quét). `han` = mốc
    time.monotonic(). -> {trang_thai, binh_luan, video, loi, dv, mot_phan, chua_chay}."""
    ra = {"trang_thai": "", "binh_luan": [], "video": len(videos), "loi": "", "dv": 0,
          "mot_phan": [], "chua_chay": [], "loi_bai": {}}
    if not videos:
        ra["trang_thai"] = "bỏ qua: không có video YouTube nào có bình luận"
        return ra
    import deep_dive_tool as DD                       # import muộn: DD import apify_tool
    if not DD._yt_api_san_sang():
        ra["trang_thai"] = "bỏ qua: không có YouTube Data API key hoặc hôm nay đã hết quota"
        return ra
    if han - time.monotonic() < 5:
        ra["trang_thai"] = "bỏ qua: hết thời gian"
        return ra
    r = DD._yt_api_lo([str(d["link"]) for d in videos], moi_video, han)
    ra.update(binh_luan=r["binh_luan"], dv=r["dv"], mot_phan=r["mot_phan"],
              chua_chay=r["chua_chay"], loi_bai=r["loi_bai"], loi=r["loi"] or "")
    if r["con_lai"]:
        ra["loi"] = (r["loi"] or "lỗi API")[:200]
    xong = len(videos) - len(r["chua_chay"]) - len(r["con_lai"])
    ra["trang_thai"] = ("đã chạy" if xong == len(videos) and not r["mot_phan"] else
                        f"chạy một phần ({max(0, xong)}/{len(videos)} video)" if xong > 0
                        else "không lấy được: " + (ra["loi"] or "hết thời gian"))
    return ra


def phan_tich_binh_luan_youtube(kq: dict, videos: list[dict], queries: list[str],
                                han_giay: float, song_song: int | None = None) -> dict:
    """Gán sắc thái + chủ đề bình luận (`phan_loai`, luật trước model sau, fail-open) rồi
    đếm. Trả lời của CHỦ KÊNH video và của chính brand không vào số đếm (vẫn ghi sheet).
    -> {dong (dict từng bình luận), thong_ke, dong_thong_ke, gan_nhan}."""
    rows, gan = gan_nhan_binh_luan_youtube(kq, videos, queries, han_giay, song_song)
    return {**thong_ke_binh_luan_youtube(rows), "gan_nhan": gan}


def gan_nhan_binh_luan_youtube(kq: dict, videos: list[dict], queries: list[str],
                               han_giay: float, song_song: int | None = None
                               ) -> tuple[list[dict], dict]:
    """Dòng bình luận (chỉ của `videos`) đã gán nhãn -> (dòng, trạng thái gán nhãn). Tách
    khỏi bước đếm để lượt tại chỗ gán nhãn SONG SONG với AI phân xử, đếm sau khi biết
    video nào còn giữ (`thong_ke_binh_luan_youtube(..., giu_link)`)."""
    theo_vid: dict = {}
    for d in videos:
        m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{6,})", str(d.get("link") or ""))
        if m:
            theo_vid[m.group(1)] = d
    rows = []
    for c in kq.get("binh_luan") or []:
        m = re.search(r"v=([\w-]{6,})", str(c.get("link") or ""))
        v = theo_vid.get(m.group(1)) if m else None
        if v is None:
            continue             # video đã bị bộ lọc loại (hoặc không quy được) — bỏ
        nha = phan_loai.la_tai_khoan_nha(c.get("kenh"), queries)
        chu = bool(c.get("cua_chu"))
        rows.append({**c, "platform": "youtube", "bai": str(v.get("link") or c.get("link")),
                     "video": str(v.get("text") or "")[:120],
                     "kenh_video": str(v.get("kenh") or ""),
                     "nguon": (phan_loai.NGUON_NHA if (nha or (chu and _nha(v)))
                               else "chủ kênh" if chu else phan_loai.NGUON_KHACH),
                     "cua_thuong_hieu": nha or chu})
    gan: dict = {}
    nhan = (phan_loai.phan_loai_binh_luan(rows, han_giay, gan, song_song=song_song)
            if rows else [])
    for r, (s, c) in zip(rows, nhan, strict=False):      # phan_loai trả đúng độ dài rows
        r["sac_thai"], r["chu_de"] = s, c
    return rows, gan


def thong_ke_binh_luan_youtube(rows: list[dict], giu_link: set | None = None) -> dict:
    """Đếm sắc thái/chủ đề bình luận (`phan_loai.dem`); `giu_link` = link video còn ở sheet
    (bình luận video bị bộ lọc loại thì bỏ). -> {dong, thong_ke, dong_thong_ke}."""
    if giu_link is not None:
        rows = [r for r in rows if r.get("bai") in giu_link]
    tk = phan_loai.dem(rows) if rows else None
    dong_tk = ""
    if tk:
        tk.pop("theo_bai", None)
        loai_ra = tk.get("cua_thuong_hieu") or 0
        tk["cua_thuong_hieu"] = 0               # câu của phan_loai nói "thương hiệu" — sai
        dong_tk = phan_loai.dong_thong_ke(tk, "bình luận")
        tk["khong_tinh_chu_kenh_thuong_hieu"] = loai_ra
        if loai_ra:
            dong_tk += f" {loai_ra} trả lời của chủ kênh/thương hiệu (không tính)."
    return {"dong": rows, "thong_ke": tk, "dong_thong_ke": dong_tk}


# ───────────────────────── gộp + bảng sheet ─────────────────────────
def tong_hop(bai: list, d_from, d_to, queries: list[str], mau: list[str] | None = None, *,
             hom_nay: datetime.date | None = None) -> dict:
    """Mọi khối tổng hợp của MỘT tập bài (bài sheet chính). `mau` = câu ngắn từng nguồn
    chạm trần / chỉ lấy được một phần ("TikTok chạm trần 100 bài") — có thì đường xu hướng
    là của MẪU và không so 7 ngày với 7 ngày (`xu_huong`)."""
    mau = [c for c in (mau or []) if c]
    xh = xu_huong(bai, d_from, d_to, hom_nay=hom_nay, mau=bool(mau))
    ng = nguon_noi_bat(bai)
    cd = chu_de(bai)
    tk = tu_khoa(bai, queries)
    so_bai = len(bai)
    bl = sum(_so(d.get("comments")) for d, _ in bai)
    return {"thao_luan": {"bai": so_bai, "binh_luan": bl, "tong": so_bai + bl},
            "xu_huong": xh, "nguon": ng, "chu_de": cd, "tu_khoa": tk, "mau": mau}


def _moc_vn(n: datetime.date, co_nam: bool = False) -> str:
    return f"{n:%d/%m/%Y}" if co_nam else f"{n:%d/%m}"


def cau_tong_hop(th: dict, bl_yt: dict | None = None) -> str:
    """Câu dựng sẵn để model chép nguyên văn (mọi số đã đếm bằng code; chữ người lạ viết
    đi qua `_sach`)."""
    tl = th["thao_luan"]
    xh = th["xu_huong"]
    nam = bool(xh.get("nhieu_nam"))
    phan = [f"Thảo luận {_so_vn(tl['tong'])} = {_so_vn(tl['bai'])} bài + "
            f"{_so_vn(tl['binh_luan'])} bình luận nền tảng hiển thị trên các bài đó (chỉ "
            f"bài đã quét được, không phải toàn bộ mạng xã hội; bình luận tính vào ngày "
            f"đăng bài)."]
    if th.get("mau"):
        phan.append("LƯU Ý — đây là MẪU, không phải toàn bộ: " + "; ".join(th["mau"])
                    + ". Phần đầu khoảng có thể thấp vì chưa quét tới, đừng đọc là ít người "
                      "nói.")
    if xh.get("cat_tuong_lai"):
        phan.append(f"Khoảng ngày kéo quá hôm nay — chỉ tính tới {_moc_vn(xh['den'], nam)}.")
    if xh["dinh"]:
        g = xh["dinh"]
        moc = (f"Ngày nhiều thảo luận nhất: {_moc_vn(g['moc'], nam)}" if xh["don_vi"] == "ngày"
               else f"Tuần nhiều thảo luận nhất: tuần từ {_moc_vn(g['moc'], True)}")
        phan.append(f"{moc} ({_so_vn(g['thao_luan'])} thảo luận, {_so_vn(g['bai'])} bài).")
    ss = xh.get("so_sanh")
    if ss:
        phan.append(f"{SO_SANH_NGAY} ngày cuối ({_moc_vn(ss['ky_nay']['tu'], nam)}–"
                    f"{_moc_vn(ss['ky_nay']['den'], nam)}) so với {SO_SANH_NGAY} ngày liền "
                    f"trước: thảo luận {_so_vn(ss['ky_nay']['thao_luan'])} so với "
                    f"{_so_vn(ss['ky_truoc']['thao_luan'])} ({_pt_vn(ss['doi_thao_luan'], True)})"
                    f", bài {_so_vn(ss['ky_nay']['bai'])} so với {_so_vn(ss['ky_truoc']['bai'])}.")
    elif th.get("mau") and xh.get("ly_do_khong_so_sanh"):
        phan.append(f"Không so {SO_SANH_NGAY} ngày cuối với {SO_SANH_NGAY} ngày trước: "
                    f"{xh['ly_do_khong_so_sanh']}.")
    nguon = []
    for p, ds in th["nguon"]["theo_nen_tang"].items():
        top = ", ".join(f"{_sach(g['kenh'], 40)} ({_so_vn(g['thao_luan'])})" for g in ds[:3])
        if top:
            nguon.append(f"{_ten_nen(p)}: {top}")
    if nguon:
        phan.append("Nguồn nhiều thảo luận nhất — " + "; ".join(nguon) + ".")
    cd = th["chu_de"]
    co = [g for g in cd["dong"] if g["chu_de"] != CHUA]
    if co:
        # Chủ đề chỉ có ở bài AI đã đọc; việc nền AI đọc bài MƠ HỒ nhiều view + một mẫu
        # ngẫu nhiên — đọc ít thì tỉ lệ lệch, phải nói ra (rà 13/10/2026).
        it = cd["da_gan"] < 0.8 * cd["tong"]
        phan.append(f"Chủ đề (đã gán {cd['da_gan']}/{cd['tong']} bài khách"
                    + ("; chỉ trên bài AI đã đọc, tỉ lệ có thể lệch so với toàn bộ" if it
                       else "") + "): " + ", ".join(
                        f"{g['chu_de']} {g['so']} ({_pt_vn(g['ti_le'])}; tiêu cực {g[TI]})"
                        for g in co[:4]) + ".")
    elif cd["tong"]:
        phan.append(f"Chủ đề: chưa có bài nào được gán chủ đề (0/{cd['tong']}).")
    tk = th["tu_khoa"]["dong"]
    if tk:
        phan.append("Từ khoá nổi bật: " + ", ".join(f"{_sach(g['tu'], 40)} ({g['so_bai']} bài)"
                                                     for g in tk[:8]) + ".")
    if bl_yt and bl_yt.get("dong_thong_ke"):
        phan.append("Bình luận YouTube: " + bl_yt["dong_thong_ke"])
    return " ".join(phan)


def tom_tat(th: dict, bl_yt: dict | None = None) -> dict:
    """Bản gọn cho kết quả tool (model đọc) — không kèm từng dòng."""
    xh = th["xu_huong"]

    def g_moc(g):
        return None if not g else {"moc": g["moc"].isoformat(), "bai": g["bai"],
                                   "thao_luan": g["thao_luan"]}
    ss = xh.get("so_sanh")
    ra = {
        "thao_luan": th["thao_luan"],
        "la_mau": th.get("mau") or None,
        "xu_huong": {"don_vi": xh["don_vi"], "dinh": g_moc(xh["dinh"]),
                     "khong_so_sanh_vi": None if ss else xh.get("ly_do_khong_so_sanh"),
                     "so_sanh_7_ngay": None
                     if not ss else {"ky_nay": {**ss["ky_nay"], "tu": ss["ky_nay"]["tu"].isoformat(),
                                                "den": ss["ky_nay"]["den"].isoformat()},
                                     "ky_truoc": {**ss["ky_truoc"],
                                                  "tu": ss["ky_truoc"]["tu"].isoformat(),
                                                  "den": ss["ky_truoc"]["den"].isoformat()},
                                     "doi_bai_pt": ss["doi_bai"],
                                     "doi_thao_luan_pt": ss["doi_thao_luan"]}},
        "nguon_top": {p: [{"kenh": _sach(g["kenh"], 40), "bai": g["bai"],
                           "thao_luan": g["thao_luan"], "thuong_hieu": g["thuong_hieu"]}
                          for g in ds[:5]]
                      for p, ds in th["nguon"]["theo_nen_tang"].items()},
        "chu_de": {"da_gan": th["chu_de"]["da_gan"], "tong": th["chu_de"]["tong"],
                   "dong": [{"chu_de": g["chu_de"], "so": g["so"], "ti_le": g["ti_le"],
                             "tich_cuc": g[TC], "tieu_cuc": g[TI], "trung_lap": g[TL]}
                            for g in th["chu_de"]["dong"]]},
        "tu_khoa_top": [{"tu": _sach(g["tu"], 40), "so_bai": g["so_bai"]}
                        for g in th["tu_khoa"]["dong"][:15]],
    }
    if bl_yt is not None:
        tk = bl_yt.get("thong_ke") or {}
        # `so_binh_luan` = mọi dòng ghi sheet (gồm trả lời của chủ kênh/brand); thống kê tính
        # trên `tinh_thong_ke` — đưa đủ cả hai kẻo model nói "2/4 đã phân loại" khi là 2/2.
        ra["binh_luan_youtube"] = {
            "trang_thai": bl_yt.get("trang_thai"), "so_binh_luan": len(bl_yt.get("dong") or []),
            "video": bl_yt.get("video"), "tinh_thong_ke": tk.get("tong", 0),
            "khong_tinh_chu_kenh_thuong_hieu": tk.get("khong_tinh_chu_kenh_thuong_hieu", 0),
            "da_phan_loai": tk.get("da_phan_loai", 0),
            "sac_thai": {k: v["so"] for k, v in (tk.get("sac_thai") or {}).items()},
            "dong_thong_ke": bl_yt.get("dong_thong_ke") or None}
    return ra


# Bảng sheet — mọi dòng cùng số cột với tiêu đề. Cột số cùng MỘT độ rộng (`_R_SO`, đủ cho
# tiêu đề dài nhất "Bài của thương hiệu"): cột kề nhau cùng độ rộng gộp được một lời gọi
# dimension_range — đo sống 13/10/2026, đặt độ rộng là phần chậm nhất khi ghi 11 tab.
_R_SO, _R_TEN, _R_DAI = 180, 240, 320


def _so_cot(ten: str) -> T.Cot:
    return T.Cot(ten, "so_nguyen", rong=_R_SO)


def bang_xu_huong(th: dict) -> T.Bang:
    xh = th["xu_huong"]
    moc = "Ngày" if xh["don_vi"] == "ngày" else "Tuần từ"
    cot = [T.Cot(moc, "ngay", rong=_R_SO), _so_cot("Số bài"), _so_cot("Bình luận trên bài"),
           _so_cot("Thảo luận"), _so_cot("Bài của thương hiệu"), _so_cot(TC), _so_cot(TI),
           _so_cot(TL), _so_cot("Chưa phân loại")]
    dong = [[g["moc"].isoformat(), g["bai"], g["binh_luan"], g["thao_luan"],
             g["bai_thuong_hieu"], g[TC], g[TI], g[TL], g[CHUA]] for g in xh["dong"]]
    tong = [["TỔNG", sum(r[1] for r in dong), sum(r[2] for r in dong),
             sum(r[3] for r in dong), sum(r[4] for r in dong), sum(r[5] for r in dong),
             sum(r[6] for r in dong), sum(r[7] for r in dong), sum(r[8] for r in dong)]]
    return T.Bang(TAB_XU_HUONG, cot, dong, dong_tong=tong, gap_duoc=False,
                  mo_ta=f"Theo {xh['don_vi']} đăng (giờ VN): thảo luận = bài + bình luận "
                        "nền tảng báo (tính vào ngày đăng bài); sắc thái không gồm bài của "
                        "thương hiệu" + ("; ĐÂY LÀ MẪU — nguồn chạm trần/thiếu"
                                          if th.get("mau") else ""))


def bang_nguon(th: dict) -> T.Bang:
    cot = [T.Cot("Nền tảng", rong=_R_SO), T.Cot("Kênh", rong=_R_TEN), _so_cot("Thảo luận"),
           _so_cot("Số bài"), _so_cot("Bình luận trên bài"), _so_cot("Views"),
           _so_cot("Likes"), _so_cot("Followers"), _so_cot(TC), _so_cot(TI), _so_cot(TL),
           T.Cot("Của thương hiệu", rong=_R_SO), T.Cot("Bài nổi bật nhất", "link", rong=_R_DAI)]
    dong = [[_ten_nen(p), g["kenh"], g["thao_luan"], g["bai"], g["binh_luan"], g["views"],
             g["likes"], g["followers"], g[TC], g[TI], g[TL],
             "có" if g["thuong_hieu"] else "", g["link_noi_bat"]]
            for p, ds in th["nguon"]["theo_nen_tang"].items() for g in ds]
    return T.Bang(TAB_NGUON, cot, dong, gap_duoc=False,
                  mo_ta=f"Top {NGUON_MOI_NEN_TANG} kênh mỗi nền tảng theo thảo luận (bài + "
                        "bình luận trên bài)")


def bang_chu_de(th: dict) -> T.Bang:
    cot = [T.Cot("Chủ đề", rong=_R_TEN), _so_cot("Số bài"),
           T.Cot("Tỉ lệ %", "phan_tram_100", rong=_R_SO), _so_cot(TC), _so_cot(TI),
           _so_cot(TL), _so_cot("Sắc thái chưa phân loại")]
    dong = [[g["chu_de"], g["so"], "" if g["ti_le"] is None else g["ti_le"], g[TC], g[TI],
             g[TL], g[CHUA]] for g in th["chu_de"]["dong"]]
    return T.Bang(TAB_CHU_DE, cot, dong, gap_duoc=False,
                  mo_ta="Chủ đề × sắc thái của bài (không gồm bài của thương hiệu); tỉ lệ % "
                        "trên số bài ĐÃ gán chủ đề")


def bang_tu_khoa(th: dict) -> T.Bang:
    cot = [_so_cot("Hạng"), T.Cot("Từ khoá / hashtag", rong=_R_TEN), _so_cot("Số bài nhắc"),
           _so_cot(TC), _so_cot(TI), _so_cot(TL)]
    dong = [[i, g["tu"], g["so_bai"], g[TC], g[TI], g[TL]]
            for i, g in enumerate(th["tu_khoa"]["dong"], 1)]
    return T.Bang(TAB_TU_KHOA, cot, dong, gap_duoc=False,
                  mo_ta=f"Top {TU_KHOA_TOI_DA} cụm từ / hashtag theo số bài nhắc (≥"
                        f"{TU_KHOA_TOI_THIEU_BAI} bài; bỏ cụm chứa từ khoá đang quét)")


COT_BL_YT = ["Video", "Kênh video", "Người bình luận", "Nội dung bình luận", "Sắc thái",
             "Chủ đề", "Likes", "Trả lời", "Thời gian", "Link video", phan_loai.NGUON_COT]
_KIEU_BL_YT = {"Nội dung bình luận": "chu_dai", "Video": "chu_dai", "Likes": "so_nguyen",
               "Trả lời": "so_nguyen", "Link video": "link"}
_RONG_BL_YT = {"Video": _R_DAI, "Kênh video": _R_TEN, "Người bình luận": _R_TEN,
               "Nội dung bình luận": _R_DAI, "Link video": _R_DAI}


def dong_bl_yt(r: dict) -> list:
    return [r.get("video") or "", r.get("kenh_video") or "", r.get("kenh") or "",
            r.get("text") or "", r.get("sac_thai") or CHUA, r.get("chu_de") or CHUA,
            _so(r.get("likes")), _so(r.get("replies")), r.get("thoi_gian") or "",
            r.get("bai") or r.get("link") or "", r.get("nguon") or ""]


def cot_bl_yt() -> list:
    return [T.Cot(c, _KIEU_BL_YT.get(c, "chu"), rong=_RONG_BL_YT.get(c, _R_SO))
            for c in COT_BL_YT]


def bang_bl_yt(bl_yt: dict) -> T.Bang | None:
    rows = bl_yt.get("dong") or []
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: (str(r.get("bai")), -_so(r.get("likes"))))
    return T.Bang(TAB_BL_YT, cot_bl_yt(), [dong_bl_yt(r) for r in rows], gap_duoc=False,
                  mo_ta="Bình luận các video YouTube nhiều bình luận nhất (YouTube Data API, "
                        "miễn phí) — sắc thái/chủ đề do tool gán")


def cac_bang(th: dict, bl_yt: dict | None = None) -> list:
    """Bảng tổng hợp theo thứ tự tab. Bảng không có dòng nào thì bỏ (khỏi tab trống). Dưới
    `TOI_THIEU_BAI_TAB` bài thì không dựng 4 tab tổng hợp (đường xu hướng 30 ngày từ 2 bài
    chỉ là nhiễu, và sheet nhỏ nên giữ một tab "Dữ liệu") — câu `cau_tong_hop` vẫn có. Tab
    bình luận YouTube không phụ thuộc ngưỡng này."""
    ds = []
    if th["thao_luan"]["bai"] >= TOI_THIEU_BAI_TAB:
        ds.append(bang_xu_huong(th))
        if th["nguon"]["theo_nen_tang"]:
            ds.append(bang_nguon(th))
        if th["chu_de"]["da_gan"]:          # AI chưa gán bài nào thì bảng chỉ có "chưa phân loại"
            ds.append(bang_chu_de(th))
        if th["tu_khoa"]["dong"]:
            ds.append(bang_tu_khoa(th))
    b = bang_bl_yt(bl_yt) if bl_yt else None
    if b is not None:
        ds.append(b)
    return ds


def ten_cac_tab(th: dict | None, bl_yt: dict | None = None) -> list[str]:
    """Tên các tab tổng hợp SẼ có (để câu/tin nhắn không nhắc tab không tồn tại)."""
    return [b.ten for b in cac_bang(th, bl_yt)] if th else []


def so_lieu(th: dict) -> list:
    """Số liệu chính cho Tổng quan (chép từ `tong_hop`, không tính lại)."""
    tl = th["thao_luan"]
    sl = [T.SoLieu("Thảo luận (bài + bình luận trên bài)", tl["tong"], "so_nguyen",
                   ghi_chu="bình luận = số nền tảng hiển thị trên các bài đã quét")]
    g = th["xu_huong"]["dinh"]
    if g:
        tuan = th["xu_huong"]["don_vi"] != "ngày"
        sl.append(T.SoLieu("Tuần nhiều thảo luận nhất (từ ngày)" if tuan
                           else "Ngày nhiều thảo luận nhất", g["moc"].strftime("%d/%m/%Y"),
                           ghi_chu=f"{_so_vn(g['thao_luan'])} thảo luận, {_so_vn(g['bai'])} bài"))
    if th.get("mau"):
        sl.append(T.SoLieu("Đây là MẪU", "có nguồn chạm trần / thiếu",
                           ghi_chu="; ".join(th["mau"])[:300]))
    ss = th["xu_huong"].get("so_sanh")
    if ss:
        sl.append(T.SoLieu(f"Thảo luận {SO_SANH_NGAY} ngày cuối so với {SO_SANH_NGAY} ngày "
                           "liền trước", _pt_vn(ss["doi_thao_luan"], True),
                           ghi_chu=f"{_so_vn(ss['ky_nay']['thao_luan'])} so với "
                                   f"{_so_vn(ss['ky_truoc']['thao_luan'])} (trong khoảng đã quét)"))
    return sl
