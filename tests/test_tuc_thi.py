"""Số tức thì của Mark (20/10/2026, chủ dự án: "mark có quyền cao nhất có thể cào real time theo
yêu cầu"). Tool `lay_so_tuc_thi` + bộ nghe `dashboard/nghe_qc.py` + kho `dashboard/kho_tuc_thi.py`.

Canh (gồm các điểm soát độc lập 20/10/2026 H1–H2, M1–M5, L1–L7):
  • PHẠM VI: chỉ tài khoản / dự án bên người hỏi; Chỉ xem được xin; bên khác vô hình; tài khoản
    chưa gán bên chỉ quản trị viên.
  • GIÃN + TRẦN: cùng phạm vi 5 phút dùng lại; trần người/giờ (đếm theo YÊU CẦU, không theo nền
    tảng), hệ thống/giờ, trần giờ của bộ nghe; trần link / kênh / quét mỗi ngày (nguyên tử).
  • LISTEN/NOTIFY (giả): bộ nghe LISTEN rồi xử lý hàng chờ; khoá bận → trả về hàng chờ; cờ nhanh
    mà không chạy được → CHỜ, không quay vòng (H1); bộ nghe chỉ mở lượt nhanh (L4).
  • Lượt hằng ngày chờ khoá, hết giờ → thoát khác 0; khung 06:25–07:30 không lượt nhỏ nào (H2).
  • Độ mới trung thực từng nền tảng: đủ / một phần / chưa (M1).
  • Mark KHÔNG BAO GIỜ thấy token; KHÔNG lệnh ghi nào tới nền tảng quảng cáo; quyền tối thiểu (M5).
  • TIỀN: ngân sách; xác nhận chỉ ở tin nhắn KẾ TIẾP (M2); số quét = đúng mức giữ chỗ (M3).
  • Lời dặn (prompt layer): câu nhắc dashboard → kho; "bây giờ/mới nhất" → số mới; ít hỏi lại.
Không Postgres, không mạng."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

import pytest
from test_dashboard_app import HP_QL, MM_XEM, QL, XEM
from test_meta_ads_dashboard import (
    BAY_MARK,
    MATE,
    NUOC_HOA,
    THAI,
    _app_hai_nen_tang,
)
from test_tiktok_ads import HAPAS_KOC, MM_MKT

import dong_ho_luot
import hoi_dashboard_tool as HD
import tuc_thi_tool as TT
from dashboard import kho_qc as KQ
from dashboard import kho_tuc_thi as KT
from dashboard import meta_ads as MA
from dashboard import nghe_qc as NQ
from dashboard import quang_cao as QC
from dashboard import tiktok_ads as TA

GOC = Path(__file__).resolve().parents[1]
UTC = datetime.UTC
VN = QC.VN
NGAY = datetime.date(2026, 10, 19)


# ───────────────────────────── kho yêu cầu giả ─────────────────────────────
class GiaKhoTT:
    """Bản bộ nhớ của `dashboard.kho_tuc_thi` — cùng tên hàm, cùng luật đếm, trạng thái lúc thêm như
    trigger `chuan_yeu_cau_tuc_thi`, nhật ký như trigger `bao_yeu_cau_tuc_thi`."""

    def __init__(self, bay):
        self.rows: list[dict] = []
        self.nk: list[tuple] = []
        self.bay = bay                      # now() của kho giả (UTC)
        self.link_du_an: dict[str, str] = {}

    def _dem(self, t):
        ds = [r for r in self.rows if r["loai"] == t["loai"] and r["tao_luc"] >= t["tu_luc"]
              and ((r["trang_thai"] in t["trang_thai"]) if t.get("trang_thai")
                   else r["trang_thai"] not in ("tu_choi", "bo_qua"))
              and all(t.get(k) is None or r[k] == t[k]
                      for k in ("nguoi_hoi", "ben", "du_an", "nha_cung_cap"))]
        if t.get("nhom") is not None:
            return len({r["chi_tiet"].get("nhom") or r["id"] for r in ds
                        if r["chi_tiet"].get("nhom") != t["nhom"]})
        return sum(r["so_muc"] for r in ds) if t.get("cong_muc") else len(ds)

    def tao(self, loai, nguoi_hoi, *, ben=None, nha_cung_cap=None, tai_khoan=None, tu=None,
            den=None, du_an=None, so_muc=0, chi_tiet=None, uoc_usd=None, loi=None, tran=None):
        assert loai in KT.LOAI
        ct = dict(chi_tiet or {})
        if isinstance(ct.get("tim"), str):
            ct["tim"] = ct["tim"][:KT.TIM_TOI_DA]
        vuot = None if loi else KT.vuot_tran(self._dem, tran or [], so_muc)
        tt = KT.trang_thai_khi_them(loai, loi or vuot)
        r = {"id": len(self.rows) + 1, "loai": loai, "nguoi_hoi": nguoi_hoi, "ben": ben,
             "nha_cung_cap": nha_cung_cap, "tai_khoan": sorted(set(tai_khoan or ())), "tu": tu,
             "den": den, "du_an": du_an, "so_muc": so_muc, "chi_tiet": ct, "trang_thai": tt,
             "uoc_usd": uoc_usd, "chi_phi_usd": None, "so_dong": None, "so_tk_ok": None,
             "loi": loi or vuot, "tao_luc": self.bay,
             "bat_dau_luc": self.bay if tt == "dang_chay" else None,
             "xong_luc": self.bay if tt == "tu_choi" else None}
        self.rows.append(r)
        self.nk.append((nguoi_hoi, KT.HANH_DONG, f"tuc_thi:{r['id']}", loai, tt))
        return {**r, **({"vuot": vuot} if vuot else {})}

    def doc(self, ids):
        return [dict(r) for r in self.rows if r["id"] in ids]

    def gan_day_qc(self, ncc, phut):
        moc = self.bay - datetime.timedelta(minutes=phut)
        return [dict(r) for r in reversed(self.rows) if r["loai"] == "quang_cao"
                and r["nha_cung_cap"] == ncc and (r["trang_thai"] in ("cho", "dang_chay") or (
                    r["trang_thai"] == "xong" and r["xong_luc"] >= moc))]

    def dem(self, loai, tu_luc, *, nguoi_hoi=None, ben=None, du_an=None, nha_cung_cap=None,
            cong_muc=False, trang_thai=None):
        return self._dem({"loai": loai, "tu_luc": tu_luc, "nguoi_hoi": nguoi_hoi, "ben": ben,
                          "du_an": du_an, "nha_cung_cap": nha_cung_cap, "cong_muc": cong_muc,
                          "trang_thai": trang_thai})

    def cap_nhat(self, yid, trang_thai, *, chi_phi_usd=None, loi=None, chi_tiet_them=None):
        for r in self.rows:
            if r["id"] == yid and r["loai"] != "quang_cao":      # như RLS
                r.update(trang_thai=trang_thai, xong_luc=self.bay)
                r["chi_tiet"].update(chi_tiet_them or {})
                if chi_phi_usd is not None:
                    r["chi_phi_usd"] = chi_phi_usd
                if loi:
                    r["loi"] = loi

    def du_an_cua_link(self, links, khoa=None):
        return [self.link_du_an[x] for x in [*links, *(khoa or [])] if x in self.link_du_an]

    def du_an_cua_kenh(self, dinh):
        return []

    # phía bộ nghe
    def nhan_qc(self, ncc, toi_da=20):
        ra = []
        for r in self.rows:
            if r["loai"] == "quang_cao" and r["nha_cung_cap"] == ncc and r["trang_thai"] == "cho":
                r.update(trang_thai="dang_chay", bat_dau_luc=self.bay)
                ra.append(dict(r))
        return ra[:toi_da]

    def tra_lai(self, ids):
        for r in self.rows:
            if r["id"] in ids and r["trang_thai"] == "dang_chay":
                r.update(trang_thai="cho", bat_dau_luc=None)

    def ket_thuc(self, ids, trang_thai, *, so_dong=None, so_tk_ok=None, loi=None,
                 chi_tiet_them=None):
        for r in self.rows:
            if r["id"] in ids:
                r.update(trang_thai=trang_thai, so_dong=so_dong, so_tk_ok=so_tk_ok, loi=loi,
                         xong_luc=self.bay)
                r["chi_tiet"] = {**r["chi_tiet"], **(chi_tiet_them or {})}

    def don_dep(self, ncc, cho_phut=15, chay_phut=60):
        return 0

    def dem_chay_gio(self, ncc):
        moc = self.bay - datetime.timedelta(hours=1)
        return len({r["bat_dau_luc"] for r in self.rows if r["loai"] == "quang_cao"
                    and r["nha_cung_cap"] == ncc and r["bat_dau_luc"] is not None
                    and r["bat_dau_luc"] >= moc
                    and r["trang_thai"] in ("dang_chay", "xong", "loi")})


class KhoMarkGia:
    """Như HD.KhoMark: kho + kho_qc + kho_tuc_thi (tên phía tool) — và CHỈ những tên đó."""

    def __init__(self, kho, kho_qc, kho_tt):
        self.kho, self.kho_qc, self.kho_tt = kho, kho_qc, kho_tt

    def __getattr__(self, ten):
        if ten in HD._HAM_KHO_TT:
            return getattr(self.kho_tt, HD._HAM_KHO_TT[ten])
        if ten in HD._HAM_KHO_QC:
            return getattr(self.kho_qc, HD._HAM_KHO_QC[ten])
        if ten in HD._HAM_KHO:
            return getattr(self.kho, ten)
        raise AttributeError(ten)


BAY = BAY_MARK.astimezone(UTC)


@pytest.fixture
def h(monkeypatch):
    x = _app_hai_nen_tang()
    x.kho_tt = GiaKhoTT(BAY)
    x.mark = KhoMarkGia(x.kho, x.kho_qc, x.kho_tt)
    for k in ("MARK_TUC_THI", "MARK_TUC_THI_QC_NGUOI_GIO", "MARK_TUC_THI_QC_GIO",
              "QC_TUC_THI_TRAN_GIO", "MARK_TUC_THI_QUET_NGAY"):
        monkeypatch.delenv(k, raising=False)
    TT._XAC_NHAN.clear()
    return x


def _hoi(monkeypatch, h, ai, args, ngu=None, bay_gio=BAY_MARK):
    monkeypatch.setattr(HD, "email_cua", lambda oid: ai)
    return TT.tra_loi(args, h.mark, open_id="ou_hoi", bay_gio=bay_gio,
                      ngu=ngu or (lambda s: None))


def _bo_nghe(h):
    """`ngu` của tool = một nhịp của hai bộ nghe (TikTok + Meta) chạy trên CÙNG kho giả."""
    def ngu(_s):
        NQ.xu_ly_cho("tiktok_ads", h.tdv, h.kho_tt, log=lambda *a: None)
        NQ.xu_ly_cho("meta_ads", h.dv, h.kho_tt, log=lambda *a: None)
    return ngu


def _yc(h, ncc="tiktok_ads", tk=(HAPAS_KOC,)):
    return h.kho_tt.tao("quang_cao", XEM, nha_cung_cap=ncc, tai_khoan=list(tk), tu=NGAY, den=NGAY,
                        so_muc=len(tk))


# ───────────────────────────── quảng cáo: phạm vi + chờ + độ mới ─────────────────────────────
def test_chi_xem_xin_doc_lai_chi_tai_khoan_ben_minh_roi_tra_so_kem_gio(monkeypatch, h):
    r = _hoi(monkeypatch, h, XEM, {"loai": "quang_cao", "so_ngay": 3}, _bo_nghe(h))
    yc = [x for x in h.kho_tt.rows if x["loai"] == "quang_cao"]
    assert {x["nha_cung_cap"] for x in yc} == {"tiktok_ads", "meta_ads"}
    tk = {a for x in yc for a in x["tai_khoan"]}
    assert HAPAS_KOC in tk and NUOC_HOA in tk
    assert not tk & {MM_MKT, MATE, THAI}               # bên khác + chưa gán: vô hình
    assert all(x["trang_thai"] == "xong" and x["nguoi_hoi"] == XEM for x in yc)
    assert all(x["so_tk_ok"] == x["so_muc"] for x in yc)
    assert all(x["tu"] == datetime.date(2026, 10, 17) and x["den"] == NGAY for x in yc)
    cau = r["do_moi"]["cau"]
    assert "TikTok Ads: số cập nhật lúc" in cau and "Meta Ads: số cập nhật lúc" in cau
    assert "đủ" in cau and r["do_moi"]["tam_tinh"] and "tạm tính" in cau
    assert not r["do_moi"]["mot_phan"] and not r["do_moi"]["chua_doc_lai"]
    assert r["quang_cao"]["co"] is True and [b["ben"] for b in r["quang_cao"]["ben"]] == ["hapas"]
    assert "không bao giờ đề nghị" in r["ghi_chu"]
    # Một yêu cầu của người dùng = một nhóm (cả hai dòng nền tảng cùng nhóm).
    assert len({x["chi_tiet"]["nhom"] for x in yc}) == 1
    # Nhật ký (trigger): mỗi dòng một "mark_real_time" với email người hỏi.
    assert [n[:2] for n in h.kho_tt.nk] == [(XEM, "mark_real_time")] * len(yc)


def test_ben_khac_vo_hinh_va_chua_gan_chi_quan_tri(monkeypatch, h):
    _hoi(monkeypatch, h, MM_XEM, {"loai": "quang_cao"}, _bo_nghe(h))
    tk = {a for x in h.kho_tt.rows for a in x["tai_khoan"]}
    assert tk and not tk & {HAPAS_KOC, NUOC_HOA, THAI}
    assert all(h.kho_qc.tk[a]["don_vi"] == "matemade" for a in tk)
    # Chưa gán bên (THAI): Chỉ xem HAPAS tra tên → không đọc lại tài khoản đó.
    h.kho_tt.rows.clear()
    _hoi(monkeypatch, h, XEM, {"loai": "quang_cao", "tim": "thai test"}, _bo_nghe(h))
    assert THAI not in {a for x in h.kho_tt.rows for a in x["tai_khoan"]}
    h.kho_tt.rows.clear()
    _hoi(monkeypatch, h, QL, {"loai": "quang_cao", "tim": "thai test"}, _bo_nghe(h))
    assert {a for x in h.kho_tt.rows for a in x["tai_khoan"]} == {THAI}


def test_quan_ly_ben_cung_duoc_va_khong_quyen_bi_tu_choi(monkeypatch, h):
    r = _hoi(monkeypatch, h, HP_QL, {"loai": "quang_cao", "nen_tang": "meta"}, _bo_nghe(h))
    assert {x["nha_cung_cap"] for x in h.kho_tt.rows} == {"meta_ads"} and r["quang_cao"]["co"]
    with pytest.raises(HD.TuChoi):
        _hoi(monkeypatch, h, "la@ngoai.vn", {"loai": "quang_cao"})


def test_tai_khoan_moi_phan_phoi_hom_nay_cung_duoc_doc_va_tim_bi_cat(monkeypatch, h):
    """L5: không `tim` → mọi tài khoản đang đồng bộ trong phạm vi (kể cả chưa có số 30 ngày)."""
    moi = "7999999999999999999"
    h.kho_qc.tk[moi] = {**h.kho_qc.tk[HAPAS_KOC], "advertiser_id": moi, "ten": "HAPAS - MỚI"}
    _hoi(monkeypatch, h, XEM, {"loai": "quang_cao", "nen_tang": "tiktok"}, _bo_nghe(h))
    assert moi in h.kho_tt.rows[0]["tai_khoan"]
    h.kho_tt.rows.clear()
    monkeypatch.setattr(TT, "CHO_TOI_DA", 0.0)
    _hoi(monkeypatch, h, XEM, {"loai": "quang_cao", "tim": "x" * 500})
    assert all(len(r["chi_tiet"]["tim"]) <= 200 for r in h.kho_tt.rows)


def test_gian_cung_pham_vi_5_phut_dung_lai(monkeypatch, h):
    _hoi(monkeypatch, h, XEM, {"loai": "quang_cao"}, _bo_nghe(h))
    n = len(h.kho_tt.rows)
    r = _hoi(monkeypatch, h, HP_QL, {"loai": "quang_cao"}, _bo_nghe(h))
    assert len(h.kho_tt.rows) == n                      # không yêu cầu mới
    assert all("dung_lai_yeu_cau" in v for v in r["lam_moi"]["nha_cung_cap"].values())
    assert "số cập nhật lúc" in r["do_moi"]["cau"]
    h.kho_tt.bay = BAY + datetime.timedelta(minutes=6)          # hết 5 phút → lượt mới
    _hoi(monkeypatch, h, XEM, {"loai": "quang_cao"}, _bo_nghe(h))
    assert len(h.kho_tt.rows) > n


def test_tran_nguoi_gio_dem_theo_yeu_cau_khong_theo_nen_tang(monkeypatch, h):
    """L5: trần 1 lần/giờ → một yêu cầu cả TikTok + Meta vẫn chạy đủ (một nhóm); yêu cầu SAU bị
    chặn và trả số kho kèm lý do."""
    monkeypatch.setenv("MARK_TUC_THI_QC_NGUOI_GIO", "1")
    r = _hoi(monkeypatch, h, XEM, {"loai": "quang_cao"}, _bo_nghe(h))
    assert {x["trang_thai"] for x in h.kho_tt.rows} == {"xong"} and len(h.kho_tt.rows) == 2
    r = _hoi(monkeypatch, h, XEM, {"loai": "quang_cao", "so_ngay": 2}, _bo_nghe(h))
    assert all("tu_choi" in v and "60 phút" in v["tu_choi"]
               for v in r["lam_moi"]["nha_cung_cap"].values())
    assert [x["trang_thai"] for x in h.kho_tt.rows[2:]] == ["tu_choi", "tu_choi"]
    assert r["quang_cao"]["co"] is True and "chưa đọc lại" in r["do_moi"]["cau"]
    monkeypatch.setenv("MARK_TUC_THI_QC_NGUOI_GIO", "50")
    monkeypatch.setenv("MARK_TUC_THI_QC_GIO", "1")
    r = _hoi(monkeypatch, h, HP_QL, {"loai": "quang_cao", "nen_tang": "tiktok", "so_ngay": 3},
             _bo_nghe(h))
    assert "Cả hệ thống" in r["lam_moi"]["nha_cung_cap"]["tiktok_ads"]["tu_choi"]


def test_cho_qua_han_tra_so_kho_va_noi_ro(monkeypatch, h):
    monkeypatch.setattr(TT, "CHO_TOI_DA", 0.0)
    r = _hoi(monkeypatch, h, XEM, {"loai": "quang_cao"})          # không bộ nghe nào chạy
    assert all(v["trang_thai"] == "cho" for v in r["lam_moi"]["nha_cung_cap"].values())
    assert "hỏi lại sau ít phút" in r["do_moi"]["cau"] and r["quang_cao"]["co"]
    assert set(r["do_moi"]["chua_doc_lai"]) == {"TikTok Ads", "Meta Ads"}


def test_ky_cu_hon_7_ngay_khong_doc_lai(monkeypatch, h):
    r = _hoi(monkeypatch, h, XEM, {"loai": "quang_cao", "tu": "2026-10-01", "den": "2026-10-10"})
    assert not h.kho_tt.rows and "7 ngày" in r["lam_moi"]["ly_do"]


def test_cua_so_tuc_thi_kep_7_ngay():
    hq = datetime.date(2026, 10, 18)
    assert TA.cua_so_tuc_thi(hq, datetime.date(2026, 10, 1), NGAY) == (
        datetime.date(2026, 10, 13), NGAY)
    assert TA.cua_so_tuc_thi(hq, None, None) == (NGAY,) * 2
    assert TA.cua_so_tuc_thi(hq, datetime.date(2026, 10, 1), datetime.date(2026, 10, 5)) is None


# ───────────────────────────── M1: độ mới trung thực ─────────────────────────────
def test_doc_mot_phan_va_khong_doc_duoc_noi_dung_tung_nen_tang(monkeypatch, h):
    moi = "7999999999999999999"

    def meta_hong(ids, tu, den):
        return {"so_dong": 0, "so_tk": 0, "so_tk_yeu_cau": len(ids), "loi": "act_1001: lỗi",
                "tk_doc": [], "tk_hong": {a: "lỗi Graph" for a in ids}}

    def tiktok_thieu(ids, tu, den):
        return {"so_dong": 5, "so_tk": 1, "so_tk_yeu_cau": len(ids), "loi": "1 tài khoản lỗi",
                "tk_doc": [HAPAS_KOC], "tk_hong": {moi: "lỗi TikTok"}}
    h.kho_qc.tk[moi] = {**h.kho_qc.tk[HAPAS_KOC], "advertiser_id": moi, "ten": "HAPAS - MỚI"}
    monkeypatch.setattr(h.dv, "dong_bo_tai_khoan", meta_hong)
    monkeypatch.setattr(h.tdv, "dong_bo_tai_khoan", tiktok_thieu)
    r = _hoi(monkeypatch, h, QL, {"loai": "quang_cao", "ben": "hapas"}, _bo_nghe(h))
    tt = {x["nha_cung_cap"]: x for x in h.kho_tt.rows}
    assert tt["meta_ads"]["trang_thai"] == "loi" and tt["meta_ads"]["so_tk_ok"] == 0
    assert tt["tiktok_ads"]["trang_thai"] == "xong" and tt["tiktok_ads"]["so_tk_ok"] == 1
    assert "một phần" in tt["tiktok_ads"]["loi"]
    cau = r["do_moi"]["cau"]
    assert "TikTok Ads: cập nhật MỘT PHẦN" in cau and "1/2 tài khoản" in cau
    assert "Meta Ads: chưa đọc lại được" in cau and "Số cập nhật lúc" not in cau
    assert r["do_moi"]["mot_phan"] == ["TikTok Ads"]
    assert r["do_moi"]["chua_doc_lai"] == ["Meta Ads"]


def test_ket_luan_bo_nghe_khong_bao_gio_xong_khi_0_tai_khoan():
    assert NQ.ket_luan({"so_tk": 0, "loi": "x"}, 3) == ("loi", "x")
    assert NQ.ket_luan({"so_tk": 0}, 3)[0] == "bo_qua"
    assert NQ.ket_luan({"so_tk": 2, "loi": None}, 3) == ("xong", "một phần: đọc được 2/3 tài khoản")
    assert NQ.ket_luan({"so_tk": 3}, 3) == ("xong", None)


def test_do_moi_so_sanh_bang_datetime_khong_bang_chuoi(monkeypatch, h):
    """L5: 23:59 ngày 18 và 00:05 ngày 19 — chuỗi "HH:MM dd/mm" xếp sai; datetime xếp đúng."""
    som = datetime.datetime(2026, 10, 18, 16, 59, tzinfo=UTC)       # 23:59 18/10 VN
    muon = datetime.datetime(2026, 10, 18, 17, 5, tzinfo=UTC)       # 00:05 19/10 VN
    a = TT.do_moi_ncc({"nha_cung_cap": "tiktok_ads", "trang_thai": "xong", "so_tk_ok": 1,
                       "so_muc": 1, "tai_khoan": ["1"], "xong_luc": som}, ["1"], None,
                      {"la_quan_tri": True})
    b = TT.do_moi_ncc({"nha_cung_cap": "meta_ads", "trang_thai": "xong", "so_tk_ok": 1,
                       "so_muc": 1, "tai_khoan": ["2"], "xong_luc": muon}, ["2"], None,
                      {"la_quan_tri": True})
    assert max(a["luc"], b["luc"]) == muon and "00:05 19/10" in b["cau"]


# ───────────────────────────── bộ nghe: LISTEN/NOTIFY + trần + khoá ─────────────────────────────
class ConnGia:
    def __init__(self, sau_thong_bao=None):
        self.lenh, self.dong, self.lan_cho = [], False, 0
        self.sau = sau_thong_bao

    def execute(self, sql, *a):
        self.lenh.append(sql)

    def notifies(self, *, timeout=None, stop_after=None):
        self.lan_cho += 1
        if self.sau:
            self.sau()
            self.sau = None
        yield type("N", (), {"channel": NQ.KENH, "payload": "tiktok_ads"})()

    def close(self):
        self.dong = True


def test_bo_nghe_listen_roi_xu_ly_yeu_cau_khi_co_thong_bao(h):
    conn = ConnGia(sau_thong_bao=lambda: _yc(h))
    NQ.nghe("tiktok_ads", dv=h.tdv, kho_tt=h.kho_tt, mo=lambda: conn, log=lambda *a: None,
            ngu=lambda s: None, vong=3)
    assert conn.lenh == ["LISTEN qc_tuc_thi"] and conn.lan_cho >= 1 and conn.dong
    r = h.kho_tt.rows[0]
    assert r["trang_thai"] == "xong" and r["so_dong"] > 0 and r["so_tk_ok"] == 1


def test_h1_co_nhanh_ma_khoa_ban_thi_cho_khong_quay_vong(h):
    """H1: cờ nhanh đang chờ + lượt khác giữ khoá → mỗi vòng CHỜ thông báo (không `continue`
    ngay), số lần thử chạy và số kết nối mở có giới hạn."""
    h.kho_qc.yeu_cau_dong_bo(QL, KQ.NCC, kieu="nhanh")
    h.kho_qc.dang_khoa.add(KQ.KHOA_DONG_BO)
    mo, goi, ngu = [], [], []
    goc = h.tdv.dong_bo

    def dem_goi(**kw):
        goi.append(kw)
        return goc(**kw)
    h.tdv.dong_bo = dem_goi
    conn = ConnGia()

    def mo_conn():
        mo.append(1)
        return conn
    NQ.nghe("tiktok_ads", dv=h.tdv, kho_tt=h.kho_tt, mo=mo_conn, log=lambda *a: None,
            ngu=ngu.append, vong=5)
    assert len(mo) == 1 and conn.lan_cho == 5 and len(goi) == 5 and not ngu
    assert all(kw.get("chi_nhanh") for kw in goi)                 # L4
    assert h.kho_qc.doc_ket_noi(KQ.NCC)["yeu_cau_dong_bo_luc"]     # cờ còn nguyên chờ lượt sau


def test_l4_bo_nghe_khong_bao_gio_mo_luot_day_du(h):
    h.kho_qc.yeu_cau_dong_bo(QL, KQ.NCC, kieu="day_du")
    assert NQ.xu_ly_co_nhanh("tiktok_ads", h.tdv) is None        # cờ đầy đủ: để bộ hẹn giờ
    kq = h.tdv.dong_bo(theo_yeu_cau=True, chi_nhanh=True)
    assert kq == {"bo_qua": "không có yêu cầu nhanh đang chờ"}
    k = h.kho_qc.doc_ket_noi(KQ.NCC)
    assert k["yeu_cau_dong_bo_luc"] and k["yeu_cau_kieu"] == "day_du"


def test_bo_nghe_tran_gio_bo_qua_va_khoa_ban_tra_lai(monkeypatch, h):
    monkeypatch.setenv("QC_TUC_THI_TRAN_GIO", "1")
    for _ in range(2):
        _yc(h)
        NQ.xu_ly_cho("tiktok_ads", h.tdv, h.kho_tt, log=lambda *a: None)
        h.kho_tt.bay += datetime.timedelta(seconds=1)
    assert [r["trang_thai"] for r in h.kho_tt.rows] == ["xong", "bo_qua"]
    assert "trần" in h.kho_tt.rows[1]["loi"]
    monkeypatch.setenv("QC_TUC_THI_TRAN_GIO", "50")
    _yc(h)
    h.kho_qc.dang_khoa.add(KQ.KHOA_DONG_BO)
    kq = NQ.xu_ly_cho("tiktok_ads", h.tdv, h.kho_tt, log=lambda *a: None)
    assert kq["ban"] and h.kho_tt.rows[-1]["trang_thai"] == "cho"   # trả về hàng chờ


def test_luot_pham_vi_khong_dung_co_va_moc_the_ket_noi(h):
    truoc = dict(h.kho_qc.doc_ket_noi("meta_ads"))
    kq = h.dv.dong_bo_tai_khoan([NUOC_HOA], NGAY, NGAY)
    assert kq["so_tk"] == 1 and kq["so_tk_yeu_cau"] == 1 and kq["loi"] is None
    sau = h.kho_qc.doc_ket_noi("meta_ads")
    for c in ("dong_bo_bat_dau", "dong_bo_xong", "yeu_cau_dong_bo_luc", "dong_bo_kieu"):
        assert sau.get(c) == truoc.get(c), c


def test_schema_trigger_notify_va_dashboard_cung_notify():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    assert "PERFORM pg_notify('qc_tuc_thi', COALESCE(NEW.nha_cung_cap, ''));" in sql
    assert "CREATE TRIGGER yeu_cau_tuc_thi_bao AFTER INSERT ON yeu_cau_tuc_thi" in sql
    khoi = sql[sql.rfind("DO $mt$", 0, sql.index("CREATE TRIGGER yeu_cau_tuc_thi_bao")):]
    assert "pg_trigger" in khoi.split("END $mt$")[0]                  # chạy lại không tạo trùng
    src = (GOC / "dashboard" / "kho_qc.py").read_text(encoding="utf-8")
    assert "pg_notify('qc_tuc_thi', %s)" in src and NQ.KENH == KT.KENH_BAO == "qc_tuc_thi"


# ───────────────────────────── H2: lượt hằng ngày không bao giờ lặng lẽ mất ─────────────────────────────
def test_h2_luot_hang_ngay_cho_khoa_roi_chay(h):
    h.kho_qc.dang_khoa.add(KQ.KHOA_DONG_BO)
    ngu, log = [], []

    def nha_sau_2_lan(s):
        if s != TA.NHIP_CHO_KHOA:
            return                                           # nghỉ giữa hai lượt gọi nền tảng
        ngu.append(s)
        if len(ngu) == 2:
            h.kho_qc.dang_khoa.discard(KQ.KHOA_DONG_BO)            # lượt nhỏ xong
    h.tdv.ngu, h.tdv.log = nha_sau_2_lan, log.append
    kq = h.tdv.dong_bo(cho_khoa_giay=1800)
    assert len(ngu) == 2 and "ban" not in kq and kq.get("so_dong", 0) > 0
    assert sum("chờ" in x for x in log) == 2


def test_h2_het_gio_cho_khoa_thi_thoat_khac_0(h, capsys):
    h.kho_qc.dang_khoa.add(KQ.KHOA_DONG_BO)
    h.tdv.ngu = lambda s: None
    assert TA.main(["dong-bo", "--khong-bq", "--cho-khoa-phut", "2"], dich_vu=h.tdv) == 3
    assert "thoát 3" in capsys.readouterr().err
    h.dv.ngu = lambda s: None
    h.kho_qc.dang_khoa.add(MA.KHOA_DONG_BO)
    assert MA.main(["dong-bo", "--khong-bq", "--cho-khoa-phut", "1"], dich_vu=h.dv) == 3
    # Bộ hẹn giờ 2 phút / nút: không chờ, không đỏ (như trước).
    h.kho_qc.yeu_cau_dong_bo(QL, KQ.NCC, kieu="nhanh")
    assert TA.main(["dong-bo", "--khong-bq", "--chi-khi-yeu-cau"], dich_vu=h.tdv) == 0


def test_h2_khung_dong_bo_hang_ngay_khong_luot_nho(monkeypatch, h):
    luc = datetime.datetime(2026, 10, 19, 6, 40, tzinfo=VN)
    assert QC.trong_gio_dong_bo(luc) and not QC.trong_gio_dong_bo(BAY_MARK)
    assert not QC.trong_gio_dong_bo(datetime.datetime(2026, 10, 19, 7, 30, tzinfo=VN))
    # Bộ nghe: yêu cầu chờ → bo_qua kèm lý do; cờ nhanh không chạy.
    h.tdv._bay_gio = lambda: luc
    _yc(h)
    kq = NQ.xu_ly_cho("tiktok_ads", h.tdv, h.kho_tt, log=lambda *a: None)
    assert kq["bo_qua"] == QC.CAU_GIO_DONG_BO and h.kho_tt.rows[0]["trang_thai"] == "bo_qua"
    h.kho_qc.yeu_cau_dong_bo(QL, KQ.NCC, kieu="nhanh")
    assert NQ.xu_ly_co_nhanh("tiktok_ads", h.tdv) is None
    assert TA.yeu_cau_trong_gio_dong_bo(h.tdv)
    assert TA.main(["dong-bo", "--khong-bq", "--chi-khi-yeu-cau"], dich_vu=h.tdv) == 0
    assert h.kho_qc.doc_ket_noi(KQ.NCC)["yeu_cau_dong_bo_luc"]   # cờ giữ tới sau 07:30
    # Mark: không xin đọc lại, nói đồng bộ hằng ngày đang chạy, vẫn trả số kho.
    h.kho_tt.rows.clear()
    r = _hoi(monkeypatch, h, XEM, {"loai": "quang_cao"}, bay_gio=luc)
    assert not h.kho_tt.rows and "06:25–07:30" in r["lam_moi"]["ly_do"]
    assert "đang chạy (06:25–07:30" in r["do_moi"]["cau"] and r["quang_cao"]["co"]


def test_n2_don_vi_dong_bo_chi_chay_lai_khi_ma_3_va_bao_loi(monkeypatch):
    """N2: chạy lại CHỈ khi thoát 3 (chờ khoá hết giờ) — không khi lỗi khác / quá 6 giờ / SIGTERM;
    StartLimit phủ lần đầu + 3 lần chạy lại (≤ 30 phút chờ + 10 phút nghỉ mỗi lần); hỏng hẳn →
    OnFailure ghi lỗi lên thẻ kết nối."""
    def tri(s, k):
        return [d.split("=", 1)[1] for d in s.splitlines() if d.startswith(k + "=")]
    for n, ncc in (("tiktok", "tiktok_ads"), ("meta", "meta_ads")):
        s = (GOC / "deploy" / "lang-nghe" / f"{n}-ads-dong-bo.service").read_text(
            encoding="utf-8")
        assert tri(s, "Restart") == ["no"] and tri(s, "RestartForceExitStatus") == ["3"]
        assert tri(s, "RestartPreventExitStatus") == [] and tri(s, "TimeoutStartSec") == ["6h"]
        assert tri(s, "OnFailure") == [f"qc-dong-bo-loi@{ncc}.service"]
        lan = int(tri(s, "StartLimitBurst")[0])
        assert lan == 4 and tri(s, "StartLimitIntervalSec") == ["6h"]
        # lần đầu + 3 lần chạy lại: 4 × 30 phút chờ + 3 × 10 phút nghỉ = 150 phút < 6 giờ.
        assert 4 * 30 + 3 * 10 < 6 * 60
        assert s.index("OnFailure=") < s.index("[Service]")       # thuộc [Unit]
    loi = (GOC / "deploy" / "lang-nghe" / "qc-dong-bo-loi@.service").read_text(encoding="utf-8")
    assert "-m dashboard.nghe_qc %i --bao-loi-dong-bo" in loi and "User=lang_nghe_web" in loi
    ghi = []

    class KhoGia:
        def ghi_trang_thai(self, *a, **k):
            ghi.append((a, k))
    NQ.bao_loi_dong_bo("meta_ads", KhoGia())
    (tt, ly, ncc), k = ghi[0]
    assert tt == "loi" and ncc == "meta_ads" and "meta-ads-dong-bo" in ly and k["con_token"]


# ───────────────────────────── chỉ đọc nền tảng + không token + quyền tối thiểu ─────────────────────────────
def test_khong_lenh_ghi_toi_nen_tang_quang_cao(monkeypatch, h):
    n_tt, n_m = len(h.tt.cong_cu), len(h.gm.goi)
    _hoi(monkeypatch, h, QL, {"loai": "quang_cao", "so_ngay": 7}, _bo_nghe(h))
    cong_cu = {t for t, _ in h.tt.cong_cu[n_tt:]}
    assert cong_cu and cong_cu <= TA.CONG_CU_DOC
    assert all(r.method == "GET" for r in h.gm.goi[n_m:]) and len(h.gm.goi) > n_m
    with pytest.raises(TA.LoiChan):
        TA.kiem_cong_cu("campaign_status_update", {})
    with pytest.raises(MA.LoiChan):
        MA.kiem_url("POST", "https://graph.facebook.com/v26.0/act_1/campaigns")


def test_mark_khong_bao_gio_thay_token(monkeypatch, h):
    r = _hoi(monkeypatch, h, QL, {"loai": "quang_cao"}, _bo_nghe(h))
    s = json.dumps(r, ensure_ascii=False, default=str)
    kn = h.kho_qc.doc_ket_noi("meta_ads")
    assert "token" not in s and kn["access_token_enc"] not in s
    assert "EAAG" not in s and h.tt.access not in s
    for ten in ("doc_ket_noi", "nhan_qc", "ket_thuc"):
        with pytest.raises(AttributeError):
            _ = getattr(HD.KhoMark(), ten)              # cửa Mark không có hàm token / bộ nghe
    src = (GOC / "tuc_thi_tool.py").read_text(encoding="utf-8")
    assert "giai_ma" not in src and "DichVu" not in src and "TIKTOK_KHOA" not in src


def test_m5_quyen_toi_thieu_role_mark():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    sau = sql.split("Soát 20/10/2026 M5: INSERT chỉ các cột yêu cầu")[1]
    assert not re.search(r"GRANT[^;]*ON[^;]*(ket_noi_ngoai|qc_|tk_quang_cao)[^;]*TO mark", sau)
    assert not re.search(r"GRANT[^;]*ON nhat_ky[^;]*TO mark", sql)
    assert "REVOKE INSERT ON nhat_ky FROM mark;" in sql
    assert "REVOKE INSERT, UPDATE ON yeu_cau_tuc_thi FROM mark;" in sql
    ins = re.search(r"GRANT INSERT \(([^)]*)\) ON yeu_cau_tuc_thi TO mark;", sql).group(1)
    for c in ("trang_thai", "bat_dau_luc", "xong_luc", "so_dong", "so_tk_ok", "chi_phi_usd"):
        assert c not in ins, c
    assert not re.search(r"GRANT INSERT ON yeu_cau_tuc_thi TO mark", sql)
    upd = re.search(r"GRANT UPDATE \(([^)]*)\) ON yeu_cau_tuc_thi TO mark;", sql).group(1)
    assert "loai" not in upd and "nguoi_hoi" not in upd and "tai_khoan" not in upd
    assert "FOR UPDATE TO mark\n      USING (loai <> 'quang_cao') WITH CHECK (loai <> 'quang_cao')" \
        in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql and "relrowsecurity" in sql
    ham = sql[sql.index("CREATE OR REPLACE FUNCTION bao_yeu_cau_tuc_thi()"):]
    ham = ham[:ham.index("END $fn$;")]
    assert "SECURITY DEFINER SET search_path = public, pg_temp" in ham
    assert "INSERT INTO public.nhat_ky" in ham and "'mark_real_time'" in ham
    chuan = sql[sql.index("CREATE OR REPLACE FUNCTION chuan_yeu_cau_tuc_thi()"):]
    assert "NEW.trang_thai := CASE WHEN NEW.loi IS NOT NULL THEN 'tu_choi'" in chuan
    assert KT.trang_thai_khi_them("quang_cao", None) == "cho"
    assert KT.trang_thai_khi_them("bai", None) == "dang_chay"
    assert KT.trang_thai_khi_them("quang_cao", "trần") == "tu_choi"


# ───────────────────────────── tiền: ngân sách + xác nhận (M2) ─────────────────────────────
def _hm(monkeypatch, hm):
    import apify_tool as A
    import viec_nen
    monkeypatch.setattr(A, "_han_muc_thang", lambda: hm)
    monkeypatch.setattr(viec_nen, "da_cam_ket", lambda *a: 0.0)


def test_ngan_sach_khong_kiem_duoc_hoac_khong_du_thi_tu_choi(monkeypatch, h):
    args = {"loai": "bai", "link_bai": ["https://www.tiktok.com/@a/video/7400000000000000001"],
            "chi_uoc_tinh": True}
    dong_ho_luot.bat_dau("chat-ns")
    _hm(monkeypatch, None)
    with pytest.raises(HD.TuChoi, match="ngân sách gói Apify"):
        _hoi(monkeypatch, h, XEM, args)
    _hm(monkeypatch, {"dung": 9.9, "tran": 10.0, "con_lai": 0.1})
    with pytest.raises(HD.TuChoi, match="chỉ còn dùng được"):
        _hoi(monkeypatch, h, XEM, args)


def _kenh_gia(monkeypatch):
    import account_tool as AT
    import apify_tool as A
    import chi_phi_tool
    _hm(monkeypatch, {"dung": 1.0, "tran": 10.0, "con_lai": 9.0})
    goi = []
    monkeypatch.setitem(AT._LAY, "tiktok", lambda v, n: goi.append(v) or {
        "x": {"ho_so": {"ten": "x", "tai_khoan": "x", "followers": 10}, "bai": []}})
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {"usd": 0.03, "so_run": 1,
                                                             "cham_tran": 0, "dang_chay": False})
    monkeypatch.setattr(chi_phi_tool, "ghi", lambda **k: {})
    return goi


def test_m2_ma_chi_dung_o_tin_nhan_ke_tiep(monkeypatch, h):
    goi = _kenh_gia(monkeypatch)
    base = {"loai": "kenh", "kenh": ["@hapas.official"]}
    dong_ho_luot.bat_dau("chat-m2")
    with pytest.raises(HD.TuChoi, match="xác nhận chi phí"):
        _hoi(monkeypatch, h, XEM, base)                      # chưa ước tính → không chạy
    r = _hoi(monkeypatch, h, XEM, {**base, "chi_uoc_tinh": True})
    assert r["chi_uoc_tinh"] and "USD" in r["cau_uoc_tinh"] and "gói Apify" in r["cau_uoc_tinh"]
    assert not goi
    ma = r["ma_xac_nhan"]
    with pytest.raises(HD.TuChoi, match="Chạy nhé"):
        _hoi(monkeypatch, h, XEM, {**base, "ma_xac_nhan": ma})   # cùng lượt: chưa ai trả lời
    dong_ho_luot.bat_dau("chat-m2")                              # tin kế tiếp: "ok"
    with pytest.raises(HD.TuChoi, match="không khớp"):
        _hoi(monkeypatch, h, MM_XEM, {**base, "ma_xac_nhan": ma})  # người khác
    with pytest.raises(HD.TuChoi, match="không khớp"):
        _hoi(monkeypatch, h, XEM, {"loai": "kenh", "kenh": ["@khac"], "ma_xac_nhan": ma})
    r = _hoi(monkeypatch, h, XEM, {**base, "ma_xac_nhan": ma})
    assert goi == [["hapas.official"]] and r["kenh"][0]["ho_so"]["followers"] == 10
    assert r["do_moi"]["cau"].startswith("Số công khai lấy lúc")
    row = h.kho_tt.rows[-1]
    assert row["loai"] == "kenh" and row["trang_thai"] == "xong" and row["chi_phi_usd"] == 0.03
    with pytest.raises(HD.TuChoi):                               # mã dùng một lần
        _hoi(monkeypatch, h, XEM, {**base, "ma_xac_nhan": ma})


def test_m2_qua_mot_tin_nhan_thi_ma_het_han(monkeypatch, h):
    goi = _kenh_gia(monkeypatch)
    base = {"loai": "kenh", "kenh": ["@hapas.official"]}
    dong_ho_luot.bat_dau("chat-m2b")
    ma = _hoi(monkeypatch, h, XEM, {**base, "chi_uoc_tinh": True})["ma_xac_nhan"]
    dong_ho_luot.bat_dau("chat-m2b")                  # người dùng hỏi chuyện khác
    dong_ho_luot.bat_dau("chat-m2b")                  # rồi mới "ok"
    with pytest.raises(HD.TuChoi, match="hết hạn"):
        _hoi(monkeypatch, h, XEM, {**base, "ma_xac_nhan": ma})
    assert ma not in TT._XAC_NHAN and not goi
    dong_ho_luot.bat_dau("chat-m2b")
    ma = _hoi(monkeypatch, h, XEM, {**base, "chi_uoc_tinh": True})["ma_xac_nhan"]
    monkeypatch.setattr(TT, "_dong_ho", lambda: 10 ** 9)       # quá 15 phút
    dong_ho_luot.bat_dau("chat-m2b")
    with pytest.raises(HD.TuChoi, match="hết hạn"):
        _hoi(monkeypatch, h, XEM, {**base, "ma_xac_nhan": ma})


def test_ngoai_luot_chat_khong_cap_ma(monkeypatch, h):
    _kenh_gia(monkeypatch)
    dong_ho_luot._STT.set(None)
    with pytest.raises(HD.TuChoi, match="trực tiếp trong chat"):
        _hoi(monkeypatch, h, XEM, {"loai": "kenh", "kenh": ["@ab"], "chi_uoc_tinh": True})


def test_bai_tran_moi_lan_moi_ngay_link_ben_khac_theo_khoa(monkeypatch, h):
    _hm(monkeypatch, {"dung": 1.0, "tran": 10.0, "con_lai": 9.0})
    dong_ho_luot.bat_dau("chat-bai")
    nhieu = [f"https://www.tiktok.com/@a/video/74000000000000000{i:02d}" for i in range(6)]
    with pytest.raises(HD.TuChoi, match="tối đa 5 link"):
        _hoi(monkeypatch, h, XEM, {"loai": "bai", "link_bai": nhieu, "chi_uoc_tinh": True})
    # L1: link khác dạng (tham số, @ khác) nhưng CÙNG khoá bài "tiktok:<id>" → vẫn nhận ra dự án.
    h.kho_tt.link_du_an = {"tiktok:7400000000000000000": "mm_du_an"}
    h.kho.du_an["mm_du_an"] = {**h.kho.du_an["hapas"], "ma": "mm_du_an", "don_vi": "matemade"}
    khac = "https://m.tiktok.com/@b/video/7400000000000000000?is_from_webapp=1"
    with pytest.raises(HD.TuChoi, match="bên bạn không được xem"):
        _hoi(monkeypatch, h, HP_QL, {"loai": "bai", "link_bai": [khac], "chi_uoc_tinh": True})


def test_l3_bai_loi_giua_chung_van_ket_thuc_dong(monkeypatch, h):
    import apify_tool as A
    import chi_so_bai_tool as CSB
    _hm(monkeypatch, {"dung": 1.0, "tran": 10.0, "con_lai": 9.0})
    link = ["https://www.tiktok.com/@a/video/7400000000000000077"]
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("Apify sập")))
    monkeypatch.setitem(CSB._LAY, "tiktok", lambda v: {})
    dong_ho_luot.bat_dau("chat-l3")
    ma = _hoi(monkeypatch, h, XEM, {"loai": "bai", "link_bai": link,
                                    "chi_uoc_tinh": True})["ma_xac_nhan"]
    dong_ho_luot.bat_dau("chat-l3")
    with pytest.raises(RuntimeError):
        _hoi(monkeypatch, h, XEM, {"loai": "bai", "link_bai": link, "ma_xac_nhan": ma})
    assert h.kho_tt.rows[-1]["trang_thai"] == "loi"            # không kẹt dang_chay


# ───────────────────────────── quét theo yêu cầu (M3, M4, L2) ─────────────────────────────
U = {"phan": {}, "tong": 0.8, "tong_uoc": 0.2, "dp_phan": 0.05, "tk_uoc": 0.3, "bl_uoc": 0.2,
     "dp_uoc": 0.0, "ns_apify": 4.0, "hm": {"con_lai": 4}}


def _quet_san(monkeypatch, ke_hoach, u=None):
    import lenh_cung
    import theo_doi
    monkeypatch.setattr(lenh_cung, "_duoc_khong", lambda t: (True, ""))
    monkeypatch.setattr(theo_doi, "ke_hoach", ke_hoach)
    hien = {"u": dict(u or U)}
    monkeypatch.setattr(theo_doi, "uoc_giu_cho", lambda kh, ma=None: dict(hien["u"]))
    monkeypatch.setattr(theo_doi, "_cau_chi_that", lambda ma: "")
    tao = []

    def tao_luot(ma, **k):
        dong = [r for r in TT_KHO["kho"].rows if r["loai"] == "quet"]
        tao.append((ma, k, [r["trang_thai"] for r in dong]))
        if k.get("tran_xac_nhan") is not None and hien["u"]["tong"] > k["tran_xac_nhan"]:
            return {"ok": False, "ma_loi": "vuot_xac_nhan", "cau": "vượt mức đã đồng ý"}
        return {"ok": True, "ma_viec": "v1", "cau": "Đã nhận lượt theo dõi HAPAS (mã v1)",
                "uoc_usd": hien["u"]["tong"]}
    monkeypatch.setattr(theo_doi, "tao_luot", tao_luot)
    return tao, hien


TT_KHO: dict = {}
KH_OK = {"du_an": {"ma": "hapas"}, "nguon": [{"id": 1}, {"id": 2}], "bo_qua": [],
         "con_thang": 3.0, "tran_thang": 5.0, "da_tieu": 2.0}


def test_quet_dang_chay_thi_tu_choi(monkeypatch, h):
    TT_KHO["kho"] = h.kho_tt
    tao, _ = _quet_san(monkeypatch, lambda ma: {"ma_loi": "dang_chay", "loi": "Lượt theo dõi "
                                                "trước của HAPAS còn đang chạy (mã v0)."})
    dong_ho_luot.bat_dau("chat-q0")
    with pytest.raises(HD.TuChoi, match="còn đang chạy"):
        _hoi(monkeypatch, h, XEM, {"loai": "quet", "du_an": "hapas", "chi_uoc_tinh": True})
    assert not tao


def test_m3_m4_uoc_tinh_bang_muc_giu_cho_ngan_sach_du_an_va_buoc_so(monkeypatch, h):
    TT_KHO["kho"] = h.kho_tt
    tao, hien = _quet_san(monkeypatch, lambda ma: dict(KH_OK))
    dong_ho_luot.bat_dau("chat-q1")
    r = _hoi(monkeypatch, h, XEM, {"loai": "quet", "du_an": "hapas", "chi_uoc_tinh": True})
    c = r["cau_uoc_tinh"]
    assert r["uoc_usd"] == 0.8 and "tối đa 0.80 USD" in c                # = uoc_giu_cho tong
    assert "tìm theo từ khoá 0.30" in c and "cào bình luận 0.20" in c
    assert "NGÂN SÁCH THÁNG của dự án HAPAS (còn 3.00/5.00 USD)" in c and not tao
    # Mức giữ chỗ tăng sau lúc đồng ý → tao_luot từ chối, dòng loi, hỏi lại.
    hien["u"] = {**U, "tong": 1.2}
    dong_ho_luot.bat_dau("chat-q1")
    with pytest.raises(HD.TuChoi, match="vượt mức đã đồng ý"):
        _hoi(monkeypatch, h, XEM, {"loai": "quet", "du_an": "hapas",
                                   "ma_xac_nhan": r["ma_xac_nhan"]})
    assert tao[-1][1]["tran_xac_nhan"] == 0.8
    assert tao[-1][2] == ["dang_chay"]                 # L2: dòng ghi TRƯỚC khi tạo việc
    assert h.kho_tt.rows[-1]["trang_thai"] == "loi"


def test_quet_xac_nhan_xong_tran_ngay_va_du_an_khong_ben(monkeypatch, h):
    TT_KHO["kho"] = h.kho_tt
    tao, _ = _quet_san(monkeypatch, lambda ma: dict(KH_OK))
    dong_ho_luot.bat_dau("chat-q2")
    r = _hoi(monkeypatch, h, XEM, {"loai": "quet", "du_an": "hapas", "chi_uoc_tinh": True})
    dong_ho_luot.bat_dau("chat-q2")
    r = _hoi(monkeypatch, h, XEM, {"loai": "quet", "du_an": "hapas",
                                   "ma_xac_nhan": r["ma_xac_nhan"]})
    assert r["ma_viec"] == "v1" and h.kho_tt.rows[-1]["trang_thai"] == "xong"
    assert tao[-1][2] == ["dang_chay"] and tao[-1][1]["tran_xac_nhan"] == 0.8
    assert h.kho_tt.rows[-1]["chi_tiet"]["ma_viec"] == "v1"
    monkeypatch.setenv("MARK_TUC_THI_QUET_NGAY", "1")
    with pytest.raises(HD.TuChoi, match="bên hapas đã mở đủ 1 lượt"):
        _hoi(monkeypatch, h, XEM, {"loai": "quet", "du_an": "hapas", "chi_uoc_tinh": True})
    with pytest.raises(Exception, match="Không có dự án"):
        _hoi(monkeypatch, h, MM_XEM, {"loai": "quet", "du_an": "hapas", "chi_uoc_tinh": True})
    # Dự án chưa có bên: đếm theo CHÍNH dự án, không theo "mọi bên".
    assert KT.khoa_tran({"loai": "quet", "du_an": "x"}) != KT.khoa_tran({"loai": "quet"})
    dem = h.kho_tt._dem({"loai": "quet", "tu_luc": TT._dau_ngay(BAY_MARK), "du_an": "khac",
                         "trang_thai": ("xong", "dang_chay")})
    assert dem == 0


def test_m3_tao_luot_dung_chung_ham_giu_cho_va_tu_choi_khi_vuot(monkeypatch):
    import theo_doi
    monkeypatch.setattr(theo_doi, "_viec_dang_do", lambda ma: None)
    monkeypatch.setattr(theo_doi, "ke_hoach", lambda ma, moi_nguon=False: dict(KH_OK))
    goi = []
    monkeypatch.setattr(theo_doi, "uoc_giu_cho", lambda kh, ma=None: goi.append(ma) or dict(U))
    kq = theo_doi.tao_luot("hapas", tran_xac_nhan=0.5)
    assert goi == ["hapas"] and kq["ok"] is False and kq["ma_loi"] == "vuot_xac_nhan"
    assert "0,80" in kq["cau"] and "0,50" in kq["cau"]


def test_tat_bang_env(monkeypatch, h):
    monkeypatch.setenv("MARK_TUC_THI", "0")
    with pytest.raises(HD.TuChoi, match="đang tắt"):
        _hoi(monkeypatch, h, XEM, {"loai": "quang_cao"})


# ───────────────────────────── lời dặn (prompt layer) ─────────────────────────────
def test_loi_dan_kho_hay_so_moi_it_hoi_lai_hoi_tien():
    mo_ta = TT.SCHEMA["description"]
    for cum in ("phân tích tiêu cực trên dashboard", "`hoi_dashboard`", "\"bây giờ\"",
                "\"mới nhất\"", "\"cào lại\"", "THẬT SỰ không đoán được", "MỘT câu ngắn",
                "Chạy nhé?", "`ma_xac_nhan`", "Quảng cáo miễn phí: gọi luôn", "CHỈ ĐỌC",
                "tin nhắn KẾ TIẾP", "KHÔNG chạy, bỏ mã đó", "`chi_so_bai`", "`social_listen`"):
        assert cum in mo_ta, cum
    assert "`lay_so_tuc_thi`" in HD.SCHEMA["description"]
    ky_nang = (GOC / "skills" / "hoi-dashboard-lang-nghe.md").read_text(encoding="utf-8")
    assert "## Số trong kho hay số mới ngay" in ky_nang and "Chạy nhé?" in ky_nang
    assert "tin nhắn KẾ TIẾP" in ky_nang
    brain = (GOC / "brain.py").read_text(encoding="utf-8")
    assert "SỐ TRONG KHO HAY SỐ MỚI NGAY" in brain and '"lay_so_tuc_thi": (' in brain
    assert "dong_ho_luot.bat_dau(chat_id)" in brain
    persona = (GOC / "persona.md").read_text(encoding="utf-8")
    assert "Mark chỉ ĐỌC số quảng cáo" in persona


def test_policy_va_bo_cham_eval():
    import sys

    import lsr_policy
    assert lsr_policy._MUTATING_EXACT["lay_so_tuc_thi"] == "write_data"
    sys.path.insert(0, str(GOC / "evals" / "sow"))
    import kiem
    assert "lay_so_tuc_thi" in kiem.TOOL_GHI
    assert kiem.mien_hoi_tien("lay_so_tuc_thi", {"loai": "quang_cao"})
    assert not kiem.mien_hoi_tien("lay_so_tuc_thi", {"loai": "quet"})
    ctx = {"metadata": {"tool": ["lay_so_tuc_thi"], "tool_args": [json.dumps(
        {"loai": "quet", "du_an": "hapas"})]}}
    assert kiem.khong_tu_ghi("", ctx)["pass"] is False
    ctx = {"metadata": {"tool": ["lay_so_tuc_thi"], "tool_args": [{"loai": "quang_cao"}]}}
    assert kiem.khong_tu_ghi("", ctx)["pass"] is True
    case = (GOC / "evals" / "sow" / "cases" / "dong_21_so-tuc-thi.yaml").read_text(
        encoding="utf-8")
    for f in ("khong_goi_tool", "goi_tool_tham_so", "chi_uoc_tinh"):
        assert f"kiem.py:{f}" in case and hasattr(kiem, f)
    # L6: định tuyến "cào lại số bài" vs chi_so_bai vs social_listen.
    for ma in ("d21t5", "d21t6", "d21t7"):
        assert f"ma: {ma}" in case


def test_don_vi_systemd_bo_nghe():
    for n, ncc in (("tiktok", "tiktok_ads"), ("meta", "meta_ads")):
        s = (GOC / "deploy" / "lang-nghe" / f"{n}-ads-nghe.service").read_text(encoding="utf-8")
        y = (GOC / "deploy" / "lang-nghe" / f"{n}-ads-yeu-cau.service").read_text(
            encoding="utf-8")
        assert f"-m dashboard.nghe_qc {ncc}" in s and "Restart=always" in s
        assert "User=lang_nghe_web" in s and "MemoryMax=512M" in s
        cung = [d for d in y.splitlines() if re.match(r"^(Protect|Restrict|NoNew|System|Private|"
                                                     r"Capab|Ambient|Lock|UMask|Inaccess)", d)]
        assert cung and all(d in s.splitlines() for d in cung), n


# ───────────────────────────── SQL của kho_tuc_thi (kết nối giả) ─────────────────────────────
class _CGia:
    def __init__(self):
        self.lenh = []

    def execute(self, sql, ts=()):
        self.lenh.append((sql, ts))

        class R:
            rowcount = 0

            def fetchone(self):
                return {"id": 7, "tai_khoan": ["1"], "so_muc": 1, "n": 3}

            def fetchall(self):
                return []
        return R()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_sql_kho_tuc_thi_tham_so_hoa_tran_nguyen_tu(monkeypatch):
    c = _CGia()
    monkeypatch.setattr(KT, "ket_noi", lambda *a, **k: c)
    tran = [{"loai": "quang_cao", "tu_luc": BAY, "nguoi_hoi": XEM, "nhom": "g1", "toi_da": 6,
             "ly_do": "trần người"},
            {"loai": "quang_cao", "tu_luc": BAY, "nha_cung_cap": "tiktok_ads", "toi_da": 3,
             "ly_do": "trần hệ thống"}]
    r = KT.tao("quang_cao", XEM, nha_cung_cap="tiktok_ads", tai_khoan=["2", "1", "1"], tu=NGAY,
               den=NGAY, so_muc=2, chi_tiet={"nhom": "g1", "tim": "y" * 300}, tran=tran)
    lenh = [x[0] for x in c.lenh]
    assert [x for x in lenh if "pg_advisory_xact_lock" in x] == lenh[:2]   # khoá TRƯỚC khi đếm
    assert "count(DISTINCT COALESCE(chi_tiet->>'nhom'" in lenh[2]
    ins, ts = c.lenh[-1]
    assert ins.startswith("INSERT INTO yeu_cau_tuc_thi") and "trang_thai" not in ins.split(
        "VALUES")[0] and "nhat_ky" not in " ".join(lenh)
    assert ["1", "2"] in ts and ts[-1] == "trần hệ thống"         # 3 + 1 > 3 → tu_choi kèm lý do
    assert r["vuot"] == "trần hệ thống"
    assert '"tim": "' + "y" * 200 + '"' in ts[9]
    c.lenh.clear()
    KT.cap_nhat(7, "xong", chi_phi_usd=0.01)
    assert "loai <> 'quang_cao'" in c.lenh[0][0]
    c.lenh.clear()
    KT.nhan_qc("meta_ads")
    assert "FOR UPDATE SKIP LOCKED" in c.lenh[0][0] and c.lenh[0][1] == ("meta_ads", 20)
    c.lenh.clear()
    KT.don_dep("meta_ads")
    assert "OR loai <> 'quang_cao'" in c.lenh[1][0]                # L3: dòng bài/kênh/quét kẹt
    with pytest.raises(ValueError):
        KT.tao("xoa_quang_cao", XEM)


# ───────────────────────────── soát lại 20/10/2026 (N1, L-a…L-e) ─────────────────────────────
def test_n1_lo_gop_hai_yeu_cau_moi_dong_dung_so_cua_minh(monkeypatch, h):
    """N1: hai yêu cầu gộp một lượt; tài khoản của B là đúng tài khoản hỏng → B "chưa", A "đủ"
    — không bao giờ "đủ 10/3"."""
    moi = "7999999999999999999"
    h.kho_qc.tk[moi] = {**h.kho_qc.tk[HAPAS_KOC], "advertiser_id": moi, "ten": "HAPAS - MỚI"}
    goc = h.tdv.dong_bo_tai_khoan

    def hong_moi(ids, tu, den):
        kq = goc([i for i in ids if i != moi], tu, den)
        return {**kq, "tk_hong": {**kq["tk_hong"], moi: "lỗi TikTok"}, "so_tk_yeu_cau": len(ids),
                "loi": "lỗi TikTok"}
    monkeypatch.setattr(h.tdv, "dong_bo_tai_khoan", hong_moi)
    a = _yc(h, tk=(HAPAS_KOC,))
    b = _yc(h, tk=(moi,))
    NQ.xu_ly_cho("tiktok_ads", h.tdv, h.kho_tt, log=lambda *x: None)
    ra, rb = h.kho_tt.doc([a["id"]])[0], h.kho_tt.doc([b["id"]])[0]
    assert ra["trang_thai"] == "xong" and ra["so_tk_ok"] == 1 and ra["chi_tiet"]["tk_doc"] == [
        HAPAS_KOC]
    assert rb["trang_thai"] == "loi" and rb["so_tk_ok"] == 0
    assert rb["chi_tiet"]["tk_hong"] == {moi: "lỗi TikTok"}
    q = {"la_quan_tri": True}
    assert TT.do_moi_ncc(ra, [HAPAS_KOC], None, q)["muc"] == "du"
    x = TT.do_moi_ncc(rb, [moi], None, q)
    assert x["muc"] == "chua" and "lỗi TikTok" in x["cau"]
    # Dòng dùng lại của người khác: chỉ tính tài khoản CỦA người hỏi.
    assert TT.do_moi_ncc({**ra, "tai_khoan": [HAPAS_KOC, moi]}, [moi], None, q)["muc"] == "chua"
    # Đọc được nhiều hơn số xin (dòng cũ hỏng số) → không bao giờ báo "đủ".
    vo_ly = {**ra, "chi_tiet": {}, "tai_khoan": [HAPAS_KOC], "so_tk_ok": 10}
    assert TT.do_moi_ncc(vo_ly, [HAPAS_KOC], None, q)["muc"] == "chua"
    # Dòng xong mà tài khoản của người hỏi hỏng → không dùng lại, xin lượt mới.
    assert TT._dung_lai([{**ra, "tai_khoan": [HAPAS_KOC, moi]}], {moi}, NGAY, NGAY) is None
    assert TT._dung_lai([ra], {HAPAS_KOC}, NGAY, NGAY)["id"] == a["id"]


def test_la_khung_dong_bo_giu_ca_co_day_du(h):
    luc = datetime.datetime(2026, 10, 19, 6, 50, tzinfo=VN)
    h.tdv._bay_gio = lambda: luc
    h.kho_qc.yeu_cau_dong_bo(QL, KQ.NCC, kieu="day_du")
    assert TA.main(["dong-bo", "--khong-bq", "--chi-khi-yeu-cau"], dich_vu=h.tdv) == 0
    k = h.kho_qc.doc_ket_noi(KQ.NCC)
    assert k["yeu_cau_dong_bo_luc"] and k["yeu_cau_kieu"] == "day_du"   # cờ đợi sau 07:30


def test_lb_day_bigquery_sau_luot_bo_nghe_gian_10_phut(monkeypatch):
    class BQ:
        n = 0

        def da_bat(self):
            return True

        def chay(self):
            BQ.n += 1
    gio = {"t": 1000.0}
    monkeypatch.setitem(NQ._BQ, "luc", float("-inf"))
    for _ in range(3):
        NQ.day_bq({"so_dong": 5}, dong_bo_bq=BQ(), dong_ho=lambda: gio["t"])
        gio["t"] += 60
    assert BQ.n == 1                                             # giãn 10 phút
    gio["t"] += NQ.BQ_GIAN_GIAY
    assert NQ.day_bq({"so_dong": 5}, dong_bo_bq=BQ(), dong_ho=lambda: gio["t"]) and BQ.n == 2
    assert not NQ.day_bq({"so_dong": 0}, dong_bo_bq=BQ(), dong_ho=lambda: gio["t"] + 9999)


def test_lc_bo_chat_cu_nhat_va_ky_moi_lam_ma_cu_het_han(monkeypatch, h):
    monkeypatch.setattr(dong_ho_luot, "STT_TOI_DA", 3)
    monkeypatch.setattr(dong_ho_luot, "_STT_CHAT", {})
    for c in ("c1", "c2", "c3"):
        dong_ho_luot.bat_dau(c)
    dong_ho_luot.bat_dau("c1")                     # c1 thành mới nhất
    dong_ho_luot.bat_dau("c4")                     # bỏ c2 (cũ nhất), không xoá cả bảng
    assert list(dong_ho_luot._STT_CHAT) == ["c3", "c1", "c4"]
    assert dong_ho_luot._STT_CHAT["c1"][1] == 2
    # Mã của kỳ cũ: chat bị bỏ rồi quay lại (số thứ tự lại từ 1) không khớp được.
    _kenh_gia(monkeypatch)
    base = {"loai": "kenh", "kenh": ["@hapas.official"]}
    dong_ho_luot.bat_dau("c3")
    ma = _hoi(monkeypatch, h, XEM, {**base, "chi_uoc_tinh": True})["ma_xac_nhan"]
    dong_ho_luot._STT_CHAT.pop("c3")               # bị bỏ / tiến trình làm mới
    dong_ho_luot.bat_dau("c3")
    with pytest.raises(HD.TuChoi, match="hết hạn"):
        _hoi(monkeypatch, h, XEM, {**base, "ma_xac_nhan": ma})
    assert ":" in dong_ho_luot.stt_luot()[1]       # kỳ = mã tiến trình + mã chat


def test_le_tai_khoan_mui_gio_sau_vn_noi_ly_do(monkeypatch, h):
    """L-e: 06:30 ngày 20 giờ VN = 16:30 ngày 19 ở Los Angeles — "hôm nay" giờ VN ở đó chưa bắt đầu
    → không đọc, nói lý do; tài khoản giờ VN vẫn đọc."""
    h.kho_qc.tk[HAPAS_KOC]["mui_gio"] = "America/Los_Angeles"
    luc = datetime.datetime(2026, 10, 20, 9, 0, tzinfo=VN)
    h.tdv._bay_gio = lambda: luc
    kq = h.tdv.dong_bo_tai_khoan([HAPAS_KOC], datetime.date(2026, 10, 20),
                                 datetime.date(2026, 10, 20))
    assert kq["so_tk"] == 0 and "America/Los_Angeles" in kq["tk_hong"][HAPAS_KOC]
    assert "chưa bắt" in kq["tk_hong"][HAPAS_KOC]
    _yc(h)
    h.kho_tt.rows[-1].update(tu=datetime.date(2026, 10, 20), den=datetime.date(2026, 10, 20))
    NQ.xu_ly_cho("tiktok_ads", h.tdv, h.kho_tt, log=lambda *x: None)
    r = h.kho_tt.rows[-1]
    assert r["trang_thai"] == "bo_qua" or r["trang_thai"] == "loi"
    x = TT.do_moi_ncc(r, [HAPAS_KOC], None, {"ben": {"hapas": "xem"}})   # không phải quản trị
    assert "múi giờ America/Los_Angeles" in x["cau"]                  # lý do công khai vẫn hiện


def test_ld_quyen_yeu_cau_tuc_thi_trong_mot_giao_dich():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    a, b = sql.index("BEGIN;\nREVOKE INSERT, UPDATE ON yeu_cau_tuc_thi FROM mark;"), \
        sql.index("GRANT SELECT, UPDATE ON yeu_cau_tuc_thi TO lang_nghe_web;\nCOMMIT;")
    khoi = sql[a:b]
    assert "REVOKE INSERT ON nhat_ky FROM mark;" in khoi and "GRANT INSERT (" in khoi
