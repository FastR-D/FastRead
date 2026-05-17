import importlib.util
import pathlib
import sys
import types
import unittest


def _install_pydantic_stub():
    pydantic_mod = types.ModuleType("pydantic")

    class _BaseModel:
        pass

    def _decorator(*_args, **_kwargs):
        def wrap(func):
            return func
        return wrap

    pydantic_mod.AnyUrl = str
    pydantic_mod.BaseModel = _BaseModel
    pydantic_mod.field_validator = _decorator
    pydantic_mod.model_validator = _decorator
    sys.modules.setdefault("pydantic", pydantic_mod)


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "validators" / "video_url_validator.py"
_install_pydantic_stub()
spec = importlib.util.spec_from_file_location("video_url_validator", MODULE_PATH)
if spec is None or spec.loader is None:
    raise ImportError("video_url_validator module spec not found")
video_url_validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_url_validator)
is_supported_video_url = video_url_validator.is_supported_video_url


class TestVideoUrlValidator(unittest.TestCase):
    def test_accepts_matching_platform_url(self):
        self.assertTrue(
            is_supported_video_url("https://www.bilibili.com/video/BV1xx411c7mD", "bilibili")
        )

    def test_accepts_douyin_search_url_with_chinese_query(self):
        self.assertTrue(
            is_supported_video_url(
                "https://www.douyin.com/jingxuan/search/五分钟学会红黑树?aid=4e95e",
                "douyin",
            )
        )

    def test_rejects_mismatched_platform_url(self):
        self.assertFalse(
            is_supported_video_url("https://www.bilibili.com/video/BV1xx411c7mD", "douyin")
        )

    def test_rejects_non_platform_url(self):
        self.assertFalse(is_supported_video_url("https://example.com/video/123"))


if __name__ == "__main__":
    unittest.main()
