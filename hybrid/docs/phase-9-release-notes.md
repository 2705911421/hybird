# Phase 9 stabilization release notes (draft)

Phase 9 adds scale indexes and Chinese trigram retrieval, bounded structured logs, online snapshot/safe restore, explicit upgrade compatibility, deterministic million-character benchmark and soak tools, robust Runtime lifecycle management, cross-platform/offline/package CI, SBOM/license/source release automation and operations documentation.

It also fixes two Studio Runtime defects found by browser measurement: the Runtime menu passed a click event as a route segment, and overview polling refetched continuously instead of every 30 seconds.

No new story domain, authority database, distributed service, Runtime or required real-model test was added. This draft is not a release announcement; all blockers in `release-checklist.md` must be closed first.
