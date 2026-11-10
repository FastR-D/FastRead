# FastNews → FastRead intake v1

Owner: FastRead. Receiver: `POST /api/integrations/fastnews/intake` with a
FastRead session cookie and matching `X-CSRF-Token`. Anonymous=401, invalid
CSRF=403, invalid title/oversized normalized text=422, success=200. Receipt is
metadata persistence, not a PDF download or automatic job submission.

Schemas cover canonical intake and receipt. `cases.json` records existing wire
semantics, including URL sanitation (invalid URLs become empty, not 422).
Same workspace + external_id deduplicates, else URL hash, else title hash.
Duplicates update metadata and return created=false. Different workspaces are
isolated. A subsequent PDF attachment retains the paper ID and active_version;
another metadata intake must not clear that version. There is no intake
Idempotency-Key contract or cross-workspace shared identity.

## Browser handoff boundary for the UI owner

News `serve.py:build_fastread_handoff` currently returns
`{readBase}/?sso=<ticket>#fastnews=<percent-encoded JSON>`; without a ticket,
`{readBase}/#fastnews=...`. readBase may include `/read`. Decode the fragment
once, normalize `handoff.id` to `intake.external_id`, and send only canonical
intake fields. DOI is present in News' carrier but is not an intake API field.
Do not claim DOI was stored. The fixture deliberately keeps both forms visible.

Keep a pending handoff across ticket consumption and local-login UI, clear the
ticket URL promptly, and clear the pending payload only after an authenticated,
CSRF-authorized successful receipt. Failed 401/403/422/network requests must not
display success. Root/subpath carrier decoding and login restoration need a real
browser scenario in the UI change. The SDK/CI work does not edit frontend source.

Run: `python -m pytest --noconftest backend/tests/test_research_intake.py`.
The HTTP contract test reads this fixture directly; News is the confirmed sending
product. A second independent sending product has not been identified. No shared
generated client or FastCommon package is introduced.
