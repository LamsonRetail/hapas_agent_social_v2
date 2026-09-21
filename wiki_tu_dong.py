"""Nhịp chạy nền: theo dõi nguồn Wiki và nhập khi chủ agent bấm.

Hai việc, hai nhịp khác nhau, cố ý:

  QUÉT   mỗi 30 phút — đọc khai báo, đi cây, đếm mục H1, báo kết quả lên console.
         KHÔNG nhập gì. Người dùng nhìn con số rồi tự quyết.
  NHẬP   mỗi 60 giây — xem chủ agent có bấm "Nhập ngay" trên console chưa.

VÌ SAO KHÔNG TỰ NHẬP
Wiki là nơi người ta sửa dở dang. Một người lưu nửa chừng mà agent nhập ngay là câu
trả lời cho người khác đổi theo, không ai duyệt. Lấy nguyên tắc từ `watch_wiki.py` của
agent HR: phát hiện đổi thì BÁO, nút cuối cùng vẫn là người.

VÌ SAO NHỊP NHẬP NGẮN HƠN NHỊP QUÉT
Bấm "Nhập ngay" là một hành động có chủ đích, người ta đứng đó chờ. Bắt chờ tới 30 phút
thì họ sẽ tưởng nút hỏng rồi bấm lại. Còn quét định kỳ thì không ai ngồi xem, nên thưa
được — và mỗi lượt quét là hàng chục lời gọi API lên Lark.

Mọi lỗi đều nuốt: nhịp nền hỏng KHÔNG được làm bot chết hay chậm câu trả lời.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

GOC = pathlib.Path(__file__).resolve().parent
AID = os.environ.get("LSR_AGENT_ID", "AG-SOCIAL-LISTENING")

NHIP_QUET = float(os.environ.get("LSR_WIKI_NHIP_QUET_SECONDS", str(30 * 60)))
NHIP_NHAP = float(os.environ.get("LSR_WIKI_NHIP_NHAP_SECONDS", "60"))

_PLATFORM = "https://platform.34-124-212-76.sslip.io"
_WEB = "https://app.34-124-212-76.sslip.io"


def _bay_gio() -> str:
    return datetime.now(timezone.utc).isoformat()


def _khoa_agent() -> str:
    return (os.environ.get("LSR_TELEMETRY_API_KEY") or "").strip()


def _khoa_nguoi() -> str:
    f = pathlib.Path.home() / ".lsr" / "token"
    return f.read_text(encoding="utf-8").strip() if f.is_file() else ""


def _goi(url: str, *, cookie: str = "", bearer: str = "", body=None, timeout: int = 120):
    h = {"Cookie": f"lsr_session={cookie}"} if cookie else {"Authorization": f"Bearer {bearer}"}
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
        return e.code, {"loi": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:
        return 0, {"loi": f"{type(e).__name__}: {e}"}


def khai_bao() -> dict:
    """Khai báo Wiki của CHÍNH agent này, đọc qua danh bạ."""
    c, d = _goi(f"{_PLATFORM}/v1/self/directory", bearer=_khoa_agent(), timeout=30)
    if c != 200:
        return {}
    toi = str(d.get("caller") or "").upper()
    hang = next((a for a in (d.get("agents") or [])
                 if str(a.get("agent_id", "")).upper() == toi), None)
    return (hang or {}).get("wiki_source") or {}


def _bao_len_console(kb: dict, moi: dict) -> bool:
    c, _ = _goi(f"{_WEB}/api/agents/{AID}/profile", cookie=_khoa_nguoi(),
                body={"wiki_source": {**kb, **moi}})
    return c == 200


def _van_tay(nodes: list[dict]) -> dict:
    """Bản đồ {node → mốc sửa cuối}. Đây là thứ phát hiện được nội dung ĐÃ ĐỔI.

    Đếm số mục H1 không đủ: ai sửa nội dung một tài liệu mà không thêm/bớt mục thì con
    số y nguyên, và người dùng không có tín hiệu nào. Lark cho sẵn `obj_edit_time` trên
    mỗi node — cách agent HR dùng trong `watch_wiki.py`, và đây là bản y như thế.
    """
    return {str(n.get("token")): int(n.get("sua_luc") or 0)
            for n in nodes if n.get("token")}


def _so_van_tay(cu: dict, moi: dict) -> dict:
    """So hai bản đồ → đếm node mới / đã sửa / đã mất."""
    cu = cu or {}
    return {
        "moi": sum(1 for k in moi if k not in cu),
        "sua": sum(1 for k, v in moi.items() if k in cu and v > cu[k]),
        "mat": sum(1 for k in cu if k not in moi),
    }


def _can_quet_lai(kb: dict, lan_quet: float) -> str:
    """Có lý do nào để quét lại ngay không? Trả lý do, hoặc chuỗi rỗng.

    ĐỔI LINK phải quét lại NGAY, không đợi hết 30 phút. Người vừa dán link mới đang
    ngồi nhìn màn hình; bắt họ chờ nửa tiếng đã tệ, nhưng tệ hơn là trong nửa tiếng đó
    console vẫn hiện số liệu của LINK CŨ — tức nói sai, không chỉ chậm.
    """
    da_quet = str((kb.get("last_scan") or {}).get("root_url") or "")
    hien = str(kb.get("root_url") or "")
    if hien and hien != da_quet:
        return "link đổi"
    if time.time() - lan_quet >= NHIP_QUET:
        return "tới hạn"
    return ""


def _can_nhap(kb: dict) -> bool:
    """Chủ agent đã bấm 'Nhập ngay' SAU lần quét/nhập gần nhất chưa?"""
    xin = str(kb.get("xin_nhap_luc") or "")
    if not xin:
        return False
    xong = str(((kb.get("last_scan") or {}).get("nhap_luc")) or "")
    return xin > xong


def mot_luot(nhap: bool) -> dict:
    """Quét một lượt. `nhap=True` thì nhập luôn. Trả tóm tắt để ghi log."""
    # Nạp muộn, và phải chỉ rõ đường: lõi quét nằm ở `scripts/nap_wiki.py` vì nó vốn
    # là công cụ chạy tay. Nạp muộn còn một lợi nữa — `nap_wiki` kéo theo `lark_client`,
    # không nên trả giá đó ở mỗi lần khởi động khi nguồn Wiki đang tắt.
    import sys as _sys
    _sc = str(GOC / "scripts")
    if _sc not in _sys.path:
        _sys.path.insert(0, _sc)
    import nap_wiki as W

    kb = khai_bao()
    if not (kb.get("enabled") and kb.get("root_url")):
        return {"bo_qua": "nguồn chưa bật"}

    kq = W.quet(str(kb["root_url"]))
    if kq.get("loi"):
        _bao_len_console(kb, {"last_scan": {
            "at": _bay_gio(), "nodes": 0, "sections": 0, "imported": 0,
            "unreadable": 0, "root_url": str(kb["root_url"]),
            # Ghi link cả khi lỗi: không ghi thì `_can_quet_lai` thấy "link đổi" mãi
            # và quét lại mỗi 60 giây — một link hỏng thành vòng lặp nện API Lark.
            "note": f"Quét lỗi: {kq['loi']}"[:200]}})
        return {"loi": kq["loi"]}

    vt = _van_tay(kq["nodes"])
    doi = _so_van_tay((kb.get("last_scan") or {}).get("van_tay") or {}, vt)
    tai_lieu, che = W.boc(kq["nodes"])
    bc = {"at": _bay_gio(), "nodes": len(kq["nodes"]), "sections": len(tai_lieu),
          "van_tay": vt, "doi": doi,
          "unreadable": kq["khong_doc"], "imported": 0,
          # Link của CHÍNH lượt quét này — để lần sau biết link có đổi không.
          "root_url": str(kb["root_url"]),
          "note": ("Đã chạm trần số node — cây còn nhánh chưa quét."
                   if kq.get("cham_tran") else "")}

    if not nhap:
        # Giữ nguyên số đã nhập lần trước: lượt này chỉ QUÉT, không đụng kho.
        bc["imported"] = (kb.get("last_scan") or {}).get("imported") or 0
        bc["nhap_luc"] = (kb.get("last_scan") or {}).get("nhap_luc") or ""
        if che:
            bc["note"] = (bc["note"] + f" Đã che {che} chuỗi giống bí mật.").strip()
        _bao_len_console(kb, {"last_scan": bc})
        return {"quet": len(tai_lieu), **({"đổi": doi} if any(doi.values()) else {})}

    da = 0
    for i in range(0, len(tai_lieu), 20):       # API trần 20 tệp mỗi lượt
        lo = tai_lieu[i:i + 20]
        c, _ = _goi(f"{_WEB}/api/agents/{AID}/knowledge", cookie=_khoa_nguoi(),
                    body={"files": lo})
        if c != 200:
            bc["note"] = f"Nhập dở ở lô {i // 20 + 1}: HTTP {c}"
            break
        da += len(lo)
    bc["imported"] = da
    bc["nhap_luc"] = _bay_gio()
    if che:
        bc["note"] = (bc["note"] + f" Đã che {che} chuỗi giống bí mật.").strip()
    _bao_len_console(kb, {"last_scan": bc})
    return {"nhap": da, "tong": len(tai_lieu)}


def _vong(dung: threading.Event) -> None:
    lan_quet = 0.0
    while not dung.is_set():
        try:
            kb = khai_bao()
            if kb.get("enabled") and kb.get("root_url"):
                if _can_nhap(kb):
                    r = mot_luot(nhap=True)
                    print(f"[wiki] chủ agent bấm Nhập ngay → {r}", flush=True)
                    lan_quet = time.time()
                elif (ly_do := _can_quet_lai(kb, lan_quet)):
                    r = mot_luot(nhap=False)
                    print(f"[wiki] quét ({ly_do}) → {r}", flush=True)
                    lan_quet = time.time()
        except Exception as e:
            # Nuốt: nhịp nền hỏng không được làm bot chết hay chậm câu trả lời.
            print(f"[wiki] nhịp lỗi: {type(e).__name__}: {e}", flush=True)
        dung.wait(NHIP_NHAP)


def start_ticker(stop_event: threading.Event | None = None) -> bool:
    """Bật nhịp nền. Trả False nếu thiếu khoá — khi đó bot chạy y như cũ."""
    if not (_khoa_agent() and _khoa_nguoi()):
        return False
    threading.Thread(target=_vong, args=(stop_event or threading.Event(),),
                     name="lsr-wiki", daemon=True).start()
    return True
