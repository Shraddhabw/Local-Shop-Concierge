// Optional niceties for flash banners. Without JavaScript the banner simply stays visible.
(function () {
  var box = document.querySelector("[data-flash]");
  if (!box) return;
  var close = box.querySelector(".flash-close");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function dismiss() {
    if (reduce) { box.remove(); return; }
    box.classList.add("hide");
    setTimeout(function () { box.remove(); }, 400);
  }
  if (close) { close.hidden = false; close.addEventListener("click", dismiss); }
  setTimeout(dismiss, 6000);
})();
