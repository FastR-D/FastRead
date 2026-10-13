# Web startup and synchronized release

The web entry loads the React UI in parallel with session verification. It reuses
the verified user, deduplicates concurrent GETs, and loads Markdown/KaTeX only
when content needs them. Network/authentication failures show a retry action.
Anonymous visitors retain local and optional FastCAS login.

The same relative Vite build serves `/` and `/Read/`. API, PDF vendor resources,
exports and reading links stay under the entry path. The blue/white knowledge
workspace is retained. Stable Research account IDs preserve workspace identity
across key changes; production import metadata overrides are included.

Validation before release:

- Frontend type check, lint, build and 71 unit tests passed.
- Backend suite passed on Linux (Windows DPAPI case skipped).
- Migration on a copy of the production DB checked 16 owner workspaces,
  library/knowledge/auth endpoints, SQLite integrity and foreign keys.
- Edge using the release build at the canonical origin checked library, PDF
  canvas, lazy Markdown reports, reader reload and `/Read/` navigation. It also
  checked anonymous login, HTTP 503, aborted UI scripts and auth timeout.
- Earlier 512 Kbps / 200 ms simulated-network tests on the old IP entry reduced
  median startup from 7.92 s to 4.88 s. This is candidate evidence, not a measured
  speedup for the public domain. The complete first screen still loads React,
  application code, CSS and API data; the ~5.6 KB entry is only the bootstrap.

Release verification uses the Git revision of the local checkout, GitHub main,
and the server checkout, plus `release.json` in the served frontend. Source is
shipped from a Git bundle, with the complete Vite dist from the same revision.
Keep previous release directories and a deployment receipt/rollback script.
Before switching: verify the queue is idle, back up SQLite, and test Nginx config.
The active source and frontend are selected by symlinks. Do not restore an old
database during ordinary code rollback, as it would discard later user data.
