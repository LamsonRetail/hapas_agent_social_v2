"""Kho quảng cáo TikTok (19/10/2026) — SQL của các bảng `ket_noi_ngoai`, `tk_quang_cao`, `qc_*`.

Tách khỏi `kho.py` (module SQL của phần lắng nghe) cho gọn, nhưng dùng CHUNG `kho.ket_noi` (cùng
role `lang_nghe_web`, cùng cách báo lỗi `LoiKho` / `LoiDuLieu`, không bao giờ in DSN). Ngoài hai
module này dashboard không có SQL.

Ba nhóm hàm:
  • Kết nối (`ket_noi_ngoai`): token chỉ đi qua đây dưới dạng ĐÃ MÃ HOÁ (`tiktok_ads.ma_hoa`) —
    module này không biết khoá, không bao giờ giải mã. `doc_ket_noi` trả cả cột mã hoá cho
    `tiktok_ads`; trang/API dùng `tiktok_ads.the_ket_noi` (bỏ cột token) chứ không đọc thẳng.
  • Ghi số liệu (`ghi_*`): upsert theo khoá chính (`ON CONFLICT … DO UPDATE`) — chạy lại cùng khoảng
    ngày không nhân đôi, chỉ cập nhật số + `cap_nhat_luc` (mốc đồng bộ BigQuery).
  • Đọc cho trang / API / Mark (`qc_*`): tổng theo ngày, top campaign/ad, khán giả, độ mới. Các hàm
    đọc chỉ chạm cột role `mark` được đọc (schema.sql) — tool `hoi_dashboard` gọi lại đúng chúng.

Khoá đồng bộ: `khoa_dong_bo()` giữ `pg_try_advisory_lock` trên MỘT kết nối riêng suốt lượt — bộ
hẹn giờ (systemd) và nút "Đồng bộ ngay" của dashboard không bao giờ chạy chồng nhau.
"""
from __future__ import annotations

import contextlib
import datetime
import json

from dashboard import quang_cao as QC
from dashboard.kho import LoiDuLieu, LoiKho, _nhat_ky, ket_noi

NCC = "tiktok_ads"
#: Khoá advisory của lượt đồng bộ (số cố định < 2^31, không trùng chỗ nào khác trong DB lang_nghe:
#: pg_locks hiện nó ở classid 0, objid = số này).
KHOA_DONG_BO = 720_191_001
_COT_SO = ", ".join(QC.TEN_COT_SO)


def _json(d) -> str:
    return json.dumps(d or {}, ensure_ascii=False, default=str, sort_keys=True)


# ───────────────────────────── kết nối ─────────────────────────────
def doc_ket_noi(ncc: str = NCC) -> dict | None:
    """Dòng kết nối ĐỦ cột (gồm token đã mã hoá) — chỉ `tiktok_ads` dùng."""
    with ket_noi() as c:
        return c.execute("SELECT * FROM ket_noi_ngoai WHERE nha_cung_cap = %s", (ncc,)).fetchone()


def _dam_bao(c, ncc: str) -> None:
    c.execute("INSERT INTO ket_noi_ngoai (nha_cung_cap) VALUES (%s) ON CONFLICT DO NOTHING",
              (ncc,))


def luu_dang_ky(client_id: str, redirect_uri: str, ncc: str = NCC) -> None:
    """Client OAuth đăng ký động (DCR) — một lần cho mỗi redirect_uri."""
    with ket_noi() as c:
        _dam_bao(c, ncc)
        c.execute("UPDATE ket_noi_ngoai SET client_id = %s, redirect_uri = %s, cap_nhat_luc = now() "
                  "WHERE nha_cung_cap = %s", (client_id, redirect_uri, ncc))


def luu_token(ai: str, loai: str, access_enc: str, refresh_enc: str | None,
              access_het: datetime.datetime | None, refresh_het: datetime.datetime | None,
              ncc: str = NCC) -> None:
    """Lưu token MỚI sau khi người quản trị cấp quyền (OAuth xong / dán token API). Nhật ký ghi
    ai + loại + hạn — KHÔNG ghi token."""
    with ket_noi() as c:
        _dam_bao(c, ncc)
        c.execute(
            "UPDATE ket_noi_ngoai SET loai = %s, access_token_enc = %s, refresh_token_enc = %s, "
            "access_het_luc = %s, refresh_het_luc = %s, nguoi_cap = %s, cap_luc = now(), "
            "lam_moi_luc = NULL, trang_thai = 'hoat_dong', loi_cuoi = NULL, loi_luc = NULL, "
            "cap_nhat_luc = now() WHERE nha_cung_cap = %s",
            (loai, access_enc, refresh_enc, access_het, refresh_het, ai, ncc))
        _nhat_ky(c, ai, "ket_noi_tiktok", f"ket_noi:{ncc}",
                 {"loai": loai, "refresh_het_luc": refresh_het})


def cap_nhat_token(access_enc: str, access_het: datetime.datetime | None,
                   refresh_enc: str | None, refresh_het: datetime.datetime | None,
                   neu: tuple, ncc: str = NCC) -> bool:
    """Sau khi làm mới access token (máy tự làm — không nhật ký). CHỈ ghi khi dòng còn đúng như
    lúc đọc (`neu` = (access_token_enc, cap_luc) đã đọc): quản trị viên ngắt / đăng nhập lại giữa
    lượt thì không bị lượt đồng bộ ghi đè. -> đã ghi hay không."""
    with ket_noi() as c:
        cur = c.execute(
            "UPDATE ket_noi_ngoai SET access_token_enc = %s, access_het_luc = %s, "
            "refresh_token_enc = COALESCE(%s, refresh_token_enc), refresh_het_luc = %s, "
            "lam_moi_luc = now(), trang_thai = 'hoat_dong', cap_nhat_luc = now() "
            "WHERE nha_cung_cap = %s AND access_token_enc IS NOT DISTINCT FROM %s "
            "AND cap_luc IS NOT DISTINCT FROM %s",
            (access_enc, access_het, refresh_enc, refresh_het, ncc, neu[0], neu[1]))
        return bool(cur.rowcount)


def ghi_trang_thai(trang_thai: str, loi: str | None = None, ncc: str = NCC, *,
                   neu: tuple | None = None, con_token: bool = False) -> None:
    """Trạng thái + lỗi cuối (lỗi đã bỏ token/URL — `tiktok_ads.gon_loi`). `neu` = (access_token_enc,
    cap_luc) đã đọc: chỉ ghi khi kết nối chưa đổi (lượt đồng bộ không ghi đè lần ngắt / đăng nhập
    lại). `con_token`: chỉ ghi khi còn token (không đặt "hoat_dong" cho kết nối đã ngắt)."""
    dk, ts = "", []
    if neu is not None:
        dk += " AND access_token_enc IS NOT DISTINCT FROM %s AND cap_luc IS NOT DISTINCT FROM %s"
        ts += [neu[0], neu[1]]
    if con_token:
        dk += " AND access_token_enc IS NOT NULL"
    with ket_noi() as c:
        _dam_bao(c, ncc)
        c.execute(
            "UPDATE ket_noi_ngoai SET trang_thai = %s, loi_cuoi = COALESCE(%s, loi_cuoi), "
            "loi_luc = CASE WHEN %s::text IS NULL THEN loi_luc ELSE now() END, "
            "cap_nhat_luc = now() WHERE nha_cung_cap = %s" + dk,
            (trang_thai, (loi or None) and str(loi)[:500], loi, ncc, *ts))


def ghi_goi_ok(ncc: str = NCC) -> None:
    with ket_noi() as c:
        c.execute("UPDATE ket_noi_ngoai SET goi_ok_luc = now() WHERE nha_cung_cap = %s", (ncc,))


def ngat(ai: str, ncc: str = NCC) -> None:
    """Xoá token (đã thu hồi phía TikTok nếu được). Giữ client_id (đăng ký lại không cần)."""
    with ket_noi() as c:
        _dam_bao(c, ncc)
        c.execute(
            "UPDATE ket_noi_ngoai SET access_token_enc = NULL, refresh_token_enc = NULL, "
            "access_het_luc = NULL, refresh_het_luc = NULL, trang_thai = 'da_ngat', "
            "cap_nhat_luc = now() WHERE nha_cung_cap = %s", (ncc,))
        _nhat_ky(c, ai, "ngat_tiktok", f"ket_noi:{ncc}", {})


def bat_dau_dong_bo(ncc: str = NCC) -> None:
    """Lượt bắt đầu: ghi mốc + xoá cờ yêu cầu đang chờ (lượt này đáp ứng nó)."""
    with ket_noi() as c:
        _dam_bao(c, ncc)
        c.execute("UPDATE ket_noi_ngoai SET dong_bo_bat_dau = now(), dong_bo_xong = NULL, "
                  "yeu_cau_dong_bo_luc = NULL WHERE nha_cung_cap = %s", (ncc,))


def yeu_cau_dong_bo(ai: str, ncc: str = NCC) -> None:
    """Quản trị viên bấm "Đồng bộ ngay" (hoặc vừa kết nối): CHỈ ghi cờ — bộ hẹn giờ 10 phút
    (`dong-bo --chi-khi-yeu-cau`) chạy lượt. Yêu cầu đang chờ thì giữ mốc cũ (không dời)."""
    with ket_noi() as c:
        _dam_bao(c, ncc)
        c.execute("UPDATE ket_noi_ngoai SET yeu_cau_dong_bo_luc = COALESCE(yeu_cau_dong_bo_luc, "
                  "now()), yeu_cau_boi = %s WHERE nha_cung_cap = %s", (ai, ncc))
        _nhat_ky(c, ai, "dong_bo_tiktok", f"ket_noi:{ncc}", {"kieu": "yeu_cau"})


def ket_thuc_dong_bo(so_dong: int, loi: str | None, den_ngay: datetime.date | None,
                     ncc: str = NCC) -> None:
    """Kết thúc lượt: số dòng ghi, lỗi (None = ổn), số liệu đến hết ngày nào."""
    with ket_noi() as c:
        c.execute(
            "UPDATE ket_noi_ngoai SET dong_bo_xong = now(), dong_bo_so_dong = %s, "
            "dong_bo_loi = %s, dong_bo_ok_luc = CASE WHEN %s::text IS NULL THEN now() "
            "ELSE dong_bo_ok_luc END, so_den_ngay = GREATEST(so_den_ngay, %s::date) "
            "WHERE nha_cung_cap = %s",
            (int(so_dong), (loi or None) and str(loi)[:500], loi, den_ngay, ncc))


@contextlib.contextmanager
def khoa_dong_bo():
    """-> True khi giữ được khoá (không ai đang đồng bộ), False khi lượt khác đang chạy. Khoá
    phiên Postgres: tiến trình chết thì khoá tự nhả."""
    try:
        import psycopg
    except ImportError:
        raise LoiKho("máy chủ dashboard chưa cài thư viện psycopg") from None
    from dashboard import kho as K
    try:
        conn = psycopg.connect(K._dsn(), connect_timeout=5, autocommit=True)
    except psycopg.Error as e:
        raise LoiKho(f"không nối được kho lắng nghe ({type(e).__name__})") from None
    try:
        co = bool(conn.execute("SELECT pg_try_advisory_lock(%s::bigint)", (KHOA_DONG_BO,)).fetchone()[0])
        try:
            yield co
        finally:
            if co:
                with contextlib.suppress(psycopg.Error):
                    conn.execute("SELECT pg_advisory_unlock(%s::bigint)", (KHOA_DONG_BO,))
    finally:
        conn.close()


def dang_dong_bo() -> bool:
    """Có lượt đồng bộ đang giữ khoá không (thẻ kết nối hiện "đang đồng bộ")."""
    with ket_noi() as c:
        r = c.execute("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                      "AND classid = 0::oid AND objid = %s::oid AND objsubid = 1 AND granted) "
                      "AS co", (KHOA_DONG_BO,)).fetchone()
    return bool(r and r["co"])


# ───────────────────────────── tài khoản quảng cáo ─────────────────────────────
_COT_TK = ("advertiser_id, ten, don_vi, gan_tay, gan_luc, tien_te, mui_gio, dang_dong_bo, "
           "con_quyen, thay_lan_dau, thay_cuoi, nap_lui_tu, nap_lui_xong_luc, khan_gia_luc, "
           "cap_nhat_luc")


def cac_tk() -> list[dict]:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_TK} FROM tk_quang_cao ORDER BY ten, advertiser_id"
                         ).fetchall()


def ben_co_tk() -> set[str]:
    """Bên có ít nhất một tài khoản quảng cáo đã gán (mục điều hướng)."""
    with ket_noi() as c:
        return {r["don_vi"] for r in c.execute(
            "SELECT DISTINCT don_vi FROM tk_quang_cao WHERE don_vi IS NOT NULL").fetchall()}


def ghi_tk(ds: list[dict], ncc: str = NCC) -> dict:
    """Tài khoản TikTok vừa thấy (auth_advertiser_get + advertiser_info_get) → upsert.

    Gán bên tự động (`quang_cao.ben_tu_dong`) CHỈ khi dòng chưa bị quản trị viên sửa tay
    (`gan_tay`): không bao giờ đè bên người quản trị đã chọn. Bên tự động chưa có trong `don_vi`
    thì để NULL (chỉ quản trị viên thấy). Tài khoản không còn thấy: `con_quyen` = false (giữ số cũ).
    -> {"so_tk_thay", "so_tk_truoc", "moi": [advertiser_id…]}."""
    with ket_noi() as c:
        _dam_bao(c, ncc)
        ben = {r["ma"] for r in c.execute("SELECT ma FROM don_vi").fetchall()}
        cu = {r["advertiser_id"] for r in c.execute(
            "SELECT advertiser_id FROM tk_quang_cao").fetchall()}
        moi = []
        for t in ds:
            adv = str(t["advertiser_id"])
            tu_dong = QC.ben_tu_dong(t.get("ten") or "")
            c.execute(
                "INSERT INTO tk_quang_cao (advertiser_id, ten, don_vi, tien_te, mui_gio) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (advertiser_id) DO UPDATE SET "
                "ten = EXCLUDED.ten, tien_te = EXCLUDED.tien_te, mui_gio = EXCLUDED.mui_gio, "
                "don_vi = CASE WHEN tk_quang_cao.gan_tay THEN tk_quang_cao.don_vi "
                "ELSE EXCLUDED.don_vi END, con_quyen = TRUE, thay_cuoi = now(), "
                "cap_nhat_luc = now()",
                (adv, str(t.get("ten") or "")[:300], tu_dong if tu_dong in ben else None,
                 str(t.get("tien_te") or "VND")[:10], str(t.get("mui_gio") or "Asia/Ho_Chi_Minh")[:60]))
            if adv not in cu:
                moi.append(adv)
        thay = [str(t["advertiser_id"]) for t in ds]
        c.execute("UPDATE tk_quang_cao SET con_quyen = FALSE, cap_nhat_luc = now() "
                  "WHERE con_quyen AND NOT (advertiser_id = ANY(%s))", (thay,))
        truoc = c.execute("SELECT so_tk_thay FROM ket_noi_ngoai WHERE nha_cung_cap = %s",
                          (ncc,)).fetchone()
        so_truoc = truoc["so_tk_thay"] if truoc else None
        c.execute("UPDATE ket_noi_ngoai SET so_tk_truoc = so_tk_thay, so_tk_thay = %s "
                  "WHERE nha_cung_cap = %s", (len(thay), ncc))
    return {"so_tk_thay": len(thay), "so_tk_truoc": so_truoc, "moi": moi}


def gan_ben(ai: str, advertiser_id: str, don_vi: str | None, dang_dong_bo: bool) -> None:
    """Quản trị viên gán tài khoản cho bên (None = bỏ gán) và bật/tắt đồng bộ. Đánh dấu
    `gan_tay` để lần thấy sau không gán tự động đè."""
    with ket_noi(trung="Dữ liệu này đã có.") as c:
        r = c.execute("SELECT don_vi, dang_dong_bo FROM tk_quang_cao WHERE advertiser_id = %s "
                      "FOR UPDATE", (advertiser_id,)).fetchone()
        if not r:
            raise LoiDuLieu("Không có tài khoản quảng cáo này.")
        if don_vi and not c.execute("SELECT 1 FROM don_vi WHERE ma = %s", (don_vi,)).fetchone():
            raise LoiDuLieu("Không có bên này.")
        c.execute("UPDATE tk_quang_cao SET don_vi = %s, dang_dong_bo = %s, gan_tay = TRUE, "
                  "gan_luc = now(), cap_nhat_luc = now() WHERE advertiser_id = %s",
                  (don_vi or None, bool(dang_dong_bo), advertiser_id))
        _nhat_ky(c, ai, "gan_ben_tk_qc", f"tk_quang_cao:{advertiser_id}",
                 {"don_vi": [r["don_vi"], don_vi or None],
                  "dang_dong_bo": [r["dang_dong_bo"], bool(dang_dong_bo)]})


def dat_nap_lui(advertiser_id: str, tu: datetime.date, xong: bool) -> None:
    """Nạp lùi đã xong tới ngày `tu` (cửa sổ vừa ghi); `xong` = đã đủ 90 ngày."""
    with ket_noi() as c:
        c.execute("UPDATE tk_quang_cao SET nap_lui_tu = %s, nap_lui_xong_luc = CASE WHEN %s "
                  "THEN now() ELSE nap_lui_xong_luc END WHERE advertiser_id = %s",
                  (tu, bool(xong), advertiser_id))


def dat_khan_gia(advertiser_id: str) -> None:
    with ket_noi() as c:
        c.execute("UPDATE tk_quang_cao SET khan_gia_luc = now() WHERE advertiser_id = %s",
                  (advertiser_id,))


# ───────────────────────────── ghi số liệu (upsert) ─────────────────────────────
#: Bảng → (cột khoá thêm trước cột số, PK). Cột số + chi_so + cap_nhat_luc chung mọi bảng.
BANG_QC = {
    "qc_tk_ngay": (("advertiser_id", "ngay"), ("advertiser_id", "ngay")),
    "qc_campaign_ngay": (("advertiser_id", "campaign_id", "ngay", "ten", "muc_tieu"),
                         ("campaign_id", "ngay")),
    "qc_ad_ngay": (("advertiser_id", "campaign_id", "adgroup_id", "ad_id", "ngay", "ten_ad",
                    "noi_dung", "ten_campaign", "ten_nhom"), ("ad_id", "ngay")),
    "qc_khan_gia": (("advertiser_id", "tu", "den", "chieu", "gia_tri"),
                    ("advertiser_id", "tu", "den", "chieu", "gia_tri")),
}


def sql_upsert(bang: str) -> str:
    """INSERT … ON CONFLICT (PK) DO UPDATE — chạy lại cùng dòng chỉ ghi đè số (idempotent)."""
    dau, pk = BANG_QC[bang]
    cot = [*dau, *QC.TEN_COT_SO, "chi_so"]
    gia_tri = ", ".join("%s::jsonb" if c == "chi_so" else "%s" for c in cot)
    cap_nhat = ", ".join(f"{c} = EXCLUDED.{c}" for c in cot if c not in pk)
    return (f"INSERT INTO {bang} ({', '.join(cot)}) VALUES ({gia_tri}) "
            f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {cap_nhat}, cap_nhat_luc = now()")


def _ghi(bang: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    dau, _ = BANG_QC[bang]
    sql = sql_upsert(bang)
    tham = [(*(r.get(k) for k in dau), *(r.get(k) for k in QC.TEN_COT_SO),
             _json(r.get("chi_so"))) for r in rows]
    with ket_noi() as c, c.cursor() as cur:
        cur.executemany(sql, tham)
    return len(rows)


def ghi_tk_ngay(rows: list[dict]) -> int:
    return _ghi("qc_tk_ngay", rows)


def ghi_campaign_ngay(rows: list[dict]) -> int:
    return _ghi("qc_campaign_ngay", rows)


def ghi_ad_ngay(rows: list[dict]) -> int:
    return _ghi("qc_ad_ngay", rows)


def ghi_khan_gia(rows: list[dict]) -> int:
    return _ghi("qc_khan_gia", rows)


# ───────────────────────────── đọc (trang, API, Mark) ─────────────────────────────
_TONG = ", ".join(f"sum({c})::float AS {c}" if c in QC.COT_TIEN else f"sum({c})::bigint AS {c}"
                  for c in QC.TEN_COT_SO)


def qc_tong(ids: list[str], tu: datetime.date, den: datetime.date) -> dict:
    """Tổng các cột số của các tài khoản `ids` trong [tu, den]."""
    if not ids:
        return {}
    with ket_noi() as c:
        return c.execute(f"SELECT {_TONG}, count(DISTINCT ngay) AS so_ngay FROM qc_tk_ngay "
                         "WHERE advertiser_id = ANY(%s) AND ngay BETWEEN %s AND %s",
                         (list(ids), tu, den)).fetchone() or {}


def qc_theo_ngay(ids: list[str], tu: datetime.date, den: datetime.date) -> list[dict]:
    if not ids:
        return []
    with ket_noi() as c:
        return c.execute(f"SELECT ngay, {_TONG} FROM qc_tk_ngay WHERE advertiser_id = ANY(%s) "
                         "AND ngay BETWEEN %s AND %s GROUP BY ngay ORDER BY ngay",
                         (list(ids), tu, den)).fetchall()


_SAP_SQL = {"chi": "chi", "hien_thi": "hien_thi", "view_video": "view_video",
            "follow": "follow"}


#: Cấp → (bảng, khoá, cột tên lấy từ NGÀY MỚI NHẤT của mỗi đối tượng).
_TOP = {"campaign": ("qc_campaign_ngay", "campaign_id", ("ten", "muc_tieu")),
        "ad": ("qc_ad_ngay", "ad_id", ("campaign_id", "ten_ad", "left(noi_dung, 300) AS noi_dung",
                                       "ten_campaign"))}
TOP_TOI_DA = 50


def sql_top(cap: str, cot: str) -> tuple[str, str]:
    """(1) tổng theo đối tượng trong kỳ, xếp + LIMIT n NGAY ở bước tổng (không gom mảng tên trên cả
    khoảng ngày); (2) tên / nội dung của ngày mới nhất CHỈ cho ≤ n đối tượng đó (DISTINCT ON dùng
    PK (khoá, ngay))."""
    bang, khoa, ten = _TOP[cap]
    tong = (f"SELECT {khoa}, advertiser_id, {_TONG} FROM {bang} WHERE advertiser_id = ANY(%s) "
            f"AND ngay BETWEEN %s AND %s GROUP BY {khoa}, advertiser_id "
            f"ORDER BY {cot} DESC NULLS LAST, {khoa} LIMIT %s")
    moi = (f"SELECT DISTINCT ON ({khoa}) {khoa}, {', '.join(ten)} FROM {bang} "
           f"WHERE {khoa} = ANY(%s) AND ngay BETWEEN %s AND %s ORDER BY {khoa}, ngay DESC")
    return tong, moi


def qc_top(cap: str, ids: list[str], tu: datetime.date, den: datetime.date, sap: str,
           n: int = 20) -> list[dict]:
    """Top campaign / ad trong kỳ theo cột `sap` (đã kiểm ở `quang_cao.cot_sap`); n ≤ 50."""
    if not ids or cap not in _TOP:
        return []
    cot = _SAP_SQL.get(QC.SAP_XEP.get(sap, sap), "hien_thi")
    _, khoa, _ = _TOP[cap]
    tong, moi = sql_top(cap, cot)
    with ket_noi() as c:
        rows = c.execute(tong, (list(ids), tu, den, max(1, min(int(n), TOP_TOI_DA)))).fetchall()
        if not rows:
            return []
        ten = {r[khoa]: r for r in c.execute(moi, ([r[khoa] for r in rows], tu, den)).fetchall()}
    return [{**r, **{k: v for k, v in (ten.get(r[khoa]) or {}).items() if k != khoa}}
            for r in rows]


def qc_khan_gia(ids: list[str]) -> dict:
    """Cửa sổ khán giả MỚI NHẤT của từng tài khoản, cộng theo chiều + giá trị.
    -> {"rows": [...], "tu", "den"} (tu/den = khoảng nhỏ nhất / lớn nhất của các cửa sổ)."""
    if not ids:
        return {"rows": [], "tu": None, "den": None}
    with ket_noi() as c:
        rows = c.execute(
            f"WITH moi AS (SELECT DISTINCT ON (advertiser_id) advertiser_id, tu, den FROM qc_khan_gia "
            f"WHERE advertiser_id = ANY(%s) ORDER BY advertiser_id, den DESC, tu DESC) "
            f"SELECT k.chieu, k.gia_tri, min(k.tu) AS tu, max(k.den) AS den, "
            f"{', '.join(f'sum(k.{x})::float AS {x}' if x in QC.COT_TIEN else f'sum(k.{x})::bigint AS {x}' for x in QC.TEN_COT_SO)} "
            "FROM qc_khan_gia k JOIN moi USING (advertiser_id, tu, den) GROUP BY k.chieu, k.gia_tri",
            (list(ids),)).fetchall()
    return {"rows": rows, "tu": min((r["tu"] for r in rows), default=None),
            "den": max((r["den"] for r in rows), default=None)}


def qc_moi(ids: list[str]) -> dict:
    """Độ mới: ngày số liệu cuối + lần ghi cuối của các tài khoản `ids`."""
    if not ids:
        return {"ngay_cuoi": None, "ghi_luc": None}
    with ket_noi() as c:
        return c.execute("SELECT max(ngay) AS ngay_cuoi, max(cap_nhat_luc) AS ghi_luc "
                         "FROM qc_tk_ngay WHERE advertiser_id = ANY(%s)", (list(ids),)
                         ).fetchone() or {"ngay_cuoi": None, "ghi_luc": None}


def trang_thai_nhac(ncc: str = NCC) -> dict | None:
    """Cột KHÔNG bí mật của kết nối (Mark nhắc gia hạn — role `mark` chỉ được đọc đúng các cột
    này, xem schema.sql)."""
    with ket_noi() as c:
        return c.execute("SELECT nha_cung_cap, loai, trang_thai, refresh_het_luc, goi_ok_luc, "
                         "loi_cuoi FROM ket_noi_ngoai WHERE nha_cung_cap = %s", (ncc,)).fetchone()
