"""Script một lần `scripts/lang_nghe_loc_khong_brand.py` (27/10/2026): dọn bài đường từ khoá giữ theo
luật `khop_tu_khoa` mà KHÔNG có tín hiệu brand (`theo_doi.co_tin_hieu_brand` — cùng hàm với lượt
quét) + bài `other_market` của dự án VN. Kho GIẢ trong bộ nhớ nhận câu SQL theo thẻ
`/* khb:<tên> */`; mỗi `ket_noi()` là một giao dịch (lỗi thì trả lại như cũ); xoá bài thì bình luận
+ chi_so_ngay xoá theo (FK ON DELETE CASCADE). Sổ "đã loại" là tệp thật trong thư mục tạm."""
from __future__ import annotations

import copy
import datetime
import json
import re
import sys
from pathlib import Path

import pytest

import lang_nghe_db as K
import nguon_web as W
import theo_doi as T
import theo_doi_api as TDA

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lang_nghe_loc_khong_brand as S

_VN = datetime.timezone(datetime.timedelta(hours=7))
BAY_GIO = datetime.datetime.now(_VN).replace(microsecond=0)
NGAY = (BAY_GIO - datetime.timedelta(days=3)).replace(hour=21, minute=0, second=0)
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas", "yêu từ điều nhỏ nhất"],
         "tu_loai_tru": [], "boi_canh": "HAPAS", "thi_truong": "VN", "cau_hinh": {},
         "hashtag": ["hapas", "yeutudieunhonhat", "quatang2010"]}
NGUON = [{"id": 1, "nen_tang": "tiktok", "dinh_danh": "hapas.official", "loai": "kenh_nha"}]
TU_VI = ("Không giỏi nói lời yêu thương, nhưng chuyện lớn nhỏ trong nhà đều tự tay lo liệu… điểm "
         "cộng lớn nhất. Người như vậy hiếm lắm, xem tới cuối nhé #xuhuong #tuvi #tuvivochinhdieu")
MOT_TRAM_HAI_MUOI = TU_VI[:120]


def _bai(khoa, tk, noi_dung, ly="khop_tu_khoa", kieu="tu_khoa", p="tiktok", tac_gia=None):
    return {"du_an": "hapas", "khoa": khoa, "nen_tang": p, "nguon_id": None, "kieu_quet": kieu,
            "link": f"https://www.tiktok.com/@{tk}/video/{khoa.rsplit(':', 1)[-1]}",
            "tac_gia": tac_gia or tk, "tai_khoan": tk, "followers": 1000, "dang_luc": NGAY,
            "noi_dung": noi_dung, "hashtag": "", "khop_tu_khoa": True, "sac_thai": None,
            "chu_de": None, "ly_do_giu": ly, "xem": 900, "thich": 1, "binh_luan": 7,
            "chia_se": 0, "thay_lan_dau": BAY_GIO, "cap_nhat_cuoi": BAY_GIO, "luot_dau": 5,
            "luot_cuoi": 5, "bl_lay_luc": None, "bl_da_lay": None, "bl_lay_khi_co": None,
            "ma_noi_dung": None, "bl_lan_thieu": 0, "kieu_trang": None, "muc_nhac": None,
            "la_pr": None, "ma_so_fb": None}


def _bl(khoa, ma, loai="hop_le"):
    return {"du_an": "hapas", "khoa_bai": khoa, "ma": ma, "nen_tang": "tiktok", "tac_gia": "k",
            "noi_dung": "hay", "thich": 0, "tra_loi": 0, "la_tra_loi": False,
            "cua_thuong_hieu": False, "dang_luc": NGAY, "sac_thai": None, "chu_de": None,
            "luot_id": 5, "thay_lan_dau": BAY_GIO, "cap_nhat_cuoi": BAY_GIO, "loai": loai,
            "ly_do_loc": None, "ma_noi_dung": None, "link": None, "ma_cha": None,
            "san_pham": None}


def _cs(khoa, lui=0):
    return {"du_an": "hapas", "khoa": khoa, "ngay": NGAY.date() - datetime.timedelta(days=lui),
            "xem": 900, "thich": 1, "binh_luan": 7, "chia_se": 0}


def _kho_mau():
    bai = [_bai("tiktok:1", "tuvi.vochinhdieu", TU_VI, tac_gia="Tử Vi Vô Chính Diệu"),
           _bai("tiktok:2", "kol_a", "Quà 20/10 #yeutudieunhonhat"),
           _bai("tiktok:3", "khach_b", "Túi HAPAS xinh"),
           _bai("tiktok:4", "hapas.official", "Yêu bản thân từ những điều nhỏ nhất"),
           _bai("threads:5", "nguoi_d", "cái brand này làm TVC hay ghê", ly="brand",
                p="threads"),
           _bai("tiktok:6", "hapas.th", "HAPAS Thailand ของขวัญ", ly="other_market"),
           _bai("youtube:7", "", "HAPAS TH", ly="other_market", kieu="theo_doi", p="youtube"),
           _bai("web:8", "", "Yêu bản thân từ những điều nhỏ nhất", p="web",
                tac_gia="baomoi.com"),
           _bai("tiktok:9", "me_c", "Yêu bản thân từ những điều nhỏ nhất", kieu="theo_doi")]
    bl = [_bl("tiktok:1", "c1"), _bl("tiktok:1", "c2", "spam"), _bl("tiktok:6", "c3"),
          _bl("tiktok:2", "c4")]
    cs = [_cs("tiktok:1"), _cs("tiktok:1", 1), _cs("tiktok:6"), _cs("tiktok:2")]
    return bai, bl, cs


class KhoGia:
    def __init__(self, bai=(), bl=(), cs=(), quyen_xoa=True, luot_chay=(), truoc_khoa=None,
                 dong_bo=0):
        self.t = {"bai": {(r["du_an"], r["khoa"]): dict(r) for r in bai},
                  "binh_luan": {(r["du_an"], r["khoa_bai"], r["ma"]): dict(r) for r in bl},
                  "chi_so_ngay": {(r["du_an"], r["khoa"], r["ngay"]): dict(r) for r in cs}}
        self.quyen_xoa, self.luot_chay, self.truoc_khoa = quyen_xoa, list(luot_chay), truoc_khoa
        self.dong_bo = dong_bo
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
        the = re.match(r"/\* khb:(\w+) \*/", sql).group(1)
        doc = the in ("du_an", "nguon", "bai", "khac", "dem_bl", "dem_cs", "quyen", "luot_chay",
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
            return self._tra(sorted((r for r in b.values() if r["du_an"] == ts[0]
                                     and r["kieu_quet"] == "tu_khoa" and r["ly_do_giu"] in ts[1]),
                                    key=lambda r: (r["nen_tang"], r["dang_luc"], r["khoa"])))
        if the == "khac":
            return self._tra([{"n": sum(1 for r in b.values() if r["ly_do_giu"] == "other_market"
                                        and r["kieu_quet"] != "tu_khoa")}])
        if the == "dem_bl":
            dem: dict = {}
            for r in bl.values():
                if r["khoa_bai"] in ts[1]:
                    x = dem.setdefault(r["khoa_bai"], [0, 0])
                    x[0] += 1
                    x[1] += r["loai"] == "hop_le"
            return self._tra([{"khoa_bai": k, "n": n, "hop_le": h} for k, (n, h) in dem.items()])
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
            return self._tra([{"n": self.dong_bo}])
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


def _chay(argv):
    out: list[str] = []
    ma = S.chay(S.tao_parser().parse_args(argv), in_ra=out.append, bay_gio=BAY_GIO)
    return ma, "\n".join(out)


def _so(ma="hapas", tu=None) -> dict:
    tu_kw = T.tu_tim(DU_AN)
    if ma.endswith(":web"):
        tu_kw = W.rut_gon_tu_khoa(tu_kw) or tu_kw
    return {k: v[0] for k, v in TDA.doc_loai(ma, TDA.dau_loai(DU_AN, tu_kw),
                                             NGAY - datetime.timedelta(days=1)).items()}


def test_chay_thu_chi_doc_liet_ke_tung_bai_va_tong(kho):
    ma, out = _chay(["hapas"])
    assert ma == 0 and kho.ghi == [] and kho.co_chi_doc
    assert "(a) giữ theo luật khop_tu_khoa, KHÔNG có tín hiệu brand: 2 bài, 2 bình luận" in out
    assert "(b) AI giữ mã other_market — dự án VN: 1 bài, 1 bình luận" in out
    assert ("[tiktok] Tử Vi Vô Chính Diệu @tuvi.vochinhdieu · "
            f"{NGAY:%d/%m} · 2 bl (1 hop_le) · https://www.tiktok.com/@tuvi.vochinhdieu/video/1"
            ) in out
    assert f"      {MOT_TRAM_HAI_MUOI}\n" in out + "\n" and TU_VI[:121] not in out
    assert "[web] baomoi.com · " in out and "[tiktok] hapas.th @hapas.th" in out
    assert "TỔNG sẽ dọn: 3 bài; đi theo (xoá theo bài): 3 bình luận (2 hop_le), 3 dòng " \
           "chi_so_ngay" in out
    # Giữ: tag chiến dịch viết liền, gọi tên HAPAS, kênh nhà. Không đụng: AI giữ, đường nguồn.
    assert "vẫn giữ (có tín hiệu brand / kênh nhà): 3" in out
    assert "Không đụng: 1 bài other_market ngoài đường từ khoá" in out
    for tk in ("kol_a", "khach_b", "hapas.official", "nguoi_d", "me_c"):
        assert f"@{tk} " not in out
    assert _so() == {} and _so("hapas:web") == {}


def test_cong_brand_tat_hoac_du_an_ngoai_vn(kho, monkeypatch):
    monkeypatch.setitem(DU_AN, "cau_hinh", {"hashtag_can_nhac_brand": False})
    out = _chay(["hapas"])[1]
    assert "KHÔNG có tín hiệu brand: 0 bài" in out and "TẮT" in out
    monkeypatch.setitem(DU_AN, "cau_hinh", {})
    monkeypatch.setitem(DU_AN, "thi_truong", "TH")
    out = _chay(["hapas"])[1]
    assert "other_market — dự án VN: 0 bài" in out and "TỔNG sẽ dọn: 2 bài" in out


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


def test_ap_dung_vao_so_xoa_kho_roi_hoan_tac(kho, tmp_path):
    tep = tmp_path / "loc.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tep)])
    assert ma == 0 and "Đã dọn 3/3 bài ((a) không nhắc brand 2, (b) other_market 1)" in out
    con = {k[1] for k in kho.t["bai"]}
    assert con == {"tiktok:2", "tiktok:3", "tiktok:4", "threads:5", "youtube:7", "tiktok:9"}
    assert {k[1] for k in kho.t["binh_luan"]} == {"tiktok:2"}, "bình luận xoá theo bài"
    assert {k[1] for k in kho.t["chi_so_ngay"]} == {"tiktok:2"}
    assert kho.khoa_luot == [K.so_khoa_luot("hapas")] * 3
    assert _so() == {"tiktok:1": T.LY_DO_KHONG_NHAC_BRAND, "tiktok:6": "ai:other_market"}
    assert _so("hapas:web") == {"web:8": T.LY_DO_KHONG_NHAC_BRAND}
    dong = [json.loads(x) for x in tep.read_text(encoding="utf-8").splitlines()]
    assert [x["loai_dong"] for x in dong] == ["dau"] + ["bai", "da_ap"] * 3
    tv = next(x for x in dong if x.get("khoa") == "tiktok:1" and x["loai_dong"] == "bai")
    assert len(tv["binh_luan"]) == 2 and len(tv["chi_so_ngay"]) == 2
    assert tv["so"] == {"hapas": ["tiktok:1"]} and tv["nhom"] == "khong_brand"
    assert "REVOKE DELETE ON bai FROM mark" in out
    # Lượt sau gặp lại bài Tử Vi: sổ chặn (vẫn không có tín hiệu brand) — không gửi AI.
    cong = T.cau_hinh_hashtag_brand(DU_AN)
    d = {"platform": "tiktok", "username": "tuvi.vochinhdieu", "kenh": "Tử Vi Vô Chính Diệu",
         "text": TU_VI, "hashtags": ""}
    assert T._con_chan([T.LY_DO_KHONG_NHAC_BRAND, "x"], d, cong, T.ten_brand(DU_AN))
    # Chạy lại: không còn gì để dọn.
    assert "Không có bài nào để dọn" in _chay(
        ["hapas", "--ap-dung", "--sao-luu", str(tmp_path / "lan2.jsonl")])[1]
    # Hoàn tác: bài, chỉ số, bình luận về như cũ; khoá gỡ khỏi cả hai sổ. Chạy lại không chèn gì.
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and "chèn lại 3 bài, 3 dòng chi_so_ngay, 3 bình luận" in out
    assert len(kho.t["bai"]) == 9 and len(kho.t["binh_luan"]) == 4
    goc = {(r["du_an"], r["khoa"]): r for r in _kho_mau()[0]}
    for k in [("hapas", "tiktok:1"), ("hapas", "tiktok:6"), ("hapas", "web:8")]:
        assert kho.t["bai"][k]["dang_luc"] == goc[k]["dang_luc"]
        assert kho.t["bai"][k]["ly_do_giu"] == goc[k]["ly_do_giu"]
    assert _so() == {} and _so("hapas:web") == {}
    assert "chèn lại 0 bài" in _chay(["hapas", "--hoan-tac", str(tep)])[1]


def test_doc_lai_trong_giao_dich_bai_doi_thi_giu(kho, tmp_path):
    """Giữa chạy thử và khoá dòng, lượt quét giữ lại bài Tử Vi với mã AI (brand) → không dọn."""
    def doi(k):
        k.t["bai"][("hapas", "tiktok:1")]["ly_do_giu"] = "brand"
    kho.truoc_khoa = doi
    _, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tmp_path / "x.jsonl")])
    assert "Đã dọn 2/3 bài" in out and "1 bài đã đổi / không còn" in out
    assert ("hapas", "tiktok:1") in kho.t["bai"] and "tiktok:1" not in _so()


def test_luot_mo_ngay_truoc_khoa_thi_dung_khong_xoa(kho, tmp_path):
    def mo(k):
        k.luot_chay.append(77)
    kho.truoc_khoa = mo
    tep = tmp_path / "y.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tep)])
    assert ma == 1 and "DỪNG" in out and len(kho.t["bai"]) == 9
    assert [json.loads(x)["loai_dong"] for x in tep.read_text(encoding="utf-8").splitlines()] \
        == ["dau"]
    assert _so() == {}


def test_hoan_tac_bai_chua_co_dau_da_ap_va_in_cau_xoa_bigquery(kho, tmp_path):
    kho.dong_bo = 12
    tep = tmp_path / "z.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tep)])
    assert ma == 0 and "ĐÃ đồng bộ" in out
    assert ("DELETE FROM `<dataset>.binh_luan` WHERE du_an = 'hapas' AND khoa_bai IN "
            "('tiktok:1', 'web:8', 'tiktok:6');") in out
    dong = [x for x in tep.read_text(encoding="utf-8").splitlines()
            if json.loads(x)["loai_dong"] != "da_ap"]
    tep.write_text("\n".join(dong) + "\n", encoding="utf-8")
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and "chèn lại 3 bài" in out and "3 bài không có dấu đã áp" in out
    assert len(kho.t["bai"]) == 9 and _so() == {}
