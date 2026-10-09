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
  phẳng, chuỗi số ghi thành số trừ cột mã); `Bang.loc_san` dựng sẵn chế độ lọc theo từng
  giá trị một cột (hỏng chỉ cảnh báo); ghi xong đọc lại từng tab (`kiem_ghi`) — lệch thì
  `day_du=False` kèm câu nói thiếu gì, không đọc lại được thì `day_du=None` ("chưa kiểm
  được"), không bao giờ tự nhận đủ.

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
- Định dạng số hỗ trợ (@, #,##0, #,##0.00, 0.00%, yyyy/MM/dd, yyyy/MM/dd HH:mm:ss …) — Lark
  thật CHỈ nhận đúng danh sách này (thử 09/10/2026; định dạng tự chế bị 90204)
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
  (đã chạy được trên Lark thật 09/10/2026)
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet-filter/create.md
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet-filter/filter-user-guide.md
- Chế độ lọc dựng sẵn (filter view)  POST .../sheets/v3/spreadsheets/:t/sheets/:sheet_id/
  filter_views {filter_view_name ≤100 ký tự, không trùng tên; range} → data.filter_view.
  filter_view_id; rồi POST .../filter_views/:filter_view_id/conditions {condition_id: chữ
  cột, filter_type:"multiValue", expected:[giá trị HIỆN]} — 100 lần/phút mỗi API, ≤150 chế
  độ lọc mỗi tab
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet-filter_view/create.md
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet-filter_view/spreadsheet-sheet-filter_view-condition/create.md
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet-sheet-filter_view/spreadsheet-sheet-filter_view-condition/filter-view-condition-user-guide.md
- Đọc lại  GET .../sheets/v2/spreadsheets/:t/values_batch_get?ranges=a,b
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/data-operation/reading-multiple-ranges.md
- Trần chung: ≤300 tab/bảng tính, ≤13.000 cột và ≤5.000.000 ô (kể cả ô trống) mỗi tab.
  https://open.feishu.cn/document/server-docs/docs/sheets-v3/overview.md
- Link tới một tab: URL bảng tính + "?sheet=<sheetId>" (cùng trang tổng quan).
"""
from __future__ import annotations

import collections
import contextlib
import contextvars
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
LUOI_DONG, LUOI_COT = 200, 20  # lưới tab mới của Lark khi không đọc được lưới thật
NGHI_GHI = 0.2                 # giây nghỉ giữa hai khối ghi (như meta_ads/sheet_lon cũ)
NGAN_SACH_CHO = 180.0          # tổng giây được chờ lùi (429) trong MỘT lần xuất
_ngu = time.sleep              # bộ thử thay để không ngủ thật

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

# (định dạng dùng, định dạng lùi). Lark THẬT (thử 09/10/2026 trên bảng tính nháp) chỉ nhận
# ĐÚNG danh sách tài liệu: "dd/MM/yyyy", "dd/MM/yyyy HH:mm", '#,##0 "₫"', '0.00"%"', "0.00",
# "yyyy/MM/dd HH:mm" đều bị từ chối (90204 invalid formatter). Nên dùng thẳng danh sách đó:
# ngày yyyy/MM/dd, tiền VND #,##0 (đơn vị nằm ở tiêu đề / cột Tiền tệ), % đã nhân 100 hiện
# số thập phân (tiêu đề cột ghi "%"). Cặp lùi giữ lại phòng Lark đổi danh sách.
_DINH_DANG = {
    "so_nguyen": ("#,##0", "#,##0"),
    "thap_phan": ("#,##0.00", "#,##0.00"),
    "ti_le": ("#,##0.00", "#,##0.00"),
    "phan_tram": ("0.00%", "0.00%"),            # giá trị là PHÂN SỐ (0.1234 → 12.34%)
    "phan_tram_100": ("#,##0.00", "#,##0.00"),  # giá trị ĐÃ nhân 100 (12.34, tiêu đề có %)
    "ngay": ("yyyy/MM/dd", "yyyy/MM/dd"),
    "ngay_gio": ("yyyy/MM/dd HH:mm:ss", "yyyy/MM/dd HH:mm:ss"),
    "ma": ("@", "@"),
}
_CAN = {"so_nguyen": 2, "tien": 2, "thap_phan": 2, "phan_tram": 2, "phan_tram_100": 2,
        "ti_le": 2, "ngay": 1, "ngay_gio": 1}
_RONG = {"ma": 140, "chu": 180, "chu_dai": 320, "link": 240, "ngay": 100, "ngay_gio": 130}
_RONG_SO = 110


def _dinh_dang_tien(tien_te: str | None, an_toan: bool) -> str:
    t = str(tien_te or "").strip().upper()
    if t == "VND":
        return "#,##0"           # '#,##0 "₫"' bị Lark thật từ chối (09/10/2026)
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
    #: Tên tab cố định (vd "Chi tiết", "Theo tài khoản") thay cho "Dữ liệu" / "N. Tên".
    ten_tab: str | None = None
    #: Tên cột: dựng sẵn một CHẾ ĐỘ LỌC (filter view) cho mỗi giá trị khác nhau của cột này
    #: (tối đa TRAN_LOC_SAN, nhóm nhiều dòng trước). Hỏng chỉ cảnh báo — dữ liệu không phụ
    #: thuộc vào nó. Nên là cột MÃ (duy nhất, không trống), vd "Mã TK".
    loc_san: str | None = None
    #: Cột lấy TÊN chế độ lọc (vd "Tài khoản"); tên trùng giữa hai mã → "tên — mã"; tên trống
    #: → mã. None = tên là chính giá trị cột `loc_san`.
    loc_san_ten: str | None = None

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
    #: Khối con trong SỐ LIỆU CHÍNH (vd "Tài khoản tiền VND"): đổi khối → một dòng tiêu đề
    #: khối. "" = không chia khối.
    khoi: str = ""

    def __post_init__(self):
        self.kieu = _BI_DANH.get(self.kieu, self.kieu)


@dataclasses.dataclass
class Nhom:
    """Khối đếm theo nhóm (đếm bằng code từ chính các dòng — dùng `dem_theo`)."""
    ten: str
    dong: list                  # [(giá trị nhóm, số dòng)]
    tong: int | None = None
    #: Thêm cột "Biểu đồ": thanh chữ █ tỉ lệ với số (nhóm lớn nhất = THANH_TOI_DA ký tự).
    thanh: bool = False
    #: Nhãn cột số (vd "Số lượt chọn" khi ô nhiều lựa chọn).
    nhan_so: str = "Số dòng"


THANH_TOI_DA = 30


def thanh_chu(n, lon_nhat, toi_da: int = THANH_TOI_DA) -> str:
    """Thanh chữ █ tỉ lệ `n / lon_nhat` (tối đa `toi_da` ký tự; n > 0 thì ít nhất 1)."""
    try:
        n, lon_nhat = float(n), float(lon_nhat)
    except (TypeError, ValueError):
        return ""
    if n <= 0 or lon_nhat <= 0:
        return ""
    return "█" * max(1, min(toi_da, round(toi_da * n / lon_nhat)))


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
#: Từ (sau khi tách tên cột theo . _ - khoảng trắng và chữ hoa camelCase) đánh dấu cột MÃ —
#: giá trị trông như số nhưng phải giữ chữ (mã vạch 13 số, điện thoại, mã bưu chính, SKU…).
_TU_MA = {"id", "ids", "pk", "uid", "ma", "code", "sku", "barcode", "ean", "gtin", "upc",
          "zip", "zipcode", "postcode", "postal", "phone", "sdt", "tel", "mobile", "msisdn"}
#: Đuôi của một từ (không có dấu tách): shortcode, postcode, telephone, productsku…
_DUOI_MA = ("code", "phone", "sku", "barcode", "zipcode", "postcode")
_RE_TU = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def la_cot_ma(ten: str) -> bool:
    """Tên cột là cột MÃ (giữ chữ, không đổi chuỗi số thành số). Không phân biệt hoa thường:
    `_RE_MA` cũ + các từ trong `_TU_MA` + từ kết thúc bằng `_DUOI_MA` (shortCode, zipcode)
    + "so_dien_thoai"."""
    t = str(ten or "")
    if _RE_MA.search(t):
        return True
    thap = t.lower()
    if "so_dien_thoai" in thap or "sodienthoai" in thap:
        return True
    tu = [w.lower() for phan in re.split(r"[._\-\s]+", t) for w in _RE_TU.findall(phan)]
    tu += [phan.lower() for phan in re.split(r"[._\-\s]+", t) if phan]
    tu += [re.sub(r"\d+$", "", w) for w in tu]          # ean13, sku2
    return any(w in _TU_MA or w.endswith(_DUOI_MA) for w in tu if w)


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
    la_ma = {k: la_cot_ma(k) for k in khoa}
    cot = [Cot(k, "ma" if la_ma[k] else "chu", rong=140) for k in khoa]
    # Chuỗi số của nguồn (Meta trả "spend": "100000") ghi thành SỐ, không thành "số lưu dạng
    # chữ" (tam giác xanh). Cột mã giữ nguyên chữ; chuỗi đổi có thể mất thông tin cũng giữ
    # (xem `so_tu_chuoi`).
    dong = [[p.get(k, "") if la_ma[k] else so_tu_chuoi(p.get(k, "")) for k in khoa]
            for p in phs]
    return Bang(ten, cot, dong, mo_ta=mo_ta, gap_duoc=False)


_RE_SO_CHUOI = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?")
TRAN_CHU_SO = 15               # số thực giữ đúng ≤15 chữ số có nghĩa


def so_tu_chuoi(v):
    """Chuỗi là số thập phân trần ("100000", "12.5", "-3") → số; còn lại giữ nguyên. Chỉ đổi
    khi số viết lại ĐÚNG y chuỗi gốc (`str(số) == v`): "1.10", "2.50", "-0" giữ chữ (đổi là
    mất số 0 người ta cố ý ghi). Cũng giữ chữ: số 0 đầu ("0123"), dấu "+", mũ, NaN/inf, khoảng
    trắng, dấu phẩy, hoặc quá TRAN_CHU_SO chữ số (mã 18 chữ số mất chữ số cuối khi thành số
    thực)."""
    if not isinstance(v, str) or not _RE_SO_CHUOI.fullmatch(v):
        return v
    chu_so = v.lstrip("-").replace(".", "").lstrip("0")
    if len(chu_so) > TRAN_CHU_SO:
        return v
    so = int(v) if "." not in v else float(v)
    if so == 0 and v.startswith("-"):      # "-0.0": số âm 0 hiện thành 0 — giữ chữ
        return v
    return so if str(so) == v else v


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
    Một bảng → tab "Dữ liệu"; nhiều bảng → "1. Tên", "2. Tên"… (`Bang.ten_tab` thì dùng đúng
    tên đó). "Dữ liệu gốc" luôn cuối.
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
        goc_ten = b.ten_tab or (f"{i}. {b.ten}" if nhieu else TAB_DU_LIEU)
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


def _dau_nguy(c: str) -> bool:
    return c.isspace() or c in "=+-@\uff1d\uff0b\uff20" or c in A._VO_HINH


def _cat_o(s: str) -> list:
    """Cắt chữ thành các đoạn ≤TRAN_KY_TU_O; lùi chỗ cắt để đoạn sau KHÔNG mở đầu bằng ký tự
    mà bộ chặn công thức sẽ thêm "'" (= + - @, khoảng trắng, ký tự vô hình) — ghép các đoạn
    lại là đúng nguyên văn."""
    ra, i = [], 0
    while i < len(s):
        j = min(len(s), i + TRAN_KY_TU_O)
        k = j
        while k < len(s) and k > i + 1 and _dau_nguy(s[k]):
            k -= 1
        if k <= i + 1:          # cả khúc toàn ký tự "nguy" (hầu như không có): cắt cứng
            k = j
        ra.append(s[i:k])
        i = k
    return ra or [""]


def _chia_o_dai(b_cot: list, dong: list) -> tuple[list, list, list]:
    """Ô chữ dài hơn TRAN_KY_TU_O → chảy sang cột "(tiếp)" ngay sau (xem `_cat_o`). -> (cột
    mới, dòng mới, bản đồ cột mới → cột gốc)."""
    can: dict = {}
    for r in dong:
        for j, v in enumerate(r):
            if isinstance(v, str) and len(v) > TRAN_KY_TU_O:
                can[j] = max(can.get(j, 1), len(_cat_o(v)))
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
                s_ = v if isinstance(v, str) else ("" if v is None else str(v))
                doan = _cat_o(s_) if len(s_) > TRAN_KY_TU_O else [s_]
                o += doan + [""] * (n - len(doan))
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
            if lan < 3 and _RE_DAY.search(str(e)):
                _ngu(min(8.0, 1.0 * 2 ** lan))
                lan += 1
                continue
            raise


_RE_DAY = re.compile(r"(?i)\b429\b|frequency|too many|rate.?limit|90217|99991400|1310217|1310235")


def _canh(canh_bao: list, viec: str, e: Exception, du: bool = True) -> None:
    """Ghi cảnh báo. `du`=False: việc hỏng làm THIẾU nội dung (vd Tổng quan) — không nói
    "dữ liệu vẫn đủ"."""
    cau = (f"{viec} hỏng (bỏ qua, dữ liệu vẫn đủ)" if du else f"{viec} HỎNG") + \
        f": {A._che_token(e)[:160]}"
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
    """Nới lưới tab đủ `can_dong` × `can_cot` (POST dimension_range, ≤5000 mỗi lần). Không
    đọc được lưới → coi là lưới tab mới của Lark (200 × 20) và vẫn nới: thêm thừa vài dòng
    trống vô hại, thiếu dòng thì ghi hỏng."""
    dong, cot = co
    dong, cot = dong or LUOI_DONG, cot or LUOI_COT
    for chieu, hien, can in (("ROWS", dong, can_dong), ("COLUMNS", cot, can_cot)):
        while hien < can:
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
            _ghi_khoi(tok, sid, khoi, dong_dau + i, c0 + 1)
        i = j
        if i < len(values):
            _ngu(NGHI_GHI)                 # nghỉ giữa các khối: Lark báo vượt tần suất (429)


class HetNganSachCho(RuntimeError):
    """Lark báo vượt tần suất quá lâu: hết NGAN_SACH_CHO giây chờ của lần xuất này — dừng,
    bảng tính (nếu đã tạo) còn thiếu, link gắn vào lỗi (`trinh_bay_url`)."""


#: {"con": giây còn được chờ} của lần xuất đang chạy (mỗi luồng/lượt riêng).
_NGAN_SACH: contextvars.ContextVar = contextvars.ContextVar("tb_ngan_sach_cho", default=None)


@contextlib.contextmanager
def ngan_sach_cho(giay: float | None = None):
    """Một ngân sách chờ 429 (mặc định NGAN_SACH_CHO giây) cho mọi lần ghi bên trong — dùng
    cho các đường ghi ngoài `xuat` (vd fb_ads ghi nối)."""
    moc = _NGAN_SACH.set({"con": NGAN_SACH_CHO if giay is None else giay})
    try:
        yield
    finally:
        _NGAN_SACH.reset(moc)


def _cho(giay: float) -> None:
    ns = _NGAN_SACH.get()
    if ns is not None:
        if ns["con"] < giay:
            raise HetNganSachCho(
                f"Lark báo vượt tần suất quá lâu: đã chờ hết {NGAN_SACH_CHO:.0f} giây cho lần "
                "xuất này — dừng ghi, bảng tính CHƯA đủ dữ liệu")
        ns["con"] -= giay
    _ngu(giay)


def _ghi_khoi(tok: str, sid: str, khoi: list, dong_dau: int, cot_dau: int) -> None:
    """Một khối qua `apify_tool._write_values` (chặn chèn công thức); Lark báo vượt tần suất
    thì lùi dần và ghi LẠI đúng vùng đó (ghi đè cùng vùng — không nhân đôi dòng)."""
    for lan in range(6):
        try:
            if cot_dau == 1:
                A._write_values(tok, sid, khoi, dong_dau=dong_dau)
            else:
                A._write_values(tok, sid, khoi, dong_dau=dong_dau, cot_dau=cot_dau)
            return
        except RuntimeError as e:
            if lan < 5 and _RE_DAY.search(str(e)):
                _cho(min(24.0, 1.5 * 2 ** lan))
                continue
            raise


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
        cac_dk = list(_LOC_DIEU_KIEN)
    duong = f"/open-apis/sheets/v3/spreadsheets/{tok}/sheets/{sid}/filter"
    loi = None
    for lan in range(2):
        for dk in cac_dk:
            try:
                _goi("POST", duong, body={"range": vung, "col": "A", "condition": dk})
                with _LOC_KHOA:                          # nhớ dạng chạy được cho lần sau
                    if dk in _LOC_DIEU_KIEN and _LOC_DIEU_KIEN[0] is not dk:
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


# Chế độ lọc dựng sẵn (filter view): 100 lần/phút mỗi API — giữ dưới bằng cửa sổ trượt
# (chờ thay vì bỏ: số lời gọi một lần xuất có trần TRAN_LOC_SAN × 2), còn 429 thì `_goi` lùi.
TRAN_LOC_SAN = 30              # chế độ lọc mỗi tab (Lark cho ≤150 mỗi tab)
TRAN_TEN_LOC = 100             # ký tự tên chế độ lọc (tài liệu: ≤100)
_LOC_SAN_PHUT = 90
_LOC_SAN_LUOT: collections.deque = collections.deque()
_LOC_SAN_KHOA = threading.Lock()


@dataclasses.dataclass
class LocSan:
    """Kết quả dựng chế độ lọc của một tab: `tao`/`tong` giá trị; `loi` khi dừng giữa chừng."""
    cot: str
    tao: int = 0
    tong: int = 0
    loi: str = ""


def _nhip_loc_san() -> None:
    with _LOC_SAN_KHOA:
        now = time.monotonic()
        while _LOC_SAN_LUOT and now - _LOC_SAN_LUOT[0] > 60:
            _LOC_SAN_LUOT.popleft()
        cho = 0.0
        if len(_LOC_SAN_LUOT) >= _LOC_SAN_PHUT:
            cho = max(0.0, 60.5 - (now - _LOC_SAN_LUOT[0]))
        _LOC_SAN_LUOT.append(now + cho)
    if cho:
        _ngu(cho)


def _ten_loc(gia_tri: str, da: set) -> str:
    """Tên chế độ lọc: bỏ ký tự cấm như tên tab, ≤TRAN_TEN_LOC, không trùng (Lark từ chối
    tên trùng — 1310240)."""
    t = re.sub(r"\s+", " ", re.sub(r"[/\\?*\[\]:]", " ", str(gia_tri))).strip() or "(trống)"
    t = t[:TRAN_TEN_LOC].strip()
    goc, k = t, 2
    while t.lower() in da:
        hau = f" ({k})"
        t = goc[:TRAN_TEN_LOC - len(hau)].rstrip() + hau
        k += 1
    da.add(t.lower())
    return t


def _chu_o(v) -> str:
    """Giá trị ô như Lark hiển thị (để so khớp điều kiện multiValue)."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(A._o_an_toan(v) if isinstance(v, str) else v)


def tao_loc_san(tok: str, sid: str, cot: list, dong: list, ten_cot: str, dong_dau: int = 1,
                canh_bao: list | None = None, cot_ten: str | None = None) -> LocSan | None:
    """Mỗi giá trị khác nhau của cột `ten_cot` (nhóm nhiều dòng trước, tối đa TRAN_LOC_SAN)
    → một chế độ lọc, vùng = tiêu đề + dữ liệu, điều kiện multiValue chỉ hiện giá trị đó.
    Tên chế độ lọc: giá trị ở cột `cot_ten` (vd tên tài khoản khi lọc theo mã); hai mã cùng
    tên → "tên — mã"; tên trống → mã. Lỗi → cảnh báo, DỪNG (không gọi tiếp), xoá chế độ lọc vừa
    tạo mà chưa có điều kiện (kẻo nó hiện tất cả dưới tên một tài khoản). Không bao giờ ném."""
    cb = canh_bao if canh_bao is not None else []
    ten = [c.ten for c in cot]
    if ten_cot not in ten or not dong:
        return None
    j = ten.index(ten_cot)
    jt = ten.index(cot_ten) if cot_ten in ten else None
    dem: collections.Counter = collections.Counter()
    nhan: dict = {}
    for r in dong:
        v = r[j] if j < len(r) else ""
        if v not in ("", None):
            k = _chu_o(v)
            dem[k] += 1
            if jt is not None and k not in nhan:
                t = r[jt] if jt < len(r) else ""
                nhan[k] = "" if t in ("", None) else str(t).strip()
    thu_tu = {s: i for i, s in enumerate(dem)}
    gia_tri = sorted(dem, key=lambda s: (-dem[s], thu_tu[s]))
    so_ma = collections.Counter(nhan.get(s) for s in gia_tri if nhan.get(s))

    def ten_hien(s):
        t = nhan.get(s, "") if jt is not None else s
        if not t:
            return s
        return t if so_ma[t] <= 1 or jt is None else f"{t} — {s}"
    kq = LocSan(cot_ten if jt is not None else ten_cot, 0, len(gia_tri))
    vung = f"{sid}!A{dong_dau}:{A._cot(len(cot))}{dong_dau + len(dong)}"
    duong = f"/open-apis/sheets/v3/spreadsheets/{tok}/sheets/{sid}/filter_views"
    da: set = set()
    for s in gia_tri[:TRAN_LOC_SAN]:
        ten_v, fid = _ten_loc(ten_hien(s), da), ""
        try:
            _nhip_loc_san()
            d = _goi("POST", duong, body={"filter_view_name": ten_v, "range": vung})
            fid = (((d or {}).get("data") or {}).get("filter_view") or {}).get(
                "filter_view_id") or ""
            if not fid:
                raise RuntimeError("Lark không trả filter_view_id")
            _nhip_loc_san()
            _goi("POST", f"{duong}/{fid}/conditions",
                 body={"condition_id": A._cot(j + 1), "filter_type": "multiValue",
                       "expected": [s]})
        except Exception as e:  # noqa: BLE001
            if fid:
                try:
                    _nhip_loc_san()
                    _goi("DELETE", f"{duong}/{fid}")
                except Exception:  # noqa: BLE001
                    pass
            kq.loi = A._che_token(e)[:160]
            _canh(cb, f"Tạo chế độ lọc '{ten_v}'", e)
            break
        kq.tao += 1
    return kq


def _ghi_chu_loc_san(tabs: list) -> list:
    """Câu Tổng quan về chế độ lọc dựng sẵn của các tab (để người xem biết mà dùng)."""
    ra = []
    for t in tabs:
        ls = getattr(t, "loc_san", None)
        if not ls:
            continue
        if ls.tao:
            cau = (f"Tab {t.ten} có sẵn {ls.tao} chế độ lọc (filter view) theo cột {ls.cot}, mỗi "
                   f"{ls.cot.lower()} một chế độ mang tên của nó: mở menu Lọc → chế độ lọc, "
                   "chọn tên để chỉ xem các dòng của nó (dữ liệu không đổi, người khác không "
                   "bị ảnh hưởng).")
            if ls.tao < ls.tong:
                cau += (f" Chỉ dựng {ls.tao}/{ls.tong} {ls.cot.lower()} nhiều dòng nhất"
                        + (" (dừng vì lỗi)" if ls.loi else f" (trần {TRAN_LOC_SAN})")
                        + f"; giá trị còn lại lọc tay ở cột {ls.cot}.")
        else:
            cau = (f"Tab {t.ten}: chưa tạo được chế độ lọc dựng sẵn theo {ls.cot}; dùng bộ lọc "
                   f"ở tiêu đề cột {ls.cot}.")
        ra.append(cau)
    return ra


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
    r_kiem: int | None = None     # dòng đọc lại để kiểm (dòng CUỐI có chữ); None = dòng cuối
    loc_san: LocSan | None = None # chế độ lọc dựng sẵn (Bang.loc_san)


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
    """Dựng các dòng tab Tổng quan (thuần). Dòng KHÔNG đệm ô trống bên phải (ô "" chặn chữ
    dài tràn sang ô kế — đo trên Lark thật 09/10/2026). -> (dòng, vai trò) với vai trò =
    {"tieu_de": r, "meta": [r], "kiem": r, "muc": [r], "dau_bang": [(r, số cột)],
     "so": [(r, c, kiểu, tiền tệ)], "rong": số cột}."""
    luc = luc or datetime.datetime.now(VN)
    dong: list = []
    vai: dict = {"muc": [], "dau_bang": [], "so": [], "link": [], "meta": []}

    def them(r):
        r = list(r)
        while r and r[-1] in ("", None):
            r.pop()
        dong.append(r)
        return len(dong)

    vai["tieu_de"] = them([tq.tieu_de])
    # Siêu dữ liệu: mỗi mục một dòng nhãn | giá trị (giá trị gộp B:D, canh trái).
    for nhan, gt in (("Nguồn", tq.nguon), ("Thời gian", tq.thoi_gian), ("Phạm vi", tq.pham_vi),
                     ("Người yêu cầu", tq.nguoi_yeu_cau),
                     ("Tạo lúc", f"{luc.astimezone(VN):%d/%m/%Y %H:%M} (giờ VN)")):
        # Giá trị dài hơn bề ngang B:D chia thành nhiều dòng (nhãn chỉ ở dòng đầu) — không
        # bao giờ cắt bớt chữ.
        for i, doan in enumerate(_tach_dong(str(gt)) if gt else []):
            vai["meta"].append(them([nhan if i == 0 else "", doan]))
    if kiem and kiem.get("cau"):
        vai["kiem"] = them([kiem["cau"]])
    them([])

    if tq.so_lieu:
        vai["muc"].append(them(["SỐ LIỆU CHÍNH"]))
        vai["dau_bang"].append((them(["Chỉ số", "Giá trị", "", "Ghi chú"]), 4))
        khoi = ""
        for s in tq.so_lieu:
            if s.khoi and s.khoi != khoi:
                # Khối con (vd mỗi tiền tệ một khối): dòng tiêu đề khối, tô như dòng đầu bảng.
                khoi = s.khoi
                vai["dau_bang"].append((them([khoi]), 4))
            gt = s.gia_tri
            if s.kieu in ("ngay", "ngay_gio"):
                gt = _o(gt, s.kieu, False)
            elif isinstance(gt, decimal.Decimal):
                gt = float(gt)
            r = them([s.nhan, "" if gt is None else gt, "", s.ghi_chu])
            if s.kieu in _KIEU_SO and _la_so(gt):
                vai["so"].append((r, 2, s.kieu, s.tien_te))
        them([])

    for g in tq.nhom:
        vai["muc"].append(them([g.ten.upper()]))
        dau = ["Nhóm", g.nhan_so or "Số dòng", "Tỉ lệ"] + (["Biểu đồ"] if g.thanh else [])
        vai["dau_bang"].append((them(dau), len(dau)))
        tong = g.tong if g.tong else sum(n for _, n in g.dong)
        lon = max((n for _, n in g.dong), default=0)
        for k, n in g.dong:
            r = them([k, n, (n / tong) if tong else ""]
                     + ([thanh_chu(n, lon)] if g.thanh else []))
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
        # Kết quả (chữ dài) ở cột D — cột rộng nhất, không bị ô kế chặn.
        vai["muc"].append(them(["KIỂM GHI"]))
        vai["dau_bang"].append((them(["Tab", "Số dòng", "Số cột", "Kết quả"]), 4))
        for k in kiem["tabs"]:
            r = them([k["tab"], k.get("du_kien", ""), k.get("cot", ""), k["cau"]])
            vai["so"].append((r, 2, "so_nguyen", None))
        them([])

    for b in gap:
        khoi_bang(b, b.ten)

    if tq.ghi_chu:
        vai["muc"].append(them(["GHI CHÚ"]))
        for g in tq.ghi_chu:
            them([f"• {g}"])
    while dong and not dong[-1]:
        dong.pop()
    vai["rong"] = max(4, max((len(r) for r in dong), default=1))
    return dong, vai


#: Số ký tự một ô giá trị siêu dữ liệu (gộp B:D ≈ 790px, chữ 10pt) hiện trọn trên Lark.
TRAN_KY_TU_META = 90


def _tach_dong(s: str, toi_da: int = TRAN_KY_TU_META) -> list:
    """Chia chuỗi thành các dòng ≤`toi_da` ký tự: ưu tiên ngắt sau "; " rồi ", ", rồi khoảng
    trắng; chỉ cắt giữa từ khi một từ dài hơn cả dòng. Ghép lại (theo dấu ngắt) đủ nguyên văn."""
    s = " ".join(s.split())
    if len(s) <= toi_da:
        return [s]
    ra = []
    while len(s) > toi_da:
        cat = -1
        for dau in ("; ", ", ", " "):
            k = s.rfind(dau, 0, toi_da)
            if k > 0:
                cat = k + len(dau.rstrip())
                break
        if cat <= 0:
            cat = toi_da
        ra.append(s[:cat].rstrip())
        s = s[cat:].lstrip()
    if s:
        ra.append(s)
    return ra


def _link_tab(url: str, sid: str) -> str:
    return f"{url.split('?')[0].split('#')[0]}?sheet={sid}"


#: Độ rộng cột Tổng quan: D rộng vì chứa chữ dài (Nội dung mục lục, Kết quả kiểm, Ghi chú).
_RONG_TONG_QUAN = [220, 160, 110, 520]


def _trang_tri_tong_quan(tok: str, sid: str, dong: list, vai: dict, cb: list) -> None:
    w = vai["rong"]
    trai = {"hAlign": 0, "vAlign": 1}
    muc = [(f"{sid}!A{vai['tieu_de']}:{A._cot(w)}{vai['tieu_de']}",
            {"font": {"bold": True, "fontSize": "16pt/1.5"}, "foreColor": CHU_TOI, **trai})]
    for r in vai["meta"]:
        muc.append((f"{sid}!A{r}:A{r}", {"font": {"bold": True}, "foreColor": "#555F6D",
                                         **trai}))
        muc.append((f"{sid}!B{r}:{A._cot(w)}{r}", {"foreColor": CHU_TOI, **trai}))
    if vai.get("kiem"):
        muc.append((f"{sid}!A{vai['kiem']}:{A._cot(w)}{vai['kiem']}",
                    {"font": {"bold": True}, "foreColor": CHU_TOI, **trai}))
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
    # Gộp ô TRƯỚC, tô SAU: ô vừa gộp bị Lark căn giữa (Lark thật 09/10/2026: giá trị "Nguồn"
    # dài bị cắt hai đầu) — tô hAlign=0 sau khi gộp mới giữ canh trái.
    gop = [(f"{sid}!A{vai['tieu_de']}:{A._cot(w)}{vai['tieu_de']}", "MERGE_ALL")]
    if vai["meta"]:   # giá trị siêu dữ liệu gộp B:cuối, MỖI dòng một ô (MERGE_ROWS, 1 lời gọi)
        gop.append((f"{sid}!B{vai['meta'][0]}:{A._cot(w)}{vai['meta'][-1]}", "MERGE_ROWS"))
    if vai.get("kiem"):
        gop.append((f"{sid}!A{vai['kiem']}:{A._cot(w)}{vai['kiem']}", "MERGE_ALL"))
    for vung, kieu_gop in gop:
        try:
            _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{tok}/merge_cells",
                 body={"range": vung, "mergeType": kieu_gop})
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Gộp ô Tổng quan", e)
            break
    try:
        _kieu(tok, muc)
    except Exception:  # noqa: BLE001 — lùi định dạng an toàn
        try:
            _kieu(tok, _an_toan_muc(muc))
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Tô tab Tổng quan", e)
    try:
        _dat_rong(tok, sid, _RONG_TONG_QUAN + [140] * (w - 4))
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Đặt độ rộng Tổng quan", e)


def _ghi_gon(tok: str, sid: str, dong: list, dong_dau: int = 1) -> None:
    """Ghi các dòng KHÔNG đệm ô trống: gom dòng liền nhau cùng số ô thành một vùng; dòng
    trống bỏ qua (ô để trống thật, chữ dài bên trái tràn sang được)."""
    i = 0
    while i < len(dong):
        n = len(dong[i])
        if not n:
            i += 1
            continue
        j = i
        while j + 1 < len(dong) and len(dong[j + 1]) == n:
            j += 1
        _ghi(tok, sid, [list(r) for r in dong[i:j + 1]], dong_dau=dong_dau + i)
        i = j + 1


def _bo_link(dong: list) -> list:
    return [[(v.get("text") if isinstance(v, dict) else v) for v in r] for r in dong]


def _viet_tong_quan(tok: str, sid: str, dong: list, luoi: tuple, cb: list | None = None,
                    dong_dau: int = 1) -> None:
    """Nới lưới rồi ghi các dòng Tổng quan (gọn) từ dòng `dong_dau`. Ô link bị từ chối →
    ghi lại không link (có cảnh báo). Hết ngân sách chờ 429 thì NÉM ngay, không thử lại.
    Lỗi ghi → NÉM (bên gọi quyết)."""
    _noi_luoi(tok, sid, luoi, dong_dau - 1 + len(dong),
              max((len(r) for r in dong), default=1))
    try:
        _ghi_gon(tok, sid, dong, dong_dau=dong_dau)
    except HetNganSachCho:
        raise
    except Exception as e:  # noqa: BLE001 — ô link (mục lục) bị từ chối?
        if not any(isinstance(v, dict) for r in dong for v in r):
            raise
        _ghi_gon(tok, sid, _bo_link(dong), dong_dau=dong_dau)
        if cb is not None:
            _canh(cb, "Ô link mục lục Tổng quan (đã ghi lại dạng chữ, không bấm được)", e)


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
        r = _r_kiem(t)
        if r != t.dong_dau:
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
            r_k = _r_kiem(t)
            dau = _tim(doc, t.sheet_id, f"A{t.dong_dau}", f"{w}{t.dong_dau}")
            cuoi = _tim(doc, t.sheet_id, f"A{r_k}", f"{w}{r_k}") if r_k != t.dong_dau else []
            lo = luoi.get(t.sheet_id)
            if dau is None or (r_k != t.dong_dau and cuoi is None):
                ket = None
            else:
                du_dau = _dem_o(dau) >= sum(1 for c in t.cot if c.ten)
                du_cuoi = r_k == t.dong_dau or _dem_o(cuoi) >= 1
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
    return _gop_kiem([{"tabs": ket_tabs}])


def _r_kiem(t) -> int:
    """Dòng đọc lại của tab: dòng dữ liệu cuối CÓ CHỮ (biết lúc ghi), không thì dòng cuối."""
    if t.r_kiem is not None:
        return t.r_kiem
    return t.dong_dau + t.so_dong


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
    urls: list                    # link các bảng tính ĐÃ ghi được (phần 1 trước)
    tabs: list
    kiem: dict
    canh_bao: list
    loai: str
    tong_quan_sid: str = ""       # sheet_id tab Tổng quan (bảng tính đầu; "" nếu thêm hỏng)
    tong_quan: TongQuan | None = None
    tong_quan_hong: bool = False  # Tổng quan bảng tính đầu không ghi được
    phan_hong: list = dataclasses.field(default_factory=list)   # [{phan, url, loi}]

    @property
    def day_du(self):
        return self.kiem.get("day_du")

    @property
    def cau_kiem(self) -> str:
        return self.kiem.get("cau") or ""

    def cho_tool(self) -> dict:
        """Trường gắn vào tool_result: Mark chép NGUYÊN `kiem_ghi` khi gửi link, gửi MỌI link
        ở `bang_tinh_tiep`. Có trục trặc thì kèm `canh_bao_trinh_bay` (ngắn); Tổng quan không
        ghi được thì các ghi chú của nó (vd "ĐÃ CẮT ở 20.000 dòng") ở `ghi_chu_sheet`."""
        ra = {"day_du": self.day_du, "kiem_ghi": self.cau_kiem,
              "bang_tinh_tiep": self.urls[1:] or None}
        if self.canh_bao:
            ra["canh_bao_trinh_bay"] = "; ".join(c[:140] for c in self.canh_bao[:4])[:600]
        if self.tong_quan_hong and self.tong_quan is not None and self.tong_quan.ghi_chu:
            ra["ghi_chu_sheet"] = list(self.tong_quan.ghi_chu)
        if self.phan_hong:
            ra["bang_tinh_hong"] = [dict(p) for p in self.phan_hong]
        loc = [t.loc_san for t in self.tabs if getattr(t, "loc_san", None)]
        if loc:
            ra["che_do_loc"] = sum(x.tao for x in loc)
        return ra


def xuat(tieu_de: str, bang: list, tong_quan: TongQuan | None = None, goc: Bang | None = None,
         sau_khi_tao: Callable[[str], Any] | None = None,
         cap_quyen: Callable[[str], Any] | None = None,
         luc: datetime.datetime | None = None) -> KetQua:
    """MỘT lời gọi dựng cả bảng tính (xem docstring module cho thứ tự). Lỗi tạo / ghi dữ liệu
    của bảng tính ĐẦU hoặc lỗi callback thì NÉM (như code cũ); bảng tính tiếp theo hỏng thì
    các phần đã ghi vẫn có Tổng quan + quyền, phần hỏng báo rõ (`phan_hong`, `day_du`=False).
    Lỗi trang trí chỉ cảnh báo."""
    with ngan_sach_cho():
        return _xuat(tieu_de, bang, tong_quan, goc, sau_khi_tao, cap_quyen, luc)


def _xuat(tieu_de, bang, tong_quan, goc, sau_khi_tao, cap_quyen, luc) -> KetQua:
    tq = tong_quan or TongQuan(tieu_de)
    if not tq.nguoi_yeu_cau:
        tq = dataclasses.replace(tq, nguoi_yeu_cau=_ten_nguoi_yeu_cau())
    kh = ke_hoach(bang, tq, goc)
    cb: list = []
    so_bt = len(kh.bang_tinh)
    phan: list = []
    for k, tabs in enumerate(kh.bang_tinh):
        td = tieu_de if so_bt == 1 else f"{tieu_de} (phần {k + 1}/{so_bt})"
        try:
            tok, url, da_ghi, kiem = _xuat_mot(td, tabs, kh, sau_khi_tao, cb)
        except Exception as e:  # noqa: BLE001
            if k == 0:
                raise
            _canh(cb, f"Bảng tính phần {k + 1}/{so_bt}", e, du=False)
            phan.append({"k": k, "td": td, "url": getattr(e, "trinh_bay_url", "") or "",
                         "loi": A._che_token(f"{type(e).__name__}: {e}")[:200], "tabs": tabs})
            continue
        phan.append({"k": k, "td": td, "tok": tok, "url": url, "da_ghi": da_ghi,
                     "kiem": kiem, "loi": None, "tabs": tabs})
    ok = [p for p in phan if not p["loi"]]
    hong = [p for p in phan if p["loi"]]
    urls = [p["url"] for p in ok]
    tq_sid, tq_hong = "", False
    for p in ok:
        dau = p["k"] == 0
        gap = kh.gap if dau else []
        tq_i = dataclasses.replace(tq, tieu_de=p["td"],
                                   ghi_chu=list(tq.ghi_chu) + _ghi_chu_loc_san(p["da_ghi"]))
        sid, tq_kiem = _ghi_tong_quan(p["tok"], p["url"], tq_i, p["da_ghi"], gap, p["kiem"],
                                      cb, luc, urls[1:] if dau else [])
        if dau:
            tq_sid, tq_hong = sid, tq_kiem["ket"] == "thieu"
        if tq_kiem["ket"] == "thieu" and gap:
            # Bảng tí hon CHỈ nằm trong Tổng quan: Tổng quan hỏng → ghi chúng thành tab riêng
            # (hoặc dưới tab dữ liệu đầu), kẻo mất mà không ai biết.
            them, kiem_gap = _ghi_bang_gap(p["tok"], p["da_ghi"], gap, cb, co_tq=bool(sid))
            p["da_ghi"] = p["da_ghi"] + them
            p["kiem"] = _gop_kiem([p["kiem"], kiem_gap])
        p["kiem"] = _gop_kiem([p["kiem"], {"day_du": None, "cau": "", "tabs": [tq_kiem]}])
        if cap_quyen:
            cap_quyen(p["tok"])
    kiem_tong = _gop_kiem([p["kiem"] for p in ok] + [_kiem_phan_hong(p, so_bt) for p in hong])
    return KetQua(urls[0], ok[0]["tok"], urls, [t for p in ok for t in p["da_ghi"]], kiem_tong,
                  cb, kh.loai, tq_sid or "", tq, tq_hong,
                  [{"phan": f"{p['k'] + 1}/{so_bt}", "url": p["url"] or None,
                    "loi": p["loi"]} for p in hong])


def _kiem_phan_hong(p: dict, so_bt: int) -> dict:
    ten = ", ".join(t.ten for t in p["tabs"])
    cau = (f"bảng tính phần {p['k'] + 1}/{so_bt} HỎNG ({p['loi']})"
           + (f" — link đã tạo nhưng chưa đủ: {p['url']}" if p["url"] else "")
           + f"; thiếu các tab: {ten}")
    return {"day_du": False, "cau": "",
            "tabs": [{"tab": f"Phần {p['k'] + 1}/{so_bt}",
                      "du_kien": sum(len(t.dong) for t in p["tabs"]), "cot": "",
                      "ket": "thieu", "cau": cau}]}


def _gop_kiem(ds: list) -> dict:
    """Gộp kết quả kiểm: THIẾU ở đâu là False; đủ hết (kể cả Tổng quan) mới True."""
    tabs = [t for k in ds if k for t in k.get("tabs") or []]
    kets = [t["ket"] for t in tabs]
    if any(k == "thieu" for k in kets):
        day_du = False
    elif kets and all(k == "du" for k in kets):
        day_du = True
    else:
        day_du = None
    du_lieu = [t for t in tabs if t["tab"] != TAB_TONG_QUAN and not t["tab"].startswith("Phần ")]
    tong_dong = sum(int(t.get("du_kien") or 0) for t in du_lieu)
    if day_du is True:
        cau = (f"Đã ghi đủ {_so_vn(tong_dong)}/{_so_vn(tong_dong)} dòng ở {len(du_lieu)} tab "
               "dữ liệu (đã đọc lại kiểm).")
    elif day_du is False:
        cau = ("CẢNH BÁO GHI THIẾU: " + "; ".join(f"{t['tab']}: {t['cau']}" for t in tabs
                                                if t["ket"] == "thieu") + ".")
    else:
        cau = (f"Đã gửi {_so_vn(tong_dong)} dòng ở {len(du_lieu)} tab dữ liệu; chưa đọc lại "
               "được để kiểm đủ.")
    return {"day_du": day_du, "cau": cau, "tabs": tabs}


def gop_quyen(cap: dict, ok) -> None:
    """`cap_quyen` chạy MỘT lần mỗi bảng tính (bảng tính tiếp theo khi quá 10 tab): `granted`
    là AND của mọi lần cấp — một phần không cấp được thì không báo "đã cấp"."""
    cap["granted"] = bool(ok) if not cap.get("_da_cap") else (cap["granted"] and bool(ok))
    cap["_da_cap"] = True


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
    if not tabs:
        return tok, url, [], {"day_du": True, "cau": "Không có bảng dữ liệu.", "tabs": []}
    da_ghi = _ghi_tabs(tok, tabs, cb, sid_dau=sid0, vi_tri0=0, noi=(sid0, 0, tabs[0].ten))
    try:
        _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{tok}/sheets_batch_update",
             body={"requests": [{"updateSheet": {"properties": {"sheetId": sid0,
                                                                "title": tabs[0].ten}}}]})
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Đặt tên tab dữ liệu đầu", e)
    return tok, url, da_ghi, kiem_ghi(tok, da_ghi)


def _ghi_tabs(tok: str, tabs: list, cb: list, sid_dau: str | None, vi_tri0: int,
              noi: tuple) -> list:
    """Ghi các TabKH: tab đầu vào `sid_dau` (nếu có — tab luôn tồn tại, dữ liệu không phụ
    thuộc addSheet), các tab sau thêm ở vị trí `vi_tri0 + i`. Thêm tab hỏng → ghi dưới tab
    `noi` = (sheet_id, số dòng đã dùng, tên tab) kèm dòng ngăn. Ghi dữ liệu lỗi → NÉM.
    -> [TabDaGhi]."""
    sids: list = []
    for i, t in enumerate(tabs):
        if i == 0 and sid_dau:
            sids.append(sid_dau)
            continue
        try:
            sids.append(_them_tab(tok, t.ten, vi_tri0 + i))
        except Exception as e:  # noqa: BLE001
            _canh(cb, f"Thêm tab '{t.ten}'", e)
            sids.append(None)
    luoi = _luoi(tok)
    sid_noi, dong_noi, ten_noi = noi
    # 1) chuẩn bị bảng (ô dài → cột tiếp) + vị trí ghi
    ke: list = []
    for i, t in enumerate(tabs):
        cot, dong, _ = _chia_o_dai(t.bang.cot, t.dong)
        tong = t.bang.dong_tong if t.co_tong else []
        if tong:
            cot2, tong, _ = _chia_o_dai(t.bang.cot, tong)
            if len(cot2) != len(cot):                       # hiếm: đồng bộ cột tiếp
                cot, dong, _ = _chia_o_dai(t.bang.cot, t.dong + t.bang.dong_tong)
                dong, tong = dong[:len(t.dong)], dong[len(t.dong):]
        if sids[i] is None:
            sid, dd, ve = sid_noi, dong_noi + 3, ten_noi
        else:
            sid, dd, ve = sids[i], 1, None
        so_dong_tab = 1 + len(dong) + ((1 + len(tong)) if tong else 0)
        if sid == sid_noi:
            dong_noi = max(dong_noi, dd - 1 + so_dong_tab)
        ke.append((t, sid, dd, ve, cot, dong, tong))
    # 2) nới lưới (dòng/cột) trước khi đặt định dạng và ghi
    can: dict = {}
    for t, sid, dd, ve, cot, dong, tong in ke:
        r = dd - 1 + 1 + len(dong) + ((1 + len(tong)) if tong else 0)
        a, b = can.get(sid, (0, 0))
        can[sid] = (max(a, r), max(b, len(cot)))
    for sid, (r, c) in can.items():
        try:
            _noi_luoi(tok, sid, luoi.get(sid, (0, 0)), r, c)
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Nới lưới", e)       # lỗi thật (nếu có) lộ ở bước ghi
    # 3) định dạng số TRƯỚC khi ghi (để ngày là ngày thật). Hỏng → ngày ghi dạng chữ.
    muc_a = []
    for t, sid, dd, ve, cot, dong, tong in ke:
        if ve is None:
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
    # 4) GHI DỮ LIỆU (lỗi → ném, như code cũ)
    da_ghi: list = []
    for t, sid, dd, ve, cot, dong, tong in ke:
        ngay_that = dinh_dang_xong and ve is None
        than = [[_o(r[j] if j < len(r) else "", c.kieu, ngay_that) for j, c in enumerate(cot)]
                for r in dong]
        vals = [[c.ten for c in cot]] + than
        if tong:
            vals += [[""] * len(cot)] + [
                [_o(r[j] if j < len(r) else "", c.kieu, False) for j, c in enumerate(cot)]
                for r in tong]
        if ve is not None:
            vals = [[f"— {t.ten} — (không thêm được tab riêng)"] + [""] * (len(cot) - 1)] + vals
            _ghi(tok, sid, vals, dong_dau=dd - 1)
        else:
            _ghi(tok, sid, vals, dong_dau=dd)
        # Dòng để đọc lại kiểm: dòng dữ liệu CUỐI có chữ (dòng trống hợp lệ không bị coi là
        # thiếu); không dòng nào có chữ thì kiểm dòng tiêu đề.
        cuoi = next((k for k in range(len(than) - 1, -1, -1)
                     if any(v not in ("", None) for v in than[k])), None)
        da_ghi.append(TabDaGhi(t.ten, sid, cot, len(dong), len(cot), len(tong),
                               t.bang.mo_ta + (f" (phần {t.phan[0]}/{t.phan[1]})"
                                               if t.phan else ""),
                               ve, dd, r_kiem=dd if cuoi is None else dd + 1 + cuoi))
    # 5) trang trí (cảnh báo nếu hỏng)
    for (t, sid, dd, ve, cot, dong, tong), tg in zip(ke, da_ghi):
        trang_tri_bang(tok, tg.sheet_id, cot, len(dong), len(tong),
                       dinh_dang_xong=dinh_dang_xong and ve is None, mau=dong,
                       canh_bao=cb, dong_dau=dd, rieng_tab=ve is None, tong=tong,
                       an_toan=an_toan or not dinh_dang_xong)
        if t.bang.loc_san and ve is None and dong:
            try:
                tg.loc_san = tao_loc_san(tok, tg.sheet_id, cot, dong, t.bang.loc_san, dd, cb,
                                         t.bang.loc_san_ten)
            except Exception as e:  # noqa: BLE001 — dữ liệu không phụ thuộc chế độ lọc
                _canh(cb, "Tạo chế độ lọc dựng sẵn", e)
    # Bỏ cột lưới trống bên phải CHỈ ở tab vừa dựng trong lượt này. Tab `noi` đã có dữ liệu
    # từ bước trước (cứu bảng tí hon khi Tổng quan hỏng) thì KHÔNG bao giờ bỏ cột: bảng ghi
    # nối hẹp hơn bảng sẵn có — bỏ cột theo bảng hẹp là xoá mất cột dữ liệu (review 09/10).
    co_san = {sid_noi} if noi[1] > 0 else set()
    for sid, (_, c) in can.items():
        if sid in co_san:
            continue
        _bo_cot_thua(tok, sid, max(c, luoi.get(sid, (0, 0))[1] or LUOI_COT), c, cb)
    return da_ghi


def _ghi_bang_gap(tok: str, da_ghi: list, gap: list, cb: list, co_tq: bool
                  ) -> tuple[list, dict]:
    """Tổng quan hỏng: bảng tí hon (vốn gấp vào Tổng quan) ghi thành tab riêng ở CUỐI, hoặc
    dưới tab dữ liệu đầu nếu thêm tab cũng hỏng. -> ([TabDaGhi], kết quả kiểm). Ghi hỏng →
    cảnh báo + kiểm THIẾU cho từng bảng (không bao giờ im lặng)."""
    da_co = [t.ten for t in da_ghi]
    tabs = []
    for b in gap:
        ten = ten_tab_sach(b.ten, da_co)
        da_co.append(ten)
        tabs.append(TabKH(ten, b, None, 0, len(b.dong)))
    dau = da_ghi[0] if da_ghi else None

    def thieu(ly_do):
        return [], {"day_du": False, "cau": "", "tabs": [
            {"tab": t.ten, "du_kien": len(t.dong), "cot": len(t.bang.cot), "ket": "thieu",
             "cau": f"bảng nhỏ (vốn ở Tổng quan) KHÔNG ghi được: {ly_do}"} for t in tabs]}
    if dau is None:
        return thieu("không có tab dữ liệu để ghi nối")
    cung = [t for t in da_ghi if t.sheet_id == dau.sheet_id]
    da_dung = max(t.dong_dau + t.so_dong + ((1 + t.dong_tong) if t.dong_tong else 0)
                  for t in cung)
    vi_tri = len({t.sheet_id for t in da_ghi}) + (1 if co_tq else 0)
    try:
        them = _ghi_tabs(tok, tabs, cb, sid_dau=None, vi_tri0=vi_tri,
                         noi=(dau.sheet_id, da_dung, dau.ten))
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Ghi bảng nhỏ (vốn ở Tổng quan) thành tab riêng", e, du=False)
        return thieu(type(e).__name__)
    return them, kiem_ghi(tok, them)


def _ghi_tong_quan(tok, url, tq, da_ghi, gap, kiem, cb, luc, khac) -> tuple[str, dict]:
    """Thêm tab Tổng quan ở vị trí 0, ghi + trang trí, đọc lại kiểm. Không ném.
    -> (sheet_id hoặc "", mục kiểm {"tab": "Tổng quan", "ket": du/thieu/chua_kiem, ...})."""
    def hong(viec, e):
        _canh(cb, viec, e, du=False)
        return {"tab": TAB_TONG_QUAN, "du_kien": 0, "cot": "", "ket": "thieu",
                "cau": f"không ghi được Tổng quan ({type(e).__name__}) — số liệu chính và ghi "
                       "chú nằm ở `ghi_chu_sheet` của kết quả tool"
                       + ("; bảng nhỏ chuyển sang tab riêng" if gap else "")}
    try:
        sid = _them_tab(tok, TAB_TONG_QUAN, 0)
    except Exception as e:  # noqa: BLE001
        return "", hong("Thêm tab Tổng quan", e)
    dong, vai = dung_tong_quan(tq, da_ghi, gap, kiem, url, luc, khac)
    try:
        _viet_tong_quan(tok, sid, dong, (LUOI_DONG, LUOI_COT), cb)
    except Exception as e:  # noqa: BLE001
        return sid, hong("Ghi tab Tổng quan", e)
    _trang_tri_tong_quan(tok, sid, dong, vai, cb)
    return sid, _kiem_tong_quan(tok, sid, dong, vai, tq.tieu_de)


def _kiem_tong_quan(tok: str, sid: str, dong: list, vai: dict, tieu_de: str) -> dict:
    """Đọc lại Tổng quan: dòng tiêu đề + dòng cuối có chữ ở cột A (ghi chú / mục lục)."""
    cuoi = max((i for i, r in enumerate(dong, 1) if r and r[0] not in ("", None)), default=1)
    tg = TabDaGhi(TAB_TONG_QUAN, sid, [Cot(str(tieu_de))], cuoi - 1, 1, r_kiem=cuoi)
    k = kiem_ghi(tok, [tg])["tabs"][0]
    k.update(du_kien=len(dong), cot=vai["rong"])
    if k["ket"] == "du":
        k["cau"] = f"Đã ghi đủ {len(dong)} dòng (số liệu chính, mục lục, ghi chú)"
    elif k["ket"] == "thieu":
        k["cau"] = "THIẾU: đọc lại không thấy đủ nội dung Tổng quan"
    return k


def ghi_lai_tong_quan(tok: str, sid: str, url: str, tq: TongQuan, tabs: list,
                      kiem: dict | None = None, gap: list | None = None,
                      canh_bao: list | None = None, so_dong_cu: int = 0) -> dict:
    """Ghi lại Tổng quan vào tab có sẵn (ghi nối brand vào sheet của lượt, việc nền). Không ném.

    Thứ tự an toàn (review 09/10/2026): ghi bản MỚI xuống DƯỚI bản cũ (dòng so_dong_cu+1…),
    ghi được rồi mới XOÁ các dòng bản cũ (1..so_dong_cu) — bản mới dồn lên đầu, ô "" không
    chặn chữ tràn, kiểu/gộp ô cũ đi theo dòng bị xoá. Ghi hỏng thì bản cũ còn nguyên. Xong
    thì trang trí và đọc lại kiểm.
    -> {"so_dong": số dòng tab đang dùng, "ok": bool, "kiem": mục kiểm Tổng quan}."""
    cb = canh_bao if canh_bao is not None else []
    dong, vai = dung_tong_quan(tq, tabs, gap or [], kiem, url)
    cu = max(0, int(so_dong_cu or 0))
    luoi = _luoi(tok).get(sid, (0, 0))
    try:
        _viet_tong_quan(tok, sid, dong, luoi, cb, dong_dau=cu + 1)
    except Exception as e:  # noqa: BLE001
        _canh(cb, "Ghi lại tab Tổng quan (bản cũ giữ nguyên, CHƯA cập nhật)", e, du=False)
        # Có thể đã ghi được MỘT PHẦN bản mới (dòng cu+1…): tính cả vào số dòng đang dùng để
        # lần ghi lại sau xoá hết, không để sót dòng cũ dưới bản mới (review 09/10).
        return {"so_dong": cu + len(dong), "ok": False, "kiem": {
            "tab": TAB_TONG_QUAN, "du_kien": len(dong), "cot": vai["rong"], "ket": "thieu",
            "cau": f"không ghi lại được Tổng quan ({type(e).__name__}) — tab còn bản cũ, "
                   "số liệu/ghi chú mới chưa vào sheet"}}
    if cu:
        try:
            _goi("DELETE", f"/open-apis/sheets/v2/spreadsheets/{tok}/dimension_range",
                 body={"dimension": {"sheetId": sid, "majorDimension": "ROWS",
                                     "startIndex": 1, "endIndex": cu}})
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Xoá bản Tổng quan cũ (bản mới nằm BÊN DƯỚI bản cũ)", e, du=False)
            return {"so_dong": cu + len(dong), "ok": False, "kiem": {
                "tab": TAB_TONG_QUAN, "du_kien": len(dong), "cot": vai["rong"],
                "ket": "chua_kiem",
                "cau": f"bản Tổng quan mới ghi ở dòng {cu + 1} trở đi, bản cũ chưa xoá được"}}
    # Dọn đuôi: mọi dòng lưới SAU bản mới (sót từ lần ghi dở trước, kể cả không được tính)
    # bỏ hẳn — Tổng quan chỉ còn đúng bản mới.
    hang = _luoi(tok).get(sid, (0, 0))[0]
    if hang > len(dong):
        try:
            _goi("DELETE", f"/open-apis/sheets/v2/spreadsheets/{tok}/dimension_range",
                 body={"dimension": {"sheetId": sid, "majorDimension": "ROWS",
                                     "startIndex": len(dong) + 1, "endIndex": hang}})
        except Exception as e:  # noqa: BLE001
            _canh(cb, "Dọn dòng thừa dưới Tổng quan", e)
    _trang_tri_tong_quan(tok, sid, dong, vai, cb)
    k = _kiem_tong_quan(tok, sid, dong, vai, tq.tieu_de)
    return {"so_dong": len(dong), "ok": k["ket"] != "thieu", "kiem": k}


def ghi_tong_quan_vao(tok: str, sid: str, url: str, tq: TongQuan, tabs: list,
                      kiem: dict | None = None, gap: list | None = None,
                      canh_bao: list | None = None, so_dong_cu: int = 0) -> int:
    """Như `ghi_lai_tong_quan`, chỉ trả số dòng tab đang dùng (giữ cho bên gọi cũ)."""
    return ghi_lai_tong_quan(tok, sid, url, tq, tabs, kiem, gap, canh_bao,
                             so_dong_cu)["so_dong"]


def gop_kiem_tong_quan(kiem: dict, ket_tq: dict) -> dict:
    """Gộp mục kiểm Tổng quan (của `ghi_lai_tong_quan`) vào kết quả kiểm các tab dữ liệu:
    Tổng quan hỏng thì `day_du` không còn True; tab dữ liệu chưa kiểm được (`day_du` vào
    không phải True, kể cả `kiem`=None) thì kết quả gộp KHÔNG BAO GIỜ True."""
    vao = kiem or {}
    gop = _gop_kiem([vao, {"tabs": [ket_tq["kiem"]]}])
    dd = vao.get("day_du")
    if dd is True or gop["day_du"] is False:
        return gop
    if dd is False:
        return dict(gop, day_du=False, cau="CẢNH BÁO GHI THIẾU: "
                    + (vao.get("cau") or "các tab dữ liệu chưa đủ"))
    tabs = gop["tabs"] + [{"tab": "(các tab dữ liệu)", "du_kien": 0, "cot": "",
                           "ket": "chua_kiem", "cau": vao.get("cau") or "chưa kiểm được"}]
    return {"day_du": None, "tabs": tabs,
            "cau": "Chưa kiểm được ghi đủ các tab dữ liệu"
                   + (f" ({vao['cau']})" if vao.get("cau") else "") + "."}
