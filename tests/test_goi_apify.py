"""Gói Apify trên trang Ngân sách (18/10/2026, chủ dự án: "kiểm thử và đo kĩ phần hiển thị chi phí
để ko bị lố so với thực tế gói").

Trần THẬT là gói Apify của tài khoản (FREE 10 USD/chu kỳ 16/10–15/11), không phải trần tháng dự
án (HAPAS 30 USD): Mark ghi ảnh chụp `GET /v2/users/me/limits` vào `han_muc_apify` (dashboard
không giữ token), trang Ngân sách hiện đã dùng / trần / ngày đặt lại và cảnh báo khi trần nội bộ
lớn hơn trần gói. Số neo theo ảnh chụp THẬT đọc 18/10/2026 01:06 (giờ VN)."""
from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

import apify_tool as A
import lang_nghe_db as K
import quet_lon
import quet_tu_dong as QT
import theo_doi as T
from dashboard import chi_phi as CP

VN = datetime.timezone(datetime.timedelta(hours=7))
UTC = datetime.timezone.utc
GOC = Path(__file__).resolve().parents[1]
#: GET /v2/users/me/limits thật, 18/10/2026 01:06 VN (token trong D:\hapas_agent_social\.env, cũng
#: là token VPS từ 17/10 15:01): chu kỳ 16/10 00:00Z → 15/11 23:59:59.999Z, trần 10, đã dùng 4,5819.
HAN_MUC_THAT = {"dung": 4.581931120015104, "tran": 10.0, "con_lai": 10.0 - 4.581931120015104,
                "reset": datetime.datetime(2026, 11, 16, 0, 0, tzinfo=UTC).astimezone(VN),
                "bat_dau": datetime.datetime(2026, 10, 16, 0, 0, tzinfo=UTC).astimezone(VN)}
LUC = datetime.datetime(2026, 10, 18, 1, 6, tzinfo=VN)


def _anh(**them) -> dict:
    """Dòng `kho.han_muc_apify` như Mark ghi từ `HAN_MUC_THAT`."""
    return {"luc": LUC, "goi": "FREE", "da_dung_usd": 4.5819, "tran_usd": 10.0,
            "chu_ky_tu": HAN_MUC_THAT["bat_dau"], "chu_ky_den": HAN_MUC_THAT["reset"],
            "tran_luot_usd": 2.0, "du_tru_usd": 0.30, "luot_id": 12, "nguon_ghi": "luot",
            **them}


# ───────────────────────────── tính (dashboard/chi_phi.py) ─────────────────────────────
def test_goi_apify_tu_anh_chup_that():
    g = CP.goi_apify(_anh(), 30.0, LUC)
    assert g["co"] and g["goi"] == "FREE" and g["tran"] == 10.0
    assert g["con_lai"] == pytest.approx(5.4181) and g["dung_duoc"] == pytest.approx(5.1181)
    assert g["dat_lai"] == datetime.datetime(2026, 11, 16, 7, 0, tzinfo=VN)   # 07:00 giờ VN
    assert g["ngay_con"] == pytest.approx(29.25, abs=0.01)
    assert g["tran_luot"] == 2.0 and not g["cu"] and not g["qua_chu_ky"]
    # Trần nội bộ 30 USD/tháng > gói 10 USD/chu kỳ: trần nội bộ không có tác dụng thật.
    assert g["noi_bo_vo_hieu"] is True
    assert len(g["canh_bao"]) == 1 and "30,00 USD/tháng lớn hơn trần gói Apify 10,00" in \
        g["canh_bao"][0] and "không có tác dụng thật" in g["canh_bao"][0]
    # Trần nội bộ ≤ gói: không cảnh báo.
    assert CP.goi_apify(_anh(), 8.0, LUC)["canh_bao"] == []


def test_goi_apify_chua_co_cu_va_qua_chu_ky():
    assert CP.goi_apify(None, 30.0, LUC) == {"co": False}
    cu = CP.goi_apify(_anh(), 8.0, LUC + datetime.timedelta(hours=CP.GOI_CU_GIO + 1))
    assert cu["cu"] and "cũ hơn 6 giờ" in cu["canh_bao"][0]
    qua = CP.goi_apify(_anh(), 30.0, datetime.datetime(2026, 11, 16, 8, 0, tzinfo=VN))
    assert qua["qua_chu_ky"] and qua["ngay_con"] == 0
    assert "đã đặt lại lúc 07:00 16/11/2026" in qua["canh_bao"][0] and len(qua["canh_bao"]) == 1


# ───────────────────────────── Mark ghi (theo_doi / quet_tu_dong) ─────────────────────────────
def test_mark_ghi_anh_chup_goi_dung_cot(monkeypatch):
    ghi: list = []
    monkeypatch.setattr(A, "_han_muc_thang", lambda: dict(HAN_MUC_THAT))
    monkeypatch.setattr(A, "_goi_apify", lambda: "FREE")
    monkeypatch.setattr(quet_lon, "tran_usd_nen", lambda: 2.0)
    monkeypatch.setattr(K, "ghi_han_muc", lambda r: ghi.append(r) or 1)
    assert T.ghi_han_muc_goi(12, "luot") is True
    (r,) = ghi
    assert set(r) == set(K._COT_HAN_MUC)
    assert r == {"goi": "FREE", "da_dung_usd": 4.5819, "tran_usd": 10.0,
                 "chu_ky_tu": HAN_MUC_THAT["bat_dau"], "chu_ky_den": HAN_MUC_THAT["reset"],
                 "tran_luot_usd": 2.0, "du_tru_usd": quet_lon._DU_TRU_THANG, "luot_id": 12,
                 "nguon_ghi": "luot"}


def test_mark_ghi_anh_chup_goi_khong_bao_gio_nem(monkeypatch):
    ghi: list = []
    monkeypatch.setattr(K, "ghi_han_muc", lambda r: ghi.append(r) or 1)
    monkeypatch.setattr(A, "_han_muc_thang", lambda: None)          # không hỏi được Apify
    assert T.ghi_han_muc_goi(None, "nhip") is False and ghi == []

    def hong(r):
        raise K.LoiKho("bảng han_muc_apify chưa tạo")
    monkeypatch.setattr(A, "_han_muc_thang", lambda: dict(HAN_MUC_THAT))
    monkeypatch.setattr(A, "_goi_apify", lambda: "")
    monkeypatch.setattr(quet_lon, "tran_usd_nen", lambda: 1 / 0)   # console hỏng: cột NULL
    monkeypatch.setattr(K, "ghi_han_muc", hong)
    assert T.ghi_han_muc_goi(3) is False


def test_cau_nhan_viec_noi_ca_goi():
    """Câu Mark trả lời khi nhận lượt: "ngân sách còn" nói cả gói (trần thật), không chỉ trần dự
    án 30 USD (còn 14,56/30 trong khi gói chỉ đủ ~3 lượt)."""
    assert T._cau_goi(HAN_MUC_THAT) == "; gói Apify còn 5,42/10,00 USD tới 16/11"
    assert T._cau_goi({"con_lai": 0.87}) == "; gói Apify còn 0,87 USD"
    assert T._cau_goi(None) == "" and T._cau_goi({}) == ""


def test_nhip_lich_quet_chup_goi_moi_3_gio(monkeypatch):
    goi: list = []
    luc = [1000.0]
    monkeypatch.setattr(T, "ghi_han_muc_goi", lambda luot=None, nguon="luot": goi.append(nguon))
    monkeypatch.setattr(QT.time, "monotonic", lambda: luc[0])
    monkeypatch.setattr(QT, "_GOI_LUC", {})
    QT._anh_chup_goi()
    luc[0] += QT.GOI_GIO * 3600 - 1
    QT._anh_chup_goi()                              # chưa đủ 3 giờ: không ghi
    luc[0] += 2
    QT._anh_chup_goi()
    assert goi == ["nhip", "nhip"]


# ───────────────────────────── schema + kho ─────────────────────────────
def test_schema_han_muc_apify_cot_quyen_khong_day_bigquery():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    khoi = re.search(r"CREATE TABLE IF NOT EXISTS han_muc_apify \((.*?)\n\);", sql,
                     re.DOTALL).group(1)
    cot = set(re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE))
    assert set(K._COT_HAN_MUC) | {"id", "luc"} == cot
    # Dashboard đọc đúng các cột có thật (kho giả che mất lỗi SQL — so câu SELECT).
    import inspect

    from dashboard import kho as KHO
    sel = inspect.getsource(KHO.han_muc_apify).split("FROM han_muc_apify")[0]
    assert all(c in sel for c in cot - {"id"})
    # Mark chỉ thêm + đọc lại; dashboard đọc (GRANT SELECT ON ALL TABLES).
    assert "GRANT SELECT, INSERT ON han_muc_apify TO mark;" in sql
    assert "GRANT USAGE ON SEQUENCE han_muc_apify_id_seq TO mark;" in sql
    assert not re.search(r"GRANT[^;]*(UPDATE|DELETE)[^;]*ON han_muc_apify[^;]*TO mark", sql)
    from dashboard import dong_bo_bq
    assert "han_muc_apify" not in dong_bo_bq.BANG
    assert "Không đẩy lên BigQuery" in re.search(
        r"COMMENT ON TABLE han_muc_apify IS \$\$(.*?)\$\$;", sql, re.DOTALL).group(1)


# ───────────────────────────── trang Ngân sách + hỏi đáp ─────────────────────────────
@pytest.fixture
def ngay_18(monkeypatch):
    from dashboard import app as APP
    monkeypatch.setattr(APP, "_bay_gio", lambda: LUC)


def test_trang_ngan_sach_hien_goi_apify(ngay_18):
    from test_dashboard_app import XEM, GiaKho, dang_nhap, tao
    kho = GiaKho()
    kho.du_an["hapas"]["tran_usd_thang"] = 30.0
    kho.han_muc_apify = lambda: _anh()
    _, c, _ = tao(kho)
    dang_nhap(c, XEM)
    t = c.get("/ngan-sach").text
    assert 'data-o="goi-apify"' in t and "Gói Apify FREE" in t
    assert "4,58</dd><dd class=\"ns-phu\">/ 10,00 USD trần gói" in t
    assert "5,42</dd>" in t and "Mark dùng được 5,12" in t
    assert ">16/11</dd>" in t and "07:00 · còn 29,2 ngày" in t
    assert "Trần nội bộ 30,00 USD/tháng lớn hơn trần gói Apify 10,00 USD/chu kỳ" in t
    # Kho chưa có bảng (kho giả cũ không có hàm): không có khối, trang vẫn chạy.
    _, c2, _ = tao(GiaKho())
    dang_nhap(c2, XEM)
    assert 'data-o="goi-apify"' not in c2.get("/ngan-sach").text
