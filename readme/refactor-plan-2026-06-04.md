# FastRead Paper-Reading-First Refactor Plan

Updated: 2026-08-05

This plan supersedes the older note-first and online-verification-first plans when they conflict.

## North Star

```text
PDF / paper URL
-> paginated source
-> guided key-question report
-> method and contributions
-> personal summary <= 300 characters
-> page-aware follow-up chat
```

## P0 Rules

1. A report requires parseable source text.
2. Page text is first-class frontend task state, not hidden backend metadata.
3. A paper landing URL follows its declared PDF when the PDF is safely fetchable.
4. Model citations are accepted only after exact page matching.
5. Method, contribution, evaluation, and limitations are stable report sections.
6. Personal summaries remain separate from generated reports.
7. Paper chat prioritizes page chunks and fails closed when source evidence is missing.
8. Online verification is an optional evidence-audit layer and does not compete with paper import in navigation.

## Implemented

- PDF page extraction and persisted `paper_document.pages`
- academic identity Gate and locked-source metadata
- guided reading report with exact citation resolution
- separate 300-character personal summary
- page-aware task and library chat chunks
- frontend page source viewer
- explicit six-step reading navigation
- paper library labels and progress
- optional evidence-audit entry
- source-registry fake-authority coverage, including official-title impersonation

## Verification

```powershell
backend\.venv\Scripts\python.exe -m pytest tests\test_academic_reading_workflow.py -q

cd fastread-frontend
corepack pnpm run build
```

Browser acceptance must use Playwright with Microsoft Edge.

## Still Needed

- OCR for scan-only PDFs with explicit provenance
- page-level highlight and report-to-source jump
- broader real-world academic metadata fixtures
- constrained conference search distinct from generic web evidence audit
- complete frontend end-to-end coverage
