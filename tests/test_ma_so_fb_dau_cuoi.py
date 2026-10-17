"""Luồng `ma_so_fb` ĐẦU-CUỐI (17/10/2026, gộp feat/ig-fb-duong-moi + fix/fb-khu-trung).

Item THÔ của actor → bộ chuẩn hoá (thedoor theo dõi trang, mina đường 2, scrapeforge) → dòng ghi
kho (`theo_doi.ghep_nguon` → `chon_bai`) → `lang_nghe_db.ghi_bai` khớp bản trùng và lưu
`bai.ma_so_fb`. Kịch bản thật: kho đã có bài fanpage dạng pfbid do actor cũ ghi TRƯỚC khi có cột
(`apify~facebook-posts-scraper`, link `/hapasglobal/posts/pfbid…`); từ 17/10 trang đi thedoor, link
`/<id trang>/posts/<id số>` — khoá mới khác hẳn, chỉ khớp được theo chủ bài + phút + nội dung.
Kho giả: `test_khu_trung_fb.KhoGia` (đúng các câu SQL của `ghi_bai` / `khoa_fb_trung`)."""
from __future__ import annotations

import copy
import datetime
import json
import pathlib

import pytest
from test_khu_trung_fb import KhoGia

import account_tool
import apify_tool as A
import lang_nghe_db as K
import theo_doi as T
import theo_doi_api as TDA

_VN = datetime.timezone(datetime.timedelta(hours=7))
TRANG = "https://www.facebook.com/hapasglobal"
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"]}
NGUON = {6: {"id": 6, "nen_tang": "facebook", "dinh_danh": TRANG, "loai": "kenh_nha",
             "so_bai_moi_lan": 20}}


def _thedoor() -> list[dict]:
    p = pathlib.Path(__file__).with_name("mau_fb_thedoor.json")
    return json.loads(p.read_text(encoding="utf-8"))["items"]


def _luc(it: dict, giay: int | None = None) -> datetime.datetime:
    t = datetime.datetime.fromtimestamp(it["created"]["timestamp"], datetime.timezone.utc)
    return t if giay is None else t.replace(second=giay)


def _cu(it: dict, giay: int = 55) -> dict:
    """CÙNG bài `it` (thedoor) như actor CŨ trả: link pfbid theo tên trang, giờ cùng phút (giây
    khác), không có id số dùng được (bài ghi trước 17/10 không lưu id)."""
    return {"pageName": "hapasglobal", "inputUrl": TRANG, "facebookUrl": TRANG,
            "url": f"{TRANG}/posts/pfbid0Cu{it['post']['id'][-6:]}x",
            "time": _luc(it, giay).isoformat(), "likes": 3, "comments": 1, "shares": 0,
            "text": it["post"]["text"]}


def _dong(ket: dict, bay_gio: datetime.datetime) -> list[dict]:
    """Kết quả bộ đọc (dạng `account_tool._doc_facebook`) → dòng ghi kho, đúng đường lượt
    `/theodoi` (`ghep_nguon` → `chon_bai`)."""
    theo, _ = T.ghep_nguon("facebook", ket, list(NGUON.values()))
    rows, _ = T.chon_bai(DU_AN, theo, NGUON, 0.0, bay_gio)
    return rows


@pytest.fixture
def kho(monkeypatch):
    """Kho TRƯỚC khi chạy schema.sql (chưa có cột `bai.ma_so_fb`); AI tắt (kênh nhà giữ hết)."""
    k = KhoGia(co_cot=False)
    monkeypatch.setattr(K, "ket_noi", lambda: k)
    monkeypatch.setattr(K, "_CO_MA_SO_FB", [])
    monkeypatch.setattr(A, "_phan_xu_ai", lambda *a, **kw: (
        {}, {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "tat"}))

    def chay_schema():
        k.co_cot = True
        monkeypatch.setattr(K, "_CO_MA_SO_FB", [])
    k.chay_schema = chay_schema
    return k


def test_bai_pfbid_cu_thedoor_tra_lai_posts_so_khop_khoa_cu(kho):
    it = _thedoor()[0]
    bay_gio = _luc(it).astimezone(_VN) + datetime.timedelta(days=1)
    # 1. Kho trước 17/10: actor cũ ghi bài với khoá pfbid, chưa có cột id số.
    cu = _dong(account_tool._doc_facebook([_cu(it)]), bay_gio)
    assert K.ghi_bai("hapas", 1, "theo_doi", cu) == (1, 0)
    (khoa_cu,) = kho.bai
    assert khoa_cu.startswith("facebook:pfbid") and kho.bai[khoa_cu].get("ma_so_fb") is None
    # 2. Chạy schema.sql; lượt sau trang đi thedoor: khoá mới theo id số, `ma_so_fb` điền sẵn.
    kho.chay_schema()
    moi = _dong(TDA.doc_fb_trang([it], [TRANG]), bay_gio)
    (r,) = moi
    so = it["post"]["id"]
    assert r["khoa"] == f"facebook:{so}" != khoa_cu and r["ma_so_fb"] == so
    assert r["link"] == it["post"]["url"] and "/posts/" in r["link"]
    assert r["tai_khoan"] == "hapasglobal", "tên trang như actor cũ, không phải tên hiển thị"
    assert K.ghi_bai("hapas", 2, "theo_doi", moi) == (0, 1)
    assert list(kho.bai) == [khoa_cu], "KHÔNG sinh bài mới: dùng lại khoá pfbid cũ"
    assert kho.bai[khoa_cu]["ma_so_fb"] == so, "dòng cũ được điền id số"
    assert kho.bai[khoa_cu]["thich"] == it["engagement"]["reactions"], "số liệu lấy bản mới"
    assert kho.so == [khoa_cu, khoa_cu], "số theo ngày ghi vào khoá cũ"
    # 3. Lượt sau nữa: khớp thẳng theo id số, kể cả khi chủ trang sửa chữ (phút/nội dung lệch).
    sua = copy.deepcopy(it)
    sua["post"]["text"] = "Bài đã sửa: CÙNG HAPAS - LÀM MỌI ĐIỀU VÌ YÊU THƯƠNG"
    sua["created"]["timestamp"] += 3600
    assert K.ghi_bai("hapas", 3, "theo_doi",
                     _dong(TDA.doc_fb_trang([sua], [TRANG]), bay_gio)) == (0, 1)
    assert list(kho.bai) == [khoa_cu]


def test_hai_id_so_khac_nhau_cung_chu_phut_chu_khong_gop(kho):
    """Trang đăng hai video cùng chú thích cùng phút: hai id số → hai bài."""
    kho.chay_schema()
    a = _thedoor()[0]
    b = copy.deepcopy(a)
    b["post"]["id"] = "1825684048899999"
    b["post"]["url"] = f"https://www.facebook.com/100066634543565/posts/{b['post']['id']}"
    b["created"]["timestamp"] += 20                       # cùng phút
    bay_gio = _luc(a).astimezone(_VN) + datetime.timedelta(days=1)
    assert K.ghi_bai("hapas", 1, "theo_doi", _dong(TDA.doc_fb_trang([a], [TRANG]), bay_gio)) \
        == (1, 0)
    assert K.ghi_bai("hapas", 2, "theo_doi", _dong(TDA.doc_fb_trang([b], [TRANG]), bay_gio)) \
        == (1, 0)
    assert {k: r["ma_so_fb"] for k, r in kho.bai.items()} == {
        f"facebook:{a['post']['id']}": a["post"]["id"],
        f"facebook:{b['post']['id']}": b["post"]["id"]}
    # Bản pfbid cũ ĐÃ có id (actor cũ trả `postId`) khác id thedoor: cũng không gộp.
    kho.bai, kho.so = {}, []
    cu = {**_cu(a), "postId": "1825684040000001"}
    dong_cu = _dong(account_tool._doc_facebook([cu]), bay_gio)
    assert dong_cu[0]["ma_so_fb"] == "1825684040000001"
    K.ghi_bai("hapas", 1, "theo_doi", dong_cu)
    assert K.ghi_bai("hapas", 2, "theo_doi", _dong(TDA.doc_fb_trang([a], [TRANG]), bay_gio)) \
        == (1, 0)
    assert len(kho.bai) == 2


def test_tim_tu_khoa_mina_tra_bai_cu_di_duong_da_co(kho):
    """Đường 2 Facebook (mina) trả lại bài fanpage đã có dạng pfbid: bước tách trước AI
    (`theo_doi._khoa_fb_cu` → `lang_nghe_db.khoa_fb_trung`) trỏ về khoá cũ."""
    it = _thedoor()[0]
    bay_gio = _luc(it).astimezone(_VN) + datetime.timedelta(days=1)
    K.ghi_bai("hapas", 1, "theo_doi", _dong(account_tool._doc_facebook([_cu(it)]), bay_gio))
    (khoa_cu,) = kho.bai
    kho.chay_schema()
    mina = {"post_id": it["post"]["id"], "id": it["post"]["id"], "type": "video",
            "url": f"{TRANG}/posts/pfbid0MinaKhac", "owner_name": "HAPAS",
            "post_title": it["post"]["text"],
            "statistics": {"reaction_count": {"count": 20}, "comment_count": 48},
            "video_details": {"publish_timestamp": (it["created"]["timestamp"] + 7) * 1000,
                              "owner": {"owner_as_page": {"id": "100066634543565",
                                                          "name": "HAPAS",
                                                          "profile_url": TRANG}}}}
    ((d, dt),) = A._chuan_facebook_mina([mina], "túi hapas")
    assert d["ma_so_fb"] == it["post"]["id"] and d["username"] == "hapasglobal"
    d["platform"] = "facebook"

    def khoa_hit(x):
        return T._khoa_bai("facebook", x["link"], {"id": (x.get("__goc") or {}).get("id")})
    assert T._khoa_fb_cu("hapas", [(d, dt)], khoa_hit) == {khoa_hit(d): khoa_cu}
    # Dòng ghi kho của bước giữ (`_giu_tu_khoa`) mang id số → lần sau khớp thẳng theo id.
    assert T._cot_fb(d) == {"ma_so_fb": it["post"]["id"]}


def test_thedoor_ma_so_tu_link_khi_thieu_id_va_ten_trang_du_phong():
    it = copy.deepcopy(_thedoor()[0])
    it["post"].pop("id")
    ket = TDA.doc_fb_trang([it], [TRANG])
    ((d, _),) = T._dong_tu_tai_khoan("facebook", next(iter(ket.values())))
    assert d["ma_so_fb"] == "1825684048882067", "id số bóc từ link /<id trang>/posts/<id bài>"
    assert TDA._ten_trang("https://www.facebook.com/100066634543565",
                          "https://www.facebook.com/profile.php?id=1", TRANG) == "hapasglobal"
    assert TDA._ten_trang("https://www.facebook.com/profile.php?id=1") == ""
