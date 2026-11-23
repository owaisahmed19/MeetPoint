# PointCommun data status — recovered snapshot, 27 October 2026

## Genuine transport archives

All three GTFS ZIPs were downloaded again from resources discovered in the official `https://transport.data.gouv.fr/api/datasets` catalogue. No mock timetable was substituted.

| Network | Download size | Catalogue service range | Licence identifier |
|---|---:|---|---|
| évolitY | 962,697 bytes | 13 July 2026–11 June 2027 | odc-odbl |
| Optymo | 2,670,087 bytes | 1 July 2026–3 January 2027 | odc-odbl |
| SNCF | 5,317,442 bytes | 26 October 2026–31 March 2027 | odc-odbl |

The common advertised range is 26 October 2026–3 January 2027. This is not evidence that every service operates on every date; GTFS calendars and exceptions decide actual service. `feed_sources.json` retains exact source URLs, metadata, retrieval time, hashes and ZIP inspection. ODbL source attribution must be retained when using/distributing these datasets.

`raw/` contains provider archives. `processed/` contains regional imports preserving full selected trips, intermediate stops and calendars. Optymo/évolitY include shapes; SNCF does not supply shapes in this resource, so rail geometry can be schematic.

## Candidate venues

- **BU Montbéliard — BU’lle 2A**: building coordinate from the university map link, 4 place Lucien Tharradin. Candidate room up to eight people; minimum group two. Published ordinary library hours Monday–Friday 08:30–18:00. The official university calendar confirms closure 11 November and 21 December–1 January. External room reservation required.
- **BU Belfort Lucien Febvre**: 43 faubourg des Ancêtres. The university lists three reservable rooms with capacities between 3 and 12. We do not invent the capacity of a selected room: capacity is null and proposal conditional. Ordinary hours Monday–Friday 09:00–19:00, Saturday 09:00–12:00; official date closures retained. This is not the separate UTBM Belfort library.
- **UTBM Sevenans Savoureuse / Chine**: group rooms of 2–7 people, maximum booking 3 hours. The official homepage reports works closure 26–30 October 2026. No future weekly schedule is assumed; `opening_hours` is empty, so these candidates must be excluded from route proposals until hours are verified. Coordinates are campus-level only.

The expanded catalogue has 29 records. Eligible entries remain conditional; none implies an external booking. This application has not booked any room. Eligibility for the group, actual free slot, exact room and access must be confirmed externally. The meaning of `permitted:true` is an identified university service for eligible users, not blanket permission for everyone or confirmation of a booking.

Campus rooms awaiting verification appear in the visible catalogue and `pending_venues.json`. Unknown permission or opening hours excludes automatic planning; unknown capacity and building-level entrances remain explicitly conditional.

## Reference scenario

`reference_scenario.json` defines two hypothetical users at published Belfort-Ville and Montbéliard station coordinates, available 08:00–18:00 on 3 November 2026, meeting duration 30 minutes. The rebuilt planner was run again against all three real feeds. Its fresh result is retained in `reference_result.json`: BU Montbéliard at 08:40:24 via C13 train, Acropole quai 6, T2 bus and Campus, conditional on room booking. The recorded run took 37.14 seconds before later planner optimisation. This remains a published-schedule calculation, not field validation.

## Explicit limits

- No operator real-time delays or vehicle GPS feed is integrated.
- Broad candidate search uses approximate walking costs. Shortlisted walks use the configured pedestrian network service when available; unresolved walks stay labelled approximate.
- Indoor routes and automatic room/floor location are not supplied by the floor-plan images alone.
- Building coordinates are not exact room entrances. Supported train geometry uses official RFN infrastructure corridors, not certified service-specific tracks.
- Provider licences and original source attribution should accompany demonstrations and redistributed datasets.

## Official venue sources rechecked

- https://bu.umlp.fr/bibliotheques/bu-montbeliard/
- https://bu.umlp.fr/bibliotheques/bu-belfort/
- https://bu.umlp.fr/services/acceder-aux-salles/
- https://bu.umlp.fr/bibliotheques/calendrier-douverture-des-bu/
- https://bibliotheque.utbm.fr/
- https://bibliotheque.utbm.fr/services/questions_reponses/


## Catalogue update — 27 October 2026

29 visible records cover campus library rooms, Numerica, CCI Place des Entrepreneurs, Bristol meeting facilities and tea salon, La Féelicità, city libraries, AZAP La Jonxion, Sevenans and the photographed STGI room. Eleven records have identified use permission and weekly hours and may be proposed conditionally; eighteen need further access/hours/room verification. The old generic Belfort room is excluded so it cannot bypass the actual three-person minimum of its named rooms. Coordinates and precision/source notes are attached per record. Numerica and STGI room positions are building/campus approximations. Quietness is not measured; unknown values are retained.
