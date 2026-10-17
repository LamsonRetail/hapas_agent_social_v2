"""Đồng bộ kho lắng nghe → BigQuery (`dashboard/dong_bo_bq.py`), đợt 2 — 14/10/2026.

Không Postgres, không BigQuery thật: kho giả hiểu đúng các dạng câu SQL module sinh ra (chặn trên,
lô theo bộ (mốc, khoá), mốc đồng bộ); BigQuery giả ghi lại từng MERGE."""
from __future__ import annotations

import contextlib
import datetime
import decimal
import re
from pathlib import Path

import pytest

from dashboard import dong_bo_bq as D

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 10, 14, 1, 30, tzinfo=UTC)
GOC = Path(__file__).resolve().parents[1]


def _moc(bang, r):
    if bang == "bai":
        return r["cap_nhat_cuoi"]
    if bang == "luot_quet":
        return max(r["bat_dau"], r["ket_thuc"] or r["bat_dau"])
    return r["ngay"]


class GiaKho:
    """Đủ để chạy các câu SQL của dong_bo_bq trên dữ liệu trong bộ nhớ."""

    def __init__(self, du_lieu, thieu_cot=()):
        self.du_lieu = du_lieu
        self.moc: dict[str, dict] = {}
        self.cau: list[str] = []
        self._kq: list = []
        self.thieu_cot = set(thieu_cot)       # cột Postgres chưa có (schema.sql chưa chạy)

    @contextlib.contextmanager
    def __call__(self):
        yield self

    def execute(self, sql, ts=None):
        self.cau.append(sql)
        self._kq = self._chay(sql, ts)
        return self

    def fetchone(self):
        return self._kq[0] if self._kq else None

    def fetchall(self):
        return list(self._kq)

    def _chay(self, sql, ts):
        if sql.startswith("SELECT moc FROM dong_bo_bq"):
            r = self.moc.get(ts[0])
            return [{"moc": r["moc"]}] if r else []
        if sql.startswith("INSERT INTO dong_bo_bq"):
            bang, moc, so, loi = ts
            cu = self.moc.get(bang, {})
            self.moc[bang] = {"moc": moc if moc is not None else cu.get("moc"), "so_dong": so,
                              "loi": loi}
            return []
        if sql.startswith("SELECT bang, moc"):
            return [{"bang": b, **v} for b, v in self.moc.items()]
        if "information_schema.columns" in sql:
            return [{"column_name": c} for c in ts[1] if c not in self.thieu_cot]
        bang = re.search(r" FROM (\w+)", sql).group(1)
        rows = self.du_lieu.get(bang, [])
        if "AS hi" in sql:
            return [{"hi": max((_moc(bang, r) for r in rows), default=None)}]
        b = D.BANG[bang]
        if b["kieu"] == "toan_bo":
            return sorted((dict(r) for r in rows), key=lambda r: [r[k] for k in b["khoa"]])
        ra = []
        for r in rows:
            m = _moc(bang, r)
            if m > ts["hi"]:
                continue
            if "tu" in ts:
                if b["kieu"] == "theo_ngay":
                    if m < ts["tu"] - datetime.timedelta(days=1):
                        continue
                elif m <= ts["tu"] - datetime.timedelta(minutes=15):
                    continue
            khoa = (m, *[r[k] for k in b["khoa"]])
            if "sau_moc" in ts and khoa <= (ts["sau_moc"], *[ts[f"sau_{k}"] for k in b["khoa"]]):
                continue
            ra.append({**r, "_moc": m})
        ra.sort(key=lambda r: (r["_moc"], *[r[k] for k in b["khoa"]]))
        return ra[:ts["lo"]]


class GiaBQ:
    def __init__(self, hong_lan=None):
        self.goi: list[tuple[str, list]] = []
        self.hong_lan = hong_lan

    def chay(self, sql, tham_so):
        self.goi.append((sql, tham_so))
        if self.hong_lan and len(self.goi) == self.hong_lan:
            raise RuntimeError("quota")
        return len(tham_so)


def _bai(i, luc, du_an="hapas"):
    return {"du_an": du_an, "khoa": f"tiktok:{i:05d}", "nen_tang": "tiktok", "nguon_id": 1,
            "kieu_quet": "theo_doi", "link": f"https://t/{i}", "tac_gia": "A", "tai_khoan": "a",
            "followers": None, "dang_luc": luc, "noi_dung": "x", "hashtag": "", "khop_tu_khoa": True,
            "sac_thai": None, "chu_de": None, "ly_do_giu": "brand", "xem": 1, "thich": None,
            "binh_luan": 2, "chia_se": None, "thay_lan_dau": luc, "cap_nhat_cuoi": luc,
            "luot_dau": 1, "luot_cuoi": 1}


def _tham_so(bang, rows):
    return rows                    # bỏ qua thư viện google-cloud-bigquery trong bộ thử


@pytest.fixture(autouse=True)
def bat(monkeypatch):
    monkeypatch.setenv("BQ_DATASET", "ganesha-381907.SOCIAL_LISTENING")


# ───────────────────────────── SQL ─────────────────────────────
def test_merge_dung_khoa_va_chi_bang_nho_moi_xoa():
    s = D.sql_merge("bai")
    assert s.startswith("MERGE `ganesha-381907.SOCIAL_LISTENING.bai` T")
    assert "ON T.du_an = S.du_an AND T.khoa = S.khoa" in s and "DELETE" not in s
    assert all(f"S.{c}" in s for c, _ in D.BANG["bai"]["cot"])
    assert "dong_bo_luc = CURRENT_TIMESTAMP()" in s
    assert D.sql_merge("nguon").endswith("WHEN NOT MATCHED BY SOURCE THEN DELETE")
    assert "DELETE" not in D.sql_merge("luot_quet")


def _cot_bigquery() -> dict[str, list[tuple[str, str]]]:
    sql = (GOC / "deploy" / "lang-nghe" / "bigquery.sql").read_text(encoding="utf-8")
    ra = {}
    for bang, khoi in re.findall(r"CREATE TABLE IF NOT EXISTS `[^`]+\.(\w+)`\s*\((.*?)\n\)",
                                 sql, re.DOTALL):
        ra[bang] = [(m.group(1), m.group(2))
                    for m in re.finditer(r"^\s{2}(\w+)\s+(ARRAY<STRING>|\w+)\s+OPTIONS", khoi,
                                         re.MULTILINE)]
    return ra


def test_cot_va_kieu_khop_bigquery_sql():
    """Lệch tên/kiểu giữa MERGE và bảng BigQuery chỉ lộ ra khi chạy thật — canh ở đây."""
    bq = _cot_bigquery()
    assert set(bq) == set(D.BANG)
    for bang, b in D.BANG.items():
        assert bq[bang] == [*b["cot"], ("dong_bo_luc", "TIMESTAMP")], bang


def test_cot_co_trong_kho_postgres_va_khong_day_email():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    for bang, b in D.BANG.items():
        khoi = re.search(rf"CREATE TABLE IF NOT EXISTS {bang} \((.*?)\n\);", sql,
                         re.DOTALL).group(1)
        cot_pg = set(re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE))
        assert {c for c, _ in b["cot"]} <= cot_pg, bang
        assert not {"sua_boi", "them_boi"} & {c for c, _ in b["cot"]}
    assert "nguoi_xem" not in D.BANG and "nhat_ky" not in D.BANG


def test_chuan_gia_tri():
    naive = datetime.datetime(2026, 10, 14, 8, 0)  # noqa: DTZ001 — cố ý: kiểm nhánh không múi giờ
    assert D.chuan_gia_tri("TIMESTAMP", naive) == "2026-10-14T08:00:00+00:00"
    vn = datetime.datetime(2026, 10, 14, 15, 0,
                           tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
    assert D.chuan_gia_tri("TIMESTAMP", vn) == "2026-10-14T08:00:00+00:00"
    assert D.chuan_gia_tri("DATE", datetime.date(2026, 10, 14)) == "2026-10-14"
    assert D.chuan_gia_tri("NUMERIC", decimal.Decimal("0.0123")) == "0.0123"
    assert D.chuan_gia_tri("ARRAY<STRING>", None) == [] and D.chuan_gia_tri("INT64", None) is None


# ───────────────────────────── đồng bộ ─────────────────────────────
def test_lo_cung_moc_khong_bo_sot(monkeypatch):
    """1.201 bài cùng một cap_nhat_cuoi (Mark ghi cả lô trong một giao dịch) → đủ 1.201 dòng."""
    monkeypatch.setattr(D, "LO", 500)
    kho = GiaKho({"bai": [_bai(i, T0) for i in range(1201)]})
    bq = GiaBQ()
    kq = D.dong_bo_bang("bai", kho, bq, _tham_so)
    assert kq == {"bang": "bai", "so_dong": 1201, "loi": None}
    da_day = [r["khoa"] for _, ts in bq.goi for r in ts]
    assert len(da_day) == 1201 == len(set(da_day))
    assert [len(ts) for _, ts in bq.goi] == [500, 500, 201]
    assert kho.moc["bai"]["moc"] == T0


def test_luot_sau_chi_lay_dong_moi_va_cua_so_15_phut():
    rows = [_bai(i, T0) for i in range(3)]
    kho = GiaKho({"bai": rows})
    D.dong_bo_bang("bai", kho, GiaBQ(), _tham_so)
    rows[1]["cap_nhat_cuoi"] = T0 + datetime.timedelta(hours=2)        # bài được cập nhật số
    rows.append(_bai(9, T0 + datetime.timedelta(hours=2)))
    rows.append(_bai(8, T0 - datetime.timedelta(minutes=5)))           # commit muộn, mốc cũ
    bq = GiaBQ()
    kq = D.dong_bo_bang("bai", kho, bq, _tham_so)
    khoa = {r["khoa"] for _, ts in bq.goi for r in ts}
    # T0 − 5' nằm trong cửa sổ lùi 15' nên không mất; bài ở T0 được đọc lại — MERGE không nhân đôi.
    assert {"tiktok:00001", "tiktok:00009", "tiktok:00008"} <= khoa
    assert kq["loi"] is None and kho.moc["bai"]["moc"] == T0 + datetime.timedelta(hours=2)


def test_loi_bigquery_giu_moc_cu_va_ghi_loi(monkeypatch):
    monkeypatch.setattr(D, "LO", 2)
    kho = GiaKho({"bai": [_bai(i, T0 + datetime.timedelta(seconds=i)) for i in range(5)]})
    kho.moc["bai"] = {"moc": T0 - datetime.timedelta(days=1)}
    kq = D.dong_bo_bang("bai", kho, GiaBQ(hong_lan=2), _tham_so)
    assert kq["loi"].startswith("RuntimeError: quota") and kq["so_dong"] == 2
    assert kho.moc["bai"]["moc"] == T0 - datetime.timedelta(days=1)     # không dời mốc


def test_chi_so_ngay_doc_lai_tu_moc_tru_mot_ngay():
    ngay = datetime.date(2026, 10, 14)
    rows = [{"du_an": "hapas", "khoa": f"tiktok:{i}", "ngay": ngay - datetime.timedelta(days=d),
             "xem": 1, "thich": 1, "binh_luan": 1, "chia_se": None}
            for i in range(2) for d in range(4)]
    kho = GiaKho({"chi_so_ngay": rows})
    kho.moc["chi_so_ngay"] = {"moc": ngay}
    bq = GiaBQ()
    D.dong_bo_bang("chi_so_ngay", kho, bq, _tham_so)
    assert sorted({r["ngay"] for _, ts in bq.goi for r in ts}) == ["2026-10-13", "2026-10-14"]


def test_bang_nho_nap_lai_toan_bo_va_luot_quet_theo_ket_thuc():
    kho = GiaKho({
        "du_an": [{"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"], "tu_loai_tru": None,
                   "boi_canh": "", "thi_truong": "VN", "tran_usd_thang": 5, "dang_bat": True,
                   "tao_luc": T0, "sua_luc": T0}],
        "luot_quet": [{"id": 1, "du_an": "hapas", "kieu": "theo_doi", "ma_viec": "t1",
                       "job_id": None, "bat_dau": T0, "ket_thuc": None, "so_nguon": 3,
                       "so_nguon_loi": 0, "bai_moi": 0, "bai_cap_nhat": 0, "chi_phi_usd": 0,
                       "trang_thai": "dang_chay", "loi": None, "ghi_chu": None}],
    })
    bq = GiaBQ()
    kq = D.chay(kho, bq, _tham_so)
    theo = {x["bang"]: x for x in kq["bang"]}
    assert theo["du_an"]["so_dong"] == 1 and theo["luot_quet"]["so_dong"] == 1
    assert bq.goi[0][1][0]["tu_loai_tru"] == []            # mảng NULL -> rỗng
    # Lượt kết thúc sau đó: mốc max(bat_dau, ket_thuc) đổi → lượt đồng bộ sau lấy lại.
    kho.du_lieu["luot_quet"][0].update(ket_thuc=T0 + datetime.timedelta(minutes=40),
                                       trang_thai="xong")
    bq2 = GiaBQ()
    D.dong_bo_bang("luot_quet", kho, bq2, _tham_so)
    assert bq2.goi[0][1][0]["trang_thai"] == "xong"


class GiaBQCot(GiaBQ):
    """BigQuery giả biết cột của bảng đích (`_BigQuery.cot` — INFORMATION_SCHEMA)."""

    def __init__(self, thieu=(), hong=False):
        super().__init__()
        self.thieu, self.hong = set(thieu), hong

    def cot(self, bang):
        if self.hong:
            raise RuntimeError("không có quyền")
        return {c for c, _ in D.BANG[bang]["cot"]} - self.thieu


def _du_an():
    return {"du_an": [{"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"], "tu_loai_tru": [],
                       "boi_canh": "", "thi_truong": "VN", "tran_usd_thang": 5,
                       "dang_bat": True, "tao_luc": T0, "sua_luc": T0, "hashtag": ["hapas"]}]}


@pytest.mark.parametrize("kho_thieu, bq_thieu, ben", [
    ({"hashtag"}, set(), "Postgres"), (set(), {"hashtag"}, "BigQuery"),
    ({"hashtag"}, {"hashtag"}, "Postgres và BigQuery")])
def test_thieu_cot_hashtag_bo_cot_canh_bao_khong_hong_bang(kho_thieu, bq_thieu, ben):
    """Soát 18/10/2026: `du_an.hashtag` thêm sau khi bảng đã tạo. Bên nào chưa chạy ALTER thì bản
    cũ hỏng CẢ câu MERGE (du_an không đồng bộ nữa). Nay bỏ cột đó, cảnh báo, các cột khác vẫn đẩy."""
    kho = GiaKho(_du_an(), thieu_cot=kho_thieu)
    bq = GiaBQCot(thieu=bq_thieu)
    kq = D.dong_bo_bang("du_an", kho, bq, _tham_so)
    assert kq["loi"] is None and kq["so_dong"] == 1
    assert kq["canh_bao"].startswith(f"bỏ cột hashtag: {ben} chưa có cột")
    sql, rows = bq.goi[0]
    assert "hashtag" not in sql and "hashtag" not in rows[0] and rows[0]["ma"] == "hapas"
    assert next(c for c in kho.cau if c.startswith("SELECT ma,")).count("hashtag") == 0
    assert kho.moc["du_an"]["loi"].startswith("cảnh báo: bỏ cột hashtag")


def test_du_cot_hashtag_thi_day_ca_hashtag():
    kho = GiaKho(_du_an())
    bq = GiaBQCot()
    kq = D.dong_bo_bang("du_an", kho, bq, _tham_so)
    assert kq == {"bang": "du_an", "so_dong": 1, "loi": None}
    assert "S.hashtag" in bq.goi[0][0] and bq.goi[0][1][0]["hashtag"] == ["hapas"]
    # Không đọc được INFORMATION_SCHEMA: MERGE đủ cột như trước, kèm cảnh báo.
    kq = D.dong_bo_bang("du_an", GiaKho(_du_an()), GiaBQCot(hong=True), _tham_so)
    assert kq["loi"] is None and "không đọc được cột BigQuery" in kq["canh_bao"]


def test_chua_bat_va_khoa_mot_luot(monkeypatch):
    monkeypatch.setenv("BQ_DATASET", "")
    assert D.chay(GiaKho({}), GiaBQ(), _tham_so) == {"bo_qua": "chưa bật (thiếu BQ_DATASET)"}
    monkeypatch.setenv("BQ_DATASET", "p.d")
    assert D._KHOA.acquire(blocking=False)
    try:
        assert D.chay(GiaKho({}), GiaBQ(), _tham_so)["bo_qua"] == "đang có lượt đồng bộ khác"
    finally:
        D._KHOA.release()


def test_cai_vao_chi_khi_bat(monkeypatch):
    class App:
        class state:
            pass
    App.state.sau_cap_nhat = []
    chay = []
    monkeypatch.setattr(D.threading, "Thread",
                        lambda **k: type("T", (), {"start": lambda s: chay.append(k["name"])})())
    monkeypatch.setenv("BQ_DATASET", "")
    D.cai_vao(App)
    assert App.state.sau_cap_nhat == [] and chay == []
    monkeypatch.setenv("BQ_DATASET", "p.d")
    D.cai_vao(App)
    assert len(App.state.sau_cap_nhat) == 1 and chay == ["dong_bo_bq"]
