"""Meta Ads numbers for the legacy Mark runtime; GET-only, fail-closed audience.

Actions overlap: prefer purchase > omni_purchase > pixel purchase, never sum aliases.
Reach/frequency are non-additive; totals deliberately leave them blank.
Sources: Meta Marketing API Insights and Meta's official Marketing API Postman collection.
"""
from __future__ import annotations

import contextvars
import datetime as dt
import json
import os
import re
import time
import urllib.request
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import apify_tool as A
import lark_client as lark
import lsr_platform
import memory_store
import requests
import scheduler
import trinh_bay_sheet as TB
from tools.registry import registry, tool_error, tool_result

VN = dt.timezone(dt.timedelta(hours=7))
MAX_ROWS = 20000
_context = contextvars.ContextVar("mark_ads_context", default={})
#: Token Meta rời khỏi os.environ ngay khi nạp module: mọi tiến trình con (lark-cli,
#: Scrapling, browser/terminal của Hermes — nơi Mark không sửa được danh sách chặn) đều
#: chép os.environ, nên giữ token trong bộ nhớ module là cách chặn được mọi cửa.
_TOKEN = os.environ.pop("MARK_META_ADS_TOKEN", "").strip()


def _token():
    # Biến môi trường đặt SAU khi nạp (bộ thử, đổi nóng) thắng bản đã giữ.
    return os.environ.get("MARK_META_ADS_TOKEN", "").strip() or _TOKEN


# key -> (Vietnamese name, unit, meaning, source fields)
METRICS = {
    "spend": ("Chi tiêu", "tiền TK", "Số tiền đã chi", ["spend"]),
    "impressions": ("Hiển thị", "lượt", "Số lần quảng cáo hiển thị", ["impressions"]),
    "reach": ("Tiếp cận", "người", "Người duy nhất trong từng dòng, không cộng tổng", ["reach"]),
    "clicks": ("Click", "lượt", "Tất cả lượt nhấp", ["clicks"]),
    "ctr": ("CTR", "%", "Click / hiển thị × 100", ["clicks", "impressions"]),
    "cpc": ("CPC", "tiền TK/click", "Chi tiêu / click", ["spend", "clicks"]),
    "cpm": ("CPM", "tiền TK/1.000 hiển thị", "Chi tiêu / hiển thị × 1.000", ["spend", "impressions"]),
    "frequency": ("Tần suất", "lần/người", "Hiển thị / tiếp cận; không cộng tổng", ["frequency"]),
    "purchases": ("Mua hàng", "lượt", "Mua theo phân bổ mặc định Meta", ["actions"]),
    "revenue": ("Giá trị mua", "tiền TK", "Giá trị chuyển đổi mua", ["action_values"]),
    "roas": ("ROAS tính", "lần", "Giá trị mua / chi tiêu", ["spend", "action_values"]),
    "meta_roas": ("ROAS Meta", "lần", "purchase_roas Meta báo, không cộng tổng", ["purchase_roas"]),
    "cost_per_purchase": ("Chi phí/mua", "tiền TK/lượt", "Chi tiêu / mua", ["spend", "actions"]),
    "messages": ("Hội thoại bắt đầu", "lượt", "Messaging conversation started 7d", ["actions"]),
    "leads": ("Lead", "lượt", "Lead; không cộng các tên action chồng nhau", ["actions"]),
    "cost_per_lead": ("Chi phí/lead", "tiền TK/lượt", "Chi tiêu / lead", ["spend", "actions"]),
    "cost_per_message": ("Chi phí/hội thoại", "tiền TK/lượt", "Chi tiêu / hội thoại bắt đầu", ["spend", "actions"]),
    "video_3s": ("Xem video 3 giây", "lượt", "Action video_view", ["actions"]),
    "thruplay": ("ThruPlay", "lượt", "Xem hết hoặc ít nhất 15 giây", ["video_thruplay_watched_actions"]),
    "cost_per_thruplay": ("Chi phí/ThruPlay", "tiền TK/lượt", "Chi tiêu / ThruPlay", ["spend", "video_thruplay_watched_actions"]),
}
GROUPS = {
    "co_ban": list(METRICS)[:8],
    "chuyen_doi": list(METRICS)[8:13],
    "tin_nhan_lead": list(METRICS)[13:17],
    "video": list(METRICS)[17:],
}
PURCHASE = ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase")
LEAD = ("lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead")
BREAKDOWNS = {"tuoi": "age", "gioi_tinh": "gender", "nen_tang": "publisher_platform",
              "vi_tri": "platform_position"}
LEVELS = {"tai_khoan": "account", "chien_dich": "campaign", "nhom_quang_cao": "adset",
          "quang_cao": "ad"}


def set_context(channel):
    """`channel` = `kenh` của lượt (brain.reply). Chỉ code Mark dựng nó từ cột job của
    Platform hoặc sự kiện listener: channel, chat_type, nguoi_gui, sender_identity_verified,
    scheduled/scheduled_by. Không có trường nào lấy từ nội dung tin hay đối số tool."""
    _context.set(dict(channel or {}))


_OU = re.compile(r"ou_[A-Za-z0-9_]+")
_HOI_RIENG = "Hãy tự hỏi Mark trong chat riêng Lark hoặc web console đã đăng nhập."


def _actor():
    """Người được nhận số. Chỉ hai nguồn danh tính được tin (review 08/10/2026):

    (a) chat RIÊNG Lark, người gửi do Platform/listener ghi (`nguoi_gui`) và đúng người
        brain đang trả lời; (b) job web có `sender_identity_verified` do Platform đóng.
    A2A và kênh lạ: từ chối — `user_ref` của job A2A do agent gọi tự khai, giả được thành
    bất kỳ `ou_`. Lịch: CHƯA hỗ trợ (giai đoạn 2) — Platform chưa gửi `chat_type` cho job
    lịch và chưa xác minh chat riêng đó thuộc `scheduled_by`; trả số vào đó có thể lộ cho
    người khác, nên từ chối mọi job lịch.
    """
    context = _context.get()
    channel = str(context.get("channel") or "").strip().lower()
    chat_type = context.get("chat_type")
    if channel == "a2a":
        raise ValueError("Số ads không trả qua agent khác (A2A) vì không xác thực được người cần số. " + _HOI_RIENG)
    if scheduler.get_current_chat_type() == "group" or chat_type == "group":
        raise ValueError("Số ads là dữ liệu hạn chế, không trả trong nhóm. " + _HOI_RIENG)
    if context.get("scheduled") is True:
        raise ValueError("Lịch số ads chưa hỗ trợ: chưa xác minh được chat nhận lịch là chat riêng của người "
                         "đặt lịch. " + _HOI_RIENG)
    if channel == "web":
        actor = memory_store.get_current_sender()
        if context.get("sender_identity_verified") is not True or actor != context.get("nguoi_gui"):
            raise ValueError("Web chưa xác thực người hỏi. Đăng nhập console rồi hỏi lại, hoặc hỏi trong chat riêng Lark.")
    elif channel == "lark":
        actor = memory_store.get_current_sender()
        if chat_type != "p2p":
            raise ValueError("Không xác định được chat riêng. " + _HOI_RIENG)
        if actor != context.get("nguoi_gui"):
            raise ValueError("Người hỏi không khớp người gửi tin Lark; chưa trả số. " + _HOI_RIENG)
    else:
        raise ValueError("Không xác định được kênh hỏi nên chưa trả số ads. " + _HOI_RIENG)
    if not isinstance(actor, str) or not _OU.fullmatch(actor):
        raise ValueError("Chưa xác thực người hỏi/người đặt lịch. " + _HOI_RIENG)
    return actor


def _allowed(actor):
    """Fresh directory per request; never reuse stale permissions after a failure."""
    key = os.environ.get("LSR_TELEMETRY_API_KEY", "").strip()
    base = (os.environ.get("LSR_PLATFORM_URL") or
            os.environ.get("LSR_COLLECTOR", "").replace("collector.", "platform."))
    if not key or not base:
        return False
    try:
        request = urllib.request.Request(base.rstrip("/") + "/v1/self/directory",
                                         headers={"Authorization": "Bearer " + key})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode())
        caller = data.get("caller")
        own = next((row for row in data.get("agents", []) if row.get("agent_id") == caller), {})
        people = (own.get("tool_allowlists") or {}).get("chi_so_ads", [])
        return _switch_on(own.get("capabilities")) and isinstance(people, list) and actor in people
    except Exception:
        return False


def _switch_on(caps):
    """Công tắc console của `chi_so_ads` phải BẬT RÕ, cùng luật `lsr_policy`:

    - `capabilities` chưa khai (null) = không có công tắc → TẮT (tool nằm trong
      `_CHO_CONSOLE`, không có công tắc cha để lùi về);
    - phải có dòng `tool: chi_so_ads`. Console ghi dòng đang bật KHÔNG kèm `bat`
      (`thanhCapLuu`), nên vắng `bat` trên dòng đó = bật; `bat` khác `True` = tắt;
    - có bất kỳ dòng tắt nào thì tắt thắng bật (nghi ngờ thì hẹp).
    """
    if not isinstance(caps, list):
        return False
    rows = [c for c in caps if isinstance(c, dict) and c.get("tool") == "chi_so_ads"]
    return bool(rows) and all(c.get("bat", True) is True for c in rows)


def _number(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _action(items, aliases):
    if not isinstance(items, list):
        return None
    found = {item.get("action_type"): item.get("value") for item in items if isinstance(item, dict)}
    for alias in aliases:
        if alias in found:
            return _number(found[alias])
    return None


def _divide(a, b, scale=1):
    return a / b * scale if a is not None and b is not None and b > 0 else None


#: Chỉ số đọc từ danh sách hành động. Meta BỎ HẲN action/giá trị bằng 0 khỏi dòng
#: (không trả `{"value": "0"}`), nên vắng mặt trên dòng đã có số phân phối là 0 thật.
_ACTION_KEYS = ("purchases", "revenue", "meta_roas", "messages", "leads", "video_3s", "thruplay")
#: Chỉ số chuyển đổi/giá trị: khi chia nhỏ (tuổi, giới tính, nền tảng, vị trí) Meta có thể
#: ẩn chúng vì quyền riêng tư, nên vắng mặt KHÔNG chứng minh là 0.
_CONVERSION_KEYS = ("purchases", "revenue", "meta_roas", "messages", "leads")
#: Trường luôn xin kèm để biết dòng có số phân phối hay không (0 khác "không có số").
DELIVERY_FIELDS = ("impressions", "spend")


def _values(row, fetched=None, breakdown=False):
    """`fetched` = các trường đã xin Meta. Action của chỉ số đã xin mà vắng trên dòng có
    số hiển thị/chi tiêu (kể cả 0) thì là 0; dòng không có số phân phối thì để trống.
    Dòng của truy vấn chia nhỏ (`breakdown`): chỉ số chuyển đổi/giá trị vắng vẫn để trống."""
    values = {key: _number(row.get(key)) for key in GROUPS["co_ban"]}
    values.update(purchases=_action(row.get("actions"), PURCHASE),
                  revenue=_action(row.get("action_values"), PURCHASE),
                  meta_roas=_action(row.get("purchase_roas"), PURCHASE),
                  messages=_action(row.get("actions"), ("onsite_conversion.messaging_conversation_started_7d",)),
                  leads=_action(row.get("actions"), LEAD),
                  video_3s=_action(row.get("actions"), ("video_view",)),
                  thruplay=_action(row.get("video_thruplay_watched_actions"), ("video_view",)))
    spend, impressions = _number(row.get("spend")), _number(row.get("impressions"))
    if fetched is not None and (spend is not None or impressions is not None):
        for key in _ACTION_KEYS:
            if breakdown and key in _CONVERSION_KEYS:
                continue
            if values[key] is None and set(METRICS[key][3]) <= set(fetched):
                # ROAS Meta không xác định khi chưa chi đồng nào.
                if key != "meta_roas" or (spend or 0) > 0:
                    values[key] = Decimal(0)
    return _ratios(values)


def _ratios(values):
    v = dict(values)
    v.update(ctr=_divide(v.get("clicks"), v.get("impressions"), 100),
             cpc=_divide(v.get("spend"), v.get("clicks")),
             cpm=_divide(v.get("spend"), v.get("impressions"), 1000),
             roas=_divide(v.get("revenue"), v.get("spend")),
             cost_per_purchase=_divide(v.get("spend"), v.get("purchases")),
             cost_per_lead=_divide(v.get("spend"), v.get("leads")),
             cost_per_message=_divide(v.get("spend"), v.get("messages")),
             cost_per_thruplay=_divide(v.get("spend"), v.get("thruplay")))
    return v


def _metrics(wanted):
    if isinstance(wanted, str):
        wanted = [wanted]
    if not isinstance(wanted, list) or not wanted:
        raise ValueError("chi_so cần danh sách chỉ số hoặc nhóm trong danh mục.")
    result = []
    for key in wanted:
        if key not in METRICS and key not in GROUPS:
            raise ValueError("Chỉ số không hỗ trợ: " + str(key))
        result.extend(GROUPS.get(key, [key]))
    return list(dict.fromkeys(result))


def _tz(name):
    """Múi giờ của tài khoản quảng cáo (Meta `timezone_name`). Meta tính `time_range`
    theo múi giờ này, nên "hôm qua/7 ngày" phải lấy theo nó chứ không theo giờ VN."""
    try:
        return ZoneInfo(name) if isinstance(name, str) and name.strip() else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _partial(args, end, tz=VN, now=None):
    """Khoảng ngày có chứa NGÀY HÔM NAY (theo múi giờ TK) — số còn đổi trong ngày."""
    return end == (now or dt.datetime.now(VN)).astimezone(tz).date().isoformat()


def _dates(args, now=None, tz=VN):
    today = (now or dt.datetime.now(VN)).astimezone(tz).date()
    start, end = args.get("tu_ngay"), args.get("den_ngay")
    if start or end:
        if not start or not end:
            raise ValueError("Cần cả tu_ngay và den_ngay (YYYY-MM-DD).")
        start, end = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    else:
        preset = args.get("khoang_ngay", "7_ngay")
        end = today
        if preset == "hom_nay":
            start = today
        elif preset == "hom_qua":
            start = end = today - dt.timedelta(days=1)
        elif preset in ("7_ngay", "14_ngay", "30_ngay"):
            # Last N completed days in the account timezone; today's incomplete data is excluded.
            end = today - dt.timedelta(days=1)
            start = today - dt.timedelta(days=int(preset.split("_")[0]))
        elif preset == "thang_nay":
            start = today.replace(day=1)
        elif preset == "thang_truoc":
            end = today.replace(day=1) - dt.timedelta(days=1)
            start = end.replace(day=1)
        else:
            raise ValueError("Khoảng ngày không hỗ trợ.")
    if end < start or (end - start).days >= 93 or end > today:
        raise ValueError("Chọn khoảng 1–93 ngày, không chọn ngày tương lai; khoảng dài hãy chia nhỏ.")
    return start.isoformat(), end.isoformat()


def _redact(text, token=""):
    value = str(text)
    if token:
        value = value.replace(token, "[đã ẩn]")
    return re.sub(r"(?i)(access_token[=\s:]+)[^\s&\"']+", r"\1[đã ẩn]", value)


class MetaClient:
    def __init__(self, token):
        self.token = token
        self.version = os.environ.get("MARK_META_API_VERSION", "v26.0")
        if not re.fullmatch(r"v\d+\.\d+", self.version):
            raise ValueError("MARK_META_API_VERSION không hợp lệ.")
        self.root = "https://graph.facebook.com/" + self.version

    def _tail(self, url):
        parsed = urlparse(url)
        path = parsed.path
        if (parsed.scheme != "https" or parsed.netloc != "graph.facebook.com"
                or parsed.username or parsed.fragment or not path.startswith("/" + self.version + "/")):
            raise ValueError("Chặn URL ngoài Graph API.")
        return parsed, path[len(self.version) + 2:]

    def _url(self, url, entry=None):
        """Lối vào chỉ có `me/adaccounts` và `act_<id>/insights`. `entry` = tail của trang
        đầu khi đang đi theo `paging.next`: trang sau phải cùng tail, riêng danh sách tài
        khoản thì Meta hay đổi `me` thành ID số của người dùng (`<số>/adaccounts`)."""
        parsed, tail = self._tail(url)
        if entry is None:
            allowed = tail == "me/adaccounts" or re.fullmatch(r"act_\d+/insights", tail)
        else:
            allowed = tail == entry or (entry == "me/adaccounts" and re.fullmatch(r"[1-9]\d*/adaccounts", tail))
        if not allowed:
            raise ValueError("Meta client chỉ cho phép đọc tài khoản và insights.")
        query = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() != "access_token"]
        return parsed._replace(query=urlencode(query)).geturl()

    def _get(self, url, params=None, entry=None):
        url = self._url(url, entry)
        for attempt in range(3):
            try:
                response = requests.get(url, params=params, headers={"Authorization": "Bearer " + self.token},
                                        timeout=30, allow_redirects=False)
                if 300 <= response.status_code < 400:
                    raise ValueError("Meta chuyển hướng URL; đã chặn.")
                data = response.json()
            except ValueError:
                raise ValueError("Meta trả phản hồi không hợp lệ hoặc chuyển hướng; hãy thử lại.") from None
            except requests.RequestException:
                raise ValueError("Không kết nối được Meta; hãy thử lại.") from None
            error = data.get("error") or {}
            code = error.get("code")
            limited = response.status_code == 429 or code in (4, 17, 32, 613) or (
                isinstance(code, int) and 80000 <= code <= 80014)
            if limited and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            if limited:
                raise ValueError("Meta đang giới hạn lượt đọc; hãy thử lại sau vài phút.")
            if code == 190:
                raise ValueError("Token Meta hết hạn/không hợp lệ; nhờ chủ agent cấp lại mã chỉ đọc.")
            if code in (10, 200, 275):
                raise ValueError("Không có quyền Meta trên " + urlparse(url).path.split("/")[-2] +
                                 "; nhờ chủ agent cấp quyền xem hiệu quả.")
            if error or response.status_code >= 400:
                # Do not surface untrusted API error text or response URLs (may contain tokens).
                raise ValueError("Meta không trả số (mã " + str(code or response.status_code) + ").")
            return data
        raise ValueError("Không đọc được Meta.")

    def pages(self, tail, params, limit=MAX_ROWS):
        url = self.root + "/" + tail
        entry = self._tail(self._url(url))[1]
        rows, seen = [], set()
        for page in range(500):
            url = self._url(url, entry if page else None)
            if url in seen:
                raise ValueError("Meta lặp trang; không thể đảm bảo đủ số.")
            seen.add(url)
            data = self._get(url, params, entry if page else None)
            items = data.get("data")
            if not isinstance(items, list):
                raise ValueError("Meta thiếu danh sách dữ liệu.")
            next_url = (data.get("paging") or {}).get("next")
            remaining = limit - len(rows)
            rows.extend(items[:remaining])
            if len(items) > remaining or (next_url and len(rows) >= limit):
                return rows, True
            if not next_url:
                return rows, False
            url, params = next_url, None
        raise ValueError("Meta trả quá nhiều trang; hãy thu hẹp khoảng ngày.")

    def accounts(self):
        # Owner-verified IDs keep the token limited to ads_read/read_insights.
        raw = os.environ.get("MARK_META_AD_ACCOUNT_IDS", "").strip()
        if not raw:
            raise ValueError("Chưa cấu hình ID tài khoản HAPAS đã xác minh. Nhờ chủ agent đặt MARK_META_AD_ACCOUNT_IDS.")
        items = raw.split(",")
        if len(items) > 200 or any(not re.fullmatch(r"(?:act_)?[1-9]\d*", item.strip()) for item in items):
            raise ValueError("MARK_META_AD_ACCOUNT_IDS cần tối đa 200 ID dạng act_123 hoặc 123, cách nhau bằng dấu phẩy; không dùng wildcard.")
        approved = {"act_" + item.strip().removeprefix("act_") for item in items}
        granted, cut = self.pages("me/adaccounts", {"fields": "id,name,currency,timezone_name", "limit": 100}, 1000)
        if cut:
            raise ValueError("Danh sách tài khoản bị cắt; chưa thể chọn chính xác.")
        return [a for a in granted if a.get("id") in approved]


class ChonTaiKhoan(ValueError):
    """Cần người dùng chọn tài khoản. Câu đầy đủ (kèm danh sách TÊN) chép nguyên cho người dùng;
    không cắt ở 500 ký tự như lỗi thường — mã act_ trần không ai đọc hiểu được (08/10)."""


def _ds_tai_khoan(accounts):
    return "\n".join(f"{i}. {a.get('name') or '(chưa đặt tên)'} — {a.get('id')}"
                     for i, a in enumerate(accounts, 1))


def _select(accounts, wanted, lay_het=False):
    if wanted == "tat_ca":
        return accounts
    fragments = wanted if isinstance(wanted, list) else [wanted]
    if not fragments or any(not isinstance(f, str) or not f.strip() for f in fragments):
        raise ValueError("Cần tên tài khoản, act_ID hoặc tat_ca.")
    selected = {}
    for fragment in fragments:
        f = fragment.strip()
        exact = [a for a in accounts if str(a.get("name", "")).strip().lower() == f.lower()
                 or str(a.get("id")) == f or str(a.get("id")) == "act_" + f]
        matches = exact or [a for a in accounts if f.lower() in str(a.get("name", "")).lower()]
        if not matches:
            raise ChonTaiKhoan(f"Không thấy tài khoản nào có chữ “{f}”. Các tài khoản đọc được:\n"
                               + _ds_tai_khoan(accounts)
                               + "\nBạn chọn một hoặc vài tên trong danh sách.")
        if len(matches) > 1 and not lay_het:
            raise ChonTaiKhoan(f"“{f}” khớp {len(matches)} tài khoản:\n" + _ds_tai_khoan(matches)
                               + "\nBạn muốn lấy một/vài tài khoản (nói tên hoặc số thứ tự), hay "
                               f"lấy hết {len(matches)} tài khoản này gộp lại?")
        for a in matches:
            selected[a["id"]] = a
    return list(selected.values())


def _totals(rows):
    # A missing metric stays unknown; never pretend an incomplete total is zero.
    result = {}
    additive = ("spend", "impressions", "clicks", "purchases", "revenue", "messages", "leads", "video_3s", "thruplay")
    for currency in sorted({r["currency"] for r in rows}):
        values = [r["values"] for r in rows if r["currency"] == currency]
        result[currency] = _ratios({key: sum((v[key] for v in values), Decimal(0))
                    if all(v.get(key) is not None for v in values) else None for key in additive})
    return result


def _cell(number):
    return "" if number is None else float(round(number, 6))


# ───────────── tab gộp, dữ liệu gốc gọn, xem trước (chủ agent chốt 09/10/2026) ─────────────
# Lần xuất thật 6 TK × cấp chiến dịch × theo ngày × nền tảng ra 5.900 dòng khó đọc: thêm các
# tab gộp do CODE cộng (cùng `_totals`), tab "Chi tiết" giữ đủ mọi dòng + chế độ lọc theo
# từng tài khoản, "Dữ liệu gốc" chỉ giữ cột mã + trường Chi tiết không có.
TAB_CHI_TIET = "Chi tiết"
_TEN_CHIA = {"age": "Tuổi", "gender": "Giới tính", "publisher_platform": "Nền tảng",
             "platform_position": "Vị trí"}
#: Không cộng được qua ngày/nền tảng/đối tượng: tab gộp không có các cột này.
_KHONG_CONG = ("reach", "frequency", "meta_roas")
#: Dòng chi tiết từ ngưỡng này thì Mark phải hỏi lại người dùng trước khi xuất (persona).
NGUONG_HOI_DONG = 2000
_GOC_DAU = ("account_id", "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id",
            "ad_name", "date_start", "date_stop")


def _ten_tk(row):
    return str(row["account"].get("name") or row["account"]["id"])


def _cac_gop(level, breakdown, theo_ngay, so_tai_khoan):
    """Các tab gộp nên có -> [(tên tab, [Cot khoá], khoá(row) -> tuple, mô tả nhóm)]."""
    ra = []
    if so_tai_khoan > 1 or level != "account":
        ra.append(("Theo tài khoản", [TB.Cot("Tài khoản"), TB.Cot("Mã TK", "ma")],
                   lambda r: (_ten_tk(r), r["account"]["id"]), "tài khoản"))
    for b in breakdown:
        if b == "platform_position":     # vị trí chỉ có nghĩa trong một nền tảng (feed FB ≠ IG)
            ra.append(("Theo vị trí", [TB.Cot("Nền tảng"), TB.Cot("Vị trí")],
                       lambda r: (str(r["data"].get("publisher_platform", "")),
                                  str(r["data"].get("platform_position", ""))), "nền tảng × vị trí"))
        else:
            ra.append(("Theo " + _TEN_CHIA[b].lower(), [TB.Cot(_TEN_CHIA[b])],
                       lambda r, b=b: (str(r["data"].get(b, "")),), _TEN_CHIA[b].lower()))
    if theo_ngay:
        ra.append(("Theo ngày", [TB.Cot("Ngày", "ngay")],
                   lambda r: (r["data"].get("date_start", r["start"]),), "ngày"))
    if level in ("adset", "ad") or (level == "campaign" and (theo_ngay or breakdown)):
        ra.append(("Theo chiến dịch", [TB.Cot("Tài khoản"), TB.Cot("Mã TK", "ma"),
                                        TB.Cot("Mã chiến dịch", "ma"), TB.Cot("Tên chiến dịch")],
                   lambda r: (_ten_tk(r), r["account"]["id"], str(r["data"].get("campaign_id", "")),
                              str(r["data"].get("campaign_name", ""))), "chiến dịch"))
    return ra


def _gop(rows, khoa):
    """Cộng các dòng theo (tiền tệ, khoá): chỉ số cộng được cộng bằng `_totals` (thiếu một dòng
    thì để trống), tỉ lệ tính lại từ tổng. Không bao giờ cộng hai tiền tệ. Sắp theo tiền tệ
    rồi chi tiêu giảm dần (chi tiêu trống xuống cuối); hoà thì giữ thứ tự gặp."""
    nhom = {}
    for r in rows:
        nhom.setdefault((r["currency"],) + tuple(khoa(r)), []).append(r)
    ra = [{"currency": k[0], "khoa": k[1:], "so_dong": len(rs), "values": _totals(rs)[k[0]]}
          for k, rs in nhom.items()]
    ra.sort(key=lambda g: (g["currency"], g["values"].get("spend") is None,
                           -(g["values"].get("spend") or 0)))
    return ra


def _tinh_gop(rows, level, breakdown, theo_ngay, so_tai_khoan):
    """-> [(tên tab, [Cot khoá], nhóm đã cộng, mô tả)] — chỉ tab THÊM thông tin: tab có số
    nhóm bằng số dòng chi tiết (không gộp được gì) bị bỏ."""
    ra = []
    for ten, cot, khoa, mo in _cac_gop(level, breakdown, theo_ngay, so_tai_khoan):
        nhom = _gop(rows, khoa)
        if nhom and len(nhom) < len(rows):
            ra.append((ten, cot, nhom, mo))
    return ra


def _bang_gop(gop, wanted, label):
    """Tab gộp → TB.Bang: khoá, Tiền tệ, chỉ số cộng được + tỉ lệ; dòng tổng theo tiền tệ
    cộng từ CHÍNH các nhóm (phải khớp tổng tab Chi tiết)."""
    so = [k for k in wanted if k not in _KHONG_CONG]
    ra = []
    for ten, khoa_cot, nhom, mo in gop:
        cot = [*khoa_cot, TB.Cot("Tiền tệ"),
               *[TB.Cot(METRICS[k][0] + " (" + METRICS[k][1] + ")", **_kieu_cot(k)) for k in so]]
        dong = [[*g["khoa"], g["currency"], *[_cell(g["values"].get(k)) for k in so]] for g in nhom]
        tong = [[label + " " + cur, *[""] * (len(khoa_cot) - 1), cur, *[_cell(v.get(k)) for k in so]]
                for cur, v in _totals(nhom).items()]
        ra.append(TB.Bang(ten, cot, dong, dong_tong=tong, gap_duoc=False, ten_tab=ten,
                          mo_ta=f"Mỗi dòng một {mo} (cộng từ tab {TAB_CHI_TIET}, từng tiền tệ); "
                                "tỉ lệ tính lại từ tổng; sắp theo chi tiêu"))
    return ra


def _toan_0(row, wanted):
    """Dòng không hiển thị, không chi tiêu và mọi chỉ số đã hỏi đều 0/trống."""
    return all(row["values"].get(k) in (None, 0) for k in {*wanted, *DELIVERY_FIELDS})


def _goc_gon(rows, wanted, breakdown):
    """"Dữ liệu gốc" gọn: cột mã/ngày/chia nhỏ + MỌI trường Meta mà tab Chi tiết không mang
    nguyên (actions, action_values… dạng JSON; spend/impressions… khi không hỏi). Trường đã có
    nguyên giá trị ở Chi tiết (chỉ số hỏi trực tiếp, tên TK) bỏ. Không còn trường riêng → None."""
    co_roi = {k for k in wanted if METRICS[k][3] == [k]} | {"account_name"}
    dau = [*_GOC_DAU, *breakdown]
    ban = []
    for row in rows:
        d = row["data"]
        b = {k: d[k] for k in dau if k in d}
        b.update((k, v) for k, v in d.items() if k not in b and k not in co_roi)
        ban.append(b)
    if not {k for b in ban for k in b} - set(dau):
        return None
    return TB.bang_goc(ban, mo_ta="Cột mã, ngày, chia nhỏ + các trường Meta tab Chi tiết không có "
                                  "(danh sách actions… ở dạng JSON), cùng thứ tự dòng với tab Chi tiết")


_KHOA_CHIA = {v: k for k, v in BREAKDOWNS.items()}
_KHOA_CAP = {v: k for k, v in LEVELS.items()}


def _xem_truoc(rows, level, breakdown, theo_ngay, wanted, cut, span, so_tai_khoan):
    """Kích thước Sheet sẽ xuất — KHÔNG tạo Sheet, không gọi Lark, không trả số chỉ số."""
    def dem(f):
        return len({f(r) for r in rows})
    kt = {"tai_khoan": dem(lambda r: r["account"]["id"])}
    if level in ("adset", "ad"):
        kt["chien_dich"] = dem(lambda r: (r["account"]["id"], r["data"].get("campaign_id")))
    if level != "account":
        kt[_KHOA_CAP[level]] = dem(lambda r: (r["account"]["id"], r["data"].get(level + "_id")))
    if theo_ngay:
        kt["ngay"] = dem(lambda r: r["data"].get("date_start"))
    for b in breakdown:
        kt[_KHOA_CHIA[b]] = dem(lambda r, b=b: r["data"].get(b))
    ten = {"tai_khoan": "tài khoản", "chien_dich": "chiến dịch", "nhom_quang_cao": "nhóm quảng cáo",
           "quang_cao": "quảng cáo", "ngay": "ngày", "tuoi": "nhóm tuổi", "gioi_tinh": "giới tính",
           "nen_tang": "nền tảng", "vi_tri": "vị trí"}
    # Tài khoản (và chiến dịch khi cấp nhỏ hơn) CHỨA đối tượng, không nhân thêm: đứng trước ":".
    long = set() if level == "account" else {"tai_khoan"} | ({"chien_dich"} if level in ("adset", "ad") else set())
    cong_thuc = " × ".join(f"{n} {ten[k]}" for k, n in kt.items() if k not in long)
    if long:
        cong_thuc = (", ".join(f"{kt[k]} {ten[k]}" for k in ("tai_khoan", "chien_dich") if k in long)
                     + ": " + cong_thuc)
    gop = _tinh_gop(rows, level, breakdown, theo_ngay, so_tai_khoan)
    goi_y = [{"tab": t, "so_dong": len(n)} for t, _, n, _ in gop] + [{"tab": TAB_CHI_TIET, "so_dong": len(rows)}]
    obj = (lambda r: (r["account"]["id"], r["data"].get(level + "_id"))) if level != "account" \
        else (lambda r: r["account"]["id"])
    gon = []
    if theo_ngay:
        gon.append({"bo": "theo_ngay", "so_dong_uoc": dem(lambda r: (obj(r), *[r["data"].get(b) for b in breakdown]))})
    if breakdown:
        gon.append({"bo": "chia_theo", "so_dong_uoc": dem(lambda r: (obj(r), r["data"].get("date_start")))})
    zero = sum(1 for r in rows if _toan_0(r, wanted))
    ra = {"xem_truoc": True, "so_dong": len(rows), "bi_cat": cut, "khoang": span, "kich_thuoc": kt,
          "cong_thuc": cong_thuc, "so_dong_toan_0": zero, "tab_se_co": goi_y, "phuong_an_gon": gon}
    if len(rows) > NGUONG_HOI_DONG:
        ra["hoi_tiep"] = (f"CHƯA xuất. Báo người dùng: tab Chi tiết sẽ có {len(rows)} dòng ({cong_thuc}), "
                          f"{zero} dòng toàn 0. Hỏi họ chọn: (1) lấy đủ chi tiết — vẫn kèm các tab gộp "
                          + (", ".join(g["tab"] for g in goi_y[:-1]) or "(không có)")
                          + (" và chế độ lọc theo từng tài khoản" if kt["tai_khoan"] > 1 else "") + "; "
                          "hoặc (2) yêu cầu gọn hơn (xem phuong_an_gon: bỏ theo ngày / bỏ chia nhỏ / cấp cao hơn). "
                          "Chỉ xuất sau khi họ trả lời: gọi lại đúng đối số đã chọn, bỏ xem_truoc.")
    else:
        ra["hoi_tiep"] = "Dưới ngưỡng hỏi lại: gọi lại cùng đối số, bỏ xem_truoc, để xuất Sheet."
    return ra


def _khoa_rieng_tu(token):
    """Chạy NGAY SAU khi tạo bảng tính, TRƯỚC mọi lần ghi số (`xuat(sau_khi_tao=...)`)."""
    # Drive v2 fields/enums verified against larksuite/oapi-sdk-go v3.12.0 drive/v2.
    # Close inherited tenant/link sharing BEFORE writing confidential values.
    lark.call("PATCH", f"/open-apis/drive/v2/permissions/{token}/public", query={"type": "sheet"},
              body={"external_access_entity": "closed", "link_share_entity": "closed",
                    "share_entity": "same_tenant", "manage_collaborator_entity": "collaborator_full_access"})
    permission = lark.call("GET", f"/open-apis/drive/v2/permissions/{token}/public", query={"type": "sheet"})
    public = ((permission or {}).get("data") or {}).get("permission_public") or {}
    # `share_entity` của Drive v2 chỉ có `anyone` | `same_tenant`; đòi đúng giá trị vừa
    # đặt (không phải `anyone`), cộng `collaborator_full_access` để chỉ người toàn quyền
    # (bot) thêm được cộng tác viên.
    if (public.get("link_share_entity") != "closed" or public.get("external_access_entity") != "closed"
            or public.get("share_entity") != "same_tenant"
            or public.get("manage_collaborator_entity") != "collaborator_full_access"):
        raise ValueError("Chưa xác minh được Sheet riêng tư; chưa ghi số ads.")


def _private_sheet(title, bang, tong_quan, actor, goc=None, gop=()):
    """Sheet riêng qua lớp trình bày chung. Thứ tự (trinh_bay_sheet.xuat): tạo → khoá chia sẻ
    link/tenant + kiểm lại (`_khoa_rieng_tu`) → ghi số → trang trí → Tổng quan → cấp quyền
    XEM cho đúng người hỏi (hỏng thì ném, như cũ). Lưới lớn (tới 20.000 dòng) do lớp tự nới.
    `gop` = các tab gộp, đứng sau Tổng quan và trước tab Chi tiết (`bang`); mỗi bảng tính tràn
    (quá 10 tab) cũng qua đúng thứ tự khoá → ghi → cấp quyền. -> KetQua (kq.url là link)."""
    def cap_quyen(token):
        if not _grant_view(token, actor):
            raise ValueError("Chưa chia sẻ được Sheet riêng cho bạn; nhờ chủ agent kiểm quyền Lark.")
    return TB.xuat(title, [*gop, bang], tong_quan, goc=goc, sau_khi_tao=_khoa_rieng_tu,
                   cap_quyen=cap_quyen)


_TEN_CAP = {"account": "tài khoản", "campaign": "chiến dịch", "adset": "nhóm quảng cáo", "ad": "quảng cáo"}


def _kieu_cot(key):
    """Kiểu cột theo đơn vị của METRICS: tiền theo tiền tệ từng dòng; CTR đã ×100 (`_ratios`)."""
    unit = METRICS[key][1]
    if unit.startswith("tiền TK"):
        return {"kieu": "tien", "cot_tien_te": "Tiền tệ"}
    if unit in ("lượt", "người"):
        return {"kieu": "so_nguyen"}
    if unit == "%":
        return {"kieu": "phan_tram_100"}
    return {"kieu": "ti_le"}                 # "lần", "lần/người"


def _grant_view(token, actor):
    """Người hỏi chỉ cần XEM số. `A._grant` (chi_so_bai, quét MXH) cấp `edit` để người
    dùng sắp/lọc bảng làm việc; với số ads hạn chế, `view` đủ dùng và không cho sửa số."""
    try:
        lark.call("POST", f"/open-apis/drive/v1/permissions/{token}/members", query={"type": "sheet"},
                  body={"member_type": "openid", "member_id": actor, "perm": "view"})
        return True
    except Exception as error:  # noqa: BLE001
        print(f"[chi_so_ads] cấp quyền xem thất bại: {_redact(error)[:200]}", flush=True)
        return False


def _handle(args, **kwargs):
    token = ""
    try:
        if args.get("danh_muc") is True:
            return tool_result({"nhom": {g: [{"ma": k, "ten": METRICS[k][0], "don_vi": METRICS[k][1],
                        "y_nghia": METRICS[k][2]} for k in keys] for g, keys in GROUPS.items()},
                "chia_theo": BREAKDOWNS, "khoang_ngay": ["hom_nay", "hom_qua", "7_ngay", "14_ngay", "30_ngay", "thang_nay", "thang_truoc"],
                "hoi_tiep": "Bạn cần chỉ số nào, tài khoản nào và khoảng thời gian nào?"})
        actor = _actor()
        if not _allowed(actor):
            raise ValueError("Bạn chưa được phép xem số ads hoặc không đọc được quyền. Nhờ quản trị agent thêm email vào Console → Mark → Năng lực → Danh sách người được xem số ads.")
        if args.get("danh_sach_tai_khoan") is True:
            token = _token()
            if not token:
                raise ValueError("Chưa cấu hình token Meta Ads. Nhờ chủ agent cấu hình MARK_META_ADS_TOKEN chỉ đọc trên VPS.")
            ds = MetaClient(token).accounts()
            return tool_result({"so_tai_khoan": len(ds), "danh_sach": _ds_tai_khoan(ds),
                                "hoi_tiep": "Chép nguyên danh_sach. Bạn cần tài khoản nào (một, vài, hay "
                                            "hết các tài khoản có chung một chữ như HAPAS)?"})
        if "tai_khoan" not in args or not any(k in args for k in ("khoang_ngay", "tu_ngay", "den_ngay")):
            raise ValueError("Bạn cần số của tài khoản nào và khoảng thời gian nào? Gọi danh_muc=true để xem các chỉ số.")
        wanted = _metrics(args.get("chi_so", ["co_ban"]))
        _dates(args)  # validate shape before any network call; per-account dates below
        level = LEVELS.get(args.get("cap", "tai_khoan"))
        if not level:
            raise ValueError("Cấp báo cáo không hỗ trợ.")
        breakdown_keys = args.get("chia_theo") or []
        if not isinstance(breakdown_keys, list) or any(k not in BREAKDOWNS for k in breakdown_keys):
            raise ValueError("Chia theo chỉ hỗ trợ tuổi, giới tính, nền tảng và vị trí.")
        breakdown = list(dict.fromkeys(BREAKDOWNS[k] for k in breakdown_keys))
        if set(breakdown) not in (set(), {"age"}, {"gender"}, {"age", "gender"},
                {"publisher_platform"}, {"publisher_platform", "platform_position"}):
            raise ValueError("Tổ hợp chia nhỏ chưa hỗ trợ. Vị trí cần kèm nền tảng; tuổi/giới tính phải tách khỏi nền tảng/vị trí.")
        for k in ("theo_ngay", "xem_truoc"):
            if k in args and not isinstance(args[k], bool):
                raise ValueError(k + " phải là true/false.")
        theo_ngay = args.get("theo_ngay") is True
        token = _token()
        if not token:
            raise ValueError("Chưa cấu hình token Meta Ads. Nhờ chủ agent cấu hình MARK_META_ADS_TOKEN chỉ đọc trên VPS.")
        client = MetaClient(token)
        if "lay_het_khop" in args and not isinstance(args["lay_het_khop"], bool):
            raise ValueError("lay_het_khop phải là true/false.")
        accounts = _select(client.accounts(), args["tai_khoan"], lay_het=args.get("lay_het_khop") is True)
        if not accounts:
            raise ValueError("Không có tài khoản HAPAS được cấp quyền xem hiệu quả.")
        # Fetch only requested fields, inputs needed for requested ratios, and the
        # delivery signal that tells a real 0 (Meta omits zero actions) from no data.
        fields = {field for key in wanted for field in METRICS[key][3]}
        fields.update(DELIVERY_FIELDS)
        fields.update(("account_id", "account_name", "date_start", "date_stop"))
        if level != "account":
            fields.update((level + "_id", level + "_name"))
        if level in ("adset", "ad"):         # tab gộp "Theo chiến dịch"
            fields.update(("campaign_id", "campaign_name"))
        parameters = {"fields": ",".join(sorted(fields)), "level": level, "limit": 500,
                      "use_unified_attribution_setting": "true"}
        if theo_ngay:
            parameters["time_increment"] = 1
        if breakdown:
            parameters["breakdowns"] = ",".join(breakdown)
        if args.get("loc"):
            if not isinstance(args["loc"], str) or len(args["loc"]) > 200:
                raise ValueError("loc cần tên chiến dịch tối đa 200 ký tự.")
            parameters["filtering"] = json.dumps([{"field": "campaign.name", "operator": "CONTAIN", "value": args["loc"]}])
        rows, cut, spans, partial, unknown_tz = [], False, set(), False, False
        for index, account in enumerate(accounts):
            if not re.fullmatch(r"act_\d+", str(account.get("id", ""))) or not account.get("currency"):
                raise ValueError("Meta thiếu mã tài khoản hoặc đơn vị tiền; không xuất tổng sai.")
            # Meta cộng số theo ngày của MÚI GIỜ TÀI KHOẢN; tính mốc theo đúng múi đó.
            tz = _tz(account.get("timezone_name"))
            unknown_tz = unknown_tz or tz is None
            a_start, a_end = _dates(args, tz=tz or VN)
            spans.add((a_start, a_end))
            partial = partial or _partial(args, a_end, tz or VN)
            data, truncated = client.pages(account["id"] + "/insights",
                                           {**parameters, "time_range": json.dumps({"since": a_start, "until": a_end})},
                                           MAX_ROWS - len(rows))
            for item in data:
                rows.append({"account": account, "data": item, "currency": account["currency"],
                             "values": _values(item, fields, bool(breakdown)), "start": a_start, "end": a_end,
                             "tz": account.get("timezone_name") if tz else "Asia/Ho_Chi_Minh (TK không báo múi giờ)"})
            cut = cut or truncated
            if len(rows) >= MAX_ROWS:
                cut = cut or index < len(accounts) - 1
                break
        start, end = min(s for s, _ in spans), max(e for _, e in spans)
        span = f"{start}–{end}" + ("" if len(spans) == 1 else " theo múi giờ từng TK")
        so_tk = len({r["account"]["id"] for r in rows}) or len(accounts)
        if args.get("xem_truoc") is True:
            # Chỉ kích thước, không số chỉ số: không tạo Sheet, không gọi Lark, không gắn cờ hạn chế.
            return tool_result(_xem_truoc(rows, level, breakdown, theo_ngay, wanted, cut, span, so_tk))
        totals = _totals(rows)
        camp = level in ("adset", "ad")
        columns = [TB.Cot("Tài khoản"), TB.Cot("Mã TK", "ma"), TB.Cot("Tiền tệ"), TB.Cot("Múi giờ TK"),
                   TB.Cot("Từ ngày", "ngay"), TB.Cot("Đến ngày", "ngay"), TB.Cot("Mã đối tượng", "ma"),
                   TB.Cot("Tên đối tượng"),
                   *([TB.Cot("Mã chiến dịch", "ma"), TB.Cot("Tên chiến dịch")] if camp else []),
                   *[TB.Cot(_TEN_CHIA[b]) for b in breakdown],
                   *[TB.Cot(METRICS[k][0] + " (" + METRICS[k][1] + ")", **_kieu_cot(k)) for k in wanted]]
        table = []
        for row in rows:
            data, account = row["data"], row["account"]
            table.append([account.get("name", ""), account["id"], row["currency"], row["tz"],
                          data.get("date_start", row["start"]), data.get("date_stop", row["end"]), data.get(level + "_id", account["id"]),
                          data.get(level + "_name", account.get("name", "")),
                          *([data.get("campaign_id", ""), data.get("campaign_name", "")] if camp else []),
                          *[data.get(k, "") for k in breakdown],
                          *[_cell(row["values"].get(k)) for k in wanted]])
        label = "TỔNG PHẦN ĐÃ ĐỌC" if cut else "TỔNG"
        total_rows = [[label + " " + currency, "", currency, "", start, end, "", "", *(["", ""] if camp else []),
                       *["" for _ in breakdown], *[_cell(values.get(k)) for k in wanted]]
                      for currency, values in totals.items()]
        gop = (_tinh_gop(rows, level, breakdown, theo_ngay, so_tk)
               if any(k not in _KHONG_CONG for k in wanted) else [])
        gop_bang = _bang_gop(gop, wanted, label)
        raw = _goc_gon(rows, wanted, breakdown) if rows else None
        zero = sum(1 for r in rows if _toan_0(r, wanted))
        notes = [f"{span}. Mốc ngày tính theo múi giờ của từng tài khoản (cột Múi giờ TK), đúng cách Meta cộng số. "
                 "Số theo phân bổ mặc định của Meta. Reach/tần suất/ROAS Meta không cộng tổng. "
                 "Dòng có số hiển thị/chi tiêu mà Meta không trả mua/lead/tin nhắn/video thì ghi 0 (Meta bỏ số 0); "
                 "ô trống = Meta không trả số phân phối cho dòng đó, không phải 0."]
        if breakdown:
            notes.append("Có chia nhỏ (tuổi/giới tính/nền tảng/vị trí): Meta có thể ẩn số mua, giá trị mua, "
                         "ROAS Meta, lead, tin nhắn vì quyền riêng tư; ô trống ở các cột đó = Meta không trả số, "
                         "không phải 0, và tổng cột đó để trống.")
        if partial:
            notes.append("Khoảng ngày gồm HÔM NAY theo múi giờ tài khoản: ngày chưa hết, số hôm nay còn thay đổi.")
        if unknown_tz:
            notes.append("Có tài khoản Meta không báo múi giờ; mốc ngày của tài khoản đó tính theo giờ VN (UTC+7).")
        if cut:
            notes.append("ĐÃ CẮT ở 20.000 dòng; tổng chỉ cho phần đã đọc. Hãy thu hẹp ngày/tài khoản.")
        notes.append(f"Dòng {label} (theo từng tiền tệ) và SỐ LIỆU CHÍNH là tổng tool tự cộng từ các dòng đã đọc; "
                     "CTR/CPC/CPM/ROAS/chi phí mỗi kết quả của dòng tổng tính lại từ tổng, không cộng tỉ lệ. "
                     "Tiền theo đơn vị tiền tệ của từng tài khoản (cột Tiền tệ), không quy đổi.")
        if gop_bang:
            bo = [METRICS[k][0].lower() for k in wanted if k in _KHONG_CONG]
            notes.append(("Các tab " if len(gop_bang) > 1 else "Tab ") + ", ".join(b.ten_tab for b in gop_bang)
                         + f": tool tự cộng từ các dòng của tab "
                         f"{TAB_CHI_TIET}, riêng từng tiền tệ (không cộng VND với USD); tỉ lệ tính lại từ tổng; "
                         f"sắp theo chi tiêu giảm dần; dòng {label} ở đó bằng đúng dòng {label} của "
                         f"{TAB_CHI_TIET}. Tiếp cận, tần suất và ROAS Meta không cộng được qua ngày/nền tảng/đối "
                         "tượng nên không có ở các tab gộp"
                         + (" (" + ", ".join(bo) + ": xem từng dòng ở " + TAB_CHI_TIET + ")" if bo else "") + ".")
        if zero:
            notes.append(f"{zero}/{len(rows)} dòng ở tab {TAB_CHI_TIET} toàn 0 (không hiển thị, không chi tiêu); "
                         "vẫn giữ đủ — muốn ẩn thì lọc bỏ số 0 ở cột chỉ số.")
        if raw is not None:
            notes.append(f"Tab Dữ liệu gốc: cột mã/ngày/chia nhỏ + các trường Meta mà tab {TAB_CHI_TIET} không có "
                         f"(danh sách actions… ở dạng JSON), cùng thứ tự dòng với tab {TAB_CHI_TIET} — để đối chiếu "
                         "cách tính.")
        bang = TB.Bang(TAB_CHI_TIET, columns, table, dong_tong=total_rows, ten_tab=TAB_CHI_TIET,
                       loc_san="Tài khoản" if so_tk > 1 else None,
                       mo_ta="Mỗi dòng một " + _TEN_CAP.get(level, level) + (" theo ngày" if theo_ngay else "")
                       + (" × " + ", ".join(_TEN_CHIA[b].lower() for b in breakdown) if breakdown else "")
                       + "; giữ cả dòng toàn 0")
        # Hậu tố tiền tệ CHỈ ở chỉ số tiền; nhiều tiền tệ thì mỗi tiền tệ một khối.
        key_figures = [TB.SoLieu(METRICS[k][0] + (" — " + currency if METRICS[k][1].startswith("tiền TK") else ""),
                                 float(round(values[k], 4)), _kieu_cot(k)["kieu"], tien_te=currency,
                                 ghi_chu=METRICS[k][1] + ("; tổng phần đã đọc" if cut else ""),
                                 khoi=("Tài khoản tiền " + currency) if len(totals) > 1 else "")
                       for currency, values in totals.items() for k in wanted if values.get(k) is not None]
        names = (list(dict.fromkeys(str(r["account"].get("name") or r["account"]["id"]) for r in rows))
                 or [str(a.get("name") or a.get("id")) for a in accounts])
        overview = TB.TongQuan(
            tieu_de="Số ads HAPAS " + start + "–" + end,
            nguon="Meta Marketing API Insights (chi_so_ads, phân bổ mặc định)", thoi_gian=span,
            pham_vi=(f"{len(accounts)} tài khoản: " + ", ".join(names[:8]) + ("…" if len(names) > 8 else "")
                     + " · cấp " + _TEN_CAP.get(level, level) + (" · chia theo " + ", ".join(_TEN_CHIA[b].lower() for b in breakdown) if breakdown else "")
                     + (" · theo ngày" if theo_ngay else "")
                     + (" · lọc chiến dịch chứa '" + args["loc"] + "'" if args.get("loc") else "")),
            so_lieu=key_figures,
            nhom=[TB.dem_theo(bang, "Tài khoản", "Số dòng theo tài khoản")] if len(accounts) > 1 and table else [],
            ghi_chu=notes)
        # Recheck immediately before disclosure: list or switch may have changed mid-fetch.
        if not _allowed(actor):
            raise ValueError("Quyền xem số ads đã đổi hoặc không đọc được quyền; chưa xuất Sheet.")
        kq = _private_sheet("Số ads HAPAS " + start + "–" + end, bang, overview, actor, raw, gop_bang)
        summary = "; ".join(currency + ": " + ", ".join(METRICS[k][0] + " " + str(round(values[k], 4))
                       for k in wanted if values.get(k) is not None) for currency, values in totals.items())
        sentence = (f"Đã đọc {len(rows)} dòng ({span})" + ("; đã cắt, tổng chỉ phần đã đọc" if cut else "")
                    + ("; gồm hôm nay chưa hết ngày, số còn thay đổi" if partial else ""))
        if summary:
            sentence += "; " + summary
        # Câu trả lời của lượt này mang số hạn chế: Platform ẩn nội dung khỏi người dưới
        # moderator ở bản ghi hội thoại (cờ `restricted` gửi kèm /reply).
        # Lượt này (hộp của lượt) và cả phiên (lưu đĩa): lượt sau có thể nhắc lại số từ lịch sử.
        lsr_platform.danh_dau_han_che("chi_so_ads")
        memory_store.danh_dau_phien_han_che(scheduler.get_current_chat() or "", "chi_so_ads")
        result = {"link": kq.url, "cau_tong": sentence + ".", "so_dong": len(rows), "bi_cat": cut,
                  "chi_so": wanted, "nguoi_duoc_chia_se": actor, "so_dong_toan_0": zero,
                  "tab": ([b.ten_tab for b in gop_bang] + [TAB_CHI_TIET]
                          + (["Dữ liệu gốc"] if raw is not None else [])),
                  **kq.cho_tool()}
        if kq.day_du is False:
            result["canh_bao"] = "Sheet có thể thiếu dữ liệu: " + kq.cau_kiem
        return tool_result(result)
    except ChonTaiKhoan as error:
        return tool_error(_redact(str(error), token)[:4000] + "\n(Chép nguyên danh sách này cho người dùng.)")
    except Exception as error:
        return tool_error(_redact(str(error), token)[:500])


SCHEMA = {"name": "chi_so_ads", "description": "Đọc số Meta Ads HAPAS rồi xuất Sheet riêng cho người hỏi có quyền. Hỏi chung: gọi danh_muc=true để liệt kê mọi chỉ số tên Việt, đơn vị, ý nghĩa, cách chia và ngày; hỏi người dùng chọn. Hỏi cụ thể: lấy đúng chi_so được yêu cầu; chép cau_tong nguyên văn, không tự tính. Chỉ đọc ads, API miễn phí; không sửa/tạm dừng. Nhóm cần chuyển chat riêng. Yêu cầu vừa theo_ngay vừa chia_theo, hoặc cấp nhom_quang_cao/quang_cao, hoặc cấp chien_dich nhiều tài khoản: gọi xem_truoc=true TRƯỚC; so_dong > 2000 thì báo số dòng + kich_thuoc, hỏi lấy đủ chi tiết (vẫn có tab gộp + chế độ lọc theo tài khoản) hay gọn hơn, chỉ xuất sau khi họ trả lời. Sheet: Tổng quan, các tab gộp (Theo tài khoản/nền tảng/ngày/chiến dịch), Chi tiết, Dữ liệu gốc.",
    "parameters": {"type": "object", "properties": {
        "danh_muc": {"type": "boolean"},
        "danh_sach_tai_khoan": {"type": "boolean", "description": "true = liệt kê tên + mã các tài khoản đọc được (không lấy số)."},
        "tai_khoan": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
                      "description": "Tên đầy đủ, một chữ trong tên, act_ID, hoặc tat_ca."},
        "lay_het_khop": {"type": "boolean", "description": "true = lấy HẾT các tài khoản có chữ trong tai_khoan (vd cả nhóm HAPAS), gộp lại. Chỉ dùng khi người dùng nói rõ muốn lấy hết."},
        "khoang_ngay": {"type": "string", "enum": ["hom_nay", "hom_qua", "7_ngay", "14_ngay", "30_ngay", "thang_nay", "thang_truoc"]},
        "tu_ngay": {"type": "string"}, "den_ngay": {"type": "string"},
        "cap": {"type": "string", "enum": list(LEVELS)}, "theo_ngay": {"type": "boolean"},
        "chia_theo": {"type": "array", "items": {"type": "string", "enum": list(BREAKDOWNS)}},
        "chi_so": {"type": "array", "items": {"type": "string", "enum": list(METRICS) + list(GROUPS)}},
        "loc": {"type": "string"},
        "xem_truoc": {"type": "boolean", "description": "true = chạy đúng truy vấn Meta nhưng KHÔNG tạo Sheet: trả so_dong, kich_thuoc (tài khoản, chiến dịch/đối tượng, ngày, giá trị chia), so_dong_toan_0, tab_se_co, phuong_an_gon."}},
        "additionalProperties": False}}

registry.register(name="chi_so_ads", toolset="social", schema=SCHEMA, handler=_handle,
                  check_fn=lambda: True, requires_env=[], is_async=False,
                  description="Số Meta Ads HAPAS → Sheet riêng", emoji="📊", override=True)
