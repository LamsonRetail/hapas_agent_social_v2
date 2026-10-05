"""Sheet kết quả gọn (E2E 04-05/10/2026): tab chính không còn tên "Sheet1", và không còn
cột trống thừa bên phải (lưới mặc định 20 cột của Lark: sheet 16 cột thừa 4–5 cột trống).

Bỏ cột thừa chỉ là tiện xem: hỏng thì không bao giờ làm hỏng lần ghi. Ghi lớn của việc nền
(`sheet_lon`) ghi đủ bảng rồi mới bỏ cột thừa; bảng sau rộng hơn thì nới lưới lại trước khi
ghi. Không gọi Lark thật.
"""
from __future__ import annotations

import json

import pytest

import apify_tool as A
import deep_dive_tool as D
import sheet_lon
from test_binh_luan_phan_tich import TT, _bl, moi_truong  # noqa: F401
from test_phan_xu_ai import quet  # noqa: F401
from test_viec_nen import _VGia


class LuoiGia:
    """lark.call giả có lưới cột: tab mới 20 cột; DELETE/POST dimension_range đổi số cột."""

    def __init__(self, cot: int = 20):
        self.goi: list = []
        self.cot = {"s0": cot}
        self.mac_dinh = cot

    def call(self, method, path, query=None, body=None):
        self.goi.append((method, path, body))
        if path == "/open-apis/sheets/v3/spreadsheets":
            return {"data": {"spreadsheet": {"spreadsheet_token": "shtA", "url": "u"}}}
        if path.endswith("/sheets/query"):
            return {"data": {"sheets": [
                {"sheet_id": s, "grid_properties": {"row_count": 200, "column_count": c}}
                for s, c in self.cot.items()]}}
        if path.endswith("/sheets_batch_update"):
            req = (body or {}).get("requests", [{}])[0]
            if "addSheet" in req:
                sid = f"tab{len(self.cot)}"
                self.cot[sid] = self.mac_dinh
                return {"data": {"replies": [{"addSheet": {"properties": {"sheetId": sid}}}]}}
        if path.endswith("/dimension_range") and body["dimension"]["majorDimension"] == "COLUMNS":
            d = body["dimension"]
            if method == "DELETE":
                self.cot[d["sheetId"]] -= d["endIndex"] - d["startIndex"] + 1
            else:
                self.cot[d["sheetId"]] += d["length"]
        return {"data": {}}

    def xoa_cot(self):
        return [b["dimension"] for m, p, b in self.goi
                if m == "DELETE" and p.endswith("/dimension_range")]

    def them_cot(self):
        return [b["dimension"] for m, p, b in self.goi if m == "POST"
                and p.endswith("/dimension_range")
                and b["dimension"]["majorDimension"] == "COLUMNS"]


@pytest.fixture
def luoi(monkeypatch):
    lk = LuoiGia()
    monkeypatch.setattr(A.lark, "call", lk.call)
    return lk


# ───────────────────────── trợ thủ chung ─────────────────────────
def test_bo_cot_thua_ben_phai_khong_dung_cot_du_lieu(luoi):
    assert A._vua_cot("shtA", "s0", 16) == 16
    assert luoi.xoa_cot() == [{"sheetId": "s0", "majorDimension": "COLUMNS",
                               "startIndex": 17, "endIndex": 20}], "từ 1, gồm hai đầu"
    assert luoi.cot["s0"] == 16
    assert A._vua_cot("shtA", "s0", 16) == 16 and len(luoi.xoa_cot()) == 1, "đủ rồi thì thôi"
    assert A._vua_cot("shtA", "s0", 25) == 16 and len(luoi.xoa_cot()) == 1


def test_bo_cot_hong_khong_bao_gio_nem(monkeypatch):
    def hong(*a, **k):
        raise RuntimeError("Lark lỗi")
    monkeypatch.setattr(A.lark, "call", hong)
    assert A._vua_cot("t", "s", 5) is None
    assert A._doi_ten_tab("t", "s", "Bài đăng") is False
    A._sua_tab_chinh("t", "s", "Bài đăng", 16)          # không ném


def test_sua_tab_chinh_dat_ten_va_bo_cot(luoi):
    A._sua_tab_chinh("shtA", "s0", A.TAB_BAI_DANG, 16)
    doi = [b["requests"][0]["updateSheet"]["properties"] for m, p, b in luoi.goi
           if p.endswith("/sheets_batch_update")]
    assert doi == [{"sheetId": "s0", "title": "Bài đăng"}]
    assert luoi.cot["s0"] == 16


def test_tab_phu_moi_cung_bo_cot_thua(luoi):
    noi, _ = A._ghi_tab_phu("shtA", "s0", 3, [["a"] * 5, ["b"] * 5], "Thống kê", "TK", "x")
    assert noi == "tab 'Thống kê'" and luoi.cot["tab1"] == 5


# ───────────────────────── từng tool ─────────────────────────
def test_social_listen_tab_chinh_ten_bai_dang_vua_tieu_de(quet, monkeypatch):  # noqa: F811
    chay, ghi, _, _ = quet
    sua = []
    monkeypatch.setattr(A, "_sua_tab_chinh", lambda *a: sua.append(a))
    chay()
    assert sua == [("tok", "s1", "Bài đăng", len(ghi[0][1][0]))]
    assert len(ghi[0][1][0]) == len(A._HEADER) + len(A._COT_THEM_BAI) + 1  # + Loại video TikTok


def test_deep_dive_tab_chinh_ten_binh_luan_vua_tieu_de(moi_truong, monkeypatch):  # noqa: F811
    ap = moi_truong[0]
    ap.tra = lambda payload, limit: [_bl(TT.format(7000001), "đẹp")]
    sua, vua = [], []
    monkeypatch.setattr(A, "_sua_tab_chinh", lambda *a: sua.append(a))
    monkeypatch.setattr(A, "_vua_cot", lambda *a: vua.append(a))
    kq = json.loads(D._handle({"post_urls": [TT.format(7000001)]}))
    assert kq["success"] is True
    assert sua == [("tok", "s1", "Bình luận", len(D._HEADER))]
    assert vua == [("tok", "s2", 5)], "tab Thống kê 5 cột"


# ───────────────────────── sheet_lon (việc nền) ─────────────────────────
def test_sheet_lon_ghi_du_roi_moi_bo_cot_va_noi_lai_khi_rong_hon(luoi, monkeypatch):
    monkeypatch.setattr(sheet_lon, "_ngu", lambda s: None)
    monkeypatch.setattr(A, "_grant", lambda *a: True)
    s = sheet_lon.SoSheet(_VGia())
    s.dam_bao("T", "Tổng hợp", "")
    bang = [[f"c{j}" for j in range(16)]] + [[i] * 16 for i in range(2500)]
    s.ghi_tab("TikTok", bang)
    sid = s.s["tabs"]["TikTok"]["sheet_id"]
    viet = [i for i, (m, p, b) in enumerate(luoi.goi) if p.endswith("values_batch_update")]
    xoa = [i for i, (m, p, b) in enumerate(luoi.goi)
           if m == "DELETE" and p.endswith("/dimension_range")]
    assert len(viet) == 3 and xoa and xoa[0] > viet[-1], "ghi ĐỦ bảng rồi mới bỏ cột"
    assert luoi.cot[sid] == 16 and s.s["tabs"]["TikTok"]["cot"] == 16
    n = len(luoi.goi)
    s.ghi_tab("TikTok", bang)                     # cùng bảng: không hỏi/xoá lại
    assert not [g for g in luoi.goi[n:] if g[1].endswith(("/sheets/query", "/dimension_range"))]
    rong = [[f"c{j}" for j in range(18)]] + [[i] * 18 for i in range(10)]
    s.ghi_tab("TikTok", rong)
    assert luoi.them_cot() == [{"sheetId": sid, "majorDimension": "COLUMNS", "length": 2}]
    them = next(i for i, (m, p, b) in enumerate(luoi.goi) if m == "POST"
                and p.endswith("/dimension_range") and b["dimension"].get("length") == 2)
    sau = next(i for i, (m, p, b) in enumerate(luoi.goi)
               if i > n and p.endswith("values_batch_update"))
    assert them < sau, "nới lưới TRƯỚC khi ghi bảng rộng hơn"
    assert luoi.cot[sid] == 18
