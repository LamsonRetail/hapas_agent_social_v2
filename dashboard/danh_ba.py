"""Danh bạ Lark cho trang Người xem: email -> tên, chức danh, phòng ban, trạng thái tài khoản.

Chủ dự án (17/10/2026): "thêm mục title của họ trong công ty nữa để dễ dàng quản lý và biết
email được thêm vào có active thật không". Dùng CHÍNH ứng dụng Lark của dashboard
(DASH_LARK_APP_ID/SECRET) với token TỔ CHỨC (tenant_access_token) — không cần ai đăng nhập.

Các bước, mỗi lô ≤ 50 (giới hạn của Lark):
  0. Người đã đăng nhập dashboard: dùng thẳng `nguoi_xem.lark_open_id` (ghi lúc đăng nhập OAuth)
     -> bước 2. Đăng nhập và token tổ chức dùng CÙNG một app (DASH_LARK_APP_ID) nên open_id —
     vốn riêng cho từng app — dùng lại được; đổi app thì phải dùng union_id (đã lưu sẵn).
  1. email -> open_id: POST /contact/v3/users/batch_get_id (include_resigned) —
     scope `contact:user.id:readonly`. LƯU Ý (tài liệu Lark, đối chiếu 17/10/2026): `emails`
     CHỈ khớp trường `email` (email người dùng), "不支持企业邮箱" — KHÔNG khớp `enterprise_email`.
     Email công ty @hapas.vn của người dùng là enterprise_email (lúc đăng nhập ta ưu tiên trường
     này) thì bước này trả rỗng -> trước đây bị báo nhầm "khong_co".
  1b. Email còn lại (chưa đăng nhập, bước 1 không khớp): dò cả danh bạ — GET
     /contact/v3/departments/0/children (fetch_child) + GET /contact/v3/users/find_by_department
     cho gốc và từng phòng ban — khớp `enterprise_email` hoặc `email`. Có trần số lần gọi; hỏng
     (thiếu quyền, quá trần) thì bỏ qua, email đó giữ "khong_co". Cần scope đọc người theo phòng
     ban (contact:contact.base:readonly hoặc tương đương) và `contact:user.employee:readonly`
     để Lark trả `enterprise_email`. Tra theo số điện thoại (`mobiles`) nằm ngoài phạm vi:
     dashboard không giữ số điện thoại.
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
DUONG_PHONG_BAN_CON = "/contact/v3/departments/0/children"
DUONG_NGUOI_THEO_PB = "/contact/v3/users/find_by_department"
#: Trần số lần gọi Lark của một lượt dò cả danh bạ (bước 1b) — công ty vài trăm người dư sức.
QUET_TOI_DA = 80
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

    async def _duyet(self, kh, h: dict):
        """Đi qua danh bạ: GET departments/0/children (fetch_child) rồi find_by_department cho gốc
        và từng phòng ban. Sinh (tên phòng ban | "", người Lark). Trần QUET_TOI_DA lần gọi mỗi
        lượt — quá thì dừng với phần đã có. Lỗi Lark -> LoiDanhBa (bên gọi quyết bỏ qua hay báo)."""
        so_goi = 0

        async def trang(buoc: str, duong: str, params: list) -> list[dict]:
            nonlocal so_goi
            ra: list[dict] = []
            tk = ""
            while so_goi < QUET_TOI_DA:
                so_goi += 1
                d = await self._goi(kh, buoc, "GET", duong, headers=h,
                                    params=[*params, ("page_size", "50"),
                                            *([("page_token", tk)] if tk else [])])
                dl = d.get("data") or {}
                ra += [x for x in (dl.get("items") or []) if isinstance(x, dict)]
                tk = str(dl.get("page_token") or "")
                if not dl.get("has_more") or not tk:
                    break
            return ra

        con = await trang("quet_phong_ban", DUONG_PHONG_BAN_CON,
                          [("department_id_type", "open_department_id"), ("fetch_child", "true")])
        ten_pb = {str(p.get("open_department_id") or ""): str(p.get("name") or "") for p in con}
        pbs = ["0", *(str(p.get("open_department_id") or "") for p in con)]
        for pb in dict.fromkeys(x for x in pbs if x):
            if so_goi >= QUET_TOI_DA:
                break
            for u in await trang("quet_nguoi", DUONG_NGUOI_THEO_PB,
                                 [("department_id", pb), ("user_id_type", "open_id"),
                                  ("department_id_type", "open_department_id")]):
                yield ten_pb.get(pb, ""), u

    async def _quet_ca_danh_ba(self, kh, h: dict, can: set[str]) -> dict[str, dict]:
        """Bước 1b: dò mọi phòng ban, trả {email cần tìm: người Lark} khớp `enterprise_email`
        hoặc `email`. Dừng sớm khi đã tìm đủ; quá QUET_TOI_DA lần gọi thì dừng với phần đã có."""
        tim: dict[str, dict] = {}
        async for _, u in self._duyet(kh, h):
            for k in ("enterprise_email", "email"):
                e = str(u.get(k) or "").strip().lower()
                if e in can and u.get("open_id"):
                    tim.setdefault(e, u)
            if len(tim) >= len(can):
                break
        return tim

    async def cac_nguoi(self) -> list[dict]:
        """Cả danh bạ cho ô "Thêm người" (tìm theo TÊN, 21/10/2026): [{"ten", "email",
        "phong_ban", "trang_thai"}] — người có email (email công ty `enterprise_email` trước),
        đang hoạt động hoặc chưa kích hoạt. Cùng đường gọi + scope với bước 1b (Lark không có API
        tìm người theo tên bằng token tổ chức — /search/v1/user cần token người dùng). Không
        chức danh (chủ dự án bỏ 18/10/2026). Lỗi -> LoiDanhBa."""
        import httpx
        ra: dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=self.giay, transport=self.transport) as kh:
            h = {"Authorization": f"Bearer {await self._token_to_chuc(kh)}"}
            async for pb, u in self._duyet(kh, h):
                e = next((str(u.get(k) or "").strip().lower() for k in ("enterprise_email", "email")
                          if "@" in str(u.get(k) or "")), "")
                tt = trang_thai(u.get("status"))
                if not e or tt in ("nghi_viec", "tam_khoa"):
                    continue
                x = ra.setdefault(e, {"ten": str(u.get("name") or "").strip()[:200] or e,
                                      "email": e, "phong_ban": [], "trang_thai": tt})
                if pb and pb not in x["phong_ban"]:
                    x["phong_ban"].append(pb)
        return [{**x, "phong_ban": " · ".join(x["phong_ban"])[:300]}
                for x in sorted(ra.values(), key=lambda x: x["ten"].lower())]

    async def tra_cuu(self, emails: list[str], open_id_cua: dict[str, str] | None = None,
                      quet: bool = True) -> dict[str, dict]:
        """emails -> {email: {"trang_thai", "ten", "chuc_danh", "phong_ban", "open_id"}}; email
        nào cũng có mặt trong kết quả (không tìm thấy -> trang_thai "khong_co", còn lại None).
        `open_id_cua`: email -> open_id đã biết (ghi lúc đăng nhập) — tra thẳng, không qua email.
        `quet`: được dò cả danh bạ (bước 1b) khi email không khớp — tắt ở đường cần nhanh."""
        import httpx
        emails = sorted({str(e).strip().lower() for e in emails if e and "@" in str(e)})
        if not emails:
            return {}
        biet = {str(k).strip().lower(): str(v) for k, v in (open_id_cua or {}).items() if v}
        async with httpx.AsyncClient(timeout=self.giay, transport=self.transport) as kh:
            tk = await self._token_to_chuc(kh)
            h = {"Authorization": f"Bearer {tk}"}

            async def doc_nguoi(ids: list[str]) -> dict[str, dict]:
                ra: dict[str, dict] = {}
                for lo in _lo(sorted(set(ids))):
                    d = await self._goi(kh, "nguoi", "GET", DUONG_NGUOI, headers=h,
                                        params=[("user_id_type", "open_id"),
                                                ("department_id_type", "open_department_id"),
                                                *[("user_ids", x) for x in lo]])
                    for u in (d.get("data") or {}).get("items") or []:
                        if u.get("open_id"):
                            ra[str(u["open_id"])] = u
                return ra

            # 0. open_id đã biết từ lần đăng nhập -> người (Lark không trả thì rơi xuống bước 1)
            id_cua: dict[str, str] = {e: biet[e] for e in emails if e in biet}
            nguoi = await doc_nguoi(list(id_cua.values())) if id_cua else {}
            id_cua = {e: o for e, o in id_cua.items() if o in nguoi}
            # 1. email -> open_id (+ trạng thái nếu Lark kèm theo); chỉ khớp `email`, KHÔNG
            #    khớp `enterprise_email` (xem đầu module)
            st_cua: dict[str, dict] = {}
            for lo in _lo([e for e in emails if e not in id_cua]):
                d = await self._goi(kh, "email", "POST", DUONG_EMAIL_RA_ID, headers=h,
                                    params={"user_id_type": "open_id"},
                                    json={"emails": lo, "include_resigned": True})
                for u in (d.get("data") or {}).get("user_list") or []:
                    e = str(u.get("email") or "").strip().lower()
                    if e in lo and u.get("user_id"):
                        id_cua[e] = str(u["user_id"])
                        if isinstance(u.get("status"), dict):
                            st_cua[e] = u["status"]
            # 1b. còn sót -> dò cả danh bạ theo enterprise_email (hỏng thì bỏ qua)
            con = {e for e in emails if e not in id_cua}
            if con and quet:
                try:
                    for e, u in (await self._quet_ca_danh_ba(kh, h, con)).items():
                        id_cua[e] = str(u["open_id"])
                        nguoi.setdefault(str(u["open_id"]), u)
                except LoiDanhBa:
                    pass
            # 2. open_id -> người (những ai chưa có thông tin)
            thieu = [o for o in id_cua.values() if o not in nguoi]
            if thieu:
                nguoi.update(await doc_nguoi(thieu))
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
                         "phong_ban": None, "open_id": None}
                continue
            u = nguoi.get(oid) or {}
            pb = [ten_pb[str(p)] for p in (u.get("department_ids") or []) if str(p) in ten_pb]
            kq[e] = {"trang_thai": trang_thai(u.get("status") or st_cua.get(e)),
                     "ten": (str(u.get("name") or "").strip() or None),
                     "chuc_danh": (str(u.get("job_title") or "").strip()[:200] or None),
                     "phong_ban": (" · ".join(pb)[:300] or None),
                     "open_id": oid[:100]}
        return kq
