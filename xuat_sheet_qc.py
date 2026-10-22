"""Bộ nghe XUẤT LARK SHEET quảng cáo (20/10/2026) — chạy lâu dài dưới user `mark`
(`deploy/lang-nghe/qc-sheet-nghe.service`, venv + `.env` của Mark, Restart=always).

Chủ dự án 20/10/2026: trang Quảng cáo (chỉ quản trị viên) có mục "Tạo Lark Sheet" — xuất số theo
ĐÚNG bộ lọc trang (bên, nền tảng, tài khoản, từ–đến) thành MỘT Lark Sheet, tiêu đề ghi TikTok Ads
(Meta khi lọc Meta — cùng bảng qc_*, cùng mã), ba tab:
  (a) Theo ngày × tài khoản  (qc_tk_ngay, mỗi tài khoản mỗi ngày một dòng + dòng tổng theo tiền tệ)
  (b) Theo chiến dịch        (tổng cả kỳ, lọc + xếp như bảng trang)
  (c) Theo quảng cáo         (tổng cả kỳ, lọc + xếp như bảng trang, cắt ở `kho_sheet_qc.TRAN_DONG`)
22/10/2026 (chủ dự án): nút "Xuất Lark Sheet theo bộ lọc này" nằm trong mục "Chiến dịch và quảng cáo";
yêu cầu mang thêm nhiều tài khoản (tk_ds) + bộ lọc bảng (tim, cd, sap, chieu). Tab (b)/(c) lọc / xếp
bằng CHÍNH SQL của bảng trang (`kho_qc.sql_bang` qua `kho_sheet_qc.doc_tong`), mọi dòng khớp (không chỉ
một trang) tới trần; tab (a) chỉ theo tài khoản + ngày; Tổng quan liệt kê bộ lọc đã dùng.
Có chi (chỉ quản trị viên bấm được) + chỉ số suy ra như trang (`quang_cao.hieu_qua`: CPM, CPC, CTR,
chi / 1.000 view, chi / follow, chi / kết quả; ROAS Shop + Doanh thu Shop tạm ẩn từ 22/10/2026 —
`quang_cao.HIEN_DOANH_THU`).

Vì sao ở phía Mark: dashboard không giữ app Lark tạo được Sheet (và không được có). Dashboard chỉ thêm
dòng `yeu_cau_sheet_qc`; trigger gọi pg_notify('qc_sheet') → tiến trình này LISTEN, nhận gần như ngay;
lúc khởi động và mỗi `CHO_GIAY` giây vẫn quét dòng chờ (không mất yêu cầu khi đang dừng).

Không tin đầu kia: mỗi yêu cầu kiểm lại người bấm CÒN là quản trị viên (`kho.quyen_cua`, role mark
đọc được) và tự tính lại phạm vi tài khoản bằng đúng luật trang (`quang_cao.tk_xuat`) — dòng chỉ mang
bộ lọc (danh sách tài khoản đã chọn cũng chỉ là bộ lọc — giao lại với phạm vi tính lại).

22/10/2026 (chủ dự án: "khi hỏi Mark thì Mark vẫn xuất Sheet được"): dòng `nguon = 'mark'` do tool
`xuat_sheet_qc` của Mark thêm (`sheet_qc_tool.py`) cho CHÍNH người hỏi. Người đó không cần là quản trị
viên — chỉ cần còn quyền ở bên. Hai luật CỨNG ở đây (không tin bên thêm dòng, kể cả Mark):
  • Phạm vi: tài khoản tính lại từ quyền CSDL của nguoi_hoi LÚC DỰNG (`tk_xuat`: chỉ bên người đó
    đọc được; tài khoản chưa gán bên / "mọi bên" chỉ quản trị viên) — mã ngoài phạm vi bị bỏ (Tổng
    quan + tin nhắn nói số đã bỏ), không còn mã nào → lỗi.
  • Tiền: `co_tien` = người đó xem được tiền của MỌI tài khoản trong Sheet (`quang_cao.xem_tien`,
    cùng luật trang / Mark; quản trị viên = có). Không → Sheet KHÔNG có cột / giá trị tiền nào (chi,
    CPM, CPC, chi / …, doanh thu — mọi khoá `quang_cao.la_tien`), không xếp theo tiền, dòng TỔNG gộp
    mọi tiền tệ (chỉ số đếm). Không xác định được quyền → coi như không có tiền.
Dòng web giữ nguyên luật cũ (chỉ quản trị viên, đủ cột tiền).

Đường Sheet giống hệt `chi_so_ads` (meta_ads_tool, số quảng cáo): `trinh_bay_sheet.xuat` — tạo →
khoá riêng tư TRƯỚC khi ghi số (`TB.khoa_rieng_tu`: đóng chia sẻ link / ngoài tổ chức, kiểm lại) →
ghi → trang trí → Tổng quan → cấp quyền XEM cho người yêu cầu (hỏng thì ném — không bao giờ báo
"xong" cho Sheet người đó không mở được). File do bot sở hữu, không thư mục (như mọi Sheet của Mark).
Người nhận: union_id Lark của người bấm TRƯỚC (dashboard ghi lúc đăng nhập — `kho.union_id_cua`;
chung mọi app của cùng nhà phát triển nên app Mark dùng được; open_id của app dashboard thì khác app
Mark). 21/10/2026 chạy thật: email đăng nhập không trùng email Lark → member_type=email / receive_id
email bị từ chối, danh bạ app Mark cũng không tra ra; union_id thì chia quyền + nhắn đều được. Chưa
có union_id thì email, rồi open_id tra danh bạ. Xong thì nhắn link (lỗi thì nhắn lý do) cho người yêu
cầu — nhắn hỏng không làm hỏng yêu cầu.

Chạy tay (trên VPS, user mark): `python -m xuat_sheet_qc` (nghe mãi) hoặc `--mot-lan` (xử lý hàng
chờ một lần rồi thoát).
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

from dashboard import kho_sheet_qc as KS
from dashboard import phan_quyen as PQ
from dashboard import quang_cao as QC

CHO_GIAY = 60          # không có thông báo: vẫn tỉnh dậy mỗi 60 giây (dọn + quét dòng chờ)
NGHI_LOI = 10          # mất kết nối Postgres / kho chưa có bảng: nghỉ rồi nối lại
TRANG = "https://social.hapas.vn/quang-cao"

#: Cột số của Sheet: (khoá, tiêu đề, kiểu trinh_bay_sheet). Tiền theo tiền tệ TỪNG dòng (cột "Tiền
#: tệ"); CTR đã ×100 (tiêu đề có %). Reach chỉ ở tab theo ngày (tổng reach nhiều ngày đếm trùng người).
_COT_SO = (
    ("chi", "Chi", "tien"), ("hien_thi", "Hiển thị", "so_nguyen"), ("reach", "Reach", "so_nguyen"),
    ("click", "Click", "so_nguyen"), ("ctr", "CTR (%)", "phan_tram_100"),
    ("cpm", "CPM", "tien"), ("cpc", "CPC", "tien"),
    ("view_video", "View video", "so_nguyen"), ("view_hai_giay", "View 2 giây", "so_nguyen"),
    ("view_sau_giay", "View 6 giây", "so_nguyen"), ("view_het", "View hết", "so_nguyen"),
    ("engaged_view", "Engaged view", "so_nguyen"),
    ("chi_tren_1000_view", "Chi / 1.000 view", "tien"),
    ("thich", "Thích", "so_nguyen"), ("binh_luan", "Bình luận", "so_nguyen"),
    ("chia_se", "Chia sẻ", "so_nguyen"), ("tuong_tac", "Tương tác", "so_nguyen"),
    ("follow", "Follow", "so_nguyen"), ("chi_moi_follow", "Chi / follow", "tien"),
    ("vao_ho_so", "Vào hồ sơ", "so_nguyen"), ("ket_qua", "Kết quả", "so_nguyen"),
    ("chi_moi_ket_qua", "Chi / kết quả", "tien"), ("chuyen_doi", "Chuyển đổi", "so_nguyen"),
    ("mua_shop", "Mua Shop", "so_nguyen"), ("gia_tri_mua_shop", "Doanh thu Shop", "tien"),
    ("roas_shop", "ROAS Shop", "ti_le"),
)
# 22/10/2026 (chủ dự án): Doanh thu Shop / ROAS tạm ẩn — nền tảng đo khác cách công ty tự tính.
if not QC.HIEN_DOANH_THU:
    _COT_SO = tuple(c for c in _COT_SO if not QC.la_doanh_thu(c[0]))
TAB_NGAY, TAB_CHIEN_DICH, TAB_QUANG_CAO = "Theo ngày × tài khoản", "Theo chiến dịch", "Theo quảng cáo"


class LoiYeuCau(Exception):
    """Yêu cầu không làm được (quyền, phạm vi) — câu đưa nguyên cho người yêu cầu."""


def _gon(e: Exception) -> str:
    try:
        import apify_tool as A
        return A._che_token(f"{type(e).__name__}: {e}")[:500]
    except Exception:  # noqa: BLE001
        return type(e).__name__


def _ngay(x) -> datetime.date:
    return x if isinstance(x, datetime.date) else datetime.date.fromisoformat(str(x)[:10])


# ───────────────────────────── dựng bảng (thuần) ─────────────────────────────
def _cot(reach: bool, tien: bool = True) -> list:
    """Cột số của tab: reach chỉ tab theo ngày; `tien` False → bỏ MỌI cột tiền (`QC.la_tien`)."""
    return [c for c in _COT_SO if (reach or c[0] != "reach") and (tien or not QC.la_tien(c[0]))]


def _cot_so(reach: bool, tien: bool = True) -> list:
    import trinh_bay_sheet as TB
    return [TB.Cot(t, k, cot_tien_te="Tiền tệ") if k == "tien" else TB.Cot(t, k)
            for m, t, k in _cot(reach, tien)]


def _so(r: dict, reach: bool, tien: bool = True) -> list:
    """Các ô số của một dòng tổng (cột kiểu riêng + chỉ số suy ra tính lại từ chính dòng đó)."""
    x = {**r, **QC.hieu_qua(r)}
    return [x.get(m) if x.get(m) is not None else "" for m, _, _ in _cot(reach, tien)]


def loc_yeu_cau(yc: dict, tien: bool = True) -> dict:
    """Bộ lọc bảng của yêu cầu (cột tim / cd / sap / chieu, 22/10/2026) qua CHÍNH
    `quang_cao.loc_bang` của trang (`tien` = người yêu cầu xem được tiền → xếp theo tiền được; không
    thì xếp tiền về hiển thị như trang). Dòng cũ (cột NULL) = chi giảm dần, không lọc — như trước."""
    return QC.loc_bang({k: yc.get(k) for k in ("tim", "cd", "sap", "chieu")}, tien)


def tu_mark(yc: dict) -> bool:
    """Dòng do tool Mark thêm (cột nguon, 22/10/2026). Thiếu cột / dòng cũ = web."""
    return str(yc.get("nguon") or "web") == "mark"


def co_tien(q: dict | None, tk: list[dict]) -> bool:
    """LUẬT CỨNG (22/10/2026): Sheet có cột tiền chỉ khi người yêu cầu xem được tiền của MỌI tài
    khoản trong Sheet — `quang_cao.xem_tien` theo bên của từng tài khoản (chưa gán bên: chỉ quản trị
    viên). Không xác định được → False (bỏ tiền)."""
    try:
        return bool(tk) and all(QC.xem_tien(q, t.get("don_vi") or None) for t in tk)
    except Exception:  # noqa: BLE001 — quyền lạ / thiếu: đóng
        return False


def bo_tien_tong(tong: dict[str, dict]) -> dict[str, dict]:
    """Tổng theo tiền tệ → MỘT tổng (khoá "") chỉ còn số đếm: không tiền thì tách theo tiền tệ vô
    nghĩa, và không bao giờ mang khoá tiền."""
    if not tong:
        return {}
    gop: dict = {}
    for t in tong.values():
        for k, v in (t or {}).items():
            if v is None or QC.la_tien(k):
                continue
            gop[k] = gop.get(k, 0) + v
    return {"": gop}


def bo_tien_dong(d: dict) -> dict:
    """{"rows", "tong"} → bỏ mọi khoá tiền khỏi từng dòng (`QC.loc_tien`)."""
    return {**d, "rows": [QC.loc_tien(r, False) for r in d.get("rows") or []]}


def cach_xep(lb: dict) -> str:
    return f"xếp theo {QC.SAP_BANG.get(lb['sap'], lb['sap'])} " + (
        "thấp → cao" if lb["chieu"] == "tang" else "cao → thấp")


def _giu(lb: dict) -> str:
    """Câu "giữ dòng nào" khi tab bị cắt ở trần (theo đúng cách xếp)."""
    if lb["sap"] == "chi" and lb["chieu"] == "giam":
        return "chi nhiều nhất trước"
    return cach_xep(lb) + ", giữ các dòng đầu"


def so_bo(yc: dict, tk: list[dict]) -> int:
    """Số tài khoản đã chọn trong yêu cầu nhưng KHÔNG còn trong phạm vi lúc dựng (bị bỏ)."""
    chon = yc.get("tk_ds") or ([yc["tk"]] if yc.get("tk") else [])
    co = {str(t["advertiser_id"]) for t in tk}
    return len({str(x) for x in chon} - co)


def mo_ta_loc(yc: dict, lb: dict, tk: list[dict]) -> list[str]:
    """Các dòng "Bộ lọc" của tab Tổng quan — đúng những gì Sheet đã lọc (đầu trang + bảng)."""
    chon = yc.get("tk_ds") or ([yc["tk"]] if yc.get("tk") else [])
    ten = ", ".join(t.get("ten") or t["advertiser_id"] for t in tk[:6]) + (
        f" và {len(tk) - 6} tài khoản khác" if len(tk) > 6 else "")
    bo = so_bo(yc, tk)
    ra = ["Bộ lọc tài khoản: " + (f"{len(tk)} tài khoản đã chọn ({ten})" if chon
                                  else f"mọi tài khoản của phạm vi ({len(tk)})")
          + (f"; bỏ {bo} tài khoản không thuộc phạm vi người yêu cầu được xem" if bo else "")]
    ra.append("Bộ lọc bảng (tab chiến dịch + quảng cáo): "
              + "; ".join([*([f"tìm theo tên “{lb['tim']}”"] if lb["tim"] else []),
                           *([f"chỉ chiến dịch mã {lb['cd']}"] if lb["cd"] else []),
                           cach_xep(lb)])
              + ". Tab theo ngày × tài khoản chỉ theo tài khoản + khoảng ngày.")
    return ra


def dung_bang(tk: list[dict], ngay: dict, cd: dict, qc: dict, tong: dict[str, dict],
              ten_nen=QC.TEN_NEN_TANG_QC, lb: dict | None = None, tien: bool = True) -> list:
    """Ba TB.Bang (tab a, b, c) từ dòng kho. `tk` = tài khoản trong phạm vi (cac_tk), `ngay` / `cd` /
    `qc` = {"rows", "tong"} của `kho_sheet_qc.doc_theo_ngay` / `doc_tong`; `tong` = tổng TOÀN phạm vi
    theo tiền tệ (`doc_tong_tien_te`) — dòng TỔNG không cộng từ dòng có thể đã cắt. `lb` = bộ lọc
    bảng (`loc_yeu_cau`) — chỉ để ghi mô tả tab đúng cách lọc / xếp. `tien` False (22/10/2026): không
    cột tiền, không cột Tiền tệ, `tong` đã gộp (`bo_tien_tong`); kiểm lại lần cuối — còn cột tiền
    nào là ném (không bao giờ ghi)."""
    import trinh_bay_sheet as TB
    lb = lb or loc_yeu_cau({}, tien)
    loc = (f", tên khớp “{lb['tim']}”" if lb["tim"] else "") + (
        f", chiến dịch {lb['cd']}" if lb["cd"] else "")
    thong_tin = {str(t["advertiser_id"]): t for t in tk}

    def tk_cua(r):
        t = thong_tin.get(str(r.get("advertiser_id"))) or {}
        return (ten_nen.get(QC.nen_tang_tk(t), "") if t else "", t.get("ten") or "",
                str(r.get("advertiser_id") or ""), t.get("tien_te") or "VND")

    def tien_te(r):
        return [tk_cua(r)[3]] if tien else []

    dau_tk = [TB.Cot("Nền tảng"), TB.Cot("Tài khoản"), TB.Cot("Mã TK", "ma")]
    cot_tt = [TB.Cot("Tiền tệ")] if tien else []
    # (a) theo ngày × tài khoản
    rows_a = [[_ngay(r["ngay"]), *tk_cua(r)[:3], *tien_te(r), *_so(r, True, tien)]
              for r in ngay["rows"]]
    tong_a = [["", f"TỔNG {tt} (cả kỳ)" if tt else "TỔNG (cả kỳ)", "", "",
               *([tt] if tien else []), *_so(t, True, tien)] for tt, t in tong.items()]
    a = TB.Bang(TAB_NGAY, [TB.Cot("Ngày", "ngay"), *dau_tk, *cot_tt, *_cot_so(True, tien)],
                rows_a, dong_tong=tong_a, gap_duoc=False, ten_tab=TAB_NGAY,
                mo_ta="Mỗi tài khoản mỗi ngày một dòng (ngày theo múi giờ tài khoản); dòng TỔNG "
                      + ("theo tiền tệ" if tien else "cả phạm vi (không có cột tiền)"),
                loc_san="Mã TK" if len(thong_tin) > 1 else None, loc_san_ten="Tài khoản")
    # (b) theo chiến dịch
    rows_b = [[*tk_cua(r)[:3], str(r.get("campaign_id") or ""), r.get("ten") or "",
               QC.TEN_MUC_TIEU.get(r.get("muc_tieu") or "", r.get("muc_tieu") or ""),
               r.get("so_ngay") or 0, *tien_te(r), *_so(r, False, tien)] for r in cd["rows"]]
    b = TB.Bang(TAB_CHIEN_DICH, [*dau_tk, TB.Cot("Mã chiến dịch", "ma"), TB.Cot("Tên chiến dịch"),
                                 TB.Cot("Mục tiêu"), TB.Cot("Ngày có số", "so_nguyen"),
                                 *cot_tt, *_cot_so(False, tien)],
                rows_b, gap_duoc=False, ten_tab=TAB_CHIEN_DICH,
                mo_ta=f"Tổng cả kỳ của từng chiến dịch{loc}, {cach_xep(lb)}")
    # (c) theo quảng cáo
    rows_c = [[*tk_cua(r)[:3], str(r.get("ad_id") or ""), r.get("ten_ad") or "",
               r.get("noi_dung") or "", r.get("ten_campaign") or "", r.get("ten_nhom") or "",
               r.get("so_ngay") or 0, *tien_te(r), *_so(r, False, tien)] for r in qc["rows"]]
    c = TB.Bang(TAB_QUANG_CAO, [*dau_tk, TB.Cot("Mã quảng cáo", "ma"), TB.Cot("Tên quảng cáo"),
                                TB.Cot("Nội dung", "chu_dai"), TB.Cot("Chiến dịch"),
                                TB.Cot("Nhóm quảng cáo"), TB.Cot("Ngày có số", "so_nguyen"),
                                *cot_tt, *_cot_so(False, tien)],
                rows_c, gap_duoc=False, ten_tab=TAB_QUANG_CAO,
                mo_ta=f"Tổng cả kỳ của từng quảng cáo{loc}, {cach_xep(lb)}"
                      + (f" — {len(rows_c):,}/{qc['tong']:,} quảng cáo đầu tiên".replace(",", ".")
                         if qc["tong"] > len(rows_c) else ""))
    if not tien and any(x.kieu == "tien" or x.cot_tien_te for bg in (a, b, c) for x in bg.cot):
        raise ValueError("Sheet không có quyền tiền vẫn còn cột tiền — không ghi.")
    return [a, b, c]


def ten_nen_tieu_de(nen_tang: str, tk: list[dict]) -> str:
    co = [n for n in QC.NEN_TANG_QC if any(QC.nen_tang_tk(t) == n for t in tk)]
    if nen_tang in QC.NEN_TANG_QC:
        co = [nen_tang]
    return " + ".join(QC.TEN_NEN_TANG_QC[n] for n in co) or "TikTok"


def tieu_de(yc: dict, tk: list[dict], ten_ben: str) -> str:
    tu, den = _ngay(yc["tu"]), _ngay(yc["den"])
    pham_vi = ten_ben
    chon = yc.get("tk_ds") or ([yc["tk"]] if yc.get("tk") else [])
    if chon and len(tk) == 1:
        pham_vi += f" · {tk[0].get('ten') or tk[0]['advertiser_id']}"
    elif chon and tk:
        pham_vi += f" · {len(tk)} tài khoản"
    return f"{ten_nen_tieu_de(yc['nen_tang'], tk)} Ads · {pham_vi} · {tu:%d/%m}–{den:%d/%m/%Y}"


def dung_tong_quan(yc: dict, tk: list[dict], ten_ben: str, tde: str, ngay: dict, cd: dict,
                   qc: dict, tong: dict[str, dict], lb: dict | None = None, tien: bool = True):
    """`tong` = tổng TOÀN phạm vi theo tiền tệ (`doc_tong_tien_te`), không từ dòng đã cắt. Ghi chú
    đầu liệt kê bộ lọc đã dùng (`mo_ta_loc`). `tien` False: không số tiền nào, nói rõ vì sao."""
    import trinh_bay_sheet as TB
    lb = lb or loc_yeu_cau(yc, tien)
    tu, den = _ngay(yc["tu"]), _ngay(yc["den"])
    co_loc = bool(lb["tim"] or lb["cd"])
    so_lieu = [TB.SoLieu("Tài khoản trong phạm vi", len(tk), "so_nguyen"),
               TB.SoLieu("Chiến dịch khớp bộ lọc" if co_loc else "Chiến dịch có phân phối",
                         cd["tong"], "so_nguyen"),
               TB.SoLieu("Quảng cáo khớp bộ lọc" if co_loc else "Quảng cáo có phân phối",
                         qc["tong"], "so_nguyen")]
    nhieu = len(tong) > 1
    for tt, t in tong.items():
        h = QC.hieu_qua(t)
        k = f"Tài khoản tiền {tt}" if nhieu else ""
        so_lieu += ([TB.SoLieu("Chi tiêu", t.get("chi"), "tien", tt, khoi=k)] if tien else []) + [
            TB.SoLieu("Hiển thị", t.get("hien_thi"), "so_nguyen", khoi=k),
            *([TB.SoLieu("CPM", h["cpm"], "tien", tt, "chi ÷ hiển thị × 1.000", khoi=k)]
              if tien else []),
            TB.SoLieu("CTR (%)", h["ctr"], "phan_tram_100", ghi_chu="click ÷ hiển thị", khoi=k),
            TB.SoLieu("View video", t.get("view_video"), "so_nguyen", khoi=k),
            TB.SoLieu("Follow", t.get("follow"), "so_nguyen", khoi=k),
            *([TB.SoLieu("Chi / follow", h["chi_moi_follow"], "tien", tt, khoi=k)] if tien else [])]
    if not tien and any(x.kieu == "tien" for x in so_lieu):
        raise ValueError("Tổng quan không có quyền tiền vẫn còn số tiền — không ghi.")
    tao_boi = ("Tạo theo yêu cầu gửi Mark trong chat riêng trên Lark." if tu_mark(yc) else
               f"Tạo bằng nút “Xuất Lark Sheet theo bộ lọc này” ở {TRANG} (chỉ quản trị viên).")
    tien_ghi = ([
        "Ngày theo múi giờ tài khoản quảng cáo. Tiền theo tiền tệ từng tài khoản (cột Tiền tệ), "
        "chưa VAT.",
        "CPM, CPC, CTR, chi / 1.000 view, chi / follow, chi / kết quả"
        + (", ROAS" if QC.HIEN_DOANH_THU else "") + " tính lại từ TỔNG của "
        "từng dòng (không trung bình tỉ lệ). Ô trống = không có số / mẫu số bằng 0."] if tien else [
        "Sheet KHÔNG có cột tiền (chi tiêu, CPM, CPC, chi / follow, chi / kết quả…): người yêu cầu "
        "không có quyền xem tiền của phạm vi này. Dòng TỔNG gộp mọi tài khoản (chỉ số đếm).",
        "Ngày theo múi giờ tài khoản quảng cáo. CTR tính lại từ TỔNG của từng dòng (không trung bình "
        "tỉ lệ). Ô trống = không có số / mẫu số bằng 0."])
    ghi_chu = [
        *mo_ta_loc(yc, lb, tk),
        "Số liệu chính + dòng TỔNG là tổng cả phạm vi tài khoản + khoảng ngày (bộ lọc bảng không áp "
        "vào tổng — như số tổng của trang).",
        "Số đọc từ kho quảng cáo của dashboard (đồng bộ TikTok mỗi sáng 06:30, Meta 06:45, đọc lại "
        "7 ngày gần nhất) — giống trang Quảng cáo cùng bộ lọc.",
        *tien_ghi,
        "Reach chỉ ở tab theo ngày: cộng reach nhiều ngày đếm trùng người.",
        "Chỉ chiến dịch / quảng cáo CÓ phân phối trong kỳ (có hiển thị hoặc chi).",
        "Sheet riêng tư: chia sẻ link đóng, chỉ người yêu cầu được XEM. " + tao_boi,
    ]
    for ten, d, tran, giu in ((TAB_NGAY, ngay, KS.TRAN_DONG["ngay"], "giữ các ngày gần nhất"),
                              (TAB_CHIEN_DICH, cd, KS.TRAN_DONG["chien_dich"], _giu(lb)),
                              (TAB_QUANG_CAO, qc, KS.TRAN_DONG["quang_cao"], _giu(lb))):
        if d["tong"] > len(d["rows"]):
            ghi_chu.append(f"ĐÃ CẮT tab {ten}: {len(d['rows']):,} / {d['tong']:,} dòng (trần "
                           f"{tran:,} dòng — {giu}). Số liệu chính và dòng TỔNG vẫn là tổng ĐỦ cả "
                           "kỳ. Muốn đủ dòng: thu hẹp ngày / tài khoản rồi tạo lại.".replace(",", "."))
    ten_tk = ", ".join(t.get("ten") or t["advertiser_id"] for t in tk[:6]) + (
        f" và {len(tk) - 6} tài khoản khác" if len(tk) > 6 else "")
    return TB.TongQuan(
        tieu_de=tde,
        nguon="Dashboard social.hapas.vn · kho quảng cáo (TikTok for Business, Meta Marketing API)",
        thoi_gian=f"{tu:%d/%m/%Y} – {den:%d/%m/%Y} ({(den - tu).days + 1} ngày)",
        pham_vi=f"{ten_ben} · {ten_nen_tieu_de(yc['nen_tang'], tk)} · {len(tk)} tài khoản ({ten_tk})",
        nguoi_yeu_cau=str(yc.get("nguoi_hoi") or ""), so_lieu=so_lieu, ghi_chu=ghi_chu)


# ───────────────────────────── Lark: quyền + tin nhắn ─────────────────────────────
def tra_open_id(lark, email: str) -> str | None:
    """Email → open_id trong app của Mark (danh bạ cấp tenant). Hỏng → None."""
    try:
        r = lark.call("POST", "/open-apis/contact/v3/users/batch_get_id",
                      query={"user_id_type": "open_id"}, body={"emails": [email]})
        for u in ((r or {}).get("data") or {}).get("user_list") or []:
            if u.get("user_id"):
                return str(u["user_id"])
    except Exception as e:  # noqa: BLE001
        print(f"[xuat_sheet_qc] tra open_id lỗi: {_gon(e)[:200]}", flush=True)
    return None


CAU_HET_QT = "Chưa chia sẻ Sheet: bạn không còn là quản trị viên."
CAU_HET_PHAM_VI = "Chưa chia sẻ Sheet: quyền xem của bạn vừa đổi — hỏi Mark xuất lại."


def cap_quyen_xem(lark, tok: str, email: str, con_quyen=None, union_id: str | None = None,
                  cau_het: str = CAU_HET_QT) -> None:
    """Người yêu cầu chỉ cần XEM số (như `meta_ads_tool._grant_view`); theo union_id (nếu có), rồi
    email, rồi open_id. `con_quyen()`: kiểm lại NGAY trước khi thêm cộng tác viên (bị bỏ quản trị /
    bỏ bên / mất quyền tiền giữa lượt → không bao giờ chia sẻ). Không cấp được → ném (KHÔNG báo xong)."""
    if con_quyen is not None and not con_quyen():
        raise ValueError(cau_het)
    duong = f"/open-apis/drive/v1/permissions/{tok}/members"
    if union_id:
        try:
            lark.call("POST", duong, query={"type": "sheet"},
                      body={"member_type": "unionid", "member_id": union_id, "perm": "view"})
            return
        except Exception as e:  # noqa: BLE001
            print(f"[xuat_sheet_qc] cấp quyền theo union_id lỗi: {_gon(e)[:200]}", flush=True)
    try:
        lark.call("POST", duong, query={"type": "sheet"},
                  body={"member_type": "email", "member_id": email, "perm": "view"})
        return
    except Exception as e:  # noqa: BLE001
        print(f"[xuat_sheet_qc] cấp quyền theo email lỗi: {_gon(e)[:200]}", flush=True)
    oid = tra_open_id(lark, email)
    if oid:
        try:
            lark.call("POST", duong, query={"type": "sheet"},
                      body={"member_type": "openid", "member_id": oid, "perm": "view"})
            return
        except Exception as e:  # noqa: BLE001
            print(f"[xuat_sheet_qc] cấp quyền theo open_id lỗi: {_gon(e)[:200]}", flush=True)
    raise ValueError("Chưa chia sẻ được Sheet cho bạn (Lark từ chối thêm quyền xem).")


def nhan_tin(lark, email: str, text: str, uuid: str, union_id: str | None = None) -> bool:
    """Nhắn người yêu cầu (theo union_id nếu có, rồi email, rồi open_id). `uuid`: khởi động lại
    giữa chừng không thành hai tin. Hỏng → False (không làm hỏng yêu cầu)."""
    cac = (([("union_id", union_id)] if union_id else []) + [("email", email), ("open_id", None)])
    for loai, ma in cac:
        if loai == "open_id":
            ma = tra_open_id(lark, email)
            if not ma:
                break
        try:
            lark.send_text(loai, ma, text, uuid=uuid)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[xuat_sheet_qc] nhắn theo {loai} lỗi: {_gon(e)[:200]}", flush=True)
    return False


# ───────────────────────────── xử lý một yêu cầu ─────────────────────────────
def quyen_yeu_cau(yc: dict, kho) -> dict:
    """Quyền CSDL của người yêu cầu, đọc LÚC DỰNG. Dòng web: chỉ quản trị viên (như cũ). Dòng Mark
    (22/10/2026): người còn quyền ở ít nhất một bên. Không được → LoiYeuCau."""
    q = PQ.chuan(kho.quyen_cua(yc["nguoi_hoi"]))
    if tu_mark(yc):
        if not PQ.co_quyen(q):
            raise LoiYeuCau("Email của bạn không còn trong danh sách người xem dashboard nên Mark "
                            "không tạo Sheet quảng cáo.")
    elif not PQ.la_quan_tri(q):
        raise LoiYeuCau("Chỉ quản trị viên tạo được Sheet quảng cáo.")
    return q


def pham_vi(yc: dict, kho, kho_qc, q: dict | None = None) -> list[dict]:
    """Kiểm lại quyền + tính lại tài khoản (luật trang, quyền CSDL của nguoi_hoi lúc dựng — tài khoản
    ngoài phạm vi bị bỏ). Không được → LoiYeuCau."""
    q = q if q is not None else quyen_yeu_cau(yc, kho)
    tu, den = _ngay(yc["tu"]), _ngay(yc["den"])
    if tu > den or (den - tu).days >= QC.XUAT_TOI_DA_NGAY:
        raise LoiYeuCau(f"Khoảng ngày phải từ 1 tới {QC.XUAT_TOI_DA_NGAY} ngày.")
    # 22/10/2026: nhiều tài khoản (cột tk_ds); dòng cũ chỉ có cột tk. Mã rơi khỏi phạm vi (bị bỏ bên
    # / bỏ duyệt từ lúc bấm) thì bỏ; không còn mã nào → lỗi như cũ.
    tk = QC.tk_xuat(q, list(kho_qc.cac_tk()), yc["ben"], yc["nen_tang"],
                    yc.get("tk_ds") or yc.get("tk"))
    if not tk:
        raise LoiYeuCau("Phạm vi này không còn tài khoản quảng cáo nào (đổi bên / nền tảng / "
                        "tài khoản rồi tạo lại).")
    return tk


def xu_ly(yc: dict, *, ks=KS, kho=None, kho_qc=None, lark=None, xuat=None, log=print) -> dict:
    """Dựng Sheet cho MỘT yêu cầu đã nhận (dang_tao) rồi kết thúc nó — không bao giờ để kẹt."""
    if kho is None:
        from dashboard import kho
    if kho_qc is None:
        from dashboard import kho_qc
    if lark is None:
        import lark_client as lark
    import trinh_bay_sheet as TB
    xuat = xuat or TB.xuat
    yid, email, moc = int(yc["id"]), str(yc["nguoi_hoi"]), yc.get("bat_dau_luc")
    tde, ket, ghi = None, None, None
    try:
        uid = kho.union_id_cua(email) if hasattr(kho, "union_id_cua") else None
    except Exception:  # noqa: BLE001 — thiếu union_id thì lùi về email / open_id
        uid = None
    mark = tu_mark(yc)
    try:
        q = quyen_yeu_cau(yc, kho)
        tk = pham_vi(yc, kho, kho_qc, q)
        ids = [str(t["advertiser_id"]) for t in tk]
        tien = co_tien(q, tk)                    # luật cứng: quyết ở đây, không tin dòng
        tu, den = _ngay(yc["tu"]), _ngay(yc["den"])
        ben = yc["ben"]
        ten_ben = {**ks.ten_ben(), QC.TAT_CA: "Tất cả bên", QC.CHUA_GAN: "Chưa gán bên"}.get(
            ben, ben.upper())
        lb = loc_yeu_cau(yc, tien)
        ngay = ks.doc_theo_ngay(ids, tu, den)
        if lb["tim"] and not lb["mau"]:
            # Chữ tìm không còn chữ/số Latin nào: không khớp gì (như bảng trang Quảng cáo).
            cd = qc = {"rows": [], "tong": 0}
        else:
            loc = {"sap": lb["sap"], "tang": lb["chieu"] == "tang", "mau": lb["mau"], "cd": lb["cd"]}
            cd = ks.doc_tong("chien_dich", ids, tu, den, **loc)
            qc = ks.doc_tong("quang_cao", ids, tu, den, **loc)
        tong = ks.doc_tong_tien_te(ids, tu, den)
        if not tien:
            ngay, cd, qc = bo_tien_dong(ngay), bo_tien_dong(cd), bo_tien_dong(qc)
            tong = bo_tien_tong(tong)
        tde = tieu_de(yc, tk, ten_ben)

        def con_quyen() -> bool:
            q2 = PQ.chuan(kho.quyen_cua(email))
            if not mark:
                return PQ.la_quan_tri(q2)
            # Dòng Mark: vẫn còn quyền, mọi tài khoản trong Sheet vẫn trong phạm vi, và (Sheet có
            # tiền) vẫn xem được tiền — đổi quyền giữa lượt thì không chia sẻ.
            con = QC.tk_xuat(q2, list(kho_qc.cac_tk()), ben, yc["nen_tang"], ids)
            return (PQ.co_quyen(q2) and {str(t["advertiser_id"]) for t in con} >= set(ids)
                    and (not tien or co_tien(q2, tk)))
        kq = xuat(tde, dung_bang(tk, ngay, cd, qc, tong, lb=lb, tien=tien),
                  dung_tong_quan(yc, tk, ten_ben, tde, ngay, cd, qc, tong, lb, tien=tien),
                  sau_khi_tao=TB.khoa_rieng_tu,
                  cap_quyen=lambda tok: cap_quyen_xem(
                      lark, tok, email, con_quyen, uid, CAU_HET_PHAM_VI if mark else CAU_HET_QT))
        if not KS.link_lark(kq.url):
            raise ValueError("Chưa nhận được link Sheet hợp lệ từ Lark — bấm tạo lại.")
        so_dong = {"ngay": len(ngay["rows"]), "chien_dich": len(cd["rows"]),
                   "quang_cao": len(qc["rows"]), "tong_chien_dich": cd["tong"],
                   "tong_quang_cao": qc["tong"]}
        loi = None if kq.day_du is not False else ("Sheet ghi thiếu — " + kq.cau_kiem)[:300]
        ghi = ks.ket_thuc(yid, "xong", bat_dau_luc=moc, tieu_de=tde, sheet_url=kq.url,
                          so_dong=so_dong, loi=loi)
        ket = {"trang_thai": "xong", "url": kq.url, "so_dong": so_dong, "co_tien": tien}
        bo = so_bo(yc, tk)
        tin = (f"Sheet quảng cáo đã xong: {tde}\n{kq.url}\n"
               f"{so_dong['ngay']} dòng theo ngày · {so_dong['chien_dich']} chiến dịch · "
               f"{so_dong['quang_cao']} quảng cáo"
               + (" (đã cắt — xem tab Tổng quan)" if qc["tong"] > len(qc["rows"])
                  or cd["tong"] > len(cd["rows"]) else "")
               + ". Bạn có quyền xem; link chia sẻ đã đóng."
               + (f" Đã bỏ {bo} tài khoản không thuộc phạm vi bạn được xem." if bo else "")
               + ("" if tien else " Sheet không có cột tiền (bạn không có quyền xem tiền của "
                                  "phạm vi này)."))
    except LoiYeuCau as e:
        ghi = ks.ket_thuc(yid, "loi", bat_dau_luc=moc, tieu_de=tde, loi=str(e))
        ket = {"trang_thai": "loi", "loi": str(e)}
        tin = f"Chưa tạo được Sheet quảng cáo: {e}"
    except Exception as e:  # noqa: BLE001 — luôn kết thúc yêu cầu, rồi báo
        cau = "Lark hoặc kho dữ liệu lỗi khi tạo Sheet — bấm tạo lại sau ít phút."
        if isinstance(e, ValueError) and str(e).startswith("Chưa"):
            cau = str(e)                      # câu của bước riêng tư / cấp quyền
        ghi = ks.ket_thuc(yid, "loi", bat_dau_luc=moc, tieu_de=tde, loi=cau, loi_noi_bo=_gon(e))
        ket = {"trang_thai": "loi", "loi": cau}
        tin = f"Chưa tạo được Sheet quảng cáo{f' ({tde})' if tde else ''}: {cau}"
        log(f"[xuat_sheet_qc] #{yid}: lỗi {_gon(e)[:300]}")
    if ghi is False:
        # Dòng đã bị dọn (quá hạn) / nhận lại giữa lượt: không nhắn — trang đã nói "Quá hạn", người
        # dùng bấm lại; Sheet (nếu đã tạo) vẫn riêng tư của bot.
        log(f"[xuat_sheet_qc] #{yid}: dòng không còn là lượt này (đã dọn / nhận lại) — không nhắn")
        return {**ket, "mo_coi": True}
    if nhan_tin(lark, email, tin, f"sheet-qc-{yid}", uid):
        try:
            ks.da_nhan_tin(yid)
        except Exception as e:  # noqa: BLE001
            log(f"[xuat_sheet_qc] #{yid}: ghi da_nhan_tin lỗi {_gon(e)[:200]}")
    log(f"[xuat_sheet_qc] #{yid}: {ket['trang_thai']}"
        + (f" {ket.get('so_dong')}" if ket.get("so_dong") else f" — {ket.get('loi')}"))
    return ket


def xu_ly_cho(*, ks=KS, log=print, **kw) -> int:
    """Dọn dòng quá hạn rồi xử lý HẾT hàng chờ (tuần tự). -> số yêu cầu đã xử lý."""
    ks.don_dep()
    n = 0
    while True:
        yc = ks.nhan()
        if not yc:
            return n
        xu_ly(yc, ks=ks, log=log, **kw)
        n += 1


# ───────────────────────────── vòng nghe ─────────────────────────────
def mo_ket_noi():
    """Kết nối RIÊNG (autocommit) cho LISTEN, DSN của Mark (peer → role mark)."""
    import psycopg

    from dashboard import kho as K
    return psycopg.connect(K._dsn(), connect_timeout=5, autocommit=True)


def nghe(*, mo=mo_ket_noi, log=print, ngu=time.sleep, vong: int | None = None,
         cho_giay: float = CHO_GIAY, **kw) -> None:
    """Vòng chính. `vong` (bộ thử): số lần thức dậy rồi dừng; None = mãi mãi (systemd giữ). Quét hàng
    chờ NGAY khi nối (khởi động lại không mất yêu cầu), rồi chờ thông báo / `cho_giay`."""
    lan, conn = 0, None
    while vong is None or lan < vong:
        try:
            if conn is None:
                conn = mo()
                conn.execute(f"LISTEN {KS.KENH}")
                log(f"[xuat_sheet_qc] đang nghe kênh {KS.KENH}")
            lan += 1
            if xu_ly_cho(log=log, **kw):
                continue
            for _ in conn.notifies(timeout=cho_giay, stop_after=1):
                pass
        except KeyboardInterrupt:
            break
        except Exception as e:  # noqa: BLE001 — mất kết nối / kho chưa có bảng: nghỉ rồi thử lại
            log(f"[xuat_sheet_qc] {_gon(e)[:300]} — thử lại sau {NGHI_LOI}s")
            _dong(conn)
            conn = None
            lan += 0 if vong is None else 1
            ngu(NGHI_LOI)
    _dong(conn)


def _dong(conn) -> None:
    if conn is not None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 — kết nối đã hỏng
            pass


def chuan_bi() -> None:
    """Môi trường của Mark: `config` nạp `.env` (Lark app + LANG_NGHE_DSN); `tools` của Hermes trên
    sys.path (như brain.py — trinh_bay_sheet → apify_tool cần); module SQL của dashboard đọc bằng DSN
    của MARK (role mark: đọc được cột tiền qc_*, chỉ sửa cột kết quả yeu_cau_sheet_qc)."""
    from config import config
    if os.path.isdir(config.hermes_agent_dir) and config.hermes_agent_dir not in sys.path:
        sys.path.insert(0, config.hermes_agent_dir)
    import lang_nghe_db
    from dashboard import kho as K
    K._dsn = lang_nghe_db._dsn


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m xuat_sheet_qc",
                                description="Nghe yêu cầu xuất Lark Sheet quảng cáo của dashboard.")
    p.add_argument("--mot-lan", action="store_true", help="xử lý hàng chờ một lần rồi thoát")
    a = p.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    chuan_bi()
    if a.mot_lan:
        try:
            print(f"[xuat_sheet_qc] đã xử lý {xu_ly_cho()} yêu cầu", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[xuat_sheet_qc] lỗi: {_gon(e)[:300]}", file=sys.stderr)
            return 1
        return 0
    nghe(log=lambda s: print(s, flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
