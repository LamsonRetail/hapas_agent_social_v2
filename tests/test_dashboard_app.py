"""Dashboard lắng nghe (đợt 2, 14/10/2026): ứng dụng web `dashboard/app.py`.

Kho GIẢ trong bộ nhớ (cùng tên hàm với `dashboard/kho.py`), Lark giả bằng httpx.MockTransport,
đồng bộ BigQuery giả — không Postgres, không mạng, không mở luồng nền ngoài ý muốn.
Phạm vi chủ dự án chốt: chỉ số + nguồn + ngân sách + người xem (+ trạng thái BigQuery); mọi
POST sửa dữ liệu phải qua phiên + CSRF + vai trò quản lý ở phía máy chủ."""
from __future__ import annotations

import asyncio
import datetime
import json
import re
import threading
from decimal import Decimal
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from dashboard import app as A
from dashboard import dang_nhap as DN
from dashboard.kho import LoiDuLieu

VN = datetime.timezone(datetime.timedelta(hours=7))
KHOA = b"khoa-phien-thu-nghiem-dai-hon-32-ky-tu!!"
TENANT = "t_hapas_thu"
CFG = DN.CauHinh(app_id="cli_dash_thu", app_secret="bi-mat-app", base_url="https://social.hapas.vn",
                 khoa_phien=KHOA, tenant_key=TENANT)
QL, XEM = "quan@hapas.vn", "xem@hapas.vn"


class GiaKho:
    """Bản bộ nhớ của `dashboard.kho`. Mỗi hàm sửa ghi `nk` như kho thật ghi `nhat_ky`."""

    def __init__(self):
        now = datetime.datetime(2026, 10, 14, 9, 0, tzinfo=VN)
        self.du_an = {"hapas": {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"],
                                "tu_loai_tru": [], "boi_canh": "", "thi_truong": "VN",
                                "tran_usd_thang": 5.0, "dang_bat": True, "tao_luc": now,
                                "sua_luc": now, "sua_boi": None, "bl_bat": True,
                                "bl_so_bai": 10, "bl_moi_bai": 20}}
        self.nguon: dict[int, dict] = {}
        self.de_xuat = {
            5: {"id": 5, "du_an": "hapas", "nen_tang": "tiktok", "dinh_danh": "@KolA", "ten": "KOL A",
                "link": "https://www.tiktok.com/@kola", "ly_do": "3 bài nhắc hapas", "so_bai": 3,
                "thao_luan": 40, "trang_thai": "cho", "de_xuat_luc": now, "xu_ly_boi": None,
                "xu_ly_luc": None},
            6: {"id": 6, "du_an": "hapas", "nen_tang": "facebook", "dinh_danh": "facebook.com/x",
                "ten": "X", "link": "", "ly_do": "", "so_bai": 1, "thao_luan": 2,
                "trang_thai": "cho", "de_xuat_luc": now, "xu_ly_boi": None, "xu_ly_luc": None}}
        self.nguoi = {QL: "quan_ly", XEM: "xem"}
        self.nk: list[tuple] = []
        self.bai: list[dict] = []
        self.luot: list[dict] = []
        self.luot_moi_nhat = None
        self.goi_bai: list[tuple] = []
        self.bl: list[dict] = []
        self.goi_bl: list[tuple] = []
        self.goi_bai_khoa: list[tuple] = []
        self.goi_bai_khoa_chu: list[bool] = []
        self.loi_kiem = False

    def _ghi(self, ai, hanh_dong, doi_tuong):
        self.nk.append((ai, hanh_dong, doi_tuong))

    def kiem_tra(self):
        if self.loi_kiem:
            raise RuntimeError("mất kết nối")
        return True

    def vai_tro(self, email):
        return self.nguoi.get(email)

    def cac_du_an(self):
        return [dict(v) for _, v in sorted(self.du_an.items())]

    def doc_du_an(self, ma):
        return dict(self.du_an[ma]) if ma in self.du_an else None

    def them_du_an(self, ai, d):
        if d["ma"] in self.du_an:
            raise LoiDuLieu(f"Mã dự án '{d['ma']}' đã có.")
        self.du_an[d["ma"]] = {**d, "tran_usd_thang": 5.0, "tao_luc": None, "sua_luc": None,
                               "sua_boi": ai}
        self._ghi(ai, "them_du_an", f"du_an:{d['ma']}")

    def sua_du_an(self, ai, ma, d):
        self.du_an[ma].update(d, sua_boi=ai)
        self._ghi(ai, "sua_du_an", f"du_an:{ma}")

    def dat_tran_thang(self, ai, ma, usd):
        self.du_an[ma]["tran_usd_thang"] = usd
        self._ghi(ai, "dat_tran_thang", f"du_an:{ma}")

    def cac_nguon(self, du_an):
        return [dict(n) for n in self.nguon.values() if n["du_an"] == du_an]

    def doc_nguon(self, nid):
        return dict(self.nguon[nid]) if nid in self.nguon else None

    def _trung(self, du_an, d, tru=None):
        return any(n["du_an"] == du_an and n["nen_tang"] == d["nen_tang"]
                   and n["dinh_danh"] == d["dinh_danh"] and n["id"] != tru
                   for n in self.nguon.values())

    def them_nguon(self, ai, du_an, d, them_qua="dashboard"):
        if self._trung(du_an, d):
            raise LoiDuLieu("Nguồn này đã có trong dự án.")
        nid = max(self.nguon, default=0) + 1
        self.nguon[nid] = {"id": nid, "du_an": du_an, **d, "trang_thai": "dang_theo_doi",
                           "them_qua": them_qua, "them_boi": ai, "them_luc": None,
                           "quet_cuoi": None, "loi_cuoi": None, "loi_luc": None}
        if them_qua == "dashboard":
            self._ghi(ai, "them_nguon", f"nguon:{nid}")
        return nid

    def sua_nguon(self, ai, nid, d):
        if self._trung(self.nguon[nid]["du_an"], d, tru=nid):
            raise LoiDuLieu("Dự án đã có nguồn khác trùng định danh này.")
        self.nguon[nid].update(d)
        self._ghi(ai, "sua_nguon", f"nguon:{nid}")

    def doi_trang_thai_nguon(self, ai, nid, tt):
        self.nguon[nid]["trang_thai"] = tt
        self._ghi(ai, "doi_trang_thai_nguon", f"nguon:{nid}")

    def xoa_nguon(self, ai, nid):
        del self.nguon[nid]
        self._ghi(ai, "xoa_nguon", f"nguon:{nid}")

    def cac_de_xuat(self, du_an, trang_thai="cho"):
        return [dict(x) for x in self.de_xuat.values()
                if x["du_an"] == du_an and x["trang_thai"] == trang_thai]

    def doc_de_xuat(self, did):
        return dict(self.de_xuat[did]) if did in self.de_xuat else None

    def duyet_de_xuat(self, ai, did, d):
        x = self.de_xuat[did]
        if x["trang_thai"] != "cho":
            raise LoiDuLieu("Đề xuất này không còn chờ duyệt.")
        x.update(trang_thai="da_duyet", xu_ly_boi=ai)
        nid = None if self._trung(x["du_an"], d) else self.them_nguon(ai, x["du_an"], d, "de_xuat")
        self._ghi(ai, "duyet_de_xuat", f"de_xuat:{did}")
        return nid

    def tu_choi_de_xuat(self, ai, did):
        x = self.de_xuat[did]
        if x["trang_thai"] != "cho":
            raise LoiDuLieu("Đề xuất này không còn chờ duyệt.")
        x.update(trang_thai="tu_choi", xu_ly_boi=ai)
        self._ghi(ai, "tu_choi_de_xuat", f"de_xuat:{did}")

    def bai_trong_khoang(self, du_an, tu, den):
        self.goi_bai.append((du_an, tu, den))
        return {"rows": [b for b in self.bai if tu <= b["dang_luc"] < den], "bi_cat": False}

    def binh_luan_trong_khoang(self, du_an, tu, den):
        self.goi_bl.append((du_an, tu, den))
        return {"rows": [c for c in self.bl if tu <= c["luc"] < den], "bi_cat": False}

    def binh_luan_cua_bai(self, du_an, khoa, toi_da=300):
        return [dict(c) for c in self.bl if c["khoa_bai"] == khoa][:toi_da]

    def bai_theo_khoa(self, du_an, khoa, co_chu=False):
        """Như kho thật: cột hẹp, nội dung + hashtag chỉ khi `co_chu`."""
        self.goi_bai_khoa.append(tuple(khoa))
        self.goi_bai_khoa_chu.append(co_chu)
        bo = () if co_chu else ("noi_dung", "hashtag")
        return [{k: v for k, v in b.items() if k not in bo} for b in self.bai
                if b["khoa"] in set(khoa)]

    def dat_tim_tu_khoa(self, ai, ma, bat, so_bai):
        self.du_an[ma].update(tk_bat=bat, tk_so_bai=so_bai)
        self._ghi(ai, "sua_tim_tu_khoa", f"du_an:{ma}")

    def dat_binh_luan(self, ai, ma, bat, so_bai, moi_bai):
        self.du_an[ma].update(bl_bat=bat, bl_so_bai=so_bai, bl_moi_bai=moi_bai)
        self._ghi(ai, "sua_binh_luan", f"du_an:{ma}")

    def ngu_canh_bai(self, du_an, khoa):
        return {b["khoa"]: {"khoa": b["khoa"], "bai_link": b.get("link"),
                            "bai_noi_dung": b.get("noi_dung"), "bai_dang_luc": b.get("dang_luc")}
                for b in self.bai if b["khoa"] in set(khoa)}

    def dat_cau_hinh(self, ai, ma, cau_hinh):
        self.du_an[ma].update(
            cau_hinh=cau_hinh,
            tk_bat=any(v.get("bat") is True for v in cau_hinh["tu_khoa"].values()),
            bl_bat=any(v.get("bat") is True for v in cau_hinh["binh_luan"].values()))
        self._ghi(ai, "sua_cau_hinh", f"du_an:{ma}")

    def da_tieu_thang(self):
        return {"hapas": 1.25}

    tran_pf = None                     # trần platform (KDLA) — kho thật hiện luôn None

    def tran_platform(self, du_an=None):
        return self.tran_pf

    def cac_luot(self, du_an, trang=1, moi_trang=20):
        ds = [x for x in self.luot if x["du_an"] == du_an]
        return ds[(trang - 1) * moi_trang: trang * moi_trang], len(ds)

    def luot_xong_moi_nhat(self):
        return self.luot_moi_nhat

    def cac_nguoi_xem(self):
        return [{"email": e, "vai_tro": v, "them_boi": None, "them_luc": None}
                for e, v in sorted(self.nguoi.items())]

    def luu_nguoi_xem(self, ai, email, vai_tro):
        self.nguoi[email] = vai_tro
        self._ghi(ai, "luu_nguoi_xem", f"nguoi_xem:{email}")

    def xoa_nguoi_xem(self, ai, email):
        del self.nguoi[email]
        self._ghi(ai, "xoa_nguoi_xem", f"nguoi_xem:{email}")

    def ghi_dang_nhap_lan_dau(self, email, open_id):
        if any(h == "dang_nhap_lan_dau" and d == f"nguoi_xem:{email}" for _, h, d in self.nk):
            return False
        self._ghi(email, "dang_nhap_lan_dau", f"nguoi_xem:{email}")
        self.open_id = open_id
        return True

    def ghi_nhat_ky(self, ai, hanh_dong, doi_tuong, chi_tiet=None):
        self._ghi(ai, hanh_dong, doi_tuong)

    def nhat_ky(self, gioi_han=100):
        return [{"id": i, "luc": None, "ai": a, "hanh_dong": h, "doi_tuong": d, "chi_tiet": {}}
                for i, (a, h, d) in enumerate(self.nk)][:gioi_han]


class GiaDongBo:
    """Giao diện của `dashboard.dong_bo_bq` mà app dùng; `cai_vao` KHÔNG mở luồng."""

    def __init__(self, bat=True, loi_trang_thai=False):
        self.bat, self.loi_trang_thai = bat, loi_trang_thai
        self.so_lan_chay = 0
        self.xong = threading.Event()
        self.app_cai = None

    def da_bat(self):
        return self.bat

    def dataset(self):
        return "ganesha-381907.SOCIAL_LISTENING" if self.bat else ""

    def trang_thai(self):
        if self.loi_trang_thai:
            raise RuntimeError("không nối được kho")
        return {"dataset": self.dataset(), "da_bat": self.bat, "bang": [
            {"bang": "du_an", "moc": None, "lan_cuoi": datetime.datetime(2026, 10, 14, 2, 0,
                                                                         tzinfo=datetime.timezone.utc),
             "so_dong": 1, "loi": None},
            {"bang": "bai", "moc": None, "lan_cuoi": None, "so_dong": None,
             "loi": "Forbidden: <b>quyền</b>"}]}

    def chay(self):
        self.so_lan_chay += 1
        self.xong.set()
        return {"bang": []}

    def cai_vao(self, app):
        self.app_cai = app
        app.state.sau_cap_nhat.append(lambda du_an=None, luot=None: None)


def lark_gia(email_tra=QL, *, ma_token=0, ghi=None, tenant=TENANT, email_dn=""):
    """LarkOAuth thật với HTTP giả: ghi lại yêu cầu để kiểm tham số gửi Lark. `email_tra` là
    email người dùng tự khai, `email_dn` là enterprise_email do tổ chức cấp."""
    ghi = ghi if ghi is not None else []

    def xu_ly(req: httpx.Request):
        ghi.append(req)
        if req.url.path.endswith("/authen/v2/oauth/token"):
            if ma_token:
                return httpx.Response(400, json={"code": ma_token, "error": "invalid_grant"})
            return httpx.Response(200, json={"code": 0, "access_token": "u-token-gia",
                                             "token_type": "Bearer", "expires_in": 7200})
        if req.url.path.endswith("/authen/v1/user_info"):
            return httpx.Response(200, json={"code": 0, "msg": "ok", "data": {
                "name": "Người Thử", "email": email_tra.upper(), "enterprise_email": email_dn,
                "open_id": "ou_thu_1", "tenant_key": tenant}})
        return httpx.Response(404)
    return DN.LarkOAuth(CFG, transport=httpx.MockTransport(xu_ly))


def tao(kho=None, *, dong_bo=None, lark=None, client=("testclient", 50000), **kw):
    kho = kho or GiaKho()
    app = A.tao_app(kho, cau_hinh=CFG, lark=lark or lark_gia(), dong_bo=dong_bo or GiaDongBo(),
                    chu_ky_kiem=None, **kw)
    c = TestClient(app, base_url="https://testserver", follow_redirects=False, client=client)
    return app, c, kho


def dang_nhap(c: TestClient, email: str) -> str:
    """Đặt cookie phiên hợp lệ. -> mã CSRF của phiên."""
    v = DN.tao_phien(email, KHOA)
    c.cookies.set(DN.COOKIE_PHIEN, v)
    return DN.doc_phien(v, KHOA)["csrf"]


def thong_bao(c: TestClient, r) -> str:
    """Theo chuyển hướng 303 và lấy trang có thông báo một lần."""
    assert r.status_code == 303, r.text
    return c.get(r.headers["location"]).text


CONG_KHAI = {"/suc-khoe", "/dang-nhap", "/dang-nhap/lark", "/dang-nhap/xong", "/noi-bo/co-du-lieu"}


def _duong(route: APIRoute) -> str:
    return route.path.replace("{ma}", "hapas").replace("{nid}", "1").replace("{did}", "5")


# ───────────────────────────── công khai + đăng nhập bắt buộc ─────────────────────────────
def test_suc_khoe_khong_can_dang_nhap():
    app, c, kho = tao()
    assert c.get("/suc-khoe").json() == {"ok": True, "db": True}
    kho.loi_kiem = True
    app.state.nho_suc_khoe = (0.0, True)            # hết hạn bộ nhớ 15 giây
    assert c.get("/suc-khoe").json() == {"ok": True, "db": False}


def test_moi_trang_va_api_deu_doi_dang_nhap():
    app, c, kho = tao()
    routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path not in CONG_KHAI]
    assert len(routes) >= 20
    for r in routes:
        for m in r.methods:
            p = _duong(r)
            res = c.request(m, p, data={"csrf": "x"} if m == "POST" else None)
            if m == "GET" and not (p.startswith("/api/") or p == "/su-kien"):
                assert res.status_code == 303, (m, p)
                assert res.headers["location"].startswith("/dang-nhap?sau="), (m, p)
            else:
                assert res.status_code == 401, (m, p, res.status_code)
    assert kho.nk == []


def test_phien_gia_hoac_het_han_coi_nhu_chua_dang_nhap():
    _, c, _ = tao()
    c.cookies.set(DN.COOKIE_PHIEN, DN.tao_phien(QL, b"khoa-khac-" * 4))
    assert c.get("/api/chi-so?du_an=hapas").status_code == 401
    c.cookies.set(DN.COOKIE_PHIEN, DN.tao_phien(QL, KHOA, bay_gio=0))     # hết hạn từ 1970
    assert c.get("/api/chi-so?du_an=hapas").status_code == 401


def test_email_bi_xoa_khoi_nguoi_xem_mat_quyen_ngay():
    _, c, _ = tao()
    dang_nhap(c, "da-bi-xoa@hapas.vn")
    r = c.get("/")
    assert r.status_code == 403 and "Bạn chưa có quyền xem" in r.text
    assert c.get("/api/chi-so?du_an=hapas").status_code == 403


# ───────────────────────────── quyền sửa + CSRF ─────────────────────────────
SUA = [("/du-an/them", {"ma": "moi", "ten": "Mới", "tu_khoa": "moi"}),
       ("/du-an/hapas/sua", {"ten": "HAPAS 2", "tu_khoa": "hapas", "thi_truong": "VN"}),
       ("/nguon/them", {"du_an": "hapas", "nen_tang": "tiktok", "dinh_danh": "@kolb"}),
       ("/nguon/1/sua", {"nen_tang": "tiktok", "dinh_danh": "kolc"}),
       ("/nguon/1/trang-thai", {"trang_thai": "tam_dung"}),
       ("/nguon/1/xoa", {}),
       ("/de-xuat/5/duyet", {"loai": "kol"}),
       ("/de-xuat/6/tu-choi", {}),
       ("/ngan-sach/hapas", {"tran_usd_thang": "7"}),
       ("/nguoi-xem/them", {"email": "moi@hapas.vn", "vai_tro": "xem"}),
       ("/nguoi-xem/xoa", {"email": XEM}),
       ("/bigquery/dong-bo", {})]


def _co_nguon(kho: GiaKho):
    kho.them_nguon("seed", "hapas", {"nen_tang": "tiktok", "dinh_danh": "kola", "ten": "KOL A",
                                     "link": "", "loai": "kol", "nhan": [], "chu_ky_ngay": 1,
                                     "so_bai_moi_lan": 5})
    kho.nk.clear()


def test_nguoi_chi_xem_khong_sua_duoc_gi():
    dong_bo = GiaDongBo()
    _, c, kho = tao(dong_bo=dong_bo)
    _co_nguon(kho)
    truoc = (json.dumps(kho.du_an, default=str), json.dumps(kho.nguon, default=str),
             json.dumps(kho.de_xuat, default=str), dict(kho.nguoi))
    csrf = dang_nhap(c, XEM)
    for duong, form in SUA:
        r = c.post(duong, data={"csrf": csrf, **form})
        assert r.status_code == 403, duong
        assert "Chỉ người quản lý" in r.text, duong
    assert c.get("/nguoi-xem").status_code == 403
    assert kho.nk == [] and dong_bo.so_lan_chay == 0
    assert truoc == (json.dumps(kho.du_an, default=str), json.dumps(kho.nguon, default=str),
                     json.dumps(kho.de_xuat, default=str), dict(kho.nguoi))


@pytest.mark.parametrize("csrf_gui", [None, "", "sai-ma"])
def test_csrf_sai_bi_tu_choi(csrf_gui):
    _, c, kho = tao()
    dang_nhap(c, QL)
    data = {"du_an": "hapas", "nen_tang": "tiktok", "dinh_danh": "kolb"}
    if csrf_gui is not None:
        data["csrf"] = csrf_gui
    r = c.post("/nguon/them", data=data)
    assert r.status_code == 403 and "Biểu mẫu đã hết hạn" in r.text
    assert kho.nguon == {} and kho.nk == []


def test_csrf_cua_phien_khac_va_origin_la_bi_tu_choi():
    _, c, kho = tao()
    csrf_cu = dang_nhap(c, QL)
    dang_nhap(c, QL)                                   # phiên mới -> mã CSRF mới
    data = {"du_an": "hapas", "nen_tang": "tiktok", "dinh_danh": "kolb"}
    assert c.post("/nguon/them", data={**data, "csrf": csrf_cu}).status_code == 403
    csrf = DN.doc_phien(c.cookies.get(DN.COOKIE_PHIEN), KHOA)["csrf"]
    r = c.post("/nguon/them", data={**data, "csrf": csrf},
               headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert kho.nguon == {}
    r = c.post("/nguon/them", data={**data, "csrf": csrf},
               headers={"Origin": "https://social.hapas.vn"})
    assert r.status_code == 303 and len(kho.nguon) == 1


# ───────────────────────────── nguồn + đề xuất ─────────────────────────────
def test_them_nguon_tu_link_dan_va_bao_loi_link_bai():
    _, c, kho = tao()
    csrf = dang_nhap(c, QL)
    r = c.post("/nguon/them", data={"csrf": csrf, "du_an": "hapas", "nen_tang": "tiktok",
                                    "dinh_danh": "https://www.tiktok.com/@Hapas.Official?lang=vi",
                                    "loai": "kenh_nha", "chu_ky_ngay": "2", "so_bai_moi_lan": "10"})
    assert "Đã thêm nguồn TikTok hapas.official" in thong_bao(c, r)
    (n,) = kho.nguon.values()
    assert (n["dinh_danh"], n["loai"], n["chu_ky_ngay"], n["so_bai_moi_lan"], n["them_boi"]) == \
        ("hapas.official", "kenh_nha", 2, 10, QL)
    assert kho.nk == [(QL, "them_nguon", "nguon:1")]
    r = c.post("/nguon/them", data={"csrf": csrf, "du_an": "hapas", "nen_tang": "instagram",
                                    "dinh_danh": "https://www.instagram.com/p/Cxyz/"})
    trang = thong_bao(c, r)
    assert "link bài/reel Instagram" in trang and len(kho.nguon) == 1
    r = c.post("/nguon/them", data={"csrf": csrf, "du_an": "hapas", "nen_tang": "tiktok",
                                    "dinh_danh": "@HAPAS.official"})
    assert "đã có trong dự án" in thong_bao(c, r) and len(kho.nguon) == 1
    r = c.post("/nguon/them", data={"csrf": csrf, "du_an": "khong-co", "nen_tang": "tiktok",
                                    "dinh_danh": "abc"})
    assert "Không có dự án này" in thong_bao(c, r)


def test_sua_tam_dung_xoa_nguon():
    _, c, kho = tao()
    _co_nguon(kho)
    csrf = dang_nhap(c, QL)
    r = c.post("/nguon/1/sua", data={"csrf": csrf, "nen_tang": "youtube",
                                     "dinh_danh": "https://www.youtube.com/@HapasVN", "loai": "page",
                                     "chu_ky_ngay": "7", "so_bai_moi_lan": "3"})
    assert r.status_code == 303
    assert (kho.nguon[1]["nen_tang"], kho.nguon[1]["dinh_danh"]) == ("youtube", "@hapasvn")
    c.post("/nguon/1/trang-thai", data={"csrf": csrf, "trang_thai": "tam_dung"})
    assert kho.nguon[1]["trang_thai"] == "tam_dung"
    r = c.post("/nguon/1/trang-thai", data={"csrf": csrf, "trang_thai": "xoa_het"})
    assert "Trạng thái không hợp lệ" in thong_bao(c, r)
    c.post("/nguon/1/xoa", data={"csrf": csrf})
    assert kho.nguon == {}
    assert c.post("/nguon/1/xoa", data={"csrf": csrf}).status_code == 404
    assert [x[1] for x in kho.nk] == ["sua_nguon", "doi_trang_thai_nguon", "xoa_nguon"]


def test_duyet_de_xuat_them_nguon_va_danh_dau():
    _, c, kho = tao()
    csrf = dang_nhap(c, QL)
    r = c.post("/de-xuat/5/duyet", data={"csrf": csrf, "loai": "kol"})
    assert "Đã duyệt — thêm nguồn kola" in thong_bao(c, r)
    (n,) = kho.nguon.values()
    assert (n["nen_tang"], n["dinh_danh"], n["loai"], n["them_qua"]) == \
        ("tiktok", "kola", "kol", "de_xuat")
    assert kho.de_xuat[5]["trang_thai"] == "da_duyet" and kho.de_xuat[5]["xu_ly_boi"] == QL
    r = c.post("/de-xuat/5/duyet", data={"csrf": csrf, "loai": "kol"})       # bấm lại
    assert "đã được xử lý" in thong_bao(c, r) and len(kho.nguon) == 1
    r = c.post("/de-xuat/6/tu-choi", data={"csrf": csrf})
    assert r.status_code == 303 and kho.de_xuat[6]["trang_thai"] == "tu_choi"
    assert len(kho.nguon) == 1
    assert [x[1] for x in kho.nk] == ["duyet_de_xuat", "tu_choi_de_xuat"]
    assert c.post("/de-xuat/99/duyet", data={"csrf": csrf}).status_code == 404


def test_them_va_sua_du_an():
    _, c, kho = tao()
    csrf = dang_nhap(c, QL)
    r = c.post("/du-an/them", data={"csrf": csrf, "ma": "DoiThu", "ten": "Đối thủ",
                                    "tu_khoa": "doithu, đối thủ", "thi_truong": "vn",
                                    "dang_bat": "1"})
    assert r.status_code == 303 and r.headers["location"] == "/nguon?du_an=doithu"
    assert kho.du_an["doithu"]["tu_khoa"] == ["doithu", "đối thủ"]
    r = c.post("/du-an/them", data={"csrf": csrf, "ma": "x y", "ten": "Sai", "tu_khoa": "a"})
    assert "Mã dự án" in thong_bao(c, r)
    r = c.post("/du-an/hapas/sua", data={"csrf": csrf, "ten": "HAPAS VN", "tu_khoa": "hapas",
                                         "tu_loai_tru": "guitar", "thi_truong": "VN"})
    assert r.status_code == 303
    assert kho.du_an["hapas"]["ten"] == "HAPAS VN" and kho.du_an["hapas"]["dang_bat"] is False
    assert [x[1] for x in kho.nk] == ["them_du_an", "sua_du_an"]


# ───────────────────────────── ngân sách ─────────────────────────────
@pytest.mark.parametrize("vao", ["-1", "abc", "", "1e9"])
def test_tran_thang_am_hoac_rac_bi_tu_choi(vao):
    _, c, kho = tao()
    csrf = dang_nhap(c, QL)
    r = c.post("/ngan-sach/hapas", data={"csrf": csrf, "tran_usd_thang": vao})
    assert "Trần tháng" in thong_bao(c, r)
    assert kho.du_an["hapas"]["tran_usd_thang"] == 5.0 and kho.nk == []


@pytest.mark.parametrize("vao, ra", [("12,5", Decimal("12.50")), ("0", Decimal("0.00")),
                                     ("100", Decimal("100.00")), ("150", Decimal("150.00"))])
def test_tran_thang_hop_le(vao, ra):
    """Chủ dự án 15/10: "không có giới hạn" — trần tháng không còn trần trên 100 USD."""
    _, c, kho = tao()
    csrf = dang_nhap(c, QL)
    r = c.post("/ngan-sach/hapas", data={"csrf": csrf, "tran_usd_thang": vao})
    assert "Đã đặt trần tháng" in thong_bao(c, r)
    assert kho.du_an["hapas"]["tran_usd_thang"] == ra
    assert kho.nk == [(QL, "dat_tran_thang", "du_an:hapas")]


def test_trang_ngan_sach_hien_da_tieu_va_lich_su():
    _, c, kho = tao()
    kho.luot = [{"id": i, "du_an": "hapas", "kieu": "theo_doi", "ma_viec": f"V{i}",
                 "bat_dau": datetime.datetime(2026, 10, 14, 1, 30, tzinfo=datetime.timezone.utc),
                 "ket_thuc": None, "so_nguon": 3, "so_nguon_loi": 0, "bai_moi": 1234,
                 "bai_cap_nhat": 0, "chi_phi_usd": 0.0123, "trang_thai": "xong", "loi": None,
                 "ghi_chu": None} for i in range(25, 0, -1)]
    dang_nhap(c, XEM)
    t = c.get("/ngan-sach").text
    assert "1,25" in t and "3,75" in t               # đã tiêu 1,25 / trần 5 -> còn 3,75
    assert "14/10/2026 08:30" in t and "1.234" in t and "0,0123" in t   # giờ VN, số kiểu Việt
    assert "Trang 1/2" in t and "tran_usd_thang" not in t   # người xem: không có ô sửa trần
    assert "Trang 2/2" in c.get("/ngan-sach?du_an=hapas&trang=2").text


# ───────────────────────────── người xem ─────────────────────────────
def test_khong_xoa_khong_ha_quan_ly_cuoi():
    _, c, kho = tao()
    csrf = dang_nhap(c, QL)
    r = c.post("/nguoi-xem/xoa", data={"csrf": csrf, "email": QL})
    assert "quản lý cuối cùng" in thong_bao(c, r) and kho.nguoi[QL] == "quan_ly"
    r = c.post("/nguoi-xem/them", data={"csrf": csrf, "email": QL, "vai_tro": "xem"})
    assert "quản lý cuối cùng" in thong_bao(c, r) and kho.nguoi[QL] == "quan_ly"
    assert kho.nk == []
    c.post("/nguoi-xem/them", data={"csrf": csrf, "email": " QL2@Hapas.VN ", "vai_tro": "quan_ly"})
    assert kho.nguoi["ql2@hapas.vn"] == "quan_ly"
    r = c.post("/nguoi-xem/xoa", data={"csrf": csrf, "email": QL})
    assert r.status_code == 303 and QL not in kho.nguoi
    assert [x[1] for x in kho.nk] == ["luu_nguoi_xem", "xoa_nguoi_xem"]
    assert all(x[0] == QL for x in kho.nk)


def test_trang_nguoi_xem_hien_nhat_ky():
    _, c, kho = tao()
    kho.nk.append((QL, "them_nguon", "nguon:<b>1</b>"))
    dang_nhap(c, QL)
    t = c.get("/nguoi-xem").text
    assert "them_nguon" in t and "nguon:&lt;b&gt;1&lt;/b&gt;" in t and "<b>1</b>" not in t


def test_moi_thao_tac_sua_ghi_nhat_ky_dung_nguoi():
    dong_bo = GiaDongBo()
    _, c, kho = tao(dong_bo=dong_bo)
    _co_nguon(kho)
    kho.nguoi["ql2@hapas.vn"] = "quan_ly"
    csrf = dang_nhap(c, QL)
    for duong, form in SUA:
        r = c.post(duong, data={"csrf": csrf, **form})
        assert r.status_code == 303, duong
        assert "thong-bao--loi" not in c.get(r.headers["location"]).text, duong
    assert dong_bo.xong.wait(2)
    hanh_dong = [x[1] for x in kho.nk]
    assert hanh_dong == ["them_du_an", "sua_du_an", "them_nguon", "sua_nguon",
                         "doi_trang_thai_nguon", "xoa_nguon", "duyet_de_xuat", "tu_choi_de_xuat",
                         "dat_tran_thang", "luu_nguoi_xem", "xoa_nguoi_xem", "dong_bo_bq"]
    assert all(x[0] == QL for x in kho.nk)


# ───────────────────────────── trang + API chỉ số ─────────────────────────────
def _bai(luc, **kw):
    return {"khoa": f"tiktok:{luc}", "nen_tang": "tiktok", "nguon_id": 1, "kieu_quet": "theo_doi",
            "link": "https://www.tiktok.com/@a/video/1", "tac_gia": "A", "tai_khoan": "a",
            "followers": None, "dang_luc": luc, "noi_dung": "túi xách", "hashtag": "",
            "sac_thai": "Tích cực", "chu_de": None, "xem": 10, "thich": 1, "binh_luan": 2,
            "chia_se": 0, "nguon_loai": "kol", "nguon_ten": "A", "nguon_dinh_danh": "a",
            "nguon_link": "", **kw}


def test_api_chi_so():
    _, c, kho = tao()
    kho.bai = [_bai(datetime.datetime(2026, 10, 10, 23, 30, tzinfo=VN)),
               _bai(datetime.datetime(2026, 10, 3, 8, 0, tzinfo=VN))]       # kỳ trước
    dang_nhap(c, XEM)
    r = c.get("/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14")
    assert r.status_code == 200
    d = r.json()
    assert d["kpi"]["bai"] == 1 and d["kpi"]["thao_luan"] == 3
    assert d["so_sanh"]["bai"] == {"nay": 1, "truoc": 1, "doi_pt": 0.0}
    assert d["du_an"] == {"ma": "hapas", "ten": "HAPAS"} and d["bi_cat"] is False
    # kho đọc MỘT lần từ 0h ngày đầu kỳ trước tới 0h ngày sau kỳ này, giờ VN
    assert kho.goi_bai[-1] == ("hapas", datetime.datetime(2026, 10, 1, tzinfo=VN),
                               datetime.datetime(2026, 10, 15, tzinfo=VN))
    assert c.get("/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14&nen_tang=facebook"
                 ).json()["kpi"]["bai"] == 0
    for q, ma in (("du_an=khong", 404), ("du_an=hapas&tu=14-10-2026", 400),
                  ("du_an=hapas&tu=2026-10-15&den=2026-10-14", 400),
                  ("du_an=hapas&tu=2025-01-01&den=2026-10-14", 400),
                  ("du_an=hapas&nen_tang=threads", 400), ("du_an=hapas&loai=vip", 400)):
        assert c.get("/api/chi-so?" + q).status_code == ma, q


def test_cac_trang_hien_dung_va_thoat_chu():
    _, c, kho = tao()
    kho.du_an["hapas"]["ten"] = "<script>alert(1)</script>"
    _co_nguon(kho)
    kho.nguon[1]["link"] = "javascript:alert(2)"
    dang_nhap(c, XEM)
    for p in ("/", "/nguon", "/ngan-sach", "/bigquery"):
        r = c.get(p)
        assert r.status_code == 200, p
        assert "<script>alert(1)</script>" not in r.text, p
        assert "Lịch quét đặt ở console platform" in r.text, p
        # Tệp tĩnh có mã phiên bản (băm nội dung): deploy đổi tệp là đổi link — trình duyệt
        # không chạy JS cũ trên HTML mới (lỗi thật 15/10/2026).
        assert re.search(r'href="/tinh/giao_dien\.css\?v=[0-9a-f]{10}"', r.text), p
        assert "content-security-policy" in r.headers and r.headers["cache-control"] == "no-store"
    v = re.search(r'/tinh/chi_so\.js\?v=([0-9a-f]{10})', c.get("/").text).group(1)
    assert "immutable" in c.get(f"/tinh/chi_so.js?v={v}").headers["cache-control"]
    assert c.get("/tinh/chi_so.js").headers["cache-control"] == "no-cache"   # link trần: hỏi lại
    t = c.get("/").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in t
    assert f'src="/tinh/echarts.min.js" integrity="{A.ECHARTS_SRI}"' in t
    assert str(A.json_script({"x": "</script><b>&"})) == \
        '{"x": "\\u003c/script\\u003e\\u003cb\\u003e\\u0026"}'
    t = c.get("/nguon").text
    assert 'href="javascript:' not in t
    assert "Thêm nguồn" not in t and "Duyệt" not in t               # người xem: không có nút sửa
    assert "Người xem" not in c.get("/").text.split("<main")[0]       # mục chỉ cho quản lý
    dang_nhap(c, QL)
    t = c.get("/nguon").text
    assert "Thêm nguồn" in t and "Duyệt" in t and "Thêm dự án mới" in t
    assert 'href="/nguoi-xem"' in c.get("/").text


def test_trang_chi_so_giu_du_khoi_va_an_toan_csp():
    """Trang Chỉ số thiết kế lại (15/10/2026): CSS riêng, giữ đủ mọi khối (KPI, thảo luận, sắc thái,
    từ khoá, chủ đề, nền tảng, loại nguồn, nguồn/bài nổi bật, luồng bình luận, ngăn chi tiết);
    không script nội dòng / on*= (CSP script-src 'self'); JS không chèn HTML từ dữ liệu MXH và
    chỉ nhận link http(s)."""
    import re
    _, c, _ = tao()
    dang_nhap(c, XEM)
    t = c.get("/").text
    assert re.search(r'href="/tinh/chi_so\.css\?v=[0-9a-f]{10}"', t)
    assert c.get("/tinh/chi_so.css").status_code == 200
    for ma in ("kpi", "ky-truoc", "bd-xu-huong", "bd-sac-thai", "bd-sac-thai-tg", "tk-may", "tk-bang",
               "chu-de", "nen-tang", "loai-nguon", "tab-nen-tang", "top-nguon", "top-bai", "khoi-bl",
               "kpi-bl", "loai-bl", "bl-tim", "bl-truong", "bl-sap-xep", "bl-ds", "chi-tiet",
               "loi-tai", "canh-bao", "canh-bao-bl"):
        assert f'id="{ma}"' in t, ma
    for m in re.finditer(r"<script([^>]*)>(.*?)</script>", t, re.S):
        assert "src=" in m.group(1) or 'type="application/json"' in m.group(1), m.group(0)[:80]
    assert not re.search(r"\son[a-z]+=", t)
    js = (A.THU_MUC / "static" / "chi_so.js").read_text(encoding="utf-8")
    for cam in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert cam not in js, cam
    assert "/^https?:\\/\\//i" in js and 'a.rel = "noopener noreferrer"' in js


def test_khong_co_trang_ky_nang_hay_cong_tac_cua_mark():
    """Phạm vi chủ dự án chốt: dashboard KHÔNG quản lý kỹ năng/persona/công tắc/lịch của Mark."""
    app, _, _ = tao()
    duong = {r.path for r in app.routes if isinstance(r, APIRoute)}
    for cam in ("ky-nang", "skill", "persona", "cong-tac", "lich", "schedule", "tran-luot"):
        assert not any(cam in p for p in duong), cam


# ───────────────────────────── BigQuery ─────────────────────────────
def test_trang_bigquery_nguoi_xem_thay_nhung_khong_bam_duoc():
    dong_bo = GiaDongBo()
    app, c, kho = tao(dong_bo=dong_bo)
    assert dong_bo.app_cai is app and len(app.state.sau_cap_nhat) == 1   # đã gắn hook
    csrf = dang_nhap(c, XEM)
    t = c.get("/bigquery").text
    assert "ganesha-381907.SOCIAL_LISTENING" in t and "14/10/2026 09:00" in t
    assert "Forbidden" not in t and A.LOI_CHUNG in t           # người xem: chỉ dấu "có lỗi"
    assert "Đồng bộ ngay" not in t
    assert "11 nhãn" in t and "nhật ký" in t
    assert c.post("/bigquery/dong-bo", data={"csrf": csrf}).status_code == 403
    assert dong_bo.so_lan_chay == 0 and kho.nk == []
    dang_nhap(c, QL)
    assert "Forbidden: &lt;b&gt;quyền&lt;/b&gt;" in c.get("/bigquery").text   # quản lý: chữ thô, đã thoát


def test_quan_ly_bam_dong_bo_chay_mot_lan():
    dong_bo = GiaDongBo()
    _, c, kho = tao(dong_bo=dong_bo)
    csrf = dang_nhap(c, QL)
    assert "Đồng bộ ngay" in c.get("/bigquery").text
    r = c.post("/bigquery/dong-bo", data={"csrf": csrf})
    assert "Đã bắt đầu đồng bộ" in thong_bao(c, r)
    assert dong_bo.xong.wait(2) and dong_bo.so_lan_chay == 1
    assert kho.nk == [(QL, "dong_bo_bq", "bigquery")]


def test_bigquery_chua_bat_va_loi_trang_thai():
    dong_bo = GiaDongBo(bat=False)
    _, c, kho = tao(dong_bo=dong_bo)
    csrf = dang_nhap(c, QL)
    t = c.get("/bigquery").text
    assert "chưa bật — thiếu BQ_DATASET" in t and "disabled" in t
    r = c.post("/bigquery/dong-bo", data={"csrf": csrf})
    assert "Đồng bộ chưa bật" in thong_bao(c, r)
    assert dong_bo.so_lan_chay == 0 and kho.nk == []
    _, c2, _ = tao(dong_bo=GiaDongBo(loi_trang_thai=True))
    dang_nhap(c2, XEM)
    r = c2.get("/bigquery")
    assert r.status_code == 200 and "Chưa đọc được trạng thái đồng bộ (RuntimeError)" in r.text


# ───────────────────────────── báo nội bộ + thời gian thực ─────────────────────────────
def test_bao_noi_bo_chi_nhan_loopback_dung_khoa(monkeypatch):
    goi = []
    body = {"du_an": "hapas", "luot": 42}
    monkeypatch.delenv("LANG_NGHE_BAO_KHOA", raising=False)
    app, c, _ = tao(client=("127.0.0.1", 40000))
    app.state.sau_cap_nhat.append(lambda du_an, luot: goi.append((du_an, luot)))
    assert c.post("/noi-bo/co-du-lieu", json=body, headers={"X-Lang-Nghe-Khoa": ""}).status_code == 403
    monkeypatch.setenv("LANG_NGHE_BAO_KHOA", "khoa-bao-dung")
    assert c.post("/noi-bo/co-du-lieu", json=body).status_code == 403
    assert c.post("/noi-bo/co-du-lieu", json=body,
                  headers={"X-Lang-Nghe-Khoa": "khoa-sai"}).status_code == 403
    assert c.post("/noi-bo/co-du-lieu", json=body, headers={
        "X-Lang-Nghe-Khoa": "khoa-bao-dung", "X-Forwarded-For": "1.2.3.4"}).status_code == 403
    assert goi == []
    r = c.post("/noi-bo/co-du-lieu", json=body, headers={"X-Lang-Nghe-Khoa": "khoa-bao-dung"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert goi == [("hapas", 42)]                               # hook BigQuery chạy sau cap-nhat
    assert c.post("/noi-bo/co-du-lieu", content=b"{hong",
                  headers={"X-Lang-Nghe-Khoa": "khoa-bao-dung"}).status_code == 400
    _, c6, _ = tao(client=("::1", 40000))
    assert c6.post("/noi-bo/co-du-lieu", json=body,
                   headers={"X-Lang-Nghe-Khoa": "khoa-bao-dung"}).status_code == 200
    _, cx, _ = tao(client=("10.0.0.8", 40000))
    assert cx.post("/noi-bo/co-du-lieu", json=body,
                   headers={"X-Lang-Nghe-Khoa": "khoa-bao-dung"}).status_code == 403


def test_su_kien_sse():
    _, c, _ = tao(sse_toi_da_su_kien=0)
    assert c.get("/su-kien").status_code == 401
    dang_nhap(c, XEM)
    r = c.get("/su-kien")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert "event: xin-chao" in r.text


def test_bang_tin_phat_toi_trinh_duyet_dang_mo():
    async def chay():
        bt = A.BangTin(toi_da=1)
        q = bt.dang_ky()
        assert bt.dang_ky() is None                     # quá số kết nối
        bt.phat("cap-nhat", {"du_an": "hapas", "luot": 3})
        assert q.get_nowait() == ("cap-nhat", {"du_an": "hapas", "luot": 3})
        bt.huy(q)
        assert bt.so_ket_noi == 0
    asyncio.run(chay())


def test_vong_kiem_phat_khi_co_luot_moi_mot_lan():
    app, _, kho = tao()
    goi = []
    app.state.sau_cap_nhat.append(lambda du_an, luot: goi.append((du_an, luot)))

    async def kiem():
        r = await A.kiem_mot_lan(app)
        await asyncio.gather(*list(app.state.viec_nen))
        return r
    t = datetime.datetime(2026, 10, 14, 8, 0, tzinfo=VN)
    kho.luot_moi_nhat = {"id": 10, "du_an": "hapas", "ket_thuc": t}
    assert asyncio.run(kiem()) is False                   # lần đầu: chỉ ghi mốc
    assert asyncio.run(kiem()) is False                   # không đổi
    kho.luot_moi_nhat = {"id": 11, "du_an": "hapas", "ket_thuc": t}
    assert asyncio.run(kiem()) is True and goi == [("hapas", 11)]
    A.bao_cap_nhat(app, "hapas", 12)                      # Mark đã báo lượt 12 qua /noi-bo
    kho.luot_moi_nhat = {"id": 12, "du_an": "hapas", "ket_thuc": t}
    assert asyncio.run(kiem()) is False and goi == [("hapas", 11)]


def test_vong_kiem_chay_trong_vong_doi_ung_dung():
    kho = GiaKho()
    goi = threading.Event()
    app = A.tao_app(kho, cau_hinh=CFG, lark=lark_gia(), dong_bo=GiaDongBo(), chu_ky_kiem=0.01)
    app.state.sau_cap_nhat.append(lambda du_an, luot: goi.set())
    t = datetime.datetime(2026, 10, 14, 8, 0, tzinfo=VN)
    kho.luot_moi_nhat = {"id": 1, "du_an": "hapas", "ket_thuc": t}
    with TestClient(app, base_url="https://testserver") as c:
        assert c.get("/suc-khoe").status_code == 200
        kho.luot_moi_nhat = {"id": 2, "du_an": "hapas", "ket_thuc": t}
        assert goi.wait(3)


def test_thieu_cau_hinh_thi_khong_khoi_dong(monkeypatch):
    for k in ("DASH_LARK_APP_ID", "DASH_LARK_APP_SECRET", "DASH_BASE_URL", "DASH_SESSION_KEY",
              "DASH_LARK_TENANT_KEY", "LANG_NGHE_BAO_KHOA"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="DASH_SESSION_KEY.*DASH_LARK_TENANT_KEY"):
        A.tao_app(GiaKho(), dong_bo=GiaDongBo(), chu_ky_kiem=None)
    monkeypatch.setenv("DASH_LARK_APP_ID", "cli_x")
    monkeypatch.setenv("DASH_LARK_APP_SECRET", "s")
    monkeypatch.setenv("DASH_BASE_URL", "https://social.hapas.vn/")
    monkeypatch.setenv("DASH_LARK_TENANT_KEY", "t_hapas")
    for sai in ("ab" * 15, "x" * 64, "khoa-phien-dai-nhung-khong-phai-hex-chut-nao!!"):
        monkeypatch.setenv("DASH_SESSION_KEY", sai)            # ngắn / không phải hex
        with pytest.raises(RuntimeError, match="32 ký tự hex"):
            DN.CauHinh.tu_env()
    monkeypatch.setenv("DASH_SESSION_KEY", "a1" * 32)
    cfg = DN.CauHinh.tu_env()
    assert cfg.redirect_uri == "https://social.hapas.vn/dang-nhap/xong" and cfg.cookie_secure
    assert cfg.tenant_key == "t_hapas"
    monkeypatch.setenv("DASH_BASE_URL", "http://social.hapas.vn")
    with pytest.raises(RuntimeError, match="https"):
        DN.CauHinh.tu_env()


@pytest.mark.parametrize("khoa_bao, chu", [
    ("a1" * 32, "KHÁC"), ("A1" * 32, "KHÁC"),                  # trùng khoá phiên (kể cả hoa/thường)
    ("ab" * 10, "32 ký tự hex"), ("khong-phai-hex-" * 4, "32 ký tự hex")])
def test_khoa_bao_trung_hoac_yeu_thi_khong_khoi_dong(monkeypatch, khoa_bao, chu):
    """Khoá báo nằm cả trong .env của Mark: trùng khoá phiên thì ai đọc .env của Mark cũng ký
    được phiên quản lý — dashboard từ chối khởi động."""
    for k, v in (("DASH_LARK_APP_ID", "cli_x"), ("DASH_LARK_APP_SECRET", "s"),
                 ("DASH_BASE_URL", "https://social.hapas.vn"), ("DASH_LARK_TENANT_KEY", "t"),
                 ("DASH_SESSION_KEY", "a1" * 32), ("LANG_NGHE_BAO_KHOA", khoa_bao)):
        monkeypatch.setenv(k, v)
    with pytest.raises(RuntimeError, match=chu):
        DN.CauHinh.tu_env()
    monkeypatch.setenv("LANG_NGHE_BAO_KHOA", "b2" * 32)
    assert DN.CauHinh.tu_env().khoa_phien == ("a1" * 32).encode()
    monkeypatch.setenv("LANG_NGHE_BAO_KHOA", "")              # trống = tắt đường báo, vẫn chạy
    DN.CauHinh.tu_env()


def test_bao_noi_bo_tu_choi_khi_khoa_bao_trung_khoa_phien(monkeypatch):
    monkeypatch.setenv("LANG_NGHE_BAO_KHOA", KHOA.decode())
    _, c, _ = tao(client=("127.0.0.1", 40000))
    r = c.post("/noi-bo/co-du-lieu", json={"du_an": "hapas", "luot": 1},
               headers={"X-Lang-Nghe-Khoa": KHOA.decode()})
    assert r.status_code == 403


def test_phien_8_gio():
    assert DN.PHIEN_GIAY == 8 * 3600
    v = DN.tao_phien(QL, KHOA, bay_gio=1_000_000)
    assert DN.doc_phien(v, KHOA, bay_gio=1_000_000 + 8 * 3600 - 1)
    assert DN.doc_phien(v, KHOA, bay_gio=1_000_000 + 8 * 3600 + 1) is None


# ───────────────────────────── đăng nhập Lark ─────────────────────────────
def _bat_dau(c: TestClient, sau="/nguon?du_an=hapas") -> str:
    r = c.get("/dang-nhap/lark", params={"sau": sau})
    assert r.status_code == 302
    u = urlsplit(r.headers["location"])
    assert (u.scheme, u.netloc, u.path) == ("https", "accounts.larksuite.com",
                                            "/open-apis/authen/v1/authorize")
    q = parse_qs(u.query)
    assert q["client_id"] == ["cli_dash_thu"]
    assert q["redirect_uri"] == ["https://social.hapas.vn/dang-nhap/xong"]
    assert "bi-mat-app" not in r.headers["location"]
    return q["state"][0]


def test_dang_nhap_thanh_cong_gui_dung_tham_so_lark():
    ghi = []
    _, c, _ = tao(lark=lark_gia(QL, ghi=ghi))
    state = _bat_dau(c)
    r = c.get("/dang-nhap/xong", params={"code": "ma-1", "state": state})
    assert r.status_code == 303 and r.headers["location"] == "/nguon?du_an=hapas"
    phien = DN.doc_phien(c.cookies.get(DN.COOKIE_PHIEN), KHOA)
    assert phien["email"] == QL                         # chữ thường
    sc = r.headers.get_list("set-cookie")
    assert any("ln_phien=" in x and "HttpOnly" in x and "Secure" in x and "samesite=lax" in x.lower()
               for x in sc)
    token_req, user_req = ghi
    assert json.loads(token_req.content) == {
        "grant_type": "authorization_code", "client_id": "cli_dash_thu",
        "client_secret": "bi-mat-app", "code": "ma-1",
        "redirect_uri": "https://social.hapas.vn/dang-nhap/xong"}
    assert str(token_req.url) == "https://open.larksuite.com/open-apis/authen/v2/oauth/token"
    assert user_req.headers["authorization"] == "Bearer u-token-gia"
    assert c.get("/").status_code == 200


def test_dang_nhap_tu_choi_state_sai_va_email_la():
    _, c, _ = tao(lark=lark_gia("nguoi-la@khac.vn"))
    state = _bat_dau(c)
    for q in ({"code": "x", "state": state + "x"}, {"code": "x", "state": "a.b"},
              {"code": "x"}, {"error": "access_denied", "state": state}):
        r = c.get("/dang-nhap/xong", params=q)
        assert r.status_code == 400, q
        assert DN.COOKIE_PHIEN not in c.cookies
    # state đúng nhưng trình duyệt KHÁC (không có cookie nonce) -> từ chối (chống login CSRF)
    _, c2, _ = tao(lark=lark_gia(QL))
    assert c2.get("/dang-nhap/xong", params={"code": "x", "state": state}).status_code == 400
    # lượt hỏng đã xoá nonce (mỗi lượt đăng nhập dùng một lần) — bắt đầu lại; email lạ
    assert DN.COOKIE_NONCE not in c.cookies
    state = _bat_dau(c)
    r = c.get("/dang-nhap/xong", params={"code": "x", "state": state})
    assert r.status_code == 403
    assert "Bạn chưa có quyền xem — nhờ người quản lý thêm email nguoi-la@khac.vn" in r.text
    assert DN.COOKIE_PHIEN not in c.cookies


def test_dang_nhap_lark_loi_va_state_het_han():
    _, c, _ = tao(lark=lark_gia(QL, ma_token=20003))
    state = _bat_dau(c)
    r = c.get("/dang-nhap/xong", params={"code": "x", "state": state})
    assert r.status_code == 502 and "bi-mat-app" not in r.text
    st, nonce = DN.tao_state(KHOA, "/", bay_gio=0)                 # hết hạn từ lâu
    assert DN.doc_state(st, nonce, KHOA) is None


def test_dang_nhap_khong_chuyen_huong_ra_ngoai():
    _, c, _ = tao(lark=lark_gia(QL))
    for sau in ("https://evil.example/x", "//evil.example", "/\\evil.example"):
        state = _bat_dau(c, sau)
        r = c.get("/dang-nhap/xong", params={"code": "x", "state": state})
        assert r.status_code == 303 and r.headers["location"] == "/", sau
    r = c.get("/dang-nhap?sau=//evil.example")
    assert "sau=%2F" in r.text or "sau=/" in r.text
    assert "evil.example" not in r.text


def test_dang_xuat_can_csrf():
    _, c, _ = tao()
    csrf = dang_nhap(c, XEM)
    assert c.post("/dang-xuat", data={"csrf": "sai"}).status_code == 403
    r = c.post("/dang-xuat", data={"csrf": csrf})
    assert r.status_code == 303 and r.headers["location"] == "/dang-nhap"
    assert any(x.startswith("ln_phien=") for x in r.headers.get_list("set-cookie"))


# ───────────────────────────── rà bảo mật 14/10/2026 ─────────────────────────────
def test_dang_nhap_tu_choi_to_chuc_lark_khac():
    """M3: tài khoản tổ chức Lark khác tự khai email trùng người xem -> vẫn bị chặn."""
    for tenant in ("t_to_chuc_khac", ""):
        _, c, kho = tao(lark=lark_gia(QL, tenant=tenant))
        r = c.get("/dang-nhap/xong", params={"code": "x", "state": _bat_dau(c)})
        assert r.status_code == 403 and "không thuộc tổ chức HAPAS" in r.text, tenant
        assert DN.COOKIE_PHIEN not in c.cookies and kho.nk == []


def test_dang_nhap_uu_tien_email_doanh_nghiep_va_ghi_lan_dau():
    """M3: enterprise_email (tổ chức cấp) thắng email tự khai; email tự khai chỉ dùng khi trống.
    Lần đầu đăng nhập ghi open_id vào nhật ký, lần sau không ghi lại."""
    # email tự khai là quản lý nhưng email doanh nghiệp là người lạ -> không vào bằng email tự khai
    _, c, _ = tao(lark=lark_gia(QL, email_dn="nguoi-la@hapas.vn"))
    r = c.get("/dang-nhap/xong", params={"code": "x", "state": _bat_dau(c)})
    assert r.status_code == 403 and "nguoi-la@hapas.vn" in r.text
    _, c, kho = tao(lark=lark_gia("tu-khai@gmail.com", email_dn="XEM@hapas.vn"))
    for _ in range(2):
        r = c.get("/dang-nhap/xong", params={"code": "x", "state": _bat_dau(c)})
        assert r.status_code == 303
        assert DN.doc_phien(c.cookies.get(DN.COOKIE_PHIEN), KHOA)["email"] == XEM
    assert kho.nk == [(XEM, "dang_nhap_lan_dau", f"nguoi_xem:{XEM}")] and kho.open_id == "ou_thu_1"


def test_echarts_tai_cho_dung_hash_va_csp_khong_co_host_ngoai():
    """M2: ECharts phục vụ tại chỗ, đúng tệp đã duyệt; CSP không cho script từ host nào khác."""
    import base64
    import hashlib
    tep = A.THU_MUC / "static" / "echarts.min.js"
    du_lieu = tep.read_bytes()
    so_hex = hashlib.sha256(du_lieu).hexdigest()
    assert so_hex == "e84270bd0cd5bdf60fefc26d00c2a391cb2e81f4d26a7a9ee16185a54773a3cf"
    assert len(du_lieu) == 1_030_855
    assert A.ECHARTS_SRI == "sha256-" + base64.b64encode(bytes.fromhex(so_hex)).decode()
    _, c, _ = tao()
    dang_nhap(c, XEM)
    r = c.get("/")
    csp = r.headers["content-security-policy"]
    script_src = next(p for p in csp.split(";") if p.strip().startswith("script-src"))
    assert script_src.split() == ["script-src", "'self'"]
    assert "http" not in csp and "jsdelivr" not in r.text
    assert c.get("/tinh/echarts.min.js").status_code == 200


def test_api_chi_so_ban_thi_503_va_nho_dem():
    """M1: tối đa 2 lượt tính cùng lúc; kết quả nhớ theo mốc lượt quét mới nhất."""
    app, c, kho = tao()
    kho.bai = [_bai(datetime.datetime(2026, 10, 10, 9, 0, tzinfo=VN))]
    dang_nhap(c, XEM)
    url = "/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14"
    assert c.get(url).status_code == 200 and len(kho.goi_bai) == 1
    assert c.get(url).json()["kpi"]["bai"] == 1 and len(kho.goi_bai) == 1     # từ bộ nhớ
    kho.luot_moi_nhat = {"id": 7, "du_an": "hapas", "ket_thuc": "x"}            # có lượt mới
    assert c.get(url).status_code == 200 and len(kho.goi_bai) == 2
    # đang có 2 lượt tính dở -> lượt thứ 3 (chưa có trong bộ nhớ) bị từ chối, không xếp hàng
    assert app.state.ban.acquire(blocking=False) and app.state.ban.acquire(blocking=False)
    try:
        r = c.get(url + "&nen_tang=tiktok")
        assert r.status_code == 503 and r.headers["retry-after"] == "5"
        assert c.get(url).status_code == 200                                    # bộ nhớ vẫn phục vụ
    finally:
        app.state.ban.release()
        app.state.ban.release()
    assert c.get(url + "&nen_tang=tiktok").status_code == 200


def test_api_chi_so_bao_bi_cat():
    _, c, kho = tao()
    kho.bai_trong_khoang = lambda du_an, tu, den: {"rows": [], "bi_cat": True}
    dang_nhap(c, XEM)
    assert c.get("/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14").json()["bi_cat"] is True


def test_khoang_mac_dinh_la_ngay_tron_toi_hom_qua():
    """L7: mặc định 30 ngày trọn tới hết hôm qua (giờ VN) — so ngày trọn với ngày trọn."""
    _, c, kho = tao()
    dang_nhap(c, XEM)
    hom_nay = A._hom_nay()
    d = c.get("/api/chi-so?du_an=hapas").json()
    assert d["khoang"]["den"] == (hom_nay - datetime.timedelta(days=1)).isoformat()
    assert d["khoang"]["so_ngay"] == 30 and d["ngay_cuoi_chua_tron"] is False
    assert kho.goi_bai[-1][2] == datetime.datetime.combine(hom_nay, datetime.time(0), VN)
    d = c.get(f"/api/chi-so?du_an=hapas&den={hom_nay.isoformat()}").json()
    assert d["ngay_cuoi_chua_tron"] is True
    assert "30 ngày trọn tới hết hôm qua" in c.get("/").text
    assert "ngày chưa hết" in c.get(f"/?den={hom_nay.isoformat()}").text


@pytest.mark.parametrize("q", ["den=9999-12-31", "tu=0001-01-01&den=2026-10-14", "den=1999-12-31",
                               "tu=2101-01-01&den=2101-01-02"])
def test_ngay_cuc_tri_bi_tu_choi_khong_500(q):
    """L5: năm ngoài 2000–2100 -> 400 (trước đây 9999-12-31 + 1 ngày là lỗi tràn, trang 500)."""
    _, c, _ = tao()
    dang_nhap(c, XEM)
    r = c.get("/api/chi-so?du_an=hapas&" + q)
    assert r.status_code == 400 and "2000–2100" in r.json()["loi"]
    assert c.get("/?" + q).status_code == 200


def test_suc_khoe_nho_ket_qua_15_giay(monkeypatch):
    """M4: /suc-khoe công khai không mở kết nối DB mỗi lần gọi."""
    _, c, kho = tao()
    dem = []
    kho.kiem_tra = lambda: dem.append(1) or True
    for _ in range(5):
        assert c.get("/suc-khoe").json() == {"ok": True, "db": True}
    assert len(dem) == 1
    goc = A.time.monotonic
    monkeypatch.setattr(A.time, "monotonic", lambda: goc() + A.SUC_KHOE_GIAY + 1)
    c.get("/suc-khoe")
    assert len(dem) == 2


def test_sse_tran_moi_nguoi_va_dong_khi_mat_quyen():
    """L2: mỗi người tối đa 5 luồng; luồng đọc lại vai trò định kỳ, bị xoá thì đóng."""
    async def tran():
        bt = A.BangTin(toi_da=200, moi_email=5)
        qs = [bt.dang_ky(QL) for _ in range(5)]
        assert all(qs) and bt.dang_ky(QL) is None and bt.dang_ky(XEM) is not None
        bt.huy(qs[0])
        assert bt.dang_ky(QL) is not None
    asyncio.run(tran())

    kho = GiaKho()
    lan = []
    goc = kho.vai_tro

    def vai_tro(email):                      # lần 1 (mở luồng) còn quyền, lần 2 đã bị xoá
        lan.append(email)
        return goc(email) if len(lan) == 1 else None
    kho.vai_tro = vai_tro
    _, c, _ = tao(kho, sse_kiem_quyen_giay=0.0)
    dang_nhap(c, XEM)
    r = c.get("/su-kien")
    assert r.status_code == 200 and "event: het-quyen" in r.text and len(lan) == 2


def test_nguoi_xem_khong_thay_email_va_loi_tho():
    """L6: email người sửa/thêm và chữ lỗi thô chỉ hiện cho quản lý."""
    _, c, kho = tao()
    _co_nguon(kho)
    kho.du_an["hapas"]["sua_boi"] = "nguoi-sua@hapas.vn"
    kho.nguon[1].update(them_boi="nguoi-them@hapas.vn",
                        loi_cuoi="HTTP 403 /opt/mark/.tokens apify_api_bimat",
                        loi_luc=datetime.datetime(2026, 10, 14, 1, 0, tzinfo=VN))
    kho.luot = [{"id": 1, "du_an": "hapas", "kieu": "theo_doi", "ma_viec": "V1",
                 "bat_dau": datetime.datetime(2026, 10, 14, 1, 0, tzinfo=VN), "ket_thuc": None,
                 "so_nguon": 1, "so_nguon_loi": 1, "bai_moi": 0, "bai_cap_nhat": 0,
                 "chi_phi_usd": 0.0, "trang_thai": "loi", "loi": "Traceback lộ /opt/lang-nghe",
                 "ghi_chu": "ghi chú nội bộ"}]
    bi_mat = ("nguoi-sua@hapas.vn", "nguoi-them@hapas.vn", "apify_api_bimat", "Traceback",
              "ghi chú nội bộ")
    dang_nhap(c, XEM)
    t = c.get("/nguon").text + c.get("/ngan-sach").text
    assert not any(x in t for x in bi_mat)
    assert A.LOI_CHUNG in t
    dang_nhap(c, QL)
    t = c.get("/nguon").text + c.get("/ngan-sach").text
    assert all(x in t for x in bi_mat)


# ───────────────────────────── quản trị chi phí (15/10/2026) ─────────────────────────────
def _kho_co_nguon_ton() -> GiaKho:
    """Cùng bộ nguồn với tests/test_dashboard_chi_phi.py (số tính tay ở đó)."""
    kho = GiaKho()
    for i, p, so_bai, ky, tt in ((1, "tiktok", 10, 1, "dang_theo_doi"),
                                 (2, "instagram", 30, 2, "dang_theo_doi"),
                                 (3, "youtube", 5, 1, "dang_theo_doi"),
                                 (4, "facebook", 5, 3, "tam_dung"),
                                 (5, "facebook", 4, 3, "dang_theo_doi")):
        kho.nguon[i] = {"id": i, "du_an": "hapas", "nen_tang": p, "dinh_danh": f"n{i}",
                        "ten": f"Nguồn {i}", "link": "", "loai": "kol", "nhan": [],
                        "trang_thai": tt, "chu_ky_ngay": ky, "so_bai_moi_lan": so_bai,
                        "them_qua": "dashboard", "them_boi": None, "them_luc": None,
                        "quet_cuoi": None, "loi_cuoi": None, "loi_luc": None}
    return kho


@pytest.fixture
def giua_thang(monkeypatch):
    monkeypatch.setattr(A, "_bay_gio",
                        lambda: datetime.datetime(2026, 10, 15, 12, 0, tzinfo=VN))


def test_ngan_sach_du_bao_trong_tran(giua_thang):
    _, c, _ = tao(_kho_co_nguon_ton())
    dang_nhap(c, XEM)
    t = c.get("/ngan-sach").text
    # đã tiêu 1,25 + còn lại 0,9863 (16,5 ngày) = 2,2363 ≤ trần 5
    assert "Dự báo cả tháng" in t and "2,24" in t and "0,99" in t and "16,5 ngày" in t
    assert "Trần do platform đặt" in t and "chưa có" in t and "chờ KDLA" in t
    assert "Dự báo vượt trần" not in t
    assert "Dự báo theo nền tảng" in t and "0,6435" in t and "0,1716" in t   # TikTok, khởi động IG
    assert "1,79" in t                                                   # theo cấu hình 30 ngày


def test_ngan_sach_canh_bao_vuot_tran_va_goi_y(giua_thang):
    kho = _kho_co_nguon_ton()
    kho.du_an["hapas"]["tran_usd_thang"] = 2.0
    _, c, _ = tao(kho)
    dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert "Dự báo vượt trần 0,24 USD" in t and 'role="alert"' in t and "chu-loi" in t
    i1, i5, i2 = t.index("<b>Nguồn 1</b>"), t.index("<b>Nguồn 5</b>"), t.index("<b>Nguồn 2</b>")
    assert i1 < i5 < i2                                       # 3 nguồn tốn nhất, tốn nhất trước
    assert "<b>Nguồn 3</b>" not in t and "<b>Nguồn 4</b>" not in t   # YouTube 0, tạm dừng
    assert "tăng chu kỳ quét, giảm số bài mỗi lần, hoặc tạm dừng nguồn tốn nhất" in t
    assert "Hoặc tăng trần dự án" in t


def test_ngan_sach_tran_platform_thap_hon_thi_ap_tran_platform(giua_thang):
    kho = _kho_co_nguon_ton()
    kho.tran_pf = 1.0                                 # khi KDLA ra: Mark ghi trần platform vào kho
    _, c, _ = tao(kho)
    dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert "chưa có" not in t and "cấp cửa hàng" in t
    assert "Dự báo vượt trần 1,24 USD" in t and "(2,24 / 1,00 USD)" in t
    assert "đang bị trần platform giữ" in t


def test_trang_nguon_hien_uoc_tinh_moi_nguon(giua_thang):
    _, c, _ = tao(_kho_co_nguon_ton())
    dang_nhap(c, QL)
    t = c.get("/nguon?du_an=hapas").text
    assert "≈ USD/tháng" in t
    assert "≈ 1,170 USD/tháng theo bài" in t                       # TikTok 10 bài, mỗi ngày
    assert "≈ 0,051 USD/tháng theo bài + phí khởi động actor chung 0,0208 USD" in t   # Instagram
    assert "≈ 0,000 USD/tháng theo bài" in t                       # YouTube miễn phí
    assert '<script type="application/json" id="chi-phi-hang-so">' in t and '"he_so": 1.3' in t
    assert 'src="/tinh/nguon.js?v=' in t and t.count("data-uoc-tinh") == 6   # 5 sửa + 1 thêm


# ───────────────────────────── chi tiết + bình luận (đợt 2b) ─────────────────────────────
def _bl(khoa, ma, luc, sac="Tích cực", nha=False, thich=0, chu_de="Sản phẩm/chất lượng"):
    return {"khoa_bai": khoa, "ma": ma, "nen_tang": "tiktok", "tac_gia": "khach", "noi_dung": "ok",
            "thich": thich, "tra_loi": 0, "la_tra_loi": False, "cua_thuong_hieu": nha,
            "dang_luc": luc, "sac_thai": None if nha else sac, "chu_de": None if nha else chu_de,
            "luc": luc, "nguon_loai": "kol", "nguon_id": 1}


def test_api_bai_loc_theo_cot_vua_bam():
    _, c, kho = tao()
    d1 = datetime.datetime(2026, 10, 10, 9, 0, tzinfo=VN)
    d2 = datetime.datetime(2026, 10, 11, 9, 0, tzinfo=VN)
    kho.bai = [_bai(d1, khoa="tiktok:1", binh_luan=50),
               _bai(d1, khoa="tiktok:2", sac_thai="Tiêu cực", binh_luan=1),
               _bai(d2, khoa="tiktok:3", nguon_loai="kenh_nha")]
    dang_nhap(c, XEM)
    q = "/api/bai?du_an=hapas&tu=2026-10-08&den=2026-10-14"
    d = c.get(q + "&ngay_tu=2026-10-10&ngay_den=2026-10-10").json()
    assert d["tong"] == 2 and d["thao_luan"] == 53
    assert [b["khoa"] for b in d["bai"]] == ["tiktok:1", "tiktok:2"]     # nhiều thảo luận trước
    assert c.get(q + "&sac_thai=Tiêu cực").json()["tong"] == 1
    # Đợt 2f: `sac_thai` là bộ lọc CHUNG; sắc thái riêng của điểm vừa bấm (gồm "kênh nhà") là
    # `ct_sac_thai` — AND với bộ lọc chung.
    assert [b["khoa"] for b in c.get(q + "&ct_sac_thai=kênh nhà").json()["bai"]] == ["tiktok:3"]
    assert c.get(q + "&sac_thai=kênh nhà").status_code == 400
    assert c.get(q + "&nguon=n:1").json()["tong"] == 3
    assert c.get(q + "&sac_thai=<script>").status_code == 400
    assert c.get(q + "&ngay_tu=2026-13-01").status_code == 400
    assert c.get("/api/bai?du_an=khong-co").status_code == 404


def test_api_bai_can_dang_nhap():
    _, c, _ = tao()
    assert c.get("/api/bai?du_an=hapas").status_code == 401
    assert c.get("/api/binh-luan?du_an=hapas&khoa=tiktok:1").status_code == 401


def test_api_chi_so_co_khoi_binh_luan_khong_tinh_thuong_hieu():
    _, c, kho = tao()
    luc = datetime.datetime(2026, 10, 10, 9, 0, tzinfo=VN)
    kho.bai = [_bai(luc, khoa="tiktok:1")]
    kho.bl = [_bl("tiktok:1", "a", luc), _bl("tiktok:1", "b", luc, sac="Tiêu cực"),
              _bl("tiktok:1", "c", luc, nha=True)]
    dang_nhap(c, XEM)
    d = c.get("/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14").json()
    k = d["binh_luan_da_cao"]["kpi"]
    assert k["so"] == 3 and k["khach"] == 2 and k["thuong_hieu"] == 1
    assert k["tich_cuc_pt"] == 50.0 and k["tieu_cuc"] == 1
    i = d["binh_luan_da_cao"]["xu_huong"]["moc"].index("2026-10-10")
    assert d["binh_luan_da_cao"]["xu_huong"]["tieu_cuc"][i] == 1


def test_api_binh_luan_theo_bai_va_theo_cot():
    _, c, kho = tao()
    luc = datetime.datetime(2026, 10, 10, 9, 0, tzinfo=VN)
    kho.bl = [_bl("tiktok:1", "a", luc, thich=1), _bl("tiktok:1", "b", luc, sac="Tiêu cực", thich=9),
              _bl("tiktok:2", "c", luc, nha=True)]
    dang_nhap(c, XEM)
    q = "/api/binh-luan?du_an=hapas&tu=2026-10-08&den=2026-10-14"
    d = c.get(q + "&khoa=tiktok:1").json()
    assert d["tong"] == 2 and {x["sac_thai"] for x in d["binh_luan"]} == {"Tích cực", "Tiêu cực"}
    d = c.get(q + "&sac_thai=Tiêu cực&ngay_tu=2026-10-10&ngay_den=2026-10-10").json()
    assert d["tong"] == 1 and d["binh_luan"][0]["thich"] == 9
    d = c.get(q).json()
    assert d["tong"] == 3 and d["binh_luan"][0]["thich"] == 9          # nhiều thích trước
    assert [x["sac_thai"] for x in d["binh_luan"]].count("thương hiệu") == 1
    assert c.get(q + "&sac_thai=kênh nhà").status_code == 400
    assert c.get(q + "&khoa=" + "x" * 300).status_code == 400


def test_api_binh_luan_bo_loc_kieu_kompa():
    """Đợt 2e: luồng bình luận lọc theo trường (nền tảng, nguồn, nhãn, chữ) + đếm facets."""
    _, c, kho = tao()
    luc = datetime.datetime(2026, 10, 10, 9, 0, tzinfo=VN)
    kho.bl = [dict(_bl("tiktok:1", "a", luc, thich=1), noi_dung="Giá bao nhiêu"),
              dict(_bl("tiktok:1", "b", luc, thich=9), nen_tang="facebook", nguon_id=2),
              dict(_bl("tiktok:1", "c", luc), loai="spam")]
    dang_nhap(c, XEM)
    q = "/api/binh-luan?du_an=hapas&tu=2026-10-08&den=2026-10-14"
    d = c.get(q).json()
    assert {g["gia_tri"] for g in d["facets"]["nen_tang"]} == {"tiktok", "facebook"}
    assert {g["gia_tri"]: g["so"] for g in d["facets"]["nguon"]} == {"n:1": 2, "n:2": 1}
    assert c.get(q + "&nen_tang_bl=facebook").json()["tong"] == 1
    assert c.get(q + "&nguon_bl=n:1&loai_bl=hop_le").json()["tong"] == 1
    assert [x["ma"] for x in c.get(q + "&q=gia bao").json()["binh_luan"]] == ["a"]
    assert c.get(q + "&sap_xep=moi").status_code == 200
    for sai in ("&sap_xep=xau", "&nen_tang_bl=myspace", "&loai_bl=xau", "&q=" + "x" * 101,
                "&nguon_bl=" + "x" * 301):
        assert c.get(q + sai).status_code == 400, sai


def test_cau_hinh_binh_luan_chi_quan_ly_va_kiem_so():
    _, c, kho = tao()
    csrf = dang_nhap(c, XEM)
    r = c.post("/ngan-sach/hapas/binh-luan",
               data={"csrf": csrf, "bl_bat": "1", "bl_so_bai": "5", "bl_moi_bai": "30"})
    assert r.status_code == 403
    csrf = dang_nhap(c, QL)
    r = c.post("/ngan-sach/hapas/binh-luan",
               data={"csrf": csrf, "bl_bat": "1", "bl_so_bai": "5", "bl_moi_bai": "30"})
    assert "Đã lưu: cào bình luận tối đa 5 bài mỗi lượt, mỗi bài 30 bình luận" in thong_bao(c, r)
    assert kho.du_an["hapas"]["bl_so_bai"] == 5 and kho.nk[-1][1] == "sua_binh_luan"
    # Không trần trên (chủ dự án 15/10): 500 bài hợp lệ; số âm vẫn bị từ chối.
    r = c.post("/ngan-sach/hapas/binh-luan",
               data={"csrf": csrf, "bl_bat": "1", "bl_so_bai": "500", "bl_moi_bai": "30"})
    assert kho.du_an["hapas"]["bl_so_bai"] == 500
    r = c.post("/ngan-sach/hapas/binh-luan",
               data={"csrf": csrf, "bl_bat": "1", "bl_so_bai": "-1", "bl_moi_bai": "30"})
    assert kho.du_an["hapas"]["bl_so_bai"] == 500 and "từ 0 trở lên" in thong_bao(c, r)
    r = c.post("/ngan-sach/hapas/binh-luan", data={"csrf": csrf, "bl_so_bai": "5", "bl_moi_bai": "30"})
    assert "Đã tắt cào bình luận" in thong_bao(c, r) and kho.du_an["hapas"]["bl_bat"] is False
    assert "Cào bình luận" in c.get("/ngan-sach").text


def test_cau_hinh_tim_tu_khoa():
    _, c, kho = tao()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15)
    csrf = dang_nhap(c, QL)
    r = c.post("/ngan-sach/hapas/tu-khoa", data={"csrf": csrf, "tk_bat": "1", "tk_so_bai": "20"})
    assert "Đã lưu: tìm 1 từ khoá, tối đa 20 bài" in thong_bao(c, r)
    assert kho.du_an["hapas"]["tk_so_bai"] == 20 and kho.nk[-1][1] == "sua_tim_tu_khoa"
    r = c.post("/ngan-sach/hapas/tu-khoa", data={"csrf": csrf, "tk_so_bai": "20"})
    assert "Đã tắt tìm theo từ khoá" in thong_bao(c, r)
    assert "Tìm theo từ khoá" in c.get("/ngan-sach").text
    csrf = dang_nhap(c, XEM)
    assert c.post("/ngan-sach/hapas/tu-khoa",
                  data={"csrf": csrf, "tk_bat": "1", "tk_so_bai": "5"}).status_code == 403


def test_cau_hinh_thu_thap_tung_nen_tang():
    """Đợt 2e: một biểu mẫu cấu hình từng nền tảng (tìm từ khoá + bình luận) + trần tháng."""
    _, c, kho = tao()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15)
    csrf = dang_nhap(c, XEM)
    assert c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf}).status_code == 403
    csrf = dang_nhap(c, QL)
    form = {"csrf": csrf, "tk_tiktok_bat": "1", "tk_tiktok_so_bai": "40",
            "tk_facebook_bat": "1", "tk_facebook_so_bai": "", "tk_instagram_so_tu": "4",
            "bl_tiktok_bat": "1", "bl_tiktok_so_bai": "30", "bl_tiktok_moi_bai": "0",
            "bl_youtube_bat": "1", "bl_youtube_moi_bai": "200", "tran_usd_thang": "8"}
    r = c.post("/ngan-sach/hapas/cau-hinh", data=form)
    assert "Đã lưu cấu hình thu thập" in thong_bao(c, r)
    ch = kho.du_an["hapas"]["cau_hinh"]
    assert ch["tu_khoa"]["tiktok"] == {"bat": True, "so_bai": 40}
    assert ch["tu_khoa"]["facebook"] == {"bat": True}            # ô trống = theo mặc định chung
    assert ch["tu_khoa"]["instagram"] == {"bat": False, "so_tu": 4}
    assert ch["binh_luan"]["tiktok"] == {"bat": True, "so_bai": 30, "moi_bai": 0}
    assert ch["binh_luan"]["youtube"] == {"bat": True, "moi_bai": 200}
    assert ch["binh_luan"]["facebook"] == {"bat": False}
    assert kho.du_an["hapas"]["tran_usd_thang"] == 8.0
    assert [h for _, h, _ in kho.nk[-2:]] == ["sua_cau_hinh", "dat_tran_thang"]
    for sai, loi in (({"bl_tiktok_moi_bai": "3"}, "0 (cào hết) hoặc từ 5"),
                     ({"tk_tiktok_so_bai": "-1"}, "TikTok"),
                     ({"tk_tiktok_so_bai": "1000001"}, "quá lớn"),
                     ({"tk_instagram_so_tu": "0"}, "Instagram")):
        r = c.post("/ngan-sach/hapas/cau-hinh", data={**form, **sai})
        assert loi in thong_bao(c, r)
    assert kho.du_an["hapas"]["cau_hinh"] == ch                  # lỗi: không ghi gì
    t = c.get("/ngan-sach").text
    assert "/ngan-sach/hapas/cau-hinh" in t


def test_ngan_sach_ma_tran_cau_hinh_mot_bieu_mau():
    """Trang Ngân sách (UX 15/10): MỘT biểu mẫu ma trận nền tảng × (tìm từ khoá, bình luận) + trần
    tháng thay các biểu mẫu cũ; ô trống = mặc định dự án (placeholder), ô đặt riêng giữ giá trị;
    ước tính USD/lượt dựng sẵn từ `bang_cau_hinh`; người xem chỉ thấy bảng đọc, không có ô sửa."""
    import re
    kho = GiaKho()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15,
                              cau_hinh={"tu_khoa": {"facebook": {"bat": True, "so_bai": 40}},
                                        "binh_luan": {"youtube": {"bat": False}}})
    _, c, _ = tao(kho)
    dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert t.count('action="/ngan-sach/hapas/cau-hinh"') == 1
    assert 'action="/ngan-sach/hapas/tu-khoa"' not in t and 'action="/ngan-sach/hapas/binh-luan"' not in t
    for p in ("tiktok", "facebook", "instagram", "youtube"):
        for o in ("tk_{}_bat", "tk_{}_so_bai", "bl_{}_bat", "bl_{}_so_bai", "bl_{}_moi_bai"):
            assert f'name="{o.format(p)}"' in t, o.format(p)
    assert 'name="tk_instagram_so_tu"' in t and 'name="tran_usd_thang"' in t
    assert re.search(r'name="tk_tiktok_so_bai" min="0" max="1000000"[^>]*placeholder="15" value=""', t)
    assert re.search(r'name="tk_facebook_so_bai"[^>]*value="40"', t)            # đặt riêng
    assert re.search(r'name="tk_facebook_bat" value="1"[^>]*checked', t)
    assert re.search(r'name="bl_youtube_bat" value="1" aria-label="[^"]*">', t)  # tắt: không checked
    # Facebook 40 bài: ước tính KHÔNG kẹp ở 20 (dashboard không biết gói Apify) —
    # (40 × 0,00259 + 0,00005) × 1,3 = 0,1347; gói FREE chỉ là ghi chú trên dòng Facebook
    assert 'data-o="tk-facebook" data-usd="0.1347"' in t
    assert "Gói Apify FREE: thực tế tối đa 20 bài/lượt" in t
    assert '<script type="application/json" id="ns-du-lieu">' in t and 'src="/tinh/ngan_sach.js?v=' in t
    dang_nhap(c, XEM)
    t = c.get("/ngan-sach").text
    assert "Tìm theo từ khoá" in t and "Cào bình luận" in t and 'data-usd="0.1347"' in t
    assert "ns-du-lieu" not in t and 'name="tk_' not in t and "/cau-hinh" not in t


def test_ngan_sach_nhieu_du_an_co_bang_tong_quan():
    kho = GiaKho()
    kho.du_an["moi"] = {**kho.du_an["hapas"], "ma": "moi", "ten": "Dự án mới", "tran_usd_thang": 0.0}
    _, c, _ = tao(kho)
    dang_nhap(c, XEM)
    t = c.get("/ngan-sach?du_an=hapas").text
    assert "Tất cả dự án" in t and 'href="/ngan-sach?du_an=moi"' in t
    assert t.count('aria-current="true"') == 1 and t.count("ns-tong__than") == 1   # chi tiết: dự án chọn
    t = c.get("/ngan-sach?du_an=khong-co").text
    assert "Tất cả dự án" in t and "ns-tong__than" not in t and "Lịch sử lượt quét" not in t


def test_binh_luan_so_sach_va_loc_theo_loai():
    _, c, kho = tao()
    luc = datetime.datetime(2026, 10, 10, 9, 0, tzinfo=VN)
    kho.bai = [_bai(luc, khoa="tiktok:1", bl_da_lay=4, binh_luan=8, ma_noi_dung="m1"),
               _bai(luc, khoa="tiktok:2", ma_noi_dung="m1"), _bai(luc, khoa="tiktok:3")]
    kho.bl = [dict(_bl("tiktok:1", "a", luc), loai="hop_le"),
              dict(_bl("tiktok:1", "b", luc, sac="Tiêu cực"), loai="spam", ly_do_loc="vay_tien"),
              dict(_bl("tiktok:1", "c", luc), loai="it_noi_dung"),
              dict(_bl("tiktok:1", "d", luc, nha=True), loai="thuong_hieu")]
    dang_nhap(c, XEM)
    d = c.get("/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14").json()
    k = d["binh_luan_da_cao"]["kpi"]
    assert k["so"] == 4 and k["sach"] == 1 and k["da_loc"] == 2 and k["thuong_hieu"] == 1
    assert k["tieu_cuc"] == 0 and k["tich_cuc"] == 1                  # spam không vào sắc thái
    assert {x["loai"] for x in d["binh_luan_da_cao"]["loai"]} == {"hop_le", "spam", "it_noi_dung",
                                                                 "thuong_hieu"}
    assert d["kpi"]["bai_khu_trung"] == 2 and d["kpi"]["bl_da_cao"] == 4
    q = "/api/binh-luan?du_an=hapas&tu=2026-10-08&den=2026-10-14"
    x = c.get(q + "&loai_bl=spam").json()
    assert x["tong"] == 1 and x["binh_luan"][0]["ten_loai"] == "Spam"
    assert x["binh_luan"][0]["ly_do_loc"] == "vay_tien"
    assert c.get(q + "&loai_bl=xau").status_code == 400
    assert c.get(q + "&sac_thai=Tiêu cực").json()["tong"] == 0         # spam bị loại khỏi sắc thái


def test_cau_hinh_cao_het_binh_luan():
    _, c, kho = tao()
    csrf = dang_nhap(c, QL)
    r = c.post("/ngan-sach/hapas/binh-luan",
               data={"csrf": csrf, "bl_bat": "1", "bl_so_bai": "10", "bl_moi_bai": "0"})
    assert "mỗi bài cào HẾT bình luận" in thong_bao(c, r) and kho.du_an["hapas"]["bl_moi_bai"] == 0
    r = c.post("/ngan-sach/hapas/binh-luan",
               data={"csrf": csrf, "bl_bat": "1", "bl_so_bai": "10", "bl_moi_bai": "3"})
    assert "0 (cào hết) hoặc từ 5" in thong_bao(c, r)


def test_loai_binh_luan_khop_mark():
    import loc_rac
    assert A.CS.LOAI_BL == loc_rac.LOAI and A.CS.TEN_LOAI_BL == loc_rac.TEN_LOAI


# ───────────────────────────── bộ lọc chung (đợt 2f) ─────────────────────────────
Q_LOC = "&tu=2026-10-08&den=2026-10-14"


def _kho_loc():
    _, c, kho = tao()
    luc = datetime.datetime(2026, 10, 10, 9, 0, tzinfo=VN)
    kho.bai = [_bai(luc, khoa="tiktok:1", binh_luan=4),                               # KOL
               _bai(luc, khoa="facebook:2", nen_tang="facebook", nguon_id=2, binh_luan=1,
                    nguon_loai="kenh_nha", sac_thai=None),                           # kênh nhà
               _bai(luc, khoa="tiktok:3", nguon_id=None, nguon_loai=None, thich=2000,
                    kieu_quet="tu_khoa", sac_thai="Tiêu cực"),                        # từ khoá
               # Bài CŨ (trước cả kỳ trước) có bình luận mới trong kỳ: chỉ đọc theo khoá khi cần.
               _bai(datetime.datetime(2026, 7, 1, 9, 0, tzinfo=VN), khoa="tiktok:cu",
                    followers=2_000_000)]
    kho.bl = [_bl("tiktok:1", "a", luc), _bl("tiktok:1", "b", luc, sac="Tiêu cực"),
              dict(_bl("facebook:2", "c", luc, sac="Tiêu cực"), nen_tang="facebook",
                   nguon_id=2, nguon_loai="kenh_nha"),
              _bl("tiktok:cu", "d", luc, sac="Tiêu cực")]
    dang_nhap(c, XEM)
    return c, kho


def test_api_chi_so_bo_loc_moi_khoi_va_khoa_nho_rieng():
    c, kho = _kho_loc()
    app = c.app

    def lay(q=""):
        r = c.get("/api/chi-so?du_an=hapas" + Q_LOC + q)
        assert r.status_code == 200, q
        return r.json()
    d = lay("&pham_vi=kenh_nha")
    assert d["kpi"]["bai"] == 1 and d["binh_luan_da_cao"]["kpi"]["so"] == 1
    assert d["bo_loc"]["pham_vi"] == "kenh_nha"
    assert d["bo_loc_dem"]["pham_vi"] == {"kenh_nha": 1, "ben_ngoai": 2}   # bỏ qua chính chiều
    nn = d["nha_ngoai"]
    assert (nn["kenh_nha"]["bai"], nn["ben_ngoai"]["bai"]) == (1, 2)
    assert (nn["kenh_nha"]["bl"], nn["ben_ngoai"]["bl"]) == (1, 3)
    d = lay("&sac_thai=tieu_cuc")
    assert d["kpi"]["bai"] == 1                                      # bài tiêu cực (từ khoá)
    assert d["binh_luan_da_cao"]["kpi"]["tieu_cuc"] == 3             # b, c, d — sắc thái của BL
    assert kho.goi_bai_khoa == []                                    # không cần bài gốc
    # Ảnh hưởng là chiều cấp BÀI: bình luận "d" theo bài cũ 2 triệu follower -> kho đọc đúng
    # MỘT bài thiếu theo khoá (không đọc lại cả khoảng).
    d = lay("&anh_huong=mega")
    assert d["kpi"]["bai"] == 0 and d["binh_luan_da_cao"]["kpi"]["so"] == 1
    assert kho.goi_bai_khoa == [("tiktok:cu",)]
    d = lay("&tuong_tac=1000")
    assert d["kpi"]["bai"] == 1 and d["top_bai"][0]["khoa"] == "tiktok:3"
    # Mỗi bộ lọc một khoá nhớ /api/chi-so; dòng thô đọc MỘT lần cho cả khoảng.
    so_khoa = len(app.state.nho_chi_so)
    assert so_khoa == 4
    lay("&nen_tang=tiktok,facebook")
    lay("&nen_tang=facebook,tiktok")                                 # cùng bộ lọc, khác thứ tự
    assert len(app.state.nho_chi_so) == so_khoa + 1
    assert len(kho.goi_bai) == 1 and len(kho.goi_bl) == 1


@pytest.mark.parametrize("duong", ["chi-so", "bai", "binh-luan"])
@pytest.mark.parametrize("sai", ["pham_vi=nha", "nen_tang=threads", "loai=vip", "sac_thai=vui",
                                 "chu_de=" + "x" * 101, "anh_huong=khong_lo", "tuong_tac=5",
                                 "kieu_quet=x", "q=" + "x" * 101, "nen_tang=tiktok,myspace"])
def test_api_bo_loc_sai_thi_400(duong, sai):
    c, _ = _kho_loc()
    r = c.get(f"/api/{duong}?du_an=hapas{Q_LOC}&{sai}")
    assert r.status_code == 400 and r.json()["loi"], (duong, sai)


def test_api_bai_va_binh_luan_theo_bo_loc_chung():
    c, _ = _kho_loc()
    qb = "/api/bai?du_an=hapas" + Q_LOC
    assert c.get(qb + "&pham_vi=ben_ngoai").json()["tong"] == 2
    # điều kiện của điểm vừa bấm (ct_*) AND bộ lọc chung
    d = c.get(qb + "&pham_vi=ben_ngoai&ct_sac_thai=Tiêu cực").json()
    assert [b["khoa"] for b in d["bai"]] == ["tiktok:3"]
    assert c.get(qb + "&pham_vi=kenh_nha&ct_nen_tang=tiktok").json()["tong"] == 0
    assert c.get(qb + "&ct_nen_tang=threads").status_code == 400
    ql = "/api/binh-luan?du_an=hapas" + Q_LOC
    assert [x["ma"] for x in c.get(ql + "&pham_vi=kenh_nha").json()["binh_luan"]] == ["c"]
    d = c.get(ql + "&sac_thai=tieu_cuc").json()
    assert d["tong"] == 3
    # Facets của luồng tính SAU bộ lọc chung; trường riêng (_bl) AND thêm.
    assert {g["gia_tri"]: g["so"] for g in d["facets"]["nen_tang"]} == {"tiktok": 2, "facebook": 1}
    assert c.get(ql + "&sac_thai=tieu_cuc&nen_tang_bl=facebook").json()["tong"] == 1
    assert [x["ma"] for x in c.get(ql + "&anh_huong=mega").json()["binh_luan"]] == ["d"]
    # Chữ tìm chung: bình luận khớp khi bài của nó khớp ("túi xách" là nội dung mọi bài mẫu).
    assert c.get(ql + "&q=TUI XACH").json()["tong"] == 4
    assert c.get(ql + "&q_bl=zzz").json()["tong"] == 0               # ô tìm riêng của luồng
    assert c.get(ql + "&sac_thai_bl=Tiêu cực&pham_vi=ben_ngoai").json()["tong"] == 2


def test_nho_dong_ngan_sach_dong_lru_va_het_han(monkeypatch):
    """Review 2f: dòng thô giới hạn theo TỔNG SỐ DÒNG; đọc/ghi lại đưa khoá về cuối hàng; quá hạn
    bị bỏ ngay khi tra."""
    gio = [1000.0]
    monkeypatch.setattr(A.time, "monotonic", lambda: gio[0])
    n = A.NhoDong(100, 60)
    n.dat("a", "A", 60)
    n.dat("b", "B", 30)
    assert (len(n), n.so_dong) == (2, 90)
    n.dat("c", "C", 20)                        # 110 > 100: bỏ mục ít dùng nhất (a)
    assert "a" not in n and n.so_dong == 50
    assert n.lay("b") == "B"                   # đọc b -> b về cuối hàng
    n.dat("d", "D", 60)                        # 110: bỏ c, không bỏ b vừa đọc
    assert "c" not in n and "b" in n
    n.dat("b", "B2", 30)                       # ghi lại b -> cuối hàng (trước đây bị bỏ kế tiếp)
    n.dat("e", "E", 20)                        # 110: bỏ d
    assert "d" not in n and n.lay("b") == "B2"
    gio[0] += 61                               # quá hạn: tra là bỏ luôn
    assert n.lay("b") is None and "b" not in n
    n.dat("f", "F", 1)                         # ghi mục mới dọn nốt mục quá hạn
    assert (len(n), n.so_dong) == (1, 1)
    to = A.NhoDong(10, 60)
    to.dat("x", "X", 500)                      # một bộ lớn hơn ngân sách vẫn phục vụ lượt này
    assert to.lay("x") == "X"
    assert A.NHO_DONG_TOI_DA_DONG >= A.BAI_TOI_DA + A.BL_TOI_DA   # ~ một khoảng bài + bình luận


def test_api_dong_tho_giu_trong_ngan_sach_dong():
    c, kho = _kho_loc()
    nho = c.app.state.nho_dong
    assert isinstance(nho, A.NhoDong) and nho.toi_da_dong == A.NHO_DONG_TOI_DA_DONG
    nho.toi_da_dong = 5                        # tí hon: 3 bài + 4 bình luận không cùng nằm được
    assert c.get("/api/chi-so?du_an=hapas" + Q_LOC).status_code == 200
    assert nho.so_dong <= 5 and len(kho.goi_bai) == 1
    assert c.get("/api/bai?du_an=hapas" + Q_LOC).status_code == 200
    assert len(kho.goi_bai) == 2 and nho.so_dong <= 5    # bộ bài đã bị bỏ để giữ ngân sách


def test_api_bai_goc_thieu_nho_theo_moc_chi_doc_khoa_moi():
    """Review 2f: bài gốc thiếu nhớ theo CÙNG mốc lượt quét với dòng đã đọc, lượt sau chỉ đọc khoá
    chưa có; cột chữ chỉ khi lọc chữ; mốc lượt quét đọc MỘT lần mỗi yêu cầu."""
    c, kho = _kho_loc()
    dem: list = []
    goc = kho.luot_xong_moi_nhat
    kho.luot_xong_moi_nhat = lambda: dem.append(1) or goc()
    kho.bai.append(_bai(datetime.datetime(2026, 6, 1, 9, 0, tzinfo=VN), khoa="tiktok:cu2",
                        followers=3_000_000))
    kho.bl.append(_bl("tiktok:cu2", "e", datetime.datetime(2026, 10, 15, 9, 0, tzinfo=VN)))
    ql = "/api/binh-luan?du_an=hapas&anh_huong=mega"
    assert c.get(ql + Q_LOC).json()["tong"] == 1
    assert kho.goi_bai_khoa == [("tiktok:cu",)] and kho.goi_bai_khoa_chu == [False]
    assert len(dem) == 1
    # Khoảng khác, cùng mốc: chỉ đọc bài gốc MỚI thiếu (cu đã nhớ).
    assert c.get(ql + "&tu=2026-10-08&den=2026-10-15").json()["tong"] == 2
    assert kho.goi_bai_khoa == [("tiktok:cu",), ("tiktok:cu2",)]
    # Lượt quét mới: bài gốc đọc lại theo mốc MỚI, không dùng bản của mốc cũ.
    kho.luot_moi_nhat = {"id": 9, "du_an": "hapas", "ket_thuc": "x"}
    c.get(ql + Q_LOC)
    assert kho.goi_bai_khoa[-1] == ("tiktok:cu",)
    # Lọc chữ: bài gốc đọc KÈM nội dung — "d" khớp nhờ chữ của bài cũ.
    assert c.get("/api/binh-luan?du_an=hapas&q=túi xách" + Q_LOC).json()["tong"] == 4
    assert kho.goi_bai_khoa_chu[-1] is True
    dem.clear()
    c.get("/api/chi-so?du_an=hapas&anh_huong=mega" + Q_LOC)
    c.get("/api/bai?du_an=hapas" + Q_LOC)
    assert len(dem) == 2


def test_api_khoa_nguon_dai_va_tim_trong_ngan_tu_khoa():
    c, kho = _kho_loc()
    link = "https://x.vn/" + "a" * 487                       # kho cắt link 500 ký tự
    kho.bai.append(_bai(datetime.datetime(2026, 10, 11, 9, 0, tzinfo=VN), khoa="web:1",
                        nguon_id=None, nguon_loai=None, tac_gia="", tai_khoan="", link=link))
    kho.bl.append(dict(_bl("tiktok:1", "f", datetime.datetime(2026, 10, 11, 9, 0, tzinfo=VN)),
                       noi_dung="Ship lâu quá, mk xin link mua"))
    k = "link:" + link                                        # 505 ký tự: vẫn lọc được
    qb = "/api/bai?du_an=hapas" + Q_LOC + "&"
    assert c.get(qb + urlencode({"ct_nguon": k})).json()["tong"] == 1
    assert c.get(qb + urlencode({"nguon": k})).json()["tong"] == 1
    assert c.get(qb + urlencode({"ct_nguon": "x" * 521})).status_code == 400
    # Ngăn "Từ khoá" (q_bl): trả đúng bình luận chứa từ, có đủ chữ.
    d = c.get("/api/binh-luan?du_an=hapas" + Q_LOC + "&q_bl=mk xin&loai_bl=hop_le").json()
    assert [x["ma"] for x in d["binh_luan"]] == ["f"]
    assert "mk xin" in d["binh_luan"][0]["noi_dung"]


def test_trang_chi_so_co_thanh_loc_chung():
    _, c, _ = tao()
    dang_nhap(c, XEM)

    def cau_hinh(t):
        m = re.search(r'<script type="application/json" id="cau-hinh-chi-so">(.*?)</script>', t,
                      re.DOTALL)
        return json.loads(m.group(1))
    t = c.get("/").text
    for ma in ("bo-loc", "loc-nhanh", "loc-form", "loc-du-an", "loc-tu", "loc-den", "loc-ky",
               "loc-pham-vi", "loc-q", "loc-truong", "loc-dang", "loc-tom", "loc-mo-tam",
               "loc-tam", "loc-tam-xem", "khoi-nha-ngoai", "nha-ngoai", "chua-tron"):
        assert f'id="{ma}"' in t, ma
    assert 'class="the-khoi cs-bo-loc"' in t and 'name="nen_tang"' not in t   # select cũ đã bỏ
    cfg = cau_hinh(t)
    assert cfg["bo_loc"]["pham_vi"] == "tat_ca" and cfg["mac_dinh"]["den"] == cfg["den"]
    assert [p["ten"] for p in cfg["nhanh"]][:2] == ["Kênh nhà", "Listening bên ngoài"]
    assert {"Khách hỏi mua", "Cảnh báo khủng hoảng", "Tiêu cực cần xử lý",
            "KOL/KOC nói về thương hiệu"} <= {p["ten"] for p in cfg["nhanh"]}
    assert set(cfg["nhan"]["pham_vi"]) == {"tat_ca", "kenh_nha", "ben_ngoai"}
    # Link chia sẻ: trang mở đúng bộ lọc trong URL; link cũ một giá trị vẫn đọc được.
    cfg = cau_hinh(c.get("/?pham_vi=kenh_nha&nen_tang=tiktok,facebook&sac_thai=tieu_cuc"
                         "&q=túi").text)
    assert cfg["bo_loc"]["pham_vi"] == "kenh_nha" and cfg["bo_loc"]["q"] == "túi"
    assert cfg["bo_loc"]["nen_tang"] == ["facebook", "tiktok"]
    assert cfg["bo_loc"]["sac_thai"] == ["tieu_cuc"]
    assert cau_hinh(c.get("/?nen_tang=facebook&loai=kol").text)["bo_loc"]["loai"] == ["kol"]
    r = c.get("/?pham_vi=xau")
    assert r.status_code == 200 and "Đã bỏ bộ lọc" in r.text
    assert cau_hinh(r.text)["bo_loc"]["pham_vi"] == "tat_ca"
    js = (A.THU_MUC / "static" / "chi_so.js").read_text(encoding="utf-8")
    for can in ("history.pushState", "popstate", "AbortController", "ct_sac_thai", "sac_thai_bl",
                "showModal",
                '"replaceState" : "pushState"',          # gõ ô tìm liên tiếp: sửa mục lịch sử
                'setAttribute("inert"',                  # lượt lỗi: khối số cũ không bấm được
                "so_sanh_lech"):                         # lọc tương tác: không so kỳ trước
        assert can in js, can

