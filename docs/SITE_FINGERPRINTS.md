# Site fingerprints: how builder detection was verified

`app/site_fingerprints.py` names the AI app builder behind a website only from
markers the builder itself leaves in what it deploys. This file records where
each marker was confirmed, so a signal is never added on a hunch. Checked
September 2026; Emergent checked October 2026.

## Method

1. Collect real deployments: subdomains of each builder's hosting domain from
   certificate-transparency logs (crt.sh), plus custom domains serving the same
   deployment.
2. Fetch each live site and record generator tags, script sources, asset paths
   and response headers.
3. Cross-check against source: GitHub code search for the marker in the files
   the builder generates (`index.html`, `app/layout.tsx`, `vite.config.ts`).
4. Keep only markers that appear in deployed output, not in dev-only config
   (for example `lovable-tagger` runs only in the Vite dev server, so it is not
   used).

## Evidence

| Builder | Marker | Where confirmed |
|---|---|---|
| Lovable | `cdn.gpteng.co/gptengineer.js` | ~35k `index.html` files on GitHub; live `*.lovable.app` sites |
| Lovable | `/lovable-uploads/` asset path | live sites on `*.lovable.app` and on custom domains |
| Lovable | `lovable-badge` element | live `*.lovable.app` sites |
| Lovable | `/~flock.js` (weak on its own) | live Lovable-hosted sites, including custom domains |
| Lovable | default OG image `lovable.dev/opengraph-image`, `@lovable_dev` card | live `*.lovable.app` sites |
| v0 | `<meta name="generator" content="v0.app">` (older: `v0.dev`) | ~25k `app/layout.tsx` files with `generator: "v0.app"`; live on `*.vercel.app` |
| Bolt | `X-Powered-By: Bolt.new` response header | every live `*.bolt.host` site sampled |
| Bolt | `bolt.new/badge.js`, `bolt.new/deployed-preview-script.js` | live `*.bolt.host` sites |
| Base44 | `data-platform-url="https://app.base44.com"`, `base44_access_token`, `base44.com/images/public/` | live `*.base44.app` sites |
| Replit | `replit.com/public/js/replit-dev-banner.js` | ~6.8k `index.html` files on GitHub |
| Replit | `replit-badge` | ~2k `index.html` files on GitHub |
| Same | `same-assets.com` asset host | ~4k files on GitHub |
| Anything | `*.created.app` host; `create.xyz` reference (weak) | GitHub code search |
| Emergent | `*.emergent.host` host | 82 live sites sampled, October 2026 |
| Emergent | `__emg_vid` and `__emg_sid` response cookies (set by the platform, so present even when the generated HTML is replaced) | 55 of 82 live `*.emergent.host` sites; none of 15 other sites checked as controls |
| Emergent | `assets.emergent.sh/scripts/emergent-main.js` script | 38 of 82 live `*.emergent.host` sites; ~2,250 `index.html` files on GitHub |
| Emergent | `*.preview.emergentagent.com` host (the preview domain) | 25 live preview sites |

A builder is reported as **confirmed** on one strong marker or any two markers,
and as **possible** on a single weak one.

## What this cannot tell you

- Code exported from these tools and deployed on ordinary hosting, or written
  in an AI editor (Cursor, Copilot, Claude Code), carries no marker. "No
  fingerprints" is not evidence of hand-written code.
- Markers can be removed by the site owner.
- The Emergent cookies and script were confirmed on `*.emergent.host` sites only.
  On a custom domain that Emergent serves they should appear too, but no live one
  was available to confirm. Without the hosting domain, 55 of the 82 sampled sites
  still carry a fingerprint, so a third of them would show none.
- Style signals used by other checkers (Tailwind class density, missing
  security headers, gradient heroes) are deliberately not used: hand-built
  sites share them, and no one has published a measurement showing they
  separate AI-built sites from others.

## Adding a builder

Confirm the marker on at least three live deployments or in the builder's
generated template, add it to `BUILDERS`, add a trimmed real fixture to
`tests/test_site_fingerprints.py`, and extend the table above.
