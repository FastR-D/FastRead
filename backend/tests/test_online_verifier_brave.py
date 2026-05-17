import importlib.util
import os
import pathlib
import sys
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "services" / "online_verifier.py"


def _install_app_stubs():
    httpx_stub = types.ModuleType("httpx")

    class HTTPStatusError(Exception):
        pass

    class NetworkError(Exception):
        pass

    class TimeoutException(Exception):
        pass

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, *_args, **_kwargs):
            raise AssertionError("HTTP calls must be mocked in this test")

    httpx_stub.HTTPStatusError = HTTPStatusError
    httpx_stub.NetworkError = NetworkError
    httpx_stub.TimeoutException = TimeoutException
    httpx_stub.Client = Client

    bs4_stub = types.ModuleType("bs4")

    class BeautifulSoup:
        def __init__(self, text, *_args, **_kwargs):
            self.text = str(text or "")

        def get_text(self, separator=" ", strip=False):
            import re

            text = re.sub(r"<[^>]+>", separator, self.text)
            text = re.sub(r"\s+", " ", text)
            return text.strip() if strip else text

        def select(self, *_args, **_kwargs):
            return []

    bs4_stub.BeautifulSoup = BeautifulSoup

    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: False

    stubs = {
        "httpx": httpx_stub,
        "bs4": bs4_stub,
        "dotenv": dotenv_stub,
        "app": types.ModuleType("app"),
        "app.gpt": types.ModuleType("app.gpt"),
        "app.gpt.gpt_factory": types.ModuleType("app.gpt.gpt_factory"),
        "app.models": types.ModuleType("app.models"),
        "app.models.model_config": types.ModuleType("app.models.model_config"),
        "app.db": types.ModuleType("app.db"),
        "app.db.model_dao": types.ModuleType("app.db.model_dao"),
        "app.services": types.ModuleType("app.services"),
        "app.services.provider": types.ModuleType("app.services.provider"),
        "app.utils": types.ModuleType("app.utils"),
        "app.utils.logger": types.ModuleType("app.utils.logger"),
    }

    class GPTFactory:
        pass

    class ModelConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class ProviderService:
        @staticmethod
        def get_provider_by_id(_provider_id):
            return None

    class Logger:
        def info(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

    stubs["app.gpt.gpt_factory"].GPTFactory = GPTFactory
    stubs["app.models.model_config"].ModelConfig = ModelConfig
    stubs["app.db.model_dao"].get_all_models = lambda: []
    stubs["app.services.provider"].ProviderService = ProviderService
    stubs["app.utils.logger"].get_logger = lambda _name: Logger()
    sys.modules.update(stubs)


def _load_online_verifier():
    _install_app_stubs()
    spec = importlib.util.spec_from_file_location("online_verifier_under_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("online_verifier module spec not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestOnlineVerifierBrave(unittest.TestCase):
    def setUp(self):
        self.env_patch = mock.patch.dict(
            os.environ,
            {
                "ONLINE_VERIFY_SEARCH_PROVIDER": "brave",
                "ONLINE_VERIFY_SEARCH_FALLBACK_PROVIDERS": "baidu,bing_cn",
                "BRAVE_SEARCH_API_KEY": "test-key",
                "BRAVE_SEARCH_COUNTRY": "CN",
                "BRAVE_SEARCH_LANG": "zh-hans",
                "BRAVE_SEARCH_UI_LANG": "zh-CN",
            },
        )
        self.env_patch.start()
        self.online_verifier = _load_online_verifier()

    def tearDown(self):
        self.env_patch.stop()

    def test_parse_brave_results_normalizes_html_and_sources(self):
        payload = {
            "web": {
                "results": [
                    {
                        "title": "Example <strong>Title</strong>",
                        "url": "https://example.edu/report",
                        "description": "A <b>trusted</b> source.",
                        "extra_snippets": ["More <em>context</em>"],
                    },
                    {
                        "title": "Duplicate",
                        "url": "https://example.edu/report",
                        "description": "Ignored duplicate",
                    },
                ],
            }
        }

        results = self.online_verifier._parse_brave_results(payload, max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Example Title")
        self.assertEqual(results[0]["domain"], "example.edu")
        self.assertEqual(results[0]["snippet"], "A trusted source. More context")
        self.assertTrue(results[0]["trusted"])

    def test_search_web_dispatches_to_brave_provider(self):
        result = [{"title": "brave", "url": "https://example.com", "snippet": ""}]
        with mock.patch.object(self.online_verifier, "search_brave", return_value=result) as search_brave:
            self.assertEqual(self.online_verifier.search_web("query", max_results=3), result)

        search_brave.assert_called_once_with("query", max_results=3)

    def test_search_web_falls_back_when_brave_is_unavailable(self):
        fallback_result = [{"title": "fallback", "url": "https://example.com", "snippet": ""}]
        with mock.patch.object(
            self.online_verifier,
            "search_brave",
            side_effect=self.online_verifier.httpx.TimeoutException("timeout"),
        ), mock.patch.object(
            self.online_verifier,
            "search_baidu",
            return_value=fallback_result,
        ) as search_baidu:
            results = self.online_verifier.search_web("query", max_results=3)

        self.assertEqual(results, fallback_result)
        search_baidu.assert_called_once_with("query", max_results=3)

    def test_search_brave_uses_mainland_localization_params(self):
        captured = {}

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "web": {
                        "results": [
                            {
                                "title": "标题",
                                "url": "https://example.com",
                                "description": "摘要",
                            }
                        ]
                    }
                }

        class Client:
            def __init__(self, *args, **kwargs):
                captured["headers"] = kwargs.get("headers")

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def get(self, url, params):
                captured["url"] = url
                captured["params"] = params
                return Response()

        with mock.patch.object(self.online_verifier.httpx, "Client", Client):
            results = self.online_verifier.search_brave("测试", max_results=1)

        self.assertEqual(results[0]["title"], "标题")
        self.assertEqual(captured["params"]["country"], "CN")
        self.assertEqual(captured["params"]["search_lang"], "zh-hans")
        self.assertEqual(captured["params"]["ui_lang"], "zh-CN")
        self.assertEqual(captured["params"]["text_decorations"], "false")
        self.assertEqual(captured["headers"]["Accept-Language"], "zh-CN,zh;q=0.9,en;q=0.7")


class TestOnlineVerifierDomesticAcademic(unittest.TestCase):
    def setUp(self):
        self.env_patch = mock.patch.dict(
            os.environ,
            {
                "ONLINE_VERIFY_SEARCH_PROVIDER": "bing_academic",
                "ONLINE_VERIFY_SEARCH_FALLBACK_PROVIDERS": "baidu_xueshu,baidu,bing_cn,brave",
            },
        )
        self.env_patch.start()
        self.online_verifier = _load_online_verifier()

    def tearDown(self):
        self.env_patch.stop()

    def test_provider_chain_prefers_domestic_academic_search(self):
        self.assertEqual(
            self.online_verifier._provider_chain(),
            ["bing_academic", "baidu_xueshu", "baidu", "bing_cn", "brave"],
        )

    def test_search_web_dispatches_to_bing_academic_first(self):
        result = [{"title": "paper", "url": "https://cn.bing.com/academic", "snippet": ""}]
        with mock.patch.object(
            self.online_verifier,
            "search_bing_academic",
            return_value=result,
        ) as search_bing_academic, mock.patch.object(
            self.online_verifier,
            "search_brave",
        ) as search_brave:
            self.assertEqual(self.online_verifier.search_web("query", max_results=3), result)

        search_bing_academic.assert_called_once_with("query", max_results=3)
        search_brave.assert_not_called()

    def test_search_web_falls_back_to_baidu_xueshu(self):
        result = [{"title": "academic", "url": "https://xueshu.baidu.com/s", "snippet": ""}]
        with mock.patch.object(
            self.online_verifier,
            "search_bing_academic",
            return_value=[],
        ), mock.patch.object(
            self.online_verifier,
            "search_baidu_xueshu",
            return_value=result,
        ) as search_baidu_xueshu:
            self.assertEqual(self.online_verifier.search_web("query", max_results=3), result)

        search_baidu_xueshu.assert_called_once_with("query", max_results=3)

    def test_search_web_multi_supplements_when_primary_source_is_weak(self):
        weak_result = {
            "title": "鸡蛋 1500种 独特 蛋白质",
            "url": "https://www.zhihu.com/question/1",
            "snippet": "鸡蛋 1500种 独特 蛋白质",
            "trusted": False,
        }
        academic_result = {
            "title": "鸡蛋 1500种 独特 蛋白质 研究",
            "url": "https://example.edu/paper",
            "snippet": "鸡蛋 1500种 独特 蛋白质 研究",
            "trusted": True,
        }

        def provider_results(provider, _query, max_results=5):
            if provider == "baidu_xueshu":
                return [academic_result]
            return []

        provider_trace = []
        with mock.patch.object(
            self.online_verifier,
            "_search_web_with_provider",
            return_value=([weak_result], "bing_academic"),
        ), mock.patch.object(
            self.online_verifier,
            "_provider_results",
            side_effect=provider_results,
        ):
            results = self.online_verifier.search_web_multi(
                ["鸡蛋 1500种 蛋白质"],
                claim="鸡蛋中含有超过1500种独特蛋白质",
                provider_trace=provider_trace,
            )

        self.assertEqual(results, [weak_result, academic_result])
        self.assertEqual(provider_trace, ["bing_academic", "baidu_xueshu"])


if __name__ == "__main__":
    unittest.main()
