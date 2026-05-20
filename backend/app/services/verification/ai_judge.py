from __future__ import annotations

import json
import re

from app.db.model_dao import get_all_models
from app.services.gpt_provider import GPTProvider
from app.services.verification.query_builder import build_search_queries
from app.utils.logger import get_logger

logger = get_logger(__name__)


def json_from_ai_text(text: str) -> dict:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            return json.loads(match.group(0))
    raise ValueError("AI 核验返回不是有效 JSON")


def default_model_config() -> tuple[str | None, str | None]:
    try:
        models = get_all_models()
    except Exception as exc:
        logger.warning(f"读取默认核验模型失败: {exc}")
        return None, None
    if not models:
        return None, None
    model = models[0]
    return str(model.get("model_name") or "") or None, str(model.get("provider_id") or "") or None


def get_ai_verifier(model_name: str | None, provider_id: str | None):
    if not model_name or not provider_id:
        default_model_name, default_provider_id = default_model_config()
        model_name = model_name or default_model_name
        provider_id = provider_id or default_provider_id
    if not model_name or not provider_id:
        return None
    logger.info(f"联网核验使用 AI 模型 provider_id={provider_id}, model={model_name}")
    return GPTProvider.create(provider_id=provider_id, model_name=model_name, required=False)


def trim_context(context: str, limit: int = 6000) -> str:
    text = re.sub(r"\s+", " ", context or "").strip()
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2:]
    return f"{head}\n...\n{tail}"


def build_context_profile(gpt, context: str) -> dict:
    if not gpt or not context:
        return {}
    prompt = f"""
你是视频内容理解助手。请从视频全文上下文中提炼事实核验所需背景。
输出 JSON，不要解释：
{{
  "topic": "视频主题",
  "domain": "所属领域",
  "key_terms": ["术语1", "术语2"],
  "aliases": {{"视频中的说法": "标准术语"}}
}}

视频上下文：
{trim_context(context)}
""".strip()
    response = gpt._chat_completion_create([{"role": "user", "content": prompt}])
    try:
        payload = json_from_ai_text(response.choices[0].message.content or "")
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        logger.warning(f"AI 上下文提炼失败: {exc}")
        return {}


def build_queries(gpt, claim: str, context_profile: dict | None = None, context: str = "") -> list[str]:
    profile_text = json.dumps(context_profile or {}, ensure_ascii=False)
    prompt = f"""
你是事实核验助手。请结合视频上下文，把下面的长观点改写成适合搜索引擎检索的查询词。
要求：
1. 保留实体、术语、年份、标准名称、定理/规则名称。
2. 如果观点里有视频内简称、口误或自造词，结合上下文改写为通用标准术语。
3. 删除修辞、泛词和无关解释。
4. 历史、军事、科技、学术主题必须同时给中文和英文查询；英文查询优先使用标准人名、武器名、事件名。
5. 科学/医学/生物类数字主张必须生成能核对数字的英文论文检索式，例如保留数字并加入 proteome、protein entries、paper、review 等标准学术词。
6. 不要输出解释，只输出 JSON。
JSON 格式：{{"queries":["英文 query","中文 query"],"query":"兜底 query","atomic_claim":"...","context_term":"..."}}

视频背景：
{profile_text}

视频上下文摘录：
{trim_context(context, 2400)}

观点：
{claim}
""".strip()
    response = gpt._chat_completion_create([{"role": "user", "content": prompt}])
    payload = json_from_ai_text(response.choices[0].message.content or "")
    raw_queries = payload.get("queries") or []
    if not isinstance(raw_queries, list):
        raw_queries = []
    queries = [str(item).strip() for item in raw_queries if str(item or "").strip()]
    query = str(payload.get("query") or "").strip()
    if query:
        queries.append(query)
    atomic_claim = str(payload.get("atomic_claim") or "").strip()
    queries.extend(build_search_queries(atomic_claim or claim))
    deduped = []
    for item in queries:
        item = re.sub(r"\s+", " ", item).strip()
        if item and item not in deduped:
            deduped.append(item)
    return deduped[:4] or build_search_queries(atomic_claim or claim)


def build_query(gpt, claim: str, context_profile: dict | None = None, context: str = "") -> str:
    queries = build_queries(gpt, claim, context_profile=context_profile, context=context)
    fallback = build_search_queries(claim)
    return queries[0] if queries else (fallback[0] if fallback else "")


def judge_claim(gpt, claim: str, results: list[dict], context_profile: dict | None = None, context: str = "") -> dict:
    sources = [
        {
            "title": item.get("title", ""),
            "domain": item.get("domain", ""),
            "snippet": item.get("snippet", ""),
            "url": item.get("url", ""),
        }
        for item in results[:5]
    ]
    prompt = f"""
你是严谨的事实核验助手。请先结合视频上下文理解主张，再根据给定搜索结果判断。
判断外部事实时只能依据搜索结果；如果搜索结果不足以判断，必须输出 uncertain。
不要因为标题或词语相似就判定支持。
如果主张包含数字、范围、百分比、数量级或单位，必须核对搜索结果是否支持同一个数字和单位；只找到同主题资料但数字不一致或没有数字，输出 uncertain 或 refuted，不要输出 supported。

输出 JSON：
{{
  "verdict": "supported|refuted|uncertain",
  "reason": "一句中文理由",
  "confidence": 0-100,
  "useful_source_indexes": [0,1]
}}

待核验主张：
{claim}

视频背景：
{json.dumps(context_profile or {}, ensure_ascii=False)}

视频上下文摘录：
{trim_context(context, 2400)}

搜索结果：
{json.dumps(sources, ensure_ascii=False)}
""".strip()
    response = gpt._chat_completion_create([{"role": "user", "content": prompt}])
    payload = json_from_ai_text(response.choices[0].message.content or "")
    verdict = payload.get("verdict")
    if verdict not in {"supported", "refuted", "uncertain"}:
        verdict = "uncertain"
    indexes = payload.get("useful_source_indexes") or []
    useful_sources = []
    for idx in indexes:
        try:
            source = results[int(idx)]
            if source not in useful_sources:
                useful_sources.append(source)
        except Exception:
            continue
    return {
        "verdict": verdict,
        "reason": str(payload.get("reason") or "AI 未给出明确理由。")[:240],
        "confidence": max(0, min(100, int(payload.get("confidence") or 50))),
        "sources": useful_sources,
    }


def verdict_to_display(claim: dict, ai_result: dict) -> tuple[str, str, int]:
    verdict = ai_result.get("verdict")
    confidence = int(ai_result.get("confidence") or claim.get("confidence", 50) or 50)
    reason = ai_result.get("reason") or ""
    if verdict == "supported":
        return "AI 判断有外部佐证", reason, max(confidence, 72)
    if verdict == "refuted":
        return "AI 判断存在反证", reason, min(confidence, 35)
    return "AI 判断证据不足", reason, min(max(confidence, 40), 60)
