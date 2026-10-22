"""Tool `xuat_sheet_qc` — Mark xuất số quảng cáo TikTok / Meta Ads thành Lark Sheet (22/10/2026).

VÌ SAO: chủ dự án 22/10/2026 gom nút xuất Sheet quảng cáo về MỘT chỗ — trang Quảng cáo (chỉ quản trị
viên) — nhưng "khi hỏi Mark thì Mark vẫn xuất Sheet được": người hỏi Mark số quảng cáo của bên mình
phải nhận được CÙNG Lark Sheet đó. Trước đây lời dặn của `hoi_dashboard` cấm Mark tạo sheet cho số
quảng cáo; luật đó đổi ở tầng lời dặn (mô tả tool, skill, brain): CHỈ khi người hỏi đòi Sheet / file /
xuất / tải về thì gọi tool này, còn lại vẫn trả lời bằng chữ.

ĐƯỜNG ĐI (không đường Sheet thứ hai): tool chỉ THÊM một dòng `yeu_cau_sheet_qc` (nguon = 'mark',
nguoi_hoi = email người hỏi đã xác thực) qua `dashboard.kho_sheet_qc.tao` — cùng trigger, cùng trần
(một yêu cầu đang chờ mỗi người, `KS.TRAN_GIO`/giờ, 30/giờ toàn hệ thống), cùng khoá advisory với nút
trên trang. Bộ nghe `xuat_sheet_qc.py` (qc-sheet-nghe, phần của Mark) dựng Sheet ba tab, khoá riêng
tư, chia quyền XEM cho người hỏi (union_id → email → open_id) và nhắn link. Tool trả ngay "đang tạo"
+ mã yêu cầu — KHÔNG chờ, không bao giờ tự nói đã có link.

AI ĐƯỢC XUẤT, PHẠM VI NÀO (cùng cửa của `hoi_dashboard`):
  1. Người hỏi: `hoi_dashboard_tool.nguoi_hoi` (chat riêng Lark / web đã xác thực; nhóm, A2A, lịch tự
     chạy → từ chối) + `kiem_quyen` (email có quyền trên dashboard, đọc lại mỗi lần).
     Thêm (soát 22/10/2026, `xac_minh_danh_tinh`): email phải là enterprise_email Lark, hoặc union_id
     người hỏi trùng union_id dashboard ghi cho email đó — email tự khai không đủ để xuất Sheet.
  2. Tài khoản: chỉ trong các bên người hỏi đọc được (`_pham_vi_qc`, cùng luật trang; chưa gán bên
     chỉ quản trị viên). Tên / mã người hỏi nêu phải khớp tài khoản TRONG phạm vi — không khớp thì từ
     chối (không nói tài khoản đó có tồn tại ở bên khác hay không). Mỗi Sheet một bên (quản trị viên
     chọn nhiều bên → "Tất cả bên").
  3. Khoảng ngày như trang (≤ `KHOANG_TOI_DA_NGAY` = `quang_cao.XUAT_TOI_DA_NGAY`), bộ lọc bảng (tim,
     chiến dịch, sap, chieu) kiểm bằng CHÍNH `quang_cao.loc_bang` — người không xem tiền không xếp
     theo tiền.
LUẬT CỨNG Ở BỘ NGHE, KHÔNG Ở ĐÂY: tool này chỉ là lớp thứ nhất. Bộ nghe không tin dòng — tính lại
quyền, phạm vi tài khoản và cột tiền từ quyền CSDL của nguoi_hoi lúc dựng (người không xem tiền nhận
Sheet KHÔNG có cột / giá trị tiền). `co_cot_tien` tool trả chỉ để Mark nói đúng, không quyết gì.
"""
from __future__ import annotations

import datetime
import json
import re
import urllib.parse

from tools.registry import registry, tool_error, tool_result  # type: ignore

import hoi_dashboard_tool as HD
from dashboard import nhap_lieu as NL
from dashboard import phan_quyen as PQ
from dashboard import quang_cao as QC

TEN = "xuat_sheet_qc"
NEN = (*QC.NEN_TANG_QC, QC.TAT_CA)
TEN_NEN = {**QC.TEN_NEN_TANG_QC, QC.TAT_CA: "TikTok + Meta"}
GOI_Y_TOI_DA = 8
_MA_CD = re.compile(r"[0-9A-Za-z_-]{1,64}")

QUY_TAC = (
    "KHI TRẢ LỜI: nói Sheet ĐANG TẠO (thường 1–2 phút), Mark sẽ nhắn link riêng cho người hỏi trên "
    "Lark (chỉ người hỏi được xem) — KHÔNG bịa link, không nói đã xong. Xác nhận ĐÚNG phạm vi đã "
    "dùng trong `pham_vi` (bên, nền tảng, tài khoản, từ–đến, bộ lọc bảng) + `ma_yeu_cau`. "
    "`co_cot_tien` false → nói rõ Sheet KHÔNG có cột tiền (chi tiêu, CPM, CPC, chi phí…) vì người hỏi "
    "không có quyền xem tiền; không bao giờ nói Sheet có số tiền khi `co_cot_tien` false. Bị từ chối "
    "(quyền, trần, tài khoản không khớp) → chuyển nguyên lời; không khớp tài khoản thì đưa vài tên "
    "trong lời từ chối để người hỏi chọn.")

SCHEMA = {
    "name": TEN,
    "description": (
        "Xuất số quảng cáo TikTok Ads / Meta Ads (của các bên người hỏi được xem) thành MỘT Lark Sheet "
        "riêng ba tab (theo ngày × tài khoản, theo chiến dịch, theo quảng cáo) + Tổng quan — cùng "
        "Sheet với nút \"Xuất Lark Sheet theo bộ lọc này\" trên trang Quảng cáo. Miễn phí, chỉ đọc kho "
        "dashboard. Tool chỉ ghi yêu cầu rồi trả ngay; Mark tạo Sheet và nhắn link riêng sau ~1–2 "
        "phút.\n"
        "KHI NÀO GỌI (lời dặn, chủ dự án 22/10/2026): CHỈ khi người hỏi ĐÒI Sheet / file / Excel / "
        "bảng tính / \"xuất\" / \"tải về\" / \"gửi file\" số quảng cáo. Hỏi số bình thường (\"tuần "
        "này chi bao nhiêu\", \"chiến dịch A thế nào\") → trả lời BẰNG CHỮ bằng `hoi_dashboard` "
        "(hoặc `lay_so_tuc_thi` khi cần số mới), KHÔNG tạo Sheet. Không rõ có muốn file không thì "
        "trả lời bằng chữ trước. Thiếu bên / tài khoản / kỳ mà đoán không được → hỏi lại MỘT câu "
        "ngắn; không nói kỳ thì dùng mặc định 30 ngày trọn tới hết hôm qua và nói rõ.\n"
        "THAM SỐ: `tai_khoan` = tên (một phần, không cần dấu) hoặc mã tài khoản người hỏi nêu; trống "
        "= mọi tài khoản của `ben` (+ `nen_tang`). Tên chiến dịch → `tim` (lọc theo tên chiến dịch / "
        "quảng cáo); `chien_dich` chỉ nhận MÃ chiến dịch. `sap`/`chieu` = cột xếp tab chiến dịch / "
        "quảng cáo. Mỗi Sheet một bên (quản trị viên: nhiều bên → \"Tất cả bên\").\n"
        "TIỀN: người không có quyền xem tiền của bên nhận Sheet KHÔNG có cột tiền (bộ tạo Sheet tự "
        "quyết từ quyền trong CSDL) — đừng hứa chi tiêu / CPM / CPC trong Sheet đó.\n"
        + QUY_TAC
        + ("" if QC.HIEN_DOANH_THU else " Doanh thu Shop / ROAS không có trong Sheet (tạm ẩn "
                                        "22/10/2026).")),
    "parameters": {
        "type": "object",
        "properties": {
            "nen_tang": {"type": "string", "enum": list(NEN),
                         "description": "tiktok | meta | tat_ca (mặc định: cả hai)."},
            "ben": {"type": "string",
                    "description": "Mã bên (hapas, matemade…). Trống = suy từ tài khoản, hoặc bên "
                                   "duy nhất người hỏi xem được."},
            "tai_khoan": {"type": "array", "items": {"type": "string"},
                          "description": "Tên hoặc mã tài khoản quảng cáo người hỏi nêu (tối đa "
                                         f"{QC.TK_TOI_DA}). Trống = mọi tài khoản của bên."},
            "tu": {"type": "string", "description": "Ngày đầu, YYYY-MM-DD (giờ VN)."},
            "den": {"type": "string", "description": "Ngày cuối, YYYY-MM-DD. Trống = hôm qua."},
            "so_ngay": {"type": "integer",
                        "description": "N ngày trọn gần nhất tới hết hôm qua, khi không đưa `tu`."},
            "tim": {"type": "string",
                    "description": f"Lọc tab chiến dịch / quảng cáo theo tên (≤ {QC.TIM_TOI_DA} ký "
                                   "tự, không cần dấu)."},
            "chien_dich": {"type": "string",
                           "description": "MÃ chiến dịch: tab chiến dịch chỉ chiến dịch đó, tab quảng "
                                          "cáo chỉ quảng cáo của nó."},
            "sap": {"type": "string", "enum": list(QC.SAP_BANG),
                    "description": "Xếp tab chiến dịch / quảng cáo theo: " + ", ".join(
                        f"{k} ({v})" for k, v in QC.SAP_BANG.items())
                    + ". Mặc định chi (người không xem tiền: hien_thi)."},
            "chieu": {"type": "string", "enum": list(QC.CHIEU_BANG),
                      "description": "giam (cao → thấp, mặc định) | tang."},
        },
    },
}


def _ds(x) -> list[str]:
    """`tai_khoan` của model (chuỗi hoặc danh sách) → danh sách chữ gọn, không trùng."""
    if isinstance(x, str):
        x = [x]
    ra: list[str] = []
    for v in x or ():
        s = " ".join(str(v or "").split())[:200]
        if s and s not in ra:
            ra.append(s)
    if len(ra) > QC.TK_TOI_DA:
        raise NL.LoiNhap(f"Tối đa {QC.TK_TOI_DA} tài khoản mỗi Sheet.")
    return ra


def _ten_tk(t: dict) -> str:
    return str(t.get("ten") or t["advertiser_id"])


def chon_tai_khoan(q: dict, cac_tk: list[dict], nen: str, ben_hoi: str,
                   ten_tk: list[str]) -> tuple[str, list[dict]]:
    """(bên của dòng, tài khoản đã chọn) — CHỈ trong phạm vi người hỏi đọc được (cùng luật trang).
    Không được → NL.LoiNhap (câu cho Mark chuyển lại / hỏi lại người dùng)."""
    tk_nen = QC.tk_dung(cac_tk, None if nen == QC.TAT_CA else nen)
    cac_ben = HD._pham_vi_qc(q, tk_nen, ben_hoi, True)
    nen_chu = "" if nen == QC.TAT_CA else f" trên {TEN_NEN[nen]}"
    if not cac_ben:
        raise NL.LoiNhap("Không có tài khoản quảng cáo nào" + nen_chu + " trong phạm vi bạn được "
                         "xem" + (f" (bên “{ben_hoi}”)" if ben_hoi else "") + ".")
    pham_vi = {b: QC.tk_trong_pham_vi(q, tk_nen, b) for b in cac_ben}
    qt = PQ.la_quan_tri(q)
    if not ten_tk:
        if ben_hoi:
            ben = ben_hoi
        elif len(cac_ben) == 1:
            ben = cac_ben[0]
        elif qt:
            ben = QC.TAT_CA
        else:
            raise NL.LoiNhap("Bạn xem được nhiều bên (" + ", ".join(cac_ben) + ") — mỗi Sheet một "
                             "bên: hỏi người dùng muốn Sheet của bên nào.")
        return ben, QC.tk_xuat(q, cac_tk, ben, nen)
    chon: list[tuple[str, dict]] = []
    for x in ten_tk:
        mau = QC.chu_tim(x)
        khop = [(b, t) for b, ds in pham_vi.items() for t in ds if HD._khop_tk(t, mau, x)]
        dung = [(b, t) for b, t in khop if QC.chu_tim(_ten_tk(t)) == mau
                or str(t["advertiser_id"]) in (x, f"act_{x}")]
        khop = dung or khop
        if not khop:
            co = [_ten_tk(t) for ds in pham_vi.values() for t in ds][:GOI_Y_TOI_DA]
            raise NL.LoiNhap(f"Không thấy tài khoản “{x}” trong phạm vi bạn được xem"
                             + nen_chu + ". Tài khoản đang có: " + (", ".join(co) or "chưa có")
                             + ".")
        if len({str(t["advertiser_id"]) for _, t in khop}) > 1:
            raise NL.LoiNhap(f"“{x}” khớp nhiều tài khoản: " + ", ".join(
                _ten_tk(t) for _, t in khop[:GOI_Y_TOI_DA]) + " — hỏi người dùng muốn tài khoản "
                "nào (hoặc dùng `ben` để lấy mọi tài khoản của một bên).")
        if all(str(t["advertiser_id"]) != str(khop[0][1]["advertiser_id"]) for _, t in chon):
            chon.append(khop[0])
    cac = sorted({b for b, _ in chon})
    if len(cac) == 1:
        ben = cac[0]
    elif qt:
        ben = QC.TAT_CA
    else:
        raise NL.LoiNhap("Các tài khoản thuộc nhiều bên (" + ", ".join(cac) + ") — mỗi Sheet một "
                         "bên: xuất từng bên một.")
    return ben, [t for _, t in chon]


CAU_DANH_TINH = (
    "Mark chưa xác minh được email {email} đúng là của bạn: danh bạ Lark không có email công ty do tổ "
    "chức cấp (chỉ email tự khai), và tài khoản đó chưa khớp lần đăng nhập dashboard của bạn. Mark không "
    "xuất Sheet theo email này. Đăng nhập social.hapas.vn một lần bằng Lark rồi hỏi lại, hoặc nhờ quản "
    "trị viên Lark cấp email công ty.")


def lien_he(open_id: str) -> dict:
    """open_id → {enterprise_email, email, union_id} từ danh bạ Lark (app Mark). Không đọc được → ném."""
    r = HD.lark.call("GET", f"/open-apis/contact/v3/users/{urllib.parse.quote(open_id)}",
                     query={"user_id_type": "open_id"})
    u = ((r or {}).get("data") or {}).get("user") or {}
    return {"enterprise_email": str(u.get("enterprise_email") or "").strip().lower(),
            "email": str(u.get("email") or "").strip().lower(),
            "union_id": str(u.get("union_id") or "").strip()}


def xac_minh_danh_tinh(kho, open_id: str, email: str) -> None:
    """Soát 22/10/2026: `HD.email_cua` lùi từ enterprise_email (tổ chức cấp) sang `email` NGƯỜI DÙNG
    TỰ KHAI trong Lark — ai đó khai email của người khác sẽ xuất Sheet dưới quyền người đó. Tool này
    TẠO Sheet và chia quyền theo email nên đòi chắc hơn: email là enterprise_email → nhận; không thì
    union_id của người hỏi (danh bạ app Mark) phải TRÙNG union_id dashboard ghi cho email đó lúc đăng
    nhập bằng Lark (`kho.union_id_cua`). Thiếu / lệch / không đọc được → HD.TuChoi."""
    try:
        u = lien_he(open_id)
    except Exception as e:  # noqa: BLE001 — không đối chiếu được thì ĐÓNG
        print(f"[{TEN}] danh bạ lỗi: {type(e).__name__}")
        raise HD.TuChoi("Mark chưa đối chiếu được danh bạ Lark lúc này nên chưa xuất Sheet — thử lại "
                        "sau ít phút.") from None
    if u["enterprise_email"]:
        if u["enterprise_email"] == email:
            return
        raise HD.TuChoi(CAU_DANH_TINH.format(email=email))
    try:
        uid_kho = kho.union_id_cua(email)
    except Exception:  # noqa: BLE001
        uid_kho = None
    if u["union_id"] and uid_kho and u["union_id"] == str(uid_kho).strip():
        return
    raise HD.TuChoi(CAU_DANH_TINH.format(email=email))


def tra_loi(args: dict, kho=None, *, open_id: str | None = None,
            bay_gio: datetime.datetime | None = None) -> dict:
    """Lõi của tool (bài thử gọi thẳng với kho giả). Ném HD.TuChoi / NL.LoiNhap / LoiDuLieu."""
    kho = kho or HD._kho_mac_dinh()
    oid = open_id if open_id is not None else HD.nguoi_hoi()
    nguoi = HD.kiem_quyen(kho, oid)
    q, email = nguoi["q"], nguoi["email"]
    xac_minh_danh_tinh(kho, oid, email)
    args = args or {}
    bay_gio = bay_gio or datetime.datetime.now(HD.VN)
    hn = bay_gio.astimezone(HD.VN).date()
    nen = str(args.get("nen_tang") or QC.TAT_CA).strip().lower()
    if nen not in NEN:
        raise NL.LoiNhap("`nen_tang` chỉ nhận tiktok, meta hoặc tat_ca.")
    ben_hoi = str(args.get("ben") or "").strip().lower()
    if ben_hoi == QC.TAT_CA:
        ben_hoi = ""                  # "mọi bên": như không nói bên (quản trị viên → Tất cả bên)
    tu, den = HD.doc_khoang(args, hn)
    if (den - tu).days + 1 > QC.XUAT_TOI_DA_NGAY:
        raise NL.LoiNhap(f"Khoảng tối đa {QC.XUAT_TOI_DA_NGAY} ngày.")
    ten_tk = _ds(args.get("tai_khoan"))
    tim = " ".join(str(args.get("tim") or "").split())
    if len(tim) > QC.TIM_TOI_DA:
        raise NL.LoiNhap(f"`tim` tối đa {QC.TIM_TOI_DA} ký tự.")
    cd = str(args.get("chien_dich") or "").strip()
    if cd and not _MA_CD.fullmatch(cd):
        raise NL.LoiNhap("`chien_dich` chỉ nhận MÃ chiến dịch (chữ số / chữ Latin); tên chiến dịch "
                         "thì đưa vào `tim`.")
    sap = str(args.get("sap") or "").strip()
    if sap and sap not in QC.SAP_BANG:
        raise NL.LoiNhap("`sap` chỉ nhận: " + ", ".join(QC.SAP_BANG) + ".")
    chieu = str(args.get("chieu") or "").strip()
    if chieu and chieu not in QC.CHIEU_BANG:
        raise NL.LoiNhap("`chieu` chỉ nhận giam hoặc tang.")
    try:
        cac_tk = list(kho.qc_cac_tk())
    except Exception as e:  # noqa: BLE001 — bảng chưa tạo / chưa cấp quyền: nói rõ, không đoán
        if HD._loi_kho(e):
            raise
        print(f"[{TEN}] đọc tài khoản lỗi: {type(e).__name__}")
        raise NL.LoiNhap("Chưa đọc được danh sách tài khoản quảng cáo lúc này — thử lại sau ít "
                         "phút.") from None
    ben, tk = chon_tai_khoan(q, cac_tk, nen, ben_hoi, ten_tk)
    # Kiểm lại bằng ĐÚNG luật bộ nghe dùng (`tk_xuat`): mọi tài khoản đã chọn phải còn trong phạm vi.
    ids = [str(t["advertiser_id"]) for t in tk]
    tk_pv = QC.tk_xuat(q, cac_tk, ben, nen)
    if not tk or not {str(t["advertiser_id"]) for t in tk_pv} >= set(ids):
        raise NL.LoiNhap("Phạm vi này không có tài khoản quảng cáo nào bạn được xem.")
    tk_ds, _ngoai = QC.tk_chon(ids, tk_pv)          # chọn đủ mọi tài khoản = NULL (như trang)
    co_tien = all(QC.xem_tien(q, t.get("don_vi") or None) for t in tk)
    if sap in QC.SAP_BANG_TIEN and not co_tien:
        raise NL.LoiNhap(f"Bạn không xem được tiền của phạm vi này nên không xếp theo "
                         f"{QC.SAP_BANG[sap]} — chọn cột khác (hiển thị, click, view…).")
    lb = QC.loc_bang({"tim": tim, "cd": cd, "sap": sap, "chieu": chieu}, co_tien)
    # Trần / "đang có Sheet chờ" → LoiDuLieu (cùng câu trang Quảng cáo), `_handle` chuyển lại.
    r = kho.sq_tao(email, ben, nen, None, tu, den, tk_ds=tk_ds or None, tim=lb["tim"] or None,
                   cd=lb["cd"] or None, sap=lb["sap"], chieu=lb["chieu"], nguon="mark")
    try:
        ten_ben = {**kho.sq_ten_ben(), QC.TAT_CA: "Tất cả bên", QC.CHUA_GAN: "Chưa gán bên"}
    except Exception:  # noqa: BLE001 — chỉ để nói tên bên cho đẹp
        ten_ben = {QC.TAT_CA: "Tất cả bên", QC.CHUA_GAN: "Chưa gán bên"}
    return {
        "trang_thai": "dang_tao", "ma_yeu_cau": (r or {}).get("id"),
        "pham_vi": {
            "ben": ten_ben.get(ben, ben.upper()), "nen_tang": TEN_NEN[nen],
            "tai_khoan": ([{"ten": _ten_tk(t), "nen_tang": TEN_NEN[QC.nen_tang_tk(t)]} for t in tk]
                          if tk_ds else f"mọi tài khoản của phạm vi ({len(tk)})"),
            "tu": tu.isoformat(), "den": den.isoformat(), "so_ngay": (den - tu).days + 1,
            "bo_loc_bang": {"tim": lb["tim"] or None, "chien_dich": lb["cd"] or None,
                            "xep_theo": QC.SAP_BANG.get(lb["sap"], lb["sap"]),
                            "chieu": "thấp → cao" if lb["chieu"] == "tang" else "cao → thấp"}},
        "co_cot_tien": co_tien,
        "canh_bao": (["Kỳ có ngày hôm nay (chưa hết ngày): số trong Sheet còn tăng."]
                     if den >= hn else []),
        "ghi_chu": ("Số trong Sheet là số kho dashboard (đồng bộ TikTok 06:30, Meta 06:45 mỗi "
                    "sáng). " + QUY_TAC),
    }


def _handle(args: dict, **_kw) -> str:
    from dashboard.kho import LoiDuLieu
    try:
        ra = tra_loi(args or {})
    except HD.TuChoi as e:
        return tool_error(str(e))
    except NL.LoiNhap as e:
        return tool_error(f"Chưa tạo yêu cầu Sheet: {e}")
    except LoiDuLieu as e:            # trần / đang có Sheet chờ (cùng câu trang Quảng cáo)
        return tool_error(f"Chưa tạo yêu cầu Sheet: {e}")
    except Exception as e:  # noqa: BLE001
        if HD._loi_kho(e):
            return tool_error(f"Chưa ghi được yêu cầu vào kho ({e}). Nói rõ là chưa tạo Sheet.")
        print(f"[{TEN}] lỗi: {type(e).__name__}: {str(e)[:200]}")
        return tool_error(f"Tạo yêu cầu Sheet lỗi ({type(e).__name__}). Nói rõ là chưa tạo Sheet.")
    return tool_result(json.loads(json.dumps(ra, ensure_ascii=False, default=str)))


def register() -> None:
    try:
        registry.register(
            name=TEN, toolset="lark_api", schema=SCHEMA, handler=_handle,
            check_fn=lambda: True, requires_env=[], is_async=False,
            description="Xuất số quảng cáo TikTok / Meta Ads thành Lark Sheet riêng cho người hỏi",
            emoji="\U0001f4c4", override=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[{TEN}] register warning: {e}")


register()
