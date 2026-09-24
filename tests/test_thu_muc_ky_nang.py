"""Canh thư mục `skills/` — nguồn DUY NHẤT cho kỹ năng của Mark.

`scripts/dong_bo_tieu_su.py` đọc thư mục này mỗi lần tạo version và đẩy nguyên nội dung
lên platform. Nên lỗi ở đây là lỗi thẳng vào prompt của bot: một kỹ năng thiếu câu "khi
nào dùng" thì mục lục không có gì để model chọn theo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_GOC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_GOC / "scripts"))

import dong_bo_tieu_su as D  # noqa: E402


def test_doc_duoc_moi_ky_nang():
    ks = D.doc_ky_nang()
    assert len(ks) == len(list(D.SKILLS.glob("*.md"))), "có file kỹ năng không đọc ra"


def test_cong_thuc_ma_khop_ma_platform_dang_dung():
    """Công thức lệch với `_upsert_custom_skills` thì mỗi lần đẩy là sinh bản trùng, và
    sáu kỹ năng cũ rụng khỏi version. Mã dưới đây là mã THẬT đang sống trên platform."""
    assert D.ma_ky_nang("Báo cáo dựa trên evidence") == "sk_7c28d5f2bb"
    assert D.ma_ky_nang("Phân tích quảng cáo đối thủ") == "sk_8776392ea3"


def test_ten_ky_nang_khong_trung():
    ten = [k["name"] for k in D.doc_ky_nang()]
    assert len(ten) == len(set(ten)), "hai file cùng một tên kỹ năng — một cái sẽ đè cái kia"


def test_khi_nao_dung_ngan_va_la_dieu_kien():
    """Dài thì mục lục lại phình thành thứ vừa bỏ đi. Bắt đầu bằng 'Khi'/'TRƯỚC' để nó là
    ĐIỀU KIỆN kích hoạt, không phải đoạn tả cách làm."""
    for k in D.doc_ky_nang():
        khi = k["description"]
        assert len(khi) <= 200, f"{k['name']}: 'khi nào dùng' dài {len(khi)} ký tự"
        assert khi.split()[0] in ("Khi", "TRƯỚC"), f"{k['name']}: không bắt đầu bằng điều kiện"


def test_khi_nao_dung_khong_phai_ban_cat_tu_than():
    """Đúng lỗi cũ của platform: `description` = 280 ký tự đầu của thân."""
    for k in D.doc_ky_nang():
        assert k["description"] not in k["instructions"], (
            f"{k['name']}: 'khi nào dùng' là đoạn chép từ thân — model không có gì để chọn")


def test_thieu_khi_nao_dung_thi_DUNG(tmp_path, monkeypatch):
    """Không lặng lẽ để platform tự cắt từ thân."""
    (tmp_path / "moi.md").write_text("# Kỹ năng chưa tả\n\nthân", encoding="utf-8")
    (tmp_path / "khi-nao-dung.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(D, "SKILLS", tmp_path)
    monkeypatch.setattr(D, "KHI_NAO_DUNG", tmp_path / "khi-nao-dung.json")
    with pytest.raises(SystemExit):
        D.doc_ky_nang()


def test_muc_mo_coi_trong_json_thi_DUNG(tmp_path, monkeypatch):
    ten = "Kỹ năng thật"
    (tmp_path / "that.md").write_text(f"# {ten}\n\nthân", encoding="utf-8")
    kn = {D.ma_ky_nang(ten): {"ten": ten, "khi_nao_dung": "Khi cần."},
          "sk_0000000000": {"ten": "đã đổi tên", "khi_nao_dung": "Khi cũ."}}
    (tmp_path / "khi-nao-dung.json").write_text(json.dumps(kn, ensure_ascii=False),
                                                encoding="utf-8")
    monkeypatch.setattr(D, "SKILLS", tmp_path)
    monkeypatch.setattr(D, "KHI_NAO_DUNG", tmp_path / "khi-nao-dung.json")
    with pytest.raises(SystemExit):
        D.doc_ky_nang()


def test_ky_nang_moi_khong_duoc_tu_thuc_thi():
    """Hai kỹ năng chuyển thể từ bộ gốc có bước TỰ THỰC THI thay đổi ngân sách và tự
    setup chiến dịch. Mark không có quyền đó và không được làm thế — chốt ngay trong văn
    bản để model đọc thấy."""
    for f, cam in (("ad-performance-audit.md", "Không bao giờ tự tăng, giảm, tắt"),
                   ("campaign-plan.md", "không tự setup")):
        assert cam in (D.SKILLS / f).read_text(encoding="utf-8"), f"{f} mất câu cấm thực thi"
