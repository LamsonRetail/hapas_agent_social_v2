"""Dọn bài đường TỪ KHOÁ giữ theo luật mà KHÔNG có tín hiệu brand — script một lần (27/10/2026).

Vì sao: từ khoá dự án hapas có khẩu hiệu chung chung ("yêu từ điều nhỏ nhất"), mà
`apify_tool._khop_tu_khoa` coi từ khoá nhiều chữ là khớp khi ĐỦ mọi chữ ở bất kỳ đâu (nội dung +
hashtag + tên kênh + định danh) — video của kênh "Tử Vi Vô Chính Diệu" khớp. AI không phán (không rõ /
hết giờ / bỏ qua) thì bản trước giữ theo luật (`ly_do_giu = 'khop_tu_khoa'`): kho 27/10/2026 có 109
bài đường từ khoá không có chữ "hapas" mang 773 bình luận (736 hop_le) — phần lớn bài 20/10 về mẹ /
tình yêu chung chung. Từ bản này lượt quét chỉ giữ bài AI không phán khi có tín hiệu brand
(`theo_doi.co_tin_hieu_brand`); script này dọn phần ĐÃ vào kho. Kèm: dự án VN còn 4 bài TikTok + 3
bài YouTube AI giữ với mã `other_market` (HAPAS Thailand, bình luận tiếng Thái — MKT báo sai) từ
trước luật M2 (18/10/2026).

Chọn (chỉ bài `kieu_quet = 'tu_khoa'` có `dang_luc` của dự án):
  (a) `ly_do_giu = 'khop_tu_khoa'` mà KHÔNG có tín hiệu brand theo ĐÚNG hàm của lượt quét
      (`theo_doi.co_tin_hieu_brand` với `ten_brand` hiện hành: tên, mã, `ten` cấu hình, hashtag dự
      án + khẩu hiệu chiến dịch đang chạy ở dạng viết liền) — XOÁ, KHÔNG ghi sổ "đã loại": kho
      không biết bài được giữ theo luật vì AI "không rõ" hay vì AI hết giờ / bỏ qua / đạt trần, nên
      không được chặn bài vĩnh viễn (video chiến dịch chỉ có khẩu hiệu mà lúc trước AI hết giờ sẽ
      mất luôn). Lượt sau gặp lại thì AI phán một lần (≈ số bài đã dọn, tối đa ~109 lượt phán).
  (b) dự án thị trường VN: `ly_do_giu = 'other_market'` — CHỈ LIỆT KÊ (kèm nội dung) để người
      quyết: lượt quét giữ đúng mã này khi ghi chú thị trường của AI là "VN" (`theo_doi.
      other_market_ngoai_vn`), mà kho không lưu ghi chú đó. Xoá khi thêm `--gom-other-market`; bài
      xoá vào sổ "đã loại" lý do `ai:other_market` (đúng lý do lượt quét ghi từ luật M2; bài
      Facebook kèm khoá ổn định; bài web vào sổ riêng "<mã>:web").
  Bài thuộc NGUỒN ĐÃ DUYỆT (`nguon_id` trỏ tới nguồn của dự án, hoặc chủ bài trùng một nguồn — kênh
  nhà, KOL, đối tác, trang…, kể cả nguồn tạm dừng): GIỮ, in riêng mục "thuộc nguồn đã duyệt" — lượt
  quét nguồn sẽ ghi lại bài đó (mất lịch sử bình luận / chỉ số), không phải việc của script này.
Bài AI giữ với mã khác (brand / ad / product / ugc…), bài đường nguồn: KHÔNG đụng. Cổng brand tắt
(`du_an.cau_hinh.hashtag_can_nhac_brand` = false — một công tắc cho cả cổng brand đường hashtag lẫn
cổng giữ-theo-luật; dự án lắng nghe theo chủ đề / ngành phải tắt) thì (a) rỗng như lượt quét. DELETE
khỏi `bai` (bình luận + chi_so_ngay xoá theo FK ON DELETE CASCADE).

An toàn (theo mẫu `scripts/lang_nghe_loc_seeding.py`):
  • Mặc định CHẠY THỬ: đọc trong MỘT giao dịch READ ONLY; in TỪNG bài của (a), (b) và mục nguồn đã
    duyệt (nền tảng, tác giả, link, 120 ký tự đầu, số bình luận) để chủ dự án / MKT duyệt, kèm tổng
    bài / bình luận / bình luận hop_le / dòng chi_so_ngay sẽ xoá. Không ghi gì (kể cả sổ).
  • `--ap-dung --sao-luu <tệp>`: không chạy khi dự án có lượt `/theodoi` đang chạy. Mỗi BÀI một
    giao dịch: giữ khoá advisory mở lượt (CÙNG khoá `lang_nghe_db.mo_luot` — lượt mới chờ bài này
    commit), kiểm lại lượt đang chạy, khoá dòng (FOR UPDATE), đọc lại (bài đã đổi `ly_do_giu` /
    đã có tín hiệu brand thì giữ), ghi tệp hoàn tác ĐỦ dòng bài + bình luận + chi_so_ngay (fsync)
    TRƯỚC, ghi sổ (chỉ (b)), rồi mới xoá. Dấu "đã áp" ghi SAU khi commit. Tệp có sẵn thì dừng.
  • `--hoan-tac <tệp>`: chèn lại bài, chi_so_ngay, bình luận của MỌI bài trong tệp — kể cả bài chưa
    có dấu "đã áp" (giao dịch huỷ: dòng còn nguyên; tiến trình dừng ngay sau commit: dòng đã xoá) —
    dòng đã có lại thì để nguyên (ON CONFLICT DO NOTHING), và gỡ các khoá đó khỏi sổ. Chạy lại được.
  • Chạy lại script: bài đã dọn không còn trong kho — chỉ xử lý phần còn lại.

Quyền: role `mark` KHÔNG có DELETE trên `bai` (bot không xoá bài). Cấp TẠM cho lần chạy rồi thu lại;
hoàn tác chỉ cần INSERT (đã có):

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_loc_khong_brand.py hapas                    # chạy thử
    sudo -u mark $PY scripts/lang_nghe_loc_khong_brand.py hapas --gom-other-market # thử cả (b)
    sudo -u postgres psql -d lang_nghe -c 'GRANT DELETE ON bai TO mark'
    sudo -u mark $PY scripts/lang_nghe_loc_khong_brand.py hapas --ap-dung \\
        --sao-luu /opt/mark/loc-khong-brand-$(date +%F).jsonl
    sudo -u postgres psql -d lang_nghe -c 'REVOKE DELETE ON bai FROM mark'
    sudo -u mark $PY scripts/lang_nghe_loc_khong_brand.py hapas --hoan-tac /opt/mark/loc-khong-brand-<ngày>.jsonl

Chạy SAU khi bản code có luật tín hiệu brand đã lên VPS (bản cũ sẽ ghi lại bài này ở lượt sau). Sổ
nằm ở thư mục việc nền của Mark (`apify_tool._thu_muc_nen`, /opt/mark/app/.audit/viec-nen) — chạy
bằng user mark từ /opt/mark/app như lệnh trên. BigQuery: MERGE không xoá dòng — nếu đã bật đồng bộ
thì bài đã dọn phải xoá tay trên BigQuery: bản in ĐÃ ÁP in câu DELETE cho `bai`, `binh_luan`,
`chi_so_ngay` với đúng các khoá đã xoá.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

import lang_nghe_db as K
import loc_rac

_VN = datetime.timezone(datetime.timedelta(hours=7))
_GIO = {"dang_luc", "thay_lan_dau", "cap_nhat_cuoi", "bl_lay_luc"}
_NGAY = {"ngay"}
#: Khoá ngoại tới bảng có thể đã xoá dòng: chèn lại qua truy vấn con (mất dòng cha thì NULL).
_FK_CON = {"nguon_id": "nguon", "luot_dau": "luot_quet", "luot_cuoi": "luot_quet",
           "luot_id": "luot_quet"}
#: Nhóm bài dọn -> mã `ly_do_giu` được xét (lý do ghi sổ: `so_cua`).
NHOM = {"khong_brand": "khop_tu_khoa", "other_market": "other_market"}
LY_SO_OTHER_MARKET = "ai:other_market"      # = lý do `theo_doi._giu_tu_khoa` ghi (luật M2)

# Mọi câu SQL mang thẻ `/* khb:<tên> */` — bộ thử nhận diện câu theo thẻ (kho giả).
SQL_CHI_DOC = "SET TRANSACTION READ ONLY"
# `hashtag` qua to_jsonb: DB chưa chạy cột `du_an.hashtag` (18/10/2026) thì ra NULL, không lỗi cột.
SQL_DU_AN = ("/* khb:du_an */ SELECT ma, ten, tu_khoa, tu_loai_tru, boi_canh, thi_truong, "
             "cau_hinh, to_jsonb(d) -> 'hashtag' AS hashtag FROM du_an d WHERE ma = %s")
SQL_NGUON = "/* khb:nguon */ SELECT id, nen_tang, dinh_danh, loai FROM nguon WHERE du_an = %s"
SQL_BAI = ("/* khb:bai */ SELECT khoa, nen_tang, nguon_id, kieu_quet, link, tai_khoan, tac_gia, "
           "dang_luc, noi_dung, hashtag, binh_luan, ly_do_giu FROM bai WHERE du_an = %s AND "
           "kieu_quet = 'tu_khoa' AND ly_do_giu = ANY(%s) AND dang_luc IS NOT NULL "
           "ORDER BY nen_tang, dang_luc, khoa")
SQL_KHAC = ("/* khb:khac */ SELECT count(*) AS n FROM bai WHERE du_an = %s AND "
            "ly_do_giu = 'other_market' AND kieu_quet <> 'tu_khoa'")
SQL_DEM_BL = ("/* khb:dem_bl */ SELECT khoa_bai, count(*) AS n, count(*) FILTER (WHERE loai = "
              "'hop_le') AS hop_le FROM binh_luan WHERE du_an = %s AND khoa_bai = ANY(%s) "
              "GROUP BY khoa_bai")
SQL_DEM_CS = ("/* khb:dem_cs */ SELECT khoa, count(*) AS n FROM chi_so_ngay WHERE du_an = %s "
              "AND khoa = ANY(%s) GROUP BY khoa")
SQL_QUYEN = "/* khb:quyen */ SELECT has_table_privilege(current_user, 'bai', 'DELETE') AS xoa"
SQL_LUOT_CHAY = ("/* khb:luot_chay */ SELECT id FROM luot_quet WHERE du_an = %s AND "
                 "trang_thai = 'dang_chay' AND bat_dau > now() - make_interval(hours => %s) "
                 "ORDER BY id")
SQL_DONG_BO = "/* khb:dong_bo */ SELECT count(*) AS n FROM dong_bo_bq"
SQL_KHOA_LUOT = "/* khb:khoa_luot */ " + K._SQL_KHOA_LUOT
SQL_KHOA_BAI = ("/* khb:khoa_bai */ SELECT * FROM bai WHERE du_an = %s AND khoa = ANY(%s) "
                "ORDER BY khoa FOR UPDATE")
SQL_KHOA_BL = ("/* khb:khoa_bl */ SELECT * FROM binh_luan WHERE du_an = %s AND "
               "khoa_bai = ANY(%s) ORDER BY khoa_bai, ma FOR UPDATE")
SQL_KHOA_CS = ("/* khb:khoa_cs */ SELECT * FROM chi_so_ngay WHERE du_an = %s AND "
               "khoa = ANY(%s) ORDER BY khoa, ngay FOR UPDATE")
SQL_XOA_BAI = "/* khb:xoa_bai */ DELETE FROM bai WHERE du_an = %s AND khoa = ANY(%s)"


# ───────────────────────────── tiện ích ─────────────────────────────
def _dsn_tu_env_file() -> None:
    """Mark đặt `LANG_NGHE_DSN` trong `.env` (deploy/lang-nghe/README.md §3): chỉ đọc ĐÚNG khoá
    đó, không nạp các bí mật khác vào tiến trình (như `lang_nghe_loc_seeding`)."""
    if os.environ.get("LANG_NGHE_DSN"):
        return
    tep = GOC / ".env"
    if not tep.exists():
        return
    for dong in tep.read_text(encoding="utf-8", errors="replace").splitlines():
        k, _, v = dong.partition("=")
        if k.strip() == "LANG_NGHE_DSN" and v.strip():
            os.environ["LANG_NGHE_DSN"] = v.strip()
            return


def _json(v):
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return str(v)


def _tu_json(r: dict) -> dict:
    """Giá trị đọc từ tệp hoàn tác → kiểu Python (giờ / ngày theo TÊN cột)."""
    ra = {}
    for k, v in r.items():
        if isinstance(v, str) and k in _GIO:
            v = datetime.datetime.fromisoformat(v)
        elif isinstance(v, str) and k in _NGAY:
            v = datetime.date.fromisoformat(v)
        ra[k] = v
    return ra


def _ghi_dong(so_luu, x: dict) -> None:
    so_luu.write(json.dumps(x, ensure_ascii=False, default=_json) + "\n")
    so_luu.flush()
    os.fsync(so_luu.fileno())


def _mot_dong(s, n: int) -> str:
    return " ".join(str(s or "").split())[:n]


def _dong_d(r: dict) -> dict:
    """Dòng `bai` → dạng `d` của lượt tìm (cho `co_tin_hieu_brand` + khoá ổn định Facebook)."""
    return {"platform": r.get("nen_tang"), "username": r.get("tai_khoan"),
            "kenh": r.get("tac_gia"), "link": r.get("link"), "text": r.get("noi_dung"),
            "hashtags": r.get("hashtag"), "ma_so_fb": r.get("ma_so_fb")}


# ───────────────────────────── kế hoạch (thuần) ─────────────────────────────
class Luat:
    """Luật chọn bài của dự án: cổng brand + tên brand (`ten_brand`, đọc một lần) + nguồn đã
    duyệt (mọi `nguon` của dự án, kể cả kênh nhà)."""

    def __init__(self, du_an: dict, nguon: list[dict], bay_gio: datetime.datetime | None = None,
                 ten: list[str] | None = None):
        import theo_doi as T
        self.cong = T.cau_hinh_hashtag_brand(du_an)
        self.ten = ten if ten is not None else (
            T.ten_brand(du_an, bay_gio, cong=self.cong) if self.cong["bat"] else [])
        # Tài khoản của MỌI nguồn (cùng cách chuẩn hoá với kênh nhà — Facebook lấy cả slug trang).
        self.tk_nguon = T._kenh_nha([{**n, "loai": "kenh_nha"} for n in nguon])
        self.nguon_id = {int(n["id"]) for n in nguon if n.get("id") is not None}
        self.vn = str(du_an.get("thi_truong") or "VN").upper() == "VN"

    def thuoc_nguon(self, r: dict) -> bool:
        return r.get("nguon_id") in self.nguon_id or loc_rac.khoa_tai_khoan(
            r.get("nen_tang"), r.get("tai_khoan")) in self.tk_nguon

    def nhom(self, r: dict) -> str | None:
        """"khong_brand" (a) / "other_market" (b) khi dòng `bai` là ứng viên dọn; "nguon" khi là ứng
        viên nhưng thuộc nguồn đã duyệt (giữ); None khi giữ."""
        import theo_doi as T
        if str(r.get("kieu_quet") or "tu_khoa") != "tu_khoa" or r.get("dang_luc") is None:
            return None
        ly = r.get("ly_do_giu")
        if ly == NHOM["other_market"] and self.vn:
            n = "other_market"
        elif ly == NHOM["khong_brand"] and not T.co_tin_hieu_brand(_dong_d(r), self.cong,
                                                                   self.ten):
            n = "khong_brand"
        else:
            return None
        return "nguon" if self.thuoc_nguon(r) else n


def ke_hoach(luat: Luat, bai: list[dict]) -> dict:
    """THUẦN. Dòng `bai` ứng viên -> {"khong_brand": [bài], "other_market": [bài], "nguon": [bài
    thuộc nguồn đã duyệt — giữ], "giu": số bài `khop_tu_khoa` vẫn giữ vì có tín hiệu brand}."""
    ra: dict = {"khong_brand": [], "other_market": [], "nguon": [], "giu": 0}
    for r in bai:
        n = luat.nhom(r)
        if n:
            ra[n].append(r)
        elif r.get("ly_do_giu") == NHOM["khong_brand"]:
            ra["giu"] += 1
    return ra


def so_cua(du_an: dict, r: dict, bay_gio: datetime.datetime) -> tuple[str, str, list]:
    """(khoá sổ, dấu luật, [(khoá, `ai:other_market`, ngày đăng)]) của bài (b) sắp dọn — dấu luật
    CÙNG dấu lượt quét ghi (sổ không bị làm lại); bài web vào sổ RIÊNG "<mã>:web" với dấu theo từ
    khoá web (từ khoá + khẩu hiệu chiến dịch, như `theo_doi._tim_web`)."""
    import theo_doi as T
    import theo_doi_api as TDA
    ma = du_an["ma"]
    tu = T.tu_tim(du_an)
    loai = [(k, LY_SO_OTHER_MARKET, r["dang_luc"])
            for k in (r["khoa"], *T._khoa_loai_on_dinh(_dong_d(r), r["dang_luc"]))]
    if r.get("nen_tang") == "web":
        import nguon_web as W
        kh = T.khau_hieu_chien_dich(ma, bay_gio)[1]
        tu_web = W.rut_gon_tu_khoa([*tu, *kh]) or tu
        return f"{ma}:web", TDA.dau_loai(du_an, tu_web), loai
    return ma, TDA.dau_loai(du_an, tu), loai


# ───────────────────────────── đọc ─────────────────────────────
def doc_kho(ma: str, bay_gio: datetime.datetime) -> dict | None:
    """Dự án, nguồn, bài ứng viên, số bình luận (+ hop_le) / chi_so_ngay đi theo, quyền, lượt đang
    chạy — MỘT giao dịch READ ONLY. None khi không có dự án."""
    with K.ket_noi() as c:
        c.execute(SQL_CHI_DOC)
        du_an = c.execute(SQL_DU_AN, (ma,)).fetchone()
        if not du_an:
            return None
        du_an = dict(du_an)
        nguon = [dict(r) for r in c.execute(SQL_NGUON, (ma,)).fetchall()]
        bai = [dict(r) for r in c.execute(SQL_BAI, (ma, list(NHOM.values()))).fetchall()]
        luat = Luat(du_an, nguon, bay_gio)        # đọc sổ mốc + lịch chiến dịch (kết nối riêng)
        kh = ke_hoach(luat, bai)
        khoa = sorted(r["khoa"] for n in (*NHOM, "nguon") for r in kh[n])
        bl, hl, cs = {}, {}, {}
        if khoa:
            for r in c.execute(SQL_DEM_BL, (ma, khoa)).fetchall():
                bl[r["khoa_bai"]], hl[r["khoa_bai"]] = int(r["n"]), int(r["hop_le"])
            cs = {r["khoa"]: int(r["n"]) for r in c.execute(SQL_DEM_CS, (ma, khoa)).fetchall()}
        khac = int((c.execute(SQL_KHAC, (ma,)).fetchone() or {}).get("n") or 0)
        quyen = bool((c.execute(SQL_QUYEN).fetchone() or {}).get("xoa"))
        dang = [int(r["id"]) for r in c.execute(SQL_LUOT_CHAY, (ma, K.GIO_BO_DO)).fetchall()]
    return {"du_an": du_an, "nguon": nguon, "luat": luat, "kh": kh, "dem_bl": bl,
            "dem_hop_le": hl, "dem_cs": cs, "khac_other_market": khac, "quyen_xoa": quyen,
            "luot_chay": dang}


def dem_dong_bo() -> tuple[int | None, str]:
    try:
        with K.ket_noi() as c:
            n = int((c.execute(SQL_DONG_BO).fetchone() or {}).get("n") or 0)
        return n, f"{n} dòng" + (" — CHƯA bật đồng bộ" if n == 0 else
                                 " — ĐÃ đồng bộ: bài đã dọn phải xoá tay trên BigQuery")
    except K.LoiKho as e:
        return None, f"không đọc được ({e})"


# ───────────────────────────── ghi ─────────────────────────────
def ap_dung_bai(du_an: dict, luat: Luat, khoa: str, nhom_duoc: set[str],
                bay_gio: datetime.datetime, tu_pv: datetime.datetime,
                so_luu) -> tuple[str, str | None]:
    """Dọn MỘT bài trong MỘT giao dịch: khoá mở lượt, kiểm lượt đang quét, khoá dòng, đọc lại, ghi
    tệp hoàn tác (fsync), ghi sổ (chỉ (b) — (a) không vào sổ), rồi xoá. `nhom_duoc`: nhóm được xoá
    lần chạy này; `tu_pv`: đầu phạm vi theo dõi (tính một lần ở `chay`). -> (trạng thái, nhóm).
    Trạng thái: "da_don", "khong_con" (bài đã đổi / không còn / thành bài nguồn — bỏ qua),
    "dang_quet" (lượt /theodoi vừa bắt đầu — dừng cả lần chạy)."""
    import theo_doi_api as TDA
    ma = du_an["ma"]
    with K.ket_noi() as c:
        c.execute(SQL_KHOA_LUOT, (K.so_khoa_luot(ma),))
        if c.execute(SQL_LUOT_CHAY, (ma, K.GIO_BO_DO)).fetchall():
            return "dang_quet", None
        bai = [dict(r) for r in c.execute(SQL_KHOA_BAI, (ma, [khoa])).fetchall()]
        # Đọc lại: bài đổi `ly_do_giu` (AI vừa giữ với mã brand), đổi nội dung… thì giữ.
        nhom = luat.nhom(bai[0]) if len(bai) == 1 else None
        if nhom not in nhom_duoc:
            return "khong_con", None
        r = bai[0]
        bl = [dict(x) for x in c.execute(SQL_KHOA_BL, (ma, [khoa])).fetchall()]
        cs = [dict(x) for x in c.execute(SQL_KHOA_CS, (ma, [khoa])).fetchall()]
        ma_so, dau, loai = so_cua(du_an, r, bay_gio) if nhom == "other_market" else ("", "", [])
        _ghi_dong(so_luu, {"loai_dong": "bai", "du_an": ma, "khoa": khoa, "nhom": nhom,
                           "bai": [r], "binh_luan": bl, "chi_so_ngay": cs,
                           "so": {ma_so: sorted({k for k, _, _ in loai})} if loai else {}})
        if loai:
            TDA.ghi_loai(ma_so, dau, loai, tu_pv)
        n = int(c.execute(SQL_XOA_BAI, (ma, [khoa])).rowcount or 0)
        if n != 1:
            raise K.LoiKho(f"xoá {n}/1 bài {khoa} — huỷ giao dịch")
    return "da_don", nhom


def _chen(c, bang: str, r: dict, xung_dot: str) -> int:
    """Chèn lại một dòng từ tệp hoàn tác (đã có thì thôi). `cap_nhat_cuoi` = now(): dòng trở lại
    kho là dòng ĐỔI với đồng bộ BigQuery."""
    cot = [k for k in r if k != "cap_nhat_cuoi"]
    dat = ", ".join(f"(SELECT id FROM {_FK_CON[k]} WHERE id = %s)" if k in _FK_CON else "%s"
                    for k in cot)
    moc = ("", "") if "cap_nhat_cuoi" not in r else (", cap_nhat_cuoi", ", now()")
    return int(c.execute(f"/* khb:hoan_{bang} */ INSERT INTO {bang} ({', '.join(cot)}{moc[0]}) "
                         f"VALUES ({dat}{moc[1]}) ON CONFLICT ({xung_dot}) DO NOTHING",
                         [r[k] for k in cot]).rowcount or 0)


def hoan_tac_bai(ma: str, x: dict) -> dict:
    """Trả lại MỘT bài (một giao dịch): bài → chi_so_ngay → bình luận (thứ tự khoá ngoại); dòng đã
    có lại thì giữ dòng hiện tại. Gỡ các khoá khỏi sổ SAU khi commit. -> số dòng chèn."""
    import theo_doi_api as TDA
    n = {"bai": 0, "chi_so_ngay": 0, "binh_luan": 0}
    with K.ket_noi() as c:
        for r in x.get("bai") or []:
            n["bai"] += _chen(c, "bai", _tu_json(r), "du_an, khoa")
        for r in x.get("chi_so_ngay") or []:
            n["chi_so_ngay"] += _chen(c, "chi_so_ngay", _tu_json(r), "du_an, khoa, ngay")
        for r in x.get("binh_luan") or []:
            n["binh_luan"] += _chen(c, "binh_luan", _tu_json(r), "du_an, khoa_bai, ma")
    for ma_so, ks in (x.get("so") or {}).items():
        TDA.bo_khoi_so(ma_so, list(ks or []))
    return n


def doc_tep_hoan_tac(tep: str) -> tuple[dict, list[dict], list[dict]]:
    """-> (dòng đầu, bài CÓ dấu đã áp, bài KHÔNG có dấu). Dòng bài ghi TRƯỚC khi xoá; giao dịch lỗi
    (rollback) thì không có dấu."""
    dau, ds, da_ap = {}, [], set()
    with open(tep, encoding="utf-8") as f:
        for i, dong in enumerate(f):
            if not dong.strip():
                continue
            r = json.loads(dong)
            if i == 0 and r.get("loai_dong") == "dau":
                dau = r
            elif r.get("loai_dong") == "bai":
                ds.append(r)
            elif r.get("loai_dong") == "da_ap":
                da_ap.add(str(r.get("khoa")))
    return dau, [r for r in ds if r.get("khoa") in da_ap], [r for r in ds if r.get("khoa")
                                                            not in da_ap]


# ───────────────────────────── in ─────────────────────────────
_TEN_NHOM = {"khong_brand": "(a) giữ theo luật khop_tu_khoa, KHÔNG có tín hiệu brand — XOÁ, không "
                            "vào sổ",
             "other_market": "(b) AI giữ mã other_market — dự án VN — NGƯỜI QUYẾT (có thể là ghi "
                             "chú thị trường VN)",
             "nguon": "Thuộc nguồn đã duyệt — GIỮ (ứng viên (a)/(b) nhưng chủ bài là nguồn của dự "
                      "án)"}


def _in_ke_hoach(kho: dict, mau: int | None, gom: bool, in_ra) -> None:
    kh, luat = kho["kh"], kho["luat"]
    ma = kho["du_an"]["ma"]
    in_ra(f"Cổng brand: {'BẬT' if luat.cong['bat'] else 'TẮT — nhóm (a) rỗng'}; tên brand hiện "
          f"hành: {', '.join(luat.ten[:20]) or '—'}"
          + (f" (+{len(luat.ten) - 20})" if len(luat.ten) > 20 else "") + ".")
    in_ra(f"Bài {ma} đường từ khoá ly_do_giu = khop_tu_khoa vẫn giữ (có tín hiệu brand / kênh "
          f"nhà): {kh['giu']}.")
    for n in (*NHOM, "nguon"):
        cac = sorted(kh[n], key=lambda r: (r["nen_tang"], -kho["dem_bl"].get(r["khoa"], 0),
                                           r["khoa"]))
        in_ra(f"{_TEN_NHOM[n]}: {len(cac)} bài, {sum(kho['dem_bl'].get(r['khoa'], 0) for r in cac)}"
              " bình luận."
              + ((" Sẽ xoá (--gom-other-market)." if gom else " KHÔNG xoá — thêm "
                  "--gom-other-market để xoá.") if n == "other_market" and cac else ""))
        for r in cac[:mau]:
            tk = _mot_dong(r.get("tai_khoan"), 40)
            in_ra(f"  [{r['nen_tang']}] {_mot_dong(r.get('tac_gia'), 40)}"
                  + (f" @{tk}" if tk else "") + " · "
                  f"{r['dang_luc'].astimezone(_VN):%d/%m} · "
                  f"{kho['dem_bl'].get(r['khoa'], 0)} bl ({kho['dem_hop_le'].get(r['khoa'], 0)} "
                  f"hop_le) · {r.get('link') or ''}")
            in_ra(f"      {_mot_dong(r.get('noi_dung'), 120)}")
        if mau is not None and len(cac) > mau:
            in_ra(f"  … và {len(cac) - mau} bài nữa (--mau 0: in hết)")
    tat = [r["khoa"] for n in _nhom_xoa(gom) for r in kh[n]]
    in_ra(f"TỔNG sẽ dọn: {len(tat)} bài; đi theo (xoá theo bài): "
          f"{sum(kho['dem_bl'].get(k, 0) for k in tat)} bình luận "
          f"({sum(kho['dem_hop_le'].get(k, 0) for k in tat)} hop_le), "
          f"{sum(kho['dem_cs'].get(k, 0) for k in tat)} dòng chi_so_ngay.")
    if kho["khac_other_market"]:
        in_ra(f"Không đụng: {kho['khac_other_market']} bài other_market ngoài đường từ khoá "
              "(đường nguồn — nguồn do người duyệt).")
    in_ra(f"dong_bo_bq: {dem_dong_bo()[1]}.")


def _in_bigquery(ma: str, khoa: list[str], in_ra) -> None:
    """BigQuery MERGE không xoá dòng: in câu xoá tay cho các khoá đã xoá ở Postgres."""
    n, cau = dem_dong_bo()
    if not khoa or n == 0:
        return
    ds = ", ".join("'" + k.replace("'", "''") + "'" for k in khoa)
    in_ra(f"BigQuery ({cau}) — xoá tay {len(khoa)} bài + dòng đi theo (thay <dataset>):")
    for bang, cot in (("bai", "khoa"), ("binh_luan", "khoa_bai"), ("chi_so_ngay", "khoa")):
        in_ra(f"  DELETE FROM `<dataset>.{bang}` WHERE du_an = '{ma}' AND {cot} IN ({ds});")


def _nhom_xoa(gom: bool) -> tuple[str, ...]:
    return ("khong_brand", "other_market") if gom else ("khong_brand",)


def chay(ns, in_ra=print, bay_gio: datetime.datetime | None = None) -> int:
    import theo_doi_api as TDA
    ma = ns.du_an.strip().lower()
    if ns.hoan_tac:
        dau, ds, khong_dau = doc_tep_hoan_tac(ns.hoan_tac)
        if dau.get("du_an") and dau["du_an"] != ma:
            in_ra(f"Tệp hoàn tác của dự án '{dau['du_an']}', không phải '{ma}' — dừng.")
            return 2
        tong = {"bai": 0, "chi_so_ngay": 0, "binh_luan": 0}
        # Bài KHÔNG có dấu "đã áp" cũng hoàn tác (như `lang_nghe_loc_seeding`): dòng bài ghi TRƯỚC
        # khi xoá, dấu ghi SAU commit — thiếu dấu là giao dịch đã huỷ (dòng còn nguyên: chèn lại
        # không làm gì) HOẶC tiến trình dừng ngay sau commit (dòng đã xoá: chèn lại là cứu dữ liệu).
        for x in [r for r in [*ds, *khong_dau] if r.get("du_an", ma) == ma]:
            for k, v in hoan_tac_bai(ma, x).items():
                tong[k] += v
        in_ra(f"Hoàn tác {ma}: {len(ds) + len(khong_dau)} bài — chèn lại {tong['bai']} bài, "
              f"{tong['chi_so_ngay']} dòng chi_so_ngay, {tong['binh_luan']} bình luận (dòng đã có "
              "lại thì giữ); đã gỡ khỏi sổ đã loại.")
        if khong_dau:
            in_ra(f"{len(khong_dau)} bài không có dấu đã áp (giao dịch đã huỷ, hoặc tiến trình dừng "
                  "ngay sau commit) — đã hoàn tác an toàn như trên.")
        return 0
    if ns.ap_dung and not ns.sao_luu:
        in_ra("--ap-dung cần --sao-luu <tệp> (tệp hoàn tác ghi TRƯỚC khi sửa kho).")
        return 2
    if ns.ap_dung and os.path.exists(ns.sao_luu):
        in_ra(f"Tệp {ns.sao_luu} đã có — chọn tên khác (không ghi đè tệp hoàn tác cũ).")
        return 2
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    kho = doc_kho(ma, bay_gio)
    if kho is None:
        in_ra(f"Không có dự án '{ma}' trong kho.")
        return 2
    in_ra(f"Dự án {ma} — {'ÁP DỤNG' if ns.ap_dung else 'CHẠY THỬ (giao dịch chỉ đọc, không ghi gì)'}.")
    _in_ke_hoach(kho, ns.mau or None, ns.gom_other_market, in_ra)
    if not kho["quyen_xoa"]:
        in_ra("Role hiện tại KHÔNG có quyền DELETE trên bai (đúng thiết kế: bot không xoá bài). "
              "Trước --ap-dung: sudo -u postgres psql -d lang_nghe -c 'GRANT DELETE ON bai TO "
              "mark'; xong thì REVOKE DELETE ON bai FROM mark.")
    if not ns.ap_dung:
        in_ra("Không ghi gì. Ghi thật: thêm --ap-dung --sao-luu <tệp hoàn tác>.")
        return 0
    if kho["luot_chay"]:
        in_ra(f"Dự án có lượt /theodoi đang chạy (lượt {', '.join(map(str, kho['luot_chay']))}) — "
              "đợi lượt xong rồi chạy lại.")
        return 2
    if not kho["quyen_xoa"]:
        return 2
    kh = kho["kh"]
    nhom_duoc = set(_nhom_xoa(ns.gom_other_market))
    ds = [r["khoa"] for n in _nhom_xoa(ns.gom_other_market) for r in kh[n]]
    if not ds:
        in_ra("Không có bài nào để dọn.")
        return 0
    du_an = kho["du_an"]
    tu_pv = TDA.pham_vi(ma, bay_gio)[0]
    don: dict[str, int] = {n: 0 for n in NHOM}
    da_xoa: list[str] = []
    khong_con = loi = 0
    with open(ns.sao_luu, "x", encoding="utf-8") as so_luu:
        _ghi_dong(so_luu, {"loai_dong": "dau", "du_an": ma, "phien_ban": 1,
                           "lenh": "loc_khong_brand",
                           "luc": datetime.datetime.now(datetime.timezone.utc).isoformat(
                               timespec="seconds"), "ten_brand": kho["luat"].ten,
                           "gom_other_market": bool(ns.gom_other_market)})
        for j, khoa in enumerate(ds, 1):
            try:
                st, nhom = ap_dung_bai(du_an, kho["luat"], khoa, nhom_duoc, bay_gio, tu_pv,
                                       so_luu)
            except K.LoiKho as e:
                loi += 1
                in_ra(f"    {j}/{len(ds)} {khoa}: lỗi, đã huỷ giao dịch ({e})")
                continue
            if st == "dang_quet":
                in_ra(f"    {j}/{len(ds)}: lượt /theodoi vừa bắt đầu — DỪNG (chạy lại khi lượt "
                      "xong; bài đã dọn không bị dọn lại)")
                loi += 1
                break
            if st == "da_don":
                _ghi_dong(so_luu, {"loai_dong": "da_ap", "du_an": ma, "khoa": khoa})
                don[nhom] += 1
                da_xoa.append(khoa)
            else:
                khong_con += 1
    in_ra(f"Đã dọn {len(da_xoa)}/{len(ds)} bài ((a) không nhắc brand {don['khong_brand']}, (b) "
          f"other_market {don['other_market']}); {khong_con} bài đã đổi / không còn, {loi} lỗi "
          f"(chạy lại script để xử lý phần còn lại). Tệp hoàn tác: {ns.sao_luu}")
    _in_bigquery(ma, da_xoa, in_ra)
    # Quyền DELETE chỉ cấp TẠM cho lần chạy — nhắc thu lại (hoàn tác chỉ cần INSERT).
    in_ra("Xong: thu quyền xoá — sudo -u postgres psql -d lang_nghe -c 'REVOKE DELETE ON bai "
          "FROM mark'.")
    return 0 if not loi else 1


def tao_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Dọn bài đường từ khoá giữ theo luật không nhắc brand "
                                             "(+ other_market của dự án VN) đã có trong kho "
                                             "lang_nghe (mặc định chạy thử, không ghi).")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("--dry-run", action="store_true",
                    help="chạy thử (mặc định khi không có --ap-dung / --hoan-tac)")
    ap.add_argument("--ap-dung", action="store_true", help="ghi thật (cần --sao-luu)")
    ap.add_argument("--sao-luu", metavar="TEP", help="tệp hoàn tác JSONL (tạo mới)")
    ap.add_argument("--hoan-tac", metavar="TEP", help="trả lại từ tệp hoàn tác")
    ap.add_argument("--gom-other-market", action="store_true",
                    help="xoá cả nhóm (b) other_market (mặc định chỉ liệt kê để người quyết)")
    ap.add_argument("--mau", type=int, default=0,
                    help="số bài in ra mỗi nhóm (mặc định 0 = in hết để duyệt)")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = tao_parser()
    ns = ap.parse_args(argv)
    if ns.dry_run and (ns.ap_dung or ns.hoan_tac):
        ap.error("--dry-run không đi cùng --ap-dung / --hoan-tac")
    if ns.ap_dung and ns.hoan_tac:
        ap.error("--ap-dung và --hoan-tac là hai việc riêng")
    _dsn_tu_env_file()
    return chay(ns)


if __name__ == "__main__":
    sys.exit(main())
