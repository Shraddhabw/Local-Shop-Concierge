// Dashboard form helpers (static file: the CSP forbids inline scripts). Everything degrades gracefully without JS.
(function () {
  // 1) Prevent duplicate submissions: ignore a second submit and disable the buttons right after the first.
  Array.prototype.forEach.call(document.querySelectorAll("form[method=post]"), function (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.submitting) { event.preventDefault(); return; }
      form.dataset.submitting = "1";
      // disable after the browser has read the clicked button (formaction), not during the event
      setTimeout(function () {
        Array.prototype.forEach.call(form.querySelectorAll("button, input[type=submit]"), function (b) { b.disabled = true; });
      }, 0);
    });
  });
  // coming back with the browser's Back button must not leave the buttons disabled
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    Array.prototype.forEach.call(document.querySelectorAll("form[data-submitting]"), function (form) {
      delete form.dataset.submitting;
      Array.prototype.forEach.call(form.querySelectorAll("button:disabled, input[type=submit]:disabled"), function (b) { b.disabled = false; });
    });
  });
  // 2) After a successful add, put the cursor in the first field of the add form.
  var banner = document.querySelector("[data-flash][data-focus]");
  var addForm = document.querySelector("[data-add-form]");
  if (banner && addForm) {
    var first = addForm.querySelector("input:not([type=hidden]):not([type=checkbox]):not([tabindex='-1']), textarea");
    if (first) first.focus();
  }
})();
