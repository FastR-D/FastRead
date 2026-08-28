import os

from app.core.settings import get_settings

def get_data_dir():
    data_path = str(get_settings().data_dir)
    os.makedirs(data_path, exist_ok=True)
    return data_path


def get_model_dir(subdir: str = "whisper") -> str:
    base_dir = str(get_settings().data_root / "models")
    path = os.path.join(base_dir, subdir)
    os.makedirs(path, exist_ok=True)
    return path


def get_app_dir(subdir: str = "") -> str:
    """Return a writable runtime directory rooted in FASTREAD_DATA_ROOT."""
    base_dir = str(get_settings().data_dir)
    full_path = os.path.join(base_dir, subdir)
    os.makedirs(full_path, exist_ok=True)
    return full_path
