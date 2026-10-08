"""Read real tool code with fake Graph, directory and Lark services."""
import datetime as dt
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

import memory_store
import meta_ads_tool as T
import scheduler


@pytest.fixture(autouse=True)
def context(monkeypatch):
    monkeypatch.delenv("MARK_META_AD_ACCOUNT_IDS", raising=False)
    memory_store.set_current_sender("ou_asker")
    scheduler.set_current_chat(None)
    scheduler.set_current_chat_type("p2p")
    T.set_context({})
    yield
    memory_store.set_current_sender(None)
    scheduler.set_current_chat_type(None)
    T.set_context({})

def response(data, status=200):
    return SimpleNamespace(json=lambda: data, status_code=status)

def run(**args):
    return json.loads(T._handle({"tai_khoan":"tat_ca", "khoang_ngay":"7_ngay", **args}))

@pytest.mark.parametrize("aliases", [["purchase","omni_purchase"], ["omni_purchase","offsite_conversion.fb_pixel_purchase"]])
def test_overlapping_purchase_aliases_are_not_added(aliases):
    items = [{"action_type":a,"value":str(i+2)} for i,a in enumerate(aliases)]
    assert T._action(items, T.PURCHASE) == Decimal(2)

def test_zero_canonical_wins_fallback():
    assert T._action([{"action_type":"purchase","value":"0"},
                     {"action_type":"omni_purchase","value":"9"}], T.PURCHASE) == 0

def test_action_ratios_and_lead_video():
    row = {"spend":"120", "impressions":"1000", "clicks":"12", "reach":"500",
        "actions":[{"action_type":"purchase","value":"3"}, {"action_type":"omni_purchase","value":"9"},
                   {"action_type":"lead","value":"4"}, {"action_type":"video_view","value":"24"},
                   {"action_type":"onsite_conversion.messaging_conversation_started_7d","value":"6"}],
        "action_values":[{"action_type":"purchase","value":"600"}],
        "video_thruplay_watched_actions":[{"action_type":"video_view","value":"8"}]}
    values = T._values(row)
    assert values["roas"] == 5 and values["cost_per_purchase"] == 40
    assert values["ctr"] == Decimal("1.2") and values["cpc"] == 10 and values["cpm"] == 120
    assert values["cost_per_lead"] == 30 and values["cost_per_message"] == 20
    assert values["video_3s"] == 24 and values["cost_per_thruplay"] == 15

@pytest.mark.parametrize("value", [None, "", True, "NaN", "Infinity", "bad"])
def test_invalid_numbers_stay_unknown(value):
    assert T._number(value) is None

def test_no_zero_for_missing_and_no_divide_by_zero():
    assert T._values({"spend":"0"})["roas"] is None
    assert T._action([], T.PURCHASE) is None
    assert T._cell(None) == ""

def test_currency_groups_weight_ratios_and_do_not_sum_reach():
    rows = [{"currency":c, "values":T._values({"spend":s,"clicks":k,"impressions":i,"reach":"10"})}
            for c,s,k,i in [("VND","100","10","100"),("VND","300","20","400"),("USD","20","2","10")]]
    totals = T._totals(rows)
    assert totals["VND"]["spend"] == 400 and totals["USD"]["spend"] == 20
    assert totals["VND"]["ctr"] == 6 and totals["VND"].get("reach") is None
    assert totals["VND"]["revenue"] is None

@pytest.mark.parametrize("preset,expected", [
    ("hom_nay",("2026-10-08","2026-10-08")), ("hom_qua",("2026-10-07","2026-10-07")),
    ("7_ngay",("2026-10-01","2026-10-07")), ("14_ngay",("2026-09-24","2026-10-07")),
    ("30_ngay",("2026-09-08","2026-10-07")), ("thang_nay",("2026-10-01","2026-10-08")),
    ("thang_truoc",("2026-09-01","2026-09-30"))])
def test_vn_date_presets(preset, expected):
    assert T._dates({"khoang_ngay":preset}, dt.datetime(2026,10,7,18,tzinfo=dt.timezone.utc)) == expected

@pytest.mark.parametrize("args", [{"tu_ngay":"2026-01-01","den_ngay":"2026-05-01"},
    {"tu_ngay":"2026-10-02","den_ngay":"2026-10-01"}, {"tu_ngay":"2026-01-01"},
    {"tu_ngay":"2026-10-09","den_ngay":"2026-10-09"}])
def test_bad_date_ranges(args):
    with pytest.raises(ValueError):
        T._dates(args, dt.datetime(2026,10,8,tzinfo=T.VN))

@pytest.mark.parametrize("url", ["http://graph.facebook.com/v26.0/me/adaccounts", "https://evil.test/v26.0/me/adaccounts",
    "https://graph.facebook.com:443/v26.0/me/adaccounts", "https://graph.facebook.com/v26.0/act_1",
    "https://graph.facebook.com/v26.0/act_1/ads", "https://graph.facebook.com/v26.0/me/adaccounts#evil",
    "https://graph.facebook.com/v26.0/1417955788397052/owned_ad_accounts"])
def test_read_endpoint_allowlist_before_network(monkeypatch, url):
    monkeypatch.setattr(T.requests,"get",lambda *a,**k: pytest.fail("network"))
    with pytest.raises(ValueError):
        T.MetaClient("fake")._get(url)

def test_paging_sanitizes_token_get_only(monkeypatch):
    calls = []
    replies = [response({"data":[{"id":1}],"paging":{"next":"https://graph.facebook.com/v26.0/act_1/insights?after=2&access_token=secret"}}),
               response({"data":[{"id":2}]})]
    def get(url, **kw):
        calls.append((url,kw))
        return replies.pop(0)
    monkeypatch.setattr(T.requests,"get",get)
    rows, cut = T.MetaClient("secret").pages("act_1/insights",{})
    assert rows == [{"id":1},{"id":2}] and not cut
    assert "secret" not in calls[1][0] and calls[1][1]["allow_redirects"] is False
    assert calls[0][1]["headers"] == {"Authorization":"Bearer secret"}

def test_paging_wrong_host(monkeypatch):
    monkeypatch.setattr(T.requests,"get",lambda *a,**k: response({"data":[],"paging":{"next":"https://evil.test/v26.0/act_1/insights"}}))
    with pytest.raises(ValueError):
        T.MetaClient("fake").pages("act_1/insights",{})

def test_cap_is_explicit(monkeypatch):
    monkeypatch.setattr(T.requests,"get",lambda *a,**k: response({"data":[1,2,3]}))
    assert T.MetaClient("fake").pages("act_1/insights",{},2) == ([1,2],True)

def test_rate_limit_retries_bounded(monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(T.requests,"get",lambda *a,**k: calls.append(1) or response({"error":{"code":613}}))
    monkeypatch.setattr(T.time,"sleep",sleeps.append)
    with pytest.raises(ValueError, match="giới hạn"):
        T.MetaClient("fake").pages("act_1/insights",{})
    assert len(calls)==3 and sleeps == [1,2]

@pytest.mark.parametrize("code,message", [(190,"hết hạn"),(200,"quyền Meta"),(100,"mã 100")])
def test_errors_never_surface_token(monkeypatch, code, message):
    monkeypatch.setattr(T.requests,"get",lambda *a,**k: response({"error":{"code":code,"message":"access_token=secret"}}))
    with pytest.raises(ValueError) as error:
        T.MetaClient("secret").pages("act_1/insights",{})
    assert message in str(error.value) and "secret" not in str(error.value)

def test_redaction():
    assert "secret" not in T._redact("URL access_token=secret&next=1; secret", "secret")

def test_accounts_are_approved_and_currently_granted(monkeypatch):
    monkeypatch.setenv("MARK_META_AD_ACCOUNT_IDS", "act_1, 2,act_2")
    client = T.MetaClient("fake")
    def pages(tail, params, limit):
        assert tail == "me/adaccounts"
        assert params["fields"] == "id,name,currency,timezone_name"
        return [{"id": "act_2", "name": "Renamed account", "currency": "VND"},
                {"id": "act_3", "name": "HAPAS", "currency": "USD"}], False
    monkeypatch.setattr(client, "pages", pages)
    assert client.accounts() == [{"id": "act_2", "name": "Renamed account", "currency": "VND"}]


@pytest.mark.parametrize("raw", ["", " ", "*", "tat_ca", "act_1,", "act_1,evil", "act_0", "-1",
                                "act_1/insights", "act_1,act_2;act_3", ",".join(["act_1"] * 201)])
def test_invalid_approved_ids_close_before_meta(monkeypatch, raw):
    monkeypatch.setenv("MARK_META_AD_ACCOUNT_IDS", raw)
    client = T.MetaClient("fake")
    monkeypatch.setattr(client, "pages", lambda *a: pytest.fail("network before config validation"))
    with pytest.raises(ValueError, match="MARK_META_AD_ACCOUNT_IDS"):
        client.accounts()


def test_revoked_account_is_excluded(monkeypatch):
    monkeypatch.setenv("MARK_META_AD_ACCOUNT_IDS", "act_1")
    client = T.MetaClient("fake")
    monkeypatch.setattr(client, "pages", lambda *a: ([{"id": "act_2"}], False))
    assert client.accounts() == []


def test_truncated_granted_accounts_close(monkeypatch):
    monkeypatch.setenv("MARK_META_AD_ACCOUNT_IDS", "act_1")
    client = T.MetaClient("fake")
    monkeypatch.setattr(client, "pages", lambda *a: ([{"id": "act_1"}], True))
    with pytest.raises(ValueError, match="bị cắt"):
        client.accounts()


def test_unapproved_requested_account_never_fetches_insights(monkeypatch):
    monkeypatch.setenv("MARK_META_ADS_TOKEN", "fake")
    monkeypatch.setenv("MARK_META_AD_ACCOUNT_IDS", "act_1")
    monkeypatch.setattr(T, "_allowed", lambda actor: True)
    def pages(self, tail, *a):
        assert tail == "me/adaccounts", "unapproved insights"
        return [{"id": "act_1", "name": "Approved", "currency": "VND"},
                {"id": "act_2", "name": "HAPAS", "currency": "VND"}], False
    monkeypatch.setattr(T.MetaClient, "pages", pages)
    monkeypatch.setattr(T, "_private_sheet", lambda *a: pytest.fail("disclosed"))
    assert "Không tìm thấy" in run(tai_khoan="act_2")["error"]

@pytest.mark.parametrize("people,caps,allowed", [([], [{"tool":"chi_so_ads"}], False),
    (["ou_asker"], [{"tool":"chi_so_ads"}], True), (["ou_other"], [{"tool":"chi_so_ads"}], False),
    (["ou_asker"], [], False), (["ou_asker"], [{"tool":"chi_so_ads","bat":False}], False)])
def test_directory_list_and_switch(monkeypatch, people, caps, allowed):
    monkeypatch.setenv("LSR_TELEMETRY_API_KEY","fake")
    monkeypatch.setenv("LSR_PLATFORM_URL","https://platform.invalid")
    data={"caller":"AG-MARK","agents":[{"agent_id":"AG-MARK","capabilities":caps,"tool_allowlists":{"chi_so_ads":people}},
          {"agent_id":"AG-OTHER","capabilities":[{"tool":"chi_so_ads"}],"tool_allowlists":{"chi_so_ads":["ou_asker"]}}]}
    class Reply:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def read(self): return json.dumps(data).encode()
    monkeypatch.setattr(T.urllib.request,"urlopen",lambda *a,**k: Reply())
    assert T._allowed("ou_asker") is allowed

def test_directory_failure_closes(monkeypatch):
    monkeypatch.setenv("LSR_TELEMETRY_API_KEY","fake")
    monkeypatch.setenv("LSR_PLATFORM_URL","https://platform.invalid")
    monkeypatch.setattr(T.urllib.request,"urlopen",lambda *a,**k: (_ for _ in ()).throw(OSError("offline")))
    assert not T._allowed("ou_asker")

def test_scheduled_actor_cannot_borrow_sender():
    T.set_context({"scheduled":True,"scheduled_by":"ou_scheduler"})
    assert T._actor()=="ou_scheduler"
    T.set_context({"scheduled":True,"scheduled_by":""})
    with pytest.raises(ValueError): T._actor()

def test_group_refused_before_meta(monkeypatch):
    scheduler.set_current_chat_type("group")
    monkeypatch.setattr(T,"_allowed",lambda *a: pytest.fail("permission/network"))
    assert "chat riêng" in run()["error"]

def test_missing_token_clear_message(monkeypatch):
    monkeypatch.setattr(T,"_allowed",lambda actor: True)
    monkeypatch.delenv("MARK_META_ADS_TOKEN",raising=False)
    assert "Chưa cấu hình" in run()["error"]

def test_catalog_all_metrics_without_token_or_permission(monkeypatch):
    monkeypatch.setattr(T,"_allowed",lambda *a: pytest.fail("permission"))
    data=json.loads(T._handle({"danh_muc":True}))
    assert set(data["nhom"])==set(T.GROUPS)
    assert sum(map(len,data["nhom"].values())) == len(T.METRICS)
    assert all(m["ten"] and m["don_vi"] and m["y_nghia"] for g in data["nhom"].values() for m in g)

def test_exact_requested_metrics_and_private_recipient(monkeypatch):
    monkeypatch.setenv("MARK_META_ADS_TOKEN","fake")
    monkeypatch.setattr(T,"_allowed",lambda actor: actor=="ou_scheduler")
    T.set_context({"scheduled":True,"scheduled_by":"ou_scheduler"})
    calls, sheets = [], []
    class Client:
        def __init__(self,*a): pass
        def accounts(self): return [{"id":"act_1","name":"HAPAS","currency":"VND"}]
        def pages(self,tail,params,limit):
            calls.append(params)
            return [{"spend":"100", "action_values":[{"action_type":"purchase","value":"500"}]}],False
    monkeypatch.setattr(T,"MetaClient",Client)
    monkeypatch.setattr(T,"_private_sheet",lambda title,rows,actor: sheets.append((rows,actor)) or "https://sheet.invalid")
    result=run(chi_so=["roas"])
    assert result["chi_so"]==["roas"] and result["nguoi_duoc_chia_se"]=="ou_scheduler"
    assert "impressions" not in calls[0]["fields"] and "actions," not in calls[0]["fields"]
    assert len(sheets[0][0][0])==9 and sheets[0][0][1][-1]==5
    assert sheets[0][1]=="ou_scheduler"

@pytest.mark.parametrize("breakdown", [["vi_tri"],["tuoi","nen_tang"],["unknown"]])
def test_invalid_breakdown_before_meta(monkeypatch, breakdown):
    monkeypatch.setattr(T,"_allowed",lambda a: True)
    assert "error" in run(chia_theo=breakdown)

def test_permission_recheck_prevents_sheet(monkeypatch):
    monkeypatch.setenv("MARK_META_ADS_TOKEN","fake")
    checks=iter([True,False])
    monkeypatch.setattr(T,"_allowed",lambda actor:next(checks))
    monkeypatch.setattr(T.MetaClient,"accounts",lambda self:[{"id":"act_1","currency":"VND"}])
    monkeypatch.setattr(T.MetaClient,"pages",lambda *a:([],False))
    monkeypatch.setattr(T,"_private_sheet",lambda *a:pytest.fail("disclosed"))
    assert "Quyền xem" in run()["error"]

@pytest.mark.parametrize("public", [{"link_share_entity":"tenant_readable","external_access":False},
                                   {"link_share_entity":"closed","external_access":True}, {}])
def test_private_sheet_not_written_if_privacy_not_confirmed(monkeypatch, public):
    monkeypatch.setattr(T.A,"_create_sheet",lambda title:("fake","url"))
    monkeypatch.setattr(T.lark,"call",lambda method,*a,**k: {"data":{"permission_public":public}})
    monkeypatch.setattr(T.A,"_write_values",lambda *a:pytest.fail("confidential write"))
    with pytest.raises(ValueError): T._private_sheet("title",[[123]],"ou_asker")

def test_private_sheet_closed_before_write_and_only_requester_granted(monkeypatch):
    events=[]
    monkeypatch.setattr(T.A,"_create_sheet",lambda title:("fake","url"))
    def call(method,path,**kwargs):
        events.append((method,kwargs))
        return {"data":{"permission_public":{"link_share_entity":"closed","external_access_entity":"closed",
                    "share_entity":"same_tenant","manage_collaborator_entity":"collaborator_full_access"}}}
    monkeypatch.setattr(T.lark,"call",call)
    monkeypatch.setattr(T.A,"_first_sheet_id",lambda token:"sid")
    monkeypatch.setattr(T.A,"_write_values",lambda *a,**k:events.append(("WRITE",a)))
    monkeypatch.setattr(T.A,"_grant",lambda token,actor:events.append(("GRANT",actor)) or True)
    assert T._private_sheet("title",[[123]],"ou_asker")=="url"
    assert events[0][0]=="PATCH"
    assert events[0][1]["body"] == {"external_access_entity":"closed", "link_share_entity":"closed",
                                  "share_entity":"same_tenant", "manage_collaborator_entity":"collaborator_full_access"}
    assert events[-1]==("GRANT","ou_asker")

def test_ambiguous_account_does_not_silently_select_multiple():
    with pytest.raises(ValueError,match="chưa rõ"):
        T._select([{"id":"act_1","name":"HAPAS A"},{"id":"act_2","name":"HAPAS B"}],"HAPAS")


def test_large_sheet_grid_and_columns_grow_before_write(monkeypatch):
    events=[]
    monkeypatch.setattr(T.A,"_create_sheet",lambda title:("fake","url"))
    monkeypatch.setattr(T.A,"_first_sheet_id",lambda token:"sid")
    def call(method,path,**kwargs):
        if "/public" in path:
            return {"data":{"permission_public":{"link_share_entity":"closed","external_access_entity":"closed",
                    "share_entity":"same_tenant","manage_collaborator_entity":"collaborator_full_access"}}}
        return {"data":{"sheets":[{"sheet_id":"sid","grid_properties":{"row_count":200,"column_count":20}}]}}
    monkeypatch.setattr(T.lark,"call",call)
    import sheet_lon
    monkeypatch.setattr(sheet_lon,"_goi",lambda method,path,**k:events.append(k["body"]["dimension"]))
    monkeypatch.setattr(T.A,"_write_values",lambda *a,**k:events.append({"write":len(a[2]),"start":k["dong_dau"]}))
    monkeypatch.setattr(T.A,"_grant",lambda *a:True)
    monkeypatch.setattr(T.time,"sleep",lambda *a:None)
    assert T._private_sheet("title",[[1]*25 for _ in range(1205)],"ou_asker")=="url"
    assert events[:2]==[{"sheetId":"sid","majorDimension":"ROWS","length":1005},
                       {"sheetId":"sid","majorDimension":"COLUMNS","length":5}]
    assert events[2:]==[{"write":1000,"start":1},{"write":205,"start":1001}]

def test_unknown_lark_chat_not_allowed():
    scheduler.set_current_chat("oc_unknown")
    scheduler.set_current_chat_type(None)
    with pytest.raises(ValueError,match="chat riêng"):
        T._actor()

def test_truncated_report_labels_partial_totals(monkeypatch):
    monkeypatch.setenv("MARK_META_ADS_TOKEN","fake")
    monkeypatch.setattr(T,"_allowed",lambda actor:True)
    monkeypatch.setattr(T.MetaClient,"accounts",lambda self:[{"id":"act_1","currency":"VND"}])
    monkeypatch.setattr(T.MetaClient,"pages",lambda *a:([{"spend":"12"}],True))
    sheet=[]
    monkeypatch.setattr(T,"_private_sheet",lambda title,rows,actor:sheet.extend(rows) or "url")
    result=run(chi_so=["spend"])
    assert result["bi_cat"] and "phần đã đọc" in result["cau_tong"]
    assert any("TỔNG PHẦN ĐÃ ĐỌC" in str(row) for row in sheet)
