(function () {
    var data = document.getElementById("report-data");
    if (!data) return;

    var reportId = data.dataset.reportId;
    var total = parseInt(data.dataset.enginesTotal, 10);
    // Band edges and verdict names come from app/config.py via the template,
    // so the colours always agree with the verdict the server computed.
    var bands = (data.dataset.bands || "30,45,55,80").split(",").map(Number);
    var verdicts = (data.dataset.verdicts || "").split("|");
    var BANDS = ["clean", "low", "suspicious", "likely", "slop"];
    var done = 0;

    function bandIndex(score) {
        for (var i = 0; i < bands.length; i++) {
            if (score <= bands[i]) return i;
        }
        return bands.length;
    }

    function setScore(score, flagged, finished) {
        var b = bandIndex(score);
        document.getElementById("score-value").textContent = score.toFixed(1);
        document.getElementById("scale").style.setProperty("--score", score);
        document.querySelectorAll(".st-scale__band").forEach(function (el, i) {
            if (i === b) el.setAttribute("data-active", "");
            else el.removeAttribute("data-active");
        });
        var badge = document.getElementById("verdict");
        badge.className = "st-verdict st-verdict--" + BANDS[b];
        badge.textContent = verdicts[b] || "";
        badge.hidden = false;
        document.getElementById("summary").textContent = finished
            ? flagged + " of " + total + " engines flag this text on their own. The score weighs each engine by how accurate it measured."
            : done + " of " + total + " engines finished.";
    }

    function setRow(key, score, details) {
        var row = document.getElementById("row-" + key);
        if (!row) return;
        var v = score * 100;
        var bar = document.getElementById("bar-" + key);
        bar.style.setProperty("--v", v.toFixed(1));
        bar.dataset.band = BANDS[bandIndex(v)];
        var cell = document.getElementById("score-" + key);
        cell.textContent = v.toFixed(1);
        cell.classList.remove("st-engine__pending");
        if (details) row.title = details;
        if (parseFloat(row.dataset.score) < 0) done++;
        row.dataset.score = v;
        sortRows();
        document.getElementById("progress").textContent = done + " / " + total;
    }

    function sortRows() {
        var body = document.getElementById("engine-rows");
        Array.prototype.slice.call(body.rows)
            .sort(function (a, b) { return parseFloat(b.dataset.score) - parseFloat(a.dataset.score); })
            .forEach(function (row) { body.appendChild(row); });
    }

    // Highlight the stock phrases the Linguistic Markers engine quoted.
    function highlightMarkers(report) {
        var body = document.querySelector(".report-text__body");
        if (!body || !report || !report.engine_results) return;
        var lm = report.engine_results.filter(function (e) { return e.engine_name === "Linguistic Markers"; })[0];
        var markers = lm && lm.details ? (lm.details.match(/"([^"]+)"/g) || []).map(function (m) { return m.slice(1, -1); }) : [];
        if (!markers.length) return;
        var pattern = new RegExp("(" + markers.map(function (m) { return m.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }).join("|") + ")", "gi");
        var text = body.textContent;
        body.textContent = "";
        text.split(pattern).forEach(function (part, i) {
            if (i % 2 === 1) {
                var mark = document.createElement("mark");
                mark.textContent = part;
                body.appendChild(mark);
            } else {
                body.appendChild(document.createTextNode(part));
            }
        });
        var details = body.closest("details");
        if (details) details.open = true;
    }

    function finish(report) {
        highlightMarkers(report);
        var dot = document.getElementById("status-dot");
        dot.classList.remove("is-live");
        document.getElementById("status-label").textContent = "Complete";
        if (report) setScore(report.overall_score, report.engines_flagged, true);
        document.getElementById("feedback").hidden = false;
    }

    function loadReport() {
        return fetch("/api/report/" + reportId)
            .then(function (r) { return r.ok ? r.json() : null; })
            .catch(function () { return null; });
    }

    var date = document.getElementById("report-date");
    if (date && date.dataset.created) {
        var iso = date.dataset.created;
        var d = new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
        date.textContent = d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
    }

    var stream = new EventSource("/api/stream/" + reportId);
    stream.onmessage = function (event) {
        var msg = JSON.parse(event.data);
        if (msg.done) {
            stream.close();
            loadReport().then(finish);
            return;
        }
        setRow(msg.key, msg.score, msg.details);
        // Until the engines the score depends on are in, any number shown
        // would still move; show progress instead. Older servers send no
        // score_final, so they keep the running score.
        if (msg.score_final !== false) {
            setScore(msg.overall_score, msg.engines_flagged, false);
        } else {
            document.getElementById("summary").textContent = done + " of " + total + " engines finished.";
            // Where the score can still land, narrowing as the engines report.
            if (msg.score_range) {
                document.getElementById("score-value").textContent =
                    Math.round(msg.score_range[0]) + "\u2013" + Math.round(msg.score_range[1]);
            }
        }
    };
    // Model engines announce when they start, so the rows show what is running.
    stream.addEventListener("running", function (event) {
        var key = JSON.parse(event.data).key;
        var bar = document.getElementById("bar-" + key);
        var cell = document.getElementById("score-" + key);
        if (!bar || bar.dataset.band) return;
        bar.dataset.running = "";
        if (cell) cell.textContent = "Running";
        var row = document.getElementById("row-" + key);
        if (row && row.dataset.score === "-1") {
            row.dataset.score = "-0.5"; // above the engines still waiting
            sortRows();
        }
    });
    stream.onerror = function () {
        stream.close();
        loadReport().then(finish);
    };

    // ---- Copy link ----
    var copy = document.getElementById("copy-btn");
    // navigator.clipboard only exists on secure origins (HTTPS or localhost),
    // so on a LAN address we select a read-only field and let the user copy it.
    function showCopied() {
        copy.textContent = "Copied";
        setTimeout(function () { copy.textContent = "Copy link"; }, 2000);
    }
    function selectLinkForManualCopy(url) {
        var input = document.getElementById("copy-fallback");
        if (!input) {
            input = document.createElement("input");
            input.id = "copy-fallback";
            input.type = "text";
            input.readOnly = true;
            input.setAttribute("aria-label", "Report link");
            copy.parentNode.insertBefore(input, copy.nextSibling);
        }
        input.value = url;
        input.focus();
        input.select();
        var ok = false;
        try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
        if (ok) {
            input.remove();
            showCopied();
        } else {
            copy.textContent = "Press Ctrl+C to copy";
        }
    }
    copy.addEventListener("click", function () {
        var url = window.location.href;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url).then(showCopied, function () {
                selectLinkForManualCopy(url);
            });
        } else {
            selectLinkForManualCopy(url);
        }
    });

// ---- Feedback: who wrote this text? ----
    var feedback = document.getElementById("feedback");
    var status = document.getElementById("feedback-status");
    if (feedback) {
        var storageKey = "sloptotal:feedback:" + reportId;
        var savedLabel = null;
        try {
            savedLabel = localStorage.getItem(storageKey);
        } catch (e) {}

        var buttons = feedback.querySelectorAll("[data-label]");
        if (savedLabel) {
            buttons.forEach(function (b) {
                if (b.dataset.label === savedLabel) {
                    b.setAttribute("aria-pressed", "true");
                }
            });
            if (status) {
                status.textContent = "Your answer: " + savedLabel + ".";
            }
        }

        buttons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                var label = btn.dataset.label;
                fetch("/api/report/" + reportId + "/feedback", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ label: label }),
                })
                    .then(function (r) {
                        if (!r.ok) throw new Error("bad status");
                        buttons.forEach(function (b) {
                            b.removeAttribute("aria-pressed");
                        });
                        btn.setAttribute("aria-pressed", "true");
                        try {
                            localStorage.setItem(storageKey, label);
                        } catch (e) {}
                        if (status) {
                            status.textContent = "Thanks, your answer is saved.";
                        }
                    })
                    .catch(function () {
                        if (status) {
                            status.textContent = "Could not save your answer. Please try again.";
                        }
                    });
            });
        });
    }

    // ---- Website builder markers (URL reports only) ----
    var site = document.getElementById("site-check");
    if (site) {
        fetch("/api/scan/site", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: site.dataset.url, include_text: false }),
        })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) {
                if (!d || !d.site) return;
                var s = d.site;
                var names = s.builders.map(function (b) { return b.name; });
                document.getElementById("site-verdict").textContent = s.verdict;
                var list = document.getElementById("site-evidence");
                list.textContent = "";
                s.builders.forEach(function (b) {
                    b.evidence.forEach(function (ev) {
                        var li = document.createElement("li");
                        li.textContent = (names.length > 1 ? b.name + ": " : "") + ev;
                        list.appendChild(li);
                    });
                });
                if (s.generator) {
                    var li = document.createElement("li");
                    li.textContent = "Generator tag: " + s.generator;
                    list.appendChild(li);
                }
                site.hidden = false;
            })
            .catch(function () {});
    }
})();
