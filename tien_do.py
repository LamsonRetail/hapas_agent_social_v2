"""Theo dõi tiến độ dự án trên Base checklist: tool hỏi `tra_tien_do` + nhắc hằng ngày vào nhóm.

VÌ SAO CÓ
SOW "Lập tiến độ, giao việc và theo dõi dự án" đòi Mark "TỰ NHẮC DEADLINE VÀO NHÓM CHUNG".
Chủ agent chốt 07/10/2026:
  • 08:30 giờ VN MỖI ngày (cả cuối tuần) gửi vào MỘT nhóm chat do cấu hình máy chạy chọn
    (`MARK_NHAC_TIEN_DO_CHAT`) — nhóm thử trước, nhóm dự án sau. Chưa đặt = TẮT.
  • Chỉ việc CHƯA XONG (TRẠNG THÁI khác "ĐÃ XONG"/"CANCEL") mà QUÁ HẠN hoặc tới hạn trong
    3 ngày. Chỉ @nhắc PIC của việc QUÁ HẠN trong 14 ngày; quá hạn lâu hơn chỉ một dòng đếm
    (sau xem trước thật: 97 việc quá hạn, phần lớn chỉ là chưa cập nhật TRẠNG THÁI). Quá hạn
    không PIC liệt kê tên riêng; việc sắp hạn chỉ ghi tên PIC; thiếu hạn chỉ đếm. Không có gì
    quá hạn (trong ngưỡng)/sắp hạn thì KHÔNG gửi.
  • Tin do CODE soạn và gửi, không qua model: ngày và số phải đúng tuyệt đối — model so
    ngày trên `doc_bang` từng là chỗ dễ sai nhất (lệch múi giờ, nhầm "hôm nay" là quá hạn).

BẤT BIẾN (kiểm bằng test):
  1. Base đích lấy từ cấu hình máy chạy — dùng CHUNG cấu hình với `viec_base_tool`
     (`MARK_BASE_VIEC_*`), đè riêng được bằng `MARK_TIEN_DO_BASE_URL`/`_APP_TOKEN`/`_TABLE_ID`.
  2. Chỉ ĐỌC: đúng hai endpoint GET /fields và POST /records/search, qua `viec_base_tool._goi`
     (gọi ngoài danh sách là ném lỗi trước khi ra mạng).
  3. Chỉ tin nhắc nhóm theo lịch mới có thẻ `<at>`; câu trả lời trong chat không bao giờ tag.
     Chữ người dùng gõ trong Base không thể tự sinh thẻ `<at>` (dấu < > bị thay).
  4. Đọc Base hỏng thì KHÔNG gửi gì vào nhóm (không gửi nửa danh sách, không gửi tin rỗng);
     hết cửa sổ thử lại mà vẫn hỏng thì nhắn RIÊNG chủ agent một lần trong ngày.
  5. Mỗi nhóm tối đa một tin mỗi ngày: sổ `.tokens/nhac_tien_do.json` + uuid Lark
     `tiendo-<chat>-<yymmdd>` (Lark bỏ tin trùng uuid trong 1 giờ — khởi động lại giữa lúc
     gửi và lúc ghi sổ không thành hai tin).
  6. Sổ KHÔNG chứa khoá `app_token`: `bang_tool.base_noi_bo()` coi mọi `app_token` trong
     `.tokens/*.json` là Base nội bộ của Mark và khoá luôn với người hỏi.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict
from urllib.parse import urlparse

import bang_tool as BT
import lark_client as lark
import lark_bang as B
import viec_base_tool as VB
from config import config

from tools.registry import registry, tool_error, tool_result  # type: ignore

_VN = VB._VN
#: Cột cần đọc — tên cột lấy từ viec_base_tool để hai tool không lệch nhau.
COT_CAN = (VB.COT_TEN, VB.COT_NHOM, VB.COT_PIC, VB.COT_HAN, VB.COT_TT)
#: TRẠNG THÁI coi là xong (so sau `VB.chuan`: bỏ dấu, hoa thường, khoảng trắng cuối).
_TT_XONG = frozenset({VB.chuan("ĐÃ XONG"), VB.chuan("CANCEL")})
SO_NGAY_MAC_DINH = 3
#: Mặc định của `qua_han_toi_da()` — chủ agent chốt 07/10/2026 sau khi xem trước thật.
QUA_HAN_TOI_DA = 14
#: Trần số dòng việc trong một tin (chủ agent: ~40) — dài hơn thì người ta không đọc.
TOI_DA_DONG = 40
#: Trần phần tử mỗi danh sách trả về model (câu chữ đã có đủ số đếm).
_TOI_DA_TRA = 100
_THU = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


class CauTrucLoi(Exception):
    """Base thiếu cột / sai kiểu cột. `str(e)` nói được thẳng với người dùng."""


# ───────────────────────────── cấu hình Base ─────────────────────────────
def cau_hinh() -> dict:
    """Base/bảng đọc tiến độ: mặc định CHÍNH Base ghi việc (`VB.cau_hinh`), đè được bằng env
    riêng. Ném ValueError nếu cấu hình hỏng."""
    url = (os.environ.get("MARK_TIEN_DO_BASE_URL") or "").strip()
    app = (os.environ.get("MARK_TIEN_DO_APP_TOKEN") or "").strip()
    bang = (os.environ.get("MARK_TIEN_DO_TABLE_ID") or "").strip()
    goc = VB.cau_hinh()
    if not (url or app or bang):
        return {k: goc[k] for k in ("app_token", "table_id", "url", "ten")}
    nd = B.nhan_dien(url) if url else None
    if url and (not nd or nd[0] != "bitable"):
        raise ValueError("MARK_TIEN_DO_BASE_URL phải là link Base (/base/…?table=tbl…)")
    app = app or (nd[1] if nd else goc["app_token"])
    bang = bang or (nd[2] if nd else "") or (goc["table_id"] if app == goc["app_token"] else "")
    if not re.fullmatch(r"[A-Za-z0-9]{10,}", app):
        raise ValueError("MARK_TIEN_DO_* không có mã Base hợp lệ")
    if not re.fullmatch(r"tbl[A-Za-z0-9]+", bang or ""):
        raise ValueError("MARK_TIEN_DO_* không có mã bảng hợp lệ (?table=tbl…)")
    u = urlparse(url or goc["url"])
    ten = ((os.environ.get("MARK_TIEN_DO_TEN") or "").strip()
           or (goc["ten"] if (app, bang) == (goc["app_token"], goc["table_id"]) else "Base tiến độ"))
    return {"app_token": app, "table_id": bang, "ten": ten,
            "url": f"{u.scheme or 'https'}://{u.hostname}/base/{app}?table={bang}"}


# ───────────────────────────── đọc Base (chỉ đọc) ─────────────────────────────
def doc_viec(d: dict) -> list[dict]:
    """Mọi dòng của bảng, chỉ 5 cột cần. Ném CauTrucLoi khi thiếu/sai cột; lỗi Lark ném
    nguyên. KHÔNG trả nửa bảng: chạm trần trang thì ném."""
    cot = VB._doc_cot(d)
    thieu = [c for c in COT_CAN if c not in cot]
    if thieu:
        raise CauTrucLoi(f"Base '{d['ten']}' thiếu cột: {', '.join(thieu)} — không đọc được "
                         "tiến độ.")
    sai = [f"{c} (cần kiểu {k}, đang là {cot[c]['type']})"
           for c, k in ((VB.COT_HAN, 5), (VB.COT_PIC, 11)) if cot[c]["type"] != k]
    if sai:
        raise CauTrucLoi("Base đổi kiểu cột, Mark không đoán: " + "; ".join(sai))
    ra, tok = [], None
    for _ in range(VB._TOI_DA_TRANG):
        kq = VB._goi("POST", VB._goc(d) + "/records/search",
                     query={"page_size": 500, "page_token": tok, "user_id_type": "open_id"},
                     body={"field_names": list(COT_CAN)})
        data = kq.get("data") or {}
        ra += [{"record_id": it.get("record_id"), "fields": it.get("fields") or {}}
               for it in data.get("items") or []]
        tok = data.get("page_token")
        if not data.get("has_more") or not tok:
            return ra
    raise RuntimeError(f"bảng quá {VB._TOI_DA_TRANG * 500} dòng — không đọc hết, không báo nửa vời")


# ───────────────────────────── lọc ─────────────────────────────
def _sach(s) -> str:
    """Chữ lấy từ Base để IN: gộp khoảng trắng, và thay < > — ai đó gõ `<at user_id="all">`
    vào HẠNG MỤC CV thì tin nhắc nhóm sẽ tag cả nhóm."""
    return VB._gon(s).replace("<", "‹").replace(">", "›")


def ngay_vn(ms) -> datetime.date | None:
    """Ô DEADLINE (ms epoch, Lark lưu 00:00 giờ VN) → ngày theo giờ VN."""
    if isinstance(ms, bool) or ms in (None, ""):
        return None
    try:
        return datetime.datetime.fromtimestamp(int(float(ms)) / 1000, _VN).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def hom_nay_vn(now: datetime.datetime | None = None) -> datetime.date:
    return (now or datetime.datetime.now(_VN)).astimezone(_VN).date()


def _mot_dong(r: dict) -> dict | None:
    f = r.get("fields") or {}
    ten = _sach(VB._chu(f.get(VB.COT_TEN)))
    if not ten:
        return None                 # dòng trống của Base — không phải việc
    pic = VB._nguoi(f.get(VB.COT_PIC))
    oid, ten_pic = (pic[0][0], _sach(VB._ten_goc(pic[0][1])) or "(chưa rõ tên)") if pic else ("", "")
    return {"record_id": r.get("record_id"), "ten": ten,
            "nhom": _sach(VB._chu(f.get(VB.COT_NHOM))), "pic_id": oid, "pic": ten_pic,
            "han": ngay_vn(f.get(VB.COT_HAN)), "tt": VB._gon(VB._chu(f.get(VB.COT_TT)))}


def qua_han_toi_da() -> int:
    """Quá hạn quá chừng này ngày thì coi là "việc cũ chưa cập nhật trạng thái": chỉ đếm,
    không liệt kê, không tag. Xem trước thật 07/10/2026: CHECKLIST DA có 97 việc quá hạn,
    46 việc quá hơn 30 ngày, 72/172 dòng bỏ trống TRẠNG THÁI — tag cả 97 mỗi sáng là spam,
    người ta sẽ tắt thông báo nhóm. Env `MARK_NHAC_TIEN_DO_QUA_HAN_TOI_DA`, mặc định 14."""
    try:
        n = int((os.environ.get("MARK_NHAC_TIEN_DO_QUA_HAN_TOI_DA") or "").strip() or QUA_HAN_TOI_DA)
    except ValueError:
        return QUA_HAN_TOI_DA
    return n if 1 <= n <= 365 else QUA_HAN_TOI_DA


def loc_viec(records: list[dict], hom_nay: datetime.date, so_ngay: int = SO_NGAY_MAC_DINH,
             *, pic: str = "", nhom: str = "", qua_han_toi_da_ngay: int | None = None) -> dict:
    """Hàm thuần. Dòng Bitable thô → {qua_han, qua_han_khong_pic, qua_han_lau, sap_han,
    thieu, dem}.

    - Bỏ dòng không có HẠNG MỤC CV và dòng TRẠNG THÁI xong/cancel (chuẩn hoá khoảng trắng,
      hoa thường, dấu). TRẠNG THÁI trống = chưa xong.
    - Không có DEADLINE → `thieu` (chỉ đếm).
    - Quá hạn > `qua_han_toi_da_ngay` ngày → `qua_han_lau` (có hay không PIC; chỉ đếm).
    - Quá hạn ≤ ngưỡng: có PIC → `qua_han` (được tag), không PIC → `qua_han_khong_pic`
      (liệt kê tên việc, không tag).
    - Hôm nay ≤ DEADLINE ≤ hôm nay + so_ngay: có PIC → `sap_han`; không PIC → `thieu`.
      Hạn đúng hôm nay là SẮP HẠN, chưa quá.
    - `pic`/`nhom`: lọc theo đoạn tên (không dấu, không hoa thường).
    """
    nguong = qua_han_toi_da() if qua_han_toi_da_ngay is None else int(qua_han_toi_da_ngay)
    k_pic, k_nhom = VB.chuan(pic), VB.chuan(nhom)
    qua, qua_kp, lau, sap, thieu = [], [], [], [], []
    xong = 0
    for r in records or []:
        v = _mot_dong(r)
        if v is None:
            continue
        if VB.chuan(v["tt"]) in _TT_XONG:
            xong += 1
            continue
        if k_nhom and k_nhom not in VB.chuan(v["nhom"]):
            continue
        if k_pic and k_pic not in VB.chuan(v["pic"]):
            continue
        if not v["han"]:
            thieu.append(v)
            continue
        lech = (v["han"] - hom_nay).days
        if lech < 0:
            v = {**v, "so_ngay_qua": -lech}
            (lau if -lech > nguong else qua if v["pic_id"] else qua_kp).append(v)
        elif not v["pic_id"]:
            thieu.append(v)
        elif lech <= so_ngay:
            sap.append({**v, "con_ngay": lech})
    for ds in (qua, qua_kp, lau, sap):
        ds.sort(key=lambda v: (v["han"], v["pic"], v["ten"]))
    return {"qua_han": qua, "qua_han_khong_pic": qua_kp, "qua_han_lau": lau, "sap_han": sap,
            "thieu": thieu, "qua_han_toi_da": nguong,
            "dem": {"qua_han": len(qua), "qua_han_khong_pic": len(qua_kp),
                    "qua_han_lau": len(lau), "sap_han": len(sap),
                    "thieu_han_hoac_pic": len(thieu), "da_xong_hoac_cancel": xong}}


# ───────────────────────────── soạn tin ─────────────────────────────
def _nhom_theo_pic(ds: list[dict]) -> list[tuple[dict, list[dict]]]:
    """Gom theo PIC (mỗi người một đầu mục — tag một lần dù nhiều việc), giữ thứ tự việc
    cấp bách nhất trước."""
    g: OrderedDict[str, tuple[dict, list[dict]]] = OrderedDict()
    for v in ds:
        g.setdefault(v["pic_id"], (v, []))[1].append(v)
    return list(g.values())


def _dong_viec(v: dict) -> str:
    if "so_ngay_qua" in v:
        trang = f"quá {v['so_ngay_qua']} ngày"
    else:
        trang = "đến hạn hôm nay" if v["con_ngay"] == 0 else f"còn {v['con_ngay']} ngày"
    # Tên việc dài bất thường (dán cả đoạn mô tả vào HẠNG MỤC CV) cắt ở 140 ký tự: trần dòng
    # TOI_DA_DONG không đủ giữ tin dưới giới hạn độ dài tin nhắn của Lark.
    ten = v["ten"] if len(v["ten"]) <= 140 else v["ten"][:139].rstrip() + "…"
    phan = [ten] + ([v["nhom"]] if v["nhom"] else []) + [f"hạn {v['han']:%d/%m} ({trang})"]
    return "- " + " — ".join(phan)


def soan_tin(ket: dict, hom_nay: datetime.date, d: dict, *, gan_the: bool,
             so_ngay: int = SO_NGAY_MAC_DINH, toi_da: int = TOI_DA_DONG) -> str:
    """Chữ thuần (persona cấm bảng markdown). "" khi không có việc quá hạn trong ngưỡng hay
    sắp hạn — tin nhắc nhóm khi đó không gửi (việc quá hạn lâu một mình không đủ để gửi:
    nhắc mỗi sáng một dòng đếm y hệt thì thành tiếng ồn). `gan_the`=True chỉ dành cho tin
    nhắc nhóm theo lịch: thẻ `<at>` chỉ gắn cho PIC của việc quá hạn trong ngưỡng."""
    qua, qua_kp, sap = ket["qua_han"], ket["qua_han_khong_pic"], ket["sap_han"]
    if not qua and not qua_kp and not sap:
        return ""
    n = ket["qua_han_toi_da"]
    L = [f"{'NHẮC TIẾN ĐỘ' if gan_the else 'TIẾN ĐỘ'} — {_THU[hom_nay.weekday()]} "
         f"{hom_nay:%d/%m/%Y} — {_sach(d['ten'])}",
         f"Quá hạn (trong {n} ngày): {len(qua) + len(qua_kp)} việc · Tới hạn trong {so_ngay} "
         f"ngày tới: {len(sap)} việc"]
    con, bo = toi_da, 0
    for tieu_de, ds, the, theo_pic in (
            (f"QUÁ HẠN (trong {n} ngày)", qua, gan_the, True),
            ("QUÁ HẠN, CHƯA CÓ NGƯỜI PHỤ TRÁCH", qua_kp, False, False),
            (f"SẮP TỚI HẠN ({so_ngay} ngày tới)", sap, False, True)):
        if not ds:
            continue
        if con <= 0:
            bo += len(ds)
            continue
        L += ["", tieu_de + ":"]
        for v0, viec in (_nhom_theo_pic(ds) if theo_pic else [(None, ds)]):
            if con <= 0:
                bo += len(viec)
                continue
            if v0 is not None:
                L.append((f'<at user_id="{v0["pic_id"]}"></at>' if the else v0["pic"]) + ":")
            for v in viec:
                if con <= 0:
                    bo += 1
                    continue
                L.append(_dong_viec(v))
                con -= 1
    L.append("")
    if bo:
        L.append(f"… và {bo} việc khác — xem Base (link bên dưới).")
    if ket["qua_han_lau"]:
        L.append(f"{len(ket['qua_han_lau'])} việc quá hạn hơn {n} ngày — nhờ PIC cập nhật "
                 "TRẠNG THÁI trên Base (link bên dưới).")
    if ket["thieu"]:
        L.append(f"{len(ket['thieu'])} việc chưa có hạn/PIC — xem Base (link bên dưới).")
    L.append(f"Base: {d['url']}")
    return "\n".join(L)


# ───────────────────────────── tool hỏi: tra_tien_do ─────────────────────────────
HUONG_DAN = ("Chép NGUYÊN `cau_tien_do` — ngày và số do CODE so theo giờ VN, không tự so lại. "
             "Việc quá hạn lâu (quá ngưỡng `qua_han_toi_da` ngày) chỉ có dòng đếm trong câu — "
             "người dùng hỏi riêng thì liệt kê từ `qua_han_lau`, nói rõ có thể chỉ là chưa cập "
             "nhật TRẠNG THÁI. Không tag ai, không gửi tin vào nhóm; muốn nhắc ai thì người "
             "dùng tự nhắc.")

SCHEMA = {
    "name": "tra_tien_do",
    "description": (
        "Tra việc QUÁ HẠN và SẮP TỚI HẠN trên Base checklist dự án của team (mặc định Base "
        "do cấu hình máy chạy chọn — CHECKLIST DA), bản mới nhất. CODE so DEADLINE với hôm "
        "nay theo giờ VN, bỏ việc ĐÃ XONG/CANCEL.\n"
        "KHI NÀO GỌI: 'việc nào trễ/quá hạn', 'sắp tới hạn', 'tuần này còn gì', 'việc của "
        "<người>/nhóm <X> có trễ không'. KHÔNG tự so ngày trên `doc_bang`.\n"
        "KHI TRẢ LỜI: chép NGUYÊN `cau_tien_do`; không tag ai, không gửi tin vào nhóm. Bị từ "
        "chối vì quyền thì chuyển NGUYÊN lời hướng dẫn."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "so_ngay": {"type": "integer",
                        "description": "Sắp hạn = tới hạn trong bao nhiêu ngày tới (mặc định 3, 0–30)."},
            "pic": {"type": "string", "description": "Chỉ việc của người này (một đoạn tên)."},
            "nhom": {"type": "string", "description": "Chỉ việc của NHÓM này (MEDIA, BOOKING…)."},
            "qua_han_toi_da": {"type": "integer",
                               "description": "Quá hạn hơn bấy nhiêu ngày thì gộp thành một "
                                              "dòng đếm (mặc định 14, 1–365)."},
            "nguon": {"type": "string",
                      "description": "Link Base khác có cùng cột (HẠNG MỤC CV, NHÓM, PIC, "
                                     "DEADLINE, TRẠNG THÁI). Bỏ trống = Base checklist mặc định."},
        },
    },
}


def _gon_viec(v: dict) -> dict:
    return {"hang_muc": v["ten"], "nhom": v["nhom"] or None, "pic": v["pic"] or None,
            "han": f"{v['han']:%Y-%m-%d}" if v["han"] else None,
            **({"so_ngay_qua": v["so_ngay_qua"]} if "so_ngay_qua" in v else {}),
            **({"con_ngay": v["con_ngay"]} if "con_ngay" in v else {})}


def _dich_tu_nguon(nguon: str, d: dict | None) -> tuple[dict | None, str]:
    """Link người dùng dán (hoặc Base mặc định) → (đích đọc, lỗi). Quyền đọc kiểm ở
    `bang_tool.mo_nguon` — CHUNG MỘT CỬA với doc_bang/dem_bang."""
    try:
        loai, token, phu, ten_loai, _vi_sao = BT.mo_nguon(nguon)
    except BT.TuChoi as e:
        return None, str(e)
    if loai != "bitable":
        return None, (f"Đây là {ten_loai}, không phải Base checklist. Tiến độ chỉ tra trên Base "
                      "có cột HẠNG MỤC CV, PIC, DEADLINE, TRẠNG THÁI.")
    if d and token == d["app_token"] and (not phu or phu == d["table_id"]):
        return dict(d), ""
    if not phu:
        return None, "Link Base cần chỉ đúng một bảng (có ?table=tbl…)."
    u = urlparse(nguon if nguon.startswith("http") else (d or {}).get("url", ""))
    return {"app_token": token, "table_id": phu, "ten": "Base đã dẫn",
            "url": f"{u.scheme or 'https'}://{u.hostname or 'o4pvcegwn6b.sg.larksuite.com'}"
                   f"/base/{token}?table={phu}"}, ""


def _handle(args: dict, **_kw) -> str:
    a = args or {}
    try:
        so_ngay = max(0, min(30, int(a.get("so_ngay") if a.get("so_ngay") not in (None, "")
                                     else SO_NGAY_MAC_DINH)))
    except (TypeError, ValueError):
        return tool_error("`so_ngay` phải là số ngày (0–30).")
    try:
        nguong = (max(1, min(365, int(a["qua_han_toi_da"])))
                  if a.get("qua_han_toi_da") not in (None, "") else qua_han_toi_da())
    except (TypeError, ValueError):
        return tool_error("`qua_han_toi_da` phải là số ngày (1–365).")
    try:
        d = cau_hinh()
    except ValueError as e:
        d, loi_ch = None, str(e)
    else:
        loi_ch = ""
    nguon = str(a.get("nguon") or "").strip()
    if not nguon and not d:
        return tool_error(f"Cấu hình Base tiến độ hỏng: {loi_ch}")
    dich, loi = _dich_tu_nguon(nguon or d["url"], d)
    if not dich:
        return tool_error(loi)
    try:
        dong = doc_viec(dich)
    except CauTrucLoi as e:
        return tool_error(str(e))
    except Exception as e:  # noqa: BLE001
        return tool_error(BT.loi_doc("Base", e))
    hom_nay = hom_nay_vn()
    ket = loc_viec(dong, hom_nay, so_ngay, pic=str(a.get("pic") or ""),
                   nhom=str(a.get("nhom") or ""), qua_han_toi_da_ngay=nguong)
    loc = ", ".join(x for x in (f"PIC '{a['pic']}'" if a.get("pic") else "",
                                f"NHÓM '{a['nhom']}'" if a.get("nhom") else "") if x)
    cau = soan_tin(ket, hom_nay, dich, gan_the=False, so_ngay=so_ngay)
    if not cau:
        cau = (f"Không có việc nào quá hạn trong {nguong} ngày gần đây hoặc tới hạn trong "
               f"{so_ngay} ngày tới" + (f" ({loc})" if loc else "")
               + f" trên {_sach(dich['ten'])} (tính tới {hom_nay:%d/%m/%Y})."
               + (f" {len(ket['qua_han_lau'])} việc quá hạn hơn {nguong} ngày — nhờ PIC cập "
                  "nhật TRẠNG THÁI trên Base." if ket["qua_han_lau"] else "")
               + (f" {len(ket['thieu'])} việc chưa có hạn/PIC." if ket["thieu"] else "")
               + f" Base: {dich['url']}")
    elif loc:
        cau = cau.replace("\n", f" (lọc {loc})\n", 1)
    return tool_result(
        success=True, bang=dich["ten"], bang_url=dich["url"], hom_nay=f"{hom_nay:%Y-%m-%d}",
        so_ngay=so_ngay, qua_han_toi_da=nguong, dem=ket["dem"],
        qua_han=[_gon_viec(v) for v in ket["qua_han"][:_TOI_DA_TRA]],
        qua_han_khong_pic=[_gon_viec(v) for v in ket["qua_han_khong_pic"][:_TOI_DA_TRA]],
        qua_han_lau=[_gon_viec(v) for v in ket["qua_han_lau"][:_TOI_DA_TRA]],
        sap_han=[_gon_viec(v) for v in ket["sap_han"][:_TOI_DA_TRA]],
        thieu_han_hoac_pic=[_gon_viec(v) for v in ket["thieu"][:_TOI_DA_TRA]],
        cau_tien_do=cau, huong_dan=HUONG_DAN)


# ───────────────────────────── nhắc hằng ngày vào nhóm ─────────────────────────────
_SO = config.token_file.parent / "nhac_tien_do.json"
#: Mark khởi động trễ: còn gửi bù trong chừng này sau giờ hẹn (08:30 → tới 10:30), quá
#: thì bỏ hôm đó — tin "nhắc deadline" lúc chiều tối gây rối hơn là giúp.
CUA_SO_BU = datetime.timedelta(hours=2)
#: Đọc Base/gửi lỗi tạm: thử lại sau chừng này (trong cửa sổ bù), không dội Lark mỗi nhịp.
_LUI_KHI_LOI = 300
_KHOA = threading.Lock()
_trang_thai: dict = {"thu_lai_sau": 0.0, "da_bao": set()}


def cau_hinh_nhac() -> tuple[dict | None, str]:
    """({chat, gio, phut} | None, lý do tắt). Chỉ từ env máy chạy — model không chọn được
    nhóm nào nhận tin."""
    chat = (os.environ.get("MARK_NHAC_TIEN_DO_CHAT") or "").strip()
    if not chat:
        return None, "chưa đặt MARK_NHAC_TIEN_DO_CHAT"
    if not re.fullmatch(r"oc_[A-Za-z0-9]+", chat):
        return None, "MARK_NHAC_TIEN_DO_CHAT phải là mã nhóm oc_…"
    gio = (os.environ.get("MARK_NHAC_TIEN_DO_GIO") or "08:30").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", gio)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None, f"MARK_NHAC_TIEN_DO_GIO '{gio}' không phải HH:MM"
    return {"chat": chat, "gio": int(m.group(1)), "phut": int(m.group(2))}, ""


def dang_bat() -> bool:
    return cau_hinh_nhac()[0] is not None


def trang_thai_khoi_dong() -> str:
    ch, ly_do = cau_hinh_nhac()
    if not ch:
        return f"Nhắc tiến độ: TẮT ({ly_do})"
    return (f"Nhắc tiến độ: BẬT → nhóm {ch['chat']} {ch['gio']:02d}:{ch['phut']:02d} "
            "mỗi ngày (giờ VN)")


def _uuid(tien_to: str, dich: str, ngay: datetime.date) -> str:
    """`<tiền tố>-<đích>-<yymmdd>`. Lark nhận uuid ≤ 50 ký tự và `send_text` cắt đuôi — cắt
    thì mất ngày, nên đích dài bất thường đổi sang băm thay vì để cắt."""
    u = f"{tien_to}-{dich}-{ngay:%y%m%d}"
    if len(u) > 50:
        u = f"{tien_to}-{hashlib.sha256(dich.encode()).hexdigest()[:24]}-{ngay:%y%m%d}"
    return u


def uuid_nhac(chat: str, ngay: datetime.date) -> str:
    return _uuid("tiendo", chat, ngay)


def uuid_bao_chu(chu: str, ngay: datetime.date) -> str:
    return _uuid("tdchu", chu, ngay)


def _doc_so() -> dict:
    try:
        j = json.loads(_SO.read_text(encoding="utf-8"))
        return j if isinstance(j, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _cap_nhat_so(chat: str, **truong) -> None:
    """Sổ theo nhóm: `ngay`/`ket_qua` = ngày đã XONG (gửi được, không có gì để gửi, hoặc đã
    báo chủ agent là hỏng); `loi_ngay`/`loi` = lỗi gần nhất (để báo chủ agent khi hết cửa
    sổ, kể cả sau khi khởi động lại)."""
    so = _doc_so()
    so[chat] = {**(so.get(chat) or {}), **truong, "luc": time.time()}
    _SO.parent.mkdir(parents=True, exist_ok=True)
    tam = _SO.with_suffix(".tmp")
    tam.write_text(json.dumps(so, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tam, _SO)


def _xong(chat: str, ngay: datetime.date, ket_qua: str) -> None:
    _cap_nhat_so(chat, ngay=f"{ngay:%Y-%m-%d}", ket_qua=ket_qua)


def _ghi_loi(chat: str, ngay: datetime.date, ly_do: str) -> None:
    _cap_nhat_so(chat, loi_ngay=f"{ngay:%Y-%m-%d}", loi=ly_do[:200])


def _bao_mot_lan(khoa: str, chu: str) -> None:
    """Log mỗi sự việc MỘT lần (nhịp 30 giây mà in lỗi mỗi nhịp thì log ngập)."""
    if khoa not in _trang_thai["da_bao"]:
        _trang_thai["da_bao"].add(khoa)
        print(f"[tien_do] {chu}", flush=True)


def den_luot(now: datetime.datetime, gio: int, phut: int) -> str:
    """'chua_den' | 'gui' | 'qua_cua_so' — hàm thuần, theo giờ VN."""
    now = now.astimezone(_VN)
    moc = now.replace(hour=gio, minute=phut, second=0, microsecond=0)
    if now < moc:
        return "chua_den"
    return "gui" if now < moc + CUA_SO_BU else "qua_cua_so"


def soan_tin_hom_nay(hom_nay: datetime.date) -> tuple[str, dict]:
    """(tin sẽ gửi hoặc "", đích). Ném khi đọc Base hỏng — nơi gọi KHÔNG gửi gì."""
    d = cau_hinh()
    ket = loc_viec(doc_viec(d), hom_nay)
    return soan_tin(ket, hom_nay, d, gan_the=True), d


def _bao_chu(chat: str, ngay: datetime.date, ly_do: str) -> str:
    """Nhắn RIÊNG chủ agent một lần trong ngày khi nhóm không nhận được nhắc vì lỗi.

    Vì sao: lỗi chỉ nằm trong log thì không ai biết sáng nay nhóm thiếu tin. Gửi vào chính
    nhóm thì lộ lỗi kỹ thuật cho cả team và vẫn có thể hỏng y như tin nhắc. Chỉ open_id
    của chủ agent (env), không bao giờ là nhóm; uuid theo ngày để Lark bỏ tin trùng."""
    # MARK_NHAC_TIEN_DO_BAO_LOI trước: prod cố ý KHÔNG đặt AGENT_BOSS_OPEN_ID (biến đó còn cấp
    # quyền chủ agent cho doc_bang…), nên báo lỗi cần một biến riêng chỉ dùng cho việc này.
    chu = ((os.environ.get("MARK_NHAC_TIEN_DO_BAO_LOI") or "").strip()
           or (os.environ.get("AGENT_BOSS_OPEN_ID") or "").strip()
           or (os.environ.get("STEVEN_BOSS_OPEN_ID") or "").strip())
    ket = "da_bao_chu"
    if not chu.startswith("ou_"):
        ket = "khong_bao_duoc_chu"
        _bao_mot_lan(f"chu-{ngay}", "không có MARK_NHAC_TIEN_DO_BAO_LOI/AGENT_BOSS_OPEN_ID để báo "
                                    "lỗi nhắc tiến độ")
    else:
        try:
            lark.send_text("open_id", chu,
                           f"Hôm nay chưa gửi được nhắc tiến độ vào nhóm: {ly_do}",
                           uuid=uuid_bao_chu(chu, ngay))
        except Exception as e:  # noqa: BLE001
            ket = "khong_bao_duoc_chu"
            _bao_mot_lan(f"chu-{ngay}", f"báo chủ agent cũng hỏng: {str(e)[:200]}")
    _xong(chat, ngay, ket)
    return ket


def chay_mot_nhip(now: datetime.datetime | None = None) -> str:
    """Một nhịp của bộ nhắc. Trả kết quả để test/log: 'tat' | 'chua_den' | 'da_xu_ly' |
    'qua_cua_so' | 'cho_thu_lai' | 'loi_doc' | 'loi_gui' | 'khong_co_gi' | 'da_gui' |
    'da_bao_chu' | 'khong_bao_duoc_chu'. Không bao giờ ném.

    Lỗi (đọc Base / gửi) trong cửa sổ: thử lại sau 5 phút. Hết cửa sổ mà hôm nay vẫn lỗi
    → nhắn riêng chủ agent MỘT lần. Lỗi vĩnh viễn (bot bị mời ra khỏi nhóm…) thì báo ngay,
    vì chờ thêm không đổi được gì."""
    try:
        ch, _ = cau_hinh_nhac()
        if not ch:
            return "tat"
        now = (now or datetime.datetime.now(_VN)).astimezone(_VN)
        ngay = now.date()
        hom_nay = f"{ngay:%Y-%m-%d}"
        chat = ch["chat"]
        with _KHOA:
            so = _doc_so().get(chat) or {}
            if so.get("ngay") == hom_nay:
                return "da_xu_ly"
            luot = den_luot(now, ch["gio"], ch["phut"])
            if luot == "chua_den":
                return "chua_den"
            if luot == "qua_cua_so":
                if so.get("loi_ngay") == hom_nay:
                    return _bao_chu(chat, ngay, str(so.get("loi") or "lỗi không rõ"))
                _bao_mot_lan(f"bo-{ngay}", f"bỏ nhắc ngày {ngay:%d/%m}: đã quá "
                             f"{ch['gio']:02d}:{ch['phut']:02d} + 2 giờ mà chưa gửi")
                return "qua_cua_so"
            if time.time() < _trang_thai["thu_lai_sau"]:
                return "cho_thu_lai"
            try:
                tin, _d = soan_tin_hom_nay(ngay)
            except Exception as e:  # noqa: BLE001 — đọc hỏng: KHÔNG gửi nửa vời
                _ghi_loi(chat, ngay, f"không đọc được Base ({str(e)[:120]})")
                _trang_thai["thu_lai_sau"] = time.time() + _LUI_KHI_LOI
                _bao_mot_lan(f"doc-{ngay}", f"không đọc được Base, chưa gửi nhắc "
                             f"(thử lại sau {_LUI_KHI_LOI // 60} phút): {str(e)[:200]}")
                return "loi_doc"
            if not tin:
                _xong(chat, ngay, "khong_co_gi")
                _bao_mot_lan(f"trong-{ngay}", f"{ngay:%d/%m}: không có việc quá hạn/sắp hạn "
                             "— không gửi")
                return "khong_co_gi"
            import scheduler  # gửi đúng đường nhắc lịch dùng (oc_ → lark.send_text kèm uuid)
            try:
                scheduler._gui(chat, tin, uuid_nhac(chat, ngay))
            except scheduler.LoiGui as e:
                ly_do = f"gửi vào nhóm bị Lark từ chối ({str(e)[:120]})"
                _ghi_loi(chat, ngay, ly_do)
                if e.vinh_vien:
                    _bao_mot_lan(f"gui-{ngay}", f"gửi nhắc vào {chat} hỏng vĩnh viễn, bỏ hôm "
                                 f"nay (bot còn trong nhóm không?): {e}")
                    _bao_chu(chat, ngay, ly_do)
                else:
                    _trang_thai["thu_lai_sau"] = time.time() + _LUI_KHI_LOI
                    _bao_mot_lan(f"gui-{ngay}", f"gửi nhắc lỗi tạm, thử lại sau "
                                 f"{_LUI_KHI_LOI // 60} phút: {e}")
                return "loi_gui"
            _xong(chat, ngay, "da_gui")
            _trang_thai["thu_lai_sau"] = 0.0
            print(f"[tien_do] đã nhắc tiến độ {ngay:%d/%m} → {chat}", flush=True)
            return "da_gui"
    except Exception as e:  # noqa: BLE001 — bộ nhắc không bao giờ được làm chết Mark
        _bao_mot_lan(f"loi-{type(e).__name__}", f"lỗi nhịp nhắc: {type(e).__name__}: {e}")
        return "loi"


def khoi_dong(nhip: int = 30) -> str:
    """Gọi từ run.py. Chưa cấu hình thì KHÔNG dựng luồng. Trả dòng trạng thái để in."""
    dong = trang_thai_khoi_dong()
    if not dang_bat():
        return dong

    def _vong():
        while True:
            chay_mot_nhip()
            time.sleep(nhip)

    threading.Thread(target=_vong, name="nhac-tien-do", daemon=True).start()
    return dong


def loi_dan() -> str:
    """Một dòng cho system prompt: Mark chỉ được nói mình nhắc nhóm khi THẬT SỰ đang bật."""
    ch, _ = cau_hinh_nhac()
    if ch:
        return (f"\n- NHẮC TIẾN ĐỘ HẰNG NGÀY: đang BẬT — {ch['gio']:02d}:{ch['phut']:02d} mỗi "
                "ngày CODE tự gửi danh sách việc quá hạn/sắp tới hạn của Base checklist vào "
                "MỘT nhóm đã cấu hình sẵn (chỉ tag PIC việc quá hạn gần đây; không có gì thì không "
                "gửi). Được hỏi thì nói đúng vậy. Mark KHÔNG đổi được nhóm, giờ hay nội dung "
                "nhắc, và không tự gửi tin hay tag ai từ chat.")
    return ("\n- NHẮC TIẾN ĐỘ HẰNG NGÀY vào nhóm: đang TẮT (máy chạy chưa cấu hình). KHÔNG "
            "nói hay hứa Mark sẽ tự nhắc deadline vào nhóm; hỏi trễ hạn thì dùng "
            "`tra_tien_do`, muốn nhắc nhóm hằng ngày thì chủ agent bật trên máy chạy.")


def register() -> None:
    try:
        registry.register(
            name="tra_tien_do", toolset="lark_api", schema=SCHEMA, handler=_handle,
            check_fn=lambda: True, requires_env=[], is_async=False,
            description="Tra việc quá hạn / sắp tới hạn trên Base checklist (code so ngày)",
            emoji="⏰", override=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[tien_do] register warning: {e}")


register()
