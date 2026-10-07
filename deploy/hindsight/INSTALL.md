# Cài Hindsight cho kho bài học của Mark (VPS Ubuntu 24.04)

Hindsight 0.10.2 (MIT) chạy như một dịch vụ riêng, user riêng, chỉ nghe `127.0.0.1:8888`,
có khoá API, KHÔNG gọi LLM (`LLM_PROVIDER=none`, lưu nguyên văn `chunks`), embedding đa
ngữ nhỏ `intfloat/multilingual-e5-small` (ONNX, 384 chiều, không cần torch), reranker
`rrf`, Postgres 16 hệ thống + pgvector. Mark gọi qua REST; Mark KHÔNG phụ thuộc dịch vụ
này để khởi động (không `Requires=`).

Mọi bước dưới đây cần người duyệt trước khi chạy trên VPS.

## 1. Postgres 16 + pgvector

```bash
sudo apt update
sudo apt install -y postgresql-16 postgresql-16-pgvector python3.12-venv
# Ubuntu 24.04 có pgvector 0.6.x — đủ dùng. Muốn 0.8.x (quét ANN lặp) thì dùng apt PGDG.
sudo -u postgres psql -c "SHOW listen_addresses;"      # phải là localhost (mặc định)
sudo -u postgres createuser --no-superuser --no-createdb --no-createrole hindsight
sudo -u postgres createdb -O hindsight hindsight
sudo -u postgres psql -d hindsight -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Kết nối bằng Unix socket với xác thực `peer` (mặc định của Ubuntu cho `local`): user hệ
điều hành `hindsight` = role `hindsight`, không mật khẩu, không mở cổng 5432 ra ngoài.

## 2. User, thư mục, venv

```bash
sudo useradd --system --home-dir /opt/hindsight --create-home --shell /usr/sbin/nologin hindsight
sudo -u hindsight python3.12 -m venv /opt/hindsight/venv
sudo -u hindsight /opt/hindsight/venv/bin/pip install --upgrade pip
sudo -u hindsight /opt/hindsight/venv/bin/pip install 'hindsight-api-slim[local-onnx]==0.10.2'
```

Gói `slim` + extra `local-onnx` kéo onnxruntime/transformers/tokenizers, KHÔNG kéo torch
hay pg0. Không cài `hindsight-api` (bản full kéo torch và pg0 nhúng).

## 3. Tải sẵn mô hình embedding (một lần, cần mạng)

```bash
sudo -u hindsight mkdir -p /opt/hindsight/models
sudo -u hindsight /opt/hindsight/venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download(repo_id="intfloat/multilingual-e5-small",
                  local_dir="/opt/hindsight/models/intfloat__multilingual-e5-small",
                  allow_patterns=["onnx/model.onnx", "onnx/model.onnx_data", "*.json",
                                  "*.txt", "*.model"])
PY
```

Sau bước này dịch vụ chạy với `HF_HUB_OFFLINE=1` và `IPAddressDeny=any` (không ra mạng).
Đổi mô hình embedding về sau phải nhúng lại toàn bộ — nạp lại từ sổ cái JSONL của Mark.

## 4. Cấu hình + khoá

```bash
sudo install -o hindsight -g hindsight -m 600 deploy/hindsight/hindsight.env.example /opt/hindsight/.env
openssl rand -hex 32    # chép vào HINDSIGHT_API_TENANT_API_KEY trong /opt/hindsight/.env
sudo -u hindsight nano /opt/hindsight/.env
```

Cùng giá trị khoá đó đặt vào `.env` của Mark: `MARK_HINDSIGHT_API_KEY=…`,
`MARK_HINDSIGHT_URL=http://127.0.0.1:8888`. Không dán khoá vào chat, log hay commit.

## 5. Dịch vụ

```bash
sudo install -m 644 deploy/hindsight/hindsight.service /etc/systemd/system/hindsight.service
sudo systemctl daemon-reload
sudo systemctl enable --now hindsight
sudo journalctl -u hindsight -n 50 --no-pager     # chờ dòng Uvicorn running on http://127.0.0.1:8888
```

Lần đầu khởi động tự chạy migration vào DB `hindsight`. Unit ép `HOST=127.0.0.1`, MCP tắt,
`LLM_PROVIDER=none`, `MemoryMax=2G`, `CPUQuota=200%`. Không chạy control-plane UI (:9999).

## 6. Bank + kiểm

```bash
# bank staging để thử, rồi bank thật — chạy thử trước, thêm --thuc-hien để làm thật
MARK_HINDSIGHT_BANK=hapas-mkt-bai-hoc-staging python3 scripts/bai_hoc_admin.py --env-file /opt/mark/.env init-bank
python3 scripts/bai_hoc_admin.py --env-file /opt/mark/.env init-bank
sudo bash deploy/hindsight/smoke_test.sh
```

`smoke_test.sh` kiểm: chỉ nghe 127.0.0.1, `/health`, thiếu khoá → 401, MCP tắt, và lưu
2 bài học tiếng Việt vào bank staging rồi nhớ lại bằng câu hỏi diễn đạt khác với lọc tag
`all_strict` (đúng bài, không lọt team khác), dọn bài thử sau đó.

## 7. Bật trên Mark

Thêm `MARK_HINDSIGHT_URL`, `MARK_HINDSIGHT_API_KEY` (và tuỳ chọn `MARK_HINDSIGHT_BANK`, `BAI_HOC_TEAMS`,
`BAI_HOC_SO_CAI`) vào `.env` của Mark, rồi `mark restart`. Thiếu một trong hai biến đầu là
hai tool `ghi_bai_hoc`/`nho_bai_hoc` ẩn hẳn. Thử trên agent TEST trước.

Lưu ý: biến của Mark CỐ Ý mang tiền tố `MARK_`. Plugin memory Hindsight của Hermes đọc
`HINDSIGHT_API_KEY`/`HINDSIGHT_API_URL` và mặc định gửi lên cloud của Vectorize — KHÔNG
đặt hai biến trần đó trong `.env` của Mark, và KHÔNG đặt `memory.provider: hindsight`
trong `config.yaml` của Hermes. Mark dùng tool riêng, không dùng plugin đó.

## Vận hành

- Dọn bài quá 365 ngày: `python3 scripts/bai_hoc_admin.py --env-file /opt/mark/.env purge
  --older-than-days 365` (chạy thử), thêm `--thuc-hien` để xoá. Có thể đặt timer hằng tháng.
- Xoá một bài: `… delete bh-xxxxxxxxxxxx --thuc-hien`.
- Sao lưu: `sudo -u postgres pg_dump -Fc hindsight > /opt/hindsight/backup/hindsight-$(date +%F).dump`.
