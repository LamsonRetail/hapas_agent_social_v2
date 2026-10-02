"""Canh trần THEO NỀN TẢNG của `social_listen` (chủ agent xin 02/10/2026: "nên làm 1 bộ
lọc giá cho từng nền tảng để ví dụ họ muốn chỉ cào 1 nền tảng thì có thể điều chỉnh").

Console lưu trong `cau_hinh` của social_listen, mọi khoá tuỳ chọn: `bat_<p>` (0 = tắt),
`tran_bai_<p>`, `tran_usd_<p>` (YouTube miễn phí nên bỏ qua `tran_usd_youtube`). Thiếu
khoá thì dùng trần chung — không đặt gì thì hành vi y như trước.
Không chạm mạng: Apify, Lark, model, platform đều giả.
"""
from __future__ import annotations

import json
import re

import pytest

import apify_tool as A
import lsr_policy
import quet_lon as Q
import viec_nen as V
from deep_dive_tool import _SoNganSach
from test_viec_nen import _quet, nen  # noqa: F401 — fixture việc nền dùng chung

TU, DEN = "2026-09-19", "2026-09-25"


@pytest.fixture
def cau_hinh(monkeypatch):
    def dat(c):
        monkeypatch.setattr(lsr_policy, "cau_hinh_tool",
                            lambda tool: dict(c) if tool == "social_listen" else {})
    return dat


@pytest.fixture
def chay(monkeypatch):
    """`_handle` với fetcher giả ghi lại `limit` + nền tảng ngữ cảnh của từng nguồn."""
    nhan: dict = {}
    for p in A._ALL:
        monkeypatch.setitem(A._FETCH, p, lambda q, lim, *a, _p=p: nhan.__setitem__(
            _p, (lim, A._NEN_TANG.get())) or [])
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A.chi_phi_tool, "ghi", lambda **k: {})
    monkeypatch.setattr(A, "_han_muc_thang", lambda: None)

    def goi(**k):
        a = {"queries": ["hapas"], "date_from": TU, "date_to": DEN}
        a.update(k)
        return json.loads(A._handle(a)), nhan
    return goi


class _Post:
    status_code = 200

    def json(self):
        return []


def _bat_post(monkeypatch) -> list:
    url: list = []
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A.requests, "post", lambda u, **k: url.append(u) or _Post())
    return url


# ───────────────────────────── đọc trần ─────────────────────────────
def test_chua_dat_khoa_rieng_thi_y_tran_chung(cau_hinh):
    cau_hinh({"tran_bai": 800, "tran_usd": 2.5})
    for p in A._ALL:
        assert A._tran_nen_tang(p) == (800, 2.5, True)
        assert A._khoa_rieng(p) == set()


def test_khoa_rieng_duoc_dung_cho_dung_nen_tang(cau_hinh):
    cau_hinh({"tran_bai": 800, "tran_usd": 2.5, "tran_bai_tiktok": 200,
              "tran_usd_tiktok": 0.6, "tran_usd_threads": 1.2})
    assert A._tran_nen_tang("tiktok") == (200, 0.6, True)
    assert A._tran_nen_tang("threads") == (800, 1.2, True)
    assert A._tran_nen_tang("instagram") == (800, 2.5, True)


@pytest.mark.parametrize("c, mong", [
    ({"tran_bai_tiktok": 99999, "tran_usd_tiktok": 999}, (10000, 5.0)),
    ({"tran_bai_tiktok": 0, "tran_usd_tiktok": 0}, (10, 0.1)),
    ({"tran_bai_tiktok": -3, "tran_usd_tiktok": -1}, (10, 0.1)),
    ({"tran_bai_tiktok": "abc", "tran_usd_tiktok": float("nan")}, (A._MAX_LIMIT,
                                                                   round(A._MAX_CHARGE, 2))),
])
def test_kep_trong_khoang_an_toan_nhu_tran_chung(cau_hinh, c, mong):
    cau_hinh(c)
    assert A._tran_nen_tang("tiktok")[:2] == mong


def test_tai_cho_kep_5_usd_nen_duoc_toi_50(cau_hinh):
    cau_hinh({"tran_usd_tiktok": 30})
    assert A._tran_nen_tang("tiktok")[1] == 5.0
    assert A._tran_nen_tang("tiktok", nen=True)[1] == 30.0
    tok = A._NEN.set(True)
    try:
        assert A._tran_nen_tang("tiktok")[1] == 30.0
    finally:
        A._NEN.reset(tok)


def test_youtube_bo_qua_tran_usd_rieng(cau_hinh):
    cau_hinh({"tran_usd": 2, "tran_usd_youtube": 0.1, "tran_bai_youtube": 300})
    assert A._tran_nen_tang("youtube") == (300, 2.0, True)
    assert A._khoa_rieng("youtube") == {"bai"}


@pytest.mark.parametrize("v, bat", [(0, False), ("0", False), (0.0, False), (1, True),
                                    (None, True), ("rác", True), (True, True)])
def test_cong_tac_chi_tat_khi_dung_bang_0(cau_hinh, v, bat):
    cau_hinh({"bat_threads": v})
    assert A._tran_nen_tang("threads")[2] is bat


# ───────────────────────────── trần USD gửi Apify ─────────────────────────────
def test_call_theo_nen_tang_dung_tran_usd_rieng(cau_hinh, monkeypatch):
    cau_hinh({"tran_usd": 2.5, "tran_usd_tiktok": 0.7})
    url = _bat_post(monkeypatch)
    A._call("apidojo~tiktok-scraper", {}, 10, nen_tang="tiktok")
    A._call("apidojo~tiktok-scraper", {}, 10)                      # không ngữ cảnh: chung
    tok = A._NEN_TANG.set("tiktok")                               # ngữ cảnh do `_handle` đặt
    try:
        A._call("apidojo~tiktok-scraper", {}, 10)
        A._call("a~b", {}, 10, tran_usd=1.9)                      # trần riêng của tool thắng
    finally:
        A._NEN_TANG.reset(tok)
    assert [re.search(r"maxTotalChargeUsd=([\d.]+)", u).group(1) for u in url] == [
        "0.7", "2.5", "0.7", "1.9"]


def test_tran_usd_rieng_tai_cho_van_kep_5(cau_hinh, monkeypatch):
    cau_hinh({"tran_usd_threads": 40})
    url = _bat_post(monkeypatch)
    A._call("a~b", {}, 10, nen_tang="threads")
    assert "maxTotalChargeUsd=5.0" in url[0]


# ───────────────────────────── `_handle` ─────────────────────────────
def test_handle_kep_limit_tung_nen_tang_va_dat_ngu_canh(cau_hinh, chay):
    cau_hinh({"tran_bai": 300, "tran_bai_tiktok": 100})
    kq, nhan = chay(platforms=["tiktok", "youtube"], limit=400)
    assert nhan == {"tiktok": (100, "tiktok"), "youtube": (300, "youtube")}
    assert "trần console của TikTok là 100 bài" in kq["limit_bi_cat"]
    assert "trần chung 300 bài/nền tảng cho YouTube" in kq["limit_bi_cat"]
    assert "trần console của TikTok là 100 bài" in kq["note"]
    assert kq["tran_theo_nen_tang"]["tiktok"]["tran_bai"] == 100


def test_handle_khong_khoa_rieng_giu_cau_cu(cau_hinh, chay):
    cau_hinh({"tran_bai": 200})
    kq, nhan = chay(platforms=["tiktok"], limit=900)
    assert nhan == {"tiktok": (200, "tiktok")}
    assert kq["limit_bi_cat"].startswith("Người dùng xin 900 bài, trần hiện tại là 200")
    assert kq["tran_theo_nen_tang"] is None and kq["nen_tang_tat"] is None


def test_handle_quet_rong_dung_tran_rieng_va_bo_qua_nen_tang_tat(cau_hinh, chay):
    cau_hinh({"tran_bai_tiktok": 20, "bat_facebook": 0})
    kq, nhan = chay()
    assert "facebook" not in nhan and nhan["tiktok"][0] == 20
    assert nhan["instagram"][0] == A._SHALLOW["instagram"]
    assert kq["per_platform"]["facebook"]["status"] == "TAT_BOI_CHU_AGENT"
    assert "facebook" not in kq["platforms"] and kq["nen_tang_tat"] == ["facebook"]
    assert kq["note"].count("chủ agent đã tắt Facebook") == 1
    assert "Nhắc một lần" in kq["note"]


def test_handle_goi_dich_danh_nen_tang_tat_thi_noi_dau_tien(cau_hinh, chay):
    cau_hinh({"bat_tiktok": 0})
    kq, nhan = chay(platforms=["tiktok", "threads"])
    assert list(nhan) == ["threads"]
    v = kq["per_platform"]["tiktok"]
    assert v["status"] == "TAT_BOI_CHU_AGENT"
    assert v["ly_do"] == ("chủ agent đã tắt TikTok trên console "
                          "(Năng lực → Quét mạng xã hội)")
    assert kq["note"].startswith("NỀN TẢNG CHỦ AGENT ĐÃ TẮT — nói ĐẦU TIÊN: chủ agent đã "
                                 "tắt TikTok")


def test_handle_tat_het_thi_tu_choi_khong_goi_apify(cau_hinh, monkeypatch):
    cau_hinh({"bat_tiktok": 0, "bat_threads": "0"})

    def cam(*a, **k):
        raise AssertionError("nền tảng đã tắt thì không được gọi Apify")
    monkeypatch.setattr(A, "_call", cam)
    monkeypatch.setattr(A.requests, "post", cam)
    kq = json.loads(A._handle({"queries": ["hapas"], "platforms": ["tiktok", "threads"],
                               "date_from": TU, "date_to": DEN}))
    s = json.dumps(kq, ensure_ascii=False)
    assert "KHÔNG QUÉT" in s and "chủ agent đã tắt TikTok" in s and "Threads" in s


def test_handle_bao_tran_usd_rieng_khi_trui(cau_hinh, chay):
    cau_hinh({"tran_usd_tiktok": 0.1})
    kq, _ = chay(platforms=["tiktok"], limit=100)       # ~0,3 USD > 0,1
    assert "trần console của TikTok là 0,1 USD/lượt" in kq["tran_rieng_rang_buoc"]
    assert "Trần riêng: trần console của TikTok là 0,1 USD/lượt" in kq["note"]


def test_uoc_tinh_tai_cho_noi_tran_rieng(cau_hinh, chay):
    cau_hinh({"tran_bai": 300, "tran_bai_tiktok": 100, "tran_usd_tiktok": 0.1})
    kq, nhan = chay(platforms=["tiktok"], limit=400, chi_uoc_tinh=True)
    assert not nhan and kq["chi_uoc_tinh"] and kq["se_chay_nen"] is False
    assert "đang trói: trần console của TikTok là 100 bài" in kq["note"]
    assert "trần console của TikTok là 0,1 USD/lượt" in kq["note"]


# ───────────────────────────── việc nền ─────────────────────────────
def test_uoc_tinh_nen_bao_vuot_tran_rieng(nen, cau_hinh, monkeypatch):
    cau_hinh({"tran_usd_tiktok": 2})
    def cam(*a, **k):
        raise AssertionError("chi_uoc_tinh không được POST")
    monkeypatch.setattr(A.requests, "post", cam)
    kq = _quet(limit=3000, chi_uoc_tinh=True)
    assert kq["se_chay_nen"] and "VƯỢT trần console của TikTok là 2 USD" in kq["note"]
    assert kq["per_platform"]["tiktok"]["tran_console_usd_rieng"] == 2.0
    kq = _quet(limit=3000)
    assert kq["chua_chay"] and "vượt trần console của TikTok là 2 USD" in kq["note"]
    assert not V.tat_ca()


def test_nen_khong_khoa_rieng_van_mot_so_chung(nen):
    kq = _quet(limit=1500)
    v = V.Viec(V.doc(kq["ma_viec"]))
    assert type(Q._so_ngan_sach(v)) is _SoNganSach
    assert "tran_usd_rieng" not in v.d["nen_tang"]["tiktok"]


def test_nen_moi_nen_tang_khong_vuot_tran_rieng(nen, cau_hinh):
    cau_hinh({"tran_usd_tiktok": 0.5})
    kq = _quet(platforms=["tiktok", "threads"], limit=1500, cat_theo_ngan_sach=True)
    assert kq["dang_chay_nen"], kq.get("note")
    d0 = V.doc(kq["ma_viec"])
    assert d0["nen_tang"]["tiktok"]["tran_usd_rieng"] == 0.5
    assert d0["nen_tang"]["threads"]["tran_usd_chung"] == 20.0
    assert d0["ngan_sach_usd"] == 20.5
    assert sum(x["uoc_usd"] for x in d0["nen_tang"]["tiktok"]["phan"]) <= 0.5
    d = V.chay_ngay(kq["ma_viec"])
    cap = [float(re.search(r"maxTotalChargeUsd=([\d.]+)", u).group(1))
           for u in nen.post_urls if "tiktok" in u]
    assert cap and sum(cap) <= 0.5 + 1e-9
    assert sum(float(ph.get("usd_so") or 0)
               for ph in d["nen_tang"]["tiktok"]["phan"]) <= 0.5 + 1e-9


def test_so_theo_nen_tang_chan_nen_tang_vuot_khong_chan_nen_tang_khac():
    ns = Q._SoTheoNenTang(_SoNganSach(10.0), {"tiktok": _SoNganSach(1.0),
                                              "_chung": _SoNganSach(5.0)},
                          {"tiktok": "tiktok", "threads": "_chung"})
    assert ns.xin(0.4, 0.6, p="tiktok") == 0.6
    assert ns.xin(0.4, 0.6, p="tiktok") == 0.4          # chỉ còn 0,4 trong trần TikTok
    ns.tra(0.6, 0.6, p="tiktok")
    assert ns.xin(0.2, 0.3, p="threads") == 0.3
    t = ns.nhom["tiktok"]
    assert t.da + t.giu == pytest.approx(1.0)
    assert ns.xin(0.1, 0.2, p="tiktok") == 0.0          # TikTok kín trần: dừng TikTok
    assert t.dung and not ns.chung.dung
    assert ns.xin(0.2, 0.3, p="threads") == 0.3         # ... Threads vẫn chạy
    assert ns.da == pytest.approx(0.6) and ns.giu == pytest.approx(1.0)


# ───────────────────────────── khớp console (repo Platform) ─────────────────────────────
def _ts_social_listen() -> str:
    import os
    import pathlib
    goc = pathlib.Path(os.environ.get("PLATFORM_REPO") or r"D:\Platform")
    ts = goc / "apps" / "platform-web" / "lib" / "agentToolCapabilities.ts"
    if not ts.is_file():
        pytest.skip(f"không thấy {ts} — đặt PLATFORM_REPO trỏ tới repo Platform")
    s = ts.read_text(encoding="utf-8")
    m = re.search(r"social_listen:\s*\[(.*?)\n  \],", s, re.S)
    assert m, "console không có khối social_listen trong CAU_HINH_THEO_TOOL"
    return m.group(1)


def _o(khoi: str, khoa: str) -> dict | None:
    """min/max/mac_dinh của ô `khoa` — viết thẳng ("tran_bai_tiktok") hoặc sinh bằng
    template (`tran_bai_${p}`)."""
    goc = khoa.rsplit("_", 1)[0]
    m = (re.search(rf'khoa:\s*"{khoa}"[^}}]*', khoi)
         or re.search(rf"khoa:\s*`{goc}_\$\{{[^}}]+\}}`[^}}]*", khoi))
    if not m:
        return None
    ra = {}
    for k in ("min", "max", "mac_dinh"):
        x = re.search(rf"\b{k}:\s*([\d.]+)", m.group(0))
        if x:
            ra[k] = float(x.group(1))
    return ra


def _nen_tang_sinh_tu_truong_chung() -> dict | None:
    """Cách console (PR #85, 02/10/2026) khai báo: bảng `NEN_TANG_THEO_TOOL.social_listen`
    + `truongNenTang` CHÉP khoảng của ô chung (`{ ...gBai, khoa: `${lk.bai}_${nt.ma}` }`).
    -> {mã nền tảng: có ô USD?} hoặc None nếu console không khai kiểu này."""
    import os
    import pathlib
    goc = pathlib.Path(os.environ.get("PLATFORM_REPO") or r"D:\Platform")
    ts = goc / "apps" / "platform-web" / "lib" / "agentToolCapabilities.ts"
    s = ts.read_text(encoding="utf-8") if ts.is_file() else ""
    m = re.search(r"NEN_TANG_THEO_TOOL[^=]*=\s*\{\s*social_listen:\s*\[(.*?)\]", s, re.S)
    if not m or not re.search(r"\.\.\.gBai,\s*khoa:\s*`\$\{lk\.bai\}_\$\{nt\.ma\}`", s) \
            or not re.search(r"\.\.\.gUsd,\s*khoa:\s*`\$\{lk\.usd\}_\$\{nt\.ma\}`", s):
        return None
    return {ma: gia != "null" for ma, gia in
            re.findall(r'ma:\s*"(\w+)"[^}]*?usd_moi_bai:\s*([\w.]+)', m.group(1))}


def test_khop_tran_theo_nen_tang_ben_console():
    """Console chặn gõ nhầm bằng min/max của nó; lệch với runtime là console cho lưu một
    số rồi runtime lặng lẽ kẹp thành số khác."""
    khoi = _ts_social_listen()
    sinh = _nen_tang_sinh_tu_truong_chung()
    if sinh is not None:
        # Ô theo nền tảng chép khoảng của ô chung, mà ô chung đã đối chiếu ở
        # test_tran_quet — ở đây chỉ cần cùng bộ nền tảng, và YouTube không có ô USD.
        assert set(sinh) == set(A._ALL), f"console có nền tảng {sorted(sinh)}"
        assert sinh["youtube"] is False and all(sinh[p] for p in A._ALL if p != "youtube")
        return
    if _o(khoi, "tran_bai_tiktok") is None:
        pytest.skip("Platform chưa có trần theo nền tảng")
    for p in A._ALL:
        bai = _o(khoi, f"tran_bai_{p}")
        assert bai, f"console thiếu tran_bai_{p}"
        assert (bai["min"], bai["max"]) == A._TRAN_BAI_KHOANG
        if "mac_dinh" in bai:
            assert bai["mac_dinh"] == A._MAX_LIMIT
        if p != "youtube":
            usd = _o(khoi, f"tran_usd_{p}")
            assert usd, f"console thiếu tran_usd_{p}"
            assert (usd["min"], usd["max"]) == A._TRAN_USD_KHOANG
            if "mac_dinh" in usd:
                assert usd["mac_dinh"] == A._MAX_CHARGE
        bat = _o(khoi, f"bat_{p}")
        if bat:
            assert (bat.get("min", 0), bat.get("max", 1), bat.get("mac_dinh", 1)) == (0, 1, 1)
