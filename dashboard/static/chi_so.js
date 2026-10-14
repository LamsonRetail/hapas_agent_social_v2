// Trang Chỉ số: lấy JSON /api/chi-so theo bộ lọc, vẽ thẻ KPI + biểu đồ ECharts + bảng.
// Thời gian thực: nghe /su-kien; có `cap-nhat` của đúng dự án thì tải lại số (không tải lại
// trang) và ghi "cập nhật lúc HH:MM:SS".
// An toàn: chữ từ kho (tên nguồn, nội dung bài, chủ đề…) chỉ đi qua textContent; link chỉ nhận
// http(s); tooltip ECharts vẽ bằng canvas (renderMode richText) nên không có HTML từ dữ liệu.
"use strict";
(function () {
  var cfgEl = document.getElementById("cau-hinh-chi-so");
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent || "{}");
  if (!cfg.du_an) return;

  var SO = new Intl.NumberFormat("vi-VN");
  var bieuDo = {};
  var duLieu = null;
  var henGio = null;
  var nenTangChon = null;

  // ─── tiện ích ───
  function $(id) { return document.getElementById(id); }
  function so(n) { return n == null ? "—" : SO.format(n); }
  function pt(x) {
    return x == null ? "—" : x.toLocaleString("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
  }
  function ngayNgan(iso) { var p = String(iso).split("-"); return p[2] + "/" + p[1]; }
  function ngayDu(iso) {
    if (!iso) return "—";
    var p = String(iso).slice(0, 10).split("-");
    return p[2] + "/" + p[1] + "/" + p[0];
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
  function linkAnToan(url, chu) {
    if (url && /^https?:\/\//i.test(url)) {
      var a = tao("a", "", chu);
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      return a;
    }
    return tao("span", "", chu);
  }
  function xoa(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  // Màu đi theo đối tượng (không theo thứ hạng): cùng một nền tảng luôn cùng một màu.
  function mau() {
    return {
      chu: bien("--chu"), phu: bien("--chu-phu"), mo: bien("--chu-mo"), ke: bien("--ke"),
      truc: bien("--truc"), mat: bien("--be-mat"),
      sac: { "Tích cực": bien("--s1"), "Trung lập": bien("--trung-lap"), "Tiêu cực": bien("--s8"),
             "chưa phân loại": bien("--chua"), "kênh nhà": bien("--s7") },
      nen: { tiktok: bien("--s1"), facebook: bien("--s2"), youtube: bien("--s3"), instagram: bien("--s4") },
      loai: { kol: bien("--s1"), page: bien("--s2"), group: bien("--s3"), bao: bien("--s4"),
              khac: bien("--s5"), tu_khoa: bien("--s6"), kenh_nha: bien("--s7") },
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
      legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10,
                textStyle: { color: m.phu, fontSize: 12 } }
    };
  }
  function trucDanhMuc(m, du) {
    return { type: "category", data: du, axisLine: { lineStyle: { color: m.truc } },
             axisTick: { show: false }, axisLabel: { color: m.mo, fontSize: 11, hideOverlap: true } };
  }
  function trucSo(m) {
    return { type: "value", splitLine: { lineStyle: { color: m.ke } },
             axisLabel: { color: m.mo, fontSize: 11, formatter: function (v) { return SO.format(v); } } };
  }

  // Bấm vào biểu đồ → khung chi tiết (đợt 2b). Mỗi biểu đồ đặt hàm xử lý ở `xuLyBam[id]` mỗi
  // lần vẽ; sự kiện ECharts gắn MỘT lần lúc khởi tạo nên vẽ lại không gắn trùng.
  var xuLyBam = {};
  function ve(id, opt) {
    var el = $(id);
    if (!el || !window.echarts) return;
    var bd = bieuDo[id];
    if (!bd) {
      bd = bieuDo[id] = window.echarts.init(el, null, { renderer: "canvas" });
      bd.on("click", function (p) {
        var f = xuLyBam[id];
        if (f && p.componentType === "series" && p.dataIndex != null) f(p);
      });
    }
    bd.setOption(opt, true);
  }

  // ─── KPI ───
  function theKpi(nhan, giaTri, doi, ghiChu) {
    var o = tao("div", "the-khoi kpi");
    o.appendChild(tao("div", "kpi__nhan", nhan));
    o.appendChild(tao("div", "kpi__so so", giaTri));
    var d = tao("div", "kpi__doi");
    if (doi) {
      if (doi.doi_pt == null) {
        d.textContent = "kỳ trước " + so(doi.truoc);
      } else {
        var lop = doi.doi_pt > 0 ? "tang" : doi.doi_pt < 0 ? "giam" : "";
        var mui = doi.doi_pt > 0 ? "▲ +" : doi.doi_pt < 0 ? "▼ " : "■ ";
        d.appendChild(tao("span", lop, mui + pt(doi.doi_pt)));
        d.appendChild(document.createTextNode(" so với kỳ trước"));
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
    el.appendChild(theKpi("Lượt xem", so(k.xem), ss.xem));
    el.appendChild(theKpi("Tương tác", so(k.tuong_tac), ss.tuong_tac));
    el.appendChild(theKpi("Tích cực", pt(k.tich_cuc_pt), null, so(k.tich_cuc) + " bài"));
    el.appendChild(theKpi("Tiêu cực", pt(k.tieu_cuc_pt), null, so(k.tieu_cuc) + " bài"));
    el.appendChild(theKpi("Trung lập", pt(k.trung_lap_pt), null, so(k.trung_lap) + " bài"));
    el.appendChild(theKpi("Chưa phân loại", so(k.chua_phan_loai), null,
                          k.bai_kenh_nha ? "+ " + so(k.bai_kenh_nha) + " bài kênh nhà" : "bài"));
  }

  // ─── biểu đồ ───
  function veXuHuong(d, m) {
    var x = d.xu_huong, nhan = x.moc.map(x.don_vi === "tuần" ? function (s) { return "từ " + ngayNgan(s); } : ngayNgan);
    $("don-vi-xu-huong").textContent = "theo " + x.don_vi + " đăng (giờ VN)";
    var o = coBan(m);
    o.legend.show = false;
    o.xAxis = trucDanhMuc(m, nhan);
    o.yAxis = trucSo(m);
    o.series = [{
      name: "Thảo luận", type: "line", data: x.thao_luan, smooth: false, showSymbol: x.moc.length <= 45,
      symbolSize: 8, lineStyle: { width: 2, color: m.chinh }, itemStyle: { color: m.chinh },
      areaStyle: { color: m.chinh, opacity: 0.08 },
      markPoint: x.dinh ? { symbol: "circle", symbolSize: 10, itemStyle: { color: m.chinh },
        label: { position: "top", color: m.chu, fontSize: 11, formatter: function (p) { return "đỉnh " + so(p.value); } },
        data: [{ type: "max" }] } : undefined
    }];
    ve("bd-xu-huong", o);
    xuLyBam["bd-xu-huong"] = function (p) {
      var kh = khoangMoc(x, p.dataIndex);
      moChiTiet("bai", kh, so(x.thao_luan[p.dataIndex]) + " thảo luận " + moTaKhoang(kh));
    };

    var o2 = coBan(m);
    o2.xAxis = trucDanhMuc(m, nhan);
    o2.yAxis = trucSo(m);
    var lop = [["Tích cực", "tich_cuc"], ["Trung lập", "trung_lap"], ["Tiêu cực", "tieu_cuc"],
               ["chưa phân loại", "chua_phan_loai"], ["kênh nhà", "kenh_nha"]];
    o2.series = lop.map(function (l, i) {
      return { name: l[0], type: "bar", stack: "bai", data: x[l[1]], barMaxWidth: 18,
               itemStyle: { color: m.sac[l[0]], borderColor: m.mat, borderWidth: 1,
                            borderRadius: i === lop.length - 1 ? [4, 4, 0, 0] : 0 } };
    });
    ve("bd-bai-ngay", o2);
    xuLyBam["bd-bai-ngay"] = function (p) {
      var kh = khoangMoc(x, p.dataIndex);
      moChiTiet("bai", Object.assign({ sac_thai: p.seriesName }, kh), p.seriesName + " · " + moTaKhoang(kh));
    };
  }

  function veThanhNgang(id, m, ten, gia, mauCua, nhanCuoi) {
    var o = coBan(m);
    o.legend.show = false;
    o.tooltip.trigger = "item";
    o.grid.top = 8;
    o.yAxis = Object.assign(trucDanhMuc(m, ten.slice().reverse()), { axisLabel: { color: m.phu, fontSize: 12, width: 140, overflow: "truncate" } });
    o.xAxis = trucSo(m);
    var dl = gia.slice().reverse();
    var mauDl = mauCua.slice().reverse();
    var nhanDl = (nhanCuoi || []).slice().reverse();
    o.series = [{ type: "bar", barMaxWidth: 18, name: "Thảo luận",
      data: dl.map(function (v, i) { return { value: v, itemStyle: { color: mauDl[i], borderRadius: [0, 4, 4, 0] } }; }),
      label: { show: true, position: "right", color: m.phu, fontSize: 11,
               formatter: function (p) { return nhanDl[p.dataIndex] || so(p.value); } } }];
    ve(id, o);
  }

  function veSacThai(d, m) {
    var tong = d.sac_thai.reduce(function (a, x) { return a + x.so; }, 0);
    var daPhan = d.sac_thai.filter(function (x) { return x.sac_thai !== "chưa phân loại"; })
      .reduce(function (a, x) { return a + x.so; }, 0);
    veThanhNgang("bd-sac-thai", m, d.sac_thai.map(function (x) { return x.sac_thai; }),
      d.sac_thai.map(function (x) { return x.so; }),
      d.sac_thai.map(function (x) { return m.sac[x.sac_thai]; }),
      d.sac_thai.map(function (x) {
        if (x.sac_thai === "chưa phân loại" || !daPhan) return so(x.so);
        return so(x.so) + " · " + pt(Math.round(1000 * x.so / daPhan) / 10);
      }));
    xuLyBam["bd-sac-thai"] = function (p) {
      var x = d.sac_thai[d.sac_thai.length - 1 - p.dataIndex];
      if (x) moChiTiet("bai", { sac_thai: x.sac_thai }, "sắc thái " + x.sac_thai);
    };
    $("ghi-chu-sac-thai").textContent = tong ? "% tính trên " + so(daPhan) + " bài đã phân loại; không tính bài kênh nhà." : "";

    var cd = d.sac_thai_chu_de.slice(0, 12);
    var o = coBan(m);
    o.grid.top = 32;
    o.yAxis = Object.assign(trucDanhMuc(m, cd.map(function (x) { return x.chu_de; }).reverse()),
                            { axisLabel: { color: m.phu, fontSize: 12, width: 150, overflow: "truncate" } });
    o.xAxis = trucSo(m);
    var lop = ["Tích cực", "Trung lập", "Tiêu cực", "chưa phân loại"];
    o.series = lop.map(function (s, i) {
      return { name: s, type: "bar", stack: "cd", barMaxWidth: 18,
               data: cd.map(function (x) { return x[s]; }).reverse(),
               itemStyle: { color: m.sac[s], borderColor: m.mat, borderWidth: 1,
                            borderRadius: i === lop.length - 1 ? [0, 4, 4, 0] : 0 } };
    });
    $("bd-chu-de").style.height = Math.max(220, 60 + 30 * cd.length) + "px";
    if (bieuDo["bd-chu-de"]) bieuDo["bd-chu-de"].resize();
    ve("bd-chu-de", o);
    xuLyBam["bd-chu-de"] = function (p) {
      var x = cd[cd.length - 1 - p.dataIndex];
      if (x) moChiTiet("bai", { chu_de: x.chu_de, sac_thai: p.seriesName }, x.chu_de + " · " + p.seriesName);
    };
    $("trong-chu-de").hidden = cd.length > 0;
  }

  function vePhanBo(d, m) {
    veThanhNgang("bd-nen-tang", m, d.nen_tang.map(function (x) { return x.ten; }),
      d.nen_tang.map(function (x) { return x.thao_luan; }),
      d.nen_tang.map(function (x) { return m.nen[x.nen_tang] || m.mo; }),
      d.nen_tang.map(function (x) { return so(x.thao_luan) + " (" + so(x.bai) + " bài)"; }));
    veThanhNgang("bd-loai-nguon", m, d.loai_nguon.map(function (x) { return x.ten; }),
      d.loai_nguon.map(function (x) { return x.thao_luan; }),
      d.loai_nguon.map(function (x) { return m.loai[x.loai] || m.mo; }),
      d.loai_nguon.map(function (x) { return so(x.thao_luan) + " (" + so(x.bai) + " bài)"; }));
    xuLyBam["bd-nen-tang"] = function (p) {
      var x = d.nen_tang[d.nen_tang.length - 1 - p.dataIndex];
      if (x) moChiTiet("bai", { nen_tang: x.nen_tang }, x.ten);
    };
    xuLyBam["bd-loai-nguon"] = function (p) {
      var x = d.loai_nguon[d.loai_nguon.length - 1 - p.dataIndex];
      if (x) moChiTiet("bai", { loai: x.loai }, x.ten);
    };
  }

  // ─── bảng ───
  function bang(cot, dong) {
    var t = tao("table"), th = tao("thead"), tr = tao("tr");
    cot.forEach(function (c) { tr.appendChild(tao("th", c.so ? "so" : "", c.ten)); });
    th.appendChild(tr);
    t.appendChild(th);
    var tb = tao("tbody");
    dong.forEach(function (r) {
      var hang = tao("tr");
      cot.forEach(function (c) {
        var td = tao("td", c.so ? "so" : (c.lop || ""));
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
    var tabs = $("tab-nen-tang"), noi = $("top-nguon");
    xoa(tabs);
    xoa(noi);
    if (!d.top_nguon.length) { noi.appendChild(tao("div", "trong", "Chưa có bài trong khoảng này.")); return; }
    if (!d.top_nguon.some(function (x) { return x.nen_tang === nenTangChon; })) nenTangChon = d.top_nguon[0].nen_tang;
    d.top_nguon.forEach(function (g) {
      var b = tao("button", "", g.ten_nen_tang + " · " + so(g.so_nguon));
      b.type = "button";
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", g.nen_tang === nenTangChon ? "true" : "false");
      b.addEventListener("click", function () { nenTangChon = g.nen_tang; veTopNguon(duLieu); });
      tabs.appendChild(b);
    });
    var g = d.top_nguon.filter(function (x) { return x.nen_tang === nenTangChon; })[0];
    noi.appendChild(bang([
      { ten: "Nguồn", lay: function (r) {
        var w = tao("div");
        w.appendChild(linkAnToan(r.link, r.ten));
        if (r.dinh_danh && r.dinh_danh !== r.ten) w.appendChild(tao("div", "mo nho", r.dinh_danh));
        return w; } },
      { ten: "Loại", lay: function (r) { return r.ten_loai; } },
      { ten: "Bài", so: true, lay: function (r) { return so(r.bai); } },
      { ten: "Bình luận", so: true, lay: function (r) { return so(r.binh_luan); } },
      { ten: "Thảo luận", so: true, lay: function (r) { return so(r.thao_luan); } },
      { ten: "Lượt xem", so: true, lay: function (r) { return so(r.xem); } },
      { ten: "", lay: function (r) {
        var b = tao("button", "nut nut--nhe nut--nho", "Xem bài");
        b.type = "button";
        b.addEventListener("click", function () { moChiTiet("bai", { nguon: r.khoa_nguon, nen_tang: g.nen_tang }, r.ten); });
        return b; } }
    ], g.nguon));
  }

  function veTuKhoa(d) {
    var el = $("tu-khoa");
    xoa(el);
    if (!d.tu_khoa.length) { el.appendChild(tao("div", "trong", "Chưa đủ bài để có từ khoá nổi bật (cụm phải xuất hiện ở ít nhất 2 bài).")); return; }
    d.tu_khoa.forEach(function (x) {
      var s = tao("button", "", x.tu);
      s.type = "button";
      s.appendChild(tao("b", "", so(x.so_bai)));
      s.title = so(x.so_bai) + " bài nhắc — bấm để xem";
      s.addEventListener("click", function () { moChiTiet("bai", { cum: x.tu }, "bài nhắc “" + x.tu + "”"); });
      el.appendChild(s);
    });
  }

  function veTopBai(d) {
    var el = $("top-bai");
    xoa(el);
    if (!d.top_bai.length) { el.appendChild(tao("div", "trong", "Chưa có bài trong khoảng này.")); return; }
    el.appendChild(bang([
      { ten: "Bài", lop: "cat-chu", lay: function (r) { return linkAnToan(r.link, r.noi_dung || r.link || "(không có chữ)"); } },
      { ten: "Nền tảng", lay: function (r) { return ({ tiktok: "TikTok", facebook: "Facebook", youtube: "YouTube", instagram: "Instagram" })[r.nen_tang] || r.nen_tang; } },
      { ten: "Tác giả", lay: function (r) { return r.tac_gia; } },
      { ten: "Ngày đăng", lay: function (r) { return ngayDu(r.dang_luc); } },
      { ten: "Sắc thái", lay: function (r) { return r.sac_thai; } },
      { ten: "Thảo luận", so: true, lay: function (r) { return so(r.thao_luan); } },
      { ten: "Xem", so: true, lay: function (r) { return so(r.xem); } },
      { ten: "Thích", so: true, lay: function (r) { return so(r.thich); } },
      { ten: "Chia sẻ", so: true, lay: function (r) { return so(r.chia_se); } },
      { ten: "Bình luận đã đọc", lay: function (r) {
        if (!r.bl_da_lay) return "—";
        var b = tao("button", "nut nut--nhe nut--nho", so(r.bl_da_lay));
        b.type = "button";
        b.addEventListener("click", function () { moMotBai(r); });
        return b; } }
    ], d.top_bai));
  }

  function veTatCa() {
    if (!duLieu) return;
    var m = mau();
    veKpi(duLieu);
    veXuHuong(duLieu, m);
    veSacThai(duLieu, m);
    vePhanBo(duLieu, m);
    veTopNguon(duLieu);
    veTuKhoa(duLieu);
    veTopBai(duLieu);
    veBinhLuan(duLieu, m);
    $("ky-truoc").textContent = "So với " + ngayDu(duLieu.khoang.ky_truoc.tu) + " – " + ngayDu(duLieu.khoang.ky_truoc.den) + " (kỳ liền trước cùng độ dài).";
    $("canh-bao").hidden = !duLieu.bi_cat;
  }

  // ─── bình luận đã đọc (đợt 2b) ───
  function veBinhLuan(d, m) {
    var b = d.binh_luan_da_cao, el = $("kpi-bl");
    if (!b || !el) return;
    var k = b.kpi;
    xoa(el);
    el.appendChild(theKpi("Bình luận đã đọc", so(k.so), null, "trên " + so(k.so_bai) + " bài"));
    el.appendChild(theKpi("Của khách", so(k.khach), null, k.thuong_hieu ? "+ " + so(k.thuong_hieu) + " của thương hiệu" : "bình luận"));
    el.appendChild(theKpi("Tích cực", pt(k.tich_cuc_pt), null, so(k.tich_cuc) + " bình luận"));
    el.appendChild(theKpi("Tiêu cực", pt(k.tieu_cuc_pt), null, so(k.tieu_cuc) + " bình luận"));
    el.appendChild(theKpi("Trung lập", pt(k.trung_lap_pt), null, so(k.trung_lap) + " bình luận"));
    el.appendChild(theKpi("Chưa phân loại", so(k.chua_phan_loai), null, "bình luận"));
    $("trong-bl").hidden = k.so > 0;
    var x = b.xu_huong, nhan = x.moc.map(x.don_vi === "tuần" ? function (s) { return "từ " + ngayNgan(s); } : ngayNgan);
    $("don-vi-bl").textContent = "theo " + x.don_vi + " đăng bình luận (giờ VN)";
    var o = coBan(m);
    o.xAxis = trucDanhMuc(m, nhan);
    o.yAxis = trucSo(m);
    var lop = [["Tích cực", "tich_cuc"], ["Trung lập", "trung_lap"], ["Tiêu cực", "tieu_cuc"], ["chưa phân loại", "chua_phan_loai"]];
    o.series = lop.map(function (l, i) {
      return { name: l[0], type: "bar", stack: "bl", data: x[l[1]], barMaxWidth: 18,
               itemStyle: { color: m.sac[l[0]], borderColor: m.mat, borderWidth: 1,
                            borderRadius: i === lop.length - 1 ? [4, 4, 0, 0] : 0 } };
    });
    ve("bd-bl-ngay", o);
    xuLyBam["bd-bl-ngay"] = function (p) {
      var kh = khoangMoc(x, p.dataIndex);
      moChiTiet("binh-luan", Object.assign(kh, { sac_thai: p.seriesName }),
                p.seriesName + " · " + moTaKhoang(kh));
    };
    var cd = b.chu_de.slice(0, 12);
    var o2 = coBan(m);
    o2.grid.top = 32;
    o2.yAxis = Object.assign(trucDanhMuc(m, cd.map(function (c) { return c.chu_de; }).reverse()),
                             { axisLabel: { color: m.phu, fontSize: 12, width: 150, overflow: "truncate" } });
    o2.xAxis = trucSo(m);
    var lop2 = ["Tích cực", "Trung lập", "Tiêu cực", "chưa phân loại"];
    o2.series = lop2.map(function (s, i) {
      return { name: s, type: "bar", stack: "cd", barMaxWidth: 18,
               data: cd.map(function (c) { return c[s]; }).reverse(),
               itemStyle: { color: m.sac[s], borderColor: m.mat, borderWidth: 1,
                            borderRadius: i === lop2.length - 1 ? [0, 4, 4, 0] : 0 } };
    });
    $("bd-bl-chu-de").style.height = Math.max(220, 60 + 30 * cd.length) + "px";
    if (bieuDo["bd-bl-chu-de"]) bieuDo["bd-bl-chu-de"].resize();
    ve("bd-bl-chu-de", o2);
    xuLyBam["bd-bl-chu-de"] = function (p) {
      var c = cd[cd.length - 1 - p.dataIndex];
      if (!c) return;
      moChiTiet("binh-luan", { chu_de: c.chu_de, sac_thai: p.seriesName }, c.chu_de + " · " + p.seriesName);
    };
  }

  // ─── khung chi tiết ───
  function ngayISO(d) { return d.toISOString().slice(0, 10); }
  function congNgay(iso, n) {
    var d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return ngayISO(d);
  }
  // Mốc i của xu hướng -> {ngay_tu, ngay_den}: theo tuần thì tới trước mốc kế (mốc cuối: tới `den`).
  function khoangMoc(x, i) {
    var tu = x.moc[i];
    if (x.don_vi !== "tuần") return { ngay_tu: tu, ngay_den: tu };
    var den = i + 1 < x.moc.length ? congNgay(x.moc[i + 1], -1) : cfg.den;
    return { ngay_tu: tu, ngay_den: den };
  }
  function moTaKhoang(kh) {
    return kh.ngay_tu === kh.ngay_den ? "ngày " + ngayDu(kh.ngay_tu) : ngayDu(kh.ngay_tu) + " – " + ngayDu(kh.ngay_den);
  }
  function ngayGio(iso) {
    if (!iso) return "";
    var s = String(iso);
    return ngayDu(s) + (s.length >= 16 ? " " + s.slice(11, 16) : "");
  }
  var TEN_NT = { tiktok: "TikTok", facebook: "Facebook", youtube: "YouTube", instagram: "Instagram" };

  function nhanThe(chu, lop) { return tao("span", "the" + (lop ? " " + lop : ""), chu); }
  function lopSac(s) {
    return s === "Tích cực" ? "the--tot" : s === "Tiêu cực" ? "the--loi" : "";
  }

  function theBinhLuan(c) {
    var o = tao("div", "the-bl" + (c.la_tra_loi ? " the-bl--tra-loi" : ""));
    var dau = tao("div", "the-bl__dau");
    dau.appendChild(tao("b", "", c.tac_gia || "(ẩn danh)"));
    if (c.dang_luc) dau.appendChild(tao("span", "mo nho", " · " + ngayGio(c.dang_luc)));
    if (c.thich) dau.appendChild(tao("span", "mo nho", " · ♥ " + so(c.thich)));
    if (c.la_tra_loi) dau.appendChild(tao("span", "mo nho", " · trả lời"));
    o.appendChild(dau);
    o.appendChild(tao("p", "the-bl__chu", c.noi_dung || ""));
    var nh = tao("div", "the-bl__nhan");
    nh.appendChild(nhanThe(c.sac_thai, lopSac(c.sac_thai)));
    if (c.chu_de) nh.appendChild(nhanThe(c.chu_de, "the--nhan"));
    o.appendChild(nh);
    return o;
  }

  function theBai(r) {
    var o = tao("article", "the-bai");
    var dau = tao("div", "the-bai__dau");
    dau.appendChild(tao("b", "", r.tac_gia || "?"));
    dau.appendChild(tao("span", "mo nho", " · " + (TEN_NT[r.nen_tang] || r.nen_tang) + " · " + ngayGio(r.dang_luc) + " · " + r.loai));
    o.appendChild(dau);
    o.appendChild(tao("p", "the-bai__chu", r.noi_dung || "(không có chữ)"));
    var nh = tao("div", "the-bl__nhan");
    nh.appendChild(nhanThe(r.sac_thai, lopSac(r.sac_thai)));
    if (r.chu_de) nh.appendChild(nhanThe(r.chu_de, "the--nhan"));
    o.appendChild(nh);
    o.appendChild(tao("div", "mo nho", "Thảo luận " + so(r.thao_luan) + " · bình luận nền tảng báo " + so(r.binh_luan) +
                      " · xem " + so(r.xem) + " · thích " + so(r.thich) + " · chia sẻ " + so(r.chia_se)));
    var hd = tao("div", "the-bai__hanh-dong");
    hd.appendChild(linkAnToan(r.link, "Mở bài gốc ↗"));
    var ds = tao("div", "the-bai__bl");
    if (r.bl_da_lay) {
      var nut = tao("button", "nut nut--nhe nut--nho", "Xem " + so(r.bl_da_lay) + " bình luận đã đọc");
      nut.type = "button";
      nut.addEventListener("click", function () {
        if (ds.childNodes.length) { xoa(ds); nut.textContent = "Xem " + so(r.bl_da_lay) + " bình luận đã đọc"; return; }
        nut.disabled = true;
        goiApi("binh-luan", { khoa: r.khoa }).then(function (j) {
          j.binh_luan.forEach(function (c) { ds.appendChild(theBinhLuan(c)); });
          if (!j.binh_luan.length) ds.appendChild(tao("div", "trong", "Chưa có bình luận đã đọc."));
          nut.textContent = "Ẩn bình luận";
        }).catch(function (e) { ds.appendChild(tao("div", "thong-bao thong-bao--loi", e.message)); })
          .then(function () { nut.disabled = false; });
      });
      hd.appendChild(nut);
    } else if (r.binh_luan) {
      hd.appendChild(tao("span", "mo nho", "Bình luận chưa được cào"));
    }
    o.appendChild(hd);
    o.appendChild(ds);
    return o;
  }

  function goiApi(duong, dk) {
    var q = new URLSearchParams({ du_an: cfg.du_an, tu: cfg.tu, den: cfg.den });
    if (cfg.nen_tang) q.set("nen_tang", cfg.nen_tang);
    if (cfg.loai) q.set("loai", cfg.loai);
    Object.keys(dk).forEach(function (k) { if (dk[k] != null && dk[k] !== "") q.set(k, dk[k]); });
    return fetch("/api/" + duong + "?" + q.toString(), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        if (r.status === 401) throw new Error("Phiên đăng nhập đã hết hạn — tải lại trang để đăng nhập lại.");
        return r.json().then(function (j) {
          if (!r.ok) throw new Error(j && j.loi ? j.loi : "Không tải được chi tiết.");
          return j;
        });
      });
  }

  var hop = $("chi-tiet");
  if (hop) {
    $("chi-tiet-dong").addEventListener("click", function () { hop.close ? hop.close() : hop.removeAttribute("open"); });
    hop.addEventListener("click", function (e) { if (e.target === hop && hop.close) hop.close(); });
  }

  // loai: "bai" | "binh-luan"; dk: điều kiện của cột vừa bấm; moTa: chữ cho tiêu đề.
  function moChiTiet(loai, dk, moTa, trang) {
    if (!hop) return;
    var than = $("chi-tiet-than"), ph = $("chi-tiet-trang");
    $("chi-tiet-tieu-de").textContent = (loai === "bai" ? "Bài" : "Bình luận") + " — " + moTa;
    $("chi-tiet-mo-ta").textContent = "Đang tải…";
    xoa(than);
    xoa(ph);
    if (!hop.open) { if (hop.showModal) hop.showModal(); else hop.setAttribute("open", ""); }
    goiApi(loai, Object.assign({ trang: trang || 1 }, dk)).then(function (j) {
      var ds = loai === "bai" ? j.bai : j.binh_luan;
      $("chi-tiet-mo-ta").textContent = loai === "bai"
        ? so(j.tong) + " bài · " + so(j.thao_luan) + " thảo luận (bài + bình luận nền tảng báo) · xếp theo thảo luận"
        : so(j.tong) + " bình luận đã đọc · xếp theo lượt thích";
      if (!ds.length) than.appendChild(tao("div", "trong", "Không có " + (loai === "bai" ? "bài" : "bình luận") + " nào."));
      ds.forEach(function (x) { than.appendChild(loai === "bai" ? theBai(x) : theBinhLuan(x)); });
      if (j.so_trang > 1) {
        if (j.trang > 1) {
          var t = tao("button", "nut nut--nhe nut--nho", "← Trước");
          t.type = "button";
          t.addEventListener("click", function () { moChiTiet(loai, dk, moTa, j.trang - 1); });
          ph.appendChild(t);
        }
        ph.appendChild(tao("span", "mo nho", "Trang " + j.trang + "/" + j.so_trang));
        if (j.trang < j.so_trang) {
          var s = tao("button", "nut nut--nhe nut--nho", "Sau →");
          s.type = "button";
          s.addEventListener("click", function () { moChiTiet(loai, dk, moTa, j.trang + 1); });
          ph.appendChild(s);
        }
      }
      than.scrollTop = 0;
    }).catch(function (e) { $("chi-tiet-mo-ta").textContent = e.message || "Không tải được chi tiết."; });
  }

  // Một bài (bảng Bài nổi bật): mở khung với đúng bài đó, tự mở bình luận đã đọc.
  function moMotBai(r) {
    if (!hop) return;
    var than = $("chi-tiet-than");
    $("chi-tiet-tieu-de").textContent = "Bài — " + (r.tac_gia || "?") + " · " + ngayDu(r.dang_luc);
    $("chi-tiet-mo-ta").textContent = so(r.bl_da_lay) + " bình luận đã đọc của bài này.";
    xoa(than);
    xoa($("chi-tiet-trang"));
    var the = theBai(r);
    than.appendChild(the);
    if (!hop.open) { if (hop.showModal) hop.showModal(); else hop.setAttribute("open", ""); }
    var nut = the.querySelector(".the-bai__hanh-dong button");
    if (nut) nut.click();
  }

  function baoLoi(chu) {
    var el = $("loi-tai");
    el.textContent = chu;
    el.hidden = !chu;
  }

  // ─── tải dữ liệu ───
  // Máy chủ chỉ tính 2 lượt cùng lúc (503 khi bận): thử lại sau 5 giây, tối đa 3 lần.
  var lanThuLai = 0;
  function tai() {
    var q = new URLSearchParams({ du_an: cfg.du_an, tu: cfg.tu, den: cfg.den });
    if (cfg.nen_tang) q.set("nen_tang", cfg.nen_tang);
    if (cfg.loai) q.set("loai", cfg.loai);
    return fetch("/api/chi-so?" + q.toString(), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        if (r.status === 401) throw new Error("Phiên đăng nhập đã hết hạn — tải lại trang để đăng nhập lại.");
        if (r.status === 503 && lanThuLai < 3) {
          lanThuLai += 1;
          setTimeout(tai, 5000);
        } else if (r.ok) {
          lanThuLai = 0;
        }
        return r.json().then(function (j) {
          if (!r.ok) throw new Error(j && j.loi ? j.loi : "Không tải được số liệu.");
          return j;
        });
      })
      .then(function (j) {
        duLieu = j;
        baoLoi("");
        veTatCa();
        var t = "Cập nhật lúc " + gioVN(new Date());
        if (j.luot_gan_nhat) t += " · lượt quét gần nhất bắt đầu " + j.luot_gan_nhat.bat_dau;
        $("cap-nhat-luc").textContent = t;
      })
      .catch(function (e) { baoLoi(e.message || "Không tải được số liệu."); });
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
  window.addEventListener("resize", function () {
    Object.keys(bieuDo).forEach(function (k) { bieuDo[k].resize(); });
  });

  tai();
})();
