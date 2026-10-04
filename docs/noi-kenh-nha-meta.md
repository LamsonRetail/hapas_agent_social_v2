# Nối kênh HAPAS (Threads, Instagram, Fanpage) cho Mark

Sau khi nối, Mark đọc được **đủ** bình luận và trả lời lồng nhau dưới bài của chính
HAPAS, miễn phí, qua API chính thức của Meta (tool `binh_luan_kenh_nha`). Không cần App
Review: tài khoản HAPAS là tester của app, app để ở chế độ Development.

Kênh nào chưa dán token thì Mark báo "kênh X chưa nối", các kênh khác vẫn chạy.

## 1. Tạo app Meta

1. Vào <https://developers.facebook.com/apps> → **Create app**.
2. Use case: chọn **Access the Threads API**, **Manage messaging & content on
   Instagram** và **Manage everything on your Page** (thêm dần ở bước 2 cũng được).
3. Ghi lại **App ID** và **App Secret** (App settings → Basic).

## 2. Thêm sản phẩm và quyền

| Kênh | Sản phẩm trong app | Quyền (scope) cần tick |
|---|---|---|
| Threads | Threads API | `threads_basic`, `threads_read_replies` |
| Instagram | Instagram API with Instagram Login | `instagram_business_basic`, `instagram_business_manage_comments` |
| Facebook | Facebook Login for Business (Pages) | `pages_read_engagement`, `pages_show_list` |

Instagram phải là tài khoản **Business** hoặc **Creator**.

## 3. Thêm tester và nhận lời mời

- App roles → Roles → **Add People** → thêm tài khoản Facebook quản trị Fanpage HAPAS
  (vai trò Tester hoặc Developer).
- Threads: Threads API → Settings → **Threads Testers** → thêm tên tài khoản Threads
  của HAPAS. Đăng nhập Threads bằng tài khoản đó → Settings → Account → Website
  permissions → **Invites** → Accept.
- Instagram: Instagram API with Instagram Login → **Instagram Testers** → thêm tài khoản
  IG của HAPAS. Đăng nhập instagram.com bằng tài khoản đó → Settings → Apps and
  websites → **Tester invites** → Accept.

## 4. Lấy token

- **Threads**: Threads API → **User Token Generator** → Generate cho tài khoản HAPAS
  (chọn `threads_basic`, `threads_read_replies`). Token ngắn hạn cũng được — Mark tự đổi
  sang token 60 ngày.
- **Instagram**: Instagram API with Instagram Login → *Generate access tokens* → **Add
  account** → đăng nhập IG của HAPAS → Generate token.
- **Facebook**: <https://developers.facebook.com/tools/explorer> → chọn app → *User
  Token* → tick `pages_read_engagement`, `pages_show_list` → Generate. Dán token USER này
  cũng được (Mark tự đổi sang token Trang không hết hạn, cần App ID + Secret), hoặc tự
  gọi `me/accounts` rồi lấy `access_token` của Trang. **FB_PAGE_ID** là số ID Trang (cột
  `id` trong `me/accounts`, hoặc Trang → Giới thiệu → Minh bạch trang).

## 5. Dán vào `.env` (máy PC, `D:\hapas_agent_social\.env`)

```
META_APP_ID=...
META_APP_SECRET=...
THREADS_ACCESS_TOKEN=...
IG_ACCESS_TOKEN=...
FB_PAGE_ID=...
FB_PAGE_ACCESS_TOKEN=...
```

Mỗi giá trị một dòng, không thêm chú thích cuối dòng. Không gửi token qua chat.

Token đã đổi/làm mới được lưu ở `.tokens/meta_kenh_nha.json`, **không** ghi lại vào
`.env`. Token Threads/Instagram sống 60 ngày; Mark tự làm mới khi còn dưới 10 ngày (kiểm
mỗi 12 giờ). Muốn thay token thì dán token mới vào `.env` — Mark tự nhận và nạp lại.

## 6. Thử trên PC (chỉ đọc, không tạo sheet)

```
cd D:\hapas_agent_social
python scripts\thu_kenh_nha.py
```

In ra mỗi kênh: số bài (3 bài mới nhất), số bình luận (tối đa 50/bài), số trả lời lồng
nhau, tình trạng token. Không in token.

## 7. Đưa lên VPS

```
bash deploy/vps/push-from-pc.sh env
mark restart
```

## Khi Mark báo lỗi

| Mark nói | Việc cần làm |
|---|---|
| "kênh X chưa nối" | Dán đủ khoá của kênh đó vào `.env`, đẩy lên VPS, restart |
| "token hết hạn / không hợp lệ — chủ agent cần cấp lại" | Tạo token mới (bước 4), dán đè, đẩy lên VPS, restart |
| "token thiếu quyền đọc bình luận" | Tạo lại token, tick đủ quyền ở bảng bước 2 |
| "Meta đang giới hạn số lần gọi" | Đợi vài phút rồi hỏi lại |

Lỗi token cũng được ghi log trên VPS (`journalctl`, dòng bắt đầu `[kenh_nha]`), không
bao giờ in giá trị token.
