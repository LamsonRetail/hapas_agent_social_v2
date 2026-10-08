"""Register a `web_scrape` tool — đọc WEBSITE công khai bằng Scrapling.

Vì sao cần, khi đã có browser
------------------------------
`browser_navigate` của Hermes đọc được web thường nhưng vấp ở site có tường bot.
Scrapling có 3 tầng fetcher (HTTP + TLS impersonation -> browser stealth ->
Playwright) và tự leo thang, nên phủ rộng hơn và tầng đầu thì NHANH HƠN NHIỀU
(HTTP thuần ~1s, không phải bật browser).

Chạy ở venv RIÊNG (.venv-scrapling), gọi qua subprocess
--------------------------------------------------------
venv của Hermes dùng CHUNG với meeting agent. Cài scrapling (kéo theo curl_cffi,
playwright, camoufox...) vào đó là đúng kiểu lây chéo đã tránh suốt. Nên tách
venv, giao tiếp bằng JSON qua stdin/stdout — cùng pattern với lark-cli.

Cào được gì — đo thật 27/08/2026
---------------------------------
ĐƯỢC (chỉ cần tầng `fast`, ~1s):
    juno.vn 3.6M ký tự · vascara.com 1.4M · hapas.vn 1.0M · charleskeith.vn 459K
KHÔNG ĐƯỢC:
    dior.com — Akamai Bot Manager. CẢ BA tầng đều thất bại: Fetcher trả 200
    nhưng chỉ 2.684 ký tự (vỏ JS rỗng), StealthyFetcher và DynamicFetcher đều
    403 "Page unavailable". README của Scrapling chỉ hứa bypass Cloudflare;
    Akamai là hệ khác. Các nhà mốt quốc tế hạng sang gần như đều dùng loại này.

Và KHÔNG thay được Apify cho mạng xã hội: chặn ở TikTok/IG/FB là ĐĂNG NHẬP +
chữ ký request, không phải bot detection.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cli_support import env_tien_trinh_con
from config import config

from tools.registry import registry, tool_error, tool_result  # type: ignore

_TOOLSET = "browser"          # đi kèm nhóm browser sẵn có
_HERE = Path(__file__).resolve().parent
_PY = _HERE / ".venv-scrapling" / "Scripts" / "python.exe"
_RUNNER = _HERE / "scrapling_runner.py"
_TIMEOUT = 150
_MAX_CHARS = 20000

# Site đã biết chắc là chặn được cả 3 tầng -> nói trước cho khỏi tốn 2 phút chờ.
_DA_BIET_CHAN = {"dior.com": "Akamai Bot Manager (đã test 27/08/2026: cả 3 tầng đều bị chặn)"}


SCHEMA = {
    "name": "web_scrape",
    "description": (
        "Đọc nội dung một TRANG WEB công khai (không cần đăng nhập) bằng Scrapling — "
        "nhanh và vượt được nhiều tường chống bot hơn `browser_navigate`. Dùng để theo "
        "dõi WEBSITE đối thủ: giá, bộ sưu tập mới, khuyến mãi, sản phẩm, tin tức, trang "
        "campaign.\n"
        "KHÔNG dùng cho mạng xã hội: TikTok/Instagram/Facebook/Threads chặn bằng ĐĂNG "
        "NHẬP nên tool này bó tay — hãy dùng `social_listen` (bài đăng) hoặc "
        "`fb_ads_library` (quảng cáo).\n"
        "BẮT BUỘC KHI TRẢ LỜI:\n"
        "- Nếu `ok`=false thì dữ liệu KHÔNG đầy đủ (bị tường bot chặn). PHẢI nói thẳng "
        "là chưa đọc được trang đó, TUYỆT ĐỐI KHÔNG kết luận 'trang không có nội dung' "
        "hay bịa thông tin về đối thủ. Đọc `da_thu` để biết đã thử những tầng nào.\n"
        "- `text_truncated`=true nghĩa là còn nội dung phía sau chưa lấy — nói rõ nếu "
        "điều đó ảnh hưởng kết luận.\n"
        "- Dùng `css` khi cần lấy đúng phần tử (vd giá sản phẩm: '.product-price::text').\n"
        "- Một số site hạng sang (dior.com, chanel.com…) dùng Akamai và KHÔNG đọc được — "
        "báo thẳng, đừng thử vòng vo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL đầy đủ của trang cần đọc."},
            "mode": {"type": "string",
                     "description": ("'auto' (mặc định: thử HTTP nhanh trước, bị chặn mới "
                                     "bật browser), 'fast' (chỉ HTTP), 'stealth' hoặc "
                                     "'dynamic' (ép dùng browser, chậm hơn nhiều).")},
            "css": {"type": "string",
                    "description": "CSS selector để lấy đúng phần tử, vd '.price::text', 'h2 a::attr(href)'."},
            "max_chars": {"type": "integer", "description": "Số ký tự văn bản tối đa (mặc định 6000, trần 20000)."},
        },
        "required": ["url"],
    },
}


def _handle(args: dict, **kwargs) -> str:
    url = str(args.get("url") or "").strip()
    if not url:
        return tool_error("Thiếu `url`.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    low = url.lower()
    for dom, ly_do in _DA_BIET_CHAN.items():
        if dom in low:
            return tool_error(
                f"{dom} đã được xác minh là KHÔNG đọc được: {ly_do}. Hãy nói thẳng với "
                f"người dùng là chưa đọc được site này, đừng bịa nội dung. Gợi ý thay "
                f"thế: tra quảng cáo của họ bằng `fb_ads_library`, hoặc theo dõi các "
                f"đối thủ trong nước (juno.vn, vascara.com, charleskeith.vn — đã test đọc tốt)."
            )
    if any(k in low for k in ("tiktok.com", "instagram.com", "facebook.com", "threads.net")):
        return tool_error(
            "Mạng xã hội chặn bằng ĐĂNG NHẬP, tool này không đọc được. Dùng "
            "`social_listen` cho bài đăng, `social_deep_dive` cho bình luận, hoặc "
            "`fb_ads_library` cho quảng cáo.")

    if not _PY.exists():
        return tool_error(
            f"Chưa cài Scrapling. Tạo venv rồi cài:\n"
            f"  py -3.12 -m venv .venv-scrapling\n"
            f"  .venv-scrapling\\Scripts\\python.exe -m pip install \"scrapling[fetchers]\"\n"
            f"  .venv-scrapling\\Scripts\\scrapling.exe install")

    try:
        mc = int(args.get("max_chars") or 6000)
    except (TypeError, ValueError):
        mc = 6000
    payload = json.dumps({
        "url": url,
        "mode": (args.get("mode") or "auto").lower(),
        "css": args.get("css") or None,
        "max_chars": max(500, min(mc, _MAX_CHARS)),
    }, ensure_ascii=False)

    env = env_tien_trinh_con()  # không mang token Meta vào Scrapling
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run([str(_PY), str(_RUNNER)], input=payload, env=env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=_TIMEOUT, cwd=str(config.here))
    except subprocess.TimeoutExpired:
        return tool_error(f"Quá {_TIMEOUT}s. Thử `mode='fast'` hoặc giảm max_chars.")
    except OSError as e:
        return tool_error(f"Không chạy được runner: {type(e).__name__}: {e}")

    out = (proc.stdout or "").strip()
    if not out:
        return tool_error(f"Runner không trả gì. stderr: {(proc.stderr or '')[:400]}")
    try:
        d = json.loads(out.splitlines()[-1])
    except json.JSONDecodeError:
        return tool_error(f"Runner trả dữ liệu không phải JSON: {out[:400]}")

    d["url"] = url
    if not d.get("ok"):
        d.setdefault("error", "Không đọc được đầy đủ.")
        d["note"] = ("Trang bị tường chống bot chặn. PHẢI nói thẳng là chưa đọc được, "
                     "KHÔNG kết luận trang trống và KHÔNG bịa nội dung về đối thủ.")
    return tool_result(**d)


def _available() -> bool:
    return _PY.exists() and _RUNNER.exists()


def register() -> None:
    try:
        registry.register(
            name="web_scrape", toolset=_TOOLSET, schema=SCHEMA, handler=_handle,
            check_fn=_available, requires_env=[], is_async=False,
            description="Đọc website công khai bằng Scrapling (tự leo thang khi bị chặn)",
            emoji="\U0001f310", override=True,
        )
    except Exception as e:
        print(f"[web_tool] register warning: {e}")


register()
