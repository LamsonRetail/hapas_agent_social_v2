"""Khử trùng bài Facebook lúc ghi kho (17/10/2026, `khu_trung_fb`).

Đo thật DB production 17/10/2026: mỗi lượt cào actor trả pfbid KHÁC cho cùng một bài, kho khoá
theo pfbid → 161 bài FB của hapas có 24 nhóm trùng (60 dòng, thừa 36); bài kênh nhà
hapaschinhhanggiatot 05/10 15:12 có 3 bản (bình luận báo / đã cào 100/93, 100/94, 91/20). Kho
`lang_nghe` GIẢ trong bộ nhớ (đủ đúng các câu SQL của `ghi_bai` / `khoa_fb_trung`)."""
from __future__ import annotations

import base64
import datetime
import re

import pytest

import apify_tool as A
import khu_trung_fb as KT
import lang_nghe_db as K
import theo_doi as T

_VN = datetime.timezone(datetime.timedelta(hours=7))
LUC = datetime.datetime(2026, 10, 5, 15, 12, 7, tzinfo=_VN)
CHU = "Bộ sưu tập túi mới về, giảm 20% cho đơn đầu tiên tại cửa hàng HAPAS"


def _bai(khoa, **kw):
    r = {"khoa": f"facebook:{khoa}", "nen_tang": "facebook",
         "link": f"https://www.facebook.com/hapaschinhhanggiatot/posts/{khoa}",
         "tai_khoan": "hapaschinhhanggiatot", "tac_gia": "hapaschinhhanggiatot",
         "dang_luc": LUC, "noi_dung": CHU, "xem": None, "thich": 10, "binh_luan": 100,
         "chia_se": 1}
    r.update(kw)
    return r


# ───────────────────────────── hàm thuần ─────────────────────────────
@pytest.mark.parametrize("link, so", [
    ("https://www.facebook.com/Hapasthoitrang/posts/1429851122453378:1429851122453378",
     "1429851122453378"),
    ("https://www.facebook.com/Hapasonlineshop/videos/1087399034274635/", "1087399034274635"),
    ("https://www.facebook.com/reel/5473353312889243/", "5473353312889243"),
    ("https://www.facebook.com/groups/700481333796092/posts/2531904023987138/", "2531904023987138"),
    ("https://www.facebook.com/story.php?story_fbid=1234567890123&id=100066634543565",
     "1234567890123"),
    ("https://www.facebook.com/groups/1/permalink/987654321098765/", "987654321098765"),
    ("https://www.facebook.com/hapasglobal/posts/pfbid0JPyRK6bE1capFFykMTkS797UZgtQbLauCx3", None),
    ("https://www.facebook.com/permalink.php?story_fbid=pfbid0VV17GQUEFa1Qr6F1&id=100064", None),
    ("https://www.facebook.com/photo.php?fbid=123456789012345", None),   # id ẢNH, không phải bài
    ("", None),
])
def test_bo_id_so_tu_link(link, so):
    assert KT.ma_so_tu_link(link) == so


def test_bo_id_so_tu_item_tho_cua_tung_actor():
    fb = base64.b64encode(b"feedback:1461248806106257").decode()
    assert KT.ma_so_tu_goc({"postId": "1087415290851146"}) == "1087415290851146"   # apify
    assert KT.ma_so_tu_goc({"post_id": "1019155114466781"}) == "1019155114466781"  # scrapeforge
    assert KT.ma_so_tu_goc({"post": {"id": "1461248806106257"}}) == "1461248806106257"  # thedoor
    assert KT.ma_so_tu_goc({"feedbackId": fb}) == "1461248806106257"
    assert KT.ma_so_tu_goc({"topLevelUrl": "https://www.facebook.com/100044/posts/1013727286781520"}
                           ) == "1013727286781520"
    # `id` trơn KHÔNG đọc (nghĩa khác nhau giữa actor); pfbid, bool, rác → None.
    assert KT.ma_so_tu_goc({"id": "1087415290851146", "postId": "pfbid02abc"}) is None
    assert KT.la_so(True) is None and KT.la_so("12a45") is None and KT.la_so(1234567) == "1234567"
    # Ưu tiên: trường bộ chuẩn hoá đã điền → item thô → link.
    assert KT.ma_so_fb({"ma_so_fb": "111111", "__goc": {"postId": "222222"}}) == "111111"
    assert KT.ma_so_fb({"ma_so_fb": "pfbid", "_goc": {"postId": "222222"}}) == "222222"
    assert KT.ma_so_fb({"link": "https://www.facebook.com/x/videos/333333/"}) == "333333"


def test_chu_bai_so_dang_gon_ten_hien_thi_va_ten_trang():
    """Đo 17/10: bài 16/09 13:49 — lượt theo dõi ghi tai_khoan "hapaschinhhanggiatot", lượt tìm
    theo từ khoá ghi tai_khoan rỗng + tac_gia "HAPAS - Chính Hãng Giá Tốt"."""
    a = _bai("pfbidA")
    b = _bai("pfbidB", tai_khoan="", tac_gia="HAPAS - Chính Hãng Giá Tốt")
    assert KT.chu_bai(a) & KT.chu_bai(b)
    nhom = _bai("pfbidC", link="https://www.facebook.com/groups/700481333796092/posts/pfbidC",
                tai_khoan="", tac_gia="Chën Dä")
    assert KT.chu_bai(nhom) == {"chenda"}, "đoạn 'groups' của link không phải chủ bài"


def test_cung_bai_theo_chu_phut_noi_dung():
    a = _bai("pfbidA")
    assert KT.cung_bai(a, _bai("pfbidB", dang_luc=LUC.replace(second=50), thich=25))
    assert not KT.cung_bai(a, _bai("pfbidB", noi_dung="Một bài KHÁC đăng cùng phút, khác hẳn chữ"))
    assert not KT.cung_bai(a, _bai("pfbidB", dang_luc=LUC + datetime.timedelta(minutes=1)))
    assert not KT.cung_bai(a, _bai("pfbidB", tai_khoan="shop.khac", tac_gia="Shop Khác",
                                   link="https://www.facebook.com/shop.khac/posts/pfbidB"))
    # Ảnh không chú thích cùng phút của một trang: thường là hai bài khác nhau.
    assert not KT.cung_bai(_bai("pfbidA", noi_dung="🌸🌸"), _bai("pfbidB", noi_dung="🌸🌸"))
    # Bài ngắn (< 30 ký tự, không có mã nội dung): so nội dung chuẩn hoá.
    assert KT.cung_bai(_bai("pfbidA", noi_dung="Túi mới!!"), _bai("pfbidB", noi_dung="túi mới"))
    # Id số: chung id → cùng bài (dù khác phút); hai id actor trả khác nhau → khác bài.
    assert KT.cung_bai(_bai("pfbidA", ma_so_fb="1111111"),
                       _bai("pfbidB", ma_so_fb="1111111", dang_luc=None))
    assert KT.cung_bai(_bai("1111111"), _bai("pfbidB", ma_so_fb="1111111", dang_luc=None))
    assert not KT.cung_bai(_bai("pfbidA", ma_so_fb="1111111"), _bai("pfbidB", ma_so_fb="2222222"))


def test_bo_chuan_hoa_facebook_dien_ma_so():
    d, _ = A._chuan_facebook([{"post_id": "1019155114466781", "timestamp": 1789748074,
                               "url": "https://www.facebook.com/reel/1434065735528313/",
                               "author": {"name": "X"}, "message": "m"}])[0]
    assert d["ma_so_fb"] == "1019155114466781", "id bài của actor, không phải id reel trong link"
    d, _ = A._chuan_facebook([{"url": "https://www.facebook.com/x/videos/1087399034274635/"}])[0]
    assert d["ma_so_fb"] == "1087399034274635"
    assert "post_id" in A._TRUONG_ACTOR["scrapeforge~facebook-search-posts"], "việc nền đọc fields="
    tk = {"ho_so": {"ten": "hapasglobal", "tai_khoan": "hapasglobal"}, "bai": [
        {"ngay": LUC, "link": "https://www.facebook.com/hapasglobal/posts/pfbid0abc",
         "noi_dung": CHU, "_goc": {"postId": "1087415290851146"}}]}
    d, _ = T._dong_tu_tai_khoan("facebook", tk)[0]
    assert d["ma_so_fb"] == "1087415290851146"
    tk["ho_so"]["tai_khoan"] = "kol.a"
    d, _ = T._dong_tu_tai_khoan("tiktok", {**tk, "bai": [{**tk["bai"][0], "_goc": {"id": "7"}}]})[0]
    assert "ma_so_fb" not in d, "nền tảng khác giữ đúng khoá cũ"


def test_ban_sao_tu_khoa_giu_ma_so_khi_bo_goc():
    d = {"platform": "facebook", "link": "https://www.facebook.com/x/posts/pfbid0abc", "text": CHU,
         "__goc": {"post_id": "1019155114466781"}}
    ban = T._ban_sao_tu_khoa([(d, LUC)])
    assert ban[0][0]["ma_so_fb"] == "1019155114466781"
    assert T._cot_fb(ban[0][0]) == {"ma_so_fb": "1019155114466781"}
    assert T._cot_fb({"platform": "tiktok"}) == {}


# ───────────────────────────── kho giả ─────────────────────────────
class KhoGia:
    """Bảng `bai` + `chi_so_ngay` trong bộ nhớ: nhận đúng các câu SQL của `ghi_bai` và
    `khoa_fb_trung`; câu lạ là lỗi (đổi SQL thì phải đổi bài thử)."""

    def __init__(self, bai=(), co_cot=True):
        self.bai = {r["khoa"]: dict(r) for r in bai}
        self.so: list[str] = []
        self.co_cot = co_cot
        self.cau: list[str] = []
        self._kq: list = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @staticmethod
    def _xep(cac):
        return sorted(cac, key=lambda r: (-(r.get("bl_da_lay") or 0), r.get("thay", 0), r["khoa"]))

    def execute(self, sql, ts=()):
        self.cau.append(sql)
        ts = list(ts or [])
        if "information_schema.columns" in sql:
            self._kq = [{"co": 1}] if self.co_cot else []
        elif sql.startswith("SELECT 1 AS co FROM bai WHERE du_an = %s AND khoa = %s"):
            self._kq = [{"co": 1}] if ts[1] in self.bai else []
        elif sql.startswith("SELECT khoa FROM bai WHERE du_an = %s AND nen_tang = 'facebook'"):
            assert ("ma_so_fb" in sql) == self.co_cot, "DB chưa có cột thì không đọc cột"
            ids, khoa = (ts[1], ts[2]) if self.co_cot else ([], ts[1])
            self._kq = [{"khoa": r["khoa"]} for r in self._xep(
                r for r in self.bai.values() if r["nen_tang"] == "facebook"
                and (r.get("ma_so_fb") in ids or r["khoa"] in khoa))][:1]
        elif sql.startswith("SELECT khoa, link, tai_khoan"):
            tu, den = ts[1], ts[2]
            self._kq = [dict(r) for r in self._xep(
                r for r in self.bai.values() if r["nen_tang"] == "facebook"
                and r.get("dang_luc") and tu <= r["dang_luc"] < den)]
        elif sql.startswith("INSERT INTO bai "):
            cot = re.search(r"luot_cuoi, (.*?)\) VALUES", sql).group(1).split(", ")
            r = dict(zip(cot, ts[4:4 + len(cot)]))
            cu = self.bai.get(r["khoa"])
            if cu is None:
                self.bai[r["khoa"]] = {**r, "thay": len(self.bai)}
            else:
                for k in ("xem", "thich", "binh_luan", "chia_se"):
                    cu[k] = r[k] if r.get(k) is not None else cu.get(k)
                if "ma_so_fb" in cot:
                    assert "ma_so_fb = COALESCE(bai.ma_so_fb, EXCLUDED.ma_so_fb)" in sql
                    cu["ma_so_fb"] = cu.get("ma_so_fb") or r.get("ma_so_fb")
            self._kq = [{"moi": cu is None}]
        elif sql.startswith("INSERT INTO chi_so_ngay"):
            self.so.append(ts[1])
            self._kq = []
        else:
            raise AssertionError(f"câu SQL lạ: {sql[:80]}")
        return self

    def fetchone(self):
        return self._kq[0] if self._kq else None

    def fetchall(self):
        return list(self._kq)


@pytest.fixture
def kho(monkeypatch):
    def tao(bai=(), co_cot=True):
        k = KhoGia(bai, co_cot)
        monkeypatch.setattr(K, "ket_noi", lambda: k)
        monkeypatch.setattr(K, "_CO_MA_SO_FB", [])
        return k
    return tao


def test_ban_trung_pfbid_moi_dung_lai_khoa_cu(kho):
    """hapaschinhhanggiatot 05/10 15:12: lượt sau trả pfbid khác → CẬP NHẬT bài cũ, không thêm."""
    k = kho([_bai("pfbid0ynyYs3dYcTV7", bl_da_lay=94)])
    moi, cu = K.ghi_bai("hapas", 9, "theo_doi", [_bai("pfbid033LcjnDFuTfZ", thich=25,
                                                      binh_luan=101)])
    assert (moi, cu) == (0, 1) and list(k.bai) == ["facebook:pfbid0ynyYs3dYcTV7"]
    assert k.bai["facebook:pfbid0ynyYs3dYcTV7"]["thich"] == 25
    assert k.so == ["facebook:pfbid0ynyYs3dYcTV7"], "số theo ngày ghi vào khoá cũ"


def test_bai_khac_dang_cung_phut_khac_noi_dung_van_them_moi(kho):
    k = kho([_bai("pfbidA")])
    assert K.ghi_bai("hapas", 9, "theo_doi", [_bai("pfbidB", noi_dung="Minigame tháng 10: "
                                                    "bình luận để nhận quà từ HAPAS nhé")]) == (1, 0)
    assert set(k.bai) == {"facebook:pfbidA", "facebook:pfbidB"}


def test_khop_theo_id_so_truoc_va_dien_id_cho_dong_cu(kho):
    k = kho([_bai("pfbidA", ma_so_fb="1087415290851146", dang_luc=LUC - datetime.timedelta(
        hours=3))])                                   # phút khác: chỉ id mới khớp được
    assert K.ghi_bai("hapas", 9, "tu_khoa", [_bai("hABC", ma_so_fb="1087415290851146")]) == (0, 1)
    assert list(k.bai) == ["facebook:pfbidA"]
    # Dòng cũ chưa có id (ghi trước 17/10) mà khớp theo phút + nội dung: điền id.
    k = kho([_bai("pfbidA")])
    K.ghi_bai("hapas", 9, "tu_khoa", [_bai("pfbidB", ma_so_fb="1019155114466781")])
    assert k.bai["facebook:pfbidA"]["ma_so_fb"] == "1019155114466781"
    # Khoá cũ dạng "facebook:<số>" (link /videos/<số>) khớp id bóc từ link mới.
    k = kho([_bai("1087399034274635", link="https://www.facebook.com/x/videos/1087399034274635/")])
    K.ghi_bai("hapas", 9, "tu_khoa", [_bai("pfbidB", ma_so_fb="1087399034274635",
                                           dang_luc=LUC + datetime.timedelta(days=1))])
    assert list(k.bai) == ["facebook:1087399034274635"]


def test_nhieu_ban_cu_chon_ban_script_gop_se_giu(kho):
    k = kho([_bai("pfbidA", bl_da_lay=20), _bai("pfbidB", bl_da_lay=94),
             _bai("pfbidC", bl_da_lay=93)])
    K.ghi_bai("hapas", 9, "theo_doi", [_bai("pfbidD")])
    assert k.so == ["facebook:pfbidB"]


def test_db_chua_co_cot_van_ghi_duoc(kho):
    k = kho([_bai("pfbidA")], co_cot=False)
    assert K.ghi_bai("hapas", 9, "theo_doi", [_bai("pfbidB", ma_so_fb="1111111")]) == (0, 1)
    assert not any("ma_so_fb" in c for c in k.cau if c.startswith("INSERT INTO bai"))
    k = kho([], co_cot=False)
    assert K.ghi_bai("hapas", 9, "theo_doi", [_bai("pfbidB", ma_so_fb="1111111")]) == (1, 0)


def test_nen_tang_khac_khong_them_cau_sql(kho):
    k = kho()
    K.ghi_bai("hapas", 9, "theo_doi", [{"khoa": "tiktok:1", "nen_tang": "tiktok", "link": "l",
                                        "noi_dung": CHU, "dang_luc": LUC, "thich": 1}])
    assert [c.split(" (")[0] for c in k.cau] == ["INSERT INTO bai", "INSERT INTO chi_so_ngay"]


def test_hai_ban_trung_trong_cung_mot_lo(kho):
    """Hai từ khoá trả cùng bài với hai pfbid trong một lượt: bản sau khớp bản trước vừa ghi."""
    k = kho()
    assert K.ghi_bai("hapas", 9, "tu_khoa", [_bai("pfbidA"), _bai("pfbidB")]) == (1, 1)
    assert list(k.bai) == ["facebook:pfbidA"]


def test_khoa_fb_trung_cho_buoc_tach_truoc_ai(kho):
    kho([_bai("pfbidCU")])
    assert K.khoa_fb_trung("hapas", [_bai("pfbidMOI"), _bai("pfbidCU"),
                                     {"khoa": "tiktok:1", "nen_tang": "tiktok"}]) == {
        "facebook:pfbidMOI": "facebook:pfbidCU"}


def test_tim_tu_khoa_bai_fb_da_co_chi_cap_nhat_so_khong_qua_ai(monkeypatch):
    """Lượt tìm theo từ khoá trả bài cũ với pfbid mới: đi đường ĐÃ CÓ (cập nhật số) với khoá cũ,
    không gửi AI xét lại."""
    import theo_doi_api as TDA
    gui_ai, cap = [], []
    monkeypatch.setattr(K, "khoa_fb_trung", lambda ma, rows: {
        r["khoa"]: "facebook:pfbidCU" for r in rows if r["khoa"].endswith("pfbidMOI")})
    monkeypatch.setattr(K, "khoa_da_co", lambda ma, khoa: {x for x in khoa if x.endswith("CU")})
    monkeypatch.setattr(K, "cap_nhat_so_lieu", lambda ma, luot, rows: cap.extend(rows) or len(rows))
    monkeypatch.setattr(T, "_giu_tu_khoa", lambda *a, **k: gui_ai.append(a[2]))
    monkeypatch.setattr(TDA, "ghi_loai", lambda *a, **k: None)
    d = {"platform": "facebook", "link": "https://www.facebook.com/hapasglobal/posts/pfbidMOI",
         "kenh": "HAPAS", "username": "", "text": CHU, "likes": 25, "__goc": {}}
    tk = {"pheu": {}, "pham_vi": {"tu": (LUC - datetime.timedelta(days=30)).isoformat()}}
    T._tach_va_giu({"ma": "hapas", "ten": "HAPAS"}, 9, [(d, LUC)], ["hapas"], 0.0, tk)
    assert [r["khoa"] for r in cap] == ["facebook:pfbidCU"] and cap[0]["thich"] == 25
    assert gui_ai == [] and tk["cap_nhat"] == 1


def test_tra_trung_hong_kho_thi_van_chay(monkeypatch):
    def hong(ma, rows):
        raise K.LoiKho("không nối được kho lắng nghe (OperationalError)")
    monkeypatch.setattr(K, "khoa_fb_trung", hong)
    d = {"platform": "facebook", "link": "https://www.facebook.com/x/posts/pfbidMOI", "text": CHU}
    assert T._khoa_fb_cu("hapas", [(d, LUC)], lambda d: "facebook:pfbidMOI") == {}
    assert T._khoa_fb_cu("hapas", [({"platform": "tiktok", "link": "l"}, LUC)], str) == {}


def test_cot_moi_co_trong_schema_va_bigquery():
    from pathlib import Path
    goc = Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe"
    sql = (goc / "schema.sql").read_text(encoding="utf-8")
    khoi = re.search(r"CREATE TABLE IF NOT EXISTS bai \((.*?)\n\);", sql, re.DOTALL).group(1)
    assert set(K._COT_FB) <= set(re.findall(r"^\s{2}([a-z_]+)\s", khoi, re.MULTILINE))
    # DB đã tạo: thêm cột chạy lại được, có index, có mô tả cột.
    assert "ALTER TABLE bai ADD COLUMN IF NOT EXISTS ma_so_fb TEXT;" in sql
    assert re.search(r"CREATE INDEX IF NOT EXISTS bai_ma_so_fb ON bai \(du_an, ma_so_fb\)", sql)
    assert re.search(r"COMMENT ON COLUMN bai\.ma_so_fb IS '.{40,}';", sql)
    # Mark ghi bài bằng quyền cả bảng (không theo cột) — cột mới không cần GRANT riêng.
    assert "GRANT SELECT, INSERT, UPDATE ON bai, chi_so_ngay, luot_quet, binh_luan TO mark;" in sql
    bq = (goc / "bigquery.sql").read_text(encoding="utf-8")
    assert bq.count("ma_so_fb        STRING    OPTIONS") == 1
    assert "ADD COLUMN IF NOT EXISTS ma_so_fb STRING" in bq
