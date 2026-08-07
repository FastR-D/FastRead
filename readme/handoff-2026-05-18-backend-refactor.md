# FastRead Backend Verification Handoff

Updated: 2026-06-20

This file replaces the older backend-refactor handoff. Historical note-generation refactors still exist in git history, but the current backend priority is online verification.

## Backend Goal

FastRead backend must become a high-quality verification engine:

```text
claim extraction -> multi-query retrieval -> source fetch -> source intelligence -> evidence extraction -> rule adjudication -> audit report
```

Legacy note generation stays compatible but is no longer the product center.

## Main Files

Verification compatibility facade:

- `backend/app/services/online_verifier.py`

Verification package:

- `backend/app/services/verification/schemas.py`
- `backend/app/services/verification/claim_pipeline.py`
- `backend/app/services/verification/query_builder.py`
- `backend/app/services/verification/search_providers.py`
- `backend/app/services/verification/search_orchestrator.py`
- `backend/app/services/verification/fetching.py`
- `backend/app/services/verification/source_intel.py`
- `backend/app/services/verification/evidence.py`
- `backend/app/services/verification/numeric_evidence.py`
- `backend/app/services/verification/adjudication.py`
- `backend/app/services/verification/verdict.py`
- `backend/app/services/verification/ai_judge.py`

Task API and lifecycle:

- `backend/app/routers/note.py`
- `backend/app/services/note_task_service.py`
- `backend/app/enmus/task_status_enums.py`

Tests:

- `backend/tests/test_verification_modules.py`
- `backend/tests/test_verification_pipeline.py`
- `backend/tests/test_online_verifier_brave.py`
- `backend/tests/test_note_task_service.py`
- `backend/tests/test_verification_task_api.py`

## API Contract

Primary verification endpoints:

```http
POST /api/verification_tasks
GET  /api/verification_tasks/{task_id}
POST /api/verification_tasks/{task_id}/rerun
GET  /api/verification_tasks
```

Default request behavior:

```json
{
  "goal": "verify",
  "verification_depth": "deep",
  "source_policy": "authoritative",
  "max_claims": 50
}
```

Supported input modes:

- text
- URL
- existing task id

The old `/verify_task_online` path still exists for compatibility.

## Verification Result Shape

The main result is stored under:

```text
result.verification_result
```

Top-level structure:

```text
input
overall
claim_counts
claims
sources
evidence
risk_flags
audit
```

Each source should include:

```text
url
canonical_url
domain
title
publisher
author
published_at
retrieved_at
source_type
trust_tier
trust_reasons
independence_group
content_hash
fetch_status
risk_flags
```

Each evidence item should include:

```text
source_url
passage
stance
claim_element
exact_value
unit
page_offsets
confidence
extraction_method
```

## Current Adjudication Rules

`adjudication.py` decides the machine verdict.

Current verdicts:

- `supported`
- `refuted`
- `mixed`
- `insufficient`
- `data_void`
- `source_risk`

Important invariant:

```text
search snippets can recall sources, but cannot support a claim.
```

Current `supported` requirements:

- at least two independent high-trust body evidence sources; or
- one high-trust body evidence source plus other independent relevant support;
- no same-tier high-trust refutation.

Current `data_void` triggers:

- low raw result count
- no independent authoritative source
- weak sources dominate
- biased listicles dominate
- no body evidence

## Source Intelligence

`source_intel.py` currently assigns source tiers with domain heuristics and fetch status.

Current tier examples:

- A: `who.int`, `iarc.who.int`, `.gov`, statistics, court, primary research, official/regulator domains
- B: `.edu`, major publishers, recognized databases, mainstream reporting
- C: encyclopedia, blogs, republished sources
- D: social, portal, marketing, SEO, listicle, forum, weak identity
- blocked: local/blocked domains

Independence grouping uses domain, canonical, publisher, and content hash.

Next needed improvement:

- source registry file or table
- redirect-chain and canonical anomaly scoring
- publisher/author/date extraction quality upgrade
- press-release repost clustering
- fake official domain detection

## Evidence Extraction

`evidence.py` extracts body passages and assigns stance:

- `support`
- `refute`
- `context`

Extraction methods now include:

- `body_overlap_rules`
- `body_numeric_rules`
- `body_classification_rules`

Recent fixes:

- IARC `Group 2B` is handled as classification evidence, not ordinary number evidence.
- False `IARC 1类` claim is refuted by body text saying `Group 2B`.
- `0-40 mg/kg` is handled as range dose evidence.
- contact phone numbers and navigation counts are not numeric evidence.
- protein-count claims do not compare with `kDa`, percentages, dates, or unrelated numeric page chrome.

## AI Usage

DeepSeek was connected locally:

```text
provider_id = deepseek
model_name  = deepseek-v4-flash
base_url    = https://api.deepseek.com
```

Do not write API keys into files or logs.

Current role of AI:

- optional structured query assistance
- optional context profile assistance

Current non-negotiable:

```text
AI does not decide the final verdict. Final status comes from rule adjudication over fetched body evidence.
```

If model/provider is absent, verification should still run without falling back to a broken default model. This was fixed.

## Real Smoke Tasks

Useful completed task ids:

```text
993b3ebb-00f4-4e36-aabd-b353f8028b79
```

Correct aspartame claim, result `supported`, confidence `95`.

```text
aed981a3-8df4-4cde-ad2c-f9b683f2729f
```

False IARC 1 classification, result `refuted`.

Earlier failed task before optional-AI fix:

```text
246a3693-f91c-40f2-b36d-019db4696c7a
```

Do not delete task artifacts unless explicitly asked.

## Verification Commands

Targeted verification subset:

```powershell
backend\.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest backend\tests\test_verification_modules.py backend\tests\test_verification_pipeline.py backend\tests\test_online_verifier_brave.py backend\tests\test_note_task_service.py backend\tests\test_verification_task_api.py
```

Latest:

```text
37 passed
```

Full backend tests may include unrelated older areas. Run targeted subset first when working on verification.

## Local Server Commands

Backend:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8483
```

From repo root, the known working server command is:

```powershell
$root = (Resolve-Path .).Path
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
$backend = Join-Path $root 'backend'
Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','main:app','--host','127.0.0.1','--port','8483') -WorkingDirectory $backend -WindowStyle Hidden
```

Frontend:

```powershell
cd fastread-frontend
npm run dev
```

Build:

```powershell
cd fastread-frontend
npm run build
```

## Next Backend Work

Highest priority:

1. Persist per-claim intermediate results.
2. Add retry only for failed fetch/search stages.
3. Add SERP, snapshot, and evidence caches.
4. Add audit lines for cache hit/miss, fetch status, canonical URL, content hash, and source independence group.
5. Expand source-risk fixtures:
   - fake official domain
   - canonical mismatch
   - redirect chain surprise
   - no author/no date
   - copied press release
   - prompt injection in body
   - SEO listicles outranking official sources
6. Add GEO/language retrieval comparison and output `geo_disagreement`.
7. Add tests for degraded mode:
   - no Brave key
   - all fetches failed
   - only weak sources
   - snippets support but body missing

## Do Not Do

- Do not re-center the product on note generation.
- Do not allow snippets to create `supported`.
- Do not let LLM free-form judgement override evidence matrix.
- Do not globally revert dirty files.
- Do not commit secrets.
