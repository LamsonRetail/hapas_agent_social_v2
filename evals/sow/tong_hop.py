"""Tổng hợp kết quả Promptfoo theo hạng mục SOW, kèm độ ổn định pass@k / pass^k.

    python evals/sow/tong_hop.py evals/sow/ket-qua/ket-qua-<thời điểm>.json

Chạy với `chay.ps1 -Lap k` thì mỗi ca có k lần trả lời. Theo eval-harness của ECC:
- pass@k: ca đạt ÍT NHẤT một lần trong k lần (Mark CÓ THỂ làm đúng);
- pass^k: ca đạt CẢ k lần (Mark làm đúng ỔN ĐỊNH) — chỉ số dùng để nghiệm thu, vì người
  dùng thật chỉ hỏi một lần.
Một ca đạt @k mà không đạt ^k là ca chập chờn: xem lý do trượt ở các lần hỏng.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def tong_hop(duong_dan: str) -> dict:
    d = json.loads(pathlib.Path(duong_dan).read_text(encoding="utf-8"))
    theo_ca: dict[str, list[dict]] = collections.defaultdict(list)
    thong_tin: dict[str, dict] = {}
    for r in d["results"]["results"]:
        ma = (r.get("vars") or {}).get("ma") or f"#{r.get('testIdx')}"
        theo_ca[ma].append(r)
        tc = r.get("testCase") or {}
        thong_tin[ma] = {"sow": (tc.get("metadata") or {}).get("sow_dong"),
                         "hang_muc": (tc.get("metadata") or {}).get("hang_muc", ""),
                         "mo_ta": tc.get("description", "")}
    hang_muc: dict = collections.defaultdict(lambda: {"ca": 0, "dat_mu": 0, "dat_at": 0, "lan": 0,
                                                      "lan_dat": 0, "ten": ""})
    chi_tiet = []
    for ma, ds in theo_ca.items():
        dat = [bool(r.get("success")) for r in ds]
        tt = thong_tin[ma]
        h = hang_muc[tt["sow"]]
        h["ten"] = h["ten"] or tt["hang_muc"]
        h["ca"] += 1
        h["lan"] += len(dat)
        h["lan_dat"] += sum(dat)
        h["dat_at"] += any(dat)
        h["dat_mu"] += all(dat)
        ly_do = sorted({c.get("reason", "") for r in ds if not r.get("success")
                        for c in (r.get("gradingResult") or {}).get("componentResults") or []
                        if not c.get("pass")} | {r.get("error") or "" for r in ds if r.get("error")})
        chi_tiet.append({"ma": ma, "sow": tt["sow"], "mo_ta": tt["mo_ta"], "dat": f"{sum(dat)}/{len(dat)}",
                         "on_dinh": all(dat), "ly_do_truot": [x for x in ly_do if x][:5]})
    return {"hang_muc": dict(hang_muc), "chi_tiet": chi_tiet}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    kq = tong_hop(sys.argv[1])
    print("SOW | hạng mục | số ca | pass^k (ổn định) | pass@k | tỉ lệ lần đạt")
    for sow in sorted(kq["hang_muc"], key=lambda x: (x is None, x)):
        h = kq["hang_muc"][sow]
        print(f"{sow} | {h['ten']} | {h['ca']} | {h['dat_mu']}/{h['ca']} | {h['dat_at']}/{h['ca']} | "
              f"{h['lan_dat']}/{h['lan']}")
    truot = [c for c in kq["chi_tiet"] if not c["on_dinh"]]
    if truot:
        print("\nCa chưa ổn định:")
        for c in sorted(truot, key=lambda x: (x["sow"] is None, x["sow"], x["ma"])):
            print(f"- {c['ma']} ({c['dat']}) {c['mo_ta']}")
            for l in c["ly_do_truot"]:
                print(f"    · {l[:300]}")


if __name__ == "__main__":
    main()
