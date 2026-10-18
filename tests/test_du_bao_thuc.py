"""Dự báo theo CHI THẬT trên trang Ngân sách (18/10/2026, chủ dự án: "kiểm thử và đo kĩ phần
hiển thị chi phí để ko bị lố so với thực tế gói").

Trước: "Dự báo cả tháng" chỉ gồm NGUỒN (HAPAS ≈ 0,25 USD/lượt) → hụt, trong khi chi thật mỗi lượt
0,60–2,00 USD; "cả tháng nếu mỗi lượt dùng hết" theo giữ chỗ 60 bình luận/bài (8,6 USD/lượt) → lố
~6 lần. Nay: số lượt còn lại × TRUNG VỊ chi thật các lượt gần nhất (+ kiểm độ phủ), và tới lúc
gói Apify đặt lại. Số neo theo 12 lượt THẬT của kho production (luot_quet, xuất 18/10/2026 01:00)
và ảnh chụp gói thật (`test_goi_apify`)."""
from __future__ import annotations

import datetime

import pytest
from test_goi_apify import HAN_MUC_THAT, _anh

import lang_nghe_db as K
import theo_doi as T
from dashboard import chi_phi as CP

VN = datetime.timezone(datetime.timedelta(hours=7))
BAY = datetime.datetime(2026, 10, 18, 1, 0, tzinfo=VN)


def _l(i, bd, kt, usd, tt="xong", so_nguon=0):
    def t(s):
        return datetime.datetime.fromisoformat(f"2026-10-{s}:00+07:00")
    return {"id": i, "du_an": "hapas", "kieu": "theo_doi", "bat_dau": t(bd), "ket_thuc": t(kt),
            "chi_phi_usd": usd, "trang_thai": tt, "so_nguon": so_nguon, "so_nguon_loi": 0,
            "bai_moi": 0, "bai_cap_nhat": 0, "ma_viec": f"t{i}", "loi": None, "ghi_chu": None,
            "lich_id": None}


#: 12 lượt THẬT (luot_quet production, 14–17/10/2026): bắt đầu, kết thúc, chi_phi_usd, trạng thái.
LUOT_THAT = [_l(12, "17T22:26", "17T22:28", 0.0385, so_nguon=1),
             _l(11, "17T12:46", "17T13:08", 0.5983), _l(10, "17T11:37", "17T12:20", 1.4321, so_nguon=9),
             _l(9, "17T00:51", "17T01:49", 1.3810), _l(8, "16T22:53", "16T23:12", 1.8362),
             _l(7, "16T21:51", "16T22:45", 1.3366, so_nguon=9), _l(6, "16T16:50", "16T16:53", 1.5890),
             _l(5, "16T11:45", "16T11:50", 1.9946, "mot_phan", 9),
             _l(4, "16T09:20", "16T09:22", 0.9183), _l(3, "16T09:09", "16T09:15", 1.9842, so_nguon=9),
             _l(2, "15T18:18", "15T18:28", 1.5032), _l(1, "14T23:45", "14T23:48", 0.8271, so_nguon=9)]
#: Lịch hằng ngày 07:00 (lich_quet id 6 production).
LICH_07 = {"id": 6, "du_an": "hapas", "ten": "", "kieu": "hang_ngay",
           "cau_hinh": {"gio": ["07:00"], "thu": []}, "bat": True, "quet_moi_nguon": False,
           "lan_chay_ke": datetime.datetime(2026, 10, 18, 7, 0, tzinfo=VN), "lan_chay_cuoi": None,
           "ket_qua_cuoi": None, "so_lan_chay": 0, "tao_luc": None, "tao_boi": "x", "sua_luc": None,
           "sua_boi": "x"}
DP_CUOI = datetime.datetime(2026, 10, 17, 11, 37, tzinfo=VN)       # kiểm độ phủ trong lượt 10


def test_chi_luot_thuc_tu_12_luot_that():
    t = CP.chi_luot_thuc(LUOT_THAT, BAY)
    # 7 lượt gần nhất ≥ 0,05 USD: lượt 5–11 (lượt 12 = script bù IG 0,0385 bị bỏ).
    assert t["co"] and t["so_luot"] == 7 and t["luot_id"] == [11, 10, 9, 8, 7, 6, 5]
    assert (t["trung_vi"], t["thap"], t["cao"]) == (1.4321, 0.5983, 1.9946)
    # Chưa đủ 3 lượt / lượt cũ hơn 14 ngày / đang chạy: không dùng.
    assert not CP.chi_luot_thuc(LUOT_THAT[:3], BAY)["co"]
    assert CP.chi_luot_thuc(LUOT_THAT, BAY + datetime.timedelta(days=30))["so_luot"] == 0
    dang = [{**LUOT_THAT[1], "trang_thai": "dang_chay", "ket_thuc": None}]
    assert CP.chi_luot_thuc(dang, BAY)["so_luot"] == 0
    chan = CP.chi_luot_thuc(LUOT_THAT[1:5], BAY)                   # 4 lượt: trung vị giữa hai số
    assert chan["trung_vi"] == pytest.approx((1.3810 + 1.4321) / 2, abs=1e-4)


def test_du_bao_thang_theo_chi_that_hapas():
    """HAPAS 18/10 01:00: đã tiêu 15,44 (tháng 10, cả hai tài khoản); lịch 07:00 còn 14 lượt
    (18–31/10) × trung vị 1,4321 = 20,05 + kiểm độ phủ 4 lần × 0,15 = 0,60 → 36,09 > trần 30.
    Trước đó trang báo 15,44 + nguồn ≈ 19,0 "trong trần"."""
    db = CP.du_bao([], 15.44, 30.0, None, BAY)
    dl = CP.du_bao_lich([LICH_07], {"uoc_tk": 0, "uoc_bl": 0, "uoc_web": 0}, [], BAY)
    assert dl["luot_con_lai"] == 14
    dp = CP.du_bao_do_phu({"cau_hinh": {"do_phu": {"bat": True, "tran_usd": 0.15}}}, DP_CUOI, BAY)
    assert (dp["luot_con_lai"], dp["con_lai"]) == (4, 0.6)
    dbt = CP.du_bao_thuc(db, CP.chi_luot_thuc(LUOT_THAT, BAY), dl["luot_con_lai"], dp["con_lai"])
    assert dbt["theo"] == "thuc" and dbt["con_lai"] == pytest.approx(14 * 1.4321 + 0.6, abs=1e-4)
    assert dbt["du_bao_thang"] == pytest.approx(36.0894, abs=1e-4)
    assert dbt["vuot"] and dbt["vuot_usd"] == pytest.approx(6.0894, abs=1e-4)
    assert dbt["nguon_con_lai"] == db["con_lai"] and db.get("theo") is None   # không sửa db
    # Chưa đủ lượt đo: giữ dự báo nguồn, ghi rõ.
    assert CP.du_bao_thuc(db, {"co": False}, 14, 0.6)["theo"] == "nguon"


def test_du_bao_toi_luc_goi_dat_lai_hapas():
    """Gói FREE còn dùng được 5,1181 (10 − 4,5819 − 0,30 dự trữ) tới 07:00 16/11: lịch 07:00 có 29
    lượt (18/10–15/11; lượt 07:00 16/11 thuộc chu kỳ mới) × 1,4321 + kiểm độ phủ 8 × 0,15 = 42,73
    → gói chỉ đủ 3 lượt, lượt 07:00 21/10 hết tiền."""
    g = CP.goi_apify(_anh(), 30.0, BAY)
    het = HAN_MUC_THAT["reset"]
    moc = CP.cac_moc_du_an([LICH_07], BAY, het - datetime.timedelta(microseconds=1))
    assert len(moc) == 29 and moc[0] == datetime.datetime(2026, 10, 18, 7, 0, tzinfo=VN)
    assert moc[-1] == datetime.datetime(2026, 11, 15, 7, 0, tzinfo=VN)
    dp = CP.luot_do_phu(BAY, het, DP_CUOI) * 0.15
    assert dp == pytest.approx(8 * 0.15)
    g = CP.goi_du_bao(g, [{"ten": "HAPAS", "thuc": CP.chi_luot_thuc(LUOT_THAT, BAY), "moc": moc,
                           "dp_usd": dp}], BAY)
    assert g["du_bao_theo"] == "thuc" and g["so_luot_chu_ky"] == 29
    assert g["du_bao_chu_ky"] == pytest.approx(29 * 1.4321 + 1.2, abs=1e-4)
    assert g["vuot_goi"] and g["du_luot"] == 3
    assert g["het_luc"] == datetime.datetime(2026, 10, 21, 7, 0, tzinfo=VN)
    c = g["canh_bao"][0]
    assert c.startswith("Dự báo tới lúc gói đặt lại (16/11): 29 lượt × 1,43 USD")
    assert "42,73 USD > phần Mark dùng được của gói 5,12 USD — gói đủ 3 lượt" in c
    assert "từ lượt 07:00 21/10" in c and "dưới 0,30 USD dự trữ" in c
    # Trần nội bộ 30 > gói 10 vẫn cảnh báo, đứng sau.
    assert any("không có tác dụng thật" in x for x in g["canh_bao"][1:])
    # Chưa đủ lượt đo chi thật: không đoán.
    g2 = CP.goi_du_bao(CP.goi_apify(_anh(), 30.0, BAY), [{"thuc": {"co": False}, "moc": moc}], BAY)
    assert g2["du_bao_theo"] == "chua_du" and "du_luot" not in g2


def test_mark_noi_chi_that_khi_nhan_viec(monkeypatch):
    monkeypatch.setattr(K, "chi_luot_gan", lambda ma, toi_da=20: [dict(x) for x in LUOT_THAT])
    assert T._cau_chi_that("hapas", BAY) == \
        " (thật 7 lượt gần nhất: 0,60–1,99, trung vị 1,43 USD)"
    monkeypatch.setattr(K, "chi_luot_gan", lambda ma, toi_da=20: [])
    assert T._cau_chi_that("hapas", BAY) == ""

    def hong(ma, toi_da=20):
        raise K.LoiKho("không nối được kho")
    monkeypatch.setattr(K, "chi_luot_gan", hong)
    assert T._cau_chi_that("hapas") == ""


# ───────────────────────────── trang Ngân sách ─────────────────────────────
@pytest.fixture
def kho_hapas(monkeypatch):
    from test_dashboard_app import GiaKho

    from dashboard import app as APP
    monkeypatch.setattr(APP, "_bay_gio", lambda: BAY)
    kho = GiaKho()
    kho.du_an["hapas"]["tran_usd_thang"] = 30.0
    kho.luot = [dict(x) for x in LUOT_THAT]
    kho._lich()[6] = dict(LICH_07)
    kho.da_tieu_thang = lambda: {"hapas": 15.44}
    kho.do_phu = [{"luc": DP_CUOI, "hanh_dong": {}}]
    kho.du_an["hapas"]["cau_hinh"] = {"do_phu": {"bat": True, "tran_usd": 0.15}}
    kho.han_muc_apify = lambda: _anh()
    return kho


def test_trang_ngan_sach_du_bao_theo_chi_that_va_goi(kho_hapas):
    from test_dashboard_app import QL, dang_nhap, tao
    _, c, _ = tao(kho_hapas)
    dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    # Dự báo cả tháng theo chi thật: 15,44 + 14 × 1,4321 + 0,60 = 36,09 → vượt trần 30.
    assert "36,09" in t and "Dự báo vượt trần 6,09 USD" in t
    assert "= 14 lượt × 1,43 USD (trung vị chi thật 7 lượt gần nhất, 0,60–1,99)" in t
    assert "+ kiểm độ phủ 0,60" in t
    # Khối gói: dự báo tới lúc đặt lại + số lượt gói còn đủ.
    assert "Dự báo tới lúc đặt lại" in t and "42,73" in t and "gói đủ 3 lượt" in t
    assert "từ lượt 07:00 21/10" in t
    assert "Thật: trung vị <b>1,43</b> USD/lượt" in t and "Mark không tiêu quá <b>2,00</b>" in t
    # "Cả tháng nếu mỗi lượt dùng hết" kẹp ở trần console 2 USD/lượt: ≤ 15,44 + 14 × 2.
    m = __import__("re").search(r'data-o="thang-so">([\d.,]+)<', t)
    assert m and float(m.group(1).replace(".", "").replace(",", ".")) <= 15.44 + 14 * 2.0 + 1e-6
    assert '"tran_luot": 2.0' in t


#: Cấu hình THẬT của dự án HAPAS (du_an production 18/10/2026).
DU_AN_HAPAS = {
    "ma": "hapas", "ten": "HAPAS", "dang_bat": True, "tran_usd_thang": 30.0,
    "tu_khoa": ["hapas", "túi hapas", "ví hapas", "túi xách hapas", "quà tặng hapas",
                "nước hoa hapas", "hapas perfume", "hộp quà hapas", "yêu từ điều nhỏ nhất",
                "yeutudieunhonhat", "hahahahahapas", "hapas.vn", "hapassuperbrandday",
                "quatanghapas", "tuixachhapas", "nuochoahapas", "vihapas", "trangsuchapas",
                "hapasvn", "lammoidieuviyeu", "hapasxthom"],
    "bl_bat": True, "bl_so_bai": 10, "bl_moi_bai": 0, "tk_bat": True, "tk_so_bai": 15,
    "cau_hinh": {"web": {"mien_nha": ["hapas.co"]}, "do_phu": {"bat": True, "tran_usd": 0.15},
                 "tu_khoa": {"web": {"bat": True}, "tiktok": {"bat": True, "so_bai": 500,
                                                               "hashtag": {"bat": True}},
                             "threads": {"bat": True, "so_bai": 300}, "youtube": {"bat": True},
                             "facebook": {"bat": True, "duong2": {"bat": True}},
                             "instagram": {"bat": True}},
                 "binh_luan": {p: {"bat": True} for p in ("tiktok", "threads", "youtube",
                                                          "facebook", "instagram")}}}


def test_lich_quet_kep_tran_console_va_chi_that():
    """Lịch hằng ngày 07:00 của HAPAS: "Mỗi lượt (tối đa)" theo cấu hình > 8 USD (giữ chỗ cào hết
    60 bình luận/bài × 10 bài: FB 1,95 + IG 2,03 + Threads 1,98 + TikTok 0,31 = 6,27 USD) trong
    khi trần console chặn 2 USD/lượt và chi thật trung vị 1,43 — trang Lịch quét kẹp tối đa ở 2 USD,
    hiện số chi thật."""
    from dashboard import lich_quet as LQ
    from dashboard import trang_lich as TL
    bang = CP.bang_cau_hinh(DU_AN_HAPAS)
    assert bang["uoc_bl"] == pytest.approx(6.2673, abs=1e-4)
    goc = CP.uoc_lich(LICH_07, bang, [])["moi_luot"]
    assert goc > 8
    chi = {"thuc": CP.chi_luot_thuc(LUOT_THAT, BAY), "tran_luot": 2.0}
    (x,) = TL.dong_lich([LICH_07], DU_AN_HAPAS, [], BAY, True, "lỗi", chi)
    assert (x["moi_luot"], x["luot_30"], x["usd_30"]) == (2.0, 30, 60.0)
    assert x["usd_30_thuc"] == pytest.approx(30 * 1.4321, abs=1e-4)
    (y,) = TL.dong_lich([LICH_07], DU_AN_HAPAS, [], BAY, True, "lỗi")          # không biết trần
    assert y["moi_luot"] == goc and y["usd_30_thuc"] is None
    tq = TL.tong_quan([LICH_07], DU_AN_HAPAS, [], 15.44, None, BAY, chi)
    assert tq["tong"] == pytest.approx(15.44 + 14 * 2.0)
    assert tq["tong_thuc"] == pytest.approx(15.44 + 14 * 1.4321, abs=1e-4)
    d = LQ.chuan_hoa({"kieu": "hang_ngay", "gio": "07:00", "bat": "1"}, BAY)
    xt = TL.xem_truoc(d, [], DU_AN_HAPAS, [], 15.44, None, BAY, None, chi)
    assert xt["chi_phi"][0]["gia_tri"] == "2,000 USD"
    assert "trần console mỗi lượt" in xt["chi_phi"][0]["phu"]
    assert "thật ≈ 1,43 USD/lượt (trung vị 7 lượt gần nhất)" in xt["chi_phi"][0]["phu"]


def test_ngan_sach_js_kep_tran_moi_luot():
    """ngan_sach.js tính "cả tháng nếu mỗi lượt dùng hết" kẹp ở D.tran_luot × số lượt — cùng
    phép kẹp với máy chủ (Jinja)."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "dashboard" / "static" / "ngan_sach.js"
          ).read_text(encoding="utf-8")
    assert "if (D.tran_luot != null && ngay > 0) toiDa = Math.min(toiDa, D.da_tieu + ngay * " \
           "D.tran_luot);" in js
