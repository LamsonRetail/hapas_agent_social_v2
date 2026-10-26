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
import json
import numbers
import re
import unicodedata

from dashboard import phan_quyen as PQ
from dashboard import vung_tiktok as VT

VN = datetime.timezone(datetime.timedelta(hours=7))

#: 101 chỉ số `report_integrated_get` nhận được (đo thật 19/10/2026 trên 16 tài khoản — một tên
#: lạ làm hỏng CẢ lượt gọi, nên chỉ xin trong danh sách này). Bỏ `currency`, `timezone` (thuộc tính
#: tài khoản, xin riêng qua advertiser_info_get). 3 tên TikTok từ chối: cost_per_engaged_view,
#: cost_per_1000_engagements, cost_per_messaging_total_conversation_tiktok_direct_message.
#: 22/10/2026 (chủ dự án): thêm `onsite_on_web_detail` = lượt xem trang chi tiết sản phẩm TikTok
#: Shop do quảng cáo (đo thật ở AUCTION_ADVERTISER + AUCTION_CAMPAIGN). 101 tên vẫn 3 lô × 45 (cấp
#: campaign 4 thuộc tính + 101 = 105, vẫn 3 lô) — không thêm lượt gọi. `onsite_on_web_detail_rate`
#: (= xem ÷ click, > 100%) KHÔNG xin. Tên TikTok TỪ CHỐI (đo 22/10/2026): TEN_TU_CHOI.
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
    "cost_per_onsite_on_web_cart", "onsite_on_web_detail", "onsite_shopping",
    "cost_per_onsite_shopping",
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
#: Tên TikTok từ chối (một tên làm hỏng cả lượt gọi) — đo 19/10 + 22/10/2026; bài thử canh không lọt
#: vào CHI_SO_HOP_LE / CHI_SO_AD.
TEN_TU_CHOI: tuple[str, ...] = (
    "cost_per_engaged_view", "cost_per_1000_engagements",
    "cost_per_messaging_total_conversation_tiktok_direct_message", "shop_page_view",
    "product_page_view", "total_product_detail_page_view", "onsite_shopping_page_view",
    "product_clicks", "onsite_product_view", "live_product_clicks_rate", "shop_visits",
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

#: 22/10/2026 (chủ dự án: "cái gì gây hiểu nhầm thì phải làm cho rõ ràng"): hai chuỗi "xem trang sản
#: phẩm" cho biểu đồ Theo ngày, cộng từ JSON `chi_so` của qc_tk_ngay. MỖI chuỗi thuộc MỘT nền tảng —
#: không gộp, không cộng chồng: TikTok đếm trong TikTok Shop, Meta đếm trên WEBSITE (pixel). Không
#: phải tiền. (khoá payload, khoá trong chi_so, nền tảng, nhãn, định nghĩa)
CHUOI_XEM_SP: tuple[tuple[str, str, str, str, str], ...] = (
    ("xem_sp_shop", "onsite_on_web_detail", "tiktok", "Xem trang SP TikTok Shop",
     "TikTok: lượt xem trang chi tiết sản phẩm trong TikTok Shop do quảng cáo mang lại (đếm "
     "lượt, không phải số người; không gồm trang chủ shop)"),
    ("xem_sp_web", "actions__view_content", "meta", "Xem SP website (Meta)",
     "Meta Pixel ViewContent: lượt xem trang sản phẩm trên WEBSITE sau quảng cáo — không phải "
     "Shop"),
)
TEN_CHUOI_XEM_SP = tuple(c[0] for c in CHUOI_XEM_SP)


def chuoi_xem_sp(ngay: list[dict]) -> list[dict]:
    """Chuỗi xem trang sản phẩm có số ≠ 0 trong `ngay` (dòng theo ngày của phạm vi đang xem) →
    [{ma, nen_tang, ten, dinh_nghia, tong}] cho nút chọn + chú thích ⓘ. Nền tảng không có trong
    phạm vi thì tổng = 0 → không có nút."""
    ra = []
    for ma, _k, nen, ten, dn in CHUOI_XEM_SP:
        tong = sum(int(r.get(ma) or 0) for r in ngay)
        if tong:
            ra.append({"ma": ma, "nen_tang": nen, "ten": ten, "dinh_nghia": dn, "tong": tong})
    return ra

#: Cấp quảng cáo: 1 lượt gọi ≤ 45 chỉ số. Tài khoản lớn có hàng nghìn ad chạy mỗi ngày (MATEMADE MKT
#: 7.599 ad / 30 ngày) — xin đủ 120 tên là 3 lượt gọi cho MỖI lô 100 ad × mỗi trang; nên cấp ad chỉ
#: xin bộ dưới đây (đủ cột kiểu riêng + tỉ lệ/chi phí chính), 1 lượt mỗi trang. Cấp tài khoản và
#: campaign xin đủ CHI_SO_HOP_LE. 22/10/2026: cấp ad đúng 7 + 38 = 45 tên — KHÔNG thêm
#: `onsite_on_web_detail` (tên thứ 46 = lô thứ hai cho mọi trang ad, gấp đôi lượt gọi).
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


#: "Đồng bộ lại 90 ngày" không nhận từ 00:00 tới 07:30 giờ VN (soát 20/10/2026): lượt nạp lại chạy nhiều giờ,
#: bắt đầu trước sáng là chồng lên lượt hằng ngày 06:30 / 06:45.
DAY_DU_TU = datetime.time(7, 30)
CAU_SANG = "để không chồng lượt tự động sáng (00:00–07:30) — bấm sau 07:30"


def ly_do_khong_dong_bo(the: dict | None, bay: datetime.datetime, kieu: str, *,
                        hien_ai: bool = False, la_quan_tri: bool = True,
                        bay_dv: datetime.datetime | None = None) -> str | None:
    """Lý do KHÔNG ghi được yêu cầu `kieu` (nhanh | day_du) cho nền tảng này — None = được. Cùng luật
    nút và máy chủ: chưa kết nối / đang chạy / đang có yêu cầu (`kiem_yeu_cau`) / khoá mã hoá chưa dùng
    được / trong khung đồng bộ hằng ngày; nhanh còn giãn 15 phút sau lượt nhanh trước; day_du chỉ quản
    trị viên và không nhận 00:00–07:30. `bay_dv`: đồng hồ của dịch vụ đồng bộ (khung giờ; bộ thử đặt
    giờ giả) — mặc định `bay`."""
    t = the or {}
    bay_dv = bay_dv or bay
    if kieu == "day_du" and not la_quan_tri:
        return "chỉ quản trị viên"
    if kieu == "day_du":
        ly = kiem_yeu_cau({**t, "nhanh_xong_luc": None, "dong_bo_kieu": None}, bay, hien_ai=hien_ai)
    else:
        ly = kiem_yeu_cau(t, bay, hien_ai=hien_ai)
    if not ly and t.get("loi_khoa"):
        ly = f"khoá mã hoá chưa dùng được ({t['loi_khoa']})"
    if not ly and trong_gio_dong_bo(bay_dv):
        ly = CAU_TRONG_GIO
    if not ly and kieu == "day_du":
        g = (bay_dv if bay_dv.tzinfo else bay_dv.replace(tzinfo=datetime.UTC)).astimezone(VN).time()
        if g < DAY_DU_TU:
            ly = CAU_SANG
    return ly


def dong_dieu_khien(the: dict | None, nen_tang: str, bay: datetime.datetime, *,
                    hien_ai: bool = False, la_quan_tri: bool = False,
                    bay_dv: datetime.datetime | None = None) -> dict:
    """Một dòng điều khiển đồng bộ (mọi chữ là chữ thường, không tiền, không số liệu): tên đầy đủ,
    MỘT câu trạng thái, lý do khoá từng nút, chi tiết phụ (gập). Lỗi chi tiết + số tài khoản chỉ quản
    trị viên (`la_quan_tri`); người khác thấy câu chung."""
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
        cau = "Lỗi lần trước — " + ("xem chi tiết" if la_quan_tri else "báo quản trị viên")
    else:
        cau = f"Số đến {_ngay_ngan(t.get('so_den_ngay'))} · cập nhật {_ngay_ngan(luc)} {_gio(luc)}"
    loi = t.get("dong_bo_loi") or (t.get("loi_cuoi") if tt == "co_loi" else None)
    if loi and not la_quan_tri:
        loi = "Lỗi lần trước — báo quản trị viên"
    return {"nen_tang": nen_tang, "ncc": NEN_NCC[nen_tang], "ten": TEN_DAY_DU[nen_tang],
            "tinh_trang": tt, "nhan": TEN_TINH_TRANG[tt], "cau": cau,
            "ly_nhanh": ly_do_khong_dong_bo(t, bay, "nhanh", hien_ai=hien_ai, bay_dv=bay_dv),
            "ly_day_du": ly_do_khong_dong_bo(t, bay, "day_du", hien_ai=hien_ai,
                                             la_quan_tri=la_quan_tri, bay_dv=bay_dv),
            "so_den_ngay": t.get("so_den_ngay"), "dong_bo_luc": luc,
            "chi_tiet": {"so_tk": t.get("so_tk_thay") if la_quan_tri else None,
                         "bat_dau": t.get("dong_bo_bat_dau"), "xong": t.get("dong_bo_xong"),
                         "so_dong": t.get("dong_bo_so_dong"), "kieu": t.get("dong_bo_kieu"),
                         "loi": loi},
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


# ───────────────────────────── doanh thu Shop / ROAS (tạm ẩn 22/10/2026) ──────────────────────
#: 22/10/2026 (chủ dự án): "Doanh thu Shop" (gia_tri_mua_shop = TikTok total_onsite_shopping_value,
#: Meta giá trị mua purchase) và ROAS suy ra từ nó đo KHÁC cách công ty tự tính → tạm gỡ khỏi
#: MỌI chỗ người xem số (trang + /api/qc, Lark Sheet, Mark). Dữ liệu vẫn lưu và đồng bộ như cũ
#: (COT_SO, COT_TIEN, BigQuery giữ nguyên). Bật lại: đổi HIEN_DOANH_THU = True — một chỗ duy nhất.
HIEN_DOANH_THU = False
CAU_KHONG_DOANH_THU = (
    "Doanh thu Shop và ROAS tạm KHÔNG báo (chủ dự án 22/10/2026): nền tảng quảng cáo đo khác cách "
    "công ty tự tính. Người hỏi thì nói rõ vậy và gợi ý xem báo cáo doanh thu của công ty — không "
    "nêu, không ước, không tự tính từ số khác.")


def la_doanh_thu(ten: str) -> bool:
    """Khoá mang doanh thu / ROAS: cột riêng gia_tri_mua_shop, roas_shop, roas; chỉ số thô TikTok
    *_value, value_per_*, *roas*; Meta action_values__*, purchase_roas__*."""
    t = str(ten or "").lower()
    if t in ("gia_tri_mua_shop", "gia_tri_mua", "doanh_thu_shop", "roas_shop", "roas", "revenue"):
        return True
    return ("roas" in t or t.endswith("_value") or "_value__" in t or "value_per_" in t
            or t.startswith("action_values"))


def loc_doanh_thu(x):
    """Bỏ mọi khoá doanh thu / ROAS (đệ quy) khi HIEN_DOANH_THU tắt. Không sửa bản gốc."""
    if HIEN_DOANH_THU:
        return x
    if isinstance(x, dict):
        return {k: loc_doanh_thu(v) for k, v in x.items() if not la_doanh_thu(k)}
    if isinstance(x, list):
        return [loc_doanh_thu(v) for v in x]
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


# ───────────────────────────── khoảng ngày + so sánh (25/10/2026) ─────────────────────────────
#: 25/10/2026 (chủ dự án): MỘT ô "Khoảng ngày" (khoảng nhanh + lịch hai tháng) và ô "So sánh với".
#: Mốc cuối mặc định của mọi khoảng nhanh = NGÀY CUỐI CÓ SỐ của phạm vi đang xem (kẹp ở hôm qua) —
#: đồng bộ trễ một hôm thì "30 ngày" vẫn là 30 ngày CÓ SỐ, không có đuôi 0 giả. `ss=` trên URL.
SO_SANH = {"truoc": "Kỳ liền trước", "thang_truoc": "Cùng kỳ tháng trước",
           "khong": "Không so sánh"}
SO_SANH_MAC_DINH = "truoc"


def doc_so_sanh(qp) -> str:
    """Tham số `ss` → một mã của SO_SANH; lạ / thiếu → kỳ liền trước (không báo lỗi, như `sap`)."""
    ss = str((qp or {}).get("ss") or "")
    return ss if ss in SO_SANH else SO_SANH_MAC_DINH


def _ngay(x) -> datetime.date | None:
    if x is None or x == "":
        return None
    if isinstance(x, datetime.datetime):
        return x.date()
    if isinstance(x, datetime.date):
        return x
    try:
        return datetime.date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def ngay_moc(ngay_cuoi, hom_qua: datetime.date) -> datetime.date:
    """Mốc cuối của khoảng mặc định / khoảng nhanh: ngày cuối có số, không quá hôm qua (hôm nay chưa
    hết ngày — số luôn thấp giả). Chưa có số nào → hôm qua."""
    d = _ngay(ngay_cuoi)
    return min(d, hom_qua) if d else hom_qua


def _cuoi_thang(d: datetime.date) -> datetime.date:
    sau = (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return sau - datetime.timedelta(days=1)


def lui_thang(d: datetime.date, n: int = 1) -> datetime.date:
    """Lùi `n` tháng, kẹp ngày vào tháng đích: 31/03 → 28/02 (29/02 năm nhuận), 31/05 → 30/04."""
    t = d.year * 12 + (d.month - 1) - n
    dau = datetime.date(t // 12, t % 12 + 1, 1)
    return dau.replace(day=min(d.day, _cuoi_thang(dau).day))


def ky_so_sanh(tu: datetime.date, den: datetime.date,
               ss: str = SO_SANH_MAC_DINH) -> tuple[datetime.date, datetime.date] | None:
    """Kỳ so sánh theo `ss`: `truoc` = kỳ liền trước cùng độ dài; `thang_truoc` = cùng ngày của
    tháng trước (kẹp ngày cuối tháng; `den` là NGÀY CUỐI THÁNG thì kỳ trước cũng hết tháng —
    01–28/02 so với trọn 01–31/01, không cụt 28/01); `khong` → None (không tính số kỳ trước)."""
    if ss == "khong":
        return None
    if ss == "thang_truoc":
        t1 = _cuoi_thang(lui_thang(den)) if den == _cuoi_thang(den) else lui_thang(den)
        return min(lui_thang(tu), t1), t1
    return khoang_truoc(tu, den)


def _ngan(d: datetime.date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def khoang_nhanh(moc: datetime.date, hom_qua: datetime.date) -> list[dict]:
    """Khoảng nhanh của ô "Khoảng ngày", MỌI khoảng hết ở `moc` (ngày cuối có số, `ngay_moc`) —
    trừ "Tháng trước" (trọn tháng trước tháng của mốc). Khoảng một ngày tên "Hôm qua" khi mốc là
    hôm qua, không thì "Ngày DD/MM" (đồng bộ trễ: không gọi ngày khác là hôm qua)."""
    def lui(n: int) -> datetime.date:
        return moc - datetime.timedelta(days=n - 1)
    dau_thang = moc.replace(day=1)
    cuoi_truoc = dau_thang - datetime.timedelta(days=1)
    ds = [("1", "Hôm qua" if moc == hom_qua else f"Ngày {_ngan(moc)}", moc, moc),
          ("7", "7 ngày", lui(7), moc), ("14", "14 ngày", lui(14), moc),
          ("30", "30 ngày", lui(30), moc), ("thang_nay", "Tháng này", dau_thang, moc),
          ("thang_truoc", "Tháng trước", cuoi_truoc.replace(day=1), cuoi_truoc),
          ("90", "90 ngày", lui(90), moc)]
    return [{"ma": m, "nhan": n, "tu": a.isoformat(), "den": b.isoformat()} for m, n, a, b in ds]


# ─── Theo ngày → theo tuần / tháng (25/10/2026): ≤ 31 ngày theo ngày, ≤ 120 theo tuần (ISO, thứ
# Hai đầu tuần), dài hơn theo tháng. Máy chủ gộp (một phép tính, có bộ thử); qc.js chỉ chọn. ───
DON_VI_BD = {"ngay": "Ngày", "tuan": "Tuần", "thang": "Tháng"}
#: Không cộng được qua ngày (người duy nhất) — ô gộp để None, không cộng sai.
_KHONG_CONG_KY = frozenset({"reach"})


def don_vi_mac_dinh(so_ngay: int) -> str:
    return "ngay" if so_ngay <= 31 else ("tuan" if so_ngay <= 120 else "thang")


def don_vi_co(tu: datetime.date, den: datetime.date) -> list[str]:
    """Các đơn vị đáng chọn: tuần khi > 7 ngày, tháng khi khoảng sang ≥ 2 tháng — luôn gồm đơn vị
    mặc định."""
    so = (den - tu).days + 1
    co = {"ngay", don_vi_mac_dinh(so)}
    if so > 7:
        co.add("tuan")
    if (tu.year, tu.month) != (den.year, den.month):
        co.add("thang")
    return [k for k in DON_VI_BD if k in co]


def _dau_ky(d: datetime.date, don_vi: str) -> datetime.date:
    if don_vi == "tuan":
        return d - datetime.timedelta(days=d.weekday())
    if don_vi == "thang":
        return d.replace(day=1)
    return d


def gop_ky(rows: list[dict], don_vi: str, tu: datetime.date, den: datetime.date) -> list[dict]:
    """Dòng theo ngày (`ngay` ISO + cột số, có thể có `nen_tang`) → dòng theo tuần / tháng: CỘNG cột
    số (tỉ lệ không có ở đây — trang tính lại từ tổng), `reach` để None. Mỗi kỳ cắt theo [tu, den]:
    `ngay` / `den` = ngày đầu / cuối của kỳ TRONG khoảng, `so_ngay` = số ngày đó (tuần đầu / cuối có
    thể thiếu ngày — chú giải ghi rõ). Nhãn "Tuần DD/MM" (ngày đầu trong khoảng) / "Tháng MM/YYYY".
    Có `nen_tang` thì gộp riêng từng nền tảng. Giữ thứ tự thời gian."""
    if don_vi not in ("tuan", "thang"):
        return [dict(r) for r in rows]
    nhom: dict = {}
    for r in rows:
        d = _ngay(r.get("ngay"))
        if d is None or not tu <= d <= den:
            continue
        dau = _dau_ky(d, don_vi)
        k = (dau, r.get("nen_tang"))
        x = nhom.get(k)
        if x is None:
            a = max(dau, tu)
            b = min(dau + datetime.timedelta(days=6) if don_vi == "tuan" else _cuoi_thang(dau), den)
            x = nhom[k] = {"ngay": a.isoformat(), "den": b.isoformat(), "so_ngay": (b - a).days + 1,
                           "nhan": (f"Tuần {_ngan(a)}" if don_vi == "tuan"
                                    else f"Tháng {dau.month:02d}/{dau.year}")}
            if r.get("nen_tang") is not None:
                x["nen_tang"] = r["nen_tang"]
        for c, v in r.items():
            if c in ("ngay", "nen_tang", "den", "so_ngay", "nhan"):
                continue
            if c in _KHONG_CONG_KY:
                x[c] = None
            elif isinstance(v, numbers.Number) and not isinstance(v, bool):
                x[c] = (x.get(c) or 0) + v
    return [nhom[k] for k in sorted(nhom, key=lambda k: (k[0], str(k[1] or "")))]


SAP_XEP = {"chi": "chi", "hien_thi": "hien_thi", "view": "view_video", "follow": "follow"}


def cot_sap(sap: str | None, co_tien: bool) -> str:
    """Tham số `sap` → cột sắp xếp bảng top. Người không xem tiền không sắp theo chi (về hien_thi)."""
    sap = sap if sap in SAP_XEP else ("chi" if co_tien else "hien_thi")
    if sap == "chi" and not co_tien:
        sap = "hien_thi"
    return sap


#: Bảng chiến dịch / quảng cáo trang Quảng cáo (22/10/2026, MKT: "lọc theo tên, campaign và sort theo
#: các chỉ số"): mã `sap` → nhãn. Mọi cột của bảng đều sắp được; tỉ lệ (CPM, CTR, ROAS) tính lại từ
#: tổng của dòng ở SQL (`kho_qc.qc_bang`). Chi / CPM / ROAS là chỉ số tiền — chỉ người xem tiền.
SAP_BANG: dict[str, str] = {"chi": "Chi", "hien_thi": "Hiển thị", "cpm": "CPM", "click": "Click",
                            "ctr": "CTR", "view": "View video", "tuong_tac": "Tương tác",
                            "follow": "Follow", "roas": "ROAS"}
SAP_BANG_TIEN = frozenset({"chi", "cpm", "roas"})
if not HIEN_DOANH_THU:      # 22/10/2026: ROAS tạm ẩn — URL cũ `sap=roas` về sắp mặc định
    SAP_BANG.pop("roas", None)
#: CPM / CTR chỉ xếp hạng dòng có ≥ 1.000 hiển thị (dòng 3 hiển thị CTR 33% không phải "tốt nhất");
#: dòng dưới ngưỡng xuống cuối, vẫn hiện số. Giải thích ở nút "i" của khối.
NGUONG_TI_LE = 1000
TIM_TOI_DA = 100
#: 22/10/2026 (chủ dự án): bỏ ô "Số dòng" — mỗi bảng 20 dòng một trang, phân trang ở MÁY CHỦ
#: (LIMIT/OFFSET trong `kho_qc.qc_bang`); trang của bảng chiến dịch ở tham số `tc`, quảng cáo ở `ta`.
#: Tham số `so` cũ trong URL bị lờ đi (không lỗi).
DONG_MOI_TRANG = 20
TRANG_TOI_DA = 1_000_000        # chặn OFFSET khổng lồ từ URL gõ tay (vẫn kẹp về trang cuối)
#: Chọn nhiều tài khoản (22/10/2026): tối đa chừng này mã trong URL / yêu cầu Sheet (= trigger
#: `chuan_yeu_cau_sheet_qc`). Không chọn = mọi tài khoản trong phạm vi.
TK_TOI_DA = 200
CHIEU_BANG = ("giam", "tang")
_MA_TK = re.compile(r"(act_)?[0-9]{1,30}")


def so_trang(x) -> int:
    """Tham số trang (`tc` / `ta`) → số trang ≥ 1; sai / thiếu → 1 (không báo lỗi)."""
    s = str(x or "").strip()
    if not s.isdecimal() or len(s) > 7:
        return 1
    return max(1, min(int(s), TRANG_TOI_DA))


def loc_bang(qp, co_tien: bool) -> dict:
    """Tham số lọc / sắp bảng chiến dịch + quảng cáo → giá trị đã kiểm (sai thì về mặc định, không
    báo lỗi — như `cot_sap`). `sap` tiền với người không xem tiền → hien_thi (không lộ thứ hạng chi).
      tim   — chữ tìm trong tên chiến dịch / quảng cáo (≤ 100 ký tự; so khớp bỏ dấu `chu_tim`)
      cd    — mã chiến dịch: bảng chiến dịch chỉ dòng đó, bảng quảng cáo chỉ quảng cáo của nó
      sap   — mã trong SAP_BANG; chieu — giam | tang
      tc/ta — trang bảng chiến dịch / quảng cáo (22/10/2026, thay "Số dòng"; máy chủ kẹp về trang
              cuối). Bộ nghe Sheet (`xuat_sheet_qc`) dùng lại hàm này cho cột tim/cd/sap/chieu của
              yêu cầu — cùng một luật kiểm hai đầu."""
    sap = str(qp.get("sap") or "")
    if sap not in SAP_BANG or (sap in SAP_BANG_TIEN and not co_tien):
        sap = "chi" if co_tien else "hien_thi"
    chieu = "tang" if qp.get("chieu") == "tang" else "giam"
    tim = " ".join(str(qp.get("tim") or "").split())[:TIM_TOI_DA]
    cd = str(qp.get("cd") or "").strip()
    if len(cd) > 64 or not re.fullmatch(r"[0-9A-Za-z_-]*", cd):
        cd = ""
    return {"tim": tim, "mau": chu_tim(tim) if tim else "", "cd": cd, "sap": sap,
            "chieu": chieu, "tc": so_trang(qp.get("tc")), "ta": so_trang(qp.get("ta"))}


#: 23/10/2026 (MKT: "lọc tên campaign" ở Bộ lọc đầu trang): lọc CẢ TRANG theo tên chiến dịch — KPI,
#: biểu đồ, TikTok và Meta, hai bảng, kênh đăng, Lark Sheet chỉ tính chiến dịch có tên khớp (Khán giả
#: theo tài khoản nên không theo được — trang ghi rõ). Dấu phẩy / chấm phẩy tách nhiều từ khoá.
TACH_TEN_CD = re.compile(r"[,;]")
#: 23/10/2026 (MKT, bản 2 — "như Meta Ads Manager": "chứa tất cả từ khoá · chứa một trong các từ
#: khoá · không chứa bất kì từ khoá nào"): ba danh sách từ khoá, các dòng AND với nhau. (mã, tham số
#: URL / biểu mẫu, nhãn ngắn ở thẻ, nhãn dòng ở bảng chọn). Tham số `ten_cd` cũ (PR #101, dấu phẩy =
#: hoặc) = `cd_mot` — link cũ vẫn chạy.
LOAI_TEN_CD = (("co", "cd_co", "chứa tất cả", "Chứa tất cả từ khoá"),
               ("mot", "cd_mot", "chứa một trong", "Chứa một trong các từ khoá"),
               ("khong", "cd_khong", "không chứa", "Không chứa từ khoá nào"))
TU_KHOA_TOI_DA = 10             # từ khoá mỗi dòng
TU_KHOA_DAI_TOI_DA = 60         # ký tự mỗi từ khoá
#: Chuỗi JSON lưu ở `yeu_cau_sheet_qc.ten_cd` (= trigger `chuan_yeu_cau_sheet_qc`, schema.sql).
TEN_CD_CHUOI_TOI_DA = 600


def _gia_tri(qp, k: str) -> list:
    """Mọi giá trị của tham số `k` (QueryParams / FormData: lặp lại; dict: chuỗi hoặc danh sách)."""
    if qp is None:
        return []
    if hasattr(qp, "getlist"):
        return list(qp.getlist(k))
    v = qp.get(k)
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def chuoi_ten_cd(loc: dict) -> str | None:
    """Ba danh sách → chuỗi JSON chuẩn `{"co":[..],"mot":[..],"khong":[..]}` (cột `ten_cd` của yêu
    cầu Sheet); không điều kiện nào → None."""
    if not any(loc.get(k) for k, *_ in LOAI_TEN_CD):
        return None
    return json.dumps({k: list(loc.get(k) or []) for k, *_ in LOAI_TEN_CD}, ensure_ascii=False,
                      separators=(",", ":"))


def mo_ta_ten_cd(loc: dict) -> str:
    """Các điều kiện bằng chữ: "chứa tất cả: LOYALTY, 20/10 · không chứa: reach" ("" = không lọc)."""
    return " · ".join(f"{ngan}: {', '.join(loc[k])}" for k, _, ngan, _ in LOAI_TEN_CD
                      if loc.get(k))


def loc_ten_cd(qp) -> dict:
    """Tham số lọc tên chiến dịch cấp trang → {"co", "mot", "khong": từ khoá đã gọn (chữ người gõ),
    "maus": {cùng khoá: từ khoá qua `chu_tim`}, "co_loc", "khong_khop", "cat", "chu"}.
      • `cd_co` / `cd_mot` / `cd_khong` lặp lại được; dấu phẩy / chấm phẩy trong một giá trị cũng
        tách. `ten_cd` cũ (dấu phẩy = hoặc) gộp vào `cd_mot`.
      • Trần: ≤ TU_KHOA_TOI_DA từ khoá mỗi dòng, mỗi từ khoá ≤ TU_KHOA_DAI_TOI_DA ký tự, chuỗi JSON
        (`chuoi_ten_cd`) ≤ TEN_CD_CHUOI_TOI_DA — vượt thì cắt lặng, `cat` = True (nút i ghi trần).
      • Từ khoá mà `chu_tim` rút về rỗng (chữ Thái, "…") bị bỏ khi so khớp (vẫn hiện như người gõ).
        `co` / `mot` có từ khoá mà mọi từ khoá bị bỏ → `khong_khop` = KHÔNG khớp gì (cùng luật `tim`,
        không lờ đi); `khong` bị bỏ hết thì chỉ là không ràng buộc.
    Bộ nghe Sheet (`xuat_sheet_qc`) + tool Mark dùng lại hàm này (qua `doc_ten_cd`)."""
    cat = False
    tho: dict[str, list[str]] = {}
    for loai, ts, *_ in LOAI_TEN_CD:
        vao = _gia_tri(qp, ts) + (_gia_tri(qp, "ten_cd") if loai == "mot" else [])
        ds: list[str] = []
        thay: set[str] = set()
        for v in vao:
            for cum in TACH_TEN_CD.split(str(v if v is not None else "")):
                kw = " ".join(cum.split())
                if not kw:
                    continue
                if len(kw) > TU_KHOA_DAI_TOI_DA:
                    kw, cat = kw[:TU_KHOA_DAI_TOI_DA].rstrip(), True
                khoa = chu_tim(kw) or kw.casefold()
                if khoa in thay:
                    continue
                if len(ds) >= TU_KHOA_TOI_DA:
                    cat = True
                    continue
                thay.add(khoa)
                ds.append(kw)
        tho[loai] = ds
    # Tổng chuỗi lưu: bớt từ khoá cuối (không chứa → một trong → tất cả) tới khi vừa.
    while len(chuoi_ten_cd(tho) or "") > TEN_CD_CHUOI_TOI_DA:
        cat = True
        next(tho[k] for k in ("khong", "mot", "co") if tho[k]).pop()
    maus = {k: list(dict.fromkeys(m for m in map(chu_tim, ds) if m)) for k, ds in tho.items()}
    return {**tho, "maus": maus, "co_loc": any(tho.values()), "cat": cat,
            "khong_khop": bool((tho["co"] and not maus["co"]) or (tho["mot"] and not maus["mot"])),
            "chu": mo_ta_ten_cd(tho)}


def khop_ten_cd(ten: str | None, loc: dict) -> bool:
    """Tên chiến dịch (TÊN MỚI NHẤT trong kỳ) khớp bộ lọc `loc_ten_cd`: chứa MỌI từ khoá `co`, ít nhất
    MỘT từ khoá `mot` (rỗng = không ràng buộc), KHÔNG từ khoá `khong` nào — so bằng `chu_tim` (bỏ dấu,
    bỏ khoảng trắng / _ / /). Dòng có từ khoá mà không còn từ Latin nào → không khớp."""
    if loc.get("khong_khop"):
        return False
    t = chu_tim(ten or "")
    m = loc.get("maus") or {}
    return (all(k in t for k in m.get("co") or ())
            and (not loc.get("mot") or any(k in t for k in m.get("mot") or ()))
            and not any(k in t for k in m.get("khong") or ()))


def doc_ten_cd(s) -> dict:
    """Cột `ten_cd` đã lưu → tham số cho `loc_ten_cd`: JSON `{"co","mot","khong"}` (bản 2) hoặc chữ
    thường (PR #101: dấu phẩy = hoặc → `cd_mot`). NULL / rỗng → không lọc."""
    s = str(s or "").strip()
    if s.startswith("{"):
        try:
            d = json.loads(s)
        except ValueError:
            d = None
        if isinstance(d, dict):
            ra = {}
            for loai, ts, *_ in LOAI_TEN_CD:
                v = d.get(loai)
                v = [v] if isinstance(v, str) else (v if isinstance(v, list) else [])
                ra[ts] = [str(x) for x in v if isinstance(x, (str, int, float))]
            return ra
    return {"ten_cd": s}


def tham_ten_cd(loc: dict | None) -> dict:
    """Tham số URL giữ bộ lọc (liên kết, ô ẩn): `cd_co` / `cd_mot` / `cd_khong` lặp lại; `ten_cd` cũ
    luôn bỏ (đã gộp)."""
    loc = loc or {}
    return {"ten_cd": "", **{ts: list(loc.get(k) or []) for k, ts, *_ in LOAI_TEN_CD}}


_TACH_DOAN = re.compile(r"[_|\[\]()]+|\s[-–·]\s")


def goi_y_ten_cd(ds: list[dict], q: str, n: int = 10, n_tu: int = 5) -> dict:
    """Gợi ý ô từ khoá (`/api/qc/ten-cd`): `ds` = tên chiến dịch trong kỳ, mới nhất trước
    (`kho_qc.ten_cd_trong_ky`). -> {"ten": ≤ n tên khác nhau chứa `q` (bỏ dấu), mới nhất trước,
    "tu_khoa": ≤ n_tu đoạn tên hay gặp (tách theo _ | - ngoặc) chứa `q`, nhiều nhất trước}."""
    mau = chu_tim(q)
    if not mau:
        return {"q": q, "ten": [], "tu_khoa": []}
    ten: list[str] = []
    dem: dict[str, list] = {}
    for r in ds:
        t = " ".join(str(r.get("ten") or "").split())
        if not t:
            continue
        if mau in chu_tim(t) and t not in ten and len(ten) < n:
            ten.append(t)
        for doan in _TACH_DOAN.split(t):
            doan = " ".join(doan.split())
            k = chu_tim(doan)
            if len(k) >= 2 and mau in k and len(doan) <= TU_KHOA_DAI_TOI_DA:
                dem.setdefault(k, [doan, 0])[1] += 1
    tu = [d for d, _ in sorted(dem.values(), key=lambda x: -x[1]) if d not in ten][:n_tu]
    return {"q": q, "ten": ten, "tu_khoa": tu}


def ten_gan_nhat(ds: list[dict], loc: dict, n: int = 5) -> list[str]:
    """Không chiến dịch nào khớp → ≤ n tên THẬT trong kỳ gần nhất với các từ khoá đã gõ (chứa nhiều từ
    khoá `co` + `mot` nhất, rồi nhiều chữ lẻ của chúng nhất; mới nhất trước khi bằng điểm; bỏ tên chứa
    từ khoá `khong`). Không tên nào chung chữ nào → []."""
    maus = loc.get("maus") or {}
    kw = [*maus.get("co", []), *maus.get("mot", [])]
    le = list(dict.fromkeys(m for k in (*loc.get("co", []), *loc.get("mot", []))
                            for m in map(chu_tim, re.split(r"[\s_/|.\-]+", k)) if len(m) >= 2))
    diem: list[tuple] = []
    thay: set[str] = set()
    for i, r in enumerate(ds):
        t = " ".join(str(r.get("ten") or "").split())
        c = chu_tim(t)
        if not t or t in thay or any(k in c for k in maus.get("khong", [])):
            continue
        thay.add(t)
        a, b = sum(k in c for k in kw), sum(m in c for m in le)
        if a or b:
            diem.append((-a, -b, i, t))
    return [t for *_, t in sorted(diem)[:n]]


def o_trang(trang: int, so_trang_: int) -> list[int | None]:
    """Các ô của thanh trang kiểu cổ điển (None = "…"): ≤ 8 trang hiện đủ; gần đầu
    1 2 3 4 5 6 … cuối; gần cuối 1 … (6 trang cuối); giữa 1 … t-1 t t+1 … cuối."""
    n = max(1, int(so_trang_))
    t = max(1, min(int(trang), n))
    if n <= 8:
        return list(range(1, n + 1))
    if t <= 4:
        return [*range(1, 7), None, n]
    if t >= n - 3:
        return [1, None, *range(n - 5, n + 1)]
    return [1, None, t - 1, t, t + 1, None, n]


def tk_chon(gia_tri, tk_ben: list[dict]) -> tuple[list[str], list[str]]:
    """Tham số `tk` (lặp lại được; một `tk=` cũ vẫn dùng được) → (mã đã chọn TRONG phạm vi theo thứ
    tự danh sách, mã ngoài phạm vi / sai dạng). Trùng bỏ; quá TK_TOI_DA mã → phần dư tính là sai.
    Chọn đủ mọi tài khoản = không chọn (mọi tài khoản) — URL / yêu cầu Sheet gọn."""
    if isinstance(gia_tri, str):
        gia_tri = [gia_tri]
    vao: list[str] = []
    for x in gia_tri or ():
        s = str(x or "").strip()
        if s and s not in vao:
            vao.append(s)
    co = {str(t["advertiser_id"]) for t in tk_ben}
    ngoai = [s for s in vao if s not in co or not _MA_TK.fullmatch(s)]
    ngoai += [s for s in vao if s not in ngoai][TK_TOI_DA:]
    giu = set(vao) - set(ngoai)
    chon = [str(t["advertiser_id"]) for t in tk_ben if str(t["advertiser_id"]) in giu]
    if chon and len(chon) == len(co):
        chon = []
    return chon, ngoai


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
        # 26/10/2026 (chủ dự án): tên tỉnh/thành từ mã GeoNames (`vung_tiktok`); mã lạ giữ "Mã vùng".
        return VT.ten_tinh(g) or (f"Mã vùng {g}" if g else "Không rõ")
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


# ───────────────────────────── Khán giả theo chiến dịch (26/10/2026) ─────────────────────────────
#: Chủ dự án 26/10/2026: khối Khán giả theo Bộ lọc đầu trang (bên, tài khoản, nền tảng, TÊN CHIẾN DỊCH)
#: + ô chọn NHIỀU chiến dịch bằng ô tích trong khối (tham số URL `kg_cd`, lặp lại: kg_cd=a&kg_cd=b;
#: một `kg_cd` đơn như bản cũ vẫn dùng được). Không lọc tên, không chọn → số cấp TÀI KHOẢN
#: (qc_khan_gia — đúng, reach không đếm trùng giữa chiến dịch); có lọc tên hoặc chọn → số cấp
#: CHIẾN DỊCH (qc_khan_gia_cd), cộng các chiến dịch khớp / đã chọn.
THAM_KG_CD = "kg_cd"
#: Cùng luật với mã chiến dịch `cd` của bảng (`loc_bang`): chữ/số/_/-, ≤ 64 ký tự.
_MA_CD = re.compile(r"[0-9A-Za-z_-]{1,64}")
#: Số chiến dịch tối đa trong ô chọn (số khán giả mặc định vẫn cộng MỌI chiến dịch khớp).
KG_CD_O_CHON = 500
#: Số mã `kg_cd` nhận tối đa (đã hợp lệ, không trùng) — chặn URL dài bất thường.
KG_CD_TOI_DA = 300


def doc_kg_cd(qp) -> list[str]:
    """Mã chiến dịch đã tích ở ô chọn trong khối Khán giả: `kg_cd` lặp lại (hoặc một giá trị như
    bản cũ). Mã sai dạng bỏ, trùng bỏ, giữ thứ tự, tối đa KG_CD_TOI_DA. Chỉ dùng để so với danh sách
    đã đọc trong phạm vi người xem — mã ngoài danh sách bị lờ (không bao giờ chạm kho)."""
    if qp is None:
        return []
    tho = qp.getlist(THAM_KG_CD) if hasattr(qp, "getlist") else qp.get(THAM_KG_CD)
    if tho is None or tho == "":
        return []
    if not isinstance(tho, (list, tuple)):
        tho = [tho]
    ra: list[str] = []
    for x in tho:
        s = str(x or "").strip()
        if _MA_CD.fullmatch(s) and s not in ra:
            ra.append(s)
            if len(ra) >= KG_CD_TOI_DA:
                break
    return ra


def ds_kg_cd(ds: list[dict], loc: dict, co_tien: bool) -> list[dict]:
    """Chiến dịch có số khán giả (`kho_qc.ds_cd_khan_gia`) khớp lọc tên cấp trang `loc`
    (`loc_ten_cd`; không lọc = mọi chiến dịch), xếp chi giảm dần — hoặc hiển thị khi người xem
    không được xem tiền (thứ tự không lộ chi tiêu)."""
    if loc.get("co_loc"):
        ds = [] if loc.get("khong_khop") else [x for x in ds if khop_ten_cd(x.get("ten"), loc)]
    khoa = "chi" if co_tien else "hien_thi"
    return sorted(ds, key=lambda x: (-(x.get(khoa) or 0), -(x.get("hien_thi") or 0),
                                     str(x.get("campaign_id"))))


def bo_reach(rows: list[dict]) -> list[dict]:
    """Reach cộng qua nhiều chiến dịch là đếm trùng người → NULL (hiển thị, chi, bấm vẫn cộng)."""
    return [{**r, "reach": None} for r in rows]


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
    phu = tuple(k for k, v in KPI_QC.items() if k not in chinh and (co_tien or not v[2])
                and (HIEN_DOANH_THU or not la_doanh_thu(k)))   # 22/10/2026: ẩn doanh thu / ROAS
    return chinh, phu


# ───────────────────────────── xuất Lark Sheet (20/10/2026) ─────────────────────────────
#: Chủ dự án 20/10/2026: trang Quảng cáo (chỉ quản trị viên) xuất số theo ĐÚNG bộ lọc trang thành một
#: Lark Sheet ba tab. Dashboard chỉ ghi yêu cầu (`kho_sheet_qc`); Mark dựng Sheet (`xuat_sheet_qc`).
#: Hai đầu cùng dùng các hàm thuần dưới đây — phạm vi và chỉ số suy ra không lệch nhau.
XUAT_TOI_DA_NGAY = 400          # = KHOANG_TOI_DA_NGAY của trang; CHECK của bảng yeu_cau_sheet_qc


def tk_xuat(q: dict | None, cac_tk: list[dict], ben: str, nen_tang: str,
            tk: str | list[str] | tuple[str, ...] | None = None) -> list[dict]:
    """Tài khoản của phạm vi xuất — CÙNG luật trang /quang-cao: đúng nền tảng, đã duyệt, trong bên
    người này xem được; `tk` (nếu chọn) phải thuộc phạm vi đó. Ngoài phạm vi → [] (như không có).
    22/10/2026: `tk` nhận MỘT mã (dòng cũ, cột tk) hoặc DANH SÁCH mã (cột tk_ds) — trả phần giao
    với phạm vi; nơi gọi so độ dài để biết có mã nào rơi khỏi phạm vi."""
    if nen_tang not in (*NEN_TANG_QC, TAT_CA) or not ben:
        return []
    ds = tk_trong_pham_vi(q, tk_dung(cac_tk, nen_tang), ben)
    if tk:
        chon = {str(tk)} if isinstance(tk, str) else {str(x) for x in tk}
        ds = [t for t in ds if str(t.get("advertiser_id")) in chon]
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
