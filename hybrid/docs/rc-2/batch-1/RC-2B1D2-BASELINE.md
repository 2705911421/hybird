# RC-2B1D2 Baseline

## Candidate identity

- Repository: `2705911421/hybird`
- Branch: `master`
- HEAD: `e2a34b5738ffb3ca4d7718b058d4046ca91d4e49`
- `origin/master`: `e2a34b5738ffb3ca4d7718b058d4046ca91d4e49`
- Ahead/behind: `0/0`
- Commits since the failed candidate: none
- Staged / unstaged / untracked: none before this document was created

## Reproduction before modification

The existing RC-2B1D dedicated suite passed (`36 passed`), which confirms that the
remaining defects are outside its assertions. An independent disposable database
and Runtime copy under `C:\tmp` reproduced both implementation defects.

### Missing revision

The fixture created `R0 -> R1 -> R2 -> R3 -> R4` and deleted R2. The stored rows
were `[0, 1, 3, 4]`. The current Doctor emitted:

```text
R3 MISSING_PREDECESSOR
R4 AFFECTED_BY_PRIOR_CORRUPTION
latest_trusted_revision=1
first_untrusted_revision=3
total_affected_revisions=2
```

This loses the logical R2 node and conflates downstream-of-gap with
downstream-of-corruption. The required first-untrusted revision is 2 and the
required affected count is 3.

### Indirect allocator bypass

A disposable production copy added a generic repository method that constructs
`UPDATE projects SET {field}=?` with `field = "revision"`, then called it from a
migration job. The architecture gate exited 0. The current model scans every
production Python file by default, but detects only local AST revision arithmetic
and complete literal SQL strings. It does not index symbols, resolve calls, or
propagate forbidden sinks through helpers.

### Current repository helper layer

Runtime data access is concentrated in `StoryRepository`, while authority writes
also use direct connection helpers inside the allocator, chapter service, and
legacy migration service. There is no approved directory-wide repository
exception. The only approved revision-write semantics remain the exact
`ProjectRevisionAllocator.execute` path and the documented limited-history
boundary establishment methods.

## Verification gaps

### Gate 11 ownership

The existing seven tests inspect manifest schema/model fields, one modest CJK body,
one event, artifact deletion, event deletion, artifact schema compatibility,
commit revision linkage, and event command linkage. Missing evidence includes
large-body size invariance, multi-event ordering/count/range, large review and
binary-like/structured payloads, cross-project/cross-commit artifact references,
duplicate identity, and explicit manifest-only reconstruction negatives.

### Gate 15 legacy first write

The existing four tests cover a migration-7 fixture, one rollback at ledger insert,
two-command concurrency, retry, historical API fail-closure, and unknown old-event
schema. Missing evidence includes the complete L1-L15 fixture families, boundary
and native-write failure points, migration-8/no-write and existing-boundary states,
revision 0 and large revision boundaries, imported/partial-artifact variants,
response-loss/process-reopen/lock behavior, and the full concurrency matrix.

## Local JavaScript environment

- pnpm: `11.13.0`
- lockfile: `lockfileVersion: '9.0'`
- `inkos/package.json` and `inkos/pnpm-lock.yaml` both contain overrides, but pnpm
  11 reports the previously recorded lockfile-configuration mismatch.
- This environment limitation is not caused by RC-2B1D2 and must not be repaired
  by changing pnpm, the lockfile, dependencies, or workspace configuration.

## Scope boundary

RC-2B1D2 may change only Doctor missing-revision semantics, architecture helper
call-graph enforcement, Gate 11/15 tests, and corresponding Batch 1 documents. It
does not address Phase 9, the transient RC-1 run, local pnpm configuration, Batch 2,
historical APIs, snapshots, or time travel.
