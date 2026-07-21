---
name: export-gate
description: Use when export-artifact has produced exports/<slug>-itinerary.md and the rendered deliverable must be validated before the pipeline completes. Produces export-gate-report.yaml.
---

# export-gate — mechanical post-export check

Validates the **rendered deliverable** `trips/<slug>/exports/<slug>-itinerary.md`.
Upstream `itinerary-gate` runs on the pre-link synthesis intermediate and cannot
see render-layer defects; this gate closes that gap. Format/structure only —
content correctness is guaranteed upstream by `source-verify`.

## Checks (logic in `scripts/export_gate.py::run_export_gate`)

- `no_naked_dollar` — no unescaped `$` (prices must be `\$`); a bare `$...$` pair
  triggers KaTeX math mode and breaks the preview.
- `links_well_formed` — every `[label](target)` target is a non-empty `http(s)://` URL.
- `poi_name_is_link` — no standalone `[地圖]` / `[Map]` token; the POI name itself
  is the link.
- `bookable_has_official_source` — every `booking.required` verified POI present in
  the file carries an official source link on its row.
- `japanese_glossed` — a kana run on a line must carry a （中文）gloss; an inline
  Japanese term left untranslated for the reader is a hard fail.
- `no_internal_jargon` — no internal `(poi-id)` token or literal `must_do` in the rendered
  text. **Content hygiene (`japanese_glossed` + `no_internal_jargon`) is primarily enforced
  at the canonical layer in `itinerary-gate`** (over the unescaped row text/checklist, so it
  protects every renderer); these render-side copies are defense-in-depth.
- `photo_has_attribution` — any POI carrying a `photo` must also carry a non-empty
  `photo_attribution` (author + license + source_url).
- `no_nondistributable_photo_source` — a POI carrying `photo_source: google` has no
  display-surface ToS clearance. **This is NOT a hard fail (P7):** it is a labelling
  decision re-rendering can never fix, so it sets the report's `distributable: false`
  (a clean terminal "personal variant complete" state) while `status` stays `pass`. A
  distributable export reports `distributable: true`.

The html deliverable `exports/<slug>-itinerary.html` is validated by
`scripts/export_gate.py::run_html_gate` (structure/format only: non-empty, at least
`min_days` day-cards, every `href` an `http(s)://` URL, no raw `<script>`, every
`<img src>` a `data:image/` or `https://` URL, plus the photo checks above).

- `media_landed` (html, P8) — when a `verified-pois-media.yaml` side-file is present, its
  entry count is checked against the rendered HTML. If that count is > 0 but the
  rendered HTML has **0 `<img>`**, the gate fails ("media side-file present but rendered
  deliverable has 0 photos") — catching a dropped `apply_media` return that silently shipped
  a photoless page.

## Family/Public Completeness Contract

`export-gate-report status: pass` is the core export hygiene pass. It is **not
sufficient** to claim a family/public HTML deliverable is ready unless the trip
declares a family/public contract and that contract also passes.

When the requested deliverable is a shareable family/public HTML page, create
`trips/<slug>/family-public-contract.yaml` before running this gate. The CLI loads
that file, runs `scripts/family_public_gate.py::run_family_public_gate`, and merges
the result into `export-gate-report.yaml` with `family_` check names and `family:`
failure prefixes.

Minimum contract shape:

```yaml
min_days: 5
html_path: exports/<slug>-itinerary.html
expected_location_keys:
  - sukayu-onsen
required_meal_ids:
  - d1-lunch
provided_meal_ids:
  - hotel-breakfast
required_restaurant_fields:
  - 菜系
  - 距離
  - 來源
  - 地圖
  - 特色
  - 為什麼選
  - 招牌
  - 人均
```

For HTML generated outside `exports/`, set `html_path` relative to
`trips/<slug>/`.

The family gate enforces the public-page contract:

- every expected place appears via `data-location-key` and has a safe real
  `<img>` plus visible `.photo-credit`;
- every non-lodging lunch/dinner listed in `required_meal_ids` appears as a
  `.meal-options` block;
- every `.meal-options` block has exactly 3 `.restaurant-card` options;
- every restaurant card carries the required detail labels;
- lodging-provided meals listed in `provided_meal_ids` are explicitly marked as
  `.provided-meal`;
- internal paths/jargon (`C:/`, `_travelwork`, `.claude`, `poi_id`, `must_do`)
  do not leak into the public page.

If `family-public-contract.yaml` is absent, the CLI prints
`family-public contract: not run`. Do not describe that output as family/public
shareable; it only passed the core export gate.

Family contract failures are not treated as blind re-render fixes. Repair the
public HTML contract or its source data, then re-run this gate.

## Output

Run `python scripts/export_gate.py trips/<slug>` — the CLI assembles the
MERGED pois itself (verified-pois + chosen lodgings + `apply_media` overlay),
gates both the md and html deliverables, and writes
`trips/<slug>/export-gate-report.yaml` (schema: `schemas/gate-report.schema.json`
— reused; same status/checks/failures shape, plus the optional `distributable` + `retryable`
flags). On `status: fail`, the report's **`retryable`** tells the orchestrator how to react
(F1): `retryable: true` (a render-fixable defect) → re-render; `retryable: false` (the only
failures are upstream DATA defects — a photo with no attribution, a bookable POI with no
official source — that re-rendering cannot fix) → **stop and ask the user to fix the data**,
do NOT loop. A `status: pass` report with `distributable: false` is a **clean terminal
personal variant** (google-photo HTML): the orchestrator completes it as "complete —
non-distributable, 勿散布", it does NOT re-export loop. (P7)

## Stage Contract

| Field | Value |
|---|---|
| Input | `trips/<slug>/exports/<slug>-itinerary.md` + the MERGED pois (`verified-pois.yaml` overlaid with optional `verified-pois-media.yaml` via `scripts/media_merge.py::apply_media`), so the photo / distributability checks see the same photos the deliverable rendered. |
| Output | `trips/<slug>/export-gate-report.yaml` (`status` pass/fail + failures, plus optional `family_*` checks when `family-public-contract.yaml` exists). |
| Stop condition | `status: fail` → branch by `retryable`; family/public contract failures require repairing the public HTML contract or source data before re-running. |
| Next stage | `tripwork:orchestrator` (core pipeline complete on pass; family/public shareability additionally requires a passing family contract when that deliverable is requested). |
