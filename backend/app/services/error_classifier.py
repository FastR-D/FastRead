from __future__ import annotations


def classify_generation_error(message: str | None) -> dict:
    """Convert low-level generation errors into product-facing failure categories."""
    raw_message = str(message or "").strip()
    text = raw_message.lower()

    categories = [
        (
            "cookie",
            ["cookie", "cookies", "登录", "fresh cookies", "msToken".lower(), "空响应"],
            "抖音 Cookie 需要重新同步",
            "后端没有拿到有效的抖音登录态，无法读取视频详情或下载音频。",
            "请在浏览器插件里打开抖音精选并重新同步 Cookie，然后重试任务。",
        ),
        (
            "douyin_detail",
            ["抖音详情", "aweme", "modal_id", "视频信息", "详情接口"],
            "抖音视频信息获取失败",
            "抖音详情接口没有返回可用的视频元数据，可能是链接失效、页面参数变化或平台临时限制。",
            "请确认链接能在浏览器打开；如果能打开，稍后重试或重新同步 Cookie。",
        ),
        (
            "provider",
            ["供应商", "provider", "api key", "api_key", "base_url", "401", "403", "unauthorized", "forbidden"],
            "模型供应商配置异常",
            "当前模型供应商、Base URL 或 API Key 配置不可用。",
            "请到模型设置页检查供应商配置，并先运行连接测试。",
        ),
        (
            "asr",
            ["asr", "whisper", "bcut", "转写", "转录", "transcrib", "字幕"],
            "音频转写失败",
            "音频下载后没有成功转成可用文本，可能是转写服务异常、音频不可识别或本地模型缺失。",
            "请切换转写引擎或稍后重试；如果使用在线转写，确认网络和服务可用。",
        ),
        (
            "llm",
            ["gpt", "llm", "openai", "chat.completions", "总结", "summar", "model", "token", "rate limit", "timeout"],
            "AI 总结生成失败",
            "转写已进入总结阶段，但大模型调用没有返回可用笔记。",
            "请检查模型额度、模型名称和网络状态；也可以换一个模型后重试。",
        ),
        (
            "media",
            ["下载音频", "下载视频", "音频下载", "视频下载", "ffmpeg", "media", "download"],
            "视频或音频处理失败",
            "后端没有成功取得可处理的音视频文件。",
            "请确认链接有效，并检查 ffmpeg 与下载器运行环境。",
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
        "title": "笔记生成失败",
        "message": "任务执行过程中出现未分类异常。",
        "retry_hint": "请稍后重试；如果连续失败，请把错误详情发给开发者排查。",
        "raw_message": raw_message,
    }
