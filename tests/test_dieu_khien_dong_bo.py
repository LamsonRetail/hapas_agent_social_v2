"""Điều khiển đồng bộ quảng cáo trên trang Quảng cáo (thiết kế lại 20/10/2026, chủ dự án: "rối, không biết
đang đồng bộ TikTok hay Facebook"): mỗi nền tảng một dòng (tên đầy đủ, một câu trạng thái), nút tách "Đồng bộ
ngay" (nhanh) + "Đồng bộ lại 90 ngày" (day_du + nạp lại, chỉ quản trị viên, hỏi xác nhận), chi tiết gập, lý do
khi nút khoá; POST /quang-cao/dong-bo nhận `ncc` + `kieu`, kiểm quyền / khung giờ / chống bấm dồn ở máy chủ.

Không mạng: dịch vụ TikTok / Meta giả của `test_meta_ads_dashboard._app_hai_nen_tang`."""
from __future__ import annotations

import datetime

from test_dashboard_app import QL, XEM, dang_nhap
from test_meta_ads_dashboard import _app_hai_nen_tang
from test_tiktok_ads import BAY

from dashboard import quang_cao as QC

UTC = datetime.timezone.utc
Q = "/quang-cao?tu=2026-10-12&den=2026-10-18"


def _h():
    h = _app_hai_nen_tang()
    for k in ("tiktok_ads", "meta_ads"):
        h.kho_qc.kns[k]["yeu_cau_dong_bo_luc"] = None
    return h


def _dai(t: str) -> str:
    return t.split('data-o="dai-qc"')[1].split("</section>")[0]


def _dong(dai: str, nen: str) -> str:
    return dai.split(f'data-nen-tang="{nen}"')[1].split("</li>")[0]


def _tb(c, r) -> str:
    return c.get(r.headers["location"]).text


def test_moi_nen_tang_mot_dong_ten_ro_nut_tach_chi_tiet_gap():
    h = _h()
    dang_nhap(h.c, QL)
    dai = _dai(h.c.get(Q).text)
    assert "Đồng bộ số quảng cáo" in dai and "Đồng bộ cả hai" in dai
    for nen, ten, ncc in (("tiktok", "TikTok Ads", "tiktok_ads"),
                          ("meta", "Meta (Facebook) Ads", "meta_ads")):
        d = _dong(dai, nen)
        assert ten in d and f"qc-cham--{nen}" in d
        assert "Số đến 18/10 · cập nhật" in d                          # một câu trạng thái
        assert f'name="ncc" value="{ncc}"' in d and 'name="kieu" value="nhanh"' in d
        assert 'name="kieu" value="day_du"' in d and "Đồng bộ lại 90 ngày" in d
        assert "data-xac-nhan=" in d and "Chạy nền" in d                  # hỏi xác nhận
        assert "<summary>chi tiết</summary>" in d and "Tài khoản thấy" in d
        assert "disabled" not in d.split("dai-qc__them")[0]              # "Đồng bộ ngay" bấm được
    assert "Chi tiêu" not in dai and "₫" not in dai                      # không tiền


def test_dong_bo_ngay_mot_nen_tang_chi_ghi_co_nhanh():
    h = _h()
    csrf = dang_nhap(h.c, QL)
    n_meta, n_tt = len(h.gm.goi), len(h.tt.goi)
    r = h.c.post("/quang-cao/dong-bo", data={"csrf": csrf, "ncc": "meta_ads", "kieu": "nhanh",
                                             "ve": "/quang-cao"})
    assert r.status_code == 303 and r.headers["location"] == "/quang-cao"
    t = _tb(h.c, r)
    assert "Đã yêu cầu đồng bộ Meta (Facebook) Ads (hôm nay + 2 ngày trước)" in t
    assert h.kho_qc.kns["meta_ads"]["yeu_cau_kieu"] == "nhanh"
    assert not h.kho_qc.kns["tiktok_ads"].get("yeu_cau_dong_bo_luc")    # chỉ đúng nền tảng
    assert len(h.gm.goi) == n_meta and len(h.tt.goi) == n_tt            # không gọi nền tảng
    # Đang có yêu cầu: nút khoá, nói vì sao; máy chủ cũng từ chối.
    d = _dong(_dai(t), "meta")
    assert "Đã yêu cầu lúc" in d and "Chưa bấm được: đang có yêu cầu lúc" in d
    assert "disabled" in d.split("dai-qc__them")[0]
    r = h.c.post("/quang-cao/dong-bo", data={"csrf": csrf, "ncc": "meta_ads", "kieu": "nhanh"})
    assert "Chưa tạo yêu cầu mới" in _tb(h.c, r)


def test_dong_bo_lai_90_ngay_chi_quan_tri_va_nap_lai():
    h = _h()
    for t in h.kho_qc.tk.values():
        t["nap_lui_xong_luc"] = BAY
    csrf = dang_nhap(h.c, XEM)
    r = h.c.post("/quang-cao/dong-bo", data={"csrf": csrf, "ncc": "tiktok_ads", "kieu": "day_du"})
    assert r.status_code == 403 and not h.kho_qc.kns["tiktok_ads"].get("yeu_cau_dong_bo_luc")
    csrf = dang_nhap(h.c, QL)
    assert h.c.post("/quang-cao/dong-bo", data={"csrf": "sai", "ncc": "tiktok_ads",
                                                "kieu": "day_du"}).status_code == 403
    r = h.c.post("/quang-cao/dong-bo", data={"csrf": csrf, "ncc": "tiktok_ads", "kieu": "day_du"})
    assert "nạp lại 90 ngày, chạy nền" in _tb(h.c, r)
    assert h.kho_qc.kns["tiktok_ads"]["yeu_cau_kieu"] == "day_du"
    tk = {a: t for a, t in h.kho_qc.tk.items() if (t.get("nen_tang") or "tiktok") == "tiktok"}
    assert all(t["nap_lui_xong_luc"] is None for t in tk.values() if t.get("dang_dong_bo"))
    assert all(t["nap_lui_xong_luc"] == BAY for a, t in h.kho_qc.tk.items() if a.startswith("act_"))
    assert (QL, "dong_bo_qc") in h.kho_qc.nk
    assert not h.kho_qc.kns["meta_ads"].get("yeu_cau_dong_bo_luc")
    # Lượt nhanh vừa xong < 15 phút không chặn đồng bộ lại 90 ngày (chỉ chặn nhanh).
    th = {"co_token": True, "nhanh_xong_luc": datetime.datetime.now(UTC), "dong_bo_kieu": "nhanh"}
    bay = datetime.datetime.now(UTC)
    assert "bấm lại được từ" in QC.ly_do_khong_dong_bo(th, bay, "nhanh", bay_dv=BAY)
    assert QC.ly_do_khong_dong_bo(th, bay, "day_du", bay_dv=BAY) is None
    assert "khoá mã hoá" in QC.ly_do_khong_dong_bo({"co_token": True, "loi_khoa": "thiếu"}, bay,
                                                     "day_du", bay_dv=BAY)


def test_trong_gio_dong_bo_tu_dong_khoa_nut_va_may_chu_tu_choi():
    h = _h()
    gio = datetime.datetime(2026, 10, 19, 23, 40, tzinfo=UTC)          # 06:40 giờ VN
    h.tdv._bay_gio = h.dv._bay_gio = lambda: gio
    csrf = dang_nhap(h.c, QL)
    dai = _dai(h.c.get(Q).text)
    assert "Đồng bộ cả hai" not in dai
    for nen in ("tiktok", "meta"):
        d = _dong(dai, nen)
        assert "Chưa bấm được: trong giờ đồng bộ tự động (06:25–07:30)" in d
        assert "disabled" in d.split("dai-qc__them")[0]
    r = h.c.post("/quang-cao/dong-bo", data={"csrf": csrf, "ncc": "ca_hai", "kieu": "day_du"})
    assert "trong giờ đồng bộ tự động" in _tb(h.c, r)
    assert not h.kho_qc.kns["tiktok_ads"].get("yeu_cau_dong_bo_luc")


def test_ncc_kieu_sai_va_chua_ket_noi():
    h = _h()
    csrf = dang_nhap(h.c, QL)
    for f in ({"ncc": "youtube"}, {"ncc": "tiktok_ads", "kieu": "tat_ca"}):
        r = h.c.post("/quang-cao/dong-bo", data={"csrf": csrf, **f})
        assert "không hợp lệ" in _tb(h.c, r)
    x = QC.dong_dieu_khien({}, "meta", datetime.datetime.now(UTC), bay_dv=BAY)
    assert x["cau"].startswith("Chưa kết nối") and x["ly_nhanh"] == "chưa kết nối"
    assert x["ten"] == "Meta (Facebook) Ads" and x["ncc"] == "meta_ads"
    x = QC.dong_dieu_khien({"co_token": True, "dong_bo_loi": "x"}, "tiktok",
                           datetime.datetime.now(UTC), la_quan_tri=True, bay_dv=BAY)
    assert x["cau"] == "Lỗi lần trước — xem chi tiết" and x["chi_tiet"]["loi"] == "x"
    x = QC.dong_dieu_khien({"co_token": True, "dang_dong_bo": True}, "tiktok",
                           datetime.datetime.now(UTC), bay_dv=BAY)
    assert x["cau"].startswith("Đang đồng bộ…") and x["ly_nhanh"].startswith("đang chạy")


# ───────────────────────────── soát 20/10/2026 (M1–M3, L1–L3) ─────────────────────────────
def _ve(app, dai, la_quan_tri):
    return app.state.mau.env.get_template("_dai_qc.html").render(
        dai_qc=dai, nguoi={"la_quan_tri": la_quan_tri, "csrf": "x"}, duong_ve="/quang-cao")


def test_nguoi_khong_phai_quan_tri_khong_thay_90_ngay_va_loi_tho():
    """Trang Quảng cáo chỉ quản trị viên mở được (`QC.thay_trang_qc` = la_quan_tri) — đây là lớp chặn
    thứ hai: dựng dải với người thường thì không có menu 90 ngày, không số tài khoản, không chữ lỗi."""
    h = _h()
    assert QC.thay_trang_qc({"la_quan_tri": False, "ben": {"hapas": "quan_ly"}}, {"hapas"}) is False
    the = {"co_token": True, "dong_bo_loi": "token=abc lỗi 500", "so_tk_thay": 7}
    x = QC.dong_dieu_khien(the, "tiktok", BAY, la_quan_tri=False, bay_dv=BAY)
    assert x["ly_day_du"] == "chỉ quản trị viên" and x["chi_tiet"]["so_tk"] is None
    assert x["cau"] == "Lỗi lần trước — báo quản trị viên" and "abc" not in str(x)
    t = _ve(h.app, [x], False)
    assert "Đồng bộ lại 90 ngày" not in t and 'value="day_du"' not in t and "Tài khoản thấy" not in t
    assert "Đồng bộ ngay" in t and "token" not in t
    y = QC.dong_dieu_khien(the, "tiktok", BAY, la_quan_tri=True, bay_dv=BAY)
    t = _ve(h.app, [y], True)
    assert 'value="day_du"' in t and "Tài khoản thấy" in t and "token=abc" in t
    assert "Meta tới ~6 giờ" in t and "số tức thì của Mark" in t                # M3


def test_90_ngay_khong_nhan_tu_0h_toi_7h30_nhanh_van_duoc():
    sang = datetime.datetime(2026, 10, 19, 22, 0, tzinfo=UTC)          # 05:00 giờ VN
    the = {"co_token": True}
    assert QC.ly_do_khong_dong_bo(the, sang, "day_du", bay_dv=sang) == QC.CAU_SANG
    assert QC.ly_do_khong_dong_bo(the, sang, "nhanh", bay_dv=sang) is None
    h = _h()
    h.tdv._bay_gio = h.dv._bay_gio = lambda: sang
    csrf = dang_nhap(h.c, QL)
    r = h.c.post("/quang-cao/dong-bo", data={"csrf": csrf, "ncc": "meta_ads", "kieu": "day_du"})
    assert "để không chồng lượt tự động sáng" in _tb(h.c, r)
    assert not h.kho_qc.kns["meta_ads"].get("yeu_cau_dong_bo_luc")


def test_khoa_ma_hoa_hong_chan_ca_dong_bo_ngay():
    assert "khoá mã hoá" in QC.ly_do_khong_dong_bo({"co_token": True, "loi_khoa": "thiếu"}, BAY,
                                                     "nhanh", bay_dv=BAY)


def test_90_ngay_mot_giao_dich_mot_dong_nhat_ky():
    """L1/L2: nap_lai xoá mốc + ghi cờ day_du cùng giao dịch; một dòng nhật ký mỗi lần bấm."""
    import inspect

    from dashboard import kho_qc as KQ
    src = inspect.getsource(KQ.nap_lai)
    assert "_yeu_cau(c, ai, ncc, \"day_du\")" in src and src.count("_nhat_ky(") == 1
    h = _h()
    csrf = dang_nhap(h.c, QL)
    n0 = len(h.kho_qc.nk) + len(h.kho.nk)
    h.c.post("/quang-cao/dong-bo", data={"csrf": csrf, "ncc": "tiktok_ads", "kieu": "day_du"})
    assert len(h.kho_qc.nk) + len(h.kho.nk) == n0 + 1
    assert h.kho_qc.kns["tiktok_ads"]["yeu_cau_kieu"] == "day_du"
