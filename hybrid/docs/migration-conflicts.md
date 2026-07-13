# Phase 7 migration conflicts

Every conflict contains `conflict_id`, `type`, `severity`, `blocking`, `sources`, `candidates`, `evidence`, `recommended_decision`, `user_decision`, and `resolution_audit`.

Supported types are:

- `duplicate_entity`, `ambiguous_alias`, `conflicting_fact`, `conflicting_relationship`;
- `chapter_body_mismatch`, `chapter_number_gap`, `duplicate_chapter`;
- `timeline_conflict`, `hook_state_conflict`, `unknown_event_type`;
- `invalid_resource_value`, `review_body_hash_mismatch`, `orphan_reference`;
- `corrupted_source`, `unmapped_field`.

Blocking conflicts move the job to `AWAITING_DECISIONS`. Studio shows source, candidate values, evidence, and the recommendation. It intentionally has no “skip all” control. A user may `choose_candidate`, `merge`, `ignore`, or `quarantine`; candidate selection requires a candidate ID. Decisions are append-audited and survive pause/resume and retries.

Quarantine means the disputed CIR item is excluded from authority import but remains in job evidence and reports. It is not deletion. Recommendations such as “prefer structured JSON” are advisory only.

