from __future__ import annotations

import re

from app.services.verification.constants import GENERIC_SEARCH_TERMS, KEEP_CHINESE_TERMS
from app.services.verification.numeric_evidence import (
    extract_numeric_constraints,
    has_egg_context,
    has_protein_context,
    is_scientific_claim,
)


def clean_claim_text(claim: str) -> str:
    text = re.sub(r"^\s*(引申|应用|经济学解释|总结|核心观点|结论)[：:]\s*", "", claim or "")
    text = re.sub(r"[*_#>`\"'“”]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def scientific_search_queries(text: str) -> list[str]:
    if not is_scientific_claim(text):
        return []

    constraints = extract_numeric_constraints(text)
    numbers = []
    for item in constraints:
        value = item.get("value")
        if value is None:
            continue
        number = str(int(value)) if float(value).is_integer() else str(value)
        if number not in numbers:
            numbers.append(number)

    queries = []
    has_egg = has_egg_context(text)
    has_protein = has_protein_context(text)
    if has_egg and has_protein:
        for number in numbers[:2]:
            queries.extend([
                f"\"chicken egg\" \"{number}\" proteins proteome",
                f"\"chicken egg\" \"{number}\" \"protein entries\"",
                f"鸡蛋 {number} 蛋白质组 蛋白质",
            ])
        queries.extend([
            "\"Egg White and Yolk Protein Atlas\"",
            "\"chicken egg\" \"protein entries\" proteome",
            "\"chicken egg white proteome\"",
            "鸡蛋 蛋白质组 蛋清 蛋黄 论文",
        ])
    elif has_protein:
        for number in numbers[:2]:
            queries.extend([
                f"\"{number}\" proteins proteome",
                f"\"{number}\" \"protein entries\"",
                f"蛋白质组 {number} 论文",
            ])
        queries.extend([
            "proteome protein entries paper",
            "蛋白质组 论文 研究",
        ])
    else:
        queries.extend([
            f"{text[:60]} paper",
            f"{text[:60]} 论文 研究",
        ])
    return queries


def domain_terms_for_claim(text: str) -> list[str]:
    terms = []
    if any(hint in text for hint in ("黑色节点", "红黑", "黑高", "黑路同", "叶子节点")):
        terms.extend(["红黑树", "黑高", "性质"])
    if any(hint.lower() in text.lower() for hint in ("b-tree", "b树", "二叉搜索树", "平衡树")):
        terms.extend(["数据结构", "树"])
    if any(hint.lower() in text.lower() for hint in ("李梅", "柯蒂斯", "lemay", "b-29", "m69", "燃烧弹", "东京大轰炸", "裸奔式轰炸")):
        terms.extend([
            "Curtis LeMay",
            "柯蒂斯 李梅",
            "B-29",
            "M69 incendiary bombs",
            "M69 燃烧弹",
            "Tokyo firebombing",
            "东京大轰炸",
        ])
    return terms


def build_search_query(claim: str) -> str:
    text = clean_claim_text(claim)
    if not text:
        return ""

    domain_terms = domain_terms_for_claim(text)
    phrase = re.split(r"[。；;\n]", text, maxsplit=1)[0].strip()
    phrase = re.sub(r"^[^：:]{1,12}[：:]\s*", "", phrase)
    if 8 <= len(phrase) <= 90:
        return " ".join([*domain_terms, phrase]).strip()

    parts = re.split(r"[，,。；;：:（）()\[\]【】、\s]+|——|--", text)
    stop_words = {
        "因为",
        "所以",
        "但是",
        "如果",
        "没有",
        "任何",
        "所有",
        "这个",
        "一种",
        "进行",
        "通过",
        "反而",
        "就是",
        "不是",
        "可以",
        "需要",
        "例如",
        "以及",
        *GENERIC_SEARCH_TERMS,
    }
    terms = list(domain_terms)
    for part in parts:
        item = part.strip()
        if not item or item in stop_words:
            continue
        if re.fullmatch(r"[a-zA-Z]{1,3}", item):
            continue
        chinese_only = "".join(re.findall(r"[\u4e00-\u9fff]", item))
        if item in KEEP_CHINESE_TERMS or len(chinese_only) >= 3:
            term = item[:18]
        else:
            term = item
        if len(term) >= 2 and term not in terms and term not in stop_words:
            terms.append(term)
        if len(terms) >= 8:
            break
    return " ".join(terms) or (claim or "")[:60]


def build_search_queries(claim: str) -> list[str]:
    text = clean_claim_text(claim)
    primary = build_search_query(text)
    queries = scientific_search_queries(text)
    if primary:
        queries.append(primary)
    lower = text.lower()

    if any(hint in lower for hint in ("李梅", "柯蒂斯", "lemay", "b-29", "m69", "燃烧弹", "东京大轰炸", "裸奔式轰炸")):
        queries = [
            "Curtis LeMay B-29 M69 Tokyo firebombing",
            "Curtis LeMay B-29 removed guns turrets M69 incendiary Tokyo raid",
            "Curtis LeMay low altitude incendiary bombing B-29 M69",
            "柯蒂斯 李梅 B-29 M69 燃烧弹 低空轰炸",
            "李梅 B-29 拆除 机枪 炮塔 M69 燃烧弹 低空轰炸",
            *queries,
        ]

    if any(hint in text for hint in ("黑色节点", "红黑", "黑高", "黑路同", "叶子节点")):
        queries.extend([
            "红黑树 黑高 性质 所有叶子 黑色节点 数量 相同",
            "red black tree property same number of black nodes paths leaves",
        ])

    deduped = []
    for query in queries:
        query = re.sub(r"\s+", " ", query or "").strip()
        if query and query not in deduped:
            deduped.append(query)
    return deduped[:4]
