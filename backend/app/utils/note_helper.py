import re


def prepend_source_link(markdown: str | None, source_url: str) -> str | None:
    """
    在笔记开头添加来源链接；若首个非空行已包含来源链接，则更新该行并避免重复。
    """
    if markdown is None:
        return None

    source = (source_url or "").strip()
    if not source:
        return markdown

    header = f"> 来源链接：{source}"
    lines = markdown.splitlines()
    first_non_empty_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_non_empty_idx = idx
            break

    if first_non_empty_idx is not None:
        first_line = lines[first_non_empty_idx].strip()
        if first_line.startswith("> 来源链接：") or first_line.startswith("来源链接："):
            lines[first_non_empty_idx] = header
            return "\n".join(lines)

    if markdown.strip():
        return f"{header}\n\n{markdown}"
    return header


def replace_content_markers(markdown: str, video_id: str, platform: str = 'douyin') -> str:
    """
    替换 *Content-04:16*、Content-04:16 或 Content-[04:16] 为抖音原片链接。
    """
    # 匹配三种形式：*Content-04:16*、Content-04:16、Content-[04:16]
    pattern = r"(?:\*?)Content-(?:\[(\d{2}):(\d{2})\]|(\d{2}):(\d{2}))"

    safe_video_id = video_id

    def replacer(match):
        mm = match.group(1) or match.group(3)
        ss = match.group(2) or match.group(4)
        total_seconds = int(mm) * 60 + int(ss)

        if platform == 'douyin':
            url = f"https://www.douyin.com/video/{video_id}"
            url = f"https://www.douyin.com/video/{safe_video_id}"
            return f"[原片 @ {mm}:{ss}]({url})"
        if platform == 'bilibili':
            return f"[原片 @ {mm}:{ss}](https://www.bilibili.com/video/{safe_video_id}?t={total_seconds})"
        if platform == 'kuaishou':
            return f"[原片 @ {mm}:{ss}](https://www.kuaishou.com/short-video/{safe_video_id})"

        return f"({mm}:{ss})"

    return re.sub(pattern, replacer, markdown)
