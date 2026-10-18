"""Script `scripts/lang_nghe_nap_raw.py` (18/10/2026): nạp raw ĐÃ TRẢ TIỀN vào kho qua pipeline lượt
tìm theo từ khoá, không gọi Apify. Raw mẫu dựng từ fixture cắt từ run thật (`mau_seeding_tiktok.json`
— scraptik; `mau_fb_mina.json` — mina), giờ đăng dời trọn ngày về gần hôm nay. Kho, AI giả."""
from __future__ import annotations

import copy
import datetime
import json
import os
import re
import sys
from pathlib import Path

import pytest

import apify_tool as A
import lang_nghe_db as K
import loc_rac as L
import theo_doi_api as TDA

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lang_nghe_nap_raw as N

_VN = datetime.timezone(datetime.timedelta(hours=7))
GOC = Path(__file__).parent
MAU = json.loads((GOC / "mau_seeding_tiktok.json").read_text(encoding="utf-8"))
MINA = json.loads((GOC / "mau_fb_mina.json").read_text(encoding="utf-8"))["items"]
BAY_GIO = datetime.datetime.now(_VN).replace(microsecond=0)
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas"], "tu_loai_tru": [],
         "boi_canh": "HAPAS — túi xách Việt Nam", "thi_truong": "VN", "cau_hinh": {},
         "hashtag": []}
NGUON = [{"id": 1, "nen_tang": "tiktok", "dinh_danh": "nha_mau", "loai": "kenh_nha"}]


def _lech() -> int:
    cuoi = max(int(a["create_time"]) for k, xs in MAU.items() if not k.startswith("_") for a in xs)
    return (int((BAY_GIO - datetime.timedelta(days=1)).timestamp()) - cuoi) // 86400 * 86400


def _aw(nhom, **doi):
    ra = []
    for a in copy.deepcopy(MAU[nhom]):
        a["create_time"] = int(a["create_time"]) + _lech()
        a.update(doi)
        ra.append(a)
    return ra


def _jsonl(f: Path, dong: list[dict]) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in dong), encoding="utf-8")


def _tao_raw(goc: Path) -> Path:
    """Thư mục raw như trên VPS: kompa/ (TikTok + mina) và vong1/ (actor không có bộ chuẩn hoá)."""
    seeding, review, live = _aw("seeding"), _aw("review"), _aw("livestream")
    ban_sao = copy.deepcopy(review[0])
    ban_sao["statistics"]["comment_count"] += 5           # cùng video, lần đọc khác nhiều bình luận hơn
    _jsonl(goc / "kompa" / "raw_tt_tag_hapas.jsonl", [
        {"loai": "searchHashtags", "tag": "hapas", "item": {"challenge_list": []}},
        {"loai": "challengePosts", "tag": "hapas", "item": {"aweme_list": seeding + review}}])
    _jsonl(goc / "kompa" / "raw_tt_tim_1_hapas.jsonl", [
        {"loai": "searchPosts", "tu": "hapas",
         "item": {"search_item_list": [{"aweme_info": a} for a in live + [ban_sao]]}}])
    nha = _aw("review")[:2]
    for i, a in enumerate(nha):
        a["aweme_id"] = f"88800000000000000{i}"
        a["author"] = {**a["author"], "unique_id": "nha_mau"}
    nha[1]["desc"] = "BST thu đông mới"                       # kênh nhà: không nhắc từ khoá vẫn giữ
    nha[1]["text_extra"] = []
    ghim = copy.deepcopy(nha[0])
    ghim.update(aweme_id="888000000000000099", is_top=1)
    _jsonl(goc / "kompa" / "raw_tt_user_nha.jsonl", [
        {"loai": "profile", "user": "nha_mau", "item": {"user": {}}},
        {"loai": "userPosts", "user": "nha_mau", "item": {"aweme_list": [ghim, *nha]}}])
    mina = copy.deepcopy(MINA[:2])
    for x in mina:
        x["post_title"] = "túi hapas pass lại 700k"
        ts = int(BAY_GIO.timestamp() - 2 * 86400) * 1000
        x["video_details"]["publish_timestamp"] = x["video_details"]["publish_date"] = ts
        x["scrape_date"] = "rác ngoài trường actor"
    (goc / "kompa" / "raw_fb_tui.json").write_text(json.dumps(
        {"ten": "fb_tui", "actor": "mina_safwat/facebook-search-actor",
         "input": {"query": "túi hapas"}, "items": [*mina, {"demo": True}]}, ensure_ascii=False),
        encoding="utf-8")
    (goc / "vong1").mkdir(parents=True, exist_ok=True)
    (goc / "vong1" / "raw_fb_scraperone_hapas.json").write_text(json.dumps(
        {"actor": "scraper_one/facebook-posts-search", "items": [{"postText": "hapas"}]}),
        encoding="utf-8")
    return goc


class KhoGia:
    def __init__(self, bai=()):
        self.bai = {r["khoa"]: dict(r) for r in bai}
        self.luot: dict[int, dict] = {}
        self.ghi: list[tuple] = []
        self.nang: list[tuple] = []
        self.quyen_xoa = True
        self.luot_chay: list[int] = []
        self.khoa_luot: list[int] = []

    def cai(self, mp):
        for ten in ("doc_du_an", "nguon_cua_du_an", "khoa_da_co", "khoa_fb_trung",
                    "lich_su_tai_khoan", "lich_chien_dich", "ghi_bai", "nang_so_lieu",
                    "cap_nhat_so_lieu", "ghi_de_xuat", "mo_luot", "dong_luot",
                    "khoa_theo_luot_dau"):
            mp.setattr(K, ten, getattr(self, ten))
        mp.setattr(K, "ket_noi", lambda: self)
        return self

    def doc_du_an(self, ma):
        return dict(DU_AN) if ma == "hapas" else None

    def nguon_cua_du_an(self, ma):
        return [dict(n) for n in NGUON]

    def khoa_da_co(self, ma, khoa):
        return {k for k in khoa if k in self.bai}

    def khoa_fb_trung(self, ma, rows):
        return {}

    def lich_su_tai_khoan(self, ma, tk, tu):
        return []

    def lich_chien_dich(self, ma):
        return []

    def ghi_bai(self, ma, luot, kieu, rows):
        self.ghi.append((kieu, [dict(r) for r in rows]))
        moi = 0
        for r in rows:
            moi += r["khoa"] not in self.bai
            self.bai.setdefault(r["khoa"], {**r, "kieu_quet": kieu, "luot_dau": luot,
                                            "luot_cuoi": luot, "bl_lay_luc": None, "so_bl": 0})
        return moi, len(rows) - moi

    def nang_so_lieu(self, ma, luot, rows, ngay):
        self.nang.append((ngay, [dict(r) for r in rows]))
        return len(rows)

    def cap_nhat_so_lieu(self, *a, **k):
        raise AssertionError("nạp raw không được ghi đè số bằng lần đọc cũ")

    def ghi_de_xuat(self, *a, **k):
        raise AssertionError("nạp raw không ghi đề xuất nguồn")

    def mo_luot(self, ma, kieu, **kw):
        i = len(self.luot) + 31
        self.luot[i] = {"kieu": kieu, **kw}
        return i

    def dong_luot(self, luot_id, **kw):
        self.luot[luot_id].update(kw)

    def khoa_theo_luot_dau(self, ma, luot):
        return [{"khoa": k, "luot_cuoi": r["luot_cuoi"], "bl_lay_luc": r.get("bl_lay_luc"),
                 "so_bl": r.get("so_bl", 0)} for k, r in sorted(self.bai.items())
                if r.get("luot_dau") == luot]

    # một giao dịch (hoàn tác)
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, ts=()):
        self._kq = []
        if sql == N.SQL_QUYEN:
            self._kq = [{"xoa": self.quyen_xoa}]
        elif sql == N.SQL_HAN_KHOA:
            pass
        elif sql == N.SQL_KHOA_LUOT:
            self.khoa_luot.append(ts[0])
        elif sql == N.SQL_LUOT_CHAY:
            self._kq = [{"id": i} for i in self.luot_chay if i != ts[1]]
        elif sql == N.SQL_XOA:
            _ma, khoa, luot_dau, luot_cuoi = ts
            for k in list(khoa):
                r = self.bai.get(k)
                if r and r.get("luot_dau") == luot_dau and r.get("luot_cuoi") == luot_cuoi \
                        and not r.get("bl_lay_luc") and not r.get("so_bl"):
                    del self.bai[k]
                    self._kq.append({"khoa": k})
        else:
            raise AssertionError(sql)
        return self

    def fetchone(self):
        return self._kq[0] if self._kq else None

    def fetchall(self):
        return list(self._kq)


@pytest.fixture
def ai(monkeypatch):
    """AI giả: phán GIỮ mọi bài (mã ugc) — chạy áp dụng chỉ ghi bài AI đã phán (soát M3)."""
    goi: list[tuple] = []

    def phan_xu(rows, *a, **k):
        goi.append((len(rows), k.get("song_song")))
        return ({i: (True, "ugc", "") for i in range(len(rows))},
                {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"})
    monkeypatch.setattr(A, "_phan_xu_ai", phan_xu)
    monkeypatch.setattr(N, "_chuan_bi_model", lambda: None)
    return goi


def _chay(argv, nghi=None):
    out: list[str] = []
    ma = N.chay(N.tao_parser().parse_args(argv), in_ra=out.append, bay_gio=BAY_GIO,
                nghi=nghi or (lambda s: None))
    return ma, "\n".join(out)


def _tu() -> str:
    return (BAY_GIO - datetime.timedelta(days=40)).date().isoformat()


def test_doc_raw_nhan_actor_chuan_hoa_dung_ham_cua_mark(tmp_path):
    raw = N.doc_raw([str(_tao_raw(tmp_path / "raw"))], BAY_GIO - datetime.timedelta(days=40),
                    BAY_GIO)
    loai = {(t, x) for t, x, _ in raw["tep"]}
    assert ("raw_fb_tui.json", "mina_safwat~facebook-search-actor") in loai
    assert raw["bo_qua"] == [("raw_fb_scraperone_hapas.json",
                              ("actor scraper_one~facebook-posts-search không có bộ chuẩn hoá "
                               "của Mark"))]
    fb = [d for d, _ in raw["tim"] if d["platform"] == "facebook"]
    assert len(fb) == 2, "item mẫu (demo) bỏ"
    assert set(fb[0]["__goc"]) <= set(A._TRUONG_ACTOR["mina_safwat~facebook-search-actor"]), \
        "item chiếu đúng trường như việc nền đọc dataset"
    assert fb[0]["_cum"] == "túi hapas" and fb[0]["username"] == "nguoi.dung.fb.1"
    tt = [d for d, _ in raw["tim"] if d["platform"] == "tiktok"]
    assert len(tt) == 8 + 3 + 6 + 1 and all(d["link"].startswith("https://www.tiktok.com/@")
                                           for d in tt)
    ho_so = [d for d, _ in raw["ho_so"]]
    assert [d["username"] for d in ho_so] == ["nha_mau", "nha_mau"], "video ghim bỏ như ho_so"


def test_gio_doc_theo_truong_thoi_gian_cua_item_roi_moi_toi_gio_ghi_tep(tmp_path):
    """Soát 18/10/2026: tệp chép lại mang giờ ghi hôm nay — giờ đọc lấy trường thời gian của item
    (scrapedAt / scraped_at / scrape_date / collectedAt, sớm nhất; không múi giờ = UTC) khi có."""
    assert N._luc_doc_item([{"scrapedAt": "2026-10-17T10:52:02.691Z"},
                            {"scrape_date": "2026-10-16 18:20:22.043405"}, {"x": 1}]) == \
        datetime.datetime(2026, 10, 17, 1, 20, 22, 43405, tzinfo=_VN)
    assert N._luc_doc_item([{"scrape_date": "rác"}]) is None
    luc = (BAY_GIO - datetime.timedelta(days=2)).astimezone(datetime.timezone.utc)
    it = {"id": "S1", "shortCode": "S1", "url": "https://www.instagram.com/p/S1/",
          "timestamp": luc.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "caption": "túi hapas",
          "hashtags": ["hapas"], "ownerUsername": "kh", "likesCount": 1, "commentsCount": 0,
          "inputUrl": "https://www.instagram.com/explore/tags/hapas",
          "scrapedAt": "2026-10-10T03:00:00.000Z"}
    (tmp_path / "raw_ig.json").write_text(json.dumps(
        {"actor": "apify/instagram-hashtag-scraper", "input": {"hashtags": ["hapas"]},
         "items": [it]}), encoding="utf-8")
    raw = N.doc_raw([str(tmp_path)], BAY_GIO - datetime.timedelta(days=40), BAY_GIO)
    ((d, _),) = raw["tim"]
    assert d["_luc_doc"] == datetime.datetime(2026, 10, 10, 10, 0, tzinfo=_VN)
    assert raw["theo_gio_tep"] == set()


def test_loc_khung_bo_trung_giu_ban_nhieu_binh_luan_va_ban_ho_so():
    luc = BAY_GIO - datetime.timedelta(days=2)

    def d(link, bl, **kw):
        return ({"platform": "tiktok", "link": link, "comments": bl, **kw}, luc)
    rows = [d("https://www.tiktok.com/@a/video/1", 2), d("https://www.tiktok.com/@a/video/1", 9),
            d("https://www.tiktok.com/@a/video/2", 1),
            d("https://www.tiktok.com/@a/video/2", 0, _ho_so=True),
            ({"platform": "tiktok", "link": "https://www.tiktok.com/@a/video/3", "comments": 0},
             BAY_GIO - datetime.timedelta(days=90))]
    giu, dem = N.loc_khung(rows, BAY_GIO - datetime.timedelta(days=30), BAY_GIO)
    assert dem["tiktok"] == {"ve": 5, "pham_vi": 4, "ngoai_pham_vi": 1, "trung": 2}
    assert sorted((x["link"][-1], x["comments"], bool(x.get("_ho_so"))) for x, _ in giu) == [
        ("1", 9, False), ("2", 0, True)]


def test_chay_thu_khong_ai_khong_ghi_in_phieu_uoc_tinh(monkeypatch, tmp_path, ai):
    kho = KhoGia().cai(monkeypatch)
    monkeypatch.delenv("PGOPTIONS", raising=False)
    ma, out = _chay(["hapas", str(_tao_raw(tmp_path / "raw")), "--tu", _tu()])
    assert ma == 0 and ai == [] and kho.ghi == [] and kho.nang == [] and kho.luot == {}
    assert "PGOPTIONS" not in os.environ, "trả lại môi trường sau chạy thử"
    assert "seeding affiliate 8" in out and "seeding tiktok @aff_mau: 8 bài" in out
    m = re.search(r"ƯỚC TÍNH: sẽ nạp (\d+) bài mới nhắc từ khoá", out)
    assert m and int(m.group(1)) == 3 + 6 + 2 + 2, out      # review + livestream + mina + kênh nhà
    assert "Bỏ qua 1 tệp" in out and "AI: " in out
    # 3 tệp scraptik + tệp mina (trường scrape_date rác) lấy giờ ghi tệp; tệp bỏ qua không tính.
    assert "CẢNH BÁO: 4 tệp raw mang giờ ghi HÔM NAY" in out, "raw vừa ghi: nhắc giữ giờ đọc thật"
    assert TDA.doc_seeding("hapas") == [], "chạy thử không ghi sổ"


def test_ap_dung_qua_pipeline_ghi_luot_va_tep_hoan_tac(monkeypatch, tmp_path, ai):
    review0 = MAU["review"][0]
    khoa_cu = f"tiktok:{review0['aweme_id']}"
    kho = KhoGia([{"khoa": khoa_cu, "luot_dau": 2, "luot_cuoi": 2, "binh_luan": 1}]).cai(monkeypatch)
    nghi: list = []
    tep = tmp_path / "nap.jsonl"
    ma, out = _chay(["hapas", str(_tao_raw(tmp_path / "raw")), "--tu", _tu(), "--ap-dung",
                     "--sao-luu", str(tep)], nghi=nghi.append)
    assert ma == 0, out
    # AI: từng phần ≤ LO bài, một lô một lúc; nghỉ giữa các phần đã gọi AI.
    assert ai and all(n <= N.LO for n, _ in ai)
    assert all(ss == 1 for n, ss in ai if ss is not None)
    assert nghi and set(nghi) == {N.NGHI_GIUA_LO}
    kieu = {r["tai_khoan"]: k for k, rows in kho.ghi for r in rows}
    assert kieu["nha_mau"] == "theo_doi" and kieu["review_mau"] == "tu_khoa"
    assert "aff_mau" not in kieu, "bài seeding không vào bai"
    nha = [r for _, rows in kho.ghi for r in rows if r["tai_khoan"] == "nha_mau"]
    assert {r["nguon_id"] for r in nha} == {1} and len(nha) == 2
    # Bài đã có: chỉ nâng số, ảnh chụp đúng ngày đọc raw (ngày ghi tệp), bản nhiều bình luận nhất.
    ((ngay, rows),) = kho.nang
    ngay_tep = datetime.datetime.fromtimestamp(
        (tmp_path / "raw" / "kompa" / "raw_tt_tim_1_hapas.jsonl").stat().st_mtime, _VN).date()
    assert ngay == ngay_tep
    assert rows == [{"khoa": khoa_cu, "xem": review0["statistics"]["play_count"],
                     "thich": review0["statistics"]["digg_count"],
                     "binh_luan": review0["statistics"]["comment_count"] + 5,
                     "chia_se": review0["statistics"]["share_count"], "nen_tang": "tiktok",
                     "_ngay_so": ngay_tep}]
    # Bài MỚI cũng mang ngày đọc raw: ảnh chụp chi_so_ngay không theo now() (soát LOW).
    assert all(r.get("_ngay_so") for _, rs in kho.ghi for r in rs)
    (luot, x), = kho.luot.items()
    assert x["kieu"] == "tu_khoa" and x["trang_thai"] == "xong" and x["chi_phi_usd"] == 0.0
    assert "phễu tìm TikTok" in x["ghi_chu"] and "seeding affiliate 8" in x["ghi_chu"]
    assert x["bai_moi"] == len([k for k, r in kho.bai.items() if r.get("luot_dau") == luot])
    assert len(TDA.doc_seeding("hapas")) == 8
    dong = [json.loads(s) for s in tep.read_text(encoding="utf-8").splitlines()]
    # Dòng "so" ghi NGAY sau mỗi phần (soát LOW: tiến trình chết giữa chừng vẫn hoàn tác được sổ),
    # "bai_moi" ở cuối.
    loai = [d["loai_dong"] for d in dong]
    assert loai[0] == "dau" and loai[-1] == "bai_moi" and set(loai[1:-1]) == {"so"}
    assert dong[0]["luot_id"] == luot and khoa_cu not in dong[-1]["khoa"]
    so = {k for d in dong if d["loai_dong"] == "so" for k in d["khoa"]}
    assert {d["so"] for d in dong if d["loai_dong"] == "so"} == {"hapas"}
    assert len(so) >= 8 and {
        k for k, v in TDA.doc_loai("hapas", TDA.dau_loai(DU_AN, ["hapas", "túi hapas"]),
                                   BAY_GIO - datetime.timedelta(days=60)).items()
        if v[0] == L.LY_DO_SEEDING_BAI} <= so
    # Hoàn tác: xoá bài lượt nạp đã thêm, TRỪ bài lượt sau đã đụng; gỡ khoá sổ; bài cũ giữ.
    dung = min(k for k, r in kho.bai.items() if r.get("luot_dau") == luot)
    kho.bai[dung]["luot_cuoi"] = luot + 1
    kho.quyen_xoa = False
    assert _chay(["hapas", "--hoan-tac", str(tep)])[0] == 2
    kho.quyen_xoa = True
    # Lượt khác đang chạy: dừng, chưa xoá gì (khoá advisory mở lượt đã giữ).
    kho.luot_chay = [luot, 99]
    so_bai = len(kho.bai)
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 2 and "lượt 99" in out and len(kho.bai) == so_bai
    assert kho.khoa_luot == [K.so_khoa_luot("hapas")]
    kho.luot_chay = [luot]                      # chính lượt nạp (bỏ dở) không chặn
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and set(kho.bai) == {khoa_cu, dung}
    assert "giữ 1 bài đã bị đụng sau lượt nạp" in out and "REVOKE DELETE ON bai" in out
    assert TDA.doc_seeding("hapas") == []


def test_so_them_ghi_sau_moi_phan_va_hoan_tac_go_ca_so_web(monkeypatch, tmp_path):
    """Soát LOW: khoá sổ lần nạp thêm (sổ dự án + sổ web `<mã>:web`) ghi vào tệp hoàn tác ngay sau
    mỗi phần, chỉ khoá của bài trong lô; `--hoan-tac` gỡ cả hai sổ (dòng "so" cũ = sổ dự án)."""
    kho = KhoGia().cai(monkeypatch)
    luc = BAY_GIO - datetime.timedelta(days=2)
    tu = BAY_GIO - datetime.timedelta(days=60)
    TDA.ghi_loai("hapas", "d1", [("tiktok:cu", "spam", luc)], tu)       # có sẵn trước lần nạp
    tep = tmp_path / "h.jsonl"
    with open(tep, "x", encoding="utf-8") as f:
        N._ghi_dong(f, {"loai_dong": "dau", "du_an": "hapas", "luot_id": 7})
        so = N.SoThem("hapas", {"tiktok:1", "tiktok:2"}, {"web:h1"}, f)
        TDA.ghi_loai("hapas", "d1", [("tiktok:1", "spam", luc), ("tiktok:la", "spam", luc)], tu)
        so.ghi()
        TDA.ghi_loai("hapas:web", "d2", [("web:h1", "khong_nhac", luc)], tu)
        TDA.ghi_seeding("hapas", [{"khoa": "tiktok:2", "nen_tang": "tiktok", "tai_khoan": "a",
                                   "dang_luc": luc, "bl": 0, "xem": 1}])
        so.ghi()
        so.ghi()                                  # không có gì mới: không ghi thêm dòng
        N._ghi_dong(f, {"loai_dong": "so", "khoa": []})                # dạng cũ không có "so"
        N._ghi_dong(f, {"loai_dong": "bai_moi", "khoa": []})
    dong = [json.loads(x) for x in tep.read_text(encoding="utf-8").splitlines()]
    assert [(d.get("so"), d["khoa"]) for d in dong if d["loai_dong"] == "so"] == [
        ("hapas", ["tiktok:1"]), ("hapas", ["tiktok:2"]), ("hapas:web", ["web:h1"]), (None, [])]
    assert so.tong() == 3
    ma, out = _chay(["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and "gỡ 3 khoá" in out
    assert set(TDA.doc_loai("hapas", "d1", tu)) == {"tiktok:cu", "tiktok:la"}
    assert TDA.doc_loai("hapas:web", "d2", tu) == {} and TDA.doc_seeding("hapas") == []
    assert kho.khoa_luot == [K.so_khoa_luot("hapas")]


def test_ap_dung_ai_khong_phan_thi_khong_ghi_va_bao_chay_lai(monkeypatch, tmp_path):
    """Soát 18/10/2026 (M3): AI lỗi / hết giờ / đạt trần thì phần đó KHÔNG ghi theo luật, không vào
    sổ; script báo số bài chưa phán, trả mã 1; chạy lại (AI ổn) thì nạp tiếp đúng các bài đó."""
    kho = KhoGia().cai(monkeypatch)
    monkeypatch.setattr(N, "_chuan_bi_model", lambda: None)
    goi: list[int] = []

    def hong(rows, *a, **k):
        goi.append(len(rows))
        return {}, {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "bỏ qua: model lỗi (0/9)"}
    monkeypatch.setattr(A, "_phan_xu_ai", hong)
    raw = str(_tao_raw(tmp_path / "raw"))
    ma, out = _chay(["hapas", raw, "--tu", _tu(), "--ap-dung", "--sao-luu",
                     str(tmp_path / "a.jsonl")])
    assert ma == 1 and goi, out
    ghi = [r["tai_khoan"] for _, rows in kho.ghi for r in rows]
    assert set(ghi) == {"nha_mau"}, "chỉ kênh nhà (AI chỉ gán nhãn) — bài AI chưa phán không ghi"
    assert "CHƯA XONG" in out and "AI chưa phán" in out
    assert kho.luot[max(kho.luot)]["trang_thai"] == "mot_phan", "chưa phán đủ: không phải xong"
    so = TDA.doc_loai("hapas", TDA.dau_loai(DU_AN, ["hapas", "túi hapas"]),
                      BAY_GIO - datetime.timedelta(days=60))
    assert {v[0] for v in so.values()} <= {L.LY_DO_SEEDING_BAI}, "AI chưa phán: không vào sổ"
    # Trần 0 lượt gọi AI: không gọi model nào.
    goi.clear()
    ma, out = _chay(["hapas", raw, "--tu", _tu(), "--ap-dung", "--sao-luu",
                     str(tmp_path / "b.jsonl"), "--toi-da-goi-ai", "0"])
    assert ma == 1 and goi == [] and "0/0 lượt gọi model" in out
    # Chạy lại khi AI ổn: bài chưa phán được xét và ghi.
    monkeypatch.setattr(A, "_phan_xu_ai", lambda rows, *a, **k: (
        {i: (True, "ugc", "") for i in range(len(rows))},
        {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"}))
    ma, out = _chay(["hapas", raw, "--tu", _tu(), "--ap-dung", "--sao-luu",
                     str(tmp_path / "c.jsonl")])
    assert ma == 0, out
    assert {"review_mau", "live_mau"} <= {r["tai_khoan"] for _, rows in kho.ghi for r in rows}


def test_gac_ai_tuan_tu_cho_lo_qua_han_va_tran_luot_goi():
    """Lô hết giờ: luồng model vẫn chạy nền — lô sau CHỜ nó xong, không bao giờ hai lô cùng gọi
    model. Trần lượt gọi: quá trần thì trả "bỏ qua" (không gọi)."""
    import threading
    import time
    dang, nhieu_nhat = [0], [0]
    khoa = threading.Lock()

    def hoi_cham(nhac, ngan_sach):
        with khoa:
            dang[0] += 1
            nhieu_nhat[0] = max(nhieu_nhat[0], dang[0])
        time.sleep(0.4)
        with khoa:
            dang[0] -= 1
        return f"ok {nhac}"
    out: list[str] = []
    g = N.GacAI(1, out.append)
    g._hoi_goc = hoi_cham
    with pytest.raises(A._FutTimeout):
        g.hoi("a", 0.05)
    assert g.hoi("b", 5) == "ok b" and nhieu_nhat[0] == 1 and g.cho == 1
    assert "chờ model trả lời xong" in out[0]
    g._xu_goc = lambda rows, *a, **k: ({0: (True, "ugc", "")}, {"trang_thai": "đã chạy"})
    assert g.phan_xu([1, 2, 3])[1]["trang_thai"] == "đã chạy" and g.da_goi == 1
    px, tt = g.phan_xu([1, 2])
    assert px == {} and tt["trang_thai"] == "bỏ qua: đạt trần 1 lượt gọi AI" and g.vuot == 2


def test_gac_ai_cho_lo_qua_han_co_gioi_han_roi_bo_qua_khi_model_treo():
    """Soát 18/10/2026 (LOW): lô quá hạn chỉ được chờ thêm `cho_toi_da` giây (mặc định
    `CHO_LO_TOI_DA`). Model vẫn chưa trả lời → TREO: phần sau trả "bỏ qua" ngay (không gọi model,
    không chờ thêm — chạy lại script là nạp tiếp); luồng treo xong thì gửi lại bình thường."""
    import threading
    import time
    nha = threading.Event()

    def hoi_treo(nhac, ngan_sach):
        nha.wait(5)
        return f"ok {nhac}"
    out: list[str] = []
    assert N.GacAI(5).cho_toi_da == N.CHO_LO_TOI_DA
    g = N.GacAI(5, out.append, cho_toi_da=0.1)
    g._hoi_goc = hoi_treo
    goi: list[int] = []
    g._xu_goc = lambda rows, *a, **k: (goi.append(len(rows)) or {0: (True, "ugc", "")},
                                       {"trang_thai": "đã chạy"})
    with pytest.raises(A._FutTimeout):
        g.hoi("a", 0.05)
    t0 = time.monotonic()
    px, tt = g.phan_xu([1, 2, 3])
    assert px == {} and tt["trang_thai"].startswith("bỏ qua: model treo") and g.bo_treo == 3
    assert g.treo and goi == [] and g.da_goi == 0 and time.monotonic() - t0 < 2
    assert any("TREO" in x for x in out)
    t0 = time.monotonic()
    assert g.phan_xu([1])[0] == {} and g.bo_treo == 4 and time.monotonic() - t0 < 0.05, \
        "đang treo: không chờ thêm"
    with pytest.raises(A._FutTimeout):
        g.hoi("b", 1)                       # lô trước còn treo: không gửi model song song
    nha.set()
    time.sleep(0.2)
    assert g.phan_xu([1, 2])[1]["trang_thai"] == "đã chạy" and goi == [2] and not g.treo


def test_ap_dung_ctrl_c_hay_loi_giua_chung_khong_dong_luot_xong(monkeypatch, tmp_path):
    """Soát 18/10/2026 (LOW): bản trước khởi tạo "xong" và chỉ bắt `Exception` — Ctrl-C giữa chừng
    vẫn đóng lượt "xong". Nay Ctrl-C → "mot_phan" (phần đã ghi giữ nguyên, tệp hoàn tác đủ khoá),
    lỗi → "loi", AI chưa phán một phần → "mot_phan"; chỉ chạy hết và đủ mới "xong"."""
    kho = KhoGia().cai(monkeypatch)
    monkeypatch.setattr(N, "_chuan_bi_model", lambda: None)
    raw = str(_tao_raw(tmp_path / "raw"))
    goi = [0]

    def ngat(rows, *a, **k):
        goi[0] += 1
        if goi[0] >= 2:
            raise KeyboardInterrupt
        return ({i: (True, "ugc", "") for i in range(len(rows))},
                {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"})
    monkeypatch.setattr(A, "_phan_xu_ai", ngat)
    tep = tmp_path / "a.jsonl"
    ma, out = _chay(["hapas", raw, "--tu", _tu(), "--ap-dung", "--sao-luu", str(tep)])
    (x,) = kho.luot.values()
    assert ma == 1 and x["trang_thai"] == "mot_phan" and "Ctrl-C" in x["loi"], out
    assert "DỪNG: dừng giữa chừng (Ctrl-C)" in out
    dong = [json.loads(s) for s in tep.read_text(encoding="utf-8").splitlines()]
    assert dong[-1]["loai_dong"] == "bai_moi" and dong[-1]["khoa"], "phần đã ghi vẫn hoàn tác được"

    def hong(rows, *a, **k):
        raise RuntimeError("kho mất kết nối")
    monkeypatch.setattr(A, "_phan_xu_ai", hong)
    ma, out = _chay(["hapas", raw, "--tu", _tu(), "--ap-dung", "--sao-luu",
                     str(tmp_path / "b.jsonl")])
    x = kho.luot[max(kho.luot)]
    assert ma == 1 and x["trang_thai"] == "loi" and "RuntimeError: kho mất kết nối" in x["loi"]


def test_nang_so_lieu_chi_nang_va_ghi_dung_ngay(monkeypatch):
    cau: list[tuple] = []

    class C:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, ts=()):
            cau.append((sql, list(ts)))
            return self

        def fetchone(self):
            return {"khoa": "tiktok:1", "moi": True}
    monkeypatch.setattr(K, "ket_noi", lambda: C())
    ngay = datetime.date(2026, 10, 18)
    n = K.nang_so_lieu("hapas", 9, [{"khoa": "tiktok:1", "xem": 10, "thich": None,
                                     "binh_luan": 3, "chia_se": 0},
                                    {"khoa": "tiktok:2"}], ngay)
    assert n == 1 and len(cau) == 2, "dòng không có số nào: bỏ"
    sua, anh = cau
    assert "xem = GREATEST(%s::bigint, xem)" in sua[0] and "now()" in sua[0]
    assert sua[1][:4] == [10, None, 3, 0] and "luot_cuoi = %s" in sua[0]
    assert "GREATEST(EXCLUDED.binh_luan, chi_so_ngay.binh_luan)" in anh[0]
    assert anh[1][2] == ngay, "ảnh chụp ghi ngày ĐỌC raw, không phải hôm nay"
    # Dòng mang `_ngay_so` (ngày đọc của chính lần đọc đó) thắng ngày chung của phần.
    cau.clear()
    K.nang_so_lieu("hapas", 9, [{"khoa": "tiktok:1", "xem": 10, "_ngay_so": datetime.date(
        2026, 10, 2)}], ngay)
    assert cau[1][1][2] == datetime.date(2026, 10, 2)
    # ghi_bai (bài MỚI của nạp raw): ảnh chụp vào ngày đọc, số chỉ nâng khi trùng bài đã có.
    cau.clear()
    K.ghi_bai("hapas", 9, "tu_khoa", [{"khoa": "tiktok:5", "nen_tang": "tiktok", "xem": 7,
                                       "_ngay_so": datetime.date(2026, 10, 3)}])
    bai, anh = cau
    assert "xem = GREATEST(EXCLUDED.xem, bai.xem)" in bai[0]
    assert "now()" not in anh[0] and anh[1][2] == datetime.date(2026, 10, 3)
    assert "GREATEST(EXCLUDED.xem, chi_so_ngay.xem)" in anh[0]
    cau.clear()
    K.ghi_bai("hapas", 9, "tu_khoa", [{"khoa": "tiktok:6", "nen_tang": "tiktok", "xem": 7}])
    assert "xem = COALESCE(EXCLUDED.xem, bai.xem)" in cau[0][0] and "now() AT TIME ZONE" in cau[1][0]
