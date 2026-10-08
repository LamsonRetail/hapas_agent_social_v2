"""Hai tool ghi DANH SÁCH VIỆC ĐÃ DUYỆT vào Base checklist của team (Lark Bitable).

  • `xem_truoc_viec_base` — đọc Base (cột + dòng), tính sẵn từng việc sẽ TẠO / CẬP NHẬT /
    GIỮ NGUYÊN / CẦN XEM / LỖI, lưu bản xem trước ở máy (`.tokens/viec_base/`) và trả câu
    xem trước cho Mark chép nguyên. KHÔNG ghi gì lên Lark.
  • `ghi_viec_base` — chỉ nhận MÃ xem trước (và danh sách dòng bỏ ra); ghi đúng những
    dòng đã xem trước. Không nhận dữ liệu việc nào từ model.

Vì sao cần — 05–06/10/2026: team dán biên bản họp, xin "tạo task luôn, đưa lên checklist".
Kỹ năng họp và bàn giao bắt Mark trả danh sách để người dùng tự dán tay. Chủ agent duyệt
06/10 (thiết kế lark_task_design.md): Mark được GHI, nhưng chỉ sau khi chính người nhờ
xem bản xem trước và đồng ý ở tin nhắn sau.

BẤT BIẾN (kiểm bằng code, không phải lời dặn — đây là chỗ ghi lên Base chung của team):
  1. Base/bảng đích lấy từ cấu hình máy chạy (`MARK_BASE_VIEC_*`), không bao giờ từ tham
     số model. Mã chiến dịch trong khoá chống trùng cũng vậy.
  2. Người duyệt = đúng người nhờ xem trước, trong đúng cuộc chat đó (open_id + chat id).
     Bản xem trước sống 24 giờ, tối đa 50 việc, bị sửa tay (lệch `bam`) thì từ chối.
  3. Chỉ gọi 4 endpoint Bitable trong `_DUONG_CHO_PHEP` — không IM, không Task, không xoá,
     không tạo cột/bảng. Gọi ngoài danh sách là ném lỗi trước khi ra mạng.
  4. Không bao giờ tạo lựa chọn select mới (Lark TỰ tạo khi ghi tên lạ): NHÓM không khớp
     lựa chọn có sẵn → dòng LỖI, không ghi.
  5. Dòng đã có chỉ được điền Ô TRỐNG; TRẠNG THÁI của dòng đã có không bao giờ đổi. Dòng
     bị người sửa sau lúc xem trước thì bỏ qua.
  6. Chạy lại không tạo trùng: đọc lại cột "Mã việc Mark" trước khi tạo, và mỗi lô tạo
     mang `client_token` cố định (Lark khử trùng lô gửi lại). Code KHÔNG tự tạo cột mã:
     Base thiếu cột đó thì từ chối, nói rõ chủ Base cần thêm.

Bật/tắt: `MARK_GHI_VIEC_BASE=1` mới chạy (mặc định tắt) — console chưa có công tắc riêng
cho tool này (xem `lsr_policy._CAN_BIEN_MOI_TRUONG`). Ghi PIC: `MARK_BASE_VIEC_GHI_PIC=0`
để tắt nếu staging cho thấy Lark báo tin cho người được gán.
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
import os
import re
import secrets
import threading
import time
import unicodedata
import uuid
from urllib.parse import parse_qs, urlparse

import lark_client as lark
import memory_store
from config import config

from tools.registry import registry, tool_error, tool_result  # type: ignore

# ───────────────────────────── cấu hình ─────────────────────────────
#: Mặc định: Base CHECKLIST DA 20.10 của team. Staging đè bằng env trỏ sang bản sao.
_URL_MAC_DINH = ("https://o4pvcegwn6b.sg.larksuite.com/base/SBfNb16GDaDVS5s8rpol8EjQgSg"
                 "?table=tbluIfPgSyOVIAg2")
_TEN_MAC_DINH = "CHECKLIST DA 20.10"
_CHIEN_DICH_MAC_DINH = "20.10"
_COT_MA_MAC_DINH = "Mã việc Mark"

_TOI_DA_DONG = 50                 # việc mỗi bản xem trước (D8)
_HAN_XEM_TRUOC = 24 * 3600        # giây (D8)
_GIU_FILE = 7 * 24 * 3600         # file bản xem trước cũ hơn hạn + 7 ngày thì dọn
_TOI_DA_TRANG = 20                # trang × 500 dòng khi đọc Base
_VN = datetime.timezone(datetime.timedelta(hours=7))

#: Cột Mark được ghi, kèm kiểu v1 của Bitable (1 chữ, 3 chọn một, 5 ngày, 11 người).
#: Cột mã việc (cấu hình được) thêm vào lúc chạy, kiểu 1.
COT_TEN, COT_NHOM, COT_PIC = "HẠNG MỤC CV", "NHÓM", "PIC"
COT_HAN, COT_TT, COT_KQ = "DEADLINE", "TRẠNG THÁI", "KẾT QUẢ CẦN ĐẠT"
_KIEU = {COT_TEN: 1, COT_NHOM: 3, COT_PIC: 11, COT_HAN: 5, COT_TT: 3, COT_KQ: 1}
_TT_MOI = "CẦN LÀM"

_THU_MUC = config.token_file.parent / "viec_base"
_KHOA = threading.Lock()

_CAU_TAT = ("Ghi việc vào Base đang TẮT ở máy chạy Mark (MARK_GHI_VIEC_BASE). Đưa danh sách "
            "việc đúng cột để người dùng tự dán vào Base.")


def _bat() -> bool:
    return os.environ.get("MARK_GHI_VIEC_BASE", "").strip() == "1"


def _ghi_pic_bat() -> bool:
    return os.environ.get("MARK_BASE_VIEC_GHI_PIC", "1").strip() != "0"


def cau_hinh() -> dict:
    """Base/bảng đích + mã chiến dịch, CHỈ từ env của máy chạy. Ném ValueError nếu hỏng."""
    url = (os.environ.get("MARK_BASE_VIEC_URL") or "").strip() or _URL_MAC_DINH
    u = urlparse(url)
    m = re.search(r"/base/([A-Za-z0-9]+)", u.path or "")
    app = (os.environ.get("MARK_BASE_VIEC_APP_TOKEN") or "").strip() or (m.group(1) if m else "")
    bang = ((os.environ.get("MARK_BASE_VIEC_TABLE_ID") or "").strip()
            or (parse_qs(u.query).get("table") or [""])[0])
    if not re.fullmatch(r"[A-Za-z0-9]{10,}", app or ""):
        raise ValueError("MARK_BASE_VIEC_URL/APP_TOKEN không có mã Base hợp lệ (cần link /base/…)")
    if not re.fullmatch(r"tbl[A-Za-z0-9]+", bang or ""):
        raise ValueError("MARK_BASE_VIEC_URL/TABLE_ID không có mã bảng hợp lệ (?table=tbl…)")
    goc = f"{u.scheme or 'https'}://{u.hostname or 'o4pvcegwn6b.sg.larksuite.com'}"
    return {
        "app_token": app, "table_id": bang,
        "url": f"{goc}/base/{app}?table={bang}",
        "ten": (os.environ.get("MARK_BASE_VIEC_TEN") or "").strip() or _TEN_MAC_DINH,
        "chien_dich": ((os.environ.get("MARK_BASE_VIEC_CHIEN_DICH") or "").strip()
                       or _CHIEN_DICH_MAC_DINH),
        "cot_ma": (os.environ.get("MARK_BASE_VIEC_COT_MA") or "").strip() or _COT_MA_MAC_DINH,
    }


def _khoa_dich(d: dict) -> tuple:
    return (d["app_token"], d["table_id"], d["chien_dich"], d["cot_ma"])


# ───────────────────────────── gọi Lark: danh sách endpoint cố định ─────────────────────────────
_GOC_BANG = r"^/open-apis/bitable/v1/apps/[A-Za-z0-9]+/tables/tbl[A-Za-z0-9]+"
#: Ý "preset" của lark-openapi-mcp: tool này CHỈ gọi được đúng 4 đường dưới đây. Không IM,
#: không task.v2, không DELETE, không tạo cột — test đối chiếu mọi lời gọi với bảng này.
_DUONG_CHO_PHEP = (
    ("GET", re.compile(_GOC_BANG + r"/fields$")),
    ("POST", re.compile(_GOC_BANG + r"/records/search$")),
    ("POST", re.compile(_GOC_BANG + r"/records/batch_create$")),
    ("POST", re.compile(_GOC_BANG + r"/records/batch_update$")),
)
_ngu = time.sleep       # bộ thử thay để khỏi chờ thật


def _goi(method: str, path: str, query: dict | None = None, body=None) -> dict:
    if not any(m == method and r.match(path) for m, r in _DUONG_CHO_PHEP):
        raise PermissionError(f"viec_base: endpoint ngoài danh sách cho phép: {method} {path}")
    return lark.call(method, path, query=query, body=body)


def _goc(d: dict) -> str:
    return f"/open-apis/bitable/v1/apps/{d['app_token']}/tables/{d['table_id']}"


def _thu_lai_duoc(e: Exception) -> bool:
    """Lark từ chối ghi đồng thời vào một bảng (1254291), quá tải (1254290), HTTP 429/5xx."""
    s = str(e)
    if re.search(r"'code':\s*125429[01]\b", s):
        return True
    h = re.search(r"HTTP (\d{3})", s)
    return bool(h and (h.group(1) == "429" or h.group(1).startswith("5")))


def _goi_ghi(path: str, query: dict, body: dict) -> dict:
    for lan in range(3):
        try:
            return _goi("POST", path, query, body)
        except PermissionError:
            raise
        except Exception as e:  # noqa: BLE001
            if lan < 2 and _thu_lai_duoc(e):
                _ngu(1.5 * (lan + 1))
                continue
            raise
    raise RuntimeError("không tới được")  # pragma: no cover


# ───────────────────────────── chuẩn hoá chữ ─────────────────────────────
_MEP = " \t.,;:!?-–—_/|*\"'()[]{}"


def chuan(s) -> str:
    """Khoá so khớp: bỏ dấu (đ→d), chữ thường, gộp khoảng trắng, bỏ dấu câu ở hai đầu."""
    s = unicodedata.normalize("NFC", str(s or "")).lower().replace("đ", "d")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.split()).strip(_MEP)


def _gon(s) -> str:
    """Chữ để GHI: giữ dấu, NFC, gộp khoảng trắng."""
    return " ".join(unicodedata.normalize("NFC", str(s or "")).split())


def ma_viec(chien_dich: str, nhom: str, hang_muc: str) -> str:
    """Khoá chống trùng: chiến dịch (từ cấu hình) | NHÓM chuẩn | HẠNG MỤC CV chuẩn."""
    goc = f"{chuan(chien_dich)}|{chuan(nhom)}|{chuan(hang_muc)}"
    return "MK-" + hashlib.sha256(goc.encode("utf-8")).hexdigest()[:10].upper()


def _client_token(ma: str, khoa: list[str]) -> str:
    """uuid dạng v4 (Lark đòi "standard uuidv4") nhưng TẤT ĐỊNH theo bản xem trước + lô."""
    b = bytearray(hashlib.sha256((ma + "|" + ",".join(khoa)).encode("utf-8")).digest()[:16])
    b[6] = (b[6] & 0x0F) | 0x40
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def _chu(v) -> str:
    """Giá trị ô Bitable (chữ dạng đoạn, chọn, người…) → chữ trơn."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, dict):
        return str(v.get("text") or v.get("name") or v.get("value") or "")
    if isinstance(v, list):
        return "".join(_chu(x) for x in v)
    return str(v)


def _nguoi(v) -> list[tuple[str, str]]:
    return [(str(x["id"]), str(x.get("name") or "")) for x in (v or [])
            if isinstance(x, dict) and x.get("id")] if isinstance(v, list) else []


def _trong(v) -> bool:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return False
    return not _chu(v).strip() and not _nguoi(v)


def _ngay_ms(s) -> tuple[int | None, str | None, str]:
    """'2026-10-24' / '2026/10/24' (có thể kèm *) → (ms lúc 00:00 giờ VN, lỗi, chữ hiện)."""
    s = str(s or "").strip()
    if not s:
        return None, None, ""
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\*?", s)
    if not m:
        return None, f"hạn '{s}' không đọc được (cần yyyy-mm-dd)", ""
    try:
        d = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=_VN)
    except ValueError:
        return None, f"hạn '{s}' không phải ngày có thật", ""
    return int(d.timestamp() * 1000), None, f"{d:%Y/%m/%d}"


def _ngay_hien(ms) -> str:
    try:
        return f"{datetime.datetime.fromtimestamp(int(ms) / 1000, _VN):%Y/%m/%d}"
    except (TypeError, ValueError, OverflowError, OSError):
        return str(ms)


def _ten_goc(ten: str) -> str:
    """'Linh Ngọc - Booking KOC/KOL Leader' → 'Linh Ngọc'."""
    return re.split(r"\s+[-–—|]\s+", (ten or "").strip(), maxsplit=1)[0].strip()


# ───────────────────────────── đọc Base ─────────────────────────────
def _doc_cot(d: dict) -> dict[str, dict]:
    ra, tok = {}, None
    for _ in range(_TOI_DA_TRANG):
        kq = _goi("GET", _goc(d) + "/fields", query={"page_size": 100, "page_token": tok})
        data = kq.get("data") or {}
        for f in data.get("items") or []:
            ten = str(f.get("field_name") or "")
            ra[ten] = {"id": f.get("field_id"), "type": f.get("type"),
                       "primary": bool(f.get("is_primary")),
                       "options": [str(o.get("name") or "")
                                   for o in ((f.get("property") or {}).get("options") or [])]}
        tok = data.get("page_token")
        if not data.get("has_more") or not tok:
            break
    return ra


def _kiem_cot(cot: dict, d: dict) -> tuple[str | None, str]:
    """(lỗi hoặc None, dấu cấu trúc). Thiếu cột / sai kiểu thì đóng — không đoán."""
    can = {**_KIEU, d["cot_ma"]: 1}
    if d["cot_ma"] not in cot:
        return (f"Base '{d['ten']}' chưa có cột '{d['cot_ma']}' (kiểu chữ) — cột này giúp "
                "Mark không ghi trùng khi chạy lại. Chủ Base cần thêm cột đó trước; Mark "
                "KHÔNG tự tạo cột."), ""
    sai = [f"{t} (cần kiểu {k}, đang là {cot[t]['type']})" if t in cot else f"{t} (không có)"
           for t, k in can.items() if t not in cot or cot[t]["type"] != k]
    if sai:
        return ("Base đổi cấu trúc, Mark dừng để không ghi sai cột: " + "; ".join(sai)), ""
    if not any(chuan(o) == chuan(_TT_MOI) for o in cot[COT_TT]["options"]):
        return f"Cột {COT_TT} không còn lựa chọn '{_TT_MOI}' — Mark không tự thêm lựa chọn.", ""
    dau = json.dumps({t: [cot[t]["id"], cot[t]["type"], sorted(cot[t]["options"])]
                      for t in sorted(can)}, ensure_ascii=False, sort_keys=True)
    return None, hashlib.sha256(dau.encode("utf-8")).hexdigest()


def _doc_dong(d: dict) -> list[dict]:
    """Mọi dòng của bảng, chỉ các cột Mark cần, kèm `last_modified_time`."""
    ten_cot = [COT_TEN, COT_NHOM, COT_PIC, COT_HAN, COT_TT, COT_KQ, d["cot_ma"]]
    ra, tok = [], None
    for _ in range(_TOI_DA_TRANG):
        kq = _goi("POST", _goc(d) + "/records/search",
                  query={"page_size": 500, "page_token": tok, "user_id_type": "open_id"},
                  body={"field_names": ten_cot, "automatic_fields": True})
        data = kq.get("data") or {}
        for it in data.get("items") or []:
            ra.append({"record_id": it.get("record_id"), "fields": it.get("fields") or {},
                       "last_modified_time": it.get("last_modified_time")})
        tok = data.get("page_token")
        if not data.get("has_more") or not tok:
            return ra
    raise RuntimeError(f"bảng quá {_TOI_DA_TRANG * 500} dòng — Mark không đọc hết để đối chiếu")


class _ChiMuc:
    """Chỉ mục dòng Base theo mã việc, record_id, (tên, nhóm); kèm người PIC đã có."""

    def __init__(self, dong: list[dict], cot_ma: str):
        self.cot_ma = cot_ma
        self.theo_id = {r["record_id"]: r for r in dong if r.get("record_id")}
        self.theo_ma: dict[str, dict] = {}
        self.theo_ten: dict[tuple, list[dict]] = collections.defaultdict(list)
        self.dem_nhom = collections.Counter()
        self.pic: dict[str, str] = {}
        for r in dong:
            f = r["fields"]
            ma = _chu(f.get(cot_ma)).strip()
            if ma:
                self.theo_ma.setdefault(ma, r)
            nhom = _chu(f.get(COT_NHOM))
            if nhom:
                self.dem_nhom[nhom] += 1
            self.theo_ten[(chuan(_chu(f.get(COT_TEN))), chuan(nhom))].append(r)
            for oid, ten in _nguoi(f.get(COT_PIC)):
                self.pic.setdefault(oid, ten)

    def giong_khong_ma(self, ten: str, nhom: str, ma: str) -> list[dict]:
        return [r for r in self.theo_ten.get((chuan(ten), chuan(nhom)), [])
                if _chu(r["fields"].get(self.cot_ma)).strip() != ma]


_chi_muc = _ChiMuc


def chon_lua_chon(gia_tri: str, lua_chon: list[str], dem: collections.Counter) -> str | None:
    """Tên lựa chọn CÓ SẴN khớp `gia_tri` (bỏ dấu/hoa thường/khoảng trắng cuối). Nhiều bản
    trùng (vd 'MEDIA' và 'MEDIA ') thì lấy bản các dòng đang dùng nhiều nhất; hoà thì bản
    không có khoảng trắng thừa. Không khớp → None (KHÔNG BAO GIỜ tạo lựa chọn mới)."""
    k = chuan(gia_tri)
    if not k:
        return None
    ung = [o for o in dict.fromkeys(lua_chon) if o.strip() and chuan(o) == k]
    if not ung:
        return None
    return max(ung, key=lambda o: (dem.get(o, 0), o == o.strip()))


def giai_pic(ten: str, open_id: str, ds_pic: dict[str, str], cau_hoi: str,
             bat: bool) -> tuple[str | None, str, str | None]:
    """(open_id hoặc None, chữ hiện, cảnh báo). Chỉ gán khi chắc ĐÚNG MỘT người (D5):
    open_id có nguyên văn trong tin nhắn đang xử lý (@nhắc), hoặc tên khớp đúng một người
    đã có trong cột PIC của Base. Còn lại để trống và báo."""
    ten, open_id = _gon(ten), str(open_id or "").strip()
    if not bat:
        return None, ten, ("không ghi PIC (đang tắt ghi PIC) — người dùng tự chọn trên Base"
                           if ten or open_id else None)
    if open_id:
        # Mã người phải vừa có nguyên văn trong tin nhắn vừa là người ĐÃ có trong cột PIC của
        # Base: chữ "ou_..." gõ tay không phải @nhắc thật (listener bỏ placeholder nhắc khỏi
        # chữ), nên không cho nó kéo một người ngoài Base vào làm PIC.
        if open_id.startswith("ou_") and open_id in (cau_hoi or "") and open_id in ds_pic:
            return open_id, ten or _ten_goc(ds_pic.get(open_id, "")) or open_id, None
        if not ten:
            return None, "", "mã người không có trong tin nhắn hoặc chưa có trong cột PIC — để trống PIC"
    if not ten:
        return None, "", None
    k = chuan(_ten_goc(ten))
    khop = sorted(oid for oid, n in ds_pic.items() if chuan(_ten_goc(n)) == k)
    if len(khop) == 1:
        return khop[0], _ten_goc(ds_pic[khop[0]]) or ten, None
    if khop:
        return None, ten, f"PIC '{ten}' khớp {len(khop)} người trên Base — để trống"
    return None, ten, f"PIC '{ten}' không khớp đúng một người đã có trong cột PIC — để trống"


# ───────────────────────────── ngữ cảnh lượt ─────────────────────────────
def _nguoi_hien_tai() -> str:
    return str(memory_store.get_current_sender() or "").strip()


def _chat_hien_tai() -> str:
    try:
        import scheduler
        return str(scheduler.get_current_chat() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _cau_hoi_hien_tai() -> str:
    """Tin nhắn đang xử lý (audit giữ) — để kiểm open_id PIC có thật được @nhắc không."""
    try:
        import audit
        tid = audit.turn_id_hien_tai()
        with audit._khoa_luot:
            return str((audit._dang_chay.get(tid) or {}).get("hoi") or "")
    except Exception:  # noqa: BLE001
        return ""


# ───────────────────────────── sổ bản xem trước ─────────────────────────────
_LOI_TRUONG = ("ma", "chat", "nguoi", "tao_luc", "het_han", "dich", "schema_hash", "rows")


def _bam(ban: dict) -> str:
    loi = {k: ban.get(k) for k in _LOI_TRUONG}
    return hashlib.sha256(json.dumps(loi, ensure_ascii=False, sort_keys=True)
                          .encode("utf-8")).hexdigest()


def _duong(ma: str):
    return _THU_MUC / f"{ma}.json"


def _luu(ban: dict) -> None:
    _THU_MUC.mkdir(parents=True, exist_ok=True)
    p = _duong(ban["ma"])
    tam = p.with_suffix(".tmp")
    tam.write_text(json.dumps(ban, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tam, p)


def _doc_ban(ma: str) -> dict | None:
    if not re.fullmatch(r"XV-[A-Z2-7]{6}", ma or ""):
        return None
    try:
        return json.loads(_duong(ma).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _moi_ban() -> list[dict]:
    ra = []
    for p in sorted(_THU_MUC.glob("XV-*.json")) if _THU_MUC.is_dir() else []:
        try:
            ra.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return ra


def _don_va_thay(chat: str, nguoi: str, gio: float) -> None:
    """Bản xem trước MỚI của cùng người, cùng chat thay bản cũ đang chờ duyệt — "ok" luôn
    trỏ vào bản người đó vừa thấy. Dọn file đã hết hạn quá 7 ngày."""
    for b in _moi_ban():
        try:
            if gio > float(b.get("het_han") or 0) + _GIU_FILE:
                _duong(b["ma"]).unlink(missing_ok=True)
            elif (b.get("trang_thai") == "cho_duyet" and b.get("chat") == chat
                  and b.get("nguoi") == nguoi):
                b["trang_thai"] = "bi_thay"
                _luu(b)
        except Exception:  # noqa: BLE001
            continue


def _ma_moi() -> str:
    while True:
        ma = "XV-" + "".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(6))
        if not _duong(ma).exists():
            return ma


# ───────────────────────────── tính từng dòng ─────────────────────────────
_NHAN = {"TAO": "TẠO", "CAP_NHAT": "CẬP NHẬT", "GIU_NGUYEN": "GIỮ NGUYÊN",
         "CAN_XEM": "CẦN XEM", "LOI": "LỖI"}


def _dong_da_co(dong: dict, r: dict, v: dict, d: dict) -> None:
    """Việc đã có trên Base: chỉ ĐIỀN Ô TRỐNG. Ô đã có giá trị khác thì giữ và báo."""
    f = r["fields"]
    thay, truoc = {}, {}
    muon = [(d["cot_ma"], dong["ma_viec"], dong["ma_viec"]),
            (COT_TEN, v["ten"], v["ten"]), (COT_NHOM, v["nhom"], v["nhom"]),
            (COT_KQ, v["kq"], v["kq"]),
            (COT_HAN, v["han_ms"], v["han_hien"]),
            (COT_PIC, [{"id": v["pic_id"]}] if v["pic_id"] else None, v["pic_hien"])]
    doi = []
    for cot, gia_tri, hien in muon:
        if not gia_tri:
            continue
        cu = f.get(cot)
        if _trong(cu):
            thay[cot], truoc[cot] = gia_tri, None
            if cot != d["cot_ma"]:
                doi.append(f"{cot}: trống → {hien}")
        elif cot in (COT_KQ, COT_HAN, COT_PIC):
            giong = (cu == gia_tri if cot == COT_HAN
                     else {x[0] for x in _nguoi(cu)} == {v["pic_id"]} if cot == COT_PIC
                     else chuan(_chu(cu)) == chuan(gia_tri))
            if not giong:
                dong["canh_bao"].append(f"{cot} trên Base đã có giá trị khác — giữ nguyên "
                                        "(Mark chỉ điền ô trống)")
    dong["record_id"] = r["record_id"]
    dong["moc_sua"] = r.get("last_modified_time")
    dong["ghi"], dong["truoc"] = thay, truoc
    dong["hanh_dong"] = "CAP_NHAT" if thay else "GIU_NGUYEN"
    dong["mo_ta"] = ("; ".join(doi) if doi else
                     ("gắn mã việc vào dòng có sẵn" if thay else "đã có trên Base, không đổi gì"))


def _tinh_dong(stt: int, vao: dict, cm: _ChiMuc, cot: dict, d: dict, cau_hoi: str,
               da_thay: dict[str, int]) -> dict:
    dong = {"stt": stt, "hanh_dong": "LOI", "ma_viec": "", "record_id": None, "ghi": {},
            "truoc": {}, "moc_sua": None, "canh_bao": [], "mo_ta": "", "hien": {}}
    vao = vao if isinstance(vao, dict) else {}
    ten = _gon(vao.get("hang_muc"))
    dong["hien"][COT_TEN] = ten
    if not ten:
        dong["mo_ta"] = f"thiếu {COT_TEN}"
        return dong
    nhom_vao = _gon(vao.get("nhom"))
    nhom = chon_lua_chon(nhom_vao, cot[COT_NHOM]["options"], cm.dem_nhom)
    dong["hien"][COT_NHOM] = nhom or nhom_vao
    if not nhom:
        dong["mo_ta"] = (f"NHÓM '{nhom_vao}' không có trong lựa chọn của Base — Mark không tự "
                         "thêm lựa chọn; chọn đúng một NHÓM có sẵn" if nhom_vao
                         else "thiếu NHÓM")
        return dong
    han_ms, loi_han, han_hien = _ngay_ms(vao.get("deadline"))
    if loi_han:
        dong["mo_ta"] = loi_han
        return dong
    if han_hien and vao.get("deadline_gia_dinh_nam"):
        han_hien += "*"
    pic_id, pic_hien, cb = giai_pic(vao.get("pic"), vao.get("pic_open_id"), cm.pic, cau_hoi,
                                    _ghi_pic_bat())
    if cb:
        dong["canh_bao"].append(cb)
    v = {"ten": ten, "nhom": nhom, "kq": _gon(vao.get("ket_qua")), "han_ms": han_ms,
         "han_hien": han_hien, "pic_id": pic_id, "pic_hien": pic_hien}
    dong["hien"].update({COT_PIC: pic_hien if pic_id else
                         (f"chưa rõ ({pic_hien})" if pic_hien else "trống"),
                         COT_HAN: han_hien or "trống", COT_TT: "", COT_KQ: v["kq"]})
    ma = ma_viec(d["chien_dich"], nhom, ten)
    dong["ma_viec"] = ma
    if ma in da_thay:
        dong["hanh_dong"] = "CAN_XEM"
        dong["mo_ta"] = f"trùng việc dòng {da_thay[ma]} trong cùng danh sách — không ghi lần hai"
        return dong
    da_thay[ma] = stt
    rid = str(vao.get("record_id") or "").strip()
    if rid:
        r = cm.theo_id.get(rid)
        if not r:
            dong["mo_ta"] = f"record_id {rid} không có trong bảng"
            return dong
        ma_cu = _chu(r["fields"].get(d["cot_ma"])).strip()
        if ma_cu and ma_cu != ma:
            dong["hanh_dong"] = "CAN_XEM"
            dong["mo_ta"] = f"dòng {rid} đã gắn mã việc khác ({ma_cu}) — không ghi"
            return dong
        _dong_da_co(dong, r, v, d)
        return dong
    if ma in cm.theo_ma:
        _dong_da_co(dong, cm.theo_ma[ma], v, d)
        return dong
    giong = cm.giong_khong_ma(ten, nhom, ma)
    if giong:
        dong["hanh_dong"] = "CAN_XEM"
        dong["mo_ta"] = ("Base đã có việc giống (do người tạo, " +
                         ", ".join(r["record_id"] for r in giong[:3]) +
                         ") — không ghi; đúng là việc đó thì xem trước lại kèm record_id")
        return dong
    tt = next(o for o in dict.fromkeys(cot[COT_TT]["options"]) if chuan(o) == chuan(_TT_MOI))
    ghi = {COT_TEN: ten, COT_NHOM: nhom, COT_TT: tt, d["cot_ma"]: ma}
    if v["kq"]:
        ghi[COT_KQ] = v["kq"]
    if han_ms:
        ghi[COT_HAN] = han_ms
    if pic_id:
        ghi[COT_PIC] = [{"id": pic_id}]
    dong["hien"][COT_TT] = tt.strip()
    dong.update(hanh_dong="TAO", ghi=ghi, mo_ta="")
    return dong


def _cau_xem_truoc(ban: dict, dong: list[dict], dem: dict) -> str:
    het = datetime.datetime.fromtimestamp(ban["het_han"], _VN)
    L = [f"XEM TRƯỚC (mã {ban['ma']}, hết hạn {het:%H:%M %d/%m}) — Base {ban['dich']['ten']}",
         f"Tạo mới {dem['tao']} · Cập nhật {dem['cap_nhat']} · Giữ nguyên {dem['giu_nguyen']}"
         f" · Cần bạn xem {dem['can_xem']} · Lỗi {dem['loi']}"]
    for x in dong:
        h = x["hien"]
        if x["hanh_dong"] == "TAO":
            dau = (f"{x['stt']}) TẠO — {h[COT_TEN]} — {h[COT_NHOM].strip()} — PIC: {h[COT_PIC]}"
                   f" — {h[COT_HAN]} — {h[COT_TT]}" + (f" — {h[COT_KQ]}" if h.get(COT_KQ) else ""))
        else:
            dau = f"{x['stt']}) {_NHAN[x['hanh_dong']]} — {h.get(COT_TEN) or '(trống)'} — {x['mo_ta']}"
            if x["hanh_dong"] in ("CAN_XEM", "LOI"):
                dau += " — không ghi"
        if x["canh_bao"]:
            dau += " (lưu ý: " + "; ".join(x["canh_bao"]) + ")"
        L.append(dau)
    if any(str(x["hien"].get(COT_HAN, "")).endswith("*") for x in dong):
        L.append("Ngày có * là Mark giả định năm hiện tại.")
    L.append("Mark chỉ ghi vào Base, không gửi tin, không tag hay nhắc ai.")
    return "\n".join(L)


# ───────────────────────────── tool 1: xem trước ─────────────────────────────
SCHEMA_XEM = {
    "name": "xem_truoc_viec_base",
    "description": (
        "BƯỚC 1/2 khi được nhờ 'tạo task', 'giao việc', 'đưa lên checklist/Base' sau khi đã "
        "tách việc: tính sẵn bản xem trước các việc sẽ ghi vào Base checklist của team (Base "
        "do cấu hình máy chạy chọn — không chọn được Base khác). KHÔNG ghi gì lên Lark.\n"
        "Truyền đúng các việc đã tách: giữ nguyên chữ ghi chép; `nhom` theo bộ phận; `pic` "
        "là tên người đúng như ghi chép (không đoán, chỉ có bộ phận thì để trống); "
        "`pic_open_id` CHỈ khi tin nhắn có @nhắc người đó; `deadline` yyyy-mm-dd, năm do Mark "
        "giả định thì `deadline_gia_dinh_nam`=true. Tối đa 50 việc.\n"
        "KHI TRẢ LỜI: chép NGUYÊN `cau_xem_truoc`, nói mã xem trước, nêu việc CẦN XEM / LỖI / "
        "PIC chưa rõ, rồi KẾT THÚC bằng \"Ghi vào Base nhé?\" và DỪNG. Chỉ gọi "
        "`ghi_viec_base` khi CHÍNH người này đồng ý ở tin nhắn SAU. Muốn sửa dòng nào thì "
        "gọi lại tool này (bản mới thay bản cũ)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "viec": {
                "type": "array", "maxItems": _TOI_DA_DONG,
                "items": {
                    "type": "object",
                    "properties": {
                        "hang_muc": {"type": "string", "description": "HẠNG MỤC CV, nguyên văn."},
                        "nhom": {"type": "string",
                                 "description": "NHÓM/bộ phận (Booking, Media, Content…)."},
                        "pic": {"type": "string", "description": "Tên PIC như ghi chép."},
                        "pic_open_id": {"type": "string",
                                        "description": "ou_… của người được @nhắc trong tin."},
                        "deadline": {"type": "string", "description": "yyyy-mm-dd hoặc trống."},
                        "deadline_gia_dinh_nam": {"type": "boolean"},
                        "ket_qua": {"type": "string", "description": "KẾT QUẢ CẦN ĐẠT."},
                        "record_id": {"type": "string",
                                      "description": "Chỉ khi người dùng nói đúng dòng có sẵn "
                                                     "trên Base là việc này (rec…)."},
                    },
                    "required": ["hang_muc", "nhom"],
                },
            },
        },
        "required": ["viec"],
    },
}


def _xem_truoc(args: dict, **_kw) -> str:
    if not _bat():
        return tool_error(_CAU_TAT)
    nguoi, chat = _nguoi_hien_tai(), _chat_hien_tai()
    if not nguoi or not chat:
        return tool_error("Không xác định được người nhờ hoặc cuộc chat — Mark không lập bản "
                          "xem trước ghi Base khi không biết ai sẽ duyệt.")
    viec = (args or {}).get("viec")
    if not isinstance(viec, list) or not viec:
        return tool_error("Thiếu `viec` — danh sách việc đã tách.")
    if len(viec) > _TOI_DA_DONG:
        return tool_error(f"{len(viec)} việc — mỗi bản xem trước tối đa {_TOI_DA_DONG} việc. "
                          "Chia thành nhiều lần.")
    try:
        d = cau_hinh()
    except ValueError as e:
        return tool_error(f"Cấu hình Base đích hỏng: {e}")
    try:
        cot = _doc_cot(d)
        loi, dau = _kiem_cot(cot, d)
        if loi:
            return tool_error(loi)
        cm = _chi_muc(_doc_dong(d), d["cot_ma"])
    except Exception as e:  # noqa: BLE001
        return tool_error(f"Mark chưa đọc được Base '{d['ten']}' ({str(e)[:200]}). Thường là "
                          "bot chưa được chia sẻ Base này.")
    cau_hoi = _cau_hoi_hien_tai()
    da_thay: dict[str, int] = {}
    dong = [_tinh_dong(i, v, cm, cot, d, cau_hoi, da_thay) for i, v in enumerate(viec, 1)]
    dem = {k: sum(1 for x in dong if x["hanh_dong"] == h)
           for k, h in (("tao", "TAO"), ("cap_nhat", "CAP_NHAT"), ("giu_nguyen", "GIU_NGUYEN"),
                        ("can_xem", "CAN_XEM"), ("loi", "LOI"))}
    pic_chua_ro = [f"{x['hien'].get(COT_PIC)} (dòng {x['stt']})" for x in dong
                   if any("PIC" in c or "mã người" in c for c in x["canh_bao"])] or None
    gio = time.time()
    with _KHOA:
        ban = {"ma": _ma_moi(), "chat": chat, "nguoi": nguoi, "tao_luc": gio,
               "het_han": gio + _HAN_XEM_TRUOC, "dich": d, "schema_hash": dau, "rows": dong}
        cau = _cau_xem_truoc(ban, dong, dem)
        if not (dem["tao"] or dem["cap_nhat"]):
            return tool_result(
                success=True, ma_xem_truoc=None, khong_co_gi_de_ghi=True, dem=dem,
                bang_url=d["url"], cau_xem_truoc=cau.replace(f"mã {ban['ma']}, ", "", 1),
                huong_dan="Không có việc nào cần ghi: chép `cau_xem_truoc`, KHÔNG hỏi ghi Base.")
        _don_va_thay(chat, nguoi, gio)      # chỉ khi có bản mới thật để thay
        ban.update(bam=_bam(ban), trang_thai="cho_duyet", lan_ghi=[])
        _luu(ban)
    return tool_result(
        success=True, ma_xem_truoc=ban["ma"],
        het_han=f"{datetime.datetime.fromtimestamp(ban['het_han'], _VN):%Y-%m-%d %H:%M}",
        bang_url=d["url"], dem=dem,
        dong=[{"stt": x["stt"], "hanh_dong": x["hanh_dong"], "ma_viec": x["ma_viec"],
               "sau": x["hien"], "ghi_chu": x["mo_ta"] or None,
               "canh_bao": x["canh_bao"] or None} for x in dong],
        pic_chua_ro=pic_chua_ro, cau_xem_truoc=cau,
        huong_dan=("Chép NGUYÊN `cau_xem_truoc`, nói mã xem trước, rồi KẾT THÚC bằng \"Ghi "
                   "vào Base nhé?\" và DỪNG. Chỉ gọi `ghi_viec_base` khi CHÍNH người này đồng "
                   "ý ở tin nhắn sau."))


# ───────────────────────────── tool 2: ghi ─────────────────────────────
SCHEMA_GHI = {
    "name": "ghi_viec_base",
    "description": (
        "BƯỚC 2/2: ghi vào Base checklist ĐÚNG những việc trong một bản xem trước đã có "
        "(`xem_truoc_viec_base`). Chỉ gọi khi CHÍNH người nhờ vừa đồng ý bản xem trước đó "
        "(ok, ghi đi…) ở tin nhắn SAU câu \"Ghi vào Base nhé?\". Người khác trong nhóm nói "
        "ok thì KHÔNG gọi — code cũng từ chối. Muốn đổi nội dung việc → xem trước lại; bỏ bớt "
        "dòng → `bo_dong`. Chạy lại cùng mã không tạo trùng.\n"
        "Không gửi tin, không tag, không tạo Lark Task, không đổi TRẠNG THÁI, không xoá.\n"
        "KHI TRẢ LỜI: chép `cau_ket_qua` (số do code đếm) kèm `bang_url`; nêu dòng `bo_qua` "
        "và lý do."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ma_xem_truoc": {"type": "string",
                             "description": "Mã XV-… của bản xem trước người dùng vừa đồng ý."},
            "bo_dong": {"type": "array", "items": {"type": "integer"},
                        "description": "Số thứ tự dòng người dùng muốn BỎ ra (không ghi)."},
        },
    },
}


def _tim_ban(ma: str, chat: str, nguoi: str, gio: float) -> tuple[dict | None, str]:
    ma = str(ma or "").strip().upper()
    if ma:
        ban = _doc_ban(ma)
        return (ban, "") if ban else (None, f"Không thấy bản xem trước {ma}.")
    cho = [b for b in _moi_ban() if b.get("trang_thai") == "cho_duyet" and b.get("chat") == chat
           and b.get("nguoi") == nguoi and float(b.get("het_han") or 0) > gio]
    if len(cho) == 1:
        return cho[0], ""
    return None, ("Không có bản xem trước nào đang chờ bạn duyệt trong cuộc chat này."
                  if not cho else "Có nhiều bản xem trước đang chờ — nói rõ mã XV-….")


def _tao(d: dict, ma: str, lo: list[dict], ket: dict) -> None:
    """Tạo một lô (≤50). Lô hỏng hẳn thì đọc lại Base rồi tạo TỪNG dòng còn thiếu — lô có
    thể đã vào Base dù phản hồi lỗi, tạo lại cả lô là trùng."""
    khoa = [x["ma_viec"] for x in lo]
    try:
        kq = _goi_ghi(_goc(d) + "/records/batch_create",
                      {"user_id_type": "open_id", "client_token": _client_token(ma, khoa)},
                      {"records": [{"fields": x["ghi"]} for x in lo]})
        recs = ((kq.get("data") or {}).get("records") or [])
        for i, x in enumerate(lo):
            r = next((r for r in recs
                      if _chu((r.get("fields") or {}).get(d["cot_ma"])).strip() == x["ma_viec"]),
                     recs[i] if i < len(recs) else {})
            ket["da_tao"].append({"stt": x["stt"], "ma_viec": x["ma_viec"],
                                  "record_id": r.get("record_id"),
                                  "link": f"{d['url']}&record={r.get('record_id')}"
                                  if r.get("record_id") else d["url"]})
        return
    except PermissionError:
        raise
    except Exception as e:  # noqa: BLE001
        if len(lo) == 1:
            ket["loi"].append({"stt": lo[0]["stt"], "ly_do": str(e)[:200]})
            return
    co = _chi_muc(_doc_dong(d), d["cot_ma"]).theo_ma
    for x in lo:
        if x["ma_viec"] in co:
            r = co[x["ma_viec"]]
            ket["da_tao"].append({"stt": x["stt"], "ma_viec": x["ma_viec"],
                                  "record_id": r["record_id"],
                                  "link": f"{d['url']}&record={r['record_id']}"})
        else:
            _tao(d, ma, [x], ket)


def _ghi(args: dict, **_kw) -> str:
    if not _bat():
        return tool_error(_CAU_TAT)
    nguoi, chat = _nguoi_hien_tai(), _chat_hien_tai()
    if not nguoi or not chat:
        return tool_error("Không xác định được người duyệt hoặc cuộc chat — không ghi.")
    gio = time.time()
    ban, loi = _tim_ban((args or {}).get("ma_xem_truoc"), chat, nguoi, gio)
    if not ban:
        return tool_error(loi + " Gọi xem trước lại rồi hỏi người dùng.")
    if ban.get("bam") != _bam(ban):
        return tool_error(f"Bản xem trước {ban.get('ma')} không còn nguyên vẹn — không ghi. "
                          "Xem trước lại.")
    if ban.get("chat") != chat or ban.get("nguoi") != nguoi:
        return tool_error("Chỉ CHÍNH người nhờ xem trước, trong đúng cuộc chat đó, mới duyệt "
                          "ghi được. Nhờ người đó trả lời đồng ý, hoặc tự xem trước lại.")
    if ban.get("trang_thai") == "bi_thay":
        return tool_error(f"Bản {ban['ma']} đã bị bản xem trước mới hơn thay — dùng mã mới nhất.")
    if gio > float(ban.get("het_han") or 0):
        return tool_error(f"Bản {ban['ma']} đã hết hạn (24 giờ). Xem trước lại.")
    try:
        d = cau_hinh()
    except ValueError as e:
        return tool_error(f"Cấu hình Base đích hỏng: {e}")
    if _khoa_dich(d) != _khoa_dich(ban["dich"]):
        return tool_error("Base đích trong cấu hình đã đổi so với lúc xem trước — không ghi. "
                          "Xem trước lại.")
    bo = (args or {}).get("bo_dong") or []
    stt_co = {x["stt"] for x in ban["rows"]}
    try:
        bo = {int(x) for x in bo}
    except (TypeError, ValueError):
        return tool_error("`bo_dong` phải là danh sách số thứ tự dòng.")
    if bo - stt_co:
        return tool_error(f"Bản xem trước không có dòng {sorted(bo - stt_co)}.")
    ghi_pic = _ghi_pic_bat()
    ket = {"da_tao": [], "da_cap_nhat": [], "da_co_san": [], "bo_qua": [], "loi": []}
    with _KHOA:
        try:
            cot = _doc_cot(d)
            loi_cot, dau = _kiem_cot(cot, d)
            if loi_cot:
                return tool_error(loi_cot)
            if dau != ban["schema_hash"]:
                return tool_error("Cột của Base đã đổi từ lúc xem trước (thêm/sửa lựa chọn hoặc "
                                  "cột) — không ghi. Xem trước lại.")
            cm = _chi_muc(_doc_dong(d), d["cot_ma"])
        except Exception as e:  # noqa: BLE001
            return tool_error(f"Mark chưa đọc được Base '{d['ten']}' ({str(e)[:200]}).")
        tao, sua = [], []
        for x in ban["rows"]:
            if x["hanh_dong"] not in ("TAO", "CAP_NHAT"):
                continue
            if x["stt"] in bo:
                ket["bo_qua"].append({"stt": x["stt"], "ly_do": "người dùng bỏ dòng này"})
                continue
            payload = {k: v for k, v in x["ghi"].items() if ghi_pic or k != COT_PIC}
            if x["hanh_dong"] == "TAO":
                r = cm.theo_ma.get(x["ma_viec"])
                if r:          # chạy lại / lần trước đã vào Base → không tạo lần hai
                    ket["da_co_san"].append({"stt": x["stt"], "ma_viec": x["ma_viec"],
                                             "record_id": r["record_id"]})
                elif cm.giong_khong_ma(x["ghi"][COT_TEN], x["ghi"][COT_NHOM], x["ma_viec"]):
                    ket["bo_qua"].append({"stt": x["stt"], "ly_do": "Base vừa có việc giống do "
                                          "người tạo sau lúc xem trước — xem trước lại"})
                else:
                    tao.append({**x, "ghi": payload})
                continue
            r = cm.theo_id.get(x["record_id"])
            if not r:
                ket["loi"].append({"stt": x["stt"], "ly_do": "dòng không còn trên Base"})
            elif r.get("last_modified_time") != x["moc_sua"]:
                ket["bo_qua"].append({"stt": x["stt"], "ly_do": "đã có người sửa dòng này sau "
                                      "lúc xem trước — xem trước lại"})
            else:
                con = {k: v for k, v in payload.items() if _trong(r["fields"].get(k))}
                if con:
                    sua.append({**x, "ghi": con})
                else:
                    ket["da_co_san"].append({"stt": x["stt"], "ma_viec": x["ma_viec"],
                                             "record_id": r["record_id"]})
        for i in range(0, len(tao), 50):
            _tao(d, ban["ma"], tao[i:i + 50], ket)
        for i in range(0, len(sua), 50):
            lo = sua[i:i + 50]
            try:
                _goi_ghi(_goc(d) + "/records/batch_update", {"user_id_type": "open_id"},
                         {"records": [{"record_id": x["record_id"], "fields": x["ghi"]}
                                      for x in lo]})
                ket["da_cap_nhat"] += [{"stt": x["stt"], "ma_viec": x["ma_viec"],
                                        "record_id": x["record_id"],
                                        "link": f"{d['url']}&record={x['record_id']}"}
                                       for x in lo]
            except PermissionError:
                raise
            except Exception as e:  # noqa: BLE001
                ket["loi"] += [{"stt": x["stt"], "ly_do": str(e)[:200]} for x in lo]
        ban["lan_ghi"] = list(ban.get("lan_ghi") or []) + [
            {"luc": time.time(), "nguoi": nguoi, **{k: v for k, v in ket.items()}}]
        ban["trang_thai"] = "ghi_mot_phan" if ket["loi"] else "da_ghi"
        _luu(ban)
    cau = (f"Đã ghi vào Base {d['ten']}: tạo mới {len(ket['da_tao'])} việc, cập nhật "
           f"{len(ket['da_cap_nhat'])}, đã có sẵn {len(ket['da_co_san'])}, bỏ qua "
           f"{len(ket['bo_qua'])}" + (f", lỗi {len(ket['loi'])}" if ket["loi"] else "")
           + f". Link: {d['url']}")
    return tool_result(success=not ket["loi"], ma_xem_truoc=ban["ma"], bang_url=d["url"],
                       **{k: (v or None) for k, v in ket.items()}, cau_ket_qua=cau)


def register() -> None:
    for ten, schema, handler, mo_ta in (
            ("xem_truoc_viec_base", SCHEMA_XEM, _xem_truoc,
             "Xem trước danh sách việc sẽ ghi vào Base checklist (không ghi Lark)"),
            ("ghi_viec_base", SCHEMA_GHI, _ghi,
             "Ghi các việc của một bản xem trước ĐÃ DUYỆT vào Base checklist")):
        try:
            registry.register(
                name=ten, toolset="lark_api", schema=schema, handler=handler,
                check_fn=_bat, requires_env=[], is_async=False, description=mo_ta,
                emoji="\U0001f4cb", override=True,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[viec_base_tool] register warning: {e}")


register()
