"""Canh hai tool ghi việc ĐÃ DUYỆT vào Base checklist (viec_base_tool.py).

Đây là chỗ đầu tiên Mark GHI lên Base chung của team, nên bộ thử canh các bất biến code
(không phải lời dặn): Base đích chỉ từ cấu hình, người duyệt = người nhờ trong đúng chat,
chạy lại không tạo trùng, không tạo lựa chọn select mới, không đè ô người đã điền, chỉ
gọi 4 endpoint Bitable. Lark giả hoàn toàn (`lark_client.call`), không mạng.

Cột và lựa chọn giả dưới đây chép đúng cấu trúc Base CHECKLIST DA 20.10 đọc ngày
06/10/2026 (NHÓM có lựa chọn trùng và khoảng trắng cuối; TRẠNG THÁI "ĐANG LÀM " có dấu
cách) — đổi sang dạng v1 của OpenAPI (`field_name`, `type` số, `property.options`).
"""
from __future__ import annotations

import copy
import json
import re

import pytest

import lark_client
import lsr_policy
import viec_base_tool as V

APP = "SBfNb16GDaDVS5s8rpol8EjQgSg"
BANG = "tbluIfPgSyOVIAg2"
NGUOI, CHAT = "ou_nguoi_nho", "oc_chat_hop"

_NHOM = ["KẾ HOẠCH", "MEDIA", "BOOKING", "CONTENT", "STORE - HỘP NHẠC", "COLLAB", "SBD", "OOH",
         "EVENT", "VM ", "COLLAB", "CELEB", "", "TVC ", "CELEB ", "KẾ HOẠCH ", "ITVC", "BOOKING",
         "CELEB", "CONTENT", "COLLAB", "EVENT ", "STORE - HỘP NHẠC", "VM", "SBD", "MEDIA "]
_TT = ["CẦN LÀM", "ĐANG LÀM ", "CHỜ DUYỆT ", "ĐÃ XONG", "CANCEL"]


def _cot(ten, kieu, ma, lua_chon=None):
    f = {"field_name": ten, "type": kieu, "field_id": ma}
    if lua_chon is not None:
        f["property"] = {"options": [{"name": o, "id": f"opt{i}"} for i, o in enumerate(lua_chon)]}
    return f


COT = [
    _cot("HẠNG MỤC CV", 1, "fldG8OveXb"), _cot("KẾT QUẢ CẦN ĐẠT", 1, "fldOBsrFk2"),
    _cot("NHÓM", 3, "fld5fs2BxR", _NHOM), _cot("DEADLINE", 5, "fldO2ilBO6"),
    _cot("PIC", 11, "fldBq9IQ84"), _cot("TRẠNG THÁI", 3, "fldeRitfHD", _TT),
    _cot("UPDATE TIẾN ĐỘ", 1, "fldzFtEu2G"), _cot("GIAO TASK", 3001, "fldMLYQfBH"),
    _cot("Các mục mẹ", 18, "fldhaXqZc3"), _cot("Owner", 1003, "fld44rJ15q"),
    _cot("Mã việc Mark", 1, "fldMaViec01"),
]


def _chu(s):
    return [{"text": s, "type": "text"}]


def _dong(rid, ten, nhom, pic=None, tt=None, han=None, kq=None, ma=None, luc=1000):
    f = {"HẠNG MỤC CV": _chu(ten), "NHÓM": nhom}
    if pic:
        f["PIC"] = [{"id": i, "name": n} for i, n in pic]
    if tt:
        f["TRẠNG THÁI"] = tt
    if han:
        f["DEADLINE"] = han
    if kq:
        f["KẾT QUẢ CẦN ĐẠT"] = _chu(kq)
    if ma:
        f["Mã việc Mark"] = _chu(ma)
    return {"record_id": rid, "fields": f, "last_modified_time": luc}


MA_BRIEF = V.ma_viec("20.10", "BOOKING", "Booking gửi brief cho KOC")


def _dong_goc():
    return [
        _dong("recLinh", "Duyệt list KOC collab", "COLLAB",
              pic=[("ou_linh", "Linh Ngọc - Booking KOC/KOL Leader")], tt="ĐANG LÀM "),
        _dong("recAn", "Order media quay chụp", "MEDIA ", pic=[("ou_an", "Trần An")]),
        _dong("recMedia2", "Dựng video teaser", "MEDIA ", pic=[("ou_an", "Trần An")]),
        _dong("recHa1", "Viết caption", "CONTENT", pic=[("ou_ha1", "Nguyễn Hà - Content")]),
        _dong("recHa2", "Chụp ảnh lookbook", "MEDIA ", pic=[("ou_ha2", "Nguyễn Hà - Media")]),
        # Dòng Mark đã tạo lần trước (có mã việc), ô DEADLINE còn trống, TRẠNG THÁI đã đổi.
        _dong("recBrief", "Booking gửi brief cho KOC", "BOOKING", tt="ĐANG LÀM ",
              kq="Gửi brief cho KOC", ma=MA_BRIEF),
    ]


class LarkGia:
    """Base giả: nhớ dòng, khử trùng batch_create theo client_token như Lark thật."""

    def __init__(self):
        self.cot = copy.deepcopy(COT)
        self.dong = _dong_goc()
        self.goi: list[tuple] = []
        self.token_da_dung: dict[str, list] = {}
        self.loi_create: list[Exception] = []
        self.so = 0

    def call(self, method, path, *, query=None, body=None):
        self.goi.append((method, path, copy.deepcopy(query), copy.deepcopy(body)))
        goc = f"/open-apis/bitable/v1/apps/{APP}/tables/{BANG}"
        if method == "GET" and path == goc + "/fields":
            return {"code": 0, "data": {"items": copy.deepcopy(self.cot), "has_more": False}}
        if method == "POST" and path == goc + "/records/search":
            return {"code": 0, "data": {"items": copy.deepcopy(self.dong), "has_more": False}}
        if method == "POST" and path == goc + "/records/batch_create":
            if self.loi_create:
                raise self.loi_create.pop(0)
            tok = query["client_token"]
            if tok in self.token_da_dung:
                return {"code": 0, "data": {"records": self.token_da_dung[tok]}}
            ra = []
            for r in body["records"]:
                self.so += 1
                rid = f"recMoi{self.so}"
                f = {k: (_chu(v) if isinstance(v, str) and k not in ("NHÓM", "TRẠNG THÁI")
                         else v) for k, v in r["fields"].items()}
                self.dong.append({"record_id": rid, "fields": f, "last_modified_time": 5000})
                ra.append({"record_id": rid, "fields": r["fields"]})
            self.token_da_dung[tok] = ra
            return {"code": 0, "data": {"records": ra}}
        if method == "POST" and path == goc + "/records/batch_update":
            for r in body["records"]:
                d = next(x for x in self.dong if x["record_id"] == r["record_id"])
                d["fields"].update(r["fields"])
                d["last_modified_time"] += 1
            return {"code": 0, "data": {"records": body["records"]}}
        raise AssertionError(f"Base giả không biết {method} {path}")

    def ghi(self):
        return [g for g in self.goi if g[1].endswith(("batch_create", "batch_update"))]

    def tao(self):
        return [g for g in self.goi if g[1].endswith("batch_create")]


@pytest.fixture
def lk(monkeypatch, tmp_path):
    for k in ("MARK_BASE_VIEC_URL", "MARK_BASE_VIEC_APP_TOKEN", "MARK_BASE_VIEC_TABLE_ID",
              "MARK_BASE_VIEC_CHIEN_DICH", "MARK_BASE_VIEC_COT_MA", "MARK_BASE_VIEC_TEN",
              "MARK_BASE_VIEC_GHI_PIC"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MARK_GHI_VIEC_BASE", "1")
    g = LarkGia()
    monkeypatch.setattr(lark_client, "call", g.call)
    monkeypatch.setattr(V, "_THU_MUC", tmp_path / "viec_base")
    monkeypatch.setattr(V, "_ngu", lambda s: None)
    ai = {"nguoi": NGUOI, "chat": CHAT, "hoi": ""}
    monkeypatch.setattr(V, "_nguoi_hien_tai", lambda: ai["nguoi"])
    monkeypatch.setattr(V, "_chat_hien_tai", lambda: ai["chat"])
    monkeypatch.setattr(V, "_cau_hoi_hien_tai", lambda: ai["hoi"])
    g.ai = ai
    return g


def _xem(**args):
    return json.loads(V._xem_truoc(args))


def _ghi(**args):
    return json.loads(V._ghi(args))


VIEC = [
    {"hang_muc": "Content viết 10 bài caption", "nhom": "Content", "pic": "Trần An",
     "deadline": "2026-10-24", "deadline_gia_dinh_nam": True, "ket_qua": "10 bài caption"},
    {"hang_muc": "Media quay video BTS", "nhom": "Media", "pic": "Media"},
]


# ───────────────────────────── cấu trúc Base ─────────────────────────────
def test_thieu_cot_ma_viec_thi_tu_choi_va_khong_tu_tao(lk):
    lk.cot = [c for c in lk.cot if c["field_name"] != "Mã việc Mark"]
    kq = _xem(viec=VIEC)
    assert "Mã việc Mark" in kq["error"] and "KHÔNG tự tạo cột" in kq["error"]
    assert not lk.ghi()
    assert not any("/fields" in g[1] and g[0] != "GET" for g in lk.goi), "không được tạo cột"


def test_ten_cot_ma_cau_hinh_duoc(lk, monkeypatch):
    monkeypatch.setenv("MARK_BASE_VIEC_COT_MA", "Mã Mark khác")
    kq = _xem(viec=VIEC)
    assert "Mã Mark khác" in kq["error"]


def test_cot_sai_kieu_thi_dung(lk):
    next(c for c in lk.cot if c["field_name"] == "PIC")["type"] = 1
    kq = _xem(viec=VIEC)
    assert "Base đổi cấu trúc" in kq["error"] and "PIC" in kq["error"]


def test_trang_thai_mat_lua_chon_can_lam_thi_dung(lk):
    c = next(c for c in lk.cot if c["field_name"] == "TRẠNG THÁI")
    c["property"]["options"] = [o for o in c["property"]["options"] if o["name"] != "CẦN LÀM"]
    assert "CẦN LÀM" in _xem(viec=VIEC)["error"]


# ───────────────────────────── lựa chọn NHÓM ─────────────────────────────
def test_lua_chon_lay_ban_dang_dung_nhieu_nhat_ke_ca_khoang_trang_cuoi():
    import collections
    dem = collections.Counter({"MEDIA ": 11, "MEDIA": 2, "EVENT ": 15, "BOOKING": 23})
    assert V.chon_lua_chon("Media", _NHOM, dem) == "MEDIA "
    assert V.chon_lua_chon("  media  ", _NHOM, dem) == "MEDIA "
    assert V.chon_lua_chon("booking", _NHOM, dem) == "BOOKING"
    assert V.chon_lua_chon("Event", _NHOM, dem) == "EVENT "
    # Không dòng nào dùng: hoà → bản không có khoảng trắng thừa.
    assert V.chon_lua_chon("kế hoạch", _NHOM, dem) == "KẾ HOẠCH"
    assert V.chon_lua_chon("Store - hộp nhạc", _NHOM, dem) == "STORE - HỘP NHẠC"


def test_nhom_la_khong_bao_gio_tao_lua_chon_moi(lk):
    assert V.chon_lua_chon("Design", _NHOM, {}) is None
    assert V.chon_lua_chon("", _NHOM, {}) is None, "không bao giờ chọn lựa chọn rỗng"
    kq = _xem(viec=[{"hang_muc": "Thiết kế banner", "nhom": "Design"}])
    assert kq["khong_co_gi_de_ghi"] and kq["dem"]["loi"] == 1
    assert "không tự thêm lựa chọn" in kq["cau_xem_truoc"]
    assert kq["ma_xem_truoc"] is None and not lk.ghi()


# ───────────────────────────── ngày ─────────────────────────────
def test_ngay_ra_ms_luc_0h_gio_viet_nam():
    assert V._ngay_ms("2026-10-24")[0] == 1792774800000
    assert V._ngay_ms("2026/9/29")[0] == 1790614800000      # mẫu thật trong Base
    assert V._ngay_ms("2026-10-24*")[2] == "2026/10/24"
    assert V._ngay_ms("")[:2] == (None, None)
    assert V._ngay_ms("thứ 6 tuần sau")[1] and V._ngay_ms("2026-02-30")[1]


def test_thieu_han_thi_khong_gui_o_ngay(lk):
    kq = _xem(viec=VIEC)
    _ghi(ma_xem_truoc=kq["ma_xem_truoc"])
    ban = lk.tao()[0][3]["records"]
    assert ban[0]["fields"]["DEADLINE"] == 1792774800000
    assert "DEADLINE" not in ban[1]["fields"], "không có hạn thì bỏ ô, không gửi 0"
    assert "2026/10/24*" in kq["cau_xem_truoc"] and "giả định năm" in kq["cau_xem_truoc"]


# ───────────────────────────── PIC ─────────────────────────────
DS_PIC = {"ou_linh": "Linh Ngọc - Booking KOC/KOL Leader", "ou_an": "Trần An",
          "ou_ha1": "Nguyễn Hà - Content", "ou_ha2": "Nguyễn Hà - Media"}


def test_pic_khop_dung_mot_nguoi_bo_chuc_danh():
    oid, hien, cb = V.giai_pic("Linh Ngọc", "", DS_PIC, "", True)
    assert (oid, cb) == ("ou_linh", None) and hien == "Linh Ngọc"
    assert V.giai_pic("linh ngoc", "", DS_PIC, "", True)[0] == "ou_linh"


def test_pic_mo_ho_hoac_khong_khop_thi_de_trong():
    oid, _, cb = V.giai_pic("Nguyễn Hà", "", DS_PIC, "", True)
    assert oid is None and "khớp 2 người" in cb
    oid, _, cb = V.giai_pic("Booking", "", DS_PIC, "", True)
    assert oid is None and "để trống" in cb
    assert V.giai_pic("Linh", "", DS_PIC, "", True)[0] is None, "không khớp một phần tên"
    assert V.giai_pic("", "", DS_PIC, "", True) == (None, "", None)


def test_pic_open_id_chi_nhan_khi_co_trong_tin_nhan():
    assert V.giai_pic("", "ou_an", DS_PIC, "giao cho @ou_an nhé", True)[0] == "ou_an"
    # Có trong tin nhắn nhưng chưa từng là PIC trên Base → không kéo người ngoài vào.
    assert V.giai_pic("", "ou_moi", DS_PIC, "giao cho @ou_moi nhé", True)[0] is None
    oid, _, cb = V.giai_pic("", "ou_bia", DS_PIC, "giao cho bạn kia", True)
    assert oid is None and "không có trong tin nhắn" in cb


def test_tat_ghi_pic(lk, monkeypatch):
    assert V.giai_pic("Linh Ngọc", "", DS_PIC, "", False)[0] is None
    monkeypatch.setenv("MARK_BASE_VIEC_GHI_PIC", "0")
    kq = _xem(viec=VIEC)
    _ghi(ma_xem_truoc=kq["ma_xem_truoc"])
    assert all("PIC" not in r["fields"] for r in lk.tao()[0][3]["records"])
    assert "đang tắt ghi PIC" in kq["cau_xem_truoc"]


def test_tat_ghi_pic_sau_luc_xem_truoc_van_bo_pic(lk, monkeypatch):
    kq = _xem(viec=VIEC)
    assert any("PIC" in x["sau"] and x["sau"]["PIC"] == "Trần An" for x in kq["dong"])
    monkeypatch.setenv("MARK_BASE_VIEC_GHI_PIC", "0")
    _ghi(ma_xem_truoc=kq["ma_xem_truoc"])
    assert all("PIC" not in r["fields"] for r in lk.tao()[0][3]["records"])


def test_pic_trong_payload_la_open_id(lk):
    kq = _xem(viec=VIEC)
    assert kq["pic_chua_ro"] and "dòng 2" in kq["pic_chua_ro"][0]
    _ghi(ma_xem_truoc=kq["ma_xem_truoc"])
    r = lk.tao()[0]
    assert r[2]["user_id_type"] == "open_id"
    assert r[3]["records"][0]["fields"]["PIC"] == [{"id": "ou_an"}]
    assert "PIC" not in r[3]["records"][1]["fields"]


# ───────────────────────────── khoá chống trùng ─────────────────────────────
def test_ma_viec_on_dinh():
    a = V.ma_viec("20.10", "BOOKING", "Booking gửi brief cho KOC")
    assert re.fullmatch(r"MK-[0-9A-F]{10}", a)
    assert a == V.ma_viec("20.10", "booking ", "  booking GUI brief  cho koc.")
    assert a != V.ma_viec("20.10", "MEDIA", "Booking gửi brief cho KOC")
    assert a != V.ma_viec("11.11", "BOOKING", "Booking gửi brief cho KOC")


def test_chien_dich_lay_tu_cau_hinh_khong_tu_model(lk, monkeypatch):
    kq = _xem(viec=[{**VIEC[1], "chien_dich": "99.99"}], chien_dich="99.99")
    assert kq["dong"][0]["ma_viec"] == V.ma_viec("20.10", "MEDIA ", "Media quay video BTS")
    monkeypatch.setenv("MARK_BASE_VIEC_CHIEN_DICH", "11.11")
    kq = _xem(viec=[VIEC[1]])
    assert kq["dong"][0]["ma_viec"] == V.ma_viec("11.11", "MEDIA", "Media quay video BTS")


# ───────────────────────────── xem trước ─────────────────────────────
def test_xem_truoc_khong_ghi_lark_va_luu_ban(lk):
    kq = _xem(viec=VIEC)
    assert kq["success"] and re.fullmatch(r"XV-[A-Z2-7]{6}", kq["ma_xem_truoc"])
    assert kq["dem"] == {"tao": 2, "cap_nhat": 0, "giu_nguyen": 0, "can_xem": 0, "loi": 0}
    assert {(g[0], g[1].rsplit("/", 1)[-1]) for g in lk.goi} == {("GET", "fields"),
                                                                ("POST", "search")}
    assert kq["cau_xem_truoc"].startswith(f"XEM TRƯỚC (mã {kq['ma_xem_truoc']}")
    assert "không gửi tin, không tag" in kq["cau_xem_truoc"]
    assert "Ghi vào Base nhé?" in kq["huong_dan"]
    assert (V._THU_MUC / f"{kq['ma_xem_truoc']}.json").is_file()


def test_tao_moi_trang_thai_can_lam_va_chi_cot_cho_phep(lk):
    _ghi(ma_xem_truoc=_xem(viec=VIEC)["ma_xem_truoc"])
    duoc = {"HẠNG MỤC CV", "NHÓM", "PIC", "DEADLINE", "TRẠNG THÁI", "KẾT QUẢ CẦN ĐẠT",
            "Mã việc Mark"}
    for r in lk.tao()[0][3]["records"]:
        assert set(r["fields"]) <= duoc
        assert r["fields"]["TRẠNG THÁI"] == "CẦN LÀM"
    assert lk.tao()[0][3]["records"][1]["fields"]["NHÓM"] == "MEDIA "


def test_toi_da_50_viec(lk):
    kq = _xem(viec=[{"hang_muc": f"Việc {i}", "nhom": "Content"} for i in range(51)])
    assert "tối đa 50" in kq["error"] and not lk.goi
    assert _xem(viec=[{"hang_muc": f"Việc {i}", "nhom": "Content"} for i in range(50)])["success"]


def test_viec_giong_do_nguoi_tao_thi_can_xem(lk):
    kq = _xem(viec=[{"hang_muc": "Duyệt list KOC collab", "nhom": "Collab"}])
    assert kq["dem"]["can_xem"] == 1 and kq["khong_co_gi_de_ghi"]
    assert "recLinh" in kq["cau_xem_truoc"]


def test_trung_trong_cung_danh_sach(lk):
    kq = _xem(viec=[VIEC[1], {**VIEC[1], "hang_muc": "media quay video BTS."}])
    assert kq["dem"]["tao"] == 1 and kq["dem"]["can_xem"] == 1


def test_dong_da_co_chi_dien_o_trong_khong_doi_trang_thai(lk):
    kq = _xem(viec=[{"hang_muc": "Booking gửi brief cho KOC", "nhom": "Booking",
                     "deadline": "2026-10-20", "ket_qua": "Nội dung khác"}])
    assert kq["dem"]["cap_nhat"] == 1
    assert "giữ nguyên" in json.dumps(kq["dong"], ensure_ascii=False)
    kq2 = _ghi(ma_xem_truoc=kq["ma_xem_truoc"])
    upd = [g for g in lk.goi if g[1].endswith("batch_update")]
    assert len(upd) == 1 and kq2["da_cap_nhat"][0]["record_id"] == "recBrief"
    f = upd[0][3]["records"][0]["fields"]
    assert f == {"DEADLINE": V._ngay_ms("2026-10-20")[0]}, "chỉ điền ô trống, không đụng TRẠNG THÁI"


def test_record_id_khong_co_trong_bang_la_loi(lk):
    kq = _xem(viec=[{**VIEC[1], "record_id": "recKhongCo"}])
    assert kq["dem"]["loi"] == 1


# ───────────────────────────── ghi: ai được duyệt ─────────────────────────────
def test_ghi_dung_nguoi_dung_chat(lk):
    ma = _xem(viec=VIEC)["ma_xem_truoc"]
    kq = _ghi(ma_xem_truoc=ma)
    assert kq["success"] and len(kq["da_tao"]) == 2
    assert kq["da_tao"][0]["link"].endswith(f"&record={kq['da_tao'][0]['record_id']}")
    assert "tạo mới 2 việc" in kq["cau_ket_qua"]


@pytest.mark.parametrize("ai", [{"nguoi": "ou_nguoi_khac"}, {"chat": "oc_chat_khac"},
                                {"nguoi": ""}])
def test_nguoi_khac_hoac_chat_khac_khong_duyet_duoc(lk, ai):
    ma = _xem(viec=VIEC)["ma_xem_truoc"]
    lk.ai.update(ai)
    kq = _ghi(ma_xem_truoc=ma)
    assert "error" in kq and not lk.ghi()


def test_het_han_24_gio(lk, monkeypatch):
    ma = _xem(viec=VIEC)["ma_xem_truoc"]
    goc = V.time.time
    monkeypatch.setattr(V.time, "time", lambda: goc() + 24 * 3600 + 5)
    kq = _ghi(ma_xem_truoc=ma)
    assert "hết hạn" in kq["error"] and not lk.ghi()


def test_ban_bi_sua_tay_thi_tu_choi(lk):
    ma = _xem(viec=VIEC)["ma_xem_truoc"]
    p = V._THU_MUC / f"{ma}.json"
    b = json.loads(p.read_text(encoding="utf-8"))
    b["rows"][0]["ghi"]["TRẠNG THÁI"] = "ĐÃ XONG"
    p.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    assert "không còn nguyên vẹn" in _ghi(ma_xem_truoc=ma)["error"] and not lk.ghi()


def test_ban_moi_thay_ban_cu(lk):
    cu = _xem(viec=VIEC)["ma_xem_truoc"]
    moi = _xem(viec=VIEC[:1])["ma_xem_truoc"]
    assert "bị bản xem trước mới hơn thay" in _ghi(ma_xem_truoc=cu)["error"]
    kq = _ghi()                                # không nói mã → bản đang chờ duy nhất
    assert kq["ma_xem_truoc"] == moi and len(kq["da_tao"]) == 1


def test_bo_dong_chi_thu_hep(lk):
    ma = _xem(viec=VIEC)["ma_xem_truoc"]
    assert "không có dòng" in _ghi(ma_xem_truoc=ma, bo_dong=[7])["error"] and not lk.ghi()
    kq = _ghi(ma_xem_truoc=ma, bo_dong=[2])
    assert len(kq["da_tao"]) == 1 and kq["bo_qua"][0]["stt"] == 2


def test_cot_doi_sau_luc_xem_truoc_thi_khong_ghi(lk):
    ma = _xem(viec=VIEC)["ma_xem_truoc"]
    next(c for c in lk.cot if c["field_name"] == "NHÓM")["property"]["options"].append(
        {"name": "DESIGN", "id": "optX"})
    assert "Cột của Base đã đổi" in _ghi(ma_xem_truoc=ma)["error"] and not lk.ghi()


# ───────────────────────────── chạy lại không trùng ─────────────────────────────
def test_chay_lai_khong_tao_trung(lk):
    ma = _xem(viec=VIEC)["ma_xem_truoc"]
    _ghi(ma_xem_truoc=ma)
    kq = _ghi(ma_xem_truoc=ma)
    assert len(lk.tao()) == 1, "lần hai không được gọi batch_create"
    assert kq["da_tao"] is None and len(kq["da_co_san"]) == 2


def test_sap_sau_khi_tao_truoc_khi_luu_so_van_khong_trung(lk):
    ma = _xem(viec=VIEC)["ma_xem_truoc"]
    p = V._THU_MUC / f"{ma}.json"
    truoc = p.read_text(encoding="utf-8")
    _ghi(ma_xem_truoc=ma)
    p.write_text(truoc, encoding="utf-8")       # như thể chết trước khi ghi `lan_ghi`
    kq = _ghi(ma_xem_truoc=ma)
    assert len(lk.tao()) == 1 and len(kq["da_co_san"]) == 2
    assert sum(1 for d in lk.dong if d["record_id"].startswith("recMoi")) == 2


def test_xem_truoc_lai_sau_khi_ghi_la_giu_nguyen(lk):
    _ghi(ma_xem_truoc=_xem(viec=VIEC)["ma_xem_truoc"])
    kq = _xem(viec=VIEC)
    assert kq["dem"]["giu_nguyen"] == 2 and kq["khong_co_gi_de_ghi"]


def test_client_token_co_dinh_khi_thu_lai(lk):
    lk.loi_create = [RuntimeError("Lark POST x failed: HTTP 429: too many")]
    kq = _ghi(ma_xem_truoc=_xem(viec=VIEC)["ma_xem_truoc"])
    tok = [g[2]["client_token"] for g in lk.tao()]
    assert len(tok) == 2 and tok[0] == tok[1]
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                        tok[0])
    assert len(kq["da_tao"]) == 2 and sum(d["record_id"].startswith("recMoi")
                                          for d in lk.dong) == 2


def test_loi_ca_lo_thi_doc_lai_roi_tao_tung_dong(lk):
    lk.loi_create = [RuntimeError("Lark POST x failed: {'code': 1254060, 'msg': 'TextFieldConvFail'}")]
    kq = _ghi(ma_xem_truoc=_xem(viec=VIEC)["ma_xem_truoc"])
    assert len(lk.tao()) == 3 and len(kq["da_tao"]) == 2
    assert all(len(g[3]["records"]) == 1 for g in lk.tao()[1:])


def test_bo_qua_dong_nguoi_sua_sau_luc_xem_truoc(lk):
    kq = _xem(viec=[{"hang_muc": "Booking gửi brief cho KOC", "nhom": "Booking",
                     "deadline": "2026-10-20"}, VIEC[1]])
    next(d for d in lk.dong if d["record_id"] == "recBrief")["last_modified_time"] = 9999
    kq2 = _ghi(ma_xem_truoc=kq["ma_xem_truoc"])
    assert not [g for g in lk.goi if g[1].endswith("batch_update")]
    assert kq2["bo_qua"][0]["stt"] == 1 and "người sửa" in kq2["bo_qua"][0]["ly_do"]
    assert len(kq2["da_tao"]) == 1


def test_nguoi_vua_tao_viec_giong_thi_bo_qua(lk):
    ma = _xem(viec=VIEC[1:])["ma_xem_truoc"]
    lk.dong.append(_dong("recNguoi", "Media quay video BTS", "MEDIA "))
    kq = _ghi(ma_xem_truoc=ma)
    assert not lk.tao() and "người tạo sau lúc xem trước" in kq["bo_qua"][0]["ly_do"]


# ───────────────────────────── Base đích + endpoint ─────────────────────────────
def test_model_khong_chon_duoc_base(lk):
    kq = _xem(viec=[{**VIEC[1], "app_token": "bascnKhac123456", "table_id": "tblKhac"}],
              app_token="bascnKhac123456", table_id="tblKhac",
              bang_url="https://x.larksuite.com/base/bascnKhac123456?table=tblKhac")
    _ghi(ma_xem_truoc=kq["ma_xem_truoc"], app_token="bascnKhac123456", table_id="tblKhac")
    assert all(f"/apps/{APP}/tables/{BANG}/" in g[1] for g in lk.goi)
    assert "app_token" not in json.dumps(V.SCHEMA_XEM) + json.dumps(V.SCHEMA_GHI)


def test_staging_doi_base_bang_env(lk, monkeypatch):
    monkeypatch.setenv("MARK_BASE_VIEC_URL",
                       "https://o4pvcegwn6b.sg.larksuite.com/base/bascnStaging0001?table=tblStage1")
    d = V.cau_hinh()
    assert (d["app_token"], d["table_id"]) == ("bascnStaging0001", "tblStage1")
    _xem(viec=VIEC)
    assert lk.goi[0][1].startswith("/open-apis/bitable/v1/apps/bascnStaging0001/tables/tblStage1/")


def test_doi_base_giua_xem_truoc_va_ghi_thi_tu_choi(lk, monkeypatch):
    ma = _xem(viec=VIEC)["ma_xem_truoc"]
    monkeypatch.setenv("MARK_BASE_VIEC_TABLE_ID", "tblKhac2")
    assert "Base đích trong cấu hình đã đổi" in _ghi(ma_xem_truoc=ma)["error"]


def test_chi_goi_endpoint_cho_phep(lk):
    kq = _xem(viec=VIEC + [{"hang_muc": "Booking gửi brief cho KOC", "nhom": "Booking",
                            "deadline": "2026-10-20"}])
    _ghi(ma_xem_truoc=kq["ma_xem_truoc"])
    _ghi(ma_xem_truoc=kq["ma_xem_truoc"])
    for m, p, *_ in lk.goi:
        assert any(m == mm and r.match(p) for mm, r in V._DUONG_CHO_PHEP), (m, p)
        assert "/im/" not in p and "/task" not in p and m != "DELETE"
    for m, p in (("POST", "/open-apis/im/v1/messages"), ("POST", "/open-apis/task/v2/tasks"),
                 ("DELETE", f"/open-apis/bitable/v1/apps/{APP}/tables/{BANG}/records/rec1"),
                 ("POST", f"/open-apis/bitable/v1/apps/{APP}/tables/{BANG}/fields")):
        n = len(lk.goi)
        with pytest.raises(PermissionError):
            V._goi(m, p)
        assert len(lk.goi) == n, "phải chặn TRƯỚC khi ra mạng"


def test_tat_thi_khong_chay(lk, monkeypatch):
    monkeypatch.setenv("MARK_GHI_VIEC_BASE", "0")
    assert "TẮT" in _xem(viec=VIEC)["error"] and "TẮT" in _ghi(ma_xem_truoc="XV-AAAAAA")["error"]
    assert not lk.goi and not V._bat()


# ───────────────────────────── policy + brain ─────────────────────────────
def test_policy_phan_loai():
    assert lsr_policy._MUTATING_EXACT["ghi_viec_base"] == "write_data"
    assert "xem_truoc_viec_base" in lsr_policy._SAFE_EXACT
    assert {"ghi_viec_base", "xem_truoc_viec_base"} <= lsr_policy._TOOL_CO_CONG_TAC
    assert "ghi_viec_base" not in lsr_policy._CONG_TAC_LUI, "tool ghi KHÔNG mượn công tắc nào"
    assert lsr_policy._CONG_TAC_LUI["xem_truoc_viec_base"] == "ghi_viec_base"


def _dat(quyen, bat):
    import time
    lsr_policy._nho.update(quyen=set(quyen), luc=time.time(), nguon="test")
    lsr_policy._nho_nl.update(bat=bat, luc=time.time(), nguon="test")


@pytest.mark.parametrize("tool", ["ghi_viec_base", "xem_truoc_viec_base"])
def test_policy_mac_dinh_tat_theo_env(monkeypatch, tool):
    _dat({"reply", "call_agent", "write_data"}, lsr_policy.KHONG_THU_HEP)
    monkeypatch.delenv("MARK_GHI_VIEC_BASE", raising=False)
    d = lsr_policy.decide(tool, {})
    assert not d.allowed and "MARK_GHI_VIEC_BASE" in d.reason
    monkeypatch.setenv("MARK_GHI_VIEC_BASE", "1")
    assert lsr_policy.decide(tool, {}).allowed


def test_policy_cong_tac_khong_lui(monkeypatch):
    monkeypatch.setenv("MARK_GHI_VIEC_BASE", "1")
    _dat({"reply", "call_agent", "write_data"}, {"social_listen", "doc_bang"})
    assert not lsr_policy.decide("ghi_viec_base", {}).allowed, "console chưa có dòng → TẮT"
    assert not lsr_policy.decide("xem_truoc_viec_base", {}).allowed
    _dat({"reply", "call_agent", "write_data"}, {"ghi_viec_base"})
    assert lsr_policy.decide("ghi_viec_base", {}).allowed
    assert lsr_policy.decide("xem_truoc_viec_base", {}).allowed, "xem trước theo công tắc ghi"
    _dat({"reply", "call_agent"}, {"ghi_viec_base"})
    assert not lsr_policy.decide("ghi_viec_base", {}).allowed, "không nới quá hợp đồng"


def test_lark_cli_ghi_base_van_bi_chan(monkeypatch):
    monkeypatch.setenv("MARK_GHI_VIEC_BASE", "1")
    _dat({"reply", "call_agent", "write_data"}, lsr_policy.KHONG_THU_HEP)
    assert not lsr_policy.decide("lark_cli", {"args": ["base", "+record-create", "--yes"]}).allowed
    assert not lsr_policy.decide("lark_cli", {"args": ["api", "POST", "/open-apis/bitable/v1/x"]}
                                 ).allowed


def test_dang_ky_va_noi_brain():
    from tools.registry import registry  # type: ignore
    for t in ("xem_truoc_viec_base", "ghi_viec_base"):
        e = registry._tools[t]
        assert e.toolset == "lark_api" and e.check_fn is V._bat
    import pathlib
    goc = pathlib.Path(__file__).resolve().parent.parent
    brain = (goc / "brain.py").read_text(encoding="utf-8")
    assert "import viec_base_tool" in brain
    assert '"ghi_viec_base":' in brain and '"xem_truoc_viec_base":' in brain   # _TOOL_CAN_XET
    assert "Ghi vào Base nhé?" in brain and "`ghi_viec_base`" in brain
    for f in ("hop-va-ban-giao.md", "ke-hoach-chien-dich-tong.md"):
        sk = (goc / "skills" / f).read_text(encoding="utf-8")
        assert "Ghi vào Base nhé?" in sk and "xem trước" in sk
        assert "không tag" in sk.lower() and "gửi tin" in sk
    assert "Mark không tự tạo task Lark" not in (goc / "skills" / "hop-va-ban-giao.md"
                                                ).read_text(encoding="utf-8")
