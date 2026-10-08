"""`tra_tien_do` trên Base tường minh khác CHECKLIST DA.

Lark giả hoàn toàn; không mạng, không ghi Base.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

import tien_do as T


TODAY = dt.date(2026, 10, 7)
DEFAULT = {"app_token": "DefaultBase12", "table_id": "tblDefault",
           "ten": "Checklist DA",
           "url": "https://x.larksuite.com/base/DefaultBase12?table=tblDefault"}
OTHER = {"app_token": "PlanBase12345", "table_id": "tblPlan", "ten": "Base đã dẫn",
         "url": "https://x.larksuite.com/base/PlanBase12345?table=tblPlan"}

FIELDS = {
    "Hạng mục": {"type": 1, "primary": True, "options": []},
    "Loại": {"type": 3, "primary": False, "options": ["Task", "Milestone"]},
    "Thuộc phase": {"type": 1, "primary": False, "options": []},
    "Trạng thái": {"type": 3, "primary": False,
                   "options": ["Chưa làm", "Đang làm", "Hoàn thành", "Huỷ"]},
    "Ưu tiên": {"type": 3, "primary": False, "options": ["Cao", "Thấp"]},
    "Người phụ trách": {"type": 11, "primary": False, "options": []},
    "Bắt đầu": {"type": 5, "primary": False, "options": []},
    "Hạn": {"type": 5, "primary": False, "options": []},
    "Ngày xong": {"type": 5, "primary": False, "options": []},
    "Kết quả cần đạt": {"type": 1, "primary": False, "options": []},
    "Link task/bằng chứng": {"type": 1, "primary": False, "options": []},
    "Ghi chú": {"type": 1, "primary": False, "options": []},
    "Mã task": {"type": 1, "primary": False, "options": []},
}


def _ms(day: int) -> int:
    return int(dt.datetime(2026, 10, day, tzinfo=T._VN).timestamp() * 1000)


ROWS = [
    {"record_id": "r-overdue", "fields": {
        "Hạng mục": "Chốt concept", "Trạng thái": "Đang làm",
        "Người phụ trách": [{"id": "ou_an", "name": "An"}], "Hạn": _ms(6),
    }},
    {"record_id": "r-done", "fields": {
        "Hạng mục": "Duyệt brief", "Trạng thái": "Hoàn thành",
        "Người phụ trách": [{"id": "ou_binh", "name": "Bình"}], "Hạn": _ms(5),
    }},
]


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(T, "cau_hinh", lambda: dict(DEFAULT))
    monkeypatch.setattr(T, "hom_nay_vn", lambda: TODAY)

    def resolve(source, configured, **kwargs):
        return (dict(DEFAULT), "") if "DefaultBase12" in source else (dict(OTHER), "")
    monkeypatch.setattr(T, "_dich_tu_nguon", resolve)
    monkeypatch.setattr(T, "ten_base", lambda d: "Kế hoạch ra mắt")
    return monkeypatch


def test_explicit_other_base_uses_adaptive_columns_end_to_end(context):
    context.setattr(T.VB, "_doc_cot", lambda d: dict(FIELDS))
    seen = []
    context.setattr(T, "_doc_dong", lambda d, fields: seen.append(fields) or list(ROWS))
    context.setattr(T, "doc_viec", lambda d: pytest.fail("không được ép cột CHECKLIST DA"))

    result = json.loads(T._handle({"nguon": OTHER["url"]}))

    assert result["success"] is True
    assert result["bang"] == "Kế hoạch ra mắt"
    assert result["dem"]["qua_han"] == 1
    assert result["dem"]["da_xong_hoac_cancel"] == 1
    assert result["qua_han"][0]["hang_muc"] == "Chốt concept"
    assert seen == [["Hạng mục", "Người phụ trách", "Hạn", "Trạng thái"]]


@pytest.mark.parametrize("source", ["", DEFAULT["url"]])
def test_default_or_explicit_same_config_preserves_strict_old_reader(context, source):
    called = []
    context.setattr(T, "doc_viec", lambda d: called.append((d["app_token"], d["table_id"])) or [])
    context.setattr(T, "doc_theo_cot", lambda *a, **k: pytest.fail("Base mặc định không đổi reader"))

    result = json.loads(T._handle({**({"nguon": source} if source else {})}))

    assert result["success"] is True
    assert called == [(DEFAULT["app_token"], DEFAULT["table_id"])]


def test_ambiguous_deadline_columns_fail_closed_without_reading_rows(context):
    fields = dict(FIELDS)
    fields["Hạn phụ"] = {"type": 5, "primary": False, "options": []}
    # Bỏ tên đặc trưng để hai cột Ngày không còn căn cứ chọn.
    fields["Ngày A"] = fields.pop("Hạn")
    fields["Ngày B"] = fields.pop("Hạn phụ")
    context.setattr(T.VB, "_doc_cot", lambda d: fields)
    context.setattr(T, "_doc_dong", lambda *a, **k: pytest.fail("mơ hồ mà vẫn đọc dòng"))

    result = json.loads(T._handle({"nguon": OTHER["url"]}))

    assert "error" in result
    assert "không đoán cột" in result["error"]
    assert "cot_han" in result["error"]


def test_primary_text_wins_over_other_text_fields(context):
    context.setattr(T.VB, "_doc_cot", lambda d: dict(FIELDS))
    context.setattr(T, "_doc_dong", lambda d, fields: list(ROWS))

    result = json.loads(T._handle({"nguon": OTHER["url"]}))

    assert result["qua_han"][0]["hang_muc"] == "Chốt concept"
    assert "Task" not in result["cau_tien_do"]
