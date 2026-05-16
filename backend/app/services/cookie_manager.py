import json
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timezone


class CookieConfigManager:
    def __init__(self, filepath: str = "config/downloader.json"):
        self.path = Path(filepath)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> Dict[str, Dict[str, str]]:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, data: Dict[str, Dict[str, str]]):
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self, platform: str) -> Optional[str]:
        data = self._read()
        value = data.get(platform)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("cookie")
        return None

    def set(self, platform: str, cookie: str):
        data = self._read()
        data[platform] = {
            "cookie": cookie,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write(data)

    def delete(self, platform: str):
        data = self._read()
        if platform in data:
            del data[platform]
            self._write(data)

    def list_all(self) -> Dict[str, str]:
        data = self._read()
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = value
            elif isinstance(value, dict):
                result[key] = value.get("cookie", "")
        return result

    def exists(self, platform: str) -> bool:
        return self.get(platform) is not None

    def status(self, platform: str) -> dict:
        data = self._read()
        value = data.get(platform)
        updated_at = None
        if isinstance(value, str):
            cookie = value
        elif isinstance(value, dict):
            cookie = value.get("cookie") or ""
            updated_at = value.get("updated_at")
        else:
            cookie = ""

        parts = [part.strip() for part in cookie.split(";") if part.strip()]
        names = {part.split("=", 1)[0].strip() for part in parts if "=" in part}
        required = {"ttwid", "msToken"}
        missing = sorted(required - names)
        configured = bool(cookie.strip())

        return {
            "platform": platform,
            "configured": configured,
            "cookie_count": len(parts),
            "length": len(cookie),
            "updated_at": updated_at,
            "valid_looking": configured and len(parts) >= 2 and not missing,
            "missing_keys": missing,
        }
