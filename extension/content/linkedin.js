// SlopTotal LinkedIn Feed Content Script
// Cache-first: cached badges appear instantly, fresh results stream in after

(function () {
  "use strict";

  const PROCESSED_ATTR = "data-sloptotal-processed";
  const MIN_TEXT_LENGTH = 50;
  let debounceTimer = null;
  let scanInFlight = false;

  // Store result data for click-to-expand
  const resultData = new Map();

  // --- Calibration utilities (mirrors server _compute_fakespot_score thresholds) ---

  function calibrateFakespot(raw) {
    if (raw >= 0.85) return 75 + ((raw - 0.85) / 0.15) * 15;
    if (raw >= 0.65) return 55 + ((raw - 0.65) / 0.20) * 20;
    if (raw >= 0.45) return 35 + ((raw - 0.45) / 0.20) * 20;
    if (raw >= 0.25) return 15 + ((raw - 0.25) / 0.20) * 20;
    return (raw / 0.25) * 15;
  }

  function interpretFakespot(calibrated) {
    if (calibrated >= 75) return "Strong AI signals detected";
    if (calibrated >= 55) return "Moderate AI signals";
    if (calibrated >= 35) return "Weak AI signals";
    return "Minimal AI signals";
  }

  function interpretStructural(score) {
    if (score >= 50) return "Strong AI writing patterns";
    if (score >= 25) return "Some AI-like patterns";
    if (score >= 10) return "Minor pattern signals";
    return "Natural writing style";
  }

  function signalLabel(engine) {
    const labels = {
      linguistic: "AI phrases", formulaic: "Formulaic structure",
      structural: "Text structure", vocabulary: "Vocabulary diversity",
      readability: "Reading level", sentiment: "Tone analysis",
    };
    return labels[engine] || engine;
  }

  // --- Sponsored post detection & hiding ---

  function hideSponsored() {
    const posts = document.querySelectorAll(
      '.feed-shared-update-v2, .occludable-update, div[data-urn]'
    );
    let hidden = 0;
    for (const post of posts) {
      if (post.dataset.sloptotalSponsored) continue;
      const labels = post.querySelectorAll(
        '.update-components-actor__sub-description, ' +
        '.feed-shared-actor__sub-description, ' +
        '.update-components-actor__description, ' +
        'span.visually-hidden'
      );
      let isSponsored = false;
      for (const lbl of labels) {
        const t = lbl.textContent.trim().toLowerCase();
        if (t === "promoted" || t === "sponsored" || t.includes("promoted")) {
          isSponsored = true;
          break;
        }
      }
      if (isSponsored) {
        post.dataset.sloptotalSponsored = "1";
        post.style.display = "none";
        hidden++;
      }
    }
    if (hidden > 0) console.log(`[LI] hidden ${hidden} sponsored posts`);
    return hidden;
  }

  // --- Post extraction ---

  function extractPosts() {
    const t0 = performance.now();
    const postSelectors = [
      '.feed-shared-update-v2:not([data-sloptotal-processed])',
      '.occludable-update:not([data-sloptotal-processed])',
      'div[data-urn]:not([data-sloptotal-processed])',
      '.reusable-search__result-container:not([data-sloptotal-processed])',
      '.search-results__cluster-content li:not([data-sloptotal-processed])',
    ];
    const posts = [];
    const seen = new Set();

    for (const selector of postSelectors) {
      document.querySelectorAll(selector).forEach((el) => {
        if (seen.has(el)) return;
        seen.add(el);
        if (el.dataset.sloptotalSponsored) return;
        const textEl = findTextEl(el);
        if (!textEl) return;
        const text = textEl.textContent.trim();
        if (text.length < MIN_TEXT_LENGTH) return;
        const id = `li-${Date.now()}-${posts.length}`;
        el.setAttribute(PROCESSED_ATTR, id);
        posts.push({ id, text, element: el, textEl });
      });
    }

    const ms = Math.round((performance.now() - t0) * 100) / 100;
    if (posts.length > 0) {
      const chars = posts.map((p) => p.text.length);
      console.log(
        `[LI] extract: ${posts.length} posts in ${ms}ms | ` +
        `chars: [${chars.join(", ")}] total=${chars.reduce((a, b) => a + b, 0)}`
      );
    }
    return posts;
  }

  // --- Badge creation ---

  function createBadge(score, confidence, raw, chars, data) {
    const badge = document.createElement("div");
    badge.className = "sloptotal-li-badge";
    let color, label;
    if (score >= 75) { color = "sloptotal-li-high"; label = "Likely AI"; }
    else if (score >= 50) { color = "sloptotal-li-medium"; label = "Maybe AI"; }
    else if (score >= 25) { color = "sloptotal-li-low"; label = "Probably Human"; }
    else { color = "sloptotal-li-safe"; label = "Likely Human"; }
    badge.classList.add(color);

    const pct = Math.round(score);
    badge.innerHTML = `
      <span class="sloptotal-li-icon"><span class="sloptotal-li-dot"></span></span>
      <span class="sloptotal-li-label">${label}</span>
      <span class="sloptotal-li-bar"><span class="sloptotal-li-bar-fill" style="width:${pct}%"></span></span>
      <span class="sloptotal-li-score">${pct}%</span>
      <span class="sloptotal-li-expand">&#9660;</span>
    `;
    badge.title = "Click for details";

    // Click to expand/collapse detail panel
    badge.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      const existing = badge.parentElement?.querySelector(".sloptotal-li-details");
      if (existing) {
        existing.remove();
        badge.querySelector(".sloptotal-li-expand").innerHTML = "&#9660;";
        return;
      }
      badge.querySelector(".sloptotal-li-expand").innerHTML = "&#9650;";
      const details = document.createElement("div");
      details.className = "sloptotal-li-details " + color;

      const isUrl = data?.source === "url_content";
      // Fakespot calibrated value: server provides this in score (snippets) or ml_score (URLs)
      const fsCalibrated = isUrl && data?.ml_score != null
        ? Math.round(data.ml_score)
        : Math.round(score);
      const fsRaw = raw?.fakespot;
      const charText = chars ? `${chars} chars` : "";
      const confText = confidence || "";
      const metaParts = [charText, confText].filter(Boolean).join(" \u00B7 ");

      const row = (name, val, pct) => `
        <div class="sloptotal-li-detail-row">
          <span class="sloptotal-li-detail-engine">${name}</span>
          <div class="sloptotal-li-detail-bar"><div class="sloptotal-li-detail-fill" style="width:${Math.min(pct, 100)}%"></div></div>
          <span class="sloptotal-li-detail-val">${val}%</span>
        </div>`;

      let html = `<div class="sloptotal-li-detail-section-label">Fakespot AI Detector</div>`;
      html += row("Fakespot", fsCalibrated, fsCalibrated);
      html += `<div class="sloptotal-li-detail-signal">${interpretFakespot(fsCalibrated)}</div>`;

      // Show raw → calibrated explanation when they differ significantly
      if (fsRaw != null) {
        const rawPct = Math.round(fsRaw * 100);
        if (Math.abs(fsCalibrated - rawPct) > 10) {
          html += `<div class="sloptotal-li-detail-signal" style="opacity:0.55">Raw model output: ${rawPct}% \u2192 calibrated to ${fsCalibrated}%</div>`;
        }
      }

      // Structural / writing patterns section (URL scans only)
      const struct = data?.structural;
      if (struct && struct.score != null) {
        html += `<div class="sloptotal-li-detail-divider"></div>`;
        html += `<div class="sloptotal-li-detail-section-label">Writing Patterns</div>`;
        html += row("Patterns", Math.round(struct.score), struct.score);
        html += `<div class="sloptotal-li-detail-signal">${interpretStructural(struct.score)}</div>`;

        const sigs = struct.signals || {};
        const flagged = Object.entries(sigs)
          .filter(([k, v]) => v > 0.15 && !k.startsWith("html_"))
          .sort(([, a], [, b]) => b - a)
          .slice(0, 3);
        if (flagged.length > 0) {
          const names = flagged.map(([k]) => signalLabel(k)).join(", ");
          html += `<div class="sloptotal-li-detail-signal">Signals: ${names}</div>`;
        }

        // Blend explanation
        if (data?.ml_score != null && Math.round(data.ml_score) !== Math.round(score)) {
          html += `<div class="sloptotal-li-detail-blend">Fakespot ${Math.round(data.ml_score)}% + Patterns ${Math.round(struct.score)}% \u2192 <strong>${Math.round(score)}%</strong></div>`;
        }
      }

      html += `<div class="sloptotal-li-detail-meta">${metaParts}</div>`;
      details.innerHTML = html;
      badge.insertAdjacentElement("afterend", details);
    });

    return badge;
  }

  function createLoadingBadge() {
    const badge = document.createElement("div");
    badge.className = "sloptotal-li-badge sloptotal-li-loading";
    badge.innerHTML = `<span class="sloptotal-li-icon"><span class="sloptotal-li-dot"></span></span><span class="sloptotal-li-label">Scanning...</span>`;
    return badge;
  }

  function findTextEl(el) {
    return el.querySelector(".feed-shared-text") ||
      el.querySelector(".feed-shared-update-v2__description") ||
      el.querySelector('[data-test-id="main-feed-activity-card__commentary"]') ||
      el.querySelector(".update-components-text") ||
      el.querySelector(".search-result__snippets") ||
      el.querySelector(".break-words");
  }

  function injectBadge(el, badge) {
    const existing = el.querySelector(".sloptotal-li-badge");
    if (existing) {
      const details = existing.parentElement?.querySelector(".sloptotal-li-details");
      if (details) details.remove();
      existing.replaceWith(badge);
      return;
    }
    const textEl = findTextEl(el);
    if (textEl) textEl.parentElement.insertBefore(badge, textEl);
    else el.prepend(badge);
  }

  function injectBadges(results) {
    const t0 = performance.now();
    let count = 0;
    for (const [id, data] of Object.entries(results)) {
      const el = document.querySelector(`[${PROCESSED_ATTR}="${id}"]`);
      if (!el) continue;
      resultData.set(id, data);
      injectBadge(el, createBadge(
        data.score ?? data.overall_score ?? 0,
        data.confidence,
        data.raw,
        data.chars,
        data
      ));
      count++;
    }
    const ms = Math.round((performance.now() - t0) * 100) / 100;
    console.log(`[LI] inject: ${count} badges in ${ms}ms`);
  }

  function removeLoadingBadges(ids) {
    for (const id of ids) {
      const el = document.querySelector(`[${PROCESSED_ATTR}="${id}"]`);
      if (!el) continue;
      const badge = el.querySelector(".sloptotal-li-loading");
      if (badge) badge.remove();
    }
  }

  function scanPage() {
    chrome.storage.sync.get({ linkedinEnabled: true, hideSponsored: true }, (settings) => {
      if (!settings.linkedinEnabled) return;
      if (settings.hideSponsored) hideSponsored();
      const posts = extractPosts();
      if (posts.length === 0 || scanInFlight) return;

      const allIds = posts.map((p) => p.id);
      for (const p of posts) injectBadge(p.element, createLoadingBadge());

      const payload = posts.map(({ id, text }) => ({ id, text, url: "" }));

      scanInFlight = true;
      const tMsg = performance.now();
      chrome.runtime.sendMessage({ type: "scanSnippets", snippets: payload }, (response) => {
        scanInFlight = false;
        const msgMs = Math.round(performance.now() - tMsg);
        if (chrome.runtime.lastError) {
          console.warn(`[LI] sendMessage error after ${msgMs}ms:`, chrome.runtime.lastError.message);
          removeLoadingBadges(allIds);
          return;
        }

        const cached = Object.keys(response?.results || {}).length;
        console.log(`[LI] sendMessage reply: ${msgMs}ms | ${cached} cached, ${response?.pending || 0} pending`);

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
      console.log(`[LI] fresh results: ${Object.keys(message.results).length} posts`);
      injectBadges(message.results);
    } else if (message.type === "snippetError" && message.pendingIds) {
      console.warn(`[LI] snippet error for ${message.pendingIds.length} ids: ${message.error}`);
      removeLoadingBadges(message.pendingIds);
    }
  });

  console.log("[LI] Content script loaded");
  setTimeout(scanPage, 500);

  const observer = new MutationObserver((mutations) => {
    let hasNew = false;
    for (const m of mutations) {
      if (m.addedNodes.length === 0) continue;
      for (const node of m.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (node.matches?.('.feed-shared-update-v2, .occludable-update, div[data-urn], .reusable-search__result-container') ||
            node.querySelector?.('.feed-shared-update-v2, .occludable-update, div[data-urn], .reusable-search__result-container')) {
          hasNew = true; break;
        }
      }
      if (hasNew) break;
    }
    if (hasNew) debouncedScan();
  });

  const feedContainer = document.querySelector(".scaffold-finite-scroll__content") ||
    document.querySelector(".search-results-container") ||
    document.querySelector("main") || document.body;
  observer.observe(feedContainer, { childList: true, subtree: true });
})();
