"""Bộ NGHE yêu cầu số quảng cáo tức thì (20/10/2026) — chạy lâu dài, mỗi nhà cung cấp một tiến trình
(`tiktok-ads-nghe.service`, `meta-ads-nghe.service`, user lang_nghe_web, Restart=always).

Vì sao: chủ dự án 20/10/2026 muốn Mark "cào real time theo yêu cầu". Mark KHÔNG BAO GIỜ cầm token
quảng cáo (role `mark` không đọc được cột token, máy Mark không có TIKTOK_KHOA_MA_HOA) nên Mark chỉ
thêm một dòng `yeu_cau_tuc_thi` (loai quang_cao: tài khoản trong phạm vi người hỏi + khoảng ≤ 7
ngày). Trigger của bảng gọi `pg_notify('qc_tuc_thi', <nhà cung cấp>)`; tiến trình này LISTEN kênh
đó nên nhận gần như ngay (thay cho chờ bộ hẹn giờ 2 phút), rồi chạy đúng lượt đọc của dịch vụ
đồng bộ (`DichVu.dong_bo_tai_khoan`: chỉ GET / công cụ đọc, khoá advisory chung với lượt hằng
ngày). Bộ hẹn giờ `*-ads-yeu-cau` (2 phút) vẫn quét dòng chờ — dự phòng khi bộ nghe chết.

Trần phía dịch vụ (Mark có trần riêng trước khi xin, đây là chốt thứ hai — không tin đầu kia):
  • `QC_TUC_THI_TRAN_GIO` (mặc định 12) lượt đọc tức thì mỗi nhà cung cấp mỗi giờ; quá thì yêu
    cầu chờ thành bo_qua (Mark trả lời bằng số đã có).
  • Yêu cầu chờ quá 15 phút → bo_qua; đang chạy quá 60 phút → loi (`kho_tuc_thi.don_dep`).
  • Nhiều yêu cầu chờ cùng lúc → GỘP một lượt (hợp tài khoản, khoảng rộng nhất).
  • Khung đồng bộ hằng ngày 06:25–07:30 giờ VN (`quang_cao.trong_gio_dong_bo`, soát H2): KHÔNG mở
    lượt nào — yêu cầu chờ thành bo_qua (Mark trả số đã có, nói đồng bộ hằng ngày đang chạy), cờ
    nhanh của dashboard đợi sau 07:30. Lượt hằng ngày tự chờ khoá (tối đa 30 phút) nếu lượt nhỏ
    đang chạy.
  • Lượt đọc không đọc được tài khoản nào → loi / bo_qua (không bao giờ "xong"); đọc được một
    phần → xong + `so_tk_ok` < số tài khoản xin + lỗi (soát M1).
Đồng thời nhận cờ "Đồng bộ ngay" loại NHANH của dashboard (kho_qc.yeu_cau_dong_bo cũng NOTIFY) — CHỈ
lượt nhanh (`dong_bo(chi_nhanh=True)`: câu UPDATE bắt đầu lượt chỉ khớp khi cờ đang chờ là nhanh);
lượt đầy đủ của quản trị viên để bộ hẹn giờ chạy, bộ nghe không bao giờ bị giữ hàng giờ (L4).
Không chạy được (khoá bận, chưa kết nối, thiếu khoá giải mã) → CHỜ thông báo / hết giờ chờ, không
quay vòng (soát H1).

Chạy tay: `python -m dashboard.nghe_qc tiktok_ads` (hoặc meta_ads); `--mot-lan` xử lý hàng chờ
một lần rồi thoát.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import time

from dashboard import quang_cao as QC

KENH = "qc_tuc_thi"
NCC = ("tiktok_ads", "meta_ads")
CHO_GIAY = 60          # không có thông báo: vẫn tỉnh dậy mỗi 60 giây (dọn hàng chờ, dự phòng)
NGHI_BAN = 20          # lượt đồng bộ khác đang giữ khoá: nghỉ rồi thử lại
NGHI_LOI = 10          # mất kết nối Postgres: nghỉ rồi nối lại


def tran_gio() -> int:
    try:
        v = int(os.environ.get("QC_TUC_THI_TRAN_GIO") or 12)
    except ValueError:
        v = 12
    return max(1, min(v, 60))


def _gon(e: Exception) -> str:
    from dashboard import tiktok_ads as TA
    return f"{type(e).__name__}: {TA.gon_loi(e)}"[:300]


def _bay(dv) -> datetime.datetime:
    f = getattr(dv, "_bay_gio", None)
    return f() if callable(f) else datetime.datetime.now(datetime.UTC)


def ket_luan(kq: dict, so_xin: int) -> tuple[str, str | None]:
    """(trạng thái, lỗi) cho MỘT yêu cầu (soát M1/N1 — gọi với số của CHÍNH dòng đó): không đọc
    được tài khoản nào → loi (có lỗi) / bo_qua (không có gì để đọc); đọc thiếu → xong + "một
    phần"."""
    ok = int(kq.get("so_tk") or 0)
    loi = kq.get("loi")
    if ok == 0:
        if loi:
            return "loi", loi
        return "bo_qua", "không có tài khoản nào đọc lại được (ngoài cửa sổ 7 ngày / tắt đồng bộ)"
    if ok < so_xin:
        return "xong", f"một phần: đọc được {ok}/{so_xin} tài khoản" + (f" — {loi}" if loi else "")
    return "xong", loi


def xu_ly_cho(ncc: str, dv, kho_tt=None, *, log=print) -> dict:
    """Xử lý MỘT lần hàng chờ quảng cáo tức thì của `ncc`. Không bao giờ để yêu cầu kẹt ở
    dang_chay: lượt khác giữ khoá → trả về hàng chờ; lỗi → loi kèm chữ lỗi đã bỏ token."""
    if kho_tt is None:
        from dashboard import kho_tuc_thi as kho_tt
    kho_tt.don_dep(ncc)
    ly_bo = None
    if QC.trong_gio_dong_bo(_bay(dv)):
        ly_bo = QC.CAU_GIO_DONG_BO
    else:
        tran = tran_gio()
        if kho_tt.dem_chay_gio(ncc) >= tran:
            ly_bo = (f"đã đủ {tran} lượt đọc tức thì trong 60 phút qua (trần chống bị nền tảng "
                     "chặn) — trả lời bằng số đã có")
    if ly_bo:
        rows = kho_tt.nhan_qc(ncc)
        if rows:
            kho_tt.ket_thuc([r["id"] for r in rows], "bo_qua", loi=ly_bo)
            log(f"[nghe_qc] {ncc}: bỏ {len(rows)} yêu cầu — {ly_bo}")
            return {"bo_qua": ly_bo, "so_yeu_cau": len(rows)}
        return {"khong_co": True}
    rows = kho_tt.nhan_qc(ncc)
    if not rows:
        return {"khong_co": True}
    ids = [r["id"] for r in rows]
    tk = sorted({str(x) for r in rows for x in (r.get("tai_khoan") or [])})
    tu = min((r["tu"] for r in rows if r.get("tu")), default=None)
    den = max((r["den"] for r in rows if r.get("den")), default=None)
    try:
        kq = dv.dong_bo_tai_khoan(tk, tu, den)
    except Exception as e:  # noqa: BLE001 — luôn kết thúc yêu cầu, rồi báo
        kho_tt.ket_thuc(ids, "loi", so_tk_ok=0, loi=_gon(e))
        log(f"[nghe_qc] {ncc}: lỗi {_gon(e)}")
        return {"loi": _gon(e), "so_yeu_cau": len(ids)}
    if kq.get("ban"):
        kho_tt.tra_lai(ids)
        return {"ban": True, "so_yeu_cau": len(ids)}
    if kq.get("bo_qua"):
        kho_tt.ket_thuc(ids, "bo_qua", so_tk_ok=0, loi=kq["bo_qua"])
    else:
        ket_thuc_tung_dong(kho_tt, rows, kq)
        day_bq(kq, log)
    log(f"[nghe_qc] {ncc}: {len(ids)} yêu cầu, {kq.get('so_tk', 0)}/{len(tk)} tài khoản, "
        f"{tu}→{den}: {kq.get('so_dong', 0)} dòng"
        + (f", lỗi: {kq['loi']}" if kq.get("loi") else ""))
    return {**kq, "so_yeu_cau": len(ids)}


def ket_thuc_tung_dong(kho_tt, rows: list[dict], kq: dict) -> None:
    """Lượt gộp nhiều yêu cầu (soát N1): mỗi dòng nhận ĐÚNG số của tài khoản CỦA NÓ — đọc được =
    tài khoản của dòng ∩ `tk_doc`; lỗi = `tk_hong` của tài khoản dòng đó. Người có 3 tài khoản
    hỏng không bao giờ nhận "đủ"."""
    doc = {str(x) for x in kq.get("tk_doc") or []}
    hong = {str(k): v for k, v in (kq.get("tk_hong") or {}).items()}
    for r in rows:
        cua = sorted({str(x) for x in r.get("tai_khoan") or []})
        ok = [a for a in cua if a in doc]
        loi_dong = {a: hong.get(a) or kq.get("loi") or "không đọc được" for a in cua
                    if a not in doc}
        loi = "; ".join(f"{a}: {v}" for a, v in loi_dong.items())[:500] or None
        tt, ly = ket_luan({"so_tk": len(ok), "loi": loi}, len(cua))
        kho_tt.ket_thuc([r["id"]], tt, so_dong=int(kq.get("so_dong") or 0), so_tk_ok=len(ok),
                        loi=ly, chi_tiet_them={"tk_doc": ok, "tk_hong": loi_dong})


#: Đẩy BigQuery sau lượt của bộ nghe (soát L-b) — tối đa mỗi `BQ_GIAN_GIAY` giây một lần (quota cập
#: nhật bảng của BigQuery: 5 lần / 10 giây mỗi bảng; lượt Mark có thể dồn dập).
BQ_GIAN_GIAY = 600.0
_BQ = {"luc": float("-inf")}


def day_bq(kq: dict, log=print, *, dong_bo_bq=None, dong_ho=time.monotonic) -> bool:
    """Lượt có ghi dòng → đẩy BigQuery như đường bộ hẹn giờ (`dong_bo_bq.chay`), giãn 10 phút. Lỗi
    chỉ ghi log (BigQuery còn nhịp 6 giờ của dashboard). -> có đẩy hay không."""
    if not kq.get("so_dong"):
        return False
    bay = dong_ho()
    if bay - _BQ["luc"] < BQ_GIAN_GIAY:
        return False
    if dong_bo_bq is None:
        from dashboard import dong_bo_bq
    if not dong_bo_bq.da_bat():
        return False
    _BQ["luc"] = bay
    try:
        dong_bo_bq.chay()
        return True
    except Exception as e:  # noqa: BLE001
        log(f"[nghe_qc] BigQuery lỗi: {type(e).__name__}")
        return False


def xu_ly_co_nhanh(ncc: str, dv, *, log=print) -> dict | None:
    """Cờ "Đồng bộ ngay" loại NHANH của dashboard đang chờ → chạy lượt đó ngay (3 ngày, tài khoản
    có chạy) — CHỈ lượt nhanh (`chi_nhanh`), không trong khung đồng bộ hằng ngày. -> kết quả lượt
    hoặc None (không có gì / không phải lúc)."""
    r = dv.kho.doc_ket_noi(ncc) or {}
    if not r.get("yeu_cau_dong_bo_luc") or r.get("yeu_cau_kieu") != "nhanh":
        return None
    if QC.trong_gio_dong_bo(_bay(dv)):
        return None
    kq = dv.dong_bo(theo_yeu_cau=True, chi_nhanh=True)
    log(f"[nghe_qc] {ncc}: lượt bấm tay {kq}")
    if da_chay(kq):
        day_bq(kq, log)
    return kq


def da_chay(kq: dict | None) -> bool:
    """Lượt bấm tay thật sự đã chạy (không phải bỏ qua vì khoá bận / chưa kết nối / thiếu khoá)."""
    return kq is not None and not kq.get("bo_qua") and not kq.get("ban")


def dich_vu(ncc: str):
    if ncc == "tiktok_ads":
        from dashboard import tiktok_ads as TA
        return TA.DichVu()
    from dashboard import meta_ads as MA
    return MA.DichVu()


def mo_ket_noi():
    """Kết nối RIÊNG (autocommit) cho LISTEN — không lấy từ `kho.ket_noi` (kết nối đó đóng sau mỗi
    khối with)."""
    import psycopg

    from dashboard import kho as K
    return psycopg.connect(K._dsn(), connect_timeout=5, autocommit=True)


def nghe(ncc: str, *, dv=None, kho_tt=None, mo=mo_ket_noi, log=print, ngu=time.sleep,
         vong: int | None = None, cho_giay: float = CHO_GIAY) -> None:
    """Vòng chính. `vong` (bộ thử): số lần thức dậy rồi dừng; None = mãi mãi (systemd giữ).
    Chỉ quay ngay (không chờ) khi vừa xử lý được yêu cầu hoặc vừa CHẠY một lượt bấm tay; mọi
    trường hợp khác chờ thông báo / `cho_giay` (soát H1 — không quay vòng khi khoá bận)."""
    if ncc not in NCC:
        raise ValueError(f"nhà cung cấp phải là {' / '.join(NCC)}")
    dv = dv or dich_vu(ncc)
    lan = 0
    conn = None
    while vong is None or lan < vong:
        try:
            if conn is None:
                conn = mo()
                conn.execute(f"LISTEN {KENH}")
                log(f"[nghe_qc] {ncc}: đang nghe kênh {KENH}")
            lan += 1
            kq = xu_ly_cho(ncc, dv, kho_tt, log=log)
            if kq.get("ban"):
                ngu(NGHI_BAN)
                continue
            if not kq.get("khong_co"):
                continue                       # vừa xử lý xong: xem còn gì chờ không
            if da_chay(xu_ly_co_nhanh(ncc, dv, log=log)):
                continue
            # Chờ thông báo (hoặc hết `cho_giay`) — bất kỳ thông báo nào cũng đánh thức; payload
            # chỉ là gợi ý, hàng chờ trong bảng mới là sự thật.
            for _ in conn.notifies(timeout=cho_giay, stop_after=1):
                pass
        except KeyboardInterrupt:
            break
        except Exception as e:  # noqa: BLE001 — mất kết nối / kho chưa có bảng: nghỉ rồi thử lại
            log(f"[nghe_qc] {ncc}: {_gon(e)} — thử lại sau {NGHI_LOI}s")
            _dong(conn)
            conn = None
            lan += 0 if vong is None else 1
            ngu(NGHI_LOI)
    _dong(conn)


def _dong(conn) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except Exception as e:  # noqa: BLE001 — kết nối đã hỏng: đóng không được cũng không sao
        print(f"[nghe_qc] đóng kết nối lỗi: {type(e).__name__}", file=sys.stderr)


CAU_LOI_DONG_BO = ("Lượt đồng bộ hằng ngày không xong (lượt khác giữ khoá quá lâu sau 3 lần thử, "
                   "lỗi, hoặc quá 6 giờ) — xem journalctl -u {ncc}-dong-bo; lượt sau tự đọc lại 7 "
                   "ngày / nạp lùi tiếp.")


def bao_loi_dong_bo(ncc: str, kho_qc=None) -> None:
    """OnFailure của *-ads-dong-bo (soát N2): ghi lỗi lên thẻ kết nối (trạng thái loi + lý do) để
    quản trị viên thấy — không để 3 lần thử hỏng nằm im. Chỉ khi còn token (`con_token`)."""
    if kho_qc is None:
        from dashboard import kho_qc
    kho_qc.ghi_trang_thai("loi", CAU_LOI_DONG_BO.format(ncc=ncc.replace("_", "-")), ncc,
                          con_token=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m dashboard.nghe_qc",
                                description="Nghe yêu cầu số quảng cáo tức thì của Mark.")
    p.add_argument("ncc", choices=NCC)
    p.add_argument("--mot-lan", action="store_true", help="xử lý hàng chờ một lần rồi thoát")
    p.add_argument("--bao-loi-dong-bo", action="store_true",
                   help="ghi lỗi lượt đồng bộ hằng ngày lên thẻ kết nối (OnFailure của systemd)")
    a = p.parse_args(argv)
    if a.bao_loi_dong_bo:
        try:
            bao_loi_dong_bo(a.ncc)
        except Exception as e:  # noqa: BLE001
            print(f"[nghe_qc] ghi lỗi đồng bộ hỏng: {_gon(e)}", file=sys.stderr)
            return 1
        return 0
    if a.mot_lan:
        try:
            print(f"[nghe_qc] {xu_ly_cho(a.ncc, dich_vu(a.ncc))}")
        except Exception as e:  # noqa: BLE001
            print(f"[nghe_qc] lỗi: {_gon(e)}", file=sys.stderr)
            return 1
        return 0
    nghe(a.ncc, log=lambda s: print(s, flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
