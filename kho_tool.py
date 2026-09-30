"""Tool `tra_kho` — tra lại kho kiến thức bằng NHIỀU bộ từ khoá do chính Mark đặt.

VÌ SAO
RAG của platform tìm theo CHỮ (full-text + trigram, bỏ dấu), không theo nghĩa. Hỏi
"doanh thu" mà tài liệu viết "revenue", hỏi "KOC" mà tài liệu viết "người sáng tạo nội
dung" là không khớp — kho có mà Mark vẫn tưởng không có. Mỗi câu hỏi platform lại chỉ
tự đưa 4 mẩu vào prompt.

Dựng dịch vụ embedding là một hệ thống mới phải vận hành. Cách rẻ và đủ: để model — thứ
HIỂU nghĩa — tự viết lại truy vấn: tiếng Việt, tiếng Anh, từ đồng nghĩa, viết tắt, tên
riêng, rồi tra từng bộ qua cửa sẵn có `/v1/self/brain/search` (tới 10 mẩu mỗi bộ), gộp
và bỏ trùng.

Chỉ đọc kho của CHÍNH agent (platform chặn ở đầu kia bằng token agent). CỐ Ý không có
công tắc: tắt nó là quay về đúng lỗi "kho có mà không thấy".
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import lsr_platform

from tools.registry import registry, tool_error, tool_result  # type: ignore

_TIMEOUT = 15
_K_MOI_BO = 10
_TOI_DA_BO = 6
_TOI_DA_MAU = 12

SCHEMA = {
    "name": "tra_kho",
    "description": (
        "Tra lại kho kiến thức riêng của bạn bằng NHIỀU bộ từ khoá bạn tự đặt. Kho tìm "
        "theo CHỮ, không theo nghĩa: 'doanh thu' không khớp 'revenue'.\n"
        "KHI NÀO GỌI: evidence tự có trong prompt không đủ, không khớp, hoặc trống — "
        "TRƯỚC khi kết luận kho không có. Cũng gọi khi câu hỏi tổng hợp cần nhiều mẩu.\n"
        "CÁCH ĐẶT TỪ KHOÁ: 2–6 bộ ngắn, mỗi bộ vài từ, khác nhau thật sự: tiếng Việt và "
        "tiếng Anh, từ đồng nghĩa, viết tắt/viết đầy đủ, tên riêng, mã. Vd hỏi 'doanh thu "
        "tháng 9' → ['doanh thu tháng 9', 'revenue September', 'doanh số', 'sales T9'].\n"
        "Kết quả có thẻ mục lục của Base/Sheet: cần dữ liệu trong bảng thì gọi tiếp "
        "`doc_bang` theo cách gọi ghi trong thẻ."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tu_khoa": {"type": "array", "items": {"type": "string"},
                        "description": "2–6 bộ từ khoá khác nhau (Việt/Anh/đồng nghĩa/viết tắt)."},
        },
        "required": ["tu_khoa"],
    },
}


def _tim(q: str) -> list[dict] | None:
    c = lsr_platform._cau_hinh()
    if not c:
        return None
    qs = urllib.parse.urlencode({"q": q, "k": _K_MOI_BO})
    req = urllib.request.Request(f"{c['platform']}/v1/self/brain/search?{qs}",
                                 headers={"Authorization": f"Bearer {c['key']}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8", "replace") or "{}")
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None
    return [x for x in (d.get("hits") or []) if isinstance(x, dict)]


def gop(ket_qua: dict[str, list[dict]]) -> list[dict]:
    """Gộp kết quả nhiều bộ từ khoá: bỏ trùng theo item_id, cộng điểm, ghi bộ nào khớp.

    Mẩu khớp NHIỀU bộ từ khoá khác nhau là tín hiệu mạnh hơn một bộ điểm cao — cộng
    điểm để nó nổi lên, và cho model thấy nó khớp những bộ nào.
    """
    gom: dict[str, dict] = {}
    for bo, hits in ket_qua.items():
        for h in hits:
            k = str(h.get("item_id") or h.get("title") or "")
            if not k:
                continue
            m = gom.setdefault(k, {**h, "diem": 0.0, "khop": []})
            m["diem"] = round(m["diem"] + float(h.get("score") or 0), 4)
            m["khop"].append(bo)
    ra = sorted(gom.values(), key=lambda x: (len(x["khop"]), x["diem"]), reverse=True)
    return [{"tieu_de": x.get("title") or "", "nguon": x.get("source_url") or "",
             "cap_nhat": str(x.get("updated_at") or "")[:10],
             "khop_bo": x["khop"], "noi_dung": (x.get("content") or "")[:1200]}
            for x in ra[:_TOI_DA_MAU]]


def _handle(args: dict, **_kw) -> str:
    bo = [str(x).strip() for x in ((args or {}).get("tu_khoa") or []) if str(x).strip()]
    bo = list(dict.fromkeys(bo))[:_TOI_DA_BO]
    if not bo:
        return tool_error("Thiếu `tu_khoa`: đưa 2–6 bộ từ khoá khác nhau.")
    kq: dict[str, list[dict]] = {}
    for q in bo:
        h = _tim(q)
        if h is not None:
            kq[q] = h
    if not kq:
        return tool_error("Không tra được kho lúc này (mất kết nối platform). Nói rõ với "
                          "người dùng là chưa tra được, đừng kết luận kho không có.")
    mau = gop(kq)
    return tool_result({"so_bo_da_tra": len(kq), "so_mau": len(mau), "mau": mau,
                        "ghi_chu": ("Không mẩu nào khớp với mọi bộ đã thử — lúc này mới được "
                                    "nói kho không có." if not mau else "")})


def register() -> None:
    try:
        registry.register(
            name="tra_kho", toolset="lark_api", schema=SCHEMA, handler=_handle,
            check_fn=lambda: lsr_platform._cau_hinh() is not None, requires_env=[],
            is_async=False, description="Tra lại kho kiến thức bằng nhiều bộ từ khoá",
            emoji="\U0001f50e", override=True,
        )
    except Exception as e:
        print(f"[kho_tool] register warning: {e}")


register()
