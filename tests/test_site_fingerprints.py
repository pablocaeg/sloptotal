"""Fixtures are trimmed from real deployments captured in September 2026."""

import pytest

from app.site_fingerprints import detect_builders

PLAIN = "<html><head><title>Bakery</title></head><body><p>Fresh rye daily.</p></body></html>"

LOVABLE_CUSTOM_DOMAIN = """<html><head>
<meta property="og:image" content="https://example.com/lovable-uploads/303a9808.webp" />
<script defer src="/~flock.js"></script>
<script type="module" crossorigin src="/assets/index-B14QSOwQ.js"></script>
</head><body><div id="root"></div></body></html>"""

LOVABLE_BADGE = '<a id="lovable-badge" href="https://lovable.dev"><span class="lovable-badge-text">Edit with Lovable</span></a>'

V0 = '<head><meta name="generator" content="v0.app"/><title>Portfolio</title></head>'

BOLT = """<head><script async src="https://bolt.new/badge.js?s=f67adf68"></script>
<script type="module" crossorigin src="/assets/index-B__YQx3w.js"></script></head>"""

BASE44 = '<script async="true" data-app-id="6a69" data-platform-url="https://app.base44.com" src="/static/js/badge.js"></script>'

REPLIT = '<script type="text/javascript" src="https://replit.com/public/js/replit-dev-banner.js"></script>'

EMERGENT = """<head><title>Emergent | Fullstack App</title>
<script src="https://assets.emergent.sh/scripts/emergent-main.js"></script>
<script defer="defer" src="/static/js/main.a9844d1b.js"></script></head>"""

# Response headers as the fetch layer returns them: httpx joins the two Set-Cookie
# headers of an emergent.host site into one comma-separated value.
EMERGENT_HEADERS = {
    "server": "cloudflare",
    "set-cookie": (
        "__emg_vid=00000000-0000-4000-8000-000000000000; Max-Age=31536000; Path=/; "
        "HttpOnly; Secure; SameSite=Lax, "
        "__emg_sid=00000000-0000-4000-8000-000000000000; Max-Age=1800; Path=/; "
        "HttpOnly; Secure; SameSite=Lax"
    ),
}


def names(result):
    return [b["name"] for b in result["builders"]]


def test_plain_site_has_no_fingerprints():
    r = detect_builders(PLAIN, "https://bakery.example")
    assert r["builders"] == []
    assert r["verdict"] == "No AI app builder fingerprints"


@pytest.mark.parametrize(
    "html,url,expected",
    [
        (LOVABLE_CUSTOM_DOMAIN, "https://ruznic-marketing.example", "Lovable"),
        (LOVABLE_BADGE, "https://example.com", "Lovable"),
        (V0, "https://portfolio.example", "v0"),
        (BOLT, "https://example.com", "Bolt"),
        (BASE44, "https://example.com", "Base44"),
        (REPLIT, "https://example.com", "Replit"),
        (PLAIN, "https://sondelicias.bolt.host/", "Bolt"),
        (PLAIN, "https://pennylane.lovable.app", "Lovable"),
        (EMERGENT, "https://example.com", "Emergent"),
        (PLAIN, "https://crop-cash-3.emergent.host/", "Emergent"),
        (PLAIN, "https://menuflow-8.preview.emergentagent.com/", "Emergent"),
    ],
)
def test_builder_is_confirmed(html, url, expected):
    r = detect_builders(html, url)
    assert names(r)[0] == expected
    assert r["builders"][0]["confidence"] == "confirmed"
    assert r["verdict"].startswith("Built with " + expected)


def test_header_fingerprint():
    r = detect_builders(
        PLAIN, "https://friendslikepigs.example", {"X-Powered-By": "Bolt.new"}
    )
    assert names(r) == ["Bolt"]


def test_lone_weak_signal_is_only_possible():
    r = detect_builders(
        '<script defer src="/~flock.js"></script>', "https://example.com"
    )
    assert r["builders"][0]["confidence"] == "possible"
    assert r["verdict"] == "Possibly built with Lovable"


def test_generator_tag_is_reported_even_for_non_ai_generators():
    r = detect_builders(
        '<meta name="generator" content="WordPress 6.8">', "https://x.example"
    )
    assert r["generator"] == "WordPress 6.8"
    assert r["builders"] == []


def test_lookalike_host_does_not_match():
    assert detect_builders(PLAIN, "https://notlovable.app")["builders"] == []


def test_emergent_cookie_header_fingerprint():
    """The cookies are set by the platform, so a custom domain whose HTML has lost
    the generated script still shows them."""
    r = detect_builders(PLAIN, "https://shop.example", EMERGENT_HEADERS)
    assert names(r) == ["Emergent"]
    assert r["builders"][0]["confidence"] == "confirmed"
    assert r["builders"][0]["evidence"] == ["Sets Emergent's __emg_sid session cookie"]


def test_emergent_is_not_named_from_look_alikes():
    """A cookie that only resembles the markers, or the badge text on its own, is
    not evidence: pages and articles about Emergent say 'Made with Emergent' too."""
    r = detect_builders(
        "<p>Made with Emergent</p>",
        "https://blog.example",
        {"set-cookie": "emg_session=abc; Path=/; HttpOnly"},
    )
    assert r["builders"] == []
