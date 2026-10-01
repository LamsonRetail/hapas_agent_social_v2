"""Run only Mark's Platform job worker (no Lark event listener).

This entrypoint is deliberately TEST-only.  It lets the Platform web console
exercise the real local ``brain.reply`` path without starting the production
Lark listener on the same machine.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _require_test_config() -> None:
    agent_id = (os.environ.get("LSR_AGENT_ID") or "").strip()
    if not agent_id.endswith("-TEST"):
        raise SystemExit(
            "Từ chối chạy: scripts/run_platform_worker.py chỉ nhận agent ID kết thúc bằng -TEST"
        )
    if os.environ.get("LSR_JOB_POLL_ENABLED", "0").strip() != "1":
        raise SystemExit("Từ chối chạy: cần LSR_JOB_POLL_ENABLED=1")


def main() -> int:
    _require_test_config()

    # Import sau safety gate để không khởi tạo bộ não/tooling nếu cấu hình nhầm
    # sang agent production.
    import brain
    import lsr_platform

    stop = threading.Event()

    def request_stop(*_args) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, request_stop)
        except (AttributeError, ValueError):
            pass

    print(lsr_platform.bat(), flush=True)
    try:
        import viec_nen

        print(viec_nen.khoi_dong(), flush=True)
    except Exception as e:  # noqa: BLE001 — việc nền hỏng không chặn worker
        print(f"Việc nền: lỗi khởi động ({type(e).__name__})", flush=True)
    if not lsr_platform.chay_vong_job(brain.reply, stop):
        print("Platform worker không khởi động được; kiểm tra LSR_*.", flush=True)
        return 2

    print("Platform TEST worker đã sẵn sàng; không khởi động listener Lark.", flush=True)
    while not stop.wait(1):
        time.sleep(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
