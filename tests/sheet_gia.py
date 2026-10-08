"""Lark Sheets GIẢ cho bộ thử (không chạm mạng): giữ bảng tính, tab (thứ tự, tên, lưới),
ô đã ghi, và GHI LẠI mọi request — để bài thử soi bố cục do `trinh_bay_sheet` dựng.

Dùng:
    gia = LarkGia(); monkeypatch.setattr(A.lark, "call", gia.call)
    gia.hong = {"styles_batch_update"}     # mọi request có đoạn này trong path → lỗi
    gia.tab_ten()  -> tên tab theo thứ tự hiển thị
    gia.o("Dữ liệu") -> lưới ô của tab (list dòng)
"""
from __future__ import annotations

import re


def meta(tq: list) -> str:
    """Khối siêu dữ liệu của tab Tổng quan (dòng 2.. "Nhãn | Giá trị") → "Nhãn: giá trị · …"."""
    ra = []
    for r in tq[1:]:
        if len(r) < 2 or not r[0] or r[0] not in ("Nguồn", "Thời gian", "Phạm vi",
                                                   "Người yêu cầu", "Tạo lúc"):
            break
        ra.append(f"{r[0]}: {r[1]}")
    return " · ".join(ra)


def _so_cot(chu: str) -> int:
    n = 0
    for ch in chu:
        n = n * 26 + ord(ch) - 64
    return n


def _vung(rg: str):
    sid, _, ab = rg.partition("!")
    m = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", ab)
    if not m:
        return sid, None
    c1, r1, c2, r2 = m.group(1), int(m.group(2)), m.group(3) or m.group(1), \
        int(m.group(4) or m.group(2))
    return sid, (_so_cot(c1), r1, _so_cot(c2), r2)


class BangTinhGia:
    def __init__(self, tok: str, title: str):
        self.tok, self.title = tok, title
        self.tabs: list[dict] = [{"sheet_id": f"{tok}_s0", "title": "Sheet1", "rows": 200,
                                  "cols": 20, "cells": {}, "frozen": 0}]

    def tab(self, sid):
        return next(t for t in self.tabs if t["sheet_id"] == sid)


class LarkGia:
    """`chat_luoi`=True (mặc định): ghi vượt lưới tab (chưa nới bằng dimension_range) bị TỪ
    CHỐI như lỗi Lark — để bài thử thật sự canh việc nới lưới trước khi ghi."""

    def __init__(self, hong=(), doc_lai: bool = True, url: str | None = None,
                 chat_luoi: bool = True):
        self.goi: list = []
        self.bt: dict[str, BangTinhGia] = {}
        self.hong = set(hong)
        self.doc_lai = doc_lai
        self.url = url                 # url cố định mọi bảng tính (bài cũ so "https://sheet")
        self.chat_luoi = chat_luoi
        self.dem = 0

    # ── tra cứu ──
    @property
    def dau(self) -> BangTinhGia:
        return next(iter(self.bt.values()))

    def tab_ten(self, tok: str | None = None) -> list[str]:
        b = self.bt[tok] if tok else self.dau
        return [t["title"] for t in b.tabs]

    def tab(self, ten: str, tok: str | None = None) -> dict:
        b = self.bt[tok] if tok else self.dau
        return next(t for t in b.tabs if t["title"] == ten)

    def o(self, ten: str, tok: str | None = None) -> list[list]:
        t = self.tab(ten, tok)
        if not t["cells"]:
            return []
        r_max = max(r for r, _ in t["cells"])
        c_max = max(c for _, c in t["cells"])
        return [[t["cells"].get((r, c), "") for c in range(1, c_max + 1)]
                for r in range(1, r_max + 1)]

    def du_lieu(self, ten: str, tok: str | None = None) -> list[list]:
        """Bảng của tab dữ liệu (tiêu đề + dòng), bỏ dòng trống cuối và khối tổng dưới
        dòng trống."""
        rows = self.o(ten, tok)
        ra = []
        for r in rows:
            if not any(v not in ("", None) for v in r):
                break
            ra.append(r)
        return ra

    def ghi_cu(self, ban_do: dict, tok: str | None = None, ba: bool = False) -> "GhiCu":
        return GhiCu(self, ban_do, tok, ba)

    def kieu(self, tok: str | None = None) -> list[tuple[str, dict]]:
        """[(vùng, style)] của mọi styles_batch_update theo thứ tự."""
        ra = []
        for m, p, q, b in self.goi:
            if p.endswith("/styles_batch_update") and (tok is None or f"/{tok}/" in p):
                for d in b["data"]:
                    ra += [(r, d["style"]) for r in d["ranges"]]
        return ra

    def kieu_o(self, ten_tab: str, cot: int, dong: int, tok: str | None = None) -> list[dict]:
        """Các style đã đặt phủ ô (cot, dong) của tab."""
        sid = self.tab(ten_tab, tok)["sheet_id"]
        ra = []
        for rg, st in self.kieu(tok):
            s, v = _vung(rg)
            if s == sid and v and v[0] <= cot <= v[2] and v[1] <= dong <= v[3]:
                ra.append(st)
        return ra

    def loc(self) -> list[tuple[str, dict]]:
        return [(p, b) for m, p, q, b in self.goi if p.endswith("/filter")]

    def rong(self, ten_tab: str, tok: str | None = None) -> dict[int, int]:
        sid = self.tab(ten_tab, tok)["sheet_id"]
        ra = {}
        for m, p, q, b in self.goi:
            if m == "PUT" and p.endswith("/dimension_range") and \
                    b["dimension"]["sheetId"] == sid:
                d = b["dimension"]
                for c in range(d["startIndex"], d["endIndex"] + 1):
                    ra[c] = b["dimensionProperties"]["fixedSize"]
        return ra

    def thu_tu(self, *doan: str) -> list[int]:
        """Vị trí đầu tiên (trong self.goi) của request có path chứa từng đoạn."""
        return [next((i for i, g in enumerate(self.goi) if d in g[1]), -1) for d in doan]

    # ── API giả ──
    def call(self, method, path, query=None, body=None):
        self.goi.append((method, path, query, body))
        for h in self.hong:
            if h in path:
                raise RuntimeError(f"Lark {method} {path} failed: HTTP 400: giả hỏng")
        if path == "/open-apis/sheets/v3/spreadsheets":
            self.dem += 1
            tok = f"sht{self.dem}"
            self.bt[tok] = BangTinhGia(tok, body.get("title"))
            return {"data": {"spreadsheet": {
                "spreadsheet_token": tok,
                "url": self.url or f"https://x.larksuite.com/sheets/{tok}"}}}
        m = re.match(r"/open-apis/sheets/v[23]/spreadsheets/([^/]+)/(.*)", path)
        if not m:
            return {"data": {}}
        b = self.bt.get(m.group(1))
        rest = m.group(2)
        if b is None:
            return {"data": {}}
        if rest == "sheets/query":
            return {"data": {"sheets": [
                {"sheet_id": t["sheet_id"], "title": t["title"], "index": i,
                 "grid_properties": {"row_count": t["rows"], "column_count": t["cols"],
                                     "frozen_row_count": t["frozen"]}}
                for i, t in enumerate(b.tabs)]}}
        if rest == "sheets_batch_update":
            replies = []
            for rq in body["requests"]:
                if "addSheet" in rq:
                    p = rq["addSheet"]["properties"]
                    sid = f"{b.tok}_s{len(b.tabs)}"
                    t = {"sheet_id": sid, "title": p["title"], "rows": 200, "cols": 20,
                         "cells": {}, "frozen": 0}
                    b.tabs.insert(p.get("index", 0), t)
                    replies.append({"addSheet": {"properties": {"sheetId": sid,
                                                                "title": p["title"]}}})
                elif "updateSheet" in rq:
                    p = rq["updateSheet"]["properties"]
                    t = b.tab(p["sheetId"])
                    if "title" in p:
                        t["title"] = p["title"]
                    if "frozenRowCount" in p:
                        t["frozen"] = p["frozenRowCount"]
                    if "index" in p:
                        b.tabs.remove(t)
                        b.tabs.insert(p["index"], t)
                    replies.append({})
            return {"data": {"replies": replies}}
        if rest == "values_batch_update":
            for vr in body["valueRanges"]:
                sid, v = _vung(vr["range"])
                t = b.tab(sid)
                c1, r1, c2, r2 = v
                if self.chat_luoi and (r2 > t["rows"] or c2 > t["cols"]):
                    raise RuntimeError(
                        f"Lark POST {path} failed: HTTP 400: range {vr['range']} vượt lưới "
                        f"{t['rows']}x{t['cols']} (giả)")
                assert len(vr["values"]) == r2 - r1 + 1, "số dòng khớp vùng"
                assert len(vr["values"]) <= 5000 and c2 - c1 + 1 <= 100, "trần ghi"
                for i, row in enumerate(vr["values"]):
                    assert len(row) <= c2 - c1 + 1, "columns of value > range"
                    for j, val in enumerate(row):
                        t["cells"][(r1 + i, c1 + j)] = val
                t["rows"] = max(t["rows"], r2)
                t["cols"] = max(t["cols"], c2)
            return {"data": {}}
        if rest.startswith("values_batch_get"):
            if not self.doc_lai:
                return {"data": {}}
            ranges = (query or {}).get("ranges", "").split(",")
            out = []
            for rg in ranges:
                sid, v = _vung(rg)
                t = b.tab(sid)
                c1, r1, c2, r2 = v
                vals = [[t["cells"].get((r, c), None) for c in range(c1, c2 + 1)]
                        for r in range(r1, r2 + 1)]
                out.append({"range": rg, "values": vals})
            return {"data": {"valueRanges": out}}
        if rest == "dimension_range":
            d = body["dimension"]
            t = b.tab(d["sheetId"])
            if method == "POST":
                t["rows" if d["majorDimension"] == "ROWS" else "cols"] += d["length"]
            elif method == "DELETE" and d["majorDimension"] == "COLUMNS":
                t["cols"] -= d["endIndex"] - d["startIndex"] + 1
            elif method == "DELETE" and d["majorDimension"] == "ROWS":
                a_, b_ = d["startIndex"], d["endIndex"]
                n = b_ - a_ + 1
                t["cells"] = {(r if r < a_ else r - n, c): v for (r, c), v in t["cells"].items()
                              if not a_ <= r <= b_}
                t["rows"] -= n
            return {"data": {}}
        return {"data": {}}


class GhiCu:
    """Nhìn các tab dữ liệu như list [(mã tab cũ, dòng gồm tiêu đề)] của fixture cũ (giả
    `_write_values`). `ban_do`: tên gốc của tab (bỏ "N. ") → mã cũ; "Dữ liệu" = tab đơn."""

    def __init__(self, gia: LarkGia, ban_do: dict, tok=None, ba: bool = False):
        self.gia, self.ban_do, self.tok, self.ba = gia, ban_do, tok, ba

    def _ds(self):
        if not self.gia.bt:
            return []
        ra = []
        for ten in self.gia.tab_ten(self.tok):
            goc = re.sub(r"^\d+\. ", "", ten)
            if goc in ("Tổng quan", "Dữ liệu gốc") or goc not in self.ban_do:
                continue
            muc = (self.ban_do[goc], self.gia.du_lieu(ten, self.tok))
            ra.append(muc + ({},) if self.ba else muc)
        return ra

    def __iter__(self):
        return iter(self._ds())

    def __len__(self):
        return len(self._ds())

    def __getitem__(self, i):
        return self._ds()[i]
