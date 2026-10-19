"""Quảng cáo TikTok (TikTok Ads, chủ dự án chốt 19/10/2026) — phần THUẦN: định nghĩa chỉ số, luật
"chỉ số tiền", phạm vi theo bên, tổng hợp số cho trang "Quảng cáo TikTok" + `/api/qc` + Mark.

Không SQL, không HTTP, không FastAPI: dashboard (`app.py`), bộ đồng bộ (`tiktok_ads.py`) và tool
`hoi_dashboard` của Mark cùng import module này — một phép tính, ba chỗ dùng (như `chi_so.py`).

Luật quyền (chủ dự án chốt):
  • Mỗi tài khoản quảng cáo thuộc một bên (`tk_quang_cao.don_vi`); chưa gán bên = chỉ quản trị viên
    thấy.
  • Chỉ số TIỀN (chi, cpm, cpc, cost_per_*, *_value, *_roas, ngân sách, billed/cash/voucher…) chỉ
    Quản trị viên và Quản lý của bên đó thấy; "Chỉ xem" của bên chỉ thấy số phân phối/tương tác.
    Lọc ở MÁY CHỦ (`loc_tien`) trước khi trả — API không bao giờ gửi trường tiền cho họ.
"""
from __future__ import annotations

import datetime
import re
import unicodedata

from dashboard import phan_quyen as PQ

VN = datetime.timezone(datetime.timedelta(hours=7))

#: 100 chỉ số `report_integrated_get` nhận được (đo thật 19/10/2026 trên 16 tài khoản — một tên
#: lạ làm hỏng CẢ lượt gọi, nên chỉ xin trong danh sách này). Bỏ `currency`, `timezone` (thuộc tính
#: tài khoản, xin riêng qua advertiser_info_get). 3 tên TikTok từ chối: cost_per_engaged_view,
#: cost_per_1000_engagements, cost_per_messaging_total_conversation_tiktok_direct_message.
CHI_SO_HOP_LE: tuple[str, ...] = (
    "spend", "impressions", "gross_impressions", "clicks", "ctr", "cpc", "cpm", "reach",
    "frequency", "cost_per_1000_reached", "result", "cost_per_result", "result_rate",
    "real_time_result", "real_time_cost_per_result", "real_time_result_rate",
    "secondary_goal_result", "cost_per_secondary_goal_result", "secondary_goal_result_rate",
    "conversion", "cost_per_conversion", "conversion_rate", "conversion_rate_v2",
    "real_time_conversion", "real_time_cost_per_conversion", "real_time_conversion_rate",
    "real_time_conversion_rate_v2", "complete_payment", "cost_per_complete_payment",
    "complete_payment_rate", "complete_payment_roas", "total_complete_payment_rate",
    "value_per_complete_payment", "purchase", "cost_per_purchase", "purchase_rate",
    "total_purchase_value", "total_landing_page_view", "cost_per_landing_page_view",
    "total_pageview", "checkout", "cost_per_checkout", "add_billing", "onsite_on_web_cart",
    "cost_per_onsite_on_web_cart", "onsite_shopping", "cost_per_onsite_shopping",
    "total_onsite_shopping_value", "onsite_shopping_roas", "onsite_initiate_checkout_count",
    "on_web_order", "total_on_web_order_value", "onsite_form", "cost_per_onsite_form", "form",
    "cost_per_form", "app_install", "cost_per_app_install", "registration",
    "cost_per_registration", "video_play_actions", "average_video_play",
    "average_video_play_per_user", "video_watched_2s", "video_watched_6s", "video_views_p25",
    "video_views_p50", "video_views_p75", "video_views_p100", "engaged_view", "engaged_view_15s",
    "paid_engaged_view", "likes", "comments", "shares", "follows", "profile_visits",
    "profile_visits_rate", "clicks_on_music_disc", "engagements", "engagement_rate",
    "duet_clicks", "stitch_clicks", "sound_usage_clicks", "anchor_clicks", "anchor_click_rate",
    "interactive_add_on_impressions", "interactive_add_on_destination_clicks",
    "interactive_add_on_activity_clicks", "interactive_add_on_option_a_clicks",
    "interactive_add_on_option_b_clicks", "live_views", "live_unique_views",
    "live_effective_views", "live_product_clicks",
    "messaging_total_conversation_tiktok_direct_message", "vta_conversion",
    "cost_per_vta_conversion", "cta_conversion", "cost_per_cta_conversion",
)
#: Thuộc tính cấp quảng cáo xin như "chỉ số" (đo 19/10/2026: hợp lệ ở data_level AUCTION_AD).
THUOC_TINH_AD: tuple[str, ...] = (
    "campaign_name", "campaign_id", "adgroup_name", "adgroup_id", "ad_name", "ad_text",
    "objective_type", "campaign_budget", "promotion_type", "placement_type", "billing_event",
    "bid_strategy", "tt_app_name", "call_to_action", "image_mode", "dpa_target_audience_type",
    "split_test", "smart_target", "campaign_dedicate_type", "opt_status",
)
#: Thuộc tính cấp campaign (xin kèm chỉ số ở AUCTION_CAMPAIGN).
THUOC_TINH_CAMPAIGN: tuple[str, ...] = ("campaign_name", "objective_type", "campaign_budget",
                                         "campaign_dedicate_type")

#: Cột số có kiểu riêng trong mọi bảng qc_* (Postgres + BigQuery): (cột, chỉ số TikTok). Thứ tự
#: = thứ tự cột trong schema.sql / bigquery.sql. Mọi chỉ số khác nằm trong JSON `chi_so`.
COT_SO: tuple[tuple[str, str], ...] = (
    ("chi", "spend"), ("hien_thi", "impressions"), ("reach", "reach"), ("click", "clicks"),
    ("ket_qua", "result"), ("chuyen_doi", "conversion"), ("view_video", "video_play_actions"),
    ("view_hai_giay", "video_watched_2s"), ("view_sau_giay", "video_watched_6s"),
    ("view_het", "video_views_p100"), ("engaged_view", "engaged_view"), ("thich", "likes"),
    ("binh_luan", "comments"), ("chia_se", "shares"), ("follow", "follows"),
    ("vao_ho_so", "profile_visits"), ("mua_shop", "onsite_shopping"),
    ("gia_tri_mua_shop", "total_onsite_shopping_value"),
)
TEN_COT_SO = tuple(c for c, _ in COT_SO)
#: Cột kiểu tiền (NUMERIC, VND theo tiền tệ tài khoản); còn lại là số đếm (BIGINT).
COT_TIEN = frozenset({"chi", "gia_tri_mua_shop"})

#: Cấp quảng cáo: 1 lượt gọi ≤ 45 chỉ số. Tài khoản lớn có hàng nghìn ad chạy mỗi ngày (MATEMADE MKT
#: 7.599 ad / 30 ngày) — xin đủ 120 tên là 3 lượt gọi cho MỖI lô 100 ad × mỗi trang; nên cấp ad chỉ
#: xin bộ dưới đây (đủ cột kiểu riêng + tỉ lệ/chi phí chính), 1 lượt mỗi trang. Cấp tài khoản và
#: campaign xin đủ CHI_SO_HOP_LE.
THUOC_TINH_AD_GIU: tuple[str, ...] = ("campaign_id", "campaign_name", "adgroup_id",
                                      "adgroup_name", "ad_name", "ad_text", "objective_type")
CHI_SO_AD: tuple[str, ...] = (
    "spend", "impressions", "reach", "clicks", "ctr", "cpc", "cpm", "frequency", "result",
    "cost_per_result", "conversion", "cost_per_conversion", "video_play_actions",
    "video_watched_2s", "video_watched_6s", "video_views_p25", "video_views_p50",
    "video_views_p75", "video_views_p100", "average_video_play", "engaged_view", "likes",
    "comments", "shares", "follows", "profile_visits", "engagements", "engagement_rate",
    "onsite_shopping", "total_onsite_shopping_value", "onsite_shopping_roas",
    "complete_payment", "total_purchase_value", "complete_payment_roas", "live_views",
    "paid_engaged_view", "cost_per_1000_reached", "total_landing_page_view",
)
#: Khán giả (báo cáo AUDIENCE, mỗi tuần, cửa sổ 30 ngày): chiều + chỉ số xin (đo 19/10/2026).
CHIEU_KHAN_GIA: tuple[str, ...] = ("age", "gender", "province_id", "platform")
CHI_SO_KHAN_GIA: tuple[str, ...] = (
    "spend", "impressions", "clicks", "ctr", "cpm", "conversion", "video_play_actions",
    "video_watched_6s", "likes", "comments", "shares", "follows", "profile_visits",
)
TEN_CHIEU = {"age": "Tuổi", "gender": "Giới tính", "province_id": "Tỉnh/thành",
             "platform": "Nền tảng"}
TEN_GIA_TRI = {
    "AGE_13_17": "13–17", "AGE_18_24": "18–24", "AGE_25_34": "25–34", "AGE_35_44": "35–44",
    "AGE_45_54": "45–54", "AGE_55_100": "55+", "NONE": "Không rõ", "FEMALE": "Nữ",
    "MALE": "Nam", "ANDROID": "Android", "IPHONE": "iPhone", "IPAD": "iPad", "WAP": "Web di động",
    "UNKNOWN": "Không rõ", "-1": "Không rõ",
}


# ───────────────────────────── chỉ số tiền ─────────────────────────────
_TIEN_DUNG = frozenset({"spend", "cpm", "cpc", "billed_cost", "cash_spend", "voucher_spend",
                        "cashback_coupon_spend", "tax_spend", "value_per_complete_payment",
                        "value_per_total_purchase", "campaign_budget", "budget", "balance"})


def la_tien(ten: str) -> bool:
    """Chỉ số / cột mang số TIỀN (chủ dự án: chỉ Quản trị viên + Quản lý của bên thấy).
    Luật theo tên để chỉ số TikTok mới thêm vẫn bị chặn đúng: spend, cpm, cpc, cost_per_*,
    real_time_cost_per_*, *_value, *_roas, *budget*, *_spend, *_cost; cột riêng chi,
    gia_tri_mua_shop, roas_shop."""
    t = str(ten or "").lower()
    if t in _TIEN_DUNG or t in COT_TIEN or t in ("roas_shop", "doanh_thu_shop"):
        return True
    return (t.startswith(("cost_", "real_time_cost_per_", "skan_cost_per_"))
            or t.endswith(("_value", "_roas", "_spend", "_cost", "_budget"))
            or "budget" in t)


def xem_tien(q: dict | None, don_vi: str | None) -> bool:
    """Người có quyền `q` thấy số tiền của bên `don_vi` không. 20/10/2026 chủ dự án: mọi người có
    quyền ở bên (Quản lý hoặc Chỉ xem) đều được biết số tiền của bên mình — nhưng chỉ qua hỏi đáp
    Mark (trang Quảng cáo chỉ quản trị viên, `thay_trang_qc`). Bên None (tài khoản chưa gán bên)
    hoặc "mọi bên": chỉ quản trị viên."""
    if PQ.la_quan_tri(q):
        return True
    if not don_vi or not PQ.co_quyen(q):
        return False
    return q["ben"].get(don_vi) in ("quan_ly", "xem")


def loc_tien(x, co_tien: bool):
    """Bỏ mọi khoá tiền (đệ quy trong dict/list) khi `co_tien` False. Không sửa bản gốc."""
    if co_tien:
        return x
    if isinstance(x, dict):
        return {k: loc_tien(v, False) for k, v in x.items() if not la_tien(k)}
    if isinstance(x, list):
        return [loc_tien(v, False) for v in x]
    return x


# ───────────────────────────── phạm vi theo bên ─────────────────────────────
def ben_doc_qc(q: dict | None, cac_tk: list[dict]) -> list[str]:
    """Mã bên người này xem được ở trang Quảng cáo (chỉ bên có ≥ 1 tài khoản đã gán)."""
    co = sorted({str(t["don_vi"]) for t in cac_tk if t.get("don_vi")})
    if PQ.la_quan_tri(q):
        return co
    return [b for b in co if b in ((q or {}).get("ben") or {})]


def thay_trang_qc(q: dict | None, ben_co_tk: set[str] | list[str]) -> bool:
    """Trang/mục "Quảng cáo TikTok" + /api/qc: CHỈ quản trị viên (20/10/2026 chủ dự án: người
    khác không xem dashboard quảng cáo, chỉ hỏi Mark và nhận câu trả lời bằng chữ).
    `ben_co_tk` giữ trong chữ ký cho nơi gọi cũ."""
    return PQ.la_quan_tri(q)


TAT_CA = "tat_ca"           # mọi bên (chỉ quản trị viên)
CHUA_GAN = "chua_gan"       # tài khoản chưa gán bên (chỉ quản trị viên)


def tk_trong_pham_vi(q: dict | None, cac_tk: list[dict], ben: str) -> list[dict]:
    """Tài khoản của bên `ben` mà người này xem được. Bên ngoài phạm vi → [] (như không có)."""
    qt = PQ.la_quan_tri(q)
    if ben == TAT_CA:
        return list(cac_tk) if qt else []
    if ben == CHUA_GAN:
        return [t for t in cac_tk if not t.get("don_vi")] if qt else []
    if not qt and ben not in ((q or {}).get("ben") or {}):
        return []
    return [t for t in cac_tk if t.get("don_vi") == ben]


# ───────────────────────────── chuẩn hoá số TikTok ─────────────────────────────
def so(v):
    """"1.234" / "1234" / 12 / "-" / "" / None → số (int khi tròn) hoặc None ("-" = TikTok không
    tính được chỉ số này cho dòng đó)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else float(v)
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "None", "null", "N/A"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def dong_so(chi_so: dict) -> dict:
    """Dòng chỉ số TikTok (tên gốc) → {cột kiểu riêng: số} theo COT_SO (thiếu = None)."""
    ra = {}
    for cot, ten in COT_SO:
        v = so(chi_so.get(ten))
        if v is not None and cot not in COT_TIEN:
            v = round(v)
        ra[cot] = v
    return ra


def ten_mau(ten: str) -> str:
    """Tên tài khoản → chữ hoa không dấu, bỏ khoảng trắng/ký hiệu (so khớp MATEMADE / MATE MADE)."""
    s = unicodedata.normalize("NFKD", str(ten or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def ben_tu_dong(ten: str) -> str:
    """Gán bên tự động khi thấy tài khoản lần đầu (chủ dự án chốt): tên có MATEMADE / MATE MADE
    (không phân biệt hoa thường, khoảng trắng) → matemade; còn lại → hapas."""
    return "matemade" if "MATEMADE" in ten_mau(ten) else "hapas"


# ───────────────────────────── tổng hợp cho trang / API / Mark ─────────────────────────────
def tuong_tac(r: dict) -> int:
    return sum(int(r.get(k) or 0) for k in ("thich", "binh_luan", "chia_se"))


def _chia(a, b):
    return round(float(a) / float(b), 2) if a is not None and b else None


def kpi(tong: dict) -> dict:
    """Tổng các cột kiểu riêng trong kỳ → ô KPI. ROAS shop = doanh thu shop / chi (lần)."""
    t = {c: tong.get(c) for c in TEN_COT_SO}
    t["tuong_tac"] = tuong_tac(t)
    t["roas_shop"] = _chia(t.get("gia_tri_mua_shop"), t.get("chi"))
    return t


def doi_pt(nay, truoc):
    """% đổi so với kỳ trước; None khi kỳ trước 0/thiếu (không chia cho 0)."""
    if nay is None or not truoc:
        return None
    return round((float(nay) - float(truoc)) / float(truoc) * 100, 1)


def khoang_truoc(tu: datetime.date, den: datetime.date) -> tuple[datetime.date, datetime.date]:
    n = (den - tu).days + 1
    return tu - datetime.timedelta(days=n), tu - datetime.timedelta(days=1)


SAP_XEP = {"chi": "chi", "hien_thi": "hien_thi", "view": "view_video", "follow": "follow"}


def cot_sap(sap: str | None, co_tien: bool) -> str:
    """Tham số `sap` → cột sắp xếp bảng top. Người không xem tiền không sắp theo chi (về hien_thi)."""
    sap = sap if sap in SAP_XEP else ("chi" if co_tien else "hien_thi")
    if sap == "chi" and not co_tien:
        sap = "hien_thi"
    return sap


def dong_top(r: dict) -> dict:
    """Một dòng bảng top (campaign / ad) từ tổng SQL → dòng hiển thị (thêm tương tác, ROAS)."""
    x = dict(r)
    x["tuong_tac"] = tuong_tac(x)
    x["roas_shop"] = _chia(x.get("gia_tri_mua_shop"), x.get("chi"))
    return x


def khan_gia(rows: list[dict]) -> dict:
    """Dòng qc_khan_gia (đã cộng theo chieu + gia_tri trên các tài khoản) → {chiều: [{nhan, …}]},
    mỗi chiều sắp theo hiển thị giảm dần, % hiển thị trong chiều."""
    ra: dict[str, list[dict]] = {c: [] for c in CHIEU_KHAN_GIA}
    for r in rows:
        c = r.get("chieu")
        if c in ra:
            g = str(r.get("gia_tri") if r.get("gia_tri") is not None else "")
            nhan = TEN_GIA_TRI.get(g) or (f"Mã vùng {g}" if c == "province_id" else g or "Không rõ")
            ra[c].append({**{k: r.get(k) for k in TEN_COT_SO}, "gia_tri": g, "nhan": nhan,
                          "tuong_tac": tuong_tac(r)})
    for c, ds in ra.items():
        tong = sum(int(x.get("hien_thi") or 0) for x in ds) or 0
        ds.sort(key=lambda x: -(x.get("hien_thi") or 0))
        for x in ds:
            x["pt"] = round(100.0 * (x.get("hien_thi") or 0) / tong, 1) if tong else None
    return ra


TEN_MUC_TIEU = {
    "REACH": "Tiếp cận", "VIDEO_VIEWS": "Lượt xem video", "ENGAGEMENT": "Tương tác",
    "TRAFFIC": "Lưu lượng", "PRODUCT_SALES": "Bán hàng", "CONVERSIONS": "Chuyển đổi",
    "WEB_CONVERSIONS": "Chuyển đổi web", "LEAD_GENERATION": "Khách tiềm năng",
    "APP_PROMOTION": "Quảng bá ứng dụng", "APP_INSTALL": "Cài ứng dụng",
    "FOLLOWERS": "Người theo dõi", "PROFILE_VISITS": "Vào hồ sơ", "SHOP_PURCHASES": "Mua Shop",
    "LIVE_SHOPPING": "Bán hàng LIVE", "RF_REACH": "Tiếp cận (đặt trước)",
}

#: Ô KPI trang Quảng cáo: mã → (nhãn, ⓘ, là tiền, tô màu ▲/▼). Thứ tự = thứ tự hiện.
KPI_QC: dict[str, tuple[str, str, bool, bool]] = {
    "chi": ("Chi tiêu", "Tổng spend TikTok báo, theo tiền tệ của tài khoản, chưa VAT.", True, False),
    "hien_thi": ("Hiển thị", "", False, True),
    "view_video": ("View video", "Lượt xem video (video_play_actions).", False, True),
    "engaged_view": ("Engaged view", ("Lượt xem ≥ 6 giây hoặc có tương tác trong 1 ngày (TikTok "
                                      "tính)."), False, True),
    "reach": ("Reach", ("Cộng reach từng ngày: một người thấy quảng cáo nhiều ngày được đếm "
                        "nhiều lần — cao hơn reach duy nhất của cả kỳ trong TikTok Ads Manager."),
              False, True),
    "tuong_tac": ("Tương tác", "Thích + bình luận + chia sẻ trên quảng cáo.", False, True),
    "follow": ("Follow", "Lượt theo dõi kênh từ quảng cáo.", False, True),
    "vao_ho_so": ("Vào hồ sơ", "Lượt vào trang hồ sơ kênh từ quảng cáo.", False, True),
    "gia_tri_mua_shop": ("Doanh thu Shop", "Giá trị mua TikTok Shop mà TikTok gán cho quảng cáo.",
                         True, True),
    "roas_shop": ("ROAS Shop", "Doanh thu Shop ÷ Chi tiêu (lần).", True, True),
}
KPI_CHINH_TIEN = ("chi", "hien_thi", "view_video")
KPI_CHINH_XEM = ("hien_thi", "view_video", "engaged_view")


def chon_kpi(co_tien: bool) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(hàng chính 3 ô, hàng phụ) — người không xem tiền không có ô tiền nào."""
    chinh = KPI_CHINH_TIEN if co_tien else KPI_CHINH_XEM
    phu = tuple(k for k, v in KPI_QC.items() if k not in chinh and (co_tien or not v[2]))
    return chinh, phu
