"""Lịch quét TỰ ĐỘNG của Mark (chủ dự án chốt 15/10/2026: "Dashboard + Mark tự chạy").

Lịch đặt trên dashboard social.hapas.vn (tab Lịch quét), lưu ở bảng `lich_quet` của kho
`lang_nghe`; cách tính mốc nằm ở `dashboard/lich_quet.py` (thuần, dùng chung với dashboard).
Module này là nhịp 30 giây trong tiến trình Mark: tới mốc thì tạo ĐÚNG việc nền `/theodoi` như
khi người gõ lệnh (`theo_doi.tao_luot`) — cùng công tắc Soi tài khoản, công tắc + trần từng nền
tảng trên console, trần tháng của dự án, ngân sách việc nền của tài khoản Apify. Lịch "Giao
việc" trên console (`/theodoi hapas`) vẫn chạy song song như cũ.

Vì sao không chạy một mốc hai lần, không kẹt:
  • NHẬN lịch trong MỘT giao dịch `FOR UPDATE SKIP LOCKED` và COMMIT mốc kế TRƯỚC khi tạo việc
    (`lang_nghe_db.nhan_lich_den_han`): lỡ chạy hai bản Mark thì mỗi mốc chỉ một bản nhận; chết
    giữa lúc ghi mốc và lúc tạo việc thì lỡ đúng một lượt, không bao giờ chạy lại.
  • Chỉ tiến trình đang giữ quyền chủ việc nền (`viec_nen.con_quyen`) mới nhận lịch — bản thừa
    không "ăn" mốc rồi bị sổ việc nền từ chối.
  • Mốc nằm trong tham số việc (`tham_so.moc`): cùng mốc nhận hai lần thì sổ việc nền trả lại
    đúng việc cũ.
  • Mark tắt rồi bật lại: mốc lỡ chưa quá 30 phút thì chạy bù MỘT lần, quá thì bỏ (ghi lý do).
  • Chiến dịch đang diễn ra thì lịch thường cùng dự án nhường (không quét chồng).
  • Lượt trước còn chạy / hết tháng / công tắc tắt: không chạy, ghi lý do vào `ket_qua_cuoi`.
  • Nhịp không bao giờ ném ra ngoài; lỗi chỉ ghi log (mỗi loại một lần).
KHÔNG nhắn Lark mỗi lượt — kết quả xem trên dashboard. Tuỳ chọn `MARK_LICH_QUET_BAO_LOI` = mã
nhóm `oc_…` (hoặc `lark:<app>:oc_…`) hay open_id `ou_…`: nhận MỘT tin cảnh báo mỗi lịch, mỗi
loại (lỗi / hết ngân sách), mỗi ngày. Tắt hẳn nhịp: `MARK_LICH_QUET=0`.
"""
from __future__ import annotations

import datetime
import os
import re
import threading
import time

import lang_nghe_db as K
from dashboard import lich_quet as LQ

VN = LQ.VN
NHIP = 30                     # giây giữa hai nhịp
TOI_DA_MOI_NHIP = 20          # lịch nhận mỗi nhịp (còn thì nhịp sau)
#: Mã lỗi của `theo_doi.tao_luot` coi là BỎ QUA bình thường (không phải lỗi, không cảnh báo).
BO_QUA = {"dang_chay", "du_an_tat", "khong_co_gi", "het_ngan_sach", "het_ngan_sach_apify",
          "nang_luc_tat", "khong_quet_duoc", "trung"}
#: Loại cảnh báo gửi (khi có `MARK_LICH_QUET_BAO_LOI`): mã -> nhãn.
CANH_BAO = {"loi": "LỖI", "het_ngan_sach": "HẾT NGÂN SÁCH"}
_LUONG: dict = {}
_DA_BAO: set[str] = set()


def _bay_gio() -> datetime.datetime:
    return datetime.datetime.now(VN)


def bat() -> bool:
    return (os.environ.get("MARK_LICH_QUET") or "1").strip() != "0"


def _bao_mot_lan(khoa: str, chu: str) -> None:
    """Log mỗi sự việc MỘT lần (nhịp 30 giây mà in lỗi mỗi nhịp thì log ngập)."""
    if khoa in _DA_BAO:
        return
    if len(_DA_BAO) > 500:
        _DA_BAO.clear()
    _DA_BAO.add(khoa)
    print(f"[lich_quet] {chu}", flush=True)


def _co_quyen() -> bool:
    """Tiến trình này đang giữ quyền chủ việc nền (bản Mark thừa thì không nhận lịch)."""
    import viec_nen
    return viec_nen.con_quyen()


def _duoc_chay() -> tuple[bool, str]:
    """Công tắc Soi tài khoản — y như `/theodoi` gõ tay (`lenh_cung`)."""
    import lenh_cung
    return lenh_cung._duoc_khong("soi_tai_khoan")


def _iso(x) -> str | None:
    return x.astimezone(VN).isoformat(timespec="seconds") if x else None


def _ket_qua(row: dict, trang_thai: str, ly_do: str, bay_gio, **them) -> dict:
    """`ket_qua_cuoi` mới; mang theo dấu cảnh báo đã gửi của kết quả cũ (khỏi gửi lại trong ngày)."""
    cu = row.get("ket_qua_cuoi") if isinstance(row.get("ket_qua_cuoi"), dict) else {}
    kq = {"trang_thai": trang_thai, "ly_do": str(ly_do or "")[:300], "luc": _iso(bay_gio),
          **{k: v for k, v in them.items() if v is not None}}
    if isinstance(cu.get("canh_bao"), dict):
        kq["canh_bao"] = dict(cu["canh_bao"])
    return kq


# ───────────────────────────── quyết định (thuần) ─────────────────────────────
def quyet(row: dict, bay_gio: datetime.datetime, chien_dich: dict[str, dict]) -> dict:
    """Quyết định cho MỘT lịch tới hạn — chạy trong giao dịch nhận lịch, không gọi mạng.
    -> {"lan_chay_ke", "hanh_dong": chay|lo|nhuong|loi, [moc], [lan_chay_cuoi, ket_qua_cuoi]}."""
    try:
        chay, lo, ke = LQ.quyet_dinh(row.get("kieu") or "", row.get("cau_hinh") or {},
                                     row.get("lan_chay_ke"), bay_gio)
    except Exception as e:  # noqa: BLE001 — cấu hình hỏng: dừng lịch, chờ sửa trên dashboard
        return {"lan_chay_ke": None, "lan_chay_cuoi": bay_gio, "hanh_dong": "loi",
                "ket_qua_cuoi": _ket_qua(row, "loi", f"cấu hình lịch hỏng ({type(e).__name__})"
                                         " — sửa lịch trên dashboard", bay_gio, ma_loi="loi")}
    q = {"lan_chay_ke": ke}
    if chay is None:
        return {**q, "hanh_dong": "lo", "lan_chay_cuoi": bay_gio, "ket_qua_cuoi": _ket_qua(
            row, "bo_qua", f"lỡ mốc {lo.astimezone(VN):%d/%m %H:%M} quá 30 phút (Mark không "
            "chạy lúc đó) — đợi mốc kế", bay_gio, ma_loi="lo", moc=_iso(lo))}
    cd = chien_dich.get(row.get("du_an"))
    if row.get("kieu") != "chien_dich" and cd and cd.get("id") != row.get("id"):
        return {**q, "hanh_dong": "nhuong", "lan_chay_cuoi": bay_gio, "ket_qua_cuoi": _ket_qua(
            row, "bo_qua", f"nhường chiến dịch #{cd.get('id')} đang chạy", bay_gio,
            ma_loi="nhuong", moc=_iso(chay))}
    return {**q, "hanh_dong": "chay", "moc": chay}


# ───────────────────────────── cảnh báo tuỳ chọn ─────────────────────────────
def _dich_canh_bao() -> str:
    d = (os.environ.get("MARK_LICH_QUET_BAO_LOI") or "").strip()
    return d if re.fullmatch(r"(ou_|oc_|lark:[A-Za-z0-9_-]+:oc_)[A-Za-z0-9_-]+", d) else ""


def _gui(dich: str, van: str, uid: str) -> None:
    if dich.startswith("ou_"):
        import lark_client
        lark_client.send_text("open_id", dich, van, uuid=uid)
    else:
        import scheduler
        scheduler._gui(dich, van, uid)


def _canh_bao(row: dict, kq: dict, bay_gio) -> dict:
    """Lỗi / hết ngân sách + có nơi nhận: gửi MỘT tin mỗi lịch mỗi loại mỗi ngày (ghi dấu ngày
    vào kq["canh_bao"]). Không có nơi nhận thì chỉ ghi kết quả. Không bao giờ ném."""
    loai = "loi" if kq.get("trang_thai") == "loi" else (
        "het_ngan_sach" if kq.get("ma_loi") in ("het_ngan_sach", "het_ngan_sach_apify") else "")
    dich = _dich_canh_bao()
    if not loai or not dich:
        return kq
    ngay = bay_gio.astimezone(VN).strftime("%Y-%m-%d")
    da = kq.get("canh_bao") if isinstance(kq.get("canh_bao"), dict) else {}
    if da.get(loai) == ngay:
        return kq
    du_an = str(row.get("du_an") or "")
    van = (f"Lịch quét #{row.get('id')} ({row.get('ten') or LQ.KIEU.get(row.get('kieu'), '')}) "
           f"của dự án {du_an}: {CANH_BAO[loai]} — {kq.get('ly_do') or ''}. Xem/sửa: "
           f"social.hapas.vn/lich-quet?du_an={du_an}")[:900]
    try:
        _gui(dich, van, f"lichq-{row.get('id')}-{loai}-{ngay.replace('-', '')}"[:50])
    except Exception as e:  # noqa: BLE001 — gửi hỏng: kết quả vẫn ghi, lần sau thử lại
        _bao_mot_lan(f"gui-{loai}-{ngay}", f"không gửi được cảnh báo lịch: {type(e).__name__}")
        return kq
    return {**kq, "canh_bao": {**da, loai: ngay}}


# ───────────────────────────── chạy một lịch ─────────────────────────────
def _chay(row: dict, moc: datetime.datetime, bay_gio: datetime.datetime) -> dict:
    """Tạo việc `/theodoi` cho một mốc đã nhận; ghi kết quả vào lịch. -> tóm tắt cho log/test."""
    lid, ma = int(row["id"]), str(row["du_an"])
    cho, ly = _duoc_chay()
    if not cho:
        kq = {"ok": False, "ma_loi": "nang_luc_tat",
              "cau": f"công tắc Soi tài khoản không cho chạy: {ly or 'đang tắt'}"}
    else:
        try:
            import theo_doi
            kq = theo_doi.tao_luot(ma, moi_nguon=bool(row.get("quet_moi_nguon")),
                                   lich={"id": lid, "moc": _iso(moc)})
        except Exception as e:  # noqa: BLE001 — một lịch hỏng không làm hỏng nhịp
            kq = {"ok": False, "ma_loi": "loi", "cau": f"lỗi khi tạo việc ({type(e).__name__})"}
    if kq.get("ok"):
        ket = _ket_qua(row, "da_tao", kq.get("cau") or "", bay_gio, ma_viec=kq.get("ma_viec"),
                       moc=_iso(moc), uoc_usd=kq.get("uoc_usd"), so_nguon=kq.get("so_nguon"))
    else:
        ma_loi = str(kq.get("ma_loi") or "loi")
        ket = _ket_qua(row, "bo_qua" if ma_loi in BO_QUA else "loi", kq.get("cau") or "",
                       bay_gio, ma_loi=ma_loi, moc=_iso(moc), ma_viec_cu=kq.get("ma_viec"))
    ket = _canh_bao(row, ket, bay_gio)
    try:
        K.ghi_ket_qua_lich(lid, ket, lan_chay_cuoi=bay_gio, tang_so_lan=bool(kq.get("ok")))
    except K.LoiKho as e:
        _bao_mot_lan(f"ghi-{type(e).__name__}", f"không ghi được kết quả lịch: {e}")
    print(f"[lich_quet] #{lid} {ma} mốc {moc.astimezone(VN):%d/%m %H:%M}: {ket['trang_thai']}"
          + (f" {kq.get('ma_viec')}" if kq.get("ok") else f" ({ket.get('ma_loi')})"), flush=True)
    return {"id": lid, "hanh_dong": ket["trang_thai"], "ma_loi": ket.get("ma_loi"),
            "ma_viec": kq.get("ma_viec") if kq.get("ok") else None}


def mot_nhip(bay_gio: datetime.datetime | None = None) -> list[dict]:
    """Một nhịp: nhận lịch tới hạn, ghi mốc kế, rồi tạo việc. Không bao giờ ném.
    -> [{"id", "hanh_dong", …}] (để kiểm thử và log)."""
    ra: list[dict] = []
    try:
        if not bat() or not _co_quyen():
            return ra
        bay_gio = bay_gio or _bay_gio()
        theo_du_an: dict[str, list[dict]] = {}
        for x in K.lich_dang_bat():
            theo_du_an.setdefault(str(x.get("du_an")), []).append(x)
        chien_dich = {ma: cd for ma, ds in theo_du_an.items()
                      if (cd := LQ.chien_dich_dang_chay(ds, bay_gio))}
        nhan = K.nhan_lich_den_han(bay_gio, lambda r: quyet(r, bay_gio, chien_dich),
                                   TOI_DA_MOI_NHIP)
        for row, q in nhan:
            if q.get("hanh_dong") == "chay":
                ra.append(_chay(row, q["moc"], bay_gio))
                continue
            kq = q.get("ket_qua_cuoi") or {}
            print(f"[lich_quet] #{row.get('id')} {row.get('du_an')}: bỏ qua — "
                  f"{kq.get('ly_do', '')}", flush=True)
            ra.append({"id": row.get("id"), "hanh_dong": q.get("hanh_dong"),
                       "ma_loi": kq.get("ma_loi")})
    except K.LoiKho as e:
        _bao_mot_lan(f"kho-{e}", f"kho lắng nghe chưa dùng được, lịch tạm dừng: {e}")
    except Exception as e:  # noqa: BLE001 — nhịp không bao giờ làm chết Mark
        _bao_mot_lan(f"loi-{type(e).__name__}", f"lỗi nhịp lịch quét: {type(e).__name__}: {e}")
    return ra


def ket_thuc_viec(lid: int, ma_viec: str, luot_id, trang_thai: str, van_ban: str) -> None:
    """Gọi khi việc theo dõi do lịch giao chạy xong (`theo_doi.chay_viec`): ghi trạng thái cuối
    (chỉ khi kết quả đang lưu vẫn là của việc này) và cảnh báo nếu lỗi. Không bao giờ ném."""
    try:
        row = K.doc_lich(int(lid))
        cu = (row or {}).get("ket_qua_cuoi") if isinstance((row or {}).get("ket_qua_cuoi"),
                                                           dict) else None
        if not row or not cu or cu.get("ma_viec") != ma_viec:
            return
        tt = {"xong_mot_phan": "mot_phan"}.get(trang_thai, trang_thai)
        bay_gio = _bay_gio()
        kq = {**cu, "trang_thai": tt, "luot_id": luot_id, "xong_luc": _iso(bay_gio)}
        if tt == "loi":
            kq.update(ly_do=str(van_ban or "")[:300], ma_loi="loi")
            kq = _canh_bao(row, kq, bay_gio)
        K.ghi_ket_qua_lich(int(lid), kq, chi_khi_ma_viec=ma_viec)
    except Exception as e:  # noqa: BLE001
        _bao_mot_lan(f"xong-{type(e).__name__}", f"không ghi được kết quả cuối của lịch: "
                     f"{type(e).__name__}")


def khoi_dong(nhip: int = NHIP) -> str:
    """Gọi MỘT lần từ run.py (sau `viec_nen.khoi_dong`). Trả dòng trạng thái để in."""
    if not bat():
        return "Lịch quét:  ⛔ tắt (MARK_LICH_QUET=0)"
    import importlib.util
    if importlib.util.find_spec("psycopg") is None:
        return "Lịch quét:  ⛔ máy chưa cài psycopg (kho lắng nghe chưa bật)"
    t = _LUONG.get("t")
    if t is None or not t.is_alive():
        def vong():
            while True:
                mot_nhip()
                time.sleep(nhip)
        _LUONG["t"] = threading.Thread(target=vong, name="lich-quet", daemon=True)
        _LUONG["t"].start()
    return (f"Lịch quét:  ✅ nhịp {nhip}s · lịch đặt trên dashboard (tab Lịch quét) · "
            + ("cảnh báo lỗi/hết ngân sách → " + _dich_canh_bao()[:12] + "…"
               if _dich_canh_bao() else "không nhắn Lark (chưa đặt MARK_LICH_QUET_BAO_LOI)"))
