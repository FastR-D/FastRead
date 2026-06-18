# Task 01: Backend Refactor Slice

## Findings

Best single slice to implement now: fix the transcriber instance cache key so ASR model/device changes create the correct transcriber instance.

Why this slice:

- It is high value and small. A user can change `WHISPER_MODEL_SIZE` or device, but the current global cache in `backend/app/transcriber/transcriber_provider.py` stores only one instance per transcriber type.
- `TranscriptService` already stores `model_size` and `device`, but primary initialization calls `get_transcriber(transcriber_type=self.transcriber_type)` without forwarding either value.
- The fallback path does pass `model_size` and `device`, so the inconsistency is localized and easy to test.
- This avoids the migration risk of the `Provider.id` / `Model.provider_id` schema mismatch, which is also unfinished but touches persisted SQLite data and API/service type signatures.

Why it is not already completed:

- `backend/app/transcriber/transcriber_provider.py` defines `_transcribers` as `{TranscriberType: instance}` rather than a cache keyed by `(type, model_size, device)`.
- `backend/app/services/transcript_service.py` imports `_transcribers` for support validation and then calls `get_transcriber()` without the selected model/device in `_init_transcriber()`.
- `backend/tests/test_transcript_service.py` covers cache hits, fallback, and metadata enrichment, but not "same type, different model/device yields different instance".

Secondary unfinished backend evidence:

- `Provider.id` is `String`, but `Model.provider_id` is still `Integer` and has no `ForeignKey`; `model_dao.py` joins `Model.provider_id == Provider.id`.
- DAO functions still call `db = next(get_db())` directly, so repository/session injection remains unfinished. That is larger than this transcriber slice.

## Recommended Patch

Patch candidate:

1. In `backend/app/transcriber/transcriber_provider.py`, replace the type-only singleton cache with keys that include relevant constructor inputs:
   - `fast-whisper`: `(TranscriberType.FAST_WHISPER, whisper_model_size, device)`
   - `mlx-whisper`: `(TranscriberType.MLX_WHISPER, whisper_model_size, None)`
   - `bcut`: `(TranscriberType.BCUT, None, None)`
   - `groq`: `(TranscriberType.GROQ, None, None)`
2. Keep a support map/set for valid transcriber types instead of relying on `_transcribers` membership from `TranscriptService`.
3. In `backend/app/services/transcript_service.py`, change `_init_transcriber()` to call:
   - `get_transcriber(transcriber_type=self.transcriber_type, model_size=self.model_size, device=self.device or "cpu")`
4. Add tests in `backend/tests/test_transcript_service.py` or a new focused provider test:
   - monkeypatch `WhisperTranscriber` with a dummy class recording `model_size` and `device`;
   - call `get_transcriber("fast-whisper", model_size="tiny", device="cpu")`;
   - call `get_transcriber("fast-whisper", model_size="base", device="cpu")`;
   - assert two different instances and the recorded model sizes differ;
   - call the same key twice and assert the instance is reused.

Exact files likely to change:

- `backend/app/transcriber/transcriber_provider.py`
- `backend/app/services/transcript_service.py`
- `backend/tests/test_transcript_service.py` or `backend/tests/test_transcriber_provider.py`

## Risks

- Existing tests or code may import `_transcribers` directly. Current search found only `TranscriptService` importing it.
- If a test suite expects one singleton per type, update it to expect one singleton per effective runtime config.
- The provider cache may retain multiple heavy whisper instances in long-running processes. That is correct for config fidelity but may increase memory usage after repeated model/device switches. A follow-up can add explicit cache clearing on config changes.

## Verification

Suggested verification:

```powershell
backend\.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest backend\tests\test_transcript_service.py
backend\.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest backend\tests
```

Commands run for this report:

- `rg -n "DAO|repository|Provider.id|provider_id|task_serial_executor|TranscriptService|transcriber" readme/refactor-plan-2026-06-04.md`
- `rg -n "get_transcriber|model_size|device|_transcribers|TranscriptService" backend/app backend/tests`
- Read-only inspection of the files listed below.

Tests were not run; this was a read-only worker investigation.

## Files Inspected

- `readme/refactor-plan-2026-06-04.md`
- `backend/app/transcriber/transcriber_provider.py`
- `backend/app/services/transcript_service.py`
- `backend/tests/test_transcript_service.py`
- `backend/app/db/models/providers.py`
- `backend/app/db/models/models.py`
- `backend/app/db/model_dao.py`
- `backend/app/db/provider_dao.py`
- `backend/app/services/model.py`
- `backend/app/services/provider.py`
- `backend/app/routers/model.py`
- `backend/app/services/task_serial_executor.py`
- `backend/tests/test_task_serial_executor.py`
