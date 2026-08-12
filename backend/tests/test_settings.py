import importlib
import os


def test_settings_resolves_runtime_paths_to_backend_root(monkeypatch):
    settings_module = importlib.import_module("app.core.settings")
    monkeypatch.delenv("NOTE_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.note_output_dir == settings.backend_root / "note_results"
    assert settings.uploads_dir == settings.backend_root / "uploads"
    assert settings.static_dir == settings.backend_root / "static"
    assert settings.data_dir == settings.backend_root / "data"
    assert settings.export_output_dir == settings.backend_root / "data" / "note_output"
    assert settings.vector_db_dir == settings.backend_root / "vector_db"


def test_settings_normalizes_relative_sqlite_url(monkeypatch):
    settings_module = importlib.import_module("app.core.settings")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///custom.db")
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.database_url == f"sqlite:///{(settings.backend_root / 'custom.db').as_posix()}"
    assert settings.sqlite_db_path == settings.backend_root / "custom.db"
