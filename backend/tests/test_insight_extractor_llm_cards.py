import json
import importlib.util
import pathlib
import unittest
from dataclasses import dataclass


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "services" / "insight_extractor.py"
spec = importlib.util.spec_from_file_location("insight_extractor", MODULE_PATH)
if spec is None or spec.loader is None:
    raise ImportError("insight_extractor module spec not found")
insight_extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(insight_extractor)
build_insights = insight_extractor.build_insights


@dataclass
class DummySegment:
    start: float
    end: float
    text: str


@dataclass
class DummyTranscript:
    language: str
    full_text: str
    segments: list
    raw: dict | None = None


@dataclass
class DummyAudioMeta:
    title: str
    raw_info: dict


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str):
        self.choices = [_Choice(content)]


class DummyGPT:
    def __init__(self, content: str):
        self.content = content
        self.temperature = 0.7
        self.messages = None

    def _chat_completion_create(self, messages):
        self.messages = messages
        return _Response(self.content)


class FailingGPT:
    temperature = 0.7

    def _chat_completion_create(self, _messages):
        raise RuntimeError("api failed")


def _sample_inputs():
    transcript = DummyTranscript(
        language="zh",
        full_text=(
            "产品经理做需求判断时，不能只看用户说想要什么，而要回到任务场景。"
            "如果一个需求无法对应到高频任务或高痛点场景，就应该延后。"
            "落地时先写出用户任务，再列证据，最后决定是否进入排期。"
            "最大风险是把少数用户的强烈表达误判成普遍需求。"
        ),
        segments=[
            DummySegment(12, 20, "产品经理做需求判断时，不能只看用户说想要什么，而要回到任务场景。"),
            DummySegment(33, 45, "如果一个需求无法对应到高频任务或高痛点场景，就应该延后。"),
            DummySegment(66, 80, "落地时先写出用户任务，再列证据，最后决定是否进入排期。"),
            DummySegment(92, 101, "最大风险是把少数用户的强烈表达误判成普遍需求。"),
        ],
    )
    audio_meta = DummyAudioMeta(title="需求判断方法", raw_info={"tags": ["产品", "方法"]})
    markdown = "## 需求判断\n\n- 回到任务场景\n- 先写用户任务，再列证据"
    return markdown, transcript, audio_meta


class TestInsightExtractorLLMCards(unittest.TestCase):
    def test_build_insights_uses_llm_cards_when_json_is_valid(self):
        markdown, transcript, audio_meta = _sample_inputs()
        cards = [
            {
                "type": "核心结论",
                "title": "需求先回到任务场景",
                "content": "判断需求时不要停留在用户表达的功能愿望，而要确认它对应的任务是否高频、痛点是否足够强。",
                "evidence": "[00:12] 不能只看用户说想要什么，而要回到任务场景。",
                "priority": 98,
            },
            {
                "type": "操作步骤",
                "title": "三步进入排期判断",
                "content": "先写出用户任务，再列证据，最后根据任务频率和痛点强度决定是否进入排期。",
                "evidence": "[01:06] 先写出用户任务，再列证据，最后决定是否进入排期。",
                "priority": 92,
            },
            {
                "type": "风险提醒",
                "title": "警惕少数用户误导",
                "content": "少数用户表达强烈不等于需求普遍存在，需要用场景频率和证据过滤，否则容易误排优先级。",
                "evidence": "[01:32] 把少数用户的强烈表达误判成普遍需求。",
                "priority": 90,
            },
        ]
        gpt = DummyGPT(json.dumps({"cards": cards}, ensure_ascii=False))

        insights = build_insights(markdown, transcript, audio_meta, gpt=gpt)

        self.assertEqual(insights["cards"][0]["title"], "需求先回到任务场景")
        self.assertEqual(insights["cards"][1]["type"], "操作步骤")
        self.assertIn("时间轴转录", gpt.messages[0]["content"])
        self.assertEqual(gpt.temperature, 0.7)

    def test_build_insights_falls_back_when_llm_fails(self):
        markdown, transcript, audio_meta = _sample_inputs()

        insights = build_insights(markdown, transcript, audio_meta, gpt=FailingGPT())

        self.assertGreaterEqual(len(insights["cards"]), 1)
        joined = " ".join(card["content"] for card in insights["cards"])
        self.assertIn("任务场景", joined)


if __name__ == "__main__":
    unittest.main()
