"""Kênh đăng của quảng cáo (22/10/2026, chủ dự án chốt): chốt chỉ đọc mới của TikTok (identity_get,
tool_execute CHỈ dạng ad_get cố định) và Meta (nút <id> chỉ fields=name|username, quyền
pages_read_engagement), đồng bộ kênh trong lượt hằng ngày (giả), khối "Theo kênh đăng" của trang
Quảng cáo, schema + BigQuery.

Không mạng: dùng lại máy chủ giả TikTok / Meta và kho giả của test_tiktok_ads /
test_meta_ads_dashboard,
thêm phần kênh đăng (đo thật 22/10/2026: ad_get trả identity_id cho 100/100 ad chi nhiều nhất của
MATEMADE MKT; identity_get một lượt trả đủ, page_info toàn 0)."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from test_dashboard_app import QL, dang_nhap
from test_meta_ads_dashboard import NUOC_HOA, TOKEN, GiaMeta, _gom_tk, _mdv
from test_tiktok_ads import MM_MKT, GiaKhoQC, GiaTikTok, _dv, _ket_noi_san, _tao_app

from dashboard import dong_bo_bq as DBQ
from dashboard import kenh_dang as KD
from dashboard import kho_qc as KQ
from dashboard import meta_ads as MA
from dashboard import quang_cao as QC
from dashboard import tiktok_ads as TA
from dashboard.kho import LoiKho

GOC = Path(__file__).resolve().parents[1]
ADV = "7449642852218470416"
F = list(TA.TRUONG_AD_GET)


def _dung(**p):
    a = {"tool_name": "ad_get", "params": {"advertiser_id": ADV, "fields": list(F),
                                           "filtering": {"ad_ids": ["1872761370049714"]},
                                           "page_size": 1000}}
    a["params"].update(p)
    return a


# ───────────────────────────── chốt TikTok ─────────────────────────────
def test_tool_execute_dung_dang_ad_get_di_qua():
    TA.kiem_cong_cu("tool_execute", _dung())
    TA.kiem_cong_cu("tool_execute", _dung(page=2, page_size=1))
    TA.kiem_cong_cu("tool_execute", _dung(filtering={"ad_ids": [str(10 ** 15 + i)
                                                                for i in range(100)]}))
    TA.kiem_cong_cu("identity_get", {"advertiser_id": ADV, "page_size": 100})
    TA.kiem_cong_cu("identity_get", {"advertiser_id": ADV, "page_size": 100, "page": 3})


def _bien(cach):
    a = _dung()
    cach(a)
    return a


SAI = [
    {"tool_name": "split_test_end_get", "params": _dung()["params"]},
    {"tool_name": "ad_update", "params": _dung()["params"]},
    {"tool_name": "ad_status_update", "params": _dung()["params"]},
    {"tool_name": "report_integrated_get", "params": _dung()["params"]},
    {"tool_name": "AD_GET", "params": _dung()["params"]},
    {"tool_name": "ad_get"},
    {"params": _dung()["params"]},
    {**_dung(), "khac": 1},
    _bien(lambda a: a["params"].update(operation_status="DISABLE")),
    _bien(lambda a: a["params"].update(fields=F + ["ad_name"])),
    _bien(lambda a: a["params"].update(fields=F[:-1])),
    _bien(lambda a: a["params"].update(fields=list(reversed(F)))),
    _bien(lambda a: a["params"].update(fields=",".join(F))),
    _bien(lambda a: a["params"].pop("fields")),
    _bien(lambda a: a["params"].pop("filtering")),
    _bien(lambda a: a["params"].pop("page_size")),
    _bien(lambda a: a["params"].update(filtering={"ad_ids": ["1"], "campaign_ids": ["2"]})),
    _bien(lambda a: a["params"].update(filtering={"campaign_ids": ["2"]})),
    _bien(lambda a: a["params"].update(filtering={"ad_ids": []})),
    _bien(lambda a: a["params"].update(filtering={"ad_ids": [str(i) for i in range(101)]})),
    _bien(lambda a: a["params"].update(filtering={"ad_ids": ["12a"]})),
    _bien(lambda a: a["params"].update(filtering={"ad_ids": [123]})),
    _bien(lambda a: a["params"].update(filtering={"ad_ids": "123"})),
    _bien(lambda a: a["params"].update(page_size=0)),
    _bien(lambda a: a["params"].update(page_size=1001)),
    _bien(lambda a: a["params"].update(page_size=True)),
    _bien(lambda a: a["params"].update(page_size="1000")),
    _bien(lambda a: a["params"].update(page=0)),
    _bien(lambda a: a["params"].update(advertiser_id=int(ADV))),
    _bien(lambda a: a["params"].update(advertiser_id="act_1")),
    "ad_get",
    None,
]


@pytest.mark.parametrize("args", SAI)
def test_tool_execute_moi_dang_khac_bi_chan_truoc_khi_gui(args):
    tt = GiaTikTok()
    mcp = TA.Mcp(tt.access, TA.Http(transport=tt.transport(), ngu=lambda s: None))
    with pytest.raises(TA.LoiChan):
        mcp.goi("tool_execute", args)
    assert tt.goi == []                       # không một byte nào tới TikTok


@pytest.mark.parametrize("args", [
    {"advertiser_id": ADV, "page_size": 100, "identity_type": "BC_AUTH_TT"},
    {"advertiser_id": ADV, "filtering": {"keyword": "x"}},
    {"advertiser_id": ADV, "page_size": 101},
    {"advertiser_id": int(ADV)},
    {"page_size": 100},
    {"tool_name": "report_integrated_get", "params": {}},
    None,
])
def test_identity_get_tham_so_la_bi_chan(args):
    tt = GiaTikTok()
    mcp = TA.Mcp(tt.access, TA.Http(transport=tt.transport(), ngu=lambda s: None))
    with pytest.raises(TA.LoiChan):
        mcp.goi("identity_get", args)
    assert tt.goi == []


# ───────────────────────────── kho giả có kênh ─────────────────────────────
class GiaKhoKenh(GiaKhoQC):
    """`GiaKhoQC` + bảng qc_ad_kenh / qc_kenh (cùng nghĩa SQL của kho_qc)."""

    def __init__(self, *a, hong=False, **kw):
        super().__init__(*a, **kw)
        self.ad_kenh: dict[tuple[str, str], dict] = {}
        self.kenh: dict[tuple[str, str], dict] = {}
        self.hong = hong

    def _kiem(self):
        if self.hong:
            raise LoiKho("relation qc_ad_kenh does not exist")

    def ad_chua_kenh(self, adv, n):
        self._kiem()
        tong: dict[str, float] = {}
        for r in self.bang["qc_ad_ngay"].values():
            if r["advertiser_id"] == adv and re.fullmatch(r"[0-9]{1,30}", r["ad_id"]):
                k = self.ad_kenh.get((adv, r["ad_id"]))
                if k and k.get("kenh_id"):
                    continue
                if k and (self.bay - k["cap_nhat_luc"]).days < KQ.HOI_LAI_KHONG_THAY_NGAY:
                    continue
                tong[r["ad_id"]] = tong.get(r["ad_id"], 0) + float(r.get("chi") or 0)
        return sorted(tong, key=lambda x: (-tong[x], x))[:n]

    def ghi_ad_kenh(self, rows):
        self._kiem()
        for r in rows:
            self.ad_kenh[(r["advertiser_id"], r["ad_id"])] = {**r, "cap_nhat_luc": self.bay}
        return len(rows)

    def kenh_chua_ten(self, nen, adv):
        self._kiem()
        ra = set()
        for r in self.ad_kenh.values():
            if r["advertiser_id"] != adv or r["nen_tang"] != nen:
                continue
            for kid, loai in ((r.get("kenh_id"), r.get("loai")),
                              (r.get("kenh_phu_id"), "instagram")):
                c = self.kenh.get((nen, kid))
                cu = c and (self.bay - c["cap_nhat_luc"]).days >= KQ.HOI_LAI_TEN_NGAY[nen]
                if kid and (c is None or (not c.get("ten") and not c.get("username") and cu)):
                    ra.add((kid, loai))
        return [{"kenh_id": k, "loai": lo} for k, lo in sorted(ra)]

    def ghi_kenh(self, rows):
        self._kiem()
        for r in rows:
            cu = self.kenh.get((r["nen_tang"], r["kenh_id"])) or {}
            self.kenh[(r["nen_tang"], r["kenh_id"])] = {
                **r, **{k: r.get(k) or cu.get(k) for k in ("loai", "ten", "username")},
                "cap_nhat_luc": self.bay}
        return len(rows)

    def qc_kenh_dang(self, ids, tu, den, *, sap="chi", n=20):
        self._kiem()
        theo_ad: dict[tuple, dict] = {}
        for r in self.bang["qc_ad_ngay"].values():
            if r["advertiser_id"] in ids and tu <= r["ngay"] <= den:
                k = (r["advertiser_id"], r["ad_id"])
                theo_ad.setdefault(k, []).append(r)
        nhom, biet, chua = {}, [], []
        for k, rs in theo_ad.items():
            a = self._cong(rs)
            kk = self.ad_kenh.get(k)
            if kk and kk.get("kenh_id"):
                biet.append(a)
                g = nhom.setdefault((kk["nen_tang"], kk["kenh_id"]), {
                    "nen_tang": kk["nen_tang"], "kenh_id": kk["kenh_id"], "loai": kk["loai"],
                    "kenh_phu_id": kk.get("kenh_phu_id"), "tk_ids": set(), "so_ad": 0, "_r": []})
                g["tk_ids"].add(k[0])
                g["so_ad"] += 1
                g["_r"].append(a)
            else:
                chua.append(a)
        rows = []
        for (nen, kid), g in nhom.items():
            c = self.kenh.get((nen, kid)) or {}
            p = self.kenh.get((nen, g["kenh_phu_id"])) or {}
            rows.append({**{x: v for x, v in g.items() if x != "_r"}, **self._cong(g["_r"]),
                         "tk_ids": sorted(g["tk_ids"]), "ten": c.get("ten"),
                         "username": c.get("username"), "phu_username": p.get("username")})
        rows.sort(key=lambda r: (-(r.get(sap) or 0), r["kenh_id"]))
        return {"rows": rows[:n], "tong": len(rows),
                "biet": {**self._cong(biet), "so_ad": len(biet)} if biet else {},
                "chua_ro": {**self._cong(chua), "so_ad": len(chua)} if chua else {}}


# ───────────────────────── máy chủ TikTok giả có ad_get / identity_get ─────────────────────────
class GiaTikTokKenh(GiaTikTok):
    """ad_id giả dạng số (như thật). Ad cuối cùng của mỗi lượt ad_get "không thấy" (đã xoá)."""

    def __init__(self, *a, loi_identity=False, loi_adv=(), bo_identity=(), ma_loi=50000, **kw):
        super().__init__(*a, **kw)
        self.loi_identity = loi_identity
        self.loi_adv = set(loi_adv)            # tài khoản ad_get lỗi
        self.bo_identity = set(bo_identity)    # danh tính identity_get không trả
        self.ma_loi = ma_loi

    @staticmethod
    def _so(x: str) -> str:
        return "9" + x[2:] if x.startswith("ad") else x

    @staticmethod
    def _chu(x: str) -> str:
        return "ad" + x[1:] if x.startswith("9") else x

    def _bao_cao(self, a):
        if a.get("filtering") and a["filtering"][0]["field_name"] == "ad_ids":
            a = {**a, "filtering": [{**a["filtering"][0], "filter_value": json.dumps(
                [self._chu(x) for x in json.loads(a["filtering"][0]["filter_value"])])}]}
        d = super()._bao_cao(a)
        for r in (d.get("data") or {}).get("list") or []:
            dims = r.get("dimensions") or {}
            if "ad_id" in dims:
                dims["ad_id"] = self._so(dims["ad_id"])
        return d

    def _cong_cu(self, ten, a):
        if ten == "tool_execute":
            self.cong_cu.append((ten, a))
            p = a["params"]
            ids = p["filtering"]["ad_ids"]
            if p["advertiser_id"] in self.loi_adv:
                return {"code": self.ma_loi, "message": "lỗi"}
            ds = [{"ad_id": x, "identity_id": f"id-{int(x) % 3}",
                   "identity_type": "AUTH_CODE" if int(x) % 3 else "BC_AUTH_TT",
                   "tiktok_item_id": "76" + x[-6:], "campaign_id": "1"} for x in ids[:-1]]
            return {"code": 0, "message": "OK", "data": {"list": ds, "page_info": {
                "page": 1, "page_size": p["page_size"], "total_page": 5,
                "total_number": len(ds)}}}
        if ten == "identity_get":
            self.cong_cu.append((ten, a))
            if self.loi_identity:
                return {"code": 50000, "message": "lỗi hệ thống"}
            return {"code": 0, "data": {"identity_list": [x for x in [
                {"identity_id": "id-0", "identity_type": "BC_AUTH_TT", "display_name": "MATE MADE",
                 "username": "matemade.official"},
                {"identity_id": "id-1", "identity_type": "AUTH_CODE", "display_name": "Bé Duy",
                 "username": None},
                {"identity_id": "id-1", "identity_type": "AUTH_CODE", "display_name": "Bé Duy",
                 "username": None},
                {"identity_id": "id-2", "identity_type": "AUTH_CODE",
                 "display_name": "<b>Nhật Hạ</b>", "username": None}]
                if x["identity_id"] not in self.bo_identity],
                "page_info": {"page": 0, "page_size": 0, "total_number": 0, "total_page": 0}}}
        return super()._cong_cu(ten, a)


def _tiktok(**kw):
    kho = GiaKhoKenh(hong=kw.pop("hong", False))
    tt = GiaTikTokKenh(**kw)
    dv, kho, tt = _dv(kho, tt)
    _ket_noi_san(dv, tt)
    return dv, kho, tt


def test_dong_bo_tiktok_doc_kenh_mot_lan_lo_100_identity_mot_luot():
    dv, kho, tt = _tiktok(so_ad=150, so_khong_chay=0)
    kq = dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert kq.get("loi") is None and kho.kn["trang_thai"] == "hoat_dong"
    ad_get = [a for t, a in tt.cong_cu if t == "tool_execute"]
    so_ad = {r["ad_id"] for r in kho.bang["qc_ad_ngay"].values()}
    assert ad_get and all(len(a["params"]["filtering"]["ad_ids"]) <= 100 for a in ad_get)
    assert all(a["tool_name"] == "ad_get" and a["params"]["fields"] == F for a in ad_get)
    assert {k[1] for k in kho.ad_kenh} == so_ad
    khong = [r for r in kho.ad_kenh.values() if r["kenh_id"] is None]
    assert khong and all(r["loai"] == TA.KHONG_THAY for r in khong)
    co = [r for r in kho.ad_kenh.values() if r["kenh_id"]]
    assert {r["loai"] for r in co} == {"AUTH_CODE", "BC_AUTH_TT"} and co[0]["bai_id"]
    # identity_get một lượt mỗi tài khoản có kênh chưa tên; bỏ trùng.
    n_id = len([t for t, _ in tt.cong_cu if t == "identity_get"])
    assert 1 <= n_id <= len({r["advertiser_id"] for r in co})
    assert kho.kenh[("tiktok", "id-0")]["ten"] == "MATE MADE"
    # Lượt sau: kênh không đổi → không ad_get, không identity_get.
    tt.cong_cu.clear()
    dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert not [t for t, _ in tt.cong_cu if t in ("tool_execute", "identity_get")]


def test_dong_bo_tiktok_nhanh_khong_doc_kenh_va_tran_luot(monkeypatch):
    dv, kho, tt = _tiktok(so_ad=30, so_khong_chay=0)
    monkeypatch.setattr(TA, "TRAN_KENH_LUOT", 1)
    dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert len([t for t, _ in tt.cong_cu if t == "tool_execute"]) == 1      # trần mỗi lượt
    tt.cong_cu.clear()
    n = len(kho.ad_kenh)
    dv.kho._kn()["yeu_cau_dong_bo_luc"] = BAY_NHANH
    dv.kho._kn()["yeu_cau_kieu"] = "nhanh"
    dv.dong_bo(theo_yeu_cau=True)
    assert not [t for t, _ in tt.cong_cu if t == "tool_execute"] and len(kho.ad_kenh) == n


BAY_NHANH = datetime.datetime(2026, 10, 19, 0, 0, tzinfo=datetime.timezone.utc)


@pytest.mark.parametrize("cach", ["identity_loi", "kho_chua_bang"])
def test_kenh_hong_khong_lam_hong_luot_dong_bo(cach):
    dv, kho, tt = _tiktok(so_ad=5, so_khong_chay=0, loi_identity=cach == "identity_loi",
                          hong=cach == "kho_chua_bang")
    nhat_ky = []
    dv.log = nhat_ky.append
    kq = dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert kq.get("loi") is None and kq["so_dong"] > 0
    assert kho.kn["trang_thai"] == "hoat_dong" and not kho.kn.get("dong_bo_loi")
    assert any(re.search(r"kênh đăng \d+ lỗi", x) for x in nhat_ky)
    assert not any(tt.access in x for x in nhat_ky)


# ───────────────────────────── chốt Meta ─────────────────────────────
def test_meta_nut_ten_chi_fields_name_hoac_username():
    for f in ("name", "username"):
        sach, duong = MA.kiem_url("GET", f"https://graph.facebook.com/v26.0/2241020449312154"
                                         f"?fields={f}&access_token={TOKEN}")
        assert duong == "2241020449312154" and TOKEN not in sach and sach.endswith(f"fields={f}")
    for q in ("", "?fields=name,id", "?fields=access_token", "?fields=name&limit=1",
              "?fields=name&fields=username", "?method=delete&fields=name", "?fields=accounts"):
        with pytest.raises(MA.LoiChan):
            MA.kiem_url("GET", f"https://graph.facebook.com/v26.0/2241020449312154{q}")
    for u in ("https://graph.facebook.com/v26.0/2241020449312154/feed?fields=name",
              "https://graph.facebook.com/v26.0/0123?fields=name"):
        with pytest.raises(MA.LoiChan):
            MA.kiem_url("GET", u)
    with pytest.raises(MA.LoiChan):
        MA.kiem_url("POST", "https://graph.facebook.com/v26.0/2241020449312154?fields=name")
    with pytest.raises(MA.LoiChan):                     # trang sau không bao giờ là nút trần
        MA.kiem_url("GET", "https://graph.facebook.com/v26.0/22410?fields=name",
                    tiep="act_1/ads")


def test_meta_quyen_pages_read_engagement_duoc_phep_quyen_ghi_van_chan():
    q = lambda *ds: [{"permission": p, "status": "granted"} for p in ds]  # noqa: E731
    assert "pages_read_engagement" in MA.kiem_quyen(q("ads_read", "read_insights",
                                                      "pages_read_engagement"))
    assert MA.kiem_quyen(q("ads_read", "read_insights")) == ["ads_read", "read_insights"]
    for x in ("ads_management", "business_management", "pages_manage_posts",
              "pages_manage_ads", "instagram_content_publish"):
        with pytest.raises(MA.LoiTokenKhongChiDoc):
            MA.kiem_quyen(q("ads_read", "read_insights", "pages_read_engagement", x))
    html = (GOC / "dashboard" / "templates" / "nguoi_xem.html").read_text(encoding="utf-8")
    assert "pages_read_engagement" in html


def test_meta_dong_kenh_trang_truoc_ig_phu():
    x = {"id": "5255", "creative": {"actor_id": "2241", "instagram_user_id": "1784",
                                    "object_story_spec": {"page_id": "2241",
                                                          "instagram_user_id": "1784"},
                                    "effective_instagram_media_id": "1811"}}
    assert MA.dong_kenh(x, "act_1") == {"advertiser_id": "act_1", "ad_id": "5255",
                                        "nen_tang": "meta", "kenh_id": "2241", "loai": "page",
                                        "kenh_phu_id": "1784", "bai_id": "1811"}
    r = MA.dong_kenh({"id": "1", "creative": {"object_story_spec": {"page_id": "77"}}}, "act_1")
    assert (r["kenh_id"], r["loai"], r["kenh_phu_id"]) == ("77", "page", None)
    r = MA.dong_kenh({"id": "1", "creative": {"instagram_user_id": "88"}}, "act_1")
    assert (r["kenh_id"], r["loai"]) == ("88", "instagram")
    r = MA.dong_kenh({"id": "1"}, "act_1")
    assert (r["kenh_id"], r["loai"]) == (None, "khong_thay")


class GiaMetaKenh(GiaMeta):
    def __init__(self, *a, ten_loi=False, **kw):
        super().__init__(*a, **kw)
        self.ten_loi = ten_loi

    def xu_ly(self, req):
        duong = req.url.path.split("/", 2)[2]
        q = {k: v[0] for k, v in parse_qs(urlsplit(str(req.url)).query).items()}
        m = re.fullmatch(r"(act_[0-9]+)/ads", duong)
        if m:
            self.goi.append(req)
            loc = json.loads(q["filtering"])
            assert loc[0]["field"] == "ad.id" and len(loc[0]["value"]) <= MA.LO_KENH
            assert loc[1]["field"] == "ad.effective_status" and "ARCHIVED" in loc[1]["value"]
            ds = [{"id": x, "creative": {"actor_id": "2241", "instagram_user_id": "1784"}}
                  for x in loc[0]["value"]]
            return httpx.Response(200, json={"data": ds})
        if re.fullmatch(r"[0-9]+", duong):
            self.goi.append(req)
            if self.ten_loi:
                return httpx.Response(400, json={"error": {"code": 100, "error_subcode": 33}})
            return httpx.Response(200, json={"id": duong, **({"name": "MATE MADE"} if
                                  q["fields"] == "name" else {"username": "matemade.vn"})})
        return super().xu_ly(req)


@pytest.mark.parametrize("co_quyen,ten_loi", [(True, False), (True, True), (False, False)])
def test_dong_bo_meta_doc_kenh_va_ten_khi_co_quyen(co_quyen, ten_loi):
    quyen = ("ads_read", "read_insights", "public_profile") + (
        ("pages_read_engagement",) if co_quyen else ())
    gm = GiaMetaKenh(quyen=quyen, ten_loi=ten_loi)
    dv, kho, gm = _mdv(GiaKhoKenh(), gm)
    _gom_tk(dv)
    kq = dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert kq.get("loi") is None
    ads = {(r["advertiser_id"], r["ad_id"]) for r in kho.bang["qc_ad_ngay"].values()}
    assert set(kho.ad_kenh) == ads and ads
    assert all(r["kenh_id"] == "2241" and r["kenh_phu_id"] == "1784"
               for r in kho.ad_kenh.values())
    ten = [r for r in gm.goi if re.fullmatch(r"/v[0-9.]+/[0-9]+", r.url.path)]
    if not co_quyen:
        assert ten == [] and kho.kenh == {}
    else:
        assert len(ten) == 2                          # Trang + IG, một lần mỗi kênh
        tr, ig = kho.kenh[("meta", "2241")], kho.kenh[("meta", "1784")]
        if ten_loi:
            assert tr["ten"] is None and ig["username"] is None
        else:
            assert tr["ten"] == "MATE MADE" and ig["username"] == "matemade.vn"
    # Lượt sau: không đọc lại kênh; tên lỗi chỉ hỏi lại sau 1 ngày.
    gm.goi.clear()
    dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert not [r for r in gm.goi if r.url.path.endswith("/ads")
                or re.fullmatch(r"/v[0-9.]+/[0-9]+", r.url.path)]
    assert NUOC_HOA in {a for a, _ in kho.ad_kenh}


# ───────────────────────────── khối trang ─────────────────────────────
def test_nhan_kenh_tiktok_va_meta():
    assert KD.loai_kenh("tiktok", "AUTH_CODE", "MATE MADE", None, ["MATEMADE MKT"]) == "spark"
    assert KD.loai_kenh("tiktok", "BC_AUTH_TT", "MATE MADE", "matemade.official",
                        ["MATEMADE MKT"]) == "chinh_chu"
    assert KD.loai_kenh("tiktok", "BC_AUTH_TT", "Bé Duy", "beduyzuize",
                        ["MATEMADE MKT"]) == "spark"
    assert KD.loai_kenh("tiktok", "BC_AUTH_TT", "Ha", "ha", ["HAPAS - KOC"]) == "spark"
    assert KD.loai_kenh("tiktok", "TT_USER", "HAPAS", "hapas.official", []) == "chinh_chu"
    assert KD.loai_kenh("meta", "page", None, None, []) == "page"
    assert KD.loai_kenh("meta", "instagram", None, None, []) == "instagram"
    assert KD.chu_gon("Đồng HỒ ☘️ x") == "donghox"


def _kho_so():
    kho = GiaKhoKenh()
    d = datetime.date(2026, 10, 18)
    for i, (adv, chi, hien) in enumerate(((MM_MKT, 900, 9000), (MM_MKT, 500, 5000),
                                          (MM_MKT, 100, 3000), ("act_1", 300, 4000))):
        kho.bang["qc_ad_ngay"][(str(i), d)] = {"advertiser_id": adv, "ad_id": str(i), "ngay": d,
                                               **{c: None for c in QC.TEN_COT_SO},
                                               "chi": chi, "hien_thi": hien, "click": 10,
                                               "view_video": 7, "thich": 1, "binh_luan": 2,
                                               "chia_se": 3, "follow": 4,
                                               "gia_tri_mua_shop": 50}
    kho.ghi_ad_kenh([{"advertiser_id": MM_MKT, "ad_id": "0", "nen_tang": "tiktok",
                      "kenh_id": "id-1", "loai": "AUTH_CODE"},
                     {"advertiser_id": MM_MKT, "ad_id": "1", "nen_tang": "tiktok",
                      "kenh_id": "id-0", "loai": "BC_AUTH_TT"},
                     {"advertiser_id": "act_1", "ad_id": "3", "nen_tang": "meta",
                      "kenh_id": "2241", "loai": "page", "kenh_phu_id": "1784"}])
    kho.ghi_kenh([{"nen_tang": "tiktok", "kenh_id": "id-1", "loai": "AUTH_CODE",
                   "ten": "<script>x</script>"},
                  {"nen_tang": "tiktok", "kenh_id": "id-0", "loai": "BC_AUTH_TT",
                   "ten": "MATE MADE", "username": "matemade.official"}])
    return kho


TEN_TK = {MM_MKT: "MATEMADE MKT", "act_1": "MATEMADE-6"}
D1, D2 = datetime.date(2026, 10, 12), datetime.date(2026, 10, 18)


def test_khoi_kenh_xep_chi_do_phu_chua_xac_dinh():
    kd = KD.du_lieu(_kho_so(), [MM_MKT, "act_1"], D1, D2, {}, True, TEN_TK)
    assert [r["ten"] for r in kd["rows"]] == ["<script>x</script>", "MATE MADE", "Page 2241"]
    assert [r["nhan_loai"] for r in kd["rows"]] == ["Spark Ads", "Chính chủ", "Page"]
    assert kd["rows"][2]["phu"] == "IG 1784" and kd["rows"][1]["phu"] == "@matemade.official"
    assert kd["rows"][0]["tuong_tac"] == 6 and kd["rows"][0]["tai_khoan"] == ["MATEMADE MKT"]
    assert kd["do_phu"] == round(1700 / 1800 * 100, 1) and kd["do_phu_theo"] == "chi"
    assert kd["chua_ro"]["chi"] == 100 and kd["chua_ro"]["so_ad"] == 1
    assert kd["tong"] == 3 and kd["so"] == 100 and kd["so_tiep"] is None


def test_khoi_kenh_khong_xem_tien_khong_lo_chi():
    kd = QC.loc_tien(KD.du_lieu(_kho_so(), [MM_MKT, "act_1"], D1, D2, {}, False, TEN_TK), False)
    assert kd["do_phu_theo"] == "hien_thi"
    assert kd["do_phu"] == round(18000 / 21000 * 100, 1)
    khoa = json.dumps(kd)
    assert '"chi"' not in khoa and "gia_tri" not in khoa and "roas" not in khoa
    assert [r["ten"] for r in kd["rows"]][0] == "<script>x</script>"   # xếp theo hiển thị


def test_khoi_kenh_pham_vi_va_xem_them():
    kho = _kho_so()
    kd = KD.du_lieu(kho, ["act_1"], D1, D2, {}, True, TEN_TK)
    assert [r["ten"] for r in kd["rows"]] == ["Page 2241"] and kd["chua_ro"] is None
    assert KD.du_lieu(kho, [], D1, D2, {}, True, TEN_TK) is None
    kd = KD.du_lieu(kho, [MM_MKT, "act_1"], D1, D2, {"kenh_so": "1"}, True, TEN_TK)
    assert kd["so"] == 100                                # chỉ 100 / 500 (23/10/2026)
    for n in KD.SO_KENH:
        assert KD.so_kenh({"kenh_so": str(n)}) == n
    assert KD.so_kenh({"kenh_so": "x"}) == 100
    kho.qc_kenh_dang = lambda *a, **k: {"rows": [{"nen_tang": "tiktok", "kenh_id": "a"}] * 100,
                                        "tong": 450, "biet": {}, "chua_ro": {}}
    kd = KD.du_lieu(kho, [MM_MKT], D1, D2, {}, True, TEN_TK)
    assert kd["so_tiep"] == 500 and kd["do_phu"] is None


def test_khoi_kenh_kho_chua_bang_khong_sap():
    kd = KD.du_lieu(GiaKhoKenh(hong=True), [MM_MKT], D1, D2, {}, True, TEN_TK)
    assert kd["loi"] and kd["rows"] == []
    assert KD.du_lieu(object(), [MM_MKT], D1, D2, {}, True, TEN_TK) is None


def test_trang_quang_cao_co_khoi_theo_kenh_dang():
    app, c, _kho, kho_qc, tt, dv = _tao_app(kho_qc=GiaKhoKenh(), tt=GiaTikTokKenh(so_ad=25))
    _ket_noi_san(dv, tt)
    dv.dong_bo(tu=datetime.date(2026, 10, 12), den=datetime.date(2026, 10, 18))
    app.state.nho_ben_qc = (float("-inf"), set())
    assert kho_qc.ad_kenh and kho_qc.kenh
    kho_qc.ghi_kenh([{"nen_tang": "tiktok", "kenh_id": "id-2", "ten": "<b>Nhật Hạ</b>"}])
    dang_nhap(c, QL)
    q = "tu=2026-10-12&den=2026-10-18&ben=tat_ca"
    t = c.get(f"/quang-cao?{q}").text
    i = t.index('id="qc-kenh-tieu-de"')
    assert t.index('id="qc-xh-tieu-de"') < i < t.index('id="qc-top-tieu-de"')
    assert "Theo kênh đăng" in t and "Chính chủ" in t and "Spark Ads" in t
    assert "MATE MADE" in t and "&lt;b&gt;Nhật Hạ&lt;/b&gt;" in t and "<b>Nhật Hạ</b>" not in t
    assert "Chưa xác định" in t and "đã biết kênh" in t and "kenh.css" in t
    assert re.search(r'data-nhan="Chi"', t[i:])
    d = c.get(f"/api/qc?{q}").json()
    assert d["kenh"]["rows"] and d["kenh"]["do_phu_theo"] == "chi"


# ───────────────────────────── schema + BigQuery ─────────────────────────────
def test_schema_bang_kenh_quyen_va_mo_ta():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS qc_ad_kenh (" in sql
    assert "CREATE TABLE IF NOT EXISTS qc_kenh (" in sql
    assert "PRIMARY KEY (advertiser_id, ad_id)" in sql and "PRIMARY KEY (nen_tang, kenh_id)" in sql
    assert "GRANT INSERT, UPDATE ON qc_ad_kenh, qc_kenh TO lang_nghe_web;" in sql
    assert "GRANT SELECT ON qc_ad_kenh, qc_kenh TO mark;" in sql
    assert not re.search(r"GRANT[^;]*DELETE[^;]*qc_(ad_)?kenh", sql)
    i = sql.index("CREATE TABLE IF NOT EXISTS qc_ad_kenh")
    assert i < sql.index("GRANT SELECT ON ALL TABLES IN SCHEMA public TO lang_nghe_web")
    for b in ("qc_ad_kenh", "qc_kenh"):
        m = re.search(rf"COMMENT ON TABLE {b} IS \$\$(.*?)\$\$;", sql, re.DOTALL)
        nhan = re.findall(r"^\[([^\]]+)\]", m.group(1), re.MULTILINE)
        assert nhan == ["Lớp", "Mục đích", "Grain", "Khoá", "Nguồn", "Phạm vi", "Đã xử lý",
                        "Refresh", "Dùng khi", "Không dùng khi", "Lưu ý"], b
        khoi = re.search(rf"CREATE TABLE IF NOT EXISTS {b} \((.*?)\n\);", sql, re.DOTALL).group(1)
        for cot in re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE):
            assert f"COMMENT ON COLUMN {b}.{cot} IS" in sql, (b, cot)
    assert {"qc_ad_kenh", "qc_kenh"} <= set(DBQ.THU_TU)
    assert not any(c in QC.COT_TIEN for b in ("qc_ad_kenh", "qc_kenh")
                   for c, _ in DBQ.BANG[b]["cot"])


def test_tai_lieu_nhac_quyen_meta_va_cong_cu_tiktok():
    for p in ("dashboard/README.md", "deploy/lang-nghe/README.md"):
        s = (GOC / p).read_text(encoding="utf-8")
        assert "pages_read_engagement" in s and "qc_ad_kenh" in s, p
    src = (GOC / "dashboard" / "tiktok_ads.py").read_text(encoding="utf-8")
    assert set(re.findall(r'goi\("([a-z_]+)"', src)) == TA.CONG_CU_DOC


# ───────────────────────────── soát 22/10/2026 ─────────────────────────────
def test_tai_khoan_loi_khong_chan_tai_khoan_sau_va_mot_trang_mot_luot():
    """Lỗi kênh của MỘT tài khoản không chặn tài khoản sau; ad_get chỉ một lượt mỗi lô (page_info
    giả báo 5 trang vẫn không đọc trang 2)."""
    from test_tiktok_ads import HAPAS_KOC, MM_2
    dv, kho, tt = _tiktok(so_ad=5, so_khong_chay=0, loi_adv={HAPAS_KOC})
    nk = []
    dv.log = nk.append
    kq = dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert kq.get("loi") is None and kho.kn["trang_thai"] == "hoat_dong"
    da = {a for a, _ in kho.ad_kenh}
    assert HAPAS_KOC not in da and {MM_MKT, MM_2} <= da
    assert any(f"kênh đăng {HAPAS_KOC} lỗi" in x for x in nk)
    ad_get = [a for t, a in tt.cong_cu if t == "tool_execute"]
    assert all("page" not in a["params"] for a in ad_get)
    assert len(ad_get) == 3                     # 3 tài khoản có số × 1 lô, không trang 2


def test_token_bi_tu_choi_o_phan_kenh_van_nem_tiep():
    class McpTuChoi:
        def goi(self, ten, a):
            raise TA.LoiXacThuc("từ chối", 40105)
    kho = GiaKhoKenh()
    d = datetime.date(2026, 10, 18)
    kho.bang["qc_ad_ngay"][("1", d)] = {"advertiser_id": MM_MKT, "ad_id": "1", "ngay": d,
                                        "chi": 1, "hien_thi": 1}
    dv, _, _ = _dv(kho)
    with pytest.raises(TA.LoiXacThuc):
        dv.kenh_dang(McpTuChoi(), [MM_MKT])


def test_tran_tinh_ca_identity_get_va_nho_am_danh_tinh_khong_tra(monkeypatch):
    dv, kho, tt = _tiktok(so_ad=5, so_khong_chay=0, bo_identity={"id-2"})
    dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert kho.kenh[("tiktok", "id-2")]["ten"] is None            # nhớ âm
    assert kho.kenh[("tiktok", "id-0")]["ten"] == "MATE MADE"
    tt.cong_cu.clear()
    dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert not [t for t, _ in tt.cong_cu if t == "identity_get"]   # trong 7 ngày: không hỏi lại
    kho.bay += datetime.timedelta(days=KQ.HOI_LAI_TEN_NGAY["tiktok"])
    dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert [t for t, _ in tt.cong_cu if t == "identity_get"]
    # Trần đếm cả identity_get: trần 1 → một lượt ad_get, không identity_get.
    monkeypatch.setattr(TA, "TRAN_KENH_LUOT", 1)
    dv2, kho2, tt2 = _tiktok(so_ad=5, so_khong_chay=0)
    dv2.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    assert [t for t, _ in tt2.cong_cu if t in ("tool_execute", "identity_get")] == ["tool_execute"]


class GiaMetaIg(GiaMetaKenh):
    """Mỗi ad một Instagram riêng; username IG luôn bị từ chối (thiếu instagram_basic)."""

    def xu_ly(self, req):
        duong = req.url.path.split("/", 2)[2]
        q = {k: v[0] for k, v in parse_qs(urlsplit(str(req.url)).query).items()}
        m = re.fullmatch(r"(act_[0-9]+)/ads", duong)
        if m:
            self.goi.append(req)
            loc = json.loads(q["filtering"])
            ds = [{"id": x, "creative": {"actor_id": "2241", "instagram_user_id": "9" + x}}
                  for x in loc[0]["value"]]
            return httpx.Response(200, json={"data": ds})
        if re.fullmatch(r"[0-9]+", duong) and q.get("fields") == "username":
            self.goi.append(req)
            return httpx.Response(400, json={"error": {"code": 100, "error_subcode": 33}})
        return super().xu_ly(req)


def test_meta_ig_loi_dau_tien_thi_thoi_hoi_ig_ca_luot():
    gm = GiaMetaIg(quyen=("ads_read", "read_insights", "pages_read_engagement",
                          "pages_show_list"))
    dv, kho, gm = _mdv(GiaKhoKenh(), gm)
    _gom_tk(dv)
    dv.dong_bo(tu=datetime.date(2026, 10, 16), den=datetime.date(2026, 10, 18))
    so_ig = len({r["kenh_phu_id"] for r in kho.ad_kenh.values()})
    assert so_ig > 1
    ten = [r for r in gm.goi if re.fullmatch(r"/v[0-9.]+/[0-9]+", r.url.path)]
    ig = [r for r in ten if "fields=username" in str(r.url)]
    assert len(ig) == 1 and len(ten) == 2                 # 1 IG lỗi rồi thôi + 1 Trang
    assert kho.kenh[("meta", "2241")]["ten"] == "MATE MADE"


def test_meta_pages_show_list_duoc_phep():
    q = [{"permission": p, "status": "granted"} for p in
         ("ads_read", "read_insights", "pages_read_engagement", "pages_show_list")]
    assert "pages_show_list" in MA.kiem_quyen(q)
    with pytest.raises(MA.LoiTokenKhongChiDoc):
        MA.kiem_quyen(q + [{"permission": "instagram_basic", "status": "granted"}])
    for p in ("deploy/lang-nghe/README.md", "dashboard/templates/nguoi_xem.html"):
        assert "pages_show_list" in (GOC / p).read_text(encoding="utf-8"), p
