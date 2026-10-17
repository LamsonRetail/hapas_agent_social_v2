"""`doc_tai_lieu` — đọc tài liệu Lark Docs/Wiki, CHỈ khi người hỏi cũng được xem.

Canh ba điều (audit 07/10/2026, link Wiki "MASTER PLAN 20.10 Copy"):
  • Mark đọc bằng token BOT → chỉ trả nội dung khi CHỨNG MINH được người hỏi có quyền, bằng
    ĐÚNG `bang_tool.quyen_nguoi_hoi` của doc_bang (không luật thứ hai).
  • Lỗi phải chỉ bước tiếp: bot chưa được chia sẻ → nhờ thêm bot; người hỏi chưa được xem →
    lý do từ quyen_nguoi_hoi.
  • Tài liệu dài: trả từng đoạn có tổng độ dài và chỗ đọc tiếp — không cắt im lặng.
Lark giả hoàn toàn — không gọi mạng.
"""
from __future__ import annotations

import json

import pytest

import bang_tool as BT
import doc_tai_lieu_tool as D
import lark_client
import lsr_policy

DOCX = "doxTok123"
NODE = "wikNode456"
NGAN = "ou_ngan"


class LarkGia:
    """(method, path) hoặc path → data | hàm(query, body) → data. Không có → lỗi 403."""

    def __init__(self, tuyen: dict):
        self.tuyen = dict(tuyen)
        self.goi: list[tuple] = []

    def __call__(self, method, path, *, query=None, body=None):
        self.goi.append((method, path, query, body))
        v = self.tuyen.get((method, path), self.tuyen.get(path))
        if v is None:
            raise RuntimeError(f"Lark {method} {path} failed: HTTP 403: forbidden")
        if callable(v):
            v = v(query or {}, body)
        return {"code": 0, "data": v}

    def da_goi(self, doan: str) -> bool:
        return any(doan in p for _, p, _, _ in self.goi)


def _chu(s: str) -> dict:
    return {"elements": [{"text_run": {"content": s}}]}


def _khoi_mau() -> list[dict]:
    return [
        {"block_id": "pg", "block_type": 1, "page": _chu("MASTER PLAN 20.10"),
         "children": ["h1", "p1", "b1", "h2", "tb", "sh", "img", "h3", "p3"]},
        {"block_id": "h1", "block_type": 3, "heading1": _chu("1. Mục tiêu")},
        {"block_id": "p1", "block_type": 2, "text": {"elements": [
            {"text_run": {"content": "Doanh thu "}}, {"text_run": {"content": "2 tỷ"}},
            {"mention_user": {"user_id": "ou_x"}}]}},
        {"block_id": "b1", "block_type": 12, "bullet": _chu("Kênh TikTok"), "children": ["b2"]},
        {"block_id": "b2", "block_type": 12, "bullet": _chu("Booking 20 KOC")},
        {"block_id": "h2", "block_type": 4, "heading2": _chu("2. Ngân sách")},
        {"block_id": "tb", "block_type": 31, "table": {
            "property": {"row_size": 2, "column_size": 2},
            "cells": ["c1", "c2", "c3", "c4"]}, "children": ["c1", "c2", "c3", "c4"]},
        {"block_id": "c1", "block_type": 32, "table_cell": {}, "children": ["t1"]},
        {"block_id": "c2", "block_type": 32, "table_cell": {}, "children": ["t2"]},
        {"block_id": "c3", "block_type": 32, "table_cell": {}, "children": ["t3"]},
        {"block_id": "c4", "block_type": 32, "table_cell": {}, "children": ["t4"]},
        {"block_id": "t1", "block_type": 2, "text": _chu("Hạng mục")},
        {"block_id": "t2", "block_type": 2, "text": _chu("Tiền")},
        {"block_id": "t3", "block_type": 2, "text": _chu("Ads | Meta")},
        {"block_id": "t4", "block_type": 2, "text": _chu("500.000.000")},
        {"block_id": "sh", "block_type": 30, "sheet": {"token": "shtAbc_s1"}},
        {"block_id": "img", "block_type": 27, "image": {"token": "img1"}},
        {"block_id": "h3", "block_type": 4, "heading2": _chu("3. Lịch")},
        {"block_id": "p3", "block_type": 2, "text": _chu("Tuần 1 quay, tuần 2 đăng")},
    ]


def _tuyen(khoi=None, *, thanh_vien=(NGAN,), cong_ty=False, bot_doc=True) -> dict:
    t = {
        f"/open-apis/drive/v2/permissions/{DOCX}/public": {"permission_public": {
            "link_share_entity": "tenant_readable" if cong_ty else "closed"}},
        f"/open-apis/drive/v1/permissions/{DOCX}/members": {"items": [
            {"member_type": "openid", "member_id": x} for x in thanh_vien]},
        ("POST", "/open-apis/drive/v1/metas/batch_query"): {"metas": [
            {"doc_token": DOCX, "latest_modify_time": "1760000000"}]},
    }
    if bot_doc:
        t[f"/open-apis/docx/v1/documents/{DOCX}"] = {"document": {
            "document_id": DOCX, "revision_id": 7, "title": "MASTER PLAN 20.10 Copy"}}
        t[f"/open-apis/docx/v1/documents/{DOCX}/blocks"] = {
            "items": khoi if khoi is not None else _khoi_mau()}
    return t


@pytest.fixture(autouse=True)
def _moi_truong(monkeypatch):
    monkeypatch.delenv("AGENT_BOSS_OPEN_ID", raising=False)
    monkeypatch.delenv("STEVEN_BOSS_OPEN_ID", raising=False)
    monkeypatch.setattr(BT, "_nguoi_hoi", lambda: NGAN)
    monkeypatch.setattr(BT, "base_noi_bo", lambda: set())
    monkeypatch.setattr(BT, "_trong_cay_wiki", lambda *a: False)
    D._NHO.clear()
    yield
    D._NHO.clear()


def _gia(monkeypatch, tuyen) -> LarkGia:
    g = LarkGia(tuyen)
    monkeypatch.setattr(lark_client, "call", g)
    return g


def _goi(**a) -> dict:
    return json.loads(D._handle(a))


LINK = f"https://o4pvcegwn6b.sg.larksuite.com/docx/{DOCX}"


# ───────────────────────────── quyền ─────────────────────────────
def test_thanh_vien_doc_duoc_kem_ten_va_lan_sua(monkeypatch):
    g = _gia(monkeypatch, _tuyen())
    r = _goi(nguon=LINK)
    assert "error" not in r, r
    assert r["ten"] == "MASTER PLAN 20.10 Copy"
    assert r["ly_do_duoc_doc"] == "là thành viên"
    assert r["sua_lan_cuoi"].endswith("(giờ VN)") and r["sua_lan_cuoi"].startswith("09/10/2025")
    assert "# 1. Mục tiêu" in r["noi_dung"] and "Doanh thu 2 tỷ@(người dùng)" in r["noi_dung"]
    assert r["con_tiep"] is False and r["goi_tiep"] is None
    assert r["tong_ky_tu"] == len(r["noi_dung"])
    # Quyền kiểm bằng API quyền drive với type=docx.
    q = [q for _, p, q, _ in g.goi if p.endswith(f"{DOCX}/members")]
    assert q and q[0]["type"] == "docx"


def test_mo_cho_ca_cong_ty_thi_doc_duoc(monkeypatch):
    _gia(monkeypatch, _tuyen(thanh_vien=(), cong_ty=True))
    r = _goi(nguon=LINK)
    assert r["ly_do_duoc_doc"] == "mở cho cả công ty"


def test_nguoi_hoi_chua_duoc_xem_thi_tu_choi_va_khong_doc_noi_dung(monkeypatch):
    g = _gia(monkeypatch, _tuyen(thanh_vien=("ou_khac",)))
    r = _goi(nguon=LINK)
    assert "chưa thấy bạn trong danh sách người có quyền" in r["error"]
    assert "Mark chỉ đọc tài liệu mà CHÍNH người hỏi cũng được xem" in r["error"]
    assert "MASTER PLAN" not in r["error"], "không lộ tiêu đề khi chưa chứng minh quyền"
    assert not g.da_goi("/blocks") and not g.da_goi("raw_content"), \
        "không đọc nội dung khi người hỏi chưa được chứng minh có quyền"


def test_khong_biet_ai_hoi_thi_dong(monkeypatch):
    monkeypatch.setattr(BT, "_nguoi_hoi", lambda: "")
    _gia(monkeypatch, _tuyen())
    r = _goi(nguon=LINK)
    assert "Console chưa chuyển danh tính Lark" in r["error"]


def test_nguon_wiki_chu_agent_khai_bao_dung_luat_chung(monkeypatch):
    """Cùng luật với doc_bang: tài liệu nằm trong Nguồn Wiki chủ agent khai báo thì đọc được."""
    monkeypatch.setattr(BT, "_trong_cay_wiki", lambda *t: DOCX in t)
    _gia(monkeypatch, _tuyen(thanh_vien=()))
    r = _goi(nguon=LINK)
    assert r["ly_do_duoc_doc"] == "nằm trong Nguồn Wiki chủ agent đã khai báo"


def test_dung_chung_quyen_nguoi_hoi(monkeypatch):
    """Không có luật quyền thứ hai: mo_tai_lieu gọi đúng `quyen_nguoi_hoi`."""
    goi = []

    def gia(loai, token, nguoi, *wiki, **kw):
        goi.append((loai, token, nguoi, wiki))
        return False, "lý do giả từ quyen_nguoi_hoi"
    monkeypatch.setattr(BT, "quyen_nguoi_hoi", gia)
    _gia(monkeypatch, _tuyen())
    r = _goi(nguon=LINK)
    assert goi == [("docx", DOCX, NGAN, ("",))]
    assert "lý do giả từ quyen_nguoi_hoi" in r["error"]


# ───────────────────────────── bot chưa được chia sẻ ─────────────────────────────
def test_bot_chua_duoc_chia_se_thi_chi_cach_them_bot(monkeypatch):
    _gia(monkeypatch, _tuyen(bot_doc=False))
    r = _goi(nguon=LINK)
    assert "thêm bot 'Mark Trần - Social Assistant' quyền xem" in r["error"]
    assert "danh sách người có quyền" not in r["error"], \
        "bot chưa được chia sẻ thì đường sửa là thêm bot, không phải lỗi tra thành viên"


def test_wiki_khong_mo_duoc_thi_chi_cach_them_bot(monkeypatch):
    _gia(monkeypatch, _tuyen())
    r = _goi(nguon=f"https://x.larksuite.com/wiki/{NODE}")
    assert "thêm bot 'Mark Trần - Social Assistant' quyền xem" in r["error"]


# ───────────────────────────── Wiki ─────────────────────────────
def test_wiki_giai_ra_docx_thi_doc(monkeypatch):
    t = _tuyen()
    t["/open-apis/wiki/v2/spaces/get_node"] = {"node": {
        "node_token": NODE, "obj_type": "docx", "obj_token": DOCX,
        "title": "MASTER PLAN 20.10 Copy", "obj_edit_time": "1760001000"}}
    g = _gia(monkeypatch, t)
    seen = []
    goc = BT.quyen_nguoi_hoi

    def soi(*a, **kw):
        seen.append(a)
        return goc(*a, **kw)
    monkeypatch.setattr(BT, "quyen_nguoi_hoi", soi)
    r = _goi(nguon=f"https://o4pvcegwn6b.sg.larksuite.com/wiki/{NODE}?from=x")
    assert "error" not in r, r
    assert r["loai"].endswith("(trang Wiki)") and r["ten"] == "MASTER PLAN 20.10 Copy"
    assert seen == [("docx", DOCX, NGAN, NODE)], "node Wiki được truyền như mo_nguon"
    assert not g.da_goi("metas/batch_query"), "đã có obj_edit_time của node, không hỏi thêm"


@pytest.mark.parametrize("loai,ten", [("sheet", "Sheet"), ("bitable", "Base")])
def test_wiki_giai_ra_bang_thi_chi_sang_doc_bang(monkeypatch, loai, ten):
    t = _tuyen()
    t["/open-apis/wiki/v2/spaces/get_node"] = {"node": {"obj_type": loai, "obj_token": "x1"}}
    g = _gia(monkeypatch, t)
    r = _goi(nguon=f"https://x.larksuite.com/wiki/{NODE}")
    assert f"là một {ten}" in r["error"] and "doc_bang" in r["error"]
    assert not g.da_goi("/members"), "không kiểm quyền / đọc gì khi sai loại"


def test_doc_bang_chi_sang_doc_tai_lieu_khi_wiki_la_docx(monkeypatch):
    monkeypatch.setattr(BT.B, "giai_wiki", lambda n: ("docx", DOCX))
    r = json.loads(BT._handle({"nguon": f"https://x.larksuite.com/wiki/{NODE}"}))
    assert "không phải Base hay Sheet" in r["error"] and "doc_tai_lieu" in r["error"]


# ───────────────────────────── trình bày ─────────────────────────────
def test_markdown_giu_cau_truc_va_danh_dau_khoi_khong_doc_duoc():
    td, md = D.ra_markdown(_khoi_mau())
    assert td == "MASTER PLAN 20.10"
    assert "- Kênh TikTok\n  - Booking 20 KOC" in md
    assert "| Hạng mục | Tiền |" in md and "| Ads \\| Meta | 500.000.000 |" in md
    assert "`sheet:shtAbc_s1`" in md, "Sheet nhúng chỉ đường doc_bang, không đọc lén"
    assert "[Ảnh" in md
    assert md.count("Hạng mục") == 1, "ô bảng không bị in lại ngoài bảng"


def test_khoi_mo_coi_khong_bi_mat():
    khoi = _khoi_mau() + [{"block_id": "le", "block_type": 2, "text": _chu("đoạn lạc")}]
    _, md = D.ra_markdown(khoi)
    assert "đoạn lạc" in md


def test_doc_khoi_hong_thi_lui_ve_chu_thuan(monkeypatch):
    t = _tuyen()
    del t[f"/open-apis/docx/v1/documents/{DOCX}/blocks"]
    t[f"/open-apis/docx/v1/documents/{DOCX}/raw_content"] = {"content": "Chữ thuần đủ"}
    _gia(monkeypatch, t)
    r = _goi(nguon=LINK)
    assert r["noi_dung"] == "Chữ thuần đủ" and "chữ thuần" in r["cach_doc"]


# ───────────────────────────── tài liệu dài ─────────────────────────────
def _khoi_dai(so_doan: int = 80) -> list[dict]:
    con, khoi = [], []
    for i in range(so_doan):
        if i % 20 == 0:
            khoi.append({"block_id": f"h{i}", "block_type": 3,
                         "heading1": _chu(f"Phần {i // 20 + 1}")})
            con.append(f"h{i}")
        khoi.append({"block_id": f"p{i}", "block_type": 2,
                     "text": _chu(f"Đoạn {i:03d} " + "x" * 900)})
        con.append(f"p{i}")
    return [{"block_id": "pg", "block_type": 1, "page": _chu("Dài"), "children": con}] + khoi


def test_tai_lieu_dai_tra_tung_doan_khong_mat_chu(monkeypatch):
    _gia(monkeypatch, _tuyen(_khoi_dai()))
    _, md = D.ra_markdown(_khoi_dai())
    assert len(md) > 2 * D.MAX_KY_TU
    ghep, tu, lan = "", 0, 0
    while True:
        r = _goi(nguon=LINK, tu_ky_tu=tu, phien_ban=7)
        assert r["tong_ky_tu"] == len(md) and r["tu_ky_tu"] == tu
        assert len(r["noi_dung"]) <= D.MAX_KY_TU
        ghep += r["noi_dung"]
        lan += 1
        if not r["con_tiep"]:
            assert r["goi_tiep"] is None and r["den_ky_tu"] == len(md)
            break
        assert r["muc_luc"][0]["muc"] == "Phần 1", "tài liệu dài kèm mục lục"
        tu = r["goi_tiep"]["tu_ky_tu"]
        assert r["noi_dung"].endswith("\n"), "cắt ở cuối dòng, không giữa câu"
    assert ghep == md, "ghép các đoạn phải ra đủ tài liệu"
    assert lan >= 3


def test_doc_dung_mot_muc(monkeypatch):
    _gia(monkeypatch, _tuyen(_khoi_dai()))
    r = _goi(nguon=LINK, muc="phan 2")
    assert r["pham_vi"] == "mục 'Phần 2'"
    assert r["noi_dung"].startswith("# Phần 2") and "Đoạn 020" in r["noi_dung"]
    assert "Đoạn 019" not in r["noi_dung"] and "Đoạn 040" not in r["noi_dung"]
    assert r["tong_ky_tu_ca_tai_lieu"] > r["tong_ky_tu"]


def test_muc_khong_co_thi_liet_ke_muc(monkeypatch):
    _gia(monkeypatch, _tuyen())
    r = _goi(nguon=LINK, muc="Không có")
    assert "Không thấy mục" in r["error"] and "2. Ngân sách" in r["error"]


def test_doc_tiep_dung_bo_nho_tam_nhung_van_kiem_quyen(monkeypatch):
    g = _gia(monkeypatch, _tuyen(_khoi_dai()))
    _goi(nguon=LINK)
    _goi(nguon=LINK, tu_ky_tu=D.MAX_KY_TU, phien_ban=7)
    assert sum(p.endswith("/blocks") for _, p, _, _ in g.goi) == 1
    assert sum(p.endswith("/members") for _, p, _, _ in g.goi) == 2, \
        "quyền người hỏi kiểm lại ở MỖI lần đọc"


# ───────────────────────────── nhận link + bản cũ ─────────────────────────────
@pytest.mark.parametrize("vao,ra", [
    ("https://x.larksuite.com/docx/AbC123?from=1", ("docx", "AbC123")),
    ("https://x.larksuite.com/docs/doccnOld1", ("doc", "doccnOld1")),
    ("https://x.larksuite.com/wiki/NodeX", ("wiki", "NodeX")),
    ("docx:AbC123", ("docx", "AbC123")),
    ("AbCdEfGhIjKlMnOpQr", ("?", "AbCdEfGhIjKlMnOpQr")),
])
def test_nhan_dien_tai_lieu(vao, ra):
    assert BT.nhan_dien_tai_lieu(vao) == ra


def test_link_la_thi_noi_ro():
    r = _goi(nguon="https://google.com/x")
    assert "Không nhận ra link tài liệu" in r["error"]


def test_tai_lieu_ban_cu(monkeypatch):
    tok = "doccnOld1"
    _gia(monkeypatch, {
        f"/open-apis/doc/v2/{tok}/raw_content": {"content": "Nội dung bản cũ"},
        f"/open-apis/drive/v2/permissions/{tok}/public": {"permission_public": {}},
        f"/open-apis/drive/v1/permissions/{tok}/members": {"items": [
            {"member_type": "openid", "member_id": NGAN}]},
    })
    r = _goi(nguon=f"https://x.larksuite.com/docs/{tok}")
    assert r["noi_dung"] == "Nội dung bản cũ" and r["sua_lan_cuoi"] is None


# ───────────────────────────── đăng ký + policy ─────────────────────────────
def test_policy_chi_doc_va_lui_ve_cong_tac_doc_bang():
    assert "doc_tai_lieu" in lsr_policy._SAFE_EXACT
    assert "doc_tai_lieu" not in lsr_policy._MUTATING_EXACT
    assert lsr_policy._CONG_TAC_LUI["doc_tai_lieu"] == "doc_bang"
    assert lsr_policy.decide("doc_tai_lieu", {"nguon": LINK}).allowed


def test_tat_doc_bang_tren_console_thi_tat_luon_doc_tai_lieu(monkeypatch):
    monkeypatch.setattr(lsr_policy, "_nho_nl", {"bat": {"lark_cli"}, "luc": float("inf"),
                                                "nguon": "test", "tat_ro": set()})
    d = lsr_policy.decide("doc_tai_lieu", {"nguon": LINK})
    assert not d.allowed and "doc_bang" in d.reason


def test_lark_cli_docs_fetch_bi_tu_choi_chi_sang_doc_tai_lieu():
    d = lsr_policy.decide("lark_cli", {"args": ["docs", "+fetch", "--doc", DOCX,
                                                "--doc-format", "markdown"]})
    assert not d.allowed and "doc_tai_lieu" in d.reason


def test_dang_ky_trong_brain():
    import brain
    assert "doc_tai_lieu" in brain._TOOL_CAN_XET
    s = (__import__("pathlib").Path(brain.__file__)).read_text(encoding="utf-8")
    assert "import doc_tai_lieu_tool" in s
