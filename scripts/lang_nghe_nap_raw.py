"""Nạp raw ĐÃ TRẢ TIỀN vào kho `lang_nghe` — KHÔNG gọi Apify (18/10/2026).

Vì sao: điều tra khoảng thiếu so với Kompa (18/10/2026, `bao_cao_kompa.md`) trả 1,91 USD cho 350
run và giữ ĐỦ item thô trên đĩa (khoảng 336 MB): 2.198 bài liên quan kho chưa có, 13.421 thảo
luận. Script này đưa các bài đó vào kho qua ĐÚNG đường lọc của lượt tìm theo từ khoá `/theodoi`,
không trả tiền lần nữa.

Đọc (mỗi đường dẫn là tệp hoặc thư mục — tìm đệ quy `raw_*.json`, `raw_*.jsonl`), nhận actor theo
trường hoặc tên tệp, chuẩn hoá bằng ĐÚNG hàm của Mark:
  • `.jsonl` scraptik~tiktok-api (TikTok API): dòng `{"loai", "item"}` — searchPosts (tìm kiếm),
    challengePosts (feed hashtag), userPosts (hồ sơ, bỏ video ghim như `tiktok_api.ho_so`), post;
    profile / searchHashtags không có bài. `tiktok_api.video` → `apify_tool._chuan_clockworks` →
    `_chuan_tiktok`.
  • `.json` có `actor` + `items`: mina_safwat (Facebook đường 2, `_chuan_facebook_mina`, cụm =
    `input.query`), scrapeforge (Facebook, `_chuan_facebook`), apify~instagram-hashtag-scraper
    (`_chuan_instagram`), futurizerush Threads (`_chuan_threads`), scrapersdelight Threads
    (`_chuan_threads_2`), thedoor trang Facebook (`theo_doi_api.doc_thedoor`), scraperlink Google
    (`nguon_web.thu_thap` — CHỈ đoạn trích Google: không tải trang, không đọc dự phòng). Item chiếu
    đúng các trường `apify_tool._TRUONG_ACTOR` như việc nền đọc dataset; item mẫu (`demo`) bỏ.
  • `raw_yt.json` (YouTube Data API: `tim` = các trang search theo câu, `video` = videos.list):
    `apify_tool._youtube_tim` với lớp gọi API thay bằng đọc tệp (không tốn quota).
  • Actor khác (scraper_one, danek, powerai, epctex, igview, actor bình luận…): Mark không có bộ
    chuẩn hoá — bỏ qua, in tên tệp (không tự viết bộ đọc mới).

Pipeline = lượt tìm theo từ khoá (`theo_doi._tach_va_giu`): khung ngày `--tu` (mặc định 17/09/2026)
→ nay; bỏ trùng trong lô (giữ bản nhiều bình luận nhất; Threads hai actor cùng mã bài giữ bản
futurizerush như `_bo_trung_duong_2`); bài ĐÃ CÓ (kể cả bản trùng Facebook theo `ma_so_fb`) chỉ
NÂNG số (`lang_nghe_db.nang_so_lieu`: số cũ không hạ số mới, ảnh chụp ghi đúng ngày đọc raw); bài
MỚI: sổ đã loại → từ loại trừ → cổng thị trường VN → spam → cổng brand đường hashtag (bài CHỈ từ
feed challengePosts / Instagram hashtag phải gọi tên brand, `theo_doi.nhac_brand`) → seeding
affiliate (lịch sử = kho + sổ + CẢ lô raw) → AI phân xử → ghi `kieu_quet = tu_khoa`. Raw theo NGUỒN (TikTok userPosts, trang thedoor)
của tài khoản ĐANG THEO DÕI — và bài tìm thấy mà chủ bài / link khớp ĐÚNG MỘT nguồn kênh nhà
(`tach_kenh_nha`, soát 18/10/2026) — CHỈ đi đường nguồn theo dõi (`theo_doi.chon_bai`, kieu
`theo_doi`, gắn `nguon_id`; ghi TRƯỚC đường từ khoá) như lượt quét nguồn thật — kênh nhà giữ mọi
bài, dashboard tách đúng bài brand. Sắc thái /
chủ đề AI trả cùng lượt; phần thiếu để gán nhãn nền làm. Không ghi đề xuất nguồn (cả tháng dữ liệu sẽ
đổ hàng trăm đề xuất vào hàng chờ duyệt).

Lượt: một `luot_quet` kiểu `tu_khoa` (không tính vào trần tháng), chi phí 0, ghi chú phễu từng nền
tảng như lượt thật.

An toàn:
  • Mặc định CHẠY THỬ: không gọi AI, không ghi gì (kể cả sổ) — kết nối kho đặt
    `default_transaction_read_only`; in phễu ước tính (bài sẽ nạp TRƯỚC AI, thảo luận thêm, bài
    seeding bị loại, bài đường hashtag không nhắc brand bị loại, bài đã có sẽ nâng số) và số lô AI.
  • `--ap-dung --sao-luu <tệp>`: AI tuần tự từng phần ≤ `apify_tool._AI_LO` bài, một lô model một
    lúc, nghỉ `gan_nhan_nen.NGHI_GIUA_LO` giây giữa hai phần (quota model dùng chung với bot) —
    hỏng giữa chừng thì chạy lại: bài đã ghi thành "đã có", bài đã loại thành "đã loại trước"
    (lý do luật không tốn AI như seeding thì luật xét lại, không gọi AI — `theo_doi._con_chan`).
    Soát 18/10/2026 (M3): AI không phán (bỏ qua, lỗi, hết `HAN_LO` giây, đạt trần
    `--toi-da-goi-ai`) thì phần đó KHÔNG ghi theo luật, không vào sổ (`can_ai`) — script báo số
    bài chưa phán, chạy lại là xét tiếp; lô quá hạn không chạy nền song song với lô sau (`GacAI`
    chờ model trả lời xong rồi mới gửi lô kế — tối đa `CHO_LO_TOI_DA` giây, quá thì phần sau không
    gửi AI, không ghi). Lượt đóng "xong" chỉ khi chạy hết và AI phán đủ; còn bài chưa phán hoặc
    Ctrl-C thì "mot_phan", lỗi thì "loi" (soát 18/10/2026).
    Tệp hoàn tác: lượt, khoá bài thêm (= bài có `luot_dau` = lượt nạp), khoá sổ thêm — dòng "so"
    ghi NGAY sau mỗi phần, mang tên sổ (dự án, hoặc `<mã>:web` của Báo & Web — `SoThem`).
  • `--hoan-tac <tệp>`: xoá đúng các bài lượt nạp đã thêm MÀ CHƯA BỊ ĐỤNG (lượt sau chưa cập nhật,
    chưa cào bình luận), gỡ khoá sổ đã thêm (sổ dự án — đường từ khoá + đường nguồn — và sổ web).
    Giao dịch xoá giữ khoá advisory mở lượt (`lang_nghe_db.so_khoa_luot`) và dừng khi dự án có
    lượt khác đang chạy. Số đã nâng của bài cũ và ảnh chụp ngày đọc giữ nguyên (số đọc thật). Cần
    GRANT DELETE tạm như `lang_nghe_gop_bai_fb.py` (bản in nhắc REVOKE khi xong).

VPS (user mark, venv Hermes, cwd /opt/mark/app — model đi đúng đường lease như /theodoi). Chép raw
lên VPS trước, ví dụ `/opt/mark/raw-kompa-1810/` (quyền 700, chủ mark), GIỮ giờ ghi tệp (`rsync -a`
hoặc `scp -rp`): "lúc đọc raw" = trường thời gian của item khi actor có (`scrapedAt`, `scraped_at`,
`scrape_date`, `collectedAt` — `_luc_doc_item`), không thì giờ ghi tệp — ngày của ảnh chụp
`chi_so_ngay` (cả bài đã có lẫn bài MỚI — `_ngay_so`, soát 18/10/2026) và mốc ngày tương đối của
trang Google ("5 ngày trước"). Tệp lấy giờ ghi tệp mà giờ đó là hôm nay thì script cảnh báo.

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_nap_raw.py hapas /opt/mark/raw-kompa-1810      # chạy thử
    sudo -u mark $PY scripts/lang_nghe_nap_raw.py hapas /opt/mark/raw-kompa-1810 --ap-dung \\
        --sao-luu /opt/mark/nap-raw-$(date +%F).jsonl
    sudo -u postgres psql -d lang_nghe -c 'GRANT DELETE ON bai TO mark'                 # chỉ khi hoàn tác
    sudo -u mark $PY scripts/lang_nghe_nap_raw.py hapas --hoan-tac /opt/mark/nap-raw-<ngày>.jsonl
    sudo -u postgres psql -d lang_nghe -c 'REVOKE DELETE ON bai FROM mark'

Chạy TRƯỚC `scripts/lang_nghe_loc_seeding.py`: bài seeding của raw vào sổ seeding, script dọn thấy
đủ nhịp đăng — đo trên ảnh chụp kho 17/10, dọn trước nạp bắt 11 tài khoản (332 bài), dọn sau nạp bắt
16 (377 bài). Nên chạy ngoài giờ lượt quét lịch (không bắt buộc: ghi là upsert, nhưng hai bên cùng
gọi model).
"""
from __future__ import annotations

import argparse
import contextlib
import contextvars
import datetime
import json
import math
import os
import pathlib
import re
import sys
import threading
import time

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

import apify_tool as A
import lang_nghe_db as K
import nguon_web as W
import theo_doi as T
import theo_doi_api as TDA
import tiktok_api as TT

_VN = datetime.timezone(datetime.timedelta(hours=7))
TU_MAC_DINH = "2026-09-17"
LO = A._AI_LO                      # bài mỗi phần gửi AI (một lô model)
NGHI_GIUA_LO = 5                   # = gan_nhan_nen.NGHI_GIUA_LO
HAN_LO = 180.0                     # = gan_nhan_nen.HAN_LO — giây chờ model mỗi phần (soát M3)
#: Giây chờ THÊM một lô đã quá `HAN_LO` (soát 18/10/2026, LOW — `GacAI.cho_lo_truoc`): lời gọi model
#: không huỷ được, chờ không giới hạn thì một lời gọi treo làm treo cả lần chạy (lượt `luot_quet`
#: mở mãi ở "dang_chay"). Quá mức này: phần sau không gửi AI, không ghi — chạy lại là nạp tiếp.
CHO_LO_TOI_DA = 600.0
TOI_DA_GOI_AI = 50                 # trần lượt gọi model cả lần chạy (`--toi-da-goi-ai`)
NHAN = "nạp raw Kompa"
_MXH = ("youtube", "tiktok", "facebook", "instagram", "threads")
#: Actor → (nền tảng, bộ chuẩn hoá). thedoor / Google / YouTube có đường riêng bên dưới.
_DOC = {
    A._ACTORS["facebook_duong2"]: ("facebook", "mina"),
    A._ACTORS["facebook"]: ("facebook", "scrapeforge"),
    A._ACTORS["instagram"]: ("instagram", "ig"),
    A._ACTORS["threads"]: ("threads", "th1"),
    A._ACTORS["threads_2"]: ("threads", "th2"),
    TDA.FB_TRANG: ("facebook", "thedoor"),
    W.ACTOR_TIM: ("web", "web"),
}
SQL_QUYEN = "/* nap:quyen */ SELECT has_table_privilege(current_user, 'bai', 'DELETE') AS xoa"
SQL_XOA = ("/* nap:xoa */ DELETE FROM bai b WHERE b.du_an = %s AND b.khoa = ANY(%s) AND "
           "b.luot_dau = %s AND b.luot_cuoi = %s AND b.bl_lay_luc IS NULL AND NOT EXISTS ("
           "SELECT 1 FROM binh_luan x WHERE x.du_an = b.du_an AND x.khoa_bai = b.khoa) "
           "RETURNING b.khoa")
# Hoàn tác (soát 18/10/2026, LOW): cùng khoá advisory MỞ LƯỢT với `lang_nghe_db.mo_luot` (như script
# gộp bài trùng / dọn seeding) — lượt mới chờ giao dịch xoá commit; lượt đang chạy (trừ chính lượt
# nạp) thì dừng, kẻo xoá bài lượt đó vừa gặp lại.
SQL_HAN_KHOA = "/* nap:han_khoa */ SET LOCAL lock_timeout = '30s'"
SQL_KHOA_LUOT = "/* nap:khoa_luot */ " + K._SQL_KHOA_LUOT
SQL_LUOT_CHAY = ("/* nap:luot_chay */ SELECT id FROM luot_quet WHERE du_an = %s AND id <> %s AND "
                 "trang_thai = 'dang_chay' AND bat_dau > now() - make_interval(hours => %s) "
                 "ORDER BY id")


# ───────────────────────────── đọc raw ─────────────────────────────
def _luc_doc(f: pathlib.Path) -> datetime.datetime:
    """Lúc đọc raw = lúc ghi tệp (script đo ghi ngay sau khi run xong; tệp không có trường giờ)."""
    return datetime.datetime.fromtimestamp(f.stat().st_mtime, _VN)


#: Trường "lúc actor đọc" có trong item thô (soi raw Kompa 18/10/2026): mina `scrape_date`
#: ("2026-10-17 18:20:22.04", giờ máy actor = UTC), scrapersdelight / powerai `scrapedAt`,
#: futurizerush `scraped_at` / `collectedAt` (ISO có múi giờ).
_TRUONG_LUC_DOC = ("scrapedAt", "scraped_at", "scrape_date", "collectedAt")


def _luc_doc_item(items: list) -> datetime.datetime | None:
    """Lúc đọc theo TRƯỜNG THỜI GIAN của item (sớm nhất trong tệp — một run đọc trong vài phút);
    None khi không item nào có. Giờ không múi giờ coi là UTC (máy Apify)."""
    ra = None
    for it in items or []:
        if not isinstance(it, dict):
            continue
        for k in _TRUONG_LUC_DOC:
            v = it.get(k)
            if not isinstance(v, str) or not v.strip():
                continue
            try:
                t = datetime.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
            except ValueError:
                continue
            t = t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
            ra = t if ra is None or t < ra else ra
            break
    return ra.astimezone(_VN) if ra else None


def cac_tep(duong: list[str]) -> list[pathlib.Path]:
    ra: list[pathlib.Path] = []
    for x in duong:
        p = pathlib.Path(x)
        if p.is_dir():
            ra += sorted(q for q in p.rglob("raw_*.json*") if q.suffix in (".json", ".jsonl"))
        elif p.is_file():
            ra.append(p)
    return sorted(dict.fromkeys(ra))


def _chieu(actor: str, items: list) -> list:
    """Như `apify_tool._lay_items(fields=…)` của việc nền: chỉ giữ trường bộ chuẩn hoá đọc (+ demo),
    bỏ item mẫu và item rỗng — `__goc` (khoá bài dự phòng) giống hệt lượt thật."""
    truong = A._TRUONG_ACTOR.get(actor)
    ra = []
    for it in items or []:
        if not isinstance(it, dict) or A._la_demo(it):
            continue
        if truong:
            it = {k: it[k] for k in (*truong, A._TRUONG_DEMO) if k in it}
        if not A._rong(it):
            ra.append(it)
    return ra


def _tiktok(f: pathlib.Path) -> tuple[list, list]:
    """Tệp JSONL scraptik → (bài đường từ khoá [(d, dt)], bài HỒ SƠ [(d, dt)])."""
    tim, ho_so = [], []
    for dong in f.read_text(encoding="utf-8").splitlines():
        if not dong.strip():
            continue
        x = json.loads(dong)
        it = x.get("item") if isinstance(x.get("item"), dict) else {}
        loai = x.get("loai")
        if loai == "searchPosts":
            aw = [(s or {}).get("aweme_info") for s in it.get("search_item_list") or []]
        elif loai in ("challengePosts", "userPosts"):
            aw = list(it.get("aweme_list") or [])
        elif loai == "post":
            aw = [it.get("aweme_detail")]
        else:
            continue
        aw = [a for a in aw if isinstance(a, dict) and a.get("aweme_id")
              and not (loai == "userPosts" and a.get("is_top"))]
        rows = A._chuan_tiktok(A._chuan_clockworks([TT.video(a) for a in aw]))
        if loai == "userPosts":
            for d, _ in rows:
                d["_ho_so"] = True
        elif loai == "challengePosts":
            # Feed hashtag: đường hashtag như `theo_doi._them_feed_tag` — qua cổng brand.
            for d, _ in rows:
                d["_tag_feed"] = f"#{TT.chuan_tag(x.get('tag') or '')}"
        (ho_so if loai == "userPosts" else tim).extend(rows)
    return tim, ho_so


@contextlib.contextmanager
def _youtube_tu_tep(raw: dict):
    """`apify_tool._youtube_get` đọc từ `raw_yt.json` thay vì gọi API: search trả lần lượt các trang
    đã lưu của câu đang tìm, videos trả video đã lưu, channels rỗng (không lưu)."""
    trang: list = []
    video = {str(v.get("id")): v for v in raw.get("video") or [] if isinstance(v, dict)}
    goc = A._youtube_get

    def gia(resource, params):
        if resource == "search":
            return trang.pop(0) if trang else {"items": []}
        if resource == "videos":
            return {"items": [video[i] for i in str(params.get("id") or "").split(",")
                              if i in video]}
        return {"items": []}
    A._youtube_get = gia
    try:
        yield trang
    finally:
        A._youtube_get = goc


def _youtube(raw: dict, tu: datetime.datetime, den: datetime.datetime) -> list:
    ra = []
    with _youtube_tu_tep(raw) as trang:
        for q, cac in (raw.get("tim") or {}).items():
            trang[:] = [x for x in (cac if isinstance(cac, list) else [cac]) if isinstance(x, dict)]
            ra += A._youtube_tim([q], 10 ** 6, "VN", tu, den)[0]
    return ra


def doc_raw(duong: list[str], tu: datetime.datetime, den: datetime.datetime) -> dict:
    """Mọi tệp raw → {"tim": [(d, dt)] đường từ khoá, "ho_so": [(d, dt)] TikTok userPosts,
    "trang_fb": [(items thedoor, giờ đọc)], "web": [(items, giờ đọc)], "tep": [(tên, loại, số
    bài)], "bo_qua": [(tên, lý do)], "theo_gio_tep": {tên tệp lấy giờ đọc theo giờ ghi tệp}}. Mỗi
    d có `platform` và `_luc_doc` (giờ đọc raw: trường thời gian của item khi có —
    `_luc_doc_item`, không thì giờ ghi tệp; soát 18/10/2026 — ảnh chụp `chi_so_ngay` của bài nạp
    ghi đúng ngày đọc, không theo now())."""
    ra = {"tim": [], "ho_so": [], "trang_fb": [], "web": [], "tep": [], "bo_qua": [],
          "theo_gio_tep": set()}

    def luc_cua(f, items=None):
        x = _luc_doc_item(items)
        if x is None:
            ra["theo_gio_tep"].add(f.name)
        return x or _luc_doc(f)

    def them(f, loai, rows, ds, luc=None):
        luc = luc or luc_cua(f)
        for d, _ in rows:
            d["_luc_doc"] = luc
        ds.extend(rows)
        ra["tep"].append((f.name, loai, len(rows)))
    for f in cac_tep(duong):
        try:
            if f.suffix == ".jsonl":
                tim, ho_so = _tiktok(f)
                for d, _ in tim + ho_so:
                    d["platform"] = "tiktok"
                them(f, "scraptik TikTok", tim, ra["tim"])
                if ho_so:
                    them(f, "scraptik TikTok hồ sơ", ho_so, ra["ho_so"])
                continue
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            ra["bo_qua"].append((f.name, f"đọc lỗi {type(e).__name__}"))
            continue
        if isinstance(r, dict) and "tim" in r and "video" in r:
            rows = _youtube(r, tu, den)
            for d, _ in rows:
                d["platform"] = "youtube"
            them(f, "YouTube Data API", rows, ra["tim"])
            continue
        actor = str((r or {}).get("actor") or "").replace("/", "~") if isinstance(r, dict) else ""
        p, kieu = _DOC.get(actor, (None, None))
        if not kieu:
            ra["bo_qua"].append((f.name, f"actor {actor or '?'} không có bộ chuẩn hoá của Mark"))
            continue
        items = _chieu(actor, r.get("items") or [])
        luc = luc_cua(f, r.get("items"))       # trường giờ đọc nằm ở item THÔ (trước khi chiếu)
        if kieu == "thedoor":
            ra["trang_fb"].append((items, luc, f.name))
            ra["tep"].append((f.name, "thedoor trang Facebook", len(items)))
            continue
        if kieu == "web":
            ra["web"].append((items, luc, f.name))
            ra["tep"].append((f.name, "Google (scraperlink)", len(items)))
            continue
        cum = str((r.get("input") or {}).get("query") or "")
        if kieu == "mina":
            rows = A._chuan_facebook_mina(items, cum)
        else:
            rows = {"scrapeforge": A._chuan_facebook, "ig": A._chuan_instagram,
                    "th1": A._chuan_threads, "th2": A._chuan_threads_2}[kieu](items)
        tim_tu = bool((r.get("input") or {}).get("keywordSearch"))
        tag_vao = [str(t) for t in (r.get("input") or {}).get("hashtags") or [] if str(t).strip()]
        for d, _ in rows:
            d["platform"] = p
            if kieu == "th2":
                d["_th2"] = True
            if kieu == "ig":
                # Cổng brand (18/10/2026): actor hashtag Instagram là đường hashtag, TRỪ run
                # `keywordSearch` (trang tìm theo từ khoá) — theo `inputUrl` của bài, thiếu thì
                # theo input của run (`_tag_vao`: `chay` gắn nhãn `theo_doi.tag_feed_chung` khi mọi
                # hashtag của run là tag brand / chiến dịch — soát 18/10/2026 M1).
                t = TDA.tag_ig(d)
                d["_tag_feed"] = ("" if tim_tu else "#") if t is None else t
                if t is None and not tim_tu and tag_vao:
                    d["_tag_vao"] = tag_vao
        them(f, actor, rows, ra["tim"], luc)
    return ra


# ───────────────────────────── lọc trước pipeline (thuần) ─────────────────────────────
def _khoa(d: dict) -> str:
    """Khoá bài như `theo_doi._tach_va_giu` (id của `__goc` khi link không có id)."""
    goc = d.get("__goc") if isinstance(d.get("__goc"), dict) else {}
    return T._khoa_bai(d["platform"], d.get("link") or "", {"id": goc.get("id") or d.get("_goc_id")})


def _so(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def loc_khung(rows: list, tu: datetime.datetime, den: datetime.datetime) -> tuple[list, dict]:
    """Giữ bài có link, đăng trong [tu, den + 1 giờ] (như lượt tìm); bỏ trùng trong lô — cùng khoá
    (Facebook thêm cùng `ma_so_fb`, Threads cùng mã bài). Bản giữ: bản đọc từ HỒ SƠ (đi đường
    nguồn nếu tài khoản đang được theo dõi), rồi bản futurizerush với Threads (có follower + lượt
    xem, như `_bo_trung_duong_2`), rồi bản nhiều bình luận nhất. -> (bài, {nền tảng: {"ve",
    "pham_vi", "ngoai_pham_vi", "trung"}}). Bản giữ mang nhãn đường hashtag gộp (`gop_duong`)."""
    import khu_trung_fb as KT
    dem: dict[str, dict] = {}
    chon: dict[tuple, tuple] = {}
    bi_danh: dict[tuple, tuple] = {}
    for d, dt in rows:
        p = d["platform"]
        x = dem.setdefault(p, {"ve": 0, "pham_vi": 0, "ngoai_pham_vi": 0, "trung": 0})
        x["ve"] += 1
        if not dt or not d.get("link") or not tu <= dt <= den + datetime.timedelta(hours=1):
            x["ngoai_pham_vi"] += 1
            continue
        x["pham_vi"] += 1
        k = (p, _khoa(d))
        phu = []
        if p == "facebook" and KT.ma_so_fb(d):
            phu.append((p, "so", KT.ma_so_fb(d)))
        if p == "threads" and A.ma_bai_threads(d.get("link") or ""):
            phu.append((p, "th", A.ma_bai_threads(d["link"])))
        k = next((bi_danh[b] for b in phu if b in bi_danh), k)
        cu = chon.get(k)
        if cu is not None:
            x["trung"] += 1

            def hon(b):
                return (bool(b.get("_ho_so")), not b.get("_th2"), _so(b.get("comments")))
            if hon(d) > hon(cu[0]):
                chon[k] = (d, dt)
            # Bài chỉ-hashtag (cổng brand) khi MỌI bản đều từ đường hashtag — như `tach_da_biet`.
            TDA.gop_duong(chon[k][0], cu[0] if chon[k][0] is d else d)
        else:
            chon[k] = (d, dt)
        for b in phu:
            bi_danh.setdefault(b, k)
    return list(chon.values()), dem


def tach_nguon(ho_so: list, nguon: list[dict]) -> tuple[dict[int, list], list]:
    """Bài HỒ SƠ TikTok → ({id nguồn đang theo dõi: bài}, bài của tài khoản không theo dõi — đi
    đường từ khoá như bài tìm thấy)."""
    theo = {T._chuan_dinh_danh("tiktok", n["dinh_danh"]): n for n in nguon
            if n.get("nen_tang") == "tiktok"}
    ra: dict[int, list] = {}
    con = []
    for d, dt in ho_so:
        n = theo.get(T._chuan_dinh_danh("tiktok", d.get("username") or ""))
        if n is None:
            con.append((d, dt))
        else:
            d["_goc_id"] = ((d.get("__goc") or {}).get("id") if isinstance(d.get("__goc"), dict)
                            else None)
            ra.setdefault(int(n["id"]), []).append((d, dt))
    return ra, con


# ───────────────────────────── chủ bài ↔ nguồn (soát 18/10/2026) ─────────────────────────────
# Vì sao: lượt nạp 14 (18/10/2026 17:30–17:41, raw `hapasglobal` của Kompa) ghép trang thedoor qua
# `theo_doi.ghep_nguon` rồi gọi LẠI `_dong_tu_tai_khoan` cho đường từ khoá — mỗi lần một dict mới,
# nên phép loại `id(d) not in dung` luôn đúng: bài fanpage nhà đi CẢ HAI đường, đường từ khoá ghi
# trước (`kieu_quet = tu_khoa`, `nguon_id` NULL) → bài nhà thành "External channel", lọt sắc thái /
# chủ đề (phễu "đường nguồn: 103 bài đã có, 19 mới"). Nay ghép theo DẤU ổn định của chủ bài, mỗi
# bài một đường; luật dùng chung với `scripts/lang_nghe_sua_nguon_nha.py` (sửa dữ liệu đã ghi).
#: Id trang Facebook trong link: `/<id trang>/posts/…` (thedoor), `profile.php?id=…`,
#: `permalink.php?story_fbid=…&id=<id trang>` — như `doc_thedoor` ghép trang theo id trong URL.
_RE_ID_TRANG = re.compile(r"facebook\.com/(\d{5,25})(?=[/?#]|$)|[?&]id=(\d{5,25})", re.IGNORECASE)


def dau_chu_bai(p: str, tai_khoan: str = "", *links: str) -> set[str]:
    """Dấu nhận diện chủ bài theo luật `/theodoi`: tài khoản = định danh nguồn
    (`theo_doi._chuan_dinh_danh`; Facebook: tên trang như `theo_doi._kenh_nha`), tên trang trong
    link (`theo_doi_api._ten_trang`), id trang trong link (`_RE_ID_TRANG`); TikTok / Threads thêm
    @tài khoản trong link. Không dùng tên hiển thị (hai trang khác nhau cùng tên "HAPAS")."""
    p, tk = str(p or ""), str(tai_khoan or "").strip()
    ra: set[str] = set()
    if p != "facebook":
        if T._chuan_dinh_danh(p, tk):
            ra.add(T._chuan_dinh_danh(p, tk))
        for u in links if p in ("tiktok", "threads") else ():
            m = re.search(r"/@([\w.\-]+)", str(u or ""))
            if m:
                ra.add(m.group(1).lower())
        return ra
    if "/" in tk:                                  # định danh nguồn là URL trang
        links, tk = (tk, *links), ""
    tk = tk.lstrip("@").lower()
    if tk:
        ra.add(f"id:{tk}" if tk.isdigit() else f"ten:{tk}")
    for u in links:
        ten = TDA._ten_trang(u)
        if ten:
            ra.add(f"ten:{ten.lower()}")
        ra.update(f"id:{a or b}" for a, b in _RE_ID_TRANG.findall(str(u or "")))
    return ra


def bang_dau(nguon: list[dict]) -> dict[int, tuple[str, set[str]]]:
    """{id nguồn: (nền tảng, dấu của định danh — tài khoản hay URL)}."""
    return {int(n["id"]): (str(n.get("nen_tang") or ""),
                           dau_chu_bai(str(n.get("nen_tang") or ""), str(n.get("dinh_danh") or ""),
                                       str(n.get("dinh_danh") or "")))
            for n in nguon}


def nguon_khop(p: str, dau: set[str], bang: dict[int, tuple[str, set[str]]]) -> list[int]:
    """Các nguồn cùng nền tảng có chung dấu với chủ bài — chỉ gắn khi ĐÚNG MỘT."""
    return [nid for nid, (q, d) in bang.items() if q == p and dau & d]


def doc_trang_fb(items: list, bang: dict, nguon: dict[int, dict]) -> dict[int | None, list]:
    """Item thedoor → {id nguồn: [(dòng, ngày)]}; khoá None = trang không khớp ĐÚNG MỘT nguồn
    Facebook (đi đường từ khoá). Ghép theo trang của TỪNG item (`page.url`, `page.id`, id trang
    trong link bài), không theo dự phòng "run một trang thì về trang đó" của `doc_thedoor` /
    `ghep_nguon` (raw nạp lại có thể là trang lạ khi dự án chỉ có một nguồn Facebook)."""
    nhom: dict[int | None, list] = {}
    for it in items:
        if not TDA.la_thedoor(it):
            continue
        pg, po = it["page"], it["post"]
        dau = dau_chu_bai("facebook", "", str(pg.get("url") or ""), str(po.get("url") or ""))
        if str(pg.get("id") or "").isdigit():
            dau.add(f"id:{pg['id']}")
        ids = nguon_khop("facebook", dau, bang)
        nhom.setdefault(ids[0] if len(ids) == 1 else None, []).append(it)
    ra: dict[int | None, list] = {}
    for nid, its in nhom.items():
        urls = [str(nguon[nid]["dinh_danh"])] if nid is not None else []
        for tk in TDA.doc_thedoor(its, urls).values():
            for d, dt in T._dong_tu_tai_khoan("facebook", tk):
                d["_ho_so"] = True                # bản đọc TRANG: thắng bản tìm khi bỏ trùng
                ra.setdefault(nid, []).append((d, dt))
    return ra


def tach_kenh_nha(tim: list, nguon: list[dict]) -> tuple[list, dict[int, list]]:
    """Bài đường từ khoá mà chủ bài / link khớp ĐÚNG MỘT nguồn kênh nhà → đường nguồn của nguồn đó
    (như lượt `/theodoi`: gắn `nguon_id`, `kieu_quet = theo_doi`, kênh nhà giữ mọi bài). Đường từ
    khoá Facebook không gắn được nguồn (`theo_doi._dinh_danh_tai_khoan` → None): bài fanpage nhà
    mina / scrapeforge tìm thấy sẽ thành "External channel". -> (bài còn lại, {id nguồn: bài})."""
    bang = bang_dau([n for n in nguon if n.get("loai") == "kenh_nha"])
    con, sang = [], {}
    for d, dt in tim:
        p = str(d.get("platform") or "")
        ids = nguon_khop(p, dau_chu_bai(p, str(d.get("username") or ""), str(d.get("link") or "")),
                         bang) if bang else []
        if len(ids) != 1:
            con.append((d, dt))
            continue
        goc = d.get("__goc") if isinstance(d.get("__goc"), dict) else {}
        d["_goc_id"] = d.get("_goc_id") or goc.get("id")      # khoá như `chon_bai` (`_goc_id`)
        sang.setdefault(ids[0], []).append((d, dt))
    return con, sang


def khoa_on_dinh(d: dict) -> set[str]:
    """Khoá bài + mọi id số Facebook của dòng (`khu_trung_fb.cac_ma_so`): hai bản đọc của cùng
    bài (link pfbid ↔ id số) chung ít nhất một khoá. Không dùng `id()` của dict."""
    import khu_trung_fb as KT
    k = _khoa(d)
    if d.get("platform") != "facebook":
        return {k}
    return {k} | {f"facebook:{x}" for x in KT.cac_ma_so(
        {"khoa": k, "link": d.get("link"), "ma_so_fb": KT.ma_so_fb(d)})}


# ───────────────────────────── chạy thử: tạm thay phần ghi + AI ─────────────────────────────
@contextlib.contextmanager
def che_do_chay_thu(ghi: dict):
    """Thay MỌI chỗ ghi + AI của pipeline bằng bản đếm (`ghi`), và đặt kết nối kho chỉ đọc
    (`default_transaction_read_only` — chỗ ghi nào lọt khỏi danh sách này thì Postgres từ chối,
    không ghi im lặng)."""
    ghi.update(ai=[], ai_khong_khop=0, bai=[], nang=[], loai=0, loai_ds=[], seeding=[])

    def ai(rows, *a, **k):
        ghi["ai"].append(len(rows))
        # Bài không nhắc từ khoá mà vẫn tới AI: chạy thật AI ĐƯỢC giữ (ngoài số "sẽ nạp").
        ghi["ai_khong_khop"] += sum(1 for d, _ in rows if not d.get("_khop"))
        return {}, {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "bỏ qua: chạy thử"}

    def ghi_bai(ma, luot, kieu, rows):
        ghi["bai"].extend(dict(r, _kieu=kieu) for r in rows)
        return len(rows), 0

    def nang(ma, luot, rows, ngay=None):
        ghi["nang"].extend(rows)
        return len(rows)

    def loai(ma, dau, moi, tu):
        ghi["loai"] += len(moi)
        ghi["loai_ds"].extend(moi)              # (khoá, lý do, giờ đăng) — phễu chạy thử

    def seeding(ma, moi, bay_gio=None, **k):
        if not k.get("chi_cap_nhat"):
            ghi["seeding"].extend(moi)
    thay = [(A, "_phan_xu_ai", ai), (K, "ghi_bai", ghi_bai), (K, "nang_so_lieu", nang),
            (K, "cap_nhat_so_lieu", nang), (K, "ghi_de_xuat", lambda ma, cac: 0),
            (TDA, "ghi_loai", loai), (TDA, "ghi_seeding", seeding),
            (TDA, "cap_nhat_seeding", lambda ma, moi: None),
            (TDA, "bo_khoi_so", lambda ma, khoa: 0),      # gỡ khoá bài vừa giữ khỏi sổ
            (T, "ghi_da_boc", lambda *a, **k: None)]
    cu = [(m, ten, getattr(m, ten)) for m, ten, _ in thay]
    pg = os.environ.get("PGOPTIONS")
    os.environ["PGOPTIONS"] = f"{pg or ''} -c default_transaction_read_only=on".strip()
    for m, ten, gt in thay:
        setattr(m, ten, gt)
    try:
        yield ghi
    finally:
        for m, ten, gt in cu:
            setattr(m, ten, gt)
        if pg is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = pg


# ───────────────────────────── gác AI (soát 18/10/2026, M3) ─────────────────────────────
class GacAI:
    """Gác MỌI lượt gọi model của lần chạy áp dụng:
      • trần tổng số lượt gọi (`toi_da`, mỗi lô ≤ `LO` bài một lượt): quá trần thì phần sau trả
        "bỏ qua: đạt trần" — với `can_ai` phần đó không ghi, chạy lại script là xét tiếp;
      • TUẦN TỰ thật: `apify_tool._hoi_model` hết giờ thì luồng model vẫn chạy nền (không thể huỷ
        lời gọi đang chờ). Lô sau phải chờ luồng đó xong, kẻo hai lô cùng gọi model — quota dùng
        chung với bot (`gan_nhan_nen` cũng một lô một lúc).
      • chờ lô quá hạn CÓ GIỚI HẠN (soát 18/10/2026, LOW): tối đa `cho_toi_da` giây
        (`CHO_LO_TOI_DA`). Model vẫn chưa trả lời thì coi là TREO: mọi phần sau trả "bỏ qua: model
        treo" ngay (với `can_ai` không ghi, chạy lại là xét tiếp) cho tới khi luồng treo xong —
        không gửi song song, cũng không treo cả lần chạy vì một lời gọi không bao giờ về.
    `cai()` thay `A._hoi_model` / `A._phan_xu_ai` trong lúc chạy, xong thì trả lại."""

    def __init__(self, toi_da: int, in_ra=print, cho_toi_da: float | None = None):
        self.toi_da = max(0, int(toi_da))
        self.cho_toi_da = max(0.0, float(CHO_LO_TOI_DA if cho_toi_da is None else cho_toi_da))
        self.da_goi = 0
        self.vuot = 0                       # bài không được gửi vì đạt trần
        self.cho = 0                        # số lần phải chờ lô quá hạn
        self.treo = False                   # lô trước chờ quá `cho_toi_da` vẫn chưa xong
        self.bo_treo = 0                    # bài không được gửi vì model treo
        self.in_ra = in_ra
        self._dang: list[threading.Thread] = []
        self._hoi_goc = A._hoi_model
        self._xu_goc = A._phan_xu_ai

    def cho_lo_truoc(self) -> bool:
        """Chờ luồng model còn chạy của lô trước (≤ `cho_toi_da` giây; đang TREO thì chỉ xem lại,
        không chờ thêm). -> True khi không còn luồng nào — gửi được lô kế."""
        han = time.monotonic() + (0.0 if self.treo else self.cho_toi_da)
        for t in list(self._dang):
            if t.is_alive():
                if not self.treo:
                    self.cho += 1
                    self.in_ra("    lô AI trước quá hạn — chờ model trả lời xong rồi mới gửi lô sau"
                               f" (tối đa {self.cho_toi_da:g} giây)")
                t.join(max(0.0, han - time.monotonic()))
        self._dang = [t for t in self._dang if t.is_alive()]
        if self._dang and not self.treo:
            self.in_ra(f"    model vẫn chưa trả lời sau {self.cho_toi_da:g} giây — TREO: phần sau "
                       "không gửi AI (không ghi), chạy lại script để nạp tiếp")
        self.treo = bool(self._dang)
        return not self.treo

    def hoi(self, nhac: str, ngan_sach: float) -> str:
        """Thay `A._hoi_model`: gọi bản gốc trong luồng RIÊNG được theo dõi (chờ không giới hạn ở
        trong, `ngan_sach` giây ở ngoài); hết giờ thì ném `_FutTimeout` như bản gốc nhưng nhớ luồng.
        Lô trước còn treo thì ném `_FutTimeout` ngay, không gọi model."""
        if not self.cho_lo_truoc():
            raise A._FutTimeout()
        kq: dict = {}
        ctx = contextvars.copy_context()

        def chay():
            try:
                kq["ra"] = ctx.run(self._hoi_goc, nhac, 10.0 ** 6)
            except BaseException as e:  # noqa: BLE001 — chuyển lỗi về luồng gọi
                kq["loi"] = e
        t = threading.Thread(target=chay, name="nap-raw-model", daemon=True)
        self._dang.append(t)
        t.start()
        t.join(max(0.0, float(ngan_sach)))
        if t.is_alive():
            raise A._FutTimeout()
        self._dang.remove(t)
        if "loi" in kq:
            raise kq["loi"]
        return kq.get("ra") or ""

    def phan_xu(self, rows, *a, **k):
        """Thay `A._phan_xu_ai`: đếm lượt gọi (mỗi `LO` bài một lô), dừng ở trần."""
        can = math.ceil(len(rows) / LO) if rows else 0
        if can and self.da_goi + can > self.toi_da:
            self.vuot += len(rows)
            return {}, {"_sac_thai": {}, "_chu_de": {},
                        "trang_thai": f"bỏ qua: đạt trần {self.toi_da} lượt gọi AI"}
        if can and not self.cho_lo_truoc():
            self.bo_treo += len(rows)
            return {}, {"_sac_thai": {}, "_chu_de": {},
                        "trang_thai": f"bỏ qua: model treo (lô trước quá {self.cho_toi_da:g} giây)"}
        self.da_goi += can
        return self._xu_goc(rows, *a, **k)

    @contextlib.contextmanager
    def cai(self):
        A._hoi_model, A._phan_xu_ai = self.hoi, self.phan_xu
        try:
            yield self
        finally:
            A._hoi_model, A._phan_xu_ai = self._hoi_goc, self._xu_goc


# ───────────────────────────── chạy pipeline ─────────────────────────────
def _tk_moi(tu: datetime.datetime) -> dict:
    return {"pheu": {}, "moi": 0, "cu": 0, "giu": 0, "de_xuat": 0, "cap_nhat": 0, "spam": 0,
            "khong_brand": 0, "seeding": 0, "chua_ai": 0,
            "pham_vi": {"tu": tu.isoformat(timespec="minutes")}}


def _cong(tong: dict, x: dict) -> None:
    """Cộng thống kê một phần vào tổng (phễu từng nền tảng, `ai_loai` theo mã, tài khoản seeding)."""
    for k, v in x.items():
        if k == "pheu":
            for p, f in v.items():
                g = tong["pheu"].setdefault(p, T._pheu_moi(0, ""))
                for kk, vv in f.items():
                    if isinstance(vv, dict):          # ai_loai theo mã, khối "web"
                        gg = g.setdefault(kk, {})
                        for m, n in vv.items():
                            if isinstance(n, (int, float)) and not isinstance(n, bool):
                                gg[m] = gg.get(m, 0) + n
                    elif isinstance(vv, (int, float)) and not isinstance(vv, bool):
                        g[kk] = g.get(kk, 0) + vv
        elif k == "_tk_seeding":
            tong.setdefault(k, {}).update(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and k in tong:
            tong[k] += v
        elif k == "ai" and v:
            tong["ai"] = v


def _so_ai(tk: dict) -> int:
    """Bài đã tới bước AI của một phần (giữ + AI loại + không nhắc)."""
    return sum(int(f.get("giu", 0)) + sum((f.get("ai_loai") or {}).values())
               + int(f.get("khong_nhac", 0)) for f in tk["pheu"].values())


def _nang(ngay):
    return lambda ma, luot, rows: K.nang_so_lieu(ma, luot, rows, ngay)


def chay_tu_khoa(du_an: dict, luot: int, hits: list, tu: datetime.datetime, nghi, tong: dict,
                 lo: int = LO, *, can_ai: bool = False, sau_phan=None) -> int:
    """Bài đường từ khoá → `_tach_va_giu` theo từng phần ≤ `lo` bài (một lô AI), nghỉ giữa hai phần
    đã gọi AI. Lịch sử seeding = CẢ lô (`lich_su_seeding`). `can_ai`: AI không phán thì không ghi
    (chạy áp dụng); AI chờ `HAN_LO` giây mỗi phần. `sau_phan()`: gọi sau mỗi phần (ghi khoá sổ vừa
    thêm vào tệp hoàn tác NGAY). -> số lô AI đã dùng."""
    tu_kw = T.tu_tim(du_an)
    them = [T._dong_seeding(d, dt) for d, dt in hits if A._khop_tu_khoa(d, tu_kw)]
    hits = sorted(hits, key=lambda x: (x[0]["platform"], x[1]))
    so_lo = 0
    for i in range(0, len(hits), lo):
        phan = hits[i:i + lo]
        ngay = max(d["_luc_doc"] for d, _ in phan).date()
        tk = _tk_moi(tu)
        T._tach_va_giu(du_an, luot, phan, tu_kw, time.monotonic() + HAN_LO + 30, tk,
                       cap_nhat_so=_nang(ngay), lich_su_seeding=them, ai={"song_song": 1},
                       de_xuat=False, can_ai=can_ai, giay_ai=HAN_LO)
        _cong(tong, tk)
        if sau_phan:
            sau_phan()
        if _so_ai(tk):
            so_lo += 1
            nghi(NGHI_GIUA_LO)
    return so_lo


def chay_web(du_an: dict, luot: int, web: list, tu: datetime.datetime, tong: dict, *,
             can_ai: bool = False, khoa_web: set | None = None, sau_phan=None) -> None:
    """Raw Google → `nguon_web.thu_thap` (đoạn trích, không tải trang) → `_tach_va_giu` với sổ đã
    loại RIÊNG của web, như `theo_doi._tim_web` + `_tim_tu_khoa`. `can_ai`, `sau_phan` như
    `chay_tu_khoa`; `khoa_web` nhận khoá bài web của lô (lọc khoá sổ web khi ghi tệp hoàn tác)."""
    ma = du_an["ma"]
    tu_kw = T.tu_tim(du_an)
    for items, luc, _ten in web:
        _cd, khau_hieu = T.khau_hieu_chien_dich(ma, luc)
        tu_web = W.rut_gon_tu_khoa([*tu_kw, *khau_hieu]) or tu_kw
        hits, wk = W.thu_thap(
            {**du_an, "tu_khoa": tu_kw}, tu=tu.date(), den=luc.date(), bay_gio=luc,
            them_tu=khau_hieu, tu_giu=tu, da_biet=T._da_biet_web(ma, du_an, tu_web, tu),
            chay_actor=lambda pl, lim, han, tran, items=items: (items, {}),
            # Không tải trang: robots "không có" (404 = cho phép) để trang không bị đếm "robots
            # cấm"; tải trả -1 (không đọc bằng đường nào) → mọi bài là đoạn trích Google.
            tai=lambda u: (-1, "", u), tai_robots=lambda u: (404, "", u), ngu=lambda s: None,
            boc_toi_da=0)
        tk = _tk_moi(tu)
        w = wk.get("pheu") or {}
        tk["pheu"]["web"] = {**T._pheu_moi(0, ""), "ve": int(w.get("serp") or 0),
                             "pham_vi": len(hits), "loai_tru": int(w.get("loai_tru") or 0),
                             "spam": int(w.get("spam") or 0),
                             "khong_nhac": int(w.get("khong_nhac") or 0),
                             "trung": int(w.get("trung") or 0),
                             "da_loai_truoc": int(w.get("da_loai_truoc") or 0),
                             "cap_nhat": int(w.get("da_co") or 0),
                             "ngoai_pham_vi": int(w.get("qua_cu") or 0)
                             + int(w.get("khong_ngay") or 0),
                             "web": {k: int(w.get(k) or 0) for k in (
                                 "mxh", "tmdt", "nha", "tuyen_dung", "robots_chan", "tai_loi",
                                 "boc_du_phong", "boc_duoc", "da_boc_truoc", "chi_trich",
                                 "trang_hong")}}
        for h, _ in hits:
            h["_luc_doc"] = luc
        tk["_bi_loai"] = list(wk.get("bi_loai") or [])
        if khoa_web is not None:
            khoa_web.update(_khoa(h) for h, _ in hits)
            khoa_web.update(str(x[0]) for x in tk["_bi_loai"] if x)
        if hits:
            T._tach_va_giu(du_an, luot, hits, tu_web, time.monotonic() + HAN_LO + 30, tk,
                           ma_loai=f"{ma}:web", cap_nhat_so=_nang(luc.date()),
                           ai={"song_song": 1}, de_xuat=False, can_ai=can_ai, giay_ai=HAN_LO)
        con = tk.pop("_bi_loai", None)
        if con:
            TDA.ghi_loai(f"{ma}:web", TDA.dau_loai(du_an, tu_web), con, tu)
        _cong(tong, tk)
        if sau_phan:
            sau_phan()


def chay_nguon(du_an: dict, luot: int, theo_nguon: dict[int, list], nguon: dict[int, dict],
               tong: dict, nghi, *, can_ai: bool = False, sau_phan=None) -> int:
    """Raw theo NGUỒN đang theo dõi → đường nguồn: bài đã có chỉ nâng số; bài mới qua `chon_bai`
    (kênh nhà giữ mọi bài; `can_ai`: bài nguồn khác mà AI không phán thì không ghi; AI chờ
    `HAN_LO` giây) → `ghi_bai(…, "theo_doi")`. `sau_phan` như `chay_tu_khoa`. -> số lô AI."""
    ma = du_an["ma"]
    so_lo = 0

    def khoa_hit(d: dict) -> str:                 # như `chon_bai`: id gốc của dòng theo nguồn
        return T._khoa_bai(d["platform"], d.get("link") or "", {"id": d.get("_goc_id")})
    for nid, rows in theo_nguon.items():
        cu = T._khoa_fb_cu(ma, rows, khoa_hit)
        cap_nhat, moi, _trung = TDA.tach_da_biet(
            ma, rows, lambda d, cu=cu: cu.get(khoa_hit(d), khoa_hit(d)))
        if cap_nhat:
            ngay = max(d["_luc_doc"] for d, _ in rows).date()
            tong["nguon"]["cap_nhat"] += K.nang_so_lieu(ma, luot, cap_nhat, ngay)
            tong["nguon"]["da_co"] += len(cap_nhat)
        for i in range(0, len(moi), LO):
            phan = moi[i:i + LO]
            ghi, tk = T.chon_bai(du_an, {nid: phan}, {nid: nguon[nid]},
                                 time.monotonic() + HAN_LO, can_ai=can_ai)
            for k in ("lay_duoc", "qua_cu", "khong_nhac", "loai_tru", "ai_loai", "seeding",
                      "chua_ai"):
                tong["nguon"][k] += int(tk.get(k) or 0)
            if ghi:
                m, c = K.ghi_bai(ma, luot, "theo_doi", ghi)
                tong["nguon"]["moi"] += m
                tong["nguon"]["giu"] += len(ghi)
                tong["nguon"]["cu"] += c
            if sau_phan:
                sau_phan()
            if phan:
                so_lo += 1
                nghi(NGHI_GIUA_LO)
    return so_lo


# ───────────────────────────── in ─────────────────────────────
def _tl(rows) -> int:
    return sum(1 + _so(r.get("binh_luan") if "binh_luan" in r else r.get("bl")) for r in rows)


def cau_ghi_chu(tong: dict, tep: list, bo_qua: list, khung: str) -> list[str]:
    """Các câu cho `luot_quet.ghi_chu` + bản in: tóm tắt, phễu từng nền tảng, đường nguồn."""
    n = tong["nguon"]
    ra = [f"{NHAN}: {len({t for t, _, _ in tep})} tệp raw đã trả tiền ({khung}), không gọi Apify, "
          "chi phí 0"
          + (f"; bỏ qua {len(bo_qua)} tệp (actor không có bộ chuẩn hoá của Mark)" if bo_qua else ""),
          f"tìm theo từ khoá (raw): nâng số liệu {tong['cap_nhat']} bài đã có, giữ "
          f"{tong['moi'] + tong['cu']} ({tong['moi']} mới), " + T._cau_seeding_tk(tong)
          + (f"bỏ {tong['spam']} bài spam, " if tong.get("spam") else "")
          + (f"bỏ {tong['khong_brand']} bài đường hashtag không nhắc brand, "
             if tong.get("khong_brand") else "") + "0,00 USD"]
    chua = int(tong.get("chua_ai") or 0) + int(n.get("chua_ai") or 0)
    if chua:
        # Soát M3: phần AI không phán KHÔNG ghi theo luật — nói rõ để người chạy chạy lại.
        ra.insert(1, f"AI chưa phán {chua} bài (lỗi / hết giờ / model treo / đạt trần gọi AI) — "
                     "CHƯA ghi, "
                     "không vào sổ; chạy lại script (tệp hoàn tác mới) để nạp tiếp")
    for p in (*_MXH, "web"):
        if p in tong["pheu"]:
            ra.append(T._cau_pheu(p, {**tong["pheu"][p], "ngay": tong.get("_ngay", 0),
                                      "ly_do": NHAN, "xin_ly_do": ""}))
    if n["lay_duoc"] or n["da_co"]:
        ra.append(f"raw theo nguồn đang theo dõi (đường nguồn): {n['da_co']} bài đã có (nâng số "
                  f"{n['cap_nhat']}), {n['lay_duoc']} bài mới → quá {T.NGAY_GIU} ngày "
                  f"{n['qua_cu']}, không nhắc {n['khong_nhac']}, từ loại trừ {n['loai_tru']}, "
                  f"AI loại {n['ai_loai']}, seeding {n['seeding']}"
                  + (f", AI chưa phán {n['chua_ai']}" if n.get("chua_ai") else "")
                  + f" → giữ {n['giu']} ({n['moi']} mới)")
    return ra


def _tong_moi(tu: datetime.datetime, ngay: int) -> dict:
    t = _tk_moi(tu)
    t["nguon"] = {k: 0 for k in ("lay_duoc", "qua_cu", "khong_nhac", "loai_tru", "ai_loai",
                                 "seeding", "chua_ai", "giu", "moi", "cu", "da_co", "cap_nhat")}
    t["_ngay"] = ngay
    return t


def chay(ns, in_ra=print, bay_gio: datetime.datetime | None = None, nghi=time.sleep) -> int:
    ma = ns.du_an.strip().lower()
    if ns.hoan_tac:
        return hoan_tac(ma, ns.hoan_tac, in_ra)
    if ns.ap_dung and not ns.sao_luu:
        in_ra("--ap-dung cần --sao-luu <tệp> (tệp hoàn tác).")
        return 2
    if ns.ap_dung and os.path.exists(ns.sao_luu):
        in_ra(f"Tệp {ns.sao_luu} đã có — chọn tên khác (không ghi đè tệp hoàn tác cũ).")
        return 2
    if not ns.duong:
        in_ra("Thiếu thư mục / tệp raw.")
        return 2
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    tu = datetime.datetime.combine(datetime.date.fromisoformat(ns.tu), datetime.time(), _VN)
    du_an = K.doc_du_an(ma)
    if not du_an:
        in_ra(f"Không có dự án '{ma}' trong kho.")
        return 2
    raw = doc_raw(ns.duong, tu, bay_gio)
    ten_brand = None
    for d, _ in raw["tim"]:
        if d.get("_tag_vao") and d.get("_tag_feed") == "#":
            ten_brand = ten_brand or T.ten_brand(du_an, bay_gio)
            d["_tag_feed"] = T.tag_feed_chung(d["_tag_vao"], ten_brand)
    nguon_ds = K.nguon_cua_du_an(ma)
    nguon = {int(n["id"]): n for n in nguon_ds}
    tim, dem = loc_khung(raw["tim"] + raw["ho_so"], tu, bay_gio)
    theo_nguon, le = tach_nguon([x for x in tim if x[0].get("_ho_so")], nguon_ds)
    tim = [x for x in tim if not x[0].get("_ho_so")] + le
    # Trang Facebook (thedoor) khớp ĐÚNG MỘT nguồn đang theo dõi → CHỈ đường nguồn; trang lạ →
    # đường từ khoá (soát 18/10/2026, lượt nạp 14: bản trước loại theo `id()` của dict nên bài
    # trang nhà đi cả hai đường — `doc_trang_fb`).
    fb = bang_dau([n for n in nguon_ds if n.get("nen_tang") == "facebook"])
    for items, luc, _ten in raw["trang_fb"]:
        for nid, ds in doc_trang_fb(items, fb, nguon).items():
            for d, dt in ds:
                if dt and tu <= dt <= bay_gio + datetime.timedelta(hours=1):
                    d["_luc_doc"] = luc
                    (tim if nid is None else theo_nguon.setdefault(nid, [])).append((d, dt))
    tim, sang = tach_kenh_nha(tim, nguon_ds)
    for nid, ds in sang.items():
        theo_nguon.setdefault(nid, []).extend(ds)
    # Hai lần đọc cùng trang (vòng 2 + Kompa): bỏ trùng, giữ bản nhiều bình luận nhất.
    theo_nguon = {nid: loc_khung(ds, tu, bay_gio)[0] for nid, ds in theo_nguon.items()}
    # Bản tìm theo từ khoá của bài đã sang đường nguồn (link pfbid ↔ id số): bỏ — mỗi bài một đường.
    da = {k for ds in theo_nguon.values() for d, _ in ds for k in khoa_on_dinh(d)}
    tim = [x for x in tim if not khoa_on_dinh(x[0]) & da]
    khung = f"{tu:%d/%m} → {bay_gio.astimezone(_VN):%d/%m}"
    tong = _tong_moi(tu, (bay_gio.date() - tu.date()).days)
    for p, x in dem.items():
        f = tong["pheu"].setdefault(p, T._pheu_moi((bay_gio.date() - tu.date()).days, NHAN))
        f.update(ngay=(bay_gio.date() - tu.date()).days, ly_do=NHAN, **x)
    in_ra(f"Dự án {ma} — " + ("ÁP DỤNG" if ns.ap_dung else
                              "CHẠY THỬ (không gọi AI, không ghi gì; kết nối kho chỉ đọc)") + ".")
    loai_tep: dict[str, list] = {}
    for ten, loai, n in raw["tep"]:
        loai_tep.setdefault(loai, [0, 0])
        loai_tep[loai][0] += 1
        loai_tep[loai][1] += n
    in_ra(f"Raw: {len({t for t, _, _ in raw['tep']})} tệp đọc được — " + "; ".join(
        f"{k} {v[0]} tệp/{v[1]} bài" for k, v in sorted(loai_tep.items())) + ".")
    # Chỉ tệp lấy giờ đọc theo giờ ghi tệp (item không có trường thời gian — `_luc_doc_item`).
    moi_chep = sorted({f.name for f in cac_tep(ns.duong) if f.name in raw["theo_gio_tep"]
                       and _luc_doc(f).date() == bay_gio.astimezone(_VN).date()})
    if moi_chep:
        in_ra(f"CẢNH BÁO: {len(moi_chep)} tệp raw mang giờ ghi HÔM NAY ({', '.join(moi_chep[:3])}"
              f"{' …' if len(moi_chep) > 3 else ''}) — chép lại bằng rsync -a / scp -rp để giữ giờ "
              "đọc thật (ngày ảnh chụp chi_so_ngay theo giờ này).")
    if raw["bo_qua"]:
        in_ra(f"Bỏ qua {len(raw['bo_qua'])} tệp: " + "; ".join(
            f"{t} ({ly})" for t, ly in raw["bo_qua"][:12])
              + (" …" if len(raw["bo_qua"]) > 12 else "") + ".")
    in_ra(f"Khung {khung}: đường từ khoá {len(tim)} bài, đường nguồn đang theo dõi "
          f"{sum(len(x) for x in theo_nguon.values())} bài.")
    if not ns.ap_dung:
        ghi: dict = {}
        with che_do_chay_thu(ghi):
            so_lo = chay_nguon(du_an, 0, theo_nguon, nguon, tong, lambda s: None)
            so_lo += chay_tu_khoa(du_an, 0, tim, tu, lambda s: None, tong)
            chay_web(du_an, 0, raw["web"], tu, tong)
        for c in cau_ghi_chu(tong, raw["tep"], raw["bo_qua"], khung):
            in_ra("  " + c)
        import loc_rac
        moi = list(ghi["bai"])
        ten = [str(du_an.get("ten") or ma)]
        goi_ten = [r for r in moi if A._khop_tu_khoa(
            {"text": r.get("noi_dung"), "hashtags": r.get("hashtag"), "kenh": r.get("tac_gia"),
             "username": r.get("tai_khoan")}, ten)]
        seed = ghi["seeding"]
        tu_kw = T.tu_tim(du_an)
        nhac = {T._dong_seeding(d, dt)["khoa"] for d, dt in tim if A._khop_tu_khoa(d, tu_kw)}
        seed_nhac = [x for x in seed if x["khoa"] in nhac]
        thi_truong = sum(int(f.get("thi_truong") or 0) for f in tong["pheu"].values())
        # Cổng brand đường hashtag: bài bỏ (theo khoá sổ đã loại) + thảo luận, tách theo nền tảng.
        k_brand = {str(k) for k, ly, _ in ghi["loai_ds"] if ly == T.LY_DO_HASHTAG_BRAND}
        bo_brand = [{"bl": d.get("comments"), "p": d["platform"]} for d, _ in tim
                    if _khoa(d) in k_brand]
        theo_p = {p: sum(1 for x in bo_brand if x["p"] == p) for p in _MXH}
        # Soát 18/10/2026: số "sẽ nạp" là bài mới NHẮC từ khoá (chạy thử không có AI) — không phải
        # trần: chạy thật AI còn được giữ bài không nhắc từ khoá trong số gửi AI (`_giu_tu_khoa`).
        in_ra(f"ƯỚC TÍNH: sẽ nạp {len(moi)} bài mới nhắc từ khoá, ≈ {_tl(moi)} thảo luận (1 + bình "
              f"luận) — TRƯỚC AI (AI còn loại bài lạc đề / trùng tên, và được giữ thêm bài trong "
              f"{ghi['ai_khong_khop']} bài không nhắc từ khoá gửi AI); trong đó gọi tên {ten[0]}: "
              f"{len(goi_ten)} bài, {_tl(goi_ten)} thảo luận. Loại seeding affiliate {len(seed)} "
              f"bài ({_tl(seed)} thảo luận; {len(seed_nhac)} bài / {_tl(seed_nhac)} thảo luận "
              f"nhắc từ khoá) của {len(tong.get('_tk_seeding') or {})} tài khoản; loại vì đường "
              f"hashtag không nhắc brand {len(bo_brand)} bài ({_tl(bo_brand)} thảo luận"
              + "".join(f"; {p} {n}" for p, n in theo_p.items() if n) + f"); ngoài thị "
              f"trường VN {thi_truong}; nâng số {len(ghi['nang'])} bài đã có.")
        for tk_, x in sorted((tong.get("_tk_seeding") or {}).items(),
                             key=lambda kv: (-kv[1]["so_bai"], kv[0])):
            in_ra(f"    seeding {loc_rac.cau_seeding(tk_, x)}")
        n_ai = sum(ghi["ai"])
        so_goi = sum(math.ceil(x / LO) for x in ghi["ai"] if x)
        in_ra(f"AI: {n_ai} bài cần phân xử → {so_lo} lần gọi model ({so_goi} lô ≤ {LO} bài, một lô "
              f"một lúc, chờ ≤ {HAN_LO:g} giây/lô, nghỉ {NGHI_GIUA_LO} giây) — ≈ {so_lo} phút; trần "
              f"--toi-da-goi-ai {ns.toi_da_goi_ai} lượt"
              + (" — THẤP hơn số lô: phần vượt trần không ghi, chạy lại để nạp tiếp"
                 if so_goi > ns.toi_da_goi_ai else "") + ".")
        in_ra("Không ghi gì. Ghi thật: thêm --ap-dung --sao-luu <tệp hoàn tác>.")
        return 0
    return ap_dung(ns, ma, du_an, raw, tim, theo_nguon, nguon, tong, tu, khung, in_ra, nghi)


def _khoa_so(ma: str) -> set[str]:
    x = (TDA._doc_so_loai().get("du_an") or {}).get(ma)
    if not isinstance(x, dict):
        return set()
    return {str(k) for phan in ("bai", "seeding") for k in (x.get(phan) or {})}


def _chuan_bi_model() -> None:
    """Nạp `.env` của Mark và chỉ đường tới Hermes như `scripts/lang_nghe_gan_lai.py` — AI phân xử
    đi đúng đường lease model như `/theodoi`."""
    from config import config
    os.environ.setdefault("HERMES_HOME", config.hermes_home)
    os.environ.setdefault("PYTHONUTF8", "1")
    if config.hermes_agent_dir not in sys.path:
        sys.path.insert(0, config.hermes_agent_dir)


def _ghi_dong(so_luu, x: dict) -> None:
    so_luu.write(json.dumps(x, ensure_ascii=False, default=str) + "\n")
    so_luu.flush()
    os.fsync(so_luu.fileno())


class SoThem:
    """Khoá sổ lần nạp đã thêm, ghi vào tệp hoàn tác NGAY sau mỗi phần (soát 18/10/2026, LOW —
    trước đây chỉ ghi một dòng "so" ở cuối, tiến trình bị giết giữa chừng là mất). Theo dõi cả sổ
    của dự án (đường từ khoá + đường nguồn: "đã loại" + seeding) và sổ RIÊNG của web
    (`<mã>:web`). Chỉ nhận khoá của bài trong lô nạp (`khoa_nap`), không gỡ nhầm khoá lượt quét
    chạy song song vừa thêm."""

    def __init__(self, ma: str, khoa_nap: set[str], khoa_web: set[str], so_luu):
        self.ma, self.khoa_nap, self.khoa_web, self.so_luu = ma, khoa_nap, khoa_web, so_luu
        self.truoc = {s: _khoa_so(s) for s in (ma, f"{ma}:web")}
        self.da_ghi: dict[str, set[str]] = {s: set() for s in self.truoc}

    def ghi(self) -> None:
        for s, cu in self.truoc.items():
            nhan = self.khoa_web if s.endswith(":web") else self.khoa_nap
            moi = sorted(((_khoa_so(s) - cu) & nhan) - self.da_ghi[s])
            if moi:
                _ghi_dong(self.so_luu, {"loai_dong": "so", "so": s, "khoa": moi})
                self.da_ghi[s].update(moi)

    def tong(self) -> int:
        return sum(len(x) for x in self.da_ghi.values())


def ap_dung(ns, ma, du_an, raw, tim, theo_nguon, nguon, tong, tu, khung, in_ra, nghi) -> int:
    _chuan_bi_model()
    # Khoá sổ có thể thêm: bài đường từ khoá + bài theo nguồn (sổ seeding của `chon_bai`), kèm khoá
    # ổn định Facebook; khoá web điền dần trong `chay_web`.
    lo_nap = [*tim, *(x for ds in theo_nguon.values() for x in ds)]
    khoa_nap = {_khoa(d) for d, _ in lo_nap} | {
        k for d, dt in lo_nap for k in T._khoa_loai_on_dinh(d, dt)}
    khoa_web: set[str] = set()
    luot = K.mo_luot(ma, "tu_khoa", ma_viec=f"nap-raw-{datetime.datetime.now(_VN):%Y%m%d%H%M}")
    # Mặc định là LỖI, chỉ chạy hết mới thành "xong" (soát 18/10/2026, LOW): bản trước khởi tạo
    # "xong" và chỉ bắt `Exception`, nên Ctrl-C (KeyboardInterrupt) hay SystemExit giữa chừng vẫn
    # đóng lượt "xong" trên dashboard dù chỉ nạp một phần.
    trang_thai, loi = "loi", "dừng giữa chừng"
    with open(ns.sao_luu, "x", encoding="utf-8") as so_luu:
        so_moi = SoThem(ma, khoa_nap, khoa_web, so_luu)
        _ghi_dong(so_luu, {"loai_dong": "dau", "du_an": ma, "luot_id": luot, "lenh": "nap_raw",
                           "luc": datetime.datetime.now(datetime.timezone.utc).isoformat(
                               timespec="seconds"), "tu": ns.tu,
                           "tep": [t for t, _, _ in raw["tep"]]})
        so_lo = 0
        gac = GacAI(ns.toi_da_goi_ai, in_ra)
        try:
            # Soát M3: AI không phán thì không ghi (`can_ai`); mọi lượt gọi model qua `GacAI`.
            with gac.cai():
                # Đường nguồn ghi TRƯỚC (soát 18/10/2026): bản trùng còn lọt ở đường từ khoá (khoá
                # khác, không id số) gặp bài đã có `nguon_id` → chỉ nâng số; ngược lại đường nguồn
                # thấy "đã có" và chỉ nâng số, bài nhà giữ `nguon_id` NULL.
                so_lo += chay_nguon(du_an, luot, theo_nguon, nguon, tong, nghi, can_ai=True,
                                    sau_phan=so_moi.ghi)
                so_lo += chay_tu_khoa(du_an, luot, tim, tu, nghi, tong, can_ai=True,
                                      sau_phan=so_moi.ghi)
                chay_web(du_an, luot, raw["web"], tu, tong, can_ai=True, khoa_web=khoa_web,
                         sau_phan=so_moi.ghi)
            trang_thai, loi = "xong", None
        except KeyboardInterrupt:
            # Người chạy bấm Ctrl-C: phần đã ghi giữ nguyên (tệp hoàn tác có đủ khoá) → "một phần".
            trang_thai = "mot_phan"
            loi = ("dừng giữa chừng (Ctrl-C) — phần đã ghi giữ nguyên; chạy lại với --sao-luu "
                   "<tệp MỚI> để nạp tiếp")
        except Exception as e:  # noqa: BLE001 — vẫn đóng lượt + ghi khoá đã thêm để hoàn tác được
            trang_thai, loi = "loi", A._che_token(f"{type(e).__name__}: {e}")[:300]
        finally:
            so_moi.ghi()
            them = [str(r["khoa"]) for r in K.khoa_theo_luot_dau(ma, luot)]
            _ghi_dong(so_luu, {"loai_dong": "bai_moi", "khoa": them})
            so_them = [k for x in so_moi.da_ghi.values() for k in x]
            cau = cau_ghi_chu(tong, raw["tep"], raw["bo_qua"], khung)
            chua = int(tong.get("chua_ai") or 0) + int(tong["nguon"].get("chua_ai") or 0)
            if trang_thai == "xong" and chua:
                trang_thai = "mot_phan"      # AI chưa phán một phần: chưa ghi, chạy lại để nạp
            K.dong_luot(luot, trang_thai=trang_thai, bai_moi=tong["moi"] + tong["nguon"]["moi"],
                        bai_cap_nhat=tong["cap_nhat"] + tong["cu"] + tong["nguon"]["cap_nhat"],
                        chi_phi_usd=0.0, loi=loi, ghi_chu="; ".join(cau))
            T._bao_dashboard(ma, luot)
    for c in cau:
        in_ra("  " + c)
    in_ra(f"Lượt {luot}: thêm {len(them)} bài, {gac.da_goi}/{gac.toi_da} lượt gọi model"
          + (f" (chờ lô quá hạn {gac.cho} lần)" if gac.cho else "")
          + (f"; model treo — {gac.bo_treo} bài chưa gửi AI" if gac.bo_treo else "")
          + f"; khoá sổ thêm {len(so_them)}. Tệp hoàn tác: {ns.sao_luu}"
          + (f". {'DỪNG' if trang_thai == 'mot_phan' else 'LỖI'}: {loi}" if loi else ""))
    if chua:
        in_ra(f"CHƯA XONG: {chua} bài AI chưa phán (lỗi / hết giờ / đạt trần --toi-da-goi-ai) — "
              "không ghi, không vào sổ. Chạy lại cùng lệnh với --sao-luu <tệp MỚI> để nạp tiếp "
              "(bài đã ghi thành \"đã có\", bài đã loại không gọi AI lại).")
    return 0 if loi is None and not chua else 1


def hoan_tac(ma: str, tep: str, in_ra) -> int:
    """Xoá bài lượt nạp đã thêm mà chưa bị đụng + gỡ khoá sổ đã thêm (sổ dự án — đường từ khoá và
    đường nguồn — lẫn sổ web `<mã>:web`; dòng "so" cũ không có trường "so" là sổ dự án). Soát
    18/10/2026 (LOW): giao dịch xoá giữ khoá advisory mở lượt (`lang_nghe_db.so_khoa_luot`) và dừng
    khi dự án có lượt khác đang chạy."""
    dau, khoa, so = {}, set(), {}
    with open(tep, encoding="utf-8") as f:
        for i, dong in enumerate(f):
            if not dong.strip():
                continue
            r = json.loads(dong)
            if i == 0 and r.get("loai_dong") == "dau":
                dau = r
            elif r.get("loai_dong") == "bai_moi":
                khoa |= set(r.get("khoa") or [])
            elif r.get("loai_dong") == "so":
                so.setdefault(str(r.get("so") or ma), set()).update(r.get("khoa") or [])
    if dau.get("du_an") != ma or not dau.get("luot_id"):
        in_ra(f"Tệp hoàn tác không phải của dự án '{ma}' (hoặc thiếu lượt) — dừng.")
        return 2
    luot = int(dau["luot_id"])
    with K.ket_noi() as c:
        if not bool((c.execute(SQL_QUYEN).fetchone() or {}).get("xoa")):
            in_ra("Role hiện tại KHÔNG có quyền DELETE trên bai. Trước --hoan-tac: sudo -u postgres "
                  "psql -d lang_nghe -c 'GRANT DELETE ON bai TO mark'; xong thì REVOKE.")
            return 2
    hien = K.khoa_theo_luot_dau(ma, luot)
    khoa |= {str(r["khoa"]) for r in hien}
    sach = [str(r["khoa"]) for r in hien if r.get("luot_cuoi") == luot and not r.get("bl_lay_luc")
            and not int(r.get("so_bl") or 0)]
    with K.ket_noi() as c:
        c.execute(SQL_HAN_KHOA)
        c.execute(SQL_KHOA_LUOT, (K.so_khoa_luot(ma),))
        dang = [int(r["id"]) for r in c.execute(SQL_LUOT_CHAY, (ma, luot, K.GIO_BO_DO)).fetchall()]
        if dang:
            in_ra(f"Dự án có lượt đang chạy (lượt {', '.join(map(str, dang))}) — đợi lượt xong rồi "
                  "chạy lại --hoan-tac (chưa xoá gì).")
            return 2
        xoa = [r["khoa"] for r in c.execute(SQL_XOA, (ma, sach, luot, luot)).fetchall()] \
            if sach else []
    go = 0
    for s, ks in so.items():
        if s in (ma, f"{ma}:web"):
            TDA.bo_khoi_so(s, sorted(ks))
            go += len(ks)
    giu = sorted({str(r["khoa"]) for r in hien} - set(xoa))
    in_ra(f"Hoàn tác lượt nạp {luot}: xoá {len(xoa)} bài; giữ {len(giu)} bài đã bị đụng sau lượt "
          f"nạp (lượt sau cập nhật / đã cào bình luận)" + (": " + ", ".join(giu[:10]) if giu else "")
          + f"; gỡ {go} khoá khỏi sổ đã loại / sổ seeding / sổ web. Số đã nâng của bài cũ giữ "
          "nguyên. Xong thì thu quyền: sudo -u postgres psql -d lang_nghe -c 'REVOKE DELETE ON bai "
          "FROM mark'.")
    return 0


def tao_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Nạp raw đã trả tiền vào kho lang_nghe qua pipeline "
                                             "lượt tìm theo từ khoá (mặc định chạy thử).")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("duong", nargs="*", help="thư mục (tìm đệ quy raw_*.json[l]) hoặc tệp raw")
    ap.add_argument("--tu", default=TU_MAC_DINH, help=f"ngày đăng sớm nhất (mặc định {TU_MAC_DINH})")
    ap.add_argument("--ap-dung", action="store_true", help="ghi thật (cần --sao-luu)")
    ap.add_argument("--sao-luu", metavar="TEP", help="tệp hoàn tác JSONL (tạo mới)")
    ap.add_argument("--hoan-tac", metavar="TEP", help="xoá bài lượt nạp đã thêm (chưa bị đụng)")
    ap.add_argument("--toi-da-goi-ai", type=int, default=TOI_DA_GOI_AI, metavar="N",
                    help=f"trần tổng lượt gọi model cả lần chạy (mặc định {TOI_DA_GOI_AI}; mỗi lô "
                         f"≤ {LO} bài một lượt) — phần vượt trần không ghi, chạy lại để nạp tiếp")
    return ap


def _dsn_tu_env_file() -> None:
    """Mark đặt `LANG_NGHE_DSN` trong `.env`: chỉ đọc ĐÚNG khoá đó (như `lang_nghe_gop_bai_fb`).
    Chạy thật thì `_chuan_bi_model` nạp cả `.env` cho đường model."""
    if os.environ.get("LANG_NGHE_DSN"):
        return
    tep = GOC / ".env"
    if not tep.exists():
        return
    for dong in tep.read_text(encoding="utf-8", errors="replace").splitlines():
        k, _, v = dong.partition("=")
        if k.strip() == "LANG_NGHE_DSN" and v.strip():
            os.environ["LANG_NGHE_DSN"] = v.strip()
            return


def main(argv: list[str] | None = None) -> int:
    ap = tao_parser()
    ns = ap.parse_args(argv)
    if ns.ap_dung and ns.hoan_tac:
        ap.error("--ap-dung và --hoan-tac là hai việc riêng")
    _dsn_tu_env_file()
    return chay(ns)


if __name__ == "__main__":
    sys.exit(main())
