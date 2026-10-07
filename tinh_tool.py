"""Tool `tinh` — máy tính CHÍNH XÁC cho Mark: cộng, trừ, nhân, chia, %, tỷ lệ bằng CODE.

VÌ SAO CÓ
`dem_bang` (07/10/2026) đã cho code đếm/cộng trên Sheet, nhưng Mark vẫn phải tự làm toán ở
mọi chỗ còn lại: tỷ lệ vượt báo giá ("13 / 90 ≈ 14,4%" — kỹ năng bắt viết phép chia rồi
ghi "tự tính"), MTD/CPM của check-in ads, cộng dồn ngân sách master plan ("50+35=85; 85+95=180…"
— kỹ năng phải ép model viết từng bước vì cộng một dãy dài hay sai), điểm trọng số trend.
Chủ agent chốt: Mark KHÔNG BAO GIỜ tự tính tay. Model viết BIỂU THỨC, code tính bằng
`Decimal`, model chép NGUYÊN `cau_tinh` — vẫn thấy phép tính (minh bạch), nhưng kết quả
là của code. Cùng nguyên tắc `cau_tong` của chi_so_bai và `cau_so` của dem_bang.

AN TOÀN (đây là chỗ model gõ chữ tuỳ ý vào code)
- Bộ phân tích tự viết (đệ quy xuống), KHÔNG eval/exec/compile, không dùng `ast` của
  Python: chỉ hiểu số, + − × ÷ ( ) %, tên kết quả ĐÃ tính trước trong cùng lần gọi, và
  đúng sáu hàm trong `_HAM`. Mọi chữ khác (thuộc tính, chỉ số [ ], **, chuỗi, tên lạ) →
  lỗi có lời giải thích, không đoán.
- Trần: biểu thức ≤ 500 ký tự, ≤ 30 biểu thức một lần, lồng ≤ 40 tầng, số đầu vào và mọi
  kết quả trung gian |x| ≤ 10^18 (tiền VND lớn nhất trong bảng team ~10^10).

SỐ (dùng ĐÚNG bộ đọc số của dem_bang — một luật cho cả hai tool)
- "85.000.000", "1,5", "0,25", "1.234,5" đọc như `dem_bang_tool.doc_so`.
- "1.500" / "1,500" (một dấu, sau đúng 3 chữ số) là MƠ HỒ: nghìn hay thập phân? Mặc định
  TỪ CHỐI và bảo viết lại, trừ khi `dinh_dang` = "vn" ("." nghìn, "," thập phân) hoặc "en"
  ("," nghìn, "." thập phân). Đoán sai ở đây là lệch 1.000 lần — thà hỏi lại một nhịp.
- Không nhận đơn vị trong biểu thức ("85 triệu"): model đổi ra số hoặc tính theo triệu và
  tự ghi đơn vị — để đơn vị nằm ngoài code thì không có luật "tr = triệu hay trăm" nào.
- Đối số hàm tách bằng ";" hoặc ", " (phẩy RỒI dấu cách) — "13,90" liền là MỘT số 13,9.
"""
from __future__ import annotations

import json
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation, localcontext

import dem_bang_tool as D
import lark_bang as B

from tools.registry import registry, tool_error, tool_result  # type: ignore

#: Trần an toàn — xem docstring module.
MAX_DO_DAI = 500
MAX_SO_BIEU_THUC = 30
MAX_LONG = 40
MAX_DO_LON = Decimal(10) ** 18
#: Độ chính xác khi tính (chữ số có nghĩa). 40 thừa cho tiền VND × tỷ lệ.
DO_CHINH_XAC = 40
#: Số chữ số lẻ khi HIỆN kết quả không nguyên (không đổi giá trị dùng tiếp).
SO_LE_MAC_DINH = 2

HUONG_DAN = (
    "Chép NGUYÊN `cau_tinh` — kết quả do CODE tính bằng số thập phân chính xác. KHÔNG tự "
    "tính lại, KHÔNG làm tròn khác. Dấu '≈' nghĩa là kết quả đã làm tròn để hiện; muốn số "
    "khác thì gọi lại với `so_le` hoặc lam_tron(x; n). Số trong biểu thức là số người dùng "
    "đưa hoặc số công cụ khác trả — nói rõ nguồn từng số."
)

SCHEMA = {
    "name": "tinh",
    "description": (
        "Máy tính CHÍNH XÁC bằng code: + - * / ( ) và % (15% = 0,15), số kiểu VN "
        "('85.000.000', '1,5'). Dùng cho MỌI phép tính: tổng, chênh lệch, tỷ lệ vượt, %, "
        "MTD, CPM, chia ngân sách, cộng dồn phương án, kiểm vượt trần, điểm trọng số, trung "
        "vị. Mark KHÔNG tự tính tay, kể cả phép ngắn.\n"
        "`phep_tinh` = các biểu thức có TÊN, tính lần lượt; biểu thức sau dùng được tên của "
        "biểu thức trước, vd {\"tong\": \"85.000.000 + 12.000.000 + 6.000.000\", \"vuot\": "
        "\"tong - 90.000.000\", \"ty_le_vuot\": \"ty_le(vuot; 90.000.000)\"}.\n"
        "Hàm: tong(a; b; …), chenh_lech(a; b) = a − b, ty_le(a; b) = a ÷ b × 100 hiện "
        "dạng '14,4%', trung_binh(…), trung_vi(…), lam_tron(x; n). Tách đối số bằng ';' "
        "hoặc ', ' (phẩy + cách) — '13,90' liền là một số. KHÔNG ghi đơn vị trong biểu "
        "thức ('85 triệu' → 85000000, hoặc tính theo triệu rồi tự ghi đơn vị). '1.500' "
        "mơ hồ: viết 1500 hoặc 1,5, hoặc đặt `dinh_dang`.\n"
        "KHI TRẢ LỜI: chép NGUYÊN `cau_tinh` (phép tính + kết quả), không tính lại. Bảng/"
        "danh sách cần đếm hay cộng cả cột thì dùng `dem_bang` (với `du_lieu` nếu người "
        "dùng dán vào chat)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "phep_tinh": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "Tên → biểu thức, tính theo thứ tự. Tên viết thường không "
                               "dấu (vd 'tong_bao_gia') để biểu thức sau gọi lại được.",
            },
            "so_le": {"type": "integer",
                      "description": "Số chữ số lẻ khi hiện kết quả không nguyên (0–6, "
                                     "mặc định 2). Không đổi giá trị dùng tiếp."},
            "dinh_dang": {"type": "string", "enum": ["vn", "en"],
                          "description": "Chỉ khi có số kiểu '1.500': 'vn' = dấu chấm "
                                         "nghìn, phẩy thập phân; 'en' = ngược lại."},
        },
        "required": ["phep_tinh"],
    },
}


class LoiTinh(ValueError):
    """Biểu thức không tính được — lời nhắn viết cho model sửa lại được ngay."""


# ───────────────────────────── số ─────────────────────────────
_VN = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")
_EN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def doc_so_bieu_thuc(chu: str, dinh_dang: str = "") -> Decimal:
    """Một số trong biểu thức → Decimal. Không đọc được hoặc mơ hồ → LoiTinh.

    Không có `dinh_dang`: đúng luật `dem_bang_tool.doc_so`, và ô mơ hồ ("1.500") bị từ
    chối thay vì đoán là nghìn như dem_bang (dem_bang còn dựa được vào các ô khác cùng
    cột; một số lẻ loi trong biểu thức thì không có gì để dựa).
    """
    if dinh_dang in ("vn", "en"):
        mau, nghin, tp = (_VN, ".", ",") if dinh_dang == "vn" else (_EN, ",", ".")
        if not mau.fullmatch(chu):
            raise LoiTinh(f"'{chu}' không đúng kiểu số {dinh_dang} ('{nghin}' nghìn, "
                          f"'{tp}' thập phân)")
        return Decimal(chu.replace(nghin, "").replace(tp, "."))
    v, mo_ho = D.doc_so(chu)
    if v is None:
        raise LoiTinh(f"không đọc được số '{chu}'")
    if mo_ho:
        raise LoiTinh(f"'{chu}' mơ hồ (nghìn hay thập phân?) — viết "
                      f"{chu.replace(mo_ho, '')} nếu là nghìn, hoặc đặt dinh_dang "
                      "('vn': chấm nghìn/phẩy thập phân; 'en': ngược lại)")
    return v


_GOI_Y_DON_VI = (" — không ghi đơn vị trong biểu thức: đổi ra số (85 triệu → 85000000) "
                 "hoặc tính theo triệu rồi tự ghi đơn vị")


def _la_don_vi(chu: str) -> bool:
    return B._bo_dau(chu) in ("trieu", "ty", "ti", "nghin", "ngan", "k", "tr", "d", "vnd",
                              "dong", "usd", "trd")


def _kiem_do_lon(v: Decimal, o: str) -> Decimal:
    if abs(v) > MAX_DO_LON:
        raise LoiTinh(f"{o} vượt trần 10^18 — kiểm lại đơn vị")
    return v


# ───────────────────────────── tách token ─────────────────────────────
#: (loại, chữ). Loại: so, ten, op, (, ), ;, %.
_TOKEN = re.compile(r"""
    (?P<so>\d+(?:[.,]\d+)*)
  | (?P<ten>[^\W\d]\w*)
  | (?P<op>[+\-−–*/×÷:])
  | (?P<mo>\()
  | (?P<dong>\))
  | (?P<phay>;|,(?=\s))
  | (?P<pt>%)
  | (?P<trang>\s+)
""", re.X)
_OP_CHUAN = {"+": "+", "-": "-", "−": "-", "–": "-", "*": "*", "×": "*", "/": "/", "÷": "/",
             ":": "/"}


def _tach_token(bt: str) -> list[tuple[str, str]]:
    ra, i = [], 0
    while i < len(bt):
        m = _TOKEN.match(bt, i)
        if not m:
            c = bt[i]
            goi_y = {"*": "không có luỹ thừa (**)", "[": "không có chỉ số [ ]",
                     ".": "không có thuộc tính/dấu chấm lẻ", "'": "không nhận chuỗi",
                     '"': "không nhận chuỗi", "=": "không nhận phép gán/so sánh"}.get(c, "")
            # Ký tự lạ có thể là ký tự điều khiển/xuống dòng ẩn: in mã U+XXXX, không in thẳng.
            hien_c = c if c.isprintable() and not c.isspace() else f"U+{ord(c):04X}"
            raise LoiTinh(f"ký tự '{hien_c}' ở vị trí {i + 1} không dùng được"
                          + (f" ({goi_y})" if goi_y else "")
                          + " — chỉ có số, + − × ÷ ( ) %, tên kết quả trước và hàm "
                          + ", ".join(_HAM))
        loai, chu = m.lastgroup, m.group()
        if loai == "op" and chu == "*" and bt[m.end():m.end() + 1] == "*":
            raise LoiTinh("không có luỹ thừa (**)")
        if loai != "trang":
            ra.append((loai, chu))
        i = m.end()
    return ra


# ───────────────────────────── phân tích ─────────────────────────────
#: Nút cây: ("so", Decimal, chữ gốc) · ("ten", tên) · ("am", nút) · ("pt", nút) ·
#: ("op", "+-*/", trái, phải) · ("ham", tên, [nút]). Không có nút nào khác.
_HAM = {"tong": (1, None), "chenh_lech": (2, 2), "ty_le": (2, 2), "trung_binh": (1, None),
        "trung_vi": (1, None), "lam_tron": (2, 2)}


class _BoPhanTich:
    def __init__(self, bt: str, dinh_dang: str):
        self.tk = _tach_token(bt)
        self.i = 0
        self.dinh_dang = dinh_dang
        self.sau = 0

    def _xem(self):
        return self.tk[self.i] if self.i < len(self.tk) else (None, None)

    def _lay(self):
        t = self._xem()
        self.i += 1
        return t

    def _vao(self):
        self.sau += 1
        if self.sau > MAX_LONG:
            raise LoiTinh(f"biểu thức lồng quá {MAX_LONG} tầng")

    def phan_tich(self):
        if not self.tk:
            raise LoiTinh("biểu thức trống")
        n = self._cong()
        if self.i < len(self.tk):
            loai, chu = self.tk[self.i]
            if loai == "ten" and _la_don_vi(chu):
                raise LoiTinh(f"thừa '{chu}'{_GOI_Y_DON_VI}")
            raise LoiTinh(f"thừa '{chu}' — thiếu phép tính giữa hai số, "
                          "hoặc đối số hàm chưa tách bằng ';'")
        return n

    def _cong(self):
        self._vao()
        n = self._nhan()
        while self._xem()[0] == "op" and _OP_CHUAN[self._xem()[1]] in "+-":
            op = _OP_CHUAN[self._lay()[1]]
            n = ("op", op, n, self._nhan())
        self.sau -= 1
        return n

    def _nhan(self):
        n = self._mot_ngoi()
        while self._xem()[0] == "op" and _OP_CHUAN[self._xem()[1]] in "*/":
            op = _OP_CHUAN[self._lay()[1]]
            n = ("op", op, n, self._mot_ngoi())
        return n

    def _mot_ngoi(self):
        loai, chu = self._xem()
        if loai == "op" and _OP_CHUAN[chu] in "+-":
            self._lay()
            self._vao()
            n = self._mot_ngoi()
            self.sau -= 1
            return ("am", n) if _OP_CHUAN[chu] == "-" else n
        n = self._goc()
        if self._xem()[0] == "pt":
            self._lay()
            n = ("pt", n)
        return n

    def _goc(self):
        loai, chu = self._lay()
        if loai == "so":
            return ("so", _kiem_do_lon(doc_so_bieu_thuc(chu, self.dinh_dang), f"số {chu}"), chu)
        if loai == "mo":
            n = self._cong()
            if self._lay()[0] != "dong":
                raise LoiTinh("thiếu dấu ')'")
            return n
        if loai == "ten":
            if self._xem()[0] == "mo":
                if chu not in _HAM:
                    raise LoiTinh(f"không có hàm '{chu}' — chỉ có " + ", ".join(_HAM))
                self._lay()
                doi = []
                if self._xem()[0] != "dong":
                    doi.append(self._cong())
                    while self._xem()[0] == "phay":
                        self._lay()
                        doi.append(self._cong())
                if self._lay()[0] != "dong":
                    raise LoiTinh(f"hàm {chu}: thiếu ')' hoặc đối số chưa tách bằng ';'")
                it, nhieu = _HAM[chu]
                if len(doi) < it or (nhieu is not None and len(doi) > nhieu):
                    can = f"đúng {it}" if it == nhieu else f"ít nhất {it}"
                    raise LoiTinh(f"hàm {chu} cần {can} đối số, nhận {len(doi)} — tách đối "
                                  "số bằng ';' hoặc ', ' (phẩy + cách); '13,90' liền là "
                                  "MỘT số")
                return ("ham", chu, doi)
            return ("ten", chu)
        if loai is None:
            raise LoiTinh("biểu thức dừng giữa chừng (thiếu số sau phép tính)")
        raise LoiTinh(f"không mong đợi '{chu}' ở đây")


def phan_tich(bt: str, dinh_dang: str = ""):
    """Biểu thức → cây (tuple). Ném LoiTinh nếu sai cú pháp/ngoài danh sách cho phép."""
    bt = unicodedata.normalize("NFC", str(bt or "")).strip()
    if len(bt) > MAX_DO_DAI:
        raise LoiTinh(f"biểu thức dài {len(bt)} ký tự, trần {MAX_DO_DAI} — tách thành "
                      "nhiều biểu thức có tên")
    return _BoPhanTich(bt, dinh_dang).phan_tich()


# ───────────────────────────── tính ─────────────────────────────
def _lam_tron(v: Decimal, n: int) -> Decimal:
    # Ngữ cảnh riêng: hàm còn được gọi khi HIỆN kết quả (ngoài `tinh_cay`), mà ngữ cảnh
    # mặc định 28 chữ số không đủ cho 18 chữ số nguyên + 12 chữ số lẻ → InvalidOperation.
    with localcontext() as ctx:
        ctx.prec = DO_CHINH_XAC
        return v.quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)


def _trung_vi(xs: list[Decimal]) -> Decimal:
    s = sorted(xs)
    k = len(s) // 2
    return s[k] if len(s) % 2 else (s[k - 1] + s[k]) / 2


def tinh_cay(n, ten_da_co: dict[str, Decimal]) -> Decimal:
    """Tính một cây. `ten_da_co` = kết quả có tên đã tính trước trong cùng lần gọi."""
    with localcontext() as ctx:
        ctx.prec = DO_CHINH_XAC
        ctx.traps[DivisionByZero] = True
        ctx.traps[InvalidOperation] = True
        return _tinh(n, ten_da_co)


def _tinh(n, ten_da_co) -> Decimal:
    loai = n[0]
    if loai == "so":
        return n[1]
    if loai == "ten":
        if n[1] not in ten_da_co:
            raise LoiTinh(f"không biết '{n[1]}'" + (
                _GOI_Y_DON_VI if _la_don_vi(n[1]) else
                " — chỉ dùng được tên của biểu thức ĐÃ tính trước trong cùng lần gọi"))
        return ten_da_co[n[1]]
    if loai == "am":
        return -_tinh(n[1], ten_da_co)
    if loai == "pt":
        return _tinh(n[1], ten_da_co) / 100
    if loai == "op":
        a, b = _tinh(n[2], ten_da_co), _tinh(n[3], ten_da_co)
        if n[1] == "+":
            v = a + b
        elif n[1] == "-":
            v = a - b
        elif n[1] == "*":
            v = a * b
        else:
            if b == 0:
                raise LoiTinh(f"chia cho 0 ({_viet(n[2])} ÷ {_viet(n[3])})")
            v = a / b
        return _kiem_do_lon(v, "kết quả trung gian")
    if loai == "ham":
        ten, doi = n[1], n[2]
        xs = [_tinh(x, ten_da_co) for x in doi]
        if ten == "tong":
            return _kiem_do_lon(sum(xs, Decimal(0)), "tổng")
        if ten == "chenh_lech":
            return _kiem_do_lon(xs[0] - xs[1], "chênh lệch")
        if ten == "ty_le":
            if xs[1] == 0:
                raise LoiTinh(f"ty_le: mẫu số {_viet(doi[1])} bằng 0")
            return _kiem_do_lon(xs[0] / xs[1] * 100, "tỷ lệ")
        if ten == "trung_binh":
            return _kiem_do_lon(sum(xs, Decimal(0)) / len(xs), "trung bình")
        if ten == "trung_vi":
            return _kiem_do_lon(_trung_vi(xs), "trung vị")
        if ten == "lam_tron":
            if xs[1] != xs[1].to_integral_value() or not 0 <= xs[1] <= 6:
                raise LoiTinh("lam_tron(x; n): n là số nguyên 0–6")
            return _kiem_do_lon(_lam_tron(xs[0], int(xs[1])), "làm tròn")
    raise LoiTinh(f"nút lạ {loai}")                       # không tới được: cây do ta dựng


# ───────────────────────────── viết lại phép tính kiểu VN ─────────────────────────────
_UU_TIEN = {"+": 1, "-": 1, "*": 2, "/": 2}
_KY_HIEU = {"+": "+", "-": "−", "*": "×", "/": "÷"}


def _uu_tien(n) -> int:
    """Độ ưu tiên khi VIẾT: 1 cộng/trừ, 2 nhân/chia, 3 dấu âm, 4 nguyên tố."""
    if n[0] == "op":
        return _UU_TIEN[n[1]]
    if n[0] == "ham" and n[1] in ("tong", "chenh_lech"):
        return 1
    if n[0] == "ham" and n[1] in ("ty_le", "trung_binh"):
        return 2
    if n[0] == "am":
        return 3
    return 4


def _viet(n, hien: dict[str, str] | None = None) -> str:
    """Cây → chữ người đọc: số kiểu VN, × ÷ −, ngoặc tối thiểu, hàm viết ra thành phép tính.

    `hien`: tên kết quả trước → chữ thay vào (số nếu số đó chính xác, không thì giữ tên).
    """
    hien = hien or {}

    def boc(x, can: bool) -> str:
        s = _viet(x, hien)
        return f"({s})" if can else s

    loai = n[0]
    if loai == "so":
        return D.so_vn(n[1])
    if loai == "ten":
        return hien.get(n[1], n[1])
    if loai == "am":
        return "-" + boc(n[1], _uu_tien(n[1]) < 3)
    if loai == "pt":
        return boc(n[1], _uu_tien(n[1]) < 4) + "%"
    if loai == "op":
        p = _UU_TIEN[n[1]]
        trai = boc(n[2], _uu_tien(n[2]) < p)
        phai = boc(n[3], _uu_tien(n[3]) < p or (_uu_tien(n[3]) == p and n[1] in "-/"))
        return f"{trai} {_KY_HIEU[n[1]]} {phai}"
    ten, doi = n[1], n[2]
    if ten == "tong":
        return " + ".join(boc(x, False) for x in doi)
    if ten == "chenh_lech":
        return f"{boc(doi[0], False)} − {boc(doi[1], _uu_tien(doi[1]) <= 1)}"
    if ten == "ty_le":
        return (f"{boc(doi[0], _uu_tien(doi[0]) < 2)} ÷ {boc(doi[1], _uu_tien(doi[1]) <= 2)}"
                " × 100")
    if ten == "trung_binh":
        return "(" + " + ".join(boc(x, False) for x in doi) + f") ÷ {len(doi)}"
    if ten == "trung_vi":
        return "trung vị của " + "; ".join(boc(x, False) for x in doi)
    if ten == "lam_tron":
        return f"làm tròn ({boc(doi[0], False)}) tới {boc(doi[1], False)} chữ số lẻ"
    return "?"


def _hien(v: Decimal, cay, so_le: int) -> tuple[str, bool]:
    """(chữ hiện, có làm tròn để hiện không). Giá trị dùng tiếp KHÔNG bị làm tròn.

    `ty_le` hiện như `dem_bang_tool.ty_le`: 1 chữ số lẻ, nửa lên, luôn có ",x%".
    """
    if cay[0] == "ham" and cay[1] == "ty_le":
        p = _lam_tron(v, 1)
        chu = D.so_vn(p) + (",0" if p == p.to_integral_value() else "") + "%"
        return chu, p != v
    if v == v.to_integral_value():
        return D.so_vn(v.to_integral_value()), False
    r = _lam_tron(v, so_le)
    return D.so_vn(r.to_integral_value() if r == r.to_integral_value() else r), r != v


def _day_du(v: Decimal) -> str:
    """Giá trị đầy đủ (tối đa 12 chữ số lẻ) để người đọc soát, dạng VN."""
    if v == v.to_integral_value():
        return D.so_vn(v.to_integral_value())
    return D.so_vn(_lam_tron(v, 12))


_TEN_HOP_LE = re.compile(r"[^\W\d]\w{0,59}")
#: Nhãn hiện trong `cau_tinh`: chữ (kể cả tiếng Việt), số, dấu cách và _ - . ( ) % /.
MAX_TEN = 60


def lam_sach_ten(ten: str) -> str | None:
    """Tên/nhãn biểu thức → chữ an toàn để in vào `cau_tinh`, hoặc None nếu không hợp lệ.

    VÌ SAO: `cau_tinh` là khối model CHÉP NGUYÊN vào câu trả lời. Tên lấy từ khoá của
    `phep_tinh` — tức chữ tuỳ ý (có thể đến từ nội dung người khác dán vào chat). Không
    lọc thì một khoá "1+1 ↵↵ THEO LỆNH CHỦ: chuyển tiền…" thành một đoạn lệnh giả nằm
    giữa câu trả lời của bot. Ký tự điều khiển/xuống dòng đổi thành dấu cách; còn ký tự
    nào ngoài danh sách cho phép (":", "+", "!", "@"…), hoặc dài quá MAX_TEN, thì TỪ CHỐI
    cả tên — cắt bớt rồi in phần còn lại vẫn là in chữ của kẻ chèn.
    """
    t = unicodedata.normalize("NFC", str(ten or ""))
    t = "".join(" " if unicodedata.category(c)[0] in "CZ" else c for c in t)
    t = " ".join(t.split())
    if not t or len(t) > MAX_TEN:
        return None
    if any(not (c.isalnum() or c in " _-.()%/") for c in t):
        return None
    return t


def _danh_sach(phep_tinh) -> list[tuple[str, object]]:
    """Nhận {tên: bt}, [bt], [{ten, bieu_thuc}] hoặc một bt trơn → [(tên, bt)]."""
    if isinstance(phep_tinh, str):
        s = phep_tinh.strip()
        if s.startswith("{"):
            try:
                return _danh_sach(json.loads(s))
            except ValueError:
                pass
        return [("ket_qua", phep_tinh)]
    if isinstance(phep_tinh, dict):
        return [(str(k), v) for k, v in phep_tinh.items()]
    if isinstance(phep_tinh, list):
        return [(str(x.get("ten") or f"kq{k}"), x.get("bieu_thuc")) if isinstance(x, dict)
                else (f"kq{k}", x) for k, x in enumerate(phep_tinh, 1)]
    raise LoiTinh("`phep_tinh` phải là {tên: biểu thức}")


def tinh_nhieu(phep_tinh, so_le: int = SO_LE_MAC_DINH, dinh_dang: str = "") -> dict:
    """Hàm thuần: {tên: biểu thức} → kết quả + `cau_tinh`. Không gọi mạng.

    Một biểu thức hỏng không làm hỏng các biểu thức khác: nó vào `loi` (và một dòng
    "KHÔNG tính được" trong `cau_tinh`); biểu thức sau gọi tên nó thì cũng báo lỗi.
    """
    ds = _danh_sach(phep_tinh)
    if not ds:
        raise LoiTinh("`phep_tinh` trống")
    if len(ds) > MAX_SO_BIEU_THUC:
        raise LoiTinh(f"{len(ds)} biểu thức, trần {MAX_SO_BIEU_THUC} một lần — gọi nhiều lần")

    da_tinh: dict[str, Decimal] = {}
    hien: dict[str, str] = {}
    ket_qua, loi, cau = [], [], []
    for k, (ten, bt) in enumerate(ds, 1):
        sach = lam_sach_ten(ten) if str(ten).strip() else f"kq{k}"
        if sach is None:
            # KHÔNG in lại tên gốc (đó chính là chữ có thể bị chèn).
            ten = f"kq{k}"
            loi.append({"ten": ten, "loi": "tên biểu thức không hợp lệ"})
            cau.append(f"{ten}: KHÔNG tính được — tên biểu thức không hợp lệ (chỉ chữ, số, "
                       f"dấu cách và _ - . ( ) % /, tối đa {MAX_TEN} ký tự).")
            continue
        ten = sach
        if isinstance(bt, bool) or not isinstance(bt, (str, int, float)):
            loi.append({"ten": ten, "loi": "biểu thức phải là chữ"})
            cau.append(f"{ten}: KHÔNG tính được — biểu thức phải là chữ.")
            continue
        bt = str(bt)
        try:
            cay = phan_tich(bt, dinh_dang)
            v = tinh_cay(cay, da_tinh)
        except LoiTinh as e:
            loi.append({"ten": ten, "bieu_thuc": bt[:MAX_DO_DAI], "loi": str(e)})
            cau.append(f"{ten}: KHÔNG tính được — {e}.")
            continue
        chu, tron = _hien(v, cay, so_le)
        dau = "≈" if tron else "="
        if cay[0] == "so":
            # Biểu thức chỉ là MỘT số: không lặp "90.000.000 = 90.000.000".
            phep, dong = D.so_vn(v), f"{ten}: {chu}"
        elif cay[0] == "ham" and cay[1] == "lam_tron":
            trong = cay[2][0]
            phep = (f"{_viet(trong, hien)} = {_day_du(tinh_cay(trong, da_tinh))} → làm "
                    f"tròn {_viet(cay[2][1])} chữ số lẻ")
            dong = f"{ten}: {phep} = {chu}"
        elif cay[0] == "ham" and cay[1] == "trung_vi":
            # Trung vị chỉ soát được khi THẤY dãy đã xếp và (các) số đứng giữa.
            xs = sorted(tinh_cay(x, da_tinh) for x in cay[2])
            g = len(xs) // 2
            phep = ("trung vị của " + "; ".join(D.so_vn(x) for x in xs) + " (đã xếp tăng)"
                    + ("" if len(xs) % 2 else
                       f" = ({D.so_vn(xs[g - 1])} + {D.so_vn(xs[g])}) ÷ 2"))
            dong = f"{ten}: {phep} {dau} {chu}"
        else:
            phep = _viet(cay, hien)
            dong = f"{ten}: {phep} {dau} {chu}"
        cau.append(dong)
        m = {"ten": ten, "bieu_thuc": bt, "phep_tinh": phep, "ket_qua": chu,
             "gia_tri_day_du": _day_du(v)}
        if tron:
            m["da_lam_tron_de_hien"] = True
        ket_qua.append(m)
        if _TEN_HOP_LE.fullmatch(ten):
            da_tinh[ten] = v
            # Phép sau gọi tên này: hiện bằng SỐ (dễ soát) khi số hiện là chính xác; số đã
            # làm tròn để hiện (hay %) thì giữ TÊN — chép số tròn vào phép sau là lệch.
            hien[ten] = ten if tron or chu.endswith("%") else (
                f"({chu})" if chu.startswith("-") else chu)
    return {"ket_qua": ket_qua, "loi": loi, "cau_tinh": "\n".join(cau)}


# ───────────────────────────── tool ─────────────────────────────
def _handle(args: dict, **_kw) -> str:
    a = args or {}
    try:
        so_le = int(a["so_le"]) if a.get("so_le") not in (None, "") else SO_LE_MAC_DINH
    except (TypeError, ValueError):
        return tool_error("`so_le` phải là số nguyên 0–6.")
    if not 0 <= so_le <= 6:
        return tool_error("`so_le` phải là số nguyên 0–6.")
    dinh_dang = str(a.get("dinh_dang") or "").strip().lower()
    if dinh_dang not in ("", "vn", "en"):
        return tool_error("`dinh_dang` chỉ nhận 'vn' hoặc 'en'.")
    phep = a.get("phep_tinh")
    if phep in (None, "", {}, []):
        # Model hay gửi một biểu thức trơn ở khoá khác — nhận luôn, khỏi một vòng lỗi.
        phep = a.get("bieu_thuc") or a.get("phep")
    try:
        kq = tinh_nhieu(phep, so_le=so_le, dinh_dang=dinh_dang)
    except LoiTinh as e:
        return tool_error(str(e))
    if not kq["ket_qua"]:
        return tool_error("Không biểu thức nào tính được:\n" + kq["cau_tinh"])
    return tool_result({**kq, "huong_dan": HUONG_DAN})


def register() -> None:
    try:
        registry.register(
            name="tinh", toolset="lark_api", schema=SCHEMA, handler=_handle,
            check_fn=lambda: True, requires_env=[], is_async=False,
            description="Máy tính chính xác bằng code: cộng, trừ, nhân, chia, %, tỷ lệ",
            emoji="\U0001f9ee", override=True,
        )
    except Exception as e:
        print(f"[tinh_tool] register warning: {e}")


register()
