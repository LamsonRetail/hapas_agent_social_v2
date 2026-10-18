"""Script `scripts/lang_nghe_sua_nguon_nha.py` (18/10/2026): gắn lại `nguon_id` + `kieu_quet =
theo_doi` cho bài kênh nhà mà lượt nạp raw 14 (và đường từ khoá Facebook trước đó) ghi với
`nguon_id` NULL. Kho giả theo câu SQL của script."""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import lang_nghe_db as K

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lang_nghe_sua_nguon_nha as S

_VN = datetime.timezone(datetime.timedelta(hours=7))
LUC = datetime.datetime(2026, 10, 16, 21, 0, tzinfo=_VN)
NGUON = [{"id": 2, "nen_tang": "facebook", "dinh_danh": "https://www.facebook.com/hapasglobal"},
         {"id": 1, "nen_tang": "tiktok", "dinh_danh": "nha_mau"}]


def _bai(khoa, p, tk, link, nguon_id=None, kieu="tu_khoa", luot=14):
    return {"khoa": khoa, "nen_tang": p, "tai_khoan": tk, "link": link, "nguon_id": nguon_id,
            "kieu_quet": kieu, "luot_dau": luot, "dang_luc": LUC}


BAI = [
    # Đã gắn (lượt /theodoi thật): link thedoor mang id trang → script học id này.
    _bai("facebook:1825684048882067", "facebook", "hapasglobal",
         "https://www.facebook.com/100066634543565/posts/1825684048882067", 2, "theo_doi", 9),
    _bai("facebook:pfbid0a", "facebook", "hapasglobal",
         "https://www.facebook.com/hapasglobal/posts/pfbid0a"),                 # tên trang
    _bai("facebook:1825684048882099", "facebook", "HAPAS",
         "https://www.facebook.com/100066634543565/posts/1825684048882099"),    # id trang đã học
    _bai("facebook:pfbid0k", "facebook", "HAPAS",
         "https://www.facebook.com/khach/posts/pfbid0k"),                       # tên hiển thị: không
    _bai("tiktok:7", "tiktok", "nha_mau", "https://www.tiktok.com/@nha_mau/video/7", luot=3),
    _bai("tiktok:8", "tiktok", "nha_mau", "https://www.tiktok.com/@nha_mau/video/8", 1, "theo_doi"),
    _bai("instagram:x", "instagram", "nha_mau", "https://www.instagram.com/p/x/"),  # không nguồn
]


class KhoGia:
    def __init__(self):
        self.bai = {r["khoa"]: dict(r) for r in BAI}
        self.lenh: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, ts=()):
        self.lenh.append(sql)
        self._kq, self.rowcount = [], 0
        if sql == S._SQL_NGUON:
            self._kq = [dict(n) for n in NGUON]
        elif sql == S._SQL_DA_GAN:
            self._kq = [{"nguon_id": r["nguon_id"], "link": r["link"]} for r in self.bai.values()
                        if r["nguon_id"] in ts[1]]
        elif sql == S._SQL_BAI:
            self._kq = [dict(r) for r in self.bai.values()
                        if r["nguon_id"] is None and r["nen_tang"] in ts[1]]
        elif sql == S._SQL_GHI:
            r = self.bai.get(ts[2])
            if r and r["nguon_id"] is None:
                r.update(nguon_id=ts[0], kieu_quet="theo_doi")
                self.rowcount = 1
        elif sql == S._SQL_HOAN:
            r = self.bai.get(ts[2])
            if r and r["nguon_id"] == ts[3]:
                r.update(nguon_id=None, kieu_quet=ts[0])
                self.rowcount = 1
        elif sql != "SET TRANSACTION READ ONLY":
            raise AssertionError(sql)
        return self

    def fetchall(self):
        return list(self._kq)


def _chay(kho, monkeypatch, argv):
    monkeypatch.setattr(K, "ket_noi", lambda: kho)
    out: list[str] = []
    ma = S.chay(S.tao_parser().parse_args(argv), in_ra=out.append)
    return ma, "\n".join(out)


def test_ke_hoach_dung_mot_nguon_kenh_nha_va_mo_ho():
    gan, mo_ho, bang = S.ke_hoach(NGUON, [{"nguon_id": 2, "link": BAI[0]["link"]}],
                                  [r for r in BAI if r["nguon_id"] is None])
    assert {r["khoa"]: r["nguon_moi"] for r in gan} == {
        "facebook:pfbid0a": 2, "facebook:1825684048882099": 2, "tiktok:7": 1}
    assert "id:100066634543565" in bang[2][1] and mo_ho == []
    # Nguồn kênh nhà thứ hai trỏ CÙNG trang theo id: chưa học id cho #2 thì về #4; học rồi thì khớp
    # hai nguồn → mơ hồ, để nguyên.
    hai = [*NGUON, {"id": 4, "nen_tang": "facebook",
                    "dinh_danh": "https://www.facebook.com/profile.php?id=100066634543565"}]
    gan, mo_ho, _ = S.ke_hoach(hai, [], [BAI[2]])
    assert [(r["khoa"], r["nguon_moi"]) for r in gan] == [("facebook:1825684048882099", 4)]
    assert mo_ho == []
    gan, mo_ho, _ = S.ke_hoach(hai, [{"nguon_id": 2, "link": BAI[0]["link"]}], [BAI[2]])
    assert gan == [] and [r["khop"] for r in mo_ho] == [[2, 4]]


def test_chay_thu_chi_doc_in_theo_luot_dau(monkeypatch):
    kho = KhoGia()
    ma, out = _chay(kho, monkeypatch, ["hapas"])
    assert ma == 0 and kho.lenh[0] == "SET TRANSACTION READ ONLY"
    assert S._SQL_GHI not in kho.lenh
    assert "Sẽ gắn 3 bài" in out and "theo luot_dau: lượt 3: 1, lượt 14: 2" in out, out
    assert "#2 facebook https://www.facebook.com/hapasglobal: 2 bài — lượt 14: 2" in out
    assert "facebook:pfbid0k" not in out and "instagram:x" not in out


def test_ap_dung_sao_luu_roi_hoan_tac(monkeypatch, tmp_path):
    kho = KhoGia()
    tep = tmp_path / "sua.json"
    assert _chay(kho, monkeypatch, ["hapas", "--ap-dung"])[0] == 2, "thiếu --sao-luu"
    ma, out = _chay(kho, monkeypatch, ["hapas", "--ap-dung", "--sao-luu", str(tep)])
    assert ma == 0 and "Đã gắn 3/3 bài" in out
    assert {k: (r["nguon_id"], r["kieu_quet"]) for k, r in kho.bai.items()} == {
        "facebook:1825684048882067": (2, "theo_doi"), "facebook:pfbid0a": (2, "theo_doi"),
        "facebook:1825684048882099": (2, "theo_doi"), "facebook:pfbid0k": (None, "tu_khoa"),
        "tiktok:7": (1, "theo_doi"), "tiktok:8": (1, "theo_doi"),
        "instagram:x": (None, "tu_khoa")}
    sl = json.loads(tep.read_text(encoding="utf-8"))
    assert sl["du_an"] == "hapas" and {(d["khoa"], d["kieu_quet"], d["nguon_id"]) for d in
                                       sl["dong"]} == {("facebook:pfbid0a", "tu_khoa", None),
                                                       ("facebook:1825684048882099", "tu_khoa",
                                                        None), ("tiktok:7", "tu_khoa", None)}
    assert _chay(kho, monkeypatch, ["hapas", "--ap-dung", "--sao-luu", str(tep)])[0] == 2, \
        "không ghi đè tệp hoàn tác"
    kho.bai["tiktok:7"]["nguon_id"] = 9                    # người khác đổi nguồn sau đó
    ma, out = _chay(kho, monkeypatch, ["hapas", "--hoan-tac", str(tep)])
    assert ma == 0 and "2/3 bài" in out
    assert kho.bai["facebook:pfbid0a"]["nguon_id"] is None
    assert kho.bai["facebook:pfbid0a"]["kieu_quet"] == "tu_khoa"
    assert kho.bai["tiktok:7"]["nguon_id"] == 9
    assert _chay(kho, monkeypatch, ["khac", "--hoan-tac", str(tep)])[0] == 2
