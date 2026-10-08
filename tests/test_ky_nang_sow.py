"""Canh các kỹ năng viết theo SOW team Marketing (đợt kỹ năng nghiệp vụ).

Mỗi kỹ năng ở đây là văn bản đi thẳng vào prompt của Mark khi model gọi `dung_ky_nang`.
Lỗi trong văn bản là lỗi hành vi của bot: thiếu câu cấm thì bot có thể tự gửi tin, tự
ghi Base hay tự quét tốn tiền; nhắc một công cụ không có thật thì bot gọi hụt; lọt số
điện thoại hay email từ tài liệu team là lộ dữ liệu cá nhân vào prompt.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_GOC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_GOC / "scripts"))

import dong_bo_tieu_su as D  # noqa: E402

#: file → tên kỹ năng (dòng "# " đầu file). Mười kỹ năng mới/sửa trong đợt SOW.
KY_NANG_SOW = {
    "nghien-cuu-khach-hang.md": "Nghiên cứu khách hàng và hành vi mua",
    "ke-hoach-chien-dich-tong.md": "Lập và rà kế hoạch tổng chiến dịch",
    "hop-va-ban-giao.md": "Họp dự án và bàn giao liên phòng ban",
    "theo-doi-ngan-sach.md": "Theo dõi ngân sách chiến dịch",
    "lich-noi-dung.md": "Lập và rà lịch nội dung",
    "viet-content.md": "Viết content bài đăng HAPAS",
    "cham-diem-xu-huong-tiktok.md": "Chọn xu hướng và lên chuỗi TikTok",
    "brief-order-media.md": "Soạn brief order media và design",
    "cap-nhat-website.md": "Chuẩn bị nội dung cập nhật website",
    "ad-performance-audit.md": "Audit hiệu quả quảng cáo",
}

#: Kỹ năng có sẵn chỉ sửa câu "khi nào dùng" để tách ranh giới với kỹ năng mới.
KY_NANG_SUA_MUC_LUC = {
    "campaign-plan.md": "Lập kế hoạch chiến dịch quảng cáo",
    "kol-content-review.md": "Duyệt nội dung KOL/KOC và quảng cáo",
    "evidence-reporting.md": "Báo cáo dựa trên evidence",
    "gioi-thieu-cong-cu.md": "Giới thiệu công cụ của Mark",
}

_TAT_CA = {**KY_NANG_SOW, **KY_NANG_SUA_MUC_LUC}


def _than(f: str) -> str:
    return (D.SKILLS / f).read_text(encoding="utf-8")


def _muc_luc() -> dict:
    return json.loads(D.KHI_NAO_DUNG.read_text(encoding="utf-8"))


# ───────────────────────────── công cụ có thật ─────────────────────────────
def _tool_da_dang_ky() -> set[str]:
    """Tên tool repo này tự đăng ký: `name="..."` trong registry.register và
    `"name": "..."` trong SCHEMA, hằng `TEN_TOOL = "..."`; quét mọi module gốc
    (*_tool.py, brain.py, scheduler.py, memory_store.py, viec_nen.py…)."""
    ten: set[str] = set()
    for f in _GOC.glob("*.py"):
        s = f.read_text(encoding="utf-8", errors="replace")
        ten |= set(re.findall(r'\bname="([a-z][a-z0-9_]+)"', s))
        ten |= set(re.findall(r'"name":\s*"([a-z][a-z0-9_]+)"', s))
        ten |= set(re.findall(r'TEN_TOOL\s*=\s*"([a-z][a-z0-9_]+)"', s))
    return ten


#: Tool của khung Hermes, không đăng ký trong repo này — nguồn: brain.py nhắc đúng tên
#: (dòng "DUYỆT WEB / TRANG CÔNG KHAI" và bảng mô tả `vision_analyze`) và
#: brief/nang_luc_mark.json. Test bên dưới kiểm brain.py vẫn còn nhắc từng tên.
_TOOL_KHUNG = {"vision_analyze", "browser_navigate", "browser_snapshot",
               "browser_get_images"}

#: Chữ snake_case trong kỹ năng mà KHÔNG phải tên tool: tham số của tool có thật.
#: `che_do`, `chi_uoc_tinh` là tham số của social_listen (apify_tool.py). Từ 07/10/2026 kỹ
#: năng dạy gọi `dem_bang` (bỏ luật "bảng >20 dòng không tự đếm") nên nhắc tham số và
#: trường kết quả của nó — mỗi tên phải còn trong dem_bang_tool.py. Cũng từ 07/10/2026 kỹ
#: năng dạy KHÔNG tự tính tay: dán vào chat → `dem_bang` với `du_lieu`; phép tính → tool
#: `tinh` (tham số, trường kết quả và tên hàm trong biểu thức — phải còn trong tinh_tool.py).
_THAM_SO = {"che_do": "apify_tool.py", "chi_uoc_tinh": "apify_tool.py",
            "cot_han": "tien_do.py", "cot_pic": "tien_do.py", "cua_toi": "tien_do.py",
            "cau_so": "dem_bang_tool.py", "nhom_theo": "dem_bang_tool.py",
            "dong_tieu_de": "dem_bang_tool.py", "dong_tieu_de_da_dung": "dem_bang_tool.py",
            "tach_dau_phay": "dem_bang_tool.py", "bi_cat": "dem_bang_tool.py",
            "du_lieu": "dem_bang_tool.py",
            "phep_tinh": "tinh_tool.py", "cau_tinh": "tinh_tool.py", "ty_le": "tinh_tool.py",
            "chenh_lech": "tinh_tool.py", "trung_vi": "tinh_tool.py",
            "trung_binh": "tinh_tool.py", "lam_tron": "tinh_tool.py"}

_SNAKE = re.compile(r"(?<![\w/.:=-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![\w])")
_URL = re.compile(r"https?://\S+|sheet:\S+")


def test_danh_sach_tool_lay_duoc_va_tool_khung_con_trong_brain():
    co = _tool_da_dang_ky()
    for t in ("doc_bang", "dem_bang", "tinh", "social_listen", "dung_ky_nang", "tra_kho", "lark_cli",
              "tra_chi_phi_quet", "binh_luan_kenh_nha"):
        assert t in co, f"không quét ra tool {t} — regex lấy tên tool đã lệch với code"
    brain = (_GOC / "brain.py").read_text(encoding="utf-8")
    for t in _TOOL_KHUNG:
        assert t in brain, f"brain.py không còn nhắc {t} — kiểm lại tool khung còn không"
    for ts, f in _THAM_SO.items():
        assert f'"{ts}"' in (_GOC / f).read_text(encoding="utf-8"), f"{ts} không còn trong {f}"


@pytest.mark.parametrize("f", sorted(KY_NANG_SOW))
def test_chi_nhac_tool_co_that(f):
    """Mọi chữ dạng snake_case trong kỹ năng phải là tool có thật hoặc tham số đã biết."""
    co = _tool_da_dang_ky() | _TOOL_KHUNG | set(_THAM_SO)
    than = _URL.sub(" ", _than(f))
    la = sorted({m for m in _SNAKE.findall(than)} - co)
    assert not la, f"{f} nhắc công cụ/tên không có thật: {la}"


# ───────────────────────────── tiêu đề + mục lục ─────────────────────────────
@pytest.mark.parametrize("f,ten", sorted(_TAT_CA.items()))
def test_co_tieu_de_dung_ten(f, ten):
    dong_dau = _than(f).lstrip(chr(0xFEFF)).splitlines()[0]
    assert dong_dau == f"# {ten}", f"{f}: dòng đầu là {dong_dau!r}"


@pytest.mark.parametrize("f,ten", sorted(_TAT_CA.items()))
def test_co_trong_muc_luc_va_khi_nao_dung_hop_le(f, ten):
    kn = _muc_luc()
    sid = D.ma_ky_nang(ten)
    assert sid in kn, f"{f}: mã {sid} chưa có trong khi-nao-dung.json"
    assert kn[sid]["ten"] == ten
    khi = kn[sid]["khi_nao_dung"].strip()
    assert khi and len(khi) <= 200, f"{ten}: 'khi nào dùng' dài {len(khi)} ký tự"
    assert khi.split()[0] in ("Khi", "TRƯỚC"), f"{ten}: không bắt đầu bằng điều kiện"
    assert khi not in _than(f), f"{ten}: 'khi nào dùng' chép từ thân"


def test_ma_ky_nang_sow_co_dinh():
    """Mã sinh theo tên. Ai đổi tiêu đề file là đổi mã — platform coi là kỹ năng khác."""
    assert D.ma_ky_nang("Audit hiệu quả quảng cáo") == "sk_e9b50ab8b9"
    assert D.ma_ky_nang("Lập kế hoạch chiến dịch quảng cáo") == "sk_f2de0ac573"
    assert D.ma_ky_nang("Nghiên cứu khách hàng và hành vi mua") == "sk_a3caf424ab"


# ───────────────────────────── câu cấm ─────────────────────────────
def _gon(s: str) -> str:
    """Gộp dòng (câu cấm hay xuống dòng giữa chừng), hạ chữ thường. "..." đổi thành "…"
    để dấu chấm liệt kê không bị coi là hết câu."""
    return re.sub(r"\s+", " ", s.replace("...", "…")).lower()


_CAM = {
    "tự gửi tin/nhắc vào nhóm": r"(không|cấm)[^.]{0,60}?gửi tin",
    "ghi/sửa Base/Sheet của team": r"không[^.]{0,40}?(ghi|sửa)[^.]{0,40}?(base|sheet)",
    "tạo task": r"không[^.]{0,80}?tạo task",
    "chạy công cụ tốn tiền khi chưa hỏi": (
        r"(không|cấm)[^.]{0,150}?tốn tiền[^.]{0,150}?(chưa hỏi|chưa được|được (người dùng )?đồng ý)"),
}


@pytest.mark.parametrize("f", sorted(KY_NANG_SOW))
def test_than_co_cau_cam(f):
    than = _gon(_than(f))
    thieu = [ten for ten, mau in _CAM.items() if not re.search(mau, than)]
    assert not thieu, f"{f} thiếu câu cấm: {thieu}"


# ───────────────────────────── định dạng + dữ liệu cá nhân ─────────────────────────────
@pytest.mark.parametrize("f", sorted(KY_NANG_SOW))
def test_khong_co_bang_markdown(f):
    """Persona cấm markdown trong chat; kỹ năng có bảng thì model bắt chước in bảng."""
    dong = [i + 1 for i, l in enumerate(_than(f).splitlines()) if l.lstrip().startswith("|")]
    assert not dong, f"{f}: dòng bảng markdown ở {dong}"


@pytest.mark.parametrize("f", sorted(KY_NANG_SOW))
def test_dan_tra_loi_van_ban_thuan(f):
    than = _gon(_than(f))
    assert "markdown" in than or "văn bản thuần" in than, (
        f"{f}: không dặn trả lời không dùng markdown")


_SDT = re.compile(r"(?<![\d.,])(?:\+?84|0)[ .-]?[35789](?:[ .-]?\d){8}(?![\d.,])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@pytest.mark.parametrize("f", sorted(_TAT_CA))
def test_khong_lot_sdt_email(f):
    than = _than(f)
    assert not _SDT.findall(than), f"{f}: có chuỗi giống số điện thoại {_SDT.findall(than)}"
    assert not _EMAIL.findall(than), f"{f}: có chuỗi giống email {_EMAIL.findall(than)}"


def test_bo_loc_sdt_email_bat_dung():
    """Chặn regex câm: phải bắt được mẫu thật, và không bắt số tiền thô."""
    assert _SDT.search("gọi 0912 345 678 nhé") and _SDT.search("+84912345678")
    assert not _SDT.search("tổng 1070000000 đồng") and not _SDT.search("CPM 0,0512")
    assert _EMAIL.search("gửi a.b@hapas.vn")


_TRO_TOI = re.compile(r'(?:→|dùng kỹ năng|Dùng kỹ năng|nạp)\s*"([^"]{6,80})"')
#: Cách viết không ngoặc kép: "dùng kỹ năng Lập và rà lịch nội dung" (tên có thể xuống dòng
#: thụt lề). Không bắt sau "→" trơn vì mũi tên còn dùng cho rẽ nhánh/quy trình.
_TRO_TOI_TRON = re.compile(r'(?:dùng kỹ năng|Dùng kỹ năng)\s+(?!")((?:[^.;,()"\n:]|\n[ \t]{2,}(?![-\d]))+)')


@pytest.mark.parametrize("f", sorted(_TAT_CA))
def test_ten_ky_nang_duoc_tro_toi_co_that(f):
    """Kỹ năng trỏ sang kỹ năng khác bằng TÊN: tên sai thì model nạp hụt hoặc nhắc một
    khả năng không có thật. Tên sau "→"/"dùng kỹ năng" (có hay không ngoặc kép) phải là
    tiêu đề thật."""
    ten_that = {p.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
                for p in (_GOC / "skills").glob("*.md")}
    than = (_GOC / "skills" / f).read_text(encoding="utf-8")
    sai = {re.sub(r"\s+", " ", m.group(1)).strip() for m in _TRO_TOI.finditer(than)} - ten_that
    for m in _TRO_TOI_TRON.finditer(than):
        x = re.sub(r"\s+", " ", m.group(1)).strip()
        if x[:1].isupper() and not any(x.startswith(t) for t in ten_that):
            sai.add(x)
    assert not sai, f"{f} trỏ tới kỹ năng không tồn tại: {sorted(sai)}"


def test_bo_bat_ten_ky_nang_bat_dung():
    """Chặn regex câm cho cả hai cách viết."""
    sai_ngoac = 'hỏi trễ → "Theo dõi tiến\n  độ dự án"'
    assert _TRO_TOI.search(sai_ngoac)
    m = _TRO_TOI_TRON.search("(dùng kỹ năng Duyệt nội dung\n  KOL không có)")
    assert m and re.sub(r"\s+", " ", m.group(1)).strip() == "Duyệt nội dung KOL không có"
