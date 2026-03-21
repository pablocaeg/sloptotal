// SlopTotal Google Search Content Script
// Cache-first: cached badges appear instantly, fresh results stream in after

(function () {
  "use strict";

  const PROCESSED_ATTR = "data-sloptotal-processed";
  const MIN_TEXT_LENGTH = 30;
  let debounceTimer = null;
  let scanInFlight = false;

  const CONTAINER_SELECTORS = [
    ".g", ".hlcw0c", ".tF2Cxc", ".N54PNb", ".Gx5Zad",
  ];

  const SNIPPET_SELECTORS = [
    ".VwiC3b", '[data-sncf="1"]', '[data-sncf="2"]',
    ".lEBKkf span", ".IsZvec", ".yDYNvb", "[data-md]", ".kb0PBd", ".hgKElc",
  ];

  function extractSnippets() {
    const t0 = performance.now();
    const containerQuery = CONTAINER_SELECTORS
      .map((s) => `${s}:not([${PROCESSED_ATTR}])`)
      .join(", ");
    const results = document.querySelectorAll(containerQuery);
    const snippets = [];
    const seen = new Set();

    results.forEach((el, i) => {
      if (seen.has(el) || el.hasAttribute(PROCESSED_ATTR)) return;
      seen.add(el);

      let snippetEl = null;
      for (const sel of SNIPPET_SELECTORS) {
        snippetEl = el.querySelector(sel);
        if (snippetEl) break;
      }
      if (!snippetEl) return;

      const text = snippetEl.textContent.trim();
      if (text.length < MIN_TEXT_LENGTH) return;

      const id = `g-${Date.now()}-${i}`;
      el.setAttribute(PROCESSED_ATTR, id);
      const linkEl = el.querySelector("a[href]");
      snippets.push({ id, text, url: linkEl ? linkEl.href : "", element: el, snippetEl });
    });

    // Fallback: h3-based heuristic
    if (snippets.length === 0 && results.length === 0) {
      const rso = document.getElementById("rso") || document.getElementById("search");
      if (rso) {
        rso.querySelectorAll("h3").forEach((h3, i) => {
          let container = h3.closest("[data-hveid]") || h3.closest("[data-ved]");
          if (!container) {
            let el = h3.parentElement;
            for (let j = 0; j < 4 && el && el !== rso; j++) {
              if (el.tagName === "DIV" && el.querySelector("a[href]")) { container = el; break; }
              el = el.parentElement;
            }
          }
          if (!container || container.hasAttribute(PROCESSED_ATTR) || seen.has(container)) return;
          seen.add(container);

          const candidates = container.querySelectorAll("span, div");
          let snippetEl = null, longestText = "";
          for (const c of candidates) {
            if (c.contains(h3) || h3.contains(c) || c.querySelector("h3")) continue;
            const t = c.textContent.trim();
            if (t.length > longestText.length && t.length >= MIN_TEXT_LENGTH) { longestText = t; snippetEl = c; }
          }
          if (!snippetEl) return;

          const id = `g-${Date.now()}-${i}`;
          container.setAttribute(PROCESSED_ATTR, id);
          const linkEl = container.querySelector("a[href]");
          snippets.push({ id, text: snippetEl.textContent.trim(), url: linkEl ? linkEl.href : "", element: container, snippetEl });
        });
      }
    }

    const ms = Math.round((performance.now() - t0) * 100) / 100;
    if (snippets.length > 0) {
      const chars = snippets.map((s) => s.text.length);
      console.log(
        `[G] extract: ${snippets.length} snippets in ${ms}ms | ` +
        `chars: [${chars.join(", ")}] total=${chars.reduce((a, b) => a + b, 0)}`
      );
    }
    return snippets;
  }

  // Calibrate raw fakespot 0-1 → 0-100 (mirrors server _compute_fakespot_score thresholds)
  function calibrateFakespot(raw) {
    if (raw >= 0.85) return 75 + ((raw - 0.85) / 0.15) * 15;
    if (raw >= 0.65) return 55 + ((raw - 0.65) / 0.20) * 20;
    if (raw >= 0.45) return 35 + ((raw - 0.45) / 0.20) * 20;
    if (raw >= 0.25) return 15 + ((raw - 0.25) / 0.20) * 20;
    return (raw / 0.25) * 15;
  }

  // Human-readable structural signal interpretation
  function interpretStructural(structScore) {
    if (structScore >= 50) return "Strong AI writing patterns";
    if (structScore >= 25) return "Some AI-like patterns";
    if (structScore >= 10) return "Minor pattern signals";
    return "Natural writing style";
  }

  // Readable signal names
  function signalLabel(engine) {
    const labels = {
      linguistic: "AI phrases", formulaic: "Formulaic structure",
      structural: "Text structure", vocabulary: "Vocabulary diversity",
      readability: "Reading level", sentiment: "Tone analysis",
    };
    return labels[engine] || engine;
  }

  function createBadge(score, confidence, source, raw, chars, data) {
    const badge = document.createElement("div");
    badge.className = "sloptotal-badge";
    let color, label;
    const isInfo = data?.scoreable === false;
    const isUrl = source === "url_content";

    if (isInfo) {
      color = "sloptotal-info";
      label = data.page_label || "Not scored";
    } else if (score >= 75) { color = "sloptotal-high"; label = "Likely AI"; }
    else if (score >= 50) { color = "sloptotal-medium"; label = "Maybe AI"; }
    else if (score >= 25) { color = "sloptotal-low"; label = "Probably Human"; }
    else { color = "sloptotal-safe"; label = "Likely Human"; }
    badge.classList.add(color);

    // Page type tag: show actual type (article/docs/hub/landing)
    let typeTag = "";
    if (isInfo) {
      typeTag = `<span class="sloptotal-type">${data.page_type || "page"}</span>`;
    } else if (data?.page_type === "reference") {
      typeTag = `<span class="sloptotal-type">docs</span>`;
    } else if (isUrl && data?.page_type) {
      typeTag = `<span class="sloptotal-type">${data.page_type}</span>`;
    }

    if (isInfo) {
      badge.innerHTML = `
        <span class="sloptotal-dot"></span>
        <span class="sloptotal-label">${label}</span>
        ${typeTag}
        <span class="sloptotal-expand">&#9660;</span>
      `;
    } else {
      badge.innerHTML = `
        <span class="sloptotal-dot"></span>
        <span class="sloptotal-label">${label}</span>
        <span class="sloptotal-bar"><span class="sloptotal-bar-fill" style="width:${Math.round(score)}%"></span></span>
        <span class="sloptotal-score">${Math.round(score)}%</span>
        ${typeTag}
        <span class="sloptotal-expand">&#9660;</span>
      `;
    }

    badge.title = isInfo ? data.page_label : "Click for details";

    // Click to expand/collapse detail panel
    badge.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      const parent = badge.parentElement;
      const existing = parent?.querySelector(".sloptotal-details");
      if (existing) {
        existing.remove();
        badge.querySelector(".sloptotal-expand").innerHTML = "&#9660;";
        return;
      }
      badge.querySelector(".sloptotal-expand").innerHTML = "&#9650;";

      const details = document.createElement("div");
      details.className = "sloptotal-details " + color;

      let html = "";

      if (isInfo) {
        const typeExplanations = {
          "short": "Not enough text for reliable AI detection.",
          "hub": "Link directory or index page with mostly navigation links.",
          "landing": "Promotional page with minimal article content.",
        };
        html += `<div class="sloptotal-detail-signal" style="opacity:0.8">${typeExplanations[data.page_type] || "This page type cannot be reliably scored."}</div>`;
        if (chars) html += `<div class="sloptotal-detail-meta">${chars} chars</div>`;
      } else {
        // Fakespot: show CALIBRATED score (matches badge), not raw
        const fsCalibrated = isUrl && data?.ml_score != null
          ? Math.round(data.ml_score)  // URL: ml_score is calibrated Fakespot before blend
          : Math.round(score);          // Snippet: badge score IS calibrated Fakespot
        const fsRaw = raw?.fakespot;

        const charText = chars ? `${chars} chars` : "";
        const confText = confidence ? confidence : "";
        const srcText = isUrl ? "page content" : "snippet";
        const metaParts = [charText, confText, srcText].filter(Boolean).join(" \u00B7 ");

        const engineRow = (name, val, pct) => `
          <div class="sloptotal-detail-row">
            <span class="sloptotal-detail-engine">${name}</span>
            <div class="sloptotal-detail-bar"><div class="sloptotal-detail-fill" style="width:${Math.min(pct, 100)}%"></div></div>
            <span class="sloptotal-detail-val">${val}%</span>
          </div>`;

        // Primary detector: calibrated Fakespot score
        html += `<div class="sloptotal-detail-section-label">Fakespot AI Detector</div>`;
        html += engineRow("Fakespot", fsCalibrated, fsCalibrated);
        // Show raw value as context if it differs significantly
        if (fsRaw != null && Math.abs(fsCalibrated - fsRaw * 100) > 10) {
          html += `<div class="sloptotal-detail-signal">Raw model output: ${(fsRaw * 100).toFixed(0)}% \u2192 calibrated to ${fsCalibrated}%</div>`;
        }

        // Structural / writing patterns section (URL scans only)
        const struct = data?.structural;
        if (struct && struct.score != null) {
          html += `<div class="sloptotal-detail-divider"></div>`;
          html += `<div class="sloptotal-detail-section-label">Writing Patterns</div>`;
          html += engineRow("Patterns", Math.round(struct.score), struct.score);
          html += `<div class="sloptotal-detail-signal">${interpretStructural(struct.score)}</div>`;

          // Show top flagged signals by name (not raw technical details)
          const sigs = struct.signals || {};
          const flagged = Object.entries(sigs)
            .filter(([k, v]) => v > 0.15 && !k.startsWith("html_"))
            .sort(([, a], [, b]) => b - a)
            .slice(0, 3);
          if (flagged.length > 0) {
            const names = flagged.map(([k]) => signalLabel(k)).join(", ");
            html += `<div class="sloptotal-detail-signal">Signals: ${names}</div>`;
          }

          // Blend explanation
          if (data?.ml_score != null && Math.round(data.ml_score) !== Math.round(score)) {
            html += `<div class="sloptotal-detail-blend">Fakespot ${Math.round(data.ml_score)}% + Patterns ${Math.round(struct.score)}% \u2192 <strong>${Math.round(score)}%</strong></div>`;
          }
        }

        // Page type + meta
        const typeLabel = data?.page_label && data.page_type !== "article" ? data.page_label : "";
        const allMeta = [typeLabel, metaParts].filter(Boolean).join(" \u00B7 ");
        html += `<div class="sloptotal-detail-meta">${allMeta}</div>`;
      }

      details.innerHTML = html;
      badge.insertAdjacentElement("afterend", details);
    });

    return badge;
  }

  function createLoadingBadge() {
    const badge = document.createElement("div");
    badge.className = "sloptotal-badge sloptotal-loading";
    badge.innerHTML = `<span class="sloptotal-dot"></span><span class="sloptotal-label">Scanning...</span>`;
    badge.title = "SlopTotal: Scanning...";
    return badge;
  }

  function findSnippetEl(el) {
    for (const sel of SNIPPET_SELECTORS) {
      const s = el.querySelector(sel);
      if (s) return s;
    }
    return null;
  }

  function injectBadge(el, badge) {
    const existing = el.querySelector(".sloptotal-badge");
    if (existing) {
      // Also remove any expanded details panel
      const details = existing.parentElement?.querySelector(".sloptotal-details");
      if (details) details.remove();
      existing.replaceWith(badge);
      return;
    }
    const snippetEl = findSnippetEl(el);
    if (snippetEl) snippetEl.parentElement.insertBefore(badge, snippetEl);
    else el.prepend(badge);
  }

  function injectBadges(results, source) {
    const t0 = performance.now();
    let count = 0;
    for (const [id, data] of Object.entries(results)) {
      const el = document.querySelector(`[${PROCESSED_ATTR}="${id}"]`);
      if (!el) continue;
      const src = data.source || source || "snippet";
      injectBadge(el, createBadge(
        data.score ?? data.overall_score ?? 0,
        data.confidence,
        src,
        data.raw,
        data.chars,
        data
      ));
      count++;
    }
    const ms = Math.round((performance.now() - t0) * 100) / 100;
    console.log(`[G] inject: ${count} ${source || "snippet"} badges in ${ms}ms`);
  }

  function removeLoadingBadges(ids) {
    for (const id of ids) {
      const el = document.querySelector(`[${PROCESSED_ATTR}="${id}"]`);
      if (!el) continue;
      const badge = el.querySelector(".sloptotal-loading");
      if (badge) badge.remove();
    }
  }

  function scanPage() {
    const tScan = performance.now();
    chrome.storage.sync.get({ googleEnabled: true }, (settings) => {
      if (!settings.googleEnabled) return;

      const snippets = extractSnippets();
      if (snippets.length === 0 || scanInFlight) return;

      const allIds = snippets.map((s) => s.id);
      for (const s of snippets) injectBadge(s.element, createLoadingBadge());

      const payload = snippets.map(({ id, text, url }) => ({ id, text, url }));

      scanInFlight = true;
      const tMsg = performance.now();
      chrome.runtime.sendMessage({ type: "scanSnippets", snippets: payload }, (response) => {
        scanInFlight = false;
        const msgMs = Math.round(performance.now() - tMsg);
        if (chrome.runtime.lastError) {
          console.warn(`[G] sendMessage error after ${msgMs}ms:`, chrome.runtime.lastError.message);
          removeLoadingBadges(allIds);
          return;
        }

        const cached = Object.keys(response?.results || {}).length;
        console.log(`[G] sendMessage reply: ${msgMs}ms | ${cached} cached, ${response?.pending || 0} pending`);

        if (response?.results && cached > 0) {
          injectBadges(response.results);
        }
        if (!response?.pending || response.pending === 0) {
          const answered = new Set(Object.keys(response?.results || {}));
          removeLoadingBadges(allIds.filter((id) => !answered.has(id)));
        }
      });
    });
  }

  function debouncedScan() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(scanPage, 300);
  }

  // Listen for fresh results from background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "snippetResults" && message.results) {
      console.log(`[G] fresh snippet results: ${Object.keys(message.results).length} snippets`);
      injectBadges(message.results, "snippet");
    } else if (message.type === "urlResults" && message.results) {
      console.log(`[G] URL content results: ${Object.keys(message.results).length} pages`);
      injectBadges(message.results, "url_content");
    } else if (message.type === "snippetError" && message.pendingIds) {
      console.warn(`[G] snippet error for ${message.pendingIds.length} ids: ${message.error}`);
      removeLoadingBadges(message.pendingIds);
    }
  });

  console.log("[G] Content script loaded");
  scanPage();

  setTimeout(() => {
    if (!document.querySelector(`[${PROCESSED_ATTR}]`)) {
      console.log("[G] Retry scan (no results from first attempt)");
      scanPage();
    }
  }, 1000);

  const observer = new MutationObserver((mutations) => {
    let hasNew = false;
    for (const m of mutations) {
      if (m.addedNodes.length === 0) continue;
      for (const node of m.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (node.matches?.(".g, .hlcw0c, .tF2Cxc, [data-hveid]") || node.querySelector?.(".g, .hlcw0c, .tF2Cxc, h3")) {
          hasNew = true; break;
        }
      }
      if (hasNew) break;
    }
    if (hasNew) debouncedScan();
  });

  const searchContainer = document.getElementById("search") || document.getElementById("rso") || document.body;
  observer.observe(searchContainer, { childList: true, subtree: true });
})();
