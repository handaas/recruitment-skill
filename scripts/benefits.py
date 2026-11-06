"""Organize source benefit labels without treating every keyword as a benefit.

Rules recognize narrow, explicit phrases. Context-dependent labels stay pending
unless a source-bound semantic review is supplied by the calling AI agent.
No model, network, paid query, salary aggregation or eligibility inference here.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

BENEFIT_CATEGORIES = ("保障福利", "休假福利", "生活福利", "成长支持", "工作安排")
CATEGORIES = (*BENEFIT_CATEGORIES, "薪酬线索", "任职条件", "企业/岗位描述", "待核验")
FIELDS = {
    **{category: "benefit_tags" for category in BENEFIT_CATEGORIES},
    "薪酬线索": "compensation_tags", "任职条件": "hiring_requirements",
    "企业/岗位描述": "employer_descriptions", "待核验": "unclassified_tags",
}
_ALIASES = {
    "五险一金": ("保障福利", "五险一金"), "5险1金": ("保障福利", "五险一金"),
    "六险一金": ("保障福利", "六险一金"), "社保": ("保障福利", "社会保险"),
    "社会保险": ("保障福利", "社会保险"), "商业保险": ("保障福利", "商业保险"),
    "补充医疗保险": ("保障福利", "补充医疗保险"), "住房公积金": ("保障福利", "住房公积金"),
    "带薪年假": ("休假福利", "带薪年假"), "法定节假日": ("休假福利", "法定节假日"),
    "双休": ("休假福利", "双休"), "周末双休": ("休假福利", "双休"),
    "节日礼品": ("生活福利", "节日礼品"), "节日福利": ("生活福利", "节日福利"),
    "餐补": ("生活福利", "餐饮补贴"), "餐饮补贴": ("生活福利", "餐饮补贴"),
    "交通补贴": ("生活福利", "交通补贴"), "住房补贴": ("生活福利", "住房补贴"),
    "包吃": ("生活福利", "包吃"), "包住": ("生活福利", "包住"),
    "免费体检": ("生活福利", "免费体检"), "定期体检": ("生活福利", "定期体检"),
    "一对一导师": ("成长支持", "一对一导师"), "培训机会": ("成长支持", "培训机会"),
    "弹性工作": ("工作安排", "弹性工作"), "弹性工作制": ("工作安排", "弹性工作"),
    "8小时工作制": ("工作安排", "8小时工作制"),
}
_QUALIFIER = re.compile(r"不提供|不享受|没有|(?:^|[（(])(?:无|不|未|非)|取消|待定|另议|面议|视情况|可能|最高|至多|试用期|转正后|仅限|部分")


def source_labels(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            parsed = value
        if isinstance(parsed, list):
            return copy.deepcopy(parsed)
    return copy.deepcopy(value if isinstance(value, list) else [value])


def _label(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("name", "label", "text", "value"):
            if isinstance(value.get(key), str):
                return value[key]
        return ""
    if isinstance(value, str):
        return value
    return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else ""

def fragments(value: Any) -> list[str]:
    """Split list delimiters, but preserve qualified phrases and parentheticals."""
    label = _label(value).strip()
    if not label:
        return []
    if _QUALIFIER.search(label):
        return [label]
    pieces, current, depth = [], [], 0
    for char in label:
        if char in "(（[【":
            depth += 1
        elif char in ")）]】":
            depth = max(0, depth - 1)
        if depth == 0 and char in "+＋、;；|｜\n":
            if current:
                pieces.append("".join(current).strip())
                current = []
        else:
            current.append(char)
    if current:
        pieces.append("".join(current).strip())
    return [" ".join(piece.split()) for piece in pieces if piece.strip()]

def _classify(fragment: str) -> tuple[str, str, str]:
    normalized = re.sub(r"(?<=\d)\s*[~～至—–]\s*(?=\d)", "-", fragment)
    if _QUALIFIER.search(normalized):
        return "待核验", normalized, "含否定、条件或不确定限定，保留完整原文，不计作已提供福利"
    if normalized in _ALIASES:
        category, label = _ALIASES[normalized]
        return category, label, "明确短语/同义名称规范；仅代表来源描述，不证明全员适用"
    annual_pay = re.fullmatch(r"(\d+(?:-\d+)?)(?:个月薪资|薪)(起)?", normalized)
    if annual_pay:
        return "薪酬线索", annual_pay[1] + "薪" + (annual_pay[2] or ""), "发薪月数不是福利项目，不与月薪样本合并"
    if re.search(r"元[/／](?:月|年|时|天)|年薪|个月(?:年终奖|奖金)|\d薪", normalized):
        return "薪酬线索", normalized, "薪资/奖金原文线索，保留区间与限定，不推算薪酬"
    if re.search(r"驾龄|周岁|\d.*岁|\d.*届|\d.*毕业|工作经验", normalized):
        return "任职条件", normalized, "年龄、毕业或经历要求，不是福利"
    if re.search(r"强$|实验室|最佳|总人数增长|大厂|业务|产品|工程师|算法|AI|JDK|Flink|Python|Tencent|TME|linux", normalized, re.I):
        return "企业/岗位描述", normalized, "企业宣传、业务或岗位词，不作为福利或已核实企业事实"
    return "待核验", normalized, "来源未明确说明福利含义；不猜测、不删除"


def organize_benefits(value: Any, review: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = source_labels(value)
    decisions: dict[tuple[int, str], dict[str, Any]] = {}
    if review is not None:
        if review.get("source_labels") != raw:
            raise ValueError("语义审校原始标签不匹配，不能套用其他报告的判断")
        for decision in review.get("decisions", []):
            index, fragment = decision.get("source_index"), decision.get("fragment")
            if (not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(raw)
                    or fragment not in fragments(raw[index]) or decision.get("category") not in CATEGORIES
                    or not str(decision.get("reason", "")).strip()):
                raise ValueError("语义审校必须引用真实标签片段、合法类别并说明依据")
            key = (index, fragment)
            if key in decisions:
                raise ValueError("同一原始片段不能有重复语义审校决策")
            if decision["category"] in BENEFIT_CATEGORIES and _QUALIFIER.search(fragment):
                raise ValueError("含否定或条件的原文不能审校成无条件福利")
            decisions[key] = decision
    result: dict[str, Any] = {field: [] for field in dict.fromkeys(FIELDS.values())}
    evidence, seen = [], set()
    for index, original in enumerate(raw):
        pieces = fragments(original)
        if not pieces:
            evidence.append({"source_index": index, "original": original, "fragment": "",
                             "category": "待核验", "normalized": None,
                             "reason": "非文本或空值，保留原始值但不生成标签", "method": "规则整理"})
        for fragment in pieces:
            category, normalized, reason = _classify(fragment)
            decision = decisions.get((index, fragment))
            if decision:
                category, reason = decision["category"], decision["reason"]
            key = (category, normalized)
            if key not in seen:
                seen.add(key)
                result[FIELDS[category]].append(normalized)
            evidence.append({"source_index": index, "original": original, "fragment": fragment,
                             "category": category, "normalized": normalized, "reason": reason,
                             "method": "智能体语义审校" if decision else "规则整理"})
    result.update(benefit_source_labels=raw, benefit_label_evidence=evidence,
                  benefit_label_quality={"source_items": len(raw), "source_fragments": sum(len(fragments(v)) for v in raw),
                                         "benefit_items": len(result["benefit_tags"]),
                                         "pending_items": len(result["unclassified_tags"]),
                                         "semantic_reviewed_fragments": len(decisions)})
    return result


def benefit_sections(result: dict[str, Any]) -> list[dict[str, Any]]:
    titles = {"benefit_tags": "福利与工作安排（规范整理）", "compensation_tags": "薪酬线索（非福利）",
              "hiring_requirements": "任职条件（非福利）", "employer_descriptions": "企业与岗位描述（非福利）",
              "unclassified_tags": "标签疑点（待核验）"}
    return [{"key": key, "title": title, "kind": "tags",
             "note": ("仅据来源标签整理，不保证适用于每个岗位或仍然有效；原文与逐项依据保存在 JSON 的 benefit_label_evidence。"
                      if key == "benefit_tags" else "从来源福利字段分流，不计入福利项；不得作为已核实事实或薪酬统计依据。")}
            for key, title in titles.items() if result.get(key)]
