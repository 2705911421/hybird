# Studio Runtime API

Studio exposes a same-origin server-side proxy under `/api/v1/story-runtime`. It is not a second authority API. Each handler loads the current InkOS project configuration, reads the bearer from `storyRuntime.apiTokenEnv`, calls `/api/story-runtime/v1`, validates the response with Zod, and returns a browser-safe DTO.

## Read routes

- `GET /status`
- `GET /projects/:id/overview`
- `GET /projects/:id/commits?cursor&limit&chapter&state&fromDate&toDate`
- `GET /projects/:id/commits/:commitId`
- `GET /projects/:id/events?cursor&limit&eventType&aggregate&chapter&revision&view`
- `GET /projects/:id/projections`
- `GET /projects/:id/doctor?deep=false`
- `GET /projects/:id/reviews/status`
- `GET /migration/status`
- `GET /configuration/status`
- `GET /projects/:id/diagnostics`
- `GET /projects/:id/recovery-jobs?cursor&limit`

## Recovery routes

- `POST /projects/:id/recovery-jobs/preview`
- `POST /projects/:id/recovery-jobs/:jobId/execute`
- `POST /projects/:id/recovery-jobs/:jobId/cancel`

The proxy supplies the fixed local actor `studio-user`. It accepts only allow-listed operation names and parameters. Browser input cannot provide an operator scope, Runtime bearer, expected revision override, SQL, or arbitrary Runtime path.

## Error envelope

Proxy failures use `{ runtimeState, error: { code, message, retryable } }`. Raw response bodies, stack traces, bearer values, and internal exception messages are never returned. A malformed DTO maps to `version_mismatch`; a network/timeout failure maps to `unavailable`.
