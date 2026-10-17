"""Kho `lang_nghe` (Postgres trên VPS) — phía dashboard. Module DUY NHẤT của dashboard có SQL.

Kết nối bằng role `lang_nghe_web` qua Unix socket + peer (user hệ điều hành của dịch vụ), không
mật khẩu; đổi bằng `LANG_NGHE_WEB_DSN` khi thử ở máy khác. Quyền của role (xem
`deploy/lang-nghe/schema.sql`): đọc mọi bảng; ghi `du_an`, `nguon`, `nguoi_xem`, `lich_quet`; chỉ đổi trạng
thái `de_xuat`; chỉ THÊM `nhat_ky`. Dashboard KHÔNG ghi `bai`, `luot_quet`, `chi_so_ngay` — đó là
phần của Mark.

Mỗi hàm sửa dữ liệu ghi thêm MỘT dòng `nhat_ky` (ai, hành động, đối tượng, chi tiết JSON) TRONG
CÙNG giao dịch: sửa thành công thì chắc chắn có nhật ký, nhật ký lỗi thì không sửa gì. Ngoại lệ
duy nhất: cột bản đệm của `nguoi_xem` (danh bạ Lark, lần đăng nhập cuối) — không phải thao tác
của người quản lý.

Lỗi: `LoiKho` (không dùng được kho — câu chỉ có tên loại lỗi, KHÔNG BAO GIỜ có DSN),
`LoiDuLieu` (vi phạm luật dữ liệu: trùng, sai ràng buộc, xoá quản lý cuối — câu hiển thị được).
Import psycopg MUỘN để bộ thử và máy không cài psycopg vẫn import được module này.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os

_TZ = "Asia/Ho_Chi_Minh"
#: Chặn số bài đọc một lần cho trang Chỉ số (2 kỳ). Vượt thì trả cờ `bi_cat` để trang báo.
#: ~20k dòng đã cắt chữ ≈ vài chục MB Python; app chỉ cho 2 lượt tính cùng lúc (MemoryMax 512M).
BAI_TOI_DA = 20_000


class LoiKho(RuntimeError):
    """Không dùng được kho (thiếu thư viện, chưa cài DB, mất kết nối, thiếu quyền)."""


class LoiDuLieu(ValueError):
    """Thao tác vi phạm luật dữ liệu; câu thông báo hiển thị được cho người dùng."""


def _dsn() -> str:
    return (os.environ.get("LANG_NGHE_WEB_DSN") or "").strip() or "dbname=lang_nghe"


@contextlib.contextmanager
def ket_noi(trung: str = "Dữ liệu này đã có."):
    """Một kết nối + một giao dịch: xong thì commit, lỗi thì rollback, luôn đóng. `trung` là
    câu báo khi vi phạm khoá duy nhất (mỗi chỗ gọi nói rõ trùng cái gì)."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise LoiKho("máy chủ dashboard chưa cài thư viện psycopg") from None
    try:
        conn = psycopg.connect(_dsn(), connect_timeout=5, row_factory=dict_row,
                               options="-c statement_timeout=20000")
    except psycopg.Error as e:
        raise LoiKho(f"không nối được kho lắng nghe ({type(e).__name__})") from None
    try:
        with conn:
            yield conn
    except psycopg.errors.UniqueViolation:
        raise LoiDuLieu(trung) from None
    except (psycopg.errors.CheckViolation, psycopg.errors.ForeignKeyViolation,
            psycopg.errors.NotNullViolation):
        raise LoiDuLieu("Giá trị không hợp lệ theo luật của kho dữ liệu.") from None
    except psycopg.Error as e:
        raise LoiKho(f"kho lắng nghe báo lỗi ({type(e).__name__}: "
                     f"{getattr(e, 'sqlstate', '') or ''})") from None
    finally:
        conn.close()


def _nhat_ky(c, ai: str, hanh_dong: str, doi_tuong: str, chi_tiet: dict | None = None) -> None:
    c.execute("INSERT INTO nhat_ky (ai, hanh_dong, doi_tuong, chi_tiet) "
              "VALUES (%s, %s, %s, %s::jsonb)",
              (ai, hanh_dong, doi_tuong,
               json.dumps(chi_tiet or {}, ensure_ascii=False, default=str)))


# ───────────────────────────── sức khoẻ + quyền ─────────────────────────────
def kiem_tra() -> bool:
    with ket_noi() as c:
        return bool(c.execute("SELECT 1 AS ok").fetchone())


def vai_tro(email: str) -> str | None:
    with ket_noi() as c:
        r = c.execute("SELECT vai_tro FROM nguoi_xem WHERE email = %s",
                      (str(email or "").lower(),)).fetchone()
    return r["vai_tro"] if r else None


# ───────────────────────────── dự án ─────────────────────────────
_COT_DU_AN = ("ma, ten, tu_khoa, tu_loai_tru, boi_canh, thi_truong, "
              "tran_usd_thang::float AS tran_usd_thang, dang_bat, tao_luc, sua_luc, sua_boi, "
              "bl_bat, bl_so_bai, bl_moi_bai, tk_bat, tk_so_bai, cau_hinh")


def cac_du_an() -> list[dict]:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_DU_AN} FROM du_an ORDER BY ma").fetchall()


def doc_du_an(ma: str) -> dict | None:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_DU_AN} FROM du_an WHERE ma = %s", (ma,)).fetchone()


def them_du_an(ai: str, d: dict) -> None:
    with ket_noi(trung=f"Mã dự án '{d['ma']}' đã có.") as c:
        c.execute("INSERT INTO du_an (ma, ten, tu_khoa, tu_loai_tru, boi_canh, thi_truong, "
                  "dang_bat, sua_boi) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                  (d["ma"], d["ten"], d["tu_khoa"], d["tu_loai_tru"], d["boi_canh"],
                   d["thi_truong"], d["dang_bat"], ai))
        _nhat_ky(c, ai, "them_du_an", f"du_an:{d['ma']}", d)


def sua_du_an(ai: str, ma: str, d: dict) -> None:
    with ket_noi() as c:
        r = c.execute("UPDATE du_an SET ten = %s, tu_khoa = %s, tu_loai_tru = %s, boi_canh = %s, "
                      "thi_truong = %s, dang_bat = %s, sua_luc = now(), sua_boi = %s "
                      "WHERE ma = %s RETURNING ma",
                      (d["ten"], d["tu_khoa"], d["tu_loai_tru"], d["boi_canh"], d["thi_truong"],
                       d["dang_bat"], ai, ma)).fetchone()
        if not r:
            raise LoiDuLieu("Không còn dự án này.")
        _nhat_ky(c, ai, "sua_du_an", f"du_an:{ma}", d)


def dat_tran_thang(ai: str, ma: str, usd) -> None:
    """Trần USD tháng của dự án (0–100; CHECK của bảng chặn thêm một lớp)."""
    with ket_noi() as c:
        cu = c.execute("SELECT tran_usd_thang::float AS v FROM du_an WHERE ma = %s FOR UPDATE",
                       (ma,)).fetchone()
        if not cu:
            raise LoiDuLieu("Không còn dự án này.")
        c.execute("UPDATE du_an SET tran_usd_thang = %s, sua_luc = now(), sua_boi = %s "
                  "WHERE ma = %s", (usd, ai, ma))
        _nhat_ky(c, ai, "dat_tran_thang", f"du_an:{ma}", {"cu": cu["v"], "moi": str(usd)})


# ───────────────────────────── nguồn ─────────────────────────────
_COT_NGUON = ("id, du_an, nen_tang, dinh_danh, ten, link, loai, nhan, trang_thai, chu_ky_ngay, "
              "so_bai_moi_lan, them_qua, them_boi, them_luc, quet_cuoi, loi_cuoi, loi_luc")


def cac_nguon(du_an: str) -> list[dict]:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_NGUON} FROM nguon WHERE du_an = %s "
                         "ORDER BY nen_tang, dinh_danh", (du_an,)).fetchall()


def doc_nguon(nid: int) -> dict | None:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_NGUON} FROM nguon WHERE id = %s", (nid,)).fetchone()


def them_nguon(ai: str, du_an: str, d: dict) -> int:
    with ket_noi(trung="Nguồn này đã có trong dự án.") as c:
        r = c.execute("INSERT INTO nguon (du_an, nen_tang, dinh_danh, ten, link, loai, nhan, "
                      "chu_ky_ngay, so_bai_moi_lan, them_qua, them_boi) VALUES "
                      "(%s, %s, %s, %s, %s, %s, %s, %s, %s, 'dashboard', %s) RETURNING id",
                      (du_an, d["nen_tang"], d["dinh_danh"], d["ten"], d["link"], d["loai"],
                       d["nhan"], d["chu_ky_ngay"], d["so_bai_moi_lan"], ai)).fetchone()
        _nhat_ky(c, ai, "them_nguon", f"nguon:{r['id']}", {"du_an": du_an, **d})
    return int(r["id"])


def sua_nguon(ai: str, nid: int, d: dict) -> None:
    with ket_noi(trung="Dự án đã có nguồn khác trùng định danh này.") as c:
        r = c.execute("UPDATE nguon SET nen_tang = %s, dinh_danh = %s, ten = %s, link = %s, "
                      "loai = %s, nhan = %s, chu_ky_ngay = %s, so_bai_moi_lan = %s "
                      "WHERE id = %s RETURNING du_an",
                      (d["nen_tang"], d["dinh_danh"], d["ten"], d["link"], d["loai"], d["nhan"],
                       d["chu_ky_ngay"], d["so_bai_moi_lan"], nid)).fetchone()
        if not r:
            raise LoiDuLieu("Không còn nguồn này.")
        _nhat_ky(c, ai, "sua_nguon", f"nguon:{nid}", {"du_an": r["du_an"], **d})


def doi_trang_thai_nguon(ai: str, nid: int, trang_thai: str) -> None:
    if trang_thai not in ("dang_theo_doi", "tam_dung"):
        raise LoiDuLieu("Trạng thái nguồn không hợp lệ.")
    with ket_noi() as c:
        r = c.execute("UPDATE nguon SET trang_thai = %s WHERE id = %s RETURNING du_an",
                      (trang_thai, nid)).fetchone()
        if not r:
            raise LoiDuLieu("Không còn nguồn này.")
        _nhat_ky(c, ai, "doi_trang_thai_nguon", f"nguon:{nid}",
                 {"du_an": r["du_an"], "trang_thai": trang_thai})


def xoa_nguon(ai: str, nid: int) -> None:
    """Xoá nguồn. Bài đã quét VẪN giữ (khoá ngoại `bai.nguon_id` ON DELETE SET NULL)."""
    with ket_noi() as c:
        r = c.execute("DELETE FROM nguon WHERE id = %s RETURNING du_an, nen_tang, dinh_danh",
                      (nid,)).fetchone()
        if not r:
            raise LoiDuLieu("Không còn nguồn này.")
        _nhat_ky(c, ai, "xoa_nguon", f"nguon:{nid}", dict(r))


# ───────────────────────────── đề xuất nguồn ─────────────────────────────
_COT_DE_XUAT = ("id, du_an, nen_tang, dinh_danh, ten, link, ly_do, so_bai, thao_luan, trang_thai, "
                "de_xuat_luc, xu_ly_boi, xu_ly_luc")


def cac_de_xuat(du_an: str, trang_thai: str = "cho") -> list[dict]:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_DE_XUAT} FROM de_xuat WHERE du_an = %s AND "
                         "trang_thai = %s ORDER BY thao_luan DESC, de_xuat_luc DESC LIMIT 200",
                         (du_an, trang_thai)).fetchall()


def doc_de_xuat(did: int) -> dict | None:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_DE_XUAT} FROM de_xuat WHERE id = %s", (did,)).fetchone()


def duyet_de_xuat(ai: str, did: int, d: dict) -> int | None:
    """Duyệt: đánh dấu đề xuất `da_duyet` và thêm nguồn (`them_qua='de_xuat'`) trong MỘT giao
    dịch. `d` = nguồn đã chuẩn hoá ở tầng app. Chỉ đề xuất còn 'cho' mới duyệt được (hai người
    bấm cùng lúc thì người sau nhận lỗi, không thêm nguồn hai lần). -> id nguồn mới, hoặc None
    khi nguồn đó đã có sẵn trong dự án (vẫn đánh dấu đã duyệt)."""
    with ket_noi() as c:
        x = c.execute("UPDATE de_xuat SET trang_thai = 'da_duyet', xu_ly_boi = %s, "
                      "xu_ly_luc = now() WHERE id = %s AND trang_thai = 'cho' RETURNING du_an",
                      (ai, did)).fetchone()
        if not x:
            raise LoiDuLieu("Đề xuất này không còn chờ duyệt.")
        r = c.execute("INSERT INTO nguon (du_an, nen_tang, dinh_danh, ten, link, loai, nhan, "
                      "chu_ky_ngay, so_bai_moi_lan, them_qua, them_boi) VALUES "
                      "(%s, %s, %s, %s, %s, %s, %s, %s, %s, 'de_xuat', %s) "
                      "ON CONFLICT (du_an, nen_tang, dinh_danh) DO NOTHING RETURNING id",
                      (x["du_an"], d["nen_tang"], d["dinh_danh"], d["ten"], d["link"], d["loai"],
                       d.get("nhan") or [], d.get("chu_ky_ngay") or 1,
                       d.get("so_bai_moi_lan") or 5, ai)).fetchone()
        nid = int(r["id"]) if r else None
        _nhat_ky(c, ai, "duyet_de_xuat", f"de_xuat:{did}",
                 {"du_an": x["du_an"], "nguon_id": nid, **d})
    return nid


def tu_choi_de_xuat(ai: str, did: int) -> None:
    with ket_noi() as c:
        x = c.execute("UPDATE de_xuat SET trang_thai = 'tu_choi', xu_ly_boi = %s, "
                      "xu_ly_luc = now() WHERE id = %s AND trang_thai = 'cho' "
                      "RETURNING du_an, nen_tang, dinh_danh", (ai, did)).fetchone()
        if not x:
            raise LoiDuLieu("Đề xuất này không còn chờ duyệt.")
        _nhat_ky(c, ai, "tu_choi_de_xuat", f"de_xuat:{did}", dict(x))


# ───────────────────────────── bài + lượt quét (chỉ đọc) ─────────────────────────────
def bai_trong_khoang(du_an: str, tu: datetime.datetime, den: datetime.datetime) -> dict:
    """Bài đăng trong [tu, den) kèm loại/tên nguồn. -> {"rows": [...], "bi_cat": bool}.

    Chỉ các cột `chi_so` dùng, chữ dài cắt ngắn ngay trong SQL (khoảng 400 ngày không làm phình
    bộ nhớ dịch vụ). Vượt `BAI_TOI_DA` thì giữ bài MỚI NHẤT (DESC): phần bị bỏ là đầu khoảng /
    kỳ trước, và trang báo rõ bằng cờ `bi_cat` — không lặng lẽ mất bài mới nhất."""
    with ket_noi() as c:
        rows = c.execute(
            f"SELECT {_COT_BAI_CS} FROM bai b LEFT JOIN nguon n ON n.id = b.nguon_id "
            "WHERE b.du_an = %s AND b.dang_luc >= %s AND b.dang_luc < %s "
            "ORDER BY b.dang_luc DESC LIMIT %s", (du_an, tu, den, BAI_TOI_DA + 1)).fetchall()
    return {"rows": rows[:BAI_TOI_DA], "bi_cat": len(rows) > BAI_TOI_DA}


# Cột bài trang Chỉ số dùng (chữ dài cắt ngay trong SQL). `kieu_quet` (đợt 2f): bộ lọc "kiểu quét".
# `kieu_trang`, `muc_nhac`, `la_pr` (lắng nghe web, 16/10/2026): chỉ bài web có, bài MXH NULL.
_COT_BAI_CS = (
    "b.khoa, b.nen_tang, b.nguon_id, b.kieu_quet, left(b.link, 500) AS link, b.bl_da_lay, "
    "b.ma_noi_dung, "
    "left(b.tac_gia, 200) AS tac_gia, left(b.tai_khoan, 200) AS tai_khoan, b.followers, "
    "b.dang_luc, left(b.noi_dung, 1000) AS noi_dung, left(b.hashtag, 500) AS hashtag, "
    "b.sac_thai, left(b.chu_de, 100) AS chu_de, b.xem, b.thich, b.binh_luan, b.chia_se, "
    "b.kieu_trang, b.muc_nhac, b.la_pr, "
    "n.loai AS nguon_loai, n.ten AS nguon_ten, n.dinh_danh AS nguon_dinh_danh, "
    "n.link AS nguon_link")


# Bài gốc của bình luận chỉ cần đủ cột cho các chiều lọc CẤP BÀI (nguồn, ảnh hưởng, tương tác,
# kiểu quét); nội dung + hashtag chỉ khi đang lọc chữ — mỗi bài thiếu không mang chữ dài vô ích.
_COT_BAI_GOC = (
    "b.khoa, b.nen_tang, b.nguon_id, n.loai AS nguon_loai, left(b.tai_khoan, 200) AS tai_khoan, "
    "left(b.tac_gia, 200) AS tac_gia, b.followers, b.thich, b.binh_luan, b.chia_se, "
    "b.kieu_quet, b.kieu_trang, left(b.link, 500) AS link")
_COT_BAI_GOC_CHU = ", left(b.noi_dung, 1000) AS noi_dung, left(b.hashtag, 500) AS hashtag"


def bai_theo_khoa(du_an: str, khoa: list[str], co_chu: bool = False) -> list[dict]:
    """Bài gốc theo khoá (cột hẹp `_COT_BAI_GOC`; `co_chu` thêm nội dung + hashtag) — cho bình
    luận trong khoảng mà bài đăng TRƯỚC khoảng đã đọc, chỉ khi bộ lọc chung có điều kiện cấp bài
    (đợt 2f). Tối đa `BL_TOI_DA` khoá (= số bình luận tối đa của một khoảng), từng lô 5.000."""
    khoa = list(dict.fromkeys(k for k in khoa if k))[:BL_TOI_DA]
    rows: list[dict] = []
    if not khoa:
        return rows
    cot = _COT_BAI_GOC + (_COT_BAI_GOC_CHU if co_chu else "")
    with ket_noi() as c:
        for i in range(0, len(khoa), 5000):
            rows += c.execute(
                f"SELECT {cot} FROM bai b LEFT JOIN nguon n ON n.id = b.nguon_id "
                "WHERE b.du_an = %s AND b.khoa = ANY(%s)", (du_an, khoa[i:i + 5000])).fetchall()
    return rows


# ───────────────────────────── bình luận (đợt 2b, chỉ đọc + cấu hình) ─────────────────────────────
BL_TOI_DA = 50_000
_COT_BL = ("b.khoa_bai, b.ma, b.nen_tang, left(b.tac_gia, 200) AS tac_gia, "
           "left(b.noi_dung, 1000) AS noi_dung, b.thich, b.tra_loi, b.la_tra_loi, "
           "b.cua_thuong_hieu, b.dang_luc, b.sac_thai, b.chu_de, b.loai, b.ly_do_loc, "
           "left(b.link, 500) AS link, b.ma_cha")
# Nguồn của bình luận (đợt 2e: lọc/đếm theo nguồn) — cột HẸP, đi cùng mọi dòng của khoảng.
_COT_BL_NGUON = ("COALESCE(b.dang_luc, b.thay_lan_dau) AS luc, n.loai AS nguon_loai, "
                 "bai.nguon_id, left(n.ten, 120) AS nguon_ten, "
                 "left(bai.tac_gia, 120) AS bai_tac_gia")
# Ngữ cảnh bài (link, đoạn nội dung): chỉ đọc cho bình luận của trang đang xem (`ngu_canh_bai`)
# hoặc của MỘT bài — đọc cho cả 50.000 dòng của khoảng thì gấp đôi bộ nhớ dịch vụ (MemoryMax).
_COT_BAI_RONG = ("left(bai.link, 500) AS bai_link, left(bai.noi_dung, 240) AS bai_noi_dung, "
                 "bai.dang_luc AS bai_dang_luc")
_TU_BL = ("FROM binh_luan b JOIN bai ON bai.du_an = b.du_an AND bai.khoa = b.khoa_bai "
          "LEFT JOIN nguon n ON n.id = bai.nguon_id ")


def binh_luan_trong_khoang(du_an: str, tu: datetime.datetime, den: datetime.datetime) -> dict:
    """Bình luận đã cào, đăng trong [tu, den) (bình luận không có giờ đăng: theo giờ cào), kèm
    nguồn của bài để lọc giống trang Chỉ số. -> {"rows", "bi_cat"}."""
    with ket_noi() as c:
        rows = c.execute(
            f"SELECT {_COT_BL}, {_COT_BL_NGUON} {_TU_BL}"
            "WHERE b.du_an = %s AND COALESCE(b.dang_luc, b.thay_lan_dau) >= %s "
            "AND COALESCE(b.dang_luc, b.thay_lan_dau) < %s "
            "ORDER BY COALESCE(b.dang_luc, b.thay_lan_dau) DESC LIMIT %s",
            (du_an, tu, den, BL_TOI_DA + 1)).fetchall()
    return {"rows": rows[:BL_TOI_DA], "bi_cat": len(rows) > BL_TOI_DA}


def binh_luan_hop_le_gon(du_an: str, tu: datetime.datetime, den: datetime.datetime) -> dict:
    """Bình luận HỢP LỆ của [tu, den), cột HẸP (đủ cho bộ lọc chung + ý định mua; nội dung cắt như
    `binh_luan_trong_khoang` để định nghĩa hai kỳ giống nhau) — chỉ để so "Ý định mua" với kỳ trước
    (16/10/2026). App không nhớ đệm bộ này; kết quả /api/chi-so đã nhớ. -> {"rows", "bi_cat"}."""
    with ket_noi() as c:
        rows = c.execute(
            "SELECT b.khoa_bai, b.nen_tang, left(b.noi_dung, 1000) AS noi_dung, b.loai, "
            "b.cua_thuong_hieu, b.sac_thai, b.chu_de, COALESCE(b.dang_luc, b.thay_lan_dau) AS luc, "
            f"n.loai AS nguon_loai, bai.nguon_id {_TU_BL}"
            "WHERE b.du_an = %s AND b.loai = 'hop_le' AND COALESCE(b.dang_luc, b.thay_lan_dau) >= %s "
            "AND COALESCE(b.dang_luc, b.thay_lan_dau) < %s "
            "ORDER BY COALESCE(b.dang_luc, b.thay_lan_dau) DESC LIMIT %s",
            (du_an, tu, den, BL_TOI_DA + 1)).fetchall()
    return {"rows": rows[:BL_TOI_DA], "bi_cat": len(rows) > BL_TOI_DA}


def binh_luan_cua_bai(du_an: str, khoa: str, toi_da: int = 3000) -> list[dict]:
    """Bình luận đã cào của MỘT bài, nhiều thích trước (app xếp lại theo luồng trả lời)."""
    with ket_noi() as c:
        return c.execute(
            f"SELECT {_COT_BL}, {_COT_BL_NGUON}, {_COT_BAI_RONG} {_TU_BL}"
            "WHERE b.du_an = %s AND b.khoa_bai = %s "
            "ORDER BY b.la_tra_loi, COALESCE(b.thich, 0) DESC, b.dang_luc LIMIT %s",
            (du_an, khoa, toi_da)).fetchall()


def ngu_canh_bai(du_an: str, khoa: list[str]) -> dict[str, dict]:
    """Link + đoạn nội dung + giờ đăng của các bài (≤ 100 khoá — bình luận một trang)."""
    khoa = list(dict.fromkeys(k for k in khoa if k))[:100]
    if not khoa:
        return {}
    with ket_noi() as c:
        rows = c.execute(
            f"SELECT bai.khoa, {_COT_BAI_RONG} FROM bai WHERE bai.du_an = %s "
            "AND bai.khoa = ANY(%s)", (du_an, khoa)).fetchall()
    return {r["khoa"]: r for r in rows}


def dat_cau_hinh(ai: str, ma: str, cau_hinh: dict) -> None:
    """Cấu hình thu thập theo từng nền tảng (đợt 2e) — JSON đã kiểm ở app. Cột tk_bat / bl_bat
    (công tắc tổng của Mark) = có ít nhất một nền tảng bật, để công tắc cũ và mới không lệch."""
    tk_bat = any(v.get("bat") is True for v in cau_hinh.get("tu_khoa", {}).values())
    bl_bat = any(v.get("bat") is True for v in cau_hinh.get("binh_luan", {}).values())
    with ket_noi() as c:
        cu = c.execute("SELECT cau_hinh FROM du_an WHERE ma = %s FOR UPDATE", (ma,)).fetchone()
        if not cu:
            raise LoiDuLieu("Không còn dự án này.")
        # Chỉ thay các nhóm biểu mẫu gửi (tu_khoa, binh_luan); nhóm khác trong JSONB (vd `web`:
        # miền nhà của lắng nghe web, 16/10/2026) giữ nguyên — lưu Ngân sách không xoá mất.
        goc = cu["cau_hinh"] if isinstance(cu["cau_hinh"], dict) else {}
        cau_hinh = {**goc, **cau_hinh}
        c.execute("UPDATE du_an SET cau_hinh = %s::jsonb, tk_bat = %s, bl_bat = %s, "
                  "sua_luc = now(), sua_boi = %s WHERE ma = %s",
                  (json.dumps(cau_hinh, ensure_ascii=False), tk_bat, bl_bat, ai, ma))
        _nhat_ky(c, ai, "sua_cau_hinh", f"du_an:{ma}", {"truoc": cu["cau_hinh"], "sau": cau_hinh})


def dat_binh_luan(ai: str, ma: str, bat: bool, so_bai: int, moi_bai: int) -> None:
    """Cấu hình cào bình luận của dự án (CHECK của bảng chặn thêm một lớp)."""
    with ket_noi() as c:
        cu = c.execute("SELECT bl_bat, bl_so_bai, bl_moi_bai FROM du_an WHERE ma = %s FOR UPDATE",
                       (ma,)).fetchone()
        if not cu:
            raise LoiDuLieu("Không còn dự án này.")
        c.execute("UPDATE du_an SET bl_bat = %s, bl_so_bai = %s, bl_moi_bai = %s, "
                  "sua_luc = now(), sua_boi = %s WHERE ma = %s",
                  (bat, so_bai, moi_bai, ai, ma))
        _nhat_ky(c, ai, "sua_binh_luan", f"du_an:{ma}",
                 {"truoc": dict(cu), "sau": {"bl_bat": bat, "bl_so_bai": so_bai,
                                              "bl_moi_bai": moi_bai}})


def dat_tim_tu_khoa(ai: str, ma: str, bat: bool, so_bai: int) -> None:
    """Cấu hình tìm theo từ khoá trong mỗi lượt /theodoi (từ khoá = từ khoá của dự án)."""
    with ket_noi() as c:
        cu = c.execute("SELECT tk_bat, tk_so_bai FROM du_an WHERE ma = %s FOR UPDATE",
                       (ma,)).fetchone()
        if not cu:
            raise LoiDuLieu("Không còn dự án này.")
        c.execute("UPDATE du_an SET tk_bat = %s, tk_so_bai = %s, sua_luc = now(), sua_boi = %s "
                  "WHERE ma = %s", (bat, so_bai, ai, ma))
        _nhat_ky(c, ai, "sua_tim_tu_khoa", f"du_an:{ma}",
                 {"truoc": dict(cu), "sau": {"tk_bat": bat, "tk_so_bai": so_bai}})


def da_tieu_thang() -> dict[str, float]:
    """USD thật các lượt `theo_doi` đã tiêu trong tháng hiện tại (giờ VN), theo dự án — cùng
    phép tính `lang_nghe_db.da_tieu_thang` của Mark (hai bên phải ra cùng một số)."""
    with ket_noi() as c:
        rows = c.execute(
            "SELECT du_an, COALESCE(sum(chi_phi_usd), 0)::float AS usd FROM luot_quet "
            "WHERE kieu = 'theo_doi' AND bat_dau >= "
            "(date_trunc('month', now() AT TIME ZONE %s) AT TIME ZONE %s) GROUP BY du_an",
            (_TZ, _TZ)).fetchall()
    return {r["du_an"]: float(r["usd"] or 0) for r in rows}


def tran_platform(du_an: str | None = None) -> float | None:
    """Trần USD tháng do PLATFORM đặt (cấp cửa hàng, KDLA — platform PR #101 chưa xong).
    Tạm thời luôn None ("chưa có"). Khi KDLA ra: Mark đọc trần từ platform rồi GHI vào kho này
    (bảng/cột mới do Mark và schema.sql thêm — dashboard không gọi platform, chủ dự án: "mark vẫn
    phải theo luật của platform"); hàm này đổi sang đọc dòng đó. Trần hiệu lực = min(platform,
    dự án) — `chi_phi.tran_hieu_luc`."""
    return None


def cac_luot(du_an: str, trang: int = 1, moi_trang: int = 20) -> tuple[list[dict], int]:
    trang = max(1, int(trang))
    with ket_noi() as c:
        tong = c.execute("SELECT count(*) AS n FROM luot_quet WHERE du_an = %s",
                         (du_an,)).fetchone()["n"]
        rows = c.execute(
            "SELECT id, kieu, ma_viec, bat_dau, ket_thuc, so_nguon, so_nguon_loi, bai_moi, "
            "bai_cap_nhat, chi_phi_usd::float AS chi_phi_usd, trang_thai, loi, ghi_chu "
            "FROM luot_quet WHERE du_an = %s ORDER BY id DESC LIMIT %s OFFSET %s",
            (du_an, moi_trang, (trang - 1) * moi_trang)).fetchall()
    return rows, int(tong)


def tien_do_gan_nhan(du_an: str) -> dict:
    """Gán nhãn AI chạy nền của Mark (17/10/2026, `gan_nhan_nen.py`): kho là hàng đợi nên đếm
    thẳng ở đây. -> {cho_bl, cho_bai (còn chờ AI, cả dự án), luot (lượt theo dõi gần nhất có
    bình luận), da, tong (bình luận hợp lệ có chữ của lượt đó: đã có nhãn / tất cả)}."""
    with ket_noi() as c:
        cho = c.execute(
            "SELECT (SELECT count(*) FROM binh_luan WHERE du_an = %s AND loai = 'hop_le' AND NOT "
            "cua_thuong_hieu AND sac_thai IS NULL AND btrim(noi_dung) <> '') AS cho_bl, "
            "(SELECT count(*) FROM bai b LEFT JOIN nguon n ON n.id = b.nguon_id WHERE b.du_an = %s "
            "AND (b.sac_thai IS NULL OR b.chu_de IS NULL) AND n.loai IS DISTINCT FROM 'kenh_nha' "
            "AND btrim(b.noi_dung || ' ' || COALESCE(b.hashtag, '')) <> '') AS cho_bai",
            (du_an, du_an)).fetchone()
        luot = c.execute(
            "SELECT b.luot_id AS luot, count(*) FILTER (WHERE b.sac_thai IS NOT NULL) AS da, "
            "count(*) AS tong FROM binh_luan b WHERE b.du_an = %s AND b.luot_id = (SELECT "
            "max(luot_id) FROM binh_luan WHERE du_an = %s) AND b.loai = 'hop_le' AND NOT "
            "b.cua_thuong_hieu AND btrim(b.noi_dung) <> '' GROUP BY b.luot_id",
            (du_an, du_an)).fetchone() or {}
    return {"cho_bl": int(cho["cho_bl"] or 0), "cho_bai": int(cho["cho_bai"] or 0),
            "luot": luot.get("luot"), "da": int(luot.get("da") or 0),
            "tong": int(luot.get("tong") or 0)}


def do_phu_gan_nhat(du_an: str, n: int = 2) -> list[dict]:
    """`n` lượt kiểm độ phủ gần nhất của dự án (17/10/2026, Mark `kiem_do_phu.py`), mới nhất
    trước — thẻ "Độ phủ" so lần mới với lần trước. Bảng chưa tạo thì `LoiKho` (bên gọi bỏ thẻ)."""
    with ket_noi() as c:
        return c.execute(
            "SELECT id, luot_id, luc, nen_tang, so_mau, so_nhac, so_da_co, so_da_loai, so_sot, "
            "thao_luan_nhac, thao_luan_da_co, do_phu::float AS do_phu, "
            "do_phu_tl::float AS do_phu_tl, bo_sung, so_yeu_cau, chi_phi_usd::float AS "
            "chi_phi_usd, mau, bai_sot FROM kiem_do_phu WHERE du_an = %s ORDER BY luc DESC, "
            "id DESC LIMIT %s", (du_an, max(1, int(n)))).fetchall()


def luot_xong_moi_nhat() -> dict | None:
    """Lượt vừa kết thúc gần nhất (mọi dự án) — vòng kiểm 30 giây so mốc này để biết có dữ liệu
    mới khi Mark không báo được (dashboard tắt lúc Mark báo, lỗi mạng nội bộ…)."""
    with ket_noi() as c:
        return c.execute("SELECT id, du_an, ket_thuc FROM luot_quet WHERE ket_thuc IS NOT NULL "
                         "ORDER BY ket_thuc DESC, id DESC LIMIT 1").fetchone()


# ───────────────────────────── lịch quét tự động (15/10/2026) ─────────────────────────────
# Chủ dự án chốt "Dashboard + Mark tự chạy": người quản lý đặt lịch ở đây, Mark (quet_tu_dong.py)
# tự chạy /theodoi đúng mốc và chỉ ghi các cột trạng thái chạy. Dashboard tính `lan_chay_ke`
# (dashboard/lich_quet.py) mỗi lần lưu/bật lại để Mark không chạy một mốc cũ.
LICH_TOI_DA = 20
_COT_LICH = ("l.id, l.du_an, l.ten, l.kieu, l.cau_hinh, l.bat, l.quet_moi_nguon, l.lan_chay_ke, "
             "l.lan_chay_cuoi, l.ket_qua_cuoi, l.so_lan_chay, l.tao_luc, l.tao_boi, l.sua_luc, "
             "l.sua_boi")


def cac_lich(du_an: str) -> list[dict]:
    """Lịch của dự án, kèm lượt GẦN NHẤT do lịch giao (kết quả thật: trạng thái, bài, chi phí)."""
    with ket_noi() as c:
        return c.execute(
            f"SELECT {_COT_LICH}, lq.id AS luot_id, lq.ma_viec AS luot_ma_viec, "
            "lq.trang_thai AS luot_trang_thai, "
            "lq.bat_dau AS luot_bat_dau, lq.ket_thuc AS luot_ket_thuc, lq.bai_moi AS luot_bai_moi, "
            "lq.bai_cap_nhat AS luot_bai_cap_nhat, lq.chi_phi_usd::float AS luot_chi_phi, "
            "lq.loi AS luot_loi FROM lich_quet l LEFT JOIN LATERAL (SELECT id, ma_viec, trang_thai, "
            "bat_dau, ket_thuc, bai_moi, bai_cap_nhat, chi_phi_usd, loi FROM luot_quet "
            "WHERE lich_id = l.id ORDER BY id DESC LIMIT 1) lq ON TRUE "
            "WHERE l.du_an = %s ORDER BY l.id", (du_an,)).fetchall()


def doc_lich(lid: int) -> dict | None:
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_LICH} FROM lich_quet l WHERE l.id = %s",
                         (lid,)).fetchone()


def _gia_tri_lich(d: dict) -> tuple:
    return (d["ten"], d["kieu"], json.dumps(d["cau_hinh"], ensure_ascii=False), bool(d["bat"]),
            bool(d["quet_moi_nguon"]), d.get("lan_chay_ke"))


def them_lich(ai: str, du_an: str, d: dict) -> int:
    """`d` = lịch đã kiểm ở app (`lich_quet.chuan_hoa`) + `lan_chay_ke`. Khoá dòng dự án để hai
    người cùng tạo không vượt `LICH_TOI_DA`."""
    with ket_noi() as c:
        if not c.execute("SELECT 1 AS co FROM du_an WHERE ma = %s FOR UPDATE", (du_an,)).fetchone():
            raise LoiDuLieu("Không còn dự án này.")
        n = c.execute("SELECT count(*) AS n FROM lich_quet WHERE du_an = %s",
                      (du_an,)).fetchone()["n"]
        if int(n) >= LICH_TOI_DA:
            raise LoiDuLieu(f"Mỗi dự án tối đa {LICH_TOI_DA} lịch — xoá bớt lịch cũ trước.")
        r = c.execute("INSERT INTO lich_quet (du_an, ten, kieu, cau_hinh, bat, quet_moi_nguon, "
                      "lan_chay_ke, tao_boi, sua_boi) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, "
                      "%s, %s) RETURNING id", (du_an, *_gia_tri_lich(d), ai, ai)).fetchone()
        _nhat_ky(c, ai, "them_lich", f"lich_quet:{r['id']}", {"du_an": du_an, **d})
    return int(r["id"])


def sua_lich(ai: str, lid: int, d: dict) -> None:
    with ket_noi() as c:
        cu = c.execute("SELECT du_an, ten, kieu, cau_hinh, bat, quet_moi_nguon FROM lich_quet "
                       "WHERE id = %s FOR UPDATE", (lid,)).fetchone()
        if not cu:
            raise LoiDuLieu("Không còn lịch này.")
        c.execute("UPDATE lich_quet SET ten = %s, kieu = %s, cau_hinh = %s::jsonb, bat = %s, "
                  "quet_moi_nguon = %s, lan_chay_ke = %s, sua_luc = now(), sua_boi = %s "
                  "WHERE id = %s", (*_gia_tri_lich(d), ai, lid))
        _nhat_ky(c, ai, "sua_lich", f"lich_quet:{lid}",
                 {"du_an": cu["du_an"], "truoc": dict(cu), "sau": d})


def bat_tat_lich(ai: str, lid: int, bat: bool, lan_chay_ke) -> None:
    """Bật (kèm mốc kế mới tính từ bây giờ — không chạy bù mốc cũ) hoặc tắt (mốc kế NULL)."""
    with ket_noi() as c:
        r = c.execute("UPDATE lich_quet SET bat = %s, lan_chay_ke = %s, sua_luc = now(), "
                      "sua_boi = %s WHERE id = %s RETURNING du_an",
                      (bool(bat), lan_chay_ke if bat else None, ai, lid)).fetchone()
        if not r:
            raise LoiDuLieu("Không còn lịch này.")
        _nhat_ky(c, ai, "bat_lich" if bat else "tat_lich", f"lich_quet:{lid}",
                 {"du_an": r["du_an"], "lan_chay_ke": lan_chay_ke if bat else None})


def xoa_lich(ai: str, lid: int) -> None:
    """Xoá lịch. Lượt đã chạy theo lịch VẪN giữ (`luot_quet.lich_id` ON DELETE SET NULL)."""
    with ket_noi() as c:
        r = c.execute("DELETE FROM lich_quet WHERE id = %s RETURNING du_an, ten, kieu, cau_hinh",
                      (lid,)).fetchone()
        if not r:
            raise LoiDuLieu("Không còn lịch này.")
        _nhat_ky(c, ai, "xoa_lich", f"lich_quet:{lid}", dict(r))


# ───────────────────────────── người xem + nhật ký ─────────────────────────────
def cac_nguoi_xem() -> list[dict]:
    """Người xem kèm bản đệm danh bạ Lark. `dang_nhap_cuoi`: cột mới (ghi mỗi lượt đăng nhập);
    người chưa đăng nhập lại kể từ khi có cột thì lấy lần đăng nhập đầu trong nhật ký."""
    with ket_noi() as c:
        return c.execute(
            "SELECT n.email, n.vai_tro, n.them_boi, n.them_luc, n.ten_lark, n.chuc_danh, "
            "n.phong_ban, n.trang_thai_lark, n.danh_ba_loi, n.danh_ba_luc, "
            "COALESCE(n.dang_nhap_cuoi, (SELECT max(k.luc) FROM nhat_ky k "
            "WHERE k.hanh_dong = 'dang_nhap_lan_dau' AND k.doi_tuong = 'nguoi_xem:' || n.email)"
            ") AS dang_nhap_cuoi FROM nguoi_xem n ORDER BY n.vai_tro DESC, n.email").fetchall()


def ghi_danh_ba(ket_qua: dict[str, dict]) -> None:
    """Ghi bản đệm danh bạ Lark (email -> trang_thai, ten, chuc_danh, phong_ban). KHÔNG ghi nhật
    ký: đây là bản sao danh bạ, không phải thao tác của người quản lý. Email đã bị xoá khỏi
    `nguoi_xem` trong lúc đọc thì câu cập nhật không khớp dòng nào — bỏ qua."""
    with ket_noi() as c:
        for email, d in ket_qua.items():
            c.execute("UPDATE nguoi_xem SET trang_thai_lark = %s, ten_lark = %s, chuc_danh = %s, "
                      "phong_ban = %s, danh_ba_loi = NULL, danh_ba_luc = now() WHERE email = %s",
                      (d.get("trang_thai"), d.get("ten"), d.get("chuc_danh"), d.get("phong_ban"),
                       email))


def ghi_loi_danh_ba(emails: list[str], loai: str) -> None:
    """Lần đọc danh bạ hỏng: giữ dữ liệu cũ (nếu có), chỉ đánh dấu lỗi + thời điểm để không thử
    lại liên tục."""
    with ket_noi() as c:
        c.execute("UPDATE nguoi_xem SET danh_ba_loi = %s, danh_ba_luc = now() "
                  "WHERE email = ANY(%s)", (loai, list(emails)))


def _khoa_nguoi_xem(c) -> None:
    """Khoá bảng người xem TRƯỚC khi đọc vai trò: hai người cùng xoá/hạ hai quản lý cuối cùng
    một lúc thì người sau phải đợi, rồi đọc lại thấy số quản lý đã giảm."""
    c.execute("LOCK TABLE nguoi_xem IN SHARE ROW EXCLUSIVE MODE")


def _so_quan_ly_con_lai(c, bo_email: str) -> int:
    """Số quản lý KHÁC `bo_email` (gọi sau `_khoa_nguoi_xem`, cùng giao dịch)."""
    return int(c.execute("SELECT count(*) AS n FROM nguoi_xem WHERE vai_tro = 'quan_ly' "
                         "AND email <> %s", (bo_email,)).fetchone()["n"])


def luu_nguoi_xem(ai: str, email: str, vai_tro_moi: str) -> None:
    """Thêm người xem, hoặc đổi vai trò nếu đã có. Không hạ quyền quản lý cuối cùng."""
    with ket_noi() as c:
        if vai_tro_moi != "quan_ly":
            _khoa_nguoi_xem(c)
            cu = c.execute("SELECT vai_tro FROM nguoi_xem WHERE email = %s", (email,)).fetchone()
            if cu and cu["vai_tro"] == "quan_ly" and _so_quan_ly_con_lai(c, email) == 0:
                raise LoiDuLieu("Không hạ quyền người quản lý cuối cùng — thêm quản lý khác trước.")
        c.execute("INSERT INTO nguoi_xem (email, vai_tro, them_boi) VALUES (%s, %s, %s) "
                  "ON CONFLICT (email) DO UPDATE SET vai_tro = EXCLUDED.vai_tro",
                  (email, vai_tro_moi, ai))
        _nhat_ky(c, ai, "luu_nguoi_xem", f"nguoi_xem:{email}", {"vai_tro": vai_tro_moi})


def xoa_nguoi_xem(ai: str, email: str) -> None:
    with ket_noi() as c:
        _khoa_nguoi_xem(c)
        cu = c.execute("SELECT vai_tro FROM nguoi_xem WHERE email = %s", (email,)).fetchone()
        if not cu:
            raise LoiDuLieu("Không còn người xem này.")
        if cu["vai_tro"] == "quan_ly" and _so_quan_ly_con_lai(c, email) == 0:
            raise LoiDuLieu("Không xoá được người quản lý cuối cùng — thêm quản lý khác trước.")
        c.execute("DELETE FROM nguoi_xem WHERE email = %s", (email,))
        _nhat_ky(c, ai, "xoa_nguoi_xem", f"nguoi_xem:{email}", {"vai_tro": cu["vai_tro"]})


def ghi_nhat_ky(ai: str, hanh_dong: str, doi_tuong: str, chi_tiet: dict | None = None) -> None:
    """Nhật ký cho thao tác KHÔNG sửa bảng nào của kho (vd bấm "Đồng bộ BigQuery ngay")."""
    with ket_noi() as c:
        _nhat_ky(c, ai, hanh_dong, doi_tuong, chi_tiet)


def ghi_dang_nhap(email: str, open_id: str) -> bool:
    """Mỗi lượt đăng nhập thành công: cập nhật `nguoi_xem.dang_nhap_cuoi` (không ghi nhật ký —
    mỗi lượt một dòng thì nhật ký ngập). Lần ĐẦU email này đăng nhập: ghi thêm open_id Lark vào
    nhật ký để sau tra được tài khoản Lark nào đã dùng email. -> có ghi lần đầu hay không.
    Chỉ ghi — không chặn khi open_id đổi (email cấp lại cho người khác là chuyện hợp lệ)."""
    with ket_noi() as c:
        c.execute("UPDATE nguoi_xem SET dang_nhap_cuoi = now() WHERE email = %s", (email,))
        co = c.execute("SELECT 1 AS co FROM nhat_ky WHERE hanh_dong = 'dang_nhap_lan_dau' "
                       "AND doi_tuong = %s LIMIT 1", (f"nguoi_xem:{email}",)).fetchone()
        if co:
            return False
        _nhat_ky(c, email, "dang_nhap_lan_dau", f"nguoi_xem:{email}", {"open_id": open_id})
    return True


def nhat_ky(gioi_han: int = 100) -> list[dict]:
    with ket_noi() as c:
        return c.execute("SELECT id, luc, ai, hanh_dong, doi_tuong, chi_tiet FROM nhat_ky "
                         "ORDER BY id DESC LIMIT %s", (int(gioi_han),)).fetchall()
