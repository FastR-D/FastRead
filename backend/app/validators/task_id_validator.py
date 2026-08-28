from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator


def validate_canonical_task_id(value: str) -> str:
    """Accept only the canonical, hyphenated, lower-case UUID representation."""
    if not isinstance(value, str):
        raise ValueError("task_id 必须是规范 UUID")
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("task_id 必须是规范 UUID") from exc
    if str(parsed) != value:
        raise ValueError("task_id 必须是规范 UUID")
    return value


CanonicalTaskId = Annotated[str, AfterValidator(validate_canonical_task_id)]
