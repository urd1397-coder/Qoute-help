/* ============================================================
   Quote planner + browser-only vehicle/driver cards.
   Personal identifiers and VINs remain in this browser; only counts
   are sent to the comparison API in this release.
   ============================================================ */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      if (key === "class") node.className = attrs[key];
      else node.setAttribute(key, attrs[key]);
    });
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function makeCard(container, className, title, fields) {
    var card = el("div", { "class": className + " mini" });
    var head = el("div", { "class": "head" });
    head.appendChild(el("strong", {}, title));
    var remove = el("button", { type: "button", "class": "link" }, "Remove");
    remove.addEventListener("click", function () {
      if (container.children.length > 1) card.remove();
      else fields.forEach(function (field) { field.input.value = ""; });
    });
    head.appendChild(remove);
    card.appendChild(head);
    var grid = el("div", { "class": "grid" });
    fields.forEach(function (item) {
      var label = el("label", {}, item.label);
      var input = el("input", { type: "text", placeholder: item.placeholder || "", autocomplete: "off" });
      if (item.key) input.dataset.field = item.key;
      input.autocomplete = "off";
      label.appendChild(input);
      grid.appendChild(label);
      item.input = input;
    });
    card.appendChild(grid);
    container.appendChild(card);
    return card;
  }

  function addVehicle() {
    makeCard($("vehicles"), "vehicle", "Vehicle " + ($("vehicles").children.length + 1), [
      { key: "vehicle_year", label: "Year", placeholder: "2022" },
      { key: "vehicle_make", label: "Make", placeholder: "Toyota" },
      { key: "vehicle_model", label: "Model", placeholder: "Camry" },
      { key: "vin", label: "VIN (optional)", placeholder: "17-character VIN" }
    ]);
  }
  function addDriver() {
    makeCard($("drivers"), "person", "Driver " + ($("drivers").children.length + 1), [
      { key: "driver_name", label: "Driver name", placeholder: "Full name" },
      { key: "date_of_birth", label: "Date of birth", placeholder: "MM/DD/YYYY" },
      { key: "license_state", label: "License state", placeholder: "CT" }
    ]);
  }
  $("add-vehicle").addEventListener("click", addVehicle);
  $("add-driver").addEventListener("click", addDriver);
  addVehicle();
  addDriver();

  // The planner creates a checklist and a manual collection grid. It does not
  // claim to query insurers; prices entered here must come from real insurer quotes.
  var insurers = [];
  var scenarioItems = [];
  var suggestions = ["Progressive", "GEICO", "State Farm", "Allstate", "Liberty Mutual", "Travelers"];

  function selectedProfile() {
    var flags = {};
    document.querySelectorAll("#profile-checks input[data-bool]").forEach(function (input) {
      flags[input.dataset.bool] = input.checked;
    });
    flags.vehicles = document.querySelectorAll("#vehicles .vehicle").length;
    return flags;
  }

  function eligibleFor(item, profile) {
    var id = item.id;
    if (id === "multi_car") return profile.vehicles >= 2;
    if (id === "bundle") return profile.homeowner || profile.has_bundle_policy;
    if (id === "group") return profile.employer_or_group;
    if (id === "military") return profile.military;
    if (id === "good_student") return profile.good_student;
    if (id === "claim_free") return profile.clean_record_3yr;
    if (id === "continuous") return profile.continuous_coverage;
    if (id === "vehicle_safety") return profile.vehicle_safety_features;
    if (id === "telematics") return profile.willing_telematics;
    if (id === "pay_in_full") return profile.willing_pay_in_full;
    if (id === "autopay") return profile.autopay_ok;
    if (id === "paperless") return profile.paperless_ok;
    if (id === "defensive_course") return profile.willing_defensive_course;
    return false;
  }

  function buildPlan() {
    fetch("/api/levers").then(function (response) {
      if (!response.ok) throw new Error("Could not load savings options");
      return response.json();
    }).then(function (data) {
      var profile = selectedProfile();
      scenarioItems = data.levers.filter(function (item) {
        return item.group === "discount" && eligibleFor(item, profile);
      });
      var root = $("plan-scenarios");
      root.replaceChildren();
      var intro = el("p", { "class": "hint" }, "These are eligible discount requests based on the answers selected. They are not guaranteed savings; keep the requested coverage unchanged.");
      root.appendChild(intro);
      if (!scenarioItems.length) {
        root.appendChild(el("p", { "class": "warn-note" }, "No additional discount was identified from the selected answers. You can still compare insurers and ask each one to check every discount available in your state."));
      } else {
        var list = el("ul", { "class": "plan-list" });
        scenarioItems.forEach(function (item) {
          var li = el("li");
          li.appendChild(el("strong", {}, item.name + " — "));
          li.appendChild(document.createTextNode(item.ask + (item.tip ? " " + item.tip : "")));
          list.appendChild(li);
        });
        root.appendChild(list);
      }
      $("plan-body").hidden = false;
      renderSuggestions();
      renderGrid();
    }).catch(function (error) {
      $("plan-scenarios").textContent = error.message;
      $("plan-body").hidden = false;
    });
  }

  function renderSuggestions() {
    var root = $("ins-suggest");
    root.replaceChildren();
    suggestions.forEach(function (name) {
      var button = el("button", { type: "button", "class": "chip" }, "+ " + name);
      button.addEventListener("click", function () { addInsurer(name); });
      root.appendChild(button);
    });
  }

  function addInsurer(name) {
    name = String(name || $("ins-name").value).trim();
    if (!name || insurers.some(function (item) { return item.toLowerCase() === name.toLowerCase(); })) return;
    insurers.push(name);
    $("ins-name").value = "";
    renderGrid();
  }

  function renderGrid() {
    var root = $("plan-grid");
    root.replaceChildren();
    if (!insurers.length) {
      root.appendChild(el("p", { "class": "hint" }, "Add the insurers you are requesting real quotes from. Suggested names are only a convenience; availability depends on your state."));
      return;
    }
    var tableWrap = el("div", { "class": "plan-scroll" });
    var table = el("table", { "class": "plan-table" });
    var head = el("thead");
    var header = el("tr");
    header.appendChild(el("th", {}, "Quote version"));
    insurers.forEach(function (name) { header.appendChild(el("th", {}, name)); });
    head.appendChild(header);
    table.appendChild(head);
    var body = el("tbody");
    var rows = [{ id: "base", name: "Requested coverage — base quote" }].concat(scenarioItems.map(function (item) {
      return { id: item.id, name: "Same coverage + " + item.name };
    }));
    rows.forEach(function (row) {
      var tr = el("tr");
      tr.appendChild(el("th", {}, row.name));
      insurers.forEach(function (name) {
        var td = el("td");
        var input = el("input", { type: "number", min: "0.01", step: "0.01", placeholder: "Real $/mo", "aria-label": name + " " + row.name });
        input.dataset.insurer = name;
        input.dataset.scenario = row.id;
        td.appendChild(input);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    tableWrap.appendChild(table);
    root.appendChild(tableWrap);
  }

  function findCheapest() {
    var entries = [];
    document.querySelectorAll("#plan-grid input[data-scenario]").forEach(function (input) {
      var price = Number(input.value);
      if (price > 0 && Number.isFinite(price)) {
        entries.push({ insurer: input.dataset.insurer, scenario: input.dataset.scenario, price: price });
      }
    });
    entries.sort(function (a, b) { return a.price - b.price; });
    var root = $("plan-results");
    root.replaceChildren();
    if (!entries.length) {
      root.appendChild(el("p", { "class": "warn-note" }, "Enter at least one real quote price returned by an insurer. The planner does not generate or estimate live quotes."));
      return;
    }
    var best = entries[0];
    var scenario = best.scenario === "base" ? "requested coverage, base quote" : "requested coverage plus " + best.scenario;
    root.appendChild(el("p", { "class": "warn-note" }, "Lowest entered real quote: " + best.insurer + " — $" + best.price.toFixed(2) + "/mo (" + scenario + "). Verify the same limits, deductibles, drivers, vehicles, fees, and policy term before comparing or buying."));
  }

  $("build-plan").addEventListener("click", buildPlan);
  $("ins-add").addEventListener("click", function () { addInsurer(); });
  $("ins-name").addEventListener("keydown", function (event) {
    if (event.key === "Enter") { event.preventDefault(); addInsurer(); }
  });
  $("plan-best").addEventListener("click", findCheapest);

  fetch("/api/search/status").then(function (response) { return response.json(); }).then(function (status) {
    var note = el("p", { "class": "warn-note" }, status.message);
    var planner = $("planner");
    planner.insertBefore(note, $("build-plan"));
  }).catch(function () {});
})();
