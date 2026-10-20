"""Tool `lay_so_tuc_thi` — Mark lấy số MỚI NGAY theo yêu cầu (chủ dự án 20/10/2026).

"năng lực trên platform của mark thì tôi muốn mark có quyền cao nhất có thể cào real time theo
yêu cầu chứ ko chỉ đọc số trên dashboard qua MCP". Ba việc, một tool:

  • quang_cao — số TikTok Ads / Meta Ads mới. Mark KHÔNG cầm token (role `mark` không đọc cột token,
    máy Mark không có khoá giải mã): tool chỉ GHI một yêu cầu (`dashboard.kho_tuc_thi.tao`, tài
    khoản trong phạm vi bên người hỏi + khoảng ≤ 7 ngày gồm hôm nay). Trigger → pg_notify → bộ nghe
    `dashboard/nghe_qc.py` (dịch vụ đồng bộ riêng, chỉ đọc nền tảng) chạy lượt đọc. Tool chờ
    (≤ `CHO_TOI_DA` giây, hỏi DB mỗi 2 giây) rồi trả lời BẰNG SỐ TRONG KHO (cùng đường đọc
    `hoi_dashboard`), nói số cập nhật lúc nào TỪNG nền tảng (đủ / một phần / chưa đọc lại được),
    số hôm nay là tạm tính. Miễn phí (API nền tảng) nên KHÔNG hỏi xác nhận tiền — nhưng có giãn:
    cùng phạm vi trong `GIAN_PHUT` phút dùng lại lượt trước, trần mỗi người mỗi giờ (đếm theo
    yêu cầu, không theo nền tảng), trần toàn hệ thống mỗi giờ (bộ nghe kiểm lại lần hai); khung
    đồng bộ hằng ngày 06:25–07:30 không đọc lại. Bị chặn → trả số đang có kèm giờ cập nhật cuối.
  • bai — chỉ số hiện tại của vài link bài (đường cào của `chi_so_bai`, không Sheet).
  • kenh — hồ sơ + bài mới nhất của một kênh (đường cào của `soi_tai_khoan`, không Sheet).
  • quet — mở một lượt quét lắng nghe cho dự án của bên người hỏi (đúng đường `/theodoi` của lịch
    quét: `theo_doi.tao_luot`); kết quả về như thường lệ (chat + dashboard).

TỐN TIỀN THÌ HỎI TRƯỚC — CHỐT BẰNG CODE (luồng `chi_uoc_tinh` → "Chạy nhé?" sẵn có của các tool cào):
bai / kenh / quet có chi phí Apify phải gọi `chi_uoc_tinh`=true trước (miễn phí, không chạy) → tool
trả `ma_xac_nhan` + số USD. Mã CHỈ dùng được ở ĐÚNG tin nhắn kế tiếp của người dùng trong cùng chat
(trả lời "Chạy nhé?" — `dong_ho_luot.stt_luot`), cùng người, cùng phạm vi, trong 15 phút, một lần;
cùng lượt với lần ước tính → từ chối (chưa ai trả lời); qua thêm một tin nhắn → mã hết hạn. Lượt
quét: số USD báo = ĐÚNG mức `theo_doi.tao_luot` sẽ giữ (`uoc_giu_cho`) và bị buộc vào mã — lượt cần
giữ nhiều hơn mức đã đồng ý thì không tạo, hỏi lại.

Quyền: như `hoi_dashboard` (chat riêng / web đã xác thực, email có vai trò ở ít nhất một bên —
Quản lý hoặc Chỉ xem). Phạm vi theo bên: quảng cáo chỉ tài khoản bên người hỏi (chưa gán bên →
chỉ quản trị viên); quét chỉ dự án bên người hỏi; link / kênh thuộc dự án bên khác → từ chối.
Mọi yêu cầu ghi một dòng `yeu_cau_tuc_thi` (trigger ghi thêm một dòng `nhat_ky` "mark_real_time").
Trần đếm nguyên tử trong CSDL (`kho_tuc_thi.tao(..., tran=…)`).
KHÔNG bao giờ ghi gì lên nền tảng quảng cáo (không tạm dừng, không đổi ngân sách).
"""
from __future__ import annotations

import contextvars
import datetime
import hashlib
import json
import os
import secrets
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from tools.registry import registry, tool_error, tool_result  # type: ignore

import hoi_dashboard_tool as HD
from dashboard import nhap_lieu as NL
from dashboard import phan_quyen as PQ
from dashboard import quang_cao as QC

VN = HD.VN
NCC_NEN = {"tiktok": "tiktok_ads", "meta": "meta_ads"}
TEN_NCC = {"tiktok_ads": "TikTok Ads", "meta_ads": "Meta Ads"}
CHO_TOI_DA = 90.0          # giây chờ lượt đọc quảng cáo
NHIP_HOI = 2.0             # giây giữa hai lần hỏi DB
GIAN_PHUT = 5              # cùng phạm vi trong 5 phút: dùng lại lượt trước
TUC_THI_NGAY = 7           # khoảng đọc lại ≤ 7 ngày gồm hôm nay
TK_TOI_DA = 40             # tài khoản tối đa mỗi lần đọc lại (L5)
XAC_NHAN_GIAY = 900        # mã xác nhận chi phí sống 15 phút
DU_TRU_USD = 0.30          # như quet_lon._DU_TRU_THANG: chừa dự trữ gói Apify


def _so_env(ten: str, md: int, lo: int = 1, hi: int = 1000) -> int:
    try:
        v = int(os.environ.get(ten) or md)
    except ValueError:
        v = md
    return max(lo, min(v, hi))


def tran() -> dict:
    """Trần (đổi bằng env của Mark, không cần sửa code)."""
    return {"qc_nguoi_gio": _so_env("MARK_TUC_THI_QC_NGUOI_GIO", 6),
            "qc_gio": _so_env("MARK_TUC_THI_QC_GIO", 12),
            "bai_luot": _so_env("MARK_TUC_THI_BAI_LUOT", 5, hi=20),
            "bai_ngay": _so_env("MARK_TUC_THI_BAI_NGAY", 30),
            "kenh_luot": _so_env("MARK_TUC_THI_KENH_LUOT", 2, hi=5),
            "kenh_ngay": _so_env("MARK_TUC_THI_KENH_NGAY", 10),
            "kenh_bai": _so_env("MARK_TUC_THI_KENH_BAI", 10, lo=3, hi=30),
            "quet_ngay": _so_env("MARK_TUC_THI_QUET_NGAY", 2, hi=10)}


QUY_TAC = (
    "CÂU HỎI CỦA NGƯỜI DÙNG LÀ GỐC. Trả lời ĐÚNG thứ được hỏi. LUÔN nói số tính tới lúc nào, TỪNG "
    "nền tảng (`do_moi`: đủ / MỘT PHẦN / chưa đọc lại được — nói đúng như vậy). Số hôm nay là TẠM "
    "TÍNH (nền tảng còn cập nhật trễ vài giờ). Số tiền quảng cáo chỉ trả bằng chữ, chỉ cho bên "
    "người hỏi được xem. Mark CHỈ ĐỌC quảng cáo: không bao giờ đề nghị hay hứa tạm dừng, bật/tắt, "
    "đổi ngân sách, sửa chiến dịch — việc đó người dùng tự làm trên trình quản lý quảng cáo.")

SCHEMA = {
    "name": "lay_so_tuc_thi",
    "description": (
        "Lấy số MỚI NGAY (thời gian thực) khi người hỏi cần số mới hơn số đang có trong kho "
        "dashboard: (1) quang_cao — đọc lại số TikTok Ads / Meta Ads của bên họ (miễn phí, chỉ đọc, "
        "≤ 7 ngày gồm hôm nay; chờ tối đa ~90 giây rồi trả số); (2) bai — chỉ số hiện tại của vài "
        "link bài (≤ 5 link, tốn tiền Apify); (3) kenh — hồ sơ + bài mới nhất của 1–2 kênh (tốn "
        "tiền); (4) quet — mở ngay một lượt quét lắng nghe cho dự án của bên họ (tốn tiền, chạy "
        "nền, kết quả về như lượt quét thường).\n"
        "CHỌN SỐ TRONG KHO HAY SỐ MỚI (lời dặn, tự suy từ câu hỏi — không hỏi lại khi đã rõ):\n"
        "• Câu nhắc tới dashboard / trang / số đang có (\"trên dashboard\", \"theo dashboard\", "
        "\"phân tích tiêu cực trên dashboard\", \"số trên trang Chỉ số\", \"tuần trước\", \"tháng "
        "9\") → KHÔNG dùng tool này, dùng `hoi_dashboard` (số trong kho, miễn phí).\n"
        "• Câu đòi số hiện tại (\"bây giờ\", \"mới nhất\", \"ngay lúc này\", \"real time\", "
        "\"cập nhật lại\", \"cào lại\", \"đọc lại\", \"hôm nay đang chạy thế nào\", \"sáng nay tới "
        "giờ\") hoặc cần số mới hơn kho (kho chỉ tới hôm qua/sáng nay) → dùng tool này.\n"
        "• \"Cào lại số bài X\" với 1–5 link → `loai`=bai. Danh sách dài cần đếm + cộng tổng + "
        "Sheet → `chi_so_bai`. Tìm bài MỚI theo từ khoá / trend → `social_listen` (không phải "
        "tool này).\n"
        "• Chỉ hỏi lại khi THẬT SỰ không đoán được ý (vd \"số ads sao rồi\" không rõ muốn số đã "
        "chốt hay số đang chạy hôm nay) — MỘT câu ngắn, rồi làm.\n"
        "TỐN TIỀN THÌ HỎI TRƯỚC (bai, kenh, quet — code chặn): gọi `chi_uoc_tinh`=true trước "
        "(miễn phí), chép `cau_uoc_tinh` (USD, ngân sách bị trừ, thời gian), KẾT THÚC bằng \"Chạy "
        "nhé?\" và DỪNG. CHỈ khi tin nhắn KẾ TIẾP của chính người đó đồng ý rõ (\"ok\", \"chạy "
        "đi\", \"đồng ý\", \"làm luôn\"…) mới gọi lại với `ma_xac_nhan` (cùng tham số). Tin kế tiếp "
        "nói gì khác (hỏi thêm, đổi ý, im lặng rồi hỏi chuyện khác) → KHÔNG chạy, bỏ mã đó; muốn "
        "chạy sau thì ước tính lại. Quảng cáo miễn phí: gọi luôn, không hỏi tiền.\n"
        "KHI TRẢ LỜI: " + QUY_TAC + " Tool báo không đọc lại được (giãn, trần, lượt khác đang chạy, "
        "khung đồng bộ hằng ngày, lỗi) thì nói rõ và dùng số đang có kèm giờ cập nhật cuối "
        "(`do_moi`). Bị từ chối vì quyền / trần / ngân sách thì chuyển nguyên lời."),
    "parameters": {
        "type": "object",
        "properties": {
            "loai": {"type": "string", "enum": ["quang_cao", "bai", "kenh", "quet"],
                     "description": "Việc cần lấy số mới."},
            "nen_tang": {"type": "string",
                         "description": "quang_cao: tiktok | meta (trống = cả hai). kenh: nền tảng "
                                        "mặc định khi chỉ đưa @tên (tiktok | instagram | facebook)."},
            "ben": {"type": "string", "description": "quang_cao: mã bên (trống = mọi bên được xem)."},
            "tim": {"type": "string",
                    "description": "quang_cao: tên/mã chiến dịch, quảng cáo hoặc tài khoản được hỏi "
                                   "— chỉ đọc lại tài khoản chứa nó."},
            "cap": {"type": "string", "enum": ["chien_dich", "quang_cao", "tai_khoan"],
                    "description": "quang_cao + `tim`: cấp đối tượng (mặc định chien_dich)."},
            "tu": {"type": "string", "description": "quang_cao: ngày đầu YYYY-MM-DD (giờ VN)."},
            "den": {"type": "string", "description": "quang_cao: ngày cuối YYYY-MM-DD (≤ hôm nay)."},
            "so_ngay": {"type": "integer",
                        "description": "quang_cao: N ngày gần nhất TÍNH CẢ hôm nay. Không nói kỳ = "
                                       "hôm nay."},
            "theo_ngay": {"type": "boolean", "description": "quang_cao + `tim`: kèm từng ngày."},
            "link_bai": {"type": "array", "items": {"type": "string"},
                         "description": "bai: link bài (≤ 5)."},
            "kenh": {"type": "array", "items": {"type": "string"},
                     "description": "kenh: link hồ sơ hoặc @tên (≤ 2)."},
            "du_an": {"type": "string", "description": "quet: mã dự án trên dashboard."},
            "chi_uoc_tinh": {"type": "boolean",
                             "description": "bai/kenh/quet: chỉ ước tính chi phí, KHÔNG chạy; trả "
                                            "`ma_xac_nhan`."},
            "ma_xac_nhan": {"type": "string",
                            "description": "bai/kenh/quet: mã từ lần ước tính — CHỈ dùng khi tin "
                                           "nhắn KẾ TIẾP của người dùng đồng ý rõ ràng."},
        },
        "required": ["loai"],
    },
}


class TuChoi(HD.TuChoi):
    pass


# ───────────────────────────── xác nhận chi phí (chốt bằng code) ─────────────────────────────
_XAC_NHAN: dict[str, dict] = {}
_KHOA_XN = threading.Lock()
_dong_ho = time.monotonic


def _stt() -> tuple[str, int] | None:
    try:
        import dong_ho_luot
        return dong_ho_luot.stt_luot()
    except Exception:  # noqa: BLE001
        return None


def _khoa_pham_vi(loai: str, muc) -> str:
    return hashlib.sha256(json.dumps([loai, muc], ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()[:24]


def cap_ma(loai: str, email: str, muc, uoc_usd: float) -> str:
    """Lần ước tính: cấp mã xác nhận cho đúng phạm vi + người + chat + lượt trả lời này. Ngoài
    lượt trả lời có chat (lịch, việc nền) → không cấp (không ai trả lời được)."""
    stt = _stt()
    if not stt:
        raise TuChoi("Việc tốn tiền chỉ chạy được khi người dùng trả lời trực tiếp trong chat.")
    ma = "xn_" + secrets.token_hex(4)
    with _KHOA_XN:
        bay = _dong_ho()
        for k in [k for k, v in _XAC_NHAN.items() if v["het"] < bay]:
            _XAC_NHAN.pop(k, None)
        _XAC_NHAN[ma] = {"loai": loai, "email": email, "chat": stt[0], "stt": stt[1],
                         "khoa": _khoa_pham_vi(loai, muc), "uoc_usd": float(uoc_usd),
                         "het": bay + XAC_NHAN_GIAY}
    return ma


def dung_ma(ma: str, loai: str, email: str, muc) -> float:
    """Chạy thật: mã phải của đúng người / chat / phạm vi, còn hạn (15 phút) và dùng ĐÚNG ở tin
    nhắn KẾ TIẾP sau lượt ước tính (soát M2). Cùng lượt → từ chối, giữ mã (chưa ai trả lời); qua
    thêm tin nhắn → mã hết hạn. Dùng một lần. -> số USD đã được đồng ý."""
    stt = _stt()
    with _KHOA_XN:
        x = _XAC_NHAN.get(str(ma or ""))
        if not x or x["het"] < _dong_ho():
            _XAC_NHAN.pop(str(ma or ""), None)
            raise TuChoi("Chưa có xác nhận chi phí hợp lệ (mã không có hoặc đã hết hạn). Gọi "
                         "lại với `chi_uoc_tinh`=true, báo chi phí rồi hỏi \"Chạy nhé?\".")
        if (x["loai"], x["email"], x["chat"], x["khoa"]) != (
                loai, email, stt[0] if stt else None, _khoa_pham_vi(loai, muc)):
            raise TuChoi("Mã xác nhận không khớp người hỏi / cuộc chat / phạm vi đã ước tính — ước "
                         "tính lại rồi hỏi \"Chạy nhé?\".")
        if stt[1] == x["stt"]:
            raise TuChoi("Chưa chạy: người dùng chưa trả lời câu hỏi chi phí. Báo `cau_uoc_tinh`, "
                         "KẾT THÚC bằng \"Chạy nhé?\" và chờ họ đồng ý.")
        _XAC_NHAN.pop(ma, None)
        if stt[1] != x["stt"] + 1:
            raise TuChoi("Mã xác nhận đã hết hạn: chỉ dùng được ở tin nhắn NGAY SAU câu hỏi chi "
                         "phí. Ước tính lại rồi hỏi \"Chạy nhé?\".")
        return x["uoc_usd"]


# ───────────────────────────── tiện ích ─────────────────────────────
def _utc(x: datetime.datetime | None) -> datetime.datetime | None:
    if isinstance(x, datetime.datetime) and x.tzinfo is None:
        return x.replace(tzinfo=datetime.UTC)
    return x if isinstance(x, datetime.datetime) else None


def _gio(x) -> str | None:
    x = _utc(x)
    return x.astimezone(VN).strftime("%H:%M %d/%m/%Y") if x else None


def _dau_ngay(bay_gio: datetime.datetime) -> datetime.datetime:
    return datetime.datetime.combine(bay_gio.astimezone(VN).date(), datetime.time(0), VN)


def _ghi_tu_choi(kho, loai: str, email: str, ly: str, **kw) -> None:
    """Từ chối vẫn để lại dấu vết (dòng tu_choi + nhật ký do trigger) — không tính vào trần."""
    try:
        kho.tt_tao(loai, email, loi=ly, **kw)
    except Exception as e:  # noqa: BLE001 — ghi dấu vết hỏng không đổi câu trả lời
        print(f"[tuc_thi] ghi từ chối lỗi: {type(e).__name__}")


def _ngay(s: str, md: datetime.date) -> datetime.date:
    return NL.ngay(str(s or "").strip(), md)


def khoang_qc(args: dict, hn: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Kỳ hỏi của quảng cáo tức thì: mặc định hôm nay; `so_ngay` N = N ngày gồm hôm nay."""
    n = args.get("so_ngay")
    if not args.get("tu") and not args.get("den") and n not in (None, ""):
        try:
            n = int(n)
        except (TypeError, ValueError):
            raise NL.LoiNhap("`so_ngay` phải là số ngày.") from None
        if not 1 <= n <= HD.KHOANG_TOI_DA_NGAY:
            raise NL.LoiNhap(f"`so_ngay` từ 1 tới {HD.KHOANG_TOI_DA_NGAY}.")
        return hn - datetime.timedelta(days=n - 1), hn
    den = min(_ngay(args.get("den"), hn), hn)
    tu = _ngay(args.get("tu"), den)
    if tu > den:
        raise NL.LoiNhap("Ngày bắt đầu phải trước ngày kết thúc.")
    if (den - tu).days + 1 > HD.KHOANG_TOI_DA_NGAY:
        raise NL.LoiNhap(f"Khoảng tối đa {HD.KHOANG_TOI_DA_NGAY} ngày.")
    return tu, den


# ───────────────────────────── quảng cáo ─────────────────────────────
def _tk_pham_vi(kho, q: dict, args: dict, cac_tk: list[dict], hn: datetime.date
                ) -> tuple[list[str], list[dict]]:
    """Tài khoản cần đọc lại: trong phạm vi bên người hỏi (cùng luật `hoi_dashboard`), đang đồng
    bộ; có `tim` → chỉ tài khoản chứa đối tượng đó (không khớp thì mọi tài khoản trong phạm vi —
    chiến dịch mới hôm nay chưa có trong kho); không `tim` → MỌI tài khoản đang đồng bộ trong
    phạm vi (tài khoản mới phân phối hôm nay cũng được đọc — L5), tài khoản có chạy 30 ngày xếp
    trước, tối đa `TK_TOI_DA`.
    -> (mọi tài khoản trong phạm vi — cho độ mới, tài khoản cần đọc lại)."""
    hoi = str(args.get("ben") or "").strip().lower()
    tim = str(args.get("tim") or "").strip()[:200]
    tk = {}
    for b in HD._pham_vi_qc(q, cac_tk, hoi, bool(tim)):
        for t in QC.tk_trong_pham_vi(q, cac_tk, b):
            if t.get("dang_dong_bo", True) and t.get("con_quyen", True):
                tk[str(t["advertiser_id"])] = t
    if not tk:
        return [], []
    if tim:
        cap = str(args.get("cap") or "chien_dich")
        if cap == "tai_khoan":
            khop = [t for t in tk.values() if HD._khop_tk(t, QC.chu_tim(tim), tim)]
        else:
            r = kho.qc_tim(cap if cap in HD.CAP_TRA else "chien_dich", list(tk), QC.chu_tim(tim), tim)
            ids = {str(x.get("advertiser_id")) for x in r.get("rows") or []}
            khop = [tk[i] for i in sorted(ids) if i in tk]
        return list(tk), (khop or list(tk.values()))[:TK_TOI_DA]
    a = hn - datetime.timedelta(days=29)
    co = {i for i in tk if (kho.qc_tong([i], a, hn) or {}).get("hien_thi")}
    xep = sorted(tk, key=lambda i: (i not in co, i))
    return list(tk), [tk[i] for i in xep[:TK_TOI_DA]]


def _dung_lai(rows: list[dict], ids: set[str], tu, den) -> dict | None:
    for r in rows:
        if (ids <= {str(x) for x in r.get("tai_khoan") or []}
                and (r.get("tu") is None or r["tu"] <= tu)
                and (r.get("den") is None or r["den"] >= den)):
            return r
    return None


def _cho(kho, ids: list[int], han: float, ngu) -> list[dict]:
    rows = kho.tt_doc(ids)
    while any(r["trang_thai"] in ("cho", "dang_chay") for r in rows) and _dong_ho() < han:
        ngu(NHIP_HOI)
        rows = kho.tt_doc(ids)
    return rows


def _han_cho() -> float:
    """Chờ ≤ 90 giây, và không vượt mốc nhắc của đồng hồ lượt (chừa thời gian viết trả lời)."""
    try:
        import dong_ho_luot
        da = dong_ho_luot.da_chay()
    except Exception:  # noqa: BLE001
        da = None
    con = CHO_TOI_DA if da is None else max(5.0, min(CHO_TOI_DA, 300.0 - da))
    return _dong_ho() + con


def do_moi_ncc(r: dict, xin: int, ghi_kho, q: dict) -> dict:
    """Độ mới của MỘT nền tảng sau lượt đọc (soát M1): đủ / một phần / chưa đọc lại được — câu nói
    sẵn + mốc datetime (so sánh bằng datetime, không bằng chuỗi)."""
    ten = TEN_NCC.get(r.get("nha_cung_cap"), r.get("nha_cung_cap") or "?")
    tt = r.get("trang_thai")
    ok = r.get("so_tk_ok")
    xin = int(r.get("so_muc") or xin or 0)
    loi = r.get("loi")
    if loi and not PQ.la_quan_tri(q):
        loi = HD.LOI_CHUNG
    x = {"nen_tang": ten, "trang_thai": tt, "so_tk_xin": xin, "so_tk_doc_duoc": ok}
    kho_luc = _gio(ghi_kho)
    if tt == "xong" and ok:
        x["luc"] = _utc(r.get("xong_luc"))
        if ok < xin:
            x["muc"] = "mot_phan"
            x["cau"] = (f"{ten}: cập nhật MỘT PHẦN lúc {_gio(x['luc'])} ({ok}/{xin} tài khoản đọc "
                        "lại được" + (f"; lỗi: {loi}" if loi else "") + ")")
        else:
            x["muc"] = "du"
            x["cau"] = f"{ten}: số cập nhật lúc {_gio(x['luc'])} (đủ {ok}/{xin} tài khoản)"
        return x
    x["muc"] = "chua"
    if tt in ("cho", "dang_chay"):
        ly = "lượt đọc chưa xong sau ~90 giây (lượt khác đang chạy hoặc nhiều tài khoản)"
    else:
        ly = loi or "không đọc lại được"
    x["cau"] = (f"{ten}: chưa đọc lại được ({ly}) — số trong kho ghi lúc {kho_luc or '?'}"
                + ("; hỏi lại sau ít phút" if tt in ("cho", "dang_chay") else ""))
    return x


def quang_cao(kho, nguoi: dict, args: dict, bay_gio: datetime.datetime, ngu=time.sleep) -> dict:
    q, email = nguoi["q"], nguoi["email"]
    hn = bay_gio.astimezone(VN).date()
    tu, den = khoang_qc(args, hn)
    nen = str(args.get("nen_tang") or "").strip().lower()
    if nen and nen not in NCC_NEN:
        raise NL.LoiNhap("nen_tang chỉ nhận tiktok hoặc meta.")
    cac_tk = QC.tk_dung(list(kho.qc_cac_tk()), nen or None)
    pham_vi, tk = _tk_pham_vi(kho, q, args, cac_tk, hn)
    lam_moi: dict = {"tu": None, "den": None, "nha_cung_cap": {}}
    rtu, rden = max(tu, hn - datetime.timedelta(days=TUC_THI_NGAY - 1)), den
    T = tran()
    theo_ncc: dict[str, list[str]] = {}
    for t in tk:
        theo_ncc.setdefault(NCC_NEN[QC.nen_tang_tk(t)], []).append(str(t["advertiser_id"]))
    cho_ids: dict[str, int] = {}
    if rtu > rden:
        lam_moi["ly_do"] = ("Kỳ hỏi đã qua hơn 7 ngày — số đã chốt ở lượt đồng bộ hằng ngày, không "
                            "cần đọc lại; trả số trong kho.")
    elif not tk:
        lam_moi["ly_do"] = ("Không có tài khoản quảng cáo nào (đang đồng bộ) trong phạm vi bạn được "
                            "xem để đọc lại.")
    elif QC.trong_gio_dong_bo(bay_gio):
        lam_moi["ly_do"] = QC.CAU_GIO_DONG_BO
    else:
        lam_moi.update(tu=rtu.isoformat(), den=rden.isoformat())
        ben = sorted({t.get("don_vi") or "" for t in tk})
        ben1 = ben[0] if len(ben) == 1 and ben[0] else None
        gio_truoc = bay_gio - datetime.timedelta(hours=1)
        nhom = uuid.uuid4().hex[:12]          # MỘT yêu cầu của người dùng (đếm trần người/giờ)
        ct = {"nhom": nhom, **{k: str(args.get(k))[:200] for k in ("tim", "cap") if args.get(k)}}
        for ncc, ids in sorted(theo_ncc.items()):
            cu = _dung_lai(kho.tt_gan_day_qc(ncc, GIAN_PHUT), set(ids), rtu, rden)
            if cu is not None:
                cho_ids[ncc] = cu["id"]
                lam_moi["nha_cung_cap"][ncc] = {"dung_lai_yeu_cau": cu["id"],
                                                "ly_do": f"cùng phạm vi đã đọc / đang đọc trong "
                                                         f"{GIAN_PHUT} phút qua — dùng lại"}
                continue
            r = kho.tt_tao("quang_cao", email, ben=ben1, nha_cung_cap=ncc, tai_khoan=ids, tu=rtu,
                           den=rden, so_muc=len(ids), chi_tiet=ct, tran=[
                               {"loai": "quang_cao", "tu_luc": gio_truoc, "nguoi_hoi": email,
                                "nhom": nhom, "toi_da": T["qc_nguoi_gio"],
                                "ly_do": f"Bạn đã xin đọc lại số quảng cáo {T['qc_nguoi_gio']} "
                                         "lần trong 60 phút qua (trần chống nền tảng chặn)."},
                               {"loai": "quang_cao", "tu_luc": gio_truoc, "nha_cung_cap": ncc,
                                "toi_da": T["qc_gio"],
                                "ly_do": f"Cả hệ thống đã đọc lại {TEN_NCC[ncc]} {T['qc_gio']} "
                                         "lần trong 60 phút qua (trần chống nền tảng chặn)."}])
            if r.get("vuot"):
                lam_moi["nha_cung_cap"][ncc] = {"tu_choi": r["vuot"]}
                continue
            cho_ids[ncc] = r["id"]
            lam_moi["nha_cung_cap"][ncc] = {"yeu_cau": r["id"], "so_tai_khoan": len(ids)}
    # Độ mới TỪNG nền tảng (M1).
    cac: list[dict] = []
    rows = {r["id"]: r for r in (_cho(kho, list(cho_ids.values()), _han_cho(), ngu)
                                 if cho_ids else [])}
    for ncc in sorted(set(theo_ncc) | {NCC_NEN[QC.nen_tang_tk(t)] for t in cac_tk
                                        if str(t["advertiser_id"]) in set(pham_vi)}):
        ids_ncc = [str(t["advertiser_id"]) for t in cac_tk if str(t["advertiser_id"])
                   in set(pham_vi) and NCC_NEN[QC.nen_tang_tk(t)] == ncc]
        ghi = (kho.qc_moi(ids_ncc) or {}).get("ghi_luc") if ids_ncc else None
        if ncc in cho_ids:
            r = rows.get(cho_ids[ncc]) or {"nha_cung_cap": ncc}
            x = do_moi_ncc(r, len(theo_ncc.get(ncc, [])), ghi, q)
            lam_moi["nha_cung_cap"][ncc].update(trang_thai=x["trang_thai"], muc=x["muc"])
        else:
            ly = (lam_moi["nha_cung_cap"].get(ncc) or {}).get("tu_choi") or lam_moi.get("ly_do") \
                or "không cần đọc lại"
            x = {"nen_tang": TEN_NCC[ncc], "muc": "chua", "trang_thai": None,
                 "cau": f"{TEN_NCC[ncc]}: chưa đọc lại ({ly}) — số trong kho ghi lúc "
                        f"{_gio(ghi) or '?'}"}
        x["kho_ghi_luc"] = _utc(ghi)
        cac.append(x)
    # Trả lời bằng số TRONG KHO (cùng đường đọc của hoi_dashboard).
    doc = {k: args.get(k) for k in ("nen_tang", "ben", "tim", "cap", "theo_ngay") if args.get(k)}
    so = HD.quang_cao(kho, q, doc, tu, den, HD.TOP_MAC_DINH)
    moc = [x["luc"] for x in cac if x.get("luc")]
    do_moi = {"theo_nen_tang": [{k: (_gio(v) if isinstance(v, datetime.datetime) else v)
                                 for k, v in x.items()} for x in cac],
              "doc_moi_xong_luc": _gio(max(moc)) if moc else None,
              "mot_phan": [x["nen_tang"] for x in cac if x["muc"] == "mot_phan"],
              "chua_doc_lai": [x["nen_tang"] for x in cac if x["muc"] == "chua"],
              "tam_tinh": den >= hn,
              "cau": "; ".join(x["cau"] for x in cac)
              + ("." if den < hn else ". Số hôm nay là tạm tính (nền tảng báo trễ vài giờ, "
                 "chuyển đổi còn ghi bù).")}
    return {"loai": "quang_cao", "khoang": {"tu": tu.isoformat(), "den": den.isoformat()},
            "lam_moi": lam_moi, "do_moi": do_moi, "quang_cao": so, "ghi_chu": QUY_TAC}


# ───────────────────────────── ngân sách Apify (chung bài / kênh / quét) ─────────────────────────────
def kiem_ngan_sach(uoc: float) -> dict:
    """Gói Apify còn đủ cho ước tính? ĐÓNG khi không hỏi được (không chạy mù)."""
    import apify_tool as A
    import viec_nen
    hm = A._han_muc_thang()
    if not hm:
        raise TuChoi("Chưa kiểm được ngân sách gói Apify lúc này nên Mark chưa cào (không chạy khi "
                     "không biết còn tiền). Thử lại sau ít phút.")
    con = max(0.0, float(hm["con_lai"]) - DU_TRU_USD - float(viec_nen.da_cam_ket() or 0))
    if uoc > con + 1e-9:
        raise TuChoi(f"Chưa chạy: ước tính {uoc:.3f} USD mà gói Apify chỉ còn dùng được {con:.2f} "
                     f"USD (đã dùng {hm['dung']:.2f}/{hm['tran']:g} USD, chừa {DU_TRU_USD:.2f} dự "
                     "trữ và phần các việc nền đang giữ).")
    return {"con_usd": round(con, 2), "da_dung_usd": hm["dung"], "tran_usd": hm["tran"]}


def _cong_tac(tool: str) -> None:
    import lsr_policy
    d = lsr_policy.decide(tool, {})
    if not d.allowed:
        raise TuChoi(f"Năng lực cào ({tool}) đang tắt hoặc không được phép: {d.reason}")


def _doc_duoc_du_an(kho, q: dict, cac: list[str]) -> bool:
    """Link / kênh thuộc dự án nào trong kho thì người hỏi phải đọc được ít nhất một dự án đó;
    không thuộc dự án nào (dữ liệu công khai) thì được."""
    if not cac:
        return True
    ds = {d["ma"]: d for d in kho.cac_du_an()}
    return any(PQ.doc_duoc(q, ds.get(m)) for m in cac)


def _tran_ngay(loai: str, email: str, bay_gio, toi_da: int, ten: str) -> list[dict]:
    return [{"loai": loai, "tu_luc": _dau_ngay(bay_gio), "nguoi_hoi": email, "cong_muc": True,
             "toi_da": toi_da, "ly_do": f"Hôm nay bạn đã dùng hết trần {toi_da} {ten}/người/ngày "
                                        "lấy số mới."}]


def _ket_thuc(kho, yid: int, tt: str, **kw) -> None:
    try:
        kho.tt_cap_nhat(yid, tt, **kw)
    except Exception as e:  # noqa: BLE001 — bộ nghe dọn dòng kẹt sau 60 phút (`don_dep`)
        print(f"[tuc_thi] kết thúc yêu cầu {yid} lỗi: {type(e).__name__}")


def bai(kho, nguoi: dict, args: dict, bay_gio: datetime.datetime) -> dict:
    import apify_tool as A
    import chi_phi_tool
    import chi_so_bai_tool as CSB
    import theo_doi
    q, email = nguoi["q"], nguoi["email"]
    T = tran()
    links = CSB._tach_link(args.get("link_bai"))
    if not links:
        raise NL.LoiNhap("Thiếu `link_bai`.")
    if len(links) > T["bai_luot"]:
        raise TuChoi(f"Số mới ngay chỉ cho tối đa {T['bai_luot']} link mỗi lần. Danh sách dài "
                     "(đếm + cộng tổng, ra Sheet) thì dùng công cụ chỉ số theo link bài.")
    _cong_tac("chi_so_bai")
    dong, khoa_da = [], set()
    for i, u in enumerate(links):
        p, k = CSB._nhan_dien(u)
        if p and k not in khoa_da:
            khoa_da.add(k)
            dong.append({"stt": i + 1, "link": u, "nen": p, "trang_thai": "", "ket": None,
                         "trung_voi": None})
    if not dong:
        raise NL.LoiNhap("Không có link BÀI nào nhận ra được (TikTok, YouTube, Instagram, "
                         "Facebook, Threads).")
    # L1: so cả khoá bài dựng bằng ĐÚNG hàm lúc ghi `bai` (link khác dạng vẫn khớp).
    khoa = [theo_doi._khoa_bai(d["nen"], d["link"]) for d in dong]
    if not _doc_duoc_du_an(kho, q, kho.tt_du_an_cua_link([d["link"] for d in dong], khoa)):
        _ghi_tu_choi(kho, "bai", email, "link thuộc dự án bên khác", so_muc=len(dong))
        raise TuChoi("Link này thuộc dự án của bên bạn không được xem nên Mark không cào.")
    chay, con_lai, tat, tran_thap = CSB._ke_hoach(dong)
    if not chay:
        ly = "; ".join([A._ly_do_tat(p) for p in sorted(tat)]
                       + [f"trần console {p} quá thấp" for p in tran_thap]) or "không có gì để cào"
        raise TuChoi(f"Chưa cào được: {ly}.")
    uoc = round(sum(CSB._GIA[p] * len(v) for p, v in chay.items()), 4)
    muc = sorted(u for v in chay.values() for u in v)
    ns = kiem_ngan_sach(uoc) if uoc > 0 else None
    if uoc > 0 and args.get("chi_uoc_tinh"):
        ma = cap_ma("bai", email, muc, uoc)
        return {"loai": "bai", "chi_uoc_tinh": True, "ma_xac_nhan": ma, "uoc_usd": uoc,
                "so_link": len(muc), "ngan_sach": ns,
                "cau_uoc_tinh": f"Lấy số hiện tại của {len(muc)} link, ước tính khoảng {uoc:.3f} "
                                "USD, trừ vào gói Apify chung của Mark (không trừ ngân sách dự án "
                                "nào), xong trong ~1–2 phút.",
                "huong_dan": "Chép `cau_uoc_tinh`, KẾT THÚC bằng \"Chạy nhé?\" và DỪNG. Chỉ chạy khi "
                             "tin nhắn KẾ TIẾP đồng ý rõ."}
    if uoc > 0:
        dung_ma(args.get("ma_xac_nhan"), "bai", email, muc)
    r = kho.tt_tao("bai", email, so_muc=len(muc), chi_tiet={"link": muc}, uoc_usd=uoc,
                   tran=_tran_ngay("bai", email, bay_gio, T["bai_ngay"], "link"))
    if r.get("vuot"):
        raise TuChoi(r["vuot"])
    tt, kw = "loi", {"loi": "dừng giữa chừng"}
    try:
        bat_dau = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=5)
        t0 = time.monotonic()
        han = t0 + A._TOOL_DEADLINE
        ket, loi, so_run = {}, {}, []

        def _lay(p, v):
            A._SO_RUN.set(so_run)
            A._HAN_CHOT.set(han - A._DU_PHONG_HUY)
            return CSB._LAY[p](v)
        ex = ThreadPoolExecutor(max_workers=max(1, len(chay)))
        try:
            futs = {p: ex.submit(contextvars.copy_context().run, _lay, p, v)
                    for p, v in chay.items()}
            for p, f in futs.items():
                try:
                    ket.update(f.result(timeout=max(0.05, han - time.monotonic())))
                except Exception as e:  # noqa: BLE001
                    loi[p] = A._che_token(f"{type(e).__name__}: {e}")[:250]
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        luc = datetime.datetime.now(A._VN_TZ)
        actors = [CSB._NGUON[p] for p in chay if p in CSB._NGUON]
        thuc = A._chi_phi_thuc(actors, bat_dau, uoc) if actors else None
        chi_phi_tool.ghi(queries=[f"số tức thì {len(muc)} link bài"], platforms=sorted(chay),
                         date_range=f"lấy số lúc {luc:%Y-%m-%d %H:%M}", thuc=thuc, est=uoc)
        usd = thuc["usd"] if thuc and thuc.get("so_run") else None
        tt = "xong" if ket else "loi"
        kw = {"chi_phi_usd": usd, "loi": "; ".join(f"{k}: {v}" for k, v in loi.items()) or None}
    finally:
        _ket_thuc(kho, r["id"], tt, **kw)          # L3: không bao giờ kẹt dang_chay
    ra = []
    for d in dong:
        k = ket.get(d["link"])
        ra.append({"link": d["link"], "nen_tang": CSB._ten(d["nen"]),
                   **({c: k.get(c) for c in CSB._COT} | {"tai_khoan": k.get("tai_khoan"),
                                                        "ngay_dang": k.get("ngay")}
                      if k else {"trang_thai": "không lấy được (xoá / riêng tư / nguồn lỗi / "
                                               "vượt trần console)"})})
    return {"loai": "bai", "lay_so_luc": f"{luc:%H:%M %d/%m/%Y}", "bai": ra,
            "gioi_han_nen_tang": [CSB._GHI_CHU_NEN[p] for p in sorted(chay)
                                  if p in CSB._GHI_CHU_NEN] or None,
            "con_lai_chua_cao": con_lai or None, "loi": loi or None,
            "chi_phi": A._dong_chi_phi(thuc, uoc), "chi_phi_thuc_usd": usd,
            "do_moi": {"cau": f"Số công khai lấy lúc {luc:%H:%M %d/%m/%Y}."},
            "ghi_chu": "Ô None = nền tảng không công khai số đó (không phải 0). " + QUY_TAC}


def kenh(kho, nguoi: dict, args: dict, bay_gio: datetime.datetime) -> dict:
    import account_tool as AT
    import apify_tool as A
    import chi_phi_tool
    q, email = nguoi["q"], nguoi["email"]
    T = tran()
    ds = args.get("kenh") or []
    ds = [ds] if isinstance(ds, str) else list(ds)
    if not ds:
        raise NL.LoiNhap("Thiếu `kenh`.")
    if len(ds) > T["kenh_luot"]:
        raise TuChoi(f"Số mới ngay chỉ cho tối đa {T['kenh_luot']} kênh mỗi lần. Soi nhiều kênh "
                     "(ra Sheet) thì dùng công cụ soi tài khoản.")
    _cong_tac("soi_tai_khoan")
    md = str(args.get("nen_tang") or "tiktok").lower()
    nhom: dict[str, list[str]] = {}
    for m in ds:
        x = AT._nhan_dien(str(m), md if md in AT._ACTOR else "tiktok")
        if x:
            nhom.setdefault(x[0], []).append(x[1])
    if not nhom:
        raise NL.LoiNhap("Không nhận ra kênh nào (link hồ sơ hoặc @tên).")
    dinh = [v.rstrip("/").split("/")[-1].lower() for vs in nhom.values() for v in vs]
    if not _doc_duoc_du_an(kho, q, kho.tt_du_an_cua_kenh(
            dinh + [v.lower() for vs in nhom.values() for v in vs])):
        _ghi_tu_choi(kho, "kenh", email, "kênh là nguồn của dự án bên khác", so_muc=len(dinh))
        raise TuChoi("Kênh này là nguồn theo dõi của dự án bên bạn không được xem nên Mark không "
                     "cào.")
    so = sum(len(v) for v in nhom.values())
    n = T["kenh_bai"]
    uoc = round(sum(AT._GIA[p] * (len(v) if p == "instagram" else len(v) * n)
                    for p, v in nhom.items()), 4)
    muc = {p: sorted(v) for p, v in sorted(nhom.items())}
    ns = kiem_ngan_sach(uoc)
    if args.get("chi_uoc_tinh"):
        ma = cap_ma("kenh", email, muc, uoc)
        return {"loai": "kenh", "chi_uoc_tinh": True, "ma_xac_nhan": ma, "uoc_usd": uoc,
                "ngan_sach": ns,
                "cau_uoc_tinh": f"Đọc hồ sơ + {n} bài mới nhất của {so} kênh, ước tính khoảng "
                                f"{uoc:.3f} USD, trừ vào gói Apify chung của Mark (không trừ ngân "
                                "sách dự án nào), ~1–2 phút.",
                "huong_dan": "Chép `cau_uoc_tinh`, KẾT THÚC bằng \"Chạy nhé?\" và DỪNG. Chỉ chạy khi "
                             "tin nhắn KẾ TIẾP đồng ý rõ."}
    dung_ma(args.get("ma_xac_nhan"), "kenh", email, muc)
    r = kho.tt_tao("kenh", email, so_muc=so, chi_tiet={"kenh": muc}, uoc_usd=uoc,
                   tran=_tran_ngay("kenh", email, bay_gio, T["kenh_ngay"], "kênh"))
    if r.get("vuot"):
        raise TuChoi(r["vuot"])
    tt, kw = "loi", {"loi": "dừng giữa chừng"}
    try:
        bat_dau = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=5)
        ket, loi = [], {}
        for p, v in nhom.items():
            try:
                for tk in AT._LAY[p](v, n).values():
                    ket.append((p, tk))
            except Exception as e:  # noqa: BLE001
                loi[p] = f"{getattr(e, 'ma', None) or type(e).__name__}"[:120]
        luc = datetime.datetime.now(A._VN_TZ)
        thuc = A._chi_phi_thuc([AT._ACTOR[p] for p in nhom], bat_dau, uoc)
        chi_phi_tool.ghi(queries=ds, platforms=sorted(nhom),
                         date_range=f"lấy số lúc {luc:%H:%M}", thuc=thuc, est=uoc)
        usd = thuc["usd"] if thuc and thuc.get("so_run") else None
        tt = "xong" if ket else "loi"
        kw = {"chi_phi_usd": usd, "loi": "; ".join(f"{k}: {v}" for k, v in loi.items()) or None}
    finally:
        _ket_thuc(kho, r["id"], tt, **kw)          # L3
    ra = []
    for p, tk in ket:
        hs = tk.get("ho_so") or {}
        ra.append({"nen_tang": p, "ho_so": {k: hs.get(k) for k in (
            "ten", "tai_khoan", "followers", "tong_like", "tong_video", "tong_bai", "link")},
            "bai_moi_nhat": [{"ngay": _gio(b.get("ngay")), "view": b.get("view"),
                              "like": b.get("like"), "binh_luan": b.get("binh_luan"),
                              "share": b.get("share"), "link": b.get("link")}
                             for b in (tk.get("bai") or [])[:n]],
            "ghi_chu": tk.get("ghi_chu") or None})
    return {"loai": "kenh", "lay_so_luc": f"{luc:%H:%M %d/%m/%Y}", "kenh": ra, "loi": loi or None,
            "chi_phi": A._dong_chi_phi(thuc, uoc), "chi_phi_thuc_usd": usd,
            "do_moi": {"cau": f"Số công khai lấy lúc {luc:%H:%M %d/%m/%Y}."}, "ghi_chu": QUY_TAC}


def quet(kho, nguoi: dict, args: dict, bay_gio: datetime.datetime) -> dict:
    import lenh_cung
    import theo_doi
    q, email = nguoi["q"], nguoi["email"]
    T = tran()
    ma = str(args.get("du_an") or "").strip()
    ds = PQ.loc_du_an(q, kho.cac_du_an())
    du_an = next((d for d in ds if d["ma"] == ma), None)
    if du_an is None:
        raise NL.LoiNhap(f"Không có dự án “{ma}” trong phạm vi bạn được xem. Dự án đang có: "
                         + (", ".join(d["ma"] for d in ds) or "chưa có") + ".")
    ben = du_an.get("don_vi")
    cho, ly = lenh_cung._duoc_khong("soi_tai_khoan")
    if not cho:
        raise TuChoi(f"Năng lực quét theo dõi đang tắt: {ly or 'chủ agent đã tắt'}.")
    # Trần lượt quét theo yêu cầu: mỗi BÊN mỗi ngày; dự án chưa có bên đếm theo CHÍNH dự án (L2).
    chieu = {"ben": ben} if ben else {"du_an": ma}
    ten_chieu = f"bên {ben}" if ben else f"dự án {ma}"
    tran_quet = [{"loai": "quet", "tu_luc": _dau_ngay(bay_gio), **chieu,
                  "trang_thai": ("xong", "dang_chay"), "toi_da": T["quet_ngay"],
                  "ly_do": f"Hôm nay {ten_chieu} đã mở đủ {T['quet_ngay']} lượt quét theo yêu cầu "
                           "(trần mỗi ngày). Lịch quét tự động vẫn chạy như thường."}]
    da = kho.tt_dem("quet", _dau_ngay(bay_gio), trang_thai=("xong", "dang_chay"), **chieu)
    if da >= T["quet_ngay"]:
        _ghi_tu_choi(kho, "quet", email, tran_quet[0]["ly_do"], ben=ben, du_an=ma)
        raise TuChoi(tran_quet[0]["ly_do"])
    kh = theo_doi.ke_hoach(ma)
    if kh.get("loi"):
        raise TuChoi(kh["loi"])            # gồm "lượt trước còn đang chạy"
    if kh["con_thang"] < 0.01:
        raise TuChoi(f"Dự án {du_an['ten']} đã hết ngân sách tháng trên dashboard — chưa quét.")
    u = theo_doi.uoc_giu_cho(kh, ma)       # M3: ĐÚNG mức tao_luot sẽ giữ
    if u["hm"] is None:
        raise TuChoi("Chưa kiểm được ngân sách gói Apify lúc này nên Mark chưa mở lượt quét.")
    uoc = float(u["tong"])
    if uoc > float(u["ns_apify"]) + 1e-9:
        raise TuChoi(f"Chưa chạy: lượt quét giữ tối đa {uoc:.2f} USD mà ngân sách Apify còn dùng "
                     f"được {float(u['ns_apify']):.2f} USD.")
    if uoc > float(kh["con_thang"]) + 1e-9:
        raise TuChoi(f"Chưa chạy: lượt quét giữ tối đa {uoc:.2f} USD mà ngân sách tháng của dự án "
                     f"{du_an['ten']} chỉ còn {float(kh['con_thang']):.2f} USD.")
    phut = max(3, len(kh["nguon"]) // 4) + (3 if u["bl_uoc"] else 0) + (3 if u["tk_uoc"] else 0)
    muc = {"du_an": ma, "nguon": sorted(int(n["id"]) for n in kh["nguon"])}
    if args.get("chi_uoc_tinh"):
        ma_xn = cap_ma("quet", email, muc, uoc)
        phan = [f"theo dõi nguồn {u['tong'] - u['tk_uoc'] - u['bl_uoc'] - u['dp_uoc']:.2f}"]
        phan += [f"{t} {v:.2f}" for t, v in (("tìm theo từ khoá", u["tk_uoc"]),
                                             ("cào bình luận", u["bl_uoc"]),
                                             ("kiểm độ phủ", u["dp_uoc"])) if v]
        return {"loai": "quet", "chi_uoc_tinh": True, "ma_xac_nhan": ma_xn, "uoc_usd": uoc,
                "phut": phut, "so_nguon": len(kh["nguon"]),
                "ngan_sach_du_an": {"du_an": du_an["ten"], "con_usd": kh["con_thang"],
                                    "tran_usd": kh["tran_thang"]},
                # M4: Chỉ xem cũng mở được (chủ dự án chốt) — câu PHẢI nói rõ tiền + ngân sách nào.
                "cau_uoc_tinh": (f"Mở ngay một lượt quét {du_an['ten']}: {len(kh['nguon'])} nguồn "
                                 f"tới hạn" + (" + tìm theo từ khoá" if not kh["nguon"] else "")
                                 + f". Chi phí tối đa {uoc:.2f} USD (" + ", ".join(phan) + " USD)"
                                 + theo_doi._cau_chi_that(ma) + f", TÍNH VÀO NGÂN SÁCH THÁNG của dự "
                                 f"án {du_an['ten']} (còn {kh['con_thang']:.2f}/"
                                 f"{kh['tran_thang']:.2f} USD) và gói Apify chung. Chạy nền khoảng "
                                 f"{phut}–{phut * 3} phút, xong Mark nhắn kết quả và số lên "
                                 "dashboard."),
                "huong_dan": "Chép `cau_uoc_tinh` (cả số tiền và ngân sách bị trừ), KẾT THÚC bằng "
                             "\"Chạy nhé?\" và DỪNG. Chỉ chạy khi tin nhắn KẾ TIẾP đồng ý rõ."}
    dong_y = dung_ma(args.get("ma_xac_nhan"), "quet", email, muc)
    # L2: ghi yêu cầu (dang_chay) TRƯỚC khi tạo việc, trần đếm nguyên tử.
    r = kho.tt_tao("quet", email, ben=ben, du_an=ma, so_muc=len(kh["nguon"]), uoc_usd=dong_y,
                   tran=tran_quet)
    if r.get("vuot"):
        raise TuChoi(r["vuot"])
    kq = {"ok": False, "cau": "dừng giữa chừng"}
    try:
        kq = theo_doi.tao_luot(ma, tran_xac_nhan=dong_y)
    finally:
        if kq.get("ok"):
            _ket_thuc(kho, r["id"], "xong", chi_tiet_them={"ma_viec": kq.get("ma_viec")})
        else:
            _ket_thuc(kho, r["id"], "loi", loi=kq.get("cau") or kq.get("ma_loi"))
    if not kq.get("ok"):
        raise TuChoi(kq.get("cau") or "Không mở được lượt quét.")
    return {"loai": "quet", "da_tao": True, "ma_viec": kq.get("ma_viec"), "cau": kq.get("cau"),
            "do_moi": {"cau": "Lượt quét chạy nền — số mới có trên dashboard khi xong."},
            "ghi_chu": "Chép `cau` cho người hỏi; kết quả về chat này + dashboard khi xong."}


# ───────────────────────────── tool ─────────────────────────────
def tra_loi(args: dict, kho=None, *, open_id: str | None = None,
            bay_gio: datetime.datetime | None = None, ngu=time.sleep) -> dict:
    if (os.environ.get("MARK_TUC_THI") or "1").strip() == "0":
        raise TuChoi("Lấy số mới ngay đang tắt ở máy chạy (MARK_TUC_THI=0) — dùng số trong kho "
                     "(hoi_dashboard) và nói rõ số tính tới lúc nào.")
    kho = kho or HD._kho_mac_dinh()
    nguoi = HD.kiem_quyen(kho, open_id if open_id is not None else HD.nguoi_hoi())
    bay_gio = bay_gio or datetime.datetime.now(VN)
    loai = str((args or {}).get("loai") or "").strip()
    if loai == "quang_cao":
        return quang_cao(kho, nguoi, args, bay_gio, ngu)
    if loai == "bai":
        return bai(kho, nguoi, args, bay_gio)
    if loai == "kenh":
        return kenh(kho, nguoi, args, bay_gio)
    if loai == "quet":
        return quet(kho, nguoi, args, bay_gio)
    raise NL.LoiNhap("`loai` phải là quang_cao, bai, kenh hoặc quet.")


def _handle(args: dict, **_kw) -> str:
    try:
        ra = tra_loi(args or {})
    except HD.TuChoi as e:
        return tool_error(str(e))
    except NL.LoiNhap as e:
        return tool_error(f"Tham số chưa hợp lệ: {e}")
    except Exception as e:  # noqa: BLE001
        if HD._loi_kho(e):
            return tool_error(f"Chưa đọc được kho ({e}). Nói rõ chưa có số mới, đừng đoán.")
        print(f"[tuc_thi] lỗi: {type(e).__name__}: {str(e)[:200]}")
        return tool_error(f"Lấy số mới lỗi ({type(e).__name__}). Nói rõ chưa có số, đừng đoán.")
    if ra.get("loai") == "quang_cao":
        HD._danh_dau_han_che()
    return tool_result(json.loads(json.dumps(ra, ensure_ascii=False, default=str)))


def register() -> None:
    try:
        registry.register(
            name="lay_so_tuc_thi", toolset="social", schema=SCHEMA, handler=_handle,
            check_fn=lambda: True, requires_env=[], is_async=False,
            description="Lấy số mới ngay: quảng cáo, chỉ số bài/kênh, mở lượt quét",
            emoji="⚡", override=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[tuc_thi] register warning: {e}")


register()
