"""Base hỗn hợp: chỉ bảng được cấu hình, không bao giờ rơi về đọc cả Base."""
from __future__ import annotations

import json

import pytest

import bang_tool as BT
import dem_bang_tool as DB
import lark_bang as B
import tien_do as TD

APP = "appMixed"
WORK = "tblWork"
AUDIT = "tblAudit"
COST = "tblCost"
WIKI = "NodeMixed"


@pytest.fixture
def mixed(tmp_path, monkeypatch):
    token_dir = tmp_path / ".tokens"
    token_dir.mkdir()
    configs = {
        "audit_base.json": {"app_token": APP, "table_id": AUDIT},
        "audit_base.previous.json": {"app_token": APP, "table_id": "tblAuditOld"},
        "chi_phi_quet_base.json": {"app_token": APP, "table_id": COST},
        "mixed_base_read_allowlist.json": {
            "version": 1, "tables": [{"app_token": APP, "table_id": WORK}]},
    }
    for name, value in configs.items():
        (token_dir / name).write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(BT, "_thu_muc_token", lambda: token_dir)
    monkeypatch.setattr(BT, "base_noi_bo", lambda: {APP})
    monkeypatch.setattr(BT.B, "giai_wiki", lambda _n: ("bitable", APP))
    monkeypatch.setattr(BT, "_quyen_thuc_te",
                        lambda loai, token, nguoi: (True, "là thành viên"))
    monkeypatch.delenv("AGENT_BOSS_OPEN_ID", raising=False)
    monkeypatch.delenv("STEVEN_BOSS_OPEN_ID", raising=False)
    return token_dir


def link(table=WORK):
    return f"https://x.larksuite.com/wiki/{WIKI}?table={table}"


def test_wiki_giu_nguyen_table_scope_va_cho_phep_cap_chinh_xac(mixed):
    assert B.nhan_dien(link()) == ("wiki", WIKI, WORK)
    assert BT.mo_nguon(link(), nguoi_hoi="ou_user")[:3] == ("bitable", APP, WORK)


@pytest.mark.parametrize("url", [
    f"https://x/wiki/{WIKI}?table={WORK}&table={AUDIT}",
    f"https://x/wiki/{WIKI}?table={WORK}&sheet=s1",
])
def test_scope_trung_hoac_mau_thuan_bi_tu_choi(mixed, url):
    with pytest.raises(BT.TuChoi):
        BT.mo_nguon(url, nguoi_hoi="ou_user")


def test_scope_khong_khop_loai_node_bi_tu_choi(mixed, monkeypatch):
    monkeypatch.setattr(BT.B, "giai_wiki", lambda _n: ("sheet", "sht1"))
    with pytest.raises(BT.TuChoi, match="không khớp"):
        BT.mo_nguon(link(), nguoi_hoi="ou_user")


@pytest.mark.parametrize("table", [AUDIT, COST, "tblAuditOld", "tblNotAllowed"])
def test_bang_nhay_cam_va_bang_chua_allowlist_luon_bi_chan(mixed, table):
    with pytest.raises(BT.TuChoi):
        BT.mo_nguon(link(table), nguoi_hoi="ou_user")


def test_khong_danh_tinh_khong_duoc_dung_ngoai_le(mixed):
    with pytest.raises(BT.TuChoi, match="danh tính Lark"):
        BT.mo_nguon(link(), nguoi_hoi="")


def test_allowlist_khong_thay_the_quyen_nguoi_hoi(mixed, monkeypatch):
    monkeypatch.setattr(BT, "_quyen_thuc_te", lambda *_a: (False, "chưa thấy bạn"))
    with pytest.raises(BT.TuChoi, match="chưa thấy bạn"):
        BT.mo_nguon(link(), nguoi_hoi="ou_user")


@pytest.mark.parametrize("missing", ["audit_base.json", "audit_base.previous.json",
                                      "chi_phi_quet_base.json"])
def test_metadata_bao_ve_thieu_thi_dong(mixed, missing):
    (mixed / missing).unlink()
    with pytest.raises(BT.TuChoi, match="metadata bảo vệ"):
        BT.mo_nguon(link(), nguoi_hoi="ou_user")


def test_metadata_table_id_sai_dinh_dang_thi_dong(mixed):
    (mixed / "audit_base.json").write_text(
        json.dumps({"app_token": APP, "table_id": "not-a-table"}), encoding="utf-8")
    with pytest.raises(BT.TuChoi, match="metadata bảo vệ"):
        BT.mo_nguon(link(), nguoi_hoi="ou_user")


def test_doc_base_scope_sai_khong_doc_record_bang_khac(monkeypatch):
    calls = []
    def call(_method, path, **_kw):
        calls.append(path)
        if path.endswith("/tables"):
            return {"data": {"items": [{"table_id": "tblSecret", "name": "Audit"}]}}
        return {"data": {"app": {"name": "Mixed"}}}
    monkeypatch.setattr(B.lark, "call", call)
    with pytest.raises(LookupError, match="không đọc bảng khác"):
        B.doc_base(APP, WORK)
    assert not any("/records" in p for p in calls)


def test_doc_sheet_scope_sai_khong_doc_tab_khac(monkeypatch):
    calls = []
    def call(_method, path, **_kw):
        calls.append(path)
        if path.endswith("/sheets/query"):
            return {"data": {"sheets": [{"sheet_id": "secret", "title": "Audit"}]}}
        return {"data": {"spreadsheet": {"title": "Mixed"}}}
    monkeypatch.setattr(B.lark, "call", call)
    with pytest.raises(LookupError, match="không đọc tab khác"):
        B.doc_sheet("sht1", "wanted")
    assert not any("/values/" in p for p in calls)


def test_loi_khong_thay_bang_khong_khuyen_chia_se_bot():
    text = BT.loi_doc("Base", LookupError("Không thấy bảng; không đọc bảng khác."))
    assert "không đọc bảng khác" in text and "chia sẻ" not in text


def test_dem_bang_khong_duoc_override_scope(mixed, monkeypatch):
    monkeypatch.setattr(BT, "mo_nguon",
                        lambda *_a, **_k: ("bitable", APP, WORK, "Base", "ok"))
    monkeypatch.setattr(B, "doc_tho", lambda *_a, **_k: pytest.fail("không được đọc"))
    out = DB._handle({"nguon": link(), "tab": AUDIT})
    assert "không được đổi" in out


def test_doc_tho_base_scope_id_sai_khong_fallback_sang_ten(monkeypatch):
    calls = []
    def call(_method, path, **_kw):
        calls.append(path)
        if path.endswith("/tables"):
            return {"data": {"items": [
                {"table_id": "tblSecret", "name": f"Archive {WORK}"}]}}
        return {"data": {"app": {"name": "Mixed"}}}
    monkeypatch.setattr(B.lark, "call", call)
    out = B.doc_tho("bitable", APP, WORK, strict_scope=True)
    assert out["bang"] == []
    assert not any(p.endswith("/fields") or p.endswith("/records") for p in calls)


def test_doc_tho_sheet_scope_id_sai_khong_fallback_sang_ten(monkeypatch):
    calls = []
    def call(_method, path, **_kw):
        calls.append(path)
        if path.endswith("/sheets/query"):
            return {"data": {"sheets": [{"sheet_id": "secret",
                                            "title": "Archive wanted"}]}}
        return {"data": {"spreadsheet": {"title": "Mixed"}}}
    monkeypatch.setattr(B.lark, "call", call)
    out = B.doc_tho("sheet", "sht1", "wanted", strict_scope=True)
    assert out["bang"] == []
    assert not any("/values/" in p for p in calls)


def test_tien_do_dung_cung_scope_gate(mixed):
    dich, loi = TD._dich_tu_nguon(link(), None, nguoi_hoi="ou_user")
    assert not loi and dich["app_token"] == APP and dich["table_id"] == WORK


def test_tien_do_mixed_base_khong_table_khong_roi_ve_mac_dinh(mixed):
    dich, loi = TD._dich_tu_nguon(f"https://x/base/{APP}", None, nguoi_hoi="ou_user")
    assert dich is None and "chưa cho phép đúng bảng" in loi


def test_dem_bang_khong_liet_ke_ten_bang_base_noi_bo(mixed, monkeypatch):
    """Allowlist trỏ bảng đã xoá/đổi: báo không thấy, KHÔNG lộ tên Audit/Chi phí."""
    monkeypatch.setattr(BT, "mo_nguon",
                        lambda *_a, **_k: ("bitable", APP, WORK, "Base", "ok"))
    monkeypatch.setattr(B, "doc_tho", lambda *_a, **_k: {
        "ten": "Mixed", "bang": [], "tat_ca": ["Audit", "Chi phí quét"]})
    out = DB._handle({"nguon": link()})
    assert "Không thấy bảng" in out
    assert "Audit" not in out and "Chi phí" not in out
