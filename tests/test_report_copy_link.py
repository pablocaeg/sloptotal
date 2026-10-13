from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_copy_link_falls_back_when_clipboard_api_is_unavailable():
    # Static check: the browser behaviour needs a real page, so this pins the
    # fallback branches that keep "Copy link" working on non-HTTPS LAN origins.
    source = (ROOT / "web/static/js/report.js").read_text(encoding="utf-8")
    assert "navigator.clipboard && navigator.clipboard.writeText" in source
    assert 'document.execCommand("copy")' in source
    assert "Press Ctrl+C to copy" in source
