import pytest

from app.scraper import _extract_text_from_html, extract_html_features

ARTICLE = """
<html><head><title>Walking to work</title></head><body>
<nav><a href="/">Home</a><a href="/about">About</a></nav>
<article><h1>Walking to work</h1>
<p>Missed the bus again this morning, so I walked. It took forty minutes and my
left shoe has a hole I keep forgetting about until it rains.</p>
<p>Stopped at the bakery on Elm. They were out of rye, obviously, so I grabbed a
coffee that was mostly foam and kept going past the river.</p>
</article>
<footer>Copyright 2026</footer>
</body></html>
"""


def test_extracts_article_body_without_chrome():
    text = _extract_text_from_html(ARTICLE)
    assert "bakery on Elm" in text
    assert "Copyright" not in text


def test_html_features_are_a_dict():
    assert isinstance(extract_html_features(ARTICLE), dict)


def test_empty_javascript_app_shows_helpful_error():
    html = """
    <html>
      <head><script src="/assets/app.js"></script></head>
      <body><div id="root"></div></body>
    </html>
    """

    with pytest.raises(
        ValueError,
        match="This page has almost no text in its HTML",
    ):
        _extract_text_from_html(html)
