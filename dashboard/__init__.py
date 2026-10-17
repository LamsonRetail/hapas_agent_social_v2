"""Dashboard lắng nghe MXH `social.hapas.vn` (đợt 2, chủ dự án chốt 14/10/2026).

Chỉ gồm: chỉ số kiểu Kompa, quản lý dự án + nguồn theo dõi + đề xuất nguồn, ngân sách theo
dõi tháng, danh sách người xem. KHÔNG chứa kỹ năng, persona, công tắc năng lực, trần mỗi lượt
hay lịch chạy của Mark — những thứ đó vẫn ở console platform (chủ dự án: "mark vẫn phải theo
luật của platform như trước không đổi … dashboard chỉ gồm những chỉ số và quản lý nguồn cũng
như ngân sách chứ ko bao gồm bộ kĩ năng hay gì khác của mark đang có ở platform"). Ngoại lệ
chủ dự án chốt 15/10/2026 ("Dashboard + Mark tự chạy"): lịch quét TỰ ĐỘNG của /theodoi (tab Lịch
quét, bảng `lich_quet`); lịch Giao việc trên console vẫn ở console.

Gói này chạy trong venv RIÊNG trên VPS (user hệ điều hành `lang_nghe_web`), không import module
nào của Mark: chỉ thư viện chuẩn + fastapi/jinja2/httpx/psycopg. Chiều ngược lại thì được: Mark
import `dashboard.lich_quet` (thuần, chỉ thư viện chuẩn) để tính mốc giống hệt dashboard; tool
`hoi_dashboard` của Mark (17/10/2026) import `chi_so`, `chi_phi`, `trang_lich`, `nhap_lieu` và các
hàm ĐỌC của `kho` để trả lời số liệu trong chat bằng đúng phép tính của trang — giữ các module đó
thuần (không import FastAPI/`app`), và sửa `/api/chi-so` thì sửa cả `hoi_dashboard_tool.tinh_chi_so`
(bài thử `test_hoi_dashboard.py` so từng khối).
"""
