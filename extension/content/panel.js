// SlopTotal Floating Panel — Full 23-engine analysis on every page
// Uses Shadow DOM for CSS isolation, SSE relay via background.js

(function () {
  "use strict";

  const proto = location.protocol;
  if (proto !== "http:" && proto !== "https:") return;

  // --- Utilities ---

  function getBodyText() {
    return document.body ? (document.body.innerText || "").trim() : "";
  }

  function hashUrl(url) {
    let h = 5381;
    for (let i = 0; i < url.length; i++) h = ((h << 5) + h + url.charCodeAt(i)) & 0xffffffff;
    return "panel_" + h.toString(36);
  }

  function escapeHtml(str) {
    const d = document.createElement("span");
    d.textContent = str;
    return d.innerHTML;
  }

  // --- Engine grouping (matches actual server keys from analyzer.py _engines) ---

  const ENGINE_GROUPS = {
    primary: {
      label: "AI Detection",
      keys: ["classifier_fakespot"],
    },
    ml: {
      label: "ML Classifiers",
      keys: [
        "classifier_tmr", "classifier_remodetect", "classifier_e5",
        "classifier_bert_raid", "classifier_openai", "classifier_chatgpt",
        "classifier_desklib", "classifier_superannotate",
      ],
    },
    statistical: {
      label: "Statistical Analysis",
      keys: [
        "binoculars", "fast_detectgpt", "perplexity", "cross_perplexity",
        "gltr", "log_rank", "diveye", "burstiness",
      ],
    },
    heuristic: {
      label: "Writing Patterns",
      keys: ["linguistic", "structural", "vocabulary", "formulaic", "readability", "sentiment"],
    },
  };

  const ALL_ENGINE_KEYS = Object.values(ENGINE_GROUPS).flatMap((g) => g.keys);

  // --- Display names ---

  const ENGINE_NAMES = {
    classifier_fakespot: "Fakespot",
    classifier_tmr: "TMR",
    classifier_remodetect: "ReMoDetect",
    classifier_e5: "E5",
    classifier_bert_raid: "BERT-RAID",
    classifier_openai: "OpenAI",
    classifier_chatgpt: "ChatGPT",
    classifier_desklib: "Desklib",
    classifier_superannotate: "SuperAnnot.",
    binoculars: "Binoculars",
    fast_detectgpt: "DetectGPT",
    perplexity: "Perplexity",
    cross_perplexity: "Cross-PPL",
    gltr: "GLTR",
    log_rank: "Log Rank",
    diveye: "DivEye",
    burstiness: "Burstiness",
    linguistic: "Linguistic",
    structural: "Structural",
    vocabulary: "Vocabulary",
    formulaic: "Formulaic",
    readability: "Readability",
    sentiment: "Sentiment",
  };

  function displayName(key) {
    return ENGINE_NAMES[key] || key.replace("classifier_", "").replace(/_/g, " ");
  }

  // --- Fakespot calibrated score (mirrors server _compute_fakespot_score) ---

  function calibrateFakespot(raw) {
    let score;
    if (raw >= 0.85) score = 75 + ((raw - 0.85) / 0.15) * 15;
    else if (raw >= 0.65) score = 55 + ((raw - 0.65) / 0.20) * 20;
    else if (raw >= 0.45) score = 35 + ((raw - 0.45) / 0.20) * 20;
    else if (raw >= 0.25) score = 15 + ((raw - 0.25) / 0.20) * 20;
    else score = (raw / 0.25) * 15;
    return Math.round(Math.min(100, Math.max(0, score)));
  }

  // --- Score colors ---

  function scoreColor(pct) {
    if (pct > 65) return "#b5282e";
    if (pct > 40) return "#c98b1d";
    return "#2d8a4e";
  }

  // --- Client-side page classifier (mirrors server page_classifier.py) ---

  function classifyPage() {
    const text = getBodyText();
    const charCount = text.length;

    if (charCount < 200) return { type: "short", label: "Short page", scoreable: false };

    const wordCount = text.split(/\s+/).length;

    // DOM feature extraction
    const paragraphs = document.querySelectorAll("p").length;
    const listItems = document.querySelectorAll("li").length;
    const navLinks = document.querySelectorAll("nav a, header a").length;
    const boldTags = document.querySelectorAll("b, strong").length;
    const forms = document.querySelectorAll("form").length;
    const codeBlocks = document.querySelectorAll("pre, code").length;

    // Hub: high link/list density, low prose
    if (wordCount > 0) {
      const liDensity = listItems / wordCount;
      if (liDensity > 0.5 && paragraphs < 5)
        return { type: "hub", label: "Hub page", scoreable: false };
    }
    if (navLinks > 20 && paragraphs < 5)
      return { type: "hub", label: "Hub page", scoreable: false };

    // Landing: low text, high formatting
    if (charCount < 800 && paragraphs < 8 && (boldTags > 5 || forms > 1))
      return { type: "landing", label: "Landing page", scoreable: false };

    // Reference: code-heavy
    const codeFences = (text.match(/```|~~~/g) || []).length;
    const techPatterns = (text.match(/\b(?:param|returns?|type|default|args?|kwargs?|raises?|str|int|float|bool|None|True|False|dict|list|tuple)\b/g) || []).length;
    const colonDensity = (text.match(/:/g) || []).length / Math.max(wordCount, 1);

    if (codeBlocks > 3 || (colonDensity > 0.04 && codeBlocks >= 1) ||
        (techPatterns > 15 && codeBlocks >= 1) || codeFences >= 4)
      return { type: "reference", label: "Documentation", scoreable: true };

    return { type: "article", label: "Article", scoreable: true };
  }

  // --- Gauge SVG ---

  const GAUGE_R = 40;
  const GAUGE_CIRC = 2 * Math.PI * GAUGE_R;

  function gaugeSVG() {
    return `<svg viewBox="0 0 100 100" width="90" height="90" class="st-gauge-svg">
      <circle cx="50" cy="50" r="${GAUGE_R}" fill="none" stroke="var(--st-track)" stroke-width="8"
        stroke-linecap="round" transform="rotate(-90 50 50)"
        stroke-dasharray="${GAUGE_CIRC}" stroke-dashoffset="0"/>
      <circle cx="50" cy="50" r="${GAUGE_R}" fill="none" stroke-width="8" stroke-linecap="round"
        class="st-gauge-arc" transform="rotate(-90 50 50)"
        stroke-dasharray="${GAUGE_CIRC}" stroke-dashoffset="${GAUGE_CIRC}"/>
      <text x="50" y="54" text-anchor="middle" class="st-gauge-num">0</text>
    </svg>`;
  }

  // --- Shadow DOM Styles ---

  const STYLES = `
    :host { all: initial; }
    * { box-sizing: border-box; margin: 0; padding: 0; }

    :host {
      --st-bg: #faf8f3;
      --st-border: #e8e4dd;
      --st-track: #ece8e1;
      --st-text: #5a5549;
      --st-text2: #8a8479;
      --st-text3: #a39e95;
      --st-hover: #ece8e1;
      --st-shadow: rgba(0,0,0,0.08);
      --st-shadow2: rgba(0,0,0,0.12);
      --st-red: #b5282e;
      --st-yellow: #c98b1d;
      --st-green: #2d8a4e;
      --st-green-bg: rgba(45,138,78,0.08);
      --st-yellow-bg: rgba(201,139,29,0.08);
      --st-red-bg: rgba(181,40,46,0.08);
      --st-grey: #8a8479;
      --st-grey-bg: rgba(138,132,121,0.08);
    }

    @media (prefers-color-scheme: dark) {
      :host {
        --st-bg: #1e1d1b;
        --st-border: #3a3835;
        --st-track: #2a2927;
        --st-text: #c5c0b8;
        --st-text2: #8a8479;
        --st-text3: #6a6560;
        --st-hover: #2a2927;
        --st-shadow: rgba(0,0,0,0.3);
        --st-shadow2: rgba(0,0,0,0.4);
        --st-green-bg: rgba(45,138,78,0.12);
        --st-yellow-bg: rgba(201,139,29,0.12);
        --st-red-bg: rgba(181,40,46,0.12);
        --st-grey-bg: rgba(138,132,121,0.12);
      }
      .st-gauge-num { fill: var(--st-text) !important; }
    }

    /* --- Pill --- */
    .st-pill {
      display: inline-flex; align-items: center; gap: 7px;
      padding: 8px 14px 8px 10px;
      background: var(--st-bg); border: 1.5px solid var(--st-border);
      border-radius: 22px; cursor: pointer;
      font: 600 11.5px/1 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: var(--st-text);
      box-shadow: 0 2px 12px var(--st-shadow);
      transition: all 0.2s ease; user-select: none; white-space: nowrap;
      margin-bottom: 8px;
    }
    .st-pill:hover { box-shadow: 0 4px 16px var(--st-shadow2); transform: translateY(-1px); }
    .st-pill-tag {
      font-size: 9px; font-weight: 700; letter-spacing: 0.5px;
      padding: 1px 5px; border-radius: 6px;
      text-transform: uppercase;
    }
    .st-pill-tag.red { background: var(--st-red-bg); color: var(--st-red); }
    .st-pill-tag.yellow { background: var(--st-yellow-bg); color: var(--st-yellow); }
    .st-pill-tag.green { background: var(--st-green-bg); color: var(--st-green); }
    .st-pill-tag.grey { background: var(--st-grey-bg); color: var(--st-grey); }

    .st-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: var(--st-text3); flex-shrink: 0;
      box-shadow: 0 0 0 2px rgba(0,0,0,0.06);
    }
    .st-dot.scanning { background: var(--st-yellow); animation: st-pulse 1.2s ease-in-out infinite; }
    .st-dot.green { background: var(--st-green); }
    .st-dot.yellow { background: var(--st-yellow); }
    .st-dot.red { background: var(--st-red); }
    .st-dot.grey { background: var(--st-grey); }
    .st-dot.error { background: var(--st-red); }

    @keyframes st-pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(0.8); }
    }

    .st-reopen {
      display: inline-flex; align-items: center; justify-content: center;
      width: 28px; height: 28px;
      background: var(--st-bg); border: 1.5px solid var(--st-border);
      border-radius: 50%; cursor: pointer;
      box-shadow: 0 2px 8px var(--st-shadow); transition: all 0.2s ease;
    }
    .st-reopen:hover { box-shadow: 0 4px 12px var(--st-shadow2); }
    .st-reopen .st-dot { width: 10px; height: 10px; }

    /* --- Panel --- */
    .st-panel {
      display: none; flex-direction: column;
      width: 320px; max-height: 500px;
      background: var(--st-bg); border: 1.5px solid var(--st-border);
      border-radius: 12px;
      box-shadow: 0 8px 32px var(--st-shadow2);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      overflow: hidden; animation: st-slideUp 0.2s ease;
    }
    .st-panel.open { display: flex; }
    @keyframes st-slideUp {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .st-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 14px; border-bottom: 1px solid var(--st-border);
    }
    .st-brand { font-size: 11px; font-weight: 700; letter-spacing: 1.5px; color: var(--st-text); }
    .st-brand-slop { color: var(--st-red); }
    .st-header-btns { display: flex; gap: 4px; }
    .st-header-btn {
      width: 24px; height: 24px; border: none; background: transparent;
      cursor: pointer; border-radius: 6px; color: var(--st-text3);
      display: flex; align-items: center; justify-content: center;
      transition: background 0.15s, color 0.15s;
    }
    .st-header-btn:hover { background: var(--st-hover); color: var(--st-text); }
    .st-header-btn svg { width: 14px; height: 14px; }

    /* --- Gauge --- */
    .st-gauge-section {
      display: flex; align-items: center; gap: 14px; padding: 14px;
    }
    .st-gauge-svg { flex-shrink: 0; }
    .st-gauge-arc {
      stroke: var(--st-track);
      transition: stroke-dashoffset 0.6s ease, stroke 0.3s ease;
    }
    .st-gauge-num {
      font-size: 22px; font-weight: 700; fill: var(--st-text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .st-gauge-info { display: flex; flex-direction: column; gap: 3px; }
    .st-gauge-score { font-size: 15px; font-weight: 700; color: var(--st-text); }
    .st-gauge-verdict { font-size: 12px; font-weight: 600; color: var(--st-text2); }
    .st-gauge-flagged { font-size: 10.5px; color: var(--st-text3); }

    /* --- Primary (Fakespot) section --- */
    .st-primary {
      padding: 10px 14px; border-top: 1px solid var(--st-border);
    }
    .st-primary-label {
      font-size: 9px; font-weight: 700; letter-spacing: 1px;
      color: var(--st-text3); text-transform: uppercase; margin-bottom: 6px;
    }
    .st-primary-row {
      display: flex; align-items: center; gap: 8px;
    }
    .st-primary-name {
      font-size: 12px; font-weight: 700; color: var(--st-text); width: 68px; flex-shrink: 0;
    }
    .st-primary-bar {
      flex: 1; height: 8px; background: var(--st-track); border-radius: 4px; overflow: hidden;
    }
    .st-primary-fill {
      height: 100%; border-radius: 4px; transition: width 0.5s ease;
    }
    .st-primary-val {
      font-size: 13px; font-weight: 700; width: 40px; text-align: right; flex-shrink: 0;
    }
    .st-primary-note {
      font-size: 10px; color: var(--st-text3); margin-top: 4px;
    }
    .st-primary.pending .st-primary-bar {
      background: linear-gradient(90deg, var(--st-track) 25%, var(--st-bg) 50%, var(--st-track) 75%);
      background-size: 200% 100%; animation: st-shimmer 1.5s ease-in-out infinite;
    }

    /* --- Engine groups --- */
    .st-groups { flex: 1; overflow-y: auto; max-height: 260px; }
    .st-groups::-webkit-scrollbar { width: 4px; }
    .st-groups::-webkit-scrollbar-track { background: transparent; }
    .st-groups::-webkit-scrollbar-thumb { background: var(--st-border); border-radius: 2px; }

    .st-group { border-top: 1px solid var(--st-border); }
    .st-group-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 14px; cursor: pointer; user-select: none;
      transition: background 0.15s;
    }
    .st-group-header:hover { background: var(--st-hover); }
    .st-group-label {
      font-size: 9px; font-weight: 700; letter-spacing: 1px;
      color: var(--st-text3); text-transform: uppercase;
    }
    .st-group-right { display: flex; align-items: center; gap: 6px; }
    .st-group-count { font-size: 10px; font-weight: 600; color: var(--st-text2); }
    .st-group-dots { display: flex; gap: 3px; }
    .st-gdot {
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--st-track); transition: background 0.3s;
    }
    .st-gdot.flagged { background: var(--st-red); }
    .st-gdot.clean { background: var(--st-green); }
    .st-gdot.pending { background: var(--st-track); }
    .st-group-chevron {
      font-size: 10px; color: var(--st-text3);
      transition: transform 0.2s; display: inline-block;
    }
    .st-group-chevron.open { transform: rotate(90deg); }

    .st-group-body { display: none; padding: 0 0 4px; }
    .st-group-body.open { display: block; }

    .st-engine-row {
      display: flex; align-items: center; padding: 3px 14px; gap: 8px;
      animation: st-fadeIn 0.3s ease;
    }
    .st-engine-row.pending { opacity: 0.35; }
    @keyframes st-fadeIn {
      from { opacity: 0; transform: translateX(-4px); }
      to { opacity: 1; transform: translateX(0); }
    }
    .st-engine-name {
      width: 68px; font-size: 10px; font-weight: 600; color: var(--st-text);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0;
    }
    .st-engine-bar {
      flex: 1; height: 5px; background: var(--st-track); border-radius: 3px; overflow: hidden;
    }
    .st-engine-fill { height: 100%; border-radius: 3px; transition: width 0.4s ease; }
    .st-engine-val {
      width: 34px; text-align: right; font-size: 10px; font-weight: 600;
      color: var(--st-text); flex-shrink: 0;
    }
    .st-engine-row.pending .st-engine-bar {
      background: linear-gradient(90deg, var(--st-track) 25%, var(--st-bg) 50%, var(--st-track) 75%);
      background-size: 200% 100%; animation: st-shimmer 1.5s ease-in-out infinite;
    }
    @keyframes st-shimmer {
      from { background-position: 200% 0; }
      to { background-position: -200% 0; }
    }

    /* --- Non-scoreable info --- */
    .st-info-section {
      padding: 16px 14px; text-align: center;
    }
    .st-info-type {
      font-size: 14px; font-weight: 700; color: var(--st-text);
      margin-bottom: 4px;
    }
    .st-info-desc {
      font-size: 11.5px; color: var(--st-text2); line-height: 1.4;
    }

    /* --- Meta bar --- */
    .st-meta {
      display: flex; gap: 6px; padding: 8px 14px; flex-wrap: wrap;
      border-top: 1px solid var(--st-border); font-size: 10px; color: var(--st-text3);
    }
    .st-meta-pill {
      background: var(--st-track); padding: 2px 7px; border-radius: 8px;
    }

    .st-error-msg { padding: 12px 14px; font-size: 11.5px; color: var(--st-red); }
  `;

  // --- State ---

  let shadow = null;
  let state = "idle"; // idle, scanning, done, info, hidden, error
  let expanded = false;
  let pageType = null; // result of classifyPage()
  let engineResults = {};
  let overallScore = 0;
  let overallVerdict = "";
  let enginesFlagged = 0;
  let enginesTotal = 23;
  let enginesDone = 0;
  let startTime = 0;
  let expandedGroups = {}; // groupKey → bool
  let lastUrl = location.href; // track URL for SPA navigation
  let initialized = false;

  // --- Init ---

  function init() {
    const root = document.createElement("div");
    root.id = "sloptotal-panel-root";
    shadow = root.attachShadow({ mode: "closed" });

    const style = document.createElement("style");
    style.textContent = STYLES;
    shadow.appendChild(style);

    const wrapper = document.createElement("div");
    wrapper.className = "st-wrapper";
    shadow.appendChild(wrapper);

    document.body.appendChild(root);

    buildPill(wrapper);
    buildPanel(wrapper);
  }

  function buildPill(wrapper) {
    const pill = document.createElement("div");
    pill.className = "st-pill";
    pill.id = "st-pill";
    pill.innerHTML = `<span class="st-dot" id="st-dot"></span><span id="st-pill-text">SlopTotal</span>`;
    pill.addEventListener("click", () => {
      if (state === "hidden") {
        state = enginesDone > 0 ? "done" : (pageType && !pageType.scoreable ? "info" : "idle");
        updatePill();
        pill.style.display = "";
        shadow.getElementById("st-reopen").style.display = "none";
      }
      togglePanel();
    });
    wrapper.appendChild(pill);

    const reopen = document.createElement("div");
    reopen.className = "st-reopen";
    reopen.id = "st-reopen";
    reopen.style.display = "none";
    reopen.innerHTML = `<span class="st-dot" id="st-reopen-dot"></span>`;
    reopen.addEventListener("click", () => {
      state = enginesDone > 0 ? "done" : (pageType && !pageType.scoreable ? "info" : "idle");
      updatePill();
      reopen.style.display = "none";
      pill.style.display = "";
      togglePanel();
    });
    wrapper.appendChild(reopen);
  }

  function buildPanel(wrapper) {
    const panel = document.createElement("div");
    panel.className = "st-panel";
    panel.id = "st-panel";
    panel.innerHTML = `
      <div class="st-header">
        <div class="st-brand"><span class="st-brand-slop">SLOP</span>TOTAL</div>
        <div class="st-header-btns">
          <button class="st-header-btn" id="st-btn-min" title="Minimize"><svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 7h8"/></svg></button>
          <button class="st-header-btn" id="st-btn-close" title="Close"><svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"/></svg></button>
        </div>
      </div>
      <div id="st-body"></div>
      <div class="st-meta" id="st-meta"></div>
    `;
    wrapper.appendChild(panel);

    panel.querySelector("#st-btn-min").addEventListener("click", (e) => {
      e.stopPropagation();
      togglePanel(false);
    });
    panel.querySelector("#st-btn-close").addEventListener("click", (e) => {
      e.stopPropagation();
      state = "hidden";
      togglePanel(false);
      shadow.getElementById("st-pill").style.display = "none";
      const reopen = shadow.getElementById("st-reopen");
      reopen.style.display = "";
      const dot = shadow.getElementById("st-reopen-dot");
      dot.className = "st-dot " + dotColorClass();
    });
  }

  function togglePanel(forceOpen) {
    const panel = shadow.getElementById("st-panel");
    expanded = forceOpen !== undefined ? forceOpen : !expanded;
    panel.classList.toggle("open", expanded);
  }

  // --- Pill updates ---

  function dotColorClass() {
    if (state === "info") return "grey";
    if (state === "error") return "error";
    if (overallScore > 65) return "red";
    if (overallScore > 40) return "yellow";
    return "green";
  }

  function updatePill() {
    const dot = shadow.getElementById("st-dot");
    const text = shadow.getElementById("st-pill-text");
    if (!dot || !text) return;

    if (state === "info" && pageType) {
      dot.className = "st-dot grey";
      text.innerHTML = `${escapeHtml(pageType.label)} <span class="st-pill-tag grey">${escapeHtml(pageType.type)}</span>`;
    } else if (state === "scanning") {
      dot.className = "st-dot scanning";
      text.textContent = `Scanning ${enginesDone}/${enginesTotal}...`;
    } else if (state === "done") {
      const pct = Math.round(overallScore);
      const cls = pct > 65 ? "red" : pct > 40 ? "yellow" : "green";
      dot.className = "st-dot " + cls;
      const tag = pageType ? ` <span class="st-pill-tag ${cls}">${escapeHtml(pageType.label)}</span>` : "";
      text.innerHTML = `${pct}%${tag}`;
    } else if (state === "error") {
      dot.className = "st-dot error";
      text.textContent = "Error";
    } else {
      dot.className = "st-dot";
      text.textContent = "SlopTotal";
    }
  }

  // --- Panel body rendering ---

  function renderBody() {
    const body = shadow.getElementById("st-body");
    if (!body) return;

    if (state === "info" && pageType) {
      body.innerHTML = `
        <div class="st-info-section">
          <div class="st-info-type">${escapeHtml(pageType.label)}</div>
          <div class="st-info-desc">
            ${pageType.type === "short" ? "Not enough text for reliable AI detection." :
              pageType.type === "hub" ? "Navigation-heavy page with minimal prose." :
              pageType.type === "landing" ? "Promotional page with limited article content." :
              "This page type is not suitable for AI detection."}
          </div>
        </div>`;
      return;
    }

    // Gauge + primary + groups
    let html = `
      <div class="st-gauge-section" id="st-gauge-section">
        ${gaugeSVG()}
        <div class="st-gauge-info">
          <span class="st-gauge-score" id="st-score-text">0 / 100</span>
          <span class="st-gauge-verdict" id="st-verdict-text">Scanning...</span>
          <span class="st-gauge-flagged" id="st-flagged-text">0 / ${enginesTotal} engines done</span>
        </div>
      </div>
      <div class="st-primary ${engineResults.classifier_fakespot ? "" : "pending"}" id="st-primary">
        <div class="st-primary-label">Primary Detector</div>
        <div class="st-primary-row">
          <span class="st-primary-name">Fakespot</span>
          <div class="st-primary-bar">
            <div class="st-primary-fill" id="st-fakespot-fill" style="width:0%"></div>
          </div>
          <span class="st-primary-val" id="st-fakespot-val">&hellip;</span>
        </div>
        <div class="st-primary-note" id="st-fakespot-note">Best AI discriminator (32% accuracy gap)</div>
      </div>
      <div class="st-groups" id="st-groups">`;

    // Render each group (skip primary since shown separately)
    for (const [gKey, group] of Object.entries(ENGINE_GROUPS)) {
      if (gKey === "primary") continue;
      html += renderGroup(gKey, group);
    }

    html += `</div>`;
    body.innerHTML = html;

    // Wire group toggle handlers
    for (const gKey of Object.keys(ENGINE_GROUPS)) {
      if (gKey === "primary") continue;
      const header = shadow.getElementById(`st-gh-${gKey}`);
      if (header) {
        header.addEventListener("click", () => {
          expandedGroups[gKey] = !expandedGroups[gKey];
          const chevron = shadow.getElementById(`st-gc-${gKey}`);
          const gbody = shadow.getElementById(`st-gb-${gKey}`);
          if (chevron) chevron.classList.toggle("open", expandedGroups[gKey]);
          if (gbody) gbody.classList.toggle("open", expandedGroups[gKey]);
        });
      }
    }

    updateGauge();
    updateFakespot();
  }

  function renderGroup(gKey, group) {
    const keys = group.keys;
    const done = keys.filter((k) => engineResults[k]);
    const flagged = done.filter((k) => engineResults[k].score >= 0.4);
    const isOpen = expandedGroups[gKey] || false;

    let dots = "";
    for (const k of keys) {
      const r = engineResults[k];
      if (!r) dots += `<span class="st-gdot pending"></span>`;
      else if (r.score >= 0.4) dots += `<span class="st-gdot flagged"></span>`;
      else dots += `<span class="st-gdot clean"></span>`;
    }

    let rows = "";
    // Sort done engines by score desc, then pending
    const sortedDone = keys.filter((k) => engineResults[k]).sort((a, b) => engineResults[b].score - engineResults[a].score);
    const pending = keys.filter((k) => !engineResults[k]);

    for (const k of sortedDone) {
      const r = engineResults[k];
      const pct = Math.round(r.score * 100);
      const color = scoreColor(pct);
      rows += `<div class="st-engine-row">
        <span class="st-engine-name" title="${escapeHtml(r.engine_name || k)}">${escapeHtml(displayName(k))}</span>
        <div class="st-engine-bar"><div class="st-engine-fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="st-engine-val" style="color:${color}">${pct}%</span>
      </div>`;
    }
    for (const k of pending) {
      rows += `<div class="st-engine-row pending">
        <span class="st-engine-name">${escapeHtml(displayName(k))}</span>
        <div class="st-engine-bar"></div>
        <span class="st-engine-val">&hellip;</span>
      </div>`;
    }

    return `<div class="st-group">
      <div class="st-group-header" id="st-gh-${gKey}">
        <span class="st-group-label">${escapeHtml(group.label)}</span>
        <div class="st-group-right">
          <div class="st-group-dots">${dots}</div>
          <span class="st-group-count">${flagged.length}/${keys.length}</span>
          <span class="st-group-chevron ${isOpen ? "open" : ""}" id="st-gc-${gKey}">\u25B8</span>
        </div>
      </div>
      <div class="st-group-body ${isOpen ? "open" : ""}" id="st-gb-${gKey}">${rows}</div>
    </div>`;
  }

  function updateFakespot() {
    const r = engineResults.classifier_fakespot;
    const fill = shadow.getElementById("st-fakespot-fill");
    const val = shadow.getElementById("st-fakespot-val");
    const note = shadow.getElementById("st-fakespot-note");
    const section = shadow.getElementById("st-primary");

    if (!r || !fill) return;

    const cal = calibrateFakespot(r.score);
    const color = scoreColor(cal);
    fill.style.width = cal + "%";
    fill.style.background = color;
    if (val) { val.textContent = cal + "%"; val.style.color = color; }
    if (section) section.classList.remove("pending");

    if (note) {
      if (cal > 65) note.textContent = "Strong AI signals detected";
      else if (cal > 40) note.textContent = "Moderate AI signals detected";
      else note.textContent = "Minimal AI signals detected";
    }
  }

  function updateGauge() {
    const arc = shadow.querySelector(".st-gauge-arc");
    const num = shadow.querySelector(".st-gauge-num");
    const scoreText = shadow.getElementById("st-score-text");
    const verdictText = shadow.getElementById("st-verdict-text");
    const flaggedText = shadow.getElementById("st-flagged-text");
    if (!arc) return;

    const pct = Math.round(overallScore);
    const offset = GAUGE_CIRC * (1 - Math.min(overallScore / 100, 1));

    arc.style.strokeDashoffset = offset;
    arc.style.stroke = scoreColor(overallScore);
    num.textContent = pct || "0";

    if (scoreText) {
      scoreText.textContent = `${Math.round(overallScore * 10) / 10} / 100`;
      scoreText.style.color = scoreColor(overallScore);
    }
    if (verdictText) verdictText.textContent = overallVerdict || "Analyzing...";
    if (flaggedText) {
      flaggedText.textContent = state === "done"
        ? `${enginesFlagged} / ${enginesTotal} flagged`
        : `${enginesDone} / ${enginesTotal} engines done`;
    }
  }

  function updateGroups() {
    // Re-render group internals (dots, counts, rows) without destroying expand state
    for (const [gKey, group] of Object.entries(ENGINE_GROUPS)) {
      if (gKey === "primary") continue;

      const keys = group.keys;
      const flagged = keys.filter((k) => engineResults[k] && engineResults[k].score >= 0.4);
      const count = shadow.querySelector(`#st-gh-${gKey} .st-group-count`);
      if (count) count.textContent = `${flagged.length}/${keys.length}`;

      // Update dots
      const dotsEl = shadow.querySelector(`#st-gh-${gKey} .st-group-dots`);
      if (dotsEl) {
        let dots = "";
        for (const k of keys) {
          const r = engineResults[k];
          if (!r) dots += `<span class="st-gdot pending"></span>`;
          else if (r.score >= 0.4) dots += `<span class="st-gdot flagged"></span>`;
          else dots += `<span class="st-gdot clean"></span>`;
        }
        dotsEl.innerHTML = dots;
      }

      // Update body if expanded
      const gbody = shadow.getElementById(`st-gb-${gKey}`);
      if (gbody && expandedGroups[gKey]) {
        const sortedDone = keys.filter((k) => engineResults[k]).sort((a, b) => engineResults[b].score - engineResults[a].score);
        const pending = keys.filter((k) => !engineResults[k]);
        let rows = "";
        for (const k of sortedDone) {
          const r = engineResults[k];
          const pct = Math.round(r.score * 100);
          const color = scoreColor(pct);
          rows += `<div class="st-engine-row">
            <span class="st-engine-name" title="${escapeHtml(r.engine_name || k)}">${escapeHtml(displayName(k))}</span>
            <div class="st-engine-bar"><div class="st-engine-fill" style="width:${pct}%;background:${color}"></div></div>
            <span class="st-engine-val" style="color:${color}">${pct}%</span>
          </div>`;
        }
        for (const k of pending) {
          rows += `<div class="st-engine-row pending">
            <span class="st-engine-name">${escapeHtml(displayName(k))}</span>
            <div class="st-engine-bar"></div>
            <span class="st-engine-val">&hellip;</span>
          </div>`;
        }
        gbody.innerHTML = rows;
      }
    }
  }

  function updateMeta() {
    const meta = shadow.getElementById("st-meta");
    if (!meta) return;
    const parts = [];
    if (pageType) parts.push(`<span class="st-meta-pill">${escapeHtml(pageType.label.toLowerCase())}</span>`);
    const bodyLen = getBodyText().length;
    if (bodyLen > 0) {
      const words = Math.round(bodyLen / 5);
      parts.push(`<span class="st-meta-pill">${words.toLocaleString()} words</span>`);
    }
    try { parts.push(`<span class="st-meta-pill">${new URL(location.href).hostname}</span>`); } catch {}
    if (startTime > 0) {
      parts.push(`<span class="st-meta-pill">${((Date.now() - startTime) / 1000).toFixed(1)}s</span>`);
    }
    meta.innerHTML = parts.join("");
  }

  // --- Cached results ---

  function renderCachedResults(data) {
    engineResults = data.engines || {};
    overallScore = data.overallScore || 0;
    overallVerdict = data.overallVerdict || "";
    enginesFlagged = data.enginesFlagged || 0;
    enginesTotal = data.enginesTotal || 23;
    enginesDone = Object.keys(engineResults).length;
    state = "done";
    // Expand all groups to show model percentages
    for (const gKey of Object.keys(ENGINE_GROUPS)) {
      if (gKey === "primary") continue;
      expandedGroups[gKey] = true;
    }
    updatePill();
    renderBody();
    updateMeta();
    // Auto-expand the panel
    togglePanel(true);
    // Ensure pill is visible (in case it was hidden)
    const pill = shadow.getElementById("st-pill");
    const reopen = shadow.getElementById("st-reopen");
    if (pill) pill.style.display = "";
    if (reopen) reopen.style.display = "none";
  }

  // --- Analysis ---

  async function startAnalysis() {
    state = "scanning";
    startTime = Date.now();
    engineResults = {};
    enginesDone = 0;
    overallScore = 0;
    overallVerdict = "";
    enginesFlagged = 0;

    updatePill();
    renderBody();
    // Show the panel immediately so user sees the design with loading states
    togglePanel(true);

    try {
      await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(
          { type: "startFullAnalysis", url: location.href },
          (resp) => {
            if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
            else if (resp && resp.error) reject(new Error(resp.error));
            else if (resp && resp.reportId) resolve(resp);
            else reject(new Error("Invalid response from background"));
          }
        );
      });
      // SSE events relayed via background.js → onMessage below
    } catch (err) {
      state = "error";
      updatePill();
      const body = shadow.getElementById("st-body");
      if (body) body.innerHTML = `<div class="st-error-msg">Failed: ${escapeHtml(err.message)}</div>`;
    }
  }

  // --- SSE relay listener ---

  chrome.runtime.onMessage.addListener((message) => {
    if (message.type !== "panelSSE" || state !== "scanning") return;
    const data = message.data;

    if (data.error) {
      if (enginesDone > 0) {
        state = "done"; updatePill(); updateGauge(); updateMeta(); cacheResults();
        togglePanel(true);
        for (const gKey of Object.keys(ENGINE_GROUPS)) {
          if (gKey === "primary") continue;
          expandedGroups[gKey] = true;
          const chevron = shadow.getElementById(`st-gc-${gKey}`);
          const gbody = shadow.getElementById(`st-gb-${gKey}`);
          if (chevron) chevron.classList.add("open");
          if (gbody) gbody.classList.add("open");
        }
        updateGroups();
      } else {
        state = "error"; updatePill();
        const body = shadow.getElementById("st-body");
        if (body) body.innerHTML = `<div class="st-error-msg">Connection lost. Server may be offline.</div>`;
      }
      return;
    }

    if (data.done) {
      state = "done";
      updatePill();
      updateGauge();
      updateMeta();
      cacheResults();
      // Auto-expand panel and all engine groups to show model percentages
      togglePanel(true);
      for (const gKey of Object.keys(ENGINE_GROUPS)) {
        if (gKey === "primary") continue;
        expandedGroups[gKey] = true;
      }
      updateGroups();
      // Expand group DOM elements
      for (const gKey of Object.keys(ENGINE_GROUPS)) {
        if (gKey === "primary") continue;
        const chevron = shadow.getElementById(`st-gc-${gKey}`);
        const gbody = shadow.getElementById(`st-gb-${gKey}`);
        if (chevron) chevron.classList.add("open");
        if (gbody) gbody.classList.add("open");
      }
      return;
    }

    engineResults[data.key] = {
      engine_name: data.engine_name,
      score: data.score,
      verdict: data.verdict,
      details: data.details,
      description: data.description,
    };
    overallScore = data.overall_score || overallScore;
    overallVerdict = data.overall_verdict || overallVerdict;
    enginesFlagged = data.engines_flagged || enginesFlagged;
    enginesTotal = data.engines_total || enginesTotal;
    enginesDone = data.engines_done || Object.keys(engineResults).length;

    updatePill();
    updateGauge();
    updateFakespot();
    updateGroups();
  });

  function cacheResults() {
    try {
      chrome.storage.session.set({
        [hashUrl(location.href)]: {
          engines: engineResults, overallScore, overallVerdict,
          enginesFlagged, enginesTotal, pageType,
        },
      });
    } catch {}
  }

  // --- SPA navigation detection ---

  function resetState() {
    state = "idle";
    expanded = false;
    engineResults = {};
    overallScore = 0;
    overallVerdict = "";
    enginesFlagged = 0;
    enginesTotal = 23;
    enginesDone = 0;
    startTime = 0;
    expandedGroups = {};
  }

  async function resetAndScan() {
    const newUrl = location.href;
    if (newUrl === lastUrl) return;
    lastUrl = newUrl;

    console.log("[SlopTotal Panel] URL changed, re-scanning:", newUrl);

    resetState();

    // Restore pill visibility and close panel
    const pill = shadow?.getElementById("st-pill");
    const reopen = shadow?.getElementById("st-reopen");
    if (pill) pill.style.display = "";
    if (reopen) reopen.style.display = "none";
    togglePanel(false);
    updatePill();

    // Wait for new page content to load
    await new Promise((r) => setTimeout(r, 1000));

    const bodyLen = getBodyText().length;
    if (bodyLen < 100) {
      state = "idle";
      updatePill();
      const body = shadow?.getElementById("st-body");
      if (body) body.innerHTML = "";
      return;
    }

    pageType = classifyPage();

    if (!pageType.scoreable) {
      state = "info";
      updatePill();
      renderBody();
      updateMeta();
      return;
    }

    // Check session cache first
    const cacheKey = hashUrl(newUrl);
    try {
      const cached = await new Promise((r) => chrome.storage.session.get(cacheKey, r));
      if (cached && cached[cacheKey]) {
        if (cached[cacheKey].pageType) pageType = cached[cacheKey].pageType;
        renderCachedResults(cached[cacheKey]);
        return;
      }
    } catch {}

    // Wait a bit more to avoid bounce
    await new Promise((r) => setTimeout(r, 1000));
    if (getBodyText().length < 200) return;

    startAnalysis();
  }

  function setupNavigationListeners() {
    // Intercept pushState
    const origPushState = history.pushState;
    history.pushState = function (...args) {
      origPushState.apply(this, args);
      setTimeout(resetAndScan, 100);
    };

    // Intercept replaceState
    const origReplaceState = history.replaceState;
    history.replaceState = function (...args) {
      origReplaceState.apply(this, args);
      setTimeout(resetAndScan, 100);
    };

    // Back/forward navigation
    window.addEventListener("popstate", () => setTimeout(resetAndScan, 100));

    // Hash changes
    window.addEventListener("hashchange", () => setTimeout(resetAndScan, 100));
  }

  // --- Entry point ---

  async function run() {
    const settings = await new Promise((r) => chrome.storage.local.get({ autoAnalyze: true }, r));
    if (!settings.autoAnalyze) return;

    if (!document.body) {
      await new Promise((r) => {
        if (document.readyState !== "loading") r();
        else document.addEventListener("DOMContentLoaded", r);
      });
    }

    const bodyLen = getBodyText().length;
    if (bodyLen < 100) return; // Absolute minimum to even show panel

    // Classify page
    pageType = classifyPage();

    if (!initialized) {
      init();
      setupNavigationListeners();
      initialized = true;
    }

    // Check session cache
    const cacheKey = hashUrl(location.href);
    try {
      const cached = await new Promise((r) => chrome.storage.session.get(cacheKey, r));
      if (cached && cached[cacheKey]) {
        if (cached[cacheKey].pageType) pageType = cached[cacheKey].pageType;
        renderCachedResults(cached[cacheKey]);
        return;
      }
    } catch {}

    // Non-scoreable pages: show info immediately, no analysis
    if (!pageType.scoreable) {
      state = "info";
      updatePill();
      renderBody();
      updateMeta();
      return;
    }

    // Wait 2s before starting (avoid bounce)
    await new Promise((r) => setTimeout(r, 2000));
    if (getBodyText().length < 200) return;

    startAnalysis();
  }

  run();
})();
