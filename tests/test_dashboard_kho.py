"""Dashboard lắng nghe (đợt 2, 14/10/2026): tầng SQL `dashboard/kho.py`, không cần Postgres.

Kết nối GIẢ ghi lại từng câu SQL: kiểm mỗi hàm sửa dữ liệu ghi đúng MỘT dòng `nhat_ky` (ai = người
thao tác) TRONG CÙNG giao dịch, không chạm bảng ngoài quyền của role `lang_nghe_web`, cột đọc có
trong `schema.sql`, và lỗi kho không bao giờ lộ DSN. SQL chạy thật trên VPS khi cài."""
from __future__ import annotations

import contextlib
import re
import sys
import types
from pathlib import Path

import pytest

from dashboard import kho as K

GOC = Path(__file__).resolve().parents[1]
SCHEMA = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
AI = "quan@hapas.vn"


class GiaCur:
    def __init__(self, dong):
        self.dong = dong

    def fetchone(self):
        return self.dong[0] if self.dong else None

    def fetchall(self):
        return list(self.dong)


class GiaConn:
    """Trả dòng theo mẫu SQL; ghi lại mọi câu đã chạy."""

    def __init__(self, tra: dict[str, list] | None = None):
        self.lenh: list[tuple[str, tuple]] = []
        self.tra = tra or {}

    def execute(self, sql, tham_so=None):
        self.lenh.append((sql, tuple(tham_so or ())))
        for mau, dong in self.tra.items():
            if re.search(mau, sql):
                return GiaCur(dong)
        return GiaCur([])


@pytest.fixture
def gia(monkeypatch):
    """-> hàm đặt dòng trả; mỗi `with ket_noi()` là một giao dịch (ghi vào danh sách)."""
    gd: list[GiaConn] = []
    tra: dict[str, list] = {}

    @contextlib.contextmanager
    def ket_noi(trung="Dữ liệu này đã có."):
        c = GiaConn(tra)
        gd.append(c)
        yield c
    monkeypatch.setattr(K, "ket_noi", ket_noi)
    return types.SimpleNamespace(gd=gd, tra=tra)


NGUON = {"nen_tang": "tiktok", "dinh_danh": "kola", "ten": "KOL A",
         "link": "https://www.tiktok.com/@kola", "loai": "kol", "nhan": ["kol"], "chu_ky_ngay": 1,
         "so_bai_moi_lan": 5}
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"], "tu_loai_tru": [],
         "boi_canh": "", "thi_truong": "VN", "dang_bat": True}

THAO_TAC = [
    ("them_du_an", lambda: K.them_du_an(AI, DU_AN)),
    ("sua_du_an", lambda: K.sua_du_an(AI, "hapas", {k: v for k, v in DU_AN.items() if k != "ma"})),
    ("dat_tran_thang", lambda: K.dat_tran_thang(AI, "hapas", 12.5)),
    ("them_nguon", lambda: K.them_nguon(AI, "hapas", NGUON)),
    ("sua_nguon", lambda: K.sua_nguon(AI, 7, NGUON)),
    ("doi_trang_thai_nguon", lambda: K.doi_trang_thai_nguon(AI, 7, "tam_dung")),
    ("xoa_nguon", lambda: K.xoa_nguon(AI, 7)),
    ("duyet_de_xuat", lambda: K.duyet_de_xuat(AI, 5, NGUON)),
    ("tu_choi_de_xuat", lambda: K.tu_choi_de_xuat(AI, 5)),
    ("luu_nguoi_xem", lambda: K.luu_nguoi_xem(AI, "moi@hapas.vn", "xem")),
    ("xoa_nguoi_xem", lambda: K.xoa_nguoi_xem(AI, "xem@hapas.vn")),
    ("dong_bo_bq", lambda: K.ghi_nhat_ky(AI, "dong_bo_bq", "bigquery", {"kieu": "bam_tay"})),
    ("dang_nhap_lan_dau", lambda: K.ghi_dang_nhap_lan_dau(AI, "ou_123")),
]


@pytest.mark.parametrize("hanh_dong, goi", THAO_TAC, ids=[t[0] for t in THAO_TAC])
def test_moi_thao_tac_ghi_nhat_ky_cung_giao_dich(gia, hanh_dong, goi):
    gia.tra.update({
        r"RETURNING id": [{"id": 9}],
        r"RETURNING ma": [{"ma": "hapas"}],
        r"^UPDATE nguon .*RETURNING du_an": [{"du_an": "hapas"}],
        r"^DELETE FROM nguon": [{"du_an": "hapas", "nen_tang": "tiktok", "dinh_danh": "kola"}],
        r"^UPDATE de_xuat": [{"du_an": "hapas", "nen_tang": "tiktok", "dinh_danh": "kola"}],
        r"tran_usd_thang::float AS v": [{"v": 5.0}],
        r"SELECT vai_tro FROM nguoi_xem": [{"vai_tro": "xem"}],
        r"count\(\*\)": [{"n": 1}],
    })
    goi()
    assert len(gia.gd) == 1, "phải là MỘT giao dịch"
    lenh = gia.gd[0].lenh
    nk = [(s, p) for s, p in lenh if s.startswith("INSERT INTO nhat_ky")]
    assert len(nk) == 1
    assert nk[0][1][:2] == (AI, hanh_dong)
    assert lenh[-1][0].startswith("INSERT INTO nhat_ky"), "nhật ký ghi SAU thao tác, cùng giao dịch"


def test_ghi_dang_nhap_lan_dau_chi_mot_lan(gia):
    gia.tra[r"FROM nhat_ky WHERE hanh_dong = 'dang_nhap_lan_dau'"] = [{"co": 1}]
    assert K.ghi_dang_nhap_lan_dau(AI, "ou_123") is False
    assert not any(s.startswith("INSERT") for s, _ in gia.gd[0].lenh)


def test_doc_bai_gon_va_giu_bai_moi_nhat_khi_cat(gia):
    """M1: chỉ cột chi_so cần, chữ dài cắt trong SQL; vượt trần thì giữ bài MỚI NHẤT."""
    gia.tra[r"FROM bai b"] = [{"dang_luc": i} for i in range(K.BAI_TOI_DA + 1)]
    kq = K.bai_trong_khoang("hapas", "a", "b")
    assert kq["bi_cat"] is True and len(kq["rows"]) == K.BAI_TOI_DA
    sql, ts = gia.gd[0].lenh[0]
    assert "ORDER BY b.dang_luc DESC LIMIT %s" in sql and ts[-1] == K.BAI_TOI_DA + 1
    assert "left(b.noi_dung, 1000)" in sql and "b.khoa" not in sql and "b.*" not in sql


def test_duyet_de_xuat_them_nguon_qua_de_xuat(gia):
    gia.tra.update({r"^UPDATE de_xuat": [{"du_an": "hapas"}], r"RETURNING id": [{"id": 11}]})
    assert K.duyet_de_xuat(AI, 5, NGUON) == 11
    sql = [s for s, _ in gia.gd[0].lenh]
    assert "trang_thai = 'cho'" in sql[0]                  # chỉ đề xuất còn chờ
    assert "'de_xuat'" in sql[1] and "ON CONFLICT (du_an, nen_tang, dinh_danh) DO NOTHING" in sql[1]


def test_duyet_de_xuat_da_xu_ly_thi_khong_them_gi(gia):
    with pytest.raises(K.LoiDuLieu):
        K.duyet_de_xuat(AI, 5, NGUON)                     # UPDATE … 'cho' không trả dòng
    assert not any("INSERT" in s for s, _ in gia.gd[0].lenh)


@pytest.mark.parametrize("goi", [lambda: K.xoa_nguoi_xem(AI, "quan@hapas.vn"),
                                 lambda: K.luu_nguoi_xem(AI, "quan@hapas.vn", "xem")])
def test_khong_xoa_khong_ha_quan_ly_cuoi(gia, goi):
    gia.tra.update({r"SELECT vai_tro FROM nguoi_xem": [{"vai_tro": "quan_ly"}],
                    r"count\(\*\)": [{"n": 0}]})
    with pytest.raises(K.LoiDuLieu):
        goi()
    sql = [s for s, _ in gia.gd[0].lenh]
    # khoá bảng TRƯỚC khi đọc vai trò (đọc trước rồi mới khoá thì hai người cùng xoá hai quản lý
    # cuối vẫn lọt — vai trò đọc được đã cũ)
    assert sql[0].startswith("LOCK TABLE nguoi_xem")
    assert not any(s.startswith(("DELETE", "INSERT")) for s in sql)


def _cot(bang: str) -> set[str]:
    khoi = re.search(rf"CREATE TABLE IF NOT EXISTS {bang} \((.*?)\n\);", SCHEMA, re.DOTALL).group(1)
    return set(re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE))


def test_cot_doc_co_trong_schema():
    for cot, bang in ((K._COT_NGUON, "nguon"), (K._COT_DE_XUAT, "de_xuat")):
        assert {c.strip() for c in cot.split(",")} <= _cot(bang)
    assert {re.split(r"[\s:]", c.strip())[0] for c in K._COT_DU_AN.split(",")} <= _cot("du_an")


def test_chi_ghi_bang_role_lang_nghe_web_duoc_ghi():
    """Quyền theo schema.sql: INSERT/UPDATE/DELETE du_an, nguon, nguoi_xem; UPDATE 3 cột của
    de_xuat; INSERT nhat_ky. Dashboard KHÔNG ghi bai/luot_quet/chi_so_ngay (phần của Mark)."""
    src = (GOC / "dashboard" / "kho.py").read_text(encoding="utf-8")
    ghi = set(re.findall(r"(?:INSERT INTO|UPDATE|DELETE FROM) ([a-z_]+)", src))
    assert ghi <= {"du_an", "nguon", "nguoi_xem", "nhat_ky", "de_xuat"}
    for m in re.finditer(r"UPDATE de_xuat SET (.*?) WHERE", src, re.DOTALL):
        cot = {x.replace('"', " ").split()[0] for x in m.group(1).split(",")
               if x.replace('"', " ").strip()}
        assert cot <= {"trang_thai", "xu_ly_boi", "xu_ly_luc"}
    assert "GRANT INSERT, UPDATE, DELETE ON du_an, nguon, nguoi_xem TO lang_nghe_web;" in SCHEMA
    assert "GRANT UPDATE (trang_thai, xu_ly_boi, xu_ly_luc) ON de_xuat TO lang_nghe_web;" in SCHEMA
    assert "GRANT INSERT ON nhat_ky TO lang_nghe_web;" in SCHEMA


def _psycopg_gia(monkeypatch, loi_noi: Exception | None = None):
    """Module psycopg giả: connect() ném lỗi có DSN trong thông điệp (như libpq hay làm)."""
    pg = types.ModuleType("psycopg")

    class Error(Exception):
        sqlstate = None
    pg.Error = Error
    loi = types.ModuleType("psycopg.errors")
    for ten in ("UniqueViolation", "CheckViolation", "ForeignKeyViolation", "NotNullViolation"):
        setattr(loi, ten, type(ten, (Error,), {}))
    pg.errors = loi
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()

    def connect(dsn, **kw):
        raise Error(f"connection failed: {dsn}")
    pg.connect = connect
    monkeypatch.setitem(sys.modules, "psycopg", pg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows)
    monkeypatch.setitem(sys.modules, "psycopg.errors", loi)


def test_loi_kho_khong_lo_dsn(monkeypatch):
    monkeypatch.setenv("LANG_NGHE_WEB_DSN", "host=db user=web password=bimat-khong-lo")
    _psycopg_gia(monkeypatch)
    with pytest.raises(K.LoiKho) as e:
        K.vai_tro("a@b.vn")
    assert "bimat" not in str(e.value) and "host=" not in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__


def test_thieu_psycopg_bao_loi_kho(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)
    with pytest.raises(K.LoiKho, match="psycopg"):
        K.kiem_tra()
