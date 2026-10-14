"""Kho dữ liệu lắng nghe (DB `lang_nghe` trên Postgres của VPS) — phía Mark.

Đợt 2 (chủ dự án chốt 14/10/2026): danh sách nguồn theo dõi, ngân sách tháng và bài đã quét
nằm trong MỘT DB riêng trên VPS, dùng chung với dashboard `social.hapas.vn`. Dashboard quản
lý dự án/nguồn/ngân sách; Mark chỉ ĐỌC cấu hình và GHI kết quả (quyền DB tách bằng role, xem
`deploy/lang-nghe/schema.sql`). Kỹ năng, công tắc, trần mỗi lượt và lịch của Mark vẫn ở console
platform — module này không đọc/ghi gì của platform.

Kết nối: Unix socket + peer (user hệ điều hành `mark` = role `mark`), không mật khẩu. Đổi bằng
`LANG_NGHE_DSN` (vd khi thử trên máy khác). Lỗi KHÔNG bao giờ in DSN — chỉ tên loại lỗi.

Thời gian lưu TIMESTAMPTZ; "ngày" và "tháng" luôn tính theo giờ VN (`_TZ`).
"""
from __future__ import annotations

import contextlib
import os

_TZ = "Asia/Ho_Chi_Minh"
#: Lượt `theo_doi` còn `dang_chay` quá chừng này coi như bỏ dở (bot tắt giữa chừng).
GIO_BO_DO = 3
#: Cho phép quét sớm hơn đúng chu kỳ chừng này giờ: lịch 08:30 hằng ngày mà hôm qua lượt
#: xong lúc 08:40 thì hôm nay vẫn tới hạn.
GIO_DUNG_SAI = 3


class LoiKho(RuntimeError):
    """Không dùng được kho (thiếu thư viện, chưa cài DB, mất kết nối, thiếu quyền)."""


def _dsn() -> str:
    return (os.environ.get("LANG_NGHE_DSN") or "").strip() or "dbname=lang_nghe"


@contextlib.contextmanager
def ket_noi():
    """Một kết nối + một giao dịch: xong thì commit, lỗi thì rollback, luôn đóng."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise LoiKho("máy chạy Mark chưa cài thư viện psycopg (kho lắng nghe chưa bật)") from None
    try:
        conn = psycopg.connect(_dsn(), connect_timeout=5, row_factory=dict_row)
    except psycopg.Error as e:
        raise LoiKho(f"không nối được kho lắng nghe ({type(e).__name__})") from None
    try:
        with conn:
            yield conn
    except psycopg.Error as e:
        raise LoiKho(f"kho lắng nghe báo lỗi ({type(e).__name__}: "
                     f"{(getattr(e, 'sqlstate', '') or '')})") from None
    finally:
        conn.close()


# ───────────────────────────── đọc cấu hình ─────────────────────────────
def doc_du_an(ma: str) -> dict | None:
    with ket_noi() as c:
        return c.execute(
            "SELECT ma, ten, tu_khoa, tu_loai_tru, boi_canh, thi_truong, "
            "tran_usd_thang::float AS tran_usd_thang, dang_bat, bl_bat, bl_so_bai, bl_moi_bai "
            "FROM du_an WHERE ma = %s",
            (ma,)).fetchone()


def cac_du_an() -> list[dict]:
    with ket_noi() as c:
        return c.execute("SELECT ma, ten, dang_bat FROM du_an ORDER BY ma").fetchall()


def du_an_dang_bat() -> list[dict]:
    """Dự án đang bật kèm từ khoá — để lượt tìm theo từ khoá biết ghi bài vào dự án nào."""
    with ket_noi() as c:
        return c.execute("SELECT ma, ten, tu_khoa FROM du_an WHERE dang_bat ORDER BY ma").fetchall()


def nguon_cua_du_an(ma: str) -> list[dict]:
    """Mọi nguồn của dự án (kể cả tạm dừng): để gắn bài tìm theo từ khoá về nguồn đã có và
    không đề xuất lại nguồn đã nằm trong danh sách."""
    with ket_noi() as c:
        return c.execute("SELECT id, nen_tang, dinh_danh FROM nguon WHERE du_an = %s",
                         (ma,)).fetchall()


def nguon_toi_han(ma: str) -> list[dict]:
    """Nguồn đang theo dõi đã tới hạn quét (chưa quét lần nào, hoặc lần cuối cách đây ≥ chu
    kỳ − `GIO_DUNG_SAI` giờ). Nguồn chưa quét lần nào đi trước."""
    with ket_noi() as c:
        return c.execute(
            "SELECT id, nen_tang, dinh_danh, ten, link, loai, so_bai_moi_lan, chu_ky_ngay, "
            "quet_cuoi FROM nguon WHERE du_an = %s AND trang_thai = 'dang_theo_doi' AND "
            "(quet_cuoi IS NULL OR quet_cuoi <= now() - make_interval(days => chu_ky_ngay) "
            "+ make_interval(hours => %s)) ORDER BY quet_cuoi NULLS FIRST, id",
            (ma, GIO_DUNG_SAI)).fetchall()


def dem_nguon(ma: str) -> dict:
    """{'dang_theo_doi': n, 'tam_dung': m} — để câu trả lời nói rõ vì sao không có gì quét."""
    with ket_noi() as c:
        rows = c.execute("SELECT trang_thai, count(*) AS n FROM nguon WHERE du_an = %s "
                         "GROUP BY trang_thai", (ma,)).fetchall()
    return {r["trang_thai"]: int(r["n"]) for r in rows}


def da_tieu_thang(ma: str) -> float:
    """USD thật các lượt `theo_doi` của dự án đã tiêu trong tháng hiện tại (giờ VN)."""
    with ket_noi() as c:
        r = c.execute(
            "SELECT COALESCE(sum(chi_phi_usd), 0)::float AS usd FROM luot_quet "
            "WHERE du_an = %s AND kieu = 'theo_doi' AND bat_dau >= "
            "(date_trunc('month', now() AT TIME ZONE %s) AT TIME ZONE %s)",
            (ma, _TZ, _TZ)).fetchone()
    return float(r["usd"] or 0)


# ───────────────────────────── lượt quét ─────────────────────────────
def luot_dang_chay(ma: str) -> dict | None:
    """Lượt theo dõi khác của cùng dự án còn đang chạy (trong `GIO_BO_DO` giờ) — có thì
    không mở lượt mới, kẻo hai lượt cùng tiêu một phần ngân sách."""
    with ket_noi() as c:
        return c.execute(
            "SELECT id, ma_viec, bat_dau FROM luot_quet WHERE du_an = %s AND kieu = 'theo_doi' "
            "AND trang_thai = 'dang_chay' AND bat_dau > now() - make_interval(hours => %s) "
            "ORDER BY id DESC LIMIT 1", (ma, GIO_BO_DO)).fetchone()


def mo_luot(ma: str, kieu: str, *, ma_viec: str | None = None,
            job_id: str | None = None) -> int:
    """Mở lượt mới; đóng luôn các lượt cùng dự án bị bỏ dở quá `GIO_BO_DO` giờ."""
    with ket_noi() as c:
        c.execute(
            "UPDATE luot_quet SET trang_thai = 'loi', ket_thuc = now(), "
            "loi = COALESCE(loi, 'bỏ dở (bot dừng giữa chừng)') WHERE du_an = %s AND "
            "kieu = %s AND trang_thai = 'dang_chay' AND bat_dau <= now() - "
            "make_interval(hours => %s)", (ma, kieu, GIO_BO_DO))
        r = c.execute(
            "INSERT INTO luot_quet (du_an, kieu, ma_viec, job_id) VALUES (%s, %s, %s, %s) "
            "RETURNING id", (ma, kieu, ma_viec, job_id)).fetchone()
    return int(r["id"])


def dong_luot(luot_id: int, *, trang_thai: str, so_nguon: int = 0, so_nguon_loi: int = 0,
              bai_moi: int = 0, bai_cap_nhat: int = 0, chi_phi_usd: float = 0.0,
              loi: str | None = None, ghi_chu: str | None = None) -> None:
    with ket_noi() as c:
        c.execute(
            "UPDATE luot_quet SET trang_thai = %s, ket_thuc = now(), so_nguon = %s, "
            "so_nguon_loi = %s, bai_moi = %s, bai_cap_nhat = %s, chi_phi_usd = %s, loi = %s, "
            "ghi_chu = %s WHERE id = %s",
            (trang_thai, so_nguon, so_nguon_loi, bai_moi, bai_cap_nhat,
             round(float(chi_phi_usd or 0), 4), (loi or None) and str(loi)[:500],
             (ghi_chu or None) and str(ghi_chu)[:2000], luot_id))


def danh_dau_nguon(da_quet: list[int], loi: dict[int, str]) -> None:
    """Nguồn quét được: ghi `quet_cuoi`, xoá lỗi cũ. Nguồn lỗi: ghi lỗi, KHÔNG dời `quet_cuoi`
    (lượt sau thử lại)."""
    with ket_noi() as c:
        if da_quet:
            c.execute("UPDATE nguon SET quet_cuoi = now(), loi_cuoi = NULL, loi_luc = NULL "
                      "WHERE id = ANY(%s)", (list(da_quet),))
        for nid, ly_do in loi.items():
            c.execute("UPDATE nguon SET loi_cuoi = %s, loi_luc = now() WHERE id = %s",
                      (str(ly_do)[:300], nid))


# ───────────────────────────── bài ─────────────────────────────
_COT_BAI = ("khoa", "nen_tang", "nguon_id", "link", "tac_gia", "tai_khoan", "followers",
            "dang_luc", "noi_dung", "hashtag", "khop_tu_khoa", "sac_thai", "chu_de", "ly_do_giu",
            "xem", "thich", "binh_luan", "chia_se")
_SO = ("xem", "thich", "binh_luan", "chia_se")


def ghi_bai(ma: str, luot_id: int, kieu: str, rows: list[dict]) -> tuple[int, int]:
    """Upsert bài đã giữ + số liệu của ngày hôm nay (giờ VN). -> (bài mới, bài cập nhật).

    Bài đã có: số liệu lấy bản mới; nhãn AI (sắc thái/chủ đề) chỉ đè khi lượt này có nhãn;
    bài từng vào bằng `theo_doi` thì giữ nguyên kiểu đó (quét từ khoá về sau không hạ cấp)."""
    if not rows:
        return 0, 0
    cot = ", ".join(_COT_BAI)
    # Nguồn có thể bị xoá trên dashboard giữa lượt quét: lấy id qua truy vấn con để nguồn đã
    # xoá thành NULL, không làm hỏng khoá ngoại (và rollback) cả lô bài đã trả tiền.
    dat = ", ".join("(SELECT id FROM nguon WHERE id = %s)" if k == "nguon_id" else "%s"
                    for k in _COT_BAI)
    moi = cu = 0
    with ket_noi() as c:
        for r in rows:
            gia_tri = [r.get(k) for k in _COT_BAI]
            x = c.execute(
                f"INSERT INTO bai (du_an, kieu_quet, luot_dau, luot_cuoi, {cot}) "
                f"VALUES (%s, %s, %s, %s, {dat}) "
                "ON CONFLICT (du_an, khoa) DO UPDATE SET "
                "xem = COALESCE(EXCLUDED.xem, bai.xem), thich = COALESCE(EXCLUDED.thich, bai.thich), "
                "binh_luan = COALESCE(EXCLUDED.binh_luan, bai.binh_luan), "
                "chia_se = COALESCE(EXCLUDED.chia_se, bai.chia_se), "
                "followers = COALESCE(EXCLUDED.followers, bai.followers), "
                "sac_thai = COALESCE(EXCLUDED.sac_thai, bai.sac_thai), "
                "chu_de = COALESCE(EXCLUDED.chu_de, bai.chu_de), "
                "nguon_id = COALESCE(bai.nguon_id, EXCLUDED.nguon_id), "
                "kieu_quet = CASE WHEN bai.kieu_quet = 'theo_doi' THEN 'theo_doi' "
                "ELSE EXCLUDED.kieu_quet END, "
                "cap_nhat_cuoi = now(), luot_cuoi = EXCLUDED.luot_cuoi "
                "RETURNING (xmax = 0) AS moi",
                [ma, kieu, luot_id, luot_id, *gia_tri]).fetchone()
            if x and x["moi"]:
                moi += 1
            else:
                cu += 1
            if any(r.get(k) is not None for k in _SO):
                c.execute(
                    "INSERT INTO chi_so_ngay (du_an, khoa, ngay, xem, thich, binh_luan, chia_se) "
                    "VALUES (%s, %s, (now() AT TIME ZONE %s)::date, %s, %s, %s, %s) "
                    "ON CONFLICT (du_an, khoa, ngay) DO UPDATE SET xem = EXCLUDED.xem, "
                    "thich = EXCLUDED.thich, binh_luan = EXCLUDED.binh_luan, "
                    "chia_se = EXCLUDED.chia_se",
                    [ma, r["khoa"], _TZ, *[r.get(k) for k in _SO]])
    return moi, cu


def cap_nhat_so_lieu(ma: str, luot_id: int, rows: list[dict]) -> int:
    """CHỈ cập nhật số liệu của bài ĐÃ CÓ (+ số của ngày hôm nay). -> số bài cập nhật được.

    Không đi qua `ghi_bai`: dòng chỉ có số thì INSERT thiếu cột NOT NULL — Postgres kiểm
    NOT NULL trước khi xét ON CONFLICT nên hỏng cả lô (review 14/10)."""
    n = 0
    with ket_noi() as c:
        for r in rows:
            x = c.execute(
                "UPDATE bai SET xem = COALESCE(%s, xem), thich = COALESCE(%s, thich), "
                "binh_luan = COALESCE(%s, binh_luan), chia_se = COALESCE(%s, chia_se), "
                "cap_nhat_cuoi = now(), luot_cuoi = %s WHERE du_an = %s AND khoa = %s "
                "RETURNING khoa", [*[r.get(k) for k in _SO], luot_id, ma, r["khoa"]]).fetchone()
            if not x:
                continue
            n += 1
            c.execute(
                "INSERT INTO chi_so_ngay (du_an, khoa, ngay, xem, thich, binh_luan, chia_se) "
                "VALUES (%s, %s, (now() AT TIME ZONE %s)::date, %s, %s, %s, %s) "
                "ON CONFLICT (du_an, khoa, ngay) DO UPDATE SET xem = EXCLUDED.xem, "
                "thich = EXCLUDED.thich, binh_luan = EXCLUDED.binh_luan, "
                "chia_se = EXCLUDED.chia_se",
                [ma, r["khoa"], _TZ, *[r.get(k) for k in _SO]])
    return n


def bai_youtube_can_lam_moi(ma: str, ngay: int = 14, toi_da: int = 200) -> list[dict]:
    """Bài YouTube đã giữ, đăng trong `ngay` ngày, chưa đọc số hôm nay (giờ VN). videos.list
    miễn phí (1 đơn vị/50 video) nên cập nhật được hằng ngày mà không tốn Apify."""
    with ket_noi() as c:
        return c.execute(
            "SELECT khoa, link FROM bai WHERE du_an = %s AND nen_tang = 'youtube' AND "
            "dang_luc >= now() - make_interval(days => %s) AND "
            "cap_nhat_cuoi < (date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s) "
            "ORDER BY dang_luc DESC LIMIT %s", (ma, ngay, _TZ, _TZ, toi_da)).fetchall()


# ───────────────────────────── bình luận (đợt 2b, 15/10/2026) ─────────────────────────────
#: Bài đã cào được cào lại khi số bình luận nền tảng báo tăng ≥ 20% (và ≥ 5) — bài cũ ít đổi
#: thì không trả tiền đọc lại cùng bình luận.
BL_TANG_TOI_THIEU = 1.2
BL_NGAY = 35


def bai_can_lay_binh_luan(ma: str, nen_tang: list[str], toi_da: int) -> list[dict]:
    """Bài nên cào bình luận lượt này: đăng trong `BL_NGAY` ngày, nền tảng báo có bình luận,
    chưa cào hoặc bình luận tăng đủ nhiều. Bài chưa cào đi trước, rồi bài nhiều bình luận."""
    if toi_da <= 0 or not nen_tang:
        return []
    with ket_noi() as c:
        return c.execute(
            "SELECT b.khoa, b.nen_tang, b.link, b.tai_khoan, b.tac_gia, b.binh_luan, "
            "b.bl_lay_luc, n.loai AS nguon_loai FROM bai b LEFT JOIN nguon n ON n.id = b.nguon_id "
            "WHERE b.du_an = %s AND b.nen_tang = ANY(%s) AND COALESCE(b.binh_luan, 0) > 0 "
            "AND b.link <> '' AND b.dang_luc >= now() - make_interval(days => %s) "
            "AND (b.bl_lay_luc IS NULL OR (b.bl_lay_luc < now() - interval '20 hours' AND "
            " b.binh_luan >= COALESCE(b.bl_lay_khi_co, 0) * %s + 5)) "
            "ORDER BY (b.bl_lay_luc IS NULL) DESC, b.binh_luan DESC LIMIT %s",
            (ma, list(nen_tang), BL_NGAY, BL_TANG_TOI_THIEU, toi_da)).fetchall()


_COT_BL = ("ma", "nen_tang", "tac_gia", "noi_dung", "thich", "tra_loi", "la_tra_loi",
           "cua_thuong_hieu", "dang_luc", "sac_thai", "chu_de")


def ghi_binh_luan(ma: str, luot_id: int, rows: list[dict],
                  da_lay: dict[str, tuple[int, int | None]]) -> tuple[int, int]:
    """Upsert bình luận (mỗi dòng có `khoa_bai` + `_COT_BL`) và đánh dấu bài đã cào
    (`da_lay` = {khoa bài: (số bình luận lấy được, số nền tảng báo lúc đó)}) trong CÙNG giao
    dịch. Nhãn chỉ đè khi lượt này có nhãn. -> (mới, cập nhật)."""
    moi = cu = 0
    cot = ", ".join(_COT_BL)
    dat = ", ".join(["%s"] * len(_COT_BL))
    with ket_noi() as c:
        for r in rows:
            x = c.execute(
                f"INSERT INTO binh_luan (du_an, khoa_bai, luot_id, {cot}) "
                f"SELECT %s, %s, %s, {dat} WHERE EXISTS "
                "(SELECT 1 FROM bai WHERE du_an = %s AND khoa = %s) "
                "ON CONFLICT (du_an, khoa_bai, ma) DO UPDATE SET "
                "thich = COALESCE(EXCLUDED.thich, binh_luan.thich), "
                "tra_loi = COALESCE(EXCLUDED.tra_loi, binh_luan.tra_loi), "
                "sac_thai = COALESCE(EXCLUDED.sac_thai, binh_luan.sac_thai), "
                "chu_de = COALESCE(EXCLUDED.chu_de, binh_luan.chu_de), "
                "luot_id = EXCLUDED.luot_id, cap_nhat_cuoi = now() "
                "RETURNING (xmax = 0) AS moi",
                [ma, r["khoa_bai"], luot_id, *[r.get(k) for k in _COT_BL],
                 ma, r["khoa_bai"]]).fetchone()
            if not x:
                continue
            if x["moi"]:
                moi += 1
            else:
                cu += 1
        for khoa, (n, co) in da_lay.items():
            c.execute("UPDATE bai SET bl_lay_luc = now(), bl_da_lay = %s, "
                      "bl_lay_khi_co = COALESCE(%s, binh_luan) WHERE du_an = %s AND khoa = %s",
                      (n, co, ma, khoa))
    return moi, cu


def ghi_de_xuat(ma: str, cac: list[dict]) -> int:
    """Nguồn nổi mà chưa theo dõi -> hàng chờ duyệt. Nguồn đã bị từ chối thì chỉ cập nhật
    số, không bật lại; nguồn đã trong danh sách thì bỏ qua. -> số dòng mới."""
    if not cac:
        return 0
    moi = 0
    with ket_noi() as c:
        for x in cac:
            co = c.execute("SELECT 1 FROM nguon WHERE du_an = %s AND nen_tang = %s AND "
                           "dinh_danh = %s", (ma, x["nen_tang"], x["dinh_danh"])).fetchone()
            if co:
                continue
            r = c.execute(
                "INSERT INTO de_xuat (du_an, nen_tang, dinh_danh, ten, link, ly_do, so_bai, "
                "thao_luan) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (du_an, nen_tang, dinh_danh) DO UPDATE SET ten = EXCLUDED.ten, "
                "link = EXCLUDED.link, ly_do = EXCLUDED.ly_do, so_bai = EXCLUDED.so_bai, "
                "thao_luan = EXCLUDED.thao_luan RETURNING (xmax = 0) AS moi",
                (ma, x["nen_tang"], x["dinh_danh"], str(x.get("ten") or "")[:200],
                 str(x.get("link") or "")[:500], str(x.get("ly_do") or "")[:300],
                 int(x.get("so_bai") or 0), int(x.get("thao_luan") or 0))).fetchone()
            moi += 1 if r and r["moi"] else 0
    return moi
