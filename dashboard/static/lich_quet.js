// Trang Lịch quét: đổi kiểu lịch thì hiện đúng nhóm ô; sửa ô nào thì hỏi máy chủ bản XEM TRƯỚC
// (10 lần chạy tới + chi phí so với trần) qua /api/lich-quet/xem-truoc. Mọi phép tính mốc/chi phí
// ở máy chủ (dashboard/lich_quet.py — đúng hàm Mark dùng), ở đây chỉ vẽ lại bằng textContent.
// Không có JS thì trang vẫn đủ: mọi nhóm ô hiện, máy chủ kiểm lại khi lưu.
"use strict";
(function () {
  var form = document.getElementById("lq-form");
  var xem = document.getElementById("lq-xem");
  if (!form || !xem) return;

  function o(k) { return xem.querySelector('[data-o="' + k + '"]'); }
  function kieu() {
    var r = form.querySelector('input[name="kieu"]:checked');
    return r ? r.value : "";
  }

  // ── kiểu lịch: hiện/ẩn nhóm ô (nhóm ẩn bị disabled nên không gửi, không kiểm) ──
  var moiNguon = form.elements.namedItem("quet_moi_nguon");
  var daCham = false;               // người dùng đã tự bấm "quét mọi nguồn" thì không đổi hộ
  if (moiNguon) moiNguon.addEventListener("change", function () { daCham = true; });
  var kieuTruoc = kieu();
  function apKieu() {
    var k = kieu();
    form.querySelectorAll("fieldset[data-cho]").forEach(function (fs) {
      var co = fs.getAttribute("data-cho").split(" ").indexOf(k) >= 0;
      fs.hidden = !co;
      fs.disabled = !co;
    });
    var gy = form.querySelector("[data-goi-y-thu]");
    if (gy) {
      var chuGy = k === "hang_tuan" ? "Chọn ít nhất một ngày chạy." : "Bỏ trống = mọi ngày.";
      gy.setAttribute("data-goi-y", chuGy);                  // ghi chú nằm trong nút ⓘ
      gy.setAttribute("aria-label", "Giải thích: " + chuGy);
    }
    // chiến dịch mặc định quét mọi nguồn; về lịch thường thì theo chu kỳ nguồn
    if (moiNguon && !daCham && k !== kieuTruoc) moiNguon.checked = k === "chien_dich";
    kieuTruoc = k;
  }

  // ── mẫu nhanh (giờ, ngày) ──
  form.querySelectorAll(".lq-nhanh").forEach(function (x) { x.hidden = false; });
  form.addEventListener("click", function (e) {
    var nut = e.target.closest ? e.target.closest("[data-dat-gio], [data-dat-thu]") : null;
    if (!nut) return;
    if (nut.hasAttribute("data-dat-gio")) {
      var o2 = form.elements.namedItem("gio");
      if (o2) o2.value = nut.getAttribute("data-dat-gio");
    } else {
      var chon = (nut.getAttribute("data-dat-thu") || "").split(",").filter(Boolean);
      for (var i = 1; i <= 7; i++) {
        var c = form.elements.namedItem("thu_" + i);
        if (c) c.checked = chon.indexOf(String(i)) >= 0;
      }
    }
    xemTruoc();
  });

  // ── xem trước ──
  var hen = null;
  var lan = 0;
  function xemTruoc() {
    window.clearTimeout(hen);
    hen = window.setTimeout(goi, 300);
  }
  function chu(el, s) { if (el && el.textContent !== s) el.textContent = s; }
  function veLoi(s) {
    chu(o("loi"), s);
    o("loi").hidden = false;
    o("than").hidden = true;
  }
  function the(ten, lop, s) {
    var e = document.createElement(ten);
    if (lop) e.className = lop;
    if (s != null) e.textContent = s;
    return e;
  }
  function ve(d) {
    o("loi").hidden = true;
    o("than").hidden = false;
    chu(o("mo_ta"), d.mo_ta || "");
    chu(o("tan_suat"), d.tan_suat || "");
    var ol = o("moc");
    ol.replaceChildren();
    (d.moc || []).forEach(function (m, i) {
      var li = the("li", m.nhuong ? "lq-moc--nhuong" : "");
      li.append(the("span", "", m.chu), the("span", "mo nho",
        m.nhuong ? "nhường chiến dịch" : (i === 0 ? m.con : "")));
      ol.append(li);
    });
    chu(o("ghi_moc"), d.ghi_moc || "");
    o("ghi_moc").hidden = !d.ghi_moc;
    var dl = o("chi_phi");
    dl.replaceChildren();
    (d.chi_phi || []).forEach(function (c) {
      var dong = the("div");
      var dd = the("dd");
      dd.append(the("b", "", c.gia_tri), the("span", "mo nho", c.phu));
      dong.append(the("dt", "", c.nhan), dd);
      dl.append(dong);
    });
    chu(o("ket_luan"), d.ket_luan || "");
    o("ket_luan").classList.toggle("lq-ket--canh", !!d.vuot);
    var ct = o("cong_thuc");                                 // công thức nằm trong nút ⓘ
    ct.setAttribute("data-goi-y", d.cong_thuc || "");
    ct.setAttribute("aria-label", "Giải thích: " + (d.cong_thuc || ""));
    ct.hidden = !d.cong_thuc;
    var ul = o("canh_bao");
    ul.replaceChildren();
    (d.canh_bao || []).forEach(function (c) { ul.append(the("li", "", c)); });
    ul.hidden = !(d.canh_bao || []).length;
  }
  function goi() {
    var q = new URLSearchParams();
    // từ khoá chiến dịch không đổi mốc chạy: không gửi (URL khỏi dài quá 4.000 ký tự)
    new FormData(form).forEach(function (v, k) { if (k !== "csrf" && k !== "tu_khoa_them") q.append(k, String(v)); });
    q.set("du_an", form.getAttribute("data-du-an") || "");
    var lid = form.getAttribute("data-lid");
    if (lid) q.set("lid", lid);
    var so = ++lan;
    chu(o("dang-tinh"), "đang tính…");
    fetch("/api/lich-quet/xem-truoc?" + q.toString(), {
      credentials: "same-origin", headers: { Accept: "application/json" }
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d || {} }; });
    }).then(function (x) {
      if (so !== lan) return;      // đã có yêu cầu mới hơn
      chu(o("dang-tinh"), "");
      if (!x.ok || x.d.loi) veLoi(x.d.loi || "Không xem trước được.");
      else ve(x.d);
    }).catch(function () {
      if (so !== lan) return;
      chu(o("dang-tinh"), "");
      veLoi("Không xem trước được (mất kết nối?) — vẫn lưu được, máy chủ kiểm lại khi lưu.");
    });
  }

  form.addEventListener("change", function (e) {
    if (e.target && e.target.name === "kieu") apKieu();
    xemTruoc();
  });
  form.addEventListener("input", xemTruoc);
  var nutLuu = form.querySelector('[data-o="nut-luu"]');
  var chuLuu = nutLuu ? nutLuu.textContent : "";
  form.addEventListener("submit", function () {
    if (!nutLuu) return;
    nutLuu.disabled = true;
    nutLuu.textContent = "Đang lưu…";
  });
  window.addEventListener("pageshow", function (e) {   // quay lại bằng nút Back: mở lại nút Lưu
    if (!e.persisted || !nutLuu) return;
    nutLuu.disabled = false;
    nutLuu.textContent = chuLuu;
  });

  apKieu();
})();
