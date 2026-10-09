"""`tao_sheet_thong_ke` — Sheet thống kê / dashboard MỚI, mọi số do CODE đếm.

Canh (01/10 và 07/10/2026: Mark nói không tạo được Sheet, nhờ tạo Sheet trống, dán số thô):
  • Nguồn Sheet/Base chỉ mở qua `bang_tool.mo_nguon` (cùng quyền doc_bang/dem_bang).
  • Đếm, %, bảng chéo, tổng/TB theo nhóm đi qua `dem_bang_tool.dem` — một luật đếm.
  • Dòng Mark đưa vào: có trần, không nhận dòng tổng, ghi nguyên vào tab Dữ liệu, ô chữ qua
    đường chặn chèn công thức; Tổng quan nói rõ nhãn do AI gán, số do code đếm.
  • Ghi xong đọc lại kiểm (`day_du`/`kiem_ghi`).
Lark giả (tests/sheet_gia.py) — không gọi mạng.
"""
from __future__ import annotations

import json

import pytest

import apify_tool as A
import bang_tool as BT
import dem_bang_tool as DB
import lark_client
import lsr_policy
import memory_store
import thong_ke_tool as T
import trinh_bay_sheet as TB
from sheet_gia import LarkGia

SRC = "shtSrc1"
NGAN = "ou_ngan"
LINK = f"https://x.larksuite.com/sheets/{SRC}"

DONG_NGUON = [
    ["STT", "Bình luận", "Nền tảng", "Sắc thái", "Lượt thích"],
    ["1", "Đẹp quá", "TikTok", "Tích cực", "120"],
    ["2", "Giá chát", "TikTok", "Tiêu cực", "40"],
    ["3", "Mua ở đâu", "Facebook", "Trung lập", "5"],
    ["4", "Xinh", "Facebook", "Tích cực", "60"],
    ["5", "Ship chậm", "TikTok", "Tiêu cực", "8"],
    ["6", "Ổn", "Threads", "Tích cực", "1.500"],
    ["7", "Chưa rõ", "Threads", "", "3"],
    ["8", "Tuyệt", "TikTok", "tích cực", "0"],
]


class Hop:
    """Nguồn Sheet (đọc) + Lark Sheets giả (tạo/ghi Sheet mới) + API quyền drive."""

    def __init__(self, gia: LarkGia, dong=DONG_NGUON, thanh_vien=(NGAN,)):
        self.gia, self.dong, self.thanh_vien = gia, dong, thanh_vien
        self.goi_nguon: list[str] = []

    def __call__(self, method, path, query=None, body=None, **_):
        if SRC in path:
            self.goi_nguon.append(path)
            if path == f"/open-apis/sheets/v3/spreadsheets/{SRC}":
                return {"data": {"spreadsheet": {"title": "Bình luận BST"}}}
            if path.endswith("/sheets/query"):
                return {"data": {"sheets": [{"sheet_id": "s1", "title": "Bình luận",
                                             "grid_properties": {
                                                 "row_count": len(self.dong),
                                                 "column_count": len(self.dong[0])}}]}}
            if "/values/" in path:
                return {"data": {"valueRange": {"values": self.dong}}}
            if path.endswith("/public"):
                return {"data": {"permission_public": {"link_share_entity": "closed"}}}
            if path.endswith("/members"):
                return {"data": {"items": [{"member_type": "openid", "member_id": x}
                                           for x in self.thanh_vien]}}
            raise RuntimeError(f"Lark {method} {path} failed: HTTP 404")
        if "/drive/v1/permissions/" in path and method == "POST":
            self.gia.goi.append((method, path, query, body))
            return {"data": {}}
        return self.gia.call(method, path, query, body)


@pytest.fixture(autouse=True)
def _moi_truong(monkeypatch):
    monkeypatch.delenv("AGENT_BOSS_OPEN_ID", raising=False)
    monkeypatch.delenv("STEVEN_BOSS_OPEN_ID", raising=False)
    monkeypatch.setattr(BT, "_nguoi_hoi", lambda: NGAN)
    monkeypatch.setattr(BT, "base_noi_bo", lambda: set())
    monkeypatch.setattr(BT, "_trong_cay_wiki", lambda *a: False)
    monkeypatch.setattr(memory_store, "get_current_sender", lambda: NGAN)


def _lap(monkeypatch, **kw) -> tuple[LarkGia, Hop]:
    gia = LarkGia(**{k: v for k, v in kw.items() if k in ("doc_lai",)})
    hop = Hop(gia, **{k: v for k, v in kw.items() if k in ("dong", "thanh_vien")})
    monkeypatch.setattr(lark_client, "call", hop)
    return gia, hop


def _goi(**a) -> dict:
    return json.loads(T._handle(a))


# ───────────────────────────── (a) từ Sheet nguồn ─────────────────────────────
def test_dem_va_ty_le_tu_sheet_nguon(monkeypatch):
    gia, _ = _lap(monkeypatch)
    r = _goi(nguon=LINK, nhom_theo=["Sắc thái"], cot_so="Lượt thích")
    assert "error" not in r, r
    assert r["sheet_url"].endswith("/sht1") and r["granted"] is True
    assert r["n"] == 8
    # 7 dòng có Sắc thái; "tích cực" gộp với "Tích cực" (luật gộp cách viết của dem_bang).
    assert "Theo Sắc thái (7/8 dòng có giá trị): Tích cực 4 (57,1%); Tiêu cực 2 (28,6%); " \
           "Trung lập 1 (14,3%)." in r["cau_so"]
    # Lượt thích "1.500" là một nghìn năm trăm (luật số VN của dem_bang): 1736 trên 8 ô.
    assert "Tổng Lượt thích: 1.736 trên 8 ô có số" in r["cau_so"]
    tab = gia.du_lieu("Theo Sắc thái")
    assert tab[0] == ["Sắc thái", "Số dòng", "Tỉ lệ", "Tổng Lượt thích", "TB Lượt thích",
                      "Biểu đồ"]
    assert tab[1][:5] == ["Tích cực", 4, 4 / 7, 1680, 420.0]
    assert tab[1][5] == "█" * 30 and tab[2][5] == "█" * 15
    o = gia.o("Theo Sắc thái")
    assert o[-1][:3] == ["Dòng có giá trị (1 dòng trống)", 7, 7 / 8]
    # Cấp quyền SỬA cho người hỏi trên Sheet mới.
    cap = [b for m, p, q, b in gia.goi if m == "POST" and "/drive/v1/permissions/sht1" in p]
    assert cap and cap[0]["member_id"] == NGAN and cap[0]["perm"] == "edit"


def test_tong_quan_co_khoi_nhom_kem_thanh_bieu_do_va_top(monkeypatch):
    gia, _ = _lap(monkeypatch)
    _goi(nguon=LINK, nhom_theo=["Sắc thái"], cot_so="Lượt thích", top=2)
    tq = gia.o("Tổng quan")
    i = next(k for k, r in enumerate(tq) if r[:4] == ["Nhóm", "Số dòng", "Tỉ lệ", "Biểu đồ"])
    assert tq[i + 1][:2] == ["Tích cực", 4] and tq[i + 1][3] == "█" * 30
    j = next(k for k, r in enumerate(tq) if r and r[0] == "TOP 2 THEO LƯỢT THÍCH")
    assert tq[j + 2][:3] == [7, "Tích cực", 1500], "dòng 7 trên Sheet nguồn, giá trị 1.500"
    ghi = " ".join(str(r[0]) for r in tq if r)
    assert "do CODE tính trên mọi dòng của nguồn" in ghi
    assert "chưa có API tạo biểu đồ gốc" in ghi


def test_bang_cheo(monkeypatch):
    gia, _ = _lap(monkeypatch)
    r = _goi(nguon=LINK, nhom_theo=["Nền tảng"], cheo=[["Nền tảng", "Sắc thái"]])
    assert "error" not in r, r
    ten = gia.tab_ten()
    assert "2. Nền tảng × Sắc thái" in ten and "3. Nền tảng × Sắc thái %" in ten
    so = gia.du_lieu("2. Nền tảng × Sắc thái")
    assert so[0] == ["Nền tảng", "Tích cực", "Tiêu cực", "Trung lập", "Có Sắc thái",
                     "Số dòng nhóm"]
    dong = {r[0]: r[1:] for r in so[1:]}
    assert dong["TikTok"] == [2, 2, 0, 4, 4]
    assert dong["Facebook"] == [1, 0, 1, 2, 2]
    assert dong["Threads"] == [1, 0, 0, 1, 2], "Threads có 1 dòng trống Sắc thái"
    tong = gia.o("2. Nền tảng × Sắc thái")[-1]
    assert tong[:4] == ["Tổng", 4, 2, 1]
    pt = {r[0]: r[1:] for r in gia.du_lieu("3. Nền tảng × Sắc thái %")[1:]}
    assert pt["TikTok"][:2] == [0.5, 0.5] and pt["Threads"][0] == 1.0


def test_nguoi_hoi_khong_co_quyen_nguon_thi_khong_tao_sheet(monkeypatch):
    gia, hop = _lap(monkeypatch, thanh_vien=("ou_khac",))
    r = _goi(nguon=LINK, nhom_theo=["Sắc thái"])
    assert "chưa thấy bạn trong danh sách người có quyền" in r["error"]
    assert not gia.bt, "không tạo Sheet khi người hỏi chưa được xem nguồn"
    assert not any("/values/" in p for p in hop.goi_nguon), "không đọc dữ liệu nguồn"


def test_dung_chung_cua_mo_nguon(monkeypatch):
    goi = []

    def gia_mo(nguon, **kw):
        goi.append(nguon)
        raise BT.TuChoi("từ chối giả của mo_nguon")
    monkeypatch.setattr(BT, "mo_nguon", gia_mo)
    _lap(monkeypatch)
    r = _goi(nguon=LINK, nhom_theo=["Sắc thái"])
    assert goi == [LINK] and r["error"] == "từ chối giả của mo_nguon"


def test_cot_khong_co_thi_bao_khong_tao_sheet(monkeypatch):
    gia, _ = _lap(monkeypatch)
    r = _goi(nguon=LINK, nhom_theo=["Không có cột này"])
    assert "Không lập được nhóm nào" in r["error"] and not gia.bt


# ───────────────────────────── (b) dòng Mark đưa vào ─────────────────────────────
COT = ["Nội dung", "Nhãn", "Chủ đề"]
DONG = [["Đẹp lắm", "Tích cực", "Sản phẩm"], ["Đắt", "Tiêu cực", "Giá"],
        ["Bao giờ có màu đen", "Trung lập", "Sản phẩm"], ["Mê", "Tích cực", ""]]


def test_che_do_dong_ghi_du_lieu_va_ghi_chu_ai(monkeypatch):
    gia, _ = _lap(monkeypatch)
    r = _goi(du_lieu={"cot": COT, "dong": DONG}, nhom_theo=["Nhãn", "Chủ đề"])
    assert "error" not in r, r
    assert r["nhan_do_ai_gan"] is True
    assert gia.tab_ten() == ["Tổng quan", "1. Theo Nhãn", "2. Theo Chủ đề", "Dữ liệu"]
    assert gia.du_lieu("Dữ liệu") == [COT] + DONG
    assert "Theo Nhãn (4/4 dòng có giá trị): Tích cực 2 (50,0%)" in r["cau_so"]
    assert "Theo Chủ đề (3/4 dòng có giá trị): Sản phẩm 2 (66,7%); Giá 1 (33,3%)" in r["cau_so"]
    tq = " ".join(str(c) for row in gia.o("Tổng quan") for c in row)
    assert "do Mark (AI) gán" in tq and "do CODE tính" in tq
    assert "Nói rõ nhãn do Mark (AI) gán" in r["huong_dan"]


def test_tran_so_dong(monkeypatch):
    gia, _ = _lap(monkeypatch)
    r = _goi(du_lieu={"cot": COT, "dong": [["x", "Tích cực", "Giá"]] * (T.MAX_DONG_NHAP + 1)},
             nhom_theo=["Nhãn"])
    assert "trần 2000 dòng" in r["error"] and "nguon" in r["error"]
    assert not gia.bt


def test_o_qua_dai_bi_cat_va_bao(monkeypatch):
    gia, _ = _lap(monkeypatch)
    dai = "a" * (T.MAX_KY_TU_O + 50)
    r = _goi(du_lieu={"cot": COT, "dong": [[dai, "Tích cực", "Giá"]]}, nhom_theo=["Nhãn"])
    assert "error" not in r, r
    o = gia.du_lieu("Dữ liệu")[1][0]
    assert len(o) == T.MAX_KY_TU_O and o.endswith("…")
    tq = " ".join(str(c) for row in gia.o("Tổng quan") for c in row)
    assert "1 ô dài hơn 1000 ký tự đã cắt bớt" in tq


def test_khong_nhan_dong_tong_mark_tu_tinh(monkeypatch):
    gia, _ = _lap(monkeypatch)
    r = _goi(du_lieu={"cot": ["Nhãn", "Số"], "dong": [["Tích cực", 3], ["Tổng", 3]]},
             nhom_theo=["Nhãn"])
    assert "dòng TỔNG" in r["error"] and not gia.bt


def test_chan_chen_cong_thuc_o_du_lieu_va_bang_nhom(monkeypatch):
    gia, _ = _lap(monkeypatch)
    dong = [['=HYPERLINK("http://x","bấm")', "@SUM(1)", "Giá"],
            ["+cmd|' /C calc'!A0", "Tích cực", "-2+3+cmd|x"]]
    r = _goi(du_lieu={"cot": COT, "dong": dong}, nhom_theo=["Nhãn", "Chủ đề"])
    assert "error" not in r, r
    du = gia.du_lieu("Dữ liệu")
    assert du[1][0].startswith("'=") and du[1][1] == "'@SUM(1)"
    assert du[2][0].startswith("'+") and du[2][2].startswith("'-")
    nhan = [r[0] for r in gia.du_lieu("1. Theo Nhãn")[1:]]
    assert "'@SUM(1)" in nhan, "giá trị nhóm do người lạ viết cũng không thành công thức"
    tq = [c for row in gia.o("Tổng quan") for c in row if isinstance(c, str)]
    assert not any(c.startswith(("=", "@", "+")) for c in tq)


def test_doc_lai_kiem_day_du(monkeypatch):
    _lap(monkeypatch)
    r = _goi(du_lieu={"cot": COT, "dong": DONG}, nhom_theo=["Nhãn"])
    assert r["day_du"] is True and r["kiem_ghi"].startswith("Đã ghi đủ")


def test_khong_doc_lai_duoc_thi_khong_tu_nhan_du(monkeypatch):
    _lap(monkeypatch, doc_lai=False)
    r = _goi(du_lieu={"cot": COT, "dong": DONG}, nhom_theo=["Nhãn"])
    assert r["day_du"] is None and "chưa đọc lại" in r["kiem_ghi"]


def test_thieu_nguon_va_du_lieu():
    assert "Cần `nguon`" in _goi(nhom_theo=["Nhãn"])["error"]
    assert "Cần `nhom_theo`" in _goi(du_lieu={"cot": COT, "dong": DONG})["error"]


# ───────────────────────────── hàm thuần ─────────────────────────────
def test_thong_ke_o_nhieu_lua_chon_va_cot_ca_nhan():
    luoi = T._luoi_tu_dong(["Tên khách", "Kênh biết"],
                           [["An", "TikTok\nFacebook"], ["Bình", "TikTok"]])
    kq = T.thong_ke(luoi, ["Kênh biết", "Tên khách"], dong_tieu_de=1)
    g = kq["nhom"][0]
    assert g["nhieu"] is True and [(m["gia_tri"], m["so"]) for m in g["gia_tri"]] == [
        ("TikTok", 2), ("Facebook", 1)]
    assert len(kq["nhom"]) == 1 and any("thông tin cá nhân" in x for x in kq["canh_bao"])
    assert "tổng % có thể >100%" in T.cau_so(kq, "x")


def test_dem_dung_chung_dem_bang(monkeypatch):
    """Không có bộ đếm thứ hai: mọi số đi qua `dem_bang_tool.dem`."""
    goi = []
    goc = DB.dem

    def soi(*a, **kw):
        goi.append(kw.get("cot"))
        return goc(*a, **kw)
    monkeypatch.setattr(DB, "dem", soi)
    T.thong_ke(T._luoi_tu_dong(COT, DONG), ["Nhãn"], dong_tieu_de=1)
    assert len(goi) >= 2


def test_thanh_chu():
    assert TB.thanh_chu(10, 10) == "█" * 30
    assert TB.thanh_chu(1, 100) == "█"
    assert TB.thanh_chu(0, 10) == "" and TB.thanh_chu(5, 0) == ""


# ───────────────────────────── đăng ký + policy ─────────────────────────────
def test_policy_la_tool_ghi_sheet_theo_cong_tac_doc_bang():
    assert lsr_policy._MUTATING_EXACT["tao_sheet_thong_ke"] == "write_data"
    assert "tao_sheet_thong_ke" not in lsr_policy._SAFE_EXACT
    assert lsr_policy._CONG_TAC_LUI["tao_sheet_thong_ke"] == "doc_bang"
    import importlib.util
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[1] / "evals" / "sow" / "kiem.py"
    spec = importlib.util.spec_from_file_location("kiem_tk", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert "tao_sheet_thong_ke" in m.TOOL_GHI


def test_dang_ky_trong_brain_va_loi_dan():
    import brain
    assert "tao_sheet_thong_ke" in brain._TOOL_CAN_XET
    s = (__import__("pathlib").Path(brain.__file__)).read_text(encoding="utf-8")
    assert "import thong_ke_tool" in s and "không nhờ" in s
    p = (__import__("pathlib").Path(brain.__file__).with_name("persona.md")
         .read_text(encoding="utf-8"))
    assert "`tao_sheet_thong_ke`" in p and "không tạo được Sheet" in p
    assert A is not None
