"""Đồng bộ kho `lang_nghe` (Postgres trên VPS) → BigQuery — đợt 2, chủ dự án chốt 14/10/2026.

Vì sao dashboard đẩy mà không phải Mark: quyết định 0017 của platform — agent nghiệp vụ không
cầm khoá BigQuery. Dashboard là dịch vụ riêng, cầm MỘT tài khoản dịch vụ chỉ có quyền trên
dataset lắng nghe (`BQ_DATASET`, bảng tạo sẵn bằng `deploy/lang-nghe/bigquery.sql` có đủ mô
tả 11 nhãn). Mark không biết BigQuery tồn tại.

Cách đẩy: MERGE theo khoá, dữ liệu đi trong MỘT tham số truy vấn ARRAY<STRUCT> (`@rows`) — không
cần bảng tạm (bảng tạm cũng phải có mô tả theo quy chuẩn), không cần quyền tạo bảng.
  • `du_an`, `nguon`: nhỏ → nạp lại toàn bảng, xoá dòng không còn ở nguồn.
  • `bai` (mốc `cap_nhat_cuoi`), `luot_quet` (mốc max(bat_dau, ket_thuc)), `chi_so_ngay` (mốc
    `ngay`, đọc lại từ mốc − 1 ngày vì số trong ngày còn bị ghi đè): đọc các dòng có mốc trong
    (mốc cũ, CHẶN TRÊN] với chặn trên = mốc lớn nhất lúc bắt đầu lượt, phân trang theo bộ
    (mốc, khoá). Vì sao không chỉ theo mốc: Mark ghi cả lô bài trong MỘT giao dịch nên cả lô
    cùng `cap_nhat_cuoi` (now() của giao dịch) — phân trang "mốc > mốc cuối" sẽ bỏ sót phần lô
    cùng mốc. Dòng bị sửa giữa lúc đồng bộ có mốc > chặn trên → lượt sau lấy. Cận dưới lùi 15
    phút để không mất giao dịch commit muộn hơn mốc của nó.
Mốc (= chặn trên) chỉ dời khi CẢ bảng đẩy xong; lỗi giữa chừng thì ghi `loi`, giữ mốc cũ — lần
sau đẩy lại, MERGE nên không nhân đôi.

Không đẩy `nguoi_xem`, `nhat_ky`, `de_xuat`, `dong_bo_bq`, cột email (`sua_boi`, `them_boi`).
Chạy: sau mỗi lượt quét (hook `sau_cap_nhat` của dashboard) và 6 giờ một lần. Một lượt một lúc.
"""
from __future__ import annotations

import contextlib
import datetime
import os
import re
import threading
import time

#: Số dòng mỗi lần MERGE (tham số truy vấn BigQuery giới hạn kích thước; 500 bài ~ 1 MB).
LO = 500
CHU_KY_GIAY = 6 * 3600
_KHOA = threading.Lock()
_URL = re.compile(r"https?://\S+")

# Kiểu BigQuery của từng cột — PHẢI khớp `deploy/lang-nghe/bigquery.sql` (có bài canh).
BANG: dict[str, dict] = {
    "du_an": {
        "khoa": ["ma"], "kieu": "toan_bo",
        "cot": [("ma", "STRING"), ("ten", "STRING"), ("tu_khoa", "ARRAY<STRING>"),
                ("tu_loai_tru", "ARRAY<STRING>"), ("boi_canh", "STRING"), ("thi_truong", "STRING"),
                ("tran_usd_thang", "NUMERIC"), ("dang_bat", "BOOL"), ("tao_luc", "TIMESTAMP"),
                ("sua_luc", "TIMESTAMP"),
                # Hashtag riêng của dự án (18/10/2026): ALTER … ADD COLUMN hashtag trên BigQuery +
                # schema.sql trên Postgres trước khi bật bản mới (mảng rỗng khi chưa đặt).
                ("hashtag", "ARRAY<STRING>")],
        # Cột thêm SAU khi bảng đã tạo (soát 18/10/2026, như cổng `kho._co_hashtag` của dashboard
        # và Mark): bên nào (Postgres / BigQuery) chưa chạy ALTER thì bỏ cột đó khỏi lượt + cảnh
        # báo, KHÔNG làm hỏng cả bảng (thiếu cột là lỗi cả câu MERGE — du_an không đồng bộ nữa).
        "tuy_chon": ("hashtag",),
    },
    "nguon": {
        "khoa": ["id"], "kieu": "toan_bo",
        "cot": [("id", "INT64"), ("du_an", "STRING"), ("nen_tang", "STRING"),
                ("dinh_danh", "STRING"), ("ten", "STRING"), ("link", "STRING"), ("loai", "STRING"),
                ("nhan", "ARRAY<STRING>"), ("trang_thai", "STRING"), ("chu_ky_ngay", "INT64"),
                ("so_bai_moi_lan", "INT64"), ("them_qua", "STRING"), ("them_luc", "TIMESTAMP"),
                ("quet_cuoi", "TIMESTAMP"), ("loi_cuoi", "STRING"), ("loi_luc", "TIMESTAMP")],
    },
    "luot_quet": {
        "khoa": ["id"], "kieu": "tang_dan",
        "moc": "GREATEST(bat_dau, COALESCE(ket_thuc, bat_dau))",
        "cot": [("id", "INT64"), ("du_an", "STRING"), ("kieu", "STRING"), ("ma_viec", "STRING"),
                ("job_id", "STRING"), ("bat_dau", "TIMESTAMP"), ("ket_thuc", "TIMESTAMP"),
                ("so_nguon", "INT64"), ("so_nguon_loi", "INT64"), ("bai_moi", "INT64"),
                ("bai_cap_nhat", "INT64"), ("chi_phi_usd", "NUMERIC"), ("trang_thai", "STRING"),
                ("loi", "STRING"), ("ghi_chu", "STRING")],
    },
    "bai": {
        "khoa": ["du_an", "khoa"], "kieu": "tang_dan", "moc": "cap_nhat_cuoi",
        "cot": [("du_an", "STRING"), ("khoa", "STRING"), ("nen_tang", "STRING"),
                ("nguon_id", "INT64"), ("kieu_quet", "STRING"), ("link", "STRING"),
                ("tac_gia", "STRING"), ("tai_khoan", "STRING"), ("followers", "INT64"),
                ("dang_luc", "TIMESTAMP"), ("noi_dung", "STRING"), ("hashtag", "STRING"),
                ("khop_tu_khoa", "BOOL"), ("sac_thai", "STRING"), ("chu_de", "STRING"),
                ("ly_do_giu", "STRING"), ("xem", "INT64"), ("thich", "INT64"),
                ("binh_luan", "INT64"), ("chia_se", "INT64"), ("thay_lan_dau", "TIMESTAMP"),
                ("cap_nhat_cuoi", "TIMESTAMP"), ("luot_dau", "INT64"), ("luot_cuoi", "INT64"),
                ("ma_noi_dung", "STRING"),
                # Lắng nghe web (16/10/2026): chỉ bài nen_tang = 'web' có, bài MXH NULL.
                ("kieu_trang", "STRING"), ("muc_nhac", "STRING"), ("la_pr", "BOOL"),
                # Khử trùng Facebook (17/10/2026): id số của bài (ALTER … ADD COLUMN ma_so_fb
                # trên BigQuery + schema.sql trên Postgres trước khi bật).
                ("ma_so_fb", "STRING")],
    },
    "chi_so_ngay": {
        "khoa": ["du_an", "khoa", "ngay"], "kieu": "theo_ngay", "moc": "ngay",
        "cot": [("du_an", "STRING"), ("khoa", "STRING"), ("ngay", "DATE"), ("xem", "INT64"),
                ("thich", "INT64"), ("binh_luan", "INT64"), ("chia_se", "INT64")],
    },
    # Đợt 2b (15/10/2026): bình luận đã cào. tac_gia là tên hiển thị CÔNG KHAI trên nền tảng
    # (không phải email nội bộ) — cần để BI đọc lại bình luận như dashboard.
    "binh_luan": {
        "khoa": ["du_an", "khoa_bai", "ma"], "kieu": "tang_dan", "moc": "cap_nhat_cuoi",
        "cot": [("du_an", "STRING"), ("khoa_bai", "STRING"), ("ma", "STRING"),
                ("nen_tang", "STRING"), ("tac_gia", "STRING"), ("noi_dung", "STRING"),
                ("thich", "INT64"), ("tra_loi", "INT64"), ("la_tra_loi", "BOOL"),
                ("cua_thuong_hieu", "BOOL"), ("dang_luc", "TIMESTAMP"), ("sac_thai", "STRING"),
                ("chu_de", "STRING"), ("luot_id", "INT64"), ("thay_lan_dau", "TIMESTAMP"),
                ("cap_nhat_cuoi", "TIMESTAMP"), ("loai", "STRING"), ("ly_do_loc", "STRING"),
                ("ma_noi_dung", "STRING"), ("link", "STRING"), ("ma_cha", "STRING"),
                # 17/10/2026: món khách hỏi mua (ALTER … ADD COLUMN san_pham trước khi bật).
                ("san_pham", "STRING")],
    },
}
THU_TU = ("du_an", "nguon", "luot_quet", "bai", "chi_so_ngay", "binh_luan")   # cha trước con


def dataset() -> str:
    """`project.dataset` đích; rỗng = chưa bật đồng bộ."""
    return (os.environ.get("BQ_DATASET") or "").strip()


def da_bat() -> bool:
    return bool(dataset())


# ───────────────────────────── SQL ─────────────────────────────
def _cot(bang: str, cot: list | None = None) -> list[tuple[str, str]]:
    """Cột của lượt: `cot` (đã bỏ cột tuỳ chọn còn thiếu — `cot_hieu_luc`) hoặc đủ cột của bảng."""
    return list(cot) if cot is not None else BANG[bang]["cot"]


def sql_toan_bo(bang: str, cot: list | None = None) -> str:
    b = BANG[bang]
    return (f"SELECT {', '.join(c for c, _ in _cot(bang, cot))} FROM {bang} "
            f"ORDER BY {', '.join(b['khoa'])}")


def sql_chan_tren(bang: str) -> str:
    return f"SELECT max({BANG[bang]['moc']}) AS hi FROM {bang}"


def sql_lo(bang: str, co_moc: bool, co_sau: bool, cot: list | None = None) -> str:
    """Một lô của bảng tăng dần, tham số tên: lo, hi, [tu], [sau_moc, sau_<khoá>…].

    `tu` là mốc cũ: bảng `tang_dan` lấy mốc > tu; `theo_ngay` lấy ngày ≥ tu − 1. `sau_*` là
    dòng cuối của lô trước (phân trang theo bộ (mốc, khoá))."""
    b = BANG[bang]
    moc, khoa = b["moc"], b["khoa"]
    dk = [f"{moc} <= %(hi)s"]
    if co_moc:
        # Lùi 15 phút: giao dịch bắt đầu sớm (mốc = now() lúc bắt đầu) mà commit SAU lượt đồng bộ
        # trước có mốc nhỏ hơn mốc đã lưu — không lùi thì mất vĩnh viễn. Đọc lại vài dòng thì
        # MERGE không nhân đôi.
        dk.append(f"{moc} >= %(tu)s::date - 1" if b["kieu"] == "theo_ngay"
                  else f"{moc} > %(tu)s::timestamptz - interval '15 minutes'")
    if co_sau:
        dk.append(f"({moc}, {', '.join(khoa)}) > (%(sau_moc)s, "
                  f"{', '.join('%(sau_' + k + ')s' for k in khoa)})")
    return (f"SELECT {', '.join(c for c, _ in _cot(bang, cot))}, {moc} AS _moc FROM {bang} "
            f"WHERE {' AND '.join(dk)} ORDER BY {moc}, {', '.join(khoa)} LIMIT %(lo)s")


def sql_merge(bang: str, cot: list | None = None) -> str:
    """MERGE BigQuery dùng tham số `@rows` (ARRAY<STRUCT> đúng cột của lượt). Cột không có trong
    lượt (tuỳ chọn còn thiếu) thì MERGE không đụng tới."""
    b = BANG[bang]
    cot = [c for c, _ in _cot(bang, cot)]
    on = " AND ".join(f"T.{k} = S.{k}" for k in b["khoa"])
    cap_nhat = ", ".join(f"{c} = S.{c}" for c in cot if c not in b["khoa"])
    sql = (f"MERGE `{dataset()}.{bang}` T USING (SELECT * FROM UNNEST(@rows)) S ON {on} "
           f"WHEN MATCHED THEN UPDATE SET {cap_nhat}, dong_bo_luc = CURRENT_TIMESTAMP() "
           f"WHEN NOT MATCHED THEN INSERT ({', '.join(cot)}, dong_bo_luc) "
           f"VALUES ({', '.join('S.' + c for c in cot)}, CURRENT_TIMESTAMP())")
    if b["kieu"] == "toan_bo":
        sql += " WHEN NOT MATCHED BY SOURCE THEN DELETE"
    return sql


# ───────────────────────────── giá trị ─────────────────────────────
def chuan_gia_tri(kieu: str, v):
    """Giá trị Postgres -> giá trị đưa vào tham số BigQuery (giữ NULL; mảng NULL -> rỗng)."""
    if v is None:
        return [] if kieu.startswith("ARRAY") else None
    if kieu == "TIMESTAMP":
        if isinstance(v, datetime.datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=datetime.timezone.utc)
            return v.astimezone(datetime.timezone.utc).isoformat()
        return str(v)
    if kieu == "DATE":
        return v.isoformat()[:10] if isinstance(v, (datetime.date, datetime.datetime)) else str(v)
    if kieu == "NUMERIC":
        return str(v)
    if kieu == "INT64":
        return int(v)
    if kieu == "BOOL":
        return bool(v)
    if kieu.startswith("ARRAY"):
        return [str(x) for x in v if x is not None]
    return str(v)


def dong_bq(bang: str, rows: list[dict], cot: list | None = None) -> list[dict]:
    return [{c: chuan_gia_tri(k, r.get(c)) for c, k in _cot(bang, cot)} for r in rows]


def _tham_so_bq(bang: str, rows: list[dict]):
    """Dựng tham số `@rows` cho thư viện google-cloud-bigquery. Import muộn: chỉ máy chủ
    dashboard có thư viện; bộ thử thay hàm này. Cột theo dòng đầu (lượt đã bỏ cột tuỳ chọn còn
    thiếu thì dòng không có khoá đó)."""
    from google.cloud import bigquery as bq
    cot = [x for x in BANG[bang]["cot"] if not rows or x[0] in rows[0]]
    kieu_dong = bq.StructQueryParameterType(*[
        bq.ArrayQueryParameterType("STRING", name=c) if k.startswith("ARRAY")
        else bq.ScalarQueryParameterType(k, name=c) for c, k in cot])
    gia_tri = [bq.StructQueryParameter(None, *[
        bq.ArrayQueryParameter(c, "STRING", r[c]) if k.startswith("ARRAY")
        else bq.ScalarQueryParameter(c, k, r[c]) for c, k in cot]) for r in rows]
    return [bq.ArrayQueryParameter("rows", kieu_dong, gia_tri)]


class _BigQuery:
    """Bọc mỏng google-cloud-bigquery: `chay(sql, tham_so)`; bộ thử dùng bản giả cùng giao diện.
    Khoá lấy theo GOOGLE_APPLICATION_CREDENTIALS (file của tài khoản dịch vụ, quyền 600)."""

    def __init__(self):
        from google.cloud import bigquery as bq
        self._bq = bq
        self._client = bq.Client(location=os.environ.get("BQ_LOCATION") or "asia-southeast1")

    def chay(self, sql: str, tham_so) -> int:
        job = self._client.query(sql, job_config=self._bq.QueryJobConfig(query_parameters=tham_so))
        job.result(timeout=300)
        return int(job.num_dml_affected_rows or 0)

    def cot(self, bang: str) -> set[str]:
        """Tên cột hiện có của bảng đích (INFORMATION_SCHEMA của dataset — chỉ đọc)."""
        job = self._client.query(
            f"SELECT column_name FROM `{dataset()}.INFORMATION_SCHEMA.COLUMNS` "
            "WHERE table_name = @bang",
            job_config=self._bq.QueryJobConfig(query_parameters=[
                self._bq.ScalarQueryParameter("bang", "STRING", bang)]))
        return {r["column_name"] for r in job.result(timeout=60)}


# ───────────────────────────── kho ─────────────────────────────
@contextlib.contextmanager
def ket_noi_kho():
    """Kết nối Postgres của dashboard (role `lang_nghe_web`, peer). Không in DSN khi lỗi."""
    import psycopg
    from psycopg.rows import dict_row
    dsn = (os.environ.get("LANG_NGHE_WEB_DSN") or "").strip() or "dbname=lang_nghe"
    try:
        conn = psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row)
    except psycopg.Error as e:
        raise RuntimeError(f"không nối được kho lắng nghe ({type(e).__name__})") from None
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _doc_moc(ket_noi, bang: str):
    with ket_noi() as c:
        r = c.execute("SELECT moc FROM dong_bo_bq WHERE bang = %s", (bang,)).fetchone()
    return r["moc"] if r else None


def _ghi_moc(ket_noi, bang: str, moc, so_dong: int, loi: str | None) -> None:
    """Ghi kết quả lượt; `moc` None = giữ mốc cũ (lỗi, hoặc bảng nạp lại toàn bộ)."""
    with ket_noi() as c:
        c.execute(
            "INSERT INTO dong_bo_bq (bang, moc, lan_cuoi, so_dong, loi) "
            "VALUES (%s, %s, now(), %s, %s) ON CONFLICT (bang) DO UPDATE SET "
            "moc = COALESCE(EXCLUDED.moc, dong_bo_bq.moc), lan_cuoi = now(), "
            "so_dong = EXCLUDED.so_dong, loi = EXCLUDED.loi",
            (bang, moc, so_dong, (loi or None) and str(loi)[:500]))


def _doc_tang_dan(bang: str, ket_noi, moc_cu, cot: list | None = None):
    """Sinh từng lô dòng của bảng tăng dần trong (mốc cũ, chặn trên]. -> (lô…, chặn trên)."""
    b = BANG[bang]
    with ket_noi() as c:
        hi = c.execute(sql_chan_tren(bang)).fetchone()["hi"]
    if hi is None:
        return [], None
    lo_list, sau = [], None
    while True:
        ts = {"lo": LO, "hi": hi}
        if moc_cu is not None:
            ts["tu"] = moc_cu
        if sau is not None:
            ts["sau_moc"] = sau["_moc"]
            ts.update({f"sau_{k}": sau[k] for k in b["khoa"]})
        with ket_noi() as c:
            rows = c.execute(sql_lo(bang, moc_cu is not None, sau is not None, cot),
                             ts).fetchall()
        if rows:
            lo_list.append(rows)
            sau = rows[-1]
        if len(rows) < LO:
            return lo_list, hi


def cot_hieu_luc(bang: str, ket_noi, bq) -> tuple[list[tuple[str, str]], str]:
    """(cột của lượt, cảnh báo). Cột tuỳ chọn (`tuy_chon`) chưa có ở Postgres (schema.sql chưa
    chạy) hoặc BigQuery (ALTER … ADD COLUMN chưa chạy) thì bỏ khỏi lượt. BigQuery giả / cũ không
    có `cot` → coi như có đủ; không đọc được INFORMATION_SCHEMA thì cũng vậy (MERGE như trước) kèm
    cảnh báo."""
    b = BANG[bang]
    tc = tuple(b.get("tuy_chon") or ())
    if not tc:
        return b["cot"], ""
    with ket_noi() as c:
        co_pg = {r["column_name"] for r in c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = "
            "current_schema() AND table_name = %s AND column_name = ANY(%s)",
            (bang, list(tc))).fetchall()}
    ghi = []
    ham = getattr(bq, "cot", None)
    co_bq = set(tc)
    if ham is not None:
        try:
            co_bq = set(ham(bang))
        except Exception as e:  # noqa: BLE001 — không kiểm được thì MERGE như trước
            ghi.append(f"không đọc được cột BigQuery ({type(e).__name__}) — MERGE đủ cột")
    bo = [c for c in tc if c not in co_pg or c not in co_bq]
    for c in bo:
        o = [x for x, co in (("Postgres", c in co_pg), ("BigQuery", c in co_bq)) if not co]
        ghi.append(f"bỏ cột {c}: {' và '.join(o)} chưa có cột (chạy "
                   + " / ".join("schema.sql" if x == "Postgres" else "ALTER trong bigquery.sql"
                                for x in o) + ")")
    return [x for x in b["cot"] if x[0] not in bo], "; ".join(ghi)


def dong_bo_bang(bang: str, ket_noi, bq, tham_so=_tham_so_bq) -> dict:
    """Đẩy một bảng. -> {"bang", "so_dong", "loi"} (+ "canh_bao" khi bỏ cột tuỳ chọn còn thiếu —
    cảnh báo ghi vào `dong_bo_bq.loi` để trang "Kết nối BigQuery" thấy, mốc vẫn dời)."""
    b = BANG[bang]
    tong, moc_moi, loi, canh = 0, None, None, ""
    try:
        cot, canh = cot_hieu_luc(bang, ket_noi, bq)
        if b["kieu"] == "toan_bo":
            with ket_noi() as c:
                rows = c.execute(sql_toan_bo(bang, cot)).fetchall()
            bq.chay(sql_merge(bang, cot), tham_so(bang, dong_bq(bang, rows, cot)))
            tong = len(rows)
        else:
            cac_lo, hi = _doc_tang_dan(bang, ket_noi, _doc_moc(ket_noi, bang), cot)
            for rows in cac_lo:
                bq.chay(sql_merge(bang, cot), tham_so(bang, dong_bq(bang, rows, cot)))
                tong += len(rows)
            moc_moi = hi
    except Exception as e:  # noqa: BLE001 — một bảng hỏng không chặn bảng khác
        # Lỗi Google hay kèm URL job/project: bỏ URL, cắt ngắn (review bảo mật 14/10).
        gon = _URL.sub("<url>", str(e))[:200]
        loi = f"{type(e).__name__}: {gon}"
        moc_moi = None
    if canh:
        print(f"[dong_bo_bq] {bang}: {canh}", flush=True)
    _ghi_moc(ket_noi, bang, moc_moi, tong, loi or (f"cảnh báo: {canh}" if canh else None))
    return {"bang": bang, "so_dong": tong, "loi": loi, **({"canh_bao": canh} if canh else {})}


def chay(ket_noi=ket_noi_kho, bq=None, tham_so=_tham_so_bq) -> dict:
    """Đẩy mọi bảng theo `THU_TU`. Lượt khác đang chạy thì bỏ qua (không xếp hàng)."""
    if not da_bat():
        return {"bo_qua": "chưa bật (thiếu BQ_DATASET)"}
    if not _KHOA.acquire(blocking=False):
        return {"bo_qua": "đang có lượt đồng bộ khác"}
    try:
        bq = bq or _BigQuery()
        t0 = time.monotonic()
        kq = [dong_bo_bang(b, ket_noi, bq, tham_so) for b in THU_TU]
        return {"bang": kq, "giay": round(time.monotonic() - t0, 1)}
    finally:
        _KHOA.release()


def trang_thai(ket_noi=ket_noi_kho) -> dict:
    """Cho trang "Kết nối BigQuery" của dashboard: dataset, mốc, lần cuối, số dòng, lỗi."""
    with ket_noi() as c:
        rows = c.execute("SELECT bang, moc, lan_cuoi, so_dong, loi FROM dong_bo_bq").fetchall()
    theo = {r["bang"]: r for r in rows}
    return {"dataset": dataset(), "da_bat": da_bat(),
            "bang": [dict(theo.get(b) or {"bang": b}) for b in THU_TU]}


def cai_vao(app) -> None:
    """Gắn vào dashboard: chạy sau mỗi `cap-nhat` (hook `app.state.sau_cap_nhat`) và mỗi
    `CHU_KY_GIAY` giây trong luồng nền riêng. Chưa bật (thiếu BQ_DATASET) thì không làm gì."""
    if not da_bat():
        return
    hook = getattr(app.state, "sau_cap_nhat", None)
    if isinstance(hook, list):
        hook.append(lambda du_an=None, luot=None: chay())

    def vong():
        while True:
            try:
                chay()
            except Exception as e:  # noqa: BLE001
                print(f"[dong_bo_bq] lỗi: {type(e).__name__}", flush=True)
            time.sleep(CHU_KY_GIAY)
    threading.Thread(target=vong, name="dong_bo_bq", daemon=True).start()
