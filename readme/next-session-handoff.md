# ReelMind Next Session Handoff

Updated: 2026-06-21

This is the first file the next conversation should read.

## Product Direction

ReelMind has pivoted to verification-first.

P0 is no longer notes, mind maps, cards, Q&A, or video summarization. P0 is:

```text
输入文本/URL -> 主张原子化 -> 多源联网检索 -> 抓取原文/PDF -> 信源验真 -> 证据抽取 -> 交叉判定 -> 可审计核验报告
```

Quality is allowed to cost time, requests, and old UX convenience. Search snippets are recall hints only. They must never produce `supported`.

## Current Workspace

```powershell
E:\C_Moved_From_C\Users\Lenovo\Desktop\schoolwork\reelmind
```

Current local services after the last run:

```text
Backend:  http://127.0.0.1:8483
Frontend: http://127.0.0.1:5173
```

The DeepSeek provider is configured locally in the app database. Do not write or echo API keys in docs, logs, commits, or final messages.

## Current Implementation Status

### Backend Verification Core

Implemented a new verification pipeline under:

- `backend/app/services/verification/schemas.py`
- `backend/app/services/verification/claim_pipeline.py`
- `backend/app/services/verification/pipeline.py`
- `backend/app/services/verification/fetching.py`
- `backend/app/services/verification/source_intel.py`
- `backend/app/services/verification/evidence.py`
- `backend/app/services/verification/adjudication.py`
- `backend/app/services/verification/numeric_evidence.py`

`backend/app/services/online_verifier.py` remains the compatibility facade, but now calls the new body-evidence pipeline.

Important current rules:

- `supported`: requires high-trust body evidence and no peer refutation.
- `refuted`: high-trust body evidence contradicts the subject, number, time, place, classification, or relation.
- `mixed`: high-trust support and refutation both exist, usually because of definitions, scope, time range, geography, or source conflict.
- `insufficient`: relevant material exists, but core elements are not covered.
- `data_void`: weak/low-independent/SEO/listicle sources dominate.
- `source_risk`: blocked domains, injection, poisoning, fake authority, or other source risks dominate.

Source tiering now uses:

```text
A = official/regulator/statistics/court/primary research/standards/filings
B = credible institutions, publishers, mainstream reporting, authority databases
C = encyclopedia/blog/republished/list-like secondary content
D = marketing/social/forum/SEO/listicle/portal/weak identity
blocked = local/blocked/unsafe source
```

Same domain, canonical, publisher, or content hash is grouped for independence.

Latest backend verification increments on 2026-06-21:

- GEO/language comparison now promotes cross-region support/refute conflicts to machine verdict `mixed`.
- `geo_disagreement` remains in `risk_flags`, and `audit.pre_geo_verdict` preserves the rule verdict before GEO escalation.
- Verification summaries now count `online_mixed`, so mixed/GEO-conflict evidence is visible at report level.
- Degraded search mode now adds `search_unavailable` when search raises, returns `data_void`, and cannot output `supported`.
- Snippet-only, fetch-failed, content-farm, copied press-release, fake authority, prompt-injection, GEO-conflict, and degraded-search paths are covered by targeted backend tests.
- HTML source identity extraction now resolves schema.org JSON-LD `@graph` `@id` references for publisher/author, reducing false `missing_source_identity` flags on real news/research pages.

Latest documentation/config increments before handoff:

- Root `README.md` now describes ReelMind as verification-first in the first screen, usage flow, config table, extension section, and roadmap.
- Root `.env.example` already documents Brave search, degraded behavior, and OpenAI-compatible examples without real keys.
- `backend/.env.example` is aligned to local backend port `8483`, and now includes `NOTE_OUTPUT_DIR`, `BACKEND_HOST`, `BACKEND_PORT`, Brave/search settings, degraded-mode comments, and OpenAI/DeepSeek placeholder examples without secrets.
- `readme/refactor-plan-2026-06-04.md` no longer lists completed persistence/cache/source-registry/GEO/taskization/popup/docs work as undone; remaining gaps are closer to the current implementation state.
- Light string checks confirmed the edited docs no longer contain the old `127.0.0.1:8000` backend env URL or the old extension wording that framed the popup primarily as Cookie sync.

### Verification Task API

Added first-class verification task APIs in `backend/app/routers/note.py`:

```http
POST /api/verification_tasks
GET  /api/verification_tasks/{task_id}
POST /api/verification_tasks/{task_id}/rerun
POST /api/verification_tasks/{task_id}/claims/{claim_id}/rerun
GET  /api/verification_tasks
```

Implemented task lifecycle in `backend/app/services/note_task_service.py`:

- `create_verification_task`
- `execute_verification_task`
- `rerun_verification_task`
- `rerun_verification_claim`
- `get_verification_task`
- `list_verification_tasks`

Added verification-specific task states in `backend/app/enmus/task_status_enums.py`.

Latest behavior:

- Whole-task rerun defaults to retry failed/incomplete work while reusing completed claim artifacts.
- Single-claim rerun excludes only the target `claim_id` from reusable artifacts and reuses other completed claims.
- Single-claim rerun returns `404` if the task or claim cannot be found from the current verification seed or claim artifact store.
- Per-claim artifacts are stored under `_verification/<task_id>/claims/<claim_id>.json`.

### Frontend Pivot

The web app now defaults toward verification:

- Main action text is verification-first.
- `NoteForm.tsx` submits to `create_verification_task`.
- `MarkdownViewer.tsx` defaults to verification view.
- Added `VerificationReportView.tsx`.
- Report view displays claim verdicts, confidence, evidence, source tiers, fetch status, retrieved time, risk flags, and audit data.
- Verification report supports whole-task retry and per-claim rerun for first-class text/URL verification tasks.
- Whole-task and per-claim reruns now mark the task active immediately, keep the existing report visible, show an inline progress strip, and rely on `useTaskPolling` to live-refresh backend stage/status messages.
- Left-panel rerun uses the same active-task path and no longer waits for the rerun request to finish before polling can begin.
- `/workspace?task_id=<id>` deep links now select restored backend tasks after `loadSavedTasks()`.
- Task snapshot timestamp normalization accepts both `createdAt/updatedAt` and `created_at/updated_at`.

### Extension Pivot

Current published extension scope is still popup-only. It now moves in the verification-first direction:

- Toolbar popup title/action is `ReelMind 联网核实`.
- Popup can submit current page URL or pasted text to `/api/verification_tasks`.
- Created verification tasks are stored in extension local history records.
- After creation, popup opens the web workbench deep link `/workspace?task_id=<id>` instead of the raw API list.
- Backend URL defaults to `http://127.0.0.1:8483` and still falls back to `http://127.0.0.1:3015`.
- Douyin Cookie sync is downgraded to `抖音输入诊断`.
- Manifest/Vite build still declares only popup; `background/contentScripts/options/sidepanel` remain drafts and are not part of the current published extension.

Live browser validation on 2026-06-21:

- Used Playwright CLI with installed Edge (`--browser msedge`) against `http://127.0.0.1:5173`.
- Created a first-class text verification task:

```text
6752bc94-fff6-44f1-9075-22ba7b77e40a
```

Input:

```text
世界卫生组织在2023年宣布阿斯巴甜被列为 IARC 1 类确定致癌物。
```

Observed:

- Initial submit showed the loading stepper while no prior report existed.
- Final report rendered as a first-class verification report with claim-level rerun controls.
- Whole-task rerun preserved the old report, showed inline progress (`多策略联网检索` / `联网检索`), and returned to `SUCCESS`.
- After whole-task rerun, body evidence from WHO was shown and the claim became `refuted`.
- Single-claim rerun preserved the old report, disabled the target claim button as `重跑中`, showed inline progress, returned to `SUCCESS`, and kept a complete report.
- Final backend check for the task: `status=SUCCESS`, `claims=1`, `online_refuted=1`, claim verdict `refuted`, evidence count `10`.

Runtime note:

- The first browser click on single-claim rerun hit `404` because the running backend process had not loaded the new `/api/verification_tasks/{task_id}/claims/{claim_id}/rerun` route.
- Restarting the backend on port `8483` loaded the current source; `/openapi.json` then included the single-claim route and the browser rerun path passed.
- Existing console errors were legacy Douyin `image_proxy` 403s from old history thumbnails, not the verification rerun flow.

Backend quality pass on 2026-06-21:

- Hardened single-claim rerun reuse semantics in `backend/app/services/note_task_service.py`.
- Rerun now resolves the target claim text from current `online.claim_id`, computed candidate IDs, and completed artifact `atomic_claim`.
- Reusable claim artifacts now use current `online.claim_id` / explicit `claim_id` / computed `claim_id` candidates, and skip by both target claim ID and target claim text.
- Stale artifacts that are no longer present in the current verification seed now return `404` instead of executing a misleading rerun.
- Added filesystem verification cache reuse coverage across service instances.
- Added source registry/source-intel edge fixtures for subdomain matching, credential/port URL host normalization, and local blocked domains.

Touched frontend files:

- `reel-mind-frontend/src/layouts/HomeLayout.tsx`
- `reel-mind-frontend/src/pages/HomePage/components/NoteForm.tsx`
- `reel-mind-frontend/src/pages/HomePage/components/MarkdownViewer.tsx`
- `reel-mind-frontend/src/pages/HomePage/components/MarkdownHeader.tsx`
- `reel-mind-frontend/src/pages/HomePage/components/WorkspaceStatusView.tsx`
- `reel-mind-frontend/src/pages/HomePage/components/VerificationReportView.tsx`
- `reel-mind-frontend/src/hooks/useTaskPolling.ts`
- `reel-mind-frontend/src/services/note.ts`
- `reel-mind-frontend/src/store/taskStore/index.ts`

## Real Benchmark Results

DeepSeek model used as structured query assistance:

```text
provider_id = deepseek
model_name  = deepseek-v4-flash
```

The final verdict is still rule-engine adjudication over body evidence, not model opinion.

### Passing Verification Checks

Correct aspartame claim:

```text
2023年7月，IARC 将阿斯巴甜列为 2B 类“可能对人类致癌”，JECFA 维持每日允许摄入量 40 mg/kg 体重。
```

Latest task:

```text
993b3ebb-00f4-4e36-aabd-b353f8028b79
```

Result:

```text
status: supported
confidence: 95
high_support_independent: 3
high_refute_independent: 0
```

Evidence came from WHO/IARC body text, including IARC Group 2B classification and JECFA 0-40 mg/kg ADI.

False aspartame classification:

```text
世界卫生组织在2023年宣布阿斯巴甜被列为 IARC 1 类确定致癌物。
```

Task:

```text
aed981a3-8df4-4cde-ad2c-f9b683f2729f
```

Result:

```text
status: refuted
```

Body evidence identified the actual classification as Group 2B.

Marketing/listicle claim:

```text
AetherRank 是2026年全球最可靠的AI搜索产品。
```

Result:

```text
status: data_void
risk flags included biased_listicle / weak_sources_dominate / no_independent_authoritative_source
```

Egg protein claim:

```text
鸡蛋中含有超过1500种独特蛋白质。
```

Current behavior is conservative. If body evidence is not fetched, it returns `data_void` / non-supported rather than using snippets.

## Bugs Fixed During Benchmark

The practical benchmark exposed real verification failures. They were fixed and covered by tests:

- IARC `2B` is no longer treated as an ordinary numeric value.
- `0-40 mg/kg` is treated as one range/dose evidence item.
- Phone numbers and media contact blocks no longer generate numeric refutations.
- Page navigation numbers such as `IARC@60`, volume `134`, and dates no longer refute dose claims.
- Protein count claims no longer compare against molecular weights like `7 kDa` or percentages like `42%`.
- IARC classification claims now use classification stance rules, so `1类` vs `2B` can be refuted from body text.

## Validation Commands

Backend targeted verification subset:

```powershell
backend\.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest backend\tests\test_verification_modules.py backend\tests\test_verification_pipeline.py backend\tests\test_online_verifier_brave.py backend\tests\test_note_task_service.py backend\tests\test_verification_task_api.py
```

Latest result:

```text
79 passed
```

Frontend:

```powershell
cd reel-mind-frontend
node_modules\.bin\eslint.cmd src\pages\HomePage\components\VerificationReportView.tsx src\pages\HomePage\components\MarkdownViewer.tsx src\pages\HomePage\components\NoteForm.tsx src\hooks\useTaskPolling.ts
```

Latest result: passed for touched rerun/progress files.

Full frontend build:

```powershell
cd reel-mind-frontend
npm run build
```

Latest result: passed in about 2m48s. Existing warnings remain for `lottie-web` eval usage and large chunks.

Extension:

```powershell
cd reel-mind-extension
npm run typecheck
npm run build
```

Latest result: passed for popup-only published extension. Full `npm run lint` still fails on existing draft background/options/sidepanel/content files; targeted lint/build for touched popup logic passed earlier.

Important: standalone `tsc --noEmit` previously reported many existing project errors unrelated to the latest verification report/service edits.

Subagent smoke test:

```powershell
opencode run -m opencode-go/glm-5.2 --agent build "Reply exactly: OK"
```

Latest result: returned exactly `OK`, so local OpenCode subagents can be created/called on this host.

Subagents were not useful for speed in the latest frontend pass. Do not use them by default; use local inspection/tests first unless the user explicitly asks again.

## Current Dirty Worktree Notes

Before continuing, run:

```powershell
git status --short
```

Do not revert unrelated user changes.

Known untracked or generated paths from this work:

- `.tmp/`
- `.vs/`
- new backend verification modules
- new backend verification tests
- `reel-mind-frontend/src/pages/HomePage/components/VerificationReportView.tsx`
- `reel-mind-frontend/src/pages/HomePage/components/WorkspacePanels.tsx`

## Next Priorities

1. Retrieval quality: keep improving query expansion and add more real-world GEO/language disagreement fixtures beyond the current synthetic fixture.
2. Anti-manipulation: expand prompt injection, SEO farm, republished press release, listicle, fake authority, and data void fixtures beyond the current unit coverage.
3. Frontend health: investigate the existing standalone `tsc --noEmit` errors separately from verification feature work.
4. Extension: decide whether to activate/fix sidepanel/content scripts or keep popup-only MVP; if activating, pivot sidepanel to progress/evidence and content script to selected-text/page-URL verification.
5. Product cleanup: make verification report the only first-class workspace; keep Markdown/mind map/cards/Q&A as secondary artifacts.
6. Documentation/env cleanup: root README and env examples were updated in this handoff pass; next agent should review `README-usage.md`, `OPEN_ME_FIRST.md`, `DEPLOYMENT.md`, `task/`, and older readme handoff docs for stale note-first/Cookie-first wording.

## Hard Constraints For Next Agent

- Do not optimize for “minimum viable”. Verification quality is the only P0.
- Do not allow snippets, forums, SEO pages, social posts, or listicles to produce `supported` alone.
- Degraded mode without authoritative search/source evidence must not output `supported`.
- LLM may structure queries or explanations, but final verdict must remain rule-engine adjudication over fetched evidence.
- Never print or commit API keys.
