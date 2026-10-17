"""Script một lần `scripts/lang_nghe_gop_bai_fb.py` (17/10/2026): gộp bài Facebook trùng (pfbid đổi
mỗi lượt cào) đã nằm trong kho. Kho GIẢ trong bộ nhớ: nhận câu SQL theo thẻ `/* gop:<tên> */`,
mỗi `ket_noi()` là một giao dịch (lỗi thì trả lại như cũ), xoá bài thì bình luận + chỉ số ngày
xoá theo (FK ON DELETE CASCADE như schema.sql)."""
from __future__ import annotations

import copy
import datetime
import json
import re
import sys
from pathlib import Path

import pytest

import lang_nghe_db as K

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lang_nghe_gop_bai_fb as G

UTC = datetime.timezone.utc
LUC = datetime.datetime(2026, 10, 5, 8, 12, 7, tzinfo=UTC)          # 05/10 15:12 giờ VN
BAY_GIO = datetime.datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
CHU = "Bộ sưu tập túi mới về, giảm 20% cho đơn đầu tiên tại cửa hàng HAPAS"
NGAY = datetime.date(2026, 10, 16)


def _bai(khoa, **kw):
    r = {"du_an": "hapas", "khoa": f"facebook:{khoa}", "nen_tang": "facebook", "nguon_id": 3,
         "kieu_quet": "theo_doi",
         "link": f"https://www.facebook.com/hapaschinhhanggiatot/posts/{khoa}",
         "tac_gia": "hapaschinhhanggiatot", "tai_khoan": "hapaschinhhanggiatot",
         "followers": None, "dang_luc": LUC, "noi_dung": CHU, "hashtag": "",
         "khop_tu_khoa": True, "sac_thai": None, "chu_de": None, "ly_do_giu": "kenh_nha",
         "xem": None, "thich": 10, "binh_luan": 100, "chia_se": 1,
         "thay_lan_dau": BAY_GIO - datetime.timedelta(days=5), "cap_nhat_cuoi": BAY_GIO,
         "luot_dau": 5, "luot_cuoi": 5, "bl_lay_luc": None, "bl_da_lay": None,
         "bl_lay_khi_co": None, "ma_noi_dung": None, "bl_lan_thieu": 0, "kieu_trang": None,
         "muc_nhac": None, "la_pr": None, "ma_so_fb": None}
    r.update(kw)
    return r


def _bl(khoa, ma, **kw):
    r = {"du_an": "hapas", "khoa_bai": f"facebook:{khoa}", "ma": ma, "nen_tang": "facebook",
         "tac_gia": f"khach {ma}", "noi_dung": f"túi đẹp quá {ma}", "thich": 1, "tra_loi": 0,
         "la_tra_loi": False, "cua_thuong_hieu": False,
         "dang_luc": LUC + datetime.timedelta(hours=1), "sac_thai": None, "chu_de": None,
         "luot_id": 5, "thay_lan_dau": BAY_GIO - datetime.timedelta(days=4),
         "cap_nhat_cuoi": BAY_GIO, "loai": "hop_le", "ly_do_loc": None, "ma_noi_dung": None,
         "link": None, "ma_cha": None, "san_pham": None}
    r.update(kw)
    return r


def _cs(khoa, ngay, **kw):
    return {"du_an": "hapas", "khoa": f"facebook:{khoa}", "ngay": ngay, "xem": None,
            "thich": kw.get("thich", 10), "binh_luan": kw.get("binh_luan", 100), "chia_se": 1}


class KhoGia:
    """`bai`, `binh_luan`, `chi_so_ngay`, `luot_quet`, `kiem_do_phu` trong bộ nhớ."""

    def __init__(self, bai=(), bl=(), cs=(), quyen_xoa=True, luot_chay=(), loi_khi=None,
                 luot_mo_truoc_khoa=()):
        self.t = {"bai": {(r["du_an"], r["khoa"]): dict(r) for r in bai},
                  "binh_luan": {(r["du_an"], r["khoa_bai"], r["ma"]): dict(r) for r in bl},
                  "chi_so_ngay": {(r["du_an"], r["khoa"], r["ngay"]): dict(r) for r in cs}}
        self.quyen_xoa, self.luot_chay, self.loi_khi = quyen_xoa, list(luot_chay), loi_khi
        # Lượt /theodoi mở (commit) ngay TRƯỚC khi nhóm lấy được khoá mở lượt — câu kiểm sau
        # khoá phải thấy nó.
        self.luot_mo_truoc_khoa = list(luot_mo_truoc_khoa)
        self.khoa_luot: list = []
        self.chi_doc = False
        self.ghi: list[str] = []

    # một giao dịch
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

    def _cua(self, bang, cot, ds):
        return sorted((r for r in self.t[bang].values() if r[cot] in ds),
                      key=lambda r: (r[cot], str(r.get("ma") or r.get("ngay") or "")))

    def execute(self, sql, ts=()):
        ts = list(ts or [])
        if sql == G.SQL_CHI_DOC:
            self.chi_doc = True
            return self._tra()
        the = re.match(r"/\* gop:(\w+) \*/", sql).group(1)
        if self.loi_khi and the == self.loi_khi:
            raise K.LoiKho("kho lắng nghe báo lỗi (DeadlockDetected: 40P01)")
        doc = the in ("du_an", "bai", "bl", "cs", "dem_bl", "quyen", "luot_chay", "kdp",
                      "dong_bo", "khoa_bai", "khoa_bl", "khoa_cs", "hoan_kiem", "khoa_luot")
        if not doc:
            assert not self.chi_doc, f"ghi ({the}) trong giao dịch chỉ đọc"
            self.ghi.append(the)
        b = self.t["bai"]
        if the == "khoa_luot":
            assert sql.endswith(K._SQL_KHOA_LUOT) and ts == [K.so_khoa_luot("hapas")]
            self.khoa_luot.append(ts[0])
            self.luot_chay += self.luot_mo_truoc_khoa
            self.luot_mo_truoc_khoa = []
            return self._tra()
        if the == "du_an":
            return self._tra([{"ma": "hapas"}] if ts[0] == "hapas" else [])
        if the == "bai":
            return self._tra(sorted((r for r in b.values() if r["nen_tang"] == "facebook"),
                                    key=lambda r: (r["dang_luc"], r["khoa"])))
        if the in ("bl", "khoa_bl"):
            return self._tra(self._cua("binh_luan", "khoa_bai", ts[1]))
        if the in ("cs", "khoa_cs"):
            return self._tra(self._cua("chi_so_ngay", "khoa", ts[1]))
        if the == "khoa_bai":
            return self._tra(sorted((r for r in b.values() if r["khoa"] in ts[1]),
                                    key=lambda r: r["khoa"]))
        if the == "dem_bl":
            return self._tra([{"n": len(self.t["binh_luan"])}])
        if the == "quyen":
            return self._tra([{"xoa": self.quyen_xoa}])
        if the == "luot_chay":
            return self._tra([{"id": i} for i in self.luot_chay])
        if the == "kdp":
            return self._tra([{"n": 0}])
        if the == "dong_bo":
            raise K.LoiKho("kho lắng nghe báo lỗi (InsufficientPrivilege: 42501)")
        if the == "hoan_kiem":
            return self._tra([{"n": sum(1 for r in b.values() if r["khoa"] in ts[1])}])
        if the == "cs_chuyen":
            g, *v, ma, tu, ngay = ts
            r = self.t["chi_so_ngay"].pop((ma, tu, ngay))
            assert (ma, g, ngay) not in self.t["chi_so_ngay"], "trùng khoá chính chi_so_ngay"
            self.t["chi_so_ngay"][(ma, g, ngay)] = {**r, "khoa": g, **dict(zip(G.SO, v))}
            return self._tra(n=1)
        if the == "cs_gop":
            *v, ma, g, ngay = ts
            self.t["chi_so_ngay"][(ma, g, ngay)].update(dict(zip(G.SO, v)))
            return self._tra(n=1)
        if the == "bl_chuyen":
            g, cha, ma, tu, m = ts
            r = self.t["binh_luan"].pop((ma, tu, m))
            assert (ma, g, m) not in self.t["binh_luan"], "trùng khoá chính binh_luan"
            assert (ma, g) in b, "khoá ngoại binh_luan → bai"
            self.t["binh_luan"][(ma, g, m)] = {**r, "khoa_bai": g, "ma_cha": cha,
                                               "cap_nhat_cuoi": "now"}
            return self._tra(n=1)
        if the == "bl_nhan":
            *v, ma, g, m = ts
            self.t["binh_luan"][(ma, g, m)].update(dict(zip(G.NHAN_BL, v)), cap_nhat_cuoi="now")
            return self._tra(n=1)
        if the == "sua_bai":
            # "k = %s" hoặc "k = (SELECT id FROM <bảng> WHERE id = %s)" — truy vấn con không có ", ".
            phan = sql.split(" SET ", 1)[1].split(", cap_nhat_cuoi = now()")[0]
            cot = [x.split(" = ", 1)[0] for x in phan.split(", ")]
            *v, ma, g = ts
            assert len(cot) == len(v)
            b[(ma, g)].update(dict(zip(cot, v)), cap_nhat_cuoi="now")
            return self._tra(n=1)
        if the == "xoa_bai":
            assert self.quyen_xoa, "DELETE không có quyền"
            ma, ds = ts
            xoa = [k for k, r in b.items() if r["du_an"] == ma and r["khoa"] in ds]
            for k in xoa:
                del b[k]
            for bang, cot in (("binh_luan", "khoa_bai"), ("chi_so_ngay", "khoa")):
                self.t[bang] = {k: r for k, r in self.t[bang].items()
                                if (r["du_an"], r[cot]) in b}          # ON DELETE CASCADE
            return self._tra(n=len(xoa))
        if the.startswith("hoan_") and sql.split("*/ ", 1)[1].startswith("INSERT INTO"):
            bang = re.search(r"INSERT INTO (\w+) \(([^)]*)\)", sql)
            cot = bang.group(2).split(", ")
            r = dict(zip(cot, ts))
            if "now()" in sql.split(" VALUES ", 1)[1]:
                assert cot[-1] == "cap_nhat_cuoi" and len(ts) == len(cot) - 1
                r["cap_nhat_cuoi"] = "now"
            k = {"bai": ("du_an", "khoa"), "binh_luan": ("du_an", "khoa_bai", "ma"),
                 "chi_so_ngay": ("du_an", "khoa", "ngay")}[bang.group(1)]
            kk = tuple(r[x] for x in k)
            if kk in self.t[bang.group(1)]:
                return self._tra(n=0)
            self.t[bang.group(1)][kk] = r
            return self._tra(n=1)
        if the in ("hoan_giu", "hoan_bl_nhan"):
            cot = re.findall(r"(\w+) = CASE WHEN", sql)
            *cap, ma, g = ts[:len(cot) * 2 + 2] if the == "hoan_giu" else ts[:-1]
            r = b[(ma, g)] if the == "hoan_giu" else self.t["binh_luan"][(ma, g, ts[-1])]
            for i, c_ in enumerate(cot):
                if r.get(c_) == cap[2 * i]:
                    r[c_] = cap[2 * i + 1]
            r["cap_nhat_cuoi"] = "now"
            return self._tra(n=1)
        if the in ("hoan_cs_chuyen", "hoan_cs_gop"):
            if the == "hoan_cs_chuyen":
                tu, *rest = ts
            else:
                tu, rest = None, ts
            v_cu, (ma, g, ngay), v_moi = rest[:4], rest[4:7], rest[7:]
            r = self.t["chi_so_ngay"].get((ma, g, ngay))
            if r is None or [r[k] for k in G.SO] != v_moi:
                return self._tra(n=0)
            if tu:
                del self.t["chi_so_ngay"][(ma, g, ngay)]
                self.t["chi_so_ngay"][(ma, tu, ngay)] = {**r, "khoa": tu}
                r = self.t["chi_so_ngay"][(ma, tu, ngay)]
            r.update(dict(zip(G.SO, v_cu)))
            return self._tra(n=1)
        if the == "hoan_bl_chuyen":
            tu, cha, ma, g, m = ts
            r = self.t["binh_luan"].pop((ma, g, m))
            self.t["binh_luan"][(ma, tu, m)] = {**r, "khoa_bai": tu, "ma_cha": cha}
            return self._tra(n=1)
        raise AssertionError(f"câu SQL lạ: {sql[:90]}")


def _kho_mau(**kw):
    """hapaschinhhanggiatot 05/10 15:12: 3 bản (bình luận báo / đã cào 100/93, 100/94, 91/20) +
    bản tìm theo từ khoá 16/09 + hai cặp cùng phút KHÔNG gộp (khác chữ; ảnh không chữ)."""
    t2 = LUC - datetime.timedelta(days=19)
    bai = [
        _bai("pfbidA", bl_da_lay=93, thich=12, thay_lan_dau=BAY_GIO - datetime.timedelta(days=9),
             luot_dau=3, luot_cuoi=7, bl_lay_luc=BAY_GIO, bl_lay_khi_co=100),
        _bai("pfbidB", bl_da_lay=94, thich=24, luot_dau=4, luot_cuoi=8, bl_lay_luc=BAY_GIO,
             bl_lay_khi_co=100, sac_thai=None),
        _bai("pfbidC", bl_da_lay=20, thich=25, binh_luan=91, luot_dau=6, luot_cuoi=9,
             sac_thai="Tích cực", chu_de="Sản phẩm"),
        _bai("pfbidT", kieu_quet="tu_khoa", tai_khoan="", tac_gia="HAPAS - Chính Hãng Giá Tốt",
             nguon_id=None, dang_luc=t2, bl_da_lay=166, binh_luan=171, ly_do_giu="brand"),
        _bai("pfbidU", dang_luc=t2, bl_da_lay=20, binh_luan=167, ma_so_fb="1019155114466781"),
        _bai("pfbidX", dang_luc=LUC + datetime.timedelta(days=1)),
        _bai("pfbidY", dang_luc=LUC + datetime.timedelta(days=1),
             noi_dung="Minigame tháng 10: bình luận để nhận quà từ HAPAS ngay hôm nay nhé"),
        _bai("pfbidP", dang_luc=LUC + datetime.timedelta(days=2), noi_dung="📸"),
        _bai("pfbidQ", dang_luc=LUC + datetime.timedelta(days=2), noi_dung="📸"),
    ]
    bl = [
        _bl("pfbidB", "c1", sac_thai="Tích cực", chu_de="Sản phẩm/chất lượng"),
        _bl("pfbidB", "c2"),
        _bl("pfbidA", "c1"),                                     # cùng mã với dòng của B
        _bl("pfbidA", "c2", sac_thai="Trung lập", chu_de="Khác"),  # B thiếu nhãn → nhận nhãn
        _bl("pfbidC", "a9", tac_gia="khach c1", noi_dung="túi đẹp quá c1"),  # cùng người+chữ+giờ
        _bl("pfbidA", "c3", sac_thai="Tiêu cực", chu_de="Giao hàng/dịch vụ"),
        _bl("pfbidC", "c3"),                                      # trùng c3 của A (A có nhãn)
        _bl("pfbidC", "c4", ma_cha="a9", la_tra_loi=True),        # cha bị bỏ → trỏ sang c1
        _bl("pfbidU", "u1"),
    ]
    cs = [_cs("pfbidB", NGAY, thich=24), _cs("pfbidA", NGAY, thich=12, binh_luan=101),
          _cs("pfbidC", NGAY - datetime.timedelta(days=1), thich=25),
          _cs("pfbidU", NGAY)]
    return KhoGia(bai, bl, cs, **kw)


@pytest.fixture
def kho(monkeypatch):
    def tao(**kw):
        k = _kho_mau(**kw)
        monkeypatch.setattr(K, "ket_noi", k)
        return k
    return tao


def _chay(*a):
    ra: list[str] = []
    rc = G.chay(G.tao_parser().parse_args(list(a)), in_ra=ra.append)
    return rc, "\n".join(ra)


# ───────────────────────────── tìm nhóm (thuần) ─────────────────────────────
def test_tim_nhom_dung_luat_va_bao_cap_khong_gop():
    k = _kho_mau()
    nhom, khong = G.tim_nhom(sorted(k.t["bai"].values(), key=lambda r: (r["dang_luc"], r["khoa"])))
    assert sorted(sorted(r["khoa"][9:] for r in g) for g in nhom) == [
        ["pfbidA", "pfbidB", "pfbidC"], ["pfbidT", "pfbidU"]]
    ly = {tuple(sorted(x["khoa"])): x["ly_do"] for x in khong}
    assert ly == {("facebook:pfbidX", "facebook:pfbidY"): "khac_noi_dung",
                  ("facebook:pfbidP", "facebook:pfbidQ"): "khong_co_chu"}


def test_tim_nhom_cung_luat_moi_hai_trang_cung_ten_va_chi_khac_gia():
    """Soát 17/10/2026: script áp CÙNG luật với lúc ghi — hai trang khác nhau cùng tên "HAPAS"
    không gộp (không cùng chủ nên cũng không vào danh sách "cùng chủ cùng phút"); bài cùng trang
    chỉ khác giá là "khác nội dung"."""
    rows = [
        _bai("pfbidA", tai_khoan="hapas.official", tac_gia="HAPAS",
             link="https://www.facebook.com/hapas.official/posts/pfbidA"),
        _bai("pfbidB", tai_khoan="hapasglobal", tac_gia="HAPAS",
             link="https://www.facebook.com/hapasglobal/posts/pfbidB"),
        _bai("pfbidC", noi_dung="Túi HAPAS giá 299k"),
        _bai("pfbidD", noi_dung="Túi HAPAS giá 399k"),
        _bai("pfbidE", noi_dung="Túi  hapas GIÁ 299k"),
    ]
    nhom, khong = G.tim_nhom(rows)
    assert [sorted(r["khoa"][9:] for r in g) for g in nhom] == [["pfbidC", "pfbidE"]]
    ly = {tuple(sorted(x["khoa"])): x["ly_do"] for x in khong}
    assert ly == {("facebook:pfbidC", "facebook:pfbidD"): "khac_noi_dung",
                  ("facebook:pfbidD", "facebook:pfbidE"): "khac_noi_dung"}


def test_chon_ban_giu_bl_da_lay_lon_nhat_hoa_thi_thay_som_nhat():
    a = _bai("a", bl_da_lay=94, thay_lan_dau=BAY_GIO)
    b = _bai("b", bl_da_lay=94, thay_lan_dau=BAY_GIO - datetime.timedelta(days=1))
    assert G.chon_giu([a, b])["khoa"] == "facebook:b"
    assert G.chon_giu([_bai("x", bl_da_lay=None), _bai("y", bl_da_lay=0)])["khoa"] == "facebook:y"
    assert G.chon_giu([_bai("x", thay_lan_dau=None), _bai("y")])["khoa"] == "facebook:y"
    assert G.chon_giu([_bai("a"), _bai("Z")])["khoa"] == "facebook:Z", "theo mã ký tự"
    # Lúc ghi kho chọn bản giữ cùng thứ tự (soát 17/10/2026: NULL từng hoà với 0).
    assert K._THU_TU_GIU == 'COALESCE(bl_da_lay, -1) DESC, thay_lan_dau, khoa COLLATE "C"'
    assert f"ORDER BY {K._THU_TU_GIU} LIMIT 1" in K._SQL_FB_THEO_SO


def test_ke_hoach_gop_so_nhan_binh_luan():
    k = _kho_mau()
    g = [r for r in k.t["bai"].values() if r["khoa"][9:] in ("pfbidA", "pfbidB", "pfbidC")]
    kh = G.ke_hoach(g, list(k.t["binh_luan"].values()), list(k.t["chi_so_ngay"].values()))
    assert kh["giu"] == "facebook:pfbidB" and sorted(kh["bo"]) == ["facebook:pfbidA",
                                                                    "facebook:pfbidC"]
    moi = kh["bai_giu"]["moi"]
    assert moi["thich"] == 25, "số luỹ kế lấy lớn nhất (12 → 24 → 25 như vòng 2)"
    assert "binh_luan" not in moi, "100 đã là lớn nhất (91 của bản C là đọc thiếu)"
    assert moi["thay_lan_dau"] == BAY_GIO - datetime.timedelta(days=9) and moi["luot_dau"] == 3
    assert moi["luot_cuoi"] == 9
    assert moi["sac_thai"] == "Tích cực", "bản giữ chưa có nhãn → lấy của bản khác (cùng bài)"
    chuyen = {(x["tu"][9:], x["ma"]): x for x in kh["bl_chuyen"]}
    assert set(chuyen) == {("pfbidA", "c3"), ("pfbidC", "c4")}
    assert chuyen[("pfbidC", "c4")]["ma_cha_moi"] == "c1", "cha trùng bị bỏ → trỏ dòng giữ"
    assert sorted((b["khoa_bai"][9:], b["ma"]) for b in kh["bl_bo"]) == [
        ("pfbidA", "c1"), ("pfbidA", "c2"), ("pfbidC", "a9"), ("pfbidC", "c3")]
    assert kh["bl_nhan"] == [{"ma": "c2", "cu": {"loai": "hop_le", "ly_do_loc": None,
                                                  "sac_thai": None, "chu_de": None,
                                                  "san_pham": None, "cua_thuong_hieu": False},
                              "moi": {"loai": "hop_le", "ly_do_loc": None,
                                      "sac_thai": "Trung lập", "chu_de": "Khác",
                                      "san_pham": None, "cua_thuong_hieu": False}}]
    assert "bl_da_lay" not in moi, "max(94, 2 dòng của B + 2 dòng chuyển) = 94: không đổi"
    cs = {(x["kieu"], x["ngay"]): x for x in kh["cs_doi"]}
    assert cs[("gop", NGAY)]["moi"]["binh_luan"] == 101 and cs[("gop", NGAY)]["moi"]["thich"] == 24
    assert cs[("chuyen", NGAY - datetime.timedelta(days=1))]["tu"] == "facebook:pfbidC"


def test_ban_tim_tu_khoa_va_ban_theo_doi_gop_dien_id_va_kieu_quet():
    k = _kho_mau()
    g = [r for r in k.t["bai"].values() if r["khoa"][9:] in ("pfbidT", "pfbidU")]
    kh = G.ke_hoach(g, list(k.t["binh_luan"].values()), [])
    assert kh["giu"] == "facebook:pfbidT"                           # đã cào 166 > 20
    moi = kh["bai_giu"]["moi"]
    assert moi["kieu_quet"] == "theo_doi" and moi["nguon_id"] == 3
    assert moi["tai_khoan"] == "hapaschinhhanggiatot" and moi["ma_so_fb"] == "1019155114466781"
    assert "ly_do_giu" not in moi, "nhãn của bản giữ"


# ───────────────────────────── chạy thử / áp dụng / hoàn tác ─────────────────────────────
def test_chay_thu_chi_doc_va_in_so(kho):
    k = kho(quyen_xoa=False)
    rc, out = _chay("hapas")
    assert rc == 0 and k.ghi == []
    assert "Nhóm trùng sẽ gộp: 2 nhóm, 5 dòng → bỏ 3 dòng, giữ 2." in out
    assert "chuyển sang bản giữ 3; bỏ trùng 4" in out and "nhận nhãn của bản trùng 1" in out
    assert "KHÔNG gộp: 2 cặp" in out and "khác nội dung" in out and "không có chữ" in out
    assert "GRANT DELETE ON bai TO mark" in out and "không đọc được" in out
    assert "#" in out and "khach c1" not in out, "tác giả bình luận đã băm"


def test_ap_dung_roi_chay_lai_roi_hoan_tac(kho, tmp_path):
    k = kho()
    goc = copy.deepcopy(k.t)
    tep = tmp_path / "gop.jsonl"
    rc, out = _chay("hapas", "--ap-dung", "--sao-luu", str(tep))
    assert rc == 0 and "Đã gộp 2/2 nhóm" in out, out
    bai = {r["khoa"][9:]: r for r in k.t["bai"].values()}
    assert set(bai) == {"pfbidB", "pfbidT", "pfbidX", "pfbidY", "pfbidP", "pfbidQ"}
    assert bai["pfbidB"]["thich"] == 25 and bai["pfbidB"]["cap_nhat_cuoi"] == "now"
    assert (bai["pfbidB"]["luot_dau"], bai["pfbidB"]["luot_cuoi"]) == (3, 9)
    assert (bai["pfbidB"]["sac_thai"], bai["pfbidB"]["bl_da_lay"]) == ("Tích cực", 94)
    assert (bai["pfbidT"]["ma_so_fb"], bai["pfbidT"]["nguon_id"]) == ("1019155114466781", 3)
    assert bai["pfbidT"]["kieu_quet"] == "theo_doi" and bai["pfbidX"]["cap_nhat_cuoi"] == BAY_GIO
    bl = {(r["khoa_bai"][9:], r["ma"]): r for r in k.t["binh_luan"].values()}
    assert set(bl) == {("pfbidB", "c1"), ("pfbidB", "c2"), ("pfbidB", "c3"), ("pfbidB", "c4"),
                       ("pfbidT", "u1")}
    assert bl[("pfbidB", "c2")]["sac_thai"] == "Trung lập" and bl[("pfbidB", "c4")]["ma_cha"] == "c1"
    assert bl[("pfbidB", "c3")]["sac_thai"] == "Tiêu cực", "giữ dòng có nhãn"
    cs = {(r["khoa"][9:], r["ngay"]): r for r in k.t["chi_so_ngay"].values()}
    assert set(cs) == {("pfbidB", NGAY), ("pfbidB", NGAY - datetime.timedelta(days=1)),
                       ("pfbidT", NGAY)}
    # Tệp hoàn tác: đủ dòng bài bị xoá + bình luận bị đổi / xoá.
    dong = [json.loads(x) for x in tep.read_text(encoding="utf-8").splitlines()]
    assert dong[0]["loai_dong"] == "dau" and len(dong) == 5
    assert [x["loai_dong"] for x in dong[1:]] == ["nhom", "da_ap", "nhom", "da_ap"], \
        "dấu đã áp ghi SAU kế hoạch (sau commit)"
    nhom = next(x for x in dong[1:] if x["loai_dong"] == "nhom" and x["giu"] == "facebook:pfbidB")
    assert {r["khoa"] for r in nhom["bai_bo"]} == {"facebook:pfbidA", "facebook:pfbidC"}
    assert all(set(r) == set(goc["bai"][("hapas", "facebook:pfbidA")]) for r in nhom["bai_bo"])
    assert len(nhom["bl_bo"]) == 4 and len(nhom["bl_chuyen"]) == 2
    # Chạy lại an toàn: không còn nhóm.
    rc, out = _chay("hapas", "--ap-dung", "--sao-luu", str(tmp_path / "lan2.jsonl"))
    assert rc == 0 and "Không có nhóm nào để gộp." in out
    # Hoàn tác: kho về như cũ (trừ mốc cap_nhat_cuoi).
    rc, out = _chay("hapas", "--hoan-tac", str(tep))
    assert rc == 0 and "trả lại 2/2 nhóm" in out, out

    def bo_moc(t):
        return {b: {k_: {c: v for c, v in r.items() if c != "cap_nhat_cuoi"}
                    for k_, r in rows.items()} for b, rows in t.items()}
    assert bo_moc(k.t) == bo_moc(goc)
    assert k.t["bai"][("hapas", "facebook:pfbidA")]["cap_nhat_cuoi"] == "now", \
        "dòng chèn lại mang mốc mới (đồng bộ BigQuery lấy lại)"
    rc, out = _chay("hapas", "--hoan-tac", str(tep))
    assert "trả lại 0/2 nhóm; 2 nhóm bỏ qua" in out, "hoàn tác hai lần không hỏng gì"


def test_hoan_tac_giu_so_moi_cua_luot_quet_sau(kho, tmp_path):
    k = kho()
    tep = tmp_path / "gop.jsonl"
    _chay("hapas", "--ap-dung", "--sao-luu", str(tep))
    k.t["bai"][("hapas", "facebook:pfbidB")]["thich"] = 40          # lượt quét sau đọc số mới
    _chay("hapas", "--hoan-tac", str(tep))
    assert k.t["bai"][("hapas", "facebook:pfbidB")]["thich"] == 40
    assert k.t["bai"][("hapas", "facebook:pfbidB")]["luot_dau"] == 4, "ô không đổi thì trả lại"


def test_ap_dung_can_sao_luu_quyen_va_khong_luot_dang_chay(kho, tmp_path):
    kho()
    assert _chay("hapas", "--ap-dung")[0] == 2
    tep = tmp_path / "co.jsonl"
    tep.write_text("x", encoding="utf-8")
    rc, out = _chay("hapas", "--ap-dung", "--sao-luu", str(tep))
    assert rc == 2 and "đã có" in out
    k = kho(quyen_xoa=False)
    rc, out = _chay("hapas", "--ap-dung", "--sao-luu", str(tmp_path / "a.jsonl"))
    assert rc == 2 and k.ghi == [] and not (tmp_path / "a.jsonl").exists()
    k = kho(luot_chay=[12])
    rc, out = _chay("hapas", "--ap-dung", "--sao-luu", str(tmp_path / "b.jsonl"))
    assert rc == 2 and "đang chạy" in out and k.ghi == []
    assert _chay("khac")[0] == 2


def test_luot_mo_sau_lan_kiem_dau_van_bi_chan_trong_giao_dich(kho, tmp_path):
    """Soát 17/10/2026: kiểm lượt đang quét chỉ ở đầu thì lượt mở ngay sau đó chạy song song với
    phần sửa. Nay mỗi nhóm giữ khoá advisory CÙNG khoá `mo_luot` rồi mới kiểm lại: lượt đã mở
    trước khi có khoá thì thấy và dừng, không ghi gì."""
    k = kho(luot_mo_truoc_khoa=[13])
    goc = copy.deepcopy(k.t)
    rc, out = _chay("hapas", "--ap-dung", "--sao-luu", str(tmp_path / "g.jsonl"))
    assert rc == 1 and "lượt /theodoi vừa bắt đầu — DỪNG" in out, out
    assert k.t == goc and k.ghi == [] and len(k.khoa_luot) == 1
    assert "Đã gộp 0/2 nhóm" in out


def test_mo_luot_giu_cung_khoa_advisory_voi_script(monkeypatch):
    cau: list = []

    class Conn:
        def execute(self, s, ts=()):
            cau.append((s, tuple(ts)))
            return self

        def fetchone(self):
            return {"id": 7}

    import contextlib

    @contextlib.contextmanager
    def ket_noi():
        yield Conn()
    monkeypatch.setattr(K, "ket_noi", ket_noi)
    assert K.mo_luot("hapas", "theo_doi", ma_viec="t1") == 7
    assert cau[0] == (K._SQL_KHOA_LUOT, (K.so_khoa_luot("hapas"),)), "khoá TRƯỚC khi mở lượt"
    assert G.SQL_KHOA_LUOT.endswith(K._SQL_KHOA_LUOT)
    assert K.so_khoa_luot("hapas") == K.so_khoa_luot("hapas") != K.so_khoa_luot("khac")
    assert -2 ** 63 <= K.so_khoa_luot("hapas") < 2 ** 63


def test_hoan_tac_in_tung_nhom_bo_qua_va_ca_mot_phan(kho, tmp_path):
    k = kho()
    tep = tmp_path / "gop.jsonl"
    _chay("hapas", "--ap-dung", "--sao-luu", str(tep))
    # Lượt quét sau ghi lại MỘT khoá cũ của nhóm pfbidB (bản bỏ A) — nhóm chỉ còn một phần.
    a = _bai("pfbidA")
    k.t["bai"][("hapas", a["khoa"])] = a
    rc, out = _chay("hapas", "--hoan-tac", str(tep))
    assert rc == 0 and "trả lại 1/2 nhóm; 1 nhóm bỏ qua (bản bỏ còn trong kho):" in out, out
    assert "bỏ qua …ebook:pfbidB: còn 1/2 bản bỏ trong kho — chỉ MỘT PHẦN có lại" in out
    assert "…ebook:pfbidA" in out and "…ebook:pfbidC" in out
    rc, out = _chay("hapas", "--hoan-tac", str(tep))
    assert "còn 1/1 bản bỏ trong kho — đã hoàn tác hoặc chưa áp" in out


def test_loi_giua_nhom_tra_lai_ca_nhom_va_hoan_tac_bo_qua(kho, tmp_path):
    k = kho(loi_khi="xoa_bai")
    goc = copy.deepcopy(k.t)
    tep = tmp_path / "gop.jsonl"
    rc, out = _chay("hapas", "--ap-dung", "--sao-luu", str(tep))
    assert rc == 1 and "2 nhóm lỗi" in out and k.t == goc, "mỗi nhóm một giao dịch"
    k.loi_khi = None
    rc, out = _chay("hapas", "--hoan-tac", str(tep))
    assert "2 kế hoạch không có dấu đã áp" in out and k.t == goc, \
        "nhóm chưa áp dụng thì hoàn tác không đụng"


def test_hoan_tac_tep_cua_lan_loi_khong_dung_nhom_lan_sau_da_gop(kho, tmp_path):
    """Soát 17/10/2026: lần 1 lỗi (tệp 1 có kế hoạch, không dấu) → lần 2 gộp thật (tệp 2) →
    hoàn tác bằng tệp 1 KHÔNG được áp kế hoạch cũ lên nhóm lần 2 đã gộp."""
    k = kho(loi_khi="xoa_bai")
    _chay("hapas", "--ap-dung", "--sao-luu", str(tmp_path / "1.jsonl"))
    k.loi_khi = None
    assert _chay("hapas", "--ap-dung", "--sao-luu", str(tmp_path / "2.jsonl"))[0] == 0
    sau_gop = copy.deepcopy(k.t)
    rc, out = _chay("hapas", "--hoan-tac", str(tmp_path / "1.jsonl"))
    assert rc == 0 and k.t == sau_gop and "trả lại 0/0 nhóm" in out
    assert "trả lại 2/2 nhóm" in _chay("hapas", "--hoan-tac", str(tmp_path / "2.jsonl"))[1]


def test_khong_gop_bac_cau_qua_ban_khong_id():
    """X1 (id 111) ~ X3 (không id) ~ X2 (id 222): cùng chủ, phút, chữ — actor nói X1, X2 là hai bài
    khác nhau → không gộp cả nhóm, in để xem tay."""
    rows = [_bai("X1", ma_so_fb="1111111"), _bai("X3"), _bai("X2", ma_so_fb="2222222")]
    nhom, khong = G.tim_nhom(rows)
    assert nhom == []
    assert [x["ly_do"] for x in khong if x["ly_do"] == "nhom_nhieu_id"] == ["nhom_nhieu_id"]
    assert sorted(next(x for x in khong if x["ly_do"] == "nhom_nhieu_id")["khoa"]) == [
        "facebook:X1", "facebook:X2", "facebook:X3"]
    nhom, _ = G.tim_nhom([_bai("X1", ma_so_fb="1111111"), _bai("X3")])
    assert len(nhom) == 1, "một id + bản không id: vẫn gộp"


def test_tra_loi_mau_cua_trang_khong_ghep_theo_chu():
    """Trang trả lời mẫu "cảm ơn bạn, check inbox nhé" cho nhiều khách cùng phút: nhiều bình luận
    thật. Ghép theo chữ chỉ cho bình luận GỐC của hai bản bài KHÁC nhau."""
    tl = {"tac_gia": "HAPAS", "noi_dung": "Cảm ơn bạn, check inbox nhé", "la_tra_loi": True}
    bl = [_bl("D", "r1", ma_cha="k1", **tl), _bl("D", "r2", ma_cha="k2", **tl),
          _bl("K", "r3", ma_cha="k3", **tl),
          _bl("D", "g1", tac_gia="An", noi_dung="đẹp"), _bl("D", "g2", tac_gia="An", noi_dung="đẹp"),
          _bl("K", "g3", tac_gia="An", noi_dung="đẹp")]
    cum = sorted(sorted(b["ma"] for b in c) for c in G._cum_binh_luan(bl))
    assert cum == [["g1", "g3"], ["g2"], ["r1"], ["r2"], ["r3"]], \
        "trả lời không ghép theo chữ; một cụm không chứa hai mã của cùng một bản"


def test_nhom_doi_tu_luc_chay_thu_thi_bo_qua(kho, tmp_path):
    k = kho()
    with open(tmp_path / "x.jsonl", "w", encoding="utf-8") as f:
        st, kh = G.ap_dung_nhom("hapas", ["facebook:pfbidA", "facebook:pfbidX"], f)
    assert (st, kh) == ("doi", None) and k.ghi == []


def test_lenh_tren_vps_trong_docstring():
    doc = G.__doc__
    assert "sudo -u mark $PY scripts/lang_nghe_gop_bai_fb.py hapas" in doc
    assert "PY=/opt/mark/hermes-agent/venv/bin/python" in doc and "cd /opt/mark/app" in doc
    assert "GRANT DELETE ON bai TO mark" in doc and "REVOKE DELETE ON bai FROM mark" in doc
