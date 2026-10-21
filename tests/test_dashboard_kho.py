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
    # DB đã có cột cờ TikTok (20/10/2026): không hỏi information_schema trước mỗi câu đọc bài.
    monkeypatch.setattr(K, "_CO_CO_TT", [True])
    return types.SimpleNamespace(gd=gd, tra=tra)


NGUON = {"nen_tang": "tiktok", "dinh_danh": "kola", "ten": "KOL A",
         "link": "https://www.tiktok.com/@kola", "loai": "kol", "nhan": ["kol"], "chu_ky_ngay": 1,
         "so_bai_moi_lan": 5}
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"], "tu_loai_tru": [],
         "boi_canh": "", "thi_truong": "VN", "dang_bat": True, "don_vi": "hapas"}
LICH = {"ten": "Sáng", "kieu": "hang_ngay", "cau_hinh": {"gio": ["08:00"], "thu": []},
        "bat": True, "quet_moi_nguon": False, "lan_chay_ke": None}

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
    ("luu_quyen", lambda: K.luu_quyen(AI, "moi@hapas.vn", "hapas", "xem")),
    ("xoa_quyen", lambda: K.xoa_quyen(AI, "xem@hapas.vn", "hapas")),
    ("dat_quan_tri", lambda: K.dat_quan_tri(AI, "moi@hapas.vn", True)),
    ("xoa_nguoi_xem", lambda: K.xoa_nguoi_xem(AI, "xem@hapas.vn")),
    ("them_don_vi", lambda: K.them_don_vi(AI, "ben-moi", "Bên mới")),
    ("dong_bo_bq", lambda: K.ghi_nhat_ky(AI, "dong_bo_bq", "bigquery", {"kieu": "bam_tay"})),
    ("dang_nhap_lan_dau", lambda: K.ghi_dang_nhap(AI, "ou_123")),
    ("them_lich", lambda: K.them_lich(AI, "hapas", LICH)),
    ("sua_lich", lambda: K.sua_lich(AI, 3, LICH)),
    ("tat_lich", lambda: K.bat_tat_lich(AI, 3, False, None)),
    ("bat_lich", lambda: K.bat_tat_lich(AI, 3, True, "2026-10-16T08:00:00+07:00")),
    ("xoa_lich", lambda: K.xoa_lich(AI, 3)),
]
LICH_DONG = {"du_an": "hapas", "ten": "Sáng", "kieu": "hang_ngay", "cau_hinh": {}, "bat": True,
             "quet_moi_nguon": False}


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
        r"SELECT 1 AS co FROM du_an": [{"co": 1}],
        r"SELECT 1 AS co FROM don_vi": [{"co": 1}],
        # quyền (người làm = quản trị viên; người bị sửa cũng có quyền Chỉ xem HAPAS)
        r"FROM nguoi_xem n WHERE n.email": [{"la_quan_tri": True, "ben": {"hapas": "xem"}}],
        r"FROM lich_quet WHERE id = %s FOR UPDATE": [LICH_DONG],
        r"^UPDATE lich_quet .*RETURNING du_an": [{"du_an": "hapas"}],
        r"^DELETE FROM lich_quet": [LICH_DONG],
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
    assert K.ghi_dang_nhap(AI, "ou_123") is False
    lenh = gia.gd[0].lenh
    assert not any(s.startswith("INSERT") for s, _ in lenh)
    # lượt đăng nhập nào cũng ghi lần cuối + mã Lark, kể cả khi không phải lần đầu
    assert lenh[0][0].startswith("UPDATE nguoi_xem SET dang_nhap_cuoi = now(), ")
    assert lenh[0][1] == ("ou_123", "ou_123", "ou_123", "", "", AI)


def test_ghi_dang_nhap_luu_ma_lark_va_doc_lai_danh_ba_khi_doi(gia):
    K.ghi_dang_nhap(AI, "ou_moi", "on_1", "u_1")
    sql, tham_so = gia.gd[0].lenh[0]
    assert tham_so == ("ou_moi", "ou_moi", "ou_moi", "on_1", "u_1", AI)
    # open_id đổi -> xoá mốc đọc danh bạ; mã rỗng không xoá mã cũ
    assert "danh_ba_luc = CASE WHEN %s <> '' AND lark_open_id IS DISTINCT FROM %s" in sql
    for cot in ("lark_open_id", "lark_union_id", "lark_user_id"):
        assert f"{cot} = COALESCE(NULLIF(%s, ''), {cot})" in sql


def test_doc_bai_gon_va_giu_bai_moi_nhat_khi_cat(gia):
    """M1: chỉ cột chi_so cần, chữ dài cắt trong SQL; vượt trần thì giữ bài MỚI NHẤT."""
    gia.tra[r"FROM bai b"] = [{"dang_luc": i} for i in range(K.BAI_TOI_DA + 1)]
    kq = K.bai_trong_khoang("hapas", "a", "b")
    assert kq["bi_cat"] is True and len(kq["rows"]) == K.BAI_TOI_DA
    sql, ts = gia.gd[0].lenh[0]
    assert "ORDER BY b.dang_luc DESC LIMIT %s" in sql and ts[-1] == K.BAI_TOI_DA + 1
    assert "left(b.noi_dung, 1000)" in sql and "b.*" not in sql
    # Đợt 2b: khoá bài cần cho khung chi tiết (mở bình luận của bài) — chỉ khoá, không cột dài.
    assert "b.khoa," in sql and "b.bl_da_lay" in sql
    assert "b.kieu_quet" in sql                                 # đợt 2f: bộ lọc "kiểu quét"


def test_doc_bai_theo_khoa_cung_cot_tung_lo(gia):
    """Đợt 2f: bài gốc của bình luận (đăng trước khoảng) đọc theo khoá, cùng cột hẹp, từng lô."""
    assert K.bai_theo_khoa("hapas", []) == [] and gia.gd == []
    gia.tra[r"FROM bai b"] = [{"khoa": "x"}]
    khoa = [f"k{i}" for i in range(12_000)] + ["k1", ""]       # trùng + rỗng bị bỏ
    assert len(K.bai_theo_khoa("hapas", khoa)) == 3            # 3 lô: 5.000 + 5.000 + 2.000
    lenh = gia.gd[0].lenh
    assert [len(p[1]) for _, p in lenh] == [5000, 5000, 2000]
    # Cột HẸP: không nội dung / hashtag / cột hiển thị khi không lọc chữ.
    assert all("b.khoa = ANY(%s)" in s and K._COT_BAI_GOC in s for s, _ in lenh)
    assert not any(c in lenh[0][0] for c in ("noi_dung", "hashtag", "b.xem", "sac_thai"))
    cot = set(re.findall(r"\bb\.([a-z_]+)", K._COT_BAI_GOC))
    assert cot == {"khoa", "nen_tang", "nguon_id", "tai_khoan", "tac_gia", "followers", "thich",
                   "binh_luan", "chia_se", "kieu_quet", "kieu_trang", "link"} \
        and cot <= _cot("bai")
    assert "n.loai AS nguon_loai" in K._COT_BAI_GOC
    K.bai_theo_khoa("hapas", ["k1"], co_chu=True)               # đang lọc chữ: thêm nội dung
    sql = gia.gd[1].lenh[0][0]
    assert "left(b.noi_dung, 1000) AS noi_dung" in sql and "AS hashtag" in sql
    assert set(re.findall(r"\bb\.([a-z_]+)", K._COT_BAI_CS)) <= _cot("bai")


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
                                 lambda: K.dat_quan_tri(AI, "quan@hapas.vn", False)])
def test_khong_xoa_khong_ha_quan_tri_cuoi(gia, goi):
    gia.tra.update({r"FROM nguoi_xem n WHERE n.email": [{"la_quan_tri": True, "ben": {}}],
                    r"count\(\*\)": [{"n": 0}]})
    with pytest.raises(K.LoiDuLieu, match="cuối cùng"):
        goi()
    sql = [s for s, _ in gia.gd[0].lenh]
    # khoá bảng TRƯỚC khi đọc quyền (đọc trước rồi mới khoá thì hai người cùng bỏ hai quản trị viên
    # cuối vẫn lọt — quyền đọc được đã cũ); khoá cả `quyen`
    assert sql[0] == "LOCK TABLE nguoi_xem, quyen IN SHARE ROW EXCLUSIVE MODE"
    assert not any(s.startswith(("DELETE", "INSERT", "UPDATE")) for s in sql)


def _quyen_theo_email(gia, bang: dict):
    """GiaConn trả quyền theo THAM SỐ email của câu `_SQL_QUYEN` (người làm ≠ người bị sửa)."""
    goc = GiaConn.execute

    def execute(self, sql, tham_so=None):
        if sql.startswith("SELECT n.la_quan_tri") and "FROM nguoi_xem n WHERE n.email" in sql:
            self.lenh.append((sql, tuple(tham_so or ())))
            r = bang.get(tham_so[0])
            return GiaCur([r] if r else [])
        return goc(self, sql, tham_so)
    return execute


@pytest.mark.parametrize("goi, khop", [
    (lambda: K.luu_quyen(AI, "moi@hapas.vn", "hapas", "quan_ly"), "chỉ thêm được người Chỉ xem"),
    (lambda: K.luu_quyen(AI, "moi@hapas.vn", "matemade", "xem"), "quản lý của bên này"),
    (lambda: K.luu_quyen(AI, "qt@hapas.vn", "hapas", "xem"), "quản trị viên"),
    (lambda: K.luu_quyen(AI, AI, "hapas", "xem"), "chính mình"),
    (lambda: K.xoa_quyen(AI, "ql2@hapas.vn", "hapas"), "Quản lý của bên"),
    (lambda: K.xoa_quyen(AI, "xem@hapas.vn", "matemade"), "quản lý của bên này"),
    (lambda: K.dat_quan_tri(AI, "xem@hapas.vn", True), "Chỉ quản trị viên"),
    (lambda: K.xoa_nguoi_xem(AI, "xem@hapas.vn"), "Chỉ quản trị viên"),
    (lambda: K.them_don_vi(AI, "ben-moi", "Bên mới"), "Chỉ quản trị viên"),
])
def test_quan_ly_ben_khong_vuot_quyen_trong_giao_dich(gia, monkeypatch, goi, khop):
    """Kho đọc quyền NGƯỜI LÀM trong giao dịch (sau khoá) rồi kiểm luật — tầng app lọt thì kho
    vẫn chặn: quản lý HAPAS không cấp Quản lý, không đụng bên khác / quản trị viên / chính mình."""
    monkeypatch.setattr(GiaConn, "execute", _quyen_theo_email(gia, {
        AI: {"la_quan_tri": False, "ben": {"hapas": "quan_ly"}},
        "qt@hapas.vn": {"la_quan_tri": True, "ben": {}},
        "ql2@hapas.vn": {"la_quan_tri": False, "ben": {"hapas": "quan_ly"}},
        "xem@hapas.vn": {"la_quan_tri": False, "ben": {"hapas": "xem", "matemade": "xem"}},
    }))
    gia.tra[r"count\(\*\)"] = [{"n": 1}]
    with pytest.raises(K.LoiDuLieu, match=khop):
        goi()
    sql = [s for s, _ in gia.gd[0].lenh]
    assert not any(s.startswith(("DELETE", "INSERT", "UPDATE")) for s in sql)


def test_quan_ly_ben_them_va_bo_nguoi_chi_xem(gia, monkeypatch):
    """Quản lý HAPAS thêm người Chỉ xem HAPAS; bỏ quyền HAPAS của người còn MATEMADE chỉ xoá dòng
    `quyen` của HAPAS; người hết bên thì xoá luôn dòng người xem."""
    monkeypatch.setattr(GiaConn, "execute", _quyen_theo_email(gia, {
        AI: {"la_quan_tri": False, "ben": {"hapas": "quan_ly"}},
        "xem@hapas.vn": {"la_quan_tri": False, "ben": {"hapas": "xem", "matemade": "xem"}}}))
    gia.tra[r"SELECT 1 AS co FROM don_vi"] = [{"co": 1}]
    K.luu_quyen(AI, "moi@hapas.vn", "hapas", "xem")
    sql = [(s, p) for s, p in gia.gd[0].lenh]
    assert any(s.startswith("INSERT INTO quyen") and p[:3] == ("moi@hapas.vn", "hapas", "xem")
               for s, p in sql)
    assert sql[-1][1][:2] == (AI, "luu_quyen")
    assert K.xoa_quyen(AI, "xem@hapas.vn", "hapas") is False     # còn MATEMADE
    lenh = gia.gd[1].lenh
    assert ("DELETE FROM quyen WHERE email = %s AND don_vi = %s", ("xem@hapas.vn", "hapas")) in lenh
    assert not any("DELETE FROM quyen" in s and "matemade" in p for s, p in lenh)
    gia.tra[r"RETURNING n.email"] = [{"email": "xem@hapas.vn"}]
    assert K.xoa_quyen(AI, "xem@hapas.vn", "hapas") is True      # hết bên -> xoá dòng


def test_dat_quyen_mot_giao_dich_mot_dong_nhat_ky_moi_thay_doi(gia, monkeypatch):
    """Nút Lưu trang Quản trị (21/10/2026): khoá bảng -> đọc quyền -> kiểm MỌI thay đổi -> áp ->
    mỗi thay đổi một dòng nhật ký (có `don_vi` để quản lý bên chỉ thấy bên mình), cùng giao dịch."""
    monkeypatch.setattr(GiaConn, "execute", _quyen_theo_email(gia, {
        AI: {"la_quan_tri": True, "ben": {}},
        "xem@hapas.vn": {"la_quan_tri": False, "ben": {"hapas": "xem", "matemade": "xem"}}}))
    gia.tra.update({r"count\(\*\)": [{"n": 1}],
                    r"SELECT ma FROM don_vi": [{"ma": "hapas"}]})
    kq = K.dat_quyen(AI, "xem@hapas.vn", None, {"hapas": "quan_ly", "matemade": None})
    assert kq["thay_doi"] == [("ben", "hapas", "xem", "quan_ly"), ("ben", "matemade", "xem", None)]
    assert len(gia.gd) == 1
    lenh = gia.gd[0].lenh
    assert lenh[0][0] == "LOCK TABLE nguoi_xem, quyen IN SHARE ROW EXCLUSIVE MODE"
    sql = [s for s, _ in lenh]
    ghi = [i for i, s in enumerate(sql) if s.startswith(("INSERT INTO quyen", "DELETE FROM quyen"))]
    nk = [(i, p) for i, (s, p) in enumerate(lenh) if s.startswith("INSERT INTO nhat_ky")]
    assert len(ghi) == 2 and [p[1] for _, p in nk] == ["luu_quyen", "xoa_quyen"]
    assert all(i > max(ghi) for i, _ in nk), "nhật ký ghi SAU khi áp"
    assert '"don_vi": "hapas"' in nk[0][1][3] and '"don_vi": "matemade"' in nk[1][1][3]


def test_dat_quyen_mot_thay_doi_sai_thi_khong_ap_gi(gia, monkeypatch):
    monkeypatch.setattr(GiaConn, "execute", _quyen_theo_email(gia, {
        AI: {"la_quan_tri": False, "ben": {"hapas": "quan_ly"}},
        "xem@hapas.vn": {"la_quan_tri": False, "ben": {"hapas": "xem", "matemade": "xem"}}}))
    gia.tra[r"count\(\*\)"] = [{"n": 1}]
    with pytest.raises(K.LoiDuLieu, match="quản lý của bên này"):
        K.dat_quyen(AI, "xem@hapas.vn", None, {"hapas": None, "matemade": None})
    with pytest.raises(K.LoiDuLieu, match="Chỉ quản trị viên"):
        K.dat_quyen(AI, "moi@hapas.vn", True, {"hapas": "xem"})
    for c in gia.gd:
        assert not any(s.startswith(("DELETE", "INSERT", "UPDATE")) for s, _ in c.lenh)


def test_dat_quyen_khong_bo_quan_tri_cuoi_va_ben_phai_co(gia, monkeypatch):
    monkeypatch.setattr(GiaConn, "execute", _quyen_theo_email(gia, {
        AI: {"la_quan_tri": True, "ben": {}}}))
    gia.tra[r"count\(\*\)"] = [{"n": 0}]
    with pytest.raises(K.LoiDuLieu, match="cuối cùng"):
        K.dat_quyen(AI, AI, False, {"hapas": "xem"})
    gia.tra[r"SELECT ma FROM don_vi"] = []
    with pytest.raises(K.LoiDuLieu, match="Không có bên này"):
        K.dat_quyen(AI, "moi@hapas.vn", None, {"ben-la": "xem"})
    for c in gia.gd:
        assert not any(s.startswith(("DELETE", "INSERT", "UPDATE")) for s, _ in c.lenh)


def test_quyen_cua_doc_dung_cot_mark_duoc_cap(gia):
    """`quyen_cua` chạy bằng role mark (tool hỏi đáp): chỉ cột đã GRANT trong schema.sql."""
    gia.tra[r"FROM nguoi_xem n WHERE n.email"] = [{"la_quan_tri": False,
                                                    "ben": {"hapas": "xem", "x": "lạ"}}]
    assert K.quyen_cua("XEM@hapas.vn") == {"la_quan_tri": False, "ben": {"hapas": "xem"}}
    assert K.vai_tro("xem@hapas.vn") == "xem"
    sql, ts = gia.gd[0].lenh[0]
    assert ts == ("xem@hapas.vn",)
    assert set(re.findall(r"\bn\.(\w+)", sql)) <= {"email", "la_quan_tri"}
    assert set(re.findall(r"\bq\.(\w+)", sql)) <= {"email", "don_vi", "vai_tro"}
    assert "GRANT SELECT (la_quan_tri) ON nguoi_xem TO mark;" in SCHEMA
    assert "GRANT SELECT (email, don_vi, vai_tro) ON quyen TO mark;" in SCHEMA
    assert "GRANT SELECT ON don_vi TO mark;" in SCHEMA
    gia.tra.pop(r"FROM nguoi_xem n WHERE n.email")
    assert K.quyen_cua("la@hapas.vn") is None and K.vai_tro("la@hapas.vn") is None


def test_schema_phan_quyen_ben_chay_lai_an_toan():
    """Chuyển đổi 19/10/2026 trong schema.sql (chạy lại mỗi lần deploy): mọi câu chỉ chạm dòng
    chưa chuyển, không đè thay đổi làm sau trên dashboard."""
    s = SCHEMA
    assert s.index("CREATE TABLE IF NOT EXISTS don_vi") < s.index("CREATE TABLE IF NOT EXISTS du_an")
    assert "('hapas', 'HAPAS'), ('matemade', 'MATEMADE')\n  ON CONFLICT (ma) DO NOTHING" in s
    assert "ALTER TABLE du_an ADD COLUMN IF NOT EXISTS don_vi TEXT REFERENCES don_vi(ma)" in s
    assert ("CASE WHEN ma LIKE '%matemade%' THEN 'matemade' ELSE 'hapas' END\n  WHERE don_vi IS "
            "NULL;") in s
    assert "is_nullable = 'YES'" in s and "ALTER COLUMN don_vi SET NOT NULL" in s
    assert "ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS la_quan_tri BOOLEAN NOT NULL DEFAULT FALSE" in s
    # quản trị viên đầu tiên: chỉ khi chưa có ai
    m = re.search(r"INSERT INTO nguoi_xem \(email, vai_tro, them_boi, la_quan_tri\)(.*?);", s, re.DOTALL)
    assert "'thamnt@hapas.vn', 'thienlq@hapas.vn'" in m.group(1)
    assert "WHERE NOT EXISTS (SELECT 1 FROM nguoi_xem WHERE la_quan_tri)" in m.group(1)
    # nganlt / itsupport + quy tắc chung: chỉ người chưa có dòng quyền nào, không thêm người mới
    khoi = re.findall(r"INSERT INTO quyen \(email, don_vi, vai_tro, them_boi\)(.*?);", s, re.DOTALL)
    assert len(khoi) == 2
    assert "('nganlt@hapas.vn', 'quan_ly'), ('itsupport@hapas.vn', 'xem')" in khoi[0]
    assert "JOIN nguoi_xem n" in khoi[0]
    assert all("NOT EXISTS (SELECT 1 FROM quyen q WHERE q.email = n.email)" in k for k in khoi)
    assert "NOT n.la_quan_tri" in khoi[1] and "ON CONFLICT (email, don_vi) DO NOTHING" in khoi[1]
    assert s.index("'nganlt@hapas.vn'") < s.index("SELECT n.email, 'hapas', n.vai_tro")
    assert "GRANT INSERT, UPDATE, DELETE ON quyen TO lang_nghe_web;" in s
    from dashboard import dong_bo_bq
    assert not {"quyen", "don_vi", "nguoi_xem"} & set(dong_bo_bq.BANG)


def _cot(bang: str) -> set[str]:
    khoi = re.search(rf"CREATE TABLE IF NOT EXISTS {bang} \((.*?)\n\);", SCHEMA, re.DOTALL).group(1)
    return set(re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE))


def test_cot_doc_co_trong_schema():
    for cot, bang in ((K._COT_NGUON, "nguon"), (K._COT_DE_XUAT, "de_xuat")):
        assert {c.strip() for c in cot.split(",")} <= _cot(bang)
    assert {re.split(r"[\s:]", c.strip())[0] for c in K._COT_DU_AN.split(",")} <= _cot("du_an")
    assert {c.strip().removeprefix("l.") for c in K._COT_LICH.split(",")} <= _cot("lich_quet")


def test_them_lich_khoa_du_an_va_chan_qua_toi_da(gia):
    """Khoá dòng dự án TRƯỚC khi đếm: hai người cùng tạo không vượt LICH_TOI_DA."""
    gia.tra.update({r"SELECT 1 AS co FROM du_an": [{"co": 1}],
                    r"count\(\*\)": [{"n": K.LICH_TOI_DA}]})
    with pytest.raises(K.LoiDuLieu, match="tối đa"):
        K.them_lich(AI, "hapas", LICH)
    sql = [s for s, _ in gia.gd[0].lenh]
    assert "FOR UPDATE" in sql[0] and not any(s.startswith("INSERT") for s in sql)
    gia.tra.pop(r"SELECT 1 AS co FROM du_an")
    with pytest.raises(K.LoiDuLieu, match="Không còn dự án"):
        K.them_lich(AI, "khong", LICH)


def test_cac_luot_chi_doc_phan_dau_ghi_chu_ban_du_doc_rieng(gia):
    """Soát 17/10/2026 (L5): ghi chú lượt giữ tới 20.000 ký tự — trang Ngân sách đọc
    `GHI_CHU_DAU` ký tự đầu + độ dài thật, API chỉ số không đọc cột, bản đủ đọc từng lượt."""
    gia.tra[r"count\(\*\)"] = [{"n": 3}]
    K.cac_luot("hapas", 2, 20)
    sql, ts = gia.gd[0].lenh[1]
    assert f"left(ghi_chu, {K.GHI_CHU_DAU}) AS ghi_chu" in sql
    assert "length(ghi_chu) AS ghi_chu_dai" in sql and ts == ("hapas", 20, 20)
    K.cac_luot("hapas", 1, 1, ghi_chu=False)
    sql, _ = gia.gd[1].lenh[1]
    assert "NULL::text AS ghi_chu" in sql and "left(ghi_chu" not in sql
    assert "length(ghi_chu" not in sql
    gia.tra[r"SELECT ghi_chu FROM luot_quet"] = [{"ghi_chu": "đủ chữ"}]
    assert K.ghi_chu_luot("hapas", "11") == "đủ chữ"
    sql, ts = gia.gd[2].lenh[0]
    assert "WHERE du_an = %s AND id = %s" in sql and ts == ("hapas", 11)
    gia.tra.pop(r"SELECT ghi_chu FROM luot_quet")
    assert K.ghi_chu_luot("hapas", 99) is None


def test_cac_lich_kem_luot_gan_nhat_cua_lich(gia):
    K.cac_lich("hapas")
    sql, ts = gia.gd[0].lenh[0]
    assert "LEFT JOIN LATERAL" in sql and "WHERE lich_id = l.id ORDER BY id DESC LIMIT 1" in sql
    assert ts == ("hapas",)


def test_chi_ghi_bang_role_lang_nghe_web_duoc_ghi():
    """Quyền theo schema.sql: INSERT/UPDATE/DELETE du_an, nguon, nguoi_xem, lich_quet; UPDATE 3 cột
    của de_xuat; INSERT nhat_ky. Dashboard KHÔNG ghi bai/luot_quet/chi_so_ngay (phần của Mark)."""
    src = (GOC / "dashboard" / "kho.py").read_text(encoding="utf-8")
    ghi = set(re.findall(r"(?:INSERT INTO|UPDATE|DELETE FROM) ([a-z_]+)", src))
    assert ghi <= {"du_an", "nguon", "nguoi_xem", "nhat_ky", "de_xuat", "lich_quet", "quyen",
                   "don_vi"}
    assert "GRANT INSERT, UPDATE, DELETE ON lich_quet TO lang_nghe_web;" in SCHEMA
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


def test_tran_platform_chua_co_va_khong_cham_kho(gia):
    """Trần platform (KDLA) chưa có: luôn None, không mở kết nối (Mark sẽ ghi vào kho sau)."""
    assert K.tran_platform("hapas") is None and K.tran_platform() is None
    assert gia.gd == []


def test_thieu_psycopg_bao_loi_kho(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)
    with pytest.raises(K.LoiKho, match="psycopg"):
        K.kiem_tra()


# ─────────────────── danh bạ Lark trong nguoi_xem (17/10/2026) ───────────────────
COT_DANH_BA = ("ten_lark", "chuc_danh", "phong_ban", "trang_thai_lark", "danh_ba_loi",
               "danh_ba_luc", "dang_nhap_cuoi", "lark_open_id", "lark_union_id", "lark_user_id")


def test_cot_danh_ba_co_trong_schema_va_co_mo_ta():
    """Cột mới thêm bằng ADD COLUMN IF NOT EXISTS (chạy lại schema.sql không hỏng) + mô tả cột
    theo quy chuẩn description; `nguoi_xem` không đẩy BigQuery nên không có bản sao BQ."""
    for cot in COT_DANH_BA:
        assert f"ALTER TABLE nguoi_xem ADD COLUMN IF NOT EXISTS {cot} " in SCHEMA, cot
        assert f"COMMENT ON COLUMN nguoi_xem.{cot} IS " in SCHEMA, cot
    from dashboard import dong_bo_bq
    assert "nguoi_xem" not in dong_bo_bq.BANG


def test_cac_nguoi_xem_doc_cot_danh_ba_va_lan_dang_nhap(gia):
    K.cac_nguoi_xem()
    sql = gia.gd[0].lenh[0][0]
    for cot in COT_DANH_BA[:-2]:          # union_id/user_id chỉ lưu, trang không cần đọc
        assert cot in sql, cot
    assert "COALESCE(n.dang_nhap_cuoi" in sql and "'dang_nhap_lan_dau'" in sql


def test_ghi_danh_ba_khong_ghi_nhat_ky(gia):
    K.ghi_danh_ba({"a@hapas.vn": {"trang_thai": "hoat_dong", "ten": "A", "chuc_danh": "CV",
                                  "phong_ban": "MKT"},
                   "b@hapas.vn": {"trang_thai": "khong_co", "ten": None, "chuc_danh": None,
                                  "phong_ban": None}})
    K.ghi_loi_danh_ba(["a@hapas.vn"], "thieu_quyen")
    lenh = [x for g in gia.gd for x in g.lenh]
    assert all(s.startswith("UPDATE nguoi_xem SET") for s, _ in lenh)
    assert lenh[0][1] == ("hoat_dong", "A", "CV", "MKT", None, "a@hapas.vn")
    assert "lark_open_id = COALESCE(%s, lark_open_id)" in lenh[0][0]
    assert "danh_ba_loi = NULL" in lenh[0][0]
    assert lenh[-1][1] == ("thieu_quyen", ["a@hapas.vn"])
