/* ============================================================
   الملف: app/static/app.js — منطق الصفحة (الواجهة الأمامية)
   ما يفعله: يبني بطاقات عروض الأسعار ويستورد ملف CSV ويرسل البيانات إلى /api/compare ويعرض النتائج وحزمة الشراء.
   متى تعدّله: لتغيير سلوك الأزرار أو شكل عرض النتائج.
   ============================================================ */
(function () {
  "use strict";

  // ===== متغيرات عامة ودوال مساعدة صغيرة =====
  var discounts = [];
  var $ = function (id) { return document.getElementById(id); };

  // دالة بناء عناصر الصفحة بأمان (النص عبر textContent وليس innerHTML)
  // Safe DOM builder: text goes through textContent, never innerHTML.
  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "class") el.className = attrs[k];
        else if (k === "text") el.textContent = attrs[k];
        else el.setAttribute(k, attrs[k]);
      });
    }
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null) continue;
      el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return el;
  }
  // تنسيق الرقم كمبلغ بالدولار
  function money(n) { return "$" + Number(n).toFixed(2); }
  // قراءة رقم من حقل (أو null إن كان الحقل فارغاً)
  function numOrNull(id) {
    var v = $(id).value.trim();
    return v === "" ? null : Number(v);
  }

  // ===== تحميل قائمة الخصومات من الخادم عند فتح الصفحة =====
  // ---------- levers catalog ----------
  fetch("/api/levers").then(function (r) { return r.json(); }).then(function (d) {
    discounts = d.levers.filter(function (l) { return l.group === "discount"; });
    $("disclaimer").textContent = d.disclaimer;
    addQuote();
  }).catch(function () {
    $("disclaimer").textContent = "Could not load the lever catalog. Reload the page.";
    addQuote();
  });

  // ===== بطاقات عروض الأسعار: إضافة وحذف وتعبئة الحقول =====
  // ---------- quote cards ----------
  // إنشاء حقل إدخال مع عنوانه
  function field(label, cls, ph, type) {
    var input = h("input", { "class": cls, placeholder: ph || "", type: type || "text" });
    if (type === "number") input.setAttribute("min", "0");
    return h("label", {}, label, input);
  }

  // إنشاء بطاقة عرض سعر جديدة (فارغة أو معبّأة من ملف CSV)
  function addQuote(data) {
    data = data || {};
    var card = h("div", { "class": "quote" });
    var title = h("span", { text: "Quote" });
    var remove = h("button", { type: "button", "class": "link", text: "Remove" });
    remove.addEventListener("click", function () { card.remove(); });
    card.appendChild(h("div", { "class": "head" }, title, remove));

    var grid = h("div", { "class": "grid" },
      field("Insurance company", "q-company", "Company name"),
      field("Monthly premium ($)", "q-premium", "180", "number"),
      field("Monthly fees ($, optional)", "q-fees", "0", "number"),
      field("Bodily injury limit", "q-bi", "100/300"),
      field("Property damage limit", "q-pd", "100"),
      field("Comp deductible", "q-comp", "500"),
      field("Collision deductible", "q-coll", "500"),
      field("Vehicles on quote", "q-veh", "", "number"),
      field("Drivers on quote", "q-drv", "", "number")
    );
    card.appendChild(grid);

    var chips = h("div", { "class": "chips" });
    discounts.forEach(function (d) {
      var cb = h("input", { type: "checkbox", value: d.id, "class": "q-disc" });
      chips.appendChild(h("label", {}, cb, d.name));
    });
    card.appendChild(h("details", {},
      h("summary", { text: "Discounts already included in this quote" }), chips));

    var set = function (cls, val) {
      if (val === undefined || val === null || val === "") return;
      card.querySelector("." + cls).value = val;
    };
    set("q-company", data.company); set("q-premium", data.monthly_premium); set("q-fees", data.fees_monthly || "");
    set("q-bi", data.bodily_injury_limit); set("q-pd", data.property_damage_limit);
    set("q-comp", data.comp_deductible); set("q-coll", data.collision_deductible);
    set("q-veh", data.vehicles); set("q-drv", data.drivers);
    (data.applied_discounts || []).forEach(function (id) {
      var cb = card.querySelector('.q-disc[value="' + id + '"]');
      if (cb) cb.checked = true;
    });
    card.dataset.source = data.source || "";
    card.dataset.quoteDate = data.quote_date || "";
    card.dataset.notes = data.notes || "";
    $("quotes").appendChild(card);
  }
  $("add-quote").addEventListener("click", function () { addQuote(); });

  // ===== استيراد ملف CSV =====
  // ---------- CSV import ----------
  $("csv-file").addEventListener("change", function (e) {
    var file = e.target.files[0];
    if (!file) return;
    var fd = new FormData();
    fd.append("file", file);
    $("csv-msg").textContent = "Importing...";
    fetch("/api/import-csv", { method: "POST", body: fd })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) { $("csv-msg").textContent = "Import failed: " + (res.body.detail || "unknown error"); return; }
        // Replace empty starter cards, then add imported ones.
        Array.prototype.slice.call(document.querySelectorAll("#quotes .quote")).forEach(function (c) {
          if (!c.querySelector(".q-company").value && !c.querySelector(".q-premium").value) c.remove();
        });
        res.body.quotes.forEach(addQuote);
        var msg = "Imported " + res.body.quotes.length + " quote(s).";
        if (res.body.errors.length) {
          msg += " Skipped " + res.body.errors.length + ": " + res.body.errors.map(function (x) {
            return "row " + x.row + " (" + x.error + ")";
          }).join("; ");
        }
        $("csv-msg").textContent = msg;
      })
      .catch(function () { $("csv-msg").textContent = "Import failed. Check the file and try again."; })
      .finally(function () { e.target.value = ""; });
  });

  // ===== جمع المدخلات وإرسالها للتحليل =====
  // ---------- collect + analyze ----------
  // قراءة كل القيم من الصفحة وتجميعها في طلب واحد
  function collect() {
    var vehicleCount = document.querySelectorAll("#vehicles .vehicle").length || 1;
    var driverCount = document.querySelectorAll("#drivers .person").length || 1;
    var profile = {
      state: $("p_state").value.trim(),
      vehicles: vehicleCount,
      drivers: driverCount,
      annual_miles: null,
      oldest_vehicle_value: null,
      days_before_renewal: numOrNull("p_days")
    };
    document.querySelectorAll("#profile-checks input[data-bool]").forEach(function (cb) {
      profile[cb.dataset.bool] = cb.checked;
    });

    var quotes = [];
    document.querySelectorAll("#quotes .quote").forEach(function (card) {
      var company = card.querySelector(".q-company").value.trim();
      var premium = card.querySelector(".q-premium").value.trim();
      if (!company && !premium) return; // ignore empty cards
      var q = {
        company: company,
        monthly_premium: Number(premium),
        fees_monthly: Number(card.querySelector(".q-fees").value) || 0,
        bodily_injury_limit: card.querySelector(".q-bi").value.trim(),
        property_damage_limit: card.querySelector(".q-pd").value.trim(),
        comp_deductible: card.querySelector(".q-comp").value.trim(),
        collision_deductible: card.querySelector(".q-coll").value.trim(),
        applied_discounts: Array.prototype.map.call(card.querySelectorAll(".q-disc:checked"), function (c) { return c.value; }),
        source: card.dataset.source || "",
        quote_date: card.dataset.quoteDate || "",
        notes: card.dataset.notes || ""
      };
      var veh = card.querySelector(".q-veh").value.trim();
      var drv = card.querySelector(".q-drv").value.trim();
      if (veh) q.vehicles = Number(veh);
      if (drv) q.drivers = Number(drv);
      quotes.push(q);
    });

    return {
      profile: profile,
      quotes: quotes,
      target_monthly: Number($("target").value) || 200,
      acceptable_overage_monthly: 50,
      desired_coverage: {
        bodily_injury_limit: $("c_bi").value.trim(),
        property_damage_limit: $("c_pd").value.trim(),
        comp_deductible: $("c_comp").value.trim(),
        collision_deductible: $("c_coll").value.trim()
      }
    };
  }

  // عرض رسالة خطأ للمستخدم
  function showError(msg) {
    var box = $("error");
    box.textContent = msg;
    box.hidden = !msg;
  }

  // زر "ابحث عن أرخص سعر": يتحقق من المدخلات ثم يرسلها إلى الخادم
  $("analyze").addEventListener("click", function () {
    showError("");
    var payload = collect();
    if (!payload.quotes.length) { showError("Add at least one quote with a company and monthly premium."); return; }
    for (var i = 0; i < payload.quotes.length; i++) {
      var q = payload.quotes[i];
      if (!q.company || !(q.monthly_premium > 0)) { showError("Each quote needs a company name and a monthly premium above 0."); return; }
    }
    $("analyze").disabled = true;
    $("analyze").textContent = "Digging...";
    fetch("/api/compare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) {
          var detail = Array.isArray(res.body.detail)
            ? res.body.detail.map(function (d) { return d.loc.slice(1).join(".") + ": " + d.msg; }).join("; ")
            : (res.body.detail || "Something went wrong.");
          showError("Check your inputs: " + detail);
          return;
        }
        render(res.body);
      })
      .catch(function () { showError("Could not reach the server. Try again in a moment (free hosting may be waking up)."); })
      .finally(function () {
        $("analyze").disabled = false;
        $("analyze").textContent = "Find my cheapest legal price";
      });
  });

  // ===== عرض النتائج على الصفحة =====
  // ---------- rendering ----------
  // قائمة الخصومات داخل البطاقة
  function leverList(items, withTip) {
    var ul = h("ul");
    items.forEach(function (l) {
      var li = h("li", {}, h("strong", { text: l.name }));
      var small = h("small", { text: "Ask for: " + l.ask + (withTip && l.tip ? ". " + l.tip : "") });
      li.appendChild(small);
      ul.appendChild(li);
    });
    return ul;
  }

  // بطاقة النتيجة لكل عرض سعر (السعر وشريط الهدف والتقديرات والتحذيرات)
  function resultCard(r, target) {
    var met = r.effective_monthly <= target;
    var card = h("div", { "class": "result" });
    card.appendChild(h("div", { "class": "top" },
      h("span", { "class": "name", text: "#" + r.rank + " " + r.company }),
      h("span", { "class": "price", text: money(r.effective_monthly) + "/mo" })
    ));
    card.appendChild(h("div", {},
      h("span", { "class": "badge " + (r.comparable ? "ok" : "no"), text: r.comparable ? "Comparable coverage" : "Not comparable" }),
      h("span", { "class": "badge " + (met ? "ok" : (r.meets_fallback_range ? "ok" : "no")), text: met ? "Meets target now" : (r.meets_fallback_range ? "Within fallback limit" : "Above fallback limit") }),
      h("span", { "class": "hint", text: money(r.annual_cost) + "/yr" + (r.fees_monthly ? " (includes " + money(r.fees_monthly) + " fees/mo)" : "") })
    ));
    var bar = h("div", { "class": "bar" + (met ? " met" : "") }, h("span", {}));
    bar.firstChild.style.width = Math.round(r.target_progress * 100) + "%";
    card.appendChild(bar);

    var p = r.projected;
    card.appendChild(h("div", { "class": "proj" },
      h("div", {}, "Conservative levers", h("b", { text: money(p.conservative) })),
      h("div", {}, "Expected levers", h("b", { text: money(p.expected) })),
      h("div", {}, "With coverage tradeoffs", h("b", { text: money(p.with_tradeoffs) }))
    ));

    if (r.warnings.length) {
      var wl = h("ul", { "class": "warnings" });
      r.warnings.forEach(function (w) { wl.appendChild(h("li", { text: w })); });
      card.appendChild(wl);
    }
    if (r.untapped.length) {
      card.appendChild(h("details", { open: "open" },
        h("summary", { text: "Untapped discounts you qualify for (" + r.untapped.length + ")" }), leverList(r.untapped, true)));
    }
    if (r.applied.length) {
      card.appendChild(h("details", {},
        h("summary", { text: "Already applied (" + r.applied.length + ")" }), leverList(r.applied, false)));
    }
    if (r.tradeoffs.length) {
      card.appendChild(h("details", {},
        h("summary", { text: "Coverage tradeoffs to consider carefully (" + r.tradeoffs.length + ")" }), leverList(r.tradeoffs, true)));
    }
    if (r.programs.length) {
      card.appendChild(h("details", {},
        h("summary", { text: "State programs to check eligibility for" }), leverList(r.programs, true)));
    }
    return card;
  }

  // عرض الحكم النهائي والعروض المرتّبة وحزمة الشراء
  function render(data) {
    var box = $("results");
    box.replaceChildren();
    var cls = { under_target_now: "good", within_fallback_range: "warn", reachable: "good", possible: "warn", possible_with_tradeoffs: "warn", gap: "bad", no_comparable_quote: "bad" }[data.verdict.status] || "warn";
    box.appendChild(h("div", { "class": "verdict " + cls },
      h("h2", { text: data.verdict.headline }),
      h("p", { text: data.verdict.detail })
    ));
    box.appendChild(h("h2", { text: "Ranked quotes" }));
    data.results.forEach(function (r) { box.appendChild(resultCard(r, data.target)); });

    var pk = data.packet;
    var pre = h("pre", { "class": "packet", text: pk.text });
    var copy = h("button", { type: "button", text: "Copy packet" });
    copy.addEventListener("click", function () {
      var done = function () { copy.textContent = "Copied"; setTimeout(function () { copy.textContent = "Copy packet"; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(pk.text).then(done, function () {});
    });
    box.appendChild(h("div", { "class": "card" },
      h("h2", { text: "Buy-ready packet" }),
      h("p", { "class": "hint", text: "Take this to the insurer to get the official quote. The estimate is not the final price." }),
      pre, copy));
    box.appendChild(h("p", { "class": "hint", text: data.disclaimer }));
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  }
})();
