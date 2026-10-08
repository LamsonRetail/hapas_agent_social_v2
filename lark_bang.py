"""Đọc NGUYÊN một Base hoặc Sheet của Lark thành markdown — CHỈ ĐỌC, không ghi gì.

Dùng ở ba chỗ:
  • tool `doc_bang` (`bang_tool.py`): hỏi tới Base/Sheet nào thì đọc nguyên cái đó NGAY
    LÚC HỎI — mọi bảng, mọi cột, mọi dòng (tới trần).
  • tool `dem_bang` (`dem_bang_tool.py`): đếm/cộng bằng CODE qua `doc_tho` — đọc thô
    từng ô, không qua markdown.
  • nhập Wiki (`scripts/nap_wiki.py`): node Base/Sheet chỉ nhập một THẺ MỤC LỤC (tên
    bảng, cột, số dòng, link) để RAG tìm thấy; nội dung thật đọc qua `doc_bang`.

VÌ SAO KHÔNG NHẬP CẢ BẢNG VÀO KHO
RAG của platform cắt tài liệu thành mẩu ~1.200 ký tự rồi mỗi câu hỏi chỉ đưa 4 mẩu vào
prompt. Câu hỏi về bảng ("bao nhiêu việc đang trễ", "ai phụ trách nhiều nhất") cần nhìn
CẢ bảng — 4 mẩu rời thì model trả lời sai mà nghe vẫn chắc chắn. Nên kho chỉ giữ mục
lục, còn đọc thì đọc nguyên và đọc bản mới nhất.

Mọi lời gọi đi bằng token BOT: bot không được chia sẻ Base/Sheet nào thì không đọc
được cái đó. Còn NGƯỜI HỎI có quyền không là việc của `bang_tool` — xem ở đó.
"""
from __future__ import annotations

import datetime
import re
import unicodedata
from urllib.parse import parse_qs, urlparse

import lark_client as lark

#: Trần một lần đọc — model phải còn chỗ để suy nghĩ và trả lời.
MAX_DONG = 2000          # tổng số dòng qua mọi bảng
MAX_KY_TU = 150_000      # tổng markdown trả về
MAX_BANG = 30            # số bảng / số tab tối đa
MAX_COT = 60             # cột mỗi bảng
_VN = datetime.timezone(datetime.timedelta(hours=7))

# Loại cột Base có giá trị là mốc thời gian mili-giây: 5 ngày, 1001 tạo lúc, 1002 sửa lúc.
_COT_NGAY = {5, 1001, 1002}


# ───────────────────────────── nhận diện link ─────────────────────────────
def nhan_dien_chi_tiet(nguon: str) -> tuple[str, str, str, str] | None:
    """Như :func:`nhan_dien`, kèm loại phạm vi ``table``/``sheet``.

    Một link có phạm vi trùng hoặc mâu thuẫn bị từ chối. Không được âm thầm chọn
    giá trị đầu tiên vì giá trị còn lại có thể trỏ sang bảng nhạy cảm.
    """
    s = (nguon or "").strip()
    m = re.match(r"^(sheet|base):([A-Za-z0-9]+)(?:_([A-Za-z0-9]+))?$", s)
    if m:
        loai = "sheet" if m.group(1) == "sheet" else "bitable"
        phu = m.group(3) or ""
        return loai, m.group(2), phu, ("sheet" if loai == "sheet" and phu else
                                      "table" if phu else "")
    try:
        u = urlparse(s)
        q = parse_qs(u.query, keep_blank_values=True)
    except ValueError:
        return None
    bang = q.get("table", [])
    trang = q.get("sheet", [])
    if len(bang) > 1 or len(trang) > 1 or (bang and trang):
        return None
    if bang and (not bang[0] or not re.fullmatch(r"[A-Za-z0-9]+", bang[0])):
        return None
    if trang and (not trang[0] or not re.fullmatch(r"[A-Za-z0-9]+", trang[0])):
        return None
    phu, kieu_phu = (bang[0], "table") if bang else ((trang[0], "sheet") if trang else ("", ""))
    m = re.search(r"/base/([A-Za-z0-9]+)", u.path)
    if m:
        return None if kieu_phu == "sheet" else ("bitable", m.group(1), phu, kieu_phu)
    m = re.search(r"/sheets/([A-Za-z0-9]+)", u.path)
    if m:
        return None if kieu_phu == "table" else ("sheet", m.group(1), phu, kieu_phu)
    m = re.search(r"/wiki/([A-Za-z0-9]+)", u.path)
    if m:
        return "wiki", m.group(1), phu, kieu_phu
    return None


def nhan_dien(nguon: str) -> tuple[str, str, str] | None:
    """Link/mã → (loại, token, phụ). Loại: "bitable" | "sheet" | "wiki".

    Nhận: link /base/…, /sheets/…, /wiki/…; và mã bảng nhúng trong tài liệu Wiki mà
    thẻ mục lục ghi dạng `sheet:<token>_<sheet_id>` hoặc `base:<app_token>_<table_id>`.
    `phụ` = sheet_id / table_id nếu link chỉ đúng một tab / một bảng.
    """
    d = nhan_dien_chi_tiet(nguon)
    return d[:3] if d else None


def giai_wiki(node_token: str) -> tuple[str, str] | None:
    """Node Wiki → (obj_type, obj_token). None nếu bot không đọc được node."""
    try:
        d = lark.call("GET", "/open-apis/wiki/v2/spaces/get_node",
                      query={"token": node_token, "obj_type": "wiki"})
    except Exception:
        return None
    n = ((d or {}).get("data") or {}).get("node") or {}
    if not n.get("obj_token"):
        return None
    return str(n.get("obj_type") or ""), str(n["obj_token"])


# ───────────────────────────── giá trị ô ─────────────────────────────
def gia_tri(v, loai: int | None = None) -> str:
    """Giá trị một ô Base (đủ kiểu JSON Lark trả) → chữ một dòng."""
    if v is None:
        return ""
    if loai in _COT_NGAY and isinstance(v, (int, float)) and v > 10**11:
        return datetime.datetime.fromtimestamp(v / 1000, _VN).strftime("%Y-%m-%d %H:%M")
    if isinstance(v, bool):
        return "có" if v else "không"
    if isinstance(v, (int, float, str)):
        return str(v)
    if isinstance(v, list):
        return ", ".join(x for x in (gia_tri(e, loai) for e in v) if x)
    if isinstance(v, dict):
        # công thức / tra cứu: {"type": .., "value": [...]}
        if "value" in v and not {"text", "name"} & v.keys():
            return gia_tri(v.get("value"), loai)
        for k in ("text", "name", "full_address", "en_name", "email", "link", "url"):
            if v.get(k):
                return str(v[k])
        if v.get("record_ids"):
            return ", ".join(map(str, v["record_ids"]))
    return str(v)


def _o(s: str) -> str:
    """Ô markdown: một dòng, không phá bảng."""
    return re.sub(r"\s*\n\s*", " / ", str(s)).replace("|", "\\|").strip()


def _bang_md(ten: str, cot: list[str], dong: list[list[str]], tong: int) -> str:
    dau = f"## {ten} — {tong} dòng" + (f" (đọc {len(dong)})" if len(dong) < tong else "")
    if not cot:
        return dau + "\n\n(bảng trống)\n"
    ra = [dau, "", "| " + " | ".join(_o(c) for c in cot) + " |",
          "|" + "---|" * len(cot)]
    ra += ["| " + " | ".join(_o(x) for x in r) + " |" for r in dong]
    return "\n".join(ra) + "\n"


# ───────────────────────────── gọi Lark (có phân trang) ─────────────────────────────
def _trang(path: str, query: dict, khoa: str = "items", toi_da: int = 10_000) -> list[dict]:
    ra: list[dict] = []
    tok = ""
    for _ in range(100):
        q = dict(query)
        if tok:
            q["page_token"] = tok
        d = lark.call("GET", path, query=q)
        data = (d or {}).get("data") or {}
        ra.extend(data.get(khoa) or [])
        if len(ra) >= toi_da or not data.get("has_more"):
            break
        tok = data.get("page_token") or ""
        if not tok:
            break
    return ra[:toi_da]


# ───────────────────────────── Base ─────────────────────────────
def doc_base(app_token: str, chi_bang: str = "", *, ca_dong: bool = True) -> dict:
    """Đọc cả Base (hoặc chỉ một bảng). `ca_dong=False` = chỉ mục lục: bảng, cột, số dòng.

    Trả {ten, loai, bang: [{ten, cot, tong_dong, da_doc}], noi_dung, bi_cat}.
    Lỗi Lark (bot không có quyền…) ném ra nguyên — nơi gọi quyết định nói gì.
    """
    try:
        ten = ((lark.call("GET", f"/open-apis/bitable/v1/apps/{app_token}")
                .get("data") or {}).get("app") or {}).get("name") or ""
    except Exception:
        ten = ""
    bangs = _trang(f"/open-apis/bitable/v1/apps/{app_token}/tables", {"page_size": 100})
    if chi_bang:
        bangs = [b for b in bangs if b.get("table_id") == chi_bang]
        if not bangs:
            raise LookupError(f"Không thấy bảng '{chi_bang}' trong Base; không đọc bảng khác.")
    bangs = bangs[:MAX_BANG]
    con_dong = MAX_DONG
    phan, tom, bi_cat = [], [], False
    for b in bangs:
        tid = b.get("table_id")
        fields = _trang(f"/open-apis/bitable/v1/apps/{app_token}/tables/{tid}/fields",
                        {"page_size": 100})[:MAX_COT]
        cot = [f.get("field_name") or "" for f in fields]
        loai = {f.get("field_name"): f.get("type") for f in fields}
        dong: list[list[str]] = []
        if ca_dong:
            recs = _trang(f"/open-apis/bitable/v1/apps/{app_token}/tables/{tid}/records",
                          {"page_size": 500}, toi_da=con_dong + 1) if con_dong > 0 else []
            tong = len(recs)
            for r in recs[:max(con_dong, 0)]:
                f = r.get("fields") or {}
                dong.append([gia_tri(f.get(c), loai.get(c)) for c in cot])
            con_dong -= len(dong)
            bi_cat = bi_cat or tong > len(dong) or con_dong <= 0
            phan.append(_bang_md(b.get("name") or tid, cot, dong, tong))
        else:
            d = lark.call("GET", f"/open-apis/bitable/v1/apps/{app_token}/tables/{tid}/records",
                          query={"page_size": 1})
            tong = int(((d or {}).get("data") or {}).get("total") or 0)
        tom.append({"ten": b.get("name") or tid, "cot": cot, "tong_dong": tong,
                    "da_doc": len(dong)})
    return _gom(ten or app_token, "Base", tom, phan, bi_cat)


# ───────────────────────────── Sheet ─────────────────────────────
def _ten_cot(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def doc_sheet(tok: str, chi_sheet: str = "", *, ca_dong: bool = True) -> dict:
    """Đọc cả Sheet (mọi tab) hoặc một tab. Dòng đầu mỗi tab coi là tiêu đề cột."""
    try:
        ten = ((lark.call("GET", f"/open-apis/sheets/v3/spreadsheets/{tok}")
                .get("data") or {}).get("spreadsheet") or {}).get("title") or ""
    except Exception:
        ten = ""
    tabs = ((lark.call("GET", f"/open-apis/sheets/v3/spreadsheets/{tok}/sheets/query")
             .get("data") or {}).get("sheets")) or []
    tabs = [t for t in tabs if (t.get("resource_type") or "sheet") == "sheet"]
    if chi_sheet:
        tabs = [t for t in tabs if t.get("sheet_id") == chi_sheet]
        if not tabs:
            raise LookupError(f"Không thấy tab '{chi_sheet}' trong Sheet; không đọc tab khác.")
    tabs = tabs[:MAX_BANG]
    con_dong = MAX_DONG
    phan, tom, bi_cat = [], [], False
    for t in tabs:
        sid = t.get("sheet_id")
        g = t.get("grid_properties") or {}
        so_dong = int(g.get("row_count") or 0)
        so_cot = min(int(g.get("column_count") or 0), MAX_COT)
        cot: list[str] = []
        dong: list[list[str]] = []
        tong = 0
        if so_dong and so_cot:
            # Mục lục chỉ cần dòng tiêu đề; đọc thật thì tới trần dòng còn lại (+1 tiêu đề).
            doc_toi = min(so_dong, (max(con_dong, 0) + 1) if ca_dong else 1)
            d = lark.call("GET", f"/open-apis/sheets/v2/spreadsheets/{tok}/values/"
                                 f"{sid}!A1:{_ten_cot(so_cot)}{doc_toi}",
                          query={"valueRenderOption": "ToString",
                                 "dateTimeRenderOption": "FormattedString"})
            vals = ((((d or {}).get("data") or {}).get("valueRange") or {}).get("values")) or []
            # Bỏ dòng trống ở cuối — lưới Sheet mặc định dài hơn dữ liệu thật.
            while vals and not any(str(x or "").strip() for x in vals[-1]):
                vals.pop()
            if vals:
                cot = [gia_tri(x) for x in vals[0]]
                dong = [[gia_tri(x) for x in r] for r in vals[1:]] if ca_dong else []
                tong = len(vals) - 1
                if so_dong > doc_toi:
                    # Chưa đọc hết lưới: không biết chắc phần sau có dữ liệu, báo là CÓ THỂ còn.
                    tong = max(tong, so_dong - 1)
        if ca_dong:
            con_dong -= len(dong)
            bi_cat = bi_cat or tong > len(dong)
            phan.append(_bang_md(t.get("title") or sid, cot, dong, tong))
        tom.append({"ten": t.get("title") or sid, "cot": cot, "tong_dong": tong,
                    "da_doc": len(dong)})
    return _gom(ten or tok, "Sheet", tom, phan, bi_cat)


def _gom(ten: str, loai: str, tom: list[dict], phan: list[str], bi_cat: bool) -> dict:
    noi_dung = f"# {loai}: {ten}\n\n" + "\n".join(phan)
    if len(noi_dung) > MAX_KY_TU:
        noi_dung = noi_dung[:MAX_KY_TU] + "\n\n…(đã cắt: vượt trần ký tự một lần đọc)"
        bi_cat = True
    return {"ten": ten, "loai": loai, "bang": tom, "noi_dung": noi_dung, "bi_cat": bi_cat}


# ───────────────────────────── đọc THÔ (cho tool đếm) ─────────────────────────────
# `doc_sheet`/`doc_base` trả markdown để MODEL đọc: ô nhiều dòng bị nối thành " / ",
# ô danh sách Base bị nối bằng ", ", dòng 1 bị coi là tiêu đề. Đủ để đọc, không đủ để
# ĐẾM: tách lại " / " hay ", " là đoán (đáp án "Có, đã mua" vốn chứa dấu phẩy). Nên tool
# đếm (`dem_bang_tool.py`) đọc qua cửa riêng này: giữ nguyên từng ô, từng lựa chọn, và
# để nơi đếm tự quyết dòng nào là tiêu đề.

#: Loại cột Base mà mỗi phần tử danh sách là MỘT lựa chọn riêng: 4 chọn nhiều, 11 người,
#: 18/21 liên kết bảng, 23 nhóm chat. Loại khác (văn bản 1 cũng là danh sách — các mẩu
#: chữ của CÙNG một ô) thì gộp về một chuỗi.
_COT_DANH_SACH = {4, 11, 18, 21, 23}


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


def _so_tho(v) -> str:
    """Số từ API → chữ KHÔNG mơ hồ cho bộ đọc số của tool đếm.

    Bộ đọc số coi "1.500" là một nghìn năm trăm (dấu chấm phân cách nghìn kiểu VN). Số
    thực 1.5 thì không sao, nhưng 1.125 in ra "1.125" sẽ bị đọc thành 1125. Thêm một số 0
    ("1.1250") để phần lẻ không bao giờ đúng 3 chữ số — giá trị không đổi.
    """
    if isinstance(v, bool):
        return "có" if v else "không"
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer()):
        return str(int(v))
    s = repr(float(v))
    if "e" in s or "E" in s:
        s = f"{v:.10f}".rstrip("0")
    if "." in s and len(s.split(".")[1]) == 3:
        s += "0"
    return s


def _o_sheet(x) -> list[str]:
    """Một ô Sheet → [chuỗi nguyên văn] (giữ xuống dòng), [] nếu trống."""
    if x is None:
        return []
    if isinstance(x, (int, float)):
        s = _so_tho(x)
    elif isinstance(x, list):
        # Ô chữ có link/nhắc tên: API trả các MẨU của cùng một ô → nối liền, không phẩy.
        s = "".join(gia_tri(e) for e in x)
    else:
        s = gia_tri(x)
    return [s] if s.strip() else []


def _o_base(v, loai: int | None) -> list[str]:
    """Một ô Base → danh sách chuỗi; cột chọn nhiều/người giữ TỪNG lựa chọn riêng."""
    if v is None or v == "" or v == []:
        return []
    if isinstance(v, (int, float)) and not isinstance(v, bool) and loai not in _COT_NGAY:
        return [_so_tho(v)]
    if isinstance(v, list) and loai in _COT_DANH_SACH:
        return [s for s in (gia_tri(e, loai) for e in v) if s.strip()]
    if isinstance(v, list) and loai == 1:
        s = "".join(gia_tri(e, loai) for e in v)
    else:
        s = gia_tri(v, loai)
    return [s] if s.strip() else []


def _chon(ds: list[dict], chi: str, khoa_id: str, khoa_ten: str, *, chi_id: bool = False
          ) -> list[dict]:
    """Lọc bảng/tab theo mã HOẶC tên (không phân biệt hoa thường, dấu). Không khớp → []."""
    if not chi:
        return ds
    co = [t for t in ds if t.get(khoa_id) == chi]
    if co or chi_id:
        return co
    k = _bo_dau(chi)
    co = [t for t in ds if _bo_dau(t.get(khoa_ten) or "") == k]
    if co:
        return co
    co = [t for t in ds if k and k in _bo_dau(t.get(khoa_ten) or "")]
    return co if len(co) == 1 else []


def doc_tho(loai: str, token: str, phu: str = "", *, strict_scope: bool = False) -> dict:
    """Đọc THÔ từng ô của Sheet (mọi dòng của vùng đã dùng, KỂ CẢ dòng 1) hoặc Base.

    `phu` = mã HOẶC tên tab/bảng; bỏ trống = mọi tab/bảng. Trả
    {ten, loai, bang: [{ten, id, luoi, loai_cot, bi_cat}], tat_ca: [tên tab/bảng]}.
    `luoi[dòng][cột]` là danh sách chuỗi: Sheet mỗi ô tối đa MỘT chuỗi nguyên văn (giữ
    xuống dòng); Base dòng 1 là tên cột, ô chọn nhiều/người giữ từng lựa chọn riêng.
    `loai_cot` = mã loại cột Base (Sheet: None). Không khớp `phu` → `bang` rỗng, nơi gọi
    báo lại bằng `tat_ca`. Cùng trần với `doc`: MAX_DONG dòng, MAX_BANG bảng, MAX_COT cột.
    Lỗi Lark ném ra nguyên — như `doc`.
    """
    if loai == "sheet":
        return _tho_sheet(token, phu, strict_scope=strict_scope)
    if loai == "bitable":
        return _tho_base(token, phu, strict_scope=strict_scope)
    raise RuntimeError(f"loại '{loai}' không phải Base hay Sheet")


def _tho_sheet(tok: str, chi: str, *, strict_scope: bool = False) -> dict:
    try:
        ten = ((lark.call("GET", f"/open-apis/sheets/v3/spreadsheets/{tok}")
                .get("data") or {}).get("spreadsheet") or {}).get("title") or ""
    except Exception:
        ten = ""
    tabs = ((lark.call("GET", f"/open-apis/sheets/v3/spreadsheets/{tok}/sheets/query")
             .get("data") or {}).get("sheets")) or []
    tabs = [t for t in tabs if (t.get("resource_type") or "sheet") == "sheet"]
    tat_ca = [t.get("title") or t.get("sheet_id") for t in tabs]
    con_dong = MAX_DONG
    ra = []
    for t in _chon(tabs, chi, "sheet_id", "title", chi_id=strict_scope)[:MAX_BANG]:
        sid = t.get("sheet_id")
        g = t.get("grid_properties") or {}
        so_dong = int(g.get("row_count") or 0)
        so_cot = min(int(g.get("column_count") or 0), MAX_COT)
        luoi: list[list[list[str]]] = []
        doc_toi = min(so_dong, max(con_dong, 0))
        if doc_toi and so_cot:
            d = lark.call("GET", f"/open-apis/sheets/v2/spreadsheets/{tok}/values/"
                                 f"{sid}!A1:{_ten_cot(so_cot)}{doc_toi}",
                          query={"valueRenderOption": "ToString",
                                 "dateTimeRenderOption": "FormattedString"})
            vals = ((((d or {}).get("data") or {}).get("valueRange") or {}).get("values")) or []
            luoi = [[_o_sheet(x) for x in (list(r or []) + [None] * so_cot)[:so_cot]]
                    for r in vals]
            # Lưới Sheet mặc định dài hơn dữ liệu thật (khảo sát 52 dòng trên lưới 191).
            while luoi and not any(luoi[-1]):
                luoi.pop()
        con_dong -= len(luoi)
        ra.append({"ten": t.get("title") or sid, "id": sid, "luoi": luoi, "loai_cot": None,
                   # Chưa đọc hết lưới: không biết phần sau có dữ liệu không → báo CÓ THỂ cắt.
                   "bi_cat": so_dong > doc_toi})
    return {"ten": ten or tok, "loai": "Sheet", "bang": ra, "tat_ca": tat_ca}


def _tho_base(app_token: str, chi: str, *, strict_scope: bool = False) -> dict:
    try:
        ten = ((lark.call("GET", f"/open-apis/bitable/v1/apps/{app_token}")
                .get("data") or {}).get("app") or {}).get("name") or ""
    except Exception:
        ten = ""
    bangs = _trang(f"/open-apis/bitable/v1/apps/{app_token}/tables", {"page_size": 100})
    tat_ca = [b.get("name") or b.get("table_id") for b in bangs]
    con_dong = MAX_DONG
    ra = []
    for b in _chon(bangs, chi, "table_id", "name", chi_id=strict_scope)[:MAX_BANG]:
        tid = b.get("table_id")
        fields = _trang(f"/open-apis/bitable/v1/apps/{app_token}/tables/{tid}/fields",
                        {"page_size": 100})[:MAX_COT]
        cot = [f.get("field_name") or "" for f in fields]
        loai_cot = [f.get("type") for f in fields]
        recs = _trang(f"/open-apis/bitable/v1/apps/{app_token}/tables/{tid}/records",
                      {"page_size": 500}, toi_da=con_dong + 1) if con_dong > 0 else []
        dung = recs[:max(con_dong, 0)]
        luoi = [[[c] if c else [] for c in cot]]
        for r in dung:
            f = r.get("fields") or {}
            luoi.append([_o_base(f.get(c), l) for c, l in zip(cot, loai_cot)])
        con_dong -= len(dung)
        ra.append({"ten": b.get("name") or tid, "id": tid, "luoi": luoi, "loai_cot": loai_cot,
                   "bi_cat": len(recs) > len(dung)})
    return {"ten": ten or app_token, "loai": "Base", "bang": ra, "tat_ca": tat_ca}


def doc(loai: str, token: str, phu: str = "", *, ca_dong: bool = True) -> dict:
    """Cửa chung: loại đã giải (bitable | sheet) → đọc."""
    if loai == "bitable":
        return doc_base(token, phu, ca_dong=ca_dong)
    if loai == "sheet":
        return doc_sheet(token, phu, ca_dong=ca_dong)
    raise RuntimeError(f"loại '{loai}' không phải Base hay Sheet")


def the_muc_luc(kq: dict, cach_goi: str) -> str:
    """Thẻ mục lục cho kho RAG: đủ để TÌM thấy, không chứa dữ liệu dòng."""
    dong = [f"Đây là một {kq['loai']} trên Lark gồm {len(kq['bang'])} bảng:"]
    for b in kq["bang"]:
        dong.append(f"- {b['ten']} ({b['tong_dong']} dòng): cột "
                    + (", ".join(c for c in b["cot"] if c) or "—"))
    dong.append("")
    dong.append(f"Kho chỉ giữ mục lục này. Cần số liệu hay nội dung trong {kq['loai']} "
                f"thì gọi tool `doc_bang` với `{cach_goi}` để đọc NGUYÊN, bản mới nhất.")
    return "\n".join(dong)
