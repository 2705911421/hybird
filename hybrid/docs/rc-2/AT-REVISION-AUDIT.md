# `at_revision` Audit

## Final classification

**Current `at_revision` is a pseudo-implementation.** It only rejects a number greater than the current project revision and then returns the current entity row. It does not select validity rows, run replay, load a snapshot or verify that the requested revision actually exists.

## Call chain

| Layer | Current behavior | Finding |
| --- | --- | --- |
| OpenAPI | advertises optional non-negative `at_revision` on entity GET | contract implies historical semantics it does not define or deliver |
| FastAPI route | calls `services.entity(...)`; afterward rejects only `at_revision > result.revision` | requested revision is never passed downward |
| service | reads current project, returns current project revision and repository entity | no revision parameter |
| repository | `SELECT * FROM entities WHERE project_id=? AND entity_id=?` | current overwrite table only |
| SQL | no validity predicate, event scan or snapshot join | latest-only |
| DTO | `EntityResult {project_id, revision, entity}` | `revision` is latest project revision, not requested/effective revision; no schema/reducer/provenance manifest |
| entity history | optional `history_json` | contains sparse caller-provided markers, not reconstructible entity states |
| TypeScript client | no entity query method and no `atRevision` field/schema | feature is not consumable through the governed TS boundary |
| Studio | no historical entity/state surface; event filter is an event-list filter only | no time travel |
| Runtime CLI | exact `query --entity` calls current service; no revision option | no historical query |
| InkOS CLI/TUI | no historical entity/state consumer | no time travel |
| tests | entity current/history marker and replay-hash tests only | no 1/2/3 historical assertion existed before this audit |

Relevant code:

- `api.py:280-285` — future-only check after current read;
- `services.py:62-64` — current project/current entity;
- `repository.py:122-130` — current-row SQL;
- `contracts.py:343-355` — DTO has no effective requested revision metadata;
- `story-runtime.openapi.yaml:363-388` — public parameter advertised;
- `StoryRuntimeClient` — no corresponding entity or historical query method.

## Dynamic revision 1/2/3 fixture

One temporary Runtime-authority project was created at revision 0. Three atomic operator commands then changed:

| Revision | entity location | entity resource | entity relationship marker | relationship trust | fact values |
| ---: | --- | ---: | --- | --- | --- |
| 1 | `dock` | 10 | `new` | `new` | dock / 10 |
| 2 | `tower` | 7 | `trusted` | `trusted` | tower / 7 |
| 3 | `vault` | 2 | `broken` | `broken` | vault / 2 |

Actual HTTP responses:

| Query | HTTP | returned DTO revision | location/resource/relationship | Correct? |
| --- | ---: | ---: | --- | --- |
| `at_revision=0` | 200 | 3 | vault / 2 / broken | **No**; entity did not exist in empty rev 0 state |
| `at_revision=1` | 200 | 3 | vault / 2 / broken | **No** |
| `at_revision=2` | 200 | 3 | vault / 2 / broken | **No** |
| `at_revision=3` | 200 | 3 | vault / 2 / broken | yes only because target is latest |
| `at_revision=4` | 404 `REVISION_NOT_FOUND` | — | — | future rejection works |
| `at_revision=-1` | 422 validation error | — | — | input bound works |

There are no public relationship/resource historical endpoints to run. The entity payload intentionally mirrored those values so the current-route defect could be observed, while actual relationship and fact events were also persisted and replayed separately.

## Missing and nonexistent revisions

No revision ledger exists. Consequently:

- any integer `0 <= R <= current` is accepted by the entity route;
- the route cannot distinguish an actual finalized transition from a fabricated/gapped number;
- it cannot return a revision manifest;
- revision 0 incorrectly returns entities created later;
- “missing revision” and “history pruned/unavailable” cannot be expressed.

The normal current write path increments by one, but imported/bootstrap projects can start with a higher current revision without authoritative transition records for every earlier value. Therefore arithmetic range validation is not evidence that a revision exists.

## Migration boundary fixture

The committed `lighthouse-project.json` bootstrap declares project revision 7. It contains two event rows with `applied_revision=NULL` and no chapter commits.

Actual queries for entity `char-lin`:

| Requested revision | HTTP | returned revision/state |
| ---: | ---: | --- |
| 0 | 200 | rev 7 current North Harbor state |
| 1 | 200 | rev 7 current North Harbor state |
| 6 | 200 | rev 7 current North Harbor state |
| 7 | 200 | rev 7 current North Harbor state |
| 8 | 404 | future rejected |

This proves both the pseudo-implementation and the absence of honest pre-migration history. Copying the rev-7 state into revisions 0–6 would fabricate history and is prohibited.

## What the current implementation uses

| Mechanism | Used by entity `at_revision`? |
| --- | --- |
| current table | **yes** |
| future revision validation | **yes** |
| `valid_from_revision` / `valid_to_revision` | no |
| event replay | no |
| snapshot | no |
| revision ledger/manifest | no |
| history availability boundary | no |

## Required contract behavior

Until RC-2 is implemented, the parameter should be considered non-conforming. RC-2B must route every historical endpoint through one `HistoricalStateService` that first resolves an existing revision manifest, applies a declared history boundary and then uses one documented architecture for all domains. The service must return the requested/effective revision, event schema, reducer version, provenance and availability status; it must never return latest under an older requested number.
