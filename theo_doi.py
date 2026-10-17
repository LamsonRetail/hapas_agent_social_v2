"""Lệnh `/theodoi <dự án>`: quét các NGUỒN ĐANG THEO DÕI của một dự án, giữ bài nhắc tới dự án,
gán nhãn AI, ghi vào kho `lang_nghe` (đợt 2, chủ dự án chốt 14/10/2026).

Vì sao có lệnh này — so với Kompa, Mark thiếu dữ liệu chủ yếu vì chỉ TÌM THEO TỪ KHOÁ khi được
hỏi; Kompa theo dõi sẵn danh sách nguồn và cộng dồn mỗi ngày. Lệnh này là nửa "theo dõi": danh
sách nguồn và ngân sách tháng quản lý trên dashboard (`social.hapas.vn`), Mark quét theo lịch.

Mark VẪN theo luật platform như trước (chủ dự án chốt 14/10/2026 — "không đổi"):
  • Lượt chạy đến từ HAI đường lịch (và lệnh gõ tay):
      1. Lịch `run` trên console platform (nội dung `/theodoi hapas`) — đi qua hàng đợi job +
         audit của platform như mọi việc khác.
      2. Từ 15/10/2026 (chủ dự án chốt "Dashboard + Mark tự chạy"): LỊCH QUÉT TỰ ĐỘNG đặt trên
         dashboard (bảng `lich_quet`). Đây LÀ một nhịp riêng trên VPS (`quet_tu_dong.py`, 30
         giây, trong tiến trình Mark) — không qua hàng đợi job của platform, nên mỗi lượt báo
         platform bằng trace (`lsr_platform.bao_luot`). Cùng đường `tao_luot`, cùng công tắc +
         trần; kết quả chỉ lên dashboard, không nhắn Lark.
  • Cần công tắc `soi_tai_khoan` (cùng actor theo tài khoản) đang bật — kiểm ở `lenh_cung`.
  • Mỗi nền tảng tôn trọng công tắc + trần USD mỗi lượt ở "Năng lực → Quét mạng xã hội".
  • Trần tháng của dự án (dashboard) chỉ THU HẸP thêm: mỗi lượt actor mang trần USD =
    min(trần console của nền tảng, ước tính × 1,5, phần còn lại của tháng) — Apify tự dừng ở
    trần đó (`maxTotalChargeUsd`), nên lượt không thể tiêu quá phần tháng còn lại.

Chạy NỀN (`viec_nen`, loại `theo_doi`), cùng kỷ luật tiền với quét nền lớn (`quet_lon`):
  • mỗi "phần" = một lượt actor (một nền tảng × một mức số bài), ghi run id ngay khi Apify trả;
  • bài lấy được ghi xuống đĩa (`Viec.ghi_dong`) TRƯỚC khi đánh dấu phần xong;
  • bot khởi động lại: phần đã xong đọc lại từ đĩa; phần có run id thì ĐỌC TIẾP run đó; phần
    đang gửi dở thì tìm run vừa tạo, không kiểm được thì KHÔNG gửi lại (không trả tiền hai lần);
  • chi phí thật chốt theo đúng run id (`Viec.chot_chi_phi`) trong `finally` — lỗi giữa chừng
    vẫn ghi tiền vào lượt, nên "đã tiêu tháng" không bị đếm thiếu.
"""
from __future__ import annotations

import contextvars
import datetime
import hashlib
import json
import math
import os
import re
import threading
import time

import apify_tool as A
import khu_trung_fb as KT
import kiem_do_phu as KDP
import lang_nghe_db as K
import nguon_web as W
import theo_doi_api as TDA

_VN = datetime.timezone(datetime.timedelta(hours=7))
#: Nền tảng theo thứ tự chạy: miễn phí trước, để hết giờ/hết tiền thì phần mất là phần tốn tiền.
#: Threads cuối: phí khởi động mỗi lượt actor cao nhất (0,08 USD, gói FREE).
THU_TU = ("youtube", "instagram", "tiktok", "facebook", "threads")
_TEN = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok", "facebook": "Facebook",
        "threads": "Threads", "web": "Báo & Web"}
#: Giá đo thật 25/09/2026 (`account_tool._GIA`): Facebook theo bài, Instagram theo tài khoản
#: (actor trả 12 bài mới nhất). YouTube Data API miễn phí. Threads (16/10/2026, chế độ "user" của
#: `apify_tool._ACTORS["threads"]`): 0,0025 USD/bài = `apify_tool._UNIT_COST`. TikTok từ
#: 16/10/2026 qua TikTok API (`tiktok_api.ho_so`), từ 18/10/2026 tính theo YÊU CẦU (giá bảng
#: 0,002 USD = giá thật từng run, `tiktok_api.GIA_YEU_CAU`): một nguồn n bài = 1 yêu cầu hồ sơ +
#: ⌈n/10⌉ trang + 1 trang bù bài ghim (`tiktok_api.so_yeu_cau_ho_so`). Dạng cũ "0,0012 × bài"
#: (0,006 USD cho 5 bài, giả định 0,003/yêu cầu) báo @hapas.official 20 bài 0,031 USD/lượt =
#: 0,936 USD/tháng trên trang Nguồn, thật 3–4 yêu cầu = 0,006–0,008 USD/lượt.
#: Facebook từ 17/10/2026 qua thedoor~facebook-page-scraper (`theo_doi_api.FB_TRANG`): 0,0025 USD/bài
#: (gói FREE, cùng 20 bài với actor cũ 0,005, có view video) + phí khởi động 0,01 USD/run
#: (`_KHOI_NGUON`; actor cũ còn làm dự phòng).
#: Threads từ 17/10/2026: actor HỒ SƠ scrapersdelight (`A._ACTORS["threads_ho_so"]`) tính THEO TÀI
#: KHOẢN như Instagram — 0,002 USD/hồ sơ kèm 4–10 bài mới nhất, không phí khởi động (đo @hapas.vn:
#: 8.434 follower, 4 bài, 0,002 USD). Chế độ "user" của futurizerush ((10 × 0,0025 + 0,08) × 1,3 =
#: 0,137 USD/tài khoản/lượt) chỉ còn làm DỰ PHÒNG khi actor hồ sơ hỏng cả lượt (`_du_phong_threads`).
_GIA = {"tiktok": TDA.TT.GIA_YEU_CAU, "facebook": 0.0025, "instagram": 0.0026, "youtube": 0.0,
        "threads": A.TH_HO_SO_GIA}
#: Phí khởi động MỖI lượt actor theo dõi nguồn: như `apify_tool._START_COST` (actor tìm bài), trừ
#: actor theo dõi riêng — Facebook thedoor 0,01 USD/run (`apify-actor-start` 1 GB, thêm
#: 15/10/2026), Threads hồ sơ không có phí khởi động (512 MB). Bản sao
#: `dashboard.chi_phi.KHOI_NGUON`.
_KHOI_NGUON = {**A._START_COST, "facebook": 0.01, "threads": 0.0}
# Threads (chủ dự án 16/10/2026: "thêm listening threads"). Actor futurizerush~meta-threads-scraper
# — đọc input schema + chạy thử 16/10/2026: chế độ "search" (từ khoá, ≤ 20 từ/lượt, lọc ngày
# start_date/end_date phía actor, "recent" bài mới trước) và "user" (bài mới nhất của ≤ 20 tài
# khoản/lượt, KHÔNG lọc ngày); `max_posts` là trần MỖI từ/tài khoản, tối thiểu 10; actor không dừng
# ở `maxItems`, chỉ trần USD chặn được. Bình luận (trả lời cấp 1) qua actor riêng của
# `deep_dive_tool` (futurizerush~threads-replies-scraper, ≤ 20 bài/lượt, 10–300 trả lời/bài).
# Từ 17/10/2026 NGUỒN Threads (theo dõi tài khoản) đi actor hồ sơ scrapersdelight (`_GIA`); chế độ
# "user" ở trên chỉ còn là lượt dự phòng (`_du_phong_threads`).
TH_TOI_THIEU_BAI = 10        # max_posts tối thiểu của actor: mỗi tài khoản/từ khoá trả tiền ≥ 10 bài
TH_TOI_DA_MOI_LUOT = 20      # tài khoản (chế độ "user") hoặc từ khoá (chế độ "search") mỗi lượt
# Threads ĐƯỜNG 2 (17/10/2026, chủ dự án duyệt): scrapersdelight~threads-keyword-search-scraper chạy
# CÙNG lượt tìm với futurizerush. Đo vòng 2 (bảng ở `apify_tool._fetch_threads`): hai actor bắt hai
# tập khác nhau — 7 ngày, futurizerush 62% + scrapersdelight 62% → cùng nhau 86% (98% theo thảo
# luận) — mà đường 2 chỉ 0,001 USD/bài, không phí khởi động (run 21 từ khoá × 7 ngày = 0,015 USD).
# Cấu hình `du_an.cau_hinh.tu_khoa.threads.duong2` = {"bat", "so_bai" (trần bài CẢ lượt),
# "so_bai_moi_tu", "so_luot"} — xem `cau_hinh_th2`. Mặc định BẬT (dưới công tắc Threads của dự án).
TH2_KHOA = "threads_2"       # khoá: bộ tìm `A._FETCH`, sổ mốc, phần "moc" của việc, phễu
TH2_GIA = A.TH2_GIA          # 0,001 USD / bài trả về
# 100 bài/lượt = tối đa 0,10 USD (0,13 với hệ số ước tính): run 3 từ khoá × 30 ngày × 2 lượt trả 47
# bài, lượt hằng ngày (cửa sổ 3 ngày) dự kiến ~10. 20 bài/từ: "hapas" 30 ngày được 29 bài.
TH2_SO_BAI = 100
TH2_MOI_TU = 20
TH2_LUOT = 2                 # passesPerSurface: lượt thứ 3 trở đi gần như không thêm bài (đo 17/10)
TH2_RONG_CANH_BAO = 2        # về 0 bài chừng này lượt liền → cảnh báo (actor 6 tuần tuổi, 81 người dùng)
# Ước tính Threads theo sản lượng lượt trước (`san_luong_du_kien`) nhân hệ số này: số bài về mỗi
# ngày thất thường (vd đợt 20/10), nhưng 1,5 × lượt trước vẫn sát hơn nhiều giả định "mỗi từ đủ trần".
TH_HE_SO_SAN_LUONG = 1.5
# Lỗi KHÔNG phải do actor (tài khoản hết tiền, nghẽn chỗ chạy, người dùng huỷ): không tính vào chuỗi
# "về 0 bài" của cảnh báo đường 2.
_TH2_LOI_KHONG_DEM = ("HET_TIEN_THANG", "NGHEN_DONG_THOI", "DA_HUY")
_HE_SO_UOC = 1.3          # ước tính chừa hao hụt (bài ghim, phí lẻ…)
_HE_SO_TRAN = 1.5         # trần USD của một lượt actor = ước tính × hệ số này (rồi kẹp)
_TRAN_TOI_THIEU = 0.1     # `_run_actor` kẹp trần ≥ 0,1 USD: tháng còn ít hơn thì không chạy
TOI_DA_NGUON = 60         # mỗi lượt; nguồn quá trần chờ lượt sau (cũ nhất đi trước)
NGAY_GIU = 35             # bài đăng cũ hơn chừng này ngày không ghi (không thuộc kỳ theo dõi)
NGAY_LAM_MOI_YT = 14      # bài YouTube đã giữ: đọc lại số mỗi ngày trong 14 ngày đầu (miễn phí)
_CHUA_GIAY_CUOI = 90      # giây chừa cho AI + ghi kho + chốt chi phí trước hạn chót việc
_KET_PHAN = ("xong", "mot_phan", "loi", "da_huy")
_LENH = "/theodoi"


# ───────────────────────────── tiện ích ─────────────────────────────
def _hom_nay() -> str:
    return datetime.datetime.now(_VN).strftime("%Y-%m-%d")


def _usd(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _usd3(x: float) -> str:
    """USD 3 chữ số lẻ — tiền đường 2 Threads tính theo phần nghìn USD (0,001/bài)."""
    return f"{float(x):.3f}".replace(".", ",")


def _chuan_dinh_danh(p: str, s: str) -> str:
    """Khoá so khớp nguồn ↔ kết quả actor: chữ thường, bỏ @, bỏ đuôi '/' và tham số URL.
    Id kênh YouTube (UC…) phân biệt hoa thường nên giữ nguyên."""
    s = (s or "").strip()
    if p == "youtube" and re.fullmatch(r"UC[\w-]{22}", s):
        return s
    s = s.split("?", 1)[0].split("#", 1)[0].rstrip("/").lower()
    if p == "facebook":
        s = re.sub(r"^https?://(www\.|m\.|web\.)?", "", s)
        s = s.replace("fb.com/", "facebook.com/")
    if p == "threads":                     # link hồ sơ threads.net / threads.com -> username
        s = re.sub(r"^(https?://)?(www\.)?threads\.(net|com)/", "", s)
    return s.lstrip("@")


def _khoa_bai(p: str, link: str, goc: dict | None = None) -> str:
    """"<nền tảng>:<id bài>" — id lấy từ link; không bóc được thì băm link (vẫn ổn định).

    Threads CỐ Ý không bóc mã bài: bài Threads đã vào kho từ lượt social_listen (`luu_tu_khoa`)
    bằng khoá băm link `post_url` — đổi sang mã bài thì cùng một bài thành hai dòng."""
    link = link or ""
    mau = {"tiktok": r"/video/(\d+)", "instagram": r"/(?:p|reel|reels|tv)/([\w-]+)",
           "youtube": r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})",
           "facebook": r"(?:/posts/|/videos/|story_fbid=|/permalink/|fbid=)([\w-]+)"}.get(p)
    m = re.search(mau, link) if mau else None
    if m:
        return f"{p}:{m.group(1)}"
    for k in ("postId", "id", "shortCode"):
        if goc and goc.get(k):
            return f"{p}:{goc[k]}"
    return f"{p}:h{hashlib.sha1(link.encode('utf-8')).hexdigest()[:16]}"


def _so_hay_none(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ───────────────────────────── ước tính + phần ─────────────────────────────
def don_vi_nguon(p: str, n: int) -> int:
    """Đơn vị tính tiền của MỘT nguồn mỗi lượt: bài (Facebook), tài khoản (Instagram, Threads —
    actor hồ sơ, 17/10/2026), YÊU CẦU (TikTok API, 18/10/2026 — `tiktok_api.so_yeu_cau_ho_so`)."""
    if p in ("instagram", "threads"):
        return 1
    return TDA.TT.so_yeu_cau_ho_so(n) if p == "tiktok" else int(n)


def _uoc_phan(p: str, so_nguon: int, n: int) -> float:
    """USD ước tính TỐI ĐA của MỘT lượt actor: `so_nguon` nguồn × đơn vị (`don_vi_nguon`) × giá,
    cộng phí khởi động của actor (`_KHOI_NGUON`), nhân hệ số hao hụt."""
    gia = _GIA.get(p, 0.0)
    if not gia or not so_nguon:
        return 0.0
    don_vi = so_nguon * don_vi_nguon(p, n)
    khoi = _KHOI_NGUON.get(p, A._START_COST.get(p, 0.0))
    return round((don_vi * gia + khoi) * _HE_SO_UOC, 4)


def _uoc_phan_user_threads(so_nguon: int, n: int) -> float:
    """USD ước tính một lượt DỰ PHÒNG Threads (futurizerush chế độ "user"): mỗi tài khoản ≥ 10 bài
    × 0,0025 + phí khởi động 0,08 (ép 4 GB, gói FREE), nhân hệ số."""
    if not so_nguon:
        return 0.0
    return round((so_nguon * max(TH_TOI_THIEU_BAI, n) * A._UNIT_COST["threads"]
                  + A._START_COST["threads"]) * _HE_SO_UOC, 4)


def _so_bai_nguon(x: dict) -> int:
    """Số bài mỗi lần THẬT SỰ lấy (và trả tiền) của một nguồn: số đã co theo nhịp đăng
    (`so_bai_hieu_luc`, `_co_gian_nguon` — 18/10/2026) hoặc số cấu hình; Threads tối thiểu 10."""
    n = int(x.get("so_bai_hieu_luc") or x.get("so_bai_moi_lan") or 5)
    return max(TH_TOI_THIEU_BAI, n) if x.get("nen_tang") == "threads" else n


def chia_phan(nguon: list[dict]) -> dict[str, list[dict]]:
    """Nguồn -> các phần (lượt actor). Nguồn cùng nền tảng VÀ cùng số bài mỗi lần đi chung một
    lượt — mỗi nguồn trả đúng số bài của nó (review 14/10: gộp theo số bài lớn nhất thì nguồn
    5 bài cũng bị lấy 30 bài và tốn tiền ngoài ước tính). YouTube một phần (API miễn phí).
    Threads: chế độ "user" của actor, tối đa `TH_TOI_DA_MOI_LUOT` tài khoản mỗi lượt."""
    import account_tool
    from dashboard import chi_phi as CP
    nhom: dict[tuple[str, int], list[dict]] = {}
    fb: list[tuple[int, dict]] = []
    for x in nguon:
        p = x["nen_tang"]
        if p == "facebook":
            fb.append((_so_bai_nguon(x), x))
            continue
        n = 0 if p in ("youtube", "instagram") else _so_bai_nguon(x)
        nhom.setdefault((p, n), []).append(x)
    # Facebook (18/10/2026): thedoor nhận MỘT số bài cho mọi trang của run + 0,01 USD khởi động mỗi
    # run — gom các nguồn (số bài đã co theo nhịp đăng khác nhau) thành các run rẻ nhất
    # (`chi_phi.nhom_fb`); trang trong nhóm lấy theo số bài lớn nhất của nhóm, đã nằm trong ước tính.
    for n, ds in CP.nhom_fb(fb, _GIA["facebook"], _KHOI_NGUON["facebook"]):
        nhom.setdefault(("facebook", n), []).extend(ds)
    ra: dict[str, list[dict]] = {}
    for (p, n), tat_ca in sorted(nhom.items()):
        lo_nguon = ([tat_ca[i:i + TH_TOI_DA_MOI_LUOT]
                     for i in range(0, len(tat_ca), TH_TOI_DA_MOI_LUOT)]
                    if p == "threads" else [tat_ca])
        for k, ds in enumerate(lo_nguon):
            ids = [int(x["id"]) for x in ds]
            ph = {"id": f"{p}-{n or 'tat_ca'}" + (f"-{k + 1}" if k else ""), "nen_tang": p,
                  "nguon": ids, "trang_thai": "cho", "n": n, "gia": _GIA.get(p, 0.0)}
            # Co theo nhịp đăng (18/10/2026): {id nguồn: [số bài cấu hình, lý do]} — phễu lượt và
            # sổ co giãn (`_ghi_co_gian`) đọc lại sau lượt.
            co = {str(x["id"]): [int(x.get("so_bai_moi_lan") or 5), str(x.get("ly_do_co_gian") or "")]
                  for x in ds if p in CP.CO_GIAN_NEN_TANG and ("so_bai_hieu_luc" in x)}
            if co:
                ph["co_gian"] = co
            if p == "youtube":
                ph.update(actor="youtube", uoc_usd=0.0)
            elif p == "threads":
                # 17/10/2026: actor HỒ SƠ (0,002 USD/tài khoản, 4–10 bài mới nhất) thay chế độ
                # "user" của futurizerush (0,137 USD/tài khoản/lượt); `du_phong` giữ đủ thông tin
                # để `_du_phong_threads` dựng lượt futurizerush khi actor hồ sơ hỏng cả lượt.
                ten = [_chuan_dinh_danh(p, x["dinh_danh"]) for x in ds]
                ph.update(actor=A._ACTORS["threads_ho_so"],
                          payload={"profiles": ten, "includePosts": True}, limit=len(ten),
                          khoi=0.0, uoc_usd=_uoc_phan(p, len(ds), n),
                          du_phong={"actor": A._ACTORS["threads"], "mem": A._MEMORY.get("threads"),
                                    "payload": {"mode": "user", "usernames": ten, "max_posts": n},
                                    "limit": n * len(ten), "gia": A._UNIT_COST["threads"],
                                    "khoi": A._START_COST["threads"],
                                    "uoc_usd": _uoc_phan_user_threads(len(ds), n)})
            else:
                ten = [x["dinh_danh"].lstrip("@") for x in ds]
                if p == "tiktok":
                    payload, limit = account_tool._payload_tiktok(ten, n), n * len(ten)
                elif p == "instagram":
                    payload, limit = account_tool._payload_instagram(ten), len(ten)
                else:
                    payload = account_tool._payload_facebook([x["dinh_danh"] for x in ds], n)
                    limit = n * len(ds)
                ph.update(actor=account_tool._ACTOR[p], payload=payload, limit=limit,
                          uoc_usd=_uoc_phan(p, len(ds), n))
                if p == "tiktok":
                    TDA.gan_ho_so(ph, ten, n)
                    if not ph.get("bo_chuyen"):
                        # Bảng chọn đổi về actor cũ (clockworks): tính theo VIDEO, không theo yêu
                        # cầu — sổ (`quet_lon._so_tien`) và ước tính theo giá của actor đó.
                        g = TDA._GIA_DU_PHONG["tiktok_ho_so"]
                        ph.update(gia=g, uoc_usd=round(len(ds) * n * g * _HE_SO_UOC, 4))
                elif p == "facebook":
                    # 17/10/2026: thedoor (rẻ nửa giá, có view video), actor cũ làm dự phòng.
                    TDA.gan_fb_trang(ph, [x["dinh_danh"] for x in ds], n)
            ra.setdefault(p, []).append(ph)
    return ra


#: Khoá sổ co giãn trong sổ mốc của dự án (`doc_moc_tk`): {id nguồn: {"day_du_luc": iso lần cuối
#: lấy ĐỦ số bài cấu hình, "bao_hoa": lượt trước lấy đủ số đã co mà bài nào cũng mới}}.
KHOA_CO_GIAN = "co_gian_nguon"


def _gio_iso(s) -> datetime.datetime | None:
    try:
        x = datetime.datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    return x if x.tzinfo else x.replace(tzinfo=_VN)


def _co_gian_nguon(ma: str, du_an: dict, nguon: list[dict],
                   bay_gio: datetime.datetime | None = None) -> list[dict]:
    """Bản sao nguồn kèm `so_bai_hieu_luc` + `ly_do_co_gian` (`dashboard.chi_phi.so_bai_co_gian`):
    co N bài mỗi lần theo nhịp đăng quan sát được (số bài cao nhất một ngày trong 14 ngày × số
    ngày từ lần quét trước × 1,5 + 2, sàn 3, trần = số cấu hình). Lấy đủ khi: tắt, chiến dịch đang
    chạy, lượt trước bão hoà, quá `ngay_day_du` ngày từ lần lấy đủ cuối (làm mới số liệu bài cũ),
    chưa có bài. Không đo được nhịp (kho lỗi) thì giữ nguyên — lấy đủ như cũ."""
    from dashboard import chi_phi as CP
    from dashboard import lich_quet as LQ
    cfg = CP.cau_hinh_co_gian(du_an)
    if not cfg["bat"] or not any(n.get("nen_tang") in CP.CO_GIAN_NEN_TANG for n in nguon):
        return nguon
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    try:
        nhip = K.nhip_dang_nguon(ma, CP.CO_GIAN_NGAY_NHIP)
        cd = LQ.chien_dich_dang_chay(K.lich_chien_dich(ma), bay_gio) is not None
    except K.LoiKho:
        return nguon
    so = doc_moc_tk(ma).get(KHOA_CO_GIAN) or {}
    ra = []
    for n in nguon:
        st = so.get(str(n["id"])) if isinstance(so.get(str(n["id"])), dict) else {}
        dd = _gio_iso(st.get("day_du_luc"))
        # Lịch hằng ngày lệch vài phút: còn dưới `GIO_DUNG_SAI` giờ thì coi như đã đủ ngày.
        day_du = dd is None or (bay_gio - dd).total_seconds() >= (
            cfg["ngay_day_du"] * 24 - K.GIO_DUNG_SAI) * 3600
        ky = max(1, int(n.get("chu_ky_ngay") or 1))
        qc = n.get("quet_cuoi")
        khoang = (max(ky, (bay_gio - qc).total_seconds() / 86400)
                  if isinstance(qc, datetime.datetime) else ky)
        m, ly = CP.so_bai_co_gian(n.get("nen_tang"), int(n.get("so_bai_moi_lan") or 5),
                                  nhip.get(int(n["id"])), khoang, cfg, day_du=day_du,
                                  bao_hoa=bool(st.get("bao_hoa")), chien_dich=cd)
        ra.append({**n, "so_bai_hieu_luc": m, "ly_do_co_gian": ly})
    return ra


def _ghi_co_gian(ma: str, v, nguon: dict[int, dict], theo_nguon: dict[int, list],
                 bay_gio: datetime.datetime | None = None) -> list[str]:
    """Sau lượt: ghi sổ co giãn (lấy đủ → `day_du_luc`; lấy đủ số đã co mà bài cũ nhất vẫn mới hơn
    lần quét trước → `bao_hoa`, lượt sau lấy đủ để không sót) và trả câu phễu: co bao nhiêu bài,
    tiết kiệm bao nhiêu, nguồn nào làm mới đủ, nguồn nào bão hoà. Không bao giờ ném."""
    from dashboard import chi_phi as CP
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    try:
        so = dict(doc_moc_tk(ma).get(KHOA_CO_GIAN) or {})
        bot = usd = 0.0
        co: list[str] = []
        du: list[str] = []
        bh: list[str] = []
        for p, ph in v.cac_phan():
            if (p not in CP.CO_GIAN_NEN_TANG or ph.get("trang_thai") not in ("xong", "mot_phan")
                    or not ph.get("co_gian")):
                continue
            dung = int(ph.get("n") or 0)
            for nid, (so_cfg, ly) in ph["co_gian"].items():
                x = nguon.get(int(nid))
                if x is None:
                    continue
                ten = _ten_nguon(x)
                st = dict(so.get(nid) or {})
                if dung >= int(so_cfg):
                    st["day_du_luc"] = bay_gio.isoformat(timespec="seconds")
                    st["bao_hoa"] = False
                    if ly.startswith("làm mới"):
                        du.append(ten)
                else:
                    dong = [dt for _, dt in theo_nguon.get(int(nid)) or [] if dt]
                    qc = x.get("quet_cuoi")
                    st["bao_hoa"] = bool(isinstance(qc, datetime.datetime) and dong
                                         and len(dong) >= dung and min(dong) > qc)
                    if st["bao_hoa"]:
                        bh.append(ten)
                    bot += int(so_cfg) - dung
                    usd += ((int(so_cfg) - dung) * _GIA["facebook"] if p == "facebook" else
                            (math.ceil(int(so_cfg) / TDA.TT.BAI_MOI_TRANG)
                             - math.ceil(dung / TDA.TT.BAI_MOI_TRANG)) * _GIA["tiktok"])
                    co.append(f"{ten} {so_cfg}→{dung}")
                so[nid] = st
        ghi_moc_tk(ma, {KHOA_CO_GIAN: so})
    except Exception as e:  # sổ co giãn hỏng không làm hỏng lượt (lượt sau lấy đủ)
        if type(e).__name__ == "MatQuyen":
            raise
        return [f"co số bài theo nhịp đăng: không ghi được sổ ({type(e).__name__})"]
    ra = []
    if co:
        ra.append(f"co số bài theo nhịp đăng: {len(co)} nguồn bớt {int(bot)} bài "
                  f"(≈ {_usd3(usd)} USD) — " + ", ".join(co[:6]) + ("…" if len(co) > 6 else ""))
    if du:
        ra.append("làm mới đủ số bài cấu hình (số liệu bài cũ): " + ", ".join(du[:6]))
    if bh:
        ra.append("nguồn bão hoà (lấy đủ số đã co mà bài nào cũng mới) — lượt sau lấy đủ: "
                  + ", ".join(bh[:6]))
    return ra


def _ten_nguon(x: dict) -> str:
    """Tên ngắn của nguồn cho phễu: tên trang Facebook trong link, còn lại định danh."""
    dd = str(x.get("dinh_danh") or x.get("ten") or x.get("id"))
    m = re.search(r"facebook\.com/([^/?#]+)", dd, re.IGNORECASE)
    return m.group(1) if m else dd.lstrip("@")


def uoc_tinh(nguon: list[dict]) -> dict[str, float]:
    """USD ước tính mỗi nền tảng cho danh sách nguồn (theo đúng cách chia phần)."""
    return {p: round(sum(ph["uoc_usd"] for ph in cac), 4) for p, cac in chia_phan(nguon).items()}


def giu_cho_phan(ph: dict) -> float:
    """USD TRƯỜNG HỢP XẤU NHẤT của một phần theo dõi nguồn — ước tính đường chính, hoặc (phần có
    dự phòng ghi `du_phong.uoc_usd`) phí khởi động đường chính (đã mất khi nó hỏng) + dự phòng cho
    mọi nguồn của phần, lấy số lớn hơn. Dự phòng chỉ chạy khi đường chính KHÔNG ra bài (Facebook:
    cho trang thiếu; Threads: cả lượt 0 hồ sơ), nên hai khoản không cộng đủ cùng lúc.

    Vì sao (soát 17/10/2026): ước tính hiển thị theo giá đường chính (thedoor 0,0025 USD/bài, hồ
    sơ Threads 0,002 USD/tài khoản), còn dự phòng đắt gấp 2 (Facebook) tới ~50 lần (futurizerush
    0,137 USD/tài khoản) — giữ chỗ / trần chỉ theo đường chính thì dự phòng gần như không bao giờ
    đủ tiền chạy, hoặc ăn vào phần đã giữ cho bình luận, kiểm độ phủ, web."""
    uoc = float(ph.get("uoc_usd") or 0)
    dp = ph.get("du_phong") if isinstance(ph.get("du_phong"), dict) else {}
    if not dp.get("uoc_usd"):
        return round(uoc, 4)
    return round(max(uoc, float(ph.get("khoi") or 0) * _HE_SO_UOC + float(dp["uoc_usd"])), 4)


def _tran_phan(p: str, ph: dict, con: float, con_viec: float = float("inf")) -> float:
    """Trần USD (`maxTotalChargeUsd`) của một phần theo dõi nguồn: min(trần console của nền tảng,
    phần còn của tháng `con`, phần còn của VIỆC `con_viec`, max(sàn 0,1, ước tính × 1,5)).
    Facebook: dự phòng (actor cũ) chạy TRONG phần, tiêu phần trần còn lại sau thedoor
    (`theo_doi_api.du_phong_fb`) → mức trần chừa chỗ cho nó (`giu_cho_phan`). Soát 17/10/2026:
    trần cũ max(0,1; ước × 1,5) với 2 trang × 5 bài là 0,1 — thedoor lỗi sau khi tạo run còn 0,09,
    dự phòng bị bỏ đúng lúc thedoor hỏng hẳn. Threads: dự phòng là phần RIÊNG, có trần riêng."""
    uoc = float(ph.get("uoc_usd") or 0)
    muc = max(_TRAN_TOI_THIEU, uoc * _HE_SO_TRAN)
    if p == "facebook":
        # Làm tròn LÊN tới cent rồi cộng 0,02 (soát lại 17/10/2026): `du_phong_fb` làm tròn XUỐNG
        # phần còn (trần − đã tiêu) rồi so với giá dự phòng × hệ số ước — làm tròn xuống hai đầu ăn
        # hết khoảng dư 0,3 × 0,01, nên ~1/3 tổ hợp trang × bài (4×5, 8×5, 10×10…) bỏ oan trang
        # cuối dù tháng và việc còn nhiều tiền. Vẫn kẹp bởi trần console / tháng / việc bên dưới.
        muc = math.ceil(max(muc, giu_cho_phan(ph)) * 100 - 1e-9) / 100 + 0.02
    return round(min(A._tran_nen_tang(p, nen=True)[1], con, con_viec, muc), 2)


def _cat_theo_ngan_sach(nguon: list[dict], con_usd: float) -> tuple[list[dict], list[dict]]:
    """Giữ nguồn theo thứ tự (cũ nhất trước) tới khi ước tính vượt `con_usd`. Nguồn miễn phí
    (YouTube) luôn giữ. -> (giữ, để lượt sau)."""
    giu, bo = [], []
    for n in nguon:
        if not _GIA.get(n["nen_tang"]):
            giu.append(n)
            continue
        if sum(uoc_tinh([*giu, n]).values()) <= con_usd + 1e-9:
            giu.append(n)
        else:
            bo.append(n)
    return giu, bo


def _nen_tang_dung_duoc(p: str) -> tuple[bool, str]:
    """Công tắc nền tảng ở "Năng lực → Quét mạng xã hội" + điều kiện riêng (key YouTube)."""
    if p == "youtube" and not A._youtube_co_key():
        return False, "máy chạy Mark chưa có YOUTUBE_DATA_API_KEY"
    _, _, bat = A._tran_nen_tang(p, nen=True)
    return (True, "") if bat else (False, A._ly_do_tat(p))


def _viec_dang_do(ma: str) -> dict | None:
    """Việc `theo_doi` CHƯA kết thúc của cùng dự án trong sổ việc nền (kể cả đang xếp hàng)
    — review 14/10: hai lịch/hai chat cùng gõ /theodoi hapas thì cả hai qua kiểm tra lượt
    đang chạy (lượt chỉ mở khi việc bắt đầu) và quét trùng nguồn."""
    import viec_nen
    for d in reversed(viec_nen.tat_ca()):
        if (d.get("loai") == "theo_doi" and (d.get("tham_so") or {}).get("du_an") == ma
                and d.get("trang_thai") in viec_nen.TRANG_THAI_DANG):
            return d
    return None


def ke_hoach(ma: str, moi_nguon: bool = False) -> dict:
    """Đọc kho + console, quyết định lượt này quét gì. Không gọi Apify, không tốn tiền.
    `moi_nguon` (lịch quét tự động kiểu chiến dịch, 15/10/2026): quét MỌI nguồn đang theo dõi,
    không xét chu kỳ của nguồn.

    -> {"loi": câu báo, "ma_loi": mã} khi không chạy được (mã: khong_co_du_an, du_an_tat,
    dang_chay, kho_loi, khong_co_gi, het_ngan_sach, khong_quet_duoc); ngược lại {"du_an",
    "nguon", "bo_qua" (nguồn không quét lượt này + lý do), "uoc_tinh", "con_thang",
    "tran_thang", "da_tieu"}."""
    try:
        du_an = K.doc_du_an(ma)
        if not du_an:
            co = ", ".join(x["ma"] for x in K.cac_du_an()) or "chưa có dự án nào"
            return {"ma_loi": "khong_co_du_an",
                    "loi": f"Không có dự án '{ma}' trong kho lắng nghe. Dự án đang có: {co}. "
                           "Thêm dự án trên dashboard social.hapas.vn."}
        if not du_an["dang_bat"]:
            return {"ma_loi": "du_an_tat",
                    "loi": f"Dự án {du_an['ten']} đang tắt trên dashboard — lượt này không quét."}
        dang = K.luot_dang_chay(ma)
        if dang:
            return {"ma_loi": "dang_chay",
                    "loi": f"Lượt theo dõi trước của {du_an['ten']} còn đang chạy "
                           f"(mã {dang.get('ma_viec') or dang['id']}) — đợi lượt đó xong."}
        toi_han = K.nguon_dang_theo_doi(ma) if moi_nguon else K.nguon_toi_han(ma)
        dem = K.dem_nguon(ma) if not toi_han else {}
        da_tieu = K.da_tieu_thang(ma)
    except K.LoiKho as e:
        return {"ma_loi": "kho_loi", "loi": f"Kho lắng nghe chưa dùng được: {e}."}
    if not toi_han and tk_co_bat(du_an):
        # Đợt 2c: tìm theo từ khoá là việc của cả dự án — chạy được dù chưa nguồn nào tới hạn.
        tran = float(du_an["tran_usd_thang"] or 0)
        return {"du_an": du_an, "nguon": [], "bo_qua": [], "uoc_tinh": {},
                "con_thang": max(0.0, tran - da_tieu), "tran_thang": tran, "da_tieu": da_tieu}
    if not toi_han:
        return {"ma_loi": "khong_co_gi",
                "loi": (f"Chưa có nguồn nào của {du_an['ten']} tới hạn quét "
                        f"(đang theo dõi {dem.get('dang_theo_doi', 0)}, tạm dừng "
                        f"{dem.get('tam_dung', 0)}). Thêm nguồn hoặc đổi chu kỳ trên dashboard.")}
    bo_qua: list[tuple[dict, str]] = []
    dung: dict[str, tuple[bool, str]] = {}
    con_lai = []
    for n in toi_han:
        p = n["nen_tang"]
        if p not in dung:
            dung[p] = _nen_tang_dung_duoc(p)
        if dung[p][0]:
            con_lai.append(n)
        else:
            bo_qua.append((n, dung[p][1]))
    for n in con_lai[TOI_DA_NGUON:]:
        bo_qua.append((n, f"quá {TOI_DA_NGUON} nguồn một lượt — để lượt sau"))
    con_lai = con_lai[:TOI_DA_NGUON]
    # Co số bài mỗi lần theo nhịp đăng (18/10/2026) TRƯỚC khi cắt theo ngân sách: nguồn rẻ đi thì
    # vừa ngân sách hơn.
    con_lai = _co_gian_nguon(ma, du_an, con_lai)
    tran = float(du_an["tran_usd_thang"] or 0)
    con_thang = max(0.0, tran - da_tieu)
    giu, het_tien = _cat_theo_ngan_sach(con_lai, con_thang)
    for n in het_tien:
        bo_qua.append((n, f"hết ngân sách tháng của dự án ({_usd(da_tieu)}/{_usd(tran)} USD)"))
    if not giu:
        ly = bo_qua[0][1] if bo_qua else "không có nguồn quét được"
        # `giu` rỗng: hoặc mọi nguồn còn lại đều vượt phần còn của tháng (het_tien), hoặc không
        # còn nguồn nào (nền tảng tắt / thiếu key).
        return {"ma_loi": "het_ngan_sach" if het_tien else "khong_quet_duoc",
                "loi": f"Lượt theo dõi {du_an['ten']} không quét được nguồn nào: {ly}."}
    return {"du_an": du_an, "nguon": giu, "bo_qua": bo_qua, "uoc_tinh": uoc_tinh(giu),
            "con_thang": con_thang, "tran_thang": tran, "da_tieu": da_tieu}


# ───────────────────────────── lệnh ─────────────────────────────
def lenh_theodoi(doi_so: str) -> str:
    """`/theodoi <mã dự án>` → tạo việc nền, trả lời NGAY (không gọi model, không bịa)."""
    ma = (doi_so or "").strip().split(" ", 1)[0].lower()
    if not ma:
        try:
            ds = ", ".join(f"{x['ma']} ({x['ten']})" for x in K.cac_du_an()) or "chưa có"
        except K.LoiKho as e:
            return f"Kho lắng nghe chưa dùng được: {e}."
        return (f"Cách dùng: {_LENH} <mã dự án>, vd `{_LENH} hapas`. Dự án đang có: {ds}. "
                "Quét tự động theo giờ/ngày/tuần/chiến dịch: tab Lịch quét trên dashboard "
                "social.hapas.vn (Mark tự chạy, kết quả xem trên dashboard). Lịch hằng ngày trên "
                f"console (Lịch chạy → Giao việc `{_LENH} <mã dự án>`) vẫn chạy như cũ.")
    return tao_luot(ma)["cau"]


#: Khoá tạo việc theo dự án (review 15/10, M1): lịch console (luồng job) và lịch dashboard (luồng
#: nhịp) cùng phút cùng dự án thì cả hai đều qua `_viec_dang_do` trước khi bên kia kịp ghi sổ —
#: hai việc quét trùng nguồn, trả tiền hai lần. Giữ khoá từ lúc kiểm việc dở tới lúc ghi việc vào
#: sổ. Hai TIẾN TRÌNH thì đã có quyền chủ việc nền (`viec_nen`): bản không giữ quyền không tạo việc.
_KHOA_TAO: dict[str, threading.Lock] = {}
_KHOA_TAO_SO = threading.Lock()


def _khoa_tao(ma: str) -> threading.Lock:
    with _KHOA_TAO_SO:
        return _KHOA_TAO.setdefault(ma, threading.Lock())


def tao_luot(ma: str, *, moi_nguon: bool = False, lich: dict | None = None) -> dict:
    """Tạo MỘT việc nền theo dõi dự án `ma` — đường chung của `/theodoi` (chat, lịch console)
    và lịch quét tự động trên dashboard (`quet_tu_dong`, `lich` = {"id", "moc"}). Cùng dự án thì
    chạy tuần tự (`_khoa_tao`): kiểm việc dở → kế hoạch → ghi sổ việc là MỘT bước.

    -> {"ok": True, "ma_viec", "cau"} hoặc {"ok": False, "ma_loi", "cau"}; `cau` là câu trả
    lời chat. Mã lỗi: các mã của `ke_hoach`, cùng dang_chay (việc cũ chưa xong), het_ngan_sach
    (lịch: tháng của dự án đã hết), het_ngan_sach_apify (ngân sách việc nền của tài khoản),
    tu_choi (sổ việc nền từ chối — hàng đợi đầy, tiến trình khác giữ quyền)."""
    with _khoa_tao(ma):
        return _tao_luot(ma, moi_nguon=moi_nguon, lich=lich)


def _tao_luot(ma: str, *, moi_nguon: bool, lich: dict | None) -> dict:
    cu = _viec_dang_do(ma)
    if cu:
        return {"ok": False, "ma_loi": "dang_chay", "ma_viec": cu.get("ma"),
                "cau": (f"Đã có việc theo dõi '{ma}' chưa xong (mã {cu.get('ma')}) — không tạo "
                        "thêm để khỏi quét trùng nguồn. Gõ /viec để xem tiến độ.")}
    kh = ke_hoach(ma, moi_nguon=moi_nguon)
    if kh.get("loi"):
        return {"ok": False, "ma_loi": kh.get("ma_loi") or "loi", "cau": kh["loi"]}
    if lich is not None and kh["con_thang"] < 0.01:
        # Lịch tự động KHÔNG chạy khi tháng của dự án đã hết (chat vẫn chạy được phần miễn phí).
        return {"ok": False, "ma_loi": "het_ngan_sach",
                "cau": (f"hết ngân sách tháng của dự án ({_usd(kh['da_tieu'])}/"
                        f"{_usd(kh['tran_thang'])} USD)")}
    import quet_lon
    import viec_nen
    phan = chia_phan(kh["nguon"])
    # Giữ chỗ phần theo dõi nguồn = TRƯỜNG HỢP XẤU NHẤT (`giu_cho_phan`), không chỉ ước tính đường
    # chính (soát 17/10/2026): dự phòng Threads (futurizerush "user", ~0,137 USD/tài khoản) và
    # Facebook (actor cũ, gấp đôi thedoor) không nằm trong ước tính — vòng phần kẹp theo ngân sách
    # CỦA VIỆC (`_con_viec`) thì dự phòng không bao giờ đủ tiền, hoặc ăn vào phần giữ cho sau.
    tong_uoc = round(sum(ph["uoc_usd"] for cac in phan.values() for ph in cac), 2)
    tong = round(sum(giu_cho_phan(ph) for cac in phan.values() for ph in cac), 2)
    dp_phan = round(max(0.0, tong - tong_uoc), 2)
    da = kh["du_an"]
    # Bình luận (đợt 2b): chưa biết bài nào sẽ được cào nên giữ chỗ theo trần cấu hình, giá
    # Facebook; tiền thật vẫn chốt theo run id.
    bl_uoc = round(uoc_binh_luan_du_an(da), 2)
    ns_apify, hm, _ = quet_lon.ngan_sach(quet_lon.tran_usd_nen())
    # Tìm theo từ khoá rồi bình luận chỉ dùng phần ngân sách việc nền còn lại sau phần bài — lúc
    # chạy mỗi lượt actor vẫn bị kẹp theo trần console, phần còn của tháng và ngân sách việc.
    # Threads theo sản lượng lượt trước (17/10/2026, `san_luong_du_kien`): giữ chỗ theo trần cũ
    # (21 từ × 10 bài ≈ 0,79 USD) làm lượt bị từ chối / Threads bị co oan khi ngân sách chật.
    # Đường 1 giữ đúng trần run (`giu_cho_tu_khoa` → `tran_threads_1`) — cùng con số lúc chạy.
    tk_uoc = round(giu_cho_tu_khoa(da, _fb_toi_da(), doc_moc_tk(ma)), 2)
    tk_uoc = round(max(0.0, min(tk_uoc, ns_apify - tong)), 2)
    tong = round(tong + tk_uoc, 2)
    bl_uoc = round(max(0.0, min(bl_uoc, ns_apify - tong)), 2)
    tong = round(tong + bl_uoc, 2)
    # Kiểm độ phủ (review M5): lượt tới hạn kiểm thì giữ chỗ đúng trần mỗi lần — khớp dự báo
    # trang Ngân sách (`dashboard.chi_phi.du_bao_do_phu`).
    dp_uoc = round(max(0.0, min(uoc_do_phu(da), ns_apify - tong)), 2)
    tong = round(tong + dp_uoc, 2)
    if tong > ns_apify + 1e-9:
        return {"ok": False, "ma_loi": "het_ngan_sach_apify", "cau": (
            f"Chưa chạy: lượt này ước tính {_usd(tong)} USD mà ngân sách Apify còn dùng được "
            f"cho việc nền là {_usd(ns_apify)} USD (trần console hoặc hạn mức tháng của tài "
            "khoản). Giảm số nguồn/số bài mỗi lần trên dashboard hoặc đợi tháng sau.")}
    ngan_sach = round(min(kh["con_thang"], ns_apify, max(tong, 0.01) * _HE_SO_TRAN), 2)
    tham_so: dict = {"du_an": ma, "ngay": _hom_nay(),
                     "nguon": sorted(int(n["id"]) for n in kh["nguon"])}
    if moi_nguon:
        tham_so["moi_nguon"] = True
    if lich is not None:
        # Mốc của lịch nằm trong tham số: khoá chống trùng của sổ việc nền (6 giờ) phân biệt
        # từng mốc — lượt mỗi giờ không bị coi là "việc cũ", còn cùng một mốc lỡ nhận hai lần
        # thì trả lại đúng việc cũ.
        tham_so.update(lich_id=int(lich["id"]), moc=str(lich.get("moc") or ""))
    kq = viec_nen.tao_viec(
        "theo_doi", tham_so,
        {p: {"phan": cac} for p, cac in phan.items()}, {"usd": tong,
                                                         "phut": max(3, len(kh["nguon"]) // 4)
                                                         + (3 if bl_uoc else 0)
                                                         + (3 if tk_uoc else 0)
                                                         + (5 if dp_uoc else 0)},
        ngan_sach, [f"bỏ qua {len(kh['bo_qua'])} nguồn"] if kh["bo_qua"] else [],
        con_lai_thang=(hm or {}).get("con_lai"))
    if kq.get("tu_choi") or kq.get("da_xong_truoc"):
        return {"ok": False, "ma_loi": "tu_choi" if kq.get("tu_choi") else "trung",
                "ma_viec": kq.get("ma_viec"),
                "cau": str(kq.get("ket_qua") or kq.get("note") or "Không tạo được việc theo dõi.")}
    dem: dict[str, int] = {}
    for n in kh["nguon"]:
        dem[n["nen_tang"]] = dem.get(n["nen_tang"], 0) + 1
    ds = ", ".join(f"{_TEN.get(p, p)} {k}" for p, k in dem.items())
    cau = (f"Đã nhận lượt theo dõi {kh['du_an']['ten']} (mã {kq.get('ma_viec')}): "
           + (f"{len(kh['nguon'])} nguồn ({ds})" if kh['nguon'] else
              "chưa nguồn nào tới hạn — lượt này chỉ tìm theo từ khoá")
           + f", ước tính tối đa {_usd(tong)} USD" + _cau_chi_that(ma)
           + (f" (gồm tới {_usd(dp_phan)} USD dự phòng nếu actor chính hỏng)" if dp_phan else "")
           + (f" (gồm tới {_usd(tk_uoc)} USD tìm theo từ khoá)" if tk_uoc else "")
           + (f" (gồm tới {_usd(bl_uoc)} USD cào bình luận)" if bl_uoc else "")
           + (f" (gồm tới {_usd(dp_uoc)} USD kiểm độ phủ)" if dp_uoc else "")
           + "; ngân sách tháng "
           f"của dự án còn {_usd(kh['con_thang'])}/{_usd(kh['tran_thang'])} USD"
           # Gói Apify (18/10/2026): trần THẬT của cả tài khoản — trần dự án 30 USD mà gói FREE
           # còn 5 USD thì câu cũ "còn 14,56/30" làm người đọc tưởng còn ~10 lượt.
           + _cau_goi(hm) + ". Xong Mark nhắn kết quả vào đây.")
    if kh["bo_qua"]:
        ly = sorted({x[1] for x in kh["bo_qua"]})
        cau += f" Bỏ qua {len(kh['bo_qua'])} nguồn: {'; '.join(ly)[:300]}."
    return {"ok": True, "ma_viec": kq.get("ma_viec"), "cau": cau, "uoc_usd": tong,
            "so_nguon": len(kh["nguon"]), "bo_qua": len(kh["bo_qua"])}


def _cau_chi_that(ma: str, bay_gio: datetime.datetime | None = None) -> str:
    """" (thật N lượt gần nhất: a–b, trung vị c USD)" — ước tính lúc nhận là mức TỐI ĐA (giữ chỗ
    cào hết bình luận), chi thật 7 lượt 16–17/10 chỉ 30–100% số đó (18/10/2026). "" khi chưa đủ
    lượt hay kho lỗi."""
    try:
        from dashboard import chi_phi as CP
        t = CP.chi_luot_thuc(K.chi_luot_gan(ma), bay_gio or datetime.datetime.now(_VN))
    except Exception as e:  # kho / dữ liệu lỗi: câu không có phần này
        if type(e).__name__ == "MatQuyen":
            raise
        return ""
    if not t.get("co"):
        return ""
    return (f" (thật {t['so_luot']} lượt gần nhất: {_usd(t['thap'])}–{_usd(t['cao'])}, "
            f"trung vị {_usd(t['trung_vi'])} USD)")


def _cau_goi(hm: dict | None) -> str:
    """"; gói Apify còn X/Y USD tới DD/MM" từ hạn mức tháng (`quet_lon.ngan_sach`) — "" khi không
    hỏi được Apify."""
    if not isinstance(hm, dict) or hm.get("con_lai") is None:
        return ""
    tran = f"/{_usd(float(hm['tran']))}" if hm.get("tran") else ""
    het = hm.get("reset")
    return (f"; gói Apify còn {_usd(float(hm['con_lai']))}{tran} USD"
            + (f" tới {het:%d/%m}" if isinstance(het, datetime.datetime) else ""))


# ───────────────────────────── đọc bài của một phần ─────────────────────────────
def _dong_tu_tai_khoan(p: str, tk: dict) -> list[tuple[dict, datetime.datetime | None]]:
    """Kết quả `account_tool._doc_*` của MỘT tài khoản -> [(dòng kiểu social_listen, ngày)]."""
    hs = tk.get("ho_so") or {}
    ra = []
    for b in tk.get("bai") or []:
        goc = b.get("_goc") or {}
        tags = [str(h).lstrip("#") for h in b.get("hashtag") or [] if h]
        ra.append(({
            "platform": p, "kenh": str(hs.get("ten") or ""), "username": str(hs.get("tai_khoan") or ""),
            "followers": hs.get("followers"), "views": b.get("view"), "likes": b.get("like"),
            "comments": b.get("binh_luan"), "shares": b.get("share"),
            "hashtags": ", ".join(tags)[:500], "text": str(b.get("noi_dung") or "")[:1000],
            "link": str(b.get("link") or ""), "_goc_id": str(goc.get("id") or goc.get("postId")
                                                             or "") or None,
            "_goc_vao": str(goc.get("inputUrl") or goc.get("facebookUrl") or ""),
            # Id số ổn định của bài Facebook (17/10/2026): pfbid trong link đổi mỗi lượt cào —
            # kho khớp bản trùng theo id này (`khu_trung_fb`). Ghi vào sổ dòng trên đĩa cùng bài
            # nên khởi động lại vẫn còn. Thedoor: `_goc.postId` (= `post.id`, `theo_doi_api.
            # doc_thedoor`), không có thì id trong link `/<id trang>/posts/<id bài>`; actor cũ:
            # `postId`, link pfbid thì không có id.
            **({"ma_so_fb": KT.ma_so_fb({**b, "_goc": goc})} if p == "facebook" else {}),
        }, b.get("ngay")))
    return ra


def ghep_nguon(p: str, ket: dict[str, dict], nguon: list[dict]) -> tuple[dict[int, list],
                                                                          dict[int, str]]:
    """Kết quả actor (theo tài khoản) -> ({id nguồn: [(dòng, ngày)]}, {id nguồn: lỗi})."""
    theo_khoa = {_chuan_dinh_danh(p, x["dinh_danh"]): x for x in nguon}
    ra: dict[int, list] = {int(x["id"]): [] for x in nguon}
    loi: dict[int, str] = {}
    for k, tk in ket.items():
        dong = _dong_tu_tai_khoan(p, tk)
        if p == "facebook":
            # Actor Facebook đặt khoá theo TÊN TRANG; ghép về nguồn theo URL đầu vào của bài.
            for d, dt in dong:
                n = theo_khoa.get(_chuan_dinh_danh(p, d.get("_goc_vao") or ""))
                if n is None and len(nguon) == 1:
                    n = nguon[0]
                if n is not None:
                    ra[int(n["id"])].append((d, dt))
            continue
        n = theo_khoa.get(_chuan_dinh_danh(p, k))
        if n is None:
            continue
        if tk.get("ghi_chu") and not dong:
            loi[int(n["id"])] = str(tk["ghi_chu"])[:200]
        ra[int(n["id"])].extend(dong[:_so_bai_nguon(dict(n, nen_tang=p))])
    for nid, dong in ra.items():
        if not dong and nid not in loi:
            loi[nid] = "không lấy được bài nào (tài khoản riêng tư, đổi tên hoặc sai định danh?)"
    return ra, loi


def _doc_ket_qua(p: str, items: list, n: int, urls: list[str] | None = None) -> dict[str, dict]:
    import account_tool
    if p == "tiktok":
        return account_tool._doc_tiktok(items)
    if p == "instagram":
        return account_tool._doc_instagram(items, 12)
    if p == "threads":
        # Actor hồ sơ (dòng có `recent_posts`/`follower_count`) hoặc dự phòng futurizerush "user".
        if any(isinstance(it, dict) and ("recent_posts" in it or "follower_count" in it)
               for it in items):
            return _doc_threads_ho_so(items)
        return _doc_threads(items)
    # Facebook (17/10/2026): bài thedoor và/hoặc actor cũ (dự phòng, phần lập trước khi đổi actor).
    return TDA.doc_fb_trang(items, list(urls or []))


def _doc_threads_ho_so(items: list) -> dict[str, dict]:
    """Item scrapersdelight profile → {tài khoản: hồ sơ + bài} cùng dạng `_doc_threads` (để
    `_dong_tu_tai_khoan` dùng chung). Link bài đúng dạng futurizerush (`apify_tool._link_threads`) —
    khoá kho trùng với bài cùng tài khoản mà lượt tìm theo từ khoá đã ghi. Actor không có lượt xem:
    `view` None (kho giữ số cũ). Hồ sơ riêng tư / chưa bật Threads → ghi chú, không bài."""
    ra: dict[str, dict] = {}
    for k, x in A.doc_ho_so_threads(items).items():
        k = _chuan_dinh_danh("threads", k)
        goc = next((it for it in items if isinstance(it, dict)
                    and _chuan_dinh_danh("threads", str(it.get("username") or "")) == k), {})
        ghi = ("tài khoản Threads riêng tư" if goc.get("is_private")
               else "tài khoản chưa bật Threads" if goc.get("has_threads_profile") is False
               else "")
        ra[k] = {"ho_so": x["ho_so"], "ghi_chu": ghi, "bai": [{
            "ngay": dt, "view": None, "like": d["likes"], "binh_luan": d["comments"],
            "share": d["shares"], "noi_dung": d["text"], "link": d["link"],
            "hashtag": [t.strip() for t in str(d["hashtags"] or "").split(",") if t.strip()],
            "_goc": d["__goc"]} for d, dt in x["bai"]]}
    return ra


def _doc_threads(items: list) -> dict[str, dict]:
    """Item chế độ "user" của actor Threads -> {tài khoản đã xin: hồ sơ + bài} cùng dạng
    `account_tool._doc_*` (để `_dong_tu_tai_khoan` dùng chung). Bộ đọc từng bài là
    `apify_tool._chuan_threads` của social_listen; khoá là `requested_username` (đúng chữ Mark
    gửi — tài khoản đổi tên thì `username` khác) rồi mới tới `username`."""
    ra: dict[str, dict] = {}
    for d, dt in A._chuan_threads([it for it in items if isinstance(it, dict)
                                   and it.get("record_type", "post") == "post"]):
        g = d["__goc"]
        k = _chuan_dinh_danh("threads", str(g.get("requested_username") or d["username"] or ""))
        if not k:
            continue
        tk = ra.setdefault(k, {"ho_so": {
            "ten": d["kenh"] or k, "tai_khoan": d["username"] or k, "followers": d["followers"],
            "link": str(g.get("profile_url") or f"https://www.threads.com/@{k}")},
            "bai": [], "ghi_chu": ""})
        tk["bai"].append({
            "ngay": dt, "view": d["views"], "like": d["likes"], "binh_luan": d["comments"],
            "share": d["shares"], "noi_dung": d["text"], "link": d["link"],
            "hashtag": [t.strip() for t in str(d["hashtags"] or "").split(",") if t.strip()],
            "_goc": g})
    return ra


def _lay_youtube(nguon: list[dict]) -> tuple[dict[int, list], dict[int, str]]:
    """Video mới nhất của từng kênh qua YouTube Data API (miễn phí): channels → playlist
    uploads → playlistItems → videos. ~3 đơn vị quota mỗi kênh (search.list thì 100)."""
    ra: dict[int, list] = {int(x["id"]): [] for x in nguon}
    loi: dict[int, str] = {}
    kenh: dict[int, dict] = {}
    theo_id: dict[str, list[dict]] = {}
    for x in nguon:
        dd = x["dinh_danh"].strip()
        if re.fullmatch(r"UC[\w-]{22}", dd):
            theo_id.setdefault(dd, []).append(x)
            continue
        try:
            data = A._youtube_get("channels", {"part": "snippet,statistics,contentDetails",
                                               "forHandle": "@" + dd.lstrip("@")})
        except A.LoiYouTube as e:
            loi[int(x["id"])] = str(e)[:200]
            continue
        it = (data.get("items") or [None])[0]
        if it:
            kenh[int(x["id"])] = it
        else:
            loi[int(x["id"])] = "không tìm thấy kênh YouTube theo handle này"
    for lo in A._chunks(list(theo_id)):
        try:
            data = A._youtube_get("channels", {"part": "snippet,statistics,contentDetails",
                                               "id": ",".join(lo), "maxResults": 50})
        except A.LoiYouTube as e:
            for cid in lo:
                for x in theo_id[cid]:
                    loi[int(x["id"])] = str(e)[:200]
            continue
        thay = {str(it.get("id")): it for it in data.get("items") or [] if isinstance(it, dict)}
        for cid in lo:
            for x in theo_id[cid]:
                if cid in thay:
                    kenh[int(x["id"])] = thay[cid]
                else:
                    loi[int(x["id"])] = "không tìm thấy kênh YouTube theo id này"
    theo_nguon = {int(x["id"]): x for x in nguon}
    for nid, it in kenh.items():
        x = theo_nguon[nid]
        sn = it.get("snippet") or {}
        uploads = ((it.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
        if not uploads:
            loi[nid] = "kênh không có danh sách video công khai"
            continue
        try:
            # Không trần số video (chủ dự án 15/10): lật trang 50 video/trang, 1 đơn vị/trang.
            can = int(x.get("so_bai_moi_lan") or 5)
            ids, trang = [], None
            while len(ids) < can:
                q = {"part": "contentDetails", "playlistId": uploads,
                     "maxResults": min(50, can - len(ids))}
                if trang:
                    q["pageToken"] = trang
                pl = A._youtube_get("playlistItems", q)
                ids += [str((v.get("contentDetails") or {}).get("videoId") or "")
                        for v in pl.get("items") or [] if isinstance(v, dict)]
                trang = pl.get("nextPageToken")
                if not trang or not pl.get("items"):
                    break
            ra[nid] = _video_youtube([i for i in ids if i], {
                "kenh": str(sn.get("title") or x.get("ten") or ""),
                "followers": int((it.get("statistics") or {}).get("subscriberCount") or 0),
                "_quoc_gia": str(sn.get("country") or "")})
        except A.LoiYouTube as e:
            loi[nid] = str(e)[:200]
            continue
        if not ra[nid]:
            loi[nid] = "kênh chưa có video công khai"
    return ra, loi


def _video_youtube(ids: list[str], kenh: dict | None = None) -> list[tuple]:
    """videos.list (1 đơn vị / 50 video) -> [(dòng kiểu social_listen, ngày VN)]."""
    import html
    ra = []
    for lo in A._chunks(ids):
        data = A._youtube_get("videos", {"part": "snippet,statistics", "id": ",".join(lo),
                                         "maxResults": 50})
        for it in data.get("items") or []:
            if not isinstance(it, dict) or not it.get("id"):
                continue
            sn, st = it.get("snippet") or {}, it.get("statistics") or {}
            title = html.unescape(str(sn.get("title") or ""))
            desc = html.unescape(str(sn.get("description") or ""))
            tags = A._tags_from(f"{title} {desc}")
            if sn.get("tags"):
                tags = A._join([tags, A._join(sn.get("tags"))])
            k = kenh or {}
            ra.append(({
                "platform": "youtube",
                "kenh": k.get("kenh") or html.unescape(str(sn.get("channelTitle") or "")),
                "username": "", "followers": k.get("followers"),
                "_quoc_gia": k.get("_quoc_gia", ""),
                "_ngon_ngu": str(sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or ""),
                "views": int(st.get("viewCount") or 0), "likes": int(st.get("likeCount") or 0),
                "comments": int(st.get("commentCount") or 0), "shares": None,
                "hashtags": tags, "text": f"{title} — {desc}"[:1000],
                "link": f"https://www.youtube.com/watch?v={it['id']}",
            }, A._to_vn(sn.get("publishedAt"))))
    return ra


# ───────────────────────────── lọc + nhãn ─────────────────────────────
def chon_bai(du_an: dict, theo_nguon: dict[int, list], nguon: dict[int, dict],
             han_ai: float, bay_gio: datetime.datetime | None = None) -> tuple[list[dict], dict]:
    """Giữ bài liên quan tới dự án + gán nhãn. -> (dòng ghi kho, thống kê).

    • Bài cũ hơn `NGAY_GIU` ngày hoặc không có ngày: bỏ.
    • Có từ loại trừ của dự án: bỏ (luật cứng, không qua AI).
    • Nguồn `kenh_nha` (kênh của chính brand): giữ mọi bài; AI chỉ gán sắc thái/chủ đề.
    • Nguồn khác: chỉ xét bài NHẮC từ khoá dự án; AI phán giữ/loại (trùng tên, lạc đề…).
      AI hỏng/hết giờ/`khong_ro` thì giữ theo luật (đã nhắc từ khoá, nguồn do người chọn)."""
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    moc = bay_gio - datetime.timedelta(days=NGAY_GIU)
    tu_khoa = [str(x) for x in du_an.get("tu_khoa") or [] if str(x).strip()] or [du_an["ten"]]
    loai_tru = [str(x) for x in du_an.get("tu_loai_tru") or [] if str(x).strip()]
    tk = {"lay_duoc": 0, "qua_cu": 0, "khong_nhac": 0, "loai_tru": 0, "ai_loai": 0,
          "giu": 0, "ai": ""}
    cho: list[tuple[dict, datetime.datetime, dict]] = []
    thay: set[str] = set()
    for nid, dong in theo_nguon.items():
        n = nguon.get(nid)
        if n is None:
            continue
        for d, dt in dong:
            khoa = _khoa_bai(d["platform"], d.get("link") or "", {"id": d.get("_goc_id")})
            if khoa in thay:
                continue                 # trùng (đọc lại sau khởi động lại, hoặc nguồn trùng)
            thay.add(khoa)
            tk["lay_duoc"] += 1
            if not dt or dt < moc:
                tk["qua_cu"] += 1
                continue
            d["_khop"] = A._khop_tu_khoa(d, tu_khoa)
            d["_thi_truong"] = A._thi_truong(d, tu_khoa)
            if A._tu_loai_tru_khop(d, loai_tru):
                tk["loai_tru"] += 1
                continue
            if n.get("loai") != "kenh_nha" and not d["_khop"]:
                tk["khong_nhac"] += 1
                continue
            d["_khoa"] = khoa
            cho.append((d, dt, n))
    phan_xu: dict = {}
    tt: dict = {"_sac_thai": {}, "_chu_de": {}, "trang_thai": ""}
    if cho:
        phan_xu, tt = A._phan_xu_ai([(d, dt) for d, dt, _ in cho], tu_khoa,
                                    du_an.get("boi_canh") or du_an["ten"],
                                    du_an.get("thi_truong") or "VN", han_ai)
    tk["ai"] = tt.get("trang_thai") or ""
    ra = []
    for i, (d, dt, n) in enumerate(cho):
        px = phan_xu.get(i)
        if px and px[1] == "khong_ro":
            px = None                     # AI không chắc → về luật (như social_listen)
        nha = n.get("loai") == "kenh_nha"
        if px and not px[0] and not nha:
            tk["ai_loai"] += 1
            continue
        ly_do = "kenh_nha" if nha and not (px and px[0]) else (px[1] if px else "khop_tu_khoa")
        ra.append({
            "khoa": d["_khoa"], "nen_tang": d["platform"], "nguon_id": int(n["id"]),
            "link": d.get("link") or "", "tac_gia": str(d.get("kenh") or "")[:200],
            "tai_khoan": str(d.get("username") or "")[:200],
            "followers": _so_hay_none(d.get("followers")), "dang_luc": dt,
            "noi_dung": str(d.get("text") or "")[:1000],
            "hashtag": str(d.get("hashtags") or "")[:500],
            "khop_tu_khoa": bool(d.get("_khop")), "sac_thai": tt["_sac_thai"].get(i),
            "chu_de": tt["_chu_de"].get(i), "ly_do_giu": str(ly_do)[:60],
            "xem": _so_hay_none(d.get("views")), "thich": _so_hay_none(d.get("likes")),
            "binh_luan": _so_hay_none(d.get("comments")),
            "chia_se": _so_hay_none(d.get("shares")),
            **_cot_fb(d),
        })
    tk["giu"] = len(ra)
    return ra, tk


def _cot_fb(d: dict) -> dict:
    """{"ma_so_fb": id số} cho dòng ghi kho của bài Facebook (`khu_trung_fb`); {} với nền tảng
    khác — dòng TikTok/YouTube… giữ đúng các khoá cũ."""
    if (d.get("platform") or d.get("nen_tang")) != "facebook":
        return {}
    return {"ma_so_fb": KT.ma_so_fb(d)}


# ───────────────────────────── chạy nền ─────────────────────────────
def chay_viec(v) -> tuple[str, str]:
    """Runner của `viec_nen` cho loại `theo_doi`. -> (trạng thái việc, câu nhắn kết quả).

    Chạy trong BẢN SAO ngữ cảnh: các cờ Apify (`_NEN`, `_HUY`, `_HAN_CHOT`, `_NEN_TANG`,
    `_KHI_CO_RUN`) đặt ở đây không rò sang lượt khác dùng chung luồng. Việc do lịch quét tự
    động giao (`tham_so.lich_id`) thì báo kết quả cuối về lịch (`quet_tu_dong.ket_thuc_viec`)."""
    kq = contextvars.copy_context().run(_chay_viec, v)
    ts = v.d.get("tham_so") or {}
    lid = ts.get("lich_id")
    if lid:
        try:
            import quet_tu_dong
            quet_tu_dong.ket_thuc_viec(
                int(lid), v.ma, v.d.get("luot_id"), kq[0], kq[1],
                chi_phi_usd=float((v.d.get("chi_phi") or {}).get("usd") or 0),
                du_an=str(ts.get("du_an") or ""), moc=str(ts.get("moc") or ""))
        except Exception as e:  # noqa: BLE001 — báo lịch hỏng không làm hỏng việc đã xong
            print(f"[theo_doi] không báo được lịch #{lid}: {type(e).__name__}", flush=True)
    return kq


def chot_lai_chi_phi(d: dict, usd: float) -> bool:
    """Bước chốt lại chi phí ở nền (`viec_nen.Viec.tinh_lai_muon`, ~90 giây sau run cuối) thấy
    Apify tính thêm sau khi lượt đã đóng — phí sự kiện ghi trễ (đo 17/10/2026: 0,1948 → 0,2397
    USD): nâng `luot_quet.chi_phi_usd` của lượt (chỉ nâng; "đã tiêu tháng" cộng cột này) rồi báo
    dashboard. -> True khi xong hoặc không có lượt; False khi kho hỏng (lần sau thử lại)."""
    luot = d.get("luot_id")
    if not luot:
        return True
    try:
        cu = K.nang_chi_phi_luot(int(luot), usd)
    except K.LoiKho as e:
        print(f"[theo_doi] không chốt lại được chi phí lượt {luot}: {e}", flush=True)
        return False
    # Gói Apify sau khi phí ghi trễ đã vào (~90 giây sau run cuối, `A._han_muc_thang` nhớ 60 giây
    # nên số mới) — khối "Gói Apify" trang Ngân sách đúng hơn ảnh chụp lúc đóng lượt.
    ghi_han_muc_goi(int(luot), "chot_lai")
    if cu is not None:
        print(f"[theo_doi] lượt {luot}: chi phí chốt lại {_usd(cu)} → {_usd(usd)} USD",
              flush=True)
        _bao_dashboard(str((d.get("tham_so") or {}).get("du_an") or ""), int(luot))
    return True


def _ghi_phan(v, p: str, ph: dict, kq: dict[int, list], loi: dict[int, str]) -> None:
    """Ghi bài của một phần xuống đĩa (kèm id nguồn) và lỗi từng nguồn vào sổ việc."""
    rows = []
    for nid, dong in kq.items():
        for d, dt in dong:
            rows.append(({**d, "_nguon_id": nid}, dt))
    if rows:
        v.ghi_dong(p, rows, ph["id"])
    v.cap_nhat_phan(ph, loi_nguon={str(k): x for k, x in loi.items()})


def _chay_actor(v, p: str, ph: dict, cap: float, han: float,
                min_charge: float = 0.0) -> tuple[list, dict, Exception | None, float | None]:
    """Chạy / đọc tiếp MỘT lượt actor của phần `ph`, cùng kỷ luật với `quet_lon._mot_phan`:
    ghi run id ngay khi Apify trả; phần có run id thì đọc tiếp; phần đang gửi dở thì tìm run
    vừa tạo, không kiểm được thì KHÔNG gửi lại. -> (items, meta, lỗi, tiền phải coi như đã
    tiêu khi không kiểm được run cũ — None nếu không phải trường hợp đó)."""
    import quet_lon
    if ph.get("bo_chuyen"):              # nhiều yêu cầu TikTok API (`theo_doi_api`)
        return TDA.chay(v, p, ph, cap, han)
    actor = ph["actor"]
    A._NEN_TANG.set(p)
    A._KHI_CO_RUN.set(lambda run, meta: v.cap_nhat_phan(
        ph, run_id=run.get("id"), dataset_id=run.get("defaultDatasetId"), trang_thai="dang_chay"))
    items: list = []
    meta: dict = {}
    loi = None
    try:
        if ph.get("run_id"):
            items, meta = A._doc_tiep_run(ph["run_id"], int(ph["limit"]), han, True, actor)
        else:
            run = None
            if ph.get("trang_thai") == "dang_gui" and ph.get("moc_gui"):
                run, kiem = A._tim_run_vua_tao_ex(
                    actor, ph["payload"], quet_lon._h(),
                    datetime.datetime.fromisoformat(ph["moc_gui"]), nghiem=True)
                if not run and not kiem:
                    return [], {}, None, float(ph.get("tran_usd") or cap)
            if run:
                v.cap_nhat_phan(ph, run_id=run["id"], trang_thai="dang_chay", nhan_lai=True)
                items, meta = A._doc_tiep_run(run["id"], int(ph["limit"]), han, True, actor)
            else:
                v.cap_nhat_phan(ph, trang_thai="dang_gui", tran_usd=cap,
                                moc_gui=datetime.datetime.now(_VN).isoformat())
                # `mem`: RAM ghim của actor tính phí khởi động theo GB (Threads).
                items, meta = A._run_actor(actor, ph["payload"], int(ph["limit"]), ph.get("mem"),
                                           han, min_charge, tran_usd=cap, mot_phan=True,
                                           nen_tang=p)
    except A.LoiApify as e:
        loi, meta = e, e.meta
    except Exception as e:
        if type(e).__name__ == "MatQuyen":
            raise
        loi = A.LoiApify("LOI", A._che_token(f"{type(e).__name__}: {e}")[:250])
        meta = loi.meta
    finally:
        A._KHI_CO_RUN.set(None)
    return items or [], meta, loi, None


def _du_phong_threads(v, ph: dict, ds: list[dict]) -> bool:
    """Thêm phần DỰ PHÒNG futurizerush (chế độ "user") cho các nguồn của phần hồ sơ Threads `ph`
    vào cuối danh sách phần Threads của việc — vòng phần của `_chay_viec` đi tiếp tới nó ngay trong
    lượt này, cùng kỷ luật tiền (ghi run id, đọc tiếp khi khởi động lại, trần = ước tính × 1,5 kẹp
    phần còn của tháng). Id cố định `<id>-du-phong`: khởi động lại không tạo lần hai. -> True khi
    đã giao (nguồn không ghi lỗi ở phần hồ sơ)."""
    dp = ph.get("du_phong") or {}
    if not dp.get("actor") or not ds:
        return False
    ma = f"{ph['id']}-du-phong"
    with v._khoa:
        cac = v.d.setdefault("nen_tang", {}).setdefault("threads", {"phan": []})["phan"]
        if not any(x.get("id") == ma for x in cac):
            cac.append({"id": ma, "nen_tang": "threads", "nguon": [int(x["id"]) for x in ds],
                        "trang_thai": "cho", "n": ph.get("n"), "gia": dp.get("gia"),
                        "khoi": dp.get("khoi"), "actor": dp["actor"], "mem": dp.get("mem"),
                        "payload": dp.get("payload"), "limit": dp.get("limit"),
                        "uoc_usd": dp.get("uoc_usd"), "la_du_phong": ph["id"]})
            v.luu()
    v.cap_nhat_phan(ph, chuyen_du_phong=ma)
    return True


def _chay_phan_apify(v, p: str, ph: dict, ds: list[dict], cap: float, han: float) -> float:
    """Một lượt actor quét bài của một phần. -> USD theo sổ của phần."""
    import quet_lon
    items, meta, loi, khong_kiem = _chay_actor(v, p, ph, cap, han)
    if khong_kiem is not None:
        v.cap_nhat_phan(ph, trang_thai="loi", ma="KHONG_KIEM_DUOC", so_item=0,
                        usd_so=khong_kiem, ly_do=quet_lon._CAU_KHONG_KIEM)
        return khong_kiem
    kq_dp: dict = {}
    if p == "facebook" and ph.get("du_phong"):
        # Trang thedoor không ra bài → actor cũ cho đúng trang đó (`theo_doi_api.du_phong_fb`).
        items, meta, loi = TDA.du_phong_fb(v, p, ph, items, meta, loi, cap, han)
        kq_dp = meta.get("du_phong") or {}
        if kq_dp:
            # `quet_lon._ket_phan` không giữ meta: kết quả dự phòng (trang đã gửi / bỏ qua + lý
            # do / lỗi) nằm trong phần của sổ việc và vào ghi chú lượt (`_chay_viec`).
            v.cap_nhat_phan(ph, du_phong_kq=kq_dp)
    kq, loi_nguon = ghep_nguon(p, _doc_ket_qua(p, items, int(ph.get("n") or 0),
                                               [x["dinh_danh"] for x in ds]), ds)
    if loi is not None:
        for nid, dong in kq.items():
            if not dong:
                loi_nguon[nid] = A._che_token(str(loi))[:200]
    if kq_dp:
        # Trang vẫn 0 bài: lỗi nguồn (`nguon.loi_cuoi`) nói thedoor + dự phòng ra sao, thay câu
        # chung "không lấy được bài nào".
        for x in ds:
            ly = TDA.ly_do_trang_fb(x["dinh_danh"], kq_dp, loi) if not kq[int(x["id"])] else None
            if ly:
                loi_nguon[int(x["id"])] = ly
    # Actor hồ sơ Threads hỏng CẢ lượt (lỗi, hoặc 0 hồ sơ cho mọi tài khoản xin): giao các nguồn
    # cho lượt dự phòng futurizerush — lỗi nguồn ghi ở lượt đó, không ghi ở đây (không thì nguồn bị
    # đánh lỗi dù dự phòng lấy được bài). Chỉ vài tài khoản thiếu thì KHÔNG dự phòng: thường là tài
    # khoản không có Threads / đổi tên — dự phòng mỗi ngày mất 0,137 USD vô ích.
    if (p == "threads" and ph.get("du_phong") and not items
            and getattr(loi, "ma", "") not in ("HET_TIEN_THANG", "DA_HUY")
            and _du_phong_threads(v, ph, ds)):
        loi_nguon = {}
    _ghi_phan(v, p, ph, kq, loi_nguon)
    tien = TDA.tien_phan(p, ph, items, meta)
    if loi is not None and meta.get("khong_kiem_duoc"):
        tien = cap                       # POST mơ hồ, không kiểm được: coi như đã tiêu trần
    quet_lon._ket_phan(v, ph, meta, len(items), loi, usd_so=tien)
    return float(tien)


# ───────────────────────────── tìm theo từ khoá (đợt 2c, 15/10/2026) ─────────────────────────────
# Chủ dự án 15/10: "social listening cho cả hapas như nghiệp vụ của kompa, họ sẽ lấy tất cả từ
# khóa liên quan cho hapas" — không chỉ nguồn đã theo dõi: mỗi lượt /theodoi còn TÌM theo từ
# khoá của dự án trên TikTok, Facebook, Instagram, YouTube để bắt bài của MỌI tài khoản. Dùng lại
# bộ tìm của social_listen (`apify_tool._FETCH`, đã đo thật) + bước AI phân xử giữ/loại; bài giữ
# ghi kho với kieu_quet 'tu_khoa' (tài khoản đã theo dõi thì gắn nguồn). Tài khoản nổi chưa theo
# dõi thành ĐỀ XUẤT trên dashboard. Tiền: run id vào phần "tu_khoa" của việc → chốt chung lượt.
# Threads (16/10/2026): cùng bộ tìm `_FETCH["threads"]`, đứng cuối (phí khởi động cao nhất); mỗi
# từ khoá actor lấy ≥ 10 bài nên lượt chỉ tìm `so_bai // 10` từ ĐẦU (≥ 1) — tổng bài ≤ số bài đặt,
# ước tính (n × giá + phí khởi động) × 1,3 như nền tảng khác (`_tu_cho`). Từ 17/10/2026 thêm ĐƯỜNG 2
# (`_FETCH["threads_2"]`, scrapersdelight, `_tim_threads_2`): chạy trước đường 1, mọi từ khoá,
# phễu + mốc + tiền riêng, gộp bài và bỏ trùng theo mã bài (`_bo_trung_duong_2`).
TK_NEN_TANG = ("youtube", "tiktok", "facebook", "instagram", "threads", "web")
#: Threads = `apify_tool._UNIT_COST` / `_START_COST` (4 GB × 0,02 USD, gói FREE).
# TikTok từ 16/10/2026: TikTok API, tính theo YÊU CẦU (0,002 USD = giá thật từng run, đo lại
# 18/10/2026 — `tiktok_api.GIA_YEU_CAU`; mỗi trang ≤30 bài, mỗi từ khoá ≥1 trang) —
# `_TK_GIA["tiktok"]` chỉ là sổ tạm theo bài; ước tính dùng `uoc_tu_khoa_nen_tang`.
# Instagram (17/10/2026, `apify~instagram-hashtag-scraper`): 0,0026 USD mỗi item (gói FREE,
# `pricingInfos`), không phí khởi động; hai run mỗi lượt (`apify_tool._IG_TAB`: tab bài + reels).
_TK_GIA = {"tiktok": 0.0001, "facebook": 0.00259, "instagram": 0.0026, "youtube": 0.0,
           "threads": 0.0025}
_TK_KHOI = {"instagram": 0.0, "facebook": 0.00005, "threads": 0.08}
TK_TT_YEU_CAU = 0.002        # = tiktok_api.GIA_YEU_CAU (bài thử đối chiếu)
TK_TT_MOI_TRANG = 30         # = tiktok_api.TIM_MOI_TRANG
#: Nền tảng TẮT khi `du_an.cau_hinh` chưa ghi `bat` cho nó (cả tìm từ khoá lẫn bình luận): thêm
#: nền tảng mới không tự tiêu tiền khi deploy — chủ dự án bật trên trang Ngân sách. Nền tảng cũ
#: vẫn mặc định BẬT như trước (theo cột tk_bat / bl_bat).
#: Báo & Web (review 16/10, M2): chủ dự án duyệt cho RIÊNG HAPAS -> mặc định TẮT với mọi dự án;
#: HAPAS bật bằng `du_an.cau_hinh.tu_khoa.web.bat = true` (deploy/lang-nghe/du-lieu-hapas-web-…).
MAC_DINH_TAT = ("threads", "web")
# Số hashtag Instagram mỗi lượt khi dự án chưa đặt `so_tu` (17/10/2026). Trước là 2 vì actor cũ chạy
# MỘT run mỗi từ, mỗi run 0,016 USD khởi động; actor mới một run nhận mọi hashtag, tiền chỉ theo
# item, nên nhiều tag KHÔNG đắt hơn với cùng số bài — đo 17/10: 11 tag cho 44 bài nhắc HAPAS (gói
# FREE chỉ trang đầu mỗi tag, nên phủ rộng nhiều tag mới bắt được bài mới). Chỉnh trên dashboard.
TK_IG_TOI_DA_TU = 12
TK_FB_TOI_DA = 20            # actor Facebook gói Free: 5 bài/lượt, mỗi từ một lượt, ≤20 bài
TK_TOI_DA_TU = 50           # = số mục tối đa của ô từ khoá trên dashboard (không cắt thêm)
# Cửa sổ ngày của lượt tìm (chẩn đoán 16/10/2026). Bản cũ: 30 ngày lần đầu, rồi CỐ ĐỊNH 3 ngày
# — lượt 4 trả tiền 225 video TikTok mà chỉ xét 33 (85% bị bỏ trước bước AI: actor hashtag tính
# tiền theo item, không lọc ngày), và bài đăng trong khoảng hở giữa hai lượt cách nhau > 3 ngày
# không lượt nào xét. Nay cửa sổ của TỪNG nền tảng tính từ lượt tìm THÀNH CÔNG gần nhất của nền
# tảng đó, lùi thêm `TK_NGAY_CHONG` ngày chồng mép, kẹp [TK_NGAY_TOI_THIEU, TK_NGAY_TOI_DA];
# chưa có mốc hoặc đổi từ khoá / số bài thì lùi tối đa. Lọc rộng hơn KHÔNG tốn thêm tiền Apify
# (tiền theo item, trần theo số bài); bài trùng khử bằng upsert theo khoá bài.
TK_NGAY_TOI_DA = 30
TK_NGAY_TOI_THIEU = 3
TK_NGAY_CHONG = 1
TK_YT_MOI_TRANG = 50         # search.list trả tối đa 50 video mỗi trang (100 đơn vị quota)
# Báo & Web (16/10/2026, `nguon_web.py`, thiết kế ở docs/lang-nghe-web.md). Chủ dự án 16/10: BẬT
# cho HAPAS, quét MỘT lượt/ngày (cửa sổ lùi 2 ngày); trong chiến dịch (`lich_quet` kiểu
# chien_dich đang chạy) MỌI lượt đều tìm web, thêm khẩu hiệu chiến dịch làm từ khoá. Mặc định
# TẮT (`MAC_DINH_TAT`) — chủ dự án chỉ duyệt cho HAPAS (bật rõ trong cau_hinh); vẫn dưới công
# tắc tổng `tk_bat`, trần tháng dự án và trần console. `so_bai` = số kết quả Google mỗi câu tìm (10/trang); `boc` = trần
# trang đọc lại qua actor dự phòng mỗi lượt (0 = tắt). Giá chép sang `dashboard/chi_phi.py`.
WEB_GIA_TRANG = W.GIA_TRANG          # 0,0005 USD / trang kết quả Google (10 link)
WEB_GIA_BOC = W.GIA_BOC              # 0,009 USD / trang đọc qua website-content-crawler
WEB_TU_MOI_CAU = W.TU_MOI_CAU        # 4 từ khoá gộp OR mỗi câu tìm
WEB_TOI_DA_CAU = W.TOI_DA_TRUY_VAN   # 4 câu tìm mỗi lượt
WEB_KQ_MOI_TRANG = W.KQ_MOI_TRANG    # 10
WEB_BOC_MAC_DINH = W.BOC_MAC_DINH    # 10 trang
WEB_GIO_GIAN = 20                    # giờ tối thiểu giữa hai lượt web ngoài chiến dịch
WEB_NGAY_CHONG = 2                   # cửa sổ ngày lùi 2 ngày (báo lên Google chậm 1–24 giờ)
WEB_CHUA_GIAY_AI = 150               # giây chừa cho AI + ghi kho sau khi đọc trang

# ───────────────────────────── cấu hình theo nền tảng (đợt 2e, 15/10/2026) ─────────────────────────────
# Chủ dự án 15/10: "không có giới hạn" — mọi số thu thập TUỲ CHỈNH được trên dashboard (không
# cứng "15 bài mỗi nền tảng"), kể cả cào bình luận. `du_an.cau_hinh` (JSONB) ghi đè TỪNG nền tảng:
#   {"tu_khoa":  {"<nền tảng>": {"bat": bool, "so_bai": int, "so_tu": int}},
#    "binh_luan": {"<nền tảng>": {"bat": bool, "so_bai": int, "moi_bai": int}}}
# Cột chung (tk_bat, tk_so_bai, bl_bat, bl_so_bai, bl_moi_bai) là mặc định khi không ghi đè.
# Chặn tiền: trần tháng của dự án + trần console mỗi lượt; còn giới hạn của chính nền tảng
# (Facebook gói Free: 5 bài/lượt, ≤20 bài một lượt tìm). `SO_TOI_DA` chỉ chặn số rác, không phải trần nghiệp vụ.
SO_TOI_DA = 1_000_000
GIOI_HAN = {"tk_so_bai": (0, SO_TOI_DA), "tk_so_tu": (1, TK_TOI_DA_TU),
            "bl_so_bai": (0, SO_TOI_DA), "bl_moi_bai": (0, SO_TOI_DA)}

# ───────────── Facebook ĐƯỜNG THỨ HAI (17/10/2026, mina_safwat~facebook-search-actor) ─────────────
# Chủ dự án duyệt 17/10 ("ưu tiên độ phủ"): kho FB chỉ phủ 20% bài liên quan 13–17/10 vì scrapeforge
# gói FREE trả 5 bài/lượt. Mina (đo 6 run: 99 bài HAPAS kho chưa có, 0,0036 USD mỗi bài mới) chạy
# CÙNG lượt với scrapeforge: bài hai đường gộp, bỏ trùng theo khoá, rồi qua cùng phễu (loại trừ,
# spam, AI) và ghi kho. Cấu hình `du_an.cau_hinh.tu_khoa.facebook.duong2`:
#   {"bat": bool (mặc định bật), "so_bai_moi_tu": bài mới nhất mỗi cụm (mặc định 12; 0 = tắt),
#    "gio": giờ tối thiểu giữa hai lượt đường 2 ngoài chiến dịch (mặc định 20 ≈ 1 lượt/ngày),
#    "gio_chien_dich": như trên khi đang có lịch chiến dịch (mặc định = `gio`, 20 — xem TK_FB2_GIO_CD)}.
# Nhịp `gio` vì sao: actor trả bài MỚI NHẤT trước; lịch chiến dịch chạy tới mỗi 30 phút thì mỗi lượt
# trả tiền lại đúng chừng ấy bài (7 cụm × 12 bài ≈ 0,17 USD/lượt). Từ khoá: chỉ cụm NHIỀU TỪ có tên
# brand (`tu_fb_duong2`) — "hapas" một chữ ra 3/30 bài liên quan ở mọi actor.
TK_FB2 = "facebook_duong2"          # khoá mốc trong sổ mốc + `nen_tang` của phần run trong sổ việc
TK_FB2_MOI_TU = 12
TK_FB2_GIO = 20
# Soát 17/10/2026: mặc định cũ 6 giờ trong chiến dịch = 4 lượt/ngày × ~0,2 USD (7 cụm × 12 bài) ≈ 25
# USD/tháng/dự án chỉ cho đường 2 — tự tăng tiền mà chủ dự án không chọn. Nay mặc định BẰNG nhịp
# thường; muốn quét dày hơn trong chiến dịch thì chủ dự án tự hạ `duong2.gio_chien_dich`.
TK_FB2_GIO_CD = TK_FB2_GIO
TK_FB2_GIA = A._GIA_FB_DUONG2       # 0,002 USD/bài
TK_FB2_KHOI = A._KHOI_FB_DUONG2     # 0,00005 USD/run

# ───────────── TikTok: FEED HASHTAG trong lượt tìm hằng ngày (17/10/2026, scraptik) ─────────────
# Đo vòng 1 (17/10/2026): kho phủ 70% video TikTok liên quan 10–17/10; 12 video sót tập trung ở
# #hapassuperbrandday (5 video tối 16/10, 3 của kênh kho đã có 59 bài) và feed #hapas (3 video
# 11–13/10 chỉ thấy qua feed hashtag) — tìm theo từ khoá không trả về chúng. Đọc feed hashtag
# (`challengePosts`, 20 bài/yêu cầu, cid nhớ chung với kiểm độ phủ) của TỪ KHOÁ MỘT CHỮ của dự án,
# sau lượt thường / mới nhất / nổi; bài về đi CÙNG phễu (phạm vi ngày, loại trừ, spam, AI). Cấu hình
# `du_an.cau_hinh.tu_khoa.tiktok.hashtag` {"bat" (thiếu = theo TikTok), "so_yeu_cau" (trần yêu cầu
# mỗi lượt, mặc định 5 ≈ 0,015 USD), "gio" (giờ tối thiểu giữa hai lượt, mặc định 20 ≈ 1/ngày)}.
TK_TAG = "tiktok_tag"               # khoá mốc trong sổ mốc tìm theo từ khoá
TK_TAG_YEU_CAU = 5
TK_TAG_GIO = 20


# ───────────── GIÃN NHỊP đường tìm ít bài mới (18/10/2026) ─────────────
# Chủ dự án 18/10: "các luồng cào để tối ưu output nhất có thể". Instagram hashtag gói FREE chỉ đọc
# TRANG ĐẦU (~6 bài mới nhất mỗi hashtag mỗi tab) nên ngày nào cũng trả phần lớn bài đã có (lượt 7–9:
# về 14/14/7, mới 2/0/0); Threads đường 1 mất 0,08 USD khởi động kể cả về 0 bài. Nền tảng trong
# `TK_GIAN_NEN_TANG` mà `luot` lượt tìm LIỀN có bài mới < `ty_le` × bài về (hoặc về 0) thì chỉ tìm
# lại sau `gio` giờ từ lượt tìm trước (mặc định 44 ≈ 2 ngày/lần); chiến dịch đang chạy thì không
# giãn; lượt có bài mới ≥ ngưỡng thì về nhịp thường. Threads chỉ giãn ĐƯỜNG 1 (đường 2 rẻ, bắt bài
# nổi). Cấu hình `du_an.cau_hinh.tu_khoa.<nền tảng>.gian` {"bat", "luot", "ty_le", "gio"}; lịch sử
# (giờ, về, mới) trong sổ mốc khoá `KHOA_NHIP_TIM` = {nền tảng: {"lich_su": […]}} — tách khỏi mốc
# cửa sổ của nền tảng (lượt về 0 bài vẫn không dời mốc cửa sổ).
KHOA_NHIP_TIM = "nhip_tim"
TK_GIAN_NEN_TANG = ("instagram", "facebook", "threads")
TK_GIAN_LUOT = 3
TK_GIAN_TY_LE = 0.05
TK_GIAN_GIO = 44
TK_GIAN_LICH_SU = 6


def _kep(v, lo: int, hi: int, md: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return md


def _cau_hinh_gian(rieng: dict) -> dict:
    """Cấu hình giãn nhịp hiệu lực (khối `gian` của nền tảng): thiếu → bật, 3 lượt, 5%, 44 giờ;
    rác → mặc định."""
    x = rieng.get("gian") if isinstance(rieng.get("gian"), dict) else {}
    t = x.get("ty_le", TK_GIAN_TY_LE)
    try:
        ty = TK_GIAN_TY_LE if isinstance(t, bool) else float(t)
    except (TypeError, ValueError):
        ty = TK_GIAN_TY_LE
    if not math.isfinite(ty) or not 0 <= ty <= 1:
        ty = TK_GIAN_TY_LE
    return {"bat": x.get("bat", True) is not False,
            "luot": _so_rieng(x.get("luot"), 1, TK_GIAN_LICH_SU, TK_GIAN_LUOT), "ty_le": ty,
            "gio": _so_rieng(x.get("gio"), 1, 24 * 14, TK_GIAN_GIO)}


def gian_nhip(cfg: dict | None, nhip: dict | None, bay_gio: datetime.datetime,
              chien_dich: bool = False) -> tuple[bool, str]:
    """(bỏ lượt tìm này?, lý do). Bỏ khi `cfg.luot` lượt tìm GẦN NHẤT đều có bài mới < `ty_le` ×
    bài về (hoặc về 0) và chưa đủ `gio` giờ (trừ `GIO_DUNG_SAI`) từ lượt tìm cuối. `nhip` =
    `doc_moc_tk(ma)[KHOA_NHIP_TIM][nền tảng]` {"lich_su": [[giờ ISO, về, mới], …]}."""
    if not cfg or not cfg.get("bat") or chien_dich:
        return False, ""
    ls = [x for x in (nhip or {}).get("lich_su") or [] if isinstance(x, list) and len(x) >= 3]
    k = int(cfg["luot"])
    if len(ls) < k:
        return False, ""
    gan = ls[-k:]
    if not all(int(ve) == 0 or int(m) < cfg["ty_le"] * int(ve) for _, ve, m in gan):
        return False, ""
    cuoi = _gio_iso(gan[-1][0])
    if cuoi is None:
        return False, ""
    ke = cuoi + datetime.timedelta(hours=int(cfg["gio"]))
    if bay_gio >= ke - datetime.timedelta(hours=K.GIO_DUNG_SAI):
        return False, ""
    chu = ", ".join(f"{int(m)}/{int(ve)}" for _, ve, m in gan)
    return True, (f"giãn nhịp: {k} lượt liền bài mới dưới {cfg['ty_le'] * 100:g}% bài về (mới/về:"
                  f" {chu}) — tìm lại từ {ke.astimezone(_VN):%H:%M %d/%m}")


def _so_rieng(v, lo: int, hi: int, md: int) -> int:
    """Số ghi đè trong JSONB: rác / bool / dưới `lo` -> `md` (giá trị cột chung), KHÔNG rơi về 0
    — 0 bình luận mỗi bài nghĩa là cào HẾT (đắt nhất)."""
    if isinstance(v, bool):
        return md
    try:
        n = int(v)
    except (TypeError, ValueError):
        return md
    return md if n < lo else min(hi, n)


def cau_hinh(du_an: dict, nhom: str, p: str) -> dict:
    """Cấu hình HIỆU LỰC của một nền tảng. `nhom`: "tu_khoa" | "binh_luan".

    Cột `tk_bat` / `bl_bat` là CÔNG TẮC TỔNG: tắt thì mọi nền tảng tắt dù JSONB ghi gì. Trong
    JSONB chỉ `bat` đúng bằng True mới là bật (chuỗi "false" không phải bật); thiếu `bat` thì
    bật, trừ nền tảng trong `MAC_DINH_TAT` (Threads) — phải bật rõ. Số bỏ trống/rác lấy cột
    chung — số bài cột chung áp cho TỪNG nền tảng."""
    goc = du_an.get("cau_hinh") if isinstance(du_an.get("cau_hinh"), dict) else {}
    nh = goc.get(nhom) if isinstance(goc.get(nhom), dict) else {}
    rieng = nh.get(p) if isinstance(nh.get(p), dict) else {}
    bat_rieng = rieng.get("bat", p not in MAC_DINH_TAT) is True
    if nhom == "tu_khoa":
        chung = _kep(du_an.get("tk_so_bai") or 0, *GIOI_HAN["tk_so_bai"], 0)
        so = _so_rieng(rieng.get("so_bai"), *GIOI_HAN["tk_so_bai"], chung)
        ra = {"bat": bool(du_an.get("tk_bat", True)) and bat_rieng and so > 0,
              "so_bai": so,
              "so_tu": _so_rieng(rieng.get("so_tu"), *GIOI_HAN["tk_so_tu"], TK_IG_TOI_DA_TU)}
        if p == "web":
            # 0 = tắt đọc dự phòng (khác số bài: 0 ở đây là giá trị hợp lệ, không rơi về mặc định).
            b = rieng.get("boc")
            ra["boc"] = (WEB_BOC_MAC_DINH if isinstance(b, bool) or b is None
                         else _kep(b, 0, SO_TOI_DA, WEB_BOC_MAC_DINH))
        if p == "facebook":
            ra["duong2"] = _cau_hinh_fb2(du_an, rieng, bat_rieng, so)
        if p == "tiktok":
            ra["hashtag"] = _cau_hinh_tag(du_an, rieng, bat_rieng, so)
        if p in TK_GIAN_NEN_TANG:
            ra["gian"] = _cau_hinh_gian(rieng)
        return ra
    chung = _kep(du_an.get("bl_so_bai") or 0, *GIOI_HAN["bl_so_bai"], 0)
    so = _so_rieng(rieng.get("so_bai"), *GIOI_HAN["bl_so_bai"], chung)
    moi_chung = _kep(du_an.get("bl_moi_bai") or 0, *GIOI_HAN["bl_moi_bai"], 0)
    moi = _so_rieng(rieng.get("moi_bai"), *GIOI_HAN["bl_moi_bai"], moi_chung)
    return {"bat": bool(du_an.get("bl_bat", True)) and bat_rieng and so > 0,
            "so_bai": so, "moi_bai": 5 if 0 < moi < 5 else moi}


def _cau_hinh_fb2(du_an: dict, rieng: dict, bat_rieng: bool, so_fb: int) -> dict:
    """Cấu hình HIỆU LỰC của đường 2 Facebook (khối `duong2` trong cấu hình Facebook). Bật khi:
    công tắc tổng `tk_bat`, công tắc Facebook của dự án, số bài mỗi cụm > 0, và:
      • khối CÓ `bat` (trang Ngân sách luôn ghi): chỉ đúng True mới là bật — khi đó KHÔNG phụ thuộc
        số bài của đường chính (đặt Facebook 0 bài = chỉ tắt scrapeforge, giữ đường 2);
      • thiếu `bat` (mặc định — chưa lưu trang lần nào): theo đường chính (bật khi Facebook có số
        bài > 0), để dự án đặt "0 bài" cột chung vẫn là KHÔNG tìm theo từ khoá như trước.
    Số rác / bool / âm → mặc định."""
    d2 = rieng.get("duong2") if isinstance(rieng.get("duong2"), dict) else {}
    so = _so_rieng(d2.get("so_bai_moi_tu"), 0, SO_TOI_DA, TK_FB2_MOI_TU)
    bat = d2["bat"] is True if "bat" in d2 else so_fb > 0
    return {"bat": bool(du_an.get("tk_bat", True)) and bat_rieng and bat and so > 0,
            "so_bai_moi_tu": so,
            "gio": _so_rieng(d2.get("gio"), 0, 24 * 31, TK_FB2_GIO),
            "gio_chien_dich": _so_rieng(d2.get("gio_chien_dich"), 0, 24 * 31, TK_FB2_GIO_CD)}


def _cau_hinh_tag(du_an: dict, rieng: dict, bat_rieng: bool, so_tt: int) -> dict:
    """Cấu hình HIỆU LỰC của feed hashtag TikTok (khối `hashtag` trong cấu hình TikTok): cùng
    luật bật như đường 2 Facebook (`_cau_hinh_fb2`) — khối có `bat` thì chỉ True là bật, thiếu thì
    theo lượt tìm TikTok (số bài > 0); số yêu cầu 0 = tắt."""
    x = rieng.get("hashtag") if isinstance(rieng.get("hashtag"), dict) else {}
    so = _so_rieng(x.get("so_yeu_cau"), 0, SO_TOI_DA, TK_TAG_YEU_CAU)
    bat = x["bat"] is True if "bat" in x else so_tt > 0
    return {"bat": bool(du_an.get("tk_bat", True)) and bat_rieng and bat and so > 0,
            "so_yeu_cau": so, "gio": _so_rieng(x.get("gio"), 0, 24 * 31, TK_TAG_GIO)}


def tag_tiktok(tu: list[str]) -> list[str]:
    """Hashtag của feed TikTok: từ khoá MỘT chữ (không dấu cách) chuẩn hoá như `tiktok_api.
    chuan_tag` ("#HAPAS" → "hapas", "hapas.vn" → "hapasvn"), 3–40 ký tự, bỏ trùng, giữ thứ tự."""
    ra: list[str] = []
    for kw in tu:
        t = TDA.TT.chuan_tag(kw) if len(str(kw).split()) == 1 else ""
        if 3 <= len(t) <= 40 and t not in ra:
            ra.append(t)
    return ra


def uoc_tag_tiktok(so_yeu_cau: int, so_tag: int) -> float:
    """USD TỐI ĐA một lượt feed hashtag TikTok: trần yêu cầu × 0,003 × 1,3 (0 khi không có tag)."""
    if so_yeu_cau <= 0 or so_tag <= 0:
        return 0.0
    return round(so_yeu_cau * TK_TT_YEU_CAU * _HE_SO_UOC, 4)


def tu_fb_duong2(du_an: dict, tu: list[str] | None = None) -> list[str]:
    """Cụm từ khoá của đường 2 Facebook: chỉ cụm NHIỀU TỪ (≥ 2 chữ cách nhau) có TÊN BRAND (mọi
    chữ của tên dự án, hoặc tên viết liền, là một chữ của cụm) — "túi hapas", "quà tặng hapas",
    "hapas perfume". Bỏ từ một chữ ("hapas") và dạng hashtag viết liền ("quatanghapas",
    "hapas.vn"): đo 17/10/2026 "hapas" ra 3/30 bài liên quan ở mọi actor, cụm tiếng Việt 56–95%."""
    ten = A._tokens(str(du_an.get("ten") or ""))
    gon = "".join(ten)
    ra = []
    for kw in (tu if tu is not None else tu_tim(du_an)):
        chu = A._tokens(kw)
        if len(str(kw).split()) >= 2 and ten and (all(t in chu for t in ten) or gon in chu):
            ra.append(kw)
    return ra


def uoc_fb_duong2(so_cum: int, moi_cum: int) -> float:
    """USD TỐI ĐA một lượt đường 2 Facebook: mỗi cụm một run × (bài × 0,002 + 0,00005) × 1,3."""
    if so_cum <= 0 or moi_cum <= 0:
        return 0.0
    return round(so_cum * (moi_cum * TK_FB2_GIA + TK_FB2_KHOI) * _HE_SO_UOC, 4)


def tk_co_bat(du_an: dict) -> bool:
    """Lượt này có tìm theo từ khoá ở ít nhất một nền tảng không (theo cấu hình hiệu lực)."""
    return any(cau_hinh(du_an, "tu_khoa", p)["bat"] for p in TK_NEN_TANG) \
        or (cau_hinh(du_an, "tu_khoa", "facebook")["duong2"]["bat"] and bool(tu_fb_duong2(du_an)))


def cau_hinh_th2(du_an: dict) -> dict:
    """Cấu hình HIỆU LỰC của đường 2 Threads (`du_an.cau_hinh.tu_khoa.threads.duong2`).

    Chỉ chạy khi Threads tìm theo từ khoá đang bật cho dự án (`cau_hinh(..., "threads")` — công
    tắc tổng `tk_bat` vẫn thắng). Thiếu `bat` thì BẬT (chủ dự án duyệt 17/10/2026); như mọi khoá
    JSONB khác, chỉ `bat` đúng bằng True mới là bật — tắt: `"bat": false`. Số rác/âm → mặc định;
    `so_bai` 0 = tắt; `so_luot` kẹp 1–5 (giới hạn của actor)."""
    goc = du_an.get("cau_hinh") if isinstance(du_an.get("cau_hinh"), dict) else {}
    nh = goc.get("tu_khoa") if isinstance(goc.get("tu_khoa"), dict) else {}
    th = nh.get("threads") if isinstance(nh.get("threads"), dict) else {}
    x = th.get("duong2") if isinstance(th.get("duong2"), dict) else {}
    so = _so_rieng(x.get("so_bai"), 0, SO_TOI_DA, TH2_SO_BAI)
    # `bat_rieng`: công tắc của RIÊNG đường 2 (trang Ngân sách cộng đường 2 khi bật Threads).
    rieng = x.get("bat", True) is True and so > 0
    return {"bat": cau_hinh(du_an, "tu_khoa", "threads")["bat"] and rieng, "bat_rieng": rieng,
            "so_bai": so,
            "so_bai_moi_tu": _so_rieng(x.get("so_bai_moi_tu"), 1, SO_TOI_DA, TH2_MOI_TU),
            "so_luot": _so_rieng(x.get("so_luot"), 1, 5, TH2_LUOT)}


def _tu_th2(tu: list[str]) -> list[str]:
    """Từ khoá đường 2 gửi actor: MỌI từ khoá của dự án (≤ `TK_TOI_DA_TU`). Khác đường 1 (chỉ
    `so_bai // 10` từ đầu): actor tính tiền theo bài TRẢ VỀ, từ khoá không ra bài không tốn đồng nào
    (đo 17/10: 21 từ, 19 từ 0 bài, cả run 0,015 USD)."""
    return list(tu[:TK_TOI_DA_TU])


def uoc_th2(c2: dict, tu: list[str], moc: dict | None = None) -> float:
    """USD một lượt đường 2: số bài × 0,001 × hệ số ước tính; 0 khi tắt / không có từ khoá. Không
    `moc`: TỐI ĐA = trần bài min(`so_bai`, `so_bai_moi_tu` × số từ) — bản sao
    `dashboard.chi_phi.uoc_th2`; có `moc` (sổ mốc `threads_2`): theo sản lượng lượt trước."""
    q = _tu_th2(tu)
    if not c2.get("bat") or not q:
        return 0.0
    n = min(c2["so_bai"], c2["so_bai_moi_tu"] * len(q))
    if moc is not None:
        n = san_luong_du_kien(q, c2["so_bai_moi_tu"], moc, n)[0]
    return round(n * TH2_GIA * _HE_SO_UOC, 4)


def _fb_toi_da() -> int:
    """Số bài tối đa một lượt tìm Facebook: 20 với gói Apify Free (hoặc chưa biết gói — an
    toàn), không giới hạn thêm với gói trả phí (chủ dự án 15/10: sẽ nâng gói)."""
    try:
        goi = A._goi_apify()
    except Exception:  # noqa: BLE001 — không hỏi được gói thì giữ mức an toàn
        goi = ""
    return TK_FB_TOI_DA if goi in ("", "FREE") else 10 ** 6


def tu_tim(du_an: dict) -> list[str]:
    """Từ khoá tìm của dự án (bỏ trùng, giữ thứ tự, tối đa `TK_TOI_DA_TU`)."""
    ra: list[str] = []
    for x in du_an.get("tu_khoa") or [du_an.get("ten") or ""]:
        x = " ".join(str(x).split())
        if x and A._norm(x) not in {A._norm(y) for y in ra}:
            ra.append(x)
    return ra[:TK_TOI_DA_TU]


def _tu_cho(p: str, tu: list[str], so_tu: int = TK_IG_TOI_DA_TU, so_bai: int = 0) -> list[str]:
    """Từ khoá THẬT SỰ gửi actor của nền tảng `p`."""
    if p == "instagram":
        # Actor tìm theo HASHTAG (17/10/2026): mọi từ khoá viết liền, bỏ dấu (`hashtag_ig`), bỏ
        # trùng — "túi hapas" thành #tuihapas thay vì bị bỏ như bản cũ (chỉ từ không dấu cách).
        return A.hashtag_ig_ds(tu)[:so_tu]
    if p == "threads":
        # Mỗi từ actor lấy (và tính tiền) ≥ 10 bài: chỉ tìm `so_bai // 10` từ đầu (≥ 1, ≤ 20)
        # để tổng bài không vượt số bài đặt trên dashboard (`apify_tool._fetch_threads` chia
        # đều phần nguyên). Muốn tìm đủ N từ: đặt số bài Threads ≥ 10 × N.
        return tu[:max(1, min(TH_TOI_DA_MOI_LUOT, so_bai // TH_TOI_THIEU_BAI))]
    return tu


def uoc_web(so_bai: int, tu: list[str], boc: int = WEB_BOC_MAC_DINH) -> float:
    """USD TỐI ĐA một lượt Báo & Web: ⌈từ khoá rút gọn / 4⌉ câu (≤ 4) × ⌈số kết quả / 10⌉ trang ×
    0,0005 + `boc` trang dự phòng × 0,009, nhân 1,3 (= `nguon_web.uoc_tu_khoa`). Đọc HTTP: 0."""
    return W.uoc_tu_khoa(tu, so_bai, boc)


def _so_ve(v, md: int) -> int:
    """Số bài đã về của một từ khoá trong sổ mốc; rác/âm/thiếu → `md` (coi như chưa đo)."""
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else md


def san_luong_du_kien(q: list[str], moi_tu: int, moc: dict | None,
                      tran: int) -> tuple[int, str]:
    """Số bài Threads DỰ KIẾN actor trả (và tính tiền) lượt này. -> (số bài, lý do).

    Vì sao (phễu lượt 11, 17/10/2026): ước tính cũ coi MỖI từ khoá về đủ trần (`max_posts` 10) nên
    21 từ khoá ≈ 0,79 USD và Threads bị "co còn 15/21 từ khoá × 10 bài (ước 0,59 USD)" — trong khi
    không đăng nhập chỉ "hapas" và "túi hapas" ra bài (19 cụm 0 bài, đo 17/10). Nay theo SẢN LƯỢNG
    THẬT của lượt trước trong sổ mốc (`.moc-tu-khoa.json`, ghi ở `_tim_tu_khoa`):
      • có `ve_tu` (bài về TỪNG từ khoá): Σ min(trần mỗi từ, số đã về); từ khoá mới chưa đo thì
        tính đủ trần mỗi từ;
      • chỉ có `ve` (sổ ghi trước 17/10): tổng bài lượt trước;
      • chưa có gì: trần (như cũ).
    rồi × `TH_HE_SO_SAN_LUONG` (bài về thất thường theo ngày), không dưới `TH_TOI_THIEU_BAI`, không
    quá `tran`. Tiền thật chặn ở trần USD gửi Apify: đường 1 = max(sàn, ước tính × 1,5) kẹp trần
    console + phần còn của việc/tháng (`tran_threads_1` — soát 17/10/2026: bản trước gửi CẢ phần
    tiền còn lại, run nhiều bài ăn luôn phần giữ cho bình luận / kiểm độ phủ / web); đường 2 =
    `maxItems`. Lượt bất ngờ nhiều bài dừng ở trần đó và giữ bài đã trả tiền."""
    moc = moc if isinstance(moc, dict) else {}
    ve_tu = moc.get("ve_tu")
    if isinstance(ve_tu, dict) and ve_tu:
        tong = sum(min(moi_tu, _so_ve(ve_tu.get(A._norm(" ".join(str(t).split()))), moi_tu))
                   for t in q)
        ly = "theo bài về từng từ khoá lượt trước"
    elif _so_ve(moc.get("ve"), -1) >= 0:
        tong, ly = moc["ve"], "theo tổng bài lượt trước"
    else:
        return tran, f"chưa có sản lượng lượt trước — tính trần {tran} bài"
    n = min(tran, max(TH_TOI_THIEU_BAI, math.ceil(tong * TH_HE_SO_SAN_LUONG)))
    return n, f"{ly}: {tong} bài → dự kiến {n}/{tran}"


def uoc_tu_khoa_nen_tang(p: str, so_bai: int, tu: list[str], so_tu: int = TK_IG_TOI_DA_TU,
                         fb_toi_da: int = TK_FB_TOI_DA, moc: dict | None = None) -> float:
    """USD một lượt tìm của nền tảng `p`. Threads + `moc` (sổ mốc của nền tảng, 17/10/2026):
    số bài theo sản lượng lượt trước (`san_luong_du_kien`); không `moc` = mức TỐI ĐA theo cấu
    hình (dashboard dùng — bản sao `dashboard.chi_phi.uoc_tk_nen_tang`)."""
    if p == "web":
        return uoc_web(so_bai, tu)
    q = _tu_cho(p, tu, so_tu, so_bai)
    if not q or not _TK_GIA.get(p) or so_bai <= 0:
        return 0.0
    if p == "tiktok":
        # Tối đa 2×(trang cần)+1 trang mỗi từ khoá (lượt thường + lượt nổi) + `MOI_TRANG`
        # trang "mới nhất" (17/10/2026) + làm mới số liệu bài nổi (`theo_doi_api`).
        trang = 2 * math.ceil(math.ceil(so_bai / len(q)) / TK_TT_MOI_TRANG) + 1 + TDA.MOI_TRANG
        return round((len(q) * trang + TDA.LAM_MOI_TOI_DA) * TK_TT_YEU_CAU * _HE_SO_UOC, 4)
    if p == "instagram":
        # Hai run (tab bài + reels), mỗi run mọi hashtag × trần mỗi tag (`_fetch_instagram`).
        tab = len(A._IG_TAB)
        per = max(1, math.ceil(so_bai / (tab * len(q))))
        return round((tab * len(q) * per * _TK_GIA[p] + tab * _TK_KHOI["instagram"])
                     * _HE_SO_UOC, 4)
    n = (min(so_bai, fb_toi_da) if p == "facebook"
         else max(so_bai, TH_TOI_THIEU_BAI) if p == "threads" else so_bai)
    if p == "threads" and moc is not None:
        n = san_luong_du_kien(q, max(TH_TOI_THIEU_BAI, so_bai // len(q)), moc, n)[0]
    return round((n * _TK_GIA[p] + _TK_KHOI.get(p, 0.0)) * _HE_SO_UOC, 4)


def uoc_tu_khoa(so_bai: int, tu: list[str]) -> float:
    """Mọi nền tảng cùng số bài; Threads gồm đường 2 theo mặc định (`TH2_*`, 17/10/2026)."""
    th2 = {"bat": True, "so_bai": TH2_SO_BAI, "so_bai_moi_tu": TH2_MOI_TU, "so_luot": TH2_LUOT}
    return round(sum(uoc_tu_khoa_nen_tang(p, so_bai, tu) for p in TK_NEN_TANG)
                 + (uoc_th2(th2, tu) if so_bai > 0 else 0.0), 4)


def uoc_tu_khoa_du_an(du_an: dict, fb_toi_da: int = TK_FB_TOI_DA,
                      moc: dict | None = None) -> float:
    """USD tối đa một lượt tìm theo từ khoá với cấu hình hiệu lực từng nền tảng (Threads: cả
    đường 2 khi bật — `cau_hinh_th2`). `moc` = sổ mốc của dự án (`doc_moc_tk`): Threads hai đường
    tính theo sản lượng lượt trước thay vì trần (`san_luong_du_kien`)."""
    tu = tu_tim(du_an)
    m = moc if isinstance(moc, dict) else {}
    tong = uoc_th2(cau_hinh_th2(du_an), tu, m.get(TH2_KHOA))
    for p in TK_NEN_TANG:
        c = cau_hinh(du_an, "tu_khoa", p)
        if c["bat"] and p == "web":
            tong += uoc_web(c["so_bai"], tu, c["boc"])
        elif c["bat"]:
            tong += uoc_tu_khoa_nen_tang(p, c["so_bai"], tu, c["so_tu"], fb_toi_da,
                                         moc=m.get(p) if p == "threads" else None)
        if p == "facebook" and c["duong2"]["bat"]:
            # Đường 2 (17/10/2026) tính TỐI ĐA mỗi lượt dù nhịp `gio` có thể bỏ lượt — giữ chỗ dư.
            tong += uoc_fb_duong2(len(tu_fb_duong2(du_an, tu)), c["duong2"]["so_bai_moi_tu"])
        if p == "tiktok" and c["hashtag"]["bat"]:
            tong += uoc_tag_tiktok(c["hashtag"]["so_yeu_cau"], len(tag_tiktok(tu)))
    return round(tong, 4)


def tran_threads_1(uoc: float, con: float = float("inf")) -> float:
    """Trần USD gửi Apify (`maxTotalChargeUsd`) của lượt tìm Threads ĐƯỜNG 1 (futurizerush):
    min(trần console Threads, `con` = phần còn của việc/tháng, max(sàn 0,1, ước tính × 1,5)), làm
    tròn XUỐNG tới cent. Actor không dừng ở `maxItems` — trần này là thứ duy nhất chặn tiền, nên
    nó phải bám ước tính đã giữ chỗ (`giu_cho_tu_khoa`), không phải cả phần tiền còn lại."""
    muc = min(A._tran_nen_tang("threads", nen=True)[1], con,
              max(_TRAN_TOI_THIEU, float(uoc) * _HE_SO_TRAN))
    return math.floor(muc * 100 + 1e-9) / 100


def uoc_threads_1(du_an: dict, fb_toi_da: int = TK_FB_TOI_DA, moc: dict | None = None) -> float:
    """Ước tính lượt tìm Threads đường 1 với cấu hình hiệu lực — CÙNG con số `_tim_tu_khoa` dùng
    lúc chạy (sổ mốc `moc` của dự án: theo sản lượng lượt trước). 0 khi Threads tắt."""
    c = cau_hinh(du_an, "tu_khoa", "threads")
    if not c["bat"]:
        return 0.0
    m = (moc or {}).get("threads") if isinstance(moc, dict) else None
    return uoc_tu_khoa_nen_tang("threads", c["so_bai"], tu_tim(du_an), c["so_tu"], fb_toi_da,
                                moc=m if isinstance(m, dict) else {})


def giu_cho_tu_khoa(du_an: dict, fb_toi_da: int = TK_FB_TOI_DA, moc: dict | None = None) -> float:
    """USD giữ chỗ cho lượt tìm theo từ khoá lúc tạo việc (`_tao_luot`): ước tính mọi nền tảng
    (`uoc_tu_khoa_du_an`), riêng Threads đường 1 giữ đúng TRẦN run (`tran_threads_1`, không kẹp
    phần còn) thay cho ước tính — run được tiêu tới đâu thì việc đã giữ tới đó."""
    tong = uoc_tu_khoa_du_an(du_an, fb_toi_da, moc)
    u1 = uoc_threads_1(du_an, fb_toi_da, moc)
    if u1 > 0:
        tong += max(0.0, tran_threads_1(u1) - u1)
    return round(tong, 4)


def uoc_binh_luan_du_an(du_an: dict) -> float:
    """USD giữ chỗ một lượt cào bình luận với cấu hình hiệu lực từng nền tảng."""
    tong = 0.0
    for p in BL_NEN_TANG:
        c = cau_hinh(du_an, "binh_luan", p)
        if c["bat"]:
            tong += uoc_binh_luan(c["so_bai"], c["moi_bai"], p)
    return round(tong, 4)


def _phan_tk(v) -> list[dict]:
    with v._khoa:
        return v.d.setdefault("nen_tang", {}).setdefault("tu_khoa", {"phan": []})["phan"]


def _them_phan_tk(v, ph: dict) -> dict:
    with v._khoa:
        _phan_tk(v).append(ph)
        v.luu()
    return ph


_KHOA_MOC_TK = threading.Lock()


def _duong_moc_tk():
    """Sổ mốc tìm theo từ khoá: `.audit/viec-nen/.moc-tu-khoa.json`, cạnh sổ việc nền (Mark có
    quyền ghi, không đổi schema kho). Dạng {"du_an": {<mã>: {<nền tảng>: {"luc", "dau",
    "luot"}}}}. Gốc không có khoá "ma" nên `viec_nen.tat_ca` không coi là một việc, và
    `viec_nen.don_dep` không xoá (chỉ xoá theo mã việc)."""
    return A._thu_muc_nen() / ".moc-tu-khoa.json"


def _doc_so_moc_tk() -> dict:
    try:
        d = json.loads(_duong_moc_tk().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) and isinstance(d.get("du_an"), dict) else {}


def doc_moc_tk(ma: str) -> dict[str, dict]:
    """{nền tảng: mốc lượt tìm thành công gần nhất} của dự án; sổ hỏng/thiếu → {} (lùi tối đa)."""
    x = (_doc_so_moc_tk().get("du_an") or {}).get(ma)
    return {p: m for p, m in x.items() if isinstance(m, dict)} if isinstance(x, dict) else {}


def ghi_moc_tk(ma: str, moc: dict[str, dict]) -> None:
    """Ghi đè mốc của các nền tảng trong `moc` (nền tảng khác giữ nguyên). Ghi nguyên tử (tmp
    rồi os.replace). Không ghi được thì chỉ báo: lượt sau lùi xa hơn, không mất bài."""
    if not moc:
        return
    with _KHOA_MOC_TK:
        d = _doc_so_moc_tk() or {"du_an": {}}
        cua = d["du_an"].get(ma) if isinstance(d["du_an"].get(ma), dict) else {}
        d["du_an"][ma] = {**cua, **moc}
        f = _duong_moc_tk()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, f)
        except OSError as e:
            print(f"[theo_doi] không ghi được mốc tìm theo từ khoá: {type(e).__name__}", flush=True)


def dau_tk(q: list[str], lim: int) -> str:
    """Dấu vân tay một lượt tìm của một nền tảng: từ khoá THẬT SỰ gửi đi (chuẩn hoá, giữ thứ tự
    — Facebook gói Free chỉ tìm từ đầu, Instagram `so_tu` hashtag đầu) + số bài gửi actor. Đổi một
    trong
    hai thì mốc cũ không còn đúng → lùi tối đa (bài cũ chưa từng được tìm bằng bộ mới)."""
    s = json.dumps([[A._norm(" ".join(str(x).split())) for x in q], int(lim)],
                   ensure_ascii=False)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def cua_so_tk(moc: dict | None, dau: str, bay_gio: datetime.datetime,
              chong: float = TK_NGAY_CHONG) -> tuple[datetime.datetime, int, str]:
    """Cửa sổ ngày của lượt tìm một nền tảng. -> (từ lúc — 0 giờ của ngày đó, số ngày, lý do).

    Có mốc cùng dấu: số ngày = ceil(khoảng từ lượt tìm thành công trước + `TK_NGAY_CHONG`), kẹp
    [`TK_NGAY_TOI_THIEU`, `TK_NGAY_TOI_DA`]. Chưa có mốc / đổi từ khoá hay số bài / mốc hỏng:
    `TK_NGAY_TOI_DA`. Mốc đầu cửa sổ về 0 giờ (actor Facebook, TikTok lọc theo ngày)."""
    luc = None
    if not moc:
        ly = "chưa có mốc"
    elif moc.get("dau") != dau:
        ly = "đổi từ khoá/số bài"
    else:
        try:
            luc = datetime.datetime.fromisoformat(str(moc.get("luc") or ""))
            luc = luc if luc.tzinfo else luc.replace(tzinfo=_VN)
        except ValueError:
            luc = None
        ly = f"từ lượt tìm {luc.astimezone(_VN):%d/%m %H:%M}" if luc else "mốc hỏng"
    if luc is None:
        ngay = TK_NGAY_TOI_DA
    else:
        ngay = math.ceil((bay_gio - luc).total_seconds() / 86400 + chong)
        ngay = max(TK_NGAY_TOI_THIEU, min(TK_NGAY_TOI_DA, ngay))
    d_from = (bay_gio - datetime.timedelta(days=ngay)).replace(hour=0, minute=0, second=0,
                                                               microsecond=0)
    return d_from, ngay, ly


def _pheu_moi(ngay: int, ly: str) -> dict:
    """Phễu một nền tảng (chẩn đoán 16/10/2026: bài bị loại sau bước lọc ngày không ghi lý do —
    chủ dự án không thấy tiền đi đâu): về → trong phạm vi (ngoài phạm vi bỏ) → bài ĐÃ CÓ: cập
    nhật số liệu; bài MỚI: trùng / từ loại trừ / spam / AI loại (theo mã lý do) / không nhắc từ
    khoá → giữ (mới). `cua_so` = số bài nằm trong cửa sổ tăng dần (chỉ để đối chiếu)."""
    return {"ngay": ngay, "ly_do": ly, "ve": 0, "cua_so": 0, "pham_vi": 0, "ngoai_pham_vi": 0,
            "cap_nhat": 0, "da_loai_truoc": 0, "trung": 0, "loai_tru": 0, "spam": 0,
            "ai_loai": {},
            "khong_nhac": 0, "giu": 0, "moi": 0, "xin": 0, "xin_ly_do": ""}


def _tim_tu_khoa(v, du_an: dict, luot: int, con: float, han: float) -> dict:
    """Tìm theo từ khoá + phân xử AI + ghi kho. -> thống kê. Lỗi Apify của một nền tảng không
    làm hỏng nền tảng khác; bot khởi động lại giữa lượt tìm thì KHÔNG gửi lại (không kiểm
    được lượt cũ trả gì — tiền vẫn chốt theo run id).

    Mốc lượt tìm thành công (không lỗi, actor trả ≥ 1 item) chỉ ghi SAU khi bài đã vào kho —
    hỏng giữa chừng thì lượt sau lùi lại từ mốc cũ, không mất khoảng nào."""
    tk = {"tu": [], "lay": 0, "giu": 0, "moi": 0, "cu": 0, "de_xuat": 0, "usd": 0.0,
          "ghi_chu": [], "ai": "", "pheu": {}}
    cfg = {p: cau_hinh(du_an, "tu_khoa", p) for p in TK_NEN_TANG}
    if not any(c["bat"] for c in cfg.values()) and not cfg["facebook"]["duong2"]["bat"]:
        return tk
    fb_toi_da = _fb_toi_da()
    ma = du_an["ma"]
    tu = tu_tim(du_an)
    tk["tu"] = tu
    bay_gio = datetime.datetime.now(_VN)
    moc_cu = doc_moc_tk(ma)
    moc_moi: dict[str, dict] = {}
    tu_pv, ngay_pv, ly_pv = TDA.pham_vi(ma, bay_gio)
    tk["pham_vi"] = {"tu": tu_pv.isoformat(timespec="minutes"), "ngay": ngay_pv, "ly_do": ly_pv}
    phan = _phan_tk(v)
    da_xong = {ph["nen_tang"] for ph in phan if ph.get("loai") == "moc"}
    co_run = {ph["nen_tang"] for ph in phan if ph.get("run_id")}
    # Giãn nhịp đường tìm ít bài mới (18/10/2026, `gian_nhip`): chiến dịch đang chạy thì không giãn.
    try:
        from dashboard import lich_quet as LQ
        cd_dang = LQ.chien_dich_dang_chay(K.lich_chien_dich(ma), bay_gio) is not None
    except K.LoiKho:
        cd_dang = False
    hits: list[tuple] = []
    web_cho: list[tuple] = []        # (hits web, từ khoá web, đã loại) — sau mạng xã hội
    try:
        # Đường 2 Facebook (17/10/2026) chạy NGAY SAU đường chính, trước các nền tảng sau: gộp bài
        # vào `hits` + phễu Facebook; lỗi của nó không làm hỏng đường chính (và ngược lại).
        for p in (*TK_NEN_TANG[:TK_NEN_TANG.index("facebook") + 1], TK_FB2,
                  *TK_NEN_TANG[TK_NEN_TANG.index("facebook") + 1:]):
            if p == TK_FB2:
                if p not in da_xong and cfg["facebook"]["duong2"]["bat"] \
                        and A._FETCH.get(TK_FB2) is not None:
                    tien = _tim_fb_duong2(v, du_an, luot, cfg["facebook"]["duong2"], tu,
                                          min(con, _con_viec(v)), han, bay_gio, moc_cu, moc_moi,
                                          tu_pv, hits, tk, p in co_run)
                    con = max(0.0, con - tien)
                    tk["usd"] += tien
                continue
            if p in da_xong or not cfg[p]["bat"]:
                continue
            so_bai = cfg[p]["so_bai"]
            q = _tu_cho(p, tu, cfg[p]["so_tu"], so_bai)
            if not q:
                continue
            if p in co_run:
                tk["ghi_chu"].append(f"tìm {_TEN[p]}: bot khởi động lại giữa lượt tìm — không gửi lại")
                _them_phan_tk(v, {"id": f"tk-{p}", "loai": "moc", "nen_tang": p,
                                  "trang_thai": "loi", "ma": "KHONG_KIEM_DUOC", "usd_so": 0.0})
                continue
            dung, ly_tat = ((A._youtube_co_key(), "máy chạy Mark chưa có YOUTUBE_DATA_API_KEY")
                            if p == "youtube" else _nen_tang_dung_duoc(p))
            if not dung:
                # Review 17/10 (lượt 8: Threads bật trên dashboard mà không có dấu vết nào):
                # nền tảng BẬT cho dự án nhưng không chạy thì phải để lại lý do. YouTube thiếu
                # key là chuyện của máy chạy (không đổi giữa các lượt): chỉ phễu + phần, không
                # thêm câu vào ghi chú mỗi lượt.
                _bo_qua_tk(v, tk, p, "THIEU_KEY" if p == "youtube" else "TAT_CONSOLE", ly_tat,
                           ghi=p != "youtube")
                continue
            if p == "threads":
                # Đường 2 chạy TRƯỚC đường 1 (17/10/2026): rẻ (0,001 USD/bài, không phí khởi
                # động) mà phủ bài nổi — ngân sách/giờ chật thì đường đắt (futurizerush, 0,08 USD
                # khởi động) là đường bị co/bỏ, không phải đường rẻ. Bài đường 2 vào `hits` ngay
                # (gắn `_duong` = 2) để mọi nhánh `continue` của đường 1 bên dưới vẫn giữ chúng;
                # đường 1 về thì bài trùng mã được bỏ khỏi `hits` (`_bo_trung_duong_2`).
                tien2, hits2 = _tim_threads_2(v, du_an, luot, tu, bay_gio, moc_cu, moc_moi,
                                              min(con, _con_viec(v)), han, tk, tu_pv)
                con = max(0.0, con - tien2)
                tk["usd"] += tien2
                hits.extend(hits2)
            if p in TK_GIAN_NEN_TANG:
                # Giãn nhịp (18/10/2026): nhiều lượt liền gần như không ra bài mới → 2 ngày/lần.
                bo, ly_gian = gian_nhip(cfg[p].get("gian"),
                                        (moc_cu.get(KHOA_NHIP_TIM) or {}).get(p), bay_gio, cd_dang)
                if bo:
                    _bo_qua_tk(v, tk, p, "GIAN_NHIP", ly_gian)
                    continue
            # Threads (17/10/2026): ước tính theo SẢN LƯỢNG THẬT lượt trước (sổ mốc), không còn giả
            # định mỗi từ khoá đủ 10 bài — `san_luong_du_kien`. Tiền thật vẫn chặn ở phần còn lại
            # (`them["tran_usd"]` bên dưới).
            moc_th = (moc_cu.get(p) if isinstance(moc_cu.get(p), dict) else {}) \
                if p == "threads" else None
            uoc = (uoc_web(so_bai, tu, cfg[p]["boc"]) if p == "web"
                   else uoc_tu_khoa_nen_tang(p, so_bai, tu, cfg[p]["so_tu"], fb_toi_da,
                                             moc=moc_th))
            if p == "web":
                # Trần trang dự phòng là TRẦN, không phải tiền chắc tiêu: chỉ cần đủ cho phần
                # tìm Google; phần đọc dự phòng tự co theo phần còn lại (`nguon_web.thu_thap`).
                uoc = uoc_web(so_bai, tu, 0)
            co = None
            if p == "threads" and uoc > min(con, _con_viec(v)) + 1e-9:
                # Thứ tự co khi chật (17/10/2026): đường 2 (rẻ) đã chạy ở trên và chỉ lấy phần của
                # nó; đường 1 (phí khởi động 0,08) co về số từ khoá ĐẦU vừa phần còn lại — từ khoá
                # đứng đầu là từ chính của dự án ("hapas"), cũng là từ ra bài nhiều nhất. Ước tính
                # theo sản lượng nên từ khoá về 0 bài lượt trước không làm co oan.
                co = _co_threads(tu, so_bai, min(con, _con_viec(v)), moc_th)
                if co:
                    q, so_bai, uoc = co
                    tk["ghi_chu"].append(
                        f"tìm Threads: ngân sách còn {_usd(min(con, _con_viec(v)))} USD — co còn "
                        f"{len(q)}/{len(tu)} từ khoá đầu × {TH_TOI_THIEU_BAI} bài (ước tính "
                        f"{_usd(uoc)} USD)")
            if p == "threads" and not co and len(q) < min(len(tu), TH_TOI_DA_MOI_LUOT) \
                    and uoc <= min(con, _con_viec(v)) + 1e-9:
                # MỘT câu về số từ khoá Threads (câu co ngân sách ở trên thay câu này).
                tk["ghi_chu"].append(
                    f"tìm Threads: {len(q)}/{len(tu)} từ khoá đầu ({', '.join(q)[:80]}) — actor "
                    f"lấy ≥ {TH_TOI_THIEU_BAI} bài mỗi từ; đặt số bài Threads ≥ "
                    f"{TH_TOI_THIEU_BAI * min(len(tu), TH_TOI_DA_MOI_LUOT)} để tìm đủ")
            if uoc > min(con, _con_viec(v)) + 1e-9 or v.con_giay() < _CHUA_GIAY_CUOI + 60:
                het_gio = v.con_giay() < _CHUA_GIAY_CUOI + 60
                _bo_qua_tk(v, tk, p, "QUA_GIO" if het_gio else "NGAN_SACH",
                           "hết giờ" if het_gio else "hết ngân sách",
                           "" if het_gio else f"ước tính {_usd(uoc)} USD, còn "
                           f"{_usd(min(con, _con_viec(v)))} USD")
                continue
            if p == "web":
                tien, web_hits = _tim_web(v, du_an, luot, cfg[p], tu, min(con, _con_viec(v)),
                                          han, tk, bay_gio, moc_cu.get(p), moc_moi, tu_pv)
                con = max(0.0, con - tien)
                tk["usd"] += tien
                web_cho.append(web_hits)
                continue
            lim_cfg = min(so_bai, fb_toi_da) if p == "facebook" else so_bai
            dau = dau_tk(q, lim_cfg)
            d_from, ngay, ly_cs = cua_so_tk(moc_cu.get(p), dau, bay_gio)
            # Mốc tăng dần quyết định XIN bao nhiêu (bộ lọc ngày phía server + cỡ xin), không còn
            # quyết định GIỮ gì — xem `theo_doi_api`.
            lim, ly_xin = TDA.so_xin(lim_cfg, moc_cu.get(p),
                                     (moc_cu.get(p) or {}).get("dau") == dau)
            q_gui, xoay = q, None
            if p == "facebook" and fb_toi_da < 10 ** 6:
                q_gui, xoay, lim = TDA.xoay_fb(q, lim, lim_cfg, moc_cu.get(p),
                                               (moc_cu.get(p) or {}).get("dau") == dau)
            them: dict = {}
            if p == "youtube":
                # Rủi ro R7 cũ: lượt tìm YouTube của /theodoi không có trần trang search — nay
                # chỉ dùng phần quota search còn lại hôm nay (trừ phần việc nền khác đã giữ chỗ).
                trang = min(math.ceil(lim / TK_YT_MOI_TRANG),
                            A._youtube_con_trang(nen=True, ma=getattr(v, "ma", None)))
                if trang <= 0:
                    tk["ghi_chu"].append(f"tìm {_TEN[p]}: bỏ qua (hết quota search hôm nay)")
                    _them_phan_tk(v, {"id": f"tk-{p}", "loai": "moc", "nen_tang": p,
                                      "trang_thai": "loi", "ma": "HET_QUOTA", "usd_so": 0.0})
                    continue
                them["toi_da_trang"] = trang
            if p == "tiktok":
                # Review 16/10: chuỗi dự phòng (tính tiền theo VIDEO) chỉ được tiêu phần ngân
                # sách còn lại sau khi trừ ước tính API — không chỉ trần console.
                them["tran_du_phong"] = round(max(0.0, min(con, _con_viec(v)) - uoc), 2)
            if p == "threads":
                # Trần USD của run theo CÙNG ước tính đã giữ chỗ (`tran_threads_1`), không phải
                # cả phần tiền còn lại: một lượt bất ngờ nhiều bài dừng ở trần, giữ bài đã trả
                # tiền, không ăn phần đã giữ cho bình luận, kiểm độ phủ, web.
                them["tran_usd"] = tran_threads_1(uoc, min(con, _con_viec(v)))
            A._NEN_TANG.set(p)
            A._HAN_CHOT.set(han)
            A._KHI_CO_RUN.set(lambda run, meta, p=p: _them_phan_tk(v, {
                "id": f"tk-{p}-{run.get('id')}", "nen_tang": p, "run_id": run.get("id"),
                "actor": (meta or {}).get("actor"), "trang_thai": "dang_chay"}))
            got: list = []
            loi = None
            ma_loi = ""
            so_run_truoc = len(_phan_tk(v))
            ve_thuong = 0
            noi: dict = {}
            moi_nhat: dict = {}
            tag_feed: dict = {}
            # Lỗi từng từ khoá mà `_fanout` nuốt (IG/FB mỗi từ một run) — xem `_loi_tim`.
            loi_tu: list = []
            tok_loi = A._LOI_TU_KHOA.set(loi_tu)
            try:
                got = A._FETCH[p](q_gui, lim, "VN", d_from, bay_gio, **them) or []
                ve_thuong = len(got)
                if p == "tiktok":
                    # Trang "mới nhất" rồi lượt nổi — cả hai tự bắt lỗi của mình (review 17/10,
                    # M1): bài lượt thường đã trả tiền luôn vào phễu dù phần thêm hỏng.
                    got, moi_nhat = _them_luot_moi(v, ma, luot, q, got, moc_cu, bay_gio, uoc,
                                                   con, _phan_tk(v)[so_run_truoc:],
                                                   KDP.cau_hinh(du_an)["bat"])
                    got, noi = _them_luot_noi(v, ma, luot, q, got, moc_cu, bay_gio, uoc, con,
                                              _phan_tk(v)[so_run_truoc:],
                                              KDP.cau_hinh(du_an)["bat"])
                    # Feed hashtag của từ khoá một chữ (17/10/2026) — phần thêm, tự bắt lỗi.
                    got, tag_feed = _them_feed_tag(v, ma, luot, tu, got, moc_cu, bay_gio,
                                                   cfg[p]["hashtag"], con,
                                                   _phan_tk(v)[so_run_truoc:],
                                                   KDP.cau_hinh(du_an)["bat"])
            except Exception as e:
                if type(e).__name__ == "MatQuyen":
                    raise
                ma_loi, loi = _loi_tim(getattr(e, "ma", "") or type(e).__name__, str(e))
            finally:
                A._KHI_CO_RUN.set(None)
                A._LOI_TU_KHOA.reset(tok_loi)
            if loi is None and not got and loi_tu:
                # Mọi từ khoá đều hỏng mà `_fanout` không ném: là LỖI của nền tảng (không dời mốc,
                # nói lý do) chứ không phải "về 0" — mã nặng nhất thắng như `_tong_hop_nguon`.
                x = max(loi_tu, key=lambda m: A._DO_NANG.get(m.get("ma"), 0))
                ma_loi, loi = _loi_tim(x.get("ma") or "LOI", str(x.get("ly_do") or ""))
            if loi is not None:
                tk["ghi_chu"].append(f"tìm {_TEN[p]}: {loi}")
                # Sổ việc (`pheu_tu_khoa`) giữ lý do như phễu bỏ qua; `_cau_tk` không lặp dòng.
                tk["pheu"][p] = {**_pheu_moi(ngay, ly_cs), "loi": loi, "ma_loi": ma_loi}
            # Threads: phí khởi động 0,08 USD mất cả khi actor trả 0 bài — vẫn trừ vào phần còn.
            co_khoi = bool(got) or (p == "threads" and loi is None)
            tien = round(len(got) * _TK_GIA.get(p, 0.0)
                         + (_TK_KHOI.get(p, 0.0) * (len(A._IG_TAB) if p == "instagram" else 1)
                            if _TK_GIA.get(p) and co_khoi else 0.0), 4)
            if p == "tiktok":
                tien = _tien_tim_tiktok(_phan_tk(v)[so_run_truoc:], got, loi,
                                        them.get("tran_du_phong"))
            for ph in _phan_tk(v):
                if (ph.get("nen_tang") == p and ph.get("run_id")
                        and ph.get("trang_thai") == "dang_chay"):
                    v.cap_nhat_phan(ph, trang_thai="xong" if loi is None else "loi")
            _them_phan_tk(v, {"id": f"tk-{p}", "loai": "moc", "nen_tang": p,
                              "trang_thai": "xong" if loi is None else "loi", "usd_so": tien,
                              "so_item": len(got),
                              **({"ma": ma_loi, "ly_do": loi[:200]} if loi is not None else {}),
                              "cua_so": {"tu": d_from.isoformat(timespec="minutes"),
                                         "ngay": ngay, "ly_do": ly_cs}})
            con = max(0.0, con - tien)
            tk["usd"] += tien
            if loi is not None:
                continue
            ph_p = tk["pheu"][p] = _pheu_moi(ngay, ly_cs)
            ph_p.update(ve=len(got), xin=lim, xin_ly_do=ly_xin)
            if p == "threads":
                # Phễu nói ước tính dựa vào đâu (sản lượng lượt trước hay trần) — đối chiếu "co còn".
                ph_p["xin_ly_do"] = (f"{ly_xin}; ước tính {_usd(uoc)} USD, " + san_luong_du_kien(
                    q, max(TH_TOI_THIEU_BAI, so_bai // len(q)), moc_th,
                    max(so_bai, TH_TOI_THIEU_BAI))[1])
                _bo_trung_duong_2(hits, got, tk)
            if loi_tu:
                # Có bài nhưng vài từ khoá hỏng: phễu nói từ nào, vì sao (mã → nhãn ngắn).
                ph_p["loi_mot_phan"] = "; ".join(
                    f"'{x.get('tu_khoa') or '?'}' {A.nhan_ma(x.get('ma'))}" for x in loi_tu)[:300]
            if moi_nhat:
                ph_p["moi_nhat"] = moi_nhat   # mốc từng từ đã ghi ngay trong `_them_luot_moi`
            if noi:
                ph_p["noi"] = noi             # mốc nhịp đã ghi ngay trong `_them_luot_noi`
            if tag_feed:
                ph_p["tag_feed"] = tag_feed   # mốc nhịp đã ghi ngay trong `_them_feed_tag`
            for d, dt in got:
                # Giữ MỌI bài trong PHẠM VI theo dõi (chủ dự án 16/10), không chỉ cửa sổ tăng dần.
                if dt and tu_pv <= dt <= bay_gio + datetime.timedelta(hours=1) and d.get("link"):
                    d["platform"] = p
                    hits.append((d, dt))
                    ph_p["pham_vi"] += 1
                    ph_p["cua_so"] += d_from <= dt
                else:
                    ph_p["ngoai_pham_vi"] += 1
            if got:
                # `ve` = bài của lượt THƯỜNG (`so_xin` co giãn theo nó) — không tính lượt nổi.
                moc_moi[p] = {"luc": bay_gio.isoformat(timespec="seconds"), "dau": dau,
                              "luot": luot, "xin": lim, "ve": ve_thuong}
                if xoay is not None:
                    moc_moi[p]["xoay"] = xoay
                if p == "threads":
                    # Bài về TỪNG từ khoá (futurizerush `search_keyword`) — ước tính lượt sau theo
                    # sản lượng thật (`san_luong_du_kien`). Từ khoá gửi mà 0 bài ghi 0: lượt sau
                    # không tính nó đủ trần nữa.
                    moc_moi[p]["ve_tu"] = _dem_ve_tu(q_gui, got, "search_keyword")
        tk["lay"] = len(hits) + sum(len(x[0]) for x in web_cho)
        if hits:
            _tach_va_giu(du_an, luot, hits, tu, han, tk)
        for h, tu_web, bo in web_cho:
            # Từ khoá web có thể thêm khẩu hiệu chiến dịch -> sổ "đã loại" RIÊNG ("<mã>:web"),
            # không đè sổ của mạng xã hội (`theo_doi_api.ghi_loai` giữ một dấu mỗi khoá dự án).
            # Bài `nguon_web` loại theo luật (không nhắc, từ loại trừ, spam) vào cùng sổ.
            tk["_bi_loai"] = list(bo)
            if h:
                _tach_va_giu(du_an, luot, h, tu_web, han, tk, ma_loai=f"{ma}:web")
            con_lai = tk.pop("_bi_loai", None)
            if con_lai:
                TDA.ghi_loai(f"{ma}:web", TDA.dau_loai(du_an, tu_web), con_lai, tu_pv)
        for p, m in moc_moi.items():
            f = tk["pheu"].get(p) or {}
            m["huu_ich"] = int(f.get("moi", 0)) + int(f.get("cap_nhat", 0))
        # Lịch sử (giờ, về, mới) của lượt tìm vừa chạy xong, không lỗi — kể cả về 0 bài (mốc tăng
        # dần thì không ghi khi về 0) — cho `gian_nhip` lượt sau.
        nhip = dict(moc_cu.get(KHOA_NHIP_TIM) or {})
        for p in TK_GIAN_NEN_TANG:
            f = tk["pheu"].get(p)
            if not f or f.get("bo_qua") or f.get("loi") or p in da_xong:
                continue
            ls = list(((nhip.get(p) if isinstance(nhip.get(p), dict) else {}).get("lich_su"))
                      or [])
            ls.append([bay_gio.isoformat(timespec="seconds"), int(f.get("ve") or 0),
                       int(f.get("moi") or 0)])
            nhip[p] = {"lich_su": ls[-TK_GIAN_LICH_SU:]}
        if nhip:
            moc_moi[KHOA_NHIP_TIM] = nhip
        ghi_moc_tk(ma, moc_moi)
        if cfg["tiktok"]["bat"] and "tiktok_lam_moi" not in da_xong \
                and _nen_tang_dung_duoc("tiktok")[0]:
            lm = TDA.lam_moi_tiktok(v, ma, luot, tu_pv, min(con, _con_viec(v)),
                                    lambda ph: _them_phan_tk(v, ph))
            _them_phan_tk(v, {"id": "lm-tiktok", "loai": "moc", "nen_tang": "tiktok_lam_moi",
                              "trang_thai": "xong", "usd_so": lm["usd"],
                              "so_item": lm["cap_nhat"]})
            tk["lam_moi"] = lm
            tk["usd"] += lm["usd"]
            if lm.get("ghi_chu"):
                tk["ghi_chu"].append(lm["ghi_chu"])
    finally:
        if tk["pheu"]:
            # Sổ việc nền giữ phễu cùng run id và tiền của từng phần — đối chiếu tiền đi đâu.
            # Gộp (không thay): chạy lại sau khởi động lại chỉ có các nền tảng chưa xong.
            with v._khoa:
                v.d.setdefault("pheu_tu_khoa", {}).update(tk["pheu"])
                v.luu()
    tk["usd"] = round(tk["usd"], 4)
    return tk


def _loi_tim(ma: str, ly: str) -> tuple[str, str]:
    """(mã, câu lỗi) của MỘT nền tảng trong lượt tìm — câu vào ghi chú lượt + phễu sổ việc.

    CHI_DEMO (17/10/2026, Instagram gói Free trả `{"demo": true}`): nhãn đã đủ lý do và cách sửa;
    lời Apify ("subscribe to a paid plan") chỉ làm dài. Mã khác giữ nguyên dạng "MÃ: lý do"."""
    if ma == "CHI_DEMO":
        return ma, f"{A.nhan_ma(ma)} — nâng gói Apify hoặc đổi actor"
    return ma, A._che_token(f"{ma}: {ly}")[:150]


def _bo_qua_tk(v, tk: dict, p: str, ma: str, ly: str, chi_tiet: str = "",
               ghi: bool = True) -> None:
    """Nền tảng BẬT cho dự án mà lượt này không tìm: phần "moc" (mã `ma`) + câu ghi chú + phễu
    `{"bo_qua": ly}` — sổ việc (`pheu_tu_khoa`) và `luot_quet.ghi_chu` đều thấy lý do.
    Chẩn đoán 17/10: Threads của HAPAS bật mà lượt 8 không có dòng phễu nào — nhánh công tắc
    console tắt bỏ qua im lặng, còn câu "bỏ qua (hết ngân sách)" nằm SAU các dòng phễu dài nên
    bị cắt mất ở 2.000 ký tự của `luot_quet.ghi_chu` (trần cũ; từ 17/10/2026 là
    `lang_nghe_db.GHI_CHU_TOI_DA`)."""
    if ghi:
        tk["ghi_chu"].append(f"tìm {_TEN.get(p, p)}: bỏ qua ({ly})"
                             + (f" — {chi_tiet}" if chi_tiet else ""))
    ly = f"{ly} — {chi_tiet}" if chi_tiet else ly
    tk["pheu"][p] = {**_pheu_moi(0, ly), "bo_qua": ly}
    _them_phan_tk(v, {"id": f"tk-{p}", "loai": "moc", "nen_tang": p, "trang_thai": "loi",
                      "ma": ma, "usd_so": 0.0, "ly_do": ly[:200]})


def _co_threads(tu: list[str], so_bai: int, con: float,
                moc: dict | None = None) -> tuple[list[str], int, float] | None:
    """Threads không đủ tiền cho số bài cấu hình: co về số từ khoá ĐẦU nhiều nhất còn vừa phần
    còn lại (mỗi từ `TH_TOI_THIEU_BAI` bài — mức actor tính tối thiểu) thay vì bỏ cả nền tảng.
    Phí khởi động 0,08 USD/lượt là cố định nên tìm 1 từ (từ khoá chính đứng đầu) vẫn đáng.
    `moc` (17/10/2026): ước tính theo sản lượng lượt trước (`san_luong_du_kien`), như lượt chạy.
    -> (từ khoá, số bài, ước tính) hoặc None khi 1 từ cũng không vừa."""
    for n in range(min(len(_tu_cho("threads", tu, so_bai=so_bai)), TH_TOI_DA_MOI_LUOT), 0, -1):
        sb = n * TH_TOI_THIEU_BAI
        u = uoc_tu_khoa_nen_tang("threads", sb, tu, moc=moc)
        if u <= con + 1e-9:
            return _tu_cho("threads", tu, so_bai=sb), sb, u
    return None


def _duong_fb(tk: dict, ngay: int, ly: str, dung_lai: bool = True) -> dict | None:
    """Phễu Facebook để gộp đường 2; `duong.scrapeforge` ghi trạng thái đường chính (số về / lỗi /
    bỏ qua / tắt). Đường chính lỗi / bỏ qua / tắt mà `dung_lai` (đường 2 có bài hoặc chạy được) thì
    phễu được dựng lại từ đường 2 — chủ dự án vẫn thấy bài đường 2, lý do đường chính nằm trong
    `duong`. `dung_lai`=False và đường chính tắt (chưa có phễu): None."""
    f = tk["pheu"].get("facebook")
    chinh = ({"tat": True} if f is None
             else {"loi": f["loi"], "ma_loi": f.get("ma_loi")} if f.get("loi")
             else {"bo_qua": f["bo_qua"]} if f.get("bo_qua") else {"ve": int(f.get("ve") or 0)})
    if f is None or ((f.get("loi") or f.get("bo_qua")) and dung_lai):
        if not dung_lai:
            return None
        f = tk["pheu"]["facebook"] = _pheu_moi(ngay, ly)
    f.setdefault("duong", {}).setdefault("scrapeforge", chinh)
    return f


def _tim_fb_duong2(v, du_an: dict, luot: int, c2: dict, tu: list[str], con: float, han: float,
                   bay_gio: datetime.datetime, moc_cu: dict, moc_moi: dict,
                   tu_pv: datetime.datetime, hits: list, tk: dict, co_run: bool) -> float:
    """Đường 2 Facebook (mina) của lượt tìm. -> USD theo sổ. Bài trong phạm vi vào `hits` (cùng phễu
    với scrapeforge), đếm vào phễu Facebook + `duong.mina`. KHÔNG ném lỗi (trừ MatQuyen): lỗi ghi
    vào ghi chú + phễu, bài đã trả tiền vẫn giữ. Mốc riêng `TK_FB2` (cửa sổ ngày + nhịp `gio`)."""
    ma = du_an["ma"]
    ten = "tìm Facebook (đường 2)"
    q = tu_fb_duong2(du_an, tu)
    per = int(c2["so_bai_moi_tu"])

    def bo_qua(ma_ly: str, ly: str, trang_thai: str = "loi") -> float:
        tk["ghi_chu"].append(f"{ten}: bỏ qua ({ly})")
        f = _duong_fb(tk, 0, "", dung_lai=False)
        if f is not None:
            f["duong"]["mina"] = {"bo_qua": ly}
        _them_phan_tk(v, {"id": f"tk-{TK_FB2}", "loai": "moc", "nen_tang": TK_FB2,
                          "trang_thai": trang_thai, "ma": ma_ly, "usd_so": 0.0, "ly_do": ly[:200]})
        return 0.0
    if not q:
        return bo_qua("KHONG_CO_CUM", "dự án không có từ khoá nhiều chữ chứa tên brand", "xong")
    if co_run:
        return bo_qua("KHONG_KIEM_DUOC", "bot khởi động lại giữa lượt tìm — không gửi lại")
    dung, ly_tat = _nen_tang_dung_duoc("facebook")
    if not dung:
        return bo_qua("TAT_CONSOLE", ly_tat)
    moc = moc_cu.get(TK_FB2) if isinstance(moc_cu.get(TK_FB2), dict) else {}
    cd, _ = khau_hieu_chien_dich(ma, bay_gio)
    gio = int(c2["gio_chien_dich"] if cd else c2["gio"])
    luc = TDA._gio(moc.get("luc"))
    if luc is not None and gio > 0 and bay_gio - luc < datetime.timedelta(hours=gio):
        return bo_qua("CHUA_TOI_LUOT", f"lượt trước {luc.astimezone(_VN):%d/%m %H:%M}, mỗi {gio} "
                                       "giờ" + (" trong chiến dịch" if cd else ""), "xong")
    if v.con_giay() < _CHUA_GIAY_CUOI + 60:
        return bo_qua("QUA_GIO", "hết giờ")
    # Co còn theo ngân sách (như Threads): giữ số cụm ĐẦU nhiều nhất còn vừa phần còn lại.
    mot = uoc_fb_duong2(1, per)
    vua = int(con / mot + 1e-9) if mot > 0 else 0
    if vua < 1:
        return bo_qua("NGAN_SACH", f"hết ngân sách — ước tính {_usd(mot)} USD/cụm, còn "
                                   f"{_usd(con)} USD")
    if vua < len(q):
        tk["ghi_chu"].append(f"{ten}: ngân sách còn {_usd(con)} USD — co còn {vua}/{len(q)} cụm "
                             f"đầu ({_usd(uoc_fb_duong2(vua, per))} USD)")
        q = q[:vua]
    dau = dau_tk(q, per)
    d_from, ngay, ly_cs = cua_so_tk(moc, dau, bay_gio)
    # Trần MỖI run (`maxTotalChargeUsd`): trần console của Facebook, ước tính × 1,5, phần còn của
    # tháng/việc — `_run_actor` kẹp sàn 0,1 USD; tiền thật vẫn chặn bởi `limit` bài mỗi run.
    tran = round(min(A._tran_nen_tang("facebook", nen=True)[1],
                     max(_TRAN_TOI_THIEU, mot * _HE_SO_TRAN), max(_TRAN_TOI_THIEU, con)), 2)
    truoc = len(_phan_tk(v))
    rows: list = []
    loi, ma_loi = None, ""
    loi_tu: list = []
    dat = [(A._NEN_TANG, "facebook"), (A._HAN_CHOT, han), (A._LOI_TU_KHOA, loi_tu),
           (A._KHI_CO_RUN, lambda run, meta: _them_phan_tk(v, {
               "id": f"tk-{TK_FB2}-{run.get('id')}", "nen_tang": TK_FB2, "run_id": run.get("id"),
               "actor": A._ACTORS["facebook_duong2"], "trang_thai": "dang_chay"}))]
    bien_cu = [(bien, bien.set(gt)) for bien, gt in dat]
    try:
        rows = A._FETCH[TK_FB2](q, per, d_from, bay_gio, tran_usd=tran) or []
    except Exception as e:
        if type(e).__name__ == "MatQuyen":
            raise
        ma_loi, loi = _loi_tim(getattr(e, "ma", "") or type(e).__name__, str(e))
    finally:
        for bien, t in reversed(bien_cu):
            bien.reset(t)
    if loi is None and not rows and loi_tu:
        x = max(loi_tu, key=lambda m: A._DO_NANG.get(m.get("ma"), 0))
        ma_loi, loi = _loi_tim(x.get("ma") or "LOI", str(x.get("ly_do") or ""))
    run = [x for x in _phan_tk(v)[truoc:] if x.get("run_id")]
    tien = round(len(rows) * TK_FB2_GIA + len(run) * TK_FB2_KHOI, 4)
    for ph in run:
        if ph.get("trang_thai") == "dang_chay":
            v.cap_nhat_phan(ph, trang_thai="xong" if loi is None else "loi")
    _them_phan_tk(v, {"id": f"tk-{TK_FB2}", "loai": "moc", "nen_tang": TK_FB2,
                      "trang_thai": "xong" if loi is None else "loi", "usd_so": tien,
                      "so_item": len(rows),
                      **({"ma": ma_loi, "ly_do": loi[:200]} if loi is not None else {}),
                      "cua_so": {"tu": d_from.isoformat(timespec="minutes"), "ngay": ngay,
                                 "ly_do": ly_cs}})
    dem: dict[str, int] = {}
    for d, _ in rows:
        dem[d.get("_cum") or ""] = dem.get(d.get("_cum") or "", 0) + 1
    tom = {"ve": len(rows), "cum": len(q), "moi_cum": per, "usd": tien, "ngay": ngay,
           "ly_do": ly_cs, "day": [c for c in q if dem.get(c, 0) >= per]}
    if loi_tu:
        tom["loi_mot_phan"] = "; ".join(f"'{x.get('tu_khoa') or '?'}' {A.nhan_ma(x.get('ma'))}"
                                        for x in loi_tu)[:300]
    if loi is not None:
        tom.update(loi=loi, ma_loi=ma_loi)
        tk["ghi_chu"].append(f"{ten}: {loi}")
    f = _duong_fb(tk, ngay, ly_cs, dung_lai=bool(rows) or loi is None)
    if f is None:
        # Đường chính tắt, đường 2 lỗi 0 bài: phễu mang lỗi (không thành dòng "về 0"), sổ việc giữ.
        f = tk["pheu"]["facebook"] = {**_pheu_moi(ngay, ly_cs), "loi": loi, "ma_loi": ma_loi,
                                      "duong": {"scrapeforge": {"tat": True}}}
    f["duong"]["mina"] = tom
    for d, dt in rows:
        f["ve"] += 1
        if dt and tu_pv <= dt <= bay_gio + datetime.timedelta(hours=1) and d.get("link"):
            d["platform"] = "facebook"
            hits.append((d, dt))
            f["pham_vi"] += 1
            f["cua_so"] += d_from <= dt
        else:
            f["ngoai_pham_vi"] += 1
    if rows and loi is None:
        # Mốc riêng của đường 2: cửa sổ ngày lượt sau + nhịp `gio` (ghi cùng mốc các nền tảng,
        # SAU khi bài vào kho — `ghi_moc_tk(ma, moc_moi)` cuối lượt tìm).
        moc_moi[TK_FB2] = {"luc": bay_gio.isoformat(timespec="seconds"), "dau": dau, "luot": luot,
                           "xin": per, "ve": len(rows)}
    return tien


def _tim_threads_2(v, du_an: dict, luot: int, tu: list[str], bay_gio: datetime.datetime,
                   moc_cu: dict, moc_moi: dict, con: float, han: float, tk: dict,
                   tu_pv: datetime.datetime) -> tuple[float, list]:
    """Đường 2 của Threads trong lượt tìm theo từ khoá. -> (USD theo sổ, [(dòng, ngày)] trong phạm
    vi theo dõi, đã gắn `platform` = "threads" và `_duong` = 2).

    KHÔNG BAO GIỜ ném lỗi (trừ MatQuyen): đường 2 hỏng thì đường 1 vẫn chạy như trước. Phễu riêng
    `tk["pheu"]["threads_2"]` (sổ việc giữ cùng `pheu_tu_khoa`), mốc riêng `threads_2` trong sổ mốc
    (cửa sổ ngày, sản lượng, chuỗi lượt về 0 bài). Bot khởi động lại giữa đường 2 thì không gửi lại
    (như mọi nền tảng — tiền vẫn chốt theo run id). Bộ thử thay `A._FETCH` mà không có bộ tìm đường
    2 thì bỏ qua lặng lẽ (máy chạy thật luôn có — `apify_tool._FETCH`)."""
    fn = A._FETCH.get(TH2_KHOA)
    c2 = cau_hinh_th2(du_an)
    q = _tu_th2(tu)
    if fn is None or not c2["bat"] or not q:
        return 0.0, []
    phan = _phan_tk(v)
    if any(ph.get("nen_tang") == TH2_KHOA and ph.get("loai") == "moc" for ph in phan):
        return 0.0, []                                   # đã xong trước khi bot khởi động lại
    if any(ph.get("nen_tang") == TH2_KHOA and ph.get("run_id") for ph in phan):
        tk["ghi_chu"].append("tìm Threads đường 2: bot khởi động lại giữa lượt tìm — không gửi lại")
        _them_phan_tk(v, {"id": f"tk-{TH2_KHOA}", "loai": "moc", "nen_tang": TH2_KHOA,
                          "trang_thai": "loi", "ma": "KHONG_KIEM_DUOC", "usd_so": 0.0})
        return 0.0, []
    moc = moc_cu.get(TH2_KHOA) if isinstance(moc_cu.get(TH2_KHOA), dict) else {}
    moi_tu = c2["so_bai_moi_tu"]
    tran_bai = min(c2["so_bai"], moi_tu * len(q))
    # Dấu gồm cả trần mỗi từ + số lượt: đổi chúng là đổi tập bài actor trả → lùi cửa sổ tối đa.
    dau = dau_tk([*q, f"moi_tu:{moi_tu}", f"luot:{c2['so_luot']}"], tran_bai)
    d_from, ngay, ly_cs = cua_so_tk(moc if moc.get("luc") else None, dau, bay_gio)
    f2 = tk["pheu"][TH2_KHOA] = {**_pheu_moi(ngay, ly_cs), "actor": A._ACTORS[TH2_KHOA],
                                 "trung_duong_1": 0, "usd": 0.0}
    # Trần bài lượt này không vượt phần ngân sách còn lại: actor tính đúng theo bài nên `maxItems`
    # là trần TIỀN cứng — kể cả khi `_run_actor` kẹp trần USD gửi Apify lên tối thiểu 0,1.
    lim = (tran_bai if con >= tran_bai * TH2_GIA * _HE_SO_UOC
           else int(con / (TH2_GIA * _HE_SO_UOC) + 1e-9))
    het_gio = v.con_giay() < _CHUA_GIAY_CUOI + 60
    if het_gio or lim < min(TH_TOI_THIEU_BAI, tran_bai):
        ly = "hết giờ" if het_gio else "hết ngân sách"
        ct = "" if het_gio else (f"còn {_usd3(con)} USD, chưa đủ "
                                 f"{min(TH_TOI_THIEU_BAI, tran_bai)} bài × {_usd3(TH2_GIA)} USD")
        tk["ghi_chu"].append(f"tìm Threads đường 2: bỏ qua ({ly})" + (f" — {ct}" if ct else ""))
        f2["bo_qua"] = f"{ly} — {ct}" if ct else ly
        _them_phan_tk(v, {"id": f"tk-{TH2_KHOA}", "loai": "moc", "nen_tang": TH2_KHOA,
                          "trang_thai": "loi", "ma": "QUA_GIO" if het_gio else "NGAN_SACH",
                          "usd_so": 0.0, "ly_do": f2["bo_qua"][:200]})
        return 0.0, []
    f2.update(xin=lim, xin_ly_do=(f"trần {tran_bai} bài" if lim == tran_bai
                                  else f"co còn {lim}/{tran_bai} bài theo ngân sách còn "
                                       f"{_usd3(con)} USD")
              + "; " + san_luong_du_kien(q, moi_tu, moc, lim)[1])
    tran_usd = round(min(A._tran_nen_tang("threads", nen=True)[1],
                         max(A._TRAN_USD_KHOANG[0], lim * TH2_GIA * _HE_SO_TRAN)), 2)
    A._NEN_TANG.set("threads")
    A._HAN_CHOT.set(han)
    A._KHI_CO_RUN.set(lambda run, meta: _them_phan_tk(v, {
        "id": f"tk-{TH2_KHOA}-{run.get('id')}", "nen_tang": TH2_KHOA, "run_id": run.get("id"),
        "actor": (meta or {}).get("actor"), "trang_thai": "dang_chay"}))
    got: list = []
    loi = None
    ma_loi = ""
    try:
        got = fn(q, lim, "VN", d_from, bay_gio, moi_tu=moi_tu, so_luot=c2["so_luot"],
                 tran_usd=tran_usd) or []
    except Exception as e:
        if type(e).__name__ == "MatQuyen":
            raise
        ma_loi, loi = _loi_tim(getattr(e, "ma", "") or type(e).__name__, str(e))
    finally:
        A._KHI_CO_RUN.set(None)
    tien = round(len(got) * TH2_GIA, 4)
    for ph in _phan_tk(v):
        if ph.get("nen_tang") == TH2_KHOA and ph.get("run_id") \
                and ph.get("trang_thai") == "dang_chay":
            v.cap_nhat_phan(ph, trang_thai="xong" if loi is None else "loi")
    _them_phan_tk(v, {"id": f"tk-{TH2_KHOA}", "loai": "moc", "nen_tang": TH2_KHOA,
                      "trang_thai": "xong" if loi is None else "loi", "usd_so": tien,
                      "so_item": len(got),
                      **({"ma": ma_loi, "ly_do": loi[:200]} if loi is not None else {}),
                      "cua_so": {"tu": d_from.isoformat(timespec="minutes"), "ngay": ngay,
                                 "ly_do": ly_cs}})
    f2.update(ve=len(got), usd=tien)
    # Chuỗi lượt về 0 bài (cảnh báo nên tắt): lỗi của actor cũng là "về 0"; lỗi không do actor
    # (`_TH2_LOI_KHONG_DEM`) giữ nguyên chuỗi.
    rong_cu = moc.get("rong_lien") if isinstance(moc.get("rong_lien"), int) else 0
    rong = rong_cu
    if not got and ma_loi not in _TH2_LOI_KHONG_DEM:
        rong += 1
    elif got:
        rong = 0
    f2["rong_lien"] = rong
    if loi is not None:
        f2.update(loi=loi, ma_loi=ma_loi)
        tk["ghi_chu"].append(f"tìm Threads đường 2: {loi}")
    if rong >= TH2_RONG_CANH_BAO:
        f2["canh_bao"] = (f"đường 2 ({A._ACTORS[TH2_KHOA]}) về 0 bài {rong} lượt liền — actor "
                          "có thể hỏng hoặc bị Threads chặn; xem log run trên Apify, nếu vẫn 0 thì "
                          "tắt: du_an.cau_hinh.tu_khoa.threads.duong2.bat = false")
        tk["ghi_chu"].append(f"tìm Threads: CẢNH BÁO {f2['canh_bao']}")
    ra = []
    for d, dt in got:
        if dt and tu_pv <= dt <= bay_gio + datetime.timedelta(hours=1) and d.get("link"):
            d["platform"], d["_duong"] = "threads", 2
            ra.append((d, dt))
            f2["pham_vi"] += 1
            f2["cua_so"] += d_from <= dt
        else:
            f2["ngoai_pham_vi"] += 1
    if got:
        # Như đường 1: mốc chỉ dời khi về ≥ 1 bài và ghi SAU khi bài vào kho (`ghi_moc_tk` cuối
        # `_tim_tu_khoa`). `ve_tu`: sản lượng từng từ khoá — ước tính lượt sau theo số thật.
        moc_moi[TH2_KHOA] = {"luc": bay_gio.isoformat(timespec="seconds"), "dau": dau,
                             "luot": luot, "xin": lim, "ve": len(got),
                             "ve_tu": _dem_ve_tu(q, got, "searchKeyword"), "rong_lien": 0}
    elif rong != rong_cu:
        # 0 bài: KHÔNG dời mốc cửa sổ (giữ `luc`/`dau` cũ), chỉ ghi chuỗi lượt về 0.
        moc_moi[TH2_KHOA] = {**moc, "luot": luot, "rong_lien": rong}
    return tien, ra


def _dem_ve_tu(q: list[str], got: list, truong: str) -> dict[str, int] | None:
    """{từ khoá chuẩn hoá: số bài về} của một lượt Threads — mọi từ khoá ĐÃ GỬI đều có mặt (0 bài
    ghi 0, để lượt sau không coi nó là "chưa đo" và tính đủ trần). Bài không gắn được từ khoá
    (actor đổi tên trường `truong`) → None: ước tính lùi về tổng `ve`, không đoán sai từng từ."""
    def chuan(s) -> str:
        return A._norm(" ".join(str(s or "").split()))
    ra = {chuan(t): 0 for t in q if chuan(t)}
    for d, _ in got:
        k = chuan((d.get("__goc") if isinstance(d.get("__goc"), dict) else {}).get(truong))
        if not k:
            return None
        ra[k] = ra.get(k, 0) + 1
    return ra


def _bo_trung_duong_2(hits: list, got: list, tk: dict) -> None:
    """Bỏ khỏi `hits` bài đường 2 mà đường 1 cũng về (cùng MÃ bài trong link). Giữ bản đường 1:
    futurizerush có follower + lượt xem, scrapersdelight không. Khoá kho (băm link) của hai bản
    trùng nhau (đo 17/10: 14/14 link trùng từng ký tự) — bỏ ở đây để phễu đếm đúng bài RIÊNG của
    đường 2, không để `tach_da_biet` đếm thành "trùng"."""
    ma1 = {A.ma_bai_threads(d.get("link") or "") for d, _ in got}
    ma1.discard("")
    if not ma1:
        return
    f2 = tk["pheu"].get(TH2_KHOA)
    giu = []
    for d, dt in hits:
        if d.get("_duong") == 2 and A.ma_bai_threads(d.get("link") or "") in ma1:
            if f2 is not None:
                f2["trung_duong_1"] += 1
            continue
        giu.append((d, dt))
    hits[:] = giu


def _dem_duong_2(tk: dict, truong: str, n: int = 1) -> None:
    """Cộng `n` vào trường của phễu đường 2 (bài RIÊNG đường 2 qua các bước lọc sau)."""
    f2 = tk.get("pheu", {}).get(TH2_KHOA)
    if f2 is not None and n:
        f2[truong] = int(f2.get(truong) or 0) + n


def _them_luot_moi(v, ma: str, luot: int, q: list[str], got: list, moc_cu: dict,
                   bay_gio: datetime.datetime, uoc: float, con: float,
                   phan_moi: list[dict], dp_bat: bool = True) -> tuple[list, dict]:
    """Trang "mới nhất" TikTok (`theo_doi_api.tim_moi_tiktok`, 17/10/2026) ngay sau lượt tìm
    thường, cùng từ khoá, cùng móc ghi run id (tiền vào `_tien_tim_tiktok`). -> (bài thường +
    bài mới nhất chưa trùng, thống kê {"ve", "moi", "usd", "tu", "nghi", "trang", "ly_do"});
    {} khi lượt này không chạy. Như lượt nổi: KHÔNG ném lỗi (trừ MatQuyen), chỉ chạy khi lượt
    thường đi TikTok API và không xuống dự phòng, còn đủ giờ. Đã tiêu tiền thì ghi mốc ngay
    (nhịp + mốc từng từ khoá) — lượt sau không lật lại phần đã xem."""
    if not TDA.TT.dung_api("tiktok_tim"):
        return got, {}
    api = [x for x in phan_moi if x.get("run_id") and x.get("actor") == TT_ACTOR]
    if not api or any(x.get("run_id") and x.get("actor") != TT_ACTOR for x in phan_moi):
        return got, {}
    moc = moc_cu.get(TDA.KHOA_MOC_MOI) if isinstance(moc_cu.get(TDA.KHOA_MOC_MOI), dict) else {}
    den, ly = TDA.den_luot_moi(moc, bay_gio)
    if not den:
        return got, {}
    # Kiểm độ phủ có thể nới trần trang mỗi từ (`kiem_do_phu.hanh_dong`); tắt thì về mặc định.
    cfg = KDP.cau_hinh_noi(moc_cu.get(KDP.KHOA_NOI_CFG) if dp_bat else None)
    if cfg["moi_trang"] != TDA.MOI_TRANG_TOI_DA:
        ly += f"; theo kiểm độ phủ: tối đa {cfg['moi_trang']} trang/từ"
    if v.con_giay() < _CHUA_GIAY_CUOI + 120:
        return got, {"ve": 0, "moi": 0, "usd": 0.0, "ly_do": f"{ly}; bỏ qua (hết giờ)"}
    # Chừa phần lượt nổi nếu nó cũng tới hạn lượt này (nó chạy ngay sau).
    den_noi = TDA.den_luot_noi(moc_cu.get(TDA.KHOA_MOC_NOI), bay_gio, cfg["gio"])[0]
    du_noi = ((len(q) + len(cfg["tag"])) * cfg["trang"] * TK_TT_YEU_CAU) if den_noi else 0.0
    tran = TDA.tran_moi(len(q), uoc, len(api) * TK_TT_YEU_CAU, min(con, _con_viec(v)), du_noi,
                        cfg["moi_trang"])
    if tran < TK_TT_YEU_CAU:
        return got, {"ve": 0, "moi": 0, "usd": 0.0, "ly_do": f"{ly}; không còn ngân sách"}
    truoc = len(_phan_tk(v))
    ve: list = []
    tkm: dict = {}
    moc_moi: dict = {}
    try:
        ve, tkm, moc_moi = TDA.tim_moi_tiktok(q, moc, bay_gio, tran, cfg["moi_trang"])
    except Exception as e:  # phần thêm, không làm hỏng lượt thường
        if type(e).__name__ == "MatQuyen":
            raise
        ly = f"{ly}; lỗi " + A._che_token(f"{getattr(e, 'ma', type(e).__name__)}: {e}")[:120]
    usd = round(sum(TK_TT_YEU_CAU for x in _phan_tk(v)[truoc:]
                    if x.get("run_id") and x.get("actor") == TT_ACTOR), 4)
    if usd > 0:
        # Review LOW: đã trả tiền thì LUÔN ghi nhịp 20 giờ — kể cả khi lỗi trước lúc có mốc mới
        # (giữ mốc từng từ cũ: lượt sau lật lại đúng chỗ, không mất khoảng nào).
        moc_ghi = moc_moi or {**moc, "luc": bay_gio.isoformat(timespec="seconds")}
        ghi_moc_tk(ma, {TDA.KHOA_MOC_MOI: {**moc_ghi, "luot": luot, "ve": len(ve), "usd": usd}})
    if tkm.get("loi"):
        ly = f"{ly}; {tkm['loi']}"
    co = {d.get("link") for d, _ in got}
    them = [(d, dt) for d, dt in ve if d.get("link") and d["link"] not in co]
    return got + them, {"ve": len(ve), "moi": len(them), "usd": usd,
                        "tu": int(tkm.get("tu") or 0), "nghi": int(tkm.get("nghi") or 0),
                        "trang": int(tkm.get("trang") or 0), "ly_do": ly}


def _them_luot_noi(v, ma: str, luot: int, q: list[str], got: list, moc_cu: dict,
                   bay_gio: datetime.datetime, uoc: float, con: float,
                   phan_moi: list[dict], dp_bat: bool = True) -> tuple[list, dict]:
    """Lượt "nổi" TikTok (`theo_doi_api.tim_noi_tiktok`) ngay sau lượt tìm thường, cùng từ khoá,
    cùng móc ghi run id (tiền vào `_tien_tim_tiktok`). -> (bài thường + bài nổi chưa trùng, thống
    kê {"ve", "moi", "usd", "ly_do"}); {} khi lượt này không chạy lượt nổi.

    Review 17/10: KHÔNG ném lỗi (trừ MatQuyen) — lỗi ghi vào `ly_do`, bài lượt thường giữ nguyên.
    Chỉ chạy khi lượt thường có ≥ 1 run TikTok API và KHÔNG xuống dự phòng (API đang ổn), còn đủ
    giờ. Đã tiêu tiền (kể cả 0 bài / lỗi giữa chừng) thì ghi mốc nhịp NGAY — lượt sau không trả
    tiền lại trong `NOI_GIO_GIAN` giờ."""
    if not TDA.TT.dung_api("tiktok_tim"):
        return got, {}                    # chỉ đi TikTok API (dự phòng tính tiền theo video)
    api = [x for x in phan_moi if x.get("run_id") and x.get("actor") == TT_ACTOR]
    if not api or any(x.get("run_id") and x.get("actor") != TT_ACTOR for x in phan_moi):
        return got, {}                    # lượt thường không qua API / đã xuống dự phòng
    # Kiểm độ phủ (17/10/2026) có thể đã thêm hashtag chiến dịch / nới trang / dày nhịp cho lượt
    # nổi của dự án (`kiem_do_phu.hanh_dong`) — vẫn trong trần `tran_noi`.
    # Kiểm độ phủ đã tắt cho dự án → lượt nổi mặc định (review M3).
    cfg = KDP.cau_hinh_noi(moc_cu.get(KDP.KHOA_NOI_CFG) if dp_bat else None)
    den, ly = TDA.den_luot_noi(moc_cu.get(TDA.KHOA_MOC_NOI), bay_gio, cfg["gio"])
    if not den:
        return got, {}
    da = {TDA.TT.chuan_tag(t) for t in q}
    tag = [t for t in cfg["tag"] if t not in da]
    moc_dp = moc_cu.get(KDP.KHOA_MOC) if isinstance(moc_cu.get(KDP.KHOA_MOC), dict) else {}
    cid = dict(moc_dp.get("cid") or {}) if isinstance(moc_dp.get("cid"), dict) else {}
    if cfg["tag"] or cfg["trang"] != TDA.NOI_TRANG or cfg["gio"] != TDA.NOI_GIO_GIAN:
        ly += (f"; theo kiểm độ phủ: {cfg['trang']} trang/từ, mỗi {cfg['gio']} giờ"
               + (", #" + ", #".join(cfg["tag"]) if cfg["tag"] else ""))
    if v.con_giay() < _CHUA_GIAY_CUOI + 120:
        return got, {"ve": 0, "moi": 0, "usd": 0.0, "ly_do": f"{ly}; bỏ qua (hết giờ)"}
    # Mỗi hashtag: 1 yêu cầu tìm cid (khi chưa nhớ) + `trang` trang feed — tính như một "từ".
    tran = TDA.tran_noi(len(q) + len(tag), uoc, len(api) * TK_TT_YEU_CAU,
                        min(con, _con_viec(v)), cfg["trang"])
    if tran < TK_TT_YEU_CAU:
        return got, {"ve": 0, "moi": 0, "usd": 0.0, "ly_do": f"{ly}; không còn ngân sách"}
    truoc = len(_phan_tk(v))
    ve: list = []
    try:
        cid_truoc = dict(cid)
        ve = (TDA.tim_noi_tiktok(q, bay_gio, tran, cfg["trang"], tag=tag, cid=cid) if tag
              else TDA.tim_noi_tiktok(q, bay_gio, tran, cfg["trang"]))
        if cid != cid_truoc:          # cid mới tìm được: nhớ vào mốc kiểm độ phủ (đỡ 1 yêu cầu)
            ghi_moc_tk(ma, {KDP.KHOA_MOC: {**moc_dp, "cid": cid}})
    except Exception as e:  # lượt nổi là phần thêm, không làm hỏng lượt thường
        if type(e).__name__ == "MatQuyen":
            raise
        loi = A._che_token(f"{getattr(e, 'ma', type(e).__name__)}: {e}")[:120]
        ly = f"{ly}; lỗi {loi}"
    usd = round(sum(TK_TT_YEU_CAU for x in _phan_tk(v)[truoc:]
                    if x.get("run_id") and x.get("actor") == TT_ACTOR), 4)
    if usd > 0:
        ghi_moc_tk(ma, {TDA.KHOA_MOC_NOI: {"luc": bay_gio.isoformat(timespec="seconds"),
                                           "luot": luot, "ve": len(ve), "usd": usd}})
    co = {d.get("link") for d, _ in got}
    them = [(d, dt) for d, dt in ve if d.get("link") and d["link"] not in co]
    return got + them, {"ve": len(ve), "moi": len(them), "usd": usd, "ly_do": ly}


def _them_feed_tag(v, ma: str, luot: int, tu: list[str], got: list, moc_cu: dict,
                   bay_gio: datetime.datetime, ctag: dict, con: float, phan_moi: list[dict],
                   dp_bat: bool = True) -> tuple[list, dict]:
    """Feed HASHTAG TikTok (`challengePosts`) của từ khoá một chữ (`tag_tiktok`), ngay sau lượt nổi,
    cùng móc ghi run id (tiền vào `_tien_tim_tiktok`). -> (bài thường + bài feed chưa trùng, thống kê
    {"tag": {tag: {"trang", "bai", "loi"}}, "chua_toi", "yeu_cau", "ve", "moi", "usd", "ly_do"});
    {} khi lượt này không chạy (tắt, chưa tới nhịp `gio`, lượt thường không đi TikTok API).

    Trần = min(`so_yeu_cau` × 0,003 USD, phần còn của tháng/việc trừ tiền TikTok API đã tiêu trong
    lượt). Yêu cầu chia theo `kiem_do_phu.chia_yeu_cau` (mỗi tag: tìm cid khi chưa nhớ + 1 trang, dư
    thì thêm trang theo thứ tự từ khoá); tag lượt nổi đang đọc (kiểm độ phủ thêm) bỏ — không trả
    tiền hai lần. KHÔNG ném lỗi (trừ MatQuyen); đã tiêu tiền thì ghi mốc nhịp NGAY."""
    if not ctag.get("bat") or not TDA.TT.dung_api("tiktok_tim"):
        return got, {}
    api = [x for x in phan_moi if x.get("run_id") and x.get("actor") == TT_ACTOR]
    if not api or any(x.get("run_id") and x.get("actor") != TT_ACTOR for x in phan_moi):
        return got, {}                    # lượt thường không qua API / đã xuống dự phòng
    noi = KDP.cau_hinh_noi(moc_cu.get(KDP.KHOA_NOI_CFG) if dp_bat else None)
    tags = [t for t in tag_tiktok(tu) if t not in noi["tag"]]
    if not tags:
        return got, {}
    moc = moc_cu.get(TK_TAG) if isinstance(moc_cu.get(TK_TAG), dict) else {}
    luc = TDA._gio(moc.get("luc"))
    gio = int(ctag.get("gio") or 0)
    if luc is not None and gio > 0 and bay_gio - luc < datetime.timedelta(hours=gio):
        return got, {}
    ly = (f"lượt trước {luc.astimezone(_VN):%d/%m %H:%M}" if luc else "chưa có lượt feed hashtag")
    if v.con_giay() < _CHUA_GIAY_CUOI + 120:
        return got, {"ve": 0, "moi": 0, "usd": 0.0, "ly_do": f"{ly}; bỏ qua (hết giờ)"}
    da = len(api) * TK_TT_YEU_CAU
    tran = min(int(ctag["so_yeu_cau"]) * TK_TT_YEU_CAU, min(con, _con_viec(v)) - da)
    n = int(tran / TK_TT_YEU_CAU + 1e-9) if tran > 0 else 0
    if n < 1:
        return got, {"ve": 0, "moi": 0, "usd": 0.0, "ly_do": f"{ly}; không còn ngân sách"}
    moc_dp = (doc_moc_tk(ma).get(KDP.KHOA_MOC) or {})
    cid = dict(moc_dp.get("cid") or {}) if isinstance(moc_dp.get("cid"), dict) else {}
    trang, _ = KDP.chia_yeu_cau(n, tags, [], cid, {})
    truoc = len(_phan_tk(v))
    items: list = []
    tkm: dict = {}
    loi = ""
    try:
        items, tkm = KDP.lay_mau(trang, {}, cid, {}, TDA.TT.Ngan(n * TDA.TT.GIA_YEU_CAU), None)
    except Exception as e:            # phần thêm, không làm hỏng lượt thường
        if type(e).__name__ == "MatQuyen":
            raise
        loi = A._che_token(f"{getattr(e, 'ma', type(e).__name__)}: {e}")[:120]
    usd = round(sum(TK_TT_YEU_CAU for x in _phan_tk(v)[truoc:]
                    if x.get("run_id") and x.get("actor") == TT_ACTOR), 4)
    moi_cid = {t: x["cid"] for t, x in (tkm.get("tag") or {}).items() if x.get("cid")}
    if usd > 0:
        ghi_moc_tk(ma, {TK_TAG: {"luc": bay_gio.isoformat(timespec="seconds"), "luot": luot,
                                 "ve": len(items), "usd": usd, "tag": list(trang)}})
        if any(cid.get(t) != c for t, c in moi_cid.items()):
            # cid mới: nhớ vào mốc kiểm độ phủ (dùng chung với lượt nổi), đọc lại mốc mới nhất
            # để không đè phần lượt nổi vừa ghi trong cùng lượt.
            dp_moi = doc_moc_tk(ma).get(KDP.KHOA_MOC) or {}
            gop = {**(dp_moi.get("cid") if isinstance(dp_moi.get("cid"), dict) else {}),
                   **moi_cid}
            ghi_moc_tk(ma, {KDP.KHOA_MOC: {**dp_moi, "cid": dict(
                list(gop.items())[-KDP.BO_NHO_TOI_DA:])}})
    ve: list = []
    for it, duong in items:              # từng bài: một bài hỏng không làm mất bài đã trả tiền
        try:
            for d, dt in A._chuan_tiktok(A._chuan_clockworks([it])):
                d["_tag_feed"] = duong
                ve.append((d, dt))
        except (KeyError, TypeError, ValueError, AttributeError):
            loi = (loi + "; bỏ 1 bài hỏng shape").lstrip("; ")
    co = {d.get("link") for d, _ in got}
    them = []
    for d, dt in ve:
        if d.get("link") and d["link"] not in co:
            co.add(d["link"])
            them.append((d, dt))
    theo_tag = {t: {"trang": trang[t], "bai": int(((tkm.get("tag") or {}).get(t) or {})
                                                     .get("bai") or 0),
                    "loi": str(((tkm.get("tag") or {}).get(t) or {}).get("loi") or "")}
                for t in trang}
    if tkm.get("dung"):
        loi = (loi + f"; dừng: {tkm['dung']}").lstrip("; ")
    return got + them, {"tag": theo_tag, "chua_toi": [t for t in tags if t not in trang],
                        "yeu_cau": n, "ve": len(ve), "moi": len(them), "usd": usd,
                        "ly_do": ly, **({"loi": loi[:200]} if loi else {})}


def _tien_tim_tiktok(phan_moi: list[dict], got: list, loi, tran_du_phong) -> float:
    """Sổ tiền một lượt tìm TikTok theo GIÁ THẬT từng actor (review 16/10): TikTok API 0,002 USD
    mỗi run (= một yêu cầu); dự phòng apidojo/clockworks theo video về (nguồn ghi ở `_nguon`
    từng dòng); dự phòng lỗi không biết tiêu bao nhiêu thì tính nguyên trần của nó."""
    run = [x for x in phan_moi if x.get("run_id")]
    api = sum(1 for x in run if x.get("actor") == TT_ACTOR)
    du_phong = [x for x in run if x.get("actor") != TT_ACTOR]
    tien = api * TK_TT_YEU_CAU
    for d, _ in got:
        nguon = str(d.get("_nguon") or "")
        if nguon.startswith("clockworks"):
            tien += A._GIA_TT_DU_PHONG["clockworks"]
        elif nguon.startswith("apidojo"):
            tien += A._GIA_TT_DU_PHONG["apidojo"]
    if du_phong and loi is not None and tran_du_phong:
        tien = max(tien, api * TK_TT_YEU_CAU + float(tran_du_phong))
    return round(tien, 4)


TT_ACTOR = "scraptik~tiktok-api"     # = tiktok_api.ACTOR (bài thử đối chiếu)


# ───────────────────────────── kiểm độ phủ (17/10/2026, 2 lần/tuần) ─────────────────────────────
DP_GIAY = 300                # giây tối thiểu còn lại (≤ 100 yêu cầu / 3 luồng × ~5 giây + AI + kho)


def uoc_do_phu(du_an: dict, bay_gio: datetime.datetime | None = None) -> float:
    """USD giữ chỗ cho kiểm độ phủ trong ngân sách việc: trần mỗi lần khi lượt này TỚI HẠN kiểm
    (bật, đủ 84 giờ từ lần trước), 0 khi chưa tới."""
    cfg = KDP.cau_hinh(du_an)
    if not cfg["bat"]:
        return 0.0
    moc = doc_moc_tk(du_an["ma"]).get(KDP.KHOA_MOC)
    return cfg["tran_usd"] if KDP.den_han(moc, bay_gio or datetime.datetime.now(_VN))[0] else 0.0


def _phan_dp(v) -> list[dict]:
    with v._khoa:
        return v.d.setdefault("nen_tang", {}).setdefault("do_phu", {"phan": []})["phan"]


def _them_phan_dp(v, ph: dict) -> dict:
    with v._khoa:
        _phan_dp(v).append(ph)
        v.luu()
    return ph


def _kiem_do_phu(v, du_an: dict, luot: int, con: float, han: float) -> dict:
    """Kiểm độ phủ (`kiem_do_phu`) trong lượt /theodoi, như lượt nổi: bên gọi bắt lỗi riêng, tự
    kiểm giờ + tiền. -> {} khi chưa tới hạn / đã tắt; {"bo_qua": lý do} khi tới hạn mà không
    kiểm được; còn lại {"usd", "so_yeu_cau", "so", "mau", "bo_sung", "cu", "hanh_dong",
    "ghi_chu"}. Run id vào phần nhóm "do_phu" của sổ việc (tiền thật chốt theo run id).

    Hai pha (review 17/10, M4): (1) lấy mẫu — xong là tiền (`usd`) + mẫu thô vào sổ việc NGAY
    (`v.d["kiem_do_phu"]`, `rows-do_phu.jsonl`), lỗi về sau vẫn trừ đúng tiền và bot khởi động
    lại thì xử lý tiếp từ đĩa, không trả tiền lại; (2) đo + lấp lỗ + tự sửa (`_xu_ly_mau`)."""
    cfg = KDP.cau_hinh(du_an)
    ma = du_an["ma"]
    if not cfg["bat"]:
        # Review M3: tắt kiểm độ phủ thì lượt nổi về mặc định (không giữ nấc đã nới mãi).
        if doc_moc_tk(ma).get(KDP.KHOA_NOI_CFG):
            ghi_moc_tk(ma, {KDP.KHOA_NOI_CFG: {}})
        return {}
    phan = _phan_dp(v)
    if any(ph.get("loai") == "moc" for ph in phan):
        cu = dict(v.d.get("kiem_do_phu") or {})
        if cu.get("cho_xu_ly"):                             # khởi động lại sau khi đã lấy mẫu
            items = [(x, str(x.pop("_duong", ""))) for x, _ in v.doc_dong("do_phu")]
            return _xu_ly_mau(v, du_an, luot, han, cu, items)
        return cu                                           # đã kiểm xong trong việc này
    if any(ph.get("run_id") for ph in phan):
        usd = round(sum(KDP.GIA_YEU_CAU_THAT for ph in phan if ph.get("run_id")), 4)
        _them_phan_dp(v, {"id": "dp", "loai": "moc", "nen_tang": "do_phu", "trang_thai": "loi",
                          "ma": "KHONG_KIEM_DUOC", "usd_so": usd})
        return {"usd": usd, "ghi_chu": ["kiểm độ phủ: bot khởi động lại giữa lúc lấy mẫu — "
                                        f"không gửi lại ({usd:.3f} USD đã tính), kiểm lại sau "
                                        f"{KDP.GIO_GIAN} giờ"]}
    bay_gio = datetime.datetime.now(_VN)
    moc_cu = doc_moc_tk(ma).get(KDP.KHOA_MOC) or {}
    den, ly = KDP.den_han(moc_cu, bay_gio)
    if not den:
        return {}
    if not TDA.TT.dung_api("tiktok_tim") or not _nen_tang_dung_duoc("tiktok")[0]:
        return {"bo_qua": "TikTok API / công tắc TikTok trên console đang tắt"}
    if v.con_giay() < _CHUA_GIAY_CUOI + DP_GIAY:
        return {"bo_qua": "hết giờ — lượt sau kiểm"}
    tran = min(cfg["tran_usd"], con, _con_viec(v))
    # Số yêu cầu chia theo giá THẬT một yêu cầu (`KDP.GIA_YEU_CAU_THAT` = 0,002, đo từng run
    # 18/10/2026) để tiền thật không vượt trần (review LOW).
    n = int(tran / KDP.GIA_YEU_CAU_THAT + 1e-9)
    if n < KDP.YEU_CAU_TOI_THIEU:
        return {"bo_qua": f"ngân sách còn {_usd(max(0.0, tran))} USD — cần ≥ "
                          f"{KDP.YEU_CAU_TOI_THIEU * KDP.GIA_YEU_CAU_THAT:.3f} USD"}
    tu = tu_tim(du_an)
    d_mau = bay_gio - datetime.timedelta(days=KDP.NGAY_MAU)
    noi_bat = K.tac_gia_noi_bat(ma, "tiktok", d_mau, 500)
    dang_theo = {_chuan_dinh_danh("tiktok", str(x.get("dinh_danh") or ""))
                 for x in K.nguon_dang_theo_doi(ma) if x.get("nen_tang") == "tiktok"}
    tag = KDP.chon_tag(tu, K.hashtag_gan_day(ma, "tiktok", d_mau))
    tac_gia = KDP.chon_tac_gia(noi_bat, K.de_xuat_dang_xet(ma, "tiktok"), dang_theo)
    cid = dict(moc_cu["cid"]) if isinstance(moc_cu.get("cid"), dict) else {}
    uid = dict(moc_cu["uid"]) if isinstance(moc_cu.get("uid"), dict) else {}
    trang_tag, trang_tg = KDP.chia_yeu_cau(n, tag, tac_gia, cid, uid)
    if not trang_tag and not trang_tg:
        return {"bo_qua": "chưa có hashtag / nhà sáng tạo nào để lấy mẫu"}
    # Mốc nhịp ghi TRƯỚC yêu cầu đầu: khởi động lại giữa chừng không trả tiền lần hai.
    ghi_moc_tk(ma, {KDP.KHOA_MOC: {**moc_cu, "luc": bay_gio.isoformat(timespec="seconds"),
                                   "luot": luot, "dang_kiem": True}})
    so: list = []
    dat = [(A._NEN_TANG, "tiktok"), (A._HAN_CHOT, han), (A._SO_RUN, so),
           (A._KHI_CO_RUN, lambda run, meta: _them_phan_dp(v, {
               "id": f"dp-{run.get('id')}", "nen_tang": "do_phu", "run_id": run.get("id"),
               "actor": (meta or {}).get("actor") or TT_ACTOR, "trang_thai": "xong"}))]
    bien_cu = [(bien, bien.set(gt)) for bien, gt in dat]
    items: list = []
    tkm: dict = {}
    try:
        items, tkm = KDP.lay_mau(trang_tag, trang_tg, cid, uid,
                                 TDA.TT.Ngan(n * TDA.TT.GIA_YEU_CAU), d_mau)
    finally:
        for bien, t in reversed(bien_cu):
            bien.reset(t)
        so_yc = sum(1 for m in so if isinstance(m, dict) and m.get("run_id"))
        usd = round(so_yc * KDP.GIA_YEU_CAU_THAT, 4)
        # Tiền + mẫu thô vào sổ việc TRƯỚC mọi bước sau (review M4).
        if items:
            v.ghi_dong("do_phu", [({**it, "_duong": duong}, None) for it, duong in items], "dp")
        ctx = {"usd": usd, "so_yeu_cau": so_yc, "cho_xu_ly": True,
               "luc": bay_gio.isoformat(timespec="seconds"), "tran_usd": cfg["tran_usd"],
               "trang_tag": trang_tag, "trang_tg": trang_tg, "tkm": tkm, "moc_cu": moc_cu}
        with v._khoa:
            v.d["kiem_do_phu"] = ctx
            v.luu()
        _them_phan_dp(v, {"id": "dp", "loai": "moc", "nen_tang": "do_phu", "trang_thai": "xong",
                          "usd_so": usd, "so_item": len(items)})
        if not so_yc:
            ghi_moc_tk(ma, {KDP.KHOA_MOC: moc_cu})      # chưa tiêu đồng nào: trả mốc cũ
    return _xu_ly_mau(v, du_an, luot, han, ctx, items)


def _xu_ly_mau(v, du_an: dict, luot: int, han: float, ctx: dict,
               items: list[tuple[dict, str]]) -> dict:
    """Pha 2 của kiểm độ phủ: đánh dấu mẫu, lấp lỗ (phễu + AI), đo LẠI sau AI, tự sửa đường thu
    thập, ghi bảng + mốc. Bài AI loại trong lúc lấp không phải "sót" (review M2): độ phủ và hành
    động chỉ tính bài sót mà phễu GIỮ (hoặc chưa xét được khi lấp lỗi — ghi rõ "trước AI")."""
    ma = du_an["ma"]
    usd, so_yc = float(ctx.get("usd") or 0), int(ctx.get("so_yeu_cau") or 0)
    tkm = ctx.get("tkm") or {}
    trang_tag, trang_tg = ctx.get("trang_tag") or {}, ctx.get("trang_tg") or {}
    moc_cu = ctx.get("moc_cu") or {}
    try:
        bay_gio = datetime.datetime.fromisoformat(str(ctx.get("luc")))
    except ValueError:
        bay_gio = datetime.datetime.now(_VN)
    ghi_chu: list[str] = []
    if tkm.get("dung"):
        ghi_chu.append(f"kiểm độ phủ: dừng giữa chừng ({tkm['dung']}: {A.nhan_ma(tkm['dung'])})")
    cid = dict(moc_cu["cid"]) if isinstance(moc_cu.get("cid"), dict) else {}
    uid = dict(moc_cu["uid"]) if isinstance(moc_cu.get("uid"), dict) else {}
    for t, x in (tkm.get("tag") or {}).items():
        if x.get("cid"):
            cid[t] = x["cid"]
    for u, x in (tkm.get("tac_gia") or {}).items():
        if x.get("uid"):
            uid[u] = x["uid"]
    tu = tu_tim(du_an)
    tu_pv = TDA.pham_vi(ma, bay_gio)[0]
    d_mau = bay_gio - datetime.timedelta(days=KDP.NGAY_MAU)
    noi_bat = K.tac_gia_noi_bat(ma, "tiktok", d_mau, 500)
    dang_theo = {_chuan_dinh_danh("tiktok", str(x.get("dinh_danh") or ""))
                 for x in K.nguon_dang_theo_doi(ma) if x.get("nen_tang") == "tiktok"}

    def khoa_cua(d: dict) -> str:
        goc = d.get("__goc") if isinstance(d.get("__goc"), dict) else {}
        return _khoa_bai("tiktok", d["link"], {"id": goc.get("id") or d.get("_goc_id")})
    mau = KDP.danh_dau(ma, items, du_an, tu, tu_pv, bay_gio, khoa_cua)
    # Lấp lỗ: bài brand của mẫu đi cùng phễu tìm theo từ khoá (đã có → cập nhật số; mới → AI).
    tk_dp = {"pheu": {}, "moi": 0, "cu": 0, "giu": 0, "de_xuat": 0, "cap_nhat": 0,
             "pham_vi": {"tu": tu_pv.isoformat(timespec="minutes")}}
    hits = [(x["d"], x["dt"]) for x in mau if x["nhac"] and not x["da_loai"]]
    sau_ai = True
    giu: set[str] = set()
    if hits:
        try:
            _tach_va_giu(du_an, luot, hits, tu, han, tk_dp)
            cho = [x["khoa"] for x in mau if x["nhac"] and not x["da_co"] and not x["da_loai"]]
            giu = K.khoa_da_co(ma, cho) if cho else set()
            loai = TDA.doc_loai(ma, TDA.dau_loai(du_an, tu), tu_pv)
            for x in mau:
                if x["khoa"] in cho and x["khoa"] not in giu and x["khoa"] in loai:
                    x["da_loai"] = True          # phễu/AI loại ngay lúc lấp: không phải sót
        except Exception as e:
            if type(e).__name__ == "MatQuyen":
                raise
            sau_ai = False
            ghi_chu.append("kiểm độ phủ: lấp bài sót lỗi (độ phủ tính trước AI) "
                           + A._che_token(f"{type(e).__name__}: {e}")[:120])
    so_do = KDP.tinh_do_phu(mau)
    theo_duong = {ten: KDP.tinh_do_phu([x for x in mau
                                        if any(str(d).startswith(dau) for d in x["duong"])])
                  for ten, dau in (("hashtag", "#"), ("tac_gia", "@"))}
    # MỌI bài sót (hành động tự sửa xét hết; bảng chỉ lưu `SOT_TOI_DA` bài nhiều thảo luận nhất).
    sot = KDP.bai_sot(mau, tu, {str(x.get("tai_khoan") or "") for x in noi_bat}, bay_gio,
                      toi_da=None)
    for s in sot:
        s["bo_sung"] = s["khoa"] in giu
        s["hanh_dong"].append("đã ghi vào kho" if s["bo_sung"]
                              else "đã qua lọc + AI — chưa giữ" if sau_ai
                              else "chưa qua AI (lấp lỗi)")
    # Tự sửa đường thu thập theo lý do sót (chủ dự án 17/10: "không chỉ đo").
    # Review 17/10 (lượt 10 ra 80 đề xuất): không đề xuất lại người bị từ chối gần đây; đề xuất
    # đang chờ không tính vào trần đề xuất mới. Đọc kho lỗi → coi như rỗng (trần 10 vẫn chặn).
    try:
        tu_choi = K.de_xuat_tu_choi_gan(ma, "tiktok", KDP.DE_XUAT_NGAY_TU_CHOI)
        cho = {str(x.get("dinh_danh") or "").lower() for x in K.de_xuat_dang_xet(ma, "tiktok")}
    except Exception as e:  # noqa: BLE001 — kho lỗi không chặn kiểm độ phủ
        if type(e).__name__ == "MatQuyen":
            raise
        tu_choi, cho = set(), set()
    hd = KDP.hanh_dong(sot, tu, dang_theo, doc_moc_tk(ma).get(KDP.KHOA_NOI_CFG),
                       so_do["do_phu_tl"], bay_gio, tl_truoc=moc_cu.get("do_phu_tl"),
                       tu_choi=tu_choi, dang_cho=cho)
    if hd["de_xuat"]:
        try:
            K.ghi_de_xuat(ma, hd["de_xuat"])
        except K.LoiKho as e:
            ghi_chu.append(f"kiểm độ phủ: không ghi được đề xuất nguồn ({e})"[:200])
    if so_yc:
        ghi_moc_tk(ma, {KDP.KHOA_NOI_CFG: hd["noi_cfg"]})
    mau_tt = {"tag": [{"ten": f"#{t}", "trang": trang_tag[t],
                       **{k: x for k, x in ((tkm.get("tag") or {}).get(t) or {}).items()
                          if k != "cid"}} for t in trang_tag],
              "tac_gia": [{"ten": f"@{u}", "trang": trang_tg[u],
                           **{k: x for k, x in ((tkm.get("tac_gia") or {}).get(u) or {}).items()
                              if k != "uid"}} for u in trang_tg],
              "theo_duong": theo_duong, "ngay": KDP.NGAY_MAU, "tran_usd": ctx.get("tran_usd"),
              "sau_ai": sau_ai}
    dp = {"usd": usd, "so_yeu_cau": so_yc, "so": so_do, "mau": mau_tt,
          "bo_sung": int(tk_dp["moi"]), "cu": int(tk_dp["cu"]) + int(tk_dp["cap_nhat"]),
          "hanh_dong": hd["tom"], "ghi_chu": ghi_chu}
    try:
        K.ghi_kiem_do_phu({"du_an": ma, "luot_id": luot, "nen_tang": "tiktok", **so_do,
                           "bo_sung": dp["bo_sung"], "so_yeu_cau": so_yc, "chi_phi_usd": usd,
                           "mau": mau_tt, "bai_sot": sot[:KDP.SOT_TOI_DA],
                           "hanh_dong": hd["tom"]})
    except K.LoiKho as e:
        ghi_chu.append(f"kiểm độ phủ: không ghi được bảng kiem_do_phu ({e})"[:200])
    if so_yc:
        gon = {k: dict(list(x.items())[-KDP.BO_NHO_TOI_DA:]) for k, x in (("cid", cid),
                                                                          ("uid", uid))}
        ghi_moc_tk(ma, {KDP.KHOA_MOC: {"luc": bay_gio.isoformat(timespec="seconds"),
                                       "luot": luot, "usd": usd, "so_nhac": so_do["so_nhac"],
                                       "do_phu_tl": so_do["do_phu_tl"], **gon}})
    with v._khoa:
        v.d["kiem_do_phu"] = dict(dp)
        v.luu()
    return dp


# ───────────────────────────── Báo & Web (16/10/2026) ─────────────────────────────
def _cot_web(d: dict) -> dict:
    """Cột riêng của bài web (`bai.kieu_trang/muc_nhac/la_pr`); bài mạng xã hội: NULL."""
    w = d.get("_web") if isinstance(d.get("_web"), dict) else {}
    return {"kieu_trang": w.get("kieu_trang") or None, "muc_nhac": w.get("muc_nhac") or None,
            "la_pr": bool(w["la_pr"]) if "la_pr" in w else None}


def khau_hieu_chien_dich(ma: str, bay_gio: datetime.datetime) -> tuple[dict | None, list[str]]:
    """(lịch chiến dịch ĐANG CHẠY của dự án, khẩu hiệu của nó). Khẩu hiệu ghi ở
    `lich_quet.cau_hinh.tu_khoa_them` của lịch chiến dịch — gắn với đúng khung chiến dịch nên tự
    thôi khi chiến dịch hết, không phải nhớ gỡ khỏi từ khoá dự án (và không làm đắt lượt tìm
    mạng xã hội: chỉ web dùng, mỗi câu tìm 0,0005 USD/trang). Lịch hỏng: (None, [])."""
    try:
        from dashboard import lich_quet as LQ
        cd = LQ.chien_dich_dang_chay(K.lich_chien_dich(ma), bay_gio)
    except Exception as e:      # lịch hỏng không chặn lượt tìm
        if type(e).__name__ == "MatQuyen":
            raise
        print(f"[theo_doi] web: không đọc được lịch chiến dịch: {type(e).__name__}", flush=True)
        return None, []
    if not cd:
        return None, []
    ch = cd.get("cau_hinh") if isinstance(cd.get("cau_hinh"), dict) else {}
    ra: list[str] = []
    for x in ch.get("tu_khoa_them") or [] if isinstance(ch.get("tu_khoa_them"), list) else []:
        x = " ".join(str(x).split())[:80]
        if x and A._norm(x) not in {A._norm(y) for y in ra}:
            ra.append(x)
    return cd, ra[:10]


def _da_biet_web(ma: str, du_an: dict, tu_web: list[str], tu_pv: datetime.datetime):
    """Hàm cho `nguon_web.thu_thap`: khoá bài web đã có trong kho / đã bị loại (sổ riêng của web)
    -> không tải lại, không đọc dự phòng lại (đỡ tiền mỗi ngày)."""
    da_loai = TDA.doc_loai(f"{ma}:web", TDA.dau_loai(du_an, tu_web), tu_pv)

    def hoi(khoa: list[str]) -> dict[str, str]:
        ra = {k: "da_loai_truoc" for k in khoa if k in da_loai}
        try:
            ra.update({k: "da_co" for k in K.khoa_da_co(ma, khoa)})
        except Exception as e:  # kho hỏng: coi như chưa biết (tải lại, không mất bài)
            if type(e).__name__ == "MatQuyen":
                raise
            print(f"[theo_doi] web: không đọc được kho ({type(e).__name__})", flush=True)
        return ra
    return hoi


def _tim_web(v, du_an: dict, luot: int, cfg: dict, tu: list[str], con: float, han: float,
             tk: dict, bay_gio: datetime.datetime, moc: dict | None, moc_moi: dict,
             tu_pv: datetime.datetime) -> tuple[float, tuple[list, list[str], list]]:
    """Phần `tk-web` của lượt tìm. -> (USD theo sổ, (hits đã lọc luật, từ khoá web, bài
    `nguon_web` loại theo luật — ghi sổ "đã loại" của web)).

    Nhịp: ngoài chiến dịch tối đa MỘT lượt / `WEB_GIO_GIAN` giờ (chủ dự án 16/10: hằng ngày);
    trong chiến dịch mọi lượt. Cửa sổ ngày gửi Google = từ lượt web thành công trước lùi
    `WEB_NGAY_CHONG` ngày (lần đầu / đổi từ khoá: 30 ngày); bài giữ trong cả PHẠM VI theo dõi.
    Tiền: mỗi run Apify ghi phần có run id ngay khi tạo (`_KHI_CO_RUN`, chốt tiền thật theo run
    id); sổ trong lượt = trang Google về × 0,0005 + trang dự phòng (giá đo, không thấp hơn thời
    gian chạy × giá giây) — cả hai có `maxTotalChargeUsd`, phần dự phòng kẹp trong phần còn."""
    ma = du_an["ma"]
    cd, khau_hieu = khau_hieu_chien_dich(ma, bay_gio)
    tu_web = W.rut_gon_tu_khoa([*tu, *khau_hieu]) or tu
    if khau_hieu:
        tk["ghi_chu"].append(f"tìm Báo & Web: chiến dịch #{cd.get('id')} thêm khẩu hiệu "
                             f"{', '.join(khau_hieu)[:80]}")
    luc_truoc = None
    try:
        luc_truoc = datetime.datetime.fromisoformat(str((moc or {}).get("luc") or ""))
    except ValueError:
        pass
    if luc_truoc is not None and not cd and luc_truoc.tzinfo \
            and bay_gio - luc_truoc < datetime.timedelta(hours=WEB_GIO_GIAN):
        _them_phan_tk(v, {"id": "tk-web", "loai": "moc", "nen_tang": "web", "trang_thai": "xong",
                          "ma": "CHUA_TOI_LUOT", "usd_so": 0.0})
        tk["ghi_chu"].append(f"tìm Báo & Web: đã quét lúc {luc_truoc.astimezone(_VN):%d/%m %H:%M}"
                             f" — một lượt mỗi ngày ngoài chiến dịch")
        return 0.0, ([], tu_web, [])
    han_web = han - WEB_CHUA_GIAY_AI - _CHUA_GIAY_CUOI
    if han_web - time.monotonic() < 60:
        tk["ghi_chu"].append("tìm Báo & Web: bỏ qua (hết giờ)")
        _them_phan_tk(v, {"id": "tk-web", "loai": "moc", "nen_tang": "web", "trang_thai": "loi",
                          "ma": "QUA_GIO", "usd_so": 0.0})
        return 0.0, ([], tu_web, [])
    so_trang = W.so_trang_cua(cfg["so_bai"])
    dau = dau_tk(tu_web, cfg["so_bai"])
    d_from, ngay, ly_cs = cua_so_tk(moc, dau, bay_gio, chong=WEB_NGAY_CHONG)
    A._NEN_TANG.set("web")
    A._HAN_CHOT.set(han_web)
    A._KHI_CO_RUN.set(lambda run, meta: _them_phan_tk(v, {
        "id": f"tk-web-{run.get('id')}", "nen_tang": "web", "run_id": run.get("id"),
        "actor": (meta or {}).get("actor"), "trang_thai": "dang_chay"}))
    wk: dict = {}                    # `thu_thap` điền dần — lỗi bất ngờ vẫn đọc được tiền đã tiêu
    hits: list = []
    try:
        hits, wk = W.thu_thap(
            {**du_an, "tu_khoa": tu}, tu=d_from.date(), den=bay_gio.astimezone(_VN).date(),
            so_trang=so_trang, con_usd=con, han=han_web, bay_gio=bay_gio, them_tu=khau_hieu,
            tu_giu=tu_pv, da_biet=_da_biet_web(ma, du_an, tu_web, tu_pv),
            boc_toi_da=int(cfg.get("boc") or 0), da_boc=doc_da_boc(ma, bay_gio), so=wk)
    except Exception as e:
        # Review 16/10 (H1): lỗi bất ngờ của phần web KHÔNG được làm mất bài mạng xã hội đã trả
        # tiền trong cùng lượt (chưa ghi kho, chưa dời mốc). Web ghi lỗi + tiền đã tiêu tới đó.
        if type(e).__name__ == "MatQuyen":
            raise
        hits = []
        wk.setdefault("pheu", W._pheu_moi())
        wk["loi"] = A._che_token(f"lỗi bất ngờ {type(e).__name__}: {e}")[:150]
        print(f"[theo_doi] web: {wk['loi']}", flush=True)
    finally:
        A._KHI_CO_RUN.set(None)
        ghi_da_boc(ma, wk.get("da_boc_moi") or [], bay_gio)
    loi = wk.get("loi") or None
    bo_qua = str(wk.get("trang_thai") or "").startswith("bo_qua")
    for ph in _phan_tk(v):
        if ph.get("nen_tang") == "web" and ph.get("run_id") and ph.get("trang_thai") == "dang_chay":
            v.cap_nhat_phan(ph, trang_thai="xong" if loi is None else "loi")
    tien = round(float(wk.get("usd_tim") or 0) + float(wk.get("usd_boc") or 0), 4)
    _them_phan_tk(v, {"id": "tk-web", "loai": "moc", "nen_tang": "web",
                      "trang_thai": "loi" if (loi is not None or bo_qua) else "xong",
                      **({"ma": "NGAN_SACH"} if bo_qua else {}), "usd_so": tien,
                      "so_item": int((wk.get("pheu") or {}).get("serp") or 0),
                      "cua_so": {"tu": d_from.isoformat(timespec="minutes"), "ngay": ngay,
                                 "ly_do": ly_cs}})
    tk["ghi_chu"].extend(f"tìm Báo & Web: {x}" for x in wk.get("ghi_chu") or [])
    if loi is not None or bo_qua:
        # Lỗi / hết ngân sách: KHÔNG dời mốc web (L4) — lượt sau tìm lại đúng khoảng này.
        tk["ghi_chu"].append(f"tìm Báo & Web: {loi or wk.get('trang_thai')}")
        return tien, ([], tu_web, [])
    w = wk["pheu"]
    ph_p = tk["pheu"]["web"] = _pheu_moi(ngay, ly_cs)
    ph_p.update(ve=w["serp"], xin=cfg["so_bai"], xin_ly_do=f"{len(wk['truy_van'])} câu tìm",
                pham_vi=len(hits), ngoai_pham_vi=w["qua_cu"] + w["khong_ngay"],
                da_loai_truoc=w["da_loai_truoc"], loai_tru=w["loai_tru"], spam=w["spam"],
                khong_nhac=w["khong_nhac"], trung=w["trung"], cap_nhat=w["da_co"],
                web={k: w.get(k, 0) for k in ("mxh", "tmdt", "nha", "tuyen_dung", "robots_chan",
                                              "tai_loi", "boc_du_phong", "boc_duoc",
                                              "da_boc_truoc", "chi_trich", "trang_hong")})
    # Mốc dời cả khi Google trả 0 kết quả (cửa sổ 2–3 ngày không có bài là chuyện thường của báo
    # với một brand) — nếu không, lịch mỗi giờ sẽ tìm web mỗi giờ. Lỗi actor thì không dời.
    moc_moi["web"] = {"luc": bay_gio.isoformat(timespec="seconds"), "dau": dau,
                      "luot": luot, "xin": cfg["so_bai"], "ve": w["serp"]}
    return tien, (hits, tu_web, wk.get("bi_loai") or [])


# Sổ "đã đọc dự phòng" của Báo & Web (review 16/10, M1): trang đã gửi actor dự phòng (trả tiền)
# không gửi lại trong `nguon_web.BOC_NHO_NGAY` ngày — trang bị loại vì không có ngày / quá cũ /
# đọc vẫn hỏng không vào sổ "đã loại" nên không có sổ này thì bị đọc trả tiền MỖI lượt (chiến
# dịch 30 phút/lượt). File JSON cạnh sổ mốc (không đổi schema kho), ghi nguyên tử.
_KHOA_DA_BOC = threading.Lock()


def _duong_da_boc():
    return A._thu_muc_nen() / ".web-da-boc.json"


def _doc_so_da_boc() -> dict:
    try:
        d = json.loads(_duong_da_boc().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) and isinstance(d.get("du_an"), dict) else {}


def doc_da_boc(ma: str, bay_gio: datetime.datetime) -> set[str]:
    """Khoá trang web của dự án đã thử đọc dự phòng trong `BOC_NHO_NGAY` ngày."""
    moc = (bay_gio - datetime.timedelta(days=W.BOC_NHO_NGAY)).astimezone(_VN).date().isoformat()
    x = (_doc_so_da_boc().get("du_an") or {}).get(ma)
    return {k for k, v in (x or {}).items() if isinstance(v, str) and v >= moc} \
        if isinstance(x, dict) else set()


def ghi_da_boc(ma: str, khoa: list[str], bay_gio: datetime.datetime) -> None:
    """Thêm khoá vừa đọc dự phòng (ngày hôm nay), bỏ khoá quá hạn; không ghi được thì chỉ báo."""
    if not khoa:
        return
    with _KHOA_DA_BOC:
        d = _doc_so_da_boc() or {"du_an": {}}
        con_han = doc_da_boc(ma, bay_gio)
        goc = d["du_an"].get(ma) if isinstance(d["du_an"].get(ma), dict) else {}
        cu = {k: v for k, v in goc.items() if k in con_han}
        cu.update({str(k): bay_gio.astimezone(_VN).date().isoformat() for k in khoa})
        d["du_an"][ma] = cu
        f = _duong_da_boc()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, f)
        except OSError as e:
            print(f"[theo_doi] web: không ghi được sổ đã đọc dự phòng: {type(e).__name__}",
                  flush=True)


def _tach_va_giu(du_an: dict, luot: int, hits: list, tu: list[str], han: float,
                 tk: dict, ma_loai: str | None = None) -> None:
    """Bài trong phạm vi: ĐÃ CÓ trong kho → cập nhật số liệu + ảnh chụp ngày (`chi_so_ngay`);
    MỚI → `_giu_tu_khoa` (lọc + AI). Xem `theo_doi_api.tach_da_biet`. Bài Facebook mang pfbid
    mới mà là bản trùng của bài đã có (`lang_nghe_db.khoa_fb_trung`) đi đường ĐÃ CÓ với khoá cũ."""
    def khoa_hit(d: dict) -> str:
        return _khoa_bai(d["platform"], d["link"], {
            "id": (d.get("__goc") if isinstance(d.get("__goc"), dict) else {}).get("id")})
    cu = _khoa_fb_cu(du_an["ma"], hits, khoa_hit)
    cap_nhat, hits_moi, trung = TDA.tach_da_biet(
        du_an["ma"], hits, lambda d: cu.get(khoa_hit(d), khoa_hit(d)))
    for p, n in trung.items():
        tk["pheu"].setdefault(p, _pheu_moi(0, ""))["trung"] += n
    if cap_nhat:
        tk["cap_nhat"] = tk.get("cap_nhat", 0) + K.cap_nhat_so_lieu(du_an["ma"], luot, cap_nhat)
        for r in cap_nhat:
            tk["pheu"].setdefault(r["nen_tang"], _pheu_moi(0, ""))["cap_nhat"] += 1
        # Phễu đường 2 Threads: bài RIÊNG của đường 2 đã có trong kho (chỉ cập nhật số liệu).
        k2 = {_khoa_bai("threads", d["link"]) for d, _ in hits if d.get("_duong") == 2}
        _dem_duong_2(tk, "cap_nhat", sum(1 for r in cap_nhat if r["khoa"] in k2))
    tu_pv = datetime.datetime.fromisoformat((tk.get("pham_vi") or {}).get("tu")
                                            or datetime.datetime.now(_VN).isoformat())
    dau = TDA.dau_loai(du_an, tu)
    ma_loai = ma_loai or du_an["ma"]
    da_loai = TDA.doc_loai(ma_loai, dau, tu_pv)
    if da_loai:
        con = []
        for d, dt in hits_moi:
            k = _khoa_bai(d["platform"], d["link"], {
                "id": (d.get("__goc") if isinstance(d.get("__goc"), dict) else {}).get("id")})
            if k in da_loai or any(x in da_loai for x in _khoa_loai_on_dinh(d, dt)):
                tk["pheu"].setdefault(d["platform"], _pheu_moi(0, ""))["da_loai_truoc"] += 1
                if d.get("_duong") == 2:
                    _dem_duong_2(tk, "loai")
            else:
                con.append((d, dt))
        hits_moi = con
    if hits_moi:
        try:
            _giu_tu_khoa(du_an, luot, hits_moi, tu, han, tk)
        finally:
            TDA.ghi_loai(ma_loai, dau, tk.pop("_bi_loai", []), tu_pv)


def _khoa_loai_on_dinh(d: dict, dt) -> list[str]:
    """Khoá ỔN ĐỊNH của bài Facebook cho sổ "đã loại" (18/10/2026): id số (`khu_trung_fb.ma_so_fb`)
    và chủ bài + phút đăng + chữ ký nội dung. Vì sao: khoá bài theo link mang pfbid — ĐỔI mỗi lượt
    cào (đo vòng 1, 17/10) — nên bài Facebook bị loại (AI lạc đề 5–10 bài/lượt ở lượt 7–11, không
    nhắc từ khoá, từ loại trừ) không bao giờ khớp lại sổ và bị gửi AI xét lại MỖI lượt. Nền tảng
    khác khoá theo id ổn định (video, shortcode, băm link chuẩn) → []."""
    if (d.get("platform") or d.get("nen_tang")) != "facebook":
        return []
    import hashlib
    ra = []
    so = KT.ma_so_fb(d)
    if so:
        ra.append(f"facebook:id:{so}")
    r = {"tai_khoan": d.get("username") or d.get("tai_khoan"), "tac_gia": d.get("kenh"),
         "link": d.get("link"), "noi_dung": str(d.get("text") or d.get("noi_dung") or "")[:1000]}
    chu, ph = sorted(KT.chu_bai(r)), KT.phut(dt)
    if chu and ph and KT.co_chu(r):
        ky = hashlib.sha1(KT.chu_ky_noi_dung(r["noi_dung"]).encode("utf-8")).hexdigest()[:12]
        ra.append(f"facebook:nd:{chu[0]}|{ph.isoformat()}|{ky}")
    return ra


def _khoa_fb_cu(ma: str, hits: list, khoa_hit) -> dict[str, str]:
    """{khoá pfbid của lượt này: khoá bài đã có} cho bài Facebook trong `hits` (17/10/2026: mỗi lượt
    actor trả pfbid khác). Kho hỏng thì {} — `lang_nghe_db.ghi_bai` vẫn dùng lại khoá cũ lúc ghi,
    chỉ tốn thêm lượt AI cho bài đó."""
    import loc_rac
    rows = []
    for d, dt in hits:
        if d.get("platform") != "facebook" or not d.get("link"):
            continue
        nd = str(d.get("text") or "")[:1000]
        rows.append({"khoa": khoa_hit(d), "nen_tang": "facebook", "link": d["link"],
                     "tai_khoan": str(d.get("username") or "")[:200],
                     "tac_gia": str(d.get("kenh") or "")[:200], "dang_luc": dt, "noi_dung": nd,
                     "ma_noi_dung": loc_rac.ma_noi_dung(nd, loc_rac.BAI_TRUNG_TOI_THIEU_CHU),
                     **_cot_fb(d)})
    if not rows:
        return {}
    try:
        return K.khoa_fb_trung(ma, rows)
    except K.LoiKho as e:
        print(f"[theo_doi] không tra được bài Facebook trùng: {e}", flush=True)
        return {}


def _giu_tu_khoa(du_an: dict, luot: int, hits: list, tu: list[str], han: float,
                 tk: dict) -> None:
    """Phân xử AI (như social_listen): AI giữ thì giữ; AI không phán được thì giữ khi bài
    THỰC SỰ nhắc từ khoá. Trùng, từ loại trừ, spam bỏ cứng trước AI. Mỗi bước đếm vào phễu
    của nền tảng (`tk["pheu"]`)."""
    import loc_rac
    ma = du_an["ma"]
    loai_tru = [str(x) for x in du_an.get("tu_loai_tru") or [] if str(x).strip()]
    pheu = tk.setdefault("pheu", {})

    def ph(d: dict) -> dict:
        return pheu.setdefault(d["platform"], _pheu_moi(0, ""))
    # Bài bị loại lượt này → sổ "đã loại" (`theo_doi_api.ghi_loai`, review 16/10): trong phạm vi
    # 30–92 ngày cùng bài về mỗi lượt, không gửi AI xét lại (tốn + kết quả có thể đổi).
    bi_loai = tk.setdefault("_bi_loai", [])

    def loai(d: dict, khoa: str, ly: str, dt) -> None:
        # Facebook (18/10/2026): kèm khoá ổn định — pfbid trong khoá đổi mỗi lượt.
        bi_loai.extend((k, ly, dt) for k in (khoa, *_khoa_loai_on_dinh(d, dt)))
    # Phễu đường 2 Threads: bài riêng của đường 2 vào bước này → giữ / loại (gộp mọi lý do loại;
    # lý do chi tiết nằm ở phễu Threads chung).
    n2_vao = sum(1 for d, _ in hits if d.get("_duong") == 2)
    cho, thay = [], set()
    for d, dt in hits:
        goc = d.get("__goc") if isinstance(d.get("__goc"), dict) else {}
        khoa = _khoa_bai(d["platform"], d["link"], {"id": goc.get("id")})
        if khoa in thay:
            ph(d)["trung"] += 1
            continue
        thay.add(khoa)
        if A._tu_loai_tru_khop(d, loai_tru):
            ph(d)["loai_tru"] += 1
            loai(d, khoa, "loai_tru", dt)
            continue
        if loc_rac.bai_spam(f"{d.get('text') or ''} {d.get('hashtags') or ''}"):
            tk["spam"] = tk.get("spam", 0) + 1            # đợt 2d: bỏ cứng trước bước AI
            ph(d)["spam"] += 1
            loai(d, khoa, "spam", dt)
            continue
        d["_khoa"] = khoa
        d["_khop"] = A._khop_tu_khoa(d, tu)
        d["_thi_truong"] = A._thi_truong(d, tu)
        cho.append((d, dt))
    if not cho:
        _dem_duong_2(tk, "loai", n2_vao)
        return
    han_ai = time.monotonic() + max(0.0, min(150.0, han - time.monotonic() - 30))
    px_all, tt = A._phan_xu_ai(cho, tu, du_an.get("boi_canh") or du_an["ten"],
                               du_an.get("thi_truong") or "VN", han_ai)
    tk["ai"] = tt.get("trang_thai") or ""
    nguon = K.nguon_cua_du_an(ma)
    theo = {(n["nen_tang"], _chuan_dinh_danh(n["nen_tang"], n["dinh_danh"])): int(n["id"])
            for n in nguon}
    rows, ban = [], []
    for i, (d, dt) in enumerate(cho):
        px = px_all.get(i)
        if px and px[1] == "khong_ro":
            px = None
        if px and not px[0]:
            lo = ph(d)["ai_loai"]
            lo[str(px[1])] = lo.get(str(px[1]), 0) + 1
            loai(d, d["_khoa"], f"ai:{px[1]}", dt)
            continue
        if not px and not d["_khop"]:
            ph(d)["khong_nhac"] += 1
            if i in px_all:              # AI đã xét (không rõ) — chưa xét thì lượt sau xét lại
                loai(d, d["_khoa"], "khong_nhac", dt)
            continue
        dd = _dinh_danh_tai_khoan(d)
        rows.append({
            "khoa": d["_khoa"], "nen_tang": d["platform"],
            "nguon_id": theo.get((dd[0], dd[1])) if dd else None, "link": d["link"],
            "tac_gia": str(d.get("kenh") or "")[:200],
            "tai_khoan": str(d.get("username") or "")[:200],
            "followers": _so_hay_none(d.get("followers")), "dang_luc": dt,
            "noi_dung": str(d.get("text") or "")[:1000],
            "hashtag": str(d.get("hashtags") or "")[:500], "khop_tu_khoa": bool(d["_khop"]),
            **dict(zip(("sac_thai", "chu_de"), _nhan_bai_ngay(
                d, tt["_sac_thai"].get(i), tt["_chu_de"].get(i)))),
            "ly_do_giu": str(px[1] if px else "khop_tu_khoa")[:60],
            "xem": _so_hay_none(d.get("views")), "thich": _so_hay_none(d.get("likes")),
            "binh_luan": _so_hay_none(d.get("comments")),
            "chia_se": _so_hay_none(d.get("shares")),
            **_cot_web(d), **_cot_fb(d),
        })
        ban.append((d, dt))
    tk["giu"] = len(rows)
    n2_giu = sum(1 for d, _ in ban if d.get("_duong") == 2)
    _dem_duong_2(tk, "giu", n2_giu)
    _dem_duong_2(tk, "moi", n2_giu)          # bài vào bước này là bài CHƯA có trong kho
    _dem_duong_2(tk, "loai", n2_vao - n2_giu)
    if rows:
        # Ghi theo từng nền tảng để phễu biết bài MỚI của nền tảng nào (upsert theo khoá bài).
        theo_p: dict[str, list[dict]] = {}
        for r in rows:
            theo_p.setdefault(r["nen_tang"], []).append(r)
        for p, cac in theo_p.items():
            moi, cu = K.ghi_bai(ma, luot, "tu_khoa", cac)
            pheu.setdefault(p, _pheu_moi(0, ""))
            pheu[p]["giu"], pheu[p]["moi"] = len(cac), moi
            tk["moi"] += moi
            tk["cu"] += cu
        tk["de_xuat"] = K.ghi_de_xuat(ma, _de_xuat_tu(ban, set(theo), tu))


def _cau_pheu(p: str, f: dict) -> str:
    """Một dòng gọn cho `luot_quet.ghi_chu` + tin nhắn kết quả."""
    ai = f.get("ai_loai") or {}
    ly = ", ".join(f"{A._MA_AI.get(k, k)} {n}"
                   for k, n in sorted(ai.items(), key=lambda kv: (-kv[1], kv[0])))
    return (f"phễu tìm {_TEN.get(p, p)} (xin {f.get('ngay', 0)} ngày, {f.get('ly_do') or '?'}"
            + (f"; {f['xin_ly_do']}" if f.get("xin_ly_do") else "") + "): "
            f"về {f.get('ve', 0)} → trong phạm vi {f.get('pham_vi', 0)} (ngoài phạm vi "
            f"{f.get('ngoai_pham_vi', 0)}) → cập nhật {f.get('cap_nhat', 0)} bài đã có; bài mới: "
            + (f"đã loại trước {f['da_loai_truoc']}, " if f.get("da_loai_truoc") else "")
            + f"trùng {f.get('trung', 0)}, từ loại trừ {f.get('loai_tru', 0)}, "
            f"spam {f.get('spam', 0)}, "
            f"AI loại {sum(ai.values())}" + (f" ({ly})" if ly else "")
            + (f", không nhắc từ khoá {f['khong_nhac']}" if f.get("khong_nhac") else "")
            + f" → giữ {f.get('giu', 0)} ({f.get('moi', 0)} mới)"
            + (f"; từ khoá lỗi: {f['loi_mot_phan']}" if f.get("loi_mot_phan") else "")
            + _cau_duong(f.get("duong"))
            + _cau_moi(f.get("moi_nhat"))
            + _cau_noi(f.get("noi"))
            + _cau_tag(f.get("tag_feed"))
            + _cau_web(f.get("web")))


def _cau_duong(d) -> str:
    """Phần "từng đường" của phễu Facebook (17/10/2026): mỗi đường về bao nhiêu, đường nào hỏng /
    bỏ qua vì sao — "về" ở đầu phễu là tổng hai đường TRƯỚC khi bỏ trùng."""
    if not isinstance(d, dict) or not d:
        return ""

    def mot(ten: str, x) -> str:
        if not isinstance(x, dict):
            return ""
        if x.get("tat"):
            return f"{ten} tắt"
        if x.get("bo_qua"):
            return f"{ten} bỏ qua ({x['bo_qua']})"
        if x.get("loi") and not x.get("ve"):
            return f"{ten} lỗi ({x['loi']})"
        s = f"{ten} về {x.get('ve', 0)}"
        if x.get("cum"):
            s += (f" ({x['cum']} cụm × {x.get('moi_cum', 0)} bài, xin {x.get('ngay', '?')} ngày, "
                  f"{_usd(x.get('usd') or 0)} USD")
            if x.get("day"):
                s += f"; đầy {len(x['day'])} cụm: " + ", ".join(f"'{c}'" for c in x["day"])[:120]
            s += ")"
        if x.get("loi_mot_phan"):
            s += f" — cụm lỗi: {x['loi_mot_phan']}"
        if x.get("loi"):
            s += f" — lỗi: {x['loi']}"
        return s
    ra = [mot("scrapeforge", d.get("scrapeforge")), mot("mina", d.get("mina"))]
    ra = [x for x in ra if x]
    return ("; theo đường: " + "; ".join(ra)) if ra else ""


def _cau_moi(n) -> str:
    """Phần trang "mới nhất" TikTok (sắp theo giờ đăng, lật tới mốc lượt trước) trong phễu."""
    if not isinstance(n, dict):
        return ""
    return (f"; mới nhất ({n.get('ly_do') or '?'}; {n.get('tu', 0)} từ, {n.get('trang', 0)} "
            f"trang" + (f", {n['nghi']} từ yên nghỉ" if n.get("nghi") else "")
            + f"): về {n.get('ve', 0)}, thêm {n.get('moi', 0)} bài chưa có trong lượt thường, "
            f"{_usd(n.get('usd') or 0)} USD")


def _cau_noi(n) -> str:
    """Phần lượt "nổi" TikTok (sắp nhiều thích, 30 ngày) trong phễu."""
    if not isinstance(n, dict):
        return ""
    return (f"; lượt nổi (nhiều thích 30 ngày, {n.get('ly_do') or '?'}): về {n.get('ve', 0)}, "
            f"thêm {n.get('moi', 0)} bài chưa có trong lượt thường, {_usd(n.get('usd') or 0)} USD")


def _cau_tag(n) -> str:
    """Phần feed hashtag TikTok (17/10/2026, từ khoá một chữ) trong phễu."""
    if not isinstance(n, dict):
        return ""
    tag = n.get("tag") or {}
    s = (f"; feed hashtag ({n.get('ly_do') or '?'}; "
         + (", ".join(f"#{t} {x.get('trang', 0)} trang" + (f" lỗi {x['loi']}" if x.get("loi")
                                                            else "")
                      for t, x in tag.items()) or "—")
         + f"; {n.get('yeu_cau', 0)} yêu cầu): về {n.get('ve', 0)}, thêm {n.get('moi', 0)} bài "
         f"chưa có trong lượt thường, {_usd(n.get('usd') or 0)} USD")
    if n.get("chua_toi"):
        s += "; chưa tới #" + ", #".join(n["chua_toi"])[:120] + " (tăng số yêu cầu)"
    if n.get("loi"):
        s += f"; {n['loi']}"
    return s


def _cau_web(w) -> str:
    """Phần riêng của phễu Báo & Web: trang bỏ qua / bị chặn / đọc dự phòng."""
    if not isinstance(w, dict):
        return ""
    return (f"; trang: bỏ MXH {w.get('mxh', 0)}, sàn {w.get('tmdt', 0)}, miền nhà "
            f"{w.get('nha', 0)}"
            + (f", tuyển dụng/hồ sơ {w['tuyen_dung']}" if w.get("tuyen_dung") else "")
            + f", robots cấm {w.get('robots_chan', 0)}, bị chặn "
            f"{w.get('tai_loi', 0)}, đọc dự phòng {w.get('boc_duoc', 0)}/"
            f"{w.get('boc_du_phong', 0)} (đã thử trước {w.get('da_boc_truoc', 0)}), chỉ đoạn "
            f"trích {w.get('chi_trich', 0)}, trang hỏng {w.get('trang_hong', 0)}")


def _cau_tk(tk: dict) -> list[str]:
    if not tk or not tk.get("tu"):
        return list((tk or {}).get("ghi_chu") or [])
    lm = tk.get("lam_moi") or {}
    cau = (f"tìm theo {len(tk['tu'])} từ khoá: lấy {tk.get('lay', 0)} bài trong phạm vi "
           f"{(tk.get('pham_vi') or {}).get('ngay', '?')} ngày, cập nhật số liệu "
           f"{tk.get('cap_nhat', 0)} bài đã có, giữ {tk.get('giu', 0)} ({tk.get('moi', 0)} mới), "
           + (f"làm mới thêm {lm.get('cap_nhat', 0)}/{lm.get('bai', 0)} bài TikTok nổi, "
              if lm.get("bai") else "")
           + f"{tk.get('de_xuat', 0)} đề xuất nguồn, "
           + (f"bỏ {tk['spam']} bài spam, " if tk.get('spam') else "") + f""
           f"{_usd(tk.get('usd') or 0)} USD")
    pheu = tk.get("pheu") or {}
    # Ghi chú (bỏ qua / lỗi / co ngân sách) đứng TRƯỚC các dòng phễu dài: `luot_quet.ghi_chu` có
    # trần (`lang_nghe_db.GHI_CHU_TOI_DA`), phần mất (nếu có) phải là chi tiết phễu, không phải lý
    # do. Phễu bỏ qua / lỗi đã có câu "tìm <nền tảng>: …" trong ghi chú — không lặp dòng phễu rỗng.
    f2 = pheu.get(TH2_KHOA)
    th2 = ([_cau_duong_2(f2)] if isinstance(f2, dict) and not f2.get("bo_qua")
           and not f2.get("loi") else [])
    return [cau, *(tk.get("ghi_chu") or []),
            *(x for p in TK_NEN_TANG for x in (
                ([_cau_pheu(p, pheu[p])] if p in pheu and not pheu[p].get("bo_qua")
                 and not pheu[p].get("loi") else []) + (th2 if p == "threads" else [])))]


def _cau_duong_2(f: dict) -> str:
    """Dòng phễu RIÊNG của đường 2 Threads (scrapersdelight), ngay sau dòng phễu Threads chung:
    về → trong phạm vi → trùng đường 1 (bỏ, giữ bản futurizerush) → bài riêng: cập nhật bài đã có /
    giữ mới / loại. Cảnh báo "về 0 bài N lượt liền" nằm ở ghi chú (đứng trước, không bị cắt)."""
    rieng = f.get("pham_vi", 0) - f.get("trung_duong_1", 0)
    usd = _usd3(f.get("usd") or 0)
    return (f"phễu tìm Threads đường 2 (scrapersdelight, xin {f.get('ngay', 0)} ngày, "
            f"{f.get('ly_do') or '?'}; {f.get('xin_ly_do') or '?'}): về {f.get('ve', 0)} → trong "
            f"phạm vi {f.get('pham_vi', 0)} (ngoài phạm vi {f.get('ngoai_pham_vi', 0)}) → trùng "
            f"đường 1 {f.get('trung_duong_1', 0)} → riêng {rieng}: cập nhật "
            f"{f.get('cap_nhat', 0)} bài đã có, giữ {f.get('giu', 0)} mới, loại "
            f"{f.get('loai', 0)}; {usd} USD"
            + (f"; {f.get('rong_lien')} lượt liền về 0 bài" if f.get("rong_lien") else ""))


# ───────────────────────────── bình luận (đợt 2b, 15/10/2026) ─────────────────────────────
# Chủ dự án 15/10: dashboard phải bóc được TỪNG bình luận như Kompa. Sau khi ghi bài, lượt cào
# bình luận của tối đa `bl_so_bai` bài (chưa cào trước, rồi nhiều bình luận nhất) × `bl_moi_bai`
# bình luận mỗi bài. Dùng lại actor + bộ đọc của `deep_dive_tool` (đã đo thật) và bộ gán nhãn
# bình luận `phan_loai`. YouTube qua Data API miễn phí. Tiền đi chung lượt (run id trong phần
# "binh_luan" của việc → `chot_chi_phi`), nên tính vào trần tháng của dự án.
# Threads (16/10/2026): actor trả lời của `deep_dive_tool` (futurizerush~threads-replies-scraper,
# 1 GB): chỉ trả lời CẤP 1 công khai (không đăng nhập), ≤ 20 bài/lượt, 10–300 trả lời/bài; actor
# tính tiền cả dòng bài gốc (0,0025/bài) — cộng vào ước tính của phần.
BL_NEN_TANG = ("youtube", "tiktok", "instagram", "facebook", "threads")
# TikTok từ 16/10/2026 qua TikTok API (`tiktok_api.binh_luan`): 50 bình luận gốc / yêu cầu
# 0,002 USD (giá bảng = giá thật từng run, đo lại 18/10/2026), trả lời 1 yêu cầu mỗi luồng —
# đo 2 video HAPAS: 0,0002–0,0004 USD/bình luận (gồm trả lời) → lấy mức cao 0,0004. Mức cũ
# 0,00075 (giả định 0,003/yêu cầu + dư) làm video 5.181 bình luận "cần" 5,8 USD và cả lô bị bỏ
# vì trần (clockworks cũ 0,00125, nay chỉ còn là dự phòng).
_BL_GIA = {"tiktok": 0.0004, "facebook": 0.0025, "instagram": 0.0026, "youtube": 0.0,
           "threads": 0.0025}
_BL_KHOI_DONG = {"facebook": 0.001, "threads": 0.02}
_BL_LO = 25                       # bài mỗi lượt actor bình luận (Threads: ≤ 20, `_lo_bl`)
# Đợt 2d (chủ dự án 15/10): "1 bài thì phải cào hết tất cả thảo luận". bl_moi_bai = 0 → mỗi bài
# xin đủ số nền tảng báo (+15% + 10 dư cho trả lời mới) — KHÔNG trần mỗi bài (chủ dự án 15/10:
# "không có giới hạn"); bài to hơn trần mỗi lượt thì actor dừng ở trần, lượt sau cào tiếp
# (`bai.bl_lan_thieu`). Facebook lấy cả trả lời (includeNestedComments); bài đã cào đủ thì lần
# sau chỉ lấy bình luận MỚI (RECENT_ACTIVITY + onlyCommentsNewerThan, +0,002 USD/bài). TikTok
# trả lời tới 100/bình luận.
_BL_LO_DAY_DU = 10                # bài mỗi lượt actor khi cào hết (số bình luận chênh nhiều)
_BL_UOC_MOI_BAI = 60              # giữ chỗ ngân sách khi chưa biết bài nào (cào hết)
_BL_FB_LOC_NGAY = 0.002           # phụ phí mỗi bài khi Facebook lọc theo ngày


def uoc_binh_luan(so_bai: int, moi_bai: int, p: str = "facebook") -> float:
    """USD ước tính cào `moi_bai` bình luận × `so_bai` bài trên nền tảng `p` (mặc định giá
    Facebook — đắt nhất trừ Instagram, dùng để giữ chỗ ngân sách khi chưa biết bài nào).
    `moi_bai` = 0 (cào hết): giữ chỗ `_BL_UOC_MOI_BAI` bình luận mỗi bài."""
    moi_bai = moi_bai or _BL_UOC_MOI_BAI
    if not so_bai or not _BL_GIA.get(p):
        return 0.0
    return round((so_bai * moi_bai * _BL_GIA[p] + _BL_KHOI_DONG.get(p, 0.0)) * _HE_SO_UOC, 4)


def _ma_bl(r: dict) -> str:
    g = r.get("__goc") or {}
    m = (g.get("cid") or g.get("id") or g.get("commentId") or g.get("reply_id")
         if isinstance(g, dict) else None)
    if m:
        return str(m)[:120]
    s = f"{r.get('kenh')}|{r.get('text')}|{r.get('thoi_gian')}"
    return "h" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _gio_bl(s) -> datetime.datetime | None:
    """`deep_dive_tool._gio` trả "YYYY-MM-DD HH:MM" giờ VN; chữ khác (thời gian tương đối) → None."""
    try:
        return datetime.datetime.strptime(str(s or ""), "%Y-%m-%d %H:%M").replace(tzinfo=_VN)
    except ValueError:
        return None


def _dong_bl(r: dict, bai: dict, thuong_hieu: list[str]) -> dict:
    import phan_loai
    nha = phan_loai.la_binh_luan_nha(r.get("kenh"), bai, thuong_hieu, bool(r.get("cua_chu")))
    ma = _ma_bl(r)
    g = r.get("__goc") if isinstance(r.get("__goc"), dict) else {}
    sn = g.get("snippet") if isinstance(g.get("snippet"), dict) else {}
    cha = (g.get("repliesToId") or g.get("replyToCommentId") or g.get("parentCommentId")
           or sn.get("parentId"))
    link = str(g.get("commentUrl") or g.get("reply_url") or "") or None    # Threads: reply_url
    if not link and bai["nen_tang"] == "youtube" and r.get("link"):
        link = f"{r['link']}&lc={ma}"            # YouTube mở thẳng tới bình luận
    return {"khoa_bai": bai["khoa"], "ma": ma, "nen_tang": bai["nen_tang"],
            "link": str(link)[:500] if link else None, "ma_cha": str(cha)[:120] if cha else None,
            "tac_gia": str(r.get("kenh") or "")[:200], "noi_dung": str(r.get("text") or "")[:1000],
            "thich": _so_hay_none(r.get("likes")), "tra_loi": _so_hay_none(r.get("replies")),
            "la_tra_loi": _la_tra_loi(r), "cua_thuong_hieu": nha,
            "dang_luc": _gio_bl(r.get("thoi_gian")), "sac_thai": None, "chu_de": None,
            "likes": r.get("likes"), "text": r.get("text")}


def _la_tra_loi(r: dict) -> bool:
    g = r.get("__goc") if isinstance(r.get("__goc"), dict) else {}
    return bool(r.get("cha") or g.get("replyToCommentId") or g.get("parentCommentId")
                or g.get("repliesToId") or int(g.get("threadingDepth") or 0) > 0)


#: Bình luận (18/10/2026): một lô chỉ tiêu tới phần còn của việc TRỪ phần giữ cho các lô SAU (tối
#: đa `BL_GIU_CHO_SAU` phần còn) — lô bài to đi trước (`_uu_tien_bl`) không ăn hết tiền của các bài
#: sau; phần chưa cào của bài to thì lượt sau đọc tiếp (`_doc_tiep_tiktok`).
BL_GIU_CHO_SAU = 0.5


def _uu_tien_bl(b: dict) -> tuple:
    """Khoá xếp bài cào bình luận (18/10/2026, chủ dự án: ưu tiên bài nhiều bình luận nền tảng báo
    mà chưa cào — đầu vào sắc thái/chủ đề): bài CHƯA cào lần nào trước, rồi bài THIẾU nhiều bình
    luận nhất (nền tảng báo − đã có). Trước đây lô xếp theo cỡ TĂNG dần → bài to luôn đứng cuối,
    hết tiền thì bị bỏ (`bl_lay_luc` vẫn NULL), lượt sau chọn lại đúng nó rồi lại bỏ: 2 video
    5.181 và 4.752 bình luận chưa cào dòng nào, TikTok chỉ có ~30% bình luận."""
    return (b.get("bl_lay_luc") is not None,
            -(int(b.get("binh_luan") or 0) - int(b.get("bl_da_lay") or 0)))


def _doc_tiep_tiktok(b: dict) -> int:
    """Vị trí bình luận GỐC đọc tiếp của video TikTok CÀO DỞ (đã cào, còn dưới 80% số nền tảng báo
    lúc cào): số gốc đã có trong kho (`bl_goc`). 0 = đọc từ đầu (bài mới; bài đã đủ mà thêm bình
    luận — thứ tự của TikTok đổi theo tương tác nên đọc lại cho đủ)."""
    if b.get("nen_tang") != "tiktok" or b.get("bl_lay_luc") is None:
        return 0
    co = int(b.get("bl_lay_khi_co") or 0)
    if not co or int(b.get("bl_da_lay") or 0) >= K.BL_DU_TOI_THIEU * co:
        return 0
    return max(0, int(b.get("bl_goc") or 0))


def _can_bl(b: dict, moi_bai: int) -> int:
    """Số bình luận xin cho một bài. Cào hết: số nền tảng báo +15% +10 (không trần mỗi bài);
    lần sau của bài đã cào đủ (Facebook lọc theo ngày): phần tăng + 20; video TikTok cào dở đọc
    tiếp (18/10/2026): chỉ phần CÒN THIẾU +15% +10."""
    if moi_bai:
        return moi_bai
    co = int(b.get("binh_luan") or 0)
    if _tang_dan(b):
        co = max(0, co - int(b.get("bl_lay_khi_co") or 0))
    elif _doc_tiep_tiktok(b):
        co = max(0, co - int(b.get("bl_da_lay") or 0))
    return max(10, int(co * 1.15) + (20 if _tang_dan(b) else 10))


def _tang_dan(b: dict) -> bool:
    """Bài Facebook đã cào ĐỦ trước đó → lần này chỉ lấy bình luận mới theo ngày."""
    return (b.get("nen_tang") == "facebook" and b.get("bl_lay_luc") is not None
            and int(b.get("bl_da_lay") or 0) >= 0.8 * int(b.get("bl_lay_khi_co") or 0) > 0)


def _payload_bl(p: str, urls: list[str], per: int, day_du: bool, moc_moi=None) -> dict:
    import deep_dive_tool as D
    if p == "facebook" and day_du:
        x = {"startUrls": [{"url": u} for u in urls], "resultsLimit": per,
             "includeNestedComments": True, "viewOption": "RANKED_UNFILTERED"}
        if moc_moi is not None:
            x.update(viewOption="RECENT_ACTIVITY",
                     onlyCommentsNewerThan=moc_moi.strftime("%Y-%m-%d"))
        return x
    if p == "tiktok" and day_du:
        return {"postURLs": urls, "commentsPerPost": per, "maxRepliesPerComment": 100}
    return D._payload(p, urls, per)


def _phan_bl(v) -> list[dict]:
    with v._khoa:
        return v.d.setdefault("nen_tang", {}).setdefault("binh_luan", {"phan": []})["phan"]


def _tao_phan_bl(v, p: str, lo: list[dict], per: int) -> dict:
    """Một phần bình luận cho các bài `lo` cùng nền tảng (lập rồi lưu sổ ngay)."""
    _tao_cac_phan_bl(v, [dict(b, nen_tang=p) for b in lo], per)
    return _phan_bl(v)[-1]


def _tao_cac_phan_bl(v, ds: list[dict], per_cfg) -> None:
    """Lập MỌI phần bình luận rồi lưu sổ một lần — bot tắt giữa chừng thì hoặc chưa có phần
    nào (lần sau chọn lại), hoặc có đủ (không lặng lẽ bỏ nền tảng còn lại). `per_cfg`: số
    bình luận mỗi bài (0 = cào hết) — một số chung, hoặc {nền tảng: số}."""
    import deep_dive_tool as D
    cac = []
    for p in BL_NEN_TANG:
        per = int(per_cfg.get(p, 0) if isinstance(per_cfg, dict) else per_cfg or 0)
        day_du = not per
        for lo, moc in _chia_lo_bl(p, [b for b in ds if b["nen_tang"] == p], per):
            urls = [b["link"] for b in lo]
            can = [_can_bl(b, per) for b in lo]
            khoang = D._PER_KHOANG.get(p)          # Threads: actor chỉ nhận 10–300 trả lời/bài
            if khoang:
                can = [max(khoang[0], min(khoang[1], c)) for c in can]
            per_lo = max(can)
            gia = _BL_GIA.get(p, 0.0)
            uoc = round((sum(can) * gia + _BL_KHOI_DONG.get(p, 0.0)
                         + D._GIA_MOI_BAI.get(p, 0.0) * len(lo)     # Threads: dòng bài gốc
                         + (_BL_FB_LOC_NGAY * len(lo) if moc is not None else 0.0)) * _HE_SO_UOC, 4)
            ph = {"id": f"bl-{p}-{len(_phan_bl(v)) + len(cac)}", "nen_tang": p, "trang_thai": "cho",
                  "bai": [{k: b.get(k) for k in ("khoa", "link", "nen_tang", "tai_khoan",
                                                 "tac_gia", "binh_luan", "nguon_loai")}
                          for b in lo],
                  "per": per_lo, "gia": gia, "uoc_usd": uoc if gia else 0.0,
                  "day_du": day_du, "tang_dan": moc is not None}
            if p != "youtube":
                ph.update(actor=D._ACTORS[p], payload=_payload_bl(p, urls, per_lo, day_du, moc),
                          limit=D._limit(p, urls, per_lo))
                if D._RAM.get(p):                  # phí khởi động Threads tính theo GB RAM
                    ph.update(mem=D._RAM[p], khoi=_BL_KHOI_DONG.get(p, 0.0))
            if p == "tiktok":
                TDA.gan_binh_luan(ph, urls, 100 if day_du else min(D._TRA_LOI_TIKTOK, per_lo),
                                  {b["link"]: n for b in lo if (n := _doc_tiep_tiktok(b))}
                                  if day_du else None)
            cac.append(ph)
    if cac:
        with v._khoa:
            _phan_bl(v).extend(cac)
            v.luu()


def _chia_lo_bl(p: str, ds: list[dict], per: int) -> list[tuple[list[dict], object]]:
    """Chia bài thành lô cho actor. Cào hết: Facebook tách bài cào lần đầu với bài chỉ lấy phần
    mới (khác tham số); mỗi lô ≤ `_BL_LO_DAY_DU` bài và tổng bình luận xin vừa ~90% trần
    console của nền tảng (một bài to hơn trần thì một mình một lô — actor dừng ở trần, lượt sau
    cào tiếp vì bài còn thiếu). -> [(lô, mốc ngày lấy phần mới | None)]."""
    if not ds:
        return []
    if per:
        import deep_dive_tool as D
        n = min(_BL_LO, D._BAI_MOI_LO.get(p, _BL_LO))      # Threads: ≤ 20 bài mỗi lượt actor
        ds = sorted(ds, key=_uu_tien_bl)
        return [(ds[i:i + n], None) for i in range(0, len(ds), n)]
    gia = _BL_GIA.get(p, 0.0)
    tran = A._tran_nen_tang(p, nen=True)[1] if gia else 0.0
    toi_da_bl = int(0.9 * tran / (gia * _HE_SO_UOC)) if gia else 10 ** 9
    nhom: dict = {}
    # Ưu tiên bài chưa cào / thiếu nhiều bình luận nhất (18/10/2026, `_uu_tien_bl`) — trước đây
    # xếp theo cỡ tăng dần nên bài to luôn đứng cuối và bị bỏ khi hết tiền.
    for b in sorted(ds, key=_uu_tien_bl):
        moc = None
        if _tang_dan(b):
            moc = (b["bl_lay_luc"] - datetime.timedelta(days=1)).date()
        nhom.setdefault(moc is not None, []).append((b, moc))
    ra = []
    for _, cac in sorted(nhom.items()):
        lo, tong, moc_lo = [], 0, None
        for b, moc in cac:
            can = _can_bl(b, 0)
            if lo and (len(lo) >= _BL_LO_DAY_DU or tong + can > toi_da_bl):
                ra.append((lo, moc_lo))
                lo, tong, moc_lo = [], 0, None
            lo.append(b)
            tong += can
            if moc is not None:
                moc_lo = moc if moc_lo is None else min(moc_lo, moc)
        if lo:
            ra.append((lo, moc_lo))
    return ra


def _con_viec(v) -> float:
    """Ngân sách CỦA VIỆC còn lại (đã giữ chỗ trong sổ việc nền lúc tạo, ≤ trần console nền và
    hạn mức tháng của tài khoản) trừ tiền các phần đã xong. Việc không có ngân sách (bộ thử cũ)
    thì không giới hạn thêm. Review 15/10: bình luận không được vượt phần đã giữ chỗ — hai việc
    nền song song mới không cùng tiêu quá hạn mức tài khoản."""
    ns = v.d.get("ngan_sach_usd")
    if ns is None:
        return float("inf")
    da = sum(float(ph.get("usd_so") or 0) for _, ph in v.cac_phan()
             if ph.get("trang_thai") in _KET_PHAN)
    return max(0.0, float(ns) - da)


def _doc_bl(p: str, items: list) -> list[dict]:
    import deep_dive_tool as D
    rows, _ = {"tiktok": D._map_tiktok, "facebook": D._map_facebook,
               "instagram": D._map_instagram, "threads": D._map_threads}[p](items)
    return rows


def _quy_bl(rows: list[dict], bai: list[dict]) -> dict[str, list[dict]]:
    """Bình luận → bài (theo id bài trong link, như `deep_dive_tool._quy_ve_bai`)."""
    import deep_dive_tool as D
    theo_link = {b["link"]: b for b in bai}
    ra: dict[str, list[dict]] = {b["khoa"]: [] for b in bai}
    for r in rows:
        u = D._quy_ve_bai(r.get("_nguon") or [r.get("link") or ""], list(theo_link))
        if u:
            ra[theo_link[u]["khoa"]].append(r)
    return ra


def _lay_binh_luan(v, du_an: dict, luot: int, con: float, han: float) -> dict:
    """Cào + gán nhãn + ghi bình luận cho các bài nên cào. -> thống kê. Tiền: run id nằm trong
    phần "binh_luan" của việc nên `chot_chi_phi` tính chung. Không ném lỗi Apify ra ngoài —
    bình luận hỏng thì lượt bài vẫn xong."""
    import deep_dive_tool as D
    import quet_lon
    ma = du_an["ma"]
    tk = {"bai": 0, "lay": 0, "moi": 0, "cu": 0, "nha": 0, "usd": 0.0, "ghi_chu": [],
          "nhan": ""}
    cfg = {p: cau_hinh(du_an, "binh_luan", p) for p in BL_NEN_TANG}
    if not any(c["bat"] for c in cfg.values()):
        return tk
    import phan_loai
    thuong_hieu = phan_loai.thuong_hieu_du_an(du_an)
    if not _phan_bl(v):
        ds: list[dict] = []
        for p in BL_NEN_TANG:
            c = cfg[p]
            dung = A._youtube_co_key() if p == "youtube" else _nen_tang_dung_duoc(p)[0]
            if c["bat"] and dung:
                ds += K.bai_can_lay_binh_luan(ma, [p], c["so_bai"], cao_het=not c["moi_bai"])
        _tao_cac_phan_bl(v, ds, {p: c["moi_bai"] for p, c in cfg.items()})
        tk["ghi_chu"] += _cau_uu_tien_bl(ds)
    cac_ph = list(_phan_bl(v))
    for i, ph in enumerate(cac_ph):
        p = ph["nen_tang"]
        if ph.get("trang_thai") in _KET_PHAN:
            continue
        bai = ph["bai"]
        tk["bai"] += len(bai)
        rows: list[dict] = []
        if p == "youtube":
            kq = D._yt_api_lo([b["link"] for b in bai], int(ph.get("per") or 100), han)
            rows = kq["binh_luan"]
            if kq["loi"]:
                tk["ghi_chu"].append(f"bình luận YouTube: {A._che_token(kq['loi'])[:120]}")
            _ghi_bl_kho(ma, luot, ph, rows, thuong_hieu, han, tk,
                        day_du=not (kq["loi"] or kq["chua_chay"] or kq["mot_phan"]))
            v.cap_nhat_phan(ph, trang_thai="xong" if not kq["loi"] else "mot_phan",
                            ma="OK" if not kq["loi"] else "LOI", so_item=len(rows), usd_so=0.0,
                            ly_do=kq["loi"][:200])
            continue
        dang_do = ph.get("trang_thai") in ("dang_gui", "dang_chay")
        min_charge = float(D._MIN_CHARGE.get(p, 0.0))
        if dang_do:
            cap = float(ph.get("tran_usd") or 0) or _TRAN_TOI_THIEU
        else:
            tran_console = A._tran_nen_tang(p, nen=True)[1]
            sau = sum(float(x.get("uoc_usd") or 0) for x in cac_ph[i + 1:]
                      if x.get("trang_thai") not in _KET_PHAN)
            cap = _tran_lo_bl(tran_console, con, _con_viec(v), sau, float(ph["uoc_usd"]),
                              min_charge)
            het_gio = v.con_giay() < _CHUA_GIAY_CUOI + 60
            if cap < max(min_charge, _TRAN_TOI_THIEU) - 1e-9 or het_gio:
                ly = ("hết giờ" if het_gio else
                      f"trần còn {_usd(cap)} USD (trần console, phần còn của tháng và ngân sách "
                      f"của lượt) < mức actor đòi {_usd(max(min_charge, _TRAN_TOI_THIEU))} USD")
                tk["ghi_chu"].append(f"bình luận {_TEN[p]}: bỏ qua ({ly})")
                v.cap_nhat_phan(ph, trang_thai="loi", ma="NGAN_SACH", so_item=0, usd_so=0.0,
                                ly_do=ly)
                continue
        items, meta, loi, khong_kiem = _chay_actor(v, p, ph, cap, han, min_charge)
        if khong_kiem is not None:
            v.cap_nhat_phan(ph, trang_thai="loi", ma="KHONG_KIEM_DUOC", so_item=0,
                            usd_so=khong_kiem, ly_do=quet_lon._CAU_KHONG_KIEM)
            con = max(0.0, con - khong_kiem)
            continue
        try:
            rows = _doc_bl(p, items)
        except RuntimeError as e:             # shape lạ: báo, không ghi bừa
            loi = loi or A.LoiApify("LOI", str(e)[:250])
        tien = TDA.tien_phan(p, ph, items, meta)
        con = max(0.0, con - tien)
        tk["usd"] += tien
        if loi is not None:
            tk["ghi_chu"].append(f"bình luận {_TEN[p]}: {A._che_token(str(loi))[:120]}")
        # Ghi kho TRƯỚC khi đánh dấu phần xong: khởi động lại giữa hai bước thì đọc lại run.
        _ghi_bl_kho(ma, luot, ph, rows, thuong_hieu, han, tk,
                    day_du=loi is None and meta.get("ma", "OK") == "OK")
        quet_lon._ket_phan(v, ph, meta, len(items), loi, usd_so=tien)
    tk["usd"] = round(tk["usd"], 4)
    return tk


def _tran_lo_bl(tran_console: float, con: float, con_v: float, sau: float, uoc: float,
                min_charge: float = 0.0) -> float:
    """Trần USD một lô bình luận = min(trần console, phần còn của tháng, phần còn của việc trừ phần
    giữ cho các lô SAU (`sau` = Σ ước tính lô sau, tối đa `BL_GIU_CHO_SAU` phần còn), ước tính ×
    1,5). Vì sao giữ chỗ (18/10/2026): lô bài to đứng đầu theo ưu tiên (`_uu_tien_bl`) mà lấy hết
    phần còn thì các bài sau lại đói như cũ; phần bài to chưa cào được lượt sau đọc tiếp."""
    return round(min(tran_console, con, con_v,
                     max(_TRAN_TOI_THIEU, con_v - min(sau, BL_GIU_CHO_SAU * con_v)),
                     max(_TRAN_TOI_THIEU, min_charge, uoc * _HE_SO_TRAN)), 2)


def _cau_uu_tien_bl(ds: list[dict]) -> list[str]:
    """Câu phễu bình luận (18/10/2026): đã ưu tiên bài nào, đọc tiếp bao nhiêu video TikTok cào dở
    (bỏ bao nhiêu bình luận gốc đã có — không trả tiền đọc lại)."""
    if not ds:
        return []
    def so(n) -> str:
        return f"{int(n or 0):,}".replace(",", ".")
    chua = sorted((b for b in ds if b.get("bl_lay_luc") is None),
                  key=lambda b: -int(b.get("binh_luan") or 0))
    tiep = [n for b in ds if (n := _doc_tiep_tiktok(b))]
    ra = []
    if chua:
        ra.append(f"bình luận: ưu tiên {len(chua)} bài chưa cào thiếu nhiều nhất ("
                  + ", ".join(f"{_TEN.get(b.get('nen_tang'), b.get('nen_tang'))} "
                              f"{so(b.get('binh_luan'))}" for b in chua[:3]) + ")")
    if tiep:
        ra.append(f"bình luận TikTok: đọc tiếp {len(tiep)} video cào dở, bỏ {so(sum(tiep))} "
                  "bình luận gốc đã có")
    return ra


def _ghi_bl_kho(ma: str, luot: int, ph: dict, rows: list[dict], thuong_hieu: list[str],
                han: float, tk: dict, day_du: bool = True) -> None:
    """`day_du`=False (lỗi, huỷ, hết giờ, hết quota): chỉ bài CÓ bình luận trả về được đánh dấu
    đã cào — bài 0 dòng vì lỗi không bị gạch khỏi lượt sau (review 15/10)."""
    bai = ph["bai"]
    theo = _quy_bl(rows, bai)
    dong: list[dict] = []
    da_lay: dict[str, tuple[int, int | None]] = {}
    for b in bai:
        cua = theo.get(b["khoa"]) or []
        thay: set[str] = set()
        for r in cua:
            d = _dong_bl(r, b, thuong_hieu)
            if d["ma"] in thay:
                continue
            thay.add(d["ma"])
            dong.append(d)
        if thay or day_du:
            da_lay[b["khoa"]] = (len(thay), _so_hay_none(b.get("binh_luan")))
    import loc_rac
    loc_rac.phan_loai(dong, thuong_hieu)
    for d in dong:
        tk.setdefault("loc", {})[d["loai"]] = tk.get("loc", {}).get(d["loai"], 0) + 1
    # Cào lại (bài thêm bình luận): bình luận đã có sắc thái không gửi AI lần nữa.
    da = K.da_gan_nhan(ma, sorted({d["khoa_bai"] for d in dong})) if dong else set()
    khach = [d for d in dong if d["loai"] in loc_rac.SACH and str(d.get("text") or "").strip()
             and (d["khoa_bai"], d["ma"]) not in da]
    tk["nha"] += sum(1 for d in dong if d["cua_thuong_hieu"])
    if khach:
        _gan_nhan_bl(khach, han, tk)
    moi, cu = K.ghi_binh_luan(ma, luot, dong, da_lay)
    tk["lay"] += len(dong)
    tk["moi"] += moi
    tk["cu"] += cu


# ───────────────────────────── gán nhãn: ngay hay để nền (17/10/2026) ─────────────────────────────
# Lượt 7 (16/10) chạy 54 phút > hạn 45 phút vì gán nhãn ~2.400 bình luận ngay trong việc. Nay
# (`gan_nhan_nen` bật — mặc định) việc chỉ gán phần LUẬT; phần cần model để trống ("chưa phân loại")
# và nhịp nền gán dần. Bài Báo & Web: nhãn của bước phân xử (chỉ 400 ký tự đầu) không dùng —
# nhịp nền chấm lại theo mọi đoạn nhắc brand (`phan_loai.phan_loai_bai`). Tắt nền hoặc luồng nền
# không chạy trong tiến trình này (`gan_nhan_nen.dang_chay`): gán ngay như cũ.
def _gan_nhan_bl(khach: list[dict], han: float, tk: dict) -> None:
    """Điền sắc thái/chủ đề cho bình luận khách sắp ghi kho; `tk["nhan"]`/`tk["cho_nen"]` ghi
    chuyện đã xảy ra."""
    import gan_nhan_nen
    import phan_loai
    if gan_nhan_nen.dang_chay():
        nhan = phan_loai.gan_theo_luat(khach)
        for d, x in zip(khach, nhan):
            if x and x[0] != phan_loai.CHUA:
                d["sac_thai"], d["chu_de"] = x
        tk["cho_nen"] = tk.get("cho_nen", 0) + sum(1 for x in nhan if x is None)
        tk["nhan"] = "để nền"
        return
    tt: dict = {}
    nhan = phan_loai.phan_loai_binh_luan(
        khach, max(0.0, min(120.0, han - time.monotonic() - 20)), tt, song_song=2)
    for d, (s, c) in zip(khach, nhan):
        if s != phan_loai.CHUA:
            d["sac_thai"] = s
        if c != phan_loai.CHUA:
            d["chu_de"] = c
    tk["nhan"] = tt.get("trang_thai") or tk["nhan"]


def _nhan_bai_ngay(d: dict, sac, cd) -> tuple:
    """(sắc thái, chủ đề) ghi kho ngay cho bài vừa giữ: bài web để nhịp nền chấm lại."""
    import gan_nhan_nen
    if d.get("platform") == W.NEN_TANG and gan_nhan_nen.dang_chay():
        return None, None
    return sac, cd


def _chay_viec(v) -> tuple[str, str]:
    ts = v.d.get("tham_so") or {}
    ma = str(ts.get("du_an") or "")
    du_an = K.doc_du_an(ma)
    if not du_an:
        return "loi", f"Việc theo dõi {v.ma}: dự án '{ma}' không còn trong kho."
    luot = v.d.get("luot_id")
    lich_id = ts.get("lich_id")
    if not luot:
        # Ghi id lượt vào sổ việc NGAY: bot khởi động lại thì chạy tiếp đúng lượt này, không
        # mở lượt thứ hai (lượt bỏ dở sẽ chặn lượt mới tới `GIO_BO_DO` giờ).
        luot = K.mo_luot(ma, "theo_doi", ma_viec=v.ma,
                         job_id=str((v.d.get("kenh") or {}).get("job_id") or "") or None,
                         **({"lich_id": int(lich_id)} if lich_id else {}))
        with v._khoa:
            v.d["luot_id"] = luot
            v.luu()
    A._NEN.set(True)
    A._HUY.set(v.co_dung)
    ids = {int(i) for i in ts.get("nguon") or []}
    nguon: dict[int, dict] = {}
    tk = {"lay_duoc": 0, "qua_cu": 0, "khong_nhac": 0, "loai_tru": 0, "ai_loai": 0, "giu": 0,
          "ai": ""}
    loi: dict[int, str] = {}
    ghi_chu: list[str] = []
    moi = cu = lam_moi = 0
    bl: dict = {}
    tkq: dict = {}
    dp: dict = {}
    ok: list[int] = []
    cau_co: list[str] = []          # phễu co số bài theo nhịp đăng (không phải lỗi của lượt)
    loi_chung = None
    usd = 0.0
    try:
        # Đọc LẠI nguồn: nguồn đã tạm dừng/xoá sau khi tạo việc thì không quét. Nguồn đã quét
        # xong ở lần chạy trước khởi động lại (đã dời quet_cuoi) vẫn giữ để đọc lại bài từ đĩa.
        doc_nguon = K.nguon_dang_theo_doi if ts.get("moi_nguon") else K.nguon_toi_han
        nguon = {int(n["id"]): n for n in doc_nguon(ma) if int(n["id"]) in ids}
        # Review 15/10: lượt chỉ ghi chi phí vào kho ở `finally` — khởi động lại giữa chừng thì
        # tiền các phần đã xong của việc này chưa nằm trong "đã tiêu tháng": trừ ở đây.
        da_xong = sum(float(ph.get("usd_so") or 0) for _, ph in v.cac_phan()
                      if ph.get("trang_thai") in _KET_PHAN)
        con = max(0.0, float(du_an["tran_usd_thang"] or 0) - K.da_tieu_thang(ma) - da_xong)
        han = v.han_mono(_CHUA_GIAY_CUOI)
        for p in THU_TU:
            for ph in ((v.d.get("nen_tang") or {}).get(p) or {}).get("phan") or []:
                ds = [nguon[i] for i in ph.get("nguon") or [] if i in nguon]
                st = ph.get("trang_thai")
                if st in _KET_PHAN:
                    continue                                  # đã xong: bài đọc lại từ đĩa
                if not ds and st not in ("dang_gui", "dang_chay"):
                    v.cap_nhat_phan(ph, trang_thai="da_huy", ma="BO_QUA", so_item=0, usd_so=0.0,
                                    ly_do="nguồn đã tạm dừng/xoá trên dashboard")
                    continue
                dang_do = st in ("dang_gui", "dang_chay")
                if not dang_do and (v.da_huy() or v.con_giay() < _CHUA_GIAY_CUOI + 30):
                    huy = v.da_huy()
                    ghi_chu.append(f"{_TEN[p]}: dừng trước khi chạy ({'huỷ' if huy else 'hết giờ'})")
                    v.cap_nhat_phan(ph, trang_thai="da_huy" if huy else "loi",
                                    ma="DA_HUY" if huy else "QUA_GIO", so_item=0, usd_so=0.0)
                    continue
                if p == "youtube":
                    try:
                        kq, l = _lay_youtube(ds)
                        _ghi_phan(v, p, ph, kq, l)
                        v.cap_nhat_phan(ph, trang_thai="xong", ma="OK", usd_so=0.0,
                                        so_item=sum(len(x) for x in kq.values()))
                    except Exception as e:
                        if type(e).__name__ == "MatQuyen":
                            raise
                        ly = A._che_token(f"{type(e).__name__}: {e}")[:200]
                        v.cap_nhat_phan(ph, trang_thai="loi", ma="LOI", ly_do=ly, so_item=0,
                                        usd_so=0.0, loi_nguon={str(n["id"]): ly for n in ds})
                    continue
                if dang_do:
                    cap = float(ph.get("tran_usd") or 0) or _TRAN_TOI_THIEU
                else:
                    # Kẹp cả ngân sách CỦA VIỆC (soát 17/10/2026), không chỉ phần còn của tháng:
                    # phần dự phòng Threads thêm giữa lượt (0,137 USD/tài khoản) không được tiêu
                    # quá phần việc đã giữ chỗ — hai việc nền song song mới không cùng vượt hạn
                    # mức tài khoản. Phần không vừa ước tính thì bỏ CÓ lý do, nguồn không bị đánh
                    # lỗi (lượt sau quét lại). Trần < sàn 0,1 vẫn chạy: `_run_actor` nâng
                    # `maxTotalChargeUsd` lên 0,1 nhưng actor theo nguồn bị `maxItems` chặn tiền,
                    # còn futurizerush (không dừng ở `maxItems`) có ước tính ≥ 0,1.
                    con_v = _con_viec(v)
                    uoc_ph = float(ph.get("uoc_usd") or 0)
                    cap = _tran_phan(p, ph, con, con_v)
                    if con < max(_TRAN_TOI_THIEU, uoc_ph) - 1e-9:
                        ghi_chu.append(f"{_TEN[p]}: hết ngân sách tháng (còn {_usd(con)} USD)")
                        v.cap_nhat_phan(ph, trang_thai="loi", ma="NGAN_SACH", so_item=0,
                                        usd_so=0.0, ly_do="hết ngân sách tháng của dự án")
                        continue
                    if con_v < uoc_ph - 1e-9:
                        ly = (f"hết ngân sách của lượt (còn {_usd(con_v)} USD, phần "
                              f"{ph['id']} ước tính {_usd(uoc_ph)} USD)")
                        ghi_chu.append(f"{_TEN[p]}: {ly}")
                        v.cap_nhat_phan(ph, trang_thai="loi", ma="NGAN_SACH", so_item=0,
                                        usd_so=0.0, ly_do=ly)
                        continue
                con = max(0.0, con - _chay_phan_apify(v, p, ph, ds, cap, han))
        # Bài: đọc từ đĩa (kể cả phần đã xong trước khi bot khởi động lại).
        theo_nguon: dict[int, list] = {}
        for p in THU_TU:
            for d, dt in v.doc_dong(p):
                nid = d.get("_nguon_id")
                if nid is not None:
                    theo_nguon.setdefault(int(nid), []).append((d, dt))
        xong_ids: set[int] = set()
        for _, ph in v.cac_phan():
            for k, x in (ph.get("loi_nguon") or {}).items():
                loi[int(k)] = str(x)
            if ph.get("chuyen_du_phong"):
                # Phần hồ sơ Threads hỏng cả lượt đã giao nguồn cho phần dự phòng (17/10/2026):
                # kết quả nguồn tính theo phần dự phòng, không đánh lỗi theo phần này.
                ghi_chu.append(f"Threads: actor hồ sơ không trả hồ sơ nào "
                               f"({ph.get('ma') or 'OK'}) — chạy dự phòng futurizerush cho "
                               f"{len(ph.get('nguon') or [])} tài khoản")
                continue
            kdp = ph.get("du_phong_kq") if isinstance(ph.get("du_phong_kq"), dict) else {}
            if kdp.get("bo_qua_trang") or kdp.get("loi"):
                # Dự phòng Facebook bị bỏ / lỗi: ghi chú lượt nói rõ (lỗi từng trang ở nguồn).
                ghi_chu.append(
                    "Facebook: thedoor thiếu "
                    f"{len(kdp.get('trang') or []) + len(kdp.get('bo_qua_trang') or [])} trang — "
                    + (f"dự phòng {kdp.get('actor')} lỗi ({kdp['loi']})" if kdp.get("loi")
                       else f"dự phòng bỏ qua {len(kdp['bo_qua_trang'])} trang "
                            f"({kdp.get('bo_qua') or 'không rõ'})"))
            if ph.get("trang_thai") in ("xong", "mot_phan"):
                xong_ids.update(int(i) for i in ph.get("nguon") or [])
            elif ph.get("trang_thai") == "loi" and ph.get("ma") not in ("NGAN_SACH", "QUA_GIO"):
                for i in ph.get("nguon") or []:
                    loi.setdefault(int(i), str(ph.get("ly_do") or ph.get("ma") or "lỗi"))
        han_ai = time.monotonic() + max(0.0, min(150.0, v.con_giay() - 45))
        rows, tk = chon_bai(du_an, theo_nguon, nguon, han_ai)
        cau_co = _ghi_co_gian(ma, v, nguon, theo_nguon)
        if rows:
            moi, cu = K.ghi_bai(ma, luot, "theo_doi", rows)
        lam_moi = _lam_moi_youtube(ma, luot)
        try:
            tkq = _tim_tu_khoa(v, du_an, luot, con, han)
            con = max(0.0, con - float(tkq.get("usd") or 0))
        except Exception as e:  # tìm từ khoá hỏng không làm hỏng lượt bài
            if type(e).__name__ == "MatQuyen":
                raise
            tkq = {"ghi_chu": [f"tìm từ khoá lỗi: {A._che_token(f'{type(e).__name__}: {e}')[:150]}"]}
        try:
            # Kiểm độ phủ (17/10/2026, 2 lần/tuần): sau tìm theo từ khoá (bài sót được lấp kịp
            # vào lượt cào bình luận), tự bắt lỗi — hỏng không làm hỏng lượt bài.
            dp = _kiem_do_phu(v, du_an, luot, con, han)
            con = max(0.0, con - float(dp.get("usd") or 0))
        except Exception as e:
            if type(e).__name__ == "MatQuyen":
                raise
            # Review M4: tiền đã tiêu (ghi ngay sau khi lấy mẫu) vẫn trừ vào phần còn của tháng.
            usd_dp = float((v.d.get("kiem_do_phu") or {}).get("usd") or 0)
            con = max(0.0, con - usd_dp)
            dp = {"usd": usd_dp, "ghi_chu": [
                f"kiểm độ phủ lỗi: {A._che_token(f'{type(e).__name__}: {e}')[:150]}"]}
        try:
            bl = _lay_binh_luan(v, du_an, luot, con, han)
        except Exception as e:  # bình luận hỏng không làm hỏng lượt bài
            if type(e).__name__ == "MatQuyen":
                raise
            bl = {"ghi_chu": [f"bình luận lỗi: {A._che_token(f'{type(e).__name__}: {e}')[:150]}"]}
        ok = sorted(i for i in xong_ids if i in nguon and i not in loi)
        K.danh_dau_nguon(ok, {k: x for k, x in loi.items() if k in nguon})
    except Exception as e:
        if type(e).__name__ == "MatQuyen":
            raise
        loi_chung = A._che_token(f"{type(e).__name__}: {e}")[:300]
    finally:
        # Tiền đã tiêu phải vào lượt dù có lỗi gì (review 14/10): không thì "đã tiêu tháng"
        # đếm thiếu và lượt sau quét lại, trả tiền lần nữa.
        if v.run_ids():
            nhan = f"theo dõi {ma}" + (f" (lịch #{lich_id})" if lich_id else "")
            usd = float(v.chot_chi_phi([nhan], sorted(
                {p for p, _ in v.cac_phan()
                 if p not in ("youtube", "binh_luan", "tu_khoa", "do_phu")}),
                _hom_nay()).get("usd") or 0)
        trang_thai = ("da_huy" if v.da_huy() else "loi" if loi_chung or not ok and nguon
                      else "xong" if not loi and not ghi_chu else "mot_phan")
        try:
            K.dong_luot(luot, trang_thai=trang_thai, so_nguon=len(nguon), so_nguon_loi=len(loi),
                        bai_moi=moi + int(tkq.get("moi") or 0) + int(dp.get("bo_sung") or 0),
                        bai_cap_nhat=cu + lam_moi + int(tkq.get("cu") or 0)
                        + int(dp.get("cu") or 0), chi_phi_usd=usd,
                        # Câu độ phủ đứng TRƯỚC các dòng phễu dài (ghi_chu có trần
                        # `K.GHI_CHU_TOI_DA` — phần lỡ bị cắt là chi tiết phễu cuối).
                        ghi_chu="; ".join([*ghi_chu, *cau_co, *KDP.cau_ghi_chu(dp),
                                           *_cau_tk(tkq), *_cau_bl(bl)]) or None,
                        loi=(loi_chung or "; ".join(sorted(set(loi.values())))[:500] or None))
        except K.LoiKho as e:
            print(f"[theo_doi] không đóng được lượt {luot}: {e}", flush=True)
    ghi_han_muc_goi(luot, "luot")
    _bao_dashboard(ma, luot)
    if loi_chung:
        return "loi", (f"Theo dõi {du_an['ten']} ({v.ma}) dừng vì lỗi: {loi_chung}. Chi phí thật "
                       f"{_usd(usd)} USD đã ghi vào lượt.")
    try:
        da_tieu = K.da_tieu_thang(ma)
    except K.LoiKho:
        da_tieu = float("nan")
    van_ban = (
        f"Theo dõi {du_an['ten']} ({v.ma}) xong: quét {len(ok)}/{len(nguon)} nguồn, lấy "
        f"{tk['lay_duoc']} bài, giữ {tk['giu']} bài nhắc tới dự án ({moi} mới, {cu} cập nhật"
        + (f"; cập nhật số {lam_moi} video YouTube cũ" if lam_moi else "") + "). "
        f"Bỏ: {tk['qua_cu']} bài cũ hơn {NGAY_GIU} ngày, {tk['khong_nhac']} bài không nhắc "
        "dự án" + (f", {tk['loai_tru']} bài chứa từ loại trừ" if tk["loai_tru"] else "")
        + (f", {tk['ai_loai']} bài AI loại" if tk["ai_loai"] else "") + ". "
        f"Chi phí thật {_usd(usd)} USD; tháng này đã dùng {_usd(da_tieu)}/"
        f"{_usd(float(du_an['tran_usd_thang'] or 0))} USD. Xem chi tiết trên dashboard "
        "social.hapas.vn.")
    if tk["ai"] and tk["ai"] != "đã chạy":
        van_ban += f" Bước AI: {tk['ai']} (bài chưa có nhãn vẫn được giữ theo từ khoá)."
    if loi:
        van_ban += f" {len(loi)} nguồn lỗi: " + "; ".join(sorted(set(loi.values())))[:300] + "."
    if ghi_chu:
        van_ban += " " + "; ".join(ghi_chu) + "."
    if KDP.cau_ghi_chu(dp):
        van_ban += " " + "; ".join(KDP.cau_ghi_chu(dp)) + "."
    if _cau_tk(tkq):
        van_ban += " " + "; ".join(_cau_tk(tkq)) + "."
    if _cau_bl(bl):
        van_ban += " " + "; ".join(_cau_bl(bl)) + "."
    st_viec = {"mot_phan": "xong_mot_phan"}.get(trang_thai, trang_thai)
    return st_viec, van_ban


def _cau_bl(bl: dict) -> list[str]:
    """Câu tóm tắt bước bình luận cho lượt quét + tin nhắn kết quả."""
    if not bl:
        return []
    ra = []
    if bl.get("bai"):
        ra.append(f"bình luận: đọc {bl.get('lay', 0)} bình luận của {bl['bai']} bài "
                  f"({bl.get('moi', 0)} mới"
                  + (f", {bl['nha']} của chính thương hiệu" if bl.get("nha") else "")
                  + (f"; đã lọc: {', '.join(f'{v} {k}' for k, v in sorted(bl['loc'].items()) if k != 'hop_le')}"
                     if any(k != "hop_le" for k in (bl.get("loc") or {})) else "")
                  + f"), {_usd(bl.get('usd') or 0)} USD"
                  + (f", {bl['cho_nen']} bình luận chờ gán nhãn nền" if bl.get("cho_nen")
                     else f", gán nhãn: {bl['nhan']}" if bl.get("nhan") else ""))
    return ra + list(bl.get("ghi_chu") or [])


def _lam_moi_youtube(ma: str, luot: int) -> int:
    """Đọc lại số của video YouTube đã giữ (≤ `NGAY_LAM_MOI_YT` ngày) chưa đọc hôm nay.
    Chỉ cập nhật số (UPDATE riêng) — review 14/10: đi qua upsert đầy đủ thì INSERT thiếu cột
    NOT NULL và hỏng lặng lẽ mỗi ngày."""
    if not A._youtube_co_key():
        return 0
    try:
        cu = K.bai_youtube_can_lam_moi(ma, NGAY_LAM_MOI_YT)
        if not cu:
            return 0
        can = {k["khoa"].split(":", 1)[1] for k in cu}
        so = []
        for d, _dt in _video_youtube(sorted(can)):
            vid = d["link"].rsplit("=", 1)[-1]
            if vid in can:
                so.append({"khoa": f"youtube:{vid}", "xem": d["views"], "thich": d["likes"],
                           "binh_luan": d["comments"], "chia_se": None})
        return K.cap_nhat_so_lieu(ma, luot, so)
    except (A.LoiYouTube, K.LoiKho) as e:
        print(f"[theo_doi] làm mới YouTube lỗi: {A._che_token(str(e))[:120]}", flush=True)
        return 0


def ghi_han_muc_goi(luot: int | None = None, nguon_ghi: str = "luot") -> bool:
    """Ghi ảnh chụp hạn mức GÓI Apify (bảng `han_muc_apify`) cho khối "Gói Apify" trang Ngân sách
    (18/10/2026). Vì sao Mark ghi mà dashboard không tự hỏi Apify: chỉ `.env` của Mark giữ
    APIFY_TOKEN; GET /users/me/limits miễn phí và đã có sẵn (`apify_tool._han_muc_thang`, nhớ 60
    giây). Gói FREE 10 USD/chu kỳ là trần THẬT (trần tháng dự án HAPAS 30 USD không bao giờ chạm
    được) — thiếu số này trang Ngân sách báo "trong trần" trong khi gói còn đủ 3–4 lượt.
    -> True khi đã ghi. Không bao giờ ném (kho / Apify lỗi thì thôi, lần sau ghi)."""
    try:
        hm = A._han_muc_thang()
        if not hm:
            return False
        import quet_lon
        try:
            tran_luot = round(float(quet_lon.tran_usd_nen()), 2)
        except Exception:  # noqa: BLE001 — console không đọc được: cột NULL
            tran_luot = None
        K.ghi_han_muc({"goi": A._goi_apify() or "", "da_dung_usd": round(float(hm["dung"]), 4),
                       "tran_usd": round(float(hm["tran"]), 2), "chu_ky_tu": hm.get("bat_dau"),
                       "chu_ky_den": hm.get("reset"), "tran_luot_usd": tran_luot,
                       "du_tru_usd": quet_lon._DU_TRU_THANG, "luot_id": luot,
                       "nguon_ghi": nguon_ghi})
        return True
    except Exception as e:  # ảnh chụp hỏng không làm hỏng lượt
        if type(e).__name__ == "MatQuyen":
            raise
        print(f"[theo_doi] không ghi được hạn mức gói Apify: {type(e).__name__}", flush=True)
        return False


def _bao_dashboard(ma: str, luot: int) -> None:
    """Báo dashboard (cùng VPS) có dữ liệu mới để đẩy số xuống trình duyệt ngay. Không có
    dashboard hay lỗi thì thôi — dashboard vẫn tự kiểm định kỳ."""
    import os
    url = (os.environ.get("LANG_NGHE_BAO_URL") or "").strip()
    if not url:
        return
    khoa = (os.environ.get("LANG_NGHE_BAO_KHOA") or "").strip()
    try:
        import requests
        requests.post(url, json={"du_an": ma, "luot": luot}, timeout=3,
                      headers={"X-Lang-Nghe-Khoa": khoa} if khoa else {})
    except Exception as e:  # noqa: BLE001
        print(f"[theo_doi] không báo được dashboard: {type(e).__name__}", flush=True)


# ───────────────────────────── kết quả tìm theo từ khoá → kho ─────────────────────────────
# Lượt `social_listen` (tại chỗ hoặc nền) có từ khoá trùng từ khoá của một dự án thì bài đã giữ
# vào kho với kiểu `tu_khoa`, và tài khoản nổi mà chưa theo dõi thành ĐỀ XUẤT chờ người duyệt
# trên dashboard (Mark không tự thêm nguồn). Vì sao: chưa có danh sách nguồn Kompa (chủ dự án
# để sau), đề xuất từ chính các lượt tìm là cách gom nguồn ban đầu. Chạy luồng nền, mọi lỗi
# chỉ ghi log — không bao giờ làm chậm hay hỏng câu trả lời của social_listen.
DE_XUAT_TOI_DA = 10
DE_XUAT_TOI_THIEU_BAI = 2
DE_XUAT_TOI_THIEU_THAO_LUAN = 50


def _dinh_danh_tai_khoan(d: dict) -> tuple[str, str, str] | None:
    """(nền tảng, định danh nguồn, link) của tài khoản đăng bài; None khi không đủ để thành
    nguồn theo dõi (Facebook: actor tìm kiếm không trả URL trang ổn định). Threads (16/10/2026):
    username như `nguon.dinh_danh` — bài của tài khoản đang theo dõi (vd kênh nhà @hapas.vn)
    gắn đúng nguồn, tài khoản nổi chưa theo dõi thành đề xuất."""
    p = str(d.get("platform") or "")
    u = str(d.get("username") or "").strip().lstrip("@").lower()
    if p == "tiktok" and u:
        return p, u, f"https://www.tiktok.com/@{u}"
    if p == "instagram" and u:
        return p, u, f"https://www.instagram.com/{u}/"
    if p == "threads" and u:
        return p, u, f"https://www.threads.com/@{u}"
    if p == "youtube":
        cid = str(d.get("_kenh_id") or "")
        if re.fullmatch(r"UC[\w-]{22}", cid):
            return p, cid, f"https://www.youtube.com/channel/{cid}"
    return None


def _ban_sao_tu_khoa(hits: list) -> list[tuple[dict, datetime.datetime]]:
    """Chép đúng phần cần ghi của từng bài (đồng bộ, nhanh) để luồng nền không đọc dict mà
    `_handle` còn đang sửa."""
    import phan_loai
    ra = []
    for d, dt in hits:
        if not dt or not d.get("link"):
            continue
        goc = d.get("__goc") if isinstance(d.get("__goc"), dict) else {}
        kenh_id = ((goc.get("search") or {}).get("snippet") or {}).get("channelId") \
            if isinstance(goc.get("search"), dict) else None
        sac, cd = d.get("_sac_thai"), d.get("_chu_de")
        ra.append(({
            "platform": d.get("platform"), "kenh": d.get("kenh"), "username": d.get("username"),
            "followers": d.get("followers"), "views": d.get("views"), "likes": d.get("likes"),
            "comments": d.get("comments"), "shares": d.get("shares"),
            "hashtags": d.get("hashtags"), "text": d.get("text"), "link": d.get("link"),
            "_khop": bool(d.get("_khop")), "_ma_ai": d.get("_ma_ai"), "_kenh_id": kenh_id,
            "_goc_id": goc.get("id") if isinstance(goc.get("id"), (str, int)) else None,
            "_sac_thai": None if not sac or sac == phan_loai.CHUA else sac,
            "_chu_de": None if not cd or cd == phan_loai.CHUA else cd,
            # Bản sao bỏ `__goc`: chép id số của bài Facebook TRƯỚC (`khu_trung_fb`).
            **_cot_fb(d),
        }, dt))
    return ra


def _de_xuat_tu(ban: list, da_co: set[tuple[str, str]], queries: list[str]) -> list[dict]:
    """Tài khoản nổi trong lượt tìm mà chưa nằm trong danh sách nguồn -> đề xuất."""
    gom: dict[tuple[str, str], dict] = {}
    for d, _dt in ban:
        x = _dinh_danh_tai_khoan(d)
        if not x or (x[0], x[1]) in da_co:
            continue
        g = gom.setdefault((x[0], x[1]), {"nen_tang": x[0], "dinh_danh": x[1], "link": x[2],
                                          "ten": str(d.get("kenh") or x[1])[:200], "so_bai": 0,
                                          "thao_luan": 0})
        g["so_bai"] += 1
        g["thao_luan"] += 1 + int(_so_hay_none(d.get("comments")) or 0)
    ngay = datetime.datetime.now(_VN).strftime("%d/%m")
    ra = [g for g in gom.values() if g["so_bai"] >= DE_XUAT_TOI_THIEU_BAI
          or g["thao_luan"] >= DE_XUAT_TOI_THIEU_THAO_LUAN]
    ra.sort(key=lambda g: (-g["thao_luan"], -g["so_bai"], g["dinh_danh"]))
    for g in ra:
        g["ly_do"] = (f"{g['so_bai']} bài, {g['thao_luan']} thảo luận khi Mark tìm "
                      f"'{', '.join(queries)[:60]}' ngày {ngay}")
    return ra[:DE_XUAT_TOI_DA]


def _du_an_khop(queries: list[str], cac: list[dict]) -> list[dict]:
    """Dự án có ít nhất một từ khoá nằm trong câu tìm (so khớp bỏ dấu, không phân biệt hoa
    thường): tìm "túi hapas" thì ghi vào dự án có từ khoá "hapas"."""
    qn = [A._norm(q) for q in queries if str(q).strip()]
    return [x for x in cac
            if any(A._norm(k) and A._norm(k) in q for k in (x.get("tu_khoa") or []) for q in qn)]


def luu_tu_khoa(queries: list[str], ban: list) -> dict:
    """Ghi bản sao bài (từ `_ban_sao_tu_khoa`) vào mọi dự án khớp. -> {mã dự án: (mới, cập
    nhật, đề xuất mới)}. Ném LoiKho nếu kho hỏng — bên gọi nền tự nuốt."""
    ra: dict[str, tuple[int, int, int]] = {}
    if not ban:
        return ra
    for x in _du_an_khop(queries, K.du_an_dang_bat()):
        ma = x["ma"]
        nguon = K.nguon_cua_du_an(ma)
        theo = {(n["nen_tang"], _chuan_dinh_danh(n["nen_tang"], n["dinh_danh"])): int(n["id"])
                for n in nguon}
        rows, thay = [], set()
        for d, dt in ban:
            khoa = _khoa_bai(str(d["platform"]), str(d["link"]), {"id": d.get("_goc_id")})
            if khoa in thay:
                continue
            thay.add(khoa)
            tk = _dinh_danh_tai_khoan(d)
            rows.append({
                "khoa": khoa, "nen_tang": d["platform"],
                "nguon_id": theo.get((tk[0], tk[1])) if tk else None,
                "link": d["link"], "tac_gia": str(d.get("kenh") or "")[:200],
                "tai_khoan": str(d.get("username") or "")[:200],
                "followers": _so_hay_none(d.get("followers")), "dang_luc": dt,
                "noi_dung": str(d.get("text") or "")[:1000],
                "hashtag": str(d.get("hashtags") or "")[:500], "khop_tu_khoa": d["_khop"],
                "sac_thai": d["_sac_thai"], "chu_de": d["_chu_de"],
                "ly_do_giu": str(d.get("_ma_ai") or "khop_tu_khoa")[:60],
                "xem": _so_hay_none(d.get("views")), "thich": _so_hay_none(d.get("likes")),
                "binh_luan": _so_hay_none(d.get("comments")),
                "chia_se": _so_hay_none(d.get("shares")),
                **_cot_fb(d),
            })
        luot = K.mo_luot(ma, "tu_khoa")
        try:
            moi, cu = K.ghi_bai(ma, luot, "tu_khoa", rows)
            dx = K.ghi_de_xuat(ma, _de_xuat_tu(ban, set(theo), queries))
            K.dong_luot(luot, trang_thai="xong", bai_moi=moi, bai_cap_nhat=cu,
                        ghi_chu=(f"tìm theo từ khoá '{', '.join(queries)[:150]}'; {dx} đề xuất "
                                 "nguồn mới; chi phí ở sổ chi phí quét, không tính vào trần "
                                 "theo dõi"))
        except K.LoiKho as e:
            K.dong_luot(luot, trang_thai="loi", loi=str(e))
            raise
        _bao_dashboard(ma, luot)
        ra[ma] = (moi, cu, dx)
    return ra


def luu_tu_khoa_nen(queries: list[str], hits: list) -> None:
    """Gọi từ `social_listen`/`quet_lon`: chép dữ liệu rồi ghi kho ở luồng nền. Không bao giờ
    ném lỗi ra bên gọi."""
    import importlib.util
    import os
    import threading
    if (os.environ.get("LANG_NGHE_GHI_TU_KHOA") or "1").strip() == "0" \
            or importlib.util.find_spec("psycopg") is None:
        return                            # chưa cài kho (máy dev, bộ thử) hoặc chủ agent tắt
    try:
        ban = _ban_sao_tu_khoa(hits)
        qs = [str(q) for q in queries or [] if str(q).strip()]
    except Exception as e:  # noqa: BLE001
        print(f"[theo_doi] không chép được bài tìm theo từ khoá: {type(e).__name__}", flush=True)
        return
    if not ban or not qs:
        return

    def chay():
        try:
            luu_tu_khoa(qs, ban)
        except Exception as e:  # noqa: BLE001 — kho chưa cài/hỏng: social_listen vẫn chạy
            print(f"[theo_doi] không ghi được kho lắng nghe: {A._che_token(str(e))[:150]}",
                  flush=True)
    threading.Thread(target=chay, name="luu_tu_khoa", daemon=True).start()
