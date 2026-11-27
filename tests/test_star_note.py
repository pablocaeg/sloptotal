"""The "star the repo" invitations stay out of the way and out of the API."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_report_star_note_is_hidden_until_the_second_report_and_remembers_dismissal():
    # Static check: the browser behaviour needs a real page. The note starts
    # hidden, counts distinct reports and stays closed via localStorage.
    template = (ROOT / "web/templates/report.html").read_text(encoding="utf-8")
    source = (ROOT / "web/static/js/report.js").read_text(encoding="utf-8")
    assert '<div class="star-note" id="star-note" hidden>' in template
    assert "if (seen.length < 2) return;" in source
    assert "localStorage.getItem(dismissKey)" in source
    assert (
        "fetch("
        not in source.split("function maybeShowStarNote")[1].split("\n    }\n")[0]
    )


def test_api_code_never_mentions_the_star_invitation():
    for path in [*(ROOT / "app/routes").glob("*.py"), ROOT / "app/schemas.py"]:
        text = path.read_text(encoding="utf-8")
        assert "STAR_LINE" not in text, path
        assert "github.com/pablocaeg/sloptotal" not in text, path
