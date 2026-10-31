/* ============================================================
   الملف: app/static/planner.js — مخطِّط عروض الأسعار
   ما يفعله: يبني قائمة بكل الطرق الصادقة لخفض السعر (الخصومات والتغطية والدفع والتوقيت)، ثم يعرض شبكة (شركة × سيناريو) تُدخل فيها الأسعار الحقيقية من شركات التأمين، ويحدد الأرخص وما الذي خفّض السعر أكثر.
   متى تعدّله: لإضافة سيناريو جديد (أضِف عنصراً داخل buildScenarios) أو لتغيير شركات التأمين المقترحة.
   ملاحظة: كل البيانات تبقى في المتصفح. الأسعار يجب أن تأتي من شركة التأمين نفسها.
   ============================================================ */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var BASE = "base";

  // شركات مقترحة للإضافة بنقرة واحدة (قابلة للتعديل)
  var SUGGESTED = ["GEICO", "Progressive", "State Farm", "Allstate", "Liberty Mutual", "Farmers", "Nationwide", "Travelers", "USAA", "Erie"];

  var insurers = [];   // أسماء الشركات المضافة
  var scenarios = [];  // السيناريوهات الحالية
  var prices = {};     // المفتاح: شركة|سيناريو => السعر الشهري

  // دالة صغيرة لبناء عناصر الصفحة بأمان (النص عبر textContent)
  function el(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "class") node.className = attrs[k];
      else if (k === "text") node.textContent = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null) continue;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return node;
  }
  function money(n) { return "$" + Number(n).toFixed(2); }
  function key(ins, sc) { return ins + "|" + sc; }
  function checked(name) { var c = document.querySelector('#profile-checks [data-bool="' + name + '"]'); return !!(c && c.checked); }
  function val(id) { var n = $(id); return n ? n.value.trim() : ""; }

  // ===== بناء السيناريوهات من ملف العميل (كلها صادقة: لا تغيّر حقائق عن العميل) =====
  // Each scenario changes only choices the client controls: coverage options, payment, timing, programs.
  // coverage:true means the scenario lowers protection, so it is tagged with a risk level.
  function buildScenarios() {
    var cov = {
      bi: val("c_bi") || "100/300", pd: val("c_pd") || "100",
      comp: val("c_comp") || "500", coll: val("c_coll") || "500"
    };
    var days = Number(val("p_days")) || 0;
    var oldValue = null;
    document.querySelectorAll("#vehicles .v-value").forEach(function (i) {
      var n = Number(i.value);
      if (n > 0 && (oldValue === null || n < oldValue)) oldValue = n;
    });
    var list = [];
    function add(s) { s.fields = s.fields || {}; list.push(s); }
    function f(over) {
      return Object.assign({ bodily_injury_limit: cov.bi, property_damage_limit: cov.pd, comp_deductible: cov.comp, collision_deductible: cov.coll }, over || {});
    }

    add({ id: BASE, label: "Your coverage as entered", ask: "Quote the coverage you chose, paid monthly.", risk: "none", coverage: false, discounts: ["autopay", "paperless"], fields: f() });
    if (checked("willing_pay_in_full")) add({ id: "paid_full", label: "Pay in full", ask: "Same coverage, paid in full up front (6 or 12 months).", risk: "none", coverage: false, discounts: ["pay_in_full"], fields: f() });
    if (checked("willing_telematics")) add({ id: "telematics", label: "Telematics program", ask: "Same coverage with the usage-based / telematics program. Read the terms: some can raise rates.", risk: "low", coverage: false, discounts: ["telematics"], fields: f() });
    if (checked("homeowner") || checked("has_bundle_policy")) add({ id: "bundle", label: "Bundle with home or renters", ask: "Same coverage bundled with the home or renters policy.", risk: "none", coverage: false, discounts: ["bundle"], fields: f() });
    if (days >= 7) add({ id: "early", label: "Start date 1 to 4 weeks out", ask: "Same coverage with the start date moved out, for the early shopper discount.", risk: "none", coverage: false, discounts: ["early_shopper"], fields: f() });
    if (checked("employer_or_group") || checked("military") || checked("good_student")) add({ id: "affinity", label: "Group, military or student discounts", ask: "Same coverage with the group, military or good student discounts applied. Have proof ready.", risk: "none", coverage: false, discounts: ["group", "military", "good_student"].filter(function (id) { return (id === "group" && checked("employer_or_group")) || (id === "military" && checked("military")) || (id === "good_student" && checked("good_student")); }), fields: f() });

    add({ id: "ded1000", label: "$1,000 deductibles", ask: "Same liability limits with comprehensive and collision deductibles at $1,000. Only if the client can pay that after a claim.", risk: "low", coverage: true, discounts: ["autopay", "paperless"], fields: f({ comp_deductible: "1000", collision_deductible: "1000" }) });
    add({ id: "ded_mixed", label: "$1,000 collision, $500 comprehensive", ask: "Collision at $1,000, comprehensive at $500. Collision is usually where the saving is.", risk: "low", coverage: true, discounts: ["autopay", "paperless"], fields: f({ comp_deductible: "500", collision_deductible: "1000" }) });
    add({ id: "no_extras", label: "Remove rental and roadside", ask: "Same coverage without rental reimbursement and roadside assistance, if the client does not need them.", risk: "low", coverage: true, discounts: ["autopay", "paperless"], fields: f() });
    if (oldValue !== null && oldValue <= 3000) add({ id: "drop_coll", label: "Drop collision on the oldest car", ask: "Quote without collision on the older, low-value vehicle. Often not worth it if a year of collision costs near the car's value.", risk: "medium", coverage: true, discounts: ["autopay", "paperless"], fields: f({ collision_deductible: "none" }) });
    add({ id: "min_limits", label: "State minimum liability", ask: "Quote state-minimum liability limits. This is much less protection: it can leave the client paying out of pocket after a serious accident.", risk: "high", coverage: true, discounts: ["autopay", "paperless"], fields: f({ bodily_injury_limit: "state minimum", property_damage_limit: "state minimum" }) });

    // أفضل مزيج بدون خفض التغطية: كل الخصومات المتاحة معاً
    var combo = [];
    list.forEach(function (s) { if (!s.coverage) s.discounts.forEach(function (d) { if (combo.indexOf(d) < 0) combo.push(d); }); });
    if (combo.length > 2) add({ id: "combo", label: "All discounts together, same coverage", ask: "Same coverage with every discount that applies to this client at once.", risk: "low", coverage: false, discounts: combo, fields: f() });
    add({ id: "combo_ded", label: "All discounts and $1,000 deductibles", ask: "Every applicable discount with $1,000 comprehensive and collision deductibles.", risk: "low", coverage: true, discounts: combo.length ? combo : ["autopay", "paperless"], fields: f({ comp_deductible: "1000", collision_deductible: "1000" }) });
    return list;
  }

  function scenarioById(id) { return scenarios.filter(function (s) { return s.id === id; })[0]; }
  var RISK = { none: "No change to protection", low: "Low risk", medium: "Medium risk", high: "High risk" };

  // ===== عرض قائمة السيناريوهات (ما يُطلب من كل شركة) =====
  function renderScenarios() {
    var box = $("plan-scenarios");
    box.replaceChildren();
    box.appendChild(el("h3", { text: "Ask every insurer for these " + scenarios.length + " versions" }));
    var ol = el("ol", { "class": "plan-list" });
    scenarios.forEach(function (s) {
      ol.appendChild(el("li", {}, el("strong", { text: s.label }), " ", el("span", { "class": "risk " + s.risk, text: RISK[s.risk] }), el("small", { text: s.ask })));
    });
    box.appendChild(ol);
  }

  // ===== شركات التأمين: إضافة وحذف =====
  function addInsurer(name) {
    name = (name || "").trim();
    if (!name || insurers.indexOf(name) >= 0 || insurers.length >= 30) return;
    insurers.push(name);
    renderGrid();
  }
  function removeInsurer(name) {
    insurers = insurers.filter(function (n) { return n !== name; });
    Object.keys(prices).forEach(function (k) { if (k.indexOf(name + "|") === 0) delete prices[k]; });
    renderGrid();
  }

  // ===== الشبكة: صف لكل شركة وعمود لكل سيناريو =====
  function renderGrid() {
    var wrap = $("plan-grid");
    wrap.replaceChildren();
    if (!insurers.length || !scenarios.length) { return; }
    var head = el("tr", {}, el("th", { text: "Insurer" }));
    scenarios.forEach(function (s) { head.appendChild(el("th", { text: s.label, title: s.ask })); });
    var table = el("table", { "class": "plan-table" }, el("thead", {}, head));
    var body = el("tbody");
    insurers.forEach(function (ins) {
      var tr = el("tr");
      var rm = el("button", { type: "button", "class": "link", text: "Remove", "aria-label": "Remove " + ins });
      rm.addEventListener("click", function () { removeInsurer(ins); });
      tr.appendChild(el("th", { scope: "row" }, el("span", { text: ins }), rm));
      scenarios.forEach(function (s) {
        var input = el("input", { type: "number", min: "0", step: "0.01", inputmode: "decimal", placeholder: "$/mo", "aria-label": ins + ", " + s.label });
        if (prices[key(ins, s.id)]) input.value = prices[key(ins, s.id)];
        input.addEventListener("input", function () {
          if (input.value === "") delete prices[key(ins, s.id)]; else prices[key(ins, s.id)] = input.value;
        });
        tr.appendChild(el("td", {}, input));
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    wrap.appendChild(el("div", { "class": "plan-scroll" }, table));
    wrap.appendChild(el("p", { "class": "hint", text: "Enter the monthly price each insurer actually quoted. Leave a cell empty if you did not get that version." }));
  }

  // ===== تحليل الأسعار المُدخلة =====
  function readPrices() {
    var cells = [];
    insurers.forEach(function (ins) {
      scenarios.forEach(function (s) {
        var p = Number(prices[key(ins, s.id)]);
        if (p > 0) cells.push({ ins: ins, sc: s, price: p });
      });
    });
    return cells;
  }
  function baselineFor(ins) { var p = Number(prices[key(ins, BASE)]); return p > 0 ? p : null; }

  function cellCard(title, c, baseline, resultsBox) {
    var delta = baseline ? Math.round((1 - c.price / baseline) * 100) : null;
    var card = el("div", { "class": "result" },
      el("div", { "class": "top" }, el("span", { "class": "name", text: title }), el("span", { "class": "price", text: money(c.price) + "/mo" })),
      el("div", {}, el("span", { "class": "badge ok", text: c.ins }), el("span", { "class": "badge " + (c.sc.risk === "none" ? "ok" : "no"), text: c.sc.label }), delta !== null && delta > 0 ? el("span", { "class": "hint", text: delta + "% below that insurer's baseline quote" }) : null),
      el("p", { "class": "hint", text: c.sc.ask })
    );
    var btn = el("button", { type: "button", "class": "secondary", text: "Add to the quotes below" });
    btn.addEventListener("click", function () {
      if (typeof window.bqAddQuote !== "function") return;
      // احذف بطاقة العرض الفارغة الافتراضية قبل الإضافة
      Array.prototype.slice.call(document.querySelectorAll("#quotes .quote")).forEach(function (card) {
        var co = card.querySelector(".q-company"), pr = card.querySelector(".q-premium");
        if (co && pr && !co.value && !pr.value) card.remove();
      });
      window.bqAddQuote(Object.assign({ company: c.ins, monthly_premium: c.price, applied_discounts: c.sc.discounts.slice(), notes: c.sc.label }, c.sc.fields));
      btn.textContent = "Added";
      btn.disabled = true;
    });
    card.appendChild(btn);
    return card;
  }

  function findCheapest() {
    var out = $("plan-results");
    out.replaceChildren();
    var cells = readPrices();
    if (!cells.length) { out.appendChild(el("p", { "class": "error", role: "alert", text: "Enter at least one real quote in the grid first." })); return; }
    var byPrice = cells.slice().sort(function (a, b) { return a.price - b.price; });
    var overall = byPrice[0];
    var same = byPrice.filter(function (c) { return !c.sc.coverage; })[0];

    out.appendChild(el("h2", { text: "Cheapest results" }));
    if (same) out.appendChild(cellCard("Cheapest with your coverage unchanged", same, baselineFor(same.ins)));
    if (overall && (!same || overall !== same)) {
      var tag = overall.sc.coverage ? "Cheapest overall (coverage reduced)" : "Cheapest overall";
      var oc = cellCard(tag, overall, baselineFor(overall.ins));
      if (overall.sc.coverage && overall.sc.risk !== "low") oc.appendChild(el("p", { "class": "warn-note", text: "This version lowers protection (" + RISK[overall.sc.risk].toLowerCase() + "). Make sure the client understands and accepts that before choosing it." }));
      out.appendChild(oc);
    }

    // ما الذي خفّض السعر أكثر: متوسط التغيير مقابل السعر الأساسي لنفس الشركة
    var effects = scenarios.filter(function (s) { return s.id !== BASE; }).map(function (s) {
      var diffs = [];
      insurers.forEach(function (ins) {
        var b = baselineFor(ins), p = Number(prices[key(ins, s.id)]);
        if (b && p > 0) diffs.push((1 - p / b) * 100);
      });
      if (!diffs.length) return null;
      return { s: s, avg: diffs.reduce(function (a, b) { return a + b; }, 0) / diffs.length, n: diffs.length };
    }).filter(Boolean).sort(function (a, b) { return b.avg - a.avg; });
    if (effects.length) {
      out.appendChild(el("h3", { text: "What moved the price" }));
      var ul = el("ul");
      effects.forEach(function (e) {
        var txt = e.avg >= 0 ? e.avg.toFixed(0) + "% cheaper" : Math.abs(e.avg).toFixed(0) + "% more expensive";
        ul.appendChild(el("li", {}, el("strong", { text: e.s.label + ": " + txt }), el("small", { text: "Average across " + e.n + " insurer" + (e.n > 1 ? "s" : "") + ", compared with each insurer's own baseline quote." })));
      });
      out.appendChild(ul);
    } else {
      out.appendChild(el("p", { "class": "hint", text: "Add each insurer's baseline quote plus at least one other version to see which choices moved the price." }));
    }
  }

  // ===== ربط الأزرار =====
  function start() {
    scenarios = buildScenarios();
    $("plan-body").hidden = false;
    renderScenarios();
    renderGrid();
    $("plan-results").replaceChildren();
  }
  $("build-plan").addEventListener("click", start);
  $("plan-best").addEventListener("click", findCheapest);
  $("ins-add").addEventListener("click", function () { addInsurer($("ins-name").value); $("ins-name").value = ""; $("ins-name").focus(); });
  $("ins-name").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); $("ins-add").click(); } });
  var chips = $("ins-suggest");
  SUGGESTED.forEach(function (n) {
    var b = el("button", { type: "button", "class": "chip", text: "+ " + n });
    b.addEventListener("click", function () { if (!scenarios.length) start(); addInsurer(n); });
    chips.appendChild(b);
  });
})();
