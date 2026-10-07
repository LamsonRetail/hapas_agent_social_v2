"""Quản trị kho bài học chiến dịch (Hindsight) — người vận hành chạy tay, Mark không gọi.

    python scripts/bai_hoc_admin.py init-bank            [--thuc-hien]
    python scripts/bai_hoc_admin.py list                 [--gioi-han 50]
    python scripts/bai_hoc_admin.py delete <ma_bai_hoc>  [--thuc-hien]
    python scripts/bai_hoc_admin.py purge --older-than-days 365 [--thuc-hien]

MẶC ĐỊNH CHẠY THỬ (dry-run): chỉ in ra sẽ làm gì. Thêm `--thuc-hien` mới gửi lệnh ghi/xoá.

Cấu hình đọc từ biến môi trường như Mark (MARK_HINDSIGHT_URL, MARK_HINDSIGHT_API_KEY,
MARK_HINDSIGHT_BANK), hoặc `--env-file <đường dẫn .env>`. Không bao giờ in khoá.

`purge` xoá bài học có `created_at` (lúc Hindsight nhận tài liệu) cũ hơn N ngày — giữ 365
ngày theo chốt của chủ agent. `delete` dùng khi có yêu cầu xoá một bài cụ thể. Xoá trong
Hindsight KHÔNG sửa sổ cái JSONL (sổ chỉ thêm); nạp lại từ sổ thì lọc theo `ghi_luc`.
Chỉ dùng thư viện chuẩn: chạy được bằng bất kỳ python3 nào trên VPS.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_BANK_MAC_DINH = "hapas-mkt-bai-hoc"
#: Cấu hình bank: lưu nguyên văn (chunks), không quan sát/gộp (sẽ trộn nguồn gốc các bài),
#: không LLM. Memory Defense chặn thêm bí mật — lớp hai sau kiểm tra của Mark.
CAU_HINH_BANK = {
    "retain_extraction_mode": "chunks",
    "enable_observations": False,
    "retain_mission": ("Bài học chiến dịch marketing HAPAS: đã thử gì, kết quả đo được, đánh "
                       "giá, nguồn. Không lưu giá bán, khuyến mãi, quyền hạn hay dữ liệu cá "
                       "nhân khách hàng."),
}


def _nap_env(duong: str) -> None:
    for dong in open(duong, encoding="utf-8"):
        dong = dong.strip()
        if dong and not dong.startswith("#") and "=" in dong:
            k, v = dong.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _cau_hinh() -> tuple[str, str, str]:
    goc = os.environ.get("MARK_HINDSIGHT_URL", "").strip().rstrip("/")
    khoa = os.environ.get("MARK_HINDSIGHT_API_KEY", "").strip()
    if not (goc and khoa):
        sys.exit("Thiếu MARK_HINDSIGHT_URL hoặc MARK_HINDSIGHT_API_KEY (đặt env hoặc --env-file).")
    return goc, khoa, os.environ.get("MARK_HINDSIGHT_BANK", "").strip() or _BANK_MAC_DINH


def _goi(method: str, duong: str, body: dict | None = None, timeout: float = 20) -> dict:
    goc, khoa, _ = _cau_hinh()
    r = urllib.request.Request(
        goc + duong, method=method,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None,
        headers={"Authorization": f"Bearer {khoa}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            raw = x.read().decode("utf-8") or "{}"
    except urllib.error.HTTPError as e:
        sys.exit(f"Hindsight HTTP {e.code} cho {method} {duong}")
    return json.loads(raw)


def _duong_bank() -> str:
    return "/v1/default/banks/" + urllib.parse.quote(_cau_hinh()[2], safe="")


def liet_ke(gioi_han: int | None = None) -> list[dict]:
    """Mọi tài liệu mang tag `loai:bai_hoc` (lọc chặt: bỏ tài liệu không tag)."""
    ra, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"tags": "loai:bai_hoc", "tags_match": "all_strict",
                                    "limit": 100, "offset": offset})
        trang = _goi("GET", f"{_duong_bank()}/documents?{q}")
        items = trang.get("items") or []
        ra += items
        offset += len(items)
        if not items or offset >= int(trang.get("total") or 0) or (gioi_han and len(ra) >= gioi_han):
            return ra[:gioi_han] if gioi_han else ra


def _ngay_tao(doc: dict) -> datetime.datetime | None:
    s = str(doc.get("created_at") or "")
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def can_don(docs: list[dict], so_ngay: int, bay_gio: datetime.datetime | None = None) -> list[dict]:
    """Tài liệu cũ hơn `so_ngay`. Không đọc được ngày tạo thì GIỮ (không xoá khi nghi ngờ)."""
    moc = (bay_gio or datetime.datetime.now(datetime.timezone.utc)) - datetime.timedelta(days=so_ngay)
    return [d for d in docs if (_ngay_tao(d) or moc) < moc]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Quản trị kho bài học (Hindsight)")
    ap.add_argument("--env-file")
    sub = ap.add_subparsers(dest="lenh", required=True)
    p = sub.add_parser("init-bank")
    p.add_argument("--thuc-hien", action="store_true")
    p = sub.add_parser("list")
    p.add_argument("--gioi-han", type=int, default=50)
    p = sub.add_parser("delete")
    p.add_argument("ma_bai_hoc")
    p.add_argument("--thuc-hien", action="store_true")
    p = sub.add_parser("purge")
    p.add_argument("--older-than-days", type=int, default=365)
    p.add_argument("--thuc-hien", action="store_true")
    a = ap.parse_args(argv)
    if a.env_file:
        _nap_env(a.env_file)

    if a.lenh == "init-bank":
        print(f"Bank {_cau_hinh()[2]}: PUT cấu hình {json.dumps(CAU_HINH_BANK, ensure_ascii=False)}")
        if not a.thuc_hien:
            print("(chạy thử — thêm --thuc-hien để tạo/cập nhật bank)")
            return 0
        _goi("PUT", _duong_bank(), CAU_HINH_BANK)
        print("Đã tạo/cập nhật bank.")
        return 0

    if a.lenh == "list":
        for d in liet_ke(a.gioi_han):
            tag = ",".join(t for t in d.get("tags") or [] if not t.startswith("loai:"))
            print(f"{d.get('id')}\t{d.get('created_at')}\t{tag}")
        return 0

    if a.lenh == "delete":
        ma = a.ma_bai_hoc.strip()
        if not ma.startswith("bh-"):
            sys.exit("Mã bài học có dạng bh-<12 hex>.")
        print(f"Xoá tài liệu {ma} khỏi bank {_cau_hinh()[2]}")
        if not a.thuc_hien:
            print("(chạy thử — thêm --thuc-hien để xoá thật)")
            return 0
        kq = _goi("DELETE", f"{_duong_bank()}/documents/{urllib.parse.quote(ma, safe='')}")
        print(f"Đã xoá: {kq.get('memory_units_deleted', '?')} đơn vị nhớ.")
        return 0

    # purge
    cu = can_don(liet_ke(), a.older_than_days)
    print(f"{len(cu)} bài học cũ hơn {a.older_than_days} ngày:")
    for d in cu:
        print(f"  {d.get('id')}\t{d.get('created_at')}")
    if not a.thuc_hien:
        print("(chạy thử — thêm --thuc-hien để xoá thật)")
        return 0
    for d in cu:
        _goi("DELETE", f"{_duong_bank()}/documents/{urllib.parse.quote(str(d.get('id')), safe='')}")
    print(f"Đã xoá {len(cu)} bài học.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
