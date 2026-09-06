# PDF metadata extraction

PDF imports retain first-page line text, coordinates and font sizes. Title
candidates come from geometry, rather than first-N-line or author-name templates.
An optional workspace model (including a configured Qwen 27B) extracts title,
authors and publication year with source line IDs. Returned text must occur in
the selected source lines. This checks location, not semantic correctness.

Exact arXiv IDs (including requested versions) or explicit DOIs resolve public
registry metadata. A registry title must also agree with a document title
candidate. Title searches cannot establish identity. Conflicting identifiers,
title disagreement and unavailable registries remain explicit in
`paper_document.metadata_resolution`. Unknown fields stay empty; PDF creation
dates and arXiv revision dates do not fill missing publication years.

In the Web UI, **导入时识别标题与作者** selects a configured model or geometry and
registry lookup alone. The first configured Qwen model containing `27b` is the
initial model preference. No provider is provisioned automatically. Only up to
250 first-page lines / 32,000 serialized characters are sent to the provider.
Selecting a model counts against the workspace model-task quota.

Both `POST /api/imports/url` JSON and `POST /api/imports/pdf` multipart accept
optional `provider_id` and `model` fields. Provider ownership and model availability
are checked before enqueueing. The worker lazily creates the existing model client
after PDF parsing, preserving the dispatch marker and ambiguous-call retry guard.
Model rejection or failure falls back to geometry/registry extraction and is
visible in `model_status`; it is not reported as successful model extraction.

Reimporting the same PDF can publish an immutable metadata revision when title,
authors, year, DOI or resolution status improve. A failed verification of identical
page content does not overwrite an already registry-verified active version.
Existing libraries are not automatically rewritten; reimport affected PDFs.

This path requires usable PDF text. Scanned PDFs and complex mathematical layout
still require a separate OCR/vision capability. A source-located model field is
not independent bibliographic verification, and a matching identifier/title is
not proof that every byte of a PDF matches the registry's document.

Tests cover license preambles, multiline titles, fabricated fields and line IDs,
revision-year rejection, exact registry versions, identifier/title conflicts,
model failure, quota/ownership, retries and metadata revision persistence.
Real provider inference must be evaluated separately from mocked model tests.
