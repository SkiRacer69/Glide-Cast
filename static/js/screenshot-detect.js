/**
 * Best-effort screenshot-related key detection. OS and browser shortcuts often never reach the page.
 * Sends a signal to the server for logging + optional email (see SCREENSHOT_ALERT_EMAIL).
 */
(function () {
  var url = window.SCREENSHOT_SIGNAL_URL;
  if (!url) return;

  var lastSent = 0;
  var THROTTLE_MS = 2500;

  function getCsrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    if (m && m.getAttribute("content")) return m.getAttribute("content");
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function send(payload) {
    var now = Date.now();
    if (now - lastSent < THROTTLE_MS) return;
    lastSent = now;
    var token = getCsrfToken();
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": token,
      },
      body: JSON.stringify(
        Object.assign(
          {
            page_path: location.pathname + location.search,
            signal_type: "keydown",
          },
          payload
        )
      ),
    }).catch(function () {});
  }

  document.addEventListener(
    "keydown",
    function (e) {
      var code = e.code || "";
      var key = e.key || "";

      if (code === "PrintScreen" || key === "PrintScreen") {
        send({ detail: "PrintScreen" });
        return;
      }

      if (
        e.metaKey &&
        e.shiftKey &&
        (key === "3" ||
          key === "4" ||
          key === "5" ||
          code === "Digit3" ||
          code === "Digit4" ||
          code === "Digit5")
      ) {
        send({ detail: "Meta+Shift+number (" + (key || code) + ")" });
        return;
      }

      if (e.shiftKey && e.ctrlKey && (code === "KeyS" || key === "s" || key === "S")) {
        send({ detail: "Ctrl+Shift+S" });
      }
    },
    true
  );
})();
