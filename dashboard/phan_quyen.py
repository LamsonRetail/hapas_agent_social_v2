"""Phân quyền theo BÊN (đơn vị) của dashboard (chủ dự án chốt 19/10/2026). Thuần Python, không SQL.

Mô hình:
  • Bên (`don_vi`: hapas, matemade…): mỗi dự án thuộc đúng MỘT bên (`du_an.don_vi`).
  • Quản trị viên (`nguoi_xem.la_quan_tri`): toàn hệ thống — mọi bên, mọi dự án, tạo bên, thêm/xoá/đổi
    bất kỳ ai (cả quản trị viên khác), trang BigQuery. Luôn còn ít nhất một quản trị viên.
  • Quyền theo bên (bảng `quyen`, một người nhiều bên): `quan_ly` sửa dự án/nguồn/ngân sách/lịch/duyệt
    đề xuất CỦA BÊN ĐÓ và thêm/xoá người "Chỉ xem" của bên đó; `xem` chỉ đọc dự án của bên đó.
  • Không cờ quản trị và không dòng `quyen` nào = không đăng nhập được (như chưa có tên).

Vì sao tách module: cùng một luật dùng ở BA chỗ — `kho.py` kiểm lại TRONG giao dịch (sau khi khoá
bảng, đọc quyền người làm từ DB chứ không tin tầng app), `app.py` lọc trang/API, và kho giả của bộ
thử. Viết một lần ở đây để ba chỗ không lệch nhau.

`q` (quyền của một người) = {"la_quan_tri": bool, "ben": {mã bên: "xem" | "quan_ly"}}; None khi
email không có trong `nguoi_xem`. Người làm là lệnh quản trị trên máy chủ (`quan_tri.py`) thì truyền
`HE_THONG` — qua mọi luật trừ luật "còn ít nhất một quản trị viên".
"""
from __future__ import annotations

VAI_TRO = {"xem": "Chỉ xem", "quan_ly": "Quản lý"}
HE_THONG = {"he_thong": True, "la_quan_tri": True, "ben": {}}


class LoiQuyen(ValueError):
    """Thao tác vượt quyền hoặc phá luật người xem; câu hiển thị được cho người dùng."""


def chuan(q: dict | None) -> dict | None:
    """Dòng kho -> dạng chuẩn (ben luôn là dict, vai trò lạ bị bỏ)."""
    if q is None:
        return None
    ben = q.get("ben") or {}
    return {"la_quan_tri": bool(q.get("la_quan_tri")),
            "ben": {str(k): v for k, v in dict(ben).items() if v in VAI_TRO}}


def co_quyen(q: dict | None) -> bool:
    """Được đăng nhập: quản trị viên hoặc có ít nhất một bên."""
    return bool(q) and (bool(q.get("la_quan_tri")) or bool(q.get("ben")))


def la_quan_tri(q: dict | None) -> bool:
    return bool(q) and bool(q.get("la_quan_tri"))


def vai_chung(q: dict | None) -> str | None:
    """Vai trò GỘP (bản cũ `nguoi_xem.vai_tro`, Mark bản cũ còn đọc): quan_ly khi là quản trị viên
    hoặc quản lý ít nhất một bên; xem khi chỉ xem; None khi không có quyền."""
    if not co_quyen(q):
        return None
    return "quan_ly" if la_quan_tri(q) or "quan_ly" in q["ben"].values() else "xem"


def doc_duoc(q: dict | None, du_an: dict | None) -> bool:
    if not du_an or not co_quyen(q):
        return False
    return la_quan_tri(q) or du_an.get("don_vi") in q["ben"]


def sua_duoc(q: dict | None, du_an: dict | None) -> bool:
    if not du_an or not co_quyen(q):
        return False
    return la_quan_tri(q) or q["ben"].get(du_an.get("don_vi")) == "quan_ly"


def loc_du_an(q: dict | None, ds: list[dict]) -> list[dict]:
    return [d for d in ds if doc_duoc(q, d)]


def ben_quan_ly(q: dict | None, tat_ca: list[str] | None = None) -> list[str]:
    """Bên người này quản lý được (quản trị viên: mọi bên trong `tat_ca`)."""
    if not co_quyen(q):
        return []
    if la_quan_tri(q):
        return list(tat_ca or [])
    return sorted(b for b, v in q["ben"].items() if v == "quan_ly")


def pham_vi(q: dict | None, ds: list[dict]) -> dict:
    """Mã dự án + mã bên người này ĐỌC / SỬA được trong danh sách dự án `ds`.
    -> {"doc": set, "sua": set, "ben_doc": set | None, "ben_sua": set | None} (None = mọi bên)."""
    qt = la_quan_tri(q)
    return {"doc": {d["ma"] for d in ds if doc_duoc(q, d)},
            "sua": {d["ma"] for d in ds if sua_duoc(q, d)},
            "ben_doc": None if qt else set((q or {}).get("ben") or {}),
            "ben_sua": None if qt else set(ben_quan_ly(q))}


def nhan_vai(q: dict | None, ten_ben: dict[str, str] | None = None) -> str:
    """Chữ ngắn ở đầu trang: "Quản trị viên" hoặc "HAPAS: Quản lý · MATEMADE: Chỉ xem"."""
    if la_quan_tri(q):
        return "Quản trị viên"
    ten_ben = ten_ben or {}
    return " · ".join(f"{ten_ben.get(b, b.upper())}: {VAI_TRO[v]}"
                      for b, v in sorted((q or {}).get("ben", {}).items())) or "—"


# ───────────────────────────── luật sửa người xem ─────────────────────────────
def _la_he_thong(lam: dict) -> bool:
    return bool(lam.get("he_thong"))


def kiem_luu_quyen(lam: dict, email_lam: str, dich: dict | None, email: str, don_vi: str,
                   vai_tro: str) -> None:
    """Thêm / đổi vai trò của `email` ở bên `don_vi`. `lam` = quyền người làm (đọc trong giao dịch),
    `dich` = quyền hiện tại của người được sửa (None: chưa có tên). Ném LoiQuyen."""
    if vai_tro not in VAI_TRO:
        raise LoiQuyen("Vai trò phải là Chỉ xem hoặc Quản lý.")
    if _la_he_thong(lam) or la_quan_tri(lam):
        return
    if (lam.get("ben") or {}).get(don_vi) != "quan_ly":
        raise LoiQuyen("Chỉ quản trị viên hoặc quản lý của bên này mới thêm được người vào bên.")
    if vai_tro != "xem":
        raise LoiQuyen("Quản lý của bên chỉ thêm được người Chỉ xem — cấp quyền Quản lý do quản "
                       "trị viên làm.")
    if email == email_lam:
        raise LoiQuyen("Không tự đổi vai trò của chính mình — nhờ quản trị viên.")
    if la_quan_tri(dich):
        raise LoiQuyen("Không sửa được quyền của quản trị viên — nhờ quản trị viên khác.")
    if (dich or {}).get("ben", {}).get(don_vi) == "quan_ly":
        raise LoiQuyen("Người này đang là Quản lý của bên — chỉ quản trị viên đổi được.")


def kiem_xoa_quyen(lam: dict, email_lam: str, dich: dict | None, email: str,
                   don_vi: str) -> None:
    """Bỏ quyền của `email` ở MỘT bên (quyền ở bên khác giữ nguyên)."""
    # Quyền người làm xét TRƯỚC (soát 19/10/2026): xét người bị bỏ trước thì quản lý bên A dò được
    # ai có quyền ở bên B qua khác biệt câu báo lỗi.
    he_thong = _la_he_thong(lam) or la_quan_tri(lam)
    if not he_thong and (lam.get("ben") or {}).get(don_vi) != "quan_ly":
        raise LoiQuyen("Chỉ quản trị viên hoặc quản lý của bên này mới bỏ được người khỏi bên.")
    if not dich or don_vi not in dich.get("ben", {}):
        raise LoiQuyen("Người này không có quyền ở bên này.")
    if he_thong:
        return
    if email == email_lam:
        raise LoiQuyen("Không tự bỏ quyền của chính mình — nhờ quản trị viên.")
    if la_quan_tri(dich):
        raise LoiQuyen("Không sửa được quyền của quản trị viên — nhờ quản trị viên khác.")
    if dich["ben"][don_vi] != "xem":
        raise LoiQuyen("Người này là Quản lý của bên — chỉ quản trị viên bỏ được.")


def kiem_dat_quan_tri(lam: dict, dich: dict | None, bat: bool, so_quan_tri_khac: int) -> None:
    """Bật / tắt cờ quản trị viên. Chỉ quản trị viên (hoặc lệnh máy chủ); không tắt người cuối."""
    if not (_la_he_thong(lam) or la_quan_tri(lam)):
        raise LoiQuyen("Chỉ quản trị viên mới cấp hoặc bỏ quyền quản trị viên.")
    if not bat and la_quan_tri(dich) and so_quan_tri_khac == 0:
        raise LoiQuyen("Không bỏ quyền quản trị viên cuối cùng — thêm quản trị viên khác trước.")


def kiem_xoa_nguoi(lam: dict, dich: dict | None, so_quan_tri_khac: int) -> None:
    """Xoá hẳn một người (mọi bên). Chỉ quản trị viên; không xoá quản trị viên cuối."""
    if not (_la_he_thong(lam) or la_quan_tri(lam)):
        raise LoiQuyen("Chỉ quản trị viên mới xoá hẳn một người — quản lý của bên bỏ người "
                       "khỏi bên của mình.")
    if dich is None:
        raise LoiQuyen("Không còn người xem này.")
    if la_quan_tri(dich) and so_quan_tri_khac == 0:
        raise LoiQuyen("Không xoá được quản trị viên cuối cùng — thêm quản trị viên khác trước.")


def kiem_tao_ben(lam: dict) -> None:
    if not (_la_he_thong(lam) or la_quan_tri(lam)):
        raise LoiQuyen("Chỉ quản trị viên mới tạo được bên.")
