"""Ngân sách tháng theo BÊN (25/10/2026, chủ dự án: "chia ngân sách theo từng bên, mỗi dự án có 1
ngân sách riêng").

Ba tầng tiền: gói Apify chung (trần thật) > ngân sách tháng của bên (`don_vi.tran_usd_thang`, chỉ
quản trị viên đặt) > trần tháng dự án (quản lý của bên đặt; tổng trần các dự án của bên không
vượt ngân sách bên). Bài thử: luật thuần `chi_phi.tran_hieu_luc`, SQL kho dashboard (khoá dòng bên
FOR UPDATE + một dòng nhật ký cùng giao dịch, hai luật từ chối), route chỉ quản trị viên, giao diện
trang Ngân sách, và Mark dừng quét khi bên đã tiêu chạm ngân sách bên."""
from __future__ import annotations

import datetime
import re
import types
from pathlib import Path

import pytest

import lang_nghe_db as K
import theo_doi as T
from dashboard import chi_phi as CP
from dashboard import kho as KD
from test_dashboard_app import QL, XEM, GiaKho as GiaKhoWeb, dang_nhap, tao, thong_bao
from test_dashboard_kho import AI, gia  # noqa: F401 — `gia` là fixture
from test_theo_doi import (DU_AN, GiaApify, GiaKho, _bat_tao_viec, _nguon, _tt, _viec,  # noqa: F401
                           mo)

GOC = Path(__file__).resolve().parents[1]
SCHEMA = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
BEN = {"tran": 40.0, "da_tieu": 12.0}


# ───────────────────────────── 1. luật thuần ─────────────────────────────
def test_tran_hieu_luc_ba_tang():
    # Chưa đặt ngân sách bên: như trước 25/10/2026.
    assert CP.tran_hieu_luc(35, None) == 35.0
    assert CP.tran_hieu_luc(35, None, None, 3) == 35.0
    assert CP.tran_hieu_luc(35, None, {"tran": None, "da_tieu": 99}, 3) == 35.0
    assert CP.tran_hieu_luc(35, 20.0) == 20.0
    # Bên còn 40 − 12 = 28: dự án đã tiêu 3 → trần hiệu lực = min(35, 3 + 28) = 31.
    assert CP.tran_hieu_luc(35, None, BEN, 3) == 31.0
    assert CP.tran_chan_boi(35, None, BEN, 3) == "ben"
    # Bên còn rộng: trần dự án giữ.
    assert CP.tran_hieu_luc(10, None, BEN, 3) == 10.0
    assert CP.tran_chan_boi(10, None, BEN, 3) == "du_an"
    assert CP.tran_chan_boi(35, 20.0, {"tran": 100.0, "da_tieu": 0.0}, 3) == "platform"
    # Bên đã tiêu hết (kể cả lố): trần = đã tiêu của dự án → phần còn 0, Mark dừng.
    assert CP.tran_hieu_luc(35, None, {"tran": 40.0, "da_tieu": 41.0}, 7) == 7.0
    assert CP.tran_hieu_luc(35, None, {"tran": 0.0, "da_tieu": 0.0}, 0) == 0.0


def test_du_bao_mang_ben_va_ben_cua():
    bay = datetime.datetime(2026, 10, 15, 12, tzinfo=CP.VN)
    db = CP.du_bao([], 3.0, 35.0, None, bay, BEN)
    assert db["tran"] == 31.0 and db["chan_boi"] == "ben"
    assert db["ben"] == {"tran": 40.0, "da_tieu": 12.0, "con": 28.0}
    assert CP.du_bao([], 3.0, 35.0, None, bay)["ben"] is None
    ns = {"hapas": {"ma": "hapas", "tran": 40.0, "da_tieu": 1.0},
          "matemade": {"ma": "matemade", "tran": None, "da_tieu": 0.0}}
    assert CP.ben_cua({"don_vi": "hapas"}, ns)["tran"] == 40.0
    assert CP.ben_cua({"don_vi": "matemade"}, ns) is None
    assert CP.ben_cua({"don_vi": "khac"}, ns) is None
    assert CP.ben_cua({"don_vi": "hapas"}, None) is None


def test_khoi_cac_ben_muc_va_canh_bao_goi():
    ns = {"hapas": {"ten": "HAPAS", "tran": 40.0, "tong_tran_du_an": 35.0, "so_du_an": 1,
                    "da_tieu": 10.0},
          "matemade": {"ten": "MATEMADE", "tran": 5.0, "tong_tran_du_an": 5.0, "so_du_an": 1,
                       "da_tieu": 4.5},
          "moi": {"ten": "Bên mới", "tran": None, "tong_tran_du_an": 5.0, "so_du_an": 1,
                  "da_tieu": 0.0}}
    khoi = [({"don_vi": "hapas"}, {"du_bao": {"du_bao_thang": 45.0}}),
            ({"don_vi": "matemade"}, {"du_bao": {"du_bao_thang": 4.6}})]
    kq = CP.ngan_sach_cac_ben(ns, khoi, {"co": True, "tran": 10.0})
    theo = {x["ma"]: x for x in kq["ben"]}
    assert [x["ma"] for x in kq["ben"]] == ["moi", "hapas", "matemade"]       # theo tên
    assert theo["hapas"]["muc"] == "vuot" and theo["hapas"]["con_trong"] == 5.0
    assert theo["hapas"]["pt"] == 25.0 and theo["hapas"]["pt_du_bao"] == 100.0
    assert theo["matemade"]["muc"] == "gan"                                   # ≥ 85 %
    assert theo["moi"]["muc"] == "chua_dat" and theo["moi"]["pt"] is None
    assert kq["tong_ben"] == 45.0 and kq["tran_goi"] == 10.0 and kq["vuot_goi"] is True
    assert CP.ngan_sach_cac_ben(ns, khoi, {"co": False})["tran_goi"] is None


# ───────────────────────────── 2. kho dashboard (SQL) ─────────────────────────────
def _ben_co_ngan_sach(gia, tran=40.0, cac=(("hapas", 5.0), ("khac", 30.0))):
    gia.tra.update({
        r"SELECT tran_usd_thang::float AS v, don_vi FROM du_an": [{"v": 5.0, "don_vi": "hapas"}],
        r"SELECT ten, tran_usd_thang::float AS tran FROM don_vi": [{"ten": "HAPAS", "tran": tran}],
        r"SELECT ma, ten, tran_usd_thang::float AS tran FROM du_an WHERE don_vi":
            [{"ma": m, "ten": m.upper(), "tran": t} for m, t in cac],
        r"FROM nguoi_xem n WHERE n.email": [{"la_quan_tri": True, "ben": {}}]})


@pytest.fixture
def co_cot(monkeypatch):
    monkeypatch.setattr(KD, "_CO_TRAN_BEN", [True])


def test_dat_tran_du_an_vuot_ngan_sach_ben_bi_tu_choi(gia, co_cot):
    _ben_co_ngan_sach(gia)
    with pytest.raises(KD.LoiDuLieu) as e:
        KD.dat_tran_thang(AI, "hapas", 12.5)
    # Câu báo: còn trống (chưa chia) = 40 − 30 − 5 = 5; dự án này tối đa 40 − 30 = 10.
    assert "vượt ngân sách bên HAPAS" in str(e.value) and "còn trống 5,00 USD" in str(e.value)
    assert "dự án này đặt được tối đa 10,00 USD" in str(e.value)
    sql = [s for s, _ in gia.gd[0].lenh]
    assert not any(s.startswith(("UPDATE", "INSERT")) for s in sql)
    # Khoá dòng dự án rồi dòng bên (FOR UPDATE) TRƯỚC khi cộng trần các dự án của bên.
    i_da = next(i for i, s in enumerate(sql) if s.startswith("SELECT tran_usd_thang"))
    i_ben = next(i for i, s in enumerate(sql) if "FROM don_vi WHERE ma = %s FOR UPDATE" in s)
    i_tong = next(i for i, s in enumerate(sql) if "FROM du_an WHERE don_vi" in s)
    assert "FOR UPDATE" in sql[i_da] and i_da < i_ben < i_tong


def test_dat_tran_du_an_vua_ngan_sach_ben_mot_giao_dich_mot_nhat_ky(gia, co_cot):
    _ben_co_ngan_sach(gia)
    KD.dat_tran_thang(AI, "hapas", 10)
    assert len(gia.gd) == 1
    lenh = gia.gd[0].lenh
    assert any(s.startswith("UPDATE du_an SET tran_usd_thang") for s, _ in lenh)
    nk = [p for s, p in lenh if s.startswith("INSERT INTO nhat_ky")]
    assert len(nk) == 1 and nk[0][:3] == (AI, "dat_tran_thang", "du_an:hapas")
    assert lenh[-1][0].startswith("INSERT INTO nhat_ky")


def test_ha_tran_du_an_luon_duoc_ke_ca_khi_ben_dang_lo(gia, co_cot):
    """Hạ trần không bao giờ bị chặn (kể cả khi tổng đang lố vì dữ liệu cũ) — không khoá bên."""
    _ben_co_ngan_sach(gia, tran=1.0)
    KD.dat_tran_thang(AI, "hapas", 2)
    sql = [s for s, _ in gia.gd[0].lenh]
    assert not any("FROM don_vi" in s for s in sql)
    assert any(s.startswith("UPDATE du_an") for s in sql)


def test_dat_ngan_sach_ben_chi_quan_tri_vien(gia, co_cot):
    _ben_co_ngan_sach(gia)
    gia.tra[r"FROM nguoi_xem n WHERE n.email"] = [{"la_quan_tri": False,
                                                   "ben": {"hapas": "quan_ly"}}]
    with pytest.raises(KD.LoiDuLieu, match="Chỉ quản trị viên"):
        KD.dat_tran_ben(AI, "hapas", 50)
    assert not any(s.startswith(("UPDATE", "INSERT")) for s, _ in gia.gd[0].lenh)


def test_ha_ngan_sach_ben_duoi_tong_tran_du_an_bi_tu_choi(gia, co_cot):
    _ben_co_ngan_sach(gia)
    with pytest.raises(KD.LoiDuLieu) as e:
        KD.dat_tran_ben(AI, "hapas", 20)
    m = str(e.value)
    # Kê trần từng dự án + phần thiếu: tổng 35, đặt 20 → thiếu 15.
    assert "nhỏ hơn tổng trần 2 dự án" in m and "35,00 USD" in m and "KHAC 30,00" in m
    assert "thiếu 15,00 USD" in m
    sql = [s for s, _ in gia.gd[0].lenh]
    assert not any(s.startswith(("UPDATE", "INSERT")) for s in sql)
    i_ben = next(i for i, s in enumerate(sql) if "FROM don_vi WHERE ma = %s FOR UPDATE" in s)
    assert i_ben < next(i for i, s in enumerate(sql) if "FROM du_an WHERE don_vi" in s)


def test_dat_ngan_sach_ben_ghi_mot_nhat_ky_cung_giao_dich(gia, co_cot):
    _ben_co_ngan_sach(gia)
    KD.dat_tran_ben(AI, "hapas", 35)
    KD.dat_tran_ben(AI, "hapas", None)                       # bỏ ngân sách bên: không kiểm tổng
    for gd, moi in zip(gia.gd, ("35", None)):
        lenh = gd.lenh
        s, p = next(x for x in lenh if x[0].startswith("UPDATE don_vi"))
        assert "tran_usd_thang = %s, sua_luc = now(), sua_boi = %s WHERE ma = %s" in s
        assert p == (35 if moi else None, AI, "hapas")
        nk = [p for s, p in lenh if s.startswith("INSERT INTO nhat_ky")]
        assert len(nk) == 1 and nk[0][:3] == (AI, "dat_tran_ben", "don_vi:hapas")
        assert '"don_vi": "hapas"' in nk[0][3] and lenh[-1][0].startswith("INSERT INTO nhat_ky")
    assert KD.ten_hanh_dong("dat_tran_ben") == "Đặt ngân sách bên"


def test_dat_ngan_sach_ben_khi_kho_chua_co_cot(gia, monkeypatch):
    monkeypatch.setattr(KD, "_CO_TRAN_BEN", [])
    gia.tra[r"FROM nguoi_xem n WHERE n.email"] = [{"la_quan_tri": True, "ben": {}}]
    with pytest.raises(KD.LoiDuLieu, match="chưa có cột ngân sách bên"):
        KD.dat_tran_ben(AI, "hapas", 10)


def test_du_an_moi_kep_tran_mac_dinh_vao_phan_con_trong(gia, co_cot):
    _ben_co_ngan_sach(gia, tran=37.0)                        # còn trống 37 − 35 = 2
    KD.them_du_an(AI, {"ma": "moi", "ten": "Mới", "tu_khoa": [], "tu_loai_tru": [],
                       "boi_canh": "", "dang_bat": True, "don_vi": "hapas"})
    s, p = next(x for x in gia.gd[0].lenh if x[0].startswith("INSERT INTO du_an"))
    assert "tran_usd_thang)" in s and p[-1] == 2.0
    nk = next(p for s, p in gia.gd[0].lenh if s.startswith("INSERT INTO nhat_ky"))
    assert '"tran_usd_thang": 2.0' in nk[3]


def test_chuyen_du_an_sang_ben_khong_du_cho_bi_tu_choi(gia, co_cot):
    gia.tra.update({
        r"SELECT don_vi, tran_usd_thang::float AS tran FROM du_an": [{"don_vi": "hapas",
                                                                       "tran": 35.0}],
        r"SELECT ten, tran_usd_thang::float AS tran FROM don_vi": [{"ten": "MATEMADE",
                                                                    "tran": 10.0}],
        r"SELECT ma, ten, tran_usd_thang::float AS tran FROM du_an WHERE don_vi":
            [{"ma": "mm", "ten": "MM", "tran": 5.0}]})
    with pytest.raises(KD.LoiDuLieu, match="còn trống 5,00 USD, dự án này đặt được tối đa 5,00"):
        KD.sua_du_an(AI, "hapas", {"ten": "HAPAS", "tu_khoa": [], "tu_loai_tru": [],
                                    "boi_canh": "", "dang_bat": True, "don_vi": "matemade"})
    assert not any(s.startswith(("UPDATE", "INSERT")) for s, _ in gia.gd[0].lenh)


def test_ngan_sach_ben_doc_mot_cau(gia, monkeypatch):
    monkeypatch.setattr(KD, "_CO_TRAN_BEN", [True])
    gia.tra[r"FROM don_vi b"] = [{"ma": "hapas", "ten": "HAPAS", "tran": 40.0,
                                  "tong_tran_du_an": 35.0, "so_du_an": 1, "da_tieu": 3.0}]
    assert KD.ngan_sach_ben()["hapas"]["tran"] == 40.0
    s, p = gia.gd[0].lenh[-1]
    assert "b.tran_usd_thang::float AS tran" in s and "l.kieu = 'theo_doi'" in s
    assert "JOIN du_an d ON d.ma = l.du_an WHERE d.don_vi = b.ma" in s and p == (KD._TZ, KD._TZ)
    monkeypatch.setattr(KD, "_CO_TRAN_BEN", [])               # DB chưa chạy schema mới
    KD.ngan_sach_ben()
    assert "NULL::float AS tran" in gia.gd[-1].lenh[-1][0]


def test_schema_ngan_sach_ben_chay_lai_an_toan():
    assert "ALTER TABLE don_vi ADD COLUMN IF NOT EXISTS tran_usd_thang NUMERIC(8,2);" in SCHEMA
    assert "ALTER TABLE don_vi DROP CONSTRAINT IF EXISTS don_vi_tran_usd_thang_check;" in SCHEMA
    assert "CHECK (tran_usd_thang BETWEEN 0 AND 1000)" in SCHEMA
    assert "ALTER TABLE don_vi ADD COLUMN IF NOT EXISTS sua_luc TIMESTAMPTZ" in SCHEMA
    assert "ALTER TABLE don_vi ADD COLUMN IF NOT EXISTS sua_boi TEXT;" in SCHEMA
    for c in ("tran_usd_thang", "sua_luc", "sua_boi"):
        assert re.search(rf"COMMENT ON COLUMN don_vi\.{c} IS '.{{40,}}';", SCHEMA), c
    # Quyền: web ghi cả bảng don_vi, Mark đọc cả bảng — không cần GRANT theo cột.
    assert "GRANT INSERT, UPDATE ON don_vi TO lang_nghe_web;" in SCHEMA
    assert "GRANT SELECT ON don_vi TO mark;" in SCHEMA


# ───────────────────────────── 3. route + giao diện ─────────────────────────────
HP_QL = "ql.hapas@hapas.vn"


def _kho_ben() -> GiaKhoWeb:
    kho = GiaKhoWeb()
    kho.nguoi[HP_QL] = "quan_ly"
    kho.quyen[HP_QL] = {"hapas": "quan_ly"}
    kho.du_an["hapas"]["tran_usd_thang"] = 35.0
    return kho


def test_chi_quan_tri_vien_dat_ngan_sach_ben_quan_ly_bi_403():
    _, c, kho = tao(_kho_ben())
    csrf = dang_nhap(c, HP_QL)
    r = c.post("/ngan-sach-ben/hapas", data={"csrf": csrf, "tran_usd_thang": "50"})
    assert r.status_code == 403 and "Chỉ quản trị viên" in r.text
    csrf = dang_nhap(c, XEM)
    assert c.post("/ngan-sach-ben/hapas", data={"csrf": csrf,
                                                "tran_usd_thang": "50"}).status_code == 403
    assert kho.tran_ben == {} and kho.nk == []
    csrf = dang_nhap(c, QL)
    r = c.post("/ngan-sach-ben/hapas", data={"csrf": csrf, "tran_usd_thang": "40"})
    assert "Đã đặt ngân sách bên hapas: 40,00 USD/tháng" in thong_bao(c, r)
    assert kho.tran_ben == {"hapas": 40.0} and kho.nk == [(QL, "dat_tran_ben", "don_vi:hapas")]


@pytest.mark.parametrize("vao, khop", [("20", "thiếu 15.00 USD"), ("1001", "tối đa 1.000,00"),
                                       ("-1", "Trần tháng phải là số")])
def test_ngan_sach_ben_sai_bao_qua_thong_bao(vao, khop):
    _, c, kho = tao(_kho_ben())
    csrf = dang_nhap(c, QL)
    r = c.post("/ngan-sach-ben/hapas", data={"csrf": csrf, "tran_usd_thang": vao})
    assert khop in thong_bao(c, r) and kho.tran_ben == {}


def test_tran_du_an_vuot_ngan_sach_ben_bao_qua_thong_bao():
    kho = _kho_ben()
    kho.tran_ben["hapas"] = 40.0
    _, c, _ = tao(kho)
    csrf = dang_nhap(c, HP_QL)
    r = c.post("/ngan-sach/hapas", data={"csrf": csrf, "tran_usd_thang": "45"})
    t = thong_bao(c, r)
    assert "vượt ngân sách bên" in t and "còn trống 5.00 USD" in t
    assert kho.du_an["hapas"]["tran_usd_thang"] == 35.0
    r = c.post("/ngan-sach/hapas", data={"csrf": csrf, "tran_usd_thang": "40"})
    assert "Đã đặt trần tháng 40,00 USD" in thong_bao(c, r)


def test_trang_ngan_sach_khoi_ben_quan_tri_vien_sua_duoc():
    kho = _kho_ben()
    kho.tran_ben["hapas"] = 40.0
    _, c, _ = tao(kho)
    dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert 'id="ns-ben"' in t and "Ngân sách theo bên" in t
    assert t.index('id="ns-ben"') < t.index('id="ns-tong-tieu-de"')     # khối bên đứng đầu
    assert 'action="/ngan-sach-ben/hapas"' in t and 'action="/ngan-sach-ben/matemade"' in t
    assert 'name="tran_usd_thang" min="0" max="1000"' in t and 'value="40.00"' in t
    assert 'placeholder="chưa đặt"' in t                                 # MATEMADE chưa đặt
    assert 'data-phan-trang="20" data-phan-trang-nhan="bên"' in t
    assert "còn trống 5,00" in t and "ns-ben__thanh" in t
    # Ô trần dự án: ngân sách bên còn trống + JSON cho trình duyệt.
    assert "Ngân sách bên còn trống: <b data-o=\"ben-con\">5,00</b> USD" in t
    assert '"ben": {"con_trong": 5.0, "toi_da_tran": 40.0}' in t


def test_trang_ngan_sach_quan_ly_chi_thay_ben_minh_chi_doc():
    kho = _kho_ben()
    kho.tran_ben["hapas"] = 40.0
    _, c, _ = tao(kho)
    dang_nhap(c, HP_QL)
    t = c.get("/ngan-sach").text
    assert 'id="ns-ben"' in t and "chỉ xem — quản trị viên đặt" in t
    assert "/ngan-sach-ben/" not in t and "MATEMADE" not in t.split('id="ns-ben"')[1].split(
        "</section>")[0]
    assert "<b>40,00</b>" in t


def test_trang_ngan_sach_goi_chung_va_canh_bao_vuot_goi(monkeypatch):
    kho = _kho_ben()
    kho.tran_ben.update(hapas=40.0, matemade=5.0)
    kho.han_muc_apify = lambda: {"tran_usd": 10.0, "da_dung_usd": 2.0, "du_tru_usd": 0.3,
                                 "goi": "FREE", "luc": datetime.datetime.now(CP.VN)}
    _, c, _ = tao(kho)
    dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    khoi = t.split('id="ns-ben"')[1].split("</section>")[0]
    assert "Gói Apify chung <b>10,00</b> USD/chu kỳ" in khoi
    assert "Tổng ngân sách các bên <b>45,00</b>" in khoi and "vượt gói 35,00 USD" in khoi


def test_tran_hieu_luc_bi_ben_giu_hien_tren_the_du_an():
    kho = _kho_ben()
    kho.tran_ben["hapas"] = 36.0
    kho.da_tieu_thang = lambda: {"hapas": 1.25}
    kho.du_an["moi"] = dict(kho.du_an["hapas"], ma="moi", ten="Mới", tran_usd_thang=1.0)
    kho.da_tieu_thang = lambda: {"hapas": 1.25, "moi": 34.0}
    _, c, _ = tao(kho)
    dang_nhap(c, QL)
    t = c.get("/ngan-sach?du_an=hapas").text
    # Bên còn 36 − 35,25 = 0,75 → trần hiệu lực HAPAS = 1,25 + 0,75 = 2,00 (< trần dự án 35).
    assert 'data-o="tran-ben">ngân sách bên giữ' in t and "Trần hiệu lực <b>2,00</b>" in t


# ───────────────────────────── 4. Mark dừng theo ngân sách bên ─────────────────────────────
class _Conn:
    def __init__(self, tra):
        self.tra, self.lenh = tra, []

    def execute(self, sql, ts=None):
        self.lenh.append((sql, tuple(ts or ())))
        for mau, dong in self.tra.items():
            if mau in sql:
                return types.SimpleNamespace(fetchone=lambda d=dong: d[0] if d else None)
        return types.SimpleNamespace(fetchone=lambda: None)


def test_mark_doc_ngan_sach_ben_sql(monkeypatch):
    monkeypatch.setattr(K, "_CO_TRAN_BEN", [])
    c = _Conn({"information_schema.columns": [{"co": 1}],
               "JOIN don_vi b": [{"ma": "hapas", "ten": "HAPAS", "tran": 40.0}],
               "FROM luot_quet l": [{"usd": 12.5}]})
    assert K._doc_ngan_sach_ben(c, "hapas") == {"ma": "hapas", "ten": "HAPAS", "tran": 40.0,
                                                "da_tieu": 12.5}
    s, p = c.lenh[2]
    assert "WHERE d.don_vi = %s AND l.kieu = 'theo_doi'" in s and p == ("hapas", K._TZ, K._TZ)
    assert "b.tran_usd_thang::float AS tran" in c.lenh[1][0]
    # DB chưa chạy schema mới: không có ngân sách bên, không cộng tiền cả bên.
    monkeypatch.setattr(K, "_CO_TRAN_BEN", [])
    c = _Conn({"JOIN don_vi b": [{"ma": "hapas", "ten": "HAPAS", "tran": None}]})
    assert K._doc_ngan_sach_ben(c, "hapas")["tran"] is None
    assert "NULL::float AS tran" in c.lenh[1][0] and len(c.lenh) == 2


def test_con_thang_cua_mark_dung_luat_chung(monkeypatch):
    monkeypatch.setattr(K, "ngan_sach_ben", lambda ma: {"ma": "hapas", "ten": "HAPAS",
                                                        "tran": 10.0, "da_tieu": 9.0})
    ct = T.con_thang("hapas", DU_AN, 1.0)
    assert ct["con"] == pytest.approx(1.0) and ct["chan_boi"] == "ben"
    assert ct["tran"] == CP.tran_hieu_luc(5.0, None, {"tran": 10.0, "da_tieu": 9.0}, 1.0)
    # Phần xong của việc đang chạy (kho chưa thấy) trừ vào cả dự án lẫn bên.
    assert T.con_thang("hapas", DU_AN, 1.0, them=0.4)["con"] == pytest.approx(0.6)
    assert "bên HAPAS" in T.con_thang("hapas", DU_AN, 1.0, them=1.0)["het_ly_do"]
    monkeypatch.setattr(K, "ngan_sach_ben", lambda ma: None)
    assert T.con_thang("hapas", DU_AN, 1.0)["con"] == 4.0


def test_ke_hoach_het_ngan_sach_ben_du_tran_du_an_con(mo):
    GiaKho(nguon=[_nguon(1, "tiktok", "a")], da_tieu=0.5).cai(mo)
    mo.setattr(K, "ngan_sach_ben", lambda ma: {"ma": "hapas", "ten": "HAPAS", "tran": 20.0,
                                               "da_tieu": 20.0})
    kh = T.ke_hoach("hapas")
    assert kh["ma_loi"] == "het_ngan_sach"
    assert "hết ngân sách tháng của bên HAPAS (20,00/20,00 USD cả bên)" in kh["loi"]


def test_ke_hoach_kho_loi_khi_doc_ngan_sach_ben_thi_khong_quet(mo):
    GiaKho(nguon=[_nguon(1, "tiktok", "a")]).cai(mo)

    def hong(ma):
        raise K.LoiKho("kho lắng nghe báo lỗi (InsufficientPrivilege: 42501)")
    mo.setattr(K, "ngan_sach_ben", hong)
    assert T.ke_hoach("hapas")["ma_loi"] == "kho_loi"


def test_lich_khong_tao_viec_khi_ben_het_va_cau_noi_ben(mo):
    GiaKho(du_an={"hapas": dict(DU_AN, tk_bat=True, tk_so_bai=10)}, nguon=[]).cai(mo)
    mo.setattr(K, "ngan_sach_ben", lambda ma: {"ma": "hapas", "ten": "HAPAS", "tran": 8.0,
                                               "da_tieu": 8.5})
    goi = _bat_tao_viec(mo)
    kq = T.tao_luot("hapas", lich={"id": 3, "moc": "x"})
    assert not kq["ok"] and kq["ma_loi"] == "het_ngan_sach" and "bên HAPAS" in kq["cau"]
    assert goi == []


def test_tao_luot_giu_cho_trong_phan_con_cua_ben(mo):
    GiaKho(nguon=[_nguon(1, "tiktok", "a"), _nguon(2, "youtube", "@b")], da_tieu=1.0).cai(mo)
    mo.setattr(K, "ngan_sach_ben", lambda ma: {"ma": "hapas", "ten": "HAPAS", "tran": 10.0,
                                               "da_tieu": 8.5})
    goi = _bat_tao_viec(mo)
    kq = T.tao_luot("hapas")
    assert kq["ok"] and 0 < goi[0]["ns"] <= 1.5           # ≤ phần còn của bên (10 − 8,5)
    assert "còn 1,50/5,00 USD (bên HAPAS còn 1,50/10,00 USD)" in kq["cau"]


def test_chay_viec_dung_khi_ben_het_luc_chay(mo):
    """Lập kế hoạch lúc bên còn tiền, tới lúc chạy dự án khác cùng bên đã tiêu hết: không gọi
    actor (đọc lại ngân sách bên lúc chạy — `con_thang`)."""
    kho = GiaKho(nguon=[_nguon(1, "tiktok", "kola")], da_tieu=0.0).cai(mo)
    ap = GiaApify(mo, [_tt("kola", 1, "hapas")])
    mo.setattr(K, "ngan_sach_ben", lambda ma: {"ma": "hapas", "ten": "HAPAS", "tran": 10.0,
                                               "da_tieu": 9.995})
    v = _viec(kho.nguon)
    _, van_ban = T.chay_viec(v)
    assert ap.gui == [] and "hết ngân sách" in van_ban
    assert v.d["nen_tang"]["tiktok"]["phan"][0]["ma"] == "NGAN_SACH" and v.chot == []
