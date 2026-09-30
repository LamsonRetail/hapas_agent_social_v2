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
import hashlib
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
#: block_type 3..11 = tiêu đề H1..H9 của Lark docx.
_CAP_TIEU_DE = {3 + i: i + 1 for i in range(9)}

#: Ba cách nhập MỘT node — chủ agent chọn cho từng node trên console (`che_do_node`).
#: Mặc định nhập cả node: một node là một tài liệu, tên là tiêu đề node, không mất gì.
#: Bản cũ chỉ cắt theo H1 nên tài liệu không dùng H1 (vd "Scope") bị bỏ CẢ tài liệu,
#: còn "Daily Standup" 64 H1 theo ngày thì chiếm trọn kho.
CA_NODE, THEO_H1, BO_QUA = "ca_node", "h1", "bo_qua"
CHE_DO = (CA_NODE, THEO_H1, BO_QUA)
#: API kiến thức nhận tối đa 400 KB mỗi tệp; để dư cho phần đầu và ký tự nhiều byte.
MAX_KY_TU_NODE = 300_000
#: Khối NHÚNG trong tài liệu docx mà bộ đọc chưa bóc được nội dung: 18 = Base, 30 = Sheet.
#: "Scope" (30/09) chỉ có tiêu đề + một Sheet nhúng — báo "tài liệu trống" là sai lý do.
_KHOI_NHUNG = {18: "Base", 30: "Sheet"}
#: Node không phải tài liệu thì chưa nhập được — nói rõ loại gì, đừng để "đã nhập 0".
_LY_DO_LOAI = {"bitable": "Base — chưa nhập được, chỉ nhập tài liệu",
               "sheet": "Sheet — chưa nhập được, chỉ nhập tài liệu",
               "mindnote": "Mindnote — chưa nhập được, chỉ nhập tài liệu",
               "file": "Tệp đính kèm — chưa nhập được, chỉ nhập tài liệu",
               "slides": "Slides — chưa nhập được, chỉ nhập tài liệu"}
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
    for k in ("text", *(f"heading{i}" for i in range(1, 10)), "bullet", "ordered",
              "code", "quote", "todo"):
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


def cat_theo_h1(blocks: list[dict]) -> list[tuple[str, list[str], str]]:
    """Cắt tài liệu theo mục H1 — đúng độ mịn ADR `WIKI` chốt.

    Bỏ phần đầu tài liệu TRƯỚC H1 đầu tiên: đó thường là mục lục hoặc lời dẫn, đưa vào
    kho làm nhiễu phần trích dẫn.
    """
    muc: list[tuple[str, list[str], str]] = []
    tieu_de: str | None = None
    dong: list[str] = []
    neo = ""          # block_id của chính dòng H1 — dùng làm neo trong link
    for b in blocks:
        if b.get("block_type") == B_H1:
            if tieu_de is not None:
                muc.append((tieu_de, dong, neo))
            tieu_de = re.sub(r"\*\*", "", _chu(b)).strip() or "(không tiêu đề)"
            neo = str(b.get("block_id") or "")
            dong = []
            continue
        if tieu_de is None:
            continue
        t = _chu(b).strip()
        if t:
            dong.append(t)
    if tieu_de is not None:
        muc.append((tieu_de, dong, neo))
    return muc


def van_ban_ca_node(blocks: list[dict]) -> str:
    """Cả tài liệu thành markdown, GIỮ tiêu đề (##, ###…) ngay trong nội dung.

    Platform tự cắt tài liệu thành mẩu ~1.200 ký tự để tra. Bỏ tiêu đề thì một mẩu giữa
    "Daily Standup" chỉ còn "đã xong X" mà không biết của ngày nào. H1 của tài liệu thành
    `##` vì `#` đã là tiêu đề node ở đầu tệp.
    """
    dong: list[str] = []
    for b in blocks:
        t = _chu(b).strip()
        if not t:
            continue
        cap = _CAP_TIEU_DE.get(b.get("block_type"))
        dong.append(f"{'#' * min(cap + 1, 6)} {re.sub(r'[*][*]', '', t)}" if cap else t)
    return "\n\n".join(dong)


def _ten_an_toan(s: str) -> str:
    return re.sub(r"\s+", "_", re.sub(r"[^\w\s\-.]", "", s).strip())[:72]


def _link_muc(node_token: str, neo: str) -> str:
    """Link về đúng mục H1 trong Wiki.

    Phần NODE luôn đúng — đó là link người dùng vẫn mở hằng ngày. Phần neo `#block_id`
    là cố gắng thêm: Lark xử lý neo ở phía trình duyệt nên không kiểm được từ server.
    Neo sai thì trang vẫn mở đúng tài liệu, chỉ là không nhảy tới mục — hỏng nhẹ, nên
    đáng để thêm.
    """
    import os as _os
    goc = (_os.environ.get("LARK_WIKI_BASE_URL")
           or "https://o4pvcegwn6b.sg.larksuite.com").rstrip("/")
    u = f"{goc}/wiki/{node_token}"
    return f"{u}#{neo}" if neo else u


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


def boc(nodes: list[dict], che_do: dict | None = None
        ) -> tuple[list[dict], int, list[dict]]:
    """Mỗi node thành tài liệu theo lựa chọn của chủ agent (`che_do`: token → cách nhập).

    Trả (tài liệu, số bí mật đã che, chi tiết từng node). Chi tiết là thứ console hiện
    thành danh sách node có ô chọn — nên node bị bỏ qua cũng phải có dòng kèm LÝ DO,
    không thì người dùng lại thấy "đã nhập 0" mà không biết vì sao.
    """
    che_do = che_do or {}
    ra: list[dict] = []
    chi_tiet: list[dict] = []
    che = 0
    for n in nodes:
        tok = str(n.get("token") or "")
        ten_node = n.get("title") or ""
        muon = che_do.get(tok) if che_do.get(tok) in CHE_DO else CA_NODE
        ct = {"token": tok, "title": ten_node, "loai": n.get("obj_type") or "",
              "sau": n.get("sau", 0), "h1": 0, "che_do": muon, "muc": 0, "ly_do": ""}
        chi_tiet.append(ct)
        if n.get("obj_type") != "docx" or not n.get("obj_token"):
            ct["ly_do"] = _LY_DO_LOAI.get(n.get("obj_type"), "không phải tài liệu")
            continue
        if muon == BO_QUA:
            ct["ly_do"] = "chủ agent chọn bỏ qua"
            continue
        blocks = lay_block(n["obj_token"])
        if blocks is None:
            ct["ly_do"] = "bot không đọc được tài liệu này"
            continue
        muc = cat_theo_h1(blocks)
        ct["h1"] = len(muc)
        nhung = [_KHOI_NHUNG[b["block_type"]] for b in blocks
                 if b.get("block_type") in _KHOI_NHUNG]
        bang = (f"{len(nhung)} bảng nhúng ({', '.join(sorted(set(nhung)))}) chưa đọc được"
                if nhung else "")

        if muon == THEO_H1 and muc:
            for i, (tieu_de, dong, neo) in enumerate(muc):
                than = "\n".join(dong).strip()
                if not than:
                    continue
                than, k = che_bi_mat(than)
                che += k
                # Tên phải DUY NHẤT. API kiến thức thay thế theo tên, nên hai mục trùng
                # tên là mục sau đè mục trước — mất im lặng, không lỗi, không ai biết.
                # Xảy ra thật ở nhánh này: hai mục "Daily Standup / 15092026" trong cùng
                # một cây. Gắn thêm vân tay của node + số thứ tự mục.
                van_tay = hashlib.sha256(
                    f"{tok}|{i}|{tieu_de}".encode("utf-8")).hexdigest()[:6]
                link = _link_muc(tok, neo)
                ra.append({"name": f"wiki_{_ten_an_toan(f'{ten_node}-{tieu_de}')}-{van_tay}.md",
                           "source_url": link,
                           "content": (f"# {tieu_de}\n\n_Nguồn Wiki: {ten_node}"
                                       f" — {link}_\n\n{than}\n")})
                ct["muc"] += 1
            continue

        # Cả node — mặc định, và là đường lùi khi chọn tách H1 mà tài liệu không có H1.
        if muon == THEO_H1:
            ct["ly_do"] = "không có tiêu đề H1 — đã nhập cả node"
        than = van_ban_ca_node(blocks)
        # Dòng tiêu đề trang (block 1) trùng tên node — không tính là có nội dung.
        co_chu = any(_chu(b).strip() for b in blocks if b.get("block_type") != 1)
        if not co_chu:
            ct["ly_do"] = (f"chỉ có {bang} — chưa nhập được" if bang else "tài liệu trống")
            continue
        if bang:
            ct["ly_do"] = "; ".join(x for x in (ct["ly_do"], f"bỏ qua {bang}") if x)
        if len(than) > MAX_KY_TU_NODE:
            than = than[:MAX_KY_TU_NODE]
            ct["ly_do"] = "; ".join(x for x in (
                ct["ly_do"], "dài quá, chỉ nhập 300.000 ký tự đầu — nên chọn Tách theo H1") if x)
        than, k = che_bi_mat(than)
        che += k
        link = _link_muc(tok, "")
        # Vân tay theo node: nhập lại cùng node là THAY đúng tài liệu cũ, không sinh bản mới.
        van_tay = hashlib.sha256(f"{tok}|{CA_NODE}".encode("utf-8")).hexdigest()[:6]
        ra.append({"name": f"wiki_{_ten_an_toan(ten_node) or 'node'}-{van_tay}.md",
                   "source_url": link,
                   "content": f"# {ten_node}\n\n_Nguồn Wiki: {ten_node} — {link}_\n\n{than}\n"})
        ct["muc"] = 1
    return ra, che, chi_tiet


def ten_can_don(da_co: list[dict], ten_moi: set[str], chi_tiet: list[dict]) -> list[str]:
    """Tài liệu Wiki cũ phải dọn sau một lần nhập ĐỦ.

    Chỉ đụng tài liệu `wiki_…` có link về một node mà lượt này ĐỌC ĐƯỢC, và lần này không
    còn tên đó — tức node đổi cách nhập (64 mục H1 → một tài liệu), bị chọn bỏ qua, hoặc
    mục H1 đã bị xoá khỏi tài liệu. Node bot không đọc được, hay đã rời khỏi cây, thì KHÔNG
    xoá: có thể bot chỉ tạm mất quyền, và xoá nhầm kiến thức là thứ không ai thấy để kêu.
    Tài liệu .md nạp tay không có tiền tố `wiki_` nên không bao giờ nằm trong danh sách.
    """
    doc_duoc = {c["token"] for c in chi_tiet
                if c.get("token") and c.get("ly_do") != "bot không đọc được tài liệu này"}
    ra: list[str] = []
    for d in da_co or []:
        ten = str(d.get("name") or "")
        if not ten.startswith("wiki_") or ten in ten_moi:
            continue
        tok = token_tu_link(str(d.get("source_url") or ""))
        if tok and tok in doc_duoc:
            ra.append(ten)
    return ra


def don_tai_lieu_cu(ten_moi: set[str], chi_tiet: list[dict], goi) -> int:
    """Đọc kho, xoá tài liệu Wiki cũ theo `ten_can_don`. Trả số đã xoá (0 nếu lỗi).

    `goi(duong, body=None) -> (status, dict)` — truyền vào để hai nơi gọi (chạy tay và
    nhịp nền) dùng chung một luật dọn, mỗi nơi một cách xác thực.
    """
    c, d = goi(f"/api/agents/{AID}/knowledge")
    if c != 200:
        return 0
    xoa = ten_can_don(d.get("documents") or [], ten_moi, chi_tiet)
    if not xoa:
        return 0
    c, r = goi(f"/api/agents/{AID}/knowledge", {"delete": xoa[:500]})
    return int(r.get("n_files") or len(xoa[:500])) if c == 200 else 0


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

    tai_lieu, che, chi_tiet = boc(nodes, kb.get("che_do_node") or {})
    print(f"\n  BÓC THEO TỪNG NODE → {len(tai_lieu)} tài liệu"
          + (f" · đã che {che} chuỗi giống bí mật" if che else ""))
    for c in chi_tiet[:20]:
        print(f"      {c['title'][:40]:<40} [{c['loai']}] {c['che_do']:<7} "
              f"H1={c['h1']:<3} → {c['muc']} tài liệu {c['ly_do']}")
    for d in tai_lieu[:12]:
        print(f"      {d['name'][:56]:<56} {len(d['content']):>6} ký tự")
    if len(tai_lieu) > 12:
        print(f"      … còn {len(tai_lieu) - 12} tài liệu")

    if not tai_lieu:
        print("\n  Không có tài liệu nào để nhập (xem lý do từng node ở trên).\n")
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

    don = don_tai_lieu_cu({d["name"] for d in tai_lieu}, chi_tiet, _goi_web)
    print(f"    đạt  dọn {don} tài liệu Wiki cũ không còn dùng")

    # Báo ngược lên console để người dùng thấy lần quét gần nhất. CHỈ gửi `last_scan`:
    # server gộp theo khoá, gửi cả khai báo đọc lúc đầu là đè mất lựa chọn người dùng
    # vừa đổi trong lúc đang quét.
    from datetime import datetime, timezone
    moi = {"last_scan": {
        "at": datetime.now(timezone.utc).isoformat(),
        "nodes": len(nodes), "sections": len(tai_lieu), "imported": da, "da_don": don,
        "unreadable": kq["khong_doc"], "chi_tiet": chi_tiet[:MAX_NODE],
        "note": ("Đã chạm trần số node — cây còn nhánh chưa quét."
                 if kq["cham_tran"] else ""),
    }}
    c, _ = _goi_web(f"/api/agents/{AID}/profile", {"wiki_source": moi})
    print(f"    {'đạt ' if c == 200 else 'TRƯỢT'} báo kết quả lên console (HTTP {c})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
