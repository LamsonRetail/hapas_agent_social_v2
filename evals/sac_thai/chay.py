"""Đo nhãn SẮC THÁI + CHỦ ĐỀ bình luận trên tập chấm tay `bo_sac_thai.jsonl` (27/10/2026).

Vì sao có: team MKT (chủ định nghĩa nhãn) rà dashboard và ghi 19 bình luận gán sai (wiki "LỌC
BÌNH LUẬN SAI AI", 27/10/2026). Sửa prompt `phan_loai._NHAC` mà không đo thì không biết sửa có
ăn, có làm hỏng ca cũ không. Bộ này gán nhãn ĐÚNG đường của lượt cào / việc nền
(`phan_loai.phan_loai_binh_luan`, kèm ngữ cảnh bài + brand như `gan_nhan_nen.gan_lo_bl`) rồi
chấm từng ca và in độ chính xác sắc thái / chủ đề theo nhóm:
  • mkt_giu_lai — ca MKT KHÔNG nằm trong ví dụ của prompt: đây mới là con số công bằng;
  • mkt_vi_du   — ca MKT đã chép vào ví dụ của prompt (`vi_du: true`): chỉ để thấy model chép
                  đúng ví dụ, không dùng để khoe độ chính xác;
  • hoi_quy     — các ví dụ có sẵn trong prompt trước 27/10: sửa prompt không được làm hỏng.
Ca `loai_tru` (vd bài HAPAS Thái Lan — loại ở cấp BÀI, nhánh khác) vẫn gán để xem, KHÔNG chấm.

Định dạng một dòng JSONL: id, nhom (mkt|hoi_quy), nguon, bai (đầu bài chứa bình luận), binh_luan,
ai_cu ([sắc thái, chủ đề] AI gán trước khi sửa), sac_thai / chu_de mong đợi — một mã, DANH SÁCH
mã chấp nhận được, hoặc null khi MKT không nói (không chấm), mon (tuỳ chọn), loai_tru, vi_du,
can_cu (MKT ghi gì, chỗ nào là suy từ nguyên tắc).

Chạy (máy dev, Python có Hermes `run_agent`; gọi model THẬT, không ghi gì vào kho / Lark):
    <hermes>/venv/Scripts/python evals/sac_thai/chay.py --env D:/hapas_agent_social/.env --lan 3

An toàn: chỉ nạp .env để có cấu hình model; bỏ mọi biến LSR_*/PHOENIX_* (không xin lease, không
báo lượt, không trace lên platform), mặc định đi tài khoản AI của MÁY
(`MARK_THEO_TAI_KHOAN_CONSOLE=0`), chặn `tai_khoan_ai.bao_loi`. Không in giá trị biến nào.
Lưu ý: production xin lease console nên model có thể khác model máy — số đo là của model máy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

#: Biến làm runtime gọi platform (lease, báo lượt, trace) — không nạp khi đo.
_BO_BIEN = ("LSR_", "PHOENIX_")


def nap_env(tep: str | Path) -> int:
    """Nạp .env của Mark (KHÔNG in giá trị), bỏ biến platform. -> số biến đã nạp."""
    n = 0
    for d in Path(tep).read_text(encoding="utf-8").splitlines():
        d = d.strip()
        if not d or d.startswith("#") or "=" not in d:
            continue
        k, v = d.split("=", 1)
        k = k.strip()
        if k.startswith(_BO_BIEN):
            continue
        os.environ[k] = v.strip().strip('"').strip("'")
        n += 1
    for k in [k for k in os.environ if k.startswith(_BO_BIEN)]:
        os.environ.pop(k, None)
    os.environ["AUDIT_TO_BASE"] = "0"
    return n


if __name__ == "__main__":
    # `config` đòi LARK_APP_ID ngay lúc import → nạp .env TRƯỚC khi import phan_loai.
    _truoc = argparse.ArgumentParser(add_help=False)
    _truoc.add_argument("--env")
    _env = _truoc.parse_known_args()[0].env
    if _env:
        nap_env(_env)

import phan_loai as P

BO = Path(__file__).with_name("bo_sac_thai.jsonl")
#: Như `gan_nhan_nen.brand_du_an` của dự án hapas: tên + mô tả brand (cấu hình tin cậy).
BRAND = "HAPAS — thương hiệu Việt Nam: túi xách, ví, nước hoa, trang sức, set quà tặng"
NHOM = ("mkt_giu_lai", "mkt_vi_du", "hoi_quy")
_MA_SAC = {v: k for k, v in P.SAC_THAI.items()}
_MA_CD = {v: k for k, v in P.CHU_DE.items()}


def _chap_nhan(x) -> set[str] | None:
    """Mã mong đợi → tập mã chấp nhận được; None = không chấm."""
    if x is None:
        return None
    return {str(m) for m in (x if isinstance(x, list) else [x])}


def doc_bo(duong: Path | str = BO) -> list[dict]:
    """Đọc + kiểm tập chấm. Sai định dạng thì dừng hẳn, không chấm bằng dữ liệu hỏng."""
    ra, thay = [], set()
    for so, dong in enumerate(Path(duong).read_text(encoding="utf-8").splitlines(), 1):
        if not dong.strip():
            continue
        ca = json.loads(dong)
        loi = []
        if not ca.get("id") or ca["id"] in thay:
            loi.append("id rỗng hoặc trùng")
        if ca.get("nhom") not in ("mkt", "hoi_quy"):
            loi.append("nhom phải là mkt|hoi_quy")
        if not str(ca.get("binh_luan") or "").strip():
            loi.append("binh_luan rỗng")
        sac, cd = _chap_nhan(ca.get("sac_thai")), _chap_nhan(ca.get("chu_de"))
        if sac is not None and (not sac or not sac <= set(P.SAC_THAI)):
            loi.append("sac_thai lạ")
        if cd is not None and (not cd or not cd <= set(P.CHU_DE)):
            loi.append("chu_de lạ")
        if ca.get("mon") is not None and ca["mon"] not in P.SAN_PHAM:
            loi.append("mon lạ")
        if not ca.get("loai_tru") and sac is None and cd is None:
            loi.append("không có gì để chấm (thiếu cả sac_thai lẫn chu_de, không loai_tru)")
        if loi:
            raise ValueError(f"{Path(duong).name} dòng {so}: " + "; ".join(loi))
        thay.add(ca["id"])
        ra.append(ca)
    return ra


def nhom_cua(ca: dict) -> str | None:
    if ca.get("loai_tru"):
        return None
    if ca["nhom"] == "hoi_quy":
        return "hoi_quy"
    return "mkt_vi_du" if ca.get("vi_du") else "mkt_giu_lai"


def gan_nhan(cac_ca: list[dict], han_giay: float = 170.0, brand: str = BRAND) -> list[dict]:
    """Gán nhãn bằng đúng `phan_loai.phan_loai_binh_luan` (ngữ cảnh bài + brand như việc nền).
    Mỗi nhóm một lượt gọi (≤ 100 bình luận, ≤ 20 bài — trong trần của một lô thật).
    -> [{sac, cd, mon}] cùng thứ tự `cac_ca`; None = chưa phân loại."""
    ra: list[dict] = [{} for _ in cac_ca]
    for nhom in dict.fromkeys(c["nhom"] for c in cac_ca):
        chi_so = [i for i, c in enumerate(cac_ca) if c["nhom"] == nhom]
        rows = [{"text": cac_ca[i]["binh_luan"], "likes": 0,
                 "ngu_canh_bai": cac_ca[i].get("bai") or ""} for i in chi_so]
        nhan = P.phan_loai_binh_luan(rows, han_giay, {}, brand=brand, kem_san_pham=True)
        for i, (s, c, sp) in zip(chi_so, nhan):
            ra[i] = {"sac": _MA_SAC.get(s), "cd": _MA_CD.get(c), "mon": sp}
    return ra


def cham(ca: dict, du: dict) -> dict:
    """-> {sac, cd, mon}: True/False, None = không chấm (loại trừ / không có nhãn mong đợi).
    Dòng model bỏ sót (chưa phân loại) tính là SAI — đó cũng là một lỗi người đọc dashboard thấy."""
    if ca.get("loai_tru"):
        return {"sac": None, "cd": None, "mon": None}
    sac, cd = _chap_nhan(ca.get("sac_thai")), _chap_nhan(ca.get("chu_de"))
    return {"sac": None if sac is None else du.get("sac") in sac,
            "cd": None if cd is None else du.get("cd") in cd,
            "mon": None if ca.get("mon") is None else du.get("mon") == ca["mon"]}


def tong_hop(cac_ca: list[dict], cac_diem: list[dict]) -> dict:
    """-> {nhóm: {sac: [đúng, tổng], cd: [...], mon: [...]}}."""
    ra = {n: {"sac": [0, 0], "cd": [0, 0], "mon": [0, 0]} for n in NHOM}
    for ca, d in zip(cac_ca, cac_diem):
        n = nhom_cua(ca)
        if n is None:
            continue
        for k in ("sac", "cd", "mon"):
            if d[k] is not None:
                ra[n][k][0] += int(d[k])
                ra[n][k][1] += 1
    return ra


def _ty_le(x: list[int]) -> str:
    return f"{x[0]}/{x[1]} ({100 * x[0] / x[1]:.0f}%)" if x[1] else "—"


def _ma(x) -> str:
    if x is None:
        return "·"
    return "|".join(x) if isinstance(x, list) else str(x)


def in_mot_lan(cac_ca: list[dict], cac_du: list[dict], cac_diem: list[dict],
               in_ra=print) -> None:
    dau = {True: "✓", False: "✗", None: "·"}
    for ca, du, d in zip(cac_ca, cac_du, cac_diem):
        mong = f"{_ma(ca.get('sac_thai'))},{_ma(ca.get('chu_de'))}"
        duoc = f"{du.get('sac') or '?'},{du.get('cd') or '?'}"
        cu = ",".join(ca["ai_cu"]) if ca.get("ai_cu") else ""
        ghi = " [loại trừ: " + str(ca["loai_tru"]) + "]" if ca.get("loai_tru") else ""
        ghi += " [ví dụ]" if ca["nhom"] == "mkt" and ca.get("vi_du") else ""
        in_ra(f"  {ca['id']:<7} {dau[d['sac']]}{dau[d['cd']]} mong {mong:<10} được {duoc:<8}"
              f" cũ {cu:<6} {ca['binh_luan'][:60]}{ghi}")
    for n, v in tong_hop(cac_ca, cac_diem).items():
        in_ra(f"  {n:<12} sắc thái {_ty_le(v['sac']):<14} chủ đề {_ty_le(v['cd']):<14}"
              f" món {_ty_le(v['mon'])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Đo nhãn sắc thái/chủ đề bình luận trên tập chấm tay")
    ap.add_argument("--env", help="file .env của Mark (cấu hình model); bỏ trống = môi trường hiện tại")
    ap.add_argument("--lan", type=int, default=1, help="số lần chạy (đo độ dao động)")
    ap.add_argument("--console", action="store_true",
                    help="đi lease console như prod (mặc định: tài khoản AI của máy)")
    ap.add_argument("--bo", default=str(BO), help="tệp JSONL tập chấm")
    ap.add_argument("--json-ra", help="ghi kết quả từng lần ra tệp JSON")
    ns = ap.parse_args(argv)

    cac_ca = doc_bo(ns.bo)
    if ns.env:
        nap_env(ns.env)
    if not ns.console:
        os.environ["MARK_THEO_TAI_KHOAN_CONSOLE"] = "0"
    import tai_khoan_ai
    tai_khoan_ai.bao_loi = lambda *a, **k: False   # đo thử: không báo lỗi tài khoản lên platform

    cac_lan = []
    for lan in range(1, ns.lan + 1):
        t0 = time.monotonic()
        cac_du = gan_nhan(cac_ca)
        cac_diem = [cham(c, d) for c, d in zip(cac_ca, cac_du)]
        print(f"── lần {lan} ({time.monotonic() - t0:.0f}s)")
        in_mot_lan(cac_ca, cac_du, cac_diem)
        cac_lan.append({"du": cac_du, "diem": cac_diem, "tong": tong_hop(cac_ca, cac_diem)})
    if ns.lan > 1:
        print("── tổng các lần (đúng/tổng mỗi lần)")
        for n in NHOM:
            for k, ten in (("sac", "sắc thái"), ("cd", "chủ đề")):
                print(f"  {n:<12} {ten:<9} " + "  ".join(_ty_le(x["tong"][n][k]) for x in cac_lan))
        print("── ca dao động / sai ở ít nhất một lần")
        for i, ca in enumerate(cac_ca):
            sai = [x["diem"][i] for x in cac_lan]
            if any(d[k] is False for d in sai for k in ("sac", "cd")):
                duoc = " ".join(f"{x['du'][i].get('sac')},{x['du'][i].get('cd')}" for x in cac_lan)
                print(f"  {ca['id']:<7} mong {_ma(ca.get('sac_thai'))},{_ma(ca.get('chu_de'))}"
                      f"  được {duoc}  {ca['binh_luan'][:50]}")
    if ns.json_ra:
        Path(ns.json_ra).write_text(json.dumps(
            [{"id": c["id"], "lan": [x["du"][i] for x in cac_lan]} for i, c in enumerate(cac_ca)],
            ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
