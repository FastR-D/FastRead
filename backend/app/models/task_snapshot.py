from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TaskSnapshot:
    """Stable backend task DTO used by task list and task status endpoints."""

    id: str
    status: str
    message: str = ""
    error: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    markdown: Any = ""
    insights: dict[str, Any] | None = None
    audio_meta: dict[str, Any] | None = None
    transcript: dict[str, Any] | None = None
    created_at: float = 0
    updated_at: float = 0
    video_url: str = ""
    collection: dict[str, Any] | None = None
    title: str = ""
    cover_url: str = ""

    def to_status_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.id,
            "status": self.status,
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    def to_list_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "markdown": self.markdown,
            "insights": self.insights,
            "audioMeta": self.audio_meta or {},
            "transcript": self.transcript,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "videoUrl": self.video_url,
            "collection": self.collection,
            "title": self.title,
            "coverUrl": self.cover_url,
        }
