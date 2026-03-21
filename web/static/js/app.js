document.addEventListener("DOMContentLoaded", () => {
    // ---- Tab switching with animation ----
    const tabs = document.querySelectorAll(".tab");
    const tabContents = document.querySelectorAll(".tab-content");

    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => {
                t.classList.remove("active");
                t.setAttribute("aria-selected", "false");
            });
            tabContents.forEach(tc => tc.classList.remove("active"));
            tab.classList.add("active");
            tab.setAttribute("aria-selected", "true");

            const panel = document.getElementById(tab.dataset.tab);
            panel.classList.add("active");

            // Focus the input in the new tab
            const input = panel.querySelector("input, textarea");
            if (input) input.focus();

            // Clear inactive inputs
            if (tab.dataset.tab === "url-tab") {
                const ti = document.getElementById("text-input");
                if (ti) ti.value = "";
            } else {
                const ui = document.getElementById("url-input");
                if (ui) ui.value = "";
            }
        });
    });

    // ---- Queue-aware form submission ----
    const form = document.getElementById("analyze-form");
    let queueAbort = null;

    if (form) {
        form.addEventListener("submit", function(e) {
            e.preventDefault();

            const btn = document.getElementById("submit-btn");
            btn.disabled = true;
            btn.querySelector(".btn-text").style.display = "none";
            btn.querySelector(".btn-loading").style.display = "inline-flex";

            // Gather form data
            const urlInput = document.getElementById("url-input");
            const textInput = document.getElementById("text-input");
            const body = {};
            if (urlInput && urlInput.value.trim()) {
                body.url = urlInput.value.trim();
            } else if (textInput && textInput.value.trim()) {
                body.text = textInput.value.trim();
            }

            queueAbort = new AbortController();

            fetch("/api/web/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
                signal: queueAbort.signal,
            })
            .then(function(resp) {
                if (resp.status === 200) {
                    return resp.json().then(function(data) {
                        // Immediate — redirect to report
                        window.location.href = "/report/" + data.report_id;
                    });
                }
                if (resp.status === 202) {
                    return resp.json().then(function(data) {
                        // Queued — show queue overlay and start polling
                        showQueueOverlay(data);
                        startQueuePolling(data.ticket_id);
                    });
                }
                // Error responses
                return resp.json().then(function(data) {
                    showFormError(data.error || "Something went wrong. Please try again.");
                    resetButton();
                });
            })
            .catch(function(err) {
                if (err.name === "AbortError") return;
                showFormError("Could not reach the server. Is it running?");
                resetButton();
            });
        });
    }

    function resetButton() {
        var btn = document.getElementById("submit-btn");
        if (!btn) return;
        btn.disabled = false;
        btn.querySelector(".btn-text").style.display = "inline-flex";
        btn.querySelector(".btn-loading").style.display = "none";
    }

    function showFormError(message) {
        // Remove existing error banner
        var existing = document.querySelector(".error-banner");
        if (existing) existing.remove();

        var banner = document.createElement("div");
        banner.className = "error-banner";
        banner.setAttribute("role", "alert");
        banner.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.5v4M8 10.5v1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg> '
            + message.replace(/</g, "&lt;");

        var card = document.querySelector(".input-card--hero");
        if (card) card.parentElement.insertBefore(banner, card);
    }

    function showQueueOverlay(data) {
        var overlay = document.getElementById("queue-overlay");
        if (!overlay) return;

        var pos = data.position || 1;
        var wait = data.estimated_wait_ms || 5000;

        document.getElementById("queue-position").textContent = pos;
        document.getElementById("queue-title").textContent =
            pos === 1 ? "You\u2019re next" : "Position #" + pos + " in queue";
        document.getElementById("queue-desc").textContent =
            "Your analysis will start shortly.";

        var waitSec = Math.ceil(wait / 1000);
        document.getElementById("queue-wait").textContent =
            "Estimated wait: ~" + waitSec + "s";

        overlay.style.display = "flex";
    }

    function hideQueueOverlay() {
        var overlay = document.getElementById("queue-overlay");
        if (overlay) overlay.style.display = "none";
    }

    function updateQueueOverlay(data) {
        var pos = data.position || 1;
        var wait = data.estimated_wait_ms || 3000;

        document.getElementById("queue-position").textContent = pos;
        document.getElementById("queue-title").textContent =
            pos === 1 ? "You\u2019re next" : "Position #" + pos + " in queue";

        if (data.status === "processing") {
            document.getElementById("queue-title").textContent = "Processing\u2026";
            document.getElementById("queue-desc").textContent =
                "Your analysis is running now.";
            document.getElementById("queue-wait").textContent = "";
        } else {
            var waitSec = Math.ceil(wait / 1000);
            document.getElementById("queue-wait").textContent =
                "Estimated wait: ~" + waitSec + "s";
        }
    }

    function startQueuePolling(ticketId) {
        var attempts = 0;
        var maxAttempts = 120; // 60 seconds at 500ms

        function poll() {
            if (attempts >= maxAttempts) {
                hideQueueOverlay();
                showFormError("Queue timed out. Please try again.");
                resetButton();
                return;
            }
            attempts++;

            fetch("/api/queue/ticket/" + ticketId, { signal: queueAbort.signal })
                .then(function(resp) {
                    if (resp.status === 200) {
                        // Result ready — should contain report_id
                        return resp.json().then(function(data) {
                            if (data.report_id) {
                                window.location.href = "/report/" + data.report_id;
                            } else {
                                // Unexpected format — try again
                                setTimeout(poll, 500);
                            }
                        });
                    }
                    if (resp.status === 202) {
                        return resp.json().then(function(data) {
                            updateQueueOverlay(data);
                            setTimeout(poll, 500);
                        });
                    }
                    if (resp.status === 404) {
                        hideQueueOverlay();
                        showFormError("Queue ticket expired. Please try again.");
                        resetButton();
                    }
                })
                .catch(function(err) {
                    if (err.name === "AbortError") return;
                    // Network error — retry
                    setTimeout(poll, 1000);
                });
        }

        setTimeout(poll, 500);
    }

    // Cancel button
    var cancelBtn = document.getElementById("queue-cancel");
    if (cancelBtn) {
        cancelBtn.addEventListener("click", function() {
            if (queueAbort) queueAbort.abort();
            hideQueueOverlay();
            resetButton();
        });
    }

    // ---- Recent scans ticker ----
    (function initTicker() {
        const ticker = document.getElementById("ticker");
        const scroll = document.getElementById("ticker-scroll");
        if (!ticker || !scroll) return;

        function scoreClass(s) {
            if (s <= 20) return "ti-clean";
            if (s <= 40) return "ti-low";
            if (s <= 60) return "ti-warn";
            if (s <= 80) return "ti-danger";
            return "ti-slop";
        }

        function buildItems(reports) {
            return reports.map(function(r) {
                var src = r.source.length > 55 ? r.source.substring(0, 55) + "\u2026" : r.source;
                return '<a href="/report/' + r.id + '" class="ticker-item">'
                    + '<span class="ti-score ' + scoreClass(r.overall_score) + '">' + r.overall_score.toFixed(1) + '</span>'
                    + '<span class="ti-source">' + src.replace(/</g, "&lt;") + '</span>'
                    + '<span class="ti-verdict">' + r.overall_verdict + '</span>'
                    + '<span class="ti-time">' + r.created_at + '</span>'
                    + '</a>';
            }).join("");
        }

        fetch("/api/recent")
            .then(function(r) { return r.json(); })
            .then(function(reports) {
                if (!reports.length) return;
                // Duplicate items for seamless loop
                var html = buildItems(reports);
                scroll.innerHTML = html + html;
                // Adjust speed: ~4s per item
                var dur = Math.max(reports.length * 4, 16);
                scroll.style.animationDuration = dur + "s";
                ticker.style.display = "flex";
            })
            .catch(function() {});
    })();

    // ---- Intersection Observer for scroll animations ----
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add("in-view");
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll(".how-step, .engine-card").forEach(el => {
        observer.observe(el);
    });

    // ---- Score bar coloring on report page ----
    document.querySelectorAll(".score-bar").forEach(bar => {
        const score = parseFloat(bar.dataset.score);
        if (score < 0.4) bar.style.background = "var(--c-clean)";
        else if (score < 0.65) bar.style.background = "var(--c-warn)";
        else bar.style.background = "var(--c-slop)";
    });

    // ---- Gauge coloring ----
    const gaugeFill = document.querySelector(".gauge-fill");
    if (gaugeFill) {
        const score = parseFloat(gaugeFill.dataset.score);
        let color;
        if (score <= 20) color = "var(--c-clean)";
        else if (score <= 40) color = "var(--c-low)";
        else if (score <= 60) color = "var(--c-warn)";
        else if (score <= 80) color = "var(--c-danger)";
        else color = "var(--c-slop)";
        gaugeFill.style.stroke = color;
    }

    const gaugeNumber = document.querySelector(".gauge-number");
    if (gaugeNumber) {
        const score = parseFloat(gaugeNumber.dataset.score);
        let color;
        if (score <= 20) color = "var(--c-clean)";
        else if (score <= 40) color = "var(--c-low)";
        else if (score <= 60) color = "var(--c-warn)";
        else if (score <= 80) color = "var(--c-danger)";
        else color = "var(--c-slop)";
        gaugeNumber.style.color = color;
    }
});
