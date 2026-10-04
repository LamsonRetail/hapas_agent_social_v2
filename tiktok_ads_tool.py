"""Tool `tiktok_top_ads`: TOP quảng cáo TikTok của một thị trường (TikTok Creative Center).

Vì sao cần: Mark chỉ có Meta Ad Library (`fb_ads_library`). Câu hỏi "đối thủ chạy ads
TikTok gì", "ads ngành túi xách trên TikTok đang ra sao" chưa có nguồn. Creative Center
mục Top Ads là trang CÔNG KHAI, có dữ liệu Việt Nam (04/10/2026: 30 ngày VN → 229 ads),
lọc được theo từ khoá, ngành, mục tiêu chiến dịch, ngôn ngữ, và trả CTR, likes, mức chi
phí, link MP4.

Vì sao là TOOL RIÊNG đặt cạnh `fb_ads_library`, không phải chế độ của nó:
  • `fb_ads_library` miễn phí, chạy bằng trình duyệt, nằm trong `_SAFE_EXACT` (chỉ đọc).
    Gắn thêm một chế độ TỐN TIỀN và GHI Lark Sheet vào đó là cho việc cần `write_data`
    lọt qua danh sách chỉ-đọc của `lsr_policy`.
  • Tool riêng có mục policy riêng (`write_data`), có luật hỏi "Chạy nhé?" như mọi tool
    tốn tiền, và có công tắc riêng trên console khi platform thêm (xem lsr_policy).

Nguồn: endpoint JSON của Creative Center đòi header ký, nên đi qua actor Apify — KHÔNG tự
dựng chữ ký hay lách chống bot.
  • Chính: `azzouzana~tiktok-creative-center-top-ads-scraper` — 0,001 USD/ad, +0,002 USD
    khi lấy chi tiết (landing page). Lọc được NGÀNH CON (túi, trang sức…).
  • Dự phòng: `lexis-solutions~tiktok-top-ads-scraper` — 0,0025 USD mỗi GB khởi động (mặc
    định 4 GB = 0,01 USD) + 0,004 USD/ad; chỉ lọc ngành CHA, không có mục tiêu "Tương
    tác". BẮT BUỘC có `startUrls` hoặc `keyword`, thiếu là FAILED mà vẫn mất phí khởi động.
  • Không dùng `doliz` (đòi cookie đăng nhập).

Đo thật 04/10/2026 (VN, 30 ngày, Apparel & Accessories, xếp CTR, xin 10):
  • Chính: 5 ads trong 16 giây, 0,015 USD. Tài khoản Apify của Mark là gói FREE (hạn mức
    10 USD/tháng) nên actor CẮT ở 5 ads/lượt, statusMessage "free accounts have limited
    data extraction" — muốn nhiều hơn phải nâng gói Apify. `brandName` rỗng ở cả 5 ads,
    `ctrTier`/`keywords`/`tags` rỗng; `industryName` là ngành CON (Women's Clothing);
    `ctr` là số 0,34–0,64 (điểm TikTok xếp, không phải CTR thật); `costScore` 0–2.
  • Dự phòng (1 GB): chậm, ~3 ads trong 110 giây rồi bị huỷ vì hết giờ, 0,0145 USD. Cùng
    ads với actor chính; `brandName` cũng rỗng; có thêm comments/shares.

Mọi lượt chạy đi qua `apify_tool._call` với `nen_tang="tiktok"`: chịu trần USD/bài của
TikTok trên console (Năng lực → Quét mạng xã hội; `bat_tiktok`=0 thì không chạy), hạn chót
+ huỷ run khi quá giờ, che token trong lỗi; chi phí thật vào sổ `chi_phi_tool`.
"""
from __future__ import annotations

import collections
import contextvars
import datetime
import os
import re
import time

import apify_tool as A
import chi_phi_tool
import memory_store
import nganh_tiktok

from tools.registry import registry, tool_error, tool_result  # type: ignore

ACTOR_CHINH = "azzouzana~tiktok-creative-center-top-ads-scraper"
ACTOR_DU_PHONG = "lexis-solutions~tiktok-top-ads-scraper"
_GIA_AD = 0.001             # azzouzana, mỗi ad
_GIA_CHI_TIET = 0.002       # azzouzana, mỗi ad khi `extractDetails`
_GIA_DP_KHOI_DONG = 0.01    # lexis, 0,0025 USD/GB × 4 GB mặc định
_GIA_DP_AD = 0.004          # lexis, mỗi ad (gói FREE 0,00399)
_BIEN = 0.9                 # mỗi lượt chỉ xin tới 90% trần USD
_MAC_DINH_ADS = 20
_TOI_DA_ADS = 200           # 30 ngày VN chỉ có ~229 ads; gọn trong một lượt trả lời
_GOI_FREE_CHINH = 5         # azzouzana cắt 5 ad/lượt khi tài khoản Apify là gói Free
# Còn ít hơn chừng này giây sau khi actor chính hỏng thì không chạy dự phòng.
_GIAY_DU_PHONG = 40
# Lỗi mà actor dự phòng cũng sẽ gặp y hệt — không chạy dự phòng, đỡ mất phí khởi động.
_KHONG_DU_PHONG = {"HET_TIEN_THANG", "NGHEN_DONG_THOI", "DA_HUY"}
# statusMessage thật 04/10: "⚠️ To ensure service stability, free accounts have limited
# data extraction. Upgrade to a paid plan to unlock full access 👉 https://apify.com/pricing"
_DAU_HIEU_GOI = re.compile(r"(?i)free account|free tier|trial|limited data|upgrade|quota")

_VUNG = {"US", "CA", "MX", "BR", "GB", "DE", "FR", "IT", "ES", "NL", "PL", "SE", "TR", "SA",
         "AE", "AU", "JP", "KR", "ID", "TH", "VN", "MY", "PH", "SG"}
_KY = ("7", "30", "180")
# sap_xep → orderBy (hai actor dùng chung giá trị).
_SAP_XEP = {"ctr": "ctr", "like": "like", "tiep_can": "impression", "cvr": "cvr",
            "xem_6s": "play_6s_rate", "mac_dinh": "for_you"}
# muc_tieu → (azzouzana, lexis, tên tiếng Việt). Lexis không có "Tương tác".
_MUC_TIEU = {
    "luu_luong": ("campaign_objective_traffic", "1", "Lưu lượng truy cập"),
    "cai_app": ("campaign_objective_app_install", "2", "Cài ứng dụng"),
    "chuyen_doi": ("campaign_objective_conversion", "3", "Chuyển đổi"),
    "xem_video": ("campaign_objective_video_view", "4", "Lượt xem video"),
    "tiep_can": ("campaign_objective_reach", "5", "Tiếp cận"),
    "khach_tiem_nang": ("campaign_objective_lead_generation", "8", "Khách hàng tiềm năng"),
    "ban_san_pham": ("campaign_objective_product_sales", "15", "Bán sản phẩm"),
    "tuong_tac": ("campaign_objective_engagement", "", "Tương tác"),
}
# `objectiveKey` actor trả về (mã số hoặc tên campaign_objective_*) → tiếng Việt.
_TEN_MUC_TIEU = {**{v[1]: v[2] for v in _MUC_TIEU.values() if v[1]},
                 **{v[0]: v[2] for v in _MUC_TIEU.values()}}
_NGON_NGU = {"vi", "en", "th", "id", "ja", "zh", "pt"}

_HEADER = ["Hạng", "Tiêu đề / caption", "Brand", "Ngành", "Mục tiêu",
           "CTR (mức tương đối)", "Likes", "Mức chi phí (tương đối)", "Kỳ",
           "Link video MP4 (hết hạn sau 24–48 giờ)", "Landing page",
           "Trang ad trên Creative Center", "Nguồn"]


def _so(v, mac_dinh: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return mac_dinh


def _co(v, mac_dinh: bool) -> bool:
    if v is None or v == "":
        return mac_dinh
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "co", "có")
    return bool(v)


def _gia_chinh(n: int, chi_tiet: bool) -> float:
    return n * (_GIA_AD + (_GIA_CHI_TIET if chi_tiet else 0.0))


def _gia_du_phong(n: int) -> float:
    return _GIA_DP_KHOI_DONG + n * _GIA_DP_AD


# ───────────────────────────── đầu vào actor ─────────────────────────────
def _payload_chinh(bo: dict) -> dict:
    p = {"countryCode": bo["vung"], "period": bo["ky"], "orderBy": bo["sap_xep"],
         "maxItems": bo["n"], "extractDetails": bo["chi_tiet"]}
    if bo["tu_khoa"]:
        p["keyword"] = bo["tu_khoa"]
    if bo["nganh"]:
        p["industry"] = bo["nganh"]["nhan_actor"]
    if bo["muc_tieu"]:
        p["objective"] = _MUC_TIEU[bo["muc_tieu"]][0]
    if bo["ngon_ngu"]:
        p["adLanguage"] = bo["ngon_ngu"]
    return p


def _payload_du_phong(bo: dict, n: int) -> dict:
    """Lexis đòi `startUrls` hoặc `keyword`; bộ lọc áp lên trang danh sách."""
    p: dict = {"country": [bo["vung"]], "period": bo["ky"], "orderBy": bo["sap_xep"],
               "maxItems": n, "proxyConfiguration": {"useApifyProxy": True}}
    if bo["tu_khoa"]:
        p["keyword"] = bo["tu_khoa"]
    else:
        p["startUrls"] = [{"url": "https://ads.tiktok.com/business/creativecenter/inspiration/"
                                  f"topads/pc/en?period={bo['ky']}&region={bo['vung']}"}]
    if bo["nganh"]:
        p["industry"] = [bo["nganh"]["nhom"]]
    if bo["muc_tieu"] and _MUC_TIEU[bo["muc_tieu"]][1]:
        p["objective"] = [_MUC_TIEU[bo["muc_tieu"]][1]]
    if bo["ngon_ngu"]:
        p["adLanguage"] = [bo["ngon_ngu"]]
    return p


# ───────────────────────────── chuẩn hoá đầu ra ─────────────────────────────
def _dau(d: dict, *ten, mac_dinh=None):
    for t in ten:
        v = d.get(t)
        if v not in (None, "", [], {}):
            return v
    return mac_dinh


def _link_video(it: dict) -> str:
    v = _dau(it, "videoUrl720p", "videoUrl540p", "videoUrl360p")
    if v:
        return str(v)
    urls = it.get("videoUrls")
    if isinstance(urls, dict) and urls:
        for k in ("720p", "540p", "480p", "360p"):
            if urls.get(k):
                return str(urls[k])
        return str(next(iter(urls.values())))
    return ""


def _muc_tieu_ra(it: dict) -> str:
    k = _dau(it, "objectiveKey", "filterObjective")
    if not k and isinstance(it.get("objectives"), list) and it["objectives"]:
        o = it["objectives"][0]
        k = (o.get("label") or o.get("value")) if isinstance(o, dict) else o
    k = str(k or "")
    return _TEN_MUC_TIEU.get(k, k)


def _ctr_ra(it: dict) -> str:
    hang = str(it.get("ctrTier") or "").replace("_", " ").strip()
    diem = it.get("ctr")
    if hang and diem not in (None, ""):
        return f"{hang} (điểm {diem})"
    return hang or ("" if diem in (None, "") else f"điểm {diem}")


def _chuan(it: dict, nguon: str, bo: dict, hang: int) -> dict | None:
    if not isinstance(it, dict) or it.get("error"):
        return None
    ma = str(_dau(it, "adId", "id", "materialId", mac_dinh="") or "")
    tieu_de = " ".join(str(_dau(it, "adTitle", "title", mac_dinh="") or "").split())
    if not ma and not tieu_de:
        return None
    ky = str(_dau(it, "periodDays", mac_dinh=bo["ky"]))
    link_cc = str(_dau(it, "detailUrl", mac_dinh="") or "")
    if not link_cc and ma:
        link_cc = (f"https://ads.tiktok.com/business/creativecenter/topads/{ma}/pc/en"
                   f"?countryCode={bo['vung']}&period={ky}")
    nganh = str(_dau(it, "industryName", "industryLabel", mac_dinh="") or "") \
        or nganh_tiktok.ten_nhom_tu_key(it.get("industryKey"))
    chi_phi = _dau(it, "costScore", "cost")
    return {
        "hang": _dau(it, "rank", mac_dinh=hang), "id": ma, "tieu_de": tieu_de[:500],
        "brand": str(_dau(it, "brandName", mac_dinh="") or ""),
        "nganh": nganh, "muc_tieu": _muc_tieu_ra(it), "ctr": _ctr_ra(it),
        "likes": _dau(it, "likes", mac_dinh=None),
        "chi_phi": "" if chi_phi in (None, "") else f"mức {chi_phi}",
        "ky": f"{ky} ngày", "video": _link_video(it),
        "landing": str(_dau(it, "landingPageUrl", "landingPage", mac_dinh="") or ""),
        "link_cc": link_cc, "spark": bool(it.get("isSparkAd")), "nguon": nguon,
    }


def _dong(a: dict) -> list:
    return [a["hang"], a["tieu_de"], a["brand"], a["nganh"], a["muc_tieu"], a["ctr"],
            "" if a["likes"] is None else a["likes"], a["chi_phi"], a["ky"], a["video"],
            a["landing"], a["link_cc"], a["nguon"]]


def _tom_tat(ads: list[dict]) -> dict:
    brand = collections.Counter(a["brand"] for a in ads if a["brand"])
    nganh = collections.Counter(a["nganh"] for a in ads if a["nganh"])
    muc = collections.Counter(a["muc_tieu"] for a in ads if a["muc_tieu"])
    return {
        "so_ads": len(ads), "so_brand": len(brand),
        "khong_ro_brand": sum(1 for a in ads if not a["brand"]),
        "brand_nhieu_ads_nhat": [{"brand": b, "so_ads": n} for b, n in brand.most_common(5)],
        "theo_nganh": dict(nganh.most_common(8)), "theo_muc_tieu": dict(muc.most_common(8)),
        "so_spark_ads": sum(1 for a in ads if a["spark"]),
        "so_co_landing_page": sum(1 for a in ads if a["landing"]),
        "so_co_link_video": sum(1 for a in ads if a["video"]),
    }


# ───────────────────────────── chạy actor ─────────────────────────────
def _trong_han(han_run: float, so_run: list, actor: str, payload: dict, n: int) -> list:
    """Một lượt actor dưới hạn chót + sổ run của apify_tool (gọi trong copy_context)."""
    A._SO_RUN.set(so_run)
    A._HAN_CHOT.set(han_run)
    return A._call(actor, payload, n, nen_tang="tiktok")


def _can_du_phong(loi: Exception | None, items: list, meta: dict | None) -> bool:
    if loi is not None:
        return getattr(loi, "ma", "LOI") not in _KHONG_DU_PHONG
    # Rỗng mà actor báo giới hạn gói (hết lượt Free trong ngày…) là HỎNG, không phải
    # "không có ad nào".
    return not items and bool(_DAU_HIEU_GOI.search(str((meta or {}).get("statusMessage") or "")))


SCHEMA = {
    "name": "tiktok_top_ads",
    "description": (
        "TOP QUẢNG CÁO TIKTOK của một thị trường (mặc định VN) từ mục Top Ads của TikTok "
        "Creative Center: tìm theo `tu_khoa` (brand/sản phẩm/chữ trong caption) và/hoặc "
        "`nganh` (vd 'thời trang', 'túi xách', 'trang sức', 'nước hoa'), xếp theo CTR hoặc "
        "likes, kỳ 7/30/180 ngày. Ra Lark Sheet: tiêu đề, brand, ngành, mục tiêu, CTR, likes, "
        "mức chi phí, kỳ, link video, landing page. Dùng khi hỏi 'đối thủ/ngành X chạy ads "
        "TikTok gì', 'ads TikTok nào đang hiệu quả'. Quảng cáo trên Facebook/Instagram/"
        "Threads thì dùng `fb_ads_library`.\n"
        "TOOL TỐN TIỀN: gọi TRƯỚC với `chi_uoc_tinh`=true (miễn phí, không chạy), nêu phạm "
        "vi (từ khoá/ngành, kỳ, xếp theo, số ads) rồi kết bằng \"Chạy nhé?\"; đồng ý mới "
        "gọi lại bỏ `chi_uoc_tinh`.\n"
        "KHI TRẢ LỜI: đây là tập ads TikTok XẾP HẠNG HIỆU QUẢ CAO NHẤT, KHÔNG phải mọi ad "
        "một brand đang chạy — không có brand trong kết quả KHÔNG có nghĩa là brand không "
        "chạy ads. CTR và chi phí là MỨC TƯƠNG ĐỐI của TikTok, KHÔNG phải số tiền chi thật "
        "hay CTR thật — đừng quy ra ngân sách. Link video MP4 hết hạn sau 24–48 giờ (trang "
        "Creative Center thì còn). TikTok thường KHÔNG trả tên brand (đo 04/10: rỗng cả 5 "
        "ads VN) — đừng đoán brand, chỉ đọc từ caption/landing page và nói là suy ra. "
        "Nói số ads, brand nổi bật, ngành, mục tiêu từ `tom_tat`; "
        "`nguon` là dự phòng hoặc `canh_bao` có nội dung thì nói ra. Gửi NGUYÊN `sheet_url`."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tu_khoa": {"type": "string", "description": (
                "Brand hoặc sản phẩm, vd 'Charles & Keith', 'túi da'. Là ô tìm kiếm của "
                "Creative Center (khớp chữ trong ad), không phải tên tài khoản chính xác.")},
            "nganh": {"type": "string", "description": (
                "Ngành bằng lời người dùng: 'thời trang', 'túi xách', 'trang sức', 'đồng hồ', "
                "'nước hoa', 'mỹ phẩm', 'chăm sóc da', 'mẹ và bé', 'đồ ăn'…")},
            "ky_ngay": {"type": "string", "enum": list(_KY),
                        "description": "Kỳ 7, 30 (mặc định) hoặc 180 ngày."},
            "sap_xep": {"type": "string", "enum": list(_SAP_XEP), "description": (
                "ctr (mặc định), like, tiep_can, cvr, xem_6s, mac_dinh (thứ tự For You "
                "của TikTok).")},
            "muc_tieu": {"type": "string", "enum": list(_MUC_TIEU),
                         "description": "Lọc theo mục tiêu chiến dịch. Bỏ trống = mọi mục tiêu."},
            "ngon_ngu": {"type": "string", "enum": sorted(_NGON_NGU),
                         "description": "Ngôn ngữ chữ trong ad, vd 'vi'. Bỏ trống = mọi ngôn ngữ."},
            "country": {"type": "string", "description": "Mã nước, mặc định VN."},
            "so_ads": {"type": "integer", "description": (
                f"Số ads lấy (mặc định {_MAC_DINH_ADS}, tối đa {_TOI_DA_ADS} và trần TikTok "
                "trên console).")},
            "chi_tiet": {"type": "boolean", "description": (
                "Lấy landing page và hạng CTR (mặc định true, thêm 0,002 USD/ad).")},
            "chi_uoc_tinh": {"type": "boolean", "description": (
                "true = CHỈ ước tính chi phí, không chạy, không tốn tiền. Gọi thế này trước.")},
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
        },
        "required": [],
    },
}


def _doc_tham_so(args: dict) -> tuple[dict | None, str]:
    """args → bộ tham số đã kiểm, hoặc (None, lỗi)."""
    vung = (str(args.get("country") or "VN").strip() or "VN").upper()
    if vung not in _VUNG:
        return None, f"Top Ads chưa có thị trường {vung}. Có: {', '.join(sorted(_VUNG))}."
    nganh = None
    if str(args.get("nganh") or "").strip():
        nganh = nganh_tiktok.tim(args["nganh"])
        if not nganh:
            return None, (f"Chưa nhận ra ngành '{args['nganh']}'. Ngành lọc được: "
                          f"{nganh_tiktok.danh_sach()}. Hoặc tìm bằng `tu_khoa`.")
    ky = str(args.get("ky_ngay") or "30").strip()
    ky = ky if ky in _KY else "30"
    sx = str(args.get("sap_xep") or "ctr").strip().lower()
    muc = str(args.get("muc_tieu") or "").strip().lower()
    nn = str(args.get("ngon_ngu") or "").strip().lower()
    return {
        "vung": vung, "ky": ky, "nganh": nganh,
        "tu_khoa": " ".join(str(args.get("tu_khoa") or "").split())[:100],
        "sap_xep": _SAP_XEP.get(sx, "ctr"), "muc_tieu": muc if muc in _MUC_TIEU else "",
        "ngon_ngu": nn if nn in _NGON_NGU else "",
        "chi_tiet": _co(args.get("chi_tiet"), True),
    }, ""


def _pham_vi(bo: dict) -> str:
    phan = [f"thị trường {bo['vung']}", f"{bo['ky']} ngày"]
    if bo["tu_khoa"]:
        phan.append(f"từ khoá '{bo['tu_khoa']}'")
    if bo["nganh"]:
        phan.append(f"ngành {bo['nganh']['ten']}")
    if bo["muc_tieu"]:
        phan.append(f"mục tiêu {_MUC_TIEU[bo['muc_tieu']][2]}")
    if bo["ngon_ngu"]:
        phan.append(f"ngôn ngữ {bo['ngon_ngu']}")
    sx = next(k for k, v in _SAP_XEP.items() if v == bo["sap_xep"])
    phan.append(f"xếp theo {sx}")
    return " · ".join(phan)


def _handle(args: dict, **_kwargs) -> str:
    bo, loi_vao = _doc_tham_so(args)
    if bo is None:
        return tool_error(loi_vao)
    tran_bai, tran_usd, bat = A._tran_nen_tang("tiktok")
    if not bat:
        return tool_error(A._ly_do_tat("tiktok") + " — Top Ads TikTok cũng không chạy.")
    xin = _so(args.get("so_ads"), _MAC_DINH_ADS, 1, _TOI_DA_ADS)
    gia_1 = _gia_chinh(1, bo["chi_tiet"])
    n = max(1, min(xin, tran_bai, int(_BIEN * tran_usd / gia_1)))
    bo["n"] = n
    canh_bao: list[str] = []
    if n < xin:
        canh_bao.append(f"Xin {xin} ads nhưng trần TikTok trên console ({tran_bai} bài, "
                        f"{A._usd_vn(tran_usd)} USD/lượt) chỉ cho {n} ads.")
    if bo["nganh"] and bo["nganh"]["la_nganh_con"]:
        canh_bao.append(f"Nếu phải dùng nguồn dự phòng thì chỉ lọc được ngành cha "
                        f"{bo['nganh']['ten_nhom']} (rộng hơn {bo['nganh']['ten']}).")
    if bo["muc_tieu"] == "tuong_tac":
        canh_bao.append("Nguồn dự phòng không lọc được mục tiêu Tương tác.")
    # Dự phòng chỉ xin số ads vừa trần USD của nó (đắt hơn ~1,3 lần).
    n_dp = max(1, min(n, int((_BIEN * tran_usd - _GIA_DP_KHOI_DONG) / _GIA_DP_AD)))
    est = _gia_chinh(n, bo["chi_tiet"])
    est_toi_da = est + _gia_du_phong(n_dp)
    pham_vi = _pham_vi(bo)

    if _co(args.get("chi_uoc_tinh"), False):
        hm = A._han_muc_thang()
        con = round(hm["con_lai"], 2) if hm else None
        return tool_result(
            success=True, chi_uoc_tinh=True, da_chay=False, pham_vi=pham_vi, so_ads=n,
            uoc_tinh_chi_phi_usd=round(est, 3),
            uoc_tinh_toi_da_usd=round(est_toi_da, 3),
            ngan_sach_thang_con_usd=con, vuot_ngan_sach=bool(hm and con is not None and con < est),
            canh_bao=canh_bao or None,
            note=("CHƯA chạy, không tốn tiền. Nêu phạm vi + số ads + ước tính USD (tối đa "
                  "nếu phải dùng nguồn dự phòng) rồi kết bằng \"Chạy nhé?\" và DỪNG. "
                  "Đồng ý mới gọi lại bỏ `chi_uoc_tinh`."
                  + (" Ngân sách Apify tháng không đủ — nói rõ, chưa chạy được."
                     if hm and con is not None and con < est else "")),
        )

    bat_dau = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=5)
    t0 = time.monotonic()
    han = t0 + A._TOOL_DEADLINE
    han_run = han - A._DU_PHONG_HUY
    so_run: list = []
    actors = [ACTOR_CHINH]
    nguon, loi_chinh, items = "chính", None, []
    try:
        items = contextvars.copy_context().run(
            _trong_han, han_run, so_run, ACTOR_CHINH, _payload_chinh(bo), n)
    except Exception as e:  # noqa: BLE001
        loi_chinh = e
    meta = so_run[-1] if so_run else None
    loi: dict[str, str] = {}
    if _can_du_phong(loi_chinh, items, meta):
        ly_do = (A._che_token(f"{getattr(loi_chinh, 'ma', type(loi_chinh).__name__)}: "
                              f"{loi_chinh}") if loi_chinh is not None
                 else "trả 0 ads kèm báo giới hạn gói: "
                      + A._che_token(str((meta or {}).get("statusMessage") or ""))[:150])
        loi["nguon_chinh"] = ly_do[:250]
        if han - time.monotonic() < _GIAY_DU_PHONG:
            loi["du_phong"] = "không còn đủ thời gian của lượt để chạy nguồn dự phòng"
        else:
            actors.append(ACTOR_DU_PHONG)
            try:
                items = contextvars.copy_context().run(
                    _trong_han, han_run, so_run, ACTOR_DU_PHONG, _payload_du_phong(bo, n_dp),
                    n_dp)
                nguon = "dự phòng"
            except Exception as e:  # noqa: BLE001
                items = []
                loi["du_phong"] = A._che_token(
                    f"{getattr(e, 'ma', type(e).__name__)}: {e}")[:250]
    elif loi_chinh is not None:
        loi["nguon_chinh"] = A._che_token(
            f"{getattr(loi_chinh, 'ma', type(loi_chinh).__name__)}: {loi_chinh}")[:250]
    elif (len(items) < n
          and _DAU_HIEU_GOI.search(str((meta or {}).get("statusMessage") or ""))):
        canh_bao.append(
            f"Chỉ lấy được {len(items)}/{n} ads: tài khoản Apify đang ở gói Free nên actor cắt "
            f"còn khoảng {_GOI_FREE_CHINH} ads mỗi lượt. Muốn nhiều hơn thì chủ tài khoản "
            f"nâng gói Apify; chạy lại cũng chỉ ra cùng {_GOI_FREE_CHINH} ads đầu bảng.")
    # Run bị huỷ vì hết giờ / dừng giữa chừng: `_call` trả phần đã có (sổ run được đặt) —
    # phải nói ra, không trình bày như đủ.
    cuoi = so_run[-1] if so_run else {}
    if items and cuoi.get("ma") in ("QUA_GIO", "OK_MOT_PHAN"):
        canh_bao.append(f"Nguồn {nguon} dừng giữa chừng ({cuoi['ma']}): "
                        + A._che_token(str(cuoi.get("ly_do") or ""))[:200])

    est_that = est + (_gia_du_phong(n_dp) if ACTOR_DU_PHONG in actors else 0.0)
    thuc = A._chi_phi_thuc(actors, bat_dau, est_that)
    chi_phi_tool.ghi(queries=[f"top ads TikTok: {pham_vi}"], platforms=["tiktok"],
                     date_range=f"{bo['ky']} ngày gần nhất", thuc=thuc, est=est_that)

    ten_nguon = ACTOR_CHINH if nguon == "chính" else ACTOR_DU_PHONG
    ads = [a for a in (_chuan(it, ten_nguon.split("~")[0], bo, i + 1)
                       for i, it in enumerate(items or [])) if a]
    if not ads and loi:
        return tool_error("Không lấy được Top Ads TikTok: " + "; ".join(
            f"{k}: {v}" for k, v in loi.items()))

    url, granted = None, False
    title = (str(args.get("title") or "").strip()
             or f"Top Ads TikTok {bo['vung']} · {pham_vi}"[:90]
             + f" · {datetime.datetime.now(A._VN_TZ):%d-%m-%Y}")
    if ads:
        try:
            tok, url = A._create_sheet(title)
            A._write_values(tok, A._first_sheet_id(tok), [list(_HEADER)] + [_dong(a) for a in ads])
            sender = memory_store.get_current_sender()
            granted = A._grant(tok, sender) if sender else False
        except Exception as e:  # noqa: BLE001
            loi["sheet"] = A._che_token(f"{type(e).__name__}: {e}")[:250]

    return tool_result(
        success=not (set(loi) - {"nguon_chinh"}), pham_vi=pham_vi,
        nguon=("Top Ads của TikTok Creative Center qua actor "
               + ("chính" if nguon == "chính" else "DỰ PHÒNG (nguồn chính hỏng)")),
        tom_tat=_tom_tat(ads),
        top=[{"hang": a["hang"], "tieu_de": a["tieu_de"][:120], "brand": a["brand"],
              "nganh": a["nganh"], "ctr": a["ctr"], "likes": a["likes"],
              "link_cc": a["link_cc"]} for a in ads[:5]],
        so_ads_xin=n, canh_bao=canh_bao or None, loi=loi or None,
        sheet_url=url, granted=granted, title=title,
        uoc_tinh_chi_phi_usd=round(est_that, 3),
        chi_phi_thuc_usd=thuc["usd"] if thuc and thuc.get("so_run") else None,
        chi_phi=A._dong_chi_phi(thuc, est_that), giay=round(time.monotonic() - t0, 1),
        note=("Tập ads XẾP HẠNG HIỆU QUẢ CAO của TikTok, không phải mọi ad brand đang chạy. "
              "CTR / chi phí là mức tương đối, không phải số tiền thật. Link video MP4 hết "
              "hạn sau 24–48 giờ.")
             + (" Không có ad nào khớp bộ lọc — thử bỏ bớt lọc hoặc kỳ 180 ngày."
                if not ads else ""),
    )


def _available() -> bool:
    return bool(os.environ.get("APIFY_TOKEN", "").strip())


try:
    registry.register(
        name="tiktok_top_ads", toolset="social", schema=SCHEMA, handler=_handle,
        check_fn=_available, requires_env=[], is_async=False,
        description="Top quảng cáo TikTok theo từ khoá/ngành (TikTok Creative Center)",
        emoji="\U0001f3ac", override=True,
    )
except Exception as e:  # noqa: BLE001
    print(f"[tiktok_ads_tool] register warning: {e}")
