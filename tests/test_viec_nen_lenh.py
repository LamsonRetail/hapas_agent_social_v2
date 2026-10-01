"""Lệnh `/viec` và chính sách của hai tool việc nền (tra_viec_nen chỉ đọc, huy_viec_nen
đòi write_data như cancel_reminder)."""
from __future__ import annotations

from test_viec_nen import _quet, nen  # noqa: F401  (fixture dùng chung)


def test_lenh_viec_tra_loi_thang_tu_so(nen):
    import lenh_cung
    kq = _quet()
    r = lenh_cung.xu_ly("/viec")
    assert r.tra_loi_thang and kq["ma_viec"] in r.tra_loi_thang and r.lenh == "/viec"
    assert "/viec" in lenh_cung.xu_ly("/help").tra_loi_thang


def test_policy_tool_viec_nen():
    import lsr_policy
    assert "tra_viec_nen" in lsr_policy._SAFE_EXACT
    assert lsr_policy._MUTATING_EXACT["huy_viec_nen"] == "write_data"
