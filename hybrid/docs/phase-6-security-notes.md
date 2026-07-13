# Phase 6 security notes

## Trust boundaries

Runtime binds locally and authenticates project data with an opaque bearer. Studio is a local same-origin UI. Only the Studio server reads `storyRuntime.apiTokenEnv`; browser JavaScript, local storage, session storage, DTOs, download filenames, logs, and error bodies never receive that bearer.

Studio never opens Runtime SQLite, `.story-system`, the Runtime data directory, projection files, or internal JSON logs. The Runtime repository remains the sole SQL boundary.

## Redaction

Runtime recursively redacts API keys, provider secrets, tokens, Authorization/bearer values, environment/traceback fields, home directory usernames, database paths, and content/body/text fields on diagnostic and event surfaces. Error handlers apply the same redactor. Studio then maps failures to fixed copy without forwarding raw Runtime text.

Diagnostic reports include versions, schema, non-sensitive configuration booleans, commit/projection/doctor status, recent redacted errors, and checksums. They exclude credentials, environment dumps, absolute database paths, provider tokens, SQL/table names, and novel prose.

## Recovery controls

Operation names and parameter keys are allow-listed at both Studio and Runtime. Confirmation tokens are job-bound and one-use. Runtime rechecks durable job state inside an immediate transaction before executing. No API accepts arbitrary SQL, path, revision mutation, validation bypass, or event deletion.

## Residual boundaries

The current Studio local server has no separate user login; its boundary is loopback access and the local OS account. Deploying it beyond localhost requires an external authenticated reverse proxy and is outside Phase 6. Snapshot restore remains intentionally blocked until snapshot authenticity, revision lineage, and atomic restore are implemented and tested.
