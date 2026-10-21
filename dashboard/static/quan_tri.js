// Trang Quản trị — mục "Người dùng và quyền" (21/10/2026, chủ dự án: "phân quyền đơn giản hơn — chọn
// vai trò qua tên người dùng, nút Lưu để ấn định quyền mỗi lần"). Không áp gì khi đổi ô chọn: chỉ
// đánh dấu "Chưa lưu"; bấm Lưu mới gửi (POST /nguoi-xem/quyen, máy chủ kiểm lại mọi luật). CSP cấm
// script nội dòng nên mọi hành vi gắn ở đây; chữ chỉ đi qua textContent.
"use strict";
(function () {
  var goc = document.querySelector("[data-nx]");
  if (!goc) return;

  // ── bỏ dấu tiếng Việt (khớp chuan_chu.bo_dau của máy chủ: đ → d, bỏ dấu, chữ thường) ──
  function boDau(s) {
    return String(s || "").toLowerCase().replace(/đ/g, "d").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ").trim();
  }

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
          f.querySelector("[data-nx-chon-ghi]").textContent = "Chọn một người trong gợi ý, hoặc nhập email đầy đủ.";
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
  function loc() {
    var q = boDau(o_tim.value), tu = q ? q.split(" ") : [], n = 0;
    dong.forEach(function (d) {
      var khop = tu.every(function (t) { return d.getAttribute("data-tim").indexOf(t) >= 0; });
      // dòng đang sửa dở (chưa lưu) không bị ẩn — khỏi mất thay đổi khỏi tầm mắt
      d.hidden = !khop && !d.classList.contains("nx-dong--doi");
      if (!d.hidden) n += 1;
    });
    dem.textContent = q ? n + "/" + dong.length : String(dong.length);
    trong.hidden = !(q && n === 0);
    goc.querySelector("[data-nx-ds]").hidden = !!(q && n === 0);
    trong.querySelector("[data-nx-tu]").textContent = o_tim.value.trim();
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

  function anGoiY() { dsGoiY.hidden = true; dsGoiY.textContent = ""; oEmail.setAttribute("aria-expanded", "false"); chon = -1; }
  function daCo(email) { return dong.filter(function (d) { return d.getAttribute("data-email") === email; })[0]; }
  function chonNguoi(x) {
    var d = daCo(x.email);
    anGoiY();
    if (d) {
      // Người đã có tên: mở ngăn sửa của họ thay vì thêm lần nữa.
      fThem.reset(); datMoThem(false); o_tim.value = ""; loc();
      var nut = d.querySelector("[data-nx-sua]");
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
  oEmail.addEventListener("input", timDanhBa);
  oEmail.addEventListener("blur", function () { setTimeout(anGoiY, 120); });
  oEmail.addEventListener("keydown", function (e) {
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
      vua.querySelector(".nx-da-luu").hidden = false;
      vua.classList.add("nx-dong--vua-luu");
    }
  }
})();
