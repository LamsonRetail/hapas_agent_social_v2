"""Chuẩn hoá chữ MXH dùng chung dashboard + Mark (`dashboard/chuan_chu.py`, 16/10/2026)."""
from __future__ import annotations

from dashboard import chuan_chu as CC


def test_nfkc_ghep_dau_chu_kieu_cach():
    """Rà 15/10: NFC để dấu rời của chữ kiểu cách thành chỗ cắt chữ ("cuối" → "cuo")."""
    t = "𝐃𝐚́𝐧 𝐦𝐚𝐱 𝐜𝐮𝐨̂́𝐢 𝐯𝐚̀𝐨 𝐬𝐨̣̂𝐩-𝐩𝐢𝐢 𝐥𝐚̀ 𝐫𝐚 𝐦𝐚̂̃𝐮"
    assert CC.thuong(t) == "dán max cuối vào sộp-pii là ra mẫu"
    assert CC.bo_dau(t) == "dan max cuoi vao sop-pii la ra mau"
    assert CC.bo_dau("ĐẸP Đơn") == "dep don"
    assert CC.dem_chu_kieu("𝐃𝐚́𝐧 AHS") == (3, 6)


def test_teen_code_theo_ngu_canh():
    cases = {
        "Mk xin giá ak": "mình xin giá ạ", "mik/mjk/mh": "mình/mình/mình",
        "giá bn": "giá bao nhiêu", "Bn ạ": "bao nhiêu ạ", "bn ơi": "bạn ơi", "cảm ơn bn": "cảm ơn bạn",
        "ko đc": "không được", "dc k": "được không", "đẹp k shop": "đẹp không shop",
        "299 k ship": "299 k ship", "299k": "299k",                       # k sau số = nghìn
        "ak shop ơi": "ak shop ơi",                                       # ak giữa câu: giữ
        "xin giá sét túi trắng": "xin giá set túi trắng", "giá sét": "giá set",
        "sét đánh": "sét đánh",                                           # không phải "bộ"
        "zán cam ah": "dán cam ạ",
        "túi đeo hông": "túi đeo hông",                                   # "hông" không đổi
    }
    for vao, ra in cases.items():
        assert CC.chuan_hoa(vao) == ra, vao


def test_khoa_va_tim():
    assert CC.khoa("Xin  giá sét túi") == CC.khoa("xin gia set tui") == "xin gia set tui"
    assert CC.khoa("mk xin") == "minh xin"
    assert CC.chua(CC.khoa_tim("MK XIN"), "Ship lâu quá, mình xin link mua")
    assert CC.chua(CC.khoa_tim("bao nhiêu"), "giá bn shop")
    assert CC.chua(CC.khoa_tim(""), "bất kỳ")
    # Chữ tìm còn 1 ký tự sau teen code ("ak" → "a") thì không khớp mọi thứ.
    assert CC.khoa_tim("ak") == "ak" and not CC.chua("ak", "túi đẹp")
