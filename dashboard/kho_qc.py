"""Kho quảng cáo TikTok + Meta (19–20/10/2026) — SQL của các bảng `ket_noi_ngoai`, `tk_quang_cao`,
`qc_*`. Meta Ads (20/10/2026) dùng chung mọi hàm: `ncc` = "meta_ads", `tk_quang_cao.nen_tang` = meta,
khoá advisory riêng (`meta_ads.KHOA_DONG_BO`).

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
import re
import unicodedata

from dashboard import quang_cao as QC
from dashboard.kho import LoiDuLieu, LoiKho, _nhat_ky, ket_noi

NCC = "tiktok_ads"
#: Khoá advisory của lượt đồng bộ (số cố định < 2^31, không trùng chỗ nào khác trong DB lang_nghe:
#: pg_locks hiện nó ở classid 0, objid = số này). Meta: 720_191_002 (`meta_ads.KHOA_DONG_BO`).
KHOA_DONG_BO = 720_191_001
_COT_SO = ", ".join(QC.TEN_COT_SO)
#: Nhà cung cấp → nền tảng của tài khoản + chữ trong tên hành động nhật ký.
NEN_TANG_NCC = {"tiktok_ads": "tiktok", "meta_ads": "meta"}


def _nen_tang(ncc: str) -> str:
    return NEN_TANG_NCC.get(ncc, "tiktok")


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
        _nhat_ky(c, ai, f"ket_noi_{_nen_tang(ncc)}", f"ket_noi:{ncc}",
                 {"loai": loai, "refresh_het_luc": refresh_het})


def luu_thong_tin_token(chu: str | None, quyen: list[str] | None, ncc: str) -> None:
    """Thông tin KHÔNG bí mật của token (Meta: tên người dùng hệ thống `me.name`, quyền đã cấp
    `me/permissions`) — thẻ kết nối hiện để quản trị viên biết token đang là ai, quyền gì."""
    with ket_noi() as c:
        _dam_bao(c, ncc)
        c.execute("UPDATE ket_noi_ngoai SET chu_token = %s, quyen_token = %s, cap_nhat_luc = now() "
                  "WHERE nha_cung_cap = %s",
                  ((chu or None) and str(chu)[:200], [str(x)[:80] for x in (quyen or [])][:50],
                   ncc))


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
        _nhat_ky(c, ai, f"ngat_{_nen_tang(ncc)}", f"ket_noi:{ncc}", {})


def bat_dau_dong_bo(ncc: str = NCC, cho_nhanh: bool = False, chi_nhanh: bool = False
                    ) -> str | None:
    """Lượt bắt đầu: ghi mốc, xoá cờ yêu cầu đang chờ (lượt này đáp ứng nó) và quyết định loại lượt
    NGUYÊN TỬ trong MỘT câu UPDATE (vế SET đọc giá trị CŨ của dòng): nhanh chỉ khi `cho_nhanh`
    (bộ hẹn giờ yêu cầu, không khoảng ngày tay) và yêu cầu đang chờ là nhanh — yêu cầu day_du ghi
    giữa lúc đọc và lúc khoá không bao giờ bị lượt nhanh "nuốt". -> "nhanh" | "day_du".
    `chi_nhanh` (bộ nghe `nghe_qc`, 20/10/2026): CHỈ bắt đầu khi yêu cầu đang chờ là nhanh — câu
    UPDATE không khớp dòng nào → None (không bắt đầu gì, cờ day_du giữ nguyên cho bộ hẹn giờ);
    bộ nghe không bao giờ mở được lượt đầy đủ."""
    with ket_noi() as c:
        _dam_bao(c, ncc)
        r = c.execute(
            "UPDATE ket_noi_ngoai SET dong_bo_bat_dau = now(), dong_bo_xong = NULL, "
            "dong_bo_kieu = CASE WHEN %s AND yeu_cau_dong_bo_luc IS NOT NULL "
            "AND yeu_cau_kieu = 'nhanh' THEN 'nhanh' ELSE 'day_du' END, "
            "yeu_cau_dong_bo_luc = NULL, yeu_cau_kieu = NULL WHERE nha_cung_cap = %s "
            "AND (NOT %s OR (yeu_cau_dong_bo_luc IS NOT NULL AND yeu_cau_kieu = 'nhanh')) "
            "RETURNING dong_bo_kieu", (bool(cho_nhanh or chi_nhanh), ncc, bool(chi_nhanh))
        ).fetchone()
    if chi_nhanh:
        return (r or {}).get("dong_bo_kieu")
    return (r or {}).get("dong_bo_kieu") or "day_du"


def _yeu_cau(c, ai: str, ncc: str, kieu: str) -> None:
    """Ghi cờ yêu cầu trong giao dịch `c` (dùng chung `yeu_cau_dong_bo` / `nap_lai`)."""
    _dam_bao(c, ncc)
    c.execute("UPDATE ket_noi_ngoai SET yeu_cau_kieu = CASE WHEN yeu_cau_dong_bo_luc IS NOT "
              "NULL AND yeu_cau_kieu = 'day_du' THEN 'day_du' ELSE %s END, "
              "yeu_cau_dong_bo_luc = COALESCE(yeu_cau_dong_bo_luc, now()), yeu_cau_boi = %s "
              "WHERE nha_cung_cap = %s", (kieu, ai, ncc))
    # 20/10/2026: đánh thức bộ nghe (`nghe_qc`, LISTEN qc_tuc_thi) — lượt nhanh chạy ngay thay vì
    # chờ bộ hẹn giờ 2 phút. Thông báo chỉ gửi khi giao dịch COMMIT; không ai nghe thì bỏ.
    c.execute("SELECT pg_notify('qc_tuc_thi', %s)", (ncc,))


def yeu_cau_dong_bo(ai: str, ncc: str = NCC, kieu: str = "day_du") -> None:
    """Ghi cờ yêu cầu — bộ hẹn giờ 2 phút (`dong-bo --chi-khi-yeu-cau`) chạy lượt. Yêu cầu đang
    chờ thì giữ mốc cũ (không dời). `kieu`: day_du (quản trị viên / vừa kết nối) hoặc nhanh (mọi
    người có quyền, 3 ngày gần nhất); yêu cầu day_du đang chờ KHÔNG bị hạ thành nhanh. Yêu cầu
    nhanh: nhật ký ghi ở app (`kho.ghi_nhat_ky`, kieu bam_tay)."""
    kieu = "nhanh" if kieu == "nhanh" else "day_du"
    with ket_noi() as c:
        _yeu_cau(c, ai, ncc, kieu)
        if kieu == "day_du":
            _nhat_ky(c, ai, f"dong_bo_{_nen_tang(ncc)}", f"ket_noi:{ncc}", {"kieu": "yeu_cau"})


def ket_thuc_dong_bo(so_dong: int, loi: str | None, den_ngay: datetime.date | None,
                     ncc: str = NCC) -> None:
    """Kết thúc lượt: số dòng ghi, lỗi (None = ổn), số liệu đến hết ngày nào; lượt nhanh ghi
    `nhanh_xong_luc` (giãn 15 phút giữa hai lượt bấm tay)."""
    with ket_noi() as c:
        c.execute(
            "UPDATE ket_noi_ngoai SET dong_bo_xong = now(), dong_bo_so_dong = %s, "
            "dong_bo_loi = %s, dong_bo_ok_luc = CASE WHEN %s::text IS NULL THEN now() "
            "ELSE dong_bo_ok_luc END, so_den_ngay = GREATEST(so_den_ngay, %s::date), "
            "nhanh_xong_luc = CASE WHEN dong_bo_kieu = 'nhanh' THEN now() ELSE nhanh_xong_luc END "
            "WHERE nha_cung_cap = %s",
            (int(so_dong), (loi or None) and str(loi)[:500], loi, den_ngay, ncc))


@contextlib.contextmanager
def khoa_dong_bo(khoa: int = KHOA_DONG_BO):
    """-> True khi giữ được khoá (không ai đang đồng bộ), False khi lượt khác đang chạy. Khoá
    phiên Postgres: tiến trình chết thì khoá tự nhả. `khoa`: TikTok / Meta mỗi bên một số — hai
    nền tảng chạy song song được, cùng nền tảng không bao giờ chạy chồng."""
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
        co = bool(conn.execute("SELECT pg_try_advisory_lock(%s::bigint)", (khoa,)).fetchone()[0])
        try:
            yield co
        finally:
            if co:
                with contextlib.suppress(psycopg.Error):
                    conn.execute("SELECT pg_advisory_unlock(%s::bigint)", (khoa,))
    finally:
        conn.close()


def dang_dong_bo(khoa: int = KHOA_DONG_BO) -> bool:
    """Có lượt đồng bộ đang giữ khoá không (thẻ kết nối hiện "đang đồng bộ")."""
    with ket_noi() as c:
        r = c.execute("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                      "AND classid = 0::oid AND objid = %s::oid AND objsubid = 1 AND granted) "
                      "AS co", (khoa,)).fetchone()
    return bool(r and r["co"])


# ───────────────────────────── tài khoản quảng cáo ─────────────────────────────
_COT_TK = ("advertiser_id, ten, don_vi, gan_tay, gan_luc, tien_te, mui_gio, dang_dong_bo, "
           "con_quyen, thay_lan_dau, thay_cuoi, nap_lui_tu, nap_lui_xong_luc, khan_gia_luc, "
           "cap_nhat_luc, nen_tang, duyet")


def cac_tk() -> list[dict]:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_TK} FROM tk_quang_cao ORDER BY ten, advertiser_id"
                         ).fetchall()


def ben_co_tk() -> set[str]:
    """Bên có ít nhất một tài khoản quảng cáo đã gán (mục điều hướng)."""
    with ket_noi() as c:
        return {r["don_vi"] for r in c.execute(
            "SELECT DISTINCT don_vi FROM tk_quang_cao WHERE don_vi IS NOT NULL").fetchall()}


def ghi_tk(ds: list[dict], ncc: str = NCC, duyet_moi: set[str] | None = None) -> dict:
    """Tài khoản vừa thấy (TikTok: auth_advertiser_get + advertiser_info_get; Meta: me/adaccounts)
    → upsert, `nen_tang` theo `ncc`.

    Gán bên tự động (`quang_cao.ben_tu_dong`) CHỈ khi dòng chưa bị quản trị viên sửa tay
    (`gan_tay`): không bao giờ đè bên người quản trị đã chọn. Bên tự động chưa có trong `don_vi`
    (hoặc None — tên có THAI) thì để NULL (chỉ quản trị viên thấy). Tài khoản CÙNG NỀN TẢNG không
    còn thấy: `con_quyen` = false (giữ số cũ) — tài khoản nền tảng kia không bị đụng.
    `duyet`: TikTok luôn TRUE; Meta dòng MỚI duyệt khi có trong `duyet_moi` (danh sách nhập kèm
    token), còn lại chưa duyệt (quản trị viên duyệt trên trang Quản trị); dòng cũ giữ nguyên.
    -> {"so_tk_thay", "so_tk_truoc", "moi": [advertiser_id…]}."""
    nen = _nen_tang(ncc)
    duyet_moi = {str(x) for x in (duyet_moi or ())}
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
                "INSERT INTO tk_quang_cao (advertiser_id, ten, don_vi, tien_te, mui_gio, nen_tang, "
                "duyet) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (advertiser_id) DO UPDATE SET "
                "ten = EXCLUDED.ten, tien_te = EXCLUDED.tien_te, mui_gio = EXCLUDED.mui_gio, "
                "don_vi = CASE WHEN tk_quang_cao.gan_tay THEN tk_quang_cao.don_vi "
                "ELSE EXCLUDED.don_vi END, con_quyen = TRUE, thay_cuoi = now(), "
                "cap_nhat_luc = now()",
                (adv, str(t.get("ten") or "")[:300], tu_dong if tu_dong in ben else None,
                 str(t.get("tien_te") or "VND")[:10], str(t.get("mui_gio") or "Asia/Ho_Chi_Minh")[:60],
                 nen, nen != "meta" or adv in duyet_moi))
            if adv not in cu:
                moi.append(adv)
        thay = [str(t["advertiser_id"]) for t in ds]
        c.execute("UPDATE tk_quang_cao SET con_quyen = FALSE, cap_nhat_luc = now() "
                  "WHERE con_quyen AND nen_tang = %s AND NOT (advertiser_id = ANY(%s))",
                  (nen, thay))
        truoc = c.execute("SELECT so_tk_thay FROM ket_noi_ngoai WHERE nha_cung_cap = %s",
                          (ncc,)).fetchone()
        so_truoc = truoc["so_tk_thay"] if truoc else None
        c.execute("UPDATE ket_noi_ngoai SET so_tk_truoc = so_tk_thay, so_tk_thay = %s "
                  "WHERE nha_cung_cap = %s", (len(thay), ncc))
    return {"so_tk_thay": len(thay), "so_tk_truoc": so_truoc, "moi": moi}


def gan_ben(ai: str, advertiser_id: str, don_vi: str | None, dang_dong_bo: bool,
            duyet: bool | None = None) -> None:
    """Quản trị viên gán tài khoản cho bên (None = bỏ gán), bật/tắt đồng bộ và (Meta) duyệt /
    bỏ duyệt tài khoản. Đánh dấu `gan_tay` để lần thấy sau không gán tự động đè. `duyet` chỉ có
    tác dụng với tài khoản Meta (TikTok luôn duyệt)."""
    with ket_noi(trung="Dữ liệu này đã có.") as c:
        r = c.execute("SELECT don_vi, dang_dong_bo, nen_tang, duyet FROM tk_quang_cao "
                      "WHERE advertiser_id = %s FOR UPDATE", (advertiser_id,)).fetchone()
        if not r:
            raise LoiDuLieu("Không có tài khoản quảng cáo này.")
        if don_vi and not c.execute("SELECT 1 FROM don_vi WHERE ma = %s", (don_vi,)).fetchone():
            raise LoiDuLieu("Không có bên này.")
        moi_duyet = bool(duyet) if (duyet is not None and r["nen_tang"] == "meta") else r["duyet"]
        c.execute("UPDATE tk_quang_cao SET don_vi = %s, dang_dong_bo = %s, duyet = %s, "
                  "gan_tay = TRUE, gan_luc = now(), cap_nhat_luc = now() WHERE advertiser_id = %s",
                  (don_vi or None, bool(dang_dong_bo), moi_duyet, advertiser_id))
        _nhat_ky(c, ai, "gan_ben_tk_qc", f"tk_quang_cao:{advertiser_id}",
                 {"don_vi": [r["don_vi"], don_vi or None],
                  "dang_dong_bo": [r["dang_dong_bo"], bool(dang_dong_bo)],
                  "duyet": [r["duyet"], moi_duyet]})


def dat_duyet(ai: str, ids: set[str] | list[str], ncc: str = "meta_ads") -> dict:
    """Danh sách tài khoản ĐƯỢC DUYỆT của một nền tảng = đúng `ids` (lệnh nhập token kèm danh sách
    — thay MARK_META_AD_ACCOUNT_IDS): có trong danh sách → duyet TRUE, còn lại của nền tảng đó →
    FALSE. ID chưa từng thấy được giữ chỗ (con_quyen FALSE, tên rỗng) để lần thấy sau đã duyệt.
    -> {"duyet": n, "bo_duyet": n}."""
    nen = _nen_tang(ncc)
    ids = sorted({str(x) for x in ids})
    with ket_noi() as c:
        for adv in ids:
            c.execute("INSERT INTO tk_quang_cao (advertiser_id, nen_tang, duyet, con_quyen) "
                      "VALUES (%s, %s, TRUE, FALSE) ON CONFLICT (advertiser_id) DO NOTHING",
                      (adv, nen))
        a = c.execute("UPDATE tk_quang_cao SET duyet = TRUE, cap_nhat_luc = now() WHERE nen_tang = %s "
                      "AND advertiser_id = ANY(%s) AND NOT duyet", (nen, ids))
        b = c.execute("UPDATE tk_quang_cao SET duyet = FALSE, cap_nhat_luc = now() WHERE nen_tang = %s "
                      "AND NOT (advertiser_id = ANY(%s)) AND duyet", (nen, ids))
        kq = {"duyet": len(ids), "bat": a.rowcount, "bo_duyet": b.rowcount}
        _nhat_ky(c, ai, f"duyet_tk_{nen}", f"tk_quang_cao:{nen}", kq)
    return kq


def dat_nap_lui(advertiser_id: str, tu: datetime.date, xong: bool) -> None:
    """Nạp lùi đã xong tới ngày `tu` (cửa sổ vừa ghi); `xong` = đã đủ 90 ngày."""
    with ket_noi() as c:
        c.execute("UPDATE tk_quang_cao SET nap_lui_tu = %s, nap_lui_xong_luc = CASE WHEN %s "
                  "THEN now() ELSE nap_lui_xong_luc END WHERE advertiser_id = %s",
                  (tu, bool(xong), advertiser_id))


def nap_lai(ai: str, ncc: str = NCC) -> int:
    """"Đồng bộ lại 90 ngày" (trang Quảng cáo, quản trị viên, 20/10/2026), MỘT giao dịch: xoá mốc nạp lùi
    của mọi tài khoản ĐANG ĐỒNG BỘ (đã duyệt, còn quyền) của nền tảng + ghi cờ yêu cầu day_du + NOTIFY +
    MỘT dòng nhật ký — lượt đầy đủ kế tiếp nạp lại 90 ngày theo đúng đường nạp lùi sẵn có (3 cửa sổ
    30 ngày, mới trước, ngắt giữa chừng thì lượt sau đọc tiếp). Upsert theo khoá chính nên đọc lại
    không nhân đôi số. -> số tài khoản."""
    nen = _nen_tang(ncc)
    with ket_noi() as c:
        n = c.execute("UPDATE tk_quang_cao SET nap_lui_tu = NULL, nap_lui_xong_luc = NULL, "
                      "cap_nhat_luc = now() WHERE nen_tang = %s AND dang_dong_bo AND duyet "
                      "AND con_quyen", (nen,)).rowcount or 0
        _yeu_cau(c, ai, ncc, "day_du")
        _nhat_ky(c, ai, "dong_bo_qc", f"quang_cao:{nen}",
                 {"kieu": "bam_tay", "cua_so": "day_du", "nap_lai_ngay": 90, "so_tk": n})
    return int(n)


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
    sql = (f"INSERT INTO {bang} ({', '.join(cot)}) VALUES ({gia_tri}) "
           f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {cap_nhat}, cap_nhat_luc = now()")
    if "advertiser_id" not in pk:
        # PK không có tài khoản (campaign_id / ad_id): TikTok + Meta cùng bảng từ 20/10/2026. Mã hai
        # nền tảng khác dạng nên không trùng — nhưng nếu lỡ trùng, dòng của tài khoản KHÁC không bao
        # giờ bị ghi đè (bỏ qua dòng mới).
        sql += f" WHERE {bang}.advertiser_id = EXCLUDED.advertiser_id"
    return sql


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


def _tong_json(khoa: str, ten: str) -> str:
    """sum một chỉ số trong JSON `chi_so` (chỉ giá trị kiểu số; chữ / thiếu → bỏ qua, không lỗi
    ép kiểu). `khoa`, `ten` là hằng trong `quang_cao.CHUOI_XEM_SP` — không bao giờ từ người dùng."""
    if not (re.fullmatch(r"[a-z0-9_]+", khoa) and re.fullmatch(r"[a-z0-9_]+", ten)):
        raise ValueError(f"tên chỉ số lạ: {khoa!r}")
    return (f"coalesce(sum(CASE WHEN jsonb_typeof(chi_so->'{khoa}') = 'number' "
            f"THEN (chi_so->>'{khoa}')::numeric END), 0)::bigint AS {ten}")


#: 22/10/2026 (chủ dự án): biểu đồ Theo ngày thêm "Xem trang SP TikTok Shop" + "Xem SP website
#: (Meta)" — cộng từ JSON chi_so (SQL cố định, không tham số hoá tên).
_TONG_XEM_SP = ", ".join(_tong_json(k, ma) for ma, k, *_ in QC.CHUOI_XEM_SP)


def qc_theo_ngay(ids: list[str], tu: datetime.date, den: datetime.date) -> list[dict]:
    """Tổng cột số theo ngày + hai chuỗi xem trang sản phẩm (`QC.TEN_CHUOI_XEM_SP`)."""
    if not ids:
        return []
    with ket_noi() as c:
        return c.execute(f"SELECT ngay, {_TONG}, {_TONG_XEM_SP} FROM qc_tk_ngay "
                         "WHERE advertiser_id = ANY(%s) AND ngay BETWEEN %s AND %s "
                         "GROUP BY ngay ORDER BY ngay", (list(ids), tu, den)).fetchall()


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


#: Bảng trang Quảng cáo (22/10/2026): mã `sap` (`quang_cao.SAP_BANG`) → biểu thức trên tổng `t` của
#: dòng. Tỉ lệ tính lại từ tổng; CPM / CTR dưới NGUONG_TI_LE hiển thị và ROAS khi chi = 0 → NULL
#: (xuống cuối dù tăng hay giảm). Chỉ nối chuỗi từ bảng cố định này — không bao giờ từ tham số.
SAP_BANG_SQL = {
    "chi": "t.chi", "hien_thi": "t.hien_thi", "click": "t.click", "view": "t.view_video",
    "follow": "t.follow",
    "tuong_tac": "(COALESCE(t.thich, 0) + COALESCE(t.binh_luan, 0) + COALESCE(t.chia_se, 0))",
    "cpm": f"CASE WHEN t.hien_thi >= {QC.NGUONG_TI_LE} THEN t.chi * 1000 / t.hien_thi END",
    "ctr": f"CASE WHEN t.hien_thi >= {QC.NGUONG_TI_LE} THEN t.click::float / t.hien_thi END",
    "roas": "CASE WHEN t.chi > 0 THEN t.gia_tri_mua_shop / t.chi END",
}
#: Cấp → cột tên để tìm (tên của NGÀY MỚI NHẤT, như cột hiện ở bảng). Quảng cáo khớp cả tên chiến
#: dịch chứa nó — gõ tên chiến dịch là thấy các quảng cáo của chiến dịch đó.
_TIM_BANG = {"campaign": ("ten",), "ad": ("ten_ad", "ten_campaign")}


def _dk_bang(cd: bool) -> str:
    return "advertiser_id = ANY(%s) AND ngay BETWEEN %s AND %s" + (" AND campaign_id = %s" if cd else "")


def sql_ten_bang(cap: str, *, cd: bool) -> str:
    """Tên mới nhất của mọi đối tượng trong kỳ (để lọc theo tên ở Python). Tham số: ids, tu, den, [cd]."""
    bang, khoa, _ = _TOP[cap]
    return (f"SELECT DISTINCT ON ({khoa}) {khoa}, {', '.join(_TIM_BANG[cap])} FROM {bang} "
            f"WHERE {_dk_bang(cd)} ORDER BY {khoa}, ngay DESC")


def sql_bang(cap: str, sap: str, tang: bool, *, loc_ma: bool, cd: bool, them: str = "",
             bo_qua: bool = True) -> str:
    """SQL một bảng chiến dịch / quảng cáo: tổng theo đối tượng trong kỳ (lọc chiến dịch `cd`, lọc
    mã khớp tên `loc_ma`) → xếp theo `sap` → LIMIT [OFFSET], kèm `tong_khop` (số dòng khớp trước
    LIMIT). Tham số theo thứ tự: ids, tu, den, [cd], [mã], n, [bỏ qua].
    22/10/2026: `bo_qua` — trang của bảng trang Quảng cáo (OFFSET); bộ nghe Sheet (`kho_sheet_qc.
    doc_tong`) dùng CHÍNH hàm này không OFFSET, `them` = cột tổng thêm (hằng trong mã, không bao
    giờ từ tham số) — cùng luật lọc / xếp hai đầu."""
    bang, khoa, _ = _TOP[cap]
    dk = _dk_bang(cd) + (f" AND {khoa} = ANY(%s)" if loc_ma else "")
    xep = SAP_BANG_SQL.get(sap, "t.hien_thi")
    return (f"WITH t AS (SELECT {khoa}, advertiser_id, {_TONG}{them} FROM {bang} WHERE {dk} "
            f"GROUP BY {khoa}, advertiser_id) SELECT t.*, count(*) OVER () AS tong_khop FROM t "
            f"ORDER BY {xep} {'ASC' if tang else 'DESC'} NULLS LAST, t.hien_thi DESC NULLS LAST, "
            f"t.{khoa} LIMIT %s" + (" OFFSET %s" if bo_qua else ""))


def ma_khop_ten(c, cap: str, ids: list[str], tu: datetime.date, den: datetime.date, mau: str,
                cd: str = "") -> list:
    """Mã chiến dịch / quảng cáo trong kỳ có TÊN MỚI NHẤT chứa `mau` (đã qua `quang_cao.chu_tim`) —
    so khớp ở PYTHON bằng đúng `chu_tim` (xem `qc_bang`). `c`: kết nối đang mở của nơi gọi."""
    _, khoa, _ = _TOP[cap]
    pv = [list(ids), tu, den] + ([cd] if cd else [])
    return [r[khoa] for r in c.execute(sql_ten_bang(cap, cd=bool(cd)), pv).fetchall()
            if any(mau in QC.chu_tim(r.get(x) or "") for x in _TIM_BANG[cap])]


def qc_bang(cap: str, ids: list[str], tu: datetime.date, den: datetime.date, *, sap: str,
            tang: bool = False, mau: str = "", cd: str = "", n: int = 10, bo_qua: int = 0) -> dict:
    """Bảng chiến dịch / quảng cáo của trang Quảng cáo — lọc tên (`mau` đã qua
    `quang_cao.chu_tim`), lọc chiến dịch `cd`, xếp theo mọi cột (`quang_cao.loc_bang` đã kiểm).
    Chỉ tài khoản `ids` (phạm vi người xem). -> {"rows": [...], "tong": số dòng khớp, "bo_qua":
    OFFSET thật đã dùng}.

    Phân trang (22/10/2026): `n` dòng từ dòng thứ `bo_qua`. Quá trang cuối (URL cũ, vừa lọc hẹp
    lại) → đếm rồi trả TRANG CUỐI (không trả bảng rỗng khi vẫn có dòng khớp).

    Lọc tên so khớp ở PYTHON bằng đúng `quang_cao.chu_tim` (như Mark tra cứu): đo 22/10/2026 trên
    21.060 quảng cáo / 30 ngày, bỏ dấu bằng translate() trong Postgres mất ~1,8 giây, đọc tên mới
    nhất + so ở Python ~0,3 giây."""
    rong = {"rows": [], "tong": 0, "bo_qua": 0}
    if not ids or cap not in _TOP:
        return rong
    _, khoa, _ = _TOP[cap]
    n = max(1, min(int(n), TOP_TOI_DA))
    bo_qua = max(0, int(bo_qua))
    pv = [list(ids), tu, den] + ([cd] if cd else [])
    _, moi = sql_top(cap, "hien_thi")
    with ket_noi() as c:
        ma = None
        if mau:
            ma = ma_khop_ten(c, cap, ids, tu, den, mau, cd)
            if not ma:
                return rong
        sql = sql_bang(cap, sap, tang, loc_ma=ma is not None, cd=bool(cd))
        ts = pv + ([ma] if ma is not None else [])
        rows = c.execute(sql, ts + [n, bo_qua]).fetchall()
        if not rows and bo_qua:
            dem = c.execute(sql, ts + [1, 0]).fetchall()
            if not dem:
                return rong
            bo_qua = (int(dem[0]["tong_khop"]) - 1) // n * n
            rows = c.execute(sql, ts + [n, bo_qua]).fetchall()
        if not rows:
            return rong
        ten = {r[khoa]: r for r in c.execute(moi, ([r[khoa] for r in rows], tu, den)).fetchall()}
    return {"rows": [{**{k: v for k, v in r.items() if k != "tong_khop"},
                      **{k: v for k, v in (ten.get(r[khoa]) or {}).items() if k != khoa}}
                     for r in rows], "tong": int(rows[0]["tong_khop"]), "bo_qua": bo_qua}


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


# ───────────────────────────── tra cứu một đối tượng (Mark, 20/10/2026) ─────────────────────────────
#: Chủ dự án 20/10/2026: "câu hỏi của người dùng là gốc" — Mark tra đúng chiến dịch / quảng cáo /
#: tài khoản người hỏi nói. Cấp → (bảng, khoá, cột lấy từ NGÀY MỚI NHẤT, cột tên để tìm). Cấp tài khoản
#: tìm tên trong tk_quang_cao (ít dòng — ở Python), số lấy ở qc_tk_ngay.
CAP_TRA_CUU = {
    "tai_khoan": ("qc_tk_ngay", "advertiser_id", (), None),
    "chien_dich": ("qc_campaign_ngay", "campaign_id", ("ten", "muc_tieu"), "ten"),
    "quang_cao": ("qc_ad_ngay", "ad_id", ("campaign_id", "adgroup_id", "ten_ad", "ten_campaign",
                                          "ten_nhom"), "ten_ad"),
}
TRA_CUU_TOI_DA = 200
_VIET = ("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ")
_VIET_KHONG_DAU = "".join("d" if ch == "đ" else unicodedata.normalize("NFKD", ch)[0]
                          for ch in _VIET)
#: translate() của Postgres theo từng ký tự — truyền bằng THAM SỐ, đủ chữ hoa + thường (lower() của
#: Postgres với collation "C" không hạ chữ có dấu).
DICH_TU = _VIET + _VIET.upper()
DICH_THANH = _VIET_KHONG_DAU + _VIET_KHONG_DAU.upper()


def _chuan_sql(cot: str) -> str:
    return f"regexp_replace(lower(translate({cot}, %s, %s)), '[^a-z0-9]+', '', 'g')"


def qc_tim(cap: str, ids: list[str], mau: str, ma: str, n: int = TRA_CUU_TOI_DA) -> dict:
    """Chiến dịch / quảng cáo của các tài khoản `ids` có TÊN MỚI NHẤT chứa `mau` (đã bỏ dấu, chữ
    thường, chỉ a-z0-9 — `quang_cao.chu_tim`) hoặc mã đúng bằng `ma`. Chỉ SELECT, tham số hoá.
    -> {"rows": [{ma, advertiser_id, <cột tên>…}], "tong": tổng số khớp (trước LIMIT)}."""
    if cap not in CAP_TRA_CUU or cap == "tai_khoan" or not ids or not (mau or ma):
        return {"rows": [], "tong": 0}
    bang, khoa, cot, ten = CAP_TRA_CUU[cap]
    dk, ts = ["ma = %s"], [str(ma or "")]
    if mau:
        dk.append(f"{_chuan_sql(ten)} LIKE %s")
        ts += [DICH_TU, DICH_THANH, f"%{mau}%"]
    sql = (f"WITH moi AS (SELECT DISTINCT ON ({khoa}) {khoa} AS ma, advertiser_id, "
           f"{', '.join(cot)} FROM {bang} WHERE advertiser_id = ANY(%s) ORDER BY {khoa}, ngay DESC) "
           f"SELECT *, count(*) OVER () AS tong FROM moi WHERE {' OR '.join(dk)} "
           f"ORDER BY (ma = %s) DESC, {ten}, ma LIMIT %s")
    with ket_noi() as c:
        rows = c.execute(sql, (list(ids), *ts, str(ma or ""), max(1, min(int(n), TRA_CUU_TOI_DA)))
                         ).fetchall()
    return {"rows": [{k: v for k, v in r.items() if k != "tong"} for r in rows],
            "tong": int(rows[0]["tong"]) if rows else 0}


def qc_ten(cap: str, ids: list[str], n: int = 5000) -> list[dict]:
    """Tên mới nhất của mọi chiến dịch / quảng cáo của `ids` (gợi ý tên gần đúng khi không khớp)."""
    if cap not in CAP_TRA_CUU or cap == "tai_khoan" or not ids:
        return []
    bang, khoa, _, ten = CAP_TRA_CUU[cap]
    with ket_noi() as c:
        return c.execute(f"SELECT DISTINCT ON ({khoa}) {khoa} AS ma, advertiser_id, {ten} AS ten "
                         f"FROM {bang} WHERE advertiser_id = ANY(%s) ORDER BY {khoa}, ngay DESC "
                         "LIMIT %s", (list(ids), max(1, min(int(n), 20000)))).fetchall()


def qc_doi_tuong(cap: str, ma: list[str], tu: datetime.date, den: datetime.date,
                 ids: list[str]) -> list[dict]:
    """Tổng cột số kiểu riêng của từng đối tượng trong kỳ + ngày đầu / cuối CÓ phân phối. CHỈ dòng
    của các tài khoản `ids` (phạm vi người hỏi) — mã trùng ở tài khoản khác không bao giờ lọt vào;
    nhóm theo (mã, tài khoản)."""
    if cap not in CAP_TRA_CUU or not ma or not ids:
        return []
    bang, khoa, _, _ = CAP_TRA_CUU[cap]
    pp = "(COALESCE(hien_thi, 0) > 0 OR COALESCE(chi, 0) > 0)"
    with ket_noi() as c:
        return c.execute(
            f"SELECT {khoa} AS ma, advertiser_id AS tk, {_TONG}, "
            f"count(DISTINCT ngay) AS so_ngay, min(ngay) FILTER (WHERE {pp}) AS ngay_dau, "
            f"max(ngay) FILTER (WHERE {pp}) AS ngay_cuoi FROM {bang} WHERE {khoa} = ANY(%s) "
            f"AND advertiser_id = ANY(%s) AND ngay BETWEEN %s AND %s GROUP BY {khoa}, advertiser_id",
            (list(ma)[:TRA_CUU_TOI_DA], list(ids), tu, den)).fetchall()


def qc_chi_so_tong(cap: str, ma: list[str], tu: datetime.date, den: datetime.date,
                   ids: list[str]) -> list[dict]:
    """Tổng THÔ từng khoá số trong `chi_so` (JSONB) của từng đối tượng trong kỳ, chỉ tài khoản
    `ids`. Khoá không cộng được (tỉ lệ, reach…) vẫn trả — bên gọi bỏ bằng `quang_cao.cong_duoc`."""
    if cap not in CAP_TRA_CUU or not ma or not ids:
        return []
    bang, khoa, _, _ = CAP_TRA_CUU[cap]
    with ket_noi() as c:
        return c.execute(
            f"SELECT t.{khoa} AS ma, t.advertiser_id AS tk, e.key AS ten, "
            "sum((e.value)::text::numeric)::float AS tong "
            f"FROM {bang} t, jsonb_each(t.chi_so) AS e WHERE t.{khoa} = ANY(%s) "
            "AND t.advertiser_id = ANY(%s) AND t.ngay BETWEEN %s AND %s "
            "AND jsonb_typeof(e.value) = 'number' "
            f"GROUP BY t.{khoa}, t.advertiser_id, e.key",
            (list(ma)[:TRA_CUU_TOI_DA], list(ids), tu, den)).fetchall()


def qc_doi_tuong_ngay(cap: str, ma: list[str], tu: datetime.date, den: datetime.date,
                      ids: list[str]) -> list[dict]:
    """Chuỗi theo ngày của từng đối tượng (cột số kiểu riêng), chỉ tài khoản `ids`."""
    if cap not in CAP_TRA_CUU or not ma or not ids:
        return []
    bang, khoa, _, _ = CAP_TRA_CUU[cap]
    with ket_noi() as c:
        return c.execute(f"SELECT {khoa} AS ma, advertiser_id AS tk, ngay, {_TONG} FROM {bang} "
                         f"WHERE {khoa} = ANY(%s) AND advertiser_id = ANY(%s) "
                         f"AND ngay BETWEEN %s AND %s GROUP BY {khoa}, advertiser_id, ngay "
                         f"ORDER BY {khoa}, advertiser_id, ngay",
                         (list(ma)[:TRA_CUU_TOI_DA], list(ids), tu, den)).fetchall()


def trang_thai_nhac(ncc: str = NCC) -> dict | None:
    """Cột KHÔNG bí mật của kết nối (Mark nhắc gia hạn — role `mark` chỉ được đọc đúng các cột
    này, xem schema.sql)."""
    with ket_noi() as c:
        return c.execute("SELECT nha_cung_cap, loai, trang_thai, refresh_het_luc, goi_ok_luc, "
                         "loi_cuoi FROM ket_noi_ngoai WHERE nha_cung_cap = %s", (ncc,)).fetchone()


# ───────────────────────────── kênh đăng (22/10/2026) ─────────────────────────────
#: Kênh đăng = danh tính một quảng cáo chạy dưới tên: TikTok identity (tài khoản chính chủ /
#: KOC / Spark Ads), Meta Trang (+ Instagram đi kèm). `qc_ad_kenh` một dòng mỗi ad (kênh của ad
#: không đổi — chỉ đọc một lần), `qc_kenh` tên kênh. Đọc trang: gộp `qc_ad_ngay` theo kênh.
#: Ad nền tảng không trả (đã xoá, Smart+ nâng cấp…) → dòng không kênh; hỏi lại sau chừng ấy ngày.
HOI_LAI_KHONG_THAY_NGAY = 7
#: Kênh đã hỏi tên mà không có (nhớ âm): TikTok — identity_get không trả danh tính đó, hỏi lại sau
#: 7 ngày; Meta — tên Trang / IG lỗi (thiếu quyền…), hỏi lại sau 1 ngày.
HOI_LAI_TEN_NGAY = {"tiktok": 7, "meta": 1}
#: Trần số kênh một lượt đọc (23/10/2026: trang lọc / xếp / chia trang ở Python trên ĐỦ kênh).
KENH_TOI_DA = 2000
_COT_AD_KENH = ("advertiser_id", "ad_id", "nen_tang", "kenh_id", "loai", "kenh_phu_id", "bai_id")


def sql_ad_chua_kenh() -> str:
    """ad_id CÓ phân phối (có dòng qc_ad_ngay) của một tài khoản chưa biết kênh — chi nhiều trước.
    Chỉ mã số (dạng nền tảng nhận; chốt chỉ đọc của tiktok_ads chặn mọi dạng khác)."""
    return ("SELECT q.ad_id FROM qc_ad_ngay q WHERE q.advertiser_id = %s "
            "AND q.ad_id ~ '^[0-9]{1,30}$' AND NOT EXISTS (SELECT 1 FROM qc_ad_kenh k "
            "WHERE k.advertiser_id = q.advertiser_id AND k.ad_id = q.ad_id "
            "AND (k.kenh_id IS NOT NULL OR k.cap_nhat_luc > now() - make_interval(days => %s))) "
            "GROUP BY q.ad_id ORDER BY sum(q.chi) DESC NULLS LAST, "
            "sum(q.hien_thi) DESC NULLS LAST, q.ad_id LIMIT %s")


def ad_chua_kenh(advertiser_id: str, n: int) -> list[str]:
    if n <= 0:
        return []
    with ket_noi() as c:
        return [r["ad_id"] for r in c.execute(
            sql_ad_chua_kenh(), (str(advertiser_id), HOI_LAI_KHONG_THAY_NGAY, int(n))).fetchall()]


def ghi_ad_kenh(rows: list[dict]) -> int:
    if not rows:
        return 0
    cot = ", ".join(_COT_AD_KENH)
    sua = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COT_AD_KENH[2:])
    sql = (f"INSERT INTO qc_ad_kenh ({cot}) VALUES ({', '.join(['%s'] * len(_COT_AD_KENH))}) "
           f"ON CONFLICT (advertiser_id, ad_id) DO UPDATE SET {sua}, cap_nhat_luc = now()")
    with ket_noi() as c, c.cursor() as cur:
        cur.executemany(sql, [tuple(r.get(k) for k in _COT_AD_KENH) for r in rows])
    return len(rows)


def sql_kenh_chua_ten() -> str:
    """Kênh (và Instagram đi kèm) của một tài khoản chưa có dòng qc_kenh, hoặc chưa có tên mà lần
    hỏi trước đã quá `HOI_LAI_TEN_NGAY` ngày (tham số)."""
    return ("SELECT DISTINCT x.kenh_id, x.loai FROM ("
            "SELECT kenh_id, loai FROM qc_ad_kenh WHERE advertiser_id = %s AND nen_tang = %s "
            "AND kenh_id IS NOT NULL UNION SELECT kenh_phu_id, 'instagram' FROM qc_ad_kenh "
            "WHERE advertiser_id = %s AND nen_tang = %s AND kenh_phu_id IS NOT NULL) x "
            "LEFT JOIN qc_kenh c ON c.nen_tang = %s AND c.kenh_id = x.kenh_id "
            "WHERE c.kenh_id IS NULL OR (c.ten IS NULL AND c.username IS NULL "
            "AND c.cap_nhat_luc < now() - make_interval(days => %s)) ORDER BY 1 LIMIT 500")


def kenh_chua_ten(nen_tang: str, advertiser_id: str) -> list[dict]:
    adv = str(advertiser_id)
    with ket_noi() as c:
        return c.execute(sql_kenh_chua_ten(), (adv, nen_tang, adv, nen_tang, nen_tang,
                                               HOI_LAI_TEN_NGAY.get(nen_tang, 1))).fetchall()


def ghi_kenh(rows: list[dict]) -> int:
    """Upsert tên kênh — giá trị trống không xoá tên đã biết."""
    if not rows:
        return 0
    sql = ("INSERT INTO qc_kenh (nen_tang, kenh_id, loai, ten, username) "
           "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (nen_tang, kenh_id) DO UPDATE SET "
           "loai = COALESCE(EXCLUDED.loai, qc_kenh.loai), "
           "ten = COALESCE(EXCLUDED.ten, qc_kenh.ten), "
           "username = COALESCE(EXCLUDED.username, qc_kenh.username), cap_nhat_luc = now()")
    with ket_noi() as c, c.cursor() as cur:
        cur.executemany(sql, [(r["nen_tang"], r["kenh_id"], r.get("loai"), r.get("ten"),
                               r.get("username")) for r in rows])
    return len(rows)


#: Cột xếp bảng kênh — chỉ nối chuỗi từ bảng cố định này.
SAP_KENH_SQL = {"chi": "g.chi", "hien_thi": "g.hien_thi"}


def sql_kenh_dang(cot: str) -> tuple[str, str]:
    """(1) tổng theo kênh (ad đã biết kênh), xếp + LIMIT, kèm tổng số kênh; (2) tổng phần đã biết /
    chưa biết kênh (độ phủ + dòng "Chưa xác định").
    23/10/2026 (chủ dự án hỏi hai dòng "HAPAS · Chính chủ"): một tài khoản TikTok có thể chạy dưới
    NHIỀU danh tính (TT_USER gắn thẳng tài khoản QC + BC_AUTH_TT qua Business Center) → gộp theo
    username khi đã biết (cùng @ = cùng kênh), chưa biết username thì theo mã danh tính."""
    tong_a = ", ".join(f"sum(q.{c}) AS {c}" for c in QC.TEN_COT_SO)
    gop = ", ".join(f"sum(a.{c})::float AS {c}" if c in QC.COT_TIEN else
                    f"sum(a.{c})::bigint AS {c}" for c in QC.TEN_COT_SO)
    kenh = (f"WITH a AS (SELECT q.advertiser_id, q.ad_id, {tong_a} FROM qc_ad_ngay q "
            "WHERE q.advertiser_id = ANY(%s) AND q.ngay BETWEEN %s AND %s "
            "GROUP BY q.advertiser_id, q.ad_id), "
            "g AS (SELECT k.nen_tang, min(k.kenh_id) AS kenh_id, max(k.loai) AS loai, "
            "max(c.ten) AS ten, max(c.username) AS username, "
            "(array_agg(k.kenh_phu_id ORDER BY a.hien_thi DESC NULLS LAST) "
            "FILTER (WHERE k.kenh_phu_id IS NOT NULL))[1] AS kenh_phu_id, "
            "array_agg(DISTINCT a.advertiser_id) AS tk_ids, count(*) AS so_ad, "
            f"{gop} FROM a JOIN qc_ad_kenh k ON k.advertiser_id = a.advertiser_id "
            "AND k.ad_id = a.ad_id LEFT JOIN qc_kenh c ON c.nen_tang = k.nen_tang "
            "AND c.kenh_id = k.kenh_id WHERE k.kenh_id IS NOT NULL "
            "GROUP BY k.nen_tang, COALESCE('u:' || lower(NULLIF(c.username, '')), k.kenh_id)) "
            "SELECT g.*, p.username AS phu_username, count(*) OVER () AS tong "
            "FROM g LEFT JOIN qc_kenh p ON p.nen_tang = g.nen_tang AND p.kenh_id = g.kenh_phu_id "
            f"ORDER BY {SAP_KENH_SQL[cot]} DESC NULLS LAST, g.hien_thi DESC NULLS LAST, g.kenh_id "
            "LIMIT %s")
    phu = (f"SELECT (k.kenh_id IS NOT NULL) AS biet, count(DISTINCT q.ad_id) AS so_ad, {_TONG} "
           "FROM qc_ad_ngay q LEFT JOIN qc_ad_kenh k ON k.advertiser_id = q.advertiser_id "
           "AND k.ad_id = q.ad_id WHERE q.advertiser_id = ANY(%s) AND q.ngay BETWEEN %s AND %s "
           "GROUP BY 1")
    return kenh, phu


def qc_kenh_dang(ids: list[str], tu: datetime.date, den: datetime.date, *, sap: str = "chi",
                 n: int = 20) -> dict:
    """Số theo kênh đăng của các tài khoản `ids` trong [tu, den]. -> {"rows" (≤ n kênh, xếp theo
    `sap` ∈ chi | hien_thi), "tong" (số kênh), "biet" / "chua_ro" (tổng phần ad đã / chưa biết
    kênh)}. Gọi viên kiểm `ids` theo phạm vi người xem và lọc tiền."""
    rong = {"rows": [], "tong": 0, "biet": {}, "chua_ro": {}}
    if not ids:
        return rong
    kenh, phu = sql_kenh_dang(sap if sap in SAP_KENH_SQL else "hien_thi")
    with ket_noi() as c:
        rows = c.execute(kenh, (list(ids), tu, den, max(1, min(int(n), KENH_TOI_DA)))).fetchall()
        tong = {bool(r["biet"]): r for r in c.execute(phu, (list(ids), tu, den)).fetchall()}
    return {"rows": rows, "tong": int(rows[0]["tong"]) if rows else 0,
            "biet": tong.get(True) or {}, "chua_ro": tong.get(False) or {}}
