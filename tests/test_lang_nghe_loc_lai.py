"""Spam affiliate trên KHO (16/10/2026): luật cấp bài trong `lang_nghe_db.ghi_binh_luan`, giữ nhãn
kho khi cào lại, và script lọc lại dữ liệu cũ `scripts/lang_nghe_loc_lai.py` (xem trước chỉ đọc /
ghi kèm tệp hoàn tác / hoàn tác). Kho GIẢ ghi lại câu SQL — không cần Postgres."""
from __future__ import annotations

import contextlib
import datetime
import json
import sys
from pathlib import Path

import pytest

import lang_nghe_db as K

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lang_nghe_loc_lai as S

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 10, 14, 0, 0, tzinfo=UTC)
MA_AFF = ("AHS-WCM-DQN", "CJW-UJK-A88AH xóa 88 rồi zán cam ah", "KQX-77A-PLM", "ZZT-81P-QWE",
          "𝐠𝐢𝐚́ 𝐫𝐞̉ 𝐪𝐮𝐚́ 𝐝𝐚́𝐧 𝐯𝐚̀𝐨 𝐥𝐚̀ 𝐫𝐚")


def _dong(ma, tg, gio, nd, loai="hop_le", bai="tiktok:1", **kw):
    return {"khoa_bai": bai, "ma": ma, "tac_gia": tg, "noi_dung": nd, "loai": loai,
            "luc": T0 + datetime.timedelta(hours=gio), "cua_thuong_hieu": False,
            "ly_do_loc": None, "sac_thai": "Trung lập", "chu_de": None, **kw}


class GiaCur:
    """Một kết nối giả, trả dòng theo câu SQL: dự án, bài, bình luận. UPDATE: affiliate hàng loạt
    đếm theo số mã; lọc lại / hoàn tác: 1 dòng (hoàn tác 0 với mã trong `da_sua_sau`)."""

    def __init__(self, rows=(), du_an=(), bai=(), da_sua_sau=()):
        self.rows, self.du_an, self.bai = list(rows), list(du_an), list(bai)
        self.da_sua_sau, self.sql = set(da_sua_sau), []
        self.rowcount = 0
        self._ra: list = []

    def execute(self, q, ts=()):
        q = " ".join(q.split())
        self.sql.append((q, ts))
        if "FROM du_an" in q:
            self._ra = self.du_an
        elif "FROM bai " in q:
            self._ra = self.bai
        elif q.startswith("SELECT"):
            self._ra = self.rows
        elif q.startswith("UPDATE binh_luan SET loai = %s"):              # hoàn tác
            self.rowcount = 0 if ts[6] in self.da_sua_sau else 1
        elif q.startswith("UPDATE"):
            self.rowcount = len(ts[2]) if isinstance(ts[2], list) else 1
        elif q.startswith("INSERT"):
            self._ra = [{"moi": True}]
        return self

    def fetchall(self):
        return list(self._ra)

    def fetchone(self):
        return self._ra[0] if self._ra else None


def test_danh_dau_affiliate_hang_loat_tren_kho():
    rows = [_dong(f"c{i}", f"acc{i}", i * 5, MA_AFF[i]) for i in range(5)] + \
           [_dong("k", "khach", 2, "xin giá set túi trắng")]
    c = GiaCur(rows, du_an=[{"ten": "HAPAS", "tu_khoa": ["hapas"]}])
    assert K._danh_dau_affiliate(c, "hapas", ["tiktok:1", None, "tiktok:1"]) == 5
    q, ts = next((q, ts) for q, ts in c.sql if q.startswith("SELECT khoa_bai, ma"))
    assert "khoa_bai = ANY(%s)" in q and "loai = 'hop_le' OR ly_do_loc = ANY(%s)" in q
    assert "dang_luc AS luc" in q and "thay_lan_dau" not in q            # chỉ giờ đăng thật
    assert "loai = 'thuong_hieu' OR cua_thuong_hieu" in q                # để biết mã của brand
    assert ts[1] == ["tiktok:1"] and set(ts[2]) == {"affiliate_dan_ma", "affiliate_hang_loat"}
    assert any(q.startswith("SELECT khoa, noi_dung FROM bai") for q, _ in c.sql)
    q, ts = next((q, ts) for q, ts in c.sql if q.startswith("UPDATE"))
    assert "ly_do_loc = 'affiliate_hang_loat'" in q and "sac_thai = NULL, chu_de = NULL" in q
    assert "cap_nhat_cuoi = now()" in q and q.endswith("AND loai = 'hop_le'")
    assert sorted(ts[2]) == [f"c{i}" for i in range(5)]                  # khách thật không đụng
    assert K._danh_dau_affiliate(GiaCur(rows[:4]), "hapas", ["tiktok:1"]) == 0
    # Minigame: mã có trong bài của brand → không phải spam.
    mg = [_dong(f"m{i}", f"acc{i}", i, "QUA-TANG-2710") for i in range(5)]
    assert K._danh_dau_affiliate(GiaCur(mg, bai=[{"khoa": "tiktok:1",
                                                  "noi_dung": "Bình luận QUA-TANG-2710"}]),
                                 "hapas", ["tiktok:1"]) == 0
    c = GiaCur()
    assert K._danh_dau_affiliate(c, "hapas", [None]) == 0 and c.sql == []


def test_ghi_binh_luan_giu_nhan_kho_va_chay_luat_cap_bai(monkeypatch):
    c = GiaCur()

    @contextlib.contextmanager
    def ket_noi():
        yield c
    monkeypatch.setattr(K, "ket_noi", ket_noi)
    K.ghi_binh_luan("hapas", 7, [{"khoa_bai": "tiktok:1", "ma": "c1", "noi_dung": "ib",
                                  "loai": "hop_le"}], {})
    ins = c.sql[0][0]
    # Nhãn kho (seeding, spam affiliate hàng loạt) không bị lượt cào sau đưa về hop_le, không mang
    # lại sắc thái/chủ đề.
    giu = "(EXCLUDED.loai = 'hop_le' AND (binh_luan.loai = 'seeding' OR " \
          "binh_luan.ly_do_loc = 'affiliate_hang_loat'))"
    for cot in ("sac_thai", "chu_de"):
        assert f"{cot} = CASE WHEN {giu} THEN NULL" in ins
    assert f"loai = CASE WHEN {giu} THEN binh_luan.loai ELSE EXCLUDED.loai END" in ins
    assert ins.count("sac_thai =") == 1                                   # không gán hai lần
    assert any(q.startswith("SELECT khoa_bai, ma, tac_gia") and "ly_do_loc = ANY" in q
               for q, _ in c.sql)                                         # luật cấp bài đã chạy


def test_da_gan_nhan_bo_qua_ai_cho_nhan_kho(monkeypatch):
    c = GiaCur()

    @contextlib.contextmanager
    def ket_noi():
        yield c
    monkeypatch.setattr(K, "ket_noi", ket_noi)
    K.da_gan_nhan("hapas", ["tiktok:1"])
    q = c.sql[0][0]
    assert "sac_thai IS NOT NULL OR loai = 'seeding' OR ly_do_loc = 'affiliate_hang_loat'" in q


def _rows_ke_hoach():
    return [_dong("a1", "spammer1", 0, "CJW-UJK-A88AH xóa 88 rồi zán cam ah"),        # 1 bình luận
            _dong("a2", "spammer1", 1, "CJW-UJK-A88AH xóa 88 rồi zán cam ah", loai="trung"),
            *[_dong(f"c{i}", f"acc{i}", i, MA_AFF[i]) for i in (0, 2, 3)],              # chỉ mã
            _dong("c4", "acc4", 4, MA_AFF[4], loai="trung"),
            _dong("s", "acc5", 5, "AHS-WCM-DQN shopee", loai="spam", ly_do_loc="affiliate_dan_ma"),
            _dong("k", "khach", 6, "xin giá set túi trắng"),
            _dong("ib", "khach2", 7, "ib mình nhé", chu_de=S.CHU_DE_MUA),
            _dong("h", "HAPAS", 8, "Cảm ơn bạn nha", loai="thuong_hieu", cua_thuong_hieu=True)]


def test_ke_hoach_chi_ha_hop_le_va_trung():
    rows = _rows_ke_hoach()
    doi = {(x["ma"], x["cu"], x["ly_do"]) for x in S.ke_hoach(rows, ["HAPAS", "hapas"])}
    assert ("a1", "hop_le", "affiliate_dan_ma") in doi and ("a2", "trung", "affiliate_dan_ma") in doi
    # c4 (chữ kiểu cách + "dán vào") bắt ngay từng bình luận; c0, c2, c3 chỉ có mã — một mình chưa
    # đủ, nhưng ≥ 5 tài khoản có mã trong 48 giờ dưới một bài → hàng loạt.
    assert ("c4", "trung", "affiliate_dan_ma") in doi
    assert {m for m, _, ly in doi if ly == "affiliate_hang_loat"} == {"c0", "c2", "c3"}
    assert not {m for m, _, _ in doi} & {"s", "k", "ib", "h"}           # không nâng, không đụng khách
    r = S.bao_cao("hapas", len(rows), S.ke_hoach(rows), 3)
    chu = "\n".join(r)
    assert "hop_le → spam (affiliate_hang_loat): 3" in chu and "trung → spam" in chu
    assert "spammer1" not in chu and "acc0" not in chu and "tg-" in chu    # tác giả đã che
    assert S.che_tac_gia("User123") != S.che_tac_gia("user456")
    assert S.bao_cao("x", 0, [], 5)[-1].endswith("Không có dòng nào cần đổi.")
    # Mã của brand (bài minigame) không tính: chỉ còn 4 tài khoản có mã → không còn hàng loạt.
    doi = S.ke_hoach(rows, ["HAPAS"], {"tiktok:1": "Bình luận mã AHS-WCM-DQN nhận quà"})
    assert not [x for x in doi if x["ly_do"] == "affiliate_hang_loat"]


def test_bao_cao_tach_mau_hang_loat_khong_co_ma():
    """Hàng loạt mà KHÔNG có mã nối gạch (chữ kiểu cách + tên sàn) in riêng để đọc tay."""
    rows = [_dong(f"f{i}", f"acc{i}", i, "𝐱𝐞𝐦 𝐭𝐫𝐞̂𝐧 𝐬𝐡𝐨𝐩𝐞𝐞 𝐧𝐡𝐚") for i in range(4)] + \
           [_dong("c9", "acc9", 5, "KQX-77A-PLM")]
    doi = S.ke_hoach(rows)
    assert {x["ly_do"] for x in doi} == {"affiliate_hang_loat"} and len(doi) == 5
    chu = "\n".join(S.bao_cao("hapas", 5, doi, 2))
    assert "Mẫu (1/1" in chu and "CẦN ĐỌC TAY — hàng loạt không có mã nối gạch (2/4)" in chu


def _ket_noi_gia(monkeypatch, rows, **kw):
    lan: list[GiaCur] = []

    @contextlib.contextmanager
    def ket_noi():
        c = GiaCur(rows, [{"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"]}], **kw)
        lan.append(c)
        yield c
    monkeypatch.setattr(K, "ket_noi", ket_noi)
    monkeypatch.setenv("LANG_NGHE_DSN", "dbname=thu")
    return lan


def test_script_xem_truoc_chi_doc_ap_dung_co_sao_luu_va_hoan_tac(monkeypatch, capsys, tmp_path):
    rows = [_dong(f"c{i}", f"acc{i}", i, MA_AFF[i], chu_de=S.CHU_DE_MUA) for i in range(5)]
    lan = _ket_noi_gia(monkeypatch, rows)
    assert S.main([]) == 0
    out = capsys.readouterr().out
    assert "XEM TRƯỚC (chỉ đọc)" in out and "5 dòng sẽ đổi" in out
    assert lan[0].sql[0][0] == "SET TRANSACTION READ ONLY"                # câu đầu giao dịch
    assert not any(q.startswith("UPDATE") for q, _ in lan[0].sql)
    # --ap-dung bắt buộc --sao-luu.
    with pytest.raises(SystemExit):
        S.main(["--ap-dung"])
    tep = tmp_path / "loc_lai.json"
    assert S.main(["--ap-dung", "--sao-luu", str(tep), "--du-an", "hapas", "--mau", "0"]) == 0
    sua = [(q, ts) for q, ts in lan[-1].sql if q.startswith("UPDATE")]
    assert len(sua) == 5 and not any(q.startswith("SET") for q, _ in lan[-1].sql)
    assert all("loai = %s" in q and "cap_nhat_cuoi = now()" in q for q, _ in sua)
    assert {ts[0] for _, ts in sua} == {"affiliate_dan_ma", "affiliate_hang_loat"}
    assert "Đã ghi 5 dòng" in capsys.readouterr().out
    sl = json.loads(tep.read_text(encoding="utf-8"))
    assert sl["so_dong"] == 5 and {x["ma"] for x in sl["dong"]} == {f"c{i}" for i in range(5)}
    assert set(sl["dong"][0]) == {"du_an", "khoa_bai", "ma", "loai", "ly_do_loc", "sac_thai",
                                  "chu_de", "ly_do_moi"}                    # không nội dung / tên
    assert all(x["loai"] == "hop_le" and x["sac_thai"] == "Trung lập" and
               x["chu_de"] == S.CHU_DE_MUA for x in sl["dong"])
    # Không ghi đè tệp hoàn tác cũ — từ chối trước khi chạm kho.
    n = len(lan)
    assert S.main(["--ap-dung", "--sao-luu", str(tep)]) == 2 and len(lan) == n
    # Hoàn tác: một giao dịch, chỉ dòng còn đúng nhãn script đặt (c3 đã bị sửa sau → để nguyên).
    lan = _ket_noi_gia(monkeypatch, rows, da_sua_sau={"c3"})
    assert S.main(["--hoan-tac", str(tep)]) == 0
    hoan = [(q, ts) for q, ts in lan[0].sql if q.startswith("UPDATE")]
    assert len(lan) == 1 and len(hoan) == 5
    assert all("AND loai = 'spam' AND ly_do_loc = %s" in q for q, _ in hoan)
    assert hoan[0][1][:4] == ("hop_le", None, "Trung lập", S.CHU_DE_MUA)
    assert "Đã trả nhãn cũ cho 4/5 dòng" in capsys.readouterr().out
