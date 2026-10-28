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
kết quả; 22/10/2026 (chủ dự án: "khi hỏi Mark thì Mark vẫn xuất Sheet được") role mark THÊM được dòng
`nguon = 'mark'` cho chính người hỏi (tool `xuat_sheet_qc` của Mark, `sheet_qc_tool.py`, gọi `tao`
với `nguon="mark"`) — cùng trigger, cùng trần, cùng khoá advisory với dòng web.

Hàm dashboard gọi (lang_nghe_web): `tao`, `gan_day`. Tool Mark gọi (role mark, qua
`hoi_dashboard_tool.KhoMark`): `tao` (nguon="mark"), `ten_ben`. Hàm bộ nghe gọi (role mark — tiến trình
`xuat_sheet_qc` đổi `kho._dsn` sang DSN của Mark): `nhan`, `ket_thuc`, `da_nhan_tin`, `don_dep`,
`ten_ben`, `doc_theo_ngay`, `doc_tong` (lọc / xếp bảng bằng SQL của `kho_qc.sql_bang`),
`ma_cd_theo_ten` (23/10/2026: lọc tên chiến dịch cấp trang, cột `ten_cd`). Chỉ SQL tham số hoá.
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
TRAN_CHUNG_GIO = 30                # dòng web toàn hệ thống mỗi giờ (= trigger, đếm nguon <> 'mark')
#: Dòng Mark toàn hệ thống mỗi giờ (soát 22/10/2026, = trigger, đếm RIÊNG nguon = 'mark'): người hỏi
#: Mark / lượt bị lừa qua lời nhắn không chiếm được trần của nút trên trang (quản trị viên).
TRAN_GIO_MARK = 15
QUA_HAN_PHUT = 30                  # chờ / đang tạo quá chừng này → coi như hỏng (không chặn nữa)
#: Trần dòng mỗi tab (trinh_bay_sheet nới lưới tới 20.000 dòng; tab quảng cáo hay lớn nhất).
TRAN_DONG = {"ngay": 20_000, "chien_dich": 5_000, "quang_cao": 10_000}
HANH_DONG = "tao_sheet_qc"
#: 23/10/2026: + ten_cd (lọc tên chiến dịch cấp trang — schema.sql cấp SELECT / INSERT cột này).
_COT_WEB = ("id, nguoi_hoi, ben, nen_tang, tk, tk_ds, tu, den, tim, cd, sap, chieu, ten_cd, "
            "trang_thai, tieu_de, sheet_url, so_dong, loi, da_nhan_tin, tao_luc, bat_dau_luc, "
            "xong_luc")
_COT_MARK = _COT_WEB + ", loi_noi_bo, nguon"
#: Cột nguon (22/10/2026): web không được cấp cột → CSDL đặt 'web'; tool Mark ghi 'mark' (RLS buộc).
NGUON = ("web", "mark")
#: 22/10/2026: cột lọc bảng (tim, cd, sap, chieu) + nhiều tài khoản (tk_ds) — trigger kiểm cùng luật
#: `quang_cao.loc_bang` / `quang_cao.tk_chon`; sai thì ném invalid_parameter_value.
CAU_LOC_SAI = "Bộ lọc không hợp lệ — tải lại trang rồi thử lại."
#: Câu khi chính trigger từ chối (trần chung toàn hệ thống — app không đếm được dòng người khác).
CAU_TRAN_MARK = ("Mark đã nhận đủ yêu cầu tạo Sheet quảng cáo trong giờ này (trần chung của Mark) "
                 "— thử lại sau ít phút, hoặc nhờ quản trị viên xuất trên trang Quảng cáo.")
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
        den: datetime.date, *, tran_gio: int = TRAN_GIO, tk_ds: list[str] | None = None,
        tim: str | None = None, cd: str | None = None, sap: str | None = None,
        chieu: str | None = None, nguon: str | None = None, ten_cd: str | None = None) -> dict:
    """Thêm MỘT yêu cầu (trạng thái do trigger đặt). Trần kiểm NGUYÊN TỬ dưới cùng khoá advisory
    với trigger. Vượt trần → LoiDuLieu (câu cho người bấm). -> dòng vừa thêm (cột web đọc được).
    22/10/2026: `tk_ds` = các tài khoản đã chọn (None = mọi tài khoản của bên + nền tảng; một mã thì
    ghi cả cột `tk` cũ), `tim` / `cd` / `sap` / `chieu` = bộ lọc bảng (`quang_cao.loc_bang`).
    `nguon` (22/10/2026): None = dòng web (cột không có trong INSERT — role web không được cấp cột,
    CSDL đặt 'web'); "mark" = tool của Mark (role mark; RLS buộc đúng 'mark'). Khoá người ở dưới
    lấy TRƯỚC khoá toàn hệ thống của trigger — cùng thứ tự cho cả hai nguồn.
    23/10/2026 (MKT): `ten_cd` = lọc tên chiến dịch cấp trang — chuỗi JSON chuẩn
    `{"co":[..],"mot":[..],"khong":[..]}` (`quang_cao.chuoi_ten_cd`, ≤ QC.TEN_CD_CHUOI_TOI_DA = trigger);
    bộ nghe tính lại chiến dịch khớp lúc dựng và áp vào MỌI tab."""
    if nguon is not None and nguon not in NGUON:
        raise ValueError("nguon phải là web hoặc mark")
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
        ds = [str(x) for x in (tk_ds or [])] or None
        cot, giu = ("", "") if nguon is None else (", nguon", ", %s")
        try:
            return c.execute(
                f"INSERT INTO yeu_cau_sheet_qc (nguoi_hoi, ben, nen_tang, tk, tk_ds, tu, den, tim, cd, "
                f"sap, chieu, ten_cd{cot}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                f"%s{giu}) RETURNING {_COT_WEB}",
                (e, ben, nen_tang, tk or (ds[0] if ds and len(ds) == 1 else None), ds, tu, den,
                 tim or None, cd or None, sap or None, chieu or None, ten_cd or None)
                + (() if nguon is None else (nguon,))).fetchone()
        except Exception as x:  # noqa: BLE001 — CheckViolation của trigger (trần chung)
            if type(x).__name__ == "CheckViolation":
                raise LoiDuLieu(CAU_TRAN_MARK if nguon == "mark" and "Mark" in str(x)
                                else CAU_TRAN_CHUNG) from None
            if type(x).__name__ == "InvalidParameterValue":
                raise LoiDuLieu(CAU_LOC_SAI) from None
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


def ket_thuc(yid: int, trang_thai: str, *, bat_dau_luc=None, tieu_de: str | None = None,
             sheet_url: str | None = None, so_dong: dict | None = None, loi: str | None = None,
             loi_noi_bo: str | None = None) -> bool:
    """Kết thúc yêu cầu ĐÚNG lượt đã nhận: chỉ khi còn dang_tao và cùng mốc `bat_dau_luc` lúc nhận
    (dòng đã bị `don_dep` đổi thành loi / nhận lại thì không đè). Link chỉ ghi khi đúng Lark
    (`link_lark`). -> có ghi được không."""
    if trang_thai not in ("xong", "loi"):
        raise ValueError("trạng thái kết thúc phải là xong hoặc loi")
    with ket_noi() as c:
        n = c.execute(
            "UPDATE yeu_cau_sheet_qc SET trang_thai = %s, tieu_de = %s, sheet_url = %s, "
            "so_dong = %s::jsonb, loi = %s, loi_noi_bo = %s, xong_luc = now() WHERE id = %s "
            "AND trang_thai = 'dang_tao' AND bat_dau_luc IS NOT DISTINCT FROM %s",
            (trang_thai, (tieu_de or None) and str(tieu_de)[:300], link_lark(sheet_url) or None,
             json.dumps(so_dong or {}, ensure_ascii=False, default=str),
             (loi or None) and str(loi)[:300], (loi_noi_bo or None) and str(loi_noi_bo)[:500],
             int(yid), bat_dau_luc)).rowcount
    return bool(n)


#: Link Sheet hợp lệ: https + máy chủ Lark / Feishu (cùng luật CHECK của bảng). Khác → "".
_HOST_LARK = (".larksuite.com", ".feishu.cn")


def link_lark(url) -> str:
    from urllib.parse import urlsplit
    s = str(url or "").strip()
    try:
        u = urlsplit(s)
    except ValueError:
        return ""
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host.endswith(_HOST_LARK) or u.username or u.password:
        return ""
    return s


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


#: Đọc cả kỳ dài (≤ 400 ngày × cấp quảng cáo) có thể lâu hơn trần 20 giây của trang.
_GIAY_DOC = "120s"


def ma_cd_theo_ten(ids: list[str], tu: datetime.date, den: datetime.date,
                   loc: dict) -> list[str]:
    """23/10/2026 (MKT): chiến dịch khớp lọc tên cấp trang (cột `ten_cd` → `quang_cao.doc_ten_cd` →
    `loc_ten_cd`; bản 2: chứa tất cả / một trong / không chứa) — CHÍNH `kho_qc.ma_cd_theo_ten` của
    trang, tính lại lúc dựng Sheet (tên mới nhất trong kỳ xuất)."""
    from dashboard import kho_qc as KQ
    if not ids or not loc.get("co_loc") or loc.get("khong_khop"):
        return []
    with ket_noi() as c:
        c.execute(f"SET LOCAL statement_timeout = '{_GIAY_DOC}'")
        return KQ.ma_cd_theo_ten_c(c, ids, tu, den, loc)


def doc_theo_ngay(ids: list[str], tu: datetime.date, den: datetime.date,
                  toi_da: int = TRAN_DONG["ngay"], cds: list[str] | None = None) -> dict:
    """Tab (a): mỗi tài khoản × ngày một dòng (qc_tk_ngay). Quá trần thì giữ các NGÀY GẦN NHẤT
    (xếp ngày giảm dần khi cắt, trả lại tăng dần để hiện). -> {"rows", "tong"} (tong = số dòng
    trước trần). Tổng KHÔNG cộng từ đây (có thể đã cắt) — dùng `doc_tong_tien_te`.
    23/10/2026: `cds` (lọc tên chiến dịch cấp trang) → cộng từ qc_campaign_ngay chỉ các chiến dịch
    đó, vẫn một dòng mỗi tài khoản × ngày; [] = rỗng, không truy vấn."""
    if not ids or (cds is not None and not cds):
        return {"rows": [], "tong": 0}
    # 28/10/2026: + click_lk (bấm liên kết — Click / CTR / CPC của Sheet như trang Quảng cáo).
    from dashboard import kho_qc as KQ
    if cds is None:
        sql = (f"SELECT advertiser_id, ngay, {', '.join(QC.TEN_COT_SO)}, "
               f"({KQ.click_lk_sql()})::bigint AS click_lk, count(*) OVER () AS tong "
               "FROM qc_tk_ngay WHERE advertiser_id = ANY(%s) AND ngay BETWEEN %s AND %s "
               "ORDER BY ngay DESC, advertiser_id LIMIT %s")
        ts = (list(ids), tu, den, int(toi_da))
    else:
        sql = (f"SELECT advertiser_id, ngay, {KQ._TONG}, {KQ._TONG_LL}, count(*) OVER () AS tong "
               "FROM qc_campaign_ngay WHERE advertiser_id = ANY(%s) AND campaign_id = ANY(%s) "
               "AND ngay BETWEEN %s AND %s GROUP BY advertiser_id, ngay "
               "ORDER BY ngay DESC, advertiser_id LIMIT %s")
        ts = (list(ids), list(cds), tu, den, int(toi_da))
    with ket_noi() as c:
        c.execute(f"SET LOCAL statement_timeout = '{_GIAY_DOC}'")
        rows = c.execute(sql, ts).fetchall()
    rows = sorted(rows, key=lambda r: (r["ngay"], str(r["advertiser_id"])))
    return {"rows": [{k: v for k, v in r.items() if k != "tong"} for r in rows],
            "tong": int(rows[0]["tong"]) if rows else 0}


def doc_tong_tien_te(ids: list[str], tu: datetime.date, den: datetime.date,
                     cds: list[str] | None = None) -> dict[str, dict]:
    """Tổng cả kỳ theo TIỀN TỆ tài khoản trên TOÀN phạm vi (không trần dòng) — dòng TỔNG của tab
    theo ngày + Tổng quan không bao giờ lấy từ dòng đã cắt. -> {tiền tệ: {cột số: tổng}}.
    23/10/2026: `cds` → chỉ các chiến dịch khớp tên (qc_campaign_ngay); [] = {} không truy vấn."""
    if not ids or (cds is not None and not cds):
        return {}
    from dashboard import kho_qc as KQ
    bang, loc_cd = (("qc_tk_ngay", "") if cds is None
                    else ("qc_campaign_ngay", " AND q.campaign_id = ANY(%s)"))
    with ket_noi() as c:
        c.execute(f"SET LOCAL statement_timeout = '{_GIAY_DOC}'")
        rows = c.execute(
            f"SELECT COALESCE(NULLIF(k.tien_te, ''), 'VND') AS tien_te, "
            f"{', '.join(f'sum(q.{x})::float AS {x}' if x in QC.COT_TIEN else f'sum(q.{x})::bigint AS {x}' for x in QC.TEN_COT_SO)}, "
            f"sum({KQ.click_lk_sql('q.')})::bigint AS click_lk "
            f"FROM {bang} q JOIN tk_quang_cao k USING (advertiser_id) "
            f"WHERE q.advertiser_id = ANY(%s){loc_cd} AND q.ngay BETWEEN %s AND %s GROUP BY 1 "
            "ORDER BY 1", (list(ids), *([list(cds)] if cds is not None else []), tu, den)).fetchall()
    return {r["tien_te"]: {k: v for k, v in r.items() if k != "tien_te"} for r in rows}


#: Cấp → (bảng, khoá, cột tên lấy từ NGÀY MỚI NHẤT của mỗi đối tượng trong kỳ, cấp của
#: `kho_qc.qc_bang` — lọc / xếp dùng CHÍNH SQL của bảng trang Quảng cáo).
_CAP = {"chien_dich": ("qc_campaign_ngay", "campaign_id", ("ten", "muc_tieu"), "campaign"),
        "quang_cao": ("qc_ad_ngay", "ad_id", ("campaign_id", "adgroup_id", "ten_ad",
                                              "left(noi_dung, 300) AS noi_dung", "ten_campaign",
                                              "ten_nhom"), "ad")}
_SO_NGAY = (", count(DISTINCT ngay) FILTER (WHERE COALESCE(hien_thi, 0) > 0 OR COALESCE(chi, 0) > 0) "
            "AS so_ngay")


def doc_tong(cap: str, ids: list[str], tu: datetime.date, den: datetime.date,
             toi_da: int | None = None, *, sap: str = "chi", tang: bool = False, mau: str = "",
             cd: str = "", cds: list[str] | None = None) -> dict:
    """Tab (b)/(c): tổng cả kỳ của từng chiến dịch / quảng cáo (nhóm theo mã + tài khoản); ≤ `toi_da`
    dòng. -> {"rows", "tong"} (tong = số đối tượng khớp trước trần).

    22/10/2026 (chủ dự án): Sheet chứa ĐÚNG những gì bảng trang Quảng cáo đang lọc — `mau` (tên, đã
    qua `quang_cao.chu_tim`), `cd` (mã chiến dịch), xếp `sap` + `tang` — bằng CHÍNH `kho_qc.sql_bang`
    + `kho_qc.ma_khop_ten` (không chép SQL), mọi dòng khớp (không chỉ một trang) tới trần.
    Mặc định (chi, giảm) = thứ tự cũ: chi giảm dần, rồi hiển thị, rồi mã.
    23/10/2026: `cds` — chiến dịch khớp lọc tên cấp trang (`ma_cd_theo_ten`); [] = rỗng."""
    if cap not in _CAP or not ids or (cds is not None and not cds):
        return {"rows": [], "tong": 0}
    from dashboard import kho_qc as KQ
    bang, khoa, ten, cap_qc = _CAP[cap]
    toi_da = int(toi_da or TRAN_DONG[cap])
    pv = KQ.tham_bang(ids, tu, den, cd, cds)
    with ket_noi() as c:
        c.execute(f"SET LOCAL statement_timeout = '{_GIAY_DOC}'")
        ma = None
        if mau:
            ma = KQ.ma_khop_ten(c, cap_qc, ids, tu, den, mau, cd, cds)
            if not ma:
                return {"rows": [], "tong": 0}
        rows = c.execute(
            KQ.sql_bang(cap_qc, sap, tang, loc_ma=ma is not None, cd=bool(cd), them=_SO_NGAY,
                        bo_qua=False, cds=cds is not None),
            pv + ([ma] if ma is not None else []) + [toi_da]).fetchall()
        if not rows:
            return {"rows": [], "tong": 0}
        moi = {r[khoa]: r for r in c.execute(
            f"SELECT DISTINCT ON ({khoa}) {khoa}, {', '.join(ten)} FROM {bang} "
            f"WHERE {khoa} = ANY(%s) AND advertiser_id = ANY(%s) AND ngay BETWEEN %s AND %s "
            f"ORDER BY {khoa}, ngay DESC", ([r[khoa] for r in rows], list(ids), tu, den)
        ).fetchall()}
    return {"rows": [{**{k: v for k, v in r.items() if k != "tong_khop"},
                      **{k: v for k, v in (moi.get(r[khoa]) or {}).items() if k != khoa}}
                     for r in rows],
            "tong": int(rows[0]["tong_khop"])}
