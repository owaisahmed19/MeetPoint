# Validation - MeetPoint 0.5.0

Revision date: 10 November 2026.

## Automated checks actually run

- Full Python suite: **77 passed** on the final application code.
- Python application and launcher compilation: passed.
- Launcher smoke test: `start.py` started Uvicorn; a real HTTP health request reported version 0.5.0; served HTML contained the personal schedule and no walking-time input.
- JavaScript syntax check (`node --check app/static/app.js`): passed.
- API end-to-end fixture: two registered users, invite/accept, automatic walking, one recommendation, separate departure times, new proposal identity, stale approval rejection, individual travelling state and venue-change invalidation.
- Course four-node shortest-path matrix and path reconstruction: passed.
- Timetable reverse-search fixture: preserves the scheduled bus and respects the boarding margin while removing unnecessary initial waiting.
- Supplied indoor-graph fixture: its duration contributes to the meeting time and final indoor leg.
- Frontend regression: no `maxwalk` form control, direct lookup or restored-state reference remains.
- Existing authentication, invitation privacy, cancellation, venue management, UI-logic, walking/refinement, transfer, rail geometry and progress tests are retained.

A non-failing Starlette/httpx deprecation warning was emitted by the test-client dependency. This is recorded rather than hidden.

## Timing actually observed

Included two-person reference scenario, local development environment:

| State | Elapsed |
|---|---:|
| Cold calculation after filtering/caching revision | 6.879 s |
| Immediate repeated calculation | 0.135 s |
| Next immediate repeated calculation | 0.062 s |

These are individual measured runs, not a statistically established p95 or a guarantee. Cold searches still take seconds. Different origins/dates/candidates, changing files and explicit external pedestrian verification can take longer.

## Limits of verification

The connected browser reached another local application copy, and the cloud preview did not reach the packaged server. Consequently no visual end-to-end browser verification of this release, physical Android test or road/indoor field test is claimed. UI syntax/DOM contracts and existing UI-logic regressions were checked separately.

The inherited Android APK was not rebuilt in this revision; its source/build kit is included. It remains a client for the shared server. No public deployment was performed.

The bundled transit data is a previously imported snapshot. Actual services on a new date, current operator delays and current venue opening/booking conditions require appropriate updated data. Unresolved walking geometry remains explicitly conditional/approximate. Cached OSM paths are modelled routes, not field-verified travel times.

The indoor engine is tested with a clearly synthetic fixture. There is no verified real indoor graph bundled; `data/indoor_networks.json` is empty. No real indoor positioning is claimed.

The professor's minimum-sum and earliest-meeting formulations are distinct and remain labelled. This release is not a guarantee of full marks or certification of literal conformity to inconsistent source wording.
