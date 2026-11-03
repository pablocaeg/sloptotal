"""Detect websites built with AI app builders (Lovable, v0, Bolt, ...).

Online "vibe-coded website" checkers mostly score style: Tailwind class counts,
missing security headers, buzzwords. Hand-written sites share all of those, so
the resulting percentages mean little. This module only reports fingerprints
that the builders themselves leave in what they deploy: generator tags, their
badge and runtime scripts, their asset paths, their hosting domains and
response headers. Each one was checked against live deployments or against the
templates the builders generate (see docs/SITE_FINGERPRINTS.md).

It reports evidence, not a probability. A site with no fingerprint may still
have been written with AI: code exported from these tools and deployed
elsewhere, or written in an AI editor, carries no marker at all.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(frozen=True)
class Signal:
    kind: str  # "host", "html" or "header"
    pattern: str  # regex (html/header) or domain suffix (host)
    evidence: str  # human-readable description shown in reports
    strong: bool = True  # one strong signal is enough to name the builder


@dataclass(frozen=True)
class Builder:
    name: str
    url: str
    signals: tuple[Signal, ...] = field(default_factory=tuple)


BUILDERS: tuple[Builder, ...] = (
    Builder(
        "Lovable",
        "https://lovable.dev",
        (
            Signal("host", ".lovable.app", "Hosted on lovable.app"),
            Signal("host", ".lovableproject.com", "Hosted on lovableproject.com"),
            Signal("html", r"cdn\.gpteng\.co/", "Loads Lovable's gptengineer runtime"),
            Signal(
                "html", r"/lovable-uploads/", "Serves assets from /lovable-uploads/"
            ),
            Signal("html", r"lovable-badge", "Carries the 'Edit with Lovable' badge"),
            Signal(
                "html",
                r"lovable\.dev/opengraph-image",
                "Uses Lovable's default social preview image",
            ),
            Signal(
                "html", r'content="@lovable_dev"', "Twitter card credits @lovable_dev"
            ),
            Signal(
                "html",
                r'src="/~flock\.js"',
                "Loads /~flock.js, served by Lovable hosting",
                strong=False,
            ),
        ),
    ),
    Builder(
        "v0",
        "https://v0.app",
        (
            Signal(
                "html",
                r'<meta[^>]+name="generator"[^>]+content="v0\.(app|dev)"',
                'Generator tag "v0.app", written by v0\'s layout template',
            ),
            Signal("host", ".vusercontent.net", "Hosted on v0's preview domain"),
        ),
    ),
    Builder(
        "Bolt",
        "https://bolt.new",
        (
            Signal(
                "header",
                r"x-powered-by:\s*bolt\.new",
                "Server header X-Powered-By: Bolt.new",
            ),
            Signal("host", ".bolt.host", "Hosted on bolt.host"),
            Signal("html", r"bolt\.new/badge\.js", "Carries the 'Made in Bolt' badge"),
            Signal(
                "html",
                r"bolt\.new/deployed-preview-script\.js",
                "Loads Bolt's deployed-preview script",
            ),
        ),
    ),
    Builder(
        "Base44",
        "https://base44.com",
        (
            Signal("host", ".base44.app", "Hosted on base44.app"),
            Signal("html", r"app\.base44\.com", "Points at the Base44 platform API"),
            Signal("html", r"base44_access_token", "Uses a Base44 access token"),
            Signal("html", r"base44\.com/images/public/", "Serves images from Base44"),
        ),
    ),
    Builder(
        "Replit",
        "https://replit.com",
        (
            Signal("host", ".replit.app", "Hosted on replit.app"),
            Signal("host", ".replit.dev", "Hosted on replit.dev"),
            Signal("host", ".repl.co", "Hosted on repl.co"),
            Signal(
                "html",
                r"replit\.com/public/js/replit-dev-banner\.js",
                "Loads the Replit Agent dev banner",
            ),
            Signal("html", r"replit-badge", "Carries the Replit badge"),
        ),
    ),
    Builder(
        "Same",
        "https://same.new",
        (Signal("html", r"same-assets\.com", "Serves assets from same-assets.com"),),
    ),
    Builder(
        "Anything (Create)",
        "https://www.createanything.com",
        (
            Signal("host", ".created.app", "Hosted on created.app"),
            Signal("html", r"create\.xyz", "References create.xyz", strong=False),
        ),
    ),
    Builder(
        "Emergent",
        "https://emergent.sh",
        (
            Signal("host", ".emergent.host", "Hosted on emergent.host"),
            Signal(
                "host",
                ".preview.emergentagent.com",
                "Hosted on Emergent's preview domain",
            ),
            Signal(
                "html",
                r"assets\.emergent\.sh/scripts/emergent-main\.js",
                "Loads Emergent's emergent-main.js script",
            ),
            Signal(
                "header",
                r"set-cookie:[^\n]*__emg_(?:sid|vid)=",
                "Sets Emergent's __emg_sid session cookie",
            ),
        ),
    ),
)

_GENERATOR_RE = re.compile(
    r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']{1,80})["\']', re.I
)


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix.lstrip(".") or host.endswith(suffix)


def detect_builders(html: str, url: str = "", headers: dict | None = None) -> dict:
    """Return the AI app builders whose fingerprints appear in a page.

    `headers` are the response headers of the final URL. The result is
    JSON-serialisable:

        {"builders": [{"name", "url", "confidence", "evidence": [...]}],
         "generator": "v0.app" | None,
         "verdict": "Built with Lovable" | "No AI app builder fingerprints"}
    """
    host = (urlparse(url).hostname or "").lower()
    header_text = "\n".join(f"{k}: {v}" for k, v in (headers or {}).items()).lower()

    found = []
    for builder in BUILDERS:
        evidence, strong = [], False
        for sig in builder.signals:
            if sig.kind == "host":
                hit = bool(host) and _host_matches(host, sig.pattern)
            elif sig.kind == "header":
                hit = re.search(sig.pattern, header_text, re.I) is not None
            else:
                hit = re.search(sig.pattern, html, re.I) is not None
            if hit:
                evidence.append(sig.evidence)
                strong = strong or sig.strong
        if evidence:
            found.append(
                {
                    "name": builder.name,
                    "url": builder.url,
                    # Two independent fingerprints, or one strong one, is enough to
                    # name the builder; a lone weak hint is reported as possible.
                    "confidence": "confirmed"
                    if strong or len(evidence) > 1
                    else "possible",
                    "evidence": evidence,
                }
            )

    found.sort(key=lambda b: (b["confidence"] != "confirmed", -len(b["evidence"])))
    gen = _GENERATOR_RE.search(html)
    confirmed = [b["name"] for b in found if b["confidence"] == "confirmed"]
    if confirmed:
        verdict = "Built with " + " + ".join(confirmed)
    elif found:
        verdict = "Possibly built with " + found[0]["name"]
    else:
        verdict = "No AI app builder fingerprints"
    return {
        "builders": found,
        "generator": gen.group(1).strip() if gen else None,
        "verdict": verdict,
    }
