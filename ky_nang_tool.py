"""Tool `dung_ky_nang` — nạp hướng dẫn chi tiết của MỘT kỹ năng, khi agent thấy cần.

VÌ SAO
Trước đây platform nhồi THÂN của mọi kỹ năng vào prompt ở mọi lượt, bất kể câu hỏi là
gì. Sáu kỹ năng của Mark ngốn khoảng 2.000 ký tự mỗi lượt, và model phải tự lọc cái nào
liên quan giữa một đống chữ nằm ngang hàng nhau. Thêm kỹ năng thứ mười thì prompt phình
tiếp còn tỉ lệ liên quan lại giảm — càng nhiều kỹ năng, mỗi kỹ năng càng mờ.

CÁCH LÀM — hai tầng, giống cách Claude dùng skill
    Tầng 1 (luôn có trong prompt): MỤC LỤC — tên + "khi nào dùng" + mã.
    Tầng 2 (nạp khi cần):          THÂN hướng dẫn, lấy qua tool này.

Model đọc mục lục, thấy việc đang làm khớp mô tả "khi nào dùng" thì gọi tool với đúng
mã. Quyết định nằm ở agent, không phải ở platform đoán hộ — đó là điểm khác với RAG.

AN TOÀN
Endpoint `/v1/self/skills/{id}` CHỈ trả kỹ năng agent đang bật ở version sống, và chỉ
nhận token của chính agent. Tool này đi qua `ToolRegistry.dispatch` nên tự động chịu
`lsr_policy` và tự ghi audit — không cần làm gì thêm.

KHÔNG có công tắc Năng lực cho nó, cố ý: tắt đường nạp kỹ năng thì agent vẫn thấy mục
lục trong prompt rồi gọi và ăn từ chối giữa câu trả lời. Muốn bỏ một kỹ năng thì tắt
chính kỹ năng đó ở version, lúc đó nó rụng khỏi mục lục luôn.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import lsr_platform

from tools.registry import registry, tool_error, tool_result  # type: ignore

_TOOLSET = "lark_api"        # đi kèm nhóm sẵn có, không tạo toolset mới
_TIMEOUT = 15

#: Nhớ trong tiến trình: cùng một kỹ năng trong cùng một lượt thì không gọi lại mạng.
#: Không đặt TTL — thân kỹ năng chỉ đổi khi publish version mới, mà publish thì bot
#: khởi động lại. Nhớ mãi trong một đời tiến trình là đúng.
_NHO: dict[str, dict] = {}

SCHEMA = {
    "name": "dung_ky_nang",
    "description": (
        "Nạp hướng dẫn CHI TIẾT của một kỹ năng đã khai trong mục lục 'Kỹ năng của bạn "
        "— nạp khi cần' ở đầu prompt.\n"
        "KHI NÀO GỌI: việc đang làm khớp phần 'khi nào dùng' của một dòng trong mục lục. "
        "Gọi TRƯỚC khi bắt tay làm, rồi làm theo hướng dẫn nhận được.\n"
        "KHI NÀO KHÔNG GỌI: câu hỏi xã giao, hỏi đáp thường, hoặc không dòng nào khớp. "
        "Gọi thừa chỉ tốn thêm một lượt mà không giúp gì.\n"
        "Gọi được nhiều kỹ năng trong một lượt nếu việc đó thật sự cần cả hai.\n"
        "BẮT BUỘC: dùng đúng mã trong mục lục. Đừng đoán mã, đừng tự bịa tên kỹ năng."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": "Mã kỹ năng lấy nguyên văn từ mục lục, dạng `sk_xxxxxxxxxx`.",
            },
        },
        "required": ["skill_id"],
    },
}


def _goi(sid: str) -> tuple[int, dict | None]:
    """Dùng lại cấu hình của `lsr_platform`, không dựng đường thứ hai.

    Gõ tay URL + khoá ở đây là tạo thêm một chỗ phải sửa khi platform đổi địa chỉ, và
    một chỗ nữa để lệch. `_cau_hinh()` đã là nơi duy nhất biết ba biến đó.
    """
    c = lsr_platform._cau_hinh()
    if not c:
        return 0, None
    req = urllib.request.Request(
        f"{c['platform']}/v1/self/skills/{urllib.parse.quote(sid)}",
        headers={"Authorization": f"Bearer {c['key']}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


def _handle(args: dict, **_kwargs) -> str:
    sid = str((args or {}).get("skill_id") or "").strip()
    if not sid:
        return tool_error("Thiếu `skill_id`. Lấy mã nguyên văn từ mục lục kỹ năng.")
    if sid in _NHO:
        return tool_result({**_NHO[sid], "tu_bo_nho": True})

    ma, d = _goi(sid)
    if ma == 404:
        # Nói rõ là KHÔNG CÓ TRONG MỤC LỤC chứ không phải "lỗi hệ thống" — model đoán
        # mã rồi ăn 404 sẽ thử lại mãi nếu tưởng đó là trục trặc tạm thời.
        return tool_error(
            f"Không có kỹ năng `{sid}` trong danh sách đang bật của bạn. "
            "Kiểm lại mã trong mục lục ở đầu prompt; đừng đoán mã.")
    if ma != 200 or not isinstance(d, dict):
        return tool_error(
            f"Không nạp được kỹ năng `{sid}` (HTTP {ma}). Cứ trả lời bằng hiểu biết "
            "chung, nhưng NÓI RÕ là chưa nạp được hướng dẫn chi tiết cho việc này.")

    than = (d.get("instructions") or "").strip()
    if not than:
        return tool_error(
            f"Kỹ năng `{sid}` ({d.get('name') or '?'}) chưa có hướng dẫn chi tiết — "
            "nó mới chỉ là cái nhãn. Cứ làm theo cách thông thường.")

    kq = {"skill_id": d.get("skill_id") or sid, "ten": d.get("name") or "",
          "khi_nao_dung": d.get("description") or "", "huong_dan": than}
    _NHO[sid] = kq
    return tool_result(kq)


def _available() -> bool:
    return lsr_platform._cau_hinh() is not None


def register() -> None:
    try:
        registry.register(
            name="dung_ky_nang", toolset=_TOOLSET, schema=SCHEMA, handler=_handle,
            check_fn=_available, requires_env=[], is_async=False,
            description="Nạp hướng dẫn chi tiết của một kỹ năng khi việc đang làm khớp",
            emoji="\U0001f4d6", override=True,
        )
    except Exception as e:
        print(f"[ky_nang_tool] register warning: {e}")


register()
