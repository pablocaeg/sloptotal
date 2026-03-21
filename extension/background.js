// SlopTotal Background Service Worker
// Cache-first: cached results return instantly, fresh results stream via messaging

const DEFAULT_API_URL = "http://localhost:8000";
const CACHE_TTL_MS = 60 * 60 * 1000;
const CACHE_MAX_SIZE = 500;
const SUB_BATCH_SIZE = 5;

const cache = new Map();
const tabCounts = new Map();

function getApiUrl() {
  return new Promise((resolve) => {
    chrome.storage.sync.get({ apiUrl: DEFAULT_API_URL }, (items) => resolve(items.apiUrl));
  });
}

function hashText(text) {
  let hash = 5381;
  for (let i = 0; i < text.length; i++) {
    hash = ((hash << 5) + hash + text.charCodeAt(i)) & 0xffffffff;
  }
  return hash.toString(36);
}

function cacheGet(key) {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > CACHE_TTL_MS) { cache.delete(key); return null; }
  cache.delete(key);
  cache.set(key, entry);
  return entry.result;
}

function cacheSet(key, result) {
  if (cache.size >= CACHE_MAX_SIZE) cache.delete(cache.keys().next().value);
  cache.set(key, { result, timestamp: Date.now() });
}

// --- Badge ---

function addToBadge(tabId, additional) {
  const total = (tabCounts.get(tabId) || 0) + additional;
  tabCounts.set(tabId, total);
  const text = total > 0 ? String(total) : "";
  chrome.action.setBadgeText({ text, tabId });
  chrome.action.setBadgeBackgroundColor({ color: total > 0 ? "#e53e3e" : "#38a169", tabId });
  chrome.storage.session?.set?.({ [`tc_${tabId}`]: total }).catch(() => {});
}

// --- DOM features cache (keyed by URL, sent by content scripts) ---

const domFeaturesCache = new Map();

function domFeaturesCacheSet(url, features) {
  if (domFeaturesCache.size >= CACHE_MAX_SIZE) domFeaturesCache.delete(domFeaturesCache.keys().next().value);
  domFeaturesCache.set(url, { features, timestamp: Date.now() });
}

function domFeaturesCacheGet(url) {
  const entry = domFeaturesCache.get(url);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > CACHE_TTL_MS) { domFeaturesCache.delete(url); return null; }
  return entry.features;
}

// --- URL cache (keyed by URL, separate from text cache) ---

const urlCache = new Map();

function urlCacheGet(url) {
  const entry = urlCache.get(url);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > CACHE_TTL_MS) { urlCache.delete(url); return null; }
  urlCache.delete(url);
  urlCache.set(url, entry);
  return entry.result;
}

function urlCacheSet(url, result) {
  if (urlCache.size >= CACHE_MAX_SIZE) urlCache.delete(urlCache.keys().next().value);
  urlCache.set(url, { result, timestamp: Date.now() });
}

// --- Fetch URL content and analyze (Phase 2: deep scan) ---

async function fetchUrlResults(snippetsWithUrls, tabId) {
  const t0 = performance.now();

  // Check URL cache first
  const cachedUrlResults = {};
  const uncachedUrls = [];
  for (const s of snippetsWithUrls) {
    const cached = urlCacheGet(s.url);
    if (cached) {
      cachedUrlResults[s.id] = { ...cached, id: s.id };
    } else {
      uncachedUrls.push(s);
    }
  }

  // Send cached URL results immediately
  if (Object.keys(cachedUrlResults).length > 0) {
    console.log(`[BG] urlScan: ${Object.keys(cachedUrlResults).length} cached URL results`);
    chrome.tabs.sendMessage(tabId, { type: "urlResults", results: cachedUrlResults }).catch(() => {});
  }

  if (uncachedUrls.length === 0) {
    console.log(`[BG] urlScan: all ${snippetsWithUrls.length} URLs cached`);
    return;
  }

  // Sub-batch URLs (5 at a time), send ALL batches in parallel for speed
  const batches = [];
  for (let i = 0; i < uncachedUrls.length; i += SUB_BATCH_SIZE) {
    batches.push(uncachedUrls.slice(i, i + SUB_BATCH_SIZE));
  }

  console.log(
    `[BG] urlScan: ${uncachedUrls.length} URLs → ${batches.length} batches (parallel) ` +
    `(${Object.keys(cachedUrlResults).length} cached)`
  );

  async function sendUrlBatch(batch, bi) {
    const tBatch = performance.now();
    try {
      const apiUrl = await getApiUrl();
      const payload = batch.map((s) => {
        const item = { id: s.id, url: s.url };
        const df = domFeaturesCacheGet(s.url);
        if (df) item.dom_features = df;
        return item;
      });
      const resp = await fetch(`${apiUrl}/api/scan/urls`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: payload }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const batchMs = Math.round(performance.now() - tBatch);

      const timing = data.timing || {};
      console.log(
        `[BG] urlBatch[${bi}]: ${batchMs}ms | ` +
        `server: ${timing.total_ms || "?"}ms | ` +
        `${timing.urls_scored || 0}/${timing.urls_total || 0} scored`
      );

      if (data.results && data.results.length > 0) {
        const results = {};
        for (const r of data.results) {
          urlCacheSet(batch.find((s) => s.id === r.id)?.url || "", r);
          results[r.id] = r;
          console.log(
            `[BG]   url ${r.id}: ${r.chars}ch → ${r.score}% ${r.indicator} ` +
            `[${r.page_type || "article"}] ` +
            `(fetch=${r.fetch_ms}ms score=${r.score_ms}ms total=${r.item_ms}ms)`
          );
        }
        chrome.tabs.sendMessage(tabId, { type: "urlResults", results }).catch(() => {});
      }

      // Info results: non-scoreable pages (hub, landing, short)
      if (data.info && data.info.length > 0) {
        const infoResults = {};
        for (const r of data.info) {
          r.scoreable = false;
          urlCacheSet(batch.find((s) => s.id === r.id)?.url || "", r);
          infoResults[r.id] = r;
          console.log(
            `[BG]   url ${r.id}: ${r.chars}ch → ${r.page_type} (${r.page_label}) ` +
            `[not scored] (${r.item_ms}ms)`
          );
        }
        chrome.tabs.sendMessage(tabId, { type: "urlResults", results: infoResults }).catch(() => {});
      }

      if (data.errors) {
        for (const e of data.errors) {
          console.warn(`[BG]   url ${e.id} FAILED: ${e.error} (${e.fetch_ms}ms)`);
        }
      }
    } catch (err) {
      console.error(`[BG] urlBatch[${bi}] ERROR: ${err.message}`);
    }
  }

  // Fire all batches in parallel — results stream as each batch completes
  await Promise.allSettled(batches.map((batch, i) => sendUrlBatch(batch, i)));

  const totalMs = Math.round(performance.now() - t0);
  console.log(`[BG] urlScan complete: ${totalMs}ms for ${uncachedUrls.length} URLs`);
}

// --- Fetch uncached snippets in sub-batches of 5 ---

async function fetchAndDeliver(uncached, tabId) {
  const t0 = performance.now();
  const batches = [];
  for (let i = 0; i < uncached.length; i += SUB_BATCH_SIZE) {
    batches.push(uncached.slice(i, i + SUB_BATCH_SIZE));
  }
  const totalChars = uncached.reduce((sum, s) => sum + s.text.length, 0);
  console.log(
    `[BG] fetch: ${uncached.length} snippets → ${batches.length} sub-batches | ${totalChars} chars total`
  );
  const results = await Promise.allSettled(batches.map((batch, i) => fetchSubBatch(batch, tabId, i)));
  const allMs = Math.round(performance.now() - t0);
  const ok = results.filter((r) => r.status === "fulfilled").length;
  console.log(`[BG] fetch done: ${ok}/${batches.length} batches in ${allMs}ms`);
}

async function fetchSubBatch(snippets, tabId, batchIdx) {
  const t0 = performance.now();
  const chars = snippets.reduce((sum, s) => sum + s.text.length, 0);
  const charList = snippets.map((s) => s.text.length).join(",");
  console.log(`[BG] batch[${batchIdx}] sending: ${snippets.length} snippets, ${chars} chars [${charList}]`);

  try {
    const apiUrl = await getApiUrl();
    const tFetch = performance.now();
    const resp = await fetch(`${apiUrl}/api/scan/snippets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ snippets }),
    });
    const tResp = performance.now();
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const tParse = performance.now();

    const networkMs = Math.round(tResp - tFetch);
    const parseMs = Math.round(tParse - tResp);
    const totalMs = Math.round(tParse - t0);

    // Log server-side timing from response
    const st = data.timing || {};
    console.log(
      `[BG] batch[${batchIdx}] done: ${totalMs}ms total ` +
      `(network=${networkMs}ms parse=${parseMs}ms) | ` +
      `server: ${st.total_ms || "?"}ms (fakespot=${st.fakespot_ms || "?"}ms) | ` +
      `${st.texts || "?"} texts, ${st.total_chars || "?"} chars (avg=${st.avg_chars || "?"}, range=${(st.char_range || []).join("-")})`
    );

    if (data.results) {
      const results = {};
      for (const r of data.results) {
        const snippet = snippets.find((s) => s.id === r.id);
        if (snippet) cacheSet(hashText(snippet.text), r);
        results[r.id] = r;
      }
      // Per-snippet log
      for (const r of data.results) {
        const raw = r.raw || {};
        console.log(
          `[BG]   ${r.id}: ${r.chars}ch → ${r.score}% ${r.indicator} (${r.confidence}) ` +
          `raw[fakespot=${raw.fakespot}]`
        );
      }
      const flagged = Object.values(results).filter((r) => r.score >= 60).length;
      addToBadge(tabId, flagged);
      chrome.tabs.sendMessage(tabId, { type: "snippetResults", results }).catch(() => {});
    }
  } catch (err) {
    const ms = Math.round(performance.now() - t0);
    console.error(`[BG] batch[${batchIdx}] ERROR after ${ms}ms: ${err.message}`);
    chrome.tabs.sendMessage(tabId, {
      type: "snippetError", pendingIds: snippets.map((s) => s.id), error: err.message,
    }).catch(() => {});
  }
}

// --- Full analysis SSE relay (background → content script) ---

function streamFullAnalysis(apiUrl, reportId, tabId) {
  const url = `${apiUrl}/api/stream/${reportId}`;
  const es = new EventSource(url);

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      chrome.tabs.sendMessage(tabId, { type: "panelSSE", data }).catch(() => {});
      if (data.done) {
        es.close();
      }
    } catch {}
  };

  es.onerror = () => {
    es.close();
    chrome.tabs.sendMessage(tabId, { type: "panelSSE", data: { error: true } }).catch(() => {});
  };
}

// --- Message handler ---

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab?.id;

  if (message.type === "scanSnippets") {
    const t0 = performance.now();
    const cachedResults = {};
    const uncached = [];
    for (const s of message.snippets) {
      const cached = cacheGet(hashText(s.text));
      if (cached) cachedResults[s.id] = cached;
      else uncached.push(s);
    }
    const cacheMs = Math.round((performance.now() - t0) * 100) / 100;

    const cachedChars = message.snippets
      .filter((s) => cachedResults[s.id])
      .reduce((sum, s) => sum + s.text.length, 0);
    const uncachedChars = uncached.reduce((sum, s) => sum + s.text.length, 0);

    console.log(
      `[BG] scanSnippets: ${message.snippets.length} total | ` +
      `${Object.keys(cachedResults).length} cached (${cachedChars}ch) | ` +
      `${uncached.length} pending (${uncachedChars}ch) | ` +
      `cache lookup: ${cacheMs}ms | cache size: ${cache.size}`
    );

    const flagged = Object.values(cachedResults).filter((r) => r.score >= 60).length;
    if (tabId && flagged > 0) addToBadge(tabId, flagged);

    // Collect snippets with URLs for Phase 2 deep scan
    const withUrls = message.snippets.filter((s) => s.url && s.url.startsWith("http"));

    sendResponse({ results: cachedResults, pending: uncached.length });

    if (uncached.length > 0 && tabId) fetchAndDeliver(uncached, tabId);

    // Phase 2: URL content analysis (runs after snippet badges appear)
    if (withUrls.length > 0 && tabId) {
      console.log(`[BG] scheduling URL scan for ${withUrls.length} URLs`);
      // Small delay to let snippet results render first
      setTimeout(() => fetchUrlResults(withUrls, tabId), 200);
    }
    return false;
  }

  if (message.type === "quickScore") {
    const key = hashText(message.text);
    const cached = cacheGet(key);
    if (cached) {
      console.log(`[BG] quickScore: cached, ${message.text.length}ch`);
      sendResponse({ result: cached });
      return false;
    }

    console.log(`[BG] quickScore: fetching, ${message.text.length}ch`);
    (async () => {
      const t0 = performance.now();
      try {
        const apiUrl = await getApiUrl();
        const resp = await fetch(`${apiUrl}/api/quick-score`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: message.text }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        cacheSet(key, data);
        console.log(`[BG] quickScore: ${Math.round(performance.now() - t0)}ms → ${data.score}%`);
        sendResponse({ result: data });
      } catch (err) {
        console.error(`[BG] quickScore ERROR: ${err.message} (${Math.round(performance.now() - t0)}ms)`);
        sendResponse({ error: err.message });
      }
    })();
    return true;
  }

  if (message.type === "startFullAnalysis") {
    (async () => {
      try {
        const apiUrl = await getApiUrl();
        const resp = await fetch(`${apiUrl}/api/web/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: message.url }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (data.report_id) {
          sendResponse({ reportId: data.report_id });
          // Open SSE in background (has full network access, no CORS issues)
          // and relay each event to the content script via tabs.sendMessage
          streamFullAnalysis(apiUrl, data.report_id, tabId);
        } else if (data.status === "queued") {
          sendResponse({ error: "Server busy \u2014 analysis queued" });
        } else {
          sendResponse({ error: data.error || "No report ID returned" });
        }
      } catch (err) {
        sendResponse({ error: err.message });
      }
    })();
    return true;
  }

  if (message.type === "getTabCount") {
    sendResponse({ count: tabCounts.get(message.tabId || tabId) || 0 });
    return false;
  }

  if (message.type === "domFeatures") {
    if (message.url && message.features) {
      domFeaturesCacheSet(message.url, message.features);
      console.log(`[BG] domFeatures cached for ${message.url}`);
    }
    return false;
  }
});

// Clean up tab counts
chrome.tabs.onRemoved.addListener((tabId) => {
  tabCounts.delete(tabId);
  chrome.storage.session?.remove?.(`tc_${tabId}`).catch(() => {});
});

// --- Context Menu ---

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "sloptotal-check", title: "Check with SlopTotal", contexts: ["selection"] });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "sloptotal-check") return;
  const text = (info.selectionText || "").trim();
  if (!text || text.length < 20) {
    chrome.notifications.create("sloptotal-short", {
      type: "basic", iconUrl: "icons/icon128.png", title: "SlopTotal",
      message: "Select at least 20 characters to analyze.",
    });
    return;
  }
  chrome.notifications.create("sloptotal-result", {
    type: "basic", iconUrl: "icons/icon128.png", title: "SlopTotal — Analyzing...",
    message: `Checking ${text.length} characters...`,
  });
  try {
    const apiUrl = await getApiUrl();
    const endpoint = text.length > 300 ? `${apiUrl}/api/paragraph-score` : `${apiUrl}/api/quick-score`;
    const t0 = performance.now();
    const resp = await fetch(endpoint, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).error || `HTTP ${resp.status}`);
    const data = await resp.json();
    const elapsed = Math.round(performance.now() - t0);
    let title, message;
    if (data.paragraphs) {
      title = `SlopTotal — ${data.overall_score}% ${data.overall_verdict.toUpperCase()}`;
      message = `${data.paragraph_count} paragraphs: ${data.ai_paragraph_count} flagged (${elapsed}ms)`;
    } else {
      title = `SlopTotal — ${data.score}% ${data.verdict.toUpperCase()}`;
      const engines = (data.engines || []).map((e) => `${e.engine.replace("classifier_", "")}: ${e.score}%`).join(", ");
      message = `Confidence: ${data.confidence} | ${elapsed}ms\n${engines}`;
    }
    chrome.notifications.create("sloptotal-result", { type: "basic", iconUrl: "icons/icon128.png", title, message });
  } catch (err) {
    chrome.notifications.create("sloptotal-result", {
      type: "basic", iconUrl: "icons/icon128.png", title: "SlopTotal — Error",
      message: err.message || "Analysis failed",
    });
  }
});

console.log("[BG] Service worker started");
