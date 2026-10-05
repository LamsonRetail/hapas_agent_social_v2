"""Đồng hồ lượt: nhắc gói lại ở mốc nhắc, chặn tool mới ở mốc chặn.

02/10/2026 một lượt gọi 24 tool nối nhau mất 417 giây — sát trần 480 giây của vòng job.
"""
from __future__ import annotations

import contextvars
import json
import pathlib
import sys
import threading
import types

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

import dong_ho_luot as D  # noqa: E402


@pytest.fixture
def dong_ho(monkeypatch):
    """Đồng hồ giả. `dat(g)`: mở lượt trong `dat.ctx` rồi cho đồng hồ chạy g giây."""
    for ten in ("LSR_LUOT_NHAC_GIAY", "LSR_LUOT_CHAN_GIAY", "LSR_HAN_TRA_LOI_SECONDS"):
        monkeypatch.delenv(ten, raising=False)
    gio = {"t": 1000.0}
    monkeypatch.setattr(D, "_dong_ho", lambda: gio["t"])
    ctx = contextvars.copy_context()

    def dat(g):
        ctx.run(D.bat_dau)
        gio["t"] += g
    dat.ctx = ctx
    dat.gio = gio
    return dat


def test_mac_dinh_300_400_480(monkeypatch):
    for ten in ("LSR_LUOT_NHAC_GIAY", "LSR_LUOT_CHAN_GIAY", "LSR_HAN_TRA_LOI_SECONDS"):
        monkeypatch.delenv(ten, raising=False)
    assert D.nguong() == (300.0, 400.0, 480.0)


def test_moc_chan_luon_chua_cho_model_viet(monkeypatch):
    monkeypatch.delenv("LSR_HAN_TRA_LOI_SECONDS", raising=False)
    monkeypatch.setenv("LSR_LUOT_CHAN_GIAY", "1000")
    monkeypatch.setenv("LSR_LUOT_NHAC_GIAY", "2000")
    nhac, chan, tran = D.nguong()
    assert chan == tran - 60 and nhac == chan


def test_env_hong_ve_mac_dinh(monkeypatch):
    monkeypatch.delenv("LSR_HAN_TRA_LOI_SECONDS", raising=False)
    monkeypatch.setenv("LSR_LUOT_CHAN_GIAY", "abc")
    monkeypatch.setenv("LSR_LUOT_NHAC_GIAY", "-5")
    assert D.nguong() == (300.0, 400.0, 480.0)


def test_ngoai_luot_tra_loi_khong_dung_gi():
    ctx = contextvars.Context()          # chưa bat_dau: việc nền, nhắc việc, bộ thử
    assert ctx.run(D.xet) == ("", 0.0)


def test_cac_moc(dong_ho):
    dong_ho(10)
    assert dong_ho.ctx.run(D.xet)[0] == ""
    dong_ho.gio["t"] += 300
    assert dong_ho.ctx.run(D.xet)[0] == "nhac"
    dong_ho.gio["t"] += 100
    assert dong_ho.ctx.run(D.xet)[0] == "chan"


def test_nhac_giu_cau_truc_json():
    d = json.loads(D.gan_nhac(json.dumps({"success": True, "rows": 3}), 320))
    assert d["success"] is True and d["rows"] == 3
    assert "tổng kết" in d["_dong_ho_luot"]


def test_nhac_chuoi_thuong_va_kieu_khac():
    assert D.gan_nhac("ok", 320).startswith("ok\n\n[đồng hồ lượt]")
    assert D.gan_nhac("[1, 2]", 320).startswith("[1, 2]\n\n")
    assert D.gan_nhac(None, 320) is None


# ───────────────────────── qua cổng registry.dispatch ─────────────────────────
def _cai(monkeypatch, che_do="enforce"):
    """Cài guard lên một registry GIẢ (không đụng registry thật của Hermes)."""
    import lsr_policy
    goi, ghi = [], []

    class Reg:
        def dispatch(self, name, args, **kw):
            goi.append(name)
            return json.dumps({"success": True})
    reg = Reg()
    mod = types.ModuleType("tools.registry")
    mod.registry = reg
    monkeypatch.setitem(sys.modules, "tools.registry", mod)
    monkeypatch.setenv("LSR_POLICY_MODE", che_do)
    monkeypatch.setattr(lsr_policy, "decide",
                        lambda n, a=None: lsr_policy.PolicyDecision(True, "ok"))
    assert lsr_policy.install_registry_guard(
        lambda *a, **k: ghi.append((a[0], k.get("loi"))))
    return reg, goi, ghi


def test_cong_ngoai_luot_chay_nguyen(monkeypatch):
    reg, goi, _ = _cai(monkeypatch)
    kq = contextvars.Context().run(reg.dispatch, "soi_tai_khoan", {})
    assert json.loads(kq) == {"success": True} and goi == ["soi_tai_khoan"]


def test_cong_moc_nhac_van_chay_va_kem_loi_nhac(monkeypatch, dong_ho):
    reg, goi, _ = _cai(monkeypatch)
    dong_ho(320)
    kq = dong_ho.ctx.run(reg.dispatch, "web_scrape", {})
    assert goi == ["web_scrape"]
    assert "_dong_ho_luot" in json.loads(kq)


def test_cong_moc_chan_khong_chay_tool_va_ghi_audit(monkeypatch, dong_ho):
    reg, goi, ghi = _cai(monkeypatch)
    dong_ho(410)
    kq = json.loads(dong_ho.ctx.run(reg.dispatch, "fb_ads_library", {}))
    assert goi == [], "quá mốc chặn thì tool KHÔNG được chạy"
    assert kq["error"] == "het_gio_luot" and "câu trả lời" in kq["reason"]
    assert ghi and ghi[0][0] == "fb_ads_library" and "hết giờ" in ghi[0][1]


def test_cong_ap_ca_khi_policy_tat(monkeypatch, dong_ho):
    """Chế độ policy `off` vẫn phải có trần thời gian."""
    reg, goi, _ = _cai(monkeypatch, "off")
    dong_ho(410)
    assert json.loads(dong_ho.ctx.run(reg.dispatch, "x", {}))["error"] == "het_gio_luot"
    assert goi == []


def test_dong_ho_theo_sang_luong_tool_song_song(dong_ho):
    """Hermes chạy tool song song bằng cách chép context sang luồng con."""
    dong_ho(410)
    ra = []
    con = dong_ho.ctx.copy()
    t = threading.Thread(target=lambda: ra.append(con.run(D.xet)[0]))
    t.start()
    t.join()
    assert ra == ["chan"]
