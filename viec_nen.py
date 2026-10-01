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
≤ phần còn lại của tháng − 0,30 USD). Xác nhận chi phí với người dùng ("Chạy nhé?") là
việc của lời dặn prompt, không chặn ở đây.

Công tắc env:
    SOCIAL_QUET_NEN=0        tắt hẳn chạy nền (lượt lớn bị kẹp về cỡ tại chỗ, có báo)
    SOCIAL_NEN_DONG_THOI=1   số việc lớn chạy cùng lúc
    SOCIAL_NEN_HAN_PHUT=45   hạn mỗi việc (kẹp 10–120 phút)
    SOCIAL_NEN_THU_MUC       thư mục sổ (bộ thử)
    SOCIAL_NEN_TU_CHAY=0     không tự dựng luồng điều phối (bộ thử)
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import queue
import re
import threading
import time
import uuid

import apify_tool as A

from tools.registry import registry, tool_error, tool_result  # type: ignore

_VN = A._VN_TZ
_KHOA = threading.RLock()
_HANG_TOI_DA = 3            # việc chờ trong hàng (không tính việc đang chạy)
_TRUNG_GIAY = 6 * 3600      # cùng tham số trong 6 giờ -> trả lại đúng việc cũ
_KHOA_CHU_CU_GIAY = 120     # khoá chủ không có nhịp tim quá chừng này = tiến trình đã chết

TRANG_THAI_DANG = ("xep_hang", "dang_cao", "dang_loc", "dang_ghi")
TRANG_THAI_XONG = ("xong", "xong_mot_phan", "loi", "da_huy")
_NHAN = {"xep_hang": "đang xếp hàng", "dang_cao": "đang cào", "dang_loc": "đang lọc/AI",
         "dang_ghi": "đang ghi sheet", "xong": "xong", "xong_mot_phan": "xong một phần",
         "loi": "lỗi", "da_huy": "đã huỷ"}
PHAN_XONG = ("xong", "mot_phan", "loi", "da_huy")

_bay_gio = time.time        # tách tên để bộ thử giả đồng hồ treo tường
_ngu = time.sleep


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
    sổ (chỉ mất lần ghi cuối)."""
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


# ───────────────────────────── kênh trả kết quả ─────────────────────────────
def kenh_hien_tai() -> tuple[dict, str]:
    """Ghi lại NGAY lúc gọi tool: cuộc chat, người hỏi, job platform. Việc chạy xong 40
    phút sau thì contextvars của lượt trả lời đã mất — không ghi lúc này là không biết
    gửi kết quả về đâu."""
    try:
        import scheduler
        chat = scheduler.get_current_chat() or ""
    except Exception:  # noqa: BLE001
        chat = ""
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
    k = {"loai": "khac", "chat_id": chat, "app_id": "", "oc": "", "job_id": job_id}
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
    return k, nguoi


def _se_bao_qua(k: dict) -> str:
    return {"lark_gateway": "tin nhắn Lark vào đúng cuộc chat này",
            "lark_truc_tiep": "tin nhắn Lark vào đúng cuộc chat này",
            "web": "sự kiện của job trên console (tạm thời; mở lại cuộc chat để xem)",
            }.get(k.get("loai"), "không tự nhắn được — hỏi lại 'xong chưa' hoặc gõ /viec")


# ───────────────────────────── tạo việc ─────────────────────────────
def khoa_trung(loai: str, chat: str, tham_so: dict) -> str:
    chuan = json.dumps(tham_so, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(f"{agent_id()}|{chat}|{loai}|{chuan}".encode("utf-8")).hexdigest()


def tao_viec(loai: str, tham_so: dict, nen_tang: dict, uoc_tinh: dict,
             ngan_sach_usd: float, ghi_chu: list[str] | None = None) -> dict:
    """Ghi việc mới vào sổ rồi đưa vào hàng. -> dict trả NGAY cho model (≤ ~2 giây).

    Cùng chat + cùng tham số trong 6 giờ thì trả lại việc cũ (model gọi lặp hoặc người
    dùng nhắn lại "quét đi") — không quét, không trả tiền hai lần."""
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
        chay = [d for d in dang if d.get("trang_thai") != "xep_hang"]
        trang_thai = "xep_hang"
        ma = (f"{'q' if loai == 'social_listen' else 'b'}"
              f"{datetime.datetime.fromtimestamp(now, _VN):%m%d%H%M}-{uuid.uuid4().hex[:5]}")
        d = {
            "ma": ma, "phien_ban": 1, "agent_id": agent_id(), "loai": loai,
            "trang_thai": trang_thai, "tao_ts": now, "tao_luc": _iso(now),
            "bat_dau_ts": None, "han_chot_ts": None, "han_phut": han_phut(),
            "xong_ts": None, "kenh": k, "nguoi_yeu_cau": nguoi,
            "tham_so": tham_so, "khoa_trung": kt, "uoc_tinh": uoc_tinh,
            "ngan_sach_usd": round(float(ngan_sach_usd), 2), "nen_tang": nen_tang,
            "ghi_chu": list(ghi_chu or []), "phan_xu": {}, "sheet": {}, "chi_phi": {},
            "thong_bao": {"ket_qua": "", "lan_thu": 0, "loi": "", "da_gui": False},
            "huy": {"yeu_cau": False}, "ly_do_ket_thuc": "", "ket_qua": {},
            "dang_cho_truoc": len(chay) + len(cho),
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


class Viec:
    """Bọc dict của một việc: lưu nguyên tử, hạn chót, huỷ, sổ dòng tràn."""

    def __init__(self, d: dict):
        self.d = d
        self.huy = su_kien_huy(d["ma"])
        if (d.get("huy") or {}).get("yeu_cau"):
            self.huy.set()
        self._khoa = threading.RLock()

    @property
    def ma(self) -> str:
        return self.d["ma"]

    def luu(self) -> None:
        with self._khoa:
            luu(self.d)

    def dat(self, trang_thai: str) -> None:
        with self._khoa:
            self.d["trang_thai"] = trang_thai
            self.luu()

    def da_huy(self) -> bool:
        return self.huy.is_set()

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
        with self._khoa:
            ph.update(kw)
            self.luu()

    def thu_muc(self):
        f = thu_muc() / self.ma
        f.mkdir(parents=True, exist_ok=True)
        return f

    def ghi_dong(self, p: str, rows: list[tuple], phan_id: str) -> None:
        """Nối dòng đã chuẩn hoá vào `rows-<p>.jsonl`. Ghi TRƯỚC khi đánh dấu phần xong —
        tắt máy giữa hai bước thì lần sau ghi lại, trùng lặp đã có khử trùng theo link."""
        with self._khoa, open(self.thu_muc() / f"rows-{p}.jsonl", "a", encoding="utf-8") as fh:
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
        return [ph["run_id"] for _, ph in self.cac_phan() if ph.get("run_id")]

    def chot_chi_phi(self, queries, platforms, date_range) -> dict:
        """Tiền THẬT của việc: Σ usageTotalUsd đúng các run id của việc (GET actor-runs),
        ghi sổ chi phí một lần (`chi_phi.da_ghi_so`)."""
        cp = self.d.get("chi_phi") or {}
        if cp.get("da_ghi_so"):
            return cp
        ids = self.run_ids()
        kq = A._chi_phi_cac_run(ids) if ids else {"usd": 0.0, "so_run": 0, "chua_doc": 0}
        if ids and kq["chua_doc"]:
            _ngu(3)                    # Apify ghi tiền chậm vài giây sau khi run xong
            kq = A._chi_phi_cac_run(ids)
        tran = [ph for _, ph in self.cac_phan()
                if ph.get("usd") and ph.get("tran_usd")
                and float(ph["usd"]) >= 0.95 * float(ph["tran_usd"])]
        thuc = {"usd": kq["usd"], "so_run": kq["so_run"], "cham_tran": len(tran),
                "dang_chay": 0}
        uoc = float((self.d.get("uoc_tinh") or {}).get("usd") or 0)
        try:
            import chi_phi_tool
            chi_phi_tool.ghi(queries=queries, platforms=platforms, date_range=date_range,
                             thuc=thuc if ids else {**thuc, "so_run": 0}, est=uoc,
                             chat=(self.d.get("kenh") or {}).get("chat_id") or None,
                             ma_viec=self.ma, nguoi=self.d.get("nguoi_yeu_cau") or None)
        except Exception as e:  # noqa: BLE001 — sổ chi phí hỏng không làm hỏng việc
            print(f"[viec_nen] ghi sổ chi phí lỗi (bỏ qua): {type(e).__name__}: {_che(e)}")
        cp = {**kq, "cham_tran": len(tran), "da_ghi_so": True}
        self.d["chi_phi"] = cp
        self.luu()
        return cp


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
    """Chạy (hoặc chạy TIẾP sau khởi động lại) một việc trong luồng hiện tại."""
    d = doc(ma)
    if not d or d.get("agent_id") != agent_id():
        return d
    v = Viec(d)
    if d["trang_thai"] in TRANG_THAI_XONG:
        if not (d.get("thong_bao") or {}).get("da_gui") and (d.get("thong_bao") or {}).get(
                "ket_qua"):
            gui(v)                     # xong rồi mà chưa nhắn được: nhắn lại, KHÔNG chạy lại
        return d
    if v.da_huy() and d["trang_thai"] == "xep_hang":
        _ket_thuc(v, "da_huy", "Đã huỷ việc quét nền "
                  f"{ma} trước khi bắt đầu — chưa chạy gì, chưa tốn tiền.")
        return v.d
    if not d.get("bat_dau_ts"):
        d["bat_dau_ts"] = _bay_gio()
        d["han_chot_ts"] = d["bat_dau_ts"] + 60 * int(d.get("han_phut") or han_phut())
    if d["trang_thai"] == "xep_hang":
        d["trang_thai"] = "dang_cao"
    v.luu()
    with _KHOA:
        _DANG_CHAY[ma] = v
    print(f"[viec_nen] {ma} chạy ({d['loai']}, {d['trang_thai']})", flush=True)
    try:
        trang_thai, van_ban = _runner(d["loai"])(v)
    except Exception as e:  # noqa: BLE001
        loi = _che(f"{type(e).__name__}: {e}")
        print(f"[viec_nen] {ma} LỖI: {loi}", flush=True)
        v.d["ly_do_ket_thuc"] = loi
        trang_thai, van_ban = "loi", (f"Việc quét nền {ma} gặp lỗi và dừng: {loi}. Phần đã "
                                       f"lấy (nếu có) vẫn nằm trong sổ; báo người vận hành.")
    finally:
        with _KHOA:
            _DANG_CHAY.pop(ma, None)
    _ket_thuc(v, trang_thai, van_ban)
    return v.d


def _ket_thuc(v: Viec, trang_thai: str, van_ban: str) -> None:
    with v._khoa:
        v.d["trang_thai"] = trang_thai
        v.d["xong_ts"] = _bay_gio()
        v.d.setdefault("thong_bao", {})["ket_qua"] = van_ban
        v.luu()
    gui(v)


# ───────────────────────────── gửi kết quả ─────────────────────────────
def gui(v: Viec) -> bool:
    """Nhắn kết quả đúng MỘT lần qua đúng kênh đã ghi lúc tạo việc; 3 lần thử, giãn dần.

    Lark trực tiếp gửi kèm `uuid` = "<mã>-kq": Lark tự khử trùng trong 1 giờ, nên tắt máy
    giữa lúc gửi và lúc ghi cờ cũng không ra hai tin. Kết quả luôn được lưu vào sổ việc và
    lịch sử chat — kênh không đẩy được (hồi quy, chat lạ) thì người dùng vẫn hỏi lại được."""
    tb = v.d.setdefault("thong_bao", {})
    van = tb.get("ket_qua") or ""
    k = v.d.get("kenh") or {}
    if van and not tb.get("da_gui"):
        loai = k.get("loai")
        for lan in range(3):
            try:
                if loai == "lark_gateway":
                    import lsr_platform
                    lsr_platform.gui_lark(k["oc"], van, k.get("app_id") or "")
                elif loai == "lark_truc_tiep":
                    import lark_client
                    lark_client.send_text("chat_id", k["oc"], van, uuid=f"{v.ma}-kq"[:50])
                elif loai == "web":
                    import lsr_platform
                    # Tạm thời (02/10/2026): console chưa có kênh đẩy tin chủ động cho agent;
                    # sự kiện "message" gắn vào job gốc là chỗ duy nhất console đọc được.
                    lsr_platform.bao_su_kien_job(k["job_id"], van)
                else:
                    tb["khong_day"] = True      # hồi quy / bộ thử / chat lạ: không đẩy
                tb["da_gui"] = True
                tb["gui_luc"] = _iso(_bay_gio())
                break
            except Exception as e:  # noqa: BLE001
                tb["lan_thu"] = int(tb.get("lan_thu") or 0) + 1
                tb["loi"] = _che(f"{type(e).__name__}: {e}")
                v.luu()
                if lan < 2:
                    _ngu(2 * 3 ** lan)
        v.luu()
    if van and not tb.get("da_ghi_lich_su") and k.get("chat_id"):
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
        tb["da_ghi_lich_su"] = True
        v.luu()
    return bool(tb.get("da_gui"))


# ───────────────────────────── khởi động / khoá chủ ─────────────────────────────
_NHIP: dict = {}


def _khoa_chu():
    return thu_muc() / ".chu.lock"


def _doc_khoa_chu() -> dict:
    try:
        return json.loads(_khoa_chu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ghi_khoa_chu() -> None:
    f = _khoa_chu()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".chu.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps({"pid": os.getpid(), "agent_id": agent_id(),
                               "heartbeat": _bay_gio()}), encoding="utf-8")
    os.replace(tmp, f)


def khoi_dong(chay_luong: bool = True) -> str:
    """Gọi MỘT lần lúc bot khởi động (run.py, scripts/run_platform_worker.py).

    Giữ khoá chủ `.chu.lock` (pid, agent_id, nhịp tim 30s; >120s không nhịp = chết): hai
    tiến trình bot cùng chạy (Stop+Start lệch, cửa sổ cmd treo `pause`) mà cùng đọc tiếp
    một run là đọc trùng, gửi tin hai lần. Chỉ nhận lại việc có ĐÚNG agent_id của mình."""
    try:
        k = _doc_khoa_chu()
        if (k and k.get("pid") != os.getpid()
                and _bay_gio() - float(k.get("heartbeat") or 0) < _KHOA_CHU_CU_GIAY):
            return (f"Việc nền: ⛔ tiến trình khác (pid {k.get('pid')}) đang giữ — không "
                    f"nhận lại việc ở tiến trình này")
        _ghi_khoa_chu()
    except OSError as e:
        return f"Việc nền: ⚠ không ghi được khoá chủ ({type(e).__name__})"
    if chay_luong and not _NHIP.get("t"):
        def nhip():
            while True:
                _ngu(30)
                try:
                    _ghi_khoa_chu()
                except OSError:
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
    if not bat():
        return f"Việc nền: ⛔ tắt (SOCIAL_QUET_NEN=0) · {len(dang)} việc dở vẫn chạy tiếp"
    return (f"Việc nền: ✅ hạn {han_phut()}′/việc"
            + (f" · nhận lại {len(dang)} việc dở" if dang else "")
            + (f" · gửi lại {len(chua_bao)} kết quả" if chua_bao else ""))


# ───────────────────────────── tra cứu / huỷ ─────────────────────────────
def _cua_toi(d: dict, chat: str, nguoi: str) -> bool:
    k = d.get("kenh") or {}
    return bool((chat and k.get("chat_id") == chat)
                or (nguoi and d.get("nguoi_yeu_cau") == nguoi))


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


def _ai_dang_hoi() -> tuple[str, str]:
    k, nguoi = kenh_hien_tai()
    return k.get("chat_id") or "", nguoi


def tra(ma: str = "", tat_ca_viec: bool = False, chat: str | None = None,
        nguoi: str | None = None) -> dict:
    if chat is None:
        chat, nguoi = _ai_dang_hoi()
    cua = [d for d in tat_ca() if _cua_toi(d, chat, nguoi or "")]
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


def huy(ma: str = "", chat: str | None = None, nguoi: str | None = None) -> dict:
    if chat is None:
        chat, nguoi = _ai_dang_hoi()
    with _KHOA:
        cua = [d for d in tat_ca() if _cua_toi(d, chat, nguoi or "")]
        if ma:
            d = next((x for x in cua if x["ma"] == ma), None)
            if not d:
                return {"ok": False, "note": (f"Không huỷ được: việc {ma} không thuộc cuộc "
                                              f"chat này và không do bạn yêu cầu.")}
        else:
            d = next((x for x in reversed(cua) if x.get("trang_thai") in TRANG_THAI_DANG), None)
            if not d:
                return {"ok": False, "note": "Không có việc quét nền nào đang chạy để huỷ."}
        if d.get("trang_thai") in TRANG_THAI_XONG:
            return {"ok": False, "ma_viec": d["ma"], "trang_thai": d["trang_thai"],
                    "note": f"Việc {d['ma']} đã {_NHAN[d['trang_thai']]}, không còn gì để huỷ."}
        yc = {"yeu_cau": True, "boi": nguoi or "", "luc": _iso(_bay_gio())}
        song = _DANG_CHAY.get(d["ma"])
    if song is not None:
        # Việc đang chạy giữ bản dict của nó trong RAM; ghi cờ vào ĐÓ, không thì lần lưu sau
        # của luồng chạy đè mất cờ huỷ trên đĩa. Làm NGOÀI `_KHOA`: luồng chạy giữ khoá
        # của việc rồi mới xin `_KHOA` (Viec.luu) — giữ ngược thứ tự là kẹt cả hai.
        song.huy.set()
        with song._khoa:
            song.d["huy"] = yc
            song.luu()
        return {"ok": True, "ma_viec": d["ma"], "trang_thai": "dang_huy",
                "note": _CAU_DANG_HUY}
    with _KHOA:
        d = doc(d["ma"]) or d
        d["huy"] = yc
        su_kien_huy(d["ma"]).set()
        if d["trang_thai"] == "xep_hang":
            d.update(trang_thai="da_huy", xong_ts=_bay_gio(),
                     ly_do_ket_thuc="huỷ khi còn xếp hàng")
            d["thong_bao"].update(ket_qua=(f"Đã huỷ việc quét nền {d['ma']} khi còn xếp "
                                           f"hàng — chưa chạy gì, chưa tốn tiền."),
                                  da_gui=True, khong_day=True)
            luu(d)
            return {"ok": True, "ma_viec": d["ma"], "trang_thai": "da_huy",
                    "note": "Đã huỷ ngay (việc chưa bắt đầu, chưa tốn tiền)."}
        luu(d)
    return {"ok": True, "ma_viec": d["ma"], "trang_thai": "dang_huy", "note": _CAU_DANG_HUY}


_CAU_DANG_HUY = ("Đã gửi lệnh huỷ: các lượt cào đang chạy sẽ dừng trong vòng ~15 giây, phần "
                 "đã lấy được vẫn ghi vào sheet, xong Mark nhắn kết quả (đánh dấu ĐÃ HUỶ) "
                 "vào cuộc chat này.")


def van_ban_lenh(doi_so: str = "", chat: str | None = None, nguoi: str | None = None) -> str:
    """Trả lời `/viec` THẲNG từ sổ, không gọi model."""
    ma = (doi_so or "").strip().split()[0] if (doi_so or "").strip() else ""
    kq = tra(ma, tat_ca_viec=not ma, chat=chat, nguoi=nguoi)
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
        "gần nhất của chat này. Chỉ người cùng chat hoặc người yêu cầu mới huỷ được."),
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
