"""Canh theo dõi tiến độ (tien_do.py): tool `tra_tien_do` + nhắc hằng ngày vào nhóm.

Chủ agent chốt 07/10/2026: 08:30 giờ VN mỗi ngày, chỉ việc chưa xong mà quá hạn hoặc tới hạn
trong 3 ngày; chỉ @nhắc PIC việc QUÁ HẠN; thiếu hạn/PIC chỉ đếm; không có gì thì không gửi;
tin do CODE soạn. Lark giả hoàn toàn (`lark_client.call` / `send_text`), không mạng.

Cột giả chép cấu trúc Base CHECKLIST DA 20.10 (đọc 06/10/2026): TRẠNG THÁI có lựa chọn mang
khoảng trắng cuối ("ĐANG LÀM ", "CHỜ DUYỆT "), NHÓM có bản trùng "MEDIA ".
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib

import pytest

import bang_tool as BT
import lark_client
import lsr_policy
import tien_do as T

GOC = pathlib.Path(__file__).resolve().parent.parent
VN = datetime.timezone(datetime.timedelta(hours=7))
APP, BANG = "SBfNb16GDaDVS5s8rpol8EjQgSg", "tbluIfPgSyOVIAg2"
CHAT = "oc_" + "a" * 32               # dài đúng như mã nhóm Lark thật (35 ký tự)
HOM_NAY = datetime.date(2026, 10, 7)  # Thứ Tư


def ms(y, m, d, h=0):
    return int(datetime.datetime(y, m, d, h, tzinfo=VN).timestamp() * 1000)


def _cot(ten, kieu):
    return {"field_name": ten, "type": kieu, "field_id": "fld" + str(abs(hash(ten)))[:8]}


COT = [_cot("HẠNG MỤC CV", 1), _cot("NHÓM", 3), _cot("PIC", 11), _cot("DEADLINE", 5),
       _cot("TRẠNG THÁI", 3), _cot("KẾT QUẢ CẦN ĐẠT", 1), _cot("Owner", 1003)]


def dong(rid, ten, nhom="MEDIA ", pic=None, han=None, tt=None):
    f = {"HẠNG MỤC CV": [{"text": ten, "type": "text"}] if ten else None, "NHÓM": nhom}
    if pic:
        f["PIC"] = [{"id": pic[0], "name": pic[1], "en_name": pic[1]}]
    if han is not None:
        f["DEADLINE"] = han
    if tt is not None:
        f["TRẠNG THÁI"] = tt
    return {"record_id": rid, "fields": f}


LINH = ("ou_linh", "Linh Ngọc - Booking KOC/KOL Leader")
AN = ("ou_an", "Trần An")
HA = ("ou_ha", "Nguyễn Hà")


def dong_mau():
    return [
        dong("r1", "Gửi brief KOC", "BOOKING", LINH, ms(2026, 10, 5), "ĐANG LÀM "),     # quá 2
        dong("r2", "Duyệt list KOC", "BOOKING", LINH, ms(2026, 10, 6), "CẦN LÀM"),      # quá 1
        dong("r3", "Quay teaser", "MEDIA ", AN, ms(2026, 10, 7), "CHỜ DUYỆT "),         # hôm nay
        dong("r4", "Dựng video", "MEDIA ", AN, ms(2026, 10, 10), None),                 # còn 3
        dong("r5", "In POSM", "VM", HA, ms(2026, 10, 11), "CẦN LÀM"),                   # còn 4 → ngoài
        dong("r6", "Viết caption", "CONTENT", HA, ms(2026, 10, 1), "ĐÃ XONG"),          # xong
        dong("r7", "Chốt giá", "KẾ HOẠCH", HA, ms(2026, 10, 2), "cancel  "),            # cancel
        dong("r8", "Thuê địa điểm", "EVENT ", None, ms(2026, 10, 3), "CẦN LÀM"),        # thiếu PIC
        dong("r9", "Mua quà tặng", "STORE - HỘP NHẠC", HA, None, "CẦN LÀM"),            # thiếu hạn
        dong("r10", "", None, None, None, None),                                        # dòng trống
        dong("r11", "Đặt OOH", "OOH", HA, ms(2026, 9, 30), "đã xong"),                  # xong (thường)
        dong("r12", "Đặt mẫu túi", "SBD", LINH, ms(2026, 9, 1), ""),                    # quá 36 → lâu
        dong("r13", "Thiết kế POSM", "VM ", None, ms(2026, 9, 22), None),               # quá 15 → lâu
        dong("r14", "Book thợ ảnh", "MEDIA ", None, ms(2026, 10, 9), "CẦN LÀM"),        # sắp hạn, thiếu PIC
    ]


@pytest.fixture(autouse=True)
def moi_truong(monkeypatch, tmp_path):
    for k in ("MARK_TIEN_DO_BASE_URL", "MARK_TIEN_DO_APP_TOKEN", "MARK_TIEN_DO_TABLE_ID",
              "MARK_TIEN_DO_TEN", "MARK_BASE_VIEC_URL", "MARK_BASE_VIEC_APP_TOKEN",
              "MARK_BASE_VIEC_TABLE_ID", "MARK_BASE_VIEC_TEN", "MARK_NHAC_TIEN_DO_CHAT",
              "MARK_NHAC_TIEN_DO_GIO", "MARK_NHAC_TIEN_DO_QUA_HAN_TOI_DA",
              "AGENT_BOSS_OPEN_ID", "STEVEN_BOSS_OPEN_ID", "MARK_NHAC_TIEN_DO_BAO_LOI"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(T, "_SO", tmp_path / ".tokens" / "nhac_tien_do.json")
    monkeypatch.setattr(T, "_trang_thai", {"thu_lai_sau": 0.0, "da_bao": set()})


class LarkGia:
    def __init__(self, dong_=None, cot=None, trang=None, loi=None):
        self.dong = dong_mau() if dong_ is None else dong_
        self.cot = COT if cot is None else cot
        self.trang = trang          # cỡ trang để thử phân trang
        self.loi = loi
        self.goi: list[tuple] = []
        self.gui: list[tuple] = []

    def call(self, method, path, query=None, body=None):
        self.goi.append((method, path, dict(query or {}), body))
        if self.loi:
            raise RuntimeError(self.loi)
        if path.endswith("/fields"):
            return {"code": 0, "data": {"items": self.cot, "has_more": False}}
        if path.endswith("/records/search"):
            n = self.trang or 500
            bat_dau = int((query or {}).get("page_token") or 0)
            lo = self.dong[bat_dau:bat_dau + n]
            con = bat_dau + n < len(self.dong)
            return {"code": 0, "data": {"items": lo, "has_more": con,
                                        "page_token": str(bat_dau + n) if con else None}}
        raise RuntimeError(f"Lark giả: không có {method} {path}")

    def send_text(self, kieu, rid, text, uuid=None):
        self.gui.append((kieu, rid, text, uuid))
        return {"code": 0}


@pytest.fixture
def lk(monkeypatch):
    g = LarkGia()
    monkeypatch.setattr(lark_client, "call", g.call)
    monkeypatch.setattr(lark_client, "send_text", g.send_text)
    return g


def _loc(dong_=None, hom_nay=HOM_NAY, **k):
    return T.loc_viec(dong_mau() if dong_ is None else dong_, hom_nay, **k)


def _d():
    return T.cau_hinh()


# ───────────────────────────── lọc ─────────────────────────────
def test_phan_nhom_dung():
    k = _loc()
    assert [v["record_id"] for v in k["qua_han"]] == ["r1", "r2"]
    assert [v["record_id"] for v in k["qua_han_khong_pic"]] == ["r8"]
    assert [v["record_id"] for v in k["qua_han_lau"]] == ["r12", "r13"]
    assert [v["record_id"] for v in k["sap_han"]] == ["r3", "r4"]
    assert {v["record_id"] for v in k["thieu"]} == {"r9", "r14"}
    assert k["dem"] == {"qua_han": 2, "qua_han_khong_pic": 1, "qua_han_lau": 2, "sap_han": 2,
                        "thieu_han_hoac_pic": 2, "da_xong_hoac_cancel": 3}
    assert k["qua_han_toi_da"] == 14


@pytest.mark.parametrize("ngay_qua,nhom", [(14, "qua_han"), (15, "qua_han_lau"), (1, "qua_han")])
def test_bien_qua_han_lau(ngay_qua, nhom):
    han = ms(*(HOM_NAY - datetime.timedelta(days=ngay_qua)).timetuple()[:3])
    k = _loc([dong("a", "A", pic=AN, han=han)])
    assert [v["record_id"] for v in k[nhom]] == ["a"]


def test_nguong_qua_han_cau_hinh_duoc(monkeypatch):
    d = [dong("a", "A", pic=AN, han=ms(2026, 9, 30))]                     # quá 7 ngày
    assert _loc(d)["qua_han"]
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_QUA_HAN_TOI_DA", "5")
    assert T.qua_han_toi_da() == 5 and _loc(d)["qua_han_lau"]
    assert _loc(d, qua_han_toi_da_ngay=30)["qua_han"]
    for sai in ("0", "abc", "-3", "999"):
        monkeypatch.setenv("MARK_NHAC_TIEN_DO_QUA_HAN_TOI_DA", sai)
        assert T.qua_han_toi_da() == 14


def test_han_hom_nay_la_sap_han_khong_phai_qua_han():
    k = _loc([dong("x", "A", pic=AN, han=ms(2026, 10, 7))])
    assert not k["qua_han"] and k["sap_han"][0]["con_ngay"] == 0
    assert "đến hạn hôm nay" in T.soan_tin(k, HOM_NAY, _d(), gan_the=False)


def test_bien_so_ngay():
    d = [dong("a", "A", pic=AN, han=ms(2026, 10, 10)), dong("b", "B", pic=AN, han=ms(2026, 10, 11))]
    assert [v["record_id"] for v in _loc(d)["sap_han"]] == ["a"]           # +3 trong, +4 ngoài
    assert [v["record_id"] for v in _loc(d, so_ngay=4)["sap_han"]] == ["a", "b"]
    assert _loc(d, so_ngay=0)["sap_han"] == []


def test_ranh_gioi_ngay_theo_gio_vn():
    """Hạn 08/10 lưu 00:00 VN = 17:00 UTC ngày 07/10. Quy hôm nay theo giờ VN, không UTC."""
    han = ms(2026, 10, 8)
    utc = datetime.timezone.utc
    truoc = datetime.datetime(2026, 10, 7, 16, 59, tzinfo=utc)     # 23:59 VN ngày 07/10
    sau = datetime.datetime(2026, 10, 7, 17, 1, tzinfo=utc)        # 00:01 VN ngày 08/10
    assert T.hom_nay_vn(truoc) == datetime.date(2026, 10, 7)
    assert T.hom_nay_vn(sau) == datetime.date(2026, 10, 8)
    assert T.ngay_vn(han) == datetime.date(2026, 10, 8)
    assert T.ngay_vn(han - 1) == datetime.date(2026, 10, 7)
    d = [dong("a", "A", pic=AN, han=han)]
    assert _loc(d, T.hom_nay_vn(truoc))["sap_han"][0]["con_ngay"] == 1
    assert _loc(d, T.hom_nay_vn(sau))["sap_han"][0]["con_ngay"] == 0
    assert _loc(d, datetime.date(2026, 10, 9))["qua_han"][0]["so_ngay_qua"] == 1


@pytest.mark.parametrize("tt,tinh", [("ĐÃ XONG", False), ("ĐÃ XONG ", False), ("đã xong", False),
                                     ("CANCEL", False), (" Cancel ", False), ("ĐANG LÀM ", True),
                                     ("CHỜ DUYỆT ", True), ("", True), (None, True)])
def test_chuan_hoa_trang_thai(tt, tinh):
    k = _loc([dong("a", "A", pic=AN, han=ms(2026, 10, 1), tt=tt)])
    assert bool(k["qua_han"]) is tinh


def test_thieu_han_chi_dem_qua_han_khong_pic_thi_liet_ke():
    tin = T.soan_tin(_loc(), HOM_NAY, _d(), gan_the=True)
    assert "2 việc chưa có hạn/PIC" in tin
    assert "Mua quà tặng" not in tin and "Book thợ ảnh" not in tin
    phan = tin.split("QUÁ HẠN, CHƯA CÓ NGƯỜI PHỤ TRÁCH:\n")[1].split("\n\n")[0]
    assert phan == "- Thuê địa điểm — EVENT — hạn 03/10 (quá 4 ngày)", "liệt kê tên, không tag"
    k = _loc([dong("a", "A", pic=AN, han=None), dong("b", "B", pic=None, han=ms(2026, 10, 8))])
    assert T.soan_tin(k, HOM_NAY, _d(), gan_the=True) == "", "chỉ có việc thiếu → không gửi"
    k = _loc([dong("a", "A", pic=None, han=ms(2026, 10, 1))])
    tin = T.soan_tin(k, HOM_NAY, _d(), gan_the=True)
    assert "Thuê" not in tin and "- A — MEDIA — hạn 01/10 (quá 6 ngày)" in tin and "<at" not in tin


def test_qua_han_lau_chi_mot_dong_dem_khong_tag():
    tin = T.soan_tin(_loc(), HOM_NAY, _d(), gan_the=True)
    assert "Đặt mẫu túi" not in tin and "Thiết kế POSM" not in tin
    assert ("2 việc quá hạn hơn 14 ngày — nhờ PIC cập nhật TRẠNG THÁI trên Base (link bên dưới)."
            in tin)
    assert tin.count("<at ") == 1, "Linh có việc quá hạn lâu nhưng chỉ tag vì việc gần đây"
    chi_lau = _loc([dong("a", "A", pic=LINH, han=ms(2026, 8, 1))])
    assert T.soan_tin(chi_lau, HOM_NAY, _d(), gan_the=True) == "", (
        "chỉ còn việc quá hạn lâu → không gửi (một dòng đếm mỗi sáng là tiếng ồn)")


def test_loc_pic_va_nhom():
    assert [v["record_id"] for v in _loc(pic="linh ngoc")["qua_han"]] == ["r1", "r2"]
    assert _loc(pic="linh")["sap_han"] == []
    assert [v["record_id"] for v in _loc(nhom="media")["sap_han"]] == ["r3", "r4"]
    assert _loc(nhom="media")["qua_han"] == []


# ───────────────────────────── soạn tin ─────────────────────────────
def test_tin_mau_dung_tung_chu():
    tin = T.soan_tin(_loc(), HOM_NAY, _d(), gan_the=True)
    assert tin == (
        "NHẮC TIẾN ĐỘ — Thứ Tư 07/10/2026 — CHECKLIST DA 20.10\n"
        "Quá hạn (trong 14 ngày): 3 việc · Tới hạn trong 3 ngày tới: 2 việc\n"
        "\n"
        "QUÁ HẠN (trong 14 ngày):\n"
        '<at user_id="ou_linh"></at>:\n'
        "- Gửi brief KOC — BOOKING — hạn 05/10 (quá 2 ngày)\n"
        "- Duyệt list KOC — BOOKING — hạn 06/10 (quá 1 ngày)\n"
        "\n"
        "QUÁ HẠN, CHƯA CÓ NGƯỜI PHỤ TRÁCH:\n"
        "- Thuê địa điểm — EVENT — hạn 03/10 (quá 4 ngày)\n"
        "\n"
        "SẮP TỚI HẠN (3 ngày tới):\n"
        "Trần An:\n"
        "- Quay teaser — MEDIA — hạn 07/10 (đến hạn hôm nay)\n"
        "- Dựng video — MEDIA — hạn 10/10 (còn 3 ngày)\n"
        "\n"
        "2 việc quá hạn hơn 14 ngày — nhờ PIC cập nhật TRẠNG THÁI trên Base (link bên dưới).\n"
        "2 việc chưa có hạn/PIC — xem Base (link bên dưới).\n"
        f"Base: https://o4pvcegwn6b.sg.larksuite.com/base/{APP}?table={BANG}")


def test_chi_tag_pic_qua_han_moi_nguoi_mot_lan():
    d = [dong("a", "A", pic=LINH, han=ms(2026, 10, 1)), dong("b", "B", pic=LINH, han=ms(2026, 10, 2)),
         dong("c", "C", pic=AN, han=ms(2026, 10, 8)),
         dong("e", "E", pic=LINH, han=ms(2026, 10, 9))]           # Linh cũng có việc sắp hạn
    tin = T.soan_tin(_loc(d), HOM_NAY, _d(), gan_the=True)
    assert tin.count("<at ") == 1 and tin.count('<at user_id="ou_linh"></at>') == 1
    assert 'user_id="ou_an"' not in tin
    sap = tin.split("SẮP TỚI HẠN")[1]
    assert "Linh Ngọc:" in sap and "Trần An:" in sap and "<at" not in sap


def test_tra_loi_chat_khong_bao_gio_co_the():
    tin = T.soan_tin(_loc(), HOM_NAY, _d(), gan_the=False)
    assert "<at" not in tin and tin.startswith("TIẾN ĐỘ — ")
    assert "Linh Ngọc:" in tin


def test_chu_trong_base_khong_tu_sinh_the_at():
    d = [dong("a", '<at user_id="all"></at> gấp', nhom="<b>", pic=("ou_x", "<at user_id=\"all\">"),
              han=ms(2026, 10, 1))]
    tin = T.soan_tin(_loc(d), HOM_NAY, _d(), gan_the=True)
    assert '<at user_id="all"' not in tin and "‹at" in tin
    assert tin.count("<at ") == 1 and '<at user_id="ou_x"></at>' in tin
    assert "<b>" not in tin


def test_tran_do_dai():
    d = [dong(f"r{i}", f"Việc {i}", pic=(f"ou_{i % 7}", f"Người {i % 7}"), han=ms(2026, 10, 1 + i % 6))
         for i in range(60)]
    tin = T.soan_tin(_loc(d), HOM_NAY, _d(), gan_the=True)
    assert sum(1 for x in tin.splitlines() if x.startswith("- ")) == T.TOI_DA_DONG
    assert "… và 20 việc khác — xem Base" in tin
    assert tin.rstrip().splitlines()[-1].startswith("Base: https://")


def test_khong_co_gi_thi_rong():
    assert T.soan_tin(_loc([]), HOM_NAY, _d(), gan_the=True) == ""
    xa = [dong("a", "A", pic=AN, han=ms(2026, 12, 1))]
    assert T.soan_tin(_loc(xa), HOM_NAY, _d(), gan_the=True) == ""


# ───────────────────────────── cấu hình + đọc Base ─────────────────────────────
def test_cau_hinh_mac_dinh_chung_base_ghi_viec(monkeypatch):
    import viec_base_tool as V
    assert (_d()["app_token"], _d()["table_id"]) == (V.cau_hinh()["app_token"], V.cau_hinh()["table_id"])
    monkeypatch.setenv("MARK_BASE_VIEC_URL", "https://x.sg.larksuite.com/base/ABCDEFGHIJKL?table=tblKhac1")
    assert (_d()["app_token"], _d()["table_id"]) == ("ABCDEFGHIJKL", "tblKhac1")
    monkeypatch.setenv("MARK_TIEN_DO_BASE_URL", "https://y.sg.larksuite.com/base/ZZZZZZZZZZZZ?table=tblTienDo")
    d = _d()
    assert (d["app_token"], d["table_id"], d["url"]) == (
        "ZZZZZZZZZZZZ", "tblTienDo", "https://y.sg.larksuite.com/base/ZZZZZZZZZZZZ?table=tblTienDo")
    monkeypatch.setenv("MARK_TIEN_DO_BASE_URL", "https://y.sg.larksuite.com/docx/abc")
    with pytest.raises(ValueError):
        _d()


def test_chi_goi_hai_endpoint_doc_va_phan_trang(lk):
    lk.trang = 4
    r = T.doc_viec(_d())
    assert len(r) == len(dong_mau())
    kieu = {(m, p.rsplit("/", 1)[-1] if not p.endswith("/records/search") else "records/search")
            for m, p, _, _ in lk.goi}
    assert kieu == {("GET", "fields"), ("POST", "records/search")}
    tim = [q for m, p, q, _ in lk.goi if p.endswith("/records/search")]
    assert len(tim) == -(-len(dong_mau()) // 4) and all(q["user_id_type"] == "open_id" for q in tim)
    assert all(b["field_names"] == list(T.COT_CAN) for m, p, _, b in lk.goi if b)


def test_thieu_cot_hoac_sai_kieu_thi_dung(lk):
    lk.cot = [c for c in COT if c["field_name"] != "DEADLINE"]
    with pytest.raises(T.CauTrucLoi, match="DEADLINE"):
        T.doc_viec(_d())
    lk.cot = [dict(c, type=1) if c["field_name"] == "DEADLINE" else c for c in COT]
    with pytest.raises(T.CauTrucLoi, match="kiểu"):
        T.doc_viec(_d())


# ───────────────────────────── tool tra_tien_do ─────────────────────────────
def _tool(**a):
    return json.loads(T._handle(a))


@pytest.fixture
def cho_doc(monkeypatch):
    """Người hỏi qua được cửa quyền (ghi lại mọi nguồn đã hỏi)."""
    hoi = []

    def mo(nguon):
        hoi.append(nguon)
        nd = BT.B.nhan_dien(nguon)
        return nd[0], nd[1], nd[2], "Base", "là thành viên"
    monkeypatch.setattr(BT, "mo_nguon", mo)
    monkeypatch.setattr(T, "hom_nay_vn", lambda now=None: HOM_NAY)
    return hoi


def test_tool_tra_cau_va_danh_sach(lk, cho_doc):
    kq = _tool()
    assert cho_doc == [_d()["url"]], "Base mặc định vẫn phải qua cửa quyền của người hỏi"
    assert kq["dem"]["qua_han"] == 2 and kq["dem"]["sap_han"] == 2
    assert kq["qua_han"][0] == {"hang_muc": "Gửi brief KOC", "nhom": "BOOKING", "pic": "Linh Ngọc",
                                "han": "2026-10-05", "so_ngay_qua": 2}
    assert "<at" not in kq["cau_tien_do"] and "quá 2 ngày" in kq["cau_tien_do"]
    assert [x["hang_muc"] for x in kq["qua_han_lau"]] == ["Đặt mẫu túi", "Thiết kế POSM"]
    assert kq["qua_han_khong_pic"][0]["hang_muc"] == "Thuê địa điểm"
    assert "2 việc quá hạn hơn 14 ngày" in kq["cau_tien_do"] and kq["qua_han_toi_da"] == 14
    kq = _tool(qua_han_toi_da=60)
    assert kq["dem"]["qua_han_lau"] == 0 and "Đặt mẫu túi" in kq["cau_tien_do"]
    assert "error" in _tool(qua_han_toi_da="x")
    assert not any(m == "POST" and "batch" in p for m, p, _, _ in lk.goi)


def test_tool_loc_va_khong_co_gi(lk, cho_doc):
    kq = _tool(pic="Hà", so_ngay=3)
    assert kq["dem"]["qua_han"] == 0 and "Không có việc nào quá hạn" in kq["cau_tien_do"]
    assert "(PIC 'Hà')" in kq["cau_tien_do"] and "07/10/2026" in kq["cau_tien_do"]
    kq = _tool(nhom="booking")
    assert "(lọc NHÓM 'booking')" in kq["cau_tien_do"].splitlines()[0]
    assert _tool(so_ngay="7")["so_ngay"] == 7 and _tool(so_ngay=99)["so_ngay"] == 30
    lk.dong = [dong("a", "Việc cũ", pic=AN, han=ms(2026, 8, 1))]
    cau = _tool()["cau_tien_do"]
    assert cau.startswith("Không có việc nào quá hạn trong 14 ngày gần đây")
    assert "1 việc quá hạn hơn 14 ngày — nhờ PIC cập nhật TRẠNG THÁI" in cau
    assert "error" in _tool(so_ngay="abc")


def test_tool_dung_chung_cua_quyen_voi_doc_bang(lk, monkeypatch):
    """Không giả `mo_nguon`: người lạ hỏi → bị chặn bằng ĐÚNG luật của doc_bang, chưa đọc Base."""
    monkeypatch.setattr(BT, "_nguoi_hoi", lambda: "ou_nguoi_la")
    kq = _tool()
    assert "error" in kq and "Không đọc Base này cho bạn" in kq["error"]
    assert not any("/bitable/" in p for _, p, _, _ in lk.goi), "từ chối TRƯỚC khi đọc Base"
    monkeypatch.setenv("AGENT_BOSS_OPEN_ID", "ou_chu")
    monkeypatch.setattr(BT, "_nguoi_hoi", lambda: "ou_chu")
    assert _tool()["success"] is True


def test_tool_nguon_khac_va_sai_loai(lk, cho_doc):
    kq = _tool(nguon="https://x.sg.larksuite.com/base/QQQQQQQQQQQQ?table=tblQ1")
    assert kq["bang_url"].endswith("/base/QQQQQQQQQQQQ?table=tblQ1")
    assert any("/apps/QQQQQQQQQQQQ/tables/tblQ1/" in p for _, p, _, _ in lk.goi)
    assert "error" in _tool(nguon="https://x.sg.larksuite.com/base/QQQQQQQQQQQQ")
    assert "error" in _tool(nguon="https://x.sg.larksuite.com/sheets/SSSSSSSSSS")


def test_tool_doc_hong_bao_loi(lk, cho_doc):
    lk.loi = "HTTP 403"
    assert "chưa đọc được Base" in _tool()["error"]


# ───────────────────────────── nhắc hằng ngày ─────────────────────────────
def gio(h, m=0, ngay=HOM_NAY):
    return datetime.datetime(ngay.year, ngay.month, ngay.day, h, m, tzinfo=VN)


@pytest.fixture
def bat_nhac(monkeypatch):
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_CHAT", CHAT)


def test_tat_khi_chua_cau_hinh(lk, monkeypatch):
    assert not T.dang_bat()
    assert T.trang_thai_khoi_dong() == "Nhắc tiến độ: TẮT (chưa đặt MARK_NHAC_TIEN_DO_CHAT)"
    assert T.chay_mot_nhip(gio(8, 31)) == "tat" and not lk.goi and not lk.gui
    import threading
    truoc = threading.active_count()
    assert T.khoi_dong().startswith("Nhắc tiến độ: TẮT")
    assert threading.active_count() == truoc, "tắt thì không dựng luồng"
    for sai in ("lark:cli_x:oc_1", "ou_abc", "oc_x;rm"):
        monkeypatch.setenv("MARK_NHAC_TIEN_DO_CHAT", sai)
        assert not T.dang_bat()
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_CHAT", CHAT)
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_GIO", "25:00")
    assert not T.dang_bat() and "HH:MM" in T.trang_thai_khoi_dong()


def test_trang_thai_bat(bat_nhac, monkeypatch):
    assert T.trang_thai_khoi_dong() == f"Nhắc tiến độ: BẬT → nhóm {CHAT} 08:30 mỗi ngày (giờ VN)"
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_GIO", "7:05")
    assert "07:05" in T.trang_thai_khoi_dong()


def test_gui_dung_mot_lan_moi_ngay(lk, bat_nhac):
    assert T.chay_mot_nhip(gio(8, 29)) == "chua_den" and not lk.goi
    assert T.chay_mot_nhip(gio(8, 30)) == "da_gui"
    assert len(lk.gui) == 1
    kieu, rid, text, uid = lk.gui[0]
    assert (kieu, rid) == ("chat_id", CHAT) and text.startswith("NHẮC TIẾN ĐỘ — Thứ Tư 07/10/2026")
    assert uid == f"tiendo-{CHAT}-261007" and len(uid) <= 50
    n = len(lk.goi)
    for h, m in ((8, 31), (9, 0), (10, 29), (23, 59)):
        assert T.chay_mot_nhip(gio(h, m)) == "da_xu_ly"
    assert len(lk.gui) == 1 and len(lk.goi) == n, "đã gửi thì không đọc Base lại"
    hom_sau = HOM_NAY + datetime.timedelta(days=1)
    assert T.chay_mot_nhip(gio(8, 30, hom_sau)) == "da_gui"
    assert lk.gui[1][3] == f"tiendo-{CHAT}-261008"


def test_cuoi_tuan_van_gui(lk, bat_nhac):
    cn = datetime.date(2026, 10, 11)
    assert cn.weekday() == 6
    lk.dong = [dong("a", "A", pic=AN, han=ms(2026, 10, 1))]
    assert T.chay_mot_nhip(gio(8, 30, cn)) == "da_gui"
    assert "Chủ Nhật 11/10/2026" in lk.gui[0][2]


def test_khoi_dong_lai_khong_gui_lan_hai(lk, bat_nhac, monkeypatch):
    assert T.chay_mot_nhip(gio(8, 30)) == "da_gui"
    # "Khởi động lại": trạng thái trong bộ nhớ mất, chỉ còn sổ trên đĩa.
    monkeypatch.setattr(T, "_trang_thai", {"thu_lai_sau": 0.0, "da_bao": set()})
    assert T.chay_mot_nhip(gio(9, 15)) == "da_xu_ly" and len(lk.gui) == 1
    so = json.loads(T._SO.read_text(encoding="utf-8"))
    assert so[CHAT]["ngay"] == "2026-10-07" and so[CHAT]["ket_qua"] == "da_gui"


def test_so_khong_bien_base_thanh_base_noi_bo(lk, bat_nhac):
    """bang_tool.base_noi_bo() khoá mọi app_token trong .tokens/*.json với người hỏi."""
    T.chay_mot_nhip(gio(8, 30))
    s = T._SO.read_text(encoding="utf-8")
    assert "app_token" not in s and "base_token" not in s and APP not in s


@pytest.mark.parametrize("h,m,kq", [(9, 0, "da_gui"), (10, 29, "da_gui"),
                                    (10, 30, "qua_cua_so"), (14, 0, "qua_cua_so")])
def test_cua_so_gui_bu(lk, bat_nhac, h, m, kq):
    assert T.chay_mot_nhip(gio(h, m)) == kq
    assert len(lk.gui) == (1 if kq == "da_gui" else 0)
    if kq == "qua_cua_so":
        assert not lk.goi, "quá cửa sổ thì không đọc Base"
        assert T.chay_mot_nhip(gio(8, 30, HOM_NAY + datetime.timedelta(days=1))) == "da_gui"


def test_cua_so_theo_gio_cau_hinh(lk, bat_nhac, monkeypatch):
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_GIO", "11:00")
    assert T.chay_mot_nhip(gio(10, 45)) == "chua_den"
    assert T.chay_mot_nhip(gio(12, 59)) == "da_gui"


def test_khong_co_gi_thi_khong_gui_va_khong_doc_lai(lk, bat_nhac):
    lk.dong = [dong("a", "A", pic=AN, han=ms(2026, 12, 1))]
    assert T.chay_mot_nhip(gio(8, 30)) == "khong_co_gi"
    n = len(lk.goi)
    assert T.chay_mot_nhip(gio(8, 31)) == "da_xu_ly" and len(lk.goi) == n and not lk.gui


def test_doc_base_hong_thi_khong_gui_va_lui(lk, bat_nhac, monkeypatch, capsys):
    lk.loi = "HTTP 500"
    assert T.chay_mot_nhip(gio(8, 30)) == "loi_doc" and not lk.gui
    assert T.chay_mot_nhip(gio(8, 31)) == "cho_thu_lai"
    assert capsys.readouterr().out.count("không đọc được Base") == 1, "log một lần"
    lk.loi = None
    T._trang_thai["thu_lai_sau"] = 0.0                    # hết thời gian lùi
    assert T.chay_mot_nhip(gio(8, 40)) == "da_gui" and len(lk.gui) == 1


def test_cau_truc_hong_thi_khong_gui(lk, bat_nhac):
    lk.cot = [c for c in COT if c["field_name"] != "PIC"]
    assert T.chay_mot_nhip(gio(8, 30)) == "loi_doc" and not lk.gui


def test_gui_hong_tam_thi_thu_lai_vinh_vien_thi_bo(lk, bat_nhac, monkeypatch):
    lan = {"n": 0}

    def hong(kieu, rid, text, uuid=None):
        lan["n"] += 1
        raise RuntimeError("HTTP 502: proxy")
    monkeypatch.setattr(lark_client, "send_text", hong)
    assert T.chay_mot_nhip(gio(8, 30)) == "loi_gui"
    assert "ket_qua" not in _so(), "lỗi tạm: chưa xong ngày, còn thử lại"
    T._trang_thai["thu_lai_sau"] = 0.0
    monkeypatch.setattr(lark_client, "send_text",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("230002 bot is not in the chat")))
    assert T.chay_mot_nhip(gio(8, 35)) == "loi_gui"
    assert _so()["ket_qua"] == "khong_bao_duoc_chu", "chưa có AGENT_BOSS_OPEN_ID"
    assert T.chay_mot_nhip(gio(8, 40)) == "da_xu_ly"


def _so():
    return json.loads(T._SO.read_text(encoding="utf-8"))[CHAT]


CHU = "ou_" + "c" * 32


@pytest.fixture
def co_chu(monkeypatch):
    monkeypatch.setenv("AGENT_BOSS_OPEN_ID", CHU)


def test_doc_hong_ca_cua_so_thi_bao_rieng_chu_mot_lan(lk, bat_nhac, co_chu, monkeypatch):
    lk.loi = "HTTP 403 forbidden"
    assert T.chay_mot_nhip(gio(8, 30)) == "loi_doc"
    T._trang_thai["thu_lai_sau"] = 0.0
    assert T.chay_mot_nhip(gio(10, 0)) == "loi_doc" and not lk.gui, "trong cửa sổ: chỉ thử lại"
    # Khởi động lại sau cửa sổ: lỗi đã ghi sổ nên vẫn báo được.
    monkeypatch.setattr(T, "_trang_thai", {"thu_lai_sau": 0.0, "da_bao": set()})
    assert T.chay_mot_nhip(gio(10, 31)) == "da_bao_chu"
    assert len(lk.gui) == 1
    kieu, rid, text, uid = lk.gui[0]
    assert (kieu, rid) == ("open_id", CHU), "chỉ nhắn RIÊNG chủ agent, không bao giờ vào nhóm"
    assert text.startswith("Hôm nay chưa gửi được nhắc tiến độ vào nhóm: không đọc được Base")
    assert "HTTP 403" in text and uid == f"tdchu-{CHU}-261007" and len(uid) <= 50
    for h in (10, 12, 23):
        assert T.chay_mot_nhip(gio(h, 45)) == "da_xu_ly"
    assert len(lk.gui) == 1, "tối đa một lần mỗi ngày"
    assert not any(g[1] == CHAT for g in lk.gui)


def test_gui_hong_tam_ca_cua_so_thi_bao_chu(lk, bat_nhac, co_chu, monkeypatch):
    nhom = []

    def gui(kieu, rid, text, uuid=None):
        if kieu == "chat_id":
            nhom.append(rid)
            raise RuntimeError("HTTP 503: quá tải")
        lk.gui.append((kieu, rid, text, uuid))
        return {}
    monkeypatch.setattr(lark_client, "send_text", gui)
    assert T.chay_mot_nhip(gio(8, 30)) == "loi_gui" and not lk.gui
    assert T.chay_mot_nhip(gio(10, 30)) == "da_bao_chu"
    assert lk.gui[0][:2] == ("open_id", CHU) and "Lark từ chối" in lk.gui[0][2]
    assert nhom == [CHAT], "hết cửa sổ thì không thử gửi nhóm nữa"


def test_gui_hong_vinh_vien_bao_chu_ngay(lk, bat_nhac, co_chu, monkeypatch):
    def gui(kieu, rid, text, uuid=None):
        if kieu == "chat_id":
            raise RuntimeError("230002 bot is not in the chat")
        lk.gui.append((kieu, rid, text, uuid))
        return {}
    monkeypatch.setattr(lark_client, "send_text", gui)
    assert T.chay_mot_nhip(gio(8, 30)) == "loi_gui"
    assert [g[:2] for g in lk.gui] == [("open_id", CHU)] and _so()["ket_qua"] == "da_bao_chu"
    assert T.chay_mot_nhip(gio(10, 31)) == "da_xu_ly" and len(lk.gui) == 1


def test_khoi_dong_tre_khong_loi_thi_khong_bao_chu(lk, bat_nhac, co_chu):
    assert T.chay_mot_nhip(gio(11, 0)) == "qua_cua_so" and not lk.gui and not lk.goi


def test_loi_hom_qua_khong_bao_hom_nay(lk, bat_nhac, co_chu):
    lk.loi = "HTTP 500"
    assert T.chay_mot_nhip(gio(8, 30)) == "loi_doc"
    mai = HOM_NAY + datetime.timedelta(days=1)
    assert T.chay_mot_nhip(gio(11, 0, mai)) == "qua_cua_so" and not lk.gui


def test_nhip_khong_bao_gio_nem(lk, bat_nhac, monkeypatch):
    monkeypatch.setattr(T, "_doc_so", lambda: 1 / 0)
    assert T.chay_mot_nhip(gio(8, 30)) == "loi"


def test_uuid_nhac():
    assert T.uuid_nhac(CHAT, HOM_NAY) == f"tiendo-{CHAT}-261007"
    dai = T.uuid_nhac("oc_" + "b" * 60, HOM_NAY)
    assert len(dai) <= 50 and dai.endswith("-261007") and dai.startswith("tiendo-")
    assert dai != T.uuid_nhac("oc_" + "c" * 60, HOM_NAY)


# ───────────────────────────── lời dặn prompt ─────────────────────────────
def test_loi_dan_theo_cau_hinh(monkeypatch):
    tat = T.loi_dan()
    assert "TẮT" in tat and "KHÔNG" in tat and "tra_tien_do" in tat
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_CHAT", CHAT)
    bat = T.loi_dan()
    assert "BẬT" in bat and "08:30" in bat and CHAT not in bat, "không lộ mã nhóm vào prompt"


# ───────────────────────────── policy + brain + kỹ năng ─────────────────────────────
def _dat(quyen, bat):
    import time
    lsr_policy._nho.update(quyen=set(quyen), luc=time.time(), nguon="test")
    lsr_policy._nho_nl.update(bat=bat, luc=time.time(), nguon="test")


def test_policy_chi_doc_va_lui_ve_doc_bang():
    assert "tra_tien_do" in lsr_policy._SAFE_EXACT
    assert "tra_tien_do" not in lsr_policy._MUTATING_EXACT
    assert lsr_policy._CONG_TAC_LUI["tra_tien_do"] == "doc_bang"
    _dat({"reply", "call_agent"}, lsr_policy.KHONG_THU_HEP)
    assert lsr_policy.decide("tra_tien_do", {}).allowed, "chỉ đọc: không cần write_data"
    _dat({"reply"}, {"doc_bang"})
    assert lsr_policy.decide("tra_tien_do", {}).allowed
    _dat({"reply"}, {"social_listen"})
    d = lsr_policy.decide("tra_tien_do", {})
    assert not d.allowed and "theo công tắc 'doc_bang'" in d.reason


def test_dang_ky_va_noi_brain():
    from tools.registry import registry  # type: ignore
    e = registry._tools["tra_tien_do"]
    assert e.toolset == "lark_api"
    brain = (GOC / "brain.py").read_text(encoding="utf-8")
    assert "import tien_do" in brain and '"tra_tien_do":' in brain        # _TOOL_CAN_XET
    assert "tien_do.loi_dan()" in brain and "`tra_tien_do`" in brain
    assert "không tự so ngày" in brain
    run = (GOC / "run.py").read_text(encoding="utf-8")
    assert "tien_do.khoi_dong()" in run
    sk = (GOC / "skills" / "hop-va-ban-giao.md").read_text(encoding="utf-8")
    assert "tra_tien_do" in sk and "không tag" in sk.lower() and "gửi tin" in sk


def test_brain_ke_tool_trong_quyen_han():
    import brain
    assert "tra_tien_do" in brain._TOOL_CAN_XET
    assert "Base checklist" in brain._TOOL_CAN_XET["tra_tien_do"][0]


# ───────────────────────────── CLI ─────────────────────────────
def _cli():
    spec = importlib.util.spec_from_file_location("nhac_tien_do_cli", GOC / "scripts" / "nhac_tien_do.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize("argv", [[], ["--gui-thu"], ["--gui-thu", "--chat", "ou_x"],
                                  ["--xem-truoc", "--chat", CHAT], ["--xem-truoc", "--gui-thu"],
                                  ["--chat", CHAT]])
def test_cli_doi_co_ro(argv):
    with pytest.raises(SystemExit) as e:
        _cli()._tham_so(argv)
    assert e.value.code == 2


def test_cli_xem_truoc_khong_gui(lk, monkeypatch, capsys):
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_CHAT", CHAT)        # có cấu hình vẫn không gửi
    assert _cli().main(["--xem-truoc", "--ngay", "2026-10-07"]) == 0
    out = capsys.readouterr().out
    assert "NHẮC TIẾN ĐỘ — Thứ Tư 07/10/2026" in out and "chưa gửi" in out
    assert not lk.gui and not T._SO.exists()


def test_cli_gui_thu_dung_chat_chi_dinh(lk, monkeypatch):
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_CHAT", "oc_nhomthat")
    assert _cli().main(["--gui-thu", "--chat", "oc_nhomthu", "--ngay", "2026-10-07"]) == 0
    assert [g[1] for g in lk.gui] == ["oc_nhomthu"]
    # uuid theo ngày: chạy lại lệnh gửi thử trong 1 giờ thì Lark không đăng tin thứ hai.
    assert str(lk.gui[0][3]).startswith("tdthu-oc_nhomthu-") and len(lk.gui[0][3]) <= 50
    assert not T._SO.exists(), "gửi thử không chặn nhắc 08:30 của bộ chạy chính"


def test_cli_khong_co_gi_hoac_doc_hong_thi_khong_gui(lk):
    lk.dong = []
    assert _cli().main(["--gui-thu", "--chat", "oc_nhomthu"]) == 0 and not lk.gui
    lk.loi = "HTTP 403"
    assert _cli().main(["--gui-thu", "--chat", "oc_nhomthu"]) == 1 and not lk.gui


def test_bao_loi_dung_bien_rieng_khong_can_quyen_chu_agent(lk, bat_nhac, monkeypatch):
    """Prod không đặt AGENT_BOSS_OPEN_ID; báo lỗi vẫn tới người ở MARK_NHAC_TIEN_DO_BAO_LOI."""
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_BAO_LOI", "ou_nguoi_nhan_loi")
    assert T._bao_chu("oc_nhomthu", datetime.date(2026, 10, 7), "HTTP 403") == "da_bao_chu"
    assert [g[:2] for g in lk.gui] == [("open_id", "ou_nguoi_nhan_loi")]
