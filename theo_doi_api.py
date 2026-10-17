"""Phần mở rộng của `/theodoi` (16/10/2026) — tách khỏi theo_doi.py cho các nhánh khác sửa
theo_doi ít đụng nhau. Hai việc:

1. PHẦN NHIỀU YÊU CẦU qua TikTok API (`tiktok_api`): hồ sơ nguồn TikTok và bình luận TikTok.
   Một phần = nhiều run Apify (mỗi yêu cầu API một run); id nằm ở `run_phu` của phần
   (`viec_nen.run_ids` cộng vào tiền thật). Bot khởi động lại giữa phần thì CHẠY LẠI phần đó
   (khác kỷ luật "không gửi lại" của actor thường: mỗi yêu cầu ~0,003 USD, chạy lại cả phần chỉ
   vài cent; id run cũ vẫn nằm trong `run_phu` nên tiền cũ vẫn được chốt). Nguồn / video API
   không ra gì thì chạy actor cũ (clockworks) cho đúng phần thiếu, trong phần trần còn lại.

2. TÌM THEO TỪ KHOÁ: TÁCH "PHÁT HIỆN" KHỎI "CẬP NHẬT" (chủ dự án 16/10: "những khoảng thời
   gian trong chiến dịch thì cào ra những bài đó phải cập nhật chứ"). Trước đây mọi bài ngày
   đăng ngoài cửa sổ tăng dần (3 ngày) bị BỎ — kể cả bài đã có trong kho: lượt 6 trả tiền 252
   bài, giữ 39. Nay:
   • PHẠM VI theo dõi (`pham_vi`): 30 ngày, nới tới đầu mọi chiến dịch (`lich_quet` kiểu
     chien_dich) đang chạy hoặc kết thúc trong 30 ngày, tối đa 92 ngày. Bài trong phạm vi đều
     dùng: bài ĐÃ CÓ → cập nhật số liệu + ảnh chụp ngày (`chi_so_ngay`); bài MỚI → lọc như cũ
     (từ loại trừ, spam, AI). Chỉ bài cũ hơn phạm vi mới bỏ ("ngoài phạm vi").
   • Mốc tăng dần không còn quyết định GIỮ gì mà quyết định XIN bao nhiêu: cửa sổ ngày gửi bộ
     lọc ngày phía server (TikTok API, Facebook) và cỡ xin co giãn theo lượt trước (`so_xin`).
   • Bài quan trọng mà tìm không trả lại nữa: làm mới số liệu N bài TikTok nhiều tương tác nhất
     trong phạm vi qua TikTok API theo link (0,003 USD/bài — `lam_moi_tiktok`).
"""
from __future__ import annotations

import datetime
import math
import re
import threading
import time

import apify_tool as A
import lang_nghe_db as K
import tiktok_api as TT

_VN = datetime.timezone(datetime.timedelta(hours=7))
_KHONG_DU_PHONG = ("HET_TIEN_THANG", "DA_HUY", "QUA_GIO", "NGHEN_DONG_THOI")
_GIA_DU_PHONG = {"tiktok_ho_so": 0.003, "tiktok_binh_luan": 0.00125}   # clockworks, gói FREE


# ───────────────────────────── 1. phần nhiều yêu cầu ─────────────────────────────
def gan_ho_so(ph: dict, ten: list[str], n: int) -> None:
    """Phần hồ sơ TikTok đi qua TikTok API (giữ actor/payload cũ làm dự phòng)."""
    if TT.dung_api("tiktok_ho_so"):
        ph["du_phong"] = {"actor": ph["actor"], "gia": _GIA_DU_PHONG["tiktok_ho_so"]}
        ph.update(actor=TT.ACTOR, bo_chuyen="tiktok_ho_so", ten=list(ten))


def gan_binh_luan(ph: dict, urls: list[str], tra_loi: int) -> None:
    """Phần bình luận TikTok đi qua TikTok API (actor cũ của phần làm dự phòng)."""
    if TT.dung_api("tiktok_binh_luan") and ph.get("actor"):
        ph["du_phong"] = {"actor": ph["actor"], "gia": _GIA_DU_PHONG["tiktok_binh_luan"]}
        ph.update(actor=TT.ACTOR, bo_chuyen="tiktok_binh_luan", urls=list(urls),
                  tra_loi=int(tra_loi))


def tien_phan(p: str, ph: dict, items: list, meta: dict) -> float:
    """USD theo sổ của một phần: phần bộ chuyển lấy tiền đã đếm theo yêu cầu (+ dự phòng)."""
    if ph.get("bo_chuyen"):
        return round(float(meta.get("usd") or 0), 4)
    import quet_lon
    return quet_lon._so_tien(p, ph, items, meta)


def _thieu(ph: dict, loi_ra: list) -> list[str]:
    """Tài khoản / video API báo LỖI (không phải "đọc được mà rỗng" — review 16/10: tài khoản 0
    video, video 0 bình luận không chạy dự phòng mỗi lượt), mà dự phòng có thể cứu được."""
    loi = {str(k).lstrip("@").lower() for k, ma, _ in loi_ra if ma not in _KHONG_DU_PHONG}
    ds = ph["ten"] if ph["bo_chuyen"] == "tiktok_ho_so" else ph["urls"]
    return [x for x in ds if str(x).lstrip("@").lower() in loi]


def _bo_cua(ph: dict, items: list, thieu: list[str]) -> list:
    """Bỏ dòng ghi chú của nguồn/video sắp chạy dự phòng (dự phòng ra gì thì thay vào)."""
    if ph["bo_chuyen"] == "tiktok_ho_so":
        th = {t.lstrip("@").lower() for t in thieu}
        return [it for it in items if str(it.get("input") or "").lower() not in th
                or it.get("webVideoUrl")]
    return items


def _du_phong(ph: dict, thieu: list[str], tran: float, han: float, p: str) -> tuple[list, dict]:
    import account_tool
    import deep_dive_tool as D
    import theo_doi
    n = int(ph.get("n") or ph.get("per") or 5)
    if ph["bo_chuyen"] == "tiktok_ho_so":
        pl, lim = account_tool._payload_tiktok(thieu, n), n * len(thieu)
    else:
        per = int(ph.get("per") or 20)
        pl = theo_doi._payload_bl("tiktok", thieu, per, bool(ph.get("day_du")))
        lim = D._limit("tiktok", thieu, per)
    return A._run_actor(ph["du_phong"]["actor"], pl, lim, None, han, 0, tran_usd=tran,
                        mot_phan=True, nen_tang=p)


def chay(v, p: str, ph: dict, cap: float, han: float):
    """Chạy một phần bộ chuyển. -> (items, meta, lỗi, None) như `theo_doi._chay_actor`."""
    t0 = time.monotonic()
    khoa = threading.Lock()

    def ghi_run(run, meta):
        with khoa:
            v.cap_nhat_phan(ph, run_phu=[*(ph.get("run_phu") or []), run.get("id")],
                            trang_thai="dang_chay")
    v.cap_nhat_phan(ph, trang_thai="dang_chay", tran_usd=cap)
    so: list = []
    dat = [(A._NEN_TANG, p), (A._HAN_CHOT, han), (A._KHI_CO_RUN, ghi_run), (A._SO_RUN, so)]
    moc = [(bien, bien.set(gt)) for bien, gt in dat]
    items: list = []
    loi = None
    usd_dp = 0.0
    loi_ra: list = []
    try:
        try:
            if ph["bo_chuyen"] == "tiktok_ho_so":
                items = TT.ho_so(ph["ten"], int(ph.get("n") or 5), tran_usd=cap, loi_ra=loi_ra)
            else:
                items = TT.binh_luan(ph["urls"], int(ph.get("per") or 20),
                                     int(ph.get("tra_loi") or 0), tran_usd=cap, loi_ra=loi_ra)
        except A.LoiApify as e:
            loi = e
        except Exception as e:
            if type(e).__name__ == "MatQuyen":
                raise
            loi = A.LoiApify("LOI", A._che_token(f"{type(e).__name__}: {e}")[:250])
        usd = sum(TT.GIA_YEU_CAU for m in so if isinstance(m, dict) and m.get("run_id"))
        thieu = _thieu(ph, loi_ra)
        con = cap - usd
        if loi is None and loi_ra and not thieu:
            loi = A.LoiApify(loi_ra[0][1], f"TikTok API: {loi_ra[0][2]}")
        if (thieu and ph.get("du_phong") and getattr(loi, "ma", "LOI") not in _KHONG_DU_PHONG
                and con >= A._TRAN_USD_KHOANG[0] and han - time.monotonic() > 30):
            tran_dp = math.floor(con * 100) / 100       # dự phòng chỉ tiêu PHẦN CÒN của trần
            try:
                dp, mdp = _du_phong(ph, thieu, tran_dp, han, p)
                # Sổ theo giá thật của actor cũ (Apify ghi tiền chậm: lấy số lớn hơn).
                usd_dp = max(float(mdp.get("usd") or 0), len(dp) * ph["du_phong"]["gia"])
                if dp:
                    items = _bo_cua(ph, items, thieu) + dp
                else:
                    loi = loi or A.LoiApify(loi_ra[0][1], f"TikTok API: {loi_ra[0][2]}")
            except A.LoiApify as e:
                # Không biết dự phòng đã tiêu bao nhiêu: tính nguyên trần của nó.
                usd_dp = float(e.meta.get("usd") or tran_dp)
                loi = loi or e
    finally:
        for bien, t in reversed(moc):
            bien.reset(t)
    mot_phan = any(isinstance(m, dict) and m.get("ma") in ("QUA_GIO", "OK_MOT_PHAN")
                   for m in so) or bool(loi and items)
    meta = {"actor": TT.ACTOR, "ma": "OK_MOT_PHAN" if mot_phan else "OK", "run_id": None,
            "usd": round(usd + usd_dp, 4), "so_item": len(items),
            "giay": round(time.monotonic() - t0, 1)}
    if loi is not None and not items:
        meta.update(ma=loi.ma, ly_do=str(loi)[:300])
    return items, meta, (loi if not items else None), None


# ─────────────── 1b. theo dõi TRANG Facebook: thedoor + actor cũ dự phòng (17/10/2026) ───────────────
# Đo thật vòng 2 (17/10/2026, `hapasglobal`, 20 bài mới nhất, cùng đầu vào cho ba actor): thedoor trả
# ĐÚNG 20 bài như actor đang dùng (apify~facebook-posts-scraper), CÓ lượt xem video (10/10 bài
# video/reel, 4.359–448.884 view — hai actor rẻ hơn không có), hợp tác, id bài SỐ; giá 0,0025 USD/bài
# (FREE; Starter 0,00199) so với 0,005 của apify; một run nhận NHIỀU trang (`pageUrls`). Rủi ro: phí
# khởi động 0,01 USD/run mới thêm 15/10/2026 (`pricingInfos`) và 1,3k người dùng → giữ actor cũ làm
# DỰ PHÒNG: trang nào thedoor lỗi / không ra bài thì chạy actor cũ cho đúng trang đó, trong phần
# trần còn lại của phần (như dự phòng hồ sơ TikTok ở trên).
FB_TRANG = "thedoor~facebook-page-scraper"
FB_TRANG_GIA = 0.0025        # USD/bài, gói FREE (`apify-default-dataset-item`)
FB_TRANG_KHOI = 0.01         # USD/run (`apify-actor-start`, 1 GB)
FB_DU_PHONG_GIA = 0.005      # apify~facebook-posts-scraper, gói FREE (sự kiện "post")
FB_DU_PHONG_KHOI = 0.001     # sự kiện "actor-start"


def gan_fb_trang(ph: dict, urls: list[str], n: int) -> None:
    """Phần theo dõi trang Facebook đi thedoor; actor + payload cũ của phần làm dự phòng. Cố ý
    KHÔNG gửi `postsNewerThan`: như actor cũ, mỗi trang trả `n` bài MỚI NHẤT bất kể ngày — trang
    0 bài khi đó mới đúng là lỗi (đáng chạy dự phòng), không lẫn với trang lâu không đăng.
    `du_phong.uoc_usd` = dự phòng cho MỌI trang (thedoor hỏng cả run) — `theo_doi._tran_phan`
    chừa chỗ cho nó trong trần phần (dự phòng chạy TRONG phần, tiêu phần trần còn lại)."""
    ph["du_phong"] = {"actor": ph["actor"], "payload": ph["payload"], "gia": FB_DU_PHONG_GIA,
                      "khoi": FB_DU_PHONG_KHOI}
    ph["du_phong"]["uoc_usd"] = can_du_phong_fb(ph["du_phong"], len(urls), int(n))
    ph.update(actor=FB_TRANG, gia=FB_TRANG_GIA, khoi=FB_TRANG_KHOI, urls=list(urls),
              payload={"pageUrls": list(urls), "postsToScrape": int(n)})


def la_thedoor(it) -> bool:
    return isinstance(it, dict) and isinstance(it.get("post"), dict) \
        and isinstance(it.get("page"), dict)


def _so_fb(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _ten_trang(*urls) -> str:
    """Tên trang Facebook trong link đầu tiên có tên ("facebook.com/hapasglobal" → "hapasglobal");
    bỏ link id số / profile.php / đường dẫn chung (`khu_trung_fb._SLUG_CHUNG`). Không có → ""."""
    import khu_trung_fb as KT
    for u in urls:
        m = re.search(r"facebook\.com/([^/?#]+)", str(u or ""), re.IGNORECASE)
        if m and not m.group(1).isdigit() and m.group(1).lower() not in KT._SLUG_CHUNG:
            return m.group(1)
    return ""


def doc_thedoor(items: list, urls: list[str]) -> dict[str, dict]:
    """Item thedoor -> {trang: {"ho_so", "bai", "ghi_chu"}} CÙNG dạng `account_tool._doc_facebook`
    để `theo_doi._dong_tu_tai_khoan` / `ghep_nguon` dùng nguyên. Trường theo run thật 17/10/2026:
    `post` {id SỐ, url `/<id trang>/posts/<id bài>`, text, hashtags}, `page` {id, name, url},
    `created.timestamp` (giây), `engagement` {reactions, comments, shares, views (chỉ video)},
    `video.is_video`, `partnership` {paid, collaborators}. Actor không có URL đầu vào trong item:
    trang ghép về URL nguồn theo `page.url` (chuẩn hoá như định danh nguồn), rồi theo id trang có
    trong URL nguồn, run một trang thì về trang đó. `_goc` thêm `postId` (id số, cho `_goc_id` /
    `ma_so_fb`) và `inputUrl` (URL nguồn đã ghép)."""
    import theo_doi as T
    theo = {T._chuan_dinh_danh("facebook", u): u for u in urls}
    ra: dict[str, dict] = {}
    for it in items:
        if not la_thedoor(it):
            continue
        po, pg = it["post"], it["page"]
        vao = theo.get(T._chuan_dinh_danh("facebook", str(pg.get("url") or "")))
        if vao is None and pg.get("id"):
            vao = next((u for u in urls if str(pg["id"]) in u), None)
        if vao is None and len(urls) == 1:
            vao = urls[0]
        # Gom theo TRANG (URL nguồn đã ghép / URL trang / id trang), không theo tên hiển thị — soát
        # 17/10/2026: hai trang khác nhau cùng tên "HAPAS" trong một run dùng chung hồ sơ (tên,
        # link, tai_khoan của trang đầu) cho bài của cả hai.
        k = (T._chuan_dinh_danh("facebook", vao or str(pg.get("url") or ""))
             or str(pg.get("id") or pg.get("name") or "").lower())
        # `tai_khoan` = tên trang trong link ("hapasglobal") như `pageName` của actor cũ, không
        # phải tên hiển thị ("HAPAS"): kho nhận bản trùng bài pfbid cũ theo chủ bài + phút + nội
        # dung (`khu_trung_fb.chu_bai`), mà link thedoor mang id SỐ của trang thay vì tên trang.
        tk = ra.setdefault(k, {"ho_so": {
            "ten": pg.get("name") or k,
            "tai_khoan": _ten_trang(pg.get("url"), vao) or pg.get("name") or k, "followers": None,
            "link": pg.get("url") or vao or ""}, "bai": [], "ghi_chu": ""})
        eg = it.get("engagement") if isinstance(it.get("engagement"), dict) else {}
        vd = it.get("video") if isinstance(it.get("video"), dict) else {}
        media = [m.get("__typename") for m in it.get("media") or [] if isinstance(m, dict)]
        cr = it.get("created") if isinstance(it.get("created"), dict) else {}
        hop = it.get("partnership") if isinstance(it.get("partnership"), dict) else {}
        txt = str(po.get("text") or "")
        tags = [str(h).lstrip("#") for h in po.get("hashtags") or [] if h]
        tk["bai"].append({
            "ngay": A._to_vn(cr.get("timestamp")),
            "loai": "video" if vd.get("is_video") or "Video" in media else "bài",
            "view": _so_fb(eg.get("views")) or None, "like": _so_fb(eg.get("reactions")),
            "binh_luan": _so_fb(eg.get("comments")), "share": _so_fb(eg.get("shares")),
            "noi_dung": txt, "link": str(po.get("url") or ""),
            "hashtag": tags or re.findall(r"#(\w+)", txt),
            "am_thanh": "", "tra_tien": bool(hop.get("paid")),
            "dong_tac_gia": [c.get("name") for c in hop.get("collaborators") or []
                             if isinstance(c, dict) and c.get("name")],
            "_goc": {**it, "postId": str(po.get("id") or ""), "inputUrl": vao or ""},
        })
    return ra


def doc_fb_trang(items: list, urls: list[str]) -> dict[str, dict]:
    """Kết quả một phần trang Facebook (thedoor, có thể kèm bài của actor dự phòng) -> dạng
    `account_tool._doc_facebook`. Item không mang shape của actor nào thì bỏ."""
    import account_tool
    ra = doc_thedoor([it for it in items if la_thedoor(it)], urls)
    cu = [it for it in items if isinstance(it, dict) and not la_thedoor(it)
          and (it.get("pageName") or it.get("facebookUrl") or it.get("postId"))]
    for k, tk in account_tool._doc_facebook(cu).items():
        if k in ra:
            ra[k]["bai"].extend(tk["bai"])
        else:
            ra[k] = tk
    return ra


def can_du_phong_fb(dp: dict, so_trang: int, n: int) -> float:
    """USD phải còn trong trần phần để chạy actor dự phòng cho `so_trang` trang × `n` bài: giá
    thật của actor cũ (bài × 0,005 + khởi động 0,001) nhân hệ số ước tính. Soát 17/10/2026: bản
    trước so phần còn với SÀN 0,1 USD của `_run_actor` — thedoor lỗi sau khi tạo run (đã tính
    0,01 khởi động) thì phần dưới ~19 bài (trần 0,1) chỉ còn 0,09 < 0,1 và dự phòng KHÔNG BAO
    GIỜ chạy, đúng lúc cần nhất. Sàn 0,1 chỉ là `maxTotalChargeUsd` gửi Apify; tiền thật của
    actor cũ bị `maxItems` (= n × số trang) chặn, nên mức cần thật là con số này."""
    import theo_doi as T
    return round((so_trang * n * float(dp.get("gia") or FB_DU_PHONG_GIA)
                  + float(dp.get("khoi") or 0)) * T._HE_SO_UOC, 4)


def ly_do_trang_fb(u: str, kq: dict, loi=None) -> str | None:
    """Lý do một trang Facebook không có bài sau thedoor + dự phòng (`kq` = `meta["du_phong"]`
    của `du_phong_fb`) — đi vào `nguon.loi_cuoi`; None khi trang không thuộc diện dự phòng. Soát
    17/10/2026: lý do bỏ / lỗi của dự phòng chỉ nằm trong meta (không lưu), nguồn chỉ hiện
    "không lấy được bài nào" — chủ dự án không biết thedoor hỏng hay trang hỏng."""
    if not kq or (u not in (kq.get("trang") or []) and u not in (kq.get("bo_qua_trang") or [])):
        return None
    dau = "thedoor không ra bài" + (f" ({A._che_token(str(loi))[:80]})" if loi else "")
    ten = kq.get("actor") or "actor cũ"
    if u in (kq.get("bo_qua_trang") or []):
        return f"{dau}; dự phòng {ten} không chạy: {kq.get('bo_qua') or 'không rõ'}"[:200]
    if kq.get("loi"):
        return f"{dau}; dự phòng {ten} lỗi: {kq['loi']}"[:200]
    return (f"{dau}; dự phòng {ten} cũng không ra bài (trang riêng tư, đổi tên hoặc sai "
            "định danh?)")[:200]


def du_phong_fb(v, p: str, ph: dict, items: list, meta: dict, loi, cap: float,
                han: float) -> tuple[list, dict, object]:
    """Trang Facebook thedoor KHÔNG ra bài (lỗi cả run, hoặc trang không có bài) → actor cũ cho
    đúng các trang đó, trong phần trần còn lại. -> (items gộp, meta, lỗi). Run dự phòng ghi vào
    `run_phu` (tiền thật chốt theo run id), `du_phong_run` + `du_phong_trang` (khởi động lại thì
    ĐỌC TIẾP đúng run đó, không POST lại). Lỗi dừng cả lượt (hết tiền tháng, huỷ, hết giờ, nghẽn)
    thì không chạy dự phòng.

    Trần còn không đủ cho mọi trang thiếu (`can_du_phong_fb`): chạy cho số trang ĐẦU vừa phần còn
    lại, phần còn lại ghi `bo_qua_trang` + `bo_qua` (lý do). `meta["du_phong"]` = {"actor",
    "trang" (đã gửi dự phòng), "so_item", "bo_qua_trang", "bo_qua", "loi"} — bên gọi lưu vào phần
    và đưa lý do vào lỗi nguồn (`ly_do_trang_fb`)."""
    dp = ph.get("du_phong") or {}
    urls = list(ph.get("urls") or (ph.get("payload") or {}).get("pageUrls") or [])
    if not dp or not urls or getattr(loi, "ma", "") in _KHONG_DU_PHONG:
        return items, meta, loi
    co = {b["_goc"].get("inputUrl") for tk in doc_thedoor(items, urls).values()
          for b in tk["bai"]}
    thieu = [u for u in urls if u not in co]
    if not thieu:
        return items, meta, loi
    da = max(float(meta.get("usd") or 0),
             len(items) * FB_TRANG_GIA + (FB_TRANG_KHOI if meta.get("run_id") else 0.0))
    con = math.floor((cap - da) * 100 + 1e-9) / 100
    n = int(ph.get("n") or 5)
    kq: dict = {"actor": dp["actor"], "trang": [], "so_item": 0}
    if ph.get("du_phong_run"):
        gui = [u for u in (ph.get("du_phong_trang") or thieu) if u in thieu] or thieu
    elif han - time.monotonic() < 30:
        gui, kq["bo_qua"] = [], "hết giờ"
    else:
        k = len(thieu)
        while k and can_du_phong_fb(dp, k, n) > con + 1e-9:
            k -= 1
        gui = thieu[:k]
        if k < len(thieu):
            kq["bo_qua"] = (f"trần phần còn {con:.2f} USD, dự phòng cần "
                            f"{can_du_phong_fb(dp, k + 1, n):.4f} USD cho {k + 1} trang"
                            ).replace(".", ",")
    kq["trang"] = gui
    if len(gui) < len(thieu):
        kq["bo_qua_trang"] = [u for u in thieu if u not in gui]
    if not gui:
        return items, {**meta, "du_phong": kq}, loi
    import account_tool
    pl, lim = account_tool._payload_facebook(gui, n), n * len(gui)

    def ghi_run(run, m):
        v.cap_nhat_phan(ph, run_phu=[*(ph.get("run_phu") or []), run.get("id")],
                        du_phong_run=run.get("id"), du_phong_trang=list(gui))
    tok = A._KHI_CO_RUN.set(ghi_run)
    them, mdp, loi_dp = [], {}, None
    try:
        if ph.get("du_phong_run"):
            them, mdp = A._doc_tiep_run(ph["du_phong_run"], lim, han, True, dp["actor"])
        else:
            # `tran_usd` có thể < 0,1 (sàn của `_run_actor`): tiền thật vẫn ≤ `can_du_phong_fb`
            # vì `maxItems` = n × số trang gửi.
            them, mdp = A._run_actor(dp["actor"], pl, lim, None, han, 0, tran_usd=con,
                                     mot_phan=True, nen_tang=p)
    except A.LoiApify as e:
        loi_dp, mdp = e, e.meta
    finally:
        A._KHI_CO_RUN.reset(tok)
    usd_dp = max(float(mdp.get("usd") or 0),
                 len(them or []) * dp["gia"] + (dp["khoi"] if ph.get("du_phong_run") else 0.0))
    if loi_dp is not None and mdp.get("khong_kiem_duoc"):
        usd_dp = con                      # POST mơ hồ, không kiểm được: coi như đã tiêu trần
    kq["so_item"] = len(them or [])
    if loi_dp is not None:
        kq["loi"] = A._che_token(str(loi_dp))[:150]
    meta = {**meta, "usd": round(da + usd_dp, 4), "du_phong": kq}
    return list(items) + list(them or []), meta, loi


# ───────────────────────────── 2. tìm theo từ khoá ─────────────────────────────
NGAY_PHAM_VI = 30            # phạm vi theo dõi mặc định (ngày đăng)
NGAY_PHAM_VI_TOI_DA = 92     # nới theo chiến dịch nhưng không quá một quý
NGAY_CHIEN_DICH_GAN = 30     # chiến dịch kết thúc trong chừng này ngày vẫn nới phạm vi
XIN_TOI_THIEU = 10           # cỡ xin nhỏ nhất khi co lại theo lượt trước


def pham_vi(ma: str, bay_gio: datetime.datetime) -> tuple[datetime.datetime, int, str]:
    """(từ lúc — 0 giờ, số ngày, lý do) của phạm vi theo dõi: bài đăng từ mốc này trở đi được
    giữ/cập nhật. Không đọc được lịch thì mặc định 30 ngày."""
    tu = bay_gio - datetime.timedelta(days=NGAY_PHAM_VI)
    ly = f"{NGAY_PHAM_VI} ngày"
    try:
        from dashboard import lich_quet as LQ
        for x in K.lich_chien_dich(ma):
            k = LQ.khung_chien_dich(x)
            if k and k[1] >= bay_gio - datetime.timedelta(days=NGAY_CHIEN_DICH_GAN) \
                    and k[0] < tu:
                tu = k[0]
                ly = f"chiến dịch #{x.get('id')} từ {k[0].astimezone(_VN):%d/%m}"
    except Exception as e:  # noqa: BLE001 — lịch hỏng không chặn lượt tìm
        print(f"[theo_doi] không đọc được lịch chiến dịch: {type(e).__name__}", flush=True)
    san = bay_gio - datetime.timedelta(days=NGAY_PHAM_VI_TOI_DA)
    if tu < san:
        tu, ly = san, f"{ly}, kẹp {NGAY_PHAM_VI_TOI_DA} ngày"
    tu = tu.astimezone(_VN).replace(hour=0, minute=0, second=0, microsecond=0)
    return tu, max(1, (bay_gio.astimezone(_VN).date() - tu.date()).days), ly


def so_xin(cau_hinh: int, moc: dict | None, cung_dau: bool) -> tuple[int, str]:
    """Cỡ xin lượt này (≤ số bài cấu hình). Lượt trước (cùng từ khoá/cấu hình) về đầy ≥ 90% số
    xin → gấp đôi (cửa sổ đầy, có thể còn bài); về ít → 1,5 × số đã về (≥ `XIN_TOI_THIEU`)."""
    xin, ve = (moc or {}).get("xin"), (moc or {}).get("ve")
    if not cung_dau or not isinstance(xin, int) or not isinstance(ve, int) or xin <= 0:
        return cau_hinh, "theo cấu hình"
    if ve >= 0.9 * xin:
        n = min(cau_hinh, max(XIN_TOI_THIEU, xin * 2))
        return n, f"lượt trước đầy {ve}/{xin} → xin {n}"
    n = min(cau_hinh, max(XIN_TOI_THIEU, math.ceil(ve * 1.5)))
    return n, f"lượt trước về {ve}/{xin} → xin {n}"


def xoay_fb(q: list[str], lim: int, lim_cfg: int, moc: dict | None,
            cung_dau: bool) -> tuple[list[str], int, int]:
    """Facebook gói Free (5 bài/lượt, mỗi từ một lượt, ≤20 bài — `apify_tool._fb_tu_free`):
    review 16/10 — co cỡ xin xuống 10 thì chỉ 2 từ đầu được quét, từ sau đói mãi. Nay: không co
    dưới 5 × số từ (tới trần cấu hình), và XOAY điểm bắt đầu qua các lượt (mốc `xoay`) để mọi
    từ khoá lần lượt được quét. -> (từ khoá theo thứ tự gửi, điểm xoay lượt sau, cỡ xin)."""
    import apify_tool
    moi_luot = apify_tool._FB_FREE_MOI_LUOT
    lim = max(lim, min(lim_cfg, moi_luot * len(q)))
    bat_dau = int((moc or {}).get("xoay") or 0) % len(q) if cung_dau and q else 0
    q_gui = q[bat_dau:] + q[:bat_dau]
    so_quet = len(apify_tool._fb_tu_free(q_gui, lim))
    return q_gui, (bat_dau + so_quet) % len(q) if q else 0, lim


def tach_da_biet(ma: str, hits: list[tuple], khoa_cua) -> tuple[list[dict], list[tuple], dict]:
    """Bài trong phạm vi → (dòng cập nhật số liệu của bài ĐÃ CÓ trong kho, bài mới cần lọc,
    {nền tảng: số dòng trùng trong lượt}). `khoa_cua(d)` → khoá bài."""
    thay: dict[str, tuple] = {}
    trung: dict[str, int] = {}
    for d, dt in hits:
        k = khoa_cua(d)
        if k in thay:
            trung[d.get("platform")] = trung.get(d.get("platform"), 0) + 1
            continue
        thay[k] = (d, dt)
    da = K.khoa_da_co(ma, list(thay)) if thay else set()
    cap_nhat = [{"khoa": k, "xem": _so(d.get("views")), "thich": _so(d.get("likes")),
                 "binh_luan": _so(d.get("comments")), "chia_se": _so(d.get("shares")),
                 "nen_tang": d.get("platform")}
                for k, (d, _) in thay.items() if k in da]
    moi = [x for k, x in thay.items() if k not in da]
    return cap_nhat, moi, trung


# ── Sổ "đã loại" của tìm theo từ khoá (review 16/10) ──
# Vì sao file JSON cạnh `.moc-tu-khoa.json` mà không phải bảng: không đổi schema kho (vai `mark`
# không có quyền DDL, bảng mới phải qua platform duyệt — KDLA), cùng kiểu sổ mốc đã có (ghi
# nguyên tử, khởi động lại vẫn còn), cỡ tự chặn vì chỉ giữ bài trong phạm vi ≤ 92 ngày. Dấu
# `dau` = từ loại trừ + bối cảnh + thị trường + từ khoá: đổi một trong số đó thì sổ cũ bỏ (bài
# bị loại theo luật cũ được xét lại).
_KHOA_LOAI = threading.Lock()
LOAI_TOI_DA = 20000           # dòng mỗi dự án (an toàn; phạm vi ≤ 92 ngày)


def _duong_loai():
    return A._thu_muc_nen() / ".loai-tu-khoa.json"


def dau_loai(du_an: dict, tu: list[str]) -> str:
    import hashlib
    import json
    s = json.dumps([sorted(A._norm(str(x)) for x in du_an.get("tu_loai_tru") or []),
                    str(du_an.get("boi_canh") or du_an.get("ten") or ""),
                    str(du_an.get("thi_truong") or "VN"), sorted(A._norm(x) for x in tu)],
                   ensure_ascii=False)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def _doc_so_loai() -> dict:
    import json
    try:
        d = json.loads(_duong_loai().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) and isinstance(d.get("du_an"), dict) else {}


def doc_loai(ma: str, dau: str, tu: datetime.datetime) -> dict[str, list]:
    """{khoá bài: [lý do, ngày đăng]} đã loại của dự án, cùng dấu luật, đăng từ `tu`."""
    x = (_doc_so_loai().get("du_an") or {}).get(ma)
    if not isinstance(x, dict) or x.get("dau") != dau:
        return {}
    moc = tu.astimezone(_VN).date().isoformat()
    return {k: v for k, v in (x.get("bai") or {}).items()
            if isinstance(v, list) and len(v) == 2 and str(v[1]) >= moc}


def ghi_loai(ma: str, dau: str, moi: list[tuple], tu: datetime.datetime) -> None:
    """Gộp bài bị loại lượt này vào sổ, bỏ bài đã ra khỏi phạm vi; ghi nguyên tử. Không ghi
    được thì chỉ báo (lượt sau xét lại — tốn AI, không mất bài)."""
    import json
    import os
    with _KHOA_LOAI:
        d = _doc_so_loai() or {"du_an": {}}
        cu = doc_loai(ma, dau, tu)
        for khoa, ly, dt in moi:
            if khoa and dt:
                cu[str(khoa)] = [str(ly)[:40], dt.astimezone(_VN).date().isoformat()]
        if len(cu) > LOAI_TOI_DA:
            cu = dict(sorted(cu.items(), key=lambda kv: kv[1][1])[-LOAI_TOI_DA:])
        d["du_an"][ma] = {"dau": dau, "bai": cu}
        f = _duong_loai()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, f)
        except OSError as e:
            print(f"[theo_doi] không ghi được sổ bài đã loại: {type(e).__name__}", flush=True)


def _so(v):
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


LAM_MOI_TOI_DA = 10          # bài TikTok làm mới số liệu mỗi lượt (0,003 USD/bài, `TT.GIA_YEU_CAU`)


def lam_moi_tiktok(v, ma: str, luot: int, tu: datetime.datetime, con: float,
                   them_phan) -> dict:
    """Làm mới số liệu tối đa `LAM_MOI_TOI_DA` bài TikTok trong phạm vi, nhiều tương tác nhất,
    chưa được cập nhật hôm nay (lượt tìm vừa rồi đã cập nhật bài nó trả về). -> thống kê.
    `them_phan(ph)` ghi phần (run id) vào sổ việc để tiền được chốt."""
    tk = {"bai": 0, "cap_nhat": 0, "usd": 0.0, "ghi_chu": ""}
    n = min(LAM_MOI_TOI_DA, int(con / TT.GIA_YEU_CAU)) if con > 0 else 0
    if n <= 0 or not TT.dung_api("tiktok_so_bai"):
        return tk
    try:
        bai = K.bai_can_lam_moi(ma, "tiktok", tu, n)
    except Exception as e:
        if type(e).__name__ == "MatQuyen":
            raise
        tk["ghi_chu"] = f"làm mới TikTok: không đọc được kho ({type(e).__name__})"
        return tk
    if not bai:
        return tk
    theo_link = {b["link"]: b["khoa"] for b in bai if b.get("link")}
    so: list = []
    dat = [(A._NEN_TANG, "tiktok"), (A._SO_RUN, so),
           (A._KHI_CO_RUN, lambda run, meta: them_phan({
               "id": f"lm-tiktok-{run.get('id')}", "nen_tang": "tiktok_lam_moi",
               "run_id": run.get("id"), "trang_thai": "xong"}))]
    moc = [(bien, bien.set(gt)) for bien, gt in dat]
    try:
        items = TT.so_lieu_bai(list(theo_link), tran_usd=n * TT.GIA_YEU_CAU)
    except A.LoiApify as e:
        items = []
        tk["ghi_chu"] = f"làm mới TikTok: {A._che_token(str(e))[:120]}"
    finally:
        for bien, t in reversed(moc):
            bien.reset(t)
    tk["bai"] = len(theo_link)
    tk["usd"] = round(sum(TT.GIA_YEU_CAU for m in so if isinstance(m, dict)
                          and m.get("run_id")), 4)
    vid = {TT.id_video(u): k for u, k in theo_link.items()}
    rows = [{"khoa": vid[it["id"]], "xem": it.get("playCount"), "thich": it.get("diggCount"),
             "binh_luan": it.get("commentCount"), "chia_se": it.get("shareCount")}
            for it in items if it.get("id") in vid]
    if rows:
        tk["cap_nhat"] = K.cap_nhat_so_lieu(ma, luot, rows)
    return tk


# ── Lượt "nổi" của tìm theo từ khoá TikTok (17/10/2026) ──
# Chủ dự án 16/10: "không cào được các bài rất viral như trong kompa". Chẩn đoán trên 16 nguồn
# TikTok top thảo luận của Kompa (HAPAS, 16/09–16/10): KOL đăng MỘT video seeding (#HAPAS
# #LAMMOIDIEUVIYEU #QUATANG2010, 30/09–04/10, 750–5.000 bình luận mỗi video) — lượt tìm thường
# sắp theo LIÊN QUAN, xin ~15 bài mỗi từ (1 trang 30 bài) và từ lượt thứ hai chỉ xin "tuần này"
# (cửa sổ tăng dần), nên video viral cũ hơn một tuần không bao giờ lọt trang đầu. Đo thật 17/10
# (21 từ khoá, 30 ngày, 1 trang mỗi từ — cùng giá 0,042 USD): sắp "nhiều thích" bắt 12/14 nhà
# sáng tạo (90% số thảo luận Kompa), "liên quan" 9/14 (53%); 2 trang "nhiều thích" 13/14 (94%).
# Hashtag (challengePosts) chỉ lật được ~100 video/tag và bắt 7/14 (27%) — không dùng.
# Nên: mỗi `NOI_GIO_GIAN` giờ một lượt sắp "nhiều thích" trên 30 ngày gần nhất, `NOI_TRANG`
# trang mỗi từ khoá; bài về đi CÙNG phễu (bài đã có → cập nhật số bình luận/xem như Kompa; bài
# mới → lọc + AI). Tiền nằm TRONG ước tính TikTok sẵn có (2×trang cần + 1 trang mỗi từ — lượt
# thường hầu như chỉ dùng 1 trang): trần = phần ước tính chưa dùng, kẹp phần còn của tháng/việc.
NOI_GIO_GIAN = 20            # giờ tối thiểu giữa hai lượt nổi (≈ 1 lượt/ngày có lượt quét)
NOI_TRANG = 2                # trang (30 bài) mỗi từ khoá
NOI_NGAY = 30                # bộ lọc ngày phía server: "tháng này"
KHOA_MOC_NOI = "tiktok_noi"  # khoá trong sổ mốc tìm theo từ khoá (`theo_doi.ghi_moc_tk`)


def den_luot_noi(moc: dict | None, bay_gio: datetime.datetime,
                 gio: int = NOI_GIO_GIAN) -> tuple[bool, str]:
    """Lượt này có chạy lượt nổi TikTok không (`gio`: nhịp — kiểm độ phủ có thể dày lên,
    `kiem_do_phu.hanh_dong`). -> (có, lý do)."""
    try:
        luc = datetime.datetime.fromisoformat(str((moc or {}).get("luc") or ""))
    except ValueError:
        return True, "chưa có lượt nổi"
    luc = luc if luc.tzinfo else luc.replace(tzinfo=_VN)
    cach = bay_gio - luc
    if cach < datetime.timedelta(hours=gio):
        return False, f"lượt nổi gần nhất {luc.astimezone(_VN):%d/%m %H:%M} (< {gio} giờ)"
    return True, f"lượt nổi trước {luc.astimezone(_VN):%d/%m %H:%M}"


def tran_noi(so_tu: int, uoc_tiktok: float, da_tieu: float, con: float,
             trang: int = NOI_TRANG) -> float:
    """Trần USD của lượt nổi: đủ `trang` trang mỗi từ, nhưng không vượt phần ước tính TikTok
    CHƯA dùng (chừa `LAM_MOI_TOI_DA` yêu cầu làm mới) và phần còn của tháng/việc — kiểm độ phủ
    nới trang / thêm hashtag cũng không thể vượt trần này."""
    du = so_tu * trang * TT.GIA_YEU_CAU
    du_uoc = uoc_tiktok - da_tieu - LAM_MOI_TOI_DA * TT.GIA_YEU_CAU
    return round(max(0.0, min(du, du_uoc, con - da_tieu)), 4)


def tim_noi_tiktok(q: list[str], bay_gio: datetime.datetime, tran: float,
                   trang: int = NOI_TRANG, tag: list[str] | None = None,
                   cid: dict | None = None) -> list[tuple]:
    """Bài TikTok nhiều thích nhất 30 ngày của từng từ khoá -> [(dòng, ngày VN)] như
    `apify_tool._FETCH["tiktok"]`. Chỉ TikTok API: lỗi thì trả [] (KHÔNG xuống chuỗi dự phòng
    tính tiền theo video — lượt nổi là phần thêm). Run id đi qua `apify_tool._KHI_CO_RUN` của
    bên gọi (sổ tiền chung của lượt tìm TikTok).

    `tag` (17/10/2026, kiểm độ phủ tự thêm — `kiem_do_phu.hanh_dong`): đọc FEED hashtag
    (`challengePosts`, `trang` trang × 20 bài mỗi tag) bằng phần trần còn lại sau từ khoá. Đo thật
    17/10: tìm "lammoidieuviyeu" như từ khoá (nhiều thích) chỉ trùng 17/94 bài 30 ngày của feed
    #lammoidieuviyeu — phải đọc feed. `cid` {tag: cid} dùng lại và được bổ sung tại chỗ."""
    so_yc = int(tran / TT.GIA_YEU_CAU + 1e-9)
    if not (q or tag) or so_yc <= 0 or not TT.dung_api("tiktok_tim"):
        return []
    items: list = []
    yc_tu = min(so_yc, len(q) * trang)
    try:
        if q and yc_tu:
            items = TT.tim(q, len(q) * trang * TT.TIM_MOI_TRANG,
                           bay_gio - datetime.timedelta(days=NOI_NGAY), bay_gio,
                           tran_usd=yc_tu * TT.GIA_YEU_CAU, sap=TT.SAP_NHIEU_THICH,
                           trang_toi_da=trang)
    except A.LoiApify as e:
        if e.ma in ("HET_TIEN_THANG", "DA_HUY"):
            raise
        print(f"[theo_doi] lượt nổi TikTok lỗi: {e.ma} {A._che_token(str(e))[:120]}", flush=True)
    if tag and so_yc > yc_tu:
        ngan = TT.Ngan((so_yc - yc_tu) * TT.GIA_YEU_CAU)
        cid = cid if cid is not None else {}
        for t in tag:
            try:
                if not cid.get(t):
                    c = TT.tim_cid(t, ngan)
                    if not c:
                        continue
                    cid[t] = c
                items += TT.bai_hashtag(cid[t], trang, ngan)
            except A.LoiApify as e:
                if e.ma in ("HET_TIEN_THANG", "DA_HUY"):
                    raise
                print(f"[theo_doi] lượt nổi #{t} lỗi: {e.ma}", flush=True)
    ra = A._chuan_tiktok(A._chuan_clockworks(items))
    for d, _ in ra:
        d["_noi"] = True
    return ra


# ── Trang "mới nhất" của tìm theo từ khoá TikTok (17/10/2026) ──
# Chủ dự án 17/10: "thêm trang: mới nhất vào lượt tìm tiktok hằng ngày". Đo thật 17/10 (HAPAS,
# "hapas" + "túi hapas", 30 ngày): hợp mọi đường 497 bài nhắc brand; liên quan + nhiều thích +
# feed hashtag bắt 446 (89,7%); feed sắp MỚI NHẤT (sortType 3) thêm 50 bài không đường nào có
# (→ 99,8%) — chủ yếu bài ít thích của tài khoản nhỏ, liên quan/nhiều thích xếp thấp. Đo lại
# đúng cấu hình hằng ngày (thường 1 trang 7 ngày + nổi 2 trang): một trang mới nhất mỗi từ thêm
# 14–17 bài brand (≈ một nửa trang), thường + nổi chỉ phủ 83–84% hợp ba đường. Feed này
# sắp đúng theo giờ đăng giảm dần, từ bận nhất ~4 bài/ngày (tối đa 13), nên MỘT trang 30 bài mỗi
# ngày đủ phủ: lượt sau chỉ cần lật tới mốc lượt trước.
# Cách chạy (cùng chỗ với lượt nổi, ngay sau lượt thường, chỉ khi lượt thường đi TikTok API):
#   • tối đa một lượt mỗi `MOI_GIO_GIAN` giờ (lịch chiến dịch 6 giờ/lượt không trả tiền 4 lần);
#   • mỗi từ khoá lật tới khi CHẠM mốc lượt trước của chính từ đó (lùi `MOI_GIO_CHONG` giờ) —
#     thường 1 trang, từ đang bận tự lật thêm (≤ `MOI_TRANG_TOI_DA`, kiểm độ phủ nới được);
#   • từ khoá "yên" (`MOI_YEN_SAU` lượt liền không có bài nào mới hơn mốc) chỉ chạy lại sau
#     `MOI_GIO_YEN` giờ — mốc của từ đứng yên nên lượt sau vẫn lật tới đúng chỗ đã xem, không
#     hở khoảng nào; có bài mới là về nhịp hằng ngày;
#   • bài về đi CÙNG phễu (đã có → cập nhật số; mới → lọc + AI), tiền vào sổ lượt tìm TikTok
#     (`theo_doi._tien_tim_tiktok` đếm mọi run TikTok API). Ước tính TikTok cộng 1 trang/từ.
MOI_GIO_GIAN = 20            # giờ tối thiểu giữa hai lượt "mới nhất" (≈ 1 lượt/ngày)
MOI_TRANG = 1                # trang/từ có trong ước tính (`theo_doi.uoc_tu_khoa_nen_tang`)
MOI_TRANG_TOI_DA = 3         # trần lật trang mỗi từ khi chưa chạm mốc lượt trước
MOI_GIO_CHONG = 24           # lùi mốc từng từ (bài lên chỉ mục tìm kiếm chậm vài giờ)
MOI_YEN_SAU = 3              # lượt liền không có bài mới hơn mốc → từ "yên"
MOI_GIO_YEN = 68             # từ yên chạy lại sau chừng này giờ (≈ 3 ngày)
MOI_NGAY_LAN_DAU = 7         # từ chưa có mốc: lật tới bài 7 ngày trước (≤ `MOI_TRANG_TOI_DA` trang)
KHOA_MOC_MOI = "tiktok_moi"  # khoá trong sổ mốc tìm theo từ khoá (`theo_doi.ghi_moc_tk`)


def _gio(s) -> datetime.datetime | None:
    try:
        x = datetime.datetime.fromisoformat(str(s or ""))
    except ValueError:
        return None
    return x if x.tzinfo else x.replace(tzinfo=_VN)


def den_luot_moi(moc: dict | None, bay_gio: datetime.datetime,
                 gio: int = MOI_GIO_GIAN) -> tuple[bool, str]:
    """Lượt này có chạy trang mới nhất không. -> (có, lý do)."""
    luc = _gio((moc or {}).get("luc"))
    if luc is None:
        return True, "chưa có lượt mới nhất"
    if bay_gio - luc < datetime.timedelta(hours=gio):
        return False, f"lượt mới nhất gần nhất {luc.astimezone(_VN):%d/%m %H:%M} (< {gio} giờ)"
    return True, f"lượt mới nhất trước {luc.astimezone(_VN):%d/%m %H:%M}"


def chon_tu_moi(q: list[str], moc: dict | None,
                bay_gio: datetime.datetime) -> tuple[list[tuple[str, datetime.datetime]], list[str]]:
    """(từ khoá chạy lượt này kèm mốc dừng lật trang, từ khoá đang nghỉ vì "yên"). Mốc của từ =
    lần chạy trước của chính từ đó lùi `MOI_GIO_CHONG` giờ (kẹp ≤ 30 ngày); từ chưa chạy lần
    nào: `MOI_NGAY_LAN_DAU` ngày."""
    tu_cu = (moc or {}).get("tu") if isinstance((moc or {}).get("tu"), dict) else {}
    san = bay_gio - datetime.timedelta(days=TT.MOI_NHAT_MOC_NGAY)
    chay, nghi = [], []
    for kw in q:
        x = tu_cu.get(A._norm(kw)) if isinstance(tu_cu.get(A._norm(kw)), dict) else {}
        luc = _gio(x.get("luc"))
        if luc is None:
            chay.append((kw, bay_gio - datetime.timedelta(days=MOI_NGAY_LAN_DAU)))
            continue
        yen = int(x.get("yen") or 0) if str(x.get("yen") or "0").isdigit() else 0
        if yen >= MOI_YEN_SAU and bay_gio - luc < datetime.timedelta(hours=MOI_GIO_YEN):
            nghi.append(kw)
            continue
        chay.append((kw, max(san, luc - datetime.timedelta(hours=MOI_GIO_CHONG))))
    return chay, nghi


def tran_moi(so_tu: int, uoc_tiktok: float, da_tieu: float, con: float, du_noi: float = 0.0,
             trang_toi_da: int = MOI_TRANG_TOI_DA) -> float:
    """Trần USD của lượt mới nhất: đủ `trang_toi_da` trang mỗi từ, nhưng phần vượt `MOI_TRANG`
    trang/từ (đã có trong ước tính) chỉ lấy từ phần ước tính TikTok CHƯA dùng sau khi chừa làm
    mới (`LAM_MOI_TOI_DA`) và lượt nổi tới hạn (`du_noi`); luôn kẹp phần còn của tháng/việc."""
    co_ban = so_tu * MOI_TRANG * TT.GIA_YEU_CAU
    du = so_tu * max(MOI_TRANG, trang_toi_da) * TT.GIA_YEU_CAU
    du_uoc = uoc_tiktok - da_tieu - LAM_MOI_TOI_DA * TT.GIA_YEU_CAU - du_noi
    return round(max(0.0, min(du, max(co_ban, du_uoc), con - da_tieu)), 4)


def tim_moi_tiktok(q: list[str], moc: dict | None, bay_gio: datetime.datetime, tran: float,
                   trang_toi_da: int = MOI_TRANG_TOI_DA) -> tuple[list[tuple], dict, dict]:
    """Trang mới nhất của các từ khoá tới lượt -> ([(dòng, ngày VN)] như
    `apify_tool._FETCH["tiktok"]`, thống kê {"tu", "nghi", "trang", "moi_hon_moc", "loi"}, mốc
    mới {"luc", "tu": {từ chuẩn hoá: {"luc", "yen"}}}). Chỉ TikTok API, không xuống dự phòng.
    Từ lỗi / chưa tới lượt (hết trần) giữ mốc cũ — lượt sau lật lại từ đó. KHÔNG ném lỗi Apify
    (lượt mới nhất là phần thêm): bài đã trả tiền luôn trả về, `loi` ghi lỗi từng từ / mã dừng
    (HET_TIEN_THANG / DA_HUY khoá bộ đếm — `tiktok_api.tim_moi_nhat`). Mốc chỉ giữ từ khoá
    hiện có của dự án."""
    chay, nghi = chon_tu_moi(q, moc, bay_gio)
    tk = {"tu": len(chay), "nghi": len(nghi), "trang": 0, "moi_hon_moc": 0, "chua_cham": 0,
          "loi": ""}
    tu_cu = (moc or {}).get("tu") if isinstance((moc or {}).get("tu"), dict) else {}
    hien = {A._norm(kw) for kw in q}
    tu_moi = {k: dict(x) for k, x in tu_cu.items() if isinstance(x, dict) and k in hien}
    so_yc = int(tran / TT.GIA_YEU_CAU + 1e-9)
    if not chay or so_yc <= 0 or not TT.dung_api("tiktok_tim"):
        return [], tk, {"luc": (moc or {}).get("luc"), "tu": tu_moi}
    ngan = TT.Ngan(so_yc * TT.GIA_YEU_CAU)
    kq = TT.tim_moi_nhat(chay, max(1, int(trang_toi_da)), ngan)
    items: list = []
    thay: set[str] = set()
    loi = []
    for kw, _ in chay:
        r = kq.get(kw) or {}
        for it in r.get("bai") or []:              # một video có thể về ở nhiều từ khoá
            if str(it.get("id")) not in thay:
                thay.add(str(it.get("id")))
                items.append(it)
        tk["trang"] += int(r.get("trang") or 0)
        tk["moi_hon_moc"] += int(r.get("moi_hon_moc") or 0)
        if r.get("loi"):
            loi.append(f"{kw}: {r['loi']}")
        if not r.get("trang") or r.get("loi"):
            continue                    # chưa xem được trang nào / lỗi: giữ mốc cũ của từ
        cu = tu_moi.get(A._norm(kw)) or {}
        if not r.get("cham"):
            # Review M1: dừng vì trần trang / trần tiền TRƯỚC khi lật tới mốc — dời mốc tới bây
            # giờ thì phần giữa (mốc cũ .. bài cũ nhất đã thấy) mất hẳn. Có mốc cũ: giữ nguyên
            # (lượt sau lật lại tới đó); chưa có: mốc = bài cũ nhất đã thấy (+ phần chồng mép).
            tk["chua_cham"] += 1
            if not cu.get("luc") and r.get("cu_nhat"):
                tu_moi[A._norm(kw)] = {"luc": (r["cu_nhat"] + datetime.timedelta(
                    hours=MOI_GIO_CHONG)).isoformat(timespec="seconds"), "yen": 0}
            continue
        yen_cu = str(cu.get("yen") or "0")
        yen = 0 if r.get("moi_hon_moc") else (int(yen_cu) if yen_cu.isdigit() else 0) + 1
        tu_moi[A._norm(kw)] = {"luc": bay_gio.isoformat(timespec="seconds"), "yen": yen}
    if ngan.dung:
        loi.append(f"dừng: {ngan.dung}")
    tk["loi"] = "; ".join(loi)[:200]
    ra: list[tuple] = []
    for it in items:                    # từng bài: một bài hỏng không làm mất bài đã trả tiền
        try:
            ra += A._chuan_tiktok(A._chuan_clockworks([it]))
        except (KeyError, TypeError, ValueError, AttributeError):
            tk["loi"] = (tk["loi"] + "; bỏ 1 bài hỏng shape").lstrip("; ")[:200]
    for d, _ in ra:
        d["_moi_nhat"] = True
    return ra, tk, {"luc": bay_gio.isoformat(timespec="seconds"), "tu": tu_moi}
