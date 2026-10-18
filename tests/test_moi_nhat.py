"""Trang "mới nhất" của tìm theo từ khoá TikTok (17/10/2026).

Chủ dự án 17/10: "thêm trang: mới nhất vào lượt tìm tiktok hằng ngày". Đo thật: feed sắp mới nhất
(sortType 3) bắt 50/497 bài brand 30 ngày mà liên quan + nhiều thích + feed hashtag đều sót.
Dữ liệu giả LÀM SẠCH, không tên/chữ thật; không bài nào gọi Apify/Postgres/model thật.
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from test_phu_song import GiaApiCoActor
from test_theo_doi import DU_AN, GiaKhoTk, GiaViec, _chay_tk, _tt_tim, mo  # noqa: F401
from test_tiktok_api import _aweme

import apify_tool as A
import kiem_do_phu as KDP
import theo_doi as T
import theo_doi_api as TDA
import tiktok_api as TT
from dashboard import chi_phi as CP

_VN = datetime.timezone(datetime.timedelta(hours=7))
G = TT.GIA_YEU_CAU
BAY = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=_VN)


def _trang(ids_ngay: list[tuple[int, float]], more=1, cursor=30) -> dict:
    """Một trang tìm kiểu scraptik: [(id, số ngày trước)] theo thứ tự đưa vào."""
    return {"status_code": 0, "has_more": more, "cursor": cursor,
            "search_item_list": [{"aweme_info": _aweme(i, ngay=n)} for i, n in ids_ngay]}


# ───────────────────────────── tiktok_api.tim_moi_nhat ─────────────────────────────
def _goi_gia(monkeypatch, theo_trang: dict, loi: dict | None = None):
    """Giả `TT._goi`: (từ khoá, offset) -> trang; `loi` (từ khoá, offset) -> LoiApify."""
    goi = []

    def f(payload, ngan):
        if not ngan.xin():
            return None
        goi.append(dict(payload))
        k = (payload["searchPosts_keyword"], payload["searchPosts_offset"])
        if loi and k in loi:
            raise loi[k]
        return theo_trang.get(k, _trang([], more=0))
    monkeypatch.setattr(TT, "_goi", f)
    return goi


def test_tim_moi_nhat_gui_sap_moi_nhat_va_dung_khi_cham_moc(monkeypatch):
    """Lật tới khi trang chạm bài cũ hơn mốc của TỪNG từ; gửi sortType 3 + bộ lọc 30 ngày."""
    now = datetime.datetime.now(_VN)
    goi = _goi_gia(monkeypatch, {
        ("a", 0): _trang([(i, 0.1) for i in range(1, 31)]),             # cả trang mới hơn mốc
        ("a", 30): _trang([(i, 0.5) for i in range(31, 46)] + [(46, 3)], cursor=60),
        ("a", 60): _trang([(99, 4)]),
        ("b", 0): _trang([(200, 0.2), (201, 5)]),                       # chạm mốc ngay trang 1
    })
    kq = TT.tim_moi_nhat([("a", now - datetime.timedelta(days=2)),
                          ("b", now - datetime.timedelta(days=2))], 3, TT.Ngan(1.0))
    assert {(g["searchPosts_sortType"], g["searchPosts_publishTime"]) for g in goi} == {(3, 30)}
    assert kq["a"]["trang"] == 2 and len(kq["a"]["bai"]) == 46 and kq["a"]["moi_hon_moc"] == 45
    assert kq["b"]["trang"] == 1 and kq["b"]["moi_hon_moc"] == 1 and not kq["b"]["loi"]


def test_tim_moi_nhat_tran_trang_moc_none_va_loi(monkeypatch):
    now = datetime.datetime.now(_VN)
    full = {(k, off): _trang([(hash((k, off, i)) % 10 ** 9, 0.01) for i in range(30)],
                             cursor=off + 30)
            for k in ("a", "c") for off in (0, 30, 60, 90)}
    loi = {("c", 30): A.LoiApify("LOI", "giả lỗi trang 2")}
    goi = _goi_gia(monkeypatch, full, loi)
    kq = TT.tim_moi_nhat([("a", now - datetime.timedelta(days=9)), ("x", None),
                          ("c", now - datetime.timedelta(days=9))], 2, TT.Ngan(1.0))
    assert kq["a"]["trang"] == 2, "không lật quá trần trang"
    assert kq["x"]["trang"] == 1, "không có mốc: chỉ trang đầu"
    # Trang 2 lỗi: giữ 30 bài trang 1 (đã trả tiền), ghi lỗi.
    assert len(kq["c"]["bai"]) == 30 and "giả lỗi" in kq["c"]["loi"]
    assert len(goi) == 5


def test_tim_moi_nhat_het_tien_khoa_bo_dem(monkeypatch):
    now = datetime.datetime.now(_VN)
    _goi_gia(monkeypatch, {("b", 0): _trang([(5, 0.1)])},
             {("a", 0): A.LoiApify("HET_TIEN_THANG", "hết hạn mức")})
    monkeypatch.setattr(TT, "_SONG_SONG", 1)
    ngan = TT.Ngan(1.0)
    kq = TT.tim_moi_nhat([("a", now), ("b", now)], 1, ngan)
    assert ngan.dung == "HET_TIEN_THANG" and kq["b"]["trang"] == 0 and kq["b"]["bai"] == []


# ───────────────────────────── theo_doi_api: chọn từ, trần, mốc ─────────────────────────────
def test_chon_tu_moi_moc_tung_tu_va_tu_yen_nghi():
    moc = {"luc": "2026-10-16T08:00:00+07:00", "tu": {
        "hapas": {"luc": "2026-10-16T08:00:00+07:00", "yen": 0},
        "vi hapas": {"luc": "2026-10-15T08:00:00+07:00", "yen": 3},       # yên, mới 49 giờ
        "tui hapas": {"luc": "2026-10-14T06:00:00+07:00", "yen": 5},      # yên, đã 75 giờ
        "rac": {"luc": "2026-08-01T00:00:00+07:00", "yen": 0}}}
    chay, nghi = TDA.chon_tu_moi(["hapas", "Túi Hapas", "ví hapas", "rác", "mới"], moc, BAY)
    m = dict(chay)
    assert nghi == ["ví hapas"]
    assert m["hapas"] == datetime.datetime(2026, 10, 15, 8, 0, tzinfo=_VN)    # lùi 24 giờ
    assert m["Túi Hapas"] == datetime.datetime(2026, 10, 13, 6, 0, tzinfo=_VN)
    assert m["rác"] == BAY - datetime.timedelta(days=30), "kẹp 30 ngày"
    assert m["mới"] == BAY - datetime.timedelta(days=TDA.MOI_NGAY_LAN_DAU)


def test_den_luot_moi_theo_nhip():
    assert TDA.den_luot_moi(None, BAY)[0]
    assert not TDA.den_luot_moi({"luc": "2026-10-17T01:00:00+07:00"}, BAY)[0]
    assert TDA.den_luot_moi({"luc": "2026-10-16T12:00:00+07:00"}, BAY)[0]
    assert TDA.den_luot_moi({"luc": "rác"}, BAY)[0]


def test_tran_moi_san_mot_trang_tran_ba_trang_va_kep_phan_con():
    uoc = T.uoc_tu_khoa_nen_tang("tiktok", 300, ["k"] * 21)      # 4 trang/từ + 10 làm mới
    # Lượt thường 1 trang/từ, lượt nổi tới hạn (chừa 2 trang/từ): phần ước tính chưa dùng
    # = 0,2444 − 21 − 10 − 42 yêu cầu = 0,0984 USD (≈ 49 yêu cầu × 0,002) — giữa sàn 21 và trần 63.
    assert TDA.tran_moi(21, uoc, 21 * G, 5.0, du_noi=42 * G) == pytest.approx(0.0984)
    assert TDA.tran_moi(21, uoc, 21 * G, 5.0, du_noi=0.0) == pytest.approx(63 * G)
    # Ước tính đã tiêu hết: vẫn được sàn 1 trang/từ (nằm trong ước tính) — trừ khi hết tiền.
    assert TDA.tran_moi(21, uoc, uoc, 5.0) == pytest.approx(21 * G)
    assert TDA.tran_moi(21, uoc, 21 * G, 21 * G + 0.01) == pytest.approx(0.01)
    assert TDA.tran_moi(21, uoc, 21 * G, 0.0) == 0.0


def test_tim_moi_tiktok_cap_nhat_moc_yen_va_giu_moc_tu_loi(monkeypatch):
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    moc = {"luc": "2026-10-16T08:00:00+07:00", "tu": {
        "hapas": {"luc": "2026-10-16T08:00:00+07:00", "yen": 2},
        "tui hapas": {"luc": "2026-10-16T08:00:00+07:00", "yen": 2},
        "loi": {"luc": "2026-10-16T08:00:00+07:00", "yen": 0},
        "da bo": {"luc": "2026-10-16T08:00:00+07:00", "yen": 0}}}

    def gia(viec, so_trang, ngan, vung="VN"):
        assert so_trang == 3 and {k for k, _ in viec} == {"hapas", "túi hapas", "lỗi"}
        a = TT.video(_aweme(7000000001, ngay=0.2))
        b = TT.video(_aweme(7000000002, ngay=6))
        return {"hapas": {"bai": [a, b], "trang": 1, "moi_hon_moc": 1, "cham": True, "loi": ""},
                "túi hapas": {"bai": [b], "trang": 1, "moi_hon_moc": 0, "cham": True, "loi": ""},
                "lỗi": {"bai": [], "trang": 0, "moi_hon_moc": 0, "loi": "LOI: giả"}}
    monkeypatch.setattr(TT, "tim_moi_nhat", gia)
    ra, tk, m = TDA.tim_moi_tiktok(["hapas", "túi hapas", "lỗi"], moc, BAY, 1.0)
    assert len(ra) == 2 and all(d["_moi_nhat"] for d, _ in ra), "bỏ trùng giữa các từ khoá"
    assert tk["tu"] == 3 and tk["trang"] == 2 and tk["moi_hon_moc"] == 1 and "lỗi: LOI" in tk["loi"]
    assert m["tu"]["hapas"] == {"luc": BAY.isoformat(timespec="seconds"), "yen": 0}
    assert m["tu"]["tui hapas"]["yen"] == 3, "không có bài mới hơn mốc: thêm một lượt yên"
    assert m["tu"]["loi"] == moc["tu"]["loi"], "từ lỗi giữ mốc cũ — lượt sau lật lại"
    assert "da bo" not in m["tu"], "từ khoá đã bỏ khỏi dự án không giữ trong mốc"
    assert m["luc"] == BAY.isoformat(timespec="seconds")


def test_tim_moi_tiktok_khong_chay_khi_api_tat_hoac_khong_tien(monkeypatch):
    monkeypatch.setattr(TT, "tim_moi_nhat", lambda *a, **k: pytest.fail("không được gọi"))
    monkeypatch.setattr(TT, "dung_api", lambda viec: False)
    assert TDA.tim_moi_tiktok(["hapas"], None, BAY, 1.0)[0] == []
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    assert TDA.tim_moi_tiktok(["hapas"], None, BAY, 0.001)[0] == []


# ───────────────────────────── trong lượt /theodoi ─────────────────────────────
def _kich_ban(mo):  # noqa: F811
    kho = GiaKhoTk(mo)
    api = GiaApiCoActor(mo)
    lien_quan = _aweme(7000000001, user="kol.lon", ngay=1)
    lien_quan["desc"] = "review túi hapas"
    it_thich = _aweme(7000000005, user="be.nho", ngay=0.3)
    it_thich["desc"] = "mới mua túi hapas nè"
    it_thich["statistics"]["digg_count"] = 2
    api.tim[("hapas", 0)] = ([lien_quan], 0)
    goc = api._tra

    def tra(p):
        if "searchPosts_keyword" in p and p["searchPosts_sortType"] == TT.SAP_MOI_NHAT:
            assert p["searchPosts_publishTime"] == TT.MOI_NHAT_MOC_NGAY
            r = _trang([(7000000009, 10)], more=1)        # bài 10 ngày: đã chạm mốc 7 ngày
            r["search_item_list"][:0] = [{"aweme_info": it_thich}, {"aweme_info": lien_quan}]
            return r
        if "searchPosts_keyword" in p and p["searchPosts_sortType"] == TT.SAP_NHIEU_THICH:
            return _trang([], more=0)
        return goc(p)
    api._tra = tra
    # Feed hashtag TikTok (17/10/2026) có bài thử riêng (`test_duong_moi.py`) — tắt ở đây để sổ
    # tiền chỉ gồm thường + mới nhất + nổi.
    da = dict(DU_AN, tk_bat=True, tk_so_bai=15,
              cau_hinh={"tu_khoa": {p: {"bat": p == "tiktok", "hashtag": {"bat": False}}
                                    for p in T.TK_NEN_TANG}})
    return kho, api, da, it_thich


@pytest.mark.tiktok_api
def test_trang_moi_nhat_bat_bai_it_thich_vao_pheu_va_theo_nhip(mo):  # noqa: F811
    kho, api, da, _ = _kich_ban(mo)
    v = GiaViec({}, [])
    tk = _chay_tk(da, v)
    sap = [g["searchPosts_sortType"] for g in api.goi if "searchPosts_keyword" in g]
    assert sap == [0, 3, 1]
    f = tk["pheu"]["tiktok"]
    assert f["moi_nhat"]["ve"] == 3 and f["moi_nhat"]["moi"] == 2 and f["moi_nhat"]["tu"] == 1
    assert f["moi_nhat"]["trang"] == 1 and f["moi_nhat"]["usd"] == pytest.approx(G)
    giu = {r["khoa"] for _, rows in kho.bai for r in rows}
    assert "tiktok:7000000005" in giu, "bài ít thích chỉ trang mới nhất bắt được vào kho"
    cau = next(c for c in T._cau_tk(tk) if c.startswith("phễu tìm TikTok"))
    assert "; mới nhất (" in cau and "thêm 2 bài chưa có trong lượt thường" in cau
    moc = T.doc_moc_tk("hapas")[TDA.KHOA_MOC_MOI]
    assert moc["usd"] == pytest.approx(G) and moc["tu"]["hapas"]["yen"] == 0
    assert moc["ve"] == 3
    # Sổ tiền: thường + mới nhất + nổi = 3 yêu cầu.
    ph = next(x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x["id"] == "tk-tiktok")
    assert ph["usd_so"] == pytest.approx(3 * G)
    # Trong 20 giờ: không chạy lại trang mới nhất.
    api.goi.clear()
    tk2 = _chay_tk(da, GiaViec({}, []))
    assert [g["searchPosts_sortType"] for g in api.goi if "searchPosts_keyword" in g] == [0]
    assert "moi_nhat" not in tk2["pheu"]["tiktok"]


@pytest.mark.tiktok_api
def test_trang_moi_nhat_loi_khong_lam_mat_bai_luot_thuong(mo):  # noqa: F811
    kho, _api, da, _ = _kich_ban(mo)

    def hong(*a, **k):
        A._KHI_CO_RUN.get()({"id": "m1"}, {"actor": TT.ACTOR})
        raise RuntimeError("shape lạ")
    mo.setattr(TDA, "tim_moi_tiktok", hong)
    v = GiaViec({}, [])
    tk = _chay_tk(da, v)
    f = tk["pheu"]["tiktok"]
    assert f["moi"] == 1 and kho.bai and "lỗi" in f["moi_nhat"]["ly_do"]
    assert f["moi_nhat"]["usd"] == pytest.approx(G)
    # Review LOW: đã trả tiền thì vẫn ghi nhịp 20 giờ (mốc từng từ giữ nguyên — không có "tu").
    m = T.doc_moc_tk("hapas")[TDA.KHOA_MOC_MOI]
    assert m["usd"] == pytest.approx(G) and not m.get("tu")
    ph = next(x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x["id"] == "tk-tiktok")
    assert ph["trang_thai"] == "xong" and ph["usd_so"] == pytest.approx(3 * G)


@pytest.mark.tiktok_api
def test_trang_moi_nhat_khong_chay_khi_du_phong_hoac_het_gio(mo):  # noqa: F811
    GiaKhoTk(mo)
    goi = []
    mo.setattr(TDA, "tim_moi_tiktok", lambda *a, **k: goi.append(a) or ([], {}, {}))
    v = GiaViec({}, [])
    du_phong = [{"run_id": "a", "actor": TT.ACTOR},
                {"run_id": "b", "actor": "apidojo~tiktok-scraper"}]
    assert T._them_luot_moi(v, "hapas", 1, ["hapas"], [], {}, BAY, 1.0, 5.0,
                            du_phong) == ([], {})
    assert T._them_luot_moi(v, "hapas", 1, ["hapas"], [], {}, BAY, 1.0, 5.0, []) == ([], {})
    v_het = GiaViec({}, [], con=T._CHUA_GIAY_CUOI + 100)
    _, m = T._them_luot_moi(v_het, "hapas", 1, ["hapas"], [], {}, BAY, 1.0, 5.0,
                            [{"run_id": "a", "actor": TT.ACTOR}])
    assert "hết giờ" in m["ly_do"] and not goi


def test_trang_moi_nhat_khong_chay_khi_tiktok_api_tat(mo):  # noqa: F811
    """Bộ thử mặc định = TikTok API tắt (đường dự phòng tính tiền theo video)."""
    GiaKhoTk(mo)
    goi = []
    mo.setattr(TDA, "tim_moi_tiktok", lambda *a, **k: goi.append(a) or ([], {}, {}))
    mo.setattr(A, "_FETCH", {p: (lambda *a, **k: [_tt_tim("kol.a", "1", "túi hapas")])
                             for p in T.TK_NEN_TANG})
    tk = _chay_tk(dict(DU_AN, tk_bat=True, tk_so_bai=15))
    assert "moi_nhat" not in tk["pheu"]["tiktok"] and not goi


# ───────────────────────────── kiểm độ phủ nới trang mới nhất ─────────────────────────────
def _sot(u, tl, ma=("it_thich",)):
    return {"tai_khoan": u, "ten": u, "thao_luan": tl, "tag": [], "ma_ly_do": list(ma),
            "hanh_dong": []}


def test_kiem_do_phu_noi_trang_moi_nhat_khi_sot_it_thich_roi_lui():
    sot = [_sot("a", 10), _sot("b", 20)]
    hd = KDP.hanh_dong(sot, ["hapas"], set(), None, 60.0, BAY)
    assert hd["noi_cfg"]["moi_trang"] == TDA.MOI_TRANG_TOI_DA + 1
    assert "nới trang mới nhất" in hd["tom"]["noi"]["ly_do"]
    assert hd["tom"]["noi"]["moi_trang"] == [3, 4]
    assert any(h.startswith("nới trang mới nhất") for h in sot[0]["hanh_dong"])
    hd = KDP.hanh_dong(sot, ["hapas"], set(), {"moi_trang": 5}, 60.0, BAY)
    assert hd["noi_cfg"]["moi_trang"] == 5, "đã tối đa"
    hd = KDP.hanh_dong([], ["hapas"], set(), {"moi_trang": 5}, 95.0, BAY, tl_truoc=91.0)
    assert hd["noi_cfg"]["moi_trang"] == 4 and "trang mới nhất lùi" in hd["tom"]["noi"]["ly_do"]
    # Sót vì tụt hạng (không ít thích) không đụng trang mới nhất.
    hd = KDP.hanh_dong([_sot("a", 10, ("ngoai_cua_so",)), _sot("b", 9, ("chi_hashtag",))],
                       ["hapas"], set(), None, 60.0, BAY)
    assert hd["noi_cfg"]["moi_trang"] == TDA.MOI_TRANG_TOI_DA


@pytest.mark.tiktok_api
def test_kiem_do_phu_moi_trang_di_vao_luot(mo):  # noqa: F811
    _kho, api, da, _ = _kich_ban(mo)
    T.ghi_moc_tk("hapas", {KDP.KHOA_NOI_CFG: {"moi_trang": 5}})
    gui = []
    goc = TT.tim_moi_nhat
    mo.setattr(TT, "tim_moi_nhat", lambda viec, so_trang, ngan, vung="VN": (
        gui.append(so_trang), goc(viec, so_trang, ngan, vung))[1])
    tk = _chay_tk(da, GiaViec({}, []))
    assert gui == [5] and "theo kiểm độ phủ: tối đa 5 trang/từ" in tk["pheu"]["tiktok"][
        "moi_nhat"]["ly_do"]


# ───────────────────────────── ước tính: Mark = dashboard = trình duyệt ─────────────────────────────
TU_VD = ["hapas", "túi hapas", "ví hapas", "yeutudieunhonhat"]


def test_uoc_tiktok_cong_mot_trang_moi_nhat_moi_tu():
    tu = ["k"] * 21
    assert T.uoc_tu_khoa_nen_tang("tiktok", 300, tu) == round((21 * 4 + 10) * G * 1.3, 4)
    for so_bai in (1, 15, 100, 300, 2000):
        assert CP.uoc_tk_nen_tang("tiktok", so_bai, TU_VD) == T.uoc_tu_khoa_nen_tang(
            "tiktok", so_bai, TU_VD)
    assert CP.TK_TT_MOI_NHAT == TDA.MOI_TRANG
    assert CP.hang_so_cho_trinh_duyet()["tk_tt_moi_nhat"] == TDA.MOI_TRANG


def test_ngan_sach_js_uoc_tk_khop_python(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    js = (Path(__file__).resolve().parents[1] / "dashboard" / "static" / "ngan_sach.js").read_text(
        encoding="utf-8")
    khoi = re.search(r"// <uoc_tk>.*?// </uoc_tk>", js, re.DOTALL).group(0)
    hs = CP.hang_so_cho_trinh_duyet()
    ca = [(p, so) for p in ("tiktok", "facebook", "threads", "instagram")
          for so in (0, 1, 15, 100, 300)]
    chay = (f"var hs = {json.dumps(hs, ensure_ascii=False)};\n"
            f"var TU = {json.dumps(TU_VD, ensure_ascii=False)};\n"
            "var TU_IG = TU.filter(function (t) { return t.indexOf(' ') < 0; });\n"
            "function r4(x) { return Number(x.toFixed(4)); }\n"
            "function uocWeb() { return 0; }\n" + khoi +
            f"\nvar ca = {json.dumps(ca)};\n"
            "console.log(JSON.stringify(ca.map(function (c) { return uocTk(c[0], c[1], 2); })));\n")
    f = tmp_path / "uoc.js"
    f.write_text(chay, encoding="utf-8")
    ra = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True,
                                   encoding="utf-8", check=True, timeout=30).stdout)
    assert ra == [CP.uoc_tk_nen_tang(p, so, TU_VD, 2, fb_toi_da=CP.GIOI_HAN["tk_so_bai"][1])
                  for p, so in ca]


# ───────────────────────────── review 17/10 (M1, M2, LOW) ─────────────────────────────
def test_tim_moi_nhat_bao_cham_moc(monkeypatch):
    """M1: dừng vì trần trang trước khi chạm mốc → cham=False (+ giờ bài cũ nhất đã thấy);
    chạm mốc hoặc hết feed → cham=True."""
    now = datetime.datetime.now(_VN)
    _goi_gia(monkeypatch, {
        ("ban", 0): _trang([(i, 0.1) for i in range(1, 31)]),
        ("ban", 30): _trang([(i, 0.2) for i in range(31, 61)], cursor=60),
        ("het", 0): _trang([(100, 0.1)], more=0),
        ("cham", 0): _trang([(200, 0.1), (201, 9)]),
    })
    moc = now - datetime.timedelta(days=5)
    kq = TT.tim_moi_nhat([("ban", moc), ("het", moc), ("cham", moc)], 2, TT.Ngan(1.0))
    assert not kq["ban"]["cham"] and kq["ban"]["trang"] == 2
    assert kq["ban"]["cu_nhat"] < now - datetime.timedelta(hours=4)
    assert kq["het"]["cham"] and kq["cham"]["cham"]


def test_tim_moi_nhat_trang_dau_cho_moi_tu_truoc(monkeypatch):
    """M2: trần chung 3 yêu cầu, từ đầu rất bận — vẫn đủ trang đầu cho cả 3 từ (không đói)."""
    now = datetime.datetime.now(_VN)
    ban = {("a", off): _trang([(off + i + 1, 0.01) for i in range(30)], cursor=off + 30)
           for off in (0, 30, 60)}
    goi = _goi_gia(monkeypatch, {**ban, ("b", 0): _trang([(500, 0.1)], more=0),
                                 ("c", 0): _trang([(600, 0.1)], more=0)})
    kq = TT.tim_moi_nhat([("a", now - datetime.timedelta(days=9)), ("b", now), ("c", now)], 3,
                         TT.Ngan(3 * G))
    assert sorted((g["searchPosts_keyword"], g["searchPosts_offset"]) for g in goi) == [
        ("a", 0), ("b", 0), ("c", 0)]
    assert kq["b"]["trang"] == kq["c"]["trang"] == 1 and not kq["a"]["cham"]
    # Còn tiền: vòng sau chỉ từ chưa xong ("a") lật tiếp.
    goi.clear()
    kq = TT.tim_moi_nhat([("a", now - datetime.timedelta(days=9)), ("b", now)], 3, TT.Ngan(1.0))
    assert [(g["searchPosts_keyword"], g["searchPosts_offset"]) for g in goi].count(("b", 0)) == 1
    assert kq["a"]["trang"] == 3


def test_tim_moi_tiktok_chua_cham_moc_khong_doi_moc(monkeypatch):
    """M1: từ chưa lật tới mốc giữ mốc cũ; từ chưa có mốc thì mốc = bài cũ nhất đã thấy + 24 giờ
    (lượt sau lật tới đúng đó — không hở khoảng)."""
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    cu = BAY - datetime.timedelta(hours=30)
    moc = {"luc": "2026-10-16T08:00:00+07:00", "tu": {
        "hapas": {"luc": "2026-10-16T08:00:00+07:00", "yen": "rác"}}}
    monkeypatch.setattr(TT, "tim_moi_nhat", lambda viec, so_trang, ngan, vung="VN": {
        "hapas": {"bai": [], "trang": 3, "moi_hon_moc": 90, "cham": False, "cu_nhat": cu,
                  "loi": ""},
        "mới": {"bai": [], "trang": 3, "moi_hon_moc": 90, "cham": False, "cu_nhat": cu,
                "loi": ""}})
    _, tk, m = TDA.tim_moi_tiktok(["hapas", "mới"], moc, BAY, 1.0)
    assert m["tu"]["hapas"] == moc["tu"]["hapas"] and tk["chua_cham"] == 2
    assert m["tu"]["moi"]["luc"] == (cu + datetime.timedelta(hours=24)).isoformat(
        timespec="seconds")
    # yen rác + chạm mốc → coi như 0 (không ném lỗi).
    monkeypatch.setattr(TT, "tim_moi_nhat", lambda viec, so_trang, ngan, vung="VN": {
        "hapas": {"bai": [], "trang": 1, "moi_hon_moc": 0, "cham": True, "loi": ""}})
    _, _, m = TDA.tim_moi_tiktok(["hapas"], moc, BAY, 1.0)
    assert m["tu"]["hapas"]["yen"] == 1


def test_tim_moi_tiktok_bai_hong_shape_khong_mat_bai_khac(monkeypatch):
    """LOW: một item hỏng không làm mất các bài đã trả tiền khác."""
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    tot = TT.video(_aweme(7000000001, ngay=0.2))
    monkeypatch.setattr(TT, "tim_moi_nhat", lambda viec, so_trang, ngan, vung="VN": {
        "hapas": {"bai": [tot, {"id": "x", "createTimeISO": None, "authorMeta": 5}], "trang": 1,
                  "moi_hon_moc": 1, "cham": True, "loi": ""}})
    goc = A._chuan_clockworks

    def chuan(items):
        if any(it.get("id") == "x" for it in items):
            raise TypeError("shape lạ")
        return goc(items)
    monkeypatch.setattr(A, "_chuan_clockworks", chuan)
    ra, tk, _ = TDA.tim_moi_tiktok(["hapas"], None, BAY, 1.0)
    assert len(ra) == 1 and "hỏng shape" in tk["loi"]
