# Revision Manifest Doctor Notes

The deep doctor checks:

- current project pointer versus latest manifest;
- a valid revision 0 or explicit bootstrap lineage start;
- contiguous managed revision chain and previous hash;
- canonical manifest hash and ordered event-membership hash;
- event count, ordered IDs/hashes, event revision and range accelerators;
- artifact reference/hash alignment and chapter artifact/commit linkage;
- committed command or finalized chapter transition linkage for non-bootstrap manifests;
- required compatibility-version fields;
- missing ledger, missing event, missing/mismatched artifact and malformed chain.

Database uniqueness constraints make duplicate project revision, manifest ID, command ID and commit linkage insertion fail before doctor, while doctor verifies the observable chain. A Runtime-authority project with no manifest is a blocking failure. A legacy project awaiting cutover receives the advisory `manifest.bootstrap_required`; doctor recommends one explicit boundary and does not synthesize it.

Repair is deliberately absent. The only guidance for corrupted immutable authority is exact hash-matching backup restoration/operator investigation. Projection replay may repair derived projections but cannot alter events, manifests or project revision.
