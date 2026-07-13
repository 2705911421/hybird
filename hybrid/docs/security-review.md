# Phase 9 security review

## Implemented controls

- Runtime CLI only accepts loopback hosts; LAN exposure needs a separate design.
- Random 256-bit bearer is generated in trusted Node code and passed through the child environment. It is not written to frontend configuration.
- Authorization headers, bearer/API keys/secrets, home paths, prompts and chapter bodies are redacted or omitted from structured logs/diagnostics. Request operations use route templates instead of raw paths, and project IDs are pseudonymized.
- Requests above 16 MiB are rejected before Pydantic body validation using both declared and actually received body bytes. Malformed JSON/DTOs return bounded 422 errors.
- Snapshot restore accepts exactly two known archive members, verifies checksum, restores only to a new directory and never extracts caller paths.
- Legacy migration does not follow symlinks and reports zip-slip entries; Studio and agent file tools have traversal tests.
- Retrieval content is `untrusted_content`; prompt-like prose cannot alter validator policy or Runtime capabilities.
- SQLite stays local, WAL/foreign keys/busy timeout are explicit, and schema-too-new never triggers an automatic down migration.
- CI runs pip audit, pnpm audit, gitleaks and CycloneDX generation. Release binaries have SHA-256 files and corresponding source.

CORS middleware is not enabled on Runtime. The browser does not call Runtime directly; Studio's server-side proxy is the trust boundary. CSRF protection relies on loopback-only Studio and same-origin API behavior; any future LAN access requires origin validation, session authentication and CSRF tokens.

## Residual risks and blockers

- Actions and npm audit/SBOM tooling are tag/version referenced rather than fully vendored; release maintainers must review supply-chain updates and pin immutable action SHAs.
- Default development token remains intentionally obvious when Runtime is launched manually; production package manager always supplies a random token.
- Native code signing/notarization and installer integrity are not implemented.
- ENOSPC, antivirus lock and corruption drills need clean-machine evidence.
- A full third-party license inventory is generated in CI but has not yet been reviewed/attached for this working tree.
