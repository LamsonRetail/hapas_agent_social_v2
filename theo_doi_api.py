"""Phần mở rộng của `/theodoi` (16/10/2026) — tách khỏi theo_doi.py cho các nhánh khác sửa
theo_doi ít đụng nhau. Hai việc:

1. PHẦN NHIỀU YÊU CẦU qua TikTok API (`tiktok_api`): hồ sơ nguồn TikTok và bình luận TikTok.
   Một phần = nhiều run Apify (mỗi yêu cầu API một run); id nằm ở `run_phu` của phần
   (`viec_nen.run_ids` cộng vào tiền thật). Bot khởi động lại giữa phần thì CHẠY LẠI phần đó
   (khác kỷ luật "không gửi lại" của actor thường: mỗi yêu cầu 0,002 USD, chạy lại cả phần chỉ
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
     trong phạm vi qua TikTok API theo link (0,002 USD/bài — `lam_moi_tiktok`).
"""
from __future__ import annotations

import datetime
import math
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


LAM_MOI_TOI_DA = 10          # bài TikTok làm mới số liệu mỗi lượt (0,002 USD/bài)


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
