"""Quảng cáo TikTok + Meta (TikTok Ads 19/10/2026, Meta Ads 20/10/2026, chủ dự án chốt) — phần
THUẦN: định nghĩa chỉ số, luật "chỉ số tiền", phạm vi theo bên, tổng hợp số cho trang "Quảng cáo" +
`/api/qc` + Mark.

Không SQL, không HTTP, không FastAPI: dashboard (`app.py`), hai bộ đồng bộ (`tiktok_ads.py`,
`meta_ads.py`) và tool `hoi_dashboard` của Mark cùng import module này — một phép tính, nhiều chỗ
dùng (như `chi_so.py`). Mỗi tài khoản có `nen_tang` (tiktok | meta); cột số kiểu riêng chung cho cả
hai nền tảng (bảng ánh xạ Meta ở `meta_ads.py`).

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
#: Mọi chiều khán giả có trong qc_khan_gia (CHECK ở schema.sql). TikTok: 4 chiều đầu; Meta (20/10/2026):
#: age + gender (cùng mã TikTok khi trùng nghĩa — `meta_ads.GIA_TRI_META`), region, publisher_platform,
#: platform_position (giá trị "<nền tảng>/<vị trí>" — Meta chỉ cho chia vị trí kèm nền tảng).
CHIEU_TAT_CA: tuple[str, ...] = ("age", "gender", "province_id", "region", "platform",
                                 "publisher_platform", "platform_position")
TEN_CHIEU = {"age": "Tuổi", "gender": "Giới tính", "province_id": "Tỉnh/thành",
             "platform": "Thiết bị", "region": "Vùng (Meta)",
             "publisher_platform": "Nền tảng Meta", "platform_position": "Vị trí Meta"}
TEN_GIA_TRI = {
    "AGE_13_17": "13–17", "AGE_18_24": "18–24", "AGE_25_34": "25–34", "AGE_35_44": "35–44",
    "AGE_45_54": "45–54", "AGE_55_100": "55+", "NONE": "Không rõ", "FEMALE": "Nữ",
    "MALE": "Nam", "ANDROID": "Android", "IPHONE": "iPhone", "IPAD": "iPad", "WAP": "Web di động",
    "UNKNOWN": "Không rõ", "-1": "Không rõ",
    # Meta (20/10/2026): nhóm tuổi Meta khác TikTok từ 55 tuổi; nền tảng hiển thị.
    "55-64": "55–64", "65+": "65+", "facebook": "Facebook", "instagram": "Instagram",
    "messenger": "Messenger", "audience_network": "Audience Network", "threads": "Threads",
    "whatsapp": "WhatsApp", "unknown": "Không rõ",
}

# ───────────────────────────── nền tảng quảng cáo ─────────────────────────────
NEN_TANG_QC: tuple[str, ...] = ("tiktok", "meta")
TEN_NEN_TANG_QC = {"tiktok": "TikTok", "meta": "Meta"}


def nen_tang_tk(t: dict) -> str:
    """Nền tảng của một dòng tk_quang_cao (dòng trước 20/10/2026 / kho giả cũ: tiktok)."""
    return str(t.get("nen_tang") or "tiktok")


def tk_dung(cac_tk: list[dict], nen_tang: str | None = None) -> list[dict]:
    """Tài khoản được tính số: đã duyệt (`duyet` — Meta: danh sách quản trị viên duyệt; TikTok
    luôn TRUE) và đúng nền tảng khi lọc (`nen_tang` None / "tat_ca" = mọi nền tảng)."""
    return [t for t in cac_tk if t.get("duyet", True) is not False
            and (nen_tang in (None, "", "tat_ca") or nen_tang_tk(t) == nen_tang)]


# ───────────────────────────── giờ đồng bộ hằng ngày (soát 20/10/2026 H2) ─────────────────────────────
#: Bộ hẹn giờ hằng ngày: TikTok 06:30, Meta 06:45 (giờ VN). Trong khung này KHÔNG mở lượt đọc tức
#: thì / lượt nhanh (bộ nghe, bộ hẹn giờ 2 phút, Mark) — lượt hằng ngày đọc lại 7 ngày, không bị
#: lượt nhỏ giành khoá. Mark trả số đã có và nói đồng bộ hằng ngày đang chạy.
GIO_DONG_BO = (datetime.time(6, 25), datetime.time(7, 30))


def trong_gio_dong_bo(bay: datetime.datetime | None = None) -> bool:
    bay = bay or datetime.datetime.now(VN)
    if bay.tzinfo is None:
        bay = bay.replace(tzinfo=datetime.UTC)
    g = bay.astimezone(VN).time()
    return GIO_DONG_BO[0] <= g < GIO_DONG_BO[1]


CAU_GIO_DONG_BO = ("Đồng bộ quảng cáo hằng ngày đang chạy (06:25–07:30 giờ VN) — chưa đọc lại "
                   "ngay; trả số đã có, sau 07:30 hỏi lại để có số mới.")


# ───────────────────────────── đồng bộ bấm tay + dải trạng thái (20/10/2026) ─────────────────────────────
#: Chủ dự án 20/10/2026: mọi người có quyền ở ít nhất một bên bấm được "Đồng bộ ngay" (như nút
#: BigQuery) — chỉ ghi cờ, lượt "nhanh" 3 ngày; giãn 15 phút sau lượt bấm tay gần nhất.
GIAN_PHUT = 15
TEN_TINH_TRANG = {"dang_chay": "đang chạy", "da_yeu_cau": "đã yêu cầu", "co_loi": "có lỗi",
                  "on": "ổn", "chua_ket_noi": "chưa kết nối"}


def _gio(x) -> str:
    if not isinstance(x, datetime.datetime):
        return "—"
    if x.tzinfo is None:
        x = x.replace(tzinfo=datetime.timezone.utc)
    return x.astimezone(VN).strftime("%H:%M")


def tinh_trang_dong_bo(the: dict | None) -> str:
    """Thẻ kết nối (`*_ads.DichVu.the`) → một trạng thái ngắn (không tiền, không số)."""
    t = the or {}
    if not t.get("co_token"):
        return "chua_ket_noi"
    if t.get("dang_dong_bo"):
        return "dang_chay"
    if t.get("yeu_cau_dong_bo_luc"):
        return "da_yeu_cau"
    if t.get("dong_bo_loi") or t.get("trang_thai") in ("loi", "het_han"):
        return "co_loi"
    return "on"


def dai_trang_thai(the: dict | None, nen_tang: str) -> dict:
    """Một ô của dải trạng thái đồng bộ (mọi người có quyền thấy): CHỈ ngày + giờ + trạng thái."""
    t = the or {}
    tt = tinh_trang_dong_bo(t)
    return {"nen_tang": nen_tang, "ten": TEN_NEN_TANG_QC.get(nen_tang, nen_tang),
            "tinh_trang": tt, "nhan": TEN_TINH_TRANG[tt], "so_den_ngay": t.get("so_den_ngay"),
            "dong_bo_luc": t.get("dong_bo_xong") or t.get("dong_bo_ok_luc"),
            "co_token": bool(t.get("co_token"))}


# ─── Điều khiển đồng bộ trên trang Quảng cáo (thiết kế lại 20/10/2026, chủ dự án: "rối, không biết đang
# đồng bộ TikTok hay Facebook") — mỗi nền tảng MỘT dòng: tên đầy đủ + một câu trạng thái + một nút tách
# "Đồng bộ ngay" (nhanh, 3 ngày) / "Đồng bộ lại 90 ngày" (day_du + nạp lại 90 ngày, chỉ quản trị viên). ───
NCC_NEN = {"tiktok_ads": "tiktok", "meta_ads": "meta"}
NEN_NCC = {v: k for k, v in NCC_NEN.items()}
TEN_DAY_DU = {"tiktok": "TikTok Ads", "meta": "Meta (Facebook) Ads"}
KIEU_DONG_BO = ("nhanh", "day_du")
CAU_TRONG_GIO = "trong giờ đồng bộ tự động (06:25–07:30) — bấm lại sau 07:30"


def _ngay_ngan(x) -> str:
    if isinstance(x, datetime.datetime):
        if x.tzinfo is None:
            x = x.replace(tzinfo=datetime.timezone.utc)
        return x.astimezone(VN).strftime("%d/%m")
    return x.strftime("%d/%m") if isinstance(x, datetime.date) else "—"


def ly_do_khong_dong_bo(the: dict | None, bay: datetime.datetime, kieu: str, *,
                        hien_ai: bool = False, trong_gio: bool | None = None) -> str | None:
    """Lý do KHÔNG ghi được yêu cầu `kieu` (nhanh | day_du) cho nền tảng này — None = được. Cùng luật
    nút và máy chủ: chưa kết nối / đang chạy / đang có yêu cầu (`kiem_yeu_cau`) / trong khung đồng bộ
    hằng ngày; nhanh còn giãn 15 phút sau lượt nhanh trước; day_du thiếu khoá giải mã."""
    t = the or {}
    if kieu == "day_du":
        ly = kiem_yeu_cau({**t, "nhanh_xong_luc": None, "dong_bo_kieu": None}, bay, hien_ai=hien_ai)
        if not ly and t.get("loi_khoa"):
            ly = f"khoá mã hoá chưa dùng được ({t['loi_khoa']})"
    else:
        ly = kiem_yeu_cau(t, bay, hien_ai=hien_ai)
    if not ly and (trong_gio_dong_bo(bay) if trong_gio is None else trong_gio):
        ly = CAU_TRONG_GIO
    return ly


def dong_dieu_khien(the: dict | None, nen_tang: str, bay: datetime.datetime, *,
                    hien_ai: bool = False, trong_gio: bool | None = None) -> dict:
    """Một dòng điều khiển đồng bộ (mọi chữ là chữ thường, không tiền, không số liệu): tên đầy đủ,
    MỘT câu trạng thái, lý do khoá từng nút, chi tiết phụ (gập)."""
    t = the or {}
    tt = tinh_trang_dong_bo(t)
    luc = t.get("dong_bo_xong") or t.get("dong_bo_ok_luc")
    if tt == "chua_ket_noi":
        cau = "Chưa kết nối — kết nối ở trang Quản trị"
    elif tt == "dang_chay":
        cau = f"Đang đồng bộ… (từ {_gio(t.get('dong_bo_bat_dau'))})"
    elif tt == "da_yeu_cau":
        cau = (f"Đã yêu cầu lúc {_gio(t.get('yeu_cau_dong_bo_luc'))}"
               + (" (lại 90 ngày)" if t.get("yeu_cau_kieu") == "day_du" else "")
               + " — bắt đầu trong ≤ 2 phút")
    elif tt == "co_loi":
        cau = "Lỗi lần trước — xem chi tiết"
    else:
        cau = f"Số đến {_ngay_ngan(t.get('so_den_ngay'))} · cập nhật {_ngay_ngan(luc)} {_gio(luc)}"
    loi = t.get("dong_bo_loi") or (t.get("loi_cuoi") if tt == "co_loi" else None)
    return {"nen_tang": nen_tang, "ncc": NEN_NCC[nen_tang], "ten": TEN_DAY_DU[nen_tang],
            "tinh_trang": tt, "nhan": TEN_TINH_TRANG[tt], "cau": cau,
            "ly_nhanh": ly_do_khong_dong_bo(t, bay, "nhanh", hien_ai=hien_ai, trong_gio=trong_gio),
            "ly_day_du": ly_do_khong_dong_bo(t, bay, "day_du", hien_ai=hien_ai,
                                             trong_gio=trong_gio),
            "so_den_ngay": t.get("so_den_ngay"), "dong_bo_luc": luc,
            "chi_tiet": {"so_tk": t.get("so_tk_thay"), "bat_dau": t.get("dong_bo_bat_dau"),
                         "xong": t.get("dong_bo_xong"), "so_dong": t.get("dong_bo_so_dong"),
                         "kieu": t.get("dong_bo_kieu"), "loi": loi},
            "co_token": bool(t.get("co_token"))}


def _utc(x):
    if isinstance(x, datetime.datetime) and x.tzinfo is None:
        return x.replace(tzinfo=datetime.timezone.utc)
    return x if isinstance(x, datetime.datetime) else None


def kiem_yeu_cau(the: dict | None, bay: datetime.datetime, gian_phut: int = GIAN_PHUT, *,
                 hien_ai: bool = False) -> str | None:
    """Có được ghi yêu cầu "Đồng bộ ngay" (nhanh) cho nền tảng này không. None = được; không thì câu
    trả lời cho người bấm: đang chạy / đang có yêu cầu / chưa hết thời gian giãn / chưa kết nối.
    Email người yêu cầu chỉ hiện khi `hien_ai` (quản trị viên); người khác chỉ thấy giờ.
    Giãn 15 phút tính từ mốc MUỘN NHẤT của: lượt nhanh gần nhất kết thúc (`nhanh_xong_luc`) và lượt
    nhanh gần nhất BẮT ĐẦU (`dong_bo_bat_dau` khi `dong_bo_kieu` = nhanh) — lượt bị giết giữa chừng
    (hết giờ, OOM, khởi động lại) không ghi được lúc xong nhưng vẫn bị tính giãn."""
    t = the or {}
    if not t.get("co_token"):
        return "chưa kết nối"
    if t.get("dang_dong_bo"):
        return f"đang chạy từ {_gio(t.get('dong_bo_bat_dau'))}"
    if t.get("yeu_cau_dong_bo_luc"):
        ai = t.get("yeu_cau_boi") if hien_ai else None
        return (f"đang có yêu cầu lúc {_gio(t.get('yeu_cau_dong_bo_luc'))}"
                + (f" ({ai})" if ai else ""))
    moc = [x for x in (_utc(t.get("nhanh_xong_luc")),
                       _utc(t.get("dong_bo_bat_dau")) if t.get("dong_bo_kieu") == "nhanh" else None)
           if x]
    if moc:
        cuoi = max(moc)
        duoc = cuoi + datetime.timedelta(minutes=gian_phut)
        if bay < duoc:
            return f"vừa đồng bộ lúc {_gio(cuoi)}, bấm lại được từ {_gio(duoc)}"
    return None


# ───────────────────────────── chỉ số tiền ─────────────────────────────
_TIEN_DUNG = frozenset({"spend", "cpm", "cpc", "cpp", "billed_cost", "cash_spend", "voucher_spend",
                        "cashback_coupon_spend", "tax_spend", "value_per_complete_payment",
                        "value_per_total_purchase", "campaign_budget", "budget", "balance",
                        "roas", "gia_tri_mua"})


def la_tien(ten: str) -> bool:
    """Chỉ số / cột mang số TIỀN (chủ dự án: chỉ người có quyền ở bên đó biết, qua Mark).
    Luật theo tên để chỉ số mới thêm vẫn bị chặn đúng: spend, cpm, cpc, cpp, cost_per_*,
    real_time_cost_per_*, *_value, *roas*, *budget*, *_spend, *_cost; Meta: action_values__*,
    purchase_roas__* (20/10/2026); cột riêng chi, gia_tri_mua_shop, roas_shop."""
    t = str(ten or "").lower()
    if t in _TIEN_DUNG or t in COT_TIEN or t in ("roas_shop", "doanh_thu_shop", "chi_phi"):
        return True
    if t.startswith(("chi_moi_", "chi_tren_")):   # chi phí suy ra của Mark (chi_moi_follow, …)
        return True
    return (t.startswith(("cost_", "real_time_cost_per_", "skan_cost_per_", "action_values"))
            or t.endswith(("_value", "_roas", "_spend", "_cost", "_budget"))
            or "budget" in t or "_roas" in t or "_value__" in t or "values__" in t)


#: Chỉ số KHÔNG cộng được qua ngày / đối tượng (tỉ lệ, trung bình, người duy nhất): tổng của chúng vô
#: nghĩa — Mark tính lại tỉ lệ từ tổng (CTR = click / hiển thị…), reach / frequency để trống.
_KHONG_CONG_DUNG = frozenset({"reach", "frequency", "ctr", "cpc", "cpm", "cpp", "result_rate",
                              "conversion_rate", "engagement_rate", "profile_visits_rate"})


def cong_duoc(ten: str) -> bool:
    """Chỉ số cộng được (số đếm, tiền): spend, impressions, clicks, actions__*, video_p25…, likes…
    Không cộng: reach, frequency, ctr/cpc/cpm/cpp, *rate*, cost_per_*, *average*/*avg*, *roas*,
    value_per_*, unique_*, *_per_user (soát 20/10/2026 trên tên TikTok + Meta)."""
    t = str(ten or "").lower()
    if t in _KHONG_CONG_DUNG:
        return False
    return not any(x in t for x in ("rate", "cost_per", "average", "avg", "roas", "frequency",
                                    "reach", "per_user", "value_per", "unique", "_ctr", "cpm",
                                    "cpc"))


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


def _chu_rieng(ten: str) -> list[str]:
    """Tên → các CHỮ hoa không dấu (tách theo mọi ký tự không phải chữ/số)."""
    s = unicodedata.normalize("NFKD", str(ten or "").replace("đ", "d").replace("Đ", "D"))
    return re.findall(r"[A-Z0-9]+", s.encode("ascii", "ignore").decode().upper())


def chu_tim(s: str) -> str:
    """Chữ để so khớp tên khi tra cứu: bỏ dấu (đ→d), chữ thường, bỏ khoảng trắng / ký hiệu — khớp
    đúng biểu thức `kho_qc._chuan_sql` phía Postgres."""
    return "".join(_chu_rieng(s)).lower()


def ben_tu_dong(ten: str) -> str | None:
    """Gán bên tự động khi thấy tài khoản lần đầu (chủ dự án chốt, áp cả TikTok lẫn Meta):
      • tên có chữ THAI đứng riêng (vd "THAI 1", "Thái") → None: chưa gán bên, chỉ quản trị viên
        thấy (20/10/2026: chưa làm HAPAS Thái Lan đợt này) — xét TRƯỚC, nghi ngờ thì hẹp;
      • tên có MATEMADE / MATE MADE / MADEMATE (không phân biệt hoa thường, khoảng trắng, dấu)
        → matemade;
      • còn lại → hapas."""
    if "THAI" in _chu_rieng(ten):
        return None
    m = ten_mau(ten)
    return "matemade" if ("MATEMADE" in m or "MADEMATE" in m) else "hapas"


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


def nhan_gia_tri(chieu: str, g: str) -> str:
    """Mã giá trị khán giả → nhãn hiện (TikTok: mã AGE_…, mã vùng số; Meta: tên vùng, nền tảng,
    "nền tảng/vị trí")."""
    if g in TEN_GIA_TRI:
        return TEN_GIA_TRI[g]
    if chieu == "province_id":
        return f"Mã vùng {g}" if g else "Không rõ"
    if chieu == "platform_position" and "/" in g:
        nt, vt = g.split("/", 1)
        return f"{TEN_GIA_TRI.get(nt, nt)} · {vt.replace('_', ' ')}"
    return g or "Không rõ"


def khan_gia(rows: list[dict]) -> dict:
    """Dòng qc_khan_gia (đã cộng theo chieu + gia_tri trên các tài khoản) → {chiều: [{nhan, …}]},
    mỗi chiều sắp theo hiển thị giảm dần, % hiển thị trong chiều."""
    ra: dict[str, list[dict]] = {c: [] for c in CHIEU_TAT_CA}
    gop: dict[tuple, dict] = {}
    for r in rows:
        c = r.get("chieu")
        if c in ra:
            g = str(r.get("gia_tri") if r.get("gia_tri") is not None else "")
            nhan = nhan_gia_tri(c, g)
            x = gop.get((c, nhan))
            if x is None:
                x = gop[(c, nhan)] = {**{k: r.get(k) for k in TEN_COT_SO}, "gia_tri": g,
                                      "nhan": nhan}
                ra[c].append(x)
            else:
                # Cùng nhãn (vd "Nữ" của TikTok + Meta, hoặc hai mã "Không rõ"): cộng chung một dòng.
                for k in TEN_COT_SO:
                    if r.get(k) is not None:
                        x[k] = (x.get(k) or 0) + r[k]
            x["tuong_tac"] = tuong_tac(x)
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
    # Meta (20/10/2026): mục tiêu ODAX + mục tiêu cũ còn trên chiến dịch cũ.
    "OUTCOME_AWARENESS": "Nhận biết", "OUTCOME_TRAFFIC": "Lưu lượng",
    "OUTCOME_ENGAGEMENT": "Tương tác", "OUTCOME_LEADS": "Khách tiềm năng",
    "OUTCOME_SALES": "Bán hàng", "OUTCOME_APP_PROMOTION": "Quảng bá ứng dụng",
    "BRAND_AWARENESS": "Nhận biết thương hiệu", "LINK_CLICKS": "Lượt bấm liên kết",
    "POST_ENGAGEMENT": "Tương tác bài viết", "PAGE_LIKES": "Thích Trang", "MESSAGES": "Tin nhắn",
    "PRODUCT_CATALOG_SALES": "Bán hàng theo danh mục", "STORE_VISITS": "Ghé cửa hàng",
    "EVENT_RESPONSES": "Phản hồi sự kiện", "LEAD_GENERATION_META": "Khách tiềm năng",
}

#: Ô KPI trang Quảng cáo: mã → (nhãn, ⓘ, là tiền, tô màu ▲/▼). Thứ tự = thứ tự hiện.
KPI_QC: dict[str, tuple[str, str, bool, bool]] = {
    "chi": ("Chi tiêu", "Tổng spend TikTok / Meta báo, theo tiền tệ của tài khoản, chưa VAT.",
            True, False),
    "hien_thi": ("Hiển thị", "", False, True),
    "view_video": ("View video", ("TikTok: lượt xem video (video_play_actions). Meta: lượt xem "
                                  "≥ 3 giây (action video_view)."), False, True),
    "engaged_view": ("Engaged view", ("TikTok: xem ≥ 6 giây hoặc có tương tác trong 1 ngày. Meta: "
                                      "ThruPlay (xem hết hoặc ≥ 15 giây)."), False, True),
    "reach": ("Reach", ("Cộng reach từng ngày: một người thấy quảng cáo nhiều ngày được đếm "
                        "nhiều lần — cao hơn reach duy nhất của cả kỳ trong trình quản lý quảng "
                        "cáo."), False, True),
    "tuong_tac": ("Tương tác", ("Thích + bình luận + chia sẻ trên quảng cáo (Meta: cảm xúc bài "
                                "viết + bình luận + chia sẻ)."), False, True),
    "follow": ("Follow", "TikTok: theo dõi kênh. Meta: lượt thích Trang (action like).",
               False, True),
    "vao_ho_so": ("Vào hồ sơ", "Lượt vào trang hồ sơ kênh từ quảng cáo (chỉ TikTok).", False, True),
    "gia_tri_mua_shop": ("Doanh thu Shop", ("TikTok: giá trị mua TikTok Shop. Meta: giá trị mua "
                                            "(purchase, mặc định phân bổ của Meta)."),
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


# ───────────────────────────── xuất Lark Sheet (20/10/2026) ─────────────────────────────
#: Chủ dự án 20/10/2026: trang Quảng cáo (chỉ quản trị viên) xuất số theo ĐÚNG bộ lọc trang thành một
#: Lark Sheet ba tab. Dashboard chỉ ghi yêu cầu (`kho_sheet_qc`); Mark dựng Sheet (`xuat_sheet_qc`).
#: Hai đầu cùng dùng các hàm thuần dưới đây — phạm vi và chỉ số suy ra không lệch nhau.
XUAT_TOI_DA_NGAY = 400          # = KHOANG_TOI_DA_NGAY của trang; CHECK của bảng yeu_cau_sheet_qc


def tk_xuat(q: dict | None, cac_tk: list[dict], ben: str, nen_tang: str,
            tk: str | None = None) -> list[dict]:
    """Tài khoản của phạm vi xuất — CÙNG luật trang /quang-cao: đúng nền tảng, đã duyệt, trong bên
    người này xem được; `tk` (nếu chọn) phải thuộc phạm vi đó. Ngoài phạm vi → [] (như không có)."""
    if nen_tang not in (*NEN_TANG_QC, TAT_CA) or not ben:
        return []
    ds = tk_trong_pham_vi(q, tk_dung(cac_tk, nen_tang), ben)
    if tk:
        ds = [t for t in ds if str(t.get("advertiser_id")) == str(tk)]
    return ds


def _chia_so(a, b, nhan: float = 1.0):
    if a is None or not b:
        return None
    return round(float(a) / float(b) * nhan, 4)


def hieu_qua(r: dict) -> dict:
    """Chỉ số SUY RA từ tổng (không cộng tỉ lệ — như trang): CPM, CPC, CTR (%), chi / 1.000 view,
    chi / follow, chi / kết quả, ROAS Shop, tương tác. Thiếu mẫu số → None (ô trống, không phải 0)."""
    chi = r.get("chi")
    return {"cpm": _chia_so(chi, r.get("hien_thi"), 1000),
            "cpc": _chia_so(chi, r.get("click")),
            "ctr": _chia_so(r.get("click"), r.get("hien_thi"), 100),
            "chi_tren_1000_view": _chia_so(chi, r.get("view_video"), 1000),
            "chi_moi_follow": _chia_so(chi, r.get("follow")),
            "chi_moi_ket_qua": _chia_so(chi, r.get("ket_qua")),
            "roas_shop": _chia_so(r.get("gia_tri_mua_shop"), chi),
            "tuong_tac": tuong_tac(r)}
