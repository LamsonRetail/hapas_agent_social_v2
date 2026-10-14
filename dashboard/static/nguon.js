// Trang Nguồn: tính lại ngay "≈ USD/tháng" khi đổi nền tảng / số bài / chu kỳ trong biểu mẫu
// thêm/sửa nguồn. Hằng số (giá, hệ số, phí khởi động) do máy chủ phát từ dashboard/chi_phi.py —
// cùng công thức trang Ngân sách và lệnh /theodoi của Mark; ở đây không tự đặt giá nào.
"use strict";
(function () {
  var el = document.getElementById("chi-phi-hang-so");
  if (!el) return;
  var hs = JSON.parse(el.textContent || "{}");
  function usd(x, so) {
    return x.toLocaleString("vi-VN", { minimumFractionDigits: so, maximumFractionDigits: so });
  }
  function tinh(form) {
    var p = (form.elements.nen_tang || {}).value;
    var soBai = Math.max(1, parseInt((form.elements.so_bai_moi_lan || {}).value, 10) || 5);
    var chuKy = Math.max(1, parseInt((form.elements.chu_ky_ngay || {}).value, 10) || 1);
    var gia = (hs.gia || {})[p] || 0;
    var donVi = !gia ? 0 : (p === "instagram" ? 1 : soBai);
    var thang = hs.ngay / chuKy * donVi * gia * hs.he_so;
    var chu = "≈ " + usd(thang, 3) + " USD/tháng theo bài";
    var kd = gia ? ((hs.start || {})[p] || 0) * hs.he_so : 0;
    if (kd) chu += " + phí khởi động actor chung " + usd(kd, 4) + " USD mỗi ngày quét";
    var out = form.querySelector(".uoc-tinh");
    if (out) out.textContent = chu;
  }
  document.querySelectorAll("form[data-uoc-tinh]").forEach(function (f) {
    f.addEventListener("input", function () { tinh(f); });
    f.addEventListener("change", function () { tinh(f); });
    tinh(f);
  });
})();
