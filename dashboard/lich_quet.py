"""Lịch quét tự động (chủ dự án chốt 15/10/2026: "Dashboard + Mark tự chạy") — phần THUẦN.

Chủ dự án: "thêm phần tự động quét, có thể là những ngày hoạt động chiến dịch cần thời gian quét
liên tục nên custom mục cài tự động có thể là theo giờ, ngày, tuần (chi tiết mục tự động này rõ
ràng theo các mốc thời gian cụ thể)". Lịch đặt trên dashboard, lưu ở bảng `lich_quet` của kho
`lang_nghe`; Mark (`quet_tu_dong.py`) tự chạy `/theodoi` đúng mốc. Lịch "Giao việc" trên console
platform vẫn chạy như cũ — đây là đường thứ hai, linh hoạt hơn.

Module này dùng chung HAI phía, nên chỉ thư viện chuẩn, không SQL, không mạng:
  • dashboard: kiểm biểu mẫu, xem trước 10 lần chạy, đếm lượt để ước tính chi phí, đặt
    `lan_chay_ke` khi lưu;
  • Mark: nhịp 30 giây quyết định mốc nào chạy, mốc nào lỡ, mốc kế tiếp (Mark import được gói
    `dashboard` vì cùng repo; venv dashboard thì KHÔNG có module nào của Mark).

Bốn kiểu (giờ Việt Nam UTC+7, không có giờ mùa hè), `cau_hinh` JSON:
  • moi_n_gio  {"moi_gio": 1|2|3|4|6|8|12, "tu": "07:00", "den": "23:00", "thu": [1..7]}
               mốc tu, tu+N giờ… tới hết `den`, trong các ngày `thu` ([] = mọi ngày).
  • hang_ngay  {"gio": ["07:00", "19:30"], "thu": [...]}   giờ cụ thể, ngày tuỳ chọn.
  • hang_tuan  {"gio": ["09:00"], "thu": [2, 4, 6]}       ngày trong tuần (bắt buộc) + giờ.
  • chien_dich {"tu_luc": "2026-10-20T08:00", "den_luc": "2026-10-22T22:00", "moi_phut": 60}
               từ lúc → tới lúc, mỗi N phút (≥ 30). Đang diễn ra thì các lịch thường của cùng dự
               án NHƯỜNG (không chạy chồng); qua `den_luc` thì tự hết (mốc kế = None).
`thu` theo `isoweekday`: 1 = Thứ 2 … 7 = Chủ nhật.
"""
from __future__ import annotations

import datetime as dt
import itertools
import re
from collections.abc import Iterator

VN = dt.timezone(dt.timedelta(hours=7))
KIEU = {"moi_n_gio": "Mỗi N giờ", "hang_ngay": "Hằng ngày", "hang_tuan": "Hằng tuần",
        "chien_dich": "Chiến dịch"}
MOI_GIO = (1, 2, 3, 4, 6, 8, 12)
THU = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}
LUOT_NGAY_TOI_DA = 96          # mốc mỗi ngày tối đa của một lịch
PHUT_TOI_THIEU = 30            # chiến dịch: tối thiểu 30 phút một lượt
PHUT_TOI_DA = 7 * 24 * 60      # chiến dịch: tối đa một lượt mỗi tuần
CHIEN_DICH_NGAY_TOI_DA = 92    # chiến dịch dài nhất ~ một quý
TRE_TOI_DA = dt.timedelta(minutes=30)   # mốc lỡ (Mark tắt) còn chạy bù nếu lỡ chưa quá 30 phút
GAN_QUA = dt.timedelta(minutes=30)      # hai mốc gần hơn thế: lượt sau thường bị bỏ (lượt trước chưa xong)
TEN_TOI_DA = 100
_NAM_TOI_DA = 2100             # chặn vòng lặp vô hạn / tràn năm với cấu hình hỏng
_RE_GIO = re.compile(r"(\d{1,2}):(\d{2})")
_RE_LUC = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})(?::\d{2})?")


#: Nhãn ngắn của `ket_qua_cuoi.ma_loi` (Mark ghi — `quet_tu_dong.py`, `theo_doi.tao_luot`).
NHAN_MA_LOI = {
    "dang_chay": "lượt trước còn chạy", "du_an_tat": "dự án đang tắt",
    "khong_co_gi": "không có nguồn tới hạn", "het_ngan_sach": "hết ngân sách tháng",
    "het_ngan_sach_apify": "hết ngân sách Apify", "nang_luc_tat": "công tắc console tắt",
    "khong_quet_duoc": "không quét được nguồn", "tu_choi": "việc nền từ chối",
    "kho_loi": "kho lỗi", "khong_co_du_an": "dự án không còn", "trung": "trùng việc cũ",
    "lo": "lỡ mốc (Mark tắt)", "nhuong": "nhường chiến dịch", "loi": "lỗi"}


class LoiLich(ValueError):
    """Cấu hình lịch sai. Câu thông báo hiển thị thẳng cho người dùng (tiếng Việt)."""


# ───────────────────────────── đọc/ghi giờ ─────────────────────────────
def _gio(s, ten: str = "Giờ") -> dt.time:
    m = _RE_GIO.fullmatch(str(s or "").strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise LoiLich(f"{ten} phải có dạng HH:MM (00:00–23:59), vd 07:30.")
    return dt.time(int(m.group(1)), int(m.group(2)))


def _chu_gio(t: dt.time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def _luc(s, ten: str) -> dt.datetime:
    """'YYYY-MM-DDTHH:MM' (ô datetime-local, giờ VN) -> datetime có múi giờ VN."""
    m = _RE_LUC.fullmatch(str(s or "").strip())
    if not m:
        raise LoiLich(f"{ten} phải có dạng ngày + giờ, vd 2026-10-20 08:00.")
    try:
        x = dt.datetime(*(int(m.group(i)) for i in range(1, 6)), tzinfo=VN)
    except ValueError:
        raise LoiLich(f"{ten} không phải ngày giờ có thật.") from None
    if not 2000 <= x.year <= _NAM_TOI_DA:
        raise LoiLich(f"{ten} phải trong khoảng năm 2000–{_NAM_TOI_DA}.")
    return x


def chu_luc(x: dt.datetime) -> str:
    """datetime -> 'YYYY-MM-DDTHH:MM' giờ VN (dạng lưu trong cau_hinh, cũng là value của ô
    datetime-local)."""
    return _vn(x).strftime("%Y-%m-%dT%H:%M")


def _vn(x: dt.datetime) -> dt.datetime:
    """Về giờ VN. datetime không múi giờ coi là giờ VN (chuỗi trong cau_hinh là giờ VN)."""
    return x.replace(tzinfo=VN) if x.tzinfo is None else x.astimezone(VN)


def _cac_gio(s) -> list[dt.time]:
    """'07:00, 12:00 19:30' hoặc list -> các giờ đã sắp, bỏ trùng."""
    phan = s if isinstance(s, (list, tuple)) else re.split(r"[,;\s]+", str(s or ""))
    ra = sorted({_gio(x) for x in phan if str(x).strip()})
    if not ra:
        raise LoiLich("Chưa nhập giờ chạy nào (vd 07:00, 12:00, 19:30).")
    if len(ra) > LUOT_NGAY_TOI_DA:
        raise LoiLich(f"Tối đa {LUOT_NGAY_TOI_DA} giờ chạy mỗi ngày.")
    return ra


def _cac_thu(v) -> list[int]:
    """Ngày trong tuần (1 = T2 … 7 = CN) đã kiểm, sắp, bỏ trùng; số lạ thì bỏ."""
    ra = set()
    for x in v or []:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 7:
            ra.add(n)
    return sorted(ra)


# ───────────────────────────── kiểm biểu mẫu ─────────────────────────────
def _bat(v) -> bool:
    return str(v or "").strip().lower() in ("1", "on", "true", "co")


def chuan_hoa(form: dict, bay_gio: dt.datetime) -> dict:
    """Biểu mẫu (hoặc query xem trước) -> {"kieu", "ten", "cau_hinh", "quet_moi_nguon", "bat"}.
    Ném `LoiLich` với câu dễ hiểu. Chỉ đọc các ô của đúng kiểu đã chọn.

    Ô: kieu; ten; bat; quet_moi_nguon; thu_1…thu_7 (ô đánh dấu); moi_gio, tu, den (mỗi N giờ);
    gio (giờ cụ thể, cách nhau dấu phẩy); tu_luc, den_luc, moi, don_vi = phut|gio (chiến dịch)."""
    kieu = str(form.get("kieu") or "").strip()
    if kieu not in KIEU:
        raise LoiLich("Chọn kiểu lịch: mỗi N giờ, hằng ngày, hằng tuần hoặc chiến dịch.")
    thu = _cac_thu(i for i in range(1, 8) if _bat(form.get(f"thu_{i}")))
    if kieu == "moi_n_gio":
        try:
            n = int(str(form.get("moi_gio") or "").strip())
        except ValueError:
            n = 0
        if n not in MOI_GIO:
            raise LoiLich("Mỗi N giờ: N là 1, 2, 3, 4, 6, 8 hoặc 12.")
        tu, den = _gio(form.get("tu") or "00:00", "Giờ bắt đầu"), _gio(
            form.get("den") or "23:59", "Giờ kết thúc")
        if den < tu:
            raise LoiLich("Khung giờ: giờ kết thúc phải sau giờ bắt đầu (cùng một ngày).")
        ch = {"moi_gio": n, "tu": _chu_gio(tu), "den": _chu_gio(den), "thu": thu}
    elif kieu in ("hang_ngay", "hang_tuan"):
        if kieu == "hang_tuan" and not thu:
            raise LoiLich("Hằng tuần: chọn ít nhất một ngày trong tuần.")
        ch = {"gio": [_chu_gio(t) for t in _cac_gio(form.get("gio"))], "thu": thu}
    else:
        tu, den = _luc(form.get("tu_luc"), "Bắt đầu"), _luc(form.get("den_luc"), "Kết thúc")
        if den <= tu:
            raise LoiLich("Chiến dịch: thời điểm kết thúc phải sau thời điểm bắt đầu.")
        if den - tu > dt.timedelta(days=CHIEN_DICH_NGAY_TOI_DA):
            raise LoiLich(f"Chiến dịch dài tối đa {CHIEN_DICH_NGAY_TOI_DA} ngày — chia thành "
                          "nhiều chiến dịch hoặc dùng lịch hằng ngày.")
        if den <= _vn(bay_gio):
            raise LoiLich("Chiến dịch đã kết thúc — chọn thời điểm kết thúc trong tương lai.")
        try:
            moi = int(str(form.get("moi") or "").strip())
        except ValueError:
            moi = 0
        don_vi = str(form.get("don_vi") or "phut").strip()
        if don_vi not in ("phut", "gio") or moi <= 0:
            raise LoiLich("Chiến dịch: nhập khoảng cách giữa hai lượt (số phút hoặc số giờ).")
        phut = moi * (60 if don_vi == "gio" else 1)
        if phut < PHUT_TOI_THIEU:
            raise LoiLich(f"Chiến dịch: tối thiểu {PHUT_TOI_THIEU} phút một lượt (một lượt quét "
                          "thường mất 5–20 phút).")
        if phut > PHUT_TOI_DA:
            raise LoiLich("Chiến dịch: tối đa 7 ngày một lượt.")
        ch = {"tu_luc": chu_luc(tu), "den_luc": chu_luc(den), "moi_phut": phut}
    if luot_moi_ngay(kieu, ch) > LUOT_NGAY_TOI_DA:
        raise LoiLich(f"Tối đa {LUOT_NGAY_TOI_DA} lượt mỗi ngày.")
    if moc_ke(kieu, ch, bay_gio) is None:
        raise LoiLich("Lịch này không còn mốc chạy nào trong tương lai.")
    ten = re.sub(r"\s+", " ", str(form.get("ten") or "")).strip()[:TEN_TOI_DA]
    return {"kieu": kieu, "ten": ten or mo_ta(kieu, ch)[:TEN_TOI_DA], "cau_hinh": ch,
            "quet_moi_nguon": _bat(form.get("quet_moi_nguon")), "bat": _bat(form.get("bat"))}


def tu_form_mac_dinh(bay_gio: dt.datetime) -> dict:
    """Giá trị ô của biểu mẫu TẠO mới (mỗi 2 giờ 07:00–23:00, mọi ngày)."""
    b = _vn(bay_gio).replace(second=0, microsecond=0)
    tu = (b + dt.timedelta(hours=1)).replace(minute=0)
    return {"kieu": "moi_n_gio", "ten": "", "bat": True, "quet_moi_nguon": False,
            "moi_gio": 2, "tu": "07:00", "den": "23:00", "gio": "08:00, 20:00", "thu": [],
            "tu_luc": chu_luc(tu), "den_luc": chu_luc(tu + dt.timedelta(days=3)),
            "moi": 1, "don_vi": "gio"}


def tu_form(lich: dict, bay_gio: dt.datetime) -> dict:
    """Dòng `lich_quet` -> giá trị ô của biểu mẫu SỬA (ô của kiểu khác giữ mặc định)."""
    f = tu_form_mac_dinh(bay_gio)
    ch = lich.get("cau_hinh") if isinstance(lich.get("cau_hinh"), dict) else {}
    f.update(kieu=lich.get("kieu") or "moi_n_gio", ten=lich.get("ten") or "",
             bat=bool(lich.get("bat")), quet_moi_nguon=bool(lich.get("quet_moi_nguon")),
             thu=_cac_thu(ch.get("thu")))
    if f["kieu"] == "moi_n_gio":
        f.update(moi_gio=ch.get("moi_gio") or 2, tu=ch.get("tu") or "07:00",
                 den=ch.get("den") or "23:00")
    elif f["kieu"] in ("hang_ngay", "hang_tuan"):
        f["gio"] = ", ".join(str(x) for x in ch.get("gio") or [])
    elif f["kieu"] == "chien_dich":
        phut = int(ch.get("moi_phut") or 60)
        f.update(tu_luc=ch.get("tu_luc") or f["tu_luc"], den_luc=ch.get("den_luc") or f["den_luc"],
                 moi=phut // 60 if phut % 60 == 0 else phut,
                 don_vi="gio" if phut % 60 == 0 else "phut")
    return f


def gia_tri_tu_form(form: dict, bay_gio: dt.datetime) -> dict:
    """Biểu mẫu vừa gửi (có thể sai) -> giá trị ô để vẽ lại biểu mẫu kèm lỗi, không mất chữ đã gõ."""
    f = tu_form_mac_dinh(bay_gio)
    for k in ("kieu", "ten", "moi_gio", "tu", "den", "gio", "tu_luc", "den_luc", "moi", "don_vi"):
        if k in form:
            f[k] = str(form.get(k) or "")[:600]
    f.update(thu=[i for i in range(1, 8) if _bat(form.get(f"thu_{i}"))],
             bat=_bat(form.get("bat")), quet_moi_nguon=_bat(form.get("quet_moi_nguon")))
    return f


def bieu_mau(gia_tri: dict) -> dict:
    """Giá trị ô (`tu_form`…) -> dạng biểu mẫu gửi lên (thu_1…thu_7, '1') cho `chuan_hoa`."""
    f = {k: v for k, v in gia_tri.items() if k not in ("thu", "bat", "quet_moi_nguon")}
    f.update({f"thu_{i}": "1" for i in _cac_thu(gia_tri.get("thu"))})
    f.update(bat="1" if gia_tri.get("bat") else "",
             quet_moi_nguon="1" if gia_tri.get("quet_moi_nguon") else "")
    return {k: str(v) for k, v in f.items()}


# ───────────────────────────── tính mốc ─────────────────────────────
def _gio_trong_ngay(kieu: str, ch: dict) -> list[dt.time]:
    """Các giờ chạy trong MỘT ngày được chạy (lịch lặp). Cấu hình hỏng -> []."""
    try:
        if kieu == "moi_n_gio":
            n = int(ch.get("moi_gio") or 0)
            tu, den = _gio(ch.get("tu") or "00:00"), _gio(ch.get("den") or "23:59")
            if n not in MOI_GIO or den < tu:
                return []
            ra, phut = [], tu.hour * 60 + tu.minute
            while phut <= den.hour * 60 + den.minute:
                ra.append(dt.time(phut // 60, phut % 60))
                phut += n * 60
            return ra
        return _cac_gio(ch.get("gio") or [])
    except (LoiLich, TypeError, ValueError, AttributeError):
        return []


def _khung_chien_dich(ch: dict) -> tuple[dt.datetime, dt.datetime, int] | None:
    try:
        tu, den = _luc(ch.get("tu_luc"), "Bắt đầu"), _luc(ch.get("den_luc"), "Kết thúc")
        phut = int(ch.get("moi_phut") or 0)
    except (LoiLich, TypeError, ValueError, AttributeError):
        return None
    if phut < 1 or den < tu:
        return None
    return tu, den, phut


def lap_moc(kieu: str, ch: dict, sau: dt.datetime) -> Iterator[dt.datetime]:
    """Các mốc chạy (giờ VN, có múi giờ) LỚN HƠN HẲN `sau`, tăng dần. Lịch lặp thì vô hạn (tới
    năm 2100); chiến dịch thì dừng ở `den_luc`. Cấu hình hỏng thì không sinh mốc nào."""
    ch = ch if isinstance(ch, dict) else {}
    sau = _vn(sau)
    if kieu == "chien_dich":
        k = _khung_chien_dich(ch)
        if not k:
            return
        tu, den, phut = k
        buoc = dt.timedelta(minutes=phut)
        i = 0 if sau < tu else (sau - tu) // buoc + 1
        x = tu + i * buoc
        while x <= den:
            yield x
            x += buoc
        return
    if kieu not in KIEU:
        return
    gio = _gio_trong_ngay(kieu, ch)
    thu_goc = ch.get("thu") or []
    thu = set(_cac_thu(thu_goc))
    if not gio or (thu_goc and not thu) or (kieu == "hang_tuan" and not thu):
        return
    ngay = sau.date()
    while ngay.year <= _NAM_TOI_DA:
        if not thu or ngay.isoweekday() in thu:
            for t in gio:
                x = dt.datetime.combine(ngay, t, VN)
                if x > sau:
                    yield x
        ngay += dt.timedelta(days=1)


def moc_ke(kieu: str, ch: dict, sau: dt.datetime) -> dt.datetime | None:
    """Mốc chạy đầu tiên SAU HẲN `sau`; None khi lịch không còn mốc (chiến dịch đã hết)."""
    return next(lap_moc(kieu, ch, sau), None)


def cac_moc(kieu: str, ch: dict, sau: dt.datetime, so: int = 10) -> list[dt.datetime]:
    ra = []
    for x in lap_moc(kieu, ch, sau):
        ra.append(x)
        if len(ra) >= so:
            break
    return ra


def dem_moc(kieu: str, ch: dict, tu: dt.datetime, den: dt.datetime,
            tru: list[tuple[dt.datetime, dt.datetime]] = ()) -> int:
    """Số mốc trong (tu, den], bỏ mốc rơi vào các khoảng `tru` (khung chiến dịch, hai đầu đều
    tính)."""
    n = 0
    for x in lap_moc(kieu, ch, tu):
        if x > _vn(den):
            break
        if not any(a <= x <= b for a, b in tru):
            n += 1
    return n


def luot_moi_ngay(kieu: str, ch: dict) -> float:
    """Số lượt tối đa trong MỘT ngày được chạy (để chặn > 96 lượt/ngày và mô tả)."""
    if kieu == "chien_dich":
        k = _khung_chien_dich(ch)
        return 1440 / k[2] if k else 0
    return len(_gio_trong_ngay(kieu, ch))


def moc_gan_qua(kieu: str, ch: dict) -> bool:
    """Có hai mốc liên tiếp trong ngày cách nhau < 30 phút (lượt sau thường bị bỏ vì lượt
    trước chưa xong) — chỉ để cảnh báo, không chặn."""
    if kieu == "chien_dich":
        return False
    g = [t.hour * 60 + t.minute for t in _gio_trong_ngay(kieu, ch)]
    return any(b - a < GAN_QUA.total_seconds() / 60 for a, b in itertools.pairwise(g))


# ───────────────────────────── nhịp quét của Mark ─────────────────────────────
def quyet_dinh(kieu: str, ch: dict, lan_chay_ke: dt.datetime | None,
               bay_gio: dt.datetime) -> tuple[dt.datetime | None, dt.datetime | None,
                                              dt.datetime | None]:
    """Một lịch tới hạn ở nhịp này. -> (mốc CHẠY bây giờ | None, mốc LỠ | None, mốc kế mới).

    • Chưa tới hạn (`lan_chay_ke` > bây giờ hoặc None): (None, None, lan_chay_ke) — không đổi gì.
    • Có mốc ≥ `lan_chay_ke` rơi vào 30 phút vừa qua: chạy ĐÚNG MỘT lần cho mốc mới nhất đó —
      Mark tắt 2 giờ thì không chạy bù 2 lượt.
    • Mốc tới hạn đã lỡ quá 30 phút: không chạy, báo mốc lỡ.
    Mốc kế luôn là mốc đầu tiên SAU bây giờ, nên một mốc không bao giờ chạy hai lần."""
    bay_gio = _vn(bay_gio)
    if lan_chay_ke is None or _vn(lan_chay_ke) > bay_gio:
        return None, None, lan_chay_ke
    ke = moc_ke(kieu, ch, bay_gio)
    tu = max(_vn(lan_chay_ke), bay_gio - TRE_TOI_DA) - dt.timedelta(microseconds=1)
    chay = None
    for x in lap_moc(kieu, ch, tu):
        if x > bay_gio:
            break
        chay = x                       # mốc MỚI NHẤT trong cửa sổ
    return chay, (None if chay else _vn(lan_chay_ke)), ke


def khung_chien_dich(lich: dict) -> tuple[dt.datetime, dt.datetime] | None:
    if lich.get("kieu") != "chien_dich":
        return None
    k = _khung_chien_dich(lich.get("cau_hinh") or {})
    return (k[0], k[1]) if k else None


def chien_dich_dang_chay(cac_lich: list[dict], bay_gio: dt.datetime) -> dict | None:
    """Chiến dịch ĐANG BẬT và đang trong khung giờ (của các lịch cùng một dự án), nếu có."""
    b = _vn(bay_gio)
    for x in cac_lich:
        k = khung_chien_dich(x)
        if x.get("bat") and k and k[0] <= b <= k[1]:
            return x
    return None


def trang_thai(lich: dict, cac_lich: list[dict], bay_gio: dt.datetime) -> tuple[str, str]:
    """(mã, nhãn) hiển thị: tat | ket_thuc | dang_chien_dich | cho_chien_dich | nhuong | bat."""
    b = _vn(bay_gio)
    k = khung_chien_dich(lich)
    if k and b > k[1]:
        return "ket_thuc", "Đã kết thúc"
    if not lich.get("bat"):
        return "tat", "Đang tắt"
    if k:
        return ("dang_chien_dich", "Đang chiến dịch") if b >= k[0] else (
            "cho_chien_dich", "Chờ chiến dịch")
    cd = chien_dich_dang_chay([x for x in cac_lich if x.get("id") != lich.get("id")], b)
    if cd:
        return "nhuong", f"Nhường chiến dịch #{cd.get('id')}"
    return "bat", "Đang bật"


def dem_luot_du_an(cac_lich: list[dict], tu: dt.datetime, den: dt.datetime) -> dict[int, int]:
    """Số lượt sẽ chạy trong (tu, den] của từng lịch ĐANG BẬT (các lịch của MỘT dự án): mốc
    của lịch thường rơi vào khung một chiến dịch đang bật thì không tính (nhường chiến dịch)."""
    khung = [k for x in cac_lich if x.get("bat") and (k := khung_chien_dich(x))]
    ra = {}
    for x in cac_lich:
        if not x.get("bat"):
            continue
        tru = [] if x.get("kieu") == "chien_dich" else khung
        ra[x.get("id")] = dem_moc(x.get("kieu") or "", x.get("cau_hinh") or {}, tu, den, tru)
    return ra


# ───────────────────────────── chữ hiển thị ─────────────────────────────
def chu_thu(thu: list[int]) -> str:
    """[1,2,3,4,5] -> 'T2–T6'; [6,7] -> 'T7, CN'; [] -> 'mọi ngày'."""
    thu = _cac_thu(thu)
    if not thu or len(thu) == 7:
        return "mọi ngày"
    doan, dau = [], thu[0]
    for a, b in zip(thu, thu[1:] + [None]):
        if b != a + 1:
            doan.append(THU[dau] if dau == a else (f"{THU[dau]}, {THU[a]}" if a == dau + 1
                                                    else f"{THU[dau]}–{THU[a]}"))
            dau = b
    return ", ".join(doan)


def _chu_phut(phut: int) -> str:
    if phut % 60 == 0:
        return f"{phut // 60} giờ"
    return f"{phut} phút" if phut < 60 else f"{phut // 60} giờ {phut % 60} phút"


def mo_ta(kieu: str, ch: dict) -> str:
    """Một dòng tả lịch, vd 'Mỗi 2 giờ, 07:00–23:00, T2–T6'."""
    ch = ch if isinstance(ch, dict) else {}
    thu = chu_thu(ch.get("thu") or [])
    if kieu == "moi_n_gio":
        return f"Mỗi {ch.get('moi_gio')} giờ, {ch.get('tu')}–{ch.get('den')}, {thu}"
    if kieu in ("hang_ngay", "hang_tuan"):
        gio = ", ".join(str(x) for x in ch.get("gio") or [])
        return f"{'Hằng ngày' if kieu == 'hang_ngay' else 'Hằng tuần'} {gio}, {thu}"
    if kieu == "chien_dich":
        k = _khung_chien_dich(ch)
        if not k:
            return "Chiến dịch (cấu hình hỏng)"
        return (f"Chiến dịch {k[0]:%d/%m %H:%M} → {k[1]:%d/%m %H:%M}, mỗi "
                f"{_chu_phut(k[2])}")
    return "Lịch không rõ kiểu"


def chu_moc(x: dt.datetime, bay_gio: dt.datetime) -> str:
    """'Hôm nay 16:00' / 'Mai 07:00' / 'T5 16/10 07:00' (thêm năm khi khác năm nay)."""
    x, b = _vn(x), _vn(bay_gio)
    d = (x.date() - b.date()).days
    gio = f"{x:%H:%M}"
    if d == 0:
        return f"Hôm nay {gio}"
    if d == 1:
        return f"Mai {gio}"
    nam = f"/{x.year}" if x.year != b.year else ""
    return f"{THU[x.isoweekday()]} {x:%d/%m}{nam} {gio}"


def chu_con(x: dt.datetime, bay_gio: dt.datetime) -> str:
    """Khoảng tới mốc: 'còn 45 phút', 'còn 2 giờ 15 phút', 'còn 3 ngày'."""
    s = (_vn(x) - _vn(bay_gio)).total_seconds()
    if s < 60:
        return "sắp chạy"
    phut = int(s // 60)
    if phut < 60:
        return f"còn {phut} phút"
    if phut < 48 * 60:
        return f"còn {phut // 60} giờ" + (f" {phut % 60} phút" if phut % 60 else "")
    return f"còn {phut // 1440} ngày"
