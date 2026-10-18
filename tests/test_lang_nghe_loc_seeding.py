"""Script một lần `scripts/lang_nghe_loc_seeding.py` (18/10/2026): dọn bài seeding affiliate ĐÃ nằm
trong kho. Kho GIẢ trong bộ nhớ nhận câu SQL theo thẻ `/* seed:<tên> */`; mỗi `ket_noi()` là một
giao dịch (lỗi thì trả lại như cũ); xoá bài thì bình luận + chi_so_ngay xoá theo (FK ON DELETE
CASCADE như schema.sql). Sổ "đã loại" là tệp thật trong thư mục tạm (conftest)."""
from __future__ import annotations

import copy
import datetime
import json
import re
import sys
from pathlib import Path

import pytest

import lang_nghe_db as K
import loc_rac as L
import theo_doi_api as TDA

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lang_nghe_loc_seeding as S

_VN = datetime.timezone(datetime.timedelta(hours=7))
BAY_GIO = datetime.datetime.now(_VN).replace(microsecond=0)
NGAY = (BAY_GIO - datetime.timedelta(days=3)).replace(hour=21, minute=0, second=0)
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"], "tu_loai_tru": [],
         "boi_canh": "HAPAS", "thi_truong": "VN", "cau_hinh": {}}
NGUON = [{"id": 1, "nen_tang": "tiktok", "dinh_danh": "hapas.official", "loai": "kenh_nha"}]


def _bai(tk, i, bl=0, xem=300, phut=None):
    luc = NGAY + datetime.timedelta(minutes=i if phut is None else phut)
    return {"du_an": "hapas", "khoa": f"tiktok:{tk}{i}", "nen_tang": "tiktok", "nguon_id": None,
            "kieu_quet": "tu_khoa", "link": f"https://www.tiktok.com/@{tk}/video/{i}",
            "tac_gia": tk, "tai_khoan": tk, "followers": 1000, "dang_luc": luc,
            "noi_dung": "#HAPAS #QUATANG2010", "hashtag": "HAPAS, QUATANG2010",
            "khop_tu_khoa": True, "sac_thai": None, "chu_de": None, "ly_do_giu": "khop_tu_khoa",
            "xem": xem, "thich": 1, "binh_luan": bl, "chia_se": 0, "thay_lan_dau": BAY_GIO,
            "cap_nhat_cuoi": BAY_GIO, "luot_dau": 5, "luot_cuoi": 5, "bl_lay_luc": None,
            "bl_da_lay": None, "bl_lay_khi_co": None, "ma_noi_dung": None, "bl_lan_thieu": 0,
            "kieu_trang": None, "muc_nhac": None, "la_pr": None, "ma_so_fb": None}


def _bl(khoa, ma):
    return {"du_an": "hapas", "khoa_bai": khoa, "ma": ma, "nen_tang": "tiktok", "tac_gia": "k",
            "noi_dung": "xinh", "thich": 0, "tra_loi": 0, "la_tra_loi": False,
            "cua_thuong_hieu": False, "dang_luc": NGAY, "sac_thai": None, "chu_de": None,
            "luot_id": 5, "thay_lan_dau": BAY_GIO, "cap_nhat_cuoi": BAY_GIO, "loai": "hop_le",
            "ly_do_loc": None, "ma_noi_dung": None, "link": None, "ma_cha": None,
            "san_pham": None}


def _cs(khoa):
    return {"du_an": "hapas", "khoa": khoa, "ngay": NGAY.date(), "xem": 300, "thich": 1,
            "binh_luan": 0, "chia_se": 0}


def _kho_mau():
    bai = ([_bai("aff_mau", i) for i in range(6)] + [_bai("aff_mau", 9, bl=15)]
           + [_bai("review_mau", i, bl=4, phut=i * 1440) for i in range(3)]
           + [_bai("hapas.official", i) for i in range(7)]
           + [_bai("hapasgigamall", i) for i in range(6)])
    bl = [_bl("tiktok:aff_mau0", "c1"), _bl("tiktok:aff_mau1", "c2")]
    cs = [_cs(f"tiktok:aff_mau{i}") for i in range(6)]
    return bai, bl, cs


class KhoGia:
    def __init__(self, bai=(), bl=(), cs=(), quyen_xoa=True, luot_chay=(), truoc_khoa=None):
        self.t = {"bai": {(r["du_an"], r["khoa"]): dict(r) for r in bai},
                  "binh_luan": {(r["du_an"], r["khoa_bai"], r["ma"]): dict(r) for r in bl},
                  "chi_so_ngay": {(r["du_an"], r["khoa"], r["ngay"]): dict(r) for r in cs}}
        self.quyen_xoa, self.luot_chay, self.truoc_khoa = quyen_xoa, list(luot_chay), truoc_khoa
        self.chi_doc = self.co_chi_doc = False
        self.ghi: list[str] = []
        self.khoa_luot: list = []

    def __call__(self):
        return self

    def __enter__(self):
        self._goc = copy.deepcopy(self.t)
        self.chi_doc = False
        return self

    def __exit__(self, kieu, *a):
        if kieu is not None:
            self.t = self._goc
        return False

    def _tra(self, rows=(), n=None):
        self._kq = [dict(r) for r in rows]
        self.rowcount = len(self._kq) if n is None else n
        return self

    def fetchone(self):
        return self._kq[0] if self._kq else None

    def fetchall(self):
        return list(self._kq)

    def execute(self, sql, ts=()):
        ts = list(ts or [])
        if sql == S.SQL_CHI_DOC:
            self.chi_doc = self.co_chi_doc = True
            return self._tra()
        the = re.match(r"/\* seed:(\w+) \*/", sql).group(1)
        doc = the in ("du_an", "nguon", "bai", "dem_bl", "dem_cs", "quyen", "luot_chay",
                      "dong_bo", "khoa_luot", "khoa_bai", "khoa_bl", "khoa_cs")
        if not doc:
            assert not self.chi_doc, f"ghi ({the}) trong giao dịch chỉ đọc"
            self.ghi.append(the)
        b, bl, cs = self.t["bai"], self.t["binh_luan"], self.t["chi_so_ngay"]
        if the == "du_an":
            return self._tra([dict(DU_AN)] if ts[0] == "hapas" else [])
        if the == "nguon":
            return self._tra(NGUON)
        if the == "bai":
            return self._tra(sorted((r for r in b.values() if r["dang_luc"] >= ts[1]
                                     and r["tai_khoan"].strip()),
                                    key=lambda r: (r["dang_luc"], r["khoa"])))
        if the == "dem_bl":
            dem: dict = {}
            for r in bl.values():
                if r["khoa_bai"] in ts[1]:
                    dem[r["khoa_bai"]] = dem.get(r["khoa_bai"], 0) + 1
            return self._tra([{"khoa_bai": k, "n": n} for k, n in dem.items()])
        if the == "dem_cs":
            dem = {}
            for r in cs.values():
                if r["khoa"] in ts[1]:
                    dem[r["khoa"]] = dem.get(r["khoa"], 0) + 1
            return self._tra([{"khoa": k, "n": n} for k, n in dem.items()])
        if the == "quyen":
            return self._tra([{"xoa": self.quyen_xoa}])
        if the == "luot_chay":
            return self._tra([{"id": i} for i in self.luot_chay])
        if the == "dong_bo":
            return self._tra([{"n": 0}])
        if the == "khoa_luot":
            assert ts == [K.so_khoa_luot("hapas")]
            self.khoa_luot.append(ts[0])
            if self.truoc_khoa:
                self.truoc_khoa(self)
            return self._tra()
        if the == "khoa_bai":
            return self._tra(sorted((r for r in b.values() if r["khoa"] in ts[1]),
                                    key=lambda r: r["khoa"]))
        if the == "khoa_bl":
            return self._tra(r for r in bl.values() if r["khoa_bai"] in ts[1])
        if the == "khoa_cs":
            return self._tra(r for r in cs.values() if r["khoa"] in ts[1])
        if the == "xoa_bai":
            xoa = [k for k in b if k[0] == ts[0] and k[1] in ts[1]]
            for k in xoa:
                del b[k]
            for k in [k for k, r in bl.items() if (r["du_an"], r["khoa_bai"]) in xoa]:
                del bl[k]
            for k in [k for k, r in cs.items() if (r["du_an"], r["khoa"]) in xoa]:
                del cs[k]
            return self._tra(n=len(xoa))
        if the.startswith("hoan_"):
            bang = the[5:]
            cot = [x.strip() for x in re.search(r"\(([^)]*)\) VALUES", sql).group(1).split(",")]
            r = dict(zip([c for c in cot if c != "cap_nhat_cuoi"], ts))
            khoa = {"bai": ("du_an", "khoa"), "chi_so_ngay": ("du_an", "khoa", "ngay"),
                    "binh_luan": ("du_an", "khoa_bai", "ma")}[bang]
            k = tuple(r[c] for c in khoa)
            if k in self.t[bang]:
                return self._tra(n=0)
            self.t[bang][k] = r
            return self._tra(n=1)
        raise AssertionError(f"thẻ lạ {the}")


@pytest.fixture
def kho(monkeypatch):
    k = KhoGia(*_kho_mau())
    monkeypatch.setattr(K, "ket_noi", k)
    monkeypatch.setattr(K, "lich_chien_dich", lambda ma: [])
    return k


def _chay(argv, kho=None):
    out: list[str] = []
    ma = S.chay(S.tao_parser().parse_args(argv), in_ra=out.append, bay_gio=BAY_GIO)
    return ma, "\n".join(out)


def test_chay_thu_chi_doc_in_so_va_mau(kho):
    ma, out = _chay(["hapas"])
    assert ma == 0 and kho.ghi == [] and kho.co_chi_doc
    assert "Tài khoản seeding: 1. Sẽ chuyển sang sổ đã loại: 6 bài (6 thảo luận)" in out
    assert "giữ vì có ≥ 10 bình luận: 1 bài" in out
    assert "Đi theo (xoá theo bài): 2 bình luận, 6 dòng chi_so_ngay" in out
    assert "tiktok @aff_mau: 7 bài, cao nhất 7 bài ngày" in out and "→ bỏ 6, giữ 1" in out
    assert re.search(r"MIỄN \(kênh nhà / tên brand\): @hapas\.official .*@hapasgigamall", out)
    assert "review_mau" not in out
    assert TDA.doc_seeding("hapas") == []


def test_ap_dung_can_tep_quyen_va_khong_co_luot_dang_chay(kho, tmp_path):
    assert _chay(["hapas", "--ap-dung"])[0] == 2
    tep = tmp_path / "hoan.jsonl"
    tep.write_text("x", encoding="utf-8")
    assert "đã có" in _chay(["hapas", "--ap-dung", "--sao-luu", str(tep)])[1]
    kho.quyen_xoa = False
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tmp_path / "a.jsonl")])
    assert ma == 2 and "GRANT DELETE ON bai TO mark" in out and kho.ghi == []
    kho.quyen_xoa, kho.luot_chay = True, [41]
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tmp_path / "b.jsonl")])
    assert ma == 2 and "lượt 41" in out and kho.ghi == []


def test_ap_dung_chuyen_sang_so_xoa_kho_roi_hoan_tac(kho, tmp_path):
    tep = tmp_path / "loc.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tep)])
    assert ma == 0 and "Đã dọn 1/1 tài khoản (6 bài)" in out
    con = {k[1] for k in kho.t["bai"]}
    assert not any(k.startswith("tiktok:aff_mau") and k != "tiktok:aff_mau9" for k in con)
    assert "tiktok:aff_mau9" in con and len(con) == 17
    assert kho.t["binh_luan"] == {} and kho.t["chi_so_ngay"] == {}, "bình luận + chỉ số xoá theo"
    assert kho.khoa_luot == [K.so_khoa_luot("hapas")]
    dau = TDA.dau_loai(DU_AN, ["hapas"])
    so = TDA.doc_loai("hapas", dau, NGAY - datetime.timedelta(days=1))
    assert {k for k, v in so.items() if v[0] == L.LY_DO_SEEDING_BAI} == {
        f"tiktok:aff_mau{i}" for i in range(6)}
    assert sorted(x["khoa"] for x in TDA.doc_seeding("hapas")) == [
        f"tiktok:aff_mau{i}" for i in range(6)]
    dong = [json.loads(x) for x in tep.read_text(encoding="utf-8").splitlines()]
    assert [x["loai_dong"] for x in dong] == ["dau", "tai_khoan", "da_ap"]
    assert len(dong[1]["bai"]) == 6 and len(dong[1]["binh_luan"]) == 2
    assert len(dong[1]["chi_so_ngay"]) == 6 and dong[0]["dau_luat"] == dau
    # Chạy lại: không còn gì để dọn.
    assert "Không có bài seeding nào để dọn" in _chay(
        ["hapas", "--ap-dung", "--sao-luu", str(tmp_path / "lan2.jsonl")])[1]
    # Hoàn tác: bài, chỉ số, bình luận về như cũ; khoá gỡ khỏi sổ. Chạy lại không chèn gì nữa.
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and "chèn lại 6 bài, 6 dòng chi_so_ngay, 2 bình luận" in out
    assert len(kho.t["bai"]) == 23 and len(kho.t["binh_luan"]) == 2
    goc = {(r["du_an"], r["khoa"]): r for r in _kho_mau()[0]}
    for k in [("hapas", f"tiktok:aff_mau{i}") for i in range(6)]:
        assert kho.t["bai"][k]["dang_luc"] == goc[k]["dang_luc"]
        assert kho.t["bai"][k]["binh_luan"] == goc[k]["binh_luan"]
    assert TDA.doc_seeding("hapas") == [] and not TDA.doc_loai(
        "hapas", dau, NGAY - datetime.timedelta(days=1))
    assert "chèn lại 0 bài" in _chay(["hapas", "--hoan-tac", str(tep)])[1]


def test_hoan_tac_ca_tai_khoan_chua_co_dau_da_ap_va_nhac_revoke(kho, tmp_path):
    """Soát 18/10/2026 (LOW): tiến trình dừng NGAY sau commit (chưa kịp ghi dấu "đã áp") — dòng đã
    xoá vẫn được chèn lại; giao dịch huỷ (dòng còn nguyên) — chèn lại không làm gì; sổ gỡ khoá."""
    tep = tmp_path / "z.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tep)])
    assert ma == 0 and "REVOKE DELETE ON bai FROM mark" in out
    dong = [x for x in tep.read_text(encoding="utf-8").splitlines()
            if json.loads(x)["loai_dong"] != "da_ap"]
    tep.write_text("\n".join(dong) + "\n", encoding="utf-8")
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and "chèn lại 6 bài, 6 dòng chi_so_ngay, 2 bình luận" in out
    assert "1 tài khoản không có dấu đã áp" in out and "đã hoàn tác an toàn" in out
    assert len(kho.t["bai"]) == 23 and TDA.doc_seeding("hapas") == []
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and "chèn lại 0 bài" in out, "dòng còn trong kho: không chèn trùng"


def test_doc_lai_trong_giao_dich_bai_vua_co_binh_luan_thi_giu(kho, tmp_path):
    def them_bl(k):
        k.t["bai"][("hapas", "tiktok:aff_mau0")]["binh_luan"] = 12
    kho.truoc_khoa = them_bl
    _, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tmp_path / "x.jsonl")])
    assert "(5 bài)" in out and ("hapas", "tiktok:aff_mau0") in kho.t["bai"]


def test_luot_mo_ngay_truoc_khoa_thi_dung_khong_xoa(kho, tmp_path):
    def mo(k):
        k.luot_chay.append(77)
    kho.truoc_khoa = mo
    tep = tmp_path / "y.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tep)])
    assert ma == 1 and "DỪNG" in out and len(kho.t["bai"]) == 23
    assert [json.loads(x)["loai_dong"] for x in tep.read_text(encoding="utf-8").splitlines()] \
        == ["dau"]
    assert TDA.doc_seeding("hapas") == []
