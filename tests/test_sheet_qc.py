"""Tạo Lark Sheet từ trang Quảng cáo (20/10/2026, chủ dự án chốt) + dọn đồng bộ bấm tay.

Soi: dải "Số quảng cáo" chỉ còn ở trang Quảng cáo; thẻ kết nối Quản trị không còn "Đồng bộ ngay";
POST /quang-cao/tao-sheet chỉ quản trị viên + CSRF + trần, phạm vi kiểm lại ở máy chủ; bộ nghe phía
Mark (`xuat_sheet_qc`) dựng đúng ba tab từ dòng giả, khoá riêng tư TRƯỚC khi ghi số, cấp quyền XEM
theo email, nhắn link, ghi trạng thái; lỗi ghi rõ; schema có đúng quyền + RLS dựa vào.

Không mạng, không Postgres: kho giả (`test_tiktok_ads`), kho Sheet giả, Lark GIẢ (`sheet_gia`).
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest
from sheet_gia import LarkGia
from test_dashboard_app import HP_QL, QL, XEM, dang_nhap
from test_tiktok_ads import HAPAS_KOC, LE, MM_2, MM_MKT, _co_so, _tao_app

import xuat_sheet_qc as X
from dashboard import kho_sheet_qc as KS
from dashboard import quang_cao as QC
from dashboard.kho import LoiDuLieu

GOC = Path(__file__).resolve().parents[1]
UTC = datetime.timezone.utc
Q = "tu=2026-10-12&den=2026-10-18"


# ───────────────────────────── kho Sheet giả (phía dashboard) ─────────────────────────────
class GiaKhoSheet:
    """Như `kho_sheet_qc` phía web: chỉ thêm + đọc dòng của chính người đó, cùng luật trần."""

    def __init__(self):
        self.rows: list[dict] = []

    def tao(self, nguoi_hoi, ben, nen_tang, tk, tu, den, *, tran_gio=KS.TRAN_GIO):
        bay = datetime.datetime.now(UTC)
        cua = [r for r in self.rows if r["nguoi_hoi"] == nguoi_hoi]
        dang = sum(1 for r in cua if KS.hien_trang(r, bay) in ("cho", "dang_tao"))
        gio = sum(1 for r in cua if bay - r["tao_luc"] < datetime.timedelta(hours=1))
        ly = KS.ly_do_chan(dang, gio, tran_gio)
        if ly:
            raise LoiDuLieu(ly)
        r = {"id": len(self.rows) + 1, "nguoi_hoi": nguoi_hoi, "ben": ben, "nen_tang": nen_tang,
             "tk": tk, "tu": tu, "den": den, "trang_thai": "cho", "tieu_de": None, "sheet_url": None,
             "so_dong": {}, "loi": None, "da_nhan_tin": False, "tao_luc": bay, "bat_dau_luc": None,
             "xong_luc": None}
        self.rows.append(r)
        return dict(r)

    def gan_day(self, nguoi_hoi, n=5):
        return [dict(r) for r in reversed(self.rows) if r["nguoi_hoi"] == nguoi_hoi][:n]


def _app():
    app, c, kho, kho_qc, tt, dv = _co_so(_tao_app())
    app.state.kho_sheet = ks = GiaKhoSheet()
    return app, c, kho, kho_qc, ks


def _form(csrf, **kw):
    return {"csrf": csrf, "ben": "tat_ca", "nen_tang": "tat_ca", "tk": "", "tu": "2026-10-12",
            "den": "2026-10-18", **kw}


# ───────────────────────────── 1 + 2: dọn đồng bộ bấm tay ─────────────────────────────
def test_dai_qc_chi_o_trang_quang_cao():
    _a, c, _kho, _kq, _ks = _app()
    dang_nhap(c, QL)
    assert 'data-o="dai-qc"' not in c.get("/").text
    t = c.get(f"/quang-cao?{Q}").text
    assert 'data-o="dai-qc"' in t and 'action="/quang-cao/dong-bo"' in t
    src = (GOC / "dashboard" / "templates" / "chi_so.html").read_text(encoding="utf-8")
    assert "_dai_qc.html" not in src
    app_src = (GOC / "dashboard" / "app.py").read_text(encoding="utf-8")
    trang = app_src[app_src.index("async def trang_chi_so"):app_src.index("def _dv_qc")]
    assert "dai_qc" not in trang


def test_the_quan_tri_khong_con_dong_bo_ngay():
    _a, c, _kho, _kq, _ks = _app()
    csrf = dang_nhap(c, QL)
    t = c.get("/quan-tri").text
    assert "Kết nối TikTok Ads" in t and "Ngắt kết nối" in t
    assert 'action="/tiktok/dong-bo"' not in t and 'action="/meta/dong-bo"' not in t
    for p in ("/tiktok/dong-bo", "/meta/dong-bo"):
        assert c.post(p, data={"csrf": csrf}).status_code in (404, 405), p
    # Trang BigQuery vẫn có nút riêng của nó.
    assert "Đồng bộ ngay" in (GOC / "dashboard" / "templates" / "bigquery.html").read_text(
        encoding="utf-8")


# ───────────────────────────── 3: dashboard ─────────────────────────────
def test_tao_sheet_chi_quan_tri_va_csrf():
    _a, c, kho, _kq, ks = _app()
    for ai in (XEM, HP_QL):
        csrf = dang_nhap(c, ai)
        assert c.post("/quang-cao/tao-sheet", data=_form(csrf)).status_code == 403, ai
        assert c.get("/api/qc/sheet").status_code == 404, ai
    dang_nhap(c, QL)
    assert c.post("/quang-cao/tao-sheet", data=_form("sai")).status_code == 403
    csrf = dang_nhap(c, QL)
    r = c.post("/quang-cao/tao-sheet", data=_form(csrf),
               headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and ks.rows == []


def test_tao_sheet_ghi_yeu_cau_dung_pham_vi_va_tran():
    _a, c, kho, _kq, ks = _app()
    csrf = dang_nhap(c, QL)
    t = c.get(f"/quang-cao?{Q}&ben=matemade&nen_tang=tiktok").text
    khoi = t.split('id="sheet"')[1].split("</section>")[0]
    assert "Tạo Lark Sheet" in t and 'action="/quang-cao/tao-sheet"' in khoi
    assert 'name="ben" value="matemade"' in khoi and 'name="nen_tang" value="tiktok"' in khoi
    assert "7 ngày" in khoi and "Theo quảng cáo" in khoi and "Chưa tạo Sheet nào" in khoi
    r = c.post("/quang-cao/tao-sheet", data=_form(csrf, ben="matemade", nen_tang="tiktok",
                                                   tk=MM_MKT))
    assert r.status_code == 303 and r.headers["location"].endswith("#sheet")
    assert "ben=matemade" in r.headers["location"]
    assert ks.rows[0] | {} == {**ks.rows[0], "nguoi_hoi": QL, "ben": "matemade",
                               "nen_tang": "tiktok", "tk": MM_MKT,
                               "tu": datetime.date(2026, 10, 12), "den": datetime.date(2026, 10, 18)}
    assert (QL, KS.HANH_DONG, "sheet_qc:1") in kho.nk
    t = c.get(r.headers["location"].split("#")[0]).text
    assert "Đang tạo Sheet" in t
    khoi = t.split('id="sheet"')[1].split("</section>")[0]
    assert 'data-dang="1"' in t and "Đang chờ" in khoi and 'id="qc-sheet-nut" disabled' in khoi
    j = c.get("/api/qc/sheet").json()
    assert j["dang"] is True and j["ds"][0]["trang_thai"] == "cho"
    # Một yêu cầu đang chờ mỗi người.
    r = c.post("/quang-cao/tao-sheet", data=_form(csrf))
    assert "đang có một Sheet đang tạo" in c.get(r.headers["location"].split("#")[0]).text
    assert len(ks.rows) == 1
    # Xong: hiện link (chỉ https) + số dòng; hết đang tạo → nút mở lại.
    ks.rows[0].update(trang_thai="xong", sheet_url="https://x.larksuite.com/sheets/sht1",
                      tieu_de="TikTok Ads · MATEMADE · 12/10–18/10/2026",
                      so_dong={"ngay": 7, "chien_dich": 3, "quang_cao": 5, "tong_chien_dich": 3,
                               "tong_quang_cao": 9})
    t = c.get(f"/quang-cao?{Q}").text
    khoi = t.split('id="sheet"')[1].split("</section>")[0]
    assert 'href="https://x.larksuite.com/sheets/sht1"' in khoi and "(đã cắt)" in khoi
    assert 'data-dang="0"' in t and 'id="qc-sheet-nut" disabled' not in khoi
    ks.rows[0]["sheet_url"] = "javascript:alert(1)"
    assert "javascript:" not in c.get(f"/quang-cao?{Q}").text
    # Trần mỗi giờ.
    for r0 in ks.rows:
        r0["trang_thai"] = "xong"
    for _ in range(KS.TRAN_GIO - 1):
        c.post("/quang-cao/tao-sheet", data=_form(csrf))
        ks.rows[-1]["trang_thai"] = "xong"
    r = c.post("/quang-cao/tao-sheet", data=_form(csrf))
    assert f"tối đa {KS.TRAN_GIO} Sheet mỗi giờ" in c.get(r.headers["location"].split("#")[0]).text
    assert len(ks.rows) == KS.TRAN_GIO


def test_tao_sheet_tu_choi_pham_vi_sai():
    _a, c, _kho, _kq, ks = _app()
    csrf = dang_nhap(c, QL)
    for f, cau in ((_form(csrf, tk="123", ben="hapas"), "chưa có tài khoản"),
                   (_form(csrf, tu="2025-01-01", den="2026-10-18"), "Khoảng ngày"),
                   (_form(csrf, ben="'; drop"), "Bộ lọc không hợp lệ"),
                   (_form(csrf, nen_tang="youtube"), "Bộ lọc không hợp lệ")):
        r = c.post("/quang-cao/tao-sheet", data=f)
        assert r.status_code == 303 and cau in c.get(r.headers["location"].split("#")[0]).text, cau
    assert ks.rows == []


def test_ly_do_chan_va_qua_han():
    assert KS.ly_do_chan(0, 0) is None
    assert "đang có" in KS.ly_do_chan(1, 0)
    assert "tối đa 4" in KS.ly_do_chan(0, 4)
    bay = datetime.datetime(2026, 10, 20, 3, 0, tzinfo=UTC)
    cu = {"trang_thai": "cho", "tao_luc": bay - datetime.timedelta(minutes=31)}
    assert KS.hien_trang(cu, bay) == "qua_han"
    assert KS.hien_trang({**cu, "tao_luc": bay}, bay) == "cho"
    assert KS.hien_trang({"trang_thai": "dang_tao",
                          "bat_dau_luc": bay - datetime.timedelta(hours=1)}, bay) == "qua_han"


def test_tk_xuat_cung_luat_trang():
    tk = [{"advertiser_id": "1", "don_vi": "hapas", "nen_tang": "tiktok"},
          {"advertiser_id": "act_2", "don_vi": "hapas", "nen_tang": "meta", "duyet": False},
          {"advertiser_id": "act_3", "don_vi": "hapas", "nen_tang": "meta"},
          {"advertiser_id": "4", "don_vi": None, "nen_tang": "tiktok"}]
    qt = {"la_quan_tri": True, "ben": {}}
    ql = {"la_quan_tri": False, "ben": {"hapas": "quan_ly"}}
    ids = lambda ds: [t["advertiser_id"] for t in ds]  # noqa: E731
    assert ids(QC.tk_xuat(qt, tk, "hapas", "tat_ca")) == ["1", "act_3"]       # chưa duyệt: bỏ
    assert ids(QC.tk_xuat(qt, tk, "hapas", "meta")) == ["act_3"]
    assert ids(QC.tk_xuat(qt, tk, "chua_gan", "tat_ca")) == ["4"]
    assert ids(QC.tk_xuat(qt, tk, "hapas", "tiktok", "act_3")) == []
    assert QC.tk_xuat(ql, tk, "tat_ca", "tat_ca") == [] and QC.tk_xuat(qt, tk, "hapas", "x") == []
    h = QC.hieu_qua({"chi": 1000, "hien_thi": 500, "click": 5, "follow": 0, "view_video": 200})
    assert h["cpm"] == 2000 and h["ctr"] == 1 and h["cpc"] == 200 and h["chi_tren_1000_view"] == 5000
    assert h["chi_moi_follow"] is None and all(QC.la_tien(k) for k in (
        "cpm", "cpc", "chi_tren_1000_view", "chi_moi_follow", "chi_moi_ket_qua", "roas_shop"))


def test_dashboard_khong_goi_lark_sheet():
    """Dashboard không giữ app Lark tạo Sheet: không đường Sheet / Drive / tin nhắn nào trong mã web."""
    for f in ("app.py", "kho_sheet_qc.py", "quang_cao.py"):
        s = (GOC / "dashboard" / f).read_text(encoding="utf-8")
        assert "/open-apis/sheets" not in s and "/open-apis/drive" not in s, f
        assert "/open-apis/im/" not in s and "lark_client" not in s and "LARK_APP_SECRET" not in s, f


# ───────────────────────────── 3: bộ nghe phía Mark ─────────────────────────────
_RIENG = {"link_share_entity": "closed", "external_access_entity": "closed",
          "share_entity": "same_tenant", "manage_collaborator_entity": "collaborator_full_access"}


class LarkMark:
    """App Lark của Mark (giả): bảng tính qua `LarkGia`, quyền + tin nhắn ghi lại."""

    def __init__(self, hong=()):
        self.gia = LarkGia()
        self.hong = set(hong)
        self.tin: list[tuple] = []

    def call(self, method, path, query=None, body=None):
        if path.endswith("/public"):
            self.gia.goi.append((method, path, query, body))
            return {"data": {"permission_public": dict(_RIENG)}} if method == "GET" else {}
        if path.endswith("/members"):
            self.gia.goi.append((method, path, query, body))
            if (body or {}).get("member_type") in self.hong:
                raise RuntimeError("Lark POST members failed: HTTP 400: giả hỏng")
            return {"data": {}}
        if path.endswith("/batch_get_id"):
            return {"data": {"user_list": [{"email": body["emails"][0], "user_id": "ou_qtv"}]}}
        return self.gia.call(method, path, query=query, body=body)

    def send_text(self, loai, ma, text, uuid=None):
        if "tin" in self.hong:
            raise RuntimeError("Lark im failed")
        self.tin.append((loai, ma, text, uuid))


class KhoNghe:
    """Như `kho_sheet_qc` phía mark (+ quyền / tài khoản của kho)."""

    def __init__(self, yc, tk, quyen):
        self.yc, self.tk, self.quyen = yc, tk, quyen
        self.ket: list = []
        self.nhan_tin: list = []

    # kho / kho_qc
    def quyen_cua(self, email):
        return self.quyen.get(email)

    def cac_tk(self):
        return list(self.tk)

    # kho_sheet_qc
    def ten_ben(self):
        return {"hapas": "HAPAS", "matemade": "MATEMADE"}

    def doc_theo_ngay(self, ids, tu, den):
        rows = [{"advertiser_id": a, "ngay": tu + datetime.timedelta(days=i), "chi": 100000.0 * (i + 1),
                 "hien_thi": 10000, "reach": 6000, "click": 120, "view_video": 4000, "follow": 20,
                 "thich": 50, "binh_luan": 5, "chia_se": 2, "ket_qua": 10}
                for a in ids for i in range((den - tu).days + 1)]
        return {"rows": rows, "tong": len(rows)}

    def doc_tong(self, cap, ids, tu, den):
        if cap == "chien_dich":
            rows = [{"campaign_id": "17001", "advertiser_id": ids[0], "ten": "=HYPERLINK(1)",
                     "muc_tieu": "VIDEO_VIEWS", "chi": 500000.0, "hien_thi": 50000, "click": 400,
                     "view_video": 9000, "follow": 0, "so_ngay": 7}]
            return {"rows": rows, "tong": 1}
        rows = [{"ad_id": f"18{i:03d}", "advertiser_id": ids[0], "campaign_id": "17001",
                 "ten_ad": f"Ad {i}", "noi_dung": "Nội dung", "ten_campaign": "CD", "ten_nhom": "N",
                 "chi": 1000.0 * i, "hien_thi": 100 * i, "click": i, "so_ngay": 3}
                for i in range(1, 4)]
        return {"rows": rows, "tong": 12000}                 # bị cắt: 3 / 12.000

    def doc_tong_tien_te(self, ids, tu, den):
        """Tổng TOÀN phạm vi (kho thật: SUM … GROUP BY tiền tệ, không trần) — cố ý khác cộng dòng."""
        tien = {t["advertiser_id"]: t["tien_te"] for t in self.cac_tk()}
        ra = {}
        for a in ids:
            x = ra.setdefault(tien[a], {})
            for k, v in {"chi": 9_000_000.0, "hien_thi": 900_000, "click": 9_000, "follow": 900,
                         "view_video": 90_000}.items():
                x[k] = x.get(k, 0) + v
        return ra

    def ket_thuc(self, yid, tt, **kw):
        self.ket.append((yid, tt, kw))
        return self.con_luot

    con_luot = True

    def da_nhan_tin(self, yid):
        self.nhan_tin.append(yid)


YC = {"id": 7, "nguoi_hoi": QL, "ben": "hapas", "nen_tang": "tiktok", "tk": None,
      "tu": datetime.date(2026, 10, 12), "den": datetime.date(2026, 10, 18), "trang_thai": "dang_tao",
      "bat_dau_luc": datetime.datetime(2026, 10, 20, 3, 0, tzinfo=datetime.timezone.utc)}
TK = [{"advertiser_id": HAPAS_KOC, "ten": "HAPAS - KOC", "don_vi": "hapas", "nen_tang": "tiktok",
       "tien_te": "VND"},
      {"advertiser_id": MM_2, "ten": "mate made 2", "don_vi": "matemade", "nen_tang": "tiktok",
       "tien_te": "VND"},
      {"advertiser_id": LE, "ten": "LE", "don_vi": "hapas", "nen_tang": "tiktok", "tien_te": "USD"}]
QUYEN = {QL: {"la_quan_tri": True, "ben": {}}, XEM: {"la_quan_tri": False, "ben": {"hapas": "xem"}}}


def _chay(monkeypatch, yc=YC, hong=()):
    import apify_tool as A
    lk = LarkMark(hong)
    monkeypatch.setattr(A.lark, "call", lk.call)
    k = KhoNghe(yc, TK, QUYEN)
    kq = X.xu_ly(dict(yc), ks=k, kho=k, kho_qc=k, lark=lk, log=lambda s: None)
    return kq, k, lk


def test_bo_nghe_dung_ba_tab_khoa_rieng_tu_cap_xem_nhan_tin(monkeypatch):
    kq, k, lk = _chay(monkeypatch)
    gia = lk.gia
    assert kq["trang_thai"] == "xong" and kq["url"].startswith("https://")
    assert gia.tab_ten() == ["Tổng quan", X.TAB_NGAY, X.TAB_CHIEN_DICH, X.TAB_QUANG_CAO]
    assert gia.dau.title == "TikTok Ads · HAPAS · 12/10–18/10/2026"
    # Phạm vi tính lại ở bộ nghe: chỉ tài khoản bên hapas (2 TK × 7 ngày), không MATEMADE.
    ngay = gia.du_lieu(X.TAB_NGAY)
    assert ngay[0][:6] == ["Ngày", "Nền tảng", "Tài khoản", "Mã TK", "Tiền tệ", "Chi"]
    assert len(ngay) == 1 + 14 and MM_2 not in {r[3] for r in ngay[1:]}
    tq = ngay[0]
    assert {"CPM", "CPC", "CTR (%)", "Chi / 1.000 view", "Chi / follow", "Chi / kết quả",
            "ROAS Shop", "Reach"} <= set(tq)
    r1 = dict(zip(tq, ngay[1]))
    assert r1["CPM"] == 10000 and r1["CTR (%)"] == 1.2 and r1["Chi / follow"] == 5000
    o = gia.o(X.TAB_NGAY)
    tong = {r[1]: dict(zip(tq, r)) for r in o if str(r[1]).startswith("TỔNG")}
    assert set(tong) == {"TỔNG USD (cả kỳ)", "TỔNG VND (cả kỳ)"}     # dòng tổng theo tiền tệ
    # Dòng TỔNG + Tổng quan lấy từ tổng TOÀN phạm vi (doc_tong_tien_te), không cộng dòng (M1).
    assert tong["TỔNG VND (cả kỳ)"]["Chi"] == 9_000_000 and tong["TỔNG VND (cả kỳ)"]["CPM"] == 10_000
    cd = gia.du_lieu(X.TAB_CHIEN_DICH)
    assert "Reach" not in cd[0] and dict(zip(cd[0], cd[1]))["Mục tiêu"] == "Lượt xem video"
    assert not str(dict(zip(cd[0], cd[1]))["Tên chiến dịch"]).startswith("=")   # chặn công thức
    assert len(gia.du_lieu(X.TAB_QUANG_CAO)) == 1 + 3
    ghi = " ".join(str(c) for r in gia.o("Tổng quan") for c in r)
    assert "ĐÃ CẮT tab Theo quảng cáo: 3 / 12.000 dòng" in ghi and QL in ghi
    assert "chi nhiều nhất trước" in ghi and "vẫn là tổng ĐỦ cả kỳ" in ghi
    assert "9.000.000" in ghi or 9_000_000 in [c for r in gia.o("Tổng quan") for c in r]
    # Thứ tự: khoá riêng tư TRƯỚC mọi lần ghi số; cấp quyền XEM theo email SAU cùng.
    i_pub, i_ghi, i_mem = gia.thu_tu("/public", "/values_batch_update", "/members")
    assert -1 < i_pub < i_ghi < i_mem
    mem = [b for m, p, q, b in gia.goi if p.endswith("/members")]
    assert mem == [{"member_type": "email", "member_id": QL, "perm": "view"}]
    # Kết thúc + nhắn link.
    (yid, tt, kw), = k.ket
    assert (yid, tt) == (7, "xong") and kw["sheet_url"] == kq["url"] and kw["loi"] is None
    assert kw["bat_dau_luc"] == YC["bat_dau_luc"]                  # đúng lượt đã nhận (L4)
    assert kw["so_dong"] == {"ngay": 14, "chien_dich": 1, "quang_cao": 3, "tong_chien_dich": 1,
                             "tong_quang_cao": 12000}
    (loai, ma, text, uuid), = lk.tin
    assert (loai, ma, uuid) == ("email", QL, "sheet-qc-7") and kq["url"] in text
    assert "đã cắt" in text and k.nhan_tin == [7]


def test_bo_nghe_meta_cung_duong_va_tieu_de(monkeypatch):
    tk = TK + [{"advertiser_id": "act_9", "ten": "HAPAS FB", "don_vi": "hapas", "nen_tang": "meta",
                "tien_te": "VND"}]
    monkeypatch.setattr(globals()["KhoNghe"], "cac_tk", lambda self: list(tk))
    kq, _k, lk = _chay(monkeypatch, {**YC, "nen_tang": "tat_ca"})
    assert kq["trang_thai"] == "xong" and lk.gia.dau.title.startswith("TikTok + Meta Ads · HAPAS")
    kq, _k, lk = _chay(monkeypatch, {**YC, "nen_tang": "meta"})
    assert lk.gia.dau.title.startswith("Meta Ads · HAPAS")
    assert {r[1] for r in lk.gia.du_lieu(X.TAB_NGAY)[1:]} == {"Meta"}


def test_bo_nghe_kiem_lai_quyen_va_pham_vi(monkeypatch):
    kq, k, lk = _chay(monkeypatch, {**YC, "nguoi_hoi": XEM})
    assert kq["trang_thai"] == "loi" and "Chỉ quản trị viên" in k.ket[0][2]["loi"]
    assert lk.gia.bt == {} and "Chưa tạo được" in lk.tin[0][2]
    kq, k, lk = _chay(monkeypatch, {**YC, "tk": "999"})
    assert kq["trang_thai"] == "loi" and "không còn tài khoản" in k.ket[0][2]["loi"]
    assert lk.gia.bt == {}


def test_bo_nghe_cap_quyen_lui_open_id_va_loi(monkeypatch):
    kq, _k, lk = _chay(monkeypatch, hong={"email"})
    mem = [b["member_type"] for m, p, q, b in lk.gia.goi if p.endswith("/members")]
    assert kq["trang_thai"] == "xong" and mem == ["email", "openid"]
    kq, k, lk = _chay(monkeypatch, hong={"email", "openid"})
    assert kq["trang_thai"] == "loi" and k.ket[0][2]["loi"].startswith("Chưa chia sẻ được Sheet")
    assert k.ket[0][2]["sheet_url"] is None if "sheet_url" in k.ket[0][2] else True
    # Nhắn tin hỏng không làm hỏng yêu cầu.
    kq, k, lk = _chay(monkeypatch, hong={"tin"})
    assert kq["trang_thai"] == "xong" and k.nhan_tin == []


def test_bo_nghe_rieng_tu_hong_thi_khong_ghi_so(monkeypatch):
    import apify_tool as A
    lk = LarkMark()
    goc = lk.call

    def call(method, path, query=None, body=None):
        if path.endswith("/public") and method == "GET":
            return {"data": {"permission_public": dict(_RIENG, share_entity="anyone")}}
        return goc(method, path, query, body)
    monkeypatch.setattr(A.lark, "call", call)
    lk.call = call
    k = KhoNghe(YC, TK, QUYEN)
    kq = X.xu_ly(dict(YC), ks=k, kho=k, kho_qc=k, lark=lk, log=lambda s: None)
    assert kq["trang_thai"] == "loi" and "riêng tư" in k.ket[0][2]["loi"]
    assert not [g for g in lk.gia.goi if g[1].endswith("/values_batch_update")]


def test_bo_nghe_loi_bat_ngo_luon_ket_thuc(monkeypatch):
    class Hong(KhoNghe):
        def doc_tong(self, *a):
            raise RuntimeError("statement timeout token=abc")
    import apify_tool as A
    lk = LarkMark()
    monkeypatch.setattr(A.lark, "call", lk.call)
    k = Hong(YC, TK, QUYEN)
    kq = X.xu_ly(dict(YC), ks=k, kho=k, kho_qc=k, lark=lk, log=lambda s: None)
    (_, tt, kw), = k.ket
    assert tt == "loi" and "bấm tạo lại" in kw["loi"] and "RuntimeError" in kw["loi_noi_bo"]
    assert kq["trang_thai"] == "loi"


def test_xu_ly_cho_quet_het_hang_cho(monkeypatch):
    goi = []

    class Hang(KhoNghe):
        def __init__(self, *a):
            super().__init__(*a)
            self.cho = [dict(YC, id=1), dict(YC, id=2)]

        def don_dep(self):
            goi.append("don_dep")

        def nhan(self):
            return self.cho.pop(0) if self.cho else None
    import apify_tool as A
    lk = LarkMark()
    monkeypatch.setattr(A.lark, "call", lk.call)
    k = Hang(YC, TK, QUYEN)
    assert X.xu_ly_cho(ks=k, kho=k, kho_qc=k, lark=lk, log=lambda s: None) == 2
    assert goi == ["don_dep"] and [x[:2] for x in k.ket] == [(1, "xong"), (2, "xong")]


def test_nghe_loi_ket_noi_thi_nghi_roi_thu_lai():
    nghi, log = [], []

    def mo():
        raise RuntimeError("không nối được")
    X.nghe(mo=mo, log=log.append, ngu=nghi.append, vong=2)
    assert nghi == [X.NGHI_LOI, X.NGHI_LOI] and "thử lại" in log[0]


# ───────────────────────────── schema + đơn vị ─────────────────────────────
def test_schema_quyen_rls_trigger():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS yeu_cau_sheet_qc (" in sql
    # RLS: web chỉ dòng của người đăng nhập; mark đọc + sửa; không chính sách UPDATE cho web.
    assert "ALTER TABLE yeu_cau_sheet_qc ENABLE ROW LEVEL SECURITY;" in sql
    assert re.search(r"CREATE POLICY sheet_qc_doc_web ON yeu_cau_sheet_qc FOR SELECT TO lang_nghe_web"
                     r"\s+USING \(nguoi_hoi = current_setting\('lang_nghe.nguoi', true\)\);", sql)
    assert re.search(r"CREATE POLICY sheet_qc_them_web ON yeu_cau_sheet_qc FOR INSERT TO "
                     r"lang_nghe_web\s+WITH CHECK \(nguoi_hoi = current_setting\('lang_nghe.nguoi', "
                     r"true\)\);", sql)
    assert "CREATE POLICY sheet_qc_sua_mark ON yeu_cau_sheet_qc FOR UPDATE TO mark" in sql
    assert not re.search(r"POLICY sheet_qc\w* ON yeu_cau_sheet_qc FOR (UPDATE|DELETE|ALL) TO "
                         r"lang_nghe_web", sql)
    assert KS.GUC == "lang_nghe.nguoi"
    # Quyền theo cột, một giao dịch, SAU "GRANT SELECT ON ALL TABLES" (REVOKE thu lại quyền đó).
    a = sql.index("BEGIN;\nREVOKE ALL ON yeu_cau_sheet_qc FROM mark, lang_nghe_web;")
    assert a > sql.index("GRANT SELECT ON ALL TABLES IN SCHEMA public TO lang_nghe_web;")
    khoi = sql[a:sql.index("COMMIT;", a)]
    ins = re.search(r"GRANT INSERT \(([^)]*)\) ON yeu_cau_sheet_qc TO lang_nghe_web;", khoi).group(1)
    assert {x.strip() for x in ins.split(",")} == {"nguoi_hoi", "ben", "nen_tang", "tk", "tu", "den"}
    doc = re.search(r"GRANT SELECT \(([^)]*)\) ON yeu_cau_sheet_qc TO lang_nghe_web;", khoi).group(1)
    assert "loi_noi_bo" not in doc and "sheet_url" in doc
    upd = re.search(r"GRANT UPDATE \(([^)]*)\) ON yeu_cau_sheet_qc TO mark;", khoi).group(1)
    assert {x.strip() for x in upd.split(",")} == {
        "trang_thai", "tieu_de", "sheet_url", "so_dong", "loi", "loi_noi_bo", "da_nhan_tin",
        "bat_dau_luc", "xong_luc"}
    assert "GRANT SELECT ON yeu_cau_sheet_qc TO mark;" in khoi
    assert not re.search(r"GRANT[^;]*(INSERT|DELETE)[^;]*ON yeu_cau_sheet_qc[^;]*TO mark", sql)
    assert not re.search(r"GRANT[^;]*(UPDATE|DELETE)[^;(]*ON yeu_cau_sheet_qc[^;]*TO lang_nghe_web",
                         sql)
    # Trigger: trạng thái do CSDL đặt + trần; NOTIFY đúng kênh bộ nghe LISTEN.
    chuan = sql[sql.index("CREATE OR REPLACE FUNCTION chuan_yeu_cau_sheet_qc()"):]
    chuan = chuan[:chuan.index("END $fn$;")]
    assert "SECURITY DEFINER SET search_path = public, pg_temp" in chuan
    assert "NEW.trang_thai := 'cho';" in chuan and "NEW.sheet_url := NULL;" in chuan
    assert f">= {KS.TRAN_GIO} THEN" in chuan and f"'{KS.QUA_HAN_PHUT} minutes'" in chuan
    assert f"pg_notify('{KS.KENH}', NEW.id::text)" in sql
    assert "CREATE TRIGGER yeu_cau_sheet_qc_chuan BEFORE INSERT ON yeu_cau_sheet_qc" in sql
    assert "CREATE TRIGGER yeu_cau_sheet_qc_bao AFTER INSERT ON yeu_cau_sheet_qc" in sql
    assert "CHECK (den >= tu AND den - tu < 400)" in sql and QC.XUAT_TOI_DA_NGAY == 400


def test_don_vi_chay_duoi_user_mark():
    s = (GOC / "deploy" / "lang-nghe" / "qc-sheet-nghe.service").read_text(encoding="utf-8")

    def tri(k):
        return [x.split("=", 1)[1] for x in s.splitlines() if x.startswith(k + "=")]
    assert tri("User") == ["mark"] and tri("WorkingDirectory") == ["/opt/mark/app"]
    assert tri("ExecStart") == ["/opt/mark/hermes-agent/venv/bin/python -m xuat_sheet_qc"]
    assert tri("InaccessiblePaths") == ["-/opt/lang-nghe"] and tri("Restart") == ["always"]
    assert not tri("EnvironmentFile")              # config.py của Mark tự nạp .env
    readme = (GOC / "deploy" / "lang-nghe" / "README.md").read_text(encoding="utf-8")
    assert "## 10. Tạo Lark Sheet" in readme and "systemctl enable --now qc-sheet-nghe.service" in readme


@pytest.mark.parametrize("ten", ["chuan_bi", "main", "nghe", "xu_ly_cho"])
def test_bo_nghe_co_du_ham(ten):
    assert callable(getattr(X, ten))


# ───────────────────────────── soát độc lập (20/10/2026) ─────────────────────────────
def test_tab_ngay_cat_giu_ngay_gan_nhat_va_ghi_chu_dung(monkeypatch):
    """M1: tab theo ngày quá trần giữ các NGÀY GẦN NHẤT; ghi chú nói đúng cách cắt; tổng vẫn đủ."""
    def doc(self, ids, tu, den):
        rows = [{"advertiser_id": ids[0], "ngay": den - datetime.timedelta(days=i), "chi": 1.0,
                 "hien_thi": 10} for i in (1, 0)]
        return {"rows": sorted(rows, key=lambda r: r["ngay"]), "tong": 400}
    monkeypatch.setattr(KhoNghe, "doc_theo_ngay", doc)
    kq, _k, lk = _chay(monkeypatch)
    ngay = lk.gia.du_lieu(X.TAB_NGAY)
    assert kq["trang_thai"] == "xong" and len(ngay) == 3
    ghi = " ".join(str(c) for r in lk.gia.o("Tổng quan") for c in r)
    assert "ĐÃ CẮT tab Theo ngày × tài khoản: 2 / 400 dòng" in ghi and "giữ các ngày gần nhất" in ghi
    src = (GOC / "dashboard" / "kho_sheet_qc.py").read_text(encoding="utf-8")
    doc_ngay = src[src.index("def doc_theo_ngay"):src.index("def doc_tong_tien_te")]
    assert "ORDER BY ngay DESC" in doc_ngay
    tong = src[src.index("def doc_tong_tien_te"):src.index("#: Cấp → (bảng")]
    assert "LIMIT" not in tong and "GROUP BY 1" in tong and "JOIN tk_quang_cao" in tong


def test_bo_quan_tri_giua_luot_thi_khong_chia_se(monkeypatch):
    """L3: kiểm quyền lại NGAY trước khi thêm cộng tác viên."""
    lan = {"n": 0}

    def quyen(self, email):
        lan["n"] += 1
        return QUYEN[QL] if lan["n"] == 1 else {"la_quan_tri": False, "ben": {}}
    monkeypatch.setattr(KhoNghe, "quyen_cua", quyen)
    kq, k, lk = _chay(monkeypatch)
    assert kq["trang_thai"] == "loi" and "không còn là quản trị viên" in k.ket[0][2]["loi"]
    assert not [g for g in lk.gia.goi if g[1].endswith("/members")]


def test_dong_da_don_thi_khong_nhan_link(monkeypatch):
    """L4: kết thúc không khớp lượt (đã dọn / nhận lại) → không nhắn link."""
    monkeypatch.setattr(KhoNghe, "con_luot", False)
    kq, k, lk = _chay(monkeypatch)
    assert kq.get("mo_coi") is True and lk.tin == [] and k.nhan_tin == []


def test_link_lark_chi_https_lark(monkeypatch):
    """L5: link chỉ https + máy chủ Lark / Feishu (bộ nghe, trang, CHECK của bảng)."""
    ok = ("https://x.larksuite.com/sheets/a", "https://abc.feishu.cn/sheets/b")
    hong = ("http://x.larksuite.com/s", "https://larksuite.com.evil.io/s", "javascript:alert(1)",
            "https://u:p@x.larksuite.com/s", "https://evil.com/?x=.larksuite.com", "")
    assert all(KS.link_lark(u) == u for u in ok) and not any(KS.link_lark(u) for u in hong)
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    assert r"(larksuite\.com|feishu\.cn)" in sql
    import apify_tool as A
    lk = LarkMark()
    lk.gia.url = "https://evil.example/sheets/x"
    monkeypatch.setattr(A.lark, "call", lk.call)
    k = KhoNghe(YC, TK, QUYEN)
    kq = X.xu_ly(dict(YC), ks=k, kho=k, kho_qc=k, lark=lk, log=lambda s: None)
    assert kq["trang_thai"] == "loi" and "link Sheet hợp lệ" in k.ket[0][2]["loi"]


def test_web_khong_co_luc_nao_doc_loi_noi_bo():
    """L6: thu quyền đọc cả bảng ngay trong giao dịch của GRANT SELECT ON ALL TABLES."""
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    i = sql.index("GRANT SELECT ON ALL TABLES IN SCHEMA public TO lang_nghe_web;")
    assert sql[:i].rstrip().endswith("BEGIN;")
    khoi = sql[i:sql.index("COMMIT;", i)]
    assert "REVOKE SELECT ON yeu_cau_sheet_qc FROM lang_nghe_web;" in khoi


def test_don_vi_theo_mark_khi_tu_len_ma():
    """M2: agent-deploy chỉ khởi động lại `mark` → bộ nghe PartOf mark, cùng trình thông dịch."""
    s = (GOC / "deploy" / "lang-nghe" / "qc-sheet-nghe.service").read_text(encoding="utf-8")
    dong = s.splitlines()
    assert "PartOf=mark.service" in dong
    assert any(x.startswith("After=") and "mark.service" in x.split() for x in dong)
    assert "WantedBy=multi-user.target" in s and "Environment=HOME=/opt/mark" in s
    assert "Environment=PYTHONUTF8=1" in s
    readme = (GOC / "deploy" / "lang-nghe" / "README.md").read_text(encoding="utf-8")
    assert "PartOf=mark.service" in readme and "psycopg.__version__" in readme


def test_js_het_15_phut_mo_lai_nut():
    js = (GOC / "dashboard" / "static" / "qc.js").read_text(encoding="utf-8")
    khoi = js[js.index("Hết 15 phút"):]
    assert "nut.disabled = false" in khoi[:300] and "tải lại trang" in khoi[:300]


def test_bo_nghe_uu_tien_union_id_roi_moi_toi_email(monkeypatch):
    """21/10/2026 chạy thật: email đăng nhập dashboard không trùng email Lark — Lark từ chối
    member_type=email và receive_id email. Có union_id (ghi lúc đăng nhập) thì dùng nó trước."""
    import apify_tool as A
    lk = LarkMark()
    monkeypatch.setattr(A.lark, "call", lk.call)
    k = KhoNghe(YC, TK, QUYEN)
    k.union_id_cua = lambda email: "on_qtv"
    kq = X.xu_ly(dict(YC), ks=k, kho=k, kho_qc=k, lark=lk, log=lambda s: None)
    mem = [(b["member_type"], b["member_id"]) for m, p, q, b in lk.gia.goi if p.endswith("/members")]
    assert kq["trang_thai"] == "xong" and mem == [("unionid", "on_qtv")]
    assert [(t[0], t[1]) for t in lk.tin] == [("union_id", "on_qtv")]
    # union_id bị từ chối → lùi về email như cũ
    lk = LarkMark(hong={"unionid"})
    monkeypatch.setattr(A.lark, "call", lk.call)
    k = KhoNghe(YC, TK, QUYEN)
    k.union_id_cua = lambda email: "on_qtv"
    kq = X.xu_ly(dict(YC), ks=k, kho=k, kho_qc=k, lark=lk, log=lambda s: None)
    mem = [b["member_type"] for m, p, q, b in lk.gia.goi if p.endswith("/members")]
    assert kq["trang_thai"] == "xong" and mem == ["unionid", "email"]


def test_schema_mark_doc_union_id():
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql"
           ).read_text(encoding="utf-8")
    assert "GRANT SELECT (lark_union_id) ON nguoi_xem TO mark;" in sql
