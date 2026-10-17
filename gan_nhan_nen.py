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
  • LÔ HỎNG = model lỗi / hết giờ / trả rác / trả JSON mà bỏ sót ≥ 80% dòng (review 17/10, M1: bỏ
    sót cả lô là model có vấn đề, không phải lỗi của từng dòng). Lô hỏng KHÔNG phạt dòng nào. Mỗi
    (dự án, loại) có cỡ lô riêng, giảm một nửa sau mỗi lô hỏng (tăng gấp đôi lại khi lô chạy được):
      – model còn sống (có lô chạy được trong `SONG_GIAY`): thử lại ngay với lô nhỏ hơn — dòng
        "độc" (luôn làm hỏng lô) bị khoanh dần tới lô MỘT dòng; dòng đó được để riêng và CHỈ bị
        ghi một lần thử khi lô ngay sau nó chạy được (chứng tỏ model sống — review 17/10, M2: lô
        luôn hỏng theo thứ tự cố định từng chặn cả dự án);
      – model chưa thấy sống (sập, hết hạn mức): lùi 1 → 30 phút cho riêng (dự án, loại) đó và
        sang dự án kế tiếp — không phạt dòng, không chặn dự án khác.
  • Dòng bị bỏ sót / dòng độc: đếm lần thử trong sổ nhỏ `.gan-nhan-that-bai.json` cạnh sổ việc
    nền; đủ `TOI_DA_THU` lần thì bỏ qua `HET_HAN_NGAY` ngày (rồi thử lại), có ghi log khi bỏ.
  • Nhường lease model cho lượt chat: MỘT lô một lúc (`song_song=1`), nghỉ `NGHI_GIUA_LO` giây
    giữa hai lô, tối đa `LO_MOI_NHIP` lô mỗi nhịp; không gọi thêm model nào ngoài lô gán nhãn.
  • Ngân sách Apify và lịch quét không liên quan: nhịp này không chạy actor, không tạo việc nền,
    không chiếm chỗ trong hàng đợi việc (`viec_nen` chỉ chạy một việc một lúc).

Bình luận trước (nhiều like trước), rồi bài (phân xử hết giờ / "không rõ", bài Báo & Web — xem
`phan_loai.phan_loai_bai`; bài kênh nhà không vào hàng). Trạng thái: dashboard tự đếm dòng còn
chờ trong kho (ⓘ cạnh khối sắc thái), lượt quét ghi "N bình luận chờ gán nhãn nền" vào ghi chú.

Tắt: `MARK_GAN_NHAN_NEN=0` — lượt `/theodoi` quay lại gán nhãn ngay trong việc như cũ (cũng vậy
khi luồng nền không chạy: `dang_chay()`).
"""
from __future__ import annotations

import datetime
import json
import os
import threading
import time

NHIP = 60                 # giây giữa hai nhịp khi hàng đợi trống / sau một nhịp đầy
NGHI_GIUA_LO = 5          # giây nghỉ giữa hai lô model trong một nhịp
LO_MOI_NHIP = 6           # lô tối đa mỗi nhịp (rồi nhường nhịp sau)
HAN_LO = 180.0            # hạn một lô model (giây) — như scripts/lang_nghe_gan_lai.py
TOI_DA_THU = 3            # lần thử hỏng của MỘT dòng trước khi bỏ qua dòng đó
HET_HAN_NGAY = 7          # dòng bị bỏ qua được thử lại sau chừng này ngày
TI_LE_LO_HONG = 0.8       # model bỏ sót ≥ 80% dòng của lô = lô hỏng (không phạt dòng)
SONG_GIAY = 300           # có lô chạy được trong chừng này giây = model còn sống
LUI_GIAY = (60, 120, 300, 900, 1800)   # lùi sau lô hỏng liên tiếp khi model chưa thấy sống
_TRANG: dict = {"song_luc": None, "khoa": {}, "cuoi": None}
_LUONG: dict = {}
_KHOA_SO = threading.Lock()
_DA_BAO: set[str] = set()


def bat() -> bool:
    return (os.environ.get("MARK_GAN_NHAN_NEN") or "1").strip() != "0"


def dang_chay() -> bool:
    """Nền bật VÀ luồng nhịp đang sống trong tiến trình này — `/theodoi` chỉ để trống nhãn khi
    có người gán (không thì gán ngay trong lượt như cũ)."""
    t = _LUONG.get("t")
    return bat() and t is not None and t.is_alive()


def _log(khoa: str, chu: str) -> None:
    """Log mỗi sự việc MỘT lần (nhịp 60 giây mà in lỗi mỗi nhịp thì log ngập)."""
    if khoa in _DA_BAO:
        return
    if len(_DA_BAO) > 200:
        _DA_BAO.clear()
    _DA_BAO.add(khoa)
    print(f"[gan_nhan_nen] {chu}", flush=True)


def _quen_log(dau: str) -> None:
    """Đã hồi phục: lần hỏng sau lại được ghi log."""
    for k in [k for k in _DA_BAO if k.startswith(dau)]:
        _DA_BAO.discard(k)


# ───────────────────────────── sổ dòng hỏng ─────────────────────────────
def _duong_so():
    import apify_tool as A
    return A._thu_muc_nen() / ".gan-nhan-that-bai.json"


def _hom_nay() -> str:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).date().isoformat()


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
        _log(f"so-{type(e).__name__}", f"không ghi được sổ dòng hỏng: {type(e).__name__}")


def _con_han(x, moc: str) -> bool:
    return isinstance(x, dict) and str(x.get("luc") or "") >= moc


def _moc_het_han() -> str:
    return (datetime.date.fromisoformat(_hom_nay())
            - datetime.timedelta(days=HET_HAN_NGAY)).isoformat()


def bo_qua(ma: str, loai: str) -> list[str]:
    """Khoá dòng đã hỏng ≥ `TOI_DA_THU` lần trong `HET_HAN_NGAY` ngày (`loai` = "bl" | "bai")."""
    moc = _moc_het_han()
    x = ((doc_so().get(ma) or {}).get(loai) or {})
    return sorted(k for k, v in x.items()
                  if _con_han(v, moc) and int(v.get("n") or 0) >= TOI_DA_THU)


def dem_bo_sot(ma: str, loai: str, khoa_sot: list[str], khoa_xong: list[str]) -> list[str]:
    """+1 lần thử hỏng cho `khoa_sot`; dòng đã gán xong thì xoá khỏi sổ; mục quá hạn bị dọn.
    -> khoá vừa chạm `TOI_DA_THU` (bắt đầu bị bỏ qua — có log)."""
    if not khoa_sot and not khoa_xong:
        return []
    moc, hom_nay = _moc_het_han(), _hom_nay()
    moi_bo: list[str] = []
    with _KHOA_SO:
        d = doc_so()
        cu = d.setdefault(ma, {}).get(loai) or {}
        x = {k: v for k, v in cu.items() if _con_han(v, moc)}
        for k in khoa_xong:
            x.pop(k, None)
        for k in khoa_sot:
            n = int((x.get(k) or {}).get("n") or 0) + 1
            x[k] = {"n": n, "luc": hom_nay}
            if n == TOI_DA_THU:
                moi_bo.append(k)
        if len(x) > 5000:                       # chặn trên: giữ phần hỏng nhiều nhất
            x = dict(sorted(x.items(), key=lambda kv: -int(kv[1].get("n") or 0))[:5000])
        d[ma][loai] = x
        _ghi_so(d)
    if moi_bo:
        print(f"[gan_nhan_nen] {ma}: bỏ qua {len(moi_bo)} {'bình luận' if loai == 'bl' else 'bài'}"
              f" sau {TOI_DA_THU} lần gán hỏng (thử lại sau {HET_HAN_NGAY} ngày): "
              + ", ".join(k.replace("\x1f", "/") for k in moi_bo[:5]), flush=True)
    return moi_bo


# ───────────────────────────── một lô ─────────────────────────────
def khoa_bl(r: dict) -> str:
    return f"{r['khoa_bai']}\x1f{r['ma']}"


def _lo_hong(x: dict, n: int) -> bool:
    return bool(x["loi"]) or x["sot"] >= TI_LE_LO_HONG * n or (not x["ghi"] and not x["sot"])


def ngu_canh_bai(r: dict) -> str:
    """Nội dung + hashtag của bài chứa bình luận (cột `bai_noi_dung`, `bai_hashtag` của
    `lang_nghe_db.bl_cho_gan_nhan`) — để model đoán MÓN khách hỏi mua (17/10/2026)."""
    nd = " ".join(str(r.get("bai_noi_dung") or "").split())
    ht = " ".join(str(r.get("bai_hashtag") or "").split())
    return f"{nd} | #{ht}" if nd and ht else nd or (f"#{ht}" if ht else "")


def brand_du_an(du_an: dict | None) -> str:
    """Tên + từ khoá + mô tả brand của dự án (cấu hình dashboard, tin cậy) — model cần biết brand
    bán gì để tách "hỏi mua hàng của brand" khỏi "xin link váy KOL mặc" (17/10/2026)."""
    import phan_loai as P
    if not du_an:
        return ""
    ten = ", ".join(dict.fromkeys(str(x) for x in P.thuong_hieu_du_an(du_an) if str(x).strip()))
    bc = " ".join(str(du_an.get("boi_canh") or "").split())
    return f"{ten} — {bc}" if ten and bc else ten or bc


def gan_lo_bl(ma: str, rows: list[dict], brand: str = "") -> dict:
    """Gán + ghi một lô bình luận (đã đọc từ kho). -> {ghi, sot, loi, hong}. Lô hỏng không ghi
    lần thử nào vào sổ (bên gọi quyết định khi lô chỉ còn một dòng). Mỗi dòng kèm ngữ cảnh bài
    và ghi cả MÓN hỏi mua (`binh_luan.san_pham`)."""
    import lang_nghe_db as K
    import phan_loai as P
    tt: dict = {}
    nhan = P.phan_loai_binh_luan(
        [{"text": r.get("noi_dung") or "", "likes": int(r.get("thich") or 0),
          "ngu_canh_bai": ngu_canh_bai(r)} for r in rows],
        HAN_LO, tt, song_song=1, brand=brand, kem_san_pham=True)
    ghi = [(r["khoa_bai"], r["ma"], r.get("noi_dung") or "", s, c, sp)
           for r, (s, c, sp) in zip(rows, nhan) if s != P.CHUA and c != P.CHUA]
    x = {"ghi": K.ghi_nhan_bl(ma, ghi), "sot": len(tt.get("khong_tra") or []),
         "loi": int(tt.get("lo_loi") or 0) + int(tt.get("lo_het_gio") or 0)}
    x["hong"] = _lo_hong(x, len(rows))
    sot = [] if x["hong"] else [khoa_bl(rows[i]) for i in tt.get("khong_tra") or []]
    dem_bo_sot(ma, "bl", sot, [f"{g[0]}\x1f{g[1]}" for g in ghi])
    return x


def gan_lo_bai(ma: str, du_an: dict, rows: list[dict]) -> dict:
    import lang_nghe_db as K
    import phan_loai as P
    tt: dict = {}
    brand = ", ".join(dict.fromkeys(str(x) for x in P.thuong_hieu_du_an(du_an) if str(x).strip()))
    nhan = P.phan_loai_bai(rows, brand, HAN_LO, tt, song_song=1)
    ghi = [(r["khoa"], r.get("noi_dung") or "", x[0], x[1]) for r, x in zip(rows, nhan) if x]
    x = {"ghi": K.ghi_nhan_bai(ma, ghi), "sot": len(tt.get("khong_tra") or []),
         "loi": int(tt.get("lo_loi") or 0) + int(tt.get("lo_het_gio") or 0),
         "rui_ro": int(tt.get("rui_ro") or 0)}
    x["hong"] = _lo_hong(x, len(rows))
    sot = [] if x["hong"] else [rows[i]["khoa"] for i in tt.get("khong_tra") or []]
    dem_bo_sot(ma, "bai", sot, [g[0] for g in ghi])
    return x


# ───────────────────────────── nhịp ─────────────────────────────
def _co_quyen() -> bool:
    import viec_nen
    return viec_nen.con_quyen()


def _trang_khoa(ma: str, loai: str, day_du: int) -> dict:
    return _TRANG["khoa"].setdefault((ma, loai), {"co": day_du, "loi_lien": 0, "nghi_toi": 0.0,
                                                  "nghi_ngo": None})


def _song(bay_gio: float) -> bool:
    s = _TRANG["song_luc"]
    return s is not None and bay_gio - s < SONG_GIAY


def _lui(ma: str, loai: str, st: dict, bay_gio: float) -> None:
    lui = LUI_GIAY[min(len(LUI_GIAY), max(1, st["loi_lien"])) - 1]
    st["nghi_toi"] = bay_gio + lui
    _log(f"lui-{ma}-{loai}-{st['loi_lien']}", f"{ma}: lô {'bình luận' if loai == 'bl' else 'bài'}"
         f" không gán được — thử lại sau {lui // 60} phút")


def mot_nhip(ngu=time.sleep, dong_ho=time.monotonic) -> dict:
    """Một nhịp: tối đa `LO_MOI_NHIP` lô qua các dự án đang bật (bình luận trước, rồi bài). Một
    (dự án, loại) đang lùi thì bỏ qua, sang loại/dự án kế. Không bao giờ ném. -> thống kê."""
    import lang_nghe_db as K
    import phan_loai as P
    kq = {"lo": 0, "ghi_bl": 0, "ghi_bai": 0, "loi": 0, "bo_qua": ""}
    if not bat():
        kq["bo_qua"] = "tắt"
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
    for da in cac:
        ma = da["ma"]
        du_an = None
        for loai, day_du in (("bl", P._LO), ("bai", P._LO_BAI)):
            st = _trang_khoa(ma, loai, day_du)
            while kq["lo"] < LO_MOI_NHIP and dong_ho() >= st["nghi_toi"]:
                try:
                    co = max(1, min(day_du, int(st["co"])))
                    bo = bo_qua(ma, loai) + ([st["nghi_ngo"]] if st["nghi_ngo"] else [])
                    rows = (K.bl_cho_gan_nhan(ma, co, bo) if loai == "bl"
                            else K.bai_cho_gan_nhan(ma, co, bo))
                    if not rows:
                        if st["nghi_ngo"]:
                            # Chỉ còn dòng đang bị nghi: chưa chứng minh được gì — thả ra, lùi.
                            st["nghi_ngo"] = None
                            _lui(ma, loai, st, dong_ho())
                        break
                    if kq["lo"]:
                        ngu(NGHI_GIUA_LO)
                    kq["lo"] += 1
                    du_an = du_an or K.doc_du_an(ma) or {"ten": da.get("ten") or ma}
                    if loai == "bl":
                        x = gan_lo_bl(ma, rows, brand_du_an(du_an))
                        kq["ghi_bl"] += x["ghi"]
                    else:
                        x = gan_lo_bai(ma, du_an, rows)
                        kq["ghi_bai"] += x["ghi"]
                except Exception as e:  # noqa: BLE001 — nhịp không bao giờ ném ra ngoài
                    if type(e).__name__ == "MatQuyen":
                        kq["bo_qua"] = "mất quyền chủ"
                        return kq
                    _log(f"loi-{ma}-{loai}-{type(e).__name__}", f"{ma}/{loai}: lỗi "
                         f"{type(e).__name__}")
                    x, rows = {"hong": True}, []
                bay_gio = dong_ho()
                if not x["hong"]:
                    _TRANG["song_luc"] = bay_gio
                    if st["nghi_ngo"]:
                        # Lô MỘT dòng vừa hỏng mà lô ngay sau chạy được: model sống, dòng đó độc.
                        dem_bo_sot(ma, loai, [st["nghi_ngo"]], [])
                        st["nghi_ngo"] = None
                    st.update(loi_lien=0, co=min(day_du, max(1, int(st["co"])) * 2))
                    _quen_log(f"lui-{ma}-{loai}")
                    continue
                kq["loi"] += 1
                st["loi_lien"] += 1
                if rows and len(rows) == 1 and not st["nghi_ngo"]:
                    # Nghi dòng độc: để riêng ra, thử lô kế. Lô kế chạy được thì mới ghi lần thử
                    # cho dòng này; lô kế cũng hỏng thì là model — bỏ nghi ngờ, lùi.
                    st["nghi_ngo"] = khoa_bl(rows[0]) if loai == "bl" else rows[0]["khoa"]
                    continue
                st["nghi_ngo"] = None
                if rows and len(rows) > 1 and _song(bay_gio):
                    st["co"] = max(1, len(rows) // 2)       # khoanh vùng: thử ngay lô nhỏ hơn
                    continue
                st["co"] = max(1, int(st["co"]) // 2)
                _lui(ma, loai, st, bay_gio)
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
