from __future__ import annotations


def classify_generation_error(message: str | None) -> dict:
    """Convert low-level generation errors into product-facing failure categories."""
    raw_message = str(message or "").strip()
    text = raw_message.lower()

    categories = [
        (
            "ingest",
            ["pdf", "pymupdf", "parse", "ingest", "论文解析", "upload", "empty pdf"],
            "论文解析失败",
            "没有成功抽出可用的分页原文，可能是 PDF 损坏、受保护或链接无法抓取。",
            "请换一份可打开的 PDF，或改用论文官方页面 URL 后重试。",
        ),
        (
            "provider",
            ["供应商", "provider", "api key", "api_key", "base_url", "401", "403", "unauthorized", "forbidden"],
            "模型供应商配置异常",
            "当前模型供应商、Base URL 或 API Key 配置不可用。",
            "请到模型设置页检查供应商配置，并先运行连接测试。",
        ),
        (
            "llm",
            ["gpt", "llm", "openai", "chat.completions", "总结", "summar", "model", "token", "rate limit", "timeout"],
            "阅读报告生成失败",
            "论文已进入报告生成阶段，但大模型调用没有返回可用内容。",
            "请检查模型额度、模型名称和网络状态；也可以换一个模型后重试。",
        ),
        (
            "search",
            ["arxiv", "venue", "检索", "search provider", "brave", "serp"],
            "论文检索失败",
            "顶会检索或联网证据检索没有返回可用结果。",
            "请检查检索配置与网络，稍后重试。",
        ),
    ]

    for category, keywords, title, user_message, retry_hint in categories:
        if any(keyword in text or keyword in raw_message for keyword in keywords):
            return {
                "category": category,
                "title": title,
                "message": user_message,
                "retry_hint": retry_hint,
                "raw_message": raw_message,
            }

    return {
        "category": "unknown",
        "title": "阅读任务失败",
        "message": "任务执行过程中出现未分类异常。",
        "retry_hint": "请稍后重试；如果连续失败，请把错误详情发给开发者排查。",
        "raw_message": raw_message,
    }
