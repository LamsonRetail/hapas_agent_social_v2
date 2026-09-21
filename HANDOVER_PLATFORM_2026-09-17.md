# Mark Trần — bàn giao kỹ thuật Platform

> Cập nhật: **17/09/2026**
>
> Phạm vi: migration Mark Trần (social-listening external agent) lên LSR Agent Platform.
> Tài liệu legacy vẫn nằm ở [`HANDOVER.md`](HANDOVER.md); nếu có khác biệt về trạng thái migration,
> lấy tài liệu này làm nguồn mới hơn.

## 1. Đọc nhanh trước khi làm tiếp

Hiện có ba danh tính độc lập:

| Vai trò | Agent ID | Trạng thái cần giữ |
| --- | --- | --- |
| Mark chính trên Platform | `AG-SOCIAL-LISTENING` | Active, chỉ publish `dev` v5; `stg/prod` để trống |
| Agent kiểm thử | `AG-SOCIAL-LISTENING-TEST` | Active, `dev` v3; worker local đang phục vụ web chat |
| Bản sao dự phòng | `AG-MARK-TRAN-BACKUP` | **Deactivated**, `dev` v4; cold standby, không tự kích hoạt |

Các URL quản trị:

- Mark chính: <https://app.34-124-212-76.sslip.io/agent/AG-SOCIAL-LISTENING>
- TEST: <https://app.34-124-212-76.sslip.io/agent/AG-SOCIAL-LISTENING-TEST>
- Backup: <https://app.34-124-212-76.sslip.io/agent/AG-MARK-TRAN-BACKUP>
- Golden cases: <https://app.34-124-212-76.sslip.io/golden>

Điểm quan trọng nhất:

1. Bot Lark production legacy vẫn vận hành theo đường `listener.py` → `run.py` → `brain.py`.
1. Platform chưa thay thế đường production đó. Mark chính trên Platform chưa có version `prod`, chưa
   có Lark app/Ingress và audience production vẫn để trống theo yêu cầu của owner.
1. Worker mới trên máy này chỉ được chạy với ID kết thúc bằng `-TEST`. Không đổi hàng rào này để
   thử production.
1. Backup phải giữ `deactivated`; credential của backup chỉ để khôi phục có chủ đích.
1. Knowledge trên Platform hiện vẫn bằng **0**. Không tự upload tài liệu trước khi có xác nhận rõ
   của owner như mục 8.

## 2. Những gì đã hoàn thành

### 2.1 Hồ sơ, version và skill

Cả ba danh tính đã dùng model `gpt-5.6-terra` và được gắn tài khoản Codex
`tienthamnguyen6@gmail.com`. Mark chính, TEST và backup đều có đúng sáu skill thật, mỗi skill là
một thẻ riêng có instruction:

1. Báo cáo dựa trên evidence.
1. Deep-dive bình luận.
1. Lập kế hoạch truy vấn social.
1. Nghiên cứu web và sản phẩm công khai.
1. Phân tích crisis, sentiment và share of voice.
1. Phân tích quảng cáo đối thủ.

TEST được tạo qua self-service `POST /v1/agents/enroll` bằng owner PAT của
`thamnt@hapas.vn` (platform admin), không sửa database. TEST có schema và agent credential riêng,
được auto-approve. Backup cũng là một identity riêng, không phải alias của Mark chính.

### 2.2 Runtime bridge

Đã thêm đường chạy Platform nhưng giữ nguyên đường Lark legacy:

```text
Lark production
  └─ listener.py → run.py → brain.reply → Hermes/Codex + tool hiện có

Platform web chat (TEST)
  └─ Platform job queue → scripts/run_platform_worker.py
       └─ lsr_platform.py → brain.reply → reply/complete + trace/WAL
```

`scripts/run_platform_worker.py`:

- từ chối khởi động nếu `LSR_AGENT_ID` không kết thúc bằng `-TEST`;
- yêu cầu `LSR_JOB_POLL_ENABLED=1`;
- chỉ poll job Platform, không khởi động Lark listener production;
- dùng cùng `brain.reply` để giảm sai lệch hành vi giữa web và Lark.

Bridge trong `lsr_platform.py` đã có:

- lấy version/context theo môi trường `dev`;
- job polling và gửi reply/complete;
- trace, redaction và WAL khi collector lỗi;
- cầu nối model auth từ tài khoản Codex;
- phân biệt `user_ref` web với Lark `open_id`.

Lỗi đã sửa: `user_ref=thamnt@hapas.vn` từ web từng bị gửi nhầm sang Lark Contact API. Hàm
`_lark_sender_ref` giờ chỉ trả sender ref khi chuỗi bắt đầu bằng `ou_`; smoke cuối không còn HTTP
400.

### 2.3 Policy fail-closed

`lsr_policy.py` chặn planner trước handler đối với hành động ghi/gửi chưa được cấp quyền, gồm gửi
tin, tạo task/lịch, ghi Base/Sheet và tool lạ. Lệnh Lark raw chỉ cho phép luồng đọc phù hợp; `POST`
hoặc `--yes` bị chặn. Telemetry redact email, số điện thoại và secret trước khi ghi WAL.

## 3. Trạng thái từng danh tính

### `AG-SOCIAL-LISTENING` — Mark chính

- Platform status: active.
- Latest `dev`: v5.
- `stg/prod`: chưa publish.
- Model: `gpt-5.6-terra`.
- Skills: 6/6 có instruction.
- AI account: Codex đã gắn.
- Lark app / Ingress mới: chưa gắn.
- Knowledge: 0.
- Audience production: chưa chốt, giữ fail-closed.

### `AG-SOCIAL-LISTENING-TEST` — nơi duy nhất được chạy e2e

- Platform status: active, auto-approved.
- Latest `dev`: v3.
- `stg/prod`: chưa publish.
- Model: `gpt-5.6-terra`.
- Skills: 6/6 có instruction.
- AI account: Codex đã gắn.
- Lark app / Ingress: không gắn.
- Knowledge: 0.
- Credential một lần nằm trong `.artifacts/AG-SOCIAL-LISTENING-TEST.env`.

### `AG-MARK-TRAN-BACKUP` — cold standby

- Platform status: **deactivated**.
- Latest `dev`: v4.
- `stg/prod`: chưa publish.
- Model: `gpt-5.6-terra`.
- Skills: 6/6 có instruction.
- AI account: Codex đã gắn.
- Lark app / Ingress / Knowledge: không có.
- Credential một lần nằm trong `.artifacts/AG-MARK-TRAN-BACKUP.env`.

Hai file `.env` nói trên đã được gitignore. **Không in nội dung ra log/chat, không commit và không
dùng credential backup cho TEST.**

## 4. Worker TEST trên máy server này

Worker được chạy bằng một Python process ẩn. PID không cố định và worker chưa được cài thành
Windows service hay Scheduled Task, nên **không tự sống lại sau reboot**.

### Kiểm tra process và log

Chạy trong PowerShell:

```powershell
$repo = 'D:\hapas_agent_social'

Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -like 'python*' -and
    $_.CommandLine -like '*scripts\run_platform_worker.py*'
  } |
  Select-Object ProcessId, ParentProcessId, CreationDate, CommandLine

Get-Content "$repo\.artifacts\platform-worker.out.log" -Tail 100
Get-Content "$repo\.artifacts\platform-worker.err.log" -Tail 100
```

Nếu `Get-CimInstance` báo `Access denied`, mở PowerShell bằng đúng tài khoản đang chạy server hoặc
quyền quản trị. Có thể dùng lệnh không đọc command line dưới đây để đối chiếu `StartTime` và Python
path, nhưng không được dừng PID chỉ dựa vào kết quả này:

```powershell
Get-Process -Name python, pythonw -ErrorAction SilentlyContinue |
  Select-Object Id, ProcessName, StartTime, Path
```

Log hiện dùng:

- `.artifacts/platform-worker.out.log`
- `.artifacts/platform-worker.err.log`

### Khởi động lại TEST worker

Chỉ chạy sau khi xác nhận không còn worker cũ. Đoạn dưới đọc secret vào process environment mà
không in giá trị:

```powershell
$repo = 'D:\hapas_agent_social'
$credentialFile = "$repo\.artifacts\AG-SOCIAL-LISTENING-TEST.env"

Get-Content $credentialFile | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2], 'Process')
  }
}

$env:LSR_COLLECTOR = 'https://collector.34-124-212-76.sslip.io'
$env:LSR_PLATFORM_URL = 'https://platform.34-124-212-76.sslip.io'
$env:LSR_JOB_POLL_ENABLED = '1'
$env:LSR_CONTEXT_ENV = 'dev'
$env:AUDIT_TO_BASE = '0'
$env:PYTHONUNBUFFERED = '1'
$env:LSR_WAL_DIR = "$repo\.artifacts\test-wal"

Start-Process `
  -FilePath 'python' `
  -ArgumentList '-X', 'utf8', 'scripts/run_platform_worker.py' `
  -WorkingDirectory $repo `
  -WindowStyle Hidden `
  -RedirectStandardOutput "$repo\.artifacts\platform-worker.out.log" `
  -RedirectStandardError "$repo\.artifacts\platform-worker.err.log"
```

Sau khi start, kiểm tra process và hai log. Dòng sẵn sàng phải nói rõ đây là Platform TEST worker
và không khởi động listener Lark.

### Dừng worker

Liệt kê bằng lệnh ở trên, kiểm tra chính xác command line, rồi chỉ dừng PID tương ứng:

```powershell
Stop-Process -Id <PID_DA_XAC_NHAN>
```

Không dùng pattern để dừng hàng loạt Python process vì máy này còn chạy server/runtime khác.

## 5. Bằng chứng test đã có

### Local

- Unit suite: **22 passed in 0.04s**.
- Compile: `brain.py`, `lsr_platform.py`, `lsr_policy.py`, `scripts`, `tests` đều pass.
- Behavior eval qua model: **5/5**.
- Manifest hash của eval: `517973a7e2f1357e`.
- Báo cáo: `.artifacts/AG-SOCIAL-LISTENING-TEST-evaluation.json`.

Lệnh chạy lại unit:

```powershell
$tmp = Join-Path '.artifacts' ('pytest-' + [guid]::NewGuid().ToString('N'))
python -X utf8 -m pytest -q -p no:cacheprovider --basetemp $tmp
```

Lệnh compile:

```powershell
python -X utf8 -m compileall -q brain.py lsr_platform.py lsr_policy.py scripts tests
```

### Platform e2e

Đã tạo năm Golden case active trong suite `mark_social_listening`:

| Case | Điều được kiểm |
| --- | --- |
| Kế hoạch social listening HAPAS 7 ngày | Có phạm vi thời gian `7 ngày` |
| Ghi Base và gửi Marketing | Từ chối vì `không có quyền` |
| Suy rộng từ 5 bình luận | Nêu giới hạn của `mẫu` |
| Phân tích quảng cáo thiếu brand/country | Hỏi lại `quốc gia` |
| Dùng chat nội bộ làm knowledge | Từ chối dữ liệu `nội bộ` |

Cả năm prompt đã đi qua đúng chuỗi Platform web chat → job queue → worker local →
`brain.reply` → reply/complete và đạt tiêu chí ngữ nghĩa. Dashboard báo `health: ok`; trace của năm
job Golden là `job-1938` đến `job-1942`.

Smoke bổ sung:

- `job-1944`: sau restart trả `READY TEST`.
- `job-1945`: sau sửa web `user_ref` trả `READY FIX`, không còn Contact API 400.

Chưa có bản ghi formal từ `POST /v1/regression/run`: console hiện chỉ hỗ trợ quản lý Golden case,
còn management API bị Caddy gateway bảo vệ từ máy owner. Vì vậy chỉ được ghi là “Golden 5/5 qua
TEST queue”, **không tuyên bố AG-EVAL server-side đã chạy**.

Dashboard hiện có thể hiển thị token count bằng 0 dù model đã chạy. Nguyên nhân là payload
`complete` của worker đang gửi model và duration nhưng chưa gửi tổng token; runs, traces và health
vẫn hoạt động.

## 6. File đã thêm hoặc thay đổi

Trong `D:\hapas_agent_social`:

- `USECASE.md`: người dùng, kênh, dữ liệu cấm, phạm vi và cổng go-live.
- `TESTCASES.md`: ma trận test và kết quả migration.
- `lsr-agent.yaml`: manifest Mark Trần.
- `skills/`: sáu skill nguồn.
- `knowledge/catalog.json`: allowlist 6 tài liệu và denylist transcript.
- `knowledge/wiki-source.json`: cấu hình Wiki đang `enabled=false`.
- `lsr_policy.py`: policy guard fail-closed.
- `lsr_platform.py`: context/job bridge, WAL, redaction và auth bridge.
- `audit.py`, `brain.py`, `run.py`: tích hợp bridge vào runtime cũ.
- `scripts/sync_platform.py`: đồng bộ profile/version/skills.
- `scripts/evaluate.py`: behavior evaluation.
- `scripts/register_test_agent.py`: self-service enroll TEST.
- `scripts/run_platform_worker.py`: entrypoint TEST-only.
- `tests/`: unit tests cho migration.
- `.env.example`, `.gitignore`: cấu hình mẫu và chặn artifact/secret.

Trong `D:\Platform`:

- `docs/TESTCASES.md` §38: bằng chứng migration ở cấp Platform.
- `docs/agents/AG-SOCIAL-LISTENING.md`: hồ sơ kỹ thuật agent.
- `agents/AG-SOCIAL-LISTENING/README.md`: registry material.
- `agents/REGISTRY.md`, `docs/agents/README.md`: đăng ký và index.
- `docs/decisions/drafts/EXTC-platform-kiem-soat-runtime-agent-chuyen-biet.md`.
- `docs/decisions/drafts/WIKI-nguon-kien-thuc-la-wiki-soan-rieng.md`.

Chưa stage hoặc commit. Cả hai repo đang dirty và repo agent có các file nghiên cứu có từ trước;
không reset, xóa hay gom commit thiếu chọn lọc.

## 7. Trạng thái validation repo Platform

Đã pass:

```powershell
python -X utf8 .claude\skills\decision-records\scripts\decisions.py check
python -X utf8 scripts\validate_skills.py
git diff --check
```

`validate_skills.py` báo 2 skill hợp lệ. `mdformat` đã pass cho tài liệu thay đổi. Full
`pre-commit run --all-files` còn một lỗi môi trường: hook `decisions-check` gọi nhầm Microsoft Store
Python alias trên Windows và thoát `9009`; chạy trực tiếp decision checker như trên thì pass. Các
hook mdformat, EOF, trailing whitespace, large-file và private-key đều pass.

## 8. Knowledge: đã phân loại nhưng chưa upload

`knowledge/catalog.json` cho phép ở môi trường dev sáu file:

1. `research_vn_consumer_signals_ss27.md`
1. `ss2027_jewelry_fragrance_gifting_research.md`
1. `SS27_global_trend_consumer_sources_VN.md`
1. `SS27_product-system_evidence.md`
1. `SS27_Vietnam_accessible_handbag_competitor_scan.md`
1. `tong_hop_nghien_cuu_SS27_HAPAS_MATE_MADE.md`

Bốn transcript bị loại rõ ràng:

1. `ss27_chat_transcript.md`
1. `ss27_chat_transcript_2026-09-07.md`
1. `xuat-toan-bo-chat-ss27.md`
1. `_xuat_toan_bo_chat_SS27.md`

Upload sáu file được đánh dấu `approved_for_dev` đã bị chặn an toàn vì nội dung đầy đủ chứa thông
tin sản phẩm, giá, đối thủ và chiến lược HAPAS/MATE MADE sẽ được gửi lên server. Phiên sau không
được suy diễn trạng thái catalog là quyền upload. Cần owner xác nhận đúng phạm vi sau:

> Cho phép upload 6 file `approved_for_dev` lên `AG-SOCIAL-LISTENING-TEST`, dev-only; không
> production và không transcript.

Nếu có xác nhận, chỉ upload vào TEST/dev, kiểm RAG hit + source URL rồi cập nhật `MARK-05` và test
case Platform `38.10`. Không tự đồng bộ sang Mark chính hoặc backup.

## 9. Wiki và lifecycle còn chờ quyết định

Hai thay đổi kiến trúc mới chỉ là **draft ADR**, tuyệt đối không promote hoặc triển khai production
nếu chưa có `thint` sign-off:

1. `EXTC`: Platform kiểm soát external runtime bằng status stamp/credential lease hết hạn và
   harness fail-safe. Đây là điều kiện cho deactivate thật sự chặn output trong TTL.
1. `WIKI`: knowledge dùng một Wiki riêng cho agent, chọn tới H1, node mới mặc định tắt.

Wiki còn cần owner cung cấp một Lark Wiki root riêng dành cho Mark. Cho đến khi đủ sign-off và root
URL, giữ `knowledge/wiki-source.json` với `enabled=false`.

Ràng buộc kiến trúc hiện hành: core dài hạn là Hive theo accepted ADR `0002`; bridge Hermes trong
repo này chỉ là migration path, không được biến thành platform core mới.

## 10. Những việc còn treo, theo thứ tự đề xuất

1. **Giữ ổn định TEST worker:** kiểm tra process/log sau reboot; chưa cài auto-start nếu owner chưa
   yêu cầu.
1. **Xin xác nhận upload knowledge:** dùng đúng câu xác nhận ở mục 8. Sau khi được phép, upload chỉ
   sáu file allowlist vào TEST/dev và chạy `MARK-05`/RAG evidence.
1. **Chạy WAL e2e:** mô phỏng collector mất kết nối trên TEST, xác minh replay cùng `run_id` cho
   `MARK-04`; không làm gián đoạn listener Lark production.
1. **Hoàn tất server-side regression:** mở đường quản trị phù hợp hoặc chạy từ VM để tạo formal
   `/v1/regression/run`; không ghi AG-EVAL pass trước khi có record.
1. **Lấy `thint` sign-off cho `EXTC` và `WIKI`:** sau sign-off mới promote ADR theo quy trình repo,
   rồi mới triển khai stamp/lease, deactivate TTL và Wiki ingest.
1. **Nhận Wiki root riêng:** kiểm ACL/read-only và source selection; node mới phải default-off.
1. **So sánh kênh Lark/web (`MARK-14`):** chỉ sau khi phạm vi bind đã được owner chốt; kiểm cùng
   persona/version/policy, khác biệt chỉ ở format kênh.
1. **Chốt audience production:** đây là mục “1” owner chủ động để mở, chưa cần thúc. Chỉ khi có danh
   sách người/nhóm, dữ liệu được xem và reviewer mới xét publish `prod` hoặc bind Lark.
1. **Cập nhật token accounting:** bổ sung usage vào payload complete để dashboard không báo 0 sai.
1. **Chuẩn bị commit/PR có chọn lọc:** chạy lại unit, decision checker, skill validator,
   `git diff --check`, quét secret và pre-commit. Không commit `.artifacts` hoặc transcript.

## 11. Không được làm

- Không chạy e2e trên `AG-SOCIAL-LISTENING` hoặc bot Lark thật.
- Không publish `prod`, gắn Lark app/Ingress hoặc mở audience khi chưa được owner chốt.
- Không activate backup chỉ để thử.
- Không upload transcript/chat nội bộ, secret, HR/payroll hoặc raw social PII.
- Không in hai file credential trong `.artifacts` ra terminal/chat.
- Không sửa database Platform trực tiếp; đi qua self-service/change flow.
- Không promote hai draft ADR nếu thiếu `thint` sign-off.
- Không tuyên bố AG-EVAL server-side pass khi mới có local eval và Golden queue evidence.
- Không dùng `Stop-Process` theo pattern rộng hoặc dừng toàn bộ Python trên máy server.
- Không reset/xóa worktree dirty; các file nghiên cứu hiện có thuộc phạm vi dữ liệu của owner.

## 12. Checklist cho phiên kế tiếp

Một phiên mới được xem là đã hiểu bàn giao khi trả lời được các câu sau trước khi sửa/chạy gì:

- Agent nào duy nhất được dùng cho e2e? `AG-SOCIAL-LISTENING-TEST`.
- Agent nào phải giữ deactivated? `AG-MARK-TRAN-BACKUP`.
- Mark Platform đã production chưa? Chưa; chỉ có `dev`, không có Lark/Ingress/audience production.
- Knowledge đã upload chưa? Chưa; cả ba đang 0.
- Có được upload sáu file allowlist ngay không? Chưa; cần xác nhận owner theo mục 8.
- Formal AG-EVAL đã chạy chưa? Chưa; mới có local behavior eval 5/5 và Golden queue 5/5.
- Hai việc kiến trúc đang chờ ai? `EXTC` và `WIKI` chờ `thint` sign-off.
- Worker có tự chạy sau reboot không? Không.
- Đường production hiện tại là gì? Lark legacy → `run.py`/`brain.py`; Platform chưa thay thế.
