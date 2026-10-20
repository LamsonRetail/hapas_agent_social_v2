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
        self.cau.append((sql, list(ts or [])))
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
    assert "IS DISTINCT FROM" in sql and ts[0] is True and "cap_nhat_cuoi = now()" in sql
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
    assert x["tong"]["bai"] == 4             # bỏ kênh nhà + Facebook; bỏ chính chiều koc
    aff = next(g for g in x["nhom"] if g["ma"] == "affiliate")
    assert aff["bai"] == 2 and aff["nguoi"] == 2 and aff["quang_cao"] == 1
    assert aff["bai_pt"] == 50.0 and aff["xem"] == 200 and aff["tuong_tac"] == 32
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
    js = (GOC / "dashboard" / "static" / "chi_so.js").read_text(encoding="utf-8")
    assert '"kieu_trang", "koc", "y_dinh"' in js and "function veKoc(" in js
    assert '{ k: "koc", ten: "Loại KOC"' in js and "veKoc(d)" in js
    css = (GOC / "dashboard" / "static" / "chi_so.css").read_text(encoding="utf-8")
    assert ".cs-koc__luoi" in css


def test_api_va_kho_doc_cot(monkeypatch):
    from dashboard import kho as KD
    monkeypatch.setattr(KD, "_CO_CO_TT", [])

    class C:
        def __init__(self, n):
            self.n = n

        def execute(self, sql, ts=()):
            return self

        def fetchone(self):
            return {"n": self.n}
    assert "NULL::boolean AS gio_hang" in KD._cot_co_tiktok(C(0))      # DB chưa chạy schema
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
    assert nhom["affiliate"]["bai"] == 1 and nhom["branding"]["bai"] == 1
    assert nhom["chua_ro"]["bai"] == 1                    # tiktok:6 không có cờ
    assert "TỪNG video" in ra["koc"]["quy_tac"] and ra["bo_loc"]["koc"]["affiliate"] == 1
    assert any(b.get("loai_koc") == CS.KOC["affiliate"] for b in ra["bai"]["top"])
    assert "koc" in HD.PHAN and "koc" in HD._PHAN_SO_LIEU
    assert "koc: affiliate,branding,chua_ro" in json.dumps(HD.SCHEMA, ensure_ascii=False)
