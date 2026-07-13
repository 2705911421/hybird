# Capacity limits

Verified on one Windows machine: 1.096 million generated Chinese characters, 600 chapters, 24,002 facts, 12,000 events, 3,200 relationships and 420 threads in a 23.7 MiB SQLite database. This proves the tested point, not an unlimited capacity claim.

| Limit | Supported/default |
|---|---|
| Projects per Runtime database | multiple, single local process owner |
| Concurrent authority writers | one SQLite writer; callers retry bounded lock errors |
| HTTP request | 16 MiB default |
| Context items/tokens | contract max 500/100,000; product defaults 100/16,000 |
| Event append command | 1,000 operator events; typed diff 100 |
| Studio page | 1-100 server-bounded items |
| Migration file/total/count | 64 MiB / 4 GiB / 200,000 |
| Runtime logs | 10 MiB each, five backups by default |
| WAL checkpoint | automatic at 1,000 pages; operator PASSIVE/FULL/RESTART/TRUNCATE |
| SQLite filesystem | local disk only; no NFS/UNC/sync-folder authority guarantee |

Capacity beyond 1.1 million characters, 24k facts or 12k events requires a benchmark artifact before support is claimed. Disk free space must cover the live DB, WAL, one online backup copy, compressed snapshot and migration working space; operations should reserve at least 3x current DB size plus blob size.
