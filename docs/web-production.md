# Web deployment and integrations

The web application includes a PDF reader with annotations, knowledge libraries,
source-grounded organization and questions, and persistent notebook notes. Model
jobs run on the worker; the browser displays organization progress immediately
and follows the server's queued, running, succeeded, and failure states.

## FastResearch authentication

The web entry point now requires FastResearch SSO. Password login and automatic
public guest sessions are disabled. Configure these on the backend:

```dotenv
FASTRESEARCH_API_URL=http://127.0.0.1:8787
FASTRESEARCH_PANEL_URL=https://research.example.org
FASTREAD_COOKIE_SECURE=true
```

The API consumes a one-time ticket at `POST /api/sso/consume` with audience
`fast-read`. Each research identity owns a separate workspace. Re-entering with
a new ticket invalidates that identity's previous sessions. The browser exchanges
the ticket through `/api/auth/research`, removes it from the URL, and obtains its
CSRF token from `/api/auth/me`. Cookie-authenticated mutations require
`X-CSRF-Token`. Keep API credentials and production configuration outside Git.

Both backend document routing and the frontend bootstrap handle SSO because
deployments may serve HTML through a separate static server. The bootstrap is
part of the normal Vite build; a patched production bundle is no longer needed.

## FastNews metadata intake

The web entry accepts `source=fastnews` with `title`, optional `authors`,
`abstract`, `url`, `venue`, `year`, and `external_id` query parameters. After login,
the bootstrap sends them to `POST /api/integrations/fastnews/intake`. This records
metadata in the authenticated workspace without downloading the paper. Repeated
intake is deduplicated within that workspace. Users attach their PDF through
`POST /api/imports/pdf` with multipart `file` and `paper_id`. Reading endpoints
return a request to upload the PDF until a document version exists.

## Build, delivery, and rollback

Build the frontend using `pnpm install --frozen-lockfile` and `pnpm run build`
inside `fastread-frontend`. Publish the complete `dist` directory, including
vendored PDF.js files and their license notices. Keep previous assets available
for clients with an older page open. Give HTML revalidation/no-cache semantics;
fingerprinted assets may be cached. Retain authentication on PDF requests, byte
range/206 and HEAD support, and ETag/304 revalidation. Do not gzip PDF responses
or apply API-wide `no-store` rules to them. Other private API responses remain
non-cacheable.

Use new release directories, preserve the previous release, and atomically swap
the active symlink. Check service health and queued/running jobs before changing
the backend or worker. A frontend-only release does not require a worker restart.
Keep runtime data, uploaded papers, login files, provider secrets, and host-specific
deployment helpers out of release source commits.

Validation: run root `python -m pytest`; run frontend `pnpm run lint`,
`pnpm run typecheck`, `pnpm test`, and `pnpm run build`. On Windows, a writable
workspace-local `--basetemp` can avoid temporary-directory permission errors.
