"""Hồi quy 02/10/2026: dòng audit bị nhân đôi + Turn ID trống trong "Chi phí quét".

1. 4 lượt (25/09, 30/09) có 2 dòng giống hệt trong bảng Audit: dòng thứ hai tạo lúc bot
   khởi động lại — `dong_bo_lai()` tin mốc `da_day_den` đã lệch nên đẩy lại dòng đã có.
2. Turn ID lưu ở threading.local nên không sang luồng tool của Hermes / luồng con.
3. Lần quét ngoài lượt bot (script/test chạy tay) để trống Turn ID.
"""
import contextvars
import datetime
import json
from concurrent.futures import ThreadPoolExecutor

import audit
import chi_phi_tool


def _jsonl(tmp_path, monkeypatch, recs, thang="2026-09"):
    d = tmp_path / ".audit"
    d.mkdir(exist_ok=True)
    (d / f"audit-{thang}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    monkeypatch.setattr(audit, "_THU_MUC", d)


def _base_gia(monkeypatch, co_san, loi_doc=False):
    """Giả Lark: GET records trả `co_san` Turn ID; POST records ghi vào `day`."""
    day = []

    def call(method, path, *, query=None, body=None):
        if method == "GET" and path.endswith("/records"):
            if loi_doc:
                raise RuntimeError("HTTP 500")
            return {"data": {"items": [{"fields": {"Turn ID": [{"text": t, "type": "text"}]}}
                                       for t in co_san], "has_more": False}}
        if method == "GET" and path.endswith("/fields"):
            return {"data": {"items": [{"field_name": n} for n, _ in audit._COT]}}
        if method == "POST" and path.endswith("/records"):
            day.append(body["fields"]["Turn ID"])
            return {"code": 0, "data": {}}
        raise AssertionError(f"goi la: {method} {path}")

    monkeypatch.setattr(audit.lark, "call", call)
    monkeypatch.setattr(audit, "_ten_nguoi", lambda x: x)
    monkeypatch.setattr(audit, "_DAY_LEN_BASE", True)
    monkeypatch.setattr(audit, "_da_kiem_cot", True)
    return day


def _cfg(tmp_path, monkeypatch, **them):
    p = tmp_path / "audit_base.json"
    p.write_text(json.dumps({"app_token": "app", "table_id": "tbl", **them}), encoding="utf-8")
    monkeypatch.setattr(audit, "_CAU_HINH", p)
    return p


def _rec(tid, ts):
    return {"turn_id": tid, "ts": ts, "chat": "lark:x", "hoi": "q"}


def _thang_nay():
    return f"{datetime.datetime.now(audit._VN):%Y-%m}"


def test_dong_bo_lai_khong_day_lai_dong_da_co_tren_base(tmp_path, monkeypatch):
    """Ca thật 30/09: mốc kẹt ở lượt trước, lượt cuối ĐÃ lên Base → không được đẩy lại."""
    _jsonl(tmp_path, monkeypatch, [_rec("a", 1.0), _rec("b", 2.0), _rec("c", 3.0)],
           thang=_thang_nay())
    p = _cfg(tmp_path, monkeypatch, da_day_den="a")
    day = _base_gia(monkeypatch, co_san={"a", "b"})
    assert audit.dong_bo_lai() == 1
    assert day == ["c"], "chỉ đẩy dòng THIẾU trên Base"
    assert json.loads(p.read_text(encoding="utf-8"))["da_day_den"] == "c"


def test_dong_bo_lai_du_lieu_da_du_thi_khong_day_va_tien_moc(tmp_path, monkeypatch):
    _jsonl(tmp_path, monkeypatch, [_rec("a", 1.0), _rec("b", 2.0)], thang=_thang_nay())
    p = _cfg(tmp_path, monkeypatch, da_day_den="a")
    day = _base_gia(monkeypatch, co_san={"a", "b"})
    assert audit.dong_bo_lai() == 0 and day == []
    assert json.loads(p.read_text(encoding="utf-8"))["da_day_den"] == "b"


def test_dong_bo_lai_khong_doc_duoc_base_thi_khong_day(tmp_path, monkeypatch):
    """Đọc Base lỗi mà vẫn đẩy là nhân đôi — thà để lần khởi động sau."""
    _jsonl(tmp_path, monkeypatch, [_rec("a", 1.0), _rec("b", 2.0)], thang=_thang_nay())
    p = _cfg(tmp_path, monkeypatch, da_day_den="a")
    day = _base_gia(monkeypatch, co_san=set(), loi_doc=True)
    assert audit.dong_bo_lai() == 0 and day == []
    assert json.loads(p.read_text(encoding="utf-8"))["da_day_den"] == "a", "mốc giữ nguyên"


def test_dong_bo_lai_doc_ca_file_thang_truoc(tmp_path, monkeypatch):
    """Khởi động đầu tháng: mốc ở file tháng trước, lượt cuối tháng trước chưa lên."""
    nay = datetime.datetime.now(audit._VN)
    truoc = nay.replace(day=1) - datetime.timedelta(days=1)
    _jsonl(tmp_path, monkeypatch, [_rec("a", 1.0), _rec("b", 2.0)], thang=f"{truoc:%Y-%m}")
    _jsonl(tmp_path, monkeypatch, [_rec("c", 3.0)], thang=f"{nay:%Y-%m}")
    _cfg(tmp_path, monkeypatch, da_day_den="a")
    day = _base_gia(monkeypatch, co_san={"a", "c"})
    assert audit.dong_bo_lai() == 1 and day == ["b"]


def test_ghi_moc_khong_lui(tmp_path, monkeypatch):
    """Hai thread `_day` xong lệch thứ tự: lượt cũ không kéo mốc về trước."""
    p = _cfg(tmp_path, monkeypatch)
    audit._ghi_moc("moi", 20.0)
    audit._ghi_moc("cu", 10.0)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    assert cfg["da_day_den"] == "moi" and cfg["table_id"] == "tbl"


def test_ghi_moc_khong_xoa_cau_hinh_khi_doc_hong(tmp_path, monkeypatch):
    p = tmp_path / "audit_base.json"
    p.write_text("{hong", encoding="utf-8")
    monkeypatch.setattr(audit, "_CAU_HINH", p)
    audit._ghi_moc("x", 1.0)
    assert p.read_text(encoding="utf-8") == "{hong", "không ghi đè thành file thiếu table_id"


def test_turn_id_sang_luong_tool_qua_copy_context(monkeypatch):
    """Hermes chạy tool trong ThreadPoolExecutor qua copy_context(): tool phải thấy lượt."""
    monkeypatch.setattr(audit, "_BAT", True)

    def mot_luot():
        tid = audit.bat_dau("lark:x", "ou_1", "q")
        with ThreadPoolExecutor(max_workers=1) as ex:
            thay = ex.submit(contextvars.copy_context().run, audit.turn_id_hien_tai).result()
            ex.submit(contextvars.copy_context().run, audit.ghi_tool,
                      "social_listen", {}, "ok", 1.0).result()
        rec = audit.ket_thuc(tid, "xong")
        return tid, thay, rec, audit.turn_id_hien_tai()

    tid, thay, rec, sau = contextvars.copy_context().run(mot_luot)
    assert thay == tid
    assert [t["ten"] for t in rec["tool"]] == ["social_listen"], "tool ở luồng khác vẫn được ghi"
    assert sau == "", "đóng lượt thì xoá turn_id khỏi ngữ cảnh"


def test_chi_phi_trong_luot_o_luong_con_co_turn_id(monkeypatch):
    monkeypatch.setattr(audit, "_BAT", True)

    def mot_luot():
        tid = audit.bat_dau("lark:x", "ou_1", "q")
        with ThreadPoolExecutor(max_workers=1) as ex:
            rec = ex.submit(contextvars.copy_context().run, lambda: chi_phi_tool.ghi(
                queries=["a"], platforms=["tiktok"], date_range="", thuc=None, est=0.1)).result()
        audit.ket_thuc(tid, "xong")
        return tid, rec

    tid, rec = contextvars.copy_context().run(mot_luot)
    assert rec["turn_id"] == tid and rec["chat"] == "lark:x"
    assert chi_phi_tool._fields(rec)["Turn ID"] == tid


def test_chi_phi_ngoai_luot_ghi_ro_nguon():
    rec = contextvars.Context().run(lambda: chi_phi_tool.ghi(
        queries=["a"], platforms=["shopee"], date_range="", thuc=None, est=0.1))
    assert rec["turn_id"] == ""
    assert chi_phi_tool._fields(rec)["Turn ID"].startswith("ngoai-luot:")


def test_chi_phi_viec_nen_giu_ma_viec():
    rec = contextvars.Context().run(lambda: chi_phi_tool.ghi(
        queries=["a"], platforms=["youtube"], date_range="", thuc=None, est=0.0,
        chat="thu-nen", ma_viec="q1"))
    assert chi_phi_tool._fields(rec)["Turn ID"] == "viec-nen:q1"
    assert "nguon" not in rec


def test_adapter_web_ghi_so_chi_phi(monkeypatch):
    """UAT-WEB-04: adapter Apify của web_crawl tốn tiền thật phải có dòng trong sổ."""
    import apify_tool
    import crawl_adapters

    ghi = []
    monkeypatch.setattr(chi_phi_tool, "ghi", lambda **k: ghi.append(k) or {})
    monkeypatch.setattr(apify_tool, "_chi_phi_thuc", lambda actors, tu, est: {
        "usd": 0.02, "so_run": len(actors), "cham_tran": 0})
    monkeypatch.setattr(crawl_adapters, "_call", lambda actor, inp, n: [])
    mien = next(iter(crawl_adapters._BANG))
    log = []
    kq = crawl_adapters.chay(f"https://www.{mien}/vn/vi/", 5, log)
    assert kq["san_pham"] == []
    assert len(ghi) == 1 and ghi[0]["platforms"] == ["web"]
    assert ghi[0]["thuc"]["so_run"] >= 1, "actor lỗi/ra rỗng vẫn bị Apify tính tiền"
