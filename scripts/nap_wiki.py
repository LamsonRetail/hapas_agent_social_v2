"""Quét Wiki theo khai báo trên console rồi nạp vào não Mark.

    python scripts/nap_wiki.py            # quét + xem sẽ nhập gì, KHÔNG ghi
    python scripts/nap_wiki.py --day      # nhập thật
    python scripts/nap_wiki.py --url <link>   # thử một link, không cần khai báo

LUỒNG
    console: chủ agent dán link node gốc ở khối Kiến thức  →  agents.wiki_source
    agent  : đọc khai báo qua /v1/self/directory, quét bằng token BOT của chính mình
    agent  : bóc tới mục H1, nhập, rồi báo kết quả ngược lên console (last_scan)

VÌ SAO AGENT ĐỌC CHỨ KHÔNG PHẢI PLATFORM
ACL Wiki cấp theo từng space cho từng bot. Node nào bot không đọc được thì cũng không
nhập được — để platform đọc bằng đường khác sẽ cho ra bản đồ nội dung KHÁC với thứ
agent thật sự lấy được, và người dùng sẽ tin vào bản đồ sai đó. Nên chỗ quét phải
đúng là chỗ sẽ nhập.

VÌ SAO MẶC ĐỊNH KHÔNG GHI
Wiki là nơi người ta sửa dở dang. Một người lưu nửa chừng mà agent nhập ngay là câu
trả lời cho người khác đổi theo, không ai duyệt. Lấy nguyên tắc này từ
`watch_wiki.py` của agent HR: phát hiện đổi thì BÁO, nút cuối vẫn là người.

CHỈ ĐỌC WIKI. Không ghi Wiki, không sửa node nào.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

for _l in (sys.stdout, sys.stderr):
    try:
        _l.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

import config  # noqa: E402  — nạp .env
import lark_client as lark  # noqa: E402

PLATFORM = "https://platform.34-124-212-76.sslip.io"
WEB = "https://app.34-124-212-76.sslip.io"
AID = "AG-SOCIAL-LISTENING"

B_H1 = 3
B_TEXT = 2
#: Trần an toàn: cây Wiki có thể rất rộng, và mỗi node là một lời gọi API.
MAX_NODE = int(__import__("os").environ.get("LSR_WIKI_MAX_NODE", "200"))
MAX_SAU = int(__import__("os").environ.get("LSR_WIKI_MAX_DEPTH", "6"))


def _token_nguoi_dung() -> str:
    f = pathlib.Path.home() / ".lsr" / "token"
    return f.read_text(encoding="utf-8").strip() if f.is_file() else ""


def _goi_web(duong: str, body=None):
    tok = _token_nguoi_dung()
    h = {"Cookie": f"lsr_session={tok}"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(WEB + duong, data=data,
                                 method="POST" if data is not None else "GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"loi": e.read().decode("utf-8", "replace")[:200]}


def khai_bao() -> dict:
    """Đọc `wiki_source` của CHÍNH agent này từ danh bạ."""
    import os
    key = (os.environ.get("LSR_TELEMETRY_API_KEY") or "").strip()
    req = urllib.request.Request(PLATFORM + "/v1/self/directory",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        print(f"  không đọc được danh bạ: {type(e).__name__}: {e}")
        return {}
    toi = str(d.get("caller") or "").upper()
    hang = next((a for a in (d.get("agents") or [])
                 if str(a.get("agent_id", "")).upper() == toi), None)
    return (hang or {}).get("wiki_source") or {}


# ───────────────────────────── đọc Wiki (chỉ đọc) ────────────────────────────
def token_tu_link(url: str) -> str:
    url = (url or "").strip()
    if "/wiki/" not in url:
        return ""
    return url.rsplit("/wiki/", 1)[1].split("?")[0].split("#")[0].strip()


#: Lỗi gần nhất khi gọi Lark — để phân biệt "bot không có quyền" với "code sai".
_LOI_CUOI = {"gi": ""}


def lay_node(token: str) -> dict | None:
    """None = không lấy được. Lý do THẬT nằm ở `_LOI_CUOI`, đừng đoán.

    Bản đầu nuốt mọi exception rồi báo "bot chưa được cấp quyền đọc". Hoá ra là tôi
    gõ `params=` trong khi `lark.call` nhận `query=` — một TypeError bị đọc thành
    thiếu quyền, và tôi đi nhầm hướng nửa ngày, còn viết cả vào mô tả PR.
    """
    try:
        d = lark.call("GET", "/open-apis/wiki/v2/spaces/get_node",
                      query={"token": token, "obj_type": "wiki"})
    except Exception as e:
        _LOI_CUOI["gi"] = f"{type(e).__name__}: {e}"
        return None
    if d and d.get("code") not in (0, None):
        _LOI_CUOI["gi"] = f"Lark code={d.get('code')} · {d.get('msg')}"
        return None
    return (((d or {}).get("data") or {}).get("node")) or None


def liet_ke_con(space_id: str, cha: str) -> list[dict] | None:
    """None = KHÔNG ĐỌC ĐƯỢC (thiếu quyền). [] = đọc được nhưng rỗng.

    Phân biệt hai cái này là quan trọng: gộp chung thành [] sẽ báo "nhánh trống"
    cho một nhánh thật ra đầy tài liệu mà bot chưa được cấp quyền.
    """
    ra: list[dict] = []
    trang = ""
    for _ in range(20):
        p: dict = {"page_size": 50}
        if cha:
            p["parent_node_token"] = cha
        if trang:
            p["page_token"] = trang
        try:
            d = lark.call("GET", f"/open-apis/wiki/v2/spaces/{space_id}/nodes", query=p)
        except Exception:
            return None
        if not d or d.get("code") not in (0, None):
            return None
        tp = d.get("data") or {}
        ra.extend(tp.get("items") or [])
        if not tp.get("has_more"):
            break
        trang = tp.get("page_token") or ""
        if not trang:
            break
    return ra


def _chu(block: dict) -> str:
    """Gộp các đoạn chữ trong một block thành một dòng."""
    for k in ("text", "heading1", "heading2", "heading3", "bullet", "ordered", "code"):
        el = (block.get(k) or {}).get("elements")
        if el:
            return "".join((e.get("text_run") or {}).get("content", "") for e in el)
    return ""


def lay_block(doc_id: str) -> list[dict] | None:
    ra: list[dict] = []
    trang = ""
    for _ in range(20):
        p: dict = {"page_size": 500}
        if trang:
            p["page_token"] = trang
        try:
            d = lark.call("GET", f"/open-apis/docx/v1/documents/{doc_id}/blocks", query=p)
        except Exception:
            return None
        if not d or d.get("code") not in (0, None):
            return None
        tp = d.get("data") or {}
        ra.extend(tp.get("items") or [])
        if not tp.get("has_more"):
            break
        trang = tp.get("page_token") or ""
        if not trang:
            break
    return ra


def cat_theo_h1(blocks: list[dict]) -> list[tuple[str, list[str]]]:
    """Cắt tài liệu theo mục H1 — đúng độ mịn ADR `WIKI` chốt.

    Bỏ phần đầu tài liệu TRƯỚC H1 đầu tiên: đó thường là mục lục hoặc lời dẫn, đưa vào
    kho làm nhiễu phần trích dẫn.
    """
    muc: list[tuple[str, list[str]]] = []
    tieu_de: str | None = None
    dong: list[str] = []
    for b in blocks:
        if b.get("block_type") == B_H1:
            if tieu_de is not None:
                muc.append((tieu_de, dong))
            tieu_de = re.sub(r"\*\*", "", _chu(b)).strip() or "(không tiêu đề)"
            dong = []
            continue
        if tieu_de is None:
            continue
        t = _chu(b).strip()
        if t:
            dong.append(t)
    if tieu_de is not None:
        muc.append((tieu_de, dong))
    return muc


_BI_MAT = re.compile(
    r"(?i)\b(?:cli_[a-z0-9]{12,}|apify_api_[A-Za-z0-9]{20,}|lsr_tel_[A-Za-z0-9]{20,}"
    r"|[A-Za-z0-9_\-]{32,}\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,})\b")


def che_bi_mat(s: str) -> tuple[str, int]:
    """Wiki là nơi người ta dán nhầm token. Nhập thẳng là đưa bí mật vào chỗ RAG
    trích ra cho mọi câu hỏi — không có nút hoàn tác cho việc đã trả lời."""
    ra, n = _BI_MAT.subn("«đã che»", s)
    return ra, n


# ──────────────────────────────── quét cây ───────────────────────────────────
def quet(url: str) -> dict:
    tok = token_tu_link(url)
    if not tok:
        return {"loi": f"link không có /wiki/<node>: {url[:70]}"}
    goc = lay_node(tok)
    if not goc:
        return {"loi": "không phân giải được node gốc — "
                       + (_LOI_CUOI["gi"] or "Lark không trả node nào")}
    space = goc.get("space_id") or ""
    tham: list[dict] = []
    khong_doc = 0

    def di(cha: str, sau: int) -> None:
        nonlocal khong_doc
        if sau > MAX_SAU or len(tham) >= MAX_NODE:
            return
        con = liet_ke_con(space, cha)
        if con is None:
            khong_doc += 1
            return
        for n in con:
            if len(tham) >= MAX_NODE:
                return
            tham.append({"token": n.get("node_token"), "title": n.get("title") or "",
                         "obj_type": n.get("obj_type"), "obj_token": n.get("obj_token"),
                         "sua_luc": n.get("obj_edit_time"), "sau": sau})
            if n.get("has_child"):
                di(n.get("node_token") or "", sau + 1)

    tham.append({"token": goc.get("node_token"), "title": goc.get("title") or "",
                 "obj_type": goc.get("obj_type"), "obj_token": goc.get("obj_token"),
                 "sua_luc": goc.get("obj_edit_time"), "sau": 0})
    di(goc.get("node_token") or "", 1)
    return {"space_id": space, "nodes": tham, "khong_doc": khong_doc,
            "cham_tran": len(tham) >= MAX_NODE}


def boc(nodes: list[dict]) -> tuple[list[dict], int]:
    """Mỗi mục H1 thành một tài liệu. Trả (tài liệu, số bí mật đã che)."""
    ra: list[dict] = []
    che = 0
    for n in nodes:
        if n.get("obj_type") != "docx" or not n.get("obj_token"):
            continue
        blocks = lay_block(n["obj_token"])
        if blocks is None:
            continue
        for tieu_de, dong in cat_theo_h1(blocks):
            than = "\n".join(dong).strip()
            if not than:
                continue
            than, k = che_bi_mat(than)
            che += k
            an_toan = re.sub(r"[^\w\s\-.]", "", f"{n['title']}-{tieu_de}").strip()
            an_toan = re.sub(r"\s+", "_", an_toan)[:80]
            ra.append({"name": f"wiki_{an_toan}.md",
                       "content": f"# {tieu_de}\n\n_Nguồn Wiki: {n['title']}_\n\n{than}\n"})
    return ra, che


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", action="store_true", help="nhập thật (mặc định chỉ xem)")
    ap.add_argument("--url", default="", help="thử một link, bỏ qua khai báo")
    args = ap.parse_args()

    kb = khai_bao()
    url = args.url.strip() or (kb.get("root_url") or "")
    print("\n  KHAI BÁO TRÊN CONSOLE")
    print("  " + "─" * 74)
    print(f"    bật        : {kb.get('enabled')}")
    print(f"    link gốc   : {kb.get('root_url') or '(chưa đặt)'}")
    print(f"    độ mịn     : {kb.get('selection_granularity') or '—'}")
    if not url:
        print("\n  Chưa có link. Dán link node Wiki ở khối Kiến thức trên console.\n")
        return 0
    if not args.url and not kb.get("enabled"):
        print("\n  Nguồn đang TẮT — không quét. Bật trên console, hoặc dùng --url để thử.\n")
        return 0

    print(f"\n  QUÉT {url[:66]}")
    print("  " + "─" * 74)
    kq = quet(url)
    if kq.get("loi"):
        print(f"    TRƯỢT {kq['loi']}\n")
        return 1
    nodes = kq["nodes"]
    print(f"    {len(nodes)} node · {kq['khong_doc']} nhánh KHÔNG đọc được"
          + (" · CHẠM TRẦN" if kq["cham_tran"] else ""))
    for n in nodes[:12]:
        print(f"      {'  ' * n['sau']}{n['title'][:56]}  [{n['obj_type']}]")
    if len(nodes) > 12:
        print(f"      … còn {len(nodes) - 12} node")

    tai_lieu, che = boc(nodes)
    print(f"\n  BÓC TỚI MỤC H1 → {len(tai_lieu)} tài liệu"
          + (f" · đã che {che} chuỗi giống bí mật" if che else ""))
    for d in tai_lieu[:12]:
        print(f"      {d['name'][:56]:<56} {len(d['content']):>6} ký tự")
    if len(tai_lieu) > 12:
        print(f"      … còn {len(tai_lieu) - 12} tài liệu")

    if not tai_lieu:
        print("\n  Không có mục H1 nào để nhập.\n")
        return 0
    if not args.day:
        print(f"\n  {len(tai_lieu)} tài liệu sẽ được nhập. Chạy lại với --day để làm thật.\n")
        return 0

    print(f"\n  NHẬP {len(tai_lieu)} tài liệu")
    print("  " + "─" * 74)
    da = 0
    for i in range(0, len(tai_lieu), 20):      # API trần 20 tệp mỗi lần
        lo = tai_lieu[i:i + 20]
        c, r = _goi_web(f"/api/agents/{AID}/knowledge", {"files": lo})
        if c != 200:
            print(f"    TRƯỢT HTTP {c} · {json.dumps(r, ensure_ascii=False)[:160]}")
            return 1
        da += len(lo)
        print(f"    đạt  lô {i // 20 + 1}: {len(lo)} tệp")

    # Báo ngược lên console để người dùng thấy lần quét gần nhất.
    from datetime import datetime, timezone
    moi = {**kb, "last_scan": {
        "at": datetime.now(timezone.utc).isoformat(),
        "nodes": len(nodes), "sections": len(tai_lieu), "imported": da,
        "unreadable": kq["khong_doc"],
        "note": ("Đã chạm trần số node — cây còn nhánh chưa quét."
                 if kq["cham_tran"] else ""),
    }}
    c, _ = _goi_web(f"/api/agents/{AID}/profile", {"wiki_source": moi})
    print(f"    {'đạt ' if c == 200 else 'TRƯỢT'} báo kết quả lên console (HTTP {c})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
