"""Bình luận: ưu tiên bài chưa cào thiếu nhiều nhất, đọc tiếp video TikTok cào dở (18/10/2026).

Chủ dự án 18/10: "các luồng cào để tối ưu output nhất có thể" — bình luận là đầu vào sắc thái /
chủ đề. Đo kho production 17/10: TikTok chỉ có ~30% số bình luận nền tảng báo; 2 video 5.181 và
4.752 bình luận chưa cào dòng nào. Lý do: lô "cào hết" xếp theo cỡ TĂNG dần → bài to luôn chạy
cuối, hết tiền thì bị bỏ (`bl_lay_luc` NULL) và lượt sau chọn lại đúng nó rồi lại bỏ (lượt 5–6:
5 lô TikTok "bỏ qua (trần còn 0,00 USD)"). Mỗi lần cào lại một video dở cũng đọc lại từ trang đầu."""
from __future__ import annotations

import datetime
import inspect
import time

import pytest
from test_theo_doi import mo, nhan_gia  # noqa: F401

import apify_tool as A
import lang_nghe_db as K
import theo_doi as T
import tiktok_api as TT

VN = datetime.timezone(datetime.timedelta(hours=7))
LUC = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=VN)


def _bai(khoa, co, *, lay=None, da=None, khi_co=None, goc=0, p="tiktok"):
    return {"khoa": khoa, "nen_tang": p, "link": f"https://www.tiktok.com/@k/video/{abs(hash(khoa))}",
            "tai_khoan": "k", "tac_gia": "k", "binh_luan": co, "bl_lay_luc": lay, "bl_da_lay": da,
            "bl_lay_khi_co": khi_co, "nguon_loai": None, "bl_goc": goc}


#: Hai video THẬT chưa cào dòng nào (kho 17/10) + một video nhỏ + một video cào dở (40 gốc).
DS = [_bai("nho", 30), _bai("v5181", 5181), _bai("do", 150, lay=LUC, da=50, khi_co=150, goc=40),
      _bai("v4752", 4752)]


def test_lo_uu_tien_bai_chua_cao_thieu_nhieu_nhat(monkeypatch):
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 2.0, True))
    lo = T._chia_lo_bl("tiktok", list(DS), 0)
    # Trần console 2 USD → lô ≤ 0,9 × 2 / (0,0004 × 1,3) = 3.461 bình luận; video to một mình.
    assert [[b["khoa"] for b in x] for x, _ in lo] == [["v5181"], ["v4752"], ["nho", "do"]]
    # Trước 18/10 (cỡ tăng dần): [nho, do], [v4752], [v5181] — video to luôn đứng cuối.
    assert min(DS, key=T._uu_tien_bl)["khoa"] == "v5181"
    lo_co_dinh = T._chia_lo_bl("tiktok", list(DS), 20)              # bl_moi_bai > 0
    assert [b["khoa"] for b in lo_co_dinh[0][0]][:2] == ["v5181", "v4752"]


def test_doc_tiep_video_tiktok_cao_do():
    assert T._doc_tiep_tiktok(DS[2]) == 40                       # cào dở: 50 / 150 < 80%
    assert T._doc_tiep_tiktok(DS[1]) == 0                        # chưa cào: đọc từ đầu
    du = dict(DS[2], bl_da_lay=130)                              # 130 / 150 ≥ 80%: đã đủ
    assert T._doc_tiep_tiktok(du) == 0
    assert T._doc_tiep_tiktok(dict(DS[2], nen_tang="facebook")) == 0
    # Chỉ xin phần CÒN THIẾU: int((150 − 50) × 1,15) + 10 = 124 thay vì int(150 × 1,15) + 10 = 182.
    assert T._can_bl(DS[2], 0) == 124 and T._can_bl(DS[1], 0) == 5968


@pytest.mark.tiktok_api
def test_phan_tiktok_mang_vi_tri_doc_tiep(monkeypatch):
    from test_theo_doi import GiaViec
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 2.0, True))
    v = GiaViec({}, [])
    T._tao_cac_phan_bl(v, list(DS), {"tiktok": 0})
    cac = T._phan_bl(v)
    assert [len(ph["bai"]) for ph in cac] == [1, 1, 2]
    assert all(ph["bo_chuyen"] == "tiktok_binh_luan" for ph in cac)
    assert "bat_dau" not in cac[0] and cac[2]["bat_dau"] == {DS[2]["link"]: 40}
    # Ước tính theo giá thật 0,0004/bình luận: video 5.181 = 5.968 × 0,0004 × 1,3 = 3,10 USD
    # (giá cũ 0,00075 → 5,82 USD, lô luôn bị bỏ vì vượt phần còn).
    assert cac[0]["uoc_usd"] == pytest.approx(5968 * 0.0004 * 1.3, abs=1e-4)


def test_tiktok_api_doc_tiep_tu_vi_tri_goc(monkeypatch):
    from test_tiktok_api import NOW, GiaApi
    api = GiaApi(monkeypatch)
    u = "https://www.tiktok.com/@kenh_a/video/70000555"

    def c(i):
        return {"cid": f"c{i}", "text": f"bl {i}", "create_time": int(NOW.timestamp()),
                "digg_count": 0, "reply_comment_total": 0, "reply_id": "0",
                "user": {"unique_id": f"khach{i}", "uid": f"k{i}"}}
    api.bl[("70000555", 100)] = ([c(i) for i in range(100, 150)], 1)
    api.bl[("70000555", 150)] = ([c(i) for i in range(150, 160)], 0)
    ra = TT.binh_luan([u], 200, tra_loi=0, bat_dau={u: 100})
    assert [g["listComments_cursor"] for g in api.goi] == [100, 150]   # không đọc lại trang 0, 50
    assert len(ra) == 60
    api.goi.clear()
    TT.binh_luan([u], 200, tra_loi=0)                                  # không có vị trí: từ đầu
    assert api.goi[0]["listComments_cursor"] == 0


def _bl_api(cid, cha="0", n_tra_loi=0):
    from test_tiktok_api import NOW
    return {"cid": cid, "text": f"bl {cid}", "create_time": int(NOW.timestamp()), "digg_count": 0,
            "reply_comment_total": n_tra_loi, "reply_id": cha,
            "user": {"unique_id": f"khach_{cid}", "uid": f"u_{cid}"}}


def test_tiktok_api_bao_het_goc_va_trang_doc_tiep_rong(monkeypatch):
    """Soát 18/10/2026: `trang_thai` báo đã đọc tới trang gốc cuối chưa, và trang đọc tiếp đầu
    tiên có rỗng không — bên gọi biết lượt sau đọc tiếp hay lấy trả lời."""
    from test_tiktok_api import GiaApi
    api = GiaApi(monkeypatch)
    u = "https://www.tiktok.com/@kenh_a/video/70000666"
    api.bl[("70000666", 0)] = ([_bl_api(f"c{i}") for i in range(50)], 1)
    api.bl[("70000666", 50)] = ([_bl_api(f"c{i}") for i in range(50, 60)], 0)
    tt: dict = {}
    assert len(TT.binh_luan([u], 200, tra_loi=0, trang_thai=tt)) == 60
    assert tt[u] == {"het_goc": True, "rong": False}
    tt.clear()
    TT.binh_luan([u], 30, tra_loi=0, trang_thai=tt)                  # dừng vì đủ `per`
    assert tt[u] == {"het_goc": False, "rong": False}
    api.goi.clear()
    tt.clear()
    # Video bị cắt giữa phần trả lời: 60 gốc đã có → đọc tiếp từ 60 chỉ gặp trang rỗng.
    assert TT.binh_luan([u], 200, tra_loi=0, bat_dau={u: 60}, trang_thai=tt) == []
    assert tt[u] == {"het_goc": True, "rong": True} and len(api.goi) == 1


def test_tiktok_api_lay_tra_loi_cua_goc_trong_kho(monkeypatch):
    from test_tiktok_api import GiaApi
    api = GiaApi(monkeypatch)
    u = "https://www.tiktok.com/@kenh_a/video/70000667"
    api.tra_loi["g1"] = [_bl_api(f"r1{i}", "g1") for i in range(3)]
    api.tra_loi["g2"] = [_bl_api("r20", "0")]                        # API không ghi reply_id
    tt: dict = {}
    ra = TT.binh_luan([u], 100, tra_loi=100, tra_loi_cho={u: [["g1", 30], ["g2", 5]]},
                      trang_thai=tt)
    assert not any("listComments_awemeId" in g for g in api.goi), "không đọc lại trang gốc"
    assert [g["commentReplies_commentId"] for g in api.goi] == ["g1", "g2"]
    assert [r["repliesToId"] for r in ra] == ["g1", "g1", "g1", "g2"]
    # Soát 18/10/2026: sau nhánh trả lời, lượt sau đọc gốc TỪ ĐẦU (không ghi "het_goc" mãi).
    assert tt[u]["het_goc"] is False and tt[u]["tu_dau"] is True and not tt[u]["rong"]
    assert tt[u]["goc_can"] == []
    api.goi.clear()
    assert len(TT.binh_luan([u], 2, tra_loi=100, tra_loi_cho={u: [["g1", 30], ["g2", 5]]})) == 2
    assert len(api.goi) == 1, "đủ `per` thì dừng"


def test_tiktok_api_bao_goc_khong_them_duoc_tra_loi(monkeypatch):
    """Soát 18/10/2026 (MEDIUM): gốc TikTok báo 30 trả lời mà API chỉ trả 3 (27 bị ẩn / xoá) —
    kho đã có 3 thì hỏi lại không thêm được gì: báo trong "goc_can" để bên gọi bỏ qua gốc đó."""
    from test_tiktok_api import GiaApi
    api = GiaApi(monkeypatch)
    u = "https://www.tiktok.com/@kenh_a/video/70000668"
    api.tra_loi["g1"] = [_bl_api(f"r1{i}", "g1") for i in range(3)]       # kho có 3: không thêm
    api.tra_loi["g2"] = [_bl_api(f"r2{i}", "g2") for i in range(2)]       # kho có 1: thêm 1
    # g3: API không trả trả lời nào (kho có 2) — cũng không thêm được.
    tt: dict = {}
    ra = TT.binh_luan([u], 100, tra_loi=100, trang_thai=tt,
                      tra_loi_cho={u: [["g1", 30, 3], ["g2", 5, 1], ["g3", 4, 2]]})
    assert [g["commentReplies_commentId"] for g in api.goi] == ["g1", "g2", "g3"]
    assert len(ra) == 5 and tt[u]["goc_can"] == ["g1", "g3"]
    # Gốc chưa kịp hỏi (đủ `per`) thì không bị coi là "không thêm được".
    tt.clear()
    TT.binh_luan([u], 2, tra_loi=100, trang_thai=tt,
                 tra_loi_cho={u: [["g2", 5, 0], ["g1", 30, 3]]})
    assert tt[u]["goc_can"] == []


def test_doc_tiep_chi_khi_dung_giua_trang_goc(monkeypatch):
    """Đã đọc hết gốc (`bl_het_goc`): KHÔNG đọc tiếp từ vị trí gốc; có gốc thiếu trả lời trong
    kho thì phần mang `tra_loi_cho`, không thì đọc lại từ đầu. Đều chỉ xin phần còn thiếu."""
    from test_theo_doi import GiaViec
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 2.0, True))
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    het = dict(DS[2], khoa="het", link="https://www.tiktok.com/@k/video/70000901")
    het2 = dict(DS[2], khoa="het2", link="https://www.tiktok.com/@k/video/70000902")
    T.ghi_moc_tk("hapas", {T.KHOA_BL_TIKTOK: {"het": {"het_goc": True}, "het2": {"het_goc": True},
                                               "do": {"het_goc": False}}})
    hoi: list = []

    def goc_thieu(ma, ks, tran, toi_da=200, bo=()):
        hoi.append((ma, sorted(ks), tran, list(bo)))
        return {"het": [("g1", 30, 2), ("g2", 5, 0)]}
    monkeypatch.setattr(K, "goc_thieu_tra_loi", goc_thieu)
    ds = [dict(DS[2]), het, het2, dict(DS[1])]
    T._gan_doc_tiep_bl("hapas", ds)
    assert hoi == [("hapas", ["het", "het2"], 50, [])]
    assert [b.get("bl_het_goc") for b in ds] == [False, True, True, None]
    assert ds[1]["bl_goc_thieu"] == [["g1", 30, 2], ["g2", 5, 0]] and "bl_goc_thieu" not in ds[2]
    assert [T._doc_tiep_tiktok(b) for b in ds] == [40, 0, 0, 0]
    assert T._can_bl(ds[1], 0) == T._can_bl(ds[2], 0) == T._can_bl(ds[0], 0) == 124
    v = GiaViec({}, [])
    T._tao_cac_phan_bl(v, ds, {"tiktok": 0})
    ph = next(x for x in T._phan_bl(v) if any(b["khoa"] == "het" for b in x["bai"]))
    assert ph["tra_loi_cho"] == {het["link"]: [["g1", 30, 2], ["g2", 5, 0]]}
    assert het["link"] not in (ph.get("bat_dau") or {}) and het2["link"] not in (
        ph.get("bat_dau") or {})
    assert any("lấy trả lời của 2 gốc còn thiếu" in c for c in T._cau_uu_tien_bl(ds))


@pytest.mark.tiktok_api
def test_video_cat_giua_tra_loi_khong_bi_bo(mo, nhan_gia, monkeypatch):  # noqa: F811
    """Soát 18/10/2026 (MEDIUM): video bị cắt giữa phần trả lời (gốc đủ, tổng dưới 80%). Bản cũ:
    mỗi lượt đọc tiếp một trang rỗng, 0 bình luận mới, sau 2 lần `bl_lan_thieu` = 2 → bỏ hẳn.
    Nay: lượt 1 gặp trang rỗng → không tính là một lần thiếu, sổ ghi đã hết gốc; lượt 2 lấy trả
    lời của các gốc còn thiếu trong kho."""
    from test_theo_doi import DU_AN, GiaKhoBl, GiaViec, _lay_bl
    from test_tiktok_api import GiaApi
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    api = GiaApi(monkeypatch)
    u = "https://www.tiktok.com/@hapas.official/video/70000777"
    b = dict(_bai("tiktok:70000777", 300, lay=LUC, da=100, khi_co=300, goc=60), link=u)
    kho = GiaKhoBl(monkeypatch, [b])
    du_an = dict(DU_AN, bl_bat=True, bl_so_bai=10, bl_moi_bai=0)
    _lay_bl(GiaViec({}, []), du_an, 8, 5.0, time.monotonic() + 300)
    assert [g.get("listComments_cursor") for g in api.goi] == [60]
    assert kho.khong_tinh == {b["khoa"]}, "trang đọc tiếp rỗng: không tính một lần thiếu"
    assert T.doc_moc_tk("hapas")[T.KHOA_BL_TIKTOK][b["khoa"]]["het_goc"] is True
    monkeypatch.setattr(K, "goc_thieu_tra_loi", lambda ma, ks, tran, toi_da=200, bo=(): {
        b["khoa"]: [("g1", 30, 0), ("g2", 5, 0)]})
    api.goi.clear()
    api.tra_loi["g1"] = [_bl_api(f"r1{i}", "g1") for i in range(3)]
    api.tra_loi["g2"] = [_bl_api("r20", "g2")]
    _lay_bl(GiaViec({}, []), du_an, 9, 5.0, time.monotonic() + 300)
    assert not any("listComments_awemeId" in g for g in api.goi)
    rows = kho.ghi[-1][2]
    assert {r["ma_cha"] for r in rows} == {"g1", "g2"} and all(r["la_tra_loi"] for r in rows)
    assert kho.khong_tinh == set()
    so = T.doc_moc_tk("hapas")[T.KHOA_BL_TIKTOK][b["khoa"]]
    assert so["het_goc"] is False and so["tu_dau"] is True, "lượt sau đọc gốc từ đầu"


@pytest.mark.tiktok_api
def test_goc_lech_so_khong_lam_video_ket_o_nhanh_tra_loi(mo, nhan_gia, monkeypatch):  # noqa: F811
    """Soát 18/10/2026 (MEDIUM): gốc g1 TikTok báo 30 trả lời mà API chỉ trả 3 (ẩn / xoá) — kho
    không bao giờ đủ, và nhánh trả lời không đọc trang gốc nên số báo không đổi. Bản cũ: sổ ghi
    "het_goc" mãi → video cào dở đi nhánh trả lời mọi lượt (tới 0,40 USD/video/lượt), bình luận
    gốc mới bị sót. Nay: lượt trả lời → lượt sau đọc gốc TỪ ĐẦU; g1 (không thêm được gì) bị bỏ khỏi
    gốc thiếu `BL_GOC_CAN_NGAY` ngày, quá hạn thì hỏi lại."""
    from test_theo_doi import DU_AN, GiaKhoBl, GiaViec, _lay_bl
    from test_tiktok_api import GiaApi
    monkeypatch.setattr(TT, "dung_api", lambda viec: True)
    api = GiaApi(monkeypatch)
    u = "https://www.tiktok.com/@hapas.official/video/70000778"
    b = dict(_bai("tiktok:70000778", 300, lay=LUC, da=100, khi_co=300, goc=60), link=u)
    GiaKhoBl(monkeypatch, [b])
    du_an = dict(DU_AN, bl_bat=True, bl_so_bai=10, bl_moi_bai=0)
    T.ghi_moc_tk("hapas", {T.KHOA_BL_TIKTOK: {b["khoa"]: {"het_goc": True}}})
    # Kho giả: g1 có 3 / 30 trả lời (API chỉ trả 3), g2 có 1 / 5.
    hoi: list = []

    def goc_thieu(ma, ks, tran, toi_da=200, bo=()):
        hoi.append(list(bo))
        return {b["khoa"]: [x for x in [("g1", 30, 3), ("g2", 5, 1)]
                            if f"{b['khoa']}\x1f{x[0]}" not in bo]}
    monkeypatch.setattr(K, "goc_thieu_tra_loi", goc_thieu)
    api.tra_loi["g1"] = [_bl_api(f"r1{i}", "g1") for i in range(3)]
    api.tra_loi["g2"] = [_bl_api(f"r2{i}", "g2") for i in range(3)]

    # Lượt 1: nhánh trả lời — g1 không thêm được gì → sổ ghi "goc_can"; lượt sau đọc từ đầu.
    _lay_bl(GiaViec({}, []), du_an, 9, 5.0, time.monotonic() + 300)
    assert [g.get("commentReplies_commentId") for g in api.goi] == ["g1", "g2"]
    so = T.doc_moc_tk("hapas")[T.KHOA_BL_TIKTOK][b["khoa"]]
    assert so["het_goc"] is False and so["tu_dau"] is True and list(so["goc_can"]) == ["g1"]

    # Lượt 2: quay lại đọc trang gốc TỪ ĐẦU (vị trí 0, không phải 60) — gốc mới n1 + số trả lời
    # mới của gốc; không hỏi kho gốc thiếu.
    api.goi.clear()
    api.bl[("70000778", 0)] = ([_bl_api("g1", n_tra_loi=30), _bl_api("n1")], 0)
    _lay_bl(GiaViec({}, []), du_an, 10, 5.0, time.monotonic() + 300)
    assert api.goi[0].get("listComments_cursor") == 0 and len(hoi) == 1
    so = T.doc_moc_tk("hapas")[T.KHOA_BL_TIKTOK][b["khoa"]]
    assert so["het_goc"] is True and "tu_dau" not in so and list(so["goc_can"]) == ["g1"]

    # Lượt 3: lại nhánh trả lời, nhưng g1 nằm trong sổ → chỉ hỏi g2.
    api.goi.clear()
    _lay_bl(GiaViec({}, []), du_an, 11, 5.0, time.monotonic() + 300)
    assert hoi[-1] == [f"{b['khoa']}\x1fg1"]
    assert [g.get("commentReplies_commentId") for g in api.goi] == ["g2"]

    # Quá `BL_GOC_CAN_NGAY` ngày: g1 hết bị bỏ qua (có thể đã có trả lời mới).
    ds = [dict(b)]
    T.ghi_moc_tk("hapas", {T.KHOA_BL_TIKTOK: {b["khoa"]: dict(so, het_goc=True)}})
    T._gan_doc_tiep_bl("hapas", ds, datetime.datetime.now(VN) + datetime.timedelta(
        days=T.BL_GOC_CAN_NGAY + 1))
    assert hoi[-1] == [] and [x[0] for x in ds[0]["bl_goc_thieu"]] == ["g1", "g2"]


def test_ghi_binh_luan_khong_tinh_thieu_va_sql_goc_thieu(monkeypatch):
    import contextlib

    from test_lang_nghe_loc_lai import GiaCur
    c = GiaCur(rows=[{"khoa_bai": "tiktok:1", "ma": "g1", "tra_loi": 30, "da_co": 2},
                     {"khoa_bai": "tiktok:1", "ma": "g2", "tra_loi": 5, "da_co": 0}])

    @contextlib.contextmanager
    def ket_noi():
        yield c
    monkeypatch.setattr(K, "ket_noi", ket_noi)
    assert K.goc_thieu_tra_loi("hapas", ["tiktok:1"], 50, bo=["tiktok:1\x1fg9"]) == {
        "tiktok:1": [("g1", 30, 2), ("g2", 5, 0)]}
    q, ts = c.sql[-1]
    assert "NOT g.la_tra_loi" in q and "HAVING count(r.ma) < LEAST(g.tra_loi, %(tran)s)" in q
    # Soát 18/10/2026: bỏ gốc không thêm được trả lời; cắt 200 gốc mỗi bài ngay trong SQL.
    assert "NOT ((g.khoa_bai || chr(31) || g.ma) = ANY(%(bo)s))" in q
    assert "row_number() OVER (PARTITION BY g.khoa_bai" in q and "WHERE thu_tu <= %(toi_da)s" in q
    assert ts == {"ma": "hapas", "khoa": ["tiktok:1"], "tran": 50, "bo": ["tiktok:1\x1fg9"],
                  "toi_da": 200}
    assert K.goc_thieu_tra_loi("hapas", [], 50) == {}
    c.sql.clear()
    K.ghi_binh_luan("hapas", 7, [], {"tiktok:1": (0, 300), "tiktok:2": (0, 40)},
                    khong_tinh_thieu={"tiktok:1"})
    cap = [(q, ts) for q, ts in c.sql if q.startswith("UPDATE bai SET bl_lay_luc")]
    assert "WHEN %s THEN bai.bl_lan_thieu" in cap[0][0]
    assert [ts[3] for _, ts in cap] == [True, False]


def test_tran_lo_giu_cho_cac_lo_sau():
    # Phần còn của việc 1 USD, lô to ước 4 USD: các lô sau ước 0,8 → giữ tối đa 0,5 cho chúng.
    assert T._tran_lo_bl(2.0, 5.0, 1.0, 0.8, 4.0) == 0.5
    assert T._tran_lo_bl(2.0, 5.0, 1.0, 0.2, 4.0) == 0.8
    assert T._tran_lo_bl(2.0, 5.0, 1.0, 0.0, 4.0) == 1.0              # lô cuối: dùng hết
    assert T._tran_lo_bl(2.0, 5.0, 1.0, 0.0, 0.01) == 0.1             # sàn 0,1 của Apify
    assert T._tran_lo_bl(0.66, 5.0, 1.0, 0.0, 4.0) == 0.66            # trần console nền tảng
    # Soát 18/10/2026: tháng còn 0,5 < việc 1,0 — phần giữ tính trên min(tháng, việc) = 0,5:
    # lô đầu 0,5 − min(0,8; 0,25) = 0,25 (bản cũ: 1,0 − 0,5 = 0,5 = cả phần còn của tháng).
    assert T._tran_lo_bl(2.0, 0.5, 1.0, 0.8, 4.0) == 0.25
    assert T._tran_lo_bl(2.0, 0.5, 1.0, 0.0, 4.0) == 0.5               # lô cuối: dùng hết


def test_cau_pheu_uu_tien_va_doc_tiep():
    c = T._cau_uu_tien_bl(list(DS))
    assert c[0] == "bình luận: ưu tiên 3 bài chưa cào thiếu nhiều nhất (TikTok 5.181, TikTok " \
                   "4.752, TikTok 30)"
    assert c[1] == "bình luận TikTok: đọc tiếp 1 video cào dở, bỏ 40 bình luận gốc đã có"
    assert T._cau_uu_tien_bl([]) == []


def test_sql_chon_bai_dem_binh_luan_goc_da_co():
    sql = inspect.getsource(K.bai_can_lay_binh_luan)
    assert "AS bl_goc" in sql and "NOT c.la_tra_loi" in sql
