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
NGUON = [{"id": 1, "nen_tang": "tiktok", "dinh_danh": "hapas.official", "loai": "kenh_nha"},
         {"id": 2, "nen_tang": "tiktok", "dinh_danh": "@kol.duyet", "loai": "kol"}]
TU_VI = ("Không giỏi nói lời yêu thương, nhưng chuyện lớn nhỏ trong nhà đều tự tay lo liệu… điểm "
         "cộng lớn nhất. Người như vậy hiếm lắm, xem tới cuối nhé #xuhuong #tuvi #tuvivochinhdieu")
MOT_TRAM_HAI_MUOI = TU_VI[:120]


def _bai(khoa, tk, noi_dung, ly="khop_tu_khoa", kieu="tu_khoa", p="tiktok", tac_gia=None,
         nguon_id=None):
    return {"du_an": "hapas", "khoa": khoa, "nen_tang": p, "nguon_id": nguon_id, "kieu_quet": kieu,
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
           _bai("tiktok:9", "me_c", "Yêu bản thân từ những điều nhỏ nhất", kieu="theo_doi"),
           # Nguồn đã duyệt: theo `nguon_id` (KOL đổi tên tài khoản) và theo tài khoản (nguồn thêm
           # SAU khi bài vào kho — `nguon_id` còn NULL).
           _bai("tiktok:10", "kol_doi_ten", "Yêu bản thân từ những điều nhỏ nhất", nguon_id=2),
           _bai("tiktok:11", "kol.duyet", "Yêu bản thân từ những điều nhỏ nhất"),
           {**_bai("tiktok:12", "khong_ngay", "Yêu bản thân từ những điều nhỏ nhất"),
            "dang_luc": None}]
    bl = [_bl("tiktok:1", "c1"), _bl("tiktok:1", "c2", "spam"), _bl("tiktok:6", "c3"),
          _bl("tiktok:2", "c4"), _bl("tiktok:10", "c5")]
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
                                     and r["kieu_quet"] == "tu_khoa" and r["ly_do_giu"] in ts[1]
                                     and r["dang_luc"] is not None),
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


def _dau(web=False) -> str:
    tu_kw = T.tu_tim(DU_AN)
    return TDA.dau_loai(DU_AN, (W.rut_gon_tu_khoa(tu_kw) or tu_kw) if web else tu_kw)


def _so(ma="hapas") -> dict:
    return {k: v[0] for k, v in TDA.doc_loai(ma, _dau(ma.endswith(":web")),
                                             NGAY - datetime.timedelta(days=1)).items()}


def test_chay_thu_chi_doc_liet_ke_tung_bai_va_tong(kho):
    ma, out = _chay(["hapas"])
    assert ma == 0 and kho.ghi == [] and kho.co_chi_doc
    assert "KHÔNG có tín hiệu brand — XOÁ, không vào sổ: 2 bài, 2 bình luận" in out
    assert ("[tiktok] Tử Vi Vô Chính Diệu @tuvi.vochinhdieu · "
            f"{NGAY:%d/%m} · 2 bl (1 hop_le) · https://www.tiktok.com/@tuvi.vochinhdieu/video/1"
            ) in out
    assert len(TU_VI) > 120 and f"      {MOT_TRAM_HAI_MUOI}\n" in out
    assert TU_VI[:121] not in out
    assert "[web] baomoi.com · " in out
    # (b): liệt kê kèm nội dung để người quyết, mặc định KHÔNG xoá.
    assert "NGƯỜI QUYẾT (có thể là ghi chú thị trường VN): 1 bài, 1 bình luận. KHÔNG xoá" in out
    assert "[tiktok] hapas.th @hapas.th" in out and "HAPAS Thailand ของขวัญ" in out
    # Nguồn đã duyệt (KOL theo nguon_id, KOL theo tài khoản): giữ, in riêng. Kênh nhà
    # @hapas.official gọi tên brand ngay ở định danh — nằm trong số "vẫn giữ".
    assert "Thuộc nguồn đã duyệt — GIỮ (ứng viên (a)/(b) nhưng chủ bài là nguồn của dự án): 2 " \
           "bài, 1 bình luận" in out
    for tk in ("kol_doi_ten", "kol.duyet"):
        assert f"@{tk} · " in out
    assert "TỔNG sẽ dọn: 2 bài; đi theo (xoá theo bài): 2 bình luận (1 hop_le), 2 dòng " \
           "chi_so_ngay" in out
    assert "vẫn giữ (có tín hiệu brand / kênh nhà): 3" in out
    assert "Không đụng: 1 bài other_market ngoài đường từ khoá" in out
    for tk in ("kol_a", "khach_b", "hapas.official", "nguoi_d", "me_c", "khong_ngay"):
        assert f"@{tk} " not in out
    assert _so() == {} and _so("hapas:web") == {}
    out = _chay(["hapas", "--gom-other-market"])[1]
    assert "Sẽ xoá (--gom-other-market)" in out and "TỔNG sẽ dọn: 3 bài" in out


def test_cong_brand_tat_hoac_du_an_ngoai_vn(kho, monkeypatch):
    monkeypatch.setitem(DU_AN, "cau_hinh", {"hashtag_can_nhac_brand": False})
    out = _chay(["hapas"])[1]
    assert "KHÔNG có tín hiệu brand — XOÁ, không vào sổ: 0 bài" in out and "TẮT" in out
    monkeypatch.setitem(DU_AN, "cau_hinh", {})
    monkeypatch.setitem(DU_AN, "thi_truong", "TH")
    out = _chay(["hapas", "--gom-other-market"])[1]
    assert "dự án VN — NGƯỜI QUYẾT (có thể là ghi chú thị trường VN): 0 bài" in out
    assert "TỔNG sẽ dọn: 2 bài" in out


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


def test_ap_dung_mac_dinh_chi_xoa_a_khong_vao_so_roi_hoan_tac(kho, tmp_path):
    """(a) xoá mà KHÔNG ghi sổ (soát M1: kho không biết lần giữ theo luật là AI "không rõ" hay AI
    hết giờ — lượt sau AI phán lại một lần); (b) mặc định chỉ liệt kê; nguồn đã duyệt giữ."""
    TDA.ghi_loai("hapas", _dau(), [("tiktok:999", "ai:lac_de", NGAY)],
                 NGAY - datetime.timedelta(days=1))
    tep = tmp_path / "loc.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tep)])
    assert ma == 0 and "Đã dọn 2/2 bài ((a) không nhắc brand 2, (b) other_market 0)" in out
    con = {k[1] for k in kho.t["bai"]}
    assert con == {"tiktok:2", "tiktok:3", "tiktok:4", "threads:5", "tiktok:6", "youtube:7",
                   "tiktok:9", "tiktok:10", "tiktok:11", "tiktok:12"}
    assert {k[1] for k in kho.t["binh_luan"]} == {"tiktok:2", "tiktok:6", "tiktok:10"}
    assert {k[1] for k in kho.t["chi_so_ngay"]} == {"tiktok:2", "tiktok:6"}
    assert kho.khoa_luot == [K.so_khoa_luot("hapas")] * 2
    assert _so() == {"tiktok:999": "ai:lac_de"}, "sổ của lượt quét giữ nguyên, (a) không vào sổ"
    assert _so("hapas:web") == {}
    dong = [json.loads(x) for x in tep.read_text(encoding="utf-8").splitlines()]
    assert [x["loai_dong"] for x in dong] == ["dau"] + ["bai", "da_ap"] * 2
    assert dong[0]["gom_other_market"] is False
    tv = next(x for x in dong if x.get("khoa") == "tiktok:1" and x["loai_dong"] == "bai")
    assert len(tv["binh_luan"]) == 2 and len(tv["chi_so_ngay"]) == 2
    assert tv["so"] == {} and tv["nhom"] == "khong_brand"
    assert "REVOKE DELETE ON bai FROM mark" in out
    assert "Không có bài nào để dọn" in _chay(
        ["hapas", "--ap-dung", "--sao-luu", str(tmp_path / "lan2.jsonl")])[1]
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and "chèn lại 2 bài, 2 dòng chi_so_ngay, 2 bình luận" in out
    assert len(kho.t["bai"]) == 12 and len(kho.t["binh_luan"]) == 5
    goc = {(r["du_an"], r["khoa"]): r for r in _kho_mau()[0]}
    for k in [("hapas", "tiktok:1"), ("hapas", "web:8")]:
        assert kho.t["bai"][k]["dang_luc"] == goc[k]["dang_luc"]
        assert kho.t["bai"][k]["ly_do_giu"] == goc[k]["ly_do_giu"]
    assert _so() == {"tiktok:999": "ai:lac_de"}
    assert "chèn lại 0 bài" in _chay(["hapas", "--hoan-tac", str(tep)])[1]


def test_gom_other_market_vao_so_giu_so_cu_va_khoa_on_dinh_facebook(kho, tmp_path):
    fb = {**_bai("facebook:pfbid0abc", "trang.th", "HAPAS Thailand sale", ly="other_market",
                 p="facebook"),
          "link": "https://www.facebook.com/trang.th/posts/pfbid0abc", "ma_so_fb": "1234567890"}
    kho.t["bai"][("hapas", fb["khoa"])] = fb
    TDA.ghi_loai("hapas", _dau(), [("tiktok:999", "ai:lac_de", NGAY)],
                 NGAY - datetime.timedelta(days=1))
    tep = tmp_path / "gom.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--gom-other-market", "--sao-luu", str(tep)])
    assert ma == 0 and "(a) không nhắc brand 2, (b) other_market 2)" in out
    so = _so()
    assert so.pop("tiktok:999") == "ai:lac_de", "sổ lượt quét còn nguyên (cùng dấu luật)"
    assert so.pop("tiktok:6") == "ai:other_market" and so.pop("facebook:pfbid0abc") == \
        "ai:other_market"
    assert so.pop("facebook:id:1234567890") == "ai:other_market", "khoá ổn định Facebook"
    assert all(k.startswith("facebook:nd:") and v == "ai:other_market" for k, v in so.items())
    dong = [json.loads(x) for x in tep.read_text(encoding="utf-8").splitlines()]
    x = next(x for x in dong if x.get("khoa") == "facebook:pfbid0abc" and x["loai_dong"] == "bai")
    assert "facebook:id:1234567890" in x["so"]["hapas"]
    assert ("hapas", "tiktok:4") in kho.t["bai"] and ("hapas", "tiktok:10") in kho.t["bai"]
    _chay(["hapas", "--hoan-tac", str(tep)])
    assert _so() == {"tiktok:999": "ai:lac_de"} and len(kho.t["bai"]) == 13


def test_doc_lai_trong_giao_dich_bai_doi_thi_giu(kho, tmp_path):
    """Giữa chạy thử và khoá dòng: lượt quét giữ lại bài Tử Vi với mã AI (brand); bài web thành bài
    của nguồn đã duyệt → không dọn."""
    def doi(k):
        k.t["bai"][("hapas", "tiktok:1")]["ly_do_giu"] = "brand"
        k.t["bai"][("hapas", "web:8")]["nguon_id"] = 2
    kho.truoc_khoa = doi
    _, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tmp_path / "x.jsonl")])
    assert "Đã dọn 0/2 bài" in out and "2 bài đã đổi / không còn" in out
    assert ("hapas", "tiktok:1") in kho.t["bai"] and ("hapas", "web:8") in kho.t["bai"]


def test_luot_mo_ngay_truoc_khoa_thi_dung_khong_xoa(kho, tmp_path):
    def mo(k):
        k.luot_chay.append(77)
    kho.truoc_khoa = mo
    tep = tmp_path / "y.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--sao-luu", str(tep)])
    assert ma == 1 and "DỪNG" in out and len(kho.t["bai"]) == 12
    assert [json.loads(x)["loai_dong"] for x in tep.read_text(encoding="utf-8").splitlines()] \
        == ["dau"]


def test_hoan_tac_bai_chua_co_dau_da_ap_va_in_cau_xoa_bigquery(kho, tmp_path):
    kho.dong_bo = 12
    tep = tmp_path / "z.jsonl"
    ma, out = _chay(["hapas", "--ap-dung", "--gom-other-market", "--sao-luu", str(tep)])
    assert ma == 0 and "ĐÃ đồng bộ" in out
    assert ("DELETE FROM `<dataset>.binh_luan` WHERE du_an = 'hapas' AND khoa_bai IN "
            "('tiktok:1', 'web:8', 'tiktok:6');") in out
    dong = [x for x in tep.read_text(encoding="utf-8").splitlines()
            if json.loads(x)["loai_dong"] != "da_ap"]
    tep.write_text("\n".join(dong) + "\n", encoding="utf-8")
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and "chèn lại 3 bài" in out and "3 bài không có dấu đã áp" in out
    assert len(kho.t["bai"]) == 12 and _so() == {}
