"""Từ khoá KHÔNG đem đi tìm trên từng nền tảng (18/10/2026, `du_an.cau_hinh.tu_khoa.<nền tảng>.bo_tu`).

Điều tra Kompa 18/10/2026: cụm "yêu từ điều nhỏ nhất" tìm trên Facebook ra 18/20 bài không phải
HAPAS ("yêu từ những điều nhỏ nhất" là câu chung). Bỏ cụm ở bước TÌM của nền tảng đó (mọi đường tìm:
Facebook scrapeforge + đường 2…), bài vẫn lọc theo đủ từ khoá. Mark = dashboard (Python) = trình duyệt."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import theo_doi as T
from dashboard import chi_phi as CP

TU = ["hapas", "túi hapas", "quà tặng hapas", "Yêu từ điều nhỏ nhất", "yeutudieunhonhat",
      "quatang2010"]
DA = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": TU, "tk_bat": True, "tk_so_bai": 15,
      "cau_hinh": {"tu_khoa": {
          "facebook": {"bat": True, "bo_tu": ["yêu từ điều NHỎ nhất", "  "]},
          "instagram": {"bat": True, "bo_tu": ["#quatang2010", "yêu từ điều nhỏ nhất"]},
          "tiktok": {"bat": True, "bo_tu": ["quatang2010"]},
          "threads": {"bat": True, "so_bai": 60, "bo_tu": ["túi hapas"]},
          "web": {"bat": True, "bo_tu": ["quà tặng hapas"]},
          "youtube": {"bat": True, "bo_tu": "không phải danh sách"}}}}


def test_bo_tu_chi_bo_dung_cum_cua_dung_nen_tang():
    assert T.bo_tu(DA, "facebook") == ["yêu từ điều NHỎ nhất"], "mục rỗng bỏ"
    assert T.bo_tu(DA, "youtube") == [] and T.bo_tu({}, "facebook") == []
    fb = T.tu_nen_tang(DA, "facebook", TU)
    assert fb == ["hapas", "túi hapas", "quà tặng hapas", "yeutudieunhonhat", "quatang2010"], \
        "bỏ đúng cụm (không dấu, không phân biệt hoa thường), GIỮ dạng hashtag viết liền"
    assert T.tu_nen_tang(DA, "tiktok", TU) == [x for x in TU if x != "quatang2010"]
    assert T.tu_nen_tang(DA, "youtube", TU) == TU
    # Hashtag (Instagram, feed TikTok): mục MỘT chữ bỏ hashtag cùng dạng viết liền; cụm nhiều chữ chỉ
    # bỏ chính cụm — #yeutudieunhonhat (từ khoá riêng) vẫn tìm.
    assert T.tag_cua(DA, "instagram", TU) == ["hapas", "túi hapas", "quà tặng hapas",
                                             "yeutudieunhonhat"]
    assert T._tu_cho("instagram", T.tag_cua(DA, "instagram", TU)) == [
        "hapas", "tuihapas", "quatanghapas", "yeutudieunhonhat"]
    assert T.tag_tiktok(T.tag_cua(DA, "tiktok", TU)) == ["hapas", "yeutudieunhonhat"]
    co_tag = {**DA, "hashtag": ["hapas", "quatang2010", "sanhyeuchieu"]}
    assert T.tag_cua(co_tag, "tiktok", TU) == ["hapas", "sanhyeuchieu"]
    for da in (DA, co_tag, {**DA, "cau_hinh": {}}):
        for p in CP.NEN_TANG:
            assert CP.bo_tu(da, p) == T.bo_tu(da, p)
            assert CP.tu_nen_tang(da, p, TU) == T.tu_nen_tang(da, p, TU), p
            assert CP.tag_cua(da, p, TU) == T.tag_cua(da, p, TU), p


def test_uoc_tinh_mark_bang_dashboard_va_giam_khi_bo_tu():
    for da in (DA, {**DA, "cau_hinh": {"tu_khoa": {p: {"bat": True} for p in CP.NEN_TANG}}}):
        b = CP.bang_cau_hinh(da)
        assert b["uoc_tk"] == pytest.approx(T.uoc_tu_khoa_du_an(da, fb_toi_da=10 ** 6), abs=1e-4)
    b = CP.bang_cau_hinh(DA)
    goc = CP.bang_cau_hinh({**DA, "cau_hinh": {"tu_khoa": {
        p: {k: v for k, v in x.items() if k != "bo_tu"}
        for p, x in DA["cau_hinh"]["tu_khoa"].items()}}})
    # Threads đường 1 (18/10/2026) chỉ nhận từ một chữ có tên brand → bỏ cụm "túi hapas" không đổi
    # đường 1; số từ TÌM (đường 2 nhận mọi từ) giảm theo `bo_tu`.
    assert b["tu_khoa"]["threads"]["so_tu_gui"] == goc["tu_khoa"]["threads"]["so_tu_gui"] == 1
    assert b["tu_khoa"]["threads"]["tu_duong1"] == ["hapas"]
    assert b["tu_khoa"]["threads"]["so_tu_tim"] == 5 < goc["tu_khoa"]["threads"]["so_tu_tim"]
    assert b["tu_khoa"]["instagram"]["uoc"] < goc["tu_khoa"]["instagram"]["uoc"]
    assert b["tu_khoa"]["facebook"]["so_tu_tim"] == len(TU) - 1
    assert b["tu_khoa"]["facebook"]["duong2"]["cum"] == ["túi hapas", "quà tặng hapas"]
    assert b["tu_khoa"]["tiktok"]["hashtag"]["tag"] == ["hapas", "yeutudieunhonhat"]
    assert b["tu_khoa"]["web"]["so_cau"] <= goc["tu_khoa"]["web"]["so_cau"]
    # Mục không khớp từ khoá nào thì trang nói rõ (gõ sai); hashtag một chữ khớp tag với IG/TikTok.
    sai = CP.bang_cau_hinh({**DA, "cau_hinh": {"tu_khoa": {
        "facebook": {"bat": True, "bo_tu": ["yêu từ điều nhỏ nhất", "hapas sale"]},
        "instagram": {"bat": True, "bo_tu": ["#quatang2010", "#khongco"]}}}})
    assert sai["tu_khoa"]["facebook"]["bo_tu_la"] == ["hapas sale"]
    assert sai["tu_khoa"]["instagram"]["bo_tu_la"] == ["#khongco"]


def test_tim_facebook_ca_hai_duong_khong_tim_cum_bo(monkeypatch):
    """Mọi đường tìm Facebook (scrapeforge + đường 2) bỏ cụm; nền tảng khác vẫn tìm đủ; ghi chú lượt
    nói rõ."""
    import test_duong_moi as DM
    from test_theo_doi import DU_AN

    import apify_tool as A
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 5.0, True))
    monkeypatch.setattr(A, "_youtube_co_key", lambda: True)
    monkeypatch.setattr(A, "_phan_xu_ai", lambda *a, **k: ({}, {"_sac_thai": {}, "_chu_de": {},
                                                                 "trang_thai": "đã chạy"}))
    import viec_nen
    monkeypatch.setattr(viec_nen, "tat_ca", list)
    monkeypatch.setattr(T, "_kiem_do_phu", lambda *a, **k: {})
    da = dict(DU_AN, tu_khoa=["hapas", "túi hapas", "quà tặng hapas", "yêu từ điều nhỏ nhất"],
              tk_bat=True, tk_so_bai=15,
              cau_hinh={"tu_khoa": {"facebook": {"bat": True,
                                                 "bo_tu": ["yêu từ điều nhỏ nhất", "quà tặng hapas"]}}})
    tk, _, goi, _ = DM._chay_tk_fb(monkeypatch, [DM._sf_tim("shop.a", "1001", "túi hapas mới về")],
                                   DM._mina(), du_an=da)
    assert goi["facebook"] and all("yêu từ điều nhỏ nhất" not in q and "quà tặng hapas" not in q
                                   for q in goi["facebook"])
    assert goi[T.TK_FB2][0][0] == ["túi hapas"], "đường 2 chỉ còn cụm không bị bỏ"
    assert any(c.startswith("tìm Facebook: không tìm 2 từ khoá theo cấu hình") for c in tk["ghi_chu"])
    assert tk["tu"] == da["tu_khoa"], "lọc bài + AI vẫn dùng đủ từ khoá"


def test_trang_ngan_sach_luu_va_hien_khong_tim_tren():
    from test_dashboard_app import QL, XEM, GiaKho, dang_nhap, tao, thong_bao
    kho = GiaKho()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15,
                              tu_khoa=["hapas", "túi hapas", "yêu từ điều nhỏ nhất"])
    _, c, _ = tao(kho)
    csrf = dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    nc = t.index('<details class="ns-nc" id="ns-nang-cao">')
    for p in CP.NEN_TANG:
        assert t.index(f'name="tk_{p}_bo_tu"') > nc, p
    assert "Không tìm trên…" in t
    form = {"csrf": csrf, "tk_facebook_bat": "1",
            "tk_facebook_bo_tu": "Yêu từ điều nhỏ nhất, hapas sale; yêu từ điều nhỏ nhất",
            "tk_tiktok_bat": "1", "tk_tiktok_bo_tu": ""}
    r = c.post("/ngan-sach/hapas/cau-hinh", data=form)
    assert "Đã lưu cấu hình thu thập" in thong_bao(c, r)
    ch = kho.du_an["hapas"]["cau_hinh"]["tu_khoa"]
    assert ch["facebook"] == {"bat": True, "bo_tu": ["Yêu từ điều nhỏ nhất", "hapas sale"]}
    assert ch["tiktok"] == {"bat": True}, "ô trống: không ghi khoá"
    t = c.get("/ngan-sach").text
    assert re.search(r'name="tk_facebook_bo_tu" value="Yêu từ điều nhỏ nhất, hapas sale"', t)
    assert "Không khớp từ khoá nào của dự án: hapas sale" in t
    assert 'data-o="bo-tu-facebook">tìm 2/3 từ khoá' in t
    d = json.loads(re.search(r'id="ns-du-lieu">(.*?)</script>', t, re.DOTALL).group(1))
    assert d["bo_tu"]["facebook"] == ["Yêu từ điều nhỏ nhất", "hapas sale"]
    # Trang cũ (biểu mẫu không có ô): giữ danh sách đang lưu.
    c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "tk_facebook_bat": "1"})
    assert kho.du_an["hapas"]["cau_hinh"]["tu_khoa"]["facebook"]["bo_tu"] == [
        "Yêu từ điều nhỏ nhất", "hapas sale"]
    dang_nhap(c, XEM)
    t = c.get("/ngan-sach").text
    assert 'name="tk_facebook_bo_tu"' not in t and "Yêu từ điều nhỏ nhất, hapas sale" in t


_DOM_GIA = r"""
var outs = {};
function phanTu(ten) {
  return outs[ten] || (outs[ten] = {textContent: "", thuoc: {}, hidden: false, disabled: false,
    setAttribute: function (k, v) { this.thuoc[k] = String(v); },
    getAttribute: function (k) { return this.thuoc[k] == null ? null : this.thuoc[k]; },
    classList: {toggle: function () {}}});
}
var o = INPUTS.map(function (x) {
  return {name: x.name, type: x.type, value: x.value, checked: x.checked,
          setCustomValidity: function () {}};
});
o.namedItem = function (ten) { return o.filter(function (e) { return e.name === ten; })[0] || null; };
var form = {elements: o, setAttribute: function () {}, addEventListener: function () {},
  querySelector: function (s) { var m = /data-o="([^"]+)"/.exec(s); return m ? phanTu(m[1]) : null; },
  querySelectorAll: function () { return []; }};
var document = {getElementById: function (id) {
  return id === "ns-form" ? form : id === "ns-du-lieu" ? {textContent: JSON.stringify(DU_LIEU)} : null; }};
var window = {addEventListener: function () {}, setTimeout: function (f) { f(); }};
"""


def test_ngan_sach_js_ca_trang_khop_may_chu_khi_co_bo_tu(tmp_path):
    """Chạy TRỌN ngan_sach.js (DOM giả dựng từ trang thật): ô USD từng nền tảng, số cụm / hashtag,
    số từ khoá tìm đúng bằng số máy chủ dựng khi dự án có "Không tìm trên…"."""
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    from test_dashboard_app import QL, GiaKho, dang_nhap, tao
    kho = GiaKho()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15, tu_khoa=TU, cau_hinh=DA["cau_hinh"])
    _, c, _ = tao(kho)
    dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    du_lieu = json.loads(re.search(r'id="ns-du-lieu">(.*?)</script>', t, re.DOTALL).group(1))
    o = []
    for the in re.findall(r"<input\b[^>]*>", t):
        ten = re.search(r'name="([^"]+)"', the)
        if not ten:
            continue
        gt = re.search(r'value="([^"]*)"', the)
        o.append({"name": ten.group(1), "type": re.search(r'type="([^"]+)"', the).group(1),
                  "value": gt.group(1) if gt else "", "checked": " checked" in the})
    js = (Path(__file__).resolve().parents[1] / "dashboard" / "static" / "ngan_sach.js").read_text(
        encoding="utf-8")
    import html
    for x in o:
        x["value"] = html.unescape(x["value"])
    chay = (f"var INPUTS = {json.dumps(o, ensure_ascii=False)};\n"
            f"var DU_LIEU = {json.dumps(du_lieu, ensure_ascii=False)};\n" + _DOM_GIA + js +
            "\nvar ra = {}; Object.keys(outs).forEach(function (k) { ra[k] = [outs[k].textContent, "
            "outs[k].thuoc['data-usd'] == null ? null : Number(outs[k].thuoc['data-usd'])]; });\n"
            "console.log(JSON.stringify(ra));\n")
    f = tmp_path / "trang.js"
    f.write_text(chay, encoding="utf-8")
    ra = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True,
                                   encoding="utf-8", check=True, timeout=30).stdout)
    may_chu = {k: float(v) for k, v in re.findall(r'data-o="((?:tk|bl)-\w+)" data-usd="([0-9.e-]+)"',
                                                   t)}
    for k, v in may_chu.items():
        assert ra[k][1] == pytest.approx(v, abs=1e-4), k
    for k in ("fb2-so-cum", "tt-tag-so", "web-so-tu", *(f"bo-tu-{p}" for p in CP.NEN_TANG)):
        assert ra[k][0] == re.search(rf'data-o="{k}"[^>]*>([^<]*)<', t).group(1), k
    assert ra["bo-tu-facebook"][0] == "tìm 5/6 từ khoá" and ra["fb2-so-cum"][0] == "2"


def test_ngan_sach_js_bo_tu_khop_python(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    js = (Path(__file__).resolve().parents[1] / "dashboard" / "static" / "ngan_sach.js").read_text(
        encoding="utf-8")
    khoi = re.search(r"// <bo_tu>.*?// </bo_tu>", js, re.DOTALL).group(0)
    ca = []
    for da in (DA, {**DA, "hashtag": ["hapas", "quatang2010", "sanhyeuchieu"]}):
        bo = {p: CP.bo_tu(da, p) for p in CP.NEN_TANG}
        tag_da = CP.nguon_tag(da, [])
        ca.append((bo, tag_da, {p: [CP.tu_nen_tang(da, p, TU), CP.tag_cua(da, p, TU)]
                                for p in CP.NEN_TANG}))
    chay = ("var form = null;\n"
            "function norm(s) { return String(s || '').replace(/đ/g, 'd').replace(/Đ/g, 'D')"
            ".normalize('NFD').replace(/\\p{Mn}/gu, '').toLowerCase(); }\n"
            "function tagIg(s) { return norm(s).replace(/[^a-z0-9_]/g, ''); }\n"
            f"var TU = {json.dumps(TU, ensure_ascii=False)};\nvar D, TAG_DA;\n" + khoi +
            f"\nvar ca = {json.dumps(ca, ensure_ascii=False)};\n"
            "console.log(JSON.stringify(ca.map(function (c) { D = {bo_tu: c[0]}; TAG_DA = c[1];\n"
            "  var r = {}; Object.keys(c[0]).forEach(function (p) { r[p] = [tuP(p), tagP(p)]; });\n"
            "  return r; })));\n")
    f = tmp_path / "bo_tu.js"
    f.write_text(chay, encoding="utf-8")
    ra = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True,
                                   encoding="utf-8", check=True, timeout=30).stdout)
    assert ra == [x[2] for x in ca]
