"""Runner chạy TRONG .venv-scrapling — được web_tool.py gọi qua subprocess.

Vì sao tách venv riêng: venv của Hermes dùng CHUNG với meeting agent. Cài thêm
gói (scrapling kéo theo curl_cffi, playwright, camoufox...) vào đó là đúng kiểu
lây chéo đã tránh suốt. Nên Scrapling sống ở .venv-scrapling và giao tiếp bằng
JSON qua stdin/stdout.

Vào : JSON {"url":..., "mode": "auto|fast|stealth|dynamic", "css":..., "max_chars":...}
Ra  : JSON {"ok":bool, "tier":..., "status":..., "title":..., "text":..., ...}
"""

from __future__ import annotations

import json
import sys

# Console Windows hay là cp1252. Runner nói chuyện với web_tool.py bằng JSON qua
# stdout, mà thông báo lỗi thì tiếng Việt có dấu — thiếu dòng này, đúng lúc thất
# bại (lúc cần thông tin nhất) print() sẽ ném UnicodeEncodeError, stdout rỗng, và
# web_tool chỉ báo được "Runner không trả gì". crawl_runner.py đã tự vệ như vậy;
# ở đây trước giờ phải trông vào PYTHONIOENCODING do người gọi đặt hộ.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ngưỡng coi là "bị chặn": trang trả 200 nhưng HTML quá ngắn (vỏ JS rỗng) hoặc
# chứa dấu hiệu tường bot. Đo thật 27/08/2026 trên dior.com: Fetcher trả 200 với
# vỏn vẹn 2.684 ký tự, ruột là script Akamai Bot Manager.
_MIN_HTML = 20000
_DAU_HIEU = ("sec-bc-tile", "akamai", "access denied", "just a moment", "captcha",
             "page unavailable", "are you a robot", "cf-browser-verification",
             "checking your browser")


def _kham(html: str, status) -> list[str]:
    low = html[:8000].lower()
    xau = [k for k in _DAU_HIEU if k in low]
    if status and int(status) >= 400:
        xau.append(f"http_{status}")
    if len(html) < _MIN_HTML:
        xau.append(f"html_qua_ngan_{len(html)}")
    return xau


def _boc(p, css: str | None, max_chars: int) -> dict:
    html = str(p.html_content)
    t = p.css("title::text")
    out = {
        "status": getattr(p, "status", None),
        "title": str(t[0]).strip() if t else "",
        "html_len": len(html),
        "canh_bao": _kham(html, getattr(p, "status", None)),
    }
    if css:
        try:
            hits = p.css(css)
            out["css_selector"] = css
            out["css_results"] = [str(x)[:400] for x in hits[:80]]
            out["css_count"] = len(hits)
        except Exception as e:  # noqa: BLE001
            out["css_error"] = f"{type(e).__name__}: {e}"[:200]
    try:
        txt = p.get_all_text(ignore_tags=("script", "style"))
    except Exception:  # noqa: BLE001
        txt = ""
    txt = " ".join(str(txt).split())
    out["text"] = txt[:max_chars]
    out["text_len"] = len(txt)
    out["text_truncated"] = len(txt) > max_chars
    return out


def main() -> int:
    try:
        args = json.loads(sys.stdin.read() or "{}")
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"input khong phai JSON: {e}"}))
        return 1

    url = (args.get("url") or "").strip()
    if not url:
        print(json.dumps({"ok": False, "error": "thieu url"}))
        return 1
    mode = (args.get("mode") or "auto").lower()
    css = args.get("css") or None
    max_chars = int(args.get("max_chars") or 6000)

    from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher

    # 'auto' = thử tầng RẺ trước, chỉ leo thang khi thật sự bị chặn. Fetcher là
    # HTTP thuần (nhanh, ~1s); StealthyFetcher/DynamicFetcher phải bật browser
    # (chậm hơn nhiều lần) nên đừng dùng khi không cần.
    thu = {"fast": ["fast"], "stealth": ["stealth"], "dynamic": ["dynamic"]}.get(
        mode, ["fast", "stealth"])

    ket_qua, cuoi = [], None
    for tier in thu:
        try:
            if tier == "fast":
                p = Fetcher.get(url, timeout=30)
            elif tier == "stealth":
                p = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=60000)
            else:
                p = DynamicFetcher.fetch(url, headless=True, network_idle=True, timeout=60000)
            d = _boc(p, css, max_chars)
            d["tier"] = tier
            cuoi = d
            ket_qua.append({"tier": tier, "status": d["status"],
                            "html_len": d["html_len"], "canh_bao": d["canh_bao"]})
            if not d["canh_bao"]:
                d["ok"] = True
                d["da_thu"] = ket_qua
                print(json.dumps(d, ensure_ascii=False))
                return 0
        except Exception as e:  # noqa: BLE001
            ket_qua.append({"tier": tier, "loi": f"{type(e).__name__}: {e}"[:200]})

    # Mọi tầng đều có cảnh báo -> vẫn trả dữ liệu lấy được nhưng KHÔNG nói là ok.
    # Im lặng ở đây sẽ khiến agent tưởng trang trống, rồi kết luận sai về đối thủ.
    out = cuoi or {}
    out.update({"ok": False, "da_thu": ket_qua,
                "error": "Mọi tầng fetcher đều gặp dấu hiệu bị chặn hoặc lỗi. "
                         "Dữ liệu dưới đây (nếu có) KHÔNG đầy đủ — đừng kết luận "
                         "là trang không có nội dung."})
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
