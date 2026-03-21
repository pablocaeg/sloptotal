// SlopTotal Context Menu Result Overlay
// Shows a floating result badge near the selected text

(function () {
  let overlay = null;

  function removeOverlay() {
    if (overlay) {
      overlay.remove();
      overlay = null;
    }
  }

  function createOverlay(score, verdict, data) {
    removeOverlay();

    overlay = document.createElement("div");
    overlay.id = "sloptotal-overlay";

    // Position near selection
    const sel = window.getSelection();
    let top = 10, left = 10;
    if (sel && sel.rangeCount > 0) {
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      top = rect.bottom + window.scrollY + 8;
      left = rect.left + window.scrollX;
    }

    // Color based on verdict
    const colors = {
      clean: { bg: "#e6f4eb", border: "#2d8a4e", text: "#1a3a24", label: "HUMAN" },
      mixed: { bg: "#fdf4e0", border: "#c98b1d", text: "#5a3e08", label: "MIXED" },
      ai:    { bg: "#fce8e9", border: "#b5282e", text: "#4a1012", label: "AI" },
    };
    const c = colors[verdict] || colors.mixed;

    overlay.style.cssText = `
      position: absolute;
      top: ${top}px;
      left: ${left}px;
      z-index: 2147483647;
      background: ${c.bg};
      border: 2px solid ${c.border};
      border-radius: 10px;
      padding: 12px 16px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      color: ${c.text};
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
      max-width: 360px;
      line-height: 1.4;
      cursor: default;
    `;

    // Build inner HTML
    let html = `
      <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
        <strong style="font-family:Georgia,serif;">SLOP</strong><strong style="font-family:'SF Mono',Consolas,monospace;font-weight:400;">TOTAL</strong>
        <span style="background:${c.border}; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700;">${c.label}</span>
        <span style="font-size:18px; font-weight:700; margin-left:auto;">${Math.round(score)}%</span>
      </div>
    `;

    if (data.paragraphs && data.paragraphs.length > 1) {
      // Paragraph heat map
      html += `<div style="font-size:11px; color:#7a756b; margin-bottom:4px;">${data.paragraph_count} paragraphs (${data.ai_paragraph_count} flagged)</div>`;
      html += `<div style="display:flex; gap:2px; margin-bottom:4px;">`;
      for (const p of data.paragraphs) {
        const pColor = p.score > 65 ? "#b5282e" : p.score > 35 ? "#c98b1d" : "#2d8a4e";
        const width = Math.max(20, (p.char_count / data.paragraphs.reduce((a, b) => a + b.char_count, 0)) * 100);
        html += `<div title="P${p.index + 1}: ${p.score}% ${p.verdict}" style="height:6px; flex:${p.char_count}; background:${pColor}; border-radius:3px;"></div>`;
      }
      html += `</div>`;
    } else if (data.engines) {
      // Engine breakdown for quick-score
      html += `<div style="font-size:11px; color:#7a756b; margin-bottom:2px;">`;
      html += data.engines
        .map((e) => {
          const eColor = e.score > 65 ? "#b5282e" : e.score > 35 ? "#c98b1d" : "#2d8a4e";
          return `<span style="color:${eColor}">${e.engine.replace("classifier_", "")}: ${e.score}%</span>`;
        })
        .join(" &middot; ");
      html += `</div>`;
    }

    html += `<div style="font-size:10px; color:#a09a8e; margin-top:4px;">Click to dismiss &middot; ${data.elapsed_ms ? Math.round(data.elapsed_ms) + "ms" : ""}</div>`;

    overlay.innerHTML = html;

    // Dismiss on click
    overlay.addEventListener("click", removeOverlay);

    document.body.appendChild(overlay);

    // Auto-dismiss after 15 seconds
    setTimeout(removeOverlay, 15000);
  }

  // Listen for context menu results from background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "contextMenuResult") {
      createOverlay(message.score, message.verdict, message.data);
    }
  });

  // Dismiss overlay when clicking elsewhere
  document.addEventListener("click", (e) => {
    if (overlay && !overlay.contains(e.target)) {
      removeOverlay();
    }
  });

  // --- DOM Feature Extraction (Phase C) ---
  // Extracts structural features from the rendered DOM for AI detection.
  // These are more accurate than server-side HTML parsing because we see
  // the final rendered state after JS execution.

  function extractDOMFeatures() {
    // Skip SERPs — google.js handles those
    if (location.hostname.includes("google.com") && location.pathname === "/search") return null;

    const liCount = document.querySelectorAll("li").length;

    const headings = document.querySelectorAll("h1, h2, h3, h4, h5, h6");
    const headingCount = headings.length;

    // Heading→list patterns: heading immediately followed by <ul> or <ol>
    let headingListCount = 0;
    for (const h of headings) {
      let sibling = h.nextElementSibling;
      if (sibling && (sibling.tagName === "UL" || sibling.tagName === "OL")) {
        headingListCount++;
      }
    }

    // Paragraphs
    const paragraphs = document.querySelectorAll("p");
    const paraCount = paragraphs.length;
    const paraWordCounts = [];
    for (const p of paragraphs) {
      const text = p.textContent.trim();
      if (text.length > 0) {
        paraWordCounts.push(text.split(/\s+/).length);
      }
    }
    // Median paragraph word count
    let medianParaWords = 0;
    if (paraWordCounts.length > 0) {
      paraWordCounts.sort((a, b) => a - b);
      const mid = Math.floor(paraWordCounts.length / 2);
      medianParaWords = paraWordCounts.length % 2 !== 0
        ? paraWordCounts[mid]
        : Math.round((paraWordCounts[mid - 1] + paraWordCounts[mid]) / 2);
    }

    // Content-to-boilerplate ratio
    // Use <main>, <article>, or [role="main"] as content area; fall back to <body>
    const contentEl =
      document.querySelector("main") ||
      document.querySelector("article") ||
      document.querySelector('[role="main"]');
    const contentLen = contentEl ? contentEl.textContent.trim().length : 0;
    const totalLen = document.body ? document.body.textContent.trim().length : 1;
    const contentRatio = totalLen > 0 ? Math.round((contentLen / totalLen) * 100) / 100 : 0;

    return {
      li_count: liCount,
      heading_count: headingCount,
      heading_list_count: headingListCount,
      paragraph_count: paraCount,
      median_para_words: medianParaWords,
      content_ratio: contentRatio,
    };
  }

  // Send DOM features to background after page load
  function sendDOMFeatures() {
    const url = location.href;
    if (!url.startsWith("http")) return;

    const features = extractDOMFeatures();
    if (!features) return;

    chrome.runtime.sendMessage({
      type: "domFeatures",
      url: url,
      features: features,
    });
  }

  // Extract after a short delay to let dynamic content render
  if (document.readyState === "complete") {
    setTimeout(sendDOMFeatures, 500);
  } else {
    window.addEventListener("load", () => setTimeout(sendDOMFeatures, 500));
  }
})();
