"""Lịch console đọc bằng quyền XEM của bot (`cach: bot_console`) — chủ agent chốt 08/10/2026.

"Phần kết nối tài khoản Lark có thể bỏ đi và dùng quyền đọc của Mark khi được truy cập vào
trong Base, tách biệt với kiến thức được nạp: set nhóm nhận thì chỉ quét và gửi vào nhóm
nhận thôi." Ranh giới kiểm ở đây:
  • chỉ job THEO LỊCH có `schedule_source` == "console" mới dùng được `bot_console`;
  • (loại, token, bảng) khớp tuyệt đối, bảng không rỗng, `kiem_luc` < 2 giờ, lệch tương
    lai ≤ 5 phút; không đòi người hỏi == người đặt;
  • `cua_toi=co` vẫn cần open_id thật (`scheduled_by` hoặc `boi`);
  • Base nội bộ chặn y như cũ;
  • gõ tay, tool model, lịch tạo trong chat, tin thường: `bot_console` bị bỏ qua;
  • /tiendo không ghi kho/trí nhớ/lịch sử, kết quả chỉ là câu trả lời của chính job.
Không chạm mạng.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

import bang_tool as BT
import lsr_platform as P
import tien_do as T

TOK, BANG, OWNER = "baseTok123", "tblViec", "ou_owner"
LINK = f"https://test.larksuite.com/base/{TOK}?table={BANG}"


def _iso(giay_truoc=60):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=giay_truoc)).isoformat()


def _pc(**kw):
    """`nguon_da_kiem` Platform gửi cho lịch console."""
    return {"loai": "bitable", "token": TOK, "table_id": BANG, "kiem_luc": _iso(),
            "cach": "bot_console", "boi": "", "nguoi_dat": "admin@x.test", **kw}


def _cm(nguon_lich="console", nguoi_dat="", **kw):
    return BT.ChungMinhLich.tu_payload(_pc(**kw), nguoi_dat, nguon_lich=nguon_lich)


@pytest.fixture
def cua(monkeypatch):
    """Cửa quyền thật, mạng giả: API thành viên luôn 403, không công khai, không Wiki."""
    goi = {"thanh_vien": 0}

    def thanh_vien(*a, **k):
        goi["thanh_vien"] += 1
        raise RuntimeError("403 forbidden")
    monkeypatch.setattr(BT.B, "_trang", thanh_vien)
    monkeypatch.setattr(BT.lark, "call", lambda *a, **k: {
        "data": {"permission_public": {"link_share_entity": "closed"}}})
    monkeypatch.setattr(BT, "base_noi_bo", lambda: set())
    monkeypatch.setattr(BT, "_trong_cay_wiki", lambda *a: False)
    monkeypatch.delenv("AGENT_BOSS_OPEN_ID", raising=False)
    monkeypatch.delenv("STEVEN_BOSS_OPEN_ID", raising=False)
    return goi


# ───────────────────────────── bằng chứng ─────────────────────────────
def test_console_qua_cua_khong_can_nguoi_hoi(cua):
    ok, vi_sao = BT.quyen_nguoi_hoi("bitable", TOK, "", table_id=BANG, chung_minh=_cm())
    assert ok and vi_sao == "lịch console do quản trị agent đặt; bot được cấp quyền xem bảng"
    assert cua["thanh_vien"] == 0


def test_console_khong_doi_nguoi_hoi_bang_nguoi_dat(cua):
    c = _cm(nguoi_dat=OWNER, boi="ou_khac")
    assert BT.quyen_nguoi_hoi("bitable", TOK, "ou_bat_ky", table_id=BANG, chung_minh=c)[0]


@pytest.mark.parametrize("nguon_lich", ["lark", "", "Console", None])
def test_bot_console_chi_cho_lich_dat_tren_console(nguon_lich):
    assert BT.ChungMinhLich.tu_payload(_pc(), OWNER, nguon_lich=nguon_lich) is None


@pytest.mark.parametrize("p", [_pc(boi="user@x.test"), _pc(table_id=""), _pc(token="a/b"),
                               _pc(loai="docx"), _pc(kiem_luc="hôm qua")])
def test_bot_console_payload_hong(p):
    assert BT.ChungMinhLich.tu_payload(p, "", nguon_lich="console") is None


@pytest.mark.parametrize("cm, loai, token, bang", [
    (dict(table_id="tblKhac"), "bitable", TOK, BANG),
    (dict(token="baseKhac999"), "bitable", TOK, BANG),
    (dict(loai="sheet"), "bitable", TOK, BANG),
    (dict(kiem_luc=_iso(2 * 3600 + 60)), "bitable", TOK, BANG),     # cũ quá 2 giờ
    (dict(kiem_luc=_iso(-600)), "bitable", TOK, BANG),               # tương lai > 5 phút
    ({}, "bitable", TOK, ""),                                        # link không chỉ bảng
])
def test_console_lech_bi_bo_qua(cua, cm, loai, token, bang):
    ok, vi_sao = BT.quyen_nguoi_hoi(loai, token, "", table_id=bang, chung_minh=_cm(**cm))
    assert not ok and vi_sao != BT.LY_DO_LICH_CONSOLE


def test_console_lech_tuong_lai_trong_5_phut_van_nhan(cua):
    assert BT.quyen_nguoi_hoi("bitable", TOK, "", table_id=BANG,
                              chung_minh=_cm(kiem_luc=_iso(-120)))[0]


def test_cach_khac_giu_luat_theo_nguoi(cua):
    """`cach` lạ = bằng chứng theo người: boi == người đặt == người hỏi."""
    p = {**_pc(cach="token_nguoi_dat", boi=OWNER)}
    c = BT.ChungMinhLich.tu_payload(p, OWNER, nguon_lich="console")
    assert c is not None and not c.la_console
    assert BT.quyen_nguoi_hoi("bitable", TOK, OWNER, table_id=BANG, chung_minh=c)[1] \
        == BT.LY_DO_LICH
    assert not BT.quyen_nguoi_hoi("bitable", TOK, "ou_khac", table_id=BANG, chung_minh=c)[0]
    assert BT.ChungMinhLich.tu_payload({**p, "boi": ""}, OWNER, nguon_lich="console") is None


def test_mo_nguon_wiki_so_voi_token_da_giai(cua, monkeypatch):
    monkeypatch.setattr(BT.B, "giai_wiki", lambda node: ("bitable", TOK))
    wiki = f"https://test.larksuite.com/wiki/WikiNode123?table={BANG}"
    assert BT.mo_nguon(wiki, nguoi_hoi="", chung_minh=_cm())[4] == BT.LY_DO_LICH_CONSOLE
    with pytest.raises(BT.TuChoi, match="không khớp đúng bảng"):
        BT.mo_nguon(wiki, nguoi_hoi="", chung_minh=_cm(token="WikiNode123"))


# ───────────────────────────── Base nội bộ ─────────────────────────────
@pytest.fixture
def noi_bo(cua, monkeypatch, tmp_path):
    monkeypatch.setattr(BT, "base_noi_bo", lambda: {TOK})
    monkeypatch.setattr(BT, "_thu_muc_token", lambda: tmp_path)
    for ten, bang in (("audit_base.json", "tblAudit"), ("chi_phi_quet_base.json", "tblChiPhi"),
                      ("audit_base.previous.json", "tblAuditCu")):
        (tmp_path / ten).write_text(json.dumps({"app_token": TOK, "table_id": bang}))
    (tmp_path / "mixed_base_read_allowlist.json").write_text(json.dumps(
        {"version": 1, "tables": [{"app_token": TOK, "table_id": "tblAudit"}]}))
    return tmp_path


@pytest.mark.parametrize("nguoi", ["", OWNER])
@pytest.mark.parametrize("bang", ["tblAudit", "tblChiPhi", "tblAuditCu", BANG])
def test_console_khong_mo_base_noi_bo(noi_bo, bang, nguoi):
    c = _cm(table_id=bang, nguoi_dat=nguoi)
    ok, _ = BT.quyen_nguoi_hoi("bitable", TOK, nguoi, table_id=bang, chung_minh=c)
    assert not ok
    link = f"https://test.larksuite.com/base/{TOK}?table={bang}"
    with pytest.raises(BT.TuChoi) as e:
        BT.mo_nguon(link, nguoi_hoi=nguoi, chung_minh=c)
    assert "Base nội bộ" in str(e.value) or "Audit/Chi phí" in str(e.value)


# ───────────────────────────── kênh job (giả mạo) ─────────────────────────────
def test_kenh_lich_mang_schedule_source():
    p = {"scheduled": True, "scheduled_by": "", "schedule_id": 3,
         "schedule_source": "console", "nguon_da_kiem": _pc()}
    k = P._kenh_cua_job({"id": 1, "payload": p})
    assert k["schedule_source"] == "console" and k["nguon_da_kiem"]["cach"] == "bot_console"


@pytest.mark.parametrize("job", [
    {"id": 2, "reply_to": {"chat_type": "group"},
     "payload": {"text": "/tiendo", "schedule_source": "console", "nguon_da_kiem": _pc()}},
    {"id": 3, "payload": {"schedule_source": "console", "nguon_da_kiem": _pc()}},
    {"id": 4, "reply_to": {"chat_type": "p2p"},
     "payload": {"scheduled": "true", "schedule_source": "console", "nguon_da_kiem": _pc()}},
    {"id": 5, "reply_to": {"chat_type": "group"},
     "payload": {"scheduled": 1, "schedule_source": "console", "nguon_da_kiem": _pc()}},
])
def test_kenh_tin_thuong_bo_schedule_source_va_chung_minh(job):
    k = P._kenh_cua_job(job) or {}
    assert "nguon_da_kiem" not in k and "schedule_source" not in k and not k.get("scheduled")


def test_kenh_schedule_source_la_bi_bo():
    k = P._kenh_cua_job({"id": 6, "payload": {"scheduled": True, "schedule_source": "web",
                                               "nguon_da_kiem": _pc()}})
    assert "schedule_source" not in k
    assert BT.ChungMinhLich.tu_payload(k["nguon_da_kiem"], "",
                                       nguon_lich=k.get("schedule_source") or "") is None


# ───────────────────────────── /tiendo đầu-cuối ─────────────────────────────
FIELDS = {"Việc": {"type": 1, "primary": True}, "Phụ trách": {"type": 11},
          "Ngày hết hạn": {"type": 5}, "Status": {"type": 3, "options": ["Chưa xong", "Done"]}}


@pytest.fixture
def td(cua, monkeypatch, tmp_path):
    monkeypatch.setattr(T, "_SO", tmp_path / "nhac.json")

    def khong_cau_hinh():
        raise ValueError("chưa cấu hình")
    monkeypatch.setattr(T, "cau_hinh", khong_cau_hinh)
    monkeypatch.setattr(T, "ten_base", lambda d: "CHECKLIST")
    monkeypatch.setattr(T, "hom_nay_vn", lambda: dt.date(2026, 10, 7))
    monkeypatch.setattr(T.VB, "_doc_cot", lambda d: FIELDS)
    han = int(dt.datetime(2026, 10, 6, tzinfo=T._VN).timestamp() * 1000)
    doc = {"n": 0}

    def dong(d, f):
        doc["n"] += 1
        return [{"record_id": r, "fields": {
            "Việc": viec, "Phụ trách": [{"id": pic, "name": ten}],
            "Ngày hết hạn": han, "Status": "Chưa xong"}}
            for r, viec, pic, ten in (("r1", "Gửi brief", "ou_pic", "An"),
                                      ("r2", "Duyệt mẫu", "ou_owner", "Chủ"))]
    monkeypatch.setattr(T, "_doc_dong", dong)
    return doc


def _lich(**kw):
    return {"scheduled": True, "scheduled_by": "", "schedule_id": 3,
            "schedule_source": "console", "nguon_da_kiem": _pc(), **kw}


def test_tiendo_console_khong_nguoi_dat_van_doc_va_tag(td):
    text = T.lenh_tiendo(LINK, kenh=_lich(), chat_id="lark:cli_x:oc_g")
    assert "Gửi brief" in text and '<at user_id="ou_pic">' in text


def test_tiendo_console_nguoi_dat_khac_boi_van_doc(td):
    text = T.lenh_tiendo(LINK, kenh=_lich(scheduled_by="ou_khac"), chat_id="oc_g")
    assert "Gửi brief" in text


def test_tiendo_console_bang_khac_bi_tu_choi_khong_doc(td):
    text = T.lenh_tiendo(LINK, kenh=_lich(nguon_da_kiem=_pc(table_id="tblKhac")),
                         chat_id="oc_g")
    assert "Gửi brief" not in text and "Lịch chạy" in text and td["n"] == 0
    assert "Kết nối" not in text


def test_tiendo_console_cu_bi_tu_choi(td):
    text = T.lenh_tiendo(LINK, kenh=_lich(nguon_da_kiem=_pc(kiem_luc=_iso(3 * 3600))),
                         chat_id="oc_g")
    assert "Gửi brief" not in text and td["n"] == 0


def test_tiendo_console_nguon_loi(td):
    k = _lich(nguon_loi="bot chưa được thêm vào Base")
    k.pop("nguon_da_kiem")
    text = T.lenh_tiendo(LINK, kenh=k, chat_id="oc_g")
    assert "Gửi brief" not in text and td["n"] == 0
    assert "bot chưa được thêm vào Base" in text and "Lịch chạy" in text


def test_tiendo_cua_toi_console_khong_danh_tinh_tu_choi_truoc_khi_doc(td):
    text = T.lenh_tiendo(LINK + " cua_toi=co", kenh=_lich(), chat_id="oc_g")
    assert text == T.LOI_KHONG_RO_NGUOI_LICH and td["n"] == 0


@pytest.mark.parametrize("kenh", [_lich(scheduled_by=OWNER),
                                  _lich(nguon_da_kiem=_pc(boi=OWNER))])
def test_tiendo_cua_toi_console_dung_scheduled_by_hoac_boi(td, kenh):
    text = T.lenh_tiendo(LINK + " cua_toi=co", kenh=kenh, chat_id="oc_g")
    assert "Duyệt mẫu" in text and "Gửi brief" not in text and "<at" not in text


def test_tiendo_lich_tao_trong_chat_bo_qua_bot_console(td):
    text = T.lenh_tiendo(LINK, kenh=_lich(scheduled_by=OWNER, schedule_source="lark"),
                         chat_id="oc_g")
    assert "Gửi brief" not in text and td["n"] == 0
    assert "Lịch chưa có người đặt" in T.lenh_tiendo(
        LINK, kenh=_lich(schedule_source="lark"), chat_id="oc_g")


def test_tiendo_go_tay_bo_qua_bot_console(td):
    k = {"chat_type": "group", "schedule_source": "console", "nguon_da_kiem": _pc()}
    text = T.lenh_tiendo(LINK, kenh=k, sender_open_id=OWNER)
    assert "Gửi brief" not in text and td["n"] == 0
    assert "đặt lịch trên console (chọn nhóm nhận, giờ)" in text


def test_tiendo_job_thuong_qua_kenh_that_bo_qua_bot_console(td):
    job = {"id": 8, "reply_to": {"chat_type": "group"},
           "payload": {"text": "/tiendo " + LINK, "sender_open_id": OWNER,
                       "schedule_source": "console", "nguon_da_kiem": _pc()}}
    text = T.lenh_tiendo(LINK, kenh=P._kenh_cua_job(job), sender_open_id=OWNER)
    assert "Gửi brief" not in text and td["n"] == 0


# ───────────────────────────── tool model ─────────────────────────────
@pytest.fixture
def ghi_cua(monkeypatch):
    """Ghi lại `chung_minh` mà tool model đưa vào cửa quyền (phải luôn là None)."""
    goc = BT.quyen_nguoi_hoi
    seen = []

    def boc(*a, **kw):
        seen.append(kw.get("chung_minh"))
        return goc(*a, **kw)
    monkeypatch.setattr(BT, "quyen_nguoi_hoi", boc)
    monkeypatch.setattr(BT, "_nguoi_hoi", lambda: OWNER)
    return seen


def test_tool_model_bo_qua_bot_console_ca_luot_theo_lich(td, ghi_cua, monkeypatch):
    import dem_bang_tool
    import scheduler
    scheduler.set_current_scheduled(True)
    try:
        args = {"nguon": LINK, "nguon_da_kiem": _pc(), "schedule_source": "console",
                "cach": "bot_console"}
        for h in (T._handle, BT._handle, dem_bang_tool._handle):
            kq = json.loads(h(dict(args)))
            assert "error" in kq and "danh sách người có quyền" in kq["error"], h
    finally:
        scheduler.set_current_scheduled(False)
    assert ghi_cua and all(c is None for c in ghi_cua) and td["n"] == 0


# ───────────────────────────── tách khỏi kiến thức ─────────────────────────────
def test_tiendo_theo_lich_khong_ghi_kho_tri_nho(td, monkeypatch):
    import bai_hoc_tool
    import brain
    import memory_store
    import wiki_tu_dong

    def cam(ten):
        return lambda *a, **k: pytest.fail(f"/tiendo đã ghi {ten}")
    monkeypatch.setattr(brain, "_resolve_agent", cam("model"))
    for mod, ten in ((memory_store, "append_turns"), (memory_store, "append_user_memory"),
                     (P, "ghi_luot_ngu_canh"), (bai_hoc_tool, "_luu"),
                     (bai_hoc_tool, "_goi"), (wiki_tu_dong, "mot_luot"),
                     (wiki_tu_dong, "_goi")):
        monkeypatch.setattr(mod, ten, cam(f"{mod.__name__}.{ten}"))
    monkeypatch.setattr(brain.audit, "bat_dau", lambda *a, **kw: "t")
    monkeypatch.setattr(brain.audit, "ket_thuc", lambda *a, **kw: None)
    k = _lich()
    text = brain.reply("/tiendo " + LINK, chat_id="lark:cli_x:oc_g", sender_open_id=None,
                       kenh=k)
    assert "Gửi brief" in text
    # Chỉ giữ chỗ gửi cho CHÍNH nhóm của job (Platform gửi câu trả lời vào chat của job).
    assert k["tien_do_gui"][0] == "oc_g"


def test_vong_job_chi_tra_loi_vao_job_cua_no(td, monkeypatch):
    job = {"id": 9, "session_id": "lark:cli_x:oc_g",
           "payload": {"text": "/tiendo " + LINK, "scheduled": True, "scheduled_by": "",
                       "schedule_id": 7, "schedule_source": "console",
                       "nguon_da_kiem": _pc()}}
    monkeypatch.setattr(P, "_goi", lambda *a, **kw: [job])
    monkeypatch.setattr(P, "_tai_anh", lambda *a: [])
    gui = []
    monkeypatch.setattr(P, "_goi_job", lambda c, duong, than: gui.append(duong) or {"ok": 1})

    def reply(text, chat_id, sender_open_id, kenh):
        return T.lenh_tiendo(text[len("/tiendo "):], chat_id=chat_id,
                             sender_open_id=sender_open_id, kenh=kenh)
    assert P._mot_vong({}, reply) == 1
    assert gui == ["/v1/self/jobs/9/reply", "/v1/self/jobs/9/complete"]
