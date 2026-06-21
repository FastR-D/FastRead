# ReelMind Verification-First Refactor Plan

Updated: 2026-06-20

This plan supersedes the old 2026-06-04 general refactor plan. The product has changed: online verification is the first-class capability. Notes, mind maps, cards, Q&A, and old video workflows are secondary artifacts.

## North Star

ReelMind should answer:

```text
这句话到底有没有可靠联网证据支持？
```

The product must show:

- atomic claims
- exact evidence passages
- source tier and independence
- support/refute/context evidence
- risk flags
- audit trail
- final machine verdict

It must not hide behind search summaries or model confidence.

## P0 Rules

1. Verification quality beats speed, cost, and old feature completeness.
2. Search snippets are recall only.
3. Weak sources cannot independently support a claim.
4. Degraded mode cannot output `supported`.
5. LLMs may help query construction and explanation, but final verdict must be rule-driven.
6. Every `supported` result must be auditable back to fetched body evidence.
7. Source truth matters as much as passage relevance.

## Target Pipeline

```text
Input
  -> claim_pipeline
      atomic claims
      entities / time / place / numeric values / comparison objects / domain type
  -> retrieval
      multi-query
      authoritative search first
      language/GEO variants
      source diversity
  -> fetching
      HTML/PDF body extraction
      canonical URL
      author/publisher/date
      content hash
      snapshot cache
  -> source_intel
      trust tier
      independence group
      risk flags
      fake authority / SEO / listicle / repost detection
  -> evidence
      passage extraction
      numeric stance
      classification stance
      support/refute/context
  -> adjudication
      evidence matrix
      verdict
      confidence
      audit
  -> report
      UI-readable and machine-readable verification result
```

## Current Completed Work

### Backend Core

Implemented:

- schemas
- claim sorting/risk prioritization
- body fetch snapshots
- source tiering and independence grouping
- evidence extraction
- numeric evidence rules
- IARC classification evidence rules
- verdict adjudication
- compatibility through `online_verifier.py`

Primary package:

```text
backend/app/services/verification/
```

### Task API

Implemented:

```http
POST /api/verification_tasks
GET  /api/verification_tasks/{task_id}
POST /api/verification_tasks/{task_id}/rerun
GET  /api/verification_tasks
```

### Frontend

Implemented:

- verification-first submit flow
- verification report view
- source tier display
- evidence display
- risk flag display
- default workspace mode changed to verification

### Model Integration

DeepSeek OpenAI-compatible provider is locally configured for benchmark use:

```text
base_url: https://api.deepseek.com
model: deepseek-v4-flash
```

No keys should be written to repository files.

### Tests

Verification subset:

```text
37 passed
```

Frontend build:

```text
passed, with existing lottie eval and large chunk warnings
```

## Real Benchmark Outcomes

Correct WHO/IARC/JECFA aspartame claim:

```text
supported
confidence 95
3 independent high-trust support groups
0 high-trust refute groups
```

False IARC Group 1 claim:

```text
refuted
```

Weak marketing/listicle claim:

```text
data_void
```

Scientific numeric claim without body fetch:

```text
not supported
```

This is intended. No body evidence means no support.

## Remaining Gaps

### Phase 1: Backend Quality Completion

Implemented:

- per-claim result persistence
- retry failed web stages only
- SERP cache
- page snapshot cache
- evidence cache
- cache audit
- PDF text page span mapping for evidence offsets
- HTML source identity extraction from meta tags, schema.org JSON-LD, schema.org `@graph` references, and `time[datetime]`

Still needed:

- broader site-specific PDF layout/page offset regression fixtures
- broader publisher/author/published date extraction across real-world official, journal, regulator, and news templates

Priority:

```text
durability and auditability before UX polish
```

### Phase 2: Source Truth and Anti-Manipulation

Implemented:

- source registry
- known authoritative domain registry
- blocked/risky domain registry
- fake official domain detection
- redirect-chain anomaly detection
- canonical mismatch detection
- no author/no date scoring
- copied press-release clustering
- SEO farm detection
- prompt-injection stress fixtures
- biased listicle clustering across domains
- GEO/language disagreement detection

Current risk flags include:

- `geo_disagreement`
- `canonical_anomaly`
- `redirect_anomaly`
- `fake_authority`
- `press_release_repost`
- `missing_source_identity`
- `content_farm`

Still needed:

- more real-world GEO/language fixtures beyond the current synthetic coverage
- broader fake authority and canonical/redirect regression fixtures
- stronger copied press-release clustering across unrelated domains
- richer no author/no date source-identity scoring

### Phase 3: Taskization

Current task API is first-class and claim-level artifacts make verification resumable for the implemented stages.

Implemented:

- one artifact per claim
- one artifact per source snapshot
- rerun only retrieval/fetch/evidence for failed claims
- job progress per phase:
  - parsing input
  - extracting claims
  - searching
  - fetching
  - extracting evidence
  - adjudicating
  - writing report

Still needed:

- stable audit IDs across all source/evidence artifacts
- richer progress telemetry for every retry/cache branch
- robust partial task repair after interrupted processes

### Phase 4: Frontend and Extension Product Pivot

Web frontend has pivoted to first-class verification reports.

Still needed:

- verification report as the only default workspace
- old Markdown/mind map/cards/Q&A as secondary tabs
- verification history filters:
  - high risk
  - insufficient
  - refuted
  - data void
  - source domain
  - source tier
- URL verification flow with fetched original page shown in report

Extension popup has pivoted; full sidepanel/content integration remains draft-only.

Implemented:

- popup title/action: `用 ReelMind 联网核实此内容`
- popup shows:
  - current page URL
  - backend connection
  - start verification button
- Cookie Sync downgraded to Douyin input diagnostics

Still needed:

- popup model/search config state
- sidepanel defaults to progress/evidence
- content script sends selected text/page URL for verification
- decide whether to activate full extension surfaces or keep popup-only MVP

### Phase 5: Documentation and Old Feature Containment

Implemented:

- root `README.md` rewrite
- `.env.example` rewrite
- backend env docs:
  - search provider
  - Brave key
  - degraded mode behavior
  - DeepSeek/OpenAI-compatible provider examples without secrets

Still needed:

- old note tasks display `未联网核实`
- old note pages offer `发起联网核实`

## Test Plan

Current passing targeted subset:

```powershell
backend\.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest backend\tests\test_verification_modules.py backend\tests\test_verification_pipeline.py backend\tests\test_online_verifier_brave.py backend\tests\test_note_task_service.py backend\tests\test_verification_task_api.py
```

Need to add golden fixtures for:

- RAG poisoning: fake authority ranks first, result cannot be `supported`.
- Prompt injection: page body tells model to ignore instructions, verdict unaffected.
- Data void: weak sources dominate, output `data_void`.
- Biased listicles: mutually copied rankings count as low-independence.
- GEO disagreement: different regions/languages conflict, output `mixed` or `geo_disagreement`.
- Numeric verification:
  - unit conversion
  - ranges
  - approximations
  - year/date exclusion
  - contact number exclusion
  - page navigation number exclusion
  - statistical scope conflict
- Source authenticity:
  - fake domain
  - redirect chain
  - canonical anomaly
  - missing author/date
  - reposted press release
- Fetching:
  - HTML success
  - PDF success
  - blocked/failed sources
  - body empty

Frontend acceptance:

- task with only `verification_result` and no Markdown renders fully
- each claim shows verdict, confidence, support/refute/context evidence, source tier, retrieved time
- failed web fetch leaves extracted claims visible
- rerun can retry web verification only
- old Markdown/mind map/Q&A paths do not block verification flow

## Suggested Next Execution Order

1. Add per-claim artifact persistence and rerun semantics.
2. Add caches and audit cache-hit records.
3. Build source registry and source-risk scoring.
4. Add GEO/language retrieval variants.
5. Expand golden fixture tests until every current failure mode is locked.
6. Pivot extension popup/sidepanel.
7. Rewrite root docs and env examples.

## Verification-First Acceptance Standard

A change is acceptable only if:

- it improves evidence quality, auditability, source truth, or anti-manipulation; or
- it preserves compatibility while moving old features out of the critical path.

A change is not acceptable if:

- it makes `supported` easier to reach from weak evidence;
- it hides missing body fetches;
- it lets model judgement replace evidence;
- it optimizes speed by skipping source verification;
- it treats search result summaries as facts.
