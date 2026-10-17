"""Tool `hoi_dashboard` — hỏi đáp số liệu dashboard lắng nghe `social.hapas.vn` ngay trong chat.

VÌ SAO (chủ dự án 17/10/2026): "nối trực tiếp số liệu dashboard vào mark trần để có thể hỏi đáp
trực tiếp với mark trần về toàn bộ dashboard". Trước đây muốn biết "tuần này tiêu cực bao nhiêu
%", "nguồn nào nói nhiều nhất" thì phải mở dashboard; Mark chỉ có sheet `social_listen` của từng
lượt quét tay — số hai bên không cùng tập, cùng bộ lọc.

CÙNG MỘT PHÉP TÍNH VỚI TRANG
Không viết lại công thức nào: số lấy bằng đúng hàm của dashboard (`dashboard.chi_so.tong_hop`,
`tu_khoa_thao_luan`, `tong_hop_bl`, `y_dinh_mua`, `tong_quan_loc`; ngân sách `dashboard.chi_phi`,
lịch `dashboard.trang_lich`) trên đúng các dòng mà `dashboard.kho` đọc (cùng câu SQL, cùng trần
dòng). `tinh_chi_so` ghép các khối y như `/api/chi-so` của `dashboard/app.py` — bài thử
`test_hoi_dashboard.py` so TỪNG KHỐI với chính endpoint đó trên cùng kho giả: lệch là đỏ. Chỉ có
phần RÚT GỌN cho model (cắt top N, bỏ chuỗi biểu đồ dài) là của riêng tool.
Dashboard chạy venv riêng và không import Mark; chiều Mark → `dashboard` thì được (gói thuần,
xem `dashboard/__init__.py`). Tool KHÔNG import `dashboard.app` (FastAPI không có trong venv Mark).

AI ĐƯỢC HỎI (chốt chặn bằng code — đây là dữ liệu nội bộ, không phải lời dặn)
  1. Danh tính người hỏi chỉ từ nguồn đã xác thực (cùng luật `meta_ads_tool._actor`): chat RIÊNG
     Lark (người gửi do listener/Platform ghi) hoặc web console có `sender_identity_verified`.
     Nhóm chat → từ chối (thành viên nhóm chưa chắc là người xem dashboard). A2A, lịch, kênh lạ →
     từ chối.
  2. open_id → email công ty qua danh bạ Lark (`enterprise_email`, trống mới lấy `email` — cùng
     thứ tự với đăng nhập dashboard `dang_nhap.LarkOAuth`).
  3. Email phải có trong bảng `nguoi_xem` (vai trò `xem` hoặc `quan_ly`), đọc lại MỖI lần gọi
     bằng đúng `dashboard.kho.vai_tro` — xoá người xem trên dashboard là Mark thôi trả số ngay.
  Không kiểm được bước nào thì ĐÓNG (không trả số), nói rõ vì sao.

KHÔNG DÙNG DỮ LIỆU CÁ NHÂN THÔ
Chỉ trả số tổng hợp + top N (≤ `TOP_TOI_DA`) bài/nguồn công khai kèm link — đúng thứ dashboard
hiện. KHÔNG trả tên người bình luận, nội dung từng bình luận, email người sửa; chữ lỗi thô của lượt
quét chỉ người `quan_ly` thấy (như `app.an_chi_tiet`). Câu trả lời được gắn cờ hạn chế
(`lsr_platform.danh_dau_han_che`) để Platform ẩn khỏi bản ghi hội thoại của người dưới moderator.

KHO
Đọc bằng role `mark` (Unix socket + peer, DSN của Mark `lang_nghe_db._dsn`). Quyền đọc thêm cần
cho tool: `nguoi_xem (email, vai_tro)` — xem `deploy/lang-nghe/schema.sql`. Lịch quét đọc bằng
câu SQL riêng (`KhoMark.cac_lich`) vì role `mark` không được đọc email người tạo/sửa lịch.
"""
from __future__ import annotations

import collections
import datetime
import json
import os
import threading
import time
import urllib.parse

from tools.registry import registry, tool_error, tool_result  # type: ignore

import lark_client as lark
import memory_store
import scheduler
from dashboard import chi_phi as CP
from dashboard import chi_so as CS
from dashboard import nhap_lieu as NL
from dashboard import trang_lich as TL

VN = CS.VN
#: Trang dashboard (đổi bằng env khi thử ở máy khác). Link luôn kèm đúng query string của bộ lọc.
DASHBOARD_URL = (os.environ.get("MARK_DASHBOARD_URL") or "").strip().rstrip("/") \
    or "https://social.hapas.vn"
KHOANG_TOI_DA_NGAY = 400          # như `app.KHOANG_TOI_DA_NGAY`
VAI_TRO_XEM = ("xem", "quan_ly")  # như `nhap_lieu.VAI_TRO`
LOI_CHUNG = "có lỗi — người quản lý xem chi tiết"     # như `app.LOI_CHUNG`
TOP_MAC_DINH, TOP_TOI_DA = 5, 10
LUOT_TOI_DA = 10
CHU_TOI_DA = 160                  # đoạn nội dung bài trả cho model
NHO_GIAY, NHO_TOI_DA = 60.0, 8    # kết quả tính nhớ lại (khoá có mốc lượt quét, như app)
EMAIL_NHO_GIAY = 600.0            # open_id → email (vai trò thì đọc lại mỗi lần)

PHAN = {
    "tong_quan": "KPI (bài, thảo luận, bình luận, lượt xem, tương tác, nguồn) + % đổi so với kỳ "
                 "trước cùng độ dài, sắc thái %, ý định mua, Internal vs External",
    "xu_huong": "thảo luận/bài theo ngày (khoảng > 92 ngày: theo tuần) + đỉnh",
    "sac_thai": "sắc thái bài (External) và bình luận hợp lệ, so kỳ trước",
    "chu_de": "chủ đề × sắc thái (bài và bình luận)",
    "tu_khoa": "từ khoá nổi bật (mây từ) kèm sắc thái nổi trội",
    "nguon": "nguồn nhiều thảo luận nhất từng nền tảng + phân bố nền tảng/loại nguồn",
    "bai": "bài nhiều thảo luận nhất (link, nguồn, sắc thái, chủ đề, số)",
    "binh_luan": "bình luận đã cào: hợp lệ/spam/seeding…, sắc thái, chủ đề",
    "y_dinh_mua": "bình luận hỏi giá/muốn mua: số, %, so kỳ trước, chia theo MÓN (túi, ví, "
                  "nước hoa, set quà…), bài nhiều nhất",
    "web": "Báo & Web: số bài, số miền, % PR, % nhắc ở tiêu đề, theo loại trang",
    "nha_ngoai": "Internal channel vs External channel",
    "khung_hoang": "tín hiệu khủng hoảng: bài tiêu cực ≥ 1.000 tương tác, tiêu cực tăng",
    "chi_phi": "ngân sách tháng: đã tiêu, dự báo, trần, các lượt quét gần nhất (chi phí, kết quả)",
    "lich": "lịch quét tự động: trạng thái, mốc kế, ≈ USD 30 ngày, kết quả lần gần nhất",
    "do_phu": "kiểm độ phủ thu thập hằng tuần (khi đã có)",
    "bo_loc": "giá trị lọc đang có dữ liệu (nền tảng, loại nguồn, chủ đề, khoá nguồn…)",
}
PHAN_MAC_DINH = ("tong_quan", "sac_thai", "chu_de", "tu_khoa", "bai")
#: Phần cần dòng bài/bình luận (tính `tinh_chi_so`); phần còn lại chỉ đọc cấu hình/lượt quét.
_PHAN_SO_LIEU = {"tong_quan", "xu_huong", "sac_thai", "chu_de", "tu_khoa", "nguon", "bai",
                 "binh_luan", "y_dinh_mua", "web", "nha_ngoai", "khung_hoang", "bo_loc"}
_HOI_RIENG = ("Hãy hỏi Mark trong chat RIÊNG trên Lark (hoặc web console đã đăng nhập), hoặc mở "
              f"thẳng dashboard {DASHBOARD_URL}.")

SCHEMA = {
    "name": "hoi_dashboard",
    "description": (
        "Đọc số liệu dashboard lắng nghe social.hapas.vn (kho bài + bình luận Mark quét theo "
        "dự án) bằng ĐÚNG phép tính của trang — số khớp dashboard. Chỉ đọc, miễn phí, không "
        "quét thêm. Chỉ trả cho người có tên trong danh sách người xem dashboard, trong chat "
        "riêng.\n"
        "KHI NÀO GỌI: hỏi về số liệu/tình hình lắng nghe của một dự án đang theo dõi trên "
        "dashboard — bao nhiêu bài/thảo luận, tăng giảm so với kỳ trước, tích cực/tiêu cực %, "
        "chủ đề, từ khoá nổi bật, nguồn/KOL nói nhiều, bài nổi bật, Internal vs External "
        "channel, khách hỏi mua, báo & web, cảnh báo khủng hoảng, chi phí/ngân sách quét, lịch "
        "quét, độ phủ. KHÔNG dùng để quét mới (đó là `social_listen`/`/theodoi`).\n"
        "THAM SỐ: không nói kỳ thì để trống (= 30 ngày trọn tới hết hôm qua, như dashboard). "
        "`bo_loc` dùng đúng mã của dashboard; giá trị nguồn/chủ đề lạ thì gọi `phan`=[\"bo_loc\"] "
        "để lấy giá trị hợp lệ.\n"
        "KHI TRẢ LỜI: chép số và % từ kết quả (không tự tính lại; cần phép tính mới thì `tinh`), "
        "nói rõ kỳ + kỳ so sánh + bộ lọc, kèm `link` để người hỏi mở đúng màn hình. "
        "`canh_bao` có gì thì phải nói (bị cắt dòng, chưa gán nhãn xong, ngày chưa trọn). Bị từ "
        "chối vì quyền thì chuyển nguyên lời từ chối, không tìm đường khác."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "du_an": {"type": "string",
                      "description": "Mã dự án trên dashboard (vd `hapas`). Trống = dự án mặc "
                                     "định của dashboard; kết quả có `cac_du_an` để đối chiếu."},
            "tu": {"type": "string", "description": "Ngày đầu, YYYY-MM-DD (giờ VN)."},
            "den": {"type": "string",
                    "description": "Ngày cuối, YYYY-MM-DD. Trống = hôm qua (ngày trọn)."},
            "so_ngay": {"type": "integer",
                        "description": "N ngày trọn gần nhất tới hết hôm qua, khi không đưa `tu`."},
            "bo_loc": {
                "type": "object",
                "description": (
                    "Bộ lọc chung của dashboard, giá trị một chuỗi hoặc danh sách. pham_vi: "
                    "tat_ca|kenh_nha (Internal channel)|ben_ngoai (External channel); nen_tang: "
                    "tiktok,facebook,instagram,youtube,threads,web; loai: kol,page,group,bao,"
                    "kenh_nha,khac,tu_khoa; sac_thai: tich_cuc,tieu_cuc,trung_lap,chua_phan_loai;"
                    " chu_de: nhãn chủ đề; nguon: khoá nguồn (lấy từ phần bo_loc/nguon); "
                    "anh_huong: nano,micro,macro,mega,khong_ro; tuong_tac: 100|1000|10000; q: chữ "
                    "tìm; kieu_quet: theo_doi|tu_khoa; kieu_trang: bao,dien_dan,blog,mxh_khac,"
                    "khac; y_dinh: \"1\" = chỉ bình luận hỏi mua, hoặc mã món = chỉ bình luận "
                    "hỏi mua món đó (" + ", ".join(k for k in CS.Y_DINH if k != "1") + "); "
                    "gom_mg: \"1\" = mây từ gồm minigame."),
                "additionalProperties": True,
            },
            "bo_loc_nhanh": {"type": "string",
                             "description": "Chip lọc nhanh của dashboard: " + ", ".join(
                                 f"{x['ma']} ({x['ten']})" for x in CS.BO_LOC_NHANH) + "."},
            "phan": {"type": "array", "items": {"type": "string", "enum": list(PHAN)},
                     "description": "Phần cần lấy. Trống = " + ", ".join(PHAN_MAC_DINH) + ". "
                                    + "; ".join(f"{k}: {v}" for k, v in PHAN.items())},
            "so_dong": {"type": "integer",
                        "description": f"Số dòng mỗi danh sách top (mặc định {TOP_MAC_DINH}, tối "
                                       f"đa {TOP_TOI_DA})."},
        },
    },
}


class TuChoi(Exception):
    """Không trả số: câu thông báo đưa nguyên cho người hỏi."""


# ───────────────────────────── kho (đọc) ─────────────────────────────
_KHOA_DSN = threading.Lock()
_HAM_KHO = ("vai_tro", "cac_du_an", "doc_du_an", "bai_trong_khoang", "binh_luan_trong_khoang",
            "binh_luan_hop_le_gon", "bai_theo_khoa", "ngu_canh_bai", "cac_nguon", "da_tieu_thang",
            "tran_platform", "cac_luot", "tien_do_gan_nhan", "luot_xong_moi_nhat",
            "do_phu_gan_nhat")


class KhoMark:
    """Hàm ĐỌC của `dashboard.kho` (cùng câu SQL, cùng trần dòng với trang) chạy bằng DSN của
    Mark. `dashboard.kho` tự đọc `LANG_NGHE_WEB_DSN`; trong tiến trình Mark không ai khác dùng
    module đó (Mark chỉ import `dashboard.lich_quet`/`chuan_chu`), nên tạm thay `_dsn` dưới khoá
    — không đặt biến môi trường (tiến trình con của Mark chép os.environ). Chỉ các tên trong
    `_HAM_KHO`: tool không bao giờ gọi được hàm GHI của dashboard qua cửa này."""

    def __getattr__(self, ten: str):
        if ten not in _HAM_KHO:
            raise AttributeError(ten)
        from dashboard import kho as K
        fn = getattr(K, ten)          # hàm chưa có ở bản dashboard này → AttributeError

        def chay(*a, **kw):
            import lang_nghe_db
            with _KHOA_DSN:
                goc = K._dsn
                K._dsn = lang_nghe_db._dsn
                try:
                    return fn(*a, **kw)
                finally:
                    K._dsn = goc
        return chay

    @staticmethod
    def cac_lich(du_an: str) -> list[dict]:
        """Như `dashboard.kho.cac_lich` nhưng chỉ các cột role `mark` được đọc (không email
        người tạo/sửa lịch) — `deploy/lang-nghe/schema.sql`."""
        import lang_nghe_db
        with lang_nghe_db.ket_noi() as c:
            return c.execute(
                "SELECT l.id, l.du_an, l.ten, l.kieu, l.cau_hinh, l.bat, l.quet_moi_nguon, "
                "l.lan_chay_ke, l.lan_chay_cuoi, l.ket_qua_cuoi, l.so_lan_chay, "
                "lq.id AS luot_id, lq.ma_viec AS luot_ma_viec, lq.trang_thai AS luot_trang_thai, "
                "lq.bat_dau AS luot_bat_dau, lq.ket_thuc AS luot_ket_thuc, "
                "lq.bai_moi AS luot_bai_moi, lq.bai_cap_nhat AS luot_bai_cap_nhat, "
                "lq.chi_phi_usd::float AS luot_chi_phi, lq.loi AS luot_loi FROM lich_quet l "
                "LEFT JOIN LATERAL (SELECT id, ma_viec, trang_thai, bat_dau, ket_thuc, bai_moi, "
                "bai_cap_nhat, chi_phi_usd, loi FROM luot_quet WHERE lich_id = l.id "
                "ORDER BY id DESC LIMIT 1) lq ON TRUE WHERE l.du_an = %s ORDER BY l.id",
                (du_an,)).fetchall()


_kho = None


def _kho_mac_dinh():
    global _kho
    if _kho is None:
        _kho = KhoMark()
    return _kho


def _loi_kho(e: Exception) -> bool:
    """Lỗi "không dùng được kho" của dashboard hoặc của Mark (câu không bao giờ có DSN)."""
    try:
        from dashboard.kho import LoiKho as A
        from lang_nghe_db import LoiKho as B
        return isinstance(e, (A, B))
    except ImportError:
        return False


# ───────────────────────────── ai được hỏi ─────────────────────────────
def _ngu_canh() -> dict:
    """`kenh` của lượt (brain.reply → meta_ads_tool.set_context): chỉ code Mark dựng nó từ cột job
    Platform hoặc sự kiện listener — không trường nào lấy từ nội dung tin hay đối số tool."""
    try:
        import meta_ads_tool
        return dict(meta_ads_tool._context.get() or {})
    except Exception:  # noqa: BLE001
        return {}


def nguoi_hoi() -> str:
    """open_id người hỏi đã xác thực, hoặc ném TuChoi. Cùng luật `meta_ads_tool._actor`."""
    k = _ngu_canh()
    kenh = str(k.get("channel") or "").strip().lower()
    if kenh == "a2a":
        raise TuChoi("Số liệu dashboard không trả qua agent khác (A2A): không xác thực được "
                     "người cần số. " + _HOI_RIENG)
    if scheduler.get_current_chat_type() == "group" or k.get("chat_type") == "group":
        raise TuChoi("Số liệu dashboard chỉ dành cho người có quyền xem dashboard, nên Mark không "
                     "trả trong nhóm chat (thành viên nhóm chưa chắc đều có quyền). " + _HOI_RIENG)
    if k.get("scheduled") is True:
        raise TuChoi("Lịch tự chạy chưa được trả số dashboard: chưa xác minh được chat nhận lịch là "
                     "chat riêng của người đặt lịch. " + _HOI_RIENG)
    ai = memory_store.get_current_sender()
    if kenh == "web":
        if k.get("sender_identity_verified") is not True or ai != k.get("nguoi_gui"):
            raise TuChoi("Web chưa xác thực người hỏi. Đăng nhập console rồi hỏi lại, hoặc hỏi "
                         "trong chat riêng Lark.")
    elif kenh == "lark":
        if k.get("chat_type") != "p2p":
            raise TuChoi("Không xác định được đây là chat riêng. " + _HOI_RIENG)
        if ai != k.get("nguoi_gui"):
            raise TuChoi("Người hỏi không khớp người gửi tin Lark; chưa trả số. " + _HOI_RIENG)
    else:
        raise TuChoi("Không xác định được kênh hỏi nên chưa trả số dashboard. " + _HOI_RIENG)
    if not (isinstance(ai, str) and ai.startswith("ou_") and len(ai) <= 100):
        raise TuChoi("Chưa xác thực được người hỏi. " + _HOI_RIENG)
    return ai


_email_nho: dict[str, tuple[float, str]] = {}
_KHOA_EMAIL = threading.Lock()


def email_cua(open_id: str) -> str:
    """open_id → email công ty (chữ thường), "" khi danh bạ không trả. `enterprise_email` (tổ chức
    cấp) trước, trống mới lấy `email` — đúng thứ tự đăng nhập dashboard. Nhớ `EMAIL_NHO_GIAY`."""
    with _KHOA_EMAIL:
        x = _email_nho.get(open_id)
        if x and time.monotonic() - x[0] < EMAIL_NHO_GIAY:
            return x[1]
    try:
        r = lark.call("GET", f"/open-apis/contact/v3/users/{urllib.parse.quote(open_id)}",
                      query={"user_id_type": "open_id"})
    except Exception as e:  # noqa: BLE001
        print(f"[hoi_dashboard] danh bạ lỗi: {type(e).__name__}")
        return ""
    u = ((r or {}).get("data") or {}).get("user") or {}
    email = (str(u.get("enterprise_email") or "").strip()
             or str(u.get("email") or "").strip()).lower()
    email = email if "@" in email and len(email) <= 254 else ""
    if email:
        with _KHOA_EMAIL:
            _email_nho[open_id] = (time.monotonic(), email)
    return email


def kiem_quyen(kho, open_id: str) -> dict:
    """{"email", "vai_tro"} khi người hỏi là người xem dashboard; không thì ném TuChoi."""
    email = email_cua(open_id)
    if not email:
        raise TuChoi("Mark chưa đọc được email Lark của bạn nên chưa đối chiếu được danh sách "
                     "người xem dashboard (app Mark cần quyền đọc email trong danh bạ). Nhờ chủ "
                     f"agent kiểm tra, hoặc mở thẳng {DASHBOARD_URL}.")
    try:
        vai = kho.vai_tro(email)
    except Exception as e:  # noqa: BLE001 — không đọc được danh sách thì ĐÓNG
        print(f"[hoi_dashboard] đọc nguoi_xem lỗi: {type(e).__name__}")
        raise TuChoi("Mark chưa đọc được danh sách người xem dashboard lúc này nên chưa trả số. "
                     f"Thử lại sau ít phút, hoặc mở thẳng {DASHBOARD_URL}.") from None
    if vai not in VAI_TRO_XEM:
        raise TuChoi(f"Email {email} chưa có trong danh sách người xem dashboard nên Mark không "
                     "trả số liệu. Nhờ người quản lý dashboard thêm email này ở tab Người xem.")
    return {"email": email, "vai_tro": vai}


# ───────────────────────────── đọc tham số ─────────────────────────────
def hom_nay() -> datetime.date:
    return datetime.datetime.now(VN).date()


def doc_khoang(args: dict, hn: datetime.date, nhanh: dict | None = None
               ) -> tuple[datetime.date, datetime.date]:
    """Như `app._doc_khoang`: mặc định 30 ngày TRỌN tới hết hôm qua (giờ VN). `so_ngay` = N ngày
    trọn tới hết hôm qua. Chip nhanh có `so_ngay` (vd "Tiêu cực cần xử lý") thì như nút trên
    trang: N ngày tính tới HÔM NAY — chỉ khi người hỏi không nói kỳ."""
    hom_qua = hn - datetime.timedelta(days=1)
    tu_s, den_s = str(args.get("tu") or "").strip(), str(args.get("den") or "").strip()
    n = args.get("so_ngay")
    n = None if n in (None, "") else n
    if not tu_s and not den_s and n is None and nhanh and nhanh.get("so_ngay"):
        return hn - datetime.timedelta(days=int(nhanh["so_ngay"]) - 1), hn
    den = NL.ngay(den_s, hom_qua)
    if not tu_s and n is not None:
        try:
            n = int(n)
        except (TypeError, ValueError):
            raise NL.LoiNhap("`so_ngay` phải là số ngày.") from None
        if not 1 <= n <= KHOANG_TOI_DA_NGAY:
            raise NL.LoiNhap(f"`so_ngay` từ 1 tới {KHOANG_TOI_DA_NGAY}.")
        return den - datetime.timedelta(days=n - 1), den
    tu = NL.ngay(tu_s, den - datetime.timedelta(days=29))
    if tu > den:
        raise NL.LoiNhap("Ngày bắt đầu phải trước ngày kết thúc.")
    if (den - tu).days + 1 > KHOANG_TOI_DA_NGAY:
        raise NL.LoiNhap(f"Khoảng tối đa {KHOANG_TOI_DA_NGAY} ngày.")
    return tu, den


def tham_so_loc(bo_loc_vao, nhanh: dict | None = None) -> dict[str, str]:
    """`bo_loc` của model (chuỗi hoặc danh sách) → tham số URL như trình duyệt gửi; chip nhanh
    (nếu có) ghi đè các chiều của nó. Kiểm bằng `CS.doc_bo_loc` ở bên gọi."""
    q: dict[str, str] = {}
    for k, v in (bo_loc_vao or {}).items() if isinstance(bo_loc_vao, dict) else ():
        if k not in CS.CHIEU_LOC or v in (None, "", [], False):
            continue
        q[k] = ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)
    for k, v in ((nhanh or {}).get("loc") or {}).items():
        q[k] = str(v)
    return q


def link_dashboard(du_an: str, tu: datetime.date, den: datetime.date, bo_loc: dict | None,
                   duong: str = "/") -> str:
    """Link mở đúng màn hình: cùng tham số URL trang Chỉ số tự ghi (`chi_so.js` urlHienTai) —
    ngày ghi rõ để link vẫn đúng kỳ khi mở lại hôm sau."""
    q = {"du_an": du_an, "tu": tu.isoformat(), "den": den.isoformat()}
    for k, v in CS.bo_loc_json(bo_loc).items():
        if k == "pham_vi" and v == "tat_ca":
            continue
        if v in ("", [], None):
            continue
        q[k] = ",".join(v) if isinstance(v, list) else str(v)
    return DASHBOARD_URL + duong + "?" + urllib.parse.urlencode(q)


# ───────────────────────────── tính (đúng như /api/chi-so) ─────────────────────────────
def _moc_ngay(tu: datetime.date, den: datetime.date) -> tuple:
    return (datetime.datetime.combine(tu, datetime.time(0), VN),
            datetime.datetime.combine(den + datetime.timedelta(days=1), datetime.time(0), VN))


def _bai_cho_bl(kho, ma: str, bai: list, bl: list, co_chu: bool) -> dict:
    """Như `app._bai_cho_bl` (không nhớ đệm): bài gốc theo khoá cho bình luận khi bộ lọc có
    điều kiện cấp bài; bài đăng trước khoảng đã đọc thì đọc thêm theo khoá."""
    ds = CS.chi_muc_bai(bai)
    thieu = CS.khoa_bai_thieu(bl, ds)
    if thieu:
        ds.update(CS.chi_muc_bai(kho.bai_theo_khoa(ma, thieu, co_chu)))
    return ds


def tinh_chi_so(kho, du_an: dict, tu: datetime.date, den: datetime.date, bo_loc: dict,
                hn: datetime.date) -> dict:
    """Mọi khối số liệu của trang Chỉ số — ghép ĐÚNG như `tinh()` trong `/api/chi-so` của
    `dashboard/app.py` (cùng dòng đọc, cùng thứ tự, cùng tham số). Sửa endpoint đó thì sửa đây;
    `test_hoi_dashboard.py::test_khop_api_chi_so*` bắt mọi lệch."""
    ma = du_an["ma"]
    kq = kho.bai_trong_khoang(ma, *_moc_ngay(CS.khoang_truoc(tu, den)[0], den))
    kb = kho.binh_luan_trong_khoang(ma, *_moc_ngay(tu, den))
    kbt = kho.binh_luan_hop_le_gon(ma, *_moc_ngay(*CS.khoang_truoc(tu, den)))
    bai_khoa = None
    if CS.can_tra_bai(bo_loc):
        bai_khoa = _bai_cho_bl(kho, ma, kq["rows"], kb["rows"] + kbt["rows"], bool(bo_loc["q"]))
    tu_khoa_da = du_an.get("tu_khoa") or []
    f = CS.bien_dich(bo_loc)
    d = CS.tong_hop(kq["rows"], tu, den, tu_khoa_du_an=tu_khoa_da, hom_nay=hn, bo_loc=f)
    tk = CS.tu_khoa_thao_luan(kq["rows"], kb["rows"], tu, den, tu_khoa_du_an=tu_khoa_da,
                              bo_loc=f, bai_theo_khoa=bai_khoa)
    d["tu_khoa"], d["tu_khoa_tong"] = tk["tu_khoa"], tk["tong"]
    d["tu_khoa_an_mg"] = tk["an_minigame"]
    d["binh_luan_da_cao"] = CS.tong_hop_bl(kb["rows"], tu, den, hom_nay=hn, bo_loc=f,
                                           bai_theo_khoa=bai_khoa)
    d["y_dinh_mua"] = CS.y_dinh_mua(kb["rows"], tu, den, rows_truoc=kbt["rows"],
                                    truoc_bi_cat=bool(kbt["bi_cat"]),
                                    nay_bi_cat=bool(kb["bi_cat"]), hom_nay=hn, bo_loc=f,
                                    bai_theo_khoa=bai_khoa)
    d.update(CS.tong_quan_loc(kq["rows"], kb["rows"], tu, den, f, bai_khoa))
    d["bo_loc"] = CS.bo_loc_json(bo_loc)
    d["bi_cat"], d["bl_bi_cat"] = kq["bi_cat"], kb["bi_cat"]
    # Khủng hoảng = điều kiện của chip "Cảnh báo khủng hoảng" (tiêu cực + từ 1.000 tương tác)
    # AND bộ lọc đang hỏi, tính lại trên CÙNG các dòng đã đọc — không đọc kho thêm. Đang lọc sắc
    # thái khác (vd chỉ tích cực) thì không có gì để xét.
    if not bo_loc["sac_thai"] or CS.TI in bo_loc["sac_thai"]:
        loc_kh = CS.doc_bo_loc(next(x for x in CS.BO_LOC_NHANH if x["ma"] == "khung_hoang")["loc"])
        kh = {**bo_loc, "sac_thai": loc_kh["sac_thai"],
              "tuong_tac": max(bo_loc["tuong_tac"], loc_kh["tuong_tac"])}
        k2 = CS.tong_hop(kq["rows"], tu, den, tu_khoa_du_an=tu_khoa_da, hom_nay=hn, bo_loc=kh)
        d["_khung_hoang"] = {"bo_loc": kh, "kpi": k2["kpi"], "top_bai": k2["top_bai"]}
    del kq, kb, kbt, bai_khoa
    top = d["y_dinh_mua"]["top_bai"]
    if top:
        CS.gan_ngu_canh_y_dinh(top, kho.ngu_canh_bai(ma, [x["khoa_bai"] for x in top]))
    return d


_nho: collections.OrderedDict = collections.OrderedDict()
_KHOA_NHO = threading.Lock()


def _tinh_co_nho(kho, du_an: dict, tu, den, bo_loc: dict, hn) -> dict:
    """`tinh_chi_so` nhớ `NHO_GIAY` giây theo bộ lọc + mốc lượt quét vừa xong (như app): Mark hỏi
    tiếp phần khác của cùng kỳ thì không đọc lại 20k bài."""
    try:
        x = kho.luot_xong_moi_nhat() or {}
    except Exception:  # noqa: BLE001 — không có mốc thì vẫn tính, chỉ không nhớ
        x = None
    khoa = None
    if x is not None:
        khoa = (du_an["ma"], tu, den, CS.khoa_bo_loc(bo_loc), hn,
                tuple(du_an.get("tu_khoa") or []), x.get("id"), str(x.get("ket_thuc")))
        with _KHOA_NHO:
            v = _nho.get(khoa)
            if v and time.monotonic() - v[0] < NHO_GIAY:
                _nho.move_to_end(khoa)
                return v[1]
    d = tinh_chi_so(kho, du_an, tu, den, bo_loc, hn)
    if khoa is not None:
        with _KHOA_NHO:
            _nho[khoa] = (time.monotonic(), d)
            while len(_nho) > NHO_TOI_DA:
                _nho.popitem(last=False)
    return d


# ───────────────────────────── rút gọn cho model ─────────────────────────────
def _chu(s, n: int = CHU_TOI_DA) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _gio(x) -> str | None:
    if isinstance(x, datetime.datetime):
        if x.tzinfo is None:
            x = x.replace(tzinfo=datetime.UTC)
        return x.astimezone(VN).isoformat(timespec="minutes")
    return None if x is None else str(x)


def _bai_gon(b: dict) -> dict:
    """Thẻ bài như dashboard hiện (tên tài khoản đăng bài công khai, không ai bình luận)."""
    ra = {"link": b.get("link") or "", "nen_tang": CS.TEN_NEN_TANG.get(b.get("nen_tang"),
                                                                        b.get("nen_tang")),
          "tac_gia": b.get("tac_gia") or "", "dang_luc": b.get("dang_luc"),
          "loai_nguon": b.get("loai"), "sac_thai": b.get("sac_thai"),
          "chu_de": b.get("chu_de") or "", "thao_luan": b.get("thao_luan"),
          "xem": b.get("xem"), "thich": b.get("thich"), "binh_luan": b.get("binh_luan"),
          "chia_se": b.get("chia_se"), "noi_dung": _chu(b.get("noi_dung"))}
    if b.get("kieu_trang"):
        ra["kieu_trang"] = CS.KIEU_TRANG.get(b["kieu_trang"], b["kieu_trang"])
    return ra


def _sac_bai(k: dict) -> dict:
    return {"da_phan_loai": k["da_phan_loai"], "chua_phan_loai": k["chua_phan_loai"],
            "tich_cuc": k["tich_cuc"], "tieu_cuc": k["tieu_cuc"], "trung_lap": k["trung_lap"],
            "tich_cuc_pt": k["tich_cuc_pt"], "tieu_cuc_pt": k["tieu_cuc_pt"],
            "trung_lap_pt": k["trung_lap_pt"]}


def _cd(g: dict) -> dict:
    return {"chu_de": g["chu_de"], "so": g["so"], "tich_cuc": g[CS.TC], "tieu_cuc": g[CS.TI],
            "trung_lap": g[CS.TL], "chua_phan_loai": g[CS.CHUA]}


def rut_gon(d: dict, phan: list[str], top: int) -> dict:
    """Các phần số liệu được hỏi, mỗi danh sách cắt `top` dòng."""
    k, ss = d["kpi"], d["so_sanh"]
    bl = d["binh_luan_da_cao"]
    yd = d["y_dinh_mua"]
    ra: dict = {}
    if "tong_quan" in phan:
        ra["tong_quan"] = {
            "kpi": {x: k[x] for x in ("bai", "thao_luan", "binh_luan", "xem", "tuong_tac",
                                      "nguon_co_bai", "bai_khu_trung", "bai_kenh_nha")},
            "so_voi_ky_truoc": ss,
            "so_sanh_tat": ({"ly_do": "đang lọc theo mức tương tác — tương tác cộng dồn theo tuổi "
                                       "bài nên % so kỳ trước không công bằng, dashboard không hiện"}
                            if d.get("so_sanh_lech") else None),
            "sac_thai_bai": _sac_bai(k),
            "binh_luan_da_cao": {x: bl["kpi"][x] for x in ("so", "sach", "da_loc", "thuong_hieu",
                                                           "tich_cuc_pt", "tieu_cuc_pt",
                                                           "trung_lap_pt")},
            "y_dinh_mua": {x: yd[x] for x in ("so", "sach", "pt", "truoc", "doi_pt", "moi")},
            "dinh_thao_luan": d["xu_huong"]["dinh"],
            "web": k["web"],
        }
    if "xu_huong" in phan:
        x = d["xu_huong"]
        ra["xu_huong"] = {"don_vi": x["don_vi"], "dinh": x["dinh"],
                          "chuoi": [{"moc": m, "bai": b, "thao_luan": t, "tieu_cuc": ti}
                                    for m, b, t, ti in zip(x["moc"], x["bai"], x["thao_luan"],
                                                           x["tieu_cuc"])]}
    if "sac_thai" in phan:
        kt = d["kpi_truoc"]
        ra["sac_thai"] = {
            "bai_external": _sac_bai(k), "bai_ky_truoc": _sac_bai(kt),
            "ghi_chu": "Sắc thái chỉ tính bài External channel (bài kênh nhà là tiếng brand).",
            "binh_luan_hop_le": {x: bl["kpi"][x] for x in (
                "da_phan_loai", "tich_cuc", "tieu_cuc", "trung_lap", "chua_phan_loai",
                "tich_cuc_pt", "tieu_cuc_pt", "trung_lap_pt")}}
    if "chu_de" in phan:
        ra["chu_de"] = {"bai": [_cd(g) for g in d["sac_thai_chu_de"][:top]],
                        "so_chu_de_bai": len(d["sac_thai_chu_de"]),
                        "binh_luan": [_cd(g) for g in bl["chu_de"][:top]],
                        "so_chu_de_bl": len(bl["chu_de"])}
    if "tu_khoa" in phan:
        ra["tu_khoa"] = {
            "cum": [{"tu": g["tu"], "thao_luan": g["so_bai"], "sac_noi_troi": g["mau"],
                     **({"mot_bai_pt": g["mot_bai_pt"]} if g.get("mot_bai_pt") else {})}
                    for g in d["tu_khoa"][:top]],
            "tong_thao_luan_xet": d["tu_khoa_tong"], "an_minigame": d["tu_khoa_an_mg"],
            "ghi_chu": "`mot_bai_pt` = phần trăm thảo luận của cụm nằm dưới MỘT bài."}
    if "nguon" in phan:
        ra["nguon"] = {
            "theo_nen_tang": [{"nen_tang": p["ten_nen_tang"], "so_nguon": p["so_nguon"],
                               "top": [{x: g[x] for x in ("ten", "ten_loai", "bai", "thao_luan",
                                                          "xem", "followers", "link",
                                                          "khoa_nguon")}
                                       for g in p["nguon"][:top]]}
                              for p in d["top_nguon"]],
            "nen_tang": d["nen_tang"], "loai_nguon": d["loai_nguon"]}
    if "bai" in phan:
        ra["bai"] = {"top": [_bai_gon(b) for b in d["top_bai"][:top]],
                     "xep_theo": "thảo luận (bài + bình luận nền tảng báo)"}
    if "binh_luan" in phan:
        ra["binh_luan"] = {"kpi": bl["kpi"], "theo_loai": bl["loai"],
                           "ghi_chu": "Mẫu bình luận Mark đã cào, không phải toàn bộ bình luận "
                                      "nền tảng báo; sắc thái/chủ đề chỉ trên bình luận hợp lệ."}
    if "y_dinh_mua" in phan:
        ra["y_dinh_mua"] = {**{x: yd[x] for x in ("so", "sach", "pt", "truoc", "doi_pt", "moi",
                                                  "theo_chu_de", "theo_cau", "ngoai_brand")},
                            "theo_mon": [{"mon": x["ten"], "ma": x["ma"], "so": x["so"]}
                                         for x in yd["theo_san_pham"]],
                            "dang_loc_mon": yd["san_pham_loc"],
                            "top_bai": [{"link": x["link"], "tac_gia": x["tac_gia"],
                                         "nen_tang": x["nen_tang"], "so": x["so"],
                                         "sach": x["sach"], "noi_dung": _chu(x["noi_dung"]),
                                         "mon_hoi_nhieu": x["ten_san_pham"]}
                                        for x in yd["top_bai"][:top]],
                            "ghi_chu": "Món do AI xếp theo bình luận + nội dung bài; chưa xếp "
                                       "thì theo tên món trong bình luận, không nói tên = Chưa "
                                       "rõ món. KHÔNG mặc định khách hỏi túi. `ngoai_brand` = "
                                       "số câu hỏi mua đồ không phải của brand (không tính)."}
    if "web" in phan:
        ra["web"] = k["web"] or {"bai": 0, "ghi_chu": "Không có bài Báo & Web trong kỳ/bộ lọc."}
    if "nha_ngoai" in phan:
        ra["nha_ngoai"] = {CS.TEN_KENH_NHA: d["nha_ngoai"]["kenh_nha"],
                           CS.TEN_BEN_NGOAI: d["nha_ngoai"]["ben_ngoai"]}
    if "khung_hoang" in phan:
        kh = d.get("_khung_hoang")
        if kh is None:
            ra["khung_hoang"] = {"ghi_chu": "Bộ lọc đang hỏi loại trừ tiêu cực — không xét."}
        else:
            ra["khung_hoang"] = {
                "dinh_nghia": "Bài tiêu cực có từ "
                              f"{so_vn(kh['bo_loc']['tuong_tac'])} tương tác (chip "
                              "\"Cảnh báo khủng hoảng\" của dashboard)",
                "so_bai": kh["kpi"]["bai"], "thao_luan": kh["kpi"]["thao_luan"],
                "top_bai": [_bai_gon(b) for b in kh["top_bai"][:top]],
                "tieu_cuc_pt": {"nay": k["tieu_cuc_pt"], "ky_truoc": d["kpi_truoc"]["tieu_cuc_pt"]},
                "bl_tieu_cuc_pt": bl["kpi"]["tieu_cuc_pt"]}
    if "bo_loc" in phan:
        dem = d["bo_loc_dem"]
        ra["bo_loc"] = {
            "nen_tang": dem["nen_tang"], "loai": dem["loai"], "pham_vi": dem["pham_vi"],
            "sac_thai": dem["sac_thai"], "anh_huong": dem["anh_huong"],
            "kieu_trang": dem["kieu_trang"],
            "chu_de": [{x: g[x] for x in ("gia_tri", "so_bai", "so_bl")}
                       for g in dem["chu_de"][:20]],
            "nguon": [{x: g[x] for x in ("gia_tri", "ten", "nen_tang", "so")}
                      for g in dem["nguon"][:20]],
            "ghi_chu": "Số mỗi ô tính trên mục khớp mọi chiều KHÁC của bộ lọc (như ô lọc trên "
                       "trang). Lọc theo nguồn: đưa `gia_tri` vào bo_loc.nguon."}
    return ra


def so_vn(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def _chi_phi(kho, du_an: dict, quan_ly: bool, top: int, bay_gio) -> dict:
    """Như trang Ngân sách (`app.trang_ngan_sach`) cho MỘT dự án + các lượt quét gần nhất."""
    ma = du_an["ma"]
    tieu = float((kho.da_tieu_thang() or {}).get(ma, 0.0))
    tran_pf = kho.tran_platform(ma)
    nguon = kho.cac_nguon(ma)
    db = CP.du_bao(nguon, tieu, float(du_an.get("tran_usd_thang") or 0), tran_pf, bay_gio)
    try:
        cac_lich = kho.cac_lich(ma)
    except Exception as e:      # bảng lịch chưa có: như trang, coi như không có lịch
        if not _loi_kho(e):
            raise
        cac_lich = []
    tq = TL.tong_quan(cac_lich, du_an, nguon, tieu, tran_pf, bay_gio)
    luot, tong = kho.cac_luot(ma, 1, min(top, LUOT_TOI_DA))
    return {
        "thang": bay_gio.strftime("%m/%Y"),
        "da_tieu_usd": round(tieu, 4), "tran_usd": db["tran"],
        "tran_du_an_usd": db["tran_du_an"], "tran_platform_usd": db["tran_platform"],
        "con_lai_theo_nguon_usd": db["con_lai"], "du_bao_thang_usd": db["du_bao_thang"],
        "vuot_tran": db["vuot"], "vuot_usd": db["vuot_usd"],
        "pt_da_tieu": round(min(100.0, 100.0 * tieu / db["tran"]), 1) if db["tran"] else None,
        "nguon_ton_nhat": [{x: n[x] for x in ("ten", "nen_tang", "chu_ky_ngay", "thang_usd")}
                           for n in db["top_ton"]],
        # Có lịch quét tự động đang bật: cả tháng = đã tiêu + nguồn theo chu kỳ + lịch (tab Lịch).
        "theo_lich": ({x: tq[x] for x in ("luot", "usd_lich", "tong", "tran", "vuot", "chenh")}
                      if tq.get("co_lich") else {"co_lich": False}),
        "tong_luot_quet": tong,
        "luot_gan_nhat": [{
            "id": r.get("id"), "kieu": r.get("kieu"), "trang_thai": r.get("trang_thai"),
            "bat_dau": _gio(r.get("bat_dau")), "ket_thuc": _gio(r.get("ket_thuc")),
            "bai_moi": r.get("bai_moi"), "bai_cap_nhat": r.get("bai_cap_nhat"),
            "so_nguon": r.get("so_nguon"), "so_nguon_loi": r.get("so_nguon_loi"),
            "chi_phi_usd": r.get("chi_phi_usd"),
            "loi": (r.get("loi") if quan_ly else (LOI_CHUNG if r.get("loi") else None))}
            for r in luot],
        "ghi_chu": "Dự báo là mức TỐI ĐA nếu mọi lượt dùng hết phần giữ chỗ; tiền thật là "
                   "`da_tieu_usd` (lượt theo dõi trong tháng, giờ VN).",
    }


def _lich(kho, du_an: dict, quan_ly: bool, bay_gio) -> dict:
    """Như tab Lịch quét: danh sách + tổng quan tháng (`dashboard.trang_lich`)."""
    ma = du_an["ma"]
    try:
        cac = kho.cac_lich(ma)
    except Exception as e:      # chỉ nuốt lỗi kho; lỗi khác là lỗi code, ném tiếp
        if not _loi_kho(e):
            raise
        return {"co_lich": False, "ghi_chu": "Chưa đọc được bảng lịch quét."}
    nguon = kho.cac_nguon(ma)
    tieu = float((kho.da_tieu_thang() or {}).get(ma, 0.0))
    ds = TL.dong_lich(cac, du_an, nguon, bay_gio, quan_ly, LOI_CHUNG)
    tq = TL.tong_quan(cac, du_an, nguon, tieu, kho.tran_platform(ma), bay_gio)
    return {"tong_quan_thang": tq, "lich": [{
        "id": x.get("id"), "ten": x.get("ten") or x.get("mo_ta"), "kieu": x.get("kieu_ten"),
        "mo_ta": x.get("mo_ta"), "trang_thai": x.get("tt_nhan"), "moc_ke": x.get("ke_chu"),
        "con": x.get("ke_con"), "tre": x.get("tre"), "luot_30_ngay": x.get("luot_30"),
        "usd_30_ngay": x.get("usd_30"), "so_lan_chay": x.get("so_lan_chay"),
        "ket_qua_gan_nhat": ({y: (x["kq"].get(y) if y != "luc" else _gio(x["kq"].get(y)))
                              for y in ("nhan", "chi_tiet", "luc")} if x.get("kq") else None)}
        for x in ds]}


def _do_phu(kho, ma: str, bay_gio) -> dict:
    """Thẻ "Độ phủ" (kiểm hằng tuần) — chỉ khi bản dashboard + kho đã có (17/10/2026)."""
    ham, json_fn = getattr(kho, "do_phu_gan_nhat", None), getattr(CS, "do_phu_json", None)
    if ham is None or json_fn is None:
        return {"co": False, "ghi_chu": "Dashboard bản này chưa có kiểm độ phủ."}
    try:
        x = json_fn(ham(ma), bay_gio)
    except Exception as e:  # noqa: BLE001 — bảng chưa tạo: như trang, không có thẻ
        print(f"[hoi_dashboard] độ phủ lỗi: {type(e).__name__}")
        return {"co": False, "ghi_chu": "Chưa đọc được kết quả kiểm độ phủ."}
    if not x:
        return {"co": False, "ghi_chu": "Dự án chưa có lượt kiểm độ phủ nào."}
    return {"co": True, **x}


# ───────────────────────────── tool ─────────────────────────────
def _chon_du_an(ds: list[dict], ma: str) -> dict | None:
    """Như `app._chon_du_an`: không nói dự án thì dự án đang bật đầu tiên."""
    if ma:
        return next((d for d in ds if d["ma"] == ma), None)
    return next((d for d in ds if d.get("dang_bat")), ds[0] if ds else None)


def tra_loi(args: dict, kho=None, *, open_id: str | None = None,
            bay_gio: datetime.datetime | None = None) -> dict:
    """Lõi của tool (bài thử gọi thẳng với kho giả). Ném TuChoi / NL.LoiNhap / CS.LoiBoLoc."""
    kho = kho or _kho_mac_dinh()
    nguoi = kiem_quyen(kho, open_id if open_id is not None else nguoi_hoi())
    quan_ly = nguoi["vai_tro"] == "quan_ly"
    bay_gio = bay_gio or datetime.datetime.now(VN)
    hn = bay_gio.astimezone(VN).date()
    args = args or {}
    ds = kho.cac_du_an()
    ma = str(args.get("du_an") or "").strip()
    du_an_ngan = _chon_du_an(ds, ma)
    cac_du_an = [{"ma": d["ma"], "ten": d["ten"], "dang_bat": bool(d.get("dang_bat"))} for d in ds]
    if du_an_ngan is None:
        raise NL.LoiNhap(f"Không có dự án “{ma}” trên dashboard. Dự án đang có: "
                         + (", ".join(f"{d['ma']} ({d['ten']})" for d in ds) or "chưa có") + ".")
    du_an = kho.doc_du_an(du_an_ngan["ma"]) or du_an_ngan
    nhanh = None
    if args.get("bo_loc_nhanh"):
        nhanh = next((x for x in CS.BO_LOC_NHANH if x["ma"] == args["bo_loc_nhanh"]), None)
        if nhanh is None:
            raise NL.LoiNhap("Chip lọc nhanh không có: " + ", ".join(
                x["ma"] for x in CS.BO_LOC_NHANH) + ".")
    tu, den = doc_khoang(args, hn, nhanh)
    bo_loc = CS.doc_bo_loc(tham_so_loc(args.get("bo_loc"), nhanh))
    phan = [p for p in (args.get("phan") or []) if p in PHAN] or list(PHAN_MAC_DINH)
    try:
        top = min(max(1, int(args.get("so_dong") or TOP_MAC_DINH)), TOP_TOI_DA)
    except (TypeError, ValueError):
        top = TOP_MAC_DINH
    hom_qua = hn - datetime.timedelta(days=1)
    ra: dict = {
        "du_an": {"ma": du_an["ma"], "ten": du_an["ten"]}, "cac_du_an": cac_du_an,
        "khoang": {"tu": tu.isoformat(), "den": den.isoformat(), "so_ngay": (den - tu).days + 1,
                   "ky_truoc": dict(zip(("tu", "den"),
                                        (x.isoformat() for x in CS.khoang_truoc(tu, den)))),
                   "mac_dinh": (tu, den) == (hom_qua - datetime.timedelta(days=29), hom_qua),
                   "hom_nay": hn.isoformat()},
        "bo_loc": {k: v for k, v in CS.bo_loc_json(bo_loc).items()
                   if v not in ("", [], "tat_ca")},
        "link": link_dashboard(du_an["ma"], tu, den, bo_loc),
        "vai_tro_nguoi_hoi": nguoi["vai_tro"],
        "canh_bao": [],
    }
    if nhanh:
        ra["bo_loc_nhanh"] = nhanh["ten"]
    if den >= hn:
        ra["canh_bao"].append("Kỳ có ngày hôm nay (chưa hết ngày): số còn tăng, so với kỳ trước "
                              "thường thấp giả.")
    if set(phan) & _PHAN_SO_LIEU:
        d = _tinh_co_nho(kho, du_an, tu, den, bo_loc, hn)
        ra["phan"] = rut_gon(d, phan, top)
        if d.get("bi_cat"):
            ra["canh_bao"].append("Kỳ quá nhiều bài: dashboard chỉ đọc 20.000 bài mới nhất (gồm kỳ "
                                  "trước) — số đầu kỳ/kỳ trước thiếu, % so sánh không đáng tin.")
        if d.get("bl_bi_cat"):
            ra["canh_bao"].append("Kỳ quá nhiều bình luận: chỉ đọc 50.000 bình luận mới nhất.")
        if "khung_hoang" in phan and d.get("_khung_hoang"):
            ra["link_khung_hoang"] = link_dashboard(du_an["ma"], tu, den,
                                                    d["_khung_hoang"]["bo_loc"])
        k = d["kpi"]
        if k["chua_phan_loai"]:
            ra["canh_bao"].append(f"{so_vn(k['chua_phan_loai'])} bài External chưa có nhãn sắc "
                                  "thái — % tính trên bài đã phân loại.")
    else:
        ra["phan"] = {}
    try:
        g = kho.tien_do_gan_nhan(du_an["ma"])
    except Exception:  # noqa: BLE001 — dòng phụ, như trang
        g = None
    if g and (g.get("cho_bl") or g.get("cho_bai")):
        ra["canh_bao"].append(f"AI còn đang gán nhãn: {so_vn(g.get('cho_bai'))} bài và "
                              f"{so_vn(g.get('cho_bl'))} bình luận chờ — sắc thái/chủ đề sẽ còn đổi.")
    if "chi_phi" in phan:
        ra["phan"]["chi_phi"] = _chi_phi(kho, du_an, quan_ly, top, bay_gio)
        ra["link_ngan_sach"] = f"{DASHBOARD_URL}/ngan-sach?" + urllib.parse.urlencode(
            {"du_an": du_an["ma"]})
    if "lich" in phan:
        ra["phan"]["lich"] = _lich(kho, du_an, quan_ly, bay_gio)
        ra["link_lich_quet"] = f"{DASHBOARD_URL}/lich-quet?" + urllib.parse.urlencode(
            {"du_an": du_an["ma"]})
    if "do_phu" in phan:
        ra["phan"]["do_phu"] = _do_phu(kho, du_an["ma"], bay_gio)
    ra["ghi_chu"] = ("Số tính bằng đúng code của dashboard. % đổi = so với kỳ liền trước cùng độ "
                     "dài (`ky_truoc`); `doi_pt` null = kỳ trước 0 (\"mới\" nếu kỳ này có) hoặc "
                     "dashboard tắt so sánh. \"Thảo luận\" = bài + bình luận nền tảng báo trên các "
                     "bài đó (như Kompa), không phải toàn bộ mạng xã hội.")
    return ra


def _danh_dau_han_che() -> None:
    """Câu trả lời mang số nội bộ: Platform ẩn khỏi bản ghi hội thoại của người dưới moderator
    (cùng cơ chế `chi_so_ads`; tên tool lạ Platform vẫn coi là hạn chế)."""
    try:
        import lsr_platform
        lsr_platform.danh_dau_han_che("hoi_dashboard")
        memory_store.danh_dau_phien_han_che(scheduler.get_current_chat() or "", "hoi_dashboard")
    except Exception as e:  # noqa: BLE001
        print(f"[hoi_dashboard] gắn cờ hạn chế lỗi: {type(e).__name__}")


def _handle(args: dict, **_kw) -> str:
    try:
        ra = tra_loi(args or {})
    except TuChoi as e:
        return tool_error(str(e))
    except (NL.LoiNhap, CS.LoiBoLoc) as e:
        return tool_error(f"Tham số chưa hợp lệ: {e}")
    except Exception as e:  # noqa: BLE001
        if _loi_kho(e):
            return tool_error(f"Chưa đọc được kho lắng nghe ({e}). Nói rõ với người hỏi là chưa "
                              f"có số, đừng đoán; họ vẫn mở được {DASHBOARD_URL}.")
        print(f"[hoi_dashboard] lỗi: {type(e).__name__}: {str(e)[:200]}")
        return tool_error(f"Đọc số liệu dashboard lỗi ({type(e).__name__}). Nói rõ là chưa có số, "
                          "đừng đoán.")
    _danh_dau_han_che()
    return tool_result(json.loads(json.dumps(ra, ensure_ascii=False, default=str)))


def register() -> None:
    try:
        registry.register(
            name="hoi_dashboard", toolset="lark_api", schema=SCHEMA, handler=_handle,
            check_fn=lambda: True, requires_env=[], is_async=False,
            description="Hỏi đáp số liệu dashboard lắng nghe social.hapas.vn",
            emoji="\U0001f4ca", override=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[hoi_dashboard] register warning: {e}")


register()
