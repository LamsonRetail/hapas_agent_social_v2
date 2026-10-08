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

LỆNH `/tiendo` + LỊCH TRÊN CONSOLE (chủ agent chốt 07/10/2026)
Nhắc deadline chuyển sang quản lý trên console Platform: một lịch "Giao việc" (mode=run) đặt
trong đúng nhóm, nội dung `/tiendo <link Base> [tuỳ chọn]`. Tới giờ Platform đẩy câu đó thành
job cho Mark (payload `scheduled: true`, `scheduled_by` = open_id người đặt lịch). Mark trả lời
HOÀN TOÀN bằng code (`lenh_tiendo`, gọi từ `lenh_cung`) — không model — nên tin trong nhóm đúng
từng ngày, từng số. Nhóm nhận = chính cuộc chat của job, không có cấu hình nhóm nào khác.
  7. Base bất kỳ cùng "motif" (tên việc, người phụ trách, hạn, trạng thái): cột TỰ NHẬN theo
     KIỂU (`nhan_cot`); nhận không chắc thì TRẢ LỜI danh sách cột ứng viên + cú pháp chỉ rõ
     (`cot_han="…"`…) — không đoán. Base có đúng bộ cột CHECKLIST DA (hoặc chính Base cấu hình
     trên máy) thì dùng nguyên cách đọc cũ (`COT_MAC_DINH`).
  8. Chỉ lượt CHẠY THEO LỊCH mới gắn `<at>` (và `tag=khong` tắt được). `/tiendo` một người
     gõ tay KHÔNG BAO GIỜ tag — chỉ ghi tên — để không ai mượn Mark tag cả nhóm hàng loạt.
  9. Quyền đọc Base: CÙNG luật `bang_tool.mo_nguon` với doc_bang, xét cho NGƯỜI HỎI — gõ tay
     là người gửi; theo lịch là `scheduled_by`. Lịch không có `scheduled_by` thì TỪ CHỐI,
     không bao giờ lùi về "bot đọc được là đủ".
 10. Bộ nhắc env (`MARK_NHAC_TIEN_DO_CHAT`) và lịch console không cùng nhắc một Base vào một
     nhóm trong một ngày: sổ `.tokens/nhac_tien_do.json` ghi `lich_ngay`/`lich_base` (băm, không
     phải app_token — xem 6), hai bên kiểm dưới cùng khoá `_KHOA`.
 11. Chỉ ĐỌC thêm hai endpoint lấy TÊN Base/bảng cho dòng tiêu đề (`_goi_ten`, hỏng thì bỏ qua).
 12. `cua_toi=co` (chủ agent chốt 08/10/2026): chỉ việc mà NGƯỜI HỎI (gõ tay = người gửi; theo
     lịch = `scheduled_by`) nằm trong cột người phụ trách — so bằng open_id, KHÔNG BAO GIỜ theo
     tên (trùng tên/đổi tên là lộ việc người khác hoặc sót việc của mình). Không có danh tính
     `ou_…` thì TỪ CHỐI. Danh sách của chính mình nên KHÔNG BAO GIỜ gắn `<at>` (kể cả lượt
     theo lịch). Không có tham số nào cho chọn "của ai" — chỉ là người hỏi, nên không ai mượn
     được lệnh để xem riêng việc của người khác. Khử trùng lượt lịch theo Base+nhóm+người.
 13. Bot chỉ có quyền XEM thì Lark không cho bot xem danh sách thành viên (403) — Mark
     không tự chứng minh được ai xem được bảng. Lượt THEO LỊCH nhận thêm phép kiểm của
     Platform (payload `nguon_da_kiem`, Platform kiểm bằng token Lark CỦA người đặt lịch lúc
     tạo và ở mỗi lần chạy). Nó chỉ thay bước tra thành viên khi `boi` == `scheduled_by` ==
     người hỏi, (loại, token, bảng) KHỚP TUYỆT ĐỐI link trong lệnh (sau khi giải Wiki) và
     `kiem_luc` trong 2 giờ; luật Base nội bộ xét TRƯỚC, không đổi (không mở Audit/Chi phí).
     Chỉ `_kenh_cua_job` của job theo lịch mang khoá này; gõ tay, tool model, tin thường
     giữ nguyên luật cũ. Platform báo `nguon_loi` mà không căn cứ nào khác đạt → từ chối,
     nêu lý do + "console → Lịch chạy để Kết nối Lark/kiểm lại".
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shlex
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


#: Ánh xạ cột của Base CHECKLIST DA (motif gốc). `xong` = TRẠNG THÁI coi là xong (đã chuẩn
#: hoá); `kieu_tt` 3 = chọn một, 7 = ô tích (tích = xong).
COT_MAC_DINH = {"ten": VB.COT_TEN, "nhom": VB.COT_NHOM, "pic": VB.COT_PIC, "han": VB.COT_HAN,
                "tt": VB.COT_TT, "kieu_tt": 3, "xong": _TT_XONG}
#: Trần chữ in ra: tên người, tên Base, cả tin (Lark nhận tin dài hơn nhiều, nhưng tin nhắc
#: dài quá một màn hình thì không ai đọc hết; trần dòng TOI_DA_DONG là chặn chính).
_TRAN_TEN_NGUOI = 60
_TRAN_TEN_BASE = 80
TRAN_KY_TU = 6000
CU_PHAP_NGAN = ('Dùng /tiendo <link Base> [cot_ten="Tên việc"] [cot_pic="Phụ trách"] '
                '[cot_han="Ngày hết hạn"] [cot_tt="Status"] [xong="Done;Huỷ"] '
                '[so_ngay=3] [qua_han_toi_da=14] [tag=co|khong] [cua_toi=co|khong].')
#: Lời từ chối `cua_toi` khi lượt không mang danh tính Lark `ou_…` (job web chưa xác thực,
#: lịch không có người đặt…). Không lùi về lọc theo tên — trùng tên là lộ việc người khác.
LOI_KHONG_RO_NGUOI = ("Chưa biết bạn là ai trên Lark nên không lọc được việc của bạn. Hỏi "
                      "Mark trong Lark (nhóm hoặc chat riêng), hoặc bỏ cua_toi=co.")


def _la_open_id(s) -> bool:
    return bool(re.fullmatch(r"ou_[A-Za-z0-9]+", str(s or "")))


#: Hướng dẫn khi /tiendo bị từ chối vì chưa chứng minh được quyền xem (thường: bot chỉ có
#: quyền xem nên không tra được danh sách thành viên). Đường chạy được: lịch console — Platform
#: kiểm bằng tài khoản Lark của người đặt (bất biến 13).
HUONG_DAN_LICH = ("Muốn Mark báo tiến độ bảng này mỗi ngày: thêm bot vào tài liệu (quyền "
                  "xem), dán link bảng, đặt lịch trên console → Lịch chạy (lần đầu bấm Kết "
                  "nối tài khoản Lark).")


def _goi_y_lich(loi: str) -> str:
    """Gợi ý đường lịch console cho lời từ chối QUYỀN thường — không cho từ chối Base nội bộ
    (lịch cũng không mở được) hay lời đã chỉ console sẵn."""
    if (not loi.startswith("Không đọc ") or "nội bộ" in loi or "Audit" in loi
            or "Lịch chạy" in loi):
        return ""
    return " " + HUONG_DAN_LICH


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
def _kiem_mac_dinh(cot: dict, d: dict) -> None:
    """Bộ cột CHECKLIST DA phải đủ và đúng kiểu — không thì ném CauTrucLoi (không đoán)."""
    thieu = [c for c in COT_CAN if c not in cot]
    if thieu:
        raise CauTrucLoi(f"Base '{d['ten']}' thiếu cột: {', '.join(thieu)} — không đọc được "
                         "tiến độ.")
    sai = [f"{c} (cần kiểu {k}, đang là {cot[c]['type']})"
           for c, k in ((VB.COT_HAN, 5), (VB.COT_PIC, 11)) if cot[c]["type"] != k]
    if sai:
        raise CauTrucLoi("Base đổi kiểu cột, Mark không đoán: " + "; ".join(sai))


def doc_viec(d: dict) -> list[dict]:
    """Mọi dòng của bảng, chỉ 5 cột CHECKLIST DA. Ném CauTrucLoi khi thiếu/sai cột; lỗi Lark
    ném nguyên. KHÔNG trả nửa bảng: chạm trần trang thì ném. (Bộ nhắc env dùng đường này.)"""
    _kiem_mac_dinh(VB._doc_cot(d), d)
    return _doc_dong(d, list(COT_CAN))


def _ten_cot_doc(cot: dict) -> list[str]:
    return [cot[k] for k in ("ten", "nhom", "pic", "han", "tt") if cot.get(k)]


def doc_theo_cot(d: dict, ghi_de: dict | None = None, *, mac_dinh: bool = False
                 ) -> tuple[dict, list[dict]]:
    """(ánh xạ cột, mọi dòng) cho Base bất kỳ. Không chỉ rõ cột nào (`ghi_de` rỗng) mà Base là
    Base cấu hình trên máy (`mac_dinh`) hoặc có đủ bộ cột CHECKLIST DA → đọc y cách cũ (kiểm
    chặt, `COT_MAC_DINH`). Còn lại → tự nhận cột theo kiểu (`nhan_cot`), ném CauTrucLoi kèm
    danh sách cột ứng viên khi không chắc."""
    cot_base = VB._doc_cot(d)
    ghi_de = {k: v for k, v in (ghi_de or {}).items() if v}
    if not ghi_de and (mac_dinh or _co_motif_goc(cot_base)):
        _kiem_mac_dinh(cot_base, d)
        return COT_MAC_DINH, _doc_dong(d, list(COT_CAN))
    cot = nhan_cot(cot_base, ghi_de, ten_base=d.get("ten") or "")
    return cot, _doc_dong(d, _ten_cot_doc(cot))


def _co_motif_goc(cot_base: dict) -> bool:
    return (all(c in cot_base for c in COT_CAN) and cot_base[VB.COT_HAN]["type"] == 5
            and cot_base[VB.COT_PIC]["type"] == 11)


# ───────────────────────────── tự nhận cột theo kiểu ─────────────────────────────
#: Kiểu cột Bitable v1 dùng ở đây: 1 chữ, 3 chọn một, 4 chọn nhiều, 5 ngày, 7 ô tích, 11 người.
_TEN_KIEU = {1: "Chữ", 2: "Số", 3: "Chọn một", 4: "Chọn nhiều", 5: "Ngày", 7: "Ô tích",
             11: "Người", 15: "Link", 20: "Công thức", 1001: "Ngày tạo", 1002: "Ngày sửa",
             1003: "Người tạo", 1004: "Người sửa", 1005: "Số tự tăng"}
#: Lựa chọn TRẠNG THÁI coi là xong: so trên chữ đã chuẩn hoá (bỏ dấu: hủy/huỷ → huy) theo
#: TỪ, không theo chuỗi con — "Chưa xong"/"not done" bị loại nhờ `_PHU_DINH`.
_XONG = re.compile(r"\b(xong|done|hoan thanh|cancel|cancell?ed|huy|completed?|finished)\b")
_PHU_DINH = re.compile(r"\b(chua|khong|not|no|dang|sap)\b")
#: Gợi ý theo tên, xếp bậc: bậc đầu có đúng một cột thì chọn; bậc đầu có nhiều cột thì
#: KHÔNG chọn (mơ hồ). "người" xếp sau "PIC/phụ trách" vì "Người duyệt" cũng là người.
_GOI_Y = {
    "pic": (("pic", "phu trach", "assignee", "owner", "chu tri"), ("nguoi",)),
    "han": (("deadline", "han", "due", "han chot", "thoi han"),),
    "tt": (("trang thai", "status", "tinh trang", "tien do"),),
}
_TEN_VAI = {"ten": "TÊN VIỆC", "pic": "NGƯỜI PHỤ TRÁCH", "han": "HẠN (deadline)",
            "tt": "TRẠNG THÁI", "nhom": "NHÓM"}
_KHOA_VAI = {"ten": "cot_ten", "pic": "cot_pic", "han": "cot_han", "tt": "cot_tt",
             "nhom": "cot_nhom"}


def la_xong(lua_chon: str) -> bool:
    """Một lựa chọn trạng thái có nghĩa "đã xong/đã huỷ"? (ĐÃ XONG, Done, Hoàn thành ,
    Cancel, Huỷ… — không phải "Chưa xong", "Not done", "Đang hoàn thành".)"""
    n = VB.chuan(lua_chon)
    return bool(n and _XONG.search(n) and not _PHU_DINH.search(n))


def _co_cum(ten: str, cum: str) -> bool:
    """Tên cột có CỤM TỪ `cum` (so theo từ, đã chuẩn hoá) — "hạn" khớp "Ngày hết hạn" nhưng
    không khớp "Hoàn thành"."""
    tu = " " + " ".join(re.findall(r"[a-z0-9]+", VB.chuan(ten))) + " "
    return f" {cum} " in tu


def _chon_theo_ten(ung_vien: list[str], vai: str) -> tuple[str, list[str]]:
    """(cột chọn được hoặc "", nhóm còn mơ hồ). Một ứng viên → chọn luôn."""
    if len(ung_vien) == 1:
        return ung_vien[0], []
    for bac in _GOI_Y.get(vai, ()):
        khop = [t for t in ung_vien if any(_co_cum(t, c) for c in bac)]
        if len(khop) == 1:
            return khop[0], []
        if len(khop) > 1:
            return "", khop
    return "", ung_vien


def _tim_cot(cot_base: dict, ten: str) -> str:
    """Tên cột người dùng gõ → tên cột thật (đúng y hệt, hoặc khớp sau chuẩn hoá và DUY NHẤT)."""
    if ten in cot_base:
        return ten
    khop = [t for t in cot_base if VB.chuan(t) == VB.chuan(ten)]
    return khop[0] if len(khop) == 1 else ""


def _ds_ten(ds, toi_da: int = 10) -> str:
    ds = list(ds)
    phan = [f'"{_sach(t)[:40]}"' for t in ds[:toi_da]]
    return ", ".join(phan) + (f" … (+{len(ds) - toi_da})" if len(ds) > toi_da else "") if ds \
        else "(không có)"


def nhan_cot(cot_base: dict, ghi_de: dict | None = None, *, ten_base: str = "") -> dict:
    """Hàm thuần. Cột của bảng ({tên: {type, options, primary}}) + phần người dùng chỉ rõ →
    ánh xạ {ten, pic, han, tt, kieu_tt, xong, nhom}. Ném CauTrucLoi liệt kê MỌI chỗ chưa chắc
    (cột ứng viên + cú pháp chỉ rõ) — một lần, không bắt người dùng sửa từng lỗi một.

    - PIC: cột kiểu Người (11). Nhiều cột thì ưu tiên tên có PIC/phụ trách, rồi "người".
    - HẠN: cột kiểu Ngày (5) — ngày tạo/sửa tự động không tính. Nhiều thì ưu tiên hạn/deadline/due.
    - TRẠNG THÁI: cột Chọn một có lựa chọn kiểu xong/done/hoàn thành/cancel/huỷ; hoặc cột Ô tích
      tên như "Xong"/"Done" (tích = xong). Nhiều thì ưu tiên tên trạng thái/status.
    - TÊN VIỆC: cột chính (primary) nếu là chữ, không thì cột chữ đầu tiên.
    - NHÓM: chỉ khi chỉ rõ, hoặc có đúng một cột tên NHÓM/Team/Group/Bộ phận.
    - `xong`: tên lựa chọn (ngăn bằng ;) — phải có thật trong cột trạng thái.
    """
    g = ghi_de or {}
    loi: list[str] = []
    ra: dict = {}
    theo_kieu = lambda *k: [t for t, c in cot_base.items() if c.get("type") in k]  # noqa: E731

    def chi_ro(vai: str, kieu_cho: tuple[int, ...]) -> str:
        ten = str(g.get(vai) or "").strip()
        if not ten:
            return ""
        that = _tim_cot(cot_base, ten)
        if not that:
            loi.append(f'- Không thấy cột "{_sach(ten)[:60]}". Các cột đang có: '
                       f"{_ds_ten(cot_base, 15)}")
            return ""
        k = cot_base[that].get("type")
        if k not in kieu_cho:
            loi.append(f'- Cột "{_sach(that)[:60]}" là kiểu {_TEN_KIEU.get(k, k)}, '
                       f"{_TEN_VAI[vai]} cần kiểu "
                       f"{' hoặc '.join(_TEN_KIEU[x] for x in kieu_cho)}.")
            return ""
        return that

    # PIC
    pic = chi_ro("pic", (11,))
    if not pic and not g.get("pic"):
        uv = theo_kieu(11)
        pic, mo_ho = _chon_theo_ten(uv, "pic")
        if not pic:
            loi.append(f"- {_TEN_VAI['pic']}: " + (
                "bảng không có cột kiểu Người (Lark: Người/User) — Mark cần cột đó để biết ai "
                "phụ trách." if not uv else
                f"có {len(mo_ho)} cột kiểu Người, chưa rõ cột nào: {_ds_ten(mo_ho)}") +
                f' → thêm cot_pic="Tên cột"')
    # HẠN
    han = chi_ro("han", (5,))
    if not han and not g.get("han"):
        uv = theo_kieu(5)
        han, mo_ho = _chon_theo_ten(uv, "han")
        if not han:
            loi.append(f"- {_TEN_VAI['han']}: " + (
                "bảng không có cột kiểu Ngày — không có hạn thì không tính được trễ hay sắp "
                "hạn." if not uv else
                f"có {len(mo_ho)} cột kiểu Ngày, chưa rõ cột nào là hạn: {_ds_ten(mo_ho)}") +
                ' → thêm cot_han="Tên cột"')
    # TRẠNG THÁI
    tt = chi_ro("tt", (3, 7))
    if not tt and not g.get("tt"):
        uv = ([t for t in theo_kieu(3) if any(la_xong(o) for o in cot_base[t].get("options") or [])]
              + [t for t in theo_kieu(7) if la_xong(t)])
        tt, mo_ho = _chon_theo_ten(uv, "tt")
        if not tt:
            chon_mot = theo_kieu(3)
            loi.append(f"- {_TEN_VAI['tt']}: " + (
                f"chưa thấy cột Chọn một nào có lựa chọn kiểu xong/done/hoàn thành/cancel/huỷ "
                f"(cột Chọn một đang có: {_ds_ten(chon_mot)})" if not uv else
                f"có {len(mo_ho)} cột trạng thái, chưa rõ cột nào: {_ds_ten(mo_ho)}") +
                ' → thêm cot_tt="Tên cột" (và xong="Tên lựa chọn xong;Tên lựa chọn huỷ")')
    # TÊN VIỆC
    ten = chi_ro("ten", (1, 3))
    if not ten and not g.get("ten"):
        chinh = [t for t, c in cot_base.items() if c.get("primary") and c.get("type") == 1]
        chu = theo_kieu(1)
        ten = (chinh or chu or [""])[0]
        if not ten:
            loi.append(f"- {_TEN_VAI['ten']}: bảng không có cột chữ nào → thêm "
                       'cot_ten="Tên cột"')
    # NHÓM (tuỳ chọn)
    nhom = chi_ro("nhom", (1, 3, 4))
    if not nhom and not g.get("nhom"):
        uv = [t for t in theo_kieu(1, 3)
              if VB.chuan(t) in ("nhom", "team", "group", "bo phan", "phong ban")]
        nhom = uv[0] if len(uv) == 1 else ""
    # TẬP "XONG"
    xong: frozenset = frozenset()
    kieu_tt = cot_base[tt]["type"] if tt else 3
    if tt and kieu_tt == 3:
        lc = cot_base[tt].get("options") or []
        if g.get("xong"):
            muon = [x for x in g["xong"] if x.strip()]
            thieu = [x for x in muon if VB.chuan(x) not in {VB.chuan(o) for o in lc}]
            if thieu:
                loi.append(f'- Cột "{_sach(tt)[:60]}" không có lựa chọn {_ds_ten(thieu)}. '
                           f"Lựa chọn đang có: {_ds_ten(lc, 15)}")
            xong = frozenset(VB.chuan(x) for x in muon)
        else:
            xong = frozenset(VB.chuan(o) for o in lc if la_xong(o))
            if not xong:
                loi.append(f'- Cột "{_sach(tt)[:60]}" không có lựa chọn nào kiểu xong/done/'
                           f"hoàn thành/cancel/huỷ (đang có: {_ds_ten(lc, 15)}) → thêm "
                           'xong="Tên lựa chọn xong"')
    if loi:
        raise CauTrucLoi(
            f"Chưa đọc được tiến độ trên {_sach(ten_base)[:_TRAN_TEN_BASE] or 'bảng này'}: Mark "
            "không đoán cột.\n" + "\n".join(loi) + "\n" + CU_PHAP_NGAN)
    ra.update(ten=ten, pic=pic, han=han, tt=tt, kieu_tt=kieu_tt, xong=xong, nhom=nhom)
    return ra


def _doc_dong(d: dict, ten_cot: list[str]) -> list[dict]:
    """Mọi dòng của bảng, chỉ các cột `ten_cot`. KHÔNG trả nửa bảng: chạm trần trang thì ném."""
    ra, tok = [], None
    for _ in range(VB._TOI_DA_TRANG):
        kq = VB._goi("POST", VB._goc(d) + "/records/search",
                     query={"page_size": 500, "page_token": tok, "user_id_type": "open_id"},
                     body={"field_names": list(ten_cot)})
        data = kq.get("data") or {}
        ra += [{"record_id": it.get("record_id"), "fields": it.get("fields") or {}}
               for it in data.get("items") or []]
        tok = data.get("page_token")
        if not data.get("has_more"):
            return ra
        if not tok:
            raise RuntimeError("Lark thiếu mã trang tiếp theo — không báo tiến độ từ nửa bảng")
    raise RuntimeError(f"bảng quá {VB._TOI_DA_TRANG * 500} dòng — không đọc hết, không báo nửa vời")


# ───────────────────────────── lọc ─────────────────────────────
def _sach(s) -> str:
    """Chữ lấy từ Base để IN: gộp khoảng trắng, và thay < > — ai đó gõ `<at user_id="all">`
    vào HẠNG MỤC CV thì tin nhắc nhóm sẽ tag cả nhóm. Và tách `{{` — câu trả lời job đi qua
    Platform, nơi `{{@Tên}}` được ĐỔI THÀNH tag thật (tra thành viên nhóm theo tên): một tên
    việc chứa `{{@Linh}}` sẽ tag người ngay cả khi `/tiendo` gõ tay (không được tag)."""
    return re.sub(r"\{(?=\{)", "{ ", VB._gon(s).replace("<", "‹").replace(">", "›"))


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


def _mot_dong(r: dict, cot: dict | None = None) -> dict | None:
    c = cot or COT_MAC_DINH
    f = r.get("fields") or {}
    ten = _sach(VB._chu(f.get(c["ten"])))
    if not ten:
        return None                 # dòng trống của Base — không phải việc
    pic = VB._nguoi(f.get(c["pic"])) if c.get("pic") else []
    # MỌI open_id trong ô người phụ trách (việc nhiều PIC): `cua_toi` so trên cả danh sách,
    # còn `pic_id` (người đầu) vẫn là người được tag/đứng tên nhóm như trước.
    pic_ids = [x[0] for x in pic]
    oid, ten_pic = ((pic[0][0], _sach(VB._ten_goc(pic[0][1]))[:_TRAN_TEN_NGUOI] or "(chưa rõ tên)")
                    if pic else ("", ""))
    o_tt = f.get(c["tt"]) if c.get("tt") else None
    # Ô tích (kiểu 7): tích = xong. Chọn một: so tên lựa chọn đã chuẩn hoá với tập `xong`.
    xong = (o_tt is True) if c.get("kieu_tt") == 7 else (VB.chuan(VB._chu(o_tt)) in c["xong"])
    return {"record_id": r.get("record_id"), "ten": ten,
            "nhom": _sach(VB._chu(f.get(c["nhom"]))) if c.get("nhom") else "",
            "pic_id": oid, "pic_ids": pic_ids, "pic": ten_pic, "han": ngay_vn(f.get(c["han"])),
            "tt": VB._gon(VB._chu(o_tt)) if not isinstance(o_tt, bool) else str(o_tt),
            "xong": xong}


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
             *, pic: str = "", nhom: str = "", qua_han_toi_da_ngay: int | None = None,
             cot: dict | None = None, chi_cua: str = "") -> dict:
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
    - `cot`: ánh xạ cột (`nhan_cot`); None = bộ cột CHECKLIST DA.
    - `chi_cua`: open_id — chỉ giữ việc có người này trong cột PIC (so open_id, không theo
      tên); lọc TRƯỚC mọi đếm để số "đã xong" cũng chỉ là việc của người đó.
    """
    nguong = qua_han_toi_da() if qua_han_toi_da_ngay is None else int(qua_han_toi_da_ngay)
    k_pic, k_nhom = VB.chuan(pic), VB.chuan(nhom)
    qua, qua_kp, lau, sap, thieu = [], [], [], [], []
    xong = 0
    for r in records or []:
        v = _mot_dong(r, cot)
        if v is None:
            continue
        if chi_cua and chi_cua not in v["pic_ids"]:
            continue
        if v["xong"]:
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
             so_ngay: int = SO_NGAY_MAC_DINH, toi_da: int = TOI_DA_DONG,
             nhac: bool | None = None, cot: dict | None = None, cua_toi: bool = False) -> str:
    """Chữ thuần (persona cấm bảng markdown). "" khi không có việc quá hạn trong ngưỡng hay
    sắp hạn — tin nhắc nhóm khi đó không gửi (việc quá hạn lâu một mình không đủ để gửi:
    nhắc mỗi sáng một dòng đếm y hệt thì thành tiếng ồn). `gan_the`=True chỉ dành cho tin
    nhắc nhóm theo lịch: thẻ `<at>` chỉ gắn cho PIC của việc quá hạn trong ngưỡng.
    `cua_toi`: danh sách việc của CHÍNH người hỏi — không bao giờ gắn thẻ, không gom theo
    PIC (việc nhiều PIC thì người đứng đầu ô có thể là người khác)."""
    qua, qua_kp, sap = ket["qua_han"], ket["qua_han_khong_pic"], ket["sap_han"]
    if not qua and not qua_kp and not sap:
        return ""
    n = ket["qua_han_toi_da"]
    nhac = gan_the if nhac is None else nhac
    if cua_toi:
        gan_the = False
    L = [f"{'NHẮC TIẾN ĐỘ' if nhac else 'TIẾN ĐỘ'}{' — VIỆC CỦA BẠN' if cua_toi else ''} — "
         f"{_THU[hom_nay.weekday()]} {hom_nay:%d/%m/%Y} — {_sach(d['ten'])[:_TRAN_TEN_BASE]}",
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
        for v0, viec in (_nhom_theo_pic(ds) if theo_pic and not cua_toi else [(None, ds)]):
            if con <= 0:
                bo += len(viec)
                continue
            if v0 is not None:
                at = the and re.fullmatch(r"ou_[A-Za-z0-9]+", v0["pic_id"])
                L.append((f'<at user_id="{v0["pic_id"]}"></at>' if at else v0["pic"]) + ":")
            for v in viec:
                if con <= 0:
                    bo += 1
                    continue
                L.append(_dong_viec(v))
                con -= 1
    duoi = []
    if bo:
        duoi.append(f"… và {bo} việc khác — xem Base (link bên dưới).")
    if ket["qua_han_lau"]:
        duoi.append(f"{len(ket['qua_han_lau'])} việc quá hạn hơn {n} ngày — "
                    f"{'bạn cập nhật' if cua_toi else 'nhờ PIC cập nhật'} "
                    f"{_sach((cot or COT_MAC_DINH)['tt'])[:40]} trên Base (link bên dưới).")
    if ket["thieu"]:
        duoi.append(f"{len(ket['thieu'])} việc chưa có hạn{'' if cua_toi else '/PIC'} — xem "
                    "Base (link bên dưới).")
    duoi.append(f"Base: {d['url']}")
    tin = "\n".join(L + [""] + duoi)
    if len(tin) <= TRAN_KY_TU:
        return tin
    bao = "… tin dài, xem đủ trên Base."
    while L and len("\n".join(L + [bao] + duoi)) > TRAN_KY_TU:
        L.pop()
    return "\n".join(L + [bao] + duoi)


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
        "<người>/nhóm <X> có trễ không', 'việc của tôi còn gì' (→ `cua_toi`=true). KHÔNG tự "
        "so ngày trên `doc_bang`.\n"
        "KHI TRẢ LỜI: chép NGUYÊN `cau_tien_do`; không tag ai, không gửi tin vào nhóm. Bị từ "
        "chối vì quyền thì chuyển NGUYÊN lời hướng dẫn."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "so_ngay": {"type": "integer",
                        "description": "Sắp hạn = tới hạn trong bao nhiêu ngày tới (mặc định 3, 0–30)."},
            "pic": {"type": "string", "description": "Chỉ việc của người này (một đoạn tên)."},
            "cua_toi": {"type": "boolean",
                        "description": "true khi người hỏi muốn VIỆC CỦA CHÍNH HỌ ('việc của "
                                       "tôi/em', 'tôi còn trễ gì'): code lọc theo danh tính "
                                       "Lark của người đang nói (không theo tên). Đừng điền "
                                       "tên họ vào `pic` thay cho cái này."},
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


def _dich_tu_nguon(nguon: str, d: dict | None, *, nguoi_hoi: str | None = None,
                   chung_minh=None, loi_lich: str = "") -> tuple[dict | None, str]:
    """Link người dùng dán (hoặc Base mặc định) → (đích đọc, lỗi). Quyền đọc kiểm ở
    `bang_tool.mo_nguon` — CHUNG MỘT CỬA với doc_bang/dem_bang. `chung_minh`/`loi_lich`
    chỉ có ở lượt THEO LỊCH (bất biến 13)."""
    try:
        them = {} if nguoi_hoi is None else {"nguoi_hoi": nguoi_hoi}
        if chung_minh is not None:
            them["chung_minh"] = chung_minh
        if loi_lich:
            them["loi_lich"] = loi_lich
        loai, token, phu, ten_loai, _vi_sao = BT.mo_nguon(nguon, **them)
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
    cua_toi = a.get("cua_toi") is True or str(a.get("cua_toi") or "").strip().lower() in (
        "true", "1", "co", "có", "yes")
    # Danh tính lấy từ LƯỢT (cùng nguồn `mo_nguon` xét quyền), không bao giờ từ đối số model.
    chu_viec = BT._nguoi_hoi() if cua_toi else ""
    if cua_toi and not _la_open_id(chu_viec):
        return tool_error(LOI_KHONG_RO_NGUOI)
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
    # `tra_tien_do` trước đây luôn ép mọi nguồn qua cột cố định CHECKLIST DA. Vì vậy
    # Base Kế hoạch có đủ motif nhưng dùng tên tự nhiên (Hạng mục, Người phụ trách,
    # Hạn, Trạng thái) vẫn bị báo sai cấu trúc, trong khi đường cứng /tiendo đọc được.
    # Chỉ nguồn TƯỜNG MINH khác Base cấu hình mới tự nhận cột; đường mặc định và link
    # trỏ đúng Base cấu hình giữ nguyên doc_viec kiểm chặt để không đổi bộ nhắc cũ.
    nguon_khac_mac_dinh = bool(nguon) and (
        d is None or _khoa_base(dich) != _khoa_base(d)
    )
    try:
        if nguon_khac_mac_dinh:
            dich["ten"] = ten_base(dich)
            cot, dong = doc_theo_cot(dich)
        else:
            cot, dong = None, doc_viec(dich)
    except CauTrucLoi as e:
        return tool_error(str(e))
    except Exception as e:  # noqa: BLE001
        return tool_error(BT.loi_doc("Base", e))
    hom_nay = hom_nay_vn()
    ket = loc_viec(dong, hom_nay, so_ngay, pic=str(a.get("pic") or ""),
                   nhom=str(a.get("nhom") or ""), qua_han_toi_da_ngay=nguong, cot=cot,
                   chi_cua=chu_viec)
    loc = ", ".join(x for x in (f"PIC '{a['pic']}'" if a.get("pic") else "",
                                f"NHÓM '{a['nhom']}'" if a.get("nhom") else "") if x)
    cau = soan_tin(ket, hom_nay, dich, gan_the=False, so_ngay=so_ngay, cot=cot,
                   cua_toi=cua_toi)
    if not cau:
        cau = (f"{'Bạn không có' if cua_toi else 'Không có'} việc nào quá hạn trong "
               f"{nguong} ngày gần đây hoặc tới hạn trong "
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
        so_ngay=so_ngay, qua_han_toi_da=nguong, dem=ket["dem"], chi_viec_cua_nguoi_hoi=cua_toi,
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
            # Cùng sổ/khoá với lịch console, nhưng khoá theo Base+bảng+nhóm.
            if da_nhac(chat, cau_hinh(), ngay):
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
            ghi_nhac(chat, _d, ngay)
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
                "bộ nhắc này, và không tự gửi tin hay tag ai từ chat. Nhắc Base khác hoặc nhóm "
                "khác: đặt LỊCH (`schedule_reminder` mode=run, message `/tiendo <link Base>`) "
                "sau khi người dùng xác nhận, hoặc họ tự đặt trên console → Lịch chạy.")
    return ("\n- BỘ NHẮC TIẾN ĐỘ CŨ TRÊN MÁY: đang TẮT (máy chạy chưa cấu hình) — trạng thái "
            "này KHÔNG nói gì về lịch trên console. Hỏi trễ hạn thì dùng `tra_tien_do` hoặc "
            "/tiendo <link Base>. Muốn nhắc tiến độ hằng ngày: đặt LỊCH (`schedule_reminder` "
            "mode=run, recurrence=daily, message `/tiendo <link Base>`) sau khi người dùng "
            "xác nhận giờ + nội dung + nhóm nhận, hoặc họ tự đặt trên console → Lịch chạy. "
            "Chưa đặt lịch thật thì KHÔNG hứa Mark sẽ tự nhắc.")


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


def tach_tuy_chon(text: str) -> tuple[str, dict]:
    """Bóc quoted names bằng shlex; không tự bỏ qua đối số sai."""
    parts = shlex.split(text)
    nguon, opts = "", {}
    cho = {"cot_ten", "cot_pic", "cot_han", "cot_tt", "xong", "so_ngay",
           "qua_han_toi_da", "tag", "cua_toi"}
    for part in parts:
        if "=" not in part or part.startswith(("https://", "http://", "base:")):
            if nguon:
                raise ValueError('Chỉ nhận một link Base; tên cột có dấu cách cần đặt trong "…".')
            nguon = part
            continue
        k, v = part.split("=", 1)
        if k not in cho or not v or k in opts:
            raise ValueError(f'Tuỳ chọn không hợp lệ: {_sach(k)}. Dùng cot_han="Ngày giao", so_ngay=3, tag=khong.')
        opts[k] = v
    for key, default, lo, hi in (("so_ngay", 3, 0, 30), ("qua_han_toi_da", qua_han_toi_da(), 1, 365)):
        opts[key] = int(opts.get(key, default))
        if not lo <= opts[key] <= hi:
            raise ValueError(f"{key} phải từ {lo} đến {hi}.")
    if opts.get("tag", "co") not in ("co", "khong"):
        raise ValueError("tag phải là co hoặc khong.")
    if opts.get("cua_toi", "khong") not in ("co", "khong"):
        raise ValueError("cua_toi phải là co hoặc khong.")
    return nguon, opts


def _khoa_base(d: dict, rieng: str = "") -> str:
    """Khoá sổ của một Base+bảng; `rieng` (open_id) = lượt `cua_toi` của MỘT người — khoá
    riêng để lịch "việc của tôi" không chặn (hay bị chặn bởi) lịch cả nhóm cùng Base."""
    # Không lưu app_token: bang_tool coi token trong sổ là Base nội bộ.
    goc = f"{d['app_token']}:{d['table_id']}" + (f":{rieng}" if rieng else "")
    return hashlib.sha256(goc.encode()).hexdigest()


def da_nhac(chat: str, d: dict, ngay: datetime.date, rieng: str = "") -> bool:
    so = _doc_so().get(chat) or {}
    entry = (so.get("bases") or {}).get(_khoa_base(d, rieng)) or {}
    if entry.get("ngay") == ngay.isoformat():
        return True
    if entry.get("cho_ngay") == ngay.isoformat() and entry.get("cho_den", 0) > time.time():
        return True
    if rieng:
        return False   # bộ nhắc env chỉ gửi danh sách cả nhóm — không thay lượt riêng
    # Tương thích sổ env cũ chỉ có ngày, áp riêng Base cấu hình.
    try:
        mac = cau_hinh()
        return (so.get("ngay") == ngay.isoformat() and so.get("ket_qua") == "da_gui"
                and _khoa_base(mac) == _khoa_base(d))
    except ValueError:
        return False


def ghi_nhac(chat: str, d: dict, ngay: datetime.date, rieng: str = "") -> None:
    so = _doc_so().get(chat) or {}
    # Giữ cả chỗ ĐANG GIỮ hôm nay của khoá khác (lịch cả nhóm và lịch "việc của tôi" cùng
    # nhóm có thể đang chờ /reply cùng lúc) — xoá nó là mở cửa cho gửi trùng.
    hom = ngay.isoformat()
    bases = {k: v for k, v in (so.get("bases") or {}).items()
             if v.get("ngay") == hom or v.get("cho_ngay") == hom}
    bases[_khoa_base(d, rieng)] = {"ngay": hom}
    _cap_nhat_so(chat, bases=bases)


def lenh_tiendo(text: str, *, kenh: dict | None = None, chat_id: str = "",
                sender_open_id: str | None = None) -> str:
    """Đường cứng: quyền theo người hỏi/người đặt lịch, không model, không ghi Base."""
    k = kenh or {}
    lich = k.get("scheduled") is True
    asker = str(k.get("scheduled_by") or "") if lich else (sender_open_id or "")
    if lich and not re.fullmatch(r"ou_[A-Za-z0-9]+", asker):
        return "Lịch chưa có người đặt — tạo lại lịch trên console."
    try:
        nguon, opts = tach_tuy_chon(text)
        # `cua_toi`: người lọc LUÔN là người hỏi (người gửi / người đặt lịch) — không có tham
        # số nào chọn người khác. Thiếu danh tính thì từ chối TRƯỚC khi đọc Base.
        cua_toi = opts.get("cua_toi") == "co"
        if cua_toi and not _la_open_id(asker):
            return LOI_KHONG_RO_NGUOI
        try:
            mac = cau_hinh()
        except ValueError:
            mac = None
        if not nguon and not mac:
            return ('Dùng /tiendo <link Base?table=tbl…> [cot_han="Ngày giao"] [tag=khong] '
                    '[cua_toi=co].')
        # Cùng cửa doc_bang; lệnh chạy trước audit nên truyền chính danh tường minh.
        # Lượt theo lịch: mang phép kiểm Platform (bằng token Lark của người đặt) vào cửa
        # quyền — cửa tự đối chiếu bảng/người/độ mới, không khớp thì như không có.
        cm = BT.ChungMinhLich.tu_payload(k.get("nguon_da_kiem"), asker) if lich else None
        loi_lich = str(k.get("nguon_loi") or "") if lich else ""
        d, loi = _dich_tu_nguon(nguon or mac["url"], mac, nguoi_hoi=asker,
                                chung_minh=cm, loi_lich=loi_lich)
        if not d:
            return loi + _goi_y_lich(loi)
        if not mac or _khoa_base(d) != _khoa_base(mac):
            d["ten"] = ten_base(d)
        if not mac or _khoa_base(d) != _khoa_base(mac):
            d["ten"] = ten_base(d)
        cot, rows = doc_theo_cot(d, {**{key[4:]: v for key, v in opts.items() if key.startswith("cot_")},
                                    **({"xong": opts["xong"]} if "xong" in opts else {})},
                                mac_dinh=not nguon)
        ngay = hom_nay_vn()
        ket = loc_viec(rows, ngay, opts["so_ngay"], cot=cot,
                       qua_han_toi_da_ngay=opts["qua_han_toi_da"],
                       chi_cua=asker if cua_toi else "")
        tin = soan_tin(ket, ngay, d,
                       gan_the=lich and not cua_toi and opts.get("tag", "co") == "co",
                       nhac=lich, cot=cot, so_ngay=opts["so_ngay"], cua_toi=cua_toi)
        if not tin:
            tin = (f"✅ {'Bạn không có' if cua_toi else 'Không có'} việc trễ trong "
                   f"{opts['qua_han_toi_da']} ngày gần đây hay sắp tới hạn "
                   f"trong {opts['so_ngay']} ngày tới. "
                   f"{len(ket['qua_han_lau'])} việc quá hạn lâu; {len(ket['thieu'])} việc thiếu "
                   f"hạn{'' if cua_toi else '/PIC'}. Base: {d['url']}")
        if lich:
            parts = chat_id.split(":", 2)
            chat = parts[2] if len(parts) == 3 and parts[0] == "lark" else chat_id
            if not re.fullmatch(r"oc_[A-Za-z0-9]+", chat):
                return "Lịch cần chạy trong nhóm Lark đã chọn trên console."
            rieng = asker if cua_toi else ""
            with _KHOA:
                if da_nhac(chat, d, ngay, rieng):
                    return ("Hôm nay đã gửi hoặc đang gửi danh sách việc của bạn trên Base này."
                            if rieng else
                            "Nhóm đã nhận hoặc đang gửi nhắc tiến độ của Base này hôm nay.")
                # Giữ chỗ dưới cùng khoá với env, hết hạn sau 15 phút nếu bot chết.
                # Không coi là ĐÃ GỬI cho tới khi /reply được Platform xác nhận.
                so = _doc_so().get(chat) or {}
                bases = dict(so.get("bases") or {})
                bases[_khoa_base(d, rieng)] = {"cho_ngay": ngay.isoformat(),
                                               "cho_den": time.time() + 900}
                _cap_nhat_so(chat, bases=bases)
                if kenh is not None:
                    kenh["tien_do_gui"] = (chat, d, ngay, rieng)
        return tin
    except (ValueError, CauTrucLoi) as e:
        return _sach(str(e))
    except Exception as e:
        return BT.loi_doc("Base", e)


def xac_nhan_gui(kenh: dict | None) -> None:
    entry = (kenh or {}).get("tien_do_gui")
    if entry:
        with _KHOA:
            ghi_nhac(*entry)


def huy_cho_gui(kenh: dict | None) -> None:
    """Gửi thất bại hẳn: giải phóng lượt để env thử lại."""
    entry = (kenh or {}).get("tien_do_gui")
    if entry:
        chat, d, _ngay, *con = entry
        khoa = _khoa_base(d, con[0] if con else "")
        with _KHOA:
            so = _doc_so().get(chat) or {}
            bases = dict(so.get("bases") or {})
            cu = bases.get(khoa) or {}
            if not cu.get("ngay"):
                bases.pop(khoa, None)
                _cap_nhat_so(chat, bases=bases)


def ten_base(d: dict) -> str:
    """Chỉ GET tên Base, sau cửa quyền. Không có quyền API tên thì dùng nhãn chung."""
    app = d["app_token"]
    if not re.fullmatch(r"[A-Za-z0-9]+", app):
        return "Base đã dẫn"
    try:
        data = lark.call("GET", f"/open-apis/bitable/v1/apps/{app}").get("data") or {}
        return _sach((data.get("app") or {}).get("name") or "Base đã dẫn")[:_TRAN_TEN_BASE]
    except Exception:
        return "Base đã dẫn"
