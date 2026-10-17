"""Script một lần `scripts/lang_nghe_gan_lai.py` (chẩn đoán 16/10/2026): trả lời fanpage nhà →
thương hiệu, gán lại nhãn bình luận minigame / khen mà Trung lập.

Kho và model đều GIẢ: kho giả nhận diện từng câu SQL theo thẻ `/* gl:… */` và làm đúng ngữ
nghĩa của câu đó trên bộ nhớ (kể cả giao dịch READ ONLY và điều kiện "giá trị còn như lúc
đọc"); model giả trả nhãn theo nội dung. Không cần Postgres, không ra mạng."""
from __future__ import annotations

import contextlib
import copy
import datetime
import importlib.util
import json
import re
from pathlib import Path

import pytest

import lang_nghe_db as K
import phan_loai as P

_DUONG = Path(__file__).resolve().parents[1] / "scripts" / "lang_nghe_gan_lai.py"
_spec = importlib.util.spec_from_file_location("lang_nghe_gan_lai", _DUONG)
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

TC, TI, TL = (P.SAC_THAI[k] for k in "+-=")
CD = P.CHU_DE
FANPAGE = "HAPAS - Chính Hãng Giá Tốt"


class _Cur:
    def __init__(self, rows=None, rowcount=0):
        self.rows, self.rowcount = rows or [], rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class KhoGia:
    """Bảng du_an / nguon / bai / binh_luan trên bộ nhớ; mỗi `ket_noi()` là một giao dịch."""

    def __init__(self):
        self.du_an = {"hapas": {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas"]}}
        self.nguon = {1: "kenh_nha", 2: "kenh_nha", 3: "kol"}
        self.bai = {
            "facebook:p1": {"tai_khoan": "hapaschinhhanggiatot", "tac_gia": "hapaschinhhanggiatot",
                            "nguon_id": 1, "noi_dung": "Túi mới về"},
            "tiktok:mg": {"tai_khoan": "hapas.official", "tac_gia": "HAPAS", "nguon_id": 2,
                          "noi_dung": "20/10 này, bạn muốn nói gì với người phụ nữ bạn thương "
                                      "nhất? 💌"},
            "tiktok:kol": {"tai_khoan": "kol.a", "tac_gia": "Kol A", "nguon_id": 3,
                           "noi_dung": "review túi"},
        }
        self.bl: dict[tuple, dict] = {}
        self.giao_dich: list[dict] = []
        self.tep_sao_luu: str | None = None
        self.luot_bat_dau: dict[int, datetime.datetime] = {}     # bảng luot_quet (id → bat_dau)

    def them(self, kb, ma, tac_gia, noi_dung, loai="hop_le", sac=TL, cd=CD["KHAC"], nha=False,
             luot=None, thay=None):
        self.bl[("hapas", kb, ma)] = {
            "khoa_bai": kb, "ma": ma, "tac_gia": tac_gia, "noi_dung": noi_dung, "thich": 1,
            "loai": loai, "ly_do_loc": None, "sac_thai": sac if loai == "hop_le" else None,
            "chu_de": cd if loai == "hop_le" else None, "cua_thuong_hieu": nha,
            "luot_id": luot, "thay_lan_dau": thay, "cap_nhat_cuoi": "cu"}

    @contextlib.contextmanager
    def ket_noi(self):
        gd = {"chi_doc": False, "lenh": []}
        anh = copy.deepcopy(self.bl)
        try:
            yield _Conn(self, gd)
        except Exception:
            self.bl = anh                                   # rollback
            gd["ok"] = False
            self.giao_dich.append(gd)
            raise
        gd["ok"] = True
        self.giao_dich.append(gd)

    def ghi(self) -> list[dict]:
        return [g for g in self.giao_dich if "sua" in g["lenh"]]


class _Conn:
    def __init__(self, kho: KhoGia, gd: dict):
        self.kho, self.gd = kho, gd

    def execute(self, sql, ts=()):
        k = self.kho
        if sql == S.SQL_CHI_DOC:
            assert not self.gd["lenh"], "SET TRANSACTION READ ONLY phải là câu đầu giao dịch"
            self.gd["chi_doc"] = True
            self.gd["lenh"].append("chi_doc")
            return _Cur()
        ten = re.match(r"/\* gl:(\w+) \*/", sql).group(1)
        self.gd["lenh"].append(ten)
        if ten == "du_an":
            x = k.du_an.get(ts[0])
            return _Cur([dict(x)] if x else [])
        if ten == "bl_nha":
            ra = []
            for (da, kb, _), r in sorted(k.bl.items()):
                p = k.bai[kb]
                if da == ts[0] and k.nguon[p["nguon_id"]] == "kenh_nha" \
                        and not r["cua_thuong_hieu"]:
                    ra.append({**{c: r[c] for c in ("khoa_bai", "ma", "tac_gia", "noi_dung",
                                                    *S.COT)},
                               "bai_tai_khoan": p["tai_khoan"], "bai_tac_gia": p["tac_gia"]})
            return _Cur(ra)
        if ten == "bl_hop_le":
            assert "b.luot_id" in sql and "b.thay_lan_dau" in sql
            return _Cur([{**{c: r[c] for c in ("khoa_bai", "ma", "tac_gia", "noi_dung", "thich",
                                               "luot_id", "thay_lan_dau", *S.COT)},
                          "bai_noi_dung": k.bai[kb]["noi_dung"]}
                         for (da, kb, _), r in sorted(k.bl.items())
                         if da == ts[0] and r["loai"] == "hop_le"])
        if ten == "moc_luot":
            assert self.gd["chi_doc"], "đọc mốc lượt trong cùng giao dịch chỉ đọc"
            sau = [t for i, t in k.luot_bat_dau.items() if i > ts[0]]
            return _Cur([{"bat_dau": min(sau) if sau else None}])
        if ten == "sua":
            if self.gd["chi_doc"]:
                raise RuntimeError("ReadOnlySqlTransaction: không ghi trong giao dịch chỉ đọc")
            assert "cap_nhat_cuoi = now()" in sql and "IS NOT DISTINCT FROM" in sql
            dat, (da, kb, ma), kiem = ts[:5], ts[5:8], ts[8:]
            if k.tep_sao_luu:
                da_luu = {(x.get("khoa_bai"), x.get("ma"))
                          for x in map(json.loads, Path(k.tep_sao_luu).read_text(
                              encoding="utf-8").splitlines())}
                assert (kb, ma) in da_luu, "tệp hoàn tác phải có dòng TRƯỚC khi sửa kho"
            r = k.bl.get((da, kb, ma))
            if r is None or tuple(r[c] for c in S.COT) != tuple(kiem):
                return _Cur(rowcount=0)
            r.update(dict(zip(S.COT, dat)), cap_nhat_cuoi="moi")
            return _Cur(rowcount=1)
        raise AssertionError(f"câu SQL lạ: {ten}")


def _kho_mau() -> KhoGia:
    k = KhoGia()
    k.them("facebook:p1", "c1", FANPAGE, "Dạ HAPAS đã gửi tin nhắn tư vấn cho mình, vui lòng "
           "kiểm tra tin nhắn. HAPAS xin cảm ơn!", cd=CD["DV"])
    k.them("facebook:p1", "c2", FANPAGE, ".", loai="it_noi_dung")
    k.them("facebook:p1", "c3", "Lan Hapas Lover", "giá bn ạ", cd=CD["GIA"])
    k.them("facebook:p1", "c4", "Nguyễn Thị Mai Anh", "túi đẹp quá", cd=CD["SP"])
    for i in range(1, 6):
        k.them("tiktok:mg", f"m{i}", f"khach{i}",
               f"27{i} – Chúc mẹ luôn hạnh phúc" + (". Chúc HAPAS phát triển" if i == 5 else ""))
    k.them("tiktok:mg", "m6", "khach6", "con thương mẹ nhiều lắm")
    k.them("tiktok:kol", "k1", "Kol A", "cảm ơn mọi người")       # chủ bài KOL trả lời
    k.them("tiktok:kol", "k2", "khach7", "20/10 vui vẻ nha", sac=TC)
    return k


@pytest.fixture
def moi(monkeypatch):
    """Kho giả + model giả (đếm số lượt gọi)."""
    monkeypatch.delenv("SOCIAL_TAI_KHOAN_NHA", raising=False)
    kho = _kho_mau()
    monkeypatch.setattr(K, "ket_noi", kho.ket_noi)
    monkeypatch.setattr(S, "_chuan_bi_model", lambda: None)
    goi: list[list[str]] = []

    def model(nhac):
        texts = re.findall(r'<c i="(\d+)">(.*?)</c>', nhac[len(P._NHAC):])
        goi.append([t for _, t in texts])
        if kho.khi_goi_model:
            kho.khi_goi_model()
        ra = {}
        for i, t in texts:
            if re.match(r"\d", t):
                ra[i] = ["+", "MG"] if "HAPAS" in t else ["=", "MG"]
            elif "mẹ" in t:
                ra[i] = ["=", "MG"]
            elif "đẹp" in t:
                ra[i] = ["+", "GIA"] if "giá" in t else ["+", "SP"]
            elif "giá" in t:
                ra[i] = ["=", "GIA"]
            else:
                ra[i] = ["=", "KHAC"]
        return json.dumps(ra)
    kho.khi_goi_model = None
    monkeypatch.setattr(P, "_goi_model", model)
    return kho, goi


def _bang(kho):
    return {k: {c: v for c, v in r.items() if c != "cap_nhat_cuoi"} for k, r in kho.bl.items()}


def test_chon_dong_dung_muc_tieu():
    k = _kho_mau()
    rows_nha = [dict(r, bai_tai_khoan=k.bai[r["khoa_bai"]]["tai_khoan"],
                     bai_tac_gia=k.bai[r["khoa_bai"]]["tac_gia"])
                for r in k.bl.values() if r["khoa_bai"] == "facebook:p1"]
    a = S.chon_thuong_hieu(k.du_an["hapas"], rows_nha)
    assert {d["ma"] for d in a} == {"c1", "c2"}
    c1 = next(d for d in a if d["ma"] == "c1")
    assert c1["moi"] == {"loai": "thuong_hieu", "ly_do_loc": None, "sac_thai": None,
                         "chu_de": None, "cua_thuong_hieu": True}
    c2 = next(d for d in a if d["ma"] == "c2")
    assert c2["moi"]["loai"] == "it_noi_dung" and c2["moi"]["cua_thuong_hieu"] is True
    hop_le = [dict(r, bai_noi_dung=k.bai[r["khoa_bai"]]["noi_dung"])
              for r in k.bl.values() if r["loai"] == "hop_le"]
    b = S.chon_gan_lai(hop_le, bo={("facebook:p1", "c1")})
    ly = {d["ma"]: d["ly_do"] for d in b}
    assert ly == {"c4": "khen_ma_trung_lap", "m1": "so_du_thi", "m2": "so_du_thi",
                  "m3": "so_du_thi", "m4": "so_du_thi", "m5": "so_du_thi", "m6": "bai_minigame"}
    assert len(S.chon_gan_lai(hop_le, tat_ca=True, bo={("facebook:p1", "c1")})) == 10
    # Số dự thi: không nhầm ngày "20/10" hay số thập phân; nhận "110:", "#271", "Số 12".
    assert all(S.la_so_du_thi(t) for t in ("110: Chúc mẹ", "271 – con", "#271 chúc", "Số 12 ạ",
                                            "679 May Mắn", "  563 aaa💖"))
    assert not any(S.la_so_du_thi(t) for t in ("20/10 vui vẻ", "8.3 rồi", "chúc mẹ 20/10"))
    assert S.la_bai_minigame("MINIGAME 20/10 — bình luận để nhận quà tặng")
    assert S.la_bai_minigame("Comment ngay để nhận quà từ HAPAS")
    assert not S.la_bai_minigame("Túi xách mới, đẹp quá trời")
    assert S.co_loi_khen("Túi XINH ghê") and not S.co_loi_khen("chúc mẹ khỏe")


def test_chay_thu_khong_ghi_khong_goi_model_va_uoc_luot(moi, capsys):
    kho, goi = moi
    truoc = copy.deepcopy(kho.bl)
    assert S.main(["hapas"]) == 0
    ra = capsys.readouterr().out
    assert kho.bl == truoc and not kho.ghi() and goi == []
    assert kho.giao_dich and all(g["chi_doc"] for g in kho.giao_dich)
    assert "CHẠY THỬ" in ra and "(a) Trả lời của tài khoản nhà dưới bài kênh nhà: 2 dòng" in ra
    assert "(b) Gán lại nhãn: 7 dòng (so_du_thi 5, khen_ma_trung_lap 1, bai_minigame 1)" in ra
    assert "Ước tính: 7 dòng cần model → 1 lượt gọi model" in ra
    # Tác giả chỉ hiện dạng băm.
    assert S.bam("Nguyễn Thị Mai Anh") in ra and "Nguyễn Thị Mai Anh" not in ra
    assert FANPAGE not in ra and S.bam(FANPAGE) in ra


def test_thu_xem_truoc_goi_mot_lo_khong_ghi(moi, capsys):
    kho, goi = moi
    truoc = copy.deepcopy(kho.bl)
    assert S.main(["hapas", "--thu", "3"]) == 0
    assert len(goi) == 1 and len(goi[0]) == 3
    assert kho.bl == truoc and not kho.ghi()
    assert "Xem trước 3 dòng (1 lượt model, KHÔNG ghi)" in capsys.readouterr().out


def test_ap_dung_roi_hoan_tac_tron_vong(moi, tmp_path, capsys):
    kho, goi = moi
    goc = _bang(kho)
    tep = tmp_path / "gan-lai.jsonl"
    kho.tep_sao_luu = str(tep)
    assert S.main(["hapas", "--ap-dung", "--sao-luu", str(tep)]) == 0
    bl = {k[2]: r for k, r in kho.bl.items()}
    # (a) trả lời của fanpage nhà
    assert (bl["c1"]["loai"], bl["c1"]["sac_thai"], bl["c1"]["chu_de"],
            bl["c1"]["cua_thuong_hieu"]) == ("thuong_hieu", None, None, True)
    assert bl["c2"]["loai"] == "it_noi_dung" and bl["c2"]["cua_thuong_hieu"] is True
    # (b) gán lại theo prompt mới
    assert (bl["c4"]["sac_thai"], bl["c4"]["chu_de"]) == (TC, CD["SP"])
    assert all((bl[f"m{i}"]["sac_thai"], bl[f"m{i}"]["chu_de"]) == (TL, CD["MG"])
               for i in range(1, 5))
    assert (bl["m5"]["sac_thai"], bl["m5"]["chu_de"]) == (TC, CD["MG"])
    assert bl["m6"]["chu_de"] == CD["MG"]
    # Dòng ngoài mục tiêu: không một cột nào đổi, kể cả cap_nhat_cuoi.
    for m in ("c3", "k1", "k2"):
        assert bl[m] == {**goc[("hapas", bl[m]["khoa_bai"], m)], "cap_nhat_cuoi": "cu"}, m
    assert all(r["cap_nhat_cuoi"] == "moi" for m, r in bl.items() if m not in ("c3", "k1", "k2"))
    assert len(goi) == 1, "7 dòng = một lô model"
    # Đọc trong giao dịch chỉ đọc; mỗi lô ghi một giao dịch riêng.
    assert kho.giao_dich[0]["chi_doc"] and len(kho.ghi()) == 2
    dong = [json.loads(x) for x in tep.read_text(encoding="utf-8").splitlines()]
    assert dong[0]["loai_dong"] == "dau" and dong[0]["du_an"] == "hapas"
    assert {(d["khoa_bai"], d["ma"]) for d in dong[1:]} == {
        ("facebook:p1", m) for m in ("c1", "c2", "c4")} | {("tiktok:mg", f"m{i}")
                                                           for i in range(1, 7)}
    assert "Tệp hoàn tác:" in capsys.readouterr().out
    # Không ghi đè tệp hoàn tác cũ.
    assert S.main(["hapas", "--ap-dung", "--sao-luu", str(tep)]) == 2
    kho.tep_sao_luu = None
    assert S.main(["hapas", "--hoan-tac", str(tep)]) == 0
    assert _bang(kho) == goc
    assert "trả lại 9/9 dòng" in capsys.readouterr().out
    # Hoàn tác lần nữa: không còn dòng nào mang giá trị mới → không đổi gì.
    assert S.main(["hapas", "--hoan-tac", str(tep)]) == 0 and _bang(kho) == goc


def test_dong_bi_sua_giua_chung_thi_khong_de(moi, tmp_path, capsys):
    kho, _ = moi

    def chen():           # lượt quét khác sửa m1 trong lúc đang gọi model
        kho.bl[("hapas", "tiktok:mg", "m1")]["sac_thai"] = TI
    kho.khi_goi_model = chen
    tep = tmp_path / "u.jsonl"
    assert S.main(["hapas", "--ap-dung", "--sao-luu", str(tep), "--buoc", "b"]) == 0
    assert kho.bl[("hapas", "tiktok:mg", "m1")]["sac_thai"] == TI
    assert kho.bl[("hapas", "tiktok:mg", "m2")]["chu_de"] == CD["MG"]
    assert kho.bl[("hapas", "facebook:p1", "c1")]["loai"] == "hop_le", "--buoc b không đụng (a)"
    assert "bỏ qua 1" in capsys.readouterr().out
    assert S.main(["hapas", "--hoan-tac", str(tep)]) == 0
    assert kho.bl[("hapas", "tiktok:mg", "m1")]["sac_thai"] == TI, "hoàn tác cũng không đè"
    assert kho.bl[("hapas", "tiktok:mg", "m2")]["chu_de"] == CD["KHAC"]


def test_lo_100_dong_moi_luot_model_va_moi_giao_dich(moi, tmp_path):
    kho, goi = moi
    for i in range(150):
        kho.them("tiktok:kol", f"x{i}", f"k{i}", f"giá túi này bn vậy {i}a", cd=CD["KHAC"])
    S.main(["hapas", "--ap-dung", "--sao-luu", str(tmp_path / "u.jsonl"), "--tat-ca",
            "--buoc", "b"])
    assert [len(x) for x in goi] == [100, 61], "161 dòng cần model → 2 lượt, lô ≤ 100"
    ghi = kho.ghi()
    assert len(ghi) == 2 and all(g["lenh"].count("sua") <= 100 for g in ghi)


def test_ap_dung_thieu_sao_luu_thi_dung(moi, capsys):
    kho, goi = moi
    truoc = copy.deepcopy(kho.bl)
    assert S.main(["hapas", "--ap-dung"]) == 2
    assert kho.bl == truoc and not kho.giao_dich and goi == []
    assert "--sao-luu" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        S.main(["hapas", "--dry-run", "--ap-dung", "--sao-luu", "x"])


# ───────────── --den-luot (17/10/2026): bỏ bình luận của lượt đã gán bằng prompt mới ─────────────
_VN = datetime.timezone(datetime.timedelta(hours=7))
_L9 = datetime.datetime(2026, 10, 17, 0, 51, tzinfo=_VN)      # lượt 9 bắt đầu (sau deploy PR #62)


def _kho_luot() -> KhoGia:
    k = KhoGia()
    k.luot_bat_dau = {5: _L9 - datetime.timedelta(days=2), 8: _L9 - datetime.timedelta(hours=5),
                      9: _L9, 10: _L9 + datetime.timedelta(hours=7)}
    cu = _L9 - datetime.timedelta(days=1)
    k.them("tiktok:kol", "o5", "khach1", "giá túi này bn vậy", luot=5, thay=cu)
    k.them("tiktok:kol", "o8", "khach2", "túi đẹp quá", luot=8, thay=cu)
    k.them("tiktok:kol", "on", "khach3", "ship tỉnh không shop", luot=None, thay=cu)  # lượt đã xoá
    k.them("tiktok:kol", "n9", "khach4", "mua ở đâu vậy", luot=9, thay=_L9)
    k.them("tiktok:kol", "n10", "khach5", "màu này còn không", luot=10,
           thay=_L9 + datetime.timedelta(hours=7))
    # Cào lại ở lượt 10 nhưng thấy lần đầu TRƯỚC lượt 9: luot_id mới, nhãn vẫn của prompt cũ
    # (prompt cũ chấm "Tích cực"; model giả — prompt mới — ra "Trung lập": phải được ghi).
    k.them("tiktok:kol", "c10", "khach6", "dùng bền lắm", luot=10, thay=cu, sac=TC)
    # Bài minigame: 5 bình luận dự thi của lượt 10 + 1 bình luận lượt 5 không mở đầu bằng số.
    for i in range(1, 6):
        k.them("tiktok:mg", f"m{i}", f"dt{i}", f"30{i} – Chúc mẹ vui", luot=10, thay=_L9)
    k.them("tiktok:mg", "m0", "dt0", "con thương mẹ", luot=5, thay=cu)
    return k


@pytest.fixture
def moi_luot(moi, monkeypatch):
    _, goi = moi
    k = _kho_luot()
    k.khi_goi_model = None
    monkeypatch.setattr(K, "ket_noi", k.ket_noi)
    return k, goi


def test_den_luot_chay_thu_in_bo_loc_va_chi_chon_luot_cu(moi_luot, capsys):
    kho, goi = moi_luot
    truoc = copy.deepcopy(kho.bl)
    assert S.main(["hapas", "--buoc", "b", "--tat-ca", "--den-luot", "8"]) == 0
    ra = capsys.readouterr().out
    assert kho.bl == truoc and not kho.ghi() and goi == []
    assert all(g["chi_doc"] for g in kho.giao_dich)
    # o5, o8, on (NULL = cũ), c10 (cào lại ở lượt 10, thấy lần đầu trước lượt 9 — soát M1) + m0
    # (bài minigame xét trên MỌI bình luận của bài, kể cả lượt 10).
    assert "(b) Gán lại nhãn: 5 dòng (tat_ca 3, khen_ma_trung_lap 1, bai_minigame 1)." in ra
    assert ("Bộ lọc lượt (b): --den-luot 8 — chọn 5 dòng có thể còn nhãn prompt cũ: luot_id ≤ 8: "
            "3; luot_id NULL (lượt đã xoá, tính là cũ): 1; luot_id > 8 nhưng thấy lần đầu TRƯỚC "
            "lượt 9 (cào lại ở lượt sau, nhãn vẫn cũ): 1 (lượt 9 bắt đầu 2026-10-17T00:51+07:00). "
            "Bỏ 7 dòng thấy lần đầu từ lượt 9 (đã gán bằng prompt mới).") in ra
    assert ra.index("Bộ lọc lượt (b)") < ra.index("(b) Gán lại nhãn"), "bộ lọc in trước số dòng"
    rows = [dict(r, bai_noi_dung=kho.bai[r["khoa_bai"]]["noi_dung"]) for r in kho.bl.values()]
    b = S.chon_gan_lai(rows, tat_ca=False, den_luot=8, moc=_L9)
    assert {d["ma"]: d["ly_do"] for d in b} == {"o8": "khen_ma_trung_lap", "m0": "bai_minigame"}
    assert {d["ma"] for d in S.chon_gan_lai(rows, True, den_luot=8, moc=_L9)} == \
        {"o5", "o8", "on", "c10", "m0"}


def test_nhanh_luot_ba_nhanh_va_khong_co_moc():
    """Soát 17/10/2026 (M1): `luot_id` là lượt cào GẦN NHẤT — dòng thấy lần đầu trước lượt N+1
    vẫn được chọn dù `luot_id > N`. Chưa có lượt nào sau N (`moc` None) / thiếu `thay_lan_dau`:
    chỉ hai nhánh theo `luot_id`."""
    cu, moi = _L9 - datetime.timedelta(days=1), _L9 + datetime.timedelta(minutes=1)
    assert S.nhanh_luot({"luot_id": 8, "thay_lan_dau": moi}, 8, _L9) == "luot_cu"
    assert S.nhanh_luot({"luot_id": None, "thay_lan_dau": moi}, 8, _L9) == "luot_null"
    assert S.nhanh_luot({"luot_id": 12, "thay_lan_dau": cu}, 8, _L9) == "thay_truoc"
    assert S.nhanh_luot({"luot_id": 12, "thay_lan_dau": _L9}, 8, _L9) is None, "đúng mốc = mới"
    assert S.nhanh_luot({"luot_id": 12, "thay_lan_dau": cu}, 8, None) is None
    assert S.nhanh_luot({"luot_id": 12, "thay_lan_dau": None}, 8, _L9) is None
    assert S.trong_luot({"luot_id": 12}, None) and not S.trong_luot({"luot_id": 12}, 8)
    assert "chưa có lượt nào sau lượt 8" in S._cau_loc_luot(8, [{"luot_id": 3}], None)


def test_den_luot_khong_dat_thi_noi_ro_khong_loc(moi_luot, capsys):
    assert S.main(["hapas", "--buoc", "b", "--tat-ca"]) == 0
    ra = capsys.readouterr().out
    assert "Bộ lọc lượt (b): KHÔNG — mọi lượt quét" in ra
    assert "(b) Gán lại nhãn: 12 dòng" in ra
    assert not any("moc_luot" in g["lenh"] for g in moi_luot[0].giao_dich), \
        "không lọc thì không hỏi mốc lượt"


def test_den_luot_ap_dung_chi_sua_luot_cu_va_ghi_vao_tep(moi_luot, tmp_path, capsys):
    kho, goi = moi_luot
    goc = _bang(kho)
    tep = tmp_path / "gan-lai-den-8.jsonl"
    kho.tep_sao_luu = str(tep)
    assert S.main(["hapas", "--buoc", "b", "--tat-ca", "--den-luot", "8", "--ap-dung",
                   "--sao-luu", str(tep)]) == 0
    assert "Bộ lọc lượt (b): --den-luot 8" in capsys.readouterr().out
    gui = {t for lo in goi for t in lo}
    assert "dùng bền lắm" in gui, "cào lại ở lượt 10 mà thấy lần đầu trước lượt 9: phải gán lại"
    assert gui <= {"giá túi này bn vậy", "túi đẹp quá", "ship tỉnh không shop", "con thương mẹ",
                   "dùng bền lắm"}, "model chỉ nhận bình luận có thể còn nhãn prompt cũ"
    for m in ("n9", "n10", "m1", "m5"):     # thấy lần đầu từ lượt 9: không một cột nào đổi
        kb = "tiktok:mg" if m.startswith("m") else "tiktok:kol"
        assert kho.bl[("hapas", kb, m)] == {**goc[("hapas", kb, m)], "cap_nhat_cuoi": "cu"}, m
    assert kho.bl[("hapas", "tiktok:kol", "c10")]["sac_thai"] == TL
    dong = [json.loads(x) for x in tep.read_text(encoding="utf-8").splitlines()]
    assert dong[0]["den_luot"] == 8 and dong[0]["tat_ca"] is True
    assert "c10" in {d["ma"] for d in dong[1:]} <= {"o5", "o8", "on", "c10", "m0"}
    with pytest.raises(SystemExit):
        S.main(["hapas", "--den-luot", "-1"])
