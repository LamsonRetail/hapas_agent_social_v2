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

// Thanh trang dùng chung (23/10/2026, chủ dự án: mọi bảng dài một kiểu như mẫu ‹ 1 2 3 4 5 6 … ›).
// Cùng markup / lớp với macro `_phan_trang.html` (máy chủ). Hai cách dùng:
//  • tự động: <table data-phan-trang="20"> (hàng trong tbody) hoặc <ul data-phan-trang> (các li) —
//    nạp sẵn hết, chỉ hiện từng trang; thanh trang đặt sau .cuon-ngang bọc bảng. Hàng có
//    [data-loc-an] (bộ lọc của trang ẩn đi) không tính. Bộ lọc đổi hàng xong thì phát sự kiện
//    "phan-trang:lam-moi" lên bảng → về trang 1.
//  • JS tự nạp trang: window.PhanTrang.ve({trang, soTrang, nhan, dem, chon: function (p) {…}}) → <nav>.
(function () {
  function oTrang(t, n) {                       // giống quang_cao.o_trang: null = "…"
    n = Math.max(1, n | 0); t = Math.max(1, Math.min(t | 0, n));
    var r = [], i;
    if (n <= 8) { for (i = 1; i <= n; i++) r.push(i); return r; }
    if (t <= 4) return [1, 2, 3, 4, 5, 6, null, n];
    if (t >= n - 3) { r = [1, null]; for (i = n - 5; i <= n; i++) r.push(i); return r; }
    return [1, null, t - 1, t, t + 1, null, n];
  }
  function so(x) { return Number(x).toLocaleString("vi-VN"); }
  function an(chu) { var s = document.createElement("span"); s.className = "dai-qc__an"; s.textContent = chu; return s; }
  function ve(o) {
    var nav = document.createElement("nav");
    nav.className = "phan-trang";
    nav.setAttribute("aria-label", "Trang của bảng " + (o.nhan || ""));
    if (!o.soTrang || o.soTrang <= 1) { nav.hidden = true; return nav; }
    var ul = document.createElement("ul");
    ul.className = "phan-trang__ds";
    function nut(p, chu, lop, nhanAn) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "phan-trang__o" + (lop ? " " + lop : "");
      if (nhanAn) b.appendChild(an(nhanAn));
      var c = document.createElement("span");
      c.textContent = chu;
      if (nhanAn && lop) c.setAttribute("aria-hidden", "true");
      b.appendChild(c);
      if (p === o.trang && !lop) b.setAttribute("aria-current", "page");
      else if (p < 1 || p > o.soTrang) { b.disabled = true; b.setAttribute("aria-disabled", "true"); }
      else b.addEventListener("click", function () { o.chon(p); });
      return b;
    }
    function li(x, lop) { var l = document.createElement("li"); if (lop) l.className = lop; l.appendChild(x); ul.appendChild(l); }
    li(nut(o.trang - 1, "‹", "phan-trang__ben", "Trang trước"));
    oTrang(o.trang, o.soTrang).forEach(function (p) {
      if (p === null) {
        var s = document.createElement("span");
        s.className = "phan-trang__ba"; s.setAttribute("aria-hidden", "true"); s.textContent = "…";
        li(s, "phan-trang__so");
      } else li(nut(p, so(p), "", "Trang "), "phan-trang__so");
    });
    var g = document.createElement("li");
    g.className = "phan-trang__gon"; g.setAttribute("aria-hidden", "true");
    g.textContent = so(o.trang) + "/" + so(o.soTrang);
    ul.appendChild(g);
    li(nut(o.trang + 1, "›", "phan-trang__ben", "Trang sau"));
    nav.appendChild(ul);
    var d = document.createElement("p");
    d.className = "phan-trang__dem";
    d.textContent = "Trang " + so(o.trang) + "/" + so(o.soTrang) + (o.dem ? " · " + o.dem : "");
    nav.appendChild(d);
    return nav;
  }
  function gan(el) {
    var co = Math.max(1, parseInt(el.getAttribute("data-phan-trang"), 10) || 20);
    var neo = el.closest(".cuon-ngang") || el;
    var nav = null, trang = 1;
    function hang() {
      var goc = el.tagName === "TABLE" ? (el.tBodies[0] || el) : el;
      return Array.prototype.filter.call(goc.children, function (r) {
        return (r.tagName === "TR" || r.tagName === "LI") && !r.hasAttribute("data-loc-an");
      });
    }
    function ve_lai(cuon) {
      var ds = hang(), n = Math.max(1, Math.ceil(ds.length / co));
      trang = Math.min(trang, n);
      var goc = el.tagName === "TABLE" ? (el.tBodies[0] || el) : el;
      Array.prototype.forEach.call(goc.children, function (r) { if (r.hasAttribute("data-loc-an")) r.hidden = true; });
      ds.forEach(function (r, i) { r.hidden = Math.floor(i / co) + 1 !== trang; });
      var moi = ve({ trang: trang, soTrang: n, nhan: el.getAttribute("data-phan-trang-nhan") || "",
                     dem: so(ds.length) + " dòng", chon: function (p) { trang = p; ve_lai(true); } });
      if (nav) nav.replaceWith(moi); else neo.after(moi);
      nav = moi;
      if (cuon) {
        var r = neo.getBoundingClientRect();
        if (r.top < 0) neo.scrollIntoView({ block: "start" });
        var cur = nav.querySelector('[aria-current="page"]');
        if (cur) cur.focus({ preventScroll: true });
      }
    }
    el.addEventListener("phan-trang:lam-moi", function () { trang = 1; ve_lai(false); });
    ve_lai(false);
  }
  window.PhanTrang = { ve: ve, oTrang: oTrang };
  function batDau() { Array.prototype.forEach.call(document.querySelectorAll("[data-phan-trang]"), gan); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", batDau);
  else batDau();
})();
