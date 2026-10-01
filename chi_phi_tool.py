"""Sổ chi phí quét: ghi tiền Apify THẬT của mỗi lần quét vào Base audit, tra lại khi được hỏi.

Vì sao tách riêng: chủ agent muốn Mark KHÔNG tự nói chi phí trong câu trả lời, chỉ
ghi lại, ai hỏi thì mới trả lời. Nhưng kết quả tool không được giữ trong lịch sử
chat, nên sang lượt sau Mark không còn con số (25/09/2026 hỏi lại thì Mark chịu).
Vậy phải có một chỗ giữ số, và một tool để tra:

  • `ghi()` — `apify_tool` gọi sau mỗi lần quét. Ghi JSONL cục bộ (nguồn để tra)
    và đẩy một dòng lên bảng "Chi phí quét" trong CHÍNH Base audit (nối với dòng
    audit qua Turn ID). Bảng được tạo một lần ở lần ghi đầu.
  • `tra_chi_phi_quet` — tool chỉ đọc, trả các lần quét gần nhất của chat hiện tại.

Không đụng `audit.py`: chỉ ĐỌC lượt đang chạy của nó để biết turn/chat/người hỏi.
Mọi lỗi đều nuốt (fail-open) — sổ chi phí hỏng không được làm hỏng lần quét.
"""
from __future__ import annotations

import datetime
import json
import threading
import time

import audit
import lark_client as lark
from config import config

from tools.registry import registry, tool_error, tool_result  # type: ignore

# Thư mục CON, không đặt thẳng trong .audit/: hồi quy và kiểm toán lấy "file *.jsonl
# cuối cùng theo tên" trong .audit/ làm sổ audit. Đặt ngang hàng là chúng đọc nhầm
# sổ này rồi chờ hết giờ ở mọi câu (đã gặp thật 25/09/2026).
_SO = audit._THU_MUC / "chi-phi" / "so.jsonl"
_CAU_HINH = config.token_file.parent / "chi_phi_quet_base.json"   # .tokens/ (gitignore)
_VN = datetime.timezone(datetime.timedelta(hours=7))
_TEN_BANG = "Chi phí quét"
# 1=text, 2=number, 5=datetime (API bitable)
_COT = [
    ("Thời điểm", 5), ("Người hỏi", 1), ("Chat", 1), ("Từ khoá", 1),
    ("Nền tảng", 1), ("Khoảng ngày", 1), ("Chi phí thực USD", 2),
    ("Ước tính USD", 2), ("Số lượt chạy", 2), ("Chạm trần", 1),
    ("Nguồn số", 1), ("Turn ID", 1),
]
_khoa = threading.Lock()


def _luot_hien_tai() -> dict:
    """Turn/chat/người hỏi của lượt đang chạy trên thread này (đọc từ audit)."""
    try:
        tid = getattr(audit._cuc_bo, "turn_id", "")
        with audit._khoa_luot:
            luot = dict(audit._dang_chay.get(tid) or {})
        return {"turn_id": tid, "chat": luot.get("chat") or "", "nguoi": luot.get("nguoi") or ""}
    except Exception:  # noqa: BLE001
        return {"turn_id": "", "chat": "", "nguoi": ""}


def ghi(*, queries, platforms, date_range, thuc: dict | None, est: float,
        chat: str | None = None, ma_viec: str | None = None,
        nguoi: str | None = None) -> dict:
    """Ghi một lần quét vào sổ cục bộ rồi đẩy lên Base ở thread nền. Trả bản ghi.

    `ma_viec`: việc quét NỀN (viec_nen) — chạy ngoài lượt trả lời nên không có turn audit;
    `chat`/`nguoi` lấy từ sổ việc thay cho lượt đang chạy."""
    luot = _luot_hien_tai()
    rec = {
        "ts": time.time(),
        "thoi_diem": datetime.datetime.now(_VN).isoformat(timespec="seconds"),
        "turn_id": luot["turn_id"], "chat": chat or luot["chat"],
        "nguoi": nguoi or luot["nguoi"],
        "tu_khoa": list(queries or []), "nen_tang": list(platforms or []),
        "khoang_ngay": date_range or "",
        "chi_phi_thuc_usd": thuc["usd"] if thuc and thuc.get("so_run") else None,
        "uoc_tinh_usd": round(float(est or 0), 3),
        "so_luot_chay": (thuc or {}).get("so_run") or 0,
        "cham_tran": bool((thuc or {}).get("cham_tran")),
    }
    if ma_viec:
        rec["ma_viec"] = ma_viec
    try:
        _SO.parent.mkdir(parents=True, exist_ok=True)
        with _khoa, open(_SO, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[chi_phi] ghi so loi (bo qua): {type(e).__name__}: {e}")
    if getattr(audit, "_DAY_LEN_BASE", False):
        threading.Thread(target=_day, args=(rec,), daemon=True).start()
    return rec


# ───────────────────────────── Base ─────────────────────────────
def _bang() -> dict:
    """Bảng "Chi phí quét" trong Base audit — tạo một lần, nhớ table_id."""
    try:
        return json.loads(_CAU_HINH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    app = (audit._doc_cau_hinh() or {}).get("app_token")
    if not app:
        return {}   # Base audit chưa có — audit tự tạo ở lượt đầu, lần sau sẽ có
    t = lark.call("POST", f"/open-apis/bitable/v1/apps/{app}/tables",
                  body={"table": {"name": _TEN_BANG,
                                  "fields": [{"field_name": n, "type": ty} for n, ty in _COT]}})
    tid = (t.get("data") or {}).get("table_id")
    if not tid:
        raise RuntimeError(f"khong tao duoc bang chi phi: {str(t)[:200]}")
    cfg = {"app_token": app, "table_id": tid}
    _CAU_HINH.parent.mkdir(parents=True, exist_ok=True)
    _CAU_HINH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def _fields(rec: dict) -> dict:
    thuc = rec.get("chi_phi_thuc_usd")
    return {
        "Thời điểm": int(rec["ts"] * 1000),
        "Người hỏi": audit._ten_nguoi(rec.get("nguoi") or ""),
        "Chat": rec.get("chat") or "",
        "Từ khoá": ", ".join(rec.get("tu_khoa") or []),
        "Nền tảng": ", ".join(rec.get("nen_tang") or []),
        "Khoảng ngày": rec.get("khoang_ngay") or "",
        "Chi phí thực USD": thuc if thuc is not None else 0,
        "Ước tính USD": rec.get("uoc_tinh_usd") or 0,
        "Số lượt chạy": rec.get("so_luot_chay") or 0,
        "Chạm trần": "có" if rec.get("cham_tran") else "",
        "Nguồn số": "Apify (thực)" if thuc is not None else "ước tính — chưa lấy được số thực",
        "Turn ID": rec.get("turn_id") or (f"viec-nen:{rec['ma_viec']}"
                                          if rec.get("ma_viec") else ""),
    }


def _day(rec: dict) -> None:
    try:
        with _khoa:
            cfg = _bang()
        if not cfg.get("table_id"):
            return
        lark.call("POST", f"/open-apis/bitable/v1/apps/{cfg['app_token']}"
                          f"/tables/{cfg['table_id']}/records", body={"fields": _fields(rec)})
    except Exception as e:  # noqa: BLE001
        print(f"[chi_phi] day len Base loi (bo qua): {type(e).__name__}: {e}")


# ───────────────────────────── tool tra cứu ─────────────────────────────
def doc_so(chat: str, n: int = 5) -> list[dict]:
    """n lần quét gần nhất của `chat`, mới nhất trước."""
    try:
        dong = _SO.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return []
    ra = []
    for l in reversed(dong):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("chat") == chat:
            ra.append(r)
            if len(ra) >= n:
                break
    return ra


SCHEMA = {
    "name": "tra_chi_phi_quet",
    "description": (
        "Tra chi phí (USD) các lần quét social gần nhất trong cuộc chat này, lấy từ sổ "
        "audit — là số tiền Apify THỰC tính, không phải ước tính.\n"
        "CHỈ GỌI khi người dùng HỎI về chi phí/tiền của lần quét. Không tự nói chi phí "
        "khi không được hỏi.\n"
        "Trả lời bằng đúng số trong kết quả. `chi_phi_thuc_usd`=null nghĩa là chưa lấy "
        "được số thực: nói rõ chỉ có ước tính. `cham_tran`=true thì nói lượt đó chạm "
        "trần chi phí nên dữ liệu có thể thiếu. Không có lần quét nào thì nói thẳng."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "so_luot": {"type": "integer",
                        "description": "Số lần quét gần nhất cần xem (mặc định 3, tối đa 10)."},
        },
    },
}


def _handle(args: dict, **_kwargs) -> str:
    chat = _luot_hien_tai()["chat"]
    if not chat:
        return tool_error("Không xác định được cuộc chat hiện tại nên không tra được sổ.")
    try:
        n = max(1, min(10, int((args or {}).get("so_luot") or 3)))
    except (TypeError, ValueError):
        n = 3
    luot = [{k: r.get(k) for k in ("thoi_diem", "tu_khoa", "nen_tang", "khoang_ngay",
                                   "chi_phi_thuc_usd", "uoc_tinh_usd", "so_luot_chay",
                                   "cham_tran")}
            for r in doc_so(chat, n)]
    return tool_result(so_lan_quet=len(luot), cac_lan_quet=luot,
                       tong_chi_phi_thuc_usd=round(sum(x["chi_phi_thuc_usd"] or 0
                                                       for x in luot), 3))


try:
    registry.register(
        name="tra_chi_phi_quet", toolset="social", schema=SCHEMA, handler=_handle,
        check_fn=lambda: True, requires_env=[], is_async=False,
        description="Tra chi phí thực của các lần quét gần nhất khi người dùng hỏi",
        emoji="\U0001f4b5", override=True,
    )
except Exception as e:  # noqa: BLE001
    print(f"[chi_phi_tool] register warning: {e}")
