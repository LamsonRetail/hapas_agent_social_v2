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
và công tắc tool phải bật rõ (có dòng `chi_so_ads`, không dòng nào `bat` khác `true`).
Mark chỉ nhận người hỏi từ: chat riêng Lark (người gửi do gateway/listener ghi), job web có
`sender_identity_verified`, hoặc lịch Platform gửi vào chat riêng (`scheduled_by`). Job A2A
và kênh không rõ bị từ chối. Sheet chỉ cấp quyền **xem** cho người hỏi. Lượt trả số gửi kèm
cờ `restricted: chi_so_ads` lên `/reply` để Platform ẩn nội dung khỏi role `user` trong bản
ghi hội thoại. Luồng Sheet cần cấu hình Lark và Platform của agent thử. Kiểm Meta trực tiếp
chưa thay thế nghiệm thu luồng này.

Mốc ngày (hôm qua, 7 ngày…) tính theo múi giờ của từng tài khoản (`timezone_name`), đúng
cách Meta cộng số; "hôm nay" và "tháng này" ghi rõ ngày hiện tại chưa hết. Dòng có hiển thị
hoặc chi tiêu mà Meta không trả action (Meta bỏ số 0) được ghi 0.

Token rời `os.environ` khi nạp `meta_ads_tool` (giữ trong bộ nhớ module), và mọi env tiến
trình con dựng qua `cli_support` bỏ `MARK_META_*`. Bộ thử không nạp `MARK_META_*` từ `.env`.

Restart runtime sau khi sửa `.env` vì loader nạp cấu hình khi khởi động.
Phase 2 Base hằng ngày chỉ bắt đầu sau khi phase 1 được kiểm tra thật.
