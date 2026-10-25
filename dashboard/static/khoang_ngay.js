// Ô "Khoảng ngày" dùng chung (25/10/2026, chủ dự án — trang Quảng cáo trước, trang Chỉ số đợt sau).
// Khung: <details data-khoang-ngay data-tu data-den data-max data-toi-da> chứa [data-kn-lich] (lịch, JS
// vẽ), hai ô ngày [data-kn-tu] / [data-kn-den] (không JS vẫn gửi được), [data-kn-tom] (chữ trên nút),
// [data-kn-bao] (dòng báo), [data-kn-ap-dung] (nút gửi), [data-kn-tuy-chon] + a[data-kn-nhanh] (khoảng
// nhanh — liên kết thường, bấm là đi), select[data-kn-ss] (so sánh, tuỳ chọn).
// Lịch hai tháng (điện thoại một tháng): bấm ngày đầu, bấm ngày cuối (rê chuột / di phím xem trước),
// ‹ › đổi tháng; ngày sau `data-max` (ngày cuối có số) bị khoá; khoảng dài hơn `data-toi-da` thì không
// cho Áp dụng. Bàn phím theo mẫu lưới ARIA: ← → ±1 ngày, ↑ ↓ ±1 tuần, Home / End đầu / cuối tuần,
// PageUp / PageDown ±1 tháng (Shift: ±1 năm), Enter / Space chọn. Chỉ tạo phần tử + textContent (CSP
// script-src 'self', không chèn HTML).
"use strict";
(function () {
  var THU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
  var THU_DU = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"];

  function doc(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
    if (!m) return null;
    var d = new Date(+m[1], +m[2] - 1, +m[3]);
    return d.getMonth() === +m[2] - 1 ? d : null;
  }
  function hai(n) { return (n < 10 ? "0" : "") + n; }
  function iso(d) { return d.getFullYear() + "-" + hai(d.getMonth() + 1) + "-" + hai(d.getDate()); }
  function ngan(d) { return hai(d.getDate()) + "/" + hai(d.getMonth() + 1); }
  function cong(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); }
  function congThang(d, n) {
    var cuoi = new Date(d.getFullYear(), d.getMonth() + n + 1, 0).getDate();
    return new Date(d.getFullYear(), d.getMonth() + n, Math.min(d.getDate(), cuoi));
  }
  function so(d) { return Math.round(d.getTime() / 864e5 - d.getTimezoneOffset() / 1440); }
  function soNgay(a, b) { return so(b) - so(a) + 1; }
  function thuIso(d) { return (d.getDay() + 6) % 7; }        // 0 = thứ Hai
  function tomTat(a, b) {
    var nam = a.getFullYear() !== b.getFullYear();
    return ngan(a) + (nam ? "/" + a.getFullYear() : "") + " – " + ngan(b) + "/" + b.getFullYear()
      + " · " + soNgay(a, b) + " ngày";
  }

  function dung(khung) {
    var lich = khung.querySelector("[data-kn-lich]");
    var oTu = khung.querySelector("[data-kn-tu]");
    var oDen = khung.querySelector("[data-kn-den]");
    if (!lich || !oTu || !oDen) return;
    var tom = khung.querySelector("[data-kn-tom]");
    var bao = khung.querySelector("[data-kn-bao]");
    var apDung = khung.querySelector("[data-kn-ap-dung]");
    var tuyChon = khung.querySelector("[data-kn-tuy-chon]");
    var ss = khung.querySelector("[data-kn-ss]");
    var nhanh = Array.prototype.slice.call(khung.querySelectorAll("a[data-kn-nhanh]"));
    var max = doc(khung.getAttribute("data-max")) || cong(new Date(), -1);
    var toiDa = parseInt(khung.getAttribute("data-toi-da"), 10) || 400;
    var tu = doc(oTu.value) || doc(khung.getAttribute("data-tu")) || max;
    var den = doc(oDen.value) || doc(khung.getAttribute("data-den")) || max;
    var dangChon = false, xem = null;
    var hep = window.matchMedia ? window.matchMedia("(max-width: 640px)") : null;
    function soThang() { return hep && hep.matches ? 1 : 2; }
    var dau = new Date(den.getFullYear(), den.getMonth() - (soThang() - 1), 1);   // tháng bên trái
    var tieuDiem = den > max ? max : den;
    var soLich = (dung.dem = (dung.dem || 0) + 1);

    function khoa(d) { return d > max; }

    function veO(td, d, thangNay) {
      var k = iso(d);
      td.className = "kn-o";
      if (!thangNay) { td.classList.add("kn-o--ngoai"); return; }
      var a = tu, b = dangChon ? (xem || tu) : den;
      if (b < a) { var t = a; a = b; b = t; }
      var trong = d >= a && d <= b;
      td.setAttribute("aria-selected", trong ? "true" : "false");
      if (trong) td.classList.add("kn-o--trong");
      if (k === iso(a)) td.classList.add("kn-o--dau");
      if (k === iso(b)) td.classList.add("kn-o--cuoi");
      if (dangChon) td.classList.add("kn-o--xem");
      if (khoa(d)) { td.classList.add("kn-o--khoa"); td.setAttribute("aria-disabled", "true"); }
      else td.removeAttribute("aria-disabled");
      if (k === iso(max)) td.classList.add("kn-o--moc");
      td.tabIndex = k === iso(tieuDiem) ? 0 : -1;
    }

    function ve() {
      while (lich.firstChild) lich.removeChild(lich.firstChild);
      var dauLich = document.createElement("div");
      dauLich.className = "kn-dau";
      var lui = nut("‹", "Tháng trước", function () { dau = new Date(dau.getFullYear(), dau.getMonth() - 1, 1); ve(); });
      var toi = nut("›", "Tháng sau", function () { dau = new Date(dau.getFullYear(), dau.getMonth() + 1, 1); ve(); });
      var cuoiHien = new Date(dau.getFullYear(), dau.getMonth() + soThang(), 0);
      toi.disabled = cuoiHien >= max;
      dauLich.appendChild(lui);
      var thangDs = document.createElement("div");
      thangDs.className = "kn-thang-ds";
      for (var i = 0; i < soThang(); i++) thangDs.appendChild(veThang(new Date(dau.getFullYear(), dau.getMonth() + i, 1), i));
      dauLich.appendChild(thangDs);
      dauLich.appendChild(toi);
      lich.appendChild(dauLich);
      veTom();
    }

    function nut(chu, nhan, f) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "kn-chuyen";
      b.textContent = chu;
      b.setAttribute("aria-label", nhan);
      b.addEventListener("click", f);
      return b;
    }

    function veThang(t, i) {
      var khoi = document.createElement("div");
      khoi.className = "kn-thang";
      var id = "kn-" + soLich + "-t" + i;
      var ten = document.createElement("p");
      ten.className = "kn-thang__ten";
      ten.id = id;
      ten.textContent = "Tháng " + (t.getMonth() + 1) + " " + t.getFullYear();
      khoi.appendChild(ten);
      var bang = document.createElement("table");
      bang.className = "kn-luoi";
      bang.setAttribute("role", "grid");
      bang.setAttribute("aria-labelledby", id);
      var thead = document.createElement("thead"), tr = document.createElement("tr");
      THU.forEach(function (x, j) {
        var th = document.createElement("th");
        th.scope = "col";
        th.abbr = THU_DU[j];
        th.textContent = x;
        tr.appendChild(th);
      });
      thead.appendChild(tr);
      bang.appendChild(thead);
      var tbody = document.createElement("tbody");
      var d = cong(t, -thuIso(t));
      for (var h = 0; h < 6; h++) {
        var dong = document.createElement("tr");
        for (var c = 0; c < 7; c++) {
          var td = document.createElement("td");
          var thangNay = d.getMonth() === t.getMonth();
          if (thangNay) {
            td.setAttribute("role", "gridcell");
            td.setAttribute("data-ngay", iso(d));
            td.textContent = d.getDate();
            td.setAttribute("aria-label", d.getDate() + " tháng " + (d.getMonth() + 1) + " " + d.getFullYear() + ", " + THU_DU[c]);
          } else {
            td.setAttribute("role", "gridcell");
            td.setAttribute("aria-hidden", "true");
          }
          veO(td, d, thangNay);
          dong.appendChild(td);
          d = cong(d, 1);
        }
        tbody.appendChild(dong);
        if (d.getMonth() !== t.getMonth() && h >= 3) break;
      }
      bang.appendChild(tbody);
      khoi.appendChild(bang);
      return khoi;
    }

    function veLai() {
      Array.prototype.forEach.call(lich.querySelectorAll("td[data-ngay]"), function (td) {
        veO(td, doc(td.getAttribute("data-ngay")), true);
      });
    }

    function veTom() {
      var dai = soNgay(tu, den);
      var quaDai = !dangChon && dai > toiDa;
      if (apDung) apDung.disabled = dangChon || quaDai;
      if (bao) {
        bao.textContent = dangChon ? "Chọn ngày kết thúc (" + ngan(tu) + " → …)."
          : quaDai ? "Tối đa " + toiDa + " ngày — đang chọn " + dai + " ngày."
          : tomTat(tu, den);
        bao.classList.toggle("kn-bao--loi", quaDai);
      }
      var trung = null;
      nhanh.forEach(function (a) {
        var u = new URL(a.href, location.href);
        var la = !dangChon && u.searchParams.get("tu") === iso(tu) && u.searchParams.get("den") === iso(den);
        if (la) trung = a;
        if (la) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
      });
      if (tuyChon) { if (trung) tuyChon.removeAttribute("aria-current"); else tuyChon.setAttribute("aria-current", "true"); }
    }

    function dongBo() {
      oTu.value = iso(tu);
      oDen.value = iso(den);
    }

    function chon(d) {
      if (khoa(d)) return;
      tieuDiem = d;
      if (!dangChon) { tu = d; den = d; dangChon = true; xem = d; }
      else {
        if (d < tu) { den = tu; tu = d; } else den = d;
        dangChon = false; xem = null;
        dongBo();
      }
      veLai();
      veTom();
    }

    function denNgay(d, giuTieuDiem) {
      if (d > max) d = max;
      tieuDiem = d;
      var trai = new Date(dau.getFullYear(), dau.getMonth(), 1);
      var phai = new Date(dau.getFullYear(), dau.getMonth() + soThang(), 0);
      if (d < trai) dau = new Date(d.getFullYear(), d.getMonth(), 1);
      else if (d > phai) dau = new Date(d.getFullYear(), d.getMonth() - (soThang() - 1), 1);
      if (dangChon) xem = d;
      if (d < trai || d > phai) ve(); else veLai();
      if (!giuTieuDiem) {
        var o = lich.querySelector('td[data-ngay="' + iso(d) + '"]');
        if (o) o.focus();
      }
    }

    lich.addEventListener("click", function (e) {
      var td = e.target.closest ? e.target.closest("td[data-ngay]") : null;
      if (td) chon(doc(td.getAttribute("data-ngay")));
    });
    lich.addEventListener("mouseover", function (e) {
      if (!dangChon) return;
      var td = e.target.closest ? e.target.closest("td[data-ngay]") : null;
      if (!td) return;
      var d = doc(td.getAttribute("data-ngay"));
      if (khoa(d) || (xem && iso(xem) === iso(d))) return;
      xem = d;
      veLai();
    });
    lich.addEventListener("keydown", function (e) {
      var td = e.target.closest ? e.target.closest("td[data-ngay]") : null;
      if (!td) return;
      var d = doc(td.getAttribute("data-ngay")), moi = null;
      switch (e.key) {
        case "ArrowLeft": moi = cong(d, -1); break;
        case "ArrowRight": moi = cong(d, 1); break;
        case "ArrowUp": moi = cong(d, -7); break;
        case "ArrowDown": moi = cong(d, 7); break;
        case "Home": moi = cong(d, -thuIso(d)); break;
        case "End": moi = cong(d, 6 - thuIso(d)); break;
        case "PageUp": moi = congThang(d, e.shiftKey ? -12 : -1); break;
        case "PageDown": moi = congThang(d, e.shiftKey ? 12 : 1); break;
        case "Enter": case " ": e.preventDefault(); chon(d); return;
        default: return;
      }
      e.preventDefault();
      denNgay(moi);
    });

    // Gõ tay vào hai ô ngày (vẫn hiện dưới lịch) → lịch theo.
    function tuO() {
      var a = doc(oTu.value), b = doc(oDen.value);
      if (!a || !b) return;
      if (b < a) { var t = a; a = b; b = t; }
      tu = a; den = b; dangChon = false; xem = null;
      denNgay(den > max ? max : den, true);
      veTom();
    }
    oTu.addEventListener("change", tuO);
    oDen.addEventListener("change", tuO);

    // Khoảng nhanh: giữ lựa chọn "So sánh với" đang đổi dở (chưa Áp dụng) khi bấm.
    if (ss) nhanh.forEach(function (a) {
      a.addEventListener("click", function () {
        var u = new URL(a.href, location.href);
        if (ss.value && ss.value !== "truoc") u.searchParams.set("ss", ss.value); else u.searchParams.delete("ss");
        a.href = u.pathname + u.search + u.hash;
      });
    });
    if (tuyChon) {
      tuyChon.hidden = false;
      tuyChon.addEventListener("click", function () { denNgay(tieuDiem); });
    }
    var f = khung.closest("form");
    if (f) f.addEventListener("submit", function () {
      if (dangChon) { den = tu; dangChon = false; dongBo(); }
    });

    // Đóng khi bấm ra ngoài / Esc (như các ô nổi khác của thanh lọc).
    document.addEventListener("click", function (e) { if (khung.open && !khung.contains(e.target)) khung.open = false; });
    khung.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && khung.open) { e.preventDefault(); khung.open = false; khung.querySelector("summary").focus(); }
    });
    if (hep && hep.addEventListener) hep.addEventListener("change", function () {
      dau = new Date(den.getFullYear(), den.getMonth() - (soThang() - 1), 1);
      ve();
    });
    // Bảng nổi không tràn khung nhìn: mở ra thì kéo về trong mép (ô nằm sát phải / trái thanh lọc).
    var bangNoi = khung.querySelector("[data-kn-bang]");
    function vuaKhung() {
      if (!khung.open || !bangNoi) return;
      bangNoi.style.left = "";
      if (getComputedStyle(bangNoi).position !== "absolute") return;
      var vw = document.documentElement.clientWidth, r = bangNoi.getBoundingClientRect();
      var goc = khung.getBoundingClientRect();
      if (r.right > vw - 8) bangNoi.style.left = Math.round(Math.max(8, vw - 8 - r.width) - goc.left) + "px";
    }
    khung.addEventListener("toggle", vuaKhung);
    window.addEventListener("resize", vuaKhung);
    lich.hidden = false;
    ve();
    vuaKhung();
    if (tom) tom.textContent = tomTat(tu, den);
  }

  Array.prototype.forEach.call(document.querySelectorAll("details[data-khoang-ngay]"), dung);
})();
