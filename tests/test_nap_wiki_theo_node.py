"""Nhập Wiki theo từng node: mặc định cả node, tuỳ chọn tách H1 hoặc bỏ qua.

Lý do có luồng này (30/09): quét Wiki "Automation" ra toàn Daily Standup — tài liệu đó
có 64 H1 theo ngày nên thành 64 mục, còn "Scope" không dùng H1 nên bị bỏ CẢ tài liệu.

Block giả thay cho Lark: 2 = chữ thường, 3/4/5 = H1/H2/H3.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

import pytest

GOC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GOC / "scripts"))
import nap_wiki as W  # noqa: E402


def _b(loai: int, chu: str) -> dict:
    khoa = "text" if loai == 2 else f"heading{loai - 2}"
    return {"block_type": loai, "block_id": f"blk_{chu[:6]}",
            khoa: {"elements": [{"text_run": {"content": chu}}]}}


TAI_LIEU = {
    "doc_standup": [_b(2, "Ghi chép hằng ngày"), _b(3, "29/09/2026"), _b(2, "đã xong A"),
                    _b(3, "28/09/2026"), _b(2, "đã xong B"), _b(3, "27/09/2026"),
                    _b(2, "đã xong C")],
    "doc_scope": [_b(2, "Phạm vi dự án CĐS"), _b(5, "Ngoài phạm vi"), _b(2, "không làm ERP")],
    "doc_rong": [],
}


MUC_LUC_BASE = {"ten": "Backlog", "loai": "Base", "bi_cat": False, "noi_dung": "",
                "bang": [{"ten": "Việc", "cot": ["Tên", "Trạng thái"], "tong_dong": 42,
                          "da_doc": 0}]}


@pytest.fixture(autouse=True)
def _lark_gia(monkeypatch):
    import lark_bang

    def doc_gia(loai, tok, phu="", *, ca_dong=True):
        if tok != "bas_1":
            raise RuntimeError("bot không có quyền")
        return MUC_LUC_BASE

    monkeypatch.setattr(W, "lay_block", lambda tok: TAI_LIEU.get(tok))
    monkeypatch.setattr(lark_bang, "doc", doc_gia)


def _node(tok, ten, loai="docx", obj=None, sau=1):
    return {"token": tok, "title": ten, "obj_type": loai, "obj_token": obj, "sau": sau}


STANDUP = _node("wk_standup", "Daily Standup", obj="doc_standup")
SCOPE = _node("wk_scope", "Scope", obj="doc_scope")
BACKLOG = _node("wk_backlog", "Backlog CĐS", loai="bitable", obj="bas_1")


def _ct(chi_tiet, tok):
    return next(c for c in chi_tiet if c["token"] == tok)


def test_mac_dinh_moi_node_la_mot_tai_lieu_va_khong_mat_tai_lieu_khong_co_h1():
    ra, _, ct = W.boc([STANDUP, SCOPE])
    assert len(ra) == 2, "mặc định phải là một node một tài liệu"
    assert _ct(ct, "wk_standup")["h1"] == 3 and _ct(ct, "wk_standup")["muc"] == 1
    scope = next(d for d in ra if "Scope" in d["name"])
    assert "không làm ERP" in scope["content"], "tài liệu không có H1 không được bị bỏ"


def test_ca_node_giu_tieu_de_trong_noi_dung():
    """Platform cắt mẩu ~1.200 ký tự; mất tiêu đề thì 'đã xong A' không biết của ngày nào."""
    ra, _, _ = W.boc([STANDUP])
    c = ra[0]["content"]
    assert c.startswith("# Daily Standup")
    assert "## 29/09/2026" in c and c.index("## 29/09/2026") < c.index("đã xong A")
    assert "Ghi chép hằng ngày" in c, "cả node thì giữ cả phần trước H1 đầu tiên"


def test_ten_ca_node_on_dinh_giua_hai_lan_nhap():
    """API kiến thức thay theo tên — tên đổi mỗi lần là sinh bản trùng thay vì thay thế."""
    a, _, _ = W.boc([STANDUP])
    b, _, _ = W.boc([STANDUP])
    assert a[0]["name"] == b[0]["name"] and a[0]["name"].startswith("wiki_Daily_Standup-")
    assert a[0]["source_url"].endswith("/wiki/wk_standup")


def test_tach_h1_giu_nguyen_ten_cu_de_nhap_lai_la_thay_the():
    ra, _, ct = W.boc([STANDUP], {"wk_standup": W.THEO_H1})
    assert len(ra) == 3 and _ct(ct, "wk_standup")["muc"] == 3
    vt = hashlib.sha256("wk_standup|0|29/09/2026".encode()).hexdigest()[:6]
    assert ra[0]["name"] == f"wiki_Daily_Standup-29092026-{vt}.md", "công thức tên cũ đã đổi"


def test_tach_h1_ma_khong_co_h1_thi_nhap_ca_node_va_noi_ro():
    ra, _, ct = W.boc([SCOPE], {"wk_scope": W.THEO_H1})
    assert len(ra) == 1 and "không làm ERP" in ra[0]["content"]
    assert "không có tiêu đề H1" in _ct(ct, "wk_scope")["ly_do"]


def test_bo_qua_va_lua_chon_la_thi_ve_mac_dinh():
    ra, _, ct = W.boc([STANDUP, SCOPE], {"wk_standup": W.BO_QUA, "wk_scope": "lung_tung"})
    assert [d["name"].split("-")[0] for d in ra] == ["wiki_Scope"]
    assert _ct(ct, "wk_standup")["ly_do"] == "chủ agent chọn bỏ qua"
    assert _ct(ct, "wk_scope")["che_do"] == W.CA_NODE


def test_base_nhap_the_muc_luc_khong_nhap_dong():
    """RAG chỉ đưa 4 mẩu — dòng của bảng không vào kho; kho giữ mục lục để TÌM thấy."""
    ra, _, ct = W.boc([BACKLOG])
    assert len(ra) == 1 and _ct(ct, "wk_backlog")["muc"] == 1
    c = ra[0]["content"]
    assert "Việc (42 dòng): cột Tên, Trạng thái" in c
    assert "doc_bang" in c and "/wiki/wk_backlog" in c
    assert _ct(ct, "wk_backlog")["obj_token"] == "bas_1"


def test_base_bot_khong_doc_duoc_thi_noi_ro():
    ra, _, ct = W.boc([_node("wk_b2", "Base khác", loai="bitable", obj="bas_khong")])
    assert ra == [] and _ct(ct, "wk_b2")["ly_do"] == "bot không đọc được bảng này"


def test_tai_lieu_trong_co_ly_do():
    ra, _, ct = W.boc([_node("wk_rong", "Trống", obj="doc_rong")])
    assert ra == [] and _ct(ct, "wk_rong")["ly_do"] == "tài liệu trống"


def test_tai_lieu_chi_nhung_sheet_van_vao_kho_de_tim_thay(monkeypatch):
    """Đúng ca "Scope" (30/09): tiêu đề trang + một Sheet nhúng, không có chữ nào. Phải
    vào kho (để RAG tìm thấy "Scope") kèm mã đọc bảng qua doc_bang."""
    monkeypatch.setitem(TAI_LIEU, "doc_sheet", [
        {"block_type": 1, "page": {"elements": [{"text_run": {"content": "Scope"}}]}},
        {"block_type": 30, "sheet": {"token": "shtAbc_6KqK"}}, _b(2, "")])
    ra, _, ct = W.boc([_node("wk_sheet", "Scope", obj="doc_sheet")])
    assert len(ra) == 1 and "`sheet:shtAbc_6KqK`" in ra[0]["content"]
    assert _ct(ct, "wk_sheet")["nhung"] == ["sheet:shtAbc_6KqK"]
    assert "1 bảng nhúng" in _ct(ct, "wk_sheet")["ly_do"]


def test_bang_nhung_trong_muc_h1_cung_giu_ma(monkeypatch):
    monkeypatch.setitem(TAI_LIEU, "doc_kem", [_b(3, "Kế hoạch"), _b(2, "Mô tả dự án"),
                                             {"block_type": 18, "bitable": {"token": "app1_tbl1"}}])
    ra, _, _ = W.boc([_node("wk_kem", "Kèm Base", obj="doc_kem")], {"wk_kem": W.THEO_H1})
    assert len(ra) == 1 and "`base:app1_tbl1`" in ra[0]["content"]


def test_node_dai_qua_thi_cat_va_bao(monkeypatch):
    monkeypatch.setitem(TAI_LIEU, "doc_dai", [_b(2, "x" * (W.MAX_KY_TU_NODE + 500))])
    ra, _, ct = W.boc([_node("wk_dai", "Dài", obj="doc_dai")])
    assert len(ra[0]["content"]) < W.MAX_KY_TU_NODE + 500
    assert "Tách theo H1" in _ct(ct, "wk_dai")["ly_do"]


# ───────────────────────────── dọn tài liệu cũ ─────────────────────────────

LINK = "https://o4pvcegwn6b.sg.larksuite.com/wiki"


def test_don_dung_ban_cu_cua_node_vua_doc_duoc():
    _, _, ct = W.boc([STANDUP, SCOPE, _node("wk_mat_quyen", "Mất quyền", obj="doc_khong_co")])
    da_co = [
        {"name": "wiki_Daily_Standup-29092026-aaaaaa.md", "source_url": f"{LINK}/wk_standup#blk"},
        {"name": "wiki_Scope-bbbbbb.md", "source_url": f"{LINK}/wk_scope"},
        {"name": "wiki_Mat-cccccc.md", "source_url": f"{LINK}/wk_mat_quyen"},
        {"name": "wiki_Ngoai_cay-dddddd.md", "source_url": f"{LINK}/wk_da_roi_cay"},
        {"name": "SS27_research.md", "source_url": None},
    ]
    xoa = W.ten_can_don(da_co, {"wiki_Scope-bbbbbb.md"}, ct)
    assert xoa == ["wiki_Daily_Standup-29092026-aaaaaa.md"], (
        "chỉ dọn bản cũ của node vừa ĐỌC ĐƯỢC; giữ node mất quyền, node rời cây, và .md tay")


def test_don_goi_api_xoa_mot_lan():
    _, _, ct = W.boc([STANDUP])
    goi_lai = []

    def goi(duong, body=None):
        goi_lai.append(body)
        if body is None:
            return 200, {"documents": [
                {"name": "wiki_Daily_Standup-cu-111111.md", "source_url": f"{LINK}/wk_standup"}]}
        return 200, {"n_files": len(body["delete"])}

    assert W.don_tai_lieu_cu({"wiki_moi.md"}, ct, goi) == 1
    assert goi_lai[-1] == {"delete": ["wiki_Daily_Standup-cu-111111.md"]}


def test_don_khong_doc_duoc_kho_thi_khong_xoa_gi():
    assert W.don_tai_lieu_cu(set(), [], lambda d, body=None: (500, {})) == 0


# ─────────────────────────── nhịp nền (wiki_tu_dong) ───────────────────────────

@pytest.fixture
def wt(monkeypatch):
    sys.path.insert(0, str(GOC))
    import wiki_tu_dong
    monkeypatch.setattr(wiki_tu_dong, "_khoa_nguoi", lambda: "phien")
    return wiki_tu_dong


def test_bao_len_console_chi_gui_last_scan(wt, monkeypatch):
    """Gửi cả khai báo cũ là đè lựa chọn người dùng vừa đổi trong lúc quét."""
    thay = {}
    monkeypatch.setattr(wt, "_goi", lambda url, **kw: (thay.update(kw), (200, {}))[1])
    wt._bao_len_console({"enabled": True, "che_do_node": {"a": "h1"}}, {"last_scan": {"x": 1}})
    assert thay["body"] == {"wiki_source": {"last_scan": {"x": 1}}}


def test_nhap_do_thi_khong_don(wt, monkeypatch):
    monkeypatch.setattr(wt, "khai_bao", lambda: {"enabled": True, "root_url": "u",
                                                  "che_do_node": {}})
    monkeypatch.setattr(W, "quet", lambda url: {"nodes": [STANDUP], "khong_doc": 0})
    monkeypatch.setattr(wt, "_bao_len_console", lambda kb, moi: True)
    don = []
    monkeypatch.setattr(W, "don_tai_lieu_cu", lambda *a: don.append(a) or 9)
    monkeypatch.setattr(wt, "_goi", lambda url, **kw: (500, {}))   # lô nhập hỏng
    assert wt.mot_luot(nhap=True)["nhap"] == 0
    assert don == [], "nhập dở mà vẫn dọn là xoá bản cũ khi bản mới chưa vào"


def test_nhap_du_thi_don_va_gui_chi_tiet(wt, monkeypatch):
    monkeypatch.setattr(wt, "khai_bao", lambda: {"enabled": True, "root_url": "u",
                                                  "che_do_node": {"wk_standup": "h1"}})
    monkeypatch.setattr(W, "quet", lambda url: {"nodes": [STANDUP, BACKLOG], "khong_doc": 0})
    gui = {}
    monkeypatch.setattr(wt, "_bao_len_console", lambda kb, moi: gui.update(moi) or True)
    monkeypatch.setattr(W, "don_tai_lieu_cu", lambda ten, ct, goi: 4)
    monkeypatch.setattr(wt, "_goi", lambda url, **kw: (200, {}))
    r = wt.mot_luot(nhap=True)
    assert r == {"nhap": 4, "tong": 4}, "3 mục H1 theo lựa chọn + 1 thẻ mục lục Base"
    bc = gui["last_scan"]
    assert bc["da_don"] == 4
    assert [c["token"] for c in bc["chi_tiet"]] == ["wk_standup", "wk_backlog"]
