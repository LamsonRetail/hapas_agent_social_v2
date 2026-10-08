"""Các ranh giới thật: quyền người đặt lịch, tag, no-model, gửi/ACK và khử trùng."""
import datetime as dt
import json
import pytest
import tien_do as T
import memory_store
import lsr_platform as P
_OPEN = T.BT.mo_nguon

NGAY = dt.date(2026, 10, 7)
D = {"app_token": "baseTokenTest123", "table_id": "tblTest", "ten": "Dự án",
     "url": "https://test.larksuite.com/base/baseTokenTest123?table=tblTest"}
FIELDS = {"Việc": {"type": 1, "primary": True}, "Phụ trách": {"type": 11},
          "Ngày hết hạn": {"type": 5},
          "Status": {"type": 3, "options": ["Chưa xong", "Done", "Hoàn thành ", "Huỷ"]}}

def row(name="Gửi brief", status="Chưa xong"):
    return {"record_id": "r1", "fields": {"Việc": name, "Phụ trách": [{"id": "ou_pic", "name": "An"}],
        "Ngày hết hạn": int(dt.datetime(2026, 10, 6, tzinfo=T._VN).timestamp() * 1000), "Status": status}}

@pytest.fixture
def ctx(monkeypatch, tmp_path):
    monkeypatch.setattr(T, "_SO", tmp_path/"nhac.json")
    monkeypatch.setattr(T, "cau_hinh", lambda: dict(D))
    monkeypatch.setattr(T, "hom_nay_vn", lambda: NGAY)
    monkeypatch.setattr(T.VB, "_doc_cot", lambda d: FIELDS)
    monkeypatch.setattr(T, "_doc_dong", lambda d, fields: [row()])
    seen=[]
    def open_source(source, *, nguoi_hoi=None):
        seen.append(nguoi_hoi)
        return "bitable", D["app_token"], D["table_id"], "Base", "fixture"
    monkeypatch.setattr(T.BT, "mo_nguon", open_source)
    return seen

def scheduled(**kw):
    return {"scheduled": True, "scheduled_by": "ou_owner", "schedule_id": 7, **kw}

def test_nhan_cot_primary_status_chua_xong_khong_bi_loai():
    c=T.nhan_cot(FIELDS)
    assert (c["ten"], c["pic"], c["han"], c["tt"]) == ("Việc", "Phụ trách", "Ngày hết hạn", "Status")
    k=T.loc_viec([row(), row(status="Done"), row(status="Hoàn thành "), row(status="Huỷ")], NGAY, cot=c)
    assert k["dem"]["qua_han"] == 1 and k["dem"]["da_xong_hoac_cancel"] == 3

def test_nhieu_nguoi_mo_ho_va_ghi_de():
    f={**FIELDS, "Người A": {"type": 11}, "Người B": {"type": 11}}
    del f["Phụ trách"]
    with pytest.raises(T.CauTrucLoi, match="cot_pic"):
        T.nhan_cot(f)
    assert T.nhan_cot(f, {"pic": "Người B"})["pic"] == "Người B"

def test_thieu_han_noi_ro_kieu_va_cu_phap():
    f={k:v for k,v in FIELDS.items() if v["type"] != 5}
    with pytest.raises(T.CauTrucLoi, match="cot_han"):
        T.nhan_cot(f)

def test_quote_link_co_query_va_overrides():
    url, o=T.tach_tuy_chon(D["url"]+' cot_han="Ngày hết hạn" xong="Done;Huỷ" so_ngay=5 tag=khong')
    assert url==D["url"] and o["cot_han"]=="Ngày hết hạn" and o["so_ngay"]==5

@pytest.mark.parametrize("text", ["so_ngay=31", "tag=sai", "cot_han=", "bad=1", "so_ngay=a"])
def test_tuy_chon_sai_khong_doan(text):
    with pytest.raises(ValueError): T.tach_tuy_chon(text)

def test_go_tay_quyen_nguoi_gui_khong_tag(ctx):
    text=T.lenh_tiendo(D["url"], sender_open_id="ou_sender")
    assert ctx==["ou_sender"] and "<at" not in text and "An" in text

def test_lich_dung_owner_tag_va_restore_sender(ctx):
    k=scheduled()
    text=T.lenh_tiendo(D["url"], kenh=k, chat_id="lark:cli_test:oc_group", sender_open_id="ou_other")
    assert ctx==["ou_owner"] and '<at user_id="ou_pic">' in text
    assert "tien_do_gui" in k

def test_lich_tag_khong(ctx):
    text=T.lenh_tiendo(D["url"]+" tag=khong", kenh=scheduled(), chat_id="oc_group")
    assert "NHẮC TIẾN ĐỘ" in text and "<at" not in text

@pytest.mark.parametrize("owner", ["", "user@email.test", "ou_bad\"<"])
def test_lich_thieu_owner_tu_choi_truoc_doc(ctx, owner):
    assert "tạo lại" in T.lenh_tiendo(D["url"], kenh=scheduled(scheduled_by=owner), chat_id="oc_group")
    assert not ctx

def test_tu_choi_quyen_khong_doc_base(ctx, monkeypatch):
    def deny(s, **kw): raise T.BT.TuChoi("Bạn chưa có quyền xem")
    monkeypatch.setattr(T.BT, "mo_nguon", deny)
    monkeypatch.setattr(T.VB, "_doc_cot", lambda d: pytest.fail("đã đọc sau từ chối"))
    assert "quyền xem" in T.lenh_tiendo(D["url"], sender_open_id="ou_sender")

def test_giu_cho_ack_that_moi_ngay_da_gui(ctx):
    k=scheduled()
    T.lenh_tiendo(D["url"], kenh=k, chat_id="oc_group")
    e=json.loads(T._SO.read_text())["oc_group"]["bases"][T._khoa_base(D)]
    assert "cho_den" in e and "ngay" not in e
    assert T.da_nhac("oc_group", D, NGAY)
    T.xac_nhan_gui(k)
    assert T.da_nhac("oc_group", D, NGAY)
    assert "cho_den" not in json.loads(T._SO.read_text())["oc_group"]["bases"][T._khoa_base(D)]
    assert "app_token" not in T._SO.read_text() and D["app_token"] not in T._SO.read_text()
    assert "đang gửi" in T.lenh_tiendo(D["url"], kenh=scheduled(), chat_id="oc_group")

def test_gui_loi_giai_phong_cho(ctx):
    k=scheduled()
    T.lenh_tiendo(D["url"], kenh=k, chat_id="oc_group")
    T.huy_cho_gui(k)
    assert not T.da_nhac("oc_group", D, NGAY)

def test_env_gui_truoc_console_bo_qua_va_base_khac_khong_bo(ctx):
    T._xong("oc_group", NGAY, "da_gui")
    assert "đang gửi" in T.lenh_tiendo(D["url"], kenh=scheduled(), chat_id="oc_group")
    assert not T.da_nhac("oc_group", {**D, "table_id": "tblKhac"}, NGAY)

def test_console_giu_cho_env_bo_qua(ctx, monkeypatch):
    monkeypatch.setenv("MARK_NHAC_TIEN_DO_CHAT", "oc_group")
    T.lenh_tiendo(D["url"], kenh=scheduled(), chat_id="oc_group")
    monkeypatch.setattr(T, "soan_tin_hom_nay", lambda d: pytest.fail("env đọc/gửi trùng"))
    assert T.chay_mot_nhip(dt.datetime(2026,10,7,8,30,tzinfo=T._VN))=="da_xu_ly"

def test_sanitize_cap_va_link_con_lai(ctx, monkeypatch):
    monkeypatch.setattr(T, "_doc_dong", lambda d, fields: [row('<at> giả '+"x"*500) for _ in range(60)])
    text=T.lenh_tiendo(D["url"], sender_open_id="ou_sender")
    assert "<at>" not in text and len(text)<=T.TRAN_KY_TU and D["url"] in text

def test_khong_viec_noi_ro_nguong_khong_tag(ctx, monkeypatch):
    monkeypatch.setattr(T, "_doc_dong", lambda d, fields: [row(status="Done")])
    text=T.lenh_tiendo(D["url"], kenh=scheduled(), chat_id="oc_group")
    assert "Không có việc" in text and "<at" not in text

def test_job_metadata_du_khong_co_chat_type():
    p={"scheduled": True, "scheduled_by": "ou_owner", "schedule_id": 7}
    k=P._kenh_cua_job({"id": 9, "payload": p})
    assert k["scheduled_by"]=="ou_owner" and k["schedule_id"]==7 and k["job_id"]==9
    assert P._kenh_cua_job({"payload": {"scheduled": "true"}}) is None

def test_brain_khong_goi_model_va_noi_dung_code(ctx, monkeypatch):
    import brain
    monkeypatch.setattr(brain, "_resolve_agent", lambda *a,**kw: pytest.fail("đã gọi model"))
    monkeypatch.setattr(brain.memory_store, "append_turns", lambda *a,**kw: None)
    monkeypatch.setattr(brain.audit, "bat_dau", lambda *a,**kw: "test")
    monkeypatch.setattr(brain.audit, "ket_thuc", lambda *a,**kw: None)
    text=brain.reply("/tiendo "+D["url"], chat_id="oc_group", sender_open_id="ou_sender")
    assert "Gửi brief" in text and "<at" not in text

def test_cua_quyen_that_nhan_chinh_danh_lich(ctx, monkeypatch):
    monkeypatch.setattr(T.BT, "mo_nguon", _OPEN)
    got=[]
    def check(kind, token, asker, node, *, table_id=""):
        got.append((asker, table_id))
        return False, "fixture denied"
    monkeypatch.setattr(T.BT, "quyen_nguoi_hoi", check)
    text=T.lenh_tiendo(D["url"], kenh=scheduled(), chat_id="oc_group", sender_open_id="ou_other")
    assert got==[("ou_owner", "tblTest")] and "fixture denied" in text

def test_nua_bang_khong_bao_thanh_day_du(monkeypatch):
    monkeypatch.setattr(T.VB, "_goi", lambda *a,**kw: {"data": {"items": [row()], "has_more": True}})
    with pytest.raises(RuntimeError, match="nửa bảng"):
        T._doc_dong(D, ["Việc"])

@pytest.mark.parametrize("gui_loi", [False, True])
def test_vong_job_that_ack_hoac_giai_phong_giu_cho(ctx, monkeypatch, gui_loi):
    job={"id": 9, "session_id": "lark:cli_test:oc_group",
         "payload": {"text": "/tiendo "+D["url"], "scheduled": True,
                     "scheduled_by": "ou_owner", "schedule_id": 7}}
    monkeypatch.setattr(P, "_goi", lambda *a,**kw: [job])
    monkeypatch.setattr(P, "_tai_anh", lambda *a: [])
    def send(c, path, body):
        if gui_loi and path.endswith("/reply"):
            raise RuntimeError("fixture send failed")
        return {"ok": True}
    monkeypatch.setattr(P, "_goi_job", send)
    def reply(text, chat_id, sender_open_id, kenh):
        return T.lenh_tiendo(text[len("/tiendo "):], chat_id=chat_id,
                             sender_open_id=sender_open_id, kenh=kenh)
    assert P._mot_vong({}, reply)==1
    assert T.da_nhac("oc_group", D, NGAY) is (not gui_loi)
