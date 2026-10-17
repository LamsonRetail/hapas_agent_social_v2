"""Khử trùng bài Facebook trong kho lắng nghe `lang_nghe` (17/10/2026).

Vì sao: đo thật trên DB production 17/10/2026 — mỗi lượt cào, actor trả một pfbid KHÁC cho cùng
một bài Facebook, mà kho khoá bài theo pfbid (`bai.khoa` = "facebook:pfbid…"), nên một bài bị
lưu nhiều lần. 161 bài FB của hapas có 24 nhóm trùng (cùng chủ bài + cùng phút đăng), 60 dòng,
thừa 36: 22/24 nhóm cùng nội dung (bản trùng thật), 2/24 nhóm khác nội dung (bài KHÁC nhau đăng
cùng phút — không được gộp). Vòng 2 thử actor: 30% dòng của `hapasglobal` là bản trùng (16 bài
chiếm 23 dòng), like tăng dần giữa các bản (12 → 24 → 25) — mỗi lượt quét lại đẻ một dòng mới.

Khoá `bai.khoa` GIỮ NGUYÊN (bình luận, chỉ số ngày, sổ của Mark đều trỏ theo nó). Lúc ghi, bài
FB khớp bài đã có theo thứ tự:
  1. cùng id số (`ma_so_fb`): actor trả `postId` / `post_id` / `post.id` / `feedbackId`, hoặc
     bóc từ link `/posts/<số>`, `/videos/<số>`, `/reel/<số>`, `/permalink/<số>`,
     `story_fbid=<số>`; kể cả khoá cũ dạng "facebook:<số>";
  2. không có id chung: cùng chủ bài + cùng phút đăng + cùng nội dung (`cung_bai`). Chủ bài so
     theo TÀI KHOẢN (`tai_khoan` / tên trang trong link) trước, tên hiển thị chỉ khi cả hai bên
     đều không có tài khoản (`cung_chu`); nội dung so CHỮ KÝ chặt (`chu_ky_noi_dung`: giữ chữ số,
     link; chỉ gộp khoảng trắng, NFKC, chữ thường, 200 ký tự đầu như cách đo) — soát 17/10/2026.
Khớp thì dùng lại khoá cũ. Module THUẦN (không DB, không mạng): dùng chung cho lượt ghi
(`lang_nghe_db.ghi_bai`), lượt tìm theo từ khoá (`theo_doi._tach_va_giu`) và script gộp một lần
(`scripts/lang_nghe_gop_bai_fb.py`).
"""
from __future__ import annotations

import base64
import binascii
import datetime
import re
import unicodedata

import loc_rac

#: Id số của bài/video Facebook: 5–25 chữ số (id trang/bài hiện 15–18 chữ số).
_RE_SO = re.compile(r"\d{5,25}")
# Link có id số của CHÍNH bài: /posts/<số> (cả "/posts/<số>:<số>" của trang), /videos/<số>,
# /reel/<số>, /permalink/<số>, story_fbid=<số>. KHÔNG lấy `fbid=` (id ẢNH, không phải id bài) và
# `id=` (id CHỦ trang trong permalink.php).
_RE_LINK = re.compile(r"(?:/posts/|/videos/|/reels?/|/permalink/|[?&]story_fbid=)(\d{5,25})(?!\d)")
_RE_KHOA = re.compile(r"facebook:(\d{5,25})")
# Đoạn đầu đường dẫn không phải tên chủ bài.
_SLUG_CHUNG = {"permalink.php", "story.php", "photo.php", "photo", "photos", "groups", "reel",
               "reels", "watch", "videos", "people", "profile.php", "share", "events", "media",
               "posts", "pages", "pg", "hashtag", "login", "l.php", "plugins"}


def la_so(v) -> str | None:
    """Chuỗi chữ số 5–25 ký tự (id số Facebook) hoặc None. Bool/số thực không tính."""
    if isinstance(v, bool) or v is None:
        return None
    s = str(v).strip()
    return s if _RE_SO.fullmatch(s) else None


def ma_so_tu_link(link) -> str | None:
    """Id số của bài bóc từ link (None với link pfbid, link ảnh, link không phải Facebook)."""
    m = _RE_LINK.search(str(link or ""))
    return m.group(1) if m else None


def _tu_feedback(v) -> str | None:
    """`feedbackId` = base64("feedback:<id bài>") (apify, thedoor)."""
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        s = base64.b64decode(v.strip() + "=" * (-len(v.strip()) % 4)).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return None
    m = re.fullmatch(r"feedback:(\d{5,25})", s.strip())
    return m.group(1) if m else None


def ma_so_tu_goc(goc) -> str | None:
    """Id số của bài trong item THÔ của actor Facebook. Đọc ĐÚNG các trường id bài đã biết:
    `postId` (apify~facebook-posts-scraper), `post_id` (scrapeforge / danek, kiểu RapidAPI),
    `post.id` (thedoor), `feedbackId` / `post.feedback_id`, `topLevelUrl`. KHÔNG đọc `id` trơn —
    nghĩa của nó khác nhau giữa các actor."""
    if not isinstance(goc, dict):
        return None
    bai = goc.get("post") if isinstance(goc.get("post"), dict) else {}
    for v in (goc.get("postId"), goc.get("post_id"), bai.get("id")):
        if la_so(v):
            return la_so(v)
    for v in (goc.get("feedbackId"), goc.get("feedback_id"), bai.get("feedback_id")):
        if _tu_feedback(v):
            return _tu_feedback(v)
    return ma_so_tu_link(goc.get("topLevelUrl"))


def ma_so_fb(d: dict) -> str | None:
    """Id số của bài cho một dòng (dòng chuẩn hoá kiểu social_listen hoặc dòng ghi kho): trường
    `ma_so_fb` bộ chuẩn hoá đã điền → item thô (`__goc` / `_goc`) → link."""
    if not isinstance(d, dict):
        return None
    so = la_so(d.get("ma_so_fb"))
    if so:
        return so
    for k in ("__goc", "_goc"):
        so = ma_so_tu_goc(d.get(k))
        if so:
            return so
    return ma_so_tu_link(d.get("link"))


def cac_ma_so(r: dict) -> set[str]:
    """Mọi id số biết được của dòng `r`: cột `ma_so_fb`, khoá "facebook:<số>", id trong link. Hai
    dòng có chung một id = cùng một bài (id Facebook không trùng giữa các đối tượng)."""
    ra = {x for x in (la_so(r.get("ma_so_fb")), ma_so_tu_link(r.get("link"))) if x}
    m = _RE_KHOA.fullmatch(str(r.get("khoa") or ""))
    if m:
        ra.add(m.group(1))
    return ra


def _gon(s) -> str:
    return re.sub(r"[^a-z0-9]", "", loc_rac.bo_dau(str(s or "")))


def tai_khoan_bai(r: dict) -> set[str]:
    """Định danh TÀI KHOẢN của chủ bài (dạng gọn: bỏ dấu, chỉ chữ + số): cột `tai_khoan` và đoạn
    tên/id trang trong link ("facebook.com/hapaschinhhanggiatot/posts/pfbid…", thedoor
    "facebook.com/<id trang>/posts/<id bài>"), bỏ đường dẫn chung (`_SLUG_CHUNG`: groups,
    permalink.php…). Rỗng khi dòng chỉ có tên hiển thị."""
    ra = {g for g in (_gon(r.get("tai_khoan")),) if g}
    m = re.search(r"facebook\.com/([^/?#]+)", str(r.get("link") or ""), re.IGNORECASE)
    if m and m.group(1).lower() not in _SLUG_CHUNG and _gon(m.group(1)):
        ra.add(_gon(m.group(1)))
    return ra


def chu_bai(r: dict) -> set[str]:
    """Chủ bài để IN / gom (script gộp, `lang_nghe_db`): định danh tài khoản (`tai_khoan_bai`),
    không có thì dạng gọn của tên hiển thị `tac_gia`. So hai chủ dùng `cung_chu`, KHÔNG dùng phần
    giao của hàm này."""
    return tai_khoan_bai(r) or {g for g in (_gon(r.get("tac_gia")),) if g}


def cung_chu(a: dict, b: dict) -> bool:
    """Hai dòng có cùng chủ bài không. Ưu tiên định danh TÀI KHOẢN (`tai_khoan_bai`): cả hai có thì
    phải có phần chung; chỉ khi CẢ HAI đều không có định danh tài khoản mới so tên hiển thị.

    Soát 17/10/2026: bản trước so lẫn cả tên hiển thị — hai trang KHÁC nhau cùng tên "HAPAS"
    (hapas.official, hapasglobal) đăng cùng phút cùng chữ bị gộp làm một. Ca đo 16/09 13:49 (lượt
    tìm theo từ khoá ghi tai_khoan rỗng, tac_gia "HAPAS - Chính Hãng Giá Tốt") vẫn khớp nhờ tên
    trang trong link pfbid của chính bài. Một bên chỉ có tên hiển thị, bên kia có tài khoản: KHÔNG
    gộp (không chứng minh được cùng trang)."""
    ta, tb = tai_khoan_bai(a), tai_khoan_bai(b)
    if ta or tb:
        return bool(ta & tb)
    ha, hb = _gon(a.get("tac_gia")), _gon(b.get("tac_gia"))
    return bool(ha) and ha == hb


def phut(dt) -> datetime.datetime | None:
    """Phút đăng (UTC, bỏ giây). Chuỗi ISO cũng nhận. None khi không có giờ đăng."""
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(dt, datetime.datetime):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.replace(second=0, microsecond=0)


#: Số ký tự đầu của nội dung (đã gộp khoảng trắng) dùng để so — ĐÚNG cách đo 17/10/2026 (md5 200
#: ký tự đầu, chỉ chuẩn hoá khoảng trắng: 22/24 nhóm trùng giống hệt). Cắt GIỐNG NHAU ở hai bên
#: và TRƯỚC các bước chuẩn hoá khác, nên cặp nào giống nhau theo cách đo cũng giống nhau theo chữ
#: ký; actor cắt chữ khác nhau sau 200 ký tự (kho cắt 1.000) vẫn khớp.
KY_TU_NOI_DUNG = 200
#: Ký tự vô hình (zero-width, chọn kiểu emoji): actor này có, actor kia không — không phải nội dung.
_VO_HINH = re.compile("[\u200b-\u200d\u2060\ufeff\ufe0e\ufe0f]")


def chu_ky_noi_dung(s) -> str:
    """Chữ ký nội dung để khử trùng: gộp khoảng trắng → cắt `KY_TU_NOI_DUNG` ký tự đầu → Unicode
    NFKC → bỏ ký tự vô hình → chữ thường → gộp khoảng trắng lần nữa. GIỮ chữ số, link, dấu câu,
    emoji: soát 17/10/2026 — bản trước so bằng `loc_rac.chuan` (số → 0, bỏ link/emoji/dấu) nên
    hai bài KHÁC nhau cùng phút chỉ khác giá ("299k" / "399k"), mã giảm giá hay link bị gộp."""
    s = " ".join(str(s or "").split())[:KY_TU_NOI_DUNG]
    s = _VO_HINH.sub("", unicodedata.normalize("NFKC", s)).lower()
    return " ".join(s.split())


def noi_dung_khop(a: dict, b: dict) -> bool:
    """Cùng nội dung: cùng chữ ký (`chu_ky_noi_dung`). Chữ ký không có chữ cái / chữ số nào (ảnh
    không chú thích, chỉ emoji) KHÔNG tính là trùng: hai bài ảnh không chữ cùng phút của một trang
    thường là hai bài khác nhau. Không dùng `ma_noi_dung` của kho (băm `loc_rac`, lỏng)."""
    ca, cb = chu_ky_noi_dung(a.get("noi_dung")), chu_ky_noi_dung(b.get("noi_dung"))
    return ca == cb and any(ch.isalnum() for ch in ca)


def co_chu(r: dict) -> bool:
    """Nội dung có ít nhất một chữ cái / chữ số (sau chuẩn hoá)."""
    return any(ch.isalnum() for ch in chu_ky_noi_dung(r.get("noi_dung")))


def cung_bai(a: dict, b: dict) -> bool:
    """Hai dòng bài Facebook có phải CÙNG một bài không.

    • Có chung một id số (`cac_ma_so`) → cùng bài.
    • Cả hai đều có cột `ma_so_fb` (id actor trả) mà khác nhau → hai bài khác nhau, dù cùng
      phút cùng chữ (trang đăng hai video cùng chú thích một lúc).
    • Còn lại: cùng chủ bài (`cung_chu`) + cùng phút đăng + cùng nội dung (`noi_dung_khop`)."""
    ia, ib = cac_ma_so(a), cac_ma_so(b)
    if ia & ib:
        return True
    sa, sb = la_so(a.get("ma_so_fb")), la_so(b.get("ma_so_fb"))
    if sa and sb and sa != sb:
        return False
    pa, pb = phut(a.get("dang_luc")), phut(b.get("dang_luc"))
    if pa is None or pa != pb:
        return False
    if not cung_chu(a, b):
        return False
    return noi_dung_khop(a, b)
