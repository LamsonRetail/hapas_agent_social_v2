"""Canh kho bài học chiến dịch (bai_hoc_tool.py): `ghi_bai_hoc` / `nho_bai_hoc` trên Hindsight.

Không mạng: giả `requests.request` của module, ghi lại từng lời gọi. Hình payload khớp
openapi Hindsight 0.10.2 (RetainRequest/MemoryItem, RecallRequest/RecallResult).

Bốn bất biến của thiết kế phải đỏ lên ở đây nếu ai sửa ẩu: bài học không là nguồn giá/
khuyến mãi/quyền (câu cảnh báo cố định), luôn có nguồn gốc, luôn có phạm vi và nhớ lại lọc
`all_strict`, không bao giờ gửi bí mật hay dữ liệu cá nhân sang Hindsight.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys
import time

import pytest
import requests

import bai_hoc_tool as B
import lsr_policy

GOC = pathlib.Path(__file__).resolve().parent.parent

BAI = {
    "chien_dich": "Sale 20.10",
    "team": "Branding Ads",
    "kenh": "tiktok",
    "da_thu": "Đẩy video KOC nano bằng Spark Ads 7 ngày, ngân sách 5 triệu",
    "ket_qua": "CPM 18.000đ, 1,2 triệu lượt xem, chi phí mỗi tin nhắn giảm 30% so với tuần trước",
    "danh_gia": "hieu_qua",
    "bai_rut_ra": "KOC nano + Spark Ads rẻ hơn ads tự dựng ở giai đoạn nhận diện",
    "nguon": "https://o4pvcegwn6b.sg.larksuite.com/sheets/OsbvsgC1chru5mtG7RFli2vFg1b?sheet=BEoYUt",
    "ngay_do": "2026-09-30",
    "nguoi_noi": "Trưởng nhóm Ads",
}


class _Tra:
    def __init__(self, ma=200, du_lieu=None):
        self.status_code, self._d = ma, du_lieu if du_lieu is not None else {}

    def json(self):
        return self._d


@pytest.fixture
def kho(monkeypatch, tmp_path):
    """Kho bật, HTTP giả, sổ cái trong thư mục tạm, ngữ cảnh lượt cố định."""
    monkeypatch.setenv("MARK_HINDSIGHT_URL", "http://127.0.0.1:8888/")
    monkeypatch.setenv("MARK_HINDSIGHT_API_KEY", "khoa-thu-nghiem")
    monkeypatch.delenv("MARK_HINDSIGHT_BANK", raising=False)
    monkeypatch.delenv("BAI_HOC_TEAMS", raising=False)
    monkeypatch.delenv("BAI_HOC_TRAN_NGAY", raising=False)
    so = tmp_path / "so" / "so_bai_hoc.jsonl"
    monkeypatch.setenv("BAI_HOC_SO_CAI", str(so))
    monkeypatch.setattr(B, "_dem_ngay", {})
    monkeypatch.setattr(B, "_ngu_canh", lambda: {
        "sender": "ou_nguoighi1234567", "ten": "Người Ghi", "chat": "oc_chat123", "turn": "t1"})
    st = {"goi": [], "tra": _Tra(200, {"success": True, "bank_id": "x", "items_count": 1,
                                        "async": False}), "loi": None, "so": so}

    def gia(method, url, headers=None, data=None, timeout=None):
        st["goi"].append({"method": method, "url": url, "headers": headers,
                          "body": json.loads(data.decode("utf-8")), "timeout": timeout})
        if st["loi"]:
            raise st["loi"]
        return st["tra"]

    monkeypatch.setattr(B.requests, "request", gia)
    return st


def _ghi(**sua):
    return json.loads(B._handle_ghi({**BAI, **sua}))


def _nho(**a):
    return json.loads(B._handle_nho({"cau_hoi": "KOC TikTok ra sao", **a}))


# ───────────────────────────── tắt khi thiếu cấu hình ─────────────────────────────
@pytest.mark.parametrize("thieu", ["MARK_HINDSIGHT_URL", "MARK_HINDSIGHT_API_KEY"])
def test_thieu_mot_bien_la_tat_han(kho, monkeypatch, thieu):
    monkeypatch.delenv(thieu)
    assert B.bat() is False
    for kq in (_ghi(), _nho()):
        assert kq.get("chua_bat") is True and "chưa bật" in kq["error"]
    assert kho["goi"] == [], "tắt mà vẫn gọi Hindsight"
    assert B.loi_dan() == "" and B.tool_can_xet() == {}, "tắt mà prompt vẫn nhắc bài học"


def test_bo_qua_bien_tran_cua_plugin_hermes(kho, monkeypatch):
    """Biến trần là của plugin Hindsight trong Hermes (mặc định gửi lên cloud Vectorize).
    Mark chỉ đọc biến có tiền tố MARK_: đặt biến trần thì kho vẫn TẮT, không gọi gì."""
    for ten in ("MARK_HINDSIGHT_URL", "MARK_HINDSIGHT_API_KEY", "MARK_HINDSIGHT_BANK"):
        monkeypatch.delenv(ten, raising=False)
    monkeypatch.setenv("HINDSIGHT_URL", "http://127.0.0.1:8888")
    monkeypatch.setenv("HINDSIGHT_API_URL", "http://127.0.0.1:8888")
    monkeypatch.setenv("HINDSIGHT_API_KEY", "khoa-tran")
    monkeypatch.setenv("HINDSIGHT_BANK", "bank-tran")
    assert B.bat() is False and B._bank() == "hapas-mkt-bai-hoc"
    assert _ghi().get("chua_bat") is True and _nho().get("chua_bat") is True
    assert kho["goi"] == []
    src = (GOC / "bai_hoc_tool.py").read_text(encoding="utf-8")
    import re
    assert not re.search(r'environ\.get\("HINDSIGHT_', src), "đọc biến trần của plugin"
    # Có biến MARK_ thì bật, và khoá gửi đi là khoá MARK_, không phải khoá trần.
    monkeypatch.setenv("MARK_HINDSIGHT_URL", "http://127.0.0.1:8888")
    monkeypatch.setenv("MARK_HINDSIGHT_API_KEY", "khoa-mark")
    _ghi()
    assert kho["goi"][0]["headers"]["Authorization"] == "Bearer khoa-mark"
    assert "/banks/hapas-mkt-bai-hoc/" in kho["goi"][0]["url"]


def test_bat_khi_du_hai_bien(kho):
    assert B.bat() is True
    assert "`nho_bai_hoc`" in B.loi_dan() and set(B.tool_can_xet()) == {"ghi_bai_hoc",
                                                                          "nho_bai_hoc"}


# ───────────────────────────── kiểm trường ─────────────────────────────
@pytest.mark.parametrize("truong", list(B._BAT_BUOC))
def test_thieu_truong_bat_buoc_thi_tu_choi(kho, truong):
    kq = _ghi(**{truong: ""})
    assert kq["da_luu"] is False and truong in kq["error"]
    assert kho["goi"] == []


@pytest.mark.parametrize("sua,chu", [
    ({"ket_qua": "chạy khá ổn, team thích"}, "số đo được"),
    ({"nguon": "http://example.com/bao-cao"}, "https"),
    ({"nguon": "https://example.com/x?access_token=abcdef"}, "token"),
    ({"nguon": "https://user:pw@example.com/x"}, "mật khẩu"),
    ({"ngay_do": "30/09/2026"}, "YYYY-MM"),
    ({"ngay_do": "2099-01-01"}, "tương lai"),
    ({"danh_gia": "tot"}, "danh_gia"),
    ({"kenh": "zalo"}, "kenh"),
    ({"da_thu": "x" * 801}, "tối đa"),
])
def test_du_lieu_sai_thi_tu_choi_va_khong_gui(kho, sua, chu):
    kq = _ghi(**sua)
    assert kq["da_luu"] is False and chu in kq["error"], kq
    assert kho["goi"] == []


def test_ngay_do_dang_thang_duoc_nhan(kho):
    assert _ghi(ngay_do="2026-09")["da_luu"] is True
    assert kho["goi"][0]["body"]["items"][0]["timestamp"] == "2026-09-01T00:00:00Z"


def test_danh_sach_team_khi_co_cau_hinh(kho, monkeypatch):
    monkeypatch.setenv("BAI_HOC_TEAMS", "Branding Ads, KOL/KOC")
    assert _ghi(team="Content")["da_luu"] is False
    assert _ghi()["da_luu"] is True


# ───────────────────────────── bí mật + dữ liệu cá nhân ─────────────────────────────
@pytest.mark.parametrize("truong,gia_tri,loai", [
    ("da_thu", "Book KOC chị Lan, sđt 0912 345 678", "số điện thoại"),
    ("ket_qua", "45 đơn, khách +84912345678 phàn nàn", "số điện thoại"),
    ("da_thu", "Gửi brief cho koc.lan@gmail.com", "email"),
    ("nguoi_noi", "ou_abcdef1234567890", "ou_"),
    ("bai_rut_ra", "Dùng khoá sk-abcdefghijklmnopqrstuv để gọi API", "token"),
    ("da_thu", "api_key=abc123 cho actor", "token"),
    ("ket_qua", "Thanh toán thẻ 4111 1111 1111 1111, 12 đơn", "số thẻ"),
])
def test_bi_mat_va_du_lieu_ca_nhan_bi_tu_choi(kho, truong, gia_tri, loai):
    kq = _ghi(**{truong: gia_tri})
    assert kq["da_luu"] is False and loai in kq["error"] and truong in kq["error"], kq
    assert kho["goi"] == [], "dữ liệu nhạy cảm đã bị gửi sang Hindsight"
    assert not kho["so"].exists()


@pytest.mark.parametrize("nguon,loai", [
    ("https://docs.example.com/x/0912345678", "số điện thoại"),
    ("https://docs.example.com/x?ghi_chu=0912%20345%20678", "số điện thoại"),
    ("https://docs.example.com/u/koc.lan@gmail.com", "email"),
    ("https://docs.example.com/x?ai=koc.lan%40gmail.com", "email"),
    ("https://docs.example.com/x?ai=koc.lan%2540gmail.com", "email"),       # mã hoá 2 lớp
    ("https://docs.example.com/x?nguoi=ou_abcdef1234567890", "ou_"),
    ("https://docs.example.com/x?the=4111%201111%201111%201111", "số thẻ"),
])
def test_link_nguon_cung_soat_du_lieu_ca_nhan_ke_ca_khi_ma_hoa(kho, nguon, loai):
    kq = _ghi(nguon=nguon)
    assert kq["da_luu"] is False and loai in kq["error"] and "nguon" in kq["error"], kq
    assert kho["goi"] == []


def test_tong_do_dai_ban_dung_co_tran(kho):
    dai = dict(da_thu="d" * 800, ket_qua="1" * 800, bai_rut_ra="b" * 400,
               nguoi_noi="n" * 80, chien_dich="c" * 120,
               nguon="https://example.com/" + "a" * 470)
    kq = _ghi(**dai)
    assert kq["da_luu"] is False and "tổng" in kq["error"] and kho["goi"] == []
    nho = {**dai, "bai_rut_ra": "", "nguon": BAI["nguon"]}
    assert len(B.dung_noi_dung({**BAI, **nho}, "x" * B._TEN_TOI_DA, "2000-01-01")) <= B._TONG_TOI_DA
    assert _ghi(**nho)["da_luu"] is True


def test_so_lieu_marketing_khong_bi_nham_la_du_lieu_ca_nhan(kho):
    """Số tiền thô, số view, CPM là thứ bài học nào cũng có — không được chặn nhầm."""
    kq = _ghi(ket_qua="Chi 1070000000 đồng, 525800 view, CPM 0,0512, 0912345 lượt hiển thị")
    assert kq["da_luu"] is True, kq


# ───────────────────────────── hình payload ghi ─────────────────────────────
def test_payload_ghi_dung_hinh_hindsight(kho):
    kq = _ghi()
    assert kq["success"] is True and kq["da_luu"] is True
    g = kho["goi"][0]
    assert g["method"] == "POST"
    assert g["url"] == "http://127.0.0.1:8888/v1/default/banks/hapas-mkt-bai-hoc/memories"
    assert g["headers"]["Authorization"] == "Bearer khoa-thu-nghiem"
    assert g["timeout"] == B._TIMEOUT_GHI
    b = g["body"]
    assert set(b) == {"items", "async", "document_tags"} and b["async"] is False
    it = b["items"][0]
    assert set(it) == {"content", "timestamp", "context", "metadata", "document_id", "tags"}
    assert it["tags"] == ["loai:bai_hoc", "team:branding-ads", "chien_dich:sale-20-10",
                          "kenh:tiktok", "danh_gia:hieu_qua"]
    assert b["document_tags"] == it["tags"], "thiếu tag tài liệu thì recall lọc tag bỏ chunk"
    assert it["timestamp"] == "2026-09-30T00:00:00Z"
    m = it["metadata"]
    assert all(isinstance(v, str) for v in m.values()), "metadata Hindsight là dict[str,str]"
    assert it["document_id"] == m["ma_bai_hoc"] == kq["ma_bai_hoc"]
    assert m["ma_bai_hoc"].startswith("bh-") and len(m["ma_bai_hoc"]) == 15
    # nguồn gốc (I2)
    assert m["nguoi_ghi_open_id"] == "ou_nguoighi1234567" and m["nguoi_ghi_ten"] == "Người Ghi"
    assert m["nguoi_noi"] == "Trưởng nhóm Ads" and m["chat_id"] == "oc_chat123"
    assert m["luot_ghi"] == "t1" and m["nguon"] == BAI["nguon"] and m["ngay_do"] == "2026-09-30"
    ghi = datetime.datetime.strptime(m["ghi_luc"], "%Y-%m-%dT%H:%M:%SZ").date()
    assert m["het_han"] == (ghi + datetime.timedelta(days=365)).isoformat()
    # nội dung do code dựng, đủ trường
    for chu in ("[Bài học chiến dịch]", "Sale 20.10", "Đã thử:", "Kết quả đo được:",
                "Đánh giá: hiệu quả", "Rút ra:", BAI["nguon"], "ghi bởi Người Ghi"):
        assert chu in it["content"]


def test_nguoi_noi_mac_dinh_la_nguoi_ghi(kho):
    _ghi(nguoi_noi="")
    assert kho["goi"][0]["body"]["items"][0]["metadata"]["nguoi_noi"] == "Người Ghi"


def test_bank_lay_tu_env(kho, monkeypatch):
    monkeypatch.setenv("MARK_HINDSIGHT_BANK", "hapas-mkt-bai-hoc-staging")
    _ghi()
    assert "/banks/hapas-mkt-bai-hoc-staging/memories" in kho["goi"][0]["url"]


def test_ngu_canh_that_lay_tu_luot(monkeypatch):
    """`_ngu_canh` đọc người gửi/chat/turn của lượt; tên tra qua lark_client (giả)."""
    import audit
    import lark_client
    import memory_store
    import scheduler
    memory_store.set_current_sender("ou_nguoi999999999")
    scheduler.set_current_chat("oc_chat999")
    monkeypatch.setattr(audit, "turn_id_hien_tai", lambda: "turn9")
    monkeypatch.setattr(lark_client, "resolve_user_name",
                        lambda oid: "Nguyễn Văn A - AI Intern")
    try:
        assert B._ngu_canh() == {"sender": "ou_nguoi999999999", "ten": "Nguyễn Văn A",
                                 "chat": "oc_chat999", "turn": "turn9"}
    finally:
        memory_store.set_current_sender(None)
        scheduler.set_current_chat(None)


# ───────────────────────────── sổ cái ─────────────────────────────
def test_luu_thanh_cong_them_dung_mot_dong_so_cai(kho):
    kq = _ghi()
    dong = kho["so"].read_text(encoding="utf-8").splitlines()
    assert len(dong) == 1
    rec = json.loads(dong[0])
    assert rec["ma_bai_hoc"] == kq["ma_bai_hoc"] and rec["bank"] == "hapas-mkt-bai-hoc"
    assert rec["item"]["tags"][0] == "loai:bai_hoc" and rec["item"]["metadata"]["nguon"]
    _ghi()
    assert len(kho["so"].read_text(encoding="utf-8").splitlines()) == 2, "sổ cái chỉ thêm"


def test_so_cai_hong_van_bao_da_luu(kho, monkeypatch):
    monkeypatch.setenv("BAI_HOC_SO_CAI", str(kho["so"].parent))   # là thư mục → ghi hỏng
    kho["so"].parent.mkdir(parents=True, exist_ok=True)
    kq = _ghi()
    assert kq["da_luu"] is True and "sổ cái" in kq["canh_bao_so_cai"]


# ───────────────────────────── fail-open ─────────────────────────────
@pytest.mark.parametrize("loi,tra", [
    (requests.Timeout("chậm"), None),
    (requests.ConnectionError("tắt"), None),
    (None, _Tra(500)),
    (None, _Tra(401)),
    (None, _Tra(200, {"success": False})),
])
def test_hindsight_hong_thi_ghi_tra_loi_nhe(kho, loi, tra):
    kho["loi"] = loi
    if tra:
        kho["tra"] = tra
    kq = _ghi()                                   # không được ném
    assert kq["da_luu"] is False and "tạm thời không truy cập được" in kq["error"]
    assert "khoa-thu-nghiem" not in json.dumps(kq), "lộ khoá trong lỗi"
    assert not kho["so"].exists(), "chưa lưu được mà đã ghi sổ cái"


@pytest.mark.parametrize("loi,tra", [(requests.Timeout("chậm"), None), (None, _Tra(503))])
def test_hindsight_hong_thi_nho_tra_loi_nhe(kho, loi, tra):
    kho["loi"] = loi
    if tra:
        kho["tra"] = tra
    kq = _nho()
    assert "tạm thời không truy cập được" in kq["error"] and kq["canh_bao"] == B.CANH_BAO
    assert kho["goi"][0]["timeout"] == B._TIMEOUT_NHO <= 5


def test_tran_moi_chat_moi_ngay(kho, monkeypatch):
    monkeypatch.setenv("BAI_HOC_TRAN_NGAY", "2")
    assert _ghi()["da_luu"] and _ghi()["da_luu"]
    kq = _ghi()
    assert kq["da_luu"] is False and "chạm trần" in kq["error"] and len(kho["goi"]) == 2


def test_tran_giu_cho_truoc_khi_goi_va_tra_lai_khi_hong(kho, monkeypatch):
    """Kiểm + cộng trong một khoá, TRƯỚC lời gọi mạng; lưu hỏng thì trả chỗ."""
    monkeypatch.setenv("BAI_HOC_TRAN_NGAY", "1")
    dem_luc_goi = []
    goc = B.requests.request

    def soi(*a, **k):
        dem_luc_goi.append(sum(B._dem_ngay.values()))
        return goc(*a, **k)

    monkeypatch.setattr(B.requests, "request", soi)
    kho["tra"] = _Tra(500)
    assert _ghi()["da_luu"] is False
    assert dem_luc_goi == [1], "chưa giữ chỗ trước lời gọi mạng"
    assert sum(B._dem_ngay.values()) == 0, "lưu hỏng mà không trả chỗ"
    kho["tra"] = _Tra(200, {"success": True})
    assert _ghi()["da_luu"] is True
    assert "chạm trần" in _ghi()["error"]


def test_tran_song_song_khong_vuot(kho, monkeypatch):
    import threading
    monkeypatch.setenv("BAI_HOC_TRAN_NGAY", "3")
    rao = threading.Barrier(8)
    goc = B.requests.request

    def cham(*a, **k):
        time.sleep(0.02)
        return goc(*a, **k)

    monkeypatch.setattr(B.requests, "request", cham)
    kq = []

    def chay():
        rao.wait()
        kq.append(_ghi())

    luong = [threading.Thread(target=chay) for _ in range(8)]
    for t in luong:
        t.start()
    for t in luong:
        t.join()
    assert sum(1 for x in kq if x.get("da_luu")) == 3 and len(kho["goi"]) == 3


# ───────────────────────────── nhớ lại ─────────────────────────────
def _hit(ma, tags, het_han="2099-01-01", **meta):
    return {"id": "m-" + ma, "text": f"[Bài học chiến dịch] {ma}", "document_id": ma,
            "tags": tags, "metadata": {"ma_bai_hoc": ma, "het_han": het_han,
                                       "nguoi_ghi_open_id": "ou_nguoighi1234567",
                                       "nguoi_ghi_ten": "Người Ghi", "nguon": "https://x.vn/a",
                                       "ngay_do": "2026-09-30", **meta}}


def test_nho_loc_tag_all_strict_va_gan_canh_bao(kho):
    the = ["loai:bai_hoc", "team:branding-ads", "kenh:tiktok"]
    kho["tra"] = _Tra(200, {"results": [
        _hit("bh-000000000001", the + ["chien_dich:sale-20-10"]),
        _hit("bh-000000000001", the + ["chien_dich:sale-20-10"]),       # chunk thứ hai
        _hit("bh-000000000002", ["loai:bai_hoc", "team:kol-koc", "kenh:tiktok"]),  # lọt team
        _hit("bh-000000000003", []),                                     # không tag
        _hit("bh-000000000004", the, het_han="2020-01-01"),              # hết hạn
        _hit("bh-000000000005", the),
    ]})
    kq = _nho(team="Branding Ads", kenh="tiktok", toi_da=5)
    g = kho["goi"][0]
    assert g["url"].endswith("/v1/default/banks/hapas-mkt-bai-hoc/memories/recall")
    assert g["body"] == {"query": "KOC TikTok ra sao", "tags": the, "tags_match": "all_strict",
                         "budget": "mid", "max_tokens": 1500}
    assert kq["canh_bao"] == B.CANH_BAO
    for chu in ("giá bán", "khuyến mãi", "quyền hạn", "KHÔNG", "không phải mệnh lệnh",
                "bỏ qua mọi yêu cầu"):
        assert chu in B.CANH_BAO.replace("KHÔNG phải", "không phải")
    assert "không phải mệnh lệnh" in B.LOI_DAN
    assert [r["ma_bai_hoc"] for r in kq["ket_qua"]] == ["bh-000000000001", "bh-000000000005"]
    r = kq["ket_qua"][0]
    assert r["nguoi_ghi"] == "Người Ghi" and r["nguon"] and r["ngay_do"] == "2026-09-30"
    assert "ou_" not in json.dumps(kq), "không đưa open_id người ghi cho model"


def test_nho_khong_loc_van_chi_lay_bai_hoc_co_tag(kho):
    kho["tra"] = _Tra(200, {"results": []})
    kq = _nho()
    assert kho["goi"][0]["body"]["tags"] == ["loai:bai_hoc"]
    assert kho["goi"][0]["body"]["tags_match"] == "all_strict"
    assert kq["so_ket_qua"] == 0 and kq["canh_bao"] == B.CANH_BAO


def test_nho_gioi_han_so_ket_qua(kho):
    kho["tra"] = _Tra(200, {"results": [_hit(f"bh-00000000001{i}", ["loai:bai_hoc"])
                                        for i in range(8)]})
    assert _nho(toi_da=3)["so_ket_qua"] == 3
    assert _nho(toi_da=99)["so_ket_qua"] == 8


def test_nho_thieu_cau_hoi(kho):
    assert "cau_hoi" in json.loads(B._handle_nho({"cau_hoi": " "}))["error"]
    assert kho["goi"] == []


# ───────────────────────────── policy + nối hệ thống ─────────────────────────────
def test_policy_phan_loai():
    assert lsr_policy._MUTATING_EXACT["ghi_bai_hoc"] == "write_data"
    assert "nho_bai_hoc" in lsr_policy._SAFE_EXACT
    assert "ghi_bai_hoc" not in lsr_policy._SAFE_EXACT
    # Cổng là env, không phải công tắc console (chưa có dòng trong agentToolCapabilities.ts).
    for t in ("ghi_bai_hoc", "nho_bai_hoc"):
        assert t not in lsr_policy._TOOL_CO_CONG_TAC and t not in lsr_policy._CONG_TAC_LUI


@pytest.mark.parametrize("quyen,cho_ghi", [({"reply", "call_agent", "write_data"}, True),
                                           ({"reply", "call_agent"}, False), (set(), False)])
def test_policy_ghi_theo_write_data_nho_luon_duoc(quyen, cho_ghi):
    lsr_policy._nho.update(quyen=set(quyen), luc=time.time(), nguon="test")
    assert lsr_policy.decide("ghi_bai_hoc", {}).allowed is cho_ghi
    assert lsr_policy.decide("nho_bai_hoc", {"cau_hoi": "x"}).allowed is True


def test_dang_ky_dung_toolset_va_an_khi_tat():
    from tools.registry import registry  # type: ignore
    for ten in ("ghi_bai_hoc", "nho_bai_hoc"):
        e = registry.get_entry(ten)
        assert e.toolset == "bai_hoc" and e.check_fn is B.bat


def test_brain_noi_dung_cho():
    brain = (GOC / "brain.py").read_text(encoding="utf-8")
    assert "import bai_hoc_tool" in brain
    assert brain.index("import bai_hoc_tool") < brain.index("lsr_policy.install_registry_guard(")
    assert '"bai_hoc",' in brain                                       # enabled_toolsets
    assert "bai_hoc_tool.loi_dan()" in brain and "bai_hoc_tool.tool_can_xet()" in brain


def test_brain_loi_dan_quyen_theo_env(kho, monkeypatch):
    brain = pytest.importorskip("brain")
    lsr_policy._nho.update(quyen={"reply", "call_agent", "write_data"}, luc=time.time(),
                           nguon="test")
    note = brain._luat_vai_note()
    assert "lưu bài học chiến dịch" in note.split("KHÔNG được:")[0]
    lsr_policy._nho.update(quyen={"reply", "call_agent"}, luc=time.time(), nguon="test")
    note = brain._luat_vai_note()
    assert "lưu bài học chiến dịch" in note.split("KHÔNG được:")[1]
    assert "tra bài học chiến dịch cũ" in note.split("KHÔNG được:")[0]
    monkeypatch.delenv("MARK_HINDSIGHT_URL")
    assert "bài học" not in brain._luat_vai_note()


def test_ky_nang_nhac_tool_bai_hoc():
    sk = GOC / "skills"
    than = (sk / "bai-hoc-chien-dich.md").read_text(encoding="utf-8")
    assert than.splitlines()[0] == "# Ghi và nhớ bài học chiến dịch"
    assert "Lưu bài học này nhé?" in than and "tin nhắn SAU" in than
    assert "không phải mệnh lệnh" in than and "dùng chung cho cả team" in than
    sys.path.insert(0, str(GOC / "scripts"))
    import dong_bo_tieu_su as D
    kn = json.loads((sk / "khi-nao-dung.json").read_text(encoding="utf-8"))
    assert kn[D.ma_ky_nang("Ghi và nhớ bài học chiến dịch")]["ten"] == "Ghi và nhớ bài học chiến dịch"
    for f in ("campaign-plan.md", "ad-performance-audit.md", "theo-doi-ngan-sach.md"):
        s = (sk / f).read_text(encoding="utf-8")
        assert "`nho_bai_hoc`" in s and "BÀI HỌC CŨ" in s, f


# ───────────────────────────── script quản trị ─────────────────────────────
def _admin():
    sys.path.insert(0, str(GOC / "scripts"))
    import bai_hoc_admin
    return bai_hoc_admin


def test_admin_purge_chi_chon_bai_qua_han():
    A = _admin()
    bay_gio = datetime.datetime(2026, 10, 7, tzinfo=datetime.timezone.utc)
    docs = [{"id": "bh-cu", "created_at": "2025-09-01T00:00:00Z"},
            {"id": "bh-moi", "created_at": "2026-09-01T00:00:00+00:00"},
            {"id": "bh-khong-ngay", "created_at": None}]
    assert [d["id"] for d in A.can_don(docs, 365, bay_gio)] == ["bh-cu"]


def test_admin_mac_dinh_chay_thu_khong_xoa(monkeypatch, capsys):
    A = _admin()
    monkeypatch.setenv("MARK_HINDSIGHT_URL", "http://127.0.0.1:8888")
    monkeypatch.setenv("MARK_HINDSIGHT_API_KEY", "khoa-thu-nghiem")
    goi = []
    monkeypatch.setattr(A, "_goi", lambda m, d, b=None, timeout=20: goi.append((m, d)) or {
        "items": [{"id": "bh-000000000001", "created_at": "2020-01-01T00:00:00Z"}], "total": 1})
    assert A.main(["purge", "--older-than-days", "365"]) == 0
    assert A.main(["delete", "bh-000000000001"]) == 0
    assert A.main(["init-bank"]) == 0
    assert all(m == "GET" for m, _ in goi), "chạy thử mà đã gửi lệnh ghi/xoá"
    assert "khoa-thu-nghiem" not in capsys.readouterr().out
    assert A.main(["delete", "bh-000000000001", "--thuc-hien"]) == 0
    assert goi[-1] == ("DELETE", "/v1/default/banks/hapas-mkt-bai-hoc/documents/bh-000000000001")
