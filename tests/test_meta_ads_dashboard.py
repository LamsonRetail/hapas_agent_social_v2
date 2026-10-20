"""Meta Ads trên dashboard (20/10/2026, chủ dự án chốt): client Graph CHỈ GET, nhập token chỉ đọc,
đồng bộ vào chung bảng quảng cáo với TikTok, lọc nền tảng trên /api/qc, Mark hỏi đáp cả hai nền tảng +
tra một đối tượng, đồng bộ bấm tay cho mọi người có quyền, BigQuery. (Tool Mark cũ `meta_ads_tool.py`
có bộ thử riêng `test_meta_ads.py`.)

Không mạng: máy chủ Graph GIẢ bằng httpx.MockTransport; kho quảng cáo GIẢ dùng chung với TikTok
(`test_tiktok_ads.GiaKhoQC`, đa nhà cung cấp). Dạng số mẫu theo Insights thật (chuỗi số, action list,
Meta bỏ action bằng 0)."""
from __future__ import annotations

import datetime
import io
import json
import re
import subprocess
import types
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from test_dashboard_app import HP_QL, MM_XEM, QL, XEM, dang_nhap
from test_tiktok_ads import BAY, KHOA_TT, GiaKhoQC, _co_so, _dv, _ket_noi_san, _tao_app

from dashboard import dong_bo_bq as DBQ
from dashboard import kho_qc as KQ
from dashboard import meta_ads as MA
from dashboard import quang_cao as QC
from dashboard import tiktok_ads as TA

GOC = Path(__file__).resolve().parents[1]
VN = datetime.timezone(datetime.timedelta(hours=7))
TOKEN = "EAAGmeta0123456789abcdefXYZtoken"
NUOC_HOA, MATE, THAI, MADE, LA = "act_1001", "act_1002", "act_1003", "act_1004", "act_1005"
TK_META = {NUOC_HOA: "HTC - [NƯỚC HOA] HAPAS 1 - FB ADS", MATE: "MATEMADE-6", THAI: "THAI 1",
           MADE: "MADEMATE - MKT", LA: "HAPAS 2: FACEBOOK BRANDING"}
#: Chiến dịch mẫu: act → [(campaign_id, tên)].
CAMPAIGN = {NUOC_HOA: [("120201", "Nước Hoa Tháng 10 - Chuyển đổi"), ("120202", "Trang sức Thu")],
            MATE: [("120301", "Mate made sale 10.10")], MADE: [("120401", "Brand awareness")],
            THAI: [("120501", "Thai test")], LA: []}


# ───────────────────────────── máy chủ Graph giả ─────────────────────────────
class GiaMeta:
    def __init__(self, *, quyen=("ads_read", "read_insights", "public_profile"), tk=None,
                 campaign=None, gioi_han=0, het_han=False):
        self.goi: list[httpx.Request] = []
        self.quyen = list(quyen)
        self.tk = dict(TK_META if tk is None else tk)
        self.campaign = dict(CAMPAIGN if campaign is None else campaign)
        self.gioi_han = gioi_han             # số lượt đầu trả mã 17 (giới hạn tần suất)
        self.token_hop_le = {TOKEN}
        self.het_han = het_han
        self.trang_tk = 2                    # me/adaccounts: 2 tài khoản mỗi trang (thử paging)
        self.next_la: str | None = None      # đặt URL lạ cho paging.next (thử chốt)

    def transport(self):
        return httpx.MockTransport(self.xu_ly)

    @staticmethod
    def _ngay(a, b):
        d = datetime.date.fromisoformat(a)
        while d <= datetime.date.fromisoformat(b):
            yield d
            d += datetime.timedelta(days=1)

    @staticmethod
    def _so(seed: int, hien: int) -> dict:
        return {"spend": str(hien * 2), "impressions": str(hien), "reach": str(hien // 2),
                "frequency": "2.0", "clicks": str(hien // 10), "inline_link_clicks": str(hien // 20),
                "ctr": "10.0", "cpc": "20", "cpm": "2000", "cpp": "4000",
                "actions": [{"action_type": "purchase", "value": "2"},
                            {"action_type": "omni_purchase", "value": "2"},
                            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "2"},
                            {"action_type": "video_view", "value": str(seed % 50 + 10)},
                            {"action_type": "post_reaction", "value": "7"},
                            {"action_type": "comment", "value": "3"},
                            {"action_type": "like", "value": "1"}],
                "action_values": [{"action_type": "purchase", "value": "300000"},
                                  {"action_type": "omni_purchase", "value": "300000"}],
                "purchase_roas": [{"action_type": "omni_purchase", "value": "1.5"}],
                "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "5"}],
                "video_p100_watched_actions": [{"action_type": "video_view", "value": "4"}]}

    def _insights(self, act: str, q: dict) -> list[dict]:
        tr = json.loads(q["time_range"])
        cap, bd = q["level"], q.get("breakdowns")
        if act == LA:                         # tài khoản không chạy: Meta không trả dòng nào
            return []
        if bd:
            gt = {"age": [{"age": "18-24"}, {"age": "65+"}], "gender": [{"gender": "female"}],
                  "region": [{"region": "Ho Chi Minh City"}],
                  "publisher_platform": [{"publisher_platform": "instagram"}],
                  "publisher_platform,platform_position": [
                      {"publisher_platform": "instagram", "platform_position": "reels"}]}[bd]
            return [{**x, "date_start": tr["since"], "date_stop": tr["until"],
                     **{k: v for k, v in self._so(1, 1000).items() if k != "actions"}} for x in gt]
        rows = []
        for d in self._ngay(tr["since"], tr["until"]):
            if cap == "account":
                rows.append({"account_id": act[4:], "date_start": d.isoformat(),
                             "date_stop": d.isoformat(), **self._so(d.day, 1000 + d.day)})
            else:
                for cid, ten in self.campaign.get(act, []):
                    base = {"campaign_id": cid, "campaign_name": ten, "objective": "OUTCOME_SALES",
                            "date_start": d.isoformat(), "date_stop": d.isoformat(),
                            **self._so(d.day, 100 + d.day)}
                    if cap == "ad":
                        base.update(adset_id=cid + "9", adset_name="Nhóm " + ten,
                                    ad_id=cid + "77", ad_name="QC " + ten)
                    rows.append(base)
        return rows

    def _trang(self, q: dict, ds: list, n: int, duong: str) -> dict:
        sau = int(q.get("after") or 0)
        d = {"data": ds[sau:sau + n]}
        if sau + n < len(ds):
            # Như Meta thật: trang sau mang lại mọi tham số + access_token + after.
            ts = {k: v for k, v in q.items() if k != "after"}
            nxt = (self.next_la or f"https://graph.facebook.com/v26.0/{duong}") + "?" + urlencode(
                {**ts, "access_token": TOKEN, "after": sau + n})
            d["paging"] = {"next": nxt}
        return d

    def xu_ly(self, req: httpx.Request) -> httpx.Response:
        self.goi.append(req)
        assert req.method == "GET"
        if self.gioi_han:
            self.gioi_han -= 1
            return httpx.Response(400, json={"error": {"code": 17, "message": "User request limit"}})
        tok = req.headers.get("authorization", "").removeprefix("Bearer ")
        if tok not in self.token_hop_le:
            loi = {"code": 190, "message": "Invalid OAuth access token"}
            if self.het_han:
                loi["error_subcode"] = 463
            return httpx.Response(400, json={"error": loi})
        duong = req.url.path.split("/", 2)[2]
        q = {k: v[0] for k, v in parse_qs(urlsplit(str(req.url)).query).items()}
        if duong == "me":
            return httpx.Response(200, json={"id": "999", "name": "mark_ads_reader"})
        if duong in ("me/permissions", "999/permissions"):
            return httpx.Response(200, json={"data": [{"permission": p, "status": "granted"}
                                                      for p in self.quyen]})
        if duong in ("me/adaccounts", "999/adaccounts"):
            ds = [{"id": k, "account_id": k[4:], "name": v, "currency": "VND",
                   "timezone_name": "Asia/Ho_Chi_Minh", "account_status": 1}
                  for k, v in self.tk.items()]
            return httpx.Response(200, json=self._trang(q, ds, self.trang_tk, "999/adaccounts"))
        m = re.fullmatch(r"(act_[0-9]+)/insights", duong)
        if m:
            return httpx.Response(200, json=self._trang(q, self._insights(m.group(1), q), 40,
                                                        duong))
        return httpx.Response(400, json={"error": {"code": 100, "message": "Unknown path"}})


def _mdv(kho_qc=None, gm=None, bay=BAY):
    gm = gm or GiaMeta()
    kho_qc = kho_qc if kho_qc is not None else GiaKhoQC()
    dv = MA.DichVu(kho_qc, http=MA.Http(transport=gm.transport(), ngu=lambda s: None),
                   khoa=KHOA_TT, ngu=lambda s: None, bay_gio=lambda: bay, log=lambda *a: None)
    return dv, kho_qc, gm


def _nhap(dv, duyet=(NUOC_HOA, MATE, THAI, MADE, LA)):
    return dv.luu_token(QL, TOKEN, list(duyet) if duyet is not None else None)


def _gom_tk(dv):
    """Kho như đã nhập token + duyệt, chưa đồng bộ (cờ yêu cầu đã xoá)."""
    _nhap(dv)
    dv.kho._kn("meta_ads")["yeu_cau_dong_bo_luc"] = None


def _khoang(r: httpx.Request):
    q = parse_qs(urlsplit(str(r.url)).query)
    if "time_range" not in q:
        return None
    t = json.loads(q["time_range"][0])
    return t["since"], t["until"]


# ───────────────────────────── chốt chỉ đọc ─────────────────────────────
@pytest.mark.parametrize("pt,url", [
    ("POST", "https://graph.facebook.com/v26.0/act_1/insights"),
    ("DELETE", "https://graph.facebook.com/v26.0/act_1"),
    ("PUT", "https://graph.facebook.com/v26.0/me"),
    ("GET", "https://graph.facebook.com/v26.0/act_1/adsets"),
    ("GET", "https://graph.facebook.com/v26.0/act_1/adcreatives"),
    ("GET", "https://graph.facebook.com/v26.0/me/businesses"),
    ("GET", "https://graph.facebook.com/v26.0/act_1/insights?method=post"),
    ("GET", "https://graph.facebook.com/v26.0/act_1?_method=DELETE"),
    ("GET", "https://graph.facebook.com/v26.0/?batch=%5B%5D"),
    ("GET", "https://evil.example/v26.0/me"),
    ("GET", "http://graph.facebook.com/v26.0/me"),
    ("GET", "https://graph.facebook.com:8443/v26.0/me"),
    ("GET", "https://user@graph.facebook.com/v26.0/me"),
    ("GET", "https://graph.facebook.com/me"),
    ("GET", "https://graph.facebook.com/v26.0/123/adaccounts"),
])
def test_chi_get_danh_sach_duong_chan_truoc_khi_gui(pt, url):
    gm = GiaMeta()
    http = MA.Http(transport=gm.transport(), ngu=lambda s: None)
    with pytest.raises(MA.LoiChan):
        http.yeu_cau(pt, url, headers={"Authorization": "Bearer " + TOKEN})
    assert gm.goi == []                                  # không một byte nào ra "mạng"
    assert not hasattr(MA.Http, "post") and not hasattr(MA.Graph, "post")


def test_duong_doc_di_qua_va_bo_access_token_trong_url():
    sach, duong = MA.kiem_url("GET", "https://graph.facebook.com/v26.0/act_12/insights"
                                     f"?access_token={TOKEN}&level=ad&after=x")
    assert duong == "act_12/insights" and TOKEN not in sach and "level=ad" in sach
    for d in ("me", "me/adaccounts", "me/permissions", "act_9", "act_9/campaigns", "act_9/ads"):
        assert MA.kiem_url("GET", f"https://graph.facebook.com/v26.0/{d}")[1] == d
    # Trang sau: chỉ cùng đường; me/... được đổi thành <id số>/...
    assert MA.kiem_url("GET", "https://graph.facebook.com/v26.0/999/adaccounts?after=2",
                       tiep="me/adaccounts")[1] == "999/adaccounts"
    with pytest.raises(MA.LoiChan):
        MA.kiem_url("GET", "https://graph.facebook.com/v26.0/act_2/insights", tiep="act_1/insights")


def test_phan_trang_chi_trong_graph_facebook_com():
    gm = GiaMeta()
    gm.next_la = "https://graph.facebook.com.evil.example/v26.0/999/adaccounts"
    g = MA.Graph(TOKEN, MA.Http(transport=gm.transport(), ngu=lambda s: None), ngu=lambda s: None)
    with pytest.raises(MA.LoiChan):
        g.trang("me/adaccounts", {"limit": 2})
    assert len(gm.goi) == 1                               # trang lạ không được gửi
    gm2 = GiaMeta()
    g2 = MA.Graph(TOKEN, MA.Http(transport=gm2.transport(), ngu=lambda s: None),
                  ngu=lambda s: None)
    ds = g2.trang("me/adaccounts", {"limit": 2})
    assert len(ds) == 5 and len(gm2.goi) == 3
    for r in gm2.goi:
        assert "access_token" not in str(r.url) and r.headers["authorization"] == "Bearer " + TOKEN


def test_gioi_han_tan_suat_nghi_roi_thu_lai():
    gm = GiaMeta(gioi_han=2)
    ngu = []
    g = MA.Graph(TOKEN, MA.Http(transport=gm.transport(), ngu=lambda s: None), ngu=ngu.append)
    assert g.goi("me")["name"] == "mark_ads_reader"
    assert ngu[:2] == [MA.NGHI_GIOI_HAN, MA.NGHI_GIOI_HAN * 2] and len(gm.goi) == 3
    gm2 = GiaMeta(gioi_han=99)
    g2 = MA.Graph(TOKEN, MA.Http(transport=gm2.transport(), ngu=lambda s: None),
                  ngu=lambda s: None)
    with pytest.raises(MA.LoiMeta, match="giới hạn"):
        g2.goi("me")
    assert len(gm2.goi) == MA.THU_LAI_GIOI_HAN + 1


def test_tai_header_cao_thi_nghi():
    hd = {"x-business-use-case-usage": json.dumps({"1001": [{"call_count": 95, "total_cputime": 3,
                                                             "estimated_time_to_regain_access": 2}]})}
    assert MA._tai_cao(hd) == 120
    assert MA._tai_cao({"x-ad-account-usage": json.dumps({"acc_id_util_pct": 10})}) == 0


# ───────────────────────────── token chỉ đọc ─────────────────────────────
@pytest.mark.parametrize("quyen", [("ads_read", "read_insights", "ads_management"),
                                   ("ads_read", "read_insights", "business_management"),
                                   ("ads_read", "read_insights", "pages_manage_ads"),
                                   ("ads_read",)])
def test_token_khong_chi_doc_bi_tu_choi_khong_luu(quyen):
    dv, kho_qc, _ = _mdv(gm=GiaMeta(quyen=quyen))
    with pytest.raises(MA.LoiTokenKhongChiDoc):
        _nhap(dv)
    assert not (kho_qc.doc_ket_noi("meta_ads") or {}).get("access_token_enc")
    assert not kho_qc.tk


def test_nhap_token_ma_hoa_duyet_va_gan_ben():
    dv, kho_qc, _ = _mdv()
    kq = _nhap(dv, duyet=(NUOC_HOA, MATE, THAI, MADE))
    assert kq["chu"] == "mark_ads_reader"
    assert kq["quyen"] == ["ads_read", "public_profile", "read_insights"]
    assert kq["so_tk_thay"] == 5 and kq["so_tk_duyet"] == 4
    kn = kho_qc.doc_ket_noi("meta_ads")
    assert kn["loai"] == "api_token" and TOKEN not in json.dumps(kn, default=str)
    assert TA.giai_ma(kn["access_token_enc"], KHOA_TT, "access", "meta_ads") == TOKEN
    with pytest.raises(TA.LoiMaHoa):                      # AAD riêng: không tráo sang TikTok
        TA.giai_ma(kn["access_token_enc"], KHOA_TT, "access")
    assert kn["yeu_cau_dong_bo_luc"] and kn["chu_token"] == "mark_ads_reader"
    tk = kho_qc.tk
    assert {k: t["nen_tang"] for k, t in tk.items()} == {k: "meta" for k in TK_META}
    assert tk[NUOC_HOA]["don_vi"] == "hapas" and tk[MATE]["don_vi"] == "matemade"
    assert tk[MADE]["don_vi"] == "matemade" and tk[THAI]["don_vi"] is None
    assert tk[LA]["duyet"] is False and tk[NUOC_HOA]["duyet"] is True
    assert dv.the()["so_tk_duyet"] == 4 and dv.the()["so_tk_cho_duyet"] == 1


@pytest.mark.parametrize("ten,ben", [("MATEMADE-6", "matemade"), ("MADEMATE - MKT", "matemade"),
                                     ("MATEMADE -  ADS", "matemade"), ("Mate Made 2", "matemade"),
                                     ("THAI 1", None), ("Thái 2", None), ("thai", None),
                                     ("THAILAND STORE", "hapas"), ("CPAS SHOPEE", "hapas"),
                                     ("HTC - HAPAS 9 - FB ADS", "hapas")])
def test_gan_ben_tu_dong_meta(ten, ben):
    assert QC.ben_tu_dong(ten) == ben


def test_thay_lai_khong_de_ban_quan_tri_va_tiktok_khong_mat_quyen():
    dv, kho_qc, _ = _mdv()
    tdv, _, tt = _dv(kho_qc=kho_qc)
    _ket_noi_san(tdv, tt)
    tdv.kham_pha(tdv.mcp())
    _nhap(dv)
    kho_qc.gan_ben(QL, THAI, "hapas", True)
    kho_qc.gan_ben(QL, MATE, None, True, False)            # bỏ duyệt
    dv.kham_pha(dv.graph())
    assert kho_qc.tk[THAI]["don_vi"] == "hapas" and kho_qc.tk[MATE]["duyet"] is False
    # Meta thấy lại không làm tài khoản TikTok "mất quyền" và ngược lại.
    assert all(t["con_quyen"] for t in kho_qc.tk.values())
    tdv.kham_pha(tdv.mcp())
    assert all(t["con_quyen"] for t in kho_qc.tk.values())


# ───────────────────────────── đổi số ─────────────────────────────
def test_bi_danh_mua_khong_cong_trung():
    r = {"spend": "1000", "impressions": "500",
         "actions": [{"action_type": "purchase", "value": "3"},
                     {"action_type": "omni_purchase", "value": "3"},
                     {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "3"}],
         "action_values": [{"action_type": "omni_purchase", "value": "90000"},
                           {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "1"}]}
    d = MA.dong_so(r)
    assert d["chuyen_doi"] == 3 and d["gia_tri_mua_shop"] == 90000       # không phải 9 / 90001
    r2 = {**r, "actions": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "4"},
                           {"action_type": "omni_purchase", "value": "5"}]}
    assert MA.dong_so(r2)["chuyen_doi"] == 5                              # omni trước pixel
    # Meta bỏ action bằng 0: dòng có phân phối → 0; dòng khán giả (chia nhỏ) → NULL cho chuyển đổi.
    d0 = MA.dong_so({"spend": "10", "impressions": "5"})
    assert d0["chuyen_doi"] == 0 and d0["view_video"] == 0 and d0["gia_tri_mua_shop"] == 0
    dk = MA.dong_so({"spend": "10", "impressions": "5"}, chia_nho=True)
    assert dk["chuyen_doi"] is None and dk["gia_tri_mua_shop"] is None and dk["thich"] == 0
    assert MA.dong_so({})["chuyen_doi"] is None
    cs = MA.chi_so_json(r)
    assert cs["actions__purchase"] == 3 and cs["action_values__omni_purchase"] == 90000
    assert QC.la_tien("action_values__omni_purchase") and QC.la_tien("purchase_roas__omni_purchase")
    assert not QC.la_tien("actions__purchase") and QC.la_tien("cpp")


def test_chi_so_cong_duoc():
    for k in ("reach", "frequency", "ctr", "cpc", "cpm", "cpp", "purchase_roas__omni_purchase",
              "video_avg_time_watched_actions__video_view", "cost_per_result", "engagement_rate",
              "average_video_play"):
        assert not QC.cong_duoc(k), k
    for k in ("spend", "impressions", "clicks", "actions__purchase", "action_values__purchase",
              "video_p25_watched_actions__video_view", "likes", "follows"):
        assert QC.cong_duoc(k), k


# ───────────────────────────── đồng bộ ─────────────────────────────
def test_dong_bo_nap_lui_90_ngay_roi_7_ngay_chi_tai_khoan_duyet():
    dv, kho_qc, gm = _mdv()
    _nhap(dv, duyet=(NUOC_HOA, MATE, THAI))
    kq = dv.dong_bo()
    assert kq["den_ngay"] == datetime.date(2026, 10, 18) and not kq["loi"], kq
    doc = {urlsplit(str(r.url)).path.split("/")[2] for r in gm.goi if "/insights" in str(r.url)}
    assert doc == {NUOC_HOA, MATE, THAI}                  # MADE, LA chưa duyệt: không đọc
    kc = [_khoang(r) for r in gm.goi if NUOC_HOA in str(r.url) and "level=account" in str(r.url)
          and "breakdowns" not in str(r.url) and _khoang(r)]
    assert list(dict.fromkeys(kc)) == [("2026-09-19", "2026-10-18"), ("2026-08-20", "2026-09-18"),
                                       ("2026-07-21", "2026-08-19")]               # mới trước
    ngay = sorted({r["ngay"] for r in kho_qc.bang["qc_tk_ngay"].values()})
    assert ngay[0] == datetime.date(2026, 7, 21) and ngay[-1] == datetime.date(2026, 10, 18)
    r = kho_qc.bang["qc_tk_ngay"][(NUOC_HOA, datetime.date(2026, 10, 18))]
    assert r["chi"] == 2036 and r["hien_thi"] == 1018 and r["chuyen_doi"] == 2
    assert r["engaged_view"] == 5 and r["thich"] == 7 and r["follow"] == 1
    assert r["gia_tri_mua_shop"] == 300000 and r["chi_so"]["actions__omni_purchase"] == 2
    camp = kho_qc.bang["qc_campaign_ngay"][("120201", datetime.date(2026, 10, 18))]
    assert camp["advertiser_id"] == NUOC_HOA and camp["muc_tieu"] == "OUTCOME_SALES"
    assert kho_qc.bang["qc_ad_ngay"][("12020177", datetime.date(2026, 10, 18))]["ten_nhom"]
    # Campaign 60 dòng / cửa sổ > trang 40 dòng: trang sau mang đủ tham số, đủ 30 ngày.
    assert len([k for k in kho_qc.bang["qc_campaign_ngay"] if k[0] == "120201"]) == 90
    kg = {(r["chieu"], r["gia_tri"]) for r in kho_qc.bang["qc_khan_gia"].values()
          if r["advertiser_id"] == NUOC_HOA}
    assert ("age", "AGE_18_24") in kg and ("age", "65+") in kg and ("gender", "FEMALE") in kg
    assert ("platform_position", "instagram/reels") in kg and ("region", "Ho Chi Minh City") in kg
    dem = {b: len(v) for b, v in kho_qc.bang.items()}
    gm.goi.clear()
    dv.dong_bo()                                          # lần 2: 7 ngày, không nhân đôi
    kc2 = {_khoang(r)[0] for r in gm.goi if "/insights" in str(r.url) and _khoang(r)}
    assert kc2 == {"2026-10-12"} and {b: len(v) for b, v in kho_qc.bang.items()} == dem
    assert all(r.method == "GET" for r in gm.goi)


def test_qua_nhieu_du_lieu_thi_chia_doi_cua_so():
    dv, kho_qc, gm = _mdv()
    _gom_tk(dv)
    goc = gm._insights
    lan = {"n": 0}

    class _QuaNhieu(Exception):
        pass

    def to(act, q):
        tr = json.loads(q["time_range"])
        if q["level"] == "ad" and act == NUOC_HOA and tr["since"] != tr["until"] and lan["n"] < 3:
            lan["n"] += 1
            raise _QuaNhieu()
        return goc(act, q)

    def xu_ly(req):
        try:
            return gm.xu_ly(req)
        except _QuaNhieu:
            return httpx.Response(500, json={"error": {"code": 1, "message": "reduce data"}})
    gm._insights = to
    dv.http = MA.Http(transport=httpx.MockTransport(xu_ly), ngu=lambda s: None)
    kq = dv.dong_bo(tu=datetime.date(2026, 10, 15), den=datetime.date(2026, 10, 18))
    assert not kq.get("loi"), kq
    assert lan["n"] == 3
    assert len([k for k in kho_qc.bang["qc_ad_ngay"] if k[0] == "12020177"]) == 4


def test_token_bi_tu_choi_giua_luot_thi_trang_thai():
    dv, kho_qc, gm = _mdv()
    _gom_tk(dv)
    gm.token_hop_le.clear()
    kq = dv.dong_bo()
    assert "loi" in kq and kho_qc.doc_ket_noi("meta_ads")["trang_thai"] == "loi"
    gm2 = GiaMeta(het_han=True)
    dv2, kho2, _ = _mdv(gm=gm2)
    _gom_tk(dv2)
    gm2.token_hop_le.clear()
    dv2.dong_bo()
    kn = kho2.doc_ket_noi("meta_ads")
    assert kn["trang_thai"] == "het_han" and TOKEN not in str(kn.get("loi_cuoi"))


def test_khoa_rieng_meta_tiktok_chay_song_song():
    kho_qc = GiaKhoQC()
    dv, _, _ = _mdv(kho_qc=kho_qc)
    _gom_tk(dv)
    with kho_qc.khoa_dong_bo():                           # TikTok đang chạy
        assert "so_dong" in dv.dong_bo(tu=datetime.date(2026, 10, 18),
                                       den=datetime.date(2026, 10, 18))
    with kho_qc.khoa_dong_bo(MA.KHOA_DONG_BO):
        assert dv.dong_bo() == {"bo_qua": "đang có lượt đồng bộ Meta khác"}


def test_tiktok_bo_qua_tai_khoan_meta():
    kho_qc = GiaKhoQC()
    dv, _, _ = _mdv(kho_qc=kho_qc)
    _gom_tk(dv)
    tdv, _, tt = _dv(kho_qc=kho_qc)
    _ket_noi_san(tdv, tt)
    tdv.dong_bo(tu=datetime.date(2026, 10, 18), den=datetime.date(2026, 10, 18))
    adv = {a.get("advertiser_id") for t, a in tt.cong_cu if t == "report_integrated_get"}
    assert adv and not any(str(x).startswith("act_") for x in adv)


# ───────────────────────────── dòng lệnh ─────────────────────────────
def test_nhap_token_khong_bao_gio_in_token(capsys):
    dv, kho_qc, _ = _mdv()
    vao = json.dumps({"token": TOKEN, "tai_khoan_duyet": [NUOC_HOA, "1002"], "ai": "deploy"})
    assert MA.main(["nhap-token"], dich_vu=dv, stdin=io.StringIO(vao)) == 0
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err and "mark_ads_reader" in out.out
    assert {k for k, t in kho_qc.tk.items() if t["duyet"]} == {NUOC_HOA, MATE}
    env = (f"MARK_META_ADS_TOKEN={TOKEN}\nMARK_META_AD_ACCOUNT_IDS=act_1001,act_1004\n"
           "MARK_KHAC=bi-mat-khac\n")
    assert MA.main(["nhap-token", "--dang-env"], dich_vu=dv, stdin=io.StringIO(env)) == 0
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err and "bi-mat-khac" not in out.out + out.err
    assert {k for k, t in kho_qc.tk.items() if t["duyet"]} == {NUOC_HOA, MADE}
    # Token có quyền ghi: từ chối, mã 1, vẫn không in token.
    dv2, kho2, _ = _mdv(gm=GiaMeta(quyen=("ads_read", "read_insights", "ads_management")))
    assert MA.main(["nhap-token"], dich_vu=dv2, stdin=io.StringIO(vao)) == 1
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err and "ads_management" in out.err
    assert not (kho2.doc_ket_noi("meta_ads") or {}).get("access_token_enc")
    assert MA.main(["trang-thai"], dich_vu=dv) == 0 and TOKEN not in capsys.readouterr().out


def test_cli_chi_khi_yeu_cau_meta(capsys):
    dv, kho_qc, gm = _mdv()
    _gom_tk(dv)
    n = len(gm.goi)
    assert MA.main(["dong-bo", "--chi-khi-yeu-cau", "--khong-bq"], dich_vu=dv) == 0
    assert len(gm.goi) == n and capsys.readouterr().out == ""
    dv.yeu_cau(QL)
    assert MA.main(["dong-bo", "--chi-khi-yeu-cau", "--khong-bq", "--tu", "2026-10-18",
                    "--den", "2026-10-18"], dich_vu=dv) == 0
    assert len(gm.goi) > n and kho_qc.doc_ket_noi("meta_ads")["yeu_cau_dong_bo_luc"] is None


# ───────────────────────────── đồng bộ bấm tay (mọi người có quyền) ─────────────────────────────
def test_luot_nhanh_chi_3_ngay_tai_khoan_co_chay_va_khong_ha_yeu_cau_day_du():
    dv, kho_qc, gm = _mdv()
    _gom_tk(dv)
    dv.dong_bo(tu=datetime.date(2026, 10, 1), den=datetime.date(2026, 10, 18))
    gm.goi.clear()
    dv.yeu_cau(XEM, "nhanh")
    assert MA.main(["dong-bo", "--chi-khi-yeu-cau", "--khong-bq"], dich_vu=dv) == 0
    kc = {_khoang(r) for r in gm.goi if "/insights" in str(r.url) and _khoang(r)}
    assert kc == {("2026-10-17", "2026-10-19")}           # hôm nay (19/10 giờ VN) + 2 ngày trước
    doc = {urlsplit(str(r.url)).path.split("/")[2] for r in gm.goi if "/insights" in str(r.url)}
    assert LA not in doc and NUOC_HOA in doc              # không chạy 30 ngày: bỏ
    kn = kho_qc.doc_ket_noi("meta_ads")
    assert kn["dong_bo_kieu"] == "nhanh" and kn["nhanh_xong_luc"]
    # Yêu cầu day_du (quản trị viên) đang chờ: bấm nhanh không hạ được.
    dv.yeu_cau(QL)
    dv.yeu_cau(XEM, "nhanh")
    assert kho_qc.doc_ket_noi("meta_ads")["yeu_cau_kieu"] == "day_du"
    kho_qc.kns["meta_ads"]["yeu_cau_dong_bo_luc"] = None
    dv.yeu_cau(XEM, "nhanh")
    dv.yeu_cau(QL)                                        # nhanh đang chờ → nâng thành day_du
    assert kho_qc.doc_ket_noi("meta_ads")["yeu_cau_kieu"] == "day_du"
    # Bộ hẹn giờ 06:45 (không --chi-khi-yeu-cau) không bao giờ chạy nhanh.
    kho_qc.kns["meta_ads"]["yeu_cau_kieu"] = "nhanh"
    dv.dong_bo()
    assert kho_qc.doc_ket_noi("meta_ads")["dong_bo_kieu"] == "day_du"


def test_kiem_yeu_cau_dang_chay_dang_cho_gian_15_phut():
    bay = datetime.datetime(2026, 10, 20, 3, 0, tzinfo=datetime.timezone.utc)   # 10:00 giờ VN
    co = {"co_token": True}
    assert QC.kiem_yeu_cau(co, bay) is None
    assert QC.kiem_yeu_cau({}, bay) == "chưa kết nối"
    assert QC.kiem_yeu_cau({**co, "dang_dong_bo": True,
                            "dong_bo_bat_dau": bay - datetime.timedelta(minutes=5)},
                           bay) == "đang chạy từ 09:55"
    assert QC.kiem_yeu_cau({**co, "yeu_cau_dong_bo_luc": bay, "yeu_cau_boi": XEM},
                           bay) == f"đang có yêu cầu lúc 10:00 ({XEM})"
    m = QC.kiem_yeu_cau({**co, "nhanh_xong_luc": bay - datetime.timedelta(minutes=5)}, bay)
    assert m == "vừa đồng bộ lúc 09:55, bấm lại được từ 10:10"
    assert QC.kiem_yeu_cau({**co, "nhanh_xong_luc": bay - datetime.timedelta(minutes=16)},
                           bay) is None
    assert QC.dai_trang_thai({**co, "dong_bo_loi": "x"}, "meta")["nhan"] == "có lỗi"


def _app_hai_nen_tang(gm=None):
    app_kq = _co_so(_tao_app())
    app, c, kho, kho_qc, tt, tdv = app_kq
    dv, _, gm = _mdv(kho_qc=kho_qc, gm=gm)
    app.state.meta = dv
    _gom_tk(dv)
    kho_qc.gan_ben(QL, LA, "hapas", True, False)          # chưa duyệt
    dv.dong_bo(tu=datetime.date(2026, 10, 12), den=datetime.date(2026, 10, 18))
    app.state.nho_ben_qc = (float("-inf"), set())
    return types.SimpleNamespace(app=app, c=c, kho=kho, kho_qc=kho_qc, tt=tt, tdv=tdv, dv=dv,
                                 gm=gm)


def test_dong_bo_bam_tay_moi_nguoi_co_quyen():
    h = _app_hai_nen_tang()
    c, kho, kho_qc, tt, gm = h.c, h.kho, h.kho_qc, h.tt, h.gm
    for k in ("tiktok_ads", "meta_ads"):
        kho_qc.kns[k]["yeu_cau_dong_bo_luc"] = None
    # Không đăng nhập: không ghi được.
    c.cookies.clear()
    r = c.post("/quang-cao/dong-bo", data={"csrf": "x", "nen_tang": "tat_ca"})
    assert r.status_code in (303, 401, 403) and not kho_qc.kns["meta_ads"].get(
        "yeu_cau_dong_bo_luc")
    # Không có quyền ở bên nào: từ chối.
    csrf = dang_nhap(c, "la@hapas.vn")
    r = c.post("/quang-cao/dong-bo", data={"csrf": csrf, "nen_tang": "meta"})
    assert r.status_code == 403 and not kho_qc.kns["meta_ads"].get("yeu_cau_dong_bo_luc")
    # Người Chỉ xem: được, chỉ ghi cờ (không gọi Meta / TikTok), nhật ký bam_tay.
    csrf = dang_nhap(c, XEM)
    t = c.get("/").text
    assert 'data-o="dai-qc"' in t and 'action="/quang-cao/dong-bo"' in t
    dai = t.split('data-o="dai-qc"')[1].split("</section>")[0]
    assert "Chi tiêu" not in dai and "TikTok" in dai and "Meta" in dai
    n_meta, n_tt = len(gm.goi), len(tt.goi)
    r = c.post("/quang-cao/dong-bo", data={"csrf": csrf, "nen_tang": "tat_ca", "ve": "/"})
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "Đã yêu cầu đồng bộ TikTok, Meta" in c.get("/").text
    assert len(gm.goi) == n_meta and len(tt.goi) == n_tt
    for k in ("tiktok_ads", "meta_ads"):
        assert kho_qc.kns[k]["yeu_cau_kieu"] == "nhanh" and kho_qc.kns[k]["yeu_cau_boi"] == XEM
    assert any(x[0] == XEM and x[1] == "dong_bo_qc" for x in kho.nk)
    # Đang có yêu cầu: không tạo mới, nói lúc nào + ai.
    csrf = dang_nhap(c, HP_QL)
    r = c.post("/quang-cao/dong-bo", data={"csrf": csrf, "nen_tang": "meta"})
    t = c.get(r.headers["location"]).text
    assert "Chưa tạo yêu cầu mới" in t and "đang có yêu cầu lúc" in t and XEM in t
    assert kho_qc.kns["meta_ads"]["yeu_cau_boi"] == XEM
    # Đang chạy: từ chối.
    kho_qc.kns["meta_ads"]["yeu_cau_dong_bo_luc"] = None
    with kho_qc.khoa_dong_bo(MA.KHOA_DONG_BO):
        r = c.post("/quang-cao/dong-bo", data={"csrf": csrf, "nen_tang": "meta"})
        assert "đang chạy từ" in c.get(r.headers["location"]).text
    # Vừa xong lượt nhanh < 15 phút: chưa cho bấm.
    kho_qc.kns["meta_ads"]["nhanh_xong_luc"] = datetime.datetime.now(datetime.timezone.utc)
    r = c.post("/quang-cao/dong-bo", data={"csrf": csrf, "nen_tang": "meta"})
    assert "bấm lại được từ" in c.get(r.headers["location"]).text
    assert not kho_qc.kns["meta_ads"].get("yeu_cau_dong_bo_luc")
    # Nạp lùi / kết nối / ngắt / gán bên: vẫn chỉ quản trị viên.
    for p in ("/meta/dong-bo", "/meta/ngat", "/meta/token", "/qc/gan-ben", "/tiktok/dong-bo"):
        assert c.post(p, data={"csrf": csrf, "token": TOKEN, "advertiser_id": NUOC_HOA}
                      ).status_code == 403, p


def test_bo_hen_gio_2_phut_va_06_45():
    d = GOC / "deploy" / "lang-nghe"
    for f in ("tiktok-ads-yeu-cau.timer", "meta-ads-yeu-cau.timer"):
        t = (d / f).read_text(encoding="utf-8")
        assert "OnUnitActiveSec=2min" in t and "10min" not in t, f
    assert "OnCalendar=*-*-* 06:45:00 Asia/Ho_Chi_Minh" in (d / "meta-ads-dong-bo.timer").read_text(
        encoding="utf-8")
    sv = (d / "meta-ads-yeu-cau.service").read_text(encoding="utf-8")
    assert "dashboard.meta_ads dong-bo --chi-khi-yeu-cau" in sv and "User=lang_nghe_web" in sv
    assert "InaccessiblePaths=-/opt/mark" in sv
    assert "dashboard.meta_ads dong-bo\n" in (d / "meta-ads-dong-bo.service").read_text(
        encoding="utf-8")
    from dashboard import app as A
    assert "≤ 2 phút" in A.CHO_DONG_BO


# ───────────────────────────── trang + /api/qc ─────────────────────────────
def test_api_qc_loc_nen_tang_va_chi_quan_tri():
    h = _app_hai_nen_tang()
    c, kho_qc = h.c, h.kho_qc
    Q = "tu=2026-10-12&den=2026-10-18"
    for ai in (XEM, HP_QL, MM_XEM):
        dang_nhap(c, ai)
        assert c.get(f"/api/qc?{Q}&nen_tang=meta").status_code == 404, ai
    dang_nhap(c, QL)
    d = c.get(f"/api/qc?{Q}").json()
    assert d["nen_tang"] == "tat_ca" and [x["ma"] for x in d["cac_nen_tang"]] == [
        "tat_ca", "tiktok", "meta"]
    assert {x["nen_tang"] for x in d["tai_khoan"]} == {"tiktok", "meta"}
    assert LA not in {x["advertiser_id"] for x in d["tai_khoan"]}        # chưa duyệt: bỏ
    assert {x["nen_tang"] for x in d["theo_nen_tang"]} == {"tiktok", "meta"}
    assert all("nen_tang" in r for r in d["campaign"] + d["ad"] + d["theo_ngay_nen_tang"])
    m = c.get(f"/api/qc?{Q}&nen_tang=meta").json()
    assert {x["nen_tang"] for x in m["tai_khoan"]} == {"meta"}
    assert m["campaign"] and all(r["nen_tang"] == "meta" for r in m["campaign"])
    tong_meta = sum(r["chi"] for r in kho_qc.bang["qc_tk_ngay"].values()
                    if r["advertiser_id"].startswith("act_"))
    assert m["kpi"]["chi"] == tong_meta
    tk = c.get(f"/api/qc?{Q}&nen_tang=tiktok").json()
    assert m["kpi"]["chi"] + tk["kpi"]["chi"] == d["kpi"]["chi"]
    assert c.get(f"/api/qc?{Q}&nen_tang=youtube").status_code == 400
    t = c.get(f"/quang-cao?{Q}&nen_tang=meta").text
    assert 'data-o="loc-nen-tang"' in t and 'id="qc-api"' in t and "Meta ·" in t
    assert "Vị trí Meta" in t and "Instagram · reels" in t


def test_the_ket_noi_meta_chi_quan_tri_khong_token():
    h = _app_hai_nen_tang()
    c, kho_qc = h.c, h.kho_qc
    dang_nhap(c, QL)
    t = c.get("/quan-tri").text
    assert "Kết nối Meta Ads" in t and "mark_ads_reader" in t and "ads_read" in t
    assert 'action="/meta/token"' in t and 'action="/qc/gan-ben"' in t
    assert f'data-o="tk-{LA}"' in t and "Chưa duyệt" in t
    enc = kho_qc.kns["meta_ads"]["access_token_enc"]
    for ai in (QL, XEM, HP_QL):
        dang_nhap(c, ai)
        for p in ("/quan-tri", "/quang-cao", "/api/qc", "/"):
            x = c.get(p).text
            assert TOKEN not in x and enc not in x, (ai, p)
    dang_nhap(c, HP_QL)
    assert "Kết nối Meta Ads" not in c.get("/quan-tri").text


def test_quan_tri_duyet_va_ngat_meta():
    h = _app_hai_nen_tang()
    c, kho_qc = h.c, h.kho_qc
    csrf = dang_nhap(c, QL)
    r = c.post("/qc/gan-ben", data={"csrf": csrf, "advertiser_id": LA, "don_vi": "hapas",
                                     "dang_dong_bo": "1", "duyet": "1"})
    assert r.status_code == 303 and kho_qc.tk[LA]["duyet"] is True
    c.post("/meta/dong-bo", data={"csrf": csrf})
    assert kho_qc.kns["meta_ads"]["yeu_cau_kieu"] == "day_du"
    r = c.post("/meta/token", data={"csrf": csrf, "token": "EAAsai0123456789abcdefghijk"})
    assert "không nhận token" in c.get(r.headers["location"]).text
    r = c.post("/meta/ngat", data={"csrf": csrf})
    assert "Business Settings" in c.get(r.headers["location"]).text
    assert kho_qc.kns["meta_ads"]["access_token_enc"] is None


# ───────────────────────────── Mark ─────────────────────────────
class _KhoMarkGia:
    """Như HD.KhoMark: hàm đọc của kho + kho_qc (tên phía tool)."""

    def __init__(self, kho, kho_qc):
        import hoi_dashboard_tool as HD
        self.HD, self.kho, self.kho_qc = HD, kho, kho_qc

    def __getattr__(self, ten):
        if ten in self.HD._HAM_KHO_QC:
            return getattr(self.kho_qc, self.HD._HAM_KHO_QC[ten])
        return getattr(self.kho, ten)


BAY_MARK = datetime.datetime(2026, 10, 19, 9, 0, tzinfo=VN)
ARGS = {"phan": ["quang_cao"], "tu": "2026-10-12", "den": "2026-10-18"}


def _hoi(monkeypatch, ai, args, kho, kho_qc):
    import hoi_dashboard_tool as HD
    monkeypatch.setattr(HD, "email_cua", lambda oid: ai)
    return HD.tra_loi(args, _KhoMarkGia(kho, kho_qc), open_id="ou_hoi", bay_gio=BAY_MARK)


def test_mark_quang_cao_hai_nen_tang_va_tien_chi_xem(monkeypatch):
    h = _app_hai_nen_tang()
    kho, kho_qc = h.kho, h.kho_qc
    qc = _hoi(monkeypatch, XEM, ARGS, kho, kho_qc)["phan"]["quang_cao"]
    b = qc["ben"][0]
    assert b["ben"] == "hapas" and b["xem_tien"] is True and b["kpi"]["chi"] > 0
    assert {x["nen_tang"] for x in b["theo_nen_tang"]} == {"TikTok", "Meta"}
    assert sum(float(x["chi"]) for x in b["theo_nen_tang"]) == float(b["kpi"]["chi"])
    assert {x["nen_tang"] for x in b["theo_tai_khoan"]} == {"TikTok", "Meta"}
    assert all("nen_tang" in x for x in b["top_chien_dich"])
    assert "link" not in b and "BẰNG CHỮ" in qc["ghi_chu"]
    # Reach không cộng qua ngày: tổng kỳ trống, từng ngày có.
    assert b["kpi"]["reach"] is None and b["theo_nen_tang"][0]["reach"] is None
    assert b["theo_ngay"][0]["reach"] > 0 and "không cộng" in qc["ghi_chu"]
    # Lọc nền tảng.
    m = _hoi(monkeypatch, XEM, {**ARGS, "nen_tang": "meta"}, kho, kho_qc)["phan"]["quang_cao"]
    assert {x["nen_tang"] for x in m["ben"][0]["theo_tai_khoan"]} == {"Meta"}
    # Bên khác: không thấy; quản trị viên có link.
    assert _hoi(monkeypatch, XEM, {**ARGS, "ben": "matemade"}, kho, kho_qc)["phan"][
        "quang_cao"]["co"] is False
    q = _hoi(monkeypatch, QL, ARGS, kho, kho_qc)["phan"]["quang_cao"]
    assert all(x["link"].startswith("https://") for x in q["ben"])


def test_mark_tra_chien_dich_theo_ten_khong_dau(monkeypatch):
    h = _app_hai_nen_tang()
    kho, kho_qc = h.kho, h.kho_qc
    r = _hoi(monkeypatch, XEM, {"tim": "nuoc  hoa THANG 10", "cap": "chien_dich",
                                "tu": "2026-10-12", "den": "2026-10-18", "theo_ngay": True},
             kho, kho_qc)["phan"]["quang_cao"]
    assert r["tim_thay"] == 1 and r["mo_ho"] is False
    x = r["doi_tuong"][0]
    assert x["ten"] == "Nước Hoa Tháng 10 - Chuyển đổi" and x["nen_tang"] == "Meta"
    assert x["ben"] == "hapas" and x["muc_tieu"] == "Bán hàng" and x["xem_tien"] is True
    rows = [v for k, v in kho_qc.bang["qc_campaign_ngay"].items() if k[0] == "120201"
            and datetime.date(2026, 10, 12) <= k[1] <= datetime.date(2026, 10, 18)]
    chi, hien, click = (sum(r[k] for r in rows) for k in ("chi", "hien_thi", "click"))
    assert x["so"]["chi"] == chi and x["so"]["reach"] is None
    # Tỉ lệ tính LẠI từ tổng — không cộng ctr (10.0) của từng ngày.
    assert x["chi_phi"]["ctr"] == round(click * 100 / hien, 2)
    assert x["chi_phi"]["cpc"] == round(chi / click, 2)
    tho = x["chi_so_tho_cong_duoc"]
    assert "ctr" not in tho and "reach" not in tho and "frequency" not in tho
    assert tho["actions__purchase"] == 2 * len(rows) and tho["spend"] == chi
    assert len(x["theo_ngay"]) == 7 and x["theo_ngay"][0]["reach"] is not None
    assert x["ngay_dau_co_phan_phoi"] and x["ngay_cuoi_co_phan_phoi"]
    # Theo mã.
    r = _hoi(monkeypatch, XEM, {"tim": "120202", "cap": "chien_dich", **ARGS}, kho, kho_qc)
    assert r["phan"]["quang_cao"]["doi_tuong"][0]["ten"] == "Trang sức Thu"
    # Quảng cáo + tài khoản + TikTok cùng một đường.
    r = _hoi(monkeypatch, XEM, {"tim": "qc trang suc", "cap": "quang_cao", **ARGS}, kho, kho_qc)
    assert r["phan"]["quang_cao"]["doi_tuong"][0]["nhom"] == "Nhóm Trang sức Thu"
    r = _hoi(monkeypatch, XEM, {"tim": "hapas 1", "cap": "tai_khoan", **ARGS}, kho, kho_qc)
    assert r["phan"]["quang_cao"]["doi_tuong"][0]["tai_khoan"] == TK_META[NUOC_HOA]
    tiktok = next(v for v in kho_qc.bang["qc_campaign_ngay"].values()
                  if not v["advertiser_id"].startswith("act_")
                  and kho_qc.tk[v["advertiser_id"]]["don_vi"] == "hapas")
    r = _hoi(monkeypatch, XEM, {"tim": tiktok["campaign_id"], "cap": "chien_dich", **ARGS}, kho,
             kho_qc)
    assert any(d["ma"] == tiktok["campaign_id"] and d["nen_tang"] == "TikTok"
               for d in r["phan"]["quang_cao"]["doi_tuong"])


def test_mark_tra_cuu_khong_thay_goi_y_va_ben_khac_vo_hinh(monkeypatch):
    h = _app_hai_nen_tang()
    kho, kho_qc = h.kho, h.kho_qc
    r = _hoi(monkeypatch, XEM, {"tim": "nuoc hoa thang 11", "cap": "chien_dich", **ARGS}, kho,
             kho_qc)["phan"]["quang_cao"]
    assert r["tim_thay"] == 0 and "KHÔNG đoán số" in r["ghi_chu"] and "doi_tuong" not in r
    assert r["goi_y"][0] == "Nước Hoa Tháng 10 - Chuyển đổi" and len(r["goi_y"]) <= 5
    # MATEMADE Chỉ xem không thấy chiến dịch HAPAS (cũng không trong gợi ý).
    r = _hoi(monkeypatch, MM_XEM, {"tim": "nuoc hoa", "cap": "chien_dich", **ARGS}, kho,
             kho_qc)["phan"]["quang_cao"]
    assert r["tim_thay"] == 0 and not any("Nước Hoa" in g for g in r["goi_y"])
    r = _hoi(monkeypatch, MM_XEM, {"tim": "mate made sale", **ARGS}, kho, kho_qc)["phan"][
        "quang_cao"]
    assert r["doi_tuong"][0]["ben"] == "matemade" and r["doi_tuong"][0]["xem_tien"] is True
    # THAI chưa gán bên: chỉ quản trị viên tra được.
    assert _hoi(monkeypatch, XEM, {"tim": "thai test", **ARGS}, kho, kho_qc)["phan"][
        "quang_cao"]["tim_thay"] == 0
    r = _hoi(monkeypatch, QL, {"tim": "thai test", **ARGS}, kho, kho_qc)["phan"]["quang_cao"]
    assert r["doi_tuong"][0]["ben"] is None and r["doi_tuong"][0]["so"]["chi"] > 0


def test_mark_tra_cuu_mo_ho_toi_da_10(monkeypatch):
    nhieu = {**CAMPAIGN, NUOC_HOA: [(f"1300{i:02d}", f"Sale {i}") for i in range(14)]}
    h = _app_hai_nen_tang(GiaMeta(campaign=nhieu))
    kho, kho_qc = h.kho, h.kho_qc
    r = _hoi(monkeypatch, XEM, {"tim": "sale", **ARGS}, kho, kho_qc)["phan"]["quang_cao"]
    assert r["tim_thay"] == 14 and r["mo_ho"] is True and len(r["doi_tuong"]) == 10
    chi = [x["so"]["chi"] for x in r["doi_tuong"]]
    assert chi == sorted(chi, reverse=True) and "hỏi lại" in r["ghi_chu"]


def test_mark_mo_ta_tool_luat_cau_hoi_la_goc():
    import hoi_dashboard_tool as HD
    mo_ta = HD.SCHEMA["description"]
    assert "CÂU HỎI CỦA NGƯỜI DÙNG LÀ GỐC" in mo_ta and "không tự nêu chi tiêu" in mo_ta
    p = HD.SCHEMA["parameters"]["properties"]
    assert {"tim", "cap", "nen_tang", "theo_ngay"} <= set(p)
    assert "Câu hỏi của người dùng là gốc" in HD.GHI_CHU_QC


# ───────────────────────────── SQL + schema + BigQuery ─────────────────────────────
def test_sql_doc_tra_cuu_chi_select_tham_so_hoa(monkeypatch):
    import inspect

    from test_tiktok_ads import _GhiSQL
    for ham in (KQ.qc_tim, KQ.qc_ten, KQ.qc_doi_tuong, KQ.qc_chi_so_tong, KQ.qc_doi_tuong_ngay):
        assert not re.search(r"\b(INSERT|UPDATE|DELETE)\b", inspect.getsource(ham)), ham.__name__
    g = _GhiSQL({"WITH moi": [{"ma": "1", "advertiser_id": NUOC_HOA, "ten": "x", "muc_tieu": None,
                               "tong": 3}]})
    monkeypatch.setattr(KQ, "ket_noi", g)
    kq = KQ.qc_tim("chien_dich", [NUOC_HOA], QC.chu_tim("Nước Hoa'; DROP"), "x'; --")
    sql, ts = g.cau[0]
    assert "translate(ten, %s, %s)" in sql and "DROP" not in sql and "--" not in sql
    assert "%nuochoadrop%" in ts and kq["tong"] == 3 and "tong" not in kq["rows"][0]
    assert QC.chu_tim("Đ ĐẸP  Ư") == "ddepu" and KQ.DICH_TU.count("đ") == 1
    assert len(KQ.DICH_TU) == len(KQ.DICH_THANH)
    for bang in ("qc_campaign_ngay", "qc_ad_ngay"):
        assert f"WHERE {bang}.advertiser_id = EXCLUDED.advertiser_id" in KQ.sql_upsert(bang)


def test_sql_ghi_tk_meta_chi_dung_nen_tang_cua_minh(monkeypatch):
    from test_tiktok_ads import _GhiSQL
    g = _GhiSQL({"SELECT ma FROM don_vi": [{"ma": "hapas"}, {"ma": "matemade"}]})
    monkeypatch.setattr(KQ, "ket_noi", g)
    KQ.ghi_tk([{"advertiser_id": THAI, "ten": "THAI 1"},
               {"advertiser_id": MATE, "ten": "MATEMADE-6"}], ncc="meta_ads", duyet_moi={MATE})
    them = [t for s, t in g.cau if s.startswith("INSERT INTO tk_quang_cao")]
    assert [(t[2], t[5], t[6]) for t in them] == [(None, "meta", False), ("matemade", "meta", True)]
    mat = next((s, t) for s, t in g.cau if "con_quyen = FALSE" in s)
    assert "nen_tang = %s" in mat[0] and mat[1][0] == "meta"


def test_schema_meta_va_quyen_mark():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    assert "CHECK (nha_cung_cap IN ('tiktok_ads', 'meta_ads'))" in sql
    assert "ADD COLUMN IF NOT EXISTS nen_tang TEXT NOT NULL DEFAULT 'tiktok'" in sql
    assert "OR (nen_tang = 'meta' AND advertiser_id ~ '^act_[0-9]{1,30}$')" in sql
    for c in ("chu_token", "quyen_token", "yeu_cau_kieu", "dong_bo_kieu", "nhanh_xong_luc"):
        assert f"COMMENT ON COLUMN ket_noi_ngoai.{c} IS" in sql, c
    assert "COMMENT ON COLUMN tk_quang_cao.nen_tang IS" in sql
    m = re.search(r"GRANT SELECT \(([^)]*)\)\s*ON ket_noi_ngoai TO mark;", sql)
    assert "token" not in m.group(1)
    assert "'platform_position'" in sql and "NULL khi TikTok không trả" not in sql


def test_bigquery_nen_tang_khong_token_khong_email(monkeypatch):
    cot = dict(DBQ.BANG["tk_quang_cao"]["cot"])
    assert cot["nen_tang"] == "STRING" and cot["duyet"] == "BOOL"
    assert set(DBQ.BANG["tk_quang_cao"]["tuy_chon"]) == {"nen_tang", "duyet"}
    for b, v in DBQ.BANG.items():
        assert not [c for c, _ in v["cot"] if any(x in c for x in ("token", "email", "nguoi_cap"))], b
    sql = (GOC / "deploy" / "lang-nghe" / "bigquery.sql").read_text(encoding="utf-8")
    cuoi = sql[sql.index("-- ───────────── Meta Ads (20/10/2026)"):]
    assert "ADD COLUMN IF NOT EXISTS nen_tang STRING" in cuoi
    assert "ADD COLUMN IF NOT EXISTS duyet BOOL" in cuoi and "CREATE TABLE" not in cuoi
    assert "ket_noi_ngoai" not in cuoi and "chu_token" not in sql
    # Tiền: BQ_QC_XUAT_TIEN khác 1 → bỏ cả khoá tiền Meta trong chi_so; = 1 (prod) → giữ.
    r = {"chi": 10, "chi_so": {"spend": 10, "action_values__purchase": 5, "actions__purchase": 1}}
    monkeypatch.delenv("BQ_QC_XUAT_TIEN", raising=False)
    assert DBQ._bo_tien("qc_tk_ngay", r)["chi_so"] == {"actions__purchase": 1}
    monkeypatch.setenv("BQ_QC_XUAT_TIEN", "1")
    assert DBQ._bo_tien("qc_tk_ngay", r) == r


def test_meta_ads_tool_cu_khong_doi():
    kq = subprocess.run(["git", "diff", "--quiet", "c1e1627", "--", "meta_ads_tool.py"],
                        cwd=GOC, capture_output=True, check=False)
    assert kq.returncode == 0
