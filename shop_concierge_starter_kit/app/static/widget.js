/* Embed: <script src="https://YOURDOMAIN/widget.js?shop=your-slug" defer></script> */
(function () {
  var script = document.currentScript;
  if (!script || !script.src) return;
  var url = new URL(script.src);
  var slug = url.searchParams.get("shop");
  if (!slug || !/^[a-z0-9-]{3,40}$/.test(slug)) return;
  var frame = null;
  var button = document.createElement("button");
  button.textContent = "Chat with us";
  button.setAttribute("aria-label", "Open chat");
  button.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483646;background:#1e6fd9;" +
    "color:#fff;border:0;border-radius:24px;padding:12px 18px;font:16px system-ui,sans-serif;cursor:pointer;" +
    "box-shadow:0 2px 8px rgba(0,0,0,.3)";
  button.addEventListener("click", function () {
    if (frame) { frame.remove(); frame = null; button.textContent = "Chat with us"; return; }
    frame = document.createElement("iframe");
    frame.src = url.origin + "/embed/" + encodeURIComponent(slug);
    frame.title = "Chat";
    frame.style.cssText = "position:fixed;right:16px;bottom:72px;z-index:2147483646;width:min(360px,calc(100vw - 32px));" +
      "height:min(520px,calc(100vh - 100px));border:0;border-radius:12px;background:#fff;box-shadow:0 4px 16px rgba(0,0,0,.35)";
    document.body.appendChild(frame);
    button.textContent = "Close chat";
  });
  document.body.appendChild(button);
})();
