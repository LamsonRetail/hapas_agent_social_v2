"""Spam affiliate trên KHO (16/10/2026): luật cấp bài trong `lang_nghe_db.ghi_binh_luan`, giữ nhãn
kho khi cào lại, và script lọc lại dữ liệu cũ `scripts/lang_nghe_loc_lai.py` (xem trước / ghi).
Kho GIẢ ghi lại câu SQL — không cần Postgres."""
from __future__ import annotations

import contextlib
import datetime
import sys
from pathlib import Path

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
            "ly_do_loc": None, "chu_de": None, **kw}


class GiaCur:
    """Một kết nối giả: SELECT trả `rows`, UPDATE đếm dòng theo số mã truyền vào."""

    def __init__(self, rows=(), du_an=()):
        self.rows, self.du_an, self.sql = list(rows), list(du_an), []
        self.rowcount = 0
        self._ra: list = []

    def execute(self, q, ts=()):
        self.sql.append((" ".join(q.split()), ts))
        if q.startswith("SELECT ma, ten, tu_khoa FROM du_an"):
            self._ra = self.du_an
        elif q.startswith("SELECT"):
            self._ra = self.rows
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
    c = GiaCur(rows)
    assert K._danh_dau_affiliate(c, "hapas", ["tiktok:1", None, "tiktok:1"]) == 5
    q, ts = c.sql[0]
    assert "khoa_bai = ANY(%s)" in q and "loai = 'hop_le' OR ly_do_loc = ANY(%s)" in q
    assert ts[1] == ["tiktok:1"] and set(ts[2]) == {"affiliate_dan_ma", "affiliate_hang_loat"}
    q, ts = c.sql[1]
    assert "ly_do_loc = 'affiliate_hang_loat'" in q and "sac_thai = NULL, chu_de = NULL" in q
    assert "cap_nhat_cuoi = now()" in q and q.endswith("AND loai = 'hop_le'")
    assert sorted(ts[2]) == [f"c{i}" for i in range(5)]                  # khách thật không đụng
    assert K._danh_dau_affiliate(GiaCur(rows[:4]), "hapas", ["tiktok:1"]) == 0
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


def test_ke_hoach_chi_ha_hop_le_va_trung():
    rows = [_dong("a1", "spammer1", 0, "CJW-UJK-A88AH xóa 88 rồi zán cam ah"),        # 1 bình luận
            _dong("a2", "spammer1", 1, "CJW-UJK-A88AH xóa 88 rồi zán cam ah", loai="trung"),
            *[_dong(f"c{i}", f"acc{i}", i, MA_AFF[i]) for i in (0, 2, 3)],              # chỉ mã
            _dong("c4", "acc4", 4, MA_AFF[4], loai="trung"),
            _dong("s", "acc5", 5, "AHS-WCM-DQN shopee", loai="spam", ly_do_loc="affiliate_dan_ma"),
            _dong("k", "khach", 6, "xin giá set túi trắng"),
            _dong("ib", "khach2", 7, "ib mình nhé", chu_de=S.CHU_DE_MUA),
            _dong("h", "HAPAS", 8, "AHS-WCM-DQN", loai="thuong_hieu", cua_thuong_hieu=True)]
    doi = {(x["ma"], x["cu"], x["ly_do"]) for x in S.ke_hoach(rows, ["HAPAS", "hapas"])}
    assert ("a1", "hop_le", "affiliate_dan_ma") in doi and ("a2", "trung", "affiliate_dan_ma") in doi
    # c4 (chữ kiểu cách + "dán vào") bắt ngay từng bình luận; c0, c2, c3 chỉ có mã — một mình chưa
    # đủ, nhưng ≥ 5 tài khoản có mã/chữ kiểu cách trong 48 giờ dưới một bài → hàng loạt.
    assert ("c4", "trung", "affiliate_dan_ma") in doi
    assert {m for m, _, ly in doi if ly == "affiliate_hang_loat"} == {"c0", "c2", "c3"}
    assert not {m for m, _, _ in doi} & {"s", "k", "ib", "h"}           # không nâng, không đụng khách
    r = S.bao_cao("hapas", len(rows), S.ke_hoach(rows), 3)
    chu = "\n".join(r)
    assert "hop_le → spam (affiliate_hang_loat): 3" in chu and "trung → spam" in chu
    assert "spammer1" not in chu and "acc0" not in chu and "tg-" in chu    # tác giả đã che
    assert S.che_tac_gia("User123") != S.che_tac_gia("user456")
    assert S.bao_cao("x", 0, [], 5)[-1].endswith("Không có dòng nào cần đổi.")


def test_script_xem_truoc_khong_ghi_ap_dung_ghi_mot_giao_dich(monkeypatch, capsys):
    rows = [_dong(f"c{i}", f"acc{i}", i, MA_AFF[i]) for i in range(5)]
    lan: list[GiaCur] = []

    @contextlib.contextmanager
    def ket_noi():
        c = GiaCur(rows, [{"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"]}])
        lan.append(c)
        yield c
    monkeypatch.setattr(K, "ket_noi", ket_noi)
    monkeypatch.setenv("LANG_NGHE_DSN", "dbname=thu")
    assert S.main([]) == 0
    out = capsys.readouterr().out
    assert "XEM TRƯỚC" in out and "5 dòng sẽ đổi" in out
    assert not any(q.startswith("UPDATE") for q, _ in lan[0].sql)
    assert S.main(["--ap-dung", "--du-an", "hapas", "--mau", "0"]) == 0
    sua = [(q, ts) for q, ts in lan[1].sql if q.startswith("UPDATE")]
    assert len(lan) == 2 and len(sua) == 5                                # một kết nối = một giao dịch
    assert all("loai = %s" in q and "cap_nhat_cuoi = now()" in q for q, _ in sua)
    assert {ts[0] for _, ts in sua} == {"affiliate_dan_ma", "affiliate_hang_loat"}
    assert "Đã ghi 5 dòng" in capsys.readouterr().out
