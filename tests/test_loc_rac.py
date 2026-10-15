"""Lọc spam / rác / trùng (đợt 2d, 15/10/2026). Mẫu lấy từ dữ liệu thật HAPAS 14/10 (đã ẩn
danh): "." ×26, "Hapas tặng" lặp, link shop giả, "Ib"/"Xin giá" là KHÁCH HỎI MUA (giữ)."""
from __future__ import annotations

import loc_rac as L


def _mot(text, tac_gia="khach", **kw):
    r = [{"khoa_bai": "tiktok:1", "tac_gia": tac_gia, "noi_dung": text, **kw}]
    L.phan_loai(r)
    return r[0]["loai"], r[0]["ly_do_loc"]


def test_hoi_mua_la_hop_le_khong_phai_spam():
    for t in ("Ib", "ib ạ", "Xin giá", "Bn ạ", "Phải trang chính hãng k ạ", "Túi đẹp quá shop ơi",
              "em sđt 0912 345 678 tư vấn giúp", "Có kết quả giveaway chx ạ"):
        assert _mot(t) == ("hop_le", None), t


def test_it_noi_dung():
    for t in (".", "…", "🥰🥰", "chấm", "  ", "In", "?"):
        assert _mot(t)[0] == "it_noi_dung", t


def test_spam_cac_loai():
    assert _mot("🔥🔥Hot mua hàng chính hãng của shop giảm đến 50% tại đây "
                "https://www.facebook.com/100073650") == ("spam", "lien_ket_quang_cao")
    assert _mot("Xem thêm mẫu tại đây nhé")[1] == "ban_hang_khac"
    assert _mot("Mua hàng chính hãng giá hot https://bit.ly/abc")[1] == "lien_ket_quang_cao"
    assert _mot("Kết bạn zalo 0912345678 nhận quà")[1] == "keo_khach"
    assert _mot("Việc nhẹ lương cao 500k/ngày")[1] == "viec_lam_mmo"
    assert _mot("Vay tiền online giải ngân trong ngày")[1] == "vay_tien"
    assert _mot("nhà cái uy tín nổ hũ")[1] == "co_bac"
    assert _mot("sale 0912.345.678 https://abc.xyz")[1] == "lien_ket_quang_cao"
    assert _mot("liên hệ 0912.345.678 https://zalo.me/x")[1] == "so_dien_thoai_quang_cao"
    # link tới brand của dự án + chính hãng: không phải shop giả
    r = [{"khoa_bai": "b", "tac_gia": "x", "noi_dung": "mua chính hãng tại https://hapas.vn nhé"}]
    L.phan_loai(r, ["hapas"])
    assert r[0]["loai"] == "hop_le"


def test_khach_hoi_khong_bi_coi_la_spam():
    """Review 15/10: các câu khách thật bị bắt nhầm ở bản đầu."""
    for t in ("Shop em có size L không", "shop mình có bán ở HCM ko", "Có giảm 10% không shop",
              "Hàng có chính hãng không shop? sđt 0987654321", "Có freeship không ạ 0912345678",
              "Đang sale à shop, mình 0912 345 678", "mình làm tại nhà mua được không",
              "Telegram có nhóm không ạ", "có hỗ trợ trả góp không", "zalo shop là gì ạ",
              "link mua ở đâu ạ", "0987654321 tư vấn em với"):
        assert _mot(t) == ("hop_le", None), t


def test_trung_cung_nguoi_cung_bai_giu_ban_dau():
    r = [{"khoa_bai": "b1", "tac_gia": "Lan", "noi_dung": "Hapas tặng"},
         {"khoa_bai": "b1", "tac_gia": "lan", "noi_dung": "hapas  tặng!!"},
         {"khoa_bai": "b2", "tac_gia": "Lan", "noi_dung": "Hapas tặng"},       # bài khác
         {"khoa_bai": "b1", "tac_gia": "Hoa", "noi_dung": "Hapas tặng"}]       # người khác
    L.phan_loai(r)
    assert [x["loai"] for x in r] == ["hop_le", "trung", "hop_le", "hop_le"]


def test_thuong_hieu_uu_tien_va_ma_noi_dung():
    assert _mot("Dạ shop ib bạn ạ", cua_thuong_hieu=True)[0] == "thuong_hieu"
    assert L.ma_noi_dung("Túi ĐẸPPPPP quá shop ơi!!! 😍", 15) == L.ma_noi_dung("tui depp qua shop oi", 15)
    assert L.ma_noi_dung("shop ơi cho mình xin giá ạ", L.SEEDING_TOI_THIEU_CHU) is None
    assert L.ma_noi_dung("Ib ạ", 15) is None                       # quá ngắn để kết luận trùng
    assert L.ma_noi_dung("Giá 299k nhé", 1) == L.ma_noi_dung("Giá 300k nhé", 1)   # số → 0


def test_bai_spam():
    assert L.bai_spam("Tuyển CTV việc nhẹ lương cao") == "viec_lam_mmo"
    assert L.bai_spam("Review túi HAPAS mới mua") == ""
