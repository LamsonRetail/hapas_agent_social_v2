// Trang Ngân sách: tính lại NGAY ước tính USD khi sửa cấu hình thu thập từng nền tảng (tìm theo
// từ khoá + cào bình luận) và trần tháng. Công thức chép đúng dashboard/chi_phi.py — `cau_hinh`,
// `uoc_tk_nen_tang`, `uoc_binh_luan_luot`, `bang_cau_hinh`; hằng số (giá, hệ số, giới hạn) do máy
// chủ phát trong #ns-du-lieu, ở đây không tự đặt giá nào. Không có JS thì trang vẫn đủ số (máy chủ
// dựng sẵn) và biểu mẫu vẫn gửi được.
"use strict";
// Nút ⚠ "Dự báo vượt trần" (21/10/2026): mở / đóng khối cảnh báo gập — mọi vai trò (khối biểu mẫu
// bên dưới chỉ chạy cho người sửa được cấu hình).
(function () {
  var nut = document.getElementById("ns-mo-canh-bao");
  var khoi = document.getElementById("ns-canh-bao");
  if (!nut || !khoi) return;
  nut.addEventListener("click", function () {
    var mo = khoi.hidden;
    khoi.hidden = !mo;
    nut.setAttribute("aria-expanded", mo ? "true" : "false");
    if (mo && khoi.scrollIntoView) khoi.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });
})();
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
  // Đường 2 Threads (17/10/2026, = chi_phi.bang_cau_hinh tu_khoa.threads.duong2): biểu mẫu chưa có
  // ô riêng, máy chủ phát cấu hình hiệu lực + USD khi Threads bật — cộng vào ô Threads.
  var TH2 = D.th2 || {};

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
  // Hashtag riêng của dự án (18/10/2026, = chi_phi.nguon_tag, máy chủ đã chuẩn hoá): có thì Instagram
  // + feed TikTok dùng chúng, không thì suy từ từ khoá như trước. Chỉ đổi ĐẦU VÀO, công thức giữ nguyên.
  var TAG_DA = D.hashtag_rieng || [];
  var NGUON_TAG = TAG_DA.length ? TAG_DA : TU;

  // <web> Báo & Web (16/10/2026) — bản sao chi_phi.rut_gon_web / so_cau_web / uoc_web (bài thử
  // tests/test_dashboard_web.py::test_ngan_sach_js_rut_gon_khop_python chạy khối này bằng node).
  var HW = hs.web || {};
  // = chi_phi._bo_dau_web: bỏ dấu + thường hoá TỪNG ký tự (đ/Đ -> d)
  function boDauWeb(s) {
    var ra = "";
    Array.from(String(s || "")).forEach(function (c) {
      if (c === "đ" || c === "Đ") { ra += "d"; return; }
      var g = c.normalize("NFD"), d = Array.from(g)[0];
      ra += (d && !/\p{Mn}/u.test(d) ? d : c).toLowerCase().slice(0, 1) || c;
    });
    return ra;
  }
  // = chi_phi._tu_web: các chữ/số của một từ khoá (bỏ dấu)
  function tuWeb(s) { return boDauWeb(s).match(/[\p{L}\p{N}]+/gu) || []; }
  function laTapConThat(a, b) {      // tập a ⊂ b (thật sự)
    var A = {}, B = {}, na = 0, nb = 0;
    a.forEach(function (x) { if (!A[x]) { A[x] = 1; na++; } });
    b.forEach(function (x) { if (!B[x]) { B[x] = 1; nb++; } });
    if (na >= nb) return false;
    return Object.keys(A).every(function (x) { return B[x]; });
  }
  // = chi_phi.rut_gon_web: bỏ rỗng, bỏ trùng (hoa thường), bỏ từ khoá đã được từ khoá khác phủ
  function rutGonWeb(ds) {
    var sach = [];
    (ds || []).forEach(function (t) {
      t = String(t).trim();
      var th = t.toLowerCase();
      if (t && tuWeb(t).length && !sach.some(function (x) { return x.toLowerCase() === th; })) sach.push(t);
    });
    return sach.filter(function (t, i) {
      var ti = tuWeb(t);
      return !sach.some(function (x, j) { return j !== i && laTapConThat(tuWeb(x), ti); });
    });
  }
  function soCauWeb(ds) {            // = chi_phi.so_cau_web
    var n = rutGonWeb(ds).length;
    return n ? Math.min(HW.toi_da_cau, Math.ceil(n / HW.tu_moi_cau)) : 0;
  }
  function uocWeb(so, ds, boc) {     // = chi_phi.uoc_web
    var cau = soCauWeb(ds);
    if (so <= 0 || cau <= 0) return 0;
    var trang = Math.max(1, Math.ceil(Math.max(0, so) / HW.kq_moi_trang));
    return r4((cau * trang * HW.gia_trang + Math.max(0, boc) * HW.gia_boc) * hs.he_so);
  }
  // </web>

  // Mẫu nhanh: [bật, số bài, (Instagram) số từ] cho tìm từ khoá; [bật, số bài, bình luận/bài] cho
  // bình luận (0 = cào hết). Chỉ ĐIỀN ô — người dùng xem số ước tính rồi mới bấm Lưu.
  var MAU = {
    tiet_kiem: {
      // web: [bật, kết quả mỗi câu, trang đọc dự phòng tối đa]; web không cào bình luận
      tk: { tiktok: [1, 10], facebook: [1, 10], instagram: [1, 5, 1], youtube: [1, 20], threads: [0, 10], web: [1, 10, 2] },
      bl: { tiktok: [1, 3, 20], facebook: [1, 3, 20], instagram: [0, 3, 20], youtube: [1, 10, 100], threads: [0, 3, 20] }
    },
    can_bang: {
      tk: { tiktok: [1, 30], facebook: [1, 20], instagram: [1, 10, 2], youtube: [1, 30], threads: [0, 10], web: [1, 20, 5] },
      bl: { tiktok: [1, 5, 50], facebook: [1, 5, 50], instagram: [1, 3, 30], youtube: [1, 20, 200], threads: [0, 5, 50] }
    },
    day_du: {
      tk: { tiktok: [1, 100], facebook: [1, 20], instagram: [1, 30, 4], youtube: [1, 100], threads: [0, 20], web: [1, 30, 10] },
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
      var c = {
        y: doc.bat("tk_" + p + "_bat"), bat: doc.bat("tk_" + p + "_bat") && so > 0, so_bai: so,
        so_tu: kep(t !== "" ? t : IG_MD, GH.tk_so_tu[0], GH.tk_so_tu[1], IG_MD)
      };
      if (p === "web") {               // trần trang đọc dự phòng: ô trống = mặc định của Mark, 0 = tắt
        var bo = doc.gt("tk_web_boc");
        c.boc = kep(bo !== "" ? bo : HW.boc_mac_dinh, 0, GH.tk_so_bai[1], HW.boc_mac_dinh);
      }
      return c;
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
  // <uoc_tk> (bài thử tests/test_moi_nhat.py::test_ngan_sach_js_uoc_tk_khop_python chạy khối này)
  // = chi_phi.hashtag_ig (17/10/2026): từ khoá -> hashtag Instagram viết liền, bỏ dấu (đ -> d),
  // chỉ giữ [a-z0-9_]; _tu_ig: bỏ rỗng, bỏ trùng, giữ thứ tự.
  function tagIg(s) {
    return String(s || "").replace(/đ/g, "d").replace(/Đ/g, "D").normalize("NFD")
      .replace(/\p{Mn}/gu, "").toLowerCase().replace(/[^a-z0-9_]/g, "");
  }
  var TU_IG = TU.map(tagIg).filter(function (t, i, ds) { return t && ds.indexOf(t) === i; });
  // `tu`, `tuIg` (18/10/2026): từ khoá / hashtag TÌM của nền tảng sau khi bỏ "Không tìm trên…"
  // (`tuP`, `tagP`); bỏ trống = TU / TU_IG như trước.
  function uocTk(p, so, soTu, boc, tu, tuIg) {
    tu = tu || TU;
    tuIg = tuIg || TU_IG;
    if (p === "web") return uocWeb(so, tu, boc);
    // Threads (= chi_phi.tu_gui): chỉ `so // 10` từ đầu (≥ 1, ≤ 20) — actor lấy ≥ 10 bài mỗi từ.
    var thMin = hs.th_toi_thieu_bai || 10;
    var q = p === "instagram" ? tuIg.slice(0, soTu)
      : p === "threads" ? tu.slice(0, Math.max(1, Math.min(hs.th_toi_da_moi_luot || 20, Math.floor(so / thMin))))
      : tu;
    var gia = (hs.tk_gia || {})[p] || 0;
    if (!q.length || !gia || so <= 0) return 0;
    if (p === "instagram") {         // hai run (tab bài + reels), mỗi run mọi hashtag × trần mỗi tag
      var tab = hs.tk_ig_tab || 2;
      var per = Math.max(1, Math.ceil(so / (tab * q.length)));
      return r4((tab * q.length * per * gia + tab * (hs.tk_khoi.instagram || 0)) * hs.he_so);
    }
    if (p === "tiktok") {            // TikTok API tính theo YÊU CẦU (= chi_phi.uoc_tk_nen_tang)
      var trang = 2 * Math.ceil(Math.ceil(so / q.length) / (hs.tk_tt_moi_trang || 30)) + 1 + (hs.tk_tt_moi_nhat || 0);
      return r4((q.length * trang + (hs.tk_lam_moi || 0)) * (hs.tk_tt_yeu_cau || 0) * hs.he_so);
    }
    var n = p === "threads" ? Math.max(so, thMin) : so;
    return r4((n * gia + ((hs.tk_khoi || {})[p] || 0)) * hs.he_so);
  }
  // </uoc_tk>
  if (TAG_DA.length) {               // = chi_phi.tu_gui("instagram", nguon_tag(...))
    TU_IG = NGUON_TAG.map(tagIg).filter(function (t, i, ds) { return t && ds.indexOf(t) === i; });
  }
  // <bo_tu> "Không tìm trên…" (18/10/2026) — = chi_phi.bo_tu / tu_nen_tang / tag_cua (bài thử
  // tests/test_bo_tu.py::test_ngan_sach_js_bo_tu_khop_python chạy khối này bằng node). Đọc ô
  // `tk_<p>_bo_tu` đang gõ (mẫu nhanh không đổi ô này), trang không có ô thì theo danh sách đã lưu.
  function boTu(p, doc) {
    var ten = "tk_" + p + "_bo_tu";
    var s = doc && form && form.elements.namedItem(ten) ? doc.gt(ten) : null;
    var ds = s == null ? ((D.bo_tu || {})[p] || []) : s.split(/[,\n;]+/);
    return ds.map(function (x) { return String(x).trim(); }).filter(Boolean);
  }
  function khoaBo(s) {
    return norm(String(s || "").replace(/#/g, " ").split(/\s+/).filter(Boolean).join(" "));
  }
  function khoaTag(s) { return tagIg(s).replace(/[^a-z0-9]/g, ""); }
  function tuP(p, doc) {
    var bo = {};
    boTu(p, doc).forEach(function (x) { bo[khoaBo(x)] = 1; });
    return TU.filter(function (x) { return !bo[khoaBo(x)]; });
  }
  function tagP(p, doc) {            // đầu vào hashtag (= chi_phi.tag_cua)
    var bo = {};
    boTu(p, doc).forEach(function (x) {
      if (String(x).replace(/#/g, " ").split(/\s+/).filter(Boolean).length === 1 && khoaTag(x)) bo[khoaTag(x)] = 1;
    });
    return (TAG_DA.length ? TAG_DA : tuP(p, doc)).filter(function (t) { return !bo[khoaTag(t)]; });
  }
  function igP(doc) {                // = chi_phi._tu_ig(tag_cua("instagram"))
    return tagP("instagram", doc).map(tagIg).filter(function (t, i, ds) { return t && ds.indexOf(t) === i; });
  }
  // </bo_tu>
  // Threads đường 1 (19/10/2026, = chi_phi.tu_threads_duong1): danh sách gốc máy chủ phát (`th1_goc`
  // — ghi đè duong1_tu hoặc từ một chữ có tên brand) bỏ "Không tìm trên Threads" đang gõ; rỗng =
  // đường 1 tắt → ước tính đường 1 = 0 (chỉ còn đường 2). Trang cũ không có `th1_goc`: như trước.
  function tuD1(doc) {
    if (!Array.isArray(D.th1_goc)) return tuP("threads", doc);
    var bo = {};
    boTu("threads", doc).forEach(function (x) { bo[khoaBo(x)] = 1; });
    return D.th1_goc.filter(function (x) { return !bo[khoaBo(x)]; });
  }
  function uocBl(p, so, moi) {       // = chi_phi.uoc_binh_luan_luot
    moi = moi || hs.bl_uoc_moi_bai;
    var gia = (hs.bl_gia || {})[p] || 0;
    if (!so || !gia) return 0;
    return r4((so * moi * gia + ((hs.bl_khoi || {})[p] || 0)) * hs.he_so);
  }
  // Facebook đường 2 (17/10/2026) — = chi_phi._cau_hinh_fb2 / tu_fb_duong2 / uoc_fb_duong2: cụm ≥ 2
  // chữ có tên brand, mỗi cụm một run × (bài × giá + phí khởi động) × hệ số; dòng riêng dưới Facebook.
  var HF2 = hs.fb2 || {};
  function chuCua(s) { return norm(s).match(/[\p{L}\p{N}]+/gu) || []; }   // = chi_phi._tokens
  var TEN = chuCua(D.ten);
  function cumFb2(doc) {             // = chi_phi.tu_fb_duong2(du_an, tu_nen_tang("facebook"))
    return tuP("facebook", doc).filter(function (kw) {
      var c = chuCua(kw);
      return String(kw).split(/\s+/).filter(Boolean).length >= 2 && TEN.length > 0 &&
        (TEN.every(function (t) { return c.indexOf(t) >= 0; }) || c.indexOf(TEN.join("")) >= 0);
    });
  }
  function cauHinhD2(doc, fb) {
    var o = doc.gt("tk_facebook_d2_so_bai");
    var so = kep(o !== "" ? o : HF2.moi_tu, 0, GH.tk_so_bai[1], HF2.moi_tu);
    var y = doc.bat("tk_facebook_d2_bat") && !!fb.y;
    var c = { y: y, bat: y && so > 0, so_bai: so };
    var cum = cumFb2(doc);
    c.so_cum = cum.length;
    c.uoc = c.bat && cum.length ? r4(cum.length * (so * HF2.gia + HF2.khoi) * hs.he_so) : 0;
    return c;
  }
  // TikTok feed hashtag (17/10/2026) — = chi_phi._cau_hinh_tag / tag_tiktok / uoc_tag_tiktok: từ
  // khoá MỘT chữ thành hashtag (bỏ '#', bỏ dấu, chỉ [0-9a-z], 3–40 ký tự), trần yêu cầu × giá × hệ số.
  var HTT = hs.tt_tag || {};
  function tagTt(doc) {              // = chi_phi.tag_tiktok(tag_cua("tiktok"))
    var ra = [];
    tagP("tiktok", doc).forEach(function (kw) {
      if (String(kw).split(/\s+/).filter(Boolean).length !== 1) return;
      var t = norm(String(kw).replace(/^#+/, "")).replace(/[^0-9a-z]/g, "");
      if (t.length >= 3 && t.length <= 40 && ra.indexOf(t) < 0) ra.push(t);
    });
    return ra;
  }
  function cauHinhTag(doc, tt) {
    var o = doc.gt("tk_tiktok_tag_so_yc");
    var so = kep(o !== "" ? o : HTT.yeu_cau, 0, GH.tk_so_bai[1], HTT.yeu_cau);
    var y = doc.bat("tk_tiktok_tag_bat") && !!tt.y;
    var c = { y: y, bat: y && so > 0, so_bai: so };
    var tag = tagTt(doc);
    c.so_tag = tag.length;
    c.uoc = c.bat && tag.length ? r4(so * (hs.tk_tt_yeu_cau || 0) * hs.he_so) : 0;
    return c;
  }
  // Threads "Tìm rộng hơn" (= chi_phi.cau_hinh_th2 + uoc_th2, máy chủ tính sẵn trong D.th2). 18/10/2026
  // có công tắc ở khối Nâng cao: bật thì cộng `uoc_neu_bat`; trang không có công tắc thì theo cấu hình
  // đã lưu như trước (`bat_rieng` + `uoc_khi_bat`).
  function cauHinhTh2(doc, th) {
    var co = !!form.elements.namedItem("tk_threads_d2_bat");
    var y = (co ? doc.bat("tk_threads_d2_bat") : !!TH2.bat_rieng) && !!th.y;
    var c = { y: y, bat: y && !!th.bat };
    c.uoc = c.bat ? (co ? (TH2.uoc_neu_bat || 0) : (TH2.uoc_khi_bat || 0)) : 0;
    return c;
  }
  function tinh(doc) {               // = chi_phi.bang_cau_hinh
    var kq = { tk: {}, bl: {} };
    var stk = 0;
    var sbl = 0;
    var ig = igP(doc);
    NT.forEach(function (p) {
      var a = cauHinh(doc, "tk", p);
      var b = cauHinh(doc, "bl", p);
      a.tu = tuP(p, doc);
      a.uoc = a.bat ? uocTk(p, a.so_bai, a.so_tu, a.boc,
        p === "threads" && a.tu.length ? tuD1(doc) : a.tu, ig) : 0;
      if (p === "threads") {
        a.th2 = cauHinhTh2(doc, a);
        a.uoc = r4(a.uoc + a.th2.uoc);
      }
      b.uoc = b.bat ? uocBl(p, b.so_bai, b.moi_bai) : 0;
      kq.tk[p] = a;
      kq.bl[p] = b;
      stk += a.uoc;
      sbl += b.uoc;
    });
    kq.d2 = cauHinhD2(doc, kq.tk.facebook || {});
    stk += kq.d2.uoc;
    kq.tag = cauHinhTag(doc, kq.tk.tiktok || {});
    stk += kq.tag.uoc;
    kq.ig = ig;
    kq.uoc_tk = r4(stk);
    kq.uoc_bl = r4(sbl);
    kq.tong = r4(kq.uoc_tk + kq.uoc_bl);
    kq.web = kq.tk.web ? kq.tk.web.uoc : 0;          // = bang_cau_hinh["uoc_web"]
    kq.khac = Math.max(0, r4(kq.tong - kq.web));
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
      // Báo & Web chỉ bật theo duyệt của chủ dự án (mặc định TẮT): mẫu nhanh KHÔNG đổi công tắc
      // web, chỉ đổi số; web không có bình luận.
      if (p !== "web") f["tk_" + p + "_bat"] = !!a[0];
      f["tk_" + p + "_so_bai"] = String(a[1]);
      if (p === "instagram") f.tk_instagram_so_tu = String(a[2]);
      if (p === "web") { f.tk_web_boc = String(a[2]); return; }
      f["bl_" + p + "_bat"] = !!b[0];
      f["bl_" + p + "_so_bai"] = String(b[1]);
      f["bl_" + p + "_moi_bai"] = String(b[2]);
    });
    return f;
  }
  // Ô mẫu nhanh KHÔNG đặt (dòng phụ đường 2 / feed hashtag, kiểm độ phủ) giữ giá trị đang có trên
  // biểu mẫu — bấm mẫu không đổi các ô đó, nên giá của mẫu tính theo đúng giá trị đang có.
  function docTu(f) {
    return {
      gt: function (ten) { return f[ten] == null ? docForm.gt(ten) : String(f[ten]); },
      bat: function (ten) { return ten in f ? !!f[ten] : docForm.bat(ten); }
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
  // Ô USD của một dòng. 18/10/2026: ô tìm theo từ khoá gồm cả phần mở rộng ở Nâng cao, nên "0 bài"
  // hay "miễn phí" chỉ khi cả dòng thật sự 0 USD (= macro o_usd của ngan_sach.html).
  function oUsd(khoa, c, gia) {
    var e = o(khoa);
    if (!e) return;
    var het = !c.so_bai && !c.uoc;
    var chu = !c.y ? "tắt" : het ? "tắt (0 bài)" : !gia && !c.uoc ? "miễn phí" : soVn(c.uoc, 3);
    ghi(khoa, chu, c.uoc);
    e.classList.toggle("ns-tat-chu", !c.y || het);
    e.classList.toggle("ns-mien-phi", !!(c.y && !het && !gia && !c.uoc));
  }
  // Ô USD của một mục Nâng cao (= macro o_nc): "tắt" hoặc "+x USD/lượt".
  function oNc(khoa, c) {
    var e = o(khoa);
    if (!e || !c) return;
    ghi(khoa, c.bat ? "+" + soVn(c.uoc, 3) + " USD/lượt" : "tắt", c.uoc);
    e.classList.toggle("ns-tat-chu", !c.bat);
  }
  function moNhom(p, nhom, bat) {
    var dong = form.querySelector('tr[data-nt="' + p + '"]');
    if (!dong) return;
    dong.querySelectorAll('[data-nhom="' + nhom + '"]').forEach(function (td) {
      td.classList.toggle("ns-mo", !bat);
    });
  }
  // Mục Nâng cao mờ đi khi nền tảng "cha" của nó tắt ở bảng trên.
  function moMuc(p, bat) {
    form.querySelectorAll('.ns-nc__muc[data-cha="' + p + '"]').forEach(function (m) {
      m.classList.toggle("ns-mo", !bat);
    });
  }
  // <do_phu> (bài thử tests/test_kiem_do_phu.py::test_ngan_sach_js_do_phu_khop_python chạy khối này)
  function soTien(s, md) {           // ô trần tháng: nhận cả "5,5"
    var x = parseFloat(String(s || "").replace(/\s/g, "").replace(",", "."));
    return isFinite(x) ? x : md;
  }
  // Kiểm độ phủ (17/10/2026, 2 lần/tuần) — = chi_phi.cau_hinh_do_phu: ô trống / rác / âm → mặc định,
  // kẹp [0, trần tối đa], trần 0 = tắt. -> USD tối đa mỗi lần (0 khi tắt).
  var HDP = hs.do_phu || {};
  function dpUsd(doc) {
    if (!doc.bat("dp_bat")) return 0;
    var o = doc.gt("dp_tran");
    var t = o === "" ? HDP.tran_mac_dinh : soTien(o, HDP.tran_mac_dinh);
    if (!isFinite(t) || t < 0) t = HDP.tran_mac_dinh;
    return Math.round(Math.min(HDP.tran_toi_da, t) * 100) / 100;
  }
  // </do_phu>

  // ── trạng thái chưa lưu ──
  var CAC_O = Array.prototype.filter.call(form.elements, function (e) {
    return e.name && e.name !== "csrf" && (e.type === "checkbox" || e.type === "number" ||
      /_bo_tu$/.test(e.name));        // ô chữ "Không tìm trên…" (18/10/2026) cũng là thay đổi chưa lưu
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
    // Phần mở rộng ở Nâng cao CỘNG vào ô của nền tảng nó thuộc (Threads: `tinh` đã cộng) — tổng
    // các dòng luôn bằng "Tổng mỗi lượt".
    var them = { facebook: kq.d2.uoc, tiktok: kq.tag.uoc };
    NT.forEach(function (p) {
      var a = kq.tk[p];
      var b = kq.bl[p];
      var dongTk = r4(a.uoc + (them[p] || 0));
      oUsd("tk-" + p, { y: a.y, so_bai: a.so_bai, uoc: dongTk },
        p === "web" ? HW.gia_trang : (hs.tk_gia || {})[p]);
      oUsd("bl-" + p, b, (hs.bl_gia || {})[p]);
      ghi("dong-" + p, soVn(r4(dongTk + b.uoc), 3), r4(dongTk + b.uoc));
      moNhom(p, "tk", a.y);
      moNhom(p, "bl", b.y);
      moMuc(p, a.y);
    });
    var th2 = (kq.tk.threads || {}).th2;
    oNc("tk-facebook_d2", kq.d2);
    oNc("tk-tiktok_tag", kq.tag);
    oNc("tk-threads_d2", th2);
    var nc = r4(kq.d2.uoc + kq.tag.uoc + (th2 ? th2.uoc : 0));
    ghi("nc-tong", soVn(nc, 3), nc);
    var ig = kq.tk.instagram;         // hashtag Instagram thật sự gửi (số hashtag đặt ở Nâng cao)
    if (ig) {
      var igq = kq.ig.slice(0, ig.so_tu);
      ghi("ig-tag", igq.length ? "#" + igq.join(" #") + " (" + igq.length + " hashtag)" : "chưa có hashtag nào");
    }
    // Số từ khoá / cụm / hashtag THẬT SỰ tìm — đổi ngay khi sửa "Không tìm trên…" (18/10/2026).
    var wb = kq.tk.web;
    if (wb) ghi("web-so-tu", rutGonWeb(wb.tu).length + " → " + soCauWeb(wb.tu) + " câu");
    ghi("fb2-so-cum", String(kq.d2.so_cum));
    ghi("tt-tag-so", String(kq.tag.so_tag));
    NT.forEach(function (p) {
      var a = kq.tk[p];
      var bo = TU.length - a.tu.length;
      ghi("bo-tu-" + p, bo ? "tìm " + a.tu.length + "/" + TU.length + " từ khoá" : "tìm đủ " + TU.length + " từ khoá");
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
    // Báo & Web: số lượt web riêng (ngoài chiến dịch ≤ 1 lượt/ngày — máy chủ đếm theo lịch).
    var luot30 = D.co_lich ? (D.luot_30 || 0) : hs.ngay;
    var web30 = D.luot_web_30 != null ? D.luot_web_30 : luot30;
    var tien30 = kq.khac * luot30 + kq.web * web30;
    ghi("tong-30", soVn(tien30, 2), r4(tien30));

    // cả tháng nếu mỗi lượt dùng hết = đã tiêu + nguồn còn lại + số lượt còn lại × tổng mỗi lượt
    // (trừ web) + số lượt web còn lại × USD một lượt web
    var tranDa = soTien(docForm.gt("tran_usd_thang"), D.tran_da);
    var tran = D.tran_platform == null ? tranDa : Math.min(tranDa, D.tran_platform);
    var ngay = D.co_lich ? (D.luot_con_lai || 0) : (D.ngay_con_lai || 0);
    var luotWeb = D.luot_web_con_lai != null ? D.luot_web_con_lai : ngay;
    var webCon = luotWeb * kq.web;
    var dp = D.dp || {};
    var dpLan = form.elements.namedItem("dp_tran") ? dpUsd(docForm) : null;
    var dpCon = dpLan == null ? 0 : (dp.luot_con_lai || 0) * dpLan;
    if (dpLan != null) {
      ghi("dp-chu", dpLan > 0 ? "tối đa " + soVn(dpLan, 2) + " USD/lần · ≈ " + soVn((dp.luot_30 || 0) * dpLan, 2) +
        " USD/30 ngày" : "tắt", dpLan);
    }
    var toiDa = D.da_tieu + D.nguon_con_lai + ngay * kq.khac + webCon + dpCon;
    // Trần việc nền trên console (18/10/2026, ảnh chụp gói của Mark): mỗi lượt không tiêu quá
    // D.tran_luot USD — giữ chỗ 60 bình luận/bài không làm "cả tháng" lố hơn số đó × số lượt.
    if (D.tran_luot != null && ngay > 0) toiDa = Math.min(toiDa, D.da_tieu + ngay * D.tran_luot);
    var vuot = toiDa > tran + 1e-9;
    var duLuot = ngay > 0 ? (tran - D.da_tieu - D.nguon_con_lai - webCon - dpCon) / ngay : 0;
    ghi("thang-so", soVn(toiDa, 2), r4(toiDa));
    ghi("thang-tran", soVn(tran, 2), tran);
    ghi("thang-ket-luan", vuot
      ? "vượt trần " + soVn(toiDa - tran, 2) + " USD, Mark dừng quét khi chạm trần; " +
        (duLuot > 0 ? "vừa trần khi ≤ " + soVn(duLuot, 3) + " USD/lượt." : "riêng nguồn theo dõi đã chạm trần.")
      : "trong trần, còn dư " + soVn(tran - toiDa, 2) + " USD.");
    ghiGoiY("thang-cong-thuc", "= đã tiêu " + soVn(D.da_tieu, 2) + " + nguồn " + soVn(D.nguon_con_lai, 2) +
      " + " + (D.co_lich ? soVn(ngay, 0) + " lượt theo lịch" : soVn(ngay, 1) + " ngày") + " × " +
      soVn(kq.khac, 3) + " + Báo & Web " + soVn(luotWeb, luotWeb % 1 ? 1 : 0) + " lượt × " + soVn(kq.web, 3) +
      " (ngoài chiến dịch ≤ 1 lượt/ngày) + kiểm độ phủ " + soVn(dp.luot_con_lai || 0, 0) + " lần × " +
      soVn(dpLan || 0, 2));
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

  ghiGoiY("ghi-ig", (TAG_DA.length ? "Tìm theo hashtag của dự án (" : "Từ khoá viết liền thành hashtag, bỏ dấu (") +
    igP(docForm).length + " hashtag); tab bài + reels, " + soVn((hs.tk_gia || {}).instagram || 0, 4) + " USD/bài");

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
  // Ô sai nằm trong khối "Nâng cao" đang thu gọn: mở khối để trình duyệt chỉ được vào ô đó (ô bị ẩn
  // thì trình duyệt chặn gửi mà không báo gì).
  form.addEventListener("invalid", function (e) {
    var k = e.target && e.target.closest ? e.target.closest("details") : null;
    if (k && !k.open) k.open = true;
  }, true);
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
