# Cấu hình số Meta Ads cho Mark

Trong `.env` cục bộ của runtime Mark:

```env
MARK_META_ADS_TOKEN=
MARK_META_API_VERSION=v26.0
MARK_META_AD_ACCOUNT_IDS=
```

Dán token system user đã được duyệt với `ads_read` và `read_insights` vào
`MARK_META_ADS_TOKEN`. Chủ Mark xác nhận ID các tài khoản thuộc phạm vi HAPAS được đọc,
rồi điền `MARK_META_AD_ACCOUNT_IDS` dạng `act_123,act_456` (tối đa 200 ID).
Không dùng tên tài khoản hoặc `*`. Không đưa token vào chat hoặc Git.

Code lấy giao giữa ID được duyệt với danh sách `me/adaccounts` hiện được cấp cho token.
Cấu hình ID rỗng/sai hoặc danh sách Meta bị cắt đều từ chối. Tài khoản đã mất quyền tự bị
loại; ID khác vẫn bị loại dù token có quyền. Thêm tài khoản mới cần xác nhận và cập nhật
cấu hình. Code không gọi Business API, không yêu cầu `business_management` và chỉ GET Meta.

Đây là cấu hình tài khoản quảng cáo. Người hỏi vẫn phải có tên trong danh sách console
và tool phải bật; dữ liệu chỉ xuất trong chat riêng/web xác thực. Luồng Sheet cần cấu hình
Lark và Platform của agent thử. Kiểm Meta trực tiếp chưa thay thế nghiệm thu luồng này.

Restart runtime sau khi sửa `.env` vì loader nạp cấu hình khi khởi động.
Phase 2 Base hằng ngày chỉ bắt đầu sau khi phase 1 được kiểm tra thật.
