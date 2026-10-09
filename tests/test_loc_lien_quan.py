"""Canh bộ lọc LIÊN QUAN của social_listen (từ khoá · loại trừ · thị trường VN · AI).

Nhiễu thật trong sheet ngày 01/10/2026 (brand "hapas"):
  • Threads: "Mason Nguyễn" ("vote Tinh Hà ở đâu"), "Bùi Trường Linh" ("Đt gập thì a k
    có…"), "Tu Anh Vu" (Thơm Da LAB x Folio's Men x Narciso) — không bài nào có chữ
    "hapas"; TikTok/Threads trước đó KHÔNG hề bị kiểm từ khoá.
  • Threads: tote của HAPAS THAILAND; YouTube: ban metal "SHINAI – Hapas Ashen",
    "Taj Nets – aquaculture hapa" (lưới nuôi cá).
  • `loc_bang_ai=True` cứng kể cả khi bộ lọc AI không chạy dòng nào vì hết giờ.
Bài bị loại KHÔNG được biến mất: phải nằm ở tab "Bị loại" kèm lý do.
Từ 01/10/2026 các luật ở đây là DỰ PHÒNG khi bước AI phân xử không chạy (bộ thử tắt AI
qua SOCIAL_AI_PHAN_XU=0); bước AI xem test_phan_xu_ai.py.
"""
from __future__ import annotations

import datetime
import json

import pytest

import apify_tool as A
from sheet_gia import LarkGia

Q = ["hapas"]


def _bai(text="", kenh="", hashtags="", **kw):
    d = {"kenh": kenh, "followers": 0, "views": 0, "likes": 0, "comments": 0,
         "shares": 0, "hashtags": hashtags, "text": text, "link": f"https://x/{kenh}/{text[:8]}"}
    d.update(kw)
    return d


# ───────────────────────────── _khop_tu_khoa ─────────────────────────────

@pytest.mark.parametrize("d", [
    _bai("vote Tinh Hà ở đâu", "Mason Nguyễn", username="mason.ng"),
    _bai("Đt gập thì a k có…", "Bùi Trường Linh"),
    _bai("Thơm Da LAB x Folio's Men x Narciso", "Tu Anh Vu"),
    _bai("Taj Nets – aquaculture hapa fish net cage", "Taj Nets"),
    _bai("hapa systems for tilapia", "fish farm"),        # ghép "hapasystems" cắt giữa chữ
])
def test_bai_khong_nhac_tu_khoa_bi_loai(d):
    assert not A._khop_tu_khoa(d, Q)


@pytest.mark.parametrize("d", [
    _bai("review nước hoa mới #HAPASNUOCHOAHAPAS", "Ngọc"),       # hashtag gõ dính
    _bai("Túi mới về nè", "hapas.official"),                       # tên kênh có dấu chấm
    _bai("Túi mới về nè", "Ngọc", username="hapas_vn"),           # username
    _bai("x", "y", hashtags="HAPAS, tuixach"),
    _bai("Mê túi HAPAS quá", "Ngọc"),
])
def test_bai_nhac_tu_khoa_duoc_giu(d):
    assert A._khop_tu_khoa(d, Q)


def test_ban_metal_hapas_ashen_van_khop_tu_khoa_de_cong_thi_truong_xu_ly():
    """Có NGUYÊN chữ "Hapas" nên luật chuỗi không loại được — việc của cổng VN/AI."""
    assert A._khop_tu_khoa(_bai("SHINAI – Hapas Ashen // Humanity's Last Breath"), Q)


def test_khong_doc_truong_actor_vong_lai_tu_khoa():
    """apidojo `includeSearchKeywords` vọng lại `searchKeyword` — đọc vào là dòng nào cũng khớp."""
    assert not A._khop_tu_khoa(_bai("outfit đi làm", searchKeyword="hapas",
                                    input="hapas"), Q)


def test_kim_ngan_phai_trung_nguyen_tu():
    assert not A._khop_tu_khoa(_bai("Thailand mai hai ngày"), ["AI"])
    assert A._khop_tu_khoa(_bai("Ứng dụng AI cho shop"), ["AI"])
    assert A._khop_tu_khoa(_bai("dùng #AI viết caption"), ["ai"])


def test_bo_dau_ca_chu_d():
    assert A._khop_tu_khoa(_bai("Đồng hồ nam đẹp"), ["dong ho"])
    assert A._khop_tu_khoa(_bai("dong ho nam"), ["đồng hồ"])
    assert A._norm("Đặng") == "dang"


def test_tu_khoa_nhieu_chu():
    assert A._khop_tu_khoa(_bai("xách túi đi chơi"), ["túi xách"]), "đủ mọi chữ là khớp"
    assert not A._khop_tu_khoa(_bai("túi da bò"), ["túi xách"])
    assert A._khop_tu_khoa(_bai("đồ handmade #matemade"), ["mate made"])
    assert A._khop_tu_khoa(_bai("Mate Made ra mẫu mới"), ["matemade"])


def test_tu_khoa_khong_co_chu_thi_khong_loai_bua():
    assert A._khop_tu_khoa(_bai("bất kỳ"), ["🔥"])


# ───────────────────────────── cổng thị trường VN ─────────────────────────────

def _ly_do(d, p="threads", boi_canh="", giu=False, khop_long=False, loai_tru=()):
    return A._ly_do_loai(d, p, Q, list(loai_tru), "VN", boi_canh, khop_long, giu)


def test_bai_tieng_viet_co_dau_duoc_giu():
    assert _ly_do(_bai("Mới mua túi Hapas xinh xỉu luôn", "Ngọc Trâm")) == ("", "")


def test_kenh_my_tieng_anh_bi_loai():
    k, ly_do = _ly_do(_bai("Hapas review: the best bags of the year — desc", "Bag Guy",
                           _quoc_gia="US"), p="youtube")
    assert k == "thi_truong" and "US" in ly_do


def test_hapas_thailand_bi_loai_ca_khi_chu_thai_lan_khi_tieng_anh():
    assert _ly_do(_bai("HAPAS กระเป๋าใหม่ล่าสุด", "HAPAS THAILAND"))[0] == "he_chu"
    assert _ly_do(_bai("HAPAS THAILAND new tote bag collection is available now",
                       "HAPAS THAILAND"))[0] == "thi_truong"
    assert _ly_do(_bai("HAPAS tote", "HAPAS TH", _quoc_gia="TH"), p="youtube")[0] == "thi_truong"


def test_ban_metal_bi_cong_vn_loai():
    k, _ = _ly_do(_bai("SHINAI – Hapas Ashen // Humanity's Last Breath — official video",
                       "SHINAI", _ngon_ngu="en"), p="youtube")
    assert k == "thi_truong"


def test_tieu_de_khong_dau_tu_kenh_vn_duoc_giu():
    d = _bai("HAPAS unboxing new collection fall winter 2026 — ", "HAPAS Official",
             _quoc_gia="VN")
    assert _ly_do(d, p="youtube") == ("", "")
    assert _ly_do(_bai("HAPAS unboxing new collection fall winter 2026", "x",
                       _ngon_ngu="vi"), p="youtube") == ("", "")


def test_tieng_viet_go_khong_dau_va_bai_chi_co_hashtag_duoc_giu():
    assert _ly_do(_bai("tui xach hapas dep qua troi luon a", "ngoc")) == ("", "")
    assert _ly_do(_bai("#hapas #tuixach #fyp #xuhuong #tiktokvn", "ngoc",
                       _nguon="clockworks (dự phòng)"), p="tiktok") == ("", "")


def test_cong_vn_chay_ca_khi_co_boi_canh():
    """Trước 01/10/2026 có `boi_canh` là tắt hẳn lọc thị trường — Mark luôn điền nó."""
    d = _bai("HAPAS THAILAND new tote bag collection is available now", "HAPAS THAILAND")
    assert _ly_do(d, boi_canh="HAPAS: túi xách, nước hoa")[0] == "thi_truong"
    assert _ly_do(_bai("HAPAS กระเป๋า", "HAPAS TH"), boi_canh="túi xách")[0] == "he_chu"


def test_giu_nuoc_ngoai_tat_cong():
    d = _bai("HAPAS THAILAND new tote bag collection is available now", "HAPAS THAILAND")
    assert _ly_do(d, giu=True) == ("", "")


def test_luat_cau_tieng_anh_chi_ap_cho_youtube():
    """Rà lại 01/10/2026: trên TikTok/Threads luật "≥5 từ Latin" loại nhầm caption tiếng
    Anh của chính brand; nhiễu tiếng Anh thật nằm ở YouTube."""
    d = _bai("Hapas haul best bags under fifty dollars", "k")
    assert _ly_do({**d, "_nguon": "apidojo"}, p="tiktok") == ("", "")
    assert _ly_do({**d, "_nguon": "clockworks (dự phòng)"}, p="tiktok") == ("", "")
    assert _ly_do(d, p="threads") == ("", "")
    assert _ly_do(d, p="youtube")[0] == "thi_truong"


def test_caption_tieng_anh_cua_kenh_brand_duoc_giu():
    d = {"kenh": "HAPAS Official", "hashtags": "", "username": "",
         "text": "HAPAS Flash Sale Today Only Best Bags Collection New Arrival",
         "_nguon": "clockworks (dự phòng)"}
    assert A._ly_do_loai(d, "tiktok", ["hapas"], [], "VN", "", False, False) == ("", "")
    # YouTube cũng giữ: từ khoá khớp ngay ở tên kênh (kênh của brand hoặc fan).
    assert _ly_do(dict(d), p="youtube") == ("", "")


@pytest.mark.parametrize("them", [
    {"hashtags": "hapas, tiktokvn"}, {"username": "hapas.vn.store"},
    {"text": "Hapas new bag collection only 299k today grab it"},
    {"text": "Hapas new bag collection price 1.290.000đ order now"},
    {"text": "Hapas new bag collection order now hotline +84901234567"},
    {"text": "Hapas new bag collection visit hapas.vn for more"},
    {"text": "Hapas pop up store opening in Saigon this weekend guys"},
    {"text": "Hapas pop up store opening in Ha Noi this weekend guys"},
])
def test_dau_hieu_vn_giu_bai_tieng_anh_ca_tren_youtube(them):
    d = {**_bai("Hapas new bag collection is finally here for everyone", "Bag Lover"), **them}
    assert _ly_do(d, p="youtube") == ("", ""), them


def test_youtube_khong_ro_nuoc_khong_ro_ngon_ngu_van_loai_ban_metal_va_luoi_ca():
    shinai = _bai("SHINAI – Hapas Ashen // Humanity's Last Breath — official music video",
                  "SHINAI")
    assert _ly_do(shinai, p="youtube")[0] == "thi_truong"
    taj = _bai("Taj Nets – aquaculture hapa fish net cage — ", "Taj Nets")
    assert _ly_do(taj, p="youtube")[0] == "tu_khoa"


def test_kenh_mang_ten_nuoc_khac_bi_loai_ke_ca_khop_tu_khoa_o_kenh():
    d = _bai("New tote bag collection is available now", "HAPAS THAILAND")
    assert _ly_do(d, p="threads")[0] == "thi_truong"
    # Kênh VN nhắc nước khác TRONG NỘI DUNG thì vẫn là bài VN.
    assert _ly_do(_bai("HAPAS now shipping to Thailand and Malaysia", "HAPAS Official"),
                  p="youtube") == ("", "")


# ───────────── từ khoá ngắn dính hashtag · từ khoá ngày/số · nhiều chữ ─────────────

def test_tu_khoa_ngan_khop_dau_hashtag_dinh():
    assert A._khop_tu_khoa(_bai("BST mới", hashtags="PNJSpring2026"), ["PNJ"])
    assert A._khop_tu_khoa(_bai("Mừng sinh nhật #PNJ30Nam"), ["PNJ"])
    assert not A._khop_tu_khoa(_bai("trang sức PNJSpring2026 mới"), ["PNJ"]), \
        "chữ dính trong NỘI DUNG (không phải hashtag) vẫn phải trùng nguyên từ"
    assert not A._khop_tu_khoa(_bai("Thailand mai hai ngày"), ["ai"])
    assert not A._khop_tu_khoa(_bai("đi hai ngày", hashtags="thailand, hai"), ["ai"])


@pytest.mark.parametrize("text", ["Quà 20/10 cho mẹ", "Sale 20-10 cực sốc",
                                  "ngày 20/10 này tặng gì", "Ưu đãi 20.10",
                                  "Mừng 20 tháng 10"])
def test_tu_khoa_ngay_khop_khi_dung_lien(text):
    assert A._khop_tu_khoa(_bai(text), ["20/10"])


@pytest.mark.parametrize("text", ["Sale có 20 mẫu giảm giá tới 10%",
                                  "10/20 khách hài lòng", "ra mắt năm 2010",
                                  "120/100 điểm", "20/105 người"])
def test_tu_khoa_ngay_khong_khop_so_roi_rac(text):
    assert not A._khop_tu_khoa(_bai(text), ["20/10"])


def test_tu_khoa_ngay_khac():
    assert A._khop_tu_khoa(_bai("Siêu sale 11.11"), ["11/11"])
    assert A._khop_tu_khoa(_bai("Quà 8/3 cho nàng"), ["8/3"])
    assert not A._khop_tu_khoa(_bai("Giảm 8% cho 3 sản phẩm"), ["8/3"])


def test_tu_khoa_nhieu_chu_can_du_moi_chu_khong_can_thu_tu():
    """Không có khop_long: 'túi xách nữ' cần ĐỦ cả ba chữ, ở đâu/thứ tự nào cũng được."""
    q = ["túi xách nữ"]
    assert not A._khop_tu_khoa(_bai("Túi xách da bò cao cấp"), q)
    assert not A._khop_tu_khoa(_bai("Thời trang nữ mùa thu"), q)
    assert A._khop_tu_khoa(_bai("Mẫu túi mới cho nữ, xách đi làm"), q)
    assert A._khop_tu_khoa(_bai("x", hashtags="tuixachnu"), q), "dạng viết liền"


def test_loai_tru_ap_cho_tiktok_va_threads():
    d = _bai("Hapas guitars custom build demo", "luthier", hashtags="hapasguitars")
    for p in ("tiktok", "threads"):
        k, ly_do = _ly_do(d, p=p, loai_tru=["guitars"])
        assert k == "loai_tru" and "guitars" in ly_do


def test_khop_long_giu_hanh_vi_cu():
    """Truy vấn khám phá ('viral'): TikTok/Threads không kiểm từ khoá; FB/IG/YT vẫn chuỗi con."""
    d = _bai("outfit đi làm siêu xinh", "Ngọc")
    assert _ly_do(d, p="tiktok", khop_long=True) == ("", "")
    assert _ly_do(d, p="facebook", khop_long=True)[0] == "tu_khoa"


# ───────────────────────────── _handle đầu-cuối ─────────────────────────────

NOW = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(hours=1)

FIXTURE = {
    "threads": [
        _bai("vote Tinh Hà ở đâu", "Mason Nguyễn"),
        _bai("Đt gập thì a k có…", "Bùi Trường Linh"),
        _bai("Thơm Da LAB x Folio's Men x Narciso", "Tu Anh Vu"),
        _bai("HAPAS THAILAND new tote bag collection is available now", "HAPAS THAILAND"),
        _bai("Mới mua túi Hapas xinh xỉu luôn mọi người ơi", "Ngọc Trâm"),
    ],
    "youtube": [
        _bai("SHINAI – Hapas Ashen // Humanity's Last Breath — official music video",
             "SHINAI", _ngon_ngu="en"),
        _bai("Taj Nets – aquaculture hapa fish net cage — ", "Taj Nets", _quoc_gia="IN"),
        _bai("HAPAS unboxing new collection fall winter 2026 — ", "HAPAS Official",
             _quoc_gia="VN"),
    ],
    "tiktok": [
        _bai("Review túi #HAPASNUOCHOAHAPAS", "Linh", _nguon="apidojo"),
        _bai("Hapas guitars custom build demo", "luthier", hashtags="hapasguitars",
             _nguon="apidojo"),
        _bai("outfit đi làm siêu xinh", "Mai", _nguon="apidojo"),
    ],
}


@pytest.fixture
def quet(monkeypatch):
    """Chạy `_handle` trên dữ liệu giả — không mạng, không Lark, không Apify, không model."""
    hoi = []
    for p, rows in FIXTURE.items():
        monkeypatch.setitem(A._FETCH, p, lambda *a, _r=rows: [(dict(d), NOW) for d in _r])
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    # Lark giả trọn vẹn: `ghi` nhìn tab dữ liệu như [(mã cũ, dòng, {})] — s1 bài, s2 Bị loại.
    gia = LarkGia(url="https://sheet")
    monkeypatch.setattr(A.lark, "call", gia.call)
    ghi = gia.ghi_cu({A.TAB_BAI_DANG: "s1", "Dữ liệu": "s1", A._TAB_BI_LOAI: "s2"}, ba=True)
    monkeypatch.setattr(A, "_grant", lambda tok, oid: True)
    monkeypatch.setattr(A.memory_store, "get_current_sender", lambda: "ou_test")
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A.chi_phi_tool, "ghi", lambda **k: {})

    monkeypatch.setattr(A, "_hoi_model", lambda nhac, ns: hoi.append(nhac) or "{}")

    def chay(**them):
        args = {"queries": ["hapas"], "platforms": ["threads", "youtube", "tiktok"],
                "date_from": f"{NOW - datetime.timedelta(days=2):%Y-%m-%d}",
                "date_to": f"{NOW + datetime.timedelta(hours=1):%Y-%m-%d}",
                "exclude": ["guitars"], "boi_canh": "HAPAS: túi xách, nước hoa", **them}
        return json.loads(A._handle(args))
    chay.gia = gia
    return chay, ghi, hoi


def test_dau_cuoi_dem_loai_tung_nen_tang(quet):
    chay, ghi, ai = quet
    kq = chay()
    pp = kq["per_platform"]
    assert pp["threads"]["loai_vi_khong_chua_tu_khoa"] == 3
    assert any("Mason Nguyễn" in x for x in pp["threads"]["vi_du_khong_chua_tu_khoa"])
    assert pp["threads"]["bi_loai_vi_ngoai_thi_truong"] == 1
    assert pp["youtube"]["loai_vi_khong_chua_tu_khoa"] == 1          # lưới cá "hapa"
    assert pp["youtube"]["bi_loai_vi_ngoai_thi_truong"] == 1         # ban metal
    assert pp["tiktok"]["loai_vi_khong_chua_tu_khoa"] == 1
    assert pp["tiktok"]["bi_loai_vi_tu_loai_tru"] == 1
    assert [pp[p]["in_range"] for p in ("threads", "youtube", "tiktok")] == [1, 1, 1]
    assert kq["trong_khoang_ngay"] == 11 and kq["tong_bi_loai"] == 8 and kq["in_range"] == 3
    assert kq["bi_loai_vi_ngoai_khoang_ngay"] == 0, "bị bộ lọc liên quan loại ≠ ngoài khoảng ngày"
    tom = kq["tom_tat_loai"]
    assert tom.startswith("Lọc theo luật 10 bài (AI bỏ qua: tắt (SOCIAL_AI_PHAN_XU=0)): "
                          "loại 7 (5 không nhắc từ khoá, 2 ngoài thị trường VN)"), tom
    assert "1 bài chứa từ loại trừ" in tom and "Bị loại" in tom
    assert ai == [], "AI tắt thì không gọi model"
    assert kq["thi_truong_quet"] == "VN" and "Đã quét thị trường VN" in kq["cau_thi_truong"]


def test_bai_bi_loai_ghi_tab_rieng_kem_ly_do(quet):
    chay, ghi, _ = quet
    kq = chay()
    assert [sid for sid, _, _ in ghi] == ["s1", "s2"]
    chinh, loai = ghi[0][1], ghi[1][1]
    assert len(chinh) == 1 + 3
    assert loai[0][-2:] == ["Lý do loại", A._COT_LOAI_VIDEO] and len(loai) == 1 + 8
    assert all(r[-2] for r in loai[1:]), "dòng bị loại nào cũng phải có lý do"
    assert any("Mason Nguyễn" == r[2] and "từ khoá" in r[-2] for r in loai[1:])
    assert kq["bi_loai_ghi_o"] == "tab '2. Bị loại'"
    assert chay.gia.tab_ten()[:3] == ["Tổng quan", "1. Bài đăng", "2. Bị loại"]


def test_them_tab_hong_thi_ghi_duoi_sheet_chinh(quet):
    chay, ghi, _ = quet
    gia = chay.gia
    goc = gia.call

    def call(method, path, query=None, body=None):
        if path.endswith("/sheets_batch_update") and any(
                "addSheet" in r and r["addSheet"]["properties"]["title"] != "Tổng quan"
                for r in body["requests"]):
            raise RuntimeError("lark 500")
        return goc(method, path, query, body)
    A.lark.call = call
    kq = chay()
    o = gia.o(gia.tab_ten()[1])
    assert o[0][0] == "Nền tảng" and len(gia.du_lieu(gia.tab_ten()[1])) == 1 + 3
    assert o[4] == [""] * len(o[0]), "một dòng trống rồi mới tới bảng ghi nối"
    assert o[5][0] == "— 2. Bị loại — (không thêm được tab riêng)"
    assert [x for x in o[6] if x][-2:] == ["Lý do loại", A._COT_LOAI_VIDEO], "ghi nối"
    assert len(o) == 6 + 1 + 8
    assert kq["bi_loai_ghi_o"].startswith("cuối tab '1. Bài đăng'")


def test_loi_tao_sheet_khong_lam_lo_token(quet, monkeypatch):
    chay, _, _ = quet
    monkeypatch.setenv("APIFY_TOKEN", "apify_api_BIMAT_SHEET")

    def hong(title):
        raise RuntimeError("lỗi ?token=apify_api_BIMAT_SHEET")
    monkeypatch.setattr(A, "_create_sheet", hong)
    kq = chay()
    assert "BIMAT_SHEET" not in json.dumps(kq, ensure_ascii=False)
    assert kq["success"] is False


def test_loc_ai_khong_chay_thi_khong_duoc_bao_da_loc(quet):
    chay, ghi, _ = quet
    kq = chay()
    assert kq["loc_bang_ai"] is False and kq["loc_ai_da_xet"] == 0
    assert kq["loc_ai_trang_thai"] == "bỏ qua: tắt (SOCIAL_AI_PHAN_XU=0)"
    chinh = ghi[0][1]
    assert chinh[0][-5:-2] == ["Thị trường", "Nhận định AI", "Sắc thái"]
    assert chinh[0][-1] == A._COT_LOAI_VIDEO
    assert all(r[-4] == "chưa qua AI (lọc theo luật)" for r in chinh[1:])
    assert all(r[-3] == "chưa phân loại" for r in chinh[1:]), "AI không chạy -> không nhãn"
    assert kq["thong_ke"]["da_phan_loai"] == 0 and kq["thong_ke_ghi_o"] is None


def test_moi_bai_deu_bi_loai_van_tao_sheet_de_kiem(quet, monkeypatch):
    monkeypatch.setitem(A._FETCH, "threads", lambda *a: [(dict(d), NOW) for d in FIXTURE["threads"][:3]])
    chay, ghi, _ = quet
    kq = chay(platforms=["threads"])
    assert kq["in_range"] == 0 and kq["sheet_url"] == "https://sheet"
    assert len(ghi[1][1]) == 1 + 3


def test_schema_noi_dung_su_that():
    mo_ta = A.SCHEMA["description"]
    assert "tom_tat_loai" in mo_ta and "loc_ai_trang_thai" in mo_ta
    props = A.SCHEMA["parameters"]["properties"]
    assert "KHÔNG có bước AI" in props["boi_canh"]["description"], "nói đúng: thiếu = luật"
    assert "khop_long" in props and "giu_nuoc_ngoai" in props and "chi_thi_truong_nay" in props
    assert "'TH'" in props["country"]["description"]
    assert "quét VN hay Thái?" in props["country"]["description"]
    assert "cau_thi_truong" in mo_ta and "cuu_lai_boi_ai" not in mo_ta


# ───────────────────────────── token Apify không được lộ ─────────────────────────────

BI_MAT = "apify_api_BIMAT1234567890"


def test_token_di_header_khong_nam_tren_url(monkeypatch):
    goi = []

    class R:
        status_code = 200

        def json(self):
            return []

    monkeypatch.setenv("APIFY_TOKEN", BI_MAT)
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    monkeypatch.setattr(A.requests, "post", lambda u, **k: goi.append((u, k)) or R())
    A._call("futurizerush~meta-threads-scraper", {}, 10, mem=1024)
    url, k = goi[0]
    assert BI_MAT not in url and "token" not in url
    assert k["headers"]["Authorization"] == f"Bearer {BI_MAT}"
    assert "maxTotalChargeUsd=1.0" in url and "memory=1024" in url


def test_loi_ket_noi_chua_url_khong_lam_lo_token(monkeypatch):
    def hong(url, **k):
        raise A.requests.ConnectionError(
            f"HTTPSConnectionPool(host='api.apify.com', port=443): Max retries exceeded "
            f"with url: /v2/acts/x/run-sync-get-dataset-items?token={BI_MAT}&maxItems=30")

    monkeypatch.setenv("APIFY_TOKEN", BI_MAT)
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    monkeypatch.setattr(A.requests, "post", hong)
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A.chi_phi_tool, "ghi", lambda **k: {})
    kq = A._handle({"queries": ["hapas"], "platforms": ["threads"],
                    "date_from": "2026-09-25", "date_to": "2026-10-01"})
    assert BI_MAT not in kq and "BIMAT" not in kq
    assert json.loads(kq)["per_platform"]["threads"]["status"] == "LOI"


def test_che_token_ca_dang_lo_tren_query():
    assert A._che_token(f"?token={BI_MAT}&x=1", "khac") == "?token=***&x=1"
    assert A._che_token(f"lỗi {BI_MAT}", BI_MAT) == "lỗi ***"


# ---- review 01/10/2026 (lần 2): dấu hiệu VN quá rộng ---------------------------------
def test_k_dem_tuong_tac_khong_phai_gia_viet():
    """'100k views' là cách viết chung toàn cầu, không phải giá '299k' — không được cứu
    video metal nước ngoài khỏi cổng thị trường."""
    shinai = _bai("SHINAI – Hapas Ashen // Humanity's Last Breath — 100k views milestone",
                  "SHINAI", _ngon_ngu="en")
    assert _ly_do(shinai, p="youtube")[0] == "thi_truong"
    for s in ("best bags 10k views today", "amazing song 100k likes subscribe",
              "thanks 50k followers", "20k lượt xem rồi"):
        assert not A._co_dau_hieu_vn(_bai(s)), s
    assert A._co_dau_hieu_vn(_bai("HAPAS tote only 299k today grab it"))


def test_so_dien_thoai_chi_tinh_khi_co_chu_goi():
    assert not A._co_dau_hieu_vn(_bai("Order tracking id 0387654321 your package has shipped"))
    for s in ("sđt 0387654321", "Hotline: 0912345678", "zalo 0868123456"):
        assert A._co_dau_hieu_vn(_bai(s)), s


def test_shop_vn_dat_ten_theo_nuoc_nguon_hang_khong_bi_loai():
    """'Korea Cosmetics Shop', 'Thailand Closet' là shop VN; tên nước chỉ tính khi đi
    cùng từ khoá trong tên kênh ('HAPAS THAILAND')."""
    for kenh in ("Korea Cosmetics Shop", "Thailand Closet"):
        assert _ly_do(_bai("Hapas new design restock", kenh), p="tiktok") == ("", ""), kenh
    assert _ly_do(_bai("New tote bag collection is available now", "HAPAS THAILAND"),
                  p="threads")[0] == "thi_truong"
    assert _ly_do(_bai("New tote", "", username="hapasthailand"), p="threads")[0] == "thi_truong"