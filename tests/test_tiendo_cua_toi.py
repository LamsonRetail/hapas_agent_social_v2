"""`/tiendo … cua_toi=co` và `tra_tien_do(cua_toi=true)` (chủ agent chốt 08/10/2026).

Ranh giới: chỉ việc có NGƯỜI HỎI trong cột PIC — so open_id, không theo tên; người hỏi là
người gửi (gõ tay) hoặc `scheduled_by` (lịch), không bao giờ là thứ gõ trong lệnh/đối số;
thiếu danh tính thì từ chối trước khi đọc Base; không bao giờ có `<at>`; khử trùng lịch
theo Base+nhóm+người. Không chạm mạng.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

import tien_do as T

NGAY = dt.date(2026, 10, 7)
D = {"app_token": "baseTokenTest123", "table_id": "tblTest", "ten": "Dự án",
     "url": "https://test.larksuite.com/base/baseTokenTest123?table=tblTest"}
FIELDS = {"Việc": {"type": 1, "primary": True}, "Phụ trách": {"type": 11},
          "Ngày hết hạn": {"type": 5},
          "Status": {"type": 3, "options": ["Chưa xong", "Done"]}}


def _ms(ngay):
    return int(dt.datetime(ngay.year, ngay.month, ngay.day, tzinfo=T._VN).timestamp() * 1000)


def row(name, pics, han=dt.date(2026, 10, 6), status="Chưa xong"):
    return {"record_id": name, "fields": {
        "Việc": name, "Phụ trách": [{"id": i, "name": n} for i, n in pics],
        "Ngày hết hạn": _ms(han), "Status": status}}


ROWS = [
    row("Việc của tôi", [("ou_toi", "Tôi")]),
    row("Việc chung", [("ou_khac", "Khác"), ("ou_toi", "Tôi")]),       # tôi là PIC thứ hai
    row("Việc trùng tên", [("ou_trungten", "Tôi")]),                   # cùng TÊN, khác người
    row("Việc người khác", [("ou_khac", "Khác")]),
    row("Việc tôi sắp hạn", [("ou_toi", "Tôi")], han=dt.date(2026, 10, 8)),
    row("Việc tôi đã xong", [("ou_toi", "Tôi")], status="Done"),
]


@pytest.fixture
def ctx(monkeypatch, tmp_path):
    monkeypatch.setattr(T, "_SO", tmp_path / "nhac.json")
    monkeypatch.setattr(T, "cau_hinh", lambda: dict(D))
    monkeypatch.setattr(T, "hom_nay_vn", lambda: NGAY)
    doc = []
    monkeypatch.setattr(T.VB, "_doc_cot", lambda d: doc.append("cot") or FIELDS)
    monkeypatch.setattr(T, "_doc_dong", lambda d, fields: doc.append("dong") or list(ROWS))
    seen = []

    def open_source(source, *, nguoi_hoi=None):
        seen.append(nguoi_hoi)
        return "bitable", D["app_token"], D["table_id"], "Base", "fixture"
    monkeypatch.setattr(T.BT, "mo_nguon", open_source)
    return {"quyen": seen, "doc": doc}


def lich(**kw):
    return {"scheduled": True, "scheduled_by": "ou_toi", "schedule_id": 7, **kw}


def test_loc_viec_theo_open_id_ca_pic_thu_hai_khong_theo_ten():
    c = T.nhan_cot(FIELDS)
    k = T.loc_viec(ROWS, NGAY, cot=c, chi_cua="ou_toi")
    ten = {v["ten"] for v in k["qua_han"] + k["sap_han"]}
    assert ten == {"Việc của tôi", "Việc chung", "Việc tôi sắp hạn"}
    assert k["dem"]["da_xong_hoac_cancel"] == 1, "đếm xong chỉ của người hỏi"
    # Không lọc thì đủ cả
    assert T.loc_viec(ROWS, NGAY, cot=c)["dem"]["qua_han"] == 4


def test_go_tay_cua_toi_chi_viec_cua_nguoi_gui_khong_tag(ctx):
    text = T.lenh_tiendo(D["url"] + " cua_toi=co", sender_open_id="ou_toi")
    assert ctx["quyen"] == ["ou_toi"]
    assert "VIỆC CỦA BẠN" in text and "<at" not in text
    assert "Việc của tôi" in text and "Việc chung" in text and "Việc tôi sắp hạn" in text
    assert "Việc trùng tên" not in text and "Việc người khác" not in text


def test_cua_toi_khong_lay_nguoi_tu_lenh(ctx):
    # Không có cú pháp nào chọn "của ai": giá trị lạ bị từ chối, không hiểu thành open_id.
    for bad in ("cua_toi=ou_khac", "cua_toi=", "nguoi=ou_khac"):
        text = T.lenh_tiendo(D["url"] + " " + bad, sender_open_id="ou_toi")
        assert "Việc người khác" not in text and "Việc của tôi" not in text
    assert ctx["doc"] == []


@pytest.mark.parametrize("sender", [None, "", "user@mail.test", "ou_bad\"<", "on_union1"])
def test_go_tay_thieu_danh_tinh_tu_choi_truoc_khi_doc(ctx, sender):
    text = T.lenh_tiendo(D["url"] + " cua_toi=co", sender_open_id=sender)
    assert text == T.LOI_KHONG_RO_NGUOI and ctx["doc"] == [] and ctx["quyen"] == []


def test_lich_cua_toi_theo_nguoi_dat_khong_tag_du_tag_co(ctx):
    k = lich()
    text = T.lenh_tiendo(D["url"] + " cua_toi=co tag=co", kenh=k,
                         chat_id="lark:cli_test:oc_group", sender_open_id="ou_khac")
    assert ctx["quyen"] == ["ou_toi"]
    assert "NHẮC TIẾN ĐỘ — VIỆC CỦA BẠN" in text and "<at" not in text
    assert "Việc của tôi" in text and "Việc người khác" not in text
    assert k["tien_do_gui"][3] == "ou_toi"


def test_lich_cua_toi_khong_chan_va_khong_bi_chan_boi_lich_ca_nhom(ctx):
    k1 = lich()
    T.lenh_tiendo(D["url"], kenh=k1, chat_id="oc_group")
    T.xac_nhan_gui(k1)
    assert T.da_nhac("oc_group", D, NGAY)
    assert not T.da_nhac("oc_group", D, NGAY, "ou_toi")
    k2 = lich()
    text = T.lenh_tiendo(D["url"] + " cua_toi=co", kenh=k2, chat_id="oc_group")
    assert "VIỆC CỦA BẠN" in text
    T.xac_nhan_gui(k2)
    assert T.da_nhac("oc_group", D, NGAY, "ou_toi") and T.da_nhac("oc_group", D, NGAY)
    # lượt thứ hai cùng người cùng ngày: không gửi lại; người khác thì vẫn được
    assert "đã gửi" in T.lenh_tiendo(D["url"] + " cua_toi=co", kenh=lich(), chat_id="oc_group")
    assert not T.da_nhac("oc_group", D, NGAY, "ou_khac")
    so = T._SO.read_text(encoding="utf-8")
    assert D["app_token"] not in so and "ou_toi" not in so, "sổ chỉ chứa băm"


def test_huy_cho_gui_cua_toi_giai_phong_dung_khoa(ctx):
    k = lich()
    T.lenh_tiendo(D["url"] + " cua_toi=co", kenh=k, chat_id="oc_group")
    assert T.da_nhac("oc_group", D, NGAY, "ou_toi")
    T.huy_cho_gui(k)
    assert not T.da_nhac("oc_group", D, NGAY, "ou_toi")


def test_ghi_nhac_giu_cho_dang_giu_cua_khoa_khac(ctx):
    k_rieng = lich()
    T.lenh_tiendo(D["url"] + " cua_toi=co", kenh=k_rieng, chat_id="oc_group")
    T.ghi_nhac("oc_group", D, NGAY)                       # lượt cả nhóm ACK trước
    assert T.da_nhac("oc_group", D, NGAY, "ou_toi"), "chỗ đang giữ của lượt riêng bị xoá"


def test_cua_toi_khong_viec_noi_ro_cua_ban(ctx, monkeypatch):
    monkeypatch.setattr(T, "_doc_dong", lambda d, f: [row("X", [("ou_khac", "K")])])
    text = T.lenh_tiendo(D["url"] + " cua_toi=co", sender_open_id="ou_toi")
    assert text.startswith("✅ Bạn không có việc") and "<at" not in text


def test_cua_toi_khong_va_cu_phap(ctx):
    text = T.lenh_tiendo(D["url"] + " cua_toi=khong", sender_open_id="ou_toi")
    assert "VIỆC CỦA BẠN" not in text and "Việc người khác" in text
    assert "cua_toi=co|khong" in T.CU_PHAP_NGAN
    with pytest.raises(ValueError, match="cua_toi"):
        T.tach_tuy_chon(D["url"] + " cua_toi=maybe")


def test_mac_dinh_checklist_cung_loc_duoc(ctx, monkeypatch):
    """Đường CHECKLIST DA (không link, cột cố định) cũng lọc theo open_id."""
    import viec_base_tool as VB
    f = {VB.COT_TEN: {"type": 1}, VB.COT_NHOM: {"type": 3}, VB.COT_PIC: {"type": 11},
         VB.COT_HAN: {"type": 5}, VB.COT_TT: {"type": 3}}
    monkeypatch.setattr(T.VB, "_doc_cot", lambda d: f)

    def r(ten, oid):
        return {"record_id": ten, "fields": {
            VB.COT_TEN: ten, VB.COT_PIC: [{"id": oid, "name": "Tên"}],
            VB.COT_HAN: _ms(dt.date(2026, 10, 6)), VB.COT_TT: "CẦN LÀM"}}
    monkeypatch.setattr(T, "_doc_dong", lambda d, cot: [r("Của tôi", "ou_toi"),
                                                         r("Của người khác", "ou_khac")])
    text = T.lenh_tiendo("cua_toi=co", sender_open_id="ou_toi")
    assert "Của tôi" in text and "Của người khác" not in text and "<at" not in text


# ───────────────────────────── tool tra_tien_do ─────────────────────────────
def test_tool_cua_toi_lay_nguoi_tu_luot(ctx, monkeypatch):
    monkeypatch.setattr(T.BT, "_nguoi_hoi", lambda: "ou_toi")
    monkeypatch.setattr(T, "doc_viec", lambda d: pytest.fail("phải đi đường tự nhận cột"))
    monkeypatch.setattr(T.BT, "mo_nguon", lambda s, **kw: ("bitable", "khacBase12345",
                                                           "tblKhac", "Base", "fixture"))
    monkeypatch.setattr(T, "ten_base", lambda d: "Base khác")
    kq = json.loads(T._handle({"cua_toi": True, "nguon": "https://test.larksuite.com/base/"
                               "khacBase12345?table=tblKhac"}))
    assert kq["chi_viec_cua_nguoi_hoi"] is True
    assert "VIỆC CỦA BẠN" in kq["cau_tien_do"] and "<at" not in kq["cau_tien_do"]
    ten = {v["hang_muc"] for v in kq["qua_han"] + kq["sap_han"]}
    assert ten == {"Việc của tôi", "Việc chung", "Việc tôi sắp hạn"}


def test_tool_cua_toi_thieu_danh_tinh_tu_choi(ctx, monkeypatch):
    monkeypatch.setattr(T.BT, "_nguoi_hoi", lambda: "")
    kq = json.loads(T._handle({"cua_toi": "true"}))
    assert kq["error"] == T.LOI_KHONG_RO_NGUOI and ctx["doc"] == []


def test_tool_schema_co_cua_toi_boolean():
    p = T.SCHEMA["parameters"]["properties"]["cua_toi"]
    assert p["type"] == "boolean" and "không theo tên" in p["description"]
