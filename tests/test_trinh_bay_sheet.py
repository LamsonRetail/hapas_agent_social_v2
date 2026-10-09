"""Lớp trình bày chung của Lark Sheet (`trinh_bay_sheet`, 08/10/2026) — Lark GIẢ, không mạng.

Canh: bố cục tất định (BAO_CAO/DANH_SACH/NHIEU_BANG/LON), tab Tổng quan + tab dữ liệu đúng
thứ tự/tên, kiểu tiêu đề, cố định dòng 1, bộ lọc, định dạng số theo kiểu cột, mã ghi dạng chữ,
quy ước phần trăm, dòng tổng, độ rộng, thứ tự riêng tư (khoá trước khi ghi, cấp quyền sau),
trang trí hỏng vẫn đủ dữ liệu + link, chặn chèn công thức, chia khối lớn, ô dài chảy sang cột
"(tiếp)", tab "Dữ liệu gốc", đọc lại kiểm ghi.
"""
from __future__ import annotations

import datetime

import pytest

import apify_tool as A
import sheet_lon
import trinh_bay_sheet as T
from sheet_gia import LarkGia
from test_viec_nen import _VGia

LUC = datetime.datetime(2026, 10, 8, 9, 30, tzinfo=T.VN)


@pytest.fixture
def gia(monkeypatch):
    g = LarkGia()
    monkeypatch.setattr(A.lark, "call", g.call)
    monkeypatch.setattr(T.time, "sleep", lambda s: None)
    T._LOC_LUOT.clear()
    return g


def _bang_ads():
    return T.Bang("Số ads", [T.Cot("Tài khoản"), T.Cot("Mã TK", "ma"), T.Cot("Tiền tệ"),
                             T.Cot("Từ ngày", "ngay"), T.Cot("Chi tiêu", "tien",
                                                             cot_tien_te="Tiền tệ"),
                             T.Cot("Hiển thị", "so_nguyen"), T.Cot("CTR (%)", "phan_tram_100"),
                             T.Cot("ROAS", "ti_le"), T.Cot("Tỉ lệ chốt", "phan_tram")],
                  [["HAPAS A", "act_123", "VND", "2026-10-01", 1500000.0, 12000, 1.25, 2.5,
                    0.125],
                   ["HAPAS B", 7312345678901234567, "USD", datetime.date(2026, 10, 2), 12.5,
                    800, 0.5, 1.1, 0.05]],
                  dong_tong=[["TỔNG VND", "", "VND", "", 1500000.0, 12000, 1.25, 2.5, ""],
                             ["TỔNG USD", "", "USD", "", 12.5, 800, 0.5, 1.1, ""]],
                  mo_ta="Số theo tài khoản")


def _tq(**k):
    return T.TongQuan(tieu_de="Báo cáo thử", nguon="chi_so_ads", thoi_gian="01/10–02/10",
                      pham_vi="2 tài khoản",
                      so_lieu=[T.SoLieu("Chi tiêu (VND)", 1500000.0, "tien", "VND")],
                      ghi_chu=["Số theo phân bổ mặc định của Meta."], **k)


# ───────────────────────── kế hoạch bố cục ─────────────────────────
def test_ke_hoach_tat_dinh_va_dung_loai():
    b = _bang_ads()
    ds = T.Bang("Bài", [T.Cot("Link", "link")], [["u"]] * 10)
    assert T.ke_hoach([b], _tq()).loai == T.BAO_CAO
    assert T.ke_hoach([ds], T.TongQuan("x")).loai == T.DANH_SACH
    assert T.ke_hoach([b, ds]).loai == T.NHIEU_BANG
    lon = T.Bang("Lớn", [T.Cot("a")], [["x"]] * (T.NGUONG_LON_DONG + 1))
    assert T.ke_hoach([lon]).loai == T.LON and T.ke_hoach([lon]).lon
    k1, k2 = T.ke_hoach([b, ds], _tq()), T.ke_hoach([b, ds], _tq())
    assert [[t.ten for t in bt] for bt in k1.bang_tinh] == \
        [[t.ten for t in bt] for bt in k2.bang_tinh] == [["1. Số ads", "2. Bài"]]
    assert T.ke_hoach([ds]).bang_tinh[0][0].ten == "Dữ liệu", "một bảng → tab 'Dữ liệu'"


def test_bang_ti_hon_gap_vao_tong_quan_va_ten_tab_sach():
    lon = T.Bang("Hồ sơ: [KOC] / A*B?", [T.Cot("a")], [["x"]] * 9)
    nho = T.Bang("Nhỏ", [T.Cot("a"), T.Cot("b")], [["1", "2"]])
    ba = T.Bang("Hồ sơ: [KOC] / A*B?", [T.Cot("a")], [["y"]] * 7)
    kh = T.ke_hoach([lon, nho, ba])
    ten = [t.ten for t in kh.bang_tinh[0]]
    assert [g.ten for g in kh.gap] == ["Nhỏ"], "bảng ≤5 dòng ≤6 cột gấp vào Tổng quan"
    assert ten == ["1. Hồ sơ KOC A B", "2. Hồ sơ KOC A B"]
    assert all(len(t) <= 30 and not set(t) & set("/\\?*[]:") for t in ten)
    assert T.ten_tab_sach("x" * 40, ["x" * 30]) == "x" * 26 + " (2)"
    # Chỉ một bảng (dù tí hon) thì không gấp — tab dữ liệu vẫn có.
    assert T.ke_hoach([nho]).gap == [] and T.ke_hoach([nho]).bang_tinh[0][0].ten == "Dữ liệu"


def test_qua_10_tab_sang_bang_tinh_tiep_va_bang_qua_tran_o_tach_phan(monkeypatch):
    ds = [T.Bang(f"B{i}", [T.Cot("a")] * 7, [["x"] * 7] * 6) for i in range(12)]
    kh = T.ke_hoach(ds)
    assert [len(bt) for bt in kh.bang_tinh] == [10, 2]
    monkeypatch.setattr(T, "TRAN_O_MOI_TAB", 20 * 6)       # 20 cột → 3 dòng/phần
    b = T.Bang("Bài", [T.Cot("a")], [[i] for i in range(10)], dong_tong=[["T"]])
    tabs = T.ke_hoach([b]).bang_tinh[0]
    assert [t.ten for t in tabs] == ["Dữ liệu (phần 1 của 4)", "Dữ liệu (phần 2 của 4)",
                                     "Dữ liệu (phần 3 của 4)", "Dữ liệu (phần 4 của 4)"]
    assert sum(len(t.dong) for t in tabs) == 10 and [t.co_tong for t in tabs] == \
        [False, False, False, True], "dòng tổng chỉ ở phần cuối"


# ───────────────────────── dựng bảng tính ─────────────────────────
def test_xuat_bao_cao_day_du_bo_cuc(gia):
    kq = T.xuat("Báo cáo thử", [_bang_ads()], _tq(), luc=LUC)
    assert kq.loai == T.BAO_CAO and kq.url.endswith("/sht1")
    assert gia.tab_ten() == ["Tổng quan", "Dữ liệu"]
    tq = gia.o("Tổng quan")
    assert tq[0][0] == "Báo cáo thử"
    assert [r[:2] for r in tq[1:5]] == [["Nguồn", "chi_so_ads"], ["Thời gian", "01/10–02/10"],
                                         ["Phạm vi", "2 tài khoản"],
                                         ["Tạo lúc", "08/10/2026 09:30 (giờ VN)"]]
    assert tq[5][0] == "Đã ghi đủ 2/2 dòng ở 1 tab dữ liệu (đã đọc lại kiểm)."
    assert ["Chi tiêu (VND)", 1500000.0] == tq[tq.index(["SỐ LIỆU CHÍNH", "", "", ""]) + 2][:2]
    muc = next(i for i, r in enumerate(tq) if r[0] == "MỤC LỤC")
    link = tq[muc + 2][0]
    assert link["text"] == "Dữ liệu" and link["link"] == \
        f"{kq.url}?sheet={gia.tab('Dữ liệu')['sheet_id']}", "mục lục bấm được"
    assert tq[muc + 2][1:3] == [2, 9]
    assert ["• Số theo phân bổ mặc định của Meta.", "", "", ""] in tq
    d = gia.o("Dữ liệu")
    assert d[0][:3] == ["Tài khoản", "Mã TK", "Tiền tệ"]
    assert d[1][1] == "act_123" and d[2][1] == "7312345678901234567", "mã luôn là chữ"
    assert d[1][3] == 46296 and d[2][3] == 46297, "ngày thật (số ngày từ 1899-12-30)"
    assert d[1][6] == 1.25, "phần trăm đã nhân 100 giữ nguyên giá trị"
    assert d[3] == [""] * 9 and d[4][0] == "TỔNG VND" and d[5][0] == "TỔNG USD"
    # kiểu
    hd = gia.kieu_o("Dữ liệu", 1, 1)
    assert any(s.get("backColor") == T.NAVY and s.get("foreColor") == T.TRANG
               and s["font"]["bold"] for s in hd)
    fmt = {c: [s.get("formatter") for s in gia.kieu_o("Dữ liệu", c, 2) if "formatter" in s]
           for c in range(1, 10)}
    assert fmt[2] == ["@"] and fmt[4] == ["yyyy/MM/dd"] and fmt[6] == ["#,##0"]
    assert fmt[5] == ["#,##0"] and fmt[7] == ["#,##0.00"] and fmt[8] == ["#,##0.00"]
    assert fmt[9] == ["0.00%"], "phần trăm dạng phân số"
    assert [s.get("formatter") for s in gia.kieu_o("Dữ liệu", 5, 3)] == ["#,##0.00"], \
        "dòng USD định dạng theo tiền tệ của dòng"
    tong = gia.kieu_o("Dữ liệu", 6, 5)
    assert any(s.get("backColor") == T.XAM_TONG and s["font"]["bold"]
               and s.get("formatter") == "#,##0" for s in tong), "dòng tổng đậm nền xám"
    assert gia.kieu_o("Dữ liệu", 1, 4) == [], "dòng trống giữa dữ liệu và tổng không tô"
    assert gia.tab("Dữ liệu")["frozen"] == 1
    sid = gia.tab("Dữ liệu")["sheet_id"]
    assert gia.loc() == [(f"/open-apis/sheets/v3/spreadsheets/sht1/sheets/{sid}/filter",
                          {"range": f"{sid}!A1:I3", "col": "A",
                           "condition": {"filter_type": "clear"}})], "lọc không gồm dòng tổng"
    rong = gia.rong("Dữ liệu")
    assert rong[2] == 140 and rong[4] == 100 and rong[6] == 110
    assert any(p.endswith("/merge_cells") and b["range"].endswith("!A1:D1")
               for m, p, q, b in gia.goi), "gộp ô tiêu đề Tổng quan"
    assert kq.day_du is True and kq.cho_tool()["kiem_ghi"] == kq.cau_kiem


def test_rieng_tu_khoa_truoc_khi_ghi_cap_quyen_sau_cung(gia):
    nhat_ky = []
    goc = gia.call

    def call(method, path, query=None, body=None):
        nhat_ky.append(path)
        return goc(method, path, query, body)
    A.lark.call = call
    T.xuat("Riêng", [_bang_ads()], _tq(),
           sau_khi_tao=lambda tok: nhat_ky.append(f"KHOA {tok}"),
           cap_quyen=lambda tok: nhat_ky.append(f"CAP {tok}"))
    i_khoa = nhat_ky.index("KHOA sht1")
    i_ghi = [i for i, p in enumerate(nhat_ky) if p.endswith("/values_batch_update")]
    assert i_khoa == 1, "khoá ngay sau khi tạo, trước mọi request khác"
    assert i_khoa < min(i_ghi) and nhat_ky[-1] == "CAP sht1" and max(i_ghi) < len(nhat_ky) - 1


def test_cap_quyen_nem_thi_loi_di_ra(gia):
    def hong(tok):
        raise ValueError("chưa chia sẻ được")
    with pytest.raises(ValueError):
        T.xuat("Riêng", [_bang_ads()], _tq(), cap_quyen=hong)


def test_trang_tri_hong_van_du_du_lieu_va_link(gia):
    gia.hong = {"styles_batch_update", "/filter", "merge_cells"}
    kq = T.xuat("Báo cáo thử", [_bang_ads()], _tq())
    assert kq.url and gia.o("Dữ liệu")[1][:2] == ["HAPAS A", "act_123"]
    assert kq.day_du is True and kq.canh_bao, "chỉ cảnh báo"
    assert gia.o("Dữ liệu")[1][3] == "01/10/2026", "không đặt được định dạng → ngày dạng chữ"
    assert gia.tab("Dữ liệu")["frozen"] == 1


#: Định dạng Lark THẬT nhận (09/10/2026: dd/MM/yyyy, '#,##0 "₫"', '0.00"%"', "0.00" đều bị
#: từ chối với 90204 invalid formatter) — đúng danh sách tài liệu.
_DINH_DANG_TAI_LIEU = {"", "@", "0", "#,##0", "#,##0.00", "0%", "0.00%", "0.00E+00",
                       "¥#,##0", "¥#,##0.00", "$#,##0", "$#,##0.00", "yyyy/MM/dd",
                       "yyyy-MM-dd", "HH:mm:ss", "yyyy/MM/dd HH:mm:ss"}


def test_chi_gui_dinh_dang_trong_tai_lieu_mot_lan_khong_bi_tu_choi(gia):
    """Lark từ chối cả lô kiểu nếu có MỘT định dạng lạ: chỉ gửi định dạng trong tài liệu,
    và lô định dạng trước khi ghi đi qua ngay lần đầu (không có lần thử hỏng rồi lùi)."""
    goc = gia.call
    loi = []

    def call(method, path, query=None, body=None):
        if path.endswith("/styles_batch_update"):
            la = [d["style"]["formatter"] for d in body["data"]
                  if "formatter" in d["style"]
                  and d["style"]["formatter"] not in _DINH_DANG_TAI_LIEU]
            if la:
                loi.append(la)
                raise RuntimeError("Lark PUT styles failed: HTTP 200: 90204 invalid formatter")
        return goc(method, path, query, body)
    A.lark.call = call
    kq = T.xuat("Báo cáo thử", [_bang_ads()], _tq())
    assert loi == [] and not kq.canh_bao
    fmt = [s.get("formatter") for s in gia.kieu_o("Dữ liệu", 4, 2)]
    assert fmt == ["yyyy/MM/dd"] and gia.o("Dữ liệu")[1][3] == 46296
    assert [s.get("formatter") for s in gia.kieu_o("Dữ liệu", 5, 2)] == ["#,##0"]


def test_chan_chen_cong_thuc_van_giu(gia):
    b = T.Bang("Bình luận", [T.Cot("Nội dung", "chu_dai")], [["=HYPERLINK(\"x\")"], ["@a"]])
    T.xuat("x", [b])
    assert [r[0] for r in gia.o("Dữ liệu")[1:]] == ["'=HYPERLINK(\"x\")", "'@a"]


def test_bang_lon_chia_khoi_dong_cot_va_noi_luoi(gia):
    cot = [T.Cot(f"c{i}", "so_nguyen") for i in range(130)]
    b = T.Bang("Lớn", cot, [[i] * 130 for i in range(2500)])
    kq = T.xuat("Lớn", [b])
    ghi = [b["valueRanges"][0]["range"] for m, p, q, b in gia.goi
           if p.endswith("/values_batch_update") and "sht1_s0" in b["valueRanges"][0]["range"]]
    assert len(ghi) == 6, "3 khối dòng × 2 khối cột (≤100 cột)"
    assert "sht1_s0!CW1:DZ1000" in ghi, "khối cột thứ hai bắt đầu ở cột 101"
    them = [b["dimension"] for m, p, q, b in gia.goi
            if m == "POST" and p.endswith("/dimension_range")]
    assert {"sheetId": "sht1_s0", "majorDimension": "ROWS", "length": 2301} in them
    assert {"sheetId": "sht1_s0", "majorDimension": "COLUMNS", "length": 110} in them
    vung = [r for r, s in gia.kieu() if s.get("formatter") == "#,##0"]
    assert all(int(r.split(":")[1].lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) -
               int(r.split("!")[1].split(":")[0].lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) < 5000
               for r in vung), "mỗi vùng kiểu ≤5000 dòng"
    assert kq.day_du is True and len(gia.du_lieu("Dữ liệu")) == 2501


def test_o_qua_dai_chay_sang_cot_tiep(gia):
    dai = "a" * (T.TRAN_KY_TU_O + 5)
    b = T.Bang("Bài", [T.Cot("Link", "link"), T.Cot("Nội dung", "chu_dai")],
               [["u1", dai], ["u2", "ngắn"]])
    T.xuat("x", [b])
    d = gia.o("Dữ liệu")
    assert d[0] == ["Link", "Nội dung", "Nội dung (tiếp)"]
    assert d[1][1] + d[1][2] == dai and len(d[1][1]) == T.TRAN_KY_TU_O
    assert d[2] == ["u2", "ngắn", ""]


def test_du_lieu_goc_moi_truong_lam_phang():
    g = T.bang_goc([{"id": 7312345678901234567, "author": {"name": "A", "stats": {"fans": 3}},
                     "tags": ["x", "y"]}, {"id": 2, "extra": True}])
    assert [c.ten for c in g.cot] == ["id", "author.name", "author.stats.fans", "tags", "extra"]
    assert g.cot[0].kieu == "ma"
    assert g.dong == [["7312345678901234567", "A", 3, '["x", "y"]', ""],
                      [2, "", "", "", "TRUE"]]


def test_tab_du_lieu_goc_cuoi_va_nhieu_bang_co_muc_luc(gia):
    a = T.Bang("Hồ sơ", [T.Cot("Tài khoản")], [["x"]] * 8, mo_ta="mỗi tài khoản một dòng")
    b = T.Bang("Bài đăng", [T.Cot("Link", "link")], [["u"]] * 9)
    c = T.Bang("Bình luận", [T.Cot("Nội dung", "chu_dai")], [["n"]] * 12)
    kq = T.xuat("Soi", [a, b, c], T.TongQuan("Soi"), goc=T.bang_goc([{"k": 1}] * 9))
    assert gia.tab_ten() == ["Tổng quan", "1. Hồ sơ", "2. Bài đăng", "3. Bình luận",
                             "Dữ liệu gốc"]
    assert kq.loai == T.NHIEU_BANG
    tq = gia.o("Tổng quan")
    muc = next(i for i, r in enumerate(tq) if r[0] == "MỤC LỤC")
    assert [(r[0]["text"], r[1], r[3]) for r in tq[muc + 2:muc + 6]] == [
        ("1. Hồ sơ", 8, "mỗi tài khoản một dòng"), ("2. Bài đăng", 9, ""),
        ("3. Bình luận", 12, ""), ("Dữ liệu gốc", 9, T.bang_goc([]).mo_ta)]
    assert all(gia.tab(t)["frozen"] == 1 for t in gia.tab_ten()[1:])
    assert len(gia.loc()) == 4


def test_doc_lai_thieu_thi_bao_khong_du(gia):
    goc = gia.call
    dem = {"n": 0}

    def call(method, path, query=None, body=None):
        if path.endswith("/values_batch_update") and "sht1_s0" in str(body):
            dem["n"] += 1
            if dem["n"] == 2:
                return {"data": {}}           # Lark "nhận" nhưng không ghi khối thứ hai
        return goc(method, path, query, body)
    A.lark.call = call
    b = T.Bang("Bài", [T.Cot("a")], [[i] for i in range(1500)])
    kq = T.xuat("x", [b])
    assert kq.day_du is False and kq.cau_kiem.startswith("CẢNH BÁO GHI THIẾU")
    assert "THIẾU" in gia.o("Tổng quan")[2][0]


def test_khong_doc_lai_duoc_thi_chua_kiem_khong_nhan_du():
    g = LarkGia(doc_lai=False)
    A_call = A.lark.call
    A.lark.call = g.call
    try:
        kq = T.xuat("x", [T.Bang("Bài", [T.Cot("a")], [["1"]])])
    finally:
        A.lark.call = A_call
    assert kq.day_du is None and "chưa đọc lại được" in kq.cau_kiem


def test_dem_theo_va_top_theo():
    b = T.Bang("Bài", [T.Cot("Nền tảng"), T.Cot("Views", "so_nguyen"), T.Cot("Link")],
               [["TikTok", 5, "a"], ["Threads", "", "b"], ["TikTok", 9, "c"], ["", 1, "d"]])
    assert T.dem_theo(b, "Nền tảng").dong == [("TikTok", 2), ("(trống)", 1), ("Threads", 1)]
    top = T.top_theo(b, "Views", 2, ["Link", "Views"])
    assert top.dong == [["c", 9], ["a", 5]] and T.top_theo(b, "Không có") is None


# ───────────────────────── bảng ghi dần (sheet_lon) ─────────────────────────
def test_sheet_lon_trang_tri_theo_cot_tong_quan_va_kiem(gia, monkeypatch):
    monkeypatch.setattr(sheet_lon, "_ngu", lambda s: None)
    monkeypatch.setattr(A, "_grant", lambda *a: True)
    s = sheet_lon.SoSheet(_VGia())
    s.dam_bao("Quét nền", "Tổng quan", "")
    bang = [["Nền tảng", "Ngày đăng", "Views", "Mã"]] + [
        ["tiktok", "2026-10-01 10:00", i, 7312345678901234567 + i] for i in range(1200)]
    cot = [T.Cot("Nền tảng"), T.Cot("Ngày đăng", "ngay_gio"), T.Cot("Views", "so_nguyen"),
           T.Cot("Mã", "ma")]
    s.ghi_tab("TikTok", bang, cot=cot, mo_ta="bài TikTok")
    d = gia.o("TikTok")
    assert d[1][3] == "7312345678901234567" and d[1][1] == "01/10/2026 10:00", \
        "mã thành chữ; ngày ghi chữ dd/MM/yyyy (định dạng chỉ đặt sau khi ghi)"
    assert gia.tab("TikTok")["frozen"] == 1 and len(gia.loc()) == 1
    assert [s_.get("formatter") for s_ in gia.kieu_o("TikTok", 3, 1201)] == ["#,##0"]
    n_kieu = sum(1 for m, p, q, b in gia.goi if p.endswith("/styles_batch_update"))
    s.ghi_tab("TikTok", bang, cot=cot)            # cùng bảng: không tô lại
    assert sum(1 for m, p, q, b in gia.goi if p.endswith("/styles_batch_update")) == n_kieu
    kiem = s.kiem_ghi(bo_qua={"Tổng quan"})
    assert kiem["day_du"] is True
    s.ghi_tong_quan("Tổng quan", T.TongQuan("Quét nền", ghi_chu=["ghi chú"]), kiem)
    tq = gia.o("Tổng quan")
    assert tq[0][0] == "Quét nền" and tq[2][0].startswith("Đã ghi đủ 1.200/1.200 dòng")
    assert any(isinstance(r[0], dict) and r[0]["text"] == "TikTok" and r[1] == 1200
               for r in tq)
    assert s.s["kiem"]["day_du"] is True
    s.sap_tab(["Tổng quan", "TikTok"])
    assert gia.tab_ten()[:2] == ["Tổng quan", "TikTok"]


def test_ten_nguoi_yeu_cau_tren_dong_sieu_du_lieu(gia, monkeypatch):
    """Dòng siêu dữ liệu ghi TÊN người hỏi (không bao giờ open_id)."""
    monkeypatch.setattr(T, "_ten_nguoi_yeu_cau", lambda: "Nguyễn Thị Lan")
    T.xuat("x", [T.Bang("Bài", [T.Cot("a")], [["1"]])], T.TongQuan("x", nguon="t"), luc=LUC)
    assert ["Người yêu cầu", "Nguyễn Thị Lan"] in [r[:2] for r in gia.o("Tổng quan")]
    assert "ou_" not in str(gia.o("Tổng quan"))
