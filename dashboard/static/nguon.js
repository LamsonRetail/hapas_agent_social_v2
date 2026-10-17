// Trang Nguồn: tính lại ngay "≈ USD/tháng" khi đổi nền tảng / số bài / chu kỳ trong biểu mẫu
// thêm/sửa nguồn. Hằng số (giá, phí khởi động) do máy chủ phát từ dashboard/chi_phi.py — cùng
// công thức `chi_phi.chi_phi_thang_nguon` (KỲ VỌNG, 18/10/2026: không nhân hệ số 1,3 — actor theo
// dõi tính đúng số đơn vị; hệ số chỉ còn ở mức tối đa của Mark); ở đây không tự đặt giá nào.
"use strict";
(function () {
  var el = document.getElementById("chi-phi-hang-so");
  var hs = {};
  try { hs = JSON.parse((el && el.textContent) || "{}"); } catch (e) { hs = {}; }
  function usd(x, so) {
    return x.toLocaleString("vi-VN", { minimumFractionDigits: so, maximumFractionDigits: so });
  }
  // = chi_phi.don_vi_ky_vong: Instagram, Threads (actor hồ sơ, 17/10/2026) tính theo TÀI KHOẢN;
  // TikTok (TikTok API, 18/10/2026) theo YÊU CẦU: 1 hồ sơ + ⌈bài/10⌉ trang.
  function donVi(p, n) {
    var gia = (hs.gia || {})[p] || 0;
    return !gia ? 0 : (p === "instagram" || p === "threads" ? 1
      : p === "tiktok" ? 1 + Math.ceil(n / (hs.tt_bai_moi_trang || 10)) : n);
  }
  // USD/tháng THEO BÀI (KỲ VỌNG) của một nguồn = chi_phi.chi_phi_thang_nguon, chưa gồm phí khởi
  // động. Dùng cho ô "≈" khi sửa nguồn VÀ thanh duyệt đề xuất hàng loạt (18/10/2026).
  // `co` (tuỳ chọn, = chi_phi.so_bai_co_gian + chi_phi_luot_nguon, 18/10/2026): nguồn có nhịp đăng
  // đo được (nhip = số bài cao nhất một ngày trong 14 ngày) thì Mark co số bài; cứ k ngày lấy đủ
  // một lần. Đề xuất mới chưa có nhịp đăng: không co.
  function thangTheoBai(p, soBai, chuKy, co) {
    var gia = (hs.gia || {})[p] || 0;
    var dv = donVi(p, soBai);
    var cg = hs.co_gian || {};
    if (gia && co && co.nhip != null && (cg.nen_tang || []).indexOf(p) >= 0) {
      var k = Math.max(1, parseInt(co.k, 10) || cg.ngay_day_du);
      var san = parseInt(co.san, 10) || cg.san;
      var m = Math.min(soBai, Math.max(san, Math.ceil(parseInt(co.nhip, 10) * chuKy * cg.he_so - 1e-9) + cg.du));
      // TikTok tính theo TRANG: tròn lên bội số cỡ trang, không dưới một trang (= so_bai_co_gian).
      var tr = hs.tt_bai_moi_trang || 10;
      if (p === "tiktok") m = Math.min(soBai, Math.max(1, Math.ceil(m / tr)) * tr);
      if (m < soBai) dv = ((k - 1) * donVi(p, m) + dv) / k;
    }
    return (hs.ngay || 30) / chuKy * dv * gia;
  }
  function tinh(form) {
    var p = (form.elements.nen_tang || {}).value;
    var soBai = Math.max(1, parseInt((form.elements.so_bai_moi_lan || {}).value, 10) || 5);
    var chuKy = Math.max(1, parseInt((form.elements.chu_ky_ngay || {}).value, 10) || 1);
    var gia = (hs.gia || {})[p] || 0;
    var thang = thangTheoBai(p, soBai, chuKy, {
      nhip: form.getAttribute("data-nhip"), k: form.getAttribute("data-ngay-day-du"),
      san: form.getAttribute("data-san")
    });
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

  // ── Đề xuất chờ duyệt (18/10/2026): lọc nền tảng, sắp xếp, 50 dòng/trang, chọn nhiều + hàng loạt ──
  // Chủ dự án: "chờ duyệt thì có thể là chọn nhiều người 1 lúc hoặc chọn tất cả chứ ko chọn từng
  // người 1 mất thời gian". "Chọn tất cả" = các dòng ĐANG XEM (lọc + trang); nút phụ chọn cả mọi
  // dòng khớp bộ lọc. Đổi bộ lọc thì bỏ chọn dòng không còn khớp — không duyệt nhầm dòng đang ẩn.
  var than = document.querySelector("[data-dx-than]");
  if (!than) return;
  var MOI_TRANG = 50;
  var dong = Array.prototype.slice.call(than.querySelectorAll("tr[data-dx]"));
  var loc = document.querySelector("[data-dx-loc]");
  var chonNt = document.querySelector("[data-dx-nen-tang]");
  var chonSap = document.querySelector("[data-dx-sap]");
  var dem = document.querySelector("[data-dx-dem]");
  var phan = document.querySelector("[data-dx-trang]");
  var thanh = document.querySelector("[data-dx-thanh]");
  var oTrang = document.querySelector("[data-dx-chon-trang]");
  var trang = 0;
  var chon = {};                     // id -> true
  var khop = dong;                   // dòng khớp bộ lọc, đã sắp xếp
  if (loc) loc.hidden = false;
  if (thanh) {
    thanh.hidden = false;
    document.querySelectorAll(".dx-o-chon").forEach(function (o) { o.hidden = false; });
  }
  function so(tr, k) { return parseFloat(tr.getAttribute(k)) || 0; }
  function dangXem() {
    return khop.slice(trang * MOI_TRANG, (trang + 1) * MOI_TRANG);
  }
  function soChon() { return Object.keys(chon).length; }
  function uocThem() {               // USD/tháng thêm nếu duyệt mọi dòng đã chọn
    if (!thanh) return 0;
    var soBai = Math.max(1, parseInt(thanh.elements.so_bai_moi_lan.value, 10) || 5);
    var chuKy = Math.max(1, Math.min(30, parseInt(thanh.elements.chu_ky_ngay.value, 10) || 1));
    return dong.reduce(function (t, tr) {
      return chon[tr.getAttribute("data-dx")] ? t + thangTheoBai(tr.getAttribute("data-nt"), soBai, chuKy) : t;
    }, 0);
  }
  function veThanh() {
    if (!thanh) return;
    var n = soChon();
    thanh.querySelector("[data-dx-so-chon]").textContent = n;
    thanh.querySelector("[data-dx-uoc]").textContent = n ? "≈ " + usd(uocThem(), 2) + " USD/tháng thêm" : "≈ 0 USD/tháng";
    thanh.querySelectorAll("[data-dx-nut]").forEach(function (b) { b.disabled = !n; });
    thanh.querySelector("[data-dx-bo-chon]").hidden = !n;
    var het = thanh.querySelector("[data-dx-chon-het]");
    var conLai = khop.filter(function (tr) { return !chon[tr.getAttribute("data-dx")]; }).length;
    het.hidden = !(khop.length > MOI_TRANG && conLai > 0 && n > 0);
    het.textContent = "Chọn cả " + khop.length + " đề xuất khớp bộ lọc";
    thanh.classList.toggle("dx-thanh--co", n > 0);
    if (oTrang) {
      var xem = dangXem();
      var daChon = xem.filter(function (tr) { return chon[tr.getAttribute("data-dx")]; }).length;
      oTrang.checked = xem.length > 0 && daChon === xem.length;
      oTrang.indeterminate = daChon > 0 && daChon < xem.length;
      oTrang.setAttribute("aria-label", "Chọn tất cả " + xem.length + " đề xuất đang xem");
    }
  }
  function ve() {
    var soTrang = Math.max(1, Math.ceil(khop.length / MOI_TRANG));
    trang = Math.min(trang, soTrang - 1);
    var hien = {};
    dangXem().forEach(function (tr) { hien[tr.getAttribute("data-dx")] = true; });
    khop.forEach(function (tr) { than.appendChild(tr); });     // thứ tự sắp xếp
    dong.forEach(function (tr) {
      var id = tr.getAttribute("data-dx");
      tr.hidden = !hien[id];
      var o = tr.querySelector("[data-dx-chon]");
      if (o) o.checked = !!chon[id];
    });
    var a = khop.length ? trang * MOI_TRANG + 1 : 0;
    var b = Math.min(khop.length, (trang + 1) * MOI_TRANG);
    if (dem) dem.textContent = "Đang xem " + a + "–" + b + " / " + khop.length + " đề xuất";
    if (phan) {
      phan.hidden = soTrang <= 1;
      phan.querySelector("[data-dx-trang-so]").textContent = "Trang " + (trang + 1) + "/" + soTrang;
      phan.querySelector("[data-dx-lui]").disabled = trang <= 0;
      phan.querySelector("[data-dx-toi]").disabled = trang >= soTrang - 1;
    }
    veThanh();
  }
  function locLai() {
    var nt = chonNt ? chonNt.value : "";
    var sap = chonSap ? chonSap.value : "thao_luan";
    var khoa = { thao_luan: "data-thao-luan", so_bai: "data-so-bai", moi: "data-luc" }[sap] || "data-thao-luan";
    khop = dong.filter(function (tr) { return !nt || tr.getAttribute("data-nt") === nt; });
    // giảm dần theo khoá, hoà thì giữ thứ tự máy chủ (thảo luận rồi mới nhất)
    khop.sort(function (x, y) { return so(y, khoa) - so(x, khoa) || so(x, "data-thu-tu") - so(y, "data-thu-tu"); });
    var con = {};
    khop.forEach(function (tr) { con[tr.getAttribute("data-dx")] = true; });
    Object.keys(chon).forEach(function (id) { if (!con[id]) delete chon[id]; });
    trang = 0;
    ve();
  }
  if (chonNt) chonNt.addEventListener("change", locLai);
  if (chonSap) chonSap.addEventListener("change", locLai);
  if (phan) {
    phan.querySelector("[data-dx-lui]").addEventListener("click", function () { trang -= 1; ve(); });
    phan.querySelector("[data-dx-toi]").addEventListener("click", function () { trang += 1; ve(); });
  }
  than.addEventListener("change", function (e) {
    var o = e.target;
    if (!o.matches || !o.matches("[data-dx-chon]")) return;
    if (o.checked) chon[o.value] = true; else delete chon[o.value];
    veThanh();
  });
  if (oTrang) {
    oTrang.addEventListener("change", function () {
      dangXem().forEach(function (tr) {
        var id = tr.getAttribute("data-dx");
        if (oTrang.checked) chon[id] = true; else delete chon[id];
      });
      ve();
    });
  }
  if (thanh) {
    thanh.querySelector("[data-dx-chon-het]").addEventListener("click", function () {
      khop.forEach(function (tr) { chon[tr.getAttribute("data-dx")] = true; });
      ve();
    });
    thanh.querySelector("[data-dx-bo-chon]").addEventListener("click", function () {
      chon = {};
      ve();
    });
    thanh.addEventListener("input", veThanh);
    // Bấm nút: ghi câu hỏi xác nhận (chung.js hỏi lúc gửi) + gom id đã chọn vào ô ẩn `ids`.
    thanh.querySelectorAll("[data-dx-nut]").forEach(function (b) {
      b.addEventListener("click", function () {
        var n = soChon();
        thanh.setAttribute("data-xac-nhan", b.value === "tu_choi"
          ? "Từ chối " + n + " đề xuất đã chọn? Các nguồn này sẽ không hiện lại trong danh sách chờ."
          : "Duyệt " + n + " đề xuất thành nguồn theo dõi (" + thanh.elements.so_bai_moi_lan.value +
            " bài mỗi " + thanh.elements.chu_ky_ngay.value + " ngày, ≈ " + usd(uocThem(), 2) +
            " USD/tháng thêm)?");
      });
    });
    thanh.addEventListener("submit", function () {
      thanh.querySelector("[data-dx-ids]").value = Object.keys(chon).join(",");
    });
  }
  locLai();
})();
