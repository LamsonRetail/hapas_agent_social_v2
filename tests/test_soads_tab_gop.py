"""chi_so_ads 09/10/2026 (chủ agent chốt sau lần xuất thật 5.900 dòng): tab gộp do code cộng,
tab "Chi tiết" giữ đủ dòng + chế độ lọc theo từng tài khoản, "Dữ liệu gốc" gọn (chuỗi số
ghi thành số, mã giữ chữ), nhãn SỐ LIỆU CHÍNH chỉ gắn tiền tệ cho chỉ số tiền, `xem_truoc`.
Lark GIẢ (tests/sheet_gia), Meta giả."""
from __future__ import annotations

import collections
import json
from decimal import Decimal

import pytest

import apify_tool as A
import meta_ads_tool as T
import trinh_bay_sheet as TB
from sheet_gia import LarkGia
from test_trinh_bay_meta_ads import _gia, context  # noqa: F401 — fixture tự dùng

ACC = [{"id": "act_111111111111111111", "name": "HAPAS A", "currency": "VND", "timezone_name": "Asia/Ho_Chi_Minh"},
       {"id": "act_2", "name": "HAPAS B", "currency": "VND", "timezone_name": "Asia/Ho_Chi_Minh"},
       {"id": "act_3", "name": "HAPAS US", "currency": "USD", "timezone_name": "Asia/Ho_Chi_Minh"}]
NGAY = ["2026-10-01", "2026-10-02"]
NEN = ["facebook", "instagram"]


def _dong(acc, k):
    """2 chiến dịch × 2 ngày × 2 nền tảng mỗi TK; dòng cuối mỗi chiến dịch 2 toàn 0."""
    ra, i = [], 0
    so_tk = acc["id"].removeprefix("act_")
    for c in (1, 2):
        for d in NGAY:
            for n in NEN:
                i += 1
                zero = c == 2 and n == "instagram"
                spend = 0 if zero else (k * 1000 + i * 37) * (1 if acc["currency"] == "VND" else 0.01)
                ra.append({"account_id": so_tk, "account_name": acc["name"],
                           "campaign_id": f"12020000000000{k}{c:03d}", "campaign_name": f"{acc['name']} C{c}",
                           "date_start": d, "date_stop": d, "publisher_platform": n,
                           "spend": str(round(spend, 2)), "impressions": str(0 if zero else 100 * i + k),
                           "clicks": str(0 if zero else i + k), "reach": str(0 if zero else 50 * i),
                           "frequency": "0" if zero else "1.9"})
    return ra


ROWS = {a["id"] + "/insights": _dong(a, k) for k, a in enumerate(ACC, 1)}
CHI_SO = ["spend", "impressions", "reach", "clicks", "ctr", "cpc", "frequency"]


@pytest.fixture
def ba_tk(monkeypatch):
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: [dict(a) for a in ACC])
    calls = []

    def pages(self, tail, params, limit):
        calls.append(params)
        return [dict(r) for r in ROWS[tail]], False
    monkeypatch.setattr(T.MetaClient, "pages", pages)
    return calls


def run(**args):
    return json.loads(T._handle({"tai_khoan": "tat_ca", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-02",
                                 "cap": "chien_dich", "theo_ngay": True, "chia_theo": ["nen_tang"],
                                 "chi_so": CHI_SO, **args}))


def _bang(gia, tab):
    """-> (tiêu đề, dòng dữ liệu, dòng tổng) của một tab dữ liệu."""
    o = gia.o(tab)
    trong = next((i for i, r in enumerate(o) if not any(v not in ("", None) for v in r)), len(o))
    return o[0], o[1:trong], [r for r in o[trong + 1:] if any(v not in ("", None) for v in r)]


# ───────────── tab gộp ─────────────
def test_tab_gop_dung_thu_tu_va_dung_tong(monkeypatch, ba_tk):
    gia = _gia(monkeypatch)
    kq = run()
    assert "error" not in kq, kq
    assert ba_tk[0]["breakdowns"] == "publisher_platform" and ba_tk[0]["time_increment"] == 1
    # Dữ liệu gốc giữ tiếp cận/tần suất/chi tiêu đầy đủ số lẻ (Chi tiết làm tròn).
    assert gia.tab_ten() == ["Tổng quan", "Theo tài khoản", "Theo nền tảng", "Theo ngày", "Theo chiến dịch",
                             "Chi tiết", "Dữ liệu gốc"]
    assert kq["tab"] == gia.tab_ten()[1:]
    hd, ct, ct_tong = _bang(gia, "Chi tiết")
    assert len(ct) == 3 * 8, "Chi tiết giữ ĐỦ dòng, kể cả dòng toàn 0"
    assert kq["so_dong_toan_0"] == 3 * 2
    # Theo nền tảng: cộng riêng từng tiền tệ, CTR/CPC tính lại từ tổng (không trung bình).
    hn, nen, _ = _bang(gia, "Theo nền tảng")
    assert hn[:2] == ["Nền tảng", "Tiền tệ"]
    assert {(r[0], r[1]) for r in nen} == {(n, c) for n in NEN for c in ("VND", "USD")}
    goc = [r for rs in ROWS.values() for r in rs]
    for n in NEN:
        dong = [r for r in goc if r["publisher_platform"] == n and r["account_id"] in ("111111111111111111", "2")]
        spend = sum(Decimal(r["spend"]) for r in dong)
        imp = sum(int(r["impressions"]) for r in dong)
        clk = sum(int(r["clicks"]) for r in dong)
        r = next(r for r in nen if r[0] == n and r[1] == "VND")
        assert r[hn.index("Chi tiêu (tiền TK)")] == pytest.approx(float(spend))
        assert r[hn.index("Hiển thị (lượt)")] == imp
        assert r[hn.index("CTR (%)")] == pytest.approx(clk / imp * 100)
        assert r[hn.index("CPC (tiền TK/click)")] == pytest.approx(float(spend / clk))
        tb = sum(clk_ / imp_ * 100 for clk_, imp_ in ((int(x["clicks"]), int(x["impressions"])) for x in dong)
                 if imp_) / len([x for x in dong if int(x["impressions"])])
        assert r[hn.index("CTR (%)")] != pytest.approx(tb), "không lấy trung bình tỉ lệ"
    # Không bao giờ có tiếp cận / tần suất cộng dồn ở tab gộp.
    for tab in ("Theo tài khoản", "Theo nền tảng", "Theo ngày", "Theo chiến dịch"):
        h, rows, tong = _bang(gia, tab)
        assert not any(x.startswith(("Tiếp cận", "Tần suất")) for x in h), tab
        # Trong mỗi tiền tệ: Theo ngày sắp theo ngày tăng dần (dòng thời gian), tab khác theo
        # chi tiêu giảm dần; khối tiền tệ liền nhau.
        tt = [r[h.index("Tiền tệ")] for r in rows]
        assert tt == sorted(tt), tab
        for cur in ("VND", "USD"):
            if tab == "Theo ngày":
                ng = [r[0] for r in rows if r[h.index("Tiền tệ")] == cur]
                assert ng == sorted(ng) and len(ng) == 2, ng
                sp = [r[h.index("Chi tiêu (tiền TK)")] for r in rows if r[h.index("Tiền tệ")] == cur]
                assert sp != sorted(sp, reverse=True), "dữ liệu thử phải phân biệt hai cách sắp"
            else:
                sp = [r[h.index("Chi tiêu (tiền TK)")] for r in rows if r[h.index("Tiền tệ")] == cur]
                assert sp == sorted(sp, reverse=True), tab
        # Dòng tổng của tab gộp = dòng tổng của Chi tiết (từng tiền tệ, từng chỉ số).
        assert [r[0] for r in tong] == ["TỔNG USD", "TỔNG VND"]
        for r, rc in zip(tong, ct_tong):
            for ten in h[h.index("Tiền tệ"):]:
                assert r[h.index(ten)] == pytest.approx(rc[hd.index(ten)]) if isinstance(
                    rc[hd.index(ten)], float) else r[h.index(ten)] == rc[hd.index(ten)], (tab, ten)
    # Chi tiết: tổng tiếp cận để trống (không cộng người duy nhất).
    assert all(r[hd.index("Tiếp cận (người)")] == "" for r in ct_tong)
    tq = " ".join(str(r[0]) for r in gia.o("Tổng quan"))
    assert "Tiếp cận, tần suất và ROAS Meta không cộng được" in tq and "không cộng VND với USD" in tq
    assert "6/24 dòng ở tab Chi tiết toàn 0" in tq
    assert "Theo ngày sắp theo ngày tăng dần; các tab khác theo chi tiêu giảm dần" in tq
    # Mục lục liệt kê mọi tab gộp + Chi tiết; đọc lại kiểm đủ mọi tab.
    muc = [r[0]["text"] for r in gia.o("Tổng quan") if r and isinstance(r[0], dict)]
    assert muc == gia.tab_ten()[1:]
    kiem = [r[0] for r in gia.o("Tổng quan") if len(r) > 3 and str(r[3]).startswith("Đã ghi đủ")]
    assert set(gia.tab_ten()[1:]) <= set(kiem) and kq["day_du"] is True


def test_gop_thuan_khop_tong_va_khong_cong_hai_tien_te():
    acc_v, acc_u = {"id": "act_1", "name": "V"}, {"id": "act_2", "name": "U"}
    fetched = {"spend", "impressions", "clicks", "reach", "frequency"}
    rows = [{"account": a, "currency": cur, "data": d, "start": "2026-10-01",
             "values": T._values(d, fetched, True)}
            for a, cur, d in ((acc_v, "VND", {"spend": "100", "impressions": "10", "clicks": "1", "reach": "8",
                                              "publisher_platform": "facebook"}),
                              (acc_v, "VND", {"spend": "300", "impressions": "90", "clicks": "9", "reach": "70",
                                              "publisher_platform": "facebook"}),
                              (acc_u, "USD", {"spend": "5", "impressions": "50", "clicks": "5", "reach": "40",
                                              "publisher_platform": "facebook"}))]
    nhom = T._gop(rows, lambda r: (r["data"]["publisher_platform"],))
    assert [(g["currency"], g["khoa"]) for g in nhom] == [("USD", ("facebook",)), ("VND", ("facebook",))]
    v = nhom[1]["values"]
    assert v["spend"] == 400 and v["impressions"] == 100 and v["ctr"] == 10 and v["cpc"] == 40
    assert "reach" not in v and "frequency" not in v, "không bao giờ cộng tiếp cận"
    assert T._totals(nhom) == T._totals(rows)
    bang = T._bang_gop([("Theo nền tảng", [TB.Cot("Nền tảng")], nhom, "nền tảng")],
                       ["spend", "reach", "ctr", "frequency"], "TỔNG")[0]
    assert [c.ten for c in bang.cot] == ["Nền tảng", "Tiền tệ", "Chi tiêu (tiền TK)", "CTR (%)"]
    assert bang.ten_tab == "Theo nền tảng" and bang.gap_duoc is False


@pytest.mark.parametrize("cap,theo_ngay,chia,so_tk,mong", [
    ("account", False, [], 1, []),
    ("account", True, [], 1, ["Theo ngày"]),      # bị `_tinh_gop` bỏ: trùng Chi tiết
    ("account", False, [], 3, ["Theo tài khoản"]),
    ("campaign", False, [], 1, ["Theo tài khoản"]),
    ("campaign", True, [], 3, ["Theo tài khoản", "Theo ngày", "Theo chiến dịch"]),
    ("adset", False, [], 1, ["Theo tài khoản", "Theo chiến dịch"]),
    ("campaign", False, ["publisher_platform", "platform_position"], 2,
     ["Theo tài khoản", "Theo nền tảng", "Theo vị trí", "Theo chiến dịch"]),
])
def test_tab_gop_chi_khi_them_thong_tin(cap, theo_ngay, chia, so_tk, mong):
    assert [t for t, *_ in T._cac_gop(cap, chia, theo_ngay, so_tk)] == mong


def test_tab_gop_trung_chi_tiet_thi_bo():
    a = {"id": "act_1", "name": "A"}
    rows = [{"account": a, "currency": "VND", "start": d, "data": {"date_start": d},
             "values": T._values({"spend": "1", "impressions": "1"}, None)} for d in NGAY]
    # 1 TK cấp tài khoản theo ngày: "Theo ngày" trùng hệt Chi tiết → không thêm tab.
    assert T._tinh_gop(rows, "account", [], True, 1) == []


# ───────────── chế độ lọc theo tài khoản ─────────────
def test_che_do_loc_moi_tai_khoan(monkeypatch, ba_tk):
    gia = _gia(monkeypatch)
    kq = run()
    views = gia.che_do_loc("Chi tiết")
    assert [v["name"] for v in views] == ["HAPAS A", "HAPAS B", "HAPAS US"]
    sid = gia.tab("Chi tiết")["sheet_id"]
    hd, ct, _ = _bang(gia, "Chi tiết")
    vung = f"{sid}!A1:{A._cot(len(hd))}{1 + len(ct)}"
    for v in views:
        assert v["range"] == vung
    # Khoá theo cột Mã TK (B), tên lấy cột Tài khoản.
    ma = {"HAPAS A": "act_111111111111111111", "HAPAS B": "act_2", "HAPAS US": "act_3"}
    for v in views:
        assert v["conditions"] == [{"condition_id": "B", "filter_type": "multiValue",
                                    "expected": [ma[v["name"]]]}]
    assert all(not gia.che_do_loc(t) for t in gia.tab_ten() if t not in ("Chi tiết",) and t != "Tổng quan")
    assert kq["che_do_loc"] == 3
    tq = " ".join(str(r[0]) for r in gia.o("Tổng quan"))
    assert "Tab Chi tiết có sẵn 3 chế độ lọc (filter view) theo cột Tài khoản" in tq
    # Chế độ lọc tạo SAU khi đã ghi dữ liệu Chi tiết, TRƯỚC khi cấp quyền xem.
    i_view = min(i for i, g in enumerate(gia.goi) if "/filter_views" in g[1])
    i_ghi = max(i for i, g in enumerate(gia.goi) if g[1].endswith("/values_batch_update")
                and f"{sid}!" in json.dumps(g[3]))
    i_quyen = next(i for i, g in enumerate(gia.goi) if g[1].endswith("/members"))
    assert i_ghi < i_view < i_quyen


def test_che_do_loc_hong_chi_canh_bao(monkeypatch, ba_tk):
    gia = _gia(monkeypatch, hong={"/filter_views"})
    kq = run()
    assert kq["link"] and kq["day_du"] is True and kq["che_do_loc"] == 0
    assert "chế độ lọc" in kq["canh_bao_trinh_bay"]
    assert len(_bang(gia, "Chi tiết")[1]) == 24
    # Hỏng ở lần đầu thì DỪNG, không gọi tiếp cho từng tài khoản.
    assert len([g for g in gia.goi if "/filter_views" in g[1]]) == 1
    tq = " ".join(str(r[0]) for r in gia.o("Tổng quan"))
    assert "chưa tạo được chế độ lọc dựng sẵn theo Tài khoản" in tq


def test_dieu_kien_hong_thi_xoa_che_do_loc_vua_tao(monkeypatch, ba_tk):
    gia = _gia(monkeypatch, hong={"/conditions"})
    kq = run()
    assert kq["day_du"] is True and gia.che_do_loc("Chi tiết") == []
    assert any(g[0] == "DELETE" and "/filter_views/" in g[1] for g in gia.goi)


def test_che_do_loc_co_tran(monkeypatch, ba_tk):
    monkeypatch.setattr(TB, "TRAN_LOC_SAN", 2)
    gia = _gia(monkeypatch)
    kq = run()
    assert len(gia.che_do_loc("Chi tiết")) == 2 and kq["che_do_loc"] == 2
    tq = " ".join(str(r[0]) for r in gia.o("Tổng quan"))
    assert "Chỉ dựng 2/3 tài khoản nhiều dòng nhất (trần 2)" in tq


def test_che_do_loc_mot_tai_khoan_khong_tao(monkeypatch):
    gia = _gia(monkeypatch)
    kq = json.loads(T._handle({"tai_khoan": "HAPAS VN", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-07",
                               "cap": "chien_dich", "chi_so": ["spend"]}))
    assert kq["link"] and "che_do_loc" not in kq
    assert not any("/filter_views" in g[1] for g in gia.goi)


def test_loc_san_chung_cho_moi_tool(monkeypatch):
    """`Bang.loc_san` là của lớp trình bày, không riêng chi_so_ads: tên trùng/dài được sửa."""
    gia = LarkGia()
    monkeypatch.setattr(A.lark, "call", gia.call)
    monkeypatch.setattr(TB, "_LOC_LUOT", collections.deque())
    dai = "x" * 120
    b = TB.Bang("Bài", [TB.Cot("Kênh"), TB.Cot("Lượt", "so_nguyen")],
                [["tiktok", 1], ["tiktok", 2], ["a/b", 3], [dai, 4], ["", 5]], loc_san="Kênh")
    kq = TB.xuat("t", [b])
    v = gia.che_do_loc("Dữ liệu")
    assert [x["name"] for x in v] == ["tiktok", "a b", "x" * 100]
    assert [x["conditions"][0]["expected"] for x in v] == [["tiktok"], ["a/b"], [dai]]
    assert kq.cho_tool()["che_do_loc"] == 3


# ───────────── Dữ liệu gốc gọn ─────────────
def test_du_lieu_goc_gon_so_la_so_ma_la_chu(monkeypatch, ba_tk):
    gia = _gia(monkeypatch)
    run(chi_so=["spend", "ctr"])
    goc = gia.o("Dữ liệu gốc")
    assert goc[0] == ["account_id", "campaign_id", "campaign_name", "date_start", "date_stop",
                      "publisher_platform", "spend", "impressions", "clicks", "reach", "frequency"]
    r = goc[1]
    # Mã 18 chữ số giữ CHỮ (không mất chữ số), định dạng "@".
    assert r[0] == "111111111111111111" and isinstance(r[1], str)
    sid = gia.tab("Dữ liệu gốc")["sheet_id"]
    fmt = [s["formatter"] for s in gia.kieu_o("Dữ liệu gốc", 1, 2) if "formatter" in s]
    assert fmt and fmt[-1] == "@", sid
    # Chuỗi số của Meta ghi thành số (không "số lưu dạng chữ").
    assert r[7] == 101 and isinstance(r[7], int) and isinstance(r[8], int) and r[10] == 1.9
    assert r[6] == 1037 and isinstance(r[6], int)
    assert "account_name" not in goc[0], "Chi tiết đã có nguyên giá trị"


def test_du_lieu_goc_giu_actions_json(monkeypatch):
    gia = _gia(monkeypatch)
    kq = json.loads(T._handle({"tai_khoan": "tat_ca", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-07",
                               "cap": "chien_dich", "chi_so": ["purchases", "revenue"]}))
    goc = gia.o("Dữ liệu gốc")
    assert "actions" in goc[0] and "spend" in goc[0] and "impressions" in goc[0]
    assert json.loads(goc[1][goc[0].index("actions")]) == [{"action_type": "purchase", "value": "3"}]
    assert goc[1][goc[0].index("spend")] == 100000 and goc[3][goc[0].index("spend")] == 20.5
    assert "action_type" not in json.dumps(kq, ensure_ascii=False)


def test_du_lieu_goc_khong_con_truong_rieng_thi_bo_tab(monkeypatch):
    gia = _gia(monkeypatch)
    import test_trinh_bay_meta_ads as M
    # Chỉ còn trường số nguyên Chi tiết hiện nguyên (hiển thị, click) → không cần tab gốc.
    monkeypatch.setattr(T.MetaClient, "pages", lambda self, tail, params, limit: (
        [{k: v for k, v in r.items() if k not in ("actions", "spend")} for r in M.INSIGHTS[tail]], False))
    kq = json.loads(T._handle({"tai_khoan": "tat_ca", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-07",
                               "cap": "chien_dich", "chi_so": ["impressions", "clicks"]}))
    assert "Dữ liệu gốc" not in gia.tab_ten() and "Dữ liệu gốc" not in kq["tab"]


@pytest.mark.parametrize("vao,ra", [
    ("100000", 100000), ("12.5", 12.5), ("-3", -3), ("0", 0), ("0.25", 0.25),
    ("0123", "0123"), ("+5", "+5"), ("1e5", "1e5"), (" 5", " 5"), ("12,5", "12,5"),
    ("123456789012345678", "123456789012345678"), ("1234567890123456", "1234567890123456"),
    ("123456789012345", 123456789012345), ("", ""), ("abc", "abc"), (7, 7)])
def test_so_tu_chuoi(vao, ra):
    kq = TB.so_tu_chuoi(vao)
    assert kq == ra and type(kq) is type(ra)


def test_bang_goc_chung_doi_so_tru_cot_ma():
    b = TB.bang_goc([{"id": "9", "post_id": "123", "luot": "12", "phone": "0987", "gia": "1.25",
                      "ten": "abc", "tags": ["a"]}])
    hang = dict(zip([c.ten for c in b.cot], b.dong[0]))
    assert hang == {"id": "9", "post_id": "123", "luot": 12, "phone": "0987", "gia": 1.25, "ten": "abc",
                    "tags": '["a"]'}
    assert {c.ten: c.kieu for c in b.cot}["post_id"] == "ma"


# ───────────── nhãn SỐ LIỆU CHÍNH ─────────────
def _so_lieu(gia):
    o = gia.o("Tổng quan")
    i = next(i for i, r in enumerate(o) if r and r[0] == "SỐ LIỆU CHÍNH")
    ra = []
    for r in o[i + 2:]:
        if not r or not r[0]:
            break
        ra.append(r[0])
    return ra


def test_nhan_tien_te_chi_o_chi_so_tien(monkeypatch):
    gia = _gia(monkeypatch)
    json.loads(T._handle({"tai_khoan": "HAPAS VN", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-07",
                          "cap": "chien_dich", "chi_so": ["spend", "impressions", "clicks", "ctr", "cpc", "cpm"]}))
    assert _so_lieu(gia) == ["Chi tiêu — VND", "Hiển thị", "Click", "CTR", "CPC — VND", "CPM — VND"]


def test_nhieu_tien_te_moi_tien_te_mot_khoi(monkeypatch):
    gia = _gia(monkeypatch)
    json.loads(T._handle({"tai_khoan": "tat_ca", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-07",
                          "cap": "chien_dich", "chi_so": ["spend", "impressions"]}))
    assert _so_lieu(gia) == ["Tài khoản tiền USD", "Chi tiêu — USD", "Hiển thị",
                             "Tài khoản tiền VND", "Chi tiêu — VND", "Hiển thị"]
    assert not any("Hiển thị — " in str(r[0]) for r in gia.o("Tổng quan"))


# ───────────── xem_truoc ─────────────
def test_xem_truoc_khong_tao_sheet_khong_goi_lark(monkeypatch):
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: [dict(a) for a in ACC[:2]])
    ten_nen = ["facebook", "instagram", "messenger"]

    def pages(self, tail, params, limit):
        assert params["time_increment"] == 1 and params["breakdowns"] == "publisher_platform"
        ra = []
        for c in range(100):
            for d in range(7):
                for n in ten_nen:
                    z = n == "messenger"
                    ra.append({"campaign_id": f"{tail[:6]}{c}", "campaign_name": f"C{c}",
                               "date_start": f"2026-10-0{d + 1}", "publisher_platform": n,
                               "spend": "0" if z else "10", "impressions": "0" if z else "100"})
        return ra, False
    monkeypatch.setattr(T.MetaClient, "pages", pages)

    def cam(*a, **k):
        raise AssertionError("xem_truoc không được gọi Lark / tạo Sheet")
    monkeypatch.setattr(T.lark, "call", cam)
    monkeypatch.setattr(A.lark, "call", cam)
    monkeypatch.setattr(TB, "xuat", cam)
    monkeypatch.setattr(T, "_private_sheet", cam)
    monkeypatch.setattr(T.lsr_platform, "danh_dau_han_che", cam)
    kq = json.loads(T._handle({"tai_khoan": "tat_ca", "khoang_ngay": "7_ngay", "cap": "chien_dich",
                               "theo_ngay": True, "chia_theo": ["nen_tang"], "chi_so": ["spend"],
                               "xem_truoc": True}))
    assert "error" not in kq and "link" not in kq
    assert kq["so_dong"] == 4200 and kq["so_dong_toan_0"] == 1400
    assert kq["kich_thuoc"] == {"tai_khoan": 2, "chien_dich": 200, "ngay": 7, "nen_tang": 3}
    assert kq["cong_thuc"] == "2 tài khoản: 200 chiến dịch × 7 ngày × 3 nền tảng"
    assert [t["tab"] for t in kq["tab_se_co"]] == ["Theo tài khoản", "Theo nền tảng", "Theo ngày",
                                                   "Theo chiến dịch", "Chi tiết"]
    assert kq["tab_se_co"][-1]["so_dong"] == 4200 and kq["tab_se_co"][3]["so_dong"] == 200
    assert {g["bo"]: g["so_dong_uoc"] for g in kq["phuong_an_gon"]} == {"theo_ngay": 600, "chia_theo": 1400}
    assert "CHƯA xuất" in kq["hoi_tiep"] and "4200 dòng" in kq["hoi_tiep"]
    assert "chế độ lọc theo từng tài khoản" in kq["hoi_tiep"]
    assert "Chi tiêu" not in json.dumps(kq, ensure_ascii=False), "xem trước không trả số chỉ số"


def test_xem_truoc_it_dong_bao_xuat_luon(monkeypatch, ba_tk):
    monkeypatch.setattr(T, "_private_sheet", lambda *a, **k: pytest.fail("không tạo Sheet"))
    kq = run(xem_truoc=True)
    assert kq["so_dong"] == 24 and "bỏ xem_truoc" in kq["hoi_tiep"] and "CHƯA" not in kq["hoi_tiep"]


def test_xem_truoc_phai_la_bool(monkeypatch, ba_tk):
    assert "xem_truoc phải là true/false" in run(xem_truoc="yes")["error"]


def test_xem_truoc_cap_quang_cao_khong_nhan_cap_chua():
    a = {"id": "act_1", "name": "A"}
    rows = [{"account": a, "currency": "VND", "start": d,
             "data": {"campaign_id": f"c{c}", "ad_id": f"c{c}a{q}", "date_start": d},
             "values": T._values({"spend": "1", "impressions": "1"}, None)}
            for c in range(2) for q in range(3) for d in NGAY]
    kq = T._xem_truoc(rows, "ad", [], True, ["spend"], False, "x", 1)
    assert kq["kich_thuoc"] == {"tai_khoan": 1, "chien_dich": 2, "quang_cao": 6, "ngay": 2}
    assert kq["cong_thuc"] == "1 tài khoản, 2 chiến dịch: 6 quảng cáo × 2 ngày"
    assert [t["tab"] for t in kq["tab_se_co"]] == ["Theo tài khoản", "Theo ngày", "Theo chiến dịch", "Chi tiết"]



# ───────────── Sheet mẫu từ số giả (xuat_mau) ─────────────
def test_xuat_mau_cung_duong_that_khong_meta_khong_quyen(monkeypatch):
    """`xuat_mau`: số giả → đúng bảng/tab gộp/TB.xuat của bản thật, khoá riêng tư trước khi
    ghi, `cap_quyen` của bên gọi chạy sau cùng; không gọi Meta, không qua _handle/_actor/_allowed."""
    gia = _gia(monkeypatch)

    def cam(*a, **k):
        raise AssertionError("xuat_mau không được gọi Meta / kiểm người hỏi")
    monkeypatch.setattr(T, "_handle", cam)
    monkeypatch.setattr(T, "_actor", cam)
    monkeypatch.setattr(T, "_allowed", cam)
    monkeypatch.setattr(T, "_grant_view", cam)
    monkeypatch.setattr(T.MetaClient, "accounts", cam)
    monkeypatch.setattr(T.MetaClient, "pages", cam)
    monkeypatch.setattr(T.lsr_platform, "danh_dau_han_che", cam)
    cap = []
    dong = [r for rs in ROWS.values() for r in rs]
    kq = T.xuat_mau(dong, {"cap": "chien_dich", "theo_ngay": True, "chia_theo": ["nen_tang"],
                           "chi_so": CHI_SO, "tu_ngay": "2026-10-01", "den_ngay": "2026-10-02"},
                    cap_quyen=lambda tok: cap.append((tok, len(gia.goi))), tai_khoan=[dict(a) for a in ACC])
    assert kq.url and kq.day_du is True
    assert gia.tab_ten() == ["Tổng quan", "Theo tài khoản", "Theo nền tảng", "Theo ngày", "Theo chiến dịch",
                             "Chi tiết", "Dữ liệu gốc"]
    assert gia.dau.title.startswith("MẪU (số giả) Số ads HAPAS 2026-10-01–2026-10-02")
    assert len(_bang(gia, "Chi tiết")[1]) == 24 and len(gia.che_do_loc("Chi tiết")) == 3
    tq = " ".join(str(r[0]) for r in gia.o("Tổng quan"))
    assert "SHEET MẪU: mọi số là số GIẢ" in tq
    # Thứ tự riêng tư y như bản thật: khoá + kiểm khoá → ghi → cap_quyen sau mọi lần ghi.
    i_patch = next(i for i, g in enumerate(gia.goi) if g[0] == "PATCH" and "/permissions/" in g[1])
    i_get = next(i for i, g in enumerate(gia.goi) if g[0] == "GET" and "/permissions/" in g[1])
    ghi = [i for i, g in enumerate(gia.goi) if g[1].endswith("/values_batch_update")]
    assert i_patch < i_get < ghi[0] and len(cap) == 1 and cap[0][1] > ghi[-1]
    assert cap[0][0] == kq.token


def test_xuat_mau_suy_tai_khoan_va_khoa_hong_thi_khong_ghi(monkeypatch):
    gia = LarkGia()

    def call(method, path, query=None, body=None):
        if path.endswith("/public"):
            return {"data": {"permission_public": {"link_share_entity": "anyone"}}}
        return gia.call(method, path, query=query, body=body)
    monkeypatch.setattr(T.lark, "call", call)
    monkeypatch.setattr(A.lark, "call", call)
    dong = [{"account_id": "9", "account_name": "Mẫu", "campaign_id": "1", "campaign_name": "C",
             "date_start": "2026-10-01", "date_stop": "2026-10-01", "spend": "5", "impressions": "50"}]
    with pytest.raises(ValueError, match="riêng tư"):
        T.xuat_mau(dong, {"cap": "chien_dich", "chi_so": ["spend"], "tu_ngay": "2026-10-01",
                          "den_ngay": "2026-10-01"}, cap_quyen=lambda tok: pytest.fail("không cấp"))
    assert not [g for g in gia.goi if g[1].endswith("/values_batch_update")]
    with pytest.raises(ValueError, match="cap_quyen"):
        T.xuat_mau(dong, {}, cap_quyen=None)



# ───────────── review 09/10/2026 ─────────────
@pytest.mark.parametrize("vao", ["1.10", "2.50", "0.10", "-0", "-0.0", "NaN", "nan", "inf",
                                 "-inf", "1e5", "12,5", "007", "+5", " 5"])
def test_so_tu_chuoi_khong_doi_gia_tri(vao):
    """Chỉ đổi khi số viết lại đúng y chuỗi: "1.10"/"2.50"/"-0" giữ chữ."""
    assert TB.so_tu_chuoi(vao) == vao


@pytest.mark.parametrize("ten,ma", [
    ("barcode", True), ("ean", True), ("ean13", True), ("gtin", True), ("upc", True), ("sku", True),
    ("product_sku", True), ("variantSku", True), ("zip", True), ("zipcode", True), ("postcode", True),
    ("postal_code", True), ("phone", True), ("Phone", True), ("telephone", True), ("sdt", True),
    ("so_dien_thoai", True), ("tel", True), ("mobile", True), ("shortCode", True), ("SHORTCODE", True),
    ("spend", False), ("impressions", False), ("mean_score", False), ("hotel_name", False),
    ("frequency", False), ("actions", False), ("publisher_platform", False)])
def test_cot_ma_rong(ten, ma):
    assert TB.la_cot_ma(ten) is ma


def test_bang_goc_cot_ma_giu_chu():
    b = TB.bang_goc([{"barcode": "8935049501503", "phone": "84912345678", "sku": "1.10",
                      "gia": "1.10", "luot": "8935049501503", "tel": "0912"}])
    hang = dict(zip([c.ten for c in b.cot], b.dong[0]))
    assert hang == {"barcode": "8935049501503", "phone": "84912345678", "sku": "1.10", "gia": "1.10",
                    "luot": 8935049501503, "tel": "0912"}
    assert {c.ten: c.kieu for c in b.cot} == {"barcode": "ma", "phone": "ma", "sku": "ma", "gia": "chu",
                                              "luot": "chu", "tel": "ma"}


def test_che_do_loc_tai_khoan_trung_ten_va_khong_ten(monkeypatch):
    acc = [{"id": "act_11", "name": "HAPAS", "currency": "VND", "timezone_name": "Asia/Ho_Chi_Minh"},
           {"id": "act_12", "name": "HAPAS", "currency": "VND", "timezone_name": "Asia/Ho_Chi_Minh"},
           {"id": "act_13", "currency": "VND", "timezone_name": "Asia/Ho_Chi_Minh"},
           {"id": "act_14", "name": "Khác", "currency": "VND", "timezone_name": "Asia/Ho_Chi_Minh"}]
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: [dict(a) for a in acc])
    monkeypatch.setattr(T.MetaClient, "pages", lambda self, tail, params, limit: (
        [{"campaign_id": "1", "campaign_name": "C", "spend": "1", "impressions": "1"}], False))
    gia = _gia(monkeypatch)
    json.loads(T._handle({"tai_khoan": "tat_ca", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-07",
                          "cap": "chien_dich", "chi_so": ["spend"]}))
    v = {x["name"]: x["conditions"][0]["expected"] for x in gia.che_do_loc("Chi tiết")}
    assert v == {"HAPAS — act_11": ["act_11"], "HAPAS — act_12": ["act_12"], "act_13": ["act_13"],
                 "Khác": ["act_14"]}


def test_toan_0_chi_khi_chi_tieu_va_hien_thi_dung_bang_0():
    f = {"spend", "impressions", "clicks"}
    w = ["spend", "impressions", "clicks", "ctr"]
    dong = lambda d: {"values": T._values(d, f)}  # noqa: E731
    assert T._toan_0(dong({"spend": "0", "impressions": "0", "clicks": "0"}), w)
    assert not T._toan_0(dong({"spend": "0"}), w), "hiển thị không rõ ≠ 0"
    assert not T._toan_0(dong({"impressions": "0"}), w), "chi tiêu không rõ ≠ 0"
    assert not T._toan_0(dong({}), w)
    assert not T._toan_0(dong({"spend": "0", "impressions": "0", "clicks": "2"}), w)


def test_du_lieu_goc_giu_so_le_chi_tiet_lam_tron(monkeypatch):
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: [dict(ACC[0])])
    monkeypatch.setattr(T.MetaClient, "pages", lambda self, tail, params, limit: (
        [{"campaign_id": "1", "campaign_name": "C", "spend": "12.12345678", "impressions": "100",
          "clicks": "3", "reach": "77", "frequency": "1.298701298701"}], False))
    gia = _gia(monkeypatch)
    json.loads(T._handle({"tai_khoan": "tat_ca", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-07",
                          "cap": "chien_dich", "chi_so": ["spend", "impressions", "clicks", "reach",
                                                          "frequency"]}))
    goc = gia.o("Dữ liệu gốc")
    hang = dict(zip(goc[0], goc[1]))
    assert hang["frequency"] == 1.298701298701 and hang["spend"] == 12.12345678 and hang["reach"] == 77
    assert "impressions" not in hang and "clicks" not in hang, "số nguyên Chi tiết đã hiện nguyên"
    hd = gia.o("Chi tiết")[0]
    assert gia.o("Chi tiết")[1][hd.index("Tần suất (lần/người)")] == 1.298701


def test_gop_chuyen_doi_trong_khi_chia_nho_khop_chi_tiet(monkeypatch):
    """Mua/giá trị/ROAS ở tab gộp khớp Chi tiết; dòng chia nhỏ Meta ẩn chuyển đổi → nhóm chứa
    nó để trống (không giả 0), tổng để trống như Chi tiết."""
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: [dict(a) for a in ACC[:2]])
    buy = lambda n, v: {"actions": [{"action_type": "purchase", "value": str(n)}],  # noqa: E731
                        "action_values": [{"action_type": "purchase", "value": str(v)}]}
    data = {
        ACC[0]["id"] + "/insights": [
            {"campaign_id": "1", "campaign_name": "A1", "date_start": "2026-10-01", "publisher_platform": "facebook",
             "spend": "100", "impressions": "10", **buy(2, 500)},
            {"campaign_id": "1", "campaign_name": "A1", "date_start": "2026-10-01", "publisher_platform": "instagram",
             "spend": "50", "impressions": "5"}],                     # chuyển đổi bị ẩn
        ACC[1]["id"] + "/insights": [
            {"campaign_id": "2", "campaign_name": "B1", "date_start": "2026-10-01", "publisher_platform": "facebook",
             "spend": "300", "impressions": "30", **buy(1, 900)}]}
    monkeypatch.setattr(T.MetaClient, "pages", lambda self, tail, params, limit: (
        [dict(r) for r in data[tail]], False))
    gia = _gia(monkeypatch)
    kq = json.loads(T._handle({"tai_khoan": "tat_ca", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-01",
                               "cap": "chien_dich", "chia_theo": ["nen_tang"],
                               "chi_so": ["spend", "purchases", "revenue", "roas"]}))
    assert "error" not in kq
    hd, ct, ct_tong = _bang(gia, "Chi tiết")
    c = {k: hd.index(k) for k in ("Mua hàng (lượt)", "Giá trị mua (tiền TK)", "ROAS tính (lần)")}
    assert all(ct_tong[0][j] == "" for j in c.values()), "Chi tiết: tổng chuyển đổi trống"
    h, nen, tong = _bang(gia, "Theo nền tảng")
    fb = next(r for r in nen if r[0] == "facebook")
    ig = next(r for r in nen if r[0] == "instagram")
    assert fb[h.index("Mua hàng (lượt)")] == 3 and fb[h.index("Giá trị mua (tiền TK)")] == 1400
    assert fb[h.index("ROAS tính (lần)")] == pytest.approx(1400 / 400)
    assert all(ig[h.index(k)] == "" for k in c), "nhóm có dòng bị ẩn: trống, không 0"
    for k, j in c.items():
        assert tong[0][h.index(k)] == ct_tong[0][j], k
    h2, tk, tong2 = _bang(gia, "Theo tài khoản")
    b = next(r for r in tk if r[0] == "HAPAS B")
    assert b[h2.index("Mua hàng (lượt)")] == 1 and b[h2.index("ROAS tính (lần)")] == 3
    assert next(r for r in tk if r[0] == "HAPAS A")[h2.index("Mua hàng (lượt)")] == ""
    for k, j in c.items():
        assert tong2[0][h2.index(k)] == ct_tong[0][j], k


_KHOA_XEM_TRUOC = {"xem_truoc", "so_dong", "bi_cat", "khoang", "kich_thuoc", "cong_thuc", "so_dong_toan_0",
                   "tab_se_co", "phuong_an_gon", "hoi_tiep"}


def test_xem_truoc_chi_tra_khoa_cho_phep(monkeypatch, ba_tk):
    kq = run(xem_truoc=True, chi_so=["spend", "purchases", "revenue"])
    assert set(kq) <= _KHOA_XEM_TRUOC, set(kq) - _KHOA_XEM_TRUOC
    assert {k for t in kq["tab_se_co"] for k in t} <= {"tab", "so_dong"}
    assert {k for g in kq["phuong_an_gon"] for k in g} <= {"bo", "so_dong_uoc"}
    assert all(isinstance(v, int) for v in kq["kich_thuoc"].values())


def test_xem_truoc_van_kiem_quyen(monkeypatch, ba_tk):
    monkeypatch.setattr(T, "_allowed", lambda actor: False)
    kq = run(xem_truoc=True)
    assert "error" in kq and "chưa được phép" in kq["error"] and not ba_tk


def test_xem_truoc_tu_choi_trong_nhom(monkeypatch, ba_tk):
    import scheduler
    scheduler.set_current_chat_type("group")
    T.set_context({"channel": "lark", "chat_type": "group", "nguoi_gui": "ou_asker"})
    kq = run(xem_truoc=True)
    assert "error" in kq and "không trả trong nhóm" in kq["error"] and not ba_tk
