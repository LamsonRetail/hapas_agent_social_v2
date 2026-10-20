"""Kho yêu cầu XUẤT LARK SHEET quảng cáo (20/10/2026) — SQL của bảng `yeu_cau_sheet_qc`.

Chủ dự án 20/10/2026: trên trang Quảng cáo (chỉ quản trị viên) có mục "Tạo Lark Sheet" — xuất số
TikTok (và Meta, cùng bảng qc_*) theo ĐÚNG bộ lọc trang thành một Lark Sheet ba tab: theo ngày ×
tài khoản, theo chiến dịch, theo quảng cáo (tổng cả kỳ).

Vì sao qua hàng chờ: dashboard KHÔNG giữ app Lark tạo được Sheet (chỉ DASH_LARK_APP_* để đăng nhập,
không thêm quyền Sheet). App Lark của Mark tạo Sheet → dashboard chỉ THÊM một dòng (phạm vi + email
người bấm); bộ nghe `xuat_sheet_qc.py` (user mark, `.env` của Mark, role mark đọc được cột tiền của
qc_*) nhận qua pg_notify('qc_sheet') — trigger `yeu_cau_sheet_qc_bao` — và quét dòng chờ mỗi phút.

Quyền (schema.sql): lang_nghe_web chỉ INSERT cột phạm vi + SELECT cột trạng thái, và RLS chỉ cho
dòng của người đang đăng nhập (`lang_nghe.nguoi`, đặt bằng `_la` trong CÙNG giao dịch); trạng thái
lúc thêm + trần do trigger `yeu_cau_sheet_qc_chuan` đặt / kiểm. Role mark đọc mọi dòng, chỉ sửa cột
kết quả, không thêm.

Hàm dashboard gọi (lang_nghe_web): `tao`, `gan_day`. Hàm bộ nghe gọi (role mark — tiến trình
`xuat_sheet_qc` đổi `kho._dsn` sang DSN của Mark): `nhan`, `ket_thuc`, `da_nhan_tin`, `don_dep`,
`ten_ben`, `doc_theo_ngay`, `doc_tong`. Chỉ SQL tham số hoá.
"""
from __future__ import annotations

import datetime
import json

from dashboard import quang_cao as QC
from dashboard.kho import LoiDuLieu, ket_noi

KENH = "qc_sheet"                  # kênh LISTEN/NOTIFY (trigger trong schema.sql)
TRANG_THAI = ("cho", "dang_tao", "xong", "loi")
GUC = "lang_nghe.nguoi"            # RLS của lang_nghe_web (schema.sql: sheet_qc_*_web)
TRAN_GIO = 4                       # yêu cầu mỗi người mỗi 60 phút (= trigger)
QUA_HAN_PHUT = 30                  # chờ / đang tạo quá chừng này → coi như hỏng (không chặn nữa)
#: Trần dòng mỗi tab (trinh_bay_sheet nới lưới tới 20.000 dòng; tab quảng cáo hay lớn nhất).
TRAN_DONG = {"ngay": 20_000, "chien_dich": 5_000, "quang_cao": 10_000}
HANH_DONG = "tao_sheet_qc"
_COT_WEB = ("id, nguoi_hoi, ben, nen_tang, tk, tu, den, trang_thai, tieu_de, sheet_url, so_dong, "
            "loi, da_nhan_tin, tao_luc, bat_dau_luc, xong_luc")
_COT_MARK = _COT_WEB + ", loi_noi_bo"
#: Câu khi chính trigger từ chối (trần chung toàn hệ thống — app không đếm được dòng người khác).
CAU_TRAN_CHUNG = ("Chưa nhận thêm yêu cầu — đã đủ trần tạo Sheet chung mỗi giờ hoặc bạn vừa có "
                  "Sheet đang tạo. Thử lại sau ít phút.")


def _la(c, email: str) -> str:
    """Đặt người đang thao tác cho RLS (chỉ trong giao dịch này)."""
    e = str(email or "").strip().lower()[:254]
    c.execute("SELECT set_config(%s, %s, true)", (GUC, e))
    return e


def ly_do_chan(dang: int, trong_gio: int, tran: int = TRAN_GIO) -> str | None:
    """Câu từ chối cho người bấm (cùng luật trigger) — None = được tạo."""
    if dang:
        return "Bạn đang có một Sheet đang tạo — đợi xong (thường 1–2 phút) rồi tạo tiếp."
    if trong_gio >= tran:
        return f"Mỗi người tạo tối đa {tran} Sheet mỗi giờ — thử lại sau."
    return None


# ───────────────────────────── phía dashboard (lang_nghe_web) ─────────────────────────────
def tao(nguoi_hoi: str, ben: str, nen_tang: str, tk: str | None, tu: datetime.date,
        den: datetime.date, *, tran_gio: int = TRAN_GIO) -> dict:
    """Thêm MỘT yêu cầu (trạng thái do trigger đặt). Trần kiểm NGUYÊN TỬ dưới cùng khoá advisory
    với trigger. Vượt trần → LoiDuLieu (câu cho người bấm). -> dòng vừa thêm (cột web đọc được)."""
    with ket_noi() as c:
        e = _la(c, nguoi_hoi)
        c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("sheet_qc|" + e,))
        r = c.execute(
            "SELECT count(*) FILTER (WHERE (trang_thai = 'cho' AND tao_luc > now() - "
            "make_interval(mins => %s::int)) OR (trang_thai = 'dang_tao' AND bat_dau_luc > now() - "
            "make_interval(mins => %s::int)))::int AS dang, count(*) FILTER (WHERE tao_luc > now() "
            "- interval '1 hour')::int AS gio FROM yeu_cau_sheet_qc WHERE nguoi_hoi = %s",
            (QUA_HAN_PHUT, QUA_HAN_PHUT, e)).fetchone() or {}
        ly = ly_do_chan(int(r.get("dang") or 0), int(r.get("gio") or 0), tran_gio)
        if ly:
            raise LoiDuLieu(ly)
        try:
            return c.execute(
                f"INSERT INTO yeu_cau_sheet_qc (nguoi_hoi, ben, nen_tang, tk, tu, den) "
                f"VALUES (%s, %s, %s, %s, %s, %s) RETURNING {_COT_WEB}",
                (e, ben, nen_tang, tk or None, tu, den)).fetchone()
        except Exception as x:  # noqa: BLE001 — CheckViolation của trigger (trần chung)
            if type(x).__name__ == "CheckViolation":
                raise LoiDuLieu(CAU_TRAN_CHUNG) from None
            raise


def gan_day(nguoi_hoi: str, n: int = 5) -> list[dict]:
    """Yêu cầu gần nhất của CHÍNH người này (RLS chỉ cho dòng của họ)."""
    with ket_noi() as c:
        e = _la(c, nguoi_hoi)
        return c.execute(f"SELECT {_COT_WEB} FROM yeu_cau_sheet_qc WHERE nguoi_hoi = %s "
                         "ORDER BY id DESC LIMIT %s", (e, max(1, min(int(n), 20)))).fetchall()


def hien_trang(r: dict, bay: datetime.datetime | None = None) -> str:
    """Trạng thái để HIỂN THỊ: chờ / đang tạo quá QUA_HAN_PHUT (bộ nghe chưa chạy hoặc chết giữa
    chừng — dòng chưa kịp được dọn) hiện là "qua_han" thay vì quay mãi."""
    tt = str(r.get("trang_thai") or "")
    if tt not in ("cho", "dang_tao"):
        return tt
    bay = bay or datetime.datetime.now(datetime.UTC)
    moc = r.get("bat_dau_luc") if tt == "dang_tao" else r.get("tao_luc")
    if isinstance(moc, datetime.datetime):
        if moc.tzinfo is None:
            moc = moc.replace(tzinfo=datetime.UTC)
        if bay - moc > datetime.timedelta(minutes=QUA_HAN_PHUT):
            return "qua_han"
    return tt


# ───────────────────────────── phía bộ nghe (role mark) ─────────────────────────────
def nhan() -> dict | None:
    """Nhận yêu cầu chờ CŨ NHẤT (FOR UPDATE SKIP LOCKED — hai tiến trình không nhận trùng) → đặt
    dang_tao. Mỗi lần một yêu cầu: dựng Sheet tuần tự, không dồn Lark API."""
    with ket_noi() as c:
        return c.execute(
            f"UPDATE yeu_cau_sheet_qc SET trang_thai = 'dang_tao', bat_dau_luc = now() "
            f"WHERE id = (SELECT id FROM yeu_cau_sheet_qc WHERE trang_thai = 'cho' ORDER BY id "
            f"LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING {_COT_MARK}").fetchone()


def ket_thuc(yid: int, trang_thai: str, *, tieu_de: str | None = None,
             sheet_url: str | None = None, so_dong: dict | None = None, loi: str | None = None,
             loi_noi_bo: str | None = None) -> None:
    if trang_thai not in ("xong", "loi"):
        raise ValueError("trạng thái kết thúc phải là xong hoặc loi")
    with ket_noi() as c:
        c.execute("UPDATE yeu_cau_sheet_qc SET trang_thai = %s, tieu_de = %s, sheet_url = %s, "
                  "so_dong = %s::jsonb, loi = %s, loi_noi_bo = %s, xong_luc = now() WHERE id = %s",
                  (trang_thai, (tieu_de or None) and str(tieu_de)[:300], sheet_url or None,
                   json.dumps(so_dong or {}, ensure_ascii=False, default=str),
                   (loi or None) and str(loi)[:300], (loi_noi_bo or None) and str(loi_noi_bo)[:500],
                   int(yid)))


def da_nhan_tin(yid: int) -> None:
    with ket_noi() as c:
        c.execute("UPDATE yeu_cau_sheet_qc SET da_nhan_tin = TRUE WHERE id = %s", (int(yid),))


def don_dep(phut: int = QUA_HAN_PHUT) -> int:
    """Chờ quá `phut` phút (bộ nghe đã dừng lâu) / đang tạo quá `phut` phút (chết giữa chừng) → loi.
    -> số dòng đổi."""
    with ket_noi() as c:
        return int(c.execute(
            "UPDATE yeu_cau_sheet_qc SET trang_thai = 'loi', xong_luc = now(), loi = CASE WHEN "
            "trang_thai = 'cho' THEN 'quá hạn chờ — dịch vụ tạo Sheet chưa nhận, bấm tạo lại' ELSE "
            "'dừng giữa chừng — bấm tạo lại' END WHERE (trang_thai = 'cho' AND tao_luc < now() - "
            "make_interval(mins => %s::int)) OR (trang_thai = 'dang_tao' AND bat_dau_luc < now() - "
            "make_interval(mins => %s::int))", (int(phut), int(phut))).rowcount or 0)


def ten_ben() -> dict[str, str]:
    with ket_noi() as c:
        return {r["ma"]: r["ten"] for r in c.execute("SELECT ma, ten FROM don_vi").fetchall()}


_TONG = ", ".join(f"sum({c})::float AS {c}" if c in QC.COT_TIEN else f"sum({c})::bigint AS {c}"
                  for c in QC.TEN_COT_SO)
#: Đọc cả kỳ dài (≤ 400 ngày × cấp quảng cáo) có thể lâu hơn trần 20 giây của trang.
_GIAY_DOC = "120s"


def doc_theo_ngay(ids: list[str], tu: datetime.date, den: datetime.date,
                  toi_da: int = TRAN_DONG["ngay"]) -> dict:
    """Tab (a): mỗi tài khoản × ngày một dòng (qc_tk_ngay). -> {"rows", "tong"} (tong = số dòng
    trước trần)."""
    if not ids:
        return {"rows": [], "tong": 0}
    with ket_noi() as c:
        c.execute(f"SET LOCAL statement_timeout = '{_GIAY_DOC}'")
        rows = c.execute(
            f"SELECT advertiser_id, ngay, {', '.join(QC.TEN_COT_SO)}, count(*) OVER () AS tong "
            "FROM qc_tk_ngay WHERE advertiser_id = ANY(%s) AND ngay BETWEEN %s AND %s "
            "ORDER BY ngay, advertiser_id LIMIT %s", (list(ids), tu, den, int(toi_da))).fetchall()
    return {"rows": [{k: v for k, v in r.items() if k != "tong"} for r in rows],
            "tong": int(rows[0]["tong"]) if rows else 0}


#: Cấp → (bảng, khoá, cột tên lấy từ NGÀY MỚI NHẤT của mỗi đối tượng trong kỳ).
_CAP = {"chien_dich": ("qc_campaign_ngay", "campaign_id", ("ten", "muc_tieu")),
        "quang_cao": ("qc_ad_ngay", "ad_id", ("campaign_id", "adgroup_id", "ten_ad",
                                              "left(noi_dung, 300) AS noi_dung", "ten_campaign",
                                              "ten_nhom"))}


def doc_tong(cap: str, ids: list[str], tu: datetime.date, den: datetime.date,
             toi_da: int | None = None) -> dict:
    """Tab (b)/(c): tổng cả kỳ của từng chiến dịch / quảng cáo (nhóm theo mã + tài khoản), xếp chi
    giảm dần rồi hiển thị; ≤ `toi_da` dòng. -> {"rows", "tong"} (tong = số đối tượng trước trần)."""
    if cap not in _CAP or not ids:
        return {"rows": [], "tong": 0}
    bang, khoa, ten = _CAP[cap]
    toi_da = int(toi_da or TRAN_DONG[cap])
    pp = "(COALESCE(hien_thi, 0) > 0 OR COALESCE(chi, 0) > 0)"
    with ket_noi() as c:
        c.execute(f"SET LOCAL statement_timeout = '{_GIAY_DOC}'")
        rows = c.execute(
            f"SELECT {khoa}, advertiser_id, {_TONG}, count(DISTINCT ngay) FILTER (WHERE {pp}) "
            f"AS so_ngay, count(*) OVER () AS tong FROM {bang} WHERE advertiser_id = ANY(%s) "
            f"AND ngay BETWEEN %s AND %s GROUP BY {khoa}, advertiser_id "
            f"ORDER BY chi DESC NULLS LAST, hien_thi DESC NULLS LAST, {khoa} LIMIT %s",
            (list(ids), tu, den, toi_da)).fetchall()
        if not rows:
            return {"rows": [], "tong": 0}
        moi = {r[khoa]: r for r in c.execute(
            f"SELECT DISTINCT ON ({khoa}) {khoa}, {', '.join(ten)} FROM {bang} "
            f"WHERE {khoa} = ANY(%s) AND advertiser_id = ANY(%s) AND ngay BETWEEN %s AND %s "
            f"ORDER BY {khoa}, ngay DESC", ([r[khoa] for r in rows], list(ids), tu, den)
        ).fetchall()}
    return {"rows": [{**{k: v for k, v in r.items() if k != "tong"},
                      **{k: v for k, v in (moi.get(r[khoa]) or {}).items() if k != khoa}}
                     for r in rows],
            "tong": int(rows[0]["tong"])}
