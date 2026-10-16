"""Dashboard — lắng nghe Báo & Web (16/10/2026, `docs/lang-nghe-web.md`).

Bài web là dòng `bai` với nen_tang = 'web', nguon_id NULL, tai_khoan = tên miền, xem / thích / chia
sẻ NULL, thêm `kieu_trang`, `muc_nhac`, `la_pr`. Kiểm: chiều lọc "loại trang", số NULL hiện "—"
(không 0), thẻ KPI web, chi phí web khớp Mark (bài đối chiếu import `theo_doi`), số lượt web theo
lịch (≤ 1/ngày ngoài chiến dịch, mọi lượt trong chiến dịch), dòng Báo & Web trên trang Ngân sách,
ô "Từ khoá chiến dịch" của lịch. Dữ liệu tổng hợp, tính tay."""
from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from dashboard import chi_phi as CP
from dashboard import chi_so as CS
from dashboard import lich_quet as LQ

VN = datetime.timezone(datetime.timedelta(hours=7))
GOC = Path(__file__).resolve().parents[1]
TU, DEN = datetime.date(2026, 10, 8), datetime.date(2026, 10, 14)
HOM_NAY = datetime.date(2026, 10, 16)


def _bai(i, nen_tang="tiktok", **kw):
    r = {"khoa": f"{nen_tang}:{i}", "nen_tang": nen_tang, "nguon_id": None, "kieu_quet": "tu_khoa",
         "link": f"https://x.vn/{i}", "tac_gia": f"T{i}", "tai_khoan": f"t{i}", "followers": None,
         "dang_luc": datetime.datetime(2026, 10, 10, 9, 0, tzinfo=VN), "noi_dung": "hapas túi",
         "hashtag": "", "sac_thai": "Tích cực", "chu_de": None, "xem": 100, "thich": 5,
         "binh_luan": 2, "chia_se": 1, "nguon_loai": None}
    r.update(kw)
    return r


def _web(i, mien="cafef.vn", **kw):
    return _bai(i, "web", tai_khoan=mien, tac_gia=mien.split(".")[0].upper(), xem=None,
                thich=None, chia_se=None, binh_luan=kw.pop("binh_luan", None),
                kieu_trang=kw.pop("kieu_trang", "bao"), muc_nhac=kw.pop("muc_nhac", "chinh"),
                la_pr=kw.pop("la_pr", False), link=f"https://{mien}/bai-{i}", **kw)


ROWS = [_bai(1), _bai(2, "facebook"),
        _web(3, "cafef.vn", muc_nhac="tieu_de", la_pr=True),
        _web(4, "cafebiz.vn", muc_nhac="thoang"),
        _web(5, "voz.vn", kieu_trang="dien_dan", binh_luan=7, muc_nhac="tieu_de", la_pr=None)]


# ───────────────────────────── chiều lọc "loại trang" ─────────────────────────────
def test_ten_nen_tang_va_bo_loc_nhan_web():
    assert CS.TEN_NEN_TANG["web"] == "Báo & Web"
    b = CS.doc_bo_loc({"nen_tang": "tiktok,instagram,youtube,facebook,threads,web"})
    assert len(b["nen_tang"]) == 6                         # đủ mọi nền tảng trong một bộ lọc
    assert CS.doc_bo_loc({"kieu_trang": "dien_dan,bao,bao"})["kieu_trang"] == ("bao", "dien_dan")
    with pytest.raises(CS.LoiBoLoc):
        CS.doc_bo_loc({"kieu_trang": "tap_chi"})
    assert CS.NHAN_BO_LOC["kieu_trang"] == CS.KIEU_TRANG and "kieu_trang" in CS.CHIEU_LOC
    assert CS.bo_loc_json(CS.doc_bo_loc({"kieu_trang": "blog"}))["kieu_trang"] == ["blog"]
    assert ("kieu_trang", ("blog",)) in CS.khoa_bo_loc(CS.doc_bo_loc({"kieu_trang": "blog"}))
    # khoá nguồn của bài web = "web:<tên miền>" — tách đúng như các nền tảng khác
    assert CS.khoa_nguon_chu(ROWS[2]) == "web:cafef.vn"
    assert CS.doc_bo_loc({"nguon": "web:cafef.vn,tiktok:a, b"})["nguon"] == ("tiktok:a, b",
                                                                               "web:cafef.vn")


def test_loc_kieu_trang_chi_khop_bai_web_dung_loai():
    assert CS.loc_bai(ROWS, CS.doc_bo_loc({})) == ROWS             # trống: bài MXH vẫn khớp
    bao = CS.loc_bai(ROWS, CS.doc_bo_loc({"kieu_trang": "bao"}))
    assert [r["khoa"] for r in bao] == ["web:3", "web:4"]
    hai = CS.loc_bai(ROWS, CS.doc_bo_loc({"kieu_trang": "bao,dien_dan", "nen_tang": "web"}))
    assert len(hai) == 3
    f = CS.bien_dich(CS.doc_bo_loc({"kieu_trang": "dien_dan"}))
    assert f.can_bai and not f.rong
    bl = {"khoa_bai": "web:5", "nen_tang": "web", "nguon_id": None, "loai": "hop_le"}
    assert f.hong_bl(bl, ROWS[4]) == 0 and f.hong_bl(bl, None) and f.hong_bl(bl, ROWS[2])


def test_dem_o_loc_kieu_trang():
    d = CS.tong_quan_loc(ROWS, [], TU, DEN)["bo_loc_dem"]
    assert d["kieu_trang"] == {"bao": 2, "dien_dan": 1}           # bài MXH không vào ô nào
    assert d["nen_tang"]["web"] == 3
    # đang chọn "bao": ô "dien_dan" vẫn có số (đếm bỏ qua chính chiều đó), nền tảng chỉ còn web
    d = CS.tong_quan_loc(ROWS, [], TU, DEN, CS.doc_bo_loc({"kieu_trang": "bao"}))["bo_loc_dem"]
    assert d["kieu_trang"] == {"bao": 2, "dien_dan": 1} and d["nen_tang"] == {"web": 2}


# ───────────────────────────── số NULL hiện "—", KPI web ─────────────────────────────
def test_so_null_cua_bai_web_khong_thanh_0():
    th = CS.tong_hop(ROWS, TU, DEN, hom_nay=HOM_NAY)
    web = {x["khoa"]: x for x in th["top_bai"] if x["nen_tang"] == "web"}
    assert web["web:3"]["xem"] is None and web["web:3"]["thich"] is None
    assert web["web:3"]["chia_se"] is None and web["web:3"]["binh_luan"] is None
    assert web["web:5"]["binh_luan"] == 7 and web["web:5"]["thao_luan"] == 8   # 1 + trả lời
    assert web["web:3"]["kieu_trang"] == "bao" and web["web:3"]["la_pr"] is True
    assert web["web:3"]["muc_nhac"] == "tieu_de"
    mxh = next(x for x in th["top_bai"] if x["khoa"] == "tiktok:1")
    assert mxh["xem"] == 100 and mxh["kieu_trang"] is None and mxh["la_pr"] is None
    assert CS.so_co(None) is None and CS.so_co(0) == 0 and CS.so_co("12") == 12
    # Nguồn web (tên miền): cột lượt xem "—" chứ không 0; nguồn MXH giữ số
    nt = {g["nen_tang"]: g for g in th["top_nguon"]}
    assert all(n["xem"] is None for n in nt["web"]["nguon"])
    assert nt["tiktok"]["nguon"][0]["xem"] == 100
    assert {n["khoa_nguon"] for n in nt["web"]["nguon"]} == {"web:cafef.vn", "web:cafebiz.vn",
                                                            "web:voz.vn"}
    ct = CS.chi_tiet_bai(ROWS, TU, DEN, nen_tang="web")
    assert ct["tong"] == 3 and all(b["xem"] is None for b in ct["bai"])
    # KPI cộng: web không làm lệch số xem / tương tác (NULL = không góp), thảo luận vẫn đếm
    k = th["kpi"]
    assert k["xem"] == 200 and k["tuong_tac"] == 2 * (5 + 2 + 1) + 7
    assert k["bai"] == 5 and k["thao_luan"] == 5 + 2 + 2 + 7


def test_kpi_web_mien_pr_tieu_de():
    w = CS.kpi(ROWS)["web"]
    assert w["bai"] == 3 and w["mien"] == 3
    assert w["pr"] == 1 and w["pr_pt"] == 50.0                    # la_pr NULL không vào mẫu số
    assert w["tieu_de"] == 2 and w["tieu_de_pt"] == round(200 / 3, 1)
    assert w["theo_kieu"] == {"bao": 2, "dien_dan": 1}
    assert CS.kpi(ROWS[:2])["web"] is None


# ───────────────────────────── chi phí: khớp Mark ─────────────────────────────
TU_VD = ["hapas", "túi hapas", "ví hapas", "quà tặng hapas", "yêu từ điều nhỏ nhất", "hapas.vn"]


def test_rut_gon_va_uoc_web_tinh_tay():
    assert CP.rut_gon_web(TU_VD) == ["hapas", "yêu từ điều nhỏ nhất"]
    assert CP.rut_gon_web([" Hapas ", "HAPAS", "", "  ", "Đồng hồ", "dong ho", "!!"]) == \
        ["Hapas", "Đồng hồ", "dong ho"]                  # trùng hoa thường bỏ; "dong ho" ≠ (cùng tập chữ)
    assert CP.so_cau_web(TU_VD) == 1 and CP.so_cau_web([f"tu{i}" for i in range(30)]) == 4
    # 1 câu × ⌈15/10⌉ = 2 trang × 0,0005 + 10 trang dự phòng × 0,009, nhân 1,3
    assert CP.uoc_web(15, TU_VD) == round((2 * 0.0005 + 10 * 0.009) * 1.3, 4) == 0.1183
    assert CP.uoc_web(15, TU_VD, 0) == 0.0013 and CP.uoc_web(0, TU_VD) == 0.0
    assert CP.uoc_web(15, ["", "!!"]) == 0.0
    # 9 từ rời -> 3 câu; 25 kết quả -> 3 trang
    assert CP.uoc_web(25, [f"x{i}" for i in range(9)], 2) == round((9 * 0.0005 + 2 * 0.009) * 1.3, 4)


def test_chi_phi_web_khop_mark():
    T = pytest.importorskip("theo_doi")
    W = pytest.importorskip("nguon_web")
    if not hasattr(T, "uoc_web"):
        pytest.skip("theo_doi.uoc_web chưa có (backend đang viết)")
    assert (CP.WEB_GIA_TRANG, CP.WEB_GIA_BOC, CP.WEB_TU_MOI_CAU, CP.WEB_TOI_DA_CAU,
            CP.WEB_KQ_MOI_TRANG, CP.WEB_BOC_MAC_DINH, CP.HE_SO_UOC) == (
        T.WEB_GIA_TRANG, T.WEB_GIA_BOC, T.WEB_TU_MOI_CAU, T.WEB_TOI_DA_CAU,
        T.WEB_KQ_MOI_TRANG, T.WEB_BOC_MAC_DINH, T._HE_SO_UOC)
    assert CP.WEB_GIO_GIAN == T.WEB_GIO_GIAN
    assert "web" in T.TK_NEN_TANG and "web" not in T.MAC_DINH_TAT and "web" not in CP.MAC_DINH_TAT
    bo = [TU_VD, ["hapas"], [], ["Túi XÁCH", "túi xách nữ", "ví", "Ví da", "đồng hồ", "dong ho",
                                 "a.b", "x-y z", "ÁO", "ao"] + [f"k{i}" for i in range(12)],
          ["hapas", "hapas"], ["  ", "!!", "ĐĐ"]]
    for tu in bo:
        assert CP.rut_gon_web(tu) == W.rut_gon_tu_khoa(tu), tu
        for so_bai in (0, 1, 10, 11, 15, 100):
            for boc in (0, 2, 10):
                assert CP.uoc_web(so_bai, tu, boc) == T.uoc_web(so_bai, tu, boc), (tu, so_bai, boc)
            assert CP.uoc_tk_nen_tang("web", so_bai, tu) == T.uoc_tu_khoa_nen_tang("web", so_bai, tu)
    cac = [{"tk_bat": True, "tk_so_bai": 15, "cau_hinh": {}},
           {"tk_bat": True, "tk_so_bai": 15, "cau_hinh": {"tu_khoa": {"web": {"boc": 0}}}},
           {"tk_bat": True, "tk_so_bai": 15,
            "cau_hinh": {"tu_khoa": {"web": {"boc": "3", "so_bai": 30, "bat": True}}}},
           {"tk_bat": True, "tk_so_bai": 15,
            "cau_hinh": {"tu_khoa": {"web": {"boc": True, "bat": "false"}}}},
           {"tk_bat": True, "tk_so_bai": 15, "cau_hinh": {"tu_khoa": {"web": {"boc": -4}}}},
           {"tk_bat": False, "tk_so_bai": 15, "cau_hinh": {"tu_khoa": {"web": {"bat": True}}}}]
    for da in cac:
        assert CP.cau_hinh(da, "tu_khoa", "web") == T.cau_hinh(da, "tu_khoa", "web"), da
        b = CP.bang_cau_hinh({**da, "tu_khoa": TU_VD})
        assert b["uoc_tk"] == T.uoc_tu_khoa_du_an({**da, "tu_khoa": TU_VD}, fb_toi_da=10 ** 6), da
    assert CP.uoc_tu_khoa_luot(15, TU_VD) == T.uoc_tu_khoa(15, TU_VD)


def test_bang_cau_hinh_web():
    da = {"tk_bat": True, "tk_so_bai": 15, "tu_khoa": TU_VD,
          "cau_hinh": {"tu_khoa": {"web": {"boc": 2}}}}
    b = CP.bang_cau_hinh(da)
    w = b["tu_khoa"]["web"]
    assert w["bat"] and w["boc"] == 2 and w["so_tu_gui"] == 2 and w["so_cau"] == 1
    assert w["uoc"] == b["uoc_web"] == round((2 * 0.0005 + 2 * 0.009) * 1.3, 4)
    assert b["uoc_tk_mxh"] == round(b["uoc_tk"] - b["uoc_web"], 4)
    assert b["binh_luan"]["web"]["uoc"] == 0.0                    # web không cào bình luận
    hs = CP.hang_so_cho_trinh_duyet()
    assert hs["web"]["gia_trang"] == 0.0005 and hs["web"]["boc_mac_dinh"] == 10
    assert "web" in hs["nen_tang"]


# ───────────────────────────── số lượt web theo lịch ─────────────────────────────
BAY_GIO = datetime.datetime(2026, 10, 16, 6, 0, tzinfo=VN)


def _lich(i, kieu, ch, bat=True):
    return {"id": i, "kieu": kieu, "cau_hinh": ch, "bat": bat, "quet_moi_nguon": False}


def test_luot_web_mot_lan_moi_ngay_ngoai_chien_dich():
    het = datetime.datetime(2026, 10, 20, 23, 59, tzinfo=VN)
    hai_gio = _lich(1, "moi_n_gio", {"moi_gio": 2, "tu": "07:00", "den": "23:00", "thu": []})
    # 16→20/10: 5 ngày, mỗi ngày 9 mốc -> 5 lượt web (không phải 45)
    assert CP.luot_web_thuong([hai_gio], BAY_GIO, het) == 5
    tuan = _lich(2, "hang_tuan", {"gio": ["08:00", "20:00"], "thu": [5]})       # T5 = 16/10
    assert CP.luot_web_thuong([tuan], BAY_GIO, het) == 1
    assert CP.luot_web_thuong([hai_gio, tuan], BAY_GIO, het) == 5               # trùng ngày: 1 lượt
    cd = _lich(3, "chien_dich", {"tu_luc": "2026-10-17T00:00", "den_luc": "2026-10-18T23:59",
                                 "moi_phut": 360})
    # chiến dịch 17–18/10: lịch thường nhường -> còn 16, 19, 20; lượt chiến dịch đếm riêng
    assert CP.luot_web_thuong([hai_gio, cd], BAY_GIO, het) == 3
    assert CP.luot_web_thuong([_lich(4, "hang_ngay", {"gio": ["08:00"], "thu": []}, bat=False)],
                              BAY_GIO, het) == 0


def test_uoc_lich_va_du_bao_lich_tach_web():
    bang = CP.bang_cau_hinh({"tk_bat": True, "tk_so_bai": 15, "tu_khoa": TU_VD, "cau_hinh": {}})
    thuong = _lich(1, "moi_n_gio", {"moi_gio": 2, "tu": "07:00", "den": "23:00", "thu": []})
    cd = _lich(2, "chien_dich", {"tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-21T08:00",
                                 "moi_phut": 360})
    u = CP.uoc_lich(thuong, bang, [])
    assert u["web"] == bang["uoc_web"] and not u["web_moi_luot"]
    assert u["moi_luot"] == round(bang["uoc_tk"] - bang["uoc_web"] + bang["uoc_bl"], 4)
    v = CP.uoc_lich(cd, bang, [])
    assert v["web_moi_luot"] and v["moi_luot"] == round(bang["uoc_tk"] + bang["uoc_bl"], 4)
    dl = CP.du_bao_lich([thuong, cd], bang, [], BAY_GIO)
    # tháng 10 còn 16→31 = 16 ngày; chiến dịch 20/10 08:00 → 21/10 08:00 mỗi 6 giờ = 5 lượt, ngày
    # 20 và 21 vẫn có mốc lịch thường ngoài khung (07:00 ngày 20; sau 08:00 ngày 21)
    assert dl["theo_lich"][2] == 5
    assert dl["luot_web_con_lai"] == 16 + 5
    assert dl["web_them"] == round(16 * bang["uoc_web"], 4)
    assert dl["luot_web_30"] >= dl["luot_web_con_lai"]


# ───────────────────────────── ngan_sach.js ↔ chi_phi (node) ─────────────────────────────
def test_ngan_sach_js_rut_gon_khop_python(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    js = (GOC / "dashboard" / "static" / "ngan_sach.js").read_text(encoding="utf-8")
    khoi = re.search(r"// <web>.*?// </web>", js, re.DOTALL).group(0)
    bo = [TU_VD, ["hapas"], [], [" Hapas ", "HAPAS", "", "Đồng hồ", "dong ho", "!!"],
          ["Túi XÁCH", "túi xách nữ", "ví", "Ví da", "a.b", "x-y z", "ÁO", "ao", "ĐĐ"]
          + [f"k{i}" for i in range(12)]]
    ca = [(tu, so_bai, boc) for tu in bo for so_bai in (0, 1, 15, 100) for boc in (0, 10)]
    hs = CP.hang_so_cho_trinh_duyet()
    chay = (f"var hs = {json.dumps({'web': hs['web'], 'he_so': hs['he_so']})};\n"
            "function r4(x) { return Number(x.toFixed(4)); }\n" + khoi +
            f"\nvar ca = {json.dumps(ca, ensure_ascii=False)};\n"
            "console.log(JSON.stringify(ca.map(function (c) {"
            " return [rutGonWeb(c[0]), soCauWeb(c[0]), uocWeb(c[1], c[0], c[2])]; })));\n")
    f = tmp_path / "web.js"
    f.write_text(chay, encoding="utf-8")
    ra = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True,
                                   encoding="utf-8", check=True, timeout=30).stdout)
    assert ra == [[CP.rut_gon_web(tu), CP.so_cau_web(tu), CP.uoc_web(s, tu, b)] for tu, s, b in ca]


# ───────────────────────────── lịch: từ khoá chiến dịch ─────────────────────────────
def _form_cd(**kw):
    return {"kieu": "chien_dich", "tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-22T08:00",
            "moi": "6", "don_vi": "gio", **kw}


def test_tu_khoa_chien_dich_luu_va_doc_lai():
    d = LQ.chuan_hoa(_form_cd(tu_khoa_them="yêu từ điều nhỏ nhất\r\nDo anything for love, "
                                              " do  ANYTHING for love ,,\n#hapas2010"), BAY_GIO)
    assert d["cau_hinh"]["tu_khoa_them"] == ["yêu từ điều nhỏ nhất", "Do anything for love",
                                             "#hapas2010"]
    assert "tu_khoa_them" not in LQ.chuan_hoa(_form_cd(tu_khoa_them=" , \n"), BAY_GIO)["cau_hinh"]
    assert "tu_khoa_them" not in LQ.chuan_hoa(_form_cd(), BAY_GIO)["cau_hinh"]
    # chỉ kiểu chiến dịch: lịch thường bỏ qua ô này
    d2 = LQ.chuan_hoa({"kieu": "hang_ngay", "gio": "08:00", "tu_khoa_them": "abc"}, BAY_GIO)
    assert "tu_khoa_them" not in d2["cau_hinh"]
    f = LQ.tu_form({**d, "id": 1}, BAY_GIO)
    assert f["tu_khoa_them"] == "yêu từ điều nhỏ nhất\nDo anything for love\n#hapas2010"
    assert LQ.chuan_hoa(LQ.bieu_mau(f), BAY_GIO)["cau_hinh"] == d["cau_hinh"]      # vòng tròn
    assert LQ.tu_form_mac_dinh(BAY_GIO)["tu_khoa_them"] == ""
    assert LQ.gia_tri_tu_form(_form_cd(tu_khoa_them="x" * 900), BAY_GIO)["tu_khoa_them"] == "x" * 900
    assert LQ.loi_cau_hinh("chien_dich", d["cau_hinh"]) == ""          # Mark vẫn chạy được lịch


@pytest.mark.parametrize("gia_tri, loi", [
    (",".join(f"k{i}" for i in range(11)), "tối đa 10 mục"),
    ("a" * 81, "dài quá 80 ký tự"),
])
def test_tu_khoa_chien_dich_sai(gia_tri, loi):
    with pytest.raises(LQ.LoiLich, match=loi):
        LQ.chuan_hoa(_form_cd(tu_khoa_them=gia_tri), BAY_GIO)
    assert len(LQ.tu_khoa_them(",".join(f"k{i}" for i in range(10)) + ",K1")) == 10   # trùng không tính


# ───────────────────────────── trang: Ngân sách, Lịch, Chỉ số ─────────────────────────────
def test_trang_ngan_sach_dong_bao_web_va_luu_boc():
    from test_dashboard_app import QL, XEM, dang_nhap, tao, thong_bao
    _, c, kho = tao()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15, tu_khoa=TU_VD)
    csrf = dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert 'data-nt="web"' in t and ">Báo &amp; Web" in t
    assert re.search(r'name="tk_web_bat" value="1"[^>]*checked', t)          # mặc định BẬT
    assert 'name="tk_web_boc"' in t and 'name="bl_web_bat"' not in t
    assert "0,0005 USD/trang" in t and "0–2 trang" in t                      # ghi chú trong ⓘ
    assert 'data-o="tk-web" data-usd="0.1183"' in t and "2 → 1 câu" in t
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "tk_web_bat": "1",
                                                   "tk_web_so_bai": "20", "tk_web_boc": "0"})
    assert "Đã lưu cấu hình thu thập" in thong_bao(c, r)
    ch = kho.du_an["hapas"]["cau_hinh"]
    assert ch["tu_khoa"]["web"] == {"bat": True, "so_bai": 20, "boc": 0} and "web" not in ch["binh_luan"]
    assert CP.bang_cau_hinh(kho.du_an["hapas"])["uoc_web"] == 0.0013
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "tk_web_bat": "1",
                                                   "tk_web_boc": "-1"})
    assert "Báo &amp; Web: số trang đọc dự phòng" in thong_bao(c, r)
    assert kho.du_an["hapas"]["cau_hinh"] == ch
    dang_nhap(c, XEM)
    t = c.get("/ngan-sach").text
    assert 'data-nt="web"' in t and "tối đa 0 trang/lượt" in t and 'name="tk_' not in t


def test_trang_lich_co_o_tu_khoa_chien_dich():
    from test_dashboard_app import QL, dang_nhap, tao
    _, c, _ = tao()
    dang_nhap(c, QL)
    t = c.get("/lich-quet?du_an=hapas").text
    assert 'name="tu_khoa_them"' in t
    assert "Chỉ dùng cho tìm Báo &amp; Web trong khung chiến dịch" in t


def test_api_chi_so_co_bai_web():
    from test_dashboard_app import XEM, dang_nhap, tao
    _, c, kho = tao()
    kho.bai = [dict(r) for r in ROWS]
    dang_nhap(c, XEM)
    d = c.get("/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14").json()
    assert d["kpi"]["web"]["bai"] == 3
    assert {x["nen_tang"] for x in d["nen_tang"]} >= {"web"}
    assert d["bo_loc_dem"]["kieu_trang"] == {"bao": 2, "dien_dan": 1}
    d = c.get("/api/chi-so?du_an=hapas&tu=2026-10-08&den=2026-10-14&kieu_trang=dien_dan").json()
    assert d["kpi"]["bai"] == 1 and d["bo_loc"]["kieu_trang"] == ["dien_dan"]
    r = c.get("/api/bai?du_an=hapas&tu=2026-10-08&den=2026-10-14&ct_nen_tang=web")
    assert r.status_code == 200 and all(b["xem"] is None for b in r.json()["bai"])
    assert c.get("/api/chi-so?du_an=hapas&kieu_trang=tap_chi").status_code == 400
    t = c.get("/?du_an=hapas").text                      # trang dựng bằng JS: nhãn đi trong cấu hình
    assert '"kieu_trang"' in t and "Diễn đàn" in t


def test_nguon_khong_cho_them_nguon_web():
    from dashboard import nhap_lieu as NL
    assert "web" not in NL.NEN_TANG and "web" not in NL.TEN_NEN_TANG
    from test_dashboard_app import QL, dang_nhap, tao
    _, c, kho = tao()
    kho.bai = [dict(r) for r in ROWS]
    dang_nhap(c, QL)
    t = c.get("/nguon?du_an=hapas").text
    assert '<option value="web"' not in t
