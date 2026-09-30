"""Tool `doc_bang` (lệnh /bang) — đọc NGUYÊN một Base hoặc Sheet của Lark khi được hỏi.

AI ĐƯỢC ĐỌC
Mark đọc bằng token BOT, không phải của người hỏi. Bot lại có quyền trên Base nội bộ —
vd Base audit chứa câu hỏi của MỌI người. "Bot đọc được là trả" thì ai dán link Base
audit vào chat cũng đọc được nhật ký của người khác. Nên phải CẢ HAI cùng có quyền:
bot đọc được, VÀ người hỏi thuộc một trong các trường hợp sau:
  1. là chủ agent (AGENT_BOSS_OPEN_ID);
  2. Base/Sheet nằm trong cây Wiki chủ agent đã khai báo (chủ agent đã chọn cho bot đọc);
  3. Base/Sheet mở cho cả công ty (link_share_entity tenant_/anyone_…);
  4. người hỏi là thành viên — trực tiếp, hoặc qua nhóm chat được chia sẻ.
Không kiểm được thì ĐÓNG: nói rõ vì sao và chỉ cách xin quyền, không đoán.

Đi qua `ToolRegistry.dispatch` nên chịu `lsr_policy` (có công tắc Năng lực) và tự ghi
audit như mọi tool.
"""
from __future__ import annotations

import os

import lark_bang as B
import lark_client as lark

from tools.registry import registry, tool_error, tool_result  # type: ignore

_CONG_TY = {"tenant_readable", "tenant_editable", "anyone_readable", "anyone_editable"}
_TEN_LOAI = {"bitable": "Base", "sheet": "Sheet"}

SCHEMA = {
    "name": "doc_bang",
    "description": (
        "Đọc NGUYÊN một Base hoặc Sheet của Lark — mọi bảng/tab, mọi cột, mọi dòng (tới "
        "trần 2.000 dòng) — bản MỚI NHẤT, ngay lúc hỏi.\n"
        "KHI NÀO GỌI: câu hỏi cần dữ liệu trong một Base/Sheet: đếm, lọc, tổng hợp, tìm "
        "ai/cái gì, so sánh. Nguồn là link người dùng dán (/base/, /sheets/, /wiki/), hoặc "
        "cách gọi ghi trong thẻ mục lục của kho (`sheet:…`, `base:…`, link Wiki).\n"
        "KHÔNG trả lời câu hỏi về bảng bằng mẩu kho: kho chỉ giữ mục lục, không có dòng.\n"
        "BẮT BUỘC KHI TRẢ LỜI:\n"
        "- Trả lời từ `noi_dung`, dẫn link nguồn. Đếm/tính thì tính trên đúng các dòng "
        "đã đọc.\n"
        "- `bi_cat`=true: mới đọc một phần — nói rõ đã đọc bao nhiêu/tổng bao nhiêu dòng, "
        "đừng trình bày như toàn bộ.\n"
        "- Bị từ chối vì quyền thì chuyển NGUYÊN lời hướng dẫn cho người dùng, đừng tìm "
        "đường khác để đọc."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "nguon": {"type": "string",
                      "description": "Link Base/Sheet/Wiki, hoặc `sheet:<mã>` / `base:<mã>` "
                                     "lấy nguyên văn từ thẻ mục lục."},
        },
        "required": ["nguon"],
    },
}


def _nguoi_hoi() -> str:
    try:
        import chi_phi_tool
        return chi_phi_tool._luot_hien_tai().get("nguoi") or ""
    except Exception:
        return ""


def _trong_cay_wiki(*tokens: str) -> bool:
    """Token có nằm trong cây Wiki chủ agent đã khai báo (theo lần quét gần nhất)?"""
    try:
        import wiki_tu_dong
        kb = wiki_tu_dong.khai_bao()
    except Exception:
        return False
    if not kb.get("enabled"):
        return False
    co: set[str] = set()
    for c in ((kb.get("last_scan") or {}).get("chi_tiet") or []):
        co.update(x for x in (c.get("token"), c.get("obj_token")) if x)
        co.update(str(x).split("_")[0] for x in (c.get("nhung") or []))
    return any(t and t in co for t in tokens)


def _trong_chat(chat_id: str, nguoi: str) -> bool:
    try:
        for m in B._trang(f"/open-apis/im/v1/chats/{chat_id}/members",
                          {"member_id_type": "open_id", "page_size": 100}, toi_da=5000):
            if m.get("member_id") == nguoi:
                return True
    except Exception:
        pass
    return False


def base_noi_bo() -> set[str]:
    """Base nội bộ của CHÍNH Mark (audit, sổ chi phí…) — lấy từ `.tokens/*.json`.

    Đây là chỗ giữ câu hỏi và câu trả lời của MỌI người. 01/10: chủ agent đặt Nguồn Wiki
    trỏ đúng vào Base audit, và luật "nằm trong Nguồn Wiki thì ai hỏi cũng đọc được" biến
    nó thành cửa cho mọi người đọc nhật ký của nhau. Nên các Base này bị chặn TRƯỚC mọi
    căn cứ khác, trừ chủ agent.
    """
    import json
    import pathlib
    ra: set[str] = set()
    try:
        from config import config
        thu_muc = pathlib.Path(config.token_file).parent
    except Exception:
        thu_muc = pathlib.Path(__file__).resolve().parent / ".tokens"
    for f in thu_muc.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(j, dict):
            ra.update(str(j[k]) for k in ("app_token", "base_token") if j.get(k))
    return ra


def quyen_nguoi_hoi(loai: str, token: str, nguoi: str, *wiki_tokens: str) -> tuple[bool, str]:
    """(được đọc?, vì sao). Chỉ trả True khi CHỨNG MINH được người hỏi có quyền."""
    boss = {x for x in (os.environ.get("AGENT_BOSS_OPEN_ID", "").strip(),
                        os.environ.get("STEVEN_BOSS_OPEN_ID", "").strip()) if x}
    if nguoi and nguoi in boss:
        return True, "chủ agent"
    if token in base_noi_bo():
        return False, "đây là Base nội bộ của Mark (nhật ký hỏi–đáp, chi phí) — chỉ chủ agent xem được"
    if _trong_cay_wiki(token, *wiki_tokens):
        return True, "nằm trong Nguồn Wiki chủ agent đã khai báo"
    try:
        d = lark.call("GET", f"/open-apis/drive/v2/permissions/{token}/public",
                      query={"type": loai})
        if (((d.get("data") or {}).get("permission_public") or {})
                .get("link_share_entity")) in _CONG_TY:
            return True, "mở cho cả công ty"
    except Exception:
        pass
    if not nguoi:
        return False, "không biết ai đang hỏi (kênh không gửi danh tính)"
    try:
        tv = B._trang(f"/open-apis/drive/v1/permissions/{token}/members",
                      {"type": loai}, toi_da=2000)
    except Exception:
        return False, "Mark không xem được danh sách người có quyền để đối chiếu"
    for m in tv:
        if m.get("member_type") == "openid" and m.get("member_id") == nguoi:
            return True, "là thành viên"
    for m in tv:
        if m.get("member_type") == "openchat" and _trong_chat(str(m.get("member_id")), nguoi):
            return True, "thuộc nhóm chat được chia sẻ"
    return False, "chưa thấy bạn trong danh sách người có quyền"


def _handle(args: dict, **_kw) -> str:
    nguon = str((args or {}).get("nguon") or "").strip()
    nd = B.nhan_dien(nguon)
    if not nd:
        return tool_error("Không nhận ra link. Cần link Base (/base/), Sheet (/sheets/), "
                          "Wiki (/wiki/), hoặc `sheet:…`/`base:…` từ thẻ mục lục.")
    loai, token, phu = nd
    node = ""
    if loai == "wiki":
        node = token
        g = B.giai_wiki(node)
        if not g:
            return tool_error("Mark không mở được node Wiki này — bot chưa được chia sẻ. "
                              "Nhờ chủ Wiki thêm bot 'Mark Trần - Social Assistant' với quyền xem.")
        loai, token = g
        if loai not in _TEN_LOAI:
            return tool_error(f"Node Wiki này là '{loai}', không phải Base hay Sheet. Tài liệu "
                              "Wiki thì tra trong kho kiến thức, không đọc bằng tool này.")
    ten_loai = _TEN_LOAI[loai]

    ok, vi_sao = quyen_nguoi_hoi(loai, token, _nguoi_hoi(), node)
    if not ok:
        return tool_error(
            f"Không đọc {ten_loai} này cho bạn: {vi_sao}. Mark chỉ đọc {ten_loai} mà CHÍNH "
            f"người hỏi cũng được xem. Nhờ chủ {ten_loai} chia sẻ cho bạn, hoặc nhờ chủ agent "
            "thêm nó vào Nguồn Wiki của Mark.")
    try:
        kq = B.doc(loai, token, phu)
    except Exception as e:
        return tool_error(
            f"Mark chưa đọc được {ten_loai} này ({str(e)[:160]}). Thường là do bot chưa được "
            f"chia sẻ — thêm bot 'Mark Trần - Social Assistant' vào {ten_loai} với quyền xem.")
    return tool_result({"nguon": nguon, "loai": ten_loai, "ten": kq["ten"],
                        "ly_do_duoc_doc": vi_sao, "bang": kq["bang"],
                        "bi_cat": kq["bi_cat"], "noi_dung": kq["noi_dung"]})


def register() -> None:
    try:
        registry.register(
            name="doc_bang", toolset="lark_api", schema=SCHEMA, handler=_handle,
            check_fn=lambda: True, requires_env=[], is_async=False,
            description="Đọc nguyên một Base hoặc Sheet của Lark (người hỏi phải có quyền xem)",
            emoji="\U0001f4ca", override=True,
        )
    except Exception as e:
        print(f"[bang_tool] register warning: {e}")


register()
