// Dùng chung mọi trang. CSP cấm script nội dòng (onclick=…), nên hỏi xác nhận gắn ở đây:
// biểu mẫu có data-xac-nhan="câu hỏi" thì hỏi trước khi gửi (xoá nguồn, xoá người xem…).
"use strict";
document.addEventListener("submit", function (e) {
  var f = e.target;
  if (!(f instanceof HTMLFormElement)) return;
  var cau = f.getAttribute("data-xac-nhan");
  if (cau && !window.confirm(cau)) e.preventDefault();
});

// Nút ⓘ (.goi-y[data-goi-y]): chữ giải thích hiện trong bóng nổi khi rê chuột / Tab tới / chạm —
// trang chỉ giữ tiêu đề ngắn, ghi chú dài nằm ở đây (16/10/2026: "ghi chú tối thiểu"). Bóng nổi
// position: fixed, kẹp trong khung nhìn; chữ chỉ đi qua textContent. Trang Chỉ số tự lo nút
// .cs-goi-y của nó (chi_so.js) nên bỏ qua ở đây.
(function () {
  var noi = null, cua = null;
  function an() {
    if (!noi || !cua) return;
    noi.hidden = true;
    cua.setAttribute("aria-expanded", "false");
    cua = null;
  }
  function hien(b) {
    if (!noi) {
      noi = document.createElement("div");
      noi.className = "noi";
      noi.setAttribute("role", "tooltip");
      noi.hidden = true;
      document.body.appendChild(noi);
    }
    if (cua && cua !== b) an();
    noi.textContent = b.getAttribute("data-goi-y") || "";
    noi.hidden = false;
    cua = b;
    b.setAttribute("aria-expanded", "true");
    var r = b.getBoundingClientRect(), w = noi.offsetWidth, h = noi.offsetHeight;
    var vw = document.documentElement.clientWidth, vh = window.innerHeight;
    var x = Math.max(8, Math.min(vw - w - 8, r.left + r.width / 2 - w / 2));
    var y = r.top - h - 8;
    if (y < 8) y = r.bottom + 8;
    if (y + h > vh - 8) y = Math.max(8, vh - h - 8);
    noi.style.left = Math.round(x) + "px";
    noi.style.top = Math.round(y) + "px";
  }
  function gan(b) {
    var vuaHien = 0;
    b.setAttribute("aria-label", (b.getAttribute("aria-label") || "Giải thích") + ": " + (b.getAttribute("data-goi-y") || ""));
    b.setAttribute("aria-expanded", "false");
    b.addEventListener("mouseenter", function () { vuaHien = Date.now(); hien(b); });
    b.addEventListener("mouseleave", an);
    b.addEventListener("focus", function () { vuaHien = Date.now(); hien(b); });
    b.addEventListener("blur", an);
    b.addEventListener("click", function () {
      if (Date.now() - vuaHien < 400) return;            // chạm trên điện thoại: vừa hiện thì giữ
      if (cua === b) an(); else hien(b);
    });
  }
  function batDau() {
    Array.prototype.forEach.call(document.querySelectorAll(".goi-y[data-goi-y]:not(.cs-goi-y)"), gan);
  }
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") an(); });
  window.addEventListener("scroll", an, { passive: true });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", batDau);
  else batDau();
})();
