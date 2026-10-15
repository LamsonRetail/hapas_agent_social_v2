"""Nhịp lịch quét tự động của Mark (`quet_tu_dong.py`, 15/10/2026).

Kho GIẢ trong bộ nhớ thay `lang_nghe_db` (cùng tên hàm), đồng hồ cố định, `theo_doi.tao_luot` giả
— không Postgres, không Apify, không mạng. Kho giả mô phỏng `FOR UPDATE SKIP LOCKED`: dòng đang bị
một "tiến trình" nhận thì tiến trình kia bỏ qua."""
from __future__ import annotations

import datetime as dt

import pytest

import lang_nghe_db as K
import quet_tu_dong as QT
import theo_doi

VN = dt.timezone(dt.timedelta(hours=7))


def vn(*a):
    return dt.datetime(*a, tzinfo=VN)


GIO_2 = {"moi_gio": 2, "tu": "07:00", "den": "23:00", "thu": []}
CHIN_GIO = vn(2026, 10, 15, 9)


def _lich(i=1, kieu="moi_n_gio", ch=None, ke=CHIN_GIO, bat=True, du_an="hapas",
          moi_nguon=False, kq=None):
    return {"id": i, "du_an": du_an, "ten": f"lịch {i}", "kieu": kieu, "cau_hinh": ch or GIO_2,
            "bat": bat, "quet_moi_nguon": moi_nguon, "lan_chay_ke": ke, "lan_chay_cuoi": None,
            "ket_qua_cuoi": kq, "so_lan_chay": 0}


class GiaKhoLich:
    def __init__(self, *lich):
        self.lich = {x["id"]: dict(x) for x in lich}
        self.khoa: set[int] = set()
        self.hong = False
        self.trong_giao_dich = None        # gọi khi đang giữ khoá dòng (mô phỏng tiến trình 2)

    def cai(self, mp):
        for ten in ("lich_dang_bat", "doc_lich", "nhan_lich_den_han", "ghi_ket_qua_lich"):
            mp.setattr(K, ten, getattr(self, ten))
        return self

    def lich_dang_bat(self):
        if self.hong:
            raise K.LoiKho("không nối được kho lắng nghe (OperationalError)")
        return [dict(x) for x in self.lich.values() if x["bat"]]

    def doc_lich(self, lid):
        return dict(self.lich[lid]) if lid in self.lich else None

    def nhan_lich_den_han(self, bay_gio, quyet, toi_da=20):
        ds = sorted((x for x in self.lich.values() if x["bat"] and x["lan_chay_ke"] is not None
                     and x["lan_chay_ke"] <= bay_gio and x["id"] not in self.khoa),
                    key=lambda x: (x["lan_chay_ke"], x["id"]))[:toi_da]
        ids = {x["id"] for x in ds}
        self.khoa |= ids
        ra = []
        try:
            if self.trong_giao_dich:
                f, self.trong_giao_dich = self.trong_giao_dich, None
                f()
            for x in ds:
                cu = dict(x)
                q = quyet(dict(x))
                x["lan_chay_ke"] = q.get("lan_chay_ke")
                if q.get("lan_chay_cuoi") is not None:
                    x["lan_chay_cuoi"] = q["lan_chay_cuoi"]
                if q.get("ket_qua_cuoi") is not None:
                    x["ket_qua_cuoi"] = q["ket_qua_cuoi"]
                ra.append((cu, q))
        finally:
            self.khoa -= ids
        return ra

    def ghi_ket_qua_lich(self, lid, ket_qua, *, lan_chay_cuoi=None, tang_so_lan=False,
                         chi_khi_ma_viec=None):
        x = self.lich.get(lid)
        cu = x.get("ket_qua_cuoi") or {} if x else {}
        if not x or (chi_khi_ma_viec and chi_khi_ma_viec not in (cu.get("ma_viec"),
                                                                  cu.get("viec_cho"))):
            return False
        x["ket_qua_cuoi"] = ket_qua
        if lan_chay_cuoi is not None:
            x["lan_chay_cuoi"] = lan_chay_cuoi
        x["so_lan_chay"] += 1 if tang_so_lan else 0
        return True


@pytest.fixture
def mt(monkeypatch):
    """Tiến trình giữ quyền chủ việc nền, công tắc Soi tài khoản bật, không nơi nhận cảnh báo."""
    import lsr_platform
    monkeypatch.setattr(QT, "_co_quyen", lambda: True)
    monkeypatch.setattr(QT, "_duoc_chay", lambda: (True, ""))
    monkeypatch.setattr(QT, "_danh_ba_da_doc", lambda: True)
    monkeypatch.delenv("MARK_LICH_QUET_BAO_LOI", raising=False)
    monkeypatch.delenv("MARK_LICH_QUET", raising=False)
    gui: list[tuple] = []
    monkeypatch.setattr(QT, "_gui", lambda dich, van, uid: gui.append((dich, van, uid)))
    monkeypatch.gui = gui
    trace: list[tuple] = []
    monkeypatch.setattr(lsr_platform, "bao_luot", lambda *a, **k: trace.append((a, k)))
    monkeypatch.trace = trace
    return monkeypatch


def _tao_luot(mp, kho, kq=None):
    """`theo_doi.tao_luot` giả: ghi lời gọi + mốc kế của lịch LÚC tạo việc (phải đã dời)."""
    goi = []

    def tao(ma, *, moi_nguon=False, lich=None):
        goi.append({"ma": ma, "moi_nguon": moi_nguon, "lich": lich,
                    "ke_luc_tao": kho.lich[lich["id"]]["lan_chay_ke"]})
        return kq or {"ok": True, "ma_viec": f"t{len(goi)}", "cau": "Đã nhận lượt theo dõi.",
                      "uoc_usd": 0.4, "so_nguon": 3}
    mp.setattr(theo_doi, "tao_luot", tao)
    return goi


# ───────────────────────────── chạy đúng mốc, không chạy hai lần ─────────────────────────────
def test_toi_moc_ghi_moc_ke_truoc_roi_moi_tao_viec(mt):
    kho = GiaKhoLich(_lich()).cai(mt)
    goi = _tao_luot(mt, kho)
    ra = QT.mot_nhip(vn(2026, 10, 15, 9, 0, 20))
    assert ra == [{"id": 1, "hanh_dong": "da_tao", "ma_loi": None, "ma_viec": "t1"}]
    (g,) = goi
    assert g["ma"] == "hapas" and g["lich"] == {"id": 1, "moc": "2026-10-15T09:00:00+07:00"}
    assert g["ke_luc_tao"] == vn(2026, 10, 15, 11)        # mốc kế đã dời TRƯỚC khi tạo việc
    x = kho.lich[1]
    assert x["ket_qua_cuoi"]["trang_thai"] == "da_tao" and x["ket_qua_cuoi"]["ma_viec"] == "t1"
    assert x["so_lan_chay"] == 1 and x["lan_chay_cuoi"] == vn(2026, 10, 15, 9, 0, 20)
    # nhịp sau (cùng phút): không chạy lại
    assert QT.mot_nhip(vn(2026, 10, 15, 9, 0, 50)) == [] and len(goi) == 1


def test_chua_toi_han_hoac_lich_tat_khong_lam_gi(mt):
    kho = GiaKhoLich(_lich(ke=vn(2026, 10, 15, 11)), _lich(2, bat=False)).cai(mt)
    goi = _tao_luot(mt, kho)
    assert QT.mot_nhip(vn(2026, 10, 15, 9, 30)) == [] and goi == []


def test_hai_tien_trinh_mot_mot_moc_chi_mot_ban_nhan(mt):
    """Tiến trình 2 nhịp đúng lúc tiến trình 1 đang giữ khoá dòng: bỏ qua (SKIP LOCKED); nhịp
    ngay sau khi tiến trình 1 commit: mốc kế đã dời nên cũng không chạy."""
    kho = GiaKhoLich(_lich()).cai(mt)
    goi = _tao_luot(mt, kho)
    luc = vn(2026, 10, 15, 9, 0, 5)
    tt2: list = []
    kho.trong_giao_dich = lambda: tt2.append(QT.mot_nhip(luc))
    QT.mot_nhip(luc)
    assert tt2 == [[]] and len(goi) == 1
    assert QT.mot_nhip(luc) == [] and len(goi) == 1


def test_chet_giua_luc_tao_viec_khong_chay_lai_moc(mt):
    """Mốc kế commit TRƯỚC: tiến trình chết ngay sau khi nhận lịch (trước/khi tạo việc) thì lỡ
    đúng một lượt, không chạy lại mốc đó."""
    kho = GiaKhoLich(_lich()).cai(mt)

    def chet(*a):
        raise RuntimeError("tiến trình chết")
    goc = QT._chay
    mt.setattr(QT, "_chay", chet)
    goi = _tao_luot(mt, kho)
    assert QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5)) == []        # không ném ra ngoài
    assert kho.lich[1]["lan_chay_ke"] == vn(2026, 10, 15, 11)
    mt.setattr(QT, "_chay", goc)
    assert QT.mot_nhip(vn(2026, 10, 15, 9, 1)) == [] and goi == []


def test_hoi_cong_tac_loi_thi_ghi_loi_co_ly_do(mt):
    """Review 15/10 (L2): hỏi công tắc ném lỗi nằm TRONG try — lịch ghi "lỗi" có lý do, không
    thoát ra nhịp mà không để lại dấu vết."""
    kho = GiaKhoLich(_lich()).cai(mt)

    def no():
        raise RuntimeError("danh bạ hỏng")
    mt.setattr(QT, "_duoc_chay", no)
    goi = _tao_luot(mt, kho)
    ra = QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))
    assert ra == [{"id": 1, "hanh_dong": "loi", "ma_loi": "loi", "ma_viec": None}] and goi == []
    assert "RuntimeError" in kho.lich[1]["ket_qua_cuoi"]["ly_do"]


def test_chua_doc_duoc_danh_ba_platform_thi_chua_chay(mt):
    """Review 15/10 (L3): khởi động nguội chưa đọc được công tắc thì KHÔNG chạy (không mở vì không
    biết); mốc chưa bị nhận nên đọc được danh bạ trong 30 phút thì vẫn chạy bù."""
    kho = GiaKhoLich(_lich()).cai(mt)
    goi = _tao_luot(mt, kho)
    mt.setattr(QT, "_danh_ba_da_doc", lambda: False)
    assert QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5)) == [] and goi == []
    assert kho.lich[1]["lan_chay_ke"] == vn(2026, 10, 15, 9)
    mt.setattr(QT, "_danh_ba_da_doc", lambda: True)
    QT.mot_nhip(vn(2026, 10, 15, 9, 10))
    assert [g["lich"]["moc"] for g in goi] == ["2026-10-15T09:00:00+07:00"]


def test_danh_ba_da_doc_theo_bo_nho_lsr_policy(monkeypatch):
    import lsr_policy
    monkeypatch.setitem(lsr_policy._nho_nl, "bat", None)
    monkeypatch.setitem(lsr_policy._nho_nl, "luc", 0.0)
    monkeypatch.setattr(lsr_policy, "_nang_luc_tu_danh_ba", lambda: None)      # platform im
    assert QT._danh_ba_da_doc() is False
    monkeypatch.setattr(lsr_policy, "_nang_luc_tu_danh_ba", lambda: {"soi_tai_khoan"})
    assert QT._danh_ba_da_doc() is True
    monkeypatch.setattr(lsr_policy, "_nang_luc_tu_danh_ba", lambda: None)      # mất mạng sau đó
    monkeypatch.setitem(lsr_policy._nho_nl, "luc", 0.0)
    assert QT._danh_ba_da_doc() is True                    # đã đọc được một lần: dùng bản nhớ


def test_khong_giu_quyen_chu_viec_nen_thi_khong_nhan_lich(mt):
    kho = GiaKhoLich(_lich()).cai(mt)
    goi = _tao_luot(mt, kho)
    mt.setattr(QT, "_co_quyen", lambda: False)
    assert QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5)) == [] and goi == []
    assert kho.lich[1]["lan_chay_ke"] == vn(2026, 10, 15, 9)   # để tiến trình chủ nhận


def test_tat_bang_env(mt):
    kho = GiaKhoLich(_lich()).cai(mt)
    goi = _tao_luot(mt, kho)
    mt.setenv("MARK_LICH_QUET", "0")
    assert QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5)) == [] and goi == []
    assert "tắt" in QT.khoi_dong()


# ───────────────────────────── mốc lỡ ─────────────────────────────
def test_lo_moc_duoi_30_phut_chay_bu_mot_lan(mt):
    ch = {"moi_gio": 1, "tu": "00:00", "den": "23:59", "thu": []}
    kho = GiaKhoLich(_lich(ch=ch, ke=vn(2026, 10, 15, 10))).cai(mt)
    goi = _tao_luot(mt, kho)
    QT.mot_nhip(vn(2026, 10, 15, 12, 10))               # Mark tắt 10:00 → 12:10
    assert [g["lich"]["moc"] for g in goi] == ["2026-10-15T12:00:00+07:00"]
    assert kho.lich[1]["lan_chay_ke"] == vn(2026, 10, 15, 13)


def test_lo_moc_qua_30_phut_thi_bo_va_ghi_ly_do(mt):
    kho = GiaKhoLich(_lich()).cai(mt)
    goi = _tao_luot(mt, kho)
    ra = QT.mot_nhip(vn(2026, 10, 15, 9, 45))
    assert ra == [{"id": 1, "hanh_dong": "lo", "ma_loi": "lo"}] and goi == []
    kq = kho.lich[1]["ket_qua_cuoi"]
    assert kq["trang_thai"] == "bo_qua" and "lỡ mốc 15/10 09:00" in kq["ly_do"]
    assert kho.lich[1]["lan_chay_ke"] == vn(2026, 10, 15, 11)


# ───────────────────────────── bỏ qua có lý do ─────────────────────────────
def test_luot_truoc_con_chay_thi_bo_qua_khong_canh_bao(mt):
    mt.setenv("MARK_LICH_QUET_BAO_LOI", "oc_nhomvanhanh")
    kho = GiaKhoLich(_lich()).cai(mt)
    _tao_luot(mt, kho, {"ok": False, "ma_loi": "dang_chay", "ma_viec": "t9",
                        "cau": "Đã có việc theo dõi 'hapas' chưa xong (mã t9)."})
    ra = QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))
    assert ra[0]["hanh_dong"] == "bo_qua" and ra[0]["ma_loi"] == "dang_chay"
    kq = kho.lich[1]["ket_qua_cuoi"]
    assert kq["ma_viec_cu"] == "t9" and "chưa xong" in kq["ly_do"]
    assert kho.lich[1]["so_lan_chay"] == 0 and mt.gui == []


def test_cong_tac_console_tat_thi_khong_tao_viec(mt):
    kho = GiaKhoLich(_lich()).cai(mt)
    goi = _tao_luot(mt, kho)
    mt.setattr(QT, "_duoc_chay", lambda: (False, "'soi_tai_khoan' đang TẮT ở khối Năng lực"))
    QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))
    assert goi == [] and kho.lich[1]["ket_qua_cuoi"]["ma_loi"] == "nang_luc_tat"


def test_het_ngan_sach_canh_bao_mot_lan_moi_ngay(mt):
    mt.setenv("MARK_LICH_QUET_BAO_LOI", "oc_nhomvanhanh")
    ch = {"moi_gio": 1, "tu": "00:00", "den": "23:59", "thu": []}
    kho = GiaKhoLich(_lich(ch=ch, ke=vn(2026, 10, 15, 9))).cai(mt)
    _tao_luot(mt, kho, {"ok": False, "ma_loi": "het_ngan_sach",
                        "cau": "hết ngân sách tháng của dự án (5,00/5,00 USD)"})
    QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))
    QT.mot_nhip(vn(2026, 10, 15, 10, 0, 5))
    assert len(mt.gui) == 1
    dich, van, uid = mt.gui[0]
    assert dich == "oc_nhomvanhanh" and "HẾT NGÂN SÁCH" in van and "lich-quet?du_an=hapas" in van
    assert uid == "lichq-1-het_ngan_sach-20261015"
    assert kho.lich[1]["ket_qua_cuoi"]["canh_bao"] == {"het_ngan_sach": "2026-10-15"}
    kho.lich[1]["lan_chay_ke"] = vn(2026, 10, 16, 9)
    QT.mot_nhip(vn(2026, 10, 16, 9, 0, 5))                 # ngày mới: báo lại một lần
    assert len(mt.gui) == 2


def test_khong_co_noi_nhan_thi_chi_ghi_ket_qua(mt):
    kho = GiaKhoLich(_lich()).cai(mt)
    _tao_luot(mt, kho, {"ok": False, "ma_loi": "tu_choi", "cau": "Hàng đợi quét nền đã đủ 3 việc."})
    QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))
    kq = kho.lich[1]["ket_qua_cuoi"]
    assert kq["trang_thai"] == "loi" and "canh_bao" not in kq and mt.gui == []


# ───────────────────────────── chiến dịch ─────────────────────────────
CD = {"tu_luc": "2026-10-15T08:00", "den_luc": "2026-10-15T12:00", "moi_phut": 60}


def test_chien_dich_uu_tien_lich_thuong_nhuong(mt):
    kho = GiaKhoLich(_lich(1), _lich(2, kieu="chien_dich", ch=CD, ke=vn(2026, 10, 15, 9),
                                     moi_nguon=True)).cai(mt)
    goi = _tao_luot(mt, kho)
    ra = {x["id"]: x for x in QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))}
    assert ra[1]["hanh_dong"] == "nhuong" and ra[2]["hanh_dong"] == "da_tao"
    assert [(g["lich"]["id"], g["moi_nguon"]) for g in goi] == [(2, True)]
    assert "nhường chiến dịch #2" in kho.lich[1]["ket_qua_cuoi"]["ly_do"]
    # dự án khác không bị ảnh hưởng
    kho.lich[3] = _lich(3, du_an="khac", ke=vn(2026, 10, 15, 11))
    QT.mot_nhip(vn(2026, 10, 15, 11, 0, 5))
    assert [g["lich"]["id"] for g in goi] == [2, 2, 3]


def test_chien_dich_moc_cuoi_roi_tu_dung(mt):
    kho = GiaKhoLich(_lich(2, kieu="chien_dich", ch=CD, ke=vn(2026, 10, 15, 12))).cai(mt)
    goi = _tao_luot(mt, kho)
    QT.mot_nhip(vn(2026, 10, 15, 12, 0, 5))
    assert len(goi) == 1 and kho.lich[2]["lan_chay_ke"] is None
    assert QT.mot_nhip(vn(2026, 10, 16, 12)) == []


def test_cau_hinh_hong_dung_lich_cho_sua(mt, monkeypatch):
    kho = GiaKhoLich(_lich()).cai(mt)
    _tao_luot(mt, kho)

    def hong(*a):
        raise ValueError("rác")
    monkeypatch.setattr(QT.LQ, "quyet_dinh", hong)
    ra = QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))
    assert ra[0]["hanh_dong"] == "loi" and kho.lich[1]["lan_chay_ke"] is None
    assert "cấu hình lịch hỏng" in kho.lich[1]["ket_qua_cuoi"]["ly_do"]


@pytest.mark.parametrize("ch", [
    {"tu_luc": "2026-10-15T08:00", "den_luc": "2026-10-15T12:00", "moi_phut": 1},     # mỗi phút
    {"tu_luc": "2026-10-15T08:00", "den_luc": "2026-10-15T12:00", "moi_phut": 20000},
    {"tu_luc": "2026-10-15T08:00", "den_luc": "2027-03-01T12:00", "moi_phut": 60},    # > 92 ngày
    {"tu_luc": "2026-10-15T08:00", "den_luc": "2026-10-15T12:00", "moi_phut": "rác"},
    {"tu_luc": "2026-10-15T08:00", "den_luc": "2026-10-15T12:00", "moi_phut": True},
])
def test_chien_dich_ghi_ngoai_dashboard_sai_gioi_han_thi_ngu(mt, ch):
    """Review 15/10 (M3): dòng ghi thẳng bằng psql với moi_phut = 1 phải NGỦ (mốc kế NULL, ghi lỗi),
    không chạy mỗi phút."""
    kho = GiaKhoLich(_lich(kieu="chien_dich", ch=ch)).cai(mt)
    goi = _tao_luot(mt, kho)
    ra = QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))
    assert ra[0]["hanh_dong"] == "loi" and goi == [] and kho.lich[1]["lan_chay_ke"] is None
    assert "không hợp lệ" in kho.lich[1]["ket_qua_cuoi"]["ly_do"]
    assert QT.mot_nhip(vn(2026, 10, 15, 9, 1, 5)) == []


def test_kho_loi_nhip_khong_nem(mt):
    kho = GiaKhoLich(_lich()).cai(mt)
    kho.hong = True
    assert QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5)) == []


# ───────────────────────────── việc xong ─────────────────────────────
def test_ket_thuc_viec_ghi_trang_thai_cuoi_va_canh_bao_loi(mt):
    mt.setenv("MARK_LICH_QUET_BAO_LOI", "ou_chuagent")
    kho = GiaKhoLich(_lich(kq={"trang_thai": "da_tao", "ma_viec": "t5"})).cai(mt)
    QT.ket_thuc_viec(1, "t4", 11, "loi", "lỗi cũ")             # việc cũ: không đè kết quả mới
    assert kho.lich[1]["ket_qua_cuoi"]["trang_thai"] == "da_tao" and mt.gui == []
    QT.ket_thuc_viec(1, "t5", 12, "xong_mot_phan", "...")
    assert kho.lich[1]["ket_qua_cuoi"]["trang_thai"] == "mot_phan"
    assert kho.lich[1]["ket_qua_cuoi"]["luot_id"] == 12
    kho.lich[1]["ket_qua_cuoi"] = {"trang_thai": "da_tao", "ma_viec": "t6"}
    QT.ket_thuc_viec(1, "t6", 13, "loi", "Theo dõi HAPAS (t6) dừng vì lỗi: KeyError")
    kq = kho.lich[1]["ket_qua_cuoi"]
    assert kq["trang_thai"] == "loi" and "KeyError" in kq["ly_do"]
    assert len(mt.gui) == 1 and mt.gui[0][0] == "ou_chuagent" and "LỖI" in mt.gui[0][1]
    QT.ket_thuc_viec(99, "t1", 1, "xong", "")                 # lịch đã xoá: im lặng


def test_luot_bi_bo_vi_viec_truoc_con_chay_van_nhan_ket_qua_cuoi_cua_viec_do(mt):
    """Review 15/10 (L1): 09:00 giao t1; 11:00 bị bỏ vì t1 còn chạy (ghi đè kết quả); t1 lỗi lúc
    11:20 — kết quả cuối + cảnh báo lỗi của t1 vẫn về lịch (qua `viec_cho`), không mất."""
    mt.setenv("MARK_LICH_QUET_BAO_LOI", "oc_vanhanh")
    kho = GiaKhoLich(_lich()).cai(mt)
    _tao_luot(mt, kho)
    QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))
    assert kho.lich[1]["ket_qua_cuoi"]["viec_cho"] == "t1"
    _tao_luot(mt, kho, {"ok": False, "ma_loi": "dang_chay", "ma_viec": "t1",
                        "cau": "Đã có việc theo dõi 'hapas' chưa xong (mã t1)."})
    QT.mot_nhip(vn(2026, 10, 15, 11, 0, 5))
    kq = kho.lich[1]["ket_qua_cuoi"]
    assert kq["trang_thai"] == "bo_qua" and kq["viec_cho"] == "t1" and kq["ma_viec_cu"] == "t1"
    QT.ket_thuc_viec(1, "t1", 7, "loi", "Theo dõi HAPAS (t1) dừng vì lỗi: KeyError",
                     chi_phi_usd=0.42, du_an="hapas", moc="2026-10-15T09:00:00+07:00")
    kq = kho.lich[1]["ket_qua_cuoi"]
    assert kq["trang_thai"] == "bo_qua"                     # kết quả mới nhất vẫn là lượt bị bỏ
    assert kq["viec_cuoi"]["ma_viec"] == "t1" and kq["viec_cuoi"]["trang_thai"] == "loi"
    assert kq["viec_cuoi"]["chi_phi_usd"] == 0.42 and "viec_cho" not in kq
    assert len(mt.gui) == 1 and "LỖI" in mt.gui[0][1] and "KeyError" in mt.gui[0][1]
    # báo lần hai (việc đã báo xong rồi): không khớp nữa, không ghi đè
    QT.ket_thuc_viec(1, "t1", 7, "xong", "")
    assert kho.lich[1]["ket_qua_cuoi"]["viec_cuoi"]["trang_thai"] == "loi"


def test_moi_luot_bao_platform_bang_trace(mt):
    """Governance: lượt theo lịch dashboard không qua hàng đợi job platform — mỗi lượt (giao
    việc, bỏ qua, xong + chi phí thật) báo bằng trace có sẵn `lsr_platform.bao_luot`."""
    import json
    ch = {"moi_gio": 1, "tu": "00:00", "den": "23:59", "thu": []}
    kho = GiaKhoLich(_lich(ch=ch)).cai(mt)
    _tao_luot(mt, kho)
    QT.mot_nhip(vn(2026, 10, 15, 9, 0, 5))                      # giao t1
    kho.lich[1]["lan_chay_ke"] = vn(2026, 10, 15, 9)
    QT.mot_nhip(vn(2026, 10, 15, 9, 45))                        # lỡ mốc → bỏ qua
    QT.ket_thuc_viec(1, "t1", 8, "xong", "", chi_phi_usd=0.1234, du_an="hapas",
                     moc="2026-10-15T09:00:00+07:00")
    ds = [(a[0], json.loads(a[2]), k) for a, k in mt.trace]
    assert [d["ket_qua"] for _, d, _ in ds] == ["da_tao", "bo_qua", "xong"]
    rid, d, k = ds[0]
    assert rid == "lich-1-202610150900" and k["ok"] is True
    assert d["lich_id"] == 1 and d["du_an"] == "hapas" and d["ma_viec"] == "t1"
    assert d["moc"] == "2026-10-15T09:00:00+07:00" and d["chi_phi_usd"] == 0
    assert ds[1][1]["ma_loi"] == "lo"
    rid, d, _ = ds[2]
    assert rid == "lich-1-t1-xong" and d["chi_phi_usd"] == 0.1234 and d["luot_id"] == 8


def test_dich_canh_bao_chi_nhan_ma_hop_le(monkeypatch):
    for gia, ok in (("oc_abc123", True), ("ou_xyz", True), ("lark:cli_a1:oc_abc", True),
                    ("hapas@x.vn", False), ("oc_a b", False), ("", False)):
        monkeypatch.setenv("MARK_LICH_QUET_BAO_LOI", gia)
        assert bool(QT._dich_canh_bao()) is ok, gia


# ───────────────────────────── SQL phía Mark (lang_nghe_db) ─────────────────────────────
@pytest.fixture
def sql(monkeypatch):
    """`K.ket_noi` giả: ghi mọi câu SQL, trả dòng theo mẫu; "COMMIT" ghi khi giao dịch xong."""
    import contextlib
    import re
    lenh: list = []
    tra: dict = {}

    class Cur:
        def __init__(self, d):
            self.d = d

        def fetchone(self):
            return self.d[0] if self.d else None

        def fetchall(self):
            return list(self.d)

    class Conn:
        def execute(self, s, ts=None):
            lenh.append((s, tuple(ts or ())))
            return Cur(next((d for m, d in tra.items() if re.search(m, s)), []))

    @contextlib.contextmanager
    def ket_noi():
        yield Conn()
        lenh.append(("COMMIT", ()))
    monkeypatch.setattr(K, "ket_noi", ket_noi)
    return lenh, tra


def test_nhan_lich_khoa_skip_locked_va_ghi_moc_ke_truoc_commit(sql):
    lenh, tra = sql
    tra[r"FOR UPDATE SKIP LOCKED"] = [_lich()]
    luc, ke = vn(2026, 10, 15, 9, 0, 5), vn(2026, 10, 15, 11)
    ra = K.nhan_lich_den_han(luc, lambda r: {"lan_chay_ke": ke, "hanh_dong": "chay"})
    assert [q["hanh_dong"] for _, q in ra] == ["chay"]
    s0, ts0 = lenh[0]
    assert "WHERE bat AND lan_chay_ke IS NOT NULL AND lan_chay_ke <= %s" in s0 and ts0 == (luc, 20)
    s1, ts1 = lenh[1]
    assert s1.startswith("UPDATE lich_quet SET lan_chay_ke = %s") and ts1 == (ke, None, None, 1)
    assert lenh[2][0] == "COMMIT" and len(lenh) == 3      # mốc kế commit TRƯỚC khi tạo việc


def test_ghi_ket_qua_lich_chi_de_dung_viec_va_mo_luot_kem_lich(sql):
    lenh, tra = sql
    K.ghi_ket_qua_lich(4, {"trang_thai": "xong"}, chi_khi_ma_viec="t5")
    s, ts = lenh[0]
    # khớp việc của kết quả hiện tại HOẶC việc còn chờ báo xong (`viec_cho`, review 15/10 L1)
    assert s.endswith("AND (ket_qua_cuoi->>'ma_viec' = %s OR ket_qua_cuoi->>'viec_cho' = %s) "
                      "RETURNING id") and ts[-2:] == ("t5", "t5")
    tra[r"RETURNING id"] = [{"id": 31}]
    assert K.mo_luot("hapas", "theo_doi", ma_viec="t5", lich_id=4) == 31
    ins = next(s for s, _ in lenh if s.startswith("INSERT INTO luot_quet"))
    assert "(SELECT id FROM lich_quet WHERE id = %s)" in ins      # lịch xoá giữa chừng -> NULL
    lenh.clear()
    K.mo_luot("hapas", "theo_doi", ma_viec="t6")
    ins = next(s for s, _ in lenh if s.startswith("INSERT INTO luot_quet"))
    assert "lich_id" not in ins                                   # gõ tay: như trước


def test_run_py_khoi_dong_nhip_lich_quet():
    from pathlib import Path
    run = (Path(__file__).resolve().parents[1] / "run.py").read_text(encoding="utf-8")
    assert run.index("viec_nen.khoi_dong()") < run.index("quet_tu_dong.khoi_dong()")
