// Trang "Quảng cáo TikTok" (19/10/2026): chỉ vẽ biểu đồ "Theo ngày" từ JSON máy chủ nhúng sẵn
// (#qc-du-lieu — đã lọc chỉ số tiền theo quyền). Không gọi API, không chèn HTML từ dữ liệu
// (CSP script-src 'self'; chữ chỉ qua textContent). Màu đọc từ biến CSS → sáng/tối tự theo.
"use strict";
(function () {
  var el = document.getElementById("qc-du-lieu");
  var khung = document.getElementById("qc-bd-ngay");
  var nhom = document.getElementById("qc-chon-chi-so");
  if (!el || !khung || !nhom || !window.echarts) return;
  var d;
  try { d = JSON.parse(el.textContent || "{}"); } catch (e) { return; }
  if (!d.chuoi || !d.chuoi.length || !d.ngay || !d.ngay.length) return;
  var giamDong = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var SO = new Intl.NumberFormat("vi-VN");
  var chon = d.chuoi[0].ma;
  try { var luu = window.localStorage.getItem("qc-chi-so"); if (luu && d.chuoi.some(function (c) { return c.ma === luu; })) chon = luu; } catch (e) { /* bỏ qua */ }
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
  function hexRgba(hex, a) {
    var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
    return m ? "rgba(" + parseInt(m[1], 16) + "," + parseInt(m[2], 16) + "," + parseInt(m[3], 16) + "," + a + ")" : hex;
  }
  function donVi(ma) { return ma === "chi" ? (d.tien_te && d.tien_te.length === 1 && d.tien_te[0] !== "VND" ? " " + d.tien_te[0] : " ₫") : ""; }

  function veNut() {
    while (nhom.firstChild) nhom.removeChild(nhom.firstChild);
    d.chuoi.forEach(function (c) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "qc-phan__nut";
      b.textContent = c.ten;
      b.setAttribute("aria-pressed", c.ma === chon ? "true" : "false");
      b.addEventListener("click", function () {
        if (chon === c.ma) return;
        chon = c.ma;
        try { window.localStorage.setItem("qc-chi-so", chon); } catch (e) { /* bỏ qua */ }
        Array.prototype.forEach.call(nhom.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        ve();
      });
      nhom.appendChild(b);
    });
  }

  function ve() {
    var c = d.chuoi.filter(function (x) { return x.ma === chon; })[0] || d.chuoi[0];
    var m = { chu: bien("--chu"), phu: bien("--chu-phu"), mo: bien("--chu-mo"), ke: bien("--ke"),
              truc: bien("--truc"), mat: bien("--be-mat"), phong: bien("--phong") || "system-ui, sans-serif",
              chinh: bien("--s1") };
    if (!bd) bd = window.echarts.init(khung, null, { renderer: "canvas" });
    khung.setAttribute("aria-label", "Biểu đồ " + c.ten.toLowerCase() + " theo ngày, " + d.ngay.length + " ngày");
    bd.setOption({
      animation: !giamDong, animationDuration: 250,
      textStyle: { fontFamily: m.phong, color: m.phu },
      grid: { left: 4, right: 12, top: 16, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis", renderMode: "richText", backgroundColor: m.mat, borderColor: m.ke, borderWidth: 1,
        padding: [8, 12], textStyle: { color: m.chu, fontSize: 12, fontFamily: m.phong },
        axisPointer: { type: "line", lineStyle: { color: m.truc, type: "dashed" } },
        formatter: function (ps) { var i = ps[0].dataIndex; return d.ngay[i].split("-").reverse().join("/") + "\n" + c.ten + ": " + SO.format(c.ds[i]) + donVi(c.ma); }
      },
      xAxis: { type: "category", data: d.ngay, boundaryGap: false, axisLine: { lineStyle: { color: m.ke } }, axisTick: { show: false },
               axisLabel: { color: m.mo, fontSize: 11, hideOverlap: true, formatter: ngayNgan, margin: 10 } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: m.ke, type: [4, 4] } },
               axisLabel: { color: m.mo, fontSize: 11, formatter: function (v) { return soGon(v); } } },
      series: [{
        name: c.ten, type: "line", data: c.ds, showSymbol: d.ngay.length <= 45, symbol: "circle", symbolSize: 6,
        smooth: 0.25, smoothMonotone: "x", lineStyle: { width: 2, color: m.chinh },
        itemStyle: { color: m.chinh, borderColor: m.mat, borderWidth: 2 },
        areaStyle: { color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: hexRgba(m.chinh, 0.22) }, { offset: 1, color: hexRgba(m.chinh, 0.02) }]) }
      }]
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
