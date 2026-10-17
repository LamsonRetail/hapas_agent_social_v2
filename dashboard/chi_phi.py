"""Dự báo chi phí theo dõi nguồn cho trang Ngân sách (chủ dự án 15/10/2026: "dashboard phải quản
trị được chi phí — tăng giảm chi phí điều chỉnh được từ platform hoặc từ chính dashboard").

Hai tầng trần (đã chốt): platform giữ trần THÁNG cấp cửa hàng (KDLA — chưa có, platform PR #101),
dashboard giữ trần tháng từng dự án (`du_an.tran_usd_thang`); Mark áp trần THẤP HƠN. Module này
chỉ TÍNH, thuần Python, không SQL, không import module nào của Mark (venv dashboard không có).

Công thức chép từ Mark — PHẢI khớp, có bài thử đối chiếu (`tests/test_dashboard_chi_phi.py`):
  • Một lượt actor (`theo_doi._uoc_phan`): (đơn vị × giá + phí khởi động actor) × hệ số 1,3; đơn
    vị = số bài mỗi lần (Facebook), số YÊU CẦU (TikTok API, 18/10/2026: 1 hồ sơ + ⌈bài/10⌉ trang
    + 1 trang bù bài ghim) hoặc 1 tài khoản (Instagram; Threads — actor hồ sơ từ 17/10/2026);
    YouTube 0 (API miễn phí).
  • Giá `theo_doi._GIA`, hệ số `theo_doi._HE_SO_UOC`, phí khởi động `theo_doi._KHOI_NGUON` (actor
    theo dõi riêng từ 17/10/2026: Facebook thedoor, Threads hồ sơ), không có thì
    `apify_tool._START_COST`.
Dự báo cấp tháng (18/10/2026: KỲ VỌNG, không nhân hệ số 1,3 — xem `chi_phi_luot_nguon`):
  • Mỗi nguồn ĐANG theo dõi chạy (số ngày) / chu_ky_ngay lượt; phần tiền theo bài/tài khoản tính
    riêng từng nguồn.
  • Phí khởi động actor tính GẦN ĐÚNG một lần mỗi nền tảng mỗi ngày quét (Threads: một lần mỗi lô
    20 tài khoản); nền tảng có ngày quét khi nguồn có chu kỳ ngắn nhất tới hạn -> (số ngày) / chu
    kỳ ngắn nhất của nền tảng.
"Tối đa" (giữ chỗ / trần của Mark, lịch quét mọi nguồn — `uoc_mot_luot`, `nguon_moi_luot`) vẫn
nhân 1,3 như `theo_doi._uoc_phan`.
  • "Còn lại của tháng" = thời gian thật từ bây giờ tới 0 giờ ngày 1 tháng sau (giờ VN), tính lẻ
    ngày: lịch chạy hằng ngày lúc nào trong ngày cũng không bị đếm hai lần hay bỏ sót có hệ thống.
"""
from __future__ import annotations

import datetime
import math
import re
import unicodedata

VN = datetime.timezone(datetime.timedelta(hours=7))

# ─── chép từ Mark (bài thử đối chiếu; đổi bên Mark thì đổi ở đây) ───
#: `theo_doi._GIA` — giá đo thật: Facebook theo bài, Instagram theo tài khoản (25/09/2026);
#: TikTok qua TikTok API theo YÊU CẦU: 0,002 USD = giá bảng = giá thật từng run (đo lại 18/10/2026:
#: 14/14 run 0,0020, `tiktok_api.GIA_YEU_CAU`) — trước 0,0012/bài theo giả định 0,003/yêu cầu.
#: Facebook 17/10/2026: thedoor~facebook-page-scraper 0,0025 USD/bài (FREE) + 0,01 USD/run khởi động
#: (`KHOI_NGUON`); actor cũ (0,005/bài) chỉ còn làm dự phòng.
#: Threads từ 17/10/2026: actor HỒ SƠ scrapersdelight, 0,002 USD mỗi TÀI KHOẢN (kèm 4–10 bài mới
#: nhất, không phí khởi động) — như Instagram tính theo tài khoản.
GIA = {"tiktok": 0.002, "facebook": 0.0025, "instagram": 0.0026, "youtube": 0.0,
       "threads": 0.002}
#: `tiktok_api.BAI_MOI_TRANG` — userPosts trả 10 bài mỗi yêu cầu.
TT_BAI_MOI_TRANG = 10
#: `theo_doi._HE_SO_UOC` — ước tính chừa hao hụt (bài ghim, phí lẻ…).
HE_SO_UOC = 1.3
#: `apify_tool._START_COST` — phí khởi động MỖI lượt actor tìm bài. Threads: actor ép 4 GB RAM, gói
#: FREE 0,02 USD/GB = 0,08 USD (đo 16/10/2026). Instagram 0 (17/10/2026: actor hashtag và hồ sơ
#: của Apify chỉ tính theo item / tài khoản).
START_COST = {"instagram": 0.0, "threads": 0.08, "facebook": 0.00005}
#: `theo_doi._KHOI_NGUON` — phí khởi động mỗi lượt actor THEO DÕI NGUỒN: như trên, trừ actor theo
#: dõi riêng (17/10/2026): Facebook thedoor 0,01 USD/run, Threads hồ sơ không có phí khởi động.
KHOI_NGUON = {**START_COST, "facebook": 0.01, "threads": 0.0}
#: `theo_doi.TH_TOI_THIEU_BAI` / `TH_TOI_DA_MOI_LUOT` — actor Threads lấy (và tính tiền) ≥ 10 bài
#: mỗi tài khoản / từ khoá; ≤ 20 tài khoản hoặc từ khoá mỗi lượt.
TH_TOI_THIEU_BAI = 10
TH_TOI_DA_MOI_LUOT = 20
#: `theo_doi.TH2_*` — đường 2 Threads (17/10/2026, scrapersdelight tìm theo từ khoá): 0,001 USD/bài
#: trả về, không phí khởi động; mặc định BẬT, trần 100 bài/lượt, 20 bài/từ, 2 lượt/bề mặt.
TH2_GIA = 0.001
TH2_SO_BAI = 100
TH2_MOI_TU = 20
TH2_LUOT = 2

#: `theo_doi._BL_GIA` / `_BL_KHOI_DONG` — giá cào BÌNH LUẬN mỗi bình luận (gói FREE, 15/10/2026;
#: Threads 16/10/2026: actor trả lời 1 GB = 0,02 USD khởi động; TikTok qua TikTok API: 0,0004 gồm
#: trả lời — 50 gốc/yêu cầu 0,002 USD, đo 2 video 0,0002–0,0004, sửa 18/10/2026 từ 0,00075).
BL_GIA = {"tiktok": 0.0004, "facebook": 0.0025, "instagram": 0.0026, "youtube": 0.0,
          "threads": 0.0025}
BL_KHOI_DONG = {"facebook": 0.001, "threads": 0.02}
#: `theo_doi._BL_UOC_MOI_BAI` — giữ chỗ mỗi bài khi cào hết (bl_moi_bai = 0).
BL_UOC_MOI_BAI = 60

NGAY_THANG_CAU_HINH = 30     # "theo cấu hình": tháng chuẩn 30 ngày (để so sánh tháng với tháng)


#: `theo_doi._TK_GIA` / `_TK_KHOI` / `TK_*` — tìm theo từ khoá (actor của social_listen).
#: Instagram (17/10/2026, `apify~instagram-hashtag-scraper`): 0,0026 USD/item, không phí khởi động,
#: hai run mỗi lượt (`TK_IG_TAB`: tab bài + reels, mỗi run mọi hashtag); mặc định 12 hashtag.
TK_GIA = {"tiktok": 0.0001, "facebook": 0.00259, "instagram": 0.0026, "youtube": 0.0,
          "threads": 0.0025}
TK_KHOI = {"instagram": 0.0, "facebook": 0.00005, "threads": 0.08}
TK_IG_TOI_DA_TU = 12
TK_IG_TAB = 2
TK_FB_TOI_DA = 20
#: TikTok tìm theo từ khoá tính theo YÊU CẦU (`theo_doi.TK_TT_*`, `theo_doi_api.LAM_MOI_TOI_DA`).
TK_TT_YEU_CAU = 0.002
TK_TT_MOI_TRANG = 30
TK_LAM_MOI = 10
#: `theo_doi_api.MOI_TRANG` — trang "mới nhất" mỗi từ khoá TikTok trong ước tính (17/10/2026).
TK_TT_MOI_NHAT = 1

#: Báo & Web (16/10/2026, `theo_doi.WEB_*` = `nguon_web`): Google tìm qua actor SERP tính theo TRANG
#: kết quả (10 link), đọc bài bằng HTTP thường 0 USD; trang bị chặn đọc qua website-content-crawler
#: tính theo trang, có trần `boc` trang mỗi lượt (thực tế thường 0–2 trang). Từ khoá gộp OR
#: `WEB_TU_MOI_CAU` từ một câu, tối đa `WEB_TOI_DA_CAU` câu mỗi lượt.
WEB_GIA_TRANG = 0.0005
WEB_GIA_BOC = 0.009
WEB_TU_MOI_CAU = 4
WEB_TOI_DA_CAU = 4
WEB_KQ_MOI_TRANG = 10
WEB_BOC_MAC_DINH = 10
#: `theo_doi.WEB_GIO_GIAN` — ngoài chiến dịch Mark chạy web tối đa một lượt / 20 giờ (≈ 1 lượt mỗi
#: ngày có lượt quét); trong khung chiến dịch thì MỌI lượt.
WEB_GIO_GIAN = 20


def _bo_dau_web(s: str) -> str:
    """Bản sao `nguon_web._bo_dau`: bỏ dấu + thường hoá TỪNG ký tự (đ/Đ -> d)."""
    ra = []
    for c in s or "":
        if c in "đĐ":
            ra.append("d")
            continue
        g = unicodedata.normalize("NFD", c)
        ra.append((g[0] if g and unicodedata.category(g[0]) != "Mn" else c).lower()[:1] or c)
    return "".join(ra)


def _tu_web(s: str) -> list[str]:
    """Bản sao `nguon_web._tu`: các chữ/số (bỏ dấu) của một từ khoá."""
    return re.findall(r"[^\W_]+", _bo_dau_web(s))


def rut_gon_web(tu_khoa: list[str]) -> list[str]:
    """Bản sao `nguon_web.rut_gon_tu_khoa`: bỏ rỗng, bỏ trùng (không phân biệt hoa thường, giữ
    bản gặp trước), bỏ từ khoá đã được từ khoá khác phủ — có "hapas" thì "túi hapas", "hapas.vn"
    thừa (tập chữ của từ khoá kia là tập con THẬT SỰ)."""
    sach: list[str] = []
    for t in tu_khoa or []:
        t = str(t).strip()
        if t and _tu_web(t) and t.lower() not in (x.lower() for x in sach):
            sach.append(t)
    ra = []
    for t in sach:
        ti = set(_tu_web(t))
        if not any(x is not t and set(_tu_web(x)) < ti for x in sach):
            ra.append(t)
    return ra


def so_cau_web(tu: list[str]) -> int:
    """Bản sao `nguon_web.so_cau_tim`: ⌈từ khoá rút gọn / 4⌉ câu tìm, tối đa 4."""
    n = len(rut_gon_web(tu))
    return min(WEB_TOI_DA_CAU, math.ceil(n / WEB_TU_MOI_CAU)) if n else 0


def uoc_web(so_bai: int, tu: list[str], boc: int = WEB_BOC_MAC_DINH) -> float:
    """Bản sao `theo_doi.uoc_web`: USD TỐI ĐA một lượt Báo & Web = (câu × ⌈số kết quả / 10⌉ trang
    × 0,0005 + `boc` trang đọc dự phòng × 0,009) × 1,3; 0 khi không có câu tìm hoặc số bài ≤ 0."""
    cau = so_cau_web(tu)
    if so_bai <= 0 or cau <= 0:
        return 0.0
    trang = max(1, math.ceil(max(0, int(so_bai)) / WEB_KQ_MOI_TRANG))
    return round((cau * trang * WEB_GIA_TRANG + max(0, int(boc)) * WEB_GIA_BOC) * HE_SO_UOC, 4)


def uoc_tu_khoa_luot(so_bai: int, tu: list[str]) -> float:
    """Bản sao `theo_doi.uoc_tu_khoa`: USD tối đa một lượt tìm theo từ khoá của dự án (mọi nền
    tảng bật, cùng số bài; Threads gồm đường 2 theo mặc định)."""
    th2 = {"bat": True, "so_bai": TH2_SO_BAI, "so_bai_moi_tu": TH2_MOI_TU, "so_luot": TH2_LUOT}
    return round(sum(uoc_tk_nen_tang(p, so_bai, tu) for p in NEN_TANG)
                 + (uoc_th2(th2, tu) if so_bai > 0 else 0.0), 4)


def uoc_binh_luan_luot(so_bai: int, moi_bai: int, p: str = "facebook") -> float:
    """Bản sao `theo_doi.uoc_binh_luan`: USD TỐI ĐA cào bình luận một lượt (giá Facebook khi
    chưa biết bài nào — thực tế thấp hơn: chỉ bài có bình luận mới/tăng mới được cào lại)."""
    moi_bai = moi_bai or BL_UOC_MOI_BAI
    if not so_bai or not BL_GIA.get(p):
        return 0.0
    return round((so_bai * moi_bai * BL_GIA[p] + BL_KHOI_DONG.get(p, 0.0)) * HE_SO_UOC, 4)
TOP_NGUON_TON = 3


def _so(v, mac_dinh: int) -> int:
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return mac_dinh


def _so_bai_th(p, so_bai: int) -> int:
    """Bản sao `theo_doi._so_bai_nguon`: Threads gom lượt theo số bài ≥ 10 (mức của lượt dự phòng
    futurizerush); tiền nguồn Threads tính theo tài khoản (`don_vi`)."""
    return max(TH_TOI_THIEU_BAI, so_bai) if p == "threads" else so_bai


def so_yeu_cau_ho_so(n: int) -> int:
    """Bản sao `tiktok_api.so_yeu_cau_ho_so`: 1 hồ sơ + ⌈n/10⌉ trang + 1 trang bù bài ghim."""
    return 2 + math.ceil(max(1, int(n)) / TT_BAI_MOI_TRANG)


def don_vi_nguon(p: str, so_bai: int) -> int:
    """Bản sao `theo_doi.don_vi_nguon`: bài (Facebook), yêu cầu (TikTok), 1 tài khoản (Instagram —
    actor trả 12 bài mới nhất; Threads — actor hồ sơ trả 4–10 bài mới nhất, 17/10/2026)."""
    if p in ("instagram", "threads"):
        return 1
    return so_yeu_cau_ho_so(so_bai) if p == "tiktok" else int(so_bai)


def don_vi(n: dict) -> int:
    """Đơn vị tính tiền mỗi lượt của một nguồn (`don_vi_nguon`), 0 với YouTube."""
    p = n.get("nen_tang")
    if not GIA.get(p):
        return 0
    return don_vi_nguon(p, _so(n.get("so_bai_moi_lan"), 5))


def uoc_mot_luot(p: str, so_nguon: int, so_bai: int) -> float:
    """Bản sao `theo_doi._uoc_phan`: USD TỐI ĐA một lượt actor gồm `so_nguon` nguồn × đơn vị
    (`don_vi_nguon`) × giá, cộng phí khởi động (`KHOI_NGUON`), nhân hệ số."""
    gia = GIA.get(p, 0.0)
    if not gia or not so_nguon:
        return 0.0
    dv = so_nguon * don_vi_nguon(p, so_bai)
    return round((dv * gia + _khoi_nguon(p)) * HE_SO_UOC, 4)


def _khoi_nguon(p: str) -> float:
    """Phí khởi động actor theo dõi nguồn của nền tảng (bản sao `theo_doi._uoc_phan`)."""
    return KHOI_NGUON.get(p, START_COST.get(p, 0.0))


# ───── co số bài mỗi lần theo NHỊP ĐĂNG (18/10/2026) — Mark (`theo_doi.ke_hoach`) gọi đúng các hàm
# này (thuần, không SQL), dashboard dùng để báo "≈ USD/tháng" theo số bài thật sự lấy ─────
# Vì sao: nguồn theo dõi lấy N bài MỚI NHẤT mỗi lượt dù nguồn chỉ đăng 0,4–4 bài/ngày — HAPAS 6 trang
# Facebook × 10 bài = 60 bài/lượt (0,15 USD) trong khi bài mới thật ~9/ngày (kho 18/10: 13–16 bài mỗi
# trang trong 4–36 ngày). Phần lặp chỉ để làm mới số liệu bài cũ — tương tác trang dồn vào 1–3 ngày
# đầu, nên co N theo nhịp đăng quan sát được và làm mới đủ N bài mỗi `CO_GIAN_NGAY_DAY_DU` ngày.
#: Nền tảng co được: Facebook (thedoor tính theo bài), TikTok (theo trang 10 bài). Instagram /
#: Threads tính theo TÀI KHOẢN — số bài không đổi tiền.
CO_GIAN_NEN_TANG = ("facebook", "tiktok")
CO_GIAN_SAN = 3              # tối thiểu mỗi lượt (bài ghim / đăng dồn đột xuất)
CO_GIAN_HE_SO = 1.5          # dư so với số bài/ngày cao nhất đã thấy
CO_GIAN_DU = 2
CO_GIAN_NGAY_NHIP = 14       # cửa sổ đo nhịp đăng (ngày đăng của bài đã giữ)
CO_GIAN_NGAY_DAY_DU = 7      # lấy đủ N bài cấu hình mỗi chừng này ngày (làm mới số bài cũ)


def cau_hinh_co_gian(du_an: dict) -> dict:
    """`du_an.cau_hinh.theo_doi` {"co_gian": bool, "san": int, "ngay_day_du": int}; thiếu → bật,
    sàn 3, làm mới đủ mỗi 7 ngày; số rác → mặc định."""
    goc = du_an.get("cau_hinh") if isinstance(du_an.get("cau_hinh"), dict) else {}
    x = goc.get("theo_doi") if isinstance(goc.get("theo_doi"), dict) else {}
    return {"bat": x.get("co_gian", True) is not False,
            "san": _so_rieng(x.get("san"), 1, SO_TOI_DA, CO_GIAN_SAN),
            "ngay_day_du": _so_rieng(x.get("ngay_day_du"), 1, 60, CO_GIAN_NGAY_DAY_DU)}


def so_bai_co_gian(p: str, so_bai: int, max_ngay: int | None, khoang_ngay: float, cfg: dict,
                   *, day_du: bool = False, bao_hoa: bool = False,
                   chien_dich: bool = False) -> tuple[int, str]:
    """Số bài THẬT SỰ lấy của một nguồn lượt này + lý do (rỗng = không co). `max_ngay`: số bài
    cao nhất nguồn đăng trong MỘT ngày (giờ VN) suốt `CO_GIAN_NGAY_NHIP` ngày qua (None = chưa
    có bài nào đã giữ); `khoang_ngay`: số ngày từ lần quét trước (≥ chu kỳ). Lấy ĐỦ `so_bai` khi:
    tắt co giãn, nền tảng tính theo tài khoản, đang chiến dịch, lượt trước BÃO HOÀ (lấy đủ mà bài
    cũ nhất vẫn mới hơn lần quét trước — có thể còn bài sót), tới lượt làm mới đủ, chưa có lịch sử.
    Còn lại: min(so_bai, max(sàn, ⌈max_ngay × khoảng × 1,5⌉ + 2))."""
    n = max(1, int(so_bai))
    if not cfg.get("bat") or p not in CO_GIAN_NEN_TANG:
        return n, ""
    if chien_dich:
        return n, "đang chiến dịch — lấy đủ"
    if bao_hoa:
        return n, "lượt trước lấy đủ mà bài nào cũng mới — lấy đủ để không sót"
    if day_du:
        return n, f"làm mới đủ {n} bài (mỗi {cfg['ngay_day_du']} ngày)"
    if max_ngay is None:
        return n, "chưa có lịch sử đăng"
    can = math.ceil(max(0, int(max_ngay)) * max(1.0, float(khoang_ngay)) * CO_GIAN_HE_SO
                    - 1e-9) + CO_GIAN_DU
    m = min(n, max(int(cfg.get("san") or CO_GIAN_SAN), can))
    if m >= n:
        return n, ""
    return m, (f"{n}→{m} bài: đăng tối đa {int(max_ngay)} bài/ngày ({CO_GIAN_NGAY_NHIP} ngày), "
               f"{float(khoang_ngay):.1f} ngày từ lần quét trước").replace(".", ",", 1)


def nhom_fb(cac: list[tuple[int, object]], gia: float, khoi: float) -> list[tuple[int, list]]:
    """Gom nguồn Facebook (mỗi nguồn một số bài) thành các run thedoor RẺ NHẤT. thedoor nhận MỘT
    `postsToScrape` cho mọi trang của run (lấy số bài lớn nhất của nhóm) và tính 0,01 USD khởi động
    mỗi run: chia mỗi số bài một run thì tốn phí khởi động, gộp hết thì trang nhỏ lấy theo trang
    lớn. Quy hoạch động trên nguồn xếp theo số bài (nhóm liền kề, O(n²)). `cac`: [(số bài, nguồn)].
    -> [(số bài của run, [nguồn])], số bài tăng dần. HAPAS 18/10 (10, 6, 6, 3, 3, 3): 3 run =
    0,1075 USD thay vì 1 run × 10 bài = 0,16 USD."""
    ds = sorted(cac, key=lambda t: t[0])
    k = len(ds)
    if not k:
        return []
    tot = [0.0] + [math.inf] * k
    cat = [0] * (k + 1)
    for j in range(1, k + 1):
        for i in range(1, j + 1):
            c = tot[i - 1] + khoi + (j - i + 1) * ds[j - 1][0] * gia
            if c < tot[j] - 1e-12:
                tot[j], cat[j] = c, i
    ra = []
    j = k
    while j > 0:
        i = cat[j]
        ra.append((ds[j - 1][0], [x for _, x in ds[i - 1:j]]))
        j = i - 1
    return ra[::-1]


def gan_co_gian(nguon: list[dict], nhip: dict, du_an: dict) -> list[dict]:
    """Bản sao nguồn kèm số bài co theo nhịp đăng cho dashboard (`so_bai_co_gian` — None khi lấy
    đủ, `ngay_day_du`, `ly_do_co_gian`, `nhip_dang` = số bài cao nhất một ngày trong 14 ngày).
    Dashboard tính với khoảng = chu kỳ của nguồn (Mark dùng khoảng thật từ lần quét trước)."""
    cfg = cau_hinh_co_gian(du_an or {})
    ra = []
    for n in nguon:
        so = _so(n.get("so_bai_moi_lan"), 5)
        mx = nhip.get(n.get("id")) if isinstance(nhip, dict) else None
        m, ly = so_bai_co_gian(n.get("nen_tang"), so, mx, _so(n.get("chu_ky_ngay"), 1), cfg)
        ra.append({**n, "so_bai_co_gian": m if m < so else None,
                   "ngay_day_du": cfg["ngay_day_du"], "ly_do_co_gian": ly, "nhip_dang": mx,
                   "co_gian_bat": cfg["bat"], "co_gian_san": cfg["san"]})
    return ra


def don_vi_ky_vong(p: str, so_bai: int) -> int:
    """Đơn vị KỲ VỌNG của một nguồn mỗi lượt: như `don_vi_nguon`, riêng TikTok không cộng trang bù
    bài ghim (đo @hapas.official 20 bài: 3 yêu cầu = 0,006 USD — trang bù chỉ có khi bài ghim lọt
    vào các trang đầu)."""
    if p == "tiktok":
        return 1 + math.ceil(max(1, int(so_bai)) / TT_BAI_MOI_TRANG)
    return don_vi_nguon(p, so_bai)


def chi_phi_luot_nguon(n: dict) -> float:
    """Phần tiền KỲ VỌNG theo bài/tài khoản/yêu cầu của MỘT nguồn trong một lượt (chưa gồm phí
    khởi động — phí đó chung cho cả nền tảng, xem `phi_khoi_dong_ngay`).

    Vì sao không nhân `HE_SO_UOC` (18/10/2026): actor theo dõi tính ĐÚNG số đơn vị, không hao hụt —
    đo thật: thedoor `hapasglobal` 20 bài = 0,0600 USD = 0,01 + 20 × 0,0025; hồ sơ Instagram 0,0026;
    hồ sơ Threads 0,0020; TikTok API 0,0020 mỗi yêu cầu. Nhân 1,3 làm trang Nguồn báo trang Facebook
    10 bài 0,975 USD/tháng (thật 0,75 + phần phí khởi động chung). Hệ số chỉ còn ở mức TỐI ĐA."""
    p = n.get("nen_tang")
    if not GIA.get(p):
        return 0.0
    so = _so(n.get("so_bai_moi_lan"), 5)
    dv = don_vi_ky_vong(p, so)
    m = n.get("so_bai_co_gian")
    if m and int(m) < so:
        # Co theo nhịp đăng (18/10/2026, `so_bai_co_gian`): (k − 1) lượt co + 1 lượt làm mới đủ
        # mỗi k = `ngay_day_du` ngày.
        k = max(1, int(n.get("ngay_day_du") or CO_GIAN_NGAY_DAY_DU))
        dv = ((k - 1) * don_vi_ky_vong(p, int(m)) + dv) / k
    return dv * GIA[p]


def phi_khoi_dong_ngay(p: str) -> float:
    """Phí khởi động actor theo dõi nguồn một ngày quét của nền tảng (kỳ vọng, không nhân hệ số):
    thedoor 0,01 USD/run chia chung mọi trang Facebook của run."""
    return _khoi_nguon(p) if GIA.get(p) else 0.0


def chi_phi_thang_nguon(n: dict, so_ngay: float = NGAY_THANG_CAU_HINH) -> float:
    """Tiền theo bài/tài khoản của nguồn trong `so_ngay` ngày theo cấu hình hiện tại."""
    return so_ngay / _so(n.get("chu_ky_ngay"), 1) * chi_phi_luot_nguon(n)


# ───────────────────────────── tháng giờ VN ─────────────────────────────
def _dau_thang_sau(bay_gio: datetime.datetime) -> datetime.datetime:
    v = bay_gio.astimezone(VN)
    nam, thang = (v.year + 1, 1) if v.month == 12 else (v.year, v.month + 1)
    return datetime.datetime(nam, thang, 1, tzinfo=VN)


def ngay_con_lai(bay_gio: datetime.datetime) -> float:
    """Số ngày (lẻ) từ `bay_gio` tới 0 giờ ngày 1 tháng sau, giờ VN."""
    if bay_gio.tzinfo is None:
        bay_gio = bay_gio.replace(tzinfo=datetime.timezone.utc)
    return max(0.0, (_dau_thang_sau(bay_gio) - bay_gio).total_seconds() / 86400.0)


def so_ngay_thang(bay_gio: datetime.datetime) -> int:
    v = bay_gio.astimezone(VN) if bay_gio.tzinfo else bay_gio.replace(
        tzinfo=datetime.timezone.utc).astimezone(VN)
    return (_dau_thang_sau(v) - datetime.datetime(v.year, v.month, 1, tzinfo=VN)).days


# ───────────────────────────── dự báo một dự án ─────────────────────────────
def tran_hieu_luc(tran_du_an: float, tran_platform: float | None) -> float:
    """Mark áp trần THẤP HƠN giữa trần platform (cấp cửa hàng) và trần của dự án."""
    tran = float(tran_du_an or 0)
    return tran if tran_platform is None else min(tran, float(tran_platform))


def du_bao(nguon: list[dict], da_tieu: float, tran_du_an: float, tran_platform: float | None,
           bay_gio: datetime.datetime) -> dict:
    """Dự báo tiền theo dõi cả tháng của MỘT dự án. Nguồn tạm dừng không tính.

    -> {ngay_con_lai, da_tieu, con_lai (USD phần còn lại), du_bao_thang (đã tiêu + còn lại),
        thang_cau_hinh (USD một tháng 30 ngày theo cấu hình), tran_du_an, tran_platform,
        tran (hiệu lực), vuot (bool), vuot_usd, nen_tang: [{nen_tang, so_nguon, nguon_con_lai,
        khoi_dong_con_lai, con_lai, thang_cau_hinh}], nguon: [{id, nen_tang, dinh_danh, ten,
        chu_ky_ngay, so_bai_moi_lan, luot_usd, thang_usd, con_lai_usd}] (tốn nhất trước),
        top_ton: 3 nguồn tốn nhất (> 0)}."""
    con = ngay_con_lai(bay_gio)
    dang = [n for n in nguon if (n.get("trang_thai") or "dang_theo_doi") == "dang_theo_doi"]
    theo_nguon = []
    for n in dang:
        theo_nguon.append({
            "id": n.get("id"), "nen_tang": n.get("nen_tang"), "dinh_danh": n.get("dinh_danh"),
            "ten": n.get("ten") or n.get("dinh_danh"),
            "chu_ky_ngay": _so(n.get("chu_ky_ngay"), 1),
            "so_bai_moi_lan": _so(n.get("so_bai_moi_lan"), 5),
            "luot_usd": round(chi_phi_luot_nguon(n), 6),
            "thang_usd": round(chi_phi_thang_nguon(n), 6),
            "con_lai_usd": round(chi_phi_thang_nguon(n, con), 6)})
    theo_nguon.sort(key=lambda x: (-x["thang_usd"], str(x["dinh_danh"])))
    nen_tang = []
    for p in sorted({x["nen_tang"] for x in theo_nguon}):
        ds = [x for x in theo_nguon if x["nen_tang"] == p]
        ky_ngan = min(x["chu_ky_ngay"] for x in ds)
        kd_ngay = phi_khoi_dong_ngay(p)
        if p == "threads":                 # ≤ 20 tài khoản mỗi lượt actor: mỗi lô một phí khởi động
            kd_ngay *= -(-len(ds) // TH_TOI_DA_MOI_LUOT)
        nguon_con = sum(x["con_lai_usd"] for x in ds)
        kd_con = con / ky_ngan * kd_ngay
        nen_tang.append({
            "nen_tang": p, "so_nguon": len(ds),
            "nguon_con_lai": round(nguon_con, 6), "khoi_dong_con_lai": round(kd_con, 6),
            "con_lai": round(nguon_con + kd_con, 6),
            "thang_cau_hinh": round(sum(x["thang_usd"] for x in ds)
                                    + NGAY_THANG_CAU_HINH / ky_ngan * kd_ngay, 6)})
    nen_tang.sort(key=lambda x: (-x["con_lai"], x["nen_tang"]))
    con_lai = sum(x["con_lai"] for x in nen_tang)
    da_tieu = float(da_tieu or 0)
    tran = tran_hieu_luc(tran_du_an, tran_platform)
    du_bao_thang = da_tieu + con_lai
    return {
        "ngay_con_lai": round(con, 4), "da_tieu": round(da_tieu, 4),
        "con_lai": round(con_lai, 4), "du_bao_thang": round(du_bao_thang, 4),
        "thang_cau_hinh": round(sum(x["thang_cau_hinh"] for x in nen_tang), 4),
        "tran_du_an": float(tran_du_an or 0),
        "tran_platform": None if tran_platform is None else float(tran_platform),
        "tran": tran, "vuot": du_bao_thang > tran + 1e-9,
        "vuot_usd": round(max(0.0, du_bao_thang - tran), 4),
        "nen_tang": nen_tang, "nguon": theo_nguon,
        "top_ton": [x for x in theo_nguon if x["thang_usd"] > 0][:TOP_NGUON_TON],
    }


# ───── cấu hình theo nền tảng (bản sao `theo_doi.cau_hinh` — đợt 2e, bài thử đối chiếu) ─────
#: "web" (Báo & Web, 16/10/2026): chỉ tìm theo từ khoá — không cào bình luận (giá bình luận 0).
NEN_TANG = ("tiktok", "facebook", "instagram", "youtube", "threads", "web")
#: `theo_doi.MAC_DINH_TAT` — nền tảng TẮT khi `du_an.cau_hinh` chưa ghi `bat` (Threads, 16/10/2026:
#: deploy không tự tiêu tiền; chủ dự án bật trên trang này).
MAC_DINH_TAT = ("threads", "web")   # web: chỉ HAPAS bật (16/10)
SO_TOI_DA = 1_000_000        # chỉ chặn số rác — chủ dự án 15/10: "không có giới hạn"
GIOI_HAN = {"tk_so_bai": (0, SO_TOI_DA), "tk_so_tu": (1, 50), "bl_so_bai": (0, SO_TOI_DA),
            "bl_moi_bai": (0, SO_TOI_DA)}


def _kep(v, lo: int, hi: int, md: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return md


def _so_rieng(v, lo: int, hi: int, md: int) -> int:
    if isinstance(v, bool):
        return md
    try:
        n = int(v)
    except (TypeError, ValueError):
        return md
    return md if n < lo else min(hi, n)


#: Facebook ĐƯỜNG 2 (17/10/2026, `theo_doi.TK_FB2_*`): mina_safwat~facebook-search-actor, 0,002 USD/bài
#: + 0,00005 USD/run, mỗi cụm nhiều từ có tên brand một run; mặc định 12 bài mỗi cụm, nhịp 20 giờ
#: (chiến dịch: mặc định CŨNG 20 giờ từ soát 17/10/2026 — 6 giờ cũ ≈ 25 USD/tháng/dự án; chủ dự án
#: tự hạ `gio_chien_dich`). Ước tính trang này là TỐI ĐA mỗi lượt (không trừ lượt bị nhịp bỏ qua).
TK_FB2_MOI_TU = 12
TK_FB2_GIO = 20
TK_FB2_GIO_CD = TK_FB2_GIO
TK_FB2_GIA = 0.002
TK_FB2_KHOI = 0.00005


def _cau_hinh_fb2(du_an: dict, rieng: dict, bat_rieng: bool, so_fb: int) -> dict:
    """Bản sao `theo_doi._cau_hinh_fb2`: khối có `bat` thì chỉ True là bật (độc lập số bài đường
    chính); thiếu `bat` thì theo đường chính (Facebook số bài > 0)."""
    d2 = rieng.get("duong2") if isinstance(rieng.get("duong2"), dict) else {}
    so = _so_rieng(d2.get("so_bai_moi_tu"), 0, SO_TOI_DA, TK_FB2_MOI_TU)
    bat = d2["bat"] is True if "bat" in d2 else so_fb > 0
    return {"bat": bool(du_an.get("tk_bat", True)) and bat_rieng and bat and so > 0,
            "so_bai_moi_tu": so,
            "gio": _so_rieng(d2.get("gio"), 0, 24 * 31, TK_FB2_GIO),
            "gio_chien_dich": _so_rieng(d2.get("gio_chien_dich"), 0, 24 * 31, TK_FB2_GIO_CD)}


#: TikTok FEED HASHTAG (17/10/2026, `theo_doi.TK_TAG_*`): feed `challengePosts` của từ khoá một chữ,
#: trần `so_yeu_cau` yêu cầu mỗi lượt (mặc định 5 × 0,002 USD), nhịp 20 giờ.
TK_TAG_YEU_CAU = 5
TK_TAG_GIO = 20


def _cau_hinh_tag(du_an: dict, rieng: dict, bat_rieng: bool, so_tt: int) -> dict:
    """Bản sao `theo_doi._cau_hinh_tag`."""
    x = rieng.get("hashtag") if isinstance(rieng.get("hashtag"), dict) else {}
    so = _so_rieng(x.get("so_yeu_cau"), 0, SO_TOI_DA, TK_TAG_YEU_CAU)
    bat = x["bat"] is True if "bat" in x else so_tt > 0
    return {"bat": bool(du_an.get("tk_bat", True)) and bat_rieng and bat and so > 0,
            "so_yeu_cau": so, "gio": _so_rieng(x.get("gio"), 0, 24 * 31, TK_TAG_GIO)}


def tag_tiktok(tu: list[str]) -> list[str]:
    """Bản sao `theo_doi.tag_tiktok` (`tiktok_api.chuan_tag`: bỏ '#', bỏ dấu, chỉ [0-9a-z])."""
    ra: list[str] = []
    for kw in tu:
        t = (re.sub(r"[^0-9a-z]", "", _norm(str(kw or "").lstrip("#")))
             if len(str(kw).split()) == 1 else "")
        if 3 <= len(t) <= 40 and t not in ra:
            ra.append(t)
    return ra


def uoc_tag_tiktok(so_yeu_cau: int, so_tag: int) -> float:
    """Bản sao `theo_doi.uoc_tag_tiktok`."""
    if so_yeu_cau <= 0 or so_tag <= 0:
        return 0.0
    return round(so_yeu_cau * TK_TT_YEU_CAU * HE_SO_UOC, 4)


def _tokens(s: str) -> list[str]:
    """Bản sao `apify_tool._tokens`: bỏ dấu, thường hoá, tách theo ký tự không phải chữ/số."""
    return re.findall(r"[^\W_]+", _norm(s))


def tu_fb_duong2(du_an: dict, tu: list[str] | None = None) -> list[str]:
    """Bản sao `theo_doi.tu_fb_duong2`: cụm ≥ 2 chữ có tên brand (mọi chữ của tên, hoặc tên viết
    liền, là một chữ của cụm)."""
    ten = _tokens(str(du_an.get("ten") or ""))
    gon = "".join(ten)
    ra = []
    for kw in (tu if tu is not None else tu_tim(du_an)):
        chu = _tokens(kw)
        if len(str(kw).split()) >= 2 and ten and (all(t in chu for t in ten) or gon in chu):
            ra.append(kw)
    return ra


def uoc_fb_duong2(so_cum: int, moi_cum: int) -> float:
    """Bản sao `theo_doi.uoc_fb_duong2`."""
    if so_cum <= 0 or moi_cum <= 0:
        return 0.0
    return round(so_cum * (moi_cum * TK_FB2_GIA + TK_FB2_KHOI) * HE_SO_UOC, 4)


#: `theo_doi.TK_GIAN_*` (18/10/2026): giãn nhịp đường tìm ít bài mới — 3 lượt liền bài mới < 5%
#: bài về thì 44 giờ mới tìm lại; khối `gian` của nền tảng.
TK_GIAN_NEN_TANG = ("instagram", "facebook", "threads")
TK_GIAN_LUOT = 3
TK_GIAN_TY_LE = 0.05
TK_GIAN_GIO = 44
TK_GIAN_LICH_SU = 6


def _cau_hinh_gian(rieng: dict) -> dict:
    """Bản sao `theo_doi._cau_hinh_gian`."""
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


def cau_hinh(du_an: dict, nhom: str, p: str) -> dict:
    """Cấu hình HIỆU LỰC của một nền tảng — y hệt `theo_doi.cau_hinh` của Mark (cột tk_bat /
    bl_bat là công tắc tổng; thiếu `bat` thì bật trừ `MAC_DINH_TAT`; số bỏ trống/rác lấy cột
    chung, áp cho TỪNG nền tảng)."""
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
            # Trần trang đọc dự phòng mỗi lượt: 0 = tắt (hợp lệ, không rơi về mặc định).
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


def cau_hinh_th2(du_an: dict) -> dict:
    """Bản sao `theo_doi.cau_hinh_th2`: đường 2 Threads (`cau_hinh.tu_khoa.threads.duong2`) —
    chỉ chạy khi Threads tìm từ khoá bật; thiếu `bat` thì bật, chỉ True mới là bật; `so_bai` 0 =
    tắt; số rác → mặc định; `so_luot` kẹp 1–5."""
    goc = du_an.get("cau_hinh") if isinstance(du_an.get("cau_hinh"), dict) else {}
    nh = goc.get("tu_khoa") if isinstance(goc.get("tu_khoa"), dict) else {}
    th = nh.get("threads") if isinstance(nh.get("threads"), dict) else {}
    x = th.get("duong2") if isinstance(th.get("duong2"), dict) else {}
    so = _so_rieng(x.get("so_bai"), 0, SO_TOI_DA, TH2_SO_BAI)
    rieng = x.get("bat", True) is True and so > 0
    return {"bat": cau_hinh(du_an, "tu_khoa", "threads")["bat"] and rieng, "bat_rieng": rieng,
            "so_bai": so,
            "so_bai_moi_tu": _so_rieng(x.get("so_bai_moi_tu"), 1, SO_TOI_DA, TH2_MOI_TU),
            "so_luot": _so_rieng(x.get("so_luot"), 1, 5, TH2_LUOT)}


def uoc_th2(c2: dict, tu: list[str]) -> float:
    """Bản sao `theo_doi.uoc_th2`: USD tối đa một lượt đường 2 = min(trần bài, bài/từ × số từ —
    MỌI từ khoá, tối đa `tk_so_tu[1]`) × 0,001 × hệ số."""
    q = list(tu[:GIOI_HAN["tk_so_tu"][1]])
    if not c2.get("bat") or not q:
        return 0.0
    return round(min(c2["so_bai"], c2["so_bai_moi_tu"] * len(q)) * TH2_GIA * HE_SO_UOC, 4)


def cau_hinh_hien_thi(goc) -> dict:
    """`du_an.cau_hinh` cho biểu mẫu trang Ngân sách: nền tảng `MAC_DINH_TAT` chưa ghi `bat` thì
    điền `bat: False` — ô bật hiện ĐÚNG trạng thái hiệu lực (tắt), không theo cột tk_bat/bl_bat
    (bấm Lưu mà không để ý thì Threads không tự bật). Không sửa dict gốc."""
    goc = goc if isinstance(goc, dict) else {}
    ra = dict(goc)
    for nhom in ("tu_khoa", "binh_luan"):
        nh = dict(goc.get(nhom)) if isinstance(goc.get(nhom), dict) else {}
        for p in MAC_DINH_TAT:
            rieng = dict(nh.get(p)) if isinstance(nh.get(p), dict) else {}
            rieng.setdefault("bat", False)
            nh[p] = rieng
        ra[nhom] = nh
    return ra


def _norm(s: str) -> str:
    """Bản sao `apify_tool._norm`: bỏ dấu (kể cả đ) + thường hoá."""
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def tu_tim(du_an: dict) -> list[str]:
    """Bản sao `theo_doi.tu_tim`: từ khoá tìm (bỏ trùng, giữ thứ tự, tối đa 12)."""
    ra: list[str] = []
    for x in du_an.get("tu_khoa") or [du_an.get("ten") or ""]:
        x = " ".join(str(x).split())
        if x and _norm(x) not in {_norm(y) for y in ra}:
            ra.append(x)
    return ra[:GIOI_HAN["tk_so_tu"][1]]


def hashtag_ig(s: str) -> str:
    """Bản sao `apify_tool.hashtag_ig`: bỏ dấu (đ→d), thường hoá, bỏ mọi ký tự ngoài [a-z0-9_]."""
    return re.sub(r"[^a-z0-9_]", "", _norm(str(s or "")))


def _tu_ig(tu: list[str], so_tu: int) -> list[str]:
    """Bản sao `apify_tool.hashtag_ig_ds` + cắt `so_tu`: hashtag bỏ rỗng, bỏ trùng, giữ thứ tự."""
    return list(dict.fromkeys(t for t in (hashtag_ig(x) for x in tu) if t))[:so_tu]


def nguon_tag(du_an: dict, tu: list[str]) -> list[str]:
    """Bản sao `theo_doi.nguon_tag` (18/10/2026): hashtag riêng của dự án (`du_an.hashtag`, chuẩn
    `hashtag_ig`, tối đa 50) khi đã đặt, không thì từ khoá — đầu vào hashtag Instagram (`tu_gui`)
    và feed TikTok (`tag_tiktok`). Chỉ đổi ĐẦU VÀO, công thức ước tính giữ nguyên."""
    rieng = _tu_ig(list(du_an.get("hashtag") or []), GIOI_HAN["tk_so_tu"][1])
    return rieng or tu


def tu_gui(p: str, tu: list[str], so_tu: int = TK_IG_TOI_DA_TU, so_bai: int = 0) -> list[str]:
    """Bản sao `theo_doi._tu_cho`: từ khoá thật sự gửi actor. Instagram: `so_tu` hashtag đầu (mọi
    từ khoá viết liền, bỏ dấu — 17/10/2026); Threads: `so_bai // 10` từ đầu (≥ 1, ≤ 20 — actor lấy
    ≥ 10 bài mỗi từ)."""
    if p == "instagram":
        return _tu_ig(tu, so_tu)
    if p == "threads":
        return tu[:max(1, min(TH_TOI_DA_MOI_LUOT, so_bai // TH_TOI_THIEU_BAI))]
    return tu


def uoc_tk_nen_tang(p: str, so_bai: int, tu: list[str], so_tu: int = TK_IG_TOI_DA_TU,
                    fb_toi_da: int = TK_FB_TOI_DA, boc: int = WEB_BOC_MAC_DINH) -> float:
    """Bản sao `theo_doi.uoc_tu_khoa_nen_tang` (web: `uoc_web` với trần đọc dự phòng `boc`)."""
    if p == "web":
        return uoc_web(so_bai, tu, boc)
    q = tu_gui(p, tu, so_tu, so_bai)
    gia = TK_GIA.get(p, 0.0)
    if not q or not gia or so_bai <= 0:
        return 0.0
    if p == "instagram":
        per = max(1, math.ceil(so_bai / (TK_IG_TAB * len(q))))
        return round((TK_IG_TAB * len(q) * per * gia + TK_IG_TAB * TK_KHOI["instagram"])
                     * HE_SO_UOC, 4)
    if p == "tiktok":
        trang = 2 * math.ceil(math.ceil(so_bai / len(q)) / TK_TT_MOI_TRANG) + 1 + TK_TT_MOI_NHAT
        return round((len(q) * trang + TK_LAM_MOI) * TK_TT_YEU_CAU * HE_SO_UOC, 4)
    n = (min(so_bai, fb_toi_da) if p == "facebook"
         else max(so_bai, TH_TOI_THIEU_BAI) if p == "threads" else so_bai)
    return round((n * gia + TK_KHOI.get(p, 0.0)) * HE_SO_UOC, 4)


def bang_cau_hinh(du_an: dict) -> dict:
    """Cấu hình hiệu lực + ước tính USD/lượt từng nền tảng cho trang Ngân sách. Dashboard không
    biết gói Apify nên Facebook tính theo đúng số bài cấu hình (mức TRẦN; gói Free thực tế chỉ
    lấy tối đa `TK_FB_TOI_DA` bài) — báo cao hơn còn hơn báo thiếu. `tu_khoa[p]["so_tu_gui"]`:
    số từ khoá THẬT SỰ tìm của nền tảng (Threads ít hơn khi số bài < 10 × số từ; web: số từ khoá
    sau rút gọn, kèm `so_cau` câu tìm). `uoc_web` = phần Báo & Web của `uoc_tk` (ngoài chiến dịch
    chạy ≤ 1 lượt/ngày — `luot_web_thuong`), `uoc_tk_mxh` = phần còn lại (chạy mọi lượt)."""
    tu = tu_tim(du_an)
    tag = nguon_tag(du_an, tu)          # 18/10/2026: hashtag riêng của dự án hoặc từ khoá
    tk = {p: {**cau_hinh(du_an, "tu_khoa", p)} for p in NEN_TANG}
    bl = {p: {**cau_hinh(du_an, "binh_luan", p)} for p in NEN_TANG}
    for p in NEN_TANG:
        tu_p = tag if p == "instagram" else tu
        tk[p]["uoc"] = (uoc_tk_nen_tang(p, tk[p]["so_bai"], tu_p, tk[p]["so_tu"],
                                        fb_toi_da=GIOI_HAN["tk_so_bai"][1],
                                        boc=tk[p].get("boc", WEB_BOC_MAC_DINH))
                        if tk[p]["bat"] else 0.0)
        tk[p]["so_tu_gui"] = (len(rut_gon_web(tu)) if p == "web"
                              else len(tu_gui(p, tu_p, tk[p]["so_tu"], tk[p]["so_bai"])))
        bl[p]["uoc"] = (uoc_binh_luan_luot(bl[p]["so_bai"], bl[p]["moi_bai"], p)
                        if bl[p]["bat"] else 0.0)
    # Đường 2 Threads (17/10/2026): cộng vào ô USD của Threads; biểu mẫu chưa có ô riêng nên cấu
    # hình hiệu lực phát kèm (`duong2`) cho trình duyệt cộng đúng số máy chủ đã tính.
    c2 = cau_hinh_th2(du_an)
    tk["threads"]["duong2"] = {**c2, "uoc": uoc_th2(c2, tu),
                               "uoc_khi_bat": uoc_th2({**c2, "bat": c2["bat_rieng"]}, tu)}
    tk["threads"]["uoc"] = round(tk["threads"]["uoc"] + tk["threads"]["duong2"]["uoc"], 4)
    tk["web"]["so_cau"] = so_cau_web(tu)
    # Facebook đường 2 (17/10/2026): dòng riêng trên trang (`tk.facebook.duong2`), cộng vào tổng
    # tìm theo từ khoá; `uoc` của Facebook vẫn chỉ là đường chính.
    d2 = tk["facebook"]["duong2"]
    d2["cum"] = tu_fb_duong2(du_an, tu)
    d2["uoc"] = uoc_fb_duong2(len(d2["cum"]), d2["so_bai_moi_tu"]) if d2["bat"] else 0.0
    # TikTok feed hashtag (17/10/2026): cũng một dòng phụ, cộng vào tổng.
    th = tk["tiktok"]["hashtag"]
    th["tag"] = tag_tiktok(tag)
    th["uoc"] = uoc_tag_tiktok(th["so_yeu_cau"], len(th["tag"])) if th["bat"] else 0.0
    uoc_tk = round(sum(x["uoc"] for x in tk.values()) + d2["uoc"] + th["uoc"], 4)
    return {"tu_khoa": tk, "binh_luan": bl, "so_tu_khoa": len(tu),
            "uoc_tk": uoc_tk, "uoc_web": tk["web"]["uoc"],
            "uoc_tk_mxh": round(uoc_tk - tk["web"]["uoc"], 4),
            "uoc_bl": round(sum(x["uoc"] for x in bl.values()), 4)}


# ───── lịch quét tự động (15/10/2026): chi phí theo TẦN SUẤT lịch, không còn giả định 1 lượt/ngày ─────
def nguon_moi_luot(nguon: list[dict]) -> float:
    """USD TỐI ĐA phần NGUỒN của MỘT lượt quét mọi nguồn (lịch `quet_moi_nguon`): chia lượt actor
    đúng như `theo_doi.chia_phan` — mỗi (nền tảng, số bài mỗi lần) một lượt (Threads: số bài
    ≥ 10, ≤ 20 tài khoản mỗi lượt), mỗi lượt = (đơn vị × giá + phí khởi động) × 1,3
    (`uoc_mot_luot`). Nguồn tạm dừng, YouTube: 0."""
    nhom: dict[tuple[str, int], int] = {}
    fb: list[tuple[int, dict]] = []
    for n in nguon:
        p = n.get("nen_tang")
        if (n.get("trang_thai") or "dang_theo_doi") != "dang_theo_doi" or not GIA.get(p):
            continue
        if p == "facebook":         # = `theo_doi.chia_phan`: run thedoor gom rẻ nhất (`nhom_fb`)
            fb.append((_so(n.get("so_bai_moi_lan"), 5), n))
            continue
        k = (p, 0 if p == "instagram" else _so_bai_th(p, _so(n.get("so_bai_moi_lan"), 5)))
        nhom[k] = nhom.get(k, 0) + 1
    tong = 0.0
    for (p, bai), so in nhom.items():
        lo = TH_TOI_DA_MOI_LUOT if p == "threads" else so
        tong += sum(uoc_mot_luot(p, min(lo, so - i), bai) for i in range(0, so, lo))
    for bai, ds in nhom_fb(fb, GIA["facebook"], _khoi_nguon("facebook")):
        tong += uoc_mot_luot("facebook", len(ds), bai)
    return round(tong, 4)


def uoc_lich(lich: dict, bang: dict, nguon: list[dict]) -> dict:
    """USD TỐI ĐA một lượt của một lịch: tìm theo từ khoá + cào bình luận (`bang_cau_hinh` — chạy
    mỗi lượt) + phần nguồn khi lịch quét mọi nguồn. Lịch thường: nguồn tốn theo CHU KỲ của nguồn
    (đã nằm trong `du_bao`), không nhân theo số lượt.
    Báo & Web (`web` = USD một lượt web): lịch chiến dịch chạy web MỌI lượt nên nằm trong
    `tk_bl` / `moi_luot`; lịch thường chỉ ≤ 1 lượt web mỗi ngày (`WEB_GIO_GIAN`) nên KHÔNG nằm
    trong `moi_luot` — tính riêng theo `luot_web_thuong` (`du_bao_lich`)."""
    web = round(float(bang.get("uoc_web") or 0), 4)
    cd = lich.get("kieu") == "chien_dich"
    tk = float(bang.get("uoc_tk") or 0) - (0.0 if cd else web)
    tk_bl = round(max(0.0, tk) + float(bang.get("uoc_bl") or 0), 4)
    ng = nguon_moi_luot(nguon) if lich.get("quet_moi_nguon") else 0.0
    return {"tk_bl": tk_bl, "nguon": ng, "moi_luot": round(tk_bl + ng, 4), "web": web,
            "web_moi_luot": cd}


def luot_web_thuong(cac_lich: list[dict], tu: datetime.datetime, den: datetime.datetime) -> int:
    """Số lượt Báo & Web của các LỊCH THƯỜNG đang bật trong (tu, den]: ngoài chiến dịch Mark chạy
    web tối đa một lượt / `WEB_GIO_GIAN` giờ -> đếm số NGÀY (giờ VN) có ít nhất một mốc lịch
    thường ngoài khung chiến dịch (≤ min(số lượt, số ngày)). Lượt chiến dịch đã tính web trong
    `uoc_lich` nên không đếm ở đây."""
    from dashboard import lich_quet as LQ
    khung = [k for x in cac_lich if x.get("bat") and (k := LQ.khung_chien_dich(x))]
    ngay: set = set()
    for x in cac_lich:
        if not x.get("bat") or x.get("kieu") == "chien_dich":
            continue
        for m in LQ.lap_moc(x.get("kieu") or "", x.get("cau_hinh") or {}, tu):
            if m > den:
                break
            d = m.astimezone(VN).date()
            if d not in ngay and not any(a <= m <= b for a, b in khung):
                ngay.add(d)
    return len(ngay)


def du_bao_lich(cac_lich: list[dict], bang: dict, nguon: list[dict],
                bay_gio: datetime.datetime) -> dict:
    """Ngân sách theo LỊCH QUÉT TỰ ĐỘNG đang bật của một dự án: số lượt còn lại tháng này (giờ
    VN) và trong 30 ngày tới (mốc lịch thường trong khung chiến dịch không tính — nhường), cùng
    phần nguồn thêm của lịch quét mọi nguồn. Không có lịch đang bật -> {"co_lich": False}
    (trang Ngân sách giữ giả định cũ: 1 lượt/ngày từ lịch console).
    Báo & Web: `luot_web_con_lai` / `luot_web_30` = số lượt web (≤ 1/ngày theo lịch thường —
    `luot_web_thuong` — + mọi lượt chiến dịch); `web_them` / `web_them_30` = USD web của lịch
    thường (phần chiến dịch đã nằm trong `moi_luot` của lịch đó).
    -> {co_lich, luot_con_lai, luot_30, nguon_them, nguon_them_30, theo_lich: {id: lượt tháng},
        luot_web_con_lai, luot_web_30, web_them, web_them_30}."""
    from dashboard import lich_quet as LQ
    if not any(x.get("bat") for x in cac_lich):
        return {"co_lich": False}
    bay_gio = bay_gio if bay_gio.tzinfo else bay_gio.replace(tzinfo=datetime.timezone.utc)
    het = _dau_thang_sau(bay_gio) - datetime.timedelta(microseconds=1)
    thang = LQ.dem_luot_du_an(cac_lich, bay_gio, het)
    ba_muoi = LQ.dem_luot_du_an(cac_lich, bay_gio, bay_gio + datetime.timedelta(days=30))
    ng = nguon_moi_luot(nguon)
    moi = {x.get("id") for x in cac_lich if x.get("bat") and x.get("quet_moi_nguon")}
    cd = {x.get("id") for x in cac_lich if x.get("bat") and x.get("kieu") == "chien_dich"}
    w_thang = luot_web_thuong(cac_lich, bay_gio, het)
    w_30 = luot_web_thuong(cac_lich, bay_gio, bay_gio + datetime.timedelta(days=30))
    web = float(bang.get("uoc_web") or 0)
    return {"co_lich": True, "luot_con_lai": sum(thang.values()),
            "luot_web_con_lai": w_thang + sum(n for i, n in thang.items() if i in cd),
            "luot_web_30": w_30 + sum(n for i, n in ba_muoi.items() if i in cd),
            "web_them": round(w_thang * web, 4), "web_them_30": round(w_30 * web, 4),
            "luot_30": sum(ba_muoi.values()),
            "nguon_them": round(sum(n * ng for i, n in thang.items() if i in moi), 4),
            "nguon_them_30": round(sum(n * ng for i, n in ba_muoi.items() if i in moi), 4),
            "theo_lich": thang}


# ───── gói Apify (18/10/2026): trần THẬT của cả tài khoản, ảnh chụp do Mark ghi ─────
#: Ảnh chụp cũ hơn chừng này giờ thì nhắc (Mark ghi sau mỗi lượt + mỗi 3 giờ ở nhịp lịch quét).
GOI_CU_GIO = 6


def _vn(x) -> datetime.datetime | None:
    if not isinstance(x, datetime.datetime):
        return None
    return (x if x.tzinfo else x.replace(tzinfo=datetime.timezone.utc)).astimezone(VN)


def goi_apify(snap: dict | None, tran_noi_bo: float, bay_gio: datetime.datetime) -> dict:
    """Khối "Gói Apify" trang Ngân sách từ ảnh chụp `GET /users/me/limits` Mark ghi
    (`kho.han_muc_apify`; dashboard không giữ token Apify).

    Vì sao (chủ dự án 18/10/2026: "ko bị lố so với thực tế gói"): trần THẬT là gói — FREE 10 USD
    mỗi chu kỳ Apify (16/10–15/11), dùng chung với mọi việc khác của token; trần tháng dự án
    (HAPAS 30 USD/tháng lịch) lớn hơn thì Mark dừng vì GÓI trước (`quet_lon.ngan_sach`: phần còn
    − 0,30 dự trữ) và trần nội bộ không có tác dụng thật.

    `tran_noi_bo`: tổng trần tháng hiệu lực của các dự án đang bật. -> {"co": False} khi chưa có
    ảnh chụp; ngược lại {co, goi, da_dung, tran, con_lai, du_tru, dung_duoc, dat_lai (giờ VN),
    ngay_con (ngày lẻ tới lúc đặt lại), chu_ky_tu, tran_luot, luc, cu (ảnh chụp > GOI_CU_GIO
    giờ), qua_chu_ky (đã qua lúc đặt lại), tran_noi_bo, noi_bo_vo_hieu, canh_bao: [chữ]}."""
    if not snap:
        return {"co": False}
    bay_gio = bay_gio if bay_gio.tzinfo else bay_gio.replace(tzinfo=datetime.timezone.utc)
    tran = float(snap.get("tran_usd") or 0)
    da = float(snap.get("da_dung_usd") or 0)
    du_tru = float(snap.get("du_tru_usd") or 0)
    dat_lai = _vn(snap.get("chu_ky_den"))
    luc = _vn(snap.get("luc"))
    qua = bool(dat_lai and dat_lai <= bay_gio)
    con = max(0.0, tran - da)
    ra = {"co": True, "goi": str(snap.get("goi") or ""), "da_dung": round(da, 4),
          "tran": round(tran, 2), "con_lai": round(con, 4), "du_tru": round(du_tru, 2),
          "dung_duoc": round(max(0.0, con - du_tru), 4), "dat_lai": dat_lai,
          "ngay_con": (round(max(0.0, (dat_lai - bay_gio).total_seconds() / 86400), 2)
                       if dat_lai else None),
          "chu_ky_tu": _vn(snap.get("chu_ky_tu")),
          "tran_luot": (None if snap.get("tran_luot_usd") is None
                        else float(snap["tran_luot_usd"])),
          "luc": luc, "cu": bool(luc and (bay_gio - luc).total_seconds() > GOI_CU_GIO * 3600),
          "qua_chu_ky": qua, "tran_noi_bo": round(float(tran_noi_bo or 0), 2),
          "noi_bo_vo_hieu": tran > 0 and float(tran_noi_bo or 0) > tran + 1e-9, "canh_bao": []}
    if qua:
        ra["canh_bao"].append(
            f"Chu kỳ gói đã đặt lại lúc {dat_lai:%H:%M %d/%m/%Y}: số đã dùng ở đây là của chu "
            "kỳ trước — Mark ghi số mới ở lượt kế hoặc trong ≤ 3 giờ.")
    elif ra["noi_bo_vo_hieu"]:
        ra["canh_bao"].append(
            f"Trần nội bộ {_usd_chu(tran_noi_bo)} USD/tháng lớn hơn trần gói Apify "
            f"{_usd_chu(tran)} USD/chu kỳ: trần nội bộ không có tác dụng thật — Mark dừng quét khi "
            f"gói còn dưới {_usd_chu(du_tru)} USD dự trữ + ước tính lượt, trước khi chạm trần "
            "nội bộ. Hạ trần dự án về ≤ phần gói dành cho dự án, hoặc nâng gói Apify.")
    if ra["cu"] and not qua:
        ra["canh_bao"].append(f"Ảnh chụp gói cũ hơn {GOI_CU_GIO} giờ ({luc:%H:%M %d/%m}) — Mark "
                              "chưa ghi lại (bot tắt hoặc không đọc được Apify).")
    return ra


def _usd_chu(x) -> str:
    """USD 2 chữ số lẻ kiểu Việt (giống bộ lọc `usd_vn` của app)."""
    return f"{float(x or 0):,.2f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


# ───── dự báo theo CHI THẬT (18/10/2026) ─────
# Vì sao: `du_bao` chỉ gồm NGUỒN theo chu kỳ (HAPAS: ≈ 0,25 USD/lượt) trong khi chi thật mỗi lượt
# 7 lượt 16–17/10 là 0,60–2,00 USD (bình luận 0,23–1,71 + tìm từ khoá 0,13–0,77 + nguồn ~0,3) —
# trang báo "trong trần" sai; còn mức TỐI ĐA theo cấu hình (giữ chỗ 60 bình luận/bài × 10 bài × 5
# nền tảng = 6,5 USD bình luận, cả lượt 8,6 USD) thì lố ~6 lần. Chi thật đã chốt theo run id
# (`luot_quet.chi_phi_usd`) là thước đo duy nhất không lệch theo cấu hình.
#: ≤ 7 lượt /theodoi gần nhất trong 14 ngày, đã kết thúc, ≥ 0,05 USD (bỏ lượt chỉ YouTube và script
#: bù lịch sử — vd lượt 12 bù IG 0,0385); cần ≥ 3 lượt mới dùng.
THUC_LUOT_TOI_DA = 7
THUC_NGAY = 14
THUC_SAN_USD = 0.05
THUC_TOI_THIEU = 3


def chi_luot_thuc(luot: list[dict], bay_gio: datetime.datetime) -> dict:
    """Chi THẬT mỗi lượt theo các lượt gần nhất (dòng `kho.cac_luot`): trung vị — bền với lượt có
    kiểm độ phủ / lượt cào bù bình luận to — kèm thấp nhất, cao nhất.
    -> {co (≥ THUC_TOI_THIEU lượt), so_luot, trung_vi, thap, cao, luot_id: [id]}."""
    bay_gio = bay_gio if bay_gio.tzinfo else bay_gio.replace(tzinfo=datetime.timezone.utc)
    moc = bay_gio - datetime.timedelta(days=THUC_NGAY)
    ds = []
    for x in luot or []:
        bd = _vn(x.get("bat_dau"))
        usd = float(x.get("chi_phi_usd") or 0)
        if (x.get("kieu", "theo_doi") != "theo_doi" or x.get("trang_thai") == "dang_chay"
                or not x.get("ket_thuc") or bd is None or bd < moc or usd < THUC_SAN_USD):
            continue
        ds.append((bd, usd, x.get("id")))
    ds = sorted(ds, key=lambda t: t[0], reverse=True)[:THUC_LUOT_TOI_DA]
    if not ds:
        return {"co": False, "so_luot": 0}
    tien = sorted(u for _, u, _ in ds)
    g = len(tien) // 2
    tv = tien[g] if len(tien) % 2 else (tien[g - 1] + tien[g]) / 2
    return {"co": len(ds) >= THUC_TOI_THIEU, "so_luot": len(ds), "trung_vi": round(tv, 4),
            "thap": round(tien[0], 4), "cao": round(tien[-1], 4),
            "luot_id": [i for _, _, i in ds]}


def du_bao_thuc(db: dict, thuc: dict, so_luot_con: float, dp_con: float = 0.0) -> dict:
    """Dự báo cả tháng THEO CHI THẬT = đã tiêu + số lượt còn lại × trung vị chi thật mỗi lượt
    (gồm mọi phần của lượt: nguồn tới hạn, tìm từ khoá, bình luận, web) + kiểm độ phủ còn lại
    (2 lần/tuần — trung vị gần như không gồm nó). Chưa đủ lượt đo (`thuc.co` sai) thì trả `db`
    (chỉ nguồn) kèm `theo` = "nguon". Không sửa `db`. -> bản sao `db` với du_bao_thang, con_lai,
    vuot, vuot_usd theo chi thật + {theo, thuc, so_luot_con, dp_con, nguon_con_lai}."""
    if not thuc or not thuc.get("co"):
        return {**db, "theo": "nguon", "thuc": thuc or {"co": False}}
    con = max(0.0, float(so_luot_con or 0)) * float(thuc["trung_vi"]) + float(dp_con or 0)
    tong = float(db.get("da_tieu") or 0) + con
    tran = float(db.get("tran") or 0)
    return {**db, "theo": "thuc", "thuc": thuc, "so_luot_con": so_luot_con,
            "dp_con": round(float(dp_con or 0), 4), "nguon_con_lai": db.get("con_lai"),
            "con_lai": round(con, 4), "du_bao_thang": round(tong, 4),
            "vuot": tong > tran + 1e-9, "vuot_usd": round(max(0.0, tong - tran), 4)}


def cac_moc_du_an(cac_lich: list[dict], tu: datetime.datetime, den: datetime.datetime,
                  toi_da: int = 3000) -> list[datetime.datetime]:
    """Mọi mốc sẽ chạy trong (tu, den] của các lịch ĐANG BẬT của MỘT dự án, tăng dần — cùng luật
    `lich_quet.dem_luot_du_an` (mốc lịch thường trong khung chiến dịch đang bật thì nhường)."""
    from dashboard import lich_quet as LQ
    khung = [k for x in cac_lich if x.get("bat") and (k := LQ.khung_chien_dich(x))]
    ra: list[datetime.datetime] = []
    for x in cac_lich:
        if not x.get("bat"):
            continue
        tru = [] if x.get("kieu") == "chien_dich" else khung
        for m in LQ.lap_moc(x.get("kieu") or "", x.get("cau_hinh") or {}, tu):
            if m > den or len(ra) >= toi_da:
                break
            if not any(a <= m <= b for a, b in tru):
                ra.append(m)
    return sorted(ra)


def goi_du_bao(goi: dict, phan: list[dict], bay_gio: datetime.datetime) -> dict:
    """Thêm DỰ BÁO TỚI LÚC GÓI ĐẶT LẠI vào khối gói (`goi_apify`). `phan`: mỗi dự án đang bật
    {"ten", "thuc" (`chi_luot_thuc`), "moc": [mốc lượt tới lúc đặt lại], "dp_usd": USD kiểm độ phủ
    tới lúc đặt lại}. Gói dùng chung: mọi dự án tiêu vào cùng phần còn.
    -> bản sao `goi` + {du_bao_chu_ky, so_luot_chu_ky, het_luc (mốc lượt đầu tiên KHÔNG đủ tiền),
    du_luot (số lượt gói còn đủ), vuot_goi, du_bao_theo ("thuc" | "chua_du")}."""
    if not goi.get("co") or goi.get("qua_chu_ky"):
        return goi
    ra = {**goi, "canh_bao": list(goi.get("canh_bao") or [])}
    co = [x for x in phan if (x.get("thuc") or {}).get("co")]
    if not co:
        ra["du_bao_theo"] = "chua_du"
        return ra
    lan = sorted((m, float(x["thuc"]["trung_vi"])) for x in co for m in x.get("moc") or [])
    dp = sum(float(x.get("dp_usd") or 0) for x in co)
    tong = sum(u for _, u in lan) + dp
    con = float(goi["dung_duoc"])
    het, du, tich = None, 0, 0.0
    for m, u in lan:
        if tich + u > con + 1e-9:
            het = m
            break
        tich += u
        du += 1
    ra.update(du_bao_theo="thuc", du_bao_chu_ky=round(tong, 4), so_luot_chu_ky=len(lan),
              du_luot=du, het_luc=het, vuot_goi=tong > con + 1e-9)
    if ra["vuot_goi"]:
        tv = co[0]["thuc"]["trung_vi"] if len(co) == 1 else None
        ra["canh_bao"].insert(0, (
            f"Dự báo tới lúc gói đặt lại ({goi['dat_lai']:%d/%m}): {len(lan)} lượt"
            + (f" × {_usd_chu(tv)} USD (trung vị chi thật)" if tv is not None else "")
            + f" + kiểm độ phủ = {_usd_chu(tong)} USD > phần Mark dùng được của gói "
            f"{_usd_chu(con)} USD — gói đủ {du} lượt như hiện nay"
            + (f"; từ lượt {het:%H:%M %d/%m} Mark co tìm từ khoá/bình luận theo phần còn rồi "
               f"dừng hẳn khi gói còn dưới {_usd_chu(goi.get('du_tru'))} USD dự trữ, tới "
               f"{goi['dat_lai']:%d/%m}" if het else "")
            + ". Giảm bình luận/tìm từ khoá ở bảng cấu hình, giãn lịch, hoặc nâng gói Apify."))
    return ra


# ───── kiểm độ phủ (17/10/2026, bản sao `kiem_do_phu` của Mark — bài thử đối chiếu) ─────
#: `kiem_do_phu.TRAN_MAC_DINH` / `TRAN_TOI_DA` / `GIO_GIAN`: chủ dự án chốt hai lần mỗi tuần (mỗi
#: 84 giờ), tối đa 0,20 USD mỗi lần; tiền thật nằm trong lượt /theodoi (trần tháng dự án).
DP_TRAN_MAC_DINH = 0.20
DP_TRAN_TOI_DA = 1.0
DP_GIO_GIAN = 84


def cau_hinh_do_phu(du_an: dict) -> dict:
    """Bản sao `kiem_do_phu.cau_hinh`: `du_an.cau_hinh.do_phu` {"bat", "tran_usd"}; thiếu → bật,
    0,20 USD; trần rác/âm → mặc định; kẹp [0, 1]; trần 0 = tắt."""
    goc = du_an.get("cau_hinh") if isinstance(du_an.get("cau_hinh"), dict) else {}
    x = goc.get("do_phu") if isinstance(goc.get("do_phu"), dict) else {}
    t = x.get("tran_usd", DP_TRAN_MAC_DINH)
    try:
        tran = DP_TRAN_MAC_DINH if isinstance(t, bool) else float(t)
    except (TypeError, ValueError):
        tran = DP_TRAN_MAC_DINH
    if not math.isfinite(tran) or tran < 0:
        tran = DP_TRAN_MAC_DINH
    tran = round(min(DP_TRAN_TOI_DA, tran), 2)
    return {"bat": x.get("bat", True) is not False and tran > 0, "tran_usd": tran}


def luot_do_phu(bay_gio: datetime.datetime, den: datetime.datetime,
                lan_cuoi: datetime.datetime | None) -> int:
    """Số lần kiểm độ phủ TỐI ĐA trong [bây giờ, `den`]: lần kế = max(bây giờ, lần cuối + 84
    giờ), rồi mỗi 84 giờ (giả định lượt /theodoi đủ dày — lịch hằng ngày)."""
    ke = bay_gio if lan_cuoi is None else max(
        bay_gio, lan_cuoi + datetime.timedelta(hours=DP_GIO_GIAN))
    if ke > den:
        return 0
    return 1 + int((den - ke).total_seconds() // (DP_GIO_GIAN * 3600))


def du_bao_do_phu(du_an: dict, lan_cuoi: datetime.datetime | None,
                  bay_gio: datetime.datetime) -> dict:
    """Kiểm độ phủ cho trang Ngân sách. -> {bat, tran_usd, luot_con_lai (tới hết tháng giờ VN),
    con_lai (USD tối đa), luot_30, usd_30, lan_toi (ISO, None khi tắt)}."""
    bay_gio = bay_gio if bay_gio.tzinfo else bay_gio.replace(tzinfo=datetime.timezone.utc)
    ch = cau_hinh_do_phu(du_an)
    het = _dau_thang_sau(bay_gio) - datetime.timedelta(microseconds=1)
    luot = luot_do_phu(bay_gio, het, lan_cuoi)
    luot_30 = luot_do_phu(bay_gio, bay_gio + datetime.timedelta(days=30), lan_cuoi)
    usd = ch["tran_usd"] if ch["bat"] else 0.0
    ke = bay_gio if lan_cuoi is None else max(
        bay_gio, lan_cuoi + datetime.timedelta(hours=DP_GIO_GIAN))
    return {**ch, "luot_con_lai": luot, "con_lai": round(luot * usd, 4), "luot_30": luot_30,
            "usd_30": round(luot_30 * usd, 4),
            "lan_toi": ke.astimezone(VN).isoformat(timespec="minutes") if ch["bat"] else None}


def hang_so_cho_trinh_duyet() -> dict:
    """Hằng số cho phép tính lại ngay trên trình duyệt khi sửa số bài / chu kỳ / cấu hình."""
    # "start" / "khoi_nguon": phí khởi động actor THEO DÕI NGUỒN (trang Nguồn — nguon.js đọc
    # "khoi_nguon" trước, "start" cho trang đã nạp bản JS cũ); tìm theo từ khoá dùng "tk_khoi".
    return {"gia": GIA, "he_so": HE_SO_UOC, "start": KHOI_NGUON, "ngay": NGAY_THANG_CAU_HINH,
            "khoi_nguon": KHOI_NGUON, "tt_bai_moi_trang": TT_BAI_MOI_TRANG,
            # Co số bài theo nhịp đăng (18/10/2026) — `so_bai_co_gian`, nguon.js tính lại khi sửa.
            "co_gian": {"nen_tang": CO_GIAN_NEN_TANG, "san": CO_GIAN_SAN, "he_so": CO_GIAN_HE_SO,
                        "du": CO_GIAN_DU, "ngay_day_du": CO_GIAN_NGAY_DAY_DU},
            "tk_gia": TK_GIA, "tk_khoi": TK_KHOI, "tk_fb_toi_da": TK_FB_TOI_DA,
            "tk_ig_so_tu": TK_IG_TOI_DA_TU, "tk_ig_tab": TK_IG_TAB,
            "fb2": {"gia": TK_FB2_GIA, "khoi": TK_FB2_KHOI, "moi_tu": TK_FB2_MOI_TU},
            "tt_tag": {"yeu_cau": TK_TAG_YEU_CAU, "gio": TK_TAG_GIO},
            "bl_gia": BL_GIA, "bl_khoi": BL_KHOI_DONG,
            "bl_uoc_moi_bai": BL_UOC_MOI_BAI, "gioi_han": GIOI_HAN, "nen_tang": NEN_TANG,
            # Threads (16/10/2026): ≥ 10 bài mỗi tài khoản / từ khoá, ≤ 20 mỗi lượt; mặc định tắt.
            "th_toi_thieu_bai": TH_TOI_THIEU_BAI, "th_toi_da_moi_luot": TH_TOI_DA_MOI_LUOT,
            "mac_dinh_tat": MAC_DINH_TAT,
            # TikTok tìm theo từ khoá tính theo yêu cầu (16/10/2026) — `uoc_tk_nen_tang`.
            "tk_tt_yeu_cau": TK_TT_YEU_CAU, "tk_tt_moi_trang": TK_TT_MOI_TRANG,
            "tk_lam_moi": TK_LAM_MOI, "tk_tt_moi_nhat": TK_TT_MOI_NHAT,
            # Báo & Web (16/10/2026) — `uoc_web`, `rut_gon_web`.
            # Kiểm độ phủ (17/10/2026, 2 lần/tuần) — `cau_hinh_do_phu`.
            "do_phu": {"tran_mac_dinh": DP_TRAN_MAC_DINH, "tran_toi_da": DP_TRAN_TOI_DA,
                       "gio_gian": DP_GIO_GIAN},
            "web": {"gia_trang": WEB_GIA_TRANG, "gia_boc": WEB_GIA_BOC,
                    "tu_moi_cau": WEB_TU_MOI_CAU, "toi_da_cau": WEB_TOI_DA_CAU,
                    "kq_moi_trang": WEB_KQ_MOI_TRANG, "boc_mac_dinh": WEB_BOC_MAC_DINH}}
