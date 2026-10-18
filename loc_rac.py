"""Lọc spam / rác / trùng cho dữ liệu lắng nghe (đợt 2d, chủ dự án 15/10/2026: "tìm hiểu kĩ cơ
chế lọc spam, chống trùng... và 1 bài thì phải cào hết tất cả thảo luận sau khi đã áp dụng cơ chế").

Cách các nền tảng chuyên nghiệp làm (Talkwalker `noise_category`, Sprinklr spam classifier,
Meltwater gom bản trùng, Kompa/YouNet "loại spam, clone, seeding"): GIỮ dữ liệu thô, GẮN NHÃN
lý do, và báo cáo SỐ SẠCH bên cạnh số thô — người xem bật lại được phần đã lọc. Không hãng nào
công bố ngưỡng; ngưỡng dưới đây chốt theo dữ liệu thật của HAPAS (14/10/2026, 184 bình luận):
26 bình luận chỉ ".", "Hapas tặng" 11 lần từ 5 người (tham gia minigame lặp), 1 bình luận shop
giả "🔥Hot mua hàng chính hãng giảm 50% tại đây https://facebook.com/…", ~45 "Ib"/"Xin giá".

QUAN TRỌNG — "ib", "xin giá", "bn ạ" dưới bài của brand là KHÁCH HỎI MUA (ý định mua), không
phải spam: giữ là hợp lệ. Spam là bình luận kéo khách đi nơi khác (link lạ + lời chào hàng,
zalo/telegram của người bán khác, vay tiền, cờ bạc, việc nhẹ lương cao).

Nhãn bình luận (`binh_luan.loai`):
  hop_le       — tính vào thảo luận sạch, được gán sắc thái/chủ đề.
  it_noi_dung  — chỉ ".", "…", emoji, tag bạn bè, "chấm", "hóng": vẫn là tương tác (đếm vào
                 thảo luận thô) nhưng không gán sắc thái.
  spam         — quảng cáo/lừa đảo/kéo khách (`ly_do_loc` nói rõ loại; `affiliate_dan_ma` /
                 `affiliate_hang_loat` = mời dán mã giới thiệu vào Shopee, xem `dau_hieu_affiliate`).
  trung        — cùng người, cùng nội dung, cùng bài: giữ bản đầu, các bản sau là trùng.
  seeding      — cùng nội dung (≥ `SEEDING_TOI_THIEU_CHU` ký tự) từ ≥ `SEEDING_TAC_GIA` tài khoản
                 khác nhau trong `SEEDING_NGAY` ngày: dấu hiệu chiến dịch đăng hộ / bot.
  thuong_hieu  — chính thương hiệu trả lời.
Thuần Python, không gọi mạng — kiểm được bằng bài thử.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import timedelta, timezone

from dashboard import chuan_chu as CC

LOAI =("hop_le", "it_noi_dung", "spam", "trung", "seeding", "thuong_hieu")
#: Nhãn được gán sắc thái + tính vào "thảo luận sạch".
SACH = ("hop_le",)
TEN_LOAI = {"hop_le": "Hợp lệ", "it_noi_dung": "Ít nội dung", "spam": "Spam",
            "trung": "Trùng lặp", "seeding": "Seeding", "thuong_hieu": "Thương hiệu"}

SEEDING_TAC_GIA = 3
SEEDING_NGAY = 7
# Review 15/10: câu hỏi mua ngắn ("shop ơi cho mình xin giá ạ") nhiều khách cùng viết là
# chuyện thường — seeding phải đủ dài VÀ xuất hiện ở ≥ 2 bài (xem lang_nghe_db).
SEEDING_TOI_THIEU_CHU = 40
BAI_TRUNG_TOI_THIEU_CHU = 30

_RE_URL = re.compile(r"(https?://|www\.)\S+|\b[\w-]+\.(?:com|vn|net|xyz|top|site|shop|me|ly|link|io)"
                     r"(?:/\S*)?\b", re.IGNORECASE)
_RE_TAG = re.compile(r"@[\w.\-À-ỹ]+")
_RE_SDT = re.compile(r"(?<!\d)(?:\+?84|0)[\s.\-]?[35789](?:[\s.\-]?\d){8}(?!\d)")
_RE_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")

# Từ vựng spam phổ biến ở mục bình luận VN, so trên bản BỎ DẤU, chữ thường.
_SPAM = {
    "vay_tien": r"\b(vay (tien|von) (nhanh|online|khong the chap)|vay nhanh|giai ngan|"
                r"no xau van vay|app vay)\b",
    "co_bac": r"\b(nha cai|no hu|tai xiu|ca cuoc|ca do|game bai|xoc dia|lo de|soi keo|"
              r"casino|thuong nap|khuyen mai nap)\b",
    "viec_lam_mmo": r"\b(viec nhe luong cao|kiem tien (online|tai nha|de dang)|tuyen ctv|"
                    r"tuyen cong tac vien|viec lam tai nha|thu nhap \d|chot don tai nha|"
                    r"go chu tai nha|xac nhan don hang tai nha)\b",
    "keo_khach": r"\b(ket ban zalo|add zalo|lien he zalo|zalo:? ?0\d|"
                 r"(add|ket ban|lien he|vao nhom) (tele|telegram)|t\.me/|"
                 r"xem trang ca nhan (minh|em)|vao trang (minh|em) (xem|mua))\b",
    # Review 15/10: "shop mình có size L không", "có giảm 10% không shop" là KHÁCH hỏi — chỉ
    # bắt câu mời mua đi nơi khác.
    "ban_hang_khac": r"\b(mua (ngay|hang) tai day|xem (them )?(mau )?tai day|"
                     r"link (o|tai|duoi) (day|bio)|inbox (shop|minh) (de|nhan) (gia|uu dai))\b",
}
# Ranh giới từ cuối mẫu không khớp sau "%" ("giảm 50% tại đây") — thay bằng "không có chữ
# liền sau".
_SPAM_RE = {k: re.compile(v[:-2] + r"(?!\w)" if v.endswith(r"\b") else v)
            for k, v in _SPAM.items()}
_KHUYEN_MAI = re.compile(r"\b(giam|sale|khuyen mai|chinh hang|mua hang|freeship|hot|uu dai)\b")
_IT_CHU = re.compile(r"^(cham|cham cham|hong|up|upp|ok|oke|e|a|o|in)$")

# ───────────── spam affiliate "dán mã" (rà kho 15/10/2026) ─────────────
# 119 bình luận / 28 tài khoản trên 2 bài TikTok: "𝐃𝐚́𝐧 𝐦𝐚𝐱 𝐜𝐮𝐨̂́𝐢 𝐯𝐚̀𝐨 𝐬𝐨̣̂𝐩-𝐩𝐢𝐢 𝐥𝐚̀ 𝐫𝐚 𝐦𝐚̂̃𝐮 𝐯𝐚̀ 𝐠𝐢𝐚́
# AHS-WCM-DQN", "CJW-UJK-A88AH xóa 88 rồi zán cam ah" — mời dán mã giới thiệu vào Shopee. Mỗi tài
# khoản một mã nên luật seeding (cùng nội dung) không bắt được: 34 bình luận lọt vào thảo luận sạch,
# 28 bị đếm là "Giá/mua ở đâu/ý định mua". Bốn dấu hiệu:
#   ma    mã giới thiệu: ≥ 3 khúc CHỮ IN HOA/số nối gạch, ≥ 2 khúc có chữ cái, đứng riêng (không
#         bắt đầu/kết thúc giữa một mã dài hơn) — SĐT "0912-345-678", ngày "2026-10-15", mã đơn
#         "ORD-2410-0001", mẫu "HP-2024-01-BLK", cỡ "XXL-3XL-4XL" không khớp; xét trên bản NFKC,
#         đã bỏ link; mã có tên thương hiệu (voucher của chính brand) không tính;
#   cum   lời dặn dán mã, so trên bản NFKC + chữ thường GIỮ dấu (bỏ dấu thì "dẫn vào", "người dân
#         mà", "sẵn cam" khớp nhầm): "dán/zán mã|max|vào|cam|code", "săn cam", "xóa 88 rồi";
#   san   nhắc sàn "shopee", "sộp-pii" — khách thật cũng hỏi "có bán trên shopee không" nên đây là
#         dấu hiệu YẾU;
#   font  ≥ 30% chữ cái (và ≥ 4 chữ) là chữ kiểu cách U+1D400–1D7FF — cách né bộ lọc từ khoá.
# MỘT bình luận là spam (`affiliate_dan_ma`) khi: MÃ + lời dặn, MÃ ĐẬM (mọi khúc có chữ, không khúc
# nào là cỡ) + tên sàn, hoặc CHỮ KIỂU CÁCH + lời dặn. Chữ kiểu cách + tên sàn KHÔNG đủ (khách gõ bằng
# bàn phím kiểu "có bán trên shopee không"); mã thường + tên sàn cũng không ("Mẫu AURA-01-BLK còn
# trên shopee không").
# Cấp BÀI (`affiliate_hang_loat`, chạy ở kho): ≥ `AFF_TAC_GIA` tài khoản khác nhau cùng có MÃ, hoặc
# chữ kiểu cách + (lời dặn | tên sàn), dưới MỘT bài trong `AFF_GIO` giờ (theo giờ ĐĂNG thật) → cả
# loạt là spam (bắt bản chỉ có mã, không lời). Mã có trong bài/bình luận của chính thương hiệu
# (minigame, voucher) không tính.
AFF_TAC_GIA = 5
AFF_GIO = 48
_RE_MA_AFF = re.compile(r"(?<![A-Za-z0-9\-–—])[A-Z0-9]{3,6}(?:[-–—][A-Z0-9]{2,6}){2,}"
                        r"(?![A-Za-z0-9\-–—])")
_RE_KHUC_CO = re.compile(r"^\d{0,2}X{0,4}[SML]$|^\d{1,3}$")      # khúc là cỡ (XXL, 3XL) hoặc số
_RE_CUM_AFF = re.compile(r"(?<!\w)(?:(?:dán|zán|zan) (?:mã|max|vào|cam|code)|săn cam"
                         r"|(?:xóa|xoá|xoa) \d+ (?:rồi|r|đi|là))(?!\w)")
_RE_SAN_AFF = re.compile(r"\b(?:sh?op+e+|sh?op+[\s.\-]*pi+)\b")


def _ten_brand(thuong_hieu) -> set[str]:
    """Tên/từ khoá brand để nhận mã của chính brand: cả cụm viết liền ("hapasofficial") và từng từ
    ≥ 4 chữ ("hapas") — "HAPAS-SALE-50" là mã brand dù dự án chỉ có tên "HAPAS Official"."""
    ra: set[str] = set()
    for x in thuong_hieu:
        t = CC.bo_dau(x).strip()
        if len(t) >= 3:
            ra.add(t.replace(" ", ""))
            ra.update(w for w in t.split() if len(w) >= 4)
    return ra


def ma_gioi_thieu(s: str, thuong_hieu: list[str] | tuple = ()) -> set[str]:
    """Các mã giới thiệu (in hoa, gạch thường) trong chuỗi — xem dấu hiệu `ma` ở trên."""
    brand = _ten_brand(thuong_hieu)
    ra = set()
    for m in _RE_MA_AFF.finditer(CC.nfkc(_RE_URL.sub(" ", str(s or "")))):
        khuc = re.split("[-–—]", m.group())
        if sum(any(c.isalpha() for c in k) for k in khuc) < 2:
            continue
        if all(_RE_KHUC_CO.match(k) for k in khuc):
            continue
        ma = "-".join(khuc)
        if not any(b and b in ma.lower().replace("-", "") for b in brand):
            ra.add(ma)
    return ra


def dau_hieu_affiliate(s: str, thuong_hieu: list[str] | tuple = ()) -> set[str]:
    """Các dấu hiệu affiliate có trong bình luận: tập con của {"ma", "cum", "san", "font"}."""
    raw = str(s or "")
    ra: set[str] = set()
    if ma_gioi_thieu(raw, thuong_hieu):
        ra.add("ma")
    if _RE_CUM_AFF.search(CC.thuong(raw)):
        ra.add("cum")
    if _RE_SAN_AFF.search(CC.bo_dau(raw)):      # cả trong link "shopee.vn"
        ra.add("san")
    kieu, chu = CC.dem_chu_kieu(raw)
    if kieu >= 4 and kieu >= 0.3 * chu:
        ra.add("font")
    return ra


def ma_dam(ma: str) -> bool:
    """Mã "đậm" giới thiệu: MỌI khúc có chữ cái và không khúc nào là cỡ (AHS-WCM-DQN, KQX-77A-PLM,
    CJW-UJK-A88AH). Mã sản phẩm hay có khúc toàn số / cỡ (AURA-01-BLK, TUI-BLK-XL)."""
    return all(any(c.isalpha() for c in k) and not _RE_KHUC_CO.match(k) for k in ma.split("-"))


def la_affiliate(s: str, thuong_hieu: list[str] | tuple = ()) -> bool:
    """Spam affiliate ngay ở MỘT bình luận: mã + lời dặn; mã ĐẬM (`ma_dam`) + tên sàn; hoặc chữ kiểu
    cách + lời dặn. Mã thường + tên sàn là khách hỏi "Mẫu AURA-01-BLK còn trên shopee không"."""
    d = dau_hieu_affiliate(s, thuong_hieu)
    if "ma" in d and "cum" in d:
        return True
    if "ma" in d and "san" in d and any(ma_dam(m) for m in ma_gioi_thieu(s, thuong_hieu)):
        return True
    return {"font", "cum"} <= d


def khoa_tac_gia(s) -> str:
    """Tài khoản để đếm "khác nhau": chữ thường, gộp khoảng trắng, bỏ @ — GIỮ số (khác `chuan`:
    "user123" và "user456" là hai người)."""
    return " ".join(CC.thuong(s).split()).lstrip("@")


def co_dau_hieu_hang_loat(s: str, thuong_hieu: list[str] | tuple = (),
                          ma_brand: set[str] | frozenset = frozenset()) -> bool:
    """Dấu hiệu cho luật cấp BÀI (một mình chưa đủ là spam): có mã giới thiệu KHÔNG phải mã của
    thương hiệu (`ma_brand`: mã trong bài / bình luận của brand — minigame, voucher), hoặc chữ kiểu
    cách + (lời dặn | tên sàn). Chữ kiểu cách một mình không đủ."""
    d = dau_hieu_affiliate(s, thuong_hieu)
    if "ma" in d and ma_gioi_thieu(s, thuong_hieu) - set(ma_brand):
        return True
    return "font" in d and bool(d & {"cum", "san"})


def ma_cua_brand(rows: list[dict], thuong_hieu: list[str] | tuple = (),
                 noi_dung_bai: dict | None = None) -> dict:
    """{khoá bài: các mã có trong nội dung bài và bình luận của thương hiệu} — minigame, voucher."""
    ra: dict = {}
    for k, nd in (noi_dung_bai or {}).items():
        ra.setdefault(k, set()).update(ma_gioi_thieu(nd, thuong_hieu))
    for r in rows:
        if r.get("cua_thuong_hieu") or r.get("loai") == "thuong_hieu":
            ra.setdefault(r.get("khoa_bai"), set()).update(
                ma_gioi_thieu(r.get("noi_dung"), thuong_hieu))
    return ra


def affiliate_hang_loat(rows: list[dict], ha_duoc: tuple = ("hop_le",), *,
                        thuong_hieu: list[str] | tuple = (),
                        noi_dung_bai: dict | None = None) -> list[tuple]:
    """Luật cấp BÀI: dưới cùng một bài, ≥ `AFF_TAC_GIA` tài khoản KHÁC NHAU có dấu hiệu
    (`co_dau_hieu_hang_loat`) trong một khung `AFF_GIO` giờ → mọi bình luận có dấu hiệu trong khung
    đó là spam. `rows`: dict có khoa_bai, ma, tac_gia, noi_dung, luc (= giờ ĐĂNG thật; None thì bỏ
    qua — giờ cào không nói hai bình luận cách nhau bao lâu), loai, cua_thuong_hieu. Bình luận của
    thương hiệu và `noi_dung_bai` ({khoá bài: nội dung bài}) chỉ dùng để biết mã nào là của brand.
    Dòng spam affiliate sẵn có vẫn được đếm (cùng một đợt). Chỉ trả các dòng đang ở nhãn `ha_duoc`
    (không bao giờ nâng nhãn). -> [(khoa_bai, ma)] cần hạ thành spam."""
    ma_brand = ma_cua_brand(rows, thuong_hieu, noi_dung_bai)
    theo_bai: dict = {}
    for r in rows:
        if r.get("cua_thuong_hieu") or r.get("loai") == "thuong_hieu" or r.get("luc") is None:
            continue
        if co_dau_hieu_hang_loat(r.get("noi_dung"), thuong_hieu,
                                 ma_brand.get(r.get("khoa_bai"), frozenset())):
            theo_bai.setdefault(r.get("khoa_bai"), []).append(r)
    khung = timedelta(hours=AFF_GIO)
    ra: list[tuple] = []
    for ds in theo_bai.values():
        ds.sort(key=lambda r: r["luc"])
        tg = [khoa_tac_gia(r.get("tac_gia")) for r in ds]
        trong: dict[str, int] = {}
        dau = 0
        trung: set[int] = set()
        for cuoi, r in enumerate(ds):              # cửa sổ trượt [dau, cuoi] dài ≤ AFF_GIO giờ
            if tg[cuoi]:
                trong[tg[cuoi]] = trong.get(tg[cuoi], 0) + 1
            while r["luc"] - ds[dau]["luc"] > khung:
                if tg[dau]:
                    trong[tg[dau]] -= 1
                    if not trong[tg[dau]]:
                        del trong[tg[dau]]
                dau += 1
            if len(trong) >= AFF_TAC_GIA:
                trung.update(range(dau, cuoi + 1))
        ra += [(ds[i].get("khoa_bai"), ds[i].get("ma")) for i in sorted(trung)
               if ds[i].get("loai") in ha_duoc]
    return ra


def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def chuan(s: str) -> str:
    """Chuẩn hoá để so trùng: bỏ dấu, chữ thường, bỏ @tag/link/emoji/dấu câu, gộp ký tự lặp
    ("đẹppppp" = "depp"), số thành 0, gộp khoảng trắng."""
    t = _RE_EMOJI.sub(" ", _RE_URL.sub(" ", _RE_TAG.sub(" ", str(s or ""))))
    t = bo_dau(unicodedata.normalize("NFC", t))
    t = re.sub(r"\d", "0", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"(\w)\1{2,}", r"\1\1", t)
    return " ".join(t.split())


def ma_noi_dung(s: str, toi_thieu: int = 1) -> str | None:
    """Băm 16 ký tự của nội dung đã chuẩn hoá — None khi nội dung (bỏ khoảng trắng) ngắn hơn
    `toi_thieu` ký tự (quá ngắn để kết luận là trùng)."""
    c = chuan(s)
    if not c or len(c.replace(" ", "")) < toi_thieu:
        return None
    return hashlib.sha1(c.encode("utf-8")).hexdigest()[:16]


def ly_do_spam(s: str, thuong_hieu: list[str] | tuple = ()) -> str:
    """Loại spam đầu tiên khớp ("" nếu không phải spam). `thuong_hieu`: tên/từ khoá của dự án —
    link kèm tên brand không phải shop giả."""
    raw = str(s or "")
    t = bo_dau(raw)
    for k, rx in _SPAM_RE.items():
        if rx.search(t):
            return k
    co_link = bool(_RE_URL.search(raw))
    brand = [bo_dau(x).strip() for x in thuong_hieu if len(str(x).strip()) >= 3]
    if co_link and _KHUYEN_MAI.search(t) and not any(b in t for b in brand):
        return "lien_ket_quang_cao"       # link lạ + lời chào hàng (shop giả mạo)
    if _RE_SDT.search(raw) and co_link:
        return "so_dien_thoai_quang_cao"  # SĐT + link; SĐT đơn thuần = khách để lại số
    if la_affiliate(raw, thuong_hieu):
        return "affiliate_dan_ma"         # mã giới thiệu / chữ kiểu cách + lời dặn dán mã
    return ""


def it_noi_dung(s: str) -> bool:
    """Chỉ ".", "…", emoji, tag bạn bè, "chấm", "hóng" — không có ý để gán sắc thái."""
    c = chuan(s)
    return not c or bool(_IT_CHU.match(c))


def phan_loai(rows: list[dict], thuong_hieu: list[str] | tuple = ()) -> None:
    """Gắn `loai`, `ly_do_loc`, `ma_noi_dung` cho từng bình luận (dict có `khoa_bai`,
    `tac_gia`, `noi_dung`, `cua_thuong_hieu`), tại chỗ. Trùng = cùng bài + cùng người + cùng
    nội dung (giữ bản đầu). Seeding xét ở kho (cần lịch sử) — `lang_nghe_db.ghi_binh_luan`."""
    thay: set[tuple] = set()
    for r in rows:
        text = r.get("noi_dung") or ""
        r["ma_noi_dung"] = ma_noi_dung(text, SEEDING_TOI_THIEU_CHU)
        if r.get("cua_thuong_hieu"):
            r["loai"], r["ly_do_loc"] = "thuong_hieu", None
            continue
        sp = ly_do_spam(text, thuong_hieu)
        if sp:
            r["loai"], r["ly_do_loc"] = "spam", sp
            continue
        khoa = (r.get("khoa_bai"), chuan(r.get("tac_gia") or ""), chuan(text))
        if khoa[1] and khoa in thay:
            r["loai"], r["ly_do_loc"] = "trung", "cung_nguoi_cung_noi_dung"
            continue
        thay.add(khoa)
        if it_noi_dung(text):
            r["loai"], r["ly_do_loc"] = "it_noi_dung", None
            continue
        r["loai"], r["ly_do_loc"] = "hop_le", None


def bai_spam(text: str) -> str:
    """Bài (tìm theo từ khoá, không phải kênh nhà) mang dấu hiệu spam rõ — bỏ trước bước AI."""
    t = bo_dau(text)
    for k in ("vay_tien", "co_bac", "viec_lam_mmo"):
        if _SPAM_RE[k].search(t):
            return k
    return ""


# ───────────── seeding affiliate cấp BÀI (18/10/2026) ─────────────
# Điều tra khoảng thiếu so với Kompa (18/10/2026, báo cáo `bao_cao_kompa.md` §4.1): khoảng 25 tài
# khoản affiliate TikTok đăng 10–180 video HAPAS MỖI NGÀY, caption chỉ có hashtag (#HAPAS
# #QUATANG2010 #HAPASsuperbrandday…), 0,03 bình luận/bài. Đọc đủ ngày 15/10: thuytrang.lee 177
# video, hanngoc.store ≥ 120, _xiwiuu_ 62, minmetbay 45, anh1m66 44 — mười tài khoản ≥ 510 video,
# kho có 50. Chủ dự án chốt 18/10/2026: KHÔNG đếm video seeding affiliate.
#
# Luật theo TÀI KHOẢN (một video seeding nhìn y như video thường — chỉ nhịp đăng của cả tài khoản
# lộ ra nó), trên bài liên quan của tài khoản trong lịch sử kho + sổ seeding + lô đang xử lý:
#   nhịp       ≥ `bai_mot_ngay` bài trong MỘT ngày (giờ VN) HOẶC ≥ `bai_bay_ngay` bài trong 7 ngày
#              liền;
#   VÀ ít tương tác: trung vị bình luận ≤ `trung_vi_bl` VÀ trung vị lượt xem ≤ `trung_vi_xem`.
# Số đo chọn ngưỡng (18/10/2026, kho 17/10 ∪ raw Kompa 18/10, bài liên quan 17/09 → 18/10):
#   • 16 tài khoản bị bắt, 15 nằm trong 25 tài khoản seeding của báo cáo: nhóm nặng 5–177
#     bài/ngày, trung vị 0 bình luận, trung vị xem 209–11.516 (thuytrang.lee 372, hanngoc.store 213,
#     phamxuan1992 5.913, duycom.real 11.516). Chỉ kho (lượt hằng ngày, trước khi dọn): 11 tài khoản.
#   • 10 tài khoản còn lại của báo cáo đăng ≤ 4 bài/ngày (sei.review, nikko.daily…) — không phân
#     biệt được với nhà sáng tạo / review thật đăng 1–3 bài/ngày, nên KHÔNG bắt. Hạ `bai_mot_ngay`
#     xuống 4 thì bắt thêm 9 tài khoản, phần lớn là review nhỏ; nâng lên 6 thì sót 4 tài khoản seeding.
#   • Có thảo luận thật thì không bị bắt dù đăng dày: hoangnhiennhien 5 bài/ngày, trung vị 38 bình
#     luận; bossgirl.media 6 bài/ngày, trung vị 22.
#   • `trung_vi_xem` 15.000 nằm giữa nhóm seeding (≤ 11.516) và người có khán giả thật: livestream
#     bán hàng longphamdtest 12 bài/ngày, trung vị 1 bình luận nhưng 30.114 xem (video 2,4 triệu);
#     KOL le_anh_nuoi (1,8 triệu follower) 6 bài/ngày, 18.373 xem. Bỏ điều kiện xem thì bắt thêm
#     5 tài khoản như vậy.
#   • `bai_bay_ngay` 20: không tài khoản nào trong số đo đổi kết quả giữa 15, 20 và 25. Ngưỡng này
#     dành cho lượt hằng ngày, khi kho chỉ thấy vài bài mỗi ngày của một tài khoản seeding.
# Raw Kompa: 1.210/2.123 bài liên quan kho chưa có là bài seeding (1.307/13.110 thảo luận). Kho
# 17/10: 332 bài seeding của 11 tài khoản theo lịch sử kho; 377 bài / 16 tài khoản khi sổ seeding đã
# có nhịp đăng từ raw.
# Bài của tài khoản seeding mà TỰ có ≥ `giu_bl_tu` bình luận vẫn giữ, vì có thảo luận thật (video
# 26/09 của thuytrang.lee: 69 bình luận, 1,5 triệu xem). Kênh nhà (`nguon.loai = kenh_nha`) và tài
# khoản mang tên brand ở định danh hoặc tên hiển thị (cửa hàng hapasgigamall, hapas.aeonth,
# hapasperfume; trang Facebook id số "HAPAS SÀI GÒN" 7 bài/ngày, "HAPAS Vincom Đà Nẵng" 5 bài/ngày
# — `mien_ten_brand`) không bao giờ là seeding. Bài bị loại KHÔNG vào `bai` (không đếm), nằm ở sổ
# "đã loại" với lý do `LY_DO_SEEDING_BAI` + sổ seeding (nhịp đăng). Soát 18/10/2026 (H1): sổ KHÔNG
# chặn vĩnh viễn — mỗi lượt gặp lại, bài được xét lại bằng luật hiện hành với số mới (không tốn AI,
# không cào bình luận): bài lên ≥ `giu_bl_tu` bình luận, trung vị tài khoản tăng, tắt luật / đổi
# ngưỡng, tài khoản thành kênh nhà thì bài đi tiếp tới AI như bài mới.
SEEDING_BAI = {"bat": True, "bai_mot_ngay": 5, "bai_bay_ngay": 20, "trung_vi_bl": 2,
               "trung_vi_xem": 15000, "giu_bl_tu": 10, "ngay": 35, "mien_ten_brand": True}
#: Khoảng hợp lệ của từng ngưỡng (ngoài khoảng / rác / bool → mặc định). 0 ở `trung_vi_xem`,
#: `giu_bl_tu` = bỏ điều kiện đó.
_GIOI_HAN_SEEDING = {"bai_mot_ngay": (2, 10_000), "bai_bay_ngay": (2, 100_000),
                     "trung_vi_bl": (0, 1_000_000), "trung_vi_xem": (0, 10 ** 9),
                     "giu_bl_tu": (0, 1_000_000), "ngay": (7, 92)}
LY_DO_SEEDING_BAI = "seeding_affiliate"
_VN = timezone(timedelta(hours=7))


def cau_hinh_seeding(du_an: dict | None) -> dict:
    """Cấu hình HIỆU LỰC của luật seeding affiliate cấp bài (`du_an.cau_hinh.seeding`). Thiếu khối /
    thiếu `bat` = BẬT với ngưỡng mặc định (`SEEDING_BAI`); chỉ `bat` đúng bằng False là tắt (như
    `kiem_do_phu.cau_hinh`). Số rác / bool / ngoài `_GIOI_HAN_SEEDING` → mặc định."""
    goc = (du_an or {}).get("cau_hinh")
    goc = goc if isinstance(goc, dict) else {}
    x = goc.get("seeding") if isinstance(goc.get("seeding"), dict) else {}
    ra = dict(SEEDING_BAI)
    ra["bat"] = x.get("bat", True) is not False
    ra["mien_ten_brand"] = x.get("mien_ten_brand", True) is not False
    for k, (lo, hi) in _GIOI_HAN_SEEDING.items():
        v = x.get(k)
        if v is None or isinstance(v, bool):
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if lo <= n <= hi:
            ra[k] = n
    return ra


def khoa_tai_khoan(nen_tang, tai_khoan) -> tuple[str, str] | None:
    """(nền tảng, tài khoản chữ thường, bỏ @) để gom bài theo người đăng; None khi không biết
    tài khoản (YouTube, Facebook từ scrapeforge) hoặc là bài web (tên miền không phải người đăng)."""
    p = str(nen_tang or "").strip().lower()
    u = str(tai_khoan or "").strip().lstrip("@").lower()
    if not p or not u or p == "web":
        return None
    return p, u


def ten_brand_trong(tai_khoan: str, thuong_hieu) -> bool:
    """Định danh / tên hiển thị mang tên brand (`thuong_hieu` = tên + mã dự án; so bỏ dấu, bỏ dấu
    câu): cửa hàng / kênh phụ của chính brand ("hapas.aeonth", "hapasgigamall", "HAPAS SÀI GÒN") —
    không xét seeding."""
    u = re.sub(r"[^a-z0-9]", "", bo_dau(tai_khoan))
    return bool(u) and any(b and b in u for b in _ten_brand(thuong_hieu))


def _so_hay_none(v) -> int | None:
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _trung_vi(xs: list[int]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    g = len(s) // 2
    return float(s[g]) if len(s) % 2 else (s[g - 1] + s[g]) / 2


def tai_khoan_seeding(bai: list[dict], cfg: dict, mien: set | frozenset = frozenset(),
                      thuong_hieu: list[str] | tuple = ()) -> dict[tuple[str, str], dict]:
    """THUẦN. Tài khoản seeding affiliate theo luật ở đầu mục. `bai` = bài liên quan (lịch sử kho,
    sổ seeding, lô đang xử lý): [{"tk": (nền tảng, tài khoản) | None, "khoa", "dang_luc"
    (datetime có múi giờ), "bl", "xem", tuỳ chọn "ten" (tên hiển thị)}] — trùng khoá chỉ đếm một
    lần (ngày theo dòng đầu; bình luận / xem lấy số lớn nhất). `mien` = tập (nền tảng, tài khoản) kênh
    nhà. Tài khoản mang tên brand ở định danh HOẶC tên hiển thị (trang Facebook của cửa hàng có
    định danh là id số: "HAPAS SÀI GÒN", "HAPAS Vincom Đà Nẵng" — đo raw 17/10) được miễn. ->
    {tài khoản: {"so_bai", "max_ngay", "ngay", "max_7", "tv_bl", "tv_xem"}} — CHỈ tài khoản bị
    coi là seeding.

    Trung vị chỉ tính trên số ĐỌC ĐƯỢC; tài khoản không có số bình luận nào thì không kết luận
    (không bắt). Không có số xem nào thì bỏ điều kiện xem (bài Facebook ảnh không có lượt xem)."""
    if not cfg.get("bat"):
        return {}
    theo: dict[tuple[str, str], dict[str, dict]] = {}
    brand: set[tuple[str, str]] = set()
    for r in bai:
        tk = r.get("tk")
        if not tk or not r.get("khoa") or r.get("dang_luc") is None or tk in mien:
            continue
        if cfg.get("mien_ten_brand", True) and (ten_brand_trong(tk[1], thuong_hieu)
                                                or ten_brand_trong(r.get("ten") or "",
                                                                   thuong_hieu)):
            brand.add(tk)
            continue
        cu = theo.setdefault(tk, {}).get(r["khoa"])
        if cu is None:
            theo[tk][r["khoa"]] = {"ngay": r["dang_luc"].astimezone(_VN).date(),
                                   "bl": _so_hay_none(r.get("bl")),
                                   "xem": _so_hay_none(r.get("xem"))}
        else:
            # Số luỹ kế (soát 18/10/2026, H1): giữ số LỚN NHẤT của các lần đọc — sổ seeding có thể
            # còn số của lần thấy đầu, lô đang xử lý mang số mới.
            for k in ("bl", "xem"):
                v = _so_hay_none(r.get(k))
                if v is not None and (cu[k] is None or v > cu[k]):
                    cu[k] = v
    ra: dict[tuple[str, str], dict] = {}
    for tk, cac in theo.items():
        if tk in brand:                   # một dòng bất kỳ mang tên brand là đủ miễn
            continue
        dem: dict = {}
        for x in cac.values():
            dem[x["ngay"]] = dem.get(x["ngay"], 0) + 1
        ngay_dinh = max(sorted(dem), key=lambda d: dem[d])
        max_7 = max(sum(n for d, n in dem.items() if 0 <= (d - d0).days < 7) for d0 in dem)
        if dem[ngay_dinh] < cfg["bai_mot_ngay"] and max_7 < cfg["bai_bay_ngay"]:
            continue
        tv_bl = _trung_vi([x["bl"] for x in cac.values() if x["bl"] is not None])
        if tv_bl is None or tv_bl > cfg["trung_vi_bl"]:
            continue
        tv_xem = _trung_vi([x["xem"] for x in cac.values() if x["xem"] is not None])
        if cfg.get("trung_vi_xem") and tv_xem is not None and tv_xem > cfg["trung_vi_xem"]:
            continue
        ra[tk] = {"so_bai": len(cac), "max_ngay": dem[ngay_dinh], "ngay": ngay_dinh,
                  "max_7": max_7, "tv_bl": tv_bl, "tv_xem": tv_xem}
    return ra


def giu_bai_seeding(bl, cfg: dict) -> bool:
    """Bài của tài khoản seeding vẫn GIỮ khi tự có ≥ `giu_bl_tu` bình luận (có thảo luận thật)."""
    n = _so_hay_none(bl)
    return bool(cfg.get("giu_bl_tu")) and n is not None and n >= cfg["giu_bl_tu"]


def cau_seeding(tk: tuple[str, str], x: dict) -> str:
    """Một câu gọn về vì sao tài khoản bị coi là seeding (phễu, bản in của script)."""
    xem = (", trung vị " + f"{int(x['tv_xem']):,}".replace(",", ".") + " xem"
           if x.get("tv_xem") is not None else "")
    return (f"{tk[0]} @{tk[1]}: {x['so_bai']} bài, cao nhất {x['max_ngay']} bài ngày "
            f"{x['ngay']:%d/%m}, {x['max_7']} bài/7 ngày, trung vị {x['tv_bl']:g} bình luận{xem}")
