"""Seed (mồi) một kênh chat 1-1 để agent có thể NHẬN tin nhắn 1-1.

Vì Lark KHÔNG cho user-token liệt kê các chat 1-1 (/im/v1/chats chỉ trả group),
ta cần biết trước chat_id của DM. Cách lấy: gửi 1 tin từ Steven cho người đó
(response trả về chat_id), rồi ghi nhớ vào .tokens/poll-chats.json.

    python seed_p2p.py "Lê Quý Thiện"
    python seed_p2p.py someone@hapas.vn
    python seed_p2p.py ou_xxxxxxxx

Sau khi seed 1 lần, người đó nhắn 1-1 cho Steven là agent sẽ trả lời.
"""

from __future__ import annotations

import sys

import lark_client as lark
from poller import register_chat


def resolve_open_id(q: str) -> str:
    if q.startswith("ou_"):
        return q
    r = lark.call("GET", "/open-apis/search/v1/user", as_="user", query={"query": q, "page_size": 1})
    users = r.get("data", {}).get("users", [])
    if not users:
        raise SystemExit(f"❌ Không tìm thấy người khớp: {q}")
    u = users[0]
    print(f"→ Khớp: {u.get('name')} ({u.get('open_id')})")
    return u["open_id"]


def main() -> None:
    if len(sys.argv) < 2:
        print('Cách dùng: python seed_p2p.py "<tên | email | open_id>"')
        return
    q = " ".join(sys.argv[1:]).strip()
    open_id = resolve_open_id(q)
    r = lark.send_text(
        "open_id",
        open_id,
        "Xin chào, em là Steven 👋 (kích hoạt kênh chat — từ giờ anh/chị nhắn em ở đây nhé).",
        as_user=True,
    )
    chat_id = r.get("data", {}).get("chat_id")
    if chat_id:
        register_chat(chat_id)
        print(f"✅ Đã seed chat 1-1: {chat_id}")
        print("   Người này nhắn 1-1 cho Steven từ giờ sẽ được agent trả lời.")
    else:
        print(f"⚠️ Gửi xong nhưng không thấy chat_id trong response: {r}")


if __name__ == "__main__":
    main()
