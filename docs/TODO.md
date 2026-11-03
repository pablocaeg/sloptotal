# TODO

Concrete next steps. Longer-range ideas are in [docs/VISION.md](VISION.md).

## Engines

- [ ] **Add Gradient** (`ShantanuT01/gradient-ai-text-detector`, MIT): RAID AUC
  0.998 without RAID training, literary bias 0.033. Load as float32, re-derive
  `ENGINE_WEIGHTS` on both corpora, report before/after. See
  [tests/eval/FINDINGS.md](../tests/eval/FINDINGS.md#newer-open-detectors-measured-standalone).
- [ ] Evaluate **Earlybird-fast** (84 ms/text) for the snippet path.
- [ ] Build an out-of-distribution corpus (not RAID) so RAID-trained models
  (TMR, tabularisai, GeorgeDrayson) can be judged fairly.
- [ ] Harness for prompted LLM detectors (distil-labs Gemma slop detector).
- [ ] Qwen / Gemma base models as Binoculars-style observer/performer pairs on
  high-RAM CPU servers.

## Site check

- [ ] More builders once their markers are verified (see
  [docs/SITE_FINGERPRINTS.md](SITE_FINGERPRINTS.md)).
- [ ] Render JavaScript-only pages (optional headless browser) so the copy of
  AI-builder sites can be scored.

## Infrastructure

- [x] `/health` reports engines that loaded, not only engines registered.
- [ ] Publish per-engine RAM and latency in `docs/MODELS.md`.

## Publishing and outreach

Ordered by how directly each one puts SlopTotal in front of people who would use
it. Every post leads with a measured finding, not with the tool.

- [ ] Set the repository's social preview to `docs/assets/social.jpg`, so links
  shared anywhere show the banner instead of GitHub's generic card.
- [ ] Write up the evaluation findings as an article on sloptotal.com: engines
  scoring backwards, networks loading with random weights, the literary bias
  table. It is the one piece of this project other people will want to share.
- [ ] Post it to r/LocalLLaMA (findings first) and r/MachineLearning as a `[P]`
  post (method first: two corpora, weights from Somers' D, the reproduction
  check), linking `tests/eval/FINDINGS.md`.
- [ ] Post to r/selfhosted around the Docker one-liner and the private,
  CPU-only angle.
- [ ] A Hugging Face Space running a lite profile, linked from the README. Every
  engine is a Hugging Face model, so that is where the likely users already are.
- [ ] Tell the authors of the measured models about their results (model page
  discussions), including the ones that scored well.
- [ ] Submit to awesome-selfhosted through its contribution process, and to
  curated lists of LLM and AI-safety tooling that accept self-hosted projects.
- [ ] One-click install templates for home-server platforms (Unraid, CasaOS,
  Umbrel), which carry their own app stores.
- [ ] Publish the Chrome extension on the Chrome Web Store.
- [ ] A second Show HN when Gradient lands, titled with the finding rather than
  the product.
- [ ] Write the evaluation up as a short paper or preprint; `CITATION.cff`
  already makes the repository citable.
- [ ] Announce every release on the same channels with its before/after
  numbers, so each one is a reason to come back.
