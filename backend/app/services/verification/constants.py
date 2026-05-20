from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[4] / ".env", override=False)

SEARCH_TIMEOUT = float(os.getenv("ONLINE_VERIFY_TIMEOUT", "8"))
DEFAULT_MAX_RESULTS = int(os.getenv("ONLINE_VERIFY_RESULTS", "5"))
SEARCH_PROVIDER = os.getenv("ONLINE_VERIFY_SEARCH_PROVIDER", "brave").strip().lower()
SEARCH_FALLBACK_PROVIDERS = [
    provider.strip().lower()
    for provider in os.getenv(
        "ONLINE_VERIFY_SEARCH_FALLBACK_PROVIDERS",
        "bing_academic,bing_cn,baidu",
    ).split(",")
    if provider.strip()
]
BRAVE_SEARCH_ENDPOINT = os.getenv(
    "BRAVE_SEARCH_ENDPOINT",
    "https://api.search.brave.com/res/v1/web/search",
).strip()
NETWORK_UNAVAILABLE_MESSAGE = (
    "当前运行环境无法访问外网，已保留离线核验结果；请检查网络、代理或 Docker/WSL 网络配置后重试。"
)
BRAVE_UNAVAILABLE_MESSAGE = (
    "Brave Search API 在当前网络链路不可达，已尝试切换国内搜索兜底；"
    "如需强制使用 Brave，请让 Docker 容器走可访问 api.search.brave.com 的代理。"
)

TRUSTED_DOMAIN_HINTS = (
    ".gov",
    ".edu",
    "who.int",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "un.org",
    "stats.gov.cn",
    "gov.cn",
    "pku.edu.cn",
    "tsinghua.edu.cn",
    "cnki.net",
    "wanfangdata.com.cn",
    "cqvip.com",
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "sciencedirect.com",
    "springer.com",
    "link.springer.com",
    "frontiersin.org",
    "mdpi.com",
    "wiley.com",
    "tandfonline.com",
    "acs.org",
    "nature.com",
    "science.org",
)

AUTHORITY_TITLE_HINTS = (
    "官方",
    "国家",
    "政府",
    "统计局",
    "世界银行",
    "国际货币基金",
    "研究",
    "报告",
    "论文",
    "学报",
    "期刊",
    "硕士",
    "博士",
)

SCIENTIFIC_CLAIM_HINTS = (
    "蛋白质",
    "蛋白",
    "基因",
    "细胞",
    "分子",
    "酶",
    "组学",
    "蛋白质组",
    "proteome",
    "proteomic",
    "protein",
    "gene",
    "cell",
    "molecular",
)

NUMERIC_OPERATOR_WORDS = {
    "超过": "gt",
    "超出": "gt",
    "大于": "gt",
    "高于": "gt",
    "多于": "gt",
    "以上": "gte",
    "不少于": "gte",
    "至少": "gte",
    "不低于": "gte",
    "小于": "lt",
    "低于": "lt",
    "少于": "lt",
    "不足": "lt",
    "不超过": "lte",
    "至多": "lte",
    "最多": "lte",
    "约": "approx",
    "大约": "approx",
    "左右": "approx",
    "近": "approx",
    "将近": "approx",
    "more than": "gt",
    "over": "gt",
    "greater than": "gt",
    "at least": "gte",
    "less than": "lt",
    "under": "lt",
    "fewer than": "lt",
    "no more than": "lte",
    "about": "approx",
    "around": "approx",
    "approximately": "approx",
    "~": "approx",
    ">": "gt",
    ">=": "gte",
    "<": "lt",
    "<=": "lte",
}

KEEP_CHINESE_TERMS = {
    "边际成本",
    "边际效用",
    "价格歧视",
    "集体行动",
    "隐性成本",
    "激励机制",
    "李梅",
    "柯蒂斯李梅",
    "燃烧弹",
    "低空轰炸",
    "东京大轰炸",
}

GENERIC_SEARCH_TERMS = {
    "关键",
    "属性",
    "节点",
    "路径",
    "后代",
    "叶子",
    "数量",
    "相同",
    "包含",
    "必须",
    "所有",
    "任一",
    "解释",
    "定义",
    "意思",
    "词语",
}

LOW_VALUE_SOURCE_HINTS = (
    "baike.baidu.com",
    "hanyu.baidu.com",
    "cidian",
    "hydcd",
    "zdic.net",
    "cidian.qianp.com",
)
