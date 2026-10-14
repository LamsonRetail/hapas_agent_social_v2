// Dùng chung mọi trang. CSP cấm script nội dòng (onclick=…), nên hỏi xác nhận gắn ở đây:
// biểu mẫu có data-xac-nhan="câu hỏi" thì hỏi trước khi gửi (xoá nguồn, xoá người xem…).
"use strict";
document.addEventListener("submit", function (e) {
  var f = e.target;
  if (!(f instanceof HTMLFormElement)) return;
  var cau = f.getAttribute("data-xac-nhan");
  if (cau && !window.confirm(cau)) e.preventDefault();
});
