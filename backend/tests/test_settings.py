import importlib


def test_settings_resolves_paper_runtime_paths_to_backend_root(monkeypatch):
    settings_module = importlib.import_module("app.core.settings")
    monkeypatch.delenv("PAPER_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.delenv("FASTREAD_DATA_ROOT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.database_url == f"sqlite:///{(settings.backend_root / 'fastread.db').as_posix()}"
    assert settings.paper_output_dir == settings.backend_root / "paper_results"
    assert settings.uploads_dir == settings.backend_root / "uploads"
    assert settings.data_dir == settings.backend_root / "data"
    assert settings.vector_db_dir == settings.backend_root / "vector_db"
    assert settings.embedding_model_cache_dir == settings.backend_root / "models" / "embedding"
    assert settings.integration_data_dir == settings.backend_root / "data" / "integrations"


def test_settings_normalizes_relative_sqlite_url(monkeypatch):
    settings_module = importlib.import_module("app.core.settings")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///custom.db")
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.database_url == f"sqlite:///{(settings.backend_root / 'custom.db').as_posix()}"
    assert settings.sqlite_db_path == settings.backend_root / "custom.db"


def test_settings_uses_explicit_product_data_root(monkeypatch, tmp_path):
    settings_module = importlib.import_module("app.core.settings")
    monkeypatch.setenv("FASTREAD_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PAPER_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.data_root == tmp_path
    assert settings.database_url == f"sqlite:///{(tmp_path / 'fastread.db').as_posix()}"
    assert settings.paper_output_dir == tmp_path / "paper_results"
    assert settings.uploads_dir == tmp_path / "uploads"
    assert settings.integration_data_dir == tmp_path / "data" / "integrations"
    assert settings.embedding_model_cache_dir == tmp_path / "models" / "embedding"


def test_runtime_directory_creation_is_paper_only(monkeypatch, tmp_path):
    settings_module = importlib.import_module("app.core.settings")
    monkeypatch.setenv("FASTREAD_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings_module.get_settings.cache_clear()
    settings = settings_module.get_settings()

    settings.ensure_runtime_dirs()

    assert settings.paper_output_dir.is_dir()
    assert settings.uploads_dir.is_dir()
    assert settings.embedding_model_cache_dir.is_dir()
