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
    // = chi_phi.don_vi_nguon: Instagram, Threads (actor hồ sơ, 17/10/2026) tính theo TÀI KHOẢN;
    // TikTok (TikTok API, 18/10/2026) theo YÊU CẦU: 1 hồ sơ + ⌈bài/10⌉ trang + 1 trang bù bài ghim.
    var donVi = !gia ? 0 : (p === "instagram" || p === "threads" ? 1
      : p === "tiktok" ? 2 + Math.ceil(soBai / (hs.tt_bai_moi_trang || 10)) : soBai);
    var thang = hs.ngay / chuKy * donVi * gia * hs.he_so;
    var chu = "≈ " + usd(thang, 3) + " USD/tháng theo bài";
    // = chi_phi.phi_khoi_dong_ngay: actor theo dõi nguồn có phí khởi động riêng (khoi_nguon,
    // 17/10/2026: Facebook thedoor) thì dùng nó, không thì phí của actor tìm (start).
    var kn = hs.khoi_nguon || {};
    var kd = gia ? (kn[p] != null ? kn[p] : ((hs.start || {})[p] || 0)) * hs.he_so : 0;
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
