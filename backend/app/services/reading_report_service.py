from __future__ import annotations

from datetime import datetime, timezone
import json
import re

from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.academic_evidence import assess_academic_identity
from app.services.gpt_provider import GPTProvider
from app.utils.logger import get_logger


logger = get_logger(__name__)

DISQUALIFYING_EVIDENCE_RISKS = {
    "blocked_domain",
    "canonical_anomaly",
    "fake_authority",
    "missing_source_identity",
    "prompt_injection",
    "redirect_anomaly",
    "retracted_or_withdrawn",
}

SYSTEM_PROMPT = """你是 FastRead 的学术论文阅读助手，报告风格优先参考 NotebookLM 的引导式理解方式。
你的任务不是堆砌零散 bullet，而是围绕读者真正需要回答的关键问题，解释论文的研究问题、方法过程、贡献、证据和局限。

硬性规则：
1. 只能依据给定原文、任务元数据和联网核验结果；不得补写来源中没有的实验数字、作者、机构、DOI 或结论。
2. 每个关键问题都要回答“答案是什么、为什么重要、依据在哪里”。
3. 明确区分 source_only（原文内陈述）、supported/refuted/mixed/insufficient/data_void/source_risk（外部核验状态）。
4. 单篇论文只能说明该研究报告了什么，不能自动写成领域共识。
5. 学术身份 Gate 未通过时，必须在 limitations 中直接说明，不能称为四大安全顶会论文。
6. 输出必须是一个 JSON 对象，不要 Markdown 代码围栏，不要额外说明。

JSON 结构：
{
  "title": "报告标题",
  "executive_summary": "连贯的总览，说明研究问题、方法主线和核心贡献",
  "key_questions": [
    {
      "question": "关键问题",
      "answer": "连贯回答",
      "why_it_matters": "为什么值得关注",
      "evidence": [{"exact_quote": "必须逐字来自材料的短引文", "page": 1, "source_url": "来源 URL"}],
      "verification_status": "source_only|supported|refuted|mixed|insufficient|data_void|source_risk"
    }
  ],
  "process": [{"step": "步骤名", "description": "该步骤如何完成"}],
  "contributions": [{"title": "贡献名", "description": "相对已有工作贡献了什么", "evidence": [{"exact_quote": "逐字原文", "page": 1, "source_url": "来源 URL"}]}],
  "limitations": ["局限或证据边界"],
  "terms": [{"term": "术语", "explanation": "面向读者的简洁解释"}],
  "suggested_questions": ["适合继续追问的问题"]
}
至少生成 4 个关键问题，其中必须覆盖研究问题、方法过程、主要贡献、实验/证据与局限。"""


def _strip_code_fence(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _as_list(value, limit: int = 12) -> list:
    return list(value)[:limit] if isinstance(value, list) else []


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _exact_source_match(quote: str, source_text: str) -> str:
    parts = [part for part in re.split(r"\s+", str(quote or "").strip()) if part]
    if not parts:
        return ""
    match = re.search(r"\s+".join(re.escape(part) for part in parts), str(source_text or ""), re.IGNORECASE)
    return match.group(0) if match else ""


def _resolve_evidence(item, evidence_sources: list[dict]) -> dict | None:
    if isinstance(item, dict):
        quote = str(item.get("exact_quote") or item.get("quote") or item.get("passage") or "").strip()
        requested_page = item.get("page") or item.get("page_start")
        requested_url = str(item.get("source_url") or "").strip()
    else:
        quote = str(item or "").strip()
        requested_page = None
        requested_url = ""
    normalized_quote = _normalized_text(quote)
    if len(normalized_quote) < 8:
        return None

    candidates = evidence_sources
    if requested_page is not None:
        try:
            requested_page_number = int(requested_page)
        except (TypeError, ValueError):
            requested_page_number = None
        page_matches = [
            source for source in candidates
            if requested_page_number is not None
            and (source.get("page_start") == requested_page_number or source.get("page_end") == requested_page_number)
        ]
        if not page_matches:
            return None
        candidates = page_matches
    if requested_url:
        url_matches = [source for source in candidates if source.get("source_url") == requested_url]
        if not url_matches:
            return None
        candidates = url_matches

    for source in candidates:
        source_text = str(source.get("text") or source.get("exact_quote") or "")
        matched_quote = _exact_source_match(quote, source_text)
        if matched_quote:
            return {
                "source_id": source.get("source_id") or "",
                "source_url": source.get("source_url") or requested_url,
                "page_start": source.get("page_start"),
                "page_end": source.get("page_end"),
                "exact_quote": matched_quote,
                "verified_in_source": True,
                "evidence_kind": source.get("evidence_kind") or "paper_source",
                "verification_status": source.get("verification_status") or "source_only",
                "claim_id": source.get("claim_id") or "",
            }
    return None


def _derived_verification_status(resolved_evidence: list[dict]) -> str:
    if not resolved_evidence:
        return "insufficient"
    external = {
        str(item.get("verification_status") or "")
        for item in resolved_evidence
        if item.get("evidence_kind") == "verification"
        and item.get("verification_status") in {
            "supported", "refuted", "mixed", "insufficient", "data_void", "source_risk"
        }
    }
    if not external:
        return "source_only"
    if "mixed" in external or ({"supported", "refuted"} <= external):
        return "mixed"
    for status in ("source_risk", "refuted", "supported", "data_void", "insufficient"):
        if status in external:
            return status
    return "insufficient"


def _completed_evidence_status(online: dict, evidence: dict, source: dict) -> str:
    status = str(online.get("status") or "")
    if not online.get("checked"):
        return "insufficient"
    if status in {"insufficient", "data_void", "source_risk"}:
        return status
    high_quality = bool(
        source
        and source.get("trust_tier") in {"A", "B"}
        and source.get("fetch_status") in {"ok", "pdf_ok"}
        and not (set(source.get("risk_flags") or []) & DISQUALIFYING_EVIDENCE_RISKS)
    )
    if not high_quality:
        return "insufficient"
    stance = str(evidence.get("stance") or "")
    if status == "supported" and stance == "support":
        return "supported"
    if status == "refuted" and stance == "refute":
        return "refuted"
    if status == "mixed" and stance in {"support", "refute"}:
        return "mixed"
    return "insufficient"


def _normalize_report(payload: dict, academic_gate: dict, evidence_sources: list[dict]) -> dict:
    key_questions = []
    for item in _as_list(payload.get("key_questions"), 10):
        if not isinstance(item, dict):
            continue
        resolved_evidence = [
            resolved
            for value in _as_list(item.get("evidence"), 8)
            for resolved in [_resolve_evidence(value, evidence_sources)]
            if resolved
        ]
        key_questions.append({
            "question": str(item.get("question") or "").strip(),
            "answer": str(item.get("answer") or "").strip(),
            "why_it_matters": str(item.get("why_it_matters") or "").strip(),
            "evidence": resolved_evidence,
            "verification_status": _derived_verification_status(resolved_evidence),
        })

    def normalized_objects(key: str, fields: tuple[str, ...], limit: int = 12) -> list[dict]:
        result = []
        for item in _as_list(payload.get(key), limit):
            if isinstance(item, dict):
                normalized = {field: str(item.get(field) or "").strip() for field in fields}
                if any(normalized.values()):
                    result.append(normalized)
        return result

    contributions = []
    for item in _as_list(payload.get("contributions"), 12):
        if not isinstance(item, dict):
            continue
        raw_evidence = item.get("evidence")
        evidence_items = raw_evidence if isinstance(raw_evidence, list) else [raw_evidence]
        resolved_evidence = [
            resolved
            for value in evidence_items[:8]
            for resolved in [_resolve_evidence(value, evidence_sources)]
            if resolved
        ]
        normalized = {
            "title": str(item.get("title") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "evidence": resolved_evidence,
        }
        if normalized["title"] or normalized["description"]:
            contributions.append(normalized)

    limitations = [str(value).strip() for value in _as_list(payload.get("limitations"), 12) if str(value).strip()]
    if not academic_gate.get("gate_passed"):
        limitations.insert(0, f"学术身份 Gate：{academic_gate.get('label')}。")

    normalized_questions = [item for item in key_questions if item["question"] and item["answer"]]
    source_grounded = bool(
        len(normalized_questions) >= 4
        and all(item["evidence"] for item in normalized_questions)
        and contributions
        and all(item["evidence"] for item in contributions)
    )
    return {
        "version": 1,
        "evidence_policy_version": "academic-evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": str(payload.get("title") or "FastRead 学术阅读报告").strip(),
        "executive_summary": str(payload.get("executive_summary") or "").strip(),
        "key_questions": normalized_questions,
        "process": normalized_objects("process", ("step", "description")),
        "contributions": contributions,
        "limitations": limitations,
        "terms": normalized_objects("terms", ("term", "explanation")),
        "suggested_questions": [
            str(value).strip() for value in _as_list(payload.get("suggested_questions"), 10) if str(value).strip()
        ],
        "academic_gate": academic_gate,
        "source_grounded": source_grounded,
        "report_grounding_status": "source_grounded" if source_grounded else "partial",
    }


class ReadingReportService:
    def __init__(self, artifacts: NoteArtifactRepository | None = None):
        self.artifacts = artifacts or NoteArtifactRepository()

    @staticmethod
    def _source_context(result: dict) -> tuple[str, dict, list[dict]]:
        audio_meta = result.get("audio_meta") or {}
        raw_info = audio_meta.get("raw_info") or {}
        transcript = result.get("transcript") or {}
        verification_input = result.get("verification_input") or {}
        insights = result.get("insights") or {}
        verification = insights.get("verification") or {}
        verification_result = result.get("verification_result") or verification.get("result") or {}

        sources = []
        for claim in verification.get("claims") or []:
            online = claim.get("online") or {}
            for source in online.get("sources") or []:
                if isinstance(source, dict):
                    sources.append(source)

        academic_candidates = [
            source.get("academic") or assess_academic_identity(source)
            for source in sources
            if isinstance(source, dict)
        ]
        academic_gate = next((item for item in academic_candidates if item.get("gate_passed")), None)
        paper_document = result.get("paper_document") or {}
        if paper_document.get("academic_gate"):
            academic_gate = paper_document["academic_gate"]
        if not academic_gate:
            academic_gate = next((item for item in academic_candidates if item.get("level") != "N/A"), None)
        if not academic_gate:
            academic_gate = assess_academic_identity({
                "title": audio_meta.get("title") or raw_info.get("title") or "",
                "author": raw_info.get("author") or raw_info.get("uploader") or "",
                "published_at": raw_info.get("published_at") or raw_info.get("date") or "",
                "url": verification_input.get("url") or raw_info.get("url") or "",
                "venue": raw_info.get("venue") or raw_info.get("conference") or "",
                "doi": raw_info.get("doi") or "",
            })

        paper_pages = paper_document.get("pages") or []
        page_budget = 65000
        per_page = max(450, min(6000, page_budget // max(len(paper_pages), 1)))
        context_pages = [
            {"page": page.get("page"), "text": str(page.get("text") or "")[:per_page]}
            for page in paper_pages
            if page.get("text")
        ]
        original_text = transcript.get("full_text") or verification_input.get("text") or ""
        source_payload = {
            "title": audio_meta.get("title") or raw_info.get("title") or "",
            "source_url": verification_input.get("url") or raw_info.get("url") or "",
            "academic_gate": academic_gate,
            "paper_pages": context_pages,
            "original_text": "" if context_pages else str(original_text)[:65000],
            "existing_markdown": str(result.get("markdown") or "")[:12000],
            "verification_overall": verification_result,
            "verification_claims": (verification.get("claims") or [])[:12],
        }
        evidence_sources = []
        paper_url = paper_document.get("pdf_url") or paper_document.get("source_url") or source_payload["source_url"]
        for page in paper_pages:
            evidence_sources.append({
                "source_id": paper_document.get("id") or "",
                "source_url": paper_url,
                "page_start": page.get("page"),
                "page_end": page.get("page"),
                "text": page.get("text") or "",
                "evidence_kind": "paper_source",
                "verification_status": "source_only",
                "claim_id": "",
            })
        for claim in verification.get("claims") or []:
            online = claim.get("online") or {}
            claim_id = str(online.get("claim_id") or claim.get("claim_id") or "")
            sources_by_url = {
                str(source.get("url") or ""): source
                for source in online.get("sources") or []
                if isinstance(source, dict) and source.get("url")
            }
            for evidence in online.get("evidence") or []:
                offsets = evidence.get("page_offsets") or {}
                evidence_url = str(evidence.get("source_url") or "")
                evidence_sources.append({
                    "source_id": evidence.get("evidence_id") or "",
                    "source_url": evidence_url,
                    "page_start": offsets.get("page_start") or offsets.get("page"),
                    "page_end": offsets.get("page_end") or offsets.get("page"),
                    "text": evidence.get("passage") or "",
                    "evidence_kind": "verification",
                    "verification_status": _completed_evidence_status(
                        online,
                        evidence,
                        sources_by_url.get(evidence_url) or {},
                    ),
                    "claim_id": claim_id,
                })
        return json.dumps(source_payload, ensure_ascii=False, default=str), academic_gate, evidence_sources

    def generate(
        self,
        *,
        task_id: str,
        provider_id: str,
        model_name: str,
        force: bool = False,
    ) -> dict:
        result = self.artifacts.read_result(task_id)
        if not result:
            raise ValueError("任务结果不存在")

        insights = result.setdefault("insights", {})
        existing = insights.get("reading_report")
        if existing and not force:
            return existing

        context, academic_gate, evidence_sources = self._source_context(result)
        if not context.strip() or (
            not evidence_sources
            and not ((result.get("transcript") or {}).get("full_text"))
            and not ((result.get("verification_input") or {}).get("text"))
        ):
            raise ValueError("当前任务没有可用于生成阅读报告的原文或核验证据")

        gpt = GPTProvider.create(provider_id=provider_id, model_name=model_name)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请基于以下材料生成报告：\n\n{context}"},
        ]
        kwargs = {
            "model": gpt.model,
            "messages": messages,
            "temperature": 0.2,
        }
        try:
            response = gpt.client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
        except Exception as exc:
            logger.warning(f"模型不支持 JSON response_format，回退普通 JSON 提示: {exc}")
            response = gpt.client.chat.completions.create(**kwargs)

        raw = response.choices[0].message.content or ""
        try:
            payload = json.loads(_strip_code_fence(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"阅读报告不是有效 JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("阅读报告响应必须是 JSON 对象")

        report = _normalize_report(payload, academic_gate, evidence_sources)
        if len(report["key_questions"]) < 4:
            raise ValueError("阅读报告至少需要 4 个有效关键问题")
        if not report["process"] or not report["contributions"]:
            raise ValueError("阅读报告必须包含方法过程和主要贡献")
        if sum(len(item["evidence"]) for item in report["key_questions"]) < 3:
            raise ValueError("阅读报告缺少可在原文中匹配的结构化引用")
        if not report["suggested_questions"]:
            report["suggested_questions"] = [
                f"请进一步解释：{item['question']}" for item in report["key_questions"][:4]
            ]

        paper_document = result.get("paper_document") or {}
        report["model"] = {"provider_id": str(provider_id), "model_name": model_name}
        report["source_content_hash"] = paper_document.get("content_hash") or ""
        report["generation_provenance"] = {
            "provider_id": str(provider_id),
            "model_name": model_name,
            "schema_version": 1,
            "parser": paper_document.get("parser") or "",
            "parser_version": paper_document.get("parser_version") or "",
        }

        def merge_report(latest: dict) -> dict:
            latest_insights = latest.setdefault("insights", {})
            latest_insights["reading_report"] = report
            latest["insights"] = latest_insights
            return latest

        self.artifacts.update_result(task_id, merge_report)
        return report

    def save_personal_summary(self, *, task_id: str, summary: str) -> dict:
        summary = str(summary or "").strip()
        if len(summary) > 300:
            raise ValueError("个人总结不能超过 300 字")
        personal_summary = {
            "content": summary,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "max_chars": 300,
        }

        def merge_summary(latest: dict) -> dict:
            insights = latest.setdefault("insights", {})
            insights["personal_summary"] = personal_summary
            latest["insights"] = insights
            return latest

        self.artifacts.update_result(task_id, merge_summary)
        return personal_summary
