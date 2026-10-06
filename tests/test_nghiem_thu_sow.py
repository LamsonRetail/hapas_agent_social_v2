"""Canh bộ nghiệm thu SOW chạy bằng Promptfoo (evals/sow).

Bộ này chỉ chạy tay trên máy dev (gọi model thật), nên lỗi trong file ca hay hàm chấm chỉ lộ
ra lúc đã tốn lượt hỏi. Test ở đây bắt các lỗi đó trước, không gọi model:
- danh sách tool "ghi" của hàm chấm khớp lsr_policy (thêm tool ghi mới mà quên cập nhật thì
  bộ chấm sẽ không bắt được Mark tự chạy nó);
- file ca đọc được, đủ trường, tên kỹ năng có thật, không chứa thông tin cá nhân;
- các hàm chấm cho kết quả đúng trên metadata giả.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_GOC = Path(__file__).resolve().parents[1]
_EV = _GOC / "evals" / "sow"
sys.path.insert(0, str(_GOC))
sys.path.insert(0, str(_GOC / "scripts"))

import lsr_policy  # noqa: E402

_spec = importlib.util.spec_from_file_location("kiem_sow", _EV / "kiem.py")
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)

_TEN_KY_NANG = {
    p.read_text(encoding="utf-8").splitlines()[0].lstrip("#").strip()
    for p in (_GOC / "skills").glob("*.md")
}
_HAM_HANH_VI = {"nap_ky_nang", "khong_nap_ky_nang", "goi_tool", "chi_uoc_tinh"}
_CASES = sorted((_EV / "cases").glob("*.yaml"))


def _ca():
    for f in _CASES:
        for t in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
            yield f.name, t


def test_tool_ghi_khop_policy():
    assert K.TOOL_GHI == frozenset(lsr_policy._MUTATING_EXACT)


def test_config_chan_ghi_va_khong_chia_se():
    cfg = yaml.safe_load((_EV / "promptfooconfig.yaml").read_text(encoding="utf-8"))
    assert cfg["providers"][0]["id"] == "file://mark_provider.py"
    assert (_EV / "mark_provider.py").is_file()
    mac_dinh = {a.get("value") for a in cfg["defaultTest"]["assert"]}
    assert "file://kiem.py:khong_tu_ghi" in mac_dinh
    assert "file://kiem.py:khong_lo_thong_tin" in mac_dinh
    assert cfg["sharing"] is False
    assert cfg["tests"] == "file://cases/*.yaml"


def test_co_file_ca():
    assert _CASES, "evals/sow/cases trống"


@pytest.mark.parametrize("ten_file,t", list(_ca()),
                         ids=lambda x: x if isinstance(x, str) else x["vars"]["ma"])
def test_ca_hop_le(ten_file, t):
    assert t.get("description", "").startswith("SOW "), ten_file
    v = t["vars"]
    assert re.fullmatch(r"[a-z0-9]+", v["ma"]), v["ma"]
    assert str(v["hoi"]).strip()
    kieu = [a["type"] for a in t["assert"]]
    ham = [a["value"].split(":")[-1] for a in t["assert"] if a["type"] == "python"]
    assert _HAM_HANH_VI & set(ham), f"{v['ma']}: thiếu phép chấm hành vi"
    assert any(k != "python" for k in kieu) or "dem_it_nhat" in ham, f"{v['ma']}: thiếu phép chấm chữ"
    for a in t["assert"]:
        if a["type"] != "python":
            continue
        assert a["value"].startswith("file://kiem.py:")
        assert callable(getattr(K, a["value"].split(":")[-1], None)), a["value"]
        ten = (a.get("config") or {}).get("ten")
        if a["value"].endswith(("nap_ky_nang", "khong_nap_ky_nang")) and ten:
            assert ten in _TEN_KY_NANG, f"{v['ma']}: không có kỹ năng '{ten}'"
    hoi = " ".join([str(v["hoi"])] + [str(x) for x in v.get("luot_truoc") or []])
    assert K.khong_lo_thong_tin(hoi, {})["pass"], f"{v['ma']}: câu hỏi chứa thông tin cá nhân"


def test_ma_ca_khong_trung():
    ma = [t["vars"]["ma"] for _, t in _ca()]
    assert len(ma) == len(set(ma))


def _ctx(tool=(), args=(), ky_nang=(), **cfg):
    return {"providerResponse": {"metadata": {"tool": list(tool), "tool_args": list(args),
                                              "ky_nang": list(ky_nang)}},
            "config": cfg}


def test_khong_tu_ghi():
    assert K.khong_tu_ghi("", _ctx(["doc_bang"], [{}]))["pass"]
    assert K.khong_tu_ghi("", _ctx(["chi_so_bai"], [{"chi_uoc_tinh": True}]))["pass"]
    assert not K.khong_tu_ghi("", _ctx(["social_listen"], [{"q": "x"}]))["pass"]
    assert not K.khong_tu_ghi("", _ctx(["chi_so_bai"], ['{"links": "x"}']))["pass"]
    assert not K.khong_tu_ghi("", _ctx(["lark_cli"], [{"args": ["base", "+record-create", "--yes"]}]))["pass"]
    assert not K.khong_tu_ghi("", _ctx(["lark_cli"], [{"args": ["task", "+create"]}]))["pass"]
    assert K.khong_tu_ghi("", _ctx(["lark_cli"], [{"args": ["base", "+record-list"]}]))["pass"]
    # Lệnh ghi ngoài regex (lịch) vẫn bị bắt nhờ luật lark_cli của prod.
    assert not K.khong_tu_ghi("", _ctx(["lark_cli"], [{"args": ["calendar", "+event-create",
                                                                "--summary", "x"]}]))["pass"]


def test_provider_ep_policy_enforce(tmp_path, monkeypatch):
    import importlib.util as iu
    import os
    env = tmp_path / ".env"
    env.write_text("LSR_POLICY_MODE=observe\n", encoding="utf-8")
    monkeypatch.setenv("MARK_ENV_FILE", str(env))
    for k in ("LSR_POLICY_MODE", "AUDIT_TO_BASE", "LSR_JOB_POLL_ENABLED", "AGENT_BOSS_OPEN_ID"):
        monkeypatch.delenv(k, raising=False)
    spec = iu.spec_from_file_location("mark_provider_thu", _EV / "mark_provider.py")
    mp = iu.module_from_spec(spec)
    spec.loader.exec_module(mp)  # nạp file không dựng môi trường (dựng ở lần gọi đầu)
    mp._nap_env()
    assert os.environ["LSR_POLICY_MODE"] == "enforce"
    assert os.environ["AUDIT_TO_BASE"] == "0"


def test_nap_ky_nang_theo_ten():
    import dong_bo_tieu_su as DB
    ma = DB.ma_ky_nang("Họp dự án và bàn giao liên phòng ban")
    assert K.nap_ky_nang("", _ctx(ky_nang=[ma], ten="Họp dự án và bàn giao liên phòng ban"))["pass"]
    assert not K.nap_ky_nang("", _ctx(ky_nang=[], ten="Họp dự án và bàn giao liên phòng ban"))["pass"]
    assert K.khong_nap_ky_nang("", _ctx(ky_nang=["sk_khac"], ma=ma))["pass"]


def test_chi_uoc_tinh_va_goi_tool():
    assert K.chi_uoc_tinh("", _ctx(["chi_so_bai"], ['{"chi_uoc_tinh": true}'], ten="chi_so_bai"))["pass"]
    assert not K.chi_uoc_tinh("", _ctx(["chi_so_bai"], [{}], ten="chi_so_bai"))["pass"]
    assert K.goi_tool("", _ctx(["doc_bang"], [{}], ten="doc_bang"))["pass"]


def test_dem_va_lo_thong_tin():
    assert K.dem_it_nhat("a [CHƯA CÓ NGƯỜI] b [chưa có người]", _ctx(cum="[CHƯA CÓ NGƯỜI]", n=2))["pass"]
    assert not K.dem_it_nhat("a", _ctx(cum="x", n=1))["pass"]
    for lo in ("gọi 0912 345 678", "mail a.b@hapas.vn", "ou_5b597bb7e77ee9e1721ff5ea8fe5be93"):
        assert not K.khong_lo_thong_tin(lo, {})["pass"], lo
    assert K.khong_lo_thong_tin("ngân sách 200.000.000 đồng, ngày 22/10/2026", {})["pass"]
