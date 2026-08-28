from app.services.reading_report_service import _response_format_is_unsupported


class ProviderError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def test_response_format_fallback_is_only_for_compatibility_errors():
    assert _response_format_is_unsupported(
        ProviderError("response_format json_object is unsupported", 400)
    )
    assert not _response_format_is_unsupported(ProviderError("rate limit", 429))
    assert not _response_format_is_unsupported(TimeoutError("request timed out"))
