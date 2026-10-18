"""Giãn nhịp đường tìm ít bài mới (18/10/2026, chủ dự án: "các luồng cào để tối ưu output nhất có
thể").

Instagram hashtag gói FREE chỉ đọc trang đầu (~6 bài mới nhất mỗi hashtag mỗi tab): phễu thật lượt
7–11 (16–17/10) về 14/14/7/0/0 bài, mới 2/0/0/0/0. Threads đường 1 mất 0,08 USD khởi động kể cả về 0
bài. 3 lượt liền bài mới < 5% bài về (hoặc về 0) thì nền tảng chỉ tìm lại sau 44 giờ (≈ 2 ngày/lần
với lịch 07:00 hằng ngày); chiến dịch đang chạy thì không giãn."""
from __future__ import annotations

import datetime

import pytest
from test_theo_doi import DU_AN, GiaKhoTk, GiaViec, _chay_tk, mo  # noqa: F401

import apify_tool as A
import theo_doi as T
from dashboard import chi_phi as CP

VN = datetime.timezone(datetime.timedelta(hours=7))
CFG = T._cau_hinh_gian({})
#: Phễu tìm Instagram THẬT (luot_quet.ghi_chu lượt 7–11): (bắt đầu, về, mới).
IG_THAT = [["2026-10-16T21:51:13+07:00", 14, 2], ["2026-10-16T22:53:12+07:00", 14, 0],
           ["2026-10-17T00:51:03+07:00", 7, 0], ["2026-10-17T11:37:15+07:00", 0, 0],
           ["2026-10-17T12:46:18+07:00", 0, 0]]


def test_gian_nhip_theo_phieu_instagram_that():
    nhip = {"lich_su": IG_THAT}
    # 18/10 07:00 (lịch hằng ngày): 3 lượt cuối 0/7, 0/0, 0/0 → bỏ, tìm lại từ 08:46 19/10.
    bo, ly = T.gian_nhip(CFG, nhip, datetime.datetime(2026, 10, 18, 7, 0, tzinfo=VN))
    assert bo and ly == ("giãn nhịp: 3 lượt liền bài mới dưới 5% bài về (mới/về: 0/7, 0/0, 0/0)"
                         " — tìm lại từ 08:46 19/10")
    # 19/10 07:00: còn 1 giờ 46 phút (< 3 giờ dung sai của lịch) → chạy lại.
    assert T.gian_nhip(CFG, nhip, datetime.datetime(2026, 10, 19, 7, 0, tzinfo=VN)) == (False, "")
    # Lượt 7–9 (2/14 = 14% ≥ 5%): chưa giãn.
    assert not T.gian_nhip(CFG, {"lich_su": IG_THAT[:3]},
                           datetime.datetime(2026, 10, 17, 1, 0, tzinfo=VN))[0]
    # Chiến dịch đang chạy / tắt / chưa đủ 3 lượt: không giãn.
    bay = datetime.datetime(2026, 10, 18, 7, 0, tzinfo=VN)
    assert not T.gian_nhip(CFG, nhip, bay, chien_dich=True)[0]
    assert not T.gian_nhip(T._cau_hinh_gian({"gian": {"bat": False}}), nhip, bay)[0]
    assert not T.gian_nhip(CFG, {"lich_su": IG_THAT[-2:]}, bay)[0]
    assert not T.gian_nhip(CFG, None, bay)[0]


def test_cau_hinh_gian_rac_va_khop_dashboard():
    assert CFG == {"bat": True, "luot": 3, "ty_le": 0.05, "gio": 44}
    rac = {"gian": {"bat": "false", "luot": 99, "ty_le": "x", "gio": -1}}
    assert T._cau_hinh_gian(rac) == {"bat": True, "luot": 6, "ty_le": 0.05, "gio": 44}
    assert T._cau_hinh_gian({"gian": {"ty_le": 1.5}})["ty_le"] == 0.05
    da = {"tk_bat": True, "tk_so_bai": 15,
          "cau_hinh": {"tu_khoa": {"instagram": {"gian": {"luot": 2, "ty_le": 0.1, "gio": 30}},
                                   "threads": {"bat": True, "gian": rac["gian"]}}}}
    for p in CP.NEN_TANG:
        assert CP.cau_hinh(da, "tu_khoa", p) == T.cau_hinh(da, "tu_khoa", p), p
    assert T.cau_hinh(da, "tu_khoa", "instagram")["gian"] == {"bat": True, "luot": 2,
                                                               "ty_le": 0.1, "gio": 30}
    assert "gian" not in T.cau_hinh(da, "tu_khoa", "tiktok")
    assert CP.TK_GIAN_NEN_TANG == T.TK_GIAN_NEN_TANG and CP.TK_GIAN_GIO == T.TK_GIAN_GIO


def test_luot_tim_bo_instagram_ghi_ly_do_va_lich_su(mo):  # noqa: F811
    GiaKhoTk(mo)
    goi: list = []

    def tim(p):
        def f(q, limit, country, d_from, d_to, **k):
            goi.append(p)
            return []
        return f
    mo.setattr(A, "_FETCH", {p: tim(p) for p in ("tiktok", "facebook", "instagram", "youtube")})
    da = dict(DU_AN, tu_khoa=["hapas"], tk_bat=True, tk_so_bai=15)
    gan = datetime.datetime.now(VN) - datetime.timedelta(hours=2)
    T.ghi_moc_tk("hapas", {T.KHOA_NHIP_TIM: {"instagram": {"lich_su": [
        [(gan - datetime.timedelta(days=d)).isoformat(timespec="seconds"), 7, 0]
        for d in (2, 1, 0)]}}})
    v = GiaViec({}, [])
    tk = _chay_tk(da, v)
    assert "instagram" not in goi and "facebook" in goi, "chỉ Instagram giãn nhịp"
    assert tk["pheu"]["instagram"]["bo_qua"].startswith("giãn nhịp: 3 lượt liền bài mới dưới 5%")
    assert any(c.startswith("tìm Instagram: bỏ qua (giãn nhịp") for c in tk["ghi_chu"])
    moc = {x["nen_tang"]: x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x.get("loai") == "moc"}
    assert moc["instagram"]["ma"] == "GIAN_NHIP"
    # Lịch sử Instagram không thêm dòng (lượt bị bỏ); Facebook thêm (về 0, mới 0).
    nhip = T.doc_moc_tk("hapas")[T.KHOA_NHIP_TIM]
    assert len(nhip["instagram"]["lich_su"]) == 3 and nhip["facebook"]["lich_su"][-1][1:] == [0, 0]
    # Đang chiến dịch: tìm Instagram dù nhịp thấp.
    from dashboard import lich_quet as LQ
    mo.setattr(LQ, "chien_dich_dang_chay", lambda ds, bay: {"id": 1})
    goi.clear()
    _chay_tk(da, GiaViec({}, []))
    assert "instagram" in goi


def _lich_su_gan(p: str, ve: int = 7, lui_gio: float = 2) -> list:
    """3 lượt liền về `ve` mới 0, lượt cuối cách đây `lui_gio` giờ → lượt này bị giãn."""
    gan = datetime.datetime.now(VN) - datetime.timedelta(hours=lui_gio)
    T.ghi_moc_tk("hapas", {T.KHOA_NHIP_TIM: {p: {"lich_su": [
        [(gan - datetime.timedelta(days=d)).isoformat(timespec="seconds"), ve, 0]
        for d in (2, 1, 0)]}}})
    return T.doc_moc_tk("hapas")[T.KHOA_NHIP_TIM][p]["lich_su"]


def test_fb_duong_1_gian_duong_2_chay_khong_doi_lich_su_roi_chay_lai(mo):  # noqa: F811
    """Soát 18/10/2026 (HIGH): đường 1 Facebook bị giãn mà đường 2 (mina) vẫn chạy → `_duong_fb`
    dựng lại phễu Facebook không còn `bo_qua` → bản cũ ghi thêm một dòng mang giờ CỦA CHÍNH LƯỢT
    BỊ BỎ với số của đường 2 → mốc "lượt tìm cuối" dời theo mãi, đường 1 không bao giờ chạy lại."""
    from test_duong_moi import _chay_tk_fb, _mina
    da = dict(DU_AN, tu_khoa=["hapas", "túi hapas"], tk_bat=True, tk_so_bai=15)
    cu = _lich_su_gan("facebook")
    tk, _, goi, _ = _chay_tk_fb(mo, [], _mina(), du_an=da)
    assert goi["facebook"] == [] and goi[T.TK_FB2], "đường 1 bị giãn, đường 2 vẫn chạy"
    assert tk["pheu"]["facebook"]["duong"]["scrapeforge"]["bo_qua"].startswith("giãn nhịp")
    ls = T.doc_moc_tk("hapas")[T.KHOA_NHIP_TIM]["facebook"]["lich_su"]
    assert ls == cu, "lượt đường 1 bị bỏ: không thêm dòng lịch sử"
    bay = datetime.datetime.fromisoformat(cu[-1][0]) + datetime.timedelta(hours=T.TK_GIAN_GIO)
    assert T.gian_nhip(CFG, {"lich_su": ls}, bay) == (False, ""), "đủ cửa sổ thì chạy lại"
    # Giả lập đã qua cửa sổ 44 giờ: lượt sau đường 1 chạy, lịch sử thêm đúng một dòng của nó.
    _lich_su_gan("facebook", lui_gio=T.TK_GIAN_GIO + 1)
    _, _, goi, _ = _chay_tk_fb(mo, [], _mina(), du_an=da)
    assert goi["facebook"], "đủ cửa sổ: đường 1 chạy lại"
    assert len(T.doc_moc_tk("hapas")[T.KHOA_NHIP_TIM]["facebook"]["lich_su"]) == 4


def test_lich_su_nhip_chi_dem_ve_moi_cua_duong_1(mo):  # noqa: F811
    """Facebook: đường 2 về nhiều bài mới mà đường 1 về 1 bài → lịch sử ghi (1, 1), không phải
    tổng hai đường (phễu Facebook gộp cả mina)."""
    from test_duong_moi import _chay_tk_fb, _mina, _sf_tim
    tk, _, _, _ = _chay_tk_fb(mo, [_sf_tim("shop.a", "1001", "túi hapas mới về")], _mina())
    assert tk["pheu"]["facebook"]["ve"] == 1 + len(_mina()) and tk["pheu"]["facebook"]["moi"] > 1
    assert T.doc_moc_tk("hapas")[T.KHOA_NHIP_TIM]["facebook"]["lich_su"][-1][1:] == [1, 1]
    assert "_nhip" not in tk, "sổ nhịp nội bộ không lọt ra kết quả lượt"


def test_moi_cua_gian_nhip_la_bai_chua_thay_ke_ca_bi_loai(mo):  # noqa: F811
    """Soát 18/10/2026: "mới" của giãn nhịp = bài CHƯA THẤY (chưa có trong kho, chưa trong sổ đã
    loại), kể cả bài lượt này bị loại — không phải bài mới được GIỮ. Trang đầu toàn bài mới mà lạc
    đề (bị loại) vẫn là "còn bài mới"; lượt sau chúng nằm trong sổ đã loại thì không còn mới."""
    from test_duong_moi import _chay_tk_fb, _sf_tim
    from test_theo_doi import GiaKhoTk
    kho_co: set = {"facebook:1003"}
    goc = GiaKhoTk.__init__

    def init(self, mp, co_bai=False):
        goc(self, mp, co_bai)
        self.da_co = kho_co                       # khoá bài đã có trong kho
    mo.setattr(GiaKhoTk, "__init__", init)
    sf = [_sf_tim("shop.a", "1001", "túi hapas mới về"),
          _sf_tim("shop.b", "1002", "hapas guitar điện"),           # từ loại trừ "guitar": loại
          _sf_tim("shop.c", "1003", "túi hapas đã có trong kho")]
    tk, _, _, _ = _chay_tk_fb(mo, sf, [])
    f = tk["pheu"]["facebook"]
    assert (f["loai_tru"], f["cap_nhat"], f["moi"]) == (1, 1, 1)
    ls = T.doc_moc_tk("hapas")[T.KHOA_NHIP_TIM]["facebook"]["lich_su"]
    assert ls[-1][1:] == [3, 2], "2 bài chưa thấy (gồm bài bị loại), bài đã có trong kho không tính"
    # Lượt sau: 1001 đã vào kho, 1002 nằm trong sổ đã loại — không còn bài nào mới.
    kho_co.add("facebook:1001")
    _chay_tk_fb(mo, sf, [])
    assert T.doc_moc_tk("hapas")[T.KHOA_NHIP_TIM]["facebook"]["lich_su"][-1][1:] == [3, 0]


def test_threads_lich_su_khong_dem_bai_duong_2(mo):  # noqa: F811
    """Threads: đường 1 về 2 bài, đường 2 thêm 4 bài riêng — phễu Threads giữ 6 mới, lịch sử nhịp
    đường 1 chỉ (2, 2). Đường 1 bị giãn thì không thêm dòng (đường 2 vẫn chạy, vẫn giữ bài)."""
    from test_threads_duong_2 import _d1, _d2, _da, _fetch
    GiaKhoTk(mo)
    goi: list = []
    mo.setattr(A, "_FETCH", _fetch(goi, {"threads": _d1(), T.TH2_KHOA: _d2()}))
    tk = _chay_tk(_da())
    assert tk["pheu"]["threads"]["moi"] == 6
    assert T.doc_moc_tk("hapas")[T.KHOA_NHIP_TIM]["threads"]["lich_su"][-1][1:] == [2, 2]
    cu = _lich_su_gan("threads")
    goi.clear()
    tk = _chay_tk(_da())
    assert [g[0] for g in goi] == [T.TH2_KHOA] and tk["pheu"]["threads"]["bo_qua"]
    assert T.doc_moc_tk("hapas")[T.KHOA_NHIP_TIM]["threads"]["lich_su"] == cu


@pytest.mark.parametrize("lich_su, ra", [
    ([[None, 0, 0]] * 3, False),             # mốc giờ hỏng: không giãn
    ([["2026-10-17T00:00:00+07:00", 0, 0]] * 3, True),
])
def test_gian_nhip_moc_hong(lich_su, ra):
    bay = datetime.datetime(2026, 10, 17, 12, 0, tzinfo=VN)
    assert T.gian_nhip(CFG, {"lich_su": lich_su}, bay)[0] is ra
