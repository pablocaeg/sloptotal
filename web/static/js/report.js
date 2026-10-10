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
        if (row.dataset.score === "-1") done++;
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
        setScore(msg.overall_score, msg.engines_flagged, false);
    };
    stream.onerror = function () {
        stream.close();
        loadReport().then(finish);
    };

    // ---- Copy link ----
    var copy = document.getElementById("copy-btn");
    copy.addEventListener("click", function () {
        navigator.clipboard.writeText(window.location.href).then(function () {
            copy.textContent = "Copied";
            setTimeout(function () { copy.textContent = "Copy link"; }, 2000);
        });
    });

    // ---- Feedback: who wrote this text? ----
    var feedback = document.getElementById("feedback");
    var status = document.getElementById("feedback-status");
    feedback.querySelectorAll("[data-label]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            fetch("/api/report/" + reportId + "/feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ label: btn.dataset.label }),
            })
                .then(function (r) {
                    if (!r.ok) throw new Error();
                    feedback.querySelectorAll("[data-label]").forEach(function (b) {
                        b.setAttribute("aria-pressed", b === btn ? "true" : "false");
                    });
                    status.textContent = "Thanks, your answer is saved.";
                })
                .catch(function () { status.textContent = "Could not save your answer. Please try again."; });
        });
    });

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
