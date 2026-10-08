"""Lớp TRÌNH BÀY chung cho mọi Lark Sheet Mark xuất (08/10/2026).

Vấn đề chủ agent nêu: sheet xuất ra "thô, không khoa học" — ghi giá trị trần, không tiêu
đề, không cố định dòng tiêu đề, không định dạng số/tiền/%/ngày, cột rộng mặc định. Module
này để tool MÔ TẢ bảng (cột + kiểu) còn việc dựng sheet, ghi, trang trí, kiểm lại nằm một
chỗ:

- Tab "Tổng quan" đầu tiên: tiêu đề (gộp ô, đậm, chữ lớn), một dòng siêu dữ liệu (nguồn,
  khoảng thời gian, phạm vi, người yêu cầu, giờ tạo VN), khối số liệu chính (CHỈ số tool
  đã tự tính — lớp này không tự cộng), khối đếm theo nhóm (đếm bằng code từ chính các dòng),
  top-N theo cột chỉ số có sẵn, mục lục tab (tên | số dòng | mô tả, bấm được), dòng KIỂM
  GHI ("Đã ghi đủ N/N dòng, M cột"), bảng nhỏ gấp vào, ghi chú.
- Mỗi bảng một tab dữ liệu: tiêu đề cột nền xanh navy chữ trắng đậm, cố định dòng 1, bật
  bộ lọc trên vùng tiêu đề + dữ liệu, định dạng số theo kiểu cột, cột mã giữ dạng chữ, dòng
  tổng (nếu tool có) đậm nền xám nhạt, cách dữ liệu một dòng trống.
- Bố cục do `ke_hoach` (hàm THUẦN, cùng đầu vào → cùng bố cục) quyết theo hình dạng dữ
  liệu: BAO_CAO / DANH_SACH / NHIEU_BANG / LON; bảng tí hon gấp vào Tổng quan; bảng vượt
  trần ô của một tab tách "phần"; quá 10 tab dữ liệu thì sang bảng tính tiếp theo.
- Không bao giờ âm thầm mất dữ liệu: ô dài hơn trần ký tự chảy sang cột "(tiếp)"; tool chỉ
  lấy một phần trường của bản ghi nguồn thì thêm tab "Dữ liệu gốc" (mọi trường, làm
  phẳng); ghi xong đọc lại từng tab (`kiem_ghi`) — lệch thì `day_du=False` kèm câu nói thiếu
  gì, không đọc lại được thì `day_du=None` ("chưa kiểm được"), không bao giờ tự nhận đủ.

THỨ TỰ GHI (dữ liệu đúng > đẹp): tạo bảng tính → `sau_khi_tao(tok)` (vd chi_so_ads khoá
chia sẻ link/tenant TRƯỚC khi có số) → thêm tab → nới lưới → đặt định dạng số trước (để ngày
ghi được thành ngày thật; hỏng thì ngày ghi dạng chữ dd/MM/yyyy) → GHI DỮ LIỆU → trang trí
(hỏng chỉ cảnh báo) → đọc lại kiểm → Tổng quan → `cap_quyen(tok)`. Mọi bước trang trí bắt lỗi
và in cảnh báo; bước ghi dữ liệu lỗi thì ném như cũ. Ô chữ vẫn qua `apify_tool._bang_an_toan`
(chặn chèn công thức) vì mọi lần ghi đi qua `apify_tool._write_values`.

API Lark Sheets đã đối chiếu tài liệu chính thức (bản markdown của open.feishu.cn, đọc
08/10/2026; Lark dùng cùng đường dẫn trên open.larksuite.com):
- Tạo bảng tính  POST /open-apis/sheets/v3/spreadsheets
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet/create.md
- Danh sách tab + lưới (row_count/column_count)  GET .../sheets/v3/spreadsheets/:t/sheets/query
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet/query.md
- Thêm tab (addSheet{properties{title,index}})  POST .../sheets/v2/spreadsheets/:t/sheets_batch_update
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet/operate-sheets.md
- Đổi tên / cố định dòng (updateSheet{properties{sheetId,title,index,frozenRowCount}}) cùng URL;
  tên tab ≤100 ký tự, không chứa / \\ ? * [ ] :
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet/update-sheet-properties.md
- Ghi nhiều vùng  POST .../sheets/v2/spreadsheets/:t/values_batch_update — ≤5000 dòng, ≤100 cột
  mỗi lần; ô ≤50.000 ký tự (khuyên ≤40.000)
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/write-data-to-multiple-ranges.md
- Kiểu giá trị ghi được (chuỗi, số, link {text,link,type:url}, ngày = số ngày từ 1899-12-30 +
  định dạng ngày đặt TRƯỚC)
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-types-supported-by-sheets.md
- Định dạng số hỗ trợ (@, #,##0, #,##0.00, 0.00%, yyyy/MM/dd, yyyy/MM/dd HH:mm:ss …)
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-formats-supported-by-sheets.md
- Kiểu ô hàng loạt  PUT .../sheets/v2/spreadsheets/:t/styles_batch_update {data:[{ranges,style:{
  font{bold,italic,fontSize:"10pt/1.5"},formatter,hAlign 0/1/2,vAlign,foreColor,backColor,
  borderType,borderColor}}]} — mỗi vùng ≤5000 dòng ≤100 cột; ô nằm ở nhiều vùng thì nhận
  kiểu của vùng cuối (nên các vùng ở đây KHÔNG chồng nhau). API không có tuỳ chọn xuống dòng.
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/batch-set-cell-style.md
- Độ rộng cột  PUT .../sheets/v2/spreadsheets/:t/dimension_range {dimension{sheetId,
  majorDimension,startIndex,endIndex (từ 1, gồm hai đầu)},dimensionProperties{fixedSize}}
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/sheet-rowcol/update-rows-or-columns.md
- Thêm dòng/cột  POST .../dimension_range {dimension{sheetId,majorDimension,length ≤5000}}
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/sheet-rowcol/add-rows-or-columns.md
- Gộp ô  POST .../sheets/v2/spreadsheets/:t/merge_cells {range,mergeType:MERGE_ALL}
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/merge-cells.md
- Bộ lọc  POST .../sheets/v3/spreadsheets/:t/sheets/:sheet_id/filter {range,col,condition{
  filter_type}} — 20 lần/phút; mỗi tab một vùng lọc; "clear" = cột không có điều kiện
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet-filter/create.md
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet-filter/filter-user-guide.md
- Đọc lại  GET .../sheets/v2/spreadsheets/:t/values_batch_get?ranges=a,b
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/reading-multiple-ranges.md
- Trần chung: ≤300 tab/bảng tính, ≤13.000 cột và ≤5.000.000 ô (kể cả ô trống) mỗi tab.
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/overview.md
- Link tới một tab: URL bảng tính + "?sheet=<sheetId>" (cùng trang tổng quan).
"""
from __future__ import annotations

import collections
import dataclasses
import datetime
import decimal
import json
import re
import threading
import time
from typing import Any, Callable, Iterable

import apify_tool as A

VN = datetime.timezone(datetime.timedelta(hours=7))

# ───────────────────────── hằng số (trần đã đối chiếu tài liệu) ─────────────────────────
TRAN_KY_TU_O = 40_000          # khuyên ≤40.000 ký tự/ô (trần cứng 45.000–50.000)
TRAN_O_MOI_TAB = 4_000_000     # trần 5.000.000 ô/tab kể cả ô trống — chừa biên
TRAN_DONG_GHI = 1000           # dòng mỗi lần ghi (API cho 5000; giữ như code cũ)
TRAN_COT_GHI = 100             # cột mỗi lần ghi / mỗi vùng kiểu
TRAN_DONG_KIEU = 5000          # dòng mỗi vùng kiểu
TRAN_BYTE_GHI = 2_000_000      # ước lượng cỡ thân request mỗi lần ghi
TRAN_TAB_DU_LIEU = 10          # tab dữ liệu mỗi bảng tính; quá thì sang bảng tính tiếp
TRAN_TEN_TAB = 30
NGUONG_LON_DONG = 20_000       # bảng lớn: chỉ trang trí theo cột
NGUONG_LON_O = 1_000_000
NHO_DONG, NHO_COT = 5, 6       # bảng tí hon gấp vào Tổng quan
TRAN_VUNG_MOI_LAN = 200        # số vùng kiểu tối đa mỗi lần styles_batch_update

TAB_TONG_QUAN = "Tổng quan"
TAB_DU_LIEU = "Dữ liệu"
TAB_GOC = "Dữ liệu gốc"

NAVY, TRANG, XAM_TONG, CHU_TOI = "#1F3864", "#FFFFFF", "#E7E9EE", "#1F2A44"
VIEN = "#8C96A8"

BAO_CAO, DANH_SACH, NHIEU_BANG, LON = "BAO_CAO", "DANH_SACH", "NHIEU_BANG", "LON"

# Kiểu cột (tên Việt) + tên tiếng Anh đề bài dùng.
_BI_DANH = {"text": "chu", "long_text": "chu_dai", "int": "so_nguyen", "money": "tien",
            "decimal": "thap_phan", "percent": "phan_tram", "percent100": "phan_tram_100",
            "ratio": "ti_le", "date": "ngay", "datetime": "ngay_gio", "link": "link",
            "id": "ma"}
KIEU = {"chu", "chu_dai", "so_nguyen", "tien", "thap_phan", "phan_tram", "phan_tram_100",
        "ti_le", "ngay", "ngay_gio", "link", "ma"}
_KIEU_SO = {"so_nguyen", "tien", "thap_phan", "phan_tram", "phan_tram_100", "ti_le"}

# (định dạng ưa dùng, định dạng an toàn trong danh sách tài liệu) — ưa dùng hỏng thì lùi.
_DINH_DANG = {
    "so_nguyen": ("#,##0", "#,##0"),
    "thap_phan": ("#,##0.00", "#,##0.00"),
    "ti_le": ("0.00", "#,##0.00"),
    "phan_tram": ("0.00%", "0.00%"),           # giá trị là PHÂN SỐ (0.1234 → 12.34%)
    "phan_tram_100": ('0.00"%"', "#,##0.00"),  # giá trị ĐÃ nhân 100 (12.34 → 12.34%)
    "ngay": ("dd/MM/yyyy", "yyyy/MM/dd"),
    "ngay_gio": ("dd/MM/yyyy HH:mm", "yyyy/MM/dd HH:mm:ss"),
    "ma": ("@", "@"),
}
_CAN = {"so_nguyen": 2, "tien": 2, "thap_phan": 2, "phan_tram": 2, "phan_tram_100": 2,
        "ti_le": 2, "ngay": 1, "ngay_gio": 1}
_RONG = {"ma": 140, "chu": 180, "chu_dai": 320, "link": 240, "ngay": 100, "ngay_gio": 130}
_RONG_SO = 110


def _dinh_dang_tien(tien_te: str | None, an_toan: bool) -> str:
    t = str(tien_te or "").strip().upper()
    if t == "VND":
        return "#,##0" if an_toan else '#,##0 "₫"'
    return "#,##0.00"


# ───────────────────────── mô tả bảng ─────────────────────────
@dataclasses.dataclass
class Cot:
    """Một cột. `kieu` ∈ KIEU (hoặc tên tiếng Anh). Tiền: `tien_te` cố định cho cả cột, hoặc
    `cot_tien_te` = tên cột chứa mã tiền của TỪNG dòng (vd chi_so_ads nhiều tài khoản)."""
    ten: str
    kieu: str = "chu"
    tien_te: str | None = None
    cot_tien_te: str | None = None
    rong: int | None = None

    def __post_init__(self):
        self.kieu = _BI_DANH.get(self.kieu, self.kieu)
        if self.kieu not in KIEU:
            raise ValueError(f"kiểu cột lạ: {self.kieu}")


@dataclasses.dataclass
class Bang:
    """Một bảng dữ liệu = một tab. `dong` KHÔNG gồm tiêu đề. `dong_tong` = các dòng tổng tool
    đã tự tính (ghi dưới dữ liệu, cách một dòng trống, đậm nền xám, ngoài vùng lọc)."""
    ten: str
    cot: list
    dong: list
    dong_tong: list = dataclasses.field(default_factory=list)
    mo_ta: str = ""
    gap_duoc: bool = True       # được gấp vào Tổng quan khi tí hon

    def __post_init__(self):
        self.cot = [c if isinstance(c, Cot) else Cot(*c) if isinstance(c, (tuple, list))
                    else Cot(str(c)) for c in self.cot]
        self.dong = [list(r) for r in (self.dong or [])]
        self.dong_tong = [list(r) for r in (self.dong_tong or [])]


@dataclasses.dataclass
class SoLieu:
    """Một con số chính ở Tổng quan — giá trị PHẢI là số tool đã tự tính."""
    nhan: str
    gia_tri: Any
    kieu: str = "chu"
    tien_te: str | None = None
    ghi_chu: str = ""

    def __post_init__(self):
        self.kieu = _BI_DANH.get(self.kieu, self.kieu)


@dataclasses.dataclass
class Nhom:
    """Khối đếm theo nhóm (đếm bằng code từ chính các dòng — dùng `dem_theo`)."""
    ten: str
    dong: list                  # [(giá trị nhóm, số dòng)]
    tong: int | None = None


@dataclasses.dataclass
class TongQuan:
    tieu_de: str
    nguon: str = ""                       # tool / nguồn số liệu
    thoi_gian: str = ""                   # khoảng thời gian
    pham_vi: str = ""                     # tài khoản / từ khoá / nền tảng
    nguoi_yeu_cau: str = ""
    so_lieu: list = dataclasses.field(default_factory=list)       # [SoLieu]
    nhom: list = dataclasses.field(default_factory=list)          # [Nhom]
    top: Bang | None = None                                       # top-N (cột có sẵn)
    ghi_chu: list = dataclasses.field(default_factory=list)       # [str]


# ───────────────────────── trợ thủ thuần ─────────────────────────
def dem_theo(bang: Bang, ten_cot: str, ten: str | None = None, toi_da: int = 30) -> Nhom:
    """Đếm số dòng theo giá trị của một cột có sẵn (ô trống → "(trống)"). Sắp giảm dần theo
    số, hoà thì theo tên — tất định."""
    i = [c.ten for c in bang.cot].index(ten_cot)
    dem = collections.Counter(str(r[i]).strip() if i < len(r) and str(r[i]).strip() else "(trống)"
                              for r in bang.dong)
    dong = sorted(dem.items(), key=lambda x: (-x[1], x[0]))
    if len(dong) > toi_da:
        khac = sum(n for _, n in dong[toi_da - 1:])
        dong = dong[:toi_da - 1] + [(f"(khác — {len(dem) - toi_da + 1} nhóm)", khac)]
    return Nhom(ten or f"Theo {ten_cot}", dong, len(bang.dong))


def top_theo(bang: Bang, ten_cot: str, n: int = 5, cot_hien: Iterable[str] | None = None,
             ten: str | None = None) -> Bang | None:
    """Top-N dòng theo một cột SỐ có sẵn (giảm dần; ô không phải số bỏ qua). None nếu cột
    không có hoặc không dòng nào có số."""
    ten_cac = [c.ten for c in bang.cot]
    if ten_cot not in ten_cac:
        return None
    i = ten_cac.index(ten_cot)
    co_so = [(r, r[i]) for r in bang.dong if i < len(r) and _la_so(r[i])]
    if not co_so:
        return None
    co_so.sort(key=lambda x: -float(x[1]))
    hien = [x for x in (cot_hien or ten_cac) if x in ten_cac]
    idx = [ten_cac.index(x) for x in hien]
    return Bang(ten or f"Top {n} theo {ten_cot}", [bang.cot[j] for j in idx],
                [[r[j] if j < len(r) else "" for j in idx] for r, _ in co_so[:n]])


def phang(obj: Any, tien_to: str = "") -> dict:
    """Làm phẳng một bản ghi nguồn: khoá lồng nối bằng ".", danh sách → JSON."""
    ra: dict = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            kk = f"{tien_to}.{k}" if tien_to else str(k)
            if isinstance(v, dict) and v:
                ra.update(phang(v, kk))
            else:
                ra[kk] = _gia_tri_goc(v)
    else:
        ra[tien_to or "gia_tri"] = _gia_tri_goc(obj)
    return ra


def _gia_tri_goc(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int) and abs(v) >= 10 ** 15:
        return str(v)                     # mã dài: số thực mất chữ số
    if isinstance(v, (int, float, str)):
        return v
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


_RE_MA = re.compile(r"(?i)(^|[._])(id|ids|pk|uid|code|ma)$|Id$")


def bang_goc(ban_ghi: list, ten: str = TAB_GOC,
             mo_ta: str = "Mọi trường của bản ghi nguồn (làm phẳng: khoá lồng nối bằng '.', "
                          "danh sách ở dạng JSON), cùng thứ tự dòng") -> Bang:
    """Bản ghi nguồn → bảng "Dữ liệu gốc" (hợp mọi khoá theo thứ tự gặp)."""
    phs = [phang(b) for b in ban_ghi]
    khoa: dict = {}
    for p in phs:
        for k in p:
            khoa.setdefault(k, None)
    # Độ rộng đồng loạt 140px: bảng gốc có thể vài trăm cột — một lời gọi dimension_range
    # thay vì một lời gọi cho mỗi cụm cột khác độ rộng.
    cot = [Cot(k, "ma" if _RE_MA.search(k) else "chu", rong=140) for k in khoa]
    dong = [[p.get(k, "") for k in khoa] for p in phs]
    return Bang(ten, cot, dong, mo_ta=mo_ta, gap_duoc=False)


def _la_so(v) -> bool:
    return isinstance(v, (int, float, decimal.Decimal)) and not isinstance(v, bool)


def ten_tab_sach(ten: str, da_co: Iterable[str] = ()) -> str:
    """Tên tab hợp lệ: bỏ / \\ ? * [ ] :, gộp khoảng trắng, ≤30 ký tự, không trùng."""
    t = re.sub(r"[/\\?*\[\]:]", " ", str(ten or "")).strip()
    t = re.sub(r"\s+", " ", t)[:TRAN_TEN_TAB].strip() or "Tab"
    da = {x.lower() for x in da_co}
    goc, k = t, 2
    while t.lower() in da:
        hau = f" ({k})"
        t = goc[:TRAN_TEN_TAB - len(hau)].rstrip() + hau
        k += 1
    return t


# ───────────────────────── kế hoạch bố cục (hàm thuần) ─────────────────────────
@dataclasses.dataclass
class TabKH:
    ten: str
    bang: Bang
    phan: tuple | None = None     # (k, tổng số phần) khi bảng bị tách
    dau: int = 0                  # chỉ số dòng đầu (trong bang.dong) của phần này
    cuoi: int = 0

    @property
    def dong(self) -> list:
        return self.bang.dong[self.dau:self.cuoi]

    @property
    def co_tong(self) -> bool:
        return bool(self.bang.dong_tong) and (self.phan is None or self.phan[0] == self.phan[1])


@dataclasses.dataclass
class KeHoach:
    loai: str
    bang_tinh: list               # [[TabKH]] — mỗi phần tử một bảng tính
    gap: list                     # bảng tí hon gấp vào Tổng quan
    lon: bool


def ke_hoach(bang: list, tong_quan: TongQuan | None = None, goc: Bang | None = None) -> KeHoach:
    """Bố cục theo HÌNH DẠNG dữ liệu, không phụ thuộc thời gian/mạng (cùng vào → cùng ra).

    - LON: bảng nào > NGUONG_LON_DONG dòng hoặc > NGUONG_LON_O ô → chỉ trang trí theo cột.
    - NHIEU_BANG: ≥2 tab dữ liệu (sau khi gấp bảng tí hon).
    - BAO_CAO: một bảng có dòng tổng, hoặc Tổng quan có số liệu chính.
    - DANH_SACH: còn lại.
    Bảng tí hon (≤5 dòng, ≤6 cột, `gap_duoc`) gấp vào Tổng quan chỉ khi còn bảng khác.
    Một bảng → tab "Dữ liệu"; nhiều bảng → "1. Tên", "2. Tên"… "Dữ liệu gốc" luôn cuối.
    Bảng vượt TRAN_O_MOI_TAB tách thành "(phần k của n)" ("/" không hợp lệ trong tên tab). Quá TRAN_TAB_DU_LIEU tab dữ liệu thì
    các tab sau sang bảng tính tiếp theo."""
    bang = [b for b in bang if b is not None]
    lon = any(len(b.dong) > NGUONG_LON_DONG or len(b.dong) * max(1, len(b.cot)) > NGUONG_LON_O
              for b in bang + ([goc] if goc else []))
    gap: list = []
    giu = list(bang)
    if len(bang) > 1:
        gap = [b for b in bang if b.gap_duoc and len(b.dong) <= NHO_DONG
               and len(b.cot) <= NHO_COT and not b.dong_tong]
        if len(gap) == len(bang):          # đừng gấp hết: bảng lớn nhất vẫn có tab riêng
            gap = gap[1:]
        giu = [b for b in bang if not any(b is g for g in gap)]
    nhieu = len(giu) > 1
    tabs: list = []
    da: list = []
    for i, b in enumerate(giu, 1):
        goc_ten = f"{i}. {b.ten}" if nhieu else TAB_DU_LIEU
        tabs += _tach(b, goc_ten, da)
    if goc is not None:
        tabs += _tach(goc, TAB_GOC, da)
    bang_tinh = [tabs[i:i + TRAN_TAB_DU_LIEU] for i in range(0, len(tabs), TRAN_TAB_DU_LIEU)] \
        or [[]]
    if lon:
        loai = LON
    elif nhieu:
        loai = NHIEU_BANG
    elif (giu and giu[0].dong_tong) or (tong_quan and tong_quan.so_lieu):
        loai = BAO_CAO
    else:
        loai = DANH_SACH
    return KeHoach(loai, bang_tinh, gap, lon)


def _so_dong_moi_phan(b: Bang) -> int:
    return max(1, TRAN_O_MOI_TAB // max(len(b.cot), 20) - 1 - len(b.dong_tong) - 1)


def _tach(b: Bang, ten: str, da: list) -> list:
    n = _so_dong_moi_phan(b)
    if len(b.dong) <= n:
        t = ten_tab_sach(ten, da)
        da.append(t)
        return [TabKH(t, b, None, 0, len(b.dong))]
    so = -(-len(b.dong) // n)
    ra = []
    for k in range(so):
        hau = f" (phần {k + 1} của {so})"
        t = ten_tab_sach(ten[:TRAN_TEN_TAB - len(hau)].rstrip() + hau, da)
        da.append(t)
        ra.append(TabKH(t, b, (k + 1, so), k * n, min(len(b.dong), (k + 1) * n)))
    return ra


# ───────────────────────── chuẩn hoá ô ─────────────────────────
_RE_NGAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?"
                      r"(Z|[+-]\d{2}:?\d{2})?)?$")
_GOC_NGAY = datetime.datetime(1899, 12, 30)


def _doc_ngay(v) -> datetime.datetime | None:
    if isinstance(v, datetime.datetime):
        if v.tzinfo is not None:
            v = v.astimezone(VN).replace(tzinfo=None)
        return v
    if isinstance(v, datetime.date):
        return datetime.datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        m = _RE_NGAY.match(v.strip())
        if not m:
            return None
        y, mo, d, h, mi, s, tz = m.groups()
        try:
            dt = datetime.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0),
                                   int(s or 0))
        except ValueError:
            return None
        if tz:
            off = datetime.timezone.utc if tz == "Z" else datetime.timezone(
                datetime.timedelta(hours=int(tz[:3]), minutes=int(tz[0] + tz[-2:])))
            dt = dt.replace(tzinfo=off).astimezone(VN).replace(tzinfo=None)
        return dt
    return None


def _o(v, kieu: str, ngay_that: bool):
    """Một ô theo kiểu cột. Chỉ đổi những gì chắc chắn: số không bao giờ đoán từ chuỗi."""
    if v is None:
        return ""
    if kieu == "ma":
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return str(v)
    if kieu in _KIEU_SO:
        if isinstance(v, decimal.Decimal):
            return float(v)
        return v
    if kieu in ("ngay", "ngay_gio"):
        dt = _doc_ngay(v)
        if dt is None:
            return v
        if ngay_that:
            so = (dt - _GOC_NGAY).total_seconds() / 86400
            return round(so, 6) if kieu == "ngay_gio" else int(so)
        return dt.strftime("%d/%m/%Y %H:%M" if kieu == "ngay_gio" else "%d/%m/%Y")
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def _chia_o_dai(b_cot: list, dong: list) -> tuple[list, list, list]:
    """Ô chữ dài hơn TRAN_KY_TU_O → chảy sang cột "(tiếp)" ngay sau. -> (cột mới, dòng mới,
    bản đồ cột mới → cột gốc)."""
    can: dict = {}
    for r in dong:
        for j, v in enumerate(r):
            if isinstance(v, str) and len(v) > TRAN_KY_TU_O:
                can[j] = max(can.get(j, 1), -(-len(v) // TRAN_KY_TU_O))
    if not can:
        return b_cot, dong, list(range(len(b_cot)))
    cot, ban_do = [], []
    for j, c in enumerate(b_cot):
        cot.append(c)
        ban_do.append(j)
        for k in range(1, can.get(j, 1)):
            cot.append(Cot(f"{c.ten} (tiếp{'' if k == 1 else ' ' + str(k)})", "chu_dai"))
            ban_do.append(j)
    moi = []
    for r in dong:
        o = []
        for j in range(len(b_cot)):
            v = r[j] if j < len(r) else ""
            n = can.get(j, 1)
            if n > 1:
                s = v if isinstance(v, str) else ("" if v is None else str(v))
                o += [s[k * TRAN_KY_TU_O:(k + 1) * TRAN_KY_TU_O] for k in range(n)]
            else:
                o.append(v)
        moi.append(o)
    return cot, moi, ban_do


# ───────────────────────── gọi Lark ─────────────────────────
def _goi(method: str, path: str, **kw) -> dict:
    """Mọi lời gọi đi qua `apify_tool.lark.call` (bộ thử giả được một chỗ), có lùi khi 429."""
    lan = 0
    while True:
        try:
            return A.lark.call(method, path, **kw) or {}
        except RuntimeError as e:
            if lan < 3 and re.search(r"(?i)\b429\b|frequency|too many|rate.?limit|90217", str(e)):
                time.sleep(min(8.0, 1.0 * 2 ** lan))
                lan += 1
                continue
            raise


def _canh(canh_bao: list, viec: str, e: Exception) -> None:
    cau = f"{viec} hỏng (bỏ qua, dữ liệu vẫn đủ): {A._che_token(e)[:160]}"
    canh_bao.append(cau)
    print(f"[trinh_bay_sheet] {cau}", flush=True)


def _them_tab(tok: str, ten: str, vi_tri: int | None) -> str:
    p: dict = {"title": ten}
    if vi_tri is not None:
        p["index"] = vi_tri
    d = _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{tok}/sheets_batch_update",
             body={"requests": [{"addSheet": {"properties": p}}]})
    replies = (d.get("data") or {}).get("replies") or []
    sid = ((replies[0].get("addSheet") or {}).get("properties") or {}).get("sheetId") \
        if replies and isinstance(replies[0], dict) else ""
    if not sid:
        raise RuntimeError("Lark không trả sheetId cho tab mới.")
    return sid


def _luoi(tok: str) -> dict:
    """{sheet_id: (số dòng lưới, số cột lưới)}; {} nếu không đọc được."""
    try:
        r = _goi("GET", f"/open-apis/sheets/v3/spreadsheets/{tok}/sheets/query")
    except Exception:  # noqa: BLE001
        return {}
    ra = {}
    for sh in ((r or {}).get("data") or {}).get("sheets") or []:
        g = sh.get("grid_properties") or {}
        if sh.get("sheet_id"):
            ra[sh["sheet_id"]] = (int(g.get("row_count") or 0), int(g.get("column_count") or 0))
    return ra


def _noi_luoi(tok: str, sid: str, co: tuple, can_dong: int, can_cot: int) -> None:
    """Nới lưới tab đủ `can_dong` × `can_cot` (POST dimension_range, ≤5000 mỗi lần)."""
    dong, cot = co
    if not dong and not cot:
        return                                   # không biết lưới → để Lark tự nới khi ghi
    for chieu, hien, can in (("ROWS", dong, can_dong), ("COLUMNS", cot, can_cot)):
        while hien and hien < can:
            n = min(5000, can - hien)
            _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{tok}/dimension_range",
                 body={"dimension": {"sheetId": sid, "majorDimension": chieu, "length": n}})
            hien += n


def _bo_cot_thua(tok: str, sid: str, luoi_cot: int, can: int, cb: list) -> None:
    """Xoá cột lưới trống bên phải cột `can` khi đã biết số cột lưới (không hỏi lại Lark).
    DELETE dimension_range: từ 1, gồm hai đầu (như `apify_tool._vua_cot`)."""
    if not luoi_cot or luoi_cot <= can:
        return
    try:
        _goi("DELETE", f"/open-apis/sheets/v2/spreadsheets/{tok}/dimension_range",
             body={"dimension": {"sheetId": sid, "majorDimension": "COLUMNS",
                                 "startIndex": can + 1, "endIndex": luoi_cot}})
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Bỏ cột trống thừa", e)


def _ghi(tok: str, sid: str, values: list, dong_dau: int = 1) -> None:
    """Ghi theo khối ≤TRAN_DONG_GHI dòng / ≤TRAN_BYTE_GHI / ≤TRAN_COT_GHI cột, qua
    `apify_tool._write_values` (chặn chèn công thức)."""
    if not values:
        return
    rong = max(len(r) for r in values)
    values = [list(r) + [""] * (rong - len(r)) for r in values]
    i = 0
    while i < len(values):
        j, byte = i, 0
        while j < len(values) and j - i < TRAN_DONG_GHI:
            byte += len(json.dumps(values[j], ensure_ascii=False, default=str).encode("utf-8"))
            if byte > TRAN_BYTE_GHI and j > i:
                break
            j += 1
        for c0 in range(0, rong, TRAN_COT_GHI):
            khoi = [r[c0:c0 + TRAN_COT_GHI] for r in values[i:j]]
            if c0 == 0:
                A._write_values(tok, sid, khoi, dong_dau=dong_dau + i)
            else:
                A._write_values(tok, sid, khoi, dong_dau=dong_dau + i, cot_dau=c0 + 1)
        i = j


def _vung(sid: str, c1: int, r1: int, c2: int, r2: int) -> list:
    """Vùng A1 cho cột c1..c2, dòng r1..r2 (1-based), cắt theo ≤5000 dòng, ≤100 cột."""
    ra = []
    for a in range(r1, r2 + 1, TRAN_DONG_KIEU):
        b = min(r2, a + TRAN_DONG_KIEU - 1)
        for x in range(c1, c2 + 1, TRAN_COT_GHI):
            y = min(c2, x + TRAN_COT_GHI - 1)
            ra.append(f"{sid}!{A._cot(x)}{a}:{A._cot(y)}{b}")
    return ra


def _kieu(tok: str, muc: list) -> None:
    """muc = [(vùng, style)] → styles_batch_update: gộp vùng cùng style, ≤TRAN_VUNG_MOI_LAN
    vùng mỗi lần gọi. Ném lỗi để bên gọi quyết lùi/cảnh báo."""
    if not muc:
        return
    gom: dict = {}
    for vung, st in muc:
        gom.setdefault(json.dumps(st, sort_keys=True, ensure_ascii=False), []).append(vung)
    lo: list = []
    dem = 0
    for k, vungs in gom.items():
        for i in range(0, len(vungs), TRAN_VUNG_MOI_LAN):
            phan = vungs[i:i + TRAN_VUNG_MOI_LAN]
            if lo and dem + len(phan) > TRAN_VUNG_MOI_LAN:
                _goi("PUT", f"/open-apis/sheets/v2/spreadsheets/{tok}/styles_batch_update",
                     body={"data": lo})
                lo, dem = [], 0
            lo.append({"ranges": phan, "style": json.loads(k)})
            dem += len(phan)
    if lo:
        _goi("PUT", f"/open-apis/sheets/v2/spreadsheets/{tok}/styles_batch_update",
             body={"data": lo})


def _an_toan_muc(muc: list) -> list:
    return [(v, dict(st, formatter=_an_toan(st["formatter"])) if "formatter" in st else st)
            for v, st in muc]


def _style_so(kieu: str, an_toan: bool, tien_te: str | None = None) -> dict | None:
    if kieu == "tien":
        fmt = _dinh_dang_tien(tien_te, an_toan)
    elif kieu in _DINH_DANG:
        fmt = _DINH_DANG[kieu][1 if an_toan else 0]
    else:
        return None
    st = {"formatter": fmt}
    if kieu in _CAN:
        st["hAlign"] = _CAN[kieu]
    return st


def _muc_dinh_dang(sid: str, cot: list, dong: list, r1: int, an_toan: bool,
                   ngay: bool = True) -> list:
    """Định dạng số cho vùng dữ liệu dòng r1..r1+len(dong)-1 (theo cột, không chồng nhau)."""
    if not dong:
        return []
    r2 = r1 + len(dong) - 1
    ten = [c.ten for c in cot]
    muc = []
    for j, c in enumerate(cot, 1):
        if c.kieu in ("ngay", "ngay_gio") and not ngay:
            continue
        if c.kieu == "tien" and c.cot_tien_te and c.cot_tien_te in ten:
            k = ten.index(c.cot_tien_te)
            ma = [str(r[k] if k < len(r) else "") for r in dong]
            so_cum = 1 + sum(1 for i in range(1, len(ma)) if ma[i] != ma[i - 1])
            if so_cum > TRAN_VUNG_MOI_LAN or len(set(ma)) == 1:   # một mã / quá vụn
                st = _style_so("tien", an_toan, ma[0] if len(set(ma)) == 1 else "")
                muc += [(v, st) for v in _vung(sid, j, r1, j, r2)]
                continue
            a = 0
            while a < len(dong):            # gom dòng liền nhau cùng mã tiền
                tt = str(dong[a][k] if k < len(dong[a]) else "")
                b = a
                while b + 1 < len(dong) and str(dong[b + 1][k] if k < len(dong[b + 1])
                                                else "") == tt:
                    b += 1
                st = _style_so("tien", an_toan, tt)
                muc += [(v, st) for v in _vung(sid, j, r1 + a, j, r1 + b)]
                a = b + 1
            continue
        st = _style_so(c.kieu, an_toan, c.tien_te)
        if st:
            muc += [(v, st) for v in _vung(sid, j, r1, j, r2)]
    return muc


def _rong_cot(c: Cot, mau: list, j: int) -> int:
    if c.rong:
        return int(c.rong)
    co_ban = _RONG.get(c.kieu, _RONG_SO if c.kieu in _KIEU_SO else 180)
    tieu_de = min(320, len(c.ten) * 8 + 24)
    rong = max(co_ban, tieu_de)
    if c.kieu in ("chu", "link"):
        dai = sorted(len(str(r[j])) for r in mau if j < len(r) and r[j] not in ("", None))
        if dai:
            p90 = dai[min(len(dai) - 1, int(len(dai) * 0.9))]
            rong = max(rong, min(320, p90 * 7 + 16))
    # Làm tròn lên vài mức cố định: cột kề nhau cùng mức gộp được một lời gọi
    # dimension_range (mỗi lời gọi một vùng; tài liệu: gọi tuần tự trên một bảng tính).
    return next((m for m in _MUC_RONG if m >= rong), _MUC_RONG[-1])


_MUC_RONG = (60, 100, 110, 140, 180, 240, 320, 360)


def _dat_rong(tok: str, sid: str, rong: list) -> None:
    """PUT dimension_range theo cụm cột liền nhau cùng độ rộng (từ 1, gồm hai đầu)."""
    j = 0
    while j < len(rong):
        k = j
        while k + 1 < len(rong) and rong[k + 1] == rong[j]:
            k += 1
        _goi("PUT", f"/open-apis/sheets/v2/spreadsheets/{tok}/dimension_range",
             body={"dimension": {"sheetId": sid, "majorDimension": "COLUMNS",
                                 "startIndex": j + 1, "endIndex": k + 1},
                   "dimensionProperties": {"fixedSize": int(rong[j])}})
        j = k + 1


# Bộ lọc: 20 lần/phút/ứng dụng — vượt thì BỎ (không chờ), cảnh báo.
_LOC_LUOT: collections.deque = collections.deque()
_LOC_KHOA = threading.Lock()
_LOC_DIEU_KIEN = [{"filter_type": "clear"},
                  {"filter_type": "text", "compare_type": "notContains", "expected": ["⁣"]}]


def _bat_loc(tok: str, sid: str, vung: str) -> None:
    with _LOC_KHOA:
        now = time.monotonic()
        while _LOC_LUOT and now - _LOC_LUOT[0] > 60:
            _LOC_LUOT.popleft()
        if len(_LOC_LUOT) >= 18:
            raise RuntimeError("đã gần trần 20 lần/phút của API bộ lọc")
        _LOC_LUOT.append(now)
    duong = f"/open-apis/sheets/v3/spreadsheets/{tok}/sheets/{sid}/filter"
    loi = None
    for lan in range(2):
        for dk in list(_LOC_DIEU_KIEN):
            try:
                _goi("POST", duong, body={"range": vung, "col": "A", "condition": dk})
                if dk is not _LOC_DIEU_KIEN[0]:          # nhớ dạng chạy được cho lần sau
                    _LOC_DIEU_KIEN.remove(dk)
                    _LOC_DIEU_KIEN.insert(0, dk)
                return
            except Exception as e:  # noqa: BLE001
                loi = e
        if lan == 0:
            # Mỗi tab chỉ MỘT vùng lọc: tab đã có lọc (vd ghi nối thêm dòng) → xoá rồi tạo lại
            # trên vùng mới. Xoá hỏng (chưa có lọc) thì thôi.
            try:
                _goi("DELETE", duong)
            except Exception:  # noqa: BLE001
                break
    raise loi  # type: ignore[misc]


_ST_TIEU_DE = {"font": {"bold": True}, "foreColor": TRANG, "backColor": NAVY,
               "hAlign": 1, "vAlign": 1, "borderType": "FULL_BORDER", "borderColor": NAVY}


def _st_tong(kieu_so: dict | None) -> dict:
    st = {"font": {"bold": True}, "backColor": XAM_TONG, "borderType": "TOP_BORDER",
          "borderColor": VIEN}
    if kieu_so:
        st.update(kieu_so)
    return st


# ───────────────────────── trang trí một tab dữ liệu ─────────────────────────
@dataclasses.dataclass
class TabDaGhi:
    ten: str
    sheet_id: str
    cot: list
    so_dong: int                  # dòng dữ liệu (không gồm tiêu đề, dòng tổng)
    so_cot: int
    dong_tong: int = 0
    mo_ta: str = ""
    noi_duoi: str | None = None   # ghi dưới tab khác vì thêm tab hỏng
    dong_dau: int = 1             # dòng tiêu đề của bảng trong tab
    kiem: str = ""                # "du" | "thieu" | "chua_kiem"
    cau_kiem: str = ""


def trang_tri_bang(tok: str, sid: str, cot: list, so_dong: int, so_tong: int = 0,
                   dinh_dang_xong: bool = False, mau: list | None = None,
                   canh_bao: list | None = None, dong_dau: int = 1, rieng_tab: bool = True,
                   tong: list | None = None, an_toan: bool = False) -> None:
    """Trang trí một bảng đã GHI XONG: tiêu đề, dòng tổng, định dạng số (nếu chưa đặt trước),
    cố định dòng 1, độ rộng, bộ lọc. Mọi bước bắt lỗi riêng → cảnh báo, không bao giờ ném.

    `rieng_tab`=False: bảng nằm dưới bảng khác trong cùng tab (thêm tab hỏng) — chỉ tô
    tiêu đề/dòng tổng/định dạng, không cố định, không lọc, không đổi độ rộng.
    Dùng trực tiếp cho bảng ghi dần (sheet_lon): gọi lại sau khi ghi xong."""
    cb = canh_bao if canh_bao is not None else []
    n = max(1, len(cot))
    r1 = dong_dau + 1
    muc = [(v, _ST_TIEU_DE) for v in _vung(sid, 1, dong_dau, n, dong_dau)]
    if not dinh_dang_xong and so_dong:
        dong = mau if mau is not None and len(mau) == so_dong else [[""] * n] * so_dong
        muc += _muc_dinh_dang(sid, cot, dong, r1, an_toan=True, ngay=False)
    if so_tong:
        r_t = r1 + so_dong + 1
        dong_t = tong if tong and len(tong) == so_tong else [[""] * n] * so_tong
        ten = [x.ten for x in cot]
        for j, c in enumerate(cot, 1):
            if c.kieu in ("ngay", "ngay_gio"):
                muc += [(v, _st_tong(None)) for v in _vung(sid, j, r_t, j, r_t + so_tong - 1)]
            elif c.kieu == "tien" and c.cot_tien_te in ten:
                k = ten.index(c.cot_tien_te)
                for i, r in enumerate(dong_t):
                    tt = r[k] if k < len(r) else ""
                    muc += [(v, _st_tong(_style_so("tien", an_toan, tt)))
                            for v in _vung(sid, j, r_t + i, j, r_t + i)]
            else:
                st = _st_tong(_style_so(c.kieu, an_toan, c.tien_te))
                muc += [(v, st) for v in _vung(sid, j, r_t, j, r_t + so_tong - 1)]
    for lan, m in enumerate((muc, _an_toan_muc(muc),
                             [(v, _ST_TIEU_DE) for v in _vung(sid, 1, dong_dau, n, dong_dau)])):
        try:
            _kieu(tok, m)
            break
        except Exception as e:  # noqa: BLE001 — lùi: định dạng an toàn, rồi chỉ tiêu đề
            if lan == 2:
                _canh(cb, "Tô tiêu đề/dòng tổng", e)
    if not rieng_tab:
        return
    try:
        _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{tok}/sheets_batch_update",
             body={"requests": [{"updateSheet": {"properties": {
                 "sheetId": sid, "frozenRowCount": 1}}}]})
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Cố định dòng tiêu đề", e)
    try:
        m = (mau or [])[:500]
        _dat_rong(tok, sid, [_rong_cot(c, m, j) for j, c in enumerate(cot)])
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Đặt độ rộng cột", e)
    if so_dong:
        try:
            _bat_loc(tok, sid, f"{sid}!A{dong_dau}:{A._cot(n)}{dong_dau + so_dong}")
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Bật bộ lọc", e)


# ───────────────────────── Tổng quan ─────────────────────────
def _so_vn(v) -> str:
    return f"{v:,}".replace(",", ".") if isinstance(v, int) else str(v)


def dung_tong_quan(tq: TongQuan, tabs: list, gap: list, kiem: dict | None = None,
                   url: str = "", luc: datetime.datetime | None = None,
                   bang_tinh_khac: list | None = None) -> tuple[list, dict]:
    """Dựng các dòng tab Tổng quan (thuần). -> (dòng, vai trò) với vai trò =
    {"tieu_de": r, "meta": r, "muc": [r], "dau_bang": [(r, số cột)], "so": [(r, c, kiểu, tiền tệ)],
    "rong": số cột}."""
    luc = luc or datetime.datetime.now(VN)
    dong: list = []
    vai: dict = {"muc": [], "dau_bang": [], "so": [], "link": []}

    def them(r):
        dong.append(list(r))
        return len(dong)

    vai["tieu_de"] = them([tq.tieu_de])
    meta = [x for x in (
        f"Nguồn: {tq.nguon}" if tq.nguon else "",
        f"Thời gian: {tq.thoi_gian}" if tq.thoi_gian else "",
        f"Phạm vi: {tq.pham_vi}" if tq.pham_vi else "",
        f"Người yêu cầu: {tq.nguoi_yeu_cau}" if tq.nguoi_yeu_cau else "",
        f"Tạo lúc: {luc.astimezone(VN):%d/%m/%Y %H:%M} (giờ VN)") if x]
    vai["meta"] = them([" · ".join(meta)])
    if kiem and kiem.get("cau"):
        vai["kiem"] = them([kiem["cau"]])
    them([])

    if tq.so_lieu:
        vai["muc"].append(them(["SỐ LIỆU CHÍNH"]))
        vai["dau_bang"].append((them(["Chỉ số", "Giá trị", "Ghi chú"]), 3))
        for s in tq.so_lieu:
            gt = s.gia_tri
            if s.kieu in ("ngay", "ngay_gio"):
                gt = _o(gt, s.kieu, False)
            elif isinstance(gt, decimal.Decimal):
                gt = float(gt)
            r = them([s.nhan, "" if gt is None else gt, s.ghi_chu])
            if s.kieu in _KIEU_SO and _la_so(gt):
                vai["so"].append((r, 2, s.kieu, s.tien_te))
        them([])

    for g in tq.nhom:
        vai["muc"].append(them([g.ten.upper()]))
        vai["dau_bang"].append((them(["Nhóm", "Số dòng", "Tỉ lệ"]), 3))
        tong = g.tong if g.tong else sum(n for _, n in g.dong)
        for k, n in g.dong:
            r = them([k, n, (n / tong) if tong else ""])
            vai["so"].append((r, 2, "so_nguyen", None))
            if tong:
                vai["so"].append((r, 3, "phan_tram", None))
        them([])

    def khoi_bang(b: Bang, nhan: str):
        vai["muc"].append(them([nhan.upper()]))
        vai["dau_bang"].append((them([c.ten for c in b.cot]), len(b.cot)))
        for r in b.dong + b.dong_tong:
            rr = them([_o(r[j] if j < len(r) else "", c.kieu, False)
                       for j, c in enumerate(b.cot)])
            for j, c in enumerate(b.cot, 1):
                if c.kieu in _KIEU_SO:
                    vai["so"].append((rr, j, c.kieu, c.tien_te))
        them([])

    if tq.top is not None and tq.top.dong:
        khoi_bang(tq.top, tq.top.ten)

    if tabs:
        vai["muc"].append(them(["MỤC LỤC"]))
        vai["dau_bang"].append((them(["Tab", "Số dòng", "Số cột", "Nội dung"]), 4))
        for t in tabs:
            ten = t.ten if not t.noi_duoi else f"{t.ten} (ghi dưới tab {t.noi_duoi})"
            o_ten: Any = ten
            if url and t.sheet_id and not t.noi_duoi:
                o_ten = {"text": ten, "link": _link_tab(url, t.sheet_id), "type": "url"}
                vai["link"].append(len(dong) + 1)
            r = them([o_ten, t.so_dong, t.so_cot, t.mo_ta])
            vai["so"].append((r, 2, "so_nguyen", None))
            vai["so"].append((r, 3, "so_nguyen", None))
        for u in bang_tinh_khac or []:
            them([f"Phần tiếp theo: {u}", "", "", "Quá nhiều tab — phần còn lại ở bảng tính này"])
        them([])

    if kiem and kiem.get("tabs"):
        vai["muc"].append(them(["KIỂM GHI"]))
        vai["dau_bang"].append((them(["Tab", "Kết quả"]), 2))
        for k in kiem["tabs"]:
            them([k["tab"], k["cau"]])
        them([])

    for b in gap:
        khoi_bang(b, b.ten)

    if tq.ghi_chu:
        vai["muc"].append(them(["GHI CHÚ"]))
        for g in tq.ghi_chu:
            them([f"• {g}"])
    vai["rong"] = max(4, max((len(r) for r in dong), default=1))
    return dong, vai


def _link_tab(url: str, sid: str) -> str:
    return f"{url.split('?')[0].split('#')[0]}?sheet={sid}"


def _trang_tri_tong_quan(tok: str, sid: str, dong: list, vai: dict, cb: list) -> None:
    w = vai["rong"]
    muc = [(f"{sid}!A{vai['tieu_de']}:{A._cot(w)}{vai['tieu_de']}",
            {"font": {"bold": True, "fontSize": "16pt/1.5"}, "foreColor": CHU_TOI}),
           (f"{sid}!A{vai['meta']}:{A._cot(w)}{vai['meta']}",
            {"font": {"italic": True}, "foreColor": "#555F6D"})]
    if vai.get("kiem"):
        muc.append((f"{sid}!A{vai['kiem']}:{A._cot(w)}{vai['kiem']}",
                    {"font": {"bold": True}, "foreColor": CHU_TOI}))
    for r in vai["muc"]:
        muc.append((f"{sid}!A{r}:{A._cot(w)}{r}", {"font": {"bold": True},
                                                    "foreColor": TRANG, "backColor": NAVY}))
    for r, n in vai["dau_bang"]:
        muc.append((f"{sid}!A{r}:{A._cot(max(n, 1))}{r}",
                    {"font": {"bold": True}, "backColor": XAM_TONG, "foreColor": CHU_TOI}))
    for r, c, kieu, tt in vai["so"]:
        st = _style_so(kieu, False, tt)
        if st:
            muc.append((f"{sid}!{A._cot(c)}{r}:{A._cot(c)}{r}", st))
    try:
        _kieu(tok, muc)
    except Exception:  # noqa: BLE001 — định dạng ưa dùng bị từ chối → lùi định dạng an toàn
        try:
            _kieu(tok, _an_toan_muc(muc))
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Tô tab Tổng quan", e)
    for r in (vai["tieu_de"], vai["meta"]) + ((vai["kiem"],) if vai.get("kiem") else ()):
        try:
            _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{tok}/merge_cells",
                 body={"range": f"{sid}!A{r}:{A._cot(w)}{r}", "mergeType": "MERGE_ALL"})
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Gộp ô tiêu đề", e)
            break
    try:
        _dat_rong(tok, sid, [260, 160, 120, 360] + [140] * (w - 4))
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Đặt độ rộng Tổng quan", e)


def _an_toan(fmt: str) -> str:
    for kieu, (ua, an) in _DINH_DANG.items():
        if fmt == ua:
            return an
    return "#,##0" if "₫" in fmt else fmt


# ───────────────────────── kiểm ghi ─────────────────────────
def kiem_ghi(tok: str, tabs: list) -> dict:
    """Đọc lại từng tab: lưới đủ dòng/cột, dòng tiêu đề đủ ô, dòng dữ liệu CUỐI có chữ.
    -> {"day_du": True/False/None, "cau": str, "tabs": [{tab, du_kien, cot, ket, cau}]}."""
    luoi = _luoi(tok)
    ranges = []
    for t in tabs:
        if t.noi_duoi:
            continue
        w = A._cot(max(1, t.so_cot))
        ranges.append(f"{t.sheet_id}!A{t.dong_dau}:{w}{t.dong_dau}")
        if t.so_dong:
            r = t.dong_dau + t.so_dong
            ranges.append(f"{t.sheet_id}!A{r}:{w}{r}")
    doc: dict = {}
    try:
        if ranges:
            d = _goi("GET", f"/open-apis/sheets/v2/spreadsheets/{tok}/values_batch_get",
                     query={"ranges": ",".join(ranges), "valueRenderOption": "ToString"})
            for vr in ((d or {}).get("data") or {}).get("valueRanges") or []:
                rg = str(vr.get("range") or "")
                doc[rg] = vr.get("values") or []
    except Exception:  # noqa: BLE001
        doc = {}
    ket_tabs = []
    for t in tabs:
        w = A._cot(max(1, t.so_cot))
        if t.noi_duoi:
            ket, cau = None, f"ghi dưới tab {t.noi_duoi} (thêm tab hỏng) — chưa kiểm riêng"
        else:
            r_cuoi = t.dong_dau + t.so_dong
            dau = _tim(doc, t.sheet_id, f"A{t.dong_dau}", f"{w}{t.dong_dau}")
            cuoi = _tim(doc, t.sheet_id, f"A{r_cuoi}", f"{w}{r_cuoi}") if t.so_dong else []
            lo = luoi.get(t.sheet_id)
            if dau is None or (t.so_dong and cuoi is None):
                ket = None
            else:
                du_dau = _dem_o(dau) >= sum(1 for c in t.cot if c.ten)
                du_cuoi = (not t.so_dong) or _dem_o(cuoi) >= 1
                du_luoi = lo is None or (lo[0] >= r_cuoi and lo[1] >= t.so_cot)
                ket = du_dau and du_cuoi and du_luoi
            if ket is True:
                cau = f"Đã ghi đủ {_so_vn(t.so_dong)}/{_so_vn(t.so_dong)} dòng, {t.so_cot} cột"
            elif ket is False:
                cau = (f"THIẾU: đọc lại không thấy đủ {_so_vn(t.so_dong)} dòng × {t.so_cot} cột "
                       f"(tiêu đề {'đủ' if du_dau else 'thiếu'}, dòng cuối "
                       f"{'có' if du_cuoi else 'trống'})")
            else:
                cau = (f"Đã gửi {_so_vn(t.so_dong)} dòng, {t.so_cot} cột — chưa đọc lại được "
                       f"để kiểm")
        t.kiem = {True: "du", False: "thieu", None: "chua_kiem"}[ket]
        t.cau_kiem = cau
        ket_tabs.append({"tab": t.ten, "du_kien": t.so_dong, "cot": t.so_cot,
                         "ket": t.kiem, "cau": cau})
    kets = [k["ket"] for k in ket_tabs]
    if any(k == "thieu" for k in kets):
        day_du = False
    elif kets and all(k == "du" for k in kets):
        day_du = True
    else:
        day_du = None
    tong_dong = sum(k["du_kien"] for k in ket_tabs)
    if day_du is True:
        cau = (f"Đã ghi đủ {_so_vn(tong_dong)}/{_so_vn(tong_dong)} dòng ở {len(ket_tabs)} tab "
               "dữ liệu (đã đọc lại kiểm).")
    elif day_du is False:
        cau = ("CẢNH BÁO GHI THIẾU: " + "; ".join(f"{k['tab']}: {k['cau']}" for k in ket_tabs
                                                if k["ket"] == "thieu") + ".")
    else:
        cau = (f"Đã gửi {_so_vn(tong_dong)} dòng ở {len(ket_tabs)} tab dữ liệu; chưa đọc lại "
               "được để kiểm đủ.")
    return {"day_du": day_du, "cau": cau, "tabs": ket_tabs}


def _tim(doc: dict, sid: str, a: str, b: str):
    for k in (f"{sid}!{a}:{b}", f"{sid}!{a}"):
        if k in doc:
            return doc[k]
    for k, v in doc.items():                 # Lark có thể trả vùng đã thu gọn
        if k.startswith(f"{sid}!{a}:") or k == f"{sid}!{a}":
            return v
    return None


def _dem_o(values) -> int:
    if not values:
        return 0
    return sum(1 for v in (values[0] or []) if v not in (None, ""))


# ───────────────────────── dựng cả bảng tính ─────────────────────────
@dataclasses.dataclass
class KetQua:
    url: str
    token: str
    urls: list
    tabs: list
    kiem: dict
    canh_bao: list
    loai: str
    tong_quan_sid: str = ""       # sheet_id tab Tổng quan (bảng tính đầu; "" nếu thêm hỏng)
    tong_quan: TongQuan | None = None

    @property
    def day_du(self):
        return self.kiem.get("day_du")

    @property
    def cau_kiem(self) -> str:
        return self.kiem.get("cau") or ""

    def cho_tool(self) -> dict:
        """Trường gắn vào tool_result: Mark chép NGUYÊN `kiem_ghi` khi gửi link."""
        return {"day_du": self.day_du, "kiem_ghi": self.cau_kiem,
                "bang_tinh_tiep": self.urls[1:] or None}


def xuat(tieu_de: str, bang: list, tong_quan: TongQuan | None = None, goc: Bang | None = None,
         sau_khi_tao: Callable[[str], Any] | None = None,
         cap_quyen: Callable[[str], Any] | None = None,
         luc: datetime.datetime | None = None) -> KetQua:
    """MỘT lời gọi dựng cả bảng tính (xem docstring module cho thứ tự). Lỗi tạo bảng tính /
    ghi dữ liệu / callback thì NÉM (như code cũ); lỗi trang trí chỉ cảnh báo."""
    tq = tong_quan or TongQuan(tieu_de)
    if not tq.nguoi_yeu_cau:
        tq = dataclasses.replace(tq, nguoi_yeu_cau=_ten_nguoi_yeu_cau())
    kh = ke_hoach(bang, tq, goc)
    urls, tok_dau, cac_tab, cb = [], "", [], []
    kiem_tong: dict = {"day_du": True, "cau": "", "tabs": []}
    so_bt = len(kh.bang_tinh)
    ket_bt = []
    for k, tabs in enumerate(kh.bang_tinh):
        td = tieu_de if so_bt == 1 else f"{tieu_de} (phần {k + 1}/{so_bt})"
        tok, url, da_ghi, kiem = _xuat_mot(td, tabs, kh, sau_khi_tao, cb)
        urls.append(url)
        ket_bt.append((tok, url, da_ghi, kiem, td))
        tok_dau = tok_dau or tok
        cac_tab += da_ghi
    # Kiểm tổng các bảng tính
    kets = [kq[3]["day_du"] for kq in ket_bt]
    if any(x is False for x in kets):
        dd = False
    elif all(x is True for x in kets):
        dd = True
    else:
        dd = None
    kiem_tong = {"day_du": dd, "tabs": [t for kq in ket_bt for t in kq[3]["tabs"]],
                 "cau": " ".join(kq[3]["cau"] for kq in ket_bt) if len(ket_bt) > 1
                 else ket_bt[0][3]["cau"]}
    tq_sid = ""
    for i, (tok, url, da_ghi, kiem, td) in enumerate(ket_bt):
        tq_i = dataclasses.replace(tq, tieu_de=td)
        sid = _ghi_tong_quan(tok, url, tq_i, da_ghi, kh.gap if i == 0 else [], kiem, cb, luc,
                             urls[1:] if i == 0 else [])
        tq_sid = tq_sid or (sid if i == 0 else "")
        if cap_quyen:
            cap_quyen(tok)
    return KetQua(urls[0], tok_dau, urls, cac_tab, kiem_tong, cb, kh.loai, tq_sid or "", tq)


def _ten_nguoi_yeu_cau() -> str:
    """Tên hiển thị người hỏi của lượt (dòng siêu dữ liệu) — KHÔNG ghi open_id. Hỏng/không
    có lượt → "". Bộ thử thay hàm này (conftest) để không đọc bộ nhớ tên thật."""
    try:
        import memory_store
        oid = memory_store.get_current_sender()
        return (A.lark.resolve_user_name(oid) or "") if oid else ""
    except Exception:  # noqa: BLE001
        return ""


def _xuat_mot(tieu_de: str, tabs: list, kh: KeHoach, sau_khi_tao, cb: list):
    tok, url = A._create_sheet(tieu_de)
    try:
        return _xuat_mot_tiep(tok, url, tabs, kh, sau_khi_tao, cb)
    except BaseException as e:
        # Bảng tính ĐÃ tạo nhưng chưa ghi đủ: gắn link vào lỗi để tool nói rõ (không gửi
        # như bản đủ). Không bọc lỗi mới — bên gọi vẫn thấy đúng loại lỗi.
        try:
            e.trinh_bay_url, e.trinh_bay_token = url, tok
        except Exception:  # noqa: BLE001
            pass
        raise


def _xuat_mot_tiep(tok: str, url: str, tabs: list, kh: KeHoach, sau_khi_tao, cb: list):
    if sau_khi_tao:
        sau_khi_tao(tok)
    sid0 = A._first_sheet_id(tok)
    da_ghi: list = []
    if not tabs:
        return tok, url, da_ghi, {"day_du": True, "cau": "Không có bảng dữ liệu.", "tabs": []}
    # 1) tab: tab dữ liệu đầu dùng tab sẵn có (luôn tồn tại — dữ liệu không phụ thuộc
    #    addSheet); tab sau thêm ở đúng vị trí. Thêm hỏng → ghi dưới tab đầu, có dòng ngăn.
    sids: list = []
    for i, t in enumerate(tabs):
        if i == 0:
            sids.append(sid0)
            continue
        try:
            sids.append(_them_tab(tok, t.ten, i))
        except Exception as e:  # noqa: BLE001
            _canh(cb, f"Thêm tab '{t.ten}'", e)
            sids.append(None)
    luoi = _luoi(tok)
    # 2) chuẩn bị bảng (ô dài → cột tiếp) + vị trí ghi
    ke: list = []
    dong_noi = 0     # số dòng đã dùng ở tab đầu (để ghi nối dưới)
    for i, t in enumerate(tabs):
        cot, dong, _ = _chia_o_dai(t.bang.cot, t.dong)
        tong = t.bang.dong_tong if t.co_tong else []
        if tong:
            cot2, tong, _ = _chia_o_dai(t.bang.cot, tong)
            if len(cot2) != len(cot):                       # hiếm: đồng bộ cột tiếp
                cot, dong, _ = _chia_o_dai(t.bang.cot, t.dong + t.bang.dong_tong)
                dong, tong = dong[:len(t.dong)], dong[len(t.dong):]
        if sids[i] is None:
            sid, dd, noi = sid0, dong_noi + 3, tabs[0].ten
        else:
            sid, dd, noi = sids[i], 1, None
        so_dong_tab = 1 + len(dong) + ((1 + len(tong)) if tong else 0)
        if sid == sid0:
            dong_noi = max(dong_noi, dd - 1 + so_dong_tab)
        ke.append((t, sid, dd, noi, cot, dong, tong))
    # 3) nới lưới (dòng/cột) trước khi đặt định dạng và ghi
    can: dict = {}
    for t, sid, dd, noi, cot, dong, tong in ke:
        r = dd - 1 + 1 + len(dong) + ((1 + len(tong)) if tong else 0)
        a, b = can.get(sid, (0, 0))
        can[sid] = (max(a, r), max(b, len(cot)))
    for sid, (r, c) in can.items():
        try:
            _noi_luoi(tok, sid, luoi.get(sid, (0, 0)), r, c)
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Nới lưới", e)       # Lark thường tự nới khi ghi; lỗi thật lộ ở bước ghi
    # 4) định dạng số TRƯỚC khi ghi (để ngày là ngày thật). Định dạng ưa dùng bị từ chối
    #    thì lùi bộ định dạng an toàn (đúng danh sách tài liệu); vẫn hỏng → ngày ghi dạng chữ.
    muc_a = []
    for t, sid, dd, noi, cot, dong, tong in ke:
        if noi is None:
            muc_a += _muc_dinh_dang(sid, cot, dong, dd + 1, an_toan=False)
    dinh_dang_xong, an_toan = False, False
    if muc_a:
        for an_toan in (False, True):
            try:
                _kieu(tok, _an_toan_muc(muc_a) if an_toan else muc_a)
                dinh_dang_xong = True
                break
            except Exception as e:  # noqa: BLE001
                if an_toan:
                    _canh(cb, "Đặt định dạng số trước khi ghi", e)
    # 5) GHI DỮ LIỆU (lỗi → ném, như code cũ)
    for t, sid, dd, noi, cot, dong, tong in ke:
        ngay_that = dinh_dang_xong and noi is None
        vals = [[c.ten for c in cot]] + [
            [_o(r[j] if j < len(r) else "", c.kieu, ngay_that) for j, c in enumerate(cot)]
            for r in dong]
        if tong:
            vals += [[""] * len(cot)] + [
                [_o(r[j] if j < len(r) else "", c.kieu, False) for j, c in enumerate(cot)]
                for r in tong]
        if noi is not None:
            vals = [[f"— {t.ten} — (không thêm được tab riêng)"] + [""] * (len(cot) - 1)] + vals
            _ghi(tok, sid, vals, dong_dau=dd - 1)
        else:
            _ghi(tok, sid, vals, dong_dau=dd)
        da_ghi.append(TabDaGhi(t.ten, sid if noi is None else sid0, cot, len(dong), len(cot),
                               len(tong), t.bang.mo_ta + (f" (phần {t.phan[0]}/{t.phan[1]})"
                                                          if t.phan else ""),
                               noi, dd))
    # 6) trang trí (cảnh báo nếu hỏng)
    try:
        reqs = [{"updateSheet": {"properties": {"sheetId": sid0, "title": tabs[0].ten}}}]
        _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{tok}/sheets_batch_update",
             body={"requests": reqs})
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Đặt tên tab dữ liệu đầu", e)
    for (t, sid, dd, noi, cot, dong, tong), tg in zip(ke, da_ghi):
        trang_tri_bang(tok, tg.sheet_id, cot, len(dong), len(tong),
                       dinh_dang_xong=dinh_dang_xong and noi is None, mau=dong,
                       canh_bao=cb, dong_dau=dd, rieng_tab=noi is None, tong=tong,
                       an_toan=an_toan or not dinh_dang_xong)
    for sid, (_, c) in can.items():          # bỏ cột lưới trống bên phải (lưới mặc định 20)
        _bo_cot_thua(tok, sid, luoi.get(sid, (0, 0))[1], c, cb)
    # 7) đọc lại kiểm
    kiem = kiem_ghi(tok, da_ghi)
    return tok, url, da_ghi, kiem


def _ghi_tong_quan(tok, url, tq, da_ghi, gap, kiem, cb, luc, khac) -> str:
    """Thêm tab Tổng quan ở vị trí 0, ghi + trang trí. Hỏng → cảnh báo (dữ liệu đã đủ).
    -> sheet_id của tab ("" nếu không thêm được)."""
    try:
        sid = _them_tab(tok, TAB_TONG_QUAN, 0)
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Thêm tab Tổng quan", e)
        return ""
    dong, vai = dung_tong_quan(tq, da_ghi, gap, kiem, url, luc, khac)
    rong = vai["rong"]
    vals = [list(r) + [""] * (rong - len(r)) for r in dong]
    try:
        _ghi(tok, sid, vals)
    except Exception:  # noqa: BLE001 — thử lại không có link (ô link bị từ chối)
        vals = [[(v.get("text") if isinstance(v, dict) else v) for v in r] for r in vals]
        try:
            _ghi(tok, sid, vals)
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Ghi tab Tổng quan", e)
            return sid
    _trang_tri_tong_quan(tok, sid, dong, vai, cb)
    _bo_cot_thua(tok, sid, 20, rong, cb)       # tab mới: lưới mặc định 20 cột
    return sid


def ghi_tong_quan_vao(tok: str, sid: str, url: str, tq: TongQuan, tabs: list,
                      kiem: dict | None = None, gap: list | None = None,
                      canh_bao: list | None = None, so_dong_cu: int = 0) -> int:
    """Ghi/ghi ĐÈ Tổng quan vào tab có sẵn (vd ghi nối thêm brand vào sheet của lượt).
    `so_dong_cu` = số dòng bản trước (xoá trắng phần thừa). -> số dòng đã ghi. Không ném."""
    cb = canh_bao if canh_bao is not None else []
    dong, vai = dung_tong_quan(tq, tabs, gap or [], kiem, url)
    rong = vai["rong"]
    vals = [list(r) + [""] * (rong - len(r)) for r in dong]
    vals += [[""] * rong for _ in range(max(0, so_dong_cu - len(vals)))]
    try:
        _ghi(tok, sid, vals)
    except Exception:  # noqa: BLE001 — thử lại không có ô link
        try:
            _ghi(tok, sid, [[(v.get("text") if isinstance(v, dict) else v) for v in r]
                            for r in vals])
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Ghi tab Tổng quan", e)
            return so_dong_cu
    if so_dong_cu:                # bỏ kiểu cũ (dòng mục đã dời chỗ) trước khi tô lại
        try:
            _kieu(tok, [(v, {"clean": True}) for v in _vung(sid, 1, 4, rong, len(vals))])
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Xoá kiểu cũ Tổng quan", e)
    _trang_tri_tong_quan(tok, sid, dong, vai, cb)
    return len(dong)
