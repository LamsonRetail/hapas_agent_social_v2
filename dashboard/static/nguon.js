// Trang Nguồn: tính lại ngay "≈ USD/tháng" khi đổi nền tảng / số bài / chu kỳ trong biểu mẫu
// thêm/sửa nguồn. Hằng số (giá, phí khởi động) do máy chủ phát từ dashboard/chi_phi.py — cùng
// công thức `chi_phi.chi_phi_thang_nguon` (KỲ VỌNG, 18/10/2026: không nhân hệ số 1,3 — actor theo
// dõi tính đúng số đơn vị; hệ số chỉ còn ở mức tối đa của Mark); ở đây không tự đặt giá nào.
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
    // = chi_phi.don_vi_ky_vong: Instagram, Threads (actor hồ sơ, 17/10/2026) tính theo TÀI KHOẢN;
    // TikTok (TikTok API, 18/10/2026) theo YÊU CẦU: 1 hồ sơ + ⌈bài/10⌉ trang.
    function dv(n) {
      return !gia ? 0 : (p === "instagram" || p === "threads" ? 1
        : p === "tiktok" ? 1 + Math.ceil(n / (hs.tt_bai_moi_trang || 10)) : n);
    }
    var donVi = dv(soBai);
    // = chi_phi.so_bai_co_gian + chi_phi_luot_nguon (18/10/2026): nguồn có nhịp đăng đo được
    // (data-nhip = số bài cao nhất một ngày trong 14 ngày) thì Mark co số bài; cứ k ngày lấy đủ một lần.
    var cg = hs.co_gian || {};
    var nhip = form.getAttribute("data-nhip");
    if (gia && nhip != null && (cg.nen_tang || []).indexOf(p) >= 0) {
      var k = Math.max(1, parseInt(form.getAttribute("data-ngay-day-du"), 10) || cg.ngay_day_du);
      var san = parseInt(form.getAttribute("data-san"), 10) || cg.san;
      var m = Math.min(soBai, Math.max(san, Math.ceil(parseInt(nhip, 10) * chuKy * cg.he_so - 1e-9) + cg.du));
      if (m < soBai) donVi = ((k - 1) * dv(m) + donVi) / k;
    }
    var thang = hs.ngay / chuKy * donVi * gia;
    var chu = "≈ " + usd(thang, 3) + " USD/tháng theo bài";
    // = chi_phi.phi_khoi_dong_ngay: actor theo dõi nguồn có phí khởi động riêng (khoi_nguon,
    // 17/10/2026: Facebook thedoor) thì dùng nó, không thì phí của actor tìm (start).
    var kn = hs.khoi_nguon || {};
    var kd = gia ? (kn[p] != null ? kn[p] : ((hs.start || {})[p] || 0)) : 0;
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
