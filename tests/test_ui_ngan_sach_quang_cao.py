"""23/10/2026 (chủ dự án): ghi chú vào dấu (i), bảng dài một kiểu thanh trang — trang Ngân sách và
Quảng cáo (khối Theo kênh đăng, dải đồng bộ, Xuất Lark Sheet)."""
from __future__ import annotations

import datetime
import re

from test_dashboard_app import QL, XEM, _kho_co_nguon_ton, dang_nhap, tao
from test_dieu_khien_dong_bo import _dai, _dong, _h
from test_kenh_dang import GiaKhoKenh, GiaTikTokKenh
from test_tiktok_ads import _ket_noi_san, _tao_app

Q = "tu=2026-10-12&den=2026-10-18&ben=tat_ca"


def _luot(n):
    return [{"id": i, "du_an": "hapas", "kieu": "theo_doi", "ma_viec": f"V{i}",
             "bat_dau": datetime.datetime(2026, 10, 14, 1, 30, tzinfo=datetime.timezone.utc),
             "ket_thuc": None, "so_nguon": 3, "so_nguon_loi": 0, "bai_moi": 1, "bai_cap_nhat": 0,
             "chi_phi_usd": 0.01, "trang_thai": "xong", "loi": None, "ghi_chu": None}
            for i in range(n, 0, -1)]


def test_ngan_sach_lich_su_dung_thanh_trang_chung_giu_du_an():
    _, c, kho = tao()
    kho.luot = _luot(45)
    dang_nhap(c, XEM)
    t = c.get("/ngan-sach?du_an=hapas&trang=2").text
    nav = t.split('aria-label="Trang của bảng lịch sử lượt quét"')[1].split("</nav>")[0]
    assert 'href="/ngan-sach?du_an=hapas#ns-ls" rel="prev"' in nav          # trang 1: không ?trang=1
    assert 'href="/ngan-sach?du_an=hapas&amp;trang=3#ns-ls" rel="next"' in nav
    assert 'aria-current="page"><span class="dai-qc__an">Trang </span>2<' in nav
    assert "Trang 2/3 · 45 lượt" in nav and 'id="ns-ls"' in t
    assert "Cũ hơn" not in t and "Mới hơn" not in t
    # một trang: không có thanh trang
    kho.luot = _luot(5)
    assert "Trang của bảng lịch sử lượt quét" not in c.get("/ngan-sach?du_an=hapas").text


def test_ngan_sach_bang_dai_phan_trang_va_ghi_chu_vao_dau_i():
    _, c, kho = tao(_kho_co_nguon_ton())
    for i in range(2, 26):
        kho.du_an[f"da{i}"] = {**kho.du_an["hapas"], "ma": f"da{i}", "ten": f"Dự án {i}"}
    dang_nhap(c, QL)
    t = c.get("/ngan-sach?du_an=hapas").text                  # hapas có nguồn → có bảng dự báo
    for bang in ("ns-cac-du-an", "ns-bang", "ns-bang-pt"):
        assert re.search(rf'<table class="{bang}" data-phan-trang="20" data-phan-trang-nhan="[^"]+"',
                         t), bang
    # dự án đang xem là dòng đầu (trang 1 của thanh trang luôn có nó)
    than = c.get("/ngan-sach?du_an=da7").text.split('<table class="ns-cac-du-an"')[1].split("</tbody>")[0]
    assert than.index('aria-current="true"') < than.index("<td>") + 5
    assert than.index("du_an=da7") < than.index("du_an=hapas")
    # không còn đoạn ghi chú dưới tiêu đề; chú giải "viền đứt" + mô tả Nâng cao nằm trong (i)
    assert 'class="ghi-chu' not in t and "ns-vd" not in t
    assert re.search(r'data-goi-y="Ô trống, viền đứt = theo mặc định dự án', t)
    assert "ns-nc__mo-ta\">Thêm nguồn dữ liệu phụ" not in t
    assert re.search(r'data-goi-y="Thêm nguồn dữ liệu phụ để bắt bài nhỏ', t)
    assert re.search(r'data-goi-y="[^"]*Dùng cho cụm chung chung kéo về bài không liên quan', t)


def _trang_qc(kenh=45, **qp):
    app, c, _kho, kho_qc, tt, dv = _tao_app(kho_qc=GiaKhoKenh(), tt=GiaTikTokKenh(so_ad=25))
    _ket_noi_san(dv, tt)
    dv.dong_bo(tu=datetime.date(2026, 10, 12), den=datetime.date(2026, 10, 18))
    app.state.nho_ben_qc = (float("-inf"), set())

    def _kenh(ids, tu, den, *, sap="chi", n=20):
        rows = [{"nen_tang": "tiktok", "kenh_id": f"k{i}", "loai": "AUTH_CODE", "tk_ids": list(ids),
                 "so_ad": 2, "ten": f"Kênh {i}", "username": f"kenh{i}", "chi": 1000 - i,
                 "hien_thi": 900 - i, "click": 1, "view_video": 1, "thich": 0, "binh_luan": 0,
                 "chia_se": 0, "follow": 0} for i in range(kenh)]
        return {"rows": rows[:n], "tong": kenh, "biet": {"chi": 9, "hien_thi": 9},
                "chua_ro": {"chi": 1, "hien_thi": 1, "so_ad": 3}}
    kho_qc.qc_kenh_dang = _kenh
    dang_nhap(c, QL)
    return c.get("/quang-cao?" + Q + "".join(f"&{k}={v}" for k, v in qp.items())).text


def test_kenh_dang_phan_trang_chung_chua_xac_dinh_o_tfoot_dong_phu_mot_dong():
    t = _trang_qc()
    k = t.split('id="kenh"')[1].split("</section>")[0]
    assert '<table class="qc-bang qc-kenh__bang" data-phan-trang="20" data-phan-trang-nhan="kênh đăng">' in k
    tfoot = k.split("<tfoot>")[1].split("</tfoot>")[0]
    assert "Chưa xác định" in tfoot and "Chưa xác định" not in k.split("<tbody>")[1].split("</tbody>")[0]
    # chú thích cuối bảng → (i) + nút "Tải đủ" ở đầu mục
    assert "Đang hiện" not in k and "xem thêm" not in k
    assert re.search(r'data-goi-y="[^"]*đang tải 20 / 45 kênh đầu', k)
    assert re.search(r'<a class="qc-kenh__them" href="[^"]*kenh_so=100[^"]*#kenh">Tải đủ 45 kênh</a>', k)
    # dòng phụ: một dòng cắt "…", đủ tài khoản ở title
    phu = re.search(r'<span class="qc-bang__phu" data-nen-tang="tiktok" title="([^"]+)">', k)
    assert phu and "@kenh0" in phu.group(1) and "2 quảng cáo" in phu.group(1)
    assert '<span class="qc-bang__phu-chu">' in k
    # đã tải đủ: không còn nút
    k = _trang_qc(kenh_so=100).split('id="kenh"')[1].split("</section>")[0]
    assert "qc-kenh__them" not in k and k.count('<tr>') == 1 + 45                  # thead + 45 kênh


def test_sheet_va_dai_dong_bo_ghi_chu_vao_dau_i():
    t = _trang_qc(kenh=3)
    s = t.split('id="sheet"')[1].split("</section>")[0]
    assert re.search(r'data-goi-y="[^"]*thường xong sau 1–2 phút', s)
    assert '<p class="mo nho qc-sheet__goi-y" id="qc-sheet-goi-y" hidden></p>' in s
    assert '<li class="qc-sheet__trong">Chưa xuất Sheet nào.</li>' in s
    h = _h()
    csrf = dang_nhap(h.c, QL)
    h.c.post("/quang-cao/dong-bo", data={"csrf": csrf, "ncc": "meta_ads", "kieu": "nhanh",
                                         "ve": "/quang-cao"})
    d = _dong(_dai(h.c.get("/quang-cao").text), "meta")
    assert "dai-qc__ly" not in d
    assert '<span class="dai-qc__an" id="dai-qc-ly-meta">Chưa bấm được: đang có yêu cầu lúc' in d
    assert re.search(r'class="goi-y"[^>]*data-goi-y="Chưa bấm được: đang có yêu cầu lúc', d)
    assert 'aria-describedby="dai-qc-ly-meta"' in d
