# FastRead Go / React release

## Product scope

The API and durable worker run in Go. The React workbench retains PDF reading,
page-linked evidence, annotations, reports, chat, knowledge libraries, notes,
paper discovery, and local / Research / FastCAS authentication. React uses
`@fastrd/ui-react` and `@fastrd/ui-foundation` 0.3.0.

The application header contains the paper library, user administration, and
system administration buttons. Account identity, sign out, settings, CAS linking,
and the theme toggle appear on the right. Settings and CAS open in dialogs.
Personal providers live in settings; system administrators assign shared
providers to workspaces and individual users. Workspace grants cover all members;
individual grants cover only the named user. Either grant is sufficient. Both
scopes are edited in one dialog and saved atomically. Existing workspace grants
remain valid after the additive user-grant table migration. Model listing, model
selection and worker dispatch all check the submitting account; disabled users
and removed workspace members cannot dispatch queued model requests.

Research exchange connects reading evidence to FastWrite projects and turns
selected papers into editable FastNews research interests. Source paper IDs and
page references remain attached to generated results.

## Accounts and connections

Existing passwords, local sessions, Research identities, and CAS links retain
their workspace. System administration is assigned with `FASTREAD_ADMIN_EMAILS`
or `user-create --admin`; ordinary workspace ownership remains separate.
The initial production administrator list is empty.

Generate a FastRead connection code in the destination service's account or
research panel. Paste it in FastRead Settings → Integrations. Codes are encrypted
at rest in FastRead and can be rotated or revoked in the destination service.
FastWrite project access follows that account's current project permissions.
News directions support append or replace within its 4,000-character limit.

FastWrite receives the paper metadata, BibTeX, source excerpts, and notes as an
immutable bundle. The writing panel can attach a feedback note to a source paper;
“取回写作笔记” imports it into that paper's reading notebook. Repeated imports
update the same note.

## Runtime

`backend-go/cmd/fastread` provides `serve`, `worker`, `user-create`, `invite`,
and `recovery`. The API and worker share `FASTREAD_WEB_ROOT`. Uploaded PDFs and
the existing `fastread-web.sqlite3` remain under that root. Poppler provides
`pdftotext` and `pdfinfo` for the native worker.

The frontend can be hosted separately with `/api` routed to the Go API. The
optional `FASTREAD_FRONTEND_DIST` serves a built frontend from the Go process.
Provider credentials, account records, and deployment configuration stay outside
the release archive.

## Build and publish

```bash
cd backend-go
go test -race ./...
go vet ./...
CGO_ENABLED=0 go build -trimpath -o ../bin/fastread ./cmd/fastread
cd ../fastread-frontend
pnpm install --frozen-lockfile
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

FastDeploy v2.1.0 packages the native executable, React dist, and Poppler runtime.
Version tags matching `v*-deploy.*` trigger the server workflow. The deployment
retains the old release, shared data, and previous service definitions for the
repository's rollback workflow. Before publishing, inspect the current queue and
back up SQLite through its backup API together with the uploaded files.

The compatibility results are recorded in [Migration validation](MIGRATION_VALIDATION.md).
