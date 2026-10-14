"""Kho `lang_nghe` (Postgres trên VPS) — phía dashboard. Module DUY NHẤT của dashboard có SQL.

Kết nối bằng role `lang_nghe_web` qua Unix socket + peer (user hệ điều hành của dịch vụ), không
mật khẩu; đổi bằng `LANG_NGHE_WEB_DSN` khi thử ở máy khác. Quyền của role (xem
`deploy/lang-nghe/schema.sql`): đọc mọi bảng; ghi `du_an`, `nguon`, `nguoi_xem`; chỉ đổi trạng
thái `de_xuat`; chỉ THÊM `nhat_ky`. Dashboard KHÔNG ghi `bai`, `luot_quet`, `chi_so_ngay` — đó là
phần của Mark.

Mỗi hàm sửa dữ liệu ghi thêm MỘT dòng `nhat_ky` (ai, hành động, đối tượng, chi tiết JSON) TRONG
CÙNG giao dịch: sửa thành công thì chắc chắn có nhật ký, nhật ký lỗi thì không sửa gì.

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
              "tran_usd_thang::float AS tran_usd_thang, dang_bat, tao_luc, sua_luc, sua_boi")


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
            "SELECT b.nen_tang, b.nguon_id, left(b.link, 500) AS link, "
            "left(b.tac_gia, 200) AS tac_gia, left(b.tai_khoan, 200) AS tai_khoan, b.followers, "
            "b.dang_luc, left(b.noi_dung, 1000) AS noi_dung, left(b.hashtag, 500) AS hashtag, "
            "b.sac_thai, left(b.chu_de, 100) AS chu_de, b.xem, b.thich, b.binh_luan, b.chia_se, "
            "n.loai AS nguon_loai, n.ten AS nguon_ten, n.dinh_danh AS nguon_dinh_danh, "
            "n.link AS nguon_link FROM bai b LEFT JOIN nguon n ON n.id = b.nguon_id "
            "WHERE b.du_an = %s AND b.dang_luc >= %s AND b.dang_luc < %s "
            "ORDER BY b.dang_luc DESC LIMIT %s", (du_an, tu, den, BAI_TOI_DA + 1)).fetchall()
    return {"rows": rows[:BAI_TOI_DA], "bi_cat": len(rows) > BAI_TOI_DA}


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


def luot_xong_moi_nhat() -> dict | None:
    """Lượt vừa kết thúc gần nhất (mọi dự án) — vòng kiểm 30 giây so mốc này để biết có dữ liệu
    mới khi Mark không báo được (dashboard tắt lúc Mark báo, lỗi mạng nội bộ…)."""
    with ket_noi() as c:
        return c.execute("SELECT id, du_an, ket_thuc FROM luot_quet WHERE ket_thuc IS NOT NULL "
                         "ORDER BY ket_thuc DESC, id DESC LIMIT 1").fetchone()


# ───────────────────────────── người xem + nhật ký ─────────────────────────────
def cac_nguoi_xem() -> list[dict]:
    with ket_noi() as c:
        return c.execute("SELECT email, vai_tro, them_boi, them_luc FROM nguoi_xem "
                         "ORDER BY vai_tro DESC, email").fetchall()


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


def ghi_dang_nhap_lan_dau(email: str, open_id: str) -> bool:
    """Lần ĐẦU email này đăng nhập thành công: ghi open_id Lark vào nhật ký (bảng `nguoi_xem`
    không có cột cho nó) để sau tra được tài khoản Lark nào đã dùng email. -> có ghi hay không.
    Chỉ ghi — không chặn khi open_id đổi (email cấp lại cho người khác là chuyện hợp lệ)."""
    with ket_noi() as c:
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
