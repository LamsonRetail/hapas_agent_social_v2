// Trang Ngân sách: tính lại NGAY ước tính USD khi sửa cấu hình thu thập từng nền tảng (tìm theo
// từ khoá + cào bình luận) và trần tháng. Công thức chép đúng dashboard/chi_phi.py — `cau_hinh`,
// `uoc_tk_nen_tang`, `uoc_binh_luan_luot`, `bang_cau_hinh`; hằng số (giá, hệ số, giới hạn) do máy
// chủ phát trong #ns-du-lieu, ở đây không tự đặt giá nào. Không có JS thì trang vẫn đủ số (máy chủ
// dựng sẵn) và biểu mẫu vẫn gửi được.
"use strict";
(function () {
  var nguon = document.getElementById("ns-du-lieu");
  var form = document.getElementById("ns-form");
  if (!nguon || !form) return;
  var D;
  try { D = JSON.parse(nguon.textContent || "{}"); } catch (e) { return; }
  var hs = D.hang_so || {};
  var NT = hs.nen_tang || [];
  var GH = hs.gioi_han || {};
  var IG_MD = hs.tk_ig_so_tu;
  var MD = D.mac_dinh || {};

  // = chi_phi._norm: bỏ dấu (kể cả đ) + thường hoá
  function norm(s) {
    return String(s || "").replace(/đ/g, "d").replace(/Đ/g, "D").normalize("NFD")
      .replace(/\p{Mn}/gu, "").toLowerCase();
  }
  // = chi_phi.tu_tim: gộp khoảng trắng, bỏ trùng (không phân biệt dấu/hoa thường), giữ thứ tự,
  // dự án chưa có từ khoá thì tìm theo tên dự án; tối đa gioi_han.tk_so_tu[1] từ
  function tuTim(ds, ten) {
    var ra = [];
    var da = [];
    (ds && ds.length ? ds : [ten || ""]).forEach(function (x) {
      var t = String(x).split(/\s+/).filter(function (y) { return y !== ""; }).join(" ");
      var n = norm(t);
      if (t && da.indexOf(n) < 0) {
        ra.push(t);
        da.push(n);
      }
    });
    return ra.slice(0, GH.tk_so_tu[1]);
  }
  var TU = tuTim(D.tu_khoa, D.ten);
  var TU_IG = TU.filter(function (t) { return t.indexOf(" ") < 0; });

  // Mẫu nhanh: [bật, số bài, (Instagram) số từ] cho tìm từ khoá; [bật, số bài, bình luận/bài] cho
  // bình luận (0 = cào hết). Chỉ ĐIỀN ô — người dùng xem số ước tính rồi mới bấm Lưu.
  var MAU = {
    tiet_kiem: {
      tk: { tiktok: [1, 10], facebook: [1, 10], instagram: [1, 5, 1], youtube: [1, 20], threads: [0, 10] },
      bl: { tiktok: [1, 3, 20], facebook: [1, 3, 20], instagram: [0, 3, 20], youtube: [1, 10, 100], threads: [0, 3, 20] }
    },
    can_bang: {
      tk: { tiktok: [1, 30], facebook: [1, 20], instagram: [1, 10, 2], youtube: [1, 30], threads: [0, 10] },
      bl: { tiktok: [1, 5, 50], facebook: [1, 5, 50], instagram: [1, 3, 30], youtube: [1, 20, 200], threads: [0, 5, 50] }
    },
    day_du: {
      tk: { tiktok: [1, 100], facebook: [1, 20], instagram: [1, 30, 4], youtube: [1, 100], threads: [0, 20] },
      bl: { tiktok: [1, 20, 0], facebook: [1, 20, 0], instagram: [1, 10, 0], youtube: [1, 50, 0], threads: [0, 10, 0] }
    }
  };

  // ── số kiểu Việt: 1.234,567 ──
  function soVn(x, le) {
    var s = Math.abs(x).toFixed(le);
    var i = s.indexOf(".");
    var nguyen = (i < 0 ? s : s.slice(0, i)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    var am = x < 0 && Number(s) !== 0 ? "-" : "";
    return am + nguyen + (i < 0 ? "" : "," + s.slice(i + 1));
  }
  // round(x, 4) của Python: làm tròn theo giá trị nhị phân thật (toFixed cũng vậy)
  function r4(x) { return Number(x.toFixed(4)); }
  // chi_phi._kep: số nguyên kẹp [lo, hi]; không phải số nguyên -> md
  function kep(v, lo, hi, md) {
    var s = String(v == null ? "" : v).trim();
    if (!/^[+-]?\d+$/.test(s)) return md;
    return Math.max(lo, Math.min(hi, parseInt(s, 10)));
  }

  // ── công thức (bản sao chi_phi.py) ──
  function cauHinh(doc, nhom, p) {   // = chi_phi.cau_hinh; doc.gt("") = ô trống -> mặc định dự án
    if (nhom === "tk") {
      var o = doc.gt("tk_" + p + "_so_bai");
      var so = kep(o !== "" ? o : (MD.tk_so_bai || 0), GH.tk_so_bai[0], GH.tk_so_bai[1], 0);
      var t = p === "instagram" ? doc.gt("tk_instagram_so_tu") : "";
      return {
        y: doc.bat("tk_" + p + "_bat"), bat: doc.bat("tk_" + p + "_bat") && so > 0, so_bai: so,
        so_tu: kep(t !== "" ? t : IG_MD, GH.tk_so_tu[0], GH.tk_so_tu[1], IG_MD)
      };
    }
    var ob = doc.gt("bl_" + p + "_so_bai");
    var om = doc.gt("bl_" + p + "_moi_bai");
    var sb = kep(ob !== "" ? ob : (MD.bl_so_bai || 0), GH.bl_so_bai[0], GH.bl_so_bai[1], 0);
    var mb = kep(om !== "" ? om : (MD.bl_moi_bai || 0), GH.bl_moi_bai[0], GH.bl_moi_bai[1], 0);
    return {
      y: doc.bat("bl_" + p + "_bat"), bat: doc.bat("bl_" + p + "_bat") && sb > 0, so_bai: sb,
      moi_bai: mb > 0 && mb < 5 ? 5 : mb
    };
  }
  // = chi_phi.uoc_tk_nen_tang như bang_cau_hinh gọi: KHÔNG kẹp Facebook ở tk_fb_toi_da — dashboard
  // không biết gói Apify, nên báo mức trần thận trọng theo đúng số bài đã đặt.
  function uocTk(p, so, soTu) {
    // Threads (= chi_phi.tu_gui): chỉ `so // 10` từ đầu (≥ 1, ≤ 20) — actor lấy ≥ 10 bài mỗi từ.
    var thMin = hs.th_toi_thieu_bai || 10;
    var q = p === "instagram" ? TU_IG.slice(0, soTu)
      : p === "threads" ? TU.slice(0, Math.max(1, Math.min(hs.th_toi_da_moi_luot || 20, Math.floor(so / thMin))))
      : TU;
    var gia = (hs.tk_gia || {})[p] || 0;
    if (!q.length || !gia || so <= 0) return 0;
    if (p === "instagram") return r4(q.length * (hs.tk_khoi.instagram + so * gia) * hs.he_so);
    var n = p === "threads" ? Math.max(so, thMin) : so;
    return r4((n * gia + ((hs.tk_khoi || {})[p] || 0)) * hs.he_so);
  }
  function uocBl(p, so, moi) {       // = chi_phi.uoc_binh_luan_luot
    moi = moi || hs.bl_uoc_moi_bai;
    var gia = (hs.bl_gia || {})[p] || 0;
    if (!so || !gia) return 0;
    return r4((so * moi * gia + ((hs.bl_khoi || {})[p] || 0)) * hs.he_so);
  }
  function tinh(doc) {               // = chi_phi.bang_cau_hinh
    var kq = { tk: {}, bl: {} };
    var stk = 0;
    var sbl = 0;
    NT.forEach(function (p) {
      var a = cauHinh(doc, "tk", p);
      var b = cauHinh(doc, "bl", p);
      a.uoc = a.bat ? uocTk(p, a.so_bai, a.so_tu) : 0;
      b.uoc = b.bat ? uocBl(p, b.so_bai, b.moi_bai) : 0;
      kq.tk[p] = a;
      kq.bl[p] = b;
      stk += a.uoc;
      sbl += b.uoc;
    });
    kq.uoc_tk = r4(stk);
    kq.uoc_bl = r4(sbl);
    kq.tong = r4(kq.uoc_tk + kq.uoc_bl);
    return kq;
  }

  // ── đọc giá trị: từ biểu mẫu, hoặc từ một mẫu nhanh ──
  function truong(ten) { return form.elements.namedItem(ten); }
  var docForm = {
    gt: function (ten) { var e = truong(ten); return e ? String(e.value).trim() : ""; },
    bat: function (ten) { var e = truong(ten); return !!(e && e.checked); }
  };
  function oMau(m) {                 // mẫu -> {tên ô: giá trị}
    var f = {};
    NT.forEach(function (p) {
      var a = m.tk[p];
      var b = m.bl[p];
      f["tk_" + p + "_bat"] = !!a[0];
      f["tk_" + p + "_so_bai"] = String(a[1]);
      if (p === "instagram") f.tk_instagram_so_tu = String(a[2]);
      f["bl_" + p + "_bat"] = !!b[0];
      f["bl_" + p + "_so_bai"] = String(b[1]);
      f["bl_" + p + "_moi_bai"] = String(b[2]);
    });
    return f;
  }
  function docTu(f) {
    return {
      gt: function (ten) { return f[ten] == null ? "" : String(f[ten]); },
      bat: function (ten) { return !!f[ten]; }
    };
  }

  // ── ghi ra trang ──
  function o(khoa) { return form.querySelector('[data-o="' + khoa + '"]'); }
  function ghi(khoa, chu, so) {
    var e = o(khoa);
    if (!e) return;
    if (e.textContent !== chu) e.textContent = chu;
    if (so != null) e.setAttribute("data-usd", String(so));
  }
  // Ghi chú nằm trong nút ⓘ (17/10/2026): đổi chữ của bóng nổi, không đổi chữ "i" trên nút.
  function ghiGoiY(khoa, chu) {
    var e = o(khoa);
    if (!e || e.getAttribute("data-goi-y") === chu) return;
    e.setAttribute("data-goi-y", chu);
    e.setAttribute("aria-label", "Giải thích: " + chu);
  }
  function oUsd(khoa, c, gia) {
    var e = o(khoa);
    if (!e) return;
    var chu = !c.y ? "tắt" : !c.so_bai ? "tắt (0 bài)" : !gia ? "miễn phí" : soVn(c.uoc, 3);
    ghi(khoa, chu, c.uoc);
    e.classList.toggle("ns-tat-chu", !c.y || !c.so_bai);
    e.classList.toggle("ns-mien-phi", !!(c.y && c.so_bai && !gia));
  }
  function moNhom(p, nhom, bat) {
    var dong = form.querySelector('tr[data-nt="' + p + '"]');
    if (!dong) return;
    dong.querySelectorAll('[data-nhom="' + nhom + '"]').forEach(function (td) {
      td.classList.toggle("ns-mo", !bat);
    });
  }
  function soTien(s, md) {           // ô trần tháng: nhận cả "5,5"
    var x = parseFloat(String(s || "").replace(/\s/g, "").replace(",", "."));
    return isFinite(x) ? x : md;
  }

  // ── trạng thái chưa lưu ──
  var CAC_O = Array.prototype.filter.call(form.elements, function (e) {
    return e.name && e.name !== "csrf" && (e.type === "checkbox" || e.type === "number");
  });
  function chup() {
    return CAC_O.map(function (e) { return e.type === "checkbox" ? (e.checked ? "1" : "0") : e.value; })
      .join("|");
  }
  var goc = chup();
  var ban = false;
  var dangLuu = false;

  function kiemO(e) {                // bình luận mỗi bài: 0 (cào hết) hoặc ≥ 5
    if (!/_moi_bai$/.test(e.name)) return;
    var v = String(e.value).trim();
    var n = /^\d+$/.test(v) ? parseInt(v, 10) : null;
    e.setCustomValidity(n != null && n > 0 && n < 5 ? "Bình luận mỗi bài: 0 (cào hết) hoặc từ 5 trở lên." : "");
  }

  function capNhat() {
    var kq = tinh(docForm);
    NT.forEach(function (p) {
      var a = kq.tk[p];
      var b = kq.bl[p];
      oUsd("tk-" + p, a, (hs.tk_gia || {})[p]);
      oUsd("bl-" + p, b, (hs.bl_gia || {})[p]);
      ghi("dong-" + p, soVn(r4(a.uoc + b.uoc), 3), r4(a.uoc + b.uoc));
      moNhom(p, "tk", a.y);
      moNhom(p, "bl", b.y);
    });
    var fb = o("ghi-fb");             // gói FREE: đặt quá tk_fb_toi_da thì làm nổi ghi chú
    if (fb) {
      var vuotFb = kq.tk.facebook && kq.tk.facebook.bat && kq.tk.facebook.so_bai > hs.tk_fb_toi_da;
      fb.classList.toggle("goi-y--canh", !!vuotFb);
    }
    ghi("tong-tk", soVn(kq.uoc_tk, 3), kq.uoc_tk);
    ghi("tong-bl", soVn(kq.uoc_bl, 3), kq.uoc_bl);
    ghi("tong-dong", soVn(kq.tong, 3), kq.tong);
    ghi("tong-luot", soVn(kq.tong, 3), kq.tong);
    // Lịch quét tự động: có lịch đang bật thì nhân theo số lượt của lịch (máy chủ đếm), không thì
    // giả định 1 lượt/ngày như trước.
    var luot30 = D.co_lich ? (D.luot_30 || 0) : hs.ngay;
    ghi("tong-30", soVn(kq.tong * luot30, 2), r4(kq.tong * luot30));

    // cả tháng nếu mỗi lượt dùng hết = đã tiêu + nguồn còn lại + số lượt còn lại × tổng mỗi lượt
    var tranDa = soTien(docForm.gt("tran_usd_thang"), D.tran_da);
    var tran = D.tran_platform == null ? tranDa : Math.min(tranDa, D.tran_platform);
    var ngay = D.co_lich ? (D.luot_con_lai || 0) : (D.ngay_con_lai || 0);
    var toiDa = D.da_tieu + D.nguon_con_lai + ngay * kq.tong;
    var vuot = toiDa > tran + 1e-9;
    var duLuot = ngay > 0 ? (tran - D.da_tieu - D.nguon_con_lai) / ngay : 0;
    ghi("thang-so", soVn(toiDa, 2), r4(toiDa));
    ghi("thang-tran", soVn(tran, 2), tran);
    ghi("thang-ket-luan", vuot
      ? "vượt trần " + soVn(toiDa - tran, 2) + " USD, Mark dừng quét khi chạm trần; " +
        (duLuot > 0 ? "vừa trần khi ≤ " + soVn(duLuot, 3) + " USD/lượt." : "riêng nguồn theo dõi đã chạm trần.")
      : "trong trần, còn dư " + soVn(tran - toiDa, 2) + " USD.");
    ghiGoiY("thang-cong-thuc", "= đã tiêu " + soVn(D.da_tieu, 2) + " + nguồn " + soVn(D.nguon_con_lai, 2) +
      " + " + (D.co_lich ? soVn(ngay, 0) + " lượt theo lịch" : soVn(ngay, 1) + " ngày") + " × " +
      soVn(kq.tong, 3));
    var hop = o("thang-hop");
    if (hop) hop.classList.toggle("ns-du-kien__thang--canh", vuot);

    // mẫu nhanh đang khớp ô nào
    form.querySelectorAll("[data-mau]").forEach(function (nut) {
      var f = oMau(MAU[nut.getAttribute("data-mau")]);
      var khop = Object.keys(f).every(function (ten) {
        var e = truong(ten);
        if (!e) return true;
        return e.type === "checkbox" ? e.checked === f[ten] : String(e.value).trim() === f[ten];
      });
      nut.setAttribute("aria-pressed", khop ? "true" : "false");
    });

    ban = chup() !== goc;
    form.setAttribute("data-ban", ban ? "1" : "0");
    var cl = o("chua-luu");
    if (cl) cl.hidden = !ban;
    var ht = o("nut-hoan-tac");
    if (ht) ht.disabled = !ban;
  }

  ghiGoiY("ghi-ig", "Chỉ từ không dấu cách (" + TU_IG.length + " từ)");

  // giá mỗi mẫu nhanh (chỉ phụ thuộc từ khoá dự án) — ghi ngay trên nút
  Object.keys(MAU).forEach(function (k) {
    var kq = tinh(docTu(oMau(MAU[k])));
    ghi("mau-" + k, "≈ " + soVn(kq.tong, 3) + " USD/lượt", kq.tong);
  });

  form.addEventListener("click", function (e) {
    var nut = e.target.closest ? e.target.closest("[data-mau]") : null;
    if (!nut) return;
    var f = oMau(MAU[nut.getAttribute("data-mau")]);
    Object.keys(f).forEach(function (ten) {
      var el = truong(ten);
      if (!el) return;
      if (el.type === "checkbox") el.checked = f[ten];
      else el.value = f[ten];
      kiemO(el);
    });
    capNhat();
  });
  form.addEventListener("input", function (e) { kiemO(e.target); capNhat(); });
  form.addEventListener("change", function (e) { kiemO(e.target); capNhat(); });
  form.addEventListener("reset", function () {
    window.setTimeout(function () { CAC_O.forEach(kiemO); capNhat(); }, 0);
  });
  form.addEventListener("submit", function () {
    dangLuu = true;
    var nut = o("nut-luu");
    if (nut) {
      nut.disabled = true;
      nut.textContent = "Đang lưu…";
    }
  });
  window.addEventListener("beforeunload", function (e) {
    if (ban && !dangLuu) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  window.addEventListener("pageshow", function (e) {   // quay lại bằng nút Back: mở lại nút Lưu
    if (!e.persisted) return;
    dangLuu = false;
    var nut = o("nut-luu");
    if (nut) {
      nut.disabled = false;
      nut.textContent = "Lưu cấu hình";
    }
  });

  CAC_O.forEach(kiemO);
  capNhat();
})();
