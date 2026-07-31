/* Browser side of the demo.
 *
 * The only job of this file is to hold a Server-Sent Events connection open and
 * apply whatever the server pushes down it. There is no polling, no timer, and
 * no reload: when the flag flips in LaunchDarkly, the server re-renders the
 * panel and sends it, and the swap you see below happens in the next frame.
 *
 * Note that the browser never talks to LaunchDarkly directly and never sees the
 * SDK key. All flag evaluation happens server-side in the Python SDK.
 */

(function () {
  "use strict";

  var els = {
    panel: document.getElementById("feature-panel"),
    variantBadge: document.getElementById("variant-badge"),
    updatedAt: document.getElementById("updated-at"),
    statePill: document.getElementById("state-pill"),
    reason: document.getElementById("reason-text"),
    evalContext: document.getElementById("eval-context"),
    evalAttrs: document.getElementById("eval-attrs"),
    conn: document.getElementById("conn-status"),
    log: document.getElementById("event-log"),
    toast: document.getElementById("toast"),
  };

  var state = window.__INITIAL_STATE__;
  var personaId = state.persona.id;
  var lastFlagValue = state.flagValue;
  var source = null;

  // ---------------------------------------------------------------- helpers

  function now() {
    return new Date().toLocaleTimeString([], { hour12: false });
  }

  function addLog(text, kind) {
    var empty = els.log.querySelector(".log-empty");
    if (empty) { empty.parentNode.remove(); }

    var li = document.createElement("li");
    if (kind) { li.className = "kind-" + kind; }
    li.innerHTML =
      '<span class="log-time"></span><span class="log-text"></span>';
    li.querySelector(".log-time").textContent = now();
    li.querySelector(".log-text").textContent = text;
    els.log.prepend(li);

    while (els.log.children.length > 40) { els.log.lastElementChild.remove(); }
  }

  var toastTimer = null;
  function toast(message, isError) {
    els.toast.textContent = message;
    els.toast.className = "toast show" + (isError ? " error" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { els.toast.className = "toast"; }, 4500);
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok && data.ok !== false, data: data };
      });
    });
  }

  function newSessionId() {
    if (window.crypto && window.crypto.randomUUID) { return window.crypto.randomUUID(); }
    return "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  // ------------------------------------------------------------ apply state

  function applyState(next, isFirstFrame) {
    var changed = next.flagValue !== lastFlagValue;

    // Swap the feature panel. This is the "instant release / instant rollback"
    // moment — the DOM for the whole feature is replaced in place. The very
    // first frame carries no HTML: the server already rendered that panel.
    if (next.panelHtml) { els.panel.innerHTML = next.panelHtml; }
    if (changed && !isFirstFrame) {
      els.panel.classList.remove("is-swapping");
      void els.panel.offsetWidth;            // restart the CSS animation
      els.panel.classList.add("is-swapping");
    }

    els.variantBadge.textContent = next.variantLabel;
    els.updatedAt.textContent = "updated at " + next.timestamp;
    els.reason.textContent = next.reasonText;

    els.statePill.textContent = next.flagValue ? "released" : "not released";
    els.statePill.className = "state-pill " + (next.flagValue ? "on" : "off");

    els.evalContext.innerHTML =
      '<span class="ctx-name"></span> <span class="muted"></span>';
    els.evalContext.querySelector(".ctx-name").textContent = next.persona.name;
    els.evalContext.querySelector(".muted").textContent = "(" + next.persona.key + ")";

    els.evalAttrs.innerHTML = "";
    [
      ["role", next.persona.role],
      ["betaTester", String(next.persona.betaTester)],
      ["plan", next.persona.plan],
    ].forEach(function (pair) {
      var chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = pair[0] + ": " + pair[1];
      els.evalAttrs.appendChild(chip);
    });

    if (changed && !isFirstFrame) {
      addLog(
        next.flagValue
          ? "Flag ON — " + next.persona.name + " now sees Order Insights v2."
          : "Flag OFF — " + next.persona.name + " rolled back to v1.",
        next.flagValue ? "release" : "rollback"
      );
    } else if (next.source === "connected") {
      addLog(
        "Watching " + next.flagKey + " for " + next.persona.name +
        " (currently " + (next.flagValue ? "ON" : "OFF") + ").");
    }

    if (next.isFallback) {
      addLog("Served the code fallback value — LaunchDarkly could not decide.", "rollback");
    }

    lastFlagValue = next.flagValue;
    state = next;
  }

  // --------------------------------------------------------------- streaming

  function connect() {
    if (source) { source.close(); }

    var sessionId = newSessionId();
    var url = "/api/stream?session=" + encodeURIComponent(sessionId) +
              "&user=" + encodeURIComponent(personaId);
    source = new EventSource(url);

    source.addEventListener("open", function () {
      els.conn.textContent = "live (server-sent events)";
      els.conn.className = "conn live";
    });

    source.addEventListener("state", function (event) {
      applyState(JSON.parse(event.data), false);
    });

    source.addEventListener("error", function () {
      // EventSource reconnects on its own; just reflect the state honestly.
      els.conn.textContent = "reconnecting…";
      els.conn.className = "conn down";
    });
  }

  // ----------------------------------------------------------------- wiring

  document.querySelectorAll(".persona-btn").forEach(function (button) {
    button.addEventListener("click", function () {
      personaId = button.dataset.persona;
      document.querySelectorAll(".persona-btn").forEach(function (other) {
        other.classList.toggle("is-active", other === button);
      });
      addLog("Switched to " + button.textContent.trim().split("\n")[0] + ".");
      // Re-open the stream so the server evaluates the flag for the new
      // LaunchDarkly context and registers a listener for it.
      connect();
    });
  });

  var reportBtn = document.getElementById("report-bug-btn");
  if (reportBtn) {
    reportBtn.addEventListener("click", function () {
      postJson("/api/report-bug", { user: personaId }).then(function (result) {
        toast(result.data.message, !result.ok);
        addLog("Reported a problem — custom metric event sent to LaunchDarkly.");
      });
    });
  }

  var remediateBtn = document.getElementById("remediate-btn");
  if (remediateBtn) {
    remediateBtn.addEventListener("click", function () {
      remediateBtn.disabled = true;
      addLog("Kill switch fired — asking LaunchDarkly to turn the flag off.", "rollback");
      postJson("/api/remediate", {})
        .then(function (result) {
          toast(result.data.message, !result.ok);
          if (!result.ok) { addLog("Kill switch failed: " + result.data.message, "rollback"); }
        })
        .catch(function (error) { toast("Request failed: " + error, true); })
        .finally(function () {
          setTimeout(function () { remediateBtn.disabled = false; }, 2000);
        });
    });
  }

  document.querySelectorAll("[data-self-test]").forEach(function (button) {
    button.addEventListener("click", function () {
      postJson("/api/self-test/toggle", { value: button.dataset.selfTest === "true" })
        .then(function (result) { if (!result.ok) { toast(result.data.message, true); } });
    });
  });

  // ------------------------------------------------------------------ start

  addLog("Dashboard loaded.");
  applyState(state, true);
  connect();

  window.addEventListener("beforeunload", function () { if (source) { source.close(); } });
})();
