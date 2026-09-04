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


def _normalize_database_url(database_url: str, base_dir: Path = BACKEND_ROOT) -> str:
    if not database_url.startswith("sqlite:///"):
        return database_url
    path = AppSettings._sqlite_path_from_url(database_url)
    if not path.is_absolute():
        path = base_dir / path
    return _sqlite_url_from_path(path)


class AppSettings:
    def __init__(self) -> None:
        _load_env_files()

        self.backend_root = BACKEND_ROOT
        self.project_root = PROJECT_ROOT

        raw_data_root = os.getenv("FASTREAD_DATA_ROOT", "").strip()
        self.data_root = _resolve_backend_path(raw_data_root) if raw_data_root else BACKEND_ROOT

        def runtime_path(value: str | Path) -> Path:
            path = Path(value)
            return path if path.is_absolute() else self.data_root / path

        # FastRead is a local-first desktop application. Exposing the API on every
        # network interface must be an explicit deployment choice, never a default.
        self.backend_host = os.getenv("BACKEND_HOST", "127.0.0.1")
        self.backend_port = _get_int("BACKEND_PORT", 8483)
        self.api_base_url = os.getenv("API_BASE_URL", "http://localhost")
        self.backend_base_url = f"{self.api_base_url.rstrip('/')}:{self.backend_port}"
        self.sqlalchemy_echo = os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true"
        self.db_pool_size = _get_int("DB_POOL_SIZE", 10)
        self.db_max_overflow = _get_int("DB_MAX_OVERFLOW", 20)
        default_database = self.data_root / "fastread.db"
        self.database_url = _normalize_database_url(
            os.getenv("DATABASE_URL") or _sqlite_url_from_path(default_database),
            self.data_root,
        )
        self.sqlite_db_path = self._sqlite_path_from_url(self.database_url)

        self.uploads_path = os.getenv("UPLOADS_PATH", "/uploads")
        self.uploads_dir = runtime_path(os.getenv("UPLOAD_DIR", "uploads"))
        self.paper_output_dir = runtime_path(os.getenv("PAPER_OUTPUT_DIR", "paper_results"))
        self.data_dir = runtime_path(os.getenv("DATA_DIR", "data"))
        self.vector_db_dir = runtime_path(os.getenv("VECTOR_DB_DIR", "vector_db"))
        self.embedding_model_cache_dir = runtime_path(
            os.getenv("CHAT_EMBEDDING_CACHE_DIR", "models/embedding")
        )

        self.max_upload_bytes = _get_int("MAX_UPLOAD_BYTES", 64 * 1024 * 1024)
        self.fastnews_enabled = os.getenv("FASTNEWS_ENABLED", "true").lower() == "true"
        self.fastnews_repo = "FastR-D/FastNews"
        self.fastnews_cache_path = runtime_path(
            os.getenv("FASTNEWS_CACHE_PATH", "data/integrations/fastnews_catalog.json")
        )
        self.fastinsight_max_bytes = _get_int("FASTINSIGHT_MAX_BYTES", 1024 * 1024)
        self.fastwrite_enabled = os.getenv("FASTWRITE_ENABLED", "true").lower() == "true"
        self.fastwrite_base_url = os.getenv("FASTWRITE_BASE_URL", "http://127.0.0.1:3003").rstrip("/")
        self.fastwrite_allowed_origins = {
            origin.strip().rstrip("/")
            for origin in os.getenv("FASTWRITE_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        }
        self.integration_timeout_seconds = _get_int("INTEGRATION_TIMEOUT_SECONDS", 15)
        self.integration_data_dir = runtime_path(
            os.getenv("INTEGRATION_DATA_DIR", "data/integrations")
        )

    def ensure_runtime_dirs(self) -> None:
        for path in (
            self.uploads_dir,
            self.paper_output_dir,
            self.data_dir,
            self.vector_db_dir,
            self.embedding_model_cache_dir,
            self.integration_data_dir,
            self.fastnews_cache_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sqlite_path_from_url(database_url: str) -> Path:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("DATABASE_URL must be an explicit SQLAlchemy URL")

        raw_path = database_url.removeprefix("sqlite:///")
        if raw_path.startswith("/") and not raw_path.startswith("//"):
            raw_path = raw_path[1:]
        if os.name != "nt" and database_url.startswith("sqlite:////"):
            raw_path = "/" + raw_path
        return Path(raw_path)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
