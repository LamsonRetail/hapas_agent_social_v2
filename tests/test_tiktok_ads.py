"""TikTok Ads (19/10/2026, chủ dự án chốt): kết nối TikTok for Business MCP, đồng bộ số quảng cáo,
trang "Quảng cáo TikTok" + /api/qc, thẻ kết nối trên trang Quản trị, Mark (hỏi đáp + nhắc gia hạn),
BigQuery.

Không mạng: máy chủ TikTok GIẢ bằng httpx.MockTransport (OAuth DCR/token/revoke + MCP JSON-RPC, có
SSE + Mcp-Session-Id), kho quảng cáo GIẢ trong bộ nhớ (cùng tên hàm với `dashboard/kho_qc.py`, cùng
nghĩa khoá chính). Số mẫu lấy dạng từ CSV kéo thật ngày 19/10/2026 (chuỗi số, "-", "0.00")."""
from __future__ import annotations

import base64
import contextlib
import datetime
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from test_dashboard_app import (
    CFG,
    HP_QL,
    KHOA,
    MM_QL,
    MM_XEM,
    QL,
    XEM,
    GiaDongBo,
    GiaKho,
    dang_nhap,
    danh_ba_gia,
    lark_gia,
)

from dashboard import app as A
from dashboard import dang_nhap as DN
from dashboard import dong_bo_bq as DBQ
from dashboard import kho_qc as KQ
from dashboard import quang_cao as QC
from dashboard import tiktok_ads as TA
from dashboard.kho import LoiDuLieu

GOC = Path(__file__).resolve().parents[1]
UTC = datetime.timezone.utc
VN = datetime.timezone(datetime.timedelta(hours=7))
KHOA_TT = bytes(range(32))
BAY = datetime.datetime(2026, 10, 19, 1, 0, tzinfo=UTC)          # 08:00 giờ VN
HAPAS_KOC, MM_MKT, MM_2, LE = "7418067186868240401", "7487889878961635329", "7449642852218470416", \
    "7104175669654863874"
TK_MAU = {HAPAS_KOC: "HAPAS - KOC", MM_MKT: "MATEMADE MKT", MM_2: "mate made 2",
          LE: "CÔNG TY TNHH HTC VIỆT NAM0601"}


# ───────────────────────────── máy chủ TikTok giả ─────────────────────────────
class GiaTikTok:
    """OAuth + MCP giả. `chay[adv]` = số campaign/ad có hiển thị; sau đó là đối tượng 0 hiển thị
    (TikTok thật trả MỌI đối tượng chưa xoá)."""

    def __init__(self, *, so_campaign=3, so_ad=5, so_khong_chay=4, tk=None):
        self.goi: list[httpx.Request] = []
        self.cong_cu: list[tuple[str, dict]] = []
        self.tk = dict(TK_MAU if tk is None else tk)
        self.so_campaign, self.so_ad, self.so_khong_chay = so_campaign, so_ad, so_khong_chay
        self.access = "act.ACCESSgia0123456789abcdefXYZ"
        self.refresh = "rft.REFRESHgia0123456789abcdefXYZ"
        self.refresh_moi = None             # đặt chuỗi khác để giả TikTok đổi refresh token
        self.lam_moi_loi = False
        self.rt_con_giay = 2591999
        self.token_hop_le = {self.access}
        self.thu_hoi: list[str] = []
        self.dang_ky: list[dict] = []
        self.doi_ma: list[dict] = []

    def transport(self):
        return httpx.MockTransport(self.xu_ly)

    # ── số mẫu ──
    @staticmethod
    def _ngay(a, b):
        d = datetime.date.fromisoformat(a)
        while d <= datetime.date.fromisoformat(b):
            yield d
            d += datetime.timedelta(days=1)

    def _chi_so(self, metrics, seed: int, hien: int):
        ra = {}
        for m in metrics:
            if m == "impressions":
                ra[m] = str(hien)
            elif m == "spend":
                ra[m] = str(hien * 3)
            elif m in ("cost_per_secondary_goal_result", "secondary_goal_result"):
                ra[m] = "-"                                   # như CSV thật
            elif m == "ctr":
                ra[m] = "0.85"
            elif m == "total_onsite_shopping_value":
                ra[m] = str(hien * 5)
            elif m == "campaign_name":
                ra[m] = f"Chiến dịch {seed}"
            elif m == "objective_type":
                ra[m] = "VIDEO_VIEWS"
            elif m in ("ad_name", "ad_text", "adgroup_name"):
                ra[m] = f"{m} {seed}"
            elif m in ("campaign_id", "adgroup_id"):
                ra[m] = f"{m[:2]}{seed // 100}"
            else:
                ra[m] = str(seed % 97 + 1)
        return ra

    def _bao_cao(self, a: dict) -> dict:
        hop_le = set(QC.CHI_SO_HOP_LE) | set(QC.THUOC_TINH_AD) | {"currency", "timezone"}
        sai = [m for m in a["metrics"] if m not in hop_le]
        if sai:
            return {"code": 40002, "message": f"Invalid metric fields: {sai}"}
        assert len(a["metrics"]) <= TA.LO_CHI_SO
        assert a["page_size"] <= (TA.TRANG_ID if a["metrics"] == ["impressions"] else TA.TRANG)
        adv, cap, dims = a["advertiser_id"], a["data_level"], a["dimensions"]
        if adv == LE:
            rows = []
        elif a["report_type"] == "AUDIENCE":
            chieu = dims[1]
            gt = {"age": ["AGE_18_24", "AGE_25_34"], "gender": ["FEMALE", "MALE"],
                  "province_id": ["1581129", "-1"], "platform": ["ANDROID", "IPHONE"]}[chieu]
            rows = [{"dimensions": {"advertiser_id": adv, chieu: g},
                     "metrics": self._chi_so(a["metrics"], i, 1000 * (i + 1))}
                    for i, g in enumerate(gt)]
        elif cap == "AUCTION_ADVERTISER":
            rows = [{"dimensions": {"advertiser_id": adv, "stat_time_day": f"{d} 00:00:00"},
                     "metrics": self._chi_so(a["metrics"], d.day, 1000 + d.day)}
                    for d in self._ngay(a["start_date"], a["end_date"])]
        else:
            dim = dims[0]
            n = self.so_campaign if dim == "campaign_id" else self.so_ad
            # ID duy nhất toàn TikTok (như thật): gắn 4 số cuối của tài khoản.
            tat_ca = [f"{dim[:2]}{adv[-4:]}{i:04d}" for i in range(n + self.so_khong_chay)]
            hien = {x: (n + 500 - i if i < n else 0) for i, x in enumerate(tat_ca)}
            if "stat_time_day" in dims:
                loc = a["filtering"][0]
                assert loc["field_name"] == TA.LOC_ID[dim] and loc["filter_type"] == "IN"
                ids = json.loads(loc["filter_value"])            # chuỗi JSON, ≤ 100 ID
                assert len(ids) <= TA.LO_ID
                rows = [{"dimensions": {dim: x, "stat_time_day": f"{d} 00:00:00"},
                         "metrics": self._chi_so(a["metrics"], 100 * int(x[2:]) + d.day,
                                                 hien[x] if d.day % 2 else 0)}
                        for x in ids for d in self._ngay(a["start_date"], a["end_date"])]
            else:
                assert a["order_field"] == "impressions" and a["order_type"] == "DESC"
                rows = [{"dimensions": {dim: x}, "metrics": {"impressions": str(hien[x])}}
                        for x in tat_ca]
        cs = a["page_size"]
        tong = max(1, -(-len(rows) // cs))
        trang = rows[(a["page"] - 1) * cs: a["page"] * cs]
        return {"code": 0, "message": "OK", "data": {"list": trang, "page_info": {
            "page": a["page"], "page_size": cs, "total_number": len(rows), "total_page": tong}}}

    def _cong_cu(self, ten: str, a: dict) -> dict:
        self.cong_cu.append((ten, a))
        if ten == "auth_advertiser_get":
            return {"code": 0, "data": {"list": [{"advertiser_id": k, "advertiser_name": v + " "}
                                                 for k, v in self.tk.items()]}}
        if ten == "advertiser_info_get":
            return {"code": 0, "data": {"list": [{"advertiser_id": k, "currency": "VND",
                                                  "display_timezone": "Asia/Ho_Chi_Minh",
                                                  "name": v} for k, v in self.tk.items()
                                                 if k in a["advertiser_ids"]]}}
        if ten == "report_integrated_get":
            return self._bao_cao(a)
        return {"code": 40001, "message": "không có"}

    def xu_ly(self, req: httpx.Request) -> httpx.Response:
        self.goi.append(req)
        duong = req.url.path
        if duong.endswith("/oauth/register"):
            d = json.loads(req.content)
            self.dang_ky.append(d)
            return httpx.Response(201, json={"client_id": "cid-gia-1", **d})
        if duong.endswith("/oauth/token"):
            f = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
            if f["grant_type"] == "authorization_code":
                self.doi_ma.append(f)
                if f.get("code") != "ma-dung":
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json={
                    "access_token": self.access, "expires_in": 86399, "token_type": "Bearer",
                    "refresh_token": self.refresh, "refresh_token_expires_in": 2591999,
                    "scope": "mcp:tt4b"})
            if self.lam_moi_loi or f.get("refresh_token") != self.refresh:
                return httpx.Response(400, json={"error": "invalid_grant"})
            self.access = "act.MOI" + self.access[7:]
            self.token_hop_le.add(self.access)
            rt = self.refresh_moi or self.refresh
            return httpx.Response(200, json={"access_token": self.access, "expires_in": 86399,
                                             "refresh_token": rt,
                                             "refresh_token_expires_in": self.rt_con_giay})
        if duong.endswith("/oauth/revoke"):
            self.thu_hoi.append(parse_qs(req.content.decode())["token"][0])
            return httpx.Response(200, json={})
        # MCP
        tok = req.headers.get("authorization", "").removeprefix("Bearer ")
        if tok not in self.token_hop_le:
            return httpx.Response(401, json={"error": "invalid_token"})
        m = json.loads(req.content)
        if m["method"] == "initialize":
            body = {"jsonrpc": "2.0", "id": m["id"], "result": {"serverInfo": {"name": "tt"}}}
            return httpx.Response(200, headers={"Mcp-Session-Id": "phien-1",
                                                "Content-Type": "text/event-stream"},
                                  text="event: message\ndata: " + json.dumps(body) + "\n\n")
        if m["method"] == "notifications/initialized":
            return httpx.Response(202)
        assert req.headers.get("mcp-session-id") == "phien-1"
        p = m["params"]
        kq = self._cong_cu(p["name"], p["arguments"])
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": m["id"], "result": {
            "content": [{"type": "text", "text": json.dumps(kq, ensure_ascii=False)}]}})


# ───────────────────────────── kho quảng cáo giả ─────────────────────────────
class GiaKhoQC:
    """Bản bộ nhớ của `dashboard.kho_qc` — cùng tên hàm, khoá chính như schema.sql."""

    def __init__(self, ben=("hapas", "matemade")):
        self.kn: dict | None = None
        self.tk: dict[str, dict] = {}
        self.bang = {b: {} for b in KQ.BANG_QC}
        self.ben = set(ben)
        self.dang = False
        self.nk: list[tuple] = []

    # kết nối
    def doc_ket_noi(self, ncc=KQ.NCC):
        return dict(self.kn) if self.kn else None

    def _kn(self):
        if self.kn is None:
            self.kn = {"nha_cung_cap": KQ.NCC, "loai": "mcp_oauth", "trang_thai": "chua_ket_noi"}
        return self.kn

    def luu_dang_ky(self, client_id, redirect_uri, ncc=KQ.NCC):
        self._kn().update(client_id=client_id, redirect_uri=redirect_uri)

    def luu_token(self, ai, loai, access_enc, refresh_enc, access_het, refresh_het, ncc=KQ.NCC):
        self._kn().update(loai=loai, access_token_enc=access_enc, refresh_token_enc=refresh_enc,
                          access_het_luc=access_het, refresh_het_luc=refresh_het, nguoi_cap=ai,
                          cap_luc=BAY, trang_thai="hoat_dong", loi_cuoi=None)
        self.nk.append((ai, "ket_noi_tiktok"))

    def _dung(self, neu):
        k = self._kn()
        return neu is None or (k.get("access_token_enc"), k.get("cap_luc")) == tuple(neu)

    def cap_nhat_token(self, access_enc, access_het, refresh_enc, refresh_het, neu, ncc=KQ.NCC):
        if not self._dung(neu):                      # như SQL: IS NOT DISTINCT FROM giá trị đã đọc
            return False
        k = self._kn()
        k.update(access_token_enc=access_enc, access_het_luc=access_het, refresh_het_luc=refresh_het,
                 lam_moi_luc=BAY, trang_thai="hoat_dong")
        if refresh_enc:
            k["refresh_token_enc"] = refresh_enc
        return True

    def ghi_trang_thai(self, trang_thai, loi=None, ncc=KQ.NCC, *, neu=None, con_token=False):
        if not self._dung(neu) or (con_token and not self._kn().get("access_token_enc")):
            return
        self._kn()["trang_thai"] = trang_thai
        if loi:
            self.kn["loi_cuoi"] = str(loi)[:500]

    def ghi_goi_ok(self, ncc=KQ.NCC):
        self._kn()["goi_ok_luc"] = BAY

    def ngat(self, ai, ncc=KQ.NCC):
        self._kn().update(access_token_enc=None, refresh_token_enc=None, access_het_luc=None,
                          refresh_het_luc=None, trang_thai="da_ngat")
        self.nk.append((ai, "ngat_tiktok"))

    def bat_dau_dong_bo(self, ncc=KQ.NCC):
        self._kn().update(dong_bo_bat_dau=BAY, dong_bo_xong=None, yeu_cau_dong_bo_luc=None)

    def yeu_cau_dong_bo(self, ai, ncc=KQ.NCC):
        k = self._kn()
        k["yeu_cau_dong_bo_luc"] = k.get("yeu_cau_dong_bo_luc") or BAY
        k["yeu_cau_boi"] = ai
        self.nk.append((ai, "dong_bo_tiktok"))

    def ket_thuc_dong_bo(self, so_dong, loi, den_ngay, ncc=KQ.NCC):
        k = self._kn()
        k.update(dong_bo_xong=BAY, dong_bo_so_dong=so_dong, dong_bo_loi=loi)
        if not loi:
            k["dong_bo_ok_luc"] = BAY
        if den_ngay:
            k["so_den_ngay"] = max(k.get("so_den_ngay") or den_ngay, den_ngay)

    @contextlib.contextmanager
    def khoa_dong_bo(self):
        if self.dang:
            yield False
            return
        self.dang = True
        try:
            yield True
        finally:
            self.dang = False

    def dang_dong_bo(self):
        return self.dang

    # tài khoản (cùng luật SQL của kho_qc.ghi_tk / gan_ben)
    def cac_tk(self):
        return [dict(v) for _, v in sorted(self.tk.items(), key=lambda x: (x[1]["ten"], x[0]))]

    def ben_co_tk(self):
        return {t["don_vi"] for t in self.tk.values() if t.get("don_vi")}

    def ghi_tk(self, ds, ncc=KQ.NCC):
        moi = []
        for t in ds:
            adv = t["advertiser_id"]
            tu_dong = QC.ben_tu_dong(t.get("ten") or "")
            tu_dong = tu_dong if tu_dong in self.ben else None
            cu = self.tk.get(adv)
            if cu is None:
                moi.append(adv)
                self.tk[adv] = {"advertiser_id": adv, "ten": t.get("ten") or "", "don_vi": tu_dong,
                                "gan_tay": False, "gan_luc": None,
                                "tien_te": t.get("tien_te") or "VND",
                                "mui_gio": t.get("mui_gio") or "Asia/Ho_Chi_Minh",
                                "dang_dong_bo": True, "con_quyen": True, "nap_lui_xong_luc": None,
                                "nap_lui_tu": None,
                                "khan_gia_luc": None, "thay_lan_dau": BAY, "thay_cuoi": BAY,
                                "cap_nhat_luc": BAY}
            else:
                cu.update(ten=t.get("ten") or "", con_quyen=True,
                          tien_te=t.get("tien_te") or "VND",
                          mui_gio=t.get("mui_gio") or "Asia/Ho_Chi_Minh")
                if not cu["gan_tay"]:
                    cu["don_vi"] = tu_dong
        thay = {t["advertiser_id"] for t in ds}
        for adv, t in self.tk.items():
            if adv not in thay:
                t["con_quyen"] = False
        k = self._kn()
        truoc = k.get("so_tk_thay")
        k.update(so_tk_truoc=truoc, so_tk_thay=len(thay))
        return {"so_tk_thay": len(thay), "so_tk_truoc": truoc, "moi": moi}

    def gan_ben(self, ai, advertiser_id, don_vi, dang_dong_bo):
        if advertiser_id not in self.tk:
            raise LoiDuLieu("Không có tài khoản quảng cáo này.")
        if don_vi and don_vi not in self.ben:
            raise LoiDuLieu("Không có bên này.")
        self.tk[advertiser_id].update(don_vi=don_vi, dang_dong_bo=bool(dang_dong_bo), gan_tay=True)
        self.nk.append((ai, "gan_ben_tk_qc"))

    def dat_nap_lui(self, adv, tu, xong):
        self.tk[adv]["nap_lui_tu"] = tu
        if xong:
            self.tk[adv]["nap_lui_xong_luc"] = BAY

    def dat_khan_gia(self, adv):
        self.tk[adv]["khan_gia_luc"] = BAY

    # số liệu: upsert theo PK
    def _ghi(self, bang, rows):
        _, pk = KQ.BANG_QC[bang]
        for r in rows:
            self.bang[bang][tuple(r[k] for k in pk)] = dict(r)
        return len(rows)

    def ghi_tk_ngay(self, rows):
        return self._ghi("qc_tk_ngay", rows)

    def ghi_campaign_ngay(self, rows):
        return self._ghi("qc_campaign_ngay", rows)

    def ghi_ad_ngay(self, rows):
        return self._ghi("qc_ad_ngay", rows)

    def ghi_khan_gia(self, rows):
        return self._ghi("qc_khan_gia", rows)

    # đọc
    @staticmethod
    def _cong(rows):
        ra = {c: None for c in QC.TEN_COT_SO}
        for r in rows:
            for c in QC.TEN_COT_SO:
                if r.get(c) is not None:
                    ra[c] = (ra[c] or 0) + r[c]
        return ra

    def qc_tong(self, ids, tu, den):
        rows = [r for r in self.bang["qc_tk_ngay"].values()
                if r["advertiser_id"] in ids and tu <= r["ngay"] <= den]
        return {**self._cong(rows), "so_ngay": len({r["ngay"] for r in rows})}

    def qc_theo_ngay(self, ids, tu, den):
        theo: dict = {}
        for r in self.bang["qc_tk_ngay"].values():
            if r["advertiser_id"] in ids and tu <= r["ngay"] <= den:
                theo.setdefault(r["ngay"], []).append(r)
        return [{"ngay": d, **self._cong(rs)} for d, rs in sorted(theo.items())]

    def qc_top(self, cap, ids, tu, den, sap, n=20):
        bang, khoa = (("qc_campaign_ngay", "campaign_id") if cap == "campaign"
                      else ("qc_ad_ngay", "ad_id"))
        nhom: dict = {}
        for r in self.bang[bang].values():
            if r["advertiser_id"] in ids and tu <= r["ngay"] <= den:
                nhom.setdefault(r[khoa], []).append(r)
        cot = QC.SAP_XEP.get(sap, sap)
        ra = []
        for k, rs in nhom.items():
            cuoi = max(rs, key=lambda r: r["ngay"])
            x = {khoa: k, "advertiser_id": cuoi["advertiser_id"], **self._cong(rs)}
            if cap == "campaign":
                x.update(ten=cuoi["ten"], muc_tieu=cuoi["muc_tieu"])
            else:
                x.update(campaign_id=cuoi["campaign_id"], ten_ad=cuoi["ten_ad"],
                         noi_dung=cuoi["noi_dung"], ten_campaign=cuoi["ten_campaign"])
            ra.append(x)
        ra.sort(key=lambda x: (-(x.get(cot) or 0), x[khoa]))
        return ra[:n]

    def qc_khan_gia(self, ids):
        rows = [r for r in self.bang["qc_khan_gia"].values() if r["advertiser_id"] in ids]
        moi = {}
        for r in rows:
            k = (r["den"], r["tu"])
            if r["advertiser_id"] not in moi or k > moi[r["advertiser_id"]]:
                moi[r["advertiser_id"]] = k
        rows = [r for r in rows if (r["den"], r["tu"]) == moi[r["advertiser_id"]]]
        nhom: dict = {}
        for r in rows:
            nhom.setdefault((r["chieu"], r["gia_tri"]), []).append(r)
        ra = [{"chieu": c, "gia_tri": g, "tu": min(x["tu"] for x in rs),
               "den": max(x["den"] for x in rs), **self._cong(rs)} for (c, g), rs in nhom.items()]
        return {"rows": ra, "tu": min((r["tu"] for r in ra), default=None),
                "den": max((r["den"] for r in ra), default=None)}

    def qc_moi(self, ids):
        rows = [r for r in self.bang["qc_tk_ngay"].values() if r["advertiser_id"] in ids]
        return {"ngay_cuoi": max((r["ngay"] for r in rows), default=None),
                "ghi_luc": BAY if rows else None}


def _dv(kho_qc=None, tt=None, bay=BAY):
    tt = tt or GiaTikTok()
    kho_qc = kho_qc if kho_qc is not None else GiaKhoQC()
    dv = TA.DichVu(kho_qc, http=TA.Http(transport=tt.transport(), ngu=lambda s: None),
                   khoa=KHOA_TT, ngu=lambda s: None, bay_gio=lambda: bay, log=lambda *a: None)
    return dv, kho_qc, tt


def _ket_noi_san(dv, tt, *, het_at=None, het_rt=None):
    """Kho như vừa OAuth xong (token đã mã hoá)."""
    k = dv.kho._kn()
    k.update(client_id="cid-gia-1", redirect_uri="https://social.hapas.vn/tiktok/xong")
    dv.kho.luu_token(QL, "mcp_oauth", TA.ma_hoa(tt.access, KHOA_TT, "access"),
                     TA.ma_hoa(tt.refresh, KHOA_TT, "refresh"),
                     het_at or BAY + datetime.timedelta(hours=20),
                     het_rt or BAY + datetime.timedelta(days=25))


def _tao_app(kho=None, kho_qc=None, tt=None):
    kho = kho or GiaKho()
    for e, ben in ((HP_QL, {"hapas": "quan_ly"}), (MM_XEM, {"matemade": "xem"}),
                   (MM_QL, {"matemade": "quan_ly"})):
        kho.quyen[e] = ben
        kho.nguoi[e] = PQvai(ben)
    dv, kho_qc, tt = _dv(kho_qc, tt)
    app = A.tao_app(kho, cau_hinh=CFG, lark=lark_gia(), dong_bo=GiaDongBo(),
                    danh_ba=danh_ba_gia(), chu_ky_kiem=None, kho_qc=kho_qc, tiktok=dv)
    from fastapi.testclient import TestClient
    c = TestClient(app, base_url="https://testserver", follow_redirects=False)
    return app, c, kho, kho_qc, tt, dv


def PQvai(ben):
    return "quan_ly" if "quan_ly" in ben.values() else "xem"


def _khoa_lap(x):
    """Mọi khoá dict (đệ quy) — kiểm API không có khoá tiền."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from _khoa_lap(v)
    elif isinstance(x, list):
        for v in x:
            yield from _khoa_lap(v)


# ───────────────────────────── danh sách công cụ chỉ đọc ─────────────────────────────
@pytest.mark.parametrize("ten", ["tool_execute", "tool_list", "tool_get", "bc_get", "identity_get", "smart_plus_campaign_create",
                                 "smart_plus_ad_status_update", "campaign_budget_update",
                                 "bc_create", "ad_delete", "", "REPORT_INTEGRATED_GET"])
def test_chan_cong_cu_ghi_va_tool_execute_truoc_khi_gui(ten):
    tt = GiaTikTok()
    mcp = TA.Mcp(tt.access, TA.Http(transport=tt.transport(), ngu=lambda s: None))
    with pytest.raises(TA.LoiChan):
        mcp.goi(ten, {"tool_name": "report_integrated_get", "params": {}})
    assert tt.goi == []                       # không một byte nào tới TikTok


def test_cong_cu_doc_di_qua_va_doc_sse_phien():
    # Soát 19/10/2026: chỉ đúng các công cụ mã dùng.
    assert TA.CONG_CU_DOC == {"auth_advertiser_get", "advertiser_info_get", "report_integrated_get"}
    src = (GOC / "dashboard" / "tiktok_ads.py").read_text(encoding="utf-8")
    goi = set(re.findall(r'goi\("([a-z_]+)"', src))
    assert goi == TA.CONG_CU_DOC, goi
    tt = GiaTikTok()
    mcp = TA.Mcp(tt.access, TA.Http(transport=tt.transport(), ngu=lambda s: None))
    d = mcp.goi("auth_advertiser_get", {})
    assert len(d["list"]) == 4
    m = [json.loads(r.content)["method"] for r in tt.goi]
    assert m == ["initialize", "notifications/initialized", "tools/call"]
    assert json.loads(tt.goi[0].content)["params"]["protocolVersion"] == "2025-06-18"
    assert tt.goi[0].headers["accept"] == "application/json, text/event-stream"
    with pytest.raises(TA.LoiXacThuc):
        TA.Mcp("token-sai-0123456789", TA.Http(transport=tt.transport(), ngu=lambda s: None)
               ).goi("auth_advertiser_get", {})


def test_loi_mang_thu_lai_ba_lan_roi_bao_loi_khong_lo_token():
    lan = []

    def hong(req):
        lan.append(1)
        raise httpx.RemoteProtocolError("peer closed connection (IncompleteRead)")
    nghi = []
    http = TA.Http(transport=httpx.MockTransport(hong), ngu=nghi.append)
    with pytest.raises(TA.LoiTikTok) as e:
        TA.Mcp("act.BIMAT0123456789abcdefghijk", http).goi("auth_advertiser_get", {})
    assert len(lan) == 3 and nghi == [3, 6]
    assert "BIMAT" not in str(e.value)
    assert TA.gon_loi("lỗi act.ABCDEF0123456789abcdef0123 https://x.y/z?t=1") == "lỗi <…> <url>"


# ───────────────────────────── mã hoá token ─────────────────────────────
def test_ma_hoa_aes_gcm_vong_tron():
    s = TA.ma_hoa("act.bi-mat-123", KHOA_TT, "access")
    b = base64.urlsafe_b64decode(s)
    assert b[:1] == b"" and len(b) == 1 + 12 + len("act.bi-mat-123") + 16
    assert "bi-mat" not in s
    assert TA.giai_ma(s, KHOA_TT, "access") == "act.bi-mat-123"
    assert TA.ma_hoa("x", KHOA_TT, "access") != TA.ma_hoa("x", KHOA_TT, "access")   # nonce
    # Đúng AES-256-GCM chuẩn: thư viện giải được với AAD = nhà cung cấp + cột.
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    assert AESGCM(KHOA_TT).decrypt(b[1:13], b[13:], b"lang-nghe|tiktok_ads|access")         == b"act.bi-mat-123"


def test_ma_hoa_bi_sua_sai_aad_sai_khoa_deu_tu_choi():
    s = TA.ma_hoa("act.bi-mat-123", KHOA_TT, "access")
    with pytest.raises(TA.LoiMaHoa):
        TA.giai_ma(s, KHOA_TT, "refresh")              # tráo cột access ↔ refresh (AAD)
    with pytest.raises(TA.LoiMaHoa):
        TA.giai_ma(s, bytes(32), "access")             # khoá khác
    for i in (0, 5, 20, -1):                           # phiên bản, nonce, bản mã, thẻ
        b = bytearray(base64.urlsafe_b64decode(s))
        b[i] ^= 1
        with pytest.raises(TA.LoiMaHoa):
            TA.giai_ma(base64.urlsafe_b64encode(bytes(b)).decode(), KHOA_TT, "access")
    for rac in ("", "khong-phai-base64!!", base64.urlsafe_b64encode(b"ngan").decode()):
        with pytest.raises(TA.LoiMaHoa):
            TA.giai_ma(rac, KHOA_TT, "access")
    for khoa in (b"", bytes(16), bytes(31), bytes(33)):  # sai độ dài: từ chối, không cắt/độn
        with pytest.raises(TA.LoiMaHoa):
            TA.ma_hoa("x", khoa, "access")
        with pytest.raises(TA.LoiMaHoa):
            TA.giai_ma(s, khoa, "access")


def test_khoa_sai_thi_the_bao_ro_va_dong_bo_ghi_loi_khong_sap(monkeypatch):
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt)
    monkeypatch.setenv("TIKTOK_KHOA_MA_HOA", base64.b64encode(bytes(16)).decode())
    hong = TA.DichVu(kho_qc, http=dv.http, khoa=None, bay_gio=lambda: BAY)
    the = hong.the()
    assert the["co_khoa"] is False and "32 byte" in the["loi_khoa"]
    kq = hong.dong_bo()
    assert "32 byte" in kq["bo_qua"] and tt.goi == []
    assert kho_qc.kn["trang_thai"] == "loi" and "32 byte" in kho_qc.kn["loi_cuoi"]
    with pytest.raises(TA.LoiMaHoa):
        hong.luu_api_token(QL, "apitoken0123456789ABCDEFabcdef")
    app, c, _kho, _kq, _tt, _dv2 = _tao_app(kho_qc=kho_qc)
    app.state.tiktok = hong
    csrf = dang_nhap(c, QL)
    t = c.get("/quan-tri").text
    assert c.get("/quan-tri").status_code == 200 and 'data-o="tt-loi-khoa"' in t
    r = c.post("/tiktok/token", data={"csrf": csrf, "token": "apitoken0123456789ABCDEFabcdef"})
    assert "32 byte" in c.get(r.headers["location"]).text
    assert c.post("/tiktok/ket-noi", data={"csrf": csrf}).status_code == 303
    assert tt.dang_ky == []


def test_khoa_tu_env():
    k = base64.b64encode(KHOA_TT).decode()
    assert TA.khoa_tu_env({"TIKTOK_KHOA_MA_HOA": k}) == KHOA_TT
    assert TA.khoa_tu_env({"TIKTOK_KHOA_MA_HOA": base64.urlsafe_b64encode(KHOA_TT).decode()}) \
        == KHOA_TT
    assert TA.khoa_tu_env({}) is None
    for sai in ("ngan", base64.b64encode(b"x" * 16).decode(), "!!!!"):
        with pytest.raises(TA.LoiMaHoa):
            TA.khoa_tu_env({"TIKTOK_KHOA_MA_HOA": sai})


# ───────────────────────────── OAuth (qua dashboard) ─────────────────────────────
def _bat_dau(c, csrf):
    r = c.post("/tiktok/ket-noi", data={"csrf": csrf})
    assert r.status_code == 303, r.text
    u = urlsplit(r.headers["location"])
    return {k: v[0] for k, v in parse_qs(u.query).items()}, u


def test_oauth_dang_ky_pkce_doi_ma_luu_token_ma_hoa():
    app, c, _kho, kho_qc, tt, _dv = _tao_app()
    csrf = dang_nhap(c, QL)
    q, u = _bat_dau(c, csrf)
    assert f"{u.scheme}://{u.netloc}{u.path}" == TA.DUONG_UY_QUYEN
    assert q["client_id"] == "cid-gia-1" and q["scope"] == "mcp:tt4b"
    assert q["resource"] == TA.BASE and q["response_type"] == "code"
    assert q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == "https://social.hapas.vn/tiktok/xong"
    assert tt.dang_ky[0]["token_endpoint_auth_method"] == "none"
    assert tt.dang_ky[0]["redirect_uris"] == ["https://social.hapas.vn/tiktok/xong"]
    r = c.get("/tiktok/xong", params={"code": "ma-dung", "state": q["state"]})
    assert r.status_code == 303 and r.headers["location"] == "/quan-tri#tiktok"
    ver = tt.doi_ma[0]["code_verifier"]
    chal = base64.urlsafe_b64encode(hashlib.sha256(ver.encode()).digest()).rstrip(b"=").decode()
    assert chal == q["code_challenge"] and tt.doi_ma[0]["client_id"] == "cid-gia-1"
    kn = kho_qc.kn
    assert kn["trang_thai"] == "hoat_dong" and kn["nguoi_cap"] == QL
    # Sau kết nối: chỉ ghi yêu cầu đồng bộ — không đọc báo cáo nào trong tiến trình web.
    assert kn["yeu_cau_dong_bo_luc"] == BAY
    assert not any(t == "report_integrated_get" for t, _ in tt.cong_cu)
    assert tt.refresh not in json.dumps(kn, default=str)
    assert TA.giai_ma(kn["refresh_token_enc"], KHOA_TT, "refresh") == tt.refresh
    assert kn["refresh_het_luc"] - BAY == datetime.timedelta(seconds=2591999)
    assert set(kho_qc.tk) == set(TK_MAU) and kho_qc.tk[MM_MKT]["don_vi"] == "matemade"
    t = c.get("/quan-tri").text
    assert "Đã kết nối TikTok Ads — thấy 4 tài khoản" in t
    # Lần kết nối sau dùng lại client đã đăng ký (cùng redirect_uri).
    _bat_dau(c, csrf)
    assert len(tt.dang_ky) == 1
    # Trang Quản trị của quản trị viên cho form chuyển hướng tới ĐÚNG gốc TikTok (CSP form-action).
    csp = c.get("/quan-tri").headers["content-security-policy"]
    assert csp.endswith("form-action 'self' https://business-api.tiktok.com")
    assert c.get("/").headers["content-security-policy"].endswith("form-action 'self'")
    del app


def test_get_ket_noi_khong_tac_dung_phu():
    """L5: GET /tiktok/ket-noi (link cũ, prefetch, ảnh nhúng…) chỉ đưa về thẻ — không đăng ký client,
    không đặt cookie OAuth."""
    _app, c, _kho, _kho_qc, tt, _dv = _tao_app()
    dang_nhap(c, QL)
    r = c.get("/tiktok/ket-noi")
    assert r.status_code == 303 and r.headers["location"] == "/quan-tri#tiktok"
    assert tt.goi == [] and A.COOKIE_TIKTOK not in r.headers.get("set-cookie", "")
    assert c.post("/tiktok/ket-noi", data={"csrf": "sai"}).status_code == 403
    assert c.post("/tiktok/ket-noi", data={"csrf": "x"},
                  headers={"origin": "https://evil.example"}).status_code == 403
    assert tt.goi == []
    t = c.get("/quan-tri").text
    assert re.search(r'<form method="post" action="/tiktok/ket-noi">\s*<input type="hidden" '
                     r'name="csrf"', t)


@pytest.mark.parametrize("hong", ["state_sai", "khong_cookie", "phien_khac", "nguoi_khac", "loi",
                                  "het_han"])
def test_oauth_xong_tu_choi_state_csrf_sai(hong):
    _app, c, kho, kho_qc, tt, _dv = _tao_app()
    kho.quan_tri.add(GIAM := "giamdoc@hapas.vn")
    kho.nguoi[GIAM] = "quan_ly"
    csrf = dang_nhap(c, QL)
    q, _ = _bat_dau(c, csrf)
    p = {"code": "ma-dung", "state": q["state"]}
    if hong == "state_sai":
        p["state"] = DN.ky({"n": "khac", "c": "x", "het": 9e9}, KHOA, "tiktok_state")
    elif hong == "khong_cookie":
        phien = c.cookies.get(DN.COOKIE_PHIEN)
        c.cookies.clear()                    # mất cookie lượt OAuth, giữ ĐÚNG phiên cũ
        c.cookies.set(DN.COOKIE_PHIEN, phien)
    elif hong == "phien_khac":
        dang_nhap(c, QL)                     # cùng người, PHIÊN mới (CSRF khác) → state không khớp
    elif hong == "nguoi_khac":
        dang_nhap(c, GIAM)
    elif hong == "loi":
        p = {"error": "access_denied", "state": q["state"]}
    elif hong == "het_han":
        p["state"] = DN.ky({**DN.mo(q["state"], KHOA, "tiktok_state"), "het": 1}, KHOA,
                           "tiktok_state")
    r = c.get("/tiktok/xong", params=p)
    assert r.status_code == 303
    assert tt.doi_ma == [] and not (kho_qc.kn or {}).get("access_token_enc")


def test_oauth_chi_quan_tri_vien():
    _app, c, _kho, kho_qc, tt, _dv = _tao_app()
    for ai in (XEM, HP_QL, MM_QL):
        csrf = dang_nhap(c, ai)
        assert c.post("/tiktok/ket-noi", data={"csrf": csrf}).status_code == 403, ai
        assert c.get("/tiktok/xong", params={"code": "ma-dung", "state": "x"}).status_code == 403
        for duong, form in (("/tiktok/dong-bo", {}), ("/tiktok/ngat", {}),
                            ("/tiktok/token", {"token": "x" * 20}),
                            ("/tiktok/gan-ben", {"advertiser_id": HAPAS_KOC, "don_vi": "hapas"})):
            r = c.post(duong, data={"csrf": csrf, **form})
            assert r.status_code == 403, (ai, duong)
    assert tt.goi == [] and kho_qc.nk == []


def test_post_tiktok_doi_csrf():
    _app, c, _kho, _kho_qc, _tt, _dv = _tao_app()
    dang_nhap(c, QL)
    for duong in ("/tiktok/ket-noi", "/tiktok/dong-bo", "/tiktok/ngat", "/tiktok/token",
                  "/tiktok/gan-ben"):
        assert c.post(duong, data={"csrf": "sai"}).status_code == 403, duong
        r = c.post(duong, data={"csrf": "x"}, headers={"origin": "https://evil.example"})
        assert r.status_code == 403, duong


# ───────────────────────────── làm mới token ─────────────────────────────
def test_lam_moi_khi_access_sap_het_va_refresh_khong_duoc_gia_han():
    dv, kho_qc, tt = _dv()
    het_rt = BAY + datetime.timedelta(days=10)
    _ket_noi_san(dv, tt, het_at=BAY + datetime.timedelta(minutes=2), het_rt=het_rt)
    tt.rt_con_giay = 30 * 86400            # TikTok báo "30 ngày" nhưng là CÙNG token
    tok = dv.token()
    assert tok.startswith("act.MOI")
    k = kho_qc.kn
    assert k["refresh_het_luc"] == het_rt                     # không kéo dài hạn cứng
    assert TA.giai_ma(k["access_token_enc"], KHOA_TT, "access") == tok
    assert k["access_het_luc"] == BAY + datetime.timedelta(seconds=86399)
    # Còn hạn: không gọi TikTok.
    n = len(tt.goi)
    assert dv.token() == tok and len(tt.goi) == n
    # TikTok đếm lùi thật (hạn sớm hơn mốc đã lưu) → lấy mốc sớm hơn.
    k["access_het_luc"] = BAY
    tt.rt_con_giay = 5 * 86400
    dv.token()
    assert k["refresh_het_luc"] == BAY + datetime.timedelta(days=5)


def test_refresh_moi_that_su_thi_luu_han_moi():
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt, het_at=BAY, het_rt=BAY + datetime.timedelta(days=3))
    tt.refresh_moi = "rft.MOIHOANTOAN0123456789abcdef"
    tt.rt_con_giay = 2591999
    dv.token()
    k = kho_qc.kn
    assert TA.giai_ma(k["refresh_token_enc"], KHOA_TT, "refresh") == tt.refresh_moi
    assert k["refresh_het_luc"] == BAY + datetime.timedelta(seconds=2591999)


def test_refresh_het_han_thi_trang_thai_het_han_khong_goi_tiktok():
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt, het_at=BAY - datetime.timedelta(hours=1),
                 het_rt=BAY - datetime.timedelta(minutes=1))
    with pytest.raises(TA.LoiHetHan):
        dv.token()
    assert tt.goi == [] and kho_qc.kn["trang_thai"] == "het_han"
    the = dv.the()
    assert the["trang_thai"] == "het_han" and the["muc"] == "loi" and the["con_ngay"] <= 0
    # Đồng bộ: thoát êm, ghi lỗi lượt, không ném.
    kq = dv.dong_bo()
    assert "hết hạn" in kq["bo_qua"] and kho_qc.kn["dong_bo_loi"].startswith("hết hạn")


def test_tiktok_tu_choi_refresh_thi_het_han():
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt, het_at=BAY, het_rt=BAY + datetime.timedelta(days=9))
    tt.lam_moi_loi = True
    with pytest.raises(TA.LoiHetHan):
        dv.token()
    assert kho_qc.kn["trang_thai"] == "het_han"


@pytest.mark.parametrize("ngay,muc", [(20, "tot"), (6.5, "canh"), (1.5, "loi")])
def test_the_dem_nguoc_mau(ngay, muc):
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt, het_rt=BAY + datetime.timedelta(days=ngay))
    the = dv.the()
    assert the["muc"] == muc and abs(the["con_ngay"] - ngay) < 0.1
    assert not any("token" in k and "enc" in k for k in the)
    for enc in (kho_qc.kn["access_token_enc"], kho_qc.kn["refresh_token_enc"]):
        assert enc not in json.dumps(the, default=str)


def test_api_token_khong_het_han_khong_lam_moi():
    dv, kho_qc, tt = _dv()
    tt.token_hop_le.add(TOK := "apitoken0123456789ABCDEFabcdef")
    kq = dv.luu_api_token(QL, TOK)
    assert kq["so_tk_thay"] == 4
    k = kho_qc.kn
    assert k["loai"] == "api_token" and k["refresh_token_enc"] is None
    assert k["access_het_luc"] is None and k["refresh_het_luc"] is None
    n = len(tt.goi)
    assert dv.token() == TOK and len(tt.goi) == n            # không làm mới
    the = dv.the()
    assert the["khong_het_han"] and the["con_ngay"] is None and the["muc"] == "tot"
    with pytest.raises(TA.LoiXacThuc):                         # token sai: không lưu
        TA.DichVu(GiaKhoQC(), http=TA.Http(transport=tt.transport(), ngu=lambda s: None),
                  khoa=KHOA_TT, ngu=lambda s: None).luu_api_token(QL, "saisaisaisaisaisai99")


def test_ngat_thu_hoi_va_xoa_token():
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt)
    assert dv.ngat(QL) is True
    assert tt.thu_hoi == [tt.access, tt.refresh]
    assert kho_qc.kn["access_token_enc"] is None and kho_qc.kn["trang_thai"] == "da_ngat"
    assert dv.dong_bo() == {"bo_qua": "chưa kết nối TikTok Ads"}


# ───────────────────────────── báo cáo + đồng bộ ─────────────────────────────
def test_lay_id_dung_o_dong_khong_dau_tien():
    tt = GiaTikTok(so_campaign=3, so_khong_chay=2500)          # 2.503 campaign, 3 chạy
    mcp = TA.Mcp(tt.access, TA.Http(transport=tt.transport(), ngu=lambda s: None),
                 ngu=lambda s: None)
    ids = TA.ids_co_chay(mcp, MM_MKT, "AUCTION_CAMPAIGN", "campaign_id",
                         datetime.date(2026, 10, 1), datetime.date(2026, 10, 18))
    assert ids == ["ca53290000", "ca53290001", "ca53290002"]
    trang = [a["page"] for t, a in tt.cong_cu if t == "report_integrated_get"]
    assert trang == [1]                                       # dừng ở trang đầu, không đọc 3 trang
    tt2 = GiaTikTok(so_campaign=1500, so_khong_chay=10)
    mcp2 = TA.Mcp(tt2.access, TA.Http(transport=tt2.transport(), ngu=lambda s: None),
                  ngu=lambda s: None)
    ids2 = TA.ids_co_chay(mcp2, MM_MKT, "AUCTION_CAMPAIGN", "campaign_id",
                          datetime.date(2026, 10, 1), datetime.date(2026, 10, 18))
    assert len(ids2) == 1500 and [a["page"] for _, a in tt2.cong_cu] == [1, 2]


def test_lo_100_id_45_chi_so_trang_200():
    tt = GiaTikTok(so_campaign=2, so_ad=250, so_khong_chay=30, tk={MM_MKT: "MATEMADE MKT"})
    dv, kho_qc, _ = _dv(tt=tt)
    _ket_noi_san(dv, tt)
    kq = dv.dong_bo(tu=datetime.date(2026, 10, 15), den=datetime.date(2026, 10, 18))
    assert kq["so_dong"] > 0 and not kq["loi"], kq
    loc = [json.loads(a["filtering"][0]["filter_value"]) for t, a in tt.cong_cu
           if t == "report_integrated_get" and a.get("filtering") and a["data_level"] == "AUCTION_AD"]
    assert sorted({len(x) for x in loc}) == [50, 100]          # 250 ad → 100 + 100 + 50
    assert all(len(a["metrics"]) <= 45 for t, a in tt.cong_cu if t == "report_integrated_get")
    assert all(a["page_size"] <= 200 for t, a in tt.cong_cu
               if t == "report_integrated_get" and a["metrics"] != ["impressions"])
    # Cấp tài khoản xin đủ 100 chỉ số hợp lệ (3 lượt ≤ 45), không tên lạ (TikTok từ chối cả lượt).
    tk = [a["metrics"] for t, a in tt.cong_cu if t == "report_integrated_get"
          and a["data_level"] == "AUCTION_ADVERTISER" and a["report_type"] == "BASIC"]
    assert sum(len(m) for m in tk[:3]) == len(QC.CHI_SO_HOP_LE) == 100
    # Chỉ ngày có hiển thị: ad giả chạy ngày lẻ.
    assert {r["ngay"].day % 2 for r in kho_qc.bang["qc_ad_ngay"].values()} == {1}
    assert len({r["ad_id"] for r in kho_qc.bang["qc_ad_ngay"].values()}) == 250


def test_dong_bo_nap_lui_90_ngay_roi_7_ngay_va_upsert_idempotent():
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt)
    kq = dv.dong_bo()
    assert kq["den_ngay"] == datetime.date(2026, 10, 18) and not kq["loi"], kq
    ngay = sorted({r["ngay"] for r in kho_qc.bang["qc_tk_ngay"].values()})
    assert ngay[0] == datetime.date(2026, 7, 21) and ngay[-1] == datetime.date(2026, 10, 18)
    kc = [(a["start_date"], a["end_date"]) for t, a in tt.cong_cu if t == "report_integrated_get"
          and a["data_level"] == "AUCTION_ADVERTISER" and a["report_type"] == "BASIC"
          and a["advertiser_id"] == HAPAS_KOC]
    assert list(dict.fromkeys(kc)) == [("2026-09-19", "2026-10-18"), ("2026-08-20", "2026-09-18"),
                                       ("2026-07-21", "2026-08-19")]          # mới trước
    assert all(t["nap_lui_xong_luc"] for a, t in kho_qc.tk.items())
    dem = {b: len(v) for b, v in kho_qc.bang.items()}
    so_ten = {a: (r["ten"], r["chi_so"].get("ctr")) for a, r in kho_qc.bang["qc_campaign_ngay"].items()}
    assert kho_qc.bang["qc_tk_ngay"][(HAPAS_KOC, datetime.date(2026, 10, 18))]["chi_so"][
        "secondary_goal_result"] is None                    # "-" của TikTok → null
    # Tài khoản không chạy (LE): không có dòng nào.
    assert not any(r["advertiser_id"] == LE for r in kho_qc.bang["qc_tk_ngay"].values())
    # Khán giả: 4 chiều × 2 giá trị × 3 tài khoản có chạy.
    assert dem["qc_khan_gia"] == 4 * 2 * 3
    tt.cong_cu.clear()
    dv.dong_bo()                                            # lần 2: chỉ 7 ngày, không nhân đôi
    kc2 = {(a["start_date"], a["end_date"]) for t, a in tt.cong_cu if t == "report_integrated_get"
           and a["report_type"] == "BASIC"}
    assert kc2 == {("2026-10-12", "2026-10-18")}
    assert {b: len(v) for b, v in kho_qc.bang.items()} == dem
    assert {a: (r["ten"], r["chi_so"].get("ctr")) for a, r in
            kho_qc.bang["qc_campaign_ngay"].items()} == so_ten
    assert not any(a.get("report_type") == "AUDIENCE" for _, a in tt.cong_cu)   # khán giả: tuần sau


def test_sql_upsert_theo_khoa_chinh():
    for bang, (_, pk) in KQ.BANG_QC.items():
        s = KQ.sql_upsert(bang)
        assert f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET" in s, bang
        assert "cap_nhat_luc = now()" in s and "%s::jsonb" in s
        assert not any(f"{k} = EXCLUDED.{k}" in s for k in pk), bang


def test_dong_bo_khong_chay_chong_va_chua_ket_noi_thoat_em(monkeypatch):
    dv, kho_qc, tt = _dv()
    assert dv.dong_bo() == {"bo_qua": "chưa kết nối TikTok Ads"}
    assert kho_qc.kn["trang_thai"] == "chua_ket_noi" and tt.goi == []
    _ket_noi_san(dv, tt)
    with kho_qc.khoa_dong_bo():
        assert dv.dong_bo() == {"bo_qua": "đang có lượt đồng bộ khác"}
    assert tt.goi == []
    k = TA.DichVu(kho_qc, khoa=None)
    monkeypatch.delenv("TIKTOK_KHOA_MA_HOA", raising=False)
    kq = k.dong_bo()
    assert "TIKTOK_KHOA_MA_HOA" in kq["bo_qua"] and kho_qc.kn["trang_thai"] == "loi"


def test_cli_khong_token_thoat_0_va_day_bq_sau_dong_bo(capsys):
    dv, kho_qc, tt = _dv()
    assert TA.main(["dong-bo"], dich_vu=dv) == 0
    assert "chưa kết nối" in capsys.readouterr().out

    class BQ:
        so = 0

        def da_bat(self):
            return True

        def chay(self):
            BQ.so += 1
            return {"bang": []}
    _ket_noi_san(dv, tt)
    assert TA.main(["dong-bo", "--tu", "2026-10-17", "--den", "2026-10-18"], dich_vu=dv,
                   dong_bo_bq=BQ()) == 0
    assert BQ.so == 1
    out = capsys.readouterr().out
    assert tt.access not in out and tt.refresh not in out
    assert TA.main(["trang-thai"], dich_vu=dv) == 0
    out = capsys.readouterr().out
    assert kho_qc.kn["access_token_enc"] not in out and tt.access not in out


# ───────────────────────────── gán bên ─────────────────────────────
@pytest.mark.parametrize("ten,ben", [("MATEMADE MKT", "matemade"), ("mate made 2", "matemade"),
                                     ("Mate  Made KD", "matemade"), ("MÂTEMADE", "matemade"),
                                     ("HAPAS - KOC", "hapas"), ("Công ty HTC", "hapas"),
                                     ("", "hapas")])
def test_gan_ben_tu_dong(ten, ben):
    assert QC.ben_tu_dong(ten) == ben


def test_gan_tay_khong_bi_ghi_de_khi_thay_lai():
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt)
    dv.kham_pha(dv.mcp())
    assert kho_qc.tk[MM_2]["don_vi"] == "matemade" and kho_qc.tk[LE]["don_vi"] == "hapas"
    kho_qc.gan_ben(QL, LE, None, False)
    kho_qc.gan_ben(QL, MM_2, "hapas", True)
    tt.tk.pop(HAPAS_KOC)
    kq = dv.kham_pha(dv.mcp())
    assert kho_qc.tk[LE]["don_vi"] is None and kho_qc.tk[MM_2]["don_vi"] == "hapas"
    assert kho_qc.tk[HAPAS_KOC]["con_quyen"] is False
    assert kq == {"so_tk_thay": 3, "so_tk_truoc": 4, "moi": []}
    assert dv.the()["it_hon"] is True


class _GhiSQL:
    """Kết nối giả cho kho_qc: ghi câu SQL + tham số, trả kết quả theo mẫu."""

    def __init__(self, tra=None):
        self.cau, self.tra = [], tra or {}

    @contextlib.contextmanager
    def __call__(self, trung="Dữ liệu này đã có."):
        yield self

    def execute(self, sql, ts=None):
        self.cau.append((sql, ts))
        self._r = next((v for k, v in self.tra.items() if k in sql), [])
        return self

    def fetchall(self):
        return list(self._r)

    def fetchone(self):
        return self._r[0] if self._r else None


def test_sql_ghi_tk_khong_de_ban_gan_tay(monkeypatch):
    g = _GhiSQL({"SELECT ma FROM don_vi": [{"ma": "hapas"}, {"ma": "matemade"}],
                 "SELECT advertiser_id FROM tk_quang_cao": [{"advertiser_id": HAPAS_KOC}],
                 "SELECT so_tk_thay": [{"so_tk_thay": 16}]})
    monkeypatch.setattr(KQ, "ket_noi", g)
    kq = KQ.ghi_tk([{"advertiser_id": MM_MKT, "ten": "MATEMADE MKT"},
                    {"advertiser_id": HAPAS_KOC, "ten": "HAPAS - KOC"}])
    them = [(s, t) for s, t in g.cau if s.startswith("INSERT INTO tk_quang_cao")]
    assert [t[2] for _, t in them] == ["matemade", "hapas"]
    assert ("don_vi = CASE WHEN tk_quang_cao.gan_tay THEN tk_quang_cao.don_vi "
            "ELSE EXCLUDED.don_vi END") in them[0][0]
    assert kq == {"so_tk_thay": 2, "so_tk_truoc": 16, "moi": [MM_MKT]}


# ───────────────────────────── trang + /api/qc: quyền ─────────────────────────────
def _co_so(app_kq):
    """Kho qc có số của 3 tài khoản (HAPAS - KOC → hapas; 2 tài khoản MATEMADE)."""
    app, _c, _kho, kho_qc, tt, dv = app_kq
    _ket_noi_san(dv, tt)
    dv.dong_bo(tu=datetime.date(2026, 10, 12), den=datetime.date(2026, 10, 18))
    kho_qc.tk[LE]["don_vi"] = None                     # một tài khoản chưa gán bên
    app.state.nho_ben_qc = (float("-inf"), set())
    return app_kq


Q = "tu=2026-10-12&den=2026-10-18"


def test_trang_va_api_quang_cao_chi_quan_tri_vien():
    """20/10/2026 chủ dự án: trang Quảng cáo + /api/qc chỉ quản trị viên; người khác (kể cả quản
    lý của bên) chỉ hỏi Mark — trang và API như không có (404)."""
    _app, c, _kho, _kho_qc, _tt, _dv = _co_so(_tao_app())
    for ai in (XEM, HP_QL, MM_XEM, MM_QL):
        dang_nhap(c, ai)
        assert c.get(f"/api/qc?{Q}").status_code == 404, ai
        assert c.get(f"/quang-cao?{Q}").status_code == 404, ai
        assert c.get(f"/api/qc?{Q}&ben=hapas").status_code == 404, ai
    dang_nhap(c, QL)
    d = c.get(f"/api/qc?{Q}").json()
    assert d["xem_tien"] is True and d["kpi"]["chi"] > 0
    assert d["kpi"]["roas_shop"] == round(d["kpi"]["gia_tri_mua_shop"] / d["kpi"]["chi"], 2)
    assert c.get(f"/api/qc?{Q}&ben=tat_ca").status_code == 200
    t = c.get(f"/quang-cao?{Q}").text
    assert "Hiển thị" in t and "HAPAS - KOC" in t


def test_xem_tien_moi_vai_trong_ben_chi_ben_minh():
    """20/10/2026: Quản lý và Chỉ xem đều được biết tiền của bên mình (qua Mark); bên khác,
    tài khoản chưa gán bên, "mọi bên": chỉ quản trị viên."""
    q_xem = {"la_quan_tri": False, "ben": {"hapas": "xem"}}
    q_ql = {"la_quan_tri": False, "ben": {"matemade": "quan_ly"}}
    q_qt = {"la_quan_tri": True, "ben": {}}
    assert QC.xem_tien(q_xem, "hapas") is True and QC.xem_tien(q_ql, "matemade") is True
    assert QC.xem_tien(q_xem, "matemade") is False and QC.xem_tien(q_ql, "hapas") is False
    assert QC.xem_tien(q_xem, None) is False and QC.xem_tien(None, "hapas") is False
    assert QC.xem_tien(q_qt, None) is True and QC.xem_tien(q_qt, "matemade") is True
    assert QC.thay_trang_qc(q_xem, {"hapas"}) is False and QC.thay_trang_qc(q_ql, {"matemade"}) is False
    assert QC.thay_trang_qc(q_qt, set()) is True


def test_api_qc_quan_tri_vien_thay_moi_ben_va_chua_gan():
    _app, c, _kho, _kho_qc, _tt, _dv = _co_so(_tao_app())
    dang_nhap(c, QL)
    d = c.get(f"/api/qc?{Q}").json()
    assert d["ben"] == "tat_ca" and d["xem_tien"] is True
    assert [b["ma"] for b in d["cac_ben"]] == ["tat_ca", "hapas", "matemade", "chua_gan"]
    assert len(d["tai_khoan"]) == 4 and d["kpi"]["chi"] > 0
    assert c.get(f"/api/qc?{Q}&ben=chua_gan").json()["tai_khoan"][0]["advertiser_id"] == LE
    assert c.get(f"/api/qc?{Q}&ben=khong-co").status_code == 404
    t = c.get(f"/quang-cao?{Q}").text
    assert "Chi tiêu" in t and "ROAS Shop" in t and 'id="qc-du-lieu"' in t
    assert "Số đến hết ngày 18/10/2026" in t
    assert c.get("/api/qc?tu=2025-01-01&den=2026-10-18").status_code == 400


def test_muc_dieu_huong_quang_cao_chi_quan_tri():
    _app, c, _kho, _kho_qc, _tt, _dv = _co_so(_tao_app())
    for ai, thay in ((QL, True), (XEM, False), (HP_QL, False), (MM_XEM, False)):
        dang_nhap(c, ai)
        assert ('href="/quang-cao"' in c.get("/nguon").text) is thay, ai
        assert (c.get("/quang-cao").status_code == 200) is thay, ai


def test_trang_va_api_khong_bao_gio_co_token():
    _app, c, _kho, kho_qc, tt, _dv = _co_so(_tao_app())
    enc = [kho_qc.kn["access_token_enc"], kho_qc.kn["refresh_token_enc"]]
    for ai in (QL, XEM, HP_QL):
        dang_nhap(c, ai)
        for p in ("/quan-tri", "/quang-cao", f"/api/qc?{Q}", "/"):
            t = c.get(p).text
            for bi_mat in (tt.access, tt.refresh, *enc, "cid-gia-1"):
                assert bi_mat not in t, (ai, p)


# ───────────────────────────── thẻ Quản trị ─────────────────────────────
def test_the_ket_noi_chi_quan_tri_vien_thay():
    _app, c, _kho, _kho_qc, _tt, _dv = _co_so(_tao_app())
    dang_nhap(c, QL)
    t = c.get("/quan-tri").text
    assert "Kết nối TikTok Ads" in t and "Đăng nhập lại để gia hạn 30 ngày" in t
    assert "Đồng bộ ngay" in t and "Ngắt kết nối" in t and 'action="/tiktok/token"' in t
    assert 'data-o="tk-' + MM_MKT + '"' in t and "Tài khoản quảng cáo → bên" in t
    assert "25 ngày" in t and "the--tot" in t
    dang_nhap(c, HP_QL)
    t = c.get("/quan-tri").text
    assert c.get("/quan-tri").status_code == 200
    assert "Kết nối TikTok Ads" not in t and "/tiktok/" not in t


def test_quan_tri_gan_ben_va_dong_bo_bam_tay():
    _app, c, _kho, kho_qc, _tt, _dv = _co_so(_tao_app())
    csrf = dang_nhap(c, QL)
    r = c.post("/tiktok/gan-ben", data={"csrf": csrf, "advertiser_id": LE, "don_vi": "matemade",
                                        "dang_dong_bo": "1"})
    assert r.status_code == 303 and kho_qc.tk[LE]["don_vi"] == "matemade"
    assert kho_qc.tk[LE]["gan_tay"] is True and (QL, "gan_ben_tk_qc") in kho_qc.nk
    r = c.post("/tiktok/gan-ben", data={"csrf": csrf, "advertiser_id": LE, "don_vi": "khong-co"})
    assert "Không có bên này" in c.get(r.headers["location"]).text
    tt_goi = len(_tt.goi)
    r = c.post("/tiktok/dong-bo", data={"csrf": csrf})
    assert "sẽ chạy trong ≤ 10 phút" in c.get(r.headers["location"]).text
    # Dashboard CHỈ ghi cờ — không gọi TikTok, không chạy lượt nào trong tiến trình web.
    assert len(_tt.goi) == tt_goi and (QL, "dong_bo_tiktok") in kho_qc.nk
    assert kho_qc.kn["yeu_cau_dong_bo_luc"] == BAY and kho_qc.kn["yeu_cau_boi"] == QL
    t = c.get("/quan-tri").text
    assert 'data-o="tt-yeu-cau"' in t and "sẽ chạy trong ≤ 10 phút" in t
    r = c.post("/tiktok/ngat", data={"csrf": csrf})
    assert "Đã ngắt kết nối" in c.get(r.headers["location"]).text
    assert kho_qc.kn["access_token_enc"] is None


def test_kho_qc_chua_co_bang_trang_van_chay():
    _app, c, _kho, _kho_qc, _tt, _dv = _tao_app(kho_qc=A.KhoQcRong())
    dang_nhap(c, QL)
    t = c.get("/quan-tri").text
    assert c.get("/quan-tri").status_code == 200 and "Kết nối TikTok Ads" in t
    assert c.get("/quang-cao").status_code == 200
    dang_nhap(c, XEM)
    assert 'href="/quang-cao"' not in c.get("/").text


# ───────────────────────────── Mark ─────────────────────────────
def test_mark_quang_cao_theo_ben_va_tien(monkeypatch):
    import hoi_dashboard_tool as HD
    _app, _c, kho, kho_qc, _tt, _dv = _co_so(_tao_app())

    class KhoMarkGia:
        """Như HD.KhoMark: hàm đọc của kho + kho_qc (tên phía tool)."""

        def __getattr__(self, ten):
            if ten in HD._HAM_KHO_QC:
                return getattr(kho_qc, HD._HAM_KHO_QC[ten])
            return getattr(kho, ten)
    assert set(HD._HAM_KHO_QC.values()) <= {"cac_tk", "qc_tong", "qc_top", "qc_moi"}
    bay = datetime.datetime(2026, 10, 19, 9, 0, tzinfo=VN)
    args = {"phan": ["quang_cao"], "tu": "2026-10-12", "den": "2026-10-18"}
    monkeypatch.setattr(HD, "email_cua", lambda oid: XEM)
    ra = HD.tra_loi(args, KhoMarkGia(), open_id="ou_hoi", bay_gio=bay)
    qc = ra["phan"]["quang_cao"]
    # 20/10/2026: Chỉ xem cũng được biết tiền của bên mình — nhưng chỉ bằng chữ, không link trang.
    assert [b["ben"] for b in qc["ben"]] == ["hapas"] and qc["ben"][0]["xem_tien"] is True
    assert qc["ben"][0]["kpi"]["chi"] > 0 and qc["ben"][0]["kpi"]["hien_thi"] > 0
    assert "link" not in qc["ben"][0] and "BẰNG CHỮ" in qc["ghi_chu"] and "du_an" not in ra
    ra = HD.tra_loi({**args, "ben": "matemade"}, KhoMarkGia(), open_id="ou_hoi", bay_gio=bay)
    assert ra["phan"]["quang_cao"]["co"] is False
    monkeypatch.setattr(HD, "email_cua", lambda oid: HP_QL)
    b = HD.tra_loi(args, KhoMarkGia(), open_id="ou_hoi", bay_gio=bay)["phan"]["quang_cao"]["ben"]
    assert b[0]["xem_tien"] is True and b[0]["kpi"]["chi"] > 0
    assert b[0]["top_chien_dich"][0]["chi"] >= b[0]["top_chien_dich"][-1]["chi"]
    monkeypatch.setattr(HD, "email_cua", lambda oid: QL)
    b = HD.tra_loi(args, KhoMarkGia(), open_id="ou_hoi", bay_gio=bay)["phan"]["quang_cao"]["ben"]
    assert [x["ben"] for x in b] == ["hapas", "matemade"] and all(x["xem_tien"] for x in b)
    assert all(x["link"].startswith(HD.DASHBOARD_URL + "/quang-cao?") for x in b)
    # Cùng tool, phần khác + quang_cao: vẫn qua dự án như cũ.
    ra = HD.tra_loi({**args, "phan": ["tong_quan", "quang_cao"]}, KhoMarkGia(),
                    open_id="ou_hoi", bay_gio=bay)
    assert ra["du_an"]["ma"] == "hapas" and ra["phan"]["quang_cao"]["co"] is True


@pytest.mark.parametrize("con,muc", [(8, None), (6.9, 7), (3, 3), (2.5, 3), (0.5, 1), (-1, 0)])
def test_mark_nhac_gia_han_7_3_1(con, muc):
    import nhac_tiktok_ads as NT
    bay = datetime.datetime(2026, 10, 19, 9, 0, tzinfo=VN)
    dong = {"nha_cung_cap": "tiktok_ads", "loai": "mcp_oauth", "trang_thai": "hoat_dong",
            "refresh_het_luc": bay + datetime.timedelta(days=con)}
    x = NT.kiem(bay, lambda: dong)
    assert (x and x["muc"]) == muc
    if x:
        assert "/quan-tri#tiktok" in x["van"] and "Đăng nhập lại để gia hạn 30 ngày" in x["van"]
    assert NT.kiem(bay, lambda: {**dong, "loai": "api_token"}) is None
    assert NT.kiem(bay, lambda: {**dong, "trang_thai": "da_ngat"}) is None


def test_mark_nhac_mot_lan_moi_moc_va_chi_khi_co_noi_nhan(monkeypatch):
    import nhac_tiktok_ads as NT
    monkeypatch.setattr(NT, "_TRANG", {"doc_luc": float("-inf"), "da_gui": set()})
    bay = datetime.datetime(2026, 10, 19, 9, 0, tzinfo=VN)
    dong = {"nha_cung_cap": "tiktok_ads", "loai": "mcp_oauth", "trang_thai": "hoat_dong",
            "refresh_het_luc": bay + datetime.timedelta(days=2)}
    gui = []
    monkeypatch.delenv("MARK_TIKTOK_NHAC", raising=False)
    monkeypatch.delenv("MARK_LICH_QUET_BAO_LOI", raising=False)
    assert NT.nhac(bay, doc=lambda: dong, gui=lambda *a: gui.append(a)) is None and gui == []
    monkeypatch.setenv("MARK_TIKTOK_NHAC", "oc_nhomquantri")
    assert NT.nhac(bay, doc=lambda: dong, gui=lambda *a: gui.append(a))
    NT._TRANG["doc_luc"] = float("-inf")
    assert NT.nhac(bay, doc=lambda: dong, gui=lambda *a: gui.append(a)) is None   # cùng mốc
    assert len(gui) == 1 and gui[0][0] == "oc_nhomquantri"
    NT._TRANG["doc_luc"] = float("-inf")
    dem = bay.replace(hour=23)
    assert NT.nhac(dem, doc=lambda: {**dong, "refresh_het_luc": dem}, gui=gui.append) is None
    # Cột Mark đọc = đúng cột role mark được cấp trong schema.sql.
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    m = re.search(r"GRANT SELECT \(([^)]*)\)\s*ON ket_noi_ngoai TO mark;", sql)
    cap = {x.strip() for x in m.group(1).split(",")}
    assert set(NT.COT_DOC) == cap
    import inspect
    nguon = inspect.getsource(KQ.trang_thai_nhac).replace('"', "").replace("\n", " ")
    doc = re.search(r"SELECT (.*?)\s+FROM ket_noi_ngoai", nguon).group(1)
    assert {re.sub(r"\s+", "", x) for x in doc.split(",")} == cap


def test_quet_tu_dong_goi_nhac_tiktok_va_khong_lam_hong_nhip(monkeypatch):
    import quet_tu_dong as QT
    goi = []
    import nhac_tiktok_ads as NT

    def no(bay_gio):
        goi.append(bay_gio)
        raise RuntimeError("kho hỏng")
    monkeypatch.setattr(NT, "nhac", no)
    QT._nhac_tiktok(BAY)                  # không ném
    assert goi == [BAY]
    src = (GOC / "quet_tu_dong.py").read_text(encoding="utf-8")
    assert re.search(r"_anh_chup_goi\(\)\s+_nhac_tiktok\(bay_gio\)", src)


# ───────────────────────────── schema + BigQuery ─────────────────────────────
def test_schema_quyen_mark_khong_doc_token():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    assert "REVOKE ALL ON ket_noi_ngoai FROM mark;" in sql
    assert sql.index("REVOKE ALL ON ket_noi_ngoai FROM mark;") < sql.index(
        "GRANT SELECT (nha_cung_cap")
    assert not re.search(r"GRANT SELECT ON [^;]*ket_noi_ngoai[^;]*TO mark", sql)
    m = re.search(r"GRANT SELECT \(([^)]*)\)\s*ON ket_noi_ngoai TO mark;", sql)
    assert not any("token" in x or x.strip() in ("client_id", "nguoi_cap")
                   for x in m.group(1).split(","))
    assert ("GRANT SELECT ON tk_quang_cao, qc_tk_ngay, qc_campaign_ngay, qc_ad_ngay, qc_khan_gia "
            "TO mark;") in sql
    assert not re.search(r"GRANT[^;]*(INSERT|UPDATE|DELETE)[^;]*ON[^;]*(qc_|tk_quang_cao|"
                         r"ket_noi_ngoai)[^;]*TO mark", sql)
    for bang in ("ket_noi_ngoai", "tk_quang_cao", "qc_tk_ngay", "qc_campaign_ngay", "qc_ad_ngay",
                 "qc_khan_gia"):
        assert f"CREATE TABLE IF NOT EXISTS {bang} (" in sql
    # Khoá chính của kho_qc.BANG_QC khớp PRIMARY KEY trong schema.
    for bang, (dau, pk) in KQ.BANG_QC.items():
        khoi = re.search(rf"CREATE TABLE IF NOT EXISTS {bang} \((.*?)\n\);", sql, re.DOTALL).group(1)
        assert f"PRIMARY KEY ({', '.join(pk)})" in khoi, bang
        cot = set(re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE))
        assert set(dau) | set(QC.TEN_COT_SO) | {"chi_so", "cap_nhat_luc"} <= cot, bang


def test_bigquery_co_bang_quang_cao_khong_token_khong_email():
    for b in ("tk_quang_cao", "qc_tk_ngay", "qc_campaign_ngay", "qc_ad_ngay", "qc_khan_gia"):
        assert b in DBQ.BANG and b in DBQ.THU_TU
    assert "ket_noi_ngoai" not in DBQ.BANG
    cam = ("token", "client_id", "nguoi_cap", "email", "gan_boi", "redirect_uri")
    for b, v in DBQ.BANG.items():
        assert not [c for c, _ in v["cot"] if any(x in c for x in cam)], b
    sql = (GOC / "deploy" / "lang-nghe" / "bigquery.sql").read_text(encoding="utf-8")
    assert "ket_noi_ngoai`" not in sql
    nhan = ["[Lớp]", "[Mục đích]", "[Grain]", "[Khoá]", "[Nguồn]", "[Phạm vi]", "[Đã xử lý]",
            "[Refresh]", "[Dùng khi]", "[Không dùng khi]", "[Lưu ý]"]
    for b in ("tk_quang_cao", "qc_tk_ngay", "qc_campaign_ngay", "qc_ad_ngay", "qc_khan_gia"):
        m = re.search(rf"CREATE TABLE IF NOT EXISTS `[^`]+\.{b}`\s*\((.*?)\n\)\n(.*?)'''\);", sql,
                      re.DOTALL)
        assert m, b
        dong = m.group(2).split("description='''", 1)[1].split("\n")
        assert [d.split("]", 1)[0] + "]" for d in dong] == nhan, b
        assert "dùng SOCIAL_LISTENING." in dong[9], b
        cot = re.findall(r"^\s{2}(\w+)\s+\w+\s+OPTIONS\(description='(.{10,}?)'\)", m.group(1),
                         re.MULTILINE)
        assert len(cot) == len(DBQ.BANG[b]["cot"]) + 1, b
    # JSONB → chuỗi JSON (không phải repr Python).
    assert DBQ.chuan_gia_tri("STRING", {"cpm": 2454, "x": None}) == '{"cpm": 2454, "x": null}'


def test_nap_lui_bi_ngat_thi_luot_sau_doc_tiep_phan_thieu():
    dv, kho_qc, tt = _dv(tt=GiaTikTok(tk={HAPAS_KOC: "HAPAS - KOC"}))
    _ket_noi_san(dv, tt)
    dv.kham_pha(dv.mcp())
    kho_qc.tk[HAPAS_KOC]["nap_lui_tu"] = datetime.date(2026, 9, 19)   # cửa sổ đầu đã xong
    tt.cong_cu.clear()
    dv.dong_bo()
    kc = [(a["start_date"], a["end_date"]) for t, a in tt.cong_cu if t == "report_integrated_get"
          and a["data_level"] == "AUCTION_ADVERTISER" and a["report_type"] == "BASIC"]
    assert list(dict.fromkeys(kc)) == [("2026-10-12", "2026-10-18"), ("2026-08-20", "2026-09-18"),
                                       ("2026-07-21", "2026-08-19")]
    t = kho_qc.tk[HAPAS_KOC]
    assert t["nap_lui_tu"] == datetime.date(2026, 7, 21) and t["nap_lui_xong_luc"] == BAY


def test_dashboard_khong_bao_gio_chay_dong_bo(monkeypatch):
    """Soát 19/10/2026: tiến trình web không chạy lượt đồng bộ (MemoryMax 512M) — mọi đường chỉ
    ghi cờ; DichVu không còn luồng nền."""
    def cam(*a, **kw):
        raise AssertionError("dashboard không được chạy đồng bộ")
    monkeypatch.setattr(TA.DichVu, "dong_bo", cam)
    monkeypatch.setattr(TA.DichVu, "_dong_bo", cam)
    assert not hasattr(TA.DichVu, "dong_bo_nen")
    _app, c, _kho, kho_qc, tt, _dv = _tao_app()
    tt.token_hop_le.add(TOK := "apitoken0123456789ABCDEFabcdef")
    csrf = dang_nhap(c, QL)
    q, _ = _bat_dau(c, csrf)
    c.get("/tiktok/xong", params={"code": "ma-dung", "state": q["state"]})
    c.post("/tiktok/token", data={"csrf": csrf, "token": TOK})
    c.post("/tiktok/dong-bo", data={"csrf": csrf})
    assert kho_qc.kn["yeu_cau_dong_bo_luc"] == BAY
    src = (GOC / "dashboard" / "app.py").read_text(encoding="utf-8")
    assert ".dong_bo_nen(" not in src and "tt.dong_bo(" not in src


def test_cli_chi_khi_yeu_cau(capsys):
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt)
    assert TA.main(["dong-bo", "--chi-khi-yeu-cau", "--khong-bq"], dich_vu=dv) == 0
    assert tt.goi == [] and capsys.readouterr().out == ""        # không yêu cầu: thoát ngay
    dv.yeu_cau(QL)
    assert TA.main(["dong-bo", "--chi-khi-yeu-cau", "--khong-bq", "--tu", "2026-10-17",
                    "--den", "2026-10-18"], dich_vu=dv) == 0
    assert tt.goi and "so_dong" in capsys.readouterr().out
    assert kho_qc.kn["yeu_cau_dong_bo_luc"] is None               # lượt đã đáp ứng → xoá cờ
    n = len(tt.goi)
    assert TA.main(["dong-bo", "--chi-khi-yeu-cau"], dich_vu=dv) == 0 and len(tt.goi) == n
    # Đang có lượt khác giữ khoá: yêu cầu vẫn chờ, lượt sau chạy.
    dv.yeu_cau(QL)
    with kho_qc.khoa_dong_bo():
        assert TA.main(["dong-bo", "--chi-khi-yeu-cau", "--khong-bq"], dich_vu=dv) == 0
    assert kho_qc.kn["yeu_cau_dong_bo_luc"] == BAY


def test_hai_bo_hen_gio_systemd():
    d = GOC / "deploy" / "lang-nghe"
    ngay = (d / "tiktok-ads-dong-bo.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 06:30:00 Asia/Ho_Chi_Minh" in ngay
    yc = (d / "tiktok-ads-yeu-cau.timer").read_text(encoding="utf-8")
    assert "OnUnitInactiveSec=10min" in yc and "Unit=tiktok-ads-yeu-cau.service" in yc
    sv = (d / "tiktok-ads-yeu-cau.service").read_text(encoding="utf-8")
    assert "dashboard.tiktok_ads dong-bo --chi-khi-yeu-cau" in sv and "User=lang_nghe_web" in sv
    req = (GOC / "dashboard" / "requirements.txt").read_text(encoding="utf-8")
    assert "cryptography>=48,<51" in req


# ───────────────────────────── soát bảo mật 19/10/2026 ─────────────────────────────
def test_lam_moi_chu_dong_khi_con_duoi_6_gio():
    """M1: lượt chạy tới 6 giờ — access token còn < 6 giờ thì làm mới TRƯỚC khi bắt đầu."""
    dv, _kho_qc, tt = _dv()
    _ket_noi_san(dv, tt, het_at=BAY + datetime.timedelta(hours=5))
    assert dv.token().startswith("act.MOI")
    dv2, _kho2, tt2 = _dv()
    _ket_noi_san(dv2, tt2, het_at=BAY + datetime.timedelta(hours=7))
    assert dv2.token() == tt2.access and not any(r.url.path.endswith("/oauth/token")
                                                 for r in tt2.goi)


def test_tiktok_tu_choi_giua_luot_thi_lam_moi_cuong_buc_roi_chay_tiep():
    """M1: token còn hạn trên sổ nhưng TikTok từ chối giữa lượt (thu hồi, đổi phía TikTok…): làm
    mới cưỡng bức MỘT lần, dựng lại phiên MCP, chạy tiếp tới hết."""
    tt = GiaTikTok(tk={HAPAS_KOC: "HAPAS - KOC", MM_MKT: "MATEMADE MKT"})
    dv, kho_qc, _ = _dv(tt=tt)
    _ket_noi_san(dv, tt)
    goc = tt._cong_cu
    lan = {"n": 0}

    def tu_choi_mot_lan(ten, a):
        lan["n"] += 1
        if lan["n"] == 6:                           # giữa lượt: TikTok coi token cũ hết hiệu lực
            tt.token_hop_le.discard(tt.access)
        return goc(ten, a)
    tt._cong_cu = tu_choi_mot_lan
    kq = dv.dong_bo(tu=datetime.date(2026, 10, 17), den=datetime.date(2026, 10, 18))
    assert kq["so_dong"] > 0 and not kq.get("loi"), kq
    assert sum(1 for r in tt.goi if r.url.path.endswith("/oauth/token")) == 1
    assert {r["advertiser_id"] for r in kho_qc.bang["qc_tk_ngay"].values()} == {HAPAS_KOC, MM_MKT}
    assert kho_qc.kn["trang_thai"] == "hoat_dong"


def test_lam_moi_cuong_buc_cung_hong_thi_moi_bao_loi():
    tt = GiaTikTok(tk={HAPAS_KOC: "HAPAS - KOC"})
    dv, kho_qc, _ = _dv(tt=tt)
    _ket_noi_san(dv, tt)
    tt.token_hop_le.clear()                          # mọi token bị từ chối
    tt.lam_moi_loi = True                            # và làm mới cũng hỏng
    kq = dv.dong_bo(tu=datetime.date(2026, 10, 17), den=datetime.date(2026, 10, 18))
    assert "hết hạn" in kq["bo_qua"] and kho_qc.kn["trang_thai"] == "het_han"


def test_ngat_giua_luot_thi_luot_dung_va_khong_ghi_de():
    """L4: quản trị viên ngắt khi lượt đang chạy — lượt dừng ở tài khoản kế, không ghi lại token,
    không đặt lại "hoat_dong"."""
    tt = GiaTikTok(tk={HAPAS_KOC: "HAPAS - KOC", MM_MKT: "MATEMADE MKT", MM_2: "mate made 2"})
    dv, kho_qc, _ = _dv(tt=tt)
    _ket_noi_san(dv, tt)
    goc = kho_qc.ghi_tk_ngay

    def ngat_sau_tk_dau(rows):
        n = goc(rows)
        if kho_qc.kn.get("access_token_enc"):
            kho_qc.ngat(QL)
        return n
    kho_qc.ghi_tk_ngay = ngat_sau_tk_dau
    kq = dv.dong_bo(tu=datetime.date(2026, 10, 17), den=datetime.date(2026, 10, 18))
    assert "ngắt" in kq["bo_qua"]
    k = kho_qc.kn
    assert k["access_token_enc"] is None and k["trang_thai"] == "da_ngat"
    assert len({r["advertiser_id"] for r in kho_qc.bang["qc_tk_ngay"].values()}) == 1


def test_lam_moi_khong_ghi_de_lan_dang_nhap_lai():
    """L4: đăng nhập lại (token + cap_luc mới) trong lúc lượt cũ đang làm mới: UPDATE có điều kiện
    không khớp → không ghi đè token mới, lượt dừng."""
    dv, kho_qc, tt = _dv()
    _ket_noi_san(dv, tt, het_at=BAY)
    goc = TA.lam_moi

    def dang_nhap_lai_xen_giua(*a, **kw):
        kq = goc(*a, **kw)
        kho_qc.kn.update(access_token_enc=TA.ma_hoa("act.LANMOI0123456789", KHOA_TT, "access"),
                         cap_luc=BAY + datetime.timedelta(minutes=1))
        return kq
    import unittest.mock
    with unittest.mock.patch.object(TA, "lam_moi", dang_nhap_lai_xen_giua),             pytest.raises(TA.ChuaKetNoi):
        dv.token()
    assert TA.giai_ma(kho_qc.kn["access_token_enc"], KHOA_TT, "access") == "act.LANMOI0123456789"


def test_sql_cap_nhat_token_co_dieu_kien(monkeypatch):
    class Cur:
        rowcount = 0
    g = []

    class C:
        def execute(self, sql, ts=None):
            g.append((sql, ts))
            return Cur()

    @contextlib.contextmanager
    def kn(trung="x"):
        yield C()
    monkeypatch.setattr(KQ, "ket_noi", kn)
    assert KQ.cap_nhat_token("enc", BAY, None, BAY, neu=("cu", BAY)) is False
    assert "access_token_enc IS NOT DISTINCT FROM %s AND cap_luc IS NOT DISTINCT FROM %s" in g[0][0]
    assert g[0][1][-2:] == ("cu", BAY)
    KQ.ghi_trang_thai("hoat_dong", con_token=True)
    assert g[-1][0].endswith("AND access_token_enc IS NOT NULL")


@pytest.mark.parametrize("gia_tri", ["abc", None, -5, "1e999", {"x": 1}])
def test_callback_expires_in_la_khong_500(gia_tri):
    """L9: TikTok trả expires_in / refresh_token_expires_in lạ → dùng mặc định, không 500."""
    _app, c, _kho, kho_qc, tt, _dv = _tao_app()
    goc = tt.xu_ly

    def la(req):
        r = goc(req)
        if req.url.path.endswith("/oauth/token") and r.status_code == 200:
            d = json.loads(r.content)
            d.update(expires_in=gia_tri, refresh_token_expires_in=gia_tri)
            return httpx.Response(200, json=d)
        return r
    tt.xu_ly = la
    csrf = dang_nhap(c, QL)
    q, _ = _bat_dau(c, csrf)
    r = c.get("/tiktok/xong", params={"code": "ma-dung", "state": q["state"]})
    assert r.status_code == 303
    k = kho_qc.kn
    assert k["access_het_luc"] - BAY == datetime.timedelta(seconds=TA.AT_MAC_DINH)
    assert k["refresh_het_luc"] - BAY == datetime.timedelta(seconds=TA.RT_MAC_DINH)


def test_gon_loi_xoa_dung_token_da_biet():
    """L10: token ngắn / lạ dạng (regex không bắt) vẫn bị xoá vì biết đúng giá trị."""
    tok = "ngan-tok1"                                  # < 24 ký tự: regex không bắt
    assert TA.gon_loi(f"lỗi {tok} x", bi_mat=[tok]) == "lỗi <…> x"
    TA.nho_bi_mat("act.qwerty-01")
    assert "act.qwerty-01" not in TA.gon_loi("HTTP 400 act.qwerty-01")
    assert "act.qwerty-01" not in str(TA.LoiTikTok("đổi mã: act.qwerty-01"))


def test_ngat_token_api_nhac_thu_hoi_o_cong_developer():
    """L6: token API không hết hạn — ngắt chỉ xoá bản trên máy chủ, phải nhắc thu hồi tận gốc."""
    _app, c, _kho, kho_qc, tt, dv = _tao_app()
    tt.token_hop_le.add(TOK := "apitoken0123456789ABCDEFabcdef")
    dv.luu_api_token(QL, TOK)
    csrf = dang_nhap(c, QL)
    t = c.get(c.post("/tiktok/ngat", data={"csrf": csrf}).headers["location"]).text
    assert "KHÔNG tự hết hạn" in t and "TikTok for Business Developer" in t
    assert tt.thu_hoi == [] and kho_qc.kn["access_token_enc"] is None


def test_api_qc_ban_thi_503_va_khoang_qua_dai_400():
    """M2: chung semaphore với /api/chi-so; khoảng > 400 ngày → 400."""
    app, c, _kho, _kq, _tt, _dv = _co_so(_tao_app())
    dang_nhap(c, QL)
    for _ in range(A.TINH_SONG_SONG):
        assert app.state.ban.acquire(blocking=False)
    try:
        assert c.get(f"/api/qc?{Q}").status_code == 503
        assert c.get(f"/quang-cao?{Q}").status_code == 503
    finally:
        for _ in range(A.TINH_SONG_SONG):
            app.state.ban.release()
    assert c.get(f"/api/qc?{Q}").status_code == 200
    assert c.get("/api/qc?tu=2025-01-01&den=2026-10-18").status_code == 400
    assert c.get("/api/qc?tu=2026-10-18&den=2026-10-01").status_code == 400
    assert app.state.ban.acquire(blocking=False)       # đã trả lại sau lỗi 400
    app.state.ban.release()


def test_sql_top_limit_truoc_roi_moi_doc_ten():
    for cap in ("campaign", "ad"):
        tong, moi = KQ.sql_top(cap, "chi")
        assert "array_agg" not in tong + moi
        assert tong.rstrip().endswith("LIMIT %s") and "GROUP BY" in tong
        assert "DISTINCT ON" in moi and "= ANY(%s)" in moi and "LIMIT" not in moi
    calls = []

    class C:
        def execute(self, sql, ts=None):
            calls.append((sql, ts))
            self._r = ([{"campaign_id": "c1", "advertiser_id": "1", "chi": 5.0}]
                       if "GROUP BY" in sql else [{"campaign_id": "c1", "ten": "Tên mới",
                                                    "muc_tieu": "REACH"}])
            return self

        def fetchall(self):
            return self._r

    @contextlib.contextmanager
    def kn(trung="x"):
        yield C()
    import unittest.mock
    with unittest.mock.patch.object(KQ, "ket_noi", kn):
        r = KQ.qc_top("campaign", ["1"], datetime.date(2026, 1, 1), datetime.date(2026, 10, 1),
                      "chi", 999)
    assert r == [{"campaign_id": "c1", "advertiser_id": "1", "chi": 5.0, "ten": "Tên mới",
                  "muc_tieu": "REACH"}]
    assert calls[0][1][-1] == KQ.TOP_TOI_DA and calls[1][1][0] == ["c1"]


def test_bq_tien_quang_cao_tat_mac_dinh(monkeypatch):
    """MEDIUM 3 (chờ chủ dự án): mặc định KHÔNG đẩy số tiền quảng cáo lên BigQuery."""
    dong = {"advertiser_id": "1", "ngay": datetime.date(2026, 10, 1), "chi": 100.5,
            "hien_thi": 9, "gia_tri_mua_shop": 7, "cap_nhat_luc": BAY,
            "chi_so": {"spend": 100.5, "cpm": 3, "cost_per_result": 1, "impressions": 9,
                       "complete_payment_roas": 2, "likes": 1}}
    monkeypatch.delenv("BQ_QC_XUAT_TIEN", raising=False)
    r = DBQ.dong_bq("qc_tk_ngay", [dong])[0]
    assert r["chi"] is None and r["gia_tri_mua_shop"] is None and r["hien_thi"] == 9
    assert json.loads(r["chi_so"]) == {"impressions": 9, "likes": 1}
    assert dong["chi"] == 100.5                                    # không sửa bản gốc
    monkeypatch.setenv("BQ_QC_XUAT_TIEN", "1")
    r = DBQ.dong_bq("qc_tk_ngay", [dong])[0]
    assert r["chi"] == "100.5" and json.loads(r["chi_so"])["cpm"] == 3
    assert DBQ.dong_bq("tk_quang_cao", [{"advertiser_id": "1", "ten": "x"}])[0]["ten"] == "x"
