// Trang "Quảng cáo" (TikTok 19/10/2026, + Meta 20/10/2026): vẽ biểu đồ "Theo ngày" từ #qc-api = ĐÚNG
// payload của GET /api/qc (đã lọc tiền theo quyền ở máy chủ; theo_ngay_nen_tang có `nen_tang`).
// Xem "Tất cả" mà phạm vi có cả TikTok lẫn Meta → cột chồng theo nền tảng (màu nền tảng, cùng màu thanh
// tỉ trọng + chấm ở bảng); một nền tảng → đường vùng một màu như trước. Điện thoại: gập sẵn bộ lọc để
// số lên màn hình đầu. Không gọi API, không chèn HTML từ dữ liệu (CSP script-src 'self'; chữ chỉ qua
// textContent). Màu đọc từ biến CSS → sáng/tối tự theo.
// 22/10/2026 (chủ dự án): thêm "Xem trang SP TikTok Shop" / "Xem SP website (Meta)" (`chuoi_xem_sp` của
// payload, chỉ chuỗi có số trong phạm vi) — mỗi chuỗi thuộc MỘT nền tảng nên luôn là đường một màu của
// nền tảng đó, không chồng, không cộng; chú giải dưới tiêu đề ghi rõ định nghĩa.
// 25/10/2026 (chủ dự án): gộp theo ngày / tuần / tháng — máy chủ gộp sẵn (`theo_ky`, quang_cao.gop_ky),
// ở đây chỉ chọn chuỗi theo nút "Ngày · Tuần · Tháng" (mặc định theo độ dài khoảng, không nhớ).
"use strict";
(function () {
  // Bộ lọc gập trên điện thoại (máy tính luôn mở; dòng tóm tắt chỉ hiện ≤ 640px — qc.css, 25/10/2026).
  var loc = document.getElementById("qc-loc");
  var hep = window.matchMedia ? window.matchMedia("(max-width: 640px)") : null;
  if (loc && hep && hep.matches) loc.open = false;
  // Cửa sổ hẹp → rộng: dòng tóm tắt bị ẩn ở máy tính, bộ lọc đang gập sẽ biến mất → mở lại.
  if (loc && hep && hep.addEventListener) hep.addEventListener("change", function () { if (!hep.matches) loc.open = true; });

  var CHUOI = [["chi", "Chi tiêu"], ["hien_thi", "Hiển thị"], ["click", "Click"], ["view_video", "View video"],
               ["engaged_view", "Engaged view"], ["tuong_tac", "Tương tác"], ["follow", "Follow"]];
  var TEN_NEN = { tiktok: "TikTok", meta: "Meta" };
  var api = document.getElementById("qc-api");
  var khung = document.getElementById("qc-bd-ngay");
  var nhom = document.getElementById("qc-chon-chi-so");
  var chuGiai = document.getElementById("qc-chu-giai");
  if (!api || !khung || !nhom || !window.echarts) return;
  var p;
  try { p = JSON.parse(api.textContent || "{}"); } catch (e) { return; }
  var ds = p.theo_ngay || [];
  if (!ds.length) return;
  var co = ds[0];
  var chuoi = CHUOI.filter(function (c) { return c[0] in co; });
  if (!chuoi.length) return;
  var ky = p.theo_ky || {};
  var DON_VI = { ngay: "Ngày", tuan: "Tuần", thang: "Tháng" };
  var coDonVi = (ky.co || ["ngay"]).filter(function (k) { return k === "ngay" || ky[k]; });
  var donVi = coDonVi.indexOf(ky.mac_dinh) >= 0 ? ky.mac_dinh : "ngay";
  var nhomDv = document.getElementById("qc-don-vi");
  var tieuDeDv = document.getElementById("qc-xh-don-vi");
  // Chuỗi của đơn vị đang chọn: ds (dòng chung), ngay (khoá trục), nhan (khoá → dòng — nhãn tuần / tháng),
  // theoNen: { tiktok: {khoá: dòng}, meta: {...} } — chỉ dùng khi xem "Tất cả" và có ≥ 2 nền tảng.
  var ngay, theoNen, dongKy;
  function napDuLieu() {
    var x = donVi === "ngay" ? { chung: p.theo_ngay || [], nen_tang: p.theo_ngay_nen_tang || [] } : ky[donVi];
    ds = x.chung || [];
    ngay = ds.map(function (r) { return r.ngay; });
    dongKy = {};
    ds.forEach(function (r) { dongKy[r.ngay] = r; });
    theoNen = {};
    (x.nen_tang || []).forEach(function (r) { (theoNen[r.nen_tang] = theoNen[r.nen_tang] || {})[r.ngay] = r; });
  }
  napDuLieu();
  var nenNgay = {};
  (p.theo_ngay_nen_tang || []).forEach(function (r) { nenNgay[r.nen_tang] = true; });
  var cacNen = (p.theo_nen_tang || []).map(function (n) { return n.nen_tang; }).filter(function (n) { return nenNgay[n]; });
  // Chuỗi riêng một nền tảng: [mã, nhãn, nền tảng, định nghĩa] — chỉ khi nền tảng đó có trong phạm vi.
  var coNen = (p.theo_nen_tang || []).map(function (n) { return n.nen_tang; });
  (p.chuoi_xem_sp || []).forEach(function (c) {
    if (c.ma in co && coNen.indexOf(c.nen_tang) >= 0) chuoi.push([c.ma, c.ten, c.nen_tang, c.dinh_nghia]);
  });
  var chong = p.nen_tang === "tat_ca" && cacNen.length > 1;

  var giamDong = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var SO = new Intl.NumberFormat("vi-VN");
  var chon = chuoi[0][0];
  try { var luu = window.localStorage.getItem("qc-chi-so"); if (luu && chuoi.some(function (c) { return c[0] === luu; })) chon = luu; } catch (e) { /* bỏ qua */ }
  var bd = null;

  function bien(ten) { return getComputedStyle(document.documentElement).getPropertyValue(ten).trim(); }
  // 26/10/2026 (chủ dự án: "không viết tắt nữa"): số ĐẦY ĐỦ có chấm nghìn, không "tỷ" / "tr" / "N".
  function soGon(n) { return n == null ? "—" : SO.format(Math.round(n)); }
  function ngayNgan(iso) { return iso.slice(8, 10) + "/" + iso.slice(5, 7); }
  function ngayDu(iso) { return iso.split("-").reverse().join("/"); }
  // Nhãn trục: ngày "23/10"; tuần "Tuần 20/10"; tháng "Tháng 10/2026" (máy chủ đặt `nhan`).
  function nhanTruc(k) { var r = dongKy[k]; return donVi === "ngay" || !r ? ngayNgan(k) : r.nhan; }
  function nhanDu(k) {
    var r = dongKy[k];
    if (donVi === "ngay" || !r) return ngayDu(k);
    var cuoiThang = new Date(+r.ngay.slice(0, 4), +r.ngay.slice(5, 7), 0).getDate();
    var thieu = r.so_ngay < (donVi === "tuan" ? 7 : cuoiThang);
    return r.nhan + " (" + ngayNgan(r.ngay) + " – " + ngayNgan(r.den) + (thieu ? ", " + r.so_ngay + " ngày trong khoảng" : "") + ")";
  }
  function hexRgba(hex, a) {
    var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
    return m ? "rgba(" + parseInt(m[1], 16) + "," + parseInt(m[2], 16) + "," + parseInt(m[3], 16) + "," + a + ")" : hex;
  }
  function donVi(ma) {
    if (ma !== "chi") return "";
    var tt = p.tien_te || ["VND"];
    return tt.length === 1 && tt[0] !== "VND" ? " " + tt[0] : " ₫";
  }
  function giaTri(r, ma) { return r ? (r[ma] || 0) : 0; }

  function veNut() {
    while (nhom.firstChild) nhom.removeChild(nhom.firstChild);
    chuoi.forEach(function (c) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "qc-phan__nut";
      b.textContent = c[1];
      if (c[3]) b.title = c[3];
      b.setAttribute("aria-pressed", c[0] === chon ? "true" : "false");
      b.addEventListener("click", function () {
        if (chon === c[0]) return;
        chon = c[0];
        try { window.localStorage.setItem("qc-chi-so", chon); } catch (e) { /* bỏ qua */ }
        Array.prototype.forEach.call(nhom.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        ve();
      });
      nhom.appendChild(b);
    });
  }

  function veDonVi() {
    if (!nhomDv) return;
    while (nhomDv.firstChild) nhomDv.removeChild(nhomDv.firstChild);
    if (coDonVi.length < 2) return;
    coDonVi.forEach(function (k) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "qc-phan__nut";
      b.textContent = DON_VI[k];
      b.setAttribute("aria-pressed", k === donVi ? "true" : "false");
      b.addEventListener("click", function () {
        if (donVi === k) return;
        donVi = k;
        napDuLieu();
        Array.prototype.forEach.call(nhomDv.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        if (tieuDeDv) tieuDeDv.textContent = DON_VI[k].toLowerCase();
        ve();
      });
      nhomDv.appendChild(b);
    });
  }

  function veChuGiai(rieng) {
    if (!chuGiai) return;
    while (chuGiai.firstChild) chuGiai.removeChild(chuGiai.firstChild);
    if (rieng) {
      // Chuỗi một nền tảng: chấm màu nền tảng + định nghĩa luôn hiện (không phải rê chuột mới thấy).
      var li1 = document.createElement("li");
      var ch = document.createElement("span");
      ch.className = "qc-cham qc-cham--" + rieng[2];
      ch.setAttribute("aria-hidden", "true");
      li1.appendChild(ch);
      li1.appendChild(document.createTextNode(rieng[3] || rieng[1]));
      chuGiai.appendChild(li1);
      chuGiai.hidden = false;
      return;
    }
    chuGiai.hidden = !chong;
    if (!chong) return;
    cacNen.forEach(function (n) {
      var li = document.createElement("li");
      var cham = document.createElement("span");
      cham.className = "qc-cham qc-cham--" + n;
      cham.setAttribute("aria-hidden", "true");
      li.appendChild(cham);
      li.appendChild(document.createTextNode(TEN_NEN[n] || n));
      chuGiai.appendChild(li);
    });
  }

  function ve() {
    var c = chuoi.filter(function (x) { return x[0] === chon; })[0] || chuoi[0];
    var ma = c[0], ten = c[1], nenRieng = c[2] || null;
    var xep = chong && !nenRieng;            // cột chồng theo nền tảng — không bao giờ cho chuỗi riêng
    var m = { chu: bien("--chu"), phu: bien("--chu-phu"), mo: bien("--chu-mo"), ke: bien("--ke"),
              truc: bien("--truc"), mat: bien("--be-mat"), phong: bien("--phong") || "system-ui, sans-serif",
              chinh: bien("--s1"), tiktok: bien("--qc-tiktok") || "#111827", meta: bien("--qc-meta") || "#1877f2" };
    if (!bd) bd = window.echarts.init(khung, null, { renderer: "canvas" });
    khung.setAttribute("aria-label", "Biểu đồ " + ten.toLowerCase() + " theo " + DON_VI[donVi].toLowerCase() + (xep ? ", chia theo nền tảng" : "") + ", " + ngay.length + " " + DON_VI[donVi].toLowerCase());
    veChuGiai(nenRieng ? c : null);
    var series;
    if (xep) {
      series = cacNen.map(function (n, i) {
        return {
          name: TEN_NEN[n] || n, type: "bar", stack: "nen", barMaxWidth: 22, barCategoryGap: "28%",
          data: ngay.map(function (x) { return giaTri((theoNen[n] || {})[x], ma); }),
          itemStyle: { color: m[n] || m.chinh, borderRadius: i === cacNen.length - 1 ? [3, 3, 0, 0] : 0 },
          emphasis: { focus: "series" }
        };
      });
    } else {
      // Chuỗi riêng: số của ĐÚNG nền tảng đó (theo_ngay_nen_tang), màu nền tảng.
      var mau = nenRieng ? (m[nenRieng] || m.chinh) : m.chinh;
      var rNen = nenRieng ? theoNen[nenRieng] : null;
      series = [{
        name: ten, type: "line",
        data: ds.map(function (x) { return rNen ? giaTri(rNen[x.ngay], ma) : giaTri(x, ma); }),
        showSymbol: ngay.length <= 45, symbol: "circle", symbolSize: 6,
        smooth: 0.25, smoothMonotone: "x", lineStyle: { width: 2, color: mau },
        itemStyle: { color: mau, borderColor: m.mat, borderWidth: 2 },
        areaStyle: { color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: hexRgba(mau, 0.22) }, { offset: 1, color: hexRgba(mau, 0.02) }]) }
      }];
    }
    bd.setOption({
      animation: !giamDong, animationDuration: 250,
      textStyle: { fontFamily: m.phong, color: m.phu },
      grid: { left: 4, right: 12, top: 16, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis", renderMode: "richText", backgroundColor: m.mat, borderColor: m.ke, borderWidth: 1,
        padding: [8, 12], textStyle: { color: m.chu, fontSize: 12, fontFamily: m.phong },
        axisPointer: xep ? { type: "shadow", shadowStyle: { color: hexRgba(m.truc, 0.25) } }
                           : { type: "line", lineStyle: { color: m.truc, type: "dashed" } },
        formatter: function (ps) {
          var i = ps[0].dataIndex, dong = [nhanDu(ngay[i])], tong = 0;
          ps.forEach(function (x) { tong += x.value || 0; dong.push(x.seriesName + ": " + SO.format(x.value || 0) + donVi(ma)); });
          if (nenRieng) dong.push(nenRieng === "tiktok" ? "(đếm lượt xem, không phải số người)" : "(trên website — không phải Shop)");
          if (xep) dong.push("Cộng: " + SO.format(tong) + donVi(ma));
          return dong.join("\n");
        }
      },
      xAxis: { type: "category", data: ngay, boundaryGap: xep, axisLine: { lineStyle: { color: m.ke } }, axisTick: { show: false },
               axisLabel: { color: m.mo, fontSize: 11, hideOverlap: true, formatter: nhanTruc, margin: 10 } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: m.ke, type: [4, 4] } },
               axisLabel: { color: m.mo, fontSize: 11, formatter: function (v) { return soGon(v); } } },
      series: series
    }, true);
  }

  veNut();
  veDonVi();
  ve();
  var cho = null;
  window.addEventListener("resize", function () {
    if (cho) return;
    cho = window.requestAnimationFrame(function () { cho = null; if (bd) bd.resize(); });
  });
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  if (mq && mq.addEventListener) {
    mq.addEventListener("change", function () { if (bd) { bd.dispose(); bd = null; } ve(); });
  }
})();

// Thanh lọc đầu trang (25/10/2026, chủ dự án: đổi là áp dụng): đổi Bên là gửi luôn; các bảng nổi
// (tài khoản, khoảng ngày, tên chiến dịch) áp dụng bằng nút của nó; nút "Xem" chỉ còn cho trường hợp
// không JS. Gửi: bỏ `ss` mặc định (URL gọn, như liên kết máy chủ dựng).
(function () {
  var f = document.querySelector('form[data-o="thanh-loc"]');
  if (!f) return;
  var xem = f.querySelector("[data-loc-xem]");
  if (xem) xem.hidden = true;
  Array.prototype.forEach.call(f.querySelectorAll("select[data-tu-gui]"), function (s) {
    s.addEventListener("change", function () { if (f.requestSubmit) f.requestSubmit(); else f.submit(); });
  });
  f.addEventListener("submit", function () {
    var ss = f.elements.ss;
    if (ss && ss.value === "truoc") ss.disabled = true;
  });
})();

// Lọc bảng chiến dịch / quảng cáo (22/10/2026): đổi "Xếp theo" / "Thứ tự" là gửi luôn (ô tìm vẫn chờ
// Enter hoặc nút Lọc). Không có JS: nút Lọc vẫn đủ dùng.
(function () {
  var f = document.querySelector('form[data-o="loc-bang"]');
  if (!f) return;
  Array.prototype.forEach.call(f.querySelectorAll("select[data-tu-gui]"), function (s) {
    s.addEventListener("change", function () { f.submit(); });
  });
})();

// Chọn nhiều tài khoản (22/10/2026, chủ dự án): ô "Tài khoản" là danh sách đánh dấu trong <details>
// (không JS vẫn chọn + gửi được). JS thêm: ô tìm (bỏ dấu, không phân biệt hoa thường), "Chọn tất cả /
// Bỏ chọn" (áp vào các dòng đang hiện), dòng tóm tắt "Tất cả tài khoản (N)" / "3 tài khoản" / tên, đóng
// khi bấm ra ngoài hoặc Esc. Gửi khi đã chọn đủ mọi tài khoản → bỏ chọn hết (= tất cả, URL gọn).
(function () {
  var khoi = document.querySelector('[data-o="chon-tk"]');
  if (!khoi) return;
  var khung = khoi.querySelector("details");
  var tom = khoi.querySelector(".qc-tk__gia-tri");
  var congCu = khoi.querySelector("[data-tk-cong-cu]");
  var tim = khoi.querySelector(".qc-tk__tim");
  var trong = khoi.querySelector("[data-tk-trong]");
  var hop = Array.prototype.slice.call(khoi.querySelectorAll('input[type="checkbox"][name="tk"]'));
  if (!khung || !tom || !hop.length) return;
  if (congCu) congCu.hidden = false;

  function boDau(x) {
    return (x || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[đĐ]/g, "d").toLowerCase();
  }
  function ten(h) { var t = h.parentNode.querySelector(".qc-tk__ten"); return t ? t.textContent : h.value; }
  function veTom() {
    var chon = hop.filter(function (h) { return h.checked; });
    tom.textContent = !chon.length || chon.length === hop.length ? tom.getAttribute("data-tat-ca")
      : chon.length === 1 ? ten(chon[0]) : chon.length + " tài khoản";
  }
  function loc() {
    var q = boDau(tim ? tim.value.trim() : "");
    var con = 0;
    hop.forEach(function (h) {
      var hien = !q || boDau(ten(h)).indexOf(q) >= 0 || h.value.indexOf(q) >= 0;
      h.parentNode.hidden = !hien;
      if (hien) con++;
    });
    Array.prototype.forEach.call(khoi.querySelectorAll(".qc-tk__nhom"), function (f) {
      f.hidden = !f.querySelector(".qc-tk__o:not([hidden])");
    });
    if (trong) trong.hidden = con > 0;
  }
  hop.forEach(function (h) { h.addEventListener("change", veTom); });
  if (tim) {
    tim.addEventListener("input", loc);
    // Enter trong ô tìm không gửi cả bộ lọc (người dùng đang lọc danh sách).
    tim.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
  }
  Array.prototype.forEach.call(khoi.querySelectorAll("button[data-tk]"), function (b) {
    b.addEventListener("click", function () {
      var bat = b.getAttribute("data-tk") === "tat-ca";
      hop.forEach(function (h) { if (!h.parentNode.hidden) h.checked = bat; });
      veTom();
    });
  });
  document.addEventListener("click", function (e) { if (khung.open && !khoi.contains(e.target)) khung.open = false; });
  khoi.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && khung.open) { khung.open = false; khung.querySelector("summary").focus(); }
  });
  // 25/10/2026 (chủ dự án: thanh lọc đổi là áp dụng): đóng bảng mà lựa chọn đã khác lúc mở → gửi luôn.
  var f = khoi.closest("form");
  function dau() { return hop.map(function (h) { return h.checked ? "1" : "0"; }).join(""); }
  var luc = dau();
  khung.addEventListener("toggle", function () {
    if (khung.open) { luc = dau(); if (tim) tim.focus(); return; }
    if (f && dau() !== luc) { if (f.requestSubmit) f.requestSubmit(); else f.submit(); }
  });
  if (f) f.addEventListener("submit", function () {
    if (hop.every(function (h) { return h.checked; })) hop.forEach(function (h) { h.checked = false; });
  });
})();

// Xuất Lark Sheet (20/10/2026; 22/10/2026 nằm trong mục "Chiến dịch và quảng cáo"): còn yêu cầu đang chờ / đang tạo → hỏi lại /api/qc/sheet mỗi 5 giây (tối
// đa 15 phút, tab ẩn thì thôi hỏi) và vẽ lại danh sách bằng textContent; hết yêu cầu đang tạo (hoặc hết
// 15 phút) thì mở lại nút "Xuất Lark Sheet". Không có JS: trang vẫn đúng, tải lại là thấy trạng thái mới.
(function () {
  var khung = document.getElementById("sheet");
  var ds = document.getElementById("qc-sheet-ds");
  var nut = document.getElementById("qc-sheet-nut");
  var goiY = document.getElementById("qc-sheet-goi-y");
  if (!khung || !ds || khung.getAttribute("data-dang") !== "1" || !window.fetch) return;
  var batDau = Date.now();
  var NHIP = 5000, TOI_DA = 15 * 60 * 1000;

  function the(ten, lop, chu) {
    var x = document.createElement(ten);
    if (lop) x.className = lop;
    if (chu != null) x.textContent = chu;
    return x;
  }
  function veO(x) {
    var li = the("li", "qc-sheet__o");
    li.setAttribute("data-id", String(x.id));
    li.setAttribute("data-tinh-trang", x.trang_thai);
    li.appendChild(the("span", "qc-sheet__ten", x.ten));
    var meta = the("span", "qc-sheet__meta");
    meta.appendChild(the("span", "qc-sheet__tt qc-sheet__tt--" + x.trang_thai, x.nhan));
    meta.appendChild(the("span", "qc-sheet__luc", x.luc));
    li.appendChild(meta);
    if (x.url && /^https:\/\//.test(x.url)) {
      var ket = the("span", "qc-sheet__ket");
      var a = the("a", "qc-sheet__mo", "Mở Sheet");
      a.href = x.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      ket.appendChild(a);
      if (x.so_dong) ket.appendChild(the("span", "qc-sheet__phu", x.so_dong));
      li.appendChild(ket);
    }
    if (x.loi) li.appendChild(the("span", "qc-sheet__loi" + (x.trang_thai === "xong" ? " qc-sheet__loi--canh" : ""), x.loi));
    return li;
  }
  function hoi() {
    if (document.hidden) { setTimeout(hoi, NHIP); return; }
    fetch("/api/qc/sheet", { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (p) {
        if (!p || !p.ds) return;
        while (ds.firstChild) ds.removeChild(ds.firstChild);
        p.ds.forEach(function (x) { ds.appendChild(veO(x)); });
        if (!p.dang) {
          khung.setAttribute("data-dang", "0");
          if (nut) nut.disabled = false;
          if (goiY) { goiY.textContent = ""; goiY.hidden = true; }   // 23/10/2026: gợi ý thời gian nằm ở (i)
          return true;
        }
      })
      .catch(function () { /* mạng chập chờn: lượt sau hỏi lại */ })
      .then(function (xong) {
        if (xong) return;
        if (Date.now() - batDau < TOI_DA) { setTimeout(hoi, NHIP); return; }
        // Hết 15 phút mà vẫn đang tạo: thôi hỏi, mở lại nút (máy chủ vẫn chặn nếu còn đang chờ thật).
        if (nut) nut.disabled = false;
        if (goiY) { goiY.textContent = "Chưa thấy xong — tải lại trang để xem trạng thái mới."; goiY.hidden = false; }
      });
  }
  setTimeout(hoi, NHIP);
})();

// Tên chiến dịch bản 2 (23/10/2026, MKT — "như Meta Ads Manager"): bảng ba dòng trong <details> (chứa tất
// cả / chứa một trong / không chứa — AND). Không JS: mỗi dòng là ô chữ, dấu phẩy tách từ khoá. JS biến mỗi
// dòng thành ô thẻ: Enter hoặc dấu phẩy → thẻ ✕; Backspace ở ô trống xoá thẻ cuối; thẻ gửi thành ô ẩn lặp
// lại (cd_co=…&cd_co=…). Gõ → gợi ý tên chiến dịch thật + đoạn tên hay gặp của kỳ / phạm vi đang chọn
// (/api/qc/ten-cd, chờ 250 ms); chọn gợi ý thêm đúng chữ đó thành thẻ. Dòng tóm tắt "2 điều kiện". Chữ chỉ
// qua textContent (CSP, không chèn HTML từ dữ liệu). Máy chủ kiểm lại mọi trần (quang_cao.loc_ten_cd).
(function () {
  var khoi = document.querySelector('[data-o="loc-ten-cd"]');
  if (!khoi) return;
  var khung = khoi.querySelector("details");
  var tom = khoi.querySelector("#qc-tcd-gia-tri");
  var f = khoi.closest("form");
  if (!khung || !tom || !f) return;
  var TOI_DA = 10, DAI = 60;
  var cacDong = [];
  var soGoiY = 0;

  function boDau(x) {
    return (x || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[đĐ]/g, "d").toLowerCase().replace(/[^a-z0-9]/g, "");
  }
  function veTom() {
    var n = cacDong.filter(function (d) { return d.ds.length; }).length;
    tom.textContent = n ? n + " điều kiện" : tom.getAttribute("data-trong");
  }

  function dung(hang) {
    var ten = hang.getAttribute("data-tcd");
    var o = hang.querySelector(".qc-tcd__o");
    var go = hang.querySelector(".qc-tcd__go");
    if (!o || !go) return;
    var d = { ten: ten, o: o, go: go, ds: [] };
    var nhan = (hang.querySelector("label") || {}).textContent || "";
    // Danh sách gợi ý (listbox) gắn vào ô; chọn bằng phím lên / xuống + Enter, hoặc bấm.
    var ds = document.createElement("ul");
    ds.className = "qc-tcd__ds";
    ds.id = "qc-tcd-ds-" + ten;
    ds.setAttribute("role", "listbox");
    ds.setAttribute("aria-label", "Gợi ý cho " + nhan);
    ds.hidden = true;
    o.appendChild(ds);
    go.setAttribute("role", "combobox");
    go.setAttribute("aria-autocomplete", "list");
    go.setAttribute("aria-expanded", "false");
    go.setAttribute("aria-controls", ds.id);
    var dangChon = -1, cho = null, luot = 0;

    function veThe() {
      Array.prototype.forEach.call(o.querySelectorAll(".qc-tcd__the"), function (x) { o.removeChild(x); });
      d.ds.forEach(function (kw, i) {
        var t = document.createElement("span");
        t.className = "qc-tcd__the";
        var c = document.createElement("span");
        c.className = "qc-tcd__the-chu";
        c.textContent = kw;
        var b = document.createElement("button");
        b.type = "button";
        b.className = "qc-tcd__the-bo";
        b.textContent = "✕";
        b.setAttribute("aria-label", "Bỏ từ khoá " + kw);
        b.addEventListener("click", function () { d.ds.splice(i, 1); veThe(); go.focus(); });
        var an = document.createElement("input");
        an.type = "hidden"; an.name = ten; an.value = kw;
        t.appendChild(c); t.appendChild(b); t.appendChild(an);
        o.insertBefore(t, go);
      });
      go.placeholder = d.ds.length ? "" : "Nhập tên hoặc từ khoá";
      veTom();
    }
    function them(chu) {
      String(chu || "").split(/[,;]/).forEach(function (x) {
        var kw = x.replace(/\s+/g, " ").trim().slice(0, DAI).trim();
        if (!kw || d.ds.length >= TOI_DA) return;
        var k = boDau(kw) || kw.toLowerCase();
        if (d.ds.some(function (y) { return (boDau(y) || y.toLowerCase()) === k; })) return;
        d.ds.push(kw);
      });
      veThe();
    }
    function dongDs() {
      ds.hidden = true; dangChon = -1;
      go.setAttribute("aria-expanded", "false");
      go.removeAttribute("aria-activedescendant");
    }
    function danhDau(i) {
      var cac = ds.querySelectorAll('[role="option"]');
      if (!cac.length) return;
      dangChon = (i + cac.length) % cac.length;
      Array.prototype.forEach.call(cac, function (x, j) { x.setAttribute("aria-selected", j === dangChon ? "true" : "false"); });
      go.setAttribute("aria-activedescendant", cac[dangChon].id);
      cac[dangChon].scrollIntoView({ block: "nearest" });
    }
    function chon(chu) { them(chu); go.value = ""; dongDs(); go.focus(); }
    function veGoiY(q, p) {
      while (ds.firstChild) ds.removeChild(ds.firstChild);
      var muc = [["Thêm từ khoá", q]];
      (p.tu_khoa || []).forEach(function (x) { muc.push(["Đoạn tên", x]); });
      (p.ten || []).forEach(function (x) { muc.push(["Chiến dịch", x]); });
      muc.forEach(function (m) {
        var li = document.createElement("li");
        li.className = "qc-tcd__goi";
        li.id = "qc-tcd-goi-" + (++soGoiY);
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        var a = document.createElement("span"); a.className = "qc-tcd__goi-loai"; a.textContent = m[0];
        var b = document.createElement("span"); b.className = "qc-tcd__goi-ten"; b.textContent = m[1];
        li.appendChild(a); li.appendChild(b);
        // mousedown (không phải click): chọn trước khi ô gõ mất tiêu điểm.
        li.addEventListener("mousedown", function (e) { e.preventDefault(); chon(m[1]); });
        ds.appendChild(li);
      });
      ds.hidden = muc.length < 2;          // chỉ có "Thêm từ khoá" thì không cần xổ
      go.setAttribute("aria-expanded", ds.hidden ? "false" : "true");
      dangChon = -1;
    }
    function hoi() {
      var q = go.value.replace(/\s+/g, " ").trim();
      if (!boDau(q) || !window.fetch) { dongDs(); return; }
      // Cùng phạm vi đang chọn trong Bộ lọc (bên, nền tảng, tài khoản, từ–đến) — máy chủ kiểm lại.
      var tham = new URLSearchParams();
      tham.set("q", q.slice(0, DAI));
      ["ben", "nen_tang", "tu", "den"].forEach(function (k) { var x = f.elements[k]; if (x && x.value) tham.set(k, x.value); });
      Array.prototype.forEach.call(f.querySelectorAll('input[name="tk"]:checked'), function (x) { tham.append("tk", x.value); });
      var so = ++luot;
      fetch("/api/qc/ten-cd?" + tham.toString(), { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (p) { if (p && so === luot && go.value.trim() && document.activeElement === go) veGoiY(q, p); })
        .catch(function () { /* gợi ý chỉ là phụ — lỗi mạng thì thôi */ });
    }

    // Không JS = ô chữ "a, b"; có JS: chữ sẵn thành thẻ, ô gõ không gửi nữa (thẻ mang ô ẩn).
    go.removeAttribute("name");
    them(go.value);
    go.value = "";
    o.addEventListener("click", function (e) { if (e.target === o) go.focus(); });
    go.addEventListener("input", function () {
      if (/[,;]/.test(go.value)) {
        var phan = go.value.split(/[,;]/);
        var cuoi = phan.pop();
        them(phan.join(","));
        go.value = cuoi.replace(/^\s+/, "");
      }
      clearTimeout(cho);
      cho = setTimeout(hoi, 250);
    });
    go.addEventListener("keydown", function (e) {
      var mo = !ds.hidden;
      if (e.key === "ArrowDown" && mo) { e.preventDefault(); danhDau(dangChon + 1); }
      else if (e.key === "ArrowUp" && mo) { e.preventDefault(); danhDau(dangChon - 1); }
      else if (e.key === "Enter") {
        if (mo && dangChon >= 0) { e.preventDefault(); chon(ds.querySelectorAll('[role="option"]')[dangChon].lastChild.textContent); }
        else if (go.value.trim()) { e.preventDefault(); chon(go.value); }
        // ô trống + Enter: gửi biểu mẫu (= Áp dụng)
      } else if (e.key === "Escape" && mo) { e.preventDefault(); e.stopPropagation(); dongDs(); }
      else if (e.key === "Backspace" && !go.value && d.ds.length) { d.ds.pop(); veThe(); }
    });
    go.addEventListener("blur", function () { setTimeout(dongDs, 120); });
    d.them = them; d.veThe = veThe;
    cacDong.push(d);
  }

  Array.prototype.forEach.call(khoi.querySelectorAll("[data-tcd]"), dung);
  if (!cacDong.length) return;
  veTom();
  // Chữ còn trong ô gõ lúc gửi (chưa Enter) vẫn tính là một từ khoá.
  f.addEventListener("submit", function () { cacDong.forEach(function (d) { if (d.go.value.trim()) { d.them(d.go.value); d.go.value = ""; } }); });
  var xoa = khoi.querySelector("[data-tcd-xoa]");
  if (xoa) xoa.addEventListener("click", function (e) {
    e.preventDefault();
    cacDong.forEach(function (d) { d.ds.length = 0; d.go.value = ""; d.veThe(); });
    cacDong[0].go.focus();
  });
  document.addEventListener("click", function (e) { if (khung.open && !khoi.contains(e.target)) khung.open = false; });
  khoi.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && khung.open) { khung.open = false; khung.querySelector("summary").focus(); }
  });
  khung.addEventListener("toggle", function () { if (khung.open) cacDong[0].go.focus(); });
})();
