"""`doc_bang` (đọc nguyên Base/Sheet) và `tra_kho` (tra lại kho bằng nhiều bộ từ khoá).

Hai điều quan trọng nhất phải canh:
  • Mark đọc bằng token BOT. Chỉ trả dữ liệu khi CHỨNG MINH được người hỏi cũng có quyền
    — không thì ai dán link Base audit cũng đọc được nhật ký của người khác.
  • Đọc NGUYÊN bảng (mọi trang), cắt thì phải báo `bi_cat`.
Lark giả hoàn toàn — không gọi mạng.
"""
from __future__ import annotations

import json

import pytest

import bang_tool as BT
import kho_tool as KT
import lark_bang as B


# ───────────────────────────── nhận diện link ─────────────────────────────
@pytest.mark.parametrize("vao,ra", [
    ("https://x.larksuite.com/base/AppTok123?table=tblAbc&view=v", ("bitable", "AppTok123", "tblAbc")),
    ("https://x.larksuite.com/sheets/ShtTok9?sheet=s1", ("sheet", "ShtTok9", "s1")),
    ("https://x.larksuite.com/wiki/NodeTok?fromScene=a", ("wiki", "NodeTok", "")),
    ("sheet:JOlss9dX_6KqKhd", ("sheet", "JOlss9dX", "6KqKhd")),
    ("base:app1_tbl1", ("bitable", "app1", "tbl1")),
])
def test_nhan_dien(vao, ra):
    assert B.nhan_dien(vao) == ra


def test_link_la_khong_nhan():
    assert B.nhan_dien("https://google.com") is None


# ───────────────────────────── giá trị ô ─────────────────────────────
def test_gia_tri_cac_kieu_o_base():
    assert B.gia_tri(1727654400000, 5) == "2024-09-30 07:00"
    assert B.gia_tri([{"name": "Thẩm"}, {"name": "Mai"}]) == "Thẩm, Mai"
    assert B.gia_tri([{"text": "a", "type": "text"}, {"text": "b"}]) == "a, b"
    assert B.gia_tri({"type": 1, "value": [{"text": "công thức"}]}) == "công thức"
    assert B.gia_tri(True) == "có" and B.gia_tri(None) == ""


# ───────────────────────────── Lark giả ─────────────────────────────
class LarkGia:
    def __init__(self, bang: dict):
        self.bang = bang          # path (bỏ query) → data, hoặc list trang
        self.goi: list[str] = []

    def __call__(self, method, path, *, query=None, body=None):
        self.goi.append(path)
        v = self.bang.get(path)
        if v is None:
            raise RuntimeError(f"HTTP 403 {path}")
        if isinstance(v, list):                  # phân trang
            i = int((query or {}).get("page_token") or 0)
            trang = dict(v[i])
            if i + 1 < len(v):
                trang.update(has_more=True, page_token=str(i + 1))
            return {"code": 0, "data": trang}
        return {"code": 0, "data": v}


APP = "/open-apis/bitable/v1/apps/appX"


@pytest.fixture
def base_gia(monkeypatch):
    lk = LarkGia({
        APP: {"app": {"name": "Backlog CĐS"}},
        f"{APP}/tables": [{"items": [{"table_id": "t1", "name": "Việc"}]}],
        f"{APP}/tables/t1/fields": [{"items": [{"field_name": "Tên", "type": 1},
                                               {"field_name": "Hạn", "type": 5}]}],
        f"{APP}/tables/t1/records": [
            {"items": [{"fields": {"Tên": [{"text": "Làm A"}], "Hạn": 1727654400000}}]},
            {"items": [{"fields": {"Tên": [{"text": "Làm | B"}]}}]},
        ],
    })
    monkeypatch.setattr(B.lark, "call", lk)
    return lk


def test_doc_base_doc_het_moi_trang(base_gia):
    kq = B.doc("bitable", "appX")
    assert kq["ten"] == "Backlog CĐS" and not kq["bi_cat"]
    assert kq["bang"] == [{"ten": "Việc", "cot": ["Tên", "Hạn"], "tong_dong": 2, "da_doc": 2}]
    assert "| Làm A | 2024-09-30 07:00 |" in kq["noi_dung"]
    assert "Làm \\| B" in kq["noi_dung"], "dấu | trong ô phải được thoát, không phá bảng"


def test_doc_base_vuot_tran_thi_bao_bi_cat(base_gia, monkeypatch):
    monkeypatch.setattr(B, "MAX_DONG", 1)
    kq = B.doc("bitable", "appX")
    assert kq["bi_cat"] and kq["bang"][0]["da_doc"] == 1


def test_doc_sheet_bo_dong_trong_cuoi(monkeypatch):
    S = "/open-apis/sheets/v3/spreadsheets/shtX"
    lk = LarkGia({
        S: {"spreadsheet": {"title": "Scope"}},
        f"{S}/sheets/query": {"sheets": [{"sheet_id": "s1", "title": "Phạm vi",
                                          "grid_properties": {"row_count": 200,
                                                              "column_count": 2}}]},
        "/open-apis/sheets/v2/spreadsheets/shtX/values/s1!A1:B200": {"valueRange": {
            "values": [["Hạng mục", "Trong phạm vi"], ["CRM", "có"], ["ERP", "không"],
                       [None, None], ["", ""]]}},
    })
    monkeypatch.setattr(B.lark, "call", lk)
    kq = B.doc("sheet", "shtX")
    assert kq["bang"][0]["tong_dong"] == 2 and not kq["bi_cat"]
    assert "| ERP | không |" in kq["noi_dung"]


def test_the_muc_luc_chi_cach_goi_doc_bang(base_gia):
    kq = B.doc("bitable", "appX", ca_dong=False)
    the = B.the_muc_luc(kq, "https://x/wiki/n1")
    assert "Việc (" in the and "`doc_bang` với `https://x/wiki/n1`" in the


# ───────────────────────────── quyền người hỏi ─────────────────────────────
@pytest.fixture
def quyen(monkeypatch):
    monkeypatch.delenv("AGENT_BOSS_OPEN_ID", raising=False)
    monkeypatch.delenv("STEVEN_BOSS_OPEN_ID", raising=False)
    monkeypatch.setattr(BT, "_trong_cay_wiki", lambda *t: False)
    monkeypatch.setattr(BT, "_trong_chat", lambda c, n: False)

    def dat(public="closed", members=None):
        lk = LarkGia({
            "/open-apis/drive/v2/permissions/tok/public":
                {"permission_public": {"link_share_entity": public}},
            **({"/open-apis/drive/v1/permissions/tok/members": [{"items": members}]}
               if members is not None else {}),
        })
        monkeypatch.setattr(BT.lark, "call", lk)
        monkeypatch.setattr(B.lark, "call", lk)
    return dat


def test_nguoi_ngoai_khong_doc_duoc_du_bot_doc_duoc(quyen):
    quyen(members=[{"member_type": "openid", "member_id": "ou_khac"}])
    ok, vi_sao = BT.quyen_nguoi_hoi("bitable", "tok", "ou_hoi")
    assert not ok and "chưa thấy bạn" in vi_sao


def test_thanh_vien_doc_duoc(quyen):
    quyen(members=[{"member_type": "openid", "member_id": "ou_hoi"}])
    assert BT.quyen_nguoi_hoi("bitable", "tok", "ou_hoi") == (True, "là thành viên")


def test_mo_ca_cong_ty_doc_duoc(quyen):
    quyen(public="tenant_readable")
    assert BT.quyen_nguoi_hoi("sheet", "tok", "ou_hoi")[0]


def test_qua_nhom_chat_doc_duoc(quyen, monkeypatch):
    quyen(members=[{"member_type": "openchat", "member_id": "oc_1"}])
    monkeypatch.setattr(BT, "_trong_chat", lambda c, n: c == "oc_1" and n == "ou_hoi")
    assert BT.quyen_nguoi_hoi("bitable", "tok", "ou_hoi") == (True, "thuộc nhóm chat được chia sẻ")


def test_trong_nguon_wiki_doc_duoc(quyen, monkeypatch):
    quyen()
    monkeypatch.setattr(BT, "_trong_cay_wiki", lambda *t: "tok" in t)
    assert BT.quyen_nguoi_hoi("bitable", "tok", "")[0]


def test_chu_agent_doc_duoc(quyen, monkeypatch):
    quyen()
    monkeypatch.setenv("AGENT_BOSS_OPEN_ID", "ou_chu")
    assert BT.quyen_nguoi_hoi("bitable", "tok", "ou_chu") == (True, "chủ agent")


def test_khong_biet_ai_hoi_thi_dong(quyen):
    quyen(members=[{"member_type": "openid", "member_id": "ou_hoi"}])
    assert not BT.quyen_nguoi_hoi("bitable", "tok", "")[0]


def test_khong_xem_duoc_danh_sach_thi_dong(quyen):
    quyen(members=None)        # API members lỗi
    ok, vi_sao = BT.quyen_nguoi_hoi("bitable", "tok", "ou_hoi")
    assert not ok and "không xem được danh sách" in vi_sao


def test_tu_choi_thi_khong_doc_bang(quyen, monkeypatch):
    quyen(members=[])
    monkeypatch.setattr(BT, "_nguoi_hoi", lambda: "ou_hoi")
    doc = []
    monkeypatch.setattr(B, "doc", lambda *a, **k: doc.append(a))
    r = json.loads(BT._handle({"nguon": "https://x.larksuite.com/base/tok"}))
    assert "error" in r and "CHÍNH người hỏi" in r["error"]
    assert doc == [], "bị từ chối mà vẫn đọc là rò dữ liệu"


def test_node_wiki_la_tai_lieu_thi_khong_doc(monkeypatch):
    monkeypatch.setattr(B, "giai_wiki", lambda n: ("docx", "doc1"))
    r = json.loads(BT._handle({"nguon": "https://x.larksuite.com/wiki/n1"}))
    assert "không phải Base hay Sheet" in r["error"]


# ───────────────────────────── tra_kho ─────────────────────────────
def test_gop_bo_trung_va_uu_tien_mau_khop_nhieu_bo():
    kq = KT.gop({
        "doanh thu": [{"item_id": "a", "title": "Báo cáo", "score": 0.9, "content": "x"}],
        "revenue": [{"item_id": "b", "title": "Revenue Q3", "score": 2.0},
                    {"item_id": "a", "title": "Báo cáo", "score": 0.5}],
    })
    assert [m["tieu_de"] for m in kq] == ["Báo cáo", "Revenue Q3"]
    assert kq[0]["khop_bo"] == ["doanh thu", "revenue"]


def test_tra_kho_mat_ket_noi_thi_khong_ket_luan_kho_trong(monkeypatch):
    monkeypatch.setattr(KT, "_tim", lambda q: None)
    r = json.loads(KT._handle({"tu_khoa": ["doanh thu", "revenue"]}))
    assert "đừng kết luận kho không có" in r["error"]


def test_tra_kho_toi_da_sau_bo_va_bo_trung(monkeypatch):
    da = []
    monkeypatch.setattr(KT, "_tim", lambda q: da.append(q) or [])
    KT._handle({"tu_khoa": ["a", "a", "b", "c", "d", "e", "f", "g"]})
    assert da == ["a", "b", "c", "d", "e", "f"]


def test_brain_luon_nhac_tra_kho_tru_khi_web():
    import pathlib
    s = (pathlib.Path(__file__).resolve().parents[1] / "brain.py").read_text(encoding="utf-8")
    assert 'if nguon != "/web":\n' in s and "lines += _LUAT_TRA_KHO" in s
    assert "import bang_tool" in s and "import kho_tool" in s
