"""Fail-closed migration guard for Mark's legacy Hermes runtime.

The long-term enforcement point is ``lsr_hive.tool_executor`` (ADR 0002).  This
module is the temporary EXTC draft adapter: it wraps Hermes' single
``ToolRegistry.dispatch`` convergence point without editing vendored Hermes.
"""

from __future__ import annotations

import json
import os
import types
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


_SAFE_EXACT = {
    "fb_ads_library",
    "web_scrape",
    "list_reminders",
    # Nạp thân hướng dẫn của chính kỹ năng agent đang bật. Chỉ đọc, và platform đã
    # chặn ở đầu kia: `/v1/self/skills/{id}` chỉ nhận token của chính agent và chỉ trả
    # kỹ năng có trong version sống. CỐ Ý không đưa vào `_TOOL_CO_CONG_TAC`: tắt đường
    # nạp thì agent vẫn thấy mục lục trong prompt rồi gọi và ăn từ chối giữa câu trả
    # lời. Muốn bỏ một kỹ năng thì tắt chính nó ở version, nó rụng khỏi mục lục luôn.
    "dung_ky_nang",
    # Chỉ đọc sổ chi phí quét cục bộ của chính chat đang hỏi (chi_phi_tool.py).
    "tra_chi_phi_quet",
    # Đọc nguyên một Base/Sheet (bang_tool.py). Chỉ đọc; tự kiểm NGƯỜI HỎI có quyền xem
    # (bot đọc bằng token của nó, nên không kiểm là lộ Base nội bộ). Có công tắc bên dưới.
    "doc_bang",
    # Tra lại kho của CHÍNH agent bằng nhiều bộ từ khoá (kho_tool.py). Không công tắc —
    # cùng lý do với `dung_ky_nang`: tắt đi là quay về lỗi "kho có mà không thấy".
    "tra_kho",
    # Đọc sổ việc quét nền (viec_nen.py) — chỉ việc của chính chat này / người hỏi này.
    "tra_viec_nen",
    "browser_navigate",
    "browser_snapshot",
    "browser_get_images",
    "browser_get_text",
}
# Tool có tác dụng phụ, kèm QUYỀN PHÁT mà nó đòi. Tên quyền lấy đúng từ
# `connections.out` của manifest (SPEC §2.1), nên hợp đồng khai gì thì ở đây cho
# nấy — không có bảng luật thứ hai chạy song song rồi rộng hoặc hẹp hơn hợp đồng.
#
# Ba tool nghiên cứu ở đầu danh sách đòi `write_data` KHÔNG phải vì việc cào nguy
# hiểm, mà vì chúng gộp kết quả vào một Lark Sheet rồi trả link. Đó là ghi dữ liệu
# ra ngoài hệ thống, nên phải xin đúng quyền đó.
_MUTATING_EXACT = {
    "social_listen": "write_data",       # cào 5 nền tảng → tạo Lark Sheet
    "social_deep_dive": "write_data",    # bóc bình luận → tạo Lark Sheet
    "web_crawl": "write_data",           # cào nhiều trang → tạo Lark Sheet
    "soi_tai_khoan": "write_data",       # soi tài khoản brand/KOC → tạo Lark Sheet
    "soi_san": "write_data",             # giá và sản phẩm Shopee → tạo Lark Sheet
    "schedule_reminder": "write_data",
    "cancel_reminder": "write_data",
    # Huỷ việc quét nền (viec_nen.py): dừng run Apify, ghi sheet phần dở — như cancel_reminder.
    "huy_viec_nen": "write_data",
    "remember_about_user": "write_data",
}
_MUTATING_WORDS = {
    "create", "update", "delete", "remove", "send", "write", "edit",
    "patch", "post", "put", "upload", "move", "copy", "grant", "revoke",
    "approve", "reject", "schedule", "cancel", "invite", "add",
}
_READ_WORDS = {
    "get", "list", "search", "find", "read", "query", "info", "schema",
    "help", "agenda", "status", "download", "export",
}


def _lark_cli_decision(args: dict[str, Any]) -> PolicyDecision:
    argv = args.get("args")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        return PolicyDecision(False, "lark_cli thiếu danh sách args hợp lệ")
    low = [x.strip().lower() for x in argv]
    if "--dry-run" in low:
        return PolicyDecision(True, "lark_cli dry-run không tạo side effect")
    if "--yes" in low:
        # CỐ Ý hẹp hơn hợp đồng. Từ 17/09 Mark là `executive` và có `write_data`,
        # nên `base +record-create --yes` đã nằm trong hợp đồng — nhưng việc ghi mà
        # Mark thật sự cần nằm TRONG `social_listen` (xuất Sheet kết quả), không đi
        # qua `lark_cli`. Chặn ở đây để một lệnh ghi Lark tuỳ ý không lọt qua chỉ
        # nhờ một cờ dòng lệnh. Nới dòng này là mở ghi Base thật, không qua duyệt.
        return PolicyDecision(False, "lark_cli --yes bị chặn ở runtime, hẹp hơn hợp đồng")
    if low[0] in {"schema", "skills", "help", "--help", "-h"} or "--help" in low:
        return PolicyDecision(True, "lệnh discovery chỉ đọc")
    if low[0] == "api":
        method = low[1] if len(low) > 1 else ""
        return PolicyDecision(
            method in {"get", "head"},
            "raw Lark API chỉ cho phép GET/HEAD" if method not in {"get", "head"}
            else "raw Lark API read-only",
        )
    words = {
        part
        for token in low
        for part in token.replace("+", " ").replace("_", " ").replace("-", " ").split()
    }
    if words & _MUTATING_WORDS:
        return PolicyDecision(False, "lark_cli có động từ ghi/gửi")
    if words & _READ_WORDS:
        return PolicyDecision(True, "lark_cli khớp thao tác đọc")
    return PolicyDecision(False, "lark_cli mơ hồ nên fail-closed")


# ─────────────────────── quyền phát: hỏi platform, có đường lùi ───────────────
#
# Trước đây file này tự giữ danh sách cấm. Hệ quả: đổi hợp đồng trên platform mà
# runtime không biết, và ngược lại. Giờ nguồn sự thật là `connections.out` —
# platform tính sẵn và phát trong `/v1/self/stamp`.
#
# BA TẦNG, theo thứ tự tin cậy:
#   1. stamp của platform   — mới nhất, có TTL
#   2. manifest cục bộ      — khi không gọi được platform
#   3. rỗng                 — không khai gì thì không phát gì (fail-closed)
#
# Nhớ tạm theo TTL để không gọi mạng ở mỗi lời gọi tool. Gọi hỏng thì DÙNG LẠI bản
# nhớ cuối chứ không tụt về rỗng: mất mạng một nhịp không nên làm agent câm giữa
# câu trả lời. Hết hạn mà vẫn không gọi được thì mới hạ xuống manifest cục bộ.

_TTL_QUYEN = 300          # giây; stamp của platform TTL 10' nên 5' là đủ mới
_nho: dict[str, Any] = {"quyen": None, "luc": 0.0, "nguon": "chưa hỏi"}


def _quyen_tu_stamp() -> set[str] | None:
    import json as _json
    import os as _os
    import urllib.request as _u
    key = (_os.environ.get("LSR_TELEMETRY_API_KEY") or "").strip()
    base = (_os.environ.get("LSR_PLATFORM_URL")
            or (_os.environ.get("LSR_COLLECTOR") or "").replace("collector.", "platform."))
    if not (key and base):
        return None
    try:
        r = _u.Request(base.rstrip("/") + "/v1/self/stamp",
                       headers={"Authorization": f"Bearer {key}"})
        with _u.urlopen(r, timeout=5) as x:
            d = _json.loads(x.read().decode())
        # Platform bảo dừng phát thì dừng hẳn, bất kể hợp đồng khai gì —
        # đây là kill-switch, không phải gợi ý.
        if d.get("out_allowed") is False:
            return set()
        out = ((d.get("policy") or {}).get("out_allowed")) or []
        return {str(x) for x in out}
    except Exception:
        return None


def _quyen_tu_manifest() -> set[str]:
    import json as _json
    import pathlib as _p
    for ten in ("lsr-agent.yaml", "manifest.json"):
        f = _p.Path(__file__).with_name(ten)
        if not f.is_file():
            continue
        try:
            m = _json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        return {v for c in (m.get("connections") or []) for v in (c.get("out") or [])}
    return set()


def quyen_phat() -> set[str]:
    """Quyền phát hiện hành. Không ném — hỏng thì trả bản nhớ cuối, cùng lắm là rỗng."""
    import time as _t
    gio = _t.time()
    if _nho["quyen"] is not None and (gio - _nho["luc"]) < _TTL_QUYEN:
        return _nho["quyen"]
    q = _quyen_tu_stamp()
    if q is not None:
        _nho.update(quyen=q, luc=gio, nguon="stamp")
        return q
    if _nho["quyen"] is not None:
        return _nho["quyen"]          # giữ bản cũ, đừng câm vì một nhịp mất mạng
    q = _quyen_tu_manifest()
    _nho.update(quyen=q, luc=gio, nguon="manifest cục bộ")
    return q


# ──────────────── công tắc Năng lực trên console: lớp THU HẸP thêm ────────────
#
# Chủ agent bật/tắt từng tool ở khối "Năng lực" trên console. Lựa chọn đó lưu vào
# `agents.capabilities`, và agent tự đọc được của chính mình qua `/v1/self/directory`.
#
# ĐÂY LÀ LỚP THU HẸP, KHÔNG PHẢI RANH GIỚI AN TOÀN. Ranh giới thật vẫn là hợp đồng
# (`out_allowed` ở trên): tool nào hợp đồng không cho thì bật công tắc cũng không chạy.
# Công tắc chỉ có thể làm HẸP thêm, không bao giờ nới ra.
#
# Vì thế chỗ này cố ý KHÔNG fail-closed như `quyen_phat()`:
#   • chưa khai `capabilities`  → không thu hẹp gì (mọi agent khác đang ở trạng thái này;
#                                 coi "trống = tắt hết" là làm chết sạch)
#   • đọc hỏng                  → dùng bản nhớ cuối; chưa đọc được lần nào thì để hợp
#                                 đồng quyết
# Fail-closed ở đây không đổi lại được an toàn nào — hợp đồng vẫn đang giữ — mà chỉ
# khiến một nhịp mất mạng làm Mark câm.

#: Tool mà console cho bật/tắt. Phải khớp `NANG_LUC_THEO_AGENT["AG-SOCIAL-LISTENING"]`
#: trong `apps/platform-web/lib/agentToolCapabilities.ts` của repo Platform —
#: `tests/test_cong_tac_nang_luc.py` đối chiếu khi tìm thấy repo đó.
#:
#: Cần danh sách này vì `capabilities` chỉ chứa tool ĐANG BẬT: không có nó thì runtime
#: không phân biệt được "tool bị tắt" với "tool không nằm trong hệ thống công tắc" —
#: và sẽ tắt nhầm cả `schedule_reminder`, `remember_about_user`…
_TOOL_CO_CONG_TAC = frozenset({
    "social_listen", "social_deep_dive", "fb_ads_library",
    "web_crawl", "web_scrape", "lark_cli", "soi_tai_khoan", "soi_san", "doc_bang",
})

#: Trả về khi agent chưa khai `capabilities` → không áp công tắc nào.
KHONG_THU_HEP = object()

#: 60 giây, CỐ Ý ngắn hơn TTL của hợp đồng (300s). Hai thứ này đổi vì lý do khác nhau:
#: hợp đồng đổi hiếm và đi qua quy trình platform, còn công tắc là cái NÚT người ta bấm
#: rồi thử ngay. Đo thật ở bản 300s: bấm tắt xong hỏi liền thì Mark vẫn hứa "tôi sẽ
#: quét…" và tool vẫn chạy — tức trong suốt cửa sổ đó cái nút không có tác dụng gì.
#: Ai tắt một năng lực vì nó đang chạy sai thì không chờ được 5 phút.
#:
#: Giá phải trả: nhiều nhất một lời gọi mạng mỗi 60 giây, và gọi hỏng thì đã có bản nhớ
#: cuối đỡ.
_TTL_NANG_LUC = float(os.environ.get("LSR_TTL_NANG_LUC_SECONDS", "60"))
_nho_nl: dict[str, Any] = {"bat": None, "luc": 0.0, "nguon": "chưa hỏi"}


def _nang_luc_tu_danh_ba():
    """Đọc `capabilities` của CHÍNH agent này từ danh bạ.

    Trả `None` khi không đọc được, `KHONG_THU_HEP` khi chưa khai, hoặc tập tool bật.
    """
    import json as _json
    import os as _os
    import urllib.request as _u
    key = (_os.environ.get("LSR_TELEMETRY_API_KEY") or "").strip()
    base = (_os.environ.get("LSR_PLATFORM_URL")
            or (_os.environ.get("LSR_COLLECTOR") or "").replace("collector.", "platform."))
    if not (key and base):
        return None
    try:
        r = _u.Request(base.rstrip("/") + "/v1/self/directory",
                       headers={"Authorization": f"Bearer {key}"})
        with _u.urlopen(r, timeout=5) as x:
            d = _json.loads(x.read().decode())
        toi = str(d.get("caller") or "").upper()
        hang = next((a for a in (d.get("agents") or [])
                     if str(a.get("agent_id", "")).upper() == toi), None)
        if hang is None:
            return None
        caps = hang.get("capabilities")
        if not isinstance(caps, list):
            _nho_nl["cau_hinh"] = {}
            return KHONG_THU_HEP          # null / chưa khai
        bat = {str(c["tool"]) for c in caps
               if isinstance(c, dict) and isinstance(c.get("tool"), str)}
        # Ô cấu hình console gắn vào CÙNG mục năng lực (vd trần quét của social_listen).
        # Đọc chung một lượt với công tắc để khỏi thêm lời gọi mạng.
        _nho_nl["cau_hinh"] = {
            str(c["tool"]): dict(c["cau_hinh"]) for c in caps
            if isinstance(c, dict) and isinstance(c.get("tool"), str)
            and isinstance(c.get("cau_hinh"), dict)}
        # Có `capabilities` nhưng không mục nào mang khoá `tool` → dữ liệu do nơi khác
        # ghi, không phải bảng công tắc của console. Không diễn giải bừa thành "tắt hết".
        return bat if bat else KHONG_THU_HEP
    except Exception:
        return None


def nang_luc_bat():
    """Tập tool đang bật, hoặc `KHONG_THU_HEP`. Không bao giờ ném."""
    import time as _t
    gio = _t.time()
    if _nho_nl["bat"] is not None and (gio - _nho_nl["luc"]) < _TTL_NANG_LUC:
        return _nho_nl["bat"]
    b = _nang_luc_tu_danh_ba()
    if b is not None:
        _nho_nl.update(bat=b, luc=gio, nguon="danh bạ")
        return b
    if _nho_nl["bat"] is not None:
        return _nho_nl["bat"]             # giữ bản cũ qua một nhịp mất mạng
    return KHONG_THU_HEP


def cau_hinh_tool(tool: str) -> dict:
    """Ô cấu hình chủ agent đặt cho `tool` trên console, `{}` nếu chưa đặt.

    Giá trị THÔ từ console — nơi dùng phải tự kẹp trong khoảng an toàn của mình.
    Làm mới cùng nhịp TTL với công tắc; đọc hỏng thì giữ bản nhớ cuối.
    """
    nang_luc_bat()
    return dict((_nho_nl.get("cau_hinh") or {}).get(tool) or {})


def decide(tool_name: str, args: dict[str, Any] | None = None) -> PolicyDecision:
    """Hợp đồng xét trước, rồi mới tới công tắc Năng lực.

    Thứ tự này quan trọng: công tắc chỉ thu hẹp thêm trên thứ hợp đồng đã cho. Đảo lại
    thì một công tắc bật lên có thể nới quá hợp đồng — đúng kiểu lỗi mà cả hệ thống này
    đang cố tránh.
    """
    d = _quyet_dinh_theo_hop_dong(tool_name, args)
    if not d.allowed:
        return d
    name = (tool_name or "").strip()
    if name in _TOOL_CO_CONG_TAC:
        bat = nang_luc_bat()
        if bat is not KHONG_THU_HEP and name not in bat:
            return PolicyDecision(
                False,
                f"'{name}' đang TẮT ở khối Năng lực trên console — chủ agent đã tắt, "
                f"không phải thiếu quyền")
    return d


#: Nơi runtime lưu ảnh người dùng gửi qua Lark. `vision_analyze` chỉ được đọc ảnh ở đây
#: (hoặc ảnh trên web) — không được trỏ tới file bất kỳ trên máy của đội.
THU_MUC_DINH_KEM = Path(__file__).resolve().with_name(".dinh_kem")


def _vision_decision(payload: dict[str, Any]) -> PolicyDecision:
    """Đọc ảnh: CHỈ ảnh người dùng vừa gửi, hoặc ảnh công khai trên web.

    Trước đây tool này bị chặn hoàn toàn (fail-closed vì chưa khai), trong khi prompt
    lại quảng cáo "đọc ẢNH (vision)". Người gửi ảnh ngày 23/09 nhận câu "chưa đọc được
    ảnh từ hệ thống" — nghe như lỗi hệ thống, thật ra là bị chặn quyền.

    Không mở trắng: `image_url` nhận cả đường dẫn file cục bộ, nên mở hết là cho model
    đọc được mọi file ảnh trên máy cá nhân của chủ agent. Chỉ nhận ảnh trong thư mục
    đính kèm mà runtime tự tải về, hoặc URL http(s).
    """
    url = str(payload.get("image_url") or "").strip()
    if url.lower().startswith(("http://", "https://")):
        return PolicyDecision(True, "vision: ảnh công khai trên web")
    if not url:
        return PolicyDecision(False, "vision: thiếu image_url")
    try:
        p = Path(url).expanduser().resolve()
        p.relative_to(THU_MUC_DINH_KEM)
    except (ValueError, OSError):
        return PolicyDecision(False, "vision: chỉ được đọc ảnh người dùng gửi kèm tin nhắn")
    return PolicyDecision(True, "vision: ảnh người dùng gửi kèm")


def _quyet_dinh_theo_hop_dong(tool_name: str, args: dict[str, Any] | None = None
                              ) -> PolicyDecision:
    """Quyết định theo hợp đồng. Giữ nguyên như trước khi có công tắc."""
    name = (tool_name or "").strip()
    payload = args if isinstance(args, dict) else {}
    if name == "lark_cli":
        return _lark_cli_decision(payload)
    if name == "vision_analyze":
        return _vision_decision(payload)
    if name in _MUTATING_EXACT:
        can = _MUTATING_EXACT[name]
        if can in quyen_phat():
            return PolicyDecision(True, f"{name}: hợp đồng có '{can}'")
        return PolicyDecision(
            False,
            f"{name} cần quyền '{can}' — hợp đồng khai "
            f"{sorted(quyen_phat()) or 'chưa khai gì'}")
    if name in _SAFE_EXACT:
        return PolicyDecision(True, "tool đọc đã được allowlist")
    if name.startswith("browser_"):
        unsafe = ("click", "type", "fill", "submit", "upload", "download")
        if any(x in name for x in unsafe):
            return PolicyDecision(False, "browser action có thể tạo side effect")
        return PolicyDecision(True, "browser read-only")
    if any(word in name.lower() for word in _MUTATING_WORDS):
        return PolicyDecision(False, "tên tool biểu thị thao tác ghi")
    return PolicyDecision(False, "tool chưa có trong policy bundle nên fail-closed")


def install_registry_guard(audit_callback: Callable[..., None] | None = None) -> bool:
    """Wrap Hermes ``registry.dispatch`` once; return True when installed."""
    try:
        from tools.registry import registry  # type: ignore
    except Exception:
        return False
    if getattr(registry, "_lsr_guard_installed", False):
        return True

    original = registry.dispatch
    mode = os.environ.get("LSR_POLICY_MODE", "enforce").strip().lower()
    if mode not in {"off", "observe", "enforce"}:
        mode = "enforce"

    def guarded(self, name: str, args: dict, **kwargs):
        if mode == "off":
            return original(name, args, **kwargs)
        verdict = decide(name, args)
        if verdict.allowed:
            return original(name, args, **kwargs)
        if audit_callback:
            audit_callback(name, args, None, 0.0, loi=f"policy: {verdict.reason}")
        if mode == "observe":
            return original(name, args, **kwargs)
        return json.dumps(
            {
                "error": "policy_denied",
                "tool": name,
                "reason": verdict.reason,
                "allowed_actions": ["read", "analyze", "reply", "call_agent"],
            },
            ensure_ascii=False,
        )

    registry.dispatch = types.MethodType(guarded, registry)
    registry._lsr_guard_installed = True
    registry._lsr_guard_mode = mode
    return True
