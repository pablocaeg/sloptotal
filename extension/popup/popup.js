// SlopTotal Popup — zero messaging, instant from cache

const DEFAULT_API_URL = "http://localhost:8000";

const connDot = document.getElementById("conn-dot");
const connLabel = document.getElementById("conn-label");
const statusCount = document.getElementById("status-count");
const statusText = document.getElementById("status-text");
const ringFill = document.getElementById("ring-fill");
const scanBtn = document.getElementById("scan-btn");
const scanStatus = document.getElementById("scan-status");
const resultsEl = document.getElementById("results");
const verdictEl = document.getElementById("verdict");
const scoreDisplay = document.getElementById("score-display");
const resultsFill = document.getElementById("results-fill");
const engineRows = document.getElementById("engine-rows");
const tGoogle = document.getElementById("t-google");
const tLinkedin = document.getElementById("t-linkedin");
const tSponsored = document.getElementById("t-sponsored");
const tAutoanalyze = document.getElementById("t-autoanalyze");
const apiUrlInput = document.getElementById("api-url");
const saveBtn = document.getElementById("save-btn");
const settingsToggle = document.getElementById("settings-toggle");
const settingsPanel = document.getElementById("settings-panel");
const settingsChevron = document.getElementById("settings-chevron");

const RING_CIRCUMFERENCE = 2 * Math.PI * 26; // r=26 → 163.36

// --- Settings toggle ---
settingsToggle.addEventListener("click", () => {
  const open = settingsPanel.style.display === "none";
  settingsPanel.style.display = open ? "block" : "none";
  settingsChevron.classList.toggle("open", open);
});

// ONE storage read — all cached data at once
chrome.storage.local.get(
  { apiUrl: DEFAULT_API_URL, googleEnabled: true, linkedinEnabled: true, hideSponsored: true, autoAnalyze: true, connOk: false },
  (s) => {
    apiUrlInput.value = s.apiUrl;
    tGoogle.checked = s.googleEnabled;
    tLinkedin.checked = s.linkedinEnabled;
    tSponsored.checked = s.hideSponsored;
    tAutoanalyze.checked = s.autoAnalyze;
    if (s.connOk) {
      connDot.className = "conn live";
      connLabel.textContent = "connected";
    }
    checkServer(s.apiUrl);
  }
);

// Tab count from session storage — no messaging, no service worker wake
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (!tabs[0]) { showCount(0); return; }
  const tabId = tabs[0].id;
  chrome.storage.session?.get?.(`tc_${tabId}`, (data) => {
    if (chrome.runtime.lastError) { showCount(0); return; }
    showCount(data?.[`tc_${tabId}`] || 0);
  }) || showCount(0);
});

function showCount(c) {
  statusCount.textContent = String(c);
  if (c > 0) {
    statusText.textContent = `${c} flagged on this page`;
    statusCount.classList.add("flagged");
    ringFill.classList.add("flagged");
    // Animate ring — show proportion (cap at full circle for 20+)
    const ratio = Math.min(c / 20, 1);
    ringFill.style.strokeDashoffset = RING_CIRCUMFERENCE * (1 - ratio);
  } else {
    statusText.textContent = "No AI content detected";
    ringFill.style.strokeDashoffset = RING_CIRCUMFERENCE; // empty
  }
}

function checkServer(url) {
  fetch(`${url}/health`, { signal: AbortSignal.timeout(1500) })
    .then((r) => r.json())
    .then((d) => {
      if (d.status) {
        connDot.className = "conn live";
        connLabel.textContent = `${d.engines} engines`;
        chrome.storage.local.set({ connOk: true });
      } else {
        connDot.className = "conn dead";
        connLabel.textContent = "error";
        chrome.storage.local.set({ connOk: false });
      }
    })
    .catch(() => {
      connDot.className = "conn dead";
      connLabel.textContent = "offline";
      chrome.storage.local.set({ connOk: false });
    });
}

// Save
saveBtn.addEventListener("click", () => {
  const url = apiUrlInput.value.trim().replace(/\/+$/, "");
  if (!url) return;
  chrome.storage.sync.set({ apiUrl: url });
  chrome.storage.local.set({ apiUrl: url });
  connDot.className = "conn";
  connLabel.textContent = "checking...";
  checkServer(url);
});

tGoogle.addEventListener("change", () => {
  const v = tGoogle.checked;
  chrome.storage.sync.set({ googleEnabled: v });
  chrome.storage.local.set({ googleEnabled: v });
});
tLinkedin.addEventListener("change", () => {
  const v = tLinkedin.checked;
  chrome.storage.sync.set({ linkedinEnabled: v });
  chrome.storage.local.set({ linkedinEnabled: v });
});
tSponsored.addEventListener("change", () => {
  const v = tSponsored.checked;
  chrome.storage.sync.set({ hideSponsored: v });
  chrome.storage.local.set({ hideSponsored: v });
});
tAutoanalyze.addEventListener("change", () => {
  const v = tAutoanalyze.checked;
  chrome.storage.sync.set({ autoAnalyze: v });
  chrome.storage.local.set({ autoAnalyze: v });
});

// --- Scan selected text ---
scanBtn.addEventListener("click", async () => {
  scanBtn.disabled = true;
  scanStatus.textContent = "Reading selection...";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error("No active tab");
    const [{ result: sel }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: () => window.getSelection().toString(),
    });
    if (!sel || sel.trim().length < 30) {
      scanStatus.textContent = "Select 30+ characters first";
      scanBtn.disabled = false;
      return;
    }
    const text = sel.trim();
    scanStatus.textContent = `Analyzing ${text.length} chars...`;
    const { apiUrl } = await chrome.storage.local.get({ apiUrl: DEFAULT_API_URL });
    const endpoint = text.length > 300 ? `${apiUrl}/api/paragraph-score` : `${apiUrl}/api/quick-score`;
    const t = performance.now();
    const resp = await fetch(endpoint, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).error || `HTTP ${resp.status}`);
    const data = await resp.json();
    scanStatus.textContent = `Done in ${Math.round(performance.now() - t)}ms`;
    showResults(data);
  } catch (err) {
    scanStatus.textContent = err.message;
  } finally {
    scanBtn.disabled = false;
  }
});

function showResults(data) {
  resultsEl.style.display = "block";
  const score = data.overall_score || data.score || 0;
  const verdict = data.overall_verdict || data.verdict || "mixed";
  const vLabels = { clean: "HUMAN", mixed: "MIXED", ai: "AI DETECTED" };
  const color = score > 65 ? "#b5282e" : score > 35 ? "#c98b1d" : "#2d8a4e";
  const fillClass = score > 65 ? "fill-red" : score > 35 ? "fill-yellow" : "fill-green";
  verdictEl.textContent = vLabels[verdict] || verdict.toUpperCase();
  verdictEl.style.color = color;
  scoreDisplay.textContent = `${Math.round(score)}%`;
  scoreDisplay.style.color = color;
  resultsFill.className = `results-fill ${fillClass}`;
  resultsFill.style.width = `${score}%`;
  let html = "";
  if (data.paragraphs?.length > 0) {
    for (const p of data.paragraphs) {
      const c = p.score > 65 ? "fill-red" : p.score > 35 ? "fill-yellow" : "fill-green";
      html += `<div class="erow" title="${esc(p.text)}"><span class="erow-name">P${p.index + 1}</span><div class="erow-track"><div class="erow-fill ${c}" style="width:${p.score}%"></div></div><span class="erow-val">${Math.round(p.score)}%</span></div>`;
    }
  }
  if (data.engines?.length > 0) {
    for (const e of [...data.engines].sort((a, b) => b.score - a.score)) {
      const c = e.score > 65 ? "fill-red" : e.score > 35 ? "fill-yellow" : "fill-green";
      const name = e.engine.replace("classifier_", "").replace(/_/g, " ");
      html += `<div class="erow"><span class="erow-name" title="${e.engine}">${name}</span><div class="erow-track"><div class="erow-fill ${c}" style="width:${e.score}%"></div></div><span class="erow-val">${Math.round(e.score)}%</span></div>`;
    }
  }
  engineRows.innerHTML = html;
}

function esc(str) { const d = document.createElement("div"); d.textContent = str; return d.innerHTML; }
