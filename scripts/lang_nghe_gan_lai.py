"""Gán lại nhãn bình luận đã nằm trong kho `lang_nghe` — script MỘT LẦN (chẩn đoán 16/10/2026).

Vì sao cần: lượt `/theodoi` chỉ gán nhãn bình luận VỪA cào và bỏ qua bình luận đã có nhãn
(`lang_nghe_db.da_gan_nhan`), nên hai bản sửa ngày 16/10 không tự áp cho dữ liệu cũ:
  (a) Trả lời của fanpage nhà: nhận tài khoản nhà nay so cả dạng gọn của chủ bài ("HAPAS -
      Chính Hãng Giá Tốt" = "hapaschinhhanggiatot"). Bình luận dưới bài kênh nhà được tính lại
      `cua_thuong_hieu` bằng ĐÚNG hàm của lượt cào (`phan_loai.la_binh_luan_nha`); dòng đang
      `hop_le` thành `thuong_hieu` và bỏ sắc thái/chủ đề (tiếng brand không gán nhãn).
  (b) Prompt gán nhãn mới (chủ đề MG, khen + hỏi giá, lời của shop, emoji cuối câu): gán lại
      bằng ĐÚNG `phan_loai.phan_loai_binh_luan` cho các bình luận `hop_le` được chọn:
        • mở đầu bằng số dự thi ("271 – …", "110: …");
        • nằm dưới bài trông như minigame (chú thích có minigame/giveaway/dự thi/trúng thưởng…,
          hoặc ≥ 30% bình luận hợp lệ của bài mở đầu bằng số dự thi);
        • đang "Trung lập" mà có lời khen rõ (đẹp, xinh, dễ thương, tuyệt vời…);
        • `--tat-ca`: MỌI bình luận `hop_le` của dự án.
      Lô model hỏng / hết giờ thì dòng đó GIỮ nhãn cũ (fail-open như lượt cào).
      `--den-luot N` (17/10/2026): mọi bộ chọn của (b) chỉ lấy bình luận CÓ THỂ còn nhãn của
      prompt cũ — bình luận thấy lần đầu từ lượt N+1 đã gán bằng prompt mới của PR #62 (deploy
      17/10 00:46, lượt 9 bắt đầu 00:51): `--tat-ca` không lọc chọn 12.527 dòng / 126 lượt
      model, trong đó 7.202 dòng của lượt ≥ 9. Chọn khi MỘT trong ba nhánh đúng (`nhanh_luot`):
        • `luot_id ≤ N`;
        • `luot_id` NULL (lượt đã bị xoá) — không chứng minh được là prompt mới → coi là CŨ;
        • `thay_lan_dau` TRƯỚC giờ bắt đầu lượt N+1 (`SQL_MOC_LUOT`). Soát 17/10/2026 (M1):
          `luot_id` là lượt cào GẦN NHẤT (upsert ghi `EXCLUDED.luot_id`), còn `/theodoi` không
          gửi model lại bình luận đã có nhãn — bình luận gán ở lượt ≤ N rồi cào lại ở lượt sau
          mang `luot_id` mới mà nhãn vẫn của prompt cũ. Bản đầu chỉ ĐẾM nhóm này rồi bỏ sót.
      Chạy thử in số dòng của từng nhánh. Bài minigame vẫn xét trên MỌI bình luận của bài (lọc
      lượt không làm lệch tỉ lệ số dự thi). Bước (a) không lọc (luật, không gọi model).
      27/10/2026 (định nghĩa sắc thái của MKT): model nhận KÈM bài chứa bình luận (đầu nội dung +
      hashtag) và chuỗi brand của dự án — y như việc nền `gan_nhan_nen.gan_lo_bl`. Prompt mới đọc
      bài để hiểu bình luận đáp lại gì (hùa theo bài chê brand, bình luận dưới video KOL); bản
      trước gửi trơn chữ bình luận nên gán lại sẽ kém hơn việc nền. Cột `san_pham` (MÓN) KHÔNG
      đổi ở đây — dashboard chỉ đọc MÓN của dòng hỏi mua, dòng mới thành hỏi mua lùi về chữ.

An toàn:
  • Mặc định CHẠY THỬ: mọi truy vấn trong MỘT giao dịch READ ONLY, không gọi model, không ghi
    gì; in số dòng, mẫu (tác giả đã băm) và ước tính số lượt gọi model. `--thu N` gọi model cho
    tối đa N dòng (một lô) để xem trước nhãn mới — vẫn không ghi gì; in bảng lật sắc thái cũ →
    mới và mẫu lật = → + / − → = để MKT soát trước khi --ap-dung (27/10/2026).
  • `--ap-dung --sao-luu <tệp>`: ghi tệp hoàn tác (giá trị cũ + mới của từng dòng, theo du_an,
    khoa_bai, ma) TRƯỚC, rồi UPDATE trong MỘT giao dịch cho mỗi lô ≤ 100 dòng. Mỗi UPDATE chỉ
    sửa đúng dòng mà giá trị hiện tại còn y như lúc đọc — dòng vừa bị lượt quét khác sửa thì bỏ
    qua, không đè. `cap_nhat_cuoi = now()` để đồng bộ BigQuery (theo mốc) lấy lại dòng đã sửa.
  • `--hoan-tac <tệp>`: trả giá trị cũ cho các dòng CÒN mang đúng giá trị script đã ghi.
  • Gọi model TUẦN TỰ từng lô 100 (quota model dùng chung với bot chính và meeting agent).

Chạy trên VPS bằng user `mark` (kho nối qua Unix socket + peer, không mật khẩu), venv và
`.env` của Mark — gán nhãn đi đúng đường lease model như `/theodoi`. Chạy SAU khi bản code mới
của Mark đã lên VPS: lượt quét chạy bản cũ sẽ ghi lại `loai = hop_le` cho trả lời fanpage nhà.

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_gan_lai.py hapas                 # chạy thử
    sudo -u mark $PY scripts/lang_nghe_gan_lai.py hapas --thu 30        # xem trước nhãn mới
    sudo -u mark $PY scripts/lang_nghe_gan_lai.py hapas --buoc b --tat-ca --den-luot 8   # chạy thử
    sudo -u mark $PY scripts/lang_nghe_gan_lai.py hapas --buoc b --tat-ca --den-luot 8 \
        --ap-dung --sao-luu .audit/gan-lai-1710-den-luot-8.jsonl
    sudo -u mark $PY scripts/lang_nghe_gan_lai.py hapas --ap-dung --sao-luu .audit/gan-lai-1610.jsonl
    sudo -u mark $PY scripts/lang_nghe_gan_lai.py hapas --hoan-tac .audit/gan-lai-1610.jsonl
    # 27/10/2026 (sắc thái MKT): N = id lượt quét CUỐI còn chạy prompt cũ (trước deploy).
    sudo -u mark $PY scripts/lang_nghe_gan_lai.py hapas --buoc b --tat-ca --den-luot N --thu 100
    sudo -u mark $PY scripts/lang_nghe_gan_lai.py hapas --buoc b --tat-ca --den-luot N \
        --ap-dung --sao-luu .audit/gan-lai-2710-sac-thai.jsonl
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import pathlib
import re
import sys
import unicodedata

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

import lang_nghe_db as K
import phan_loai as P

LO = P._LO                      # 100 bình luận mỗi lượt gọi model — như lượt cào
HAN_LO_GIAY = 180.0             # hạn một lô model
COT = ("loai", "ly_do_loc", "sac_thai", "chu_de", "cua_thuong_hieu")
TI_LE_SO_DU_THI = 0.3           # bài có ≥ 30% bình luận mở đầu bằng số dự thi = bài minigame
TOI_THIEU_BL_MINIGAME = 5

# Mọi câu SQL mang thẻ `/* gl:<tên> */` — bộ thử nhận diện câu theo thẻ (kho giả).
SQL_CHI_DOC = "SET TRANSACTION READ ONLY"
SQL_DU_AN = "/* gl:du_an */ SELECT ma, ten, tu_khoa, boi_canh FROM du_an WHERE ma = %s"
SQL_BL_NHA = (
    "/* gl:bl_nha */ SELECT b.khoa_bai, b.ma, b.tac_gia, b.noi_dung, b.loai, b.ly_do_loc, "
    "b.sac_thai, b.chu_de, b.cua_thuong_hieu, p.tai_khoan AS bai_tai_khoan, "
    "p.tac_gia AS bai_tac_gia FROM binh_luan b "
    "JOIN bai p ON p.du_an = b.du_an AND p.khoa = b.khoa_bai "
    "JOIN nguon n ON n.id = p.nguon_id "
    "WHERE b.du_an = %s AND n.loai = 'kenh_nha' AND NOT b.cua_thuong_hieu "
    "ORDER BY b.khoa_bai, b.ma")
SQL_BL_HOP_LE = (
    "/* gl:bl_hop_le */ SELECT b.khoa_bai, b.ma, b.tac_gia, b.noi_dung, b.thich, b.loai, "
    "b.ly_do_loc, b.sac_thai, b.chu_de, b.cua_thuong_hieu, b.luot_id, b.thay_lan_dau, "
    "p.noi_dung AS bai_noi_dung, left(p.hashtag, 120) AS bai_hashtag "
    "FROM binh_luan b JOIN bai p ON p.du_an = b.du_an AND p.khoa = b.khoa_bai "
    "WHERE b.du_an = %s AND b.loai = 'hop_le' ORDER BY b.khoa_bai, b.ma")
# Một dòng, chỉ khi giá trị hiện tại còn đúng `cu` (khoá chính + so từng cột).
SQL_SUA = (
    "/* gl:sua */ UPDATE binh_luan SET loai = %s, ly_do_loc = %s, sac_thai = %s, chu_de = %s, "
    "cua_thuong_hieu = %s, cap_nhat_cuoi = now() "
    "WHERE du_an = %s AND khoa_bai = %s AND ma = %s AND loai = %s "
    "AND ly_do_loc IS NOT DISTINCT FROM %s AND sac_thai IS NOT DISTINCT FROM %s "
    "AND chu_de IS NOT DISTINCT FROM %s AND cua_thuong_hieu = %s")
# Giờ bắt đầu của lượt ĐẦU TIÊN sau `--den-luot N` (id lượt tăng chung mọi dự án/kiểu) — bình
# luận thấy lần đầu trước mốc đó vẫn được chọn dù `luot_id > N` (cào lại ở lượt sau, nhãn còn cũ).
SQL_MOC_LUOT = "/* gl:moc_luot */ SELECT min(bat_dau) AS bat_dau FROM luot_quet WHERE id > %s"

# Số dự thi đầu câu: 1–4 chữ số, không phải ngày/số thập phân ("20/10", "8.3").
_RE_SO_DU_THI = re.compile(r"^(?:#|s[ốo]\s*)?\d{1,4}(?!\d)(?![/.,:]\d)")
# So trên bản BỎ DẤU của chú thích bài.
_RE_BAI_MINIGAME = re.compile(
    r"\b(mini ?game|give ?away|du thi|so du thi|trung thuong|nguoi may man|chon ngau nhien|"
    r"cong bo ket qua|trung giai|giai thuong|(binh luan|comment|cmt)\b.{0,80}"
    r"\b(nhan qua|phan qua|qua tang|tang qua))\b")
# So trên bản CÓ DẤU (chữ thường, NFC): "mê" khác "mẹ" — bản bỏ dấu thì trùng.
_RE_KHEN = re.compile(
    r"(?<!\w)(đẹp|xinh|xink|dễ thương|đáng yêu|đáng iu|cute|tuyệt vời|tuyệt|xuất sắc|ưng|"
    r"thích|mê|xịn|đỉnh|sang trọng|sang chảnh|tinh tế|chất lượng|thơm|ấm lòng|"
    r"dep|de thuong|dang yeu|tuyet voi|thich)(?!\w)")


def _nfc(s) -> str:
    return unicodedata.normalize("NFC", " ".join(str(s or "").split())).lower()


def _bo_dau(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").replace("đ", "d").replace("Đ", "D"))
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().split())


def bam(tac_gia) -> str:
    """Tác giả trong bản in: băm, không in tên thật."""
    return "#" + hashlib.sha1(str(tac_gia or "").encode("utf-8")).hexdigest()[:8]


def la_so_du_thi(text) -> bool:
    return bool(_RE_SO_DU_THI.match(_nfc(text)))


def la_bai_minigame(chu_thich) -> bool:
    return bool(_RE_BAI_MINIGAME.search(_bo_dau(chu_thich)))


def co_loi_khen(text) -> bool:
    return bool(_RE_KHEN.search(_nfc(text)))


# ───────────────────────────── đọc + chọn ─────────────────────────────
def doc_kho(ma: str, den_luot: int | None = None) -> tuple[dict | None, list[dict], list[dict],
                                                          datetime.datetime | None]:
    """(dự án, bình luận chưa là thương hiệu dưới bài kênh nhà, bình luận hop_le, giờ bắt đầu lượt
    đầu tiên sau `den_luot` — None khi không lọc / chưa có lượt nào sau) — MỘT giao dịch READ
    ONLY."""
    with K.ket_noi() as c:
        c.execute(SQL_CHI_DOC)
        du_an = c.execute(SQL_DU_AN, (ma,)).fetchone()
        if not du_an:
            return None, [], [], None
        nha = list(c.execute(SQL_BL_NHA, (ma,)).fetchall())
        hop_le = list(c.execute(SQL_BL_HOP_LE, (ma,)).fetchall())
        moc = None
        if den_luot is not None:
            moc = (c.execute(SQL_MOC_LUOT, (den_luot,)).fetchone() or {}).get("bat_dau")
    return du_an, nha, hop_le, moc


def nhanh_luot(r: dict, den_luot: int, moc: datetime.datetime | None) -> str | None:
    """Nhánh làm dòng được chọn dưới `--den-luot` ("luot_cu" | "luot_null" | "thay_truoc"); None =
    bỏ (thấy lần đầu từ lượt N+1, đã gán bằng prompt mới). `moc`: giờ bắt đầu lượt N+1 — None khi
    chưa có lượt nào sau N (khi đó không thể có `luot_id > N`). `luot_id` NULL: lượt đã bị xoá
    (ON DELETE SET NULL), không chứng minh được là prompt mới → coi là cũ."""
    x = r.get("luot_id")
    if x is None:
        return "luot_null"
    if int(x) <= den_luot:
        return "luot_cu"
    # `luot_id` là lượt cào GẦN NHẤT, không phải lượt gán nhãn: bình luận gán ở lượt ≤ N rồi được
    # cào lại sau vẫn còn nhãn cũ (`/theodoi` không gửi model lại dòng đã có nhãn) — nhận ra nhờ
    # giờ thấy lần đầu (soát 17/10/2026, M1).
    t = r.get("thay_lan_dau")
    if moc is not None and t is not None and t < moc:
        return "thay_truoc"
    return None


def trong_luot(r: dict, den_luot: int | None, moc: datetime.datetime | None = None) -> bool:
    """Dòng có thể còn nhãn của prompt cũ dưới `--den-luot` (`nhanh_luot`); None = không lọc."""
    return den_luot is None or nhanh_luot(r, den_luot, moc) is not None


def _dong(r: dict, cu: dict, moi: dict, buoc: str, ly_do: str) -> dict:
    return {"khoa_bai": r["khoa_bai"], "ma": r["ma"], "tac_gia": r.get("tac_gia") or "",
            "noi_dung": r.get("noi_dung") or "", "thich": r.get("thich"), "cu": cu,
            "moi": moi, "buoc": buoc, "ly_do": ly_do, "luot_id": r.get("luot_id"),
            "thay_lan_dau": r.get("thay_lan_dau"),
            # Ngữ cảnh bài cho model (27/10/2026) — KHÔNG vào tệp hoàn tác (`ghi_lo` chọn khoá).
            "bai_noi_dung": r.get("bai_noi_dung"), "bai_hashtag": r.get("bai_hashtag")}


def chon_thuong_hieu(du_an: dict, rows: list[dict]) -> list[dict]:
    """(a) Bình luận dưới bài kênh nhà mà hàm nhận tài khoản nhà (bản sửa) nói là của brand."""
    th = P.thuong_hieu_du_an(du_an)
    ra = []
    for r in rows:
        bai = {"nguon_loai": "kenh_nha", "tai_khoan": r.get("bai_tai_khoan"),
               "tac_gia": r.get("bai_tac_gia")}
        if r.get("cua_thuong_hieu") or not P.la_binh_luan_nha(r.get("tac_gia"), bai, th):
            continue
        cu = {k: r.get(k) for k in COT}
        moi = dict(cu, cua_thuong_hieu=True)
        if cu["loai"] == "hop_le":
            moi.update(loai="thuong_hieu", ly_do_loc=None, sac_thai=None, chu_de=None)
        ra.append(_dong(r, cu, moi, "a", "tra_loi_cua_kenh_nha"))
    return ra


def chon_gan_lai(rows: list[dict], tat_ca: bool = False, bo: set | None = None,
                 den_luot: int | None = None,
                 moc: datetime.datetime | None = None) -> list[dict]:
    """(b) Bình luận hop_le cần gán lại; `bo` = khoá (khoa_bai, ma) bước (a) đã chuyển thành
    thương hiệu. `moi` để trống — điền sau khi gọi model. `den_luot` (+ `moc` = giờ bắt đầu lượt
    N+1): mọi bộ chọn chỉ lấy dòng `trong_luot` — bài minigame vẫn xét trên MỌI bình luận của bài
    (lọc trước thì bài có 20 bình luận dự thi ở lượt mới + 1 bình luận cũ chỉ còn 1 dòng, dưới
    ngưỡng 5 — không nhận ra)."""
    bo = bo or set()
    rows = [r for r in rows if (r["khoa_bai"], r["ma"]) not in bo]
    theo_bai: dict[str, list[dict]] = {}
    for r in rows:
        theo_bai.setdefault(r["khoa_bai"], []).append(r)
    bai_mg = set()
    for kb, cac in theo_bai.items():
        so = sum(1 for r in cac if la_so_du_thi(r.get("noi_dung")))
        if (la_bai_minigame(cac[0].get("bai_noi_dung"))
                or (len(cac) >= TOI_THIEU_BL_MINIGAME and so >= TI_LE_SO_DU_THI * len(cac))):
            bai_mg.add(kb)
    ra = []
    for r in rows:
        if not str(r.get("noi_dung") or "").strip() or not trong_luot(r, den_luot, moc):
            continue
        if la_so_du_thi(r.get("noi_dung")):
            ly = "so_du_thi"
        elif r["khoa_bai"] in bai_mg:
            ly = "bai_minigame"
        elif r.get("sac_thai") == P.SAC_THAI["="] and co_loi_khen(r.get("noi_dung")):
            ly = "khen_ma_trung_lap"
        elif tat_ca:
            ly = "tat_ca"
        else:
            continue
        ra.append(_dong(r, {k: r.get(k) for k in COT}, {}, "b", ly))
    return ra


def can_model(d: dict) -> bool:
    return P._luat(d.get("noi_dung") or "") is None


def uoc_luot_model(dong: list[dict]) -> tuple[int, int]:
    """-> (số dòng cần model, số lượt gọi model) — lô `LO`, như lượt cào."""
    n = sum(1 for d in dong if can_model(d))
    return n, math.ceil(n / LO)


def chia_lo(dong: list[dict]) -> list[list[dict]]:
    """Dòng cần model chia lô `LO` (mỗi lô đúng MỘT lượt gọi model); dòng gán bằng luật đi lô
    riêng, không gọi model."""
    can = [d for d in dong if can_model(d)]
    luat = [d for d in dong if not can_model(d)]
    return ([can[i:i + LO] for i in range(0, len(can), LO)]
            + [luat[i:i + LO] for i in range(0, len(luat), LO)])


def gan_nhan(lo: list[dict], brand: str = "") -> tuple[list[dict], dict]:
    """Gọi đúng bộ gán nhãn của việc nền cho một lô — kèm bài chứa bình luận và `brand`
    (`gan_nhan_nen.brand_du_an`). -> (dòng có nhãn mới KHÁC nhãn cũ, thống kê). Dòng chưa gán
    được thì giữ nhãn cũ."""
    import gan_nhan_nen as N
    tt: dict = {}
    nhan = P.phan_loai_binh_luan(
        [{"text": d["noi_dung"], "likes": int(d.get("thich") or 0),
          "ngu_canh_bai": N.ngu_canh_bai(d)} for d in lo],
        HAN_LO_GIAY, tt, song_song=1, brand=brand)
    doi, dem = [], {"chua_gan": 0, "khong_doi": 0}
    ma_tran: dict[tuple, int] = {}
    for d, (s, c) in zip(lo, nhan):
        if s == P.CHUA or c == P.CHUA:
            dem["chua_gan"] += 1
            continue
        cap = (d["cu"].get("sac_thai") or "—", s)
        ma_tran[cap] = ma_tran.get(cap, 0) + 1
        moi = dict(d["cu"], sac_thai=s, chu_de=c)
        if moi == d["cu"]:
            dem["khong_doi"] += 1
            continue
        doi.append(dict(d, moi=moi))
    return doi, {**dem, "ma_tran": ma_tran, "trang_thai": tt.get("trang_thai") or ""}


_NGAN = {P.SAC_THAI["+"]: "+", P.SAC_THAI["-"]: "-", P.SAC_THAI["="]: "="}
#: Hai kiểu lật MKT cần soi trước khi --ap-dung (27/10/2026): luật "thiện cảm là +" có thể kéo
#: bình luận trung lập lên "+", luật "một từ tiêu cực không đủ" có thể kéo lời chê xuống "=".
_LAT_SOI = ((P.SAC_THAI["="], P.SAC_THAI["+"]), (P.SAC_THAI["-"], P.SAC_THAI["="]))


def in_ma_tran(dem: dict, doi: list[dict], mau: int, in_ra=print) -> None:
    """Bảng lật sắc thái cũ → mới của các dòng gán được + vài mẫu =→+ và −→= (tác giả đã băm)."""
    mt = dem.get("ma_tran") or {}
    if not mt:
        return
    cot = ("+", "=", "-")
    in_ra("    Lật sắc thái (hàng = cũ, cột = mới):   " + "  ".join(f"{c:>5}" for c in cot))
    for cu in sorted({k[0] for k in mt}, key=lambda x: (x not in _NGAN, x)):
        so = [mt.get((cu, m), 0) for m in (P.SAC_THAI["+"], P.SAC_THAI["="], P.SAC_THAI["-"])]
        in_ra(f"      {_NGAN.get(cu, cu):<34}" + "  ".join(f"{n:>5}" for n in so))
    for cu, moi in _LAT_SOI:
        lat = [d for d in doi if d["cu"].get("sac_thai") == cu and d["moi"]["sac_thai"] == moi]
        in_ra(f"    Mẫu {_NGAN[cu]} → {_NGAN[moi]}: {len(lat)} dòng")
        for d in lat[:mau]:
            in_ra(_mau(d))


# ───────────────────────────── ghi + hoàn tác ─────────────────────────────
def _tham_so_sua(ma: str, d: dict, dat: dict, kiem: dict) -> tuple:
    return (*[dat[k] for k in COT], ma, d["khoa_bai"], d["ma"], *[kiem[k] for k in COT])


def ghi_lo(ma: str, lo: list[dict], so_luu, nguoc: bool = False) -> tuple[int, int]:
    """Ghi một lô trong MỘT giao dịch. `so_luu` (tệp hoàn tác đang mở) nhận các dòng TRƯỚC khi
    UPDATE. `nguoc`: hoàn tác (đặt `cu`, kiểm `moi`). -> (đã sửa, bỏ qua vì dòng đã đổi)."""
    if not lo:
        return 0, 0
    if so_luu is not None:
        for d in lo:
            so_luu.write(json.dumps({"du_an": ma, "khoa_bai": d["khoa_bai"], "ma": d["ma"],
                                     "buoc": d["buoc"], "ly_do": d["ly_do"], "cu": d["cu"],
                                     "moi": d["moi"]}, ensure_ascii=False) + "\n")
        so_luu.flush()
        os.fsync(so_luu.fileno())
    sua = 0
    with K.ket_noi() as c:
        for d in lo:
            dat, kiem = (d["cu"], d["moi"]) if nguoc else (d["moi"], d["cu"])
            sua += int(c.execute(SQL_SUA, _tham_so_sua(ma, d, dat, kiem)).rowcount or 0)
    return sua, len(lo) - sua


def doc_tep_hoan_tac(tep: str) -> tuple[dict, list[dict]]:
    dau, dong = {}, []
    with open(tep, encoding="utf-8") as f:
        for i, x in enumerate(f):
            if not x.strip():
                continue
            r = json.loads(x)
            if i == 0 and r.get("loai_dong") == "dau":
                dau = r
            elif all(k in r for k in ("khoa_bai", "ma", "cu", "moi")):
                dong.append(r)
    return dau, dong


# ───────────────────────────── in ─────────────────────────────
def _mau(d: dict) -> str:
    t = P._TAG_RE.sub("@…", " ".join(str(d.get("noi_dung") or "").split()))
    t = t if len(t) <= 90 else t[:89] + "…"
    s = f"  [{bam(d.get('tac_gia'))}] \"{t}\" ({d['cu'].get('sac_thai') or '—'} / " \
        f"{d['cu'].get('chu_de') or '—'}"
    if d.get("moi"):
        s += f" → {d['moi'].get('sac_thai') or '—'} / {d['moi'].get('chu_de') or '—'}"
        if d["moi"].get("loai") != d["cu"].get("loai"):
            s += f"; {d['cu'].get('loai')} → {d['moi'].get('loai')}"
    return s + ")"


def _dem(dong: list[dict], khoa: str) -> str:
    c: dict[str, int] = {}
    for d in dong:
        c[d[khoa]] = c.get(d[khoa], 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]))


def _chuan_bi_model() -> None:
    """Nạp `.env` của Mark và chỉ đường tới Hermes như `brain.py` — `phan_loai` gọi model qua
    `tai_khoan_ai` (lease console, hỏng thì máy) đúng như lượt `/theodoi`."""
    from config import config
    os.environ.setdefault("HERMES_HOME", config.hermes_home)
    os.environ.setdefault("PYTHONUTF8", "1")
    if config.hermes_agent_dir not in sys.path:
        sys.path.insert(0, config.hermes_agent_dir)


def _cau_loc_luot(den: int | None, b_khong_loc: list[dict],
                  moc: datetime.datetime | None) -> str:
    """Dòng mô tả bộ lọc lượt của (b) kèm số dòng từng nhánh của `nhanh_luot`. `b_khong_loc`: các
    dòng bộ chọn lấy khi KHÔNG lọc."""
    if den is None:
        return ("Bộ lọc lượt (b): KHÔNG — mọi lượt quét (thêm --den-luot N để chỉ lấy bình luận "
                "của lượt ≤ N).")
    dem = {"luot_cu": 0, "luot_null": 0, "thay_truoc": 0, None: 0}
    for d in b_khong_loc:
        dem[nhanh_luot(d, den, moc)] += 1
    # Số dòng TỪNG nhánh (soát 17/10/2026): người chạy thấy ngay nhánh "cào lại" lớn cỡ nào trước
    # khi --ap-dung, thay vì một con số gộp.
    moc_s = (f"lượt {den + 1} bắt đầu {moc.isoformat(timespec='minutes')}" if moc is not None
             else f"chưa có lượt nào sau lượt {den}")
    return (f"Bộ lọc lượt (b): --den-luot {den} — chọn {len(b_khong_loc) - dem[None]} dòng có thể "
            f"còn nhãn prompt cũ: luot_id ≤ {den}: {dem['luot_cu']}; luot_id NULL (lượt đã xoá, "
            f"tính là cũ): {dem['luot_null']}; luot_id > {den} nhưng thấy lần đầu TRƯỚC lượt "
            f"{den + 1} (cào lại ở lượt sau, nhãn vẫn cũ): {dem['thay_truoc']} ({moc_s}). Bỏ "
            f"{dem[None]} dòng thấy lần đầu từ lượt {den + 1} (đã gán bằng prompt mới).")


def chay(ns, in_ra=print) -> int:
    ma = ns.du_an.strip().lower()
    if ns.hoan_tac:
        dau, dong = doc_tep_hoan_tac(ns.hoan_tac)
        if dau.get("du_an") and dau["du_an"] != ma:
            in_ra(f"Tệp hoàn tác của dự án '{dau['du_an']}', không phải '{ma}' — dừng.")
            return 2
        dong = [d for d in reversed(dong) if d.get("du_an", ma) == ma]
        sua = bo_qua = 0
        for i in range(0, len(dong), LO):
            a, b = ghi_lo(ma, dong[i:i + LO], None, nguoc=True)
            sua, bo_qua = sua + a, bo_qua + b
        in_ra(f"Hoàn tác {ma}: trả lại {sua}/{len(dong)} dòng; {bo_qua} dòng bỏ qua (đã đổi "
              "sau lần gán lại — không đè).")
        return 0
    if ns.ap_dung and not ns.sao_luu:
        in_ra("--ap-dung cần --sao-luu <tệp> (tệp hoàn tác ghi TRƯỚC khi sửa kho).")
        return 2
    if ns.ap_dung and os.path.exists(ns.sao_luu):
        in_ra(f"Tệp {ns.sao_luu} đã có — chọn tên khác (không ghi đè tệp hoàn tác cũ).")
        return 2
    den = getattr(ns, "den_luot", None)
    du_an, nha, hop_le, moc = doc_kho(ma, den)
    if not du_an:
        in_ra(f"Không có dự án '{ma}' trong kho.")
        return 2
    import gan_nhan_nen as N
    brand = N.brand_du_an(du_an)
    a = chon_thuong_hieu(du_an, nha) if "a" in ns.buoc else []
    bo = {(d["khoa_bai"], d["ma"]) for d in a}
    b = chon_gan_lai(hop_le, ns.tat_ca, bo, den, moc) if "b" in ns.buoc else []
    can, luot = uoc_luot_model(b)
    che_do = "ÁP DỤNG" if ns.ap_dung else "CHẠY THỬ (giao dịch chỉ đọc, không ghi gì)"
    in_ra(f"Dự án {ma} — {che_do}.")
    if "b" in ns.buoc:
        # In bộ lọc ĐANG áp trước mọi con số (17/10/2026): chạy nhầm không có --den-luot là gán
        # lại cả 7.202 dòng đã có nhãn prompt mới — thấy ngay ở dòng này, trước khi --ap-dung.
        in_ra(_cau_loc_luot(den, chon_gan_lai(hop_le, ns.tat_ca, bo) if den is not None
                            else b, moc))
    doi_loai = sum(1 for d in a if d["moi"]["loai"] != d["cu"]["loai"])
    in_ra(f"(a) Trả lời của tài khoản nhà dưới bài kênh nhà: {len(a)} dòng thành của thương "
          f"hiệu ({doi_loai} hop_le → thuong_hieu, bỏ sắc thái/chủ đề; {len(a) - doi_loai} "
          "loại khác chỉ bật cờ).")
    for d in a[:ns.mau]:
        in_ra(_mau(d))
    in_ra(f"(b) Gán lại nhãn: {len(b)} dòng" + (f" ({_dem(b, 'ly_do')})" if b else "") + ".")
    in_ra(f"    Ước tính: {can} dòng cần model → {luot} lượt gọi model (lô {LO}, tuần tự); "
          f"{len(b) - can} dòng gán bằng luật.")
    for d in b[:ns.mau]:
        in_ra(_mau(d))
    if not ns.ap_dung:
        thu = [d for d in b if can_model(d)][:min(max(0, ns.thu), LO)]
        if thu:
            _chuan_bi_model()
            doi, dem = gan_nhan(thu, brand)
            in_ra(f"Xem trước {len(thu)} dòng (1 lượt model, KHÔNG ghi): {len(doi)} đổi nhãn, "
                  f"{dem['khong_doi']} giữ nguyên, {dem['chua_gan']} chưa gán được "
                  f"({dem['trang_thai'] or '—'}).")
            in_ma_tran(dem, doi, ns.mau, in_ra)
            in_ra("    Mẫu đổi nhãn khác:")
            for d in doi[:ns.mau]:
                in_ra(_mau(d))
        in_ra("Không ghi gì. Ghi thật: thêm --ap-dung --sao-luu <tệp hoàn tác>.")
        return 0
    with open(ns.sao_luu, "x", encoding="utf-8") as so_luu:
        so_luu.write(json.dumps({
            "loai_dong": "dau", "du_an": ma, "phien_ban": 1,
            "luc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "buoc": ns.buoc, "tat_ca": bool(ns.tat_ca), "den_luot": den},
            ensure_ascii=False) + "\n")
        so_luu.flush()
        sua_a = bo_a = 0
        for i in range(0, len(a), LO):
            x, y = ghi_lo(ma, a[i:i + LO], so_luu)
            sua_a, bo_a = sua_a + x, bo_a + y
        in_ra(f"(a) đã sửa {sua_a} dòng, bỏ qua {bo_a} (dòng đã đổi từ lúc đọc).")
        if b:
            _chuan_bi_model()
        sua_b = bo_b = chua = giu = 0
        cac_lo = chia_lo(b)
        for j, lo in enumerate(cac_lo, 1):
            doi, dem = gan_nhan(lo, brand)
            x, y = ghi_lo(ma, doi, so_luu)
            sua_b, bo_b = sua_b + x, bo_b + y
            chua, giu = chua + dem["chua_gan"], giu + dem["khong_doi"]
            in_ra(f"    lô {j}/{len(cac_lo)}: {len(lo)} dòng, đổi {x}, giữ {dem['khong_doi']}, "
                  f"chưa gán {dem['chua_gan']}, bỏ qua {y} ({dem['trang_thai'] or 'luật'})")
        in_ra(f"(b) đã sửa {sua_b} dòng; giữ nguyên {giu}; chưa gán được {chua} (giữ nhãn cũ); "
              f"bỏ qua {bo_b}. Tệp hoàn tác: {ns.sao_luu}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gán lại nhãn bình luận trong kho lang_nghe "
                                             "(mặc định chạy thử, không ghi).")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("--dry-run", action="store_true",
                    help="chạy thử (mặc định khi không có --ap-dung / --hoan-tac)")
    ap.add_argument("--ap-dung", action="store_true", help="ghi thật (cần --sao-luu)")
    ap.add_argument("--sao-luu", metavar="TEP", help="tệp hoàn tác JSONL (tạo mới)")
    ap.add_argument("--hoan-tac", metavar="TEP", help="trả lại giá trị cũ từ tệp hoàn tác")
    ap.add_argument("--tat-ca", action="store_true", help="(b) gán lại MỌI bình luận hop_le")
    ap.add_argument("--buoc", choices=("a", "b", "ab"), default="ab",
                    help="a = trả lời fanpage nhà, b = gán lại nhãn (mặc định cả hai)")
    ap.add_argument("--thu", type=int, default=0, metavar="N",
                    help="chạy thử: gọi model cho tối đa N dòng (≤ 100) để xem trước, không ghi")
    ap.add_argument("--den-luot", type=int, metavar="N",
                    help="(b) chỉ bình luận có binh_luan.luot_id ≤ N, luot_id NULL (tính là cũ) "
                         "hoặc thấy lần đầu trước lượt N+1 (cào lại sau, nhãn còn cũ); áp cho mọi "
                         "bộ chọn của (b), kể cả --tat-ca. Vd --den-luot 8: bỏ bình luận thấy lần "
                         "đầu từ lượt 9, đã gán bằng prompt mới")
    ap.add_argument("--mau", type=int, default=8, help="số dòng mẫu in ra mỗi bước")
    ns = ap.parse_args(argv)
    if ns.den_luot is not None and ns.den_luot < 0:
        ap.error("--den-luot phải ≥ 0")
    if ns.dry_run and (ns.ap_dung or ns.hoan_tac):
        ap.error("--dry-run không đi cùng --ap-dung / --hoan-tac")
    if ns.ap_dung and ns.hoan_tac:
        ap.error("--ap-dung và --hoan-tac là hai việc riêng")
    return chay(ns)


if __name__ == "__main__":
    sys.exit(main())
