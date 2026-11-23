# Course requirements and design baseline

This is the source-grounded planning baseline prepared before implementation. For the implemented release, running instructions, test results and current limits, use the root README.md and VALIDATION.md. The later user instruction removes walking-time input; walking durations are calculated automatically.

---

# Mobility in Smart Cities - Mini-Project README and Change Specification

**Project:** Optimizing Emergency Indoor & Outdoor Navigation and Meeting-Point Detection & Tracking  
**Course:** Mobility in Smart Cities - Philippe Canalda  
**Updated:** 10 November 2026  
**Purpose:** A complete specification for the next application revision, grounded in the supplied course Resources and the two current itinerary screenshots.

This document starts with the professor's algorithms, then specifies the changes to meeting places, calculation speed, individual departure times, meeting confirmation, routes and tracking. It consolidates the earlier mini-project notes. It is a development specification, not a claim that the current application has passed an implementation audit. The application source has not been inspected for this revision.

## 1. First: which algorithm did the professor ask us to use?

**The professor explicitly names Dijkstra for shortest paths, requires an origin-destination (OD) matrix, and describes a second function that selects the meeting point minimizing the sum of the group's travel costs.**

| Part | Professor's instruction | Required application result | Source |
|---|---|---|---|
| `f1`: shortest paths | Calculate indirect connections and shortest paths; the slides call this Dijkstra | Reachable OD costs and recoverable routes between modelled locations | Part IIIb, pp. 11-12; Part IV, p. 6 |
| `f2`: group meeting selection | For each discrete candidate point, add everybody's displacement cost; keep the point with the minimum total | One selected meeting point under the stated cost objective | Part IIIb, p. 13; Part IV, p. 7 |
| Route construction | An OD cell includes a cost and route; combine route segments through intermediate nodes | An individual itinerary for every participant | Part IIIb, pp. 13-14; Part IV, pp. 7-8 |
| Application timing | Determine the place and time window where registered friends can meet at the earliest | A feasible common meeting time, considering everybody | Part I, pp. 13-16 |
| Monitoring | Follow friends step by step and signal delay or advance | Individual progress and updated arrival information | Part I, pp. 15-16 |

The `f1`/`f2` internal functions are supporting calculations. They are not a replacement for the three user-facing functions: meeting selection, individual itineraries and journey monitoring.

### 1.1 An inconsistency in the slides must be documented

The slides name Dijkstra but also describe repeated full-matrix improvement passes until nothing changes. That procedure is not the standard single-source, priority-queue Dijkstra algorithm. Part IIIb, p. 11 also prints comparisons that conflict with finding shortest paths.

| Printed statement | Correction needed for shortest paths |
|---|---|
| Consider a connection only when its cost is greater than 1 | Include valid cost-1 connections; identify missing connections separately |
| Replace the old cost when the new cost is greater | Replace a finite cost when the new route is cheaper; also initialize an unavailable route when a valid route is found |
| Missing connection is `-1` | Convert absence to an unreachable state internally; never add `-1` as a real edge cost |

**Implementation baseline proposed here:** use standard Dijkstra on a directed graph with non-negative costs. Run it from each modelled origin to build the static OD table; for a new origin, compute the necessary row. Retain predecessors or next hops for itinerary reconstruction. Document the lecture's repeated-relaxation description and the corrections above rather than claiming that the two procedures are identical.

Floyd-Warshall is a possible all-pairs alternative, but it must not be presented as the algorithm the professor explicitly named. The course files do not establish that a particular external routing API, framework or database is compulsory.

### 1.2 What Dijkstra does and does not decide

Dijkstra finds the shortest route from one origin to other nodes under the chosen edge costs. It does not, by itself, choose the best common meeting point. The group comparison is `f2`.

For a static time-cost matrix:

```text
total_cost(candidate) = sum(OD[participant_origin][candidate])
selected_place = feasible candidate with minimum total_cost
```

Use one unit consistently, such as seconds. Do not add metres to minutes. Do not assume that a geographical midpoint, the nearest cafe to the organizer, the first result from a places API, or the first reachable venue implements `f2`.

### 1.3 Public transport needs a timetable-aware model

The screenshots contain buses and trains. A fixed edge labelled "13 minutes by train" does not describe when that train operates or whether the passenger can catch it.

For the real application, represent walking access, scheduled departures and arrivals, service dates, boarding/transfer margins and egress walking. Use a suitable timetable/event graph or a routing service that supports those constraints. Dijkstra can support shortest paths on an appropriately constructed non-negative event graph; a time-dependent implementation needs its corresponding validity assumptions.

The choice of timetable engine is an implementation decision. The professor did not expressly require a named public-transport routing package in the cited passages. A static classroom demonstration must disclose its assumptions instead of pretending to provide verified live transit journeys.

## 2. Official scope and what changed in the later materials

Part I offers two project directions: implement one of the four transport algorithms, **or** build the positioning/mobility application. This project follows the application direction. It does not also need all four Louage, On Demand Transportation, Dynamic Carpooling and Carpooling++ implementations.

| Requirement | What must be delivered |
|---|---|
| Platform | A mobile application, preferably Android, or a web application; both are not compulsory |
| Users | A group of registered friends; normally a team of 2-3 students develops the project, with solo work also accepted |
| Locations | Map relevant homes, classrooms, activity locations, meeting places and car parks |
| OD data | Model places, travel distances, times and routes |
| Meeting selection | Determine a meeting location and feasible time window |
| Personal navigation | Generate a route for each participant |
| Advanced monitoring | Track individual progress and signal delay/advance |
| Conception | Illustrated subject, specifications, necessary data, essential/supporting functions, actors and architecture mapped to priority scenarios |

The later materials make the internal OD/shortest-path and group-cost calculations explicit. Part IV also explains reusing static calculations for smaller dynamic queries. They do not introduce a requirement to search every business in a city on every request.

The previous lecture-reference README records a classroom territory of approximately 30 locations and a smaller active group. Part IV, p. 61 uses 10 locations as another example. **Neither number is a mandatory application limit.** Participant origins are a subset of the network; routes may still need intermediate stops outside that subset.

Keep the indoor/outdoor project framing. Part IV, p. 2 says there is insufficient time for the separate positioning objective; it does not explicitly cancel indoor/outdoor rendezvous navigation. For a verified indoor demonstration, model actual entrances, corridors and rooms. Do not invent indoor GPS accuracy or floor plans.

The 8/14/18/20 figures in Part I describe modelling and functional assessment progression. They are not separate scores to add together or guaranteed marks. Module weighting is theory 50%, practical exercises 20%, mini-project 30%.

## 3. Evidence from the current application

| Evidence | What is visible | What still needs inspection |
|---|---|---|
| Ahmed's itinerary | 08:00 departure; about 3.07 minutes walking; bus B at 09:37; 94-minute displayed wait; arrival 09:48 | Why the search selected that departure, service and initial waiting period |
| Prof Canalda's itinerary | 08:00 departure; 25.3 minutes walking; train C3 at 09:36; 71-minute displayed wait; arrival 09:51 | Whether 08:00 is a forced shared start, a user input or a routing-query default |
| Shared destination | Both routes end at La Tasse a The - Hotel Bristol | Which other candidates were evaluated and why this one won |
| Geometry | Ahmed's last walking segment lacks geometry; the train corridor is not certified as the service-specific path | Whether better verified geometry is available for the chosen routes |
| Calculation speed | The user reports that the places calculation is slow | Actual duration, API-call count, cache use and the location of the bottleneck |

These screenshots show excessive initial waiting in this example. They do not prove that the source code always forces simultaneous departure or calculates every possible place. The revised implementation must expose enough calculation evidence to diagnose both.

## 4. The new behavior we want

The user should create a group, provide individual availability and travel constraints, and receive **one recommended meeting place, one common meeting time, and a separate journey and departure time for each person**.

Changing a place or participant must update the result without requiring a page refresh. The normal result should be concise; the OD comparison remains available as calculation evidence for the project demonstration.

| Topic | Required revision | Basis |
|---|---|---|
| Meeting venues | Use a manageable, editable set of verified meeting places | User request and proposed performance design |
| Group choice | Compare admissible candidates using an explicitly stated objective | Professor's `f2` and timing specification |
| Result display | Show one winner by default, with a short explanation | User request |
| Departure times | Calculate each person's latest feasible departure for the common meeting | User request; scheduling design supporting the project |
| Acceptance | Accepting the meeting confirms the proposal; it must not force everybody to depart immediately | User request |
| Speed | Reuse valid OD/network data; avoid repeated route/geometry work | Later course materials plus proposed implementation design |
| Itineraries | Preserve actual service times, walking, transfers and route recovery | Professor's individual-route requirement and application correctness |
| Monitoring | Track each person independently and update delay/advance | Professor's advanced function |

Details below marked as a **proposed design** are project choices, not quotations from the professor.

## 5. Meeting places: replace the expensive default search

### 5.1 Use an explicit candidate catalogue

**Proposed design:** use a small, configurable catalogue of suitable meeting places, maintained before the calculation. Campus entrances, approved common areas, libraries, classrooms or other real meeting venues can be included after their location and access conditions are verified.

For an initial demonstration, approximately 10-20 enabled candidates is a reasonable configurable starting point, not a professor requirement or a proven optimum. Choose the actual places from the application's operating territory. Do not silently restrict the candidates to the organizer's town when participants are distributed across the region.

Replace automatic mass discovery of cafes/hotels on every calculation. Allow a place to be added, edited, enabled or disabled through the existing place-management flow. A map pin or saved coordinates can identify a location without repeated address lookup. Preserve existing valid places unless explicitly disabled.

Minimum useful venue information:

| Information | Purpose |
|---|---|
| Stable ID, name and coordinates | Identify the candidate and connect it to the network |
| Enabled status and location type | Control which venues participate in the search |
| Access/availability information, when relevant | Avoid proposing a closed, inaccessible or unsuitable venue |
| Building, floor, entrance or indoor node, when available | Connect indoor navigation to a verified outdoor access point |
| Source and data version | Know when cached information must be refreshed |

Opening times, capacity and access restrictions are enforced when the application claims to support them. Unknown availability must remain unknown, rather than being converted into a verified guarantee that the venue is open.

### 5.2 One displayed winner still needs a valid comparison

The application should not load and draw a complete itinerary for every candidate. It should obtain the necessary cost/feasibility summaries, compare the allowed candidates, select one, and then load detailed display geometry for that winner.

Selecting one arbitrary venue before comparison is not group optimization. An exact claim is limited to the declared candidate set and routing assumptions. An approximation that shortlists by straight-line distance must be labelled approximate unless its pruning is proved safe for the actual objective and transport modes.

Changing the catalogue changes the domain of the optimum. The result may say "Best among 12 enabled meeting places"; it must not claim "best place anywhere".

Removing a place from the meeting candidates must not delete a stop, entrance or corridor needed as an intermediate routing node.

## 6. Define what "best for everyone" means

The source materials contain two different objectives:

| Objective | Meaning |
|---|---|
| Minimum total movement (`f2`) | Minimize the sum of individual travel costs to the candidate |
| Earliest meeting (Part I) | Minimize the time when the last required participant can arrive, subject to availability |

They are not equivalent. With simultaneous availability and static travel times:

| Candidate | Person A | Person B | Total travel | Earliest group arrival |
|---|---:|---:|---:|---:|
| A | 2 min | 10 min | 12 min | 10 min |
| B | 7 min | 7 min | 14 min | 7 min |

`f2` selects A. Earliest meeting selects B. No implementation can truthfully claim that this example has one venue independently optimal for both objectives.

### 6.1 Proposed policy for the revised application

For the normal **meet as early as possible** request:

1. Reject infeasible candidates.
2. Minimize the feasible common meeting start.
3. Break equal-start ties using total travel cost under a consistent routing model.
4. Break remaining exact ties using a stable venue ID.

Also implement and verify the professor's **minimum-total-cost `f2`** calculation as a separate, clearly named reference selection. Record its winning venue and score in the calculation evidence. It need not create another default result card or another public-facing workflow.

This priority rule is a proposed application decision. The supplied files do not prescribe how to reconcile the objectives. If the professor confirms minimum total movement as the primary application policy, change the ranking order and its label; do not change the meaning of the scores. Until this discrepancy is settled, do not claim literal agreement with both global objectives in every case.

If the user specifies a fixed meeting time, first check which venues are reachable by that time and then apply the declared travel-cost ranking within that feasible set. This is a distinct scheduling request, not a claim to have found the earliest possible meeting.

### 6.2 Availability and feasibility

Separate these inputs:

- Earliest time each person can leave their origin.
- Time intervals during which each person can attend the meeting.
- Meeting date and duration.
- Permitted modes and supported walking/access constraints.
- Venue availability, where known and required.

For each candidate `c`, let `E_i(c)` be participant `i`'s earliest reachable arrival after their own earliest departure. The first possible group arrival is the maximum of these arrivals. Find the earliest meeting start at or after that time that lies in a common attendance interval and permits the complete meeting duration at the venue.

An unreachable participant makes the candidate infeasible. An empty common attendance window also makes it infeasible. Report "No feasible meeting under these constraints" rather than discarding a participant or fabricating a zero-minute route.

For a single attendance interval per person, and a single relevant venue interval, a simplified check is:

```text
start = max(all earliest arrivals, all attendance starts, venue opening)
feasible if start + meeting_duration <= min(all attendance ends, venue closing)
```

Use actual interval intersections when there are several openings or availability windows. Return travel is included only if explicitly supported and requested; it is not covered by the simplified formula above.

## 7. Separate departure times: the main scheduling correction

**Everybody agrees on the same destination and meeting time. Everybody does not need the same departure time.**

For a simple constant-duration example, if the meeting is at 10:00:

| Participant | Journey | Departure without an additional margin | Meeting |
|---|---:|---:|---:|
| A | 90 min | 08:30 | 10:00 |
| B | 20 min | 09:40 | 10:00 |

This example explains the behavior. Real bus and train journeys must follow their timetables.

### 7.1 Calculate forward, then plan individual departures backward

1. Use individual earliest-departure constraints to establish feasible candidate arrivals and choose the common meeting time.
2. For the selected venue and time, run an **arrive-by/latest-feasible-departure calculation** for each participant independently.
3. Respect their earliest departure, actual services, walking durations and boarding/transfer margins.
4. Return the latest feasible departure that still gets them there on time under those constraints.
5. Show unavoidable waiting at the destination if transit services cannot produce identical arrivals.

The backward calculation must use timetable-aware logic or the routing engine's arrive-by capability. Subtracting a previously displayed total duration from the meeting time can produce an impossible bus/train journey. For a time-invariant walking route, subtraction can be valid; it is not a universal transit algorithm.

If the resulting routing costs change a value used to rank candidates, update that comparison before claiming the final venue is optimal. Do not rank using one cost definition and explain the result using a different one.

### 7.2 Apply this to the screenshots

The displayed 08:00 itineraries include substantial waiting before boarding. A person available from 08:00 should usually be allowed to remain at their origin until closer to the service departure.

Using only the printed first-walk durations and service departures, an illustrative five-minute boarding margin gives:

| Participant | Service in screenshot | Access walk | Illustrative origin departure | Effect |
|---|---|---:|---:|---|
| Ahmed | Bus B, 09:37 from JEAN MOULIN | 3.07 min | Around 09:28, conservatively rounded earlier | Reach the stop around 09:31, leaving about six minutes before boarding |
| Prof Canalda | Train C3, 09:36 from Belfort-Ville | 25.3 min | Around 09:05, conservatively rounded earlier | Reach the station around 09:30, leaving about six minutes before boarding |

These are illustrations, not newly verified travel instructions. The screenshots do not establish the service date, complete boarding rules, precise arrival seconds or venue availability. The revised application must recalculate the selected date and margins. If the same services remain feasible, the displayed destination arrivals can remain approximately 09:48 and 09:51 despite the later origin departures.

The common meeting cannot begin before the last actual arrival. A later-departure plan removes unnecessary waiting at the stop; it must not remove a necessary interchange or move a train departure.

### 7.3 Distinguish the different times

Display separately:

- **Available from:** the earliest permitted departure, not an instruction to leave.
- **Leave at:** the individual's planned departure.
- **Journey duration:** actual origin departure to destination arrival, including required waiting during the journey.
- **Arrive at:** their own destination arrival.
- **Meeting starts:** the shared meeting time.
- **Wait at destination:** any time between their arrival and the meeting.

Time spent staying at home before the recommended departure is not journey duration. An optional early departure can be allowed, but should not be forced by accepting the proposal.

## 8. Confirmation, plan changes and independent journeys

**Proposed design:** confirmations refer to one specific proposal version containing the venue, meeting time and individual itinerary summaries.

| Event | Expected behavior |
|---|---|
| One participant accepts | Record acceptance of that proposal version |
| All required participants accept | Confirm the meeting and retain each person's separate departure schedule |
| Someone's departure time arrives | Show that person's departure reminder/status; other people keep their schedules |
| Someone starts moving | Change only that person's journey state |
| Venue, attendance, modes or meeting time changes | Recalculate affected data and create a revised proposal; previous acceptance does not silently approve a materially different plan |
| A delay threatens the meeting | Update ETA and explain the impact; propose a revision if necessary |
| Meeting is cancelled | Cancel pending departure reminders and stop presenting the plan as active |

Suggested participant states are waiting for confirmation, scheduled, ready to leave, travelling, arrived and delayed. These names are implementation suggestions. There must be no single group "departed" flag that starts every itinerary simultaneously.

Tracking should identify which participant is late or early. Actual location updates require the participant's consent. A simulated demonstration is acceptable only when labelled simulated; it must not be presented as live GPS evidence.

## 9. Make the calculation fast without changing the answer

The performance design follows the course distinction between reusable static work and a smaller dynamic group query. Actual bottlenecks must still be measured in the source application.

| Stage | Reusable/static work | Per-request work |
|---|---|---|
| Geography | Verified meeting catalogue, entrances, walking network and graph connections | Connect changed participant origins to the network |
| Transit data | Parse/index the timetable and service calendars once per data version | Select valid services for the requested date/time and constraints |
| OD information | Cache valid costs and route-recovery data | Compute missing or invalid entries |
| Group selection | Reuse network/cost information | Evaluate the current participants against enabled candidates |
| Map rendering | Reuse map assets and route identifiers | Load detailed winning itineraries and required geometry |

### 9.1 Required performance changes

1. Stop repeated city-wide venue discovery during normal calculation.
2. Filter disabled or definitely unsuitable venues before requesting expensive routes.
3. Use one-to-many routing from each participant to the candidates where the engine supports it. Do not issue a separate external request for every OD cell by default.
4. Cache stable network and OD information with explicit validity rules.
5. Compare compact costs, arrival information and feasibility before loading display geometry.
6. Retrieve/render detailed geometry for the selected venue's individual routes. If the routing engine necessarily computes internal paths during ranking, avoid additional geometry/API work for losing venues.
7. Use bounded concurrency for independent requests, within provider limits.
8. Cancel or supersede stale calculations when input changes. Only the latest request may replace the visible result.
9. Prevent duplicate submissions and accidental recomputation on every UI render or live position update.
10. Show progress and a usable failure/retry state. A page refresh must not be required to obtain the completed result.

With `p` participants and `c` candidates, a matrix contains `p*c` relevant costs. Once valid costs exist, a simple group comparison is `O(p*c)`. Three participants and twelve venues need 36 costs; they do not inherently require 36 separate network requests or 36 drawn routes.

Static Dijkstra from one origin can discover costs to many venues in a single search. Repeated Dijkstra for a full `n`-node static OD table uses `n` searches; the distance table itself uses `O(n^2)` space. Do not rebuild that full table for every acceptance click.

### 9.2 Cache correctness

An entry must be invalidated or recomputed when any input affecting it changes. Depending on the model, this includes origin/destination, direction, modes, walking/access constraints, date/time, service calendar, timetable version, real-time disruption and graph version.

A departure-time bucket is an approximation unless it can preserve the required service feasibility and objective. Never reuse an 08:00 transit route at 09:30 merely because the origin and destination match. Separate reusable physical geometry from time-sensitive transit schedules.

Changing only the active group can reuse valid participant-to-venue entries. Changing the chosen venue can reuse other cached entries without recomputing the whole territory. Venue availability updates may invalidate feasibility without changing physical route geometry.

### 9.3 Safe reduction

Reducing a routing graph must preserve the costs and constraints needed by the application. Hasse reduction from the divisibility exercise is not a general weighted-road simplification method. An alternative path costing 10 does not justify removing a direct edge costing 2.

Record what a simplification preserves and verify recovered itineraries. Do not remove nodes solely because they are not current participants or meeting candidates.

### 9.4 Performance evidence

Measure before and after using the same date, modes, origins, venue set and reference environment. Record cold-cache and warm-cache times, request counts, candidates considered, cache hits and time spent ranking versus loading geometry.

**Proposed initial engineering target:** for a reference case of three participants and twelve verified venues, aim for a warm-cache result within two seconds. This is not a professor requirement or a measured promise. Record actual median and 95th-percentile latency over repeated runs, and disclose external routing/network delays. A fast result that silently omits candidates or violates schedules fails correctness.

## 10. OD model, routes and time correctness

### 10.1 Static graph baseline

Use directed movements. Costs from A to B can differ from B to A. Store zero on the diagonal, a non-negative cost for a permitted movement and an explicit unreachable state otherwise.

The professor's four-node example is:

| Origin / destination | 0 | 1 | 2 | 3 |
|---|---:|---:|---:|---:|
| 0 | 0 | 1 | 8 | -1 |
| 1 | -1 | 0 | 5 | 2 |
| 2 | 1 | -1 | 0 | -1 |
| 3 | 3 | 2 | -1 | 0 |

Its shortest-path costs are:

| Origin / destination | 0 | 1 | 2 | 3 |
|---|---:|---:|---:|---:|
| 0 | 0 | 1 | 6 | 3 |
| 1 | 5 | 0 | 5 | 2 |
| 2 | 1 | 2 | 0 | 4 |
| 3 | 3 | 2 | 7 | 0 |

For example, `0 -> 1 -> 2` costs 6 and improves the direct cost of 8. This is weighted shortest-path computation, not merely Boolean reachability. The example is a mathematical verification target, not an assertion about the current application's code.

### 10.2 Practical OD/journey information

An implementation can store:

| Information | Meaning |
|---|---|
| Reachable/feasible | Distinguish unavailable routes from zero duration |
| Cost and unit | The value actually used for the stated objective |
| Departure/arrival and date | Required for timed journeys |
| Distance and duration | Route summary; duration semantics must be explicit |
| Predecessor/next-hop or itinerary reference | Recover the route without duplicating every full geometry |
| Legs | Walking, service identifiers, stops, boarding/alighting and transfers |
| Constraints and data version | Explain why a cached result remains valid |
| Geometry status | Verified path, approximate corridor, or unavailable |

These are proposed fields, not mandated API names. A transit OD cell may need a time-dependent function or several journey options; a single timeless scalar cannot represent every service date and departure.

Store seconds internally and render minutes for readability. Use the relevant local time zone, Europe/Paris for the illustrated territory, including service dates and daylight-saving changes. Handle transit service times past midnight correctly. Rounded display times must not make a missed connection look catchable.

Walking limits, if offered, must state whether they apply per leg or cumulatively and be enforced accordingly. The professor's screenshot contains a 25.3-minute initial walk; it is a violation only if an applicable user constraint forbids it.

### 10.3 Route geometry and user presentation

Show actual walking-network paths when available. Use the correct transit route shape where available. A general rail corridor must not be presented as a certified service-specific itinerary. If geometry is unavailable, label the affected segment clearly and show endpoints without inventing a route.

The normal meeting result should show:

- One recommended venue and the shared meeting start/duration.
- A short reason for the recommendation under the declared objective.
- Each person's departure, arrival, duration and main modes.
- Expandable stop/transfer instructions and route details.
- Individual acceptance and journey status.

Keep technical diagnostics in a calculation-details view or logs. A user should not need to understand OD cells, graph algorithms or geometry providers to follow the meeting plan.

## 11. Proposed calculation sequence

This sequence is a design guide. It does not prescribe new folders, frameworks or services.

```text
load the versioned network, timetable and enabled meeting catalogue
validate the request and each participant's own availability/constraints
filter definitely unsuitable venues

for each participant:
    reuse valid OD information
    compute missing candidate costs and earliest arrivals in batches where possible

for each candidate:
    reject if any required participant cannot reach it
    determine its earliest feasible common meeting window
    retain the correctly defined group cost and selection evidence

compute the minimum-total-cost f2 reference winner
select one application winner under the declared scheduling policy

for each participant, for the selected place/time:
    calculate a latest-feasible-departure itinerary
    verify service times, constraints and margins

recheck any ranking values affected by the finalized timing model
load winning route geometry and publish one versioned proposal
collect acceptances for that version
confirm the meeting without synchronizing everybody's departure
track each person's own journey and update delay/advance
```

The cost used for `f2`, the earliest-arrival calculation and the final displayed duration must have documented meanings. In particular, an earliest-departure query time is not automatically the actual journey departure. If the time-dependent model requires more journey alternatives to optimize its declared cost exactly, obtain those alternatives or qualify the result; do not claim an unproved global optimum.

## 12. Work table: what to inspect and change

All entries describe the next revision. None is marked implemented or passed without source inspection and evidence.

| Priority | Work item | Concrete completion condition |
|---|---|---|
| P0 | Inspect current ranking and routing code | Identify existing objective, candidate source, query time, cache behavior and time spent in each stage |
| P0 | Make `f1`/OD explicit | Demonstrate corrected shortest costs and recoverable paths, including the four-node example |
| P0 | Implement/verify `f2` | Sum every required participant's cost for every admissible candidate; record its minimum |
| P0 | State the application objective | Result and calculation evidence name the policy; the earliest/sum conflict is not hidden |
| P0 | Replace expensive venue discovery | Manage a verified catalogue; identify the actual places without fabricated coordinates or opening hours |
| P0 | Return one winner | Compare valid costs first and display one recommendation |
| P0 | Fix individual departure scheduling | Arrive-by planning gives different departure times when appropriate |
| P0 | Fix confirmation semantics | Acceptance confirms a plan version and never starts everyone's route immediately |
| P0 | Enforce timetable feasibility | Correct day, service, access walk, boarding and transfer times |
| P0 | Handle unavailable meetings | Clear no-solution result; no participant dropped and no fake route |
| P1 | Reduce repeated computation | Reuse valid OD data, batch work, avoid duplicate requests and defer display geometry |
| P1 | Fix refresh/stale-result behavior | Latest valid result appears automatically and older requests cannot overwrite it |
| P1 | Improve route display | Separate leave/arrival/meeting times; honest geometry labels and understandable legs |
| P1 | Support independent progress | Each participant has separate status and ETA; delay/advance is visible |
| P1 | Verify indoor/outdoor scope | Demonstrate verified entrance/interior navigation or explicitly document the remaining limitation |
| P1 | Evaluate performance | Comparable before/after measurements with correctness unchanged |
| P2 | Prepare submission materials | Conception, report, code access, presentation and demonstration video reflect the verified implementation |

P0/P1/P2 are proposed development priorities, not professor-assigned grading categories. Keep the existing technology and project structure unless inspection establishes a concrete reason to change them. There is no requirement to add a new framework, microservices or a separate Make Change module to this mini-project.

## 13. Acceptance scenarios

| Scenario | Expected evidence |
|---|---|
| Four-node course graph | Shortest-path matrix matches section 10.1; recovered paths have the printed costs |
| Minimum-sum comparison | A small manually checkable OD table produces the actual sum minimum |
| Earliest versus sum disagreement | The 2/10 versus 7/7 example distinguishes both winners and labels the application policy |
| Different journey durations | A 90-minute traveller and a 20-minute traveller can meet at 10:00 without leaving together |
| Current screenshot scenario | On a valid service date, later origin departures are considered; unnecessary 94/71-minute initial waits are removed when feasible |
| Necessary transfer wait | A required timetable wait remains visible and is not deleted to make the route look faster |
| No suitable late service | An earlier arrival is retained if necessary; venue waiting is explained |
| Individual availability | Nobody is scheduled to depart before their own availability or attend outside their attendance window |
| Unreachable participant | That venue is rejected for the whole required group |
| Venue edit/disable | Candidate set and cached feasibility update; old results cannot remain confirmed silently |
| Date or mode change | A relevant cache entry is invalidated and services/constraints are recalculated |
| Acceptance by both users | Meeting confirms while their different departure times remain intact |
| Delay or cancellation | Affected ETA/status or reminders change correctly; other participants are not falsely marked departed |
| Missing geometry | The result does not invent a street or rail path |
| Performance comparison | Same feasible winner under the same objective, with measured latency/request-count improvement |

Use deterministic fixtures for algorithm and schedule tests, plus a dated end-to-end demonstration. Screenshots and a "checks passed" label alone do not establish that these cases passed.

## 14. Conception, presentation and submission

### 14.1 Conception content requested in Part I, p. 17

Document the illustrated problem, actors, priority scenarios, specifications, data, supporting functions and architecture. Explain the network, OD preparation, candidate selection, time constraints, individual navigation and monitoring. Include one small worked example and the assumptions behind timetable and location information.

The earlier lecture-reference notes also record a request to prepare a project presentation for the next class. They do not establish a precise speaking slot from that recording. The Moodle submission screenshot supplies the presentation/video lengths below.

### 14.2 First practical-work deposit

The supplied Moodle screenshot asks for:

- A report explaining course/TD/TP contributions: team, design, implementation, tests and evaluation.
- Code accessible through a GitHub repository.
- The mini-project conception for the emergency indoor/outdoor navigation and meeting-point detection/tracking application.

### 14.3 Mini-project materials deposit

The screenshot asks for:

- A report: team, design, conception, implementation, running/tests/evaluation and analysis/comments.
- Slides for a presentation of at most 15 minutes; 5 minutes preferred.
- A demonstration video of 3 minutes; 1 minute 30 seconds preferred.

It does not prescribe a report page count, slide count, mandatory slide template, video format or hosting provider. This README is the working specification; it does not replace the final report, slides, video or application.

### 14.4 Dates and assessment

| Source | Instruction shown |
|---|---|
| Supplied Moodle screenshot | Both displayed submission areas: Monday 30 November 2026, 23:59 |
| Part IV, p. 63 | First practical work and mini-project conception before 30 November |
| Part IV, p. 63 | Second version until the Christmas holidays |
| Part IV, p. 63 | Project delivery until 16 January; early delivery encouraged for feedback |
| Part IV, p. 63 | Session on 18 November, 13:30-16:30; exam on 27 November, 14:00-16:00 |

The January year is not printed in the slide; the course sequence suggests January 2027. The visible November deposit and the later project-delivery line need to be treated as staged or conflicting information until clarified. Do not use the January line as permission to miss the displayed Moodle deadline. These are records of the supplied materials, not a fresh check of the live timetable.

### 14.5 Optional Cybermatics26 bonuses

The screenshot lists two bonus statements: +5 for demonstrating and proving conference adaptation of the Emergency Meeting Point and Itinerary Tracking web application; and +5 for the project most used during the event and receiving the most votes from IoT students.

Keep them separate from base project requirements. Claim them only with evidence. The screenshot does not define detailed conference features, voting mechanics or grade-capping rules.

## 15. Evidence and source index

Page references above use the supplied PDF/slide pagination; file prefixes are Resource filenames, not course-part numbers.

| ID | Supplied source | Relevant passages |
|---|---|---|
| S1 | `05-MSC-DynamicTransportationExactSolving-PhCanalda-25092026am-EnglishVersion-part1.ppt-Compatibility-Mode-.pdf` | pp. 10-17: project choice, platform, mapping, OD, functions, grading progression and conception |
| S2 | `07-MSC-DynamicTransportationExactSolving-PhCanalda-29092029-EnglishVersion-part2.pdf` | pp. 11, 13-15: earlier `f1`/`f2` and route descriptions; filename date retained as supplied |
| S3a | `06-MSC-DynamicTransportationExactSolving-PhCanalda-29092026-EnglishVersion-part3a.pdf` | pp. 9-12: repeated graph and group-selection specification |
| S3b | `08-MSC-DynamicTransportationExactSoving-PhCanalda-03112026-EnglishVersion-part3b.pdf` | pp. 11-14: graph example, named Dijkstra, sum objective and route cells |
| S4 | `04-MSC-DynamicTransportationExactSolving-PhCanalda-03112026-EnglishVersion-part4.pdf` | pp. 2, 6-8, 16-18, 61, 63: scope, algorithms, static/dynamic work, OD example and schedule |
| S4 duplicate | `03-MSC-DynamicTransportationExactSolving-PhCanalda-03112026-EnglishVersion-part4-1-.pdf` | Duplicate Part IV; not an additional specification |
| M | `image(20261104-145103).png` | Submission contents, visible deadlines and bonus statements |
| A1/A2 | `image(20261110-102740).png` and `image(20261110-102746).png` | Current Ahmed and Prof Canalda itineraries |
| Prior reference | Earlier version of `README_MINI_PROJECT.md`, prepared 5 November 2026 | Consolidated lecture-transcript notes on static preparation, approximately 30 locations, dynamic subsets and presentation preparation |

The research annexes describe the course's Louage/carpooling examples. Their full research models are not automatically additional requirements for the chosen rendezvous application. The latest two itinerary screenshots establish observed output, not an audit of the underlying code.

## 16. Completion checklist

- [ ] The application demonstrates corrected shortest paths and an OD representation with recoverable routes.
- [ ] The professor's minimum-total-cost `f2` is implemented and verified.
- [ ] The earliest-meeting requirement is handled and the objective-priority decision is explicit.
- [ ] The candidate catalogue contains real, suitable places and can be changed without repeated mass discovery.
- [ ] The normal result displays one justified meeting recommendation.
- [ ] Each participant gets an independently calculated departure and arrival.
- [ ] Acceptance confirms a versioned meeting rather than forcing simultaneous departure.
- [ ] Timetable dates, walking, boarding and transfers are feasible.
- [ ] Unreachable or incompatible requests produce an honest no-solution result.
- [ ] Route geometry is verified where available and honestly labelled otherwise.
- [ ] Progress/delay tracking is individual and its live/simulated status is clear.
- [ ] The indoor/outdoor scope and any remaining limitations are documented.
- [ ] Before/after performance is measured under comparable conditions.
- [ ] Conception, report, code access, slides and demo video reflect what has actually been verified.

**Current revision status:** requirements and proposed changes documented; implementation completion and professor compliance remain to be checked against the actual mini-project source and demonstrations.
