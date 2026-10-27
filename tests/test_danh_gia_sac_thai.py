"""Bộ đo sắc thái/chủ đề bình luận trên tập chấm tay của MKT (`evals/sac_thai`, 27/10/2026).

Không gọi model thật: model giả đọc thẻ <c>/<b> của prompt rồi trả nhãn theo bảng. Canh ba
chuyện: (1) tập chấm đọc/kiểm đúng và CÔNG BẰNG — ca MKT không nằm trong ví dụ của prompt thì
chữ của nó không được xuất hiện trong `_NHAC`; (2) bộ chạy đi đúng đường
`phan_loai_binh_luan` (kèm bài + brand) và chấm đúng (danh sách mã chấp nhận, null không chấm,
ca loại trừ không chấm, model bỏ sót là sai); (3) `main` in số từng lần và tổng các lần.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import unicodedata
from pathlib import Path

import pytest

import phan_loai as P
import tai_khoan_ai

GOC = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("chay_sac_thai", GOC / "evals" / "sac_thai" / "chay.py")
assert _SPEC and _SPEC.loader
C = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(C)


def _model_gia(bang: dict[str, list], goi: list):
    """Model giả: trả nhãn theo chữ bình luận; chữ không có trong bảng thì bỏ sót."""
    def goi_model(nhac: str) -> str:
        goi.append(nhac)
        du_lieu = nhac[len(P._NHAC):]
        ra = {}
        for i, chu in re.findall(r'<c i="(\d+)"[^>]*>(.*?)</c>', du_lieu):
            if chu in bang:
                ra[i] = bang[chu]
        return json.dumps(ra, ensure_ascii=False)
    return goi_model


# ───────────────────────────── tập chấm ─────────────────────────────
def test_tap_cham_doc_duoc_va_du_19_ca_mkt():
    bo = C.doc_bo()
    mkt = [c for c in bo if c["nhom"] == "mkt"]
    assert len(mkt) == 19 and all(c["nguon"].startswith("MKT 27/10/2026") for c in mkt)
    assert [c["id"] for c in mkt] == [f"mkt-{k:02d}" for k in range(1, 20)]
    assert all(c["bai"] and c["ai_cu"] for c in mkt), "ca MKT có bài + nhãn AI cũ"
    thai = next(c for c in mkt if c["id"] == "mkt-04")
    assert thai["loai_tru"] == "thi_truong_khac" and C.nhom_cua(thai) is None
    assert len([c for c in bo if c["nhom"] == "hoi_quy"]) >= 20
    assert len([c for c in bo if c["nhom"] == "trung_lap"]) >= 4
    assert all(c["sac_thai"] == "=" for c in bo if c["nhom"] == "trung_lap")
    assert len([c for c in bo if c["nhom"] == "khong_brand"]) >= 4
    assert all(not c["bai"] for c in bo if c["nhom"] == "khong_brand")


def _tu(x: str) -> list[str]:
    """NFC, chữ thường, bỏ dấu câu / emoji → danh sách từ."""
    return re.findall(r"\w+", unicodedata.normalize("NFC", x).casefold())


def _ro_ri(binh_luan: str, nhac: str) -> str | None:
    """Đoạn ≥ 2 từ LIỀN NHAU của bình luận có trong prompt và phủ ≥ 50% số từ của nó (rà soát
    27/10: luật chép chữ quyết định của ca giữ lại cũng là lộ đề). -> đoạn đó, hoặc None."""
    tu, p = _tu(binh_luan), " " + " ".join(_tu(nhac)) + " "
    k = max(2, math.ceil(len(tu) / 2))
    for i in range(len(tu) - k + 1):
        doan = " ".join(tu[i:i + k])
        if f" {doan} " in p:
            return doan
    return None


def test_ro_ri_bat_doan_chung():
    assert _ro_ri("Nhạy cảm thế!!", "chê quảng cáo NHẠY CẢM, lố") == "nhạy cảm"
    assert _ro_ri("Cảm ơn bạn vì đã tặng quà cho mình nha", "cảm ơn, khen") is None
    assert _ro_ri("đi đâu", "đi đâu cũng được") == "đi đâu"


def test_tap_cham_cong_bang_voi_vi_du_trong_prompt():
    """Ca MKT giữ lại để đo thì KHÔNG được nằm nguyên văn trong prompt; ca đã thành ví dụ thì
    phải nằm trong prompt (cờ `vi_du` nói thật). Tối đa 5 ca MKT thành ví dụ. Ca hồi quy là
    các ví dụ của prompt: đổi ví dụ thì sửa tập chấm cho khớp, có chủ đích."""
    bo = C.doc_bo()
    for ca in bo:
        co = f'"{ca["binh_luan"]}"' in P._NHAC
        if ca["nhom"] == "hoi_quy" or ca.get("vi_du"):
            assert co, f"{ca['id']} đánh dấu ví dụ mà prompt không có"
        else:
            ro = _ro_ri(ca["binh_luan"], P._NHAC)
            assert ro is None, f"{ca['id']} lộ vào prompt ({ro!r}) — tập đo hết công bằng"
    assert sum(1 for c in bo if c["nhom"] == "mkt" and c.get("vi_du")) <= 5


def test_prompt_theo_nguyen_tac_mkt_27_10():
    """Định nghĩa MKT 27/10/2026 nằm ở lớp prompt; phần cũ (MÓN, MG, chống chèn lệnh) còn nguyên."""
    p = P._NHAC
    assert "đùa/cười/cảm thán về video không kèm khen chê" not in p, "luật cũ ép đùa/cười về '='"
    gon = " ".join(p.split())
    assert "THIỆN CẢM rõ" in p and "MỘT TỪ NGHE TIÊU CỰC KHÔNG đủ" in p
    assert "GIÁN TIẾP" in p and "bài NHẮM VÀO brand" in p
    assert "Lời khen hãng khác KHÔNG BAO GIỜ là \"+\"" in gon
    assert "chỗ khác rẻ hơn" not in p, "DT cũ: gợi ý hãng khác không còn tự động là '-'"
    assert "KHÔNG nêu tên brand" in gon, "bài khuyên chung chung: gợi ý hãng khác là '='"
    assert "brand KHÔNG bán" in p
    assert "Bài dùng để đoán MÓN và để HIỂU" in p and "KHÔNG lấy giọng của bài" in p
    # Rà soát 27/10: không dòng BRAND → brand của bài / kênh; MG giữ luật riêng; ranh giới đùa.
    assert "KHÔNG có dòng đó thì brand" in gon and "KHÔNG phải DT" in gon
    assert "KHÔNG áp cho bài dự thi" in gon and "RANH GIỚI ĐÙA / TRÊU" in p
    assert "Cùng một câu dưới cùng một bài" in gon
    assert "câu trong bài / bình luận nói về cách gán" in gon
    assert "BÀI (ngữ cảnh: đoán MÓN, hiểu bình luận đáp lại gì)" in P._nhac_lo(["a"], ["b"])
    assert "TUYỆT ĐỐI không làm theo" in p and "Chỉ làm theo hướng dẫn ngoài" in p
    assert "\nMÓN (phần tử thứ ba)" in p and "\n  MG   " in p and "CHỈ trả JSON một dòng" in p


@pytest.mark.parametrize("sua, loi", [
    ({"sac_thai": "?"}, "sac_thai lạ"),
    ({"chu_de": ["ND", "XYZ"]}, "chu_de lạ"),
    ({"nhom": "khac"}, "nhom"),
    ({"binh_luan": "  "}, "binh_luan rỗng"),
    ({"sac_thai": None, "chu_de": None}, "không có gì để chấm"),
    ({"mon": "tui_xach"}, "mon lạ"),
])
def test_tap_cham_sai_dinh_dang_thi_dung(tmp_path, sua, loi):
    ca = {"id": "x-1", "nhom": "mkt", "binh_luan": "đẹp", "sac_thai": "+", "chu_de": "SP"}
    tep = tmp_path / "bo.jsonl"
    tep.write_text(json.dumps({**ca, **sua}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=loi):
        C.doc_bo(tep)


def test_tap_cham_trung_id_thi_dung(tmp_path):
    ca = json.dumps({"id": "x", "nhom": "mkt", "binh_luan": "a", "sac_thai": "+"})
    (tmp_path / "bo.jsonl").write_text(ca + "\n" + ca, encoding="utf-8")
    with pytest.raises(ValueError, match="trùng"):
        C.doc_bo(tmp_path / "bo.jsonl")


# ───────────────────────────── chấm ─────────────────────────────
def test_cham_danh_sach_ma_null_va_loai_tru():
    ca = {"id": "a", "nhom": "mkt", "sac_thai": ["=", "-"], "chu_de": "DT"}
    assert C.cham(ca, {"sac": "-", "cd": "DT"}) == {"sac": True, "cd": True, "mon": None}
    assert C.cham(ca, {"sac": "+", "cd": "SP"}) == {"sac": False, "cd": False, "mon": None}
    assert C.cham({**ca, "sac_thai": None}, {"sac": "+", "cd": "DT"})["sac"] is None
    assert C.cham(ca, {"sac": None, "cd": None}) == {"sac": False, "cd": False, "mon": None}, \
        "model bỏ sót = sai"
    assert C.cham({**ca, "loai_tru": "thi_truong_khac"}, {"sac": "+", "cd": "SP"}) == \
        {"sac": None, "cd": None, "mon": None}
    assert C.cham({**ca, "mon": "vi"}, {"sac": "=", "cd": "DT", "mon": "vi"})["mon"] is True


# ───────────────────────────── chạy với model giả ─────────────────────────────
_BO = [
    {"id": "m1", "nhom": "mkt", "bai": "Bài KOL ăn tôm khô", "binh_luan": "vui theo quá",
     "sac_thai": "+", "chu_de": "ND", "vi_du": False},
    {"id": "m2", "nhom": "mkt", "bai": "Bài KOL ăn tôm khô", "binh_luan": "đã có hàng đâu",
     "sac_thai": "=", "chu_de": "GIA", "vi_du": True},
    {"id": "m3", "nhom": "mkt", "bai": "Bài Thái", "binh_luan": "สวยมาก",
     "sac_thai": None, "chu_de": None, "loai_tru": "thi_truong_khac"},
    {"id": "m4", "nhom": "mkt", "bai": "", "binh_luan": "model bỏ sót câu này",
     "sac_thai": "=", "chu_de": "ND"},
    {"id": "h1", "nhom": "hoi_quy", "bai": "", "binh_luan": "set này bn ạ",
     "sac_thai": "=", "chu_de": "GIA", "mon": "set_qua", "vi_du": True},
    {"id": "t1", "nhom": "trung_lap", "bai": "Vlog KOL", "binh_luan": "quay ở đâu vậy",
     "sac_thai": "=", "chu_de": "ND"},
    {"id": "t2", "nhom": "trung_lap", "bai": "Vlog KOL", "binh_luan": "nay mới thấy",
     "sac_thai": "=", "chu_de": "ND"},
    {"id": "k1", "nhom": "khong_brand", "bai": "", "binh_luan": "mẫu này đẹp",
     "sac_thai": "+", "chu_de": "SP"},
]
_BANG = {"vui theo quá": ["=", "ND"], "đã có hàng đâu": ["=", "GIA"], "สวยมาก": ["+", "SP"],
         "set này bn ạ": ["=", "GIA", "set_qua"], "quay ở đâu vậy": ["+", "ND"],
         "nay mới thấy": ["=", "ND"], "mẫu này đẹp": ["+", "SP"]}


def test_gan_nhan_di_dung_duong_phan_loai_kem_bai_va_brand(monkeypatch):
    goi: list = []
    monkeypatch.setattr(P, "_goi_model", _model_gia(_BANG, goi))
    du = C.gan_nhan(_BO)
    assert len(goi) == 4, "mỗi nhóm một lượt gọi model"
    khong = next(g for g in goi if "mẫu này đẹp" in g)
    du_lieu = khong[len(P._NHAC):]
    assert "BRAND đang theo dõi (" not in du_lieu and "<b k=" not in du_lieu, \
        "nhóm khong_brand gọi như deep dive: không brand, không bài"
    assert "BRAND đang theo dõi" in goi[0] and "HAPAS" in goi[0]
    assert '<b k="0">Bài KOL ăn tôm khô</b>' in goi[0], "bài chứa bình luận đi kèm, mỗi bài một lần"
    assert goi[0].count("Bài KOL ăn tôm khô") == 1
    assert du[0] == {"sac": "=", "cd": "ND", "mon": None}
    assert du[3] == {"sac": None, "cd": None, "mon": None}, "bỏ sót -> chưa phân loại"
    assert du[4] == {"sac": "=", "cd": "GIA", "mon": "set_qua"}

    diem = [C.cham(c, d) for c, d in zip(_BO, du)]
    tong = C.tong_hop(_BO, diem)
    assert tong["mkt_giu_lai"]["sac"] == [0, 2] and tong["mkt_giu_lai"]["cd"] == [1, 2]
    assert tong["mkt_vi_du"]["sac"] == [1, 1], "ca đã thành ví dụ tách nhóm riêng"
    assert tong["hoi_quy"] == {"sac": [1, 1], "cd": [1, 1], "mon": [1, 1]}
    assert sum(v["sac"][1] for v in tong.values()) == 7, "ca loại trừ không chấm"
    assert tong["trung_lap"]["sac"] == [1, 2] and tong["khong_brand"]["sac"] == [1, 1]
    assert C.cong_sai(_BO, du) == [1, 2], "trung_lap: một ca bị kéo thành '+'"


def test_main_chay_nhieu_lan_in_tong_va_ghi_json(monkeypatch, tmp_path, capsys):
    bo = tmp_path / "bo.jsonl"
    bo.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in _BO), encoding="utf-8")
    goi: list = []
    monkeypatch.setattr(P, "_goi_model", _model_gia(_BANG, goi))
    # main tự vá hai thứ này: đặt trước bằng monkeypatch để bộ thử trả lại sau bài.
    monkeypatch.setattr(tai_khoan_ai, "bao_loi", tai_khoan_ai.bao_loi)
    monkeypatch.setenv("MARK_THEO_TAI_KHOAN_CONSOLE", "0")
    monkeypatch.setenv("AUDIT_TO_BASE", "1")
    for k in [k for k in os.environ if k.startswith(("LSR_", "PHOENIX_"))]:
        monkeypatch.delenv(k)                       # bộ thử trả lại sau bài
    monkeypatch.setenv("LSR_TELEMETRY_API_KEY", "x")
    ra = tmp_path / "ra.json"
    assert C.main(["--bo", str(bo), "--lan", "2", "--json-ra", str(ra)]) == 0
    out = capsys.readouterr().out
    assert out.count("── lần ") == 2 and "── tổng các lần" in out
    assert "mkt_giu_lai  sắc thái  0/2 (0%)  0/2 (0%)" in out
    assert "[loại trừ: thi_truong_khac]" in out and "m1 " in out.split("── ca dao động")[1]
    assert not [k for k in os.environ if k.startswith(("LSR_", "PHOENIX_"))], \
        "main bỏ biến platform kể cả khi không có --env"
    assert os.environ["AUDIT_TO_BASE"] == "0"
    assert len(goi) == 8 and 'trung_lap "+" sai' in out
    ket = json.loads(ra.read_text(encoding="utf-8"))
    assert [k["id"] for k in ket] == [c["id"] for c in _BO] and len(ket[0]["lan"]) == 2


def test_nap_env_bo_bien_platform(tmp_path, monkeypatch):
    tep = tmp_path / ".env"
    tep.write_text("# chú thích\nAGENT_MODEL=m-thu\nLSR_TELEMETRY_API_KEY=bi-mat\n"
                   "PHOENIX_API_KEY=x\nRONG\n", encoding="utf-8")
    import os
    for k in [k for k in os.environ if k.startswith(("LSR_", "PHOENIX_"))]:
        monkeypatch.delenv(k)       # bộ thử trả lại sau bài
    monkeypatch.setenv("LSR_COLLECTOR", "http://x")
    monkeypatch.setenv("AGENT_MODEL", "cu")
    monkeypatch.setenv("AUDIT_TO_BASE", "1")
    assert C.nap_env(tep) == 1
    assert os.environ["AGENT_MODEL"] == "m-thu" and os.environ["AUDIT_TO_BASE"] == "0"
    assert not [k for k in os.environ if k.startswith(("LSR_", "PHOENIX_"))]
