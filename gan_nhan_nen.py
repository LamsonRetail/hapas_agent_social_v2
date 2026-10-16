"""Gán nhãn AI CHẠY NỀN cho kho lắng nghe `lang_nghe` (17/10/2026).

Vì sao có: lượt `/theodoi` từng gán nhãn ~2.400 bình luận NGAY trong việc quét — lượt 7 chạy 54
phút, quá hạn 45 phút của việc nền, nên phần cuối (bình luận, chốt lượt) bị hết giờ. Chủ dự án
16/10: "các lượt quét có thể để chạy nền". Nay việc quét chỉ cào + lọc rác + gán phần LUẬT (rỗng,
chỉ @tag, chỉ emoji) rồi ghi kho; dòng cần model nằm trong kho với sắc thái NULL ("chưa phân
loại" trên dashboard) và nhịp này gán dần.

Kho LÀ hàng đợi (`lang_nghe_db.bl_cho_gan_nhan` / `bai_cho_gan_nhan`): không thêm cột, không thêm
bảng. Vì thế:
  • Khởi động lại giữa chừng: nhịp sau đọc lại đúng các dòng còn trống — lô đang gọi model dở chỉ
    mất một lượt gọi, không mất dòng nào.
  • Không gán hai lần: chỉ tiến trình giữ quyền chủ việc nền (`viec_nen.con_quyen`) chạy nhịp;
    UPDATE chỉ ghi dòng CÒN trống và CÙNG chữ lúc đọc (`ghi_nhan_bl`), nên lượt quét chen giữa hạ
    dòng thành seeding/spam (xoá nhãn) hay hai bản Mark lỡ cùng chạy cũng không đè nhau.
  • Model hỏng / hết hạn mức: lô fail-open (dòng vẫn "chưa phân loại", không đoán bù), nhịp lùi
    dần 1 → 30 phút rồi thử lại. Báo platform "limit"/"auth_error" vẫn qua `phan_loai` (một lần
    mỗi lô) như trước.
  • Dòng model cứ bỏ sót (lô chạy được mà không trả nhãn cho dòng đó): đếm lần thử trong sổ nhỏ
    `.gan-nhan-that-bai.json` cạnh sổ việc nền; quá `TOI_DA_THU` lần thì bỏ qua, không chặn hàng.
  • Nhường lease model cho lượt chat: MỘT lô một lúc (`song_song=1`), nghỉ `NGHI_GIUA_LO` giây
    giữa hai lô, tối đa `LO_MOI_NHIP` lô mỗi nhịp; không gọi thêm model nào ngoài lô gán nhãn.
  • Ngân sách Apify và lịch quét không liên quan: nhịp này không chạy actor, không tạo việc nền,
    không chiếm chỗ trong hàng đợi việc (`viec_nen` chỉ chạy một việc một lúc).

Bình luận trước (nhiều nhất), rồi bài (phân xử hết giờ / "không rõ", bài Báo & Web — xem
`phan_loai.phan_loai_bai`). Trạng thái: dashboard tự đếm dòng còn chờ trong kho (ⓘ cạnh khối sắc
thái), lượt quét ghi "N bình luận chờ gán nhãn nền" vào ghi chú.

Tắt: `MARK_GAN_NHAN_NEN=0` — lượt `/theodoi` quay lại gán nhãn ngay trong việc như cũ.
"""
from __future__ import annotations

import json
import os
import threading
import time

NHIP = 60                 # giây giữa hai nhịp khi hàng đợi trống / sau một nhịp đầy
NGHI_GIUA_LO = 5          # giây nghỉ giữa hai lô model trong một nhịp
LO_MOI_NHIP = 6           # lô tối đa mỗi nhịp (rồi nhường nhịp sau)
HAN_LO = 180.0            # hạn một lô model (giây) — như scripts/lang_nghe_gan_lai.py
TOI_DA_THU = 3            # lần model bỏ sót một dòng trước khi bỏ qua dòng đó
LUI_GIAY = (60, 120, 300, 900, 1800)   # lùi sau lô hỏng liên tiếp
_TRANG: dict = {"loi_lien": 0, "nghi_toi": 0.0, "cuoi": None}
_LUONG: dict = {}
_KHOA_SO = threading.Lock()
_DA_BAO: set[str] = set()


def bat() -> bool:
    return (os.environ.get("MARK_GAN_NHAN_NEN") or "1").strip() != "0"


def _log(khoa: str, chu: str) -> None:
    """Log mỗi sự việc MỘT lần (nhịp 60 giây mà in lỗi mỗi nhịp thì log ngập)."""
    if khoa in _DA_BAO:
        return
    if len(_DA_BAO) > 200:
        _DA_BAO.clear()
    _DA_BAO.add(khoa)
    print(f"[gan_nhan_nen] {chu}", flush=True)


# ───────────────────────────── sổ dòng bị bỏ sót ─────────────────────────────
def _duong_so():
    import apify_tool as A
    return A._thu_muc_nen() / ".gan-nhan-that-bai.json"


def doc_so() -> dict:
    try:
        d = json.loads(_duong_so().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _ghi_so(d: dict) -> None:
    f = _duong_so()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, f)
    except OSError as e:
        _log(f"so-{type(e).__name__}", f"không ghi được sổ dòng bỏ sót: {type(e).__name__}")


def bo_qua(ma: str, loai: str) -> list[str]:
    """Khoá dòng đã bị model bỏ sót ≥ `TOI_DA_THU` lần (`loai` = "bl" | "bai")."""
    x = ((doc_so().get(ma) or {}).get(loai) or {})
    return sorted(k for k, n in x.items() if isinstance(n, int) and n >= TOI_DA_THU)


def dem_bo_sot(ma: str, loai: str, khoa_sot: list[str], khoa_xong: list[str]) -> None:
    """+1 lần thử cho dòng bị bỏ sót; dòng đã gán xong thì xoá khỏi sổ. Sổ chỉ giữ dòng lỗi."""
    if not khoa_sot and not khoa_xong:
        return
    with _KHOA_SO:
        d = doc_so()
        x = d.setdefault(ma, {}).setdefault(loai, {})
        for k in khoa_xong:
            x.pop(k, None)
        for k in khoa_sot:
            x[k] = int(x.get(k) or 0) + 1
        if len(x) > 5000:                       # chặn trên: giữ phần bị bỏ sót nhiều nhất
            d[ma][loai] = dict(sorted(x.items(), key=lambda kv: -kv[1])[:5000])
        _ghi_so(d)


# ───────────────────────────── một lô ─────────────────────────────
def khoa_bl(r: dict) -> str:
    return f"{r['khoa_bai']}\x1f{r['ma']}"


def gan_lo_bl(ma: str, rows: list[dict]) -> dict:
    """Gán + ghi một lô bình luận (đã đọc từ kho). -> {ghi, sot, loi (lô hỏng/hết giờ)}."""
    import lang_nghe_db as K
    import phan_loai as P
    tt: dict = {}
    nhan = P.phan_loai_binh_luan(
        [{"text": r.get("noi_dung") or "", "likes": int(r.get("thich") or 0)} for r in rows],
        HAN_LO, tt, song_song=1)
    ghi = [(r["khoa_bai"], r["ma"], r.get("noi_dung") or "", s, c)
           for r, (s, c) in zip(rows, nhan) if s != P.CHUA and c != P.CHUA]
    n = K.ghi_nhan_bl(ma, ghi)
    sot = [khoa_bl(rows[i]) for i in tt.get("khong_tra") or []]
    dem_bo_sot(ma, "bl", sot, [f"{g[0]}\x1f{g[1]}" for g in ghi])
    return {"ghi": n, "sot": len(sot), "loi": int(tt.get("lo_loi") or 0)
            + int(tt.get("lo_het_gio") or 0)}


def gan_lo_bai(ma: str, du_an: dict, rows: list[dict]) -> dict:
    import lang_nghe_db as K
    import phan_loai as P
    tt: dict = {}
    brand = ", ".join(dict.fromkeys(str(x) for x in P.thuong_hieu_du_an(du_an) if str(x).strip()))
    nhan = P.phan_loai_bai(rows, brand, HAN_LO, tt, song_song=1)
    ghi = [(r["khoa"], r.get("noi_dung") or "", x[0], x[1])
           for r, x in zip(rows, nhan) if x]
    n = K.ghi_nhan_bai(ma, ghi)
    sot = [rows[i]["khoa"] for i in tt.get("khong_tra") or []]
    dem_bo_sot(ma, "bai", sot, [g[0] for g in ghi])
    return {"ghi": n, "sot": len(sot), "loi": int(tt.get("lo_loi") or 0)
            + int(tt.get("lo_het_gio") or 0), "rui_ro": int(tt.get("rui_ro") or 0)}


# ───────────────────────────── nhịp ─────────────────────────────
def _co_quyen() -> bool:
    import viec_nen
    return viec_nen.con_quyen()


def mot_nhip(bay_gio: float | None = None, ngu=time.sleep) -> dict:
    """Một nhịp: tối đa `LO_MOI_NHIP` lô (bình luận trước, rồi bài) qua các dự án đang bật.
    Không bao giờ ném ra ngoài. -> thống kê nhịp (bộ thử đọc)."""
    import lang_nghe_db as K
    import phan_loai as P
    bay_gio = time.monotonic() if bay_gio is None else bay_gio
    kq = {"lo": 0, "ghi_bl": 0, "ghi_bai": 0, "loi": 0, "bo_qua": ""}
    if not bat():
        kq["bo_qua"] = "tắt"
        return kq
    if bay_gio < _TRANG["nghi_toi"]:
        kq["bo_qua"] = "đang lùi sau lỗi"
        return kq
    try:
        if not _co_quyen():
            kq["bo_qua"] = "không giữ quyền chủ việc nền"
            return kq
        cac = K.du_an_dang_bat()
    except Exception as e:  # noqa: BLE001 — kho hỏng: thử lại nhịp sau
        _log(f"kho-{type(e).__name__}", f"không đọc được kho: {type(e).__name__}")
        kq["bo_qua"] = "kho lỗi"
        return kq
    try:
        for da in cac:
            ma = da["ma"]
            du_an = None
            while kq["lo"] < LO_MOI_NHIP:
                rows = K.bl_cho_gan_nhan(ma, P._LO, bo_qua(ma, "bl"))
                loai = "bl"
                if not rows:
                    rows = K.bai_cho_gan_nhan(ma, P._LO_BAI, bo_qua(ma, "bai"))
                    loai = "bai"
                if not rows:
                    break
                if kq["lo"]:
                    ngu(NGHI_GIUA_LO)
                kq["lo"] += 1
                if loai == "bl":
                    x = gan_lo_bl(ma, rows)
                    kq["ghi_bl"] += x["ghi"]
                else:
                    du_an = du_an or K.doc_du_an(ma) or {"ten": da.get("ten") or ma}
                    x = gan_lo_bai(ma, du_an, rows)
                    kq["ghi_bai"] += x["ghi"]
                if x["loi"] or not x["ghi"] and not x["sot"]:
                    # Lô hỏng / hết giờ / không ghi được dòng nào: model có vấn đề — lùi dần.
                    _TRANG["loi_lien"] += 1
                    lui = LUI_GIAY[min(len(LUI_GIAY), _TRANG["loi_lien"]) - 1]
                    _TRANG["nghi_toi"] = time.monotonic() + lui
                    kq["loi"] += 1
                    _log(f"lui-{_TRANG['loi_lien']}", f"lô {loai} của {ma} không gán được — "
                         f"thử lại sau {lui // 60} phút")
                    return kq
                _TRANG["loi_lien"] = 0
                _DA_BAO.discard("lui-1")
    except Exception as e:  # noqa: BLE001 — nhịp không bao giờ ném ra ngoài
        if type(e).__name__ == "MatQuyen":
            kq["bo_qua"] = "mất quyền chủ"
            return kq
        _TRANG["loi_lien"] += 1
        _TRANG["nghi_toi"] = time.monotonic() + LUI_GIAY[
            min(len(LUI_GIAY), _TRANG["loi_lien"]) - 1]
        _log(f"loi-{type(e).__name__}", f"nhịp lỗi: {type(e).__name__}")
        kq["loi"] += 1
    _TRANG["cuoi"] = kq
    return kq


def khoi_dong(nhip: int = NHIP) -> str:
    """Gọi MỘT lần từ run.py (sau `viec_nen.khoi_dong`). Trả dòng trạng thái để in."""
    if not bat():
        return "Gán nhãn nền: ⛔ tắt (MARK_GAN_NHAN_NEN=0) — /theodoi gán nhãn ngay trong lượt"
    import importlib.util
    if importlib.util.find_spec("psycopg") is None:
        return "Gán nhãn nền: ⛔ máy chưa cài psycopg (kho lắng nghe chưa bật)"
    t = _LUONG.get("t")
    if t is None or not t.is_alive():
        def vong():
            while True:
                kq = mot_nhip()
                # Nhịp đầy (còn hàng) thì chạy tiếp ngay sau một quãng nghỉ ngắn.
                time.sleep(NGHI_GIUA_LO if kq.get("lo", 0) >= LO_MOI_NHIP else nhip)
        _LUONG["t"] = threading.Thread(target=vong, name="gan-nhan-nen", daemon=True)
        _LUONG["t"].start()
    return (f"Gán nhãn nền: ✅ nhịp {nhip}s · {LO_MOI_NHIP} lô/nhịp, một lô một lúc · "
            "bình luận/bài chưa phân loại trong kho")
