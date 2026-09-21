# Use case — Mark Trần (`AG-SOCIAL-LISTENING`)

> Trạng thái: triển khai kỹ thuật trên `AG-SOCIAL-LISTENING-TEST`. Phạm vi người dùng
> production vẫn để mở theo yêu cầu ngày 16/09/2026; vì vậy audience production đang
> fail-closed và chưa được phép go-live.

## Bài toán

Mark hỗ trợ đội Marketing phát hiện và tổng hợp tín hiệu công khai về thương hiệu,
đối thủ, sản phẩm và xu hướng. Kết quả phải phân biệt rõ dữ kiện, suy luận và khoảng
trống dữ liệu; không được biến tín hiệu mẫu thành kết luận toàn thị trường.

## Người dùng và kênh

- Giai đoạn TEST: `thamnt@hapas.vn`, qua Platform web chat; không nối app Lark thật.
- Giai đoạn production: người dùng, nhóm Lark và audience cụ thể **chưa chốt**.
- App Lark hiện tại được giữ nguyên; chỉ bind vào Platform sau khi owner chốt phạm vi.

## Luồng chính

1. Người dùng nêu brand/chủ đề, nguồn, khoảng thời gian và mục tiêu phân tích.
1. Mark lập kế hoạch truy vấn, nói rõ chi phí/giới hạn và chỉ dùng nguồn công khai được cấp.
1. Mark thu thập bằng connector đọc phù hợp, lưu evidence và nguồn.
1. Mark phân tích sentiment, chủ đề, tín hiệu rủi ro hoặc đối thủ.
1. Mark trả báo cáo có nguồn, độ tin cậy, giới hạn mẫu và đề xuất bước tiếp theo.

## Luồng chuyên môn

- Social listening đa nền tảng theo keyword/brand.
- Deep-dive bình luận của một tập bài đã xác định.
- Phân tích quảng cáo đối thủ từ Meta Ad Library.
- Public web/product research và competitor scan.
- Cảnh báo tín hiệu khủng hoảng; không tự tuyên bố một sự kiện là khủng hoảng nếu
  evidence chưa đủ.

## Ngoài phạm vi

- Tự gửi tin, đăng bài, tạo task/lịch hoặc thay đổi tài liệu/Base.
- Dùng tài khoản hoặc browser profile cá nhân để vượt tường đăng nhập.
- Thu thập chat nội bộ, HR/payroll, credential hoặc PII không cần thiết.
- Ra quyết định truyền thông thay người có thẩm quyền.

## Dữ liệu

Được phép trong TEST:

- Nội dung web/social công khai.
- Meta Ad Library công khai.
- Knowledge đã được đánh dấu `approved_for_dev` trong `knowledge/catalog.json`.

Cấm:

- Chat transcript và export toàn bộ hội thoại.
- Dữ liệu HR/payroll, chat nội bộ, secret/token.
- Social PII thô ngoài phần trích dẫn tối thiểu cần cho evidence.

## Quyền xem

- TEST: chỉ owner `thamnt@hapas.vn` và quản trị viên Platform phục vụ kiểm thử.
- Production: để trống, fail-closed, chờ owner chốt email/role và nội dung mỗi audience.

## Cổng go-live

Không được bind Lark thật hoặc publish production cho đến khi:

1. Audience production được chốt.
1. ADR external-runtime và Wiki được `thint` sign-off.
1. Policy guard chặn được mọi thao tác ghi/gửi trong test.
1. Context/RAG, WAL, deactivate/lease và AG-EVAL có kết quả ghi trong TESTCASES.
