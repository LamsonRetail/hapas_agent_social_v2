"""Dashboard lắng nghe — dự báo chi phí theo dõi (`dashboard/chi_phi.py`, chủ dự án 15/10/2026:
"dashboard phải quản trị được chi phí").

Hằng số và công thức một lượt được CHÉP từ Mark (dashboard không import module của Mark): bài
đối chiếu ở đây import `theo_doi` / `apify_tool` để lệch là đỏ ngay. Số dự báo tính tay."""
from __future__ import annotations

import datetime

import pytest

import apify_tool as A
import theo_doi as T
from dashboard import chi_phi as CP

VN = datetime.timezone(datetime.timedelta(hours=7))
UTC = datetime.timezone.utc
XAP_XI = {"abs": 1e-6}


def test_hang_so_khop_mark():
    import tiktok_api as TT
    assert CP.GIA == T._GIA
    assert CP.HE_SO_UOC == T._HE_SO_UOC
    assert CP.START_COST == A._START_COST
    assert CP.KHOI_NGUON == T._KHOI_NGUON
    # TikTok API theo YÊU CẦU (18/10/2026): giá, số yêu cầu một nguồn, giá bình luận.
    assert CP.TK_TT_YEU_CAU == T.TK_TT_YEU_CAU == TT.GIA_YEU_CAU == CP.GIA["tiktok"]
    assert CP.TT_BAI_MOI_TRANG == TT.BAI_MOI_TRANG and CP.BL_GIA == T._BL_GIA
    for n in (1, 5, 9, 10, 11, 20, 30, 101):
        assert CP.so_yeu_cau_ho_so(n) == TT.so_yeu_cau_ho_so(n)
        for p in ("tiktok", "facebook", "instagram", "threads"):
            assert CP.don_vi_nguon(p, n) == T.don_vi_nguon(p, n)


@pytest.mark.parametrize("p", ["tiktok", "instagram", "facebook", "youtube"])
@pytest.mark.parametrize("so_nguon", [0, 1, 3])
@pytest.mark.parametrize("so_bai", [1, 5, 30])
def test_mot_luot_khop_uoc_phan_cua_mark(p, so_nguon, so_bai):
    assert CP.uoc_mot_luot(p, so_nguon, so_bai) == T._uoc_phan(p, so_nguon, so_bai)


@pytest.mark.parametrize("p, so_bai, bu", [("tiktok", 10, 1), ("instagram", 7, 0),
                                           ("facebook", 4, 0)])
def test_ky_vong_nhan_he_so_bang_toi_da_cua_mark(p, so_bai, bu):
    """(Phần theo đơn vị + phí khởi động một ngày) KỲ VỌNG × 1,3 = mức TỐI ĐA một lượt actor của
    Mark (`_uoc_phan`); TikTok tối đa thêm `bu` trang bù bài ghim."""
    n = {"nen_tang": p, "so_bai_moi_lan": so_bai, "chu_ky_ngay": 1}
    assert (CP.chi_phi_luot_nguon(n) + bu * CP.GIA[p] + CP.phi_khoi_dong_ngay(p)) \
        * CP.HE_SO_UOC == pytest.approx(T._uoc_phan(p, 1, so_bai), abs=1e-4)


def test_ky_vong_neo_theo_so_do_that():
    """Neo theo run Apify THẬT (đo 16–17/10/2026, đọc lại 18/10/2026) — trang Nguồn / dự báo báo
    đúng tiền một lượt, không lố 30% (hệ số) hay 5 lần (TikTok theo bài):
      • thedoor `hapasglobal` 20 bài: 0,0600 USD (1 sự kiện khởi động 0,01 + 20 × 0,0025);
      • hồ sơ Threads scrapersdelight: 0,0020; hồ sơ Instagram apify: 0,0026 (`pricingInfos`);
      • scraptik @hapas.official 20 bài: 3 yêu cầu = 0,006 USD."""
    def mot(p, so_bai):
        return CP.chi_phi_luot_nguon({"nen_tang": p, "so_bai_moi_lan": so_bai, "chu_ky_ngay": 1})
    assert mot("facebook", 20) + CP.phi_khoi_dong_ngay("facebook") == pytest.approx(0.0600)
    assert mot("threads", 10) == pytest.approx(0.0020)
    assert mot("instagram", 12) == pytest.approx(0.0026)
    assert mot("tiktok", 20) == pytest.approx(0.0060)
    # Ảnh trang Nguồn chủ dự án gửi 18/10 (cấu hình thật HAPAS): FB 10 bài 0,975, TikTok 20 bài
    # 0,936, Threads 0,078 USD/tháng → nay 0,75 (+ phí khởi động chung), 0,18, 0,06.
    thang = {p: CP.chi_phi_thang_nguon({"nen_tang": p, "so_bai_moi_lan": b, "chu_ky_ngay": 1})
             for p, b in (("facebook", 10), ("tiktok", 20), ("threads", 10))}
    assert thang == pytest.approx({"facebook": 0.75, "tiktok": 0.18, "threads": 0.06})


def test_nguon_js_khop_python(tmp_path):
    """`dashboard/static/nguon.js` (ô "≈ USD/tháng" khi sửa nguồn) ra đúng số của
    `chi_phi.chi_phi_thang_nguon` + `phi_khoi_dong_ngay` — chạy file thật bằng node, DOM giả."""
    import json
    import re
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("máy không có node")
    js = (Path(__file__).resolve().parents[1] / "dashboard" / "static" / "nguon.js").read_text(
        encoding="utf-8")
    # (nền tảng, số bài, chu kỳ, nhịp đăng — số bài cao nhất một ngày trong 14 ngày | None)
    ca = [("tiktok", 20, 1, None), ("tiktok", 5, 2, None), ("tiktok", 31, 1, None),
          ("facebook", 10, 1, None), ("facebook", 4, 3, None), ("instagram", 12, 1, None),
          ("threads", 10, 3, None), ("youtube", 10, 1, None),
          # Co theo nhịp đăng (18/10/2026): FB trang đăng ≤ 1 bài/ngày → 4 bài/lần, 7 ngày lấy đủ.
          ("facebook", 10, 1, 1), ("facebook", 10, 1, 6), ("tiktok", 20, 1, 2),
          ("instagram", 12, 1, 1)]
    vo = (f"var hs = {json.dumps(CP.hang_so_cho_trinh_duyet())}, ca = {json.dumps(ca)}, ra = [];\n"
          "var forms = ca.map(function (c) { var o = {textContent: ''}; ra.push(o);\n"
          "  var tt = c[3] == null ? {} : {'data-nhip': String(c[3]), 'data-ngay-day-du': '7',\n"
          "                               'data-san': '3'};\n"
          "  return {\n"
          "  elements: {nen_tang: {value: c[0]}, so_bai_moi_lan: {value: String(c[1])},\n"
          "             chu_ky_ngay: {value: String(c[2])}},\n"
          "  getAttribute: function (k) { return k in tt ? tt[k] : null; },\n"
          "  querySelector: function () { return o; }, addEventListener: function () {}}; });\n"
          "globalThis.document = {getElementById: function () {\n"
          "  return {textContent: JSON.stringify(hs)}; },\n"
          # Trang không có mục Đề xuất (duyệt hàng loạt, 18/10/2026): nguon.js dừng sau biểu mẫu.
          "  querySelector: function () { return null; },\n"
          "  querySelectorAll: function () { return forms; }};\n"
          + js + "\nconsole.log(JSON.stringify(ra.map(function (o) { return o.textContent; })));\n")
    f = tmp_path / "nguon_thu.js"
    f.write_text(vo, encoding="utf-8")
    chu = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True,
                                    encoding="utf-8", check=True).stdout)

    def so(s):
        return float(s.replace(".", "").replace(",", "."))
    for (p, b, k, nh), c in zip(ca, chu):
        n = {"id": 1, "nen_tang": p, "so_bai_moi_lan": b, "chu_ky_ngay": k}
        if nh is not None:
            (n,) = CP.gan_co_gian([n], {1: nh}, {})
        thang = re.match(r"≈ ([\d.,]+) USD/tháng theo bài", c)
        assert thang and so(thang.group(1)) == pytest.approx(
            round(CP.chi_phi_thang_nguon(n), 3), abs=1e-9), (p, b, k, c)
        kd = re.search(r"phí khởi động actor chung ([\d.,]+) USD", c)
        assert (so(kd.group(1)) if kd else 0.0) == pytest.approx(
            round(CP.phi_khoi_dong_ngay(p), 4), abs=1e-9), (p, c)


@pytest.mark.parametrize("so_bai, chu_ky", [(20, 2), (35, 1), (7, 5)])
def test_nguon_js_duyet_hang_loat_khop_python(tmp_path, so_bai, chu_ky):
    """Thanh duyệt đề xuất hàng loạt (18/10/2026) báo "≈ USD/tháng thêm" = tổng
    `chi_phi.chi_phi_thang_nguon` của các đề xuất đã chọn — cùng mức KỲ VỌNG của ô sửa nguồn
    (TikTok theo yêu cầu, không nhân hệ số 1,3; đề xuất mới chưa có nhịp đăng nên không co).
    Chạy nguon.js thật bằng node: bấm "Chọn cả … đề xuất khớp bộ lọc" rồi đọc ô ước tính."""
    import json
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("máy không có node")
    js = (Path(__file__).resolve().parents[1] / "dashboard" / "static" / "nguon.js").read_text(
        encoding="utf-8")
    dx = [("tiktok", 11), ("tiktok", 12), ("facebook", 13), ("facebook", 14),
          ("instagram", 15), ("threads", 16), ("youtube", 17)]
    vo = (f"var hs = {json.dumps(CP.hang_so_cho_trinh_duyet())}, dx = {json.dumps(dx)};\n"
          "var nghe = {}, o = {};\n"
          "function q(s) { return o[s] || (o[s] = {textContent: '', hidden: false,\n"
          "  disabled: false, setAttribute: function () {},\n"
          "  addEventListener: function (e, f) { nghe[s] = f; }}); }\n"
          "var dong = dx.map(function (c, i) { var chk = {checked: false};\n"
          "  var a = {'data-dx': String(c[1]), 'data-nt': c[0], 'data-thu-tu': String(i)};\n"
          "  return {hidden: false, getAttribute: function (k) { return k in a ? a[k] : null; },\n"
          "          querySelector: function () { return chk; }}; });\n"
          "var than = {querySelectorAll: function () { return dong; },\n"
          "  appendChild: function () {}, addEventListener: function () {}};\n"
          f"var thanh = {{hidden: true, elements: {{so_bai_moi_lan: {{value: '{so_bai}'}},\n"
          f"  chu_ky_ngay: {{value: '{chu_ky}'}}}}, querySelector: q,\n"
          "  querySelectorAll: function () { return []; }, classList: {toggle: function () {}},\n"
          "  setAttribute: function () {}, addEventListener: function () {}};\n"
          "globalThis.document = {getElementById: function () {\n"
          "  return {textContent: JSON.stringify(hs)}; },\n"
          "  querySelectorAll: function () { return []; },\n"
          "  querySelector: function (s) {\n"
          "    return s === '[data-dx-than]' ? than : s === '[data-dx-thanh]' ? thanh : null; }};\n"
          + js + "\nnghe['[data-dx-chon-het]']();\n"
          "console.log(JSON.stringify([q('[data-dx-so-chon]').textContent,\n"
          "                            q('[data-dx-uoc]').textContent]));\n")
    f = tmp_path / "nguon_hang_loat.js"
    f.write_text(vo, encoding="utf-8")
    so_chon, uoc = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True,
                                             encoding="utf-8", check=True).stdout)
    assert so_chon == len(dx)
    tong = sum(CP.chi_phi_thang_nguon({"nen_tang": p, "so_bai_moi_lan": so_bai,
                                       "chu_ky_ngay": chu_ky}) for p, _ in dx)
    assert uoc == f"≈ {tong:.2f} USD/tháng thêm".replace(".", ","), (uoc, tong)


def _nguon(i, p, so_bai, chu_ky, tt="dang_theo_doi"):
    return {"id": i, "nen_tang": p, "dinh_danh": f"n{i}", "ten": f"Nguồn {i}",
            "so_bai_moi_lan": so_bai, "chu_ky_ngay": chu_ky, "trang_thai": tt}


NGUON = [_nguon(1, "tiktok", 10, 1),            # 2 yêu cầu × 0,002 = 0,004/lượt
         _nguon(2, "instagram", 30, 2),         # 1 tài khoản × 0,0026/lượt
         _nguon(3, "youtube", 5, 1),            # miễn phí
         _nguon(4, "facebook", 5, 3, "tam_dung"),   # tạm dừng: không tính
         _nguon(5, "facebook", 4, 3)]           # 4 × 0,0025 = 0,01/lượt + 0,01 khởi động
GIUA_THANG = datetime.datetime(2026, 10, 15, 12, 0, tzinfo=VN)   # còn 16,5 ngày


def test_du_bao_tinh_tay():
    db = CP.du_bao(NGUON, da_tieu=1.2, tran_du_an=1.3, tran_platform=None, bay_gio=GIUA_THANG)
    assert db["ngay_con_lai"] == 16.5
    # Kỳ vọng (18/10/2026, không nhân 1,3). Còn lại: TikTok 16,5 × 0,004 = 0,066 (TikTok API theo
    # yêu cầu: 1 hồ sơ + 1 trang × 0,002, giá thật từng run); Instagram 8,25 × 0,0026 = 0,02145,
    # KHÔNG phí khởi động (17/10/2026: actor Apify chỉ tính theo tài khoản); Facebook (thedoor:
    # 0,0025/bài + 0,01/run) 5,5 × 0,01 = 0,055 + 5,5 × 0,01 khởi động = 0,055 → 0,11.
    nt = {x["nen_tang"]: x for x in db["nen_tang"]}
    assert [x["nen_tang"] for x in db["nen_tang"]] == ["facebook", "tiktok", "instagram", "youtube"]
    assert nt["tiktok"]["con_lai"] == pytest.approx(0.066, **XAP_XI)
    assert nt["instagram"]["nguon_con_lai"] == pytest.approx(0.02145, **XAP_XI)
    assert nt["instagram"]["khoi_dong_con_lai"] == 0
    assert nt["facebook"]["con_lai"] == pytest.approx(0.11, **XAP_XI)
    assert nt["facebook"]["khoi_dong_con_lai"] == pytest.approx(0.055, **XAP_XI)
    assert nt["facebook"]["so_nguon"] == 1                       # nguồn 4 tạm dừng
    assert nt["youtube"]["con_lai"] == 0 and nt["youtube"]["thang_cau_hinh"] == 0
    assert db["con_lai"] == pytest.approx(0.19745, abs=1e-4)
    assert db["du_bao_thang"] == pytest.approx(1.39745, abs=1e-4)
    # 30 ngày theo cấu hình: 0,12 + 0,039 + (0,1 + 0,1) = 0,359
    assert db["thang_cau_hinh"] == pytest.approx(0.359, abs=1e-4)
    assert db["tran"] == 1.3 and db["vuot"] is True
    assert db["vuot_usd"] == pytest.approx(0.09745, abs=1e-4)
    assert [(x["id"], x["thang_usd"]) for x in db["top_ton"]] == [
        (1, pytest.approx(0.12)), (5, pytest.approx(0.1)), (2, pytest.approx(0.039))]
    assert 4 not in [x["id"] for x in db["nguon"]] and 3 not in [x["id"] for x in db["top_ton"]]


def test_tran_hieu_luc_lay_tran_thap_hon():
    db = CP.du_bao(NGUON, 1.2, tran_du_an=5.0, tran_platform=None, bay_gio=GIUA_THANG)
    assert db["tran"] == 5.0 and db["vuot"] is False and db["vuot_usd"] == 0
    db = CP.du_bao(NGUON, 1.2, tran_du_an=5.0, tran_platform=1.3, bay_gio=GIUA_THANG)
    assert (db["tran"], db["tran_platform"], db["vuot"]) == (1.3, 1.3, True)
    assert CP.tran_hieu_luc(1.0, 3.0) == 1.0 and CP.tran_hieu_luc(4.0, None) == 4.0


def test_chi_nguon_tam_dung_va_youtube_thi_khong_ton():
    db = CP.du_bao([_nguon(1, "youtube", 30, 1), _nguon(2, "tiktok", 30, 1, "tam_dung")],
                   0.0, 5.0, None, GIUA_THANG)
    assert db["con_lai"] == 0 and db["du_bao_thang"] == 0 and db["top_ton"] == []
    assert [x["nen_tang"] for x in db["nen_tang"]] == ["youtube"]
    trong = CP.du_bao([], 0.7, 5.0, None, GIUA_THANG)
    assert trong["du_bao_thang"] == 0.7 and trong["nen_tang"] == [] and not trong["vuot"]


def test_khoi_dong_theo_chu_ky_ngan_nhat_cua_nen_tang():
    """Hai nguồn Facebook chu kỳ 1 và 7: nền tảng có ngày quét MỖI ngày -> khởi động 30 lần.
    (Instagram từ 17/10/2026 không còn phí khởi động nên kiểm trên Facebook.)"""
    n1, n2 = _nguon(1, "facebook", 5, 1), _nguon(2, "facebook", 5, 7)
    db = CP.du_bao([n1, n2], 0, 5, None, GIUA_THANG)
    (fb,) = db["nen_tang"]
    assert CP.phi_khoi_dong_ngay("facebook") > 0
    assert fb["thang_cau_hinh"] == pytest.approx(
        30 * CP.chi_phi_luot_nguon(n1) + 30 / 7 * CP.chi_phi_luot_nguon(n2)
        + 30 * CP.phi_khoi_dong_ngay("facebook"))


@pytest.mark.parametrize("luc, con, so_ngay", [
    (datetime.datetime(2026, 10, 31, 23, 0, tzinfo=VN), 1 / 24, 31),
    (datetime.datetime(2026, 10, 31, 17, 30, tzinfo=UTC), 30 - 0.5 / 24, 30),   # 00:30 1/11 VN
    (datetime.datetime(2026, 10, 31, 16, 59, tzinfo=UTC), 1 / 1440, 31),        # 23:59 31/10 VN
    (datetime.datetime(2026, 12, 15, 0, 0, tzinfo=VN), 17.0, 31),               # sang năm mới
    (datetime.datetime(2028, 2, 1, 0, 0, tzinfo=VN), 29.0, 29),                 # năm nhuận
    (datetime.datetime(2026, 10, 1, 0, 0, tzinfo=VN), 31.0, 31),
])
def test_ngay_con_lai_theo_thang_gio_vn(luc, con, so_ngay):
    assert CP.ngay_con_lai(luc) == pytest.approx(con, abs=1e-9)
    assert CP.so_ngay_thang(luc) == so_ngay


def test_hang_so_cho_trinh_duyet():
    hs = CP.hang_so_cho_trinh_duyet()
    # "start" = phí khởi động actor THEO DÕI NGUỒN (17/10/2026: Threads qua actor hồ sơ, 0 USD;
    # Facebook qua thedoor, 0,01 USD/run); "khoi_nguon" cùng số (nguon.js đọc trước).
    assert {k: hs[k] for k in ("gia", "he_so", "start", "khoi_nguon", "ngay")} == {
        "gia": CP.GIA, "he_so": 1.3, "start": CP.KHOI_NGUON, "khoi_nguon": CP.KHOI_NGUON,
        "ngay": 30}
    assert CP.KHOI_NGUON == {**CP.START_COST, "facebook": 0.01, "threads": 0.0}
    # Đợt 2e: đủ hằng số để trang Ngân sách tính lại ước tính cấu hình ngay trên trình duyệt.
    assert hs["tk_gia"] == CP.TK_GIA and hs["bl_gia"] == CP.BL_GIA and hs["gioi_han"] == CP.GIOI_HAN


def test_cau_hinh_dashboard_khop_mark():
    """Bản sao `theo_doi.cau_hinh` / ước tính trên dashboard phải ra cùng số với Mark."""
    import theo_doi as T
    cac = [
        {"tk_bat": True, "tk_so_bai": 15, "bl_bat": True, "bl_so_bai": 10, "bl_moi_bai": 0,
         "cau_hinh": {}},
        {"tk_bat": True, "tk_so_bai": 15, "bl_bat": False, "bl_so_bai": 10, "bl_moi_bai": 0,
         "cau_hinh": {"tu_khoa": {"facebook": {"so_bai": 60}, "instagram": {"so_tu": 4}},
                      "binh_luan": {"tiktok": {"bat": True, "so_bai": 30, "moi_bai": 2},
                                    "youtube": {"so_bai": "xx"}}}},
        # Rác trong JSONB: chuỗi "false", số âm, bool, null -> theo cột chung, KHÔNG về 0 (= hết).
        {"tk_bat": True, "tk_so_bai": 15, "bl_bat": True, "bl_so_bai": 10, "bl_moi_bai": 40,
         "cau_hinh": {"tu_khoa": {"tiktok": {"bat": "false"}, "instagram": {"so_tu": 0}},
                      "binh_luan": {"tiktok": {"moi_bai": -3}, "facebook": {"moi_bai": None},
                                    "instagram": {"so_bai": True}, "youtube": {"bat": 1}}}},
        # Công tắc tổng tắt: mọi nền tảng tắt dù JSONB bật.
        {"tk_bat": False, "tk_so_bai": 15, "bl_bat": False, "bl_so_bai": 10, "bl_moi_bai": 0,
         "cau_hinh": {"tu_khoa": {"tiktok": {"bat": True}}, "binh_luan": {"tiktok": {"bat": True}}}},
    ]
    tu = ["hapas", "túi hapas", "yeutudieunhonhat", "hahahapas"]
    for da in cac:
        for nhom in ("tu_khoa", "binh_luan"):
            for p in CP.NEN_TANG:
                assert CP.cau_hinh(da, nhom, p) == T.cau_hinh(da, nhom, p), (nhom, p)
        for p in CP.NEN_TANG:
            c = CP.cau_hinh(da, "tu_khoa", p)
            assert CP.uoc_tk_nen_tang(p, c["so_bai"], tu, c["so_tu"]) == \
                T.uoc_tu_khoa_nen_tang(p, c["so_bai"], tu, c["so_tu"])
    assert CP.GIOI_HAN == T.GIOI_HAN and CP.TK_GIA == T._TK_GIA
    rac = cac[2]
    assert not CP.cau_hinh(rac, "tu_khoa", "tiktok")["bat"]
    assert CP.cau_hinh(rac, "tu_khoa", "instagram")["so_tu"] == CP.TK_IG_TOI_DA_TU
    assert [CP.cau_hinh(rac, "binh_luan", p)["moi_bai"] for p in ("tiktok", "facebook")] == [40, 40]
    assert CP.cau_hinh(rac, "binh_luan", "instagram")["so_bai"] == 10
    assert not CP.cau_hinh(rac, "binh_luan", "youtube")["bat"]
    assert not any(CP.cau_hinh(cac[3], n, "tiktok")["bat"] for n in ("tu_khoa", "binh_luan"))
    for da in ({"ten": "HAPAS", "tu_khoa": []},
               {"tu_khoa": [" Túi  HAPAS ", "tui hapas", "Đồng hồ", "dong ho", ""] + list("abcdefghijklmn")}):
        assert CP.tu_tim(da) == T.tu_tim(da)
    # Dashboard không biết gói Apify: Facebook báo theo đúng số bài cấu hình (mức trần).
    b = CP.bang_cau_hinh({**cac[1], "tu_khoa": tu})
    assert b["tu_khoa"]["facebook"]["uoc"] == T.uoc_tu_khoa_nen_tang("facebook", 60, tu,
                                                                      fb_toi_da=10 ** 6)
