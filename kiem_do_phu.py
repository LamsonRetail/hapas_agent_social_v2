"""Kiểm ĐỘ PHỦ của `/theodoi` — hai lần mỗi tuần (17/10/2026).

Vì sao — chủ dự án 17/10: "nhưng nó chỉ giải quyết khi tôi yêu cầu, trước đó làm social quét sao
ko quét thấy những bài đó" → duyệt "độ phủ cho hẳn 0,1 đô đi"; cùng ngày đổi phạm vi: HAI lần
mỗi tuần, 0,20 USD mỗi lần, và Mark phải TỰ SỬA đường thu thập theo lý do sót (`hanh_dong`). Video seeding của KOL (caption chỉ
có hashtag: #HAPAS #LAMMOIDIEUVIYEU #QUATANG2010) lọt mấy tuần vì thu thập chỉ có MỘT đường (tìm
theo từ khoá, sắp liên quan); lượt "nổi" (#63) vá đúng ca đó nhưng chỉ vá được ca đã biết. Kiểm độ
phủ làm lỗ hổng TỰ HIỆN ra trên dashboard trước khi chủ dự án phải tự phát hiện.

Cách làm — mỗi dự án tối đa một lượt mỗi `GIO_GIAN` giờ (mốc trong sổ mốc tìm theo từ khoá,
khoá `KHOA_MOC`), trần `TRAN_MAC_DINH` USD (đặt riêng ở `du_an.cau_hinh.do_phu`, có công tắc):
  • MẪU ĐỐI CHIẾU lấy bằng đường KHÁC thu thập hằng ngày, chỉ TikTok qua TikTok API (scraptik,
    0,003 USD/yêu cầu → 0,20 USD ≈ 66 yêu cầu):
      (a) bài của HASHTAG brand/chiến dịch (`challengePosts`, 20 bài/yêu cầu): tag lấy từ từ khoá
          dự án + tag hay đi cùng nhất trong bài đã giữ 30 ngày — ~4/5 số yêu cầu. Đường này bắt
          đúng ca seeding chỉ-hashtag, và mỗi yêu cầu ra ~10 bài trong 30 ngày (đo #hapas).
      (b) bài MỚI NHẤT của các nhà sáng tạo nhiều thảo luận nhất 30 ngày (+ đề xuất nguồn đang
          chờ/đã duyệt mà chưa theo dõi), ≤ 2 trang × 10 bài, dừng sớm khi gặp bài cũ hơn 30
          ngày — ~1/5 số yêu cầu: kiểm theo NGƯỜI (bài brand thứ hai của cùng KOL), ít bài brand
          mỗi yêu cầu hơn nên phần nhỏ hơn (`PHAN_TAG`).
      (c) "tìm nhiều bình luận nhất": TikTok API chỉ sắp liên quan / nhiều thích / ngày (đã dùng
          ở lượt thường + lượt nổi) — không có đường độc lập thứ ba, bỏ.
    Nguồn đang theo dõi KHÔNG vào mẫu (đó là đường thu thập hằng ngày).
  • ĐỘ PHỦ = bài mẫu nhắc brand (cùng luật khớp từ khoá/hashtag `apify_tool._khop_tu_khoa`, bỏ từ
    loại trừ + spam + bài AI đã loại trước — không gọi AI cho số đo) đã có trong `bai` / tổng bài
    nhắc brand; ĐỘ PHỦ THEO THẢO LUẬN như trên nhưng mỗi bài nặng 1 + số bình luận (cách đếm thảo
    luận của Kompa). Kèm danh sách bài sót nhiều thảo luận nhất + lý do có lẽ bị sót.
  • Bài brand trong mẫu đi CÙNG phễu của tìm theo từ khoá (`theo_doi._tach_va_giu`: bài đã có →
    cập nhật số; bài mới → spam → AI → ghi kho), nên kiểm xong là lỗ đã được lấp; rồi Mark sửa
    đường thu thập theo lý do sót (đề xuất nguồn, hashtag lượt nổi, nới lượt nổi — `hanh_dong`).
Tiền: mỗi yêu cầu một run Apify (`maxTotalChargeUsd` của `tiktok_api._goi`), run id ghi vào sổ
việc ngay khi Apify trả (`them_phan`) → `chot_chi_phi` tính tiền thật; tổng yêu cầu chặn bởi
`tiktok_api.Ngan` = min(trần độ phủ, phần còn của tháng, phần còn của việc). Mốc nhịp ghi TRƯỚC
khi gửi yêu cầu đầu (khởi động lại giữa chừng không trả tiền lần hai trong cùng nhịp); không tiêu đồng
nào thì trả mốc cũ.
"""
from __future__ import annotations

import datetime
import math
import re
from collections import Counter

import apify_tool as A
import lang_nghe_db as K
import tiktok_api as TT

_VN = datetime.timezone(datetime.timedelta(hours=7))
KHOA_MOC = "do_phu"          # khoá trong sổ mốc tìm theo từ khoá (`theo_doi.ghi_moc_tk`)
#: Chủ dự án 17/10 (đổi phạm vi): HAI lần mỗi tuần, 0,20 USD mỗi lần.
GIO_GIAN = 84                # giờ giữa hai lượt kiểm của một dự án (3,5 ngày)
TRAN_MAC_DINH = 0.20         # USD/lượt kiểm
TRAN_TOI_DA = 1.0            # trần đặt riêng lớn nhất (chặn số rác)
NGAY_MAU = 30                # chỉ bài đăng trong 30 ngày gần nhất mới vào mẫu
#: Phần yêu cầu cho đường hashtag (còn lại: nhà sáng tạo). Đo thật 17/10/2026 (HAPAS, 30 ngày,
#: 497 bài brand trong hợp mọi đường): feed hashtag thêm 157 bài / 8.036 thảo luận ngoài (liên quan
#: + nhiều thích) với 22 yêu cầu; bài mới nhất của 10 nhà sáng tạo thêm 4 bài / 1.390 thảo luận với
#: 10 yêu cầu → hashtag gấp ~2,6 lần thảo luận mỗi USD.
PHAN_TAG = 0.8
TAG_TOI_DA = 4
TAG_TU_KHOA_TOI_DA = 2       # tag lấy từ từ khoá dự án; phần còn lại từ bài đã giữ
TAG_TOI_THIEU_BAI = 2        # tag trong bài đã giữ phải có ở ≥ 2 bài mới chọn
TAG_TRANG_TOI_DA = 6         # ≈ 120 bài mỗi tag
TAC_GIA_TOI_DA = 10
TAC_GIA_TRANG = 2            # 2 × 10 bài mới nhất (bài seeding 15 ngày trước nằm ở trang 2)
YEU_CAU_TOI_THIEU = 5        # ít hơn thì mẫu quá mỏng — không kiểm
SOT_TOI_DA = 10              # bài sót lưu lại (nhiều thảo luận nhất)
BO_NHO_TOI_DA = 60           # cid / uid nhớ trong mốc (đỡ một yêu cầu mỗi tag / người)
NGAY_CUA_SO = 7              # lượt tìm hằng ngày từ lượt thứ hai chỉ xin "tuần này"
IT_THICH = 100               # dưới mức này tìm liên quan / nhiều thích đều xếp thấp
#: Hashtag chung chung — không phải tag brand/chiến dịch dù đi cùng bài brand.
TAG_CHUNG = frozenset({
    "fyp", "foryou", "foryoupage", "fypシ", "xuhuong", "xh", "xuhuongtiktok", "viral", "trending",
    "trend", "tiktok", "tiktokvietnam", "capcut", "review", "reviewlamdep", "unboxing", "outfit",
    "ootd", "fashion", "thoitrang", "quatang", "giftideas", "hot", "learnontiktok", "lamdep",
    "beauty", "tet", "sale", "deal", "vietnam", "vn", "tui", "tuixach", "fy", "foryourpage",
    "xuhuong2026", "trending2026", "tiktokshop", "muataitiktokshop", "goclamdep"})


# ───────────────────────────── cấu hình + nhịp ─────────────────────────────
def cau_hinh(du_an: dict) -> dict:
    """{"bat", "tran_usd"} hiệu lực: `du_an.cau_hinh.do_phu`; thiếu → bật, 0,20 USD. Trần rác
    (không phải số, âm) → mặc định; kẹp [0, `TRAN_TOI_DA`]; 0 = tắt."""
    goc = du_an.get("cau_hinh") if isinstance(du_an.get("cau_hinh"), dict) else {}
    x = goc.get("do_phu") if isinstance(goc.get("do_phu"), dict) else {}
    t = x.get("tran_usd", TRAN_MAC_DINH)
    try:
        tran = TRAN_MAC_DINH if isinstance(t, bool) else float(t)
    except (TypeError, ValueError):
        tran = TRAN_MAC_DINH
    if not math.isfinite(tran) or tran < 0:
        tran = TRAN_MAC_DINH
    tran = round(min(TRAN_TOI_DA, tran), 2)
    return {"bat": x.get("bat", True) is not False and tran > 0, "tran_usd": tran}


def den_han(moc: dict | None, bay_gio: datetime.datetime) -> tuple[bool, str]:
    """Lượt này có kiểm không. -> (có, lý do)."""
    try:
        luc = datetime.datetime.fromisoformat(str((moc or {}).get("luc") or ""))
    except ValueError:
        return True, "chưa kiểm lần nào"
    luc = luc if luc.tzinfo else luc.replace(tzinfo=_VN)
    if bay_gio - luc < datetime.timedelta(hours=GIO_GIAN):
        return False, f"đã kiểm {luc.astimezone(_VN):%d/%m %H:%M} (< {GIO_GIAN} giờ)"
    return True, f"lần kiểm trước {luc.astimezone(_VN):%d/%m}"


# ───────────────────────────── chọn mẫu ─────────────────────────────
def _tag_cua(chuoi: str) -> list[str]:
    """Tag (đã `chuan_tag`) của một ô `bai.hashtag` ("a, b, c") hoặc chữ có '#'."""
    ra = []
    for x in re.split(r"[,\s]+", str(chuoi or "")):
        t = TT.chuan_tag(x)
        if t and t not in ra:
            ra.append(t)
    return ra


def chon_tag(tu: list[str], hashtag_bai: list[str]) -> list[str]:
    """Tag cho mẫu: (1) từ khoá dự án viết liền (≤ `TAG_TU_KHOA_TOI_DA`, từ một chữ trước), (2)
    tag hay đi cùng nhất trong bài đã giữ 30 ngày (≥ `TAG_TOI_THIEU_BAI` bài, bỏ tag chung
    chung `TAG_CHUNG`), tag chứa tên brand đi trước. Tổng ≤ `TAG_TOI_DA`."""
    ra: list[str] = []
    for t in sorted(tu, key=lambda x: (" " in str(x).strip(), len(str(x)))):
        g = TT.chuan_tag(t)
        if 3 <= len(g) <= 40 and g not in ra and len(ra) < TAG_TU_KHOA_TOI_DA:
            ra.append(g)
    goc = [TT.chuan_tag(t) for t in tu if TT.chuan_tag(t)]
    dem = Counter(t for h in hashtag_bai for t in _tag_cua(h))
    ung = [(t, n) for t, n in dem.items()
           if n >= TAG_TOI_THIEU_BAI and t not in TAG_CHUNG and t not in ra and 3 <= len(t) <= 40]
    ung.sort(key=lambda x: (not any(g in x[0] for g in goc), -x[1], x[0]))
    for t, _ in ung:
        if len(ra) >= TAG_TOI_DA:
            break
        ra.append(t)
    return ra


def chon_tac_gia(noi_bat: list[dict], de_xuat: list[dict], dang_theo_doi: set[str],
                 toi_da: int = TAC_GIA_TOI_DA) -> list[str]:
    """Nhà sáng tạo cho mẫu: nhiều thảo luận nhất 30 ngày, rồi đề xuất (chờ / đã duyệt) — bỏ
    tài khoản đang theo dõi làm nguồn (đường thu thập hằng ngày)."""
    ra: list[str] = []
    for u in [x.get("tai_khoan") for x in noi_bat] + [x.get("dinh_danh") for x in de_xuat]:
        u = str(u or "").strip().lstrip("@").lower()
        if u and u not in dang_theo_doi and u not in ra:
            ra.append(u)
        if len(ra) >= toi_da:
            break
    return ra


def chia_yeu_cau(n: int, tag: list[str], tac_gia: list[str], cid: dict,
                 uid: dict) -> tuple[dict[str, int], dict[str, int]]:
    """Chia `n` yêu cầu: ~`PHAN_TAG` cho hashtag (tìm cid nếu chưa nhớ + trang, chia vòng
    tròn tới `TAG_TRANG_TOI_DA` trang mỗi tag), phần còn lại (và phần tag không dùng hết) cho
    nhà sáng tạo (hồ sơ nếu chưa nhớ uid + `TAC_GIA_TRANG` trang). -> ({tag: trang},
    {tài khoản: trang})."""
    n_tag = math.ceil(n * PHAN_TAG) if tac_gia else n
    if not tag:
        n_tag = 0
    trang_tag: dict[str, int] = {}
    con = n_tag
    for t in tag:                           # mỗi tag cần cid + ít nhất 1 trang
        can = (0 if cid.get(t) else 1) + 1
        if can <= con:
            trang_tag[t] = 1
            con -= can
    while con > 0 and any(v < TAG_TRANG_TOI_DA for v in trang_tag.values()):
        for t in trang_tag:
            if con > 0 and trang_tag[t] < TAG_TRANG_TOI_DA:
                trang_tag[t] += 1
                con -= 1
    con += n - n_tag
    trang_tg: dict[str, int] = {}
    for u in tac_gia:
        can = (0 if uid.get(u) else 1) + TAC_GIA_TRANG
        if can <= con:
            trang_tg[u] = TAC_GIA_TRANG
            con -= can
        elif con >= (0 if uid.get(u) else 1) + 1:
            trang_tg[u] = con - (0 if uid.get(u) else 1)
            con = 0
    return trang_tag, trang_tg


# ───────────────────────────── số đo ─────────────────────────────
def _thao_luan(d: dict) -> int:
    try:
        return 1 + max(0, int(d.get("comments") or 0))
    except (TypeError, ValueError):
        return 1


#: Mã lý do sót → câu hiện cho người xem. Mã quyết định Mark tự sửa gì (`hanh_dong`).
LY_DO = {"chi_hashtag": "chỉ nhắc brand qua hashtag — tìm theo từ khoá xếp thấp",
         "ngoai_cua_so": "đăng {ngay} ngày trước — ngoài cửa sổ 'tuần này' của lượt tìm",
         "it_thich": "ít lượt thích — lượt nổi (nhiều thích) không với tới",
         "tac_gia_moi": "nhà sáng tạo chưa có bài nào trong kho",
         "khac": "tìm theo từ khoá không trả về bài này"}
#: Lý do kiểu "tụt hạng" (tìm có thể trả về nhưng bài nằm quá sâu) → nới lượt nổi. KHÔNG gồm
#: `it_thich` (review M3): thêm trang "nhiều thích" không với tới bài ít thích — bài đó chỉ lấp
#: được qua feed hashtag (hashtag lượt nổi) hoặc tìm theo ngày, nên không đẩy lượt nổi lên mãi.
LY_DO_TUT_HANG = ("chi_hashtag", "ngoai_cua_so")


def ma_ly_do(d: dict, dt: datetime.datetime | None, tu: list[str], tac_gia_kho: set[str],
             bay_gio: datetime.datetime) -> list[str]:
    """Mã lý do CÓ LẼ bị sót (≤ 2, suy từ dữ liệu bài — không chắc chắn)."""
    ra = []
    chu = re.sub(r"#\S+", " ", str(d.get("text") or ""))
    if not A._khop_tu_khoa({"text": chu, "kenh": d.get("kenh"), "username": d.get("username")},
                           tu):
        ra.append("chi_hashtag")
    if dt and bay_gio - dt > datetime.timedelta(days=NGAY_CUA_SO):
        ra.append("ngoai_cua_so")
    if int(d.get("likes") or 0) < IT_THICH:
        ra.append("it_thich")
    if str(d.get("username") or "").lower() not in tac_gia_kho:
        ra.append("tac_gia_moi")
    return ra[:2] or ["khac"]


def ly_do_sot(d: dict, dt: datetime.datetime | None, tu: list[str], tac_gia_kho: set[str],
              bay_gio: datetime.datetime) -> list[str]:
    """Câu lý do (theo `ma_ly_do`)."""
    ngay = (bay_gio - dt).days if dt else 0
    return [LY_DO[m].format(ngay=ngay) for m in ma_ly_do(d, dt, tu, tac_gia_kho, bay_gio)]


def tinh_do_phu(mau: list[dict]) -> dict:
    """Số đo trên các bài mẫu đã đánh dấu (`nhac`, `da_co`, `da_loai`, `tl`). Bài AI đã loại
    trước không vào mẫu số (đã thấy, cố ý bỏ — không phải lỗ thu thập)."""
    nhac = [x for x in mau if x["nhac"] and not x["da_loai"]]
    co = [x for x in nhac if x["da_co"]]
    tl, tl_co = sum(x["tl"] for x in nhac), sum(x["tl"] for x in co)
    return {"so_mau": len(mau), "so_nhac": len(nhac), "so_da_co": len(co),
            "so_da_loai": sum(1 for x in mau if x["nhac"] and x["da_loai"]),
            "so_sot": len(nhac) - len(co), "thao_luan_nhac": tl, "thao_luan_da_co": tl_co,
            "do_phu": round(100.0 * len(co) / len(nhac), 2) if nhac else None,
            "do_phu_tl": round(100.0 * tl_co / tl, 2) if tl else None}


# ───────────────────────────── lấy mẫu (gọi API) ─────────────────────────────
def lay_mau(trang_tag: dict[str, int], trang_tg: dict[str, int], cid: dict, uid: dict,
            ngan, d_from: datetime.datetime) -> tuple[list[tuple[dict, str]], dict]:
    """Gọi TikTok API theo kế hoạch. -> ([(item kiểu clockworks, đường)], thống kê từng
    tag / người: {"tag": {t: {"cid", "bai", "loi"}}, "tac_gia": {u: {...}}, "dung": mã}).
    KHÔNG ném lỗi Apify: lỗi một tag / một người ghi vào `loi` của nó, phần khác (đã trả tiền)
    giữ nguyên; HET_TIEN_THANG / DA_HUY thì khoá bộ đếm (`dung`) — không gửi thêm yêu cầu."""
    tk: dict = {"tag": {}, "tac_gia": {}}

    def loi(x: dict, e: Exception) -> None:
        x["loi"] = A._che_token(f"{getattr(e, 'ma', type(e).__name__)}: {e}")[:120]
        if getattr(e, "ma", "") in TT._DUNG_HAN:
            tk["dung"] = e.ma
            ngan.dung = e.ma
            ngan.toi_da = 0

    def mot_tag(t: str) -> list[tuple[dict, str]]:
        x = tk["tag"].setdefault(t, {"cid": cid.get(t), "bai": 0, "loi": ""})
        try:
            if not x["cid"]:
                x["cid"] = TT.tim_cid(t, ngan)
                if not x["cid"]:
                    x["loi"] = "không thấy hashtag"
                    return []
            items = TT.bai_hashtag(x["cid"], trang_tag[t], ngan)
        except A.LoiApify as e:
            loi(x, e)
            return []
        x["bai"] = len(items)
        return [(it, f"#{t}") for it in items]

    def mot_nguoi(u: str) -> list[tuple[dict, str]]:
        x = tk["tac_gia"].setdefault(u, {"uid": uid.get(u), "bai": 0, "loi": ""})
        try:
            items, x["uid"] = TT.bai_tai_khoan(u, trang_tg[u], ngan, uid=x["uid"], d_from=d_from)
        except A.LoiApify as e:
            loi(x, e)
            return []
        if not x["uid"]:
            x["loi"] = "không thấy tài khoản"
        x["bai"] = len(items)
        return [(it, f"@{u}") for it in items]

    ra = [y for ds in TT._song_song(mot_tag, list(trang_tag)) for y in ds]
    ra += [y for ds in TT._song_song(mot_nguoi, list(trang_tg)) for y in ds]
    if getattr(ngan, "dung", None) and not tk.get("dung"):
        tk["dung"] = ngan.dung              # trang sau gặp hết tiền / huỷ (đã khoá bộ đếm)
    return ra, tk


def danh_dau(ma: str, items: list[tuple[dict, str]], du_an: dict, tu: list[str],
             tu_pv: datetime.datetime, bay_gio: datetime.datetime, khoa_cua) -> list[dict]:
    """Item → bài mẫu (bỏ trùng theo khoá, gộp đường) trong `NGAY_MAU` ngày và trong phạm vi
    theo dõi, đánh dấu nhắc brand / đã có trong kho / AI đã loại trước."""
    import loc_rac
    import theo_doi_api as TDA
    moc = max(tu_pv, bay_gio - datetime.timedelta(days=NGAY_MAU))
    loai_tru = [str(x) for x in du_an.get("tu_loai_tru") or [] if str(x).strip()]
    theo: dict[str, dict] = {}
    for it, duong in items:
        for d, dt in A._chuan_tiktok(A._chuan_clockworks([it])):
            if not d.get("link") or not dt or not (moc <= dt <= bay_gio + datetime.timedelta(
                    hours=1)):
                continue
            d["platform"] = "tiktok"
            k = khoa_cua(d)
            if k in theo:
                if duong not in theo[k]["duong"]:
                    theo[k]["duong"].append(duong)
                continue
            nhac = (A._khop_tu_khoa(d, tu) and not A._tu_loai_tru_khop(d, loai_tru)
                    and not loc_rac.bai_spam(f"{d.get('text') or ''} {d.get('hashtags') or ''}"))
            theo[k] = {"khoa": k, "d": d, "dt": dt, "duong": [duong], "nhac": bool(nhac),
                       "tl": _thao_luan(d), "da_co": False, "da_loai": False}
    if theo:
        co = K.khoa_da_co(ma, list(theo))
        loai = TDA.doc_loai(ma, TDA.dau_loai(du_an, tu), tu_pv)
        for k, x in theo.items():
            x["da_co"], x["da_loai"] = k in co, k in loai
    return list(theo.values())


def bai_sot(mau: list[dict], tu: list[str], tac_gia_kho: set[str],
            bay_gio: datetime.datetime, toi_da: int | None = SOT_TOI_DA) -> list[dict]:
    """Bài brand chưa có trong kho, nhiều thảo luận nhất trước (≤ `toi_da`; None = hết)."""
    sot = [x for x in mau if x["nhac"] and not x["da_co"] and not x["da_loai"]]
    sot.sort(key=lambda x: (-x["tl"], x["khoa"]))
    ra = []
    for x in sot[:toi_da]:
        d = x["d"]
        ra.append({"khoa": x["khoa"], "link": d.get("link"), "tai_khoan": d.get("username") or "",
                   "ten": str(d.get("kenh") or "")[:120], "thao_luan": x["tl"],
                   "binh_luan": int(d.get("comments") or 0), "thich": int(d.get("likes") or 0),
                   "xem": int(d.get("views") or 0),
                   "dang_luc": x["dt"].isoformat(timespec="minutes") if x["dt"] else None,
                   "noi_dung": str(d.get("text") or "")[:200], "duong": x["duong"][:3],
                   "ma_ly_do": ma_ly_do(d, x["dt"], tu, tac_gia_kho, bay_gio),
                   "ly_do": ly_do_sot(d, x["dt"], tu, tac_gia_kho, bay_gio),
                   "tag": _tag_cua(d.get("hashtags") or "")[:10],
                   "bo_sung": False, "hanh_dong": []})
    return ra


# ───────────────────────────── tự sửa đường thu thập (chủ dự án 17/10) ─────────────────────────────
# "Không chỉ đo": mỗi bài sót, ngoài việc đưa qua phễu (bổ sung), Mark sửa CHÍNH đường thu thập theo
# lý do sót và ghi lại đã làm gì (`kiem_do_phu.hanh_dong` + từng bài sót):
#   • nhà sáng tạo chưa theo dõi → ĐỀ XUẤT nguồn (bảng `de_xuat`, người duyệt trên dashboard —
#     Mark không có quyền tự thêm nguồn); thảo luận sót ≥ `DE_XUAT_MANH` thì đề xuất ƯU TIÊN;
#   • hashtag chiến dịch/brand chưa được tìm → thêm vào danh sách hashtag của LƯỢT NỔI (tìm theo
#     từ đó, sắp nhiều thích, 30 ngày) — lưu trong sổ mốc của Mark (`KHOA_NOI_CFG`; Mark không
#     sửa được `du_an.cau_hinh`), bản chụp nằm ở `kiem_do_phu.hanh_dong` cho dashboard;
#   • tụt hạng (chỉ hashtag / ngoài cửa sổ tuần / ít thích) → nới lượt nổi: thêm trang mỗi từ, đã
#     tối đa thì dày nhịp — vẫn trong trần lượt nổi (phần ước tính TikTok chưa dùng, phần còn của
#     tháng: `theo_doi_api.tran_noi`). Lần kiểm sau tốt (≥ `TOT`) và hết tụt hạng thì lùi một nấc.
KHOA_NOI_CFG = "tiktok_noi_cfg"   # khoá trong sổ mốc tìm theo từ khoá
DE_XUAT_MANH = 500           # thảo luận sót của một người → đề xuất ưu tiên
TAG_NOI_TOI_DA = 4
NOI_TRANG_TOI_DA = 4
NOI_GIO_TOI_THIEU = 10
TUT_HANG_TOI_THIEU = 2       # ≥ 2 bài sót kiểu tụt hạng, hoặc ≥ 25% thảo luận sót
TOT = 90.0                   # độ phủ theo thảo luận ≥ mức này HAI lần liền: lùi một nấc
#: Giá THẬT một yêu cầu TikTok API (đo 17/10/2026 trên gói FREE: 0,0023–0,0034 USD, phí nền
#: tảng mỗi run) — kiểm độ phủ chia số yêu cầu + ghi sổ theo mức cao này (review LOW).
GIA_YEU_CAU_THAT = 0.0034


def cau_hinh_noi(cfg: dict | None) -> dict:
    """Cấu hình lượt nổi hiệu lực (mặc định của `theo_doi_api` khi Mark chưa nới gì)."""
    import theo_doi_api as TDA
    x = cfg if isinstance(cfg, dict) else {}

    def so(k, md, lo, hi):
        try:
            return max(lo, min(hi, int(x.get(k, md))))
        except (TypeError, ValueError):
            return md
    tag = ([TT.chuan_tag(t) for t in x["tag"] if TT.chuan_tag(t)]
           if isinstance(x.get("tag"), list) else [])
    return {"trang": so("trang", TDA.NOI_TRANG, TDA.NOI_TRANG, NOI_TRANG_TOI_DA),
            "gio": so("gio", TDA.NOI_GIO_GIAN, NOI_GIO_TOI_THIEU, TDA.NOI_GIO_GIAN),
            "tag": list(dict.fromkeys(tag))[:TAG_NOI_TOI_DA]}


def hanh_dong(sot: list[dict], tu: list[str], dang_theo_doi: set[str], noi_cfg: dict | None,
              do_phu_tl: float | None, bay_gio: datetime.datetime,
              tl_truoc: float | None = None) -> dict:
    """Việc Mark tự làm cho các bài sót (TẤT CẢ, không chỉ 10 bài hiện); ghi câu vào `hanh_dong`
    của từng bài. `tl_truoc`: độ phủ theo thảo luận của lần kiểm trước (lùi nấc lượt nổi khi
    HAI lần liền ≥ `TOT`). -> {"de_xuat": [dòng cho `lang_nghe_db.ghi_de_xuat`], "noi_cfg": cấu
    hình lượt nổi mới, "tom": bản tóm tắt lưu bảng}."""
    import theo_doi_api as TDA
    ngay = bay_gio.astimezone(_VN).strftime("%d/%m")
    # 1. Nhà sáng tạo chưa theo dõi → đề xuất (gộp theo người).
    nguoi: dict[str, dict] = {}
    for s in sot:
        u = str(s.get("tai_khoan") or "").strip().lstrip("@").lower()
        if not u or u in dang_theo_doi:
            continue
        g = nguoi.setdefault(u, {"nen_tang": "tiktok", "dinh_danh": u,
                                 "link": f"https://www.tiktok.com/@{u}",
                                 "ten": str(s.get("ten") or u)[:200], "so_bai": 0, "thao_luan": 0})
        g["so_bai"] += 1
        g["thao_luan"] += int(s.get("thao_luan") or 0)
    de_xuat = sorted(nguoi.values(), key=lambda g: (-g["thao_luan"], g["dinh_danh"]))
    for g in de_xuat:
        g["uu_tien"] = g["thao_luan"] >= DE_XUAT_MANH
        g["ly_do"] = (("ƯU TIÊN theo dõi — " if g["uu_tien"] else "")
                      + f"kiểm độ phủ {ngay}: {g['so_bai']} bài brand bị sót, "
                      f"{g['thao_luan']} thảo luận")[:300]
    # 2. Hashtag chiến dịch/brand của bài sót → danh sách hashtag lượt nổi.
    cu = cau_hinh_noi(noi_cfg)
    goc = [TT.chuan_tag(t) for t in tu if TT.chuan_tag(t)]
    diem: Counter = Counter()
    dem: Counter = Counter()
    for s in sot:
        for t in s.get("tag") or []:
            if t in TAG_CHUNG or t in goc or not 3 <= len(t) <= 40:
                continue
            diem[t] += int(s.get("thao_luan") or 0)
            dem[t] += 1
    nhan = [t for t in sorted(diem, key=lambda t: (-diem[t], t))
            if dem[t] >= 2 or diem[t] >= DE_XUAT_MANH or any(g in t for g in goc)]
    tag_moi = list(dict.fromkeys(nhan + cu["tag"]))[:TAG_NOI_TOI_DA]
    them_tag = [t for t in tag_moi if t not in cu["tag"]]
    # 3. Hai lần kiểm liền tốt (≥ `TOT`) → lùi một nấc (review M3: không chờ hết sót); còn tụt
    #    hạng đáng kể → nới lượt nổi.
    tut = [s for s in sot if set(s.get("ma_ly_do") or []) & set(LY_DO_TUT_HANG)]
    tl_sot = sum(int(s.get("thao_luan") or 0) for s in sot)
    tl_tut = sum(int(s.get("thao_luan") or 0) for s in tut)
    trang, gio = cu["trang"], cu["gio"]
    ly = ""
    tot = (do_phu_tl is not None and do_phu_tl >= TOT and tl_truoc is not None
           and float(tl_truoc) >= TOT)
    if tot and (trang > TDA.NOI_TRANG or gio < TDA.NOI_GIO_GIAN):
        if gio < TDA.NOI_GIO_GIAN:
            gio = min(TDA.NOI_GIO_GIAN, gio * 2)
        else:
            trang -= 1
        ly = f"độ phủ tốt hai lần liền — lùi lượt nổi về {trang} trang/từ khoá, mỗi {gio} giờ"
    elif not tot and tut and (len(tut) >= TUT_HANG_TOI_THIEU
                              or tl_tut >= 0.25 * max(1, tl_sot)):
        if trang < NOI_TRANG_TOI_DA:
            trang += 1
            ly = f"nới lượt nổi lên {trang} trang/từ khoá ({len(tut)} bài sót do tụt hạng)"
        elif gio > NOI_GIO_TOI_THIEU:
            gio = max(NOI_GIO_TOI_THIEU, gio // 2)
            ly = f"lượt nổi dày lên mỗi {gio} giờ ({len(tut)} bài sót do tụt hạng)"
    noi_moi = {"trang": trang, "gio": gio, "tag": tag_moi,
               "luc": bay_gio.isoformat(timespec="seconds"), "ly_do": ly}
    doi_noi = trang != cu["trang"] or gio != cu["gio"]
    # Câu "Mark đã làm gì" trên từng bài.
    for s in sot:
        u = str(s.get("tai_khoan") or "").strip().lstrip("@").lower()
        hd = s.setdefault("hanh_dong", [])
        if u in nguoi:
            hd.append(f"đề xuất theo dõi @{u}" + (" (ưu tiên)" if nguoi[u]["uu_tien"] else ""))
        elif u:
            hd.append(f"@{u} đã là nguồn theo dõi")
        tg = [t for t in s.get("tag") or [] if t in tag_moi]
        if tg:
            hd.append("tìm #" + ", #".join(tg[:2]) + " trong lượt nổi")
        if doi_noi and any(s is x for x in tut):
            hd.append(ly.split(" (")[0])
    tom = {"de_xuat": [{k: g[k] for k in ("dinh_danh", "so_bai", "thao_luan", "uu_tien")}
                       for g in de_xuat],
           "tag_noi": tag_moi, "tag_them": them_tag,
           "noi": {"trang": [cu["trang"], trang], "gio": [cu["gio"], gio], "ly_do": ly}}
    return {"de_xuat": [{k: v for k, v in g.items() if k != "uu_tien"} for g in de_xuat],
            "noi_cfg": noi_moi, "tom": tom}


def cau_hanh_dong(tom: dict | None) -> str:
    """Một câu "Mark đã làm gì" cho ghi chú lượt + tin nhắn kết quả."""
    if not tom:
        return ""
    ra = []
    dx = tom.get("de_xuat") or []
    if dx:
        ut = sum(1 for g in dx if g.get("uu_tien"))
        ra.append(f"đề xuất theo dõi {len(dx)} nhà sáng tạo" + (f" ({ut} ưu tiên)" if ut else ""))
    if tom.get("tag_them"):
        ra.append("thêm #" + ", #".join(tom["tag_them"]) + " vào lượt nổi")
    if (tom.get("noi") or {}).get("ly_do"):
        ra.append(tom["noi"]["ly_do"])
    return "; ".join(ra)


def cau_ghi_chu(dp: dict) -> list[str]:
    """Câu cho `luot_quet.ghi_chu` (đứng TRƯỚC các dòng phễu dài) + tin nhắn kết quả."""
    if not dp:
        return []
    if dp.get("bo_qua"):
        return [f"kiểm độ phủ: bỏ qua ({dp['bo_qua']})"]
    so = dp.get("so") or {}
    if not so:
        return list(dp.get("ghi_chu") or [])

    def pt(x):
        return "—" if x is None else f"{x:.0f}%"
    m = dp.get("mau") or {}
    return [f"kiểm độ phủ (TikTok: {len(m.get('tag') or [])} hashtag + "
            f"{len(m.get('tac_gia') or [])} nhà sáng tạo, {so.get('so_mau', 0)} bài mẫu, "
            f"{dp.get('so_yeu_cau', 0)} yêu cầu, {dp.get('usd', 0):.3f} USD): "
            f"{so.get('so_da_co', 0)}/{so.get('so_nhac', 0)} bài nhắc brand đã có "
            f"({pt(so.get('do_phu'))}), theo thảo luận {pt(so.get('do_phu_tl'))}; sót "
            f"{so.get('so_sot', 0)}, bổ sung {dp.get('bo_sung', 0)}"
            + (f", AI đã loại trước {so['so_da_loai']}" if so.get("so_da_loai") else "")
            + (f"; Mark đã làm: {cau_hanh_dong(dp.get('hanh_dong'))}"
               if cau_hanh_dong(dp.get("hanh_dong")) else "")
            ] + list(dp.get("ghi_chu") or [])
