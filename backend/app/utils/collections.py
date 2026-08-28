from __future__ import annotations

import re
import unicodedata


DEFAULT_COLLECTION_FOLDER = "默认收藏夹"
COLLECTION_FOLDER_MAX_CHARS = 80


def normalize_collection_folder(value: str | None) -> str:
    normalized = unicodedata.normalize("NFC", str(value or "")).strip()
    return re.sub(r"\s+", " ", normalized)


def require_collection_folder(value: str | None) -> str:
    normalized = normalize_collection_folder(value)
    if not normalized:
        raise ValueError("收藏夹名称不能为空")
    if len(normalized) > COLLECTION_FOLDER_MAX_CHARS:
        raise ValueError(f"收藏夹名称不能超过 {COLLECTION_FOLDER_MAX_CHARS} 个字符")
    return normalized
