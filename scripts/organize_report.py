#!/usr/bin/env python3
"""Reorganize existing recruitment labels, optionally applying an AI review.

Writes a new report revision; never contacts MCP or overwrites the source file.
The review contains source_labels and source_index/fragment/category/reason
entries. It cannot edit source facts, amounts or generate missing benefits.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from benefits import FIELDS, benefit_sections, organize_benefits
from compose_report import FOCUS_LABELS, _count_text, build_abstract, build_insights, build_records
from render_report import render_html, render_markdown


def organize_report(report: dict[str, Any], review: dict[str, Any] | None = None) -> dict[str, Any]:
    result = copy.deepcopy(report)
    core = result.setdefault("core_analysis", {})
    labels = core.get("benefit_source_labels", core.get("benefit_tags", []))
    organized = organize_benefits(labels, review)
    source_fields = set(FIELDS.values())
    sections = core.get("sections", [])
    had_section = any(spec.get("key") in source_fields for spec in sections)
    index = next((i for i, spec in enumerate(sections) if spec.get("key") in source_fields), len(sections))
    remaining = [spec for spec in sections if spec.get("key") not in source_fields]
    if labels or had_section:
        core.update(organized)
        core["sections"] = remaining[:index] + benefit_sections(organized) + remaining[index:]
    metrics = [metric for metric in result.get("metrics", [])
               if metric.get("label") not in ("画像福利标签数", "福利与工作安排项")]
    count = len(organized["benefit_tags"])
    if labels:
        metrics.append({"label": "福利与工作安排项", "value": str(count),
                        "hint": "来源标签规范整理后的去重项数；非全员享有福利数，不含薪酬、任职条件与宣传"})
    for metric in metrics:
        label = metric.get("label")
        if label in ("当前招聘人数", "近三月招聘人数", "近三月岗位数"):
            metric["value"] = _count_text(metric.get("value"))
        if label == "在招岗位数":
            metric.update(label="职位检索命中记录数", hint="上游职位记录总数，非当前在招或实际录用人数")
        elif label == "当前页样本城市数":
            metric.update(label="本次样本城市数", hint="仅本报告已有明细样本中的城市标签数，不代表全部岗位")
        elif label == "城市CR3":
            metric["hint"] = "按本报告已有城市样本派生的约数，非企业完整地域分布"
    result["metrics"] = metrics
    for key in ("employer_profile", "demand_stats"):
        for label, value in (core.get(key) or {}).items():
            if any(term in label for term in ("人数", "岗位数", "招聘规模")):
                core[key][label] = _count_text(value)
    profile = core.get("employer_profile") or {}
    for before, after in (("画像返回城市数", "画像地点标签数"), ("主要城市", "地点标签（来源节选）")):
        if before in profile:
            profile[after] = profile.pop(before)
    for row in core.get("trend_overview", []):
        if row.get("指标") in ("当前招聘人数", "近三月招聘人数", "近三月岗位数"):
            row["数值"] = _count_text(row.get("数值"))
    if core.get("consistency_check"):
        core["consistency_check"]["核验结论"] = "招聘人数与职位记录数口径不同，数值差异本身不能证明数据冲突，须分别解读"
    notes = {
        "position_keywords": "来源岗位关键词，不附各词岗位数量，不表示排名或热度",
        "salary_dist": "沿用原报告已有薪酬样本分布，非企业整体；来源币种和计薪周期仍以原记录为准",
        "city_dist": "仅按本报告已有明细样本中的地点标签聚合，不代表全部岗位或企业业务重心",
        "employer_profile": "地点字段可能包含别名、区县或地标；来源标签数不是去重行政城市数",
    }
    for spec in core.get("sections", []):
        if spec.get("key") in notes:
            spec["note"] = notes[spec["key"]]
        if spec.get("key") == "source_dist":
            source_rows = core.get("source_dist", [])
            core["source_dist"] = list(dict.fromkeys(
                row.get("渠道") if isinstance(row, dict) else row for row in source_rows
                if (row.get("渠道") if isinstance(row, dict) else row)
            ))
            spec.update(title="招聘渠道", kind="tags", note="仅来源渠道名单，未提供各渠道岗位数量")
            spec.pop("chart", None)
            spec.pop("columns", None)
    result["representative_records"] = build_records(core)
    result["insights"] = build_insights(result.get("subject", {}), core, metrics)
    request = result.get("analysis_request") or {}
    topics = request.get("focus") or ["full"]
    if not all(topic in FOCUS_LABELS for topic in topics):
        topics = ["full"]
    plan = {"topics": topics, "warnings": request.get("limitations", []),
            **(request.get("filters") or {})}
    result["abstract"] = build_abstract(result.get("subject", {}), core, metrics, plan,
                                       dry_run=bool(result.get("data_source", {}).get("dry_run")))
    result["summary"] = result["abstract"]
    result["executive_summary"] = [
        f"{item['feature']}：{item['evidence']}{item['interpretation']}"
        for item in result["insights"][:5]
    ]
    data_source = result.setdefault("data_source", {})
    data_source["content_quality"] = organized["benefit_label_quality"]
    total = len(core.get("sections", []))
    populated = sum(core.get(spec.get("key")) not in (None, "", [], {}) for spec in core.get("sections", []))
    data_source["quality_report"] = {"total_sections": total, "populated_sections": populated,
                                      "empty_sections": total - populated,
                                      "coverage_pct": round(populated / total * 100) if total else 0}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="离线整理招聘报告标签；不查询 MCP，原始文件不变")
    parser.add_argument("--input", required=True, help="原报告 JSON")
    parser.add_argument("--review", help="智能体语义审校 JSON（source_labels + decisions）")
    parser.add_argument("--output", required=True, help="新报告 JSON，必须不同于原文件")
    parser.add_argument("--report-output", help="同时输出 HTML 和同名 Markdown")
    args = parser.parse_args()
    source = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    html_path = Path(args.report_output).expanduser().resolve().with_suffix(".html") if args.report_output else None
    targets = [output] + ([html_path, html_path.with_suffix(".md")] if html_path else [])
    if source in targets or len(targets) != len(set(targets)):
        parser.error("输出文件不能覆盖原始文件，JSON、HTML、Markdown 路径必须不同")
    raw = source.read_bytes()
    report = json.loads(raw)
    review = json.loads(Path(args.review).read_text(encoding="utf-8")) if args.review else None
    result = organize_report(report, review)
    result["data_source"]["content_revision"] = {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "reorganized_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_generated_at": report.get("data_source", {}).get("generated_at"),
        "new_mcp_calls": 0,
        "semantic_review_applied": review is not None,
    }
    rendered_html = render_html(result) if html_path else None
    rendered_md = render_markdown(result) if html_path else None
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if html_path:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(rendered_html, encoding="utf-8")
        html_path.with_suffix(".md").write_text(rendered_md, encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "new_mcp_calls": 0,
                      "content_quality": result["data_source"]["content_quality"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
