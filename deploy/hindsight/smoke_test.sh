#!/usr/bin/env bash
# Kiểm nhanh dịch vụ Hindsight sau khi cài (chạy trên VPS, bằng root hoặc user hindsight).
#   sudo bash deploy/hindsight/smoke_test.sh
# Kiểm: (1) chỉ nghe 127.0.0.1:8888  (2) /health  (3) thiếu khoá → 401  (4) MCP tắt
#       (5) lưu 2 bài học tiếng Việt vào bank STAGING rồi nhớ lại bằng câu hỏi diễn đạt
#           khác, lọc tag all_strict → đúng bài, không lọt bài của team khác; dọn sau đó.
# Chỉ đụng bank staging (mặc định hapas-mkt-bai-hoc-staging), không đụng bank thật.
set -euo pipefail

URL="${MARK_HINDSIGHT_URL:-http://127.0.0.1:8888}"
BANK="${HINDSIGHT_SMOKE_BANK:-hapas-mkt-bai-hoc-staging}"
ENV_FILE="${HINDSIGHT_ENV_FILE:-/opt/hindsight/.env}"
if [[ -z "${MARK_HINDSIGHT_API_KEY:-}" && -r "$ENV_FILE" ]]; then
  MARK_HINDSIGHT_API_KEY="$(grep -E '^HINDSIGHT_API_TENANT_API_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '"'"'")"
fi
[[ -n "${MARK_HINDSIGHT_API_KEY:-}" ]] || { echo "THIẾU khoá (MARK_HINDSIGHT_API_KEY hoặc $ENV_FILE)"; exit 2; }
AUTH=(-H "Authorization: Bearer ${MARK_HINDSIGHT_API_KEY}" -H "Content-Type: application/json")
LOI=0
ok()  { echo "  OK   $*"; }
hong(){ echo "  HỎNG $*"; LOI=1; }

echo "1) Địa chỉ nghe của cổng 8888"
NGHE="$(ss -ltnH 'sport = :8888' | awk '{print $4}' | sort -u)"
if [[ -z "$NGHE" ]]; then hong "không có tiến trình nào nghe :8888"
elif echo "$NGHE" | grep -qv '^127\.0\.0\.1:8888$'; then hong "nghe ngoài localhost: $(echo $NGHE)"
else ok "chỉ 127.0.0.1:8888"; fi
if ss -ltnH 'sport = :9999' | grep -q .; then hong "có thứ đang nghe :9999 (control plane?)"; else ok "không có :9999"; fi

echo "2) /health"
[[ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/health")" == 200 ]] && ok "/health 200" || hong "/health không 200"

echo "3) Thiếu khoá phải bị từ chối"
MA="$(curl -s -o /dev/null -w '%{http_code}' "$URL/v1/default/banks/$BANK/documents")"
[[ "$MA" == 401 || "$MA" == 403 ]] && ok "không khoá → $MA" || hong "không khoá → $MA (phải 401)"

echo "4) MCP tắt"
MA="$(curl -s -o /dev/null -w '%{http_code}' "${AUTH[@]}" "$URL/mcp/$BANK/")"
[[ "$MA" == 404 || "$MA" == 405 ]] && ok "/mcp → $MA" || hong "/mcp → $MA (phải 404)"

echo "5) Lưu + nhớ lại tiếng Việt trên bank $BANK"
curl -sf -X PUT "${AUTH[@]}" "$URL/v1/default/banks/$BANK" \
  -d '{"retain_extraction_mode":"chunks","enable_observations":false}' >/dev/null \
  && ok "tạo/cập nhật bank staging" || hong "không tạo được bank staging"
luu() {  # $1 doc_id  $2 team  $3 nội dung
  python3 - "$1" "$2" "$3" <<'PY' | curl -sf -X POST "${AUTH[@]}" "$URL/v1/default/banks/$BANK/memories" -d @- >/dev/null
import json, sys
ma, team, nd = sys.argv[1:4]
tag = ["loai:bai_hoc", f"team:{team}", "chien_dich:smoke-test"]
print(json.dumps({"items": [{"content": nd, "timestamp": "2026-09-30T00:00:00Z",
  "context": "bai_hoc_chien_dich", "document_id": ma, "tags": tag,
  "metadata": {"ma_bai_hoc": ma, "team": team, "schema": "1"}}],
  "async": False, "document_tags": tag}, ensure_ascii=False))
PY
}
luu bh-smoke00000a branding-ads "[Bài học chiến dịch] Chiến dịch: Smoke test | Team: Branding Ads | Kênh: tiktok
Đã thử: đẩy video KOC nano bằng Spark Ads 7 ngày, ngân sách 5 triệu
Kết quả đo được: CPM 18.000đ, 1,2 triệu lượt xem, chi phí mỗi tin nhắn giảm 30%
Đánh giá: hiệu quả" && ok "lưu bài team A" || hong "không lưu được bài team A"
luu bh-smoke00000b kol-koc "[Bài học chiến dịch] Chiến dịch: Smoke test | Team: KOL KOC | Kênh: facebook
Đã thử: livestream bán túi với KOL tầm trung 2 giờ
Kết quả đo được: 45 đơn, chi phí mỗi đơn 210.000đ
Đánh giá: lẫn lộn" && ok "lưu bài team B" || hong "không lưu được bài team B"

KQ="$(curl -sf -X POST "${AUTH[@]}" "$URL/v1/default/banks/$BANK/memories/recall" -d '{
  "query":"quảng cáo video người có ảnh hưởng nhỏ trên TikTok tốn bao nhiêu mỗi nghìn lượt hiển thị",
  "tags":["loai:bai_hoc","team:branding-ads"],"tags_match":"all_strict","budget":"mid","max_tokens":1500}' || true)"
python3 - "$KQ" <<'PY' && ok "nhớ lại đúng bài team A, không lọt team B" || hong "nhớ lại sai (xem trên)"
import json, sys
try:
    r = json.loads(sys.argv[1] or "{}").get("results") or []
except ValueError:
    print("    trả về không phải JSON"); sys.exit(1)
ma = [x.get("document_id") for x in r]
print("    document_id:", ma)
sys.exit(0 if ma and ma[0] == "bh-smoke00000a" and "bh-smoke00000b" not in ma else 1)
PY

for ma in bh-smoke00000a bh-smoke00000b; do
  curl -s -o /dev/null -X DELETE "${AUTH[@]}" "$URL/v1/default/banks/$BANK/documents/$ma" || true
done
ok "đã dọn 2 bài thử"

[[ $LOI == 0 ]] && echo "TẤT CẢ ĐẠT" || { echo "CÓ MỤC HỎNG"; exit 1; }
