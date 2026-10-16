"""Lọc spam / rác / trùng (đợt 2d, 15/10/2026). Mẫu lấy từ dữ liệu thật HAPAS 14/10 (đã ẩn
danh): "." ×26, "Hapas tặng" lặp, link shop giả, "Ib"/"Xin giá" là KHÁCH HỎI MUA (giữ)."""
from __future__ import annotations

import datetime

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


# ───────────── spam affiliate "dán mã" (rà kho 15/10/2026, 16/10/2026) ─────────────
# Hai mẫu THẬT (đã bỏ tên người viết) + biến thể cùng kiểu.
AFF_THAT = ("𝐃𝐚́𝐧 𝐦𝐚𝐱 𝐜𝐮𝐨̂́𝐢 𝐯𝐚̀𝐨 𝐬𝐨̣̂𝐩-𝐩𝐢𝐢 𝐥𝐚̀ 𝐫𝐚 𝐦𝐚̂̃𝐮 𝐯𝐚̀ 𝐠𝐢𝐚́ AHS-WCM-DQN",
            "CJW-UJK-A88AH xóa 88 rồi zán cam ah")


def test_spam_affiliate_mot_binh_luan():
    for t in (*AFF_THAT,
              "𝐃𝐚́𝐧 𝐦𝐚𝐱 𝐜𝐮𝐨̂́𝐢 𝐯𝐚̀𝐨 𝐬𝐨̣̂𝐩-𝐩𝐢𝐢 𝐥𝐚̀ 𝐫𝐚 𝐠𝐢𝐚́",          # chữ kiểu cách + lời dặn, không mã
              "dán mã KQX-77A-PLM vào shopee nhé",                  # mã + lời dặn + sàn
              "AHS–WCM–DQN shopee",                                 # gạch dài, mã + sàn
              "𝐂𝐉𝐖-𝐔𝐉𝐊-𝐀𝟖𝟖𝐀𝐇 𝐱𝐨́𝐚 𝟖𝟖 𝐫𝐨̂̀𝐢 𝐳𝐚́𝐧 𝐜𝐚𝐦"):            # mã viết bằng chữ kiểu cách
        assert _mot(t) == ("spam", "affiliate_dan_ma"), t
    assert L.dau_hieu_affiliate(AFF_THAT[0]) == {"ma", "cum", "san", "font"}
    assert L.dau_hieu_affiliate(AFF_THAT[1]) == {"ma", "cum"}


def test_spam_affiliate_khong_bat_nham_khach_that():
    """Câu khách thật: không mã nhiều khúc, không chữ kiểu cách → không bao giờ là affiliate. "ib",
    "xin giá" dưới bài của brand là Ý ĐỊNH MUA — phải giữ hợp lệ."""
    for t in ("mã giảm giá ở đâu ạ", "shop có mã giảm giá không", "mình mua trên shopee được không",
              "xin giá set túi trắng", "ib mình nhé", "Ib", "Xin giá", "Bn ạ",
              "link shopee của shop đâu ạ", "dán mã vào shopee không được shop ơi",   # sàn + lời dặn
              "Mã SALE50 dùng được không", "sđt 0912-345-678 tư vấn giúp",          # SĐT toàn số
              "đơn 2026-10-15 chưa nhận", "𝐓𝐮́𝐢 đẹp quá", "𝓒𝓱𝓾́𝓬 𝓶𝓾̛̀𝓷𝓰 𝓼𝓱𝓸𝓹",              # chỉ chữ kiểu
              "https://s.shopee.vn/AbC-DEF-GHI-JKL xem giúp mình"):                 # mã trong link
        assert _mot(t) == ("hop_le", None), t


def _bl_aff(ma, tg, gio, nd="AHS-WCM-DQN", loai="hop_le", bai="tiktok:1", **kw):
    luc = datetime.datetime(2026, 10, 14, 0, 0, tzinfo=datetime.timezone.utc)
    return {"khoa_bai": bai, "ma": ma, "tac_gia": tg, "noi_dung": nd, "loai": loai,
            "luc": luc + datetime.timedelta(hours=gio), "cua_thuong_hieu": False, **kw}


def test_affiliate_hang_loat_cap_bai():
    """≥ 5 tài khoản khác nhau có mã / chữ kiểu cách dưới CÙNG một bài trong 48 giờ → spam, kể cả
    bình luận chỉ có mã (luật một bình luận không bắt được)."""
    rows = [_bl_aff(f"c{i}", f"Acc {i}", i * 10) for i in range(5)]        # 0h … 40h
    assert sorted(L.affiliate_hang_loat(rows)) == [("tiktok:1", f"c{i}") for i in range(5)]
    assert L.affiliate_hang_loat(rows[:4]) == []                           # 4 tài khoản: chưa đủ
    xa = [_bl_aff(f"c{i}", f"Acc {i}", i * 13) for i in range(5)]         # 0h … 52h: lệch khung
    assert L.affiliate_hang_loat(xa) == []
    cung_nguoi = [_bl_aff(f"c{i}", "Acc", i) for i in range(6)]            # một tài khoản 6 lần
    assert L.affiliate_hang_loat(cung_nguoi) == []
    khac_bai = rows[:3] + [_bl_aff(f"d{i}", f"B {i}", i, bai="tiktok:2") for i in range(2)]
    assert L.affiliate_hang_loat(khac_bai) == []                           # mỗi bài xét riêng
    # Spam affiliate sẵn có vẫn được đếm (cùng đợt) nhưng không trả lại; chỉ hạ nhãn hop_le;
    # khách thật không mã trong cùng khung không bị đụng; thương hiệu bỏ qua.
    tron = [_bl_aff("s0", "Acc 0", 0, loai="spam", ly_do_loc="affiliate_dan_ma"),
            _bl_aff("t1", "Acc 1", 1, loai="trung"),
            *[_bl_aff(f"c{i}", f"Acc {i}", i) for i in (2, 3, 4)],
            _bl_aff("k", "Khách", 5, nd="xin giá set túi trắng"),
            _bl_aff("h", "HAPAS", 6, cua_thuong_hieu=True, loai="thuong_hieu")]
    assert sorted(L.affiliate_hang_loat(tron)) == [("tiktok:1", "c2"), ("tiktok:1", "c3"),
                                                   ("tiktok:1", "c4")]
    assert ("tiktok:1", "t1") in L.affiliate_hang_loat(tron, ha_duoc=("hop_le", "trung"))
    # Dấu hiệu cấp bài: mã HOẶC chữ kiểu cách; "shopee" một mình không phải.
    assert L.co_dau_hieu_hang_loat("𝐠𝐢𝐚́ 𝐫𝐞̉ 𝐪𝐮𝐚́ 𝐧𝐞̀") and not L.co_dau_hieu_hang_loat("mua shopee")
