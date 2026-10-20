"""Kết nối Meta Ads (Facebook / Instagram) + đồng bộ số quảng cáo vào kho `lang_nghe` (20/10/2026).

Chủ dự án chốt 20/10/2026: thêm Meta vào đúng đường ống quảng cáo TikTok đang chạy — cùng bảng
(`tk_quang_cao.nen_tang = 'meta'`, `qc_*`), cùng luật quyền / tiền, cùng trang Quảng cáo (chỉ quản trị
viên) và hỏi đáp Mark. Không LLM: chỉ GET Graph API, đổi số và upsert. Không phụ thuộc mã runtime của
Mark (chạy trong venv dashboard bằng user lang_nghe_web); kiến thức đọc số lấy từ `meta_ads_tool.py`.

KẾT NỐI
  • Token người dùng hệ thống (system user) CHỈ ĐỌC, đo thật 20/10/2026: `me` = "mark_ads_reader",
    quyền đã cấp read_insights, ads_read, public_profile; `me/adaccounts` 20 tài khoản (VND,
    Asia/Ho_Chi_Minh). Token loại này không hết hạn → `ket_noi_ngoai.loai = 'api_token'`.
  • Không dùng MCP chính thức của Meta (xin ads_management). Lưu token (`luu_token`) chỉ khi quyền
    đã cấp nằm TRỌN trong `QUYEN_CHO_PHEP` — có ads_management, business_management hay bất kỳ quyền
    *_manage*/publish nào là TỪ CHỐI, không lưu.

AN TOÀN (chỉ đọc — kiểm TRƯỚC khi gửi, `kiem_url`)
  • Chỉ GET; chỉ https://graph.facebook.com/<phiên bản>/ + đường trong danh sách: me,
    me/adaccounts, me/permissions, act_<số>, act_<số>/insights, act_<số>/campaigns, act_<số>/ads.
    Trang sau (`paging.next`) phải cùng đường của trang đầu (riêng me/… Meta đổi thành <id số>/…).
  • Tham số đổi phương thức (`method`, `_method`, `batch`…) bị chặn — Graph API nhận `?method=delete`
    trên GET. Token đi bằng header Authorization, `access_token` trong URL trang sau bị bỏ.
  • Không theo chuyển hướng. Token mã hoá AES-256-GCM như TikTok (`tiktok_ads.ma_hoa`, cùng khoá
    TIKTOK_KHOA_MA_HOA, AAD "meta_ads" — bản mã TikTok/Meta không tráo được). Lỗi qua `gon_loi`.

ĐỒNG BỘ (`python -m dashboard.meta_ads dong-bo`, bộ hẹn giờ 06:45 giờ VN; nút "Đồng bộ ngay" chỉ ghi
cờ — bộ hẹn giờ 2 phút chạy `dong-bo --chi-khi-yeu-cau`; dashboard KHÔNG chạy đồng bộ)
  • Thấy tài khoản (me/adaccounts) → tk_quang_cao; CHỈ tài khoản quản trị viên đã DUYỆT (`duyet`,
    thay MARK_META_AD_ACCOUNT_IDS; nhập kèm token bằng `nhap-token`) mới được đọc số.
  • Insights cấp account / campaign / ad, time_increment=1 (Meta chỉ trả dòng có phân phối); lần đầu
    nạp lùi 90 ngày (cửa sổ 30 ngày, mới trước), sau đó mỗi ngày đọc lại 7 ngày (phân bổ chuyển đổi
    đổi trễ). Meta báo "quá nhiều dữ liệu" thì chia đôi cửa sổ (tới 1 ngày) — chỉ GET, không job
    async (POST). Ghi theo TỪNG TRANG (không giữ cả cửa sổ trong bộ nhớ, MemoryMax 512M).
  • Khán giả mỗi tuần, cửa sổ 30 ngày: age, gender, region, publisher_platform,
    publisher_platform+platform_position.
  • Giới hạn tần suất (mã 4, 17, 32, 613, 80000–80014, HTTP 429): nghỉ rồi thử lại; tải header
    x-business-use-case-usage / x-ad-account-usage ≥ 85% thì nghỉ trước lượt sau.

ÁNH XẠ CHỈ SỐ (cột kiểu riêng; MỌI trường / action thô vào `chi_so`):
  chi=spend · hien_thi=impressions · reach=reach (theo dòng, không cộng được) · click=clicks (mọi
  lượt bấm) · chuyen_doi=action mua (purchase > omni_purchase > offsite_conversion.fb_pixel_purchase,
  lấy TÊN ĐẦU TIÊN có mặt, không cộng bí danh) · view_video=action video_view (xem ≥ 3 giây) ·
  view_het=video_p100_watched_actions · engaged_view=video_thruplay_watched_actions (ThruPlay) ·
  thich=action post_reaction · binh_luan=action comment · chia_se=action post · follow=action like
  (thích Trang) · gia_tri_mua_shop=action_values mua (cùng luật bí danh) · ket_qua, view_hai_giay,
  view_sau_giay, vao_ho_so, mua_shop = NULL (Meta không có chỉ số tương đương rõ).
  Meta BỎ action bằng 0 khỏi dòng: dòng có phân phối mà vắng action → 0; riêng dòng khán giả (chia
  nhỏ) chuyển đổi / giá trị vắng thì để NULL (Meta có thể ẩn vì quyền riêng tư).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import os
import re
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dashboard import quang_cao as QC
from dashboard import tiktok_ads as TA

NCC = "meta_ads"
NEN_TANG = "meta"
MAY_CHU = "graph.facebook.com"
PHIEN_BAN_MAC_DINH = "v26.0"
#: Khoá advisory riêng (TikTok 720_191_001) — hai nền tảng chạy song song được.
KHOA_DONG_BO = 720_191_002

#: Quyền token được phép có (đo 20/10/2026: đúng 3 quyền này). Thêm bất kỳ quyền nào khác — nhất là
#: ads_management, business_management, *_manage_*, publish_* — là token không còn chỉ đọc: từ chối.
QUYEN_CHO_PHEP = frozenset({"ads_read", "read_insights", "public_profile"})
QUYEN_CAN = frozenset({"ads_read", "read_insights"})

_PHIEN_BAN = re.compile(r"v[0-9]{1,3}\.[0-9]{1,3}")
#: Đường được GET (phần sau /<phiên bản>/).
_DUONG = re.compile(r"me|me/(?:adaccounts|permissions)|act_[0-9]{1,30}"
                    r"|act_[0-9]{1,30}/(?:insights|campaigns|ads)")
#: Tham số ĐƯỢC gửi (danh sách cho phép — soát 20/10/2026). Mọi khoá khác — `method`, `_method`,
#: `batch` (Graph nhận `?method=delete` trên GET), khoá lạ trong `paging.next` — bị chặn TRƯỚC khi
#: gửi, cả trang đầu lẫn trang sau. `access_token` được phép có mặt trong `paging.next` nhưng luôn bị
#: bỏ khỏi URL (token đi header).
THAM_SO_DUOC = frozenset({"fields", "limit", "after", "before", "level", "time_range",
                          "time_increment", "breakdowns", "access_token"})

MA_GIOI_HAN = frozenset({4, 17, 32, 613, *range(80000, 80015)})
MA_TOKEN_HONG = frozenset({102, 190})
MA_QUYEN = frozenset({10, 200, 272, 275, 294})
#: Mã con của 190: 463 = token hết hạn (system user thường không có — vẫn xử lý).
MA_CON_HET_HAN = frozenset({463})

NAP_LUI_NGAY = 90
CUA_SO_NGAY = 30
LUI_NGAY = 7
KHAN_GIA_NGAY = 7
TRANG = 500                    # dòng mỗi trang insights
#: 1 ngày vẫn quá nặng → xin lại với trang nhỏ dần (Meta hết giờ khi một trang nhiều ad × action).
TRANG_NHO = (200, 50)
#: Mã 2 = "Service temporarily unavailable" — với insights thường là yêu cầu quá nặng / hết giờ
#: (mã con 1504044): xử lý như quá nhiều dữ liệu (chia nhỏ), không bỏ cả tài khoản.
MA_QUA_TAI = frozenset({2})
TRAN_TRANG = 2000              # trang tối đa mỗi lượt đọc (phòng vòng lặp vô hạn)
THU_LAI = 3                    # lỗi mạng / 5xx
THU_LAI_GIOI_HAN = 4           # giới hạn tần suất: nghỉ 30, 60, 120, 240 giây
NGHI_GIOI_HAN = 30
NGUONG_TAI = 85                # % tải header → nghỉ trước lượt sau
NGHI_TAI_TOI_DA = 300
NGHI_GIAY = 0.2
TRAN_TOKEN = 4096

#: Bí danh action (luật của meta_ads_tool.py: lấy tên đầu tiên có mặt, KHÔNG cộng).
MUA = ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase")
#: Trường số xin ở mọi cấp (chỉ trường chắc chắn có ở Insights v2x — một tên sai làm hỏng cả lượt).
TRUONG_SO: tuple[str, ...] = (
    "spend", "impressions", "reach", "frequency", "clicks", "inline_link_clicks", "ctr", "cpc",
    "cpm", "cpp", "actions", "action_values", "purchase_roas", "video_play_actions",
    "video_thruplay_watched_actions", "video_p25_watched_actions", "video_p50_watched_actions",
    "video_p75_watched_actions", "video_p95_watched_actions", "video_p100_watched_actions",
    "video_avg_time_watched_actions", "inline_post_engagement",
)
TRUONG_TK = ("account_id",) + TRUONG_SO
TRUONG_CAMPAIGN = ("campaign_id", "campaign_name", "objective") + TRUONG_SO
TRUONG_AD = ("campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name",
             "objective") + TRUONG_SO
TRUONG_KHAN_GIA = ("spend", "impressions", "reach", "clicks", "inline_link_clicks", "actions",
                   "action_values", "video_thruplay_watched_actions")
#: Chiều khán giả: (chieu lưu trong qc_khan_gia, breakdowns gửi Meta).
CHIEU_META: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("age", ("age",)), ("gender", ("gender",)), ("region", ("region",)),
    ("publisher_platform", ("publisher_platform",)),
    ("platform_position", ("publisher_platform", "platform_position")),
)
#: Giá trị Meta → mã TikTok khi TRÙNG nghĩa (cộng chung trên trang); còn lại giữ nguyên.
GIA_TRI_META = {
    "age": {"13-17": "AGE_13_17", "18-24": "AGE_18_24", "25-34": "AGE_25_34",
            "35-44": "AGE_35_44", "45-54": "AGE_45_54", "Unknown": "NONE", "unknown": "NONE"},
    "gender": {"female": "FEMALE", "male": "MALE", "unknown": "NONE"},
}
_CHU = frozenset({"campaign_name", "adset_name", "ad_name", "objective"})
_BO_QUA = frozenset({"date_start", "date_stop", "account_id", "campaign_id", "adset_id", "ad_id",
                     "age", "gender", "region", "publisher_platform", "platform_position"})
VN = QC.VN


# ───────────────────────────── lỗi ─────────────────────────────
class LoiMeta(RuntimeError):
    """Gọi Meta hỏng. Câu đã qua `gon_loi` (không token, không URL) — hiện được cho quản trị."""

    def __init__(self, thong_diep: str, ma: int | None = None):
        super().__init__(TA.gon_loi(thong_diep))
        self.ma = ma


class LoiChan(LoiMeta):
    """Yêu cầu không phải GET / đường ngoài danh sách đọc — KHÔNG gửi đi."""


class LoiXacThuc(LoiMeta):
    """Token bị Meta từ chối (mã 190/102) — cần dán token mới."""

    def __init__(self, thong_diep: str, ma: int | None = None, het_han: bool = False):
        super().__init__(thong_diep, ma)
        self.het_han = het_han


class LoiQuyen(LoiMeta):
    """Token không có quyền trên đối tượng (mã 10/200/…)."""


class LoiQuaNhieu(LoiMeta):
    """Meta báo yêu cầu quá nhiều dữ liệu — chia nhỏ cửa sổ."""


class LoiTokenKhongChiDoc(LoiMeta):
    """Token có quyền ngoài danh sách chỉ đọc — từ chối, không lưu."""


ChuaKetNoi = TA.ChuaKetNoi
LoiMaHoa = TA.LoiMaHoa


# ───────────────────────────── chốt chỉ đọc ─────────────────────────────
def kiem_url(phuong_thuc: str, url: str, tiep: str | None = None) -> tuple[str, str]:
    """Chốt chặn TRƯỚC khi gửi. -> (url sạch không access_token, đường sau phiên bản).
    `tiep` = đường của trang đầu khi đang theo `paging.next`. Sai bất kỳ điều gì → LoiChan."""
    if str(phuong_thuc or "").upper() != "GET":
        raise LoiChan(f"chặn phương thức {str(phuong_thuc)[:10]}: Meta chỉ được GET")
    try:
        p = urlsplit(str(url))
        cong = p.port
    except ValueError:
        raise LoiChan("chặn URL hỏng") from None
    if (p.scheme != "https" or p.hostname != MAY_CHU or p.username or p.password or p.fragment
            or cong not in (None, 443)):
        raise LoiChan("chặn URL ngoài graph.facebook.com")
    phan = p.path.split("/", 2)
    if len(phan) < 3 or phan[0] != "" or not _PHIEN_BAN.fullmatch(phan[1]):
        raise LoiChan("chặn đường Graph không có phiên bản")
    duong = phan[2]
    if tiep is None:
        hop_le = bool(_DUONG.fullmatch(duong))
    else:
        hop_le = duong == tiep or (tiep in ("me/adaccounts", "me/permissions") and bool(
            re.fullmatch(rf"[1-9][0-9]{{0,30}}/{tiep[3:]}", duong)))
    if not hop_le:
        raise LoiChan(f"chặn đường '{duong[:60]}': không nằm trong danh sách chỉ đọc")
    ts = parse_qsl(p.query, keep_blank_values=True)
    la = sorted({k for k, _ in ts if k not in THAM_SO_DUOC})
    if la:
        raise LoiChan("chặn tham số ngoài danh sách đọc: " + ", ".join(x[:30] for x in la[:5]))
    q = urlencode([(k, v) for k, v in ts if k.lower() != "access_token"])
    return urlunsplit(("https", MAY_CHU, p.path, q, "")), duong


class Http:
    """GET tới Graph bằng httpx (venv dashboard có sẵn). Lớp này KHÔNG có hàm gửi nào khác: mọi
    yêu cầu qua `yeu_cau`, `kiem_url` chạy trước — POST/DELETE/đường lạ bị chặn, 0 byte ra mạng.
    Lỗi mạng và 502/503/504 thử lại `THU_LAI` lần. Bộ thử truyền `httpx.MockTransport`."""

    def __init__(self, transport=None, ngu=time.sleep, timeout: float = 120.0):
        self.transport, self.ngu, self.timeout = transport, ngu, timeout

    def yeu_cau(self, phuong_thuc: str, url: str, *, params: dict | None = None,
                headers: dict | None = None, tiep: str | None = None) -> tuple[int, dict, str]:
        import httpx
        if params:
            sep = "&" if urlsplit(url).query else "?"
            url = url + sep + urlencode({k: v for k, v in params.items() if v is not None})
        sach, _ = kiem_url(phuong_thuc, url, tiep)
        loi = None
        for lan in range(THU_LAI):
            try:
                with httpx.Client(timeout=self.timeout, transport=self.transport,
                                  follow_redirects=False) as kh:
                    r = kh.get(sach, headers=dict(headers or {}))
                    van = r.text
                if r.status_code in (502, 503, 504) and lan < THU_LAI - 1:
                    loi = f"HTTP {r.status_code}"
                    self.ngu(3 * (lan + 1))
                    continue
                if 300 <= r.status_code < 400:
                    raise LoiChan("Meta chuyển hướng — đã chặn, không theo")
                return r.status_code, {k.lower(): v for k, v in r.headers.items()}, van
            except httpx.TransportError as e:
                loi = type(e).__name__
                if lan < THU_LAI - 1:
                    self.ngu(3 * (lan + 1))
        raise LoiMeta(f"không gọi được Meta sau {THU_LAI} lần ({loi})")


def _tai_cao(hd: dict) -> int:
    """Số giây nên nghỉ theo header tải của Meta (0 = không cần)."""
    nghi = 0
    for ten in ("x-business-use-case-usage", "x-ad-account-usage", "x-app-usage"):
        try:
            d = json.loads(hd.get(ten) or "null")
        except ValueError:
            continue
        cac = []
        if isinstance(d, dict) and ten == "x-business-use-case-usage":
            cac = [x for v in d.values() if isinstance(v, list) for x in v if isinstance(x, dict)]
        elif isinstance(d, dict):
            cac = [d]
        for x in cac:
            pct = max([float(x.get(k) or 0) for k in ("call_count", "total_cputime", "total_time",
                                                       "acc_id_util_pct")
                       if isinstance(x.get(k), (int, float))] or [0])
            if pct >= NGUONG_TAI:
                cho = x.get("estimated_time_to_regain_access") or 0      # phút
                giay = x.get("reset_time_duration") or 0
                nghi = max(nghi, int(cho) * 60 if cho else int(giay) or 60)
    return min(nghi, NGHI_TAI_TOI_DA)


class Graph:
    """Client GET Graph API của một token (header Authorization, không đặt token vào URL)."""

    def __init__(self, token: str, http: Http, ngu=time.sleep, phien_ban: str | None = None,
                 nghi: float = NGHI_GIAY):
        self._token, self.http, self.ngu, self.nghi = token, http, ngu, nghi
        TA.nho_bi_mat(token)
        pb = phien_ban or (os.environ.get("META_API_VERSION") or PHIEN_BAN_MAC_DINH).strip()
        if not _PHIEN_BAN.fullmatch(pb):
            raise LoiMeta("META_API_VERSION không hợp lệ (dạng v26.0)")
        self.goc = f"https://{MAY_CHU}/{pb}/"
        self.so_luot = 0

    def goi(self, duong_hoac_url: str, params: dict | None = None, *, tiep: str | None = None
            ) -> dict:
        url = duong_hoac_url if duong_hoac_url.startswith("https://") else self.goc + duong_hoac_url
        if self.so_luot and self.nghi:
            self.ngu(self.nghi)
        for lan in range(THU_LAI_GIOI_HAN + 1):
            self.so_luot += 1
            s, hd, van = self.http.yeu_cau("GET", url, params=params, tiep=tiep,
                                           headers={"Authorization": "Bearer " + self._token})
            try:
                d = json.loads(van) if van else {}
            except ValueError:
                d = None
            loi = (d.get("error") if isinstance(d, dict) else None) or {}
            ma = loi.get("code") if isinstance(loi, dict) else None
            ma_con = loi.get("error_subcode") if isinstance(loi, dict) else None
            if s == 429 or ma in MA_GIOI_HAN:
                if lan < THU_LAI_GIOI_HAN:
                    self.ngu(NGHI_GIOI_HAN * 2 ** lan)
                    continue
                raise LoiMeta(f"Meta giới hạn tần suất (mã {ma or s}) — thử lại sau", ma)
            if ma in MA_TOKEN_HONG or (s == 401 and not ma):
                raise LoiXacThuc(f"Meta từ chối token (mã {ma or s}"
                                 + (f"/{ma_con}" if ma_con else "") + ")", ma,
                                 het_han=ma_con in MA_CON_HET_HAN)
            if ma in MA_QUYEN:
                raise LoiQuyen(f"token không có quyền trên đối tượng này (mã {ma})", ma)
            if ma == 1 or (ma == 100 and ma_con in (1487534, 1504018)):
                raise LoiQuaNhieu(f"Meta báo quá nhiều dữ liệu (mã {ma})", ma)
            if loi or s >= 400 or not isinstance(d, dict):
                # Không chép chữ lỗi của Meta (có thể chứa URL/token) — chỉ mã.
                raise LoiMeta(f"Meta không trả số (mã {ma or s}"
                              + (f"/{ma_con}" if ma_con else "") + ")", ma)
            cho = _tai_cao(hd)
            if cho:
                self.ngu(cho)
            return d
        raise LoiMeta("không đọc được Meta")

    def trang_lap(self, duong: str, params: dict | None = None):
        """Từng trang `data` (list) theo `paging.next` — trang sau qua đúng chốt `kiem_url` với
        đường của trang đầu."""
        d = self.goi(duong, params)
        da = set()
        for _ in range(TRAN_TRANG):
            ds = d.get("data")
            if not isinstance(ds, list):
                raise LoiMeta("Meta thiếu danh sách dữ liệu")
            yield ds
            nxt = (d.get("paging") or {}).get("next")
            if not nxt or not ds:
                return
            if nxt in da:
                raise LoiMeta("Meta lặp trang")
            da.add(nxt)
            d = self.goi(str(nxt), tiep=duong)
        raise LoiMeta("Meta trả quá nhiều trang — thu hẹp khoảng ngày")

    def trang(self, duong: str, params: dict | None = None) -> list[dict]:
        return [x for ds in self.trang_lap(duong, params) for x in ds]


def tham_so_insights(cap: str, truong, tu: datetime.date, den: datetime.date, *,
                     theo_ngay: bool = True, breakdowns=(), trang: int = TRANG) -> dict:
    p = {"level": cap, "fields": ",".join(truong), "limit": trang,
         "time_range": json.dumps({"since": tu.isoformat(), "until": den.isoformat()})}
    if theo_ngay:
        p["time_increment"] = 1
    if breakdowns:
        p["breakdowns"] = ",".join(breakdowns)
    return p


# ───────────────────────────── dòng Meta → dòng kho ─────────────────────────────
def hanh_dong(ds) -> dict:
    """[{action_type, value}] → {action_type: số}."""
    ra = {}
    for x in ds if isinstance(ds, list) else []:
        if isinstance(x, dict) and x.get("action_type"):
            ra[str(x["action_type"])] = QC.so(x.get("value"))
    return ra


def bi_danh(d: dict, ten: tuple[str, ...]):
    """Giá trị của tên ĐẦU TIÊN có mặt (purchase > omni_purchase > pixel) — không cộng bí danh."""
    for t in ten:
        if t in d and d[t] is not None:
            return d[t]
    return None


def chi_so_json(r: dict) -> dict:
    """Mọi trường Meta trả → JSON phẳng: số đổi bằng `quang_cao.so`; danh sách action →
    `<trường>__<action_type>` (vd actions__purchase, action_values__purchase,
    video_p100_watched_actions__video_view); chữ (tên, mục tiêu) giữ, cắt 300."""
    ra = {}
    for k, v in r.items():
        if k in _BO_QUA:
            continue
        if isinstance(v, list):
            for t, so in hanh_dong(v).items():
                ra[f"{k}__{t}"] = so
        elif k in _CHU:
            ra[k] = str(v)[:300]
        else:
            ra[k] = QC.so(v)
    return ra


def dong_so(r: dict, chia_nho: bool = False) -> dict:
    """Dòng Insights → cột kiểu riêng (`quang_cao.COT_SO`). Bảng ánh xạ ở docstring module."""
    hd, gt = hanh_dong(r.get("actions")), hanh_dong(r.get("action_values"))
    chi, hien = QC.so(r.get("spend")), QC.so(r.get("impressions"))
    co = (chi or 0) > 0 or (hien or 0) > 0

    def dem(v, chuyen_doi=False):
        if v is None:
            if not co or (chia_nho and chuyen_doi):
                return None
            v = 0                         # Meta bỏ action bằng 0 khỏi dòng có phân phối
        return round(v)

    def mot(truong):
        return hanh_dong(r.get(truong)).get("video_view")

    tien_mua = bi_danh(gt, MUA)
    if tien_mua is None and co and not chia_nho:
        tien_mua = 0
    return {"chi": chi, "hien_thi": None if hien is None else round(hien),
            "reach": None if QC.so(r.get("reach")) is None else round(QC.so(r.get("reach"))),
            "click": None if QC.so(r.get("clicks")) is None else round(QC.so(r.get("clicks"))),
            "ket_qua": None, "chuyen_doi": dem(bi_danh(hd, MUA), True),
            "view_video": dem(hd.get("video_view")), "view_hai_giay": None, "view_sau_giay": None,
            "view_het": dem(mot("video_p100_watched_actions")),
            "engaged_view": dem(mot("video_thruplay_watched_actions")),
            "thich": dem(hd.get("post_reaction")), "binh_luan": dem(hd.get("comment")),
            "chia_se": dem(hd.get("post")), "follow": dem(hd.get("like")), "vao_ho_so": None,
            "mua_shop": None, "gia_tri_mua_shop": tien_mua}


def _ngay(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def dong_tk(r: dict, act: str) -> dict:
    return {"advertiser_id": act, "ngay": _ngay(r.get("date_start")), **dong_so(r),
            "chi_so": chi_so_json(r)}


def dong_campaign(r: dict, act: str) -> dict:
    return {"advertiser_id": act, "campaign_id": str(r.get("campaign_id")),
            "ngay": _ngay(r.get("date_start")), "ten": str(r.get("campaign_name") or "")[:300],
            "muc_tieu": str(r.get("objective") or "")[:60] or None, **dong_so(r),
            "chi_so": chi_so_json(r)}


def dong_ad(r: dict, act: str) -> dict:
    return {"advertiser_id": act, "campaign_id": str(r.get("campaign_id") or "") or None,
            "adgroup_id": str(r.get("adset_id") or "") or None, "ad_id": str(r.get("ad_id")),
            "ngay": _ngay(r.get("date_start")), "ten_ad": str(r.get("ad_name") or "")[:300],
            "noi_dung": "", "ten_campaign": str(r.get("campaign_name") or "")[:300],
            "ten_nhom": str(r.get("adset_name") or "")[:300], **dong_so(r),
            "chi_so": chi_so_json(r)}


def gia_tri_khan_gia(chieu: str, r: dict) -> str:
    if chieu == "platform_position":
        g = f"{r.get('publisher_platform') or ''}/{r.get('platform_position') or ''}"
    else:
        g = str(r.get(chieu) if r.get(chieu) is not None else "")
    return GIA_TRI_META.get(chieu, {}).get(g, g)[:100]


def dong_khan_gia(r: dict, act: str, tu: datetime.date, den: datetime.date, chieu: str) -> dict:
    return {"advertiser_id": act, "tu": tu, "den": den, "chieu": chieu,
            "gia_tri": gia_tri_khan_gia(chieu, r), **dong_so(r, chia_nho=True),
            "chi_so": chi_so_json(r)}


def gop_khan_gia(rows: list[dict]) -> list[dict]:
    """Dòng khán giả cùng `gia_tri` sau khi đổi mã (vd Meta "Unknown" + "unknown" → NONE) CỘNG lại
    thành một dòng (PK …, chieu, gia_tri) — không ghi đè. Số đếm/tiền cộng; reach không cộng được →
    NULL khi gộp; chi_so: khoá cộng được thì cộng, còn lại bỏ."""
    gop: dict[str, dict] = {}
    for x in rows:
        cu = gop.get(x["gia_tri"])
        if cu is None:
            gop[x["gia_tri"]] = {**x, "chi_so": dict(x.get("chi_so") or {})}
            continue
        for k in QC.TEN_COT_SO:
            if k == "reach":
                cu[k] = None
            elif x.get(k) is not None:
                cu[k] = (cu.get(k) or 0) + x[k]
        cs = cu["chi_so"]
        for k, v in (x.get("chi_so") or {}).items():
            if not QC.cong_duoc(k) or not isinstance(v, (int, float)) or isinstance(v, bool):
                cs.pop(k, None)
            elif isinstance(cs.get(k), (int, float)):
                cs[k] = cs[k] + v
            else:
                cs[k] = v
        for k in [k for k in cs if not QC.cong_duoc(k)]:
            cs.pop(k)
    return list(gop.values())


def co_phan_phoi(r: dict) -> bool:
    return bool((r.get("hien_thi") or 0) > 0 or (r.get("chi") or 0) > 0)


def chuan_act(x) -> str | None:
    """"act_123" / "123" → "act_123"; dạng khác → None."""
    s = str(x or "").strip()
    m = re.fullmatch(r"(?:act_)?([1-9][0-9]{0,29})", s)
    return f"act_{m.group(1)}" if m else None


def kiem_quyen(quyen: list[dict]) -> list[str]:
    """me/permissions → quyền ĐÃ CẤP. Có quyền ngoài `QUYEN_CHO_PHEP` hoặc thiếu `QUYEN_CAN` →
    LoiTokenKhongChiDoc (không lưu token)."""
    cap = sorted({str(x.get("permission")) for x in quyen
                  if isinstance(x, dict) and x.get("status") == "granted"})
    thua = [q for q in cap if q not in QUYEN_CHO_PHEP]
    if thua:
        raise LoiTokenKhongChiDoc("token có quyền ngoài chỉ đọc (" + ", ".join(thua[:10]) + ") — "
                                  "tạo token người dùng hệ thống CHỈ ads_read + read_insights")
    thieu = sorted(QUYEN_CAN - set(cap))
    if thieu:
        raise LoiTokenKhongChiDoc("token thiếu quyền " + ", ".join(thieu))
    return cap


# ───────────────────────────── dịch vụ ─────────────────────────────
class DichVu:
    """Mọi việc Meta Ads của dashboard + bộ hẹn giờ. `kho` = module `kho_qc` (hoặc bản giả)."""

    def __init__(self, kho=None, *, http: Http | None = None, khoa: bytes | None = None,
                 ngu=time.sleep, bay_gio=None, log=print, phien_ban: str | None = None):
        if kho is None:
            from dashboard import kho_qc as kho
        self.kho = kho
        self.http = http or Http(ngu=ngu)
        self._khoa = khoa
        self.ngu = ngu
        self._bay_gio = bay_gio or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self.log = log
        self.phien_ban = phien_ban

    # ── khoá ──
    def khoa(self) -> bytes:
        k = self._khoa if self._khoa is not None else TA.khoa_tu_env()
        if not k:
            raise LoiMaHoa("máy chủ chưa đặt TIKTOK_KHOA_MA_HOA (khoá chung TikTok + Meta)")
        return k

    def loi_khoa(self) -> str | None:
        try:
            TA._aesgcm(self.khoa())
            return None
        except LoiMaHoa as e:
            return str(e)

    # ── thẻ trạng thái (KHÔNG token) ──
    def the(self) -> dict:
        r = self.kho.doc_ket_noi(NCC) or {}
        try:
            tk = [t for t in self.kho.cac_tk() if QC.nen_tang_tk(t) == NEN_TANG]
        except Exception:  # noqa: BLE001 — bảng chưa có cột nen_tang: thẻ vẫn hiện
            tk = []
        co_token = bool(r.get("access_token_enc"))
        tt = r.get("trang_thai") or "chua_ket_noi"
        muc = {"het_han": "loi", "loi": "loi", "chua_ket_noi": "", "da_ngat": ""}.get(tt, "tot")
        try:
            dang = bool(self.kho.dang_dong_bo(KHOA_DONG_BO))
        except Exception:  # noqa: BLE001
            dang = False
        duyet = [t for t in tk if t.get("duyet")]
        return {
            "trang_thai": tt, "nhan": TA.TEN_TRANG_THAI.get(tt, tt), "muc": muc,
            "co_token": co_token, "chu_token": r.get("chu_token"),
            "quyen_token": list(r.get("quyen_token") or []),
            "nguoi_cap": r.get("nguoi_cap"), "cap_luc": r.get("cap_luc"),
            "so_tk_thay": r.get("so_tk_thay"), "so_tk_truoc": r.get("so_tk_truoc"),
            "so_tk_duyet": len(duyet),
            "so_tk_dong_bo": sum(1 for t in duyet if t.get("con_quyen", True)
                                 and t.get("dang_dong_bo", True)),
            "so_tk_cho_duyet": sum(1 for t in tk if not t.get("duyet") and t.get("con_quyen", True)),
            "goi_ok_luc": r.get("goi_ok_luc"),
            "dong_bo_bat_dau": r.get("dong_bo_bat_dau"), "dong_bo_xong": r.get("dong_bo_xong"),
            "dong_bo_ok_luc": r.get("dong_bo_ok_luc"), "dong_bo_so_dong": r.get("dong_bo_so_dong"),
            "dong_bo_loi": r.get("dong_bo_loi"), "loi_cuoi": r.get("loi_cuoi"),
            "loi_luc": r.get("loi_luc"), "so_den_ngay": r.get("so_den_ngay"),
            "dang_dong_bo": dang, "loi_khoa": self.loi_khoa(), "co_khoa": self.loi_khoa() is None,
            "yeu_cau_dong_bo_luc": r.get("yeu_cau_dong_bo_luc"), "yeu_cau_boi": r.get("yeu_cau_boi"),
            "yeu_cau_kieu": r.get("yeu_cau_kieu"), "nhanh_xong_luc": r.get("nhanh_xong_luc"),
            "dong_bo_kieu": r.get("dong_bo_kieu"),
        }

    # ── token ──
    def graph(self, token: str | None = None) -> Graph:
        return Graph(token or self.token(), self.http, self.ngu, self.phien_ban)

    def kiem_token(self, token: str) -> dict:
        """GET me + me/permissions (chỉ đọc?) + me/adaccounts. Không lưu gì."""
        token = str(token or "").strip()
        if not re.fullmatch(rf"[A-Za-z0-9._\-|]{{20,{TRAN_TOKEN}}}", token):
            raise LoiMeta("token không đúng dạng")
        TA.nho_bi_mat(token)
        g = self.graph(token)
        me = g.goi("me", {"fields": "id,name"})
        quyen = kiem_quyen(g.trang("me/permissions", {"limit": 100}))
        return {"chu": str(me.get("name") or "")[:200] or None, "quyen": quyen,
                "tk": self._doc_tk(g)}

    def _doc_tk(self, g: Graph) -> list[dict]:
        ra = []
        for x in g.trang("me/adaccounts", {"fields": "id,name,currency,timezone_name,"
                                                     "account_status", "limit": 100}):
            act = chuan_act(x.get("id"))
            if act:
                ra.append({"advertiser_id": act, "ten": str(x.get("name") or "").strip(),
                           "tien_te": x.get("currency") or "VND",
                           "mui_gio": x.get("timezone_name") or "Asia/Ho_Chi_Minh",
                           "trang_thai_tk": x.get("account_status")})
        return ra

    def luu_token(self, ai: str, token: str, duyet: list[str] | None = None) -> dict:
        """Kiểm token (chỉ đọc) rồi mới lưu MÃ HOÁ. `duyet` (danh sách act_…) có → đặt đúng danh
        sách duyệt; không có → giữ duyệt cũ (tài khoản mới chờ quản trị viên duyệt). Ghi cờ đồng
        bộ. -> tóm tắt KHÔNG bí mật."""
        k = self.khoa()
        token = str(token or "").strip()
        ids = None
        if duyet is not None:
            ids = [chuan_act(x) for x in duyet]
            if not all(ids):
                raise LoiMeta("danh sách tài khoản duyệt phải là act_<số> hoặc <số>")
            ids = sorted(set(ids))
        kt = self.kiem_token(token)                 # sai / không chỉ đọc → ném, không lưu
        self.kho.luu_token(ai, "api_token", TA.ma_hoa(token, k, "access", NCC), None, None, None,
                           ncc=NCC)
        self.kho.luu_thong_tin_token(kt["chu"], kt["quyen"], NCC)
        if ids is not None:
            self.kho.dat_duyet(ai, ids, NCC)
        kq = self.kho.ghi_tk(kt["tk"], ncc=NCC, duyet_moi=set(ids or ()))
        self.kho.ghi_goi_ok(NCC)
        self.kho.yeu_cau_dong_bo(ai, NCC)
        thay = {t["advertiser_id"] for t in kt["tk"]}
        return {"chu": kt["chu"], "quyen": kt["quyen"], "so_tk_thay": len(thay),
                "so_tk_truoc": kq.get("so_tk_truoc"),
                "so_tk_duyet": None if ids is None else len(ids),
                "duyet_khong_thay": sorted(set(ids or ()) - thay)}

    def ngat(self, ai: str) -> None:
        """Xoá token khỏi máy chủ. Token người dùng hệ thống KHÔNG thu hồi được bằng quyền đọc —
        quản trị viên thu hồi trong Business Settings (thông báo trên trang nói rõ)."""
        self.kho.ngat(ai, NCC)

    def token(self) -> str:
        r = self.kho.doc_ket_noi(NCC) or {}
        if not r.get("access_token_enc"):
            raise ChuaKetNoi("chưa kết nối Meta Ads")
        t = TA.giai_ma(r["access_token_enc"], self.khoa(), "access", NCC)
        TA.nho_bi_mat(t)
        return t

    # ── tài khoản ──
    def kham_pha(self, g: Graph) -> dict:
        kq = self.kho.ghi_tk(self._doc_tk(g), ncc=NCC)
        self.kho.ghi_goi_ok(NCC)
        return kq

    # ── đồng bộ ──
    def co_yeu_cau(self) -> bool:
        return bool((self.kho.doc_ket_noi(NCC) or {}).get("yeu_cau_dong_bo_luc"))

    def yeu_cau(self, ai: str, kieu: str = "day_du") -> None:
        """Nút "Đồng bộ ngay": CHỈ ghi cờ — meta-ads-yeu-cau.timer (2 phút) chạy lượt. `kieu` như
        `tiktok_ads.DichVu.yeu_cau` (nhanh = 3 ngày gần nhất, không hạ yêu cầu day_du đang chờ)."""
        self.kho.yeu_cau_dong_bo(ai, NCC, kieu=kieu)

    def dong_bo(self, *, bu: int | None = None, tu: datetime.date | None = None,
                den: datetime.date | None = None, theo_yeu_cau: bool = False) -> dict:
        """Một lượt đồng bộ. `theo_yeu_cau` (bộ hẹn giờ 2 phút): loại lượt (nhanh / đầy đủ) quyết định
        NGUYÊN TỬ lúc bắt đầu, sau khi giữ khoá (`kho_qc.bat_dau_dong_bo`)."""
        r = self.kho.doc_ket_noi(NCC) or {}
        loi = self.loi_khoa()
        if loi:
            if r.get("access_token_enc"):
                self.kho.ghi_trang_thai("loi", f"Không giải mã được token: {loi}", NCC)
            return {"bo_qua": loi}
        if not r.get("access_token_enc"):
            self.kho.ghi_trang_thai(r.get("trang_thai") or "chua_ket_noi", None, NCC)
            return {"bo_qua": "chưa kết nối Meta Ads"}
        with self.kho.khoa_dong_bo(KHOA_DONG_BO) as giu:
            if not giu:
                return {"bo_qua": "đang có lượt đồng bộ Meta khác"}
            return self._dong_bo(bu=bu, tu=tu, den=den, theo_yeu_cau=theo_yeu_cau)

    def _dong_bo(self, *, bu, tu, den, theo_yeu_cau: bool = False) -> dict:
        """Bắt đầu lượt rồi chạy; LUÔN kết thúc lượt (dong_bo_xong): khoá/bản mã hỏng → trạng thái
        loi; ngoại lệ lạ → ghi "dừng bất thường" rồi ném tiếp (thẻ không bao giờ kẹt "ổn")."""
        kieu = self.kho.bat_dau_dong_bo(NCC, cho_nhanh=bool(theo_yeu_cau and not (bu or tu or den)))
        dem = {"tong": 0, "den_ngay": None}
        ket = None
        try:
            ket = self._chay(dem, bu=bu, tu=tu, den=den, nhanh=kieu == "nhanh")
        except LoiMaHoa as e:
            self.kho.ghi_trang_thai("loi", f"Không giải mã được token: {e}", NCC, con_token=True)
            ket = (f"không giải mã được token: {e}", {"loi": str(e), "so_dong": dem["tong"]})
        finally:
            if ket is None:
                ten = "lượt dừng bất thường — xem journalctl meta-ads-*"
                with contextlib.suppress(Exception):
                    self.kho.ghi_trang_thai("loi", ten, NCC, con_token=True)
                with contextlib.suppress(Exception):
                    self.kho.ket_thuc_dong_bo(dem["tong"], ten, dem["den_ngay"], NCC)
        self.kho.ket_thuc_dong_bo(dem["tong"], ket[0], dem["den_ngay"], NCC)
        return ket[1]

    def _chay(self, dem: dict, *, bu, tu, den, nhanh: bool) -> tuple[str | None, dict]:
        """Thân lượt. -> (chữ lỗi cho ket_thuc_dong_bo | None, kết quả trả). `dem` cập nhật dần."""
        loi = []
        try:
            g = self.graph()
            self.kham_pha(g)
            bay = self._bay_gio()
            cap_luc = (self.kho.doc_ket_noi(NCC) or {}).get("cap_luc")
            for t in self.kho.cac_tk():
                if QC.nen_tang_tk(t) != NEN_TANG or not t.get("duyet"):
                    continue
                if not t.get("dang_dong_bo") or not t.get("con_quyen", True):
                    continue
                r = self.kho.doc_ket_noi(NCC) or {}
                if not r.get("access_token_enc") or r.get("cap_luc") != cap_luc:
                    raise ChuaKetNoi("kết nối vừa bị ngắt hoặc thay token — lượt này dừng")
                if nhanh and not TA.co_chay_gan(self.kho, t, bay):
                    continue
                try:
                    n, d = self._dong_bo_tk(g, t, bay, bu=bu, tu=tu, den=den, nhanh=nhanh)
                    dem["tong"] += n
                    dn = dem["den_ngay"]
                    dem["den_ngay"] = max(dn, d) if dn and d else (d or dn)
                except LoiXacThuc:
                    raise
                except LoiMeta as e:
                    loi.append(f"{t.get('ten') or t['advertiser_id']}: {e}")
                    self.log(f"[meta_ads] {t['advertiser_id']} lỗi: {e}")
            self.kho.ghi_trang_thai("hoat_dong", None, NCC, con_token=True)
        except ChuaKetNoi as e:
            return str(e), {"bo_qua": str(e)}
        except LoiXacThuc as e:
            self.kho.ghi_trang_thai("het_han" if e.het_han else "loi",
                                    f"Meta từ chối token: {e} — dán token mới", NCC,
                                    con_token=True)
            return f"token bị từ chối: {e}", {"loi": str(e), "so_dong": dem["tong"]}
        except LoiMeta as e:
            self.kho.ghi_trang_thai("loi", str(e), NCC, con_token=True)
            return str(e), {"loi": str(e), "so_dong": dem["tong"]}
        chu_loi = "; ".join(loi)[:500] or None
        return chu_loi, {"so_dong": dem["tong"], "den_ngay": dem["den_ngay"], "loi": chu_loi}

    def _dong_bo_tk(self, g: Graph, t: dict, bay: datetime.datetime, *, bu, tu, den,
                    nhanh: bool = False) -> tuple[int, datetime.date]:
        act = str(t["advertiser_id"])
        hq = TA.hom_qua(t.get("mui_gio"), bay)
        if nhanh:
            a, b = TA.cua_so_nhanh(hq)
            n = self._mot_cua_so(g, act, a, b)
            self.log(f"[meta_ads] {act} nhanh {a}→{b}: {n} dòng")
            return n, hq
        tuan = hq - datetime.timedelta(days=LUI_NGAY - 1)
        nap_lui = None
        if tu or den:
            a, b = tu or (den or hq) - datetime.timedelta(days=LUI_NGAY - 1), min(den or hq, hq)
            cac = TA.cua_so(a, b, CUA_SO_NGAY)
        elif bu:
            a, b = hq - datetime.timedelta(days=int(bu) - 1), hq
            cac = TA.cua_so(a, b, CUA_SO_NGAY)
        elif not t.get("nap_lui_xong_luc"):
            a, b = hq - datetime.timedelta(days=NAP_LUI_NGAY - 1), hq
            nap_lui = a
            da = t.get("nap_lui_tu")
            cac = ([(tuan, hq)] + TA.cua_so(a, da - datetime.timedelta(days=1), CUA_SO_NGAY)
                   if isinstance(da, datetime.date) and a < da <= hq
                   else TA.cua_so(a, b, CUA_SO_NGAY))
        else:
            a, b = tuan, hq
            cac = TA.cua_so(a, b, CUA_SO_NGAY)
        n = 0
        for x, y in cac:
            n += self._mot_cua_so(g, act, x, y)
            if nap_lui is not None and (x, y) != (tuan, hq):
                self.kho.dat_nap_lui(act, x, xong=x <= nap_lui)
        n += self._khan_gia(g, t, hq, bay)
        self.log(f"[meta_ads] {act} {a}→{b}: {n} dòng")
        return n, b

    def _doc_ghi(self, g: Graph, act: str, cap: str, truong, a: datetime.date,
                 b: datetime.date, xu_ly, trang: int = TRANG) -> int:
        """Đọc insights [a, b] theo trang, ghi từng trang. Meta báo quá nhiều dữ liệu (mã 1) hoặc
        quá tải / hết giờ (mã 2, vd 2/1504044 — 20/10/2026 gặp ở 6 tài khoản lớn khi nạp lùi) →
        chia đôi cửa sổ (tới 1 ngày); 1 ngày vẫn lỗi → xin trang nhỏ dần (TRANG_NHO). Upsert nên
        đọc lại phần đã ghi không nhân đôi."""
        try:
            n = 0
            for ds in g.trang_lap(f"{act}/insights",
                                  tham_so_insights(cap, truong, a, b, trang=trang)):
                n += xu_ly(ds)
            return n
        except LoiMeta as e:
            if not (isinstance(e, LoiQuaNhieu) or e.ma in MA_QUA_TAI):
                raise
            if a < b:
                giua = a + datetime.timedelta(days=(b - a).days // 2)
                self.log(f"[meta_ads] {act} {cap} {a}→{b} quá nhiều dữ liệu (mã {e.ma}) — chia đôi")
                return (self._doc_ghi(g, act, cap, truong, a, giua, xu_ly, trang)
                        + self._doc_ghi(g, act, cap, truong, giua + datetime.timedelta(days=1), b,
                                        xu_ly, trang))
            nho = next((x for x in TRANG_NHO if x < trang), None)
            if nho is None:
                raise
            self.log(f"[meta_ads] {act} {cap} {a} quá nặng (mã {e.ma}) — trang {nho} dòng")
            return self._doc_ghi(g, act, cap, truong, a, b, xu_ly, nho)

    def _mot_cua_so(self, g: Graph, act: str, a: datetime.date, b: datetime.date) -> int:
        def ghi_bang(dong, ghi):
            return lambda ds: ghi([x for x in (dong(r, act) for r in ds)
                                   if x["ngay"] and co_phan_phoi(x)])
        co_ngay = []

        def tk(ds):
            rows = [x for x in (dong_tk(r, act) for r in ds) if x["ngay"] and co_phan_phoi(x)]
            co_ngay.extend(rows)
            return self.kho.ghi_tk_ngay(rows)
        n = self._doc_ghi(g, act, "account", TRUONG_TK, a, b, tk)
        if not co_ngay:
            return n                       # không phân phối trong cửa sổ: bỏ campaign/ad
        n += self._doc_ghi(g, act, "campaign", TRUONG_CAMPAIGN, a, b,
                           ghi_bang(dong_campaign, self.kho.ghi_campaign_ngay))
        n += self._doc_ghi(g, act, "ad", TRUONG_AD, a, b, ghi_bang(dong_ad, self.kho.ghi_ad_ngay))
        return n

    def _khan_gia(self, g: Graph, t: dict, hq: datetime.date, bay: datetime.datetime) -> int:
        luc = TA._utc(t.get("khan_gia_luc"))
        if luc and (bay - luc).days < KHAN_GIA_NGAY:
            return 0
        act = str(t["advertiser_id"])
        a = hq - datetime.timedelta(days=CUA_SO_NGAY - 1)
        if not ((self.kho.qc_tong([act], a, hq) or {}).get("hien_thi") or 0):
            return 0
        n = 0
        for chieu, bd in CHIEU_META:
            rows = g.trang(f"{act}/insights", tham_so_insights(
                "account", TRUONG_KHAN_GIA, a, hq, theo_ngay=False, breakdowns=bd))
            n += self.kho.ghi_khan_gia(gop_khan_gia([dong_khan_gia(r, act, a, hq, chieu)
                                                      for r in rows]))
        self.kho.dat_khan_gia(act)
        return n


# ───────────────────────────── dòng lệnh ─────────────────────────────
def _ngay_tham_so(s: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError("ngày dạng YYYY-MM-DD") from None


def doc_dau_vao(van: str, dang_env: bool) -> dict:
    """STDIN của `nhap-token`: JSON {token, tai_khoan_duyet, ai} hoặc (--dang-env) các dòng
    MARK_META_ADS_TOKEN=… / MARK_META_AD_ACCOUNT_IDS=… (chỉ đọc hai khoá này, bỏ mọi dòng khác)."""
    if not dang_env:
        d = json.loads(van or "{}")
        if not isinstance(d, dict):
            raise ValueError("STDIN phải là một đối tượng JSON")
        return d
    env = {}
    for dong in (van or "").splitlines():
        dong = dong.strip()
        if dong.startswith("export "):
            dong = dong[7:].strip()
        if "=" not in dong or dong.startswith("#"):
            continue
        k, v = dong.split("=", 1)
        if k.strip() in ("MARK_META_ADS_TOKEN", "MARK_META_AD_ACCOUNT_IDS"):
            env[k.strip()] = v.strip().strip("'\"")
    ids = [x.strip() for x in env.get("MARK_META_AD_ACCOUNT_IDS", "").split(",") if x.strip()]
    return {"token": env.get("MARK_META_ADS_TOKEN", ""), "tai_khoan_duyet": ids or None}


def main(argv: list[str] | None = None, dich_vu: DichVu | None = None, dong_bo_bq=None,
         stdin=None) -> int:
    p = argparse.ArgumentParser(prog="python -m dashboard.meta_ads",
                                description="Đồng bộ Meta Ads vào kho lang_nghe (chỉ GET Graph).")
    sub = p.add_subparsers(dest="lenh", required=True)
    d = sub.add_parser("dong-bo", help="một lượt đồng bộ (bộ hẹn giờ gọi lệnh này)")
    d.add_argument("--bu", type=int, help="nạp lại N ngày gần nhất (≤ 400)")
    d.add_argument("--tu", type=_ngay_tham_so)
    d.add_argument("--den", type=_ngay_tham_so)
    d.add_argument("--khong-bq", action="store_true", help="không đẩy BigQuery sau khi xong")
    d.add_argument("--chi-khi-yeu-cau", action="store_true",
                   help="chỉ chạy khi có yêu cầu \"Đồng bộ ngay\" đang chờ (bộ hẹn giờ 2 phút)")
    sub.add_parser("trang-thai", help="in trạng thái kết nối (không in token)")
    n = sub.add_parser("nhap-token", help="đọc token từ STDIN, kiểm chỉ đọc, mã hoá, lưu")
    n.add_argument("--dang-env", action="store_true",
                   help="STDIN là dòng .env (MARK_META_ADS_TOKEN, MARK_META_AD_ACCOUNT_IDS)")
    n.add_argument("--ai", default=None, help="ghi nhật ký là ai nhập (mặc định: deploy)")
    a = p.parse_args(argv)
    token = ""
    try:
        dv = dich_vu or DichVu()
        if a.lenh == "trang-thai":
            print(json.dumps(dv.the(), ensure_ascii=False, default=str, indent=1))
            return 0
        if a.lenh == "nhap-token":
            vao = doc_dau_vao((stdin or sys.stdin).read(), a.dang_env)
            token = str(vao.get("token") or "").strip()
            TA.nho_bi_mat(token)
            if not token:
                print("[meta_ads] STDIN không có token", file=sys.stderr)
                return 2
            ds = vao.get("tai_khoan_duyet")
            kq = dv.luu_token(str(a.ai or vao.get("ai") or "deploy")[:200], token,
                              list(ds) if ds is not None else None)
            print("[meta_ads] đã lưu token: " + json.dumps(kq, ensure_ascii=False, default=str))
            return 0
        if a.bu is not None and not 1 <= a.bu <= 400:
            p.error("--bu trong 1..400")
        if a.chi_khi_yeu_cau and not dv.co_yeu_cau():
            return 0
        kq = dv.dong_bo(bu=a.bu, tu=a.tu, den=a.den, theo_yeu_cau=a.chi_khi_yeu_cau)
    except LoiMaHoa as e:
        print(f"[meta_ads] {e}", file=sys.stderr)
        return 0 if a.lenh == "dong-bo" else 1
    except Exception as e:  # noqa: BLE001 — báo lỗi gọn (không token), mã thoát 1
        print(f"[meta_ads] lỗi: {type(e).__name__}: {TA.gon_loi(e, (token,))}", file=sys.stderr)
        return 1
    print(f"[meta_ads] {json.dumps(kq, ensure_ascii=False, default=str)}")
    if kq.get("so_dong") and not a.khong_bq:
        if dong_bo_bq is None:
            from dashboard import dong_bo_bq
        if dong_bo_bq.da_bat():
            try:
                bq = dong_bo_bq.chay()
                print(f"[meta_ads] BigQuery: {json.dumps(bq, ensure_ascii=False, default=str)[:500]}")
            except Exception as e:  # noqa: BLE001
                print(f"[meta_ads] BigQuery lỗi: {type(e).__name__}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
