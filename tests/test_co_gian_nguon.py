"""Co số bài mỗi lần theo NHỊP ĐĂNG của nguồn (18/10/2026, chủ dự án: "các luồng cào để tối ưu
output nhất có thể").

Nguồn theo dõi lấy N bài MỚI NHẤT mỗi lượt dù nguồn chỉ đăng 0,4–4 bài/ngày: HAPAS 6 trang Facebook
× 10 bài = 60 bài/lượt (thedoor 0,15 + 0,01 USD) trong khi kho 18/10 có 13–16 bài mỗi trang trong
4–36 ngày (`bai_theo_nguon`) — phần lặp chỉ để làm mới số liệu bài cũ. Mark co N theo số bài cao
nhất một ngày (14 ngày) × số ngày từ lần quét trước × 1,5 + 2 (sàn 3), lấy đủ N mỗi 7 ngày, khi
chiến dịch, khi lượt trước bão hoà; thedoor gom các trang thành run rẻ nhất."""
from __future__ import annotations

import datetime

import pytest

import lang_nghe_db as K
import theo_doi as T
from dashboard import chi_phi as CP

VN = datetime.timezone(datetime.timedelta(hours=7))
BAY = datetime.datetime(2026, 10, 18, 7, 0, tzinfo=VN)
CFG = CP.cau_hinh_co_gian({})


@pytest.mark.parametrize("p, max_ngay, khoang, ra", [
    ("facebook", 1, 1.0, 4),          # trang đăng ≤ 1 bài/ngày: ⌈1,5⌉ + 2 = 4
    ("facebook", 0, 1.0, 3),          # 14 ngày không đăng: sàn 3
    ("facebook", 4, 1.0, 8),          # ⌈6⌉ + 2
    ("facebook", 6, 1.0, 10),         # ⌈9⌉ + 2 = 11 ≥ 10: lấy đủ
    ("facebook", 1, 3.0, 7),          # Mark lỡ 2 ngày: ⌈4,5⌉ + 2
    ("tiktok", 2, 1.0, 10),           # 10 → 5 vẫn tải đủ 1 trang 10 bài: không co (tiền theo trang)
    ("instagram", 1, 1.0, 10),        # tính theo tài khoản: số bài không đổi tiền
    ("threads", 1, 1.0, 10),
])
def test_so_bai_co_gian(p, max_ngay, khoang, ra):
    m, ly = CP.so_bai_co_gian(p, 10, max_ngay, khoang, CFG)
    assert m == ra and (bool(ly) is (ra < 10))
    if ra < 10:
        assert ly.startswith(f"10→{ra} bài: đăng tối đa {max_ngay} bài/ngày (14 ngày)")


@pytest.mark.parametrize("so, max_ngay, ra", [
    (20, 2, 10),       # ⌈3⌉ + 2 = 5 → tròn lên 1 trang (10 bài): bớt 1 trang, giữ đủ bài của trang
    (25, 6, 20),       # ⌈9⌉ + 2 = 11 → 2 trang
    (15, 0, 10),       # sàn 3 → 1 trang
    (10, 0, 10),       # dưới một trang thì không co: 1 trang đằng nào cũng tải
    (8, 0, 8),
])
def test_tiktok_co_theo_trang(so, max_ngay, ra):
    """Soát 18/10/2026: TikTok API tính tiền theo TRANG ~10 bài — co dưới một trang mất bài mà không
    bớt yêu cầu nào. Làm tròn LÊN bội số cỡ trang; trang đã tải thì giữ hết bài
    (`tiktok_api._ho_so_mot` không cắt `bai[:n]`)."""
    m, ly = CP.so_bai_co_gian("tiktok", so, max_ngay, 1.0, CFG)
    assert m == ra and bool(ly) is (ra < so)
    assert m == so or m % CP.TT_BAI_MOI_TRANG == 0
    assert CP.don_vi_ky_vong("tiktok", m) <= CP.don_vi_ky_vong("tiktok", so)


def test_lay_du_khi_lam_moi_chien_dich_bao_hoa_chua_co_lich_su_hoac_tat():
    for kw, chu in (({"day_du": True}, "làm mới đủ 10 bài (mỗi 7 ngày)"),
                    ({"chien_dich": True}, "đang chiến dịch"),
                    ({"bao_hoa": True}, "lượt trước lấy đủ mà bài về đều mới")):
        m, ly = CP.so_bai_co_gian("facebook", 10, 1, 1.0, CFG, **kw)
        assert m == 10 and ly.startswith(chu)
    assert CP.so_bai_co_gian("facebook", 10, None, 1.0, CFG) == (10, "chưa có lịch sử đăng")
    tat = CP.cau_hinh_co_gian({"cau_hinh": {"theo_doi": {"co_gian": False}}})
    assert CP.so_bai_co_gian("facebook", 10, 1, 1.0, tat) == (10, "")
    rieng = CP.cau_hinh_co_gian({"cau_hinh": {"theo_doi": {"san": 6, "ngay_day_du": "x"}}})
    assert (rieng["san"], rieng["ngay_day_du"]) == (6, 7)
    assert CP.so_bai_co_gian("facebook", 10, 1, 1.0, rieng)[0] == 6


def test_gom_run_thedoor_re_nhat():
    """HAPAS (giả định nhịp 18/10): 6 trang co còn (10, 6, 6, 3, 3, 3) → 3 run = 0,1075 USD/lượt thay
    vì 1 run × 10 bài cho mọi trang = 0,16 USD; mỗi số bài một run cũng là 3 run."""
    g = CP.nhom_fb([(10, "a"), (6, "b"), (3, "d"), (6, "c"), (3, "e"), (3, "f")], 0.0025, 0.01)
    assert g == [(3, ["d", "e", "f"]), (6, ["b", "c"]), (10, ["a"])]
    phi = sum(0.01 + len(ds) * n * 0.0025 for n, ds in g)
    assert phi == pytest.approx(0.1075) and 0.01 + 6 * 10 * 0.0025 == pytest.approx(0.16)
    # Hai trang 5 và 4 bài: gộp một run 5 bài (0,035) rẻ hơn hai run (0,0425).
    assert CP.nhom_fb([(5, "x"), (4, "y")], 0.0025, 0.01) == [(5, ["y", "x"])]
    assert CP.nhom_fb([(30, "x"), (5, "y")], 0.0025, 0.01) == [(5, ["y"]), (30, ["x"])]
    assert CP.nhom_fb([], 0.0025, 0.01) == []


def test_ky_vong_thang_cua_nguon_da_co():
    """FB 10 bài/lần, nhịp ≤ 1 bài/ngày: 6 lượt × 4 bài + 1 lượt × 10 bài mỗi 7 ngày → 30 ngày
    ≈ 30 × 34/7 × 0,0025 = 0,364 USD (không co: 0,75)."""
    (n,) = CP.gan_co_gian([{"id": 1, "nen_tang": "facebook", "so_bai_moi_lan": 10,
                            "chu_ky_ngay": 1, "loai": "kenh_nha"}], {1: 1}, {})
    assert n["so_bai_co_gian"] == 4 and n["ly_do_co_gian"].startswith("10→4 bài")
    assert CP.chi_phi_thang_nguon(n) == pytest.approx(30 * 34 / 7 * 0.0025)
    (k,) = CP.gan_co_gian([{"id": 2, "nen_tang": "facebook", "so_bai_moi_lan": 10,
                            "chu_ky_ngay": 1, "loai": "kenh_nha"}], {}, {})
    assert k["so_bai_co_gian"] is None and CP.chi_phi_thang_nguon(k) == pytest.approx(0.75)
    # Soát 18/10/2026: nguồn KHÔNG phải kênh nhà (hoặc thiếu loại) lấy đủ dù nhịp thấp — kho chỉ
    # giữ bài nhắc từ khoá của nó, nhịp đếm trên kho thấp hơn nhịp đăng thật.
    for loai in ("kol", "page", None):
        (x,) = CP.gan_co_gian([{"id": 3, "nen_tang": "facebook", "so_bai_moi_lan": 10,
                                "chu_ky_ngay": 1, "loai": loai}], {3: 1}, {})
        assert x["so_bai_co_gian"] is None and CP.chi_phi_thang_nguon(x) == pytest.approx(0.75)


# ───────────────────────────── Mark ─────────────────────────────
def _ng(i, dd, p="facebook", so=10, qc=None):
    return {"id": i, "nen_tang": p, "dinh_danh": dd, "ten": dd, "link": "", "loai": "kenh_nha",
            "so_bai_moi_lan": so, "chu_ky_ngay": 1, "quet_cuoi": qc}


def test_mark_co_va_gom_run_trong_ke_hoach(monkeypatch):
    ds = [_ng(1, "https://www.facebook.com/hapasglobal"),
          _ng(2, "https://www.facebook.com/hapasonlineshop"),
          _ng(3, "https://www.facebook.com/hapasvietnamstore"),
          _ng(4, "hapas.official", p="tiktok", so=20), _ng(5, "hapas.vn", p="instagram", so=12)]
    monkeypatch.setattr(K, "nhip_dang_nguon", lambda ma, ngay=14: {1: 6, 2: 1, 3: 1, 4: 2, 5: 1})
    monkeypatch.setattr(K, "lich_chien_dich", lambda ma: [])
    # Đã lấy đủ hôm qua → hôm nay co.
    hom_qua = (BAY - datetime.timedelta(days=1)).isoformat()
    T.ghi_moc_tk("hapas", {T.KHOA_CO_GIAN: {str(i): {"day_du_luc": hom_qua} for i in range(1, 6)}})
    co = T._co_gian_nguon("hapas", {"ma": "hapas", "cau_hinh": {}}, ds, BAY)
    # TikTok 20 bài, nhịp 2/ngày: 5 → tròn lên 1 trang = 10 (tiền theo trang, 18/10/2026).
    assert [x["so_bai_hieu_luc"] for x in co] == [10, 4, 4, 10, 12]
    ph = T.chia_phan(co)
    fb = {x["id"]: x for x in ph["facebook"]}
    # thedoor: run 4 bài cho 2 trang nhỏ + run 10 bài cho hapasglobal (0,04 < 0,085 gộp một run).
    assert set(fb) == {"facebook-4", "facebook-10"} and fb["facebook-4"]["nguon"] == [2, 3]
    assert fb["facebook-4"]["payload"]["postsToScrape"] == 4
    assert fb["facebook-4"]["co_gian"] == {"2": [10, co[1]["ly_do_co_gian"]],
                                           "3": [10, co[2]["ly_do_co_gian"]]}
    assert ph["tiktok"][0]["n"] == 10
    # Quá 7 ngày từ lần lấy đủ: lấy đủ để làm mới số liệu bài cũ.
    tuan = (BAY - datetime.timedelta(days=7, hours=1)).isoformat()
    T.ghi_moc_tk("hapas", {T.KHOA_CO_GIAN: {"2": {"day_du_luc": tuan}}})
    co = T._co_gian_nguon("hapas", {"ma": "hapas", "cau_hinh": {}}, ds, BAY)
    assert co[1]["so_bai_hieu_luc"] == 10 and co[1]["ly_do_co_gian"].startswith("làm mới đủ")
    # Kho lỗi: giữ nguyên (lấy đủ như cũ).

    def hong(ma, ngay=14):
        raise K.LoiKho("kho")
    monkeypatch.setattr(K, "nhip_dang_nguon", hong)
    assert T._co_gian_nguon("hapas", {"ma": "hapas"}, ds, BAY) == ds


def test_mark_ghi_so_co_gian_va_pheu():
    from test_theo_doi import GiaViec
    qc = BAY - datetime.timedelta(days=1)
    nguon = {1: _ng(1, "https://www.facebook.com/hapasglobal", qc=qc),
             2: _ng(2, "https://www.facebook.com/hapasonlineshop", qc=qc),
             3: _ng(3, "https://www.facebook.com/hapasvietnamstore", qc=qc)}
    v = GiaViec({"facebook": {"phan": [
        {"id": "facebook-4", "nen_tang": "facebook", "nguon": [2, 3], "n": 4, "trang_thai": "xong",
         "co_gian": {"2": [10, "10→4 bài: …"], "3": [10, "10→4 bài: …"]}},
        {"id": "facebook-10", "nen_tang": "facebook", "nguon": [1], "n": 10, "trang_thai": "xong",
         "co_gian": {"1": [10, "làm mới đủ 10 bài (mỗi 7 ngày)"]}}]}}, [])
    moi = [({}, BAY - datetime.timedelta(hours=h)) for h in (1, 2, 3, 4)]    # 4 bài, đều mới
    cu = [({}, BAY - datetime.timedelta(days=d)) for d in (0.2, 2, 3, 4)]    # có bài cũ
    cau = T._ghi_co_gian("hapas", v, nguon, {2: moi, 3: cu, 1: cu * 2}, BAY)
    so = T.doc_moc_tk("hapas")[T.KHOA_CO_GIAN]
    assert so["2"]["bao_hoa"] is True and so["3"]["bao_hoa"] is False
    assert so["1"]["day_du_luc"] == BAY.isoformat(timespec="seconds")
    assert cau[0] == ("co số bài theo nhịp đăng: 2 nguồn bớt 12 bài (≈ 0,030 USD) — "
                      "hapasonlineshop 10→4, hapasvietnamstore 10→4")
    assert cau[1] == "làm mới đủ số bài cấu hình (số liệu bài cũ): hapasglobal"
    assert cau[2].startswith("nguồn bão hoà") and cau[2].endswith("hapasonlineshop")
    # Bão hoà → lượt sau lấy đủ.
    m, ly = CP.so_bai_co_gian("facebook", 10, 1, 1.0, CFG, bao_hoa=so["2"]["bao_hoa"])
    assert m == 10 and "lượt trước lấy đủ" in ly


def test_mark_chi_co_kenh_nha_va_nhip_theo_bai_tho(monkeypatch):
    """Soát 18/10/2026: (1) chỉ kênh nhà được co — KOL chỉ có bài nhắc từ khoá trong kho nên nhịp
    đếm trên kho thấp hơn nhịp đăng thật; (2) nhịp = số lớn hơn giữa kho và bài THÔ actor trả các
    lượt trước (sổ `ngay_dang`, chỉ ngày trong 14 ngày)."""
    kol = dict(_ng(2, "https://www.facebook.com/kol.a"), loai="kol")
    ds = [_ng(1, "https://www.facebook.com/hapasglobal"), kol,
          _ng(3, "https://www.facebook.com/hapasonlineshop")]
    monkeypatch.setattr(K, "nhip_dang_nguon", lambda ma, ngay=14: {1: 1, 2: 1, 3: 1})
    monkeypatch.setattr(K, "lich_chien_dich", lambda ma: [])
    hom_qua = (BAY - datetime.timedelta(days=1)).isoformat()
    ngay = (BAY - datetime.timedelta(days=2)).date().isoformat()
    T.ghi_moc_tk("hapas", {T.KHOA_CO_GIAN: {
        "1": {"day_du_luc": hom_qua}, "2": {"day_du_luc": hom_qua},
        # Kho giữ 1 bài/ngày nhưng actor trả 4 bài ngày đó (3 bài bị loại); ngày ngoài 14 ngày bỏ.
        "3": {"day_du_luc": hom_qua, "ngay_dang": {ngay: 4, "2026-09-01": 50}}}})
    co = T._co_gian_nguon("hapas", {"ma": "hapas", "cau_hinh": {}}, ds, BAY)
    # 1: ⌈1,5⌉ + 2 = 4; KOL: lấy đủ; 3: ⌈4 × 1,5⌉ + 2 = 8.
    assert [x["so_bai_hieu_luc"] for x in co] == [4, 10, 8]
    assert co[1]["ly_do_co_gian"] == ""
    assert T._nhip_tho({"ngay_dang": {ngay: 4, "2026-09-01": 50, "rác": "x"}}, BAY) == 4
    assert T._nhip_tho({}, BAY) is None


def test_bao_hoa_bo_qua_bai_ghim_va_ghi_nhip_bai_tho():
    """Soát 18/10/2026: bão hoà = bài THÔ mới hơn lần quét trước ≥ số đã co − 1. Bản cũ xét
    `min(ngày) > quet_cuoi`: MỘT bài ghim cũ là đủ để nguồn không bao giờ bão hoà, bị co mãi."""
    from test_theo_doi import GiaViec
    qc = BAY - datetime.timedelta(days=1)
    nguon = {2: _ng(2, "https://www.facebook.com/hapasonlineshop", qc=qc)}

    def chay(dong):
        v = GiaViec({"facebook": {"phan": [
            {"id": "facebook-4", "nen_tang": "facebook", "nguon": [2], "n": 4,
             "trang_thai": "xong", "co_gian": {"2": [10, "10→4 bài: …"]}}]}}, [])
        T._ghi_co_gian("hapas", v, nguon, {2: dong}, BAY)
        return T.doc_moc_tk("hapas")[T.KHOA_CO_GIAN]["2"]
    ghim = ({}, BAY - datetime.timedelta(days=200))
    moi = [({}, BAY - datetime.timedelta(hours=h)) for h in (1, 2, 3)]
    st = chay([ghim, *moi])
    assert st["bao_hoa"] is True and st["moi"] == 3, "bài ghim cũ không chặn bão hoà"
    assert st["ngay_dang"] == {BAY.date().isoformat(): 3}, "bài ghim ngoài 14 ngày: không vào nhịp"
    # Chỉ 2/4 bài mới: chưa bão hoà; số theo ngày giữ mức lớn nhất (không cộng dồn qua lượt).
    cu = [({}, BAY - datetime.timedelta(days=d)) for d in (2, 3)]
    st = chay([*moi[:2], *cu])
    assert st["bao_hoa"] is False and st["moi"] == 2
    assert st["ngay_dang"][BAY.date().isoformat()] == 3
    assert st["ngay_dang"][(BAY - datetime.timedelta(days=2)).date().isoformat()] == 1


# ───────────────────────────── trang Nguồn ─────────────────────────────
def test_trang_nguon_bao_so_bai_co(monkeypatch):
    from test_dashboard_app import QL, GiaKho, dang_nhap, tao
    kho = GiaKho()
    kho.nguon[1] = {"id": 1, "du_an": "hapas", "nen_tang": "facebook",
                    "dinh_danh": "https://www.facebook.com/hapasonlineshop", "ten": "Online",
                    "link": "", "loai": "kenh_nha", "nhan": [], "trang_thai": "dang_theo_doi",
                    "chu_ky_ngay": 1, "so_bai_moi_lan": 10, "them_qua": "dashboard",
                    "them_boi": None, "them_luc": None, "quet_cuoi": None, "loi_cuoi": None,
                    "loi_luc": None}
    kho.nhip_dang = lambda du_an, ngay=14: {1: 1}
    _, c, _ = tao(kho)
    dang_nhap(c, QL)
    t = c.get("/nguon?du_an=hapas").text
    assert 'data-o="co-gian"' in t and "co ~4/lần" in t
    assert "≈ 0,364 USD/tháng theo bài" in t                    # 30 × 34/7 × 0,0025
    assert 'data-nhip="1" data-ngay-day-du="7" data-san="3"' in t
