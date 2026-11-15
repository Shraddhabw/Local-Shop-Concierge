(function () {
  var root = document.getElementById("chat");
  if (!root) return;
  var slug = root.dataset.slug;
  var log = document.getElementById("chat-log");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var leadBox = document.getElementById("lead-box");
  var leadForm = document.getElementById("lead-form");
  var lastQuestion = "";

  function add(text, who) {
    var p = document.createElement("p");
    p.className = "msg " + who;
    p.textContent = text;                      // never innerHTML
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
  }
  function post(path, body) {
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body) }).then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, data: j }; }); });
  }
  add("Hi! Ask me about prices, timings or services.", "bot");
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    lastQuestion = text; input.value = ""; add(text, "me");
    post("/api/chat", { slug: slug, message: text }).then(function (res) {
      if (!res.ok) { add(res.data.error || "Something went wrong. Please try again.", "bot"); return; }
      add(res.data.answer, "bot");
      leadBox.hidden = !(res.data.needs_human || res.data.proposed_lead);
      if (res.data.proposed_lead) {            // AI staged a lead: prefill, customer must tick consent
        leadForm.name.value = res.data.proposed_lead.name || "";
        leadForm.contact.value = res.data.proposed_lead.contact || "";
      }
    }).catch(function () { add("Could not reach the shop. Please try again.", "bot"); });
  });
  leadForm.addEventListener("submit", function (e) {
    e.preventDefault();
    post("/api/lead", { slug: slug, name: leadForm.name.value, contact: leadForm.contact.value,
      message: lastQuestion, consent: leadForm.consent.checked }).then(function (res) {
        add(res.ok ? res.data.message : (res.data.error || "Could not save your details."), "bot");
        if (res.ok) { leadBox.hidden = true; leadForm.reset(); }
      }).catch(function () { add("Could not reach the shop. Please try again.", "bot"); });
  });
})();
