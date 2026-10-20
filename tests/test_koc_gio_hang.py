"""KOC affiliate (gắn giỏ) vs KOC branding (20/10/2026, task Lark t284905, chủ dự án duyệt PA1).

Marketing: "đang bị lẫn KOC branding và KOC aff → tiêu chí: KOC branding không gắn giỏ hàng ><
KOC aff có gắn giỏ". Canh cả đường đi của cờ giỏ TikTok Shop:
  • schema Postgres + BigQuery có hai cột (`bai.gio_hang`, `bai.la_quang_cao`), đồng bộ tuỳ chọn;
  • lúc cào → dòng ghi kho: chỉ TikTok, chỉ giá trị bool (nguồn không báo = None, không đoán);
  • ghi kho: TRUE dính, FALSE chỉ điền chỗ NULL, NULL không đè (`_GOP_CO`) — cả upsert lẫn đường
    chỉ cập nhật số; dòng không mang cờ ghi đúng câu lệnh cũ (không hỏi DB thêm);
  • script bù từ raw đã trả tiền: chạy thử không ghi, `--ghi` ghi + sao lưu, đường API trả tiền
    chỉ khi có `--goi-api --toi-da-usd`;
  • dashboard: xếp theo TỪNG video, bộ lọc "Loại KOC" áp mọi khối (bình luận theo bài), khối
    Kênh & Nguồn, chip lọc nhanh; Mark (`hoi_dashboard`) trả phần `koc`.
Không Postgres, không mạng."""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys

import pytest

import apify_tool as A
import lang_nghe_db as K
import theo_doi_api as TDA
import tiktok_api as TT
from dashboard import chi_so as CS
from dashboard import dong_bo_bq as D

GOC = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC / "scripts"))
import lang_nghe_nap_gio_hang as G  # noqa: E402

VN = datetime.timezone(datetime.timedelta(hours=7))


def _aweme(vid: str, anchors="khong", is_ads=False, ten="koc_a") -> dict:
    a = {"aweme_id": vid, "desc": "túi hapas", "create_time": 1760000000,
         "author": {"uid": "1", "unique_id": ten, "nickname": ten, "follower_count": 1000},
         "statistics": {"play_count": 100, "digg_count": 5, "comment_count": 2, "share_count": 1}}
    if anchors != "khong":
        a["anchors"] = anchors
    if is_ads is not None:
        a["is_ads"] = is_ads
    return a


SHOP = [{"component_key": "anchor_complex_shop"}]
KHAC = [{"component_key": "anchor_music"}]


# ───────────────────────────── schema ─────────────────────────────
def test_schema_postgres_bigquery_va_dong_bo():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    for c in ("gio_hang", "la_quang_cao"):
        assert f"ALTER TABLE bai ADD COLUMN IF NOT EXISTS {c} BOOLEAN;" in sql
        assert re.search(rf"COMMENT ON COLUMN bai\.{c} IS '[^']*NULL", sql), c
        khoi = re.search(r"CREATE TABLE IF NOT EXISTS bai \((.*?)\n\);", sql, re.DOTALL).group(1)
        assert re.search(rf"^\s+{c}\s+BOOLEAN,", khoi, re.MULTILINE)
    assert "GRANT SELECT, INSERT, UPDATE ON bai" in sql        # quyền cả bảng, không theo cột
    bq = (GOC / "deploy" / "lang-nghe" / "bigquery.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS gio_hang BOOL" in bq
    assert "ADD COLUMN IF NOT EXISTS la_quang_cao BOOL" in bq
    cot = dict(D.BANG["bai"]["cot"])
    assert cot["gio_hang"] == cot["la_quang_cao"] == "BOOL"
    assert set(D.BANG["bai"]["tuy_chon"]) == {"gio_hang", "la_quang_cao"}


# ───────────────────────────── lúc cào ─────────────────────────────
def test_co_tu_tiktok_api_toi_dong_kho():
    raw = [_aweme("7001", SHOP, True), _aweme("7002", KHAC, False), _aweme("7003", None, None)]
    rows = A._chuan_tiktok(A._chuan_clockworks([TT.video(a) for a in raw]))
    co = [(d["gio_hang"], d["la_quang_cao"]) for d, _ in rows]
    assert co == [(True, True), (False, False), (None, None)]   # thiếu anchors / is_ads: None
    assert K.co_tiktok({"platform": "tiktok", **rows[0][0]}) == {"gio_hang": True,
                                                                 "la_quang_cao": True}
    assert K.co_tiktok({"platform": "tiktok", "gio_hang": None, "la_quang_cao": None}) == {}
    assert K.co_tiktok({"platform": "facebook", "gio_hang": True}) == {}
    # clockworks dự phòng: isAd nằm trong danh sách trường việc nền đọc (`fields=`)
    assert "isAd" in A._TRUONG_ACTOR["clockworks~tiktok-hashtag-scraper"]


def test_tach_da_biet_mang_co_cho_bai_da_co(monkeypatch):
    monkeypatch.setattr(K, "khoa_da_co", lambda ma, ks: set(ks))
    d = {"platform": "tiktok", "link": "https://www.tiktok.com/@a/video/1", "views": 5,
         "gio_hang": True, "la_quang_cao": None}
    cap, moi, _ = TDA.tach_da_biet("hapas", [(d, None)], lambda x: "tiktok:1")
    assert not moi and cap[0]["gio_hang"] is True and "la_quang_cao" not in cap[0]


# ───────────────────────────── ghi kho ─────────────────────────────
def _ba_tri(cu, moi):
    """Logic ba trị của Postgres cho `_GOP_CO` = COALESCE(cu OR moi, cu, moi)."""
    hoac = True if (cu is True or moi is True) else (None if cu is None or moi is None else False)
    return next((x for x in (hoac, cu, moi) if x is not None), None)


@pytest.mark.parametrize("cu,moi,ky_vong", [(None, False, False), (None, True, True),
                                            (False, True, True), (True, False, True),
                                            (False, None, False), (True, None, True),
                                            (None, None, None), (False, False, False)])
def test_gop_co_true_dinh_null_khong_de(cu, moi, ky_vong):
    assert _ba_tri(cu, moi) == ky_vong == G.gop(cu, moi)
    assert K._GOP_CO.format(cu="a", moi="b") == "COALESCE(a OR b, a, b)"


class Kho:
    """Kết nối giả: ghi lại câu lệnh; information_schema trả `co_cot`."""

    def __init__(self, co_cot=True, doi=True):
        self.cau: list[tuple[str, list]] = []
        self.co_cot, self.doi = co_cot, doi
        self._kq = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, ts=()):
        self.cau.append((sql, dict(ts) if isinstance(ts, dict) else list(ts or [])))
        if "information_schema" in sql:
            self._kq = {"co": 1} if self.co_cot else None
        elif sql.startswith("INSERT INTO bai"):
            self._kq = {"moi": True, "xem": 1, "thich": 1, "binh_luan": 1, "chia_se": 1}
        elif sql.startswith("UPDATE bai SET gio_hang") or sql.startswith("UPDATE bai SET la_"):
            self._kq = {"khoa": "x"} if self.doi else None
        elif sql.startswith("UPDATE bai SET"):
            self._kq = {"khoa": "tiktok:1", "xem": 1, "thich": 1, "binh_luan": 1, "chia_se": 1}
        else:
            self._kq = None
        return self

    def fetchone(self):
        return self._kq


@pytest.fixture
def kho(monkeypatch):
    def tao(**kw):
        k = Kho(**kw)
        monkeypatch.setattr(K, "ket_noi", lambda: k)
        monkeypatch.setattr(K, "_CO_COT", set())
        monkeypatch.setattr(K, "_KHONG_CO", {})
        return k
    return tao


def _dong(**kw):
    return {"khoa": "tiktok:1", "nen_tang": "tiktok", "nguon_id": None, "link": "l", "tac_gia": "",
            "tai_khoan": "a", "followers": None, "dang_luc": None, "noi_dung": "", "hashtag": "",
            "khop_tu_khoa": True, "sac_thai": None, "chu_de": None, "ly_do_giu": "x", "xem": 1,
            "thich": 1, "binh_luan": 1, "chia_se": 1, **kw}


def test_ghi_bai_luu_co_va_gop_khi_trung(kho):
    k = kho()
    K.ghi_bai("hapas", 1, "tu_khoa", [_dong(gio_hang=False, la_quang_cao=False)])
    sql, ts = next(x for x in k.cau if x[0].startswith("INSERT INTO bai"))
    assert "gio_hang, la_quang_cao" in sql and ts[-2:] == [False, False]
    assert "gio_hang = COALESCE(bai.gio_hang OR EXCLUDED.gio_hang, bai.gio_hang, " \
           "EXCLUDED.gio_hang)" in sql


def test_ghi_bai_khong_co_thi_cau_cu_khong_hoi_db(kho):
    k = kho()
    K.ghi_bai("hapas", 1, "tu_khoa", [_dong()])
    assert not any("information_schema" in s for s, _ in k.cau)
    assert all("gio_hang" not in s for s, _ in k.cau)


def test_db_chua_co_cot_van_ghi_bai(kho):
    k = kho(co_cot=False)
    K.ghi_bai("hapas", 1, "tu_khoa", [_dong(gio_hang=True)])
    sql = next(s for s, _ in k.cau if s.startswith("INSERT INTO bai"))
    assert "gio_hang" not in sql


def test_cap_nhat_so_dien_co_bai_da_co(kho):
    k = kho()
    K.cap_nhat_so_lieu("hapas", 1, [{"khoa": "tiktok:1", "xem": 9, "gio_hang": True}])
    sql, ts = next(x for x in k.cau if x[0].startswith("UPDATE bai SET gio_hang"))
    assert "IS DISTINCT FROM" in sql and ts["gio_hang"] is True and "cap_nhat_cuoi = now()" in sql
    assert "la_quang_cao" not in sql                    # dòng không mang cờ quảng cáo
    # nang_so_lieu (số cũ của raw): không có số nào vẫn điền cờ
    k.cau.clear()
    K.nang_so_lieu("hapas", 1, [{"khoa": "tiktok:1", "gio_hang": False}], datetime.date.today())
    assert any(s.startswith("UPDATE bai SET gio_hang") for s, _ in k.cau)


# ───────────────────────────── script bù ─────────────────────────────
def _raw(tmp_path) -> pathlib.Path:
    d = tmp_path / "raw"
    d.mkdir()
    dong = [
        {"loai": "searchPosts", "item": {"search_item_list": [
            {"aweme_info": _aweme("7101", SHOP)}, {"aweme_info": _aweme("7102", KHAC)}]}},
        # feed hashtag: cùng video 7101 báo "không giỏ" — không hạ TRUE
        {"loai": "challengePosts", "tag": "hapas", "item": {"aweme_list": [
            _aweme("7101", KHAC), _aweme("7103", None)]}},
    ]
    (d / "raw_tt_thu.jsonl").write_text("\n".join(json.dumps(x) for x in dong), encoding="utf-8")
    (d / "raw_tt_epctex_x.json").write_text(json.dumps({"actor": "epctex/tiktok-search-scraper",
                                                        "items": []}), encoding="utf-8")
    return d


def test_doc_raw_gop_co_moi_video(tmp_path):
    r = G.doc_co_raw([str(_raw(tmp_path))])
    co = r["co"]
    assert co["tiktok:7101"]["gio_hang"] is True
    assert co["tiktok:7102"]["gio_hang"] is False
    assert co["tiktok:7103"]["gio_hang"] is None
    assert r["ban_doc"] == 4 and any("epctex" in ly for _, ly in r["bo_qua"])


BAI_KHO = [{"khoa": "tiktok:7101", "link": "https://www.tiktok.com/@a/video/7101",
            "gio_hang": None, "la_quang_cao": None},
           {"khoa": "tiktok:7102", "link": "u2", "gio_hang": True, "la_quang_cao": None},
           {"khoa": "tiktok:7103", "link": "u3", "gio_hang": None, "la_quang_cao": None},
           {"khoa": "tiktok:9999", "link": "u4", "gio_hang": None, "la_quang_cao": None}]


def _ns(tmp_path, *them):
    ap = ["hapas", str(_raw(tmp_path)), *them]
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("du_an")
    p.add_argument("duong", nargs="*")
    p.add_argument("--ghi", action="store_true")
    p.add_argument("--sao-luu")
    p.add_argument("--goi-api", action="store_true")
    p.add_argument("--toi-da-usd", type=float)
    return p.parse_args(ap)


def test_chay_thu_chi_dem_khong_ghi(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "bai_tiktok_co", lambda ma: [dict(b) for b in BAI_KHO])
    ghi = []
    monkeypatch.setattr(K, "ghi_co_tiktok_lo", lambda ma, cac: ghi.append(cac) or len(cac))
    out: list[str] = []
    assert G.chay(_ns(tmp_path), out.append) == 0
    chu = "\n".join(out)
    assert not ghi
    # 7101 → TRUE (+ quảng cáo FALSE); 7102 đã TRUE không hạ (chỉ điền quảng cáo FALSE);
    # 7103 và 9999 còn NULL
    assert "3 khớp raw" in chu and "giỏ hàng TRUE 1, FALSE 0" in chu
    assert "còn NULL giỏ hàng sau bước này: 2" in chu
    assert f"{2 * TT.GIA_YEU_CAU:.4f} USD" in chu and "--goi-api" in chu


def test_ghi_co_sao_luu_va_khong_goi_api(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "bai_tiktok_co", lambda ma: [dict(b) for b in BAI_KHO])
    ghi = []
    monkeypatch.setattr(K, "ghi_co_tiktok_lo", lambda ma, cac: ghi.extend(cac) or len(cac))
    monkeypatch.setattr(G, "goi_api", lambda *a, **k: pytest.fail("không được gọi API trả tiền"))
    sl = tmp_path / "sl.jsonl"
    assert G.chay(_ns(tmp_path, "--ghi", "--sao-luu", str(sl)), lambda s: None) == 0
    theo = {r["khoa"]: r for r in ghi}
    assert theo["tiktok:7101"] == {"khoa": "tiktok:7101", "gio_hang": True, "la_quang_cao": False}
    assert "gio_hang" not in theo["tiktok:7102"]           # TRUE đã có: không ghi lại
    dong = [json.loads(x) for x in sl.read_text(encoding="utf-8").splitlines()]
    assert {x["khoa"] for x in dong} == set(theo) and dong[0]["cu"]["gio_hang"] is None


def test_goi_api_can_tran_va_ghi(capsys):
    for thieu in (["--goi-api", "--ghi", "--sao-luu", "x"], ["--goi-api", "--toi-da-usd", "1"]):
        with pytest.raises(SystemExit):
            G.main(["hapas", *thieu])


def test_goi_api_kep_tran_va_vao_luot(monkeypatch):
    import quet_lon
    monkeypatch.setattr(K, "doc_du_an", lambda ma: {"tran_usd_thang": 5})
    monkeypatch.setattr(K, "da_tieu_thang", lambda ma: 0.0)
    monkeypatch.setattr(quet_lon, "ngan_sach", lambda t: (1.0, None, ""))
    monkeypatch.setattr(quet_lon, "tran_usd_nen", lambda: 1.0)
    monkeypatch.setenv("APIFY_TOKEN", "x")
    monkeypatch.setattr(K, "luot_dang_chay", lambda ma: None)
    monkeypatch.setattr(K, "mo_luot", lambda *a, **k: 77)
    dong = {}
    monkeypatch.setattr(K, "dong_luot", lambda luot, **k: dong.update(k, luot=luot))
    gui = []

    def so_lieu(urls, tran_usd=None):
        gui.append((list(urls), tran_usd))
        A._SO_RUN.get().append({"run_id": "r1"})
        return [TT.video(_aweme("7101000001", SHOP))]
    monkeypatch.setattr(TT, "so_lieu_bai", so_lieu)
    cap = []
    monkeypatch.setattr(K, "cap_nhat_so_lieu", lambda ma, luot, rows: cap.extend(rows) or len(rows))
    bai = [{"khoa": "tiktok:7101000001", "link": "https://www.tiktok.com/@a/video/7101000001"},
           {"khoa": "tiktok:7102000002", "link": "https://www.tiktok.com/@a/video/7102000002"}]
    rows, tk = G.goi_api("hapas", bai, 0.002, lambda s: None, datetime.datetime.now(VN))
    assert len(gui[0][0]) == 1 and gui[0][1] == pytest.approx(TT.GIA_YEU_CAU)   # trần 1 video
    assert cap[0]["gio_hang"] is True and tk["usd"] == pytest.approx(TT.GIA_YEU_CAU)
    assert dong["luot"] == 77 and dong["chi_phi_usd"] == pytest.approx(TT.GIA_YEU_CAU)


# ───────────────────────────── dashboard ─────────────────────────────
def _bai(khoa, **kw):
    return {"khoa": khoa, "nen_tang": "tiktok", "nguon_id": None, "kieu_quet": "tu_khoa",
            "tai_khoan": khoa, "tac_gia": khoa, "link": "", "dang_luc":
            datetime.datetime(2026, 10, 10, 9, tzinfo=VN), "sac_thai": "Tích cực", "xem": 100,
            "thich": 10, "binh_luan": 5, "chia_se": 1, "nguon_loai": None, **kw}


BAI = [_bai("tiktok:1", gio_hang=True, la_quang_cao=True), _bai("tiktok:2", gio_hang=True),
       _bai("tiktok:3", gio_hang=False, sac_thai="Tiêu cực"), _bai("tiktok:4"),
       _bai("tiktok:5", gio_hang=True, nguon_id=9, nguon_loai="kenh_nha"),
       _bai("facebook:6", nen_tang="facebook")]


def test_xep_theo_tung_video():
    assert [CS.nhom_koc(r) for r in BAI] == ["affiliate", "affiliate", "branding", "chua_ro",
                                            None, None]


def test_bo_loc_koc_ap_bai_va_binh_luan():
    b = CS.doc_bo_loc({"koc": "affiliate"})
    assert b["koc"] == ("affiliate",)
    with pytest.raises(CS.LoiBoLoc):
        CS.doc_bo_loc({"koc": "viral"})
    assert [r["khoa"] for r in CS.loc_bai(BAI, b)] == ["tiktok:1", "tiktok:2"]
    assert CS.can_tra_bai(b)                             # bình luận theo bài gốc
    bl = [{"khoa_bai": "tiktok:1", "nen_tang": "tiktok", "nguon_id": None, "loai": "hop_le"},
          {"khoa_bai": "tiktok:3", "nen_tang": "tiktok", "nguon_id": None, "loai": "hop_le"},
          {"khoa_bai": "tiktok:x", "nen_tang": "tiktok", "nguon_id": None, "loai": "hop_le"}]
    giu = CS.loc_bl(bl, b, CS.chi_muc_bai(BAI))
    assert [c["khoa_bai"] for c in giu] == ["tiktok:1"]  # thiếu bài gốc: không đoán


def test_khoi_kenh_nguon_va_dem_o_loc():
    d = CS.tong_quan_loc(BAI, [], datetime.date(2026, 10, 1), datetime.date(2026, 10, 31),
                         CS.doc_bo_loc({"koc": "branding"}))
    assert d["bo_loc_dem"]["koc"] == {"affiliate": 2, "branding": 1, "chua_ro": 1}
    x = d["loai_koc"]
    # HAI nhóm (chủ dự án 20/10 tối); video NULL là dòng mờ `chua_doc_lai`, không phải thẻ
    assert [g["ma"] for g in x["nhom"]] == ["affiliate", "branding"]
    assert x["tong"]["bai"] == 3 and x["chua_doc_lai"] == 1    # bỏ kênh nhà + Facebook
    aff = next(g for g in x["nhom"] if g["ma"] == "affiliate")
    assert aff["bai"] == 2 and aff["nguoi"] == 2 and aff["quang_cao"] == 1
    assert aff["bai_pt"] == 66.7 and aff["xem"] == 200 and aff["tuong_tac"] == 32
    br = next(g for g in x["nhom"] if g["ma"] == "branding")
    assert br["sac_bai"]["tieu_cuc"] == 1
    # chiều khác vẫn áp: lọc Facebook thì không còn video TikTok nào
    d2 = CS.tong_quan_loc(BAI, [], datetime.date(2026, 10, 1), datetime.date(2026, 10, 31),
                          CS.doc_bo_loc({"nen_tang": "facebook"}))
    assert d2["loai_koc"]["tong"]["bai"] == 0


def test_chip_nhanh_va_nhan_va_the_bai():
    chip = {x["ma"]: x for x in CS.BO_LOC_NHANH}
    assert CS.doc_bo_loc(chip["koc_aff"]["loc"])["koc"] == ("affiliate",)
    assert CS.doc_bo_loc(chip["koc_brand"]["loc"])["koc"] == ("branding",)
    assert CS.NHAN_BO_LOC["koc"] == CS.KOC
    assert CS._the_bai(BAI[0])["koc"] == "affiliate" and CS._the_bai(BAI[5])["koc"] is None


def test_trang_co_khoi_va_o_loc():
    html = (GOC / "dashboard" / "templates" / "chi_so.html").read_text(encoding="utf-8")
    assert 'id="khoi-koc"' in html and 'id="loai-koc"' in html and "Theo từng video" in html
    assert 'id="koc-chua"' in html and "tổng hai nhóm" in html
    assert html.count("cs-khung-cho--nn", html.index('id="loai-koc"'),
                      html.index('id="koc-chua"')) == 2
    js = (GOC / "dashboard" / "static" / "chi_so.js").read_text(encoding="utf-8")
    assert '"kieu_trang", "koc", "y_dinh"' in js and "function veKoc(" in js
    assert '{ k: "koc", ten: "Loại KOC"' in js and "veKoc(d)" in js
    assert 'k === "koc" && gt === "chua_ro"' in js and "chưa đọc lại được giỏ" in js
    css = (GOC / "dashboard" / "static" / "chi_so.css").read_text(encoding="utf-8")
    assert ".cs-koc__luoi" in css


def test_api_va_kho_doc_cot(monkeypatch):
    from dashboard import kho as KD
    monkeypatch.setattr(KD, "_CO_CO_TT", [])
    monkeypatch.setattr(KD, "_KHONG_CO_TT", [])

    class C:
        def __init__(self, n):
            self.n = n

        def execute(self, sql, ts=()):
            return self

        def fetchone(self):
            return {"n": self.n}
    assert "NULL::boolean AS gio_hang" in KD._cot_co_tiktok(C(0))      # DB chưa chạy schema
    KD._KHONG_CO_TT.clear()                     # (bình thường: hỏi lại sau `_KHONG_CO_GIAY`)
    assert KD._cot_co_tiktok(C(2)) == ", b.gio_hang, b.la_quang_cao" and KD._CO_CO_TT


# ───────────────────────────── Mark: hoi_dashboard ─────────────────────────────
def test_hoi_dashboard_tra_phan_koc():
    import hoi_dashboard_tool as HD
    from test_hoi_dashboard import _kho_mau
    kho = _kho_mau()
    d = HD.tinh_chi_so(kho, kho.doc_du_an("hapas"), datetime.date(2026, 10, 8),
                       datetime.date(2026, 10, 14), CS.doc_bo_loc({}), datetime.date(2026, 10, 17))
    ra = HD.rut_gon(d, ["koc", "bo_loc", "bai"], 5)
    nhom = {g["ma"]: g for g in ra["koc"]["nhom"]}
    assert set(nhom) == {"affiliate", "branding"}
    assert nhom["affiliate"]["bai"] == 1 and nhom["branding"]["bai"] == 1
    assert ra["koc"]["chua_doc_lai_duoc"] == 1            # tiktok:6 không có cờ
    assert "TỪNG video" in ra["koc"]["quy_tac"] and ra["bo_loc"]["koc"]["affiliate"] == 1
    assert any(b.get("loai_koc") == CS.KOC["affiliate"] for b in ra["bai"]["top"])
    assert "koc" in HD.PHAN and "koc" in HD._PHAN_SO_LIEU
    assert "koc: affiliate,branding " in json.dumps(HD.SCHEMA, ensure_ascii=False)


# ───────────────────────────── soát 21/10/2026: cờ theo loại phản hồi ─────────────────────────────
@pytest.mark.parametrize("nguon,anchors,ky_vong", [
    (TT.FEED, SHOP, True), (TT.FEED, KHAC, None), (TT.FEED, None, None), (TT.FEED, "khong", None),
    (TT.DAY_DU, SHOP, True), (TT.DAY_DU, KHAC, False), (TT.DAY_DU, None, False),
    (TT.DAY_DU, "khong", False),
    (TT.CHI_TIET, SHOP, True), (TT.CHI_TIET, KHAC, False), (TT.CHI_TIET, None, None)])
def test_co_gio_theo_loai_phan_hoi(nguon, anchors, ky_vong):
    assert TT.video(_aweme("7201000001", anchors), nguon)["hasTikTokShopProduct"] is ky_vong


def test_nap_raw_feed_khong_bao_gio_ra_false(tmp_path):
    import lang_nghe_nap_raw as N
    dong = [{"loai": "challengePosts", "tag": "hapas", "item": {"aweme_list": [
                _aweme("7301000001", KHAC), _aweme("7301000002", SHOP)]}},
            {"loai": "searchPosts", "item": {"search_item_list": [
                {"aweme_info": _aweme("7301000003", None)}]}},
            {"loai": "userPosts", "item": {"aweme_list": [_aweme("7301000004")]}}]
    f = tmp_path / "raw_tt_x.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in dong), encoding="utf-8")
    tim, ho_so = N._tiktok(f)
    co = {d["link"].rsplit("/", 1)[-1]: d["gio_hang"] for d, _ in tim + ho_so}
    assert co == {"7301000001": None, "7301000002": True, "7301000003": False,
                  "7301000004": False}


def test_clockworks_hashtag_chi_tin_true():
    ra = A.chi_tin_gio_true([{"hasTikTokShopProduct": False}, {"hasTikTokShopProduct": True},
                             {}])
    assert [x["hasTikTokShopProduct"] for x in ra] == [None, True, None]


@pytest.mark.parametrize("giu,bo,ky_vong", [(None, False, False), (False, True, True),
                                            (True, None, True), (False, None, False),
                                            (None, None, None)])
def test_gop_duong_gop_co(giu, bo, ky_vong):
    a = {"platform": "tiktok", "gio_hang": giu}
    TDA.gop_duong(a, {"platform": "tiktok", "gio_hang": bo})
    assert a.get("gio_hang") is ky_vong


def test_nho_cau_tra_loi_chua_co_cot(kho, monkeypatch):
    k = kho(co_cot=False)
    gio = [1000.0]
    monkeypatch.setattr(K.time, "monotonic", lambda: gio[0])
    monkeypatch.setattr(K, "_KHONG_CO", {})
    assert not K._co_cot(k, "gio_hang") and not K._co_cot(k, "gio_hang")
    assert sum("information_schema" in s for s, _ in k.cau) == 1
    gio[0] += K._KHONG_CO_GIAY + 1
    k.co_cot = True
    assert K._co_cot(k, "gio_hang")
    from dashboard import kho as KD
    monkeypatch.setattr(KD, "_CO_CO_TT", [])
    monkeypatch.setattr(KD, "_KHONG_CO_TT", [])
    monkeypatch.setattr(KD.time, "monotonic", lambda: gio[0])
    hoi = []

    class C:
        def execute(self, sql, ts=()):
            hoi.append(sql)
            return self

        def fetchone(self):
            return {"n": 0}
    assert not KD._co_co_tiktok(C()) and not KD._co_co_tiktok(C()) and len(hoi) == 1


# ───────────────────────────── đọc hồ sơ nhà sáng tạo (21/10/2026) ─────────────────────────────
class GiaTT:
    """Giả `tiktok_api._goi`: hồ sơ trả uid, userPosts trả trang theo con trỏ. Mỗi lời gọi ghi
    run id vào `A._SO_RUN` như `_call` thật."""

    def __init__(self, trang: dict[str, list[list[dict]]], loi: set[str] = frozenset()):
        self.trang, self.loi, self.goi = trang, set(loi), []

    def __call__(self, payload, ngan):
        if not ngan.xin():
            return None
        self.goi.append(payload)
        so = A._SO_RUN.get(None)
        if so is not None:
            so.append({"run_id": f"r{len(self.goi)}"})
        if "profile_username" in payload:
            ten = payload["profile_username"]
            if ten in self.loi:
                raise A.LoiApify("LOI", "riêng tư")
            return {"user": {"uid": f"u-{ten}"}}
        ten = payload["userPosts_userId"][2:]
        i = int(payload["userPosts_maxCursor"] or 0)
        ds = self.trang.get(ten) or []
        if i >= len(ds):
            return {"aweme_list": [], "has_more": False}
        return {"aweme_list": ds[i], "has_more": i + 1 < len(ds), "max_cursor": str(i + 1)}


def _a(vid, ngay, anchors="khong", top=False, ten="a"):
    a = _aweme(vid, anchors, ten=ten)
    a["create_time"] = int(datetime.datetime(2026, 10, ngay, tzinfo=VN).timestamp())
    if top:
        a["is_top"] = 1
    return a


def _bn(ten, vid, ngay=10):
    return {"khoa": f"tiktok:{vid}", "tai_khoan": ten, "dang_luc":
            datetime.datetime(2026, 10, ngay, tzinfo=VN),
            "link": f"https://www.tiktok.com/@{ten}/video/{vid}"}


def test_nhom_ho_so_nhieu_video_truoc():
    bai = [_bn("b", "8000000001"), _bn("a", "8000000002"), _bn("a", "8000000003"),
           {"khoa": "tiktok:x", "tai_khoan": "", "link": "https://www.tiktok.com/@c/video/8000000004"},
           {"khoa": "tiktok:y", "tai_khoan": "d", "link": "khong-co-id"}]
    nhom = TDA.nhom_ho_so(bai)
    assert [(t, len(d)) for t, d in nhom] == [("a", 2), ("b", 1), ("c", 1)]
    assert TDA.uoc_ho_so(3) == 12                         # 1 hồ sơ + 3 trang mỗi tài khoản


def test_doc_ho_so_lat_trang_tim_thay_va_bonus(monkeypatch):
    gia = GiaTT({
        # a: trang 1 có video ghim (cần tìm) + bonus; trang 2 có video cần tìm còn lại → dừng
        "a": [[_a("8100000001", 20, SHOP, top=True), _a("8100000009", 19, KHAC)],
              [_a("8100000002", 12, None)], [_a("8100000003", 1)]],
        # b: video cần tìm không có (xoá) — dừng khi video cũ hơn video cần tìm
        "b": [[_a("8200000005", 15)], [_a("8200000006", 2)], [_a("8200000007", 1)]]})
    monkeypatch.setattr(TT, "_goi", gia)
    bai = [_bn("a", "8100000001"), _bn("a", "8100000002", 12), _bn("b", "8200000001", 10)]
    rows, tk = TDA.doc_ho_so_gio(bai, 1.0)
    co = {r["khoa"]: r.get("gio_hang") for r in rows}
    assert co["tiktok:8100000001"] is True and co["tiktok:8100000002"] is False
    assert co["tiktok:8100000009"] is False               # bonus: video khác của tài khoản
    assert "tiktok:8100000003" not in co                  # đủ video cần tìm thì thôi lật
    assert "tiktok:8200000007" not in co                  # cũ hơn video cần tìm thì thôi lật
    assert tk["thay"] == 2 and tk["khong_doc_duoc"] == 1 and tk["tai_khoan"] == 2
    assert tk["yeu_cau"] == len(gia.goi) == 6 and tk["usd"] == pytest.approx(6 * TT.GIA_YEU_CAU)


def test_doc_ho_so_kep_tran_tai_khoan_nhieu_video_truoc(monkeypatch):
    gia = GiaTT({"a": [[_a("8100000001", 10)]], "b": [[_a("8200000001", 10)]]})
    monkeypatch.setattr(TT, "_goi", gia)
    bai = [_bn("b", "8200000001"), _bn("a", "8100000001"), _bn("a", "8100000002")]
    rows, tk = TDA.doc_ho_so_gio(bai, 3 * TT.GIA_YEU_CAU)
    assert [p.get("profile_username") for p in gia.goi if "profile_username" in p] == ["a"]
    assert tk["yeu_cau"] == 2 and tk["khong_doc_duoc"] == 2   # b không đủ trần: giữ NULL


def test_doc_ho_so_loi_mot_tai_khoan_khong_dung_ca_luot(monkeypatch):
    gia = GiaTT({"b": [[_a("8200000001", 10, SHOP)]]}, loi={"a"})
    monkeypatch.setattr(TT, "_goi", gia)
    rows, tk = TDA.doc_ho_so_gio([_bn("a", "8100000001"), _bn("a", "8100000002"),
                                  _bn("b", "8200000001")], 1.0)
    assert [r["khoa"] for r in rows] == ["tiktok:8200000001"] and tk["khong_doc_duoc"] == 2


def test_script_doc_ho_so_chay_thu_khong_goi_api(tmp_path, monkeypatch):
    bai = [dict(_bn("a", "8100000001"), gio_hang=None, la_quang_cao=None),
           dict(_bn("a", "8100000002"), gio_hang=None, la_quang_cao=None),
           dict(_bn("b", "8200000001"), gio_hang=True, la_quang_cao=False)]
    monkeypatch.setattr(K, "bai_tiktok_co", lambda ma: [dict(b) for b in bai])
    monkeypatch.setattr(TT, "_goi", lambda *a, **k: pytest.fail("chạy thử không được gọi API"))
    monkeypatch.setattr(K, "mo_luot", lambda *a, **k: pytest.fail("chạy thử không mở lượt"))
    out: list[str] = []
    G.chay(_ns_hs(["--doc-ho-so", "--toi-da-usd", "0.008"]), out.append)
    chu = "\n".join(out)
    assert "1 tài khoản, 2 video cần tìm, tối đa 4 yêu cầu" in chu and "@a: 2 video" in chu
    assert "trần --toi-da-usd đủ cho 1 tài khoản đầu" in chu


def _ns_hs(them):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("du_an")
    p.add_argument("duong", nargs="*")
    for c in ("--ghi", "--goi-api", "--doc-ho-so"):
        p.add_argument(c, action="store_true")
    p.add_argument("--sao-luu")
    p.add_argument("--toi-da-usd", type=float)
    p.add_argument("--so-trang", type=int, default=3)
    return p.parse_args(["hapas", *them])


def test_script_doc_ho_so_ghi_qua_luot_va_tran(tmp_path, monkeypatch):
    import quet_lon
    bai = [dict(_bn("a", "8100000001"), gio_hang=None, la_quang_cao=None),
           dict(_bn("a", "8100000009"), gio_hang=None, la_quang_cao=None)]
    monkeypatch.setattr(K, "bai_tiktok_co", lambda ma: [dict(b) for b in bai])
    monkeypatch.setattr(K, "doc_du_an", lambda ma: {"tran_usd_thang": 5})
    monkeypatch.setattr(K, "da_tieu_thang", lambda ma: 4.99)          # còn tháng 0,01
    monkeypatch.setattr(quet_lon, "ngan_sach", lambda t: (1.0, None, ""))
    monkeypatch.setattr(quet_lon, "tran_usd_nen", lambda: 1.0)
    monkeypatch.setenv("APIFY_TOKEN", "x")
    monkeypatch.setattr(K, "luot_dang_chay", lambda ma: None)
    monkeypatch.setattr(K, "mo_luot", lambda *a, **k: 55)
    dong = {}
    monkeypatch.setattr(K, "dong_luot", lambda luot, **k: dong.update(k, luot=luot))
    nhip = []
    monkeypatch.setattr(K, "nhip_luot", lambda luot, usd, ghi_chu=None: nhip.append(usd))
    cap = []
    monkeypatch.setattr(K, "cap_nhat_so_lieu", lambda ma, luot, rows: cap.extend(rows) or len(rows))
    gia = GiaTT({"a": [[_a("8100000001", 10, SHOP), _a("8100000009", 9, None)]]})
    monkeypatch.setattr(TT, "_goi", gia)
    sl = tmp_path / "sl.jsonl"
    assert G.chay(_ns_hs(["--doc-ho-so", "--toi-da-usd", "9", "--ghi", "--sao-luu", str(sl)]),
                  lambda s: None) == 0
    assert len(gia.goi) == 2                     # trần = còn tháng 0,01 USD; đủ ở trang 1
    assert {r["khoa"]: r["gio_hang"] for r in cap} == {"tiktok:8100000001": True,
                                                       "tiktok:8100000009": False}
    assert dong["luot"] == 55 and dong["chi_phi_usd"] == pytest.approx(2 * TT.GIA_YEU_CAU)
    assert dong["trang_thai"] == "xong" and nhip == [pytest.approx(2 * TT.GIA_YEU_CAU)]
    assert len(sl.read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.tiktok_api
def test_buoc_cuoi_luot_tran_moi_luot(monkeypatch):
    monkeypatch.setenv("LANG_NGHE_GIO_HO_SO_USD", "0.004")
    assert TDA.ho_so_gio_usd() == 0.004
    monkeypatch.setattr(K, "bai_gio_null_luot", lambda ma, luot: [_bn("a", "8100000001")])
    cap = []
    monkeypatch.setattr(K, "cap_nhat_so_lieu", lambda ma, luot, rows: cap.extend(rows) or 1)
    gia = GiaTT({"a": [[_a("8100000001", 10, None)]]})
    monkeypatch.setattr(TT, "_goi", gia)
    phan = []
    tk = TDA.gio_ho_so_luot("hapas", 7, 1.0, phan.append)
    assert len(gia.goi) == 2 and cap[0]["gio_hang"] is False and tk["usd"] == 0.004
    monkeypatch.setenv("LANG_NGHE_GIO_HO_SO_USD", "0")
    assert TDA.gio_ho_so_luot("hapas", 7, 1.0, phan.append)["yeu_cau"] == 0


# ───────────────────────────── soát 21/10/2026 (trước lượt trả tiền) ─────────────────────────────
class GiaTTNo(GiaTT):
    """Như `GiaTT` nhưng ném `loi_sau` ở hồ sơ thứ `n_ho_so` (chết giữa chừng)."""

    def __init__(self, trang, n_ho_so, loi_sau):
        super().__init__(trang)
        self.n, self.loi_sau, self.ho_so = n_ho_so, loi_sau, 0

    def __call__(self, payload, ngan):
        if "profile_username" in payload:
            self.ho_so += 1
            if self.ho_so == self.n:
                raise self.loi_sau
        return super().__call__(payload, ngan)


def test_doc_ho_so_ghi_dan_va_chet_giua_chung_van_dua_lo(monkeypatch):
    gia = GiaTTNo({"a": [[_a("8100000001", 10, SHOP)]], "b": [[_a("8200000001", 10)]]},
                  3, RuntimeError("mạng"))
    monkeypatch.setattr(TT, "_goi", gia)
    lo, so = [], []
    bai = [_bn("a", "8100000001"), _bn("a", "8100000002"), _bn("b", "8200000001"),
           _bn("c", "8300000001")]
    with pytest.raises(RuntimeError):
        TDA.doc_ho_so_gio(bai, 1.0, so_run=so, ghi_lo=lambda r, tk: lo.append(
            ([x["khoa"] for x in r], tk["usd"])), lo=1)
    assert [k for k, _ in lo] == [["tiktok:8100000001"], ["tiktok:8200000001"]]
    assert len(so) == 4 and lo[-1][1] == pytest.approx(4 * TT.GIA_YEU_CAU)


def _script_gia(monkeypatch, gia):
    import quet_lon
    monkeypatch.setattr(K, "doc_du_an", lambda ma: {"tran_usd_thang": 50})
    monkeypatch.setattr(K, "da_tieu_thang", lambda ma: 0.0)
    monkeypatch.setattr(quet_lon, "ngan_sach", lambda t: (9.0, None, ""))
    monkeypatch.setattr(quet_lon, "tran_usd_nen", lambda: 9.0)
    monkeypatch.setenv("APIFY_TOKEN", "x")
    monkeypatch.setattr(K, "luot_dang_chay", lambda ma: None)
    monkeypatch.setattr(K, "mo_luot", lambda *a, **k: 77)
    dong, nhip, cap = {}, [], []
    monkeypatch.setattr(K, "dong_luot", lambda luot, **k: dong.update(k, luot=luot))
    monkeypatch.setattr(K, "nhip_luot", lambda luot, usd, ghi_chu=None: nhip.append(usd))
    monkeypatch.setattr(K, "cap_nhat_so_lieu", lambda ma, luot, rows: cap.extend(rows) or len(rows))
    monkeypatch.setattr(TDA, "ghi_nho_ho_so", lambda *a, **k: None)
    monkeypatch.setattr(TT, "_goi", gia)
    return dong, nhip, cap


def test_script_ctrl_c_dong_luot_loi_voi_tien_da_tieu(tmp_path, monkeypatch):
    gia = GiaTTNo({"a": [[_a("8100000001", 10, SHOP)]]}, 2, KeyboardInterrupt())
    dong, nhip, cap = _script_gia(monkeypatch, gia)
    monkeypatch.setattr(G, "LO_TAI_KHOAN", 1)
    sl = tmp_path / "sl.jsonl"
    bai = [_bn("a", "8100000001"), _bn("a", "8100000003"), _bn("b", "8200000001")]
    with pytest.raises(KeyboardInterrupt):
        G.doc_ho_so("hapas", bai, 9.0, 3, lambda s: None, datetime.datetime.now(VN),
                    sao_luu=str(sl), cu={"tiktok:8100000001": {"gio_hang": None,
                                                                "la_quang_cao": None}})
    assert dong["trang_thai"] == "loi" and "KeyboardInterrupt" in dong["loi"]
    assert dong["chi_phi_usd"] == pytest.approx(2 * TT.GIA_YEU_CAU)   # hồ sơ + 1 trang của a
    assert [r["khoa"] for r in cap] == ["tiktok:8100000001"] and nhip
    assert len(sl.read_text(encoding="utf-8").splitlines()) == 1


def test_script_het_gio_dung_sach(monkeypatch):
    gia = GiaTT({"a": [[_a("8100000001", 10)]], "b": [[_a("8200000001", 10)]]})
    dong, nhip, cap = _script_gia(monkeypatch, gia)
    gio = [datetime.datetime(2026, 10, 21, 6, 49, tzinfo=VN)]

    def dong_ho():
        gio[0] += datetime.timedelta(minutes=1)
        return gio[0]
    out: list[str] = []
    rows, tk = G.doc_ho_so("hapas", [_bn("a", "8100000001"), _bn("a", "8100000002"),
                                     _bn("b", "8200000001")], 9.0, 3, out.append,
                           datetime.datetime(2026, 10, 21, 6, 0, tzinfo=VN), dong_ho=dong_ho)
    assert dong["trang_thai"] == "xong" and "hết giờ" in dong["ghi_chu"] and tk["loi"] is None
    assert tk["tai_khoan"] == 0 and not gia.goi          # 06:50 ở lần kiểm đầu: không gửi gì


@pytest.mark.parametrize("bat_dau,het,phut,ky_vong", [
    ((5, 0), None, 150, (21, 6, 50)), ((7, 30), None, 150, (21, 10, 0)),
    ((23, 0), datetime.time(6, 50), 600, (22, 6, 50)), ((5, 0), None, 30, (21, 5, 30))])
def test_han_dung(bat_dau, het, phut, ky_vong):
    b = datetime.datetime(2026, 10, 21, *bat_dau, tzinfo=VN)
    assert G.han_dung(b, het, phut) == datetime.datetime(2026, 10, ky_vong[0], ky_vong[1],
                                                         ky_vong[2], tzinfo=VN)


def test_chay_thu_in_tran_hieu_luc(monkeypatch):
    import quet_lon
    monkeypatch.setattr(K, "bai_tiktok_co", lambda ma: [
        dict(_bn("a", "8100000001"), gio_hang=None, la_quang_cao=None)])
    monkeypatch.setattr(K, "doc_du_an", lambda ma: {"tran_usd_thang": 5})
    monkeypatch.setattr(K, "da_tieu_thang", lambda ma: 4.0)
    monkeypatch.setattr(quet_lon, "ngan_sach", lambda t: (9.0, None, ""))
    monkeypatch.setattr(quet_lon, "tran_usd_nen", lambda: 9.0)
    monkeypatch.setattr(TT, "_goi", lambda *a, **k: pytest.fail("chạy thử không gọi API"))
    out: list[str] = []
    G.chay(_ns_hs(["--doc-ho-so", "--toi-da-usd", "9"]), out.append)
    chu = "\n".join(out)
    assert "trần 1.0000 USD = min(--toi-da-usd 9.0, còn tháng dự án 1.00" in chu


def test_so_nho_bo_tai_khoan_da_thu(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_thu_muc_nen", lambda: tmp_path)
    nay = datetime.datetime(2026, 10, 21, 7, tzinfo=VN)
    TDA.ghi_nho_ho_so("hapas", {"a": ["8100000001"], "cu": ["1"]}, nay - datetime.timedelta(days=8))
    TDA.ghi_nho_ho_so("hapas", {"a": ["8100000001"]}, nay - datetime.timedelta(days=1))
    assert TDA.tai_khoan_moi_thu("hapas", nay) == {"a"}            # "cu" quá 7 ngày
    TDA.ghi_nho_ho_so("hapas", {"x": ["1"]}, nay + datetime.timedelta(days=40))
    assert set(TDA.doc_nho_ho_so("hapas")) == {"x"}                # chỉ giữ 30 ngày


@pytest.mark.tiktok_api
def test_buoc_cuoi_luot_bo_tai_khoan_trong_so_nho(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_thu_muc_nen", lambda: tmp_path)
    nay = datetime.datetime(2026, 10, 21, 7, tzinfo=VN)
    TDA.ghi_nho_ho_so("hapas", {"a": ["8100000001"]}, nay - datetime.timedelta(days=2))
    monkeypatch.setattr(K, "bai_gio_null_luot", lambda ma, luot: [
        _bn("a", "8100000001"), _bn("b", "8200000001")])
    monkeypatch.setattr(K, "cap_nhat_so_lieu", lambda ma, luot, rows: len(rows))
    gia = GiaTT({"b": []})                                         # b: hồ sơ trống → nhớ b
    monkeypatch.setattr(TT, "_goi", gia)
    tk = TDA.gio_ho_so_luot("hapas", 7, 1.0, lambda ph: None, bay_gio=nay)
    assert [p.get("profile_username") for p in gia.goi if "profile_username" in p] == ["b"]
    assert tk["bo_qua_nho"] == 1 and set(TDA.doc_nho_ho_so("hapas")) == {"a", "b"}


class _ViecGia:
    def __init__(self, giay):
        import threading
        self._khoa, self.d, self.giay = threading.RLock(), {}, giay

    def con_giay(self):
        return self.giay

    def luu(self):
        pass

    def cac_phan(self):
        return []


def test_buoc_cuoi_luot_co_lap_loi_va_tru_tien(monkeypatch):
    import theo_doi as T
    seen = {}

    def no(ma, luot, con, them_phan, dung=None):
        seen["con"] = con
        them_phan({"id": "hs-tiktok-r1", "nen_tang": "tiktok_gio_ho_so", "run_id": "r1"})
        raise RuntimeError("hỏng")
    monkeypatch.setattr(TDA, "gio_ho_so_luot", no)
    v = _ViecGia(1000)
    tk = {"usd": 0.3, "ghi_chu": []}
    T._gio_ho_so_cuoi_luot(v, "hapas", 7, 0.5, tk)
    assert seen["con"] == pytest.approx(0.2)                       # đã trừ tiền tìm + làm mới
    assert tk["usd"] == pytest.approx(0.3 + TT.GIA_YEU_CAU) and "lỗi RuntimeError" in tk["ghi_chu"][-1]
    v2 = _ViecGia(10)
    monkeypatch.setattr(TDA, "gio_ho_so_luot", lambda *a, **k: pytest.fail("sắp hết giờ"))
    T._gio_ho_so_cuoi_luot(v2, "hapas", 7, 0.5, {"usd": 0.0, "ghi_chu": []})


def test_ghi_co_tiktok_moi_tham_so_trong_sql_deu_co_gia_tri(monkeypatch):
    """21/10/2026, chạy thật: `_GOP_CO` nhắc giá trị mới hai lần và dùng ở cả SET lẫn WHERE — bản
    tham số vị trí truyền thiếu (ProgrammingError, hỏng cả lô cap_nhat_so_lieu). Mọi tên `%(x)s`
    phải có trong tham số, không còn `%s` vị trí."""
    import re
    import lang_nghe_db as K

    class C:
        def execute(self, sql, params):
            self.sql, self.params = sql, params
            return self

        def fetchone(self):
            return {"khoa": "k"}

    c = C()
    monkeypatch.setattr(K, "_co_cot", lambda _c, _k: True)
    assert K.ghi_co_tiktok(c, "hapas", "k", {"khoa": "k", "gio_hang": True, "la_quang_cao": False})
    assert "%s" not in c.sql
    assert set(re.findall(r"%\((\w+)\)s", c.sql)) <= set(c.params)
