"""Read real tool code with fake Graph, directory and Lark services."""
import datetime as dt
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

import memory_store
import meta_ads_tool as T
import scheduler
import trinh_bay_sheet as TB


P2P = {"channel": "lark", "chat_type": "p2p", "nguoi_gui": "ou_asker"}


@pytest.fixture(autouse=True)
def context(monkeypatch):
    monkeypatch.delenv("MARK_META_AD_ACCOUNT_IDS", raising=False)
    monkeypatch.setattr(T, "_TOKEN", "")
    memory_store.set_current_sender("ou_asker")
    scheduler.set_current_chat(None)
    scheduler.set_current_chat_type("p2p")
    T.set_context(P2P)
    yield
    memory_store.set_current_sender(None)
    scheduler.set_current_chat_type(None)
    T.set_context({})

def response(data, status=200):
    return SimpleNamespace(json=lambda: data, status_code=status)

def run(**args):
    return json.loads(T._handle({"tai_khoan":"tat_ca", "khoang_ngay":"7_ngay", **args}))

def _kq(url="https://sheet.invalid"):
    """KetQua giả cho bài thử thay `_private_sheet` (không chạm Lark)."""
    return TB.KetQua(url, "tok", [url], [], {"day_du": True, "cau": "Đã ghi đủ 1/1 dòng ở 1 tab dữ liệu (đã đọc lại kiểm).", "tabs": []}, [], TB.BAO_CAO)

def _bang(rows=([123],)):
    return TB.Bang("Số ads", [TB.Cot("Chi tiêu (tiền TK)", "tien", cot_tien_te="Tiền tệ"), TB.Cot("Tiền tệ")],
                   [list(r) + ["VND"] for r in rows])

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
    err = run(tai_khoan="act_2")["error"]
    assert "Không thấy" in err and "Approved — act_1" in err and "act_2" not in err.split("“act_2”")[-1]

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

def test_scheduled_actor_never_accepted_yet():
    # Giai đoạn 2: chưa xác minh chat nhận lịch là chat riêng của người đặt → mọi lịch bị từ chối,
    # kể cả khi (giả định) kênh mang chat_type p2p; không mượn người gửi của lượt.
    for ctx in ({"channel":"lark","chat_type":"p2p","nguoi_gui":"ou_asker"}, {"channel":"lark","chat_type":"group"},
                {"channel":"web","chat_type":"p2p"}, {"channel":"lark"}):
        for by in ("ou_scheduler", ""):
            T.set_context({**ctx, "scheduled":True, "scheduled_by":by})
            with pytest.raises(ValueError, match="Lịch số ads chưa hỗ trợ|nhóm"): T._actor()

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
    monkeypatch.setattr(T,"_allowed",lambda actor: actor=="ou_asker")
    calls, sheets = [], []
    class Client:
        def __init__(self,*a): pass
        def accounts(self): return [{"id":"act_1","name":"HAPAS","currency":"VND"}]
        def pages(self,tail,params,limit):
            calls.append(params)
            return [{"spend":"100", "action_values":[{"action_type":"purchase","value":"500"}]}],False
    monkeypatch.setattr(T,"MetaClient",Client)
    monkeypatch.setattr(T,"_private_sheet",lambda title,bang,tq,actor,goc=None: sheets.append((bang,actor)) or _kq())
    result=run(chi_so=["roas"])
    assert result["chi_so"]==["roas"] and result["nguoi_duoc_chia_se"]=="ou_asker"
    # Chỉ xin trường của chỉ số được hỏi + tín hiệu phân phối (hiển thị/chi tiêu) để phân
    # biệt 0 thật với không có số; không xin `actions` khi không hỏi số mua/lead/video.
    assert set(calls[0]["fields"].split(",")) == {"action_values", "spend", "impressions", "account_id",
                                                  "account_name", "date_start", "date_stop"}
    assert len(sheets[0][0].cot)==9 and sheets[0][0].dong[0][-1]==5
    assert sheets[0][1]=="ou_asker"
    assert result["link"]=="https://sheet.invalid" and result["day_du"] is True and "Đã ghi đủ" in result["kiem_ghi"]

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

_CLOSED = {"link_share_entity":"closed","external_access_entity":"closed",
           "share_entity":"same_tenant","manage_collaborator_entity":"collaborator_full_access"}


@pytest.mark.parametrize("public", [{"link_share_entity":"tenant_readable","external_access":False},
                                   {"link_share_entity":"closed","external_access":True}, {},
                                   {**_CLOSED, "share_entity":"anyone"}, {**_CLOSED, "share_entity":None},
                                   {**_CLOSED, "manage_collaborator_entity":"collaborator_can_view"}])
def test_private_sheet_not_written_if_privacy_not_confirmed(monkeypatch, public):
    monkeypatch.setattr(T.A,"_create_sheet",lambda title:("fake","url"))
    monkeypatch.setattr(T.lark,"call",lambda method,*a,**k: {"data":{"permission_public":public}})
    monkeypatch.setattr(T.A,"_write_values",lambda *a:pytest.fail("confidential write"))
    with pytest.raises(ValueError): T._private_sheet("title",_bang(),TB.TongQuan("title"),"ou_asker")

def _lark_rieng(monkeypatch, public=None, hong=()):
    """LarkGia (bảng tính giả) + Drive v2 public permission giả; trả gia."""
    from sheet_gia import LarkGia
    gia = LarkGia(hong=hong)
    import collections
    monkeypatch.setattr(TB, "_LOC_LUOT", collections.deque())   # trần 20 lần lọc/phút
    def call(method, path, query=None, body=None):
        if "/drive/v2/permissions/" in path and path.endswith("/public"):
            gia.goi.append((method, path, query, body))
            return {"data": {"permission_public": dict(_CLOSED if public is None else public)}}
        return gia.call(method, path, query=query, body=body)
    monkeypatch.setattr(T.lark, "call", call)
    monkeypatch.setattr(T.A, "_grant", lambda *a: pytest.fail("edit grant"))
    return gia


def test_private_sheet_closed_before_write_and_only_requester_granted(monkeypatch):
    gia = _lark_rieng(monkeypatch)
    kq = T._private_sheet("title", _bang(), TB.TongQuan("title"), "ou_asker")
    assert kq.url.startswith("https://") and kq.day_du is True
    patch = [g for g in gia.goi if g[0] == "PATCH"]
    assert patch[0][3] == {"external_access_entity":"closed", "link_share_entity":"closed",
                           "share_entity":"same_tenant", "manage_collaborator_entity":"collaborator_full_access"}
    i_patch, i_get = [i for i, g in enumerate(gia.goi) if "/drive/v2/permissions/" in g[1]][:2]
    writes = [i for i, g in enumerate(gia.goi) if g[1].endswith("/values_batch_update")]
    grants = [i for i, g in enumerate(gia.goi) if g[1].endswith("/members")]
    # Khoá + kiểm lại TRƯỚC lần ghi số đầu tiên; quyền XEM cấp SAU lần ghi cuối (cả Tổng quan).
    assert gia.goi[i_patch][0] == "PATCH" and gia.goi[i_get][0] == "GET"
    assert i_patch < i_get < writes[0]
    assert len(grants) == 1 and grants[0] > writes[-1] and grants[0] == len(gia.goi) - 1
    assert gia.goi[-1][0] == "POST" and gia.goi[-1][2] == {"type": "sheet"}
    assert gia.goi[-1][3] == {"member_type":"openid", "member_id":"ou_asker", "perm":"view"}


def test_private_sheet_view_grant_failure_raises_after_data(monkeypatch):
    _lark_rieng(monkeypatch, hong={"/members"})
    with pytest.raises(ValueError, match="Chưa chia sẻ được Sheet riêng"):
        T._private_sheet("title", _bang(), TB.TongQuan("title"), "ou_asker")


_TK = [{"id":"act_1","name":"HTC - [TRANG SỨC] HAPAS 1"},{"id":"act_2","name":"HAPAS 11 - FB ADS"},
       {"id":"act_3","name":"MATEMADE - 5"},{"id":"act_4","name":"HAPAS 1"}]


def test_ambiguous_account_does_not_silently_select_multiple():
    with pytest.raises(ValueError,match="khớp"):
        T._select([{"id":"act_1","name":"HAPAS A"},{"id":"act_2","name":"HAPAS B"}],"HAPAS")


def test_mo_ho_liet_ke_ten_kem_ma_danh_so():
    with pytest.raises(T.ChonTaiKhoan) as e:
        T._select(_TK,"hapas")
    s=str(e.value)
    assert "khớp 3 tài khoản" in s and "1. HTC - [TRANG SỨC] HAPAS 1 — act_1" in s
    assert "HAPAS 11 - FB ADS — act_2" in s and "MATEMADE" not in s and "lấy hết 3" in s


def test_lay_het_khop_lay_ca_nhom():
    assert [a["id"] for a in T._select(_TK,"HAPAS",lay_het=True)]==["act_1","act_2","act_4"]


def test_trung_ten_day_du_thi_chon_dung_mot():
    assert [a["id"] for a in T._select(_TK,"hapas 1")]==["act_4"]
    assert [a["id"] for a in T._select(_TK,"act_3")]==["act_3"]
    assert [a["id"] for a in T._select(_TK,["HAPAS 1","MATEMADE - 5"])]==["act_4","act_3"]


def test_khong_thay_thi_liet_ke_tat_ca_ten():
    with pytest.raises(T.ChonTaiKhoan) as e:
        T._select(_TK,"thai")
    assert "MATEMADE - 5 — act_3" in str(e.value)


def _qua_quyen(monkeypatch, ok=True):
    monkeypatch.setattr(T,"_actor",lambda:"ou_x")
    monkeypatch.setattr(T,"_allowed",lambda actor:ok)
    monkeypatch.setattr(T,"_token",lambda:"tok")


def test_cau_chon_tai_khoan_khong_bi_cat_500_ky_tu(monkeypatch):
    nhieu=[{"id":f"act_{i}","name":f"HAPAS {i} - FB ADS DAI TEN DE VUOT TRAN","currency":"VND"} for i in range(1,21)]
    _qua_quyen(monkeypatch)
    monkeypatch.setattr(T.MetaClient,"accounts",lambda self:nhieu)
    msg=json.dumps(json.loads(T._handle({"tai_khoan":"hapas","khoang_ngay":"7_ngay"})),ensure_ascii=False)
    assert "20. HAPAS 20" in msg and "act_20" in msg


def test_danh_sach_tai_khoan_can_quyen(monkeypatch):
    _qua_quyen(monkeypatch, ok=False)
    monkeypatch.setattr(T.MetaClient,"accounts",lambda self:pytest.fail("không được gọi Meta"))
    out=json.loads(T._handle({"danh_sach_tai_khoan":True}))
    assert "chưa được phép" in json.dumps(out,ensure_ascii=False)


def test_danh_sach_tai_khoan_tra_ten(monkeypatch):
    _qua_quyen(monkeypatch)
    monkeypatch.setattr(T.MetaClient,"accounts",lambda self:_TK)
    out=json.loads(T._handle({"danh_sach_tai_khoan":True}))
    assert out["so_tai_khoan"]==4 and "3. MATEMADE - 5 — act_3" in out["danh_sach"]


def test_large_sheet_grid_and_columns_grow_before_write(monkeypatch):
    gia = _lark_rieng(monkeypatch)
    cot = [TB.Cot(f"c{i}", "so_nguyen") for i in range(25)]
    kq = T._private_sheet("title", TB.Bang("Số ads", cot, [[1] * 25 for _ in range(1205)]),
                          TB.TongQuan("title"), "ou_asker")
    grow = [(i, g[3]["dimension"]) for i, g in enumerate(gia.goi)
            if g[0] == "POST" and g[1].endswith("/dimension_range")]
    writes = [i for i, g in enumerate(gia.goi) if g[1].endswith("/values_batch_update")]
    dims = [d for _, d in grow]
    assert any(d["majorDimension"] == "ROWS" and d["length"] == 1006 for d in dims)
    assert any(d["majorDimension"] == "COLUMNS" and d["length"] == 5 for d in dims)
    assert all(i < writes[0] for i, _ in grow)
    assert len(gia.o("Dữ liệu")) == 1206 and kq.day_du is True


def test_unknown_lark_chat_not_allowed():
    scheduler.set_current_chat("oc_unknown")
    scheduler.set_current_chat_type(None)
    T.set_context({"channel":"lark","nguoi_gui":"ou_asker"})   # thiếu chat_type
    with pytest.raises(ValueError,match="chat riêng"):
        T._actor()
    T.set_context({})                                          # không rõ kênh
    with pytest.raises(ValueError,match="chat riêng"):
        T._actor()

def test_truncated_report_labels_partial_totals(monkeypatch):
    monkeypatch.setenv("MARK_META_ADS_TOKEN","fake")
    monkeypatch.setattr(T,"_allowed",lambda actor:True)
    monkeypatch.setattr(T.MetaClient,"accounts",lambda self:[{"id":"act_1","currency":"VND"}])
    monkeypatch.setattr(T.MetaClient,"pages",lambda *a:([{"spend":"12"}],True))
    sheet=[]
    monkeypatch.setattr(T,"_private_sheet",lambda title,bang,tq,actor,goc=None:sheet.append((bang,tq)) or _kq())
    result=run(chi_so=["spend"])
    assert result["bi_cat"] and "phần đã đọc" in result["cau_tong"]
    bang, tq = sheet[0]
    assert bang.dong_tong[0][0] == "TỔNG PHẦN ĐÃ ĐỌC VND"
    assert any("ĐÃ CẮT ở 20.000 dòng" in g for g in tq.ghi_chu)


# ───────────── review 08/10/2026: danh tính theo kênh, cờ hạn chế, số 0, trang, múi giờ ─────────────
import lsr_platform as P  # noqa: E402


def _ok_meta(monkeypatch, accounts=None, rows=None, calls=None):
    monkeypatch.setenv("MARK_META_ADS_TOKEN", "fake")
    monkeypatch.setattr(T, "_allowed", lambda actor: True)
    accounts = accounts or [{"id": "act_1", "name": "HAPAS", "currency": "VND",
                             "timezone_name": "Asia/Ho_Chi_Minh"}]
    monkeypatch.setattr(T.MetaClient, "accounts", lambda self: accounts)

    def pages(self, tail, params, limit):
        if calls is not None:
            calls.append((tail, params))
        return list(rows if rows is not None else [{"spend": "10", "impressions": "100"}]), False
    monkeypatch.setattr(T.MetaClient, "pages", pages)
    sheets = []
    monkeypatch.setattr(T, "_private_sheet", lambda title, bang, tq, actor, goc=None:
                        sheets.append(_Chup(bang, actor, tq, goc)) or _kq("url"))
    return sheets


class _Chup(tuple):
    """(dòng như sheet cũ: tiêu đề + dữ liệu + trống + tổng, người nhận) + bang/tq/goc."""
    def __new__(cls, bang, actor, tq, goc):
        rows = [[c.ten for c in bang.cot]] + bang.dong + [[]] + bang.dong_tong
        self = super().__new__(cls, (rows, actor))
        self.bang, self.tq, self.goc = bang, tq, goc
        return self


def _job_context(job):
    """Như `_mot_vong` → `brain.reply`: kenh từ cột job, sender qua `_lark_sender_ref`."""
    p = job.get("payload") or {}
    kenh = P._kenh_job_day_du(job, job.get("channel", ""))
    memory_store.set_current_sender(P._lark_sender_ref(p, job.get("channel", "")))
    scheduler.set_current_chat_type(kenh.get("chat_type"))
    T.set_context(kenh)


def test_a2a_forged_user_ref_refused_before_permission_or_meta(monkeypatch):
    monkeypatch.setattr(T, "_allowed", lambda *a: pytest.fail("permission lookup"))
    monkeypatch.setattr(T, "MetaClient", lambda *a: pytest.fail("meta"))
    _job_context({"channel": "a2a", "reply_to": {"channel": "a2a", "chat_type": "p2p"},
                  "payload": {"text": "/soads", "user_ref": "ou_asker", "sender_open_id": "ou_asker",
                              "from_agent": "AG-OTHER"}})
    assert memory_store.get_current_sender() == "ou_asker"   # cửa cũ: user_ref giả thành người hỏi
    assert "A2A" in run()["error"]


@pytest.mark.parametrize("channel", ["telegram", "", "webhook", "khong_ro"])
def test_unknown_channel_refused(monkeypatch, channel):
    monkeypatch.setattr(T, "_allowed", lambda *a: pytest.fail("permission lookup"))
    _job_context({"channel": channel, "reply_to": {"chat_type": "p2p"},
                  "payload": {"sender_open_id": "ou_asker"}})
    assert "kênh" in run()["error"]


def test_lark_job_missing_chat_type_refused(monkeypatch):
    monkeypatch.setattr(T, "_allowed", lambda *a: pytest.fail("permission lookup"))
    _job_context({"channel": "lark", "payload": {"sender_open_id": "ou_asker"}})
    assert "chat riêng" in run()["error"]


def test_lark_job_user_ref_cannot_replace_gateway_sender(monkeypatch):
    monkeypatch.setattr(T, "_allowed", lambda *a: pytest.fail("permission lookup"))
    _job_context({"channel": "lark", "reply_to": {"chat_type": "p2p"},
                  "payload": {"sender_open_id": "ou_real", "user_ref": "ou_asker"}})
    assert "không khớp" in run()["error"]


def test_lark_p2p_gateway_sender_allowed(monkeypatch):
    sheets = _ok_meta(monkeypatch)
    _job_context({"channel": "lark", "reply_to": {"chat_type": "p2p"},
                  "payload": {"sender_open_id": "ou_asker"}})
    assert run()["nguoi_duoc_chia_se"] == "ou_asker" and sheets[0][1] == "ou_asker"


@pytest.mark.parametrize("verified,ok", [(True, True), (False, False), ("true", False), (None, False)])
def test_web_needs_platform_verified_identity(monkeypatch, verified, ok):
    _ok_meta(monkeypatch)
    _job_context({"channel": "web", "payload": {"sender_open_id": "ou_asker", "user_ref": "a@b.vn",
                                                "sender_identity_verified": verified}})
    result = run()
    assert ("link" in result) is ok
    if not ok:
        assert "xác thực" in result["error"]


@pytest.mark.parametrize("reply_to", [
    {"channel": "lark", "chat_id": "oc_1", "app_id": "cli"},                     # đúng như Platform gửi hôm nay
    {"channel": "lark", "chat_id": "oc_1", "app_id": "cli", "chat_type": "p2p"}])  # kể cả khi có chat_type
def test_scheduled_ads_refused_until_phase2(monkeypatch, reply_to):
    """Job lịch của Platform không mang chat_type (app.py lịch → _ingest) và chưa có bằng chứng
    chat riêng đó thuộc `scheduled_by` → lịch số ads luôn bị từ chối, trước tra quyền/Meta."""
    monkeypatch.setattr(T, "_allowed", lambda *a: pytest.fail("permission lookup"))
    monkeypatch.setattr(T, "MetaClient", lambda *a: pytest.fail("meta"))
    _job_context({"channel": "lark", "reply_to": reply_to,
                  "payload": {"scheduled": True, "scheduled_by": "ou_owner", "sender_open_id": "ou_owner",
                              "schedule_id": 7, "schedule_source": "console"}})
    assert "error" in run()


def test_success_marks_turn_and_session_restricted_refusal_does_not(monkeypatch):
    _ok_meta(monkeypatch)
    scheduler.set_current_chat("lark:cli:oc_1")
    box = {}
    P._HOP_HAN_CHE.set(box)
    assert "link" in run()
    assert box == {"tool": "chi_so_ads"}
    assert memory_store.phien_han_che("lark:cli:oc_1") == "chi_so_ads"
    scheduler.set_current_chat("lark:cli:oc_2")
    box = {}
    P._HOP_HAN_CHE.set(box)
    T.set_context({"channel": "a2a"})
    assert "error" in run()
    assert box == {} and memory_store.phien_han_che("lark:cli:oc_2") == ""
    P._HOP_HAN_CHE.set(None)


def test_session_flag_survives_restart_and_fails_closed(monkeypatch, tmp_path):
    memory_store.danh_dau_phien_han_che("web:s1", "chi_so_ads")
    files = list(memory_store._HAN_CHE_DIR.glob("*.json"))
    assert len(files) == 1 and str(tmp_path) in str(files[0])          # không ghi .tokens thật
    assert memory_store.phien_han_che("web:s1") == "chi_so_ads"        # đọc lại từ đĩa
    files[0].write_text("{hỏng", encoding="utf-8")
    assert memory_store.phien_han_che("web:s1") == "restricted"
    assert memory_store.phien_han_che("web:khac") == ""


# Chia nhỏ: Meta có thể ẩn chuyển đổi vì quyền riêng tư → vắng là KHÔNG BIẾT, không phải 0.
def test_breakdown_rows_keep_missing_conversions_blank():
    fetched = {"spend", "impressions", "actions", "action_values", "purchase_roas",
               "video_thruplay_watched_actions"}
    row = {"spend": "50", "impressions": "1000", "age": "18-24"}
    values = T._values(row, fetched, breakdown=True)
    for key in ("purchases", "revenue", "meta_roas", "messages", "leads"):
        assert values[key] is None, key
    assert values["video_3s"] == 0 and values["thruplay"] == 0
    assert T._values(row, fetched)["purchases"] == 0                  # không chia nhỏ: vẫn là 0


def test_breakdown_sheet_blank_and_note(monkeypatch):
    calls = []
    sheets = _ok_meta(monkeypatch, calls=calls, rows=[{"spend": "10", "impressions": "100", "age": "18-24"},
        {"spend": "5", "impressions": "50", "age": "25-34", "actions": [{"action_type": "purchase", "value": "1"}]}])
    result = run(chi_so=["purchases"], chia_theo=["tuoi"])
    sheet = sheets[0][0]
    assert sheet[1][-1] == "" and sheet[2][-1] == 1.0
    assert any("TỔNG" in str(r[0]) and r[-1] == "" for r in sheet if r)
    assert any("quyền riêng tư" in g for g in sheets[0].tq.ghi_chu)
    assert "Mua hàng" not in result["cau_tong"]
    assert calls[0][1]["breakdowns"] == "age"


@pytest.mark.parametrize("switch,on", [
    ([{"tool": "chi_so_ads"}], True), ([{"tool": "chi_so_ads", "bat": True}], True),
    ([{"tool": "chi_so_ads"}, {"tool": "chi_so_ads", "bat": False}], False),
    ([{"tool": "chi_so_ads", "bat": "true"}], False), ([{"tool": "chi_so_ads", "bat": None}], False),
    ([{"tool": "chi_so_ads", "bat": 1}], False), (None, False), ([{"tool": "social_listen"}], False)])
def test_console_switch_must_be_explicitly_on(switch, on):
    assert T._switch_on(switch) is on


# Số 0: Meta bỏ hẳn action bằng 0 khỏi dòng.
def test_missing_actions_on_delivered_row_are_zero_and_totals_not_blank():
    fetched = {"spend", "impressions", "actions", "action_values", "purchase_roas",
               "video_thruplay_watched_actions"}
    delivered = T._values({"spend": "50", "impressions": "1000"}, fetched)
    for key in ("purchases", "revenue", "messages", "leads", "video_3s", "thruplay", "meta_roas"):
        assert delivered[key] == 0, key
    assert delivered["roas"] == 0 and delivered["cost_per_purchase"] is None
    zero_day = T._values({"spend": "0", "impressions": "0"}, fetched)
    assert zero_day["purchases"] == 0 and zero_day["meta_roas"] is None
    no_data = T._values({"date_start": "2026-10-01"}, fetched)
    assert no_data["purchases"] is None and no_data["revenue"] is None
    other = T._values({"spend": "10", "impressions": "5",
                       "actions": [{"action_type": "purchase", "value": "2"}]}, fetched)
    totals = T._totals([{"currency": "VND", "values": delivered}, {"currency": "VND", "values": other}])
    assert totals["VND"]["purchases"] == 2 and totals["VND"]["revenue"] == 0
    totals = T._totals([{"currency": "VND", "values": no_data}, {"currency": "VND", "values": other}])
    assert totals["VND"]["purchases"] is None


def test_unrequested_action_metric_not_zero_filled():
    values = T._values({"spend": "50", "impressions": "1000"}, {"spend", "impressions", "action_values"})
    assert values["revenue"] == 0 and values["purchases"] is None and values["thruplay"] is None


def test_sheet_note_explains_zero_vs_blank(monkeypatch):
    sheets = _ok_meta(monkeypatch, rows=[{"spend": "10", "impressions": "100"}])
    result = run(chi_so=["purchases"])
    sheet = sheets[0][0]
    assert sheet[1][-1] == 0.0
    note = " ".join(sheets[0].tq.ghi_chu)
    assert "ghi 0" in note and "ô trống = Meta không trả số phân phối" in note
    assert "Mua hàng 0" in result["cau_tong"]


# Phân trang danh sách tài khoản theo ID số của người dùng.
def test_adaccounts_next_may_use_numeric_user_id(monkeypatch):
    calls = []
    replies = [response({"data": [{"id": "act_1"}], "paging": {"next":
               "https://graph.facebook.com/v26.0/10158/adaccounts?after=x&access_token=secret"}}),
               response({"data": [{"id": "act_2"}]})]
    monkeypatch.setattr(T.requests, "get", lambda url, **k: calls.append(url) or replies.pop(0))
    rows, cut = T.MetaClient("secret").pages("me/adaccounts", {"limit": 100})
    assert rows == [{"id": "act_1"}, {"id": "act_2"}] and not cut
    assert calls[1].startswith("https://graph.facebook.com/v26.0/10158/adaccounts?") and "secret" not in calls[1]


@pytest.mark.parametrize("next_url", [
    "https://graph.facebook.com/v26.0/10158/owned_ad_accounts?after=x",
    "https://graph.facebook.com/v25.0/10158/adaccounts?after=x",
    "https://evil.test/v26.0/10158/adaccounts?after=x",
    "https://graph.facebook.com/v26.0/act_9/insights?after=x"])
def test_adaccounts_next_cannot_leave_account_list(monkeypatch, next_url):
    replies = [response({"data": [{"id": "act_1"}], "paging": {"next": next_url}})]
    monkeypatch.setattr(T.requests, "get", lambda url, **k: replies.pop(0))
    with pytest.raises(ValueError):
        T.MetaClient("fake").pages("me/adaccounts", {})


def test_numeric_adaccounts_not_an_entry_point_and_insights_next_stays_on_account(monkeypatch):
    monkeypatch.setattr(T.requests, "get", lambda *a, **k: pytest.fail("network"))
    with pytest.raises(ValueError):
        T.MetaClient("fake")._get("https://graph.facebook.com/v26.0/10158/adaccounts")
    with pytest.raises(ValueError):
        T.MetaClient("fake").pages("10158/adaccounts", {})
    replies = [response({"data": [1], "paging": {"next": "https://graph.facebook.com/v26.0/act_2/insights?after=x"}})]
    monkeypatch.setattr(T.requests, "get", lambda url, **k: replies.pop(0))
    with pytest.raises(ValueError):
        T.MetaClient("fake").pages("act_1/insights", {})


# Mốc ngày theo múi giờ tài khoản.
@pytest.mark.parametrize("preset,expected", [
    ("hom_qua", ("2026-10-06", "2026-10-06")), ("7_ngay", ("2026-09-30", "2026-10-06")),
    ("hom_nay", ("2026-10-07", "2026-10-07")), ("thang_nay", ("2026-10-01", "2026-10-07"))])
def test_presets_follow_account_timezone(preset, expected):
    # 08/10 09:00 giờ VN = 07/10 19:00 ở Los Angeles: hôm qua của TK Mỹ là 06/10.
    now = dt.datetime(2026, 10, 8, 9, tzinfo=T.VN)
    assert T._dates({"khoang_ngay": preset}, now, T._tz("America/Los_Angeles")) == expected


class _Clock(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return dt.datetime(2026, 10, 8, 9, tzinfo=T.VN).astimezone(tz)


def test_each_account_queried_in_its_own_timezone(monkeypatch):
    calls = []
    sheets = _ok_meta(monkeypatch, calls=calls, accounts=[
        {"id": "act_1", "name": "VN", "currency": "VND", "timezone_name": "Asia/Ho_Chi_Minh"},
        {"id": "act_2", "name": "US", "currency": "USD", "timezone_name": "America/Los_Angeles"}])
    monkeypatch.setattr(T.dt, "datetime", _Clock)
    result = run(khoang_ngay="hom_qua")
    ranges = {tail: json.loads(params["time_range"]) for tail, params in calls}
    assert ranges["act_1/insights"] == {"since": "2026-10-07", "until": "2026-10-07"}
    assert ranges["act_2/insights"] == {"since": "2026-10-06", "until": "2026-10-06"}
    assert "theo múi giờ từng TK" in result["cau_tong"] and "chưa hết ngày" not in result["cau_tong"]
    assert [row[3] for row in sheets[0][0][1:3]] == ["Asia/Ho_Chi_Minh", "America/Los_Angeles"]


@pytest.mark.parametrize("preset", ["thang_nay", "hom_nay"])
def test_partial_today_is_stated(monkeypatch, preset):
    sheets = _ok_meta(monkeypatch)
    result = run(khoang_ngay=preset)
    assert "hôm nay chưa hết ngày" in result["cau_tong"]
    assert any("ngày chưa hết" in g for g in sheets[0].tq.ghi_chu)


def test_completed_presets_not_marked_partial(monkeypatch):
    _ok_meta(monkeypatch)
    for preset in ("hom_qua", "7_ngay", "thang_truoc"):
        assert "chưa hết ngày" not in run(khoang_ngay=preset)["cau_tong"]


def test_unknown_account_timezone_falls_back_to_vn_and_says_so(monkeypatch):
    sheets = _ok_meta(monkeypatch, accounts=[{"id": "act_1", "name": "X", "currency": "VND",
                                             "timezone_name": "Not/AZone"}])
    run(khoang_ngay="hom_qua")
    assert any("không báo múi giờ" in g for g in sheets[0].tq.ghi_chu)


# Token: không lọt vào bộ thử, không lọt vào tiến trình con.
def test_local_dotenv_meta_token_does_not_leak_into_tests(monkeypatch, tmp_path):
    import os

    import config
    assert "MARK_META_ADS_TOKEN" not in os.environ and T._TOKEN == ""
    env = tmp_path / ".env"
    env.write_text("MARK_META_ADS_TOKEN=leak-from-local-env\nMARK_META_AD_ACCOUNT_IDS=act_1\n"
                   "MARK_TEST_DOTENV_PROBE=seen\n", encoding="utf-8")
    monkeypatch.delenv("MARK_TEST_DOTENV_PROBE", raising=False)
    try:
        config._load_dotenv(env)
        assert os.environ.get("MARK_TEST_DOTENV_PROBE") == "seen"     # loader vẫn chạy
        assert "MARK_META_ADS_TOKEN" not in os.environ
        assert "MARK_META_AD_ACCOUNT_IDS" not in os.environ
        # Máy chạy thật (không đặt MARK_DOTENV_BO_QUA) vẫn nạp `.env` như cũ.
        monkeypatch.delenv("MARK_DOTENV_BO_QUA")
        config._load_dotenv(env)
        assert os.environ["MARK_META_ADS_TOKEN"] == "leak-from-local-env"
    finally:
        for key in ("MARK_META_ADS_TOKEN", "MARK_META_AD_ACCOUNT_IDS", "MARK_TEST_DOTENV_PROBE"):
            os.environ.pop(key, None)


def test_child_process_envs_strip_meta_secrets(monkeypatch):
    import cli_support
    monkeypatch.setenv("MARK_META_ADS_TOKEN", "secret-token")
    monkeypatch.setenv("MARK_META_AD_ACCOUNT_IDS", "act_1")
    monkeypatch.setenv("PATH_PROBE", "kept")
    for env in (cli_support.cli_env(), cli_support.env_tien_trinh_con()):
        assert not any(k.startswith("MARK_META_") for k in env) and env["PATH_PROBE"] == "kept"
    assert "secret-token" not in json.dumps(cli_support.cli_env())


def test_scrapling_runners_use_stripped_env(monkeypatch):
    import crawl_tool
    import web_tool
    for module in (crawl_tool, web_tool):
        assert "env_tien_trinh_con()" in open(module.__file__, encoding="utf-8").read()
        assert "dict(os.environ)" not in open(module.__file__, encoding="utf-8").read()


def test_token_held_in_module_memory_is_used(monkeypatch):
    monkeypatch.delenv("MARK_META_ADS_TOKEN", raising=False)
    monkeypatch.setattr(T, "_TOKEN", "held")
    assert T._token() == "held"
