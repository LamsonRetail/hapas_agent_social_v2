"""26/10/2026 (chủ dự án): "những số đang viết tắt thì phải viết rõ số cụ thể ra, từ giờ không viết tắt
nữa" — mọi số trên dashboard hiện ĐỦ có chấm nghìn (8.812.345.678), không còn "tỷ" / "tr" / "N" / "K"
ở thẻ, tooltip, nhãn đỉnh, trục biểu đồ. Phần JS chạy bằng node nếu máy có."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from test_dashboard_app import QL, dang_nhap
from test_tiktok_ads import Q, _co_so, _tao_app

from dashboard import app as APP

GOC = Path(__file__).resolve().parent.parent
TINH = GOC / "dashboard" / "static"
CA = [(8812345678, "8.812.345.678"), (484123456, "484.123.456"), (24776, "24.776"),
      (1234, "1.234"), (999, "999"), (0, "0"), (-1500000, "-1.500.000"), (24776.4, "24.776"),
      (None, "—")]


def test_so_gon_python_tra_so_day_du():
    for vao, ra in CA:
        assert APP.so_gon(vao) == ra
    assert APP.so_gon("x") == "—"


def test_o_kpi_tien_giu_don_vi_va_so_day_du():
    d = {"kpi": {"chi": 8812345678, "hien_thi": 484123456}, "kpi_truoc": {}, "doi": {},
         "tien_te": ["VND"]}
    o = APP._o_kpi(d, "chi")
    assert o["so"] == o["day_du"] == "8.812.345.678 ₫"
    assert APP._o_kpi(d, "hien_thi")["so"] == "484.123.456"


def _ham_js(tep: str, *ten: str) -> str:
    """Cắt các hàm một dòng `function ten(...) {...}` + biến SO từ tệp JS tĩnh."""
    js = (TINH / tep).read_text(encoding="utf-8")
    kq = ['var SO = new Intl.NumberFormat("vi-VN");']
    for t in ten:
        m = re.search(rf"^ *function {t}\(.*$", js, re.MULTILINE)
        assert m, t
        kq.append(m.group(0).strip())
    return "\n".join(kq)


@pytest.mark.parametrize("tep,ten", [("chi_so.js", "soThe"), ("chi_so.js", "soTruc"),
                                      ("qc.js", "soGon")])
def test_ham_js_tra_so_day_du(tmp_path, tep, ten):
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node")
    ham = _ham_js(tep, *(["soThe", "soTruc"] if tep == "chi_so.js" else ["soGon"]))
    f = tmp_path / "so.js"
    f.write_text(ham + f"\nconsole.log(JSON.stringify({json.dumps([v for v, _ in CA])}.map({ten})));\n",
                 encoding="utf-8")
    ra = json.loads(subprocess.run([node, str(f)], capture_output=True, text=True,
                                   encoding="utf-8", check=True, timeout=30).stdout)
    assert ra == [r for _, r in CA]


def test_ma_nguon_khong_con_viet_tat_so():
    for tep in ("chi_so.js", "qc.js"):
        js = (TINH / tep).read_text(encoding="utf-8")
        assert not re.search(r'" (tỷ|tr|N|K)"', js), tep
        assert "1e9" not in js and "1e6" not in js, tep
    py = (GOC / "dashboard" / "app.py").read_text(encoding="utf-8")
    assert '" tỷ"' not in py and '" tr"' not in py


def test_trang_quang_cao_khong_con_chu_viet_tat():
    _app, c, _kho, _kq, _tt, _dv = _co_so(_tao_app())
    dang_nhap(c, QL)
    t = c.get(f"/quang-cao?{Q}").text
    assert not re.search(r"\d(,\d)? (tỷ|tr|N)\b", t)
