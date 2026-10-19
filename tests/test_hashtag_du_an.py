"""Hashtag riêng của dự án (chủ dự án 18/10/2026: "dự án ở đây tôi nghĩ là bỏ phần thị trường, thay
bằng phần hashtag").

Từ ô nhập trên trang Nguồn (chuẩn hoá như Mark gửi actor) tới hai đường Mark dùng hashtag —
Instagram tìm theo hashtag và feed hashtag TikTok —, bản sao ước tính của dashboard (`chi_phi`),
kho (cột mới, code lên VPS trước schema vẫn chạy) và đồng bộ BigQuery. Thị trường: bỏ khỏi giao
diện nhưng GIỮ cột + cổng thị trường của Mark (dự án mới mặc định VN, sửa dự án không đổi)."""
from __future__ import annotations

import contextlib
import contextvars
import re
import time
import types
from pathlib import Path

import pytest

import apify_tool as A
import lang_nghe_db as K
import theo_doi as T
from dashboard import chi_phi as CP
from dashboard import dong_bo_bq as DBQ
from dashboard import kho as KD
from dashboard import nhap_lieu as NL

GOC = Path(__file__).resolve().parents[1]


@pytest.fixture
def mo(monkeypatch):
    """Như `test_duong_moi.mo`: mọi nền tảng bật, có key YouTube, AI không phán gì."""
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 5.0, True))
    monkeypatch.setattr(A, "_youtube_co_key", lambda: True)
    monkeypatch.setattr(A, "_phan_xu_ai", lambda *a, **k: ({}, {"_sac_thai": {}, "_chu_de": {},
                                                                 "trang_thai": "đã chạy"}))
    import viec_nen
    monkeypatch.setattr(viec_nen, "tat_ca", list)
    monkeypatch.setattr(T, "_kiem_do_phu", lambda *a, **k: {})
    return monkeypatch


# ───────────────────────────── 1. nhập liệu ─────────────────────────────
@pytest.mark.parametrize("vao, ra", [
    ("#hapas, #YeuTuDieuNhoNhat", ["hapas", "yeutudieunhonhat"]),
    ("#hapas #hapassuperbrandday", ["hapas", "hapassuperbrandday"]),      # dán từ caption
    ("TúiHAPAS; quà_tặng\n#hapas, HAPAS", ["tuihapas", "qua_tang", "hapas"]),
    # Soát 18/10/2026: dấu tách là phẩy, chấm phẩy, xuống dòng, tab và '#'; dấu cách TRONG một
    # đoạn được nối lại — "Túi HAPAS" là MỘT tag (bản trước ra tag rác "tui" chiếm suất Instagram).
    ("Túi HAPAS", ["tuihapas"]),
    ("hapas vn\tTúi HAPAS  #quatanghapas", ["hapasvn", "tuihapas", "quatanghapas"]),
    ("#Yêu từ điều nhỏ nhất, Túi HAPAS", ["yeutudieunhonhat", "tuihapas"]),
    ("#Đồng hồ 20/10", ["dongho2010"]),
    ("🥰, , #", []),
    ("", []),
])
def test_chuan_hoa_hashtag_dung_dang_mark_gui_actor(vao, ra):
    assert NL.hashtag(vao) == ra
    assert A.hashtag_ig_ds(ra) == ra, "đã đúng dạng apify_tool.hashtag_ig — Mark không đổi gì"


def test_hashtag_mot_doan_trung_cach_mark_suy_tu_tu_khoa():
    """Một đoạn có dấu cách ra đúng tag Mark tự suy từ từ khoá cùng chữ (`apify_tool.hashtag_ig`
    — hàm của Mark không đổi: từ khoá "túi hapas" vẫn là #tuihapas)."""
    for x in ("Túi HAPAS", "túi xách hapas", "#Yêu từ điều nhỏ nhất"):
        assert NL.hashtag(x) == A.hashtag_ig_ds([x])
    assert A.hashtag_ig("túi hapas") == "tuihapas"


def test_hashtag_qua_dai_hoac_qua_nhieu_bao_loi():
    with pytest.raises(NL.LoiNhap, match="quá dài"):
        NL.hashtag("a" * (NL.HASHTAG_DAI_TOI_DA + 1))
    with pytest.raises(NL.LoiNhap, match=f"Tối đa {NL.HASHTAG_TOI_DA}"):
        NL.hashtag(",".join(f"t{i}" for i in range(NL.HASHTAG_TOI_DA + 1)))
    assert len(NL.hashtag(",".join(f"t{i}" for i in range(NL.HASHTAG_TOI_DA)))) == 50


def test_bieu_mau_du_an_khong_con_thi_truong():
    moi = NL.du_an({"ma": "x1", "ten": "X", "tu_khoa": "x", "hashtag": "#x"}, moi=True)
    assert moi["thi_truong"] == "VN" and moi["hashtag"] == ["x"]
    assert NL.du_an({"ma": "x1", "ten": "X", "tu_khoa": "x"}, moi=True)["hashtag"] == []
    sua = NL.du_an({"ten": "X", "tu_khoa": "x", "hashtag": ""}, moi=False)
    assert "thi_truong" not in sua and sua["hashtag"] == []          # xoá hết hashtag được
    cu = NL.du_an({"ten": "X", "tu_khoa": "x"}, moi=False)            # trang cũ còn mở
    assert "hashtag" not in cu and "thi_truong" not in cu
    assert NL.du_an({"ten": "X", "tu_khoa": "x", "thi_truong": "th"},
                    moi=False)["thi_truong"] == "TH"


# ───────────────────────────── 2. trang Nguồn ─────────────────────────────
def test_trang_nguon_o_hashtag_thay_thi_truong_va_giu_thi_truong_cu():
    from test_dashboard_app import QL, XEM, dang_nhap, tao, thong_bao
    _, c, kho = tao()
    kho.du_an["hapas"]["thi_truong"] = "TH"               # dự án cũ khác VN: phải giữ nguyên
    csrf = dang_nhap(c, QL)
    t = c.get("/nguon").text
    assert "Thị trường" not in t and 'name="thi_truong"' not in t
    assert "Chưa đặt — Mark tự lấy từ từ khoá" in t and t.count('name="hashtag"') == 2
    # Nhãn ô nói đúng luật tách (soát 18/10/2026): dấu cách không tách tag.
    assert t.count("dấu cách trong một hashtag được nối lại") == 2 and "dấu cách hoặc #" not in t
    r = c.post("/du-an/hapas/sua", data={"csrf": csrf, "ten": "HAPAS", "tu_khoa": "hapas",
                                         "hashtag": "#hapas, #Yêu từ điều nhỏ nhất",
                                         "dang_bat": "1"})
    assert "Đã lưu dự án" in thong_bao(c, r)
    d = kho.du_an["hapas"]
    assert d["hashtag"] == ["hapas", "yeutudieunhonhat"] and d["thi_truong"] == "TH"
    t = c.get("/nguon").text
    assert '<span class="the the--tag">#hapas</span>' in t
    assert 'value="#hapas, #yeutudieunhonhat"' in t
    assert re.search(r"Trần tháng <b>5,00</b> USD", t)
    dang_nhap(c, XEM)
    t = c.get("/nguon").text
    assert "#yeutudieunhonhat" in t and 'name="hashtag"' not in t


def test_them_du_an_moi_mac_dinh_vn_kem_hashtag():
    from test_dashboard_app import QL, dang_nhap, tao
    _, c, kho = tao()
    csrf = dang_nhap(c, QL)
    r = c.post("/du-an/them", data={"csrf": csrf, "ma": "moi", "ten": "Mới", "tu_khoa": "moi",
                                    "hashtag": "#Mới #moi2026", "don_vi": "hapas"})
    assert r.status_code == 303
    assert kho.du_an["moi"]["thi_truong"] == "VN" and kho.du_an["moi"]["hashtag"] == [
        "moi", "moi2026"]


# ───────────────────────────── 3. kho (dashboard + Mark) ─────────────────────────────
class _Conn:
    """Kết nối giả: trả cột `du_an.hashtag` có/không theo `co_cot`; ghi lại câu SQL."""

    def __init__(self, co_cot: bool):
        self.co_cot, self.lenh = co_cot, []

    def execute(self, sql, ts=None):
        self.lenh.append((sql, tuple(ts or ())))
        dong = ([{"co": 1}] if "information_schema.columns" in sql and self.co_cot
                else [{"ma": "hapas"}] if "RETURNING ma" in sql else [])
        return types.SimpleNamespace(fetchone=lambda: dong[0] if dong else None,
                                     fetchall=lambda: list(dong))


def _kho_gia(monkeypatch, mod, co_cot: bool) -> list[_Conn]:
    gd: list[_Conn] = []

    @contextlib.contextmanager
    def ket_noi(*a, **k):
        gd.append(_Conn(co_cot))
        yield gd[-1]
    monkeypatch.setattr(mod, "ket_noi", ket_noi)
    monkeypatch.setattr(mod, "_CO_HASHTAG", [])
    return gd


SUA = {"ten": "HAPAS", "tu_khoa": ["hapas"], "tu_loai_tru": [], "boi_canh": "", "dang_bat": True}


def test_kho_dashboard_chua_chay_schema_van_mo_trang_va_giu_thi_truong(monkeypatch):
    gd = _kho_gia(monkeypatch, KD, co_cot=False)
    KD.cac_du_an()
    assert "'{}'::text[] AS hashtag" in gd[-1].lenh[-1][0]          # trang không vỡ
    KD.sua_du_an("ql@hapas.vn", "hapas", dict(SUA))
    sql, ts = next(x for x in gd[-1].lenh if x[0].startswith("UPDATE du_an"))
    assert "thi_truong = COALESCE(%s, thi_truong)" in sql and "hashtag" not in sql
    assert ts[4] is None, "biểu mẫu không có ô thị trường: giữ giá trị đang lưu"
    KD.sua_du_an("ql@hapas.vn", "hapas", dict(SUA, hashtag=[]))      # ô trống: không cần cột
    with pytest.raises(KD.LoiDuLieu, match="chưa có cột hashtag"):
        KD.sua_du_an("ql@hapas.vn", "hapas", dict(SUA, hashtag=["hapas"]))


def test_kho_dashboard_co_cot_thi_doc_ghi_hashtag(monkeypatch):
    gd = _kho_gia(monkeypatch, KD, co_cot=True)
    KD.doc_du_an("hapas")
    assert gd[-1].lenh[-1][0].startswith(f"SELECT {KD._COT_DU_AN}, hashtag FROM du_an")
    KD.sua_du_an("ql@hapas.vn", "hapas", dict(SUA, hashtag=["hapas", "yeu"]))
    sql, ts = next(x for x in gd[-1].lenh if x[0].startswith("UPDATE du_an"))
    assert "hashtag = %s::text[]" in sql and ["hapas", "yeu"] in ts
    KD.them_du_an("ql@hapas.vn", dict(SUA, ma="moi", thi_truong="VN", hashtag=["moi"],
                                      don_vi="hapas"))
    sql, ts = next(x for x in gd[-1].lenh if x[0].startswith("INSERT INTO du_an"))
    assert "sua_boi, don_vi, hashtag)" in sql and ts[-1] == ["moi"]
    assert len(KD._CO_HASHTAG) == 1, "có cột rồi thì nhớ, không hỏi lại information_schema"


@pytest.mark.parametrize("co_cot", [True, False])
def test_mark_doc_du_an_co_hoac_chua_co_cot(monkeypatch, co_cot):
    gd = _kho_gia(monkeypatch, K, co_cot=co_cot)
    K.doc_du_an("hapas")
    sql = gd[-1].lenh[-1][0]
    assert ("cau_hinh, hashtag FROM du_an" in sql) if co_cot \
        else ("'{}'::text[] AS hashtag FROM du_an" in sql)


def test_schema_bigquery_va_dong_bo_co_cot_hashtag():
    sql = (GOC / "deploy" / "lang-nghe" / "schema.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE du_an ADD COLUMN IF NOT EXISTS hashtag TEXT[] NOT NULL DEFAULT '{}';" in sql
    assert re.search(r"COMMENT ON COLUMN du_an\.hashtag IS '.{200,}';", sql)
    assert "GRANT SELECT ON du_an, nguon TO mark;" in sql, "Mark đọc cả bảng → đọc được cột mới"
    bq = (GOC / "deploy" / "lang-nghe" / "bigquery.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS hashtag ARRAY<STRING> OPTIONS(description=" in bq
    assert ("hashtag", "ARRAY<STRING>") in DBQ.BANG["du_an"]["cot"]
    assert DBQ.dong_bq("du_an", [{"ma": "hapas", "hashtag": None}])[0]["hashtag"] == []


# ───────────────────────────── 4. Mark dùng hashtag ─────────────────────────────
DA = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas", "yeutudieunhonhat"],
      "tk_bat": True, "tk_so_bai": 15}
CO_TAG = dict(DA, hashtag=["#HAPAS", "hapas_superbrandday", "ab", "hapas"])


def test_nguon_tag_rong_thi_suy_tu_tu_khoa_nhu_cu():
    tu = T.tu_tim(DA)
    assert T.nguon_tag(DA, tu) == tu and T.nguon_tag(dict(DA, hashtag=[]), tu) == tu
    assert T._tu_cho("instagram", T.nguon_tag(DA, tu)) == ["hapas", "tuihapas", "yeutudieunhonhat"]
    assert T.tag_tiktok(T.nguon_tag(DA, tu)) == ["hapas", "yeutudieunhonhat"]


def test_nguon_tag_dung_hashtag_du_an_va_ban_sao_dashboard():
    tu = T.tu_tim(CO_TAG)
    assert T.hashtag_du_an(CO_TAG) == ["hapas", "hapas_superbrandday", "ab"]
    assert T._tu_cho("instagram", T.nguon_tag(CO_TAG, tu)) == [
        "hapas", "hapas_superbrandday", "ab"]
    assert T._tu_cho("instagram", T.nguon_tag(CO_TAG, tu), 2) == ["hapas", "hapas_superbrandday"]
    # TikTok: chuẩn `tiktok_api.chuan_tag` (bỏ '_'), chỉ tag 3–40 ký tự.
    assert T.tag_tiktok(T.nguon_tag(CO_TAG, tu)) == ["hapas", "hapassuperbrandday"]
    for da in (DA, CO_TAG, dict(CO_TAG, cau_hinh={"tu_khoa": {"instagram": {"so_tu": 2}}})):
        tu = T.tu_tim(da)
        assert CP.nguon_tag(da, CP.tu_tim(da)) == T.nguon_tag(da, tu)
        b = CP.bang_cau_hinh(da)
        so_tu = b["tu_khoa"]["instagram"]["so_tu"]
        assert b["tu_khoa"]["tiktok"]["hashtag"]["tag"] == T.tag_tiktok(T.nguon_tag(da, tu))
        assert b["tu_khoa"]["instagram"]["so_tu_gui"] == len(
            T._tu_cho("instagram", T.nguon_tag(da, tu), so_tu))
        assert b["tu_khoa"]["instagram"]["uoc"] == T.uoc_tu_khoa_nen_tang(
            "instagram", 15, T.nguon_tag(da, tu), so_tu)
        assert b["uoc_tk"] == pytest.approx(T.uoc_tu_khoa_du_an(da, fb_toi_da=10 ** 6), abs=1e-4)


def test_ngan_sach_uoc_tinh_theo_hashtag_du_an():
    import json

    from test_dashboard_app import QL, dang_nhap, tao
    _, c, kho = tao()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15, tu_khoa=["hapas", "túi hapas"],
                              hashtag=["hapassuperbrandday", "yeu_tu", "hapas"])
    dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    d = json.loads(re.search(r'id="ns-du-lieu">(.*?)</script>', t, re.DOTALL).group(1))
    assert d["hashtag_rieng"] == ["hapassuperbrandday", "yeu_tu", "hapas"]
    assert "Tìm theo hashtag của dự án (3 hashtag)" in t
    b = CP.bang_cau_hinh(kho.du_an["hapas"])
    assert f'data-o="tk-instagram" data-usd="{b["tu_khoa"]["instagram"]["uoc"]}"' in t


def test_tim_tu_khoa_instagram_tim_theo_hashtag_du_an(mo):
    from test_theo_doi import DU_AN, GiaKhoTk, GiaViec
    GiaKhoTk(mo)
    goi: dict = {}

    def tim(p):
        def f(q, limit, country, d_from, d_to, **k):
            goi[p] = list(q)
            return []
        return f
    mo.setattr(A, "_FETCH", {p: tim(p) for p in ("tiktok", "facebook", "instagram", "youtube")})
    da = dict(DU_AN, tu_khoa=["hapas", "túi hapas"], tk_bat=True, tk_so_bai=15,
              hashtag=["hapassuperbrandday", "yeutudieunhonhat"])
    contextvars.copy_context().run(T._tim_tu_khoa, GiaViec({}, []), da, 3, 5.0,
                                   time.monotonic() + 600)
    assert goi["instagram"] == ["hapassuperbrandday", "yeutudieunhonhat"]
    assert goi["tiktok"] == ["hapas", "túi hapas"], "tìm theo từ khoá không đổi"
    goi.clear()
    contextvars.copy_context().run(T._tim_tu_khoa, GiaViec({}, []), dict(da, hashtag=[]), 3,
                                   5.0, time.monotonic() + 600)
    assert goi["instagram"] == ["hapas", "tuihapas"], "chưa đặt hashtag: như trước 18/10"


@pytest.mark.tiktok_api
def test_feed_hashtag_tiktok_doc_hashtag_du_an(mo):
    from test_duong_moi import _chay_tk_tt
    from test_theo_doi import DU_AN
    da = dict(DU_AN, tu_khoa=["hapas", "túi hapas"], tk_bat=True, tk_so_bai=15,
              hashtag=["hapassuperbrandday"])
    _, goi, _ = _chay_tk_tt(mo, du_an=da)
    assert [set(trang) for trang, _ in goi["mau"]] == [{"hapassuperbrandday"}]
    T.ghi_moc_tk("hapas", {T.TK_TAG: {}})                  # nhịp 20 giờ: cho đọc lại ngay
    _, goi, _ = _chay_tk_tt(mo, du_an=dict(da, hashtag=[]))
    assert [set(trang) for trang, _ in goi["mau"]] == [{"hapas"}], "chưa đặt: từ khoá một chữ"
