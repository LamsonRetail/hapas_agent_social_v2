"""Dọn bài SEEDING AFFILIATE đã nằm trong kho `lang_nghe` — script một lần (18/10/2026).

Vì sao: điều tra khoảng thiếu so với Kompa (18/10/2026) thấy khoảng 25 tài khoản affiliate TikTok
đăng 10–180 video HAPAS mỗi ngày, chỉ có hashtag, gần 0 bình luận. Chủ dự án chốt: KHÔNG đếm video
seeding affiliate. Từ bản này, lượt quét (/theodoi, social_listen) và script nạp raw bỏ bài seeding
TRƯỚC khi ghi (`theo_doi._loc_seeding`, luật `loc_rac.tai_khoan_seeding`); script này dọn phần ĐÃ
vào kho trước đó. Đo trên ảnh chụp kho 17/10: chỉ với kho thì bắt 11 tài khoản, 332 bài (417 thảo
luận); chạy SAU `scripts/lang_nghe_nap_raw.py` (sổ seeding đã có nhịp đăng từ raw Kompa) thì bắt 16
tài khoản, 377 bài (494 thảo luận) — nên nạp raw trước, dọn sau.

Luật: ĐÚNG `loc_rac.tai_khoan_seeding` với cấu hình hiệu lực của dự án (`du_an.cau_hinh.seeding`,
thiếu = mặc định `loc_rac.SEEDING_BAI`), trên bài đã giữ đăng từ mốc sớm hơn của (phạm vi theo dõi,
`ngay` ngày gần nhất) + sổ seeding. Kênh nhà và tài khoản mang tên brand không bao giờ bị bắt; bài
của tài khoản seeding mà tự có ≥ `giu_bl_tu` bình luận được giữ. Bài bị dọn chuyển sang sổ "đã loại"
của lượt tìm theo từ khoá (`.loai-tu-khoa.json`, lý do `seeding_affiliate`) + sổ seeding — lượt sau
gặp lại bài đó thì luật seeding xét lại trên số mới (vẫn seeding: không ghi, không gửi AI, không cào
bình luận; lên ≥ `giu_bl_tu` bình luận hay tài khoản hết đủ luật thì bài vào lại như bài mới —
`theo_doi.LY_DO_XET_LAI`) — rồi DELETE khỏi `bai` (bình luận + chi_so_ngay xoá theo FK ON DELETE
CASCADE).

An toàn (theo mẫu `scripts/lang_nghe_gop_bai_fb.py`):
  • Mặc định CHẠY THỬ: đọc trong MỘT giao dịch READ ONLY; in số tài khoản, bài, thảo luận, bình luận
    + chi_so_ngay đi theo, kèm mẫu từng tài khoản. Không ghi gì (kể cả sổ).
  • `--ap-dung --sao-luu <tệp>`: không chạy khi dự án có lượt `/theodoi` đang chạy. Mỗi TÀI KHOẢN
    một giao dịch: giữ khoá advisory mở lượt (CÙNG khoá `lang_nghe_db.mo_luot` — lượt mới chờ tài
    khoản này commit), kiểm lại lượt đang chạy, khoá dòng (FOR UPDATE), đọc lại (bài đã có thêm
    bình luận ≥ `giu_bl_tu` thì giữ), ghi tệp hoàn tác ĐỦ dòng bài + bình luận + chi_so_ngay (fsync)
    TRƯỚC, ghi sổ, rồi mới xoá. Dấu "đã áp" ghi SAU khi commit. Tệp có sẵn thì dừng.
  • `--hoan-tac <tệp>`: chèn lại bài, chi_so_ngay, bình luận của các tài khoản có dấu "đã áp" (dòng
    đã có lại thì để nguyên — ON CONFLICT DO NOTHING) và gỡ các khoá đó khỏi sổ. Chạy lại được.
  • Chạy lại script: bài đã dọn không còn trong kho — chỉ xử lý phần còn lại.

Quyền: role `mark` KHÔNG có DELETE trên `bai` (bot không xoá bài). Cấp TẠM cho lần chạy rồi thu lại;
hoàn tác chỉ cần INSERT (đã có):

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_loc_seeding.py hapas                        # chạy thử
    sudo -u postgres psql -d lang_nghe -c 'GRANT DELETE ON bai TO mark'
    sudo -u mark $PY scripts/lang_nghe_loc_seeding.py hapas --ap-dung \\
        --sao-luu /opt/mark/loc-seeding-$(date +%F).jsonl
    sudo -u postgres psql -d lang_nghe -c 'REVOKE DELETE ON bai FROM mark'
    sudo -u mark $PY scripts/lang_nghe_loc_seeding.py hapas --hoan-tac /opt/mark/loc-seeding-<ngày>.jsonl

Chạy SAU khi bản code có luật seeding đã lên VPS (bản cũ sẽ ghi lại bài seeding ở lượt sau) và sau
script nạp raw (nếu nạp). Sổ
nằm ở thư mục việc nền của Mark (`apify_tool._thu_muc_nen`, /opt/mark/app/.audit/viec-nen) — chạy
bằng user mark từ /opt/mark/app như lệnh trên. BigQuery: MERGE không xoá dòng — nếu đã bật đồng bộ
thì bài đã dọn phải xoá tay trên BigQuery (bản in nói số dòng `dong_bo_bq`).
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

# Mọi câu SQL mang thẻ `/* seed:<tên> */` — bộ thử nhận diện câu theo thẻ (kho giả).
SQL_CHI_DOC = "SET TRANSACTION READ ONLY"
SQL_DU_AN = ("/* seed:du_an */ SELECT ma, ten, tu_khoa, tu_loai_tru, boi_canh, thi_truong, "
             "cau_hinh FROM du_an WHERE ma = %s")
SQL_NGUON = "/* seed:nguon */ SELECT id, nen_tang, dinh_danh, loai FROM nguon WHERE du_an = %s"
SQL_BAI = ("/* seed:bai */ SELECT khoa, nen_tang, nguon_id, link, tai_khoan, tac_gia, dang_luc, "
           "binh_luan, xem FROM bai WHERE du_an = %s AND dang_luc >= %s AND "
           "btrim(tai_khoan) <> '' ORDER BY dang_luc, khoa")
SQL_DEM_BL = ("/* seed:dem_bl */ SELECT khoa_bai, count(*) AS n FROM binh_luan WHERE du_an = %s "
              "AND khoa_bai = ANY(%s) GROUP BY khoa_bai")
SQL_DEM_CS = ("/* seed:dem_cs */ SELECT khoa, count(*) AS n FROM chi_so_ngay WHERE du_an = %s "
              "AND khoa = ANY(%s) GROUP BY khoa")
SQL_QUYEN = "/* seed:quyen */ SELECT has_table_privilege(current_user, 'bai', 'DELETE') AS xoa"
SQL_LUOT_CHAY = ("/* seed:luot_chay */ SELECT id FROM luot_quet WHERE du_an = %s AND "
                 "trang_thai = 'dang_chay' AND bat_dau > now() - make_interval(hours => %s) "
                 "ORDER BY id")
SQL_DONG_BO = "/* seed:dong_bo */ SELECT count(*) AS n FROM dong_bo_bq"
SQL_KHOA_LUOT = "/* seed:khoa_luot */ " + K._SQL_KHOA_LUOT
SQL_KHOA_BAI = ("/* seed:khoa_bai */ SELECT * FROM bai WHERE du_an = %s AND khoa = ANY(%s) "
                "ORDER BY khoa FOR UPDATE")
SQL_KHOA_BL = ("/* seed:khoa_bl */ SELECT * FROM binh_luan WHERE du_an = %s AND "
               "khoa_bai = ANY(%s) ORDER BY khoa_bai, ma FOR UPDATE")
SQL_KHOA_CS = ("/* seed:khoa_cs */ SELECT * FROM chi_so_ngay WHERE du_an = %s AND "
               "khoa = ANY(%s) ORDER BY khoa, ngay FOR UPDATE")
SQL_XOA_BAI = "/* seed:xoa_bai */ DELETE FROM bai WHERE du_an = %s AND khoa = ANY(%s)"


# ───────────────────────────── tiện ích ─────────────────────────────
def _dsn_tu_env_file() -> None:
    """Mark đặt `LANG_NGHE_DSN` trong `.env` (deploy/lang-nghe/README.md §3): chỉ đọc ĐÚNG khoá
    đó, không nạp các bí mật khác vào tiến trình (như `lang_nghe_gop_bai_fb`)."""
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


def _mau_link(link: str) -> str:
    return str(link or "").split("?", 1)[0][:90]


# ───────────────────────────── kế hoạch (thuần) ─────────────────────────────
def ke_hoach(du_an: dict, nguon: list[dict], bai: list[dict], so_seeding: list[dict]) -> dict:
    """THUẦN. Bài đã giữ (khoa, nen_tang, link, tai_khoan, tac_gia, dang_luc, binh_luan, xem) + sổ
    seeding -> {"cfg", "tai_khoan": {tk: số đo}, "bo": {tk: [bài]}, "giu_bl": {tk: [bài]},
    "mien": {tk: số đo}}. `mien` = tài khoản ĐỦ luật nhưng là kênh nhà / mang tên brand (để người
    chạy thấy)."""
    import theo_doi as T
    cfg = loc_rac.cau_hinh_seeding(du_an)
    th = [str(du_an.get("ten") or ""), str(du_an.get("ma") or "")]
    rows = [{"tk": loc_rac.khoa_tai_khoan(r["nen_tang"], r["tai_khoan"]), "khoa": r["khoa"],
             "dang_luc": r["dang_luc"], "bl": r.get("binh_luan"), "xem": r.get("xem"),
             "ten": r.get("tac_gia") or ""}
            for r in bai if r.get("dang_luc") is not None]
    rows += [{"tk": loc_rac.khoa_tai_khoan(x["nen_tang"], x["tai_khoan"]), **x}
             for x in so_seeding]
    seed = loc_rac.tai_khoan_seeding(rows, cfg, T._kenh_nha(nguon), th)
    mien = {}
    if cfg["bat"]:
        tat = loc_rac.tai_khoan_seeding(rows, {**cfg, "mien_ten_brand": False})
        mien = {tk: x for tk, x in tat.items() if tk not in seed}
    bo: dict = {}
    giu_bl: dict = {}
    for r in bai:
        tk = loc_rac.khoa_tai_khoan(r["nen_tang"], r["tai_khoan"])
        if tk not in seed:
            continue
        (giu_bl if loc_rac.giu_bai_seeding(r.get("binh_luan"), cfg) else bo).setdefault(
            tk, []).append(r)
    return {"cfg": cfg, "tai_khoan": seed, "bo": bo, "giu_bl": giu_bl, "mien": mien}


def _dong_so(r: dict) -> dict:
    """Dòng `bai` (đầy đủ cột) → dạng `d` của lượt tìm, cho khoá ổn định Facebook của sổ."""
    return {"platform": r.get("nen_tang"), "username": r.get("tai_khoan"),
            "kenh": r.get("tac_gia"), "link": r.get("link"), "text": r.get("noi_dung"),
            "ma_so_fb": r.get("ma_so_fb")}


# ───────────────────────────── đọc ─────────────────────────────
def moc_xet(du_an: dict, bay_gio: datetime.datetime) -> datetime.datetime:
    """Mốc xét: sớm hơn của (đầu phạm vi theo dõi, `ngay` ngày gần nhất) — như `theo_doi._loc_seeding`."""
    import theo_doi_api as TDA
    cfg = loc_rac.cau_hinh_seeding(du_an)
    tu_pv = TDA.pham_vi(du_an["ma"], bay_gio)[0]
    return min(tu_pv, bay_gio - datetime.timedelta(days=cfg["ngay"]))


def doc_kho(ma: str, bay_gio: datetime.datetime) -> dict | None:
    """Dự án, nguồn, bài có tài khoản đăng từ mốc xét, số bình luận/chi_so_ngay đi theo, quyền,
    lượt đang chạy — MỘT giao dịch READ ONLY. None khi không có dự án."""
    import theo_doi_api as TDA
    with K.ket_noi() as c:
        c.execute(SQL_CHI_DOC)
        du_an = c.execute(SQL_DU_AN, (ma,)).fetchone()
        if not du_an:
            return None
        du_an = dict(du_an)
        tu = moc_xet(du_an, bay_gio)            # đọc lịch chiến dịch ở kết nối riêng
        nguon = [dict(r) for r in c.execute(SQL_NGUON, (ma,)).fetchall()]
        bai = [dict(r) for r in c.execute(SQL_BAI, (ma, tu)).fetchall()]
        kh = ke_hoach(du_an, nguon, bai, TDA.doc_seeding(ma, tu))
        khoa = sorted(r["khoa"] for cac in kh["bo"].values() for r in cac)
        bl = {r["khoa_bai"]: int(r["n"]) for r in c.execute(SQL_DEM_BL, (ma, khoa)).fetchall()} \
            if khoa else {}
        cs = {r["khoa"]: int(r["n"]) for r in c.execute(SQL_DEM_CS, (ma, khoa)).fetchall()} \
            if khoa else {}
        quyen = bool((c.execute(SQL_QUYEN).fetchone() or {}).get("xoa"))
        dang = [int(r["id"]) for r in c.execute(SQL_LUOT_CHAY, (ma, K.GIO_BO_DO)).fetchall()]
    return {"du_an": du_an, "nguon": nguon, "bai": bai, "tu": tu, "kh": kh, "dem_bl": bl,
            "dem_cs": cs, "quyen_xoa": quyen, "luot_chay": dang}


def dem_dong_bo() -> str:
    try:
        with K.ket_noi() as c:
            n = int((c.execute(SQL_DONG_BO).fetchone() or {}).get("n") or 0)
        return f"{n} dòng" + (" — CHƯA bật đồng bộ" if n == 0 else
                              " — ĐÃ đồng bộ: bài đã dọn phải xoá tay trên BigQuery")
    except K.LoiKho as e:
        return f"không đọc được ({e})"


# ───────────────────────────── ghi ─────────────────────────────
def ap_dung_tai_khoan(du_an: dict, tk: tuple, khoa: list[str], cfg: dict, dau: str,
                      tu_pv: datetime.datetime, so_luu) -> tuple[str, list[str]]:
    """Dọn MỘT tài khoản trong MỘT giao dịch: khoá mở lượt, kiểm lượt đang quét, khoá dòng, đọc
    lại, ghi tệp hoàn tác (fsync), ghi sổ, rồi xoá. -> (trạng thái, khoá đã xoá). Trạng thái:
    "da_don", "khong_con" (bài đã đổi/không còn — bỏ qua), "dang_quet" (lượt /theodoi vừa bắt
    đầu — dừng cả lần chạy)."""
    import theo_doi as T
    import theo_doi_api as TDA
    ma = du_an["ma"]
    with K.ket_noi() as c:
        c.execute(SQL_KHOA_LUOT, (K.so_khoa_luot(ma),))
        if c.execute(SQL_LUOT_CHAY, (ma, K.GIO_BO_DO)).fetchall():
            return "dang_quet", []
        bai = [dict(r) for r in c.execute(SQL_KHOA_BAI, (ma, khoa)).fetchall()]
        # Đọc lại: bài vừa có thêm bình luận (≥ ngưỡng giữ) thì giữ; tài khoản đổi (sửa tay) thì bỏ.
        bai = [r for r in bai if loc_rac.khoa_tai_khoan(r["nen_tang"], r["tai_khoan"]) == tk
               and not loc_rac.giu_bai_seeding(r.get("binh_luan"), cfg)]
        if not bai:
            return "khong_con", []
        ks = [r["khoa"] for r in bai]
        bl = [dict(r) for r in c.execute(SQL_KHOA_BL, (ma, ks)).fetchall()]
        cs = [dict(r) for r in c.execute(SQL_KHOA_CS, (ma, ks)).fetchall()]
        loai = [(k, loc_rac.LY_DO_SEEDING_BAI, r["dang_luc"])
                for r in bai for k in (r["khoa"], *T._khoa_loai_on_dinh(_dong_so(r), r["dang_luc"]))]
        _ghi_dong(so_luu, {"loai_dong": "tai_khoan", "du_an": ma, "tai_khoan": list(tk),
                           "bai": bai, "binh_luan": bl, "chi_so_ngay": cs,
                           "khoa_so": sorted({k for k, _, _ in loai})})
        TDA.ghi_loai(ma, dau, loai, tu_pv)
        TDA.ghi_seeding(ma, [{"khoa": r["khoa"], "nen_tang": r["nen_tang"],
                              "tai_khoan": tk[1], "dang_luc": r["dang_luc"],
                              "bl": r.get("binh_luan"), "xem": r.get("xem")} for r in bai])
        n = int(c.execute(SQL_XOA_BAI, (ma, ks)).rowcount or 0)
        if n != len(ks):
            raise K.LoiKho(f"xoá {n}/{len(ks)} bài của @{tk[1]} — huỷ giao dịch")
    return "da_don", ks


def _chen(c, bang: str, r: dict, xung_dot: str) -> int:
    """Chèn lại một dòng từ tệp hoàn tác (đã có thì thôi). `cap_nhat_cuoi` = now(): dòng trở lại
    kho là dòng ĐỔI với đồng bộ BigQuery."""
    cot = [k for k in r if k != "cap_nhat_cuoi"]
    dat = ", ".join(f"(SELECT id FROM {_FK_CON[k]} WHERE id = %s)" if k in _FK_CON else "%s"
                    for k in cot)
    moc = ("", "") if "cap_nhat_cuoi" not in r else (", cap_nhat_cuoi", ", now()")
    return int(c.execute(f"/* seed:hoan_{bang} */ INSERT INTO {bang} ({', '.join(cot)}{moc[0]}) "
                         f"VALUES ({dat}{moc[1]}) ON CONFLICT ({xung_dot}) DO NOTHING",
                         [r[k] for k in cot]).rowcount or 0)


def hoan_tac_tai_khoan(ma: str, x: dict) -> dict:
    """Trả lại MỘT tài khoản (một giao dịch): bài → chi_so_ngay → bình luận (thứ tự khoá ngoại);
    dòng đã có lại thì giữ dòng hiện tại. Gỡ các khoá khỏi sổ SAU khi commit. -> số dòng chèn."""
    import theo_doi_api as TDA
    n = {"bai": 0, "chi_so_ngay": 0, "binh_luan": 0}
    with K.ket_noi() as c:
        for r in x.get("bai") or []:
            n["bai"] += _chen(c, "bai", _tu_json(r), "du_an, khoa")
        for r in x.get("chi_so_ngay") or []:
            n["chi_so_ngay"] += _chen(c, "chi_so_ngay", _tu_json(r), "du_an, khoa, ngay")
        for r in x.get("binh_luan") or []:
            n["binh_luan"] += _chen(c, "binh_luan", _tu_json(r), "du_an, khoa_bai, ma")
    TDA.bo_khoi_so(ma, list(x.get("khoa_so") or []))
    return n


def doc_tep_hoan_tac(tep: str) -> tuple[dict, list[dict], list[dict]]:
    """-> (dòng đầu, tài khoản CÓ dấu đã áp, tài khoản KHÔNG có dấu). Dòng tài khoản ghi TRƯỚC khi
    xoá; giao dịch lỗi (rollback) thì không có dấu — không hoàn tác tự động phần đó."""
    dau, ds, da_ap = {}, [], set()
    with open(tep, encoding="utf-8") as f:
        for i, dong in enumerate(f):
            if not dong.strip():
                continue
            r = json.loads(dong)
            if i == 0 and r.get("loai_dong") == "dau":
                dau = r
            elif r.get("loai_dong") == "tai_khoan":
                ds.append(r)
            elif r.get("loai_dong") == "da_ap":
                da_ap.add((tuple(r.get("tai_khoan") or ()), tuple(sorted(r.get("khoa") or ()))))
    def dau_cua(r):
        return tuple(r.get("tai_khoan") or ()), tuple(sorted(b["khoa"] for b in r.get("bai") or []))
    return dau, [r for r in ds if dau_cua(r) in da_ap], [r for r in ds if dau_cua(r) not in da_ap]


# ───────────────────────────── in ─────────────────────────────
def _in_ke_hoach(kho: dict, mau: int, in_ra) -> None:
    kh, cfg = kho["kh"], kho["kh"]["cfg"]
    ma = kho["du_an"]["ma"]
    in_ra(f"Luật seeding hiệu lực: {'BẬT' if cfg['bat'] else 'TẮT'} — ≥ {cfg['bai_mot_ngay']} bài/"
          f"ngày hoặc ≥ {cfg['bai_bay_ngay']} bài/7 ngày, trung vị ≤ {cfg['trung_vi_bl']} bình "
          f"luận, trung vị ≤ {cfg['trung_vi_xem']} xem; giữ bài ≥ {cfg['giu_bl_tu']} bình luận.")
    bo = [r for cac in kh["bo"].values() for r in cac]
    giu = [r for cac in kh["giu_bl"].values() for r in cac]
    tl = sum(1 + int(r.get("binh_luan") or 0) for r in bo)
    in_ra(f"Bài có tài khoản đăng của {ma} từ {kho['tu'].astimezone(_VN):%d/%m}: {len(kho['bai'])}. "
          f"Tài khoản seeding: {len(kh['tai_khoan'])}. Sẽ chuyển sang sổ đã loại: {len(bo)} bài "
          f"({tl} thảo luận); giữ vì có ≥ {cfg['giu_bl_tu']} bình luận: {len(giu)} bài.")
    in_ra(f"Đi theo (xoá theo bài): {sum(kho['dem_bl'].values())} bình luận, "
          f"{sum(kho['dem_cs'].values())} dòng chi_so_ngay.")
    xep = sorted(kh["tai_khoan"].items(), key=lambda kv: (-len(kh["bo"].get(kv[0], [])), kv[0]))
    for tk, x in xep[:mau]:
        cac = kh["bo"].get(tk, [])
        in_ra(f"  {loc_rac.cau_seeding(tk, x)} → bỏ {len(cac)}, giữ "
              f"{len(kh['giu_bl'].get(tk, []))}")
        for r in cac[:2]:
            in_ra(f"      {r['dang_luc'].astimezone(_VN):%d/%m %H:%M} "
                  f"{int(r.get('binh_luan') or 0)} bl {_mau_link(r.get('link'))}")
    if len(xep) > mau:
        in_ra(f"  … và {len(xep) - mau} tài khoản nữa")
    if kh["mien"]:
        in_ra("Đủ luật nhưng MIỄN (kênh nhà / tên brand): "
              + ", ".join(f"@{tk[1]} ({x['max_ngay']} bài ngày {x['ngay']:%d/%m})"
                          for tk, x in sorted(kh["mien"].items())[:10]) + ".")
    in_ra(f"dong_bo_bq: {dem_dong_bo()}.")


def chay(ns, in_ra=print, bay_gio: datetime.datetime | None = None) -> int:
    import theo_doi as T
    import theo_doi_api as TDA
    ma = ns.du_an.strip().lower()
    if ns.hoan_tac:
        dau, ds, khong_dau = doc_tep_hoan_tac(ns.hoan_tac)
        if dau.get("du_an") and dau["du_an"] != ma:
            in_ra(f"Tệp hoàn tác của dự án '{dau['du_an']}', không phải '{ma}' — dừng.")
            return 2
        tong = {"bai": 0, "chi_so_ngay": 0, "binh_luan": 0}
        for x in [r for r in ds if r.get("du_an", ma) == ma]:
            for k, v in hoan_tac_tai_khoan(ma, x).items():
                tong[k] += v
        in_ra(f"Hoàn tác {ma}: {len(ds)} tài khoản — chèn lại {tong['bai']} bài, "
              f"{tong['chi_so_ngay']} dòng chi_so_ngay, {tong['binh_luan']} bình luận (dòng đã có "
              "lại thì giữ); đã gỡ khỏi sổ đã loại + sổ seeding.")
        if khong_dau:
            in_ra(f"{len(khong_dau)} tài khoản không có dấu đã áp (giao dịch lỗi đã huỷ) — KHÔNG "
                  "hoàn tác tự động: " + ", ".join(f"@{x['tai_khoan'][1]}" for x in khong_dau[:10]))
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
    _in_ke_hoach(kho, ns.mau, in_ra)
    if not kho["quyen_xoa"]:
        in_ra("Role hiện tại KHÔNG có quyền DELETE trên bai (đúng thiết kế: bot không xoá bài). "
              "Trước --ap-dung: sudo -u postgres psql -d lang_nghe -c 'GRANT DELETE ON bai TO "
              "mark'; xong thì REVOKE DELETE ON bai FROM mark.")
    if not ns.ap_dung:
        in_ra("Không ghi gì. Ghi thật: thêm --ap-dung --sao-luu <tệp hoàn tác>.")
        return 0
    if kho["luot_chay"]:
        in_ra(f"Dự án có lượt /theodoi đang chạy (lượt {', '.join(map(str, kho['luot_chay']))}) — đợi lượt xong rồi "
              "chạy lại.")
        return 2
    if not kho["quyen_xoa"]:
        return 2
    kh = kho["kh"]
    if not kh["bo"]:
        in_ra("Không có bài seeding nào để dọn.")
        return 0
    du_an = kho["du_an"]
    dau = TDA.dau_loai(du_an, T.tu_tim(du_an))
    tu_pv = TDA.pham_vi(ma, bay_gio)[0]
    don = khong_con = loi = so_bai = 0
    with open(ns.sao_luu, "x", encoding="utf-8") as so_luu:
        _ghi_dong(so_luu, {"loai_dong": "dau", "du_an": ma, "phien_ban": 1, "lenh": "loc_seeding",
                           "luc": datetime.datetime.now(datetime.timezone.utc).isoformat(
                               timespec="seconds"), "dau_luat": dau, "cfg": kh["cfg"]})
        for j, (tk, cac) in enumerate(sorted(kh["bo"].items()), 1):
            try:
                st, ks = ap_dung_tai_khoan(du_an, tk, [r["khoa"] for r in cac], kh["cfg"], dau,
                                           tu_pv, so_luu)
            except K.LoiKho as e:
                loi += 1
                in_ra(f"    {j}/{len(kh['bo'])} @{tk[1]}: lỗi, đã huỷ giao dịch ({e})")
                continue
            if st == "dang_quet":
                in_ra(f"    {j}/{len(kh['bo'])}: lượt /theodoi vừa bắt đầu — DỪNG (chạy lại khi "
                      "lượt xong; tài khoản đã dọn không bị dọn lại)")
                loi += 1
                break
            if st == "da_don":
                _ghi_dong(so_luu, {"loai_dong": "da_ap", "du_an": ma, "tai_khoan": list(tk),
                                   "khoa": ks})
                don += 1
                so_bai += len(ks)
            else:
                khong_con += 1
    in_ra(f"Đã dọn {don}/{len(kh['bo'])} tài khoản ({so_bai} bài); {khong_con} tài khoản không còn "
          f"bài cần dọn, {loi} lỗi (chạy lại script để xử lý phần còn lại). Tệp hoàn tác: "
          f"{ns.sao_luu}")
    return 0 if not loi else 1


def tao_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Dọn bài seeding affiliate đã có trong kho lang_nghe "
                                             "(mặc định chạy thử, không ghi).")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("--dry-run", action="store_true",
                    help="chạy thử (mặc định khi không có --ap-dung / --hoan-tac)")
    ap.add_argument("--ap-dung", action="store_true", help="ghi thật (cần --sao-luu)")
    ap.add_argument("--sao-luu", metavar="TEP", help="tệp hoàn tác JSONL (tạo mới)")
    ap.add_argument("--hoan-tac", metavar="TEP", help="trả lại từ tệp hoàn tác")
    ap.add_argument("--mau", type=int, default=12, help="số tài khoản mẫu in ra")
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
