# Travelwork Morning Run Lifecycle — Approved Specification

**Status:** Approved by 光佑 on 2026-07-25
**Selected design:** C — plan, reconcile Garmin actuals, and republish the same trip artifacts
**Primary trip for dogfood:** `2026-uk-family`

## Outcome

Travelwork gains a morning-run workflow that can plan a safe and scenic 6–8 km
route with meaningful historical and cultural waypoints, give one tap-ready
Google Maps Directions link, then reconcile the completed Garmin activity into
the same run record after the existing daily Garmin refresh. The trip Markdown
and stable family webpage are rebuilt in place; no second Garmin schedule and
no second family URL are created.

## Ownership

| Boundary | Owner | Contract |
|---|---|---|
| Garmin login, fetch, FIT download, normalization, route trackpoints | `garmin-claude-analysis` producer/runtime | Atomic normalized activity snapshot plus per-activity route sidecars |
| Daily trigger | `health-command-center` | Run Garmin once, publish Health, then invoke travelwork as an isolated post-sync consumer |
| Morning-run planning, matching, comparison, Markdown block | `travelwork` | `morning-runs.yaml` plus a bounded generated Markdown section |
| Trip meaning and family output | Vault `出遊/60_Efforts/<trip-slug>/` | Canonical trip pack and `deliverables/public/index.html` |
| Public serving | `app-cmd-center-web` | Stable `/travel/<trip-slug>/` link resolves the canonical deliverable |

Garmin remains an independent producer. Travelwork never logs in to Garmin,
never fetches Garmin independently, and never reads the producer's SQLite
database directly.

## User-visible lifecycle

| State | Meaning | Public presentation |
|---|---|---|
| `planned` | A researched route exists but no Garmin activity is matched | Distance target, route option, Google Maps link, safety notes, waypoint reasons and stories |
| `completed-summary` | Exactly one Garmin run matched, but route points are not yet available | Actual statistics plus `實際路線待同步` |
| `completed` | Garmin summary and route sidecar both matched | Actual statistics, visited/missed waypoints and deterministic deviations |
| `pending-match` | Zero or multiple plausible activities exist | Keep the plan unchanged and show no guessed actual |

## Canonical trip artifact

Each active trip may contain `morning-runs.yaml`:

```yaml
schema_version: 1
trip_slug: 2026-uk-family
timezone: Europe/London
runs:
  - run_id: 2026-07-25-windsor
    date: 2026-07-25
    locality: Windsor
    hotel: Holiday Inn Express Windsor
    target_distance_km: {min: 6, max: 8}
    selected_option: A
    status: planned
    google_maps_url: https://www.google.com/maps/dir/?api=1&...
    waypoints:
      - name: Windsor Castle
        latitude: 51.4839
        longitude: -0.6044
        why_selected: Royal Windsor story and a safe, legible landmark
        history_culture: Concise sourced historical context
        safety_note: Daylight, crossing or surface guidance
        visit_radius_m: 150
    actual: null
```

The reconciler updates only:

```yaml
status: completed
actual:
  garmin_activity_id: 123456789
  start_local: 2026-07-25T07:12:00+01:00
  distance_km: 7.24
  duration_min: 44.6
  pace_min_per_km: 6.16
  avg_hr: 143
  max_hr: 158
  elevation_gain_m: 38
  matched_by: [date, activity_type, start_window, locality]
  visited_waypoints: [Windsor Castle]
  missed_waypoints: [The Long Walk]
  deviations:
    distance_delta_km: 0.24
    distance_delta_percent: 3.4
    notes: [實跑沒有進入 The Long Walk 的 150 m 範圍]
```

`garmin_activity_id` is the idempotency key. Reprocessing the same normalized
snapshot updates the same record and cannot append a duplicate run.

## Garmin route contract

The existing Garmin fetch stops using `--no-files`. The same authenticated
fetch downloads only missing FIT archives and lets the installed
`garmin-givemydata` parser populate `activity_trackpoints`.

The producer atomically publishes:

```text
health_normalized.json
activity_routes/
  index.json
  <activity-id>.json
```

`index.json` contains schema version, generation time, and activity ID to
sidecar digest mappings. Each sidecar contains the immutable activity ID and
ordered normalized points:

```json
{
  "schema_version": 1,
  "activity_id": 123456789,
  "source": "garmin-fit",
  "points": [
    {
      "seq": 0,
      "timestamp_utc": "2026-07-25T06:12:00+00:00",
      "latitude": 51.48,
      "longitude": -0.61,
      "altitude_m": 26.0,
      "distance_m": 0.0
    }
  ]
}
```

No FIT archive, token, browser profile, or raw SQLite byte enters the Vault or
travelwork repository.

## Matching rules

An activity is eligible only when all mandatory rules pass:

1. Activity `type` is `running`; treadmill activity is excluded.
2. Activity local date equals the run date in the trip timezone.
3. Start time is between 04:00 and 11:30 local time.
4. Activity has not been bound to a different `run_id`.

Locality or route evidence is additive:

- With route points, the route bounding box must be within 30 km of the planned
  locality anchor.
- Without route points, the activity name may match the locality.

Exactly one eligible activity produces a match. Zero or multiple candidates
produce `pending-match`; the reconciler does not guess.

## Route comparison

- A planned waypoint is visited when any valid actual point is within that
  waypoint's `visit_radius_m`, default 150 m.
- Distance delta uses Garmin summary distance, not geometry recomputation.
- Pace is derived as `duration_min / distance_km` only when distance is positive.
- Deviation prose is deterministic and fact-based: distance delta,
  visited/missed waypoint names, and route-availability state.
- Historical and cultural explanations remain the researched planning text;
  Garmin data cannot rewrite them.

## Markdown and webpage publication

Travelwork owns one bounded block in the family Markdown:

```markdown
<!-- travelwork:morning-runs:start -->
## 晨跑路線與實跑紀錄
...
<!-- travelwork:morning-runs:end -->
```

The update is atomic and preserves all bytes outside the markers. If markers
are missing, the block is inserted once at the configured section anchor. If
markers are malformed or duplicated, reconciliation stops without writing.

After a meaningful change:

1. Update `morning-runs.yaml`.
2. Update the bounded block in the family Markdown.
3. Run `publish.yaml.render_command`.
4. Verify the fixed public URL through HTTP.

The public page shows planned route, actual statistics and named deviations.
Full Garmin coordinates, FIT files and exact start/end points remain outside
the public HTML. The family URL remains:

`https://home.luminexhealthbiohack.com/travel/<trip-slug>/`

## Morning-run skill requirements

The skill triggers on urgent or planned travel runs, including `晨跑`,
`morning run`, `跑步路線`, hotel-based running, Garmin reconciliation and
updating a trip webpage after a run.

Before-run output must include:

- Three 6–8 km options unless the user requests another count.
- Safety, scenery and narrative value.
- A single Google Maps Directions link per option.
- Every waypoint's selection reason and concise sourced history/culture.
- Surface, crossing, daylight and bailout guidance.

After-run reconciliation must consume only the normalized Garmin contracts and
follow the matching, privacy and publication rules above.

## Failure and privacy rules

- Missing/stale Garmin data is unknown, never zero.
- Garmin acquisition failure keeps the last good snapshot and does not alter a
  run record.
- A travelwork post-sync failure cannot invalidate the already-published
  Health projection; it records a separate receipt and exits visibly.
- Public HTML must not contain raw coordinates, FIT/GPX paths, exact hotel
  start/end points or private local paths.
- The first UK backfill remains `pending-match` until the 2026-07-25 Windsor
  activity appears in the normalized snapshot. Current evidence at approval
  time shows the newest normalized Garmin activity is 2026-07-19.

## Acceptance outcomes

1. A Windsor morning-run request yields three researched 6–8 km routes and
   one valid Google Maps link per route.
2. The existing Garmin daily job produces summary and route contracts without
   a second scheduled Garmin fetch.
3. An exact single Garmin match updates one existing run idempotently.
4. Ambiguous or absent matches do not fabricate actuals.
5. The family Markdown and stable HTML show planned and actual information
   while raw coordinates stay private.
6. The 2026 UK family trip contains future morning-run plans and today's run
   transitions automatically when its Garmin activity becomes available.
