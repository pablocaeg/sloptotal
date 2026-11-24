from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_report_shows_elapsed_time_and_a_polite_long_wait_note():
    # Static check, like test_report_copy_link: the behaviour needs a real page.
    page = (ROOT / "web/templates/report.html").read_text(encoding="utf-8")
    script = (ROOT / "web/static/js/report.js").read_text(encoding="utf-8")

    # The ticking timer must stay out of the live region, so only the single
    # note is announced.
    wait = page[page.index('id="report-wait"') : page.index('id="wait-note"')]
    assert 'id="elapsed" aria-hidden="true"' in wait
    assert 'id="wait-note" aria-live="polite"' in page

    assert "LONG_WAIT_SECONDS = 30" in script
    assert "Long texts can take a couple of minutes" in script
    # The timer stops once the report is complete.
    assert "clearInterval(waitTimer)" in script
    assert script.index("stopWait();") > script.index("function finish(report)")
