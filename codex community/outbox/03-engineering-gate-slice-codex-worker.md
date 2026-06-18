# Task 03: Engineering Gate Slice

## Findings

Best low-conflict patch candidate: add browser extension checks to `.github/workflows/quality-gate.yml`.

Why this slice:

- The current quality gate checks backend tests, frontend lint/build, and `docker compose config`.
- The refactor ledger says the extension was brought to a Cookie Sync MVP and `npm run typecheck` / `npm run build` passed, but the CI workflow does not enforce that.
- This does not compete with backend/frontend source edits.
- The extension already has `packageManager: "npm@11.12.1"` and a committed `package-lock.json`, so `npm ci` is the right CI install command.

Current package-manager state:

- Frontend is intentionally pnpm: `reel-mind-frontend/package.json` has `packageManager: "pnpm@9.15.0"` and `pnpm-lock.yaml`.
- Extension is intentionally npm: `reel-mind-extension/package.json` has `packageManager: "npm@11.12.1"` and `package-lock.json`.
- Root docs and `run.bat` consistently use pnpm for the frontend local path.
- Extension README consistently uses npm for extension development.

Contradictions / remaining engineering cleanup:

- `.github/workflows/quality-gate.yml` does not currently check the extension despite the refactor plan treating extension typecheck/build as a gate.
- `Dockerfile.complete` still rewrites nginx `frontend:80` to `127.0.0.1:8080`, but the same Dockerfile copies frontend static files into `/usr/share/nginx/html` and does not start a frontend server on 8080. This matches the plan's note that single-image Docker needs either repair or retirement. I would not patch this before the main agent decides the final Docker strategy.

## Recommended Patch

Add a new job to `.github/workflows/quality-gate.yml`:

```yaml
  extension-checks:
    name: Extension typecheck and build
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: reel-mind-extension

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: reel-mind-extension/package-lock.json

      - name: Install extension dependencies
        run: npm ci

      - name: Typecheck extension
        run: npm run typecheck

      - name: Build extension
        run: npm run build
```

Exact files likely to change:

- `.github/workflows/quality-gate.yml`

Optional documentation follow-up:

- Add one sentence under `README.md` testing section saying CI runs backend tests, frontend lint/build, extension typecheck/build, and compose config.

## Risks

- `npm@11.12.1` in `packageManager` may be newer than the npm bundled with Node 20. If CI enforces package manager versions through corepack, it may need `corepack enable` plus npm activation. If not, `npm ci` should use the bundled npm and still honor `package-lock.json`.
- `npm run build` may emit extension artifacts under `reel-mind-extension/extension/`; CI workspace writes are fine.
- If extension dependencies include browser or Playwright downloads in postinstall, CI time may increase. Current scripts do not require e2e for this slice.

## Verification

Suggested local verification:

```powershell
cd reel-mind-extension
npm ci
npm run typecheck
npm run build
```

Suggested full gate after patch:

```powershell
backend\.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest backend\tests
cd reel-mind-frontend
pnpm run lint
pnpm run build
cd ..\reel-mind-extension
npm run typecheck
npm run build
```

Commands run for this report:

- `rg --files .github reel-mind-frontend reel-mind-extension | rg "(quality-gate\\.yml|package\\.json|package-lock\\.json|pnpm-lock|yarn\\.lock)$"`
- `rg -n "pnpm|npm|packageManager|package-lock|pnpm-lock|Docker|docker|corepack|quality" README.md README-usage.md OPEN_ME_FIRST.md DEPLOYMENT.md run.bat .github/workflows/quality-gate.yml reel-mind-frontend/package.json reel-mind-extension/package.json reel-mind-extension/README.md Dockerfile.complete docker-compose.yml`
- `git status --short -- reel-mind-frontend/package-lock.json reel-mind-frontend/pnpm-lock.yaml reel-mind-extension/package-lock.json reel-mind-extension/pnpm-lock.yaml .github/workflows/quality-gate.yml run.bat README.md README-usage.md OPEN_ME_FIRST.md DEPLOYMENT.md Dockerfile.complete docker-compose.yml`
- Read-only inspection of the files listed below.

Tests were not run; this was a read-only worker investigation.

## Files Inspected

- `readme/refactor-plan-2026-06-04.md`
- `.github/workflows/quality-gate.yml`
- `README.md`
- `README-usage.md`
- `OPEN_ME_FIRST.md`
- `DEPLOYMENT.md`
- `run.bat`
- `Dockerfile.complete`
- `docker-compose.yml`
- `reel-mind-frontend/package.json`
- `reel-mind-frontend/pnpm-lock.yaml`
- `reel-mind-extension/package.json`
- `reel-mind-extension/package-lock.json`
- `reel-mind-extension/README.md`
