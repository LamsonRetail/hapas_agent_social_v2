// Trang Quản trị — mục "Người dùng và quyền" (21/10/2026, chủ dự án: "phân quyền đơn giản hơn — chọn
// vai trò qua tên người dùng, nút Lưu để ấn định quyền mỗi lần"). Không áp gì khi đổi ô chọn: chỉ
// đánh dấu "Chưa lưu"; bấm Lưu mới gửi (POST /nguoi-xem/quyen, máy chủ kiểm lại mọi luật). CSP cấm
// script nội dòng nên mọi hành vi gắn ở đây; chữ chỉ đi qua textContent.
"use strict";

// ── bỏ dấu tiếng Việt (khớp chuan_chu.bo_dau của máy chủ: đ → d, bỏ dấu, chữ thường) ──
function boDau(s) {
  return String(s || "").toLowerCase().replace(/đ/g, "d").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ").trim();
}

// 23/10/2026: các danh sách dài của trang dùng thanh trang chung (chung.js, data-phan-trang). Một dòng
// cần hiện (vừa lưu, chọn người đã có) có thể đang ở trang khác: bấm ‹ / › của thanh trang tới đúng
// trang chứa nó — không đụng mã dùng chung. Dòng bị bộ lọc ẩn ([data-loc-an]) thì thôi.
function denTrang(bang, dong) {
  if (!bang || !dong || dong.hasAttribute("data-loc-an") || !dong.hidden) return;
  var co = Math.max(1, parseInt(bang.getAttribute("data-phan-trang"), 10) || 20);
  var than = bang.tagName === "TABLE" ? (bang.tBodies[0] || bang) : bang;
  var ds = Array.prototype.filter.call(than.children, function (r) {
    return (r.tagName === "TR" || r.tagName === "LI") && !r.hasAttribute("data-loc-an");
  });
  var dich = Math.floor(ds.indexOf(dong) / co), dang = -1;
  ds.some(function (r, i) { if (!r.hidden) { dang = Math.floor(i / co); return true; } return false; });
  var neo = bang.closest(".cuon-ngang") || bang;
  for (var buoc = 0; dich >= 0 && dang >= 0 && dang !== dich && buoc < 500; buoc++) {
    var nav = neo.nextElementSibling;
    if (!nav || !nav.classList.contains("phan-trang")) return;
    var ben = nav.querySelectorAll(".phan-trang__ben");
    var nut = ben[dich > dang ? ben.length - 1 : 0];
    if (!nut || nut.disabled) return;
    nut.click();
    dang += dich > dang ? 1 : -1;
  }
}

(function () {
  var goc = document.querySelector("[data-nx]");
  if (!goc) return;

  // ── trạng thái biểu mẫu: đổi so với lúc tải trang? ──
  function oChon(f) { return Array.prototype.slice.call(f.querySelectorAll("[data-nx-ben]")); }
  function congTac(f) { return f.querySelector("[data-nx-qt]"); }
  function daDoi(f) {
    var qt = congTac(f);
    if (qt && !qt.disabled && qt.checked !== qt.defaultChecked) return true;
    return oChon(f).some(function (s) {
      return Array.prototype.some.call(s.options, function (o) { return o.selected !== o.defaultSelected; });
    });
  }
  function apCongTac(f) {
    // Quản trị viên (mọi bên) bật: ô theo bên khoá (không gửi — máy chủ giữ nguyên quyền theo bên).
    var qt = congTac(f), bat = !!(qt && qt.checked);
    oChon(f).forEach(function (s) { s.disabled = bat || s.hasAttribute("data-nx-khoa"); });
    var ghi = f.querySelector("[data-nx-ghi-qt]");
    if (ghi) ghi.hidden = !bat;
  }
  function seKhongConQuyen(f) {
    var qt = congTac(f);
    if (qt && qt.checked) return false;
    return oChon(f).every(function (s) { return s.value === ""; });
  }
  function capNhat(f) {
    apCongTac(f);
    var luu = f.querySelector("[data-nx-luu]"), huy = f.querySelector("[data-nx-huy]");
    var tt = f.querySelector("[data-nx-trang-thai]");
    if (f.hasAttribute("data-nx-moi")) {
      var email = f.querySelector("[data-nx-email]").value.trim();
      var co = email && !seKhongConQuyen(f);
      luu.disabled = !co;
      tt.textContent = !email ? "Chọn người trước." : (co ? "" : "Chọn ít nhất một quyền.");
      return;
    }
    var doi = daDoi(f), dong = f.closest(".nx-dong");
    luu.disabled = !doi;
    if (huy) huy.disabled = !doi;
    tt.textContent = doi ? "Chưa lưu — thay đổi chỉ có hiệu lực khi bấm Lưu." : "";
    if (dong) {
      dong.classList.toggle("nx-dong--doi", doi);
      dong.querySelector(".nx-chua-luu").hidden = !doi;
      if (doi) dong.querySelector(".nx-da-luu").hidden = true;
    }
  }
  var cacForm = Array.prototype.slice.call(goc.querySelectorAll("[data-nx-form]"));
  cacForm.forEach(function (f) {
    f.addEventListener("change", function () { capNhat(f); });
    f.addEventListener("input", function () { capNhat(f); });
    var huy = f.querySelector("[data-nx-huy]");
    if (huy) huy.addEventListener("click", function () { f.reset(); capNhat(f); });
    f.addEventListener("submit", function (e) {
      if (f.hasAttribute("data-nx-moi")) {
        var o = f.querySelector("[data-nx-email]");
        if (o.value.indexOf("@") < 0) {
          e.preventDefault();
          f.querySelector("[data-nx-chon-ghi]").textContent = o.hasAttribute("data-nx-goi-y") ?
            "Chọn một người trong gợi ý, hoặc nhập email đầy đủ." : "Nhập email Lark đầy đủ, vd ten@hapas.vn.";
          o.focus();
          return;
        }
      } else if (seKhongConQuyen(f) && !window.confirm((f.getAttribute("data-ten") || "Người này") +
          " sẽ không còn quyền nào và bị xoá khỏi danh sách. Lưu?")) {
        e.preventDefault();
        return;
      }
      f.setAttribute("data-dang-gui", "1");
      var luu = f.querySelector("[data-nx-luu]");
      luu.disabled = true;
      luu.textContent = "Đang lưu…";
    });
    capNhat(f);
  });

  // Rời trang khi còn thay đổi chưa lưu: hỏi lại (trình duyệt tự soạn câu).
  window.addEventListener("beforeunload", function (e) {
    var con = cacForm.some(function (f) {
      return !f.hasAttribute("data-nx-moi") && !f.hasAttribute("data-dang-gui") && daDoi(f);
    });
    if (con) { e.preventDefault(); e.returnValue = ""; }
  });

  // ── mở / đóng ngăn "Sửa quyền" ──
  function moNgan(nut, mo) {
    var ngan = document.getElementById(nut.getAttribute("aria-controls"));
    if (!ngan) return;
    ngan.hidden = !mo;
    nut.setAttribute("aria-expanded", mo ? "true" : "false");
    nut.textContent = mo ? "Đóng" : "Sửa quyền";
    // Ngăn nằm ngay sau nút trong DOM: Tab đi thẳng vào ô đầu, không cần dời tiêu điểm.
    nut.closest(".nx-dong").classList.toggle("nx-dong--mo", mo);
  }
  goc.addEventListener("click", function (e) {
    var nut = e.target.closest("[data-nx-sua]");
    if (nut) moNgan(nut, nut.getAttribute("aria-expanded") !== "true");
  });

  // ── tìm trong danh sách (tại chỗ, không dấu) ──
  var o_tim = goc.querySelector("[data-nx-tim]"), dem = goc.querySelector("[data-nx-dem]");
  var trong = goc.querySelector("[data-nx-trong]"), dong = Array.prototype.slice.call(goc.querySelectorAll(".nx-dong"));
  var ds = goc.querySelector("[data-nx-ds]"), khung = goc.querySelector("[data-nx-khung]");
  function loc() {
    var q = boDau(o_tim.value), tu = q ? q.split(" ") : [], n = 0;
    dong.forEach(function (d) {
      var khop = tu.every(function (t) { return d.getAttribute("data-tim").indexOf(t) >= 0; });
      // dòng đang sửa dở (chưa lưu) không bị ẩn — khỏi mất thay đổi khỏi tầm mắt.
      // 23/10/2026: ẩn bằng [data-loc-an] (không phải hidden) để thanh trang chung đếm đúng.
      var an = !khop && !d.classList.contains("nx-dong--doi");
      if (an) d.setAttribute("data-loc-an", ""); else { d.removeAttribute("data-loc-an"); n += 1; }
    });
    dem.textContent = q ? n + "/" + dong.length : String(dong.length);
    trong.hidden = !(q && n === 0);
    khung.hidden = !!(q && n === 0);
    trong.querySelector("[data-nx-tu]").textContent = o_tim.value.trim();
    ds.dispatchEvent(new Event("phan-trang:lam-moi"));
  }
  o_tim.addEventListener("input", loc);
  o_tim.addEventListener("keydown", function (e) { if (e.key === "Escape") { o_tim.value = ""; loc(); } });

  // ── Thêm người: gợi ý từ danh bạ Lark theo tên ──
  var them = document.getElementById("nx-them"), moThem = goc.querySelector("[data-nx-mo-them]");
  var fThem = them.querySelector("form"), oEmail = fThem.querySelector("[data-nx-email]");
  var dsGoiY = fThem.querySelector("#nx-goi-y"), ghiChon = fThem.querySelector("[data-nx-chon-ghi]");
  var ghiGoc = ghiChon.textContent, hen = 0, luot = 0, chon = -1;
  function datMoThem(mo, chu) {
    them.hidden = !mo;
    moThem.setAttribute("aria-expanded", mo ? "true" : "false");
    if (mo) {
      if (chu) oEmail.value = chu;
      capNhat(fThem);
      oEmail.focus();
      if (chu) timDanhBa();
    }
  }
  moThem.addEventListener("click", function () { datMoThem(them.hidden, ""); });
  fThem.querySelector("[data-nx-dong-them]").addEventListener("click", function () {
    fThem.reset(); anGoiY(); ghiChon.textContent = ghiGoc; datMoThem(false); moThem.focus();
  });
  trong.querySelector("[data-nx-them-tu]").addEventListener("click", function () { datMoThem(true, o_tim.value.trim()); });

  // Quản lý bên: không có ô gợi ý (danh bạ chỉ quản trị viên tìm được) — chỉ nhập email.
  function anGoiY() { if (!dsGoiY) return; dsGoiY.hidden = true; dsGoiY.textContent = ""; oEmail.setAttribute("aria-expanded", "false"); chon = -1; }
  function daCo(email) { return dong.filter(function (d) { return d.getAttribute("data-email") === email; })[0]; }
  function chonNguoi(x) {
    var d = daCo(x.email);
    anGoiY();
    if (d) {
      // Người đã có tên: mở ngăn sửa của họ thay vì thêm lần nữa.
      fThem.reset(); datMoThem(false); o_tim.value = ""; loc();
      var nut = d.querySelector("[data-nx-sua]");
      denTrang(ds, d);
      d.scrollIntoView({ block: "center" });
      if (nut) moNgan(nut, true);
      return;
    }
    oEmail.value = x.email;
    ghiChon.textContent = x.ten + (x.phong_ban ? " · " + x.phong_ban : "");
    capNhat(fThem);
    var s = fThem.querySelector("[data-nx-qt], select");
    if (s) s.focus();
  }
  function veGoiY(ds, loi) {
    dsGoiY.textContent = "";
    chon = -1;
    ds.forEach(function (x, i) {
      var li = document.createElement("li"), ten = document.createElement("span"), phu = document.createElement("span");
      li.id = "nx-gy-" + i;
      li.setAttribute("role", "option");
      li.className = "nx-goi-y__dong";
      ten.className = "nx-goi-y__ten";
      ten.textContent = x.ten;
      phu.className = "nx-goi-y__phu";
      phu.textContent = x.email + (x.phong_ban ? " · " + x.phong_ban : "") + (daCo(x.email) ? " · đã có — mở để sửa" : "");
      li.appendChild(ten); li.appendChild(phu);
      li.addEventListener("mousedown", function (e) { e.preventDefault(); chonNguoi(x); });
      dsGoiY.appendChild(li);
    });
    dsGoiY._ds = ds;
    dsGoiY.hidden = !ds.length;
    oEmail.setAttribute("aria-expanded", ds.length ? "true" : "false");
    if (!ds.length) {
      ghiChon.textContent = loi ? "Chưa tìm được trong danh bạ Lark — nhập thẳng email." :
        (oEmail.value.indexOf("@") >= 0 ? ghiGoc : "Không thấy ai tên này trong danh bạ Lark — thử tên khác hoặc nhập email.");
    } else {
      ghiChon.textContent = ghiGoc;
    }
  }
  function timDanhBa() {
    if (!dsGoiY) return;
    var q = oEmail.value.trim(), so = ++luot;
    clearTimeout(hen);
    if (q.length < 2) { anGoiY(); ghiChon.textContent = ghiGoc; return; }
    hen = setTimeout(function () {
      fetch("/api/danh-ba/tim?q=" + encodeURIComponent(q), { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { return r.ok ? r.json() : { ket_qua: [], loi: "loi" }; })
        .catch(function () { return { ket_qua: [], loi: "loi" }; })
        .then(function (d) { if (so === luot) veGoiY(d.ket_qua || [], d.loi); });
    }, 250);
  }
  if (dsGoiY) oEmail.addEventListener("input", timDanhBa);
  oEmail.addEventListener("blur", function () { setTimeout(anGoiY, 120); });
  oEmail.addEventListener("keydown", function (e) {
    if (!dsGoiY) return;
    var li = dsGoiY.querySelectorAll("li");
    if (dsGoiY.hidden || !li.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      chon = (chon + (e.key === "ArrowDown" ? 1 : -1) + li.length) % li.length;
      Array.prototype.forEach.call(li, function (x, i) { x.setAttribute("aria-selected", i === chon ? "true" : "false"); });
      oEmail.setAttribute("aria-activedescendant", li[chon].id);
    } else if (e.key === "Enter" && chon >= 0) {
      e.preventDefault();
      chonNguoi(dsGoiY._ds[chon]);
    } else if (e.key === "Escape") {
      anGoiY();
    }
  });

  // ── vừa lưu (máy chủ chuyển về #nx-…): đánh dấu dòng đó ──
  if (location.hash.indexOf("#nx-") === 0 && document.querySelector(".thong-bao--ok, .thong-bao--canh")) {
    var vua = document.getElementById(location.hash.slice(1));
    if (vua && vua.classList.contains("nx-dong")) {
      denTrang(ds, vua);
      vua.scrollIntoView({ block: "center" });
      vua.querySelector(".nx-da-luu").hidden = false;
      vua.classList.add("nx-dong--vua-luu");
    }
  }
})();

// ── Tài khoản quảng cáo → bên (23/10/2026, chủ dự án: "để cho gọn lại") ──
// Lọc tại chỗ theo nền tảng / bên / trạng thái + tìm tên hoặc mã; dòng không khớp mang [data-loc-an] để
// thanh trang chung (20 dòng) đếm lại. Lọc theo bên ĐÃ LƯU (data-ben của máy chủ), không theo ô chọn
// đang sửa. Dòng sửa dở (chưa bấm Lưu) được tô, nút Lưu của nó đậm lên, và không bị lọc ẩn. Mỗi dòng
// vẫn là form riêng gb-<id> → POST /qc/gan-ben; máy chủ đưa về #tk-qc nên nhớ dòng vừa lưu + bộ lọc
// trong sessionStorage (chỉ cho tiện — trình duyệt chặn thì thôi) để mở lại đúng trang và tô dòng đó.
(function () {
  var goc = document.querySelector("[data-tkqc]");
  var bang = goc && goc.querySelector(".tkqc-bang");
  if (!bang) return;
  var dong = Array.prototype.slice.call(bang.tBodies[0].rows);
  var tim = goc.querySelector("[data-tkqc-tim]"), dem = goc.querySelector("[data-tkqc-dem]");
  var loc = Array.prototype.slice.call(goc.querySelectorAll("[data-tkqc-loc]"));
  var trong = goc.querySelector("[data-tkqc-trong]"), khung = bang.closest(".cuon-ngang");
  var KHOA = "tkqc-loc", KHOA_VUA = "tkqc-vua";
  function doc(k) { try { return window.sessionStorage.getItem(k); } catch (e) { return null; } }
  function ghi(k, v) {
    try { if (v === null) window.sessionStorage.removeItem(k); else window.sessionStorage.setItem(k, v); } catch (e) { /* bỏ qua */ }
  }

  dong.forEach(function (d) { d._tim = boDau(d.getAttribute("data-tim")); });
  function chon(ten) { var s = goc.querySelector('[data-tkqc-loc="' + ten + '"]'); return s ? s.value : ""; }
  function apLoc() {
    var q = boDau(tim.value), tu = q ? q.split(" ") : [], nen = chon("nen"), ben = chon("ben"), tt = chon("trang");
    var n = 0;
    dong.forEach(function (d) {
      var co = " " + d.getAttribute("data-trang") + " ";
      var khop = (!nen || d.getAttribute("data-nen-tang") === nen) && (!ben || d.getAttribute("data-ben") === ben) &&
        (!tt || co.indexOf(" " + tt + " ") >= 0) && tu.every(function (t) { return d._tim.indexOf(t) >= 0; });
      if (khop || d.classList.contains("tkqc-doi")) { d.removeAttribute("data-loc-an"); n += 1; }
      else d.setAttribute("data-loc-an", "");
    });
    var dangLoc = !!(q || nen || ben || tt);
    dem.textContent = dangLoc ? n + "/" + dong.length : String(dong.length);
    trong.hidden = n > 0;
    khung.hidden = n === 0;
    bang.dispatchEvent(new Event("phan-trang:lam-moi"));
    ghi(KHOA, JSON.stringify({ q: tim.value, nen: nen, ben: ben, trang: tt }));
  }
  tim.addEventListener("input", apLoc);
  tim.addEventListener("keydown", function (e) { if (e.key === "Escape") { tim.value = ""; apLoc(); } });
  loc.forEach(function (s) { s.addEventListener("change", apLoc); });
  goc.querySelector("[data-tkqc-bo-loc]").addEventListener("click", function () {
    tim.value = ""; loc.forEach(function (s) { s.value = ""; }); apLoc(); tim.focus();
  });

  // dòng sửa dở: so với giá trị lúc tải trang
  function daDoi(d) {
    return Array.prototype.some.call(d.querySelectorAll("select, input[type=checkbox]"), function (o) {
      if (o.tagName === "SELECT") return Array.prototype.some.call(o.options, function (x) { return x.selected !== x.defaultSelected; });
      return o.checked !== o.defaultChecked;
    });
  }
  dong.forEach(function (d) {
    var f = d.querySelector("[data-tkqc-form]"), nut = f.querySelector("button");
    d.addEventListener("change", function () {
      var c = daDoi(d);
      d.classList.toggle("tkqc-doi", c);
      nut.classList.toggle("nut--nhe", !c);
    });
    f.addEventListener("submit", function () { ghi(KHOA_VUA, d.getAttribute("data-o")); });
  });

  // vừa lưu (máy chủ đưa về #tk-qc): khôi phục bộ lọc, mở đúng trang của dòng đó và tô nó
  var veLai = location.hash === "#tk-qc";
  if (veLai) {
    try {
      var cu = JSON.parse(doc(KHOA) || "null");
      if (cu) {
        tim.value = cu.q || "";
        loc.forEach(function (s) {
          var v = cu[s.getAttribute("data-tkqc-loc")] || "";
          if (Array.prototype.some.call(s.options, function (o) { return o.value === v; })) s.value = v;
        });
      }
    } catch (e) { /* bỏ qua */ }
  }
  apLoc();
  var vua = doc(KHOA_VUA);
  ghi(KHOA_VUA, null);
  if (vua && veLai) {
    var d = bang.querySelector('tr[data-o="' + vua.replace(/[^\w-]/g, "") + '"]');
    if (d) {
      denTrang(bang, d);
      d.classList.add("tkqc-vua-luu");
      d.scrollIntoView({ block: "center" });
    }
  }
})();

// 23/10/2026: ô lọc nhật ký theo hành động — đổi là gửi (nút Lọc ẩn khi có JS).
(function () {
  Array.prototype.forEach.call(document.querySelectorAll("select[data-tu-gui]"), function (o) {
    var f = o.form;
    if (!f) return;
    var nut = f.querySelector(".nk-loc__nut");
    if (nut) nut.hidden = true;
    o.addEventListener("change", function () { f.submit(); });
  });
})();
