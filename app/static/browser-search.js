(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var box = $("browser-search-status");
  var providersRoot = $("browser-provider-list");
  var button = $("browser-search-button");
  var consent = $("browser-consent");
  var jobBox = $("browser-job-status");
  if (!box || !button) return;

  var providers = [];
  var busy = false;
  function selectedProviders() {
    return Array.prototype.map.call(providersRoot.querySelectorAll("input[type=checkbox]:checked"), function (node) { return node.value; });
  }
  function updateButton() {
    button.disabled = busy || !consent.checked || selectedProviders().length === 0;
  }
  function addProvider(provider) {
    var label = document.createElement("label");
    var input = document.createElement("input");
    input.type = "checkbox";
    input.value = provider.id;
    input.addEventListener("change", updateButton);
    label.appendChild(input);
    label.appendChild(document.createTextNode(" " + provider.name));
    providersRoot.appendChild(label);
  }
  function collectFormData() {
    var data = {};
    function add(key, value) { if (value !== undefined && value !== null && String(value).trim()) data[key] = String(value).trim(); }
    add("state", $("p_state").value);
    add("zip_code", $("p_zip").value);
    add("vehicles", document.querySelectorAll("#vehicles .vehicle").length);
    add("drivers", document.querySelectorAll("#drivers .person").length);
    var vehicle = document.querySelector("#vehicles .vehicle");
    if (vehicle) ["vehicle_year", "vehicle_make", "vehicle_model"].forEach(function (key) {
      var input = vehicle.querySelector('[data-field="' + key + '"]');
      if (input) add(key, input.value);
    });
    add("bodily_injury_limit", $("c_bi").value);
    add("property_damage_limit", $("c_pd").value);
    add("comp_deductible", $("c_comp").value);
    add("collision_deductible", $("c_coll").value);
    return data;
  }
  function showJob(job) {
    jobBox.replaceChildren();
    var heading = document.createElement("p");
    heading.className = "warn-note";
    heading.textContent = "Search status: " + job.status;
    jobBox.appendChild(heading);
    (job.results || []).forEach(function (result) {
      var item = document.createElement("p");
      item.textContent = result.company + ": $" + result.effective_monthly.toFixed(2) + "/mo — " + result.verification_status + ". This is extracted data, not yet a confirmed coverage match.";
      jobBox.appendChild(item);
    });
    (job.errors || []).forEach(function (error) {
      var item = document.createElement("p");
      item.textContent = error.provider_id + ": " + error.status + " — " + error.message;
      jobBox.appendChild(item);
    });
  }
  function poll(jobId, attempts) {
    fetch("/api/browser/jobs/" + encodeURIComponent(jobId)).then(function (response) {
      if (!response.ok) throw new Error("Could not read search status.");
      return response.json();
    }).then(function (job) {
      showJob(job);
      if (["completed", "failed", "needs_human"].indexOf(job.status) === -1 && attempts < 45) {
        window.setTimeout(function () { poll(jobId, attempts + 1); }, 2500);
      } else {
        if (attempts >= 45) jobBox.appendChild(document.createTextNode("Status polling timed out. The server-side task may still be running."));
        busy = false;
        updateButton();
      }
    }).catch(function (error) {
      jobBox.textContent = error.message;
    });
  }

  consent.addEventListener("change", updateButton);
  fetch("/api/browser/providers").then(function (response) {
    if (!response.ok) throw new Error("Browser service is unavailable.");
    return response.json();
  }).then(function (data) {
    providers = data.providers || [];
    box.textContent = data.message + " Engine: " + data.engine + ".";
    box.className = providers.length ? "success-note" : "warn-note";
    providers.forEach(addProvider);
    updateButton();
  }).catch(function () {
    box.className = "warn-note";
    box.textContent = "Could not check browser search status. Reload the page.";
  });

  button.addEventListener("click", function () {
    var ids = selectedProviders();
    if (!consent.checked || !ids.length) return;
    busy = true;
    updateButton();
    button.textContent = "Starting browser search...";
    jobBox.textContent = "Submitting an authorized quote request. No policy will be purchased or bound.";
    fetch("/api/browser/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider_ids: ids, form_data: collectFormData(), authorized_to_request_quote: true })
    }).then(function (response) {
      return response.json().then(function (data) { if (!response.ok) throw new Error(data.detail || "Search could not start."); return data; });
    }).then(function (job) {
      showJob(job);
      poll(job.id, 0);
    }).catch(function (error) {
      jobBox.textContent = error.message;
      busy = false;
      updateButton();
    }).finally(function () {
      button.textContent = "Search approved insurers";
      updateButton();
    });
  });
})();
