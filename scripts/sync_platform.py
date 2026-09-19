"""Build a Mark dev-version payload and optionally sync approved knowledge.

Dry-run is the default.  Knowledge writes use the agent-scoped API and are
therefore limited to the configured ``LSR_AGENT_ID``.  Creating/publishing a
version still requires a moderator/admin session and is intentionally left to
the Platform UI or its authenticated API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def approved_knowledge() -> list[dict]:
    catalog = json.loads((ROOT / "knowledge" / "catalog.json").read_text(encoding="utf-8"))
    rows = []
    for item in catalog.get("items", []):
        if item.get("status") != "approved_for_dev":
            continue
        path = ROOT / item["path"]
        if not path.is_file():
            raise SystemExit(f"Knowledge đã duyệt nhưng thiếu file: {item['path']}")
        content = path.read_text(encoding="utf-8")
        rows.append({
            **item,
            "title": path.stem.replace("_", " ").replace("-", " "),
            "content": content,
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
        })
    return rows


def custom_skills() -> list[dict]:
    rows = []
    for path in sorted((ROOT / "skills").glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        title = content.splitlines()[0].lstrip("# ").strip() if content else path.stem
        rows.append({"name": title, "instructions": content})
    return rows


def persona_from_file() -> dict:
    """Lấy tiểu sử từ `persona.md` — nguồn sự thật DUY NHẤT về tính cách agent.

    Trước đây bốn trường này viết cứng ở đây. Hệ quả: ai sửa `persona.md` thì
    runtime đổi còn hồ sơ trên platform vẫn nói câu cũ, và không ai biết hai bên
    đã lệch. Đọc thẳng từ file thì sửa một chỗ là cả hai theo.

    Rơi về giá trị mặc định nếu không đọc được — thà có tiểu sử cũ còn hơn để
    trống, vì trống thì console không hiện gì cả.
    """
    mac_dinh = {
        "name": "Mark Trần",
        "vibe": "professional",
        "bio": "Social listening agent của Lamson Retail",
        "description": ("Theo dõi tín hiệu công khai về thương hiệu và đối thủ; "
                        "phân tích, dẫn nguồn và đề xuất. Không tự gửi tin hoặc ghi dữ liệu."),
    }
    f = ROOT / "persona.md"
    if not f.is_file():
        return mac_dinh
    try:
        dong = f.read_text(encoding="utf-8").splitlines()
    except OSError:
        return mac_dinh

    def sau_dau(tien_to: str) -> str:
        for ln in dong:
            s = ln.strip()
            if s.startswith(tien_to):
                return s[len(tien_to):].strip().rstrip(".")
        return ""

    # "- Tên: Mark Nguyễn — Social Assistant." → bỏ phần mô tả sau dấu gạch dài,
    # giữ đúng tên riêng để khớp tên bot trên Lark.
    ten = sau_dau("- Tên:")
    ten = ten.split("—")[0].strip() if ten else ""
    ban_chat = sau_dau("- Bản chất:")
    nhiem_vu = sau_dau("- Nhiệm vụ cốt lõi:")

    ra = dict(mac_dinh)
    if nhiem_vu:
        # Câu đầu của nhiệm vụ là tiểu sử ngắn; console hiện một dòng.
        ra["bio"] = nhiem_vu.split(",")[0].strip()[:200]
    if ban_chat:
        ra["description"] = ban_chat[:600]
    # TÊN thì KHÔNG lấy từ persona.md. Tên hiển thị phải khớp bot trên Lark
    # ("Mark Trần"), còn persona.md đang ghi "Mark Nguyễn" — hai nguồn đã lệch.
    # Lấy theo file sẽ đổi tên agent trên console thành tên không ai thấy trong
    # Lark. Ai đó cần chốt một tên rồi sửa cho khớp; tới lúc đó giữ tên Lark.
    if ten and ten != ra["name"]:
        print(f"  [persona] persona.md ghi ten {ten!r} nhung giu {ra['name']!r} "
              f"cho khop bot Lark", flush=True)
    return ra


def version_payload() -> dict:
    knowledge = approved_knowledge()
    return {
        "persona": persona_from_file(),
        "skills": [],
        "custom_skills": custom_skills(),
        "knowledge_files": [
            {"name": row["path"], "content": row["content"]} for row in knowledge
        ],
        "model": os.environ.get("AGENT_MODEL", "gpt-5.6-terra"),
        "tool_grants": {"profile": "planner-read-only", "policy_mode": "enforce"},
        "note": "Mark dev candidate: skills + approved knowledge + fail-closed planner policy",
    }


def api_post(base: str, token: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def sync_knowledge(apply: bool, allow_production: bool) -> dict:
    load_dotenv()
    agent_id = (os.environ.get("LSR_AGENT_ID") or "").strip()
    token = (os.environ.get("LSR_TELEMETRY_API_KEY") or "").strip()
    collector = (os.environ.get("LSR_COLLECTOR") or "").strip().rstrip("/")
    platform = (os.environ.get("LSR_PLATFORM_URL") or collector.replace("collector.", "platform."))
    rows = approved_knowledge()
    if not apply:
        return {"mode": "dry-run", "agent_id": agent_id or None, "knowledge_items": len(rows)}
    if not agent_id.endswith("-TEST") and not allow_production:
        raise SystemExit("Từ chối sync vào ID production; dùng TEST hoặc --allow-production rõ ràng.")
    if not (agent_id and token and platform):
        raise SystemExit("Thiếu LSR_AGENT_ID/LSR_TELEMETRY_API_KEY/LSR_PLATFORM_URL.")
    synced = []
    for row in rows:
        item_id = "mark_" + row["sha256"][:16]
        result = api_post(platform, token, "/v1/self/brain/items", {
            "item_id": item_id,
            "kind": "knowledge",
            "title": row["title"],
            "content": row["content"],
            "domain": row.get("domain"),
            "tags": ["mark", "approved_for_dev"],
            "source_ref": row["path"],
            "source_url": f"repo:hapas_agent_social/{row['path']}",
            "status": "approved",
        })
        synced.append(result.get("item_id"))
    return {"mode": "apply", "agent_id": agent_id, "synced": synced}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", action="store_true", help="in payload tạo dev version")
    parser.add_argument("--apply-knowledge", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()
    if args.payload:
        print(json.dumps(version_payload(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(
            sync_knowledge(args.apply_knowledge, args.allow_production),
            ensure_ascii=False,
            indent=2,
        ))


if __name__ == "__main__":
    main()
