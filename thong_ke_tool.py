"""Tool `tao_sheet_thong_ke` — lập một Lark Sheet THỐNG KÊ / "dashboard" MỚI, số do CODE đếm.

VÌ SAO CÓ (01/10 và 07/10/2026)
Người dùng nhờ "gán nhãn từng bình luận và thống kê", "tạo dashboard thống kê tỉ lệ tiêu cực
tích cực" từ Sheet bình luận do chính tool của Mark xuất. Mark trả lời là không tạo được
Sheet, nhờ người dùng tạo Sheet trống, rồi dán số thống kê thô vào chat. Tool này tạo Sheet
mới (bot là chủ, cấp quyền SỬA cho người hỏi như mọi tool xuất Sheet) qua lớp trình bày
chung `trinh_bay_sheet.xuat` (Tổng quan, tab đánh số, đọc lại kiểm `day_du`/`kiem_ghi`).

HAI NGUỒN DỮ LIỆU
(a) `nguon` = link Sheet/Base (ưu tiên): mở CHỈ qua `bang_tool.mo_nguon` — cùng cửa quyền với
    `doc_bang`/`dem_bang` — rồi đọc thô bằng `lark_bang.doc_tho`.
(b) `du_lieu` = các dòng Mark đưa vào (vd Mark gán nhãn từng bình luận: cột Nội dung, Nhãn,
    Chủ đề). Trần `MAX_DONG_NHAP` dòng, `MAX_KY_TU_O` ký tự/ô. Mark KHÔNG đưa số tổng: không
    có tham số nào nhận số đã tính, và dòng "Tổng/Total" bị từ chối. Các dòng được ghi nguyên
    vào tab "Dữ liệu" để soát lại; Tổng quan ghi rõ nhãn do Mark (AI) gán, số do code đếm.

ĐẾM THẾ NÀO
Mọi con số đi qua `dem_bang_tool.dem` — ĐÚNG luật đếm của `dem_bang` (tự nhận dòng tiêu đề,
ô nhiều dòng = nhiều lựa chọn, gộp cách viết, bỏ cột tên/SĐT/email, cột trả lời mở không đếm,
cộng số kiểu VN, ô "%" không cộng). Tool này chỉ GHÉP kết quả đó thành bảng: đếm + % theo
từng cột nhóm, bảng chéo hai cột (số và % theo dòng), tổng/trung bình một cột số theo nhóm,
top-N dòng theo cột số. % = số / số dòng có giá trị ở cột đó. Thanh "█" chỉ là hình vẽ từ số.

BIỂU ĐỒ GỐC CỦA LARK SHEETS: KHÔNG có. Tài liệu Sheets Open API (tổng quan
https://open.feishu.cn/document/server-docs/docs/sheets-v3/overview.md, đọc 09/10/2026) chỉ
có bảng tính, tab, định dạng có điều kiện, bộ lọc, chế độ lọc, dòng/cột, vùng bảo vệ, dữ
liệu/kiểu ô/gộp ô/ảnh, ảnh nổi, kiểm dữ liệu — không có API tạo biểu đồ. Nên "biểu đồ" là
cột thanh chữ █ (Tổng quan và từng tab nhóm).
"""
from __future__ import annotations

import datetime
import re
import unicodedata
from decimal import Decimal

import apify_tool as A
import bang_tool as BT
import dem_bang_tool as DB
import lark_bang as B
import memory_store
import trinh_bay_sheet as TB

from tools.registry import registry, tool_error, tool_result  # type: ignore

TEN_TOOL = "tao_sheet_thong_ke"
MAX_DONG_NHAP = 2000
MAX_COT_NHAP = 20
MAX_KY_TU_O = 1000
MAX_NHOM_THEO = 5
MAX_CHEO = 3
#: Giá trị liệt kê mỗi bảng nhóm (còn lại gộp "Khác").
MAX_GIA_TRI = 50
#: Cột giá trị của bảng chéo (còn lại gộp "Khác").
MAX_COT_CHEO = 15
TOP_MAC_DINH = 10
TOP_TOI_DA = 50

GHI_CHU_AI = ("Nhãn/cột phân loại ở tab Dữ liệu do Mark (AI) gán cho từng dòng — có thể sai, "
              "soát lại ở tab Dữ liệu. Mọi số đếm, %, tổng và trung bình do CODE tính từ "
              "chính các dòng đó.")
GHI_CHU_CODE = ("Số đếm, %, tổng và trung bình do CODE tính trên mọi dòng của nguồn (cùng "
                "luật đếm với dem_bang): % tính trên số dòng có giá trị ở cột đó.")

SCHEMA = {
    "name": TEN_TOOL,
    "description": (
        "Tạo MỘT Lark Sheet thống kê / dashboard MỚI (bot tạo, cấp quyền sửa cho người hỏi) "
        "— số đếm, %, bảng chéo, tổng/trung bình do CODE tính. Dùng khi được nhờ 'tạo "
        "dashboard', 'thống kê ra sheet', 'tỉ lệ tích cực/tiêu cực', 'gán nhãn từng bình "
        "luận và thống kê'. KHÔNG bảo người dùng tạo Sheet trống, KHÔNG dán bảng số thô vào "
        "chat thay cho Sheet.\n"
        "NGUỒN (chọn một):\n"
        "- `nguon` = link Sheet/Base (ưu tiên — vd Sheet bình luận Mark đã xuất, có cột Sắc "
        "thái). Người hỏi phải có quyền xem (cùng luật `doc_bang`). Nhiều tab thì nêu `tab`.\n"
        "- `du_lieu` = {cot: [tên cột], dong: [[ô…], …]} — các dòng Mark tự gán nhãn (vd "
        "Nội dung, Nhãn, Chủ đề), tối đa 2.000 dòng. CHỈ đưa từng dòng gốc + nhãn; TUYỆT ĐỐI "
        "không đưa số đếm, %, dòng tổng — code tự đếm.\n"
        "`nhom_theo` = 1–5 cột để đếm theo nhóm (vd ['Sắc thái','Nền tảng']); `cheo` = cặp "
        "cột cho bảng chéo (vd [['Nền tảng','Sắc thái']]); `cot_so` = một cột số để cộng/"
        "trung bình theo nhóm và lấy top (vd 'View').\n"
        "KHI TRẢ LỜI: gửi link, chép NGUYÊN `cau_so` và `kiem_ghi`; nhãn do Mark gán thì nói "
        "rõ nhãn là AI gán, số do code đếm. Bị từ chối vì quyền thì chuyển NGUYÊN lời hướng dẫn."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "nguon": {"type": "string",
                      "description": "Link Sheet/Base/Wiki (hoặc `sheet:…`/`base:…`). Bỏ trống "
                                     "khi dùng `du_lieu`."},
            "tab": {"type": "string",
                    "description": "Tên hoặc mã tab/bảng khi nguồn có nhiều tab."},
            "du_lieu": {
                "type": "object",
                "description": "Các dòng Mark đưa vào (khi không có nguồn Sheet/Base).",
                "properties": {
                    "cot": {"type": "array", "items": {"type": "string"},
                            "description": "Tên cột, vd ['Nội dung','Nhãn','Chủ đề']."},
                    "dong": {"type": "array",
                             "items": {"type": "array", "items": {"type": ["string", "number",
                                                                          "null"]}},
                             "description": "Mỗi phần tử một dòng, đúng thứ tự `cot`."},
                },
            },
            "nhom_theo": {"type": "array", "items": {"type": "string"},
                          "description": "1–5 cột để đếm theo nhóm (chữ cái cột, mã câu, hoặc "
                                         "tên/đoạn tên cột)."},
            "cheo": {"type": "array",
                     "items": {"type": "array", "items": {"type": "string"}},
                     "description": "Bảng chéo: tối đa 3 cặp [cột dòng, cột cột]."},
            "cot_so": {"type": "string",
                       "description": "Một cột số (vd 'View') để cộng/trung bình theo nhóm và "
                                      "lấy top dòng."},
            "top": {"type": "integer",
                    "description": "Số dòng top theo `cot_so` (mặc định 10, tối đa 50)."},
            "dong_tieu_de": {"type": "integer",
                             "description": "Dòng tiêu đề của nguồn (đếm từ 1). Bỏ trống = tự "
                                            "nhận như dem_bang."},
            "tach_dau_phay": {"type": "boolean",
                              "description": "Tách lựa chọn theo dấu phẩy/chấm phẩy. Mặc định "
                                             "false."},
            "tieu_de": {"type": "string", "description": "Tên Sheet (tuỳ chọn)."},
        },
        "required": ["nhom_theo"],
    },
}


class LoiNhap(ValueError):
    """Đầu vào không dùng được — câu nói thẳng cho model."""


# ───────────────────────────── đầu vào ─────────────────────────────
def _ds(x) -> list[str]:
    if x is None or x == "":
        return []
    if isinstance(x, str):
        return [p.strip() for p in re.split(r"[,;]", x) if p.strip()]
    return [str(v).strip() for v in x if str(v).strip()]


def _cap_cheo(x) -> list[tuple[str, str]]:
    ra = []
    for c in x or []:
        if isinstance(c, dict):
            c = [c.get("hang") or c.get("dong"), c.get("cot")]
        if isinstance(c, str):
            c = re.split(r"\s*(?:×|\bx\b|\*|\|)\s*", c)
        c = [str(v).strip() for v in (c or []) if v is not None and str(v).strip()]
        if len(c) != 2:
            raise LoiNhap("mỗi phần tử `cheo` phải là đúng hai cột, vd ['Nền tảng','Sắc thái']")
        ra.append((c[0], c[1]))
    return ra


_DONG_TONG = {"tong", "tong cong", "total", "grand total", "cong", "sum", "tong so"}


def _o_nhap(v) -> str | int | float:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "có" if v else "không"
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = unicodedata.normalize("NFC", v).replace("\r\n", "\n").replace("\r", "\n")
        return s.strip()
    raise LoiNhap("ô trong `du_lieu.dong` chỉ được là chữ hoặc số")


def doc_nhap(du: dict) -> tuple[list[str], list[list], int]:
    """`du_lieu` → (tên cột, dòng đã làm sạch, số ô bị cắt). Ném `LoiNhap`."""
    if not isinstance(du, dict):
        raise LoiNhap("`du_lieu` phải có dạng {cot: [...], dong: [[...], ...]}")
    cot = du.get("cot")
    dong = du.get("dong")
    if not isinstance(cot, list) or not cot or not all(isinstance(c, str) and c.strip()
                                                       for c in cot):
        raise LoiNhap("`du_lieu.cot` phải là danh sách tên cột (chữ, không trống)")
    cot = [DB._gon(c)[:100] for c in cot]
    if len(cot) > MAX_COT_NHAP:
        raise LoiNhap(f"`du_lieu` có {len(cot)} cột, trần {MAX_COT_NHAP}")
    if len({c.casefold() for c in cot}) != len(cot):
        raise LoiNhap("`du_lieu.cot` có tên cột trùng nhau")
    if not isinstance(dong, list) or not dong:
        raise LoiNhap("`du_lieu.dong` trống — cần từng dòng dữ liệu")
    if len(dong) > MAX_DONG_NHAP:
        raise LoiNhap(f"`du_lieu` có {len(dong)} dòng, trần {MAX_DONG_NHAP} dòng mỗi lần. Dữ "
                      "liệu lớn hơn thì đưa lên Lark Sheet (vd Sheet bình luận đã xuất) rồi gọi "
                      "với `nguon`, hoặc chia nhỏ")
    ra, cat = [], 0
    for i, r in enumerate(dong, 1):
        if not isinstance(r, list):
            raise LoiNhap(f"dòng {i} của `du_lieu.dong` không phải danh sách ô")
        if len(r) > len(cot):
            raise LoiNhap(f"dòng {i} có {len(r)} ô, nhiều hơn {len(cot)} cột")
        hang = []
        for v in list(r) + [""] * (len(cot) - len(r)):
            v = _o_nhap(v)
            if isinstance(v, str) and len(v) > MAX_KY_TU_O:
                v, cat = v[:MAX_KY_TU_O - 1] + "…", cat + 1
            hang.append(v)
        dau = next((str(x) for x in hang if str(x).strip()), "")
        if B._bo_dau(dau).rstrip(":") in _DONG_TONG:
            raise LoiNhap(f"dòng {i} là dòng TỔNG ('{dau[:30]}') — chỉ đưa từng dòng gốc, code "
                          "tự đếm và cộng")
        if any(str(x).strip() for x in hang):
            ra.append(hang)
    if not ra:
        raise LoiNhap("`du_lieu.dong` không có dòng nào có chữ")
    return cot, ra, cat


def _luoi_tu_dong(cot: list[str], dong: list[list]) -> list[list[list[str]]]:
    """Dòng nhập → lưới y như `lark_bang.doc_tho` (dòng 1 = tiêu đề)."""
    def o(v) -> list[str]:
        s = B._so_tho(v) if isinstance(v, (int, float)) else str(v or "")
        return [s] if s.strip() else []
    return [[[c] for c in cot]] + [[o(v) for v in r] for r in dong]


# ───────────────────────────── tính (thuần) ─────────────────────────────
def _so(chu) -> Decimal | None:
    v, _ = DB.doc_so(str(chu or ""))
    return v


def _so_ra(v: Decimal):
    """Decimal → int/float để ghi Sheet (số thật, không chuỗi)."""
    return int(v) if v == v.to_integral_value() else float(v)


def thong_ke(luoi: list, nhom_theo: list[str], cheo=(), cot_so: str = "",
             top: int = TOP_MAC_DINH, *, dong_tieu_de: int | None = None,
             khong_tieu_de: bool = False, loai_cot: list | None = None,
             tach_dau_phay: bool = False) -> dict:
    """Mọi con số của Sheet thống kê — hàm THUẦN, mọi phép đếm qua `dem_bang_tool.dem`.

    Trả {n, dong_tieu_de_da_dung, nhom: [...], cheo: [...], so: {...}|None, top: [...],
    canh_bao: [...], cot_bo_qua: [...], tieu_de: {chữ cột: tên}} hoặc {"loi": ...}."""
    chung = dict(dong_tieu_de=dong_tieu_de, khong_tieu_de=khong_tieu_de, loai_cot=loai_cot,
                 tach_dau_phay=tach_dau_phay, top=MAX_GIA_TRI)
    can = list(dict.fromkeys(list(nhom_theo) + [x for c in cheo for x in c]))
    tham_do = DB.dem(luoi, cot=can, cong=[cot_so] if cot_so else None, tra_chi_so=True,
                     **chung)
    if tham_do.get("loi"):
        return {"loi": tham_do["loi"]}
    so_cot = max(len(r) for r in luoi)
    tieu_de = [""] * so_cot
    for t in tham_do.get("tieu_de") or []:
        tieu_de[DB._so_cot(t["cot"])] = t["tieu_de"]
    canh: list[str] = []
    bo_qua = {b["cot"]: b["ly_do"] for b in tham_do.get("cot_bo_qua") or []}
    ca_nhan = {j for j in range(so_cot)
               if any(f"[cột {DB.chu_cot(j)}]" in k or k == f"cột {DB.chu_cot(j)}"
                      for k in bo_qua)}

    def ten(j: int) -> str:
        return tieu_de[j] or f"cột {DB.chu_cot(j)}"

    def giai(chi: str) -> int | None:
        co = DB.tim_cot(chi, tieu_de)
        if not co:
            canh.append(f"không thấy cột '{DB._gon(chi)[:60]}'")
            return None
        if len(co) > 1:
            canh.append(f"'{DB._gon(chi)[:60]}' khớp {len(co)} cột, dùng {ten(co[0])} "
                        f"[cột {DB.chu_cot(co[0])}]")
        if co[0] in ca_nhan:
            canh.append(f"{ten(co[0])}: thông tin cá nhân — không thống kê")
            return None
        return co[0]

    n = tham_do["n"]
    j_so = giai(cot_so) if cot_so else None
    kq: dict = {"n": n, "dong_tieu_de_da_dung": tham_do["dong_tieu_de_da_dung"],
                "tieu_de_tu_nhan": tham_do.get("tieu_de_tu_nhan"),
                "tieu_de_khong_ro": bool(tham_do.get("tieu_de_khong_ro")),
                "nhom": [], "cheo": [], "so": None, "top": [], "canh_bao": canh,
                "cot_bo_qua": [f"{k}: {v}" for k, v in bo_qua.items()]}
    if j_so is not None:
        kq["ten_cot_so"] = ten(j_so)
    chu_so = DB.chu_cot(j_so) if j_so is not None else ""

    # ── Đếm theo từng cột nhóm (+ cộng cột số theo nhóm) ──
    for chi in nhom_theo:
        j = giai(chi)
        if j is None:
            continue
        L = DB.chu_cot(j)
        k = DB.dem(luoi, cot=[L], nhom_theo=L, cong=[chu_so] if chu_so else None, **chung)
        c = (k.get("cot") or [{}])[0]
        if c.get("trong"):
            canh.append(f"{ten(j)}: không dòng nào có giá trị — bỏ qua")
            continue
        if c.get("la_cau_mo"):
            canh.append(f"{ten(j)}: {c.get('so_cach_tra_loi')} giá trị khác nhau — quá nhiều "
                        "để lập nhóm (luật đếm của dem_bang); gộp nhãn rồi lập lại")
            continue
        tong_nhom = {}
        tc = (k.get("tong") or [None])[0]
        if tc and tc.get("theo_nhom"):
            # Nhóm "(trống)" của dem = dòng không có giá trị ở cột nhóm: không phải một giá
            # trị, không vào "Khác".
            tong_nhom = {DB._khoa(x["nhom"]): (_so(x["tong"]), x["so_o_so"])
                         for x in tc["theo_nhom"] if x["nhom"] != "(trống)"}
        gia_tri = [{"gia_tri": m["gia_tri"], "so": m["so"],
                    "ty_le": m["so"] / c["so_tra_loi"], "ty_le_chu": m["ty_le_tren_tra_loi"],
                    **({"tong": tong_nhom.get(DB._khoa(m["gia_tri"]), (None, 0))[0],
                        "so_o_so": tong_nhom.get(DB._khoa(m["gia_tri"]), (None, 0))[1]}
                       if chu_so else {})}
                   for m in c["gia_tri"]]
        khac = c.get("con_lai")
        if khac:
            tong_k, o_k = Decimal(0), 0
            if chu_so:
                da = {DB._khoa(m["gia_tri"]) for m in c["gia_tri"]}
                for kk, (v, o) in tong_nhom.items():
                    if kk and kk not in da and v is not None:
                        tong_k, o_k = tong_k + v, o_k + o
            gia_tri.append({"gia_tri": f"Khác ({khac['so_lua_chon']} giá trị)",
                            "so": khac["so_luot_chon"],
                            "ty_le": khac["so_luot_chon"] / c["so_tra_loi"],
                            "ty_le_chu": DB.ty_le(khac["so_luot_chon"], c["so_tra_loi"]),
                            **({"tong": tong_k, "so_o_so": o_k} if chu_so else {})})
        kq["nhom"].append({"cot": ten(j), "chu_cot": L, "so_tra_loi": c["so_tra_loi"],
                           "trong": n - c["so_tra_loi"], "nhieu": bool(c.get("la_nhieu_lua_chon")),
                           "gia_tri": gia_tri})

    # ── Bảng chéo ──
    for a, b in cheo:
        ja, jb = giai(a), giai(b)
        if ja is None or jb is None:
            continue
        if ja == jb:
            canh.append(f"bảng chéo {ten(ja)} × {ten(jb)}: hai cột trùng nhau — bỏ qua")
            continue
        La, Lb = DB.chu_cot(ja), DB.chu_cot(jb)
        k = DB.dem(luoi, cot=[Lb], nhom_theo=La, **chung)
        c = (k.get("cot") or [{}])[0]
        if c.get("trong") or c.get("la_cau_mo") or not c.get("theo_nhom"):
            canh.append(f"bảng chéo {ten(ja)} × {ten(jb)}: cột {ten(jb)} không lập nhóm được "
                        "(trống hoặc quá nhiều giá trị) — bỏ qua")
            continue
        cot_y = [m["gia_tri"] for m in c["gia_tri"][:MAX_COT_CHEO]]
        khoa_y = [DB._khoa(x) for x in cot_y]
        co_khac = len(c["gia_tri"]) > MAX_COT_CHEO or bool(c.get("con_lai"))
        hang = []
        for g in c["theo_nhom"]:
            dem_g = {DB._khoa(m["gia_tri"]): m["so"] for m in g["gia_tri"]}
            o = [dem_g.get(kk, 0) for kk in khoa_y]
            khac = (sum(v for kk, v in dem_g.items() if kk not in khoa_y)
                    + ((g.get("con_lai") or {}).get("so_luot_chon") or 0))
            hang.append({"nhom": g["nhom"], "n": g["n"], "so_tra_loi": g["so_tra_loi"],
                         "o": o, "khac": khac})
        kq["cheo"].append({"hang": ten(ja), "cot": ten(jb), "gia_tri_cot": cot_y,
                           "co_khac": co_khac, "dong": hang,
                           "nhieu": bool(c.get("la_nhieu_lua_chon"))})

    # ── Cột số: tổng/trung bình chung + top-N dòng ──
    if j_so is not None:
        k = DB.dem(luoi, cong=[chu_so], **chung)
        tc = (k.get("tong") or [None])[0] or {}
        tong = _so(tc.get("tong")) if tc.get("tong") is not None else None
        kq["so"] = {"cot": ten(j_so), "tong": tong, "so_o_so": tc.get("so_o_so", 0),
                    "so_o_bo_qua": tc.get("so_o_bo_qua", 0),
                    "phan_tram": bool(tc.get("chi_phan_tram") or tc.get("o_phan_tram_khong_cong"))}
        dong_so = []
        for i in tham_do.get("chi_so_dong_du_lieu") or []:
            chu = DB._chu_o(luoi[i][j_so]) if j_so < len(luoi[i]) else ""
            if not chu or chu.strip().endswith("%"):
                continue
            v = _so(chu)
            if v is not None:
                dong_so.append((v, i))
        dong_so.sort(key=lambda x: (-x[0], x[1]))
        cot_hien = [g["chu_cot"] for g in kq["nhom"]]
        for v, i in dong_so[:max(1, min(int(top or TOP_MAC_DINH), TOP_TOI_DA))]:
            kq["top"].append({"dong": i + 1, "gia_tri": v, "nhom": [
                DB._gon(" / ".join(luoi[i][DB._so_cot(L)])) if DB._so_cot(L) < len(luoi[i])
                else "" for L in cot_hien]})
    return kq


def cau_so(kq: dict, nguon: str) -> str:
    """Khối chữ để Mark chép NGUYÊN (số do code đếm)."""
    L = [f"{nguon}: n = {kq['n']} dòng dữ liệu (tiêu đề ở dòng "
         f"{kq['dong_tieu_de_da_dung']}).".replace("(tiêu đề ở dòng 0)", "(không có dòng tiêu đề)")]
    for g in kq["nhom"]:
        L.append(f"Theo {g['cot']} ({g['so_tra_loi']}/{kq['n']} dòng có giá trị"
                 + ("; ô nhiều lựa chọn nên tổng % có thể >100%" if g["nhieu"] else "")
                 + "): " + "; ".join(f"{m['gia_tri']} {m['so']} ({m['ty_le_chu']})"
                                     for m in g["gia_tri"][:12])
                 + ("; …(đủ ở Sheet)" if len(g["gia_tri"]) > 12 else "") + ".")
    for c in kq["cheo"]:
        L.append(f"Bảng chéo {c['hang']} × {c['cot']}: {len(c['dong'])} nhóm × "
                 f"{len(c['gia_tri_cot'])} giá trị — xem tab trong Sheet.")
    s = kq.get("so")
    if s and s["tong"] is not None and s["so_o_so"]:
        tb = s["tong"] / s["so_o_so"]
        L.append(f"Tổng {s['cot']}: {DB.so_vn(s['tong'])} trên {s['so_o_so']} ô có số "
                 f"(trung bình {DB.so_vn(tb.quantize(Decimal('0.01')))})"
                 + (f"; bỏ qua {s['so_o_bo_qua']} ô không phải số" if s["so_o_bo_qua"] else "")
                 + ".")
    for c in kq["canh_bao"]:
        L.append(f"Lưu ý: {c}.")
    return "\n".join(L)


# ───────────────────────────── dựng Sheet ─────────────────────────────
def _ten_ngan(s: str, toi_da: int = 20) -> str:
    s = DB._gon(s)
    return s if len(s) <= toi_da else s[:toi_da - 1].rstrip() + "…"


def _kieu_so(vals) -> str:
    return "so_nguyen" if all(v is None or float(v).is_integer() for v in vals) else "thap_phan"


def dung_bang(kq: dict) -> list:
    """Kết quả `thong_ke` → các `TB.Bang` (một tab mỗi cột nhóm, hai tab mỗi bảng chéo)."""
    ra = []
    s = kq.get("so")
    for g in kq["nhom"]:
        nhan = "Số lượt chọn" if g["nhieu"] else "Số dòng"
        lon = max((m["so"] for m in g["gia_tri"]), default=0)
        cot = [TB.Cot(g["cot"][:100] or "Giá trị"), TB.Cot(nhan, "so_nguyen"),
               TB.Cot("Tỉ lệ", "phan_tram")]
        if s:
            tongs = [m.get("tong") for m in g["gia_tri"]]
            cot += [TB.Cot(f"Tổng {s['cot']}"[:100], _kieu_so(tongs)),
                    TB.Cot(f"TB {s['cot']}"[:100], "thap_phan")]
        cot.append(TB.Cot("Biểu đồ", "chu"))
        dong = []
        for m in g["gia_tri"]:
            r = [m["gia_tri"], m["so"], m["ty_le"]]
            if s:
                t, o = m.get("tong"), m.get("so_o_so") or 0
                r += [_so_ra(t) if t is not None and o else None,
                      round(float(t / o), 2) if t is not None and o else None]
            r.append(TB.thanh_chu(m["so"], lon))
            dong.append(r)
        tong_r = [f"Dòng có giá trị ({g['trong']} dòng trống)", g["so_tra_loi"],
                  g["so_tra_loi"] / kq["n"] if kq["n"] else None]
        if s:
            tong_r += [None, None]
        ra.append(TB.Bang(f"Theo {_ten_ngan(g['cot'])}", cot, dong, dong_tong=[tong_r],
                          mo_ta=(f"Đếm theo {g['cot']}: {g['so_tra_loi']}/{kq['n']} dòng có "
                                 "giá trị; % trên số dòng có giá trị"
                                 + ("; ô nhiều lựa chọn nên tổng % có thể >100%"
                                    if g["nhieu"] else "")),
                          gap_duoc=False))
    for c in kq["cheo"]:
        dau = [TB.Cot(c["hang"][:100] or "Nhóm")]
        ten_cot = list(c["gia_tri_cot"]) + (["Khác"] if c["co_khac"] else [])
        so_cot = [TB.Cot(str(x)[:100], "so_nguyen") for x in ten_cot]
        dong_so, dong_pt = [], []
        for h in c["dong"]:
            o = list(h["o"]) + ([h["khac"]] if c["co_khac"] else [])
            dong_so.append([h["nhom"], *o, h["so_tra_loi"], h["n"]])
            dong_pt.append([h["nhom"], *[(x / h["so_tra_loi"]) if h["so_tra_loi"] else None
                                         for x in o], h["so_tra_loi"]])
        tong_cot = [sum(r[1 + i] for r in dong_so) for i in range(len(ten_cot))]
        ten_tab = f"{_ten_ngan(c['hang'], 10)} × {_ten_ngan(c['cot'], 10)}"
        ra.append(TB.Bang(
            ten_tab, dau + so_cot + [TB.Cot(f"Có {c['cot']}"[:100], "so_nguyen"),
                                    TB.Cot("Số dòng nhóm", "so_nguyen")],
            dong_so, dong_tong=[["Tổng", *tong_cot, None, None]],
            mo_ta=f"Số dòng theo {c['hang']} (dòng) × {c['cot']} (cột)", gap_duoc=False))
        ra.append(TB.Bang(
            f"{ten_tab} %", dau + [TB.Cot(str(x)[:100], "phan_tram") for x in ten_cot]
            + [TB.Cot(f"Có {c['cot']}"[:100], "so_nguyen")],
            dong_pt, mo_ta=(f"% theo dòng: mỗi nhóm {c['hang']} chia cho số dòng có "
                            f"{c['cot']}" + ("; ô nhiều lựa chọn nên tổng có thể >100%"
                                             if c["nhieu"] else "")),
            gap_duoc=False))
    return ra


def dung_tong_quan(kq: dict, tieu_de: str, nguon: str, ai_gan: bool, bi_cat: bool) -> TB.TongQuan:
    so_lieu = [TB.SoLieu("Số dòng dữ liệu (n)", kq["n"], "so_nguyen",
                         ghi_chu=("tiêu đề ở dòng " + str(kq["dong_tieu_de_da_dung"])
                                  if kq["dong_tieu_de_da_dung"] else "không có dòng tiêu đề"))]
    s = kq.get("so")
    if s and s["tong"] is not None and s["so_o_so"]:
        so_lieu += [
            TB.SoLieu(f"Tổng {s['cot']}", _so_ra(s["tong"]), _kieu_so([s["tong"]]),
                      ghi_chu=f"cộng {s['so_o_so']} ô có số"
                              + (f"; bỏ qua {s['so_o_bo_qua']} ô không phải số"
                                 if s["so_o_bo_qua"] else "")),
            TB.SoLieu(f"Trung bình {s['cot']}", round(float(s["tong"] / s["so_o_so"]), 2),
                      "thap_phan", ghi_chu="trên các ô có số")]
    nhom = [TB.Nhom(f"Theo {g['cot']}", [(m["gia_tri"], m["so"]) for m in g["gia_tri"]],
                    tong=g["so_tra_loi"], thanh=True,
                    nhan_so="Số lượt chọn" if g["nhieu"] else "Số dòng")
            for g in kq["nhom"]]
    top = None
    if kq["top"] and s:
        cot = ([TB.Cot("Dòng (nguồn)", "so_nguyen")]
               + [TB.Cot(g["cot"][:100]) for g in kq["nhom"]]
               + [TB.Cot(s["cot"][:100], _kieu_so([t["gia_tri"] for t in kq["top"]]))])
        top = TB.Bang(f"Top {len(kq['top'])} theo {s['cot']}", cot,
                      [[t["dong"], *t["nhom"], _so_ra(t["gia_tri"])] for t in kq["top"]])
    ghi = [GHI_CHU_AI if ai_gan else GHI_CHU_CODE,
           "Cột Biểu đồ là thanh chữ █ vẽ từ số (nhóm lớn nhất = 30 ký tự); Lark Sheets "
           "Open API chưa có API tạo biểu đồ gốc."]
    if kq.get("tieu_de_tu_nhan") and not ai_gan:
        ghi.append(f"Dòng tiêu đề tự nhận: dòng {kq['dong_tieu_de_da_dung']}"
                   + (" (không rõ — kiểm lại)" if kq.get("tieu_de_khong_ro") else "") + ".")
    if bi_cat:
        ghi.append("CHẠM TRẦN ĐỌC: nguồn dài hơn 2.000 dòng — số chỉ tính phần đã đọc.")
    ghi += [f"Bỏ qua {x}" for x in kq.get("cot_bo_qua") or []]
    ghi += [f"Lưu ý: {x}" for x in kq.get("canh_bao") or []]
    pham = "Nhóm theo: " + ", ".join(g["cot"] for g in kq["nhom"])
    if kq["cheo"]:
        pham += "; chéo: " + ", ".join(f"{c['hang']} × {c['cot']}" for c in kq["cheo"])
    if s:
        pham += f"; cột số: {s['cot']}"
    return TB.TongQuan(tieu_de, nguon=nguon, pham_vi=pham, so_lieu=so_lieu, nhom=nhom,
                       top=top, ghi_chu=ghi)


# ───────────────────────────── tool ─────────────────────────────
def _handle(args: dict, **_kw) -> str:
    a = args or {}
    nhom = _ds(a.get("nhom_theo"))[:MAX_NHOM_THEO + 1]
    if not nhom:
        return tool_error("Cần `nhom_theo`: ít nhất một cột để đếm theo nhóm (vd ['Sắc thái']).")
    if len(nhom) > MAX_NHOM_THEO:
        return tool_error(f"`nhom_theo` tối đa {MAX_NHOM_THEO} cột mỗi Sheet.")
    try:
        cheo = _cap_cheo(a.get("cheo"))
    except LoiNhap as e:
        return tool_error(f"{e}.")
    if len(cheo) > MAX_CHEO:
        return tool_error(f"`cheo` tối đa {MAX_CHEO} cặp mỗi Sheet.")
    cot_so = str(a.get("cot_so") or "").strip()
    try:
        top = int(a.get("top") or TOP_MAC_DINH)
        dong_td = int(a["dong_tieu_de"]) if a.get("dong_tieu_de") not in (None, "") else None
    except (TypeError, ValueError):
        return tool_error("`top` và `dong_tieu_de` phải là số.")
    tach = bool(a.get("tach_dau_phay"))
    nguon = str(a.get("nguon") or "").strip()
    du = a.get("du_lieu")
    goc_dong, goc_cot, bi_cat, ai_gan, loai_cot, khong_td = None, None, False, False, None, False
    if du:
        try:
            goc_cot, goc_dong, so_cat = doc_nhap(du)
        except LoiNhap as e:
            return tool_error(f"Không dùng được `du_lieu`: {e}.")
        luoi, dong_td, ai_gan = _luoi_tu_dong(goc_cot, goc_dong), 1, True
        ten_nguon = f"dữ liệu Mark đưa vào ({len(goc_dong)} dòng)"
        mo_ta_nguon = f"{len(goc_dong)} dòng Mark (AI) gán nhãn — tab Dữ liệu"
    elif nguon:
        try:
            loai, token, phu, ten_loai, vi_sao = BT.mo_nguon(nguon)
        except BT.TuChoi as e:
            return tool_error(str(e))
        tab = str(a.get("tab") or "").strip()
        if phu and tab and tab != phu:
            return tool_error("Nguồn đã chỉ đúng một bảng/tab; không được đổi sang bảng/tab khác.")
        try:
            tho = B.doc_tho(loai, token, tab or phu, strict_scope=bool(phu))
        except Exception as e:  # noqa: BLE001
            return tool_error(BT.loi_doc(ten_loai, e))
        if len(tho["bang"]) != 1:
            if not tho["bang"] and token in BT.base_noi_bo():
                return tool_error(f"Không thấy bảng '{tab or phu}' trong {ten_loai} này.")
            return tool_error(
                (f"Không thấy tab/bảng '{tab or phu}'" if not tho["bang"] else
                 f"{ten_loai} có {len(tho['bang'])} tab/bảng — chọn MỘT bằng `tab`")
                + f". Các tab: {', '.join(map(str, tho['tat_ca'])) or '(không có)'}.")
        b = tho["bang"][0]
        luoi, bi_cat, loai_cot = b["luoi"], bool(b.get("bi_cat")), b.get("loai_cot")
        if not luoi:
            return tool_error(f"Tab '{b['ten']}' trống — không có gì để thống kê.")
        ten_nguon = f"Tab \"{DB._gon(b['ten'])}\" của {ten_loai} \"{DB._gon(tho['ten'])}\""
        mo_ta_nguon = f"{ten_nguon} — {nguon}"
    else:
        return tool_error("Cần `nguon` (link Sheet/Base người hỏi xem được) hoặc `du_lieu` "
                          "(các dòng Mark đã gán nhãn).")

    kq = thong_ke(luoi, nhom, cheo, cot_so, top, dong_tieu_de=dong_td, khong_tieu_de=khong_td,
                  loai_cot=loai_cot, tach_dau_phay=tach)
    if kq.get("loi"):
        return tool_error(f"Không thống kê được: {kq['loi']}.")
    if not kq["nhom"] and not kq["cheo"]:
        return tool_error("Không lập được nhóm nào: " + "; ".join(
            kq["canh_bao"] + kq["cot_bo_qua"]) + ". Kiểm tên cột (chữ cái, mã câu hoặc tên).")
    cau = cau_so(kq, ten_nguon)

    luc = datetime.datetime.now(TB.VN)
    tieu_de = (str(a.get("tieu_de") or "").strip()[:80]
               or f"Thống kê {', '.join(g['cot'] for g in kq['nhom'])[:50]} · {luc:%d-%m-%Y %H:%M}")
    bang = dung_bang(kq)
    if goc_dong is not None:
        dai = {j for j in range(len(goc_cot))
               if any(isinstance(r[j], str) and len(r[j]) > 60 for r in goc_dong)}
        bang.append(TB.Bang("Dữ liệu", [TB.Cot(c, "chu_dai" if j in dai else "chu")
                                        for j, c in enumerate(goc_cot)],
                            goc_dong, ten_tab=TB.TAB_DU_LIEU, gap_duoc=False,
                            mo_ta="Các dòng Mark đưa vào; nhãn do Mark (AI) gán"))
    if len(bang) == 1:
        # Một bảng duy nhất thì lớp trình bày đặt tên tab "Dữ liệu" — ở đây sai nghĩa.
        bang[0].ten_tab = bang[0].ten
    tq = dung_tong_quan(kq, tieu_de, mo_ta_nguon, ai_gan, bi_cat)
    if goc_dong is not None and so_cat:
        tq.ghi_chu.append(f"{so_cat} ô dài hơn {MAX_KY_TU_O} ký tự đã cắt bớt ở tab Dữ liệu "
                          "(nhãn và số không đổi).")
    cap = {"granted": False}

    def _cap_quyen(tok: str) -> None:
        # Như mọi tool xuất Sheet: người hỏi được quyền SỬA file bot vừa tạo.
        sender = memory_store.get_current_sender()
        TB.gop_quyen(cap, A._grant(tok, sender) if sender else False)

    try:
        ket = TB.xuat(tieu_de, bang, tq, cap_quyen=_cap_quyen, luc=luc)
    except Exception as e:  # noqa: BLE001
        url = getattr(e, "trinh_bay_url", "")
        return tool_error("Tạo Sheet thống kê hỏng: " + A._che_token(f"{type(e).__name__}: {e}")[:250]
                          + (f". Bảng tính đã tạo nhưng CHƯA ghi đủ: {url}" if url else "")
                          + ". Số (do code đếm, chưa có Sheet):\n" + cau)
    return tool_result(
        success=ket.day_du is not False, sheet_url=ket.url, granted=cap["granted"],
        nguon=ten_nguon, nhan_do_ai_gan=ai_gan, n=kq["n"], cau_so=cau,
        nhom=[{"cot": g["cot"], "so_tra_loi": g["so_tra_loi"],
               "gia_tri": [{"gia_tri": m["gia_tri"], "so": m["so"], "ty_le": m["ty_le_chu"]}
                           for m in g["gia_tri"][:20]]} for g in kq["nhom"]],
        canh_bao=kq["canh_bao"] or None, bi_cat=bi_cat or None,
        huong_dan=("Gửi link Sheet, chép NGUYÊN `cau_so` và `kiem_ghi`. "
                   + ("Nói rõ nhãn do Mark (AI) gán, số do code đếm. " if ai_gan else "")
                   + ("`granted`=false: người hỏi chưa được cấp quyền mở — nói rõ. "
                      if not cap["granted"] else "")),
        **ket.cho_tool(),
    )


def register() -> None:
    try:
        registry.register(
            name="tao_sheet_thong_ke", toolset="lark_api", schema=SCHEMA, handler=_handle,
            check_fn=lambda: True, requires_env=[], is_async=False,
            description="Tạo Lark Sheet thống kê/dashboard — số do code đếm",
            emoji="\U0001f4c8", override=True,
        )
    except Exception as e:
        print(f"[thong_ke_tool] register warning: {e}")


register()
