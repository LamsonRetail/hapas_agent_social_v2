"""Danh bạ Lark cho trang Người xem: email -> tên, chức danh, phòng ban, trạng thái tài khoản.

Chủ dự án (17/10/2026): "thêm mục title của họ trong công ty nữa để dễ dàng quản lý và biết
email được thêm vào có active thật không". Dùng CHÍNH ứng dụng Lark của dashboard
(DASH_LARK_APP_ID/SECRET) với token TỔ CHỨC (tenant_access_token) — không cần ai đăng nhập.

Ba bước, mỗi lô ≤ 50 email (giới hạn của Lark):
  1. email -> open_id: POST /contact/v3/users/batch_get_id (include_resigned) —
     scope `contact:user.id:readonly`.
  2. open_id -> người: GET /contact/v3/users/batch — scope `contact:user.base:readonly` (tên,
     trạng thái); trường `job_title` cần `contact:user.employee:readonly`, `department_ids` cần
     `contact:user.department:readonly` (thiếu quyền trường thì Lark trả THIẾU trường, không lỗi).
  3. mã phòng ban -> tên: GET /contact/v3/departments/batch — scope
     `contact:department.base:readonly`. Bước này hỏng thì chỉ thiếu tên phòng ban.
Ngoài scope, "phạm vi dữ liệu danh bạ" của app (Lark Developer -> Permissions -> contacts range)
phải gồm toàn công ty: người ngoài phạm vi bị Lark báo như KHÔNG CÓ trong danh bạ.

Không bao giờ chặn trang: bên gọi bọc `asyncio.wait_for`; mỗi lần gọi HTTP có timeout. Lỗi ->
`LoiDanhBa(loai, buoc)` với `loai` = "thieu_quyen" (app chưa được cấp scope) hoặc "loi"; câu lỗi
KHÔNG chứa token hay secret.
"""
from __future__ import annotations

import time

from dashboard.dang_nhap import CauHinh

DUONG_TOKEN_TO_CHUC = "/auth/v3/tenant_access_token/internal"
DUONG_EMAIL_RA_ID = "/contact/v3/users/batch_get_id"
DUONG_NGUOI = "/contact/v3/users/batch"
DUONG_PHONG_BAN = "/contact/v3/departments/batch"
LO = 50                     # Lark nhận tối đa 50 email / 50 open_id / 50 phòng ban mỗi lần
GIAY_MOI_LAN_GOI = 8.0

#: Mã lỗi Lark nghĩa là "app chưa có quyền" (scope chưa bật/chưa duyệt, ngoài phạm vi dữ liệu).
MA_THIEU_QUYEN = {99991672, 99991679, 40004, 41050}

#: Scope cần cho từng bước — hiện trong ⓘ khi đọc danh bạ hỏng vì thiếu quyền.
SCOPE_BUOC = {
    "token": "App ID/App Secret của dashboard",
    "email": "contact:user.id:readonly",
    "nguoi": "contact:user.base:readonly (+ contact:user.employee:readonly cho chức danh, "
             "contact:user.department:readonly cho phòng ban)",
}

#: Trạng thái tài khoản Lark (cột `nguoi_xem.trang_thai_lark`).
TRANG_THAI = {
    "hoat_dong": "Đang hoạt động",
    "chua_kich_hoat": "Chưa kích hoạt",
    "tam_khoa": "Tạm khoá",
    "nghi_viec": "Đã nghỉ việc",
    "khong_co": "Không có trong danh bạ",
}


class LoiDanhBa(Exception):
    def __init__(self, loai: str, buoc: str, chi_tiet: str = ""):
        super().__init__(f"{loai} ở bước {buoc}: {chi_tiet}"[:300])
        self.loai, self.buoc = loai, buoc


def trang_thai(st: dict | None) -> str:
    """`status` của Lark -> mã trạng thái. Nghỉ việc/rời tổ chức thắng tạm khoá thắng chưa kích
    hoạt. Không có `status` (Lark không trả) thì coi là đang hoạt động — người đã tìm thấy."""
    st = st if isinstance(st, dict) else {}
    if st.get("is_resigned") or st.get("is_exited"):
        return "nghi_viec"
    if st.get("is_frozen"):
        return "tam_khoa"
    if st.get("is_activated") is False or st.get("is_unjoin"):
        return "chua_kich_hoat"
    return "hoat_dong"


def _lo(ds: list, n: int = LO):
    for i in range(0, len(ds), n):
        yield ds[i:i + n]


class DanhBaLark:
    """Đọc danh bạ bằng token tổ chức. `transport` để bộ thử giả HTTP (httpx.MockTransport)."""

    def __init__(self, cfg: CauHinh, transport=None, giay: float = GIAY_MOI_LAN_GOI):
        self.cfg = cfg
        self.transport = transport
        self.giay = giay
        self._token: tuple[str, float] | None = None     # (token, hết hạn theo monotonic)

    async def _goi(self, kh, buoc: str, phuong_thuc: str, duong: str, **kw) -> dict:
        import httpx
        try:
            r = await kh.request(phuong_thuc, self.cfg.open_base + duong, **kw)
            d = r.json() if r.content else {}
        except (httpx.HTTPError, ValueError) as e:
            raise LoiDanhBa("loi", buoc, type(e).__name__) from None
        ma = d.get("code") if isinstance(d, dict) else None
        if r.status_code == 200 and ma == 0:
            return d
        loai = "thieu_quyen" if (ma in MA_THIEU_QUYEN or r.status_code == 403) else "loi"
        raise LoiDanhBa(loai, buoc, f"HTTP {r.status_code}, mã {ma}")

    async def _token_to_chuc(self, kh) -> str:
        if self._token and self._token[1] > time.monotonic() + 60:
            return self._token[0]
        d = await self._goi(kh, "token", "POST", DUONG_TOKEN_TO_CHUC,
                            json={"app_id": self.cfg.app_id, "app_secret": self.cfg.app_secret})
        tk = str(d.get("tenant_access_token") or "")
        if not tk:
            raise LoiDanhBa("loi", "token", "Lark không trả token")
        het = d.get("expire")
        self._token = (tk, time.monotonic() + (int(het) if isinstance(het, int) else 3600))
        return tk

    async def tra_cuu(self, emails: list[str]) -> dict[str, dict]:
        """emails -> {email: {"trang_thai", "ten", "chuc_danh", "phong_ban"}}; email nào cũng có
        mặt trong kết quả (không tìm thấy -> trang_thai "khong_co", các trường khác None)."""
        import httpx
        emails = sorted({str(e).strip().lower() for e in emails if e and "@" in str(e)})
        if not emails:
            return {}
        async with httpx.AsyncClient(timeout=self.giay, transport=self.transport) as kh:
            tk = await self._token_to_chuc(kh)
            h = {"Authorization": f"Bearer {tk}"}
            # 1. email -> open_id (+ trạng thái nếu Lark kèm theo)
            id_cua: dict[str, str] = {}
            st_cua: dict[str, dict] = {}
            for lo in _lo(emails):
                d = await self._goi(kh, "email", "POST", DUONG_EMAIL_RA_ID, headers=h,
                                    params={"user_id_type": "open_id"},
                                    json={"emails": lo, "include_resigned": True})
                for u in (d.get("data") or {}).get("user_list") or []:
                    e = str(u.get("email") or "").strip().lower()
                    if e in lo and u.get("user_id"):
                        id_cua[e] = str(u["user_id"])
                        if isinstance(u.get("status"), dict):
                            st_cua[e] = u["status"]
            # 2. open_id -> người
            nguoi: dict[str, dict] = {}
            ids = sorted(set(id_cua.values()))
            for lo in _lo(ids):
                d = await self._goi(kh, "nguoi", "GET", DUONG_NGUOI, headers=h,
                                    params=[("user_id_type", "open_id"),
                                            ("department_id_type", "open_department_id"),
                                            *[("user_ids", x) for x in lo]])
                for u in (d.get("data") or {}).get("items") or []:
                    if u.get("open_id"):
                        nguoi[str(u["open_id"])] = u
            # 3. phòng ban -> tên (hỏng thì bỏ qua, chỉ thiếu tên phòng ban)
            ten_pb: dict[str, str] = {}
            pbs = sorted({str(p) for u in nguoi.values() for p in (u.get("department_ids") or [])
                          if p and str(p) != "0"})
            try:
                for lo in _lo(pbs):
                    d = await self._goi(kh, "phong_ban", "GET", DUONG_PHONG_BAN, headers=h,
                                        params=[("department_id_type", "open_department_id"),
                                                *[("department_ids", x) for x in lo]])
                    for p in (d.get("data") or {}).get("items") or []:
                        ma = p.get("open_department_id") or p.get("department_id")
                        if ma and p.get("name"):
                            ten_pb[str(ma)] = str(p["name"])
            except LoiDanhBa:
                ten_pb = {}
        kq: dict[str, dict] = {}
        for e in emails:
            oid = id_cua.get(e)
            if not oid:
                kq[e] = {"trang_thai": "khong_co", "ten": None, "chuc_danh": None,
                         "phong_ban": None}
                continue
            u = nguoi.get(oid) or {}
            pb = [ten_pb[str(p)] for p in (u.get("department_ids") or []) if str(p) in ten_pb]
            kq[e] = {"trang_thai": trang_thai(u.get("status") or st_cua.get(e)),
                     "ten": (str(u.get("name") or "").strip() or None),
                     "chuc_danh": (str(u.get("job_title") or "").strip()[:200] or None),
                     "phong_ban": (" · ".join(pb)[:300] or None)}
        return kq
