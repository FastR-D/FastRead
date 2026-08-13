import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


def _load_env_files() -> None:
    """Load both local and repo-level env files without overriding real env vars."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(BACKEND_ROOT / ".env", override=False)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _resolve_backend_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return BACKEND_ROOT / path


def _sqlite_url_from_path(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _normalize_database_url(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        return database_url
    path = AppSettings._sqlite_path_from_url(database_url)
    if not path.is_absolute():
        path = _resolve_backend_path(path)
    return _sqlite_url_from_path(path)


class AppSettings:
    def __init__(self) -> None:
        _load_env_files()

        self.backend_root = BACKEND_ROOT
        self.project_root = PROJECT_ROOT

        self.backend_host = os.getenv("BACKEND_HOST", "0.0.0.0")
        self.backend_port = _get_int("BACKEND_PORT", 8483)
        self.api_base_url = os.getenv("API_BASE_URL", "http://localhost")
        self.backend_base_url = f"{self.api_base_url.rstrip('/')}:{self.backend_port}"
        self.sqlalchemy_echo = os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true"
        self.db_pool_size = _get_int("DB_POOL_SIZE", 10)
        self.db_max_overflow = _get_int("DB_MAX_OVERFLOW", 20)
        self.database_url = _normalize_database_url(
            os.getenv("DATABASE_URL") or _sqlite_url_from_path(_resolve_backend_path("fastread.db"))
        )
        self.sqlite_db_path = self._sqlite_path_from_url(self.database_url)

        self.static_path = os.getenv("STATIC", "/static")
        self.static_dir = _resolve_backend_path(os.getenv("STATIC_DIR", "static"))
        self.uploads_path = os.getenv("UPLOADS_PATH", "/uploads")
        self.uploads_dir = _resolve_backend_path(os.getenv("UPLOAD_DIR", "uploads"))
        self.note_output_dir = _resolve_backend_path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))
        self.data_dir = _resolve_backend_path(os.getenv("DATA_DIR", "data"))
        self.export_output_dir = _resolve_backend_path(os.getenv("EXPORT_OUTPUT_DIR", "data/note_output"))
        self.vector_db_dir = _resolve_backend_path(os.getenv("VECTOR_DB_DIR", "vector_db"))

        self.max_upload_bytes = _get_int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
        self.max_image_proxy_bytes = _get_int("MAX_IMAGE_PROXY_BYTES", 15 * 1024 * 1024)
        self.image_proxy_allowed_hosts = {
            host.strip().lower()
            for host in os.getenv("IMAGE_PROXY_ALLOWED_HOSTS", "").split(",")
            if host.strip()
        }

    def ensure_runtime_dirs(self) -> None:
        for path in (
            self.static_dir,
            self.uploads_dir,
            self.note_output_dir,
            self.data_dir,
            self.export_output_dir,
            self.vector_db_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sqlite_path_from_url(database_url: str) -> Path:
        if not database_url.startswith("sqlite:///"):
            return BACKEND_ROOT / "fastread.db"

        raw_path = database_url.removeprefix("sqlite:///")
        if raw_path.startswith("/") and not raw_path.startswith("//"):
            raw_path = raw_path[1:]
        if os.name != "nt" and database_url.startswith("sqlite:////"):
            raw_path = "/" + raw_path
        return Path(raw_path)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
