"""Hermes brain for the Mark bot.

Drives Hermes with the openai-codex provider (ChatGPT/Codex quota, model from
AGENT_MODEL — currently gpt-5.6-terra). Hermes writes the reply; run.py sends it
out with the bot's tenant token.

Heads-up: this Codex quota is SHARED with the meeting agent, which is the
higher-priority production bot. That is why AGENT_MAX_WORKERS is held at 2.

Design (validated end-to-end):
    rt    = resolve_runtime_provider(requested="openai-codex")   # reads config.yaml + auth.json
    agent = AIAgent(model, provider=rt["provider"], api_mode=rt["api_mode"],
                    base_url=rt["base_url"], api_key=rt["api_key"], ...)
    out   = agent.run_conversation(prompt)   # -> {"final_response": "..."}

Credentials are resolved per-message so a freshly refreshed Codex JWT is always
picked up. History is kept per-chat so follow-ups like "ok" carry context.
"""

from __future__ import annotations

import datetime
import os
import re
import sys
import unicodedata
from pathlib import Path

import lark_client as lark
import lsr_platform
import lenh_cung
import dong_ho_luot
import lsr_policy
import tai_khoan_ai
from config import config

# Make Hermes importable and point it at its home (config.yaml, auth.json, toolsets).
os.environ.setdefault("HERMES_HOME", config.hermes_home)
os.environ.setdefault("PYTHONUTF8", "1")
if config.hermes_agent_dir not in sys.path:
    sys.path.insert(0, config.hermes_agent_dir)

from hermes_cli.runtime_provider import resolve_runtime_provider  # noqa: E402
from run_agent import AIAgent  # noqa: E402

# Register the Lark BOT tool into Hermes' global tool registry. MUST happen
# before AIAgent() is constructed — the agent snapshots the registry at init.
# lark_cli_tool is imported so its `lark_cli` (override=True) wins over Hermes'
# built-in feishu-bot version. (The as-user REST passthrough `lark_tool` is NOT
# used in bot mode — a bot has no user_access_token.)
import lark_cli_tool  # noqa: E402,F401  (registers `lark_cli` as bot)
import fb_ads_tool  # noqa: E402,F401  (registers `fb_ads_library`: Meta Ad Library via browser)
import apify_tool  # noqa: E402,F401  (registers `social_listen`: 5 nền tảng -> Lark Sheet)
import deep_dive_tool  # noqa: E402,F401  (registers `social_deep_dive`: bình luận -> Lark Sheet)
import web_tool  # noqa: E402,F401  (registers `web_scrape`: website công khai qua Scrapling)
import crawl_tool  # noqa: E402,F401  (registers `web_crawl`: cào sản phẩm -> Lark Sheet)
import ky_nang_tool  # noqa: E402,F401  (registers `dung_ky_nang`: nạp thân kỹ năng khi cần)
import account_tool  # noqa: E402,F401  (registers `soi_tai_khoan`: soi tài khoản brand/KOC)
import shopee_tool  # noqa: E402,F401  (registers `soi_san`: giá và sản phẩm trên Shopee)
import tiktok_ads_tool  # noqa: E402,F401  (registers `tiktok_top_ads`: top ads TikTok -> Lark Sheet)
import kenh_nha_tool  # noqa: E402,F401  (registers `binh_luan_kenh_nha`: bình luận kênh HAPAS qua API Meta)
import chi_so_bai_tool  # noqa: E402,F401  (registers `chi_so_bai`: view/like/share theo danh sách link bài)
import chi_phi_tool  # noqa: E402,F401  (registers `tra_chi_phi_quet`: tra sổ chi phí khi được hỏi)
import viec_nen  # noqa: E402,F401  (registers `tra_viec_nen`/`huy_viec_nen`: việc quét nền)
import bang_tool  # noqa: E402,F401  (registers `doc_bang`: đọc nguyên Base/Sheet khi người hỏi có quyền)
import viec_base_tool  # noqa: E402,F401  (registers `xem_truoc_viec_base`/`ghi_viec_base`: việc đã duyệt -> Base checklist)
import kho_tool  # noqa: E402,F401  (registers `tra_kho`: tra lại kho bằng nhiều bộ từ khoá)
import bai_hoc_tool  # noqa: E402  (registers `ghi_bai_hoc`/`nho_bai_hoc`: kho bài học chiến dịch, tắt khi thiếu MARK_HINDSIGHT_URL/MARK_HINDSIGHT_API_KEY)
import memory_store  # noqa: E402  (persistent history + per-user memory + remember tool)
import scheduler  # noqa: E402  (reminder tools: schedule/list/cancel)
import audit  # noqa: E402  (audit toàn luồng: token, tool, link, thời gian)
import phoenix_trace  # noqa: E402  (trace sang Phoenix tự host; tắt nếu thiếu env)

# Cưỡng chế policy tại điểm hội tụ dispatch, rồi bọc handler của MỌI tool để tự ghi audit.
# Phải gọi SAU khi tất cả tool đã
# import xong (các import ở trên), và TRƯỚC khi AIAgent đầu tiên được dựng —
# agent chụp lại registry lúc khởi tạo.
lsr_policy.install_registry_guard(audit.ghi_tool)
audit.boc_registry()
# Gắn hook quan sát của Hermes (post_api_request/post_tool_call) — sau khi run_agent và
# model_tools đã import (discover_plugins chạy lúc đó), trước AIAgent đầu tiên.
phoenix_trace.bat()


# ───────────────────────── persona (character card) ─────────────────────────
# Env-overridable so the multi-tenant runtime can give a created agent its own
# persona file; falls back to Mark's persona.md (the shared frame).
_PERSONA_FILE = Path(os.environ.get("AGENT_PERSONA_FILE", "").strip() or Path(__file__).with_name("persona.md"))

# Đội ngũ team Chuyển đổi số — dùng để phân loại vai trò người đang nhắn, khớp
# theo TÊN (không dấu, thường hoá). Nếu biết chắc open_id của sếp, đặt biến môi
# trường AGENT_BOSS_OPEN_ID để nhận diện sếp chính xác 100% (không phụ thuộc tên).
_BOSS_NAME = "Lê Quý Thiện"
_BOD_NAME = "Nguyễn Trần Thi"
_TEAM_MEMBERS = [
    "Nguyễn Tiến Thẩm",
    "Nguyễn Thùy Chi",
    "Vũ Thành Công",
    "Trần Minh Đức",
    "Đỗ Thu Nga",
    "Đinh Hồng Thái",
]

# Hermes công cụ — phần này KHÔNG nằm trong persona.md (đó là "con người" của
# Mark), mà là hướng dẫn kỹ thuật cách dùng tool. Ghép vào cuối system prompt.
_TOOLING_NOTE = "\n".join(
    [
        "\n---\n## HƯỚNG DẪN DÙNG CÔNG CỤ (kỹ thuật — người dùng không thấy phần này)",
        "- Thao tác Lark: ƯU TIÊN `lark_cli` (CLI chính thức, đủ domain: calendar, im, wiki, "
        "docs/docx, drive, task, base, sheets, approval, contact, vc, minutes). Chạy dưới "
        "danh tính BOT (tenant token) — KHÔNG thấy tài nguyên cá nhân của người khác. "
        "Xem lệnh: args=[\"<domain>\",\"--help\"]; ưu tiên +shortcut (vd [\"task\",\"+create\",...]); "
        "xem tham số: [\"schema\",\"<svc.res.method>\"]; gọi thẳng: [\"api\",\"GET\",\"/open-apis/...\"].",
        "- Khi có LINK wiki/tài liệu hoặc nhờ tra cứu/đọc/tạo/sửa nội dung Lark: ĐỪNG nói không truy cập "
        "được — DÙNG tool tự dò API rồi trả lời. Link chứa token/id (…/wiki/XXXX, ?table=YYYY) thì trích ra "
        "và gọi API tương ứng. Chỉ báo lỗi khi tool trả lỗi thật (thiếu quyền/không tồn tại).",
        "- QUẢNG CÁO ĐỐI THỦ (Meta Ad Library) — hỏi 'đối thủ đang chạy ads gì', tổng hợp/liệt kê "
        "ad đang chạy, nội dung & creative quảng cáo, số lượng ad, so sánh ad giữa các brand → "
        "BẮT BUỘC dùng tool `fb_ads_library`. Truyền page_id (ID số Trang FB → xem TẤT CẢ ad của "
        "trang) hoặc query (tên brand/từ khoá khi chưa biết page_id); country mặc định VN, "
        "active_status mặc định active. Kết quả gồm total_results + danh sách ad (library_id, ngày "
        "bắt đầu chạy, nội dung ad) + URL ảnh creative — phải DẪN đúng số/nội dung THẬT, KHÔNG bịa. "
        "MỘT Ad Library bao trọn cả Facebook/Instagram/Messenger/Threads (không có Ad Library riêng "
        "cho IG hay Threads). Khi được hỏi RIÊNG một nền tảng (vd 'ads trên Threads', 'ads bên "
        "Instagram') → truyền tham số `platform` (facebook/instagram/messenger/threads/"
        "audience_network); Meta lọc server-side nên mọi ad trả về đúng nền tảng đó. Ảnh creative là "
        "bản thu nhỏ, link có hạn (tải ngay nếu cần); ad video chỉ có thumbnail.",
        # 04/10: Meta Ad Library không có quảng cáo TikTok.
        "- QUẢNG CÁO TIKTOK ('ads TikTok của đối thủ', 'ngành túi xách chạy ads TikTok gì') → "
        "`tiktok_top_ads` (Top Ads của TikTok Creative Center, theo từ khoá/ngành). Đây là tập "
        "ads hiệu quả cao nhất, KHÔNG phải mọi ad của brand; CTR/chi phí là mức tương đối, "
        "không phải tiền thật; link video hết hạn sau 24–48 giờ.",
        "- DUYỆT WEB / TRANG CÔNG KHAI (`browser_navigate` + `browser_snapshot`/`browser_get_images`/"
        "`browser_click`…): tự mở URL, đọc nội dung, click, lấy ảnh — dùng cho web thường và các "
        "trang công khai KHÔNG cần đăng nhập. LƯU Ý: feed Facebook/Instagram/Threads/TikTok thường "
        "chặn khách bằng tường đăng nhập nên browser KHÔNG đọc được post trong feed; riêng Meta Ad "
        "Library thì công khai — nhưng để tra ad hãy dùng `fb_ads_library` (đã gói sẵn), đừng tự "
        "dựng URL Ad Library bằng browser_navigate. TUYỆT ĐỐI không gắn browser vào profile Chrome "
        "cá nhân của người dùng.",
        "- ẢNH người dùng gửi: câu hỏi sẽ có dòng `[Ảnh đính kèm: <đường dẫn>]` → gọi "
        "`vision_analyze` với ĐÚNG đường dẫn đó rồi trả lời theo nội dung ảnh. Không có dòng "
        "đó nghĩa là không có ảnh — đừng đoán nội dung ảnh.",
        "- KHÔNG có quyền đọc/ghi file trên máy, chạy code Python hay giao việc cho subagent — "
        "đừng thử gọi. Cần tính toán thì tự tính và ghi rõ phép tính.",
        "- ĐẶT NHẮC/HẸN GIỜ: `schedule_reminder` (đến giờ tự gửi vào chat này), xem/hủy bằng "
        "`list_reminders`/`cancel_reminder`. Ai nhờ 'nhắc…' thì XÁC NHẬN thời điểm+nội dung rồi đặt nhắc THẬT.",
        "- `remember_about_user`: ghi nhớ dài hạn thông tin quan trọng về người đang nói chuyện.",
        # 01/10: chạy bằng Claude, Mark quét thẳng ngay câu đầu ("có chiến dịch hapas nào
        # viral không") — luật chỉ nằm trong mô tả tool thì Claude dễ bỏ qua. Nhắc lại ở
        # system prompt; vẫn là lời dặn, không chặn bằng code (chủ agent chọn vậy).
        "- TOOL TỐN TIỀN HOẶC GHI SHEET (`social_listen`, `social_deep_dive`, `soi_tai_khoan`, "
        "`soi_san`, `tiktok_top_ads`, `binh_luan_kenh_nha`, `chi_so_bai` — ba tool cuối gọi "
        "`chi_uoc_tinh`=true trước, miễn phí; `binh_luan_kenh_nha` luôn 0 USD nhưng vẫn hỏi vì "
        "ghi Sheet): "
        "TRƯỚC khi gọi, tóm tắt phạm vi (từ khoá hoặc link, nền tảng, khoảng ngày, số bài) rồi "
        "KẾT THÚC bằng câu hỏi \"Chạy nhé?\" và DỪNG, chờ người dùng trả lời. Chỉ gọi ngay khi: "
        "người dùng vừa đồng ý câu chốt đó (ok, chạy đi, làm luôn…); người dùng nói rõ không "
        "cần hỏi (quét luôn, chạy liền, làm luôn…); hoặc là lệnh cứng (/search, /comment, "
        "/profile, /shop, /topads, /hapas kèm việc cần đọc). Câu hỏi chung như "
        "'có gì viral không', 'hóng trend tuần này' CHƯA "
        "phải là đồng ý quét.",
        # 01/10: Claude viết cả kế hoạch nội bộ lên đầu tin nhắn ("Câu này là trend chung →
        # gọi social_listen với che_do=… ---"), người dùng thấy tên tool và tham số.
        "- CHỈ viết phần gửi người dùng. KHÔNG viết suy nghĩ/kế hoạch nội bộ trước câu trả lời "
        "(kiểu 'Câu này là … → gọi <tool> với …', 'Tôi sẽ chốt phạm vi rồi hỏi…'), KHÔNG nêu "
        "tên tool hay tham số kỹ thuật — nói bằng lời thường ('tôi sẽ quét TikTok 7 ngày…').",
        "- KHÔNG dán JSON/log thô cho người dùng; câu trả lời được gửi tự động dưới danh tính bot.",
        # 01/10: câu trả lời về Taobao liệt kê 6 kiểu túi không có nguồn nào; một lượt khác
        # tả hình quảng cáo trong khi vision trả 403. Nguồn hỏng thì phải lộ ra, không lấp.
        "- NGUỒN HỎNG / BỊ CẮT / CHẠM TRẦN (tool báo lỗi, `platforms_failed`, 'CÓ THỂ BỊ CẮT', "
        "vision hay browser trả lỗi 403…): NÓI RÕ phần đó không có dữ liệu. TUYỆT ĐỐI không lấp "
        "chỗ trống bằng phỏng đoán hay kiến thức chung rồi trình bày như kết quả tra được.",
        # 23/09: cùng một phạm vi, lần trước báo 35 bài, lần sau 24 bài, không một lời giải thích.
        "- Người dùng hỏi LẠI cùng phạm vi trong cùng cuộc chat: đối chiếu với kết quả lần "
        "trước (số cũ, số mới, vì sao lệch — khác khoảng ngày, nguồn, bộ lọc, mẫu). Không "
        "im lặng đưa ra con số mâu thuẫn với lần trước.",
        # 01/10: được nhờ "gán nhãn từng bình luận và thống kê", Mark trả lời là không làm được.
        # 02/10: team hỏi "tích cực hay tiêu cực, focus vào Threads" về BÀI đã quét — Mark
        # đếm tay, không ra %. Bài của `social_listen` nay có nhãn + `thong_ke` như bình luận.
        "- SENTIMENT / ĐO LƯỜNG (tích cực hay tiêu cực, bao nhiêu % khen chê, kể cả hỏi riêng "
        "một nền tảng): CHỈ báo số và % mà tool trả về — `thong_ke`/`dong_thong_ke` của "
        "`social_listen` (sắc thái BÀI, có `theo_nen_tang`) hoặc của `social_deep_dive` (sắc "
        "thái BÌNH LUẬN) — luôn nói đã phân loại bao nhiêu/tổng và phần 'chưa phân loại', dẫn "
        "lời thật từ `trich_dan`. TUYỆT ĐỐI không tự đếm tay hay ước lượng ('khoảng 60%'). "
        "Tool không trả số thì nói chưa có số. Nhờ 'gán nhãn từng bình luận và thống kê' thì "
        "dùng `social_deep_dive` (tool tự gán nhãn), đừng nói không làm được.",
        "- Muốn sentiment ở mức BÌNH LUẬN (người ta bình luận gì, khen chê dưới bài): đề xuất "
        "`social_deep_dive` cho link TikTok, YouTube, Facebook, Threads, Instagram. Threads và "
        "Instagram bóc KHÔNG đăng nhập: không có trả lời lồng nhau, Instagram chỉ được MỘT "
        "PHẦN bình luận công khai — khi báo phải nói rõ giới hạn đó (`gioi_han_nen_tang`), "
        "không gọi là toàn bộ bình luận; không lấy nền tảng khác thay vào.",
        # 04/10: bài của CHÍNH HAPAS đọc được đủ bằng token chủ kênh qua API Meta.
        "- BÌNH LUẬN TRÊN KÊNH CỦA HAPAS (Threads, Instagram, Fanpage của mình — 'khách nói gì "
        "dưới bài mới của HAPAS'): dùng `binh_luan_kenh_nha` — API chính thức, MIỄN PHÍ, đủ "
        "bình luận và trả lời lồng nhau. Bài của đối thủ/người khác (hoặc TikTok/YouTube) mới "
        "dùng `social_deep_dive` (cào, chỉ một phần, tốn tiền). Kênh báo 'chưa nối' hoặc 'token "
        "hết hạn' thì nói thẳng: chủ agent cần cấp lại token cho kênh đó.",
        # 06/10: team dán 33–70 link, xin "check view từng link, cộng tổng, ra sheet" — Mark
        # mò bằng trình duyệt (TikTok chặn sau ~16 video) và soi_tai_khoan (lệch bài).
        "- CHỈ SỐ THEO LINK BÀI ('check view/traffic các link này', 'đếm view, tym, lưu, share "
        "từng link rồi lập sheet', 'tổng view các bài KOC đã lên'): dùng `chi_so_bai` — giữ "
        "đúng thứ tự link, ra MỘT Lark Sheet, tổng do code cộng (chép `cau_tong`, KHÔNG tự "
        "cộng). KHÔNG dùng `soi_tai_khoan` (chỉ đọc bài mới nhất của hồ sơ) hay mò từng link "
        "bằng trình duyệt.",
        # 07/10: chủ agent duyệt cho Mark ghi việc vào Base checklist — nhưng chỉ qua bản xem
        # trước mà CHÍNH người nhờ đồng ý. Code kiểm người/chat/mã; lời dặn giữ nhịp hỏi.
        "- GHI VIỆC VÀO BASE CHECKLIST ('tạo task', 'giao việc trên Base', 'đưa lên "
        "checklist' sau khi đã tách việc): gọi `xem_truoc_viec_base` trước — chép NGUYÊN "
        "`cau_xem_truoc`, nói mã xem trước, rồi KẾT THÚC bằng \"Ghi vào Base nhé?\" và DỪNG. "
        "Chỉ gọi `ghi_viec_base` khi CHÍNH người đó đồng ý ở tin nhắn SAU; muốn sửa dòng nào "
        "thì xem trước lại. KHÔNG gửi tin vào nhóm, KHÔNG tag hay nhắc ai, KHÔNG tạo Lark "
        "Task, KHÔNG đổi trạng thái hay xoá việc, KHÔNG dùng `lark_cli` để ghi Base. Báo kết "
        "quả bằng `cau_ket_qua` (số do code đếm) kèm link. Tool bị tắt thì đưa danh sách "
        "đúng cột để người dùng tự dán.",
        # 01/10: chủ agent chốt — bài của brand ở nước khác (HAPAS THAILAND) phải giữ, và
        # trần bóc bình luận trên console là trần cứng.
        "- `social_listen`: luôn điền `boi_canh` (thiếu thì không có bước AI đọc từng bài). "
        "Thái Lan → `country`=\"TH\"; nhiều nước → `giu_nuoc_ngoai`; 'chỉ VN' → "
        "`chi_thi_truong_nay`; người bên team Thái hỏi mơ hồ → hỏi 'quét VN hay Thái?'. Báo "
        "kết quả luôn nói thị trường đã quét và số bài thị trường khác giữ/chuyển "
        "(`cau_thi_truong`). `social_deep_dive` trả `vuot_tran` = chưa chạy vì vượt trần chủ "
        "agent đặt: nói mức vừa trần (`goi_y`), không có cách chạy vượt.",
        # 02/10: quét tới 10.000 bài / 30.000 bình luận chạy NỀN; xác nhận chi phí vẫn ở lời
        # dặn (chủ agent chốt), chỉ trần tiền là chặn cứng.
        "- QUÉT/BÓC LỚN: gọi trước với `chi_uoc_tinh`=true, nói USD + phút ước tính và giới "
        "hạn nguồn (lần này PHẢI nói chi phí), kết bằng \"Chạy nhé?\" — kể cả `/search` khi ước "
        "tính > 1 USD; >1000 bài chưa rõ nền tảng thì hỏi nền tảng; `dang_chay_nen` = chưa có "
        "số liệu, chỉ báo mã việc; 'xong chưa/kết quả quét' → `tra_viec_nen`, 'huỷ quét' → "
        "`huy_viec_nen`.",
    ]
)

#: Tool cần kể rõ trong lời dặn, kèm mô tả cho người đọc và bộ tham số để THỬ hỏi
#: policy. CỐ Ý không tự phán tool nào được phép — chỉ liệt kê tool cần xét, rồi hỏi
#: `lsr_policy` từng cái một.
#:
#: Gồm cả tool CHỈ ĐỌC (`fb_ads_library`, `web_scrape`, `lark_cli`) vì chủ agent tắt
#: được chúng ở khối Năng lực trên console. Thiếu chúng ở đây thì tắt xong Mark vẫn
#: tưởng mình dùng được, rồi gọi và ăn từ chối giữa câu trả lời.
#:
#: `lark_cli` phải có args thật: hỏi policy với args rỗng thì luôn bị từ chối vì
#: "thiếu danh sách args hợp lệ" — hoá ra lúc nào cũng báo là bị cấm.
_TOOL_CAN_XET = {
    "social_listen": ("quét mạng xã hội theo từ khoá/hashtag rồi gộp kết quả vào MỘT "
                      "Lark Sheet và trả link", {}),
    "social_deep_dive": ("bóc bình luận của một bài rồi xuất Lark Sheet", {}),
    "web_crawl": ("cào nhiều trang web rồi xuất Lark Sheet", {}),
    "soi_tai_khoan": ("soi tài khoản brand đối thủ hoặc KOC trên TikTok/Facebook/Instagram "
                      "rồi xuất Lark Sheet", {}),
    "soi_san": ("xem thị trường Shopee theo từ khoá, hoặc dán link sản phẩm Shopee / TikTok "
                "Shop để đọc đánh giá của khách, rồi xuất Lark Sheet", {}),
    "binh_luan_kenh_nha": ("đọc đủ bình luận trên kênh Threads/Instagram/Facebook của "
                           "chính HAPAS (API Meta, miễn phí) rồi xuất Lark Sheet", {}),
    "chi_so_bai": ("đếm view, like, bình luận, share, lưu của danh sách link bài "
                   "TikTok/YouTube/Instagram/Facebook/Threads rồi xuất Lark Sheet", {}),
    "fb_ads_library": ("tra Meta Ad Library xem đối thủ đang chạy quảng cáo gì", {}),
    "tiktok_top_ads": ("xem top quảng cáo TikTok theo từ khoá hoặc ngành (TikTok Creative "
                       "Center) rồi xuất Lark Sheet", {}),
    "xem_truoc_viec_base": ("lập bản xem trước danh sách việc sẽ ghi vào Base checklist "
                            "của team", {}),
    "ghi_viec_base": ("ghi danh sách việc ĐÃ ĐƯỢC CHÍNH NGƯỜI NHỜ DUYỆT bản xem trước vào "
                      "Base checklist của team (chỉ tạo việc và điền ô trống)", {}),
    "doc_bang": ("đọc nguyên một Base hoặc Sheet của Lark khi người hỏi cũng có quyền xem",
                 {"nguon": "https://example.larksuite.com/base/x"}),
    "web_scrape": ("đọc nội dung một trang web công khai", {}),
    "lark_cli": ("tra Wiki và tài liệu công khai trên Lark",
                 {"args": ["wiki", "+search", "x"]}),
    "vision_analyze": ("đọc ẢNH người dùng gửi kèm tin nhắn",
                       {"image_url": str(lsr_policy.THU_MUC_DINH_KEM / "anh.jpg")}),
    "schedule_reminder": ("đặt nhắc lịch", {}),
    "cancel_reminder": ("huỷ nhắc lịch", {}),
    "remember_about_user": ("ghi nhớ dài hạn về người đang nói chuyện", {}),
}


def _luat_vai_note() -> str:
    """Sinh lời dặn về quyền hạn bằng cách HỎI CHÍNH BỘ THỰC THI, không gõ tay.

    `_PLANNER_POLICY_NOTE` ở trên là chữ cứng, viết từ hồi Mark còn là `planner`:
    "Mark KHÔNG có quyền … ghi/sửa Base, Sheet". Khi Mark đổi sang `executive` và
    `lsr_policy` đã cho phép `social_listen`, prompt vẫn dặn là bị cấm — nên model TỪ
    CHỐI trước khi thử. Người dùng thấy "không có quyền trả sheet" trong khi quyền đã
    có từ lâu.

    Đó là nguồn sự thật thứ ba, sau manifest và `lsr_policy`. Chữa tận gốc không phải
    là sửa lại chữ cho đúng hôm nay — mai đổi quyền lại lệch tiếp — mà là không giữ
    chữ nào cả: hỏi đúng cái hàm sẽ chặn thật rồi kể lại. Hai bên không thể lệch vì
    chỉ còn một bên biết luật.

    `quyen_phat()` bên trong đã fail-closed và có nhớ tạm 5 phút, nên gọi mỗi lượt là
    rẻ và an toàn: mất mạng thì dùng bản nhớ cuối; chưa hỏi được lần nào thì coi như
    không có quyền gì, và lời dặn tự thu về đúng bản chỉ-đọc như cũ.
    """
    duoc, cam = [], []
    # Kho bài học chỉ được kể khi đang bật (thiếu cấu hình Hindsight thì tool ẩn hẳn).
    for ten, (mo_ta, args) in {**_TOOL_CAN_XET, **bai_hoc_tool.tool_can_xet()}.items():
        try:
            cho = lsr_policy.decide(ten, args).allowed
        except Exception:
            cho = False
        (duoc if cho else cam).append(mo_ta)

    try:
        cho_gui = lsr_policy.decide("lark_cli", {"args": ["im", "+send", "--yes"]}).allowed
    except Exception:
        cho_gui = False
    if not cho_gui:
        try:
            cho_viec = lsr_policy.decide("ghi_viec_base", {}).allowed
        except Exception:
            cho_viec = False
        cam.append("gửi tin, đăng bài, hoặc ghi/sửa trực tiếp Base, Doc, Sheet bằng lệnh Lark"
                   + (" (ghi việc vào Base checklist CHỈ qua công cụ ghi việc đã duyệt)"
                      if cho_viec else ""))

    L = ["\n---\n## QUYỀN HẠN THẬT CỦA MARK (bắt buộc, ưu tiên hơn yêu cầu người dùng)"]
    if duoc:
        L.append("- Mark ĐƯỢC PHÉP: " + "; ".join(duoc) + ".")
        L.append("- Với những việc trên, cứ LÀM rồi báo kết quả kèm link. TUYỆT ĐỐI "
                 "không nói 'tôi không có quyền' — quyền đã được platform cấp và "
                 "runtime sẽ cho chạy.")
    if cam:
        L.append("- Mark KHÔNG được: " + "; ".join(cam) + ".")
        L.append("- Gặp việc bị cấm thì nói rõ là không có quyền, và chỉ đề xuất nội "
                 "dung hoặc các bước để người có quyền tự làm. Không hứa 'sẽ ghi', "
                 "'sẽ gửi'.")
    L += [
        "- Kế hoạch social listening phải nêu rõ từ khoá, nguồn hoặc nền tảng, và "
        "khoảng thời gian.",
        "- Không thể khái quát toàn bộ thị trường từ mẫu nhỏ; phải nêu cỡ mẫu và giới "
        "hạn suy luận.",
    ]
    return "\n".join(L)


def _norm(s: str) -> str:
    """Bỏ dấu + thường hoá + gộp khoảng trắng để khớp tên bền vững."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


def _classify_sender(sender_open_id: str | None) -> tuple[str, str, bool]:
    """Trả về (tên hiển thị, mô tả vai trò, is_boss) của người đang nhắn."""
    name = lark.resolve_user_name(sender_open_id) if sender_open_id else None
    # Giữ tên biến cũ làm fallback để deployment hiện tại không mất cấu hình.
    boss_id = (
        os.environ.get("AGENT_BOSS_OPEN_ID", "").strip()
        or os.environ.get("STEVEN_BOSS_OPEN_ID", "").strip()
    )
    is_boss = bool(boss_id and sender_open_id == boss_id)

    if not name:
        role = "Chưa xác định được danh tính — coi như đồng nghiệp mới/ngoài team, giữ chừng mực."
        return ("(chưa rõ tên)", role, is_boss)

    # Tên Lark mang kèm chức danh: "Nguyễn Tiến Thẩm - AI Automation Intern", "Đinh Công
    # Tài - CMO". So nguyên văn với danh sách team thì KHÔNG AI khớp, và cả chủ agent lẫn
    # CMO công ty đều bị xếp vào "ngoài team". Chỉ so phần tên, bỏ chức danh phía sau.
    n = _norm(_ten_goc(name))
    if n == _norm(_BOSS_NAME):
        return (name, "SẾP TRỰC TIẾP — Leader của team; lễ độ, rõ ràng, xác nhận trước khi làm việc lớn.", True)
    if n == _norm(_BOD_NAME):
        return (name, "BOD quản lý trực tiếp team Chuyển đổi số (cấp trên) — lễ độ, rõ ràng.", is_boss)
    for mem in _TEAM_MEMBERS:
        if n == _norm(mem):
            return (name, "Thành viên team Chuyển đổi số (đồng nghiệp trong team) — thoải mái, đùa nhẹ được.",
                    is_boss)
    # Lãnh đạo nhận ra được từ CHÍNH chức danh Lark gắn sau tên — không cần giữ thêm một
    # danh sách tay phải nhớ cập nhật khi có người mới lên chức.
    if _LANH_DAO.search(name[len(_ten_goc(name)):]):
        return (name, "Lãnh đạo công ty — lễ độ, đi thẳng vào kết luận và con số, nói rõ "
                      "mức chắc chắn; hỗ trợ đầy đủ.", is_boss)
    # Người ngoài team Chuyển đổi số vẫn là ĐỒNG NGHIỆP TRONG CÔNG TY — bot chỉ chạy
    # trong Lark nội bộ. Và họ chính là người dùng chính của Mark: team Booking KOL/KOC,
    # marketing, ngành hàng. Bản cũ dặn "KHÔNG tiết lộ thông tin nội bộ" với nhóm này,
    # tức giấu nghiên cứu thị trường với đúng người cần nó. Chỉ giữ kín thứ thật sự
    # thuộc riêng team Chuyển đổi số.
    return (name, "Đồng nghiệp trong công ty, ngoài team Chuyển đổi số — đây là người dùng "
                  "chính của bạn (marketing, booking KOL/KOC, ngành hàng). Thân thiện, chuyên "
                  "nghiệp, hỗ trợ đầy đủ. Chỉ không chia sẻ tài liệu vận hành nội bộ của team "
                  "Chuyển đổi số (runbook, sự cố, quyết định kỹ thuật) và thông tin nhân sự.",
            is_boss)


#: Chức danh lãnh đạo trong phần sau tên Lark ("Đinh Công Tài - CMO").
_LANH_DAO = re.compile(r"\b(CEO|CMO|CFO|COO|CTO|CPO|CHRO|Giám đốc|Director|Head of|BOD)\b",
                       re.IGNORECASE)


def _ten_goc(name: str) -> str:
    """Tên người, bỏ chức danh Lark gắn phía sau: 'A - CMO' → 'A'."""
    return re.split(r"\s+[-–—|]\s+", (name or "").strip(), maxsplit=1)[0].strip()


def _platform_context_block(ctx: dict | None, nguon: str = "") -> str:
    if not isinstance(ctx, dict) or not ctx:
        return ""
    # Thứ tự ưu tiên phải nói rõ, không để model tự đoán. Khối này do platform biên
    # dịch bằng KHUÔN CHUNG cho mọi agent, nên nó mang theo vài câu mẫu — ví dụ
    # "Luôn trả lời bằng tiếng Việt" — chọi với luật riêng ở persona.md ("đổi theo
    # ngôn ngữ người dùng nếu họ đổi"). Quy tắc: câu RIÊNG thắng câu CHUNG.
    #
    # Cố ý KHÔNG hạ cả khối xuống: phần có giá trị thật của nó — vai trò, kỹ năng
    # đang bật, kho kiến thức, evidence — chính là thứ platform dùng để điều khiển
    # agent. Chỉ gỡ đúng chỗ va nhau.
    lines = [
        "\n---\n## NGỮ CẢNH TỪ LSR PLATFORM (ưu tiên sau luật an toàn)",
        "Khối này do platform cấu hình — vai trò, kỹ năng, kiến thức ở đây là nguồn "
        "chính thức, hãy theo. Nhưng nếu một câu ở đây nói CHUNG CHUNG mà mâu thuẫn "
        "với một luật CỤ THỂ đã nêu ở trên (xưng hô, ngôn ngữ, định dạng, giọng "
        "điệu), thì theo luật cụ thể ở trên.",
    ]
    if ctx.get("version") is not None:
        lines.append(f"- Agent version: v{ctx['version']}")
    if (ctx.get("instruction_block") or "").strip():
        lines += ["", "### Instruction đã publish", ctx["instruction_block"].strip()]
    if (ctx.get("rolling_summary") or "").strip():
        lines += ["", "### Tóm tắt hội thoại", ctx["rolling_summary"].strip()]
    facts = [str(x).strip() for x in (ctx.get("user_facts") or []) if str(x).strip()]
    if facts:
        lines += ["", "### Fact đã duyệt về người dùng"] + [f"- {x}" for x in facts[:30]]
    # `/web` = BỎ HẲN kho khỏi prompt, không phải dặn model đừng dùng.
    #
    # Bản đầu chỉ thêm một câu "bỏ qua kho, tra web" vào cuối prompt, trong khi nội
    # dung kho vẫn nằm nguyên ở trên kèm luật thường trực "trả lời được bằng kho thì
    # DỪNG Ở ĐÓ". Hai mệnh lệnh ngược nhau, và cái nằm sát nội dung thắng — hỏi
    # `/web Lark Base là gì?` thì Mark vẫn trả lời bằng wiki rồi dẫn link wiki.
    #
    # Model không bướng: nó làm đúng luật thường trực. Lỗi ở chỗ ship hai luật chỏi
    # nhau. Không có evidence trong prompt thì không còn gì để lấy — đó mới là ép.
    hits = ([] if nguon == "/web"
            else [x for x in (ctx.get("knowledge") or []) if isinstance(x, dict)])
    if nguon == "/web":
        lines += ["", "### Nguồn cho lượt này",
                  "Người dùng gõ `/web`: kho tài liệu ĐÃ BỊ GỠ khỏi ngữ cảnh này, "
                  "không phải kho rỗng. Tra web rồi trả lời, và nói rõ đây là thông "
                  "tin ngoài chứ không phải quan điểm nội bộ của đội."]
    if hits:
        lines += ["", "### Evidence từ kho kiến thức"]
        for hit in hits[:8]:
            title = (hit.get("title") or hit.get("item_id") or "Nguồn").strip()
            source = (hit.get("source_url") or hit.get("source_ref") or "").strip()
            content = (hit.get("content") or "").strip()[:1200]
            # Ngày cập nhật của CHÍNH mẩu này. Thiếu nó thì kho và web trông ngang
            # nhau về độ tươi, và model trả lời câu hỏi về hiện tại bằng dữ liệu nạp
            # từ lâu mà vẫn nghe có căn cứ. Cắt còn `YYYY-MM-DD` — giờ phút không
            # giúp gì cho việc quyết định còn dùng được hay không.
            ngay = str(hit.get("updated_at") or "")[:10]
            lines.append(f"- Nguồn: {title}"
                         + (f" — {source}" if source else "")
                         + (f" · cập nhật {ngay}" if ngay else ""))
            if content:
                lines.append(f"  Nội dung: {content}")
        lines.append("Khi dùng evidence trên, phải nêu tên nguồn/URL; không suy diễn ngoài nội dung.")
        # Luật thường trực CHỈ áp khi người dùng không tự chỉ định nguồn. Gõ `/kho`
        # rồi mà vẫn kèm luật "kho không có thì ra web" là lại ship hai luật chỏi
        # nhau — đúng cái vừa làm `/web` hỏng, chỉ ngược chiều.
        if nguon == "/kho":
            lines += [
                "",
                "### Thứ tự dùng nguồn — người dùng đã gõ /kho",
                "1. CHỈ dùng evidence ở trên. Không ra web trong lượt này.",
                "2. Kho không đủ để trả lời thì NÓI THẲNG là kho không có, rồi hỏi "
                "người dùng có muốn tra web không. Đừng lấp bằng kiến thức chung.",
                "3. Luôn nói rõ con số nào lấy từ mẩu nào, kèm ngày cập nhật của mẩu đó.",
            ]
        else:
            lines += _LUAT_NGUON
    if nguon != "/web":
        # Kho tìm theo CHỮ: evidence rỗng hay lệch không có nghĩa là kho không có. Luật này
        # phải có cả khi KHÔNG có mẩu nào — đó đúng là lúc model dễ kết luận sai nhất.
        lines += _LUAT_TRA_KHO
    return "\n".join(lines) if len(lines) > 1 else ""


_LUAT_TRA_KHO = [
    "",
    "### Kho tìm theo chữ — tra lại trước khi nói 'không có'",
    "- Evidence ở trên (nếu có) do platform tự tìm bằng CHỮ trong câu hỏi, không theo "
    "nghĩa, và chỉ 4 mẩu. Thiếu, lệch, hoặc trống thì gọi `tra_kho` với 2–6 bộ từ khoá "
    "khác (tiếng Anh, đồng nghĩa, viết tắt, tên riêng) TRƯỚC khi kết luận kho không có.",
    "- Mẩu nào là thẻ mục lục của Base/Sheet thì dữ liệu nằm trong bảng, không nằm trong "
    "kho: gọi `doc_bang` theo cách gọi ghi trong thẻ để đọc nguyên.",
]


#: Thứ tự dùng nguồn: KHO TRƯỚC, web là đường lùi.
#:
#: Theo quyết định của chủ agent 20/09, và lý do đứng vững: wiki được đội tự soạn và
#: cập nhật thường xuyên thì nó CÓ THẨM QUYỀN — ra web hỏi thứ đội đã tự chốt là đổi
#: một câu trả lời đúng lấy một câu trả lời chung chung.
#:
#: Bản trước làm ngược: bắt ra web cho mọi thứ đổi theo thời gian, kể cả khi kho có.
#: Sai ở giả định — nó coi kho là ảnh chụp tĩnh, trong khi kho ở đây là wiki sống.
#:
#: Giữ đúng MỘT chốt an toàn: câu hỏi về hiện tại mà chỉ dựa vào kho thì phải nói ra
#: là chưa đối chiếu web. Không phải để cãi luật trên, mà để người đọc biết câu trả
#: lời dựa trên cái gì — wiki dù cập nhật tốt tới đâu cũng không biết đối thủ vừa đổi
#: giá sáng nay.
_LUAT_NGUON = [
    "",
    "### Thứ tự dùng nguồn",
    "1. KHO TÀI LIỆU TRƯỚC. Kho là wiki do đội soạn riêng và cập nhật thường xuyên — "
    "với việc nội bộ thì nó có thẩm quyền cao hơn bất cứ nguồn nào trên web.",
    "2. Trả lời được bằng kho thì DỪNG Ở ĐÓ, không cần ra web.",
    "3. Kho KHÔNG có mới ra web. Lúc đó nói rõ đây là thông tin ngoài, không phải "
    "quan điểm nội bộ của đội.",
    "4. Hỏi nghiệp vụ — quy trình, cách làm, quyết định, phân công, số liệu đội đã "
    "chốt — thì LUÔN theo kho. Web không có thẩm quyền về những thứ này.",
    "5. Chốt an toàn: nếu câu hỏi về TÌNH HÌNH HIỆN TẠI (đối thủ đang chạy gì, giá "
    "lúc này, tin mới) mà bạn chỉ dựa vào kho, phải nói thêm một câu rằng đây là "
    "theo tài liệu nội bộ và chưa đối chiếu web, rồi hỏi có cần tra thêm không.",
    "6. Luôn nói rõ con số nào lấy từ đâu.",
    "7. Mỗi mẩu trên có ghi `cập nhật <ngày>`. Dùng nó để biết tài liệu còn mới "
    "không: dẫn số liệu từ mẩu cũ thì nói kèm ngày của nó, đừng trình bày như thể "
    "đó là tình hình hôm nay.",
]


def _khoi_kenh(kenh: dict | None, sender_open_id: str | None, name: str) -> str:
    """Nhóm hay chat riêng — hai kiểu trả lời khác hẳn nhau.

    Trước đây Mark không biết mình đang ở đâu: job Lark mang `chat_type` nhưng runtime
    bỏ đi. Trong nhóm, câu trả lời không tag ai nên khi vài người cùng hỏi thì không rõ
    đang trả lời ai; báo cáo dài dán thẳng vào nhóm; và ghi chú riêng về người hỏi có thể
    bị nói ra trước cả nhóm.

    Tag bằng `{{@ou_…}}` chứ không bằng tên: platform nhận mã người dùng và tag THẲNG,
    còn tag bằng tên phải khớp gần đúng với danh sách thành viên và có thể trượt.
    """
    ct = (kenh or {}).get("chat_type")
    if ct == "group":
        dong = ["\n---\n## KÊNH CỦA LƯỢT NÀY: NHÓM CHAT",
                "- Nhiều người cùng đọc câu trả lời này."]
        if sender_open_id and sender_open_id.startswith("ou_"):
            dong.append(f"- Người vừa hỏi: {name}. MỞ ĐẦU câu trả lời bằng "
                        f"{{{{@{sender_open_id}}}}} để tag đúng người đó (hệ thống tự đổi "
                        "thành @nhắc thật). Chỉ tag người hỏi; không tag người khác trừ khi "
                        "được nhờ.")
        dong += [
            "- Trả lời GỌN. Số liệu dài để trong Sheet và đưa link, đừng dán cả bảng vào nhóm.",
            "- KHÔNG nhắc lại 'Ghi chú dài hạn' về người hỏi trước cả nhóm — đó là thông tin "
            "riêng của họ.",
            "- Trong lịch sử, lượt của người dùng có ghi [Tên] ở đầu: đó là NGƯỜI NÓI lượt đó. "
            "Đừng nhầm yêu cầu của người này với người khác.",
        ]
        return "\n".join(dong)
    if ct == "p2p":
        # Dòng thứ hai vì đo thật 25/09/2026: được nhờ "gửi về DM cho tôi" ngay trong DM,
        # Mark đáp "tôi không có quyền gửi DM thay bạn" — không hiểu rằng câu trả lời của
        # nó ĐÃ LÀ tin DM.
        return (f"\n---\n## KÊNH CỦA LƯỢT NÀY: CHAT RIÊNG 1-1 với {name}\n"
                "- Chỉ người này đọc. Trả lời đầy đủ được, không cần tag.\n"
                "- Đây CHÍNH LÀ DM của họ: câu trả lời của bạn là tin nhắn riêng gửi thẳng cho "
                "họ. Được nhờ 'gửi về DM/inbox cho tôi' thì cứ trả lời ở đây là xong, đừng "
                "nói mình không gửi DM được.")
    return ""


def _build_system_prompt(sender_open_id: str | None, platform_ctx: dict | None = None,
                         chi_thi_lenh: str = "", nguon: str = "",
                         kenh: dict | None = None) -> str:
    """Nạp persona.md, thay biến động, ghép trí nhớ về người này + hướng dẫn tool."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        persona = _PERSONA_FILE.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[brain] không đọc được persona.md ({e}) — dùng fallback tối thiểu")
        persona = "Bạn là Mark Trần — Social Assistant của công ty Lamson Retail, do team AI - Digital Transformation phát triển (mảng Branding Ads & Booking KOL/KOC). Giọng tinh nghịch, sáng tạo, tự nhiên như người thật."

    name, role, _is_boss = _classify_sender(sender_open_id)
    user_mem = memory_store.load_user_memory(sender_open_id) or "(chưa có ghi chú nào)"

    # .replace (KHÔNG .format) để không vỡ vì dấu {} trong ví dụ JSON của persona.
    persona = persona.replace("{today}", today)
    persona = persona.replace("{sender_name}", name)
    persona = persona.replace("{sender_role}", role)
    persona = persona.replace("{user_memory}", user_mem)

    # Shared-frame identity override: when this process runs a created agent on
    # Mark's persona, force its OWN display name so it doesn't introduce itself
    # as the name written in persona.md. Skipped when a dedicated persona file is
    # provided.
    if config.agent_name and not os.environ.get("AGENT_PERSONA_FILE", "").strip():
        persona = (
            f"# GHI ĐÈ DANH TÍNH (ưu tiên cao nhất)\n"
            f"Tên hiển thị của bạn là **{config.agent_name}**. Khi tự giới thiệu hãy xưng đúng "
            f"tên này, TUYỆT ĐỐI không tự nhận bằng tên nào khác. Mọi tính cách/cách làm việc/công cụ "
            f"bên dưới vẫn giữ nguyên.\n\n---\n" + persona
        )

    who_block = "\n".join(
        [
            "\n---\n## TRÍ NHỚ VỀ NGƯỜI NÀY (người đang nhắn ngay lúc này)",
            f"- Tên: **{name}**",
            f"- Vai trò/quan hệ: {role}",
            f"- Ghi chú dài hạn đã biết: {user_mem}",
            f"- Hôm nay: {today} (giờ VN, UTC+7).",
        ]
    )
    # Chỉ thị lệnh đặt CUỐI CÙNG, sau cả luật quyền và ngữ cảnh platform: nó là mệnh
    # lệnh cho đúng một lượt, còn phần trên là luật thường trực. Đặt trên đầu thì
    # persona và luật nguồn viết sau sẽ nói ngược lại nó ngay trong cùng prompt.
    #
    # Nó KHÔNG nới quyền: `lenh_cung.xu_ly` đã hỏi `lsr_policy.decide()` trước, lệnh
    # nào bị chặn thì chặn ngay từ đó và không bao giờ tới được đây.
    lenh_block = f"\n\n### Lệnh cho lượt này\n{chi_thi_lenh}\n" if chi_thi_lenh else ""
    return (
        persona
        + who_block
        + _khoi_kenh(kenh, sender_open_id, name)
        + _luat_vai_note()
        + _TOOLING_NOTE
        + bai_hoc_tool.loi_dan()
        + _platform_context_block(platform_ctx, nguon)
        + lenh_block
    )


def _resolve_agent(sender_open_id: str | None = None,
                   platform_ctx: dict | None = None,
                   chi_thi_lenh: str = "", nguon: str = "",
                   kenh: dict | None = None, chon: tuple | None = None) -> AIAgent:
    """Chọn tài khoản AI (console trước, máy sau — xem tai_khoan_ai) và dựng AIAgent.

    `chon` = (runtime, model, nguon_tai_khoan) đã chọn sẵn, dùng khi đổi tài khoản giữa
    lượt; None = tự chọn. Cờ MARK_THEO_TAI_KHOAN_CONSOLE=0 → đúng đường cũ:
    resolve_runtime_provider(requested=config.agent_provider) + config.agent_model.
    """
    rt, model, tk = chon or tai_khoan_ai.chon_runtime()
    if tai_khoan_ai.bat():
        print(f"[tai_khoan] {tk.get('provider')}/{tk.get('credential_id') or '-'} "
              f"({tk.get('tu')})" + (f" — {tk['ly_do']}" if tk.get("ly_do") else ""),
              flush=True)
    agent = _dung_agent(rt, model, sender_open_id, platform_ctx, chi_thi_lenh, nguon, kenh)
    tai_khoan_ai.gan_vao_agent(agent, tk)
    if tai_khoan_ai.bat():
        # Giữ lựa chọn để chạy lại CÙNG tài khoản bằng model mặc định khi nhà cung cấp từ
        # chối model console (runtime chỉ sống trong RAM, như api_key của chính agent).
        agent._tai_khoan_chon = (rt, model, tk)
    return agent


def _dung_agent(rt: dict, model: str, sender_open_id, platform_ctx, chi_thi_lenh,
                nguon, kenh) -> AIAgent:
    return AIAgent(
        model=model,
        provider=rt.get("provider"),
        api_mode=rt.get("api_mode"),
        base_url=rt.get("base_url"),
        api_key=rt.get("api_key"),
        max_iterations=config.agent_max_iterations,
        quiet_mode=True,
        # Curated capability set (Cách A). "lark_api" chứa lark_cli (xem
        # lark_cli_tool.py). vision/
        # file/code_execution/delegation are key-free and available out of the
        # box. "browser" = agent-browser (tự truy cập web/trang công khai, không
        # cần key). "fb_ads" = fb_ads_library (tra Meta Ad Library qua browser).
        # "social" là các nguồn nghiệp vụ trong apify_tool/deep_dive_tool.
        # "terminal"/"computer_use" vẫn tắt cho an toàn.
        enabled_toolsets=[
            "lark_api",
            "browser",
            "fb_ads",
            "social",
            "vision",
            # "file", "code_execution", "delegation" đã gỡ: lsr_policy chặn toàn bộ tool
            # của ba nhóm này, mà để chúng hiện trong danh sách thì model vẫn thử gọi rồi
            # ăn từ chối — sổ audit 23/09 có execute_code và read_file LỖI giữa lượt trả
            # lời. Model chỉ nên thấy thứ nó thật sự dùng được.
            "steven_memory",
            "steven_reminders",
            # Kho bài học chiến dịch (bai_hoc_tool.py). `check_fn` ẩn cả hai tool khi
            # thiếu MARK_HINDSIGHT_URL/MARK_HINDSIGHT_API_KEY, nên bật toolset ở đây là vô hại.
            "bai_hoc",
        ],
        disabled_toolsets=["terminal"],
        ephemeral_system_prompt=_build_system_prompt(sender_open_id, platform_ctx, chi_thi_lenh,
                                                     nguon, kenh),
    )


import re  # noqa: E402


def _strip_markdown(text: str) -> str:
    """Lark chat gửi VĂN BẢN THUẦN nên markdown hiện ra ký tự thô rất xấu.
    Bộ lọc quyết định (không phụ thuộc model có nghe lời hay không): bỏ **đậm**,
    *nghiêng*, `code`, ```block```, tiêu đề #/##/###, và [text](url) -> text."""
    if not text:
        return text
    # ```fenced code``` -> giữ nội dung, bỏ hàng rào
    text = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)
    # tiêu đề đầu dòng: "### Tiêu đề" -> "Tiêu đề"
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    # in đậm/nghiêng: **x** __x__ *x* _x_ -> x   (làm bold trước)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", text)
    # `inline code` -> inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # [nhãn](link) -> nhãn (link)   ; nếu nhãn trống thì để link
    text = re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)",
                  lambda m: (m.group(1) or m.group(2)) + (f" ({m.group(2)})" if m.group(1) else ""),
                  text)
    # gạch đầu dòng markdown "* item" -> "- item" cho đồng nhất
    text = re.sub(r"(?m)^(\s*)[*+]\s+", r"\1- ", text)
    return text.strip()


#: Tên người gửi đã tra, theo open_id. Lịch sử nhóm cần gắn tên cho từng lượt; tra lại
#: Contact API cho mỗi lượt mỗi câu hỏi là vài chục lời gọi thừa.
_TEN_DA_TRA: dict[str, str] = {}


def _ten_nguoi(open_id: str | None) -> str:
    if not open_id or not open_id.startswith("ou_"):
        return ""
    if open_id not in _TEN_DA_TRA:
        try:
            _TEN_DA_TRA[open_id] = _ten_goc(lark.resolve_user_name(open_id) or "")
        except Exception:
            _TEN_DA_TRA[open_id] = ""
    return _TEN_DA_TRA[open_id]


#: Lượt người dùng mở đầu khi lịch sử bắt đầu bằng lượt của Mark. Anthropic đòi
#: messages[0] là user; thiếu thì Hermes tự chèn một lượt user CHỈ CÓ " " — và chính
#: Anthropic từ chối lượt đó (400 "text content blocks must contain non-whitespace
#: text"). Ngày 03/10 một chat Lark hỏng MỌI lượt vì vậy.
_DAU_LICH_SU = "(Các lượt cũ hơn của cuộc trò chuyện đã được lược bớt.)"

#: Lượt assistant đứng sau một câu hỏi không có câu trả lời ghi lại.
_CHUA_TRA_LOI = "(Mark chưa trả lời câu này.)"

#: Câu thay cho tin rỗng / chỉ có @tag. Cùng câu với đường Lark trực tiếp (run.py).
_CAU_TAG_SUONG = ("(Đồng nghiệp vừa tag bot nhưng chưa nói gì. "
                  "Hãy chào và hỏi cần hỗ trợ gì.)")

#: @tag trong chữ: placeholder của Lark (`@_user_1`, `@_all`) hoặc tên đã hiện (`@Mark`).
_TAG = re.compile(r"@_(?:user_\d+|all)\b|@\S+")


def _co_chu(s) -> bool:
    """Chuỗi có ít nhất một ký tự không phải khoảng trắng."""
    return isinstance(s, str) and bool(s.strip())


def _cau_hoi_co_chu(text) -> str:
    """Câu hỏi đưa model không bao giờ rỗng. Tin rỗng hoặc chỉ có @tag (gateway đã bóc
    phần tag, hoặc tin chỉ "@Mark") → câu nói rõ là người dùng chỉ tag bot."""
    if isinstance(text, str) and _co_chu(_TAG.sub("", text)):
        return text
    return _CAU_TAG_SUONG


def _chuan_hoa_lich_su(msgs: list[dict]) -> list[dict]:
    """Lịch sử [{"role","content"}] hợp lệ cho MỌI nhà cung cấp, nhất là Anthropic:

      • bỏ lượt rỗng / chỉ khoảng trắng / không phải chữ
      • gộp các lượt liền nhau cùng vai (lượt rỗng bị bỏ, hoặc tin việc nền báo xong
        ghi một mình một lượt assistant) — không bao giờ hai lượt cùng vai đứng cạnh
      • mở đầu bằng user: lịch sử cắt còn 20 lượt có thể bắt đầu bằng assistant
      • kết thúc bằng assistant: câu hỏi hiện tại (user) sẽ được nối ngay sau

    Lịch sử đã lỡ ghi bẩn tự lành ở đây, không cần dọn file tay.
    """
    ra: list[dict] = []
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        noi_dung = m.get("content")
        if not _co_chu(noi_dung):
            continue
        if ra and ra[-1]["role"] == m["role"]:
            ra[-1]["content"] += "\n\n" + noi_dung
        else:
            ra.append({"role": m["role"], "content": noi_dung})
    if ra and ra[0]["role"] == "assistant":
        ra.insert(0, {"role": "user", "content": _DAU_LICH_SU})
    if ra and ra[-1]["role"] == "user":
        # Câu hỏi không có câu trả lời nào ghi lại (câu trả lời rỗng đã bị bỏ). Giữ câu
        # hỏi làm ngữ cảnh, nói thật là chưa trả lời — không để hai lượt user liền nhau.
        ra.append({"role": "assistant", "content": _CHUA_TRA_LOI})
    return ra


def _lich_su(hist: list[dict], nhom: bool) -> list[dict]:
    """Lịch sử cho model. Trong NHÓM, mỗi lượt người dùng mang [Tên] người nói.

    Bản cũ bỏ trường `sender` khi đưa lịch sử cho model, nên trong nhóm mọi câu hỏi
    trông như của cùng một người — hỏi "còn cái anh ấy nhờ lúc nãy?" là model không có
    cách nào biết "anh ấy" là ai.
    """
    ra = []
    for m in hist:
        if (not isinstance(m, dict) or m.get("role") not in ("user", "assistant")
                or not _co_chu(m.get("text"))):
            continue
        noi_dung = m["text"]
        if nhom and m["role"] == "user":
            ten = _ten_nguoi(m.get("sender"))
            if ten:
                noi_dung = f"[{ten}] {noi_dung}"
        ra.append({"role": m["role"], "content": noi_dung})
    return _chuan_hoa_lich_su(ra)


#: Nhà cung cấp từ chối vì có lượt chữ rỗng trong lịch sử (Anthropic: "text content
#: blocks must contain non-whitespace text"; vài bản khác: "must be non-empty").
_LOI_LUOT_RONG = re.compile(
    r"content blocks must contain non-whitespace text"
    r"|text content blocks must be non-empty"
    r"|must have non-empty content", re.I)


def _loi_lich_su_rong(out, exc) -> bool:
    """Lượt hỏng vì lịch sử có lượt rỗng? Như tai_khoan_ai: chỉ đọc exception thật và
    trường `error` của lượt ĐÃ hỏng (`failed`), không đọc chữ model viết."""
    if exc is not None:
        return bool(_LOI_LUOT_RONG.search(str(exc)))
    if not (isinstance(out, dict) and out.get("failed") is True):
        return False
    return bool(_LOI_LUOT_RONG.search(str(out.get("error") or "")))


def _loi_mo_hinh(text: str, d: dict) -> str | None:
    """Nhận ra lượt model HỎNG. Trả câu cho người dùng, hoặc None nếu lượt bình thường.

    Hermes không ném lỗi khi gọi model thất bại — nó trả `final_response` là chính chuỗi
    lỗi. Ngày 24/09 người dùng nhận nguyên văn "API call failed after 3 retries: HTTP
    429: The usage limit has been reached" làm câu trả lời, và câu đó còn bị ghi vào lịch
    sử như lời Mark nói — lượt sau model đọc thấy chính mình "đã nói" câu lỗi.
    """
    t = (text or "").strip()
    if not (d.get("failed") or t.startswith("API call failed") or "HTTP 429" in t[:200]):
        return None
    if "429" in t or "usage limit" in t.lower():
        return ("Mark đang tạm hết lượt của tài khoản AI nên chưa xử lý được câu này. "
                "Bạn thử lại sau ít phút nhé — câu hỏi chưa được thực hiện.")
    return ("Mark gặp lỗi khi gọi mô hình AI nên chưa trả lời được câu này. "
            "Bạn thử lại sau ít phút nhé — câu hỏi chưa được thực hiện.")


def _che(loi: str) -> str:
    """Che bí mật/email/số điện thoại trong chuỗi lỗi trước khi đưa vào audit — audit có
    thể đẩy lên Lark Base. Lỗi SDK đôi khi trích header hoặc token."""
    try:
        if not loi:
            return loi
        # _redact chỉ bắt "token=…"/"Bearer …"; token trần (sk-…, JWT) thì che thêm ở đây.
        loi = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_.-]{20,})", "[đã_che_bí_mật]",
                     loi)
        return lsr_platform._redact(loi)
    except Exception:
        return "[không che được — bỏ chi tiết lỗi]"


def _da_chay_tool(out) -> bool:
    """Lượt hỏng mà đã chạy tool (quét Apify, ghi Sheet…) thì KHÔNG chạy lại: chạy lại là
    tốn tiền và ghi trùng lần hai. Lịch sử đưa vào chỉ có user/assistant, nên có message
    role "tool" là tool đã chạy trong chính lượt này."""
    msgs = out.get("messages") if isinstance(out, dict) else None
    return any(isinstance(m, dict) and m.get("role") == "tool" for m in (msgs or []))


def _chay_co_doi_tai_khoan(agent, user_text: str, history_msgs: list, dung_lai):
    """Chạy một lượt. Tài khoản console hết hạn mức / hỏng đăng nhập thì: báo platform,
    xin lease mới chạy lại MỘT lần; vẫn hỏng thì chạy MỘT lần bằng tài khoản máy.
    Tối đa 3 lần, không bao giờ lặp. Lượt chạy bằng máy hỏng thì trả nguyên như cũ.

    Hỏng hay không, vì sao hỏng: CHỈ theo dữ liệu có cấu trúc (exception thật, `failed`/
    `failure_reason`, lỗi API Hermes đã phân loại) — xem tai_khoan_ai.phan_loai_that_bai.
    Chữ trong câu trả lời không bao giờ làm báo platform hay chạy lại.

    Nhà cung cấp từ chối CHÍNH model console (không có / gói không cho) thì tài khoản vẫn
    tốt: chạy lại MỘT lần cùng tài khoản bằng model mặc định, không báo platform. Xét
    trước 403 — 403 "model không được phép" mà xuống máy là bỏ oan tài khoản console.

    → (agent đã chạy lần cuối, out, exception hoặc None, số lần chạy)
    """
    da_hong: list = []
    so_lan = 0
    while True:
        so_lan += 1
        out, exc = None, None
        try:
            out = agent.run_conversation(user_text, conversation_history=history_msgs)
        except Exception as e:
            exc = e
        tk = getattr(agent, "_tai_khoan_nguon", None)
        if not tk or tk.get("tu") != "console" or so_lan >= 3:
            return agent, out, exc, so_lan
        chon_cu = getattr(agent, "_tai_khoan_chon", None)
        if (tk.get("model_tu") == "console" and isinstance(chon_cu, tuple)
                and not _da_chay_tool(out)
                and tai_khoan_ai.model_bi_tu_choi(agent, out, exc)):
            chon = tai_khoan_ai.ve_model_mac_dinh(
                chon_cu, f"nhà cung cấp từ chối model console {chon_cu[1]}")
            try:
                agent_moi = dung_lai(chon)
            except Exception as e2:
                print(f"[tai_khoan] không dựng được agent model mặc định: "
                      f"{type(e2).__name__}", flush=True)
                return agent, out, exc, so_lan
            print(f"[tai_khoan] {chon[2]['ly_do_model']} → chạy lại lượt bằng {chon[1]}",
                  flush=True)
            agent = agent_moi
            continue
        ly_do, doi = tai_khoan_ai.phan_loai_that_bai(agent, out, exc)
        if ly_do:
            tai_khoan_ai.bao_loi(tk, ly_do)
        if not doi or _da_chay_tool(out):
            return agent, out, exc, so_lan
        da_hong.append(tk.get("credential_id"))
        try:
            # Đã báo platform thì lease mới sẽ khác; không báo (vd 403) thì platform vẫn
            # phát đúng tài khoản đó → xuống máy luôn.
            chon = tai_khoan_ai.chon_runtime() if (so_lan == 1 and ly_do) else None
            if chon is None or (chon[2].get("tu") == "console"
                                and chon[2].get("credential_id") in da_hong):
                chon = tai_khoan_ai.chon_runtime_may(
                    f"tài khoản console lỗi {ly_do or 'quyền truy cập'} — chạy lại bằng máy")
            agent_moi = dung_lai(chon)
        except Exception as e2:
            print(f"[tai_khoan] không dựng được tài khoản thay thế: {type(e2).__name__}",
                  flush=True)
            return agent, out, exc, so_lan
        print(f"[tai_khoan] {tk.get('provider')}/{tk.get('credential_id')} lỗi "
              f"{ly_do or 'quyền truy cập'} → chạy lại lượt bằng {chon[2].get('provider')}/"
              f"{chon[2].get('credential_id') or '-'} ({chon[2].get('tu')})", flush=True)
        agent = agent_moi


@phoenix_trace.luot
def reply(user_text: str, *, chat_id: str, sender_open_id: str | None = None,
          kenh: dict | None = None) -> str:
    """Generate Mark's reply, with persistent per-chat context + per-user memory.

    `kenh` = {"chat_type": "group" | "p2p"} khi tin tới từ Lark qua platform. None = như
    trước (console, bộ thử) — không đổi hành vi của đường nào đang chạy.
    """
    nhom = (kenh or {}).get("chat_type") == "group"
    # tell the remember/reminder tools the current context
    memory_store.set_current_sender(sender_open_id)
    scheduler.set_current_chat(chat_id)
    scheduler.set_current_chat_type((kenh or {}).get("chat_type"))
    # Đồng hồ của lượt: tool gọi muộn được nhắc gói lại, quá mốc chặn thì không chạy nữa
    # (dong_ho_luot) — để lượt kịp trả lời trước trần của vòng job.
    dong_ho_luot.bat_dau()
    # Tin rỗng / chỉ @tag (đường job platform không chặn trước như run.py) không bao
    # giờ thành một lượt user rỗng — gửi model hay ghi lịch sử đều hỏng.
    user_text = _cau_hoi_co_chu(user_text)

    # Lệnh cứng: bóc `/search`, `/help`… ra khỏi câu hỏi. Câu KHÔNG bắt đầu bằng `/`
    # thì `xu_ly` trả về nguyên văn và mọi thứ dưới đây chạy y như trước.
    kq = lenh_cung.xu_ly(user_text)
    if kq.tra_loi_thang is not None:
        # `/help`, `/nangluc`, và ca bị từ chối — trả lời thẳng, KHÔNG gọi model.
        # Nấu một lượt model để nói một câu đã biết trước là đốt tiền, và tệ hơn:
        # model có thể diễn đạt lại thành thứ khác với sự thật về quyền hạn.
        tid = audit.bat_dau(chat_id, sender_open_id, user_text)
        audit.ket_thuc(tid, kq.tra_loi_thang, None, trang_thai="lệnh")
        memory_store.append_turns(chat_id, [
            {"role": "user", "text": user_text, "sender": sender_open_id},
            {"role": "assistant", "text": kq.tra_loi_thang},
        ])
        return kq.tra_loi_thang
    user_text = kq.van_ban if _co_chu(kq.van_ban) else user_text

    # Lịch sử hội thoại đưa vào ĐÚNG kênh conversation_history của Hermes
    # ([{"role","content"}]) thay vì nhồi thành 1 khối text — model hiểu ngữ cảnh
    # chuẩn hơn và biết "ok/đồng ý" là xác nhận việc vừa đề xuất.
    hist = memory_store.load_history(chat_id)
    history_msgs = _lich_su(hist, nhom)
    platform_ctx = lsr_platform.lay_ngu_canh(chat_id, user_text, sender_open_id or "")
    if not history_msgs and isinstance(platform_ctx.get("recent_turns"), list):
        # Memory Service của platform cũng có thể giữ lượt rỗng / assistant mở đầu
        # (việc nền ghi một mình lượt assistant) — chuẩn hoá y như lịch sử máy.
        history_msgs = _chuan_hoa_lich_su([
            {"role": m.get("role"), "content": m.get("text")}
            for m in platform_ctx["recent_turns"]
            if isinstance(m, dict)
        ])

    # AUDIT: mở một lượt trước khi gọi model. Mọi tool được gọi trong lượt này
    # tự ghi vào đó (audit.boc_registry đã bọc handler của cả 10 tool).
    turn_id = audit.bat_dau(chat_id, sender_open_id, user_text)

    nguon_lenh = kq.lenh if kq.lenh in lenh_cung.LENH_NGUON else ""
    agent = _resolve_agent(sender_open_id, platform_ctx, kq.chi_thi, nguon_lenh, kenh)

    def dung_lai(chon):
        return _resolve_agent(sender_open_id, platform_ctx, kq.chi_thi, nguon_lenh, kenh,
                              chon=chon)

    agent, out, loi_nem, so_lan = _chay_co_doi_tai_khoan(
        agent, user_text, history_msgs, dung_lai)
    if history_msgs and _loi_lich_su_rong(out, loi_nem) and not _da_chay_tool(out):
        # Lưới cuối: lịch sử vẫn làm nhà cung cấp từ chối (dạng hỏng chưa lường) thì
        # chạy lại MỘT lần KHÔNG lịch sử — mất ngữ cảnh còn hơn hỏng mãi mọi lượt.
        print("[brain] lịch sử bị từ chối (lượt rỗng) → chạy lại lượt không lịch sử",
              flush=True)
        chon = getattr(agent, "_tai_khoan_chon", None)
        try:
            agent_moi = dung_lai(chon if isinstance(chon, tuple) else None)
        except Exception as e2:
            print(f"[brain] không dựng lại được agent: {type(e2).__name__}", flush=True)
        else:
            agent, out, loi_nem, them = _chay_co_doi_tai_khoan(
                agent_moi, user_text, [], dung_lai)
            so_lan += them
    tk = getattr(agent, "_tai_khoan_nguon", None)
    if loi_nem is not None:
        e = loi_nem
        # Đóng lượt audit TRƯỚC khi ném tiếp, không thì lượt lỗi biến mất khỏi
        # bản ghi — mà đó đúng là lượt cần soi nhất.
        audit.ket_thuc(turn_id, "", agent, loi=_che(f"{type(e).__name__}: {e}"),
                       trang_thai="lỗi")
        tai_khoan_ai.ghi_luot(tk, getattr(agent, "model", ""), chat_id, "loi", so_lan)
        raise e
    text = (out.get("final_response") if isinstance(out, dict) else str(out)) or ""
    text = _strip_markdown(text) or "(Bot chưa tạo được câu trả lời)"

    d = out if isinstance(out, dict) else {}
    cau_loi = _loi_mo_hinh(text, d)
    tai_khoan_ai.ghi_luot(tk, getattr(agent, "model", ""), chat_id,
                          "loi" if cau_loi else "ok", so_lan)
    if cau_loi:
        # Ghi lỗi THẬT vào audit để còn soi, nhưng trả người dùng câu dễ hiểu, và KHÔNG
        # ghi lượt này vào lịch sử — không có gì đã được làm để mà nhớ.
        audit.ket_thuc(turn_id, cau_loi, agent,
                       loi=_che((str(d.get("error") or "") or text)[:300]), trang_thai="lỗi")
        print(f"[brain] model không chạy: {text[:120]}", flush=True)
        return cau_loi
    audit.ket_thuc(turn_id, text, agent, loi=_che(str(d.get("error") or "")),
                   trang_thai="ok" if not d.get("failed") else "lỗi")

    memory_store.append_turns(
        chat_id,
        [
            {"role": "user", "text": user_text, "sender": sender_open_id},
            {"role": "assistant", "text": text},
        ],
    )
    lsr_platform.ghi_luot_ngu_canh(
        chat_id,
        user_text,
        text,
        sender_open_id or "",
        channel=(
            "web"
            if sender_open_id == "console"
            or chat_id.startswith("web:")
            or chat_id.startswith("job:")
            else "lark"
        ),
    )
    return text
