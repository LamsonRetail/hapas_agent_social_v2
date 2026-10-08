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

import requests
from tools.registry import registry, tool_error, tool_result

import apify_tool as A
import lark_client as lark
import memory_store
import scheduler

VN = dt.timezone(dt.timedelta(hours=7))
MAX_ROWS = 20000
_context = contextvars.ContextVar("mark_ads_context", default={})

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
    _context.set(dict(channel or {}))


def _actor():
    context = _context.get()
    actor = context.get("scheduled_by") if context.get("scheduled") is True else memory_store.get_current_sender()
    if not isinstance(actor, str) or not re.fullmatch(r"ou_[A-Za-z0-9_]+", actor):
        raise ValueError("Chưa xác thực người hỏi/người đặt lịch. Hãy hỏi trong chat riêng hoặc web đã xác thực.")
    chat_type = scheduler.get_current_chat_type()
    chat_id = scheduler.get_current_chat() or ""
    if chat_type == "group" or (chat_id.startswith("oc_") and chat_type != "p2p"):
        raise ValueError("Số ads là dữ liệu hạn chế. Hãy hỏi trong chat riêng hoặc web đã xác thực để giữ số riêng cho bạn.")
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
        caps = own.get("capabilities")
        enabled = isinstance(caps, list) and any(isinstance(c, dict) and c.get("tool") == "chi_so_ads"
                  and c.get("bat") is not False for c in caps)
        return enabled and isinstance(people, list) and actor in people
    except Exception:
        return False


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


def _values(row):
    values = {key: _number(row.get(key)) for key in GROUPS["co_ban"]}
    values.update(purchases=_action(row.get("actions"), PURCHASE),
                  revenue=_action(row.get("action_values"), PURCHASE),
                  meta_roas=_action(row.get("purchase_roas"), PURCHASE),
                  messages=_action(row.get("actions"), ("onsite_conversion.messaging_conversation_started_7d",)),
                  leads=_action(row.get("actions"), LEAD),
                  video_3s=_action(row.get("actions"), ("video_view",)),
                  thruplay=_action(row.get("video_thruplay_watched_actions"), ("video_view",)))
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


def _dates(args, now=None):
    today = (now or dt.datetime.now(VN)).astimezone(VN).date()
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
            # Last N completed VN calendar days; today's incomplete data is excluded.
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

    def _url(self, url):
        parsed = urlparse(url)
        path = parsed.path
        if (parsed.scheme != "https" or parsed.netloc != "graph.facebook.com"
                or parsed.username or parsed.fragment or not path.startswith("/" + self.version + "/")):
            raise ValueError("Chặn URL ngoài Graph API.")
        tail = path[len(self.version) + 2:]
        if not (tail == "me/adaccounts" or re.fullmatch(r"act_\d+/insights", tail)):
            raise ValueError("Meta client chỉ cho phép đọc tài khoản và insights.")
        query = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() != "access_token"]
        return parsed._replace(query=urlencode(query)).geturl()

    def _get(self, url, params=None):
        url = self._url(url)
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
        rows, seen = [], set()
        for _ in range(500):
            url = self._url(url)
            if url in seen:
                raise ValueError("Meta lặp trang; không thể đảm bảo đủ số.")
            seen.add(url)
            data = self._get(url, params)
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


def _select(accounts, wanted):
    if wanted == "tat_ca":
        return accounts
    fragments = wanted if isinstance(wanted, list) else [wanted]
    if not fragments or any(not isinstance(f, str) or not f.strip() for f in fragments):
        raise ValueError("Cần tên tài khoản, act_ID hoặc tat_ca.")
    selected = {}
    for fragment in fragments:
        matches = [a for a in accounts if fragment.lower() in str(a.get("name", "")).lower()
                   or str(a.get("id")) == fragment or str(a.get("id")) == "act_" + fragment]
        if not matches:
            raise ValueError("Không tìm thấy tài khoản: " + fragment)
        if len(matches) > 1:
            raise ValueError("Tên tài khoản chưa rõ: " + fragment + ". Chọn act_ID: " +
                             ", ".join(str(a.get("id")) for a in matches))
        selected[matches[0]["id"]] = matches[0]
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


def _private_sheet(title, rows, actor):
    token, url = A._create_sheet(title)
    # Drive v2 fields/enums verified against larksuite/oapi-sdk-go v3.12.0 drive/v2.
    # Close inherited tenant/link sharing BEFORE writing confidential values.
    lark.call("PATCH", f"/open-apis/drive/v2/permissions/{token}/public", query={"type": "sheet"},
              body={"external_access_entity": "closed", "link_share_entity": "closed",
                    "share_entity": "same_tenant", "manage_collaborator_entity": "collaborator_full_access"})
    permission = lark.call("GET", f"/open-apis/drive/v2/permissions/{token}/public", query={"type": "sheet"})
    public = (permission.get("data") or {}).get("permission_public") or {}
    if (public.get("link_share_entity") != "closed" or public.get("external_access_entity") != "closed"
            or public.get("manage_collaborator_entity") != "collaborator_full_access"):
        raise ValueError("Chưa xác minh được Sheet riêng tư; chưa ghi số ads.")
    sheet_id = A._first_sheet_id(token)
    grid_response = lark.call("GET", f"/open-apis/sheets/v3/spreadsheets/{token}/sheets/query")
    grid = next((s.get("grid_properties") or {} for s in
                (grid_response.get("data") or {}).get("sheets", []) if s.get("sheet_id") == sheet_id), {})
    row_count = int(grid.get("row_count") or 200)
    column_count = int(grid.get("column_count") or 20)
    import sheet_lon
    while row_count < len(rows):
        extra = min(5000, len(rows) - row_count)
        sheet_lon._goi("POST", f"/open-apis/sheets/v2/spreadsheets/{token}/dimension_range",
                      body={"dimension": {"sheetId": sheet_id, "majorDimension": "ROWS", "length": extra}})
        row_count += extra
    columns = max((len(row) for row in rows), default=1)
    if columns > column_count:
        sheet_lon._goi("POST", f"/open-apis/sheets/v2/spreadsheets/{token}/dimension_range",
                      body={"dimension": {"sheetId": sheet_id, "majorDimension": "COLUMNS", "length": columns - column_count}})
    for offset in range(0, len(rows), 1000):
        A._write_values(token, sheet_id, rows[offset:offset+1000], dong_dau=offset+1)
        if offset + 1000 < len(rows):
            time.sleep(0.2)
    if not A._grant(token, actor):
        raise ValueError("Chưa chia sẻ được Sheet riêng cho bạn; nhờ chủ agent kiểm quyền Lark.")
    return url


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
        if "tai_khoan" not in args or not any(k in args for k in ("khoang_ngay", "tu_ngay", "den_ngay")):
            raise ValueError("Bạn cần số của tài khoản nào và khoảng thời gian nào? Gọi danh_muc=true để xem các chỉ số.")
        wanted = _metrics(args.get("chi_so", ["co_ban"]))
        start, end = _dates(args)
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
        if "theo_ngay" in args and not isinstance(args["theo_ngay"], bool):
            raise ValueError("theo_ngay phải là true/false.")
        token = os.environ.get("MARK_META_ADS_TOKEN", "").strip()
        if not token:
            raise ValueError("Chưa cấu hình token Meta Ads. Nhờ chủ agent cấu hình MARK_META_ADS_TOKEN chỉ đọc trên VPS.")
        client = MetaClient(token)
        accounts = _select(client.accounts(), args["tai_khoan"])
        if not accounts:
            raise ValueError("Không có tài khoản HAPAS được cấp quyền xem hiệu quả.")
        # Fetch only requested fields plus inputs needed for requested ratios.
        fields = {field for key in wanted for field in METRICS[key][3]}
        fields.update(("account_id", "account_name", "date_start", "date_stop"))
        if level != "account":
            fields.update((level + "_id", level + "_name"))
        parameters = {"fields": ",".join(sorted(fields)), "level": level, "limit": 500,
                      "time_range": json.dumps({"since": start, "until": end}),
                      "use_unified_attribution_setting": "true"}
        if args.get("theo_ngay"):
            parameters["time_increment"] = 1
        if breakdown:
            parameters["breakdowns"] = ",".join(breakdown)
        if args.get("loc"):
            if not isinstance(args["loc"], str) or len(args["loc"]) > 200:
                raise ValueError("loc cần tên chiến dịch tối đa 200 ký tự.")
            parameters["filtering"] = json.dumps([{"field": "campaign.name", "operator": "CONTAIN", "value": args["loc"]}])
        rows, cut = [], False
        for index, account in enumerate(accounts):
            if not re.fullmatch(r"act_\d+", str(account.get("id", ""))) or not account.get("currency"):
                raise ValueError("Meta thiếu mã tài khoản hoặc đơn vị tiền; không xuất tổng sai.")
            data, truncated = client.pages(account["id"] + "/insights", parameters, MAX_ROWS - len(rows))
            for item in data:
                rows.append({"account": account, "data": item, "currency": account["currency"], "values": _values(item)})
            cut = cut or truncated
            if len(rows) >= MAX_ROWS:
                cut = cut or index < len(accounts) - 1
                break
        totals = _totals(rows)
        headers = ["Tài khoản", "Mã TK", "Tiền tệ", "Múi giờ TK", "Từ ngày", "Đến ngày", "Mã đối tượng", "Tên đối tượng", *breakdown,
                   *[METRICS[k][0] + " (" + METRICS[k][1] + ")" for k in wanted]]
        sheet = [headers]
        for row in rows:
            data, account = row["data"], row["account"]
            sheet.append([account.get("name", ""), account["id"], row["currency"], account.get("timezone_name", ""),
                          data.get("date_start", start), data.get("date_stop", end), data.get(level + "_id", account["id"]),
                          data.get(level + "_name", account.get("name", "")), *[data.get(k, "") for k in breakdown],
                          *[_cell(row["values"].get(k)) for k in wanted]])
        sheet.append([])
        for currency, values in totals.items():
            sheet.append([("TỔNG PHẦN ĐÃ ĐỌC" if cut else "TỔNG") + " " + currency, "", currency, "", start, end, "", "",
                          *["" for _ in breakdown], *[_cell(values.get(k)) for k in wanted]])
        sheet.append([f"{start}–{end}; mốc chọn ngày VN (UTC+7), Meta báo theo múi giờ tài khoản. Số theo phân bổ mặc định của Meta. Reach/tần suất/ROAS Meta không cộng tổng. Ô trống = không có số, không phải 0."])
        if cut:
            sheet.append(["ĐÃ CẮT ở 20.000 dòng; tổng chỉ cho phần đã đọc. Hãy thu hẹp ngày/tài khoản."])
        # Recheck immediately before disclosure: list or switch may have changed mid-fetch.
        if not _allowed(actor):
            raise ValueError("Quyền xem số ads đã đổi hoặc không đọc được quyền; chưa xuất Sheet.")
        url = _private_sheet("Số ads HAPAS " + start + "–" + end, sheet, actor)
        summary = "; ".join(currency + ": " + ", ".join(METRICS[k][0] + " " + str(round(values[k], 4))
                       for k in wanted if values.get(k) is not None) for currency, values in totals.items())
        sentence = f"Đã đọc {len(rows)} dòng ({start}–{end})" + ("; đã cắt, tổng chỉ phần đã đọc" if cut else "")
        if summary:
            sentence += "; " + summary
        return tool_result({"link": url, "cau_tong": sentence + ".", "so_dong": len(rows), "bi_cat": cut,
                            "chi_so": wanted, "nguoi_duoc_chia_se": actor})
    except Exception as error:
        return tool_error(_redact(str(error), token)[:500])


SCHEMA = {"name": "chi_so_ads", "description": "Đọc số Meta Ads HAPAS rồi xuất Sheet riêng cho người hỏi có quyền. Hỏi chung: gọi danh_muc=true để liệt kê mọi chỉ số tên Việt, đơn vị, ý nghĩa, cách chia và ngày; hỏi người dùng chọn. Hỏi cụ thể: lấy đúng chi_so được yêu cầu; chép cau_tong nguyên văn, không tự tính. Chỉ đọc ads, API miễn phí; không sửa/tạm dừng. Nhóm cần chuyển chat riêng.",
    "parameters": {"type": "object", "properties": {
        "danh_muc": {"type": "boolean"},
        "tai_khoan": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
        "khoang_ngay": {"type": "string", "enum": ["hom_nay", "hom_qua", "7_ngay", "14_ngay", "30_ngay", "thang_nay", "thang_truoc"]},
        "tu_ngay": {"type": "string"}, "den_ngay": {"type": "string"},
        "cap": {"type": "string", "enum": list(LEVELS)}, "theo_ngay": {"type": "boolean"},
        "chia_theo": {"type": "array", "items": {"type": "string", "enum": list(BREAKDOWNS)}},
        "chi_so": {"type": "array", "items": {"type": "string", "enum": list(METRICS) + list(GROUPS)}},
        "loc": {"type": "string"}}, "additionalProperties": False}}

registry.register(name="chi_so_ads", toolset="social", schema=SCHEMA, handler=_handle,
                  check_fn=lambda: True, requires_env=[], is_async=False,
                  description="Số Meta Ads HAPAS → Sheet riêng", emoji="📊", override=True)
