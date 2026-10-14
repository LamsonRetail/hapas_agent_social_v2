"""Lệnh `/theodoi <dự án>`: quét các NGUỒN ĐANG THEO DÕI của một dự án, giữ bài nhắc tới dự án,
gán nhãn AI, ghi vào kho `lang_nghe` (đợt 2, chủ dự án chốt 14/10/2026).

Vì sao có lệnh này — so với Kompa, Mark thiếu dữ liệu chủ yếu vì chỉ TÌM THEO TỪ KHOÁ khi được
hỏi; Kompa theo dõi sẵn danh sách nguồn và cộng dồn mỗi ngày. Lệnh này là nửa "theo dõi": danh
sách nguồn và ngân sách tháng quản lý trên dashboard (`social.hapas.vn`), Mark quét theo lịch.

Mark VẪN theo luật platform như trước (chủ dự án chốt 14/10/2026 — "không đổi"):
  • Lượt chạy đến từ LỊCH `run` đặt trên console platform (nội dung `/theodoi hapas`), đi qua
    hàng đợi job + audit như mọi việc khác — không có timer riêng trên VPS.
  • Cần công tắc `soi_tai_khoan` (cùng actor theo tài khoản) đang bật — kiểm ở `lenh_cung`.
  • Mỗi nền tảng tôn trọng công tắc + trần USD mỗi lượt ở "Năng lực → Quét mạng xã hội".
  • Trần tháng của dự án (dashboard) chỉ THU HẸP thêm: mỗi lượt actor mang trần USD =
    min(trần console của nền tảng, ước tính × 1,5, phần còn lại của tháng) — Apify tự dừng ở
    trần đó (`maxTotalChargeUsd`), nên lượt không thể tiêu quá phần tháng còn lại.

Chạy NỀN (`viec_nen`, loại `theo_doi`), cùng kỷ luật tiền với quét nền lớn (`quet_lon`):
  • mỗi "phần" = một lượt actor (một nền tảng × một mức số bài), ghi run id ngay khi Apify trả;
  • bài lấy được ghi xuống đĩa (`Viec.ghi_dong`) TRƯỚC khi đánh dấu phần xong;
  • bot khởi động lại: phần đã xong đọc lại từ đĩa; phần có run id thì ĐỌC TIẾP run đó; phần
    đang gửi dở thì tìm run vừa tạo, không kiểm được thì KHÔNG gửi lại (không trả tiền hai lần);
  • chi phí thật chốt theo đúng run id (`Viec.chot_chi_phi`) trong `finally` — lỗi giữa chừng
    vẫn ghi tiền vào lượt, nên "đã tiêu tháng" không bị đếm thiếu.
"""
from __future__ import annotations

import contextvars
import datetime
import hashlib
import re
import time

import apify_tool as A
import lang_nghe_db as K

_VN = datetime.timezone(datetime.timedelta(hours=7))
#: Nền tảng theo thứ tự chạy: miễn phí trước, để hết giờ/hết tiền thì phần mất là phần tốn tiền.
THU_TU = ("youtube", "instagram", "tiktok", "facebook")
_TEN = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok", "facebook": "Facebook"}
#: Giá đo thật 25/09/2026 (`account_tool._GIA`): TikTok/Facebook theo bài, Instagram theo tài
#: khoản (actor trả 12 bài mới nhất). YouTube Data API miễn phí.
_GIA = {"tiktok": 0.003, "facebook": 0.005, "instagram": 0.0026, "youtube": 0.0}
_HE_SO_UOC = 1.3          # ước tính chừa hao hụt (bài ghim, phí lẻ…)
_HE_SO_TRAN = 1.5         # trần USD của một lượt actor = ước tính × hệ số này (rồi kẹp)
_TRAN_TOI_THIEU = 0.1     # `_run_actor` kẹp trần ≥ 0,1 USD: tháng còn ít hơn thì không chạy
TOI_DA_NGUON = 60         # mỗi lượt; nguồn quá trần chờ lượt sau (cũ nhất đi trước)
NGAY_GIU = 35             # bài đăng cũ hơn chừng này ngày không ghi (không thuộc kỳ theo dõi)
NGAY_LAM_MOI_YT = 14      # bài YouTube đã giữ: đọc lại số mỗi ngày trong 14 ngày đầu (miễn phí)
_CHUA_GIAY_CUOI = 90      # giây chừa cho AI + ghi kho + chốt chi phí trước hạn chót việc
_KET_PHAN = ("xong", "mot_phan", "loi", "da_huy")
_LENH = "/theodoi"


# ───────────────────────────── tiện ích ─────────────────────────────
def _hom_nay() -> str:
    return datetime.datetime.now(_VN).strftime("%Y-%m-%d")


def _usd(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _chuan_dinh_danh(p: str, s: str) -> str:
    """Khoá so khớp nguồn ↔ kết quả actor: chữ thường, bỏ @, bỏ đuôi '/' và tham số URL.
    Id kênh YouTube (UC…) phân biệt hoa thường nên giữ nguyên."""
    s = (s or "").strip()
    if p == "youtube" and re.fullmatch(r"UC[\w-]{22}", s):
        return s
    s = s.split("?", 1)[0].split("#", 1)[0].rstrip("/").lower()
    if p == "facebook":
        s = re.sub(r"^https?://(www\.|m\.|web\.)?", "", s)
        s = s.replace("fb.com/", "facebook.com/")
    return s.lstrip("@")


def _khoa_bai(p: str, link: str, goc: dict | None = None) -> str:
    """"<nền tảng>:<id bài>" — id lấy từ link; không bóc được thì băm link (vẫn ổn định)."""
    link = link or ""
    mau = {"tiktok": r"/video/(\d+)", "instagram": r"/(?:p|reel|reels|tv)/([\w-]+)",
           "youtube": r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})",
           "facebook": r"(?:/posts/|/videos/|story_fbid=|/permalink/|fbid=)([\w-]+)"}.get(p)
    m = re.search(mau, link) if mau else None
    if m:
        return f"{p}:{m.group(1)}"
    for k in ("postId", "id", "shortCode"):
        if goc and goc.get(k):
            return f"{p}:{goc[k]}"
    return f"{p}:h{hashlib.sha1(link.encode('utf-8')).hexdigest()[:16]}"


def _so_hay_none(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ───────────────────────────── ước tính + phần ─────────────────────────────
def _uoc_phan(p: str, so_nguon: int, n: int) -> float:
    """USD ước tính của MỘT lượt actor: `so_nguon` nguồn, mỗi nguồn `n` bài (Instagram tính theo
    tài khoản), cộng phí khởi động của actor, nhân hệ số hao hụt."""
    gia = _GIA.get(p, 0.0)
    if not gia or not so_nguon:
        return 0.0
    don_vi = so_nguon if p == "instagram" else so_nguon * n
    return round((don_vi * gia + A._START_COST.get(p, 0.0)) * _HE_SO_UOC, 4)


def chia_phan(nguon: list[dict]) -> dict[str, list[dict]]:
    """Nguồn -> các phần (lượt actor). Nguồn cùng nền tảng VÀ cùng số bài mỗi lần đi chung một
    lượt — mỗi nguồn trả đúng số bài của nó (review 14/10: gộp theo số bài lớn nhất thì nguồn
    5 bài cũng bị lấy 30 bài và tốn tiền ngoài ước tính). YouTube một phần (API miễn phí)."""
    import account_tool
    nhom: dict[tuple[str, int], list[dict]] = {}
    for x in nguon:
        p = x["nen_tang"]
        n = 0 if p in ("youtube", "instagram") else int(x.get("so_bai_moi_lan") or 5)
        nhom.setdefault((p, n), []).append(x)
    ra: dict[str, list[dict]] = {}
    for (p, n), ds in sorted(nhom.items()):
        ids = [int(x["id"]) for x in ds]
        ph = {"id": f"{p}-{n or 'tat_ca'}", "nen_tang": p, "nguon": ids, "trang_thai": "cho",
              "n": n, "gia": _GIA.get(p, 0.0)}
        if p == "youtube":
            ph.update(actor="youtube", uoc_usd=0.0)
        else:
            ten = [x["dinh_danh"].lstrip("@") for x in ds]
            if p == "tiktok":
                payload, limit = account_tool._payload_tiktok(ten, n), n * len(ten)
            elif p == "instagram":
                payload, limit = account_tool._payload_instagram(ten), len(ten)
            else:
                payload = account_tool._payload_facebook([x["dinh_danh"] for x in ds], n)
                limit = n * len(ds)
            ph.update(actor=account_tool._ACTOR[p], payload=payload, limit=limit,
                      uoc_usd=_uoc_phan(p, len(ds), n))
        ra.setdefault(p, []).append(ph)
    return ra


def uoc_tinh(nguon: list[dict]) -> dict[str, float]:
    """USD ước tính mỗi nền tảng cho danh sách nguồn (theo đúng cách chia phần)."""
    return {p: round(sum(ph["uoc_usd"] for ph in cac), 4) for p, cac in chia_phan(nguon).items()}


def _cat_theo_ngan_sach(nguon: list[dict], con_usd: float) -> tuple[list[dict], list[dict]]:
    """Giữ nguồn theo thứ tự (cũ nhất trước) tới khi ước tính vượt `con_usd`. Nguồn miễn phí
    (YouTube) luôn giữ. -> (giữ, để lượt sau)."""
    giu, bo = [], []
    for n in nguon:
        if not _GIA.get(n["nen_tang"]):
            giu.append(n)
            continue
        if sum(uoc_tinh([*giu, n]).values()) <= con_usd + 1e-9:
            giu.append(n)
        else:
            bo.append(n)
    return giu, bo


def _nen_tang_dung_duoc(p: str) -> tuple[bool, str]:
    """Công tắc nền tảng ở "Năng lực → Quét mạng xã hội" + điều kiện riêng (key YouTube)."""
    if p == "youtube" and not A._youtube_co_key():
        return False, "máy chạy Mark chưa có YOUTUBE_DATA_API_KEY"
    _, _, bat = A._tran_nen_tang(p, nen=True)
    return (True, "") if bat else (False, A._ly_do_tat(p))


def _viec_dang_do(ma: str) -> dict | None:
    """Việc `theo_doi` CHƯA kết thúc của cùng dự án trong sổ việc nền (kể cả đang xếp hàng)
    — review 14/10: hai lịch/hai chat cùng gõ /theodoi hapas thì cả hai qua kiểm tra lượt
    đang chạy (lượt chỉ mở khi việc bắt đầu) và quét trùng nguồn."""
    import viec_nen
    for d in reversed(viec_nen.tat_ca()):
        if (d.get("loai") == "theo_doi" and (d.get("tham_so") or {}).get("du_an") == ma
                and d.get("trang_thai") in viec_nen.TRANG_THAI_DANG):
            return d
    return None


def ke_hoach(ma: str) -> dict:
    """Đọc kho + console, quyết định lượt này quét gì. Không gọi Apify, không tốn tiền.

    -> {"loi": câu báo} khi không chạy được; ngược lại {"du_an", "nguon", "bo_qua" (nguồn
    không quét lượt này + lý do), "uoc_tinh", "con_thang", "tran_thang", "da_tieu"}."""
    try:
        du_an = K.doc_du_an(ma)
        if not du_an:
            co = ", ".join(x["ma"] for x in K.cac_du_an()) or "chưa có dự án nào"
            return {"loi": f"Không có dự án '{ma}' trong kho lắng nghe. Dự án đang có: {co}. "
                           "Thêm dự án trên dashboard social.hapas.vn."}
        if not du_an["dang_bat"]:
            return {"loi": f"Dự án {du_an['ten']} đang tắt trên dashboard — lượt này không quét."}
        dang = K.luot_dang_chay(ma)
        if dang:
            return {"loi": f"Lượt theo dõi trước của {du_an['ten']} còn đang chạy "
                           f"(mã {dang.get('ma_viec') or dang['id']}) — đợi lượt đó xong."}
        toi_han = K.nguon_toi_han(ma)
        dem = K.dem_nguon(ma) if not toi_han else {}
        da_tieu = K.da_tieu_thang(ma)
    except K.LoiKho as e:
        return {"loi": f"Kho lắng nghe chưa dùng được: {e}."}
    if not toi_han:
        return {"loi": (f"Chưa có nguồn nào của {du_an['ten']} tới hạn quét "
                        f"(đang theo dõi {dem.get('dang_theo_doi', 0)}, tạm dừng "
                        f"{dem.get('tam_dung', 0)}). Thêm nguồn hoặc đổi chu kỳ trên dashboard.")}
    bo_qua: list[tuple[dict, str]] = []
    dung: dict[str, tuple[bool, str]] = {}
    con_lai = []
    for n in toi_han:
        p = n["nen_tang"]
        if p not in dung:
            dung[p] = _nen_tang_dung_duoc(p)
        if dung[p][0]:
            con_lai.append(n)
        else:
            bo_qua.append((n, dung[p][1]))
    for n in con_lai[TOI_DA_NGUON:]:
        bo_qua.append((n, f"quá {TOI_DA_NGUON} nguồn một lượt — để lượt sau"))
    con_lai = con_lai[:TOI_DA_NGUON]
    tran = float(du_an["tran_usd_thang"] or 0)
    con_thang = max(0.0, tran - da_tieu)
    giu, het_tien = _cat_theo_ngan_sach(con_lai, con_thang)
    for n in het_tien:
        bo_qua.append((n, f"hết ngân sách tháng của dự án ({_usd(da_tieu)}/{_usd(tran)} USD)"))
    if not giu:
        ly = bo_qua[0][1] if bo_qua else "không có nguồn quét được"
        return {"loi": f"Lượt theo dõi {du_an['ten']} không quét được nguồn nào: {ly}."}
    return {"du_an": du_an, "nguon": giu, "bo_qua": bo_qua, "uoc_tinh": uoc_tinh(giu),
            "con_thang": con_thang, "tran_thang": tran, "da_tieu": da_tieu}


# ───────────────────────────── lệnh ─────────────────────────────
def lenh_theodoi(doi_so: str) -> str:
    """`/theodoi <mã dự án>` → tạo việc nền, trả lời NGAY (không gọi model, không bịa)."""
    ma = (doi_so or "").strip().split(" ", 1)[0].lower()
    if not ma:
        try:
            ds = ", ".join(f"{x['ma']} ({x['ten']})" for x in K.cac_du_an()) or "chưa có"
        except K.LoiKho as e:
            return f"Kho lắng nghe chưa dùng được: {e}."
        return (f"Cách dùng: {_LENH} <mã dự án>, vd `{_LENH} hapas`. Dự án đang có: {ds}. "
                "Đặt lịch hằng ngày ở tab Lịch chạy trên console: kiểu Giao việc, nội dung "
                f"`{_LENH} <mã dự án>`.")
    cu = _viec_dang_do(ma)
    if cu:
        return (f"Đã có việc theo dõi '{ma}' chưa xong (mã {cu.get('ma')}) — không tạo thêm để "
                "khỏi quét trùng nguồn. Gõ /viec để xem tiến độ.")
    kh = ke_hoach(ma)
    if kh.get("loi"):
        return kh["loi"]
    import quet_lon
    import viec_nen
    phan = chia_phan(kh["nguon"])
    tong = round(sum(ph["uoc_usd"] for cac in phan.values() for ph in cac), 2)
    da = kh["du_an"]
    # Bình luận (đợt 2b): chưa biết bài nào sẽ được cào nên giữ chỗ theo trần cấu hình, giá
    # Facebook; tiền thật vẫn chốt theo run id.
    bl_uoc = round(uoc_binh_luan(int(da.get("bl_so_bai") or 0), int(da.get("bl_moi_bai") or 20))
                   if da.get("bl_bat", True) else 0.0, 2)
    ns_apify, hm, _ = quet_lon.ngan_sach(quet_lon.tran_usd_nen())
    # Bình luận chỉ dùng phần ngân sách việc nền còn lại sau phần bài — lúc chạy mỗi lượt actor
    # bình luận vẫn bị kẹp theo trần console và phần còn lại của tháng.
    bl_uoc = round(max(0.0, min(bl_uoc, ns_apify - tong)), 2)
    tong = round(tong + bl_uoc, 2)
    if tong > ns_apify + 1e-9:
        return (f"Chưa chạy: lượt này ước tính {_usd(tong)} USD mà ngân sách Apify còn dùng được "
                f"cho việc nền là {_usd(ns_apify)} USD (trần console hoặc hạn mức tháng của tài "
                "khoản). Giảm số nguồn/số bài mỗi lần trên dashboard hoặc đợi tháng sau.")
    ngan_sach = round(min(kh["con_thang"], ns_apify, max(tong, 0.01) * _HE_SO_TRAN), 2)
    kq = viec_nen.tao_viec(
        "theo_doi",
        {"du_an": ma, "ngay": _hom_nay(), "nguon": sorted(int(n["id"]) for n in kh["nguon"])},
        {p: {"phan": cac} for p, cac in phan.items()}, {"usd": tong,
                                                         "phut": max(3, len(kh["nguon"]) // 4)
                                                         + (3 if bl_uoc else 0)},
        ngan_sach, [f"bỏ qua {len(kh['bo_qua'])} nguồn"] if kh["bo_qua"] else [],
        con_lai_thang=(hm or {}).get("con_lai"))
    if kq.get("tu_choi") or kq.get("da_xong_truoc"):
        return str(kq.get("ket_qua") or kq.get("note") or "Không tạo được việc theo dõi.")
    dem: dict[str, int] = {}
    for n in kh["nguon"]:
        dem[n["nen_tang"]] = dem.get(n["nen_tang"], 0) + 1
    ds = ", ".join(f"{_TEN.get(p, p)} {k}" for p, k in dem.items())
    cau = (f"Đã nhận lượt theo dõi {kh['du_an']['ten']} (mã {kq.get('ma_viec')}): "
           f"{len(kh['nguon'])} nguồn ({ds}), ước tính tối đa {_usd(tong)} USD"
           + (f" (gồm tới {_usd(bl_uoc)} USD cào bình luận)" if bl_uoc else "")
           + "; ngân sách tháng "
           f"của dự án còn {_usd(kh['con_thang'])}/{_usd(kh['tran_thang'])} USD. "
           f"Xong Mark nhắn kết quả vào đây.")
    if kh["bo_qua"]:
        ly = sorted({x[1] for x in kh["bo_qua"]})
        cau += f" Bỏ qua {len(kh['bo_qua'])} nguồn: {'; '.join(ly)[:300]}."
    return cau


# ───────────────────────────── đọc bài của một phần ─────────────────────────────
def _dong_tu_tai_khoan(p: str, tk: dict) -> list[tuple[dict, datetime.datetime | None]]:
    """Kết quả `account_tool._doc_*` của MỘT tài khoản -> [(dòng kiểu social_listen, ngày)]."""
    hs = tk.get("ho_so") or {}
    ra = []
    for b in tk.get("bai") or []:
        goc = b.get("_goc") or {}
        tags = [str(h).lstrip("#") for h in b.get("hashtag") or [] if h]
        ra.append(({
            "platform": p, "kenh": str(hs.get("ten") or ""), "username": str(hs.get("tai_khoan") or ""),
            "followers": hs.get("followers"), "views": b.get("view"), "likes": b.get("like"),
            "comments": b.get("binh_luan"), "shares": b.get("share"),
            "hashtags": ", ".join(tags)[:500], "text": str(b.get("noi_dung") or "")[:1000],
            "link": str(b.get("link") or ""), "_goc_id": str(goc.get("id") or goc.get("postId")
                                                             or "") or None,
            "_goc_vao": str(goc.get("inputUrl") or goc.get("facebookUrl") or ""),
        }, b.get("ngay")))
    return ra


def ghep_nguon(p: str, ket: dict[str, dict], nguon: list[dict]) -> tuple[dict[int, list],
                                                                          dict[int, str]]:
    """Kết quả actor (theo tài khoản) -> ({id nguồn: [(dòng, ngày)]}, {id nguồn: lỗi})."""
    theo_khoa = {_chuan_dinh_danh(p, x["dinh_danh"]): x for x in nguon}
    ra: dict[int, list] = {int(x["id"]): [] for x in nguon}
    loi: dict[int, str] = {}
    for k, tk in ket.items():
        dong = _dong_tu_tai_khoan(p, tk)
        if p == "facebook":
            # Actor Facebook đặt khoá theo TÊN TRANG; ghép về nguồn theo URL đầu vào của bài.
            for d, dt in dong:
                n = theo_khoa.get(_chuan_dinh_danh(p, d.get("_goc_vao") or ""))
                if n is None and len(nguon) == 1:
                    n = nguon[0]
                if n is not None:
                    ra[int(n["id"])].append((d, dt))
            continue
        n = theo_khoa.get(_chuan_dinh_danh(p, k))
        if n is None:
            continue
        if tk.get("ghi_chu") and not dong:
            loi[int(n["id"])] = str(tk["ghi_chu"])[:200]
        ra[int(n["id"])].extend(dong[:int(n.get("so_bai_moi_lan") or 5)])
    for nid, dong in ra.items():
        if not dong and nid not in loi:
            loi[nid] = "không lấy được bài nào (tài khoản riêng tư, đổi tên hoặc sai định danh?)"
    return ra, loi


def _doc_ket_qua(p: str, items: list, n: int) -> dict[str, dict]:
    import account_tool
    if p == "tiktok":
        return account_tool._doc_tiktok(items)
    if p == "instagram":
        return account_tool._doc_instagram(items, 12)
    return account_tool._doc_facebook(items)


def _lay_youtube(nguon: list[dict]) -> tuple[dict[int, list], dict[int, str]]:
    """Video mới nhất của từng kênh qua YouTube Data API (miễn phí): channels → playlist
    uploads → playlistItems → videos. ~3 đơn vị quota mỗi kênh (search.list thì 100)."""
    ra: dict[int, list] = {int(x["id"]): [] for x in nguon}
    loi: dict[int, str] = {}
    kenh: dict[int, dict] = {}
    theo_id: dict[str, list[dict]] = {}
    for x in nguon:
        dd = x["dinh_danh"].strip()
        if re.fullmatch(r"UC[\w-]{22}", dd):
            theo_id.setdefault(dd, []).append(x)
            continue
        try:
            data = A._youtube_get("channels", {"part": "snippet,statistics,contentDetails",
                                               "forHandle": "@" + dd.lstrip("@")})
        except A.LoiYouTube as e:
            loi[int(x["id"])] = str(e)[:200]
            continue
        it = (data.get("items") or [None])[0]
        if it:
            kenh[int(x["id"])] = it
        else:
            loi[int(x["id"])] = "không tìm thấy kênh YouTube theo handle này"
    for lo in A._chunks(list(theo_id)):
        try:
            data = A._youtube_get("channels", {"part": "snippet,statistics,contentDetails",
                                               "id": ",".join(lo), "maxResults": 50})
        except A.LoiYouTube as e:
            for cid in lo:
                for x in theo_id[cid]:
                    loi[int(x["id"])] = str(e)[:200]
            continue
        thay = {str(it.get("id")): it for it in data.get("items") or [] if isinstance(it, dict)}
        for cid in lo:
            for x in theo_id[cid]:
                if cid in thay:
                    kenh[int(x["id"])] = thay[cid]
                else:
                    loi[int(x["id"])] = "không tìm thấy kênh YouTube theo id này"
    theo_nguon = {int(x["id"]): x for x in nguon}
    for nid, it in kenh.items():
        x = theo_nguon[nid]
        sn = it.get("snippet") or {}
        uploads = ((it.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
        if not uploads:
            loi[nid] = "kênh không có danh sách video công khai"
            continue
        try:
            pl = A._youtube_get("playlistItems", {
                "part": "contentDetails", "playlistId": uploads,
                "maxResults": min(50, int(x.get("so_bai_moi_lan") or 5))})
            ids = [str((v.get("contentDetails") or {}).get("videoId") or "")
                   for v in pl.get("items") or [] if isinstance(v, dict)]
            ra[nid] = _video_youtube([i for i in ids if i], {
                "kenh": str(sn.get("title") or x.get("ten") or ""),
                "followers": int((it.get("statistics") or {}).get("subscriberCount") or 0),
                "_quoc_gia": str(sn.get("country") or "")})
        except A.LoiYouTube as e:
            loi[nid] = str(e)[:200]
            continue
        if not ra[nid]:
            loi[nid] = "kênh chưa có video công khai"
    return ra, loi


def _video_youtube(ids: list[str], kenh: dict | None = None) -> list[tuple]:
    """videos.list (1 đơn vị / 50 video) -> [(dòng kiểu social_listen, ngày VN)]."""
    import html
    ra = []
    for lo in A._chunks(ids):
        data = A._youtube_get("videos", {"part": "snippet,statistics", "id": ",".join(lo),
                                         "maxResults": 50})
        for it in data.get("items") or []:
            if not isinstance(it, dict) or not it.get("id"):
                continue
            sn, st = it.get("snippet") or {}, it.get("statistics") or {}
            title = html.unescape(str(sn.get("title") or ""))
            desc = html.unescape(str(sn.get("description") or ""))
            tags = A._tags_from(f"{title} {desc}")
            if sn.get("tags"):
                tags = A._join([tags, A._join(sn.get("tags"))])
            k = kenh or {}
            ra.append(({
                "platform": "youtube",
                "kenh": k.get("kenh") or html.unescape(str(sn.get("channelTitle") or "")),
                "username": "", "followers": k.get("followers"),
                "_quoc_gia": k.get("_quoc_gia", ""),
                "_ngon_ngu": str(sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or ""),
                "views": int(st.get("viewCount") or 0), "likes": int(st.get("likeCount") or 0),
                "comments": int(st.get("commentCount") or 0), "shares": None,
                "hashtags": tags, "text": f"{title} — {desc}"[:1000],
                "link": f"https://www.youtube.com/watch?v={it['id']}",
            }, A._to_vn(sn.get("publishedAt"))))
    return ra


# ───────────────────────────── lọc + nhãn ─────────────────────────────
def chon_bai(du_an: dict, theo_nguon: dict[int, list], nguon: dict[int, dict],
             han_ai: float, bay_gio: datetime.datetime | None = None) -> tuple[list[dict], dict]:
    """Giữ bài liên quan tới dự án + gán nhãn. -> (dòng ghi kho, thống kê).

    • Bài cũ hơn `NGAY_GIU` ngày hoặc không có ngày: bỏ.
    • Có từ loại trừ của dự án: bỏ (luật cứng, không qua AI).
    • Nguồn `kenh_nha` (kênh của chính brand): giữ mọi bài; AI chỉ gán sắc thái/chủ đề.
    • Nguồn khác: chỉ xét bài NHẮC từ khoá dự án; AI phán giữ/loại (trùng tên, lạc đề…).
      AI hỏng/hết giờ/`khong_ro` thì giữ theo luật (đã nhắc từ khoá, nguồn do người chọn)."""
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    moc = bay_gio - datetime.timedelta(days=NGAY_GIU)
    tu_khoa = [str(x) for x in du_an.get("tu_khoa") or [] if str(x).strip()] or [du_an["ten"]]
    loai_tru = [str(x) for x in du_an.get("tu_loai_tru") or [] if str(x).strip()]
    tk = {"lay_duoc": 0, "qua_cu": 0, "khong_nhac": 0, "loai_tru": 0, "ai_loai": 0,
          "giu": 0, "ai": ""}
    cho: list[tuple[dict, datetime.datetime, dict]] = []
    thay: set[str] = set()
    for nid, dong in theo_nguon.items():
        n = nguon.get(nid)
        if n is None:
            continue
        for d, dt in dong:
            khoa = _khoa_bai(d["platform"], d.get("link") or "", {"id": d.get("_goc_id")})
            if khoa in thay:
                continue                 # trùng (đọc lại sau khởi động lại, hoặc nguồn trùng)
            thay.add(khoa)
            tk["lay_duoc"] += 1
            if not dt or dt < moc:
                tk["qua_cu"] += 1
                continue
            d["_khop"] = A._khop_tu_khoa(d, tu_khoa)
            d["_thi_truong"] = A._thi_truong(d, tu_khoa)
            if A._tu_loai_tru_khop(d, loai_tru):
                tk["loai_tru"] += 1
                continue
            if n.get("loai") != "kenh_nha" and not d["_khop"]:
                tk["khong_nhac"] += 1
                continue
            d["_khoa"] = khoa
            cho.append((d, dt, n))
    phan_xu: dict = {}
    tt: dict = {"_sac_thai": {}, "_chu_de": {}, "trang_thai": ""}
    if cho:
        phan_xu, tt = A._phan_xu_ai([(d, dt) for d, dt, _ in cho], tu_khoa,
                                    du_an.get("boi_canh") or du_an["ten"],
                                    du_an.get("thi_truong") or "VN", han_ai)
    tk["ai"] = tt.get("trang_thai") or ""
    ra = []
    for i, (d, dt, n) in enumerate(cho):
        px = phan_xu.get(i)
        if px and px[1] == "khong_ro":
            px = None                     # AI không chắc → về luật (như social_listen)
        nha = n.get("loai") == "kenh_nha"
        if px and not px[0] and not nha:
            tk["ai_loai"] += 1
            continue
        ly_do = "kenh_nha" if nha and not (px and px[0]) else (px[1] if px else "khop_tu_khoa")
        ra.append({
            "khoa": d["_khoa"], "nen_tang": d["platform"], "nguon_id": int(n["id"]),
            "link": d.get("link") or "", "tac_gia": str(d.get("kenh") or "")[:200],
            "tai_khoan": str(d.get("username") or "")[:200],
            "followers": _so_hay_none(d.get("followers")), "dang_luc": dt,
            "noi_dung": str(d.get("text") or "")[:1000],
            "hashtag": str(d.get("hashtags") or "")[:500],
            "khop_tu_khoa": bool(d.get("_khop")), "sac_thai": tt["_sac_thai"].get(i),
            "chu_de": tt["_chu_de"].get(i), "ly_do_giu": str(ly_do)[:60],
            "xem": _so_hay_none(d.get("views")), "thich": _so_hay_none(d.get("likes")),
            "binh_luan": _so_hay_none(d.get("comments")),
            "chia_se": _so_hay_none(d.get("shares")),
        })
    tk["giu"] = len(ra)
    return ra, tk


# ───────────────────────────── chạy nền ─────────────────────────────
def chay_viec(v) -> tuple[str, str]:
    """Runner của `viec_nen` cho loại `theo_doi`. -> (trạng thái việc, câu nhắn kết quả).

    Chạy trong BẢN SAO ngữ cảnh: các cờ Apify (`_NEN`, `_HUY`, `_HAN_CHOT`, `_NEN_TANG`,
    `_KHI_CO_RUN`) đặt ở đây không rò sang lượt khác dùng chung luồng."""
    return contextvars.copy_context().run(_chay_viec, v)


def _ghi_phan(v, p: str, ph: dict, kq: dict[int, list], loi: dict[int, str]) -> None:
    """Ghi bài của một phần xuống đĩa (kèm id nguồn) và lỗi từng nguồn vào sổ việc."""
    rows = []
    for nid, dong in kq.items():
        for d, dt in dong:
            rows.append(({**d, "_nguon_id": nid}, dt))
    if rows:
        v.ghi_dong(p, rows, ph["id"])
    v.cap_nhat_phan(ph, loi_nguon={str(k): x for k, x in loi.items()})


def _chay_actor(v, p: str, ph: dict, cap: float, han: float,
                min_charge: float = 0.0) -> tuple[list, dict, Exception | None, float | None]:
    """Chạy / đọc tiếp MỘT lượt actor của phần `ph`, cùng kỷ luật với `quet_lon._mot_phan`:
    ghi run id ngay khi Apify trả; phần có run id thì đọc tiếp; phần đang gửi dở thì tìm run
    vừa tạo, không kiểm được thì KHÔNG gửi lại. -> (items, meta, lỗi, tiền phải coi như đã
    tiêu khi không kiểm được run cũ — None nếu không phải trường hợp đó)."""
    import quet_lon
    actor = ph["actor"]
    A._NEN_TANG.set(p)
    A._KHI_CO_RUN.set(lambda run, meta: v.cap_nhat_phan(
        ph, run_id=run.get("id"), dataset_id=run.get("defaultDatasetId"), trang_thai="dang_chay"))
    items: list = []
    meta: dict = {}
    loi = None
    try:
        if ph.get("run_id"):
            items, meta = A._doc_tiep_run(ph["run_id"], int(ph["limit"]), han, True, actor)
        else:
            run = None
            if ph.get("trang_thai") == "dang_gui" and ph.get("moc_gui"):
                run, kiem = A._tim_run_vua_tao_ex(
                    actor, ph["payload"], quet_lon._h(),
                    datetime.datetime.fromisoformat(ph["moc_gui"]), nghiem=True)
                if not run and not kiem:
                    return [], {}, None, float(ph.get("tran_usd") or cap)
            if run:
                v.cap_nhat_phan(ph, run_id=run["id"], trang_thai="dang_chay", nhan_lai=True)
                items, meta = A._doc_tiep_run(run["id"], int(ph["limit"]), han, True, actor)
            else:
                v.cap_nhat_phan(ph, trang_thai="dang_gui", tran_usd=cap,
                                moc_gui=datetime.datetime.now(_VN).isoformat())
                items, meta = A._run_actor(actor, ph["payload"], int(ph["limit"]), None, han,
                                           min_charge, tran_usd=cap, mot_phan=True, nen_tang=p)
    except A.LoiApify as e:
        loi, meta = e, e.meta
    except Exception as e:
        if type(e).__name__ == "MatQuyen":
            raise
        loi = A.LoiApify("LOI", A._che_token(f"{type(e).__name__}: {e}")[:250])
        meta = loi.meta
    finally:
        A._KHI_CO_RUN.set(None)
    return items or [], meta, loi, None


def _chay_phan_apify(v, p: str, ph: dict, ds: list[dict], cap: float, han: float) -> float:
    """Một lượt actor quét bài của một phần. -> USD theo sổ của phần."""
    import quet_lon
    items, meta, loi, khong_kiem = _chay_actor(v, p, ph, cap, han)
    if khong_kiem is not None:
        v.cap_nhat_phan(ph, trang_thai="loi", ma="KHONG_KIEM_DUOC", so_item=0,
                        usd_so=khong_kiem, ly_do=quet_lon._CAU_KHONG_KIEM)
        return khong_kiem
    kq, loi_nguon = ghep_nguon(p, _doc_ket_qua(p, items, int(ph.get("n") or 0)), ds)
    if loi is not None:
        for nid, dong in kq.items():
            if not dong:
                loi_nguon[nid] = A._che_token(str(loi))[:200]
    _ghi_phan(v, p, ph, kq, loi_nguon)
    tien = quet_lon._so_tien(p, ph, items, meta)
    if loi is not None and meta.get("khong_kiem_duoc"):
        tien = cap                       # POST mơ hồ, không kiểm được: coi như đã tiêu trần
    quet_lon._ket_phan(v, ph, meta, len(items), loi, usd_so=tien)
    return float(tien)


# ───────────────────────────── bình luận (đợt 2b, 15/10/2026) ─────────────────────────────
# Chủ dự án 15/10: dashboard phải bóc được TỪNG bình luận như Kompa. Sau khi ghi bài, lượt cào
# bình luận của tối đa `bl_so_bai` bài (chưa cào trước, rồi nhiều bình luận nhất) × `bl_moi_bai`
# bình luận mỗi bài. Dùng lại actor + bộ đọc của `deep_dive_tool` (đã đo thật) và bộ gán nhãn
# bình luận `phan_loai`. YouTube qua Data API miễn phí. Tiền đi chung lượt (run id trong phần
# "binh_luan" của việc → `chot_chi_phi`), nên tính vào trần tháng của dự án.
BL_NEN_TANG = ("youtube", "tiktok", "instagram", "facebook")
_BL_GIA = {"tiktok": 0.00125, "facebook": 0.0025, "instagram": 0.0026, "youtube": 0.0}
_BL_KHOI_DONG = {"facebook": 0.001}
_BL_LO = 25                       # bài mỗi lượt actor bình luận


def uoc_binh_luan(so_bai: int, moi_bai: int, p: str = "facebook") -> float:
    """USD ước tính cào `moi_bai` bình luận × `so_bai` bài trên nền tảng `p` (mặc định giá
    Facebook — đắt nhất trừ Instagram, dùng để giữ chỗ ngân sách khi chưa biết bài nào)."""
    if not so_bai or not _BL_GIA.get(p):
        return 0.0
    return round((so_bai * moi_bai * _BL_GIA[p] + _BL_KHOI_DONG.get(p, 0.0)) * _HE_SO_UOC, 4)


def _ma_bl(r: dict) -> str:
    g = r.get("__goc") or {}
    m = g.get("cid") or g.get("id") or g.get("commentId") if isinstance(g, dict) else None
    if m:
        return str(m)[:120]
    s = f"{r.get('kenh')}|{r.get('text')}|{r.get('thoi_gian')}"
    return "h" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _gio_bl(s) -> datetime.datetime | None:
    """`deep_dive_tool._gio` trả "YYYY-MM-DD HH:MM" giờ VN; chữ khác (thời gian tương đối) → None."""
    try:
        return datetime.datetime.strptime(str(s or ""), "%Y-%m-%d %H:%M").replace(tzinfo=_VN)
    except ValueError:
        return None


def _dong_bl(r: dict, bai: dict, thuong_hieu: list[str]) -> dict:
    import phan_loai
    # Chủ bài trả lời = tiếng thương hiệu CHỈ khi bài ở kênh nhà; trên bài KOL/đối thủ, chủ
    # bài trả lời không phải HAPAS (review 15/10).
    chu = ([x for x in (bai.get("tai_khoan"), bai.get("tac_gia")) if x]
           if bai.get("nguon_loai") == "kenh_nha" else [])
    nha = bool(r.get("cua_chu")) or any(
        phan_loai.la_tai_khoan_nha(r.get("kenh"), thuong_hieu, c) for c in chu or [""])
    return {"khoa_bai": bai["khoa"], "ma": _ma_bl(r), "nen_tang": bai["nen_tang"],
            "tac_gia": str(r.get("kenh") or "")[:200], "noi_dung": str(r.get("text") or "")[:1000],
            "thich": _so_hay_none(r.get("likes")), "tra_loi": _so_hay_none(r.get("replies")),
            "la_tra_loi": bool(r.get("cha")), "cua_thuong_hieu": nha,
            "dang_luc": _gio_bl(r.get("thoi_gian")), "sac_thai": None, "chu_de": None,
            "likes": r.get("likes"), "text": r.get("text")}


def _phan_bl(v) -> list[dict]:
    with v._khoa:
        return v.d.setdefault("nen_tang", {}).setdefault("binh_luan", {"phan": []})["phan"]


def _tao_phan_bl(v, p: str, lo: list[dict], per: int) -> dict:
    """Một phần bình luận cho các bài `lo` cùng nền tảng (lập rồi lưu sổ ngay)."""
    _tao_cac_phan_bl(v, [dict(b, nen_tang=p) for b in lo], per)
    return _phan_bl(v)[-1]


def _tao_cac_phan_bl(v, ds: list[dict], per: int) -> None:
    """Lập MỌI phần bình luận rồi lưu sổ một lần — bot tắt giữa chừng thì hoặc chưa có phần
    nào (lần sau chọn lại), hoặc có đủ (không lặng lẽ bỏ nền tảng còn lại)."""
    import deep_dive_tool as D
    cac = []
    for p in BL_NEN_TANG:
        bp = [b for b in ds if b["nen_tang"] == p]
        for i in range(0, len(bp), _BL_LO):
            lo = bp[i:i + _BL_LO]
            urls = [b["link"] for b in lo]
            ph = {"id": f"bl-{p}-{len(_phan_bl(v)) + len(cac)}", "nen_tang": p, "trang_thai": "cho",
                  "bai": [{k: b.get(k) for k in ("khoa", "link", "nen_tang", "tai_khoan",
                                                 "tac_gia", "binh_luan", "nguon_loai")}
                          for b in lo],
                  "per": per, "gia": _BL_GIA.get(p, 0.0), "uoc_usd": uoc_binh_luan(len(lo), per, p)}
            if p != "youtube":
                ph.update(actor=D._ACTORS[p], payload=D._payload(p, urls, per),
                          limit=D._limit(p, urls, per))
            cac.append(ph)
    if cac:
        with v._khoa:
            _phan_bl(v).extend(cac)
            v.luu()


def _con_viec(v) -> float:
    """Ngân sách CỦA VIỆC còn lại (đã giữ chỗ trong sổ việc nền lúc tạo, ≤ trần console nền và
    hạn mức tháng của tài khoản) trừ tiền các phần đã xong. Việc không có ngân sách (bộ thử cũ)
    thì không giới hạn thêm. Review 15/10: bình luận không được vượt phần đã giữ chỗ — hai việc
    nền song song mới không cùng tiêu quá hạn mức tài khoản."""
    ns = v.d.get("ngan_sach_usd")
    if ns is None:
        return float("inf")
    da = sum(float(ph.get("usd_so") or 0) for _, ph in v.cac_phan()
             if ph.get("trang_thai") in _KET_PHAN)
    return max(0.0, float(ns) - da)


def _doc_bl(p: str, items: list) -> list[dict]:
    import deep_dive_tool as D
    rows, _ = {"tiktok": D._map_tiktok, "facebook": D._map_facebook,
               "instagram": D._map_instagram}[p](items)
    return rows


def _quy_bl(rows: list[dict], bai: list[dict]) -> dict[str, list[dict]]:
    """Bình luận → bài (theo id bài trong link, như `deep_dive_tool._quy_ve_bai`)."""
    import deep_dive_tool as D
    theo_link = {b["link"]: b for b in bai}
    ra: dict[str, list[dict]] = {b["khoa"]: [] for b in bai}
    for r in rows:
        u = D._quy_ve_bai(r.get("_nguon") or [r.get("link") or ""], list(theo_link))
        if u:
            ra[theo_link[u]["khoa"]].append(r)
    return ra


def _lay_binh_luan(v, du_an: dict, luot: int, con: float, han: float) -> dict:
    """Cào + gán nhãn + ghi bình luận cho các bài nên cào. -> thống kê. Tiền: run id nằm trong
    phần "binh_luan" của việc nên `chot_chi_phi` tính chung. Không ném lỗi Apify ra ngoài —
    bình luận hỏng thì lượt bài vẫn xong."""
    import deep_dive_tool as D
    import quet_lon
    ma = du_an["ma"]
    tk = {"bai": 0, "lay": 0, "moi": 0, "cu": 0, "nha": 0, "usd": 0.0, "ghi_chu": [],
          "nhan": ""}
    if not du_an.get("bl_bat", True) or int(du_an.get("bl_so_bai") or 0) <= 0:
        return tk
    per = max(5, min(200, int(du_an.get("bl_moi_bai") or 20)))
    thuong_hieu = [du_an["ten"], *(du_an.get("tu_khoa") or [])]
    if not _phan_bl(v):
        dung = [p for p in BL_NEN_TANG if p == "youtube" and A._youtube_co_key()
                or p != "youtube" and _nen_tang_dung_duoc(p)[0]]
        ds = K.bai_can_lay_binh_luan(ma, dung, int(du_an["bl_so_bai"]))
        _tao_cac_phan_bl(v, ds, per)
    for ph in list(_phan_bl(v)):
        p = ph["nen_tang"]
        if ph.get("trang_thai") in _KET_PHAN:
            continue
        bai = ph["bai"]
        tk["bai"] += len(bai)
        rows: list[dict] = []
        if p == "youtube":
            kq = D._yt_api_lo([b["link"] for b in bai], per, han)
            rows = kq["binh_luan"]
            if kq["loi"]:
                tk["ghi_chu"].append(f"bình luận YouTube: {A._che_token(kq['loi'])[:120]}")
            _ghi_bl_kho(ma, luot, ph, rows, thuong_hieu, han, tk,
                        day_du=not (kq["loi"] or kq["chua_chay"] or kq["mot_phan"]))
            v.cap_nhat_phan(ph, trang_thai="xong" if not kq["loi"] else "mot_phan",
                            ma="OK" if not kq["loi"] else "LOI", so_item=len(rows), usd_so=0.0,
                            ly_do=kq["loi"][:200])
            continue
        dang_do = ph.get("trang_thai") in ("dang_gui", "dang_chay")
        min_charge = float(D._MIN_CHARGE.get(p, 0.0))
        if dang_do:
            cap = float(ph.get("tran_usd") or 0) or _TRAN_TOI_THIEU
        else:
            tran_console = A._tran_nen_tang(p, nen=True)[1]
            cap = round(min(tran_console, con, _con_viec(v), max(
                _TRAN_TOI_THIEU, min_charge, float(ph["uoc_usd"]) * _HE_SO_TRAN)), 2)
            het_gio = v.con_giay() < _CHUA_GIAY_CUOI + 60
            if cap < max(min_charge, _TRAN_TOI_THIEU) - 1e-9 or het_gio:
                ly = ("hết giờ" if het_gio else
                      f"trần còn {_usd(cap)} USD (trần console, phần còn của tháng và ngân sách "
                      f"của lượt) < mức actor đòi {_usd(max(min_charge, _TRAN_TOI_THIEU))} USD")
                tk["ghi_chu"].append(f"bình luận {_TEN[p]}: bỏ qua ({ly})")
                v.cap_nhat_phan(ph, trang_thai="loi", ma="NGAN_SACH", so_item=0, usd_so=0.0,
                                ly_do=ly)
                continue
        items, meta, loi, khong_kiem = _chay_actor(v, p, ph, cap, han, min_charge)
        if khong_kiem is not None:
            v.cap_nhat_phan(ph, trang_thai="loi", ma="KHONG_KIEM_DUOC", so_item=0,
                            usd_so=khong_kiem, ly_do=quet_lon._CAU_KHONG_KIEM)
            con = max(0.0, con - khong_kiem)
            continue
        try:
            rows = _doc_bl(p, items)
        except RuntimeError as e:             # shape lạ: báo, không ghi bừa
            loi = loi or A.LoiApify("LOI", str(e)[:250])
        tien = quet_lon._so_tien(p, ph, items, meta)
        con = max(0.0, con - tien)
        tk["usd"] += tien
        if loi is not None:
            tk["ghi_chu"].append(f"bình luận {_TEN[p]}: {A._che_token(str(loi))[:120]}")
        # Ghi kho TRƯỚC khi đánh dấu phần xong: khởi động lại giữa hai bước thì đọc lại run.
        _ghi_bl_kho(ma, luot, ph, rows, thuong_hieu, han, tk,
                    day_du=loi is None and meta.get("ma", "OK") == "OK")
        quet_lon._ket_phan(v, ph, meta, len(items), loi, usd_so=tien)
    tk["usd"] = round(tk["usd"], 4)
    return tk


def _ghi_bl_kho(ma: str, luot: int, ph: dict, rows: list[dict], thuong_hieu: list[str],
                han: float, tk: dict, day_du: bool = True) -> None:
    """`day_du`=False (lỗi, huỷ, hết giờ, hết quota): chỉ bài CÓ bình luận trả về được đánh dấu
    đã cào — bài 0 dòng vì lỗi không bị gạch khỏi lượt sau (review 15/10)."""
    import phan_loai
    bai = ph["bai"]
    theo = _quy_bl(rows, bai)
    dong: list[dict] = []
    da_lay: dict[str, tuple[int, int | None]] = {}
    for b in bai:
        cua = theo.get(b["khoa"]) or []
        thay: set[str] = set()
        for r in cua:
            d = _dong_bl(r, b, thuong_hieu)
            if d["ma"] in thay:
                continue
            thay.add(d["ma"])
            dong.append(d)
        if thay or day_du:
            da_lay[b["khoa"]] = (len(thay), _so_hay_none(b.get("binh_luan")))
    khach = [d for d in dong if not d["cua_thuong_hieu"] and str(d.get("text") or "").strip()]
    tk["nha"] += len(dong) - len(khach)
    if khach:
        tt: dict = {}
        nhan = phan_loai.phan_loai_binh_luan(
            khach, max(0.0, min(120.0, han - time.monotonic() - 20)), tt, song_song=2)
        for d, (s, c) in zip(khach, nhan):
            if s != phan_loai.CHUA:
                d["sac_thai"] = s
            if c != phan_loai.CHUA:
                d["chu_de"] = c
        tk["nhan"] = tt.get("trang_thai") or tk["nhan"]
    moi, cu = K.ghi_binh_luan(ma, luot, dong, da_lay)
    tk["lay"] += len(dong)
    tk["moi"] += moi
    tk["cu"] += cu


def _chay_viec(v) -> tuple[str, str]:
    ts = v.d.get("tham_so") or {}
    ma = str(ts.get("du_an") or "")
    du_an = K.doc_du_an(ma)
    if not du_an:
        return "loi", f"Việc theo dõi {v.ma}: dự án '{ma}' không còn trong kho."
    luot = v.d.get("luot_id")
    if not luot:
        # Ghi id lượt vào sổ việc NGAY: bot khởi động lại thì chạy tiếp đúng lượt này, không
        # mở lượt thứ hai (lượt bỏ dở sẽ chặn lượt mới tới `GIO_BO_DO` giờ).
        luot = K.mo_luot(ma, "theo_doi", ma_viec=v.ma,
                         job_id=str((v.d.get("kenh") or {}).get("job_id") or "") or None)
        with v._khoa:
            v.d["luot_id"] = luot
            v.luu()
    A._NEN.set(True)
    A._HUY.set(v.co_dung)
    ids = {int(i) for i in ts.get("nguon") or []}
    nguon: dict[int, dict] = {}
    tk = {"lay_duoc": 0, "qua_cu": 0, "khong_nhac": 0, "loai_tru": 0, "ai_loai": 0, "giu": 0,
          "ai": ""}
    loi: dict[int, str] = {}
    ghi_chu: list[str] = []
    moi = cu = lam_moi = 0
    bl: dict = {}
    ok: list[int] = []
    loi_chung = None
    usd = 0.0
    try:
        # Đọc LẠI nguồn: nguồn đã tạm dừng/xoá sau khi tạo việc thì không quét. Nguồn đã quét
        # xong ở lần chạy trước khởi động lại (đã dời quet_cuoi) vẫn giữ để đọc lại bài từ đĩa.
        nguon = {int(n["id"]): n for n in K.nguon_toi_han(ma) if int(n["id"]) in ids}
        # Review 15/10: lượt chỉ ghi chi phí vào kho ở `finally` — khởi động lại giữa chừng thì
        # tiền các phần đã xong của việc này chưa nằm trong "đã tiêu tháng": trừ ở đây.
        da_xong = sum(float(ph.get("usd_so") or 0) for _, ph in v.cac_phan()
                      if ph.get("trang_thai") in _KET_PHAN)
        con = max(0.0, float(du_an["tran_usd_thang"] or 0) - K.da_tieu_thang(ma) - da_xong)
        han = v.han_mono(_CHUA_GIAY_CUOI)
        for p in THU_TU:
            for ph in ((v.d.get("nen_tang") or {}).get(p) or {}).get("phan") or []:
                ds = [nguon[i] for i in ph.get("nguon") or [] if i in nguon]
                st = ph.get("trang_thai")
                if st in _KET_PHAN:
                    continue                                  # đã xong: bài đọc lại từ đĩa
                if not ds and st not in ("dang_gui", "dang_chay"):
                    v.cap_nhat_phan(ph, trang_thai="da_huy", ma="BO_QUA", so_item=0, usd_so=0.0,
                                    ly_do="nguồn đã tạm dừng/xoá trên dashboard")
                    continue
                dang_do = st in ("dang_gui", "dang_chay")
                if not dang_do and (v.da_huy() or v.con_giay() < _CHUA_GIAY_CUOI + 30):
                    huy = v.da_huy()
                    ghi_chu.append(f"{_TEN[p]}: dừng trước khi chạy ({'huỷ' if huy else 'hết giờ'})")
                    v.cap_nhat_phan(ph, trang_thai="da_huy" if huy else "loi",
                                    ma="DA_HUY" if huy else "QUA_GIO", so_item=0, usd_so=0.0)
                    continue
                if p == "youtube":
                    try:
                        kq, l = _lay_youtube(ds)
                        _ghi_phan(v, p, ph, kq, l)
                        v.cap_nhat_phan(ph, trang_thai="xong", ma="OK", usd_so=0.0,
                                        so_item=sum(len(x) for x in kq.values()))
                    except Exception as e:
                        if type(e).__name__ == "MatQuyen":
                            raise
                        ly = A._che_token(f"{type(e).__name__}: {e}")[:200]
                        v.cap_nhat_phan(ph, trang_thai="loi", ma="LOI", ly_do=ly, so_item=0,
                                        usd_so=0.0, loi_nguon={str(n["id"]): ly for n in ds})
                    continue
                if dang_do:
                    cap = float(ph.get("tran_usd") or 0) or _TRAN_TOI_THIEU
                else:
                    tran_console = A._tran_nen_tang(p, nen=True)[1]
                    cap = round(min(tran_console, con,
                                    max(_TRAN_TOI_THIEU, float(ph.get("uoc_usd") or 0)
                                        * _HE_SO_TRAN)), 2)
                    if con < max(_TRAN_TOI_THIEU, float(ph.get("uoc_usd") or 0)) - 1e-9:
                        ghi_chu.append(f"{_TEN[p]}: hết ngân sách tháng (còn {_usd(con)} USD)")
                        v.cap_nhat_phan(ph, trang_thai="loi", ma="NGAN_SACH", so_item=0,
                                        usd_so=0.0, ly_do="hết ngân sách tháng của dự án")
                        continue
                con = max(0.0, con - _chay_phan_apify(v, p, ph, ds, cap, han))
        # Bài: đọc từ đĩa (kể cả phần đã xong trước khi bot khởi động lại).
        theo_nguon: dict[int, list] = {}
        for p in THU_TU:
            for d, dt in v.doc_dong(p):
                nid = d.get("_nguon_id")
                if nid is not None:
                    theo_nguon.setdefault(int(nid), []).append((d, dt))
        xong_ids: set[int] = set()
        for _, ph in v.cac_phan():
            for k, x in (ph.get("loi_nguon") or {}).items():
                loi[int(k)] = str(x)
            if ph.get("trang_thai") in ("xong", "mot_phan"):
                xong_ids.update(int(i) for i in ph.get("nguon") or [])
            elif ph.get("trang_thai") == "loi" and ph.get("ma") not in ("NGAN_SACH", "QUA_GIO"):
                for i in ph.get("nguon") or []:
                    loi.setdefault(int(i), str(ph.get("ly_do") or ph.get("ma") or "lỗi"))
        han_ai = time.monotonic() + max(0.0, min(150.0, v.con_giay() - 45))
        rows, tk = chon_bai(du_an, theo_nguon, nguon, han_ai)
        if rows:
            moi, cu = K.ghi_bai(ma, luot, "theo_doi", rows)
        lam_moi = _lam_moi_youtube(ma, luot)
        try:
            bl = _lay_binh_luan(v, du_an, luot, con, han)
        except Exception as e:  # bình luận hỏng không làm hỏng lượt bài
            if type(e).__name__ == "MatQuyen":
                raise
            bl = {"ghi_chu": [f"bình luận lỗi: {A._che_token(f'{type(e).__name__}: {e}')[:150]}"]}
        ok = sorted(i for i in xong_ids if i in nguon and i not in loi)
        K.danh_dau_nguon(ok, {k: x for k, x in loi.items() if k in nguon})
    except Exception as e:
        if type(e).__name__ == "MatQuyen":
            raise
        loi_chung = A._che_token(f"{type(e).__name__}: {e}")[:300]
    finally:
        # Tiền đã tiêu phải vào lượt dù có lỗi gì (review 14/10): không thì "đã tiêu tháng"
        # đếm thiếu và lượt sau quét lại, trả tiền lần nữa.
        if v.run_ids():
            usd = float(v.chot_chi_phi([f"theo dõi {ma}"], sorted(
                {p for p, _ in v.cac_phan() if p not in ("youtube", "binh_luan")}),
                _hom_nay()).get("usd") or 0)
        trang_thai = ("da_huy" if v.da_huy() else "loi" if loi_chung or not ok and nguon
                      else "xong" if not loi and not ghi_chu else "mot_phan")
        try:
            K.dong_luot(luot, trang_thai=trang_thai, so_nguon=len(nguon), so_nguon_loi=len(loi),
                        bai_moi=moi, bai_cap_nhat=cu + lam_moi, chi_phi_usd=usd,
                        ghi_chu="; ".join([*ghi_chu, *_cau_bl(bl)]) or None,
                        loi=(loi_chung or "; ".join(sorted(set(loi.values())))[:500] or None))
        except K.LoiKho as e:
            print(f"[theo_doi] không đóng được lượt {luot}: {e}", flush=True)
    _bao_dashboard(ma, luot)
    if loi_chung:
        return "loi", (f"Theo dõi {du_an['ten']} ({v.ma}) dừng vì lỗi: {loi_chung}. Chi phí thật "
                       f"{_usd(usd)} USD đã ghi vào lượt.")
    try:
        da_tieu = K.da_tieu_thang(ma)
    except K.LoiKho:
        da_tieu = float("nan")
    van_ban = (
        f"Theo dõi {du_an['ten']} ({v.ma}) xong: quét {len(ok)}/{len(nguon)} nguồn, lấy "
        f"{tk['lay_duoc']} bài, giữ {tk['giu']} bài nhắc tới dự án ({moi} mới, {cu} cập nhật"
        + (f"; cập nhật số {lam_moi} video YouTube cũ" if lam_moi else "") + "). "
        f"Bỏ: {tk['qua_cu']} bài cũ hơn {NGAY_GIU} ngày, {tk['khong_nhac']} bài không nhắc "
        "dự án" + (f", {tk['loai_tru']} bài chứa từ loại trừ" if tk["loai_tru"] else "")
        + (f", {tk['ai_loai']} bài AI loại" if tk["ai_loai"] else "") + ". "
        f"Chi phí thật {_usd(usd)} USD; tháng này đã dùng {_usd(da_tieu)}/"
        f"{_usd(float(du_an['tran_usd_thang'] or 0))} USD. Xem chi tiết trên dashboard "
        "social.hapas.vn.")
    if tk["ai"] and tk["ai"] != "đã chạy":
        van_ban += f" Bước AI: {tk['ai']} (bài chưa có nhãn vẫn được giữ theo từ khoá)."
    if loi:
        van_ban += f" {len(loi)} nguồn lỗi: " + "; ".join(sorted(set(loi.values())))[:300] + "."
    if ghi_chu:
        van_ban += " " + "; ".join(ghi_chu) + "."
    if _cau_bl(bl):
        van_ban += " " + "; ".join(_cau_bl(bl)) + "."
    st_viec = {"mot_phan": "xong_mot_phan"}.get(trang_thai, trang_thai)
    return st_viec, van_ban


def _cau_bl(bl: dict) -> list[str]:
    """Câu tóm tắt bước bình luận cho lượt quét + tin nhắn kết quả."""
    if not bl:
        return []
    ra = []
    if bl.get("bai"):
        ra.append(f"bình luận: đọc {bl.get('lay', 0)} bình luận của {bl['bai']} bài "
                  f"({bl.get('moi', 0)} mới"
                  + (f", {bl['nha']} của chính thương hiệu" if bl.get("nha") else "")
                  + f"), {_usd(bl.get('usd') or 0)} USD"
                  + (f", gán nhãn: {bl['nhan']}" if bl.get("nhan") else ""))
    return ra + list(bl.get("ghi_chu") or [])


def _lam_moi_youtube(ma: str, luot: int) -> int:
    """Đọc lại số của video YouTube đã giữ (≤ `NGAY_LAM_MOI_YT` ngày) chưa đọc hôm nay.
    Chỉ cập nhật số (UPDATE riêng) — review 14/10: đi qua upsert đầy đủ thì INSERT thiếu cột
    NOT NULL và hỏng lặng lẽ mỗi ngày."""
    if not A._youtube_co_key():
        return 0
    try:
        cu = K.bai_youtube_can_lam_moi(ma, NGAY_LAM_MOI_YT)
        if not cu:
            return 0
        can = {k["khoa"].split(":", 1)[1] for k in cu}
        so = []
        for d, _dt in _video_youtube(sorted(can)):
            vid = d["link"].rsplit("=", 1)[-1]
            if vid in can:
                so.append({"khoa": f"youtube:{vid}", "xem": d["views"], "thich": d["likes"],
                           "binh_luan": d["comments"], "chia_se": None})
        return K.cap_nhat_so_lieu(ma, luot, so)
    except (A.LoiYouTube, K.LoiKho) as e:
        print(f"[theo_doi] làm mới YouTube lỗi: {A._che_token(str(e))[:120]}", flush=True)
        return 0


def _bao_dashboard(ma: str, luot: int) -> None:
    """Báo dashboard (cùng VPS) có dữ liệu mới để đẩy số xuống trình duyệt ngay. Không có
    dashboard hay lỗi thì thôi — dashboard vẫn tự kiểm định kỳ."""
    import os
    url = (os.environ.get("LANG_NGHE_BAO_URL") or "").strip()
    if not url:
        return
    khoa = (os.environ.get("LANG_NGHE_BAO_KHOA") or "").strip()
    try:
        import requests
        requests.post(url, json={"du_an": ma, "luot": luot}, timeout=3,
                      headers={"X-Lang-Nghe-Khoa": khoa} if khoa else {})
    except Exception as e:  # noqa: BLE001
        print(f"[theo_doi] không báo được dashboard: {type(e).__name__}", flush=True)


# ───────────────────────────── kết quả tìm theo từ khoá → kho ─────────────────────────────
# Lượt `social_listen` (tại chỗ hoặc nền) có từ khoá trùng từ khoá của một dự án thì bài đã giữ
# vào kho với kiểu `tu_khoa`, và tài khoản nổi mà chưa theo dõi thành ĐỀ XUẤT chờ người duyệt
# trên dashboard (Mark không tự thêm nguồn). Vì sao: chưa có danh sách nguồn Kompa (chủ dự án
# để sau), đề xuất từ chính các lượt tìm là cách gom nguồn ban đầu. Chạy luồng nền, mọi lỗi
# chỉ ghi log — không bao giờ làm chậm hay hỏng câu trả lời của social_listen.
DE_XUAT_TOI_DA = 10
DE_XUAT_TOI_THIEU_BAI = 2
DE_XUAT_TOI_THIEU_THAO_LUAN = 50


def _dinh_danh_tai_khoan(d: dict) -> tuple[str, str, str] | None:
    """(nền tảng, định danh nguồn, link) của tài khoản đăng bài; None khi không đủ để thành
    nguồn theo dõi (Facebook: actor tìm kiếm không trả URL trang ổn định; Threads chưa hỗ
    trợ theo dõi)."""
    p = str(d.get("platform") or "")
    u = str(d.get("username") or "").strip().lstrip("@").lower()
    if p == "tiktok" and u:
        return p, u, f"https://www.tiktok.com/@{u}"
    if p == "instagram" and u:
        return p, u, f"https://www.instagram.com/{u}/"
    if p == "youtube":
        cid = str(d.get("_kenh_id") or "")
        if re.fullmatch(r"UC[\w-]{22}", cid):
            return p, cid, f"https://www.youtube.com/channel/{cid}"
    return None


def _ban_sao_tu_khoa(hits: list) -> list[tuple[dict, datetime.datetime]]:
    """Chép đúng phần cần ghi của từng bài (đồng bộ, nhanh) để luồng nền không đọc dict mà
    `_handle` còn đang sửa."""
    import phan_loai
    ra = []
    for d, dt in hits:
        if not dt or not d.get("link"):
            continue
        goc = d.get("__goc") if isinstance(d.get("__goc"), dict) else {}
        kenh_id = ((goc.get("search") or {}).get("snippet") or {}).get("channelId") \
            if isinstance(goc.get("search"), dict) else None
        sac, cd = d.get("_sac_thai"), d.get("_chu_de")
        ra.append(({
            "platform": d.get("platform"), "kenh": d.get("kenh"), "username": d.get("username"),
            "followers": d.get("followers"), "views": d.get("views"), "likes": d.get("likes"),
            "comments": d.get("comments"), "shares": d.get("shares"),
            "hashtags": d.get("hashtags"), "text": d.get("text"), "link": d.get("link"),
            "_khop": bool(d.get("_khop")), "_ma_ai": d.get("_ma_ai"), "_kenh_id": kenh_id,
            "_goc_id": goc.get("id") if isinstance(goc.get("id"), (str, int)) else None,
            "_sac_thai": None if not sac or sac == phan_loai.CHUA else sac,
            "_chu_de": None if not cd or cd == phan_loai.CHUA else cd,
        }, dt))
    return ra


def _de_xuat_tu(ban: list, da_co: set[tuple[str, str]], queries: list[str]) -> list[dict]:
    """Tài khoản nổi trong lượt tìm mà chưa nằm trong danh sách nguồn -> đề xuất."""
    gom: dict[tuple[str, str], dict] = {}
    for d, _dt in ban:
        x = _dinh_danh_tai_khoan(d)
        if not x or (x[0], x[1]) in da_co:
            continue
        g = gom.setdefault((x[0], x[1]), {"nen_tang": x[0], "dinh_danh": x[1], "link": x[2],
                                          "ten": str(d.get("kenh") or x[1])[:200], "so_bai": 0,
                                          "thao_luan": 0})
        g["so_bai"] += 1
        g["thao_luan"] += 1 + int(_so_hay_none(d.get("comments")) or 0)
    ngay = datetime.datetime.now(_VN).strftime("%d/%m")
    ra = [g for g in gom.values() if g["so_bai"] >= DE_XUAT_TOI_THIEU_BAI
          or g["thao_luan"] >= DE_XUAT_TOI_THIEU_THAO_LUAN]
    ra.sort(key=lambda g: (-g["thao_luan"], -g["so_bai"], g["dinh_danh"]))
    for g in ra:
        g["ly_do"] = (f"{g['so_bai']} bài, {g['thao_luan']} thảo luận khi Mark tìm "
                      f"'{', '.join(queries)[:60]}' ngày {ngay}")
    return ra[:DE_XUAT_TOI_DA]


def _du_an_khop(queries: list[str], cac: list[dict]) -> list[dict]:
    """Dự án có ít nhất một từ khoá nằm trong câu tìm (so khớp bỏ dấu, không phân biệt hoa
    thường): tìm "túi hapas" thì ghi vào dự án có từ khoá "hapas"."""
    qn = [A._norm(q) for q in queries if str(q).strip()]
    return [x for x in cac
            if any(A._norm(k) and A._norm(k) in q for k in (x.get("tu_khoa") or []) for q in qn)]


def luu_tu_khoa(queries: list[str], ban: list) -> dict:
    """Ghi bản sao bài (từ `_ban_sao_tu_khoa`) vào mọi dự án khớp. -> {mã dự án: (mới, cập
    nhật, đề xuất mới)}. Ném LoiKho nếu kho hỏng — bên gọi nền tự nuốt."""
    ra: dict[str, tuple[int, int, int]] = {}
    if not ban:
        return ra
    for x in _du_an_khop(queries, K.du_an_dang_bat()):
        ma = x["ma"]
        nguon = K.nguon_cua_du_an(ma)
        theo = {(n["nen_tang"], _chuan_dinh_danh(n["nen_tang"], n["dinh_danh"])): int(n["id"])
                for n in nguon}
        rows, thay = [], set()
        for d, dt in ban:
            khoa = _khoa_bai(str(d["platform"]), str(d["link"]), {"id": d.get("_goc_id")})
            if khoa in thay:
                continue
            thay.add(khoa)
            tk = _dinh_danh_tai_khoan(d)
            rows.append({
                "khoa": khoa, "nen_tang": d["platform"],
                "nguon_id": theo.get((tk[0], tk[1])) if tk else None,
                "link": d["link"], "tac_gia": str(d.get("kenh") or "")[:200],
                "tai_khoan": str(d.get("username") or "")[:200],
                "followers": _so_hay_none(d.get("followers")), "dang_luc": dt,
                "noi_dung": str(d.get("text") or "")[:1000],
                "hashtag": str(d.get("hashtags") or "")[:500], "khop_tu_khoa": d["_khop"],
                "sac_thai": d["_sac_thai"], "chu_de": d["_chu_de"],
                "ly_do_giu": str(d.get("_ma_ai") or "khop_tu_khoa")[:60],
                "xem": _so_hay_none(d.get("views")), "thich": _so_hay_none(d.get("likes")),
                "binh_luan": _so_hay_none(d.get("comments")),
                "chia_se": _so_hay_none(d.get("shares")),
            })
        luot = K.mo_luot(ma, "tu_khoa")
        try:
            moi, cu = K.ghi_bai(ma, luot, "tu_khoa", rows)
            dx = K.ghi_de_xuat(ma, _de_xuat_tu(ban, set(theo), queries))
            K.dong_luot(luot, trang_thai="xong", bai_moi=moi, bai_cap_nhat=cu,
                        ghi_chu=(f"tìm theo từ khoá '{', '.join(queries)[:150]}'; {dx} đề xuất "
                                 "nguồn mới; chi phí ở sổ chi phí quét, không tính vào trần "
                                 "theo dõi"))
        except K.LoiKho as e:
            K.dong_luot(luot, trang_thai="loi", loi=str(e))
            raise
        _bao_dashboard(ma, luot)
        ra[ma] = (moi, cu, dx)
    return ra


def luu_tu_khoa_nen(queries: list[str], hits: list) -> None:
    """Gọi từ `social_listen`/`quet_lon`: chép dữ liệu rồi ghi kho ở luồng nền. Không bao giờ
    ném lỗi ra bên gọi."""
    import importlib.util
    import os
    import threading
    if (os.environ.get("LANG_NGHE_GHI_TU_KHOA") or "1").strip() == "0" \
            or importlib.util.find_spec("psycopg") is None:
        return                            # chưa cài kho (máy dev, bộ thử) hoặc chủ agent tắt
    try:
        ban = _ban_sao_tu_khoa(hits)
        qs = [str(q) for q in queries or [] if str(q).strip()]
    except Exception as e:  # noqa: BLE001
        print(f"[theo_doi] không chép được bài tìm theo từ khoá: {type(e).__name__}", flush=True)
        return
    if not ban or not qs:
        return

    def chay():
        try:
            luu_tu_khoa(qs, ban)
        except Exception as e:  # noqa: BLE001 — kho chưa cài/hỏng: social_listen vẫn chạy
            print(f"[theo_doi] không ghi được kho lắng nghe: {A._che_token(str(e))[:150]}",
                  flush=True)
    threading.Thread(target=chay, name="luu_tu_khoa", daemon=True).start()
