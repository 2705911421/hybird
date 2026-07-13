# Phase 9 known issues

- Portable release archives are not signed native installers. Node 22 remains required for the InkOS shell; the Runtime itself embeds Python.
- The Runtime process manager is implemented as a core library but is not yet wired into the Studio/CLI bootstrap or bundled-binary resolver.
- SQLite authority on NFS, UNC, cloud-sync or other network filesystems is unsupported.
- Optional vector retrieval is not configured in the baseline; deterministic exact/trigram lexical retrieval remains available offline.
- The Studio main entry chunk is 2.53 MiB and first cold load P95 was 2.51 s on the measured Windows machine.
- Windows development-workspace standalone smoke passed, but Windows clean-machine, macOS/Linux package smoke, native installer smoke, 24-hour soak and complete disaster drills have no accepted artifacts yet.
- Production downgrade is snapshot restore only unless a release note explicitly marks a migration reversible.
