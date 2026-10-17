"""Chốt chi phí THẬT khi phí sự kiện Apify ghi trễ (17/10/2026).

Đo thật: `usageTotalUsd` đọc ngay khi run xong còn thiếu — 0,1948 → 0,2397; 0,0201 → 0,0501;
danek 0,0001 → 0,0251 — phải đọc lại sau vài chục giây mới ra số cuối, trong khi vòng "hai lần
đọc khớp nhau" cách 3 giây của bản cũ đã dừng. Đồng hồ GIẢ: ngủ là dời đồng hồ, Apify giả trả
số thiếu tới khi run đã xong đủ lâu."""
from __future__ import annotations

import datetime
import json
import time

import pytest
from test_viec_nen import _quet, nen  # noqa: F401

import apify_tool as A
import lang_nghe_db as K
import theo_doi as T
import viec_nen as V

GOC = 1_792_200_000.0                   # 17/10/2026 (epoch giây)


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


@pytest.fixture
def dong_ho(monkeypatch):
    """Đồng hồ giả chung cho `viec_nen` (`_bay_gio`, `_ngu`) và `apify_tool` (`_giay_tu`,
    `time.sleep`)."""
    t = {"giay": 0.0, "ngu": []}

    def ngu(s):
        t["ngu"].append(s)
        t["giay"] += s
    monkeypatch.setattr(V, "_bay_gio", lambda: GOC + t["giay"])
    monkeypatch.setattr(V, "_ngu", ngu)
    monkeypatch.setattr(A.time, "sleep", ngu)
    monkeypatch.setattr(A, "_giay_tu", lambda moc: None if moc is None else round(
        GOC + t["giay"] - moc.timestamp(), 1))
    return t


# ───────────────────────────── apify_tool ─────────────────────────────
class _R:
    def __init__(self, data, code=200):
        self.status_code, self._d = code, data

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


def test_chi_phi_cac_run_bao_gio_xong_muon_nhat(monkeypatch, dong_ho):
    runs = {"r1": {"status": "SUCCEEDED", "usageTotalUsd": 0.1, "finishedAt": _iso(GOC - 30)},
            "r2": {"status": "SUCCEEDED", "usageTotalUsd": 0.0948, "finishedAt": _iso(GOC - 5)},
            "r3": {"status": "RUNNING", "usageTotalUsd": 0.01, "finishedAt": None}}
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A.requests, "get", lambda url, **k: _R({"data": runs[url.rsplit("/", 1)[1]]}))
    kq = A._chi_phi_cac_run(["r1", "r2", "r3"])
    assert kq["usd"] == 0.2048 and kq["con_song"] == ["r3"]
    assert kq["giay_tu_ket_thuc"] == 5.0 and kq["ket_thuc_cuoi"].startswith("2026-10-")


def _lich_su(monkeypatch, dong_ho, xong_truoc: float, thieu: float, du: float, sau: float = 30):
    """Lịch sử run của actor: run "r1" đã xong `xong_truoc` giây trước GOC; `usageTotalUsd` =
    `thieu` tới khi run đã xong `sau` giây, rồi `du`."""
    doc = []

    def get(url, **kw):
        g = GOC + dong_ho["giay"] - (GOC - xong_truoc)
        doc.append(g)
        return _R({"data": {"items": [{"id": "r1", "startedAt": _iso(GOC - 200),
                                       "status": "SUCCEEDED", "finishedAt": _iso(GOC - xong_truoc),
                                       "usageTotalUsd": du if g >= sau else thieu}]}})
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A, "_tran", lambda: (500, 5.0))
    monkeypatch.setattr(A.requests, "get", get)
    return doc


TU = datetime.datetime.fromtimestamp(GOC - 300, A._VN_TZ)


def test_chi_phi_thuc_run_vua_xong_la_so_tam_va_hen_doc_lai(monkeypatch, dong_ho):
    """Bản cũ: 0,0201 hai lần liền khớp nhau → báo "số thực", sổ ghi thiếu 0,03 USD. Lượt tại
    chỗ KHÔNG đứng chờ thêm (trả lời chat ~135 giây): báo số tạm + hẹn đọc lại đúng run đó."""
    _lich_su(monkeypatch, dong_ho, xong_truoc=2, thieu=0.0201, du=0.0501)
    thuc = A._chi_phi_thuc(["danek~facebook-search-ppr"], TU)
    assert thuc["usd"] == 0.02 and thuc["on_dinh"] is False
    assert thuc["doc_lai"] == {"run_ids": ["r1"], "sau_giay": pytest.approx(
        A._CP_DOC_LAI_GIAY - 2 - A._CP_NGHI)}
    assert sum(dong_ho["ngu"]) <= A._CP_LAN_TOI_DA * A._CP_NGHI, "không chờ chặn thêm"
    assert "_giay" not in thuc and "_ids" not in thuc
    assert "phí sự kiện" in A._dong_chi_phi(thuc, 0.05)


def test_chi_phi_thuc_run_xong_lau_roi_la_so_cuoi(monkeypatch, dong_ho):
    _lich_su(monkeypatch, dong_ho, xong_truoc=120, thieu=0.2397, du=0.2397)
    thuc = A._chi_phi_thuc(["x~y"], TU)
    assert thuc["usd"] == 0.24 and thuc["on_dinh"] is True and "doc_lai" not in thuc
    assert dong_ho["ngu"] == [A._CP_NGHI], "chỉ một lần đọc xác nhận như cũ"
    assert "phí sự kiện" not in A._dong_chi_phi(thuc, 0.2)


def test_so_chi_phi_doc_lai_ghi_phan_chenh(monkeypatch, tmp_path):
    import chi_phi_tool as C
    monkeypatch.setattr(C, "_SO", tmp_path / "so.jsonl")
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {"usd": 0.0501, "so_run": len(ids),
                                                             "chua_doc": 0, "con_song": []})
    ngu = []
    rec = C.ghi(queries=["hapas"], platforms=["facebook"], date_range="7 ngày",
                thuc={"usd": 0.02, "so_run": 1, "cham_tran": 0, "dang_chay": 0, "on_dinh": False,
                      "doc_lai": {"run_ids": ["r1"], "sau_giay": 85.0}}, est=0.05)
    assert len((tmp_path / "so.jsonl").read_text(encoding="utf-8").splitlines()) == 1, \
        "bộ thử (SOCIAL_NEN_TU_CHAY=0) không dựng luồng đọc lại"
    assert C.doc_lai(rec, {"run_ids": ["r1"], "sau_giay": 85.0}, ngu=ngu.append) == 0.0301
    dong = [json.loads(x) for x in (tmp_path / "so.jsonl").read_text(encoding="utf-8").splitlines()]
    assert ngu == [85.0] and dong[-1]["chi_phi_thuc_usd"] == 0.0301
    assert dong[-1]["tu_khoa"][0].startswith("điều chỉnh") and dong[-1]["uoc_tinh_usd"] == 0
    assert dong[0]["doc_lai"]["run_ids"] == ["r1"] and dong[-1]["dieu_chinh_cho"] == dong[0]["id"]
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {"usd": 0.0201, "so_run": 1,
                                                             "chua_doc": 0, "con_song": []})
    assert C.doc_lai(rec, {"run_ids": ["r1"], "sau_giay": 0}, ngu=ngu.append) == 0.0, \
        "không cao hơn thì không ghi"


def test_so_chi_phi_khoi_dong_lai_lam_bu_doc_lai(monkeypatch, tmp_path):
    """Soát 17/10/2026: luồng đọc lại của lượt TẠI CHỖ chỉ sống trong RAM — Mark khởi động lại
    trong 90 giây là mất phần chênh. Nay hẹn nằm trên đĩa; `bu_doc_lai` (run.py) làm bù."""
    import chi_phi_tool as C
    monkeypatch.setattr(C, "_SO", tmp_path / "so.jsonl")
    thuc = {"usd": 0.02, "so_run": 1, "cham_tran": 0, "dang_chay": 0,
            "doc_lai": {"run_ids": ["r1"], "sau_giay": 85.0}}
    rec = C.ghi(queries=["hapas"], platforms=["facebook"], date_range="7 ngày", thuc=thuc,
                est=0.05)
    C.ghi(queries=["khac"], platforms=["tiktok"], date_range="", thuc={"usd": 0.1, "so_run": 1},
          est=0.1)                                              # không hẹn đọc lại
    # Bot tắt trước khi luồng đọc lại chạy: lần khởi động sau tìm thấy đúng bản ghi đó.
    cac = C.bu_doc_lai()
    assert [r["id"] for r in cac] == [rec["id"]] and cac[0]["doc_lai"]["luc"] == round(
        rec["ts"] + 85.0, 1)
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {"usd": 0.0, "so_run": 0,
                                                             "chua_doc": 1, "con_song": []})
    assert C._lam_bu(cac, ngu=lambda s: None) == 0.0
    assert len(C.bu_doc_lai()) == 1, "GET hỏng: không đánh dấu, lần sau thử lại"
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {"usd": 0.0501, "so_run": 1,
                                                             "chua_doc": 0, "con_song": []})
    assert C._lam_bu(C.bu_doc_lai(), ngu=lambda s: None) == 0.0301
    assert C.bu_doc_lai() == [], "làm bù một lần"
    # Không chênh: một dòng dấu "đã đọc lại", không dòng tiền nào.
    rec2 = C.ghi(queries=["x"], platforms=["facebook"], date_range="", thuc=thuc, est=0.0)
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {"usd": 0.02, "so_run": 1,
                                                             "chua_doc": 0, "con_song": []})
    assert C._lam_bu(C.bu_doc_lai(), ngu=lambda s: None) == 0.0 and C.bu_doc_lai() == []
    dong = [json.loads(x) for x in (tmp_path / "so.jsonl").read_text(encoding="utf-8").splitlines()]
    assert dong[-1] == {"loai": "da_doc_lai", "cho": rec2["id"], "ts": dong[-1]["ts"]}
    assert all("loai" not in r for r in C.doc_so("", 50)), "dòng dấu không thành lần quét"
    # Hẹn quá cũ (> 2 ngày): không làm bù.
    C.ghi(queries=["cu"], platforms=["facebook"], date_range="", thuc=thuc, est=0.0)
    assert C.bu_doc_lai(bay_gio=time.time() + C.DOC_LAI_TRONG_GIAY + 60) == []


# ───────────────────────────── viec_nen ─────────────────────────────
def _viec_co_run(nen, dong_ho, xong_truoc=3.0, thieu=0.0201, du=0.0501, sau=40.0):  # noqa: F811
    kq = _quet()
    v = V.Viec(V.doc(kq["ma_viec"]))
    rid = nen.tao_run("x~y", {}, [1] * 3, "SUCCEEDED")
    nen.runs[rid]["finishedAt"] = _iso(GOC - xong_truoc)

    def doc_run(r):
        g = GOC + dong_ho["giay"] - (GOC - xong_truoc)
        nen.runs[r]["usageTotalUsd"] = du if g >= sau else thieu
    nen.khi_get_run = doc_run
    v.d["nen_tang"]["tiktok"]["phan"][1]["run_id"] = rid
    return v, rid


def test_chot_chi_phi_cho_toi_khi_run_xong_du_lau(nen, dong_ho):  # noqa: F811
    v, _ = _viec_co_run(nen, dong_ho)
    cp = v.chot_chi_phi(["hapas"], ["tiktok"], "")
    assert cp["usd"] == 0.0501 and cp["on_dinh"] is True, cp
    assert nen.so_chi_phi[-1]["thuc"]["usd"] == 0.0501, "sổ chi phí ghi số cuối"
    assert sum(dong_ho["ngu"]) <= V.TRAN_CHO_PHI_GIAY, "chờ có trần"
    assert cp["can_tinh_lai"] is True and cp["chot_ts"] == GOC + dong_ho["giay"]


def test_chot_chi_phi_het_tran_thi_chot_tam_roi_chot_lai_nang_luot(nen, dong_ho, monkeypatch):  # noqa: F811
    """Phí ghi 60 giây sau khi run xong (muộn hơn mốc 45 giây của lần chốt): lượt đóng với số
    tạm, bước nền đọc lại ở 90 giây thấy cao hơn → một dòng điều chỉnh + NÂNG
    luot_quet.chi_phi_usd của lượt theo dõi."""
    nang = []
    monkeypatch.setattr(K, "nang_chi_phi_luot", lambda luot, usd: nang.append((luot, usd)) or 0.02)
    monkeypatch.setattr(T, "_bao_dashboard", lambda ma, luot: None)
    v, _ = _viec_co_run(nen, dong_ho, sau=60)
    v.d.update(loai="theo_doi", luot_id=17, tham_so={"du_an": "hapas"})
    cp = v.chot_chi_phi(["theo dõi hapas"], ["tiktok"], "")
    assert cp["usd"] == 0.0201, "số tạm: đọc lúc run đã xong 45 giây"
    assert sum(dong_ho["ngu"]) <= V.TRAN_CHO_PHI_GIAY + 1e-9
    lech = v.tinh_lai_muon()
    assert lech == 0.03 and nang == [(17, 0.0501)]
    assert nen.so_chi_phi[-1]["thuc"]["usd"] == 0.03 and "điều chỉnh" in nen.so_chi_phi[-1]["queries"][0]
    assert v.d["chi_phi"]["da_tinh_lai"] is True and v.d["chi_phi"]["usd_sau"] == 0.0501
    assert v.tinh_lai_muon() == 0.0 and len(nang) == 1, "chỉ chốt lại MỘT lần"


def test_chot_lai_cho_du_90_giay_sau_run_cuoi(nen, dong_ho):  # noqa: F811
    v, _ = _viec_co_run(nen, dong_ho, xong_truoc=60)
    v.chot_chi_phi(["hapas"], ["tiktok"], "")
    da = dong_ho["giay"]
    v.tinh_lai_muon()
    assert dong_ho["ngu"][-1] == pytest.approx(V.CHO_LAI_GIAY - (60 + da)), "chờ tới 90 giây"
    cp = {"ket_thuc_cuoi": None, "chot_ts": GOC + dong_ho["giay"] - 10}
    assert v._con_cho_lai(cp) == pytest.approx(V.CHO_LAI_GIAY - 10)
    assert v._con_cho_lai({"ket_thuc_cuoi": _iso(GOC + dong_ho["giay"] + 9999)}) == \
        V.TRAN_CHO_LAI_GIAY, "trần chờ"


def test_kho_hong_khi_nang_luot_thi_thu_lai_khong_ghi_so_hai_lan(nen, dong_ho, monkeypatch):  # noqa: F811
    lan = []

    def hong(luot, usd):
        lan.append(usd)
        raise K.LoiKho("không nối được kho lắng nghe (OperationalError)")
    monkeypatch.setattr(K, "nang_chi_phi_luot", hong)
    v, _ = _viec_co_run(nen, dong_ho, sau=60)
    v.d.update(loai="theo_doi", luot_id=17, tham_so={"du_an": "hapas"})
    v.chot_chi_phi(["theo dõi hapas"], ["tiktok"], "")
    assert v.tinh_lai_muon() == 0.03 and v.d["chi_phi"]["da_tinh_lai"] is False
    so = len(nen.so_chi_phi)
    assert v.tinh_lai_muon() == 0.0 and len(nen.so_chi_phi) == so, "phần chênh đã ghi sổ"
    v.tinh_lai_muon()
    assert len(lan) == V.TINH_LAI_TOI_DA_LAN and v.d["chi_phi"]["da_tinh_lai"] is True


def test_chot_lai_khi_get_run_hong_thi_chua_xong(nen, dong_ho, monkeypatch):  # noqa: F811
    """Soát 17/10/2026: GET run hỏng lúc chốt lại (mất mạng, APIFY_TOKEN vừa đổi) thì tổng THIẾU —
    không được đánh dấu đã chốt lại (luot_quet sẽ thiếu vĩnh viễn)."""
    monkeypatch.setattr(K, "nang_chi_phi_luot", lambda luot, usd: None)
    v, _ = _viec_co_run(nen, dong_ho, sau=60)
    v.d.update(loai="theo_doi", luot_id=17, tham_so={"du_an": "hapas"})
    v.chot_chi_phi(["theo dõi hapas"], ["tiktok"], "")
    goc = A._chi_phi_cac_run
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {**goc(ids), "usd": 0.0, "so_run": 0,
                                                             "chua_doc": len(ids)})
    assert v.tinh_lai_muon() == 0.0 and v.d["chi_phi"]["da_tinh_lai"] is False
    assert V._con_hen(v.d), "còn hẹn: luồng nền / lần khởi động sau thử lại"
    monkeypatch.setattr(A, "_chi_phi_cac_run", goc)
    assert v.tinh_lai_muon() == 0.03 and v.d["chi_phi"]["da_tinh_lai"] is True


def test_viec_xong_tu_tien_trinh_truoc_van_gui_lai_va_chot_lai(nen, dong_ho, monkeypatch):  # noqa: F811
    """Soát 17/10/2026 (lỗi có từ trước): việc xong mà chưa gửi được kết quả, bot khởi động lại —
    sổ mang số thế hệ CŨ nên `gui` ném MatQuyen: kết quả không bao giờ tới, bước chốt lại chi
    phí cũng mất."""
    nang = []
    monkeypatch.setattr(K, "nang_chi_phi_luot", lambda luot, usd: nang.append((luot, usd)) or 0.02)
    monkeypatch.setattr(T, "_bao_dashboard", lambda ma, luot: None)
    v, _ = _viec_co_run(nen, dong_ho, sau=60)
    v.d.update(loai="theo_doi", luot_id=31, tham_so={"du_an": "hapas"})
    v.chot_chi_phi(["theo dõi hapas"], ["tiktok"], "")
    assert V._lay_quyen()
    cu = V.the_cua_toi()
    v.d.update(trang_thai="xong", xong_ts=V._bay_gio(), the=cu,
               thong_bao={"ket_qua": "Theo dõi HAPAS xong", "lan_thu": 0, "da_gui": False})
    V.luu(dict(v.d))
    monkeypatch.setattr(V, "_QUYEN", {})                 # tiến trình mới: nhận khoá, thế hệ mới
    assert V._lay_quyen() and V.the_cua_toi() > cu
    d = V.chay_ngay(v.ma)
    assert d["thong_bao"]["da_gui"] is True and d["the"] == V.the_cua_toi()
    assert nang == [(31, 0.0501)] and V.doc(v.ma)["chi_phi"]["da_tinh_lai"] is True


def test_doc_lai_cho_tron_90_giay_khi_con_run_dang_chay(monkeypatch, dong_ho):
    items = [{"id": "r1", "startedAt": _iso(GOC - 300), "status": "SUCCEEDED",
              "finishedAt": _iso(GOC - 200), "usageTotalUsd": 0.1},
             {"id": "r2", "startedAt": _iso(GOC - 100), "status": "RUNNING", "finishedAt": None,
              "usageTotalUsd": 0.05}]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A, "_tran", lambda: (500, 5.0))
    monkeypatch.setattr(A.requests, "get", lambda url, **k: _R({"data": {"items": items}}))
    thuc = A._chi_phi_thuc(["x~y"], TU)
    assert thuc["dang_chay"] == 1 and thuc["doc_lai"] == {"run_ids": ["r1", "r2"],
                                                          "sau_giay": A._CP_DOC_LAI_GIAY}


def test_khoi_dong_lai_lam_bu_buoc_chot_lai(nen, dong_ho, monkeypatch):  # noqa: F811
    """Bot tắt sau khi lượt đã đóng (số tạm) mà trước bước chốt lại: lần khởi động sau làm bù từ
    run id trong sổ việc."""
    nang = []
    monkeypatch.setattr(K, "nang_chi_phi_luot", lambda luot, usd: nang.append((luot, usd)) or 0.02)
    monkeypatch.setattr(T, "_bao_dashboard", lambda ma, luot: None)
    v, _ = _viec_co_run(nen, dong_ho, sau=60)
    v.d.update(loai="theo_doi", luot_id=21, tham_so={"du_an": "hapas"})
    v.chot_chi_phi(["theo dõi hapas"], ["tiktok"], "")
    v.d.update(trang_thai="xong", xong_ts=V._bay_gio(), the=1)         # thế hệ của tiến trình cũ
    V.luu(dict(v.d))
    assert V._lay_quyen(ep=True)
    nhan = [d for d in V.tat_ca() if d.get("agent_id") == V.agent_id()]
    cac = V._viec_tinh_lai(nhan, set())
    assert [x.ma for x in cac] == [v.ma] and cac[0].d["the"] == V.the_cua_toi()
    V._tinh_lai_nen(cac)                                 # SOCIAL_NEN_TU_CHAY=0: chạy tại chỗ
    assert nang == [(21, 0.0501)] and V.doc(v.ma)["chi_phi"]["da_tinh_lai"] is True
    assert V._viec_tinh_lai([V.doc(v.ma)], set()) == [], "làm bù một lần"
    cu = dict(V.doc(v.ma), xong_ts=V._bay_gio() - V.TINH_LAI_TRONG_GIAY - 1)
    cu["chi_phi"] = {**cu["chi_phi"], "da_tinh_lai": False}
    assert not V._can_tinh_lai(cu), "việc quá cũ không làm bù"


# ───────────────────────────── kho + theo_doi ─────────────────────────────
class _Cur:
    def __init__(self, dong):
        self.dong, self.cau = dong, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, ts=()):
        self.cau.append((sql, ts))
        self._kq = self.dong if sql.startswith("SELECT") else None
        return self

    def fetchone(self):
        return self._kq


def test_nang_chi_phi_luot_chi_nang_khong_ha(monkeypatch):
    c = _Cur({"usd": 0.1948, "ghi_chu": "phễu TikTok: về 120"})
    monkeypatch.setattr(K, "ket_noi", lambda: c)
    assert K.nang_chi_phi_luot(9, 0.23974) == 0.1948
    sql, ts = c.cau[-1]
    assert sql.startswith("UPDATE luot_quet SET chi_phi_usd = %s") and ts[0] == 0.2397
    assert ts[1].startswith("chi phí chốt lại 0,1948 → 0,2397 USD") and ts[1].endswith(
        "; phễu TikTok: về 120"), "câu chốt lại đứng ĐẦU ghi chú (đuôi dài bị cắt)"
    c = _Cur({"usd": 0.2397, "ghi_chu": None})
    monkeypatch.setattr(K, "ket_noi", lambda: c)
    assert K.nang_chi_phi_luot(9, 0.2) is None and len(c.cau) == 1, "không bao giờ hạ"
    assert K.nang_chi_phi_luot(9, 0.2397) is None


def test_chot_lai_chi_phi_cua_theo_doi(monkeypatch):
    bao = []
    monkeypatch.setattr(T, "_bao_dashboard", lambda ma, luot: bao.append((ma, luot)))
    monkeypatch.setattr(K, "nang_chi_phi_luot", lambda luot, usd: 0.0201)
    assert T.chot_lai_chi_phi({"luot_id": 5, "tham_so": {"du_an": "hapas"}}, 0.0501)
    assert bao == [("hapas", 5)]
    assert T.chot_lai_chi_phi({}, 1.0), "việc chưa mở lượt: không có gì để nâng"

    def hong(luot, usd):
        raise K.LoiKho("kho lắng nghe báo lỗi (OperationalError: 08006)")
    monkeypatch.setattr(K, "nang_chi_phi_luot", hong)
    assert T.chot_lai_chi_phi({"luot_id": 5}, 0.0501) is False


def test_viec_khong_phai_theo_doi_khong_dung_kho():
    v = V.Viec({"ma": "q1", "loai": "social_listen", "luot_id": 3})
    assert v._sau_tinh_lai(1.0) is True


def test_mo_ta_cot_chi_phi_van_dung():
    """Trần tháng cộng `luot_quet.chi_phi_usd`: mô tả cột vẫn là tiền THẬT của các run."""
    from pathlib import Path
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    assert "COMMENT ON COLUMN luot_quet.chi_phi_usd IS 'Chi phí Apify THẬT" in sql
    assert json.dumps(V.CHO_LAI_GIAY) == "90.0" and V.CHO_PHI_GIAY >= 45
