"""Chạy hồi quy golden set qua agent THẬT rồi nộp kết quả cho platform.

    python scripts/chay_hoi_quy.py                 # chạy, chấm, KHÔNG publish
    python scripts/chay_hoi_quy.py --publish-prod  # đạt thì publish version lên prod

VÌ SAO CẦN
`_eval_gate` của platform đòi một regression PASS gắn ĐÚNG version trước khi cho
publish prod. Nhưng `POST /v1/regression/run` chỉ CHẤM ĐIỂM câu trả lời nộp lên — nó
không tự gọi agent. Phải có một bộ ở giữa: lấy câu hỏi, đưa qua agent thật, gom câu
trả lời, rồi nộp. Đây là bộ đó.

LỌC THEO SKILL LÀ BẮT BUỘC
Golden set dùng chung cho nhiều agent. Hôm nay có 10 case active, trong đó 5 case
`s1_qa` là của agent pháp chế (thẩm quyền duyệt hợp đồng, chính sách crypto…). Chấm
Mark bằng những câu đó là chấm sai người — Mark trả lời đúng bằng cách nói "ngoài
phạm vi", nhưng điểm vẫn 0 vì không chứa chuỗi mong đợi.

Đi qua ĐÚNG ingress thật (`/v1/chat/{id}/messages`) chứ không gọi model trực tiếp —
hồi quy phải đo thứ người dùng thật sự gặp, gồm cả policy, công tắc và prompt.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

for _l in (sys.stdout, sys.stderr):
    try:
        _l.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))
import config  # noqa: E402,F401

AID = "AG-SOCIAL-LISTENING"
SKILL = "mark_social_listening"
PLATFORM = "https://platform.34-124-212-76.sslip.io"
WEB = "https://app.34-124-212-76.sslip.io"
#: Một lượt có thể gọi tool nên chậm. Trần của chính runtime là 480s.
CHO_MOI_CAU = int(os.environ.get("LSR_HQ_CHO_SECONDS", "300"))


def _pat() -> str:
    return (pathlib.Path.home() / ".lsr" / "token").read_text(encoding="utf-8").strip()


def _goi(url: str, tok: str, cookie: bool = False, body=None, timeout: int = 90):
    h = {"Cookie": f"lsr_session={tok}"} if cookie else {"Authorization": f"Bearer {tok}"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data,
                                 method="POST" if data is not None else "GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"loi": e.read().decode("utf-8", "replace")[:240]}


def hoi_agent(text: str) -> str | None:
    """Gửi qua ingress thật, đọc trả lời từ sổ audit của máy này."""
    key = (os.environ.get("LSR_TELEMETRY_API_KEY") or "").strip()
    au = sorted((GOC / ".audit").glob("*.jsonl"))
    if not au:
        return None
    f = au[-1]
    n0 = len(f.read_text(encoding="utf-8").splitlines())
    c, _ = _goi(f"{PLATFORM}/v1/chat/{AID}/messages", key,
                body={"text": text, "session_id": f"hoiquy-{int(time.time()*1000)}"})
    if c != 200:
        return None
    het = time.time() + CHO_MOI_CAU
    while time.time() < het:
        time.sleep(2)
        rows = f.read_text(encoding="utf-8").splitlines()
        if len(rows) > n0:
            return json.loads(rows[-1]).get("tra_loi") or ""
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish-prod", action="store_true",
                    help="đạt thì publish version hiện tại lên prod")
    ap.add_argument("--nguong", type=float, default=0.8)
    args = ap.parse_args()
    pat = _pat()

    c, d = _goi(f"{WEB}/api/golden?target_id={AID}", pat, cookie=True)
    if c != 200:
        print(f"  không đọc được golden case: HTTP {c}")
        return 1
    cs = [x for x in (d.get("cases") or [])
          if x.get("active") and x.get("skill") == SKILL]
    khac = [x for x in (d.get("cases") or [])
            if x.get("active") and x.get("skill") != SKILL]
    print(f"\n  GOLDEN SET: {len(cs)} case của `{SKILL}`"
          f" · bỏ qua {len(khac)} case của skill khác")
    print("  " + "─" * 76)
    if not cs:
        print("  không có case nào để chạy.\n")
        return 1

    # Version đang sống ở dev — chính là thứ sẽ publish lên prod.
    key = (os.environ.get("LSR_TELEMETRY_API_KEY") or "").strip()
    import urllib.parse
    q = urllib.parse.urlencode({"session_id": "hq", "q": "x", "user_ref": "", "env": "dev"})
    c, ctx = _goi(f"{PLATFORM}/v1/self/context?{q}", key)
    ver = (ctx or {}).get("version")
    print(f"  version đang ở dev: v{ver}")
    if ver is None:
        print("  chưa có version nào — không gắn kết quả vào đâu được.\n")
        return 1

    dap = []
    for i, x in enumerate(cs, 1):
        print(f"\n  [{i}/{len(cs)}] {x['case_id']} · mong đợi chứa {x['expected']!r}")
        print(f"      hỏi: {str(x['prompt'])[:88]}")
        tl = hoi_agent(str(x["prompt"]))
        if tl is None:
            print("      → KHÔNG TRẢ LỜI")
            dap.append({"case_id": x["case_id"], "response": ""})
            continue
        khop = str(x["expected"]).lower() in tl.lower()
        print(f"      → {'khớp ' if khop else 'LỆCH '} {tl[:96]}")
        dap.append({"case_id": x["case_id"], "response": tl})

    print("\n  NỘP CHO PLATFORM CHẤM")
    print("  " + "─" * 76)
    c, kq = _goi(f"{WEB}/api/admin", pat, cookie=True, body={
        "path": "/v1/regression/run",
        "payload": {"target_id": AID, "target_type": "agent", "skill": SKILL,
                    "threshold": args.nguong, "answers": dap,
                    "agent_version": ver, "run_by": "chay_hoi_quy.py"},
    })
    if c != 200 or not isinstance(kq, dict) or kq.get("score") is None:
        print(f"    TRƯỢT HTTP {c} · {json.dumps(kq, ensure_ascii=False)[:220]}")
        return 1
    print(f"    run_id {kq.get('run_id')} · điểm {kq.get('score')} "
          f"· {kq.get('n_pass')}/{kq.get('n_total')} · ngưỡng {kq.get('threshold')}")
    for x in kq.get("detail") or []:
        print(f"      {'đạt ' if x.get('ok') else 'TRƯỢT'} {x.get('case_id')}")
    if not kq.get("passed"):
        print("\n  CHƯA ĐẠT NGƯỠNG — không publish. Xem case trượt ở trên.\n")
        return 1
    print("\n  ĐẠT.")

    if not args.publish_prod:
        print("  Chạy lại với --publish-prod để đưa version này lên prod.\n")
        return 0

    print("\n  PUBLISH PROD")
    print("  " + "─" * 76)
    c, r = _goi(f"{WEB}/api/admin", pat, cookie=True, body={
        "path": f"/v1/agents/{AID}/versions/{ver}/publish", "payload": {"env": "prod"}})
    pub = (r or {}).get("publication")
    if c == 200 and pub == "prod":
        print(f"    đạt  v{ver} đã lên prod")
    elif c == 200 and pub == "pending_approval":
        print(f"    CHỜ  đã gửi admin duyệt (việc #{r.get('action_id')}) — prod CHƯA đổi")
        return 2
    else:
        print(f"    TRƯỢT HTTP {c} · {json.dumps(r, ensure_ascii=False)[:220]}")
        return 1
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
