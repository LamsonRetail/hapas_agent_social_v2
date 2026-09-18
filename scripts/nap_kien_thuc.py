"""Đồng bộ kiến thức của Mark từ file trên máy lên platform.

    python scripts/nap_kien_thuc.py            # xem sẽ làm gì, KHÔNG đẩy
    python scripts/nap_kien_thuc.py --day      # đẩy thật những file đã đổi

Vì sao cần: kiến thức của Mark hiện là sáu file `.md` nạp tay qua console. Ai sửa file
thì platform không biết — kho tri thức đứng yên ở ảnh chụp lúc nạp. Wiki đáng lẽ đóng
chỗ này nhưng đang vướng ADR `WIKI` (chưa sign-off) và bot chưa được thêm vào space
nào, nên trong lúc chờ phải có một đường thủ công chạy được.

Nguồn sự thật là `knowledge/catalog.json`. CHỈ nạp mục `approved_for_dev`.

Vì sao chặn cứng `excluded`: bốn mục trong danh mục là chat transcript, và đặc tả vai
ghi rõ *"Không ingest chat transcript, export hội thoại, HR/payroll, credential hoặc
raw social PII"*. Nạp nhầm một cái là đưa nội dung hội thoại nội bộ vào chỗ RAG trích
ra cho mọi câu hỏi — không có nút hoàn tác cho việc đã trả lời.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

for _l in (sys.stdout, sys.stderr):
    try:
        _l.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GOC = pathlib.Path(__file__).resolve().parent.parent
AID = "AG-SOCIAL-LISTENING"
PLATFORM = "https://platform.34-124-212-76.sslip.io"
WEB = "https://app.34-124-212-76.sslip.io"
DANH_MUC = GOC / "knowledge" / "catalog.json"
TRANG_THAI = GOC / "knowledge" / ".da-nap.json"


def _token() -> str:
    f = pathlib.Path.home() / ".lsr" / "token"
    if not f.is_file():
        sys.exit("không thấy ~/.lsr/token")
    return f.read_text(encoding="utf-8").strip()


def _goi(url: str, body=None, cookie: bool = False):
    tok = _token()
    h = {"Cookie": f"lsr_session={tok}"} if cookie else {"Authorization": f"Bearer {tok}"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data,
                                 method="POST" if data is not None else "GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"loi": e.read().decode("utf-8", "replace")[:200]}


def _tim(ten: str) -> pathlib.Path | None:
    """Đường dẫn trong `catalog.json` ghi tương đối, nhưng file thật nằm ở GỐC repo.

    Dò cả hai chỗ thay vì sửa danh mục: danh mục là thứ người khác cũng sửa, còn dò thì
    đúng ở cả hai cách bày file. Không tìm thấy thì NÓI RA, đừng lặng lẽ bỏ qua.
    """
    for p in (GOC / "knowledge" / ten, GOC / ten):
        if p.is_file():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", action="store_true", help="đẩy thật (mặc định chỉ xem)")
    args = ap.parse_args()

    if not DANH_MUC.is_file():
        sys.exit(f"không thấy {DANH_MUC}")
    dm = json.loads(DANH_MUC.read_text(encoding="utf-8"))
    muc = dm.get("items") or []
    duyet = [m for m in muc if m.get("status") == "approved_for_dev"]
    loai = [m for m in muc if m.get("status") == "excluded"]

    print(f"\n  DANH MỤC: {len(muc)} mục · {len(duyet)} đã duyệt · {len(loai)} loại trừ")
    print("  " + "─" * 74)
    for m in loai:
        print(f"    bỏ qua  {m['path'][:58]:<58} ({m.get('source_type') or m['status']})")

    can_day, thieu, khong_doi = [], [], []
    da = json.loads(TRANG_THAI.read_text(encoding="utf-8")) if TRANG_THAI.is_file() else {}
    for m in duyet:
        p = _tim(m["path"])
        if p is None:
            thieu.append(m["path"]); continue
        noi_dung = p.read_text(encoding="utf-8")
        bam = hashlib.sha256(noi_dung.encode("utf-8")).hexdigest()[:16]
        (khong_doi if da.get(m["path"]) == bam else can_day).append(
            {"name": m["path"], "content": noi_dung, "bam": bam, "tep": p})

    for m in khong_doi:
        print(f"    y nguyên {m['name'][:57]:<57} {len(m['content']):>7} ký tự")
    for m in can_day:
        cu = "đã đổi" if da.get(m["name"]) else "chưa nạp"
        print(f"    SẼ ĐẨY  {m['name'][:50]:<50} {len(m['content']):>7} ký tự  ({cu})")
    for t in thieu:
        print(f"    THIẾU   {t[:58]:<58} không tìm thấy file")

    # Đối chiếu với thứ platform ĐANG giữ — phát hiện tài liệu mồ côi.
    c, kn = _goi(f"{WEB}/api/agents/{AID}/knowledge", cookie=True)
    if c == 200:
        tren = {d["name"] for d in (kn.get("documents") or [])}
        duoi = {m["path"] for m in duyet}
        mo_coi = sorted(tren - duoi)
        print(f"\n  PLATFORM đang giữ {len(tren)} tài liệu · {kn.get('total_chunks')} mẩu")
        for x in mo_coi:
            print(f"    MỒ CÔI  {x[:58]:<58} có trên platform, không có trong danh mục")
        if mo_coi:
            print("    (KHÔNG tự xoá — xoá kiến thức là việc một chiều, để người quyết)")

    if not can_day:
        print("\n  Không có gì để đẩy.\n")
        return 0
    if not args.day:
        print(f"\n  {len(can_day)} tệp sẽ được đẩy. Chạy lại với --day để làm thật.\n")
        return 0

    print(f"\n  ĐẨY {len(can_day)} tệp")
    print("  " + "─" * 74)
    # Đi qua route console, KHÔNG gọi thẳng platform: Caddy chỉ cho `spec|profile|
    # manifest|changes|agent-card|golive-checklist|lark-identities` qua từ ngoài —
    # `knowledge` không nằm trong đó và trả 403. Route console chạy bên trong nên tới
    # được, và vẫn đi đúng kiểm quyền moderator của platform_api.
    c, r = _goi(f"{WEB}/api/agents/{AID}/knowledge", cookie=True,
                body={"files": [{"name": m["name"], "content": m["content"]}
                                for m in can_day]})
    if c != 200:
        print(f"    TRƯỢT HTTP {c} · {json.dumps(r, ensure_ascii=False)[:200]}")
        return 1
    print(f"    đạt  HTTP 200 · {json.dumps(r, ensure_ascii=False)[:160]}")
    da.update({m["name"]: m["bam"] for m in can_day})
    TRANG_THAI.write_text(json.dumps(da, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    c, kn = _goi(f"{WEB}/api/agents/{AID}/knowledge", cookie=True)
    if c == 200:
        print(f"    đạt  platform giờ có {len(kn.get('documents') or [])} tài liệu · "
              f"{kn.get('total_chunks')} mẩu")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
