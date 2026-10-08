# Cho đọc một bảng trong Base nội bộ hỗn hợp

Mark mặc định không cho người ngoài chủ agent đọc Base chứa Audit hoặc Chi phí quét.
Nếu cùng Base có một bảng công việc cần chia sẻ, chủ agent phải cho phép **đúng cặp**
`app_token` và `table_id`. Quyền này không thay thế quyền Lark của người hỏi.

Tạo `.tokens/mixed_base_read_allowlist.json` trên từng máy chạy Mark:

```json
{
  "version": 1,
  "tables": [
    {
      "app_token": "APP_TOKEN_CUA_BASE",
      "table_id": "TABLE_ID_BANG_CONG_VIEC"
    }
  ]
}
```

Đây là file runtime đã bị `.gitignore`; không commit token thật. Trước khi cấu hình, lấy
`table_id` từ link `...?table=tbl...` và đối chiếu tên bảng bằng API chỉ đọc. Không thêm
table Audit, Audit cũ hoặc Chi phí quét. Mark vẫn từ chối nếu `audit_base.json`,
`audit_base.previous.json`, hoặc `chi_phi_quet_base.json` bị thiếu, hỏng hay
thiếu `app_token`/`table_id`. Cả ba file đều bắt buộc để mở ngoại lệ; nếu hệ thống chưa
có Audit cũ, chủ vận hành phải xác minh trạng thái và tạo metadata bảo vệ theo quy trình
triển khai trước khi bật allowlist, không được dùng một token giả để lách cửa kiểm tra.

Kiểm tra khô, không gọi Lark và không ghi production:

```powershell
$env:LARK_APP_ID='test'; $env:LARK_APP_SECRET='test'
python -m pytest tests/test_mixed_base_scope.py -q
```

Link phải chỉ đúng một bảng. Mark từ chối link đọc cả Base, tham số `table` lặp/mâu
thuẫn, bảng không tồn tại, và yêu cầu `dem_bang.tab` đổi sang bảng khác.
