// Trang Chỉ số (thiết kế lại 15/10/2026): lấy JSON /api/chi-so theo bộ lọc, vẽ thẻ KPI, biểu đồ
// ECharts, mây từ khoá + hàng "sắc thái theo chủ đề" kiểu Kompa, và luồng bình luận có bộ lọc theo
// trường (nền tảng / nguồn / sắc thái / chủ đề / nhãn lọc) gọi /api/binh-luan.
// Thời gian thực: nghe /su-kien; có `cap-nhat` của đúng dự án thì tải lại số (không tải lại
// trang) và ghi "cập nhật lúc HH:MM:SS".
// An toàn: chữ từ kho (tên nguồn, nội dung bài/bình luận, chủ đề…) chỉ đi qua textContent /
// createElement — KHÔNG chèn chuỗi HTML; link chỉ nhận http(s) (linkAnToan); tooltip ECharts vẽ bằng
// canvas (renderMode richText); biểu tượng là SVG dựng bằng createElementNS.
"use strict";
(function () {
  var cfgEl = document.getElementById("cau-hinh-chi-so");
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent || "{}");
  if (!cfg.du_an) return;

  var SO = new Intl.NumberFormat("vi-VN");
  var SO_GON = new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 });
  var bieuDo = {};
  var duLieu = null;
  var henGio = null;
  var nenTangChon = null;
  var giamDong = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  var TC = "Tích cực", TI = "Tiêu cực", TL = "Trung lập", CHUA = "chưa phân loại", NHA = "kênh nhà";
  var SAC4 = [TC, TI, TL, CHUA];
  var KHOA_SAC = { "Tích cực": "tich_cuc", "Tiêu cực": "tieu_cuc", "Trung lập": "trung_lap",
                   "chưa phân loại": "chua_phan_loai", "kênh nhà": "kenh_nha" };
  var LOP_SAC = { "Tích cực": "tc", "Tiêu cực": "ti", "Trung lập": "tl", "chưa phân loại": "chua", "kênh nhà": "nha" };
  var TEN_SAC = { "Tích cực": "Tích cực", "Tiêu cực": "Tiêu cực", "Trung lập": "Trung lập",
                  "chưa phân loại": "Chưa phân loại", "kênh nhà": "Kênh nhà" };
  var TEN_NT = { tiktok: "TikTok", facebook: "Facebook", youtube: "YouTube", instagram: "Instagram" };
  var TEN_LOAI_BL = { hop_le: "Hợp lệ", it_noi_dung: "Ít nội dung", spam: "Spam", trung: "Trùng lặp",
                      seeding: "Seeding", thuong_hieu: "Thương hiệu" };
  var MAU_LOAI_BL = { hop_le: "--s1", it_noi_dung: "--trung-lap", spam: "--s2", trung: "--s4",
                      seeding: "--s5", thuong_hieu: "--s7" };
  // Trạng thái hiển thị (không gửi lên máy chủ).
  var tt = { che: "ngay", sacNguon: "bai", tgNguon: "bai", cdNguon: "bai", tkDang: "may", cdMo: false };

  // ─── tiện ích ───
  function $(id) { return document.getElementById(id); }
  function so(n) { return n == null ? "—" : SO.format(n); }
  function soGon(n) { return n == null ? "—" : (n >= 10000 ? SO_GON.format(n) : SO.format(n)); }
  function pt(x) {
    return x == null ? "—" : x.toLocaleString("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
  }
  function ptCua(v, tong) { return tong ? pt(Math.round(1000 * v / tong) / 10) : "—"; }
  function ngayNgan(iso) { var p = String(iso).split("-"); return p[2] + "/" + p[1]; }
  function ngayDu(iso) {
    if (!iso) return "—";
    var p = String(iso).slice(0, 10).split("-");
    return p[2] + "/" + p[1] + "/" + p[0];
  }
  function ngayGio(iso) {
    if (!iso) return "";
    var s = String(iso);
    return ngayDu(s) + (s.length >= 16 ? " " + s.slice(11, 16) : "");
  }
  function gioVN(d) {
    return d.toLocaleTimeString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false });
  }
  function bien(ten) {
    return getComputedStyle(document.documentElement).getPropertyValue(ten).trim();
  }
  function tao(the, lop, chu) {
    var el = document.createElement(the);
    if (lop) el.className = lop;
    if (chu != null) el.textContent = chu;
    return el;
  }
  function chuNode(s) { return document.createTextNode(s); }
  function xoa(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function urlHopLe(u) { return typeof u === "string" && /^https?:\/\//i.test(u); }
  function linkAnToan(url, chu, lop) {
    if (urlHopLe(url)) {
      var a = tao("a", lop || "", chu);
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      return a;
    }
    return tao("span", lop || "", chu);
  }
  function nut(chu, lop, xuLy) {
    var b = tao("button", lop || "", chu);
    b.type = "button";
    if (xuLy) b.addEventListener("click", xuLy);
    return b;
  }
  function treo(fn, ms) {
    var t = null;
    return function () {
      var a = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(null, a); }, ms);
    };
  }
  function boDau(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
  }
  function hexRgba(hex, a) {
    var h = String(hex || "").replace("#", "");
    if (h.length === 3) h = h.replace(/./g, "$&$&");
    var n = parseInt(h, 16);
    if (h.length !== 6 || isNaN(n)) return hex;
    return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
  }
  // Mỗi khối vẽ riêng: một khối lỗi không làm trắng cả trang.
  function chay(ten, fn) {
    try { fn(); } catch (e) { if (window.console) console.error("Chỉ số — lỗi vẽ khối " + ten, e); }
  }
  function taoCtl() {
    return window.AbortController ? new AbortController() : { signal: undefined, abort: function () {} };
  }

  // ─── biểu tượng SVG (dựng bằng createElementNS, không chèn chuỗi HTML) ───
  var SVG = "http://www.w3.org/2000/svg";
  var BIEU_TUONG = {
    tim: [["path", { d: "M12 20.5s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.7c0 5.6-7.5 10.2-7.5 10.2z" }]],
    bl: [["path", { d: "M4.5 5.5h15v10.5h-8.5l-4.5 3.5V16h-2z" }]],
    mat: [["path", { d: "M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z" }], ["circle", { cx: 12, cy: 12, r: 2.6 }]],
    chia: [["path", { d: "M4 13v6.5h16V13M12 15V4M7.5 8.5 12 4l4.5 4.5" }]],
    mo: [["path", { d: "M14 4h6v6M20 4l-8.5 8.5M18 14v6H4V6h6" }]],
    tim_kiem: [["circle", { cx: 11, cy: 11, r: 6.5 }], ["path", { d: "M20 20l-4.2-4.2" }]],
    xuong: [["path", { d: "M6 9l6 6 6-6" }]],
    tra_loi: [["path", { d: "M6 5v6a4 4 0 0 0 4 4h9M15 11l4 4-4 4" }]],
    dau: [["path", { d: "M5 12.5l4.5 4.5L19 7.5" }]],
    dong: [["path", { d: "M6 6l12 12M18 6 6 18" }]]
  };
  var GLYPH_NT = {
    tiktok: [["path", { d: "M16.6 5.8A4.3 4.3 0 0 1 15.5 3h-3.1v12.4a2.6 2.6 0 1 1-1.8-2.5V9.7a5.7 5.7 0 1 0 4.9 5.6V9a7.3 7.3 0 0 0 4.3 1.4V7.3a4.3 4.3 0 0 1-3.2-1.5z" }]],
    facebook: [["path", { d: "M13.4 21v-7.6h2.6l.4-3h-3V8.5c0-.9.3-1.5 1.5-1.5h1.6V4.3a21 21 0 0 0-2.3-.1c-2.3 0-3.9 1.4-3.9 4v2.2H7.7v3h2.6V21z" }]],
    youtube: [["path", { d: "M9.5 7.8v8.4l7-4.2z" }]],
    instagram: [["rect", { x: 4.5, y: 4.5, width: 15, height: 15, rx: 4.2, fill: "none", stroke: "currentColor", "stroke-width": 2.1 }],
                ["circle", { cx: 12, cy: 12, r: 3.4, fill: "none", stroke: "currentColor", "stroke-width": 2.1 }],
                ["circle", { cx: 16.6, cy: 7.4, r: 1.15 }]]
  };
  function dungSvg(ds, lop) {
    var s = document.createElementNS(SVG, "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("focusable", "false");
    if (lop) s.setAttribute("class", lop);
    ds.forEach(function (p) {
      var e = document.createElementNS(SVG, p[0]);
      Object.keys(p[1]).forEach(function (k) { e.setAttribute(k, String(p[1][k])); });
      s.appendChild(e);
    });
    return s;
  }
  function bieuTuong(ten) { return dungSvg(BIEU_TUONG[ten], "cs-bt"); }

  // Huy hiệu nền tảng: ô màu thương hiệu + glyph; `coChu` thêm tên; `trangTri` = ẩn với trình đọc.
  function huyHieuNT(nt, coChu, trangTri) {
    var co = !!GLYPH_NT[nt];
    var o = tao("span", "cs-nt cs-nt--" + (co ? nt : "khac"));
    var hop = tao("span", "cs-nt__o");
    if (co) hop.appendChild(dungSvg(GLYPH_NT[nt]));
    else hop.textContent = String(TEN_NT[nt] || nt || "?").charAt(0).toUpperCase();
    o.appendChild(hop);
    var ten = TEN_NT[nt] || nt || "?";
    if (coChu) o.appendChild(tao("span", "cs-nt__chu", ten));
    else if (trangTri) o.setAttribute("aria-hidden", "true");
    else { o.title = ten; o.appendChild(tao("span", "cs-an", ten)); }
    return o;
  }

  // Ảnh đại diện = chữ cái đầu, màu băm theo tên (không ảnh ngoài — CSP img-src 'self').
  function bam(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return Math.abs(h);
  }
  function chuCai(ten) {
    var t = String(ten || "").replace(/[^\p{L}\p{N}\s]/gu, " ").trim().split(/\s+/).filter(Boolean);
    if (!t.length) return "?";
    var a = Array.from(t[0])[0], b = t.length > 1 ? Array.from(t[t.length - 1])[0] : "";
    return (a + b).toUpperCase();
  }
  function anhDaiDien(ten, lop) {
    var o = tao("span", "cs-av cs-av--" + (bam(String(ten || "?")) % 8) + (lop ? " " + lop : ""), chuCai(ten));
    o.setAttribute("aria-hidden", "true");
    return o;
  }

  // "3 giờ trước" (title = ngày giờ đầy đủ).
  function thoiDiem(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    if (isNaN(d.getTime())) return { chu: ngayGio(iso), day: ngayGio(iso) };
    var s = (Date.now() - d.getTime()) / 1000, chu;
    if (s < 60) chu = "vừa xong";
    else if (s < 3600) chu = Math.floor(s / 60) + " phút trước";
    else if (s < 86400) chu = Math.floor(s / 3600) + " giờ trước";
    else if (s < 7 * 86400) chu = Math.floor(s / 86400) + " ngày trước";
    else if (s < 35 * 86400) chu = Math.floor(s / (7 * 86400)) + " tuần trước";
    else chu = ngayDu(iso);
    return { chu: chu, day: ngayGio(iso) };
  }

  // ─── nhãn (chip): MỘT kiểu cho mọi nhãn ───
  var CO_CHAM = { tc: 1, ti: 1, tl: 1, chua: 1, nha: 1 };
  function chip(chu, kieu, title) {
    var c = tao("span", "cs-chip" + (kieu ? " cs-chip--" + kieu : ""));
    if (CO_CHAM[kieu]) c.appendChild(tao("span", "cs-chip__cham"));
    c.appendChild(tao("span", "cs-chip__chu", chu));
    if (title) c.title = title;
    return c;
  }
  function chipSac(s) {
    var k = LOP_SAC[s];
    return k ? chip(TEN_SAC[s], k) : chip(s || "—", "chua");
  }

  // ─── bóng nổi (ⓘ, mây từ): position fixed, kẹp trong khung nhìn ───
  var noi = null, noiCua = null;
  function hienNoi(dich, dung) {
    if (!noi) {
      noi = tao("div", "cs-noi");
      noi.setAttribute("role", "tooltip");
      noi.hidden = true;
      document.body.appendChild(noi);
    }
    xoa(noi);
    dung(noi);
    noi.hidden = false;
    noiCua = dich;
    var r = dich.getBoundingClientRect(), w = noi.offsetWidth, h = noi.offsetHeight;
    var vw = document.documentElement.clientWidth, vh = window.innerHeight;
    var x = Math.max(8, Math.min(vw - w - 8, r.left + r.width / 2 - w / 2));
    var y = r.top - h - 8;
    if (y < 8) y = r.bottom + 8;
    if (y + h > vh - 8) y = Math.max(8, vh - h - 8);
    noi.style.left = Math.round(x) + "px";
    noi.style.top = Math.round(y) + "px";
  }
  function anNoi(dich) {
    if (noi && (!dich || dich === noiCua)) { noi.hidden = true; noiCua = null; }
  }
  window.addEventListener("scroll", function () { anNoi(); }, { passive: true });

  function ganGoiY(b) {
    var chu = b.getAttribute("data-goi-y") || "";
    var vuaHien = 0;
    b.setAttribute("aria-label", "Giải thích: " + chu);
    b.setAttribute("aria-expanded", "false");
    function hien() {
      vuaHien = Date.now();
      hienNoi(b, function (o) { o.appendChild(chuNode(chu)); });
      b.setAttribute("aria-expanded", "true");
    }
    function an() { anNoi(b); b.setAttribute("aria-expanded", "false"); }
    b.addEventListener("mouseenter", hien);
    b.addEventListener("mouseleave", an);
    b.addEventListener("focus", hien);
    b.addEventListener("blur", an);
    b.addEventListener("click", function () {
      if (Date.now() - vuaHien < 400) return;            // chạm trên điện thoại: vừa hiện thì giữ
      if (noiCua === b && noi && !noi.hidden) an(); else hien();
    });
    b.addEventListener("keydown", function (e) { if (e.key === "Escape") an(); });
  }
  Array.prototype.forEach.call(document.querySelectorAll(".cs-goi-y"), ganGoiY);

  // ─── nhóm nút chọn (segmented) ───
  function nhomNut(el, ds, chon, doi) {
    if (!el) return;
    xoa(el);
    el.setAttribute("role", "group");
    ds.forEach(function (x) {
      var b = nut(x.chu, "cs-phan__nut", function () { if (x.gt !== chon) doi(x.gt); });
      b.setAttribute("aria-pressed", x.gt === chon ? "true" : "false");
      if (x.tat) { b.disabled = true; if (typeof x.tat === "string") b.title = x.tat; }
      el.appendChild(b);
    });
  }
  function giuTapTrung(el, fn) {
    var co = el && el.contains(document.activeElement);
    fn();
    if (co) {
      var b = el.querySelector('[aria-pressed="true"]');
      if (b) b.focus();
    }
  }

  // ─── màu + khung ECharts ───
  // Màu đi theo đối tượng (không theo thứ hạng): cùng một sắc thái luôn cùng một màu.
  function mau() {
    return {
      chu: bien("--chu"), phu: bien("--chu-phu"), mo: bien("--chu-mo"), ke: bien("--ke"),
      truc: bien("--truc"), mat: bien("--be-mat"),
      sac: { "Tích cực": bien("--cs-tc"), "Tiêu cực": bien("--cs-ti"), "Trung lập": bien("--cs-tl"),
             "chưa phân loại": bien("--cs-chua"), "kênh nhà": bien("--cs-nha") },
      chinh: bien("--s1")
    };
  }
  function coBan(m) {
    return {
      animationDuration: 300,
      textStyle: { fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif", color: m.phu },
      grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
      tooltip: {
        renderMode: "richText", trigger: "axis", backgroundColor: m.mat, borderColor: m.truc,
        textStyle: { color: m.chu, fontSize: 12 }, valueFormatter: function (v) { return so(v); },
        axisPointer: { type: "line", lineStyle: { color: m.truc } }
      },
      legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, type: "scroll",
                textStyle: { color: m.phu, fontSize: 12 }, pageIconColor: m.phu, pageIconInactiveColor: m.ke,
                pageTextStyle: { color: m.mo } }
    };
  }
  function nhanTruc(v) {
    return String(v).replace(/^Tuần từ /, "").replace(/^Tháng /, "").replace(/^(\d\d)\/(\d\d)\/\d{4}$/, "$1/$2");
  }
  function trucDanhMuc(m, du) {
    return { type: "category", data: du, axisLine: { lineStyle: { color: m.truc } }, axisTick: { show: false },
             axisLabel: { color: m.mo, fontSize: 11, hideOverlap: true, formatter: nhanTruc } };
  }
  function trucSo(m) {
    return { type: "value", splitLine: { lineStyle: { color: m.ke } }, minInterval: 1,
             axisLabel: { color: m.mo, fontSize: 11, formatter: function (v) { return SO.format(v); } } };
  }

  // Bấm vào biểu đồ → ngăn chi tiết. Mỗi biểu đồ đặt hàm ở `xuLyBam[id]` (bấm vào mảng/cột) hoặc
  // `xuLyBam[id + ":nen"]` (bấm bất kỳ đâu trong lưới — dùng cho biểu đồ đường); sự kiện gắn MỘT
  // lần lúc khởi tạo nên vẽ lại không gắn trùng.
  var xuLyBam = {};
  function ve(id, opt) {
    var el = $(id);
    if (!el || !window.echarts) return null;
    var bd = bieuDo[id];
    if (!bd) {
      bd = bieuDo[id] = window.echarts.init(el, null, { renderer: "canvas" });
      bd.on("click", function (p) {
        var f = xuLyBam[id];
        if (f && p.componentType === "series" && p.dataIndex != null) f(p);
      });
      bd.getZr().on("click", function (e) {
        var f = xuLyBam[id + ":nen"];
        if (f) f(e, bd);
      });
    }
    bd.setOption(opt, true);
    return bd;
  }
  function chiSoTuDiem(bd, e, n) {
    var p = [e.offsetX, e.offsetY];
    if (!bd.containPixel({ gridIndex: 0 }, p)) return null;
    var v = bd.convertFromPixel({ gridIndex: 0 }, p);
    if (!v) return null;
    var i = Math.round(v[0]);
    return i >= 0 && i < n ? i : null;
  }

  // ─── gom theo ngày / tuần / tháng (cộng dồn chuỗi ngày ở trình duyệt) ───
  function ngayISO(d) { return d.toISOString().slice(0, 10); }
  function congNgay(iso, n) {
    var d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return ngayISO(d);
  }
  function dauTuan(iso) {
    var d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7);
    return ngayISO(d);
  }
  function moTaKhoang(kh) {
    return kh.ngay_tu === kh.ngay_den ? "ngày " + ngayDu(kh.ngay_tu) : ngayDu(kh.ngay_tu) + " – " + ngayDu(kh.ngay_den);
  }
  // x = xu_huong của máy chủ (theo "ngày" hoặc "tuần"); cd = "ngay" | "tuan" | "thang".
  function gom(x, khoa, cd) {
    var theoTuan = x.don_vi === "tuần";
    if (theoTuan && cd === "ngay") cd = "tuan";
    var nhom = [];
    (x.moc || []).forEach(function (m, i) {
      var k = cd === "thang" ? m.slice(0, 7) : cd === "tuan" ? (theoTuan ? m : dauTuan(m)) : m;
      var g = nhom[nhom.length - 1];
      if (!g || g.k !== k) { g = { k: k, bd: m, chi: [] }; nhom.push(g); }
      g.chi.push(i);
    });
    var du = {};
    khoa.forEach(function (k) {
      var cot = x[k] || [];
      du[k] = nhom.map(function (g) { return g.chi.reduce(function (a, i) { return a + (cot[i] || 0); }, 0); });
    });
    return {
      cd: cd, n: nhom.length, du: du,
      ten: nhom.map(function (g) {
        if (cd === "thang") return "Tháng " + g.bd.slice(5, 7) + "/" + g.bd.slice(0, 4);
        return cd === "tuan" ? "Tuần từ " + ngayNgan(g.bd) : ngayDu(g.bd);
      }),
      tu: nhom.map(function (g) { return g.bd; }),
      den: nhom.map(function (g, j) {
        if (cd === "ngay") return g.bd;
        return j + 1 < nhom.length ? congNgay(nhom[j + 1].bd, -1) : cfg.den;
      })
    };
  }
  function cacChe(x) {
    return [{ gt: "ngay", chu: "Ngày", tat: x.don_vi === "tuần" ? "Khoảng dài hơn 92 ngày chỉ có số theo tuần" : false },
            { gt: "tuan", chu: "Tuần" }, { gt: "thang", chu: "Tháng" }];
  }
  function doiChe(v) {
    tt.che = v;
    var m = mau();
    giuTapTrung($("che-xu-huong"), function () { chay("thảo luận", function () { veXuHuong(duLieu, m); }); });
    giuTapTrung($("che-sac-thai-tg"), function () { chay("sắc thái theo thời gian", function () { veSacThaiTg(duLieu, m); }); });
  }
  function nutNguon(coBl) {
    return [{ gt: "bai", chu: "Bài đăng" }, { gt: "bl", chu: "Bình luận", tat: coBl ? false : "Chưa có bình luận đã đọc" }];
  }

  // ─── KPI ───
  function theKpi(nhan, giaTri, doi, ghiChu, cham) {
    var o = tao("div", "the-khoi kpi");
    var n = tao("div", "kpi__nhan");
    if (cham) { var c = tao("span", "cs-kpi__cham"); c.style.background = cham; n.appendChild(c); }
    n.appendChild(chuNode(nhan));
    o.appendChild(n);
    o.appendChild(tao("div", "kpi__so so", giaTri));
    var d = tao("div", "kpi__doi");
    if (doi) {
      if (doi.doi_pt == null) {
        d.textContent = "kỳ trước " + so(doi.truoc);
      } else {
        var lop = doi.doi_pt > 0 ? "tang" : doi.doi_pt < 0 ? "giam" : "";
        var mui = doi.doi_pt > 0 ? "▲ +" : doi.doi_pt < 0 ? "▼ " : "■ ";
        d.appendChild(tao("span", lop, mui + pt(doi.doi_pt)));
        d.appendChild(chuNode(" so với kỳ trước"));
      }
    } else if (ghiChu) {
      d.textContent = ghiChu;
    }
    o.appendChild(d);
    return o;
  }
  function veKpi(d) {
    var k = d.kpi, ss = d.so_sanh, el = $("kpi");
    xoa(el);
    el.appendChild(theKpi("Bài đăng", so(k.bai), ss.bai));
    el.appendChild(theKpi("Thảo luận", so(k.thao_luan), ss.thao_luan));
    el.appendChild(theKpi("Nguồn có bài", so(k.nguon_co_bai), ss.nguon_co_bai));
    if (k.bai_khu_trung != null && k.bai_khu_trung < k.bai) {
      el.appendChild(theKpi("Bài (khử trùng nội dung)", so(k.bai_khu_trung), null, so(k.bai - k.bai_khu_trung) + " bài đăng lại cùng nội dung"));
    }
    el.appendChild(theKpi("Lượt xem", so(k.xem), ss.xem));
    el.appendChild(theKpi("Tương tác", so(k.tuong_tac), ss.tuong_tac));
    el.appendChild(theSacKpi(k));
  }
  // Bốn chỉ số sắc thái của bài gộp vào MỘT thẻ rộng có thanh 100% (bấm ô → xem bài).
  function theSacKpi(k) {
    var o = tao("div", "the-khoi kpi cs-kpi-sac");
    var n = tao("div", "kpi__nhan");
    n.appendChild(chuNode("Sắc thái bài"));
    if (k.bai_kenh_nha) n.appendChild(tao("span", "mo", "· không tính " + so(k.bai_kenh_nha) + " bài kênh nhà"));
    o.appendChild(n);
    var dl = {};
    dl[TC] = k.tich_cuc; dl[TI] = k.tieu_cuc; dl[TL] = k.trung_lap; dl[CHUA] = k.chua_phan_loai;
    o.appendChild(thanhTron(dl));
    var luoi = tao("div", "cs-kpi-sac__luoi");
    [[TC, pt(k.tich_cuc_pt), so(k.tich_cuc) + " bài", "var(--cs-tc)"],
     [TI, pt(k.tieu_cuc_pt), so(k.tieu_cuc) + " bài", "var(--cs-ti)"],
     [TL, pt(k.trung_lap_pt), so(k.trung_lap) + " bài", "var(--cs-tl)"],
     [CHUA, so(k.chua_phan_loai), k.bai_kenh_nha ? "+ " + so(k.bai_kenh_nha) + " bài kênh nhà" : "bài", "var(--cs-chua)"]
    ].forEach(function (x) {
      var b = nut("", "cs-kpi-sac__o", function () { moChiTiet("bai", { sac_thai: x[0] }, "sắc thái " + TEN_SAC[x[0]]); });
      var nh = tao("span", "kpi__nhan");
      var c = tao("span", "cs-kpi__cham");
      c.style.background = x[3];
      nh.appendChild(c);
      nh.appendChild(chuNode(TEN_SAC[x[0]]));
      b.appendChild(nh);
      b.appendChild(tao("span", "kpi__so so", x[1]));
      b.appendChild(tao("span", "kpi__doi", x[2]));
      b.setAttribute("aria-label", TEN_SAC[x[0]] + ": " + x[1] + ", " + x[2] + " — bấm để xem bài");
      luoi.appendChild(b);
    });
    o.appendChild(luoi);
    return o;
  }

  // ─── thảo luận theo thời gian (đỉnh + gom ngày/tuần/tháng) ───
  function veXuHuong(d, m) {
    var x = d.xu_huong, g = gom(x, ["thao_luan", "bai", "binh_luan"], tt.che);
    nhomNut($("che-xu-huong"), cacChe(x), g.cd, doiChe);
    var dl = g.du.thao_luan, imax = -1;
    dl.forEach(function (v, i) { if (v > 0 && (imax < 0 || v > dl[imax])) imax = i; });
    var dinh = $("dinh-xu-huong");
    xoa(dinh);
    if (imax >= 0) {
      dinh.appendChild(chuNode("Tổng "));
      dinh.appendChild(tao("b", "", so(d.kpi.thao_luan)));
      dinh.appendChild(chuNode(" · đỉnh "));
      dinh.appendChild(tao("b", "", so(dl[imax])));
      dinh.appendChild(chuNode(" — " + g.ten[imax].toLowerCase()));
    } else {
      dinh.textContent = "Chưa có thảo luận trong khoảng này.";
    }
    var o = coBan(m);
    o.legend.show = false;
    o.grid.top = 30;
    o.xAxis = trucDanhMuc(m, g.ten);
    o.xAxis.boundaryGap = false;
    o.yAxis = trucSo(m);
    o.tooltip.formatter = function (ps) {
      var i = ps[0].dataIndex;
      return g.ten[i] + "\n" + so(g.du.thao_luan[i]) + " thảo luận\n" + so(g.du.bai[i]) + " bài · " +
             so(g.du.binh_luan[i]) + " bình luận nền tảng báo";
    };
    o.series = [{
      name: "Thảo luận", type: "line", data: dl, showSymbol: g.n <= 45, symbol: "circle", symbolSize: 7,
      smooth: 0.25, smoothMonotone: "x",
      lineStyle: { width: 2, color: m.chinh }, itemStyle: { color: m.chinh, borderColor: m.mat, borderWidth: 2 },
      areaStyle: { color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: hexRgba(m.chinh, 0.24) }, { offset: 1, color: hexRgba(m.chinh, 0.02) }]) },
      markPoint: imax >= 0 ? {
        symbol: "pin", symbolSize: 40, itemStyle: { color: m.chinh },
        label: { color: "#fff", fontSize: 10, fontWeight: 600, formatter: function (p) { return soGon(p.value); } },
        data: [{ type: "max", name: "Đỉnh" }] } : undefined
    }];
    ve("bd-xu-huong", o);
    xuLyBam["bd-xu-huong:nen"] = function (e, bd) {
      var i = chiSoTuDiem(bd, e, g.n);
      if (i == null) return;
      var kh = { ngay_tu: g.tu[i], ngay_den: g.den[i] };
      moChiTiet("bai", kh, so(dl[i]) + " thảo luận · " + moTaKhoang(kh));
    };
  }

  // ─── sắc thái (vòng) ───
  function duSac(d, laBl) {
    if (laBl) {
      var k = d.binh_luan_da_cao.kpi;
      return { ds: [[TC, k.tich_cuc], [TI, k.tieu_cuc], [TL, k.trung_lap], [CHUA, k.chua_phan_loai]], don: "bình luận" };
    }
    var map = {};
    (d.sac_thai || []).forEach(function (x) { map[x.sac_thai] = x.so; });
    return { ds: SAC4.map(function (s) { return [s, map[s] || 0]; }), don: "bài" };
  }
  function moSac(s, laBl) {
    if (laBl) moChiTiet("binh-luan", { sac_thai: s, loai_bl: "hop_le" }, "sắc thái " + TEN_SAC[s]);
    else moChiTiet("bai", { sac_thai: s }, "sắc thái " + TEN_SAC[s]);
  }
  function coBinhLuan(d) {
    var b = d && d.binh_luan_da_cao;
    return !!(b && b.kpi && b.kpi.so > 0);
  }
  function veSacThai(d, m) {
    var coBl = coBinhLuan(d);
    if (!coBl) tt.sacNguon = "bai";
    nhomNut($("nguon-sac-thai"), nutNguon(coBl), tt.sacNguon, function (v) {
      tt.sacNguon = v;
      giuTapTrung($("nguon-sac-thai"), function () { chay("sắc thái", function () { veSacThai(duLieu, mau()); }); });
    });
    var laBl = tt.sacNguon === "bl";
    var x = duSac(d, laBl);
    var tong = x.ds.reduce(function (a, r) { return a + r[1]; }, 0);
    var daPhan = x.ds.slice(0, 3).reduce(function (a, r) { return a + r[1]; }, 0);
    ve("bd-sac-thai", {
      animationDuration: 300,
      title: { text: so(tong), subtext: x.don, left: "center", top: "middle", itemGap: 2,
               textStyle: { color: m.chu, fontSize: 20, fontWeight: 650 }, subtextStyle: { color: m.mo, fontSize: 12 } },
      tooltip: { trigger: "item", renderMode: "richText", backgroundColor: m.mat, borderColor: m.truc,
                 textStyle: { color: m.chu, fontSize: 12 },
                 formatter: function (p) {
                   var s = p.data.sac;
                   return p.name + ": " + so(p.value) + " " + x.don + (s !== CHUA && daPhan ? " (" + ptCua(p.value, daPhan) + ")" : "");
                 } },
      series: [{ type: "pie", radius: ["60%", "88%"], center: ["50%", "50%"], avoidLabelOverlap: false,
                 label: { show: false }, labelLine: { show: false },
                 itemStyle: { borderColor: m.mat, borderWidth: 2, borderRadius: 3 },
                 emphasis: { scale: true, scaleSize: 4, label: { show: false } },
                 data: x.ds.filter(function (r) { return r[1] > 0; }).map(function (r) {
                   return { name: TEN_SAC[r[0]], value: r[1], sac: r[0], itemStyle: { color: m.sac[r[0]] } };
                 }) }]
    });
    xuLyBam["bd-sac-thai"] = function (p) { if (p.data && p.data.sac) moSac(p.data.sac, laBl); };
    var cg = $("chu-giai-sac-thai");
    xoa(cg);
    x.ds.forEach(function (r) {
      var b = nut("", "cs-cg__dong", function () { moSac(r[0], laBl); });
      var c = tao("span", "cs-cg__cham");
      c.style.background = m.sac[r[0]];
      b.appendChild(c);
      b.appendChild(tao("span", "cs-cg__ten", TEN_SAC[r[0]]));
      b.appendChild(tao("span", "cs-cg__so", so(r[1])));
      b.appendChild(tao("span", "cs-cg__pt", r[0] === CHUA || !daPhan ? "" : ptCua(r[1], daPhan)));
      b.setAttribute("aria-label", TEN_SAC[r[0]] + ": " + so(r[1]) + " " + x.don + " — bấm để xem");
      cg.appendChild(b);
    });
    $("ghi-chu-sac-thai").textContent = !tong ? "Chưa có dữ liệu sắc thái." : laBl
      ? "% trên " + so(daPhan) + " bình luận hợp lệ đã phân loại."
      : "% trên " + so(daPhan) + " bài đã phân loại; không tính bài kênh nhà.";
  }

  // ─── sắc thái theo thời gian (đường kiểu Kompa) ───
  function veSacThaiTg(d, m) {
    var coBl = coBinhLuan(d);
    if (!coBl) tt.tgNguon = "bai";
    nhomNut($("nguon-sac-thai-tg"), nutNguon(coBl), tt.tgNguon, function (v) {
      tt.tgNguon = v;
      giuTapTrung($("nguon-sac-thai-tg"), function () { chay("sắc thái theo thời gian", function () { veSacThaiTg(duLieu, mau()); }); });
    });
    var laBl = tt.tgNguon === "bl";
    var x = laBl ? d.binh_luan_da_cao.xu_huong : d.xu_huong;
    var lop = laBl ? SAC4 : SAC4.concat([NHA]);
    var g = gom(x, lop.map(function (s) { return KHOA_SAC[s]; }), tt.che);
    nhomNut($("che-sac-thai-tg"), cacChe(x), g.cd, doiChe);
    var o = coBan(m);
    o.grid.top = 40;
    o.legend.data = lop.map(function (s) { return TEN_SAC[s]; });
    o.xAxis = trucDanhMuc(m, g.ten);
    o.xAxis.boundaryGap = false;
    o.yAxis = trucSo(m);
    o.series = lop.map(function (s) {
      var phu = s === CHUA || s === NHA;
      return { name: TEN_SAC[s], type: "line", data: g.du[KHOA_SAC[s]], smooth: 0.25, smoothMonotone: "x",
               showSymbol: g.n <= 45, symbol: "circle", symbolSize: 6,
               lineStyle: { width: phu ? 1.5 : 2.2, type: phu ? "dashed" : "solid", color: m.sac[s] },
               itemStyle: { color: m.sac[s], borderColor: m.mat, borderWidth: 1.5 },
               emphasis: { focus: "series" } };
    });
    ve("bd-sac-thai-tg", o);
    // Bấm gần một đường → đúng sắc thái đó; bấm chỗ trống → mọi sắc thái của mốc đó.
    xuLyBam["bd-sac-thai-tg:nen"] = function (e, bd) {
      var i = chiSoTuDiem(bd, e, g.n);
      if (i == null) return;
      var opt = bd.getOption(), chon = (opt.legend && opt.legend[0] && opt.legend[0].selected) || {};
      var tot = null, kc = 14;
      lop.forEach(function (s) {
        if (chon[TEN_SAC[s]] === false) return;
        var px = bd.convertToPixel({ gridIndex: 0 }, [i, g.du[KHOA_SAC[s]][i]]);
        if (px && Math.abs(px[1] - e.offsetY) < kc) { kc = Math.abs(px[1] - e.offsetY); tot = s; }
      });
      var kh = { ngay_tu: g.tu[i], ngay_den: g.den[i] };
      if (tot) kh.sac_thai = tot;
      if (laBl) kh.loai_bl = "hop_le";
      moChiTiet(laBl ? "binh-luan" : "bai", kh, (tot ? TEN_SAC[tot] + " · " : "") + moTaKhoang(kh));
    };
  }

  // ─── sắc thái thảo luận theo chủ đề (hàng 100% kiểu Kompa) ───
  function veChuDe(d) {
    var b = d.binh_luan_da_cao, coBl = coBinhLuan(d);
    if (!coBl) tt.cdNguon = "bai";
    nhomNut($("nguon-chu-de"), nutNguon(coBl), tt.cdNguon, function (v) {
      tt.cdNguon = v;
      tt.cdMo = false;
      giuTapTrung($("nguon-chu-de"), function () { chay("chủ đề", function () { veChuDe(duLieu); }); });
    });
    var laBl = tt.cdNguon === "bl";
    var ds = (laBl ? b.chu_de : d.sac_thai_chu_de) || [];
    var don = laBl ? "bình luận" : "bài";
    var tong = ds.reduce(function (a, x) { return a + x.so; }, 0);
    var tom = $("cd-tom-tat");
    xoa(tom);
    if (ds.length) {
      tom.appendChild(tao("b", "", so(ds.length)));
      tom.appendChild(chuNode(" chủ đề trên "));
      tom.appendChild(tao("b", "", so(tong)));
      tom.appendChild(chuNode(" " + don + (laBl ? " hợp lệ" : " (không tính kênh nhà)")));
    } else {
      tom.textContent = " ";
    }
    var el = $("chu-de");
    xoa(el);
    if (!ds.length) {
      el.appendChild(tao("div", "trong", laBl ? "Chưa có bình luận được gán chủ đề." : "Chưa có bài được gán chủ đề."));
      return;
    }
    (tt.cdMo ? ds : ds.slice(0, 8)).forEach(function (x) { el.appendChild(hangChuDe(x, don, laBl)); });
    if (ds.length > 8) {
      el.appendChild(nut(tt.cdMo ? "Thu gọn" : "Xem thêm " + (ds.length - 8) + " chủ đề", "nut nut--nhe nut--nho cs-cd__them", function () {
        tt.cdMo = !tt.cdMo;
        veChuDe(duLieu);
        var t = $("chu-de").querySelector(".cs-cd__them");
        if (t) t.focus();
      }));
    }
  }
  function tenChuDe(cd) { return cd === CHUA ? "Chưa phân loại chủ đề" : cd; }
  function hangChuDe(x, don, laBl) {
    var h = tao("div", "cs-cd__hang");
    var ten = tao("div", "cs-cd__ten", tenChuDe(x.chu_de));
    ten.title = tenChuDe(x.chu_de);
    h.appendChild(ten);
    var th = tao("div", "cs-cd__thanh");
    th.setAttribute("role", "group");
    th.setAttribute("aria-label", "Sắc thái của " + tenChuDe(x.chu_de));
    SAC4.forEach(function (s) {
      var v = x[s] || 0;
      if (!v) return;
      var p = 100 * v / (x.so || 1);
      var b = nut(p >= 9 ? Math.round(p) + "%" : "", "cs-cd__doan cs-cd__doan--" + LOP_SAC[s], function () { moChuDe(x.chu_de, s, laBl); });
      b.style.flexGrow = String(v);
      b.title = TEN_SAC[s] + ": " + so(v) + " " + don + " (" + ptCua(v, x.so) + ")";
      b.setAttribute("aria-label", tenChuDe(x.chu_de) + " — " + b.title);
      th.appendChild(b);
    });
    h.appendChild(th);
    var sl = tao("div", "cs-cd__so");
    sl.appendChild(tao("b", "so", so(x.so)));
    sl.appendChild(chuNode(" " + don));
    h.appendChild(sl);
    var ct = nut("Chi tiết", "nut nut--nhe nut--nho cs-cd__nut", function () { moChuDe(x.chu_de, null, laBl); });
    ct.setAttribute("aria-label", "Chi tiết: " + tenChuDe(x.chu_de));
    h.appendChild(ct);
    return h;
  }
  function moChuDe(cd, s, laBl) {
    if (laBl) {                                        // bình luận: lọc luồng bình luận bên dưới
      datLocBl({ chu_de: cd, sac_thai: s || "", loai_bl: "hop_le", q: "", nguon_bl: "", nen_tang_bl: "" }, true);
      return;
    }
    var dk = { chu_de: cd };
    if (s) dk.sac_thai = s;
    moChiTiet("bai", dk, tenChuDe(cd) + (s ? " · " + TEN_SAC[s] : ""));
  }

  // ─── từ khoá nổi bật: mây từ tự xếp (xoắn ốc + va chạm hộp) ───
  var may = { ds: [], rong: 0 };
  function lopTu(x) {
    var tot = TL, v = -1;
    SAC4.forEach(function (s) { if ((x[s] || 0) > v) { v = x[s] || 0; tot = s; } });
    return tot === TC ? "tc" : tot === TI ? "ti" : "tl";
  }
  function thanhTron(x) {
    var t = tao("div", "cs-tron");
    SAC4.forEach(function (s) {
      var v = x[s] || 0;
      if (!v) return;
      var p = tao("span", "cs-nen-" + LOP_SAC[s]);
      p.style.flex = v + " 1 0";
      t.appendChild(p);
    });
    return t;
  }
  function noiTu(o, x) {
    o.appendChild(tao("div", "cs-noi__tieu-de", "“" + x.tu + "”"));
    o.appendChild(tao("div", "cs-noi__so", so(x.so_bai) + " thảo luận nhắc tới · bấm để xem"));
    o.appendChild(thanhTron(x));
    SAC4.forEach(function (s) {
      if (!x[s]) return;
      var d = tao("div", "cs-noi__dong");
      d.appendChild(tao("span", "cs-chip__cham cs-nen-" + LOP_SAC[s]));
      d.appendChild(chuNode(TEN_SAC[s]));
      d.appendChild(tao("span", "so", so(x[s]) + " · " + ptCua(x[s], x.so_bai)));
      o.appendChild(d);
    });
  }
  function ganTu(b, x) {
    function hien() { hienNoi(b, function (o) { noiTu(o, x); }); }
    function an() { anNoi(b); }
    b.addEventListener("mouseenter", hien);
    b.addEventListener("focus", hien);
    b.addEventListener("mouseleave", an);
    b.addEventListener("blur", an);
    b.addEventListener("click", function () { anNoi(); moTuKhoa(x); });
  }
  function veTuKhoa(d) {
    may.ds = (d.tu_khoa || []).slice().sort(function (a, b) { return b.so_bai - a.so_bai || (a.tu < b.tu ? -1 : 1); });
    var tom = $("tk-tom-tat");
    xoa(tom);
    if (may.ds.length) {
      tom.appendChild(chuNode("Top "));
      tom.appendChild(tao("b", "", so(may.ds.length)));
      tom.appendChild(chuNode(" từ khoá"));
      if (d.tu_khoa_tong != null) {
        tom.appendChild(chuNode(" trên tổng "));
        tom.appendChild(tao("b", "", so(d.tu_khoa_tong)));
        tom.appendChild(chuNode(" thảo luận"));
      }
    } else {
      tom.textContent = " ";
    }
    veKieuTu();
  }
  function veKieuTu() {
    var laMay = tt.tkDang === "may";
    nhomNut($("tk-che"), [{ gt: "may", chu: "Mây từ" }, { gt: "bang", chu: "Bảng" }], tt.tkDang, function (v) {
      tt.tkDang = v;
      giuTapTrung($("tk-che"), veKieuTu);
    });
    $("tk-may").hidden = !laMay;
    $("tk-bang").hidden = laMay;
    if (!laMay) { veBangTu(); return; }
    xepMay();
    // Đo chữ phải đúng phông đã nạp: phông chưa sẵn thì xếp lại một lần khi nạp xong.
    if (document.fonts && document.fonts.status !== "loaded") {
      document.fonts.ready.then(function () { if (tt.tkDang === "may") xepMay(); });
    }
  }
  function xepMay() {
    var el = $("tk-may"), ds = may.ds;
    anNoi();
    xoa(el);
    el.classList.remove("cs-may--san");
    $("tk-ghi-chu").textContent = "";
    if (!ds.length) {
      el.appendChild(tao("div", "trong", "Chưa đủ thảo luận để có từ khoá nổi bật (cụm phải xuất hiện ở ít nhất 2 thảo luận)."));
      return;
    }
    var W = el.clientWidth, H = el.clientHeight;
    if (!W || !H) return;
    may.rong = W;
    var vmax = ds[0].so_bai, vmin = ds[ds.length - 1].so_bai;
    var k = Math.max(0.62, Math.min(1.2, W / 620));
    var fMin = 12, fMax = Math.round((ds.length < 20 ? 50 : 44) * k);
    var cac = ds.map(function (x) {
      var t = vmax === vmin ? 0.55 : Math.sqrt((x.so_bai - vmin) / (vmax - vmin));
      var f = fMin + (fMax - fMin) * t;
      var b = nut(x.tu, "cs-may__tu cs-may__tu--" + lopTu(x) + (t > 0.55 ? " cs-may__tu--dam" : ""));
      b.style.fontSize = f.toFixed(1) + "px";
      b.setAttribute("aria-label", x.tu + ": " + so(x.so_bai) + " thảo luận — bấm để xem");
      ganTu(b, x);
      el.appendChild(b);
      return { b: b, f: f };
    });
    // Đo, co/giãn đều cỡ chữ cho tổng diện tích chữ ≈ 55% khung, xếp; còn từ rơi ra ngoài thì
    // thu nhỏ 12% rồi xếp lại (tối đa 4 lượt) — từ to nhất luôn to nhất, cả 50 từ đều có chỗ.
    function doCo() {
      cac.forEach(function (n) { n.w = n.b.offsetWidth; n.h = n.b.offsetHeight; });
      return cac.reduce(function (a, n) { return a + (n.w + 4) * (n.h + 2); }, 0);
    }
    function coChu(heSo) {
      cac.forEach(function (n) {
        n.f = Math.max(11, n.f * heSo);
        n.b.style.fontSize = n.f.toFixed(1) + "px";
        n.b.hidden = false;
      });
      return doCo();
    }
    var dienTich = doCo(), muc = 0.55 * W * H;
    if (dienTich > muc || dienTich < muc * 0.7) dienTich = coChu(Math.max(0.4, Math.min(1.4, Math.sqrt(muc / dienTich))));
    var dat = [], an = 0, cx = W / 2, cy = H / 2, gian = Math.max(1, W / H) * 0.85;
    function dung(x, y, w, h) {
      for (var i = 0; i < dat.length; i++) {
        var o = dat[i];
        if (x < o.x + o.w + 4 && x + w + 4 > o.x && y < o.y + o.h + 2 && y + h + 2 > o.y) return true;
      }
      return false;
    }
    function tim(w, h, goc) {
      var th = 0, a = 2.2;
      for (var buoc = 0; buoc < 6000; buoc++) {
        var r = a * th;
        if (r > Math.max(W, H)) break;
        var x = cx + r * Math.cos(th + goc) * gian - w / 2, y = cy + r * Math.sin(th + goc) - h / 2;
        if (x >= 2 && y >= 2 && x + w <= W - 2 && y + h <= H - 2 && !dung(x, y, w, h)) return { x: x, y: y, w: w, h: h };
        th += Math.max(0.02, 6 / Math.max(r * gian, 6));
      }
      return null;
    }
    function xep() {
      dat = [];
      an = 0;
      cac.forEach(function (n, i) {
        var cho = tim(n.w, n.h, i * 2.39996);              // góc vàng: từ toả đều quanh tâm
        if (!cho) { n.b.hidden = true; an++; return; }
        n.b.style.left = Math.round(cho.x) + "px";
        n.b.style.top = Math.round(cho.y) + "px";
        dat.push(cho);
      });
    }
    xep();
    for (var lanXep = 0; an && lanXep < 4; lanXep++) { coChu(0.88); xep(); }
    if (an) $("tk-ghi-chu").textContent = "Hiện " + (ds.length - an) + "/" + ds.length + " từ — xem đủ ở dạng Bảng.";
    if (window.requestAnimationFrame && !giamDong) {
      window.requestAnimationFrame(function () { el.classList.add("cs-may--san"); });
    } else {
      el.classList.add("cs-may--san");
    }
  }
  function veBangTu() {
    var el = $("tk-bang"), ds = may.ds;
    xoa(el);
    $("tk-ghi-chu").textContent = "";
    if (!ds.length) { el.appendChild(tao("li", "trong", "Chưa có từ khoá nổi bật.")); return; }
    var max = ds[0].so_bai || 1;
    ds.forEach(function (x, i) {
      var li = tao("li");
      var b = nut("", "cs-bang-tu__dong", function () { moTuKhoa(x); });
      b.appendChild(tao("span", "cs-bang-tu__hang", String(i + 1)));
      b.appendChild(tao("span", "cs-bang-tu__tu cs-may__tu--" + lopTu(x), x.tu));
      var t = thanhTron(x);
      t.style.width = Math.max(10, Math.round(100 * x.so_bai / max)) + "%";
      b.appendChild(t);
      b.appendChild(tao("span", "cs-bang-tu__so", so(x.so_bai)));
      b.title = x.tu + " — " + SAC4.filter(function (s) { return x[s]; }).map(function (s) { return TEN_SAC[s] + " " + so(x[s]); }).join(" · ");
      b.setAttribute("aria-label", x.tu + ": " + so(x.so_bai) + " thảo luận — bấm để xem");
      li.appendChild(b);
      el.appendChild(li);
    });
  }

  // ─── phân bố theo nền tảng / loại nguồn (thanh ngang HTML) ───
  function dsThanh(el, ds, dau, bamVao) {
    xoa(el);
    if (!ds.length) { el.appendChild(tao("div", "trong", "Chưa có bài trong khoảng này.")); return; }
    var max = Math.max.apply(null, ds.map(function (x) { return x.thao_luan; }).concat([1]));
    var tong = ds.reduce(function (a, x) { return a + x.thao_luan; }, 0) || 1;
    ds.forEach(function (x) {
      var b = nut("", "cs-thanh", function () { bamVao(x); });
      var ten = tao("span", "cs-thanh__ten");
      var bt = dau(x);
      if (bt) ten.appendChild(bt);
      ten.appendChild(tao("span", "", x.ten));
      b.appendChild(ten);
      var ray = tao("span", "cs-thanh__ray"), dac = tao("span", "cs-thanh__dac");
      dac.style.width = (100 * x.thao_luan / max).toFixed(1) + "%";
      dac.style.background = "var(--s1)";
      ray.appendChild(dac);
      b.appendChild(ray);
      var gt = tao("span", "cs-thanh__gt");
      gt.appendChild(tao("b", "so", so(x.thao_luan)));
      gt.appendChild(chuNode(" · " + so(x.bai) + " bài · " + Math.round(100 * x.thao_luan / tong) + "%"));
      b.appendChild(gt);
      b.setAttribute("aria-label", x.ten + ": " + so(x.thao_luan) + " thảo luận, " + so(x.bai) + " bài — bấm để xem bài");
      el.appendChild(b);
    });
  }
  function vePhanBo(d) {
    dsThanh($("nen-tang"), d.nen_tang || [], function (x) { return huyHieuNT(x.nen_tang, false, true); },
            function (x) { moChiTiet("bai", { nen_tang: x.nen_tang }, x.ten); });
    dsThanh($("loai-nguon"), d.loai_nguon || [], function () { return null; },
            function (x) { moChiTiet("bai", { loai: x.loai }, x.ten); });
  }

  // ─── bảng ───
  function bang(cot, dong) {
    var t = tao("table", "cs-bang"), th = tao("thead"), tr = tao("tr");
    cot.forEach(function (c) { tr.appendChild(tao("th", c.so ? "so" : "", c.ten)); });
    th.appendChild(tr);
    t.appendChild(th);
    var tb = tao("tbody");
    dong.forEach(function (r) {
      var hang = tao("tr");
      cot.forEach(function (c) {
        var td = tao("td", c.so ? "so" : (c.lop || ""));
        if (c.ten) td.setAttribute("data-nhan", c.ten);
        var v = c.lay(r);
        if (v instanceof Node) td.appendChild(v); else td.textContent = v;
        hang.appendChild(td);
      });
      tb.appendChild(hang);
    });
    t.appendChild(tb);
    var k = tao("div", "cuon-ngang");
    k.appendChild(t);
    return k;
  }

  function veTopNguon(d) {
    var tabs = $("tab-nen-tang"), noiDung = $("top-nguon");
    xoa(tabs);
    xoa(noiDung);
    if (!d.top_nguon.length) { noiDung.appendChild(tao("div", "trong", "Chưa có bài trong khoảng này.")); return; }
    if (!d.top_nguon.some(function (x) { return x.nen_tang === nenTangChon; })) nenTangChon = d.top_nguon[0].nen_tang;
    d.top_nguon.forEach(function (g) {
      var b = nut("", "", function () {
        nenTangChon = g.nen_tang;
        veTopNguon(duLieu);
        var t = $("tab-nen-tang").querySelector('[aria-selected="true"]');
        if (t) t.focus();
      });
      b.appendChild(huyHieuNT(g.nen_tang, false, true));
      b.appendChild(chuNode(g.ten_nen_tang + " · " + so(g.so_nguon)));
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", g.nen_tang === nenTangChon ? "true" : "false");
      tabs.appendChild(b);
    });
    var g = d.top_nguon.filter(function (x) { return x.nen_tang === nenTangChon; })[0];
    noiDung.appendChild(bang([
      { ten: "Nguồn", lay: function (r) {
        var w = tao("div", "cs-o-nguon");
        w.appendChild(anhDaiDien(r.ten));
        var c = tao("div", "cs-o-nguon__chu");
        c.appendChild(linkAnToan(r.link, r.ten));
        if (r.dinh_danh && r.dinh_danh !== r.ten) c.appendChild(tao("div", "mo nho", r.dinh_danh));
        w.appendChild(c);
        return w; } },
      { ten: "Loại", lay: function (r) { return chip(r.ten_loai, r.loai === "kenh_nha" ? "nha" : "nguon"); } },
      { ten: "Bài", so: true, lay: function (r) { return so(r.bai); } },
      { ten: "Bình luận", so: true, lay: function (r) { return so(r.binh_luan); } },
      { ten: "Thảo luận", so: true, lay: function (r) { return tao("b", "", so(r.thao_luan)); } },
      { ten: "Lượt xem", so: true, lay: function (r) { return so(r.xem); } },
      { ten: "", lay: function (r) {
        var b = nut("Xem bài", "nut nut--nhe nut--nho", function () {
          moChiTiet("bai", { nguon: r.khoa_nguon, nen_tang: g.nen_tang }, r.ten);
        });
        b.setAttribute("aria-label", "Xem bài của " + r.ten);
        return b; } }
    ], g.nguon));
  }

  function veTopBai(d) {
    var el = $("top-bai");
    xoa(el);
    if (!d.top_bai.length) { el.appendChild(tao("div", "trong", "Chưa có bài trong khoảng này.")); return; }
    var GON = 10, ds = tt.baiMo ? d.top_bai : d.top_bai.slice(0, GON);
    el.appendChild(bang([
      { ten: "Bài", lay: function (r) {
        var w = tao("div", "cs-o-bai");
        w.appendChild(huyHieuNT(r.nen_tang, false));
        var c = tao("div", "cs-o-bai__chu");
        c.appendChild(linkAnToan(r.link, r.noi_dung || r.link || "(không có chữ)"));
        c.appendChild(tao("div", "cs-o-bai__phu", (r.tac_gia || "?") + " · " + (TEN_NT[r.nen_tang] || r.nen_tang) +
                          " · " + ngayDu(r.dang_luc) + (r.loai ? " · " + r.loai : "")));
        w.appendChild(c);
        return w; } },
      { ten: "Sắc thái", lay: function (r) { return chipSac(r.sac_thai); } },
      { ten: "Thảo luận", so: true, lay: function (r) { return tao("b", "", so(r.thao_luan)); } },
      { ten: "Xem", so: true, lay: function (r) { return so(r.xem); } },
      { ten: "Thích", so: true, lay: function (r) { return so(r.thich); } },
      { ten: "Chia sẻ", so: true, lay: function (r) { return so(r.chia_se); } },
      { ten: "Bình luận đã đọc", lay: function (r) {
        if (!r.bl_da_lay) return "—";
        var b = nut("", "nut nut--nhe nut--nho cs-nut-bl", function () { moMotBai(r); });
        b.appendChild(bieuTuong("bl"));
        b.appendChild(chuNode(so(r.bl_da_lay)));
        b.setAttribute("aria-label", "Đọc " + so(r.bl_da_lay) + " bình luận của bài này");
        return b; } }
    ], ds));
    if (d.top_bai.length > GON) {
      el.appendChild(nut(tt.baiMo ? "Thu gọn" : "Xem thêm " + (d.top_bai.length - GON) + " bài", "nut nut--nhe nut--nho cs-them-bai", function () {
        tt.baiMo = !tt.baiMo;
        veTopBai(duLieu);
        var t = $("top-bai").querySelector(".cs-them-bai");
        if (t) t.focus();
      }));
    }
  }

  // ─── bình luận: tổng quan (cột bên) ───
  function oSo(nhan, gt, phu, cham, rong) {
    var o = tao("div", "cs-o-so" + (rong ? " cs-o-so--rong" : ""));
    var n = tao("div", "cs-o-so__nhan");
    if (cham) { var c = tao("span", "cs-kpi__cham"); c.style.background = cham; n.appendChild(c); }
    n.appendChild(chuNode(nhan));
    o.appendChild(n);
    o.appendChild(tao("div", "cs-o-so__so", gt));
    if (phu) o.appendChild(tao("div", "cs-o-so__phu", phu));
    return o;
  }
  function veBinhLuan(d) {
    var b = d.binh_luan_da_cao, el = $("kpi-bl");
    if (!b || !el) return;
    var k = b.kpi, kp = d.kpi;
    var phu = kp.bl_nen_tang_bao_bai_da_cao ? Math.min(100, Math.round(1000 * kp.bl_da_cao / kp.bl_nen_tang_bao_bai_da_cao) / 10) : null;
    $("don-vi-bl").textContent = so(k.so) + " bình luận đã cào trên " + so(k.so_bai) + " bài" + (phu != null ? " · độ phủ " + pt(phu) : "");
    xoa(el);
    el.appendChild(oSo("Đã cào (thô)", so(k.so), "trên " + so(k.so_bai) + " bài" + (phu != null ? " · phủ " + pt(phu) : "")));
    el.appendChild(oSo("Thảo luận sạch", so(k.sach), "đã lọc " + so(k.da_loc) + (k.thuong_hieu ? " · " + so(k.thuong_hieu) + " thương hiệu" : "")));
    el.appendChild(oSo("Tích cực", pt(k.tich_cuc_pt), so(k.tich_cuc) + " bình luận", "var(--cs-tc)"));
    el.appendChild(oSo("Tiêu cực", pt(k.tieu_cuc_pt), so(k.tieu_cuc) + " bình luận", "var(--cs-ti)"));
    el.appendChild(oSo("Trung lập", pt(k.trung_lap_pt), so(k.trung_lap) + " bình luận", "var(--cs-tl)"));
    el.appendChild(oSo("Chưa phân loại", so(k.chua_phan_loai), "bình luận hợp lệ", "var(--cs-chua)"));
    $("trong-bl").hidden = k.so > 0;
    veLoaiBl();
  }
  function veLoaiBl() {
    var b = duLieu && duLieu.binh_luan_da_cao;
    var thanh = $("loai-bl-thanh"), ds = $("loai-bl");
    if (!b || !thanh) return;
    xoa(thanh);
    xoa(ds);
    var loai = b.loai || [];
    var tong = loai.reduce(function (a, x) { return a + x.so; }, 0);
    if (!loai.length) { ds.appendChild(tao("div", "mo nho", "Chưa có bình luận.")); return; }
    loai.forEach(function (x) {
      var mauL = "var(" + (MAU_LOAI_BL[x.loai] || "--chu-mo") + ")";
      var p = tao("span");
      p.style.flex = x.so + " 1 0";
      p.style.background = mauL;
      p.title = x.ten + ": " + so(x.so);
      thanh.appendChild(p);
      var dang = bl.loc.loai_bl === x.loai;
      var n = nut("", "cs-loai__dong", function () { datLocBl({ loai_bl: dang ? "" : x.loai }, false); });
      var c = tao("span", "cs-o-mau");
      c.style.background = mauL;
      n.appendChild(c);
      n.appendChild(tao("span", "", x.ten + (tong ? " · " + Math.round(100 * x.so / tong) + "%" : "")));
      n.appendChild(tao("span", "so", so(x.so)));
      n.setAttribute("aria-pressed", dang ? "true" : "false");
      n.title = dang ? "Bỏ lọc " + x.ten : "Chỉ xem bình luận " + x.ten.toLowerCase();
      ds.appendChild(n);
    });
  }

  // ─── bình luận: luồng có bộ lọc theo trường (kiểu Kompa) ───
  var MOI_TRANG_BL = 20;
  var MAC_DINH = { q: "", nen_tang_bl: "", nguon_bl: "", sac_thai: "", chu_de: "", loai_bl: "hop_le", sap_xep: "thich" };
  var bl = { loc: Object.assign({}, MAC_DINH), ten: {}, trang: 0, soTrang: 0, tong: 0, facets: null, ctl: null, daTai: false };
  var TRUONG = [
    { k: "nen_tang_bl", f: "nen_tang", ten: "Nền tảng" },
    { k: "nguon_bl", f: "nguon", ten: "Nguồn", tim: true },
    { k: "sac_thai", f: "sac_thai", ten: "Sắc thái" },
    { k: "chu_de", f: "chu_de", ten: "Chủ đề", tim: true },
    { k: "loai_bl", f: "loai", ten: "Nhãn lọc" }
  ];
  var truongNut = {};
  var popMo = null;

  function tenGiaTri(t, v) {
    if (!v) return "";
    if (t.k === "nen_tang_bl") return TEN_NT[v] || v;
    if (t.k === "loai_bl") return TEN_LOAI_BL[v] || v;
    if (t.k === "sac_thai") return TEN_SAC[v] || v;
    if (t.k === "chu_de") return v === CHUA ? "Chưa phân loại" : v;
    if (t.k === "nguon_bl") {
      if (bl.ten[v]) return bl.ten[v];
      var f = (bl.facets && bl.facets.nguon) || [];
      for (var i = 0; i < f.length; i++) if (f[i].gia_tri === v) return f[i].ten;
    }
    return v;
  }
  function khacMacDinh() {
    return Object.keys(MAC_DINH).some(function (k) { return k !== "sap_xep" && bl.loc[k] !== MAC_DINH[k]; });
  }
  function datLocBl(thay, cuon) {
    Object.keys(thay).forEach(function (k) { bl.loc[k] = thay[k] == null ? "" : thay[k]; });
    // Sắc thái / chủ đề chỉ có nghĩa với bình luận hợp lệ.
    if ((thay.sac_thai || thay.chu_de) && bl.loc.loai_bl && bl.loc.loai_bl !== "hop_le") bl.loc.loai_bl = "hop_le";
    if (thay.loai_bl && thay.loai_bl !== "hop_le") { bl.loc.sac_thai = ""; bl.loc.chu_de = ""; }
    var o = $("bl-tim");
    if (o && o.value.trim() !== bl.loc.q) o.value = bl.loc.q;
    var sx = $("bl-sap-xep");
    if (sx) sx.value = bl.loc.sap_xep;
    taiBl(false);
    if (cuon) cuonToiBl();
  }
  function cuonToiBl() {
    var k = $("khoi-bl"), h = $("bl-tieu-de");
    if (!k) return;
    var r = k.getBoundingClientRect();
    if (r.top < 56 || r.top > window.innerHeight * 0.5) k.scrollIntoView({ behavior: giamDong ? "auto" : "smooth", block: "start" });
    try { h.focus({ preventScroll: true }); } catch (_) { h.focus(); }
  }

  function taoTruong() {
    var w = $("bl-truong");
    if (!w) return;
    xoa(w);
    TRUONG.forEach(function (t) {
      var bo = tao("div", "cs-truong");
      var b = nut("", "cs-truong__nut", function () {
        if (popMo && popMo.t === t) dongPop(true); else moPop(t);
      });
      b.setAttribute("aria-haspopup", "listbox");
      b.setAttribute("aria-expanded", "false");
      b.appendChild(tao("span", "", t.ten));
      b.appendChild(bieuTuong("xuong"));
      bo.appendChild(b);
      w.appendChild(bo);
      truongNut[t.k] = { bo: bo, b: b };
    });
  }
  function capNhatTruong() {
    TRUONG.forEach(function (t) {
      var x = truongNut[t.k];
      if (!x) return;
      var v = bl.loc[t.k], chu = v ? t.ten + ": " + tenGiaTri(t, v) : t.ten;
      x.b.firstChild.textContent = chu;
      x.b.classList.toggle("cs-truong__nut--dang", !!v);
      x.b.title = v ? chu : "Lọc theo " + t.ten.toLowerCase();
    });
    if (popMo) popMo.veDs();
  }
  function moPop(t) {
    dongPop(false);
    var x = truongNut[t.k];
    var pop = tao("div", "cs-pop");
    pop.id = "cs-pop-" + t.k;
    var o = { t: t, pop: pop, nut: x.b, loc: "" };
    var muc0 = (bl.facets && bl.facets[t.f]) || [];
    var tim = null;
    if (t.tim && muc0.length > 7) {
      tim = tao("input", "cs-pop__tim");
      tim.type = "search";
      tim.placeholder = "Tìm " + t.ten.toLowerCase() + "…";
      tim.setAttribute("aria-label", "Tìm " + t.ten.toLowerCase());
      tim.addEventListener("input", function () { o.loc = tim.value; o.veDs(); });
      pop.appendChild(tim);
    }
    var dsEl = tao("div", "cs-pop__ds");
    dsEl.setAttribute("role", "listbox");
    dsEl.setAttribute("aria-label", t.ten);
    pop.appendChild(dsEl);
    o.veDs = function () {
      xoa(dsEl);
      var muc = (bl.facets && bl.facets[t.f]) || [];
      var v = bl.loc[t.k];
      var ds = [{ gia_tri: "", ten: "Tất cả", so: null }].concat(muc);
      if (v && !muc.some(function (m) { return m.gia_tri === v; })) ds.splice(1, 0, { gia_tri: v, ten: tenGiaTri(t, v), so: 0 });
      var q = boDau(o.loc).trim(), co = 0;
      ds.forEach(function (m) {
        var ten = !m.gia_tri ? m.ten : t.k === "chu_de" || t.k === "sac_thai" ? tenGiaTri(t, m.gia_tri) : m.ten;
        if (q && m.gia_tri && boDau(ten).indexOf(q) < 0) return;
        if (m.gia_tri) co++;
        var b = nut("", "cs-pop__muc", function () { chonPop(t, m); });
        b.setAttribute("role", "option");
        b.setAttribute("aria-selected", m.gia_tri === v ? "true" : "false");
        var dau = tao("span", "cs-pop__dau");
        if (m.gia_tri === v) dau.appendChild(bieuTuong("dau"));
        b.appendChild(dau);
        var chu = tao("span", "cs-pop__chu");
        if (t.k === "nen_tang_bl" && m.gia_tri) chu.appendChild(huyHieuNT(m.gia_tri, false, true));
        if (t.k === "sac_thai" && m.gia_tri) chu.appendChild(tao("span", "cs-chip__cham cs-nen-" + (LOP_SAC[m.gia_tri] || "chua")));
        chu.appendChild(tao("span", "", ten));
        b.appendChild(chu);
        if (m.so != null) b.appendChild(tao("span", "cs-pop__so", so(m.so)));
        b.title = ten;
        dsEl.appendChild(b);
      });
      if (!muc.length) {
        dsEl.appendChild(tao("div", "cs-pop__trong", (t.k === "sac_thai" || t.k === "chu_de") && bl.loc.loai_bl && bl.loc.loai_bl !== "hop_le"
          ? "Chỉ áp dụng cho bình luận hợp lệ." : "Không có giá trị nào với bộ lọc hiện tại."));
      } else if (q && !co) {
        dsEl.appendChild(tao("div", "cs-pop__trong", "Không tìm thấy “" + o.loc.trim() + "”."));
      }
    };
    o.veDs();
    pop.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); dongPop(true); return; }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        var cac = Array.prototype.slice.call(dsEl.querySelectorAll(".cs-pop__muc"));
        if (!cac.length) return;
        e.preventDefault();
        var i = cac.indexOf(document.activeElement);
        i = e.key === "ArrowDown" ? (i + 1) % cac.length : (i <= 0 ? cac.length - 1 : i - 1);
        cac[i].focus();
      }
    });
    x.bo.appendChild(pop);
    x.b.setAttribute("aria-expanded", "true");
    x.b.setAttribute("aria-controls", pop.id);
    popMo = o;
    kepPop(pop);
    var dauTien = tim || dsEl.querySelector('[aria-selected="true"]') || dsEl.querySelector(".cs-pop__muc");
    if (dauTien) dauTien.focus();
  }
  // Kẹp popover trong khung nhìn (không để trang cuộn ngang trên điện thoại).
  function kepPop(pop) {
    pop.style.left = "";
    var r = pop.getBoundingClientRect(), vw = document.documentElement.clientWidth;
    if (r.right > vw - 8) pop.style.left = Math.round(Math.max(8 - r.left, vw - 8 - r.right)) + "px";
  }
  function dongPop(traTapTrung) {
    if (!popMo) return;
    var o = popMo;
    popMo = null;
    if (o.pop.parentNode) o.pop.parentNode.removeChild(o.pop);
    o.nut.setAttribute("aria-expanded", "false");
    o.nut.removeAttribute("aria-controls");
    if (traTapTrung) o.nut.focus();
  }
  function chonPop(t, m) {
    var o = {};
    o[t.k] = m.gia_tri;
    if (t.k === "nguon_bl" && m.gia_tri) bl.ten[m.gia_tri] = m.ten;
    dongPop(true);
    datLocBl(o, false);
  }
  document.addEventListener("mousedown", function (e) {
    if (popMo && !popMo.pop.contains(e.target) && !popMo.nut.contains(e.target)) dongPop(false);
  });
  document.addEventListener("focusin", function (e) {
    if (popMo && !popMo.pop.contains(e.target) && !popMo.nut.contains(e.target)) dongPop(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { if (popMo) dongPop(true); anNoi(); }
  });

  function chipLoc(chu, bo) {
    var c = tao("span", "cs-chip cs-chip--dang");
    c.appendChild(tao("span", "cs-chip__chu", chu));
    c.title = chu;
    var x = nut("", "cs-chip__x", bo);
    x.setAttribute("aria-label", "Bỏ lọc " + chu);
    x.appendChild(bieuTuong("dong"));
    c.appendChild(x);
    return c;
  }
  function xoaLoc() {
    datLocBl(Object.assign({}, MAC_DINH, { sap_xep: bl.loc.sap_xep }), false);
    var o = $("bl-tim");
    if (o) o.focus();
  }
  function veThanhLoc() {
    capNhatTruong();
    var ch = $("bl-dang-loc");
    xoa(ch);
    if (bl.loc.q) ch.appendChild(chipLoc("Tìm: “" + bl.loc.q + "”", function () { datLocBl({ q: "" }); }));
    TRUONG.forEach(function (t) {
      var v = bl.loc[t.k];
      if (!v) return;
      ch.appendChild(chipLoc(t.ten + ": " + tenGiaTri(t, v), function () {
        var o = {};
        o[t.k] = "";
        datLocBl(o);
      }));
    });
    if (khacMacDinh()) ch.appendChild(nut("Xoá lọc", "cs-nut-chu", xoaLoc));
    var dem = $("bl-dem");
    xoa(dem);
    dem.appendChild(tao("b", "", so(bl.tong)));
    dem.appendChild(chuNode(" bình luận"));
    veNutThem();
    veLoaiBl();
  }
  function veNutThem() {
    var k = $("bl-them-khoi");
    xoa(k);
    if (!bl.tong) return;
    var n = $("bl-ds").querySelectorAll(".cs-bl").length;
    if (bl.trang < bl.soTrang) {
      var b = nut("Tải thêm " + so(Math.min(MOI_TRANG_BL, bl.tong - n)) + " bình luận", "nut nut--nhe", function () { taiBl(true); });
      b.id = "bl-them-nut";
      k.appendChild(b);
    }
    k.appendChild(tao("span", "", "Đang hiện " + so(n) + "/" + so(bl.tong) + " bình luận"));
  }
  function trongLoc() {
    var o = tao("div", "cs-trong-loc");
    o.appendChild(tao("p", "", bl.loc.q ? "Không có bình luận nào khớp “" + bl.loc.q + "”." : "Không có bình luận nào khớp bộ lọc."));
    if (khacMacDinh()) o.appendChild(nut("Xoá lọc", "nut nut--nhe nut--nho", xoaLoc));
    return o;
  }
  // them = true: tải trang kế tiếp và nối vào; im = true: làm mới lặng lẽ (không mờ danh sách).
  function taiBl(them, im) {
    var ds = $("bl-ds");
    if (!ds) return;
    if (bl.ctl) bl.ctl.abort();
    var ctl = bl.ctl = taoCtl();
    var trang = them ? bl.trang + 1 : 1;
    if (!them) {
      if (!bl.daTai) {
        xoa(ds);
        for (var i = 0; i < 3; i++) ds.appendChild(tao("div", "cs-khung-cho cs-khung-cho--the"));
      } else if (!im) {
        ds.classList.add("cs-dang-doi");
      }
      ds.setAttribute("aria-busy", "true");
      if (!im) $("bl-dem").textContent = "Đang tải…";
    } else {
      var nt = $("bl-them-nut");
      if (nt) { nt.disabled = true; nt.textContent = "Đang tải…"; }
    }
    var dk = { trang: trang };
    Object.keys(bl.loc).forEach(function (k) { if (bl.loc[k]) dk[k] = bl.loc[k]; });
    goiApi("binh-luan", dk, { signal: ctl.signal, khiBan: function (g) {
      if (ctl === bl.ctl) $("bl-dem").textContent = "Máy chủ đang bận — thử lại sau " + g + " giây…";
    } })
      .then(function (j) {
        if (ctl !== bl.ctl) return;
        bl.daTai = true;
        bl.trang = j.trang;
        bl.soTrang = j.so_trang;
        bl.tong = j.tong;
        if (j.facets) bl.facets = j.facets;
        if (!them) xoa(ds);
        if (!them && !j.binh_luan.length) ds.appendChild(trongLoc());
        var frag = document.createDocumentFragment();
        j.binh_luan.forEach(function (c) { frag.appendChild(theBinhLuan(c, { danhDauTraLoi: true })); });
        ds.appendChild(frag);
        kiemKep(ds);
        veThanhLoc();
      })
      .catch(function (e) {
        if ((e && e.name === "AbortError") || ctl !== bl.ctl) return;
        var loi = tao("div", "thong-bao thong-bao--loi");
        loi.appendChild(chuNode(((e && e.message) || "Không tải được bình luận.") + " "));
        loi.appendChild(nut("Thử lại", "cs-nut-chu", function () { taiBl(them); }));
        if (!them) { xoa(ds); ds.appendChild(loi); $("bl-dem").textContent = ""; }
        else { veNutThem(); $("bl-them-khoi").appendChild(loi); }
      })
      .then(function () {
        if (ctl !== bl.ctl) return;
        bl.ctl = null;
        ds.classList.remove("cs-dang-doi");
        ds.removeAttribute("aria-busy");
      });
  }

  // ─── thẻ bình luận: trông như một bình luận thật ───
  function soLieu(bt, n, nhan) {
    var s = tao("span", "cs-so-lieu");
    s.title = so(n || 0) + " " + nhan;
    s.appendChild(bieuTuong(bt));
    s.appendChild(chuNode(so(n || 0)));
    s.appendChild(tao("span", "cs-an", " " + nhan));
    return s;
  }
  function linkMo(url, chu) {
    var a = linkAnToan(url, chu);
    a.appendChild(bieuTuong("mo"));
    return a;
  }
  function nutXemThem(p) {
    var b = nut("Xem thêm", "cs-xem-them", function () {
      var kep = p.classList.toggle("cs-kep");
      b.textContent = kep ? "Xem thêm" : "Thu gọn";
      b.setAttribute("aria-expanded", kep ? "false" : "true");
    });
    b.setAttribute("aria-expanded", "false");
    return b;
  }
  // Chữ dài bị kẹp 5 dòng; đo sau khi gắn vào trang — không tràn thì bỏ nút "Xem thêm".
  function kiemKep(goc) {
    var lam = function () {
      Array.prototype.forEach.call(goc.querySelectorAll(".cs-kep[data-kep]"), function (p) {
        p.removeAttribute("data-kep");
        if (p.scrollHeight <= p.clientHeight + 2) {
          p.classList.remove("cs-kep");
          var b = p.nextSibling;
          if (b && b.classList && b.classList.contains("cs-xem-them")) b.parentNode.removeChild(b);
        }
      });
    };
    if (window.requestAnimationFrame) window.requestAnimationFrame(lam); else lam();
  }
  function dongNguon(c) {
    var o = tao("div", "cs-bl__nguon");
    o.appendChild(huyHieuNT(c.nen_tang, false));
    var s = tao("span", "cs-bl__nguon-chu");
    var ng = (c.nguon && c.nguon.ten) || (c.bai && c.bai.tac_gia) || "nguồn không rõ";
    var phu = [(c.nguon && c.nguon.loai) || "", TEN_NT[c.nen_tang] || c.nen_tang || ""].filter(Boolean);
    s.appendChild(chuNode("Trên bài của "));
    s.appendChild(tao("b", "", ng));
    if (phu.length) s.appendChild(chuNode(" · " + phu.join(" · ")));
    s.title = "Trên bài của " + ng + (phu.length ? " · " + phu.join(" · ") : "");
    o.appendChild(s);
    var bai = c.bai || {};
    if (bai.noi_dung) {
      var tr = linkAnToan(bai.link, "“" + bai.noi_dung + "”", "cs-bl__trich");
      tr.title = urlHopLe(bai.link) ? "Mở bài: " + bai.noi_dung : bai.noi_dung;
      o.appendChild(tr);
    }
    return o;
  }
  // opt: boNguon (ẩn dòng nguồn — đang xem trong chính bài đó), danhDauTraLoi (hiện "↳ trả lời"),
  //      chuoi (có chỗ chứa trả lời con), nho (ảnh đại diện nhỏ cho trả lời).
  function theBinhLuan(c, opt) {
    opt = opt || {};
    var nha = !!c.cua_thuong_hieu || c.loai === "thuong_hieu";
    var daLoc = !!c.loai && c.loai !== "hop_le" && c.loai !== "thuong_hieu";
    var o = tao("article", "cs-bl" + (nha ? " cs-bl--nha" : "") + (daLoc ? " cs-bl--loc" : ""));
    if (!opt.boNguon) o.appendChild(dongNguon(c));
    var than = tao("div", "cs-bl__than");
    than.appendChild(anhDaiDien(c.tac_gia || "?", (nha ? "cs-av--nha" : "") + (opt.nho ? " cs-av--nho" : "")));
    var noiDung = tao("div", "cs-bl__noi");
    var bong = tao("div", "cs-bl__bong");
    var ten = tao("div", "cs-bl__ten");
    ten.appendChild(tao("b", "", c.tac_gia || "(ẩn danh)"));
    if (nha) {
      var nn = tao("span", "cs-bl__nha-nhan");
      nn.appendChild(bieuTuong("dau"));
      nn.appendChild(chuNode("Phản hồi từ thương hiệu"));
      ten.appendChild(nn);
    }
    if (c.la_tra_loi && opt.danhDauTraLoi) {
      var tl = tao("span", "cs-bl__tl");
      tl.appendChild(bieuTuong("tra_loi"));
      tl.appendChild(chuNode("trả lời"));
      ten.appendChild(tl);
    }
    bong.appendChild(ten);
    var nd = c.noi_dung || "";
    var p = tao("p", "cs-bl__chu", nd || "(không có chữ)");
    bong.appendChild(p);
    if (nd.length > 180 || nd.split("\n").length > 4) {
      p.classList.add("cs-kep");
      p.setAttribute("data-kep", "1");
      bong.appendChild(nutXemThem(p));
    }
    noiDung.appendChild(bong);
    var chan = tao("div", "cs-bl__chan");
    var td = thoiDiem(c.dang_luc);
    if (td) {
      var t = tao("time", "", td.chu);
      t.dateTime = c.dang_luc;
      t.title = td.day;
      chan.appendChild(t);
    }
    chan.appendChild(soLieu("tim", c.thich, "lượt thích"));
    if (c.tra_loi) chan.appendChild(soLieu("bl", c.tra_loi, "trả lời"));
    if (urlHopLe(c.link)) chan.appendChild(linkMo(c.link, "Mở bình luận"));
    if (!opt.boNguon && c.bai && urlHopLe(c.bai.link)) chan.appendChild(linkMo(c.bai.link, "Xem bài"));
    var the = tao("span", "cs-bl__the");
    if (daLoc) {
      var lyDo = String(c.ly_do_loc || "").replace(/_/g, " ");
      the.appendChild(chip(c.ten_loai || c.loai, "loc", "Đã lọc khỏi sắc thái" + (lyDo ? " — lý do: " + lyDo : "")));
    } else if (!nha) {
      the.appendChild(chipSac(c.sac_thai));
      if (c.chu_de) the.appendChild(chip(c.chu_de, "chu-de"));
    }
    if (the.childNodes.length) chan.appendChild(the);
    noiDung.appendChild(chan);
    if (opt.chuoi) noiDung.appendChild(tao("div", "cs-bl__con"));
    than.appendChild(noiDung);
    o.appendChild(than);
    return o;
  }
  // Xếp bình luận của MỘT bài thành chuỗi theo ma_cha (2 tầng như Facebook). Trả lời mà cha chưa
  // có (cha ở trang sau / không cào) thì đứng ở gốc kèm dấu "↳ trả lời".
  function veChuoi(ds, noiChua, map) {
    function dat(c, cha) {
      var t = theBinhLuan(c, { boNguon: true, chuoi: !cha, danhDauTraLoi: c.la_tra_loi && !cha, nho: !!cha });
      (cha || noiChua).appendChild(t);
      map[c.ma] = cha || t.querySelector(".cs-bl__con");
    }
    var cho = [];
    ds.forEach(function (c) {
      if (c.ma_cha && !map[c.ma_cha]) { cho.push(c); return; }
      dat(c, c.ma_cha ? map[c.ma_cha] : null);
    });
    for (var lan = 0; lan < 3 && cho.length; lan++) {
      cho = cho.filter(function (c) {
        if (!map[c.ma_cha]) return true;
        dat(c, map[c.ma_cha]);
        return false;
      });
    }
    cho.forEach(function (c) { dat(c, null); });
  }

  // ─── thẻ bài (ngăn chi tiết) ───
  function theBai(r, moSan) {
    var o = tao("article", "cs-bai");
    var dau = tao("div", "cs-bai__dau");
    dau.appendChild(anhDaiDien(r.tac_gia || "?"));
    var ten = tao("div", "cs-bai__ten");
    ten.appendChild(tao("b", "", r.tac_gia || "?"));
    var phu = tao("div", "cs-bai__phu");
    phu.appendChild(huyHieuNT(r.nen_tang, true));
    var td = thoiDiem(r.dang_luc);
    if (td) {
      var t = tao("time", "", td.chu);
      t.dateTime = r.dang_luc;
      t.title = td.day;
      phu.appendChild(chuNode("·"));
      phu.appendChild(t);
    }
    if (r.loai) { phu.appendChild(chuNode("·")); phu.appendChild(tao("span", "", r.loai)); }
    ten.appendChild(phu);
    dau.appendChild(ten);
    o.appendChild(dau);
    var nd = r.noi_dung || "";
    var p = tao("p", "cs-bai__chu", nd || "(không có chữ)");
    o.appendChild(p);
    if (nd.length > 280) {
      p.classList.add("cs-kep");
      p.setAttribute("data-kep", "1");
      o.appendChild(nutXemThem(p));
    }
    var nh = tao("div", "cs-bai__the");
    nh.appendChild(chipSac(r.sac_thai));
    if (r.chu_de) nh.appendChild(chip(r.chu_de, "chu-de"));
    o.appendChild(nh);
    var sl = tao("div", "cs-bai__so");
    var tl = tao("span", "");
    tl.appendChild(tao("b", "", so(r.thao_luan)));
    tl.appendChild(chuNode(" thảo luận"));
    sl.appendChild(tl);
    sl.appendChild(soLieu("bl", r.binh_luan, "bình luận nền tảng báo"));
    sl.appendChild(soLieu("mat", r.xem, "lượt xem"));
    sl.appendChild(soLieu("tim", r.thich, "lượt thích"));
    sl.appendChild(soLieu("chia", r.chia_se, "lượt chia sẻ"));
    o.appendChild(sl);
    var hd = tao("div", "cs-bai__hd");
    if (urlHopLe(r.link)) hd.appendChild(linkMo(r.link, "Mở bài gốc"));
    else hd.appendChild(tao("span", "mo", "Không có link bài"));
    var khoi = tao("div", "cs-chuoi");
    khoi.hidden = true;
    if (r.bl_da_lay) {
      var nb = nut("", "nut nut--nhe nut--nho", null);
      var chuNut = function (mo) {
        xoa(nb);
        nb.appendChild(bieuTuong("bl"));
        nb.appendChild(chuNode(mo ? "Ẩn bình luận" : "Xem " + so(r.bl_da_lay) + " bình luận đã đọc"));
        nb.setAttribute("aria-expanded", mo ? "true" : "false");
      };
      chuNut(false);
      var daNap = false;
      nb.addEventListener("click", function () {
        if (!khoi.hidden) { khoi.hidden = true; chuNut(false); return; }
        khoi.hidden = false;
        chuNut(true);
        if (!daNap) { daNap = true; napChuoi(r, khoi); }
      });
      hd.appendChild(nb);
      if (moSan) { khoi.hidden = false; chuNut(true); daNap = true; napChuoi(r, khoi); }
    } else if (r.binh_luan) {
      hd.appendChild(tao("span", "mo nho", "Bình luận chưa được cào"));
    }
    o.appendChild(hd);
    o.appendChild(khoi);
    return o;
  }
  function napChuoi(r, khoi) {
    var map = {}, ctl = ngan.ctl;
    function trang(t) {
      var cho = tao("div", "cs-khung-cho cs-khung-cho--the");
      khoi.appendChild(cho);
      goiApi("binh-luan", { khoa: r.khoa, trang: t }, { signal: ctl && ctl.signal })
        .then(function (j) {
          if (cho.parentNode) cho.parentNode.removeChild(cho);
          if (!j.binh_luan.length && t === 1) { khoi.appendChild(tao("div", "trong", "Chưa có bình luận đã đọc.")); return; }
          veChuoi(j.binh_luan, khoi, map);
          kiemKep(khoi);
          if (j.trang < j.so_trang) {
            var con = j.tong - khoi.querySelectorAll(".cs-bl").length;
            var b = nut("Tải thêm bình luận (còn " + so(Math.max(0, con)) + ")", "nut nut--nhe nut--nho", function () {
              b.parentNode.removeChild(b);
              trang(j.trang + 1);
            });
            khoi.appendChild(b);
          } else if (j.tong > 5) {
            khoi.appendChild(tao("div", "mo nho", "Đã hiện đủ " + so(j.tong) + " bình luận đã đọc · nhiều thích trước."));
          }
        })
        .catch(function (e) {
          if (e && e.name === "AbortError") return;
          if (cho.parentNode) cho.parentNode.removeChild(cho);
          khoi.appendChild(tao("div", "thong-bao thong-bao--loi", (e && e.message) || "Không tải được bình luận."));
        });
    }
    trang(1);
  }

  // ─── gọi API (503 bận: tự thử lại theo Retry-After, tối đa 3 lần; huỷ được bằng signal) ───
  function cho(ms, signal) {
    return new Promise(function (ok, hong) {
      var t = setTimeout(ok, ms);
      if (signal) {
        signal.addEventListener("abort", function () {
          clearTimeout(t);
          var e = new Error("Đã huỷ");
          e.name = "AbortError";
          hong(e);
        }, { once: true });
      }
    });
  }
  function goiApi(duong, dk, tuyChon) {
    tuyChon = tuyChon || {};
    var q = new URLSearchParams({ du_an: cfg.du_an, tu: cfg.tu, den: cfg.den });
    if (cfg.nen_tang) q.set("nen_tang", cfg.nen_tang);
    if (cfg.loai) q.set("loai", cfg.loai);
    Object.keys(dk || {}).forEach(function (k) { if (dk[k] != null && dk[k] !== "") q.set(k, dk[k]); });
    var url = "/api/" + duong + "?" + q.toString(), lan = 0;
    function thu() {
      return fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" }, signal: tuyChon.signal })
        .then(function (r) {
          if (r.status === 401) throw new Error("Phiên đăng nhập đã hết hạn — tải lại trang để đăng nhập lại.");
          if (r.status === 503 && lan < 3) {
            lan += 1;
            var giay = Math.min(10, Math.max(1, parseInt(r.headers.get("Retry-After"), 10) || 5));
            if (tuyChon.khiBan) tuyChon.khiBan(giay);
            return cho(giay * 1000, tuyChon.signal).then(thu);
          }
          return r.json().catch(function () { return null; }).then(function (j) {
            if (!r.ok) throw new Error(j && j.loi ? j.loi : "Không tải được dữ liệu.");
            return j;
          });
        });
    }
    return thu();
  }

  // ─── ngăn chi tiết (dialog trượt từ phải) ───
  var hop = $("chi-tiet");
  var ngan = { ctl: null, truoc: null, tapTrungTrang: false };
  function moHop() {
    if (!hop || hop.open) return;
    ngan.truoc = document.activeElement;
    if (hop.showModal) hop.showModal(); else hop.setAttribute("open", "");
    document.documentElement.classList.add("cs-khoa-cuon");
  }
  function dongHop() {
    if (!hop) return;
    if (hop.close) hop.close();
    else { hop.removeAttribute("open"); daDongHop(); }
  }
  function daDongHop() {
    document.documentElement.classList.remove("cs-khoa-cuon");
    if (ngan.ctl) { ngan.ctl.abort(); ngan.ctl = null; }
    var t = ngan.truoc;
    ngan.truoc = null;
    if (t && t.focus && t !== document.body && document.contains(t)) t.focus();
  }
  if (hop) {
    $("chi-tiet-dong").addEventListener("click", dongHop);
    hop.addEventListener("close", daDongHop);
    hop.addEventListener("click", function (e) {
      if (e.target !== hop) return;
      var r = hop.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dongHop();
    });
  }
  function batDauNgan(loaiChu, tieuDe) {
    if (ngan.ctl) ngan.ctl.abort();
    ngan.ctl = taoCtl();
    $("chi-tiet-loai").textContent = loaiChu;
    $("chi-tiet-tieu-de").textContent = tieuDe;
    $("chi-tiet-mo-ta").textContent = "Đang tải…";
    var tab = $("chi-tiet-tab");
    xoa(tab);
    tab.hidden = true;
    xoa($("chi-tiet-than"));
    xoa($("chi-tiet-trang"));
    moHop();
    return ngan.ctl;
  }
  function khungCho(than) {
    xoa(than);
    for (var i = 0; i < 3; i++) than.appendChild(tao("div", "cs-khung-cho cs-khung-cho--the"));
  }
  function moTaMacDinh(loai, j) {
    return loai === "bai"
      ? so(j.tong) + " bài · " + so(j.thao_luan) + " thảo luận (bài + bình luận nền tảng báo) · xếp theo thảo luận"
      : so(j.tong) + " bình luận đã đọc · xếp theo lượt thích";
  }
  function veDs(loai, j, napTrang, moTa) {
    var than = $("chi-tiet-than"), ph = $("chi-tiet-trang");
    xoa(than);
    xoa(ph);
    var ds = (loai === "bai" ? j.bai : j.binh_luan) || [];
    $("chi-tiet-mo-ta").textContent = moTa || moTaMacDinh(loai, j);
    if (!ds.length) than.appendChild(tao("div", "trong", "Không có " + (loai === "bai" ? "bài" : "bình luận") + " nào."));
    var frag = document.createDocumentFragment();
    ds.forEach(function (x) { frag.appendChild(loai === "bai" ? theBai(x) : theBinhLuan(x, { danhDauTraLoi: true })); });
    than.appendChild(frag);
    kiemKep(than);
    if (j.so_trang > 1) {
      var t = nut("← Trước", "nut nut--nhe nut--nho", function () { ngan.tapTrungTrang = true; napTrang(j.trang - 1); });
      t.disabled = j.trang <= 1;
      ph.appendChild(t);
      ph.appendChild(tao("span", "mo nho", "Trang " + j.trang + "/" + j.so_trang));
      var s = nut("Sau →", "nut nut--nhe nut--nho", function () { ngan.tapTrungTrang = true; napTrang(j.trang + 1); });
      s.disabled = j.trang >= j.so_trang;
      ph.appendChild(s);
    }
    than.scrollTop = 0;
    if (ngan.tapTrungTrang) {
      ngan.tapTrungTrang = false;
      var b = ph.querySelector("button:not([disabled])");
      if (b) b.focus();
    }
  }
  function taiDs(loai, dk, trang, ctl, moTa) {
    var than = $("chi-tiet-than");
    khungCho(than);
    xoa($("chi-tiet-trang"));
    return goiApi(loai, Object.assign({ trang: trang || 1 }, dk), { signal: ctl.signal, khiBan: function (g) {
      if (ctl === ngan.ctl) $("chi-tiet-mo-ta").textContent = "Máy chủ đang bận — thử lại sau " + g + " giây…";
    } })
      .then(function (j) {
        if (ctl !== ngan.ctl) return;
        veDs(loai, j, function (t) { taiDs(loai, dk, t, ctl, moTa); }, moTa);
      })
      .catch(function (e) {
        if ((e && e.name === "AbortError") || ctl !== ngan.ctl) return;
        xoa(than);
        $("chi-tiet-mo-ta").textContent = (e && e.message) || "Không tải được chi tiết.";
        than.appendChild(nut("Thử lại", "nut nut--nhe nut--nho", function () { taiDs(loai, dk, trang, ctl, moTa); }));
      });
  }
  // loai: "bai" | "binh-luan"; dk: điều kiện của điểm/cột vừa bấm; moTa: chữ cho tiêu đề.
  function moChiTiet(loai, dk, moTa) {
    if (!hop) return;
    var ctl = batDauNgan(loai === "bai" ? "Bài đăng" : "Bình luận", moTa);
    taiDs(loai, dk, 1, ctl);
  }
  // Từ khoá: hai thẻ Bình luận (q=) / Bài đăng (cum=) — từ khoá đếm trên cả bài lẫn bình luận.
  function moTuKhoa(x) {
    if (!hop) return;
    var ctl = batDauNgan("Từ khoá", "“" + x.tu + "”");
    var dk = { "binh-luan": { q: x.tu.slice(0, 100), loai_bl: "hop_le" }, bai: { cum: x.tu } };
    var kq = {}, chon = "binh-luan", tab = $("chi-tiet-tab"), than = $("chi-tiet-than");
    var tom = so(x.so_bai) + " thảo luận nhắc tới — " + SAC4.filter(function (s) { return x[s]; })
      .map(function (s) { return TEN_SAC[s].toLowerCase() + " " + so(x[s]); }).join(" · ");
    function veTab() {
      xoa(tab);
      tab.hidden = false;
      [["binh-luan", "Bình luận"], ["bai", "Bài đăng"]].forEach(function (l) {
        var b = nut(l[1] + (kq[l[0]] ? " · " + so(kq[l[0]].tong) : " · …"), "cs-phan__nut", function () {
          if (chon === l[0]) return;
          chon = l[0];
          veTab();
          hien();
          var t = tab.querySelector('[aria-selected="true"]');
          if (t) t.focus();
        });
        b.setAttribute("role", "tab");
        b.setAttribute("aria-selected", chon === l[0] ? "true" : "false");
        tab.appendChild(b);
      });
    }
    function hien() {
      if (kq[chon]) veDs(chon, kq[chon], napFn(chon), tom);
      else { khungCho(than); xoa($("chi-tiet-trang")); }
    }
    function napFn(l) { return function (t) { if (kq[l]) delete kq[l]; hien(); tai(l, t); }; }
    function tai(l, t) {
      return goiApi(l, Object.assign({ trang: t }, dk[l]), { signal: ctl.signal })
        .then(function (j) {
          if (ctl !== ngan.ctl) return;
          kq[l] = j;
          veTab();
          if (chon === l) veDs(l, j, napFn(l), tom);
        })
        .catch(function (e) {
          if ((e && e.name === "AbortError") || ctl !== ngan.ctl) return;
          kq[l] = { tong: 0, so_trang: 1, trang: 1, bai: [], binh_luan: [] };
          veTab();
          if (chon === l) { xoa(than); than.appendChild(tao("div", "thong-bao thong-bao--loi", (e && e.message) || "Không tải được.")); }
        });
    }
    veTab();
    hien();
    $("chi-tiet-mo-ta").textContent = tom;
    Promise.all([tai("binh-luan", 1), tai("bai", 1)]).then(function () {
      if (ctl !== ngan.ctl) return;
      if (chon === "binh-luan" && kq["binh-luan"] && !kq["binh-luan"].tong && kq.bai && kq.bai.tong) {
        chon = "bai";
        veTab();
        hien();
      }
    });
  }
  // Một bài (bảng Bài nổi bật): mở ngăn với đúng bài đó, tự mở chuỗi bình luận đã đọc.
  function moMotBai(r) {
    if (!hop) return;
    batDauNgan("Bài đăng", (r.tac_gia || "?") + " · " + ngayDu(r.dang_luc));
    $("chi-tiet-mo-ta").textContent = so(r.bl_da_lay) + " bình luận đã đọc của bài này · trả lời nằm dưới bình luận gốc.";
    $("chi-tiet-than").appendChild(theBai(r, true));
  }

  // ─── vẽ tất cả ───
  function veTatCa() {
    if (!duLieu) return;
    var d = duLieu, m = mau();
    chay("KPI", function () { veKpi(d); });
    chay("thảo luận", function () { veXuHuong(d, m); });
    chay("sắc thái", function () { veSacThai(d, m); });
    chay("sắc thái theo thời gian", function () { veSacThaiTg(d, m); });
    chay("chủ đề", function () { veChuDe(d); });
    chay("từ khoá", function () { veTuKhoa(d); });
    chay("phân bố", function () { vePhanBo(d); });
    chay("nguồn nổi bật", function () { veTopNguon(d); });
    chay("bài nổi bật", function () { veTopBai(d); });
    chay("bình luận", function () { veBinhLuan(d); });
    $("ky-truoc").textContent = "So với " + ngayDu(d.khoang.ky_truoc.tu) + " – " + ngayDu(d.khoang.ky_truoc.den) + " (kỳ liền trước cùng độ dài).";
    $("canh-bao").hidden = !d.bi_cat;
    $("canh-bao-bl").hidden = !d.bl_bi_cat;
  }

  function baoLoi(chu) {
    var el = $("loi-tai");
    el.textContent = chu;
    el.hidden = !chu;
  }
  function nhapSong() {
    var c = $("cham-song");
    if (!c || giamDong) return;
    c.classList.remove("cs-nhap");
    void c.offsetWidth;
    c.classList.add("cs-nhap");
  }

  // ─── tải dữ liệu ───
  // Máy chủ chỉ tính 2 lượt cùng lúc (503 khi bận): goiApi tự thử lại sau Retry-After, tối đa 3 lần.
  function tai() {
    return goiApi("chi-so", {}, { khiBan: function (g) { baoLoi("Máy chủ đang bận tính số liệu — tự thử lại sau " + g + " giây…"); } })
      .then(function (j) {
        var lanDau = !duLieu;
        duLieu = j;
        baoLoi("");
        if (lanDau) {
          tt.che = j.xu_huong && j.xu_huong.don_vi === "tuần" ? "tuan" : "ngay";
          var nguon = coBinhLuan(j) ? "bl" : "bai";
          tt.sacNguon = tt.tgNguon = tt.cdNguon = nguon;
        }
        veTatCa();
        $("cs-trang").classList.remove("dang-tai");
        var t = "Cập nhật lúc " + gioVN(new Date());
        if (j.luot_gan_nhat) t += " · lượt quét gần nhất bắt đầu " + j.luot_gan_nhat.bat_dau;
        $("cap-nhat-luc").textContent = t;
        nhapSong();
        // Luồng bình luận tải SAU số tổng (máy chủ chỉ cho 2 lượt tính cùng lúc).
        if (!bl.daTai && !bl.ctl) taiBl(false);
        else if (!lanDau && bl.trang <= 1 && !popMo) taiBl(false, true);
      })
      .catch(function (e) {
        baoLoi((e && e.message) || "Không tải được số liệu.");
        if (!duLieu) {
          $("cs-trang").classList.remove("dang-tai");
          xoa($("kpi"));
          $("cap-nhat-luc").textContent = "Chưa tải được số liệu";
        }
      });
  }

  function henTaiLai() {
    if (henGio) clearTimeout(henGio);
    henGio = setTimeout(function () { henGio = null; tai(); }, 1500);
  }

  // ─── thời gian thực ───
  if (window.EventSource) {
    var es = new EventSource("/su-kien");
    es.addEventListener("cap-nhat", function (e) {
      try { if (JSON.parse(e.data).du_an === cfg.du_an) henTaiLai(); } catch (_) { /* bỏ qua */ }
    });
    es.addEventListener("het-phien", function () {
      es.close();
      baoLoi("Phiên đăng nhập đã hết hạn — tải lại trang để đăng nhập lại.");
    });
    es.addEventListener("het-quyen", function () {
      es.close();
      baoLoi("Tài khoản không còn trong danh sách người xem — số liệu dừng cập nhật.");
    });
  }

  // Đổi sáng/tối: vẽ lại với màu mới (màu đọc từ biến CSS).
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  if (mq && mq.addEventListener) {
    mq.addEventListener("change", function () {
      Object.keys(bieuDo).forEach(function (k) { bieuDo[k].dispose(); delete bieuDo[k]; });
      veTatCa();
    });
  }
  // Đổi cỡ: biểu đồ co giãn; mây từ xếp lại khi bề rộng đổi (chờ 150 ms cho khỏi xếp liên tục).
  window.addEventListener("resize", treo(function () {
    Object.keys(bieuDo).forEach(function (k) { bieuDo[k].resize(); });
    var el = $("tk-may");
    if (el && !el.hidden && el.clientWidth && Math.abs(el.clientWidth - may.rong) > 4) xepMay();
    if (popMo) kepPop(popMo.pop);                       // bàn phím ảo mở cũng là "resize": giữ popover
  }, 150));

  // ─── khởi tạo luồng bình luận ───
  (function () {
    var o = $("bl-tim");
    if (!o) return;
    $("bl-tim-khung").insertBefore(bieuTuong("tim_kiem"), o);
    taoTruong();
    var timNgay = function () {
      var v = o.value.trim().slice(0, 100);
      if (v !== bl.loc.q) datLocBl({ q: v });
    };
    o.addEventListener("input", treo(timNgay, 300));
    o.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); timNgay(); } });
    $("bl-sap-xep").addEventListener("change", function (e) { datLocBl({ sap_xep: e.target.value }); });
  })();

  tai();
})();
