# RC-2B1D2 Legacy First-Write Matrix

| Family | Automated evidence |
|---|---|
| L1 plain current state | populated entities/facts/chapters; one boundary and one native revision |
| L2 null event metadata | null schema/applied revision remains unchanged |
| L3 partial commits | prepared legacy commit remains unchanged |
| L4 imported project | real migration-job provenance retained |
| L5 migration 7 DB | real schema 7 upgraded additively to 8 |
| L6 migration 8/no write | no manifest appears during migration |
| L7 existing boundary | bootstrap is reused; first native is R8 |
| L8 interrupted boundary | before/after boundary insert rollback |
| L9 interrupted native write | event, manifest, CAS and ledger faults rollback |
| L10 concurrent first write | different-key and chapter-vs-diff races have one winner |
| L11 response loss retry | same request returns R8, never R9 |
| L12 malformed optional metadata | unreadable optional legacy evidence is preserved |
| L13 unknown compatibility | Doctor fails closed without rewriting rows |
| L14 legacy revision 0 | populated state creates boundary R1 then native R2; no fake R0 |
| L15 revision 9999 | boundary R9999 then native R10000 |

Failure tests reopen the database after rollback. SQLite lock/retry, same-key
concurrency, idempotency conflict, process reopen, and a missing first native row
after a valid boundary are covered. All fixtures assert no fabricated earlier
manifests, no changed legacy events/entities/facts/partial commits, one boundary,
one native successor, correct previous hash, and no duplicate/gap. The public
historical API remains fail-closed below the boundary.

## Gate 15 conclusion

YES. The dedicated file contains 26 passing tests. This is current-state boundary
verification only; it creates no historical state table or pre-boundary history.
