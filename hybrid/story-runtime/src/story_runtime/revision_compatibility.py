"""Central compatibility registry for immutable revision-manifest verification.

Batch 1 persists only the fields already present in migration 8.  Derived
protocols (hash tagging and canonical JSON) live here as verification policy;
they are not new history or replay capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompatibilityField:
    diagnostic_code: str
    supported_values: frozenset[str]
    stops_integrity_verification: bool = False
    replay_safety_relevant: bool = False


KNOWN_REVISION_COMPATIBILITY: dict[str, CompatibilityField] = {
    "manifest_schema_version": CompatibilityField(
        "UNKNOWN_MANIFEST_SCHEMA_VERSION",
        frozenset({"revision-manifest/v1"}),
        stops_integrity_verification=True,
    ),
    "event_schema_version": CompatibilityField(
        "UNKNOWN_EVENT_SCHEMA_VERSION",
        frozenset({"legacy-unversioned", "story-runtime/v1"}),
        replay_safety_relevant=True,
    ),
    "reducer_version": CompatibilityField(
        "UNKNOWN_REDUCER_VERSION",
        frozenset({"story-reducers/legacy-v1", "story-reducers/not-applicable"}),
        replay_safety_relevant=True,
    ),
    "artifact_schema_version": CompatibilityField(
        "UNKNOWN_ARTIFACT_SCHEMA_VERSION",
        frozenset({"story-runtime/v1", "review-artifacts/v1"}),
        replay_safety_relevant=True,
    ),
    "hash_algorithm": CompatibilityField(
        "UNKNOWN_HASH_ALGORITHM",
        frozenset({"sha256"}),
        stops_integrity_verification=True,
    ),
    "canonicalization_version": CompatibilityField(
        "UNKNOWN_CANONICALIZATION_VERSION",
        frozenset({"manifest-canonical-json/v1"}),
        stops_integrity_verification=True,
    ),
    "provenance_class": CompatibilityField(
        "UNKNOWN_PROVENANCE_VERSION",
        frozenset({"native", "verified_import", "bootstrap_boundary", "compensation"}),
        replay_safety_relevant=True,
    ),
    "transition_kind": CompatibilityField(
        "UNKNOWN_COMPATIBILITY_VERSION",
        frozenset({
            "initialize_empty", "chapter_finalize", "chapter_replace", "domain_command",
            "bootstrap", "verified_import", "compensation", "tombstone", "restore",
        }),
        replay_safety_relevant=True,
    ),
    "contract_version": CompatibilityField(
        "UNKNOWN_COMPATIBILITY_VERSION",
        frozenset({"story-runtime/v1"}),
        replay_safety_relevant=True,
    ),
    "bootstrap_compatibility_version": CompatibilityField(
        "UNKNOWN_COMPATIBILITY_VERSION",
        frozenset({"bootstrap-boundary/v1"}),
        replay_safety_relevant=True,
    ),
}


def supported_values(field: str) -> list[str]:
    return sorted(KNOWN_REVISION_COMPATIBILITY[field].supported_values)
