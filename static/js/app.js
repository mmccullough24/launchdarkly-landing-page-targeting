/* Browser side of the landing page targeting demo.
 *
 * This file holds a Server-Sent Events connection open and applies whatever the
 * server pushes down it. There is no polling, no timer, and no reload: when you
 * change targeting in LaunchDarkly, the server re-evaluates the flag for this
 * visitor's context, re-renders the hero, and sends it.
 *
 * The browser never talks to LaunchDarkly and never sees the SDK key. All flag
 * evaluation happens server-side in the Python SDK, which is why the targeting
 * attributes below can include things you would not want to expose publicly.
 */

(function () {
  "use strict";

  var els = {
    heroMount: document.getElementById("hero-mount"),
    variationPill: document.getElementById("variation-pill"),
    variationIndex: document.getElementById("variation-index"),
    mechanism: document.getElementById("mechanism-badge"),
    reason: document.getElementById("reason-text"),
    expected: document.getElementById("expected-line"),
    ctxName: document.getElementById("ctx-name"),
    ctxKey: document.getElementById("ctx-key"),
    ctxBlurb: document.getElementById("ctx-blurb"),
    ctxAttrs: document.getElementById("ctx-attrs"),
    ctaCount: document.getElementById("cta-count"),
    conn: document.getElementById("conn-status"),
    log: document.getElementById("event-log"),
    toast: document.getElementById("toast"),
  };

  var state = window.__INITIAL_STATE__;
  var visitorId = state.visitor.id;
  var lastVariation = state.variation;
  var source = null;
  var conversions = 0;

  // ----------------------------------------------------------------- helpers

  function now() {
    return new Date().toLocaleTimeString([], { hour12: false });
  }

  function addLog(text, kind) {
    var empty = els.log.querySelector(".log-empty");
    if (empty) { empty.remove(); }

    var li = document.createElement("li");
    if (kind) { li.className = "kind-" + kind; }
    li.innerHTML = '<span class="log-time"></span><span class="log-text"></span>';
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
    toastTimer = setTimeout(function () { els.toast.className = "toast"; }, 4000);
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

  // Human-readable name for each targeting mechanism, used in the event log.
  var MECHANISM_LABEL = {
    individual: "individual target",
    rule: "targeting rule",
    default: "default rule",
    off: "flag off",
    error: "evaluation error",
  };

  // ------------------------------------------------------------- apply state

  function applyState(next, isFirstFrame) {
    var changed = next.variation !== lastVariation;

    // Swap the flagged component. This is the moment worth watching: the whole
    // hero is replaced in place, with no reload and no flash of the old page.
    // The very first frame carries no HTML — the server already rendered it.
    if (next.heroHtml) { els.heroMount.innerHTML = next.heroHtml; }
    if (changed && !isFirstFrame) {
      els.heroMount.classList.remove("is-swapping");
      void els.heroMount.offsetWidth;          // restart the CSS animation
      els.heroMount.classList.add("is-swapping");
    }

    els.variationPill.textContent = next.variation;
    els.variationPill.className = "variation-pill var-" + next.variation;
    els.variationIndex.textContent =
      next.variationIndex === null ? "fallback value" : "index " + next.variationIndex;

    els.mechanism.textContent = next.reasonKind;
    els.mechanism.className = "mechanism mech-" + next.mechanism;
    els.reason.textContent = next.reasonText;

    els.expected.className = "expected " + (next.expected.matches ? "ok" : "pending");
    els.expected.innerHTML = "";
    els.expected.append(
      next.expected.matches ? "✓ " : "· ",
      "Expected ",
      Object.assign(document.createElement("b"), { textContent: next.expected.variation }),
      " via ",
      Object.assign(document.createElement("b"), { textContent: next.expected.via })
    );

    els.ctxName.textContent = next.visitor.name;
    els.ctxKey.textContent = next.visitor.key;
    els.ctxBlurb.textContent = next.visitor.blurb;

    els.ctxAttrs.innerHTML = "";
    Object.keys(next.attributes).forEach(function (name) {
      var chip = document.createElement("span");
      chip.className = "chip";
      var label = document.createElement("b");
      label.textContent = name;
      chip.append(label, String(next.attributes[name]));
      els.ctxAttrs.appendChild(chip);
    });

    if (changed && !isFirstFrame) {
      addLog(
        next.visitor.name + " now sees '" + next.variation + "' — served by the " +
        (MECHANISM_LABEL[next.mechanism] || next.mechanism) + ".",
        next.variation === "control" ? "rollback" : "release"
      );
    } else if (next.source === "connected") {
      addLog(
        "Watching " + next.flagKey + " for " + next.visitor.name +
        " (currently '" + next.variation + "' via " + next.reasonKind + ")."
      );
    }

    if (next.isFallback) {
      addLog("Served the code fallback — LaunchDarkly could not decide.", "rollback");
    }

    lastVariation = next.variation;
    state = next;
  }

  // --------------------------------------------------------------- streaming

  function connect() {
    if (source) { source.close(); }

    var url = "/api/stream?session=" + encodeURIComponent(newSessionId()) +
              "&visitor=" + encodeURIComponent(visitorId);
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

  // ------------------------------------------------------------------ wiring

  document.querySelectorAll(".visitor-btn").forEach(function (button) {
    button.addEventListener("click", function () {
      visitorId = button.dataset.visitor;
      document.querySelectorAll(".visitor-btn").forEach(function (other) {
        other.classList.toggle("is-active", other === button);
      });
      addLog("Previewing as " + button.textContent.trim() + ".");
      // Re-open the stream so the server evaluates the flag for the new
      // LaunchDarkly context and registers a listener for it.
      connect();
    });
  });

  // Delegated: the CTA lives inside the hero, which is replaced wholesale on
  // every variation change, so binding directly would not survive a swap.
  els.heroMount.addEventListener("click", function (event) {
    if (!event.target.closest("#hero-cta")) { return; }
    postJson("/api/cta-click", { visitor: visitorId }).then(function (result) {
      toast(result.data.message, !result.ok);
      if (result.ok) {
        conversions += 1;
        els.ctaCount.textContent =
          conversions + (conversions === 1 ? " conversion" : " conversions") +
          " sent this session (last: '" + state.variation + "').";
        addLog("Conversion event sent for variation '" + state.variation + "'.", "metric");
      }
    });
  });

  document.querySelectorAll("[data-offline-targeting]").forEach(function (button) {
    button.addEventListener("click", function () {
      var on = button.dataset.offlineTargeting === "true";
      postJson("/api/offline/targeting", { on: on }).then(function (result) {
        if (!result.ok) { toast(result.data.message, true); }
        else { addLog("Targeting turned " + (on ? "ON" : "OFF") + ".", on ? "release" : "rollback"); }
      });
    });
  });

  // ------------------------------------------------------------------- start

  addLog("Landing page loaded.");
  applyState(state, true);
  connect();

  window.addEventListener("beforeunload", function () { if (source) { source.close(); } });
})();
