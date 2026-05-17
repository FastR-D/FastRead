import json
import importlib

from app.transcriber.transcriber_provider import MLX_WHISPER_AVAILABLE


def _json_response_data(response):
    return json.loads(response.body.decode("utf-8"))["data"]


def _load_config_router(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_router = importlib.import_module("app.routers.config")
    return importlib.reload(config_router)


def test_get_transcriber_config_includes_mlx_availability_flag(monkeypatch, tmp_path):
    config_router = _load_config_router(monkeypatch, tmp_path)
    data = _json_response_data(config_router.get_transcriber_config())

    assert data["transcriber_type"]
    assert data["whisper_model_size"]
    assert isinstance(data["available_types"], list)
    assert isinstance(data["whisper_model_sizes"], list)
    assert data["mlx_whisper_available"] is MLX_WHISPER_AVAILABLE


def test_get_transcriber_models_status_does_not_import_mlx_when_unavailable(monkeypatch, tmp_path):
    config_router = _load_config_router(monkeypatch, tmp_path)
    data = _json_response_data(config_router.get_transcriber_models_status())

    assert isinstance(data["whisper"], list)
    assert isinstance(data["mlx_whisper"], list)
    assert data["mlx_available"] is MLX_WHISPER_AVAILABLE
