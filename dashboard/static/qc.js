// Trang "Quảng cáo" (TikTok 19/10/2026, + Meta 20/10/2026): vẽ biểu đồ "Theo ngày" từ #qc-api = ĐÚNG
// payload của GET /api/qc (đã lọc tiền theo quyền ở máy chủ; theo_ngay_nen_tang có `nen_tang`).
// Xem "Tất cả" mà phạm vi có cả TikTok lẫn Meta → cột chồng theo nền tảng (màu nền tảng, cùng màu thanh
// tỉ trọng + chấm ở bảng); một nền tảng → đường vùng một màu như trước. Điện thoại: gập sẵn bộ lọc để
// số lên màn hình đầu. Không gọi API, không chèn HTML từ dữ liệu (CSP script-src 'self'; chữ chỉ qua
// textContent). Màu đọc từ biến CSS → sáng/tối tự theo.
"use strict";
(function () {
  // Bộ lọc gập trên điện thoại (máy tính luôn mở; dòng tóm tắt chỉ hiện ≤ 760px — qc.css).
  var loc = document.getElementById("qc-loc");
  if (loc && window.matchMedia && window.matchMedia("(max-width: 760px)").matches) loc.open = false;

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
  var ngay = ds.map(function (x) { return x.ngay; });
  var co = ds[0];
  var chuoi = CHUOI.filter(function (c) { return c[0] in co; });
  if (!chuoi.length) return;
  // Theo nền tảng: { tiktok: {ngày: dòng}, meta: {...} } — chỉ khi xem "Tất cả" và có ≥ 2 nền tảng.
  var theoNen = {};
  (p.theo_ngay_nen_tang || []).forEach(function (r) { (theoNen[r.nen_tang] = theoNen[r.nen_tang] || {})[r.ngay] = r; });
  var cacNen = (p.theo_nen_tang || []).map(function (n) { return n.nen_tang; }).filter(function (n) { return theoNen[n]; });
  var chong = p.nen_tang === "tat_ca" && cacNen.length > 1;

  var giamDong = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var SO = new Intl.NumberFormat("vi-VN");
  var chon = chuoi[0][0];
  try { var luu = window.localStorage.getItem("qc-chi-so"); if (luu && chuoi.some(function (c) { return c[0] === luu; })) chon = luu; } catch (e) { /* bỏ qua */ }
  var bd = null;

  function bien(ten) { return getComputedStyle(document.documentElement).getPropertyValue(ten).trim(); }
  function soGon(n) {
    if (n == null) return "—";
    var a = Math.abs(n), dv = a >= 1e9 ? [1e9, " tỷ"] : a >= 1e6 ? [1e6, " tr"] : a >= 1e4 ? [1e3, " N"] : null;
    if (!dv) return SO.format(n);
    var x = n / dv[0];
    return x.toLocaleString("vi-VN", { maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 1 }) + dv[1];
  }
  function ngayNgan(iso) { return iso.slice(8, 10) + "/" + iso.slice(5, 7); }
  function ngayDu(iso) { return iso.split("-").reverse().join("/"); }
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

  function veChuGiai() {
    if (!chuGiai) return;
    while (chuGiai.firstChild) chuGiai.removeChild(chuGiai.firstChild);
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
    var ma = c[0], ten = c[1];
    var m = { chu: bien("--chu"), phu: bien("--chu-phu"), mo: bien("--chu-mo"), ke: bien("--ke"),
              truc: bien("--truc"), mat: bien("--be-mat"), phong: bien("--phong") || "system-ui, sans-serif",
              chinh: bien("--s1"), tiktok: bien("--qc-tiktok") || "#111827", meta: bien("--qc-meta") || "#1877f2" };
    if (!bd) bd = window.echarts.init(khung, null, { renderer: "canvas" });
    khung.setAttribute("aria-label", "Biểu đồ " + ten.toLowerCase() + " theo ngày" + (chong ? ", chia theo nền tảng" : "") + ", " + ngay.length + " ngày");
    veChuGiai();
    var series;
    if (chong) {
      series = cacNen.map(function (n, i) {
        return {
          name: TEN_NEN[n] || n, type: "bar", stack: "nen", barMaxWidth: 22, barCategoryGap: "28%",
          data: ngay.map(function (x) { return giaTri(theoNen[n][x], ma); }),
          itemStyle: { color: m[n] || m.chinh, borderRadius: i === cacNen.length - 1 ? [3, 3, 0, 0] : 0 },
          emphasis: { focus: "series" }
        };
      });
    } else {
      series = [{
        name: ten, type: "line", data: ds.map(function (x) { return giaTri(x, ma); }),
        showSymbol: ngay.length <= 45, symbol: "circle", symbolSize: 6,
        smooth: 0.25, smoothMonotone: "x", lineStyle: { width: 2, color: m.chinh },
        itemStyle: { color: m.chinh, borderColor: m.mat, borderWidth: 2 },
        areaStyle: { color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: hexRgba(m.chinh, 0.22) }, { offset: 1, color: hexRgba(m.chinh, 0.02) }]) }
      }];
    }
    bd.setOption({
      animation: !giamDong, animationDuration: 250,
      textStyle: { fontFamily: m.phong, color: m.phu },
      grid: { left: 4, right: 12, top: 16, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis", renderMode: "richText", backgroundColor: m.mat, borderColor: m.ke, borderWidth: 1,
        padding: [8, 12], textStyle: { color: m.chu, fontSize: 12, fontFamily: m.phong },
        axisPointer: chong ? { type: "shadow", shadowStyle: { color: hexRgba(m.truc, 0.25) } }
                           : { type: "line", lineStyle: { color: m.truc, type: "dashed" } },
        formatter: function (ps) {
          var i = ps[0].dataIndex, dong = [ngayDu(ngay[i])], tong = 0;
          ps.forEach(function (x) { tong += x.value || 0; dong.push(x.seriesName + ": " + SO.format(x.value || 0) + donVi(ma)); });
          if (chong) dong.push("Cộng: " + SO.format(tong) + donVi(ma));
          return dong.join("\n");
        }
      },
      xAxis: { type: "category", data: ngay, boundaryGap: chong, axisLine: { lineStyle: { color: m.ke } }, axisTick: { show: false },
               axisLabel: { color: m.mo, fontSize: 11, hideOverlap: true, formatter: ngayNgan, margin: 10 } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: m.ke, type: [4, 4] } },
               axisLabel: { color: m.mo, fontSize: 11, formatter: function (v) { return soGon(v); } } },
      series: series
    }, true);
  }

  veNut();
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
  khung.addEventListener("toggle", function () { if (khung.open && tim) tim.focus(); });
  var f = khoi.closest("form");
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
          if (goiY) goiY.textContent = "Thường xong sau 1–2 phút.";
          return true;
        }
      })
      .catch(function () { /* mạng chập chờn: lượt sau hỏi lại */ })
      .then(function (xong) {
        if (xong) return;
        if (Date.now() - batDau < TOI_DA) { setTimeout(hoi, NHIP); return; }
        // Hết 15 phút mà vẫn đang tạo: thôi hỏi, mở lại nút (máy chủ vẫn chặn nếu còn đang chờ thật).
        if (nut) nut.disabled = false;
        if (goiY) goiY.textContent = "Chưa thấy xong — tải lại trang để xem trạng thái mới.";
      });
  }
  setTimeout(hoi, NHIP);
})();
