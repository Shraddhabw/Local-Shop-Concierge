// "Copy" button for the chat snippet. Without JavaScript the button stays hidden and the box can still be selected by hand.
(function () {
  var box = document.getElementById("embed-snippet");
  var button = document.getElementById("copy-embed");
  var status = document.getElementById("copy-status");
  if (!box || !button) return;
  button.hidden = false;
  box.addEventListener("focus", function () { box.select(); });
  function done() {
    button.textContent = "Copied";
    if (status) status.textContent = "Copied to clipboard.";
    setTimeout(function () { button.textContent = "Copy"; if (status) status.textContent = ""; }, 3000);
  }
  button.addEventListener("click", function () {
    box.focus(); box.select();
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(box.value).then(done, function () { document.execCommand("copy") && done(); });
    } else if (document.execCommand("copy")) { done(); }
  });
})();
