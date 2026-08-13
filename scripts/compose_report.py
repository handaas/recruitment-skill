#!/usr/bin/env python3
"""Compose a recruitment big-data report by orchestrating the recruitment MCP.

Calls the upstream recruitment-mcp-server tools and assembles a structured JSON
payload rendered into a professional HTML / Markdown report. Supports
``--dry-run`` which returns a well-formed skeleton from the bundled sample data
WITHOUT contacting the MCP.

Workflow (real run):
  1. The recruitment MCP has no fuzzy search — ``matchKeyword`` is treated as the
     enterprise name. If the input lacks a full-name suffix we still pass it
     through (the upstream search resolves it), but recommend a full name.
  2. Query recruitment_trend (趋势概览), recruitment_employer_profile (雇主画像),
     recruitment_demand_analysis view=statistics (需求统计),
     recruitment_salary (薪酬明细), recruitment_job_search (职位明细).
  3. Build unified report JSON with domain sections.
  4. Optionally render HTML + Markdown.

This file never prints secrets; MCP credentials live in the server's own .env.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence

from common import REPORT_BANNER, REPORT_TYPE, json_dumps, load_json_file, print_json
import mcp_client
from render_report import render_html, render_markdown, html_to_pdf

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "report.example.json"

# Recruitment MCP tools. Note: no fuzzy_search in this server.
T_TREND = "recruitment_trend"
T_PROFILE = "recruitment_employer_profile"
T_DEMAND = "recruitment_demand_analysis"
T_SALARY = "recruitment_salary"
T_JOB_SEARCH = "recruitment_job_search"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _is_api_error(value: Any) -> bool:
    """Detect MCP API error responses (not empty data, but actual failures like 405)."""
    if value is None:
        return False
    if isinstance(value, str):
        return any(s in value for s in ("接口调用失败", "查询失败", "状态码：4", "状态码：5"))
    if isinstance(value, dict):
        for v in value.values():
            if isinstance(v, str) and any(s in v for s in ("接口调用失败", "查询失败", "状态码：4", "状态码：5")):
                return True
    return False

def _first_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if _is_api_error(value):
            return []
        # Treat upstream empty responses ({"text": "查询数据为空"}) and internal
        # skip markers ({"_error": "未指定..."}) as empty so tables don't render
        # a phantom all-"-" row.
        if set(value.keys()) <= {"text", "error", "code", "_error"} and not any(
            isinstance(value.get(k), list) for k in ("resultList", "list", "items", "data")
        ):
            return []
        for key in ("resultList", "list", "items", "data"):
            if isinstance(value.get(key), list):
                return value[key]
    if value in (None, "", {}):
        return []
    return [value]


def _first_record(value: Any) -> Dict[str, Any]:
    for record in _first_list(value):
        if isinstance(record, dict):
            return record
    if isinstance(value, dict):
        return value
    return {}


def _text(value: Any, limit: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        t = json.dumps(value, ensure_ascii=False)
    else:
        t = str(value)
    t = " ".join(t.split())
    if limit and len(t) > limit:
        return t[: limit - 1].rstrip() + "…"
    return t


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_call(tool: str, arguments: Dict[str, Any]) -> Any:
    try:
        result = mcp_client.call_tool(tool, arguments)
        if _is_api_error(result):
            return {"_error": "API错误"}
        return result
    except Exception as exc:
        return {"_error": str(exc)}


def _safe_total(payload: Any) -> Any:
    if isinstance(payload, dict):
        if _is_api_error(payload):
            return None
        return payload.get("total")
    return None


def _salary_text(value: Any) -> str:
    """workingSalary 实际结构：{coinType, min, max}（数值型，单位元/月）。

    渲染为紧凑的 "min-max" 形式（千元单位），方便在表格中阅读。
    """
    if isinstance(value, dict):
        lo = value.get("min")
        hi = value.get("max")
        if lo is not None or hi is not None:
            lo_s = f"{_num_k(lo)}K" if _is_num(lo) else _text(lo)
            hi_s = f"{_num_k(hi)}K" if _is_num(hi) else _text(hi)
            return f"{lo_s}-{hi_s}"
        if value.get("origin"):
            return _text(value.get("origin"))
    return _text(value)


def _is_num(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _num_k(value: Any) -> str:
    """Format a raw yuan amount as K (thousands), 1 decimal trimmed."""
    try:
        n = float(value) / 1000.0
        return f"{n:.1f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return _text(value)


def _salary_mid_k(value: Any) -> Optional[float]:
    """Parse a workingSalary spec into a midpoint in K (thousands yuan/month).

    Real shape: {coinType, min, max}. Also tolerates legacy {minSalary,maxSalary}
    and strings like "25-45K", "18-35K·14薪". Returns None when not parseable.
    """
    import re as _re
    if isinstance(value, dict):
        lo = value.get("min") if value.get("min") is not None else value.get("minSalary")
        hi = value.get("max") if value.get("max") is not None else value.get("maxSalary")
        lo_f = _to_float(lo)
        hi_f = _to_float(hi)
        if lo_f is not None and hi_f is not None:
            mid = (lo_f + hi_f) / 2.0
            return mid / 1000.0 if mid >= 1000 else mid
        if lo_f is not None:
            return lo_f / 1000.0 if lo_f >= 1000 else lo_f
        if hi_f is not None:
            return hi_f / 1000.0 if hi_f >= 1000 else hi_f
        return None
    s = str(value or "").strip()
    if not s:
        return None
    nums = _re.findall(r"(\d+(?:\.\d+)?)", s)
    if not nums:
        return None
    vals = [float(n) for n in nums]
    mid = sum(vals) / len(vals)
    if mid >= 1000:
        mid = mid / 1000.0
    return mid


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _salary_dist_rows(rows: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate salary/job rows into K-based salary range buckets."""
    buckets = [("0-10K", 0, 10), ("10-20K", 10, 20), ("20-30K", 20, 30), ("30K+", 30, 1e9)]
    counts = {label: 0 for label, _, _ in buckets}
    for r in rows:
        v = r.get("workingSalary")
        if v is None:
            v = r.get("薪酬区间") if r.get("薪酬区间") else r.get("薪酬")
        mid = _salary_mid_k(v)
        if mid is None:
            continue
        for label, lo, hi in buckets:
            if lo <= mid < hi:
                counts[label] += 1
                break
    return [{"薪酬区间": label, "岗位数": str(n)} for label, n in counts.items() if n > 0]


def _city_dist_rows(rows: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate salary/job rows by 城市 into a {城市,岗位数} distribution."""
    counts: Dict[str, int] = {}
    for r in rows:
        c = (r.get("城市") or "-").strip()
        if not c or c == "-":
            continue
        counts[c] = counts.get(c, 0) + 1
    out = [{"城市": k, "岗位数": str(v)} for k, v in counts.items()]
    out.sort(key=lambda x: int(x["岗位数"]), reverse=True)
    return out


def _concentration(rows: List[Mapping[str, Any]], name_key: str, value_key: str, top_n: int = 3) -> Dict[str, Any]:
    """Compute top-N concentration (CRn) and dominant category from {name,count} rows."""
    items = []
    for r in rows:
        try:
            items.append((r.get(name_key, "-"), float(str(r.get(value_key, 0)).replace(",", ""))))
        except (TypeError, ValueError):
            items.append((r.get(name_key, "-"), 0.0))
    total = sum(v for _, v in items)
    if not total:
        return {}
    items.sort(key=lambda x: x[1], reverse=True)
    cr = sum(v for _, v in items[:top_n]) / total * 100
    return {"top": items[0][0], "top_share": items[0][1] / total * 100, "cr": cr, "total": total, "n": len(items)}


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #

def resolve_enterprise_name(raw: str) -> Dict[str, Any]:
    """The recruitment MCP has no fuzzy search; matchKeyword IS the enterprise name.

    We only classify whether the input already looks like a full enterprise name
    (so we can mark it resolved). Keywords without a suffix are passed through
    verbatim — upstream search will resolve them.
    """
    raw = (raw or "").strip()
    if not raw:
        return {"keyword": "", "enterprise": "", "resolved": False, "reason": "关键词为空"}
    if any(suffix in raw for suffix in ("公司", "集团", "有限", "院", "厂", "中心", "事务所", "合作社", "合伙")):
        return {"keyword": raw, "enterprise": raw, "resolved": True, "reason": "视为企业全称"}
    return {"keyword": raw, "enterprise": raw, "resolved": True, "reason": "招聘 MCP 无模糊查询，按企业名称直查"}


def _derive_core_metrics(metrics: List[Dict[str, Any]], core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Derive additional metrics from core analysis sections."""
    city_dist = core.get("city_dist", []) if isinstance(core, dict) else []
    source_dist = core.get("source_dist", []) if isinstance(core, dict) else []
    salary_dist = core.get("salary_dist", []) if isinstance(core, dict) else []
    employer = core.get("employer_profile", {}) if isinstance(core, dict) else {}
    if isinstance(city_dist, list) and city_dist:
        metrics.append({"label": "招聘城市数", "value": str(len(city_dist)), "hint": "覆盖的招聘城市数量"})
        try:
            nums = [int(str(r.get("岗位数", "0")).replace(",", "")) for r in city_dist if str(r.get("岗位数", "0")).replace(",", "").isdigit()]
            total = sum(nums)
            if total > 0:
                top3 = sum(sorted(nums, reverse=True)[:3])
                metrics.append({"label": "城市CR3", "value": f"{top3/total*100:.1f}%", "hint": "前3大城市岗位集中度"})
        except (ValueError, TypeError):
            pass
    if isinstance(source_dist, list) and source_dist:
        metrics.append({"label": "招聘渠道数", "value": str(len(source_dist)), "hint": "不同招聘渠道数量"})
    if isinstance(salary_dist, list) and salary_dist:
        metrics.append({"label": "薪酬区间数", "value": str(len(salary_dist)), "hint": "薪酬分布区间数"})
    return metrics


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #

def build_subject(raw: str, resolved: Mapping[str, Any], keyword_type: str) -> Dict[str, Any]:
    return {
        "enterprise": resolved.get("enterprise") or raw,
        "matchKeyword": resolved.get("enterprise") or raw,
        "keywordType": keyword_type,
        "match_raw": raw,
        "resolved": bool(resolved.get("resolved")),
        "resolve_reason": resolved.get("reason", ""),
    }


def build_metrics(trend: Mapping[str, Any], job_search_total: Any) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    t = trend if isinstance(trend, dict) else {}
    cur = t.get("recruitingCurrentCount")
    last3 = t.get("recruitingLastThreeMonthCount")
    metrics.append({"label": "当前招聘人数", "value": _text(cur) or "-", "hint": "当前在招岗位人数"})
    cur_n = _int(cur)
    last3_n = _int(last3)
    if cur_n and last3_n:
        ratio = last3_n / cur_n
        metrics.append({"label": "近三月招聘人数", "value": _text(last3) or "-", "hint": "近三个月招聘人数", "delta": f"为当前的 {ratio:.1f}x"})
    else:
        metrics.append({"label": "近三月招聘人数", "value": _text(last3) or "-", "hint": "近三个月招聘人数"})
    metrics.append({"label": "近三月岗位数", "value": _text(t.get("recruitingLastThreeMonthNo")) or "-", "hint": "近三月发布岗位数"})
    metrics.append({"label": "平均更新频率", "value": _text(t.get("recruitingAvgUpdate")) or "-", "hint": "岗位平均更新频率"})
    metrics.append({"label": "平均薪酬", "value": _text(t.get("recruitingAvgWorkingSalary")) or "-", "hint": "在招岗位平均薪酬"})
    metrics.append({"label": "在招岗位数", "value": str(job_search_total or "0") + " 个", "hint": "本次职位检索命中条数"})
    return [m for m in metrics if m.get("value") not in ("", None, "-")]


def build_caliber(subject: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "match_target": subject.get("enterprise") or subject.get("match_raw"),
        "match_type": f"招聘大数据按企业主体匹配（keywordType={subject.get('keywordType', 'name')}）；招聘 MCP 无模糊查询，需提供企业全称",
        "data_scope": "招聘趋势概览、雇主招聘画像、招聘需求分析、职位薪酬明细、招聘职位明细",
        "products": ["招聘明细", "招聘统计"],
        "limit": "数据来自招聘公开数据；少量字段可能存在更新延迟。",
    }


def build_core_analysis(trend: Any, profile: Any, demand_stats: Any, salary: Any, job_search: Any) -> Dict[str, Any]:
    p = profile if isinstance(profile, dict) else {}
    t = trend if isinstance(trend, dict) else {}
    ds = demand_stats if isinstance(demand_stats, dict) else {}

    # 雇主招聘画像 KV — 全部使用 profile / demand statistics 视图的真实字段。
    profile_kv: Dict[str, Any] = {}
    for k, label in (
        ("recruitingCurrentCount", "当前招聘人数"),
        ("recruitingLastThreeMonthCount", "近三月招聘人数"),
        ("recruitingLastThreeMonthNo", "近三月岗位数"),
        ("recruitingAvgUpdate", "岗位平均更新频率(秒)"),
        ("recruitingAvgWorkingSalary", "平均薪酬(元/月)"),
    ):
        src = p if p.get(k) is not None else ds
        if src.get(k) is not None:
            profile_kv[label] = _text(src.get(k))
    # 福利标签 / 城市列表 / 渠道 / 用工类型 / 业务关键词：profile 优先，回退 demand 统计视图。
    def _first_list_str(src: Mapping[str, Any], keys: Sequence[str]) -> List[str]:
        for k in keys:
            v = src.get(k)
            if isinstance(v, list) and v:
                return [str(x) for x in v if x]
        return []

    benefit_list = _first_list_str(p, ("benefitList", "welfareList")) or _first_list_str(ds, ("benefitList", "welfareList"))
    city_list = _first_list_str(p, ("recruitingCities", "recruitingCityList")) or _first_list_str(ds, ("recruitingCities", "recruitingCityList"))
    source_list = _first_list_str(p, ("recruitingSources", "channelList")) or _first_list_str(ds, ("recruitingSources", "channelList"))
    type_list = _first_list_str(p, ("recruitingTypes",)) or _first_list_str(ds, ("recruitingTypes",))
    biz_kw = _first_list_str(p, ("recruitingBusinessKeyWords",)) or _first_list_str(ds, ("recruitingBusinessKeyWords",))
    pos_kw = _first_list_str(p, ("recruitingPositionKeyWords",)) or _first_list_str(ds, ("recruitingPositionKeyWords",))

    # KV 内的城市/渠道做去重并展示前 N 项（更完整列表走专门 tags/bar 段）。
    def _dedup_keep(items: Sequence[str]) -> List[str]:
        seen, out = set(), []
        for it in items:
            if it and it not in seen:
                seen.add(it)
                out.append(it)
        return out

    city_dedup = _dedup_keep(city_list)
    source_dedup = _dedup_keep(source_list)
    if city_dedup:
        profile_kv["招聘城市数"] = str(len(city_dedup))
        profile_kv["主要城市"] = "、".join(city_dedup[:10]) + ("…" if len(city_dedup) > 10 else "")
    if source_dedup:
        profile_kv["招聘渠道数"] = str(len(source_dedup))
        profile_kv["主要渠道"] = "、".join(source_dedup[:10])
    if type_list:
        profile_kv["用工类型"] = "、".join(_dedup_keep(type_list))

    # 招聘需求统计 KV（statistics 视图的企业级汇总）。
    demand_kv: Dict[str, Any] = {}
    for k, label in (
        ("recruitingCurrentCount", "当前招聘规模"),
        ("recruitingLastThreeMonthCount", "近三月招聘规模"),
        ("recruitingLastThreeMonthNo", "近三月岗位数"),
        ("recruitingAvgWorkingSalary", "平均薪酬水平"),
    ):
        if ds.get(k) is not None:
            demand_kv[label] = _text(ds.get(k))
    if biz_kw:
        demand_kv["业务关键词"] = "、".join(biz_kw)
    if pos_kw:
        demand_kv["岗位关键词"] = "、".join(pos_kw)

    # 招聘趋势（汇总指标，非时间序列）。
    trend_rows = [
        {"指标": "当前招聘人数", "数值": _text(t.get("recruitingCurrentCount")) or "-"},
        {"指标": "近三月招聘人数", "数值": _text(t.get("recruitingLastThreeMonthCount")) or "-"},
        {"指标": "近三月岗位数", "数值": _text(t.get("recruitingLastThreeMonthNo")) or "-"},
        {"指标": "岗位平均更新频率", "数值": _text(t.get("recruitingAvgUpdate")) or "-"},
        {"指标": "平均薪酬", "数值": _text(t.get("recruitingAvgWorkingSalary")) or "-"},
    ]

    salary_total = _safe_total(salary)
    salary_rows = []
    for item in _first_list(salary):
        if not isinstance(item, dict):
            continue
        salary_rows.append({
            "职位": _text(item.get("recruitingName")) or "-",
            "城市": _text(item.get("recruitingCity")) or "-",
            "渠道": _text(item.get("recruitingSource")) or "-",
            "薪酬": _salary_text(item.get("workingSalary")) or "-",
            "发布日期": _text(item.get("recruitingPublishedTime")) or "-",
        })

    job_total = _safe_total(job_search)
    job_rows = []
    for item in _first_list(job_search):
        if not isinstance(item, dict):
            continue
        job_rows.append({
            "职位名称": _text(item.get("recruitingName")) or "-",
            "城市": _text(item.get("recruitingCity")) or "-",
            "渠道": _text(item.get("recruitingSource")) or "-",
            "薪酬": _salary_text(item.get("workingSalary")) or "-",
            "发布日期": _text(item.get("recruitingPublishedTime")) or "-",
        })

    # 派生：薪酬区间分布（聚合 salary_records，回退 job_records）
    salary_src = salary_rows if salary_rows else job_rows
    salary_dist_rows = _salary_dist_rows(salary_src)
    # 派生：城市分布（聚合 salary_records + job_records 去重城市计数）
    city_pool = list(salary_rows) + list(job_rows)
    city_dist_rows = _city_dist_rows(city_pool)
    # 派生：招聘渠道分布（profile / demand statistics 的渠道列表长度）
    source_dist_rows: List[Dict[str, Any]] = []
    for src in source_dedup:
        source_dist_rows.append({"渠道": src, "岗位来源数": "1"})
    # tags 段
    benefit_tags = benefit_list
    position_tags = pos_kw

    sections = [
        {"key": "employer_profile", "title": "雇主招聘画像", "kind": "kv"},
        {"key": "demand_stats", "title": "招聘需求统计", "kind": "kv", "note": "基于招聘统计视图的企业级汇总"},
        {"key": "benefit_tags", "title": "福利标签", "kind": "tags", "note": f"共 {len(benefit_tags)} 项福利标签"},
        {"key": "position_keywords", "title": "岗位关键词", "kind": "tags", "note": "高频岗位关键词（如工程师/经理等）"},
        {"key": "source_dist", "title": "招聘渠道分布", "kind": "bar", "note": "企业发布的招聘渠道列表",
         "chart": {"name": "渠道", "value": "岗位来源数", "orient": "h"},
         "columns": [("渠道", "渠道"), ("岗位来源数", "岗位来源数")]},
        {"key": "salary_dist", "title": "薪酬区间分布", "kind": "bar", "note": "按月薪区间聚合在招岗位数量",
         "chart": {"name": "薪酬区间", "value": "岗位数", "orient": "v"},
         "columns": [("薪酬区间", "薪酬区间"), ("岗位数", "岗位数")]},
        {"key": "city_dist", "title": "招聘城市分布", "kind": "bar", "note": "按城市聚合在招岗位数量",
         "chart": {"name": "城市", "value": "岗位数", "orient": "h"},
         "columns": [("城市", "城市"), ("岗位数", "岗位数")]},
        {"key": "trend_overview", "title": "招聘趋势", "kind": "table", "note": "招聘趋势概览（汇总指标，非逐月时间序列）",
         "columns": [("指标", "指标"), ("数值", "数值")]},
        {"key": "salary_records", "title": "职位薪酬明细", "kind": "table", "note": f"共 {salary_total or len(salary_rows)} 条，展示前若干条",
         "columns": [("职位", "职位"), ("城市", "城市"), ("渠道", "渠道"), ("薪酬", "薪酬"), ("发布日期", "发布日期")]},
        {"key": "job_records", "title": "招聘职位明细", "kind": "table", "note": f"共 {job_total or len(job_rows)} 条，展示前 N 条",
         "columns": [("职位名称", "职位名称"), ("城市", "城市"), ("渠道", "渠道"), ("薪酬", "薪酬"), ("发布日期", "发布日期")]},
    ]

    return {
        "sections": sections,
        "employer_profile": profile_kv,
        "demand_stats": demand_kv,
        "benefit_tags": benefit_tags,
        "position_keywords": position_tags,
        "source_dist": source_dist_rows,
        "salary_dist": salary_dist_rows,
        "city_dist": city_dist_rows,
        "trend_overview": trend_rows,
        "salary_records": salary_rows,
        "job_records": job_rows,
    }


def build_records(core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for item in core.get("job_records") or []:
        out.append({
            "职位名称": item.get("职位名称") or "-",
            "城市": item.get("城市") or "-",
            "薪酬": item.get("薪酬") or "-",
        })
    return out[:20]


def build_insights(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    metric_map = {m["label"]: str(m["value"]) for m in metrics}
    cur = metric_map.get("当前招聘人数")
    last3 = metric_map.get("近三月招聘人数")
    avg = metric_map.get("平均薪酬")

    if cur:
        insights.append({
            "feature": "招聘规模",
            "evidence": f"当前在招人数 {cur}。",
            "interpretation": "当前招聘规模反映企业业务扩张与人才需求的即时强度，是组织活跃度的直接信号。",
        })
    if cur and last3:
        try:
            c = float(cur)
            l = float(last3)
            if c > 0:
                ratio = l / c
                converge = "已部分收敛/岗位补齐" if ratio > 1.2 else ("持续高密度扩张" if ratio < 0.8 else "保持平稳节奏")
                insights.append({
                    "feature": "近期招聘节奏",
                    "evidence": f"近三月招聘 {last3}，为当前在招的 {ratio:.1f}x。",
                    "interpretation": f"近三月/当前比反映招聘收敛度：{converge}。",
                })
        except (TypeError, ValueError):
            pass
    elif last3:
        insights.append({
            "feature": "近期招聘节奏",
            "evidence": f"近三月招聘人数 {last3}。",
            "interpretation": "近三月招聘量反映企业持续扩张能力；若显著高于当前在招，说明招聘已部分收敛或岗位已补齐。",
        })
    # 薪酬区间集中度
    salary_dist = core.get("salary_dist") or []
    if salary_dist:
        conc = _concentration(salary_dist, "薪酬区间", "岗位数", 1)
        if conc:
            insights.append({
                "feature": "薪酬带集中度",
                "evidence": f"“{conc['top']}”区间岗位占比约 {conc['top_share']:.0f}%。",
                "interpretation": "薪酬带集中度反映人才定位：偏低薪区间偏多常见于运营/客服密集型团队，偏高薪区间偏多则反映核心技术岗位（研发/算法）占比较高。",
            })
    # 平均薪酬换算（K 中位）— salary/job 行已渲染为 "薪酬": "min-max" 字符串。
    salary_rows = core.get("salary_records") or []
    job_rows = core.get("job_records") or []
    sample = salary_rows if salary_rows else job_rows
    mids = []
    for r in sample:
        v = r.get("薪酬") or r.get("薪酬区间")
        m = _salary_mid_k(v)
        if m is not None:
            mids.append(m)
    mids = [m for m in mids if m is not None]
    if mids:
        avg_mid = sum(mids) / len(mids)
        insights.append({
            "feature": "薪酬水平",
            "evidence": f"样本岗位薪酬中位均值约 {avg_mid:.0f}K/月（n={len(mids)}）。",
            "interpretation": "薪酬中位均值反映企业人才预算与岗位定位；结合行业基准可评估其人才竞争力，高均值通常对应研发/技术密集型团队。",
        })
    elif avg and avg != "-":
        insights.append({
            "feature": "薪酬水平",
            "evidence": f"在招岗位平均薪酬 {avg} 元/月。",
            "interpretation": "平均薪酬反映企业人才预算与岗位定位；结合行业基准可评估其人才竞争力。",
        })
    # 渠道集中度（profile/demand 提供的渠道列表）
    source_dist = core.get("source_dist") or []
    if source_dist:
        conc = _concentration(source_dist, "渠道", "岗位来源数", 3)
        if conc:
            insights.append({
                "feature": "招聘渠道",
                "evidence": f"覆盖 {conc['n']} 个招聘渠道，主流渠道为“{conc['top']}”。",
                "interpretation": "渠道覆盖面反映招聘触达能力；主流招聘平台（Boss/猎聘/智联等）为主时偏向中高端与白领岗位，制造业平台偏多则对应一线生产岗位。",
            })
    # 城市分布集中度
    city_dist = core.get("city_dist") or []
    if city_dist:
        conc = _concentration(city_dist, "城市", "岗位数", 2)
        if conc:
            insights.append({
                "feature": "地域集中度",
                "evidence": f"“{conc['top']}”岗位占比约 {conc['top_share']:.0f}%，前 2 城市合计 {conc['cr']:.0f}%（CR2），覆盖 {conc['n']} 个城市。",
                "interpretation": "招聘城市集中度反映业务地域重心：CR2 偏高通常意味着总部或核心研发/运营中心；城市数偏多则代表多区域分布式团队。",
            })
    if not insights:
        insights.append({
            "feature": "数据完整性",
            "evidence": "部分维度未返回有效数据。",
            "interpretation": "建议核对匹配关键词是否为企业全称，或检查 MCP 连接与上游数据产品覆盖范围。",
        })
    return insights


def build_abstract(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]]) -> str:
    name = subject.get("enterprise") or subject.get("match_raw") or "目标企业"
    parts = [f"本报告以“{name}”为分析对象，基于招聘公开数据，系统呈现雇主招聘画像、招聘需求统计、招聘趋势、职位薪酬与招聘职位明细。"]
    if metrics:
        kv = "、".join(f"{m['label']} {m['value']}" for m in metrics[:5])
        parts.append(f"关键指标包括：{kv}。")
    parts.append("报告同时给出招聘规模、近期招聘节奏与薪酬水平的结构化解读，便于人才市场分析与组织扩张研究参考。")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Dry-run sample
# --------------------------------------------------------------------------- #

def build_dry_run_payload(raw: str, keyword_type: str) -> Dict[str, Any]:
    try:
        sample = load_json_file(SAMPLE_PATH)
    except Exception:
        sample = {}
    sample = sample if isinstance(sample, dict) else {}
    subject = sample.get("subject") or {"enterprise": raw, "matchKeyword": raw, "keywordType": keyword_type, "match_raw": raw}
    subject = {**subject, "match_raw": raw, "keywordType": keyword_type}
    core = sample.get("core_analysis") or {}
    metrics = sample.get("metrics") or []
    return _assemble(subject, core, metrics, dry_run=True)


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def _assemble(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]], *, dry_run: bool) -> Dict[str, Any]:
    abstract = build_abstract(subject, core, metrics)
    records = build_records(core)
    insights = build_insights(subject, core, metrics)
    # Quality gate: count populated core-analysis sections.
    ca = core if isinstance(core, dict) else {}
    secs = ca.get("sections", [])
    if secs:
        total_secs = len(secs)
        populated = sum(1 for s in secs if isinstance(s, dict) and ca.get(s.get("key")) not in (None, "", [], {}))
    else:
        total_secs = max(1, len([k for k in ca if k != "sections"]))
        populated = sum(1 for k in ca if k != "sections" and ca.get(k) not in (None, "", [], {}))
    quality_report = {
        "total_sections": total_secs,
        "populated_sections": populated,
        "empty_sections": total_secs - populated,
        "coverage_pct": round(populated / max(1, total_secs) * 100),
    }
    if populated == 0:
        import sys
        print("⚠️ 质量门禁警告: 所有核心分析维度均无数据", file=sys.stderr)
    title = f"{subject.get('enterprise') or '目标企业'} 招聘大数据报告"
    return {
        "report_type": REPORT_TYPE,
        "title": title,
        "banner": REPORT_BANNER,
        "subject": dict(subject),
        "abstract": abstract,
        "summary": abstract,
        "executive_summary": [item["interpretation"] for item in insights][:5] or [abstract[:120]],
        "metrics": list(metrics),
        "caliber": build_caliber(subject),
        "core_analysis": dict(core),
        "representative_records": records,
        "insights": insights,
        "data_source": {
            "mcp_server": "recruitment-mcp-server",
            "products": [
                {"name": "招聘明细", "product_id": "66b338e274bf098447db7f09"},
                {"name": "招聘统计", "product_id": "66b338e274bf098447db7f1b"},
            ],
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "dry_run": dry_run,
            "quality_report": quality_report,
        },
    }


def build_payload(raw: str, keyword_type: str, view: str, page_size: int) -> Dict[str, Any]:
    resolved = resolve_enterprise_name(raw)
    enterprise = resolved["enterprise"]
    mk_args: Dict[str, Any] = {"matchKeyword": enterprise, "keywordType": keyword_type}
    search_args: Dict[str, Any] = {**mk_args, "pageIndex": 1, "pageSize": page_size}

    trend = _safe_call(T_TREND, mk_args)
    profile = _safe_call(T_PROFILE, mk_args)
    # The 招聘需求统计 section reads enterprise-level summary fields, so the
    # report prefers the statistics view; --view=details still flows through to
    # the demand tool but yields sparser KV (job records come from job_search).
    demand_stats = _safe_call(T_DEMAND, {**mk_args, "view": view, "listLimit": 50})
    salary = _safe_call(T_SALARY, search_args)
    job_search = _safe_call(T_JOB_SEARCH, search_args)

    subject = build_subject(raw, resolved, keyword_type)
    core = build_core_analysis(trend, profile, demand_stats, salary, job_search)
    metrics = build_metrics(
        trend if isinstance(trend, dict) else {},
        _safe_total(job_search) if isinstance(job_search, dict) else None,
    )
    _derive_core_metrics(metrics, core if isinstance(core, dict) else {})
    return _assemble(subject, core, metrics, dry_run=False)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Compose a recruitment big-data report via the recruitment MCP.")
    parser.add_argument("--enterprise", required=True, help="企业全称（招聘 MCP 无模糊查询，建议直接提供企业全称）")
    parser.add_argument("--keyword-type", default="name", help="主体类型：name/nameId/regNumber/socialCreditCode")
    parser.add_argument("--view", default="statistics", choices=["details", "statistics"], help="招聘需求分析视图：details=岗位级需求；statistics=企业汇总需求")
    parser.add_argument("--page-size", type=int, default=50, help="检索明细分页大小（最多 50）")
    parser.add_argument("--dry-run", action="store_true", help="不调用真实 MCP，使用样例数据组装报告骨架")
    parser.add_argument("--output", help="输出 JSON 路径；省略则打印到 stdout")
    parser.add_argument("--report-output", help="同时输出 HTML 报告（.html）与 Markdown 报告（.md）")
    parser.add_argument("--pdf-output", help="额外输出 PDF 报告（.pdf）；需要 Playwright + Chromium")
    args = parser.parse_args()

    if args.dry_run:
        payload = build_dry_run_payload(args.enterprise, args.keyword_type)
    else:
        payload = build_payload(args.enterprise, args.keyword_type, args.view, args.page_size)

    if args.output:
        out = pathlib.Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_dumps(payload, pretty=True), encoding="utf-8")
        print_json({"ok": True, "json": str(out), "dry_run": args.dry_run})
    else:
        print_json(payload)

    if args.report_output:
        base_out = pathlib.Path(args.report_output).expanduser()
        base_out.parent.mkdir(parents=True, exist_ok=True)
        html_path = base_out.with_suffix(".html") if base_out.suffix.lower() not in (".html", ".htm") else base_out
        md_path = html_path.with_suffix(".md")
        html_path.write_text(render_html(payload), encoding="utf-8")
        md_path.write_text(render_markdown(payload), encoding="utf-8")
        if args.pdf_output:
            pdf_path = pathlib.Path(args.pdf_output).expanduser()
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            html_to_pdf(render_html(payload), str(pdf_path))
        print_json({"ok": True, "html": str(html_path), "markdown": str(md_path), "pdf": str(pdf_path) if args.pdf_output else None, "dry_run": args.dry_run})


if __name__ == "__main__":
    main()
