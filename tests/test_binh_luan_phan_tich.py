"""Canh đợt 3 (01/10/2026): social_deep_dive chia lô theo trần chi phí, hỏi trước khi vượt
ngân sách, báo bài có thể bị cắt, quy bình luận về bài theo ID, ghi chi phí — và
phan_loai gán nhãn sắc thái/chủ đề rồi đếm.

Lỗi thật 01/10: 25 bài TikTok gửi chung một lượt (maxItems 1250) chạm trần 0,37 USD sau
~300 bình luận — 12 bài có bình luận, 13 bài hiện 0 mà Mark báo "chưa ai bình luận".
Không bài nào ở đây gọi Apify, Lark hay model thật.
"""
from __future__ import annotations

import json
import time

import pytest

import apify_tool as A
import deep_dive_tool as D
import phan_loai as P

TT = "https://www.tiktok.com/@kenh/video/{}"


def _bl(video, text="ok", likes=0, **kw):
    return {"uniqueId": "u", "text": text, "diggCount": likes, "videoWebUrl": video, **kw}


class _Apify:
    """`_call` giả: ghi lại từng lượt, trả dữ liệu theo hàm `tra(payload, limit)`."""

    def __init__(self, tra=None):
        self.goi = []
        self.tra = tra or (lambda payload, limit: [])

    def __call__(self, actor, payload, limit, mem=None, min_charge=0, tran_usd=None):
        self.goi.append({"actor": actor, "payload": payload, "limit": limit,
                         "tran_usd": tran_usd, "min_charge": min_charge})
        return self.tra(payload, limit)


def _model_gia(nhac: str) -> str:
    """Model giả: gán nhãn theo từ khoá trong từng dòng "i: text"."""
    ra = {}
    for dong in nhac.split("\n"):
        if ": " not in dong or not dong.split(": ", 1)[0].isdigit():
            continue
        i, t = dong.split(": ", 1)
        ra[i] = (["+", "SP"] if "đẹp" in t else ["-", "DV"] if "chậm" in t
                 else ["=", "GIA"] if "giá" in t else ["=", "KHAC"])
    return json.dumps(ra)


@pytest.fixture
def moi_truong(monkeypatch):
    ap = _Apify()
    ghi_so, ghi_sheet, ghi_tab = [], [], []
    monkeypatch.setattr(D, "_call", ap)
    monkeypatch.setattr(D, "_cau_hinh", lambda: (300, 0.5))
    monkeypatch.setattr(A, "_tran", lambda: (500, 0.37))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 0.2, "so_run": len(ap.goi), "cham_tran": 0, "dang_chay": 0})
    monkeypatch.setattr(D.chi_phi_tool, "ghi", lambda **k: ghi_so.append(k) or {})
    monkeypatch.setattr(D.phan_loai, "_goi_model", _model_gia)
    monkeypatch.setattr(D, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(D, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(D, "_write", lambda tok, sid, values: ghi_sheet.extend(values))
    monkeypatch.setattr(A, "_them_tab", lambda tok, ten: ghi_tab.append(ten) or "s2")
    monkeypatch.setattr(A, "_write_values", lambda tok, sid, rows, **k: ghi_tab.append((sid, rows)))
    monkeypatch.setattr(D, "_grant", lambda tok, oid: True)
    monkeypatch.setattr(D.memory_store, "get_current_sender", lambda: "ou_test")
    return ap, ghi_so, ghi_sheet, ghi_tab


# ───────────────────────── chia lô, cổng xác nhận ─────────────────────────
def test_chia_lo_moi_luot_gon_trong_tran(moi_truong):
    ap = moi_truong[0]
    urls = [TT.format(7000000 + i) for i in range(25)]
    kq = json.loads(D._handle({"post_urls": urls, "xac_nhan_chi_phi": True}))
    # 0,9 × 0,5 / 0,00125 = 360 bình luận mỗi lượt → 7 bài × 50
    assert [len(g["payload"]["postURLs"]) for g in ap.goi] == [7, 7, 7, 4]
    for g in ap.goi:
        assert g["limit"] * 0.00125 <= 0.9 * 0.5, "mỗi lượt phải nằm dưới trần"
        assert g["tran_usd"] == 0.5, "trần riêng của deep_dive, không phải 0,37 của listen"
    gui = [u for g in ap.goi for u in g["payload"]["postURLs"]]
    assert sorted(gui) == sorted(urls), "mỗi bài đúng một lần"
    assert kq["so_luot_chay"] == 4


def test_vuot_ngan_sach_thi_hoi_truoc_khong_goi_apify(moi_truong):
    ap = moi_truong[0]
    urls = [TT.format(7000000 + i) for i in range(25)]
    kq = json.loads(D._handle({"post_urls": urls}))
    assert ap.goi == [], "chưa xác nhận thì không được chạy lượt nào"
    assert kq["can_xac_nhan"] is True and kq["chua_chay"] is True
    assert kq["uoc_tinh_binh_luan"] == 1250
    assert kq["uoc_tinh_chi_phi_usd"] == pytest.approx(1.5625, abs=0.001)
    assert kq["vua_ngan_sach"]["max_comments_cho_du_bai"] == 12, "300 // 25 bài"
    assert "xac_nhan_chi_phi" in kq["note"] and "CHƯA CHẠY" in kq["note"]


def test_vuot_usd_du_chua_vuot_so_binh_luan_cung_phai_hoi(moi_truong, monkeypatch):
    ap = moi_truong[0]
    monkeypatch.setattr(D, "_cau_hinh", lambda: (3000, 0.1))
    kq = json.loads(D._handle({"post_urls": [TT.format(7000001 + i) for i in range(2)]}))
    assert kq["can_xac_nhan"] is True and ap.goi == []


def test_trong_ngan_sach_thi_chay_ngay(moi_truong):
    ap = moi_truong[0]
    D._handle({"post_urls": [TT.format(7000001)]})
    assert len(ap.goi) == 1


# ───────────────────────── bài bị cắt, quy về bài ─────────────────────────
def test_bai_rong_trong_luot_cham_han_muc_bi_bao_co_the_cat(moi_truong):
    ap = moi_truong[0]
    a, b, c = (TT.format(7000001), TT.format(7000002), TT.format(7000003))
    ap.tra = lambda payload, limit: [_bl(a, f"bl {i}") for i in range(limit)]
    kq = json.loads(D._handle({"post_urls": [a, b, c], "max_comments": 10}))
    assert kq["per_url"][a] == {"platform": "tiktok", "status": "OK", "comments": 30}
    for u in (b, c):
        assert kq["per_url"][u]["status"] == "CÓ THỂ BỊ CẮT DO TRẦN CHI PHÍ"
        assert "KHÔNG phải bài không có bình luận" in kq["per_url"][u]["ghi_chu"]
    assert kq["so_bai_co_the_bi_cat"] == 2 and kq["cham_tran_chi_phi"] is True
    assert "CÓ THỂ BỊ CẮT" in D.SCHEMA["description"]
    assert "0 comment là BÌNH THƯỜNG" not in D.SCHEMA["description"]


def test_luot_khong_cham_han_muc_thi_bai_rong_la_that(moi_truong):
    ap = moi_truong[0]
    a, b = TT.format(7000001), TT.format(7000002)
    ap.tra = lambda payload, limit: [_bl(a, "đẹp")] * 3
    kq = json.loads(D._handle({"post_urls": [a, b], "max_comments": 10}))
    assert kq["per_url"][b] == {"platform": "tiktok", "status": "OK", "comments": 0}


def test_quy_ve_bai_theo_id_khong_theo_chuoi_con(moi_truong):
    """…/video/7000001 từng khớp nhầm …/video/70000011 (chuỗi con); link vt.tiktok khớp
    qua submittedVideoUrl."""
    ap = moi_truong[0]
    a = TT.format(7000001) + "?is_from_webapp=1"
    b = "https://www.tiktok.com/@khac/video/70000011"
    ngan = "https://vt.tiktok.com/ZSabc123/"
    ap.tra = lambda payload, limit: [
        _bl(TT.format(7000001)), _bl(TT.format(7000001)),
        _bl(b),
        _bl(TT.format(7999999), submittedVideoUrl=ngan)]
    kq = json.loads(D._handle({"post_urls": [a, b, ngan]}))
    assert [kq["per_url"][u]["comments"] for u in (a, b, ngan)] == [2, 1, 1]
    assert kq["khong_quy_ve_bai"] == 0


def test_id_bai_cac_nen_tang():
    assert D._id_bai("https://youtu.be/dQw4w9WgXcQ?t=3") == "youtube:dQw4w9WgXcQ"
    assert D._id_bai("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "youtube:dQw4w9WgXcQ"
    assert D._id_bai("https://www.facebook.com/hapas/posts/pfbid02abc") == "facebook:pfbid02abc"
    assert D._id_bai("https://www.facebook.com/permalink.php?story_fbid=123&id=9") == "facebook:123"
    assert D._chuan("https://www.youtube.com/watch?v=a") != D._chuan("https://youtube.com/watch?v=b")


# ───────────────────────── chi phí, sheet, thống kê ─────────────────────────
def test_ghi_chi_phi_that_vao_so(moi_truong):
    ap, ghi_so = moi_truong[0], moi_truong[1]
    ap.tra = lambda payload, limit: [_bl(TT.format(7000001), "đẹp")]
    kq = json.loads(D._handle({"post_urls": [TT.format(7000001)]}))
    assert len(ghi_so) == 1 and ghi_so[0]["thuc"]["usd"] == 0.2
    assert ghi_so[0]["est"] == pytest.approx(50 * 0.00125)
    assert kq["chi_phi_thuc_usd"] == 0.2 and "0,20 USD" in kq["chi_phi"]


def test_co_cham_tran_cua_listen_khong_lam_bao_nham(moi_truong, monkeypatch):
    """`_chi_phi_thuc` so với trần 0,37 của listen; lô 0,45 của deep_dive không phải chạm trần."""
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 0.44, "so_run": 1, "cham_tran": 1, "dang_chay": 0})
    kq = json.loads(D._handle({"post_urls": [TT.format(7000001)]}))
    assert kq["cham_tran_chi_phi"] is False


def test_sheet_co_cot_sac_thai_chu_de_va_tab_thong_ke(moi_truong):
    ap, _, sheet, tab = moi_truong
    u = TT.format(7000001)
    ap.tra = lambda payload, limit: [_bl(u, "túi đẹp quá", 9), _bl(u, "giao chậm", 2),
                                     _bl(u, "giá bao nhiêu", 1), _bl(u, "@ban")]
    kq = json.loads(D._handle({"post_urls": [u]}))
    hd = sheet[0]
    assert hd[3:5] == ["Sắc thái", "Chủ đề"]
    nhan = {r[2]: (r[3], r[4]) for r in sheet[1:]}
    assert nhan["túi đẹp quá"] == ("Tích cực", "Sản phẩm/chất lượng")
    assert nhan["giao chậm"] == ("Tiêu cực", "Giao hàng/dịch vụ")
    assert nhan["giá bao nhiêu"] == ("Trung lập", "Giá/mua ở đâu/ý định mua")
    assert nhan["@ban"] == ("Trung lập", "Tag bạn bè")
    assert tab[0] == "Thống kê" and tab[1][0] == "s2"
    assert all(len(r) == 5 for r in tab[1][1]), "mọi dòng bảng thống kê cùng số cột"
    tk = kq["thong_ke"]
    assert tk["tong"] == 4 and tk["da_phan_loai"] == 4
    assert tk["sac_thai"]["Tích cực"] == {"so": 1, "ti_le": 25.0, "ti_le_theo_like": 75.0}
    assert tk["theo_bai"][u]["tong"] == 4 and tk["theo_nen_tang"]["tiktok"]["tong"] == 4
    assert kq["dong_thong_ke"].startswith("Đã phân loại 4/4 bình luận")
    assert kq["trich_dan"]["Tích cực"][0]["text"] == "túi đẹp quá"
    assert kq["thong_ke_ghi_o"] == "tab 'Thống kê'"


# ───────────────────────── phan_loai ─────────────────────────
class _AgentGia:
    tao = []

    def __init__(self, model="", provider=None, api_mode=None, base_url=None, api_key=None,
                 max_iterations=90, quiet_mode=False, enabled_toolsets=None,
                 disabled_toolsets=None, reasoning_config=None, skip_context_files=False,
                 skip_memory=False):
        _AgentGia.tao.append(dict(locals()))

    def run_conversation(self, nhac):
        return {"final_response": _AgentGia.tra(nhac)}


@pytest.fixture
def agent_gia(monkeypatch):
    _AgentGia.tao = []
    _AgentGia.tra = staticmethod(_model_gia)
    monkeypatch.setattr(P, "_lop_agent", lambda: _AgentGia)
    monkeypatch.setattr(P.tai_khoan_ai, "chon_runtime", lambda: (
        {"provider": "p", "api_mode": "m", "base_url": "b", "api_key": "k"}, "mo-hinh",
        {"tu": "may"}))
    return _AgentGia


def _dong(*texts):
    return [{"text": t, "likes": i} for i, t in enumerate(texts)]


def test_phan_loai_dung_tai_khoan_ai_cua_mark_va_doc_nhan(agent_gia):
    tt = {}
    ra = P.phan_loai_binh_luan(_dong("đẹp lắm", "ship chậm", "giá sao shop"), 30, tt)
    assert ra == [("Tích cực", "Sản phẩm/chất lượng"), ("Tiêu cực", "Giao hàng/dịch vụ"),
                  ("Trung lập", "Giá/mua ở đâu/ý định mua")]
    kw = agent_gia.tao[0]
    assert kw["model"] == "mo-hinh" and kw["max_iterations"] == 1 and kw["quiet_mode"]
    assert kw["enabled_toolsets"] == [] and kw["reasoning_config"]["effort"] == "low"
    assert kw["skip_context_files"] is True and kw["skip_memory"] is True
    assert tt["trang_thai"] == "đã chạy" and tt["da_phan_loai"] == 3


def test_agent_khong_ho_tro_reasoning_thi_khong_truyen(agent_gia, monkeypatch):
    class Cu:
        def __init__(self, model="", provider=None, api_mode=None, base_url=None,
                     api_key=None, max_iterations=90, quiet_mode=False,
                     enabled_toolsets=None, disabled_toolsets=None):
            pass

        def run_conversation(self, nhac):
            return {"final_response": '{"0":["+","ND"]}'}
    monkeypatch.setattr(P, "_lop_agent", lambda: Cu)
    assert P.phan_loai_binh_luan(_dong("idol xinh"), 30) == [("Tích cực", "KOL/nội dung")]


def test_json_hong_thi_chua_phan_loai_khong_doan(agent_gia):
    agent_gia.tra = staticmethod(lambda nhac: "xin lỗi, tôi không chắc")
    tt = {}
    ra = P.phan_loai_binh_luan(_dong("đẹp", "xấu"), 30, tt)
    assert ra == [(P.CHUA, P.CHUA)] * 2
    assert tt["trang_thai"] == "không gán được nhãn nào" and tt["lo_loi"] == 1


def test_nhan_sai_enum_thi_bo_dong_do(agent_gia):
    agent_gia.tra = staticmethod(lambda nhac: '{"0":["+","SP"],"1":["tốt","SP"],"7":["-","SP"]}')
    ra = P.phan_loai_binh_luan(_dong("a b", "c d"), 30)
    # Lô xếp theo like giảm dần: dòng 0 của lô là "c d" (1 like) — nhãn phải về đúng chỗ.
    assert ra == [(P.CHUA, P.CHUA), ("Tích cực", "Sản phẩm/chất lượng")]


def test_luat_khong_goi_model(monkeypatch):
    def cam(nhac):
        raise AssertionError("không được gọi model cho bình luận luật đã xử lý")
    monkeypatch.setattr(P, "_goi_model", cam)
    ra = P.phan_loai_binh_luan(_dong("", "@an @binh", "😍😍", "👎", "???"), 30)
    assert ra == [(P.CHUA, P.CHUA), ("Trung lập", "Tag bạn bè"),
                  ("Tích cực", "KOL/nội dung"), ("Tiêu cực", "KOL/nội dung"),
                  ("Trung lập", "Khác")]


def test_nhieu_like_duoc_gan_truoc(agent_gia, monkeypatch):
    monkeypatch.setattr(P, "_LO", 2)
    monkeypatch.setattr(P, "_SONG_SONG", 1)
    lo = []
    agent_gia.tra = staticmethod(lambda nhac: lo.append(nhac) or "{}")
    rows = [{"text": f"bl{i}", "likes": i} for i in range(5)]
    P.phan_loai_binh_luan(rows, 30)
    assert "bl4" in lo[0] and "bl3" in lo[0] and "bl0" in lo[-1]


def test_het_gio_khong_chan_va_bao_trung_thuc(agent_gia, monkeypatch):
    monkeypatch.setattr(P, "_TOI_THIEU_GIAY", 0)
    agent_gia.tra = staticmethod(lambda nhac: time.sleep(1.5) or "{}")
    tt = {}
    t0 = time.monotonic()
    ra = P.phan_loai_binh_luan(_dong("a b"), 0.3, tt)
    assert time.monotonic() - t0 < 1.2, "không được chờ lô treo"
    assert ra == [(P.CHUA, P.CHUA)] and tt["lo_het_gio"] == 1


def test_khong_du_thoi_gian_thi_bo_han_model(monkeypatch):
    monkeypatch.setattr(P, "_goi_model", lambda nhac: pytest.fail("không đủ giờ mà vẫn gọi"))
    tt = {}
    assert P.phan_loai_binh_luan(_dong("a b"), 5, tt) == [(P.CHUA, P.CHUA)]
    assert "không đủ thời gian" in tt["ghi_chu"]


def test_dem_ti_le_chinh_xac_tren_so_da_phan_loai():
    rows = ([{"sac_thai": "Tích cực", "chu_de": "Sản phẩm/chất lượng", "likes": 1}] * 7
            + [{"sac_thai": "Tiêu cực", "chu_de": "Giao hàng/dịch vụ", "likes": 1}] * 3
            + [{"sac_thai": "Trung lập", "chu_de": "Giá/mua ở đâu/ý định mua", "likes": 0}] * 2
            + [{"sac_thai": P.CHUA, "chu_de": P.CHUA, "likes": 50}] * 2)
    tk = P.dem(rows, "bai")
    assert (tk["tong"], tk["da_phan_loai"], tk["chua_phan_loai"]) == (14, 12, 2)
    assert [tk["sac_thai"][k]["ti_le"] for k in ("Tích cực", "Tiêu cực", "Trung lập")] == \
        [58.3, 25.0, 16.7]
    assert tk["sac_thai"]["Tích cực"]["ti_le_theo_like"] == 70.0, "7/10 like đã phân loại"
    assert tk["chu_de"]["Sản phẩm/chất lượng"] == {"so": 7, "ti_le": 58.3}
    assert P.dong_thong_ke(tk).startswith(
        "Đã phân loại 12/14 bình luận (2 chưa phân loại): Tích cực 7 (58,3%), "
        "Tiêu cực 3 (25,0%), Trung lập 2 (16,7%).")


# ───────────────────────── lời dặn ─────────────────────────
def test_loi_dan_he_thong_co_ba_luat_moi():
    import brain
    n = brain._TOOLING_NOTE
    assert "không lấp" in n and "403" in n, "nguồn hỏng thì nói rõ, không đoán bù"
    assert "hỏi LẠI cùng phạm vi" in n, "hỏi lại thì đối chiếu với lần trước"
    assert "`thong_ke`" in n and "gán nhãn từng" in n and "đừng nói không" in n
