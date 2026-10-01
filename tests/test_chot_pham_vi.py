"""Cổng chốt phạm vi: tool cào tốn tiền chỉ chạy khi người dùng đã đồng ý.

Câu mẫu lấy từ sổ audit thật: các câu chốt của Mark tháng 9 (phải cho chạy ở lượt sau) và
hai lượt 01/10 Claude quét thẳng không hỏi (phải chặn).
"""
import contextvars
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import brain
import chot_pham_vi as C
import lenh_cung

# ---- câu thật trong sổ audit ----------------------------------------------------------
CAU_CHOT_THANG_9 = [
    "…giới hạn 100 bài. Kết quả sẽ là mẫu phát hiện tín hiệu, không đại diện toàn bộ thị "
    "trường. Chạy nhé? 👀",
    "…nếu không, tôi sẽ báo rõ thay vì đoán.  Bạn xác nhận “chạy” là tôi quét ngay.",
    "…đối thủ nổi bật và 3–5 cơ hội cho HAPAS.  Phần quét social có phát sinh chi phí. "
    "Bạn xác nhận phạm vi trên để tôi chạy nhé?",
    "…chưa gồm bình luận.  Lượt quét này có phát sinh chi phí. Bạn xác nhận để tôi chạy "
    "và trả tổng số kèm breakdown từng nền tảng nhé?",
    "…(hợp HAPAS), hay quét rộng mọi chủ đề?  Chốt 2 ý này, tôi sẽ tổng hợp các "
    "video/hashtag nổi bật vào Sheet và rút ra angle content có thể dùng.",
    "“Sớm” đang cần chốt khung ngày: bạn muốn quét từ 01/09 đến hôm nay 30/09/2026, hay "
    "một khoảng khác?",
    "Tôi sẽ quét từ khoá “HAPAS” tại Việt Nam trên 2 nền tảng này, tối đa 100 bài mỗi "
    "nguồn. Chạy nhé?",
]

# Câu Mark nói ngay trước hai lượt quét thẳng 01/10 — không phải câu chốt.
CAU_KHONG_PHAI_CHOT = [
    "Mark Trần đây 😎 — trợ lý social của Lamson Retail. Bạn cần tôi soi gì tiếp không — "
    "trend, đối thủ, hay bóc bình luận bài nào đó?",
    "Hi Ngân! 👀 Mark Trần đây — trợ lý social của Lamson Retail.  Hôm nay cần tôi xử lý gì "
    "không? Soi đối thủ, hóng trend, hay lo phần KOL/KOC? Cứ quăng đề bài là tôi cân ngay.",
    "",
    # báo cáo deep dive: "lấy không được" là kể lại, không phải hỏi
    "Bài 3 lấy không được bình luận (bài đã tắt comment). Sheet: https://x/sheets/abc",
    # "xác nhận … chạy" trong câu kể việc, KHÔNG độn chữ để đẩy ra khỏi đoạn cuối
    "Số liệu tuần này cần xác nhận lại với team ads trước khi chạy ngân sách.",
    "Đã xác nhận với team: lượt quét hôm qua chạy đủ 5 nền tảng. Sheet: https://x/s/abc",
    "Tôi đã quét xong, team ads sẽ xác nhận số liệu sau.",
    # câu hỏi và chữ "chốt" ở hai câu khác nhau
    "Bạn mở được Sheet không? Hôm qua team đã chốt ngân sách tháng 10.",
    # "xác nhận" lọt giữa một báo cáo dài, đoạn cuối không hỏi gì
    "Bạn xác nhận giúp con số này với team nhé, rồi chạy tiếp. "
    + "Chi tiết từng nền tảng như sau. " * 40 + "Sheet đầy đủ: https://x/sheets/abc",
]


@pytest.fixture
def luot():
    """Mở ngữ cảnh một lượt như brain.reply làm, tự đóng khi xong."""
    moc = []

    def mo(hoi="", truoc="", lenh=""):
        moc.append(C.dat(lenh, hoi, truoc))
    yield mo
    for m in reversed(moc):
        C.bo(m)


@pytest.mark.parametrize("cau", CAU_CHOT_THANG_9)
@pytest.mark.parametrize("tool", sorted(C.TOOL_TON_TIEN))
def test_tra_loi_cau_chot_thi_cho_chay(luot, cau, tool):
    luot(hoi="Ok", truoc=cau)
    assert C.xet(tool) is None


@pytest.mark.parametrize("cau", CAU_KHONG_PHAI_CHOT)
@pytest.mark.parametrize("tool", sorted(C.TOOL_TON_TIEN))
def test_chua_chot_thi_chan_moi_tool_ton_tien(luot, cau, tool):
    luot(hoi="hóng xem những trend đang viral tại việt nam tuần này là gì em", truoc=cau)
    ly_do = C.xet(tool)
    assert ly_do and "Chạy nhé?" in ly_do and tool in ly_do


def test_hai_luot_quet_thang_ngay_01_10_bi_chan(luot):
    luot(hoi="có chiến dịch hapas nào viral không ?", truoc=CAU_KHONG_PHAI_CHOT[1])
    assert C.xet("social_listen")


@pytest.mark.parametrize("hoi", [
    "quét luôn trend tiktok, đủ 800 bài , các trend mới đang nổi",
    "chạy ngay giúp mình từ khoá hapas 7 ngày",
    "Quét đi, không cần hỏi lại",
    "soi luôn tài khoản @hapas.official",
    "khỏi hỏi, cứ lấy 100 bài",
])
def test_noi_ro_khong_can_hoi_thi_cho_chay(luot, hoi):
    luot(hoi=hoi)
    assert C.xet("social_listen") is None


LENH_TON_TIEN = {lenh: tool for lenh, tool in lenh_cung.BANG_LENH.items()
                 if tool in C.TOOL_TON_TIEN}


def test_moi_tool_ton_tien_deu_co_lenh_cung():
    assert set(LENH_TON_TIEN.values()) == C.TOOL_TON_TIEN


@pytest.mark.parametrize("lenh,tool", sorted(LENH_TON_TIEN.items()))
def test_lenh_cung_mo_dung_tool_cua_no(luot, lenh, tool):
    luot(hoi="hapas", lenh=lenh_cung.BANG_LENH[lenh])
    assert C.xet(tool) is None
    khac = sorted(C.TOOL_TON_TIEN - {tool})
    assert all(C.xet(t) for t in khac), f"{lenh} không được mở khoá tool khác"


@pytest.mark.parametrize("lenh", ["/kho", "/web", "/nho", "/nhac", "/bang", "/ad", "/read"])
def test_lenh_khac_khong_mo_khoa_tool_ton_tien(luot, lenh):
    luot(hoi="hapas", lenh=lenh_cung.BANG_LENH.get(lenh, ""))
    assert all(C.xet(t) for t in C.TOOL_TON_TIEN)


@pytest.mark.parametrize("tool", ["doc_bang", "tra_kho", "web_crawl", "web_scrape",
                                  "fb_ads_library", "dung_ky_nang", "lark_cli"])
def test_tool_khong_ton_tien_khong_bao_gio_bi_chan(luot, tool):
    luot(hoi="đọc giúp", truoc="")
    assert C.xet(tool) is None


def test_ngoai_luot_tra_loi_khong_ap_cong():
    assert C._NGU_CANH.get() is None
    assert C.xet("social_listen") is None


def test_bo_tra_ve_dung_trang_thai_truoc():
    a = C.dat("", "x", "")
    b = C.dat("/search", "y", "")
    C.bo(b)
    assert C._NGU_CANH.get()["hoi"] == "x"
    C.bo(a)
    assert C._NGU_CANH.get() is None


def test_tool_chay_song_song_van_thay_ngu_canh(luot):
    """Hermes chạy tool song song bằng copy_context().run — cổng phải thấy lượt hiện tại."""
    luot(hoi="hóng trend", truoc="")
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(contextvars.copy_context().run, C.xet, "social_listen")
                for _ in range(2)]
        kq = [f.result() for f in futs]
    assert all(kq)


def test_hai_chat_song_song_khong_lan_nhau():
    """Hai lượt ở hai thread: người đã chốt chạy được, người chưa chốt bị chặn."""
    ra = {}
    rao = threading.Barrier(2)

    def chay(ten, truoc):
        C.dat("", "ok", truoc)
        rao.wait()
        ra[ten] = C.xet("social_listen")

    t1 = threading.Thread(target=chay, args=("da_chot", "Chạy nhé?"))
    t2 = threading.Thread(target=chay, args=("chua_chot", "Chào bạn 😎"))
    t1.start(), t2.start()
    t1.join(), t2.join()
    assert ra["da_chot"] is None and ra["chua_chot"]


# ---- bọc dispatch -----------------------------------------------------------------------
class _RegistryGia:
    def __init__(self):
        self.da_goi = []

    def dispatch(self, name, args, **kw):
        self.da_goi.append(name)
        return json.dumps({"ok": True})


def test_boc_dispatch_chan_khong_goi_handler_va_ghi_audit(luot):
    reg, audit_ghi = _RegistryGia(), []
    assert C.cai_vao_registry(lambda *a, **k: audit_ghi.append((a, k)), registry=reg)
    luot(hoi="hóng trend", truoc="")
    kq = json.loads(reg.dispatch("social_listen", {"queries": ["hapas"]}))
    assert kq["error"] == "can_chot_pham_vi" and "Chạy nhé?" in kq["huong_dan"]
    assert reg.da_goi == [], "bị chặn thì tuyệt đối không chạm handler (không tốn tiền)"
    assert audit_ghi and audit_ghi[0][1]["loi"] == "chờ chốt phạm vi"
    assert json.loads(reg.dispatch("doc_bang", {}))["ok"] is True


def test_boc_dispatch_cho_chay_khi_da_chot(luot):
    reg = _RegistryGia()
    C.cai_vao_registry(None, registry=reg)
    luot(hoi="ok", truoc="Chạy nhé?")
    assert json.loads(reg.dispatch("social_listen", {}))["ok"] is True
    assert reg.da_goi == ["social_listen"]


def test_boc_dispatch_chi_cai_mot_lan():
    reg = _RegistryGia()
    C.cai_vao_registry(None, registry=reg)
    lan1 = reg.dispatch
    C.cai_vao_registry(None, registry=reg)
    assert reg.dispatch == lan1


def test_registry_that_da_cai_cong_va_policy_xet_truoc(monkeypatch, luot):
    """Tool đang TẮT trên console → người dùng nghe 'đang tắt', không bị hỏi 'Chạy nhé?'."""
    from tools.registry import registry
    assert getattr(registry, "_mark_chot_pham_vi", False)
    luot(hoi="hóng trend", truoc="")
    monkeypatch.setattr(brain.lsr_policy, "nang_luc_bat", lambda: {"doc_bang"})
    kq = json.loads(registry.dispatch("social_listen", {}))
    assert kq["error"] == "policy_denied" and "TẮT" in kq["reason"]
    monkeypatch.setattr(brain.lsr_policy, "nang_luc_bat",
                        lambda: brain.lsr_policy.KHONG_THU_HEP)
    kq = json.loads(registry.dispatch("social_listen", {}))
    assert kq["error"] == "can_chot_pham_vi"


# ---- nối trọn qua brain.reply -----------------------------------------------------------
def _gia_reply(monkeypatch, lich_su, run):
    class A:
        model = "m"

        def run_conversation(self, *a, **k):
            return run()
    monkeypatch.setattr(brain, "_dung_agent", lambda *a, **k: A())
    monkeypatch.setattr(brain.lsr_platform, "lay_ngu_canh", lambda *a, **k: {})
    monkeypatch.setattr(brain.lsr_platform, "ghi_luot_ngu_canh", lambda *a, **k: None)
    monkeypatch.setattr(brain.memory_store, "load_history", lambda cid: lich_su)
    monkeypatch.setattr(brain.memory_store, "append_turns", lambda *a, **k: None)
    monkeypatch.setattr(brain.audit, "bat_dau", lambda *a, **k: "t")
    monkeypatch.setattr(brain.audit, "ket_thuc", lambda *a, **k: {})


def _xet_trong_reply(monkeypatch, lich_su, hoi):
    thay = {}

    def run():
        thay["xet"] = C.xet("social_listen")
        return {"final_response": "xong", "messages": []}
    _gia_reply(monkeypatch, lich_su, run)
    brain.reply(hoi, chat_id="thu-chot", sender_open_id=None)
    return thay["xet"]


def test_reply_cau_dau_tien_bi_chan(monkeypatch):
    assert _xet_trong_reply(monkeypatch, [], "có chiến dịch hapas nào viral không ?")
    assert C._NGU_CANH.get() is None, "xong lượt phải gỡ ngữ cảnh"


def test_reply_tra_loi_ok_sau_cau_chot_thi_chay(monkeypatch):
    lich_su = [{"role": "user", "text": "quét hapas tuần này"},
               {"role": "assistant", "text": "TikTok + Threads, 7 ngày, 100 bài. Chạy nhé?"}]
    assert _xet_trong_reply(monkeypatch, lich_su, "ok") is None


def test_reply_chi_xet_cau_mark_gan_nhat(monkeypatch):
    """Câu chốt CŨ, sau đó Mark đã trả lời việc khác → câu mới không còn là đồng ý quét."""
    lich_su = [{"role": "assistant", "text": "Chạy nhé?"},
               {"role": "user", "text": "ok"},
               {"role": "assistant", "text": "Sheet đầy đủ: https://x/sheets/abc"}]
    assert _xet_trong_reply(monkeypatch, lich_su, "quét thêm instagram")


@pytest.fixture
def bat_het_nang_luc(monkeypatch):
    monkeypatch.setattr(brain.lsr_policy, "nang_luc_bat",
                        lambda: brain.lsr_policy.KHONG_THU_HEP)


def test_reply_lenh_search_mo_social_listen(monkeypatch, bat_het_nang_luc):
    assert _xet_trong_reply(monkeypatch, [], "/search hapas 7 ngày") is None


def test_reply_lenh_kho_khong_mo_social_listen(monkeypatch, bat_het_nang_luc):
    assert _xet_trong_reply(monkeypatch, [], "/kho hapas có viral không")


def test_reply_loi_van_go_ngu_canh(monkeypatch):
    def run():
        raise RuntimeError("hỏng")
    _gia_reply(monkeypatch, [], run)
    with pytest.raises(RuntimeError):
        brain.reply("quét", chat_id="thu-chot", sender_open_id=None)
    assert C._NGU_CANH.get() is None
