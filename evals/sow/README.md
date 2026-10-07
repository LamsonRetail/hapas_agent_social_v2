# Bộ nghiệm thu SOW Marketing HAPAS (Promptfoo)

Chấm Mark theo từng hạng mục AI trong SOW "MARKETING HAPAS" bằng các ca hỏi thật, chạy lại
được sau mỗi lần sửa kỹ năng/prompt. Áp dụng repo [Promptfoo](https://github.com/promptfoo/promptfoo)
(MIT) theo quyết định ngày 06/10/2026.

## Chấm gì

- `cases/dong_<NN>_*.yaml`: mỗi file một hạng mục SOW (NN = số thứ tự trong SOW), 2–5 ca.
- Mọi ca đều phải: không lỗi, không tự chạy tool ghi/tốn tiền (trừ `chi_uoc_tinh`), không lộ
  SĐT/email/open_id, không dùng bảng markdown (`defaultTest` trong `promptfooconfig.yaml`).
- Từng ca chấm thêm: nạp đúng kỹ năng, gọi đúng tool (vd `doc_bang` khi có link Sheet), và
  các mốc chữ bắt buộc mà kỹ năng quy định (vd "GIẢ ĐỊNH", "[CHƯA CÓ NGƯỜI]").
- Chỉ dùng phép chấm XÁC ĐỊNH (không dùng AI chấm AI). Tiêu chí cần người đọc nằm ở dòng
  `# người chấm:` trong file ca — xem trong giao diện `promptfoo view` và chấm tay.

## An toàn

`mark_provider.py` chạy `brain.reply` của nhánh hiện tại ở chế độ thử:

- Chỉ ĐỌC ngữ cảnh prod của Mark (GET), thay mục lục kỹ năng bằng `skills/` cục bộ.
- Chặn: chạy actor Apify, tạo/ghi/cấp quyền Lark Sheet, mọi tool trong
  `lsr_policy._MUTATING_EXACT` (trừ `chi_uoc_tinh`), báo lượt và ghi ngữ cảnh lên platform,
  đẩy audit lên Base.
- Có gọi model thật qua tài khoản AI của Mark (như staging), nên mỗi lần chạy đủ bộ tốn vài
  chục lượt hỏi. Chạy một hạng mục khi chỉ sửa một kỹ năng.
- Tắt telemetry, chia sẻ cloud và kiểm tra cập nhật của Promptfoo (`chay.ps1` đặt sẵn). Kết
  quả chỉ nằm trên máy chạy. Không chạy trên VPS production.

## Chạy

Cần Node ≥ 22.22 và Python có đủ thư viện của Mark. File env của Mark: mặc định `<repo>/.env`,
hoặc đặt `MARK_ENV_FILE`.

```powershell
# cả bộ
powershell -File evals\sow\chay.ps1
# một hạng mục (vd SOW 6 — Họp)
powershell -File evals\sow\chay.ps1 -Loc "SOW 6 "
# xem kết quả, chấm tay tiêu chí "người chấm"
npx promptfoo@0.124.0 view
```

`-Loc` lọc theo `description` của ca (`--filter-pattern`). Kết quả JSON ghi ra
`evals/sow/ket-qua/` (đã gitignore), rồi `tong_hop.py` in bảng theo hạng mục SOW.

## Độ ổn định (pass^k)

Một lần chạy đạt chưa chắc lần sau đạt. Theo eval-harness của ECC, nghiệm thu dùng
pass^k: hỏi mỗi ca k lần (`-Lap 3`), ca chỉ tính đạt khi đạt CẢ k lần. `tong_hop.py` in
pass^k, pass@k và liệt kê ca chập chờn kèm lý do trượt. Chạy `-Lap 3` trước khi publish
kỹ năng lên prod; khi chỉ sửa nhanh thì `-Lap 1`.

## Thêm ca

Thêm vào file `cases/` đúng hạng mục, giữ dạng:

```yaml
- description: "SOW 6 · Họp — ..."
  metadata: {sow_dong: 6, hang_muc: "Họp dự án và phối hợp liên phòng ban"}
  vars: {ma: d06x, hoi: "câu người dùng hỏi"}
  assert:
    - {type: python, value: "file://kiem.py:nap_ky_nang", config: {ten: "Họp dự án và bàn giao liên phòng ban"}}
    - {type: icontains, value: "[CHƯA CÓ HẠN]"}
```

Hàm chấm hành vi có sẵn trong `kiem.py`: `nap_ky_nang`, `khong_nap_ky_nang`, `goi_tool`,
`chi_uoc_tinh`, `dem_it_nhat`, `khong_tu_ghi`, `khong_lo_thong_tin`.
`goi_tool` nhận thêm `co_tham_so` (vd `{ten: dem_bang, co_tham_so: du_lieu}`: phải đếm trên
chữ người dùng dán, không phải trên Sheet).
`tests/test_nghiem_thu_sow.py` kiểm các file ca hợp lệ (đọc được, tên kỹ năng có thật).
