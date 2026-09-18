"""Đồng bộ tiểu sử Mark từ `persona.md` lên console platform.

    python scripts/dong_bo_tieu_su.py            # tạo draft + publish dev, KHÔNG chạm prod
    python scripts/dong_bo_tieu_su.py --prod     # publish tiếp lên prod (bot thật đọc)

Vì sao cần: trang agent trên console lấy Tiểu sử / Tính cách / Mô tả từ `persona`
của version đang sống, còn hành vi bot thì lấy từ `persona.md` trên máy này. Hai
nơi, một sự thật — nên file này coi `persona.md` là gốc và đẩy lên, thay vì gõ tay
hai lần rồi lệch.

CẨN TRỌNG — vì sao mặc định chỉ dev:
`instruction_block` mà platform biên dịch từ persona + kỹ năng được GHÉP THẲNG vào
prompt sống của bot (`brain._platform_context_block`). Nhưng runtime chỉ đọc env
`prod` với ID không kết thúc bằng `-TEST` (`lsr_platform._context_env`). Nên
publish dev là xem trước an toàn: console đã hiện đúng, bot chưa đổi gì.

Chạy lại bất cứ lúc nào ai sửa `persona.md`.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

# PowerShell 5.1 chạy console ở cp1252, mà script này in tiếng Việt — không ép UTF-8
# thì `print` ném UnicodeEncodeError. Nguy ở chỗ nó ném GIỮA CHỪNG: version đã tạo
# xong rồi mới chết ở dòng in, để lại một draft treo không ai publish.
for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

AID = "AG-SOCIAL-LISTENING"
WEB = "https://app.34-124-212-76.sslip.io"
GOC = pathlib.Path(__file__).resolve().parent.parent
PERSONA = GOC / "persona.md"

#: Kỹ năng riêng của Mark. Lấy từ `GET /api/agents/<id>/skills` → `custom`.
#: Sau khi xoá-dựng-lại, bản thân kỹ năng còn (brain_items sống sót) nhưng danh
#: sách ĐANG BẬT thì mất theo `agent_versions` — nên phải bật lại tường minh.
KY_NANG = [
    "sk_7c28d5f2bb",   # Báo cáo dựa trên evidence
    "sk_9d02c5de94",   # Deep-dive bình luận
    "sk_41fc43d6b7",   # Lập kế hoạch truy vấn social
    "sk_a99f515e13",   # Nghiên cứu web và sản phẩm công khai
    "sk_2d37e7d0e7",   # Phân tích crisis, sentiment và share of voice
    "sk_8776392ea3",   # Phân tích quảng cáo đối thủ
]


def _phien() -> str:
    f = pathlib.Path.home() / ".lsr" / "token"
    if not f.is_file():
        sys.exit("không thấy ~/.lsr/token — đăng nhập console rồi lưu token vào đó")
    return f.read_text(encoding="utf-8").strip()


def _goi(path: str, payload: dict) -> tuple[int, dict]:
    """Đi qua proxy admin của console.

    Proxy này LUÔN POST, bỏ qua mọi ý định đọc — nên tuyệt đối không dùng nó để
    'xem thử' một endpoint mà POST có tác dụng phụ.
    """
    body = json.dumps({"path": path, "payload": payload}, ensure_ascii=False).encode()
    req = urllib.request.Request(
        WEB + "/api/admin", data=body, method="POST",
        headers={"Cookie": f"lsr_session={_phien()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"loi": e.read().decode()[:300]}


def _goi_doc(path: str) -> tuple[int, dict]:
    """GET thẳng platform. KHÔNG đi qua proxy admin — proxy đó luôn POST.

    Chỉ dùng được với đường Caddy cho qua từ ngoài (`spec`, `profile`, `manifest`,
    `agent-card`…); `persona` và `skills` không nằm trong danh sách đó.
    """
    tok = (pathlib.Path.home() / ".lsr" / "token").read_text(encoding="utf-8").strip()
    req = urllib.request.Request(
        "https://platform.34-124-212-76.sslip.io" + path,
        headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"loi": e.read().decode()[:200]}


# ─────────────────────────────── bóc từ persona.md ───────────────────────────
def _gach_dau_dong(khoi: str, nhan: str) -> str:
    """Lấy nội dung của đúng một bullet `- <nhãn>: ...`, gồm cả dòng thụt vào sau nó."""
    m = re.search(rf"(?m)^- {re.escape(nhan)}:\s*(.+(?:\n(?:  |\t).+)*)", khoi)
    if not m:
        return ""
    return re.sub(r"\s*\n\s*", " ", m.group(1)).strip()


def _muc(s: str, so: int) -> str:
    m = re.search(rf"(?ms)^## {so}\. .*?$(.*?)(?=^## \d+\.|\Z)", s)
    return m.group(1) if m else ""


def doc_persona() -> dict:
    if not PERSONA.is_file():
        sys.exit(f"không thấy {PERSONA}")
    s = PERSONA.read_text(encoding="utf-8")
    danh_tinh, tinh_cach = _muc(s, 1), _muc(s, 2)

    ten = _gach_dau_dong(danh_tinh, "Tên")
    thang_do = _gach_dau_dong(tinh_cach, "Thang đo (0–10)")
    nha = _gach_dau_dong(danh_tinh, "Nhà")
    nhiem_vu = _gach_dau_dong(danh_tinh, "Nhiệm vụ cốt lõi")
    cot_loi = _gach_dau_dong(tinh_cach, "Cốt lõi")

    if not (ten and nha and nhiem_vu and cot_loi):
        sys.exit("persona.md đổi cấu trúc — không bóc được Tên / Nhà / Nhiệm vụ cốt lõi / "
                 "Cốt lõi.\nSửa hàm doc_persona() cho khớp file mới, đừng để nó im lặng "
                 "đẩy lên nửa vời.")

    # "Tên: Mark Nguyễn — Social Assistant." → vai trò là vế sau dấu gạch dài.
    vai = (ten.split("—")[-1] if "—" in ten else ten).strip().rstrip(".")
    # "Nhà: công ty X, do team Y phát triển. Khi ai hỏi… " → chỉ giữ câu đầu.
    nha_ngan = nha.split(". Khi ai hỏi")[0].rstrip(".")
    # "Nhiệm vụ cốt lõi: hỗ trợ mảng A, gồm 4 nhóm việc: 1) … 2) …" → phần trước ": 1)".
    viec = re.split(r",?\s*gồm \d+ nhóm việc", nhiem_vu)[0].rstrip(":. ")
    bon_viec = re.findall(r"\d\)\s*([^—]+)—", nhiem_vu)

    return {
        # Tên KHÔNG lấy từ persona.md. File đó ghi "Mark Nguyễn", còn `agents.name` và
        # tên bot bên Lark là "Mark Trần" — mà tên bot Lark chỉ đổi được bằng cách tạo
        # version app mới (người dùng quét lại, admin tenant duyệt lại). Nên platform
        # mới là gốc của TÊN, persona.md là gốc của TÍNH CÁCH. Lấy nhầm chiều thì
        # console hiện một đằng, Lark hiện một nẻo.
        "name": ten_tren_platform(),
        "bio": f"{vai} của {nha_ngan}. {viec[0].upper()}{viec[1:]}.",
        # `vibe` là ENUM bốn giá trị, không phải chữ tự do: platform tra nó trong
        # `_VIBE_VOICE` để sinh câu giọng điệu, tra trượt thì rơi về "Thân thiện"
        # ("ấm áp, gần gũi") — trái hẳn persona.md. Đã đúng một lần như thế ở v1.
        "vibe": _chon_vibe(cot_loi + " " + thang_do),
        "description": ("Bốn nhóm việc: "
                        + "; ".join(x.strip().lower() for x in bon_viec) + "."
                        ) if bon_viec else viec,
    }


#: Bốn giá trị platform hiểu (`_VIBE_VOICE` trong platform_api). Thứ tự = thứ tự xét.
_VIBE = {
    "Hóm hỉnh": ("tinh nghịch", "hài hước", "dí dỏm", "chơi chữ", "đùa"),
    "Châm chọc": ("cà khịa", "châm chọc", "mỉa"),
    "Thẳng thắn": ("thẳng thắn", "trực tiếp", "đi thẳng"),
    "Thân thiện": ("thân thiện", "ấm áp", "gần gũi"),
}


def _chon_vibe(mo_ta: str) -> str:
    low = mo_ta.lower()
    for ten, tu in _VIBE.items():
        if any(t in low for t in tu):
            return ten
    return "Thân thiện"


def ten_tren_platform() -> str:
    """Tên hiển thị lấy từ chính platform, không gõ tay vào đây."""
    c, r = _goi_doc(f"/v1/agents/{AID}/spec")
    ten = (r.get("name") or "").strip() if isinstance(r, dict) else ""
    if not ten:
        sys.exit(f"không đọc được tên agent từ /spec (HTTP {c}) — dừng, không đoán tên.")
    return ten


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", action="store_true",
                    help="publish tiếp lên prod — bot Lark thật sẽ đọc")
    args = ap.parse_args()

    p = doc_persona()
    print("\n  BÓC TỪ persona.md")
    print("  " + "─" * 74)
    for k in ("bio", "vibe", "description"):
        print(f"    {k:<12} {p[k]}")

    print(f"\n  TẠO VERSION ({len(KY_NANG)} kỹ năng)")
    print("  " + "─" * 74)
    c, r = _goi(f"/v1/agents/{AID}/versions", {
        "persona": p, "skills": KY_NANG,
        "note": "đồng bộ tiểu sử từ persona.md + bật lại kỹ năng sau khi dựng lại"})
    if c != 200 or not r.get("version"):
        print(f"    HTTP {c} · {json.dumps(r, ensure_ascii=False)[:250]}")
        return 1
    v = r["version"]
    print(f"    đạt  version v{v} · {r.get('publication')}")

    cho_duyet = None
    for env in (["dev", "prod"] if args.prod else ["dev"]):
        c, r = _goi(f"/v1/agents/{AID}/versions/{v}/publish", {"env": env})
        # HTTP 200 KHÔNG có nghĩa là đã publish. Publish prod bằng vai moderator chỉ
        # TẠO YÊU CẦU chờ admin duyệt, mà vẫn trả 200 kèm
        # `publication: "pending_approval"`. Kiểm mỗi mã HTTP là script báo "đạt"
        # trong khi prod không đổi gì — đã sai đúng một lần như thế.
        pub = (r or {}).get("publication")
        ok = c == 200 and pub == env
        if c == 200 and pub == "pending_approval":
            cho_duyet = r.get("action_id")
            print(f"    CHỜ  publish {env:<5} đã gửi admin duyệt — prod CHƯA đổi "
                  f"(việc #{cho_duyet})")
            continue
        print(f"    {'đạt ' if ok else 'TRƯỢT'} publish {env:<5} HTTP {c} · pub={pub}"
              + ("" if ok else f" · {json.dumps(r, ensure_ascii=False)[:160]}"))
        if not ok:
            return 1

    if cho_duyet:
        print(f"\n  CHƯA XONG. Việc #{cho_duyet} đang chờ admin duyệt ở")
        print("  https://app.34-124-212-76.sslip.io/admin/approvals")
        print("  Người duyệt phải KHÁC người đề xuất. Duyệt xong prod mới đổi.\n")
        return 2
    if not args.prod:
        print("\n  Mới lên dev — bot Lark CHƯA đổi gì (runtime chỉ đọc prod).")
        print("  Xem trên console, ưng thì chạy lại với --prod.\n")
    else:
        print("\n  Đã lên prod — bot Lark sẽ đọc instruction này ở lượt trả lời tới.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
