"""Gộp bài Facebook TRÙNG đã nằm trong kho `lang_nghe` — script MỘT LẦN (17/10/2026).

Vì sao cần: đo thật DB production 17/10/2026 — mỗi lượt cào, actor trả một pfbid KHÁC cho cùng
một bài Facebook, mà kho khoá bài theo pfbid (`bai.khoa` = "facebook:pfbid…"). 161 bài FB của
hapas có 24 nhóm trùng (cùng chủ bài + cùng phút đăng), 60 dòng, thừa 36: 22/24 nhóm cùng nội
dung (bản trùng thật), 2/24 nhóm khác nội dung (bài KHÁC nhau đăng cùng phút — KHÔNG gộp). Bài kênh
nhà hapaschinhhanggiatot 05/10 15:12 có 3 bản (bình luận báo / đã cào: 100/93, 100/94, 91/20);
bình luận bị cào lặp dưới nhiều bản (1.307 bình luận đang nằm dưới bài FB). Bản sửa lúc ghi
(`khu_trung_fb` + `lang_nghe_db.ghi_bai`) chỉ chặn bản trùng MỚI; script này gộp bản trùng CŨ.

Nhóm trùng = các dòng `khu_trung_fb.cung_bai` nối với nhau: chung id số (cột `ma_so_fb`, khoá
"facebook:<số>", id trong link), hoặc cùng chủ bài + cùng phút đăng + cùng nội dung. Chủ bài so
dạng gọn của tai_khoan / tac_gia / tên trong link — bắt cả bản lượt tìm theo từ khoá ghi tác giả
"HAPAS - Chính Hãng Giá Tốt" mà lượt theo dõi ghi "hapaschinhhanggiatot". Cùng chủ + cùng phút mà
khác nội dung (hoặc chữ rỗng, hoặc hai id actor trả khác nhau): KHÔNG gộp, chạy thử in riêng.

Quy tắc gộp một nhóm (mỗi nhóm MỘT giao dịch):
  • Giữ bản có `bl_da_lay` lớn nhất (chưa cào = thấp nhất); hoà thì bản `thay_lan_dau` sớm nhất.
  • xem / thich / binh_luan / chia_se: LỚN NHẤT của các bản — số luỹ kế chỉ tăng, bản nhỏ hơn là
    lần đọc cũ hơn hoặc actor đọc thiếu (vòng 2: like 12 → 24 → 25 giữa các bản; 05/10 15:12:
    bình luận 100/100/91). followers: bản có `luot_cuoi` mới nhất (số của tài khoản, có thể giảm).
  • thay_lan_dau sớm nhất, luot_dau nhỏ nhất, luot_cuoi lớn nhất; kieu_quet = theo_doi nếu một bản
    là theo_doi; khop_tu_khoa = có bản nào khớp; nguon_id của bản giữ (không có thì bản khác).
  • Nhãn (sac_thai, chu_de, ly_do_giu), link, nội dung, giờ đăng, bl_lay_luc, bl_lay_khi_co,
    bl_lan_thieu: của bản GIỮ; ô nào của bản giữ trống (NULL / chuỗi rỗng) thì lấy bản khác (cùng
    bài nên nhãn vẫn đúng — khỏi trả tiền AI gán lại). ma_so_fb: bản giữ, không có thì id duy
    nhất của nhóm (nhóm có hai id khác nhau thì để trống).
  • Bình luận của bản bỏ chuyển sang `khoa_bai` của bản giữ. Bình luận trùng (cùng `ma`, hoặc
    cùng tác giả + nội dung + thời điểm đăng) chỉ giữ MỘT dòng: dòng đã nằm dưới bản giữ thì giữ
    nó (nó thiếu nhãn mà bản trùng có nhãn thì nhận nhãn của bản trùng); không thì giữ dòng có
    nhãn (sắc thái, hoặc loai khác hop_le), hoà thì dòng thấy sớm nhất. `ma_cha` trỏ tới dòng bị
    bỏ thì đổi sang dòng giữ. bl_da_lay = max(bl_da_lay của bản giữ, số bình luận sau khi gộp).
  • chi_so_ngay: mỗi ngày lấy số LỚN NHẤT của các bản; ngày bản giữ chưa có thì chuyển dòng sang.
  • cap_nhat_cuoi = now() ở dòng bài / bình luận đã đổi (mốc đồng bộ BigQuery). Dòng bản bỏ:
    DELETE bài → bình luận + chi_so_ngay còn lại xoá theo (FK ON DELETE CASCADE).

Bảng tham chiếu `bai.khoa` / `binh_luan` (rà 17/10/2026): FK chỉ có binh_luan và chi_so_ngay (đã
xử lý ở trên). `de_xuat` theo định danh tài khoản, không theo khoá bài. `kiem_do_phu.bai_sot` chỉ
giữ bài TikTok (chạy thử đếm bài FB trong đó). Sổ "đã loại" của tìm theo từ khoá
(`.loai-tu-khoa.json`) chỉ giữ bài BỊ LOẠI (không có trong `bai`) — không đổi. Sổ bỏ qua của
gán nhãn nền theo khoá cũ: dòng chuyển chỉ được thử lại vài lần, vô hại. BigQuery: CHƯA bật
(`dong_bo_bq` 0 dòng, 17/10/2026) — bật sau thì nạp lần đầu từ Postgres đã gộp. Nếu đã bật trước
khi gộp: MERGE của bai/binh_luan không xoá dòng, phải xoá tay bản bỏ trên BigQuery.

An toàn (theo mẫu `scripts/lang_nghe_gan_lai.py`):
  • Mặc định CHẠY THỬ: mọi truy vấn trong MỘT giao dịch READ ONLY; in số nhóm, số bài bỏ, số bình
    luận chuyển / bỏ trùng, ngày chỉ số, kèm mẫu (tác giả bình luận đã băm). Không ghi gì.
  • `--ap-dung --sao-luu <tệp>`: không chạy khi dự án có lượt `/theodoi` đang chạy (bình luận cào
    dở dưới bản bỏ sẽ mất theo bài). Mỗi nhóm: khoá dòng (FOR UPDATE), ĐỌC LẠI, kiểm nhóm vẫn
    như lúc chạy thử, ghi tệp hoàn tác (đủ dòng bài bị xoá, dòng bình luận bị đổi hay xoá, dòng
    chi_so_ngay) + fsync TRƯỚC, rồi mới sửa, trong MỘT giao dịch. Tệp có sẵn thì dừng.
  • `--hoan-tac <tệp>`: nhóm nào đã áp dụng (bản bỏ không còn trong kho) thì chèn lại bài + bình
    luận + chỉ số đã xoá, chuyển bình luận về bản cũ, trả giá trị cũ cho các ô CÒN mang đúng giá
    trị script đã ghi (lượt quét sau đã đổi số thì giữ số mới). Chạy lại được.
  • Chạy lại script: nhóm đã gộp không còn là nhóm — chạy lại an toàn, chỉ xử lý phần còn lại.

Quyền: role `mark` KHÔNG có DELETE trên `bai` (schema.sql — bot không xoá bài). Cấp TẠM cho lần
chạy này rồi thu lại (xoá theo FK chạy bằng quyền chủ bảng, không cần DELETE trên bảng con):

    cd /opt/mark/app
    PY=/opt/mark/hermes-agent/venv/bin/python
    sudo -u mark $PY scripts/lang_nghe_gop_bai_fb.py hapas                        # chạy thử
    sudo -u postgres psql -d lang_nghe -c 'GRANT DELETE ON bai TO mark'
    sudo -u mark $PY scripts/lang_nghe_gop_bai_fb.py hapas --ap-dung \\
        --sao-luu /opt/mark/gop-bai-fb-$(date +%F).jsonl
    sudo -u postgres psql -d lang_nghe -c 'REVOKE DELETE ON bai FROM mark'
    sudo -u mark $PY scripts/lang_nghe_gop_bai_fb.py hapas --hoan-tac /opt/mark/gop-bai-fb-<ngày>.jsonl

Chạy SAU khi bản code mới (chặn trùng lúc ghi) đã lên VPS và schema.sql đã chạy (cột ma_so_fb):
bản cũ của Mark sẽ đẻ lại bản trùng ở lượt quét sau.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
import pathlib
import sys

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

import khu_trung_fb as KT
import lang_nghe_db as K

_VN = datetime.timezone(datetime.timedelta(hours=7))
SO = ("xem", "thich", "binh_luan", "chia_se")
NHAN_BL = ("loai", "ly_do_loc", "sac_thai", "chu_de", "san_pham", "cua_thuong_hieu")
#: Cột lấy của bản GIỮ, trống thì lấy bản khác (thứ tự bản trong nhóm).
_COT_GIU_TRONG = ("sac_thai", "chu_de", "ly_do_giu", "ma_noi_dung", "tai_khoan", "tac_gia",
                  "hashtag", "noi_dung", "nguon_id", "bl_lay_luc", "bl_lay_khi_co", "dang_luc")
_GIO = {"dang_luc", "thay_lan_dau", "cap_nhat_cuoi", "bl_lay_luc"}
_NGAY = {"ngay"}
#: Khoá ngoại tới bảng có thể đã xoá dòng: chèn lại qua truy vấn con (mất dòng cha thì NULL),
#: như `lang_nghe_db.ghi_bai`.
_FK_CON = {"nguon_id": "nguon", "luot_dau": "luot_quet", "luot_cuoi": "luot_quet",
           "luot_id": "luot_quet"}

# Mọi câu SQL mang thẻ `/* gop:<tên> */` — bộ thử nhận diện câu theo thẻ (kho giả).
SQL_CHI_DOC = "SET TRANSACTION READ ONLY"
SQL_DU_AN = "/* gop:du_an */ SELECT ma FROM du_an WHERE ma = %s"
SQL_BAI = ("/* gop:bai */ SELECT * FROM bai WHERE du_an = %s AND nen_tang = 'facebook' "
           "ORDER BY dang_luc, khoa")
SQL_BL = ("/* gop:bl */ SELECT * FROM binh_luan WHERE du_an = %s AND khoa_bai = ANY(%s) "
          "ORDER BY khoa_bai, ma")
SQL_CS = ("/* gop:cs */ SELECT * FROM chi_so_ngay WHERE du_an = %s AND khoa = ANY(%s) "
          "ORDER BY khoa, ngay")
SQL_DEM_BL = ("/* gop:dem_bl */ SELECT count(*) AS n FROM binh_luan b JOIN bai p ON "
              "p.du_an = b.du_an AND p.khoa = b.khoa_bai WHERE b.du_an = %s AND "
              "p.nen_tang = 'facebook'")
SQL_QUYEN = "/* gop:quyen */ SELECT has_table_privilege(current_user, 'bai', 'DELETE') AS xoa"
SQL_LUOT_CHAY = ("/* gop:luot_chay */ SELECT id FROM luot_quet WHERE du_an = %s AND "
                 "trang_thai = 'dang_chay' AND bat_dau > now() - make_interval(hours => %s) "
                 "ORDER BY id")
SQL_KDP = ("/* gop:kdp */ SELECT count(*) AS n FROM kiem_do_phu WHERE du_an = %s AND "
           "position('\"facebook:' in bai_sot::text) > 0")
SQL_DONG_BO = "/* gop:dong_bo */ SELECT count(*) AS n FROM dong_bo_bq"
# Ghi (mỗi nhóm một giao dịch): khoá dòng trước, đọc lại, rồi sửa.
SQL_KHOA_BAI = ("/* gop:khoa_bai */ SELECT * FROM bai WHERE du_an = %s AND khoa = ANY(%s) "
                "ORDER BY khoa FOR UPDATE")
SQL_KHOA_BL = ("/* gop:khoa_bl */ SELECT * FROM binh_luan WHERE du_an = %s AND "
               "khoa_bai = ANY(%s) ORDER BY khoa_bai, ma FOR UPDATE")
SQL_KHOA_CS = ("/* gop:khoa_cs */ SELECT * FROM chi_so_ngay WHERE du_an = %s AND "
               "khoa = ANY(%s) ORDER BY khoa, ngay FOR UPDATE")
SQL_CS_CHUYEN = ("/* gop:cs_chuyen */ UPDATE chi_so_ngay SET khoa = %s, xem = %s, thich = %s, "
                 "binh_luan = %s, chia_se = %s WHERE du_an = %s AND khoa = %s AND ngay = %s")
SQL_CS_GOP = ("/* gop:cs_gop */ UPDATE chi_so_ngay SET xem = %s, thich = %s, binh_luan = %s, "
              "chia_se = %s WHERE du_an = %s AND khoa = %s AND ngay = %s")
SQL_BL_CHUYEN = ("/* gop:bl_chuyen */ UPDATE binh_luan SET khoa_bai = %s, ma_cha = %s, "
                 "cap_nhat_cuoi = now() WHERE du_an = %s AND khoa_bai = %s AND ma = %s")
SQL_BL_NHAN = ("/* gop:bl_nhan */ UPDATE binh_luan SET loai = %s, ly_do_loc = %s, sac_thai = %s, "
               "chu_de = %s, san_pham = %s, cua_thuong_hieu = %s, cap_nhat_cuoi = now() "
               "WHERE du_an = %s AND khoa_bai = %s AND ma = %s")
SQL_XOA_BAI = "/* gop:xoa_bai */ DELETE FROM bai WHERE du_an = %s AND khoa = ANY(%s)"
# Hoàn tác.
SQL_HOAN_KIEM = "/* gop:hoan_kiem */ SELECT count(*) AS n FROM bai WHERE du_an = %s AND khoa = ANY(%s)"
SQL_HOAN_BL_CHUYEN = ("/* gop:hoan_bl_chuyen */ UPDATE binh_luan SET khoa_bai = %s, ma_cha = %s, "
                      "cap_nhat_cuoi = now() WHERE du_an = %s AND khoa_bai = %s AND ma = %s")


# ───────────────────────────── tiện ích ─────────────────────────────
def _dsn_tu_env_file() -> None:
    """Mark đặt `LANG_NGHE_DSN` trong `.env` (deploy/lang-nghe/README.md §3): chỉ đọc ĐÚNG khoá
    đó, không nạp các bí mật khác vào tiến trình (như `lang_nghe_loc_lai`)."""
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


def bam(tac_gia) -> str:
    """Tác giả bình luận trong bản in: băm, không in tên thật."""
    return "#" + hashlib.sha1(str(tac_gia or "").encode("utf-8")).hexdigest()[:8]


def _trong(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _lon_nhat(cac) -> int | None:
    so = [int(x) for x in cac if x is not None]
    return max(so) if so else None


def _nho_nhat(cac):
    so = [x for x in cac if x is not None]
    return min(so) if so else None


def _json(v):
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return str(v)


def _tu_json(r: dict | None) -> dict | None:
    """Giá trị đọc từ tệp hoàn tác → kiểu Python (giờ / ngày theo TÊN cột)."""
    if r is None:
        return None
    ra = {}
    for k, v in r.items():
        if isinstance(v, str) and k in _GIO:
            v = datetime.datetime.fromisoformat(v)
        elif isinstance(v, str) and k in _NGAY:
            v = datetime.date.fromisoformat(v)
        ra[k] = v
    return ra


def _gio_vn(dt) -> str:
    p = KT.phut(dt)
    return p.astimezone(_VN).strftime("%d/%m %H:%M") if p else "—"


# ───────────────────────────── tìm nhóm (thuần) ─────────────────────────────
class _Hop:
    def __init__(self, n: int):
        self.cha = list(range(n))

    def goc(self, i: int) -> int:
        while self.cha[i] != i:
            self.cha[i] = self.cha[self.cha[i]]
            i = self.cha[i]
        return i

    def noi(self, a: int, b: int) -> None:
        a, b = self.goc(a), self.goc(b)
        if a != b:
            self.cha[max(a, b)] = min(a, b)


def _ly_do_khong_gop(a: dict, b: dict) -> str:
    sa, sb = KT.la_so(a.get("ma_so_fb")), KT.la_so(b.get("ma_so_fb"))
    if sa and sb and sa != sb:
        return "id_so_khac"
    import loc_rac
    if not loc_rac.chuan(a.get("noi_dung") or "") and not loc_rac.chuan(b.get("noi_dung") or ""):
        return "khong_co_chu"
    return "khac_noi_dung"


def tim_nhom(rows: list[dict]) -> tuple[list[list[dict]], list[dict]]:
    """THUẦN. Bài Facebook của MỘT dự án -> (nhóm gộp — mỗi nhóm ≥ 2 dòng, theo thứ tự dòng vào;
    cặp CÙNG chủ + CÙNG phút mà không gộp: [{phut, chu, khoa: [a, b], ly_do}])."""
    hop = _Hop(len(rows))
    theo_phut: dict = collections.defaultdict(list)
    theo_id: dict = collections.defaultdict(list)
    for i, r in enumerate(rows):
        p = KT.phut(r.get("dang_luc"))
        if p is not None:
            theo_phut[p].append(i)
        for x in KT.cac_ma_so(r):
            theo_id[x].append(i)
    for cac in theo_id.values():
        for j in cac[1:]:
            hop.noi(cac[0], j)
    khong: list[dict] = []
    for p, cac in theo_phut.items():
        for x, i in enumerate(cac):
            for j in cac[x + 1:]:
                if KT.cung_bai(rows[i], rows[j]):
                    hop.noi(i, j)
    for p, cac in theo_phut.items():
        for x, i in enumerate(cac):
            for j in cac[x + 1:]:
                chung = KT.chu_bai(rows[i]) & KT.chu_bai(rows[j])
                if chung and hop.goc(i) != hop.goc(j):
                    khong.append({"phut": p, "chu": min(chung),
                                  "khoa": [rows[i]["khoa"], rows[j]["khoa"]],
                                  "ly_do": _ly_do_khong_gop(rows[i], rows[j])})
    nhom: dict[int, list[dict]] = {}
    for i, r in enumerate(rows):
        nhom.setdefault(hop.goc(i), []).append(r)
    return [g for g in nhom.values() if len(g) > 1], khong


def chon_giu(nhom: list[dict]) -> dict:
    """Bản GIỮ: `bl_da_lay` lớn nhất (chưa cào = thấp nhất), hoà thì `thay_lan_dau` sớm nhất."""
    xa = datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
    return min(nhom, key=lambda r: (-(r["bl_da_lay"] if r.get("bl_da_lay") is not None else -1),
                                    r.get("thay_lan_dau") or xa, r["khoa"]))


# ───────────────────────────── kế hoạch một nhóm (thuần) ─────────────────────────────
def _co_nhan(b: dict) -> bool:
    return b.get("sac_thai") is not None or (b.get("loai") or "hop_le") != "hop_le"


def _cum_binh_luan(bl: list[dict]) -> list[list[dict]]:
    """Bình luận cùng một nhóm bài -> các cụm TRÙNG (cùng `ma`, hoặc cùng tác giả + nội dung +
    thời điểm đăng). Cụm 1 dòng cũng trả (bình luận không trùng)."""
    hop = _Hop(len(bl))
    dau: dict = {}
    for i, b in enumerate(bl):
        khoa = [("ma", b["ma"])]
        nd = " ".join(str(b.get("noi_dung") or "").split())
        if b.get("dang_luc") is not None and nd:
            khoa.append(("tg", str(b.get("tac_gia") or "").strip().lower(), nd,
                         KT.phut(b["dang_luc"]) or b["dang_luc"]))
        for k in khoa:
            if k in dau:
                hop.noi(dau[k], i)
            else:
                dau[k] = i
    cum: dict[int, list[dict]] = {}
    for i, b in enumerate(bl):
        cum.setdefault(hop.goc(i), []).append(b)
    return list(cum.values())


def ke_hoach(nhom: list[dict], bl: list[dict], cs: list[dict]) -> dict:
    """THUẦN. Một nhóm bài trùng (dòng `bai` đầy đủ cột) + mọi bình luận + chi_so_ngay của chúng
    -> kế hoạch gộp (cũng là bản ghi tệp hoàn tác): bai_giu {cu, moi} (chỉ ô đổi), bai_bo (dòng
    đầy đủ), cs_doi, cs_bo, bl_chuyen, bl_nhan, bl_bo (dòng đầy đủ)."""
    giu = chon_giu(nhom)
    bo = [r for r in nhom if r["khoa"] != giu["khoa"]]
    thu_tu = [giu, *bo]
    cua_nhom = {r["khoa"] for r in nhom}
    bl = [b for b in bl if b["khoa_bai"] in cua_nhom]
    cs = [x for x in cs if x["khoa"] in cua_nhom]
    moi: dict = {}
    for k in SO:
        moi[k] = _lon_nhat(r.get(k) for r in thu_tu)
    co_luot = [r for r in thu_tu if r.get("luot_cuoi") is not None]
    moi["followers"] = (max(co_luot, key=lambda r: r["luot_cuoi"]) if co_luot else giu).get(
        "followers")
    if moi["followers"] is None:
        moi["followers"] = next((r.get("followers") for r in thu_tu
                                 if r.get("followers") is not None), None)
    moi["thay_lan_dau"] = _nho_nhat(r.get("thay_lan_dau") for r in thu_tu)
    moi["luot_dau"] = _nho_nhat(r.get("luot_dau") for r in thu_tu)
    moi["luot_cuoi"] = _lon_nhat(r.get("luot_cuoi") for r in thu_tu)
    moi["kieu_quet"] = "theo_doi" if any(r.get("kieu_quet") == "theo_doi" for r in thu_tu) \
        else giu.get("kieu_quet")
    moi["khop_tu_khoa"] = any(bool(r.get("khop_tu_khoa")) for r in thu_tu)
    for k in _COT_GIU_TRONG:
        moi[k] = next((r.get(k) for r in thu_tu if not _trong(r.get(k))), giu.get(k))
    if "ma_so_fb" in giu:
        ids = sorted({x for r in thu_tu for x in KT.cac_ma_so(r)})
        moi["ma_so_fb"] = KT.la_so(giu.get("ma_so_fb")) or (ids[0] if len(ids) == 1 else None)
    # Bình luận.
    cua_giu = {b["ma"] for b in bl if b["khoa_bai"] == giu["khoa"]}
    xa = datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
    bl_chuyen, bl_nhan, bl_bo = [], [], []
    doi_ma: dict[tuple[str, str], str] = {}        # (khoá bản bỏ, mã bị bỏ) -> mã dòng giữ
    cum_cua: list[tuple[list[dict], dict]] = []
    for cum in _cum_binh_luan(bl):
        tot = min(cum, key=lambda b: (not _co_nhan(b), b["khoa_bai"] != giu["khoa"],
                                      b.get("thay_lan_dau") or xa, b["khoa_bai"], b["ma"]))
        o_giu = [b for b in cum if b["khoa_bai"] == giu["khoa"]]
        song = o_giu[0] if o_giu else tot
        cum_cua.append((cum, song))
        for b in cum:
            if b["khoa_bai"] != giu["khoa"] and b is not song:
                doi_ma[(b["khoa_bai"], b["ma"])] = song["ma"]
        if o_giu and _co_nhan(tot) and tot["khoa_bai"] != giu["khoa"]:
            for b in o_giu:
                if not _co_nhan(b):
                    cu_n = {k: b.get(k) for k in NHAN_BL}
                    moi_n = {k: tot.get(k) for k in NHAN_BL}
                    moi_n["cua_thuong_hieu"] = bool(b.get("cua_thuong_hieu")) or bool(
                        tot.get("cua_thuong_hieu"))
                    if moi_n != cu_n:
                        bl_nhan.append({"ma": b["ma"], "cu": cu_n, "moi": moi_n})
    for cum, song in cum_cua:
        for b in cum:
            if b["khoa_bai"] == giu["khoa"]:
                continue
            if b is song:
                cha = b.get("ma_cha")
                cha_moi = doi_ma.get((b["khoa_bai"], cha), cha) if cha else cha
                bl_chuyen.append({"tu": b["khoa_bai"], "ma": b["ma"], "ma_cha_cu": cha,
                                  "ma_cha_moi": cha_moi})
            else:
                bl_bo.append(b)
    so_bl = len(cua_giu) + len(bl_chuyen)
    da_lay = giu.get("bl_da_lay")
    moi["bl_da_lay"] = max(int(da_lay or 0), so_bl) if (da_lay is not None or so_bl) else None
    moi["bl_lan_thieu"] = giu.get("bl_lan_thieu")
    doi = {k: v for k, v in moi.items() if k in giu and giu.get(k) != v}
    # chi_so_ngay: mỗi ngày số LỚN NHẤT của các bản.
    theo_ngay: dict = collections.defaultdict(list)
    for x in cs:
        theo_ngay[x["ngay"]].append(x)
    cs_doi = []
    for ngay, cac in sorted(theo_ngay.items()):
        gop = {k: _lon_nhat(x.get(k) for x in cac) for k in SO}
        cua_g = next((x for x in cac if x["khoa"] == giu["khoa"]), None)
        if cua_g is not None:
            cu_v = {k: cua_g.get(k) for k in SO}
            if cu_v != gop:
                cs_doi.append({"kieu": "gop", "tu": None, "ngay": ngay, "cu": cu_v, "moi": gop})
        else:
            x = cac[0]
            cs_doi.append({"kieu": "chuyen", "tu": x["khoa"], "ngay": ngay,
                           "cu": {k: x.get(k) for k in SO}, "moi": gop})
    khoa_bo = {r["khoa"] for r in bo}
    return {"giu": giu["khoa"], "bo": [r["khoa"] for r in bo],
            "bai_giu": {"cu": {k: giu.get(k) for k in doi}, "moi": doi},
            "bai_bo": bo, "cs_doi": cs_doi, "cs_bo": [x for x in cs if x["khoa"] in khoa_bo],
            "bl_chuyen": bl_chuyen, "bl_nhan": bl_nhan, "bl_bo": bl_bo,
            "mau": {"chu": sorted(KT.chu_bai(giu))[:1], "phut": _gio_vn(giu.get("dang_luc")),
                    "ban": [(r["khoa"], r.get("binh_luan"), r.get("bl_da_lay")) for r in thu_tu]}}


# ───────────────────────────── đọc ─────────────────────────────
def doc_kho(ma: str) -> dict | None:
    """Dự án, bài FB, bình luận + chi_so_ngay của bài trong nhóm, các số kiểm — MỘT giao dịch
    READ ONLY. None khi không có dự án."""
    with K.ket_noi() as c:
        c.execute(SQL_CHI_DOC)
        if not c.execute(SQL_DU_AN, (ma,)).fetchone():
            return None
        bai = [dict(r) for r in c.execute(SQL_BAI, (ma,)).fetchall()]
        nhom, khong = tim_nhom(bai)
        khoa = sorted({r["khoa"] for g in nhom for r in g})
        bl = [dict(r) for r in c.execute(SQL_BL, (ma, khoa)).fetchall()] if khoa else []
        cs = [dict(r) for r in c.execute(SQL_CS, (ma, khoa)).fetchall()] if khoa else []
        dem_bl = int((c.execute(SQL_DEM_BL, (ma,)).fetchone() or {}).get("n") or 0)
        quyen = bool((c.execute(SQL_QUYEN).fetchone() or {}).get("xoa"))
        dang = [int(r["id"]) for r in c.execute(SQL_LUOT_CHAY, (ma, K.GIO_BO_DO)).fetchall()]
        kdp = int((c.execute(SQL_KDP, (ma,)).fetchone() or {}).get("n") or 0)
    return {"bai": bai, "nhom": nhom, "khong": khong, "bl": bl, "cs": cs, "dem_bl": dem_bl,
            "quyen_xoa": quyen, "luot_chay": dang, "kdp_fb": kdp}


def dem_dong_bo() -> str:
    """Số dòng `dong_bo_bq` (mốc đồng bộ BigQuery) — role mark không có quyền đọc bảng này thì
    nói rõ, không coi là lỗi."""
    try:
        with K.ket_noi() as c:
            n = int((c.execute(SQL_DONG_BO).fetchone() or {}).get("n") or 0)
        return f"{n} dòng" + (" — CHƯA bật đồng bộ" if n == 0 else
                              " — ĐÃ đồng bộ: bản bỏ phải xoá tay trên BigQuery")
    except K.LoiKho as e:
        return f"không đọc được ({e}); 17/10/2026: 0 dòng, chưa bật"


def _ke_hoach_tu_kho(kho: dict) -> list[dict]:
    theo_bl = collections.defaultdict(list)
    for b in kho["bl"]:
        theo_bl[b["khoa_bai"]].append(b)
    theo_cs = collections.defaultdict(list)
    for x in kho["cs"]:
        theo_cs[x["khoa"]].append(x)
    ra = []
    for g in kho["nhom"]:
        ks = [r["khoa"] for r in g]
        ra.append(ke_hoach(g, [b for k in ks for b in theo_bl[k]],
                           [x for k in ks for x in theo_cs[k]]))
    return ra


# ───────────────────────────── ghi ─────────────────────────────
def _chen(c, bang: str, r: dict, xung_dot: str) -> int:
    cot = list(r)
    dat = ", ".join(f"(SELECT id FROM {_FK_CON[k]} WHERE id = %s)" if k in _FK_CON else "%s"
                    for k in cot)
    return int(c.execute(f"/* gop:hoan_{bang} */ INSERT INTO {bang} ({', '.join(cot)}) VALUES "
                         f"({dat}) ON CONFLICT ({xung_dot}) DO NOTHING",
                         [r[k] for k in cot]).rowcount or 0)


def _ghi_tep(so_luu, ma: str, kh: dict) -> None:
    x = {"loai_dong": "nhom", "du_an": ma, **{k: v for k, v in kh.items() if k != "mau"}}
    so_luu.write(json.dumps(x, ensure_ascii=False, default=_json) + "\n")
    so_luu.flush()
    os.fsync(so_luu.fileno())


def ap_dung_nhom(ma: str, khoa: list[str], so_luu) -> tuple[str, dict | None]:
    """Gộp MỘT nhóm trong MỘT giao dịch: khoá dòng, đọc lại, kiểm nhóm còn nguyên, ghi tệp hoàn
    tác (fsync), rồi sửa. -> (trạng thái, kế hoạch đã áp). Trạng thái: "da_gop", "doi" (nhóm
    đổi từ lúc chạy thử — bỏ qua, chạy lại script), "dang_quet" (lượt /theodoi vừa bắt đầu —
    dừng cả lượt gộp: bình luận cào dở dưới bản bỏ sẽ mất theo bài)."""
    with K.ket_noi() as c:
        if c.execute(SQL_LUOT_CHAY, (ma, K.GIO_BO_DO)).fetchall():
            return "dang_quet", None
        bai = [dict(r) for r in c.execute(SQL_KHOA_BAI, (ma, khoa)).fetchall()]
        nhom, _ = tim_nhom(bai)
        if len(bai) != len(khoa) or len(nhom) != 1 or len(nhom[0]) != len(khoa):
            return "doi", None
        bl = [dict(r) for r in c.execute(SQL_KHOA_BL, (ma, khoa)).fetchall()]
        cs = [dict(r) for r in c.execute(SQL_KHOA_CS, (ma, khoa)).fetchall()]
        kh = ke_hoach(nhom[0], bl, cs)
        _ghi_tep(so_luu, ma, kh)
        g = kh["giu"]
        for x in kh["cs_doi"]:
            v = [x["moi"][k] for k in SO]
            if x["kieu"] == "chuyen":
                c.execute(SQL_CS_CHUYEN, (g, *v, ma, x["tu"], x["ngay"]))
            else:
                c.execute(SQL_CS_GOP, (*v, ma, g, x["ngay"]))
        for x in kh["bl_chuyen"]:
            c.execute(SQL_BL_CHUYEN, (g, x["ma_cha_moi"], ma, x["tu"], x["ma"]))
        for x in kh["bl_nhan"]:
            c.execute(SQL_BL_NHAN, (*[x["moi"][k] for k in NHAN_BL], ma, g, x["ma"]))
        doi = kh["bai_giu"]["moi"]
        if doi:
            dat = ", ".join(f"{k} = (SELECT id FROM {_FK_CON[k]} WHERE id = %s)" if k in _FK_CON
                            else f"{k} = %s" for k in doi)
            c.execute(f"/* gop:sua_bai */ UPDATE bai SET {dat}, cap_nhat_cuoi = now() "
                      "WHERE du_an = %s AND khoa = %s", [*doi.values(), ma, g])
        n = int(c.execute(SQL_XOA_BAI, (ma, kh["bo"])).rowcount or 0)
        if n != len(kh["bo"]):
            raise K.LoiKho(f"xoá {n}/{len(kh['bo'])} bản bỏ của nhóm {g} — huỷ giao dịch")
    return "da_gop", kh


def hoan_tac_nhom(ma: str, kh: dict) -> str:
    """Trả lại MỘT nhóm (một giao dịch). -> "da_tra" | "bo_qua" (bản bỏ còn trong kho: nhóm chưa
    áp dụng, hoặc đã hoàn tác)."""
    g = kh["giu"]
    with K.ket_noi() as c:
        n = int((c.execute(SQL_HOAN_KIEM, (ma, kh["bo"])).fetchone() or {}).get("n") or 0)
        if n:
            return "bo_qua"
        for r in kh["bai_bo"]:
            _chen(c, "bai", _tu_json(r), "du_an, khoa")
        cu, moi = _tu_json(kh["bai_giu"]["cu"]), _tu_json(kh["bai_giu"]["moi"])
        if moi:
            dat, ts = [], []
            for k in moi:
                dat.append(f"{k} = CASE WHEN {k} IS NOT DISTINCT FROM %s THEN %s ELSE {k} END")
                ts += [moi[k], cu.get(k)]
            c.execute(f"/* gop:hoan_giu */ UPDATE bai SET {', '.join(dat)}, cap_nhat_cuoi = "
                      "now() WHERE du_an = %s AND khoa = %s", [*ts, ma, g])
        for x in kh["cs_doi"]:
            ngay = datetime.date.fromisoformat(x["ngay"]) if isinstance(x["ngay"], str) \
                else x["ngay"]
            kiem = " AND ".join(f"{k} IS NOT DISTINCT FROM %s" for k in SO)
            v_cu, v_moi = [x["cu"][k] for k in SO], [x["moi"][k] for k in SO]
            if x["kieu"] == "chuyen":
                c.execute("/* gop:hoan_cs_chuyen */ UPDATE chi_so_ngay SET khoa = %s, xem = %s, "
                          "thich = %s, binh_luan = %s, chia_se = %s WHERE du_an = %s AND "
                          f"khoa = %s AND ngay = %s AND {kiem}",
                          (x["tu"], *v_cu, ma, g, ngay, *v_moi))
            else:
                c.execute("/* gop:hoan_cs_gop */ UPDATE chi_so_ngay SET xem = %s, thich = %s, "
                          "binh_luan = %s, chia_se = %s WHERE du_an = %s AND khoa = %s AND "
                          f"ngay = %s AND {kiem}", (*v_cu, ma, g, ngay, *v_moi))
        for x in kh["cs_bo"]:
            _chen(c, "chi_so_ngay", _tu_json(x), "du_an, khoa, ngay")
        for x in kh["bl_chuyen"]:
            c.execute(SQL_HOAN_BL_CHUYEN, (x["tu"], x["ma_cha_cu"], ma, g, x["ma"]))
        for x in kh["bl_nhan"]:
            dat, ts = [], []
            for k in NHAN_BL:
                dat.append(f"{k} = CASE WHEN {k} IS NOT DISTINCT FROM %s THEN %s ELSE {k} END")
                ts += [x["moi"][k], x["cu"][k]]
            c.execute(f"/* gop:hoan_bl_nhan */ UPDATE binh_luan SET {', '.join(dat)}, "
                      "cap_nhat_cuoi = now() WHERE du_an = %s AND khoa_bai = %s AND ma = %s",
                      [*ts, ma, g, x["ma"]])
        for b in kh["bl_bo"]:
            _chen(c, "binh_luan", _tu_json(b), "du_an, khoa_bai, ma")
    return "da_tra"


def doc_tep_hoan_tac(tep: str) -> tuple[dict, list[dict]]:
    dau, nhom = {}, []
    with open(tep, encoding="utf-8") as f:
        for i, x in enumerate(f):
            if not x.strip():
                continue
            r = json.loads(x)
            if i == 0 and r.get("loai_dong") == "dau":
                dau = r
            elif r.get("loai_dong") == "nhom" and r.get("giu") and r.get("bo"):
                nhom.append(r)
    return dau, nhom


# ───────────────────────────── in ─────────────────────────────
_LY_DO = {"khac_noi_dung": "khác nội dung (bài khác đăng cùng phút)",
          "khong_co_chu": "cả hai không có chữ (ảnh không chú thích — không chứng minh được trùng)",
          "id_so_khac": "hai id số actor trả khác nhau"}


def _in_ke_hoach(ma: str, kho: dict, cac: list[dict], mau: int, in_ra) -> None:
    so_bo = sum(len(k["bo"]) for k in cac)
    so_dong = sum(len(k["bo"]) + 1 for k in cac)
    in_ra(f"Bài Facebook của {ma}: {len(kho['bai'])} dòng; {kho['dem_bl']} bình luận dưới bài FB.")
    in_ra(f"Nhóm trùng sẽ gộp: {len(cac)} nhóm, {so_dong} dòng → bỏ {so_bo} dòng, giữ "
          f"{len(cac)}.")
    in_ra(f"Bình luận: chuyển sang bản giữ {sum(len(k['bl_chuyen']) for k in cac)}; bỏ trùng "
          f"{sum(len(k['bl_bo']) for k in cac)} (xoá theo bài); dòng của bản giữ nhận nhãn của "
          f"bản trùng {sum(len(k['bl_nhan']) for k in cac)}.")
    in_ra(f"chi_so_ngay: chuyển {sum(1 for k in cac for x in k['cs_doi'] if x['kieu'] == 'chuyen')}"
          f" ngày sang bản giữ, gộp số lớn nhất vào {sum(1 for k in cac for x in k['cs_doi'] if x['kieu'] == 'gop')}"
          f" ngày đã có; {len([x for k in cac for x in k['cs_bo']])} dòng của bản bỏ (xoá theo bài "
          "sau khi chuyển).")
    in_ra("Chọn số: xem/thich/binh_luan/chia_se lấy LỚN NHẤT (luỹ kế); followers theo lần đọc mới "
          "nhất; thay_lan_dau sớm nhất, luot_dau nhỏ nhất; nhãn của bản giữ (trống thì bản khác).")
    for k in cac[:mau]:
        ban = "; ".join(f"{kh[-12:]} {bl if bl is not None else '—'}/"
                        f"{da if da is not None else '—'}" for kh, bl, da in k["mau"]["ban"])
        in_ra(f"  [{(k['mau']['chu'] or ['?'])[0]} {k['mau']['phut']}] giữ …{k['giu'][-12:]} "
              f"(bản: bình luận báo/đã cào {ban}); bỏ {len(k['bo'])}, chuyển "
              f"{len(k['bl_chuyen'])} bl, bỏ trùng {len(k['bl_bo'])} bl")
        for b in k["bl_bo"][:2]:
            nd = " ".join(str(b.get("noi_dung") or "").split())
            in_ra(f"      bỏ trùng [{bam(b.get('tac_gia'))}] \"{nd[:70]}\"")
    dem = collections.Counter(x["ly_do"] for x in kho["khong"])
    in_ra(f"Cùng chủ + cùng phút mà KHÔNG gộp: {len(kho['khong'])} cặp"
          + (f" ({', '.join(f'{_LY_DO[k]}: {v}' for k, v in dem.items())})" if dem else "") + ".")
    for x in kho["khong"][:mau]:
        in_ra(f"  [{x['chu']} {_gio_vn(x['phut'])}] {x['khoa'][0][-14:]} ≠ {x['khoa'][1][-14:]}: "
              f"{_LY_DO[x['ly_do']]}")
    in_ra(f"Tham chiếu: kiem_do_phu.bai_sot có bài FB ở {kho['kdp_fb']} lượt kiểm (chỉ TikTok "
          f"là đúng); dong_bo_bq: {dem_dong_bo()}; de_xuat theo định danh tài khoản (không đổi).")


def chay(ns, in_ra=print) -> int:
    ma = ns.du_an.strip().lower()
    if ns.hoan_tac:
        dau, nhom = doc_tep_hoan_tac(ns.hoan_tac)
        if dau.get("du_an") and dau["du_an"] != ma:
            in_ra(f"Tệp hoàn tác của dự án '{dau['du_an']}', không phải '{ma}' — dừng.")
            return 2
        tra = bo = 0
        for kh in reversed([x for x in nhom if x.get("du_an", ma) == ma]):
            if hoan_tac_nhom(ma, kh) == "da_tra":
                tra += 1
            else:
                bo += 1
        in_ra(f"Hoàn tác {ma}: trả lại {tra}/{len(nhom)} nhóm; {bo} nhóm bỏ qua (bản bỏ còn "
              "trong kho — nhóm chưa áp dụng hoặc đã hoàn tác).")
        return 0
    if ns.ap_dung and not ns.sao_luu:
        in_ra("--ap-dung cần --sao-luu <tệp> (tệp hoàn tác ghi TRƯỚC khi sửa kho).")
        return 2
    if ns.ap_dung and os.path.exists(ns.sao_luu):
        in_ra(f"Tệp {ns.sao_luu} đã có — chọn tên khác (không ghi đè tệp hoàn tác cũ).")
        return 2
    kho = doc_kho(ma)
    if kho is None:
        in_ra(f"Không có dự án '{ma}' trong kho.")
        return 2
    cac = _ke_hoach_tu_kho(kho)
    che_do = "ÁP DỤNG" if ns.ap_dung else "CHẠY THỬ (giao dịch chỉ đọc, không ghi gì)"
    in_ra(f"Dự án {ma} — {che_do}.")
    _in_ke_hoach(ma, kho, cac, ns.mau, in_ra)
    if not kho["quyen_xoa"]:
        in_ra("Role hiện tại KHÔNG có quyền DELETE trên bai (đúng thiết kế: bot không xoá bài). "
              "Trước --ap-dung: sudo -u postgres psql -d lang_nghe -c 'GRANT DELETE ON bai TO "
              "mark'; xong thì REVOKE DELETE ON bai FROM mark.")
    if not ns.ap_dung:
        in_ra("Không ghi gì. Ghi thật: thêm --ap-dung --sao-luu <tệp hoàn tác>.")
        return 0
    if kho["luot_chay"]:
        in_ra(f"Dự án có lượt /theodoi đang chạy (lượt {kho['luot_chay']}) — bình luận cào dở dưới "
              "bản bỏ sẽ mất theo bài. Đợi lượt xong rồi chạy lại.")
        return 2
    if not kho["quyen_xoa"]:
        return 2
    if not cac:
        in_ra("Không có nhóm nào để gộp.")
        return 0
    gop = doi = loi = 0
    with open(ns.sao_luu, "x", encoding="utf-8") as so_luu:
        so_luu.write(json.dumps({
            "loai_dong": "dau", "du_an": ma, "phien_ban": 1, "lenh": "gop_bai_fb",
            "luc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
            ensure_ascii=False) + "\n")
        so_luu.flush()
        for j, kh in enumerate(cac, 1):
            try:
                st, _ = ap_dung_nhom(ma, [kh["giu"], *kh["bo"]], so_luu)
            except K.LoiKho as e:
                loi += 1
                in_ra(f"    nhóm {j}/{len(cac)} …{kh['giu'][-12:]}: lỗi, đã huỷ giao dịch ({e})")
                continue
            if st == "dang_quet":
                in_ra(f"    nhóm {j}/{len(cac)}: lượt /theodoi vừa bắt đầu — DỪNG (chạy lại khi "
                      "lượt xong; nhóm đã gộp không bị gộp lại)")
                loi += 1
                break
            if st == "da_gop":
                gop += 1
            else:
                doi += 1
                in_ra(f"    nhóm {j}/{len(cac)} …{kh['giu'][-12:]}: đổi từ lúc đọc — bỏ qua")
    in_ra(f"Đã gộp {gop}/{len(cac)} nhóm; {doi} nhóm đổi từ lúc đọc, {loi} nhóm lỗi (chạy lại "
          f"script để xử lý phần còn lại). Tệp hoàn tác: {ns.sao_luu}")
    return 0 if not loi else 1


def tao_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Gộp bài Facebook trùng (pfbid đổi mỗi lượt cào) "
                                             "trong kho lang_nghe (mặc định chạy thử, không ghi).")
    ap.add_argument("du_an", help="mã dự án, vd hapas")
    ap.add_argument("--dry-run", action="store_true",
                    help="chạy thử (mặc định khi không có --ap-dung / --hoan-tac)")
    ap.add_argument("--ap-dung", action="store_true", help="ghi thật (cần --sao-luu)")
    ap.add_argument("--sao-luu", metavar="TEP", help="tệp hoàn tác JSONL (tạo mới)")
    ap.add_argument("--hoan-tac", metavar="TEP", help="trả lại từ tệp hoàn tác")
    ap.add_argument("--mau", type=int, default=8, help="số nhóm mẫu in ra")
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
