"""Lắng nghe web (`nguon_web.py`, bản mẫu 16/10/2026). Mọi HTML/kết quả tìm ở đây là MẪU TỰ
VIẾT (không chép bài báo thật); mạng bị chặn bởi conftest — actor, tải trang, robots đều giả."""
from __future__ import annotations

import datetime
import json

import pytest

import nguon_web as W

VN = datetime.timezone(datetime.timedelta(hours=7))
BAY_GIO = datetime.datetime(2026, 10, 16, 10, 0, tzinfo=VN)
DU_AN = {"ma": "hapas", "ten": "HAPAS", "thi_truong": "VN",
         "tu_khoa": ["hapas", "túi hapas", "ví hapas", "quà tặng hapas", "yêu từ điều nhỏ nhất",
                     "hapas.vn"],
         "tu_loai_tru": ["guitar"]}


def _bai(tieu_de="Tiêu đề", than="", ngay="2026-10-10T09:00:00+07:00", lien_quan="",
         ld_them=None, site="Báo Mẫu"):
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": tieu_de,
          "datePublished": ngay, "author": {"@type": "Person", "name": "Phóng viên A"},
          **(ld_them or {})}
    return f"""<html><head><title>{tieu_de} - {site}</title>
<meta property="og:site_name" content="{site}">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script></head>
<body><nav>Trang chủ | Thời trang | HAPAS khuyến mãi</nav>
<article><h1>{tieu_de}</h1><div class="detail-content">{than}</div></article>
<div class="box-related"><a href="/x">{lien_quan}</a></div>
<footer>Liên hệ toà soạn</footer></body></html>"""


# ───────── URL + phân loại ─────────
def test_url_chuan_gop_bien_the():
    a = W.url_chuan("https://m.cafef.vn/bai-mau-1.chn?utm_source=fb&srsltid=abc#top")
    assert a == W.url_chuan("http://cafef.vn/bai-mau-1.chn/") == "https://cafef.vn/bai-mau-1.chn"
    assert W.url_chuan("https://voz.vn/t/chu-de.1/?page=2") == "https://voz.vn/t/chu-de.1?page=2"
    assert W.url_chuan("https://báo.vn/amp/") == W.url_chuan("https://báo.vn/")
    assert W.url_chuan("ftp://x.vn/a") == ""
    assert W.khoa_web("https://www.kenh14.vn/a.chn") == W.khoa_web("https://kenh14.vn/a.chn")
    assert W.khoa_web("https://kenh14.vn/a.chn").startswith("web:")


def test_khoa_trung_voi_theo_doi():
    """`theo_doi._giu_tu_khoa` dựng khoá bằng `_khoa_bai(platform, link, {id: __goc.id})` —
    phải ra đúng khoá `nguon_web` dự tính, kẻo một bài thành hai dòng."""
    import theo_doi
    link = "https://cafef.vn/bai-mau-1.chn"
    d, _ = W.thanh_hit({"link": link, "tieu_de": "x", "trich": "hapas"}, None,
                       {"vi_tri": []}, ["hapas"], BAY_GIO)
    assert theo_doi._khoa_bai(d["platform"], d["link"], {"id": d["__goc"]["id"]}) \
        == W.khoa_web(link)


def test_kieu_trang():
    assert W.kieu_trang("https://m.kenh14.vn/a.chn") == "bao"
    assert W.kieu_trang("https://www.brandsvietnam.com/congdong/topic/a") == "bao"
    assert W.kieu_trang("https://voz.vn/t/a.1/") == "dien_dan"
    assert W.kieu_trang("https://diendan.vd.vn/threads/a.9/") == "dien_dan"
    assert W.kieu_trang("https://vd.vn/a", "DiscussionForumPosting") == "dien_dan"
    assert W.kieu_trang("https://vn.linkedin.com/posts/a") == "mxh_khac"
    assert W.kieu_trang("https://blog.vd.vn/a", "BlogPosting") == "blog"
    assert W.kieu_trang("https://vd.vn/a") == "khac"


def test_mien_nha_tu_tu_khoa_va_cau_hinh():
    assert W.mien_nha(DU_AN) == ["hapas.vn"]
    assert W.mien_nha({**DU_AN, "cau_hinh": {"web": {"mien_nha": ["https://www.hapas.co/"]}}}) \
        == ["hapas.co", "hapas.vn"]


# ───────── câu tìm + chi phí ─────────
def test_rut_gon_tu_khoa():
    assert W.rut_gon_tu_khoa(DU_AN["tu_khoa"]) == ["hapas", "yêu từ điều nhỏ nhất"]
    assert W.rut_gon_tu_khoa(["Túi Hapas", "túi hapas", " "]) == ["Túi Hapas"]


def test_cau_truy_van_gon_va_trong_tran_32_tu():
    q = W.cau_truy_van(DU_AN)
    assert len(q) == 1
    assert q[0].startswith('(hapas OR "yêu từ điều nhỏ nhất")')
    for x in ("-site:facebook.com", "-site:tiktok.com", "-site:hapas.vn", "-guitar"):
        assert x in q[0]
    assert len(q[0].split()) <= W.TOI_DA_TU_GOOGLE
    nhieu = {"ten": "X", "tu_khoa": [f"thuong hieu {i} dai qua" for i in range(30)]}
    cac = W.cau_truy_van(nhieu)
    assert len(cac) == W.TOI_DA_TRUY_VAN
    assert all(len(c.split()) <= W.TOI_DA_TU_GOOGLE for c in cac)


def test_payload_va_uoc_tinh():
    p = W.payload_tim(["hapas"], datetime.date(2026, 10, 9), datetime.date(2026, 10, 16), 2)
    assert p["tbs"] == "cdr:1,cd_min:10/9/2026,cd_max:10/16/2026"
    assert (p["limit"], p["country"], p["hl"]) == ("20", "VN", "vi")
    assert W.payload_tim(["a"], BAY_GIO.date(), BAY_GIO.date(), 7)["limit"] == "100"
    assert W.uoc_luot(2, 2) == round(2 * 2 * W.GIA_TRANG * W.HE_SO_UOC, 4)
    assert W.uoc_luot(1, 2, so_boc=2) == round((2 * W.GIA_TRANG + 2 * W.GIA_BOC) * 1.3, 4)
    assert W.uoc_luot(0) == 0.0
    assert W.tran_luot(0.002) == 0.1
    assert W.tran_luot(0.2, con_usd=0.25) == 0.25
    assert W.tran_luot(0.002, con_usd=0.05) == 0.0


# ───────── ngày ─────────
@pytest.mark.parametrize("s, mong", [
    ("4 thg 5, 2026", datetime.date(2026, 5, 4)),
    ("16 thg 12, 2025", datetime.date(2025, 12, 16)),
    ("5 ngày trước", datetime.date(2026, 10, 11)),
    ("14 giờ trước", datetime.date(2026, 10, 15)),
    ("2 tuần trước", datetime.date(2026, 10, 2)),
    ("Oct 5, 2026", datetime.date(2026, 10, 5)),
    ("3 days ago", datetime.date(2026, 10, 13)),
    ("2026-10-14T10:42:38.000Z", datetime.date(2026, 10, 14)),
])
def test_ngay_serp(s, mong):
    assert W.ngay_serp(s, BAY_GIO).astimezone(VN).date() == mong


def test_ngay_iso_cac_dang():
    assert W.ngay_iso("2026-07-02T09:12:45+0700").utcoffset() == datetime.timedelta(hours=7)
    assert W.ngay_iso("2025-12-17T07:09:25.000Z").utcoffset() == datetime.timedelta(0)
    assert W.ngay_iso("2026-08-25T13:30:00").tzinfo == VN        # không múi giờ: giờ VN
    assert W.ngay_iso("2026-02-30") is None
    assert W.ngay_iso("hôm qua") is None and W.ngay_serp("", BAY_GIO) is None


def test_doc_serp_ba_dang():
    items = [
        {"search_term": "hapas", "results": [
            {"position": 1, "link": "https://a.vn/1", "title": "A", "snippet": "s", "date": "5 ngày trước"},
            {"position": 2, "link": "javascript:void(0)", "title": "x"}]},
        {"rowType": "newsResult", "searchTerm": "hapas", "url": "https://b.vn/2", "title": "B",
         "description": "d", "date": "2026-10-14T10:42:38.000Z"},
        {"organicResults": [{"url": "https://c.vn/3", "title": "C", "description": "e"}]},
        "rác",
    ]
    r = W.doc_serp(items, BAY_GIO)
    assert [x["link"] for x in r] == ["https://a.vn/1", "https://b.vn/2", "https://c.vn/3"]
    assert r[0]["ngay"].date() == datetime.date(2026, 10, 11) and r[2]["ngay"] is None
    assert r[1]["truy_van"] == "hapas"


# ───────── bóc HTML ─────────
def test_boc_bai_bao_bo_tin_lien_quan_va_menu():
    h = _bai("Xu hướng túi mùa thu", "<p>Đoạn một nói về túi xách công sở &amp; màu nâu.</p>"
             "<p>Đoạn hai, tiếp tục bàn về chất liệu da thật cho dân văn phòng.</p>" * 3,
             lien_quan="Ví HAPAS giảm giá sốc")
    t = W.boc_trang(h, "https://bao.vd.vn/a.htm")
    assert "hapas" not in t["noi_dung"].lower()           # chữ brand chỉ ở menu + tin liên quan
    assert "túi xách công sở & màu nâu" in t["noi_dung"]
    assert t["dang_luc"] == datetime.datetime(2026, 10, 10, 9, 0, tzinfo=VN)
    assert (t["tac_gia"], t["ten_trang"], t["kieu_ld"]) == ("Phóng viên A", "Báo Mẫu", "NewsArticle")


def test_boc_dien_dan_xenforo():
    ld = {"@context": "https://schema.org", "@type": "DiscussionForumPosting",
          "headline": "Hỏi về túi", "datePublished": "2025-12-08T07:40:42+00:00",
          "dateModified": "2026-10-12T08:00:00+07:00",
          "interactionStatistic": {"@type": "InteractionCounter",
                                   "interactionType": "https://schema.org/ReplyAction",
                                   "userInteractionCount": 12}}
    h = (f'<html><head><script type="application/ld+json">{json.dumps(ld)}</script>'
         '<link rel="canonical" href="https://dd.vd.vn/threads/hoi-ve-tui.9/"></head><body>'
         '<div class="message-body"><div class="bbWrapper">Túi hapas<br>dùng bền không mọi người?'
         '</div></div><div class="message-body"><div class="bbWrapper">Mình dùng 2 năm vẫn ổn, '
         'da mềm, khoá chắc chắn, đáng tiền.</div></div></body></html>')
    t = W.boc_trang(h, "https://dd.vd.vn/threads/hoi-ve-tui.9/?utm_source=x")
    assert t["so_binh_luan"] == 12 and t["kieu_ld"] == "DiscussionForumPosting"
    assert "Túi hapas" in t["noi_dung"] and "da mềm" in t["noi_dung"]
    assert t["canonical"] == "https://dd.vd.vn/threads/hoi-ve-tui.9/"
    assert t["sua_luc"].date() == datetime.date(2026, 10, 12)


def test_boc_html_hong_khong_vo():
    t = W.boc_trang("<html><div class='content'><p>chưa đóng thẻ <b>hapas", "https://x.vn/a")
    assert "hapas" in t["noi_dung"] and t["dang_luc"] is None
    assert W.boc_trang("", "https://x.vn")["noi_dung"] == ""
    bad = '<script type="application/ld+json">{hỏng</script><p>văn bản</p>'
    assert W.boc_trang(bad, "https://x.vn")["noi_dung"] == "văn bản"


def test_canonical_khac_mien_bi_bo():
    h = '<link rel="canonical" href="https://khac.vn/a"><p>x</p>'
    assert W.boc_trang(h, "https://x.vn/a")["canonical"] == ""


# ───────── nhắc brand ─────────
def test_vi_tri_nhac_co_dau_va_khong_khop_bua():
    s = "Mẫu TÚI HAPAS mới; hapa sushi khác; Yêu từ điều nhỏ nhất!"
    vt = W.vi_tri_nhac(s, ["hapas", "yêu từ điều nhỏ nhất"])
    assert [s[a:b] for a, b in vt] == ["HAPAS", "Yêu từ điều nhỏ nhất"]
    assert W.vi_tri_nhac("Đồng hồ AI", ["ai"]) == [(8, 10)]
    assert W.vi_tri_nhac("chai nước", ["ai"]) == []


def test_doan_trich_khong_chong():
    s = "a" * 300 + "hapas" + "b" * 300 + "hapas" + "c" * 10
    d = W.doan_trich(s, W.vi_tri_nhac(s, ["hapas"]), truoc=10, sau=20)
    assert len(d) == 2 and all("hapas" in x for x in d) and d[0].startswith("…")


def test_danh_gia_nhac_va_pr():
    t = {"tieu_de": "Top 10 túi đẹp", "noi_dung": "… số 6 là túi Hapas Solea. ẢNH: HAPAS",
         "lien_ket_chinh": []}
    n = W.danh_gia_nhac(t, ["hapas"], ["hapas.vn"])
    assert (n["muc_nhac"], n["la_pr"], n["so_lan_nhac"]) == ("thoang", True, 2)
    t2 = {"tieu_de": "HAPAS ra mắt BST", "noi_dung": "x", "lien_ket_chinh": ["https://hapas.vn/sp"]}
    n2 = W.danh_gia_nhac(t2, ["hapas"], ["hapas.vn"])
    assert (n2["muc_nhac"], n2["la_pr"], n2["link_nha"]) == ("tieu_de", True, 1)
    t3 = {"tieu_de": "Bàn về túi", "noi_dung": "hapas hapas hapas", "lien_ket_chinh": []}
    assert W.danh_gia_nhac(t3, ["hapas"], [])["muc_nhac"] == "chinh"


# ───────── an toàn + robots ─────────
def test_url_an_toan():
    pub = lambda h: ["93.184.216.34"]
    assert W.url_an_toan("https://bao.vd.vn/a", pub)
    for u in ("http://127.0.0.1/a", "http://10.0.0.5/", "http://169.254.169.254/latest",
              "http://[::1]/", "file:///etc/passwd", "https://bao.vd.vn:8080/a",
              "https://u:p@bao.vd.vn/"):
        assert not W.url_an_toan(u, pub), u
    assert not W.url_an_toan("https://noibo.vd.vn/", lambda h: ["192.168.1.2"])
    assert not W.url_an_toan("https://khong-co.vd.vn/", lambda h: (_ for _ in ()).throw(OSError()))


def test_robots():
    bang = {"https://a.vn/robots.txt": (200, "User-agent: *\nDisallow: /tim-kiem\n", ""),
            "https://b.vn/robots.txt": (404, "", ""), "https://c.vn/robots.txt": (503, "", ""),
            "https://d.vn/robots.txt": (200, "User-agent: HapasListeningBot\nDisallow: /\n", "")}
    goi = []

    def tai(u):
        goi.append(u)
        return bang[u]
    r = W.Robots(tai)
    assert r.cho_phep("https://a.vn/bai.htm") and not r.cho_phep("https://a.vn/tim-kiem?q=1")
    assert r.cho_phep("https://b.vn/x") and not r.cho_phep("https://c.vn/x")
    assert not r.cho_phep("https://d.vn/x")
    assert goi.count("https://a.vn/robots.txt") == 1               # nhớ trong lượt


# ───────── một lượt ─────────
def _serp(*ds):
    return [{"search_term": "q", "results": [
        {"position": i, "link": l, "title": t, "snippet": s, "date": n}
        for i, (l, t, s, n) in enumerate(ds, 1)]}]


class _Gia:
    def __init__(self, trang: dict):
        self.trang, self.goi, self.ngu = trang, [], []
        self.t = 0.0

    def tai(self, u):
        self.goi.append(u)
        if u.endswith("/robots.txt"):
            return 404, "", u
        x = self.trang.get(u)
        return (200, x, u) if x else (403, "", u)

    def dong_ho(self):
        self.t += 0.1
        return self.t

    def ngu_(self, s):
        self.ngu.append(s)
        self.t += s


def _chay(items, trang, **kw):
    g = _Gia(trang)
    hits, tk = W.thu_thap(DU_AN, tu=datetime.date(2026, 10, 1), den=datetime.date(2026, 10, 16),
                          chay_actor=lambda p, lim, han, tran: (items, {"run_id": "r1"}),
                          tai=g.tai, ngu=g.ngu_, bay_gio=BAY_GIO, tu_dong_ho=g.dong_ho,
                          han=1e9, **kw)
    return hits, tk, g


def test_thu_thap_loc_dung_tung_buoc():
    than_tot = "<p>" + "Bài viết dài về thương hiệu túi Việt. " * 5 + "Túi HAPAS bán chạy.</p>"
    items = _serp(
        ("https://www.facebook.com/hapas/posts/1", "fb", "hapas", "1 ngày trước"),
        ("https://hapas.vn/bst", "nhà", "hapas", "1 ngày trước"),
        ("https://shopee.vn/hapas", "sàn", "hapas", "1 ngày trước"),
        ("https://bao.vd.vn/a.htm?utm_source=g", "A", "", "2 ngày trước"),
        ("https://m.bao.vd.vn/a.htm", "A trùng", "", "2 ngày trước"),
        ("https://bao.vd.vn/cu.htm", "Cũ", "", "1 ngày trước"),
        ("https://bao.vd.vn/khong.htm", "Không", "", "1 ngày trước"),
        ("https://dan.vd.vn/guitar.htm", "Đàn", "", "1 ngày trước"),
        ("https://chan.vd.vn/a", "Hapas được khen", "Khách khen túi hapas bền", "3 ngày trước"),
        ("https://bao.vd.vn/tai-lieu.pdf", "pdf", "hapas", "1 ngày trước"),
    )
    trang = {
        "https://bao.vd.vn/a.htm?utm_source=g": _bai("Túi Việt lên ngôi", than_tot),
        "https://bao.vd.vn/cu.htm": _bai("Túi HAPAS", than_tot, ngay="2026-08-01T09:00:00+07:00"),
        "https://bao.vd.vn/khong.htm": _bai("Túi khác", "<p>" + "Không nhắc brand nào. " * 20 + "</p>",
                                            lien_quan="HAPAS sale"),
        "https://dan.vd.vn/guitar.htm": _bai("Hapas guitar", "<p>" + "đàn guitar hapas 7 dây. " * 10 + "</p>"),
    }
    hits, tk, g = _chay(items, trang)
    ph = tk["pheu"]
    assert (ph["mxh"], ph["nha"], ph["tmdt"], ph["tep"], ph["trung"]) == (1, 1, 1, 1, 1)
    assert (ph["qua_cu"], ph["khong_nhac"], ph["loai_tru"], ph["tai_loi"]) == (1, 1, 1, 1)
    assert ph["giu"] == len(hits) == 2 and tk["run_id"] == "r1" and tk["trang_thai"] == "xong"
    a, b = hits
    assert a[0]["link"] == "https://bao.vd.vn/a.htm?utm_source=g" and a[0]["platform"] == "web"
    assert a[0]["username"] == "bao.vd.vn" and a[0]["kenh"] == "Báo Mẫu"
    assert a[0]["text"].startswith("Túi Việt lên ngôi | ") and "HAPAS" in a[0]["text"][:200]
    assert a[0]["_web"]["muc_nhac"] == "thoang" and not a[0]["_web"]["chi_trich"]
    assert b[0]["_web"]["chi_trich"] and "hapas bền" in b[0]["text"]       # 403: đoạn trích Google
    assert b[1].date() == datetime.date(2026, 10, 13)
    assert not any("facebook" in u or "hapas.vn" in u or "shopee" in u for u in g.goi)
    assert g.ngu and all(0 < s <= W.NGHI_MOI_MIEN for s in g.ngu)   # cùng miền: có nghỉ


def test_thu_thap_dong_ghi_kho_du_cot():
    import lang_nghe_db as K
    items = _serp(("https://bao.vd.vn/a.htm", "A", "", "1 ngày trước"))
    than = "<p>" + "Nội dung. " * 30 + "Túi HAPAS.</p>"
    hits, _, _ = _chay(items, {"https://bao.vd.vn/a.htm": _bai("HAPAS mở cửa hàng", than)})
    d, dt = hits[0]
    r = W.thanh_dong(d, dt, sac_thai="Tích cực")
    assert set(K._COT_BAI) - {"ma_noi_dung"} <= set(r)
    assert r["khoa"] == W.khoa_web(d["link"]) and r["nen_tang"] == "web"
    assert (r["xem"], r["thich"], r["chia_se"]) == (None, None, None)
    assert r["kieu_trang"] == "bao" and r["muc_nhac"] == "tieu_de" and len(r["noi_dung"]) <= 1000


def test_thu_thap_het_gio_dung_trich_khong_tai():
    items = _serp(("https://bao.vd.vn/a.htm", "HAPAS ra mắt", "túi hapas mới", "1 ngày trước"))
    g = _Gia({})
    hits, _tk = W.thu_thap(DU_AN, tu=datetime.date(2026, 10, 1), den=datetime.date(2026, 10, 16),
                           chay_actor=lambda *a: (items, {}), tai=g.tai, bay_gio=BAY_GIO,
                           tu_dong_ho=lambda: 100.0, han=105.0)
    assert len(hits) == 1 and hits[0][0]["_web"]["chi_trich"] and g.goi == []


def test_thu_thap_het_ngan_sach_va_loi_actor():
    hits, tk = W.thu_thap(DU_AN, con_usd=0.05, chay_actor=lambda *a: pytest.fail("không chạy"),
                          bay_gio=BAY_GIO)
    assert hits == [] and tk["trang_thai"].startswith("bo_qua")

    def hong(*a):
        raise RuntimeError("HTTP 401 token=apify_api_BIMAT123 sai")
    hits, tk = W.thu_thap(DU_AN, chay_actor=hong, bay_gio=BAY_GIO)
    assert hits == [] and tk["trang_thai"] == "loi"
    assert "BIMAT123" not in tk["loi"] and "***" in tk["loi"]


def test_thu_thap_truyen_tran_va_payload():
    seen = {}

    def actor(p, lim, han, tran):
        seen.update(p=p, lim=lim, tran=tran)
        return [], {}
    W.thu_thap(DU_AN, tu=datetime.date(2026, 10, 9), den=datetime.date(2026, 10, 16),
               chay_actor=actor, bay_gio=BAY_GIO, con_usd=3.0)
    assert seen["tran"] == 0.1 and seen["lim"] == 4
    assert seen["p"]["tbs"] == "cdr:1,cd_min:10/9/2026,cd_max:10/16/2026"


# ───────── đọc dự phòng, đã biết, khẩu hiệu (tích hợp 16/10) ─────────
def test_so_cau_tim_va_cau_truy_van_nhom_4_tu():
    assert W.so_cau_tim(DU_AN["tu_khoa"]) == 1
    tu = [f"brand{i}" for i in range(9)]
    assert W.so_cau_tim(tu) == 3 and len(W.cau_truy_van({"ten": "x", "tu_khoa": tu})) == 3
    assert W.so_cau_tim([f"b{i}x" for i in range(40)]) == W.TOI_DA_TRUY_VAN
    assert W.so_cau_tim([]) == 0
    q = W.cau_truy_van(DU_AN, them_tu=["Do anything for love"])
    assert q[0].startswith('(hapas OR "yêu từ điều nhỏ nhất" OR "Do anything for love")')


def test_doc_du_phong_trang_bi_chan_co_tran_va_so_tien():
    items = _serp(("https://chan.vd.vn/a", "HAPAS", "túi hapas", "1 ngày trước"),
                  ("https://chan.vd.vn/b", "Khác", "", "1 ngày trước"),
                  ("https://chan.vd.vn/c", "Khác 2", "", "1 ngày trước"))
    goi = []

    def boc(urls, han, tran):
        goi.append((urls, tran))
        than = "<p>" + "Nội dung dài. " * 20 + "Túi HAPAS bền.</p>"
        return [{"url": urls[0], "crawl": {"httpStatusCode": 200}, "html": _bai("Bài A", than)},
                {"url": urls[1], "crawl": {"httpStatusCode": 403}}], {"run_id": "rb", "giay": 10}
    hits, tk, _ = _chay(items, {}, boc=boc, boc_toi_da=2, con_usd=1.0)
    assert goi == [(["https://chan.vd.vn/a", "https://chan.vd.vn/b"], 0.1)]   # brand trước, ≤ 2
    assert tk["run_ids"] == ["r1", "rb"] and tk["pheu"]["boc_duoc"] == 1
    assert tk["usd_boc"] == round(2 * W.GIA_BOC, 4) and tk["usd_tim"] == W.GIA_TRANG
    a = next(d for d, _ in hits if d["link"] == "https://chan.vd.vn/a")
    assert not a["_web"]["chi_trich"] and "HAPAS bền" in a["text"]


def test_doc_du_phong_loi_tinh_nguyen_tran_va_robots_cam_khong_doc():
    items = _serp(("https://chan.vd.vn/a", "HAPAS", "hapas", "1 ngày trước"))
    from apify_tool import LoiApify

    def hong(urls, han, tran):
        raise LoiApify("QUA_GIO", "hết giờ", {"run_id": "rb"})
    hits, tk, _ = _chay(items, {}, boc=hong, boc_toi_da=5, con_usd=1.0)
    assert tk["usd_boc"] == 0.1 and "rb" in tk["run_ids"] and hits[0][0]["_web"]["chi_trich"]
    g = _Gia({})
    g.tai = lambda u: (200, "User-agent: *\nDisallow: /\n", u) if u.endswith("robots.txt") \
        else pytest.fail("không được tải")
    hits, tk = W.thu_thap(DU_AN, tu=datetime.date(2026, 10, 1), den=datetime.date(2026, 10, 16),
                          chay_actor=lambda *a: (items, {}), tai=g.tai, bay_gio=BAY_GIO,
                          boc=lambda *a: pytest.fail("robots cấm: không đọc dự phòng"),
                          boc_toi_da=5, tu_dong_ho=g.dong_ho, han=1e9, ngu=g.ngu_)
    assert tk["pheu"]["robots_chan"] == 1 and hits[0][0]["_web"]["chi_trich"]


def test_da_biet_khong_tai_lai_va_tu_giu():
    items = _serp(("https://bao.vd.vn/co.htm", "HAPAS", "hapas", "1 ngày trước"),
                  ("https://bao.vd.vn/loai.htm", "HAPAS", "hapas", "1 ngày trước"),
                  ("https://bao.vd.vn/cu.htm", "HAPAS", "hapas", "20 ngày trước"))
    biet = {W.khoa_web("https://bao.vd.vn/co.htm"): "da_co",
            W.khoa_web("https://bao.vd.vn/loai.htm"): "da_loai_truoc"}
    hits, tk, g = _chay(items, {}, da_biet=lambda ks: {k: biet[k] for k in ks if k in biet},
                        tu_giu=BAY_GIO - datetime.timedelta(days=30))
    assert (tk["pheu"]["da_co"], tk["pheu"]["da_loai_truoc"]) == (1, 1)
    assert not any("co.htm" in u or "loai.htm" in u for u in g.goi)
    assert [d["link"] for d, _ in hits] == ["https://bao.vd.vn/cu.htm"]      # 20 ngày: trong phạm vi
