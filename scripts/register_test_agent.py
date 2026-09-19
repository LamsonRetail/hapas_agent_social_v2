"""Register the isolated Mark TEST identity on LSR Agent Platform.

The command is a dry-run unless ``--apply`` is passed. ``--self-service`` uses
the owner's Platform PAT and the public enroll endpoint; direct admin register
is retained for execution on the Platform VM. The one-time agent key is written
to the gitignored ``.artifacts`` directory and is never printed.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

import yaml


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ID = "AG-SOCIAL-LISTENING"
TEST_ID = "AG-SOCIAL-LISTENING-TEST"
OWNER = "thamnt@hapas.vn"


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


def build_payload() -> dict:
    source = yaml.safe_load((ROOT / "lsr-agent.yaml").read_text(encoding="utf-8"))
    manifest = copy.deepcopy(source)
    if manifest.get("agent", {}).get("id") != PRODUCTION_ID:
        raise SystemExit(f"Manifest nguồn phải là {PRODUCTION_ID}.")

    agent = manifest["agent"]
    agent["id"] = TEST_ID
    agent["name"] = "Mark Trần TEST"
    agent["description"] = (
        "Bản TEST cô lập của Mark Trần; chỉ dùng để kiểm tra Platform web trên dữ liệu công khai."
    )

    for source_item in manifest.get("data_sources", []):
        if source_item.get("kind") == "index":
            source_item["scope"] = f"agent:{TEST_ID}:approved"

    # TEST không nhận ingress thật và không có quyền ghi ra hệ thống ngoài.
    manifest["connections"] = [
        {
            "side": "external",
            "channel": "web",
            "in": ["question"],
            "out": ["reply"],
        }
    ]
    manifest["permissions"]["access"] = {
        "users": [{"email": OWNER, "via": ["web"]}],
        "agents": [],
    }
    manifest["permissions"]["data"]["audiences"] = [
        {
            "name": "test-owner-only",
            "viewers": [OWNER],
            "covers": ["all_test_outputs"],
        }
    ]

    skills = manifest.get("memory", {}).get("initial", {}).get("skills", [])
    return {
        "agent_id": TEST_ID,
        "name": "Mark Trần TEST",
        "owner": OWNER,
        "backup_owner": agent.get("backup_owner"),
        "squad": agent.get("squad"),
        "connect_mode": "api",
        "is_squad_agent": False,
        "skills": skills,
        "deployment": "external",
        "host_note": "Isolated TEST identity; no Lark app; Platform web only.",
        "reserved": False,
        "manifest": manifest,
    }


def platform_url() -> str:
    configured = (os.environ.get("LSR_PLATFORM_URL") or "").strip()
    if configured:
        return configured.rstrip("/")
    collector = (os.environ.get("LSR_COLLECTOR") or "").strip().rstrip("/")
    return collector.replace("collector.", "platform.")


def agent_exists(base: str, admin_token: str) -> bool:
    request = urllib.request.Request(
        f"{base}/v1/agents/{TEST_ID}",
        headers={"Authorization": f"Bearer {admin_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def register(base: str, admin_token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base}/v1/agents/register",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
            "X-Actor": OWNER,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def evaluation_path() -> Path:
    return ROOT / ".artifacts" / f"{TEST_ID}-evaluation.json"


def load_evaluation() -> dict:
    path = evaluation_path()
    if not path.is_file():
        raise SystemExit(f"Thiếu báo cáo đánh giá thật: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if int(report.get("tests_pass") or 0) < int(report.get("tests_total") or 0):
        raise SystemExit("Báo cáo đánh giá chưa pass hết; từ chối enroll.")
    return report


def enroll(base: str, owner_token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base}/v1/agents/enroll",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {owner_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def secret_path() -> Path:
    return ROOT / ".artifacts" / f"{TEST_ID}.env"


def save_telemetry_key(key: str) -> Path:
    target = secret_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"LSR_AGENT_ID={TEST_ID}\n")
        handle.write(f"LSR_TELEMETRY_API_KEY={key}\n")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--self-service",
        action="store_true",
        help="dùng PAT của owner và /v1/agents/enroll công khai",
    )
    parser.add_argument(
        "--force-rotate-key",
        action="store_true",
        help="đăng ký lại ID đã tồn tại và xoay telemetry key",
    )
    args = parser.parse_args()
    payload = build_payload()
    if not args.apply:
        print(json.dumps({"mode": "dry-run", "payload": payload}, ensure_ascii=False, indent=2))
        return

    load_dotenv()
    base = platform_url()
    platform_token = (
        os.environ.get("LSR_PLATFORM_TOKEN")
        or
        os.environ.get("LSR_PLATFORM_ADMIN_TOKEN")
        or os.environ.get("PLATFORM_ADMIN_TOKEN")
        or ""
    ).strip()
    if not base or not platform_token:
        raise SystemExit("Thiếu LSR_PLATFORM_URL và LSR_PLATFORM_TOKEN.")
    if secret_path().exists():
        raise SystemExit(f"Từ chối ghi đè secret hiện có: {secret_path()}")
    if args.self_service:
        if args.force_rotate_key:
            raise SystemExit("Self-service không được xoay key của ID đã tồn tại.")
        payload["evaluation"] = load_evaluation()
        result = enroll(base, platform_token, payload)
    else:
        if agent_exists(base, platform_token) and not args.force_rotate_key:
            raise SystemExit(
                f"{TEST_ID} đã tồn tại; không xoay key nếu thiếu --force-rotate-key."
            )
        result = register(base, platform_token, payload)
    key = result.pop("telemetry_key", "") or result.pop("agent_token", "")
    result.pop("agent_token", None)
    if not key:
        raise SystemExit("Platform không trả telemetry key.")
    target = save_telemetry_key(key)
    print(json.dumps({**result, "telemetry_key": "saved", "secret_file": str(target)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
