"""Canh social_deep_dive và hợp đồng của `apify_tool._call`.

01/10/2026: 9/9 lượt kéo bình luận YouTube/Facebook chết vì TypeError — deep_dive gọi
`_call(..., min_charge=...)` mà `_call` không có tham số đó. Bộ thử cũ không bắt được
vì mọi bài đều thay `_call` bằng lambda tự khai chữ ký riêng.
"""
from __future__ import annotations

import ast
import inspect
import json
import pathlib

import pytest

import apify_tool as A
import deep_dive_tool as D

GOC = pathlib.Path(A.__file__).resolve().parent
NOI_GOI = ["deep_dive_tool.py", "account_tool.py", "shopee_tool.py", "tiktok_trend.py",
           "san_link.py", "crawl_adapters.py", "apify_tool.py"]


def test_moi_loi_goi_call_khop_chu_ky_that():
    """Quét AST: mọi `_call(...)` / `A._call(...)` phải bind được vào chữ ký THẬT."""
    sig = inspect.signature(A._call)
    so_loi_goi = 0
    for ten in NOI_GOI:
        f = GOC / ten
        if not f.is_file():
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            ten_ham = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if ten_ham != "_call":
                continue
            so_loi_goi += 1
            kws = {k.arg: None for k in node.keywords if k.arg}
            for k in kws:
                assert k in sig.parameters, f"{ten}:{node.lineno} truyền `{k}=` mà _call không có"
            sig.bind(*[None] * len(node.args), **kws)   # TypeError nếu thừa/thiếu đối số
    assert so_loi_goi >= 15, "quét AST hỏng: không thấy đủ lời gọi _call"


class _R:
    status_code = 200

    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


@pytest.fixture
def apify_gia(monkeypatch):
    """Dùng `_call` THẬT (không lambda), chỉ giả `requests.post` — bắt đúng lỗi chữ ký."""
    goi = []
    tra = {"streamers~youtube-comments-scraper": [
               {"author": "@an", "comment": "Túi đẹp", "voteCount": 3, "replyCount": 0,
                "publishedTimeText": "2 days ago", "pageUrl": "https://www.youtube.com/watch?v=abc"}],
           "apify~facebook-comments-scraper": [
               {"profileName": "Bình", "text": "Giá bao nhiêu?", "likesCount": 1,
                "facebookUrl": "https://www.facebook.com/hapas/posts/1"}]}

    def post(url, **k):
        goi.append((url, k))
        actor = url.split("/acts/")[1].split("/")[0]
        return _R(tra.get(actor, []))

    monkeypatch.setenv("APIFY_TOKEN", "apify_api_BIMAT_DD")
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    monkeypatch.setattr(A.requests, "post", post)
    monkeypatch.setattr(D, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(D, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(D, "_write", lambda tok, sid, values: None)
    monkeypatch.setattr(D, "_grant", lambda tok, oid: True)
    monkeypatch.setattr(D.memory_store, "get_current_sender", lambda: "ou_test")
    return goi


@pytest.mark.parametrize("url", ["https://www.youtube.com/watch?v=abc",
                                 "https://www.facebook.com/hapas/posts/1"])
def test_youtube_facebook_khong_con_typeerror(apify_gia, url):
    kq = json.loads(D._handle({"post_urls": [url], "max_comments": 10}))
    assert kq["platforms_failed"] == [], kq["per_url"]
    assert kq["tong_comment"] == 1
    assert "maxTotalChargeUsd=1.0" in apify_gia[0][0], "trần console vẫn là trần của lượt chạy"
    assert "token" not in apify_gia[0][0]


def test_tran_console_thap_hon_muc_actor_doi_thi_tu_choi_ro_rang(apify_gia, monkeypatch):
    """Không tự nâng trần lên 0,5 USD sau lưng chủ agent — từ chối và nói lý do."""
    monkeypatch.setattr(A, "_tran", lambda: (500, 0.3))
    kq = json.loads(D._handle({"post_urls": ["https://www.youtube.com/watch?v=abc"]}))
    loi = kq["per_url"]["https://www.youtube.com/watch?v=abc"]["error"]
    assert "thấp hơn mức tối thiểu" in loi and "0,5 USD" in loi and "console" in loi
    assert apify_gia == [], "không được gọi Apify khi trần không đủ"


def test_tiktok_khong_doi_min_charge(apify_gia, monkeypatch):
    monkeypatch.setattr(A, "_tran", lambda: (500, 0.3))
    kq = json.loads(D._handle({"post_urls": ["https://www.tiktok.com/@a/video/1"]}))
    assert kq["platforms_failed"] == []


def test_loi_deep_dive_khong_lam_lo_token(monkeypatch):
    bi_mat = "apify_api_BIMAT_DD"
    monkeypatch.setenv("APIFY_TOKEN", bi_mat)

    def hong(*a, **k):
        raise RuntimeError(f"ConnectionError: url /v2/acts/x?token={bi_mat}")
    monkeypatch.setattr(D, "_call", hong)
    kq = D._handle({"post_urls": ["https://www.tiktok.com/@a/video/1"]})
    assert bi_mat not in kq and "LỖI" in kq
