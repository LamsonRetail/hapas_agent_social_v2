"""Kho dữ liệu lắng nghe (DB `lang_nghe` trên Postgres của VPS) — phía Mark.

Đợt 2 (chủ dự án chốt 14/10/2026): danh sách nguồn theo dõi, ngân sách tháng và bài đã quét
nằm trong MỘT DB riêng trên VPS, dùng chung với dashboard `social.hapas.vn`. Dashboard quản
lý dự án/nguồn/ngân sách; Mark chỉ ĐỌC cấu hình và GHI kết quả (quyền DB tách bằng role, xem
`deploy/lang-nghe/schema.sql`). Kỹ năng, công tắc, trần mỗi lượt và lịch của Mark vẫn ở console
platform — module này không đọc/ghi gì của platform. Riêng lịch quét TỰ ĐỘNG (chủ dự án chốt
15/10/2026) đặt trên dashboard, bảng `lich_quet`: Mark đọc lịch, chỉ ghi cột trạng thái chạy.

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
            "tran_usd_thang::float AS tran_usd_thang, dang_bat, bl_bat, bl_so_bai, bl_moi_bai, "
            "tk_bat, tk_so_bai, cau_hinh "
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


def nguon_dang_theo_doi(ma: str) -> list[dict]:
    """MỌI nguồn đang theo dõi, không xét chu kỳ — lượt theo lịch có `quet_moi_nguon` (chiến
    dịch, 15/10/2026) quét hết mỗi lượt. Nguồn lâu chưa quét đi trước (trần `TOI_DA_NGUON`)."""
    with ket_noi() as c:
        return c.execute(
            "SELECT id, nen_tang, dinh_danh, ten, link, loai, so_bai_moi_lan, chu_ky_ngay, "
            "quet_cuoi FROM nguon WHERE du_an = %s AND trang_thai = 'dang_theo_doi' "
            "ORDER BY quet_cuoi NULLS FIRST, id", (ma,)).fetchall()


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
            job_id: str | None = None, lich_id: int | None = None) -> int:
    """Mở lượt mới; đóng luôn các lượt cùng dự án bị bỏ dở quá `GIO_BO_DO` giờ. `lich_id`: lượt
    do lịch quét tự động (bảng `lich_quet`) giao — chỉ ghi cột này khi có (lịch bị xoá giữa
    chừng thì thành NULL, không hỏng khoá ngoại)."""
    with ket_noi() as c:
        c.execute(
            "UPDATE luot_quet SET trang_thai = 'loi', ket_thuc = now(), "
            "loi = COALESCE(loi, 'bỏ dở (bot dừng giữa chừng)') WHERE du_an = %s AND "
            "kieu = %s AND trang_thai = 'dang_chay' AND bat_dau <= now() - "
            "make_interval(hours => %s)", (ma, kieu, GIO_BO_DO))
        if lich_id:
            r = c.execute(
                "INSERT INTO luot_quet (du_an, kieu, ma_viec, job_id, lich_id) VALUES "
                "(%s, %s, %s, %s, (SELECT id FROM lich_quet WHERE id = %s)) RETURNING id",
                (ma, kieu, ma_viec, job_id, int(lich_id))).fetchone()
        else:
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
            "xem", "thich", "binh_luan", "chia_se", "ma_noi_dung")
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
    import loc_rac
    moi = cu = 0
    with ket_noi() as c:
        for r in rows:
            r = {**r, "ma_noi_dung": r.get("ma_noi_dung") or loc_rac.ma_noi_dung(
                r.get("noi_dung") or "", loc_rac.BAI_TRUNG_TOI_THIEU_CHU)}
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
                "ma_noi_dung = COALESCE(EXCLUDED.ma_noi_dung, bai.ma_noi_dung), "
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


def co_bai_tu_khoa(ma: str) -> bool:
    """Dự án đã từng có bài tìm theo từ khoá chưa (lần đầu thì lùi xa hơn)."""
    with ket_noi() as c:
        return bool(c.execute("SELECT EXISTS (SELECT 1 FROM bai WHERE du_an = %s AND "
                              "kieu_quet = 'tu_khoa') AS co", (ma,)).fetchone()["co"])


# ───────────────────────────── bình luận (đợt 2b, 15/10/2026) ─────────────────────────────
#: Bài đã cào được cào lại khi số bình luận nền tảng báo tăng ≥ 20% (và ≥ 5) — bài cũ ít đổi
#: thì không trả tiền đọc lại cùng bình luận.
BL_TANG_TOI_THIEU = 1.1
#: Đã cào dưới 80% số nền tảng báo lúc cào = chưa đủ → lượt sau cào tiếp (đợt 2d: cào HẾT).
BL_DU_TOI_THIEU = 0.8
BL_NGAY = 35


def bai_can_lay_binh_luan(ma: str, nen_tang: list[str], toi_da: int,
                          cao_het: bool = False) -> list[dict]:
    """Bài nên cào bình luận lượt này: đăng trong `BL_NGAY` ngày, nền tảng báo có bình luận,
    chưa cào hoặc bình luận tăng đủ nhiều. Bài chưa cào đi trước, rồi bài nhiều bình luận."""
    if toi_da <= 0 or not nen_tang:
        return []
    with ket_noi() as c:
        return c.execute(
            "SELECT b.khoa, b.nen_tang, b.link, b.tai_khoan, b.tac_gia, b.binh_luan, "
            "b.bl_lay_luc, b.bl_da_lay, b.bl_lay_khi_co, n.loai AS nguon_loai "
            "FROM bai b LEFT JOIN nguon n ON n.id = b.nguon_id "
            "WHERE b.du_an = %s AND b.nen_tang = ANY(%s) AND COALESCE(b.binh_luan, 0) > 0 "
            "AND b.link <> '' AND b.dang_luc >= now() - make_interval(days => %s) "
            "AND (b.bl_lay_luc IS NULL "
            # Cào hết mà lần trước chưa đủ (chạm trần chi phí / actor dừng sớm): cào bù tới khi
            # đủ, miễn mỗi lần còn lấy THÊM được bình luận; dừng sau 2 lần liên tiếp không thêm
            # gì (review 15/10: Instagram chưa đăng nhập, bài ẩn bình luận không bao giờ đủ —
            # không trả tiền mỗi ngày cho cùng bình luận).
            " OR (%s AND b.nen_tang <> 'instagram' AND b.bl_lan_thieu < 2 AND "
            "     b.bl_lay_luc < now() - interval '20 hours' AND "
            "     COALESCE(b.bl_da_lay, 0) < COALESCE(b.bl_lay_khi_co, 0) * %s) "
            # Có thêm bình luận đáng kể: ≥ 20 hoặc ≥ 10% (+3) so với lúc cào.
            " OR (b.bl_lay_luc < now() - interval '20 hours' AND "
            "     b.binh_luan > COALESCE(b.bl_lay_khi_co, 0) AND "
            "     (b.binh_luan - COALESCE(b.bl_lay_khi_co, 0) >= 20 OR "
            "      b.binh_luan >= COALESCE(b.bl_lay_khi_co, 0) * %s + 3))) "
            "ORDER BY (b.bl_lay_luc IS NULL) DESC, "
            "b.binh_luan - COALESCE(b.bl_da_lay, 0) DESC LIMIT %s",
            (ma, list(nen_tang), BL_NGAY, bool(cao_het), BL_DU_TOI_THIEU, BL_TANG_TOI_THIEU,
             toi_da)).fetchall()


_COT_BL = ("ma", "nen_tang", "tac_gia", "noi_dung", "thich", "tra_loi", "la_tra_loi",
           "cua_thuong_hieu", "dang_luc", "sac_thai", "chu_de", "loai", "ly_do_loc",
           "ma_noi_dung", "link", "ma_cha")
#: Nhãn chỉ xét được trên KHO (cần lịch sử nhiều tài khoản / nhiều bình luận), không phải từ một
#: bình luận: cào lại thấy bình luận "hợp lệ" thì vẫn giữ nhãn kho, không gửi lại AI.
_NHAN_KHO = "(binh_luan.loai = 'seeding' OR binh_luan.ly_do_loc = 'affiliate_hang_loat')"
_GIU_NHAN_KHO = f"(EXCLUDED.loai = 'hop_le' AND {_NHAN_KHO})"


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
                # Nhãn xét trên KHO (seeding, spam affiliate hàng loạt — `_NHAN_KHO`) thì lượt sau
                # không đưa về hop_le, và không mang lại sắc thái/chủ đề.
                f"sac_thai = CASE WHEN {_GIU_NHAN_KHO} THEN NULL "
                "ELSE COALESCE(EXCLUDED.sac_thai, binh_luan.sac_thai) END, "
                f"chu_de = CASE WHEN {_GIU_NHAN_KHO} THEN NULL "
                "ELSE COALESCE(EXCLUDED.chu_de, binh_luan.chu_de) END, "
                f"loai = CASE WHEN {_GIU_NHAN_KHO} THEN binh_luan.loai ELSE EXCLUDED.loai END, "
                f"ly_do_loc = CASE WHEN {_GIU_NHAN_KHO} THEN binh_luan.ly_do_loc "
                "ELSE EXCLUDED.ly_do_loc END, "
                "ma_noi_dung = EXCLUDED.ma_noi_dung, "
                # 16/10: nhận ra trả lời của fanpage muộn hơn (so tên gọn với chủ bài) thì bật cờ
                # cho dòng cũ — chỉ bật, không tắt (cờ đặt tay / script gán lại vẫn giữ).
                "cua_thuong_hieu = binh_luan.cua_thuong_hieu "
                "OR COALESCE(EXCLUDED.cua_thuong_hieu, false), "
                "link = COALESCE(EXCLUDED.link, binh_luan.link), "
                "ma_cha = COALESCE(EXCLUDED.ma_cha, binh_luan.ma_cha), "
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
            # bl_da_lay = TỔNG bình luận đã có của bài trong kho (lượt sau có thể chỉ lấy phần
            # mới — Facebook theo ngày), không phải số của riêng lượt này. bl_lan_thieu đếm số
            # lần LIÊN TIẾP chưa đủ mà KHÔNG thêm được bình luận nào (vế phải của SET đọc giá
            # trị CŨ của dòng): còn thêm được thì về 0 để lượt sau cào tiếp — "cào hết".
            c.execute(
                "UPDATE bai SET bl_lay_luc = now(), bl_lay_khi_co = COALESCE(%s, binh_luan), "
                "bl_da_lay = t.moi, bl_lan_thieu = CASE "
                "  WHEN t.moi >= COALESCE(%s, bai.binh_luan, 0) * %s THEN 0 "
                "  WHEN t.moi > COALESCE(bai.bl_da_lay, 0) THEN 0 "
                "  ELSE bai.bl_lan_thieu + 1 END "
                "FROM (SELECT GREATEST(%s, (SELECT count(*) FROM binh_luan b WHERE "
                "      b.du_an = %s AND b.khoa_bai = %s)) AS moi) t "
                "WHERE bai.du_an = %s AND bai.khoa = %s",
                (co, co, BL_DU_TOI_THIEU, n, ma, khoa, ma, khoa))
        _danh_dau_seeding(c, ma, [r.get("ma_noi_dung") for r in rows])
        _danh_dau_affiliate(c, ma, [r.get("khoa_bai") for r in rows])
    return moi, cu


def _danh_dau_seeding(c, ma: str, cac_ma: list) -> int:
    """Cùng nội dung (≥ 15 ký tự) từ ≥ `SEEDING_TAC_GIA` tài khoản trong `SEEDING_NGAY` ngày →
    `seeding` (chỉ hạ bình luận đang hop_le; spam/thương hiệu giữ nhãn của nó)."""
    import loc_rac
    ds = sorted({x for x in cac_ma if x})
    if not ds:
        return 0
    return c.execute(
        "WITH nhom AS (SELECT ma_noi_dung FROM binh_luan WHERE du_an = %s AND ma_noi_dung = ANY(%s) "
        "AND COALESCE(dang_luc, thay_lan_dau) >= now() - make_interval(days => %s) "
        "AND loai IN ('hop_le', 'seeding') GROUP BY ma_noi_dung "
        "HAVING count(DISTINCT lower(tac_gia)) >= %s AND count(DISTINCT khoa_bai) >= 2) "
        # cap_nhat_cuoi: mốc đồng bộ BigQuery — dòng CŨ (bài khác) bị hạ nhãn cũng phải đẩy lại.
        "UPDATE binh_luan b SET loai = 'seeding', "
        "ly_do_loc = 'cung_noi_dung_nhieu_tai_khoan', sac_thai = NULL, chu_de = NULL, "
        "cap_nhat_cuoi = now() FROM nhom WHERE b.du_an = %s AND b.ma_noi_dung = nhom.ma_noi_dung AND b.loai = 'hop_le'",
        (ma, ds, loc_rac.SEEDING_NGAY, loc_rac.SEEDING_TAC_GIA, ma)).rowcount or 0


#: Bình luận đã là spam affiliate vẫn đếm vào "cùng một đợt" của luật cấp bài.
_LY_DO_AFF = ("affiliate_dan_ma", "affiliate_hang_loat")


def _danh_dau_affiliate(c, ma: str, khoa_bai: list) -> int:
    """Luật cấp BÀI của spam affiliate (`loc_rac.affiliate_hang_loat`, 16/10/2026): dưới cùng một
    bài, ≥ 5 tài khoản có mã giới thiệu (hoặc chữ kiểu cách + lời dặn/tên sàn) trong 48 giờ theo
    giờ ĐĂNG → `spam` (`affiliate_hang_loat`). Chỉ hạ bình luận đang hop_le, xoá sắc thái/chủ đề
    như seeding. Mỗi tài khoản một mã nên luật seeding (cùng nội dung) không bắt được. Mã có trong
    bài / bình luận của chính thương hiệu (minigame, voucher) không tính. -> số dòng đã hạ."""
    import loc_rac
    ds = sorted({k for k in khoa_bai if k})
    if not ds:
        return 0
    da = c.execute("SELECT ten, tu_khoa FROM du_an WHERE ma = %s", (ma,)).fetchone() or {}
    thuong_hieu = [da.get("ten") or "", *(da.get("tu_khoa") or [])]
    bai = {r["khoa"]: r["noi_dung"] for r in c.execute(
        "SELECT khoa, noi_dung FROM bai WHERE du_an = %s AND khoa = ANY(%s)", (ma, ds)).fetchall()}
    # Bình luận không có giờ đăng (luc NULL) bị bỏ qua: giờ cào không nói chúng cách nhau bao lâu.
    rows = c.execute(
        "SELECT khoa_bai, ma, tac_gia, noi_dung, dang_luc AS luc, loai, cua_thuong_hieu "
        "FROM binh_luan WHERE du_an = %s AND khoa_bai = ANY(%s) AND (loai = 'hop_le' OR "
        "ly_do_loc = ANY(%s) OR loai = 'thuong_hieu' OR cua_thuong_hieu)",
        (ma, ds, list(_LY_DO_AFF))).fetchall()
    ha: dict[str, list[str]] = {}
    for kb, m in loc_rac.affiliate_hang_loat(rows, thuong_hieu=thuong_hieu, noi_dung_bai=bai):
        ha.setdefault(kb, []).append(m)
    n = 0
    for kb, cac in ha.items():
        n += c.execute(
            "UPDATE binh_luan SET loai = 'spam', ly_do_loc = 'affiliate_hang_loat', "
            "sac_thai = NULL, chu_de = NULL, cap_nhat_cuoi = now() WHERE du_an = %s AND "
            "khoa_bai = %s AND ma = ANY(%s) AND loai = 'hop_le'", (ma, kb, cac)).rowcount or 0
    return n


def da_gan_nhan(ma: str, khoa_bai: list[str]) -> set[tuple[str, str]]:
    """(khoá bài, mã bình luận) đã có sắc thái — cào lại không gửi lại AI (review 15/10). Kể cả
    bình luận mang nhãn KHO (seeding, spam affiliate hàng loạt): `ghi_binh_luan` giữ nhãn đó, gán
    sắc thái cho nó chỉ tốn tiền AI."""
    if not khoa_bai:
        return set()
    with ket_noi() as c:
        rows = c.execute("SELECT khoa_bai, ma FROM binh_luan WHERE du_an = %s AND "
                         "khoa_bai = ANY(%s) AND (sac_thai IS NOT NULL OR loai = 'seeding' OR "
                         "ly_do_loc = 'affiliate_hang_loat')", (ma, list(khoa_bai)))
        return {(r["khoa_bai"], r["ma"]) for r in rows.fetchall()}


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


# ───────────────────────────── lịch quét tự động (15/10/2026) ─────────────────────────────
# Dashboard đặt lịch (bảng `lich_quet`); Mark chỉ ĐỌC lịch và GHI các cột trạng thái chạy
# (lan_chay_ke, lan_chay_cuoi, ket_qua_cuoi, so_lan_chay) — GRANT trong schema.sql.
_COT_LICH = ("id, du_an, ten, kieu, cau_hinh, bat, quet_moi_nguon, lan_chay_ke, lan_chay_cuoi, "
             "ket_qua_cuoi, so_lan_chay")


def lich_dang_bat() -> list[dict]:
    """Mọi lịch đang bật (kể cả chưa tới hạn) — để biết dự án nào đang có chiến dịch."""
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_LICH} FROM lich_quet WHERE bat ORDER BY id").fetchall()


def doc_lich(lid: int) -> dict | None:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_LICH} FROM lich_quet WHERE id = %s", (lid,)).fetchone()


def nhan_lich_den_han(bay_gio, quyet, toi_da: int = 20) -> list[tuple[dict, dict]]:
    """NHẬN các lịch tới hạn (`lan_chay_ke` ≤ `bay_gio`) trong MỘT giao dịch:

    • `SELECT … FOR UPDATE SKIP LOCKED`: hai tiến trình Mark (lỡ chạy hai bản) không nhận cùng
      một dòng — bản thứ hai bỏ qua dòng đang bị khoá, sau commit thì dòng đã có mốc kế mới.
    • `quyet(dòng)` (thuần, không gọi mạng) -> {"lan_chay_ke", tuỳ chọn "lan_chay_cuoi",
      "ket_qua_cuoi"}; mốc kế GHI và COMMIT trước khi bên gọi bắt đầu lượt quét — chết giữa
      chừng thì lỡ một lượt, không bao giờ chạy một mốc hai lần.
    -> [(dòng cũ, quyết định)]."""
    import json
    with ket_noi() as c:
        rows = c.execute(
            f"SELECT {_COT_LICH} FROM lich_quet WHERE bat AND lan_chay_ke IS NOT NULL AND "
            "lan_chay_ke <= %s ORDER BY lan_chay_ke, id LIMIT %s FOR UPDATE SKIP LOCKED",
            (bay_gio, int(toi_da))).fetchall()
        ra = []
        for r in rows:
            q = quyet(dict(r))
            kq = q.get("ket_qua_cuoi")
            c.execute(
                "UPDATE lich_quet SET lan_chay_ke = %s, lan_chay_cuoi = COALESCE(%s, "
                "lan_chay_cuoi), ket_qua_cuoi = COALESCE(%s::jsonb, ket_qua_cuoi) WHERE id = %s",
                (q.get("lan_chay_ke"), q.get("lan_chay_cuoi"),
                 json.dumps(kq, ensure_ascii=False, default=str) if kq is not None else None,
                 r["id"]))
            ra.append((dict(r), q))
    return ra


def ghi_ket_qua_lich(lid: int, ket_qua: dict, *, lan_chay_cuoi=None, tang_so_lan: bool = False,
                     chi_khi_ma_viec: str | None = None) -> bool:
    """Ghi kết quả gần nhất của một lịch. `chi_khi_ma_viec`: chỉ ghi khi kết quả đang lưu là của
    đúng việc đó, hoặc việc đó còn chờ báo xong (`viec_cho` — lượt sau bị bỏ vì nó còn chạy).
    Việc nền xong muộn không đè kết quả của việc khác. -> có ghi không."""
    import json
    sql = ("UPDATE lich_quet SET ket_qua_cuoi = %s::jsonb, lan_chay_cuoi = COALESCE(%s, "
           "lan_chay_cuoi), so_lan_chay = so_lan_chay + %s WHERE id = %s")
    ts = [json.dumps(ket_qua, ensure_ascii=False, default=str), lan_chay_cuoi,
          1 if tang_so_lan else 0, int(lid)]
    if chi_khi_ma_viec:
        sql += (" AND (ket_qua_cuoi->>'ma_viec' = %s OR ket_qua_cuoi->>'viec_cho' = %s)")
        ts += [chi_khi_ma_viec, chi_khi_ma_viec]
    with ket_noi() as c:
        return bool(c.execute(sql + " RETURNING id", ts).fetchone())
