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

import datetime
import os
import re
import time
from dataclasses import dataclass

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
        "KHI NÀO GỌI: câu hỏi cần NỘI DUNG trong một Base/Sheet: lọc, tìm ai/cái gì, đọc "
        "câu trả lời mở, rà từng dòng. Nguồn là link người dùng dán (/base/, /sheets/, "
        "/wiki/), hoặc cách gọi ghi trong thẻ mục lục của kho (`sheet:…`, `base:…`, link "
        "Wiki).\n"
        "KHÔNG trả lời câu hỏi về bảng bằng mẩu kho: kho chỉ giữ mục lục, không có dòng.\n"
        "BẮT BUỘC KHI TRẢ LỜI:\n"
        "- Trả lời từ `noi_dung`, dẫn link nguồn. Cần ĐẾM, tính %, so nhóm hay CỘNG tổng "
        "thì gọi `dem_bang` (code đếm, chép số nguyên văn) — không tự đếm trên "
        "`noi_dung`.\n"
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


def _thu_muc_token():
    import pathlib
    try:
        from config import config
        return pathlib.Path(config.token_file).parent
    except Exception:
        return pathlib.Path(__file__).resolve().parent / ".tokens"


def _doc_json_bat_buoc(ten: str) -> tuple[dict | None, bool]:
    """Trả (nội dung, file tồn tại). File có mà hỏng được giữ là trạng thái fail-closed."""
    import json
    f = _thu_muc_token() / ten
    if not f.exists():
        return None, False
    try:
        j = json.loads(f.read_text(encoding="utf-8"))
        return (j if isinstance(j, dict) else None), True
    except Exception:
        return None, True


def _id_app(v) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"[A-Za-z0-9]+", v))


def _id_bang(v) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"tbl[A-Za-z0-9]+", v))


def _ngoai_le_bang_noi_bo(token: str, table_id: str, nguoi: str) -> tuple[bool, str]:
    """Kiểm cấu hình ngoại lệ theo bảng; quyền thật của người hỏi được kiểm ở bước sau."""
    if not nguoi:
        return False, "không biết ai đang hỏi (kênh không gửi danh tính)"
    if not table_id:
        return False, "Base nội bộ chứa cả bảng công việc và Audit/Chi phí; chưa cho phép đúng bảng"

    audit, co_audit = _doc_json_bat_buoc("audit_base.json")
    chi_phi, co_chi_phi = _doc_json_bat_buoc("chi_phi_quet_base.json")
    cu, co_cu = _doc_json_bat_buoc("audit_base.previous.json")
    # Chỉ mở ngoại lệ khi biết đủ cả Audit hiện tại, Audit trước đó và Chi phí. Thiếu
    # previous cũng phải đóng: nếu đoán "không có" ta có thể bỏ sót một bảng cũ còn dữ liệu.
    bat_buoc = (audit, cu, chi_phi)
    if (not co_audit or not co_cu or not co_chi_phi or
            any(not x or not _id_app(x.get("app_token")) or not _id_bang(x.get("table_id"))
                for x in bat_buoc)):
        return False, "metadata bảo vệ Audit/Chi phí chưa đầy đủ; mặc định không mở bảng"
    if audit["app_token"] != token or chi_phi["app_token"] != token:
        return False, "Base nội bộ chưa có cấu hình ngoại lệ theo bảng"
    bao_ve = {(str(x["app_token"]), str(x["table_id"])) for x in (audit, chi_phi, cu)
              if x and x.get("app_token") and x.get("table_id")}
    if (token, table_id) in bao_ve:
        return False, "đây là bảng Audit/Chi phí nội bộ; chỉ chủ agent xem được"

    cho, co_cho = _doc_json_bat_buoc("mixed_base_read_allowlist.json")
    if not co_cho or not cho or cho.get("version") != 1 or not isinstance(cho.get("tables"), list):
        return False, "Base nội bộ chứa cả bảng công việc và Audit/Chi phí; chưa cho phép đúng bảng"
    if not cho["tables"] or any(not isinstance(x, dict) or not _id_app(x.get("app_token"))
                                 or not _id_bang(x.get("table_id")) for x in cho["tables"]):
        return False, "cấu hình bảng được phép không hợp lệ; mặc định không mở bảng"
    cap = {(str(x.get("app_token") or ""), str(x.get("table_id") or ""))
           for x in cho["tables"] if isinstance(x, dict)}
    if (token, table_id) not in cap:
        return False, "Base nội bộ chứa cả bảng công việc và Audit/Chi phí; chưa cho phép đúng bảng"
    return True, "bảng được chủ agent cho phép trong Base hỗn hợp"


def _quyen_thuc_te(loai: str, token: str, nguoi: str) -> tuple[bool, str]:
    """Chứng minh quyền người hỏi, không dùng việc Wiki được khai báo thay cho quyền."""
    try:
        d = lark.call("GET", f"/open-apis/drive/v2/permissions/{token}/public",
                      query={"type": loai})
        if (((d.get("data") or {}).get("permission_public") or {})
                .get("link_share_entity")) in _CONG_TY:
            return True, "mở cho cả công ty"
    except Exception:
        pass
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


#: Câu "vì sao được đọc" khi căn cứ là phép kiểm của Platform cho lịch.
LY_DO_LICH = "người đặt lịch xem được bảng này (Platform kiểm bằng tài khoản Lark của họ)"
#: Câu "vì sao được đọc" cho lịch console (`cach` = `CACH_BOT_CONSOLE`).
LY_DO_LICH_CONSOLE = "lịch console do quản trị agent đặt; bot được cấp quyền xem bảng"
#: `nguon_da_kiem.cach` của lịch đặt trên console bởi quản trị agent (moderator+, Platform
#: kiểm vai trò). Chủ agent chốt 08/10/2026: bỏ "Kết nối tài khoản Lark" — lịch console
#: đọc bằng quyền XEM đã cấp cho bot, và chỉ gửi vào nhóm nhận của chính lịch đó.
CACH_BOT_CONSOLE = "bot_console"
#: Phép kiểm của Platform chỉ còn giá trị trong chừng này (Platform kiểm lại MỖI lần chạy).
_HAN_CHUNG_MINH = 2 * 3600
#: Lệch đồng hồ chấp nhận được giữa Platform và máy chạy Mark.
_LECH_DONG_HO = 300


def _la_open_id(v) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"ou_[A-Za-z0-9]+", v))


@dataclass(frozen=True)
class ChungMinhLich:
    """Bằng chứng quyền xem do PLATFORM tính khi chạy một lịch mode=run (08/10/2026).

    Bot chỉ có quyền XEM tài liệu thì API danh sách thành viên trả 403 — Mark không tự
    chứng minh được người hỏi xem được bảng, và chặn tất cả. Platform đặt vào payload job
    `nguon_da_kiem` = {loai, token, table_id, kiem_luc, boi[, cach, nguoi_dat]}. Chỉ dựng từ
    payload job theo lịch (`lsr_platform._kenh_cua_job`); `nguoi_dat` = `scheduled_by` của
    chính job đó, `nguon_lich` = `schedule_source` của job đó. Hai loại:
      • THEO NGƯỜI (không có `cach`, hoặc `cach` khác): Platform kiểm bằng token Lark CỦA
        người đặt. Chỉ tính khi `boi` == `scheduled_by` == người hỏi.
      • `cach` == "bot_console" (CACH_BOT_CONSOLE): lịch do quản trị agent đặt trên console
        (Platform chỉ cho moderator+ đặt), bot đã được cấp quyền xem bảng. Chỉ tính khi job
        có `schedule_source` == "console"; KHÔNG đòi người hỏi == người đặt.
    Cả hai: (loại, token, bảng) khớp TUYỆT ĐỐI, bảng không rỗng, `kiem_luc` trong 2 giờ
    (lệch tương lai ≤ 5 phút). Không khớp thì như không có. Luật Base nội bộ xét TRƯỚC."""
    loai: str
    token: str
    table_id: str
    kiem_luc: float          # epoch giây
    boi: str
    nguoi_dat: str
    cach: str = ""
    nguon_lich: str = ""

    @classmethod
    def tu_payload(cls, p, nguoi_dat: str, *, nguon_lich: str = "") -> "ChungMinhLich | None":
        """Payload `nguon_da_kiem` → bằng chứng, None nếu thiếu/sai kiểu (không đoán).

        `nguon_lich` = `schedule_source` của job theo lịch ("console" | "lark" | "")."""
        if not isinstance(p, dict):
            return None
        loai, token, bang, boi = (p.get(k) for k in ("loai", "token", "table_id", "boi"))
        if loai not in _TEN_LOAI or not _id_app(token) or not _id_app(bang):
            return None
        if p.get("cach") == CACH_BOT_CONSOLE:
            # Chỉ lịch đặt TRÊN CONSOLE; lịch tạo trong chat ("lark") giữ luật theo người.
            if nguon_lich != "console":
                return None
            if boi in (None, ""):
                boi = ""
            elif not _la_open_id(boi):
                return None
            cach = CACH_BOT_CONSOLE
            nguoi_dat = nguoi_dat if _la_open_id(nguoi_dat) else ""
        else:
            if (not _la_open_id(boi) or not isinstance(nguoi_dat, str) or not nguoi_dat):
                return None
            cach = ""
        try:
            t = datetime.datetime.fromisoformat(
                str(p.get("kiem_luc") or "").replace("Z", "+00:00"))
        except ValueError:
            return None
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return cls(loai, token, bang, t.timestamp(), boi, nguoi_dat, cach,
                   nguon_lich if isinstance(nguon_lich, str) else "")

    @property
    def la_console(self) -> bool:
        return self.cach == CACH_BOT_CONSOLE

    @property
    def ly_do(self) -> str:
        return LY_DO_LICH_CONSOLE if self.la_console else LY_DO_LICH

    def dung_cho(self, loai: str, token: str, table_id: str, nguoi: str,
                 now: float | None = None) -> bool:
        now = time.time() if now is None else now
        khop = (bool(table_id) and bool(self.table_id)
                and (self.loai, self.token, self.table_id) == (loai, token, table_id)
                and now - _HAN_CHUNG_MINH <= self.kiem_luc <= now + _LECH_DONG_HO)
        if self.la_console:
            return khop and self.nguon_lich == "console"
        return khop and bool(nguoi) and self.boi == self.nguoi_dat == nguoi


def quyen_nguoi_hoi(loai: str, token: str, nguoi: str, *wiki_tokens: str,
                    table_id: str = "", chung_minh: ChungMinhLich | None = None
                    ) -> tuple[bool, str]:
    """(được đọc?, vì sao). Chỉ trả True khi CHỨNG MINH được người hỏi có quyền.

    `chung_minh` (chỉ lịch Platform, xem `ChungMinhLich`) thay cho bước tra thành viên —
    SAU mọi luật Base nội bộ, nên không bao giờ mở bảng Audit/Chi phí. Lịch console
    (`bot_console`) không có người hỏi vẫn bị Base nội bộ chặn ("không biết ai đang hỏi")."""
    boss = {x for x in (os.environ.get("AGENT_BOSS_OPEN_ID", "").strip(),
                        os.environ.get("STEVEN_BOSS_OPEN_ID", "").strip()) if x}
    if nguoi and nguoi in boss:
        return True, "chủ agent"
    hop_le = chung_minh is not None and chung_minh.dung_cho(loai, token, table_id, nguoi)
    if token in base_noi_bo():
        ok, ly_do = _ngoai_le_bang_noi_bo(token, table_id, nguoi)
        if not ok:
            return False, ly_do
        if hop_le:
            return True, f"{ly_do}; {chung_minh.ly_do}"
        quyen, bang_chung = _quyen_thuc_te(loai, token, nguoi)
        return (True, f"{ly_do}; {bang_chung}") if quyen else (False, bang_chung)
    if hop_le:
        return True, chung_minh.ly_do
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


def _gon_loi(s) -> str:
    """Lý do từ payload Platform → một dòng ngắn, không thành thẻ `<at>`/`{{@…}}` được."""
    s = " ".join(str(s or "").split())[:200]
    return re.sub(r"\{(?=\{)", "{ ", s.replace("<", "‹").replace(">", "›"))


def _loi_lich_platform(ten_loai: str, loi_lich: str) -> str:
    """Platform báo `nguon_loi` cho lượt theo lịch — nêu lý do + đường sửa trên console."""
    return (f"Không đọc {ten_loai} này theo lịch: Platform chưa kiểm được bảng "
            f"({_gon_loi(loi_lich)}). Mở console → Lịch chạy để kiểm lại: bot Mark đã được "
            "thêm vào tài liệu (quyền xem) và link đúng bảng chưa, rồi lưu lại lịch.")


class TuChoi(Exception):
    """Không mở nguồn cho người hỏi. `str(e)` là câu nói NGUYÊN với người dùng."""


def mo_nguon(nguon: str, *, nguoi_hoi: str | None = None,
             chung_minh: ChungMinhLich | None = None,
             loi_lich: str = "") -> tuple[str, str, str, str, str]:
    """Link/mã → (loại, token, phụ, tên loại, vì sao được đọc) — hoặc ném `TuChoi`.

    Cửa DUY NHẤT cho mọi tool đọc Base/Sheet bằng token bot (`doc_bang`, `dem_bang`).
    Tách ra để tool đếm không có luật quyền thứ hai: hai bản luật thì sớm muộn một bản
    nới hơn bản kia, và Base audit lại thành cửa cho ai cũng đọc được.
    """
    nd = B.nhan_dien_chi_tiet(nguon)
    if not nd:
        raise TuChoi("Không nhận ra link. Cần link Base (/base/), Sheet (/sheets/), "
                     "Wiki (/wiki/), hoặc `sheet:…`/`base:…` từ thẻ mục lục.")
    loai, token, phu, kieu_phu = nd
    node = ""
    if loai == "wiki":
        node = token
        g = B.giai_wiki(node)
        if not g:
            raise TuChoi("Mark không mở được node Wiki này — bot chưa được chia sẻ. "
                         "Nhờ chủ Wiki thêm bot 'Mark Trần - Social Assistant' với quyền xem.")
        loai, token = g
        if loai not in _TEN_LOAI:
            raise TuChoi(f"Node Wiki này là '{loai}', không phải Base hay Sheet. "
                         + ("Tài liệu thì đọc bằng `doc_tai_lieu` với nguyên link này."
                            if loai in _TEN_TAI_LIEU else
                            "Loại này Mark chưa đọc được bằng tool này."))
        if kieu_phu and ((loai == "bitable" and kieu_phu != "table") or
                         (loai == "sheet" and kieu_phu != "sheet")):
            raise TuChoi("Phạm vi table/sheet trong link Wiki không khớp loại tài liệu.")
    ten_loai = _TEN_LOAI[loai]

    # Lệnh cứng chạy trước audit.bat_dau nên truyền asker tường minh. None giữ đường
    # doc_bang/dem_bang cũ; chuỗi rỗng vẫn xét như không có danh tính, không mượn bot.
    # `chung_minh`/`loi_lich`: chỉ `tien_do.lenh_tiendo` truyền, và chỉ cho job THEO LỊCH
    # (lấy từ payload Platform). Không truyền thì mọi đường cũ y như trước. Chỉ phép kiểm
    # `bot_console` của lịch console (khớp bảng, còn mới) mới cho đọc khi người hỏi rỗng.
    them ={"chung_minh": chung_minh} if chung_minh is not None else {}
    ok, vi_sao = quyen_nguoi_hoi(
        loai, token, _nguoi_hoi() if nguoi_hoi is None else nguoi_hoi, node,
        table_id=phu, **them)
    if not ok:
        noi_bo = (token in base_noi_bo() or "Audit/Chi phí" in vi_sao or
                  "bảng được phép" in vi_sao or "metadata bảo vệ" in vi_sao)
        loi_noi_bo = (f"Không đọc {ten_loai} này cho bạn: {vi_sao}. Nhờ chủ agent cấu hình "
                      "đúng cặp app_token/table_id trong mixed_base_read_allowlist.json; không "
                      "mở quyền cho cả Base nội bộ.")
        if chung_minh is not None and chung_minh.la_console:
            # Lịch console: không có "người hỏi" để hướng dẫn xin quyền — chỉ có nội bộ
            # (không mở), lỗi Platform, hoặc phép kiểm không khớp/đã cũ.
            if noi_bo:
                raise TuChoi(loi_noi_bo)
            if loi_lich:
                raise TuChoi(_loi_lich_platform(ten_loai, loi_lich))
            raise TuChoi(
                f"Không đọc {ten_loai} này theo lịch: phép kiểm của Platform không khớp đúng "
                "bảng trong lệnh hoặc đã quá 2 giờ. Mở console → Lịch chạy, kiểm lại link "
                "bảng (đúng ?table=…) rồi lưu lại lịch.")
        if vi_sao.startswith("không biết ai đang hỏi"):
            raise TuChoi(_loi_khong_danh_tinh(ten_loai))
        if noi_bo:
            raise TuChoi(loi_noi_bo)
        if loi_lich:
            raise TuChoi(_loi_lich_platform(ten_loai, loi_lich))
        raise TuChoi(_loi_khong_quyen(ten_loai, vi_sao))
    return loai, token, phu, ten_loai, vi_sao


def _loi_khong_danh_tinh(ten_loai: str) -> str:
    return (f"Không thể kiểm tra quyền đọc {ten_loai}: Console chưa chuyển danh tính "
            "Lark đã xác thực của tài khoản đang hỏi. Hãy mở lại yêu cầu từ Lark. "
            "Chia sẻ thêm tài liệu không tự khắc phục lỗi nhận diện này.")


def _loi_khong_quyen(ten_loai: str, vi_sao: str) -> str:
    return (f"Không đọc {ten_loai} này cho bạn: {vi_sao}. Mark chỉ đọc {ten_loai} mà CHÍNH "
            f"người hỏi cũng được xem. Nhờ chủ {ten_loai} chia sẻ cho bạn, hoặc nhờ chủ agent "
            "thêm nó vào Nguồn Wiki của Mark.")


# ───────────────────────────── tài liệu Docx / Doc (doc_tai_lieu) ─────────────────────────────
#: Loại tài liệu chữ đọc được (`type` của API quyền drive: docx = tài liệu mới, doc = bản cũ).
_TEN_TAI_LIEU = {"docx": "tài liệu", "doc": "tài liệu"}
LOI_BOT_CHUA_CHIA_SE = ("Nhờ chủ tài liệu thêm bot 'Mark Trần - Social Assistant' quyền xem "
                        "(Chia sẻ → thêm ứng dụng/bot), rồi gửi lại link.")


@dataclass(frozen=True)
class TaiLieu:
    """Tài liệu đã MỞ cho người hỏi: bot đọc được VÀ người hỏi được chứng minh có quyền."""
    loai: str                 # "docx" | "doc"
    token: str                # token tài liệu thật (đã giải node Wiki)
    node: str                 # token node Wiki ("" nếu link thẳng)
    ten: str                  # tiêu đề (từ node Wiki hoặc bước thăm dò)
    sua_luc: str              # giây epoch lần sửa cuối nếu node Wiki có ("" nếu không)
    ly_do: str                # vì sao được đọc (từ `quyen_nguoi_hoi`)
    meta: dict                # kết quả bước thăm dò (`tham_do`)


def nhan_dien_tai_lieu(nguon: str) -> tuple[str, str] | None:
    """Link/mã → (kiểu, token). Kiểu: "docx" | "doc" | "wiki" | "?" (token trần).

    Nhận /docx/<tok>, /docs/<tok> (bản cũ), /wiki/<tok>, `docx:<tok>`, `doc:<tok>`,
    `wiki:<tok>` và token trần (thử node Wiki trước, không phải thì coi là docx)."""
    s = (nguon or "").strip()
    m = re.fullmatch(r"(docx|doc|wiki):([A-Za-z0-9]+)", s)
    if m:
        return m.group(1), m.group(2)
    if re.fullmatch(r"[A-Za-z0-9]{16,}", s):
        return "?", s
    try:
        from urllib.parse import urlparse
        p = urlparse(s).path
    except ValueError:
        return None
    for mau, kieu in ((r"/docx/([A-Za-z0-9]+)", "docx"), (r"/docs/([A-Za-z0-9]+)", "doc"),
                      (r"/wiki/([A-Za-z0-9]+)", "wiki")):
        m = re.search(mau, p)
        if m:
            return kieu, m.group(1)
    return None


def mo_tai_lieu(nguon: str, tham_do, *, nguoi_hoi: str | None = None) -> TaiLieu:
    """Link tài liệu → `TaiLieu`, hoặc ném `TuChoi` (câu nói NGUYÊN với người dùng).

    Cùng MỘT luật quyền với `mo_nguon` (Base/Sheet): `quyen_nguoi_hoi` — chủ agent, Nguồn
    Wiki chủ agent khai báo, mở cho cả công ty, thành viên trực tiếp hoặc qua nhóm chat.
    Không có luật thứ hai. Chứng minh quyền người hỏi trước khi thăm dò tài liệu.
    """
    nd = nhan_dien_tai_lieu(nguon)
    if not nd:
        raise TuChoi("Không nhận ra link tài liệu. Cần link Lark Docs (/docx/ hoặc /docs/), "
                     "Wiki (/wiki/), hoặc `docx:<mã>`.")
    kieu, token = nd
    node, ten, sua_luc = "", "", ""
    if kieu in ("wiki", "?"):
        n = B.nut_wiki(token)
        if n is None and kieu == "wiki":
            raise TuChoi("Mark không mở được node Wiki này — bot chưa được chia sẻ. "
                         + LOI_BOT_CHUA_CHIA_SE)
        if n is not None:
            node, loai_nut = token, str(n.get("obj_type") or "")
            token = str(n["obj_token"])
            ten = str(n.get("title") or "")
            sua_luc = str(n.get("obj_edit_time") or "")
            if loai_nut in _TEN_LOAI:
                raise TuChoi(
                    f"Node Wiki này là một {_TEN_LOAI[loai_nut]}, không phải tài liệu chữ. "
                    "Đọc nội dung bằng `doc_bang`, đếm/thống kê bằng `dem_bang` (hoặc lập "
                    "Sheet thống kê bằng `tao_sheet_thong_ke`) với nguyên link này.")
            if loai_nut not in _TEN_TAI_LIEU:
                raise TuChoi(f"Node Wiki này là '{loai_nut}' — Mark chỉ đọc được tài liệu "
                             "chữ (Docs), Base và Sheet.")
            kieu = loai_nut
        else:
            kieu = "docx"
    ten_loai = _TEN_TAI_LIEU[kieu]
    nguoi = _nguoi_hoi() if nguoi_hoi is None else nguoi_hoi
    ok, vi_sao = quyen_nguoi_hoi(kieu, token, nguoi, node)
    if not ok:
        if vi_sao.startswith("không biết ai đang hỏi"):
            raise TuChoi(_loi_khong_danh_tinh(ten_loai))
        raise TuChoi(_loi_khong_quyen(ten_loai, vi_sao))
    try:
        meta = tham_do(kieu, token) or {}
    except Exception as e:  # noqa: BLE001
        raise TuChoi(f"Mark chưa đọc được tài liệu này ({str(e)[:160]}). Thường là do bot "
                     "chưa được chia sẻ. " + LOI_BOT_CHUA_CHIA_SE) from None
    return TaiLieu(kieu, token, node, ten or str(meta.get("ten") or ""), sua_luc, vi_sao,
                   dict(meta))


def loi_doc(ten_loai: str, e: Exception) -> str:
    """Câu báo khi bot không đọc được (thường là chưa được chia sẻ) — dùng chung."""
    if isinstance(e, LookupError):
        return str(e)
    return (f"Mark chưa đọc được {ten_loai} này ({str(e)[:160]}). Thường là do bot chưa được "
            f"chia sẻ — thêm bot 'Mark Trần - Social Assistant' vào {ten_loai} với quyền xem.")


def _handle(args: dict, **_kw) -> str:
    nguon = str((args or {}).get("nguon") or "").strip()
    try:
        loai, token, phu, ten_loai, vi_sao = mo_nguon(nguon)
    except TuChoi as e:
        return tool_error(str(e))
    try:
        kq = B.doc(loai, token, phu)
    except Exception as e:
        return tool_error(loi_doc(ten_loai, e))
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
