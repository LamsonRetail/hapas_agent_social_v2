"""Hai campaign tồn tại nhưng chỉ một có Insights: audit Thẩm 09/10/2026."""
import json
import pytest
import meta_ads_tool as T
from test_trinh_bay_meta_ads import _gia, context  # noqa: F401
REAL_PAGES = T.MetaClient.pages

ACC = [{"id": "act_2", "name": "HAPAS 2", "currency": "VND", "timezone_name": "Asia/Ho_Chi_Minh"}]
INVENTORY = [{"id": "11", "name": "20/10_Reach_PRODUCT_Tây Nam Bộ", "stop_time": "2026-10-04T23:59:00+0700"},
             {"id": "12", "name": "20/10_Reach_PRODUCT_Mass"}]
MASS = {"campaign_id": "12", "campaign_name": INVENTORY[1]["name"], "spend": "849247", "impressions": "160711"}

def setup(monkeypatch, rows=None, inventory=None, inventory_cut=False, insight_cut=False):
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: ACC)
    calls = []
    def pages(self, tail, params, limit):
        calls.append((tail, params, limit))
        if tail.endswith("/campaigns"):
            return list(INVENTORY if inventory is None else inventory), inventory_cut
        return list([MASS] if rows is None else rows), insight_cut
    monkeypatch.setattr(T.MetaClient, "pages", pages)
    return calls

def run(**args):
    return json.loads(T._handle({"tai_khoan": "HAPAS 2", "tu_ngay": "2026-10-08", "den_ngay": "2026-10-08",
        "cap": "chien_dich", "chi_so": ["spend"], "loc_tat_ca": ["20/10", "product"], **args}))

def test_two_campaigns_one_report_and_sheet_keeps_missing_campaign(monkeypatch):
    gia = _gia(monkeypatch); calls = setup(monkeypatch)
    result = run()
    assert "error" not in result, result
    assert (result["so_chien_dich_khop_ten"], result["so_chien_dich_co_bao_cao"],
            result["so_chien_dich_chua_co_bao_cao"]) == (2, 1, 1)
    assert "Chi tiêu 849247" in result["cau_tong"] and "2 chiến dịch khớp tên" in result["cau_tong"]
    assert "2026-10-04" in result["cau_tong"] and result["so_dong"] == 1
    assert [x[0] for x in calls] == ["act_2/insights", "act_2/campaigns"]
    assert "time_range" not in calls[1][1]
    assert json.loads(calls[1][1]["filtering"]) == [{"field": "name", "operator": "CONTAIN", "value": "20/10"}]
    sheet = gia.o("Đối chiếu campaign")
    assert len(sheet) >= 3 and sheet[1][3] == INVENTORY[0]["name"]
    assert "Không có dòng Insights" in sheet[1][4]
    assert result["day_du"] and "Đối chiếu campaign" in result["tab"]

def test_no_reports_does_not_mean_no_campaigns_or_zero_spend(monkeypatch):
    gia = _gia(monkeypatch); setup(monkeypatch, rows=[])
    result = run()
    assert "error" not in result, result
    assert result["so_chien_dich_khop_ten"] == 2 and result["so_chien_dich_co_bao_cao"] == 0
    assert result["so_chien_dich_chua_co_bao_cao"] == 2 and result["so_dong_toan_0"] == 0
    assert "Chi tiêu 0" not in result["cau_tong"] and "campaign không tồn tại" in result["cau_tong"]
    assert "Đối chiếu campaign" in gia.tab_ten() and result["day_du"]

def test_real_zero_insights_is_reported_not_missing(monkeypatch):
    _gia(monkeypatch); setup(monkeypatch, rows=[dict(MASS, spend="0", impressions="0")])
    result = run()
    assert result["so_chien_dich_co_bao_cao"] == 1 and result["so_dong_toan_0"] == 1
    assert result["chien_dich_chua_co_bao_cao"][0]["campaign_id"] == "11"

@pytest.mark.parametrize("failure", ["cut", "permission", "bad_row"])
def test_inventory_failure_never_claims_complete_or_exports(monkeypatch, failure):
    calls = setup(monkeypatch, inventory_cut=failure == "cut", inventory=[{"name": "20/10_PRODUCT"}] if failure == "bad_row" else None)
    if failure == "permission":
        original = T.MetaClient.pages
        def pages(self, tail, *a):
            if tail.endswith("/campaigns"): raise ValueError("Không có quyền Meta")
            return original(self, tail, *a)
        monkeypatch.setattr(T.MetaClient, "pages", pages)
    monkeypatch.setattr(T, "_private_sheet", lambda *a, **k: pytest.fail("exported incomplete inventory"))
    result = run()
    assert "error" in result and "so_chien_dich_khop_ten" not in result

def test_truncated_insights_does_not_claim_missing_report_for_entire_day(monkeypatch):
    setup(monkeypatch, insight_cut=True)
    result = run(xem_truoc=True)
    assert result["bi_cat"] and "chưa thấy trong phần đã đọc" in result["cau_loc"]
    assert "Không có dòng Insights trong khoảng ngày" not in json.dumps(result, ensure_ascii=False)

def test_insights_only_campaign_is_not_dropped_if_deleted_from_inventory(monkeypatch):
    setup(monkeypatch, inventory=INVENTORY[:1])
    result = run(xem_truoc=True)
    assert result["so_chien_dich_khop_ten"] == 2 and result["so_chien_dich_co_bao_cao"] == 1

def test_inventory_matches_unicode_casefold_and_exact_campaign_id(monkeypatch):
    setup(monkeypatch, inventory=[dict(INVENTORY[0], name="20/10_PRODUCT_Mass"), INVENTORY[1]])
    result = run(xem_truoc=True)
    assert result["so_chien_dich_co_bao_cao"] == 1 and result["chien_dich_chua_co_bao_cao"][0]["campaign_id"] == "11"

def test_preview_rechecks_permission_after_inventory(monkeypatch):
    setup(monkeypatch); checks=[]
    monkeypatch.setattr(T, "_allowed", lambda actor: checks.append(actor) or len(checks) == 1)
    result = run(xem_truoc=True)
    assert "error" in result and "chien_dich_chua_co_bao_cao" not in result

def test_preview_campaign_names_are_marked_restricted(monkeypatch):
    setup(monkeypatch); marked=[]
    monkeypatch.setattr(T.lsr_platform, "danh_dau_han_che", marked.append)
    result=run(xem_truoc=True)
    assert marked == ["chi_so_ads"]
    assert {"tab": "Đối chiếu campaign", "so_dong": 2} in result["tab_se_co"]

def test_campaign_pagination_is_get_only_strips_token_and_stays_on_same_account(monkeypatch):
    monkeypatch.setattr(T.MetaClient, "pages", REAL_PAGES)
    calls=[]
    replies=[{"data": [INVENTORY[0]], "paging": {"next": "https://graph.facebook.com/v26.0/act_2/campaigns?after=x&access_token=fake"}},
             {"data": [INVENTORY[1]]}]
    class Response:
        status_code=200
        def json(self): return replies.pop(0)
    def get(url, **kw): calls.append((url,kw)); return Response()
    monkeypatch.setattr(T.requests, "get", get)
    rows, cut=T.MetaClient("fake").pages("act_2/campaigns", {})
    assert rows == INVENTORY and not cut and "access_token" not in calls[1][0]
    assert all(c[1]["allow_redirects"] is False for c in calls)
    with pytest.raises(ValueError):
        T.MetaClient("fake")._url("https://graph.facebook.com/v26.0/act_3/campaigns", "act_2/campaigns")
    with pytest.raises(ValueError):
        T.MetaClient("fake")._url("https://graph.facebook.com/v26.0/act_2/ads")

def test_inventory_cap_across_accounts_does_not_claim_unread_account_empty(monkeypatch):
    monkeypatch.setattr(T, "MAX_CAMPAIGNS", 2)
    setup(monkeypatch)
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: ACC + [dict(ACC[0], id="act_3")])
    result = run(tai_khoan="tat_ca", xem_truoc=True)
    assert "chạm trần" in result["error"] and "so_chien_dich_khop_ten" not in result
