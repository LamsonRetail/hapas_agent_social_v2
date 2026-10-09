"""chi_so_ads → lớp trình bày chung (trinh_bay_sheet) với Lark GIẢ (tests/sheet_gia).

Soi: thứ tự tab, Tổng quan (số liệu chính = đúng tổng tool đã tính trong cau_tong), kiểu cột
(tiền theo tiền tệ từng dòng, CTR đã ×100, mã dạng chữ, ngày thật), dòng tổng, bộ lọc, cố
định dòng 1, quyền riêng tư (khoá trước khi ghi, cấp XEM sau cùng), trang trí hỏng vẫn đủ
dữ liệu + link, `day_du`/`kiem_ghi`, tab "Dữ liệu gốc".
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import re

import pytest

import memory_store
import meta_ads_tool as T
import scheduler
import trinh_bay_sheet as TB
from sheet_gia import LarkGia
from sheet_gia import meta  # noqa: E402

_CLOSED = {"link_share_entity": "closed", "external_access_entity": "closed",
           "share_entity": "same_tenant", "manage_collaborator_entity": "collaborator_full_access"}
ACT_VN = "act_123456789012345678"
ACCOUNTS = [{"id": ACT_VN, "name": "HAPAS VN", "currency": "VND", "timezone_name": "Asia/Ho_Chi_Minh"},
            {"id": "act_2", "name": "HAPAS US", "currency": "USD", "timezone_name": "Asia/Ho_Chi_Minh"}]
INSIGHTS = {
    ACT_VN + "/insights": [
        {"campaign_id": "120200000000000001", "campaign_name": "=Chiến dịch A", "spend": "100000",
         "impressions": "1000", "clicks": "12", "date_start": "2026-10-01", "date_stop": "2026-10-07",
         "actions": [{"action_type": "purchase", "value": "3"}]},
        {"campaign_id": "120200000000000002", "campaign_name": "Chiến dịch B", "spend": "50000",
         "impressions": "500", "clicks": "3", "date_start": "2026-10-01", "date_stop": "2026-10-07"}],
    "act_2/insights": [
        {"campaign_id": "9", "campaign_name": "US", "spend": "20.5", "impressions": "200", "clicks": "4",
         "date_start": "2026-10-01", "date_stop": "2026-10-07"}],
}


@pytest.fixture(autouse=True)
def context(monkeypatch):
    monkeypatch.delenv("MARK_META_AD_ACCOUNT_IDS", raising=False)
    monkeypatch.setattr(T, "_TOKEN", "")
    monkeypatch.setenv("MARK_META_ADS_TOKEN", "fake")
    monkeypatch.setattr(T, "_allowed", lambda actor: actor == "ou_asker")
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: [dict(a) for a in ACCOUNTS])
    monkeypatch.setattr(T.MetaClient, "pages",
                        lambda self, tail, params, limit: ([dict(r) for r in INSIGHTS[tail]], False))
    monkeypatch.setattr(TB, "_LOC_LUOT", collections.deque())     # trần 20 lần lọc/phút
    memory_store.set_current_sender("ou_asker")
    scheduler.set_current_chat(None)
    scheduler.set_current_chat_type("p2p")
    T.set_context({"channel": "lark", "chat_type": "p2p", "nguoi_gui": "ou_asker"})
    yield
    memory_store.set_current_sender(None)
    scheduler.set_current_chat_type(None)
    T.set_context({})


def _gia(monkeypatch, hong=()):
    gia = LarkGia(hong=hong)

    def call(method, path, query=None, body=None):
        if "/drive/v2/permissions/" in path and path.endswith("/public"):
            gia.goi.append((method, path, query, body))
            return {"data": {"permission_public": dict(_CLOSED)}}
        return gia.call(method, path, query=query, body=body)
    monkeypatch.setattr(T.lark, "call", call)
    return gia


def run(**args):
    return json.loads(T._handle({"tai_khoan": "tat_ca", "tu_ngay": "2026-10-01", "den_ngay": "2026-10-07",
                                 "cap": "chien_dich", "chi_so": ["spend", "impressions", "ctr", "cpc"],
                                 **args}))


def _fmt(gia, tab, cot, dong):
    st = [s for s in gia.kieu_o(tab, cot, dong) if "formatter" in s]
    return st[-1]["formatter"] if st else None


def _serial(d: str) -> int:
    return (dt.date.fromisoformat(d) - dt.date(1899, 12, 30)).days


def test_bo_cuc_tab_va_du_lieu(monkeypatch):
    gia = _gia(monkeypatch)
    kq = run()
    assert kq["link"].startswith("https://") and kq["so_dong"] == 3 and kq["bi_cat"] is False
    assert gia.tab_ten() == ["Tổng quan", "Theo tài khoản", "Chi tiết", "Dữ liệu gốc"]
    o = gia.o("Chi tiết")
    assert o[0][:8] == ["Tài khoản", "Mã TK", "Tiền tệ", "Múi giờ TK", "Từ ngày", "Đến ngày",
                        "Mã đối tượng", "Tên đối tượng"]
    assert o[0][8:] == ["Chi tiêu (tiền TK)", "Hiển thị (lượt)", "CTR (%)", "CPC (tiền TK/click)"]
    # act_ và mã chiến dịch dài là CHỮ (không thành số mất chữ số); ô "=..." vẫn bị chặn.
    assert o[1][1] == ACT_VN and o[1][6] == "120200000000000001" and o[1][7] == "'=Chiến dịch A"
    assert _fmt(gia, "Chi tiết", 2, 2) == "@" and _fmt(gia, "Chi tiết", 7, 2) == "@"
    # Ngày là ngày thật (định dạng đặt trước khi ghi).
    assert o[1][4] == _serial("2026-10-01") and _fmt(gia, "Chi tiết", 5, 2) == "yyyy/MM/dd"
    # CTR đã ×100 trong tool (12/1000×100 = 1.2) → giữ nguyên giá trị, hiện "1.20%".
    assert o[1][10] == pytest.approx(1.2) and _fmt(gia, "Chi tiết", 11, 2) == "#,##0.00"
    assert _fmt(gia, "Chi tiết", 10, 2) == "#,##0"
    # Tiền theo tiền tệ TỪNG dòng: VND ₫, USD 2 số lẻ.
    assert _fmt(gia, "Chi tiết", 9, 2) == "#,##0" and _fmt(gia, "Chi tiết", 9, 4) == "#,##0.00"
    assert _fmt(gia, "Chi tiết", 12, 4) == "#,##0.00"
    # Dòng tổng (tool tự tính, theo tiền tệ) cách dữ liệu một dòng trống, đậm nền xám.
    assert o[4] == [""] * 12
    assert o[5][0] == "TỔNG USD" and o[6][0] == "TỔNG VND" and o[6][8] == 150000.0
    tong = gia.kieu_o("Chi tiết", 9, 7)
    assert any(s.get("font", {}).get("bold") and s.get("backColor") == TB.XAM_TONG for s in tong)
    assert _fmt(gia, "Chi tiết", 9, 7) == "#,##0" and _fmt(gia, "Chi tiết", 9, 6) == "#,##0.00"
    # Tiêu đề navy, cố định dòng 1, lọc tiêu đề + dữ liệu (không gồm dòng tổng).
    assert any(s.get("backColor") == TB.NAVY for s in gia.kieu_o("Chi tiết", 1, 1))
    assert gia.tab("Chi tiết")["frozen"] == 1
    sid = gia.tab("Chi tiết")["sheet_id"]
    assert [b["range"] for p, b in gia.loc() if f"/{sid}/" in p] == [f"{sid}!A1:L4"]
    # Đọc lại kiểm.
    assert kq["day_du"] is True and "Đã ghi đủ" in kq["kiem_ghi"]


def test_tong_quan_so_lieu_chinh_dung_tong_cua_tool(monkeypatch):
    gia = _gia(monkeypatch)
    kq = run()
    o = gia.o("Tổng quan")
    assert o[0][0] == "Số ads HAPAS 2026-10-01–2026-10-07"
    assert "Meta Marketing API" in meta(o) and "2026-10-01–2026-10-07" in meta(o)
    assert "ou_asker" not in json.dumps(o, ensure_ascii=False), "không ghi open_id vào sheet"
    # Nhiều tiền tệ: mỗi tiền tệ một khối "Tài khoản tiền X"; số liệu đọc theo (khối, nhãn).
    so, khoi = {}, ""
    for r in o:
        if r and str(r[0]).startswith("Tài khoản tiền "):
            khoi = r[0].removeprefix("Tài khoản tiền ")
        elif khoi and len(r) > 1 and isinstance(r[1], (int, float)):
            so[(khoi, r[0])] = r[1]
        elif khoi and r and not r[0]:
            break
    # Mỗi số trong cau_tong (đúng chuỗi tool đã báo) = một số liệu chính ở Tổng quan.
    cau = kq["cau_tong"].rstrip(".")
    tien = {"Chi tiêu", "CPC"}
    for cur, phan in re.findall(r"(VND|USD): ([^;]+)", cau):
        for ten, gt in re.findall(r"([^,]+?) (-?[\d.]+)(?:,|$)", phan):
            ten = ten.strip()
            nhan = f"{ten} — {cur}" if ten in tien else ten
            assert so[(cur, nhan)] == pytest.approx(float(gt)), (ten, cur)
    assert so[("VND", "Chi tiêu — VND")] == 150000.0 and so[("USD", "Chi tiêu — USD")] == 20.5
    assert len(so) == 8
    ghi = " ".join(str(r[0]) for r in o)
    assert "Mốc ngày tính theo múi giờ" in ghi and "ô trống = Meta không trả số phân phối" in ghi
    assert "SỐ LIỆU CHÍNH" in ghi and "MỤC LỤC" in ghi and "KIỂM GHI" in ghi
    assert "SỐ DÒNG THEO TÀI KHOẢN" in ghi


def test_du_lieu_goc_giu_moi_truong_insights_chi_trong_sheet(monkeypatch):
    gia = _gia(monkeypatch)
    kq = run(chi_so=["purchases"])
    goc = gia.o("Dữ liệu gốc")
    assert "actions" in goc[0] and "campaign_id" in goc[0]
    j = goc[0].index("actions")
    assert json.loads(goc[1][j]) == [{"action_type": "purchase", "value": "3"}]
    assert len(goc) == 1 + 3
    # Dữ liệu gốc KHÔNG lọt vào kết quả gửi model.
    assert "action_type" not in json.dumps(kq, ensure_ascii=False)


def test_rieng_tu_khoa_truoc_khi_ghi_cap_xem_sau_cung(monkeypatch):
    gia = _gia(monkeypatch)
    kq = run()
    assert "link" in kq
    i_patch = next(i for i, g in enumerate(gia.goi) if g[0] == "PATCH" and "/drive/v2/permissions/" in g[1])
    i_get = next(i for i, g in enumerate(gia.goi) if g[0] == "GET" and "/drive/v2/permissions/" in g[1])
    writes = [i for i, g in enumerate(gia.goi) if g[1].endswith("/values_batch_update")]
    grants = [(i, g) for i, g in enumerate(gia.goi) if g[1].endswith("/members")]
    assert i_patch < i_get < writes[0]
    assert len(grants) == 1 and grants[0][0] > writes[-1]
    assert grants[0][1][3] == {"member_type": "openid", "member_id": "ou_asker", "perm": "view"}


def test_cap_quyen_xem_hong_thi_bao_loi_nhu_cu(monkeypatch):
    _gia(monkeypatch, hong={"/members"})
    kq = run()
    assert "error" in kq and "Chưa chia sẻ được Sheet riêng" in kq["error"] and "link" not in kq


def test_khoa_rieng_tu_hong_thi_khong_ghi_so(monkeypatch):
    gia = LarkGia()

    def call(method, path, query=None, body=None):
        if path.endswith("/public"):
            return {"data": {"permission_public": dict(_CLOSED, share_entity="anyone")}}
        return gia.call(method, path, query=query, body=body)
    monkeypatch.setattr(T.lark, "call", call)
    kq = run()
    assert "error" in kq and "riêng tư" in kq["error"]
    assert not [g for g in gia.goi if g[1].endswith("/values_batch_update")]


def test_trang_tri_hong_van_du_du_lieu_va_link(monkeypatch):
    gia = _gia(monkeypatch, hong={"styles_batch_update"})
    kq = run()
    assert kq["link"].startswith("https://") and kq["day_du"] is True
    o = gia.o("Chi tiết")
    assert len(o) == 7 and o[1][1] == ACT_VN
    assert o[1][4] == "01/10/2026", "định dạng hỏng → ngày ghi dạng chữ dd/MM/yyyy"
    assert o[1][8] == 100000.0


def test_cat_20000_dong_noi_ro_o_tong_quan(monkeypatch):
    gia = _gia(monkeypatch)
    monkeypatch.setattr(T.MetaClient, "pages",
                        lambda self, tail, params, limit: ([dict(r) for r in INSIGHTS[tail]], True))
    kq = run()
    assert kq["bi_cat"] is True
    o = gia.o("Chi tiết")
    assert o[-1][0].startswith("TỔNG PHẦN ĐÃ ĐỌC")
    ghi = " ".join(str(r[0]) for r in gia.o("Tổng quan"))
    assert "ĐÃ CẮT ở 20.000 dòng" in ghi and "thu hẹp ngày/tài khoản" in ghi
