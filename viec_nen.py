"""Việc NỀN — quét lớn (tới 10.000 bài / 30.000 bình luận) chạy ngoài lượt trả lời.

Vì sao có (chủ agent chốt 01–02/10/2026): một yêu cầu phải quét được 10.000 bài, mà một
lượt trả lời chỉ có ~135 giây (`AGENT_REPLY_TIMEOUT` 180 trừ phần model viết). Nhét 10.000
bài vào đó là chắc chắn quá giờ, run Apify bị huỷ giữa chừng, tiền vẫn mất. Nên lượt lớn
thành MỘT VIỆC: tool trả `ma_viec` trong ~2 giây, việc chạy nền tới 45 phút, xong thì Mark
tự nhắn kết quả (link sheet, số bài, chi phí thật) vào đúng cuộc chat đã hỏi.

Sổ việc: `.audit/viec-nen/<ma>.json` (ghi nguyên tử tmp + os.replace dưới khoá), dòng đã
chuẩn hoá tràn ra `.audit/viec-nen/<ma>/rows-<nền tảng>.jsonl`. Khởi động lại bot
(`khoi_dong()` gọi từ run.py) thì đọc tiếp đúng run id đã ghi — KHÔNG POST lại.

Ranh giới tiền vẫn là trần CỨNG (`ngan_sach_usd` của việc ≤ trần console ≤ 50 USD, và
≤ phần còn lại của tháng − 0,30 USD − phần các việc nền KHÁC đang giữ). Xác nhận chi phí
với người dùng ("Chạy nhé?") là việc của lời dặn prompt, không chặn ở đây.

Quyền chủ (review 02/10/2026): mỗi agent một khoá `.chu-<agent>.lock` mang SỐ THẾ HỆ tăng
dần. Tiến trình nào nhận quyền thì đóng số đó vào việc; mọi lần lưu sổ / POST / ghi sheet /
nhắn tin đều kiểm số thế hệ — tiến trình cũ (cửa sổ cmd treo, Stop+Start lệch) bị tiến
trình mới giành quyền thì dừng ngay, không chạy song song hai bản.

Công tắc env:
    SOCIAL_QUET_NEN=0        tắt hẳn chạy nền (lượt lớn bị kẹp về cỡ tại chỗ, có báo)
    SOCIAL_NEN_DONG_THOI=1   số việc lớn chạy cùng lúc
    SOCIAL_NEN_HAN_PHUT=45   hạn mỗi việc (kẹp 10–120 phút)
    SOCIAL_NEN_GIU_NGAY=14   giữ việc đã xong bao nhiêu ngày (dọn khi khởi động + mỗi ngày)
    SOCIAL_NEN_TOI_DA_MB=2048  trần dung lượng thư mục việc nền (xoá việc xong cũ nhất trước)
    SOCIAL_NEN_THU_MUC       thư mục sổ (bộ thử)
    SOCIAL_NEN_TU_CHAY=0     không tự dựng luồng điều phối (bộ thử)
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
import queue
import re
import shutil
import threading
import time
import uuid

import apify_tool as A

from tools.registry import registry, tool_error, tool_result  # type: ignore

_VN = A._VN_TZ
# Thứ tự khoá cố định: Viec._khoa (khoá của MỘT việc) rồi mới tới _KHOA (sổ chung). Ai đang
# giữ _KHOA thì không được xin khoá của một việc đang chạy.
_KHOA = threading.RLock()
_HANG_TOI_DA = 3            # việc chờ trong hàng (không tính việc đang chạy)
_TRUNG_GIAY = 6 * 3600      # cùng tham số trong 6 giờ -> trả lại đúng việc cũ
_KHOA_CHU_CU_GIAY = 120     # khoá chủ không có nhịp tim quá chừng này = tiến trình đã chết
_DU_TRU_THANG = 0.30

TRANG_THAI_DANG = ("xep_hang", "dang_cao", "dang_loc", "dang_ghi")
TRANG_THAI_XONG = ("xong", "xong_mot_phan", "loi", "da_huy")
_NHAN = {"xep_hang": "đang xếp hàng", "dang_cao": "đang cào", "dang_loc": "đang lọc/AI",
         "dang_ghi": "đang ghi sheet", "xong": "xong", "xong_mot_phan": "xong một phần",
         "loi": "lỗi", "da_huy": "đã huỷ"}
PHAN_XONG = ("xong", "mot_phan", "loi", "da_huy")

_bay_gio = time.time        # tách tên để bộ thử giả đồng hồ treo tường
_ngu = time.sleep


class MatQuyen(RuntimeError):
    """Tiến trình này không còn là chủ (tiến trình khác giành khoá với số thế hệ lớn hơn)."""


def _so(ten: str, md: int, lo: int, hi: int) -> int:
    return A._so_env(ten, md, lo, hi)


def bat() -> bool:
    return os.environ.get("SOCIAL_QUET_NEN", "1").strip() != "0"


def han_phut() -> int:
    return _so("SOCIAL_NEN_HAN_PHUT", 45, 10, 120)


def agent_id() -> str:
    return (os.environ.get("LSR_AGENT_ID") or "").strip() or "AG-SOCIAL-LISTENING"


def thu_muc():
    return A._thu_muc_nen()


def _iso(ts: float | None) -> str | None:
    return (datetime.datetime.fromtimestamp(ts, _VN).isoformat(timespec="seconds")
            if ts else None)


def _che(s) -> str:
    return A._che_token(s)[:400]


# ───────────────────────────── sổ việc ─────────────────────────────
def _duong(ma: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", ma or ""):
        raise ValueError("mã việc không hợp lệ")
    return thu_muc() / f"{ma}.json"


def doc(ma: str) -> dict | None:
    try:
        return json.loads(_duong(ma).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def luu(d: dict) -> None:
    """Ghi nguyên tử: tmp rồi os.replace, dưới khoá — tắt máy giữa chừng không làm hỏng
    sổ (chỉ mất lần ghi cuối). `d` phải là bản CHỤP không ai sửa (Viec.luu deepcopy)."""
    with _KHOA:
        f = _duong(d["ma"])
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{f.name}.{uuid.uuid4().hex[:6]}.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, f)


def tat_ca() -> list[dict]:
    ra = []
    try:
        ds = sorted(thu_muc().glob("*.json"))
    except OSError:
        return []
    for f in ds:
        if f.name.startswith(("youtube-", "toc-do")):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("ma"):
            ra.append(d)
    ra.sort(key=lambda d: d.get("tao_ts") or 0)
    return ra


# ───────────────────────────── quyền chủ + số thế hệ ─────────────────────────────
_QUYEN: dict = {}            # {"dir": thư mục, "the": số thế hệ của tiến trình này}
_NHIP: dict = {}


def _ten_an_toan(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", s)[:64]


def _khoa_chu():
    return thu_muc() / f".chu-{_ten_an_toan(agent_id())}.lock"


def _doc_khoa_chu() -> dict:
    try:
        return json.loads(_khoa_chu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ghi_khoa_chu(the: int) -> None:
    f = _khoa_chu()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f"{f.name}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps({"pid": os.getpid(), "agent_id": agent_id(),
                               "heartbeat": _bay_gio(), "the": the}), encoding="utf-8")
    os.replace(tmp, f)


def _pid_song(pid) -> bool:
    """Tiến trình `pid` còn sống không. KHÔNG dùng os.kill(pid, 0) trên Windows: ở đó nó
    gọi TerminateProcess — hỏi thăm thành giết."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            ma = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(ma))) and ma.value == 259
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _chu_khac() -> dict | None:
    """Khoá đang thuộc một tiến trình KHÁC còn sống, nhịp tim còn mới -> khoá đó; không thì
    None. Stop+Start trong vòng 2 phút: nhịp tim còn "mới" nhưng pid cũ đã chết — vẫn None."""
    k = _doc_khoa_chu()
    if (k and k.get("pid") != os.getpid() and _pid_song(k.get("pid"))
            and _bay_gio() - float(k.get("heartbeat") or 0) < _KHOA_CHU_CU_GIAY):
        return k
    return None


def _so_the_moi(cu: int) -> int:
    """Số thế hệ tăng dần, KHÔNG trùng giữa hai tiến trình giành quyền cùng lúc: mỗi số
    được nhận bằng một file tạo độc quyền (O_EXCL)."""
    goc = thu_muc()
    goc.mkdir(parents=True, exist_ok=True)
    n = int(cu) + 1
    for _ in range(1000):
        try:
            fd = os.open(goc / f".the-{_ten_an_toan(agent_id())}-{n}",
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return n
        except FileExistsError:
            n += 1
    raise OSError("không cấp được số thế hệ")


def _lay_quyen(ep: bool = False) -> bool:
    """Nhận quyền chủ cho thư mục hiện tại. -> False nếu tiến trình khác đang giữ."""
    with _KHOA:
        if _QUYEN.get("dir") == str(thu_muc()) and con_quyen():
            return True
        k = _doc_khoa_chu()
        if not ep and _chu_khac():
            return False
        cac = [int(k.get("the") or 0)]
        try:
            cac += [int(f.name.rsplit("-", 1)[1]) for f in
                    thu_muc().glob(f".the-{_ten_an_toan(agent_id())}-*")]
        except (OSError, ValueError):
            pass
        the = _so_the_moi(max(cac))
        _ghi_khoa_chu(the)
        _QUYEN.update(dir=str(thu_muc()), the=the)
        return True


def con_quyen() -> bool:
    """Tiến trình này còn là chủ: khoá trên đĩa mang ĐÚNG số thế hệ của mình."""
    if _QUYEN.get("dir") != str(thu_muc()) or not _QUYEN.get("the"):
        return False
    return int(_doc_khoa_chu().get("the") or 0) == int(_QUYEN["the"])


def the_cua_toi() -> int:
    return int(_QUYEN.get("the") or 0) if _QUYEN.get("dir") == str(thu_muc()) else 0


# ───────────────────────────── kênh trả kết quả ─────────────────────────────
def kenh_hien_tai() -> tuple[dict, str]:
    """Ghi lại NGAY lúc gọi tool: cuộc chat, người hỏi, job platform. Việc chạy xong 40
    phút sau thì contextvars của lượt trả lời đã mất — không ghi lúc này là không biết
    gửi kết quả về đâu."""
    try:
        import scheduler
        chat = scheduler.get_current_chat() or ""
        loai_chat = scheduler.get_current_chat_type() or ""
    except Exception:  # noqa: BLE001
        chat, loai_chat = "", ""
    try:
        import memory_store
        nguoi = memory_store.get_current_sender() or ""
    except Exception:  # noqa: BLE001
        nguoi = ""
    try:
        import lsr_platform
        job_id = lsr_platform.job_cua_phien(chat) if chat else None
    except Exception:  # noqa: BLE001
        job_id = None
    return kenh_tu_chat(chat, job_id, loai_chat), nguoi


def kenh_tu_chat(chat: str, job_id=None, loai_chat: str = "") -> dict:
    """Kênh đẩy tin chủ động cho cuộc chat `chat` — dùng chung cho việc nền và tin trả
    lời muộn của vòng job (lsr_platform._chay_co_han)."""
    chat = chat or ""
    k = {"loai": "khac", "chat_id": chat, "app_id": "", "oc": "", "job_id": job_id,
         "loai_chat": loai_chat}
    if chat.startswith("lark:"):
        phan = chat.split(":", 2)
        if len(phan) == 3 and phan[2]:
            k.update(loai="lark_gateway", app_id=phan[1], oc=phan[2])
    elif chat.startswith("oc_"):
        k.update(loai="lark_truc_tiep", oc=chat)
    elif chat.startswith(("hoiquy-", "test", "thu-")) or not chat:
        k["loai"] = "khac"
    elif job_id:
        k["loai"] = "web"
    return k


def co_the_day(k: dict) -> bool:
    """Kênh `k` có đẩy tin chủ động được không (hồi quy, bộ thử, chat lạ thì không)."""
    return k.get("loai") in ("lark_gateway", "lark_truc_tiep", "web")


def day_theo_kenh(k: dict, van: str, kid: str) -> bool:
    """Gửi `van` MỘT lần qua kênh `k` (`kid` để khử trùng). True = đã đẩy; False = kênh
    không đẩy được. Lỗi mạng thì ném — người gọi tự thử lại."""
    loai = k.get("loai")
    if loai == "lark_gateway":
        import lsr_platform
        lsr_platform.gui_lark(k["oc"], van, k.get("app_id") or "", uuid=kid)
    elif loai == "lark_truc_tiep":
        import lark_client
        lark_client.send_text("chat_id", k["oc"], van, uuid=kid)
    elif loai == "web":
        import lsr_platform
        # Tạm thời (02/10/2026): console chưa có kênh đẩy tin chủ động cho agent;
        # sự kiện "message" gắn vào job gốc là chỗ duy nhất console đọc được.
        lsr_platform.bao_su_kien_job(k["job_id"], van, ma_su_kien=kid)
    else:
        return False
    return True


def _se_bao_qua(k: dict) -> str:
    return {"lark_gateway": "tin nhắn Lark vào đúng cuộc chat này",
            "lark_truc_tiep": "tin nhắn Lark vào đúng cuộc chat này",
            "web": "sự kiện của job trên console (tạm thời; mở lại cuộc chat để xem)",
            }.get(k.get("loai"), "không tự nhắn được — hỏi lại 'xong chưa' hoặc gõ /viec")


# ───────────────────────────── ngân sách tháng đang giữ ─────────────────────────────
def _da_tieu(d: dict) -> float:
    """Tiền đã tiêu (theo sổ) của các lượt con đã kết thúc trong một việc."""
    return sum(float(ph.get("usd_so") if ph.get("usd_so") is not None else ph.get("usd") or 0)
               for nt in (d.get("nen_tang") or {}).values() for ph in nt.get("phan") or []
               if ph.get("trang_thai") in PHAN_XONG)


def da_cam_ket(tru_ma: str | None = None) -> float:
    """USD các việc nền ĐANG DỞ (của agent này) còn được phép tiêu — đã "giữ" trong ngân
    sách tháng nhưng Apify chưa tính (review 02/10/2026: hai việc tạo gần nhau cùng thấy
    nguyên phần còn lại của tháng rồi cùng tiêu, vượt tháng). Đọc từ sổ nên đúng cả sau
    khi khởi động lại; việc kết thúc là tự trả phần giữ."""
    tong = 0.0
    for d in tat_ca():
        if (d.get("agent_id") != agent_id() or d.get("ma") == tru_ma
                or d.get("trang_thai") not in TRANG_THAI_DANG):
            continue
        tong += max(0.0, float(d.get("ngan_sach_usd") or 0) - _da_tieu(d))
    return round(tong, 4)


# ───────────────────────────── tạo việc ─────────────────────────────
def khoa_trung(loai: str, chat: str, tham_so: dict) -> str:
    chuan = json.dumps(tham_so, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(f"{agent_id()}|{chat}|{loai}|{chuan}".encode("utf-8")).hexdigest()


def ma_moi(loai: str) -> str:
    return (f"{'q' if loai == 'social_listen' else 'b'}"
            f"{datetime.datetime.fromtimestamp(_bay_gio(), _VN):%m%d%H%M}-{uuid.uuid4().hex[:5]}")


def tao_viec(loai: str, tham_so: dict, nen_tang: dict, uoc_tinh: dict,
             ngan_sach_usd: float, ghi_chu: list[str] | None = None, *,
             ma: str | None = None, con_lai_thang: float | None = None) -> dict:
    """Ghi việc mới vào sổ rồi đưa vào hàng. -> dict trả NGAY cho model (≤ ~2 giây).

    Cùng chat + cùng tham số trong 6 giờ thì trả lại việc cũ (model gọi lặp hoặc người
    dùng nhắn lại "quét đi") — không quét, không trả tiền hai lần. `con_lai_thang` (USD còn
    của tháng, nếu hỏi được): kiểm LẠI dưới khoá chung rằng ngân sách việc vẫn vừa sau khi
    trừ phần các việc khác đang giữ."""
    k, nguoi = kenh_hien_tai()
    kt = khoa_trung(loai, k["chat_id"], tham_so)
    now = _bay_gio()
    with _KHOA:
        cac = tat_ca()
        cu = next((d for d in reversed(cac) if d.get("khoa_trung") == kt
                   and now - (d.get("tao_ts") or 0) < _TRUNG_GIAY
                   and d.get("trang_thai") not in ("loi", "da_huy")), None)
        if cu:
            return _tom_tat_tao(cu, trung=True)
        if _chu_khac() and not con_quyen():
            return {"dang_chay_nen": False, "tu_choi": True,
                    "note": ("Một tiến trình bot KHÁC đang giữ quyền chạy việc nền (có thể bot "
                             "đang chạy hai bản). Không tạo việc ở bản này — báo người vận "
                             "hành tắt bản thừa rồi thử lại.")}
        dang = [d for d in cac if d.get("trang_thai") in TRANG_THAI_DANG
                and d.get("agent_id") == agent_id()]
        cua_chat = [d for d in dang if k["chat_id"] and
                    (d.get("kenh") or {}).get("chat_id") == k["chat_id"]]
        if cua_chat:
            return {"dang_chay_nen": False, "tu_choi": True, "ma_viec": cua_chat[-1]["ma"],
                    "note": (f"Cuộc chat này đã có một việc quét nền đang chạy "
                             f"({cua_chat[-1]['ma']}, {_NHAN[cua_chat[-1]['trang_thai']]}). Mỗi "
                             f"chat chỉ chạy một việc lớn một lúc — đợi xong (hỏi 'xong "
                             f"chưa') hoặc huỷ việc đó trước.")}
        cho = [d for d in dang if d.get("trang_thai") == "xep_hang"]
        if len(cho) >= _HANG_TOI_DA:
            return {"dang_chay_nen": False, "tu_choi": True,
                    "note": (f"Hàng đợi quét nền đã đủ {_HANG_TOI_DA} việc. Thử lại sau, "
                             f"hoặc thu nhỏ yêu cầu để chạy ngay.")}
        if con_lai_thang is not None:
            cam = da_cam_ket()
            duoc = round(max(0.0, con_lai_thang - _DU_TRU_THANG - cam), 2)
            if float(ngan_sach_usd) > duoc + 1e-9:
                return {"dang_chay_nen": False, "tu_choi": True, "vuot_ngan_sach": True,
                        "ngan_sach_con_usd": duoc,
                        "note": (f"CHƯA CHẠY: các việc nền khác đang giữ {cam:.2f} USD của "
                                 f"ngân sách tháng nên chỉ còn {duoc:.2f} USD cho việc mới "
                                 f"(xin {float(ngan_sach_usd):.2f}). Đợi việc kia xong, hoặc "
                                 f"chạy nhỏ hơn với `cat_theo_ngan_sach`=true.")}
        chay = [d for d in dang if d.get("trang_thai") != "xep_hang"]
        ma = ma or ma_moi(loai)
        d = {
            "ma": ma, "phien_ban": 2, "agent_id": agent_id(), "loai": loai,
            "trang_thai": "xep_hang", "tao_ts": now, "tao_luc": _iso(now),
            "bat_dau_ts": None, "han_chot_ts": None, "han_phut": han_phut(),
            "xong_ts": None, "kenh": k, "nguoi_yeu_cau": nguoi,
            "tham_so": tham_so, "khoa_trung": kt, "uoc_tinh": uoc_tinh,
            "ngan_sach_usd": round(float(ngan_sach_usd), 2), "nen_tang": nen_tang,
            "ghi_chu": list(ghi_chu or []), "phan_xu": {}, "sheet": {}, "chi_phi": {},
            "thong_bao": {"ket_qua": "", "lan_thu": 0, "loi": "", "da_gui": False},
            "huy": {"yeu_cau": False}, "ly_do_ket_thuc": "", "ket_qua": {},
            "dang_cho_truoc": len(chay) + len(cho), "the": 0, "run_muon": [],
        }
        luu(d)
    _dua_vao_hang(ma)
    return _tom_tat_tao(d)


def _tom_tat_tao(d: dict, trung: bool = False) -> dict:
    u = d.get("uoc_tinh") or {}
    truoc = d.get("dang_cho_truoc") or 0
    tt = "dang_chay" if d["trang_thai"] != "xep_hang" or not truoc else "xep_hang"
    han = d.get("han_chot_ts") or ((d.get("tao_ts") or _bay_gio()) + 60 * d["han_phut"]
                                   * (1 + truoc))
    k = d.get("kenh") or {}
    if d["trang_thai"] in TRANG_THAI_XONG:
        # Cùng yêu cầu đã chạy XONG trong 6 giờ: trả kết quả cũ, không quét lại.
        return {"dang_chay_nen": False, "da_xong_truoc": True, "ma_viec": d["ma"],
                "trang_thai_viec": d["trang_thai"], "trung_viec_cu": True,
                "sheet_url": (d.get("sheet") or {}).get("url"),
                "ket_qua": (d.get("thong_bao") or {}).get("ket_qua"),
                "note": (f"Cùng yêu cầu này đã chạy {_NHAN[d['trang_thai']]} trong 6 giờ qua "
                         f"(mã {d['ma']}) — KHÔNG quét lại. Chép `ket_qua` cho người dùng; "
                         f"muốn quét mới thì đổi phạm vi.")}
    return {
        "dang_chay_nen": True, "ma_viec": d["ma"], "trang_thai": tt,
        "trang_thai_viec": d["trang_thai"], "trung_viec_cu": trung,
        "uoc_tinh_phut": u.get("phut"), "uoc_tinh_usd": u.get("usd"),
        "ngan_sach_usd": d.get("ngan_sach_usd"), "han_chot": _iso(han),
        "se_bao_qua": _se_bao_qua(k),
        "note": ((f"Việc này ĐÃ có từ trước (cùng tham số trong 6 giờ) — trả lại mã cũ "
                  f"{d['ma']}, không quét lại. " if trung else "")
                 + f"ĐÃ CHUYỂN SANG CHẠY NỀN, mã việc {d['ma']}"
                 + (f", đang chờ {truoc} việc trước" if tt == "xep_hang" else "")
                 + f". Ước tính ~{u.get('phut')} phút, ~{u.get('usd')} USD (trần việc "
                 f"{d.get('ngan_sach_usd')} USD). Xong sẽ báo qua: {_se_bao_qua(k)}. Nói đúng "
                 f"như vậy với người dùng, kèm mã việc; hỏi tiến độ thì dùng `tra_viec_nen`, "
                 f"huỷ thì `huy_viec_nen`. CHƯA có sheet/số liệu — đừng bịa kết quả."),
    }


# ───────────────────────────── đối tượng việc đang chạy ─────────────────────────────
_SU_KIEN_HUY: dict[str, threading.Event] = {}
_DANG_CHAY: dict[str, "Viec"] = {}      # việc đang chạy trong tiến trình này


def su_kien_huy(ma: str) -> threading.Event:
    with _KHOA:
        return _SU_KIEN_HUY.setdefault(ma, threading.Event())


class _CoDung:
    """Cờ dừng cho lượt con (đặt vào `apify_tool._HUY`): người dùng huỷ (DA_HUY) hoặc việc
    tự đóng lượt con ở hạn chót / khi kết thúc (QUA_GIO)."""

    def __init__(self, v: "Viec"):
        self.v = v

    def is_set(self) -> bool:
        return self.v.huy.is_set() or self.v.dung.is_set()

    def ma(self) -> str:
        return "DA_HUY" if self.v.huy.is_set() else "QUA_GIO"


class Viec:
    """Bọc dict của một việc: lưu nguyên tử, hạn chót, huỷ, sổ dòng tràn, số thế hệ."""

    def __init__(self, d: dict):
        self.d = d
        self.huy = su_kien_huy(d["ma"])
        if (d.get("huy") or {}).get("yeu_cau"):
            self.huy.set()
        self.dung = threading.Event()
        self.co_dung = _CoDung(self)
        self._khoa = threading.RLock()

    @property
    def ma(self) -> str:
        return self.d["ma"]

    def kiem_quyen(self) -> None:
        """Ném MatQuyen nếu tiến trình này không còn là chủ của việc. Gọi trước MỌI tác
        dụng ra ngoài (lưu sổ, POST, ghi sheet, nhắn tin)."""
        the = int(self.d.get("the") or 0)
        if not the:
            return                       # việc chưa được điều phối (vừa tạo) — chưa ràng
        if the != the_cua_toi() or not con_quyen():
            self.dung.set()
            raise MatQuyen(f"việc {self.ma}: tiến trình này (thế hệ {the_cua_toi()}) không "
                           f"còn quyền (việc mang thế hệ {the})")
        dia = doc(self.ma) or {}
        if int(dia.get("the") or 0) > the:
            self.dung.set()
            raise MatQuyen(f"việc {self.ma} đã được thế hệ {dia.get('the')} nhận")

    def luu(self) -> None:
        with self._khoa:
            self.kiem_quyen()
            luu(copy.deepcopy(self.d))

    def dat(self, trang_thai: str) -> None:
        with self._khoa:
            self.d["trang_thai"] = trang_thai
            self.luu()

    def da_huy(self) -> bool:
        return self.huy.is_set()

    def da_ket_thuc(self) -> bool:
        return self.d.get("trang_thai") in TRANG_THAI_XONG

    def con_giay(self) -> float:
        return (self.d.get("han_chot_ts") or _bay_gio()) - _bay_gio()

    def qua_han(self) -> bool:
        return self.con_giay() <= 0

    def han_mono(self, chua_giay: float = 0.0) -> float:
        """Hạn chót đổi sang time.monotonic (Apify `_run_actor` dùng đồng hồ đó)."""
        return A._dong_ho() + self.con_giay() - chua_giay

    def cac_phan(self):
        for p, nt in (self.d.get("nen_tang") or {}).items():
            for ph in nt.get("phan") or []:
                yield p, ph

    def cap_nhat_phan(self, ph: dict, **kw) -> None:
        """Đổi trạng thái một lượt con. Việc đã KẾT THÚC thì luồng lô muộn không được đổi gì
        (review 02/10/2026): chỉ ghi chú, giữ run id để tính tiền, và huỷ run đó."""
        with self._khoa:
            if self.da_ket_thuc():
                rid = kw.get("run_id")
                self.d.setdefault("ghi_chu_muon", []).append(
                    f"{_iso(_bay_gio())} lượt {ph.get('id')} báo muộn: "
                    f"{_che({k: kw[k] for k in ('trang_thai', 'ma') if k in kw})}"[:200])
                if rid and rid not in self.d.setdefault("run_muon", []) and rid != ph.get(
                        "run_id"):
                    self.d["run_muon"].append(rid)
                self.luu()
                if rid and kw.get("trang_thai") in ("dang_chay", "dang_gui"):
                    _huy_run_id(rid)
                return
            ph.update(kw)
            self.luu()

    def thu_muc(self):
        f = thu_muc() / self.ma
        f.mkdir(parents=True, exist_ok=True)
        return f

    def ghi_dong(self, p: str, rows: list[tuple], phan_id: str) -> None:
        """Nối dòng đã chuẩn hoá vào `rows-<p>.jsonl`. Ghi TRƯỚC khi đánh dấu phần xong —
        tắt máy giữa hai bước thì lần sau ghi lại, trùng lặp đã có khử trùng theo link."""
        with self._khoa:
            if self.da_ket_thuc():
                return                    # lô muộn sau khi việc đã chốt: bỏ
            self.kiem_quyen()
            with open(self.thu_muc() / f"rows-{p}.jsonl", "a", encoding="utf-8") as fh:
                for d, dt in rows:
                    x = {k: v for k, v in d.items() if not k.startswith("__")}
                    x["__dt"] = dt.isoformat() if dt else None
                    x["__phan"] = phan_id
                    fh.write(json.dumps(x, ensure_ascii=False) + "\n")

    def doc_dong(self, p: str) -> list[tuple]:
        ra = []
        try:
            fh = open(self.thu_muc() / f"rows-{p}.jsonl", encoding="utf-8")
        except OSError:
            return ra
        with fh:
            for l in fh:
                try:
                    x = json.loads(l)
                except ValueError:
                    continue
                dt = x.pop("__dt", None)
                x.pop("__phan", None)
                try:
                    dt = datetime.datetime.fromisoformat(dt) if dt else None
                except ValueError:
                    dt = None
                ra.append((x, dt))
        return ra

    def run_ids(self) -> list[str]:
        with self._khoa:
            ids = [ph["run_id"] for _, ph in self.cac_phan() if ph.get("run_id")]
            return list(dict.fromkeys(ids + list(self.d.get("run_muon") or [])))

    def _tinh(self) -> dict:
        """Σ usageTotalUsd (GET mới) của MỌI run id của việc; run còn sống thì HUỶ rồi tính
        lại (review 02/10/2026: luồng lô bỏ lại bởi shutdown(wait=False) vẫn có thể tính
        tiền sau khi việc chốt)."""
        ids = self.run_ids()
        if not ids:
            return {"usd": 0.0, "so_run": 0, "chua_doc": 0, "con_song": []}
        kq = A._chi_phi_cac_run(ids)
        if kq.get("con_song"):
            for rid in kq["con_song"]:
                _huy_run_id(rid)
            _ngu(3)
            kq = A._chi_phi_cac_run(ids)
        elif kq["chua_doc"]:
            _ngu(3)                    # Apify ghi tiền chậm vài giây sau khi run xong
            kq = A._chi_phi_cac_run(ids)
        return kq

    def chot_chi_phi(self, queries, platforms, date_range) -> dict:
        """Tiền THẬT của việc: Σ usageTotalUsd đúng các run id của việc (GET actor-runs),
        ghi sổ chi phí một lần (`chi_phi.da_ghi_so`)."""
        with self._khoa:
            cp = dict(self.d.get("chi_phi") or {})
        if cp.get("da_ghi_so"):
            return cp
        self.dung.set()
        kq = self._tinh()
        ids = self.run_ids()
        with self._khoa:
            tran = [ph for _, ph in self.cac_phan()
                    if ph.get("usd") and ph.get("tran_usd")
                    and float(ph["usd"]) >= 0.95 * float(ph["tran_usd"])]
        thuc = {"usd": kq["usd"], "so_run": kq["so_run"], "cham_tran": len(tran),
                "dang_chay": len(kq.get("con_song") or [])}
        uoc = float((self.d.get("uoc_tinh") or {}).get("usd") or 0)
        self._ghi_so(queries, platforms, date_range, thuc if ids else {**thuc, "so_run": 0},
                     uoc)
        cp = {**kq, "cham_tran": len(tran), "da_ghi_so": True,
              "can_tinh_lai": bool(kq.get("con_song") or kq.get("chua_doc")),
              "so_bao": {"queries": list(queries), "platforms": list(platforms),
                         "date_range": date_range}}
        with self._khoa:
            self.d["chi_phi"] = cp
            self.luu()
        return cp

    def _ghi_so(self, queries, platforms, date_range, thuc, est) -> None:
        try:
            import chi_phi_tool
            chi_phi_tool.ghi(queries=queries, platforms=platforms, date_range=date_range,
                             thuc=thuc, est=est,
                             chat=(self.d.get("kenh") or {}).get("chat_id") or None,
                             ma_viec=self.ma, nguoi=self.d.get("nguoi_yeu_cau") or None)
        except Exception as e:  # noqa: BLE001 — sổ chi phí hỏng không làm hỏng việc
            print(f"[viec_nen] ghi sổ chi phí lỗi (bỏ qua): {type(e).__name__}: {_che(e)}")

    def tinh_lai_muon(self, cho_giay: float = 10.0) -> float:
        """Một lần TÍNH LẠI sau khi đã chốt (run báo xong muộn, lô muộn có run id mới): chênh
        lệch > 0 thì ghi MỘT dòng điều chỉnh vào sổ chi phí (sổ cộng dồn nên không ghi đè).
        -> USD chênh đã ghi."""
        with self._khoa:
            cp = dict(self.d.get("chi_phi") or {})
            muon = list(self.d.get("run_muon") or [])
        if not cp.get("da_ghi_so") or cp.get("da_tinh_lai") or not (
                cp.get("can_tinh_lai") or muon):
            return 0.0
        _ngu(cho_giay)
        kq = self._tinh()
        lech = round(kq["usd"] - float(cp.get("usd") or 0), 4)
        if lech > 0.0005:
            sb = cp.get("so_bao") or {}
            self._ghi_so([f"điều chỉnh việc {self.ma}"] + list(sb.get("queries") or []),
                         sb.get("platforms") or [], sb.get("date_range") or "",
                         {"usd": lech, "so_run": kq["so_run"], "cham_tran": 0,
                          "dang_chay": 0}, 0.0)
        with self._khoa:
            self.d["chi_phi"].update(usd_sau=kq["usd"], da_tinh_lai=True,
                                     lech_sau=lech if lech > 0.0005 else 0.0)
            self.luu()
        return lech if lech > 0.0005 else 0.0


def _huy_run_id(rid: str) -> bool:
    tok = os.environ.get("APIFY_TOKEN", "").strip()
    return bool(tok) and A._huy_run(rid, {"Authorization": f"Bearer {tok}"})


# ───────────────────────────── điều phối ─────────────────────────────
_HANG: queue.Queue = queue.Queue()
_TRONG_HANG: set[str] = set()
_THO: list[threading.Thread] = []


def _dua_vao_hang(ma: str) -> None:
    with _KHOA:
        if ma in _TRONG_HANG:
            return
        _TRONG_HANG.add(ma)
    _HANG.put(ma)
    _dam_bao_tho()


def _dam_bao_tho() -> None:
    if os.environ.get("SOCIAL_NEN_TU_CHAY", "1").strip() == "0":
        return
    with _KHOA:
        _THO[:] = [t for t in _THO if t.is_alive()]
        for i in range(len(_THO), _so("SOCIAL_NEN_DONG_THOI", 1, 1, 4)):
            t = threading.Thread(target=_vong_tho, name=f"viec-nen-{i}", daemon=True)
            t.start()
            _THO.append(t)


def _vong_tho() -> None:
    while True:
        ma = _HANG.get()
        try:
            chay_ngay(ma)
        except Exception as e:  # noqa: BLE001 — một việc hỏng không giết luồng điều phối
            print(f"[viec_nen] {ma} lỗi ngoài dự kiến: {type(e).__name__}: {_che(e)}",
                  flush=True)
        finally:
            with _KHOA:
                _TRONG_HANG.discard(ma)


def _runner(loai: str):
    if loai == "social_listen":
        import quet_lon
        return quet_lon.chay_viec
    if loai == "social_deep_dive":
        import deep_dive_tool
        return deep_dive_tool.chay_viec_nen
    raise ValueError(f"loại việc lạ: {loai}")


def chay_ngay(ma: str) -> dict | None:
    """Chạy (hoặc chạy TIẾP sau khởi động lại) một việc trong luồng hiện tại.

    Đọc sổ -> kiểm huỷ -> đóng số thế hệ -> ghi -> vào `_DANG_CHAY` làm NGUYÊN TỬ dưới
    `_KHOA` (review 02/10/2026: huỷ chen giữa lúc đọc và lúc đăng ký bị lần lưu sau đè
    mất). `huy()` cũng đi dưới `_KHOA`, nên nó hoặc thấy việc trong `_DANG_CHAY`, hoặc
    ghi cờ huỷ trước khi việc được đọc."""
    if not _lay_quyen():
        print(f"[viec_nen] {ma}: tiến trình khác đang giữ quyền — không chạy ở đây",
              flush=True)
        return doc(ma)
    gui_lai = None
    with _KHOA:
        if ma in _DANG_CHAY:
            return _DANG_CHAY[ma].d
        d = doc(ma)
        if not d or d.get("agent_id") != agent_id():
            return d
        v = Viec(d)
        if d["trang_thai"] in TRANG_THAI_XONG:
            tb = d.get("thong_bao") or {}
            if not tb.get("da_gui") and tb.get("ket_qua"):
                gui_lai = v
        elif v.da_huy() and d["trang_thai"] == "xep_hang":
            d.update(trang_thai="da_huy", xong_ts=_bay_gio(), the=the_cua_toi())
            d["thong_bao"]["ket_qua"] = (f"Đã huỷ việc quét nền {ma} trước khi bắt đầu — "
                                         f"chưa chạy gì, chưa tốn tiền.")
            luu(copy.deepcopy(d))
            gui_lai = v
        else:
            if not d.get("bat_dau_ts"):
                d["bat_dau_ts"] = _bay_gio()
                d["han_chot_ts"] = d["bat_dau_ts"] + 60 * int(d.get("han_phut") or han_phut())
            if d["trang_thai"] == "xep_hang":
                d["trang_thai"] = "dang_cao"
            d["the"] = the_cua_toi()
            luu(copy.deepcopy(d))
            _DANG_CHAY[ma] = v
    if gui_lai is not None:
        try:
            gui(gui_lai)               # xong rồi mà chưa nhắn được: nhắn lại, KHÔNG chạy lại
        except MatQuyen as e:
            print(f"[viec_nen] {e}", flush=True)
        return gui_lai.d
    print(f"[viec_nen] {ma} chạy ({d['loai']}, {d['trang_thai']})", flush=True)
    try:
        trang_thai, van_ban = _runner(d["loai"])(v)
    except MatQuyen as e:
        v.dung.set()
        print(f"[viec_nen] DỪNG — mất quyền chủ: {e}", flush=True)
        with _KHOA:
            _DANG_CHAY.pop(ma, None)
        return v.d
    except Exception as e:  # noqa: BLE001
        loi = _che(f"{type(e).__name__}: {e}")
        print(f"[viec_nen] {ma} LỖI: {loi}", flush=True)
        with v._khoa:
            v.d["ly_do_ket_thuc"] = loi
        van_ban = (f"Việc quét nền {ma} gặp lỗi và dừng: {loi}. Phần đã lấy (nếu có) vẫn "
                   f"nằm trong sổ; báo người vận hành.")
        # Lỗi giữa chừng vẫn có thể đã tiêu tiền: huỷ run còn sống + ghi sổ chi phí theo
        # đúng run id đã có.
        try:
            ts = d.get("tham_so") or {}
            cp = v.chot_chi_phi(ts.get("queries") or [f"việc {ma}"],
                                list(d.get("nen_tang") or {}), "")
            van_ban += (f" Chi phí thật tới lúc lỗi: {cp.get('usd', 0):.2f} USD."
                        .replace(".", ",", 1))
        except MatQuyen:
            with _KHOA:
                _DANG_CHAY.pop(ma, None)
            return v.d
        except Exception:  # noqa: BLE001
            pass
        trang_thai = "loi"
    finally:
        v.dung.set()                   # mọi lượt con còn sót tự huỷ run ở nhịp hỏi kế tiếp
    try:
        _ket_thuc(v, trang_thai, van_ban)
    except MatQuyen as e:
        print(f"[viec_nen] DỪNG — mất quyền chủ: {e}", flush=True)
    finally:
        with _KHOA:
            _DANG_CHAY.pop(ma, None)
    return v.d


def _ket_thuc(v: Viec, trang_thai: str, van_ban: str) -> None:
    with v._khoa:
        v.d["trang_thai"] = trang_thai
        v.d["xong_ts"] = _bay_gio()
        v.d.setdefault("thong_bao", {})["ket_qua"] = van_ban
        v.luu()
    try:
        A._youtube_tra(v.ma)           # trả phần quota YouTube giữ chỗ mà chưa dùng
    except Exception:  # noqa: BLE001
        pass
    gui(v)
    try:
        v.tinh_lai_muon()
    except MatQuyen:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"[viec_nen] tính lại chi phí muộn lỗi: {type(e).__name__}: {_che(e)}")


# ───────────────────────────── gửi kết quả ─────────────────────────────
def gui(v: Viec) -> bool:
    """Nhắn kết quả đúng MỘT lần qua đúng kênh đã ghi lúc tạo việc; 3 lần thử, giãn dần.

    Khử trùng theo kênh — nói thật chỗ còn hở:
    - Lark trực tiếp: gửi kèm `uuid` "<mã>-kq", Lark tự bỏ tin trùng uuid trong 1 giờ, nên
      tắt máy giữa lúc gửi và lúc ghi cờ cũng không ra hai tin.
    - Gateway (`/v1/lark/send` của platform): có gửi kèm "uuid" "<mã>-kq" nhưng platform
      (02/10/2026) KHÔNG chuyển trường đó cho Lark -> tắt máy đúng giữa lúc platform nhận và
      lúc ghi cờ `da_gui` thì có thể ra HAI tin (một lần, chỉ trong cửa sổ đó). Cần platform
      chuyển `uuid` xuống `_lark_send_to`.
    - Web (sự kiện job): `data.id` = "<mã>-kq" để console tự bỏ trùng; console hiện chưa
      bỏ trùng theo id.
    Kết quả luôn nằm trong sổ việc và lịch sử chat — kênh không đẩy được (hồi quy, chat lạ)
    thì người dùng vẫn hỏi lại được. Mọi sửa `thong_bao` đi dưới `v._khoa`; gọi mạng thì
    ngoài khoá."""
    with v._khoa:
        tb = v.d.setdefault("thong_bao", {})
        van = tb.get("ket_qua") or ""
        da_gui = bool(tb.get("da_gui"))
        k = dict(v.d.get("kenh") or {})
    kid = f"{v.ma}-kq"[:50]
    if van and not da_gui:
        for lan in range(3):
            v.kiem_quyen()
            try:
                da_day = day_theo_kenh(k, van, kid)
                with v._khoa:
                    if not da_day:
                        tb["khong_day"] = True      # hồi quy / bộ thử / chat lạ: không đẩy
                    tb["da_gui"] = True
                    tb["gui_luc"] = _iso(_bay_gio())
                    v.luu()
                break
            except MatQuyen:
                raise
            except Exception as e:  # noqa: BLE001
                with v._khoa:
                    tb["lan_thu"] = int(tb.get("lan_thu") or 0) + 1
                    tb["loi"] = _che(f"{type(e).__name__}: {e}")
                    v.luu()
                if lan < 2:
                    _ngu(2 * 3 ** lan)
    with v._khoa:
        ghi_ls = bool(van and not tb.get("da_ghi_lich_su") and k.get("chat_id"))
    if ghi_ls:
        try:
            import memory_store
            memory_store.append_turns(k["chat_id"], [{"role": "assistant", "text": van}])
        except Exception as e:  # noqa: BLE001
            print(f"[viec_nen] ghi lịch sử lỗi: {type(e).__name__}", flush=True)
        try:
            import lsr_platform
            lsr_platform.ghi_luot_ngu_canh(
                k["chat_id"], "", van, v.d.get("nguoi_yeu_cau") or "",
                channel="lark" if str(k.get("loai", "")).startswith("lark") else "web")
        except Exception:  # noqa: BLE001
            pass
        with v._khoa:
            tb["da_ghi_lich_su"] = True
            v.luu()
    with v._khoa:
        return bool(tb.get("da_gui"))


# ───────────────────────────── dọn đĩa ─────────────────────────────
def _co_thu_muc(f) -> int:
    try:
        if f.is_file():
            return f.stat().st_size
        return sum(x.stat().st_size for x in f.rglob("*") if x.is_file())
    except OSError:
        return 0


def don_dep() -> dict:
    """Xoá việc ĐÃ KẾT THÚC cũ hơn SOCIAL_NEN_GIU_NGAY ngày (mặc định 14), rồi chặn tổng dung
    lượng ở SOCIAL_NEN_TOI_DA_MB (mặc định 2048) — xoá việc xong cũ nhất trước. KHÔNG bao
    giờ đụng việc đang dở hay việc chưa nhắn được kết quả. Vì sao (review 02/10/2026): mỗi
    việc 10.000 bài để lại vài chục MB jsonl; không dọn thì ổ đĩa máy chạy bot đầy dần."""
    giu = _so("SOCIAL_NEN_GIU_NGAY", 14, 1, 3650) * 86400
    tran = _so("SOCIAL_NEN_TOI_DA_MB", 2048, 10, 10 ** 6) * 1024 * 1024
    now = _bay_gio()
    goc = thu_muc()
    xoa, tong = [], 0

    def xoa_viec(d):
        try:
            _duong(d["ma"]).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        shutil.rmtree(goc / d["ma"], ignore_errors=True)
        xoa.append(d["ma"])

    cac = tat_ca()
    xong = [d for d in cac if d.get("trang_thai") in TRANG_THAI_XONG
            and ((d.get("thong_bao") or {}).get("da_gui")
                 or not (d.get("thong_bao") or {}).get("ket_qua"))
            and d["ma"] not in _DANG_CHAY]
    con = []
    for d in xong:
        if now - float(d.get("xong_ts") or d.get("tao_ts") or now) > giu:
            xoa_viec(d)
        else:
            con.append(d)
    try:
        tong = sum(_co_thu_muc(f) for f in goc.iterdir())
    except OSError:
        tong = 0
    for d in sorted(con, key=lambda d: d.get("xong_ts") or d.get("tao_ts") or 0):
        if tong <= tran:
            break
        tong -= _co_thu_muc(goc / d["ma"]) + _co_thu_muc(_duong(d["ma"]))
        xoa_viec(d)
    # Bộ đếm YouTube các ngày cũ, file số thế hệ cũ.
    try:
        for f in goc.glob("youtube-*-PT.json"):
            if now - f.stat().st_mtime > 3 * 86400:
                f.unlink(missing_ok=True)
        the = the_cua_toi()
        for f in goc.glob(f".the-{_ten_an_toan(agent_id())}-*"):
            try:
                if int(f.name.rsplit("-", 1)[1]) < the - 5:
                    f.unlink(missing_ok=True)
            except ValueError:
                pass
    except OSError:
        pass
    _NHIP["don_luc"] = now
    return {"xoa": xoa, "con_byte": tong}


# ───────────────────────────── khởi động ─────────────────────────────
def khoi_dong(chay_luong: bool = True) -> str:
    """Gọi MỘT lần lúc bot khởi động (run.py, scripts/run_platform_worker.py).

    Nhận khoá chủ `.chu-<agent>.lock` (pid, agent_id, nhịp tim 30s, SỐ THẾ HỆ; >120s không
    nhịp hoặc pid đã chết = mất): hai tiến trình bot cùng chạy mà cùng đọc tiếp một run là
    đọc trùng, gửi tin hai lần. Chỉ nhận lại việc có ĐÚNG agent_id của mình. Dọn đĩa
    (`don_dep`) lúc khởi động và mỗi ngày một lần."""
    try:
        if not _lay_quyen():
            k = _doc_khoa_chu()
            return (f"Việc nền: ⛔ tiến trình khác (pid {k.get('pid')}) đang giữ — không "
                    f"nhận lại việc ở tiến trình này")
    except OSError as e:
        return f"Việc nền: ⚠ không ghi được khoá chủ ({type(e).__name__})"
    try:
        don = don_dep()
    except Exception as e:  # noqa: BLE001 — dọn hỏng không chặn khởi động
        don = {"xoa": [], "loi": type(e).__name__}
    if chay_luong and not _NHIP.get("t"):
        def nhip():
            while True:
                _ngu(30)
                try:
                    if not con_quyen():
                        print("[viec_nen] mất khoá chủ — tiến trình khác đã nhận; ngừng nhịp "
                              "tim", flush=True)
                        for v in list(_DANG_CHAY.values()):
                            v.dung.set()
                        _NHIP.pop("t", None)
                        return
                    _ghi_khoa_chu(the_cua_toi())
                    if _bay_gio() - float(_NHIP.get("don_luc") or 0) > 86400:
                        don_dep()
                except Exception:  # noqa: BLE001
                    pass
        _NHIP["t"] = threading.Thread(target=nhip, name="viec-nen-nhip", daemon=True)
        _NHIP["t"].start()
    nhan = [d for d in tat_ca() if d.get("agent_id") == agent_id()]
    dang = [d for d in nhan if d.get("trang_thai") in TRANG_THAI_DANG]
    # Việc đang chạy dở trước, rồi tới việc đang xếp hàng — giữ thứ tự tạo.
    dang.sort(key=lambda d: (d["trang_thai"] == "xep_hang", d.get("tao_ts") or 0))
    chua_bao = [d for d in nhan if d.get("trang_thai") in TRANG_THAI_XONG
                and (d.get("thong_bao") or {}).get("ket_qua")
                and not (d.get("thong_bao") or {}).get("da_gui")]
    for d in dang + chua_bao:
        _dua_vao_hang(d["ma"])
    don_cau = f" · dọn {len(don.get('xoa') or [])} việc cũ" if don.get("xoa") else ""
    if not bat():
        return (f"Việc nền: ⛔ tắt (SOCIAL_QUET_NEN=0) · {len(dang)} việc dở vẫn chạy tiếp"
                + don_cau)
    return (f"Việc nền: ✅ hạn {han_phut()}′/việc · thế hệ {the_cua_toi()}"
            + (f" · nhận lại {len(dang)} việc dở" if dang else "")
            + (f" · gửi lại {len(chua_bao)} kết quả" if chua_bao else "") + don_cau)


# ───────────────────────────── tra cứu / huỷ ─────────────────────────────
def _cua_toi(d: dict, chat: str, nguoi: str, rieng: bool = False) -> bool:
    """Việc này người đang hỏi được xem/huỷ không.

    Cùng cuộc chat thì được. "Do chính người này yêu cầu" CHỈ tính khi người đó đang ở chat
    RIÊNG (p2p / phiên web của chính họ) — review 02/10/2026: trong nhóm, ai cũng gọi được
    tool dưới tên người gửi của họ, khớp theo người yêu cầu là lộ việc (link sheet, chi phí)
    của chat riêng sang nhóm."""
    k = d.get("kenh") or {}
    if chat and k.get("chat_id") == chat:
        return True
    return bool(rieng and nguoi and d.get("nguoi_yeu_cau") == nguoi)


def _tien_do(d: dict) -> dict:
    cac = [ph for nt in (d.get("nen_tang") or {}).values() for ph in nt.get("phan") or []]
    xong = [ph for ph in cac if ph.get("trang_thai") in PHAN_XONG]
    now = _bay_gio()
    bd = d.get("bat_dau_ts")
    ra = {"phan_xong": len(xong), "tong_phan": len(cac),
          "da_lay": sum(int(ph.get("so_item") or 0) for ph in cac),
          "phut_da_chay": round((min(now, d.get("xong_ts") or now) - bd) / 60, 1) if bd else 0}
    if d.get("trang_thai") in TRANG_THAI_DANG and d.get("han_chot_ts"):
        ra["phut_toi_han"] = round(max(0.0, d["han_chot_ts"] - now) / 60, 1)
    return ra


def _mo_ta_viec(d: dict) -> dict:
    ts = d.get("tham_so") or {}
    return {"ma_viec": d["ma"], "loai": d.get("loai"), "trang_thai": d.get("trang_thai"),
            "trang_thai_vi": _NHAN.get(d.get("trang_thai"), d.get("trang_thai")),
            "tao_luc": d.get("tao_luc"), "tham_so": {k: ts.get(k) for k in (
                "queries", "platforms", "date_from", "date_to", "limit", "country",
                "so_bai", "max_comments") if ts.get(k) is not None},
            "tien_do": _tien_do(d), "uoc_tinh": d.get("uoc_tinh"),
            "ngan_sach_usd": d.get("ngan_sach_usd"),
            "sheet_url": (d.get("sheet") or {}).get("url"),
            "chi_phi_thuc_usd": (d.get("chi_phi") or {}).get("usd"),
            "ket_qua": (d.get("thong_bao") or {}).get("ket_qua") or None,
            "ly_do_ket_thuc": d.get("ly_do_ket_thuc") or None}


def _ai_dang_hoi() -> tuple[str, str, bool]:
    k, nguoi = kenh_hien_tai()
    chat = k.get("chat_id") or ""
    rieng = k.get("loai_chat") == "p2p" or chat.startswith(("web:", "job:"))
    return chat, nguoi, rieng


def tra(ma: str = "", tat_ca_viec: bool = False, chat: str | None = None,
        nguoi: str | None = None, rieng: bool = False) -> dict:
    if chat is None:
        chat, nguoi, rieng = _ai_dang_hoi()
    cua = [d for d in tat_ca() if _cua_toi(d, chat, nguoi or "", rieng)]
    if ma:
        cua = [d for d in cua if d["ma"] == ma]
        if not cua:
            return {"tim_thay": False, "note": (f"Không thấy việc {ma} trong cuộc chat này "
                                                f"hoặc do bạn yêu cầu.")}
    cua = cua[-(10 if tat_ca_viec else 3):][::-1]
    return {"tim_thay": bool(cua), "so_viec": len(cua), "viec": [_mo_ta_viec(d) for d in cua],
            "note": ("Đọc đúng trạng thái/tiến độ từ đây. Việc đã xong thì chép `ket_qua` "
                     "(có link sheet, số bài, chi phí thật). Việc đang chạy thì nói tiến độ "
                     "và số phút tới hạn; CHƯA xong thì đừng bịa số liệu." if cua else
                     "Cuộc chat này chưa có việc quét nền nào.")}


def huy(ma: str = "", chat: str | None = None, nguoi: str | None = None,
        rieng: bool = False) -> dict:
    """Huỷ một việc. Có `ma`: cùng chat, hoặc người yêu cầu đang ở chat riêng. KHÔNG có
    `ma`: chỉ việc đang dở của CHÍNH cuộc chat này (không bao giờ đoán sang chat khác)."""
    if chat is None:
        chat, nguoi, rieng = _ai_dang_hoi()
    with _KHOA:
        if ma:
            d = next((x for x in tat_ca() if x["ma"] == ma
                      and _cua_toi(x, chat, nguoi or "", rieng)), None)
            if not d:
                return {"ok": False, "note": (f"Không huỷ được: việc {ma} không thuộc cuộc "
                                              f"chat này và không do bạn yêu cầu.")}
        else:
            d = next((x for x in reversed(tat_ca()) if chat
                      and (x.get("kenh") or {}).get("chat_id") == chat
                      and x.get("trang_thai") in TRANG_THAI_DANG), None)
            if not d:
                return {"ok": False, "note": ("Cuộc chat này không có việc quét nền nào đang "
                                              "chạy để huỷ (muốn huỷ việc ở chat khác thì "
                                              "đưa mã việc).")}
        if d.get("trang_thai") in TRANG_THAI_XONG:
            return {"ok": False, "ma_viec": d["ma"], "trang_thai": d["trang_thai"],
                    "note": f"Việc {d['ma']} đã {_NHAN[d['trang_thai']]}, không còn gì để huỷ."}
        yc = {"yeu_cau": True, "boi": nguoi or "", "luc": _iso(_bay_gio())}
        song = _DANG_CHAY.get(d["ma"])
        if song is None:
            # Chưa chạy trong tiến trình này: ghi thẳng vào sổ, dưới `_KHOA` — `chay_ngay`
            # đọc sổ cũng dưới `_KHOA` nên chắc chắn thấy cờ huỷ.
            d = doc(d["ma"]) or d
            d["huy"] = yc
            su_kien_huy(d["ma"]).set()
            if d["trang_thai"] == "xep_hang":
                d.update(trang_thai="da_huy", xong_ts=_bay_gio(),
                         ly_do_ket_thuc="huỷ khi còn xếp hàng")
                d["thong_bao"].update(ket_qua=(f"Đã huỷ việc quét nền {d['ma']} khi còn "
                                               f"xếp hàng — chưa chạy gì, chưa tốn tiền."),
                                      da_gui=True, khong_day=True)
                luu(d)
                return {"ok": True, "ma_viec": d["ma"], "trang_thai": "da_huy",
                        "note": "Đã huỷ ngay (việc chưa bắt đầu, chưa tốn tiền)."}
            luu(d)
            return {"ok": True, "ma_viec": d["ma"], "trang_thai": "dang_huy",
                    "note": _CAU_DANG_HUY}
    # Việc đang chạy giữ bản dict của nó trong RAM; ghi cờ vào ĐÓ, không thì lần lưu sau
    # của luồng chạy đè mất cờ huỷ trên đĩa. Làm NGOÀI `_KHOA` (thứ tự khoá: việc rồi sổ).
    song.huy.set()
    with song._khoa:
        song.d["huy"] = yc
        try:
            song.luu()
        except MatQuyen:
            pass
    return {"ok": True, "ma_viec": d["ma"], "trang_thai": "dang_huy", "note": _CAU_DANG_HUY}


_CAU_DANG_HUY = ("Đã gửi lệnh huỷ: các lượt cào đang chạy sẽ dừng trong vòng ~15 giây, phần "
                 "đã lấy được vẫn ghi vào sheet, xong Mark nhắn kết quả (đánh dấu ĐÃ HUỶ) "
                 "vào cuộc chat này.")


def van_ban_lenh(doi_so: str = "", chat: str | None = None, nguoi: str | None = None,
                 rieng: bool = False) -> str:
    """Trả lời `/viec` THẲNG từ sổ, không gọi model."""
    ma = (doi_so or "").strip().split()[0] if (doi_so or "").strip() else ""
    kq = tra(ma, tat_ca_viec=not ma, chat=chat, nguoi=nguoi, rieng=rieng)
    if not kq.get("tim_thay"):
        return kq.get("note") or "Chưa có việc quét nền nào."
    d = ["Việc quét nền của cuộc chat này:"]
    for x in kq["viec"]:
        td = x["tien_do"]
        dong = (f"• {x['ma_viec']} — {x['trang_thai_vi']} · {td['phan_xong']}/"
                f"{td['tong_phan']} phần · đã lấy {td['da_lay']}")
        if "phut_toi_han" in td:
            dong += f" · còn ≤{td['phut_toi_han']:g} phút"
        if x.get("sheet_url"):
            dong += f"\n  {x['sheet_url']}"
        if x.get("chi_phi_thuc_usd") is not None:
            dong += f"\n  Chi phí thật: {x['chi_phi_thuc_usd']:.2f} USD".replace(".", ",")
        d.append(dong)
    d.append("Huỷ: nhắn 'huỷ quét <mã>'. Xem một việc: /viec <mã>.")
    return "\n".join(d)


# ───────────────────────────── tool ─────────────────────────────
TRA_SCHEMA = {
    "name": "tra_viec_nen",
    "description": (
        "Xem tiến độ / kết quả các việc QUÉT NỀN (quét lớn chạy ngoài lượt trả lời) của "
        "cuộc chat này. Dùng khi người dùng hỏi 'xong chưa', 'kết quả quét', 'tới đâu rồi', "
        "'link sheet đâu' sau một lượt quét đã chuyển sang chạy nền. Chỉ đọc. Việc xong thì "
        "chép `ket_qua`; việc đang chạy thì nói tiến độ + phút tới hạn, KHÔNG bịa số liệu."),
    "parameters": {"type": "object", "properties": {
        "ma_viec": {"type": "string", "description": "Mã việc (bỏ trống = các việc gần nhất)."},
        "tat_ca": {"type": "boolean", "description": "true = tới 10 việc gần nhất."},
    }},
}
HUY_SCHEMA = {
    "name": "huy_viec_nen",
    "description": (
        "HUỶ một việc quét nền đang chạy hoặc đang xếp hàng của cuộc chat này (người dùng "
        "nói 'huỷ quét', 'dừng lại', 'thôi không quét nữa'). Phần đã lấy được vẫn ghi vào "
        "sheet; Mark tự nhắn kết quả đánh dấu ĐÃ HUỶ. Bỏ trống `ma_viec` = việc đang chạy "
        "của CHÍNH chat này. Việc ở chat khác chỉ huỷ được bằng mã việc, từ chat riêng của "
        "người đã yêu cầu."),
    "parameters": {"type": "object", "properties": {
        "ma_viec": {"type": "string", "description": "Mã việc cần huỷ."},
    }},
}


def _handle_tra(args: dict, **_kw) -> str:
    a = args or {}
    return tool_result(**tra(str(a.get("ma_viec") or "").strip(), A._co(a.get("tat_ca"))))


def _handle_huy(args: dict, **_kw) -> str:
    kq = huy(str((args or {}).get("ma_viec") or "").strip())
    return tool_result(**kq) if kq.get("ok") else tool_error(kq.get("note") or "Không huỷ được.")


def register() -> None:
    for ten, sch, fn, emo in (("tra_viec_nen", TRA_SCHEMA, _handle_tra, "⏳"),
                              ("huy_viec_nen", HUY_SCHEMA, _handle_huy, "❌")):
        try:
            registry.register(name=ten, toolset="social", schema=sch, handler=fn,
                              check_fn=lambda: True, requires_env=[], is_async=False,
                              description=sch["description"][:80], emoji=emo,
                              override=True)
        except Exception as e:  # noqa: BLE001
            print(f"[viec_nen] register warning ({ten}): {e}")


register()
