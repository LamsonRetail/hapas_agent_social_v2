"""Tool `dem_bang` — ĐẾM, tính % và CỘNG trên một Base/Sheet của Lark bằng CODE.

VÌ SAO CÓ
Mark không có máy tính. Tháng 10/2026, đếm tab khảo sát 52 dòng ("Khách store HAPAS")
bằng model ra số sai ba lượt liền — lệch vài đơn vị mà câu trả lời vẫn nghe chắc chắn.
Cách chữa tạm là cấm Mark đếm bảng trên 20 dòng và đưa công thức COUNTIF cho team tự
đếm: đúng, nhưng team hỏi số thì nhận về bài tập. Chủ agent duyệt cách chữa tận gốc,
cùng nguyên tắc với `chi_so_bai_tool.py`: CODE đếm/cộng, model chỉ CHÉP NGUYÊN câu số
(`cau_so`) — y như `cau_tong` của chi_so_bai.

ĐẾM THẾ NÀO (mọi luật là luật CỨNG trong code, không đoán theo nghĩa)
- Dòng tiêu đề: mặc định TỰ NHẬN trong 5 dòng đầu (xem `_tu_nhan_tieu_de`), luôn báo dòng
  đã dùng và chữ tiêu đề để model gọi lại với `dong_tieu_de` nếu sai.
- Dòng dữ liệu = dòng sau tiêu đề có ít nhất một ô ngoài cột STT; dòng lặp lại tiêu đề
  (tab lịch nội dung lặp "STT | Ngày đăng…" mỗi phase) bị bỏ và báo. n = số dòng đó.
- Ô nhiều lựa chọn: các lựa chọn là các DÒNG trong ô (Base chọn nhiều thì đã tách sẵn).
  KHÔNG tách theo dấu phẩy, trừ khi `tach_dau_phay` — vì "Có, đã mua/sẽ mua ngay hôm nay"
  là MỘT đáp án.
- Gộp cách viết: bỏ khoảng trắng thừa, không phân biệt hoa thường và dấu câu cuối; KHÔNG
  bỏ dấu tiếng Việt ("bán" ≠ "ban"). Gộp theo nghĩa thì người gọi khai trong `gop`.
- Một người chọn một đáp án hai lần trong cùng ô vẫn tính MỘT.
- Cột trả lời mở (> 40 đáp án khác nhau, đáp án dài trung bình > 60 ký tự, hoặc gần như
  mỗi người một kiểu — xem `la_cau_mo`) không đếm theo đáp án — mã hoá câu mở là việc
  ĐỌC, của model, qua `doc_bang`.
- Cột tên/SĐT/email/Zalo (theo tiêu đề, loại cột Base, hoặc ô có dạng SĐT/email) không
  bao giờ trả giá trị — chỉ báo là đã bỏ qua.

Quyền đọc đi CHUNG MỘT CỬA với `doc_bang` (`bang_tool.mo_nguon`): không có luật quyền
thứ hai. Đi qua `ToolRegistry.dispatch` nên chịu `lsr_policy` (công tắc lùi về
`doc_bang`) và tự ghi audit như mọi tool.

DỮ LIỆU DÁN TRONG CHAT (`du_lieu`, 07/10/2026)
Chủ agent: "sửa những phần bị limit 20 dòng luôn" — ghi chép khảo sát, bảng báo giá, danh
sách số mà người dùng DÁN vào chat trước đây vẫn để model tự đếm/cộng ("số tự cộng, kiểm lại
trên Sheet"). Nay cùng một đường đếm: `doc_du_lieu_dan` biến chữ dán thành lưới y như
`doc_tho` trả, rồi chạy đúng `dem()`. Không kiểm quyền Lark (dữ liệu đã nằm trong chat, không
đọc gì thêm), không gọi mạng. Luật đọc chữ dán (CỐ ĐỊNH, báo lại trong `dinh_dang`):
- có ký tự tab → TSV (kiểu chép từ Sheet/Excel; ô có ngoặc kép giữ xuống dòng trong ô);
- đa số dòng bắt đầu bằng "|" → bảng markdown (bỏ dòng |---|, "<br>" là xuống dòng trong ô);
- đa số dòng có "|" → cột cách nhau bằng "|";
- CSV dấu ";" rồi dấu "," (có ngoặc kép): chỉ khi ≥ 80% dòng cùng số cột > 1 VÀ dòng đầu
  cũng đúng số cột đó — "1,5" một mình là số thập phân, không phải hai cột;
- đa số dòng dạng "nhãn: số" → hai cột (A nhãn, B số), không dòng tiêu đề;
- còn lại: mỗi dòng một ô (bỏ gạch đầu dòng "- ", "1) "); dòng đầu là tiêu đề chỉ khi nó
  là chữ mà phần còn lại là số, hoặc nó kết thúc bằng ":"/"?".
Ô nhiều lựa chọn trong chữ dán: xuống dòng trong ô (ngoặc kép, "<br>") như Sheet; thêm dấu
";" — CHỈ khi cột không dùng ";" làm dấu cột và ≥ 2 ô của cột có ";" (kiểu xuất Microsoft
Forms). Dấu phẩy vẫn KHÔNG tách (trừ `tach_dau_phay`).
Không thấy dòng chữ nào ra dáng tiêu đề trong 5 dòng đầu → coi như KHÔNG có dòng tiêu đề
(cột gọi bằng chữ cái) thay vì nuốt dòng số đầu làm tiêu đề như với Sheet.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import bang_tool as BT
import lark_bang as B

from tools.registry import registry, tool_error, tool_result  # type: ignore

#: Giá trị liệt kê tối đa mỗi cột (mỗi nhóm) — phần còn lại gộp "và N lựa chọn khác".
TOP_GIA_TRI = 25
#: Ngưỡng coi là cột trả lời MỞ: quá nhiều đáp án khác nhau, hoặc đáp án quá dài.
CAU_MO_SO_GIA_TRI = 40
CAU_MO_DO_DAI = 60
#: Trần cỡ kết quả gửi lại model. Vượt thì thu TOP_GIA_TRI xuống 10, rồi 5.
MAX_KY_TU_RA = 60_000
#: Nhóm dưới ngưỡng này: số chỉ để tham khảo (skill nghiên cứu khách hàng dùng cùng mốc).
NHOM_NHO = 10
#: Trần dữ liệu dán: chữ quá dài thì model đã cắt/chép sai trước khi tới đây — bảng cỡ đó
#: phải nằm trên Sheet (đọc thẳng bằng `nguon`), không đi qua chat.
MAX_KY_TU_DAN = 200_000
MAX_DONG_DAN = 5_000
TEN_NGUON_DAN = "dữ liệu dán trong chat"

HUONG_DAN = (
    "Chép NGUYÊN các số trong `cau_so` — số do CODE đếm trên toàn bộ dòng. KHÔNG tự đếm "
    "lại, KHÔNG làm tròn khác, KHÔNG cộng % các đáp án của câu chọn nhiều (tổng có thể "
    ">100%). Muốn gộp hai cách viết cùng ý thì gọi lại với `gop`, đừng tự cộng hai số. "
    "Nói rõ n từng tab và dòng tiêu đề đã dùng. Cột trả lời mở không có số: mã hoá ý là "
    "nhận định của Mark khi ĐỌC (doc_bang) — nói rõ là đọc, kèm trích dẫn, không gắn %."
)

SCHEMA = {
    "name": "dem_bang",
    "description": (
        "ĐẾM, tính %, so nhóm và CỘNG TỔNG trên một Base/Sheet của Lark bằng CODE — số "
        "chính xác trên MỌI dòng, không phải model tự đếm. Dùng cho mọi câu hỏi về SỐ trên "
        "bảng: bao nhiêu người chọn X, tỷ lệ %, tần suất từng đáp án, so đã mua/chưa mua, "
        "tỷ trọng pillar, tổng chi phí một cột, có dòng trùng không. Đọc NỘI DUNG (câu trả "
        "lời mở, rà từng dòng) thì dùng `doc_bang`.\n"
        "Nguồn và quyền y như `doc_bang` (link /sheets/, /base/, /wiki/, `sheet:…`, "
        "`base:…`); người hỏi phải có quyền xem.\n"
        "Người dùng DÁN bảng/danh sách vào chat (ghi chép khảo sát, báo giá, danh sách số): "
        "đưa NGUYÊN VĂN phần dán vào `du_lieu`, bỏ trống `nguon` — nhận bảng tab (chép từ "
        "Sheet), bảng markdown, CSV, cột '|', dòng 'nhãn: số' (cột A nhãn, cột B số), hoặc "
        "mỗi dòng một giá trị (cột A). Không có dòng tiêu đề thì gọi cột bằng chữ cái.\n"
        "Cột chọn bằng chữ cái ('H'), mã câu ('B5', 'C2.') hoặc một đoạn tiêu đề; bỏ trống "
        "`cot` = đếm mọi cột. Ô nhiều lựa chọn = nhiều DÒNG trong ô; không tách dấu phẩy "
        "trừ khi `tach_dau_phay`.\n"
        "KHI TRẢ LỜI: chép NGUYÊN `cau_so` (số do code đếm — KHÔNG tự đếm lại, KHÔNG làm "
        "tròn khác); nói dòng tiêu đề đã dùng (`dong_tieu_de_da_dung`) và n; tiêu đề nhận "
        "sai thì gọi lại với `dong_tieu_de`. Bảng nhiều tầng (dòng nhóm = tổng các dòng "
        "con, có dòng TỔNG): cộng cả cột là cộng trùng — dùng `dong` để cộng đúng các dòng "
        "con của một nhóm. Bị từ chối vì quyền thì chuyển NGUYÊN lời hướng dẫn."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "nguon": {"type": "string",
                      "description": "Link Base/Sheet/Wiki, hoặc `sheet:<mã>` / `base:<mã>` "
                                     "từ thẻ mục lục. Bỏ trống khi dùng `du_lieu`."},
            "du_lieu": {"type": "string",
                        "description": "Bảng/danh sách người dùng DÁN trong chat, chép "
                                       "NGUYÊN VĂN (không tự sửa, không bỏ dòng). Có thì "
                                       "không cần `nguon`, không kiểm quyền Lark."},
            "tab": {"type": "string",
                    "description": "Tên hoặc mã tab/bảng khi link trỏ cả file. Bỏ trống = "
                                   "mọi tab (hoặc đúng tab trong link ?sheet=/?table=)."},
            "cot": {"type": "array", "items": {"type": "string"},
                    "description": "Cột cần đếm: chữ cái ('H'), mã câu ('B5'), hoặc đoạn "
                                   "tiêu đề ('Pillar'). Bỏ trống = mọi cột."},
            "nhom_theo": {"type": "string",
                          "description": "Một cột để so nhóm (vd 'C2' đã mua/chưa mua): mỗi "
                                         "cột đếm được tách số theo từng nhóm."},
            "cong": {"type": "array", "items": {"type": "string"},
                     "description": "Cột cần CỘNG TỔNG (số kiểu VN '1.100.000đ', '1,5', "
                                    "'3 triệu'). Ô không phải số được báo, không đoán; ô '%' "
                                    "không cộng vào tổng (báo riêng)."},
            "dong": {"type": "string",
                     "description": "Chỉ xét các dòng này (số dòng thật trên Sheet), vd "
                                    "'6-7' hay '9-11, 13'. Dùng để cộng dòng con của một nhóm."},
            "dong_tieu_de": {"type": "integer",
                             "description": "Dòng tiêu đề (đếm từ 1). Bỏ trống = tự nhận; "
                                            "0 = bảng không có dòng tiêu đề."},
            "tach_dau_phay": {"type": "boolean",
                              "description": "true = tách lựa chọn theo cả dấu phẩy/chấm "
                                             "phẩy. Mặc định false."},
            "gop": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                    "description": "Gộp các cách viết cùng ý thành một đáp án, mỗi nhóm một "
                                   "mảng, tên đầu là tên giữ lại. Một người chọn nhiều cách "
                                   "viết vẫn tính một."},
        },
        "required": [],
    },
}


# ───────────────────────────── chữ ─────────────────────────────
def _gon(s: str) -> str:
    """Chuẩn Unicode + gộp khoảng trắng (giữ nguyên hoa thường, dấu), bỏ ký tự điều khiển
    và ký tự định dạng vô hình (Cc/Cf: ESC, đảo chiều chữ U+202E, zero-width…).

    Mọi chữ lấy từ bảng/đối số mà `cau_so` nhắc lại đều đi qua đây: `cau_so` là khối model
    chép NGUYÊN vào câu trả lời, nên một ô hay tiêu đề mang xuống dòng/ký tự điều khiển là
    đường chèn lệnh giả vào câu trả lời của bot."""
    s = unicodedata.normalize("NFC", str(s or ""))
    s = "".join(" " if unicodedata.category(c) in ("Cc", "Cf") else c for c in s)
    return " ".join(s.split())


_GACH_DAU = re.compile(r"^[\-–•*+·]\s+")
_DAU_CUOI = re.compile(r"[\s.,;:!?…]+$")


def _khoa(s: str) -> str:
    """Khoá gộp đáp án: không phân biệt hoa thường, gạch đầu dòng, dấu câu cuối."""
    return _DAU_CUOI.sub("", _GACH_DAU.sub("", _gon(s))).casefold()


def _chu_o(o: list[str]) -> str:
    return "\n".join(o).strip()


def _tach(o: list[str], tach_dau_phay: bool) -> list[str]:
    """Một ô → các lựa chọn (mỗi DÒNG trong ô là một lựa chọn)."""
    ra = []
    for chuoi in o:
        for x in re.split(r"[\r\n]+" + (r"|[,;]" if tach_dau_phay else ""), chuoi):
            x = _GACH_DAU.sub("", _gon(x))
            if _khoa(x):
                ra.append(x)
    return ra


# ───────────────────────────── số ─────────────────────────────
_DON_VI = [(r"tỷ|tỉ|ty", Decimal(10) ** 9), (r"triệu|trieu|tr", Decimal(10) ** 6),
           (r"nghìn|nghin|ngàn|ngan|k", Decimal(1000))]
_TIEN = re.compile(r"₫|vnđ|vnd|đồng|đ|usd|\$")


def doc_so(chu: str) -> tuple[Decimal | None, str]:
    """Chữ trong ô → (số, dấu mơ hồ). Không đọc được → (None, ""). Luật CỐ ĐỊNH:

    - bỏ ký hiệu tiền (₫, đ, VND, USD, $), khoảng trắng; "(123)" là số âm (kiểu kế toán);
    - "%" giữ nguyên số đang hiện ("12%" → 12; khi CỘNG thì ô % bị tách riêng, không vào
      tổng); đuôi "tỷ/triệu/tr/nghìn/k" nhân tương ứng;
    - có cả "." và ",": dấu đứng SAU là dấu thập phân ("1.234,5" và "1,234.5");
    - một loại dấu xuất hiện nhiều lần: dấu nghìn ("1.100.000", "8,385,649,200");
    - một dấu duy nhất, sau nó đúng 3 chữ số, trước nó không phải "0": dấu NGHÌN — "1.500"
      và "1,500" đều là 1500. Đây là chỗ mơ hồ duy nhất: trả lại chính dấu đó để nơi gọi
      báo (trừ khi ô có ký hiệu tiền/đơn vị — "700,000 ₫" thì chắc là nghìn); còn lại là
      thập phân ("1,5", "0,512").
    Nhóm nghìn sai khuôn ("1.23.4") → không đọc, không đoán.
    """
    s = unicodedata.normalize("NFC", str(chu or "")).strip().lower()
    if not s:
        return None, ""
    am = False
    if s.startswith("(") and s.endswith(")"):
        am, s = True, s[1:-1].strip()
    nhan = Decimal(1)
    for mau, he_so in _DON_VI:
        m = re.search(rf"(?<=[\d\s.,])({mau})\.?$", s)
        if m:
            nhan, s = he_so, s[:m.start()].strip()
            break
    s = s.removesuffix("%").strip()
    co_tien = nhan != 1 or bool(_TIEN.search(s))
    s = re.sub(r"\s+", "", _TIEN.sub("", s))     # \s gồm cả khoảng trắng không ngắt
    if s and s[0] in "-−+":
        am, s = am ^ (s[0] != "+"), s[1:]
    if not re.fullmatch(r"\d[\d.,]*", s) or s[-1] in ".,":
        return None, ""
    mo_ho = ""
    if "." in s and "," in s:
        tp = "." if s.rfind(".") > s.rfind(",") else ","
        ng = "," if tp == "." else "."
        nguyen, _, le = s.rpartition(tp)
        if ng in le or nguyen.count(tp):
            return None, ""
    elif s.count(".") > 1 or s.count(",") > 1:
        ng = "." if "." in s else ","
        nguyen, le = s, ""
    elif "." in s or "," in s:
        dau = "." if "." in s else ","
        truoc, sau = s.split(dau)
        if len(sau) == 3 and truoc != "0":
            ng, nguyen, le, mo_ho = dau, s, "", ("" if co_tien else dau)
        else:
            ng, nguyen, le = "", truoc, sau
    else:
        ng, nguyen, le = "", s, ""
    if ng:
        nhom = nguyen.split(ng)
        if not (1 <= len(nhom[0]) <= 3 and all(len(x) == 3 for x in nhom[1:])):
            return None, ""
        nguyen = "".join(nhom)
    try:
        v = Decimal(nguyen + ("." + le if le else "")) * nhan
    except InvalidOperation:
        return None, ""
    return (-v if am else v), mo_ho


def so_vn(v: Decimal) -> str:
    """Decimal → kiểu VN: "8.385.649.200", "1.234,5"."""
    v = v.normalize() if v == v.to_integral_value() else v
    dau = "-" if v < 0 else ""
    v = abs(v)
    nguyen = int(v)
    le = format(v - nguyen, "f").split(".")[1].rstrip("0") if v != nguyen else ""
    return dau + f"{nguyen:,}".replace(",", ".") + ("," + le if le else "")


def ty_le(so: int, mau: int) -> str | None:
    """Phần trăm 1 chữ số lẻ, làm tròn nửa lên (73,05 → 73,1), dấu phẩy VN."""
    if not mau:
        return None
    p = (Decimal(so) * 100 / Decimal(mau)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{p}".replace(".", ",") + "%"


# ───────────────────────────── cột ─────────────────────────────
def chu_cot(i: int) -> str:
    return B._ten_cot(i + 1)


def _so_cot(chu: str) -> int:
    n = 0
    for c in chu.upper():
        n = n * 26 + ord(c) - 64
    return n - 1


def _la_stt(h: str) -> bool:
    return re.sub(r"[^\w#]", "", B._bo_dau(h)) in {"stt", "tt", "no", "#", "sott", "sothutu"}


_MA_CAU = re.compile(r"^[a-z]{1,2}\d{1,3}[a-z]?\s*[.):\-]\s*")
#: "Tên …" là tên NGƯỜI, trừ các cột tên đồ vật/việc hay gặp trong bảng marketing.
_TEN_KHONG_PHAI_NGUOI = re.compile(
    r"^ten\s+(san pham|sp|hang muc|chien dich|campaign|bai|cua hang|thuong hieu|brand|kenh|"
    r"mau|file|tab|bang|du an|nhom|pillar|content|video|tai lieu|hoat dong|su kien|event|"
    r"bst|bo suu tap)\b")
_COT_CA_NHAN = re.compile(
    r"\b(sdt|so dien thoai|dien thoai|phone|mobile|e-?mail|gmail|zalo|cccd|cmnd|dia chi nha)\b")
#: Loại cột Base mang danh tính: 11 người, 13 SĐT, 1003/1004 người tạo/sửa.
_LOAI_CA_NHAN = {11, 13, 1003, 1004}
_SDT = re.compile(r"(?<![\d.,])(?:\+?84|0)[ .-]?[35789](?:[ .-]?\d){8}(?![\d.,])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def la_cot_ca_nhan(tieu_de: str) -> bool:
    """Tiêu đề cột trông như tên/SĐT/email/Zalo của một người."""
    h = _MA_CAU.sub("", B._bo_dau(tieu_de))
    if _COT_CA_NHAN.search(h):
        return True
    if h in {"name", "full name", "ho ten", "ho va ten", "ten"}:
        return True
    return bool(re.match(r"(ho va ten|ho ten|ten)\b", h)) and not _TEN_KHONG_PHAI_NGUOI.match(h)


def _an(s: str) -> str:
    return _EMAIL.sub("[email đã ẩn]", _SDT.sub("[SĐT đã ẩn]", s))


def tim_cot(chi: str, tieu_de: list[str]) -> list[int]:
    """Một chỉ định cột → các chỉ số cột khớp.

    'H'/'AB' = chữ cái cột; 'B5', 'C2.' = mã câu ở ĐẦU tiêu đề ('B5' không khớp 'B51');
    còn lại = đoạn tiêu đề (không phân biệt hoa thường, dấu) — trùng khít thì lấy cột đó,
    không thì mọi cột chứa đoạn đó.
    """
    s = (chi or "").strip()
    if not s:
        return []
    if re.fullmatch(r"[A-Za-z]{1,2}", s) and _so_cot(s) < len(tieu_de):
        return [_so_cot(s)]
    m = re.fullmatch(r"([A-Za-z]{1,2}\d{1,3}[A-Za-z]?)\s*[.):]?", s)
    if m:
        ma = m.group(1).lower()
        co = [i for i, h in enumerate(tieu_de)
              if re.match(rf"{re.escape(ma)}(?![0-9a-z])", B._bo_dau(h))]
        if co:
            return co
    k = B._bo_dau(s)
    trung = [i for i, h in enumerate(tieu_de) if B._bo_dau(h) == k]
    return trung or [i for i, h in enumerate(tieu_de) if k and k in B._bo_dau(h)]


def _doc_dong(chi: str) -> set[int] | None:
    """'6-7, 9' → {6, 7, 9}. Sai cú pháp → None."""
    ra: set[int] = set()
    for p in re.split(r"[,;\s]+", (chi or "").strip()):
        if not p:
            continue
        m = re.fullmatch(r"(\d+)(?:\s*[-–:]\s*(\d+))?", p)
        if not m:
            return None
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        ra.update(range(min(a, b), max(a, b) + 1))
    return ra or None


def la_cau_mo(so_dap_an: int, so_luot: int, dai_tb: float) -> bool:
    """Cột trả lời MỞ → không đếm theo đáp án.

    Ba dấu hiệu, dấu nào cũng đủ: quá nhiều đáp án khác nhau (> 40); đáp án dài (trung bình
    > 60 ký tự); hoặc gần như mỗi câu một kiểu (≥ 10 lượt mà ≥ 80% là đáp án riêng). Dấu
    thứ ba đo thật trên câu C3 của khảo sát store: 28 người, 27 câu khác nhau, ngắn
    (~25 ký tự) — hai ngưỡng đầu để lọt, ra 27 dòng "1 (3,6%)" vô nghĩa.
    """
    return (so_dap_an > CAU_MO_SO_GIA_TRI or dai_tb > CAU_MO_DO_DAI
            or (so_luot >= 10 and so_dap_an >= 0.8 * so_luot))


# ───────────────────────────── dòng tiêu đề ─────────────────────────────
def _tu_nhan_tieu_de(luoi: list[list[list[str]]]) -> tuple[int, bool]:
    """(chỉ số từ 0 của dòng tiêu đề, có dòng chữ rõ ràng không) — tự nhận trong 5 dòng đầu.

    Luật: dòng SỚM NHẤT có số ô không trống ≥ 80% mức cao nhất trong 5 dòng đầu — nhưng
    chỉ xét dòng "chữ" (≤ 20% ô là số). Vì sao thêm điều kiện chữ: bảng ngân sách thật
    (BẢNG TỔNG) có dòng 1 tiêu đề 7 ô, còn dòng 4 là dòng nhóm BOOKING đủ 9 ô số — luật
    80% trơn chọn nhầm dòng 4. Khảo sát (dòng 1 tên PHẦN, dòng 2 câu hỏi) và lịch nội dung
    (dòng 1 tên kênh, dòng 2 PHASE, dòng 3 tiêu đề) vẫn ra đúng dòng 2 và dòng 3.
    Không dòng nào là dòng chữ (bảng không có tiêu đề) → bỏ điều kiện chữ, và báo `False`
    để câu số nói rõ tiêu đề là đoán, cần kiểm.
    """
    dem = []
    for i, r in enumerate(luoi[:5]):
        o = [_chu_o(c) for c in r if _chu_o(c)]
        if o:
            so = sum(1 for x in o if doc_so(x)[0] is not None)
            dem.append((i, len(o), so / len(o) <= 0.2))
    if not dem:
        return 0, False
    ro = any(x[2] for x in dem)
    ung = [x for x in dem if x[2]] or dem
    cao = max(x[1] for x in ung)
    return next(i for i, c, _ in ung if c >= 0.8 * cao), ro


# ───────────────────────────── đếm một bảng ─────────────────────────────
def dem(luoi: list[list[list[str]]], *, cot=None, nhom_theo: str = "", cong=None,
        dong: str = "", dong_tieu_de: int | None = None, tach_dau_phay: bool = False,
        gop=None, loai_cot: list | None = None, top: int = TOP_GIA_TRI,
        khong_tieu_de: bool = False) -> dict:
    """Đếm trên lưới thô của `lark_bang.doc_tho`. Hàm thuần — không gọi mạng.

    Trả dict kết quả; `loi` khác rỗng khi không đếm được (tiêu đề ngoài bảng, dòng sai cú
    pháp…). Số dòng trả về là số dòng THẬT trên Sheet (đếm từ 1).
    `khong_tieu_de` (hoặc `dong_tieu_de=0`): mọi dòng là dữ liệu, cột chỉ có chữ cái —
    `dong_tieu_de_da_dung` = 0.
    """
    if not luoi:
        return {"loi": "bảng trống — không có dòng nào"}
    so_cot = max(len(r) for r in luoi)
    luoi = [list(r) + [[]] * (so_cot - len(r)) for r in luoi]
    if khong_tieu_de or dong_tieu_de == 0:
        h, tu_nhan, ro = -1, False, True
    elif dong_tieu_de:
        if not 1 <= int(dong_tieu_de) <= len(luoi):
            return {"loi": f"dòng tiêu đề {dong_tieu_de} nằm ngoài bảng (bảng có "
                           f"{len(luoi)} dòng)"}
        h, tu_nhan, ro = int(dong_tieu_de) - 1, False, True
    else:
        (h, ro), tu_nhan = _tu_nhan_tieu_de(luoi), True

    # Tiêu đề: ô dòng tiêu đề; trống thì lấy ô gần nhất PHÍA TRÊN (ô gộp dọc kiểu "STT"
    # ở A1:A2 của khảo sát chỉ có chữ ở dòng 1).
    tieu_de = []
    for j in range(so_cot):
        t = next((_gon(_chu_o(luoi[i][j])) for i in range(h, -1, -1) if _chu_o(luoi[i][j])), "")
        tieu_de.append(t)
    stt = {j for j in range(so_cot) if any(_la_stt(_chu_o(luoi[i][j])) for i in range(h + 1))}
    khoa_td = ({j: _khoa(_chu_o(luoi[h][j])) for j in range(so_cot) if _chu_o(luoi[h][j])}
               if h >= 0 else {})

    loc = None
    if dong:
        loc = _doc_dong(dong)
        if loc is None:
            return {"loi": f"không hiểu `dong` = '{dong}' — viết kiểu '6-7' hoặc '9-11, 13'"}

    du_lieu, lap = [], []
    for i in range(h + 1, len(luoi)):
        r = luoi[i]
        if not any(_chu_o(r[j]) for j in range(so_cot) if j not in stt):
            continue
        # Dòng lặp lại tiêu đề (mỗi phase một lần): ≥ 80% ô tiêu đề trùng khít.
        if len(khoa_td) >= 2 and sum(1 for j, k in khoa_td.items()
                                     if _khoa(_chu_o(r[j])) == k) >= 0.8 * len(khoa_td):
            lap.append(i + 1)
            continue
        if loc is not None and (i + 1) not in loc:
            continue
        du_lieu.append(i)
    n = len(du_lieu)
    ten = [f"{t} [cột {chu_cot(j)}]" if t else f"cột {chu_cot(j)}" for j, t in enumerate(tieu_de)]

    def _ca_nhan(j: int) -> str:
        if loai_cot and j < len(loai_cot) and loai_cot[j] in _LOAI_CA_NHAN:
            return "cột người/SĐT của Base"
        if la_cot_ca_nhan(tieu_de[j]):
            return "tiêu đề là tên/SĐT/email"
        if any(_SDT.search(_chu_o(luoi[i][j])) or _EMAIL.search(_chu_o(luoi[i][j]))
               for i in du_lieu):
            return "ô có dạng SĐT/email"
        return ""

    kq: dict = {"dong_tieu_de_da_dung": h + 1, "tieu_de_tu_nhan": tu_nhan,
                **({} if ro else {"tieu_de_khong_ro": True}),
                "tieu_de": [{"cot": chu_cot(j), "tieu_de": t} for j, t in enumerate(tieu_de)
                            if t], "n": n,
                "dong_du_lieu": (f"{du_lieu[0] + 1}–{du_lieu[-1] + 1}" if du_lieu else None)}
    if lap:
        kq["dong_lap_tieu_de_bo_qua"] = lap
    if loc is not None:
        kq["chi_xet_dong"] = dong

    # Chọn cột.
    bo_qua, khong_thay, ghi_chu = [], [], []
    chon: list[int] = []
    cong_j: list[int] = []
    for c in (cong or []):
        co = tim_cot(str(c), tieu_de)
        if not co:
            khong_thay.append(str(c))
        cong_j += [j for j in co if j not in cong_j]
    if cot:
        for c in cot:
            co = tim_cot(str(c), tieu_de)
            if not co:
                khong_thay.append(str(c))
            elif len(co) > 1:
                ghi_chu.append(f"'{c}' khớp {len(co)} cột: " + ", ".join(ten[j] for j in co))
            chon += [j for j in co if j not in chon]
    elif not cong_j or nhom_theo:
        chon = [j for j in range(so_cot) if j not in stt and j not in cong_j
                and any(_chu_o(luoi[i][j]) for i in du_lieu)]
    g_j = None
    if nhom_theo:
        co = tim_cot(nhom_theo, tieu_de)
        if not co:
            khong_thay.append(nhom_theo)
        else:
            g_j = co[0]
            if len(co) > 1:
                ghi_chu.append(f"nhóm theo '{nhom_theo}' khớp {len(co)} cột, dùng "
                               f"{ten[g_j]}")
    for j in sorted(set(chon) | set(cong_j) | ({g_j} if g_j is not None else set())):
        ly_do = _ca_nhan(j)
        if ly_do:
            bo_qua.append({"cot": ten[j], "ly_do": f"thông tin cá nhân ({ly_do}) — không "
                                                   "đếm, không trả giá trị"})
            chon = [x for x in chon if x != j]
            cong_j = [x for x in cong_j if x != j]
            if g_j == j:
                g_j = None
    if khong_thay:
        kq["cot_khong_thay"] = khong_thay
    if bo_qua:
        kq["cot_bo_qua"] = bo_qua
    if ghi_chu:
        kq["ghi_chu"] = ghi_chu

    # Bảng gộp cách viết: khoá → (khoá đích, tên đích).
    ban_gop: dict[str, tuple[str, str]] = {}
    for nhom in (gop or []):
        nhom = [_gon(x) for x in (nhom or []) if _khoa(str(x))]
        if len(nhom) >= 2:
            for x in nhom:
                ban_gop[_khoa(x)] = (_khoa(nhom[0]), nhom[0])
    if ban_gop:
        kq["da_gop"] = [list(x) for x in (gop or []) if len(x or []) >= 2]

    def _lua_chon(i: int, j: int) -> list[tuple[str, str]]:
        """[(khoá, cách viết)] của một ô, mỗi khoá MỘT lần (một người tính một)."""
        ra, thay = [], set()
        for x in _tach(luoi[i][j], tach_dau_phay):
            k = _khoa(x)
            k, x = ban_gop.get(k, (k, x))
            if k not in thay:
                thay.add(k)
                ra.append((k, x))
        return ra

    # Nhóm (so nhóm).
    nhom_cua: dict[int, list[str]] = {}
    ten_nhom: dict[str, Counter] = {}
    co_nhom: Counter = Counter()
    if g_j is not None:
        for i in du_lieu:
            ks = _lua_chon(i, g_j) or [("", "(trống)")]
            nhom_cua[i] = [k for k, _ in ks]
            for k, x in ks:
                ten_nhom.setdefault(k, Counter())[x] += 1
                co_nhom[k] += 1
        thu_tu_nhom = [k for k, _ in sorted(co_nhom.items(), key=lambda kv: -kv[1])]
        kq["nhom_theo"] = {
            "cot": ten[g_j],
            "nhom": [{"gia_tri": ten_nhom[k].most_common(1)[0][0], "n": co_nhom[k],
                      **({"nho": True} if co_nhom[k] < NHOM_NHO else {})}
                     for k in thu_tu_nhom]}
        if any(len(v) > 1 for v in nhom_cua.values()):
            kq["nhom_theo"]["ghi_chu"] = ("cột nhóm có ô nhiều lựa chọn — một người có thể "
                                          "thuộc nhiều nhóm")

    def _dem_cot(j: int, dong_xet: list[int]) -> dict:
        so: Counter = Counter()
        viet: dict[str, Counter] = {}
        dau_tien: dict[str, int] = {}
        tra_loi, nhieu, do_dai = 0, False, []
        for i in dong_xet:
            ks = _lua_chon(i, j)
            if not ks:
                continue
            tra_loi += 1
            nhieu = nhieu or len(ks) > 1
            for k, x in ks:
                so[k] += 1
                viet.setdefault(k, Counter())[x] += 1
                dau_tien.setdefault(k, len(dau_tien))
                do_dai.append(len(x))
        thu_tu = sorted(so, key=lambda k: (-so[k], dau_tien[k]))
        return {"tra_loi": tra_loi, "nhieu": nhieu, "thu_tu": thu_tu, "so": so,
                "viet": {k: v.most_common(1)[0][0] for k, v in viet.items()},
                "dai_tb": (sum(do_dai) / len(do_dai)) if do_dai else 0}

    def _liet_ke(d: dict, mau_n: int | None) -> tuple[list[dict], dict | None]:
        ds = []
        for k in d["thu_tu"][:top]:
            m = {"gia_tri": d["viet"][k], "so": d["so"][k],
                 "ty_le_tren_tra_loi": ty_le(d["so"][k], d["tra_loi"])}
            if mau_n is not None:
                m["ty_le_tren_n"] = ty_le(d["so"][k], mau_n)
            ds.append(m)
        con = d["thu_tu"][top:]
        return ds, ({"so_lua_chon": len(con), "so_luot_chon": sum(d["so"][k] for k in con)}
                    if con else None)

    ket_cot = []
    for j in chon:
        d = _dem_cot(j, du_lieu)
        muc: dict = {"cot": chu_cot(j), "tieu_de": tieu_de[j], "so_tra_loi": d["tra_loi"]}
        if not d["tra_loi"]:
            muc["trong"] = True
            ket_cot.append(muc)
            continue
        if la_cau_mo(len(d["thu_tu"]), sum(d["so"].values()), d["dai_tb"]):
            muc.update(la_cau_mo=True, so_cach_tra_loi=len(d["thu_tu"]))
            ket_cot.append(muc)
            continue
        muc["la_nhieu_lua_chon"] = d["nhieu"]
        muc["so_dap_an"] = len(d["thu_tu"])
        muc["gia_tri"], con = _liet_ke(d, n)
        if con:
            muc["con_lai"] = con
        if g_j is not None and j != g_j:
            theo = []
            for k in [x for x, _ in sorted(co_nhom.items(), key=lambda kv: -kv[1])]:
                dn = _dem_cot(j, [i for i in du_lieu if k in nhom_cua[i]])
                ds, con_n = _liet_ke(dn, None)
                theo.append({"nhom": ten_nhom[k].most_common(1)[0][0], "n": co_nhom[k],
                             "so_tra_loi": dn["tra_loi"], "gia_tri": ds,
                             **({"con_lai": con_n} if con_n else {})})
            muc["theo_nhom"] = theo
        ket_cot.append(muc)
    kq["cot"] = ket_cot

    # Cộng.
    if cong_j:
        ket_cong = []
        for j in cong_j:
            tong, co_so, mo_ho = Decimal(0), 0, []
            # Ô "%" KHÔNG cộng vào tổng: cộng tỷ lệ với tiền (hay cộng các tỷ lệ với nhau) là
            # vô nghĩa. Giữ riêng (chữ, giá trị, dòng) để báo lại.
            pt: list[tuple[str, Decimal, int]] = []
            bo: list[str] = []
            so_bo = 0
            dong_tong = []
            theo: dict[str, Decimal] = {}
            for i in du_lieu:
                chu = _chu_o(luoi[i][j])
                if not chu:
                    continue
                v, mh = doc_so(chu)
                if v is None:
                    so_bo += 1
                    vi_du = _an(_gon(chu))[:60]
                    if vi_du not in bo:
                        bo.append(vi_du)
                    continue
                if chu.strip().endswith("%"):
                    pt.append((_gon(chu), v, i + 1))
                    continue
                tong += v
                co_so += 1
                if mh:
                    mo_ho.append((_gon(chu), mh))
                # Dòng mang chữ TỔNG/Chênh lệch ở cột khác: tổng cột đã gồm cả nó.
                if any(re.match(r"(tong|total|chenh lech)\b", B._bo_dau(_chu_o(luoi[i][x])))
                       for x in range(so_cot) if x != j):
                    dong_tong.append(i + 1)
                if g_j is not None:
                    for k in nhom_cua[i]:
                        theo[k] = theo.get(k, Decimal(0)) + v
            # Cột đã có ô "1.100.000" (dấu chấm nhiều nhóm) thì "1.500" cùng cột chắc chắn
            # cũng là nghìn — chỉ báo mơ hồ khi cột không tự cho biết quy ước.
            ro = {d for d in ".," if any(re.search(rf"\d{re.escape(d)}\d{{3}}{re.escape(d)}\d{{3}}",
                                                   _chu_o(luoi[i][j])) for i in du_lieu)}
            mo_ho = [x for x, d in mo_ho if d not in ro]
            m = {"cot": chu_cot(j), "tieu_de": tieu_de[j],
                 "tong": so_vn(tong) if co_so or not pt else None,
                 "so_o_so": co_so, "so_o_bo_qua": so_bo}
            if bo:
                m["vi_du_bo_qua"] = bo[:3]
            if mo_ho:
                m["o_hieu_la_nghin"] = {"so_o": len(mo_ho), "vi_du": mo_ho[:3]}
            if pt and not co_so:
                # Cột toàn %: không có tổng, chỉ báo khoảng giá trị.
                m["chi_phan_tram"] = {"so_o": len(pt),
                                      "nho_nhat": so_vn(min(v for _, v, _ in pt)) + "%",
                                      "lon_nhat": so_vn(max(v for _, v, _ in pt)) + "%"}
            elif pt:
                m["o_phan_tram_khong_cong"] = {"so_o": len(pt),
                                               "vi_du": [x for x, _, _ in pt[:3]],
                                               "dong": [d for _, _, d in pt]}
            if dong_tong:
                m["dong_co_chu_tong"] = dong_tong
            if g_j is not None and m["tong"] is not None:
                m["theo_nhom"] = [{"nhom": ten_nhom[k].most_common(1)[0][0],
                                   "tong": so_vn(theo.get(k, Decimal(0)))}
                                  for k, _ in sorted(co_nhom.items(), key=lambda kv: -kv[1])]
            ket_cong.append(m)
        kq["tong"] = ket_cong

    # Dòng trùng: giống hệt mọi cột trừ STT (skill nghiên cứu khách hàng bắt soát).
    if du_lieu:
        stt_j = min(stt) if stt else None
        nhom_trung: dict[tuple, list[int]] = {}
        for i in du_lieu:
            k = tuple(_khoa(_chu_o(luoi[i][j])) for j in range(so_cot) if j not in stt)
            nhom_trung.setdefault(k, []).append(i)
        trung = [v for v in nhom_trung.values() if len(v) > 1]
        kq["dong_trung"] = {
            "so_dong_trung": sum(len(v) - 1 for v in trung),
            "nhom": [{"dong": [i + 1 for i in v],
                      **({"stt": [_gon(_chu_o(luoi[i][stt_j])) for i in v]}
                         if stt_j is not None else {})} for v in trung[:10]]}
    return kq


# ───────────────────────────── câu số ─────────────────────────────
def _ds_gia_tri(ds: list[dict], con: dict | None) -> str:
    s = "; ".join(f"{m['gia_tri']}: {m['so']} ({m['ty_le_tren_tra_loi']})" for m in ds)
    if con:
        s += (f"; và {con['so_lua_chon']} lựa chọn khác ({con['so_luot_chon']} lượt chọn, "
              "xem đủ bằng `cot`)")
    return s


def cau_so(ten_tab: str, kq: dict, *, dan: str = "") -> str:
    """Khối chữ thuần (không bảng markdown) để model chép nguyên.

    `dan` = mô tả cách đọc chữ dán (`doc_du_lieu_dan`) → câu mở bằng "Dữ liệu dán trong
    chat" thay cho tên tab, và số dòng là thứ tự dòng trong bảng dán.
    """
    dau_nguon = (f"Dữ liệu dán trong chat ({dan}; số dòng = thứ tự dòng trong bảng dán)"
                 if dan else f'Tab "{_gon(ten_tab)}"')
    if kq.get("loi"):
        return f'{dau_nguon}: không đếm được — {_gon(kq["loi"])}.'
    n = kq["n"]
    if kq["dong_tieu_de_da_dung"] == 0:
        td = " — không có dòng tiêu đề, cột gọi theo chữ cái (A, B…)"
    else:
        td = (f' — tiêu đề ở dòng {kq["dong_tieu_de_da_dung"]}'
              + ((" (tự nhận, KHÔNG thấy dòng chữ nào rõ là tiêu đề trong 5 dòng đầu — kiểm "
                  "lại, sai thì gọi lại với dong_tieu_de)" if kq.get("tieu_de_khong_ro") else
                  " (tự nhận; sai thì gọi lại với dong_tieu_de)")
                 if kq["tieu_de_tu_nhan"] else " (theo dong_tieu_de đã chỉ định)"))
    L = [dau_nguon + td
         + f'. n = {n} dòng có dữ liệu'
         + (f' (dòng {kq["dong_du_lieu"]}; không tính dòng trống hoặc chỉ có STT)'
            if kq.get("dong_du_lieu") else "")
         + (f'; chỉ xét dòng {_gon(kq["chi_xet_dong"])}' if kq.get("chi_xet_dong") else "")
         + "."]
    # Cột cá nhân bị bỏ qua: ghi NGAY ĐẦU — câu số dài bị cắt đuôi thì vẫn còn dòng này.
    for b in kq.get("cot_bo_qua", []):
        L.append(f"Bỏ qua {b['cot']}: {b['ly_do']}.")
    if kq.get("dong_lap_tieu_de_bo_qua"):
        L.append("Bỏ qua dòng lặp lại tiêu đề: " + ", ".join(map(str, kq["dong_lap_tieu_de_bo_qua"])) + ".")
    t = kq.get("dong_trung")
    if t is not None:
        if t["so_dong_trung"]:
            L.append(f"Dòng trùng (giống hệt mọi cột trừ STT): {t['so_dong_trung']} — " + "; ".join(
                ("STT " + " = STT ".join(g["stt"]) + " " if g.get("stt") and all(g["stt"])
                 else "") + f"(dòng {', '.join(map(str, g['dong']))})" for g in t["nhom"])
                + ". Không tự xoá: có thể là hai người trả lời giống nhau.")
        else:
            L.append("Dòng trùng (giống hệt mọi cột trừ STT): không có.")
    g = kq.get("nhom_theo")
    if g:
        L.append(f"So nhóm theo {g['cot']}: " + "; ".join(
            f'"{x["gia_tri"]}" n={x["n"]}' + (" (dưới 10 người — chỉ tham khảo)" if x.get("nho") else "")
            for x in g["nhom"]) + ".")
    for c in kq.get("cot", []):
        dau = f"{c['tieu_de']} [cột {c['cot']}]" if c["tieu_de"] else f"cột {c['cot']}"
        if c.get("trong"):
            L.append(f"{dau}: không ai trả lời trong các dòng đã xét.")
            continue
        tl = f"{c['so_tra_loi']}/{n} người trả lời"
        if c.get("la_cau_mo"):
            L.append(f"{dau} — câu trả lời MỞ ({c['so_cach_tra_loi']} cách trả lời khác "
                     f"nhau): {tl}. Không đếm theo đáp án — đọc nội dung bằng doc_bang để "
                     "mã hoá ý.")
            continue
        L.append(f"{dau} — {tl}, % tính trên {c['so_tra_loi']} người trả lời"
                 + ("; câu chọn nhiều nên tổng % có thể >100%" if c.get("la_nhieu_lua_chon") else "")
                 + ": " + _ds_gia_tri(c["gia_tri"], c.get("con_lai")) + ".")
        for x in c.get("theo_nhom", []):
            L.append(f'  · nhóm "{x["nhom"]}" (n={x["n"]}, {x["so_tra_loi"]} trả lời câu này)'
                     + (": " + _ds_gia_tri(x["gia_tri"], x.get("con_lai")) if x["gia_tri"] else ": —")
                     + ".")
    for c in kq.get("tong", []):
        ten_c = f"{c['tieu_de']} [cột {c['cot']}]" if c["tieu_de"] else f"cột {c['cot']}"
        if c.get("chi_phan_tram"):
            p = c["chi_phan_tram"]
            L.append(f"{ten_c}: cả {p['so_o']} ô đều là % nên KHÔNG cộng tổng (cộng tỷ lệ vô "
                     f"nghĩa); thấp nhất {p['nho_nhat']}, cao nhất {p['lon_nhat']}.")
            continue
        s = f"Tổng {ten_c}: {c['tong']} — cộng {c['so_o_so']} ô có số"
        if c["so_o_bo_qua"]:
            s += (f"; bỏ qua {c['so_o_bo_qua']} ô không phải số (vd "
                  + ", ".join(f'"{x}"' for x in c.get("vi_du_bo_qua", [])) + ")")
        if c.get("o_hieu_la_nghin"):
            s += (f"; {c['o_hieu_la_nghin']['so_o']} ô kiểu '1.500' được hiểu là phân cách "
                  "nghìn")
        if c.get("o_phan_tram_khong_cong"):
            p = c["o_phan_tram_khong_cong"]
            s += (f"; {p['so_o']} ô là % nên không cộng vào tổng (vd "
                  + ", ".join(f'"{x}"' for x in p["vi_du"]) + "; dòng "
                  + ", ".join(map(str, p["dong"][:10])) + ("…" if len(p["dong"]) > 10 else "")
                  + ")")
        if c.get("dong_co_chu_tong"):
            s += ("; CẢNH BÁO: tổng đã gồm dòng ghi TỔNG/Chênh lệch (dòng "
                  + ", ".join(map(str, c["dong_co_chu_tong"])) + ") — dùng `dong` để loại")
        L.append(s + ".")
        for x in c.get("theo_nhom", []):
            L.append(f'  · nhóm "{x["nhom"]}": {x["tong"]}')
    if kq.get("cot_khong_thay"):
        L.append("Không thấy cột: " + ", ".join(f"'{_gon(x)}'" for x in kq["cot_khong_thay"])
                 + " — xem danh sách `tieu_de`.")
    for x in kq.get("ghi_chu", []):
        L.append(f"Lưu ý: {_gon(x)}.")
    if kq.get("da_gop"):
        L.append("Đã gộp: " + "; ".join(" = ".join(_gon(y) for y in x) for x in kq["da_gop"])
                 + ".")
    return "\n".join(L)


# ───────────────────────────── dữ liệu dán trong chat ─────────────────────────────
class LoiDan(ValueError):
    """Chữ dán không đọc thành bảng được (quá cỡ, trống) — lời nhắn gửi thẳng cho model."""


_DONG_KE_MD = re.compile(r"^\s*:?-{2,}:?\s*$")
_BR = re.compile(r"<br\s*/?>", re.I)
_GACH_DONG = re.compile(r"^\s*(?:[-•*+·]|\d{1,3}[.)])\s+")
_NHAN_SO = re.compile(r"^\s*([^:\t|]*[^\W\d][^:\t|]*?)\s*:\s*(\S.*?)\s*$")


def _la_so(chu: str) -> bool:
    return doc_so(chu)[0] is not None


def _csv(chu: str, dau: str) -> list[list[str]]:
    return [r for r in csv.reader(io.StringIO(chu), delimiter=dau) if any(x.strip() for x in r)]


def _tach_md(dong: str, bo_vien: bool) -> list[str]:
    d = dong.strip()
    if bo_vien:
        d = d[1:] if d.startswith("|") else d
        d = d[:-1] if d.endswith("|") and not d.endswith("\\|") else d
    o = [x.replace("\\|", "|") for x in re.split(r"(?<!\\)\|", d)]
    return [_BR.sub("\n", x).strip() for x in o]


def _giong_csv(chu: str, dau: str) -> bool:
    """Dấu phân cách là dấu CỘT (CSV xuất từ công cụ) chứ không phải dấu câu: CSV không có
    dấu cách sau dấu phân cách (hoặc có ô ngoặc kép). Văn xuôi tiếng Việt luôn có — "Có, mua
    luôn hôm nay" là MỘT đáp án, không phải hai cột."""
    tong = chu.count(dau)
    sau_cach = len(re.findall(re.escape(dau) + r"[ \t]", chu))
    return bool(tong) and (sau_cach <= 0.1 * tong or f'{dau}"' in chu or f'"{dau}' in chu)


def _deu_cot(dong: list[list[str]]) -> int:
    """Số cột chung của CSV nếu ra dáng bảng thật (≥ 80% dòng cùng số cột > 1 và dòng đầu
    cũng vậy), không thì 0."""
    if len(dong) < 2:
        return 0
    dem_c: dict[int, int] = {}
    for r in dong:
        dem_c[len(r)] = dem_c.get(len(r), 0) + 1
    c, so = max(dem_c.items(), key=lambda kv: (kv[1], kv[0]))
    return c if c > 1 and so >= 0.8 * len(dong) and len(dong[0]) == c else 0


def doc_du_lieu_dan(chu: str) -> tuple[list[list[list[str]]], str, bool | None]:
    """Chữ người dùng dán → (lưới như `doc_tho`, mô tả cách đã đọc, có tiêu đề không).

    "có tiêu đề": True/False khi cách đọc tự biết (dòng "nhãn: số" thì không; danh sách một
    cột thì theo luật ở docstring module), None = để `dem()` tự nhận như với Sheet.
    Luật xem docstring module (mục DỮ LIỆU DÁN). Không đoán theo nghĩa.
    """
    chu = unicodedata.normalize("NFC", str(chu or "")).replace("\ufeff", "")
    chu = chu.replace("\r\n", "\n").replace("\r", "\n")
    if len(chu) > MAX_KY_TU_DAN:
        raise LoiDan(f"dữ liệu dán dài {so_vn(Decimal(len(chu)))} ký tự, trần "
                     f"{so_vn(Decimal(MAX_KY_TU_DAN))} — bảng cỡ này nên đưa lên Lark Sheet "
                     "rồi đếm bằng `nguon`")
    dong = [d for d in chu.split("\n") if d.strip()]
    if not dong:
        raise LoiDan("dữ liệu dán trống")
    co_td: bool | None = None
    dau_cot = ""
    if "\t" in chu:
        rows, mo_ta, dau_cot = _csv(chu.strip("\n"), "\t"), "bảng cách nhau bằng tab", "\t"
    elif sum(d.lstrip().startswith("|") for d in dong) >= 0.6 * len(dong):
        rows = [_tach_md(d, True) for d in dong
                if not all(_DONG_KE_MD.match(x) for x in _tach_md(d, True))]
        mo_ta, dau_cot = "bảng markdown", "|"
    elif sum("|" in d for d in dong) >= 0.6 * len(dong):
        rows, mo_ta, dau_cot = [_tach_md(d, False) for d in dong], "cột cách nhau bằng '|'", "|"
    else:
        rows, mo_ta = [], ""
        for dau, ten in ((";", "CSV dấu ';'"), (",", "CSV dấu ','")):
            r = _csv(chu, dau)
            if _deu_cot(r) and _giong_csv(chu, dau):
                rows, mo_ta, dau_cot = r, ten, dau
                break
        if not rows:
            nhan = [_NHAN_SO.match(d) for d in dong]
            if sum(1 for m in nhan if m and _la_so(m.group(2))) >= max(2, 0.8 * len(dong)):
                rows = [[m.group(1), m.group(2)] if m else [d.strip()] for m, d in zip(nhan, dong)]
                mo_ta, co_td = "dòng 'nhãn: số' — cột A nhãn, cột B số", False
            else:
                rows = [[_GACH_DONG.sub("", d).strip()] for d in dong]
                mo_ta = "mỗi dòng một giá trị (cột A)"
                dau = rows[0][0]
                con = [r[0] for r in rows[1:]]
                co_td = bool(con) and (dau.endswith((":", "?")) or (
                    not _la_so(dau) and sum(map(_la_so, con)) >= 0.8 * len(con)))
    if len(rows) > MAX_DONG_DAN:
        raise LoiDan(f"dữ liệu dán có {len(rows)} dòng, trần {MAX_DONG_DAN} — đưa lên Lark "
                     "Sheet rồi đếm bằng `nguon`")
    so_cot = max(len(r) for r in rows)
    # Ô nhiều lựa chọn tách bằng ";" (kiểu xuất Microsoft Forms) — chỉ khi rõ ràng.
    cham_phay = []
    if dau_cot != ";":
        for j in range(so_cot):
            o = [r[j] for r in rows[1:] if j < len(r) and r[j].strip()]
            if sum(";" in x for x in o) >= 2 and not any(_la_so(x) for x in o):
                cham_phay.append(j)
    luoi = []
    for r in rows:
        hang = []
        for j in range(so_cot):
            x = r[j] if j < len(r) else ""
            if j in cham_phay:
                x = "\n".join(p.strip() for p in x.split(";"))
            hang.append([x] if x.strip() else [])
        luoi.append(hang)
    if cham_phay:
        mo_ta += "; ô có ';' ở cột " + ", ".join(chu_cot(j) for j in cham_phay) \
            + " tách thành nhiều lựa chọn"
    return luoi, mo_ta, co_td


# ───────────────────────────── tool ─────────────────────────────
def _ds(x) -> list[str]:
    if x is None or x == "":
        return []
    if isinstance(x, str):
        return [p.strip() for p in re.split(r"[,;]", x) if p.strip()]
    return [str(v).strip() for v in x if str(v).strip()]


def _dem_va_gon(bang_vao: list[dict], tham: dict, dau: dict, dan: str = "") -> dict:
    """Đếm từng bảng rồi thu gọn kết quả cho vừa `MAX_KY_TU_RA` — chung cho Sheet/Base và
    dữ liệu dán. `bang_vao`: [{ten, luoi, loai_cot?, bi_cat?, khong_tieu_de?}]."""
    ra: dict = {}
    for top in (TOP_GIA_TRI, 10, 5):
        bang, cau, bi_cat = [], [], False
        for b in bang_vao:
            kq = dem(b["luoi"], loai_cot=b.get("loai_cot"), top=top,
                     khong_tieu_de=b.get("khong_tieu_de", False), **tham)
            # Nhiều tab mà tab này không có cột nào được hỏi: bỏ, khỏi làm rối câu số.
            if (len(bang_vao) > 1 and (tham["cot"] or tham["cong"])
                    and not kq.get("cot") and not kq.get("tong")):
                continue
            bang.append({"tab": b["ten"], **kq})
            cau.append(cau_so(b["ten"], kq, dan=dan))
            bi_cat = bi_cat or b.get("bi_cat", False)
        ra = {**dau, "bang": bang,
              "cau_so": "\n\n".join(cau) or "Không tab nào có cột được hỏi.",
              "huong_dan": HUONG_DAN}
        if bi_cat:
            ra["bi_cat"] = True
            ra["cau_so"] += ("\n\nLƯU Ý: chạm trần đọc một lần — số trên chỉ tính phần đã "
                             "đọc, không phải cả bảng.")
        if len(json.dumps(ra, ensure_ascii=False)) <= MAX_KY_TU_RA:
            break
    if len(json.dumps(ra, ensure_ascii=False)) > MAX_KY_TU_RA:
        # Vẫn quá lớn (nhiều tab × nhiều cột): bỏ chi tiết JSON, giữ câu số đã cắt gọn.
        ra["bang"] = [{k: v for k, v in b.items() if k in ("tab", "n", "dong_tieu_de_da_dung",
                                                           "tieu_de", "loi")}
                      for b in ra["bang"]]
        ra["cau_so"] = ra["cau_so"][:MAX_KY_TU_RA // 2] + (
            "\n…(đã cắt: kết quả quá dài — gọi lại với `tab` và `cot` cụ thể)")
        ra["bi_cat_ket_qua"] = True
    return ra


def _cot_so(luoi: list[list[list[str]]], co_td: bool) -> tuple[list[str], list[str]]:
    """(cột gần như toàn số, cột chữ) của phần dữ liệu — để tự chọn `cong` cho danh sách
    số dán vào chat mà không nói cột nào."""
    so, chu = [], []
    for j in range(max(len(r) for r in luoi)):
        o = [_chu_o(r[j]) for r in luoi[1 if co_td else 0:] if j < len(r) and _chu_o(r[j])]
        if not o:
            continue
        if sum(map(_la_so, o)) < 0.8 * len(o):
            chu.append(chu_cot(j))
        elif [doc_so(x)[0] for x in o] != [Decimal(k) for k in range(1, len(o) + 1)]:
            # Cột 1, 2, 3… là mã/STT của người trả lời, không phải số để cộng.
            so.append(chu_cot(j))
    return so, chu


def _handle_dan(a: dict, du_lieu: str, tham: dict) -> str:
    """`du_lieu`: bảng người dùng dán. Không kiểm quyền Lark, không đọc gì qua mạng."""
    try:
        luoi, mo_ta, co_td = doc_du_lieu_dan(du_lieu)
    except LoiDan as e:
        return tool_error(f"Không đọc được dữ liệu dán: {e}.")
    khong_td = False
    if tham["dong_tieu_de"] is None:
        if co_td is not None:
            khong_td = not co_td
            if co_td:
                tham = {**tham, "dong_tieu_de": 1}
        else:
            # Không dòng chữ nào ra dáng tiêu đề → bảng số không tiêu đề; đừng nuốt dòng
            # số đầu làm tiêu đề (với Sheet thì vẫn báo "tiêu đề không rõ" như cũ).
            khong_td = not _tu_nhan_tieu_de(luoi)[1]
    tu_chon = None
    if not (tham["cot"] or tham["cong"] or tham["nhom_theo"]):
        so, chu = _cot_so(luoi, not khong_td and tham["dong_tieu_de"] != 0)
        # Danh sách số / "nhãn: số" (≤ 1 cột chữ làm nhãn): hỏi tổng là việc hiển nhiên.
        if so and len(chu) <= 1:
            tham = {**tham, "cong": so}
            tu_chon = so
    ra = _dem_va_gon([{"ten": TEN_NGUON_DAN, "luoi": luoi, "khong_tieu_de": khong_td}], tham,
                     {"nguon": TEN_NGUON_DAN, "loai": "Dữ liệu dán", "dinh_dang": mo_ta,
                      "so_dong_doc_duoc": len(luoi), "so_cot": max(len(r) for r in luoi)},
                     dan=mo_ta)
    if tu_chon:
        ra["tu_chon_cong"] = tu_chon
        ra["cau_so"] += ("\nTự cộng cột " + ", ".join(tu_chon) + " (dữ liệu dán chỉ có số"
                         " và nhãn); muốn đếm theo giá trị thì gọi lại với `cot`.")
    return tool_result(ra)


def _handle(args: dict, **_kw) -> str:
    a = args or {}
    nguon = str(a.get("nguon") or "").strip()
    try:
        dong_td = int(a["dong_tieu_de"]) if a.get("dong_tieu_de") not in (None, "") else None
    except (TypeError, ValueError):
        return tool_error("`dong_tieu_de` phải là số dòng (đếm từ 1; 0 = không có tiêu đề).")
    tham = dict(cot=_ds(a.get("cot")), nhom_theo=str(a.get("nhom_theo") or "").strip(),
                cong=_ds(a.get("cong")), dong=str(a.get("dong") or "").strip(),
                dong_tieu_de=dong_td, tach_dau_phay=bool(a.get("tach_dau_phay")),
                gop=[x for x in (a.get("gop") or []) if isinstance(x, list)])
    du_lieu = a.get("du_lieu")
    if isinstance(du_lieu, str) and du_lieu.strip():
        return _handle_dan(a, du_lieu, tham)
    if not nguon:
        return tool_error("Cần `nguon` (link Base/Sheet) hoặc `du_lieu` (bảng/danh sách "
                          "người dùng dán trong chat, chép nguyên văn).")
    try:
        loai, token, phu, ten_loai, vi_sao = BT.mo_nguon(nguon)
    except BT.TuChoi as e:
        return tool_error(str(e))
    tab = str(a.get("tab") or "").strip()
    if phu and tab and tab != phu:
        return tool_error("Nguồn đã chỉ đúng một bảng/tab; không được đổi sang bảng/tab khác.")
    try:
        tho = B.doc_tho(loai, token, tab or phu, strict_scope=bool(phu))
    except Exception as e:
        return tool_error(BT.loi_doc(ten_loai, e))
    if not tho["bang"]:
        # Base nội bộ hỗn hợp: không liệt kê tên bảng (lộ tên Audit/Chi phí).
        if token in BT.base_noi_bo():
            return tool_error(f"Không thấy bảng '{tab or phu}' trong {ten_loai} này.")
        return tool_error(f"Không thấy tab/bảng '{tab or phu}' trong {ten_loai} này. Các "
                          f"tab: {', '.join(map(str, tho['tat_ca'])) or '(không có)'}.")
    return tool_result(_dem_va_gon(tho["bang"], tham,
                                   {"nguon": nguon, "loai": ten_loai, "ten": tho["ten"],
                                    "ly_do_duoc_doc": vi_sao}))


def register() -> None:
    try:
        registry.register(
            name="dem_bang", toolset="lark_api", schema=SCHEMA, handler=_handle,
            check_fn=lambda: True, requires_env=[], is_async=False,
            description="Đếm, tính % và cộng tổng trên Base/Sheet của Lark bằng code",
            emoji="\U0001f522", override=True,
        )
    except Exception as e:
        print(f"[dem_bang_tool] register warning: {e}")


register()
