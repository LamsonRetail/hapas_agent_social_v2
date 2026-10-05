"""Ghi Lark Sheet CỠ LỚN cho việc nền (10.000+ dòng), ghi tiếp được sau khi khởi động lại.

Vì sao không dùng thẳng `apify_tool._write_values`: hàm đó bắn liền các khối 1000 dòng,
không nghỉ, không thử lại — đủ cho ≤600 bài của lượt tại chỗ. 10.000 bài là 10–20 lượt
gọi liên tiếp: Lark trả "frequency limit"/429 giữa chừng, và lưới mặc định của tab mới chỉ
có ~200 dòng. Ở đây: khối ≤1000 dòng, nghỉ ~0,2 giây giữa các khối, lùi dần khi 429, tự
thêm dòng (`dimension_range`) khi lưới thiếu, và ghi `da_ghi` của từng tab vào sổ việc
sau MỖI khối — khởi động lại thì ghi tiếp từ đó, không nhân đôi dòng.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

import apify_tool as A

KHOI = 1000            # dòng mỗi lượt ghi
NGHI = 0.2             # giây nghỉ giữa hai khối
LUOI_MAC_DINH = 200    # số dòng lưới của tab mới khi Lark không nói
_THEM_TOI_DA = 5000    # dòng tối đa mỗi lượt `dimension_range`
_ngu = time.sleep

_RE_DAY = re.compile(r"(?i)\b429\b|frequency|too many|rate.?limit|90217|99991400")


def _goi(method: str, path: str, **kw) -> dict:
    """lark.call có lùi dần khi Lark báo vượt tần suất (5 lần, 1,5 → 24 giây)."""
    for lan in range(6):
        try:
            return A.lark.call(method, path, **kw)
        except RuntimeError as e:
            if lan < 5 and _RE_DAY.search(str(e)):
                _ngu(min(30.0, 1.5 * 2 ** lan))
                continue
            raise
    return {}


class SoSheet:
    """Trạng thái sheet trong sổ việc: v.d["sheet"] = {token, url, granted, giai_doan,
    tabs: {tên: {sheet_id, da_ghi, so_dong_cu, luoi, hash, rong, cot}}}. `cot` = số cột
    lưới sau khi đã bỏ cột trống thừa (None/thiếu = chưa biết, lưới mặc định của Lark).

    MỌI thay đổi `v.d` đi dưới `v._khoa` (review 02/10/2026: luồng khác đang json.dumps sổ
    việc mà dict đổi cỡ giữa chừng là RuntimeError, mất lần lưu)."""

    def __init__(self, v):
        self.v = v
        with v._khoa:
            self.s = v.d.setdefault("sheet", {})
            self.s.setdefault("tabs", {})

    @property
    def co(self) -> bool:
        return bool(self.s.get("token"))

    def _luu(self):
        self.v.luu()

    def _luoi(self) -> dict:
        try:
            r = _goi("GET", f"/open-apis/sheets/v3/spreadsheets/{self.s['token']}/sheets/query")
        except Exception:  # noqa: BLE001
            return {}
        ra = {}
        for sh in (r.get("data") or {}).get("sheets") or []:
            g = sh.get("grid_properties") or {}
            if sh.get("sheet_id"):
                ra[sh["sheet_id"]] = int(g.get("row_count") or LUOI_MAC_DINH)
        return ra

    def dam_bao(self, title: str, tab_dau: str, nguoi: str = "") -> None:
        """Tạo sheet (một lần) + đổi tên tab đầu + cấp quyền cho người hỏi."""
        if self.co:
            return
        tok, url = A._create_sheet(title)
        sid = A._first_sheet_id(tok)
        with self.v._khoa:
            self.s.update(token=tok, url=url, title=title, giai_doan="so_bo")
            self.s["tabs"][tab_dau] = {"sheet_id": sid, "da_ghi": 0, "so_dong_cu": 0,
                                       "luoi": LUOI_MAC_DINH}
            self._luu()
        try:
            _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{tok}/sheets_batch_update",
                 body={"requests": [{"updateSheet": {"properties": {
                     "sheetId": sid, "title": tab_dau}}}]})
        except Exception as e:  # noqa: BLE001 — tên tab xấu không làm hỏng dữ liệu
            print(f"[sheet_lon] đổi tên tab đầu lỗi: {A._che_token(e)[:120]}")
        luoi = self._luoi()
        if sid in luoi:
            with self.v._khoa:
                self.s["tabs"][tab_dau]["luoi"] = luoi[sid]
        granted = A._grant(tok, nguoi) if str(nguoi or "").startswith("ou_") else False
        with self.v._khoa:
            self.s["granted"] = granted
            self._luu()

    def dam_bao_tab(self, ten: str) -> dict:
        t = self.s["tabs"].get(ten)
        if t:
            return t
        sid = A._them_tab(self.s["token"], ten)
        t = {"sheet_id": sid, "da_ghi": 0, "so_dong_cu": 0,
             "luoi": self._luoi().get(sid, LUOI_MAC_DINH)}
        with self.v._khoa:
            self.s["tabs"][ten] = t
            self._luu()
        return t

    def _them_dong(self, t: dict, can: int) -> None:
        while t["luoi"] < can:
            n = min(_THEM_TOI_DA, can - t["luoi"] + KHOI)
            _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{self.s['token']}/dimension_range",
                 body={"dimension": {"sheetId": t["sheet_id"], "majorDimension": "ROWS",
                                     "length": n}})
            with self.v._khoa:
                t["luoi"] += n
                self._luu()

    def _them_cot(self, t: dict, can: int) -> None:
        """Tab đã bị bỏ cột thừa (`cot`) mà bảng mới rộng hơn: nới lưới trước khi ghi."""
        cot = t.get("cot")
        if cot and can > cot:
            _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{self.s['token']}/dimension_range",
                 body={"dimension": {"sheetId": t["sheet_id"], "majorDimension": "COLUMNS",
                                     "length": can - cot}})
            with self.v._khoa:
                t["cot"] = can
                self._luu()

    def _ghi_khoi(self, t: dict, dong_dau: int, khoi: list[list]) -> None:
        kiem = getattr(self.v, "kiem_quyen", None)
        if kiem:
            kiem()                          # tiến trình đã mất quyền chủ thì không ghi sheet
        khoi = A._bang_an_toan(khoi)        # chữ người lạ viết: chặn chèn công thức
        so_cot = max((len(r) for r in khoi), default=1)
        rong = A._cot(so_cot)
        cuoi = dong_dau + len(khoi) - 1
        self._them_dong(t, cuoi)
        self._them_cot(t, so_cot)
        _goi("POST", f"/open-apis/sheets/v2/spreadsheets/{self.s['token']}/values_batch_update",
             body={"valueRanges": [{"range": f"{t['sheet_id']}!A{dong_dau}:{rong}{cuoi}",
                                    "values": khoi}]})

    def bat_dau_giai_doan(self, giai_doan: str) -> None:
        """Đổi giai đoạn ("so_bo" → "cuoi"): mọi tab ghi lại TỪ ĐẦU một lần."""
        if self.s.get("giai_doan") == giai_doan:
            return
        with self.v._khoa:
            for t in self.s["tabs"].values():
                t["da_ghi"] = 0
            self.s["giai_doan"] = giai_doan
            self._luu()

    def ghi_tab(self, ten: str, bang: list[list], tu_dau: bool = False) -> int:
        """Ghi `bang` (dòng 0 = tiêu đề) vào tab, tiếp từ `da_ghi`. -> số dòng đã có.

        Ghi tiếp chỉ khi bảng Y HỆT lần ghi dở trước (băm `hash`): khởi động lại mà danh sách
        kết quả đã khác (vd lần trước có AI, lần này không) thì nửa trên của tab thuộc danh
        sách cũ, nửa dưới thuộc danh sách mới — review 02/10/2026. Bảng khác -> ghi lại từ
        dòng 1. Mọi dòng đệm tới cột RỘNG NHẤT từng ghi (`rong`) để cột thừa của bản cũ
        (bản sơ bộ) bị xoá chứ không nằm lại."""
        t = self.dam_bao_tab(ten)
        rong = max(max((len(r) for r in bang), default=1), int(t.get("rong") or 0))
        bang = [list(r) + [""] * (rong - len(r)) for r in bang]
        h = hashlib.sha1(json.dumps(bang, ensure_ascii=False, default=str)
                         .encode("utf-8")).hexdigest()
        with self.v._khoa:
            if tu_dau or t.get("hash") != h:
                t["da_ghi"] = 0
            t["hash"], t["rong"] = h, rong
            self._luu()
        i = int(t.get("da_ghi") or 0)
        while i < len(bang):
            khoi = bang[i:i + KHOI]
            self._ghi_khoi(t, i + 1, khoi)
            i += len(khoi)
            with self.v._khoa:
                t["da_ghi"] = i
                t["so_dong_cu"] = max(int(t.get("so_dong_cu") or 0), i)
                self._luu()
            if i < len(bang):
                _ngu(NGHI)
        # Giai đoạn trước (bản sơ bộ) ghi NHIỀU dòng hơn thì xoá phần thừa, kẻo bài đã bị
        # AI loại vẫn nằm dưới đáy tab như bài được giữ.
        thua = int(t.get("so_dong_cu") or 0) - len(bang)
        j = len(bang)
        while thua > 0:
            n = min(KHOI, thua)
            self._ghi_khoi(t, j + 1, [[""] * rong for _ in range(n)])
            j += n
            thua -= n
            _ngu(NGHI)
        with self.v._khoa:
            t["so_dong_cu"] = len(bang)
            self._luu()
        # Ghi xong cả bảng mới bỏ cột trống thừa bên phải (lưới mặc định 20 cột); khởi động
        # lại giữa chừng thì lần ghi tiếp làm. Bảng sau rộng hơn thì `_them_cot` nới lại.
        if t.get("cot") != rong:
            cot = A._vua_cot(self.s["token"], t["sheet_id"], rong)
            with self.v._khoa:
                t["cot"] = cot
                self._luu()
        return len(bang)
