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
import datetime
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
_CO_HASHTAG: list[bool] = []


def _co_hashtag(c) -> bool:
    """DB đã có cột `du_an.hashtag` (18/10/2026) chưa — bản Mark mới lên VPS TRƯỚC khi chạy
    schema.sql thì /theodoi vẫn đọc được dự án (thiếu cột là hỏng cả lượt), hashtag coi như rỗng
    (suy từ từ khoá như trước). Có rồi thì nhớ trong tiến trình (như `_co_ma_so_fb`)."""
    if _CO_HASHTAG:
        return True
    x = c.execute("SELECT 1 AS co FROM information_schema.columns WHERE table_schema = "
                  "current_schema() AND table_name = 'du_an' AND column_name = 'hashtag'"
                  ).fetchone()
    if x:
        _CO_HASHTAG.append(True)
    return bool(x)


def doc_du_an(ma: str) -> dict | None:
    with ket_noi() as c:
        return c.execute(
            "SELECT ma, ten, tu_khoa, tu_loai_tru, boi_canh, thi_truong, "
            "tran_usd_thang::float AS tran_usd_thang, dang_bat, bl_bat, bl_so_bai, bl_moi_bai, "
            "tk_bat, tk_so_bai, cau_hinh, "
            + ("hashtag " if _co_hashtag(c) else "'{}'::text[] AS hashtag ")
            + "FROM du_an WHERE ma = %s",
            (ma,)).fetchone()


def cac_du_an() -> list[dict]:
    with ket_noi() as c:
        return c.execute("SELECT ma, ten, dang_bat FROM du_an ORDER BY ma").fetchall()


def du_an_dang_bat() -> list[dict]:
    """Dự án đang bật kèm từ khoá — để lượt tìm theo từ khoá biết ghi bài vào dự án nào."""
    with ket_noi() as c:
        return c.execute("SELECT ma, ten, tu_khoa FROM du_an WHERE dang_bat ORDER BY ma").fetchall()


def nguon_cua_du_an(ma: str) -> list[dict]:
    """Mọi nguồn của dự án (kể cả tạm dừng): để gắn bài tìm theo từ khoá về nguồn đã có, không đề
    xuất lại nguồn đã nằm trong danh sách, và (`loai`, 18/10/2026) để kênh nhà không bao giờ bị luật
    seeding affiliate bắt."""
    with ket_noi() as c:
        return c.execute("SELECT id, nen_tang, dinh_danh, loai FROM nguon WHERE du_an = %s",
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
def chi_luot_gan(ma: str, toi_da: int = 20) -> list[dict]:
    """Chi phí thật các lượt /theodoi gần nhất (mới trước) — câu nhận việc nói chi THẬT bên cạnh
    ước tính TỐI ĐA (18/10/2026, `dashboard.chi_phi.chi_luot_thuc`)."""
    with ket_noi() as c:
        return c.execute(
            "SELECT id, kieu, bat_dau, ket_thuc, trang_thai, chi_phi_usd::float AS chi_phi_usd "
            "FROM luot_quet WHERE du_an = %s AND kieu = 'theo_doi' ORDER BY id DESC LIMIT %s",
            (ma, max(1, int(toi_da)))).fetchall()


def luot_dang_chay(ma: str) -> dict | None:
    """Lượt theo dõi khác của cùng dự án còn đang chạy (trong `GIO_BO_DO` giờ) — có thì
    không mở lượt mới, kẻo hai lượt cùng tiêu một phần ngân sách."""
    with ket_noi() as c:
        return c.execute(
            "SELECT id, ma_viec, bat_dau FROM luot_quet WHERE du_an = %s AND kieu = 'theo_doi' "
            "AND trang_thai = 'dang_chay' AND bat_dau > now() - make_interval(hours => %s) "
            "ORDER BY id DESC LIMIT 1", (ma, GIO_BO_DO)).fetchone()


#: Khoá advisory của việc MỞ lượt quét một dự án (17/10/2026): `mo_luot` và script gộp bài trùng
#: (`scripts/lang_nghe_gop_bai_fb.py`, mỗi nhóm một giao dịch) cùng giữ khoá này trong giao dịch —
#: lượt mở trong lúc script đang gộp một nhóm phải chờ nhóm đó commit, lượt mở trước thì câu kiểm
#: "lượt đang chạy" của script (chạy SAU khi có khoá) thấy. Không cần quyền gì thêm trên bảng.
_SQL_KHOA_LUOT = "SELECT pg_advisory_xact_lock(%s)"


def so_khoa_luot(ma: str) -> int:
    """Số khoá advisory (bigint có dấu, ổn định giữa các tiến trình / phiên bản Postgres — không
    dùng `hashtext`) cho dự án `ma`."""
    import hashlib
    return int.from_bytes(hashlib.sha1(f"lang_nghe:mo_luot:{ma}".encode()).digest()[:8],
                          "big", signed=True)


def mo_luot(ma: str, kieu: str, *, ma_viec: str | None = None,
            job_id: str | None = None, lich_id: int | None = None) -> int:
    """Mở lượt mới; đóng luôn các lượt cùng dự án bị bỏ dở quá `GIO_BO_DO` giờ. `lich_id`: lượt
    do lịch quét tự động (bảng `lich_quet`) giao — chỉ ghi cột này khi có (lịch bị xoá giữa
    chừng thì thành NULL, không hỏng khoá ngoại). Giữ khoá `so_khoa_luot` tới hết giao dịch."""
    with ket_noi() as c:
        # Chờ khoá có hạn (soát 17/10/2026): giao dịch của script gộp mà treo (vd FOR UPDATE chờ một
        # phiên idle-in-transaction) thì lượt mở báo lỗi sau 30 giây, không kẹt luồng việc nền mãi.
        c.execute("SET LOCAL lock_timeout = '30s'")
        c.execute(_SQL_KHOA_LUOT, (so_khoa_luot(ma),))
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


#: Trần `luot_quet.ghi_chu` (cột TEXT) — chỉ để chặn rác, không phải cỡ hiển thị. Trần cũ 2.000:
#: lượt 9, 10, 11 (17/10/2026) đều dài đúng 2.000 nên phần cuối phễu (Báo & Web, bình luận…) mất;
#: một lượt đủ nền tảng + web + bình luận + kiểm độ phủ chừng 3–6 nghìn ký tự. Ô nhỏ trên dashboard
#: tự cắt khi hiển thị (`dashboard/templates/ngan_sach.html`), kho giữ đủ.
GHI_CHU_TOI_DA = 20_000
_DUOI_CAT = " … (đã cắt ở trần ghi chú của lượt)"


def cat_ghi_chu(ghi_chu) -> str | None:
    """Ghi chú lượt sẵn sàng ghi: rỗng → None; quá `GHI_CHU_TOI_DA` thì cắt và ĐÁNH DẤU đã cắt
    (đọc thấy câu cụt mà không biết là bị cắt thì tưởng phễu dừng ở đó)."""
    s = str(ghi_chu or "")
    if not s:
        return None
    if len(s) <= GHI_CHU_TOI_DA:
        return s
    return s[:GHI_CHU_TOI_DA - len(_DUOI_CAT)] + _DUOI_CAT


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
             cat_ghi_chu(ghi_chu), luot_id))


def _usd_vn(x: float) -> str:
    return f"{x:.4f}".replace(".", ",")


def nang_chi_phi_luot(luot_id: int, usd: float) -> float | None:
    """Chốt LẠI chi phí lượt đã đóng (17/10/2026, `viec_nen.Viec.tinh_lai_muon`): phí sự kiện
    Apify ghi trễ sau khi run xong (0,1948 → 0,2397 USD; 0,0201 → 0,0501…). Chỉ NÂNG
    `chi_phi_usd`, không bao giờ hạ — "đã tiêu tháng" (trần tháng) cộng cột này, đếm thiếu là
    lượt sau tiêu lố. Ghi một câu vào ĐẦU ghi chú lượt (ghi chú dài bị cắt ở đuôi). -> số cũ khi
    đã nâng, None khi không cần (số mới không cao hơn, hoặc không có lượt)."""
    moi = round(float(usd or 0), 4)
    with ket_noi() as c:
        x = c.execute("SELECT chi_phi_usd::float AS usd, ghi_chu FROM luot_quet WHERE id = %s "
                      "FOR UPDATE", (int(luot_id),)).fetchone()
        if not x or moi <= round(float(x["usd"] or 0), 4):
            return None
        cu = float(x["usd"] or 0)
        cau = (f"chi phí chốt lại {_usd_vn(cu)} → {_usd_vn(moi)} USD (phí sự kiện Apify ghi sau "
               "khi run xong)")
        c.execute("UPDATE luot_quet SET chi_phi_usd = %s, ghi_chu = %s WHERE id = %s",
                  (moi, cat_ghi_chu(f"{cau}; {x['ghi_chu']}" if x.get("ghi_chu") else cau),
                   int(luot_id)))
    return cu


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
#: Số "tụt về 0" (19/10/2026, bài TikTok 1.387 bình luận ghi thành 0 dù TikTok vẫn hiện 1.389):
#: nhiều parser đổi trường thiếu thành 0 (`int(x or 0)`). Bài đã có số > 0 mà lượt mới trả đúng 0
#: thì coi như nguồn không trả số — giữ số cũ; lượt sau đọc được số thật sẽ ghi đè.
_GIU_KHI_VE_0 = "COALESCE(NULLIF({moi}, CASE WHEN {cu} > 0 THEN 0 END), {cu})"


def _so_da_giu(x, r: dict) -> list:
    """Số ghi vào `chi_so_ngay`: số của bài SAU khi cập nhật (đã giữ số cũ khi tụt về 0) cho cột
    lượt này có đọc; cột lượt này không đọc vẫn để NULL như trước."""
    return [(x[k] if isinstance(x, dict) and k in x else r.get(k)) if r.get(k) is not None else None
            for k in _SO]
#: Cột riêng của bài Báo & Web (16/10/2026, `nguon_web`): chỉ đưa vào câu ghi khi dòng có giá trị
#: — bài mạng xã hội ghi đúng câu lệnh cũ, DB chưa chạy bản schema mới vẫn ghi được bài MXH.
_COT_WEB = ("kieu_trang", "muc_nhac", "la_pr")
#: Id số của bài Facebook (17/10/2026, `khu_trung_fb`): chỉ ghi khi DB đã có cột (`_co_ma_so_fb`).
_COT_FB = ("ma_so_fb",)
_CO_MA_SO_FB: list[bool] = []


def _co_ma_so_fb(c) -> bool:
    """DB đã chạy bản schema có cột `bai.ma_so_fb` chưa. Bản code mới lên VPS TRƯỚC khi chạy
    schema.sql thì vẫn ghi được bài (không đọc/ghi cột chưa có — lỗi cột là hỏng CẢ lô bài đã
    trả tiền). Có rồi thì nhớ luôn trong tiến trình."""
    if _CO_MA_SO_FB:
        return True
    x = c.execute("SELECT 1 AS co FROM information_schema.columns WHERE table_schema = "
                  "current_schema() AND table_name = 'bai' AND column_name = 'ma_so_fb'"
                  ).fetchone()
    if x:
        _CO_MA_SO_FB.append(True)
    return bool(x)


#: Thứ tự chọn bản GIỮ khi nhiều bản trùng cũ cùng khớp — ĐÚNG thứ tự `chon_giu` của script gộp
#: (`scripts/lang_nghe_gop_bai_fb.py`): `bl_da_lay` lớn nhất, chưa cào (NULL) = -1 thấp hơn cả 0
#: (soát 17/10/2026: bản trước COALESCE về 0 nên NULL hoà với 0 — kho và script có thể giữ hai bản
#: khác nhau); hoà thì `thay_lan_dau` sớm nhất (NULL cuối, như `datetime.max` của script), rồi khoá
#: theo thứ tự mã ký tự (`COLLATE "C"` = so chuỗi Python, không theo collation của DB).
_THU_TU_GIU = 'COALESCE(bl_da_lay, -1) DESC, thay_lan_dau, khoa COLLATE "C"'
_SQL_FB_THEO_SO = (
    "SELECT khoa FROM bai WHERE du_an = %s AND nen_tang = 'facebook' AND ({dk}) "
    # Nhiều bản trùng cũ cùng khớp (chưa chạy script gộp): chọn đúng bản script sẽ GIỮ.
    f"ORDER BY {_THU_TU_GIU} LIMIT 1")


def _khoa_fb_cu(c, ma: str, r: dict, co_cot: bool) -> str | None:
    """Khoá của bài Facebook ĐÃ CÓ trong kho mà dòng `r` là bản trùng (khoá khác, `khu_trung_fb`):
    1. cùng id số (cột `ma_so_fb`, khoá "facebook:<số>"); 2. cùng chủ bài + phút + nội dung.
    None khi khoá của `r` đã có (upsert thường) hoặc `r` là bài mới."""
    import khu_trung_fb as KT
    if c.execute("SELECT 1 AS co FROM bai WHERE du_an = %s AND khoa = %s",
                 (ma, r["khoa"])).fetchone():
        return None
    ids = sorted(KT.cac_ma_so(r))
    if ids:
        khoa = [f"facebook:{x}" for x in ids]
        dk, ts = ("ma_so_fb = ANY(%s) OR khoa = ANY(%s)", [ids, khoa]) if co_cot \
            else ("khoa = ANY(%s)", [khoa])
        x = c.execute(_SQL_FB_THEO_SO.format(dk=dk), [ma, *ts]).fetchone()
        if x:
            return x["khoa"]
    p = KT.phut(r.get("dang_luc"))
    if p is None or not KT.chu_bai(r):
        return None
    cot = "khoa, link, tai_khoan, tac_gia, noi_dung, ma_noi_dung, dang_luc" + (
        ", ma_so_fb" if co_cot else "")
    for x in c.execute(
            f"SELECT {cot} FROM bai WHERE du_an = %s AND nen_tang = 'facebook' AND "
            f"dang_luc >= %s AND dang_luc < %s ORDER BY {_THU_TU_GIU}",
            (ma, p, p + datetime.timedelta(minutes=1))).fetchall():
        if x["khoa"] != r["khoa"] and KT.cung_bai(r, x):
            return x["khoa"]
    return None


def _chuan_fb(r: dict) -> dict:
    """Dòng bài Facebook sẵn sàng tra trùng: `ma_so_fb` (bộ chuẩn hoá đã điền, hoặc bóc từ link)."""
    import khu_trung_fb as KT
    return {**r, "ma_so_fb": KT.ma_so_fb(r)}


def khoa_fb_trung(ma: str, rows: list[dict]) -> dict[str, str]:
    """{khoá của dòng: khoá bài ĐÃ CÓ} cho các dòng Facebook là bản trùng của bài trong kho (pfbid
    đổi giữa các lượt cào) — tìm theo từ khoá tách bài đã biết TRƯỚC bước AI (`theo_doi`), để bài
    cũ chỉ cập nhật số, không gửi AI lại. Chỉ đọc. Mỗi dòng cần khoa, link, tai_khoan, tac_gia,
    dang_luc, noi_dung (+ ma_so_fb nếu có)."""
    import loc_rac
    fb = [r for r in rows if r.get("nen_tang") == "facebook" and r.get("khoa")]
    if not fb:
        return {}
    ra: dict[str, str] = {}
    with ket_noi() as c:
        co_cot = _co_ma_so_fb(c)
        for r in fb:
            r = _chuan_fb({**r, "ma_noi_dung": r.get("ma_noi_dung") or loc_rac.ma_noi_dung(
                r.get("noi_dung") or "", loc_rac.BAI_TRUNG_TOI_THIEU_CHU)})
            k = _khoa_fb_cu(c, ma, r, co_cot)
            if k:
                ra[r["khoa"]] = k
    return ra


def ghi_bai(ma: str, luot_id: int, kieu: str, rows: list[dict]) -> tuple[int, int]:
    """Upsert bài đã giữ + số liệu của ngày hôm nay (giờ VN) — dòng mang `_ngay_so` (script nạp
    raw: ngày ĐỌC raw, soát 18/10/2026) thì ảnh chụp vào ngày đó. -> (bài mới, bài cập nhật).

    Bài đã có: số liệu lấy bản mới; nhãn AI (sắc thái/chủ đề) chỉ đè khi lượt này có nhãn;
    bài từng vào bằng `theo_doi` thì giữ nguyên kiểu đó (quét từ khoá về sau không hạ cấp).
    Bài Facebook (17/10/2026): bản trùng của bài đã có (pfbid đổi mỗi lượt cào — `khu_trung_fb`)
    dùng lại KHOÁ CŨ: chỉ cập nhật số, không thêm bài; bình luận cào sau gắn vào khoá cũ (lượt cào
    bình luận đọc bài từ kho)."""
    if not rows:
        return 0, 0
    import loc_rac
    moi = cu = 0
    with ket_noi() as c:
        co_cot: bool | None = None
        for r in rows:
            r = {**r, "ma_noi_dung": r.get("ma_noi_dung") or loc_rac.ma_noi_dung(
                r.get("noi_dung") or "", loc_rac.BAI_TRUNG_TOI_THIEU_CHU)}
            if r.get("nen_tang") == "facebook":
                if co_cot is None:
                    co_cot = _co_ma_so_fb(c)
                r = _chuan_fb(r)
                khoa_cu = _khoa_fb_cu(c, ma, r, co_cot)
                if khoa_cu:
                    r["khoa"] = khoa_cu
            cac = _COT_BAI + tuple(k for k in _COT_WEB if r.get(k) is not None) + tuple(
                k for k in _COT_FB if co_cot and r.get(k) is not None)
            cot = ", ".join(cac)
            # Nguồn có thể bị xoá trên dashboard giữa lượt quét: lấy id qua truy vấn con để nguồn
            # đã xoá thành NULL, không làm hỏng khoá ngoại (và rollback) cả lô bài đã trả tiền.
            dat = ", ".join("(SELECT id FROM nguon WHERE id = %s)" if k == "nguon_id" else "%s"
                            for k in cac)
            them = "".join(f"{k} = COALESCE(EXCLUDED.{k}, bai.{k}), " for k in cac
                           if k in _COT_WEB)
            # Id số: GIỮ id đã có (bản trùng tìm thấy qua phút + nội dung có thể mang id khác
            # loại — id reel thay vì id bài); dòng cũ chưa có id thì điền.
            them += "".join(f"{k} = COALESCE(bai.{k}, EXCLUDED.{k}), " for k in cac
                            if k in _COT_FB)
            gia_tri = [r.get(k) for k in cac]
            # Lần đọc cũ (`_ngay_so`, nạp raw) trùng bài đã có (bản trùng Facebook): số chỉ NÂNG.
            ham = "GREATEST" if r.get("_ngay_so") is not None else "COALESCE"
            x = c.execute(
                f"INSERT INTO bai (du_an, kieu_quet, luot_dau, luot_cuoi, {cot}) "
                f"VALUES (%s, %s, %s, %s, {dat}) "
                "ON CONFLICT (du_an, khoa) DO UPDATE SET "
                + "".join(f"{k} = GREATEST(EXCLUDED.{k}, bai.{k}), " if ham == "GREATEST" else
                          f"{k} = " + _GIU_KHI_VE_0.format(moi=f"EXCLUDED.{k}", cu=f"bai.{k}") + ", "
                          for k in _SO) +
                "followers = COALESCE(EXCLUDED.followers, bai.followers), "
                "sac_thai = COALESCE(EXCLUDED.sac_thai, bai.sac_thai), "
                "chu_de = COALESCE(EXCLUDED.chu_de, bai.chu_de), "
                "nguon_id = COALESCE(bai.nguon_id, EXCLUDED.nguon_id), "
                "ma_noi_dung = COALESCE(EXCLUDED.ma_noi_dung, bai.ma_noi_dung), "
                f"{them}"
                "kieu_quet = CASE WHEN bai.kieu_quet = 'theo_doi' THEN 'theo_doi' "
                "ELSE EXCLUDED.kieu_quet END, "
                "cap_nhat_cuoi = now(), luot_cuoi = EXCLUDED.luot_cuoi "
                "RETURNING (xmax = 0) AS moi, xem, thich, binh_luan, chia_se",
                [ma, kieu, luot_id, luot_id, *gia_tri]).fetchone()
            if x and x["moi"]:
                moi += 1
            else:
                cu += 1
            if any(r.get(k) is not None for k in _SO) and r.get("_ngay_so") is not None:
                # Lần đọc CŨ (script nạp raw, soát 18/10/2026): ảnh chụp vào đúng NGÀY ĐỌC, ngày đó
                # đã có dòng thì giữ số lớn hơn từng cột (như `nang_so_lieu`).
                c.execute(
                    "INSERT INTO chi_so_ngay (du_an, khoa, ngay, xem, thich, binh_luan, chia_se) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (du_an, khoa, ngay) DO "
                    "UPDATE SET " + ", ".join(f"{k} = GREATEST(EXCLUDED.{k}, chi_so_ngay.{k})"
                                              for k in _SO),
                    [ma, r["khoa"], r["_ngay_so"], *[r.get(k) for k in _SO]])
            elif any(r.get(k) is not None for k in _SO):
                c.execute(
                    "INSERT INTO chi_so_ngay (du_an, khoa, ngay, xem, thich, binh_luan, chia_se) "
                    "VALUES (%s, %s, (now() AT TIME ZONE %s)::date, %s, %s, %s, %s) "
                    "ON CONFLICT (du_an, khoa, ngay) DO UPDATE SET xem = EXCLUDED.xem, "
                    "thich = EXCLUDED.thich, binh_luan = EXCLUDED.binh_luan, "
                    "chia_se = EXCLUDED.chia_se",
                    [ma, r["khoa"], _TZ, *_so_da_giu(x, r)])
    return moi, cu


def cap_nhat_so_lieu(ma: str, luot_id: int, rows: list[dict]) -> int:
    """CHỈ cập nhật số liệu của bài ĐÃ CÓ (+ số của ngày hôm nay). -> số bài cập nhật được.

    Không đi qua `ghi_bai`: dòng chỉ có số thì INSERT thiếu cột NOT NULL — Postgres kiểm
    NOT NULL trước khi xét ON CONFLICT nên hỏng cả lô (review 14/10)."""
    n = 0
    with ket_noi() as c:
        for r in rows:
            x = c.execute(
                "UPDATE bai SET " + "".join(
                    f"{k} = " + _GIU_KHI_VE_0.format(moi="%s::bigint", cu=k) + ", " for k in _SO) +
                "cap_nhat_cuoi = now(), luot_cuoi = %s WHERE du_an = %s AND khoa = %s "
                "RETURNING khoa, xem, thich, binh_luan, chia_se",
                [*[r.get(k) for k in _SO], luot_id, ma, r["khoa"]]).fetchone()
            if not x:
                continue
            n += 1
            c.execute(
                "INSERT INTO chi_so_ngay (du_an, khoa, ngay, xem, thich, binh_luan, chia_se) "
                "VALUES (%s, %s, (now() AT TIME ZONE %s)::date, %s, %s, %s, %s) "
                "ON CONFLICT (du_an, khoa, ngay) DO UPDATE SET xem = EXCLUDED.xem, "
                "thich = EXCLUDED.thich, binh_luan = EXCLUDED.binh_luan, "
                "chia_se = EXCLUDED.chia_se",
                [ma, r["khoa"], _TZ, *_so_da_giu(x, r)])
    return n


def nang_so_lieu(ma: str, luot_id: int, rows: list[dict], ngay) -> int:
    """Số liệu của một lần đọc CŨ (script nạp raw đã trả tiền, 18/10/2026) cho bài ĐÃ CÓ: mỗi số
    chỉ được NÂNG (GREATEST — xem/thích/bình luận/chia sẻ là số luỹ kế; lượt quét sau lần đọc đó
    đã ghi số lớn hơn thì giữ), `cap_nhat_cuoi`/`luot_cuoi` chỉ đổi khi có số tăng. Ảnh chụp ghi
    vào ĐÚNG ngày đọc `ngay` (không phải hôm nay): ngày đó đã có dòng thì giữ số lớn hơn từng cột.
    Khác `cap_nhat_so_lieu` (số MỚI NHẤT đè số cũ, ảnh chụp hôm nay) — dùng nó cho số cũ là hạ số
    thật xuống và ghi nhầm ngày. Dòng mang `_ngay_so` (ngày đọc của CHÍNH lần đọc đó) thắng `ngay`
    chung của phần. -> số bài có ít nhất một số tăng."""
    n = 0
    tang = " OR ".join(f"%s::bigint > COALESCE({k}, -1)" for k in _SO)
    with ket_noi() as c:
        for r in rows:
            v = [r.get(k) for k in _SO]
            if all(x is None for x in v):
                continue
            x = c.execute(
                "UPDATE bai SET " + ", ".join(f"{k} = GREATEST(%s::bigint, {k})" for k in _SO)
                + ", cap_nhat_cuoi = now(), luot_cuoi = %s WHERE du_an = %s AND khoa = %s "
                f"AND ({tang}) RETURNING khoa", [*v, luot_id, ma, r["khoa"], *v]).fetchone()
            n += 1 if x else 0
            c.execute(
                "INSERT INTO chi_so_ngay (du_an, khoa, ngay, xem, thich, binh_luan, chia_se) "
                "SELECT %s, %s, %s, %s, %s, %s, %s WHERE EXISTS (SELECT 1 FROM bai WHERE "
                "du_an = %s AND khoa = %s) ON CONFLICT (du_an, khoa, ngay) DO UPDATE SET "
                + ", ".join(f"{k} = GREATEST(EXCLUDED.{k}, chi_so_ngay.{k})" for k in _SO),
                [ma, r["khoa"], r.get("_ngay_so") or ngay, *v, ma, r["khoa"]])
    return n


def khoa_theo_luot_dau(ma: str, luot_id: int) -> list[dict]:
    """Bài lần đầu vào kho ở lượt `luot_id` (khoá, lượt cuối, đã cào bình luận chưa, số bình luận
    đã cào) — hoàn tác script nạp raw: chỉ xoá bài chưa bị lượt sau đụng tới. Chỉ đọc."""
    with ket_noi() as c:
        return c.execute(
            "SELECT b.khoa, b.luot_cuoi, b.bl_lay_luc, (SELECT count(*) FROM binh_luan x WHERE "
            "x.du_an = b.du_an AND x.khoa_bai = b.khoa) AS so_bl FROM bai b WHERE b.du_an = %s "
            "AND b.luot_dau = %s ORDER BY b.khoa", (ma, int(luot_id))).fetchall()


def lich_su_tai_khoan(ma: str, tai_khoan: list[str], tu) -> list[dict]:
    """Bài đã giữ của các tài khoản (`tai_khoan` chữ thường) đăng từ `tu` — lịch sử nhịp đăng cho
    luật seeding affiliate (`loc_rac.tai_khoan_seeding`, 18/10/2026). Soát M4: kèm thích / chia sẻ
    (tín hiệu tương tác khi nền tảng không có lượt xem) và link / nội dung / id số Facebook (khoá
    ổn định — pfbid đổi mỗi lượt, `theo_doi._khoa_loai_on_dinh`). Chỉ đọc."""
    ds = sorted({str(x).strip().lstrip("@").lower() for x in tai_khoan if str(x or "").strip()})
    if not ds:
        return []
    with ket_noi() as c:
        so_fb = "ma_so_fb" if _co_ma_so_fb(c) else "NULL::text AS ma_so_fb"
        return c.execute(
            "SELECT khoa, nen_tang, lower(tai_khoan) AS tai_khoan, tac_gia, dang_luc, binh_luan, "
            "xem, thich, chia_se, link, CASE WHEN nen_tang = 'facebook' THEN noi_dung END AS "
            f"noi_dung, {so_fb} FROM bai WHERE du_an = %s AND lower(tai_khoan) = ANY(%s) "
            "AND dang_luc >= %s", (ma, ds, tu)).fetchall()


def bai_youtube_can_lam_moi(ma: str, ngay: int = 14, toi_da: int = 200) -> list[dict]:
    """Bài YouTube đã giữ, đăng trong `ngay` ngày, chưa đọc số hôm nay (giờ VN). videos.list
    miễn phí (1 đơn vị/50 video) nên cập nhật được hằng ngày mà không tốn Apify."""
    with ket_noi() as c:
        return c.execute(
            "SELECT khoa, link FROM bai WHERE du_an = %s AND nen_tang = 'youtube' AND "
            "dang_luc >= now() - make_interval(days => %s) AND "
            "cap_nhat_cuoi < (date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s) "
            "ORDER BY dang_luc DESC LIMIT %s", (ma, ngay, _TZ, _TZ, toi_da)).fetchall()


def khoa_da_co(ma: str, khoa: list[str]) -> set[str]:
    """Khoá bài nào trong `khoa` đã có trong kho của dự án (tìm theo từ khoá: bài đã biết thì
    chỉ cập nhật số liệu, không lọc/AI lại — `theo_doi_api.tach_da_biet`)."""
    if not khoa:
        return set()
    with ket_noi() as c:
        return {r["khoa"] for r in c.execute(
            "SELECT khoa FROM bai WHERE du_an = %s AND khoa = ANY(%s)",
            (ma, list(khoa))).fetchall()}


def bai_can_lam_moi(ma: str, nen_tang: str, tu, toi_da: int) -> list[dict]:
    """Bài của nền tảng đăng từ `tu`, CHƯA cập nhật số hôm nay (giờ VN), nhiều tương tác nhất
    trước — làm mới số liệu theo link (`theo_doi_api.lam_moi_tiktok`)."""
    with ket_noi() as c:
        return c.execute(
            "SELECT khoa, link FROM bai WHERE du_an = %s AND nen_tang = %s AND link <> '' AND "
            "dang_luc >= %s AND "
            "cap_nhat_cuoi < (date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s) "
            "ORDER BY COALESCE(thich, 0) + COALESCE(binh_luan, 0) + COALESCE(chia_se, 0) DESC, "
            "COALESCE(xem, 0) DESC LIMIT %s",
            (ma, nen_tang, tu, _TZ, _TZ, toi_da)).fetchall()


def nhip_dang_nguon(ma: str, ngay: int = 14) -> dict[int, int]:
    """{id nguồn: số bài CAO NHẤT nguồn đăng trong MỘT ngày (giờ VN)} trên bài đã giữ đăng trong
    `ngay` ngày qua — co số bài mỗi lần theo nhịp đăng (18/10/2026, `dashboard.chi_phi.
    so_bai_co_gian`). Nguồn không có bài trong cửa sổ thì không có khoá."""
    with ket_noi() as c:
        rows = c.execute(
            "SELECT nguon_id, max(n) AS n FROM (SELECT nguon_id, "
            "(dang_luc AT TIME ZONE %s)::date AS d, count(*) AS n FROM bai WHERE du_an = %s "
            "AND nguon_id IS NOT NULL AND dang_luc >= now() - make_interval(days => %s) "
            "GROUP BY 1, 2) t GROUP BY 1", (_TZ, ma, int(ngay))).fetchall()
    return {int(r["nguon_id"]): int(r["n"]) for r in rows}


def lich_chien_dich(ma: str) -> list[dict]:
    """Mọi lịch kiểu chiến dịch của dự án (bật hay tắt) — nới phạm vi theo dõi theo khung
    chiến dịch (`theo_doi_api.pham_vi`)."""
    with ket_noi() as c:
        return c.execute(f"SELECT {_COT_LICH} FROM lich_quet WHERE du_an = %s AND "
                         "kieu = 'chien_dich' ORDER BY id", (ma,)).fetchall()


def co_bai_tu_khoa(ma: str) -> bool:
    """Dự án đã từng có bài tìm theo từ khoá chưa (lần đầu thì lùi xa hơn)."""
    with ket_noi() as c:
        return bool(c.execute("SELECT EXISTS (SELECT 1 FROM bai WHERE du_an = %s AND "
                              "kieu_quet = 'tu_khoa') AS co", (ma,)).fetchone()["co"])


# ───────────────────────────── kiểm độ phủ 2 lần/tuần (17/10/2026) ─────────────────────────────
def hashtag_gan_day(ma: str, nen_tang: str, tu, toi_da: int = 3000) -> list[str]:
    """Cột `hashtag` của bài nền tảng `nen_tang` đăng từ `tu` (mới nhất trước) — đếm hashtag
    chiến dịch hay đi cùng brand (`kiem_do_phu.chon_tag`)."""
    with ket_noi() as c:
        return [r["hashtag"] for r in c.execute(
            "SELECT hashtag FROM bai WHERE du_an = %s AND nen_tang = %s AND dang_luc >= %s AND "
            "btrim(COALESCE(hashtag, '')) <> '' ORDER BY dang_luc DESC LIMIT %s",
            (ma, nen_tang, tu, toi_da)).fetchall()]


def tac_gia_noi_bat(ma: str, nen_tang: str, tu, toi_da: int = 20) -> list[dict]:
    """Tài khoản đăng bài nhiều thảo luận nhất (Σ 1 + bình luận) từ `tu`. -> [{tai_khoan,
    thao_luan, so_bai}]."""
    with ket_noi() as c:
        return c.execute(
            "SELECT lower(tai_khoan) AS tai_khoan, sum(1 + COALESCE(binh_luan, 0))::bigint AS "
            "thao_luan, count(*) AS so_bai FROM bai WHERE du_an = %s AND nen_tang = %s AND "
            "dang_luc >= %s AND btrim(tai_khoan) <> '' GROUP BY lower(tai_khoan) "
            "ORDER BY thao_luan DESC, so_bai DESC LIMIT %s", (ma, nen_tang, tu, toi_da)).fetchall()


def de_xuat_dang_xet(ma: str, nen_tang: str) -> list[dict]:
    """Đề xuất nguồn đang chờ hoặc đã duyệt của nền tảng (nhiều thảo luận trước)."""
    with ket_noi() as c:
        return c.execute(
            "SELECT dinh_danh, thao_luan, trang_thai FROM de_xuat WHERE du_an = %s AND "
            "nen_tang = %s AND trang_thai IN ('cho', 'da_duyet') ORDER BY thao_luan DESC, id",
            (ma, nen_tang)).fetchall()


def de_xuat_tu_choi_gan(ma: str, nen_tang: str, ngay: int = 60) -> set[str]:
    """Tài khoản bị từ chối đề xuất trong `ngay` ngày gần nhất (kiểm độ phủ không đề xuất lại)."""
    with ket_noi() as c:
        rows = c.execute(
            "SELECT dinh_danh FROM de_xuat WHERE du_an = %s AND nen_tang = %s AND "
            "trang_thai = 'tu_choi' AND COALESCE(xu_ly_luc, de_xuat_luc) >= "
            "now() - make_interval(days => %s)", (ma, nen_tang, int(ngay))).fetchall()
    return {str(r["dinh_danh"]).lower() for r in rows}


_COT_DO_PHU = ("du_an", "luot_id", "nen_tang", "so_mau", "so_nhac", "so_da_co", "so_da_loai",
               "so_sot", "thao_luan_nhac", "thao_luan_da_co", "do_phu", "do_phu_tl", "bo_sung",
               "so_yeu_cau", "chi_phi_usd", "mau", "bai_sot", "hanh_dong")


_JSON_DO_PHU = ("mau", "bai_sot", "hanh_dong")


def ghi_kiem_do_phu(r: dict) -> int:
    """Ghi MỘT lượt kiểm độ phủ (bảng `kiem_do_phu`). -> id. `mau`, `bai_sot`, `hanh_dong` là
    JSON."""
    import json
    gt = [json.dumps(r.get(k) if r.get(k) is not None else ([] if k == "bai_sot" else {}),
                     ensure_ascii=False) if k in _JSON_DO_PHU else r.get(k)
          for k in _COT_DO_PHU]
    with ket_noi() as c:
        x = c.execute(
            f"INSERT INTO kiem_do_phu ({', '.join(_COT_DO_PHU)}) VALUES ("
            + ", ".join("(SELECT id FROM luot_quet WHERE id = %s)" if k == "luot_id"
                        else "%s::jsonb" if k in _JSON_DO_PHU else "%s"
                        for k in _COT_DO_PHU)
            + ") RETURNING id", gt).fetchone()
    return int(x["id"])


#: Cột của `han_muc_apify` Mark ghi (18/10/2026) — bài thử đối chiếu với schema.sql.
_COT_HAN_MUC = ("goi", "da_dung_usd", "tran_usd", "chu_ky_tu", "chu_ky_den", "tran_luot_usd",
                "du_tru_usd", "luot_id", "nguon_ghi")


def ghi_han_muc(r: dict) -> int:
    """Ghi MỘT ảnh chụp hạn mức gói Apify (bảng `han_muc_apify`) cho trang Ngân sách — dashboard
    không giữ token Apify. `luot_id` không còn trong `luot_quet` thì ghi NULL. -> id."""
    with ket_noi() as c:
        x = c.execute(
            f"INSERT INTO han_muc_apify ({', '.join(_COT_HAN_MUC)}) VALUES ("
            + ", ".join("(SELECT id FROM luot_quet WHERE id = %s)" if k == "luot_id" else "%s"
                        for k in _COT_HAN_MUC)
            + ") RETURNING id", [r.get(k) for k in _COT_HAN_MUC]).fetchone()
    return int(x["id"])


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
    chưa cào hoặc bình luận tăng đủ nhiều. Bài chưa cào đi trước, rồi bài thiếu nhiều bình luận.
    `bl_goc` (18/10/2026): số bình luận GỐC đã có trong kho — TikTok cào dở thì đọc tiếp từ đó
    (`theo_doi._chia_lo_bl`, `tiktok_api.binh_luan(bat_dau=…)`); khoá chính (du_an, khoa_bai, ma)
    phủ phép đếm."""
    if toi_da <= 0 or not nen_tang:
        return []
    with ket_noi() as c:
        return c.execute(
            "SELECT b.khoa, b.nen_tang, b.link, b.tai_khoan, b.tac_gia, b.binh_luan, "
            "b.bl_lay_luc, b.bl_da_lay, b.bl_lay_khi_co, n.loai AS nguon_loai, "
            "(SELECT count(*) FROM binh_luan c WHERE c.du_an = b.du_an AND c.khoa_bai = b.khoa "
            "AND NOT c.la_tra_loi) AS bl_goc "
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
           "ma_noi_dung", "link", "ma_cha", "san_pham")
#: Nhãn chỉ xét được trên KHO (cần lịch sử nhiều tài khoản / nhiều bình luận), không phải từ một
#: bình luận: cào lại thấy bình luận "hợp lệ" thì vẫn giữ nhãn kho, không gửi lại AI.
_NHAN_KHO = "(binh_luan.loai = 'seeding' OR binh_luan.ly_do_loc = 'affiliate_hang_loat')"
_GIU_NHAN_KHO = f"(EXCLUDED.loai = 'hop_le' AND {_NHAN_KHO})"


def goc_thieu_tra_loi(ma: str, khoa_bai: list[str], tran_moi_goc: int, toi_da: int = 200,
                      bo: list[str] | tuple = ()) -> dict[str, list[tuple[str, int, int]]]:
    """{khoá bài: [(mã bình luận gốc, số trả lời nền tảng báo, số trả lời kho đã có), …]} — gốc
    ĐÃ có trong kho mà số trả lời trong kho còn dưới min(số báo, `tran_moi_goc` — một yêu cầu trả
    lời đọc được tối đa bấy nhiêu), thiếu nhiều trước, tối đa `toi_da` gốc mỗi bài (soát 18/10/2026:
    video TikTok đã đọc hết trang gốc mà vẫn thiếu thì lấy trả lời cho các gốc này —
    `tiktok_api.binh_luan`).

    `bo` = khoá "<khoa_bai>\\x1f<ma>" bỏ qua: gốc đã hỏi mà không thêm được trả lời nào (trả lời
    bị ẩn / xoá — số báo không bao giờ đạt; `theo_doi._gan_doc_tiep_bl`). Giới hạn `toi_da` ngay
    trong SQL (`row_number` theo bài): video lớn có hàng nghìn gốc thiếu thì không kéo hết về rồi
    mới cắt ở Python."""
    if not khoa_bai:
        return {}
    with ket_noi() as c:
        rows = c.execute(
            "SELECT khoa_bai, ma, tra_loi, da_co FROM ("
            "SELECT g.khoa_bai, g.ma, g.tra_loi, count(r.ma) AS da_co, row_number() OVER ("
            "PARTITION BY g.khoa_bai ORDER BY LEAST(g.tra_loi, %(tran)s) - count(r.ma) DESC, g.ma"
            ") AS thu_tu FROM binh_luan g "
            "LEFT JOIN binh_luan r ON r.du_an = g.du_an AND r.khoa_bai = g.khoa_bai "
            "AND r.ma_cha = g.ma WHERE g.du_an = %(ma)s AND g.khoa_bai = ANY(%(khoa)s) "
            "AND NOT g.la_tra_loi AND COALESCE(g.tra_loi, 0) > 0 "
            "AND NOT ((g.khoa_bai || chr(31) || g.ma) = ANY(%(bo)s)) "
            "GROUP BY g.khoa_bai, g.ma, g.tra_loi HAVING count(r.ma) < LEAST(g.tra_loi, %(tran)s)"
            ") x WHERE thu_tu <= %(toi_da)s ORDER BY khoa_bai, thu_tu",
            {"ma": ma, "khoa": list(khoa_bai), "tran": int(tran_moi_goc), "bo": list(bo),
             "toi_da": int(toi_da)}).fetchall()
    ra: dict[str, list[tuple[str, int, int]]] = {}
    for r in rows:
        ra.setdefault(r["khoa_bai"], []).append(
            (str(r["ma"]), int(r["tra_loi"]), int(r["da_co"] or 0)))
    return ra


def ghi_binh_luan(ma: str, luot_id: int, rows: list[dict],
                  da_lay: dict[str, tuple[int, int | None]],
                  khong_tinh_thieu: set[str] | None = None) -> tuple[int, int]:
    """Upsert bình luận (mỗi dòng có `khoa_bai` + `_COT_BL`) và đánh dấu bài đã cào
    (`da_lay` = {khoa bài: (số bình luận lấy được, số nền tảng báo lúc đó)}) trong CÙNG giao
    dịch. Nhãn chỉ đè khi lượt này có nhãn. -> (mới, cập nhật). `khong_tinh_thieu` (soát
    18/10/2026): khoá bài mà lượt này KHÔNG tính là một lần thiếu dù không thêm được gì (trang
    đọc tiếp rỗng — lỗi vị trí của Mark, không phải bài hết bình luận): giữ `bl_lan_thieu`."""
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
                # không đưa về hop_le, và không mang lại sắc thái/chủ đề. Lượt này thấy KHÔNG còn
                # hop_le (spam, trả lời của brand…) thì cũng xoá sắc thái/chủ đề cũ: chỉ dòng
                # hop_le mang nhãn AI (mô tả cột sac_thai).
                f"sac_thai = CASE WHEN {_GIU_NHAN_KHO} OR EXCLUDED.loai <> 'hop_le' THEN NULL "
                "ELSE COALESCE(EXCLUDED.sac_thai, binh_luan.sac_thai) END, "
                f"chu_de = CASE WHEN {_GIU_NHAN_KHO} OR EXCLUDED.loai <> 'hop_le' THEN NULL "
                "ELSE COALESCE(EXCLUDED.chu_de, binh_luan.chu_de) END, "
                # Món hỏi mua (17/10/2026): như chủ đề — lượt có món thì ghi, không thì giữ món
                # cũ; dòng hết hop_le thì bỏ.
                f"san_pham = CASE WHEN {_GIU_NHAN_KHO} OR EXCLUDED.loai <> 'hop_le' THEN NULL "
                "ELSE COALESCE(EXCLUDED.san_pham, binh_luan.san_pham) END, "
                f"loai = CASE WHEN {_GIU_NHAN_KHO} THEN binh_luan.loai ELSE EXCLUDED.loai END, "
                f"ly_do_loc = CASE WHEN {_GIU_NHAN_KHO} THEN binh_luan.ly_do_loc "
                "ELSE EXCLUDED.ly_do_loc END, "
                "ma_noi_dung = EXCLUDED.ma_noi_dung, "
                # 16/10: nhận ra trả lời của fanpage muộn hơn (so tên gọn với chủ bài) thì bật cờ
                # cho dòng cũ — cờ chỉ bật, không tắt; `loai` thì vẫn theo lượt này.
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
                "  WHEN %s THEN bai.bl_lan_thieu "
                "  ELSE bai.bl_lan_thieu + 1 END "
                "FROM (SELECT GREATEST(%s, (SELECT count(*) FROM binh_luan b WHERE "
                "      b.du_an = %s AND b.khoa_bai = %s)) AS moi) t "
                "WHERE bai.du_an = %s AND bai.khoa = %s",
                (co, co, BL_DU_TOI_THIEU, khoa in (khong_tinh_thieu or ()), n, ma, khoa, ma,
                 khoa))
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
        "san_pham = NULL, "
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
            "sac_thai = NULL, chu_de = NULL, san_pham = NULL, cap_nhat_cuoi = now() "
            "WHERE du_an = %s AND "
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


# ───────────────────────────── gán nhãn nền (17/10/2026, `gan_nhan_nen`) ─────────────────────────────
# Kho LÀ hàng đợi: dòng cần AI = bình luận `hop_le` (không của thương hiệu, có chữ) chưa có sắc
# thái, và bài chưa có sắc thái/chủ đề. Không có cột trạng thái riêng — khởi động lại giữa chừng
# thì nhịp sau đọc lại đúng các dòng còn trống. `bo` = khoá các dòng đã thử quá số lần (sổ của
# `gan_nhan_nen`), để một dòng model luôn bỏ sót không chặn hàng đợi.
_SQL_BL_CHO = (
    "FROM binh_luan WHERE du_an = %s AND loai = 'hop_le' AND NOT cua_thuong_hieu AND "
    "sac_thai IS NULL AND btrim(noi_dung) <> ''")
# Bài kênh nhà không vào hàng: dashboard không tính sắc thái/chủ đề của bài thương hiệu.
_SQL_BAI_CHO = (
    "FROM bai b LEFT JOIN nguon n ON n.id = b.nguon_id WHERE b.du_an = %s AND "
    "(b.sac_thai IS NULL OR b.chu_de IS NULL) AND n.loai IS DISTINCT FROM 'kenh_nha' AND "
    "btrim(b.noi_dung || ' ' || COALESCE(b.hashtag, '')) <> ''")


def bl_cho_gan_nhan(ma: str, toi_da: int, bo: list[str] | tuple = ()) -> list[dict]:
    """Bình luận chờ AI, nhiều like trước (như `phan_loai`: hết giờ thì thiếu phần ít like).
    `bo` = khoá "<khoa_bai>\x1f<ma>" bỏ qua. Kèm đầu nội dung + hashtag của BÀI (`bai_noi_dung`,
    `bai_hashtag`, 17/10/2026): ngữ cảnh để model đoán MÓN khách hỏi mua ("xin giá" dưới bài
    hộp quà là hỏi set quà, không phải hỏi túi)."""
    with ket_noi() as c:
        return c.execute(
            "SELECT x.khoa_bai, x.ma, x.noi_dung, x.thich, x.la_tra_loi, "
            "left(p.noi_dung, 300) AS bai_noi_dung, left(p.hashtag, 120) AS bai_hashtag "
            "FROM (SELECT du_an, khoa_bai, ma, noi_dung, thich, la_tra_loi, dang_luc, thay_lan_dau "
            f"{_SQL_BL_CHO} AND NOT ((khoa_bai || chr(31) || ma) = ANY(%s)) "
            "ORDER BY COALESCE(thich, 0) DESC, COALESCE(dang_luc, thay_lan_dau) DESC LIMIT %s) x "
            "LEFT JOIN bai p ON p.du_an = x.du_an AND p.khoa = x.khoa_bai "
            "ORDER BY COALESCE(x.thich, 0) DESC, COALESCE(x.dang_luc, x.thay_lan_dau) DESC",
            (ma, list(bo), int(toi_da))).fetchall()


def ghi_nhan_bl(ma: str, nhan: list[tuple]) -> int:
    """`nhan` = [(khoa_bai, ma, noi_dung đã đọc, sắc thái, chủ đề[, món hỏi mua])]. Chỉ ghi dòng
    CÒN chờ và CÙNG chữ lúc đọc: lượt quét chen giữa hạ dòng thành seeding/spam (xoá nhãn) hay sửa
    nội dung thì không đè; hai tiến trình cùng gán thì dòng chỉ nhận nhãn một lần. `cap_nhat_cuoi`
    để đồng bộ BigQuery lấy lại dòng. Món (`san_pham`, 17/10/2026) NULL khi không phải bình luận
    hỏi mua. -> số dòng đã ghi."""
    n = 0
    if not nhan:
        return 0
    with ket_noi() as c:
        for kb, m, nd, s, cd, *sp in nhan:
            n += c.execute(
                "UPDATE binh_luan SET sac_thai = %s, chu_de = %s, san_pham = %s, "
                "cap_nhat_cuoi = now() "
                "WHERE du_an = %s AND khoa_bai = %s AND ma = %s AND sac_thai IS NULL AND "
                "loai = 'hop_le' AND NOT cua_thuong_hieu AND noi_dung = %s",
                (s, cd, sp[0] if sp else None, ma, kb, m, nd)).rowcount or 0
    return n


def bai_cho_gan_nhan(ma: str, toi_da: int, bo: list[str] | tuple = ()) -> list[dict]:
    """Bài chờ AI gán sắc thái/chủ đề (phân xử hết giờ/"không rõ", bài Báo & Web), mới trước.
    `kieu_trang` (cột của Báo & Web, schema 16/10) đưa loại trang vào prompt."""
    with ket_noi() as c:
        return c.execute(
            "SELECT b.khoa, b.nen_tang, b.tai_khoan, b.tac_gia, b.noi_dung, b.hashtag, "
            f"b.kieu_trang, b.sac_thai, b.chu_de {_SQL_BAI_CHO} "
            "AND NOT (b.khoa = ANY(%s)) ORDER BY b.dang_luc DESC NULLS LAST LIMIT %s",
            (ma, list(bo), int(toi_da))).fetchall()


#: Biểu thức SQL mốc mới của `bai.cap_nhat_cuoi` khi CHỈ đổi nhãn (gán nền, script gán lại).
DOI_MOC_BAI_SQL = (
    "CASE WHEN nen_tang = 'youtube' AND dang_luc >= now() - interval '14 days' AND cap_nhat_cuoi "
    "< (date_trunc('day', now() AT TIME ZONE 'Asia/Ho_Chi_Minh') AT TIME ZONE 'Asia/Ho_Chi_Minh') "
    "THEN cap_nhat_cuoi ELSE now() END")


def ghi_nhan_bai(ma: str, nhan: list[tuple]) -> int:
    """`nhan` = [(khoa, noi_dung đã đọc, sắc thái, chủ đề)] — chỉ điền ô CÒN trống, cùng chữ lúc
    đọc. -> số bài đã ghi. `cap_nhat_cuoi` = mốc đồng bộ BigQuery: dời (`DOI_MOC_BAI_SQL`) TRỪ bài
    YouTube còn trong cửa sổ làm mới số MIỄN PHÍ hằng ngày (`bai_youtube_can_lam_moi`, ≤ 14 ngày)
    mà hôm nay chưa đọc số — dời mốc thì lượt hôm nay bỏ qua bài đó; lượt làm mới (chắc chắn
    trong ngày) tự dời mốc và đồng bộ mang nhãn đi. TikTok làm mới chỉ 10 bài nhiều tương tác
    mỗi lượt (không chắc tới bài nào) nên luôn dời: cùng lắm bài đó lỡ làm mới số MỘT ngày."""
    n = 0
    if not nhan:
        return 0
    with ket_noi() as c:
        for k, nd, s, cd in nhan:
            n += c.execute(
                "UPDATE bai SET sac_thai = COALESCE(sac_thai, %s), chu_de = COALESCE(chu_de, %s), "
                f"cap_nhat_cuoi = {DOI_MOC_BAI_SQL} "
                "WHERE du_an = %s AND khoa = %s AND (sac_thai IS NULL OR chu_de IS NULL) AND "
                "noi_dung = %s", (s, cd, ma, k, nd)).rowcount or 0
    return n


def dem_cho_gan_nhan(ma: str) -> dict:
    """{'bl': n, 'bai': m} còn chờ AI (cả dòng đã thử quá số lần) — trạng thái cho log/lượt."""
    with ket_noi() as c:
        bl = c.execute(f"SELECT count(*) AS n {_SQL_BL_CHO}", (ma,)).fetchone()
        bai = c.execute(f"SELECT count(*) AS n {_SQL_BAI_CHO}", (ma,)).fetchone()
    return {"bl": int(bl["n"]), "bai": int(bai["n"])}
