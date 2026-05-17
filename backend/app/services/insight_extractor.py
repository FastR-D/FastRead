import json
import logging
import os
import re
from dataclasses import asdict, is_dataclass
from typing import Any


CARD_LIMIT = 8
CLAIM_LIMIT = 8
LLM_CONTEXT_CHARS = int(os.getenv("INSIGHT_LLM_CONTEXT_CHARS", "24000"))

logger = logging.getLogger(__name__)

CARD_TYPES = {
    "核心结论",
    "关键概念",
    "机制原理",
    "操作步骤",
    "风险提醒",
    "反常识",
    "行动清单",
    "案例证据",
    "金句",
    "知识要点",
}

HIGH_RISK_TOPICS = {
    "医疗健康": ["治疗", "治愈", "药", "疾病", "癌", "疫苗", "医生", "医院", "保健", "减肥", "血压", "血糖"],
    "金融投资": ["投资", "股票", "基金", "收益", "回报", "暴富", "贷款", "保险", "理财", "币", "加密货币"],
    "法律政策": ["违法", "合法", "政策", "法律", "合同", "处罚", "税", "监管", "诉讼", "法院"],
    "公共安全": ["安全", "事故", "灾害", "消防", "食品安全", "中毒", "隐患"],
}

CLAIM_TYPE_LABELS = {
    "data": "数据陈述",
    "causal": "因果判断",
    "advice": "经验建议",
    "risk": "高风险主题",
    "opinion": "观点判断",
    "fact": "事实陈述",
}


def _as_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    return getattr(value, "__dict__", {}) or {}


def _clean_markdown(text: str) -> str:
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", "", text or "")
    text = re.sub(r"\[[^\]]+]\([^)]*\)", lambda m: m.group(0).split("]")[0].lstrip("["), text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r"^[>#\-\*\s]+", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?；;\n]+", _clean_markdown(text))
    ignored = ["来源链接", "思维导图", "免责声明"]
    return [
        p.strip(" -:*#\t")
        for p in parts
        if len(p.strip()) >= 12 and not _contains_any(p, ignored)
    ]


def _clamp(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _level(score: int) -> str:
    if score >= 75:
        return "高"
    if score >= 45:
        return "中"
    return "低"


def _score_item(score: float, reason: str) -> dict:
    value = _clamp(score)
    return {"score": value, "level": _level(value), "reason": reason}


def _extract_headings(markdown: str) -> list[str]:
    return [
        m.group(1).strip()
        for m in re.finditer(r"^#{1,4}\s+(.+)$", markdown or "", flags=re.MULTILINE)
        if m.group(1).strip()
    ]


def _extract_bullets(markdown: str) -> list[str]:
    bullets = []
    for line in (markdown or "").splitlines():
        match = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$", line)
        if match:
            text = _clean_markdown(match.group(1))
            if len(text) >= 10:
                bullets.append(text)
    return bullets


def _contains_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _truncate_middle(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    marker = "\n\n...[中间内容已压缩，保留首尾以控制 API 请求长度]...\n\n"
    head_len = max(0, int((limit - len(marker)) * 0.58))
    tail_len = max(0, limit - len(marker) - head_len)
    return f"{text[:head_len]}{marker}{text[-tail_len:]}"


def _format_timestamp(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds)))
    except Exception:
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _segment_text(segments: list[Any], full_text: str) -> str:
    lines = []
    for seg in segments or []:
        data = _as_dict(seg)
        text = str(data.get("text") or "").strip()
        if not text:
            continue
        start = data.get("start", 0)
        lines.append(f"[{_format_timestamp(start)}] {text}")
    if lines:
        return "\n".join(lines)
    return full_text or ""


def _json_from_response(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            loaded = json.loads(raw[start:end + 1])
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    return {}


def _sanitize_card_text(value: Any, limit: int) -> str:
    text = _clean_markdown(str(value or ""))
    text = text.strip(" ，,。；;：:")
    return text[:limit]


def _looks_like_filler(card: dict) -> bool:
    joined = f"{card.get('title', '')} {card.get('content', '')}"
    filler_terms = [
        "围绕",
        "知识主题",
        "回到原笔记",
        "没有足够",
        "基于标题和元数据",
        "本视频主要介绍",
        "本期视频讲了",
    ]
    if _contains_any(joined, filler_terms):
        return True
    content = card.get("content", "")
    return len(content) < 28 and card.get("type") != "金句"


def _normalize_llm_cards(raw_cards: Any) -> list[dict]:
    if not isinstance(raw_cards, list):
        return []

    cards = []
    for raw_card in raw_cards:
        if not isinstance(raw_card, dict):
            continue
        card_type = _sanitize_card_text(raw_card.get("type"), 12) or "知识要点"
        if card_type not in CARD_TYPES:
            card_type = "知识要点"
        title = _sanitize_card_text(raw_card.get("title"), 40)
        content = _sanitize_card_text(raw_card.get("content"), 260)
        evidence = _sanitize_card_text(raw_card.get("evidence"), 180)
        try:
            priority = int(raw_card.get("priority", 60))
        except Exception:
            priority = 60
        priority = max(0, min(100, priority))

        card = {
            "type": card_type,
            "title": title or card_type,
            "content": content,
            "evidence": evidence,
            "priority": priority,
        }
        if _looks_like_filler(card):
            continue
        cards.append(card)

    return _dedupe_cards(cards)


def _build_llm_card_prompt(markdown: str, transcript_data: dict, audio_data: dict) -> str:
    raw_info = _as_dict(audio_data.get("raw_info"))
    tags = raw_info.get("tags") or raw_info.get("hashtags") or []
    if isinstance(tags, list):
        tags = "、".join(str(tag) for tag in tags if tag)

    title = audio_data.get("title") or raw_info.get("title") or "未命名视频"
    desc = raw_info.get("desc") or raw_info.get("caption") or raw_info.get("metadata_text") or ""
    transcript_text = transcript_data.get("full_text") or ""
    transcript_context = _segment_text(transcript_data.get("segments") or [], transcript_text)

    notes_budget = max(3000, int(LLM_CONTEXT_CHARS * 0.34))
    transcript_budget = max(6000, LLM_CONTEXT_CHARS - notes_budget)
    note_context = _truncate_middle(markdown or "", notes_budget)
    transcript_context = _truncate_middle(transcript_context, transcript_budget)

    schema = {
        "cards": [
            {
                "type": "核心结论",
                "title": "8到24个字的具体标题",
                "content": "80到180字，直接讲清一个可复用知识点、判断、机制、步骤或风险。",
                "evidence": "来自转录或笔记的短证据，尽量保留原话或时间点。",
                "priority": 95,
            }
        ]
    }

    return f"""你是严苛的视频知识编辑。请从下面的视频转录、笔记和元信息中提取真正有学习价值的知识卡片。

目标：让用户不看原视频，也能抓住视频的核心知识、关键判断、方法步骤、风险边界和可复用经验。

硬性规则：
1. 优先依据“时间轴转录”，笔记只能作为辅助校验；不要只改写目录、标题或小节名。
2. 输出 5 到 8 张卡片。宁可少，也不要空话、重复话、标题党。
3. 每张卡片必须承载一个具体知识点：结论、概念、机制、步骤、案例证据、风险、反常识或行动建议。
4. content 要说清“是什么 + 为什么重要/怎么用/边界是什么”，不要写“本视频主要讲了……”。
5. evidence 放能支撑这张卡片的短证据；如果有时间点，保留时间点。
6. 不要输出 Markdown，不要解释过程，只输出合法 JSON。

允许的 type：核心结论、关键概念、机制原理、操作步骤、风险提醒、反常识、行动清单、案例证据、金句、知识要点。

JSON 结构示例：
{json.dumps(schema, ensure_ascii=False)}

视频元信息：
标题：{title}
标签：{tags}
简介：{desc}

笔记：
{note_context}

时间轴转录：
{transcript_context}
"""


def _call_llm_for_cards(markdown: str, transcript_data: dict, audio_data: dict, gpt: Any) -> list[dict]:
    if gpt is None:
        return []

    prompt = _build_llm_card_prompt(markdown, transcript_data, audio_data)
    messages = [{"role": "user", "content": prompt}]
    old_temperature = getattr(gpt, "temperature", None)

    try:
        if old_temperature is not None:
            gpt.temperature = 0.2

        if hasattr(gpt, "_chat_completion_create"):
            response = gpt._chat_completion_create(messages)
        else:
            client = getattr(gpt, "client", None)
            model = getattr(gpt, "model", None)
            if client is None or model is None:
                return []
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
            )
    except Exception as exc:
        logger.warning(f"LLM 知识卡片生成失败，回退到离线规则: {exc}")
        return []
    finally:
        if old_temperature is not None:
            gpt.temperature = old_temperature

    try:
        content = response.choices[0].message.content
    except Exception:
        return []

    payload = _json_from_response(content)
    cards = _normalize_llm_cards(payload.get("cards"))
    if len(cards) < 3:
        logger.warning("LLM 知识卡片数量不足，回退到离线规则")
        return []
    return cards


def _claim_key(text: str) -> str:
    return re.sub(r"\W+", "", text or "")[:48]


def _find_risk_topics(text: str) -> list[str]:
    return [
        topic
        for topic, keywords in HIGH_RISK_TOPICS.items()
        if _contains_any(text, keywords)
    ]


def _claim_type(text: str, risk_topics: list[str]) -> str:
    normalized = re.sub(r"^\s*\d+[.)、]\s*", "", text)
    if risk_topics:
        return "risk"
    if re.search(r"\d+(?:\.\d+)?%?|[12]\d{3}年|\d+倍|\d+个|\d+元|\d+分钟|\d+小时", normalized):
        return "data"
    if _contains_any(normalized, ["导致", "造成", "决定", "因为", "所以", "影响", "证明", "取决于", "源于"]):
        return "causal"
    if _contains_any(normalized, ["建议", "应该", "需要", "可以", "方法", "步骤", "先", "然后", "适合", "行动"]):
        return "advice"
    if _contains_any(normalized, ["认为", "观点", "可能", "大概", "或许", "感觉", "倾向于"]):
        return "opinion"
    return "fact"


def _claim_risk_level(text: str, claim_type: str, risk_topics: list[str]) -> str:
    absolute_terms = ["一定", "必然", "所有", "永远", "唯一", "完全", "绝对", "肯定", "只要"]
    if risk_topics:
        return "high"
    if claim_type in {"data", "causal"} and _contains_any(text, absolute_terms):
        return "high"
    if claim_type in {"data", "causal"}:
        return "medium"
    if _contains_any(text, absolute_terms):
        return "medium"
    return "low"


def _claim_verdict(
    text: str,
    claim_type: str,
    risk_level: str,
    metadata_only: bool,
    transcript_len: int,
) -> tuple[str, str, str, int]:
    evidence_words = ["来源", "研究", "数据", "报告", "实验", "案例", "统计", "论文", "官方", "调查"]
    has_evidence_signal = _contains_any(text, evidence_words)

    if metadata_only or transcript_len < 80:
        return (
            "证据不足",
            "缺少完整转写，当前只能基于标题或元数据做风险提示。",
            "建议回到原视频或权威资料核对后再使用。",
            35,
        )
    if risk_level == "high":
        return (
            "需重点核实",
            "涉及高风险主题或绝对化表述，不能仅凭视频内容采信。",
            "优先查官方文件、原始报告、专业机构或多方资料。",
            45 if has_evidence_signal else 35,
        )
    if claim_type in {"data", "causal"} and not has_evidence_signal:
        return (
            "缺少来源",
            "包含数字、因果或具体结论，但文本中没有明显来源线索。",
            "建议补充检索原始数据、报告或出处。",
            55,
        )
    if claim_type == "opinion":
        return (
            "观点判断",
            "更像作者观点或解释框架，不适合直接按事实采信。",
            "可作为思考角度，落地前仍需结合场景验证。",
            65,
        )
    if has_evidence_signal:
        return (
            "有来源线索",
            "文本中出现研究、数据、案例或来源信号，但尚未联网交叉验证。",
            "后续可接入外部检索确认来源质量。",
            72,
        )
    return (
        "文本内可追溯",
        "该主张能在转写或笔记中定位，但尚未做外部事实核查。",
        "适合作为笔记线索，不宜当作最终证据。",
        68,
    )


def _claim_priority(text: str, claim_type: str, risk_level: str) -> int:
    normalized = re.sub(r"^\s*\d+[.)、]\s*", "", text)
    score = 40
    if risk_level == "high":
        score += 35
    elif risk_level == "medium":
        score += 20
    if claim_type in {"data", "causal", "risk"}:
        score += 16
    if re.search(r"\d", normalized):
        score += 8
    if _contains_any(text, ["一定", "必然", "所有", "唯一", "绝对", "证明", "导致"]):
        score += 8
    return score


def _extract_claim_candidates(markdown: str, transcript_text: str) -> list[str]:
    source_items = _extract_bullets(markdown) + _sentences(markdown)
    if len(source_items) < 6:
        source_items += _sentences(transcript_text)[:24]

    candidates = []
    seen = set()
    for item in source_items:
        text = _clean_markdown(item).strip(" ，,。；;：:")
        text = re.sub(r"^\d+[.)、]\s*", "", text).strip()
        if not 14 <= len(text) <= 180:
            continue
        if _contains_any(text, ["目录", "来源链接", "思维导图", "免责声明"]):
            continue
        key = _claim_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append(text)
    return candidates


def _dedupe_claims(claims: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for claim in sorted(claims, key=lambda item: item.get("priority", 0), reverse=True):
        key = _claim_key(claim.get("claim", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(claim)
        if len(result) >= CLAIM_LIMIT:
            break
    return result


def _build_verification(markdown: str, transcript_text: str, metadata_only: bool, transcript_len: int) -> dict:
    claims = []
    for text in _extract_claim_candidates(markdown, transcript_text):
        risk_topics = _find_risk_topics(text)
        claim_type = _claim_type(text, risk_topics)
        risk_level = _claim_risk_level(text, claim_type, risk_topics)
        verdict, reason, evidence_hint, confidence = _claim_verdict(
            text,
            claim_type,
            risk_level,
            metadata_only,
            transcript_len,
        )
        claims.append({
            "claim": text,
            "type": claim_type,
            "type_label": CLAIM_TYPE_LABELS.get(claim_type, "事实陈述"),
            "risk_level": risk_level,
            "risk_topics": risk_topics,
            "verdict": verdict,
            "confidence": confidence,
            "reason": reason,
            "evidence_hint": evidence_hint,
            "priority": _claim_priority(text, claim_type, risk_level),
        })

    claims = _dedupe_claims(claims)
    high_risk_count = sum(1 for claim in claims if claim["risk_level"] == "high")
    medium_risk_count = sum(1 for claim in claims if claim["risk_level"] == "medium")
    needs_review_count = sum(
        1
        for claim in claims
        if claim["verdict"] in {"证据不足", "缺少来源", "需重点核实"}
    )

    score = 88 - high_risk_count * 14 - medium_risk_count * 3 - needs_review_count * 2
    if metadata_only:
        score -= 18
    if transcript_len >= 800:
        score += 8
    score = _clamp(score)

    if not claims:
        status = "无法判断"
        summary = "未抽取到足够明确的可核验主张。"
    elif high_risk_count:
        status = "高风险"
        summary = f"抽取到 {len(claims)} 条关键主张，其中 {high_risk_count} 条需要重点核实。"
    elif needs_review_count:
        status = "需核实"
        summary = f"抽取到 {len(claims)} 条关键主张，其中 {needs_review_count} 条缺少外部证据或来源线索。"
    else:
        status = "基本可信"
        summary = f"抽取到 {len(claims)} 条关键主张，未发现明显高风险表述。"

    return {
        "version": 1,
        "external_check": False,
        "overall": {
            "status": status,
            "score": score,
            "summary": summary,
            "note": "当前为离线核验，只判断可核验性、风险和文本内依据，不代表外部事实已证实。",
        },
        "claim_counts": {
            "total": len(claims),
            "needs_review": needs_review_count,
            "high_risk": high_risk_count,
            "medium_risk": medium_risk_count,
        },
        "claims": claims,
    }


def _make_card(card_type: str, title: str, content: str, priority: int, evidence: str = "") -> dict:
    return {
        "type": card_type,
        "title": title[:40] or card_type,
        "content": content[:220],
        "evidence": evidence[:160],
        "priority": priority,
    }


def _dedupe_cards(cards: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for card in sorted(cards, key=lambda item: item.get("priority", 0), reverse=True):
        if _looks_like_filler(card):
            continue
        key = re.sub(r"\W+", "", f"{card.get('title', '')}{card.get('content', '')}")[:36]
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(card)
        if len(result) >= CARD_LIMIT:
            break
    return result


def _build_cards(markdown: str, transcript_text: str, audio_meta: dict) -> list[dict]:
    headings = _extract_headings(markdown)
    bullets = _extract_bullets(markdown)
    sentences = _sentences(markdown) or _sentences(transcript_text)
    title = audio_meta.get("title") or _as_dict(audio_meta.get("raw_info")).get("title") or "视频知识"

    cards: list[dict] = []
    if sentences:
        cards.append(_make_card("核心结论", title, sentences[0], 100, sentences[0]))

    for text in bullets[:12]:
        if _contains_any(text, ["步骤", "先", "再", "然后", "最后", "方法", "执行", "操作", "清单"]):
            cards.append(_make_card("操作步骤", "可执行步骤", text, 88, text))
        elif _contains_any(text, ["风险", "注意", "避免", "不要", "问题", "误区", "但是"]):
            cards.append(_make_card("风险提醒", "需要注意", text, 84, text))
        elif _contains_any(text, ["建议", "可以", "应该", "需要", "适合", "行动"]):
            cards.append(_make_card("行动清单", "下一步行动", text, 82, text))
        else:
            cards.append(_make_card("知识要点", text[:18], text, 70, text))

    for heading in headings[:6]:
        related = next(
            (sentence for sentence in sentences if heading in sentence and len(sentence) >= 24),
            "",
        )
        if related and 4 <= len(heading) <= 32:
            cards.append(_make_card("关键概念", heading, related, 66, related))

    quote_candidates = [
        s for s in sentences
        if 18 <= len(s) <= 80 and _contains_any(s, ["是", "不是", "关键", "本质", "核心", "真正"])
    ]
    for sentence in quote_candidates[:2]:
        cards.append(_make_card("金句", "高浓度表达", sentence, 78, sentence))

    result = _dedupe_cards(cards)
    if not result and title:
        fallback_text = sentences[0] if sentences else _clean_markdown(transcript_text)[:160]
        if fallback_text:
            result = [_make_card("核心结论", title, fallback_text, 50, fallback_text)]
    return result


def build_insights(markdown: str, transcript: Any, audio_meta: Any, gpt: Any = None) -> dict:
    """从笔记、转录和视频元信息中生成结构化洞察；有 GPT 时优先抽取高质量知识卡片。"""
    transcript_data = _as_dict(transcript)
    audio_data = _as_dict(audio_meta)
    raw = _as_dict(transcript_data.get("raw"))
    transcript_text = transcript_data.get("full_text") or ""
    segments = transcript_data.get("segments") or []
    markdown_text = markdown or ""
    combined = f"{markdown_text}\n{transcript_text}"

    metadata_only = raw.get("source") == "douyin_metadata"
    transcript_len = len(transcript_text.strip())
    markdown_len = len(_clean_markdown(markdown_text))
    headings = _extract_headings(markdown_text)
    bullets = _extract_bullets(markdown_text)
    numeric_hits = len(re.findall(r"\d+(?:\.\d+)?%?", combined))
    evidence_hits = sum(combined.count(word) for word in ["因为", "案例", "数据", "研究", "来源", "实验", "对比", "证明"])
    action_hits = sum(combined.count(word) for word in ["步骤", "方法", "建议", "清单", "执行", "复盘", "先", "然后", "最后", "可以"])
    caveat_hits = sum(combined.count(word) for word in ["可能", "大概", "建议", "注意", "风险", "限制", "不一定"])

    density_score = (
        min(markdown_len / 28, 42)
        + min(transcript_len / 45, 26)
        + min(len(headings) * 4, 16)
        + min(len(bullets) * 2, 16)
    )
    credibility_score = (
        38
        + min(numeric_hits * 4, 18)
        + min(evidence_hits * 5, 22)
        + min(caveat_hits * 2, 10)
        + (12 if len(segments) >= 8 and not metadata_only else 0)
        - (24 if metadata_only else 0)
    )
    actionability_score = 28 + min(action_hits * 5, 38) + min(len(bullets) * 3, 22)
    if any(card_word in markdown_text for card_word in ["待办", "行动", "步骤", "操作"]):
        actionability_score += 12

    transcript_reason = "有真实转录支撑" if not metadata_only and transcript_len >= 80 else "转录内容较少，部分判断依赖标题和元数据"
    verification = _build_verification(markdown_text, transcript_text, metadata_only, transcript_len)
    credibility_score = min(credibility_score, verification["overall"]["score"] + 12)

    llm_cards = _call_llm_for_cards(markdown_text, transcript_data, audio_data, gpt)

    return {
        "version": 1,
        "summary": {
            "title": audio_data.get("title") or "",
            "transcript_type": "metadata_only" if metadata_only else "transcript",
            "transcript_chars": transcript_len,
            "markdown_chars": markdown_len,
        },
        "scores": {
            "information_density": _score_item(density_score, f"笔记含 {len(headings)} 个标题、{len(bullets)} 个列表项，转录约 {transcript_len} 字。"),
            "credibility": _score_item(credibility_score, f"{transcript_reason}；检测到 {numeric_hits} 个数字线索、{evidence_hits} 个证据词；核验结论：{verification['overall']['status']}。"),
            "actionability": _score_item(actionability_score, f"检测到 {action_hits} 个行动词和 {len(bullets)} 个列表项。"),
        },
        "verification": verification,
        "cards": llm_cards or _build_cards(markdown_text, transcript_text, audio_data),
    }
