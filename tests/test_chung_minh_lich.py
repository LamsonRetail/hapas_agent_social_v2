"""Phép kiểm quyền của Platform cho lịch (`nguon_da_kiem`) — chủ agent chốt 08/10/2026.

Bot chỉ có quyền XEM thì API thành viên trả 403, Mark chặn tất cả. Platform kiểm thay bằng
token Lark của người đặt lịch. Ranh giới:
  • chỉ job THEO LỊCH mang khoá này sang kenh; tin/job thường có khoá cũng bị bỏ;
  • chỉ tính khi boi == scheduled_by == người hỏi, (loại, token, bảng) khớp tuyệt đối link
    (sau khi giải Wiki), kiem_luc trong 2 giờ — không khớp thì như không có;
  • luật Base nội bộ xét trước, không đổi: không bao giờ mở Audit/Chi phí;
  • `nguon_loi` mà không căn cứ nào đạt → từ chối nêu lý do + chỉ console.
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


def _p(**kw):
    return {"loai": "bitable", "token": TOK, "table_id": BANG, "kiem_luc": _iso(),
            "boi": OWNER, **kw}


@pytest.fixture
def cua(monkeypatch):
    """Cửa quyền thật, mạng giả: API thành viên luôn 403, không công khai, không Wiki."""
    goi = {"thanh_vien": 0, "cong_khai": 0}

    def thanh_vien(*a, **k):
        goi["thanh_vien"] += 1
        raise RuntimeError("403 forbidden")

    def cong_khai(*a, **k):
        goi["cong_khai"] += 1
        return {"data": {"permission_public": {"link_share_entity": "closed"}}}
    monkeypatch.setattr(BT.B, "_trang", thanh_vien)
    monkeypatch.setattr(BT.lark, "call", cong_khai)
    monkeypatch.setattr(BT, "base_noi_bo", lambda: set())
    monkeypatch.setattr(BT, "_trong_cay_wiki", lambda *a: False)
    monkeypatch.delenv("AGENT_BOSS_OPEN_ID", raising=False)
    monkeypatch.delenv("STEVEN_BOSS_OPEN_ID", raising=False)
    return goi


def _cm(**kw):
    return BT.ChungMinhLich.tu_payload(_p(**kw), OWNER)


# ───────────────────────────── cửa quyền ─────────────────────────────
def test_chung_minh_khop_qua_cua_khong_can_api_thanh_vien(cua):
    ok, vi_sao = BT.quyen_nguoi_hoi("bitable", TOK, OWNER, table_id=BANG, chung_minh=_cm())
    assert ok and vi_sao == BT.LY_DO_LICH
    assert vi_sao == ("người đặt lịch xem được bảng này (Platform kiểm bằng tài khoản Lark "
                      "của họ)")
    assert cua == {"thanh_vien": 0, "cong_khai": 0}


@pytest.mark.parametrize("cm, nguoi, loai, token, bang", [
    (dict(table_id="tblKhac"), OWNER, "bitable", TOK, BANG),
    (dict(token="baseKhac999"), OWNER, "bitable", TOK, BANG),
    (dict(loai="sheet"), OWNER, "bitable", TOK, BANG),
    (dict(boi="ou_khac"), OWNER, "bitable", TOK, BANG),
    ({}, "ou_khac", "bitable", TOK, BANG),                       # người hỏi ≠ người đặt
    (dict(kiem_luc=_iso(2 * 3600 + 60)), OWNER, "bitable", TOK, BANG),   # cũ quá 2 giờ
    (dict(kiem_luc=_iso(-3600)), OWNER, "bitable", TOK, BANG),   # ở tương lai
    ({}, OWNER, "bitable", TOK, ""),                              # link không chỉ bảng
])
def test_chung_minh_lech_bi_bo_qua(cua, cm, nguoi, loai, token, bang):
    c = BT.ChungMinhLich.tu_payload(_p(**cm), OWNER)
    ok, vi_sao = BT.quyen_nguoi_hoi(loai, token, nguoi, table_id=bang, chung_minh=c)
    assert not ok and vi_sao != BT.LY_DO_LICH and cua["thanh_vien"] == 1


def test_nguoi_dat_khac_nguoi_hoi_trong_payload(cua):
    c = BT.ChungMinhLich.tu_payload(_p(), "ou_scheduled_khac")
    assert not BT.quyen_nguoi_hoi("bitable", TOK, OWNER, table_id=BANG, chung_minh=c)[0]


@pytest.mark.parametrize("p", [None, "x", [], {}, _p(loai="docx"), _p(token="a/b"),
                               _p(table_id=""), _p(boi="user@x.test"), _p(kiem_luc="hôm qua"),
                               _p(kiem_luc=None)])
def test_payload_hong_khong_thanh_chung_minh(p):
    assert BT.ChungMinhLich.tu_payload(p, OWNER) is None


def test_gio_khong_mui_coi_la_utc():
    t = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat()
    c = BT.ChungMinhLich.tu_payload(_p(kiem_luc=t), OWNER)
    assert c and c.dung_cho("bitable", TOK, BANG, OWNER)


# ───────────────────────────── Base nội bộ ─────────────────────────────
@pytest.fixture
def noi_bo(cua, monkeypatch, tmp_path):
    monkeypatch.setattr(BT, "base_noi_bo", lambda: {TOK})
    monkeypatch.setattr(BT, "_thu_muc_token", lambda: tmp_path)
    for ten, bang in (("audit_base.json", "tblAudit"), ("chi_phi_quet_base.json", "tblChiPhi"),
                      ("audit_base.previous.json", "tblAuditCu")):
        (tmp_path / ten).write_text(json.dumps({"app_token": TOK, "table_id": bang}))
    return tmp_path


@pytest.mark.parametrize("bang", ["tblAudit", "tblChiPhi", "tblAuditCu"])
def test_chung_minh_khong_mo_audit_chi_phi(noi_bo, bang):
    c = BT.ChungMinhLich.tu_payload(_p(table_id=bang), OWNER)
    ok, vi_sao = BT.quyen_nguoi_hoi("bitable", TOK, OWNER, table_id=bang, chung_minh=c)
    assert not ok and "Audit/Chi phí" in vi_sao


def test_chung_minh_khong_mo_base_noi_bo_chua_cho_phep(noi_bo):
    ok, vi_sao = BT.quyen_nguoi_hoi("bitable", TOK, OWNER, table_id=BANG, chung_minh=_cm())
    assert not ok and "chưa cho phép đúng bảng" in vi_sao


def test_chung_minh_thay_tra_thanh_vien_cho_bang_duoc_cho_phep(noi_bo):
    (noi_bo / "mixed_base_read_allowlist.json").write_text(json.dumps(
        {"version": 1, "tables": [{"app_token": TOK, "table_id": BANG}]}))
    ok, vi_sao = BT.quyen_nguoi_hoi("bitable", TOK, OWNER, table_id=BANG, chung_minh=_cm())
    assert ok and BT.LY_DO_LICH in vi_sao and "cho phép" in vi_sao
    assert not BT.quyen_nguoi_hoi("bitable", TOK, OWNER, table_id=BANG)[0], "luật cũ không đổi"


# ───────────────────────────── mo_nguon (cả Wiki) ─────────────────────────────
def test_mo_nguon_wiki_so_voi_token_da_giai(cua, monkeypatch):
    monkeypatch.setattr(BT.B, "giai_wiki", lambda node: ("bitable", TOK))
    wiki = f"https://test.larksuite.com/wiki/WikiNode123?table={BANG}"
    assert BT.mo_nguon(wiki, nguoi_hoi=OWNER, chung_minh=_cm())[4] == BT.LY_DO_LICH
    sai = BT.ChungMinhLich.tu_payload(_p(token="WikiNode123"), OWNER)
    with pytest.raises(BT.TuChoi):
        BT.mo_nguon(wiki, nguoi_hoi=OWNER, chung_minh=sai)


def test_mo_nguon_nguon_loi_noi_ly_do_va_console(cua):
    with pytest.raises(BT.TuChoi) as e:
        BT.mo_nguon(LINK, nguoi_hoi=OWNER, loi_lich="bot chưa được thêm vào Base <at>")
    s = str(e.value)
    assert "bot chưa được thêm vào Base" in s and "<at" not in s
    assert "console → Lịch chạy để kiểm lại" in s and "Kết nối" not in s


def test_mo_nguon_khong_chung_minh_giu_luat_cu(cua):
    with pytest.raises(BT.TuChoi, match="danh sách người có quyền"):
        BT.mo_nguon(LINK, nguoi_hoi=OWNER)


# ───────────────────────────── kênh job ─────────────────────────────
def test_kenh_chi_job_theo_lich_mang_chung_minh():
    p = {"scheduled": True, "scheduled_by": OWNER, "schedule_id": 3,
         "nguon_da_kiem": _p(), "nguon_loi": "  hết hạn token  "}
    k = P._kenh_cua_job({"id": 1, "payload": p})
    assert k["nguon_da_kiem"] == p["nguon_da_kiem"] and k["scheduled_by"] == OWNER
    assert k["nguon_loi"] == "hết hạn token"


@pytest.mark.parametrize("job", [
    {"id": 2, "reply_to": {"chat_type": "group"},
     "payload": {"text": "/tiendo", "nguon_da_kiem": _p(), "nguon_loi": "x"}},
    {"id": 3, "payload": {"nguon_da_kiem": _p(), "scheduled_by": OWNER}},
    {"id": 4, "reply_to": {"chat_type": "p2p"},
     "payload": {"scheduled": "true", "nguon_da_kiem": _p()}},
])
def test_kenh_tin_thuong_bo_chung_minh(job):
    k = P._kenh_cua_job(job) or {}
    assert "nguon_da_kiem" not in k and "nguon_loi" not in k and not k.get("scheduled")


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
    monkeypatch.setattr(T, "_doc_dong", lambda d, f: [{"record_id": "r", "fields": {
        "Việc": "Gửi brief", "Phụ trách": [{"id": "ou_pic", "name": "An"}],
        "Ngày hết hạn": han, "Status": "Chưa xong"}}])


def _lich(**kw):
    return {"scheduled": True, "scheduled_by": OWNER, "schedule_id": 3, **kw}


def test_tiendo_lich_co_chung_minh_doc_duoc(td):
    text = T.lenh_tiendo(LINK, kenh=_lich(nguon_da_kiem=_p()), chat_id="oc_g")
    assert "Gửi brief" in text and '<at user_id="ou_pic">' in text


def test_tiendo_lich_chung_minh_bang_khac_bi_tu_choi(td):
    text = T.lenh_tiendo(LINK, kenh=_lich(nguon_da_kiem=_p(table_id="tblKhac")), chat_id="oc_g")
    assert "Gửi brief" not in text and "Không đọc" in text


def test_tiendo_lich_nguon_loi(td):
    text = T.lenh_tiendo(LINK, kenh=_lich(nguon_loi="token Lark của người đặt đã hết hạn"),
                         chat_id="oc_g")
    assert "token Lark của người đặt đã hết hạn" in text and "Lịch chạy" in text
    assert "Gửi brief" not in text


def test_tiendo_go_tay_mang_chung_minh_bi_bo_qua_va_huong_dan(td):
    k = {"chat_type": "group", "nguon_da_kiem": _p(), "scheduled_by": OWNER}
    text = T.lenh_tiendo(LINK, kenh=k, sender_open_id=OWNER)
    assert "Gửi brief" not in text
    assert ("thêm bot Mark vào tài liệu (quyền xem), dán link bảng, đặt lịch trên console "
            "(chọn nhóm nhận, giờ)" in text) and "Kết nối" not in text


def test_tool_model_khong_nhan_chung_minh(td, monkeypatch):
    monkeypatch.setattr(BT, "_nguoi_hoi", lambda: OWNER)
    kq = json.loads(T._handle({"nguon": LINK, "nguon_da_kiem": _p()}))
    assert "error" in kq and "danh sách người có quyền" in kq["error"]
