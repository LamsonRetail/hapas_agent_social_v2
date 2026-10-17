"""Regressions for the blocked 09/10 review; all transports are fake."""
import json
from decimal import Decimal

import pytest

import bang_tool as BT
import doc_tai_lieu_tool as D
import lsr_policy as P
import thong_ke_tool as T
import lenh_cung
from test_doc_tai_lieu import _gia, _tuyen, DOCX, LINK, NGAN
from test_thong_ke import _lap, LINK as SHEET_LINK


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(BT, "base_noi_bo", lambda: set())
    monkeypatch.setattr(BT, "_nguoi_hoi", lambda: NGAN)
    monkeypatch.setattr(BT, "_trong_cay_wiki", lambda *a: False)
    monkeypatch.delenv("AGENT_BOSS_OPEN_ID", raising=False)
    monkeypatch.delenv("STEVEN_BOSS_OPEN_ID", raising=False)
    D._NHO.clear()


@pytest.mark.parametrize("path", [
    "docx/v1/documents/X/raw_content", "doc/v2/X/raw_content",
    "/open-apis//docx/v1/documents/X/blocks",
    "https://open.larksuite.com/OPEN-APIS/DOCX/v1/documents/X/raw_content?q=1",
    "/open-apis/wiki/../../docx/v1/documents/X/raw_content",
    "%64ocx/v1/documents/X/raw_content",
    "%44OCX/v1/documents/X/raw_content",
    "https://example.org/calendar/v4/calendars",
    "docs_ai/v1/x", "bitable/v1/apps/X/tables/Y/records",
    "sheets/v2/spreadsheets/X/values/A1", "sheet_ai/v2/spreadsheets/X/tools/invoke_read", "slides/v1/X",
    "drive/v1/medias/X/download", "drive/v1/export_tasks/X",
    "im/v1/messages/X/resources/Y",
])
@pytest.mark.parametrize("flags", [[], ["--as", "bot"], ["--format=json"]])
def test_raw_content_cannot_bypass_with_paths_or_flags(path, flags):
    assert not P.decide("lark_cli", {"args": ["api", "GET", *flags, path]}).allowed


@pytest.mark.parametrize("args", [
    ["base", "+record-list"], ["base", "+record-get"],
    ["base", "+data-query"], ["base", "+dashboard-block-get-data"],
    ["sheets", "+cells-get"], ["sheets", "+csv-get"],
    ["sheets", "+export"], ["sheets", "+workbook-export"],
    ["slides", "+read"], ["slides", "+xml-get"],
    ["drive", "+download"], ["drive", "+export"], ["drive", "+pull"],
    ["drive", "+list-comments"], ["markdown", "+fetch"],
    ["docs", "+fetch", "--format", "--help"],
    ["base", "+record-list", "--dry-run"],
    ["api", "GET", "--mystery", "docx/v1/X"],
    ["api", "GET", "--data", "--help", "docx/v1/X"],
])
def test_shortcuts_and_ambiguous_flags_stay_closed(args):
    assert not P.decide("lark_cli", {"args": args}).allowed


@pytest.mark.parametrize("args", [
    ["docs", "+fetch", "--help"], ["schema", "docx.document"],
    ["wiki", "+node-get", "--token", "X"], ["base", "+table-list"],
    ["drive", "+search"], ["api", "GET", "--as", "bot", "wiki/v2/spaces"],
    ["contact", "+list"], ["calendar", "+agenda"], ["im", "+list"],
])
def test_metadata_and_discovery_are_available(args):
    assert P.decide("lark_cli", {"args": args}).allowed


def test_internal_base_even_metadata_is_refused(monkeypatch):
    monkeypatch.setattr(BT, "base_noi_bo", lambda: {"AuditTOKEN"})
    for args in (["base", "+table-list", "--app-token", "AuditTOKEN"],
                 ["wiki", "+node-get", "--token", "audit%54oken"],
                 ["wiki", "+node-get", "--token", "%2541uditTOKEN"]):
        assert not P.decide("lark_cli", {"args": args}).allowed


def test_wiki_command_can_use_checked_readers(monkeypatch):
    monkeypatch.setattr(lenh_cung, "_duoc_khong", lambda tool: (True, ""))
    text = lenh_cung._cau_di_kem("lark_cli")
    assert all(t in text for t in ("doc_tai_lieu", "doc_bang", "dem_bang"))


def test_totals_excluded_from_all_numbers_and_source_indices():
    rows = [["Nền tảng", "Sắc thái", "Views"], ["FB", "Tốt", "100"],
            ["TikTok", "Xấu", "300"], ["FB", "Tốt", "50"],
            ["Tổng", "Tốt", "450"]]
    grid = [[[x] for x in row] for row in rows]
    result = T.thong_ke(grid, ["Nền tảng"], [["Nền tảng", "Sắc thái"]], "Views", dong_tieu_de=1)
    assert result["n"] == 3 and result["so"]["tong"] == Decimal(450)
    assert result["so"]["so_o_so"] == 3
    assert result["top"][0]["dong"] == 3 and result["top"][0]["gia_tri"] == 300
    assert result["dong_tong_bo_qua"] == [5]
    assert [(g["gia_tri"], g["so"]) for g in result["nhom"][0]["gia_tri"]] == [("FB", 2), ("TikTok", 1)]
    assert len(result["cheo"][0]["dong"]) == 2
    assert "đã bỏ 1 dòng tổng: 5" in T.cau_so(result, "nguồn")


def test_total_warning_in_tool_and_overview(monkeypatch):
    rows = [["Nền tảng", "Views"], ["FB", "100"], ["FB", "50"], ["Tổng", "150"]]
    fake, _ = _lap(monkeypatch, dong=rows)
    result = json.loads(T._handle({"nguon": SHEET_LINK, "nhom_theo": ["Nền tảng"], "cot_so": "Views"}))
    assert result["n"] == 2 and result["dong_tong_bo_qua"] == [4]
    assert "đã bỏ 1 dòng tổng" in str(fake.o("Tổng quan"))


@pytest.mark.parametrize("label", ["Total views", "Tổng cộng (tất cả)", "Grand total", "Chênh lệch"])
def test_model_total_in_any_column_is_rejected(label):
    with pytest.raises(T.LoiNhap, match="dòng TỔNG"):
        T.doc_nhap({"cot": ["STT", "Nhãn", "Số"], "dong": [[1, label, 12]]})


def test_model_numeric_totals_are_not_claimed_as_source_numbers(monkeypatch):
    fake, _ = _lap(monkeypatch)
    result = json.loads(T._handle({"du_lieu": {"cot": ["Nhãn", "Số"],
                                               "dong": [["Tốt", 100], ["Xấu", 25]]},
                                 "nhom_theo": ["Nhãn"], "cot_so": "Số"}))
    assert "Không cộng số Mark" in result["error"] and not fake.bt


def test_old_document_permission_denial_never_reads_content(monkeypatch):
    calls = []
    monkeypatch.setattr(BT, "quyen_nguoi_hoi", lambda *a: (False, "không có quyền"))
    with pytest.raises(BT.TuChoi):
        BT.mo_tai_lieu("doc:oldToken", lambda *a: calls.append(a))
    assert not calls


@pytest.mark.parametrize("cap", [True, False])
def test_block_truncation_is_visible(monkeypatch, cap):
    routes = _tuyen()
    routes[f"/open-apis/docx/v1/documents/{DOCX}/blocks"]["has_more"] = True
    if cap:
        monkeypatch.setattr(D, "MAX_KHOI", 2)
    _gia(monkeypatch, routes)
    result = json.loads(D._handle({"nguon": LINK}))
    assert result["bi_cat"] and result["tong_ky_tu"] is None
    assert "chưa đọc đủ" in result["ghi_chu"]


def test_document_changed_between_chunks_stops_before_content(monkeypatch):
    fake = _gia(monkeypatch, _tuyen())
    result = json.loads(D._handle({"nguon": LINK, "tu_ky_tu": 20, "phien_ban": 6}))
    assert "đổi phiên bản" in result["error"] and not fake.da_goi("/blocks")


def test_block_requests_pin_revision(monkeypatch):
    fake = _gia(monkeypatch, _tuyen())
    json.loads(D._handle({"nguon": LINK}))
    requests = [q for _, p, q, _ in fake.goi if p.endswith("/blocks")]
    assert requests[0]["document_revision_id"] == 7


@pytest.mark.parametrize("args", [
    ["--as", "bot", "base", "+record-list"],
    ["--as=bot", "docs", "+fetch"],
    ["--verbose", "api", "GET", "docx/v1/documents/X/raw_content"],
])
def test_global_flags_cannot_hide_the_content_domain(args):
    assert not P.decide("lark_cli", {"args": args}).allowed


def test_reading_next_chunk_requires_revision(monkeypatch):
    fake = _gia(monkeypatch, _tuyen())
    result = json.loads(D._handle({"nguon": LINK, "tu_ky_tu": 20}))
    assert "Đọc tiếp cần" in result["error"] and not fake.da_goi("/blocks")


@pytest.mark.parametrize("args", [
    ["sheets", "+cells-set"], ["base", "+record-upsert"],
    ["api", "POST", "docx/v1/documents/X"],
])
def test_sow_does_not_confuse_denied_writes_with_content_reads(args):
    from evals.sow import kiem
    assert kiem._lark_cli_bi_chan({"args": args})


def test_native_chart_uses_actual_tab_and_excludes_total_row(monkeypatch):
    from types import SimpleNamespace
    import trinh_bay_sheet as TB
    calls = []
    def fake(method, path, body=None, **kw):
        calls.append((path, json.loads(body["input"])))
        return {"data": {"output": '{"chart_id":"chart1"}'}}
    monkeypatch.setattr(T.A.lark, "call", fake)
    tab = TB.TabDaGhi("1. Theo Nhãn", "s1", [TB.Cot("Nhãn"), TB.Cot("Số dòng"), TB.Cot("Tỉ lệ")],
                     3, 3, dong_tong=1, kiem="du")
    charts, warnings = T.tao_bieu_do(SimpleNamespace(token="newSheet", tabs=[tab]), {"nhom": [{"cot": "Nhãn"}]})
    assert charts == [{"tab": "1. Theo Nhãn", "chart_id": "chart1"}] and not warnings
    assert "newSheet/tools/invoke_write" in calls[0][0]
    config = calls[0][1]["properties"]
    assert config["snapshot"]["data"]["refs"] == [{"value": "'1. Theo Nhãn'!A1:B4"}]


def test_native_chart_failure_preserves_verified_sheet(monkeypatch):
    fake, _ = _lap(monkeypatch)
    result = json.loads(T._handle({"nguon": SHEET_LINK, "nhom_theo": ["Sắc thái"]}))
    assert result["day_du"] is True and result["sheet_url"]
    assert not result["bieu_do"] and result["canh_bao_bieu_do"]
    assert "bảng số vẫn có" in result["huong_dan"]
