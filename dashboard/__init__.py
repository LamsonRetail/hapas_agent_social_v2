"""Dashboard lắng nghe MXH `social.hapas.vn` (đợt 2, chủ dự án chốt 14/10/2026).

Chỉ gồm: chỉ số kiểu Kompa, quản lý dự án + nguồn theo dõi + đề xuất nguồn, ngân sách theo
dõi tháng, danh sách người xem. KHÔNG chứa kỹ năng, persona, công tắc năng lực, trần mỗi lượt
hay lịch chạy của Mark — những thứ đó vẫn ở console platform (chủ dự án: "mark vẫn phải theo
luật của platform như trước không đổi … dashboard chỉ gồm những chỉ số và quản lý nguồn cũng
như ngân sách chứ ko bao gồm bộ kĩ năng hay gì khác của mark đang có ở platform").

Gói này chạy trong venv RIÊNG trên VPS (user hệ điều hành `lang_nghe_web`), không import module
nào của Mark: chỉ thư viện chuẩn + fastapi/jinja2/httpx/psycopg.
"""
