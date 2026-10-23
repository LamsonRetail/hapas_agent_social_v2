"""Mark xuất Lark Sheet quảng cáo (22/10/2026, chủ dự án: "khi hỏi Mark thì Mark vẫn xuất Sheet được").

Soi: tool `xuat_sheet_qc` (`sheet_qc_tool.py`) chỉ thêm dòng `yeu_cau_sheet_qc` nguon = 'mark' cho
CHÍNH người hỏi, trong phạm vi tài khoản người đó đọc được; bộ nghe (`xuat_sheet_qc.py`) không tin
dòng — tính lại phạm vi + quyền tiền từ quyền CSDL lúc dựng (không xem tiền → Sheet không cột tiền;
tài khoản ngoài phạm vi bị bỏ); schema cho role mark THÊM đúng cột + RLS nguon = 'mark', trigger trần
áp cho cả dòng Mark; lời dặn (prompt) đổi đúng chỗ.

Không mạng, không Postgres: kho giả, Lark giả (`test_sheet_qc`).
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

import pytest
from test_dashboard_app import QL, XEM
from test_sheet_qc import TK, YC, KhoNghe, LarkMark, _ket_noi_gia
from test_tiktok_ads import HAPAS_KOC, LE, MM_2

import hoi_dashboard_tool as HD
import sheet_qc_tool as ST
import xuat_sheet_qc as X
from dashboard import kho_sheet_qc as KS
from dashboard import nhap_lieu as NL
from dashboard import quang_cao as QC
from dashboard.kho import LoiDuLieu

GOC = Path(__file__).resolve().parents[1]
VN = QC.VN
BAY = datetime.datetime(2026, 10, 22, 10, 0, tzinfo=VN)
CHUA = "8000000000000000001"                                 # tài khoản chưa gán bên
TK_TOOL = TK + [{"advertiser_id": "act_77", "ten": "HAPAS FB", "don_vi": "hapas", "nen_tang": "meta",
                 "tien_te": "VND"},
                {"advertiser_id": CHUA, "ten": "Chưa gán", "don_vi": None, "nen_tang": "tiktok",
                 "tien_te": "VND"}]
QUYEN = {QL: {"la_quan_tri": True, "ben": {}}, XEM: {"la_quan_tri": False, "ben": {"hapas": "xem"}},
         "hai@hapas.vn": {"la_quan_tri": False, "ben": {"hapas": "quan_ly", "matemade": "xem"}}}


# ───────────────────────────── tool phía Mark ─────────────────────────────
class KhoTool:
    """Như HD.KhoMark cho tool: quyền + tài khoản + `sq_tao` (cùng luật trần của KS.tao)."""

    def __init__(self, hong=None):
        self.rows: list[dict] = []
        self.hong = hong

    def quyen_cua(self, email):
        return QUYEN.get(email)

    def qc_cac_tk(self):
        return list(TK_TOOL)

    def sq_ten_ben(self):
        return {"hapas": "HAPAS", "matemade": "MATEMADE"}

    def sq_tao(self, nguoi_hoi, ben, nen_tang, tk, tu, den, **kw):
        if self.hong:
            raise LoiDuLieu(self.hong)
        r = {"id": len(self.rows) + 1, "nguoi_hoi": nguoi_hoi, "ben": ben, "nen_tang": nen_tang,
             "tk": tk, "tu": tu, "den": den, **kw}
        self.rows.append(r)
        return dict(r)


def _hoi(monkeypatch, ai, args, kho=None):
    monkeypatch.setattr(HD, "email_cua", lambda oid: ai)
    monkeypatch.setattr(ST, "lien_he", lambda oid: {"enterprise_email": ai, "email": "",
                                                    "union_id": "on_x"})
    kho = kho or KhoTool()
    return ST.tra_loi(args, kho, open_id="ou_hoi", bay_gio=BAY), kho


def test_tool_chi_xem_xuat_tai_khoan_ben_minh_dung_dong(monkeypatch):
    ra, kho = _hoi(monkeypatch, XEM, {"tai_khoan": ["hapas koc"], "nen_tang": "tiktok",
                                      "tu": "2026-10-13", "den": "2026-10-19", "tim": "Tết",
                                      "sap": "click", "chieu": "tang"})
    (r,) = kho.rows
    assert r["nguoi_hoi"] == XEM and r["ben"] == "hapas" and r["nen_tang"] == "tiktok"
    assert r["nguon"] == "mark" and r["tk_ds"] == [HAPAS_KOC]
    assert (r["tu"], r["den"]) == (datetime.date(2026, 10, 13), datetime.date(2026, 10, 19))
    assert (r["tim"], r["sap"], r["chieu"], r["cd"]) == ("Tết", "click", "tang", None)
    assert ra["trang_thai"] == "dang_tao" and ra["ma_yeu_cau"] == 1 and ra["co_cot_tien"] is True
    pv = ra["pham_vi"]
    assert pv["ben"] == "HAPAS" and pv["tai_khoan"] == [{"ten": "HAPAS - KOC", "nen_tang": "TikTok"}]
    assert pv["so_ngay"] == 7 and pv["bo_loc_bang"]["xep_theo"] == "Click"
    assert "KHÔNG bịa link" in ra["ghi_chu"]


def test_tool_khong_noi_tai_khoan_la_moi_tai_khoan_cua_ben(monkeypatch):
    ra, kho = _hoi(monkeypatch, XEM, {})
    (r,) = kho.rows
    assert r["ben"] == "hapas" and r["nen_tang"] == "tat_ca" and r["tk_ds"] is None
    assert ra["pham_vi"]["tai_khoan"] == "mọi tài khoản của phạm vi (3)"
    # Mặc định 30 ngày trọn tới hết hôm qua (như dashboard).
    assert r["den"] == datetime.date(2026, 10, 21) and (r["den"] - r["tu"]).days == 29
    # Chọn đủ mọi tài khoản của bên = NULL (như trang).
    _ra, kho = _hoi(monkeypatch, XEM, {"tai_khoan": ["HAPAS - KOC", LE, "HAPAS FB"]})
    assert kho.rows[0]["tk_ds"] is None


def test_tool_tu_choi_tai_khoan_ngoai_pham_vi_khong_them_dong(monkeypatch):
    kho = KhoTool()
    for args, cau in (({"tai_khoan": ["mate made 2"]}, "Không thấy tài khoản “mate made 2”"),
                      ({"tai_khoan": [MM_2]}, "Không thấy tài khoản"),
                      ({"tai_khoan": [CHUA]}, "Không thấy tài khoản"),
                      ({"ben": "matemade"}, "Không có tài khoản quảng cáo nào"),
                      ({"ben": "chua_gan"}, "Không có tài khoản quảng cáo nào")):
        with pytest.raises(NL.LoiNhap, match=cau):
            _hoi(monkeypatch, XEM, args, kho)
    assert kho.rows == []
    # Lời từ chối chỉ nêu tài khoản TRONG phạm vi (không lộ bên khác).
    with pytest.raises(NL.LoiNhap) as e:
        _hoi(monkeypatch, XEM, {"tai_khoan": ["mate made 2"]}, kho)
    assert "HAPAS - KOC" in str(e.value) and "mate made" not in str(e.value).split("đang có:")[1]


def test_tool_nhieu_ben_mo_ho_va_quan_tri(monkeypatch):
    kho = KhoTool()
    with pytest.raises(NL.LoiNhap, match="nhiều bên"):
        _hoi(monkeypatch, "hai@hapas.vn", {}, kho)
    with pytest.raises(NL.LoiNhap, match="mỗi Sheet một bên"):
        _hoi(monkeypatch, "hai@hapas.vn", {"tai_khoan": ["HAPAS - KOC", "mate made 2"]}, kho)
    with pytest.raises(NL.LoiNhap, match="khớp nhiều tài khoản"):
        _hoi(monkeypatch, XEM, {"tai_khoan": ["hapas"]}, kho)
    assert kho.rows == []
    # Quản trị viên: nhiều bên → Tất cả bên; tài khoản chưa gán bên được.
    ra, kho = _hoi(monkeypatch, QL, {"tai_khoan": ["HAPAS - KOC", "mate made 2"]})
    assert kho.rows[0]["ben"] == "tat_ca" and kho.rows[0]["tk_ds"] == [HAPAS_KOC, MM_2]
    _ra, kho = _hoi(monkeypatch, QL, {"tai_khoan": [CHUA]})
    assert kho.rows[0]["ben"] == "chua_gan" and kho.rows[0]["tk_ds"] is None
    _ra, kho = _hoi(monkeypatch, QL, {"ben": "tat_ca"})
    assert kho.rows[0]["ben"] == "tat_ca" and kho.rows[0]["tk_ds"] is None
    # Chỉ một bên có tài khoản Meta → bên đó (không cần "Tất cả bên").
    _ra, kho = _hoi(monkeypatch, QL, {"ben": "tat_ca", "nen_tang": "meta"})
    assert kho.rows[0]["ben"] == "hapas" and kho.rows[0]["nen_tang"] == "meta"


def test_tool_kiem_tham_so_va_tien(monkeypatch):
    kho = KhoTool()
    for args, cau in (({"chien_dich": "Chiến dịch Tết"}, "MÃ chiến dịch"),
                      ({"sap": "doanh_thu"}, "`sap` chỉ nhận"), ({"chieu": "asc"}, "giam hoặc tang"),
                      ({"nen_tang": "youtube"}, "tiktok, meta"), ({"tim": "x" * 101}, "tối đa 100"),
                      ({"tu": "2025-01-01", "den": "2026-10-01"}, "tối đa 400")):
        with pytest.raises(NL.LoiNhap, match=cau):
            _hoi(monkeypatch, XEM, args, kho)
    assert kho.rows == []
    # Luật tiền tương lai (vd "Chỉ xem" không thấy tiền): tool không xếp theo tiền, báo co_cot_tien.
    monkeypatch.setattr(QC, "xem_tien", lambda q, b: bool(q and q.get("la_quan_tri")))
    with pytest.raises(NL.LoiNhap, match="không xếp theo Chi"):
        _hoi(monkeypatch, XEM, {"sap": "chi"}, kho)
    ra, kho = _hoi(monkeypatch, XEM, {})
    assert ra["co_cot_tien"] is False and kho.rows[0]["sap"] == "hien_thi"


def test_tool_cua_hoi_dashboard_va_tran(monkeypatch):
    monkeypatch.setattr(HD, "email_cua", lambda oid: "la@ngoai.vn")
    with pytest.raises(HD.TuChoi, match="chưa có trong danh sách"):
        ST.tra_loi({}, KhoTool(), open_id="ou_hoi", bay_gio=BAY)
    # Không ngữ cảnh chat đã xác thực (nhóm / A2A / lịch…) → từ chối như hoi_dashboard.
    monkeypatch.setattr(HD, "_ngu_canh", lambda: {"channel": "lark", "chat_type": "group"})
    with pytest.raises(HD.TuChoi):
        ST.tra_loi({}, KhoTool(), bay_gio=BAY)
    # Trần / đang có Sheet chờ (LoiDuLieu của KS.tao) → lỗi tool, nguyên câu.
    monkeypatch.setattr(HD, "email_cua", lambda oid: XEM)
    kho = KhoTool(hong=KS.ly_do_chan(1, 0))
    monkeypatch.setattr(HD, "_kho_mac_dinh", lambda: kho)
    monkeypatch.setattr(HD, "nguoi_hoi", lambda: "ou_hoi")
    monkeypatch.setattr(ST, "lien_he", lambda oid: {"enterprise_email": XEM, "email": "",
                                                    "union_id": ""})
    ra = json.loads(ST._handle({}))
    assert "đang có một Sheet đang tạo" in json.dumps(ra, ensure_ascii=False)


def test_kho_sheet_tao_nguon_mark_ghi_cot_nguon(monkeypatch):
    def tra(sql, ts):
        if sql.startswith("INSERT"):
            assert sql.count("%s") == len(ts)
            return [{"id": 5, "n": len(ts), "nguon": ts[-1] if len(ts) == 13 else None}]
        return [{"dang": 0, "gio": 0}]
    goi, kn = _ket_noi_gia(tra)
    monkeypatch.setattr(KS, "ket_noi", kn)
    d = datetime.date(2026, 10, 1)
    # 23/10/2026: + cột ten_cd (lọc tên chiến dịch cấp trang) trước nguon.
    assert KS.tao(XEM, "hapas", "tiktok", None, d, d, nguon="mark") == {"id": 5, "n": 13,
                                                                        "nguon": "mark"}
    ins = [s for s, _ in goi if s.startswith("INSERT")][0]
    assert "sap, chieu, ten_cd, nguon)" in ins
    # Khoá người TRƯỚC khi INSERT (cùng thứ tự khoá với trigger cho cả hai nguồn).
    assert goi[1][0].startswith("SELECT pg_advisory_xact_lock") and goi[1][1] == ["sheet_qc|" + XEM]
    assert KS.tao(XEM, "hapas", "tiktok", None, d, d)["n"] == 12           # web: không cột nguon
    with pytest.raises(ValueError):
        KS.tao(XEM, "hapas", "tiktok", None, d, d, nguon="khac")
    assert "nguon" in KS._COT_MARK and "nguon" not in KS._COT_WEB


def test_kho_mark_chi_mo_ham_them_va_ten_ben():
    assert HD._HAM_KHO_SQ == {"sq_tao": "tao", "sq_ten_ben": "ten_ben"}
    with pytest.raises(AttributeError):
        HD.KhoMark().sq_nhan                                       # noqa: B018
    with pytest.raises(AttributeError):
        HD.KhoMark().sq_ket_thuc                                   # noqa: B018


# ───────────────────────────── bộ nghe: dòng Mark ─────────────────────────────
YC_MARK = {**YC, "nguoi_hoi": XEM, "nguon": "mark"}
_TIEN_TIEU_DE = {"Chi", "CPM", "CPC", "Chi / 1.000 view", "Chi / follow", "Chi / kết quả",
                 "Doanh thu Shop", "ROAS Shop", "Tiền tệ"}


def _chay(monkeypatch, yc, quyen=None):
    import apify_tool as A
    lk = LarkMark()
    monkeypatch.setattr(A.lark, "call", lk.call)
    k = KhoNghe(yc, TK, quyen or {**QUYEN})
    kq = X.xu_ly(dict(yc), ks=k, kho=k, kho_qc=k, lark=lk, log=lambda s: None)
    return kq, k, lk


def test_bo_nghe_dong_mark_chi_xem_duoc_tao_co_tien_theo_luat_hien_tai(monkeypatch):
    """Luật 20/10/2026: người có quyền ở bên (Chỉ xem) biết tiền của bên mình → Sheet đủ cột."""
    kq, k, lk = _chay(monkeypatch, YC_MARK)
    assert kq["trang_thai"] == "xong" and kq["co_tien"] is True
    dau = lk.gia.du_lieu(X.TAB_NGAY)[0]
    assert "Chi" in dau and "CPM" in dau and "Tiền tệ" in dau
    ghi = " ".join(str(c) for r in lk.gia.o("Tổng quan") for c in r)
    assert "Tạo theo yêu cầu gửi Mark" in ghi and "chỉ quản trị viên" not in ghi
    assert [b["member_id"] for m, p, q, b in lk.gia.goi if p.endswith("/members")] == [XEM]


def test_bo_nghe_khong_quyen_tien_thi_khong_cot_tien_nao(monkeypatch):
    """LUẬT CỨNG: không xem tiền → không cột / giá trị tiền ở BẤT KỲ tab nào, kể cả khi dòng xin
    xếp theo chi; bộ nghe tự quyết (không có cột nào trong dòng nói về tiền)."""
    monkeypatch.setattr(QC, "xem_tien", lambda q, b: bool(q and q.get("la_quan_tri")))
    kq, k, lk = _chay(monkeypatch, {**YC_MARK, "sap": "chi"})
    assert kq["trang_thai"] == "xong" and kq["co_tien"] is False
    g = lk.gia
    for tab in (X.TAB_NGAY, X.TAB_CHIEN_DICH, X.TAB_QUANG_CAO):
        dau = g.du_lieu(tab)[0]
        assert not _TIEN_TIEU_DE & set(dau), (tab, dau)
        assert "Hiển thị" in dau and "CTR (%)" in dau
    o = [c for tab in g.tab_ten() for r in g.o(tab) for c in r]
    chi = {100000.0 * i for i in range(1, 8)} | {500000.0, 1000.0, 2000.0, 3000.0, 9_000_000.0,
                                                  18_000_000.0}
    assert not chi & {c for c in o if isinstance(c, (int, float))}
    assert not {"Chi tiêu", "CPM", "Chi / follow"} & {c for c in o if isinstance(c, str)}
    tong = [r for r in g.o(X.TAB_NGAY) if str(r[1]).startswith("TỔNG")]
    assert [r[1] for r in tong] == ["TỔNG (cả kỳ)"]                   # gộp, không theo tiền tệ
    assert k.loc[0][1]["sap"] == "hien_thi"                          # không xếp theo tiền
    ghi = " ".join(str(c) for c in o)
    assert "KHÔNG có cột tiền" in ghi
    (_, _, text, _), = lk.tin
    assert "không có cột tiền" in text


def test_bo_nghe_quan_tri_dong_mark_va_web_giu_nguyen(monkeypatch):
    for yc in ({**YC, "nguon": "mark"}, YC, {**YC, "nguon": "web"}):
        kq, _k, lk = _chay(monkeypatch, yc)
        assert kq["trang_thai"] == "xong" and kq["co_tien"] is True
        assert {"Chi", "CPM", "Tiền tệ"} <= set(lk.gia.du_lieu(X.TAB_NGAY)[0])
    # Dòng web của người không phải quản trị viên: vẫn từ chối như cũ.
    kq, k, lk = _chay(monkeypatch, {**YC, "nguoi_hoi": XEM})
    assert kq["trang_thai"] == "loi" and "Chỉ quản trị viên" in k.ket[0][2]["loi"]


def test_bo_nghe_dong_mark_bo_tai_khoan_ngoai_pham_vi(monkeypatch):
    """Dòng chế tay (tk_ds có tài khoản bên khác, bên tat_ca / chua_gan) không lộ số bên khác."""
    kq, k, lk = _chay(monkeypatch, {**YC_MARK, "tk_ds": [HAPAS_KOC, MM_2]})
    assert kq["trang_thai"] == "xong"
    assert {r[3] for r in lk.gia.du_lieu(X.TAB_NGAY)[1:]} == {HAPAS_KOC}
    ghi = " ".join(str(c) for r in lk.gia.o("Tổng quan") for c in r)
    assert "bỏ 1 tài khoản không thuộc phạm vi" in ghi
    assert "Đã bỏ 1 tài khoản" in lk.tin[0][2]
    for yc in ({**YC_MARK, "ben": "matemade"}, {**YC_MARK, "ben": "tat_ca"},
               {**YC_MARK, "ben": "chua_gan"}, {**YC_MARK, "tk_ds": [MM_2]}):
        kq, k, lk = _chay(monkeypatch, yc)
        assert kq["trang_thai"] == "loi" and lk.gia.bt == {}, yc
    # Người không còn quyền gì → lỗi, không Sheet.
    kq, k, lk = _chay(monkeypatch, {**YC_MARK, "nguoi_hoi": "la@ngoai.vn"})
    assert kq["trang_thai"] == "loi" and "không còn trong danh sách" in k.ket[0][2]["loi"]
    assert lk.gia.bt == {}


def test_bo_nghe_dong_mark_doi_quyen_giua_luot_thi_khong_chia_se(monkeypatch):
    lan = {"n": 0}

    def quyen(self, email):
        lan["n"] += 1
        return QUYEN[XEM] if lan["n"] == 1 else {"la_quan_tri": False, "ben": {"matemade": "xem"}}
    monkeypatch.setattr(KhoNghe, "quyen_cua", quyen)
    kq, k, lk = _chay(monkeypatch, YC_MARK)
    assert kq["trang_thai"] == "loi" and k.ket[0][2]["loi"] == X.CAU_HET_PHAM_VI
    assert not [g for g in lk.gia.goi if g[1].endswith("/members")]


def test_co_tien_khong_xac_dinh_thi_dong():
    assert X.co_tien({"la_quan_tri": True, "ben": {}}, [{"don_vi": None}]) is True
    assert X.co_tien({"la_quan_tri": False, "ben": {"hapas": "xem"}}, [{"don_vi": None}]) is False
    assert X.co_tien(None, [{"don_vi": "hapas"}]) is False
    assert X.co_tien({"la_quan_tri": False, "ben": None}, [{"don_vi": "hapas"}]) is False
    assert X.co_tien({"la_quan_tri": True}, []) is False
    assert X.bo_tien_tong({"VND": {"chi": 5.0, "hien_thi": 2}, "USD": {"chi": 1.0, "hien_thi": 3,
                                                                       "cpm": 9}}) == {
        "": {"hien_thi": 5}}
    assert X.tu_mark({"nguon": "mark"}) and not X.tu_mark({}) and not X.tu_mark({"nguon": "web"})
    # Chốt cuối: dựng bảng không tiền mà còn cột tiền → ném, không bao giờ ghi.
    assert all(not QC.la_tien(m) for m, _, _ in X._cot(True, False))


# ───────────────────────────── schema ─────────────────────────────
def test_schema_mark_them_dong_nguon_rls_va_trigger():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    assert ("ALTER TABLE yeu_cau_sheet_qc ADD COLUMN IF NOT EXISTS nguon TEXT NOT NULL DEFAULT 'web'"
            "\n  CHECK (nguon IN ('web', 'mark'));") in sql
    assert sql.index("ADD COLUMN IF NOT EXISTS nguon") < sql.index(
        "CREATE OR REPLACE FUNCTION chuan_yeu_cau_sheet_qc()")
    assert re.search(r"CREATE POLICY sheet_qc_them_mark ON yeu_cau_sheet_qc FOR INSERT TO mark\s+"
                     r"WITH CHECK \(nguon = 'mark'\);", sql)
    a = sql.index("BEGIN;\nREVOKE ALL ON yeu_cau_sheet_qc FROM mark, lang_nghe_web;")
    khoi = sql[a:sql.index("COMMIT;", a)]
    ins = re.search(r"GRANT INSERT \(([^)]*)\)\s+ON yeu_cau_sheet_qc TO mark;", khoi).group(1)
    assert {x.strip() for x in ins.split(",")} == {"nguoi_hoi", "ben", "nen_tang", "tk", "tk_ds",
                                                    "tu", "den", "tim", "cd", "sap", "chieu",
                                                    "ten_cd", "nguon"}      # ten_cd: 23/10/2026
    assert "GRANT USAGE ON SEQUENCE yeu_cau_sheet_qc_id_seq TO mark;" in khoi
    # Web KHÔNG được ghi cột nguon (luôn mặc định 'web'); mark không DELETE.
    web = re.search(r"GRANT INSERT \(([^)]*)\)\s+ON yeu_cau_sheet_qc TO lang_nghe_web;", khoi).group(1)
    assert "nguon" not in web
    assert not re.search(r"GRANT[^;]*DELETE[^;]*ON yeu_cau_sheet_qc[^;]*TO mark", sql)
    # Trigger BEFORE INSERT không lọc theo role (trần áp cho dòng Mark) và không đặt lại nguon.
    chuan = sql[sql.index("CREATE OR REPLACE FUNCTION chuan_yeu_cau_sheet_qc()"):]
    chuan = chuan[:chuan.index("END $fn$;")]
    assert "current_user" not in chuan and "session_user" not in chuan
    assert "NEW.nguon :=" not in chuan               # đọc nguon (trần tách), không bao giờ đặt lại
    assert chuan.index("hashtext('sheet_qc|' || NEW.nguoi_hoi)") < chuan.index(
        "hashtext('sheet_qc|*')")
    assert "COMMENT ON COLUMN yeu_cau_sheet_qc.nguon IS" in sql
    assert "nguon = mark" in sql[sql.index("COMMENT ON TABLE yeu_cau_sheet_qc"):]


# ───────────────────────────── lời dặn (prompt layer) ─────────────────────────────
def test_loi_dan_mark_xuat_sheet_khi_duoc_doi():
    assert "không tạo ảnh/\"\n    \"sheet" not in HD.GHI_CHU_QC
    assert "sheet/tệp" not in HD.GHI_CHU_QC and "`xuat_sheet_qc`" in HD.GHI_CHU_QC
    assert "BẰNG CHỮ" in HD.GHI_CHU_QC and "`xuat_sheet_qc`" in HD.SCHEMA["description"]
    mo_ta = ST.SCHEMA["description"]
    for cum in ("CHỈ khi người hỏi ĐÒI Sheet", "\"tải về\"", "KHÔNG tạo Sheet", "KHÔNG bịa link",
                "`co_cot_tien` false", "`pham_vi`", "`hoi_dashboard`", "MỘT câu"):
        assert cum in mo_ta, cum
    ky_nang = (GOC / "skills" / "hoi-dashboard-lang-nghe.md").read_text(encoding="utf-8")
    assert "## Số quảng cáo ra Lark Sheet" in ky_nang and "`xuat_sheet_qc`" in ky_nang
    assert "`co_cot_tien` false" in ky_nang
    brain = (GOC / "brain.py").read_text(encoding="utf-8")
    assert "import sheet_qc_tool" in brain and '"xuat_sheet_qc": (' in brain
    assert "SỐ QUẢNG CÁO RA LARK SHEET" in brain


def test_policy_va_bo_cham_eval_xuat_sheet():
    import sys

    import lsr_policy
    assert lsr_policy._MUTATING_EXACT["xuat_sheet_qc"] == "write_data"
    sys.path.insert(0, str(GOC / "evals" / "sow"))
    import kiem
    assert "xuat_sheet_qc" in kiem.TOOL_GHI and kiem.mien_hoi_tien("xuat_sheet_qc", {})


# ───────────────────────────── soát bảo mật 22/10/2026 ─────────────────────────────
class KhoUid(KhoTool):
    def __init__(self, uid):
        super().__init__()
        self.uid = uid

    def union_id_cua(self, email):
        if isinstance(self.uid, Exception):
            raise self.uid
        return self.uid


@pytest.mark.parametrize("lh, uid_kho, duoc", [
    ({"enterprise_email": XEM, "email": "", "union_id": ""}, None, True),        # tổ chức cấp
    ({"enterprise_email": "", "email": XEM, "union_id": "on_1"}, "on_1", True),  # khớp union_id
    ({"enterprise_email": "", "email": XEM, "union_id": "on_1"}, "on_2", False),  # lệch
    ({"enterprise_email": "", "email": XEM, "union_id": "on_1"}, None, False),     # chưa đăng nhập
    ({"enterprise_email": "", "email": XEM, "union_id": ""}, "on_1", False),       # danh bạ thiếu
    ({"enterprise_email": "", "email": XEM, "union_id": "on_1"}, RuntimeError("kho"), False),
    ({"enterprise_email": "khac@hapas.vn", "email": XEM, "union_id": "on_1"}, "on_1", False),
])
def test_danh_tinh_email_tu_khai_phai_khop_union_id(monkeypatch, lh, uid_kho, duoc):
    monkeypatch.setattr(HD, "email_cua", lambda oid: XEM)
    monkeypatch.setattr(ST, "lien_he", lambda oid: dict(lh))
    kho = KhoUid(uid_kho)
    if duoc:
        ST.tra_loi({}, kho, open_id="ou_hoi", bay_gio=BAY)
        assert kho.rows[0]["nguoi_hoi"] == XEM
    else:
        with pytest.raises(HD.TuChoi, match="chưa xác minh được email"):
            ST.tra_loi({}, kho, open_id="ou_hoi", bay_gio=BAY)
        assert kho.rows == []


def test_danh_tinh_danh_ba_loi_thi_dong(monkeypatch):
    monkeypatch.setattr(HD, "email_cua", lambda oid: XEM)

    def hong(oid):
        raise RuntimeError("lark 500")
    monkeypatch.setattr(ST, "lien_he", hong)
    kho = KhoUid("on_1")
    with pytest.raises(HD.TuChoi, match="chưa đối chiếu được danh bạ"):
        ST.tra_loi({}, kho, open_id="ou_hoi", bay_gio=BAY)
    assert kho.rows == [] and "union_id_cua" in HD._HAM_KHO


def test_luoi_tien_theo_khoa_cot_dan_nhan_sai(monkeypatch):
    """Cột tiền dán nhãn sai kiểu (roas_shop kiểu ti_le) + bộ lọc cột hỏng → lưới cuối theo KHOÁ
    chặn, không ghi số nào."""
    monkeypatch.setattr(QC, "HIEN_DOANH_THU", True)
    monkeypatch.setattr(QC, "xem_tien", lambda q, b: bool(q and q.get("la_quan_tri")))
    monkeypatch.setattr(X, "_COT_SO", X._COT_SO + (("roas_shop", "ROAS Shop", "ti_le"),))
    goc = X._cot
    monkeypatch.setattr(X, "_cot", lambda reach, tien=True: [      # lọc chỉ theo kiểu (hỏng)
        c for c in X._COT_SO if (reach or c[0] != "reach") and c[2] != "tien"])
    kq, k, lk = _chay(monkeypatch, YC_MARK)
    assert kq["trang_thai"] == "loi" and "roas_shop" in k.ket[0][2]["loi_noi_bo"]
    assert not [g for g in lk.gia.goi if g[1].endswith("/values_batch_update")]
    with pytest.raises(ValueError, match="roas_shop"):
        X.chot_khong_tien(["hien_thi", "roas_shop"])
    X.chot_khong_tien(["hien_thi", "click", "ctr"])
    # `_cot` thật: bỏ theo khoá LẪN kiểu.
    monkeypatch.setattr(X, "_cot", goc)
    assert "roas_shop" not in [m for m, _, _ in X._cot(True, False)]
    # Tổng quan: mục dán cờ tay sai (không đánh dấu tiền) vẫn bị lưới theo khoá chặn.
    monkeypatch.setattr(X, "_SO_TQ", X._SO_TQ + (("chi_moi_ket_qua", "Chi / KQ", "so", False, ""),))
    kq, k, lk = _chay(monkeypatch, YC_MARK)
    assert kq["trang_thai"] == "loi" and "chi_moi_ket_qua" in k.ket[0][2]["loi_noi_bo"]
    assert not [g for g in lk.gia.goi if g[1].endswith("/values_batch_update")]


def test_tran_gio_mark_tach_khoi_tran_web():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    chuan = sql[sql.index("CREATE OR REPLACE FUNCTION chuan_yeu_cau_sheet_qc()"):]
    chuan = chuan[:chuan.index("END $fn$;")]
    assert KS.TRAN_GIO_MARK == 15 and KS.TRAN_CHUNG_GIO == 30
    assert re.search(r"IF NEW\.nguon = 'mark' THEN\s+IF \(SELECT count\(\*\) FROM "
                     r"public\.yeu_cau_sheet_qc WHERE nguon = 'mark'\s+AND tao_luc > now\(\) - "
                     rf"interval '1 hour'\) >= {KS.TRAN_GIO_MARK} THEN", chuan)
    assert re.search(r"ELSIF \(SELECT count\(\*\) FROM public\.yeu_cau_sheet_qc WHERE nguon <> "
                     rf"'mark'\s+AND tao_luc > now\(\) - interval '1 hour'\) >= {KS.TRAN_CHUNG_GIO} "
                     r"THEN", chuan)
    assert "'yeu_cau_sheet_qc: quá trần Mark mỗi giờ'" in chuan
    assert "CREATE OR REPLACE FUNCTION chuan_yeu_cau_sheet_qc()" in sql     # chạy lại được
    # Trần mỗi người không đổi (đếm mọi nguồn).
    assert f"AND tao_luc > now() - interval '1 hour') >= {KS.TRAN_GIO} THEN" in chuan


def test_kho_sheet_tran_mark_bao_cau_rieng(monkeypatch):
    class CheckViolation(Exception):
        pass

    def tra(sql, ts):
        if sql.startswith("INSERT"):
            raise CheckViolation("yeu_cau_sheet_qc: quá trần Mark mỗi giờ")
        return [{"dang": 0, "gio": 0}]
    _goi, kn = _ket_noi_gia(tra)
    monkeypatch.setattr(KS, "ket_noi", kn)
    d = datetime.date(2026, 10, 1)
    with pytest.raises(LoiDuLieu, match="trần chung của Mark"):
        KS.tao(XEM, "hapas", "tiktok", None, d, d, nguon="mark")
    with pytest.raises(LoiDuLieu, match="trần tạo Sheet chung"):
        KS.tao(XEM, "hapas", "tiktok", None, d, d)
