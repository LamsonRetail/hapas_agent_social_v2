"""Trang Lịch quét của dashboard: dựng danh sách lịch, tổng quan tháng và bản XEM TRƯỚC của biểu
mẫu (10 lần chạy tới + chi phí so với trần tháng). Thuần Python, không SQL: `app.py` đọc kho rồi
gọi vào đây. Cùng một hàm `xem_truoc` dựng phần xem trước lúc tải trang VÀ trả JSON cho
`/api/lich-quet/xem-truoc` mà `lich_quet.js` gọi khi người dùng sửa ô — số trên trang và số JS
hiện ra không thể lệch nhau (không có bản chép công thức bằng JS).

Chi phí là mức TỐI ĐA nếu mọi lượt dùng hết phần giữ chỗ (như trang Ngân sách): tìm theo từ
khoá + cào bình luận chạy MỖI lượt; nguồn chỉ tốn theo chu kỳ của nguồn, trừ lịch "quét mọi
nguồn" (mỗi lượt quét hết)."""
from __future__ import annotations

import datetime as dt

from dashboard import chi_phi as CP
from dashboard import lich_quet as LQ

#: Trạng thái lượt quét (bảng luot_quet) -> (nhãn, lớp thẻ).
TT_LUOT = {"dang_chay": ("đang chạy", "the--nhan"), "xong": ("xong", "the--tot"),
           "mot_phan": ("một phần", ""), "loi": ("lỗi", "the--loi"), "da_huy": ("đã huỷ", "")}
#: Trạng thái lịch -> lớp thẻ.
LOP_TT = {"tat": "", "ket_thuc": "", "dang_chien_dich": "the--tot", "cho_chien_dich": "the--nhan",
          "nhuong": "lq-the-nhuong", "bat": "the--tot"}
TRE_BAO = dt.timedelta(minutes=3)      # mốc kế đã qua chừng này mà chưa dời: Mark không chạy?


def _usd(x, so_le: int = 2) -> str:
    """Số USD kiểu Việt (giống `app.usd_vn`)."""
    s = f"{float(x or 0):,.{int(so_le)}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _so(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")


def _ket_thuc_thang(bay_gio: dt.datetime) -> dt.datetime:
    return CP._dau_thang_sau(bay_gio) - dt.timedelta(microseconds=1)


# ───────────────────────────── danh sách ─────────────────────────────
def ket_qua_hien(x: dict, quan_ly: bool, loi_chung: str) -> dict | None:
    """Lần xử lý gần nhất của một lịch -> {"nhan", "lop", "chi_tiet", "title", "luc"}. Lượt đã
    mở thì lấy số THẬT từ luot_quet (bài mới, chi phí); bỏ qua thì nói lý do. Người chỉ xem không
    thấy chữ lỗi thô."""
    kq = x.get("ket_qua_cuoi") if isinstance(x.get("ket_qua_cuoi"), dict) else {}
    tt = kq.get("trang_thai")
    if not tt:
        return None
    ra = {"luc": x.get("lan_chay_cuoi"), "title": "", "chi_tiet": "", "lop": ""}
    ma_viec = kq.get("ma_viec")
    if ma_viec and x.get("luot_id") and x.get("luot_ma_viec") == ma_viec:
        nhan, lop = TT_LUOT.get(x.get("luot_trang_thai"), (x.get("luot_trang_thai"), ""))
        ct = f"{_so(x.get('luot_bai_moi'))} bài mới · {_usd(x.get('luot_chi_phi'), 4)} USD"
        loi = x.get("luot_loi") or ""
        return {**ra, "nhan": nhan, "lop": lop, "chi_tiet": ct, "luot_id": x.get("luot_id"),
                "title": (loi if quan_ly else (loi_chung if loi else "")) or ma_viec}
    if tt == "da_tao":
        return {**ra, "nhan": "đã giao việc", "lop": "the--nhan",
                "chi_tiet": f"{ma_viec} — chờ chạy", "title": kq.get("ly_do") or ""}
    if tt in TT_LUOT:
        nhan, lop = TT_LUOT[tt]
        ly = kq.get("ly_do") or ""
        return {**ra, "nhan": nhan, "lop": lop, "chi_tiet": ma_viec or "",
                "title": ly if quan_ly or tt != "loi" else loi_chung}
    if tt == "bo_qua":
        ct = LQ.NHAN_MA_LOI.get(kq.get("ma_loi"), kq.get("ma_loi") or "")
        vc = kq.get("viec_cuoi") if isinstance(kq.get("viec_cuoi"), dict) else None
        if vc:      # việc trước của lịch (chạy chồng lên lượt bị bỏ) đã xong: nói kết quả của nó
            ct += f" · việc {vc.get('ma_viec')}: {TT_LUOT.get(vc.get('trang_thai'), ('?',))[0]}"
        return {**ra, "nhan": "bỏ qua", "lop": "", "chi_tiet": ct,
                "title": kq.get("ly_do") or ""}
    ly = kq.get("ly_do") or ""
    return {**ra, "nhan": "lỗi", "lop": "the--loi",
            "chi_tiet": (ly if quan_ly else loi_chung)[:120], "title": ly if quan_ly else ""}


def _kep_luot(moi_luot: float, chi: dict | None) -> float:
    """USD tối đa một lượt kẹp ở trần việc nền trên console (18/10/2026, `chi["tran_luot"]` từ ảnh
    chụp gói Mark ghi): giữ chỗ cào hết bình luận (60/bài) làm "tối đa" HAPAS 8,6 USD/lượt trong
    khi console chặn mỗi lượt ở 2 USD."""
    tl = (chi or {}).get("tran_luot")
    return round(min(float(moi_luot), float(tl)), 4) if tl is not None else float(moi_luot)


def _trung_vi(chi: dict | None) -> float | None:
    """Trung vị chi THẬT mỗi lượt (`chi_phi.chi_luot_thuc`) khi đủ lượt đo; None khi chưa."""
    t = (chi or {}).get("thuc") or {}
    return float(t["trung_vi"]) if t.get("co") else None


def dong_lich(cac_lich: list[dict], du_an: dict, nguon: list[dict], bay_gio: dt.datetime,
              quan_ly: bool, loi_chung: str, chi: dict | None = None) -> list[dict]:
    """Mỗi lịch + trạng thái, mô tả, mốc kế (chữ), ≈ USD/30 ngày, kết quả gần nhất. `chi`
    (18/10/2026): {"thuc": `chi_phi.chi_luot_thuc`, "tran_luot": trần console mỗi lượt} — mức tối
    đa kẹp ở trần console, `usd_30_thuc` = lượt × trung vị chi thật."""
    bang = CP.bang_cau_hinh(du_an)
    ba_muoi = LQ.dem_luot_du_an(cac_lich, bay_gio, bay_gio + dt.timedelta(days=30))
    tv = _trung_vi(chi)
    ra = []
    for x in cac_lich:
        ma_tt, nhan_tt = LQ.trang_thai(x, cac_lich, bay_gio)
        u = CP.uoc_lich(x, bang, nguon)
        moi = _kep_luot(u["moi_luot"], chi)
        ke = x.get("lan_chay_ke") if x.get("bat") else None
        tre = bool(ke and ke < bay_gio - TRE_BAO)
        luot_30 = ba_muoi.get(x.get("id"), 0)
        ra.append({
            **x, "kieu_ten": LQ.KIEU.get(x.get("kieu"), x.get("kieu")),
            "mo_ta": LQ.mo_ta(x.get("kieu") or "", x.get("cau_hinh") or {}),
            "tt": ma_tt, "tt_nhan": nhan_tt, "tt_lop": LOP_TT.get(ma_tt, ""),
            "ke_chu": LQ.chu_moc(ke, bay_gio) if ke else "—",
            "ke_con": "" if not ke or tre else LQ.chu_con(ke, bay_gio), "tre": tre,
            "luot_30": luot_30, "usd_30": round(luot_30 * moi, 4),
            "moi_luot": moi, "moi_luot_thuc": tv,
            "usd_30_thuc": None if tv is None else round(luot_30 * tv, 4),
            "kq": ket_qua_hien(x, quan_ly, loi_chung),
            "tao_boi": x.get("tao_boi") if quan_ly else None,
            "sua_boi": x.get("sua_boi") if quan_ly else None})
    return ra


def tong_quan(cac_lich: list[dict], du_an: dict, nguon: list[dict], da_tieu: float,
              tran_pf: float | None, bay_gio: dt.datetime, chi: dict | None = None) -> dict:
    """Tháng này theo các lịch đang bật: số lượt còn lại, USD tối đa của lịch (mỗi lượt kẹp ở trần
    console khi biết — `chi`), cả tháng so trần; `tong_thuc` = đã tiêu + lượt còn lại × trung vị
    chi thật (18/10/2026)."""
    bang = CP.bang_cau_hinh(du_an)
    db = CP.du_bao(nguon, da_tieu, float(du_an.get("tran_usd_thang") or 0), tran_pf, bay_gio)
    dl = CP.du_bao_lich(cac_lich, bang, nguon, bay_gio)
    if not dl.get("co_lich"):
        return {"co_lich": False, "tran": db["tran"], "da_tieu": float(da_tieu or 0)}
    theo = dl["theo_lich"]
    usd = sum(theo.get(x.get("id"), 0) * _kep_luot(CP.uoc_lich(x, bang, nguon)["moi_luot"], chi)
              for x in cac_lich if x.get("bat")) + dl["web_them"]   # + web lịch thường ≤ 1/ngày
    tong = float(da_tieu or 0) + db["con_lai"] + usd
    tl = (chi or {}).get("tran_luot")
    if tl is not None:          # mỗi lượt (gồm nguồn, web) không tiêu quá trần console
        tong = min(tong, float(da_tieu or 0) + dl["luot_con_lai"] * float(tl))
    tv = _trung_vi(chi)
    return {"co_lich": True, "luot": dl["luot_con_lai"], "usd_lich": round(usd, 4),
            "nguon_chu_ky": db["con_lai"], "da_tieu": float(da_tieu or 0), "tong": round(tong, 4),
            "tran": db["tran"], "vuot": tong > db["tran"] + 1e-9,
            "chenh": round(abs(db["tran"] - tong), 4),
            "tong_thuc": (None if tv is None
                          else round(float(da_tieu or 0) + dl["luot_con_lai"] * tv, 4))}


# ───────────────────────────── xem trước biểu mẫu ─────────────────────────────
def xem_truoc(d: dict, cac_lich: list[dict], du_an: dict, nguon: list[dict], da_tieu: float,
              tran_pf: float | None, bay_gio: dt.datetime, lid: int | None = None,
              chi: dict | None = None) -> dict:
    """`d` = lịch đã kiểm (`LQ.chuan_hoa`), `cac_lich` = mọi lịch của dự án (lịch đang sửa `lid`
    được thay bằng `d`). `chi` (18/10/2026): như `dong_lich` — mức tối đa mỗi lượt kẹp ở trần
    console, thêm chi thật trung vị. -> {mo_ta, tan_suat, moc: [{chu, con, nhuong}], ghi_moc,
    chi_phi: [{nhan, gia_tri, phu}], ket_luan, cong_thuc, vuot, canh_bao: [chữ]}."""
    kieu, ch = d["kieu"], d["cau_hinh"]
    toi = lid if lid else -1
    khac = [x for x in cac_lich if x.get("id") != toi]
    ung_vien = {**d, "id": toi, "bat": True}
    tat_ca = khac + [ung_vien]
    khung_cd = [(x.get("id"), k) for x in khac if x.get("bat") and (k := LQ.khung_chien_dich(x))]
    moc = LQ.cac_moc(kieu, ch, bay_gio, 10)
    ds_moc = [{"chu": LQ.chu_moc(x, bay_gio), "con": LQ.chu_con(x, bay_gio),
               "nhuong": kieu != "chien_dich" and any(a <= x <= b for _, (a, b) in khung_cd)}
              for x in moc]
    ghi_moc = (f"Chiến dịch hết sau {len(moc)} lượt nữa." if kieu == "chien_dich" and len(moc) < 10
               else "")
    # ── chi phí ──
    bang = CP.bang_cau_hinh(du_an)
    u = dict(CP.uoc_lich(d, bang, nguon))
    u_goc = u["moi_luot"]
    u["moi_luot"] = _kep_luot(u_goc, chi)
    tv = _trung_vi(chi)
    khung = LQ.khung_chien_dich(ung_vien) if kieu == "chien_dich" else None
    if kieu == "chien_dich":
        ky_den, ky_nhan = (khung[1] if khung else bay_gio), "Cả chiến dịch"
    else:
        ky_den, ky_nhan = bay_gio + dt.timedelta(days=30), "30 ngày tới"
    # Review 15/10 (M2): kỳ của ứng viên (tới 92 ngày, bắt đầu ≤ 365 ngày tới) chỉ đếm mốc của
    # CHÍNH ứng viên — đếm mọi lịch khác tới hết chiến dịch là đường cho người xem làm treo CPU.
    # Phần tháng (≤ 31 ngày) vẫn đếm đủ mọi lịch để so trần.
    tru = [] if kieu == "chien_dich" else [k for _, k in khung_cd]
    luot_ky = LQ.dem_moc(kieu, ch, bay_gio, ky_den, tru)
    thang = LQ.dem_luot_du_an(tat_ca, bay_gio, _ket_thuc_thang(bay_gio))
    luot_thang = thang.get(toi, 0)
    usd_khac = sum(thang.get(x.get("id"), 0)
                   * _kep_luot(CP.uoc_lich(x, bang, nguon)["moi_luot"], chi)
                   for x in khac if x.get("bat"))
    db = CP.du_bao(nguon, da_tieu, float(du_an.get("tran_usd_thang") or 0), tran_pf, bay_gio)
    # Báo & Web (16/10/2026): lịch thường chạy web ≤ 1 lượt/ngày (`CP.luot_web_thuong`, cả dự án —
    # hai lịch cùng ngày vẫn một lượt web); lịch chiến dịch đã gồm web trong `moi_luot`.
    het_thang = _ket_thuc_thang(bay_gio)
    web_thang = CP.luot_web_thuong(tat_ca, bay_gio, het_thang) * u["web"]
    rieng = [x for x in khac if x.get("kieu") == "chien_dich"] + [ung_vien]
    web_ky = web_nay = 0.0
    if not u["web_moi_luot"] and u["web"]:
        web_ky = CP.luot_web_thuong(rieng, bay_gio, ky_den) * u["web"]
        web_nay = CP.luot_web_thuong(rieng, bay_gio, het_thang) * u["web"]
    usd_thang = luot_thang * u["moi_luot"]
    tong = float(da_tieu or 0) + db["con_lai"] + usd_khac + usd_thang + web_thang
    if (chi or {}).get("tran_luot") is not None:     # mỗi lượt (gồm nguồn, web) ≤ trần console
        tong = min(tong, float(da_tieu or 0) + sum(thang.values()) * float(chi["tran_luot"]))
    tran = db["tran"]
    vuot = tong > tran + 1e-9
    ghi_web = (f" · Báo & Web {_usd(u['web'], 3)} tối đa 1 lượt/ngày"
               if u["web"] and not u["web_moi_luot"] else "")
    kep = u["moi_luot"] < u_goc - 1e-9
    chi_phi = [
        {"nhan": "Mỗi lượt (tối đa)", "gia_tri": f"{_usd(u['moi_luot'], 3)} USD",
         "phu": (f"trần console mỗi lượt (theo cấu hình {_usd(u_goc, 3)})" if kep else
                 f"tìm từ khoá + bình luận {_usd(u['tk_bl'], 3)}"
                 + (f" + quét mọi nguồn {_usd(u['nguon'], 3)}" if d.get("quet_moi_nguon") else "")
                 + ghi_web)
                + (f" · thật ≈ {_usd(tv, 2)} USD/lượt (trung vị "
                   f"{(chi or {}).get('thuc', {}).get('so_luot')} lượt gần nhất)"
                   if tv is not None else "")},
        {"nhan": ky_nhan, "gia_tri": f"≈ {_usd(luot_ky * u['moi_luot'] + web_ky)} USD",
         "phu": f"{_so(luot_ky)} lượt"},
        {"nhan": f"Còn lại tháng {bay_gio.astimezone(LQ.VN):%m/%Y}",
         "gia_tri": f"≈ {_usd(usd_thang + web_nay)} USD", "phu": f"{_so(luot_thang)} lượt"},
    ]
    ket_luan = (f"Cả tháng tối đa ≈ {_usd(tong)} / {_usd(tran)} USD trần — "
                + (f"vượt {_usd(tong - tran)} USD, Mark dừng quét khi chạm trần." if vuot
                   else f"trong trần, còn dư {_usd(tran - tong)} USD."))
    cong_thuc = (f"= đã tiêu {_usd(da_tieu)} + nguồn theo chu kỳ {_usd(db['con_lai'])} + lịch "
                 f"khác {_usd(usd_khac)} + lịch này {_usd(usd_thang)}"
                 + (f" + Báo & Web ngoài chiến dịch {_usd(web_thang)}" if web_thang else ""))
    # ── cảnh báo ──
    cb = []
    if not du_an.get("dang_bat"):
        cb.append("Dự án đang tắt — lịch không chạy cho tới khi bật dự án ở trang Nguồn.")
    if vuot:
        cb.append("Có thể vượt trần tháng: Mark dừng quét khi chạm trần. Giảm tần suất, bớt tìm "
                  "từ khoá/bình luận ở trang Ngân sách, hoặc tăng trần.")
    if LQ.moc_gan_qua(kieu, ch):
        cb.append("Có hai mốc cách nhau dưới 30 phút — lượt sau thường bị bỏ vì lượt trước "
                  "chưa xong.")
    nhuong = sorted({i for i, (a, b) in khung_cd if kieu != "chien_dich"
                     and any(a <= x <= b for x in moc)})
    if nhuong:
        cb.append(f"Một số mốc rơi vào chiến dịch #{', #'.join(str(i) for i in nhuong)} — lịch "
                  "này nhường, không quét chồng.")
    if kieu == "chien_dich" and khung:
        tu, den = khung
        trung = [i for i, (a, b) in khung_cd if a <= den and tu <= b]
        if trung:
            cb.append(f"Trùng khung với chiến dịch #{', #'.join(str(i) for i in trung)}: lượt nào "
                      "tới trước chạy, lượt kia bị bỏ nếu lượt trước chưa xong.")
    if not u["tk_bl"] and not d.get("quet_moi_nguon"):
        cb.append("Tìm theo từ khoá và cào bình luận đang tắt: mỗi lượt chỉ quét nguồn tới chu kỳ"
                  " — chạy dày không thêm dữ liệu. Bật \"Quét mọi nguồn mỗi lượt\" hoặc bật tìm "
                  "từ khoá ở trang Ngân sách.")
    if bang["tu_khoa"]["facebook"]["bat"] and LQ.luot_moi_ngay(kieu, ch) > 1:
        cb.append("Facebook tìm theo từ khoá (gói Apify Free) chỉ chạy 1 lượt/24 giờ — các lượt "
                  "sau trong ngày báo lỗi phần Facebook, nền tảng khác vẫn chạy.")
    if d.get("quet_moi_nguon") and not any(
            (n.get("trang_thai") or "dang_theo_doi") == "dang_theo_doi" for n in nguon):
        cb.append("Dự án chưa có nguồn đang theo dõi — \"quét mọi nguồn\" chưa có gì để quét.")
    return {"mo_ta": LQ.mo_ta(kieu, ch), "tan_suat": tan_suat(kieu, ch), "moc": ds_moc,
            "ghi_moc": ghi_moc, "chi_phi": chi_phi, "ket_luan": ket_luan,
            "cong_thuc": cong_thuc, "vuot": vuot, "canh_bao": cb}


def tan_suat(kieu: str, ch: dict) -> str:
    n = LQ.luot_moi_ngay(kieu, ch)
    if kieu == "chien_dich":
        return f"≈ {int(n)} lượt/ngày trong khung chiến dịch"
    thu = LQ._cac_thu(ch.get("thu"))
    if kieu == "hang_tuan":
        return f"{int(n)} lượt mỗi ngày đã chọn · {int(n) * len(thu)} lượt/tuần"
    return f"{int(n)} lượt/ngày" + (f" · chỉ {LQ.chu_thu(thu)}" if thu and len(thu) < 7 else "")
