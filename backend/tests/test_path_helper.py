from types import SimpleNamespace

from app.utils import path_helper


def test_runtime_paths_follow_configured_data_root(monkeypatch, tmp_path):
    settings = SimpleNamespace(
        data_root=tmp_path,
        data_dir=tmp_path / "data",
    )
    monkeypatch.setattr(path_helper, "get_settings", lambda: settings)

    assert path_helper.get_data_dir() == str(tmp_path / "data")
    assert path_helper.get_model_dir("whisper") == str(tmp_path / "models" / "whisper")
    assert path_helper.get_app_dir("output_frames") == str(tmp_path / "data" / "output_frames")
