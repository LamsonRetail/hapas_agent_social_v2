"""Kho yêu cầu SỐ TỨC THÌ của Mark (20/10/2026) — SQL của bảng `yeu_cau_tuc_thi`.

Chủ dự án 20/10/2026: "mark có quyền cao nhất có thể cào real time theo yêu cầu chứ ko chỉ đọc số
trên dashboard". Ba loại yêu cầu, MỘT bảng (dấu vết + trần đếm chung):
  • quang_cao — Mark xin một lượt đọc số TikTok / Meta Ads THEO PHẠM VI (tài khoản của bên người
    hỏi, ≤ 7 ngày gồm hôm nay). Mark CHỈ thêm dòng; lượt đọc chạy ở dịch vụ đồng bộ riêng
    (`dashboard/nghe_qc.py`, user lang_nghe_web, có khoá giải mã) — Mark không bao giờ cầm token.
    Trigger `yeu_cau_tuc_thi_bao` (schema.sql) gọi pg_notify('qc_tuc_thi', nhà cung cấp) khi thêm
    dòng chờ → bộ nghe nhận gần như ngay; bộ hẹn giờ 2 phút vẫn quét dòng chờ (dự phòng).
  • bai / kenh — Mark tự cào chỉ số bài / kênh ngay (Apify, trần nhỏ); dòng ghi để đếm trần mỗi
    người mỗi ngày + chi phí thật.
  • quet — Mark mở một lượt quét lắng nghe theo yêu cầu (đúng đường /theodoi của lịch quét);
    dòng ghi TRƯỚC khi tạo việc (dang_chay), đếm trần mỗi bên mỗi ngày.

Quyền tối thiểu (soát 20/10/2026 M5): Mark chỉ INSERT các cột yêu cầu — trạng thái do trigger
`yeu_cau_tuc_thi_chuan` đặt (có `loi` → tu_choi; quảng cáo → cho; còn lại → dang_chay); nhật ký
(`nhat_ky`, "mark_real_time", ai = email người hỏi) do trigger SECURITY DEFINER ghi — role mark không
có quyền ghi nhat_ky. RLS: Mark chỉ sửa dòng bài / kênh / quét.

Trần đếm NGUYÊN TỬ (L2): `tao(..., tran=[...])` giữ `pg_advisory_xact_lock` theo khoá của từng
trần (người / bên / dự án / nhà cung cấp), đếm rồi thêm trong CÙNG giao dịch — hai yêu cầu song song
không cùng lọt qua trần. Vượt trần → dòng tu_choi (dấu vết) + trả `vuot`.

Hàm Mark gọi (role `mark`, qua `hoi_dashboard_tool.KhoMark`): `tao`, `doc`, `gan_day_qc`, `dem`,
`cap_nhat`, `du_an_cua_link`, `du_an_cua_kenh`. Hàm bộ nghe gọi (role lang_nghe_web): `nhan_qc`,
`tra_lai`, `ket_thuc`, `don_dep`, `dem_chay_gio`. Chỉ SQL tham số hoá.
"""
from __future__ import annotations

import datetime
import json

from dashboard.kho import ket_noi

LOAI = ("quang_cao", "bai", "kenh", "quet")
TRANG_THAI = ("cho", "dang_chay", "xong", "loi", "bo_qua", "tu_choi")
HANH_DONG = "mark_real_time"
KENH_BAO = "qc_tuc_thi"            # kênh LISTEN/NOTIFY (trigger trong schema.sql)
TIM_TOI_DA = 200                   # chữ `tim` lưu trong chi_tiet (L5)
_COT = ("id, loai, nguoi_hoi, ben, nha_cung_cap, tai_khoan, tu, den, du_an, so_muc, chi_tiet, "
        "trang_thai, uoc_usd::float AS uoc_usd, chi_phi_usd::float AS chi_phi_usd, so_dong, "
        "so_tk_ok, loi, tao_luc, bat_dau_luc, xong_luc")


def _json(d) -> str:
    return json.dumps(d or {}, ensure_ascii=False, default=str, sort_keys=True)


def trang_thai_khi_them(loai: str, loi: str | None) -> str:
    """Như trigger `chuan_yeu_cau_tuc_thi` (schema.sql) — bản giả của bộ thử dùng lại."""
    return "tu_choi" if loi else ("cho" if loai == "quang_cao" else "dang_chay")


def khoa_tran(t: dict) -> str:
    """Khoá advisory của một trần: theo đúng chiều nó đếm (dự án không có bên đếm theo dự án)."""
    return "|".join(["tuc_thi", str(t.get("loai") or ""), str(t.get("nguoi_hoi") or ""),
                     str(t.get("ben") or ""), str(t.get("du_an") or ""),
                     str(t.get("nha_cung_cap") or "")])


def _sql_dem(loai: str, tu_luc, *, nguoi_hoi=None, ben=None, du_an=None, nha_cung_cap=None,
             cong_muc=False, trang_thai=None, nhom=None) -> tuple[str, list]:
    dk, ts = ["loai = %s", "tao_luc >= %s"], [loai, tu_luc]
    if trang_thai:
        dk.append("trang_thai = ANY(%s)")
        ts.append(list(trang_thai))
    else:
        dk.append("trang_thai NOT IN ('tu_choi', 'bo_qua')")
    for cot, v in (("nguoi_hoi", nguoi_hoi), ("ben", ben), ("du_an", du_an),
                   ("nha_cung_cap", nha_cung_cap)):
        if v is not None:
            dk.append(f"{cot} = %s")
            ts.append(v)
    if nhom is not None:
        # Một yêu cầu của người dùng có thể thành 2 dòng (TikTok + Meta): đếm theo NHÓM, bỏ nhóm
        # của chính yêu cầu đang xét (L5).
        gt = "count(DISTINCT COALESCE(chi_tiet->>'nhom', id::text))"
        dk.append("COALESCE(chi_tiet->>'nhom', '') <> %s")
        ts.append(str(nhom))
    else:
        gt = "COALESCE(sum(so_muc), 0)" if cong_muc else "count(*)"
    return f"SELECT {gt}::bigint AS n FROM yeu_cau_tuc_thi WHERE {' AND '.join(dk)}", ts


def _dem_c(c, t: dict) -> int:
    sql, ts = _sql_dem(t["loai"], t["tu_luc"], nguoi_hoi=t.get("nguoi_hoi"), ben=t.get("ben"),
                       du_an=t.get("du_an"), nha_cung_cap=t.get("nha_cung_cap"),
                       cong_muc=bool(t.get("cong_muc")), trang_thai=t.get("trang_thai"),
                       nhom=t.get("nhom"))
    r = c.execute(sql, tuple(ts)).fetchone()
    return int((r or {}).get("n") or 0)


def vuot_tran(dem_fn, tran: list[dict], so_muc: int) -> str | None:
    """Trần đầu tiên bị vượt nếu thêm yêu cầu này (`dem_fn(t)` = số đã dùng) → lý do, hoặc None."""
    for t in tran or ():
        them = so_muc if t.get("cong_muc") else 1
        if dem_fn(t) + them > int(t["toi_da"]):
            return str(t.get("ly_do") or "chạm trần")
    return None


def tao(loai: str, nguoi_hoi: str, *, ben: str | None = None, nha_cung_cap: str | None = None,
        tai_khoan: list[str] | None = None, tu: datetime.date | None = None,
        den: datetime.date | None = None, du_an: str | None = None, so_muc: int = 0,
        chi_tiet: dict | None = None, uoc_usd: float | None = None, loi: str | None = None,
        tran: list[dict] | None = None) -> dict:
    """Thêm MỘT yêu cầu (trạng thái do trigger đặt; nhật ký do trigger ghi). `tran`: các trần
    {loai, tu_luc, nguoi_hoi?/ben?/du_an?/nha_cung_cap?, cong_muc?, nhom?, toi_da, ly_do} kiểm
    NGUYÊN TỬ (khoá advisory theo từng trần, đếm + thêm cùng giao dịch); vượt → thêm dòng tu_choi
    với lý do. -> dòng vừa thêm (+ "vuot": lý do khi bị trần chặn)."""
    if loai not in LOAI:
        raise ValueError("loại yêu cầu không hợp lệ")
    ct = dict(chi_tiet or {})
    if isinstance(ct.get("tim"), str):
        ct["tim"] = ct["tim"][:TIM_TOI_DA]
    with ket_noi() as c:
        for k in sorted({khoa_tran(t) for t in tran or ()}):
            c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (k,))
        vuot = None if loi else vuot_tran(lambda t: _dem_c(c, t), tran or [], int(so_muc or 0))
        ly = loi or vuot
        r = c.execute(
            f"INSERT INTO yeu_cau_tuc_thi (loai, nguoi_hoi, ben, nha_cung_cap, tai_khoan, tu, den, "
            f"du_an, so_muc, chi_tiet, uoc_usd, loi) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
            f"%s::jsonb, %s, %s) RETURNING {_COT}",
            (loai, str(nguoi_hoi)[:254], ben, nha_cung_cap, sorted(set(tai_khoan or ())), tu, den,
             du_an, max(0, int(so_muc or 0)), _json(ct), uoc_usd,
             str(ly)[:500] if ly else None)).fetchone()
    return {**r, **({"vuot": vuot} if vuot else {})}


def doc(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT} FROM yeu_cau_tuc_thi WHERE id = ANY(%s) ORDER BY id",
                         ([int(x) for x in ids],)).fetchall()


def gan_day_qc(nha_cung_cap: str, phut: int) -> list[dict]:
    """Yêu cầu quảng cáo của một nhà cung cấp còn chờ / đang chạy, hoặc xong trong `phut` phút —
    Mark dùng lại thay vì xin lượt mới (giãn theo phạm vi)."""
    with ket_noi() as c:
        return c.execute(
            f"SELECT {_COT} FROM yeu_cau_tuc_thi WHERE loai = 'quang_cao' AND nha_cung_cap = %s "
            "AND (trang_thai IN ('cho', 'dang_chay') OR (trang_thai = 'xong' "
            "AND xong_luc >= now() - make_interval(mins => %s::int))) ORDER BY id DESC LIMIT 50",
            (nha_cung_cap, int(phut))).fetchall()


def dem(loai: str, tu_luc: datetime.datetime, *, nguoi_hoi: str | None = None,
        ben: str | None = None, du_an: str | None = None, nha_cung_cap: str | None = None,
        cong_muc: bool = False, trang_thai: tuple[str, ...] | None = None) -> int:
    """Số yêu cầu (hoặc tổng `so_muc` khi `cong_muc`) của `loai` từ `tu_luc`, KHÔNG tính dòng bị
    từ chối / bỏ qua (chưa tốn gì) — trừ khi `trang_thai` chỉ định. Chỉ để HIỂN THỊ; chặn trần
    dùng `tao(..., tran=…)` (nguyên tử)."""
    sql, ts = _sql_dem(loai, tu_luc, nguoi_hoi=nguoi_hoi, ben=ben, du_an=du_an,
                       nha_cung_cap=nha_cung_cap, cong_muc=cong_muc, trang_thai=trang_thai)
    with ket_noi() as c:
        r = c.execute(sql, tuple(ts)).fetchone()
    return int((r or {}).get("n") or 0)


def cap_nhat(yid: int, trang_thai: str, *, chi_phi_usd: float | None = None,
             loi: str | None = None, chi_tiet_them: dict | None = None) -> None:
    """Mark kết thúc yêu cầu bài / kênh / quét của chính nó (RLS chặn dòng quảng cáo)."""
    if trang_thai not in TRANG_THAI:
        raise ValueError("trạng thái không hợp lệ")
    with ket_noi() as c:
        c.execute("UPDATE yeu_cau_tuc_thi SET trang_thai = %s, chi_phi_usd = COALESCE(%s, "
                  "chi_phi_usd), loi = COALESCE(%s, loi), chi_tiet = chi_tiet || %s::jsonb, "
                  "xong_luc = CASE WHEN %s::text IN ('xong', 'loi', 'bo_qua') THEN now() "
                  "ELSE xong_luc END WHERE id = %s AND loai <> 'quang_cao'",
                  (trang_thai, chi_phi_usd, str(loi)[:500] if loi else None,
                   _json(chi_tiet_them), trang_thai, int(yid)))


def du_an_cua_link(links: list[str], khoa: list[str] | None = None) -> list[str]:
    """Dự án (mã) có bài mang đúng các link này — so cả `bai.khoa` (khoá dựng bằng ĐÚNG hàm lúc ghi
    bài, `theo_doi._khoa_bai`: "<nền tảng>:<id>") để link khác dạng (tham số, www…) vẫn khớp."""
    if not links and not khoa:
        return []
    with ket_noi() as c:
        return [r["du_an"] for r in c.execute(
            "SELECT DISTINCT du_an FROM bai WHERE link = ANY(%s) OR khoa = ANY(%s)",
            (list(links or [])[:50], list(khoa or [])[:50])).fetchall()]


def du_an_cua_kenh(dinh_danh: list[str]) -> list[str]:
    """Dự án có nguồn theo dõi mang định danh này (chữ thường, như `nguon.dinh_danh`)."""
    if not dinh_danh:
        return []
    with ket_noi() as c:
        return [r["du_an"] for r in c.execute(
            "SELECT DISTINCT du_an FROM nguon WHERE lower(dinh_danh) = ANY(%s)",
            ([str(x).lower() for x in dinh_danh][:20],)).fetchall()]


# ───────────────────────────── phía dịch vụ đồng bộ (lang_nghe_web) ─────────────────────────────
def nhan_qc(nha_cung_cap: str, toi_da: int = 20) -> list[dict]:
    """Nhận MỌI yêu cầu quảng cáo đang chờ của nhà cung cấp (FOR UPDATE SKIP LOCKED — bộ nghe và
    bộ hẹn giờ dự phòng không bao giờ nhận trùng) → đặt dang_chay. Bộ nghe gộp chúng thành MỘT
    lượt (hợp tài khoản, khoảng ngày rộng nhất)."""
    with ket_noi() as c:
        return c.execute(
            f"UPDATE yeu_cau_tuc_thi SET trang_thai = 'dang_chay', bat_dau_luc = now() "
            f"WHERE id IN (SELECT id FROM yeu_cau_tuc_thi WHERE loai = 'quang_cao' "
            f"AND nha_cung_cap = %s AND trang_thai = 'cho' ORDER BY id LIMIT %s "
            f"FOR UPDATE SKIP LOCKED) RETURNING {_COT}", (nha_cung_cap, int(toi_da))).fetchall()


def tra_lai(ids: list[int]) -> None:
    """Lượt đồng bộ khác đang giữ khoá: trả yêu cầu về hàng chờ (lượt sau nhận lại)."""
    if ids:
        with ket_noi() as c:
            c.execute("UPDATE yeu_cau_tuc_thi SET trang_thai = 'cho', bat_dau_luc = NULL "
                      "WHERE id = ANY(%s) AND trang_thai = 'dang_chay'", (list(ids),))


def ket_thuc(ids: list[int], trang_thai: str, *, so_dong: int | None = None,
             so_tk_ok: int | None = None, loi: str | None = None,
             chi_tiet_them: dict | None = None) -> None:
    """Kết thúc yêu cầu. Bộ nghe gọi TỪNG dòng khi gộp lượt (soát N1): `so_tk_ok` = tài khoản CỦA
    DÒNG ĐÓ đọc được, `chi_tiet_them` = {tk_doc, tk_hong} của dòng."""
    if ids:
        with ket_noi() as c:
            c.execute("UPDATE yeu_cau_tuc_thi SET trang_thai = %s, so_dong = %s, so_tk_ok = %s, "
                      "loi = %s, chi_tiet = chi_tiet || %s::jsonb, xong_luc = now() "
                      "WHERE id = ANY(%s)",
                      (trang_thai, so_dong, so_tk_ok, str(loi)[:500] if loi else None,
                       _json(chi_tiet_them), list(ids)))


def don_dep(nha_cung_cap: str, cho_phut: int = 15, chay_phut: int = 60) -> int:
    """Yêu cầu quảng cáo chờ quá `cho_phut` phút → bo_qua (người hỏi đã nhận câu trả lời từ số
    cũ); đang chạy quá `chay_phut` phút (tiến trình chết giữa lượt) → loi — cả dòng bài / kênh /
    quét của Mark kẹt dang_chay (Mark chết giữa chừng, L3). -> số dòng đổi."""
    with ket_noi() as c:
        a = c.execute("UPDATE yeu_cau_tuc_thi SET trang_thai = 'bo_qua', xong_luc = now(), "
                      "loi = 'quá hạn chờ — chưa có lượt đọc nào nhận' WHERE loai = 'quang_cao' "
                      "AND nha_cung_cap = %s AND trang_thai = 'cho' "
                      "AND tao_luc < now() - make_interval(mins => %s::int)",
                      (nha_cung_cap, int(cho_phut))).rowcount
        b = c.execute("UPDATE yeu_cau_tuc_thi SET trang_thai = 'loi', xong_luc = now(), "
                      "loi = 'dừng bất thường (kẹt đang chạy)' WHERE trang_thai = 'dang_chay' "
                      "AND ((loai = 'quang_cao' AND nha_cung_cap = %s) OR loai <> 'quang_cao') "
                      "AND bat_dau_luc < now() - make_interval(mins => %s::int)",
                      (nha_cung_cap, int(chay_phut))).rowcount
    return int(a or 0) + int(b or 0)


def dem_chay_gio(nha_cung_cap: str) -> int:
    """Số LƯỢT đọc tức thì (đã bắt đầu, mỗi lượt có thể gộp nhiều yêu cầu — đếm theo mốc bắt đầu
    khác nhau) của nhà cung cấp trong 60 phút qua — trần toàn hệ thống ở phía dịch vụ."""
    with ket_noi() as c:
        r = c.execute("SELECT count(DISTINCT bat_dau_luc)::bigint AS n FROM yeu_cau_tuc_thi "
                      "WHERE loai = 'quang_cao' AND nha_cung_cap = %s "
                      "AND trang_thai IN ('dang_chay', 'xong', 'loi') "
                      "AND bat_dau_luc >= now() - interval '1 hour'", (nha_cung_cap,)).fetchone()
    return int((r or {}).get("n") or 0)
