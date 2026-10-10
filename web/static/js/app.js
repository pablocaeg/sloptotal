(function () {
    var form = document.getElementById("analyze-form");
    if (!form) return;

    var SAMPLE = "In today’s fast-paced digital landscape, effective communication has never been more important. Whether you are collaborating with a remote team or engaging with customers across the globe, the ability to convey ideas clearly can make all the difference. Moreover, clear communication fosters trust, enhances productivity, and ultimately drives success. By embracing best practices such as active listening, concise messaging, and regular feedback, organizations can unlock their full potential. In conclusion, investing in communication skills is not just a nice-to-have; it is a strategic imperative that empowers individuals and teams to thrive in an ever-evolving world.";
    var SHORT_WORDS = 80;
    var SUBMIT = { text: "Analyse text", document: "Analyse text", url: "Analyse page", site: "Check website" };

    var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"][data-tab]'));
    var textInput = document.getElementById("text-input");
    var urlInput = document.getElementById("url-input");
    var siteInput = document.getElementById("site-input");
    var meta = document.getElementById("tool-meta");
    var submit = document.getElementById("submit-btn");
    var sampleBtn = document.getElementById("sample-btn");
    var current = "text";
    var queueAbort = null;

    // ---- Tabs (arrow keys move between them, as in the WAI-ARIA pattern) ----
    function selectTab(name, focus) {
        current = name;
        tabs.forEach(function (tab) {
            var on = tab.dataset.tab === name;
            tab.setAttribute("aria-selected", on ? "true" : "false");
            tab.tabIndex = on ? 0 : -1;
            document.getElementById(tab.getAttribute("aria-controls")).hidden = !on;
            if (on && focus) tab.focus();
        });
        // Only the active field is submitted.
        urlInput.disabled = name !== "url";
        textInput.disabled = name !== "text";
        submit.textContent = SUBMIT[name];
        sampleBtn.hidden = name !== "text";
        hideNotice();
        updateMeta();
    }
    tabs.forEach(function (tab, i) {
        tab.addEventListener("click", function () { selectTab(tab.dataset.tab, false); });
        tab.addEventListener("keydown", function (e) {
            var next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
            if (next === undefined) return;
            e.preventDefault();
            selectTab(tabs[(next + tabs.length) % tabs.length].dataset.tab, true);
        });
    });

    // ---- Word count ----
    function countWords(text) {
        // CJK and Thai have no spaces: count their characters one by one.
        var dense = (text.match(/[぀-ヿ㐀-鿿가-힯฀-๿]/g) || []).length;
        var spaced = text.replace(/[぀-ヿ㐀-鿿가-힯฀-๿]/g, " ").trim();
        return dense + (spaced ? spaced.split(/\s+/).length : 0);
    }
    function updateMeta() {
        if (current !== "text") { meta.textContent = ""; return; }
        var n = countWords(textInput.value);
        meta.textContent = n === 0 ? "Paste at least 80 words for a reliable score."
            : n.toLocaleString() + (n === 1 ? " word" : " words") + (n < SHORT_WORDS ? ". Under 80 words the score is a weak signal." : "");
    }
    // The text box grows a ruled line at a time (6 to 12 lines), so the last
    // line is never cut in half.
    function fitText() {
        var cs = getComputedStyle(textInput);
        var line = parseFloat(cs.lineHeight) || 30;
        var pad = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
        var borders = parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
        textInput.style.height = "auto";
        var lines = Math.min(12, Math.max(6, Math.ceil((textInput.scrollHeight - pad) / line)));
        textInput.style.height = lines * line + pad + borders + "px";
    }
    textInput.addEventListener("input", function () { updateMeta(); fitText(); });

    sampleBtn.addEventListener("click", function () {
        textInput.value = SAMPLE;
        updateMeta();
        fitText();
        textInput.focus();
    });

    // Ctrl+Enter or Cmd+Enter submits from any field.
    form.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            form.requestSubmit();
        }
    });

    // ---- Notices ----
    var notice = document.getElementById("tool-notice");
    function showNotice(message) {
        document.getElementById("tool-notice-text").textContent = message;
        notice.hidden = false;
    }
    function hideNotice() { notice.hidden = true; }

    function busy(on) {
        submit.disabled = on;
        submit.setAttribute("aria-busy", on ? "true" : "false");
    }

    // ---- Documents: extract the text on the server, then show it in the Text tab ----
    var fileInput = document.getElementById("file-input");
    var drop = document.getElementById("drop-zone");
    var uploadStatus = document.getElementById("upload-status");
    var TYPES_HINT = uploadStatus.textContent;
    function readFile(file) {
        if (!file) return;
        uploadStatus.textContent = "Reading " + file.name + "…";
        var body = new FormData();
        body.append("file", file);
        fetch("/api/extract", { method: "POST", body: body })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
            .then(function (res) {
                if (!res.ok || !res.d.text) throw new Error(res.d && res.d.error);
                uploadStatus.textContent = TYPES_HINT;
                textInput.value = res.d.text;
                selectTab("text", false);
                meta.textContent = "Loaded " + file.name + ". Check the text, then analyse it.";
                textInput.focus();
            })
            .catch(function (err) {
                uploadStatus.textContent = TYPES_HINT;
                showNotice((err && err.message) || "That file could not be read. Use a .pdf, .docx, .txt or .md file under 10 MB.");
            })
            .finally(function () { fileInput.value = ""; });
    }
    fileInput.addEventListener("change", function () { readFile(fileInput.files && fileInput.files[0]); });
    ["dragenter", "dragover"].forEach(function (type) {
        drop.addEventListener(type, function (e) { e.preventDefault(); drop.classList.add("is-dragging"); });
    });
    ["dragleave", "drop"].forEach(function (type) {
        drop.addEventListener(type, function () { drop.classList.remove("is-dragging"); });
    });
    drop.addEventListener("drop", function (e) {
        e.preventDefault();
        readFile(e.dataTransfer.files && e.dataTransfer.files[0]);
    });

    // ---- Submit ----
    form.addEventListener("submit", function (e) {
        e.preventDefault();
        hideNotice();
        if (current === "document") { fileInput.click(); return; }
        if (current === "site") { runSiteCheck(siteInput.value.trim()); return; }

        var body = {};
        if (current === "url") {
            var url = urlInput.value.trim();
            if (!/^https?:\/\/\S+\.\S+/.test(url)) { showNotice("Enter the address of a page, starting with https://"); urlInput.focus(); return; }
            body.url = url;
        } else {
            if (!textInput.value.trim()) { showNotice("Paste some text to analyse."); textInput.focus(); return; }
            body.text = textInput.value.trim();
        }

        busy(true);
        queueAbort = new AbortController();
        fetch("/api/web/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            signal: queueAbort.signal,
        })
            .then(function (resp) {
                return resp.json().then(function (data) {
                    if (resp.status === 200) { window.location.href = "/report/" + data.report_id; return; }
                    if (resp.status === 202) { showQueue(data); pollQueue(data.ticket_id); return; }
                    showNotice(data.error || "Something went wrong. Please try again.");
                    busy(false);
                });
            })
            .catch(function (err) {
                if (err.name === "AbortError") return;
                showNotice("Could not reach the server. Is it running?");
                busy(false);
            });
    });

    // ---- Queue ----
    var overlay = document.getElementById("queue-overlay");
    function showQueue(data) { updateQueue(data); overlay.hidden = false; document.getElementById("queue-cancel").focus(); }
    function hideQueue() { overlay.hidden = true; }
    function updateQueue(data) {
        var pos = data.position || 1;
        var title = document.getElementById("queue-title");
        var desc = document.getElementById("queue-desc");
        var wait = document.getElementById("queue-wait");
        if (data.status === "processing") {
            title.textContent = "Processing…";
            desc.textContent = "Your analysis is running now.";
            wait.textContent = "";
            return;
        }
        title.textContent = pos === 1 ? "You’re next" : "Position #" + pos + " in queue";
        desc.textContent = "All engines are busy. Your report opens as soon as it is your turn.";
        wait.textContent = "Estimated wait: ~" + Math.ceil((data.estimated_wait_ms || 5000) / 1000) + "s";
    }
    function pollQueue(ticketId) {
        var attempts = 0;
        function poll() {
            if (++attempts > 240) {
                hideQueue(); busy(false);
                showNotice("The queue timed out. Please try again.");
                return;
            }
            fetch("/api/queue/ticket/" + ticketId, { signal: queueAbort.signal })
                .then(function (resp) {
                    if (resp.status === 404) { hideQueue(); busy(false); showNotice("The queue ticket expired. Please try again."); return; }
                    return resp.json().then(function (data) {
                        if (resp.status === 200 && data.report_id) { window.location.href = "/report/" + data.report_id; return; }
                        updateQueue(data);
                        setTimeout(poll, 500);
                    });
                })
                .catch(function (err) { if (err.name !== "AbortError") setTimeout(poll, 1000); });
        }
        setTimeout(poll, 500);
    }
    document.getElementById("queue-cancel").addEventListener("click", function () {
        if (queueAbort) queueAbort.abort();
        hideQueue();
        busy(false);
        submit.focus();
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !overlay.hidden) document.getElementById("queue-cancel").click();
    });

    // ---- Website builder check ----
    function runSiteCheck(url) {
        if (!url) { showNotice("Enter a website to check."); siteInput.focus(); return; }
        busy(true);
        fetch("/api/scan/site", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: url }),
        })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
            .then(function (res) {
                if (!res.ok) { showNotice(res.d.error || res.d.detail || "Could not check that site."); return; }
                renderSite(res.d);
            })
            .catch(function () { showNotice("Could not reach the server. Is it running?"); })
            .finally(function () { busy(false); });
    }
    function renderSite(d) {
        var box = document.getElementById("site-result");
        var s = d.site;
        var several = s.builders.length > 1;
        document.getElementById("site-result-host").textContent = new URL(d.final_url).hostname;
        document.getElementById("site-result-verdict").textContent = s.verdict;
        var list = document.getElementById("site-result-evidence");
        list.textContent = "";
        s.builders.forEach(function (b) {
            b.evidence.forEach(function (ev) {
                var li = document.createElement("li");
                li.textContent = (several ? b.name + ": " : "") + ev;
                list.appendChild(li);
            });
        });
        if (s.generator) {
            var li = document.createElement("li");
            li.textContent = "Generator tag: " + s.generator;
            list.appendChild(li);
        }
        var text = document.getElementById("site-result-text");
        var full = document.getElementById("site-result-full");
        if (d.text) {
            var reads = { clean: "reads as human-written", mixed: "shows mixed signals", ai: "reads as AI-generated" };
            text.textContent = "The page copy (" + d.text.word_count + " words) " + (reads[d.text.verdict] || "was scored") + " on the quick scan.";
            full.hidden = false;
            full.onclick = function () {
                selectTab("url", false);
                urlInput.value = d.final_url;
                form.requestSubmit();
            };
        } else {
            text.textContent = "The page has too little server-rendered text to score its copy.";
            full.hidden = true;
        }
        box.hidden = false;
        box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    selectTab("text", false);
})();
