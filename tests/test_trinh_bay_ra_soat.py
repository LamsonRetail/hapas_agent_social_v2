"""Rà soát 09/10/2026 lớp trình bày (`trinh_bay_sheet`) — Lark GIẢ, không mạng.

Canh: Tổng quan hỏng không làm mất bảng tí hon (vốn gấp vào nó) và không bao giờ nhận
"đủ"; ghi gặp 429 thì lùi và ghi lại đúng vùng, có nghỉ giữa các khối; bảng tính thứ hai
hỏng vẫn xong phần đầu; không đọc được lưới vẫn nới lưới (Lark giả từ chối ghi vượt lưới);
dòng cuối trống hợp lệ không bị coi là thiếu; Tổng quan dạng nhãn | giá trị, không ô "" chặn
chữ tràn, cột D rộng; ô dài cắt không để đoạn sau bị chặn công thức; ghi đè Tổng quan xoá
dòng cũ.
"""
from __future__ import annotations

import datetime

import pytest

import apify_tool as A
import trinh_bay_sheet as T
from sheet_gia import LarkGia

LUC = datetime.datetime(2026, 10, 8, 9, 30, tzinfo=T.VN)


@pytest.fixture
def gia(monkeypatch):
    g = LarkGia()
    monkeypatch.setattr(A.lark, "call", g.call)
    return g


def _hong_add_tong_quan(gia):
    """Chỉ addSheet của tab Tổng quan hỏng (các tab khác vẫn thêm được)."""
    goc = gia.call

    def call(method, path, query=None, body=None):
        if path.endswith("/sheets_batch_update") and any(
                r.get("addSheet", {}).get("properties", {}).get("title") == T.TAB_TONG_QUAN
                for r in body["requests"]):
            raise RuntimeError("Lark POST sheets_batch_update failed: HTTP 500")
        return goc(method, path, query, body)
    A.lark.call = call


def _hai_bang():
    lon = T.Bang("Bình luận", [T.Cot("Nội dung", "chu_dai")], [["n"]] * 9)
    nho = T.Bang("Bài đăng", [T.Cot("Link", "link"), T.Cot("Trạng thái")],
                 [["u1", "CHẠM TRẦN"], ["u2", "OK"]], mo_ta="trạng thái từng bài")
    return lon, nho


def test_tong_quan_hong_thi_bang_gap_thanh_tab_rieng_va_khong_nhan_du(gia):
    _hong_add_tong_quan(gia)
    lon, nho = _hai_bang()
    tq = T.TongQuan("Soi", ghi_chu=["ĐÃ CẮT ở 20.000 dòng; hãy thu hẹp ngày."])
    kq = T.xuat("Soi", [lon, nho], tq)
    ten = gia.tab_ten()
    assert "Tổng quan" not in ten and "Bài đăng" in ten, "bảng tí hon không mất"
    assert gia.du_lieu("Bài đăng") == [["Link", "Trạng thái"], ["u1", "CHẠM TRẦN"],
                                       ["u2", "OK"]]
    assert kq.day_du is False and kq.tong_quan_hong
    assert "Tổng quan" in kq.cau_kiem and kq.cau_kiem.startswith("CẢNH BÁO GHI THIẾU")
    ra = kq.cho_tool()
    assert ra["day_du"] is False and "Thêm tab Tổng quan HỎNG" in ra["canh_bao_trinh_bay"]
    assert ra["ghi_chu_sheet"] == ["ĐÃ CẮT ở 20.000 dòng; hãy thu hẹp ngày."]


def test_ghi_tong_quan_hong_thi_cung_chuyen_bang_gap(gia):
    goc = gia.call
    sid_tq = {}

    def call(method, path, query=None, body=None):
        if path.endswith("/sheets_batch_update"):
            d = goc(method, path, query, body)
            for r, rep in zip(body["requests"], d["data"]["replies"]):
                if r.get("addSheet", {}).get("properties", {}).get("title") == "Tổng quan":
                    sid_tq["sid"] = rep["addSheet"]["properties"]["sheetId"]
            return d
        if path.endswith("/values_batch_update") and sid_tq.get("sid") and any(
                vr["range"].startswith(sid_tq["sid"] + "!") for vr in body["valueRanges"]):
            raise RuntimeError("Lark 500")
        return goc(method, path, query, body)
    A.lark.call = call
    lon, nho = _hai_bang()
    kq = T.xuat("Soi", [lon, nho], T.TongQuan("Soi"))
    assert any(t.ten == "Bài đăng" for t in kq.tabs) and kq.day_du is False
    assert gia.du_lieu("Bài đăng")[1] == ["u1", "CHẠM TRẦN"]
    assert "Ghi tab Tổng quan HỎNG" in kq.cho_tool()["canh_bao_trinh_bay"]


def test_tong_quan_ghi_du_thi_kiem_gom_ca_tong_quan(gia):
    lon, nho = _hai_bang()
    kq = T.xuat("Soi", [lon, nho], T.TongQuan("Soi"))
    assert kq.day_du is True and "Bài đăng" not in gia.tab_ten()
    tq_k = [t for t in kq.kiem["tabs"] if t["tab"] == "Tổng quan"]
    assert tq_k and tq_k[0]["ket"] == "du"
    assert "canh_bao_trinh_bay" not in kq.cho_tool() and "ghi_chu_sheet" not in kq.cho_tool()


def test_429_giua_chung_thi_lui_va_ghi_lai_dung_vung(gia, monkeypatch):
    goc = gia.call
    dem = {"n": 0}
    ngu = []
    monkeypatch.setattr(T, "_ngu", ngu.append)

    def call(method, path, query=None, body=None):
        if path.endswith("/values_batch_update"):
            dem["n"] += 1
            if dem["n"] in (2, 3):
                raise RuntimeError("Lark POST values_batch_update failed: HTTP 429: "
                                   "frequency limit")
        return goc(method, path, query, body)
    A.lark.call = call
    b = T.Bang("Bài", [T.Cot("a", "so_nguyen")], [[i] for i in range(2500)])
    kq = T.xuat("x", [b])
    assert kq.day_du is True
    assert [r[0] for r in gia.du_lieu("Dữ liệu")[1:]] == list(range(2500))
    assert 1.5 in ngu and 3.0 in ngu, "lùi dần khi 429"
    assert ngu.count(T.NGHI_GHI) >= 2, "nghỉ giữa các khối 1000 dòng"


def test_bang_tinh_thu_hai_hong_van_xong_phan_dau(gia):
    goc = gia.call
    tao = {"n": 0}

    def call(method, path, query=None, body=None):
        if path == "/open-apis/sheets/v3/spreadsheets":
            tao["n"] += 1
            if tao["n"] == 2:
                raise RuntimeError("Lark 500: tạo bảng tính hỏng")
        return goc(method, path, query, body)
    A.lark.call = call
    quyen = []
    ds = [T.Bang(f"B{i}", [T.Cot("a")] * 7, [["x"] * 7] * 6) for i in range(12)]
    kq = T.xuat("Nhiều", ds, cap_quyen=quyen.append)
    assert quyen == ["sht1"] and kq.urls == [kq.url]
    assert kq.day_du is False and "phần 2/2 HỎNG" in kq.cau_kiem
    assert kq.cho_tool()["bang_tinh_hong"][0]["phan"] == "2/2"
    assert "Tổng quan" in gia.tab_ten("sht1")


def test_lark_gia_tu_choi_ghi_vuot_luoi(gia):
    tok = gia.call("POST", "/open-apis/sheets/v3/spreadsheets", None,
                   {"title": "t"})["data"]["spreadsheet"]["spreadsheet_token"]
    with pytest.raises(RuntimeError, match="vượt lưới"):
        A._write_values(tok, f"{tok}_s0", [[1]] * 3, dong_dau=199)


def test_khong_doc_duoc_luoi_van_noi_luoi_truoc_khi_ghi(gia):
    goc = gia.call
    dem = {"n": 0}

    def call(method, path, query=None, body=None):
        if path.endswith("/sheets/query"):
            dem["n"] += 1
            if dem["n"] > 1:                       # lần 1 = _first_sheet_id; sau đó hỏng
                raise RuntimeError("Lark 500")
        return goc(method, path, query, body)
    A.lark.call = call
    b = T.Bang("Bài", [T.Cot(f"c{i}") for i in range(25)], [["v"] * 25] * 450)
    kq = T.xuat("x", [b])
    assert len(gia.du_lieu("Dữ liệu")) == 451 and kq.url
    them = [b["dimension"] for m, p, q, b in gia.goi
            if m == "POST" and p.endswith("/dimension_range")]
    assert {"sheetId": "sht1_s0", "majorDimension": "ROWS", "length": 251} in them
    assert {"sheetId": "sht1_s0", "majorDimension": "COLUMNS", "length": 5} in them


def test_dong_cuoi_trong_hop_le_khong_bi_coi_la_thieu(gia):
    b = T.Bang("Bài", [T.Cot("a"), T.Cot("b")], [["x", "1"], ["y", "2"], ["", ""]])
    kq = T.xuat("x", [b])
    assert kq.day_du is True and kq.tabs[0].r_kiem == 3


def test_tong_quan_nhan_gia_tri_rong_va_khong_o_rong_chan_chu(gia):
    lon, nho = _hai_bang()
    tq = T.TongQuan("Soi", nguon="social_deep_dive", thoi_gian="01/10–08/10",
                    pham_vi="9 bài " + "x" * 60,
                    so_lieu=[T.SoLieu("Bình luận", 9, "so_nguyen", ghi_chu="đã ghi")])
    T.xuat("Soi", [lon, T.Bang("C", [T.Cot("a")], [["z"]] * 8), nho], tq, luc=LUC)
    o = gia.tab("Tổng quan")
    sid = o["sheet_id"]
    assert {r: o["cells"][(r, 1)] for r in range(2, 6)} == {
        2: "Nguồn", 3: "Thời gian", 4: "Phạm vi", 5: "Tạo lúc"}
    assert o["cells"][(4, 2)].startswith("9 bài ")
    for r in range(1, max(k[0] for k in o["cells"]) + 1):
        hang = [c for (rr, c) in o["cells"] if rr == r]
        if hang:
            assert o["cells"][(r, max(hang))] not in ("", None), \
                f"dòng {r}: ô trống cuối dòng chặn chữ tràn"
    gop = [b for m, p, q, b in gia.goi if p.endswith("/merge_cells")]
    assert {"range": f"{sid}!B2:D5", "mergeType": "MERGE_ROWS"} in gop
    assert any(st.get("hAlign") == 0 for st in gia.kieu_o("Tổng quan", 2, 3))
    assert gia.rong("Tổng quan")[4] == 520, "cột D (Nội dung / Kết quả / Ghi chú) rộng"
    tq_o = gia.o("Tổng quan")
    k = next(i for i, r in enumerate(tq_o) if r[0] == "KIỂM GHI")
    assert tq_o[k + 1] == ["Tab", "Số dòng", "Số cột", "Kết quả"]
    assert tq_o[k + 2][3].startswith("Đã ghi đủ"), "kết quả kiểm ở cột D rộng"
    m = next(i for i, r in enumerate(tq_o) if r[0] == "MỤC LỤC")
    assert tq_o[m + 1] == ["Tab", "Số dòng", "Số cột", "Nội dung"]
    assert o["cols"] >= 4


def test_cat_o_dai_khong_de_doan_sau_mo_dau_bang_ky_tu_cong_thuc(gia):
    s = "a" * (T.TRAN_KY_TU_O - 1) + "=+-@ x" + "b" * 10
    doan = T._cat_o(s)
    assert "".join(doan) == s and all(not T._dau_nguy(d[0]) for d in doan[1:])
    T.xuat("x", [T.Bang("Bài", [T.Cot("Nội dung", "chu_dai")], [[s]])])
    d = gia.o("Dữ liệu")
    assert d[1][0] + d[1][1] == s, "ghép lại đúng nguyên văn, không bị chèn dấu nháy"


def test_ghi_de_tong_quan_xoa_dong_cu(gia):
    kq = T.xuat("x", [T.Bang("Bài", [T.Cot("a")], [["1"]] * 8)],
                T.TongQuan("x", ghi_chu=[f"ghi chú {i}" for i in range(20)]))
    cu = len(gia.o("Tổng quan"))
    n = T.ghi_tong_quan_vao(kq.token, kq.tong_quan_sid, kq.url, T.TongQuan("x"), kq.tabs,
                            so_dong_cu=cu)
    assert len(gia.o("Tổng quan")) == n < cu and "ghi chú 19" not in str(gia.o("Tổng quan"))


def test_granted_la_and_cua_moi_bang_tinh():
    cap = {"granted": False}
    T.gop_quyen(cap, True)
    assert cap["granted"] is True
    T.gop_quyen(cap, False)
    T.gop_quyen(cap, True)
    assert cap["granted"] is False, "một phần không cấp được thì không báo đã cấp"


def test_gia_tri_sieu_du_lieu_gop_truoc_roi_moi_canh_trai(gia):
    """Lark căn giữa ô vừa gộp (live 09/10/2026): tô hAlign=0 phải đến SAU lần gộp B:D."""
    T.xuat("Soi", [T.Bang("Bài", [T.Cot("a")], [["1"]])],
           T.TongQuan("Soi", nguon="account_tool", thoi_gian="01/10–08/10"), luc=LUC)
    sid = gia.tab("Tổng quan")["sheet_id"]
    i_gop = next(i for i, (m, p, q, b) in enumerate(gia.goi) if p.endswith("/merge_cells")
                 and b["range"].startswith(f"{sid}!B2:") and b["mergeType"] == "MERGE_ROWS")
    i_kieu = [i for i, (m, p, q, b) in enumerate(gia.goi)
              if p.endswith("/styles_batch_update") and any(
                  r.startswith(f"{sid}!B2:") and d["style"].get("hAlign") == 0
                  and d["style"].get("vAlign") == 1
                  for d in b["data"] for r in d["ranges"])]
    assert i_kieu and min(i_kieu) > i_gop, "canh trái + giữa dọc đặt SAU khi gộp"
    assert all(st.get("hAlign") == 0 for st in gia.kieu_o("Tổng quan", 2, 2)
               if "hAlign" in st)


def test_gia_tri_sieu_du_lieu_dai_chia_nhieu_dong_khong_cat(gia):
    nguon = ("account_tool · Facebook (apify~facebook-posts-scraper), Instagram "
             "(apify~instagram-profile-scraper), TikTok (clockworks~tiktok-profile-scraper); "
             "YouTube Data API v3")
    T.xuat("Soi", [T.Bang("Bài", [T.Cot("a")], [["1"]])],
           T.TongQuan("Soi", nguon=nguon, thoi_gian="01/10–08/10"), luc=LUC)
    tq = gia.o("Tổng quan")
    i = next(k for k, r in enumerate(tq) if r[0] == "Nguồn")
    dong = [tq[i][1]]
    k = i + 1
    while tq[k][0] == "" and tq[k][1]:
        dong.append(tq[k][1])
        k += 1
    assert len(dong) >= 2 and all(len(d) <= T.TRAN_KY_TU_META for d in dong)
    assert " ".join(dong) == nguon, "đủ nguyên văn, không cắt"
    assert tq[k][0] == "Thời gian", "nhãn chỉ ở dòng đầu, dòng sau là nhãn kế tiếp"
    sid = gia.tab("Tổng quan")["sheet_id"]
    gop = [b for m, p, q, b in gia.goi if p.endswith("/merge_cells")]
    assert {"range": f"{sid}!B2:D{k + 2}", "mergeType": "MERGE_ROWS"} in gop, \
        "mọi dòng giá trị (cả dòng tiếp) gộp B:D"
    assert T._tach_dong("x" * 200) == ["x" * 90, "x" * 90, "x" * 20], "từ quá dài: cắt cứng"
